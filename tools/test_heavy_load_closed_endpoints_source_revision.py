"""Closed Heavy ranges connect actual carried weight to native penalties/actions."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
import capability_actions as CAP
import state_codec as CODEC
import test_category3_capabilities as FIXTURE
import turn as TURN
import world_entities as WORLD


class HeavyLoadClosedEndpointSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    actor = FIXTURE.Tests.actor
    setUp = FIXTURE.Tests.setUp
    turn = FIXTURE.Tests.turn

    def observe(self, weight, *, identity='actual-endpoint-crate', **options):
        return self.e.gm.set_carried_objects(
            self.a, [{'id': identity, 'weight_kg': weight}],
            'GM weighs this actual carried object', **options)

    def test_all_printed_rows_include_both_endpoints_in_actual_combined_carried_weight(self):
        for power in range(1, 17):
            self.a.spec['movement']['power'] = power
            limits = CAP.limits(self.a)
            for edge, weight in enumerate(limits['heavy']):
                with self.subTest(power=power, endpoint=edge):
                    objects = [{'id': f'power-{power}-edge-{edge}-part-{n}',
                                'weight_kg': weight / 2} for n in (1, 2)]
                    result = self.e.gm.set_carried_objects(
                        self.a, objects, 'GM weighs both actual objects at the printed total')
                    self.assertEqual(result['weight_kg'], weight)
                    self.assertEqual(result['band'], 'heavy')
                    self.assertEqual((CAP.accuracy(self.a), CAP.evasion(self.a)), (-2, -2))
                    self.assertIsNone(self.a.spec['_carried_load']['boundary_band'])
            low, high = limits['heavy']
            self.assertEqual(self.observe(low - 0.01, identity=f'below-{power}')['band'], 'normal')
            self.assertEqual(self.observe(high + 0.01, identity=f'above-{power}')['band'], 'staggering')
        self.e.gm.set_carried_objects(self.a, [], 'actual release of the last objects')
        self.assertEqual(CAP.load(self.a)['band'], 'normal')

    def test_either_heavy_endpoint_preserves_native_actions_and_applies_actual_accuracy_penalty(self):
        for weight in (34, 52):
            with self.subTest(weight=weight):
                self.setUp()
                self.a.stages['spe'] = 2
                before_speed = self.a.staged('spe')
                self.observe(weight)
                self.assertEqual(self.a.stages['spe'], 2)
                self.assertLess(self.a.staged('spe'), before_speed)
                self.assertEqual(self.a.evasion('물리', engine=self.e), 2)
                self.b.stats['spe'] = self.b.stats['spd'] = 0
                move = self.rules.move('move/화염방사')
                self.assertFalse(self.e.accuracy_check(self.a, self.b, move, fixed_roll=3)[0])
                self.turn()
                self.assertTrue(TURN.spend(self.e, self.a, 'standard', 'actual permitted Heavy action'))
                start = self.a.pos
                self.e.approach(self.a, self.b)
                self.assertNotEqual(self.a.pos, start)
                self.assertEqual(self.a.budget['shift'], 0)
                self.e.gm.set_carried_objects(self.a, [], 'actual release restores independent stages')
                self.assertEqual(self.a.staged('spe'), before_speed)
                self.assertEqual(self.a.stages['spe'], 2)
                self.assertTrue(self.e.accuracy_check(self.a, self.b, move, fixed_roll=3)[0])

    def test_above_heavy_and_exact_staggering_limit_keep_real_restrictions_and_round_check(self):
        for weight in (52.01, 104):
            with self.subTest(weight=weight):
                self.setUp()
                self.assertEqual(self.observe(weight)['band'], 'staggering')
                self.turn()
                standard = self.a.budget['standard']
                self.assertFalse(TURN.spend(self.e, self.a, 'standard', 'blocked actual Staggering action'))
                self.assertEqual(self.a.budget['standard'], standard)
                self.assertEqual(self.e.move_profile(self.a)[0], 1)
                self.assertEqual((CAP.accuracy(self.a), CAP.evasion(self.a)), (-4, -4))
                with self.assertRaises(ValueError):
                    self.e.end_of_turn(self.a)
                check = self.e.carry_check(self.a, fixed=iter([2, 2]))
                self.assertEqual((check.dc, check.total), (4, 4))
                self.assertTrue(check.passed)
                self.e.end_of_turn(self.a)

    def test_opposite_legacy_boundary_rulings_never_override_source_or_mutate_native_state(self):
        self.observe(40)
        for weight, band in ((34, 'normal'), (34, 'staggering'),
                             (52, 'normal'), (52, 'staggering'), (60, 'heavy')):
            with self.subTest(weight=weight, band=band):
                before = deepcopy((self.a.spec, self.a.budget, self.e._physical_objects))
                rng = self.e.rng.getstate()
                with self.assertRaises(ValueError):
                    self.observe(weight, identity='invalid-observation', boundary_band=band)
                self.assertEqual((self.a.spec, self.a.budget, self.e._physical_objects), before)
                self.assertEqual(self.e.rng.getstate(), rng)
        self.observe(52, identity='historical-heavy-endpoint', boundary_band='heavy')
        self.assertEqual(CAP.load(self.a)['band'], 'heavy')
        # An old live sheet may retain the former opposite ruling. Do not silently
        # rewrite that history or let it determine future source-rule actions.
        self.a.spec['_carried_load']['boundary_band'] = 'staggering'
        with self.assertRaises(ValueError):
            CAP.load(self.a)
        self.assertEqual(self.a.spec['_carried_load']['boundary_band'], 'staggering')
        self.observe(52, identity='historical-heavy-endpoint')
        self.assertEqual(CAP.load(self.a)['band'], 'heavy')
        self.assertIsNone(self.a.spec['_carried_load']['boundary_band'])

    def test_gm_and_cold_json_restore_preserve_closed_endpoint_and_reversible_sources(self):
        for restoration in ('gm', 'json'):
            with self.subTest(restoration=restoration):
                self.setUp()
                self.a.stages['spe'] = 2
                stages = deepcopy(self.a.stages)
                self.observe(52, boundary_band='heavy')
                identity = self.a.entity_id
                if restoration == 'gm':
                    self.e.gm.snapshot('actual closed Heavy endpoint')
                    self.e.gm.set_carried_objects(self.a, [], 'actual temporary release')
                    self.e.gm.restore('actual closed Heavy endpoint')
                else:
                    payload = json.loads(json.dumps(CODEC.dump_engine(self.e)))
                    self.e = CODEC.load_engine(Rules(ROOT, ruleset='core'), payload)
                self.a = WORLD.actor_index(self.e)[identity]
                self.assertEqual(CAP.load(self.a)['band'], 'heavy')
                self.assertEqual(CAP.load(self.a)['weight_kg'], 52)
                self.assertEqual(self.a.stages, stages)
                self.assertEqual((CAP.accuracy(self.a), CAP.evasion(self.a)), (-2, -2))
                self.e.gm.set_carried_objects(self.a, [], 'actual release after restoring the observed objects')
                self.assertEqual(CAP.load(self.a)['band'], 'normal')
                self.assertEqual((CAP.accuracy(self.a), CAP.evasion(self.a)), (0, 0))
                self.assertEqual(self.a.stages, stages)


if __name__ == '__main__':
    unittest.main()
