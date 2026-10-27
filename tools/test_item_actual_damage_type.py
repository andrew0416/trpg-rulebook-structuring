"""S-p2_csv_items-1 (C2CSV/inventory:69:17 타입 방어복, C2CSV/inventory:127:10 약점보험).

R69 "구매시 타입 하나를 선택하세요. 선택한 타입 데미지에 대한 10의 데미지 감소"
R127 "효과가 굉장한 공격을 맞을 경우 자유 행동으로 선언. 이번 인카운트동안, 데미지에 +10"
Both read the ACTUAL damage of the hit (type of the damage / actual effectiveness).
Actual-type producer: reviewed alternate mode 타오르는분노(악 -> 불꽃) chosen through
GM.choose_alternate_move_type and consumed by Engine.use_move.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from grid import Grid
import items as ITEMS
import world_entities as WORLD
import equipment_variant_contracts as VARIANTS
import csv_item_physical_contracts as PHYSICAL


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def attacker(self):
        return Combatant(self.r, build_pokemon(self.r, "파이어-가라르", 30,
            name="Alt-mode attacker", moves=["move/타오르는분노", "move/화염방사"],
            abilities=["심록"], side="foe"))

    def world(self, target):
        e = Engine(self.r, seed=49214)
        e.grid = Grid(30, 30)
        a = self.attacker()
        a.pos = (1, 1); target.pos = (2, 1)
        e.gm.add_combatant(a); e.gm.add_combatant(target)
        e.begin_encounter(e.everyone)
        a.on_field = target.on_field = True
        e.start_round([a, target]); e.start_of_turn(a, initiative_count=20)
        return e, a

    def equip(self, e, owner, uid, item_id, *, chosen_type=None, held=False):
        WORLD.register_object(e, uid, location={"kind": "unknown"}, reason="audit r3 actual-type fixture",
                              kind="item_instance", item_rule_id=item_id, owner_id=owner.entity_id)
        if chosen_type is not None:
            VARIANTS.configure_type_armor(e, owner, uid, chosen_type)
        ITEMS.register_item(e, owner, item_id, source_instance_id=uid, as_held=held)

    def strike(self, e, a, target, move_id, fire_mode):
        if fire_mode:
            e.gm.choose_alternate_move_type(a, "move/타오르는분노", "불꽃", reason="player selects Fire mode")
        e.d20 = lambda: 12
        dealt = e.use_move(a, target, move_id, set_damage=True)
        if fire_mode:
            self.assertTrue(any("타입 선택 사용: 악 → 불꽃" in line for line in e.log_lines))
        self.assertTrue(e.validate_state()["valid"])
        return dealt


class TypeArmorActualType(_Base):
    def trainer(self):
        return Combatant(self.r, build_trainer(self.r, "Type-armor wearer", 30,
            {"hp": 80, "atk": 20, "def": 20, "spa": 20, "spd": 20, "spe": 20},
            extra={"moves": ["move/몸통박치기"], "movement": {"land": 6, "power": 7},
                   "power_basis": "current", "skills": {"은신": 3}, "side": "party"}))

    def dealt(self, armor_type, move_id, fire_mode):
        t = self.trainer()
        e, a = self.world(t)
        if armor_type is not None:
            self.equip(e, t, "equipment-variant/audit-r3-armor", "item/타입-방어복", chosen_type=armor_type)
        before = t.hp
        dealt = self.strike(e, a, t, move_id, fire_mode)
        self.assertGreater(t.hp, 0)
        self.assertEqual(before - t.hp, dealt)
        return dealt

    def test_control_printed_fire_reduced_by_fire_armor(self):
        self.assertEqual(self.dealt(None, "move/화염방사", False) - self.dealt("불꽃", "move/화염방사", False), 10)

    def test_actual_fire_damage_reduced_by_fire_armor(self):
        bare = self.dealt(None, "move/타오르는분노", True)
        armored = self.dealt("불꽃", "move/타오르는분노", True)
        self.assertEqual(bare - armored, 10, msg=f"bare={bare} fire-armor={armored}")

    def test_dark_armor_does_not_reduce_actual_fire_damage(self):
        bare = self.dealt(None, "move/타오르는분노", True)
        armored = self.dealt("악", "move/타오르는분노", True)
        self.assertEqual(bare - armored, 0, msg=f"bare={bare} dark-armor={armored}")


class WeaknessPolicyActualEffectiveness(_Base):
    def holder(self, types):
        spec = build_pokemon(self.r, "피카츄", 40, name="Weakness holder", moves=["move/몸통박치기"],
                             abilities=[], side="party", extra={"types": list(types)})
        return Combatant(self.r, spec)

    def pending_after(self, types, move_id, fire_mode):
        h = self.holder(types)
        e, a = self.world(h)
        self.equip(e, h, "audit/r3-weakness", "item/약점보험", held=True)
        self.strike(e, a, h, move_id, fire_mode)
        return "weakness_policy" in h.spec.get(PHYSICAL.PENDING, {})

    def test_control_printed_fire_on_grass_offers_policy(self):
        self.assertTrue(self.pending_after(("풀",), "move/화염방사", False))

    def test_actual_fire_on_grass_offers_policy(self):
        self.assertTrue(self.pending_after(("풀",), "move/타오르는분노", True),
                        msg="actual Fire (x2 vs Grass) hit did not offer Weakness Policy")

    def test_actual_fire_on_psychic_does_not_offer_policy(self):
        # printed 악 would be super effective vs 에스퍼, actual 불꽃 is neutral
        self.assertFalse(self.pending_after(("에스퍼",), "move/타오르는분노", True),
                         msg="neutral actual Fire hit offered Weakness Policy from printed Dark type")


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for case in (TypeArmorActualType, WeaknessPolicyActualEffectiveness):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__ == "__main__":
    unittest.main()
