"""Direct contracts for Assurance, Revenge and Avalanche source rows."""
from pathlib import Path
from unittest.mock import patch
import os
import sys
import unittest


HERE = Path(__file__).resolve()
STAGE = HERE.parents[1]
ROOT = Path(os.environ.get("PTK_EXPERIMENT_ROOT") or
            (STAGE if (STAGE / "data").exists() else Path(os.environ["PTK_EXPERIMENT_ROOT"])))
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

from engine import Rules, Engine, Combatant
from builder import build_trainer
from grid import Grid
import conditional_damage_base as CONDITIONAL_DB


class ConditionalDamageBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")
        cls.moves = {move.get("eng"): move["id"] for move in cls.r.moves.values()}
        cls.assurance = cls.moves["Assurance"]
        cls.revenge = cls.moves["Revenge"]
        cls.avalanche = cls.moves["Avalanche"]

    def add(self, name, side, pos, moves=()):
        spec = build_trainer(self.r, name, 30,
            {key: 30 for key in ("hp", "atk", "def", "spa", "spd", "spe")},
            moves=list(moves), pos=pos, side=side, extra={"abilities": []})
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def setUp(self):
        self.e = Engine(self.r, seed=411)
        self.e.grid = Grid(12, 12)
        all_moves = (self.assurance, self.revenge, self.avalanche)
        self.a = self.add("conditional user", "party", (2, 2), all_moves)
        self.b = self.add("first target", "enemy", (3, 2))
        self.c = self.add("second target", "enemy", (3, 3))
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=30)

    def actual_damage(self, source, target, move_id=None, amount=7):
        move = self.r.move(move_id or self.assurance)
        with patch.object(self.e, "roll_damage", return_value=amount):
            return self.e.resolve_attack_damage(source, target, move)

    def test_assurance_reads_actual_same_round_damage_and_limits_each_scene_target(self):
        move = self.r.move(self.assurance)
        self.assertEqual(self.e.damage_base(self.a, move, target=self.b), 6)
        self.actual_damage(self.c, self.b)
        self.assertEqual(self.e.damage_base(self.a, move, target=self.b), 12)
        self.assertEqual(self.e.damage_base(self.a, move, target=self.c), 6)
        self.actual_damage(self.a, self.b, self.assurance)
        self.assertEqual(self.e.damage_base(self.a, move, target=self.b), 6)
        self.actual_damage(self.b, self.c)
        self.assertEqual(self.e.damage_base(self.a, move, target=self.c), 12)
        self.assertTrue(any(key.startswith("lim:conditional-db:") for key in self.a.counters))

    def test_damage_history_requires_positive_observed_loss_and_current_round(self):
        move = self.r.move(self.assurance)
        self.actual_damage(self.c, self.b, amount=0)
        self.assertEqual(self.e.damage_base(self.a, move, target=self.b), 6)
        self.actual_damage(self.c, self.b, amount=5)
        self.assertEqual(self.e.damage_base(self.a, move, target=self.b), 12)
        self.e.end_of_turn(self.a)
        self.e.end_round()
        self.e.start_round(self.e.everyone)
        self.assertEqual(self.e.damage_base(self.a, move, target=self.b), 6)

    def test_revenge_and_avalanche_require_damage_from_the_declared_target(self):
        revenge = self.r.move(self.revenge)
        avalanche = self.r.move(self.avalanche)
        self.actual_damage(self.c, self.a)
        for move in (revenge, avalanche):
            self.assertEqual(self.e.damage_base(self.a, move, target=self.b), 6)
            self.assertEqual(self.e.damage_base(self.a, move, target=self.c), 12)

    def test_round_end_setup_locks_then_resolves_revenge_once(self):
        before = self.b.hp
        with patch.object(self.e, "d20", return_value=10) as accuracy:
            self.assertEqual(self.e.use_move(self.a, self.b, self.revenge), 0)
        accuracy.assert_not_called()
        self.assertTrue(CONDITIONAL_DB.action_locked(self.a))
        self.assertEqual(set(self.a.budget.values()), {0})
        self.assertEqual(self.a.move_uses[self.revenge], 1)
        self.assertEqual(self.e.use_move(self.a, self.c, self.assurance), 0)
        old_pos = self.a.pos
        self.assertEqual(self.e.approach(self.a, self.c), 0)
        self.assertEqual(self.a.pos, old_pos)
        self.e.end_of_turn(self.a)
        with patch.object(Engine, "d20", return_value=10), \
             patch.object(Engine, "roll_damage", return_value=8) as damage:
            self.e.end_round()
        damage.assert_called_once()
        self.assertLess(self.b.hp, before)
        self.assertFalse(CONDITIONAL_DB.action_locked(self.a))
        self.assertIsNone(self.a.setup_move)
        self.assertEqual(self.a.move_uses[self.revenge], 1)

    def test_avalanche_uses_the_same_round_end_contract(self):
        before = self.b.hp
        self.assertEqual(self.e.use_move(self.a, self.b, self.avalanche), 0)
        self.e.end_of_turn(self.a)
        with patch.object(Engine, "d20", return_value=10), \
             patch.object(Engine, "roll_damage", return_value=8):
            self.e.end_round()
        self.assertLess(self.b.hp, before)
        self.assertEqual(self.a.move_uses[self.avalanche], 1)
        self.assertFalse(CONDITIONAL_DB.action_locked(self.a))


if __name__ == "__main__":
    unittest.main(verbosity=2)
