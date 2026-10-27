"""S-p2_core_c07_2-1 (C07-143): Frozen is cured by a damaging Fire/Fighting/Rock/Steel
attack -- the attack's ACTUAL damage type, not its printed type.

ch07:582 "얼음 대상에게 데미지를 주는 불꽃, 격투, 바위, 강철 공격을 받으면 얼음 상태를 치료"
EN p246 "hit by a Damaging Fire, Fighting, Rock, or Steel Attack".
Producer of the actual type: GM/player choice of the reviewed alternate-type mode
(타오르는분노 악 -> 불꽃, data/alternate-move-mode-policy.json) consumed by Engine.use_move.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
from grid import Grid
import alternate_move_modes as ALTERNATE


class FrozenActualTypeThaw(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def setUp(self):
        self.e = Engine(self.r, seed=49214)
        self.e.grid = Grid(30, 30)
        self.p = Combatant(self.r, build_pokemon(self.r, "파이어-가라르", 30,
            moves=["move/타오르는분노", "move/화염방사"], abilities=["심록"]))
        # Grass/Poison target: Fire x2 > Dark x1.
        self.t = Combatant(self.r, build_pokemon(self.r, "이상해꽃", 60,
            moves=["move/몸통박치기"], abilities=["심록"], side="wild"))
        self.p.pos = (1, 1); self.t.pos = (2, 1)
        self.e.gm.add_combatant(self.p); self.e.gm.add_combatant(self.t)
        self.e.start_round([self.p, self.t]); self.e.start_of_turn(self.p, initiative_count=20)
        self.e.apply_status(self.t, "얼음")
        self.assertIn("얼음", self.t.conditions)

    def hit(self, move_id):
        self.e.d20 = lambda: 12
        before = self.t.hp
        dealt = self.e.use_move(self.p, self.t, move_id, set_damage=True)
        self.assertGreater(dealt, 0, msg="\n".join(self.e.log_lines))
        self.assertLess(self.t.hp, before)
        self.assertGreater(self.t.hp, 0)
        return dealt

    def test_control_printed_fire_attack_thaws(self):
        self.hit("move/화염방사")
        self.assertNotIn("얼음", self.t.conditions)
        self.assertTrue(self.e.validate_state()["valid"])

    def test_control_printed_dark_mode_keeps_frozen(self):
        self.hit("move/타오르는분노")
        self.assertIn("얼음", self.t.conditions)

    def test_actual_fire_mode_of_dark_move_thaws(self):
        self.e.gm.choose_alternate_move_type(self.p, "move/타오르는분노", "불꽃",
                                             reason="player selects the optional Fire mode")
        self.hit("move/타오르는분노")
        status = ALTERNATE.status(self.p, "move/타오르는분노")
        self.assertEqual(status[0]["use"]["actual_type"], "불꽃")
        self.assertTrue(any("타입 선택 사용: 악 → 불꽃" in line for line in self.e.log_lines))
        self.assertNotIn("얼음", self.t.conditions,
                         msg="actual Fire damage hit did not cure Frozen (printed type 악 was read)")


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromTestCase(FrozenActualTypeThaw)


if __name__ == "__main__":
    unittest.main()
