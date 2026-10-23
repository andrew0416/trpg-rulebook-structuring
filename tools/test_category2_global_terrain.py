"""Direct contract tests for the four reviewed global Terrain Move rows."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest


STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

import field_effects as FIELD
import effects as _STAGED_EFFECTS
from engine import Combatant, Engine, Rules
from builder import build_pokemon


IDS = {
    "C2CSV-MOVE-R0116": "move/일렉트릭필드",
    "C2CSV-MOVE-R0169": "move/미스트필드",
    "C2CSV-MOVE-R0345": "move/그래스필드",
    "C2CSV-MOVE-R0710": "move/사이코필드",
}


class GlobalTerrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def setUp(self):
        self.e = Engine(self.r, seed=116169345710)
        self.a = Combatant(self.r, build_pokemon(self.r, "피카츄", 30,
            moves=list(IDS.values()), abilities=["정전기"]))
        self.t = Combatant(self.r, build_pokemon(self.r, "이상해씨", 25,
            moves=["move/전광석화", "move/스카이어퍼", "move/몸통박치기"],
            abilities=["심록"], side="wild"))
        self.e.gm.add_combatant(self.a)
        self.e.gm.add_combatant(self.t)
        self.e.start_round([self.a, self.t])
        self.e.start_of_turn(self.a, initiative_count=20)

    def _install(self, move_id):
        effect = self.r.move_mech(move_id)[0]["effects_exec"][0]
        return FIELD.install(self.e, self.a, effect, move_id)

    def _damage(self, move_id):
        return self.e.roll_damage(self.a, self.t, self.r.move(move_id), set_damage=True)

    def test_source_rows_and_contract_boundary_table(self):
        registry = json.loads((ROOT / "data/verification/category2-csv-abilities-moves-status.json").read_text(encoding="utf-8"))
        rows = {row["row_id"]: row for row in registry["rows"] if row["row_id"] in IDS}
        self.assertEqual(set(rows), set(IDS))
        # This test is valid both before and after candidate reconciliation.
        self.assertTrue(all(row["category2_status"] in {"incomplete", "implemented"} for row in rows.values()))
        policy = FIELD.policy(self.r)["moves"]
        expected = {
            "move/일렉트릭필드": ("일렉트릭", 5, "grounded_electric_damage_bonus", 10),
            "move/미스트필드": ("미스트", 5, "dragon_vs_grounded_damage_roll", -10),
            "move/그래스필드": ("그래스", 5, "grounded_grass_damage_bonus", 10),
            "move/사이코필드": ("사이코", 5, "grounded_psychic_damage_bonus", 10),
        }
        for clause_id, move_id in IDS.items():
            with self.subTest(clause_id=clause_id):
                row = policy[move_id]
                self.assertEqual(row["clause_id"], clause_id)
                self.assertEqual(row["source_row_sha256"], rows[clause_id]["source_row_sha256"])
                name, rounds, key, value = expected[move_id]
                self.assertEqual((row["field"], row["rounds"], row["effect"][key]), (name, rounds, value))
                FIELD.prepare(self.e, self.r.move_mech(move_id)[0]["effects_exec"][0], move_id)

    def test_actual_move_producer_replacement_and_pre_spend_atomicity(self):
        before_budget = deepcopy(self.a.budget)
        self.e.use_move(self.a, self.a, "move/일렉트릭필드")
        self.assertEqual((self.e.field["kind"], self.e.field["name"], self.e.field["rounds"]),
                         (FIELD.KIND, "일렉트릭", 5))
        self.assertEqual(self.a.budget["standard"], before_budget["standard"] - 1)
        self.e.end_of_turn(self.a)
        self.e.start_round([self.a, self.t])
        self.e.start_of_turn(self.a, initiative_count=20)
        self.e.use_move(self.a, self.a, "move/그래스필드")
        self.assertEqual((self.e.field["source_id"], self.e.field["name"]),
                         ("move/그래스필드", "그래스"))

        self.e.end_of_turn(self.a)
        self.e.start_round([self.a, self.t])
        self.e.start_of_turn(self.a, initiative_count=20)
        old_field, old_budget, old_uses = deepcopy(self.e.field), deepcopy(self.a.budget), deepcopy(self.a.move_uses)
        original = deepcopy(self.r.moves_llm["일렉트릭필드"])
        try:
            self.r.moves_llm["일렉트릭필드"]["effects"][0]["rounds"] = 4
            with self.assertRaisesRegex(ValueError, "differs from reviewed source policy"):
                self.e.use_move(self.a, self.a, "move/일렉트릭필드")
        finally:
            self.r.moves_llm["일렉트릭필드"] = original
        self.assertEqual((self.e.field, self.a.budget, self.a.move_uses), (old_field, old_budget, old_uses))

    def test_electric_immunity_and_misty_status_lifecycle(self):
        self._install("move/일렉트릭필드")
        self.assertFalse(self.e.apply_status(self.t, "잠듦", source="test/sleep", applied_by=self.a))
        self.assertNotIn("잠듦", self.t.conditions)
        self.t.airborne = True
        self.assertTrue(self.e.apply_status(self.t, "잠듦", source="test/sleep-airborne", applied_by=self.a))
        self.assertIn("잠듦", self.t.conditions)
        self.e.cure_status(self.t, "잠듦")
        self.t.airborne = False

        self._install("move/미스트필드")
        self.assertFalse(self.e.apply_status(self.t, "화상", source="test/burn", applied_by=self.a))
        self.assertNotIn("화상", self.t.conditions)
        self.assertTrue(self.e.apply_status(self.t, "혼란", source="test/confusion", applied_by=self.a))
        self.assertNotIn("혼란", self.t.conditions)
        self.assertEqual(FIELD._pending(self.t)[0]["condition"], "혼란")
        self.e.end_of_turn(self.a)
        self.e.start_of_turn(self.t, initiative_count=10)
        self.assertNotIn("혼란", self.t.conditions)
        self.e.end_of_turn(self.t)
        self.assertIn("혼란", self.t.conditions)
        self.assertNotIn(FIELD.DEFERRED, self.t.custom_conditions)

    def test_damage_consumers_use_actual_type_and_ground_contact(self):
        cases = [
            ("move/일렉트릭필드", "move/전기쇼크", 10),
            ("move/그래스필드", "move/덩굴채찍", 10),
            ("move/사이코필드", "move/염동력", 10),
            ("move/미스트필드", "move/용의숨결", -10),
        ]
        for field_move, attack_move, delta in cases:
            with self.subTest(field=field_move):
                self.e.field = None
                self._install(field_move)
                move = self.r.move(attack_move)
                actual_type = move["type"]
                self.assertEqual(FIELD.damage_roll_modifier(self.e, self.a, self.t, move, actual_type), delta)
                before_logs = len(self.e.log_lines)
                self._damage(attack_move)
                self.assertTrue(any(f"피해 굴림 {delta:+d}" in line for line in self.e.log_lines[before_logs:]))
        self.a.airborne = True
        self.t.airborne = True
        self._install("move/미스트필드")
        dragon = self.r.move("move/용의숨결")
        self.assertEqual(FIELD.damage_roll_modifier(self.e, self.a, self.t, dragon, "드래곤"), 0)

    def test_grassy_turn_start_heal_uses_current_maximum_and_ground_contact(self):
        self._install("move/그래스필드")
        self.e.end_of_turn(self.a)
        self.t.hp = self.t.max_hp - 30
        before = self.t.hp
        self.e.start_of_turn(self.t, initiative_count=10)
        self.assertEqual(self.t.hp - before, self.t.max_hp // 10)
        self.t.airborne = True
        self.t.hp -= 10
        before = self.t.hp
        self.assertEqual(FIELD.turn_start(self.e, self.t), 0)
        self.assertEqual(self.t.hp, before)

    def test_psychic_nullifies_single_target_priority_and_interrupt_before_cost(self):
        self._install("move/사이코필드")
        self.e.end_of_turn(self.a)
        self.e.start_of_turn(self.t, initiative_count=10)
        for move_id in ("move/전광석화", "move/스카이어퍼"):
            with self.subTest(move=move_id):
                before = (deepcopy(self.t.budget), deepcopy(self.t.move_uses))
                self.assertEqual(self.e.use_move(self.t, self.a, move_id), 0)
                self.assertEqual((self.t.budget, self.t.move_uses), before)
        ordinary = self.e.use_move(self.t, self.a, "move/몸통박치기", set_damage=True)
        self.assertGreater(ordinary, 0)
        fake = {"id": "move/fake-priority-area", "name": "fake", "range": "파열 1", "keywords": ["우선"]}
        fake_mech = {"header": {"range": {"raw": "파열 1", "shape": "burst", "size": 1}, "keywords": ["우선"]}}
        self.assertIsNone(FIELD.move_block_reason(self.e, self.t, self.a, fake, fake_mech))

    def test_five_round_expiry_snapshot_restore_and_tamper_rejection(self):
        self.e.use_move(self.a, self.a, "move/일렉트릭필드")
        self.e.end_of_turn(self.a)
        self.e.gm.snapshot("terrain")
        self.e.gm.restore("terrain")
        blob = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        restored = Engine.import_state(self.r, blob)
        FIELD.validate(restored)
        actors = list(restored.everyone)
        for expected in (4, 3, 2, 1):
            restored.start_round(actors)
            self.assertEqual(restored.field["rounds"], expected)
        restored.start_round(actors)
        self.assertIsNone(restored.field)

        damaged = Engine.import_state(self.r, blob)
        damaged.field["source_row_sha256"] = "tampered"
        with self.assertRaisesRegex(ValueError, "provenance or payload changed"):
            FIELD.validate(damaged)


if __name__ == "__main__":
    unittest.main()
