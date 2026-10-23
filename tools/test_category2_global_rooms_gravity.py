"""Direct source-bound contracts for Gravity and the three reviewed Room moves."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]

import field_effects as FIELD
import initiative as INIT
import items as ITEMS
import weather_state as WEATHER
from engine import Combatant, Engine, Rules
from builder import build_pokemon

IDS = {
    "C2CSV-MOVE-R0675": "move/중력",
    "C2CSV-MOVE-R0695": "move/매직룸",
    "C2CSV-MOVE-R0729": "move/트릭룸",
    "C2CSV-MOVE-R0731": "move/원더룸",
}


class GlobalRoomGravityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def setUp(self):
        self.e = Engine(self.r, seed=675695729731)
        self.a = Combatant(self.r, build_pokemon(self.r, "피카츄", 30,
            moves=list(IDS.values()) + ["move/몸통박치기", "move/공중날기"], abilities=["정전기"]))
        self.t = Combatant(self.r, build_pokemon(self.r, "이상해씨", 25,
            moves=["move/몸통박치기"], abilities=["심록"], side="wild"))
        self.e.gm.add_combatant(self.a)
        self.e.gm.add_combatant(self.t)
        self.e.start_round([self.a, self.t])

    def effect(self, move_id):
        return self.r.move_mech(move_id)[0]["effects_exec"][0]

    def install(self, move_id):
        return FIELD.install(self.e, self.a, self.effect(move_id), move_id)

    def test_policy_source_hashes_and_actual_move_producers(self):
        registry = json.loads((ROOT / "data/verification/category2-csv-abilities-moves-status.json").read_text(encoding="utf-8"))
        source = {row["row_id"]: row for row in registry["rows"] if row["row_id"] in IDS}
        self.assertEqual(set(source), set(IDS))
        policy = FIELD.policy(self.r)["moves"]
        for clause, move_id in IDS.items():
            with self.subTest(clause=clause):
                row = policy[move_id]
                self.assertEqual(row["clause_id"], clause)
                self.assertEqual(row["source_row_sha256"], source[clause]["source_row_sha256"])
                plan = FIELD.prepare(self.e, self.effect(move_id), move_id)
                self.assertTrue(plan["reviewed"])
        self.e.start_of_turn(self.a, initiative_count=20)
        self.e.use_move(self.a, self.a, "move/중력")
        self.assertEqual((self.e.field["source_id"], self.e.field["name"], self.e.field["rounds"]),
                         ("move/중력", "왜곡", 5))

    def test_gravity_closes_move_accuracy_height_and_ground_immunity_consumers(self):
        tackle = self.r.move("move/몸통박치기")
        self.assertFalse(self.e.accuracy_check(
            self.a, self.t, tackle, fixed_roll=3)[0])
        self.install("move/중력")
        self.assertEqual(FIELD.accuracy_modifier(self.e, self.a), 2)
        self.assertTrue(self.e.accuracy_check(
            self.a, self.t, tackle, fixed_roll=3)[0])
        self.assertEqual(FIELD.move_block_reason(self.e, self.a, self.t,
            self.r.move("move/공중날기"), self.r.move_mech("move/공중날기")[0]), "move/중력")
        self.e.start_of_turn(self.a, initiative_count=20)
        before = (deepcopy(self.a.budget), deepcopy(self.a.move_uses),
                  deepcopy(self.a.custom_conditions), self.a.setup_move)
        self.assertEqual(self.e.use_move(self.a, self.t, "move/공중날기"), 0)
        self.assertEqual((self.a.budget, self.a.move_uses,
                          self.a.custom_conditions, self.a.setup_move), before)
        self.assertEqual(self.e.use_setup_move_on(
            self.a, self.t, "move/공중날기", self.e.everyone, setup_options={}), 0)
        self.assertEqual((self.a.budget, self.a.move_uses,
                          self.a.custom_conditions, self.a.setup_move), before)
        with self.assertRaisesRegex(ValueError, "above 1 metre"):
            FIELD.validate_aerial_height(self.e, self.a, 2)
        self.a.spec["_movement_altitude"] = 2
        with self.assertRaisesRegex(ValueError, "above 1 metre"):
            self.e.end_of_turn(self.a)
        self.a.spec["_movement_altitude"] = 0
        original = list(self.t._types)
        self.t._types = ["비행"]
        try:
            self.assertEqual(self.e.type_multiplier("땅", self.t)[0], 1.0)
        finally:
            self.t._types = original
        self.e.gm.set_ability(self.t, "부유", reason="Gravity suppresses this Ground immunity")
        self.assertGreater(self.e.roll_damage(
            self.a, self.t, self.r.move("move/지진"), set_damage=True), 0)

    def test_magic_room_suspends_static_and_triggered_registration_but_restores_it(self):
        ITEMS.register_item(self.e, self.a, "선제공격손톱")
        self.assertEqual(self.a.initiative_bonus, 10)
        key, record = next(iter(self.a._item_reg.items()))
        self.assertIn(record["state_source"], self.a.spec["state_grants"]["sources"])
        held_before = deepcopy(self.a.spec["held_equipment"])
        self.install("move/매직룸")
        record = self.a._item_reg[key]
        self.assertEqual(self.a.initiative_bonus, 0)
        self.assertIn(ITEMS.MAGIC_ROOM_KEY, record)
        self.assertEqual(self.a.spec["held_equipment"], held_before)
        # The suspended registration survives JSON restore. Replacing the
        # field restores the passive from the same still-held item.
        blob = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        restored = Engine.import_state(self.r, blob)
        restored_a = next(actor for actor in restored.everyone
                          if actor.entity_id == self.a.entity_id)
        self.assertEqual(restored_a.initiative_bonus, 0)
        self.assertTrue(any(ITEMS.MAGIC_ROOM_KEY in row
                            for row in restored_a._item_reg.values()))
        FIELD.install(restored, restored_a, self.effect("move/원더룸"), "move/원더룸")
        self.assertEqual(restored_a.initiative_bonus, 10)
        self.assertFalse(any(ITEMS.MAGIC_ROOM_KEY in row
                             for row in restored_a._item_reg.values()))
        self.assertEqual(restored_a.spec["held_equipment"], held_before)

    def test_magic_room_suspends_weather_rock_creation_time_passive(self):
        ITEMS.register_item(self.e, self.a, "축축한바위")
        self.install("move/매직룸")
        self.e.start_of_turn(self.a, initiative_count=20)
        WEATHER.set_weather(self.e, "rain", rounds=5, source_id="move/비바라기",
                            origin="move", actor=self.a)
        self.assertEqual(self.e.weather_rounds, 5)
        self.assertNotIn("item_extension", self.e._weather_state["active"])
        self.install("move/원더룸")
        WEATHER.set_weather(self.e, "rain", rounds=5, source_id="move/비바라기",
                            origin="move", actor=self.a)
        self.assertEqual(self.e.weather_rounds, 7)
        self.assertEqual(self.e._weather_state["active"]["item_extension"]["added_rounds"], 2)

    def test_wonder_room_projects_both_damage_defense_and_evasion_stat(self):
        self.t.stats.update({"def": 999, "spd": 1, "spe": 1})
        tackle = self.r.move("move/몸통박치기")
        self.assertFalse(self.e.accuracy_check(self.a, self.t, tackle, fixed_roll=5)[0])
        self.assertEqual(self.e.roll_damage(self.a, self.t, tackle, set_damage=True), 1)
        self.install("move/원더룸")
        self.assertEqual(FIELD.defense_stat(self.e, self.t, "def"), "spd")
        self.assertEqual(FIELD.defense_stat(self.e, self.t, "spd"), "def")
        self.assertEqual(FIELD.evasion_class(self.e, self.t, "물리"), "특수")
        self.assertTrue(self.e.accuracy_check(self.a, self.t, tackle, fixed_roll=5)[0])
        self.assertGreater(self.e.roll_damage(self.a, self.t, tackle, set_damage=True), 1)
        trainer = type("TrainerProbe", (), {"kind": "trainer"})()
        self.assertEqual(FIELD.defense_stat(self.e, trainer, "def"), "def")

    def test_trick_room_starts_next_round_and_runs_five_complete_rounds(self):
        self.a.stats["spe"] = 20
        self.t.stats["spe"] = 5
        self.install("move/트릭룸")
        self.assertFalse(FIELD.initiative_ascending(self.e))
        self.assertEqual(INIT.order(self.e, [self.a, self.t]), [self.a, self.t])
        self.assertEqual(INIT.order(self.e, [self.a, self.t], round_no=self.e.round_no + 1), [self.t, self.a])
        self.e.start_round([self.a, self.t])
        self.assertTrue(FIELD.initiative_ascending(self.e))
        self.assertEqual(self.e.field["rounds"], 5)
        for remaining in (4, 3, 2, 1):
            self.e.start_round([self.a, self.t])
            self.assertEqual(self.e.field["rounds"], remaining)
        self.e.start_round([self.a, self.t])
        self.assertIsNone(self.e.field)

        scheduled = Engine(self.r, seed=729)
        fast = Combatant(self.r, build_pokemon(self.r, "피카츄", 30,
            moves=["move/트릭룸"], abilities=["정전기"]))
        slow = Combatant(self.r, build_pokemon(self.r, "이상해씨", 25,
            moves=["move/몸통박치기"], abilities=["심록"], side="wild"))
        fast.stats["spe"], slow.stats["spe"] = 20, 5
        scheduled.gm.add_combatant(fast)
        scheduled.gm.add_combatant(slow)
        scheduled.start_round([fast, slow])
        FIELD.install(scheduled, fast, self.effect("move/트릭룸"), "move/트릭룸")
        scheduled.end_round()
        status = scheduled.prepare_initiative_schedule(
            [fast, slow], source="move/트릭룸 direct schedule")
        self.assertEqual(status["status"], "prepared")
        self.assertEqual(scheduled._initiative_schedule["order"],
                         [slow.entity_id, fast.entity_id])


if __name__ == "__main__":
    unittest.main()
