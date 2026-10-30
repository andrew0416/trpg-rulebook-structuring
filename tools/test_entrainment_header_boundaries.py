"""IMPL-04 draft: native Entrainment Scene, AC2 and range4 boundaries.

Source-only addition, not yet executed or accepted. Reuses the existing native
AA actors/selection helpers without inheriting the other AA test methods.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
import test_csv_ability_exchange_contracts as _fixture_test_csv_ability_exchange_contracts
import frequency as FREQ
import weapon_actions as WEAPONS

Engine = _fixture_test_csv_ability_exchange_contracts.Engine
Grid = _fixture_test_csv_ability_exchange_contracts.Grid
X = _fixture_test_csv_ability_exchange_contracts.X
A = _fixture_test_csv_ability_exchange_contracts.A


class EntrainmentHeaderBoundaryTests(unittest.TestCase):
    setUpClass = classmethod(_fixture_test_csv_ability_exchange_contracts.AbilityExchangeContractsTests.setUpClass.__func__)
    actor = _fixture_test_csv_ability_exchange_contracts.AbilityExchangeContractsTests.actor
    choose = _fixture_test_csv_ability_exchange_contracts.AbilityExchangeContractsTests.choose
    live = _fixture_test_csv_ability_exchange_contracts.AbilityExchangeContractsTests.live

    def setUp(self):
        self.new_world()

    def new_world(self, distance=4):
        self.e = Engine(self.r, 530)
        self.e.grid = Grid(30, 30)
        self.a = self.actor('donor', ['단순'], (2, 2), 'party')
        self.t = self.actor('recipient', ['불면'], (2+distance, 2), 'opponent')
        self.begin()
        self.choose(self.a, self.t, X.ENTRAIN, '단순')

    def begin(self):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def assert_header(self):
        move = self.r.move(X.ENTRAIN)
        self.assertEqual((move['frequency'], move['ac'], move['range'], move['class'], move['type']),
                         ('장면', 2, '4, 대상 1', '변화', '노말'))
        self.assertEqual(FREQ.move_frequency(self.e, X.ENTRAIN, self.a), ('scene', 1))
        native = WEAPONS.range_spec(self.e, move, self.a)
        self.assertEqual(native['origin'], 4)
        self.assertEqual(native['targets'], 1)
        self.assertFalse(native.get('shape'))

    def gameplay_inputs(self):
        # Return-zero rejections append diagnostics; compare actual resources,
        # source choices, actor state and RNG, rather than requiring an empty log.
        return deepcopy((self.a.budget, self.a.move_uses,
            self.a.spec.get('frequency_state'), self.a.spec.get(A.CHOICES),
            [(c.pos, c.hp, c.injuries, c.conditions, c.stages, c.abilities,
              c.spec['abilities']) for c in (self.a, self.t)], self.e.rng.getstate()))

    def cast(self, face):
        # Class patch survives the native transaction's Engine deepcopy. Only
        # the die face is controlled; accuracy/range/frequency consumers stay real.
        with patch.object(Engine, 'd20', return_value=face) as die:
            result = self.e.use_move(self.a, self.t, X.ENTRAIN, set_damage=True)
        return result, die.call_count

    def test_entrainment_scene_quota_survives_encounter_then_resets_at_scene_boundary(self):
        self.assert_header()
        self.assertEqual(self.cast(20)[1], 1)
        self.assertIn('단순', self.t.abilities)
        self.assertEqual(self.a.move_uses[X.ENTRAIN], 1)
        self.e.end_encounter(self.e.everyone)
        self.begin()
        self.choose(self.a, self.t, X.ENTRAIN, '단순')
        self.assertEqual(self.a.budget['standard'], 1)
        self.assertEqual(FREQ.move_allowed(self.e, self.a, X.ENTRAIN, outside_combat=False),
                         (False, '사용 횟수 소진'))
        before = self.gameplay_inputs()
        start = len(self.e.log_lines)
        self.assertEqual(self.cast(20), (0, 0))
        self.assertEqual(self.gameplay_inputs(), before)
        self.assertEqual(self.live(self.t), [])
        self.assertTrue(any('사용 횟수 소진' in line and '[frequency/move]' in line
                            for line in self.e.log_lines[start:]))
        self.e.end_scene(self.e.everyone)
        self.begin()
        self.choose(self.a, self.t, X.ENTRAIN, '단순')
        self.assertEqual(self.a.move_uses.get(X.ENTRAIN, 0), 0)
        self.assertEqual(self.cast(20)[1], 1)
        self.assertEqual(self.a.move_uses[X.ENTRAIN], 1)
        self.assertEqual(self.a.budget['standard'], 0)
        self.assertIn('단순', self.t.abilities)
        self.assertEqual(len(self.live(self.t)), 1)

    def test_entrainment_ac2_uses_speed_evasion_threshold(self):
        for face, hit in ((3, False), (4, True)):
            with self.subTest(face=face):
                self.new_world()
                self.assert_header()
                self.assertEqual(self.t.evasion('변화', attacker=self.a, engine=self.e), 2)
                start = len(self.e.log_lines)
                self.assertEqual(self.cast(face)[1], 1)
                self.assertEqual('단순' in self.t.abilities, hit)
                self.assertEqual(len(self.live(self.t)), int(hit))
                self.assertEqual(self.t.spec['abilities'], ['불면'])
                self.assertEqual(self.a.move_uses[X.ENTRAIN], 1)
                self.assertEqual(self.a.budget['standard'], 0)
                outcome = '→ 명중' if hit else '→ 빗나감'
                self.assertTrue(any(f'명중 d20={face}+0={face} vs AC 2+회피 2=4' in line
                                    and outcome in line for line in self.e.log_lines[start:]))

    def test_entrainment_range_four_accepts_edge_and_rejects_fifth_meter_before_cost(self):
        for distance in (4, 5):
            with self.subTest(distance=distance):
                self.new_world(distance)
                self.assert_header()
                before = self.gameplay_inputs()
                start = len(self.e.log_lines)
                result, rolls = self.cast(20)
                if distance == 4:
                    self.assertEqual(rolls, 1)
                    self.assertIn('단순', self.t.abilities)
                    self.assertEqual(len(self.live(self.t)), 1)
                    self.assertEqual(self.a.move_uses[X.ENTRAIN], 1)
                    self.assertEqual(self.a.budget['standard'], 0)
                else:
                    self.assertEqual((result, rolls), (0, 0))
                    self.assertEqual(self.gameplay_inputs(), before)
                    self.assertEqual(self.live(self.t), [])
                    self.assertTrue(any('target outside current attack reach' in line
                                        and '[combat/range]' in line
                                        for line in self.e.log_lines[start:]))


if __name__ == '__main__':
    unittest.main()
