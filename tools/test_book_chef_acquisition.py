"""Chef class template: actual static acquisition, Culinary Appreciation lesson and Dietician link."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from native_scenario_fixture import assert_rejected_unchanged
import book_chef_fixture as FIX
import ability_transitions as ABILITIES
import acquired_features as ACQUIRED
import chef_cooking as CHEF
import feature_ability_lessons as LESSONS
import food_effects as FOOD
import items as I
import move_state as MOVE_STATE
import state_codec as CODEC
import trainer_feature_acquisition as ACQUIRE
import world_entities as W


class ChefAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')
        cls.core = Rules(ROOT, ruleset='core')

    def setUp(self):
        for rules in (self.rules, self.core):
            previous = rules.rulings
            rules.rulings = deepcopy(previous)
            self.addCleanup(setattr, rules, 'rulings', previous)
            # Lazy policy caches are part of the Rules fingerprint; warm them before atomic comparisons.
            LESSONS._policy(rules)
            FOOD.buff_policy(rules)
            CHEF.definitions(rules)
            try:
                ABILITIES.ability_id(rules, 'ability/먹보-playtest')
            except ValueError:
                pass

    def rejected(self, engine, operation, pattern):
        return assert_rejected_unchanged(engine, operation, reason_pattern=pattern)

    def lesson(self, engine, teacher, pupil, **changes):
        options = {'target': pupil, 'feature': CHEF.APPRECIATION, 'ability': 'ability/먹보-playtest', 'seconds': 600,
                   'reason': 'GM observed the completed Extended lesson'}
        options.update(changes)
        return engine.pokemon_activity(teacher, 'teach_feature_ability', **options)

    def test_template_binds_seven_definitions_to_sources_and_class_acquisition_grants_no_follower(self):
        data = CHEF.definitions(self.rules)
        lines = (ROOT / 'input/ch04-trainer-classes.md').read_text(encoding='utf-8').splitlines()
        self.assertEqual(hashlib.sha256((ROOT / 'input/ch04-trainer-classes.md').read_bytes()).hexdigest(), data['source_sha256'])
        expected = {CHEF.HITS: (1887, 1891), CHEF.APPRECIATION: (1893, 1897), CHEF.ACCENTUATED: (1899, 1908),
                    CHEF.AFTERTASTE: (1910, 1914), CHEF.DIETICIAN: (1916, 1919), CHEF.DUMPLINGS: (1921, 1926)}
        self.assertEqual({uid: tuple(row['span']) for uid, row in data['features'].items()}, expected)
        for uid, (start, end) in expected.items():
            excerpt = '\n'.join(lines[start - 1:end])
            self.assertEqual(hashlib.sha256(excerpt.encode('utf-8')).hexdigest(), data['features'][uid]['excerpt_sha256'])
            self.assertEqual(self.rules.selection.units[uid]['source']['lines'], data['features'][uid]['catalog_span'])
            self.assertIn(uid, ACQUIRE.STATIC_FEATURES)
        self.assertEqual(ACQUIRE.STATIC_FEATURES[CHEF.CLASS]['span'], [1884, 1884])
        self.assertEqual(set(data['recipes']), {CHEF.TASTY, CHEF.HEARTY, CHEF.PRESERVES, CHEF.LEFTOVERS, CHEF.BAIT, CHEF.VITAMINS, CHEF.MEAL_PLANNER})
        self.assertEqual(data['taste_bonuses']['짠맛'], {'kind': 'temporary_hp', 'value': 5, 'stack': True})
        self.assertEqual(data['taste_bonuses']['단맛'], {'kind': 'initiative', 'value': 5})
        world = FIX.scene(self.rules, feats=(CHEF.CLASS,))
        chef = world['chef']
        self.assertEqual(chef.spec['feats'], [CHEF.CLASS])
        self.assertEqual(ACQUIRED.owned_rule_count(chef, CHEF.CLASS), 1)
        for uid in expected:
            self.assertEqual(ACQUIRED.owned_rule_count(chef, uid), 0)
        self.assertEqual(CHEF.chef_feature_count(chef), 1)
        self.assertTrue(world['engine'].validate_state()['valid'])

    def test_class_requires_basic_cooking_edge_and_novice_intuition_before_any_receipt(self):
        engine = Engine(self.rules, seed=3)
        trainer = Combatant(self.rules, FIX.trainer_spec(self.rules, 'novice', intuition=2, edges=()))
        engine.gm.add_combatant(trainer, pos=(0, 0), side='party', reason='trainer without the printed prerequisites')
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, CHEF.CLASS), 'acquired feature required')
        engine.gm.set_skill(trainer, '직감', 3, reason='actual Novice Intuition')
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, CHEF.CLASS), 'acquired feature required')
        trainer.spec['edges'] = ['edge/기본-요리']
        receipt = FIX.acquire(engine, trainer, CHEF.CLASS)
        self.assertEqual((receipt['status'], receipt['snapshot']), ('acquired', {'parent': 'edge/기본-요리', 'intuition': 3}))
        self.assertEqual(receipt['qualification']['status'], 'qualified')
        self.assertIn(CHEF.CLASS, trainer.spec['feats'])
        self.rejected(engine, lambda: ACQUIRE.acquire_static(engine, trainer, CHEF.CLASS, acquisition_request_id='second'), 'already acquired')
        self.assertTrue(engine.validate_state()['valid'])

    def test_feature_prerequisites_use_parent_receipts_intuition_ranks_and_four_chef_features(self):
        world = FIX.scene(self.rules, feats=(), intuition=3)
        engine, chef = world['engine'], world['chef']
        self.rejected(engine, lambda: FIX.acquire(engine, chef, CHEF.HITS), 'Chef prerequisite required')
        FIX.acquire(engine, chef, CHEF.CLASS)
        self.assertEqual(FIX.acquire(engine, chef, CHEF.HITS)['snapshot']['parents'], {CHEF.CLASS: 'chef/' + chef.entity_id + '/' + CHEF.CLASS})
        self.rejected(engine, lambda: FIX.acquire(engine, chef, CHEF.ACCENTUATED), 'Intuition rank')
        self.rejected(engine, lambda: FIX.acquire(engine, chef, CHEF.AFTERTASTE), 'Chef prerequisite required')
        engine.gm.set_skill(chef, '직감', 4, reason='actual Adept Intuition')
        FIX.acquire(engine, chef, CHEF.ACCENTUATED)
        FIX.acquire(engine, chef, CHEF.AFTERTASTE)
        self.rejected(engine, lambda: FIX.acquire(engine, chef, CHEF.DIETICIAN), 'Intuition rank')
        engine.gm.set_skill(chef, '직감', 5, reason='actual Expert Intuition')
        self.rejected(engine, lambda: FIX.acquire(engine, chef, CHEF.DUMPLINGS), 'Intuition rank')
        engine.gm.set_skill(chef, '직감', 6, reason='actual Master Intuition')
        self.assertEqual(CHEF.chef_feature_count(chef), 4)
        receipt = FIX.acquire(engine, chef, CHEF.DUMPLINGS)
        self.assertEqual(set(receipt['snapshot']['chef_features']), {CHEF.CLASS, CHEF.HITS, CHEF.ACCENTUATED, CHEF.AFTERTASTE})
        other = Combatant(self.rules, FIX.trainer_spec(self.rules, 'three', intuition=6))
        engine.gm.add_combatant(other, pos=(3, 3), side='party', reason='trainer with three Chef Features')
        for uid in (CHEF.CLASS, CHEF.HITS, CHEF.ACCENTUATED):
            FIX.acquire(engine, other, uid)
        self.assertEqual(CHEF.chef_feature_count(other), 3)
        self.rejected(engine, lambda: FIX.acquire(engine, other, CHEF.DUMPLINGS), 'four acquired Chef Features')
        I.register_feats(engine, chef)
        self.assertTrue(engine.validate_state()['valid'])

    def test_culinary_appreciation_pays_two_tutor_points_extended_time_and_binds_the_corpus_gluttony(self):
        world = FIX.scene(self.rules, feats=(CHEF.CLASS, CHEF.APPRECIATION), ally=True)
        engine, chef, partner, companion = world['engine'], world['chef'], world['partner'], world['companion']
        self.assertEqual(ABILITIES.known(partner), [])
        self.rejected(engine, lambda: self.lesson(engine, chef, companion), 'different trainer')
        self.rejected(engine, lambda: self.lesson(engine, chef, partner, ability='ability/도시락통-playtest'), 'outside')
        partner.spec['tutor_points'] = 1
        self.rejected(engine, lambda: self.lesson(engine, chef, partner), 'two actual Tutor Points')
        partner.spec['tutor_points'] = 5
        result = self.lesson(engine, chef, partner)
        self.assertEqual((result['source'], result['ability'], result['point_cost'], result['seconds']), (CHEF.APPRECIATION, 'ability/먹보-playtest', 2, 600))
        self.assertEqual((engine.elapsed_seconds, partner.spec['tutor_points']), (600, 3))
        self.assertEqual(ABILITIES.known(partner), ['ability/먹보-playtest'])
        self.assertEqual(engine.activity_job_status(result['job_id'])['status'], 'complete')
        limits = FOOD.food_limits(engine, partner)
        self.assertEqual((limits['stored'], limits['per_scene'], limits['drinks']), (3, 3, 2))
        self.assertEqual(FOOD.buff_capacity(engine, partner), 3)
        # No printed once-per-Pokemon limit: the second lesson fails only because the Ability is already held.
        self.rejected(engine, lambda: self.lesson(engine, chef, partner), 'already has the printed Ability')
        loaded, actors = FIX.restore(self.rules, engine)
        self.assertEqual(ABILITIES.known(actors[partner.entity_id]), ['ability/먹보-playtest'])
        self.assertTrue(loaded.validate_state()['valid'])

    def test_culinary_appreciation_under_core_ruleset_refuses_the_excluded_playtest_source_without_payment(self):
        world = FIX.scene(self.core, feats=(CHEF.CLASS, CHEF.APPRECIATION))
        engine, chef, partner = world['engine'], world['chef'], world['partner']
        self.rejected(engine, lambda: self.lesson(engine, chef, partner), 'Excluded rule selection')
        self.assertEqual((partner.spec['tutor_points'], engine.elapsed_seconds, ABILITIES.known(partner)), (5, 0, []))
        # The distinct core definition is now admitted; this explicit Playtest request still is not.
        self.assertEqual(self.core.selection.resolve_name('먹보', ('ability/',)), 'ability/먹보')

    def test_dietician_acquired_through_the_static_receipt_registers_seven_vitamin_capacity(self):
        world = FIX.scene(self.rules, feats=(CHEF.CLASS, CHEF.DIETICIAN), ally=True, register=False)
        engine, chef, partner, companion = world['engine'], world['chef'], world['partner'], world['companion']
        self.assertEqual(MOVE_STATE.vitamin_state(self.rules, partner.spec)['capacity'], 5)
        I.register_feats(engine, chef)
        self.assertEqual(MOVE_STATE.vitamin_state(self.rules, partner.spec)['capacity'], 7)
        self.assertEqual(MOVE_STATE.vitamin_state(self.rules, companion.spec)['capacity'], 5)
        self.assertEqual(chef.spec['dietician_acquisition']['class_source'], CHEF.CLASS)
        self.assertTrue(engine.validate_state()['valid'])

    def test_receipts_survive_json_and_gm_restore_and_reject_forged_ownership(self):
        world = FIX.scene(self.rules)
        engine, chef = world['engine'], world['chef']
        engine.gm.snapshot('acquired')
        loaded, actors = FIX.restore(self.rules, engine)
        restored = actors[chef.entity_id]
        self.assertEqual(restored.spec['feats'], list(FIX.ALL_FEATURES))
        self.assertEqual(CHEF.chef_feature_count(restored), 7)
        self.assertTrue(loaded.validate_state()['valid'])
        rows = [row for _, row, live in ACQUIRE._static_records(restored) if live]
        self.assertEqual(len(rows), 7)
        for uid in FIX.ALL_FEATURES:
            replay = FIX.acquire(loaded, restored, uid)
            self.assertEqual(replay['status'], 'acquired')
        chef.spec['feats'].append(CHEF.DUMPLINGS)
        self.assertFalse(engine.validate_state()['valid'])
        engine.gm.restore('acquired', reason='rewind the forged duplicate')
        self.assertTrue(engine.validate_state()['valid'])
        chef.spec['skills']['직감'] = 2
        self.assertTrue(engine.validate_state()['valid'])  # historical qualification snapshots are immutable receipts
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='preserves', origin='item/오랭열매'), 'required')


if __name__ == '__main__':
    unittest.main()
