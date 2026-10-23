"""Action fixtures accept Rules explicitly and never cache mutable worlds."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
from native_scenario_fixture import (prepare_setup_move_scene, prepare_gmax_scene,
                                     assert_rejected_unchanged, assert_rejections_unchanged)
import gmax_moves as GMAX


class RejectionFixtureTests(unittest.TestCase):
    class World:
        def __init__(self):
            self.state = {'hp': 10, 'rng': 3}
            self.exports = 0

        def export_state(self):
            self.exports += 1
            return self.state.copy()

    def test_batch_checks_every_action_with_one_baseline(self):
        world = self.World()
        def reject():
            raise ValueError('missing stats are unknown')
        errors = assert_rejections_unchanged(world, [reject] * 8,
                                            reason_pattern='missing stats are unknown')
        self.assertEqual(len(errors), 8)
        self.assertEqual(world.exports, 9)
        self.assertIsInstance(assert_rejected_unchanged(world, reject,
                                                        reason_pattern='missing stats'), ValueError)
        self.assertEqual(world.exports, 11)

    def test_batch_stops_at_first_mutation_even_if_later_action_would_restore(self):
        world = self.World()
        def mutate():
            world.state['rng'] += 1
            raise ValueError('rejected')
        def restore():
            world.state['rng'] -= 1
            raise ValueError('rejected')
        with self.assertRaisesRegex(AssertionError, 'changed engine state or RNG'):
            assert_rejections_unchanged(world, [mutate, restore], reason_pattern='rejected')
        self.assertEqual(world.exports, 2)
        self.assertEqual(world.state['rng'], 4)

    def test_batch_keeps_each_rejection_reason_and_validates_before_snapshot(self):
        world = self.World()
        def reject(reason):
            raise ValueError(reason)
        actions = [lambda: reject('first'), lambda: reject('second')]
        with self.assertRaisesRegex(ValueError, 'for each operation'):
            assert_rejections_unchanged(world, actions, reason_pattern=['first'])
        self.assertEqual(world.exports, 0)
        with self.assertRaisesRegex(AssertionError, "did not match 'wrong'"):
            assert_rejections_unchanged(world, actions, reason_pattern=['first', 'wrong'])
        self.assertEqual(world.exports, 3)
        errors = assert_rejections_unchanged(world, actions, reason_pattern=['first', 'second'])
        self.assertEqual([str(error) for error in errors], ['first', 'second'])
        self.assertEqual(world.exports, 6)


class ActionFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='all')

    def assert_separate_worlds(self, first, second):
        self.assertIs(first[0].r, self.rules)
        self.assertIs(second[0].r, self.rules)
        for left, right in zip(first[:3], second[:3]):
            self.assertIsNot(left, right)
        self.assertIsNot(first[1].budget, second[1].budget)
        hp = second[1].hp
        first[1].hp -= 1
        self.assertEqual(second[1].hp, hp)
        self.assertEqual(first[0].round_no, 1)
        self.assertEqual(second[0].round_no, 1)

    def test_setup_uses_supplied_rules_and_fresh_worlds(self):
        with patch('native_scenario_fixture.Rules', side_effect=AssertionError('unexpected Rules creation')):
            first = prepare_setup_move_scene(self.rules)
            second = prepare_setup_move_scene(self.rules)
        self.assert_separate_worlds(first, second)
        self.assertIn('move/공중날기', second[1].moves)

    def test_gmax_uses_supplied_rules_and_fresh_worlds(self):
        row = next(row for row in GMAX.declarations(self.rules)
                   if row['clause_id'] == 'C2CSV-MOVE-R1046')
        with patch('native_scenario_fixture.Rules', side_effect=AssertionError('unexpected Rules creation')):
            first = prepare_gmax_scene(self.rules, row)
            second = prepare_gmax_scene(self.rules, row)
        self.assert_separate_worlds(first, second)
        self.assertEqual(second[2].last_move, second[2].moves[0])
        self.assertEqual(second[4], row['move_id'])


if __name__ == '__main__':
    unittest.main()
