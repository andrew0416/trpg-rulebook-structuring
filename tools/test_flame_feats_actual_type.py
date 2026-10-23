"""S-p2cfe-3 (feats.csv R253 빛나는 화염, R624 불타는 낙인): burn trigger reads the
printed Move type instead of the actual damage type.

R253 '당신의 포켓몬이 사용하는 피해를 입히는 불꽃타입 기술은 18+에 화상' (EN core 3802
"Your Pokemon's Damaging Fire-Type Moves ... Burn on 18+").
Actual-type producer (Pokemon): reviewed alternate mode 타오르는분노 악 -> 불꽃 chosen through
GM.choose_alternate_move_type, consumed by Engine.use_move.
R624 (trainer's own Fire moves, 19+): no rule-faithful producer lets a trainer use a Move whose
actual type differs from the printed one (alternate modes are Pokemon-only).  The synthetic class
below gives a trainer 심판의뭉치('any' type) only to show the shared guard; it is NOT used as
rule-faithful reproduction evidence.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
import class_passive_combat as C
import alternate_move_modes as ALTERNATE
import test_category2_class_passive_combat_bulk as FIXTURE


class ShiningFlameActualType(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIXTURE.ClassPassiveCombatBulkTests.setUpClass()
        cls.rules = FIXTURE.ClassPassiveCombatBulkTests.rules

    def use(self, move_id, *, feat=True, fire_mode=False, natural=18):
        f = FIXTURE.ClassPassiveCombatBulkTests("test_shining_flame_and_burning_brand_split_owner_scope_and_burn_move_exception")
        e, t, p, q = f.fixture(feats=[C.SHINING_FLAME] if feat else [],
                               pokemon_moves=["move/타오르는분노", "move/니트로차지"])
        e.gm.observe_loyalty(p, 6, reason="observed current trainer relationship")
        e.begin_encounter(e.everyone)
        e.start_round(e.everyone)
        e.start_of_turn(p, initiative_count=20)
        if fire_mode:
            e.gm.choose_alternate_move_type(p, "move/타오르는분노", "불꽃", reason="player selects Fire mode")
        e.d20 = lambda: natural
        dealt = e.use_move(p, q, move_id, situational=100, set_damage=True)
        self.assertGreater(dealt, 0, msg="\n".join(e.log_lines[-30:]))
        if fire_mode:
            self.assertEqual(ALTERNATE.status(p, "move/타오르는분노")[0]["use"]["actual_type"], "불꽃")
        self.assertTrue(e.validate_state()["valid"])
        return "화상" in q.conditions

    def test_control_printed_fire_18_burns_with_feat(self):
        self.assertTrue(self.use("move/니트로차지"))

    def test_control_printed_fire_18_without_feat_no_burn(self):
        self.assertFalse(self.use("move/니트로차지", feat=False))

    def test_control_dark_mode_18_no_burn(self):
        self.assertFalse(self.use("move/타오르는분노"))

    def test_actual_fire_mode_18_burns(self):
        self.assertTrue(self.use("move/타오르는분노", fire_mode=True),
                        msg="actual Fire damaging Move at natural 18 did not Burn (printed 악 was read)")


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for case in (ShiningFlameActualType,):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__ == "__main__":
    unittest.main()
