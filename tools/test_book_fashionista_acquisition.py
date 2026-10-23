"""Fashionista: actual class acquisition with two chosen skills, Feature rank prerequisites, recipes and Parfumier."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from grid import Grid
from native_scenario_fixture import prepare_body, assert_rejected_unchanged
import action_points as AP
import fashionista as FA
import frequency as FREQ
import held_equipment as HELD
import items as I
import state_codec as CODEC
import state_fields as FIELDS
import trainer_feature_acquisition as ACQUIRE
import world_entities as WORLD


class FashionistaAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.setup()

    def setup(self, *, charm=6, intuition=6, choices=('매력', '직감')):
        self.e = Engine(self.rules, seed=19842044)
        self.e.grid = Grid(14, 12)
        self.common = dict(level=30, size='중형',
            stats={'hp':1000, 'atk':20, 'def':20, 'spa':20, 'spd':20, 'spe':20},
            moves=['move/몸통박치기'], abilities=[], types=['노말'],
            movement={'land':6, 'swim':0, 'sky':0, 'power':4}, weight_kg=30,
            skills={'매력':charm, '직감':intuition, '명령':6, '교활':6, '협박':6, '집중':6, '통찰':6, '전투':3, '은신':3})
        self.t = self.add('actual Fashionista', 'trainer', (1, 1), classes=[], feats=[], exp_bank=100, money=20000,
            fashionista_skill_choices=list(choices))
        self.p = self.add('actual model', 'pokemon', (2, 2), trainer_id=self.t.entity_id, tutor_points=8,
            species='피카츄', types=['전기'], moves=['move/전광석화'], speed=25)
        self.q = self.add('actual thief', 'pokemon', (3, 2), side='foe', species='피카츄', types=['전기'],
            moves=['move/도둑질', 'move/탁쳐서떨구기', 'move/바꿔치기', 'move/전광석화'], speed=15)
        self.e.gm.observe_loyalty(self.p, 6, reason='actual willing Pokemon')

    def add(self, name, kind, pos, speed=None, **extra):
        spec = dict(deepcopy(self.common), name=name, kind=kind)
        if speed is not None:
            spec['stats'] = dict(spec['stats'], spe=speed)   # distinct Speeds keep initiative schedules tie-free
        spec.update(extra)
        actor = Combatant(self.e.r, spec)
        self.e.gm.add_combatant(actor, pos=pos, side=extra.get('side', 'party'),
            reason='actual Fashionista scene participant')
        prepare_body(self.e, actor, size='중형', offsets=[(0, 0)], reason='observed complete body')
        return actor

    def acquire(self, feature=None, actor=None):
        feature = FA.CLASS if feature is None else FA.uid(feature)
        actor = self.t if actor is None else actor
        return ACQUIRE.acquire_static(self.e, actor, feature,
            acquisition_request_id='fashionista/' + actor.entity_id + '/' + feature)

    def whole(self):
        """Class and every Feature in printed order."""
        for feature in (FA.CLASS, FA.MAKEOVER, FA.STYLE, FA.ACCESSORIZE, FA.PARFUMIER, FA.WARDROBE, FA.DRESS):
            self.acquire(feature)

    def rejected(self, operation, pattern):
        return assert_rejected_unchanged(self.e, operation, reason_pattern=pattern)

    def valid(self):
        result = self.e.validate_state()
        self.assertTrue(result['valid'], result['issues'])

    def restore(self):
        names = ('t', 'p', 'q', 'u', 'v', 'c')
        identities = {name:getattr(self, name).entity_id for name in names if hasattr(self, name)}
        self.e = CODEC.load_engine(self.rules, json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
        actors = WORLD.actor_index(self.e)
        for name, identity in identities.items():
            setattr(self, name, actors[identity])

    def skills(self, **ranks):
        FIELDS.base_patch(self.t, {'skills':dict(self.t.spec['skills'], **ranks)}, reason='observed actual skill ranks')

    # ---- shared scene helpers borrowed by the equipment/wardrobe test modules ----
    def item(self, uid, item_id, owner):
        """An actual inspected item instance legally owned by the given actor."""
        WORLD.register_object(self.e, uid, location={'kind':'unknown'}, reason='actual inspected item',
            kind='item_instance', item_rule_id=item_id, owner_id=owner.entity_id)
        return self.e._physical_objects[uid]

    def hold(self, pokemon, uid, item_id):
        self.item(uid, item_id, pokemon)
        return I.equip_held(self.e, pokemon, item_id, source_instance_id=uid)

    def wear(self, trainer, uid, item_id):
        self.item(uid, item_id, trainer)
        return I.register_item(self.e, trainer, item_id, source_instance_id=uid)

    def combat(self, actor, *, count=30):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor, initiative_count=count)

    def next_turn(self, actor, *, count=30):
        self.e.end_of_turn(self.e._active_turn_actor)
        self.e.end_round()
        self.combat(actor, count=count)

    def use(self, actor, target, move, *, face=10, **options):
        if move not in actor.moves:
            self.e.gm.set_move(actor, move, reason='actual complete known Move list')
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.use_move_on(actor, target, move, self.e.everyone, set_damage=True, **options)

    def craft(self, recipe_id, *, uid=None, owner=None, event=None, **options):
        policy = None if uid is None else {'mode':'create', 'instance_ids':[uid], 'owner_id':(owner or self.t).entity_id,
                                           'state':'intact', 'attachments':[]}
        return FA.craft(self.e, self.t, recipe_id, seconds=600, reason='actual completed Fashionista crafting',
            product_policy=policy, event_id=event or ('craft:' + (uid or recipe_id)), **options)

    def incense(self, uid='incense:1', owner=None, move='달콤한향기', recipe='fashionista/incense-lax'):
        return self.craft(recipe, uid=uid, owner=owner or self.p, incense_move=move)

    def decisions(self, trainer, feature):
        import trainer_retraining as RETRAINING
        sources = {owned:RETRAINING.owned_source(self.e, trainer, owned) for owned in RETRAINING._owned(trainer)}
        retained = {source:list(trainer.spec['state_grants']['sources'][source].get('withdrawal_dependencies', []))
                    for owned, source in sources.items() if owned != feature}
        for child, parents in RETRAINING._native_dependencies(self.e, trainer, RETRAINING._owned(trainer)).items():
            if child != feature:
                retained[sources[child]] = [sources[parent] for parent in parents]
        return dict(request_id='retrain/' + feature, reason='actual trainer chooses retraining',
                    gm_decision={'allowed':True, 'reason':'GM reviewed prerequisites and narrative'},
                    retained_dependencies=retained)

    def retrain(self, feature):
        return self.e.retrain_trainer_source(self.t, feature, **self.decisions(self.t, feature))

    # ---------------------------------------------------------------- class and Features
    def test_template_is_complete_and_class_choice_records_two_skills_without_followers(self):
        self.assertEqual(len(FA.DEFINITIONS), 7)
        self.assertEqual(set(FA.DEFINITIONS), set(FA.FEATURES))
        for feature in FA.FEATURES:
            self.assertEqual(ACQUIRE.STATIC_FEATURES[feature]['clause_id'], FA.clause(feature))
        self.assertEqual({FA.clause(f) for f in (FA.MAKEOVER, FA.ACCESSORIZE, FA.WARDROBE, FA.DRESS)},
                         {'C04-075', 'C04-076', 'C04-077', 'C04-078'})
        receipt = self.acquire()
        self.assertEqual(receipt['snapshot'], {'skills':['매력', '직감'], 'ranks':{'매력':6, '직감':6}, 'parents':[]})
        self.assertEqual(receipt, self.acquire())
        self.assertEqual(self.t.spec['feats'], [FA.CLASS])
        self.assertEqual(FA.chosen_skills(self.t), ['매력', '직감'])
        for feature in (FA.MAKEOVER, FA.STYLE, FA.ACCESSORIZE, FA.PARFUMIER, FA.WARDROBE, FA.DRESS):
            self.assertIsNone(FA.acquired(self.t, feature))
        # The class alone permits the three Contest Trends recipes; the Basic Fashion rows are homebrew-excluded under core.
        self.assertEqual(FA.craftable(self.e, self.t),
            ['fashionista/contest-accessory', 'fashionista/contest-fashion', 'fashionista/fancy-clothes'])
        self.restore()
        self.valid()
        self.assertEqual(FA.chosen_skills(self.t), ['매력', '직감'])

    def test_class_requires_two_distinct_printed_skills_at_novice_and_an_actual_trainer(self):
        self.t.spec.pop(FA.CHOICES)
        self.rejected(self.acquire, 'skill choice')
        self.t.spec[FA.CHOICES] = ['매력', '매력']
        self.rejected(self.acquire, 'skill choice')
        self.t.spec[FA.CHOICES] = ['매력', '통찰']
        self.rejected(self.acquire, 'skill choice')
        self.t.spec[FA.CHOICES] = ['매력', '직감', '명령']
        self.rejected(self.acquire, 'skill choice')
        self.setup(intuition=2)
        self.rejected(self.acquire, 'Novice')
        self.setup(intuition=3)
        self.assertEqual(self.acquire()['snapshot']['ranks'], {'매력':6, '직감':3})
        self.p.spec[FA.CHOICES] = ['매력', '직감']
        self.rejected(lambda:self.acquire(actor=self.p), 'Trainer|trainer')
        self.rejected(lambda:self.acquire(FA.MAKEOVER, actor=self.p), 'Trainer|trainer')

    def test_feature_prerequisites_need_the_class_parent_and_printed_adept_expert_counts(self):
        self.setup(charm=3, intuition=3)
        self.rejected(lambda:self.acquire(FA.MAKEOVER), 'Fashionista class')
        self.rejected(lambda:self.acquire(FA.STYLE), 'Fashionista class')
        self.acquire()
        self.rejected(lambda:self.acquire(FA.ACCESSORIZE), 'Dashing Makeover')
        self.acquire(FA.MAKEOVER)
        self.acquire(FA.STYLE)
        self.rejected(lambda:self.acquire(FA.ACCESSORIZE), 'Adept')
        self.rejected(lambda:self.acquire(FA.PARFUMIER), 'Expert')
        self.rejected(lambda:self.acquire(FA.WARDROBE), 'Adept rank in 2')
        self.rejected(lambda:self.acquire(FA.DRESS), 'Versatile Wardrobe')
        self.skills(명령=6, 교활=6)   # ranks outside the committed choice do not count
        self.rejected(lambda:self.acquire(FA.ACCESSORIZE), 'Adept')
        self.skills(매력=4)
        self.acquire(FA.ACCESSORIZE)
        self.rejected(lambda:self.acquire(FA.WARDROBE), 'Adept rank in 2')
        self.skills(직감=4)
        receipt = self.acquire(FA.WARDROBE)
        self.assertEqual(receipt['snapshot']['ranks'], {'매력':4, '직감':4})
        self.rejected(lambda:self.acquire(FA.DRESS), 'Expert rank in 2')
        self.rejected(lambda:self.acquire(FA.PARFUMIER), 'Expert')
        self.skills(매력=5)
        self.acquire(FA.PARFUMIER)
        self.rejected(lambda:self.acquire(FA.DRESS), 'Expert rank in 2')
        self.skills(직감=5)
        receipt = self.acquire(FA.DRESS)
        self.assertEqual(list(receipt['snapshot']['prerequisites']), [FA.WARDROBE])
        self.rejected(lambda:ACQUIRE.acquire_static(self.e, self.t, FA.DRESS, acquisition_request_id='fashionista/again'), 'already acquired')
        self.assertEqual(len(FA.records(self.t, active=True)), 7)
        self.restore()
        self.valid()

    def test_json_and_gm_restore_keep_receipts_and_reject_a_tampered_skill_choice(self):
        self.whole()
        before = deepcopy(self.t.spec['state_grants']['sources'])
        self.e.gm.snapshot('fashionista')
        self.e.gm.restore('fashionista')
        self.assertEqual(self.t.spec['state_grants']['sources'], before)
        self.restore()
        self.valid()
        self.assertEqual(FA.chosen_skills(self.t), ['매력', '직감'])
        record = next(row for row in self.t.spec['state_grants']['sources'].values()
                      if row.get('static_acquisition', {}).get('feature_id') == FA.CLASS)
        record['static_acquisition']['snapshot']['skills'] = ['매력', '명령']
        self.assertFalse(self.e.validate_state()['valid'])

    # ---------------------------------------------------------------- recipes
    def test_fashionista_recipes_craft_through_the_shared_owners_with_printed_cost_and_explicit_duration(self):
        self.acquire()
        self.rejected(lambda:self.craft('fashionista/practical-winter-cloak'), 'requirements are not met')
        self.rejected(lambda:self.craft('fashionista/incense-lax'), 'requirements are not met')
        self.rejected(lambda:self.craft('fashionista/basic-fashion-charm'), 'requirements are not met')
        self.rejected(lambda:self.craft('fashionista/unknown'), 'printed Fashionista recipe')
        self.rejected(lambda:FA.craft(self.e, self.t, 'fashionista/contest-accessory', seconds=0, reason='x'), 'seconds')
        self.rejected(lambda:self.craft('fashionista/contest-accessory', incense_move='달콤한향기'), 'only a Parfumier')
        elapsed = self.e.elapsed_seconds
        result = self.craft('fashionista/contest-accessory')
        self.assertEqual((result['item_id'], result['money_spent'], result['category']), ('item/콘테스트-장신구', 750, '패션 도구'))
        self.assertEqual((self.t.spec['money'], self.e.elapsed_seconds, self.t.spec['items']['item/콘테스트-장신구']), (19250, elapsed + 600, 1))
        self.assertEqual(self.t._action_history, ['extended'])
        self.acquire(FA.MAKEOVER)
        self.assertIn('fashionista/practical-winter-cloak', FA.craftable(self.e, self.t))
        self.assertNotIn('fashionista/focused-focus-band', FA.craftable(self.e, self.t))
        self.acquire(FA.STYLE)
        self.assertIn('fashionista/focused-focus-sash', FA.craftable(self.e, self.t))
        made = self.craft('fashionista/focused-focus-sash', uid='sash:1')
        self.assertEqual((made['product_instance_ids'], self.t.spec['money'], self.t.spec['items']['item/기합의띠']), (['sash:1'], 17250, 0))
        self.assertEqual(self.e._physical_objects['sash:1']['crafting_origin']['maker_id'], self.t.entity_id)
        self.assertNotIn(FA.INCENSE, self.e._physical_objects['sash:1'])
        self.restore()
        self.valid()
        self.assertEqual(len(self.t.spec['resource_transformations']), 2)

    def test_parfumier_binds_the_chosen_move_to_each_crafted_incense_and_lists_it_only_while_the_own_pokemon_actively_holds_it(self):
        self.acquire()
        self.acquire(FA.PARFUMIER)
        self.rejected(lambda:self.incense(move=None), 'Sweet Scent or Aromatic Mist')
        self.rejected(lambda:self.incense(move='전광석화'), 'Sweet Scent or Aromatic Mist')
        self.rejected(lambda:self.craft('fashionista/incense-lax', incense_move='달콤한향기'), 'physical product')
        money = self.t.spec['money']
        self.incense()
        choice = self.e._physical_objects['incense:1'][FA.INCENSE]
        self.assertEqual((choice['move_id'], choice['maker_id'], self.t.spec['money']), ('move/달콤한향기', self.t.entity_id, money - 1000))
        self.incense(uid='incense:2', move='아로마미스트', recipe='fashionista/incense-luck')
        self.assertEqual(self.e._physical_objects['incense:2'][FA.INCENSE]['move_id'], 'move/아로마미스트')
        self.assertNotIn('move/달콤한향기', self.p.moves)
        I.equip_held(self.e, self.p, 'item/무사태평향로', source_instance_id='incense:1')
        self.assertIn('move/달콤한향기', self.p.moves)
        self.assertEqual(self.p.stages['spe'], 0)
        self.valid()
        self.restore()
        self.valid()
        self.assertIn('move/달콤한향기', self.p.moves)
        # Theft moves the Incense out of the maker's Pokemon: the Move leaves with it and the thief gains nothing.
        I.transfer_equipment(self.e, self.p, self.q, 'incense:1', consent_by=(self.p,))
        self.assertNotIn('move/달콤한향기', self.p.moves)
        self.assertNotIn('move/달콤한향기', self.q.moves)
        self.assertEqual(HELD.entries(self.q)[0]['instance_id'], 'incense:1')
        self.valid()
        I.transfer_equipment(self.e, self.q, self.p, 'incense:1', consent_by=(self.q,))
        self.assertIn('move/달콤한향기', self.p.moves)
        I.unregister_item(self.e, self.p, registration_key=HELD.entries(self.p)[0]['registration_key'])
        self.assertNotIn('move/달콤한향기', self.p.moves)
        # A Luck Incense crafted with Aromatic Mist adds that Move instead; the Pokemon-only Incense never lists on the Trainer.
        I.equip_held(self.e, self.p, 'item/행운의향로', source_instance_id='incense:2')
        self.assertIn('move/아로마미스트', self.p.moves)
        self.assertNotIn('move/달콤한향기', self.p.moves)
        self.assertNotIn('move/아로마미스트', self.t.moves)
        # Another Trainer's Parfumier Incense never grants on this Pokemon.
        self.u = self.add('other Fashionista', 'trainer', (1, 6), classes=[], feats=[], exp_bank=100, money=20000,
            fashionista_skill_choices=['매력', '직감'], speed=18)
        self.acquire(actor=self.u)
        self.acquire(FA.PARFUMIER, actor=self.u)
        FA.craft(self.e, self.u, 'fashionista/incense-luck', seconds=600, reason='actual other crafting', incense_move='달콤한향기',
            product_policy={'mode':'create', 'instance_ids':['incense:3'], 'owner_id':self.p.entity_id, 'state':'intact', 'attachments':[]}, event_id='craft:3')
        I.unregister_item(self.e, self.p, registration_key=HELD.entries(self.p)[0]['registration_key'])
        I.equip_held(self.e, self.p, 'item/행운의향로', source_instance_id='incense:3')
        self.assertNotIn('move/달콤한향기', self.p.moves)
        self.restore()
        self.valid()
        # A grant that no active Incense justifies is detected.
        self.p.spec['state_grants']['sources'][FA.INCENSE_PREFIX + self.p.entity_id + ':incense:3'] = {'kind':'item', 'grants':{'moves':['move/달콤한향기']}}
        self.assertFalse(self.e.validate_state()['valid'])

    # ---------------------------------------------------------------- retraining
    def test_retraining_withdraws_only_what_each_fashionista_source_justified(self):
        self.whole()
        self.incense()
        I.equip_held(self.e, self.p, 'item/무사태평향로', source_instance_id='incense:1')
        self.assertIn('move/달콤한향기', self.p.moves)
        self.wear(self.t, 'brace:fire', 'item/불꽃깁스')
        self.wear(self.t, 'brace:ice', 'item/얼음깁스')
        self.assertEqual(len(FA._accessory_registrations(self.t)), 2)
        FA.arm_style(self.e, self.t, self.p)
        ap = AP.available(self.t)
        FA.makeover(self.e, self.t, self.p, 'item/겨울망토', recipe_id='fashionista/practical-winter-cloak', seconds=600, reason='actual makeover')
        self.assertEqual(AP.available(self.t), ap - 2)
        self.retrain(FA.ACCESSORIZE)
        self.assertEqual([row['item_id'] for _, row in FA._accessory_registrations(self.t)], ['item/불꽃깁스'])
        self.assertIn('move/달콤한향기', self.p.moves)
        self.retrain(FA.PARFUMIER)
        self.assertNotIn('move/달콤한향기', self.p.moves)
        self.assertEqual(HELD.entries(self.p)[0]['instance_id'], 'incense:1')   # the Incense itself stays held
        self.assertIsNotNone(FA.armed(self.p))
        self.retrain(FA.STYLE)
        self.assertIsNone(FA.armed(self.p))
        self.assertIsNotNone(FA.makeover_record(self.p))
        self.retrain(FA.DRESS)
        self.retrain(FA.MAKEOVER)
        self.assertIsNone(FA.makeover_record(self.p))
        self.assertEqual(AP.available(self.t), ap)
        self.assertEqual(self.t.spec['fashionista_makeover_history'][-1]['cause'], 'retrained:' + FA.MAKEOVER)
        self.assertNotIn('makeover:' + self.t.entity_id, getattr(self.p, '_item_reg', {}))
        # The Chic transformation is a completed permanent effect; the Wardrobe source cannot be retrained after use.
        FA.make_chic(self.e, self.t, self.p, seconds=600, reason='actual completed wardrobe')
        self.rejected(lambda:self.retrain(FA.WARDROBE), 'irreversible|permanent|used')
        self.restore()
        self.valid()
        self.assertEqual(self.t.spec['feats'], [FA.CLASS, FA.WARDROBE])


if __name__ == '__main__':
    unittest.main()
