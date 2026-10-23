"""Shared dice preserve native results, validation boundaries, and RNG order."""
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
import roll_pools as P
from engine import Engine, Rules


class PoolTests(unittest.TestCase):
    def test_declared_die_sizes_and_offsets_match_independent_rng(self):
        rng = random.Random(137)
        oracle = random.Random(137)
        for sides in (4, 6, 8, 10, 12, 20, 100):
            with self.subTest(sides=sides):
                expected = [oracle.randint(1, sides) for _ in range(5)]
                result = P.pool(rng, 5, sides=sides, offset=-8)
                self.assertEqual(result['faces'], expected)
                self.assertEqual(result['total'], sum(expected) - 8)
                self.assertEqual(rng.getstate(), oracle.getstate())

    def test_fixed_pool_has_path_evidence_and_uses_no_randomness(self):
        result = P.pool(None, 3, sides=12, offset=4, fixed=(1, 12, 5))
        self.assertEqual(result['total'], 22)
        self.assertEqual(result['observations'], [
            {'path': str(i), 'face': face, 'rerolled': False}
            for i, face in enumerate((1, 12, 5))])

    def test_zero_pool_is_valid_and_does_not_need_rng(self):
        self.assertEqual(P.pool(None, 0, offset=-3)['total'], -3)
        self.assertEqual(P.pool(None, 0, fixed=[])['faces'], [])

    def test_invalid_pool_input_never_advances_rng(self):
        rng = random.Random(3)
        before = rng.getstate()
        options = [dict(count=-1), dict(count=True), dict(count=2, sides=0),
                   dict(count=2, offset=True), dict(count=2, fixed=[1]),
                   dict(count=2, fixed=[1, 7]), dict(count=2, fixed=[1, True]),
                   dict(count=2, fixed={'0': 1, '1': 2})]
        for option in options:
            with self.subTest(option=option), self.assertRaises(ValueError):
                P.pool(rng, **option)
            self.assertEqual(rng.getstate(), before)

    def test_dice_and_flat_bonus_multipliers_are_independent(self):
        for dice, bonus, faces, expected in [
                (1, 1, [1, 2], 11), (2, 1, [1, 2, 3, 4], 18),
                (2, 2, [1, 2, 3, 4], 26), (0, 2, [], 16)]:
            with self.subTest(dice=dice, bonus=bonus):
                result = P.expression(None, '2d6+8', dice_multiplier=dice,
                                      flat_bonus_multiplier=bonus, fixed=faces)
                self.assertEqual(result['total'], expected)

    def test_negative_bonus_and_expression_without_bonus(self):
        self.assertEqual(P.expression(None, '2d4-3', fixed=[1, 1])['total'], -1)
        self.assertEqual(P.expression(None, '1d20', fixed=[20])['total'], 20)

    def test_invalid_expression_or_multiplier_never_advances_rng(self):
        rng = random.Random(3)
        before = rng.getstate()
        cases = [(value, {}) for value in
                 (None, 3, '', '2d6garbage', '2d6+8+4', '2d0', '2.5d6', '2d6\n')]
        cases += [('2d6+8', options) for options in
                  (dict(dice_multiplier=True), dict(dice_multiplier=-1),
                   dict(flat_bonus_multiplier=1.5), dict(fixed=[1, 2, 3]))]
        for expr, options in cases:
            with self.subTest(expr=expr, options=options), self.assertRaises(ValueError):
                P.expression(rng, expr, **options)
            self.assertEqual(rng.getstate(), before)


class NativeDiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def test_existing_expression_api_preserves_scaled_bonus_and_rng_sequence(self):
        engine = Engine(self.rules, seed=137)
        oracle = random.Random(137)
        for times in (1, 2, 3):
            expected = [oracle.randint(1, 6) for _ in range(2 * times)]
            self.assertEqual(engine.roll_expr('2d6+8', times),
                             (sum(expected) + 8 * times, expected))
        self.assertEqual(engine.d20(), oracle.randint(1, 20))
        self.assertEqual(engine.rng.getstate(), oracle.getstate())

    def test_native_fixed_expression_and_invalid_text_do_not_draw_rng(self):
        engine = Engine(self.rules, seed=137)
        before = engine.rng.getstate()
        self.assertEqual(engine.roll_expr('2d6+8', 2, fixed=[1, 2, 3, 4]),
                         (26, [1, 2, 3, 4]))
        with self.assertRaises(ValueError):
            engine.roll_expr('2d6+8invalid')
        self.assertEqual(engine.rng.getstate(), before)


if __name__ == '__main__':
    unittest.main()
