"""Audit C05-143/C05-146, C05-027 and C06-028 repairs on the native owners.

Declared eggs keep their original producer receipt and newborns take their Ability
from the child species' own pools (ch05:111,649,656,660); the optional 2d6 Nature
lookup names the rolled chapter-table cell (ch05:89-101); a trainer's pre-roll AP
bonus reaches only that trainer or a Pokemon it currently owns (ch06:84-85, Core
1.05 p.221 "your Pokemon's Accuracy or Skill Checks").
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json, random, sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_foundation_egg_creation as EGG
import action_points as AP
import builder as B
import creation_egg as E
import downtime as D
import growth_milestones as MILESTONES
from native_scenario_fixture import assert_rejected_unchanged
import nature_state as NATURE
import pokemon_party as PARTY
import world_entities as W
from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
from state_codec import dump_engine, load_engine

STATS = ('hp', 'atk', 'def', 'spa', 'spd', 'spe')
GRID = ['평안 귀여운 산만 위풍당당 과감 끈기', '절박 노력 외로움 고집 개구쟁이 용감',
        '냉혹 대담 온순 장난꾸러기 촐랑 무사태평', '호기심 조심 의젓 수줍음 덜렁 냉정',
        '낭만적 차분 얌전 신중 변덕 건방', '활발 겁쟁이 성급 명랑 천진난만 성실']


def restored(rules, engine):
    return load_engine(rules, json.loads(json.dumps(dump_engine(engine), ensure_ascii=False)))


class AuditEggEvidenceTests(unittest.TestCase):
    """C05-143 producer receipt and C05-146 newborn Ability on the declared egg owner."""
    setUpClass = classmethod(EGG.EggTests.setUpClass.__func__)
    add = EGG.EggTests.add
    policy = EGG.EggTests.policy
    create = EGG.EggTests.create
    choices = EGG.EggTests.choices
    hatch = EGG.EggTests.hatch
    snap = EGG.EggTests.snap

    def setUp(self):
        EGG.EggTests.setUp(self)

    def receiver(self):
        return self.add(build_trainer(self.r, 'receiver', 20, dict.fromkeys(STATS, 10),
                                      skills={'명령': 3}, extra={'edges': []}))

    def selected(self, abilities):
        value = self.choices()
        value['abilities'] = list(abilities)
        return value

    def assert_rejected_unchanged(self, row, abilities, pattern):
        before = self.snap()
        with self.assertRaisesRegex(ValueError, pattern):
            self.hatch(row, choices=self.selected(abilities))
        self.assertEqual(before, self.snap())
        self.assertFalse(next(egg for egg in self.a.spec['eggs'] if egg['entity_id'] == row['entity_id'])['hatched'])

    def test_declared_egg_keeps_original_producer_receipt_through_transfer_restore_and_hatch(self):
        row = self.create()
        receipt = deepcopy(self.a.spec[E.RECORDS]['egg'])
        self.assertEqual(receipt['egg_entity_id'], row['entity_id'])
        other = self.receiver()
        self.e.gm.transfer_egg(self.a, other, row['entity_id'], reason='real egg gift', request_id='gift')
        self.assertTrue(self.e.validate_state()['valid'])
        loaded = restored(self.r, self.e)
        actors = W.actor_index(loaded)
        self.assertEqual(actors[self.a.entity_id].spec[E.RECORDS]['egg'], receipt)
        child = loaded.hatch_declared_egg(actors[other.entity_id], row['entity_id'], name='gift child', ready=True,
                                          reason='actual recipient observes readiness', choices=self.choices())['pokemon']
        self.assertEqual(child.spec['trainer_id'], other.entity_id)
        self.assertEqual(actors[self.a.entity_id].spec[E.RECORDS]['egg'], receipt)
        self.assertTrue(loaded.validate_state()['valid'])
        self.assertTrue(restored(self.r, loaded).validate_state()['valid'])
        checkpoint = loaded.gm.snapshot()
        loaded.gm.restore(checkpoint)
        actors = W.actor_index(loaded)
        before = dump_engine(loaded)
        replay = loaded.create_declared_egg(actors[self.a.entity_id],
            [actors[parent.entity_id] for parent in self.parents], self.policy(),
            request_id='egg', compatible=True, species='pokemon/이상해씨',
            inheritance_moves=['move/뿌리박기'], reason='actual observed breeding')
        self.assertEqual(replay['entity_id'], row['entity_id'])
        self.assertEqual(replay['pokemon_id'], child.entity_id)
        self.assertEqual(replay['owner_id'], other.entity_id)
        self.assertEqual(before, dump_engine(loaded))

    def test_missing_producer_receipt_rejects_native_state_json_restore_and_hatch(self):
        row = self.create()
        self.assertTrue(self.e.validate_state()['valid'])
        original = deepcopy(self.a.spec[E.RECORDS].pop('egg'))
        self.assertEqual(original['egg_entity_id'], row['entity_id'])
        self.assertFalse(self.e.validate_state()['valid'])
        with self.assertRaises(ValueError):
            restored(self.r, self.e)  # the invalid state is neither saved nor restored
        before, roster = deepcopy(self.a.spec), list(self.e.gm.everyone)
        with self.assertRaises(ValueError):
            self.hatch(row)
        self.assertEqual(before, self.a.spec)
        self.assertEqual(roster, self.e.gm.everyone)
        self.assertFalse(self.a.spec['eggs'][-1]['hatched'])
        self.a.spec[E.RECORDS]['egg'] = original
        self.assertTrue(self.e.validate_state()['valid'])
        self.assertEqual(self.hatch(row)['pokemon'].level, 1)

    def test_changed_or_malformed_producer_receipt_is_rejected(self):
        self.create()
        for field, value in (('egg_entity_id', 'egg/wrong'), ('intent', '0' * 64)):
            with self.subTest(field=field):
                original = deepcopy(self.a.spec[E.RECORDS]['egg'])
                self.a.spec[E.RECORDS]['egg'][field] = value
                self.assertFalse(self.e.validate_state()['valid'])
                self.a.spec[E.RECORDS]['egg'] = original
        self.a.spec[E.RECORDS]['egg'] = ['not', 'a', 'receipt']
        self.assertFalse(self.e.validate_state()['valid'])

    def test_gm_observed_egg_without_declared_contract_needs_no_producer_receipt(self):
        row = self.e.pokemon_activity(self.a, 'observe_egg', egg_id='gm-egg', reason='GM established an egg',
                                      parents=[p.entity_id for p in self.parents])
        self.assertNotIn(E.CONTRACT, row)
        self.assertNotIn('gm-egg', self.a.spec.get(E.RECORDS, {}))
        self.assertTrue(self.e.validate_state()['valid'])
        self.assertTrue(restored(self.r, self.e).validate_state()['valid'])

    def test_newborn_takes_one_ability_from_the_child_species_basic_list(self):
        basic = self.r.learnsets['이상해씨']['abilities']['기본 특성']
        self.assertIn('엽록소', basic)
        self.assertNotIn('건조피부', basic)
        row = self.create()
        for abilities, pattern in ((['건조피부'], 'outside'), (['자신감'], 'outside'),
                                   ([], 'one species Basic'), (['심록', '엽록소'], 'one species Basic')):
            with self.subTest(abilities=abilities):
                self.assert_rejected_unchanged(row, abilities, pattern)
        child = self.hatch(row, choices=self.selected(['엽록소']))['pokemon']
        self.assertEqual(child.abilities, ['엽록소'])
        self.assertTrue(self.e.validate_state()['valid'])
        loaded = restored(self.r, self.e)
        self.assertEqual(W.actor_index(loaded)[child.entity_id].abilities, ['엽록소'])
        self.assertTrue(loaded.validate_state()['valid'])

    def test_reached_level_slot_never_admits_outside_species_or_pool_abilities(self):
        # Retained historical ID: the ordinary hatch event has no optional level slots.
        for level in (1, 20, 40):
            with self.subTest(level=level):
                value = self.policy()
                value['hatch']['level'] = level
                row = self.create(value, request_id='birth-' + str(level))
                for abilities in ([], ['건조피부'], ['자신감'], ['심록', '엽록소'], ['심록', '자신감', '절제력']):
                    with self.subTest(abilities=abilities):
                        assert_rejected_unchanged(self.e,
                            lambda: self.hatch(row, choices=self.selected(abilities)),
                            reason_pattern='outside|one species Basic')
                child = self.hatch(row, choices=self.selected(['심록']))['pokemon']
                self.assertEqual((child.level, child.abilities), (level, ['심록']))
                self.assertNotIn('ability:20', child.spec.get(MILESTONES.KEY, {}))
                self.assertNotIn('ability:40', child.spec.get(MILESTONES.KEY, {}))
                if level >= 20:
                    assert_rejected_unchanged(self.e,
                        lambda: self.e.choose_growth_ability(child, 20, '엽록소', reason='unearned historical level'),
                        reason_pattern='recorded ability milestone right')
                if level == 40:
                    assert_rejected_unchanged(self.e,
                        lambda: self.e.choose_growth_ability(child, 40, '엽록소', reason='unearned historical level'),
                        reason_pattern='recorded ability milestone right')
        loaded = restored(self.r, self.e)
        self.assertTrue(loaded.validate_state()['valid'])

    def test_real_level_19_to_20_and_39_to_40_offer_one_right_and_public_choice_replays_once(self):
        for level in (19, 39):
            with self.subTest(level=level):
                value = self.policy()
                value['hatch']['level'] = level
                child = self.hatch(self.create(value, request_id='grow-' + str(level)))['pokemon']
                stage = level + 1
                key = 'ability:' + str(stage)
                self.assertNotIn(key, child.spec.get(MILESTONES.KEY, {}))
                D.gain_exp_combatant(self.e, child, 'to next level')
                self.assertEqual(child.level, stage)
                offered = child.spec[MILESTONES.KEY][key]
                self.assertEqual(offered['offered']['stage']['kind'], 'level')
                self.assertIsNone(offered['selection'])
                self.assertEqual(child.abilities, ['심록'])
                choice = offered['offered']['options'][0]
                loaded = restored(self.r, self.e)
                actual = W.actor_index(loaded)[child.entity_id]
                result = loaded.choose_growth_ability(actual, stage, choice, reason='actual attained level choice')
                self.assertFalse(result['replayed'])
                self.assertEqual(actual.abilities, ['심록', choice])
                before = dump_engine(loaded)
                replay = loaded.choose_growth_ability(actual, stage, choice, reason='actual attained level choice')
                self.assertTrue(replay['replayed'])
                self.assertEqual(before, dump_engine(loaded))
                again = restored(self.r, loaded)
                self.assertEqual(W.actor_index(again)[child.entity_id].abilities, ['심록', choice])

    def test_high_level_import_preserves_explicit_abilities_and_does_not_replay_milestones(self):
        for level in (20, 40):
            with self.subTest(level=level):
                child = self.add(build_pokemon(self.r, '이상해씨', level, moves=[],
                    abilities=['심록', '건조피부'], extra={'trainer_id': self.a.entity_id}))
                self.assertEqual(child.abilities, ['심록', '건조피부'])
                self.assertNotIn('ability:20', child.spec.get(MILESTONES.KEY, {}))
                self.assertNotIn('ability:40', child.spec.get(MILESTONES.KEY, {}))
                pending = self.e.gm.snapshot()
                self.e.gm.restore(pending)
                loaded = restored(self.r, self.e)
                self.assertEqual(W.actor_index(loaded)[child.entity_id].abilities, ['심록', '건조피부'])

    def test_missing_or_malformed_receipt_container_and_entry_reject_before_birth_mutation(self):
        row = self.create()
        original = deepcopy(self.a.spec[E.RECORDS])
        variants = [None, [], {}, {'egg': None}, {'egg': []}, {'egg': {}},
                    {'egg': {'intent': original['egg']['intent']}},
                    {'egg': {'egg_entity_id': row['entity_id']}}]
        for records in variants:
            with self.subTest(records=records):
                self.a.spec[E.RECORDS] = deepcopy(records)
                before = (deepcopy(self.a.spec), tuple(self.e.gm.everyone), self.e.rng.getstate(), list(self.e.log_lines))
                with self.assertRaisesRegex(ValueError, 'producer replay receipt'):
                    E.validate_binding(self.e, row)
                with self.assertRaises(ValueError):
                    self.hatch(row)
                self.assertEqual(before, (self.a.spec, tuple(self.e.gm.everyone), self.e.rng.getstate(), self.e.log_lines))
                self.a.spec[E.RECORDS] = deepcopy(original)
        # Exercise the decoder, independently of the save-time rejection of an invalid world.
        encoded = dump_engine(self.e)
        owner_spec = next(node for node in encoded['nodes'].values()
                          if node['kind'] == 'dict' and any(pair[0] == E.RECORDS for pair in node['items']))
        owner_spec['items'] = [pair for pair in owner_spec['items'] if pair[0] != E.RECORDS]
        with self.assertRaises(ValueError):
            load_engine(self.r, json.loads(json.dumps(encoded)))
        self.assertTrue(self.e.validate_state()['valid'])

    def test_pre_repair_newborn_with_outside_ability_is_not_retroactively_invalid(self):
        row = self.create()
        native = sys.modules['creation_egg']  # the module object the Engine call resolves at hatch time
        with patch.object(native, 'birth_abilities', lambda *args, **kwargs: None):
            child = self.hatch(row, choices=self.selected(['건조피부']))['pokemon']
        self.assertEqual(child.spec['abilities'], ['건조피부'])
        self.assertTrue(self.e.validate_state()['valid'])
        self.assertTrue(restored(self.r, self.e).validate_state()['valid'])


class AuditNatureDiceLabelTests(unittest.TestCase):
    """C05-027: the optional 2d6 result is the chapter-table cell; numbers and saved spellings unchanged."""

    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='core')

    def test_every_fixed_cell_returns_its_chapter_table_label_without_consuming_rng(self):
        rng = random.Random(27)
        before = rng.getstate()
        for up, row in enumerate(GRID, 1):
            for down, label in enumerate(row.split(), 1):
                with self.subTest(up=up, down=down):
                    self.assertEqual(NATURE.from_dice(self.r, rng, raise_die=up, lower_die=down), label)
                    view = NATURE.describe(self.r, label)
                    self.assertEqual((view['up_stat'], view['down_stat']), (NATURE.STATS[up - 1], NATURE.STATS[down - 1]))
        self.assertEqual(rng.getstate(), before)

    def test_random_dice_consume_the_same_two_draws_and_name_the_rolled_cell(self):
        for seed in range(60):
            rng, control = random.Random(seed), random.Random(seed)
            up, down = control.randint(1, 6), control.randint(1, 6)
            self.assertEqual(NATURE.from_dice(self.r, rng), GRID[up - 1].split()[down - 1])
            self.assertEqual(rng.getstate(), control.getstate())
        rng, control = random.Random(5), random.Random(5)
        down = control.randint(1, 6)
        self.assertEqual(NATURE.from_dice(self.r, rng, raise_die=2), GRID[1].split()[down - 1])
        self.assertEqual(rng.getstate(), control.getstate())

    def test_three_relabelled_cells_keep_catalog_numbers_flavors_and_explicit_spelling(self):
        base = {'hp': 4, 'atk': 5, 'def': 4, 'spa': 6, 'spd': 5, 'spe': 7}
        for (up, down), label, catalog in (((2, 1), '절박', '무모'), ((5, 1), '낭만적', '낭만'), ((6, 1), '활발', '소심')):
            with self.subTest(label=label):
                self.assertEqual(NATURE.from_dice(self.r, random.Random(0), raise_die=up, lower_die=down), label)
                table, explicit = NATURE.describe(self.r, label), NATURE.describe(self.r, catalog)
                self.assertEqual((table['name'], table['catalog_name']), (label, catalog))
                self.assertEqual((explicit['name'], explicit['catalog_name']), (catalog, catalog))
                for key in ('up_stat', 'down_stat', 'neutral', 'likes', 'dislikes'):
                    self.assertEqual(table[key], explicit[key])
                self.assertEqual(B.nature_base(base, label, self.r), B.nature_base(base, catalog, self.r))

    def test_actor_keeps_rolled_or_catalog_spelling_through_gm_and_json_restore(self):
        e = Engine(self.r)
        rolled = NATURE.from_dice(self.r, random.Random(0), raise_die=2, lower_die=1)
        actors = []
        for name in (rolled, '무모'):
            c = Combatant(self.r, build_pokemon(self.r, '파이리', 5, nature=name, abilities=['맹화']))
            e.gm.add_combatant(c, reason='GM imports a Pokemon with this Nature spelling')
            actors.append(c)
        self.assertEqual([c.spec['nature'] for c in actors], ['절박', '무모'])
        self.assertEqual(actors[0].stats, actors[1].stats)
        views = [e.gm.describe_actor(c)['nature_state'] for c in actors]
        self.assertEqual([v['name'] for v in views], ['절박', '무모'])
        e.gm.snapshot('nature')
        e.gm.restore('nature')
        loaded = Engine.import_state(self.r, e.export_state())
        for c, view in zip(actors, views):
            again = next(a for a in loaded.everyone if a.entity_id == c.entity_id)
            self.assertEqual(again.spec['nature'], c.spec['nature'])
            self.assertEqual(loaded.gm.describe_actor(again)['nature_state'], view)


class AuditOwnPokemonApRollTests(unittest.TestCase):
    """C06-028: trainer self or that trainer's current Pokemon; others reject before any cost."""

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def setUp(self):
        self.e = Engine(self.rules, seed=419)
        self.payer, self.other = self.trainer('payer'), self.trainer('other')
        self.own = self.pokemon('own-pokemon', self.payer)
        self.foreign = self.pokemon('foreign-pokemon', self.other)
        self.unowned = self.pokemon('unowned-pokemon', None)
        self.e.gm.everyone = [self.payer, self.other, self.own, self.foreign, self.unowned]
        self.e.everyone = self.e.gm.everyone

    def trainer(self, identity):
        return Combatant(self.rules, {'id': identity, 'name': identity, 'kind': 'trainer', 'level': 20,
                                      'stats': dict.fromkeys(STATS, 5) | {'hp': 10}, 'skills': {'athletics': '초보'}})

    def pokemon(self, identity, owner):
        spec = {'id': identity, 'name': identity, 'kind': 'pokemon', 'level': 20,
                'stats': dict.fromkeys(STATS, 5) | {'hp': 10}, 'skills': {'athletics': '초보'}}
        if owner is not None:
            spec['trainer_id'] = owner.entity_id
        return Combatant(self.rules, spec)

    def state(self, engine=None):
        return json.dumps(dump_engine(engine or self.e), sort_keys=True, ensure_ascii=False)

    def test_trainer_self_and_own_pokemon_skill_and_accuracy_receive_one_bonus(self):
        for beneficiary, kind in ((self.own, 'skill'), (self.own, 'accuracy'), (self.payer, 'skill'), (self.payer, 'accuracy')):
            with self.subTest(beneficiary=beneficiary.entity_id, kind=kind):
                roll_id = beneficiary.entity_id + ':' + kind
                available = AP.available(self.payer)
                self.assertEqual(self.e.boost_roll(self.payer, beneficiary, roll_id=roll_id, kind=kind), 1)
                self.assertEqual(AP.available(self.payer), available - 1)
                with self.assertRaisesRegex(ValueError, 'already'):
                    self.e.boost_roll(self.payer, beneficiary, roll_id=roll_id, kind=kind)
                if kind == 'skill':
                    out = self.e.common_action(beneficiary, 'athletics', 1, mode='skill', fixed=[1, 1, 1], roll_id=roll_id)
                    self.assertEqual(out.check.total, 4)
                else:
                    target = self.other if beneficiary is not self.other else self.payer
                    self.assertTrue(self.e.accuracy_check(beneficiary, target, self.rules.move('move/블록'),
                                                          fixed_roll=2, roll_id=roll_id)[0])
                self.assertEqual(self.e._ap_rolls[roll_id]['state'], 'resolved')
                self.assertEqual(AP.available(self.payer), available - 1)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_other_trainers_unowned_and_unregistered_pokemon_reject_before_cost(self):
        stray = self.pokemon('stray-pokemon', self.payer)
        for beneficiary in (self.foreign, self.unowned, stray):
            for kind in ('skill', 'accuracy'):
                with self.subTest(beneficiary=beneficiary.entity_id, kind=kind):
                    roll_id = 'rejected:' + beneficiary.entity_id + ':' + kind
                    before, available = self.state(), AP.available(self.payer)
                    with self.assertRaises(ValueError):
                        self.e.boost_roll(self.payer, beneficiary, roll_id=roll_id, kind=kind)
                    self.assertEqual(AP.available(self.payer), available)
                    self.assertNotIn(roll_id, self.e._ap_rolls)
                    self.assertEqual(before, self.state())
        out = self.e.common_action(self.foreign, 'athletics', 1, mode='skill', fixed=[1, 1, 1],
                                   roll_id='rejected:foreign-pokemon:skill')
        self.assertEqual(out.check.total, 3)
        self.assertFalse(self.e.accuracy_check(self.unowned, self.other, self.rules.move('move/블록'),
                                               fixed_roll=2, roll_id='rejected:unowned-pokemon:accuracy')[0])

    def test_former_owner_loses_and_new_owner_gains_the_bonus_after_actual_transfer(self):
        e = Engine(self.rules, seed=419)
        def add(spec):
            actor = Combatant(self.rules, spec)
            e.gm.add_combatant(actor, reason='actual AP ownership participant')
            return actor
        old = add(build_trainer(self.rules, 'former owner', 20, dict.fromkeys(STATS, 10), abilities=[]))
        new = add(build_trainer(self.rules, 'new owner', 20, dict.fromkeys(STATS, 10), abilities=[]))
        pet = add(build_pokemon(self.rules, '파이리', 20, abilities=['맹화'], extra={'trainer_id': old.entity_id}))
        self.assertEqual(e.boost_roll(old, pet, roll_id='before-transfer', kind='skill'), 1)
        for owner, roster in ((old, [pet]), (new, [])):
            PARTY.configure(e, owner, mode='standard', roster=roster,
                            storage={'kind': 'center', 'id': 'ap-center-' + owner.entity_id},
                            reason='actual registered ownership and storage')
        W.transfer_owner(e, pet, old, new, reason='actual later ownership transfer', request_id='ap/transfer')
        self.assertEqual(pet.spec['trainer_id'], new.entity_id)
        before, available = self.state(e), AP.available(old)
        with self.assertRaises(ValueError):
            e.boost_roll(old, pet, roll_id='former-owner', kind='skill')
        self.assertEqual((AP.available(old), self.state(e)), (available, before))
        self.assertEqual(e.boost_roll(new, pet, roll_id='new-owner', kind='accuracy'), 1)

    def test_prepared_own_pokemon_bonus_survives_json_restore_once_and_restored_owner_is_checked(self):
        self.assertEqual(self.e.boost_roll(self.payer, self.own, roll_id='saved-own', kind='skill'), 1)
        loaded = restored(self.rules, self.e)
        actors = W.actor_index(loaded)
        payer, own, foreign = actors['payer'], actors['own-pokemon'], actors['foreign-pokemon']
        self.assertIs(loaded._ap_rolls['saved-own']['payer'], payer)
        self.assertIs(loaded._ap_rolls['saved-own']['beneficiary'], own)
        available = AP.available(payer)
        out = loaded.common_action(own, 'athletics', 1, mode='skill', fixed=[1, 1, 1], roll_id='saved-own')
        self.assertEqual(out.check.total, 4)
        self.assertEqual(loaded._ap_rolls['saved-own']['state'], 'resolved')
        before = self.state(loaded)
        with self.assertRaises(ValueError):
            loaded.boost_roll(payer, foreign, roll_id='restored-foreign', kind='skill')
        self.assertEqual((AP.available(payer), self.state(loaded)), (available, before))
        self.assertTrue(loaded.validate_state()['valid'])

    def transfer_world(self):
        e = Engine(self.rules, seed=419)
        def add(spec):
            actor = Combatant(self.rules, spec)
            e.gm.add_combatant(actor, reason='actual prepaid AP transfer participant')
            return actor
        old = add(build_trainer(self.rules, 'old', 20, dict.fromkeys(STATS, 5), abilities=[]))
        new = add(build_trainer(self.rules, 'new', 20, dict.fromkeys(STATS, 5), abilities=[]))
        pet = add(build_pokemon(self.rules, '파이리', 20, abilities=['맹화'], moves=[],
            extra={'trainer_id': old.entity_id, 'skills': {'athletics': '초보'}}))
        for owner, roster in ((old, [pet]), (new, [])):
            PARTY.configure(e, owner, mode='standard', roster=roster,
                storage={'kind': 'center', 'id': 'prepaid-center-' + owner.entity_id},
                reason='actual registered ownership and storage')
        return e, old, new, pet

    def test_prepaid_skill_and_accuracy_survive_actual_transfer_both_restores_and_charge_once(self):
        e, old, new, pet = self.transfer_world()
        available = AP.available(old)
        for kind in ('skill', 'accuracy'):
            self.assertEqual(e.boost_roll(old, pet, roll_id='prepaid-' + kind, kind=kind), 1)
        self.assertEqual(AP.available(old), available - 2)
        W.transfer_owner(e, pet, old, new, reason='transfer after valid prepayment', request_id='prepaid-gift')
        self.assertEqual(pet.spec['trainer_id'], new.entity_id)
        self.assertEqual(AP.available(old), available - 2)
        e.gm.send_out(pet, reason='new owner sends out the prepaid beneficiary')
        checkpoint = e.gm.snapshot()
        e.gm.restore(checkpoint)
        loaded = restored(self.rules, e)
        actors = W.actor_index(loaded)
        old, new, pet = (actors[actor.entity_id] for actor in (old, new, pet))
        self.assertEqual(pet.spec['trainer_id'], new.entity_id)
        for kind in ('skill', 'accuracy'):
            assert_rejected_unchanged(loaded,
                lambda: loaded.boost_roll(old, pet, roll_id='old-after-' + kind, kind=kind),
                reason_pattern='own current Pokemon')
            assert_rejected_unchanged(loaded,
                lambda: loaded.boost_roll(new, pet, roll_id='prepaid-' + kind, kind=kind),
                reason_pattern='already')
        before_new = AP.available(new)
        out = loaded.common_action(pet, 'athletics', 1, mode='skill', fixed=[1, 1, 1], roll_id='prepaid-skill')
        self.assertEqual(out.check.total, 4)
        self.assertTrue(loaded.accuracy_check(pet, new, self.rules.move('move/블록'),
            fixed_roll=2, roll_id='prepaid-accuracy')[0])
        self.assertEqual((AP.available(old), AP.available(new)), (available - 2, before_new))
        self.assertEqual([loaded._ap_rolls['prepaid-' + kind]['state'] for kind in ('skill', 'accuracy')],
                         ['resolved', 'resolved'])
        assert_rejected_unchanged(loaded,
            lambda: loaded.common_action(pet, 'athletics', 1, mode='skill', fixed=[1, 1, 1], roll_id='prepaid-skill'),
            reason_pattern='resolved|expired')
        assert_rejected_unchanged(loaded,
            lambda: loaded.accuracy_check(pet, new, self.rules.move('move/블록'), fixed_roll=2, roll_id='prepaid-accuracy'),
            reason_pattern='resolved|expired')
        again = restored(self.rules, loaded)
        self.assertEqual(again._ap_rolls['prepaid-skill']['state'], 'resolved')
        self.assertEqual(again._ap_rolls['prepaid-accuracy']['state'], 'resolved')

    def test_transferred_prepaid_bonus_expires_at_scene_end_without_reuse(self):
        e, old, new, pet = self.transfer_world()
        e.boost_roll(old, pet, roll_id='expires-after-transfer', kind='skill')
        W.transfer_owner(e, pet, old, new, reason='transfer before expiry', request_id='expiry-gift')
        e.end_scene()
        self.assertEqual(e._ap_rolls['expires-after-transfer']['state'], 'expired')
        # Scene AP replenishment is its own owner; expired roll identities stay unusable.
        loaded = restored(self.rules, e)
        actors = W.actor_index(loaded)
        old, new, pet = (actors[actor.entity_id] for actor in (old, new, pet))
        assert_rejected_unchanged(loaded,
            lambda: loaded.boost_roll(new, pet, roll_id='expires-after-transfer', kind='skill'),
            reason_pattern='already')
        assert_rejected_unchanged(loaded,
            lambda: loaded.common_action(pet, 'athletics', 1, mode='skill', fixed=[1, 1, 1], roll_id='expires-after-transfer'),
            reason_pattern='resolved|expired')


if __name__ == '__main__':
    unittest.main()
