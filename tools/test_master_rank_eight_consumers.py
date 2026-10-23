"""Virtuoso (ch03:331-333, core-1.05 Virtuoso) makes the chosen Master skill count as Rank 8 for rank-dependent
Features and effects, while prerequisites and skill dice keep the ordinary Master rank 6.

Consumers repaired by audit_master_rank_eight_consumers_repair (audit S-ta2-13, S-p2c4-2, S-p2_cls_ch03_1-2):
- Potent Venom (input/ch04-trainer-classes.md:1737-1741): the stored Type Link effect rank 8 stays a valid world.
- Dietician (C04-071): the acquisition evidence records the ordinary Expert/Master prerequisite rank, not 8.
- Deep Diver / Traceur (C04-094 terrain talents): Survival rank minutes of breath and half Survival rank evasion use 8.
- Glyph (supp-fantasy:615-621, consumer special_entities.validate_glyph): active glyphs equal to the Occult rank use 8.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine, Rules, Combatant
from builder import build_trainer, build_pokemon
import book_survivalist_fixture as SURVIVAL
import items as ITEMS
import move_state as MOVES
import pokemon_party as PARTY
import skill_modifiers as SKILL
import special_entities as SPECIAL
import state_codec as CODEC
import state_grants as GRANTS
import survivalist_class as SC
import test_book_type_ace_acquisition as ACE_FIXTURE
import test_book_type_ace_reactions as ACE_REACTIONS
import trainer_capabilities as TRAINER
import vitamin_capacity as VITAMIN
import world_entities as WORLD

VIRTUOSO = 'edge/거장'


def add_virtuoso(engine, trainer, skill):
    """Acquire one Virtuoso for an already Master skill through the ordinary state transition."""
    GRANTS.transition(engine, trainer, lambda e, owner: owner.spec.update(
        edges=[*owner.spec.get('edges', []), VIRTUOSO], edge_choices={VIRTUOSO: [skill]}))


def issues(engine):
    result = engine.validate_state()
    return result['valid'], ' '.join(str(x) for x in result.get('issues', []))


class PotentVenomVirtuosoTests(unittest.TestCase):
    """input/ch04-trainer-classes.md:1737-1741: extra loss equal to the Type Link skill rank."""
    setUpClass = classmethod(ACE_FIXTURE.TypeAceAcquisitionTests.setUpClass.__func__)
    setUp = ACE_FIXTURE.TypeAceAcquisitionTests.setUp
    setup = ACE_FIXTURE.TypeAceAcquisitionTests.setup
    add = ACE_FIXTURE.TypeAceAcquisitionTests.add
    acquire = ACE_FIXTURE.TypeAceAcquisitionTests.acquire
    combat = ACE_FIXTURE.TypeAceAcquisitionTests.combat
    restore = ACE_FIXTURE.TypeAceAcquisitionTests.restore
    valid = ACE_FIXTURE.TypeAceAcquisitionTests.valid
    family = ACE_REACTIONS.TypeAceReactionTests.family
    known = ACE_REACTIONS.TypeAceReactionTests.known
    answer = ACE_REACTIONS.TypeAceReactionTests.answer
    native = ACE_REACTIONS.TypeAceReactionTests.native

    def poisoned(self, *, virtuoso):
        self.family('독', 'Potent Venom')
        skill = self.t.spec['type_link_skills']['독']
        if virtuoso:
            add_virtuoso(self.e, self.t, skill)
        self.assertEqual(SKILL.rank(self.e.r, self.t, skill)[1:], ('6d6', 6))
        self.assertEqual(SKILL.effective_rank(self.e.r, self.t, skill), 8 if virtuoso else 6)
        self.answer('type_ace_choice', True)
        self.answer('type_ace_potent_venom_stat', 'atk')
        self.e.gm.set_position(self.b, (3, 2), reason='adjacent actual poisoned foe')
        self.combat(self.p)
        self.native(self.p, self.b, 'move/독가루', face=15)
        self.assertIn('독', self.b.conditions)
        self.assertEqual((self.b.stages['atk'], self.b.stages['spd']), (-2, 0))
        return self.b.custom_conditions['type_ace_poison']

    def poison_tick(self):
        self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_of_turn(self.b, initiative_count=20)
        self.native(self.b, self.q, 'move/몸통박치기')
        tick, before = self.e.tick(self.b), self.b.hp
        self.e.end_of_turn(self.b)
        return before - self.b.hp, tick

    def test_virtuoso_type_link_rank_eight_adds_eight_and_stays_valid_through_gm_and_json_restore(self):
        row = self.poisoned(virtuoso=True)
        self.assertEqual(row['rank'], 8)
        self.valid()
        self.e.gm.snapshot('potent-venom-eight')
        self.e.cure_status(self.b, '독')
        self.assertNotIn('type_ace_poison', self.b.custom_conditions)
        self.e.gm.restore('potent-venom-eight', reason='actual rewind to the sourced Potent Venom poison')
        self.assertEqual(self.b.custom_conditions['type_ace_poison']['rank'], 8)
        self.valid()
        self.restore()
        self.assertEqual(self.b.custom_conditions['type_ace_poison']['rank'], 8)
        self.valid()
        lost, tick = self.poison_tick()
        self.assertEqual(lost, tick + 8)
        self.assertEqual(SKILL.rank(self.e.r, self.t, self.t.spec['type_link_skills']['독'])[1], '6d6')
        self.valid()

    def test_ordinary_master_keeps_six_and_impossible_stored_ranks_are_rejected(self):
        row = self.poisoned(virtuoso=False)
        self.assertEqual(row['rank'], 6)
        self.valid()
        for forged in (7, 9, 0, 6.0, True):
            with self.subTest(rank=forged):
                self.b.custom_conditions['type_ace_poison']['rank'] = forged
                valid, text = issues(self.e)
                self.assertFalse(valid)
                self.assertIn('Potent Venom rank', text)
        self.b.custom_conditions['type_ace_poison']['rank'] = 6
        self.valid()
        lost, tick = self.poison_tick()
        self.assertEqual(lost, tick + 6)


class DieticianVirtuosoTests(unittest.TestCase):
    """C04-071 (ch04:1916-1919): prerequisite Chef and Expert Intuition; your Pokemon benefit from up to 7 Vitamins."""
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='all')

    def setUp(self):
        self.e = Engine(self.r, seed=419)
        self.owner = self.trainer('virtuoso-chef', intuition=6, virtuoso=True)
        self.p = self.pokemon(self.owner)

    def add(self, spec):
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor, pos=(0, 0), side='party', reason='actual current sheet')
        return actor

    def trainer(self, name, *, intuition, virtuoso):
        extra = {'classes': [VITAMIN.CHEF], 'feats': [VITAMIN.DIETICIAN], 'skills': {'직감': intuition}, 'items': {'타우린': 20}}
        if virtuoso:
            extra.update(edges=[VIRTUOSO], edge_choices={VIRTUOSO: ['직감']})
        return self.add(build_trainer(self.r, name, 20, dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10), extra=extra))

    def pokemon(self, owner, name='브케인'):
        actor = self.add(build_pokemon(self.r, name, 5, moves=[], abilities=[], extra={'trainer_id': owner.entity_id, 'tutor_points': 4}))
        return actor

    def view(self, actor=None):
        return MOVES.vitamin_state(self.r, (actor or self.p).spec)

    def state(self):
        return deepcopy((self.e.rng.getstate(), [a.spec for a in self.e.everyone]))

    def test_virtuoso_intuition_records_ordinary_master_evidence_and_keeps_seven_vitamins_valid(self):
        self.assertEqual(SKILL.rank(self.r, self.owner, '직감')[1:], ('6d6', 6))
        self.assertEqual(SKILL.effective_rank(self.r, self.owner, '직감'), 8)
        ITEMS.register_feats(self.e, self.owner)
        self.assertEqual(self.owner.spec['dietician_acquisition']['intuition_rank'], 6)
        self.assertEqual(self.view()['capacity'], 7)
        valid, text = issues(self.e)
        self.assertTrue(valid, text)
        before = deepcopy(self.p.spec[GRANTS.KEY])
        ITEMS.register_feats(self.e, self.owner)
        self.assertEqual(self.p.spec[GRANTS.KEY], before)
        later = self.pokemon(self.owner, '파이리')
        self.assertEqual(self.view(later)['capacity'], 7)
        attack = self.p.spec['stats']['atk']
        for _ in range(8):
            self.e.use_item(self.owner, '타우린', self.p)
        self.assertEqual((len(self.p.spec['vitamins']), self.p.spec['stats']['atk']), (7, attack + 7))
        valid, text = issues(self.e)
        self.assertTrue(valid, text)

    def test_virtuoso_owner_transfer_and_both_restores_keep_the_ordinary_evidence(self):
        ITEMS.register_feats(self.e, self.owner)
        second = self.trainer('second-virtuoso-chef', intuition=6, virtuoso=True)
        for owner, roster in ((self.owner, [self.p]), (second, [])):
            PARTY.configure(self.e, owner, mode='unlimited', reason='actual full roster', roster=roster)
        self.e.use_item(self.owner, '타우린', self.p)
        self.e.gm.snapshot('virtuoso-dietician')
        PARTY.transfer(self.e, self.owner, target=self.p, new_owner=second, reason='observed voluntary actual ownership transfer', request_id='virtuoso-transfer')
        sources = self.view()['capacity_sources']
        self.assertEqual((len(sources), sources[0]['owner_id'], self.view()['capacity']), (1, second.entity_id, 7))
        self.assertEqual(second.spec['dietician_acquisition']['intuition_rank'], 6)
        valid, text = issues(self.e)
        self.assertTrue(valid, text)
        payload = json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False))
        loaded = CODEC.load_engine(self.r, payload)
        actors = WORLD.actor_index(loaded)
        self.assertEqual(actors[second.entity_id].spec['dietician_acquisition']['intuition_rank'], 6)
        self.assertEqual(MOVES.vitamin_state(loaded.r, actors[self.p.entity_id].spec)['capacity'], 7)
        self.assertTrue(loaded.validate_state()['valid'])
        self.e.gm.restore('virtuoso-dietician', reason='actual rewind before the transfer')
        self.assertEqual(self.view()['capacity_sources'][0]['owner_id'], self.owner.entity_id)
        valid, text = issues(self.e)
        self.assertTrue(valid, text)

    def test_effect_rank_evidence_is_rejected_and_a_failed_registration_changes_nothing(self):
        ITEMS.register_feats(self.e, self.owner)
        for forged in (8, 7, 4):
            with self.subTest(rank=forged):
                self.owner.spec['dietician_acquisition']['intuition_rank'] = forged
                valid, text = issues(self.e)
                self.assertFalse(valid)
                self.assertIn('Dietician acquisition evidence', text)
                before = self.state()
                with self.assertRaisesRegex(ValueError, 'Dietician acquisition evidence'):
                    ITEMS.register_feats(self.e, self.owner)
                self.assertEqual(self.state(), before)
        self.owner.spec['dietician_acquisition']['intuition_rank'] = 6
        valid, text = issues(self.e)
        self.assertTrue(valid, text)
        before = (self.state(), [a.entity_id for a in self.e.everyone])
        with self.assertRaisesRegex(ValueError, 'Expert Intuition'):
            self.trainer('novice-chef', intuition=4, virtuoso=False)
        self.assertEqual((self.state(), [a.entity_id for a in self.e.everyone]), before)


class TerrainTalentVirtuosoTests(unittest.TestCase):
    """C04-094 Deep Diver and Traceur (core-1.05 'equal to your Survival Rank', 'half your Survival Rank')."""
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        SC.definitions(self.rules)

    def world(self, *terrains):
        world = SURVIVAL.scene(self.rules)
        engine, trainer = world['engine'], world['trainer']
        for terrain in terrains:
            SURVIVAL.master(engine, trainer, terrain)
        SURVIVAL.talents(engine, trainer, *terrains[:2])
        SURVIVAL.env(engine, trainer, 'urban')
        add_virtuoso(engine, trainer, '생존')
        self.assertEqual(SKILL.rank(self.rules, trainer, '생존')[1:], ('6d6', 6))
        self.assertEqual(SKILL.effective_rank(self.rules, trainer, '생존'), 8)
        return world

    def test_deep_diver_virtuoso_survival_holds_breath_eight_minutes_through_json_restore(self):
        world = self.world('ocean', 'cave')
        engine, trainer = world['engine'], world['trainer']
        self.assertEqual(SC.breath_seconds(trainer, 'water', engine), 480)
        self.assertEqual(TRAINER.breath_grace(trainer, 'water', engine=engine), 480)
        self.assertEqual(TRAINER.breath_grace(trainer, 'air', engine=engine), 60)
        engine.observe_breathing(trainer, air_available=False, medium='water', reason='GM observed the dive',
                                 timing_policy='grace_boundary')
        self.assertEqual(trainer.spec['_respiration']['grace_seconds'], 480)
        loaded, actors = SURVIVAL.restore(self.rules, engine)
        diver = actors[trainer.entity_id]
        self.assertTrue(loaded.validate_state()['valid'])
        loaded.advance_time(479, [diver])
        self.assertEqual(diver.injuries, 0)
        loaded.advance_time(1, [diver])
        self.assertEqual(diver.injuries, 1)
        self.assertTrue(loaded.validate_state()['valid'])

    def test_traceur_virtuoso_survival_adds_four_evasion_to_the_native_push_only(self):
        world = self.world('urban', 'cave')
        engine, trainer = world['engine'], world['trainer']
        bandit = Combatant(self.rules, SURVIVAL.trainer_spec(self.rules, 'bandit', survival=3, movement={'land': 6, 'power': 4}))
        engine.gm.add_combatant(bandit, pos=(1, 2), side='wild', reason='adjacent opposing trainer')
        engine.gm.set_position(world['partner'], (3, 5), reason='own Pokemon clears the push lane')
        bandit.spec['weight_kg'] = 30
        trainer.spec['weight_kg'] = 30
        SURVIVAL.battle(engine, bandit)
        self.assertEqual(SC.evasion_bonus(engine, trainer, bandit, {'id': SC.PUSH}), 4)
        self.assertEqual(SC.evasion_bonus(engine, trainer, bandit, {'id': SC.TRIP}), 4)
        self.assertEqual(SC.evasion_bonus(engine, trainer, bandit, {'id': 'move/몸통박치기'}), 0)
        loaded, actors = SURVIVAL.restore(self.rules, engine)
        self.assertEqual(SC.evasion_bonus(loaded, actors[trainer.entity_id], actors[bandit.entity_id], {'id': SC.PUSH}), 4)
        need = 4 + trainer.evasion('변화', engine=engine)
        # An ordinary-rank +3 bonus would let this accuracy hit; the effective-rank +4 bonus makes it miss.
        pushed = engine.push(bandit, trainer, challenger_skill='전투', defender_skill='전투', fixed_accuracy=need + 3,
                             challenger_options={'fixed': [3] * 4}, defender_options={'fixed': [2] * 4})
        self.assertFalse(pushed)
        self.assertEqual(trainer.pos, (2, 2))
        self.assertTrue(engine.validate_state()['valid'])


class GlyphVirtuosoTests(unittest.TestCase):
    """supp-fantasy:615-621 (Game of Throhs Glyph): active Glyphs equal to your Occult Education Rank."""
    @classmethod
    def setUpClass(cls):
        cls.fantasy = Rules(str(ROOT), ruleset='fantasy')

    def world(self, *, virtuoso, count):
        self.e = Engine(self.fantasy, 18)
        extra = {'edges': [VIRTUOSO], 'edge_choices': {VIRTUOSO: ['오컬트학']}} if virtuoso else {}
        self.a = Combatant(self.fantasy, dict({'id': 'trainer', 'name': 'trainer', 'kind': 'trainer', 'level': 20,
            'stats': dict(hp=10, atk=10, **{'def': 10}, spa=10, spd=10, spe=10), 'skills': {'오컬트학': 6},
            'moves': ['move/잠재파워'], 'pos': (1, 1)}, **extra))
        self.unown = []
        for n in range(count):
            u = Combatant(self.fantasy, build_pokemon(self.fantasy, '안농', 5, name='source-unown-' + str(n)))
            u.on_field = False
            self.unown.append(u)
        self.e.everyone = self.e.gm.everyone = [self.a, *self.unown]
        WORLD.register_object(self.e, 'wall', location={'kind': 'unknown'}, reason='GM observed physical object')
        self.assertEqual(SKILL.rank(self.fantasy, self.a, '오컬트학')[1:], ('6d6', 6))
        self.assertEqual(SKILL.effective_rank(self.fantasy, self.a, '오컬트학'), 8 if virtuoso else 6)

    def glyph(self, n):
        return dict(id='glyph-' + str(n), kind='glyph', location={'kind': 'abstract', 'place_id': 'wall/north'},
                    creator_id=self.a.entity_id, unown_id=self.unown[n].entity_id, creation_level=20, level=20,
                    hp=20, max_hp=20, status='active', visible=False, channeling=False, flat_surface_id='wall')

    def test_virtuoso_occult_holds_eight_active_glyphs_and_ninth_is_rejected_atomically(self):
        self.world(virtuoso=True, count=9)
        SPECIAL.observe_batch(self.e, [self.glyph(n) for n in range(8)], reason='eight actual established glyphs')
        self.assertEqual(SPECIAL.view(self.e, 'glyph-7')['state_view']['active_glyph_limit'], 8)
        before = deepcopy(self.e._physical_objects)
        with self.assertRaisesRegex(ValueError, 'active glyphs exceed creator Occult rank'):
            SPECIAL.observe(self.e, self.glyph(8), reason='ninth active glyph exceeds the effective rank')
        self.assertEqual(self.e._physical_objects, before)
        self.assertTrue(WORLD.validate_world(self.e)['valid'])
        self.e.gm.snapshot('eight-glyphs')
        row = self.glyph(0)
        row['status'] = 'deactivated'
        SPECIAL.observe(self.e, row, reason='intentional deactivation frees one slot')
        SPECIAL.observe(self.e, self.glyph(8), reason='a replacement ninth identity fits the eight-glyph cap')
        self.e.gm.restore('eight-glyphs', reason='actual rewind to the eight active glyphs')
        active = [x for x in self.e._physical_objects.values() if x.get('kind') == 'glyph' and x.get('status') == 'active']
        self.assertEqual(len(active), 8)
        self.assertNotIn('glyph-8', self.e._physical_objects)
        self.assertTrue(WORLD.validate_world(self.e)['valid'])

    def test_ordinary_master_occult_still_caps_active_glyphs_at_six(self):
        self.world(virtuoso=False, count=7)
        SPECIAL.observe_batch(self.e, [self.glyph(n) for n in range(6)], reason='six actual established glyphs')
        self.assertEqual(SPECIAL.view(self.e, 'glyph-5')['state_view']['active_glyph_limit'], 6)
        before = deepcopy(self.e._physical_objects)
        with self.assertRaisesRegex(ValueError, 'active glyphs exceed creator Occult rank'):
            SPECIAL.observe(self.e, self.glyph(6), reason='seventh active glyph exceeds the ordinary Master rank')
        self.assertEqual(self.e._physical_objects, before)


if __name__ == '__main__':
    unittest.main()
