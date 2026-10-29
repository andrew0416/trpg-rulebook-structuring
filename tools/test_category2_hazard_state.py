"""Direct source, producer, state, trigger, exchange, and lifetime tests for Hazards."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest


STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

import hazard_state as HAZARDS
import effects_ext as EXT
import condition_instances as CONDITION_INSTANCES
import items as ITEMS
import world_entities as WORLD
from engine import Combatant, Engine, Rules
from builder import build_pokemon
from grid import Grid


MOVES = {
    "C2CSV-MOVE-R0027": "move/끈적끈적네트",
    "C2CSV-MOVE-R0405": "move/압정뿌리기",
    "C2CSV-MOVE-R0462": "move/코트체인지",
    "C2CSV-MOVE-R0657": "move/독압정",
    "C2CSV-MOVE-R0751": "move/스텔스록",
}
INSTALL = tuple(move for move in MOVES.values() if move != "move/코트체인지")
CELLS8 = ((3, 1), (3, 2), (3, 3), (4, 1), (4, 2), (4, 3), (5, 1), (5, 2))
CELLS4 = ((3, 1), (3, 3), (5, 1), (5, 3))


class HazardStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def world(self, move_id="move/압정뿌리기", *, target_species="파이리"):
        e = Engine(self.r, seed=336337)
        e.grid = Grid(16, 16)
        moves = list(INSTALL) + ["move/코트체인지"]
        a = Combatant(self.r, build_pokemon(self.r, "피카츄", 30, moves=moves, abilities=["정전기"], side="party"))
        t = Combatant(self.r, build_pokemon(self.r, target_species, 25, moves=["move/몸통박치기"], abilities=["심록"], side="wild"))
        a.pos, t.pos = (2, 2), (12, 12)
        e.gm.add_combatant(a)
        e.gm.add_combatant(t)
        e.start_round([a, t])
        e.start_of_turn(a, initiative_count=20)
        return e, a, t

    def install(self, move_id, *, target_species="파이리"):
        e, a, t = self.world(move_id, target_species=target_species)
        aim = CELLS4 if move_id == "move/스텔스록" else CELLS8
        e.use_move_on(a, a, move_id, [a, t], aim=aim)
        return e, a, t

    def test_source_rows_core_scope_and_exact_runtime_adapter(self):
        selected = HAZARDS.policy(self.r)
        self.assertEqual(set(selected["moves"]), set(MOVES.values()))
        self.assertEqual(set(selected["core_clauses"]), {"C10-336", "C10-337"})
        status = json.loads((ROOT / "data/verification/category2-csv-abilities-moves-status.json").read_text(encoding="utf-8"))
        rows = {row["row_id"]: row for row in status["rows"] if row["row_id"] in MOVES}
        self.assertEqual(set(rows), set(MOVES))
        for clause, move_id in MOVES.items():
            with self.subTest(clause=clause):
                row = selected["moves"][move_id]
                self.assertEqual(row["source_row_sha256"], rows[clause]["source_row_sha256"])
                mm = self.r.move_mech(move_id)[0]
                if move_id in INSTALL:
                    self.assertTrue(mm.get("_native_hazard_activation"))
                    self.assertEqual(len(HAZARDS.field_effects(mm)), 1)
                else:
                    self.assertFalse(HAZARDS.field_effects(mm))

    def test_all_four_actual_producers_geometry_overlap_and_pre_spend_rejection(self):
        for move_id in INSTALL:
            with self.subTest(move=move_id):
                e, a, t = self.install(move_id)
                expected = 4 if move_id == "move/스텔스록" else 8
                instances = [row for envelope in e.hazards.values() for row in envelope["instances"]]
                self.assertEqual(len(instances), expected)
                self.assertEqual({row["source_id"] for row in instances}, {move_id})
                self.assertEqual(len({row["region_id"] for row in instances}), 1)
                self.assertTrue(all(row["owner_actor_id"] == a.entity_id and row["owner_side"] == "party" for row in instances))
        e, a, t = self.world()
        before = (deepcopy(a.budget), deepcopy(a.move_uses), e._hazard_sequence, deepcopy(e.hazards))
        with self.assertRaisesRegex(ValueError, "exactly 8 distinct cells"):
            e.use_move_on(a, a, "move/압정뿌리기", [a, t], aim=CELLS8[:-1])
        self.assertEqual((a.budget, a.move_uses, e._hazard_sequence, e.hazards), before)

        e, a, t = self.install("move/압정뿌리기")
        effect = self.r.move_mech("move/독압정")[0]["effects_exec"][0]
        HAZARDS.install(e, a, effect, {"source_id": "move/독압정", "move": {"id": "move/독압정", "_hazard_cells": CELLS8}})
        self.assertEqual(len(e.hazards[CELLS8[0]]["instances"]), 2)
        self.assertEqual({row["kind"] for row in e.hazards[CELLS8[0]]["instances"]}, {"spikes", "toxic_spikes"})

    def test_sticky_web_spikes_immunity_boots_and_timed_slow(self):
        e, a, t = self.install("move/끈적끈적네트")
        cell = CELLS8[0]
        EXT.on_enter_cell(e, t, cell)
        self.assertEqual(t.stages["spe"], -1)
        self.assertIn("둔화", t.conditions)
        self.assertTrue(t.custom_conditions.get("combat_timed_effects"))

        bug = Combatant(self.r, build_pokemon(self.r, "캐터피", 10, moves=["move/몸통박치기"], abilities=["인분"], side="wild"))
        bug.pos = (10, 10)
        e.gm.add_combatant(bug)
        EXT.on_enter_cell(e, bug, cell)
        self.assertFalse(any(row["kind"] == "sticky_web" for row in e.hazards.get(cell, {}).get("instances", [])))

        e, a, t = self.install("move/압정뿌리기")
        cell = CELLS8[0]
        before = t.hp
        EXT.on_enter_cell(e, t, cell)
        self.assertEqual(before - t.hp, t.max_hp // 10)
        self.assertIn("둔화", t.conditions)
        WORLD.register_object(e,"hazard-test/boots",kind="item_instance",item_rule_id="item/통굽부츠",
                              owner_id=t.entity_id,location={"kind":"unknown"},reason="Hazard direct fixture")
        ITEMS.register_item(e,t,"item/통굽부츠",source_instance_id="hazard-test/boots",as_held=True)
        before = t.hp
        EXT.on_enter_cell(e, t, CELLS8[1])
        self.assertEqual(t.hp, before)

    def test_toxic_spikes_layers_poison_destroy_and_persistent_lifetime(self):
        e, a, t = self.install("move/독압정")
        effect = self.r.move_mech("move/독압정")[0]["effects_exec"][0]
        HAZARDS.install(e, a, effect, {"source_id": "move/독압정", "move": {"id": "move/독압정", "_hazard_cells": CELLS8}})
        cell = CELLS8[0]
        EXT.on_enter_cell(e, t, cell)
        self.assertIn("독", t.conditions)
        self.assertEqual(CONDITION_INSTANCES.records(t, "독")[0]["effect"]["variant"], "맹독")
        self.assertEqual(len(e.hazards[cell]["instances"]), 2)

        poison = Combatant(self.r, build_pokemon(self.r, "이상해씨", 20, moves=["move/몸통박치기"], abilities=["심록"], side="wild"))
        poison.pos = (11, 11)
        e.gm.add_combatant(poison)
        EXT.on_enter_cell(e, poison, cell)
        self.assertNotIn(cell, e.hazards)
        self.assertNotIn(cell, e.grid.slow)

    def test_stealth_rock_proximity_typed_damage_physical_consumption_and_recall(self):
        e, a, t = self.install("move/스텔스록")
        before = t.hp
        EXT.on_enter_cell(e, t, (3, 2))
        expected = int(e.tick(t) * e.type_multiplier("바위", t)[0])
        self.assertEqual(before - t.hp, expected)
        self.assertEqual(sum(len(x["instances"]) for x in e.hazards.values()), 3)
        after = t.hp
        EXT.on_enter_cell(e, t, (5, 2))
        self.assertEqual(t.hp, after)
        HAZARDS.on_recall(t)
        EXT.on_enter_cell(e, t, (5, 2))
        self.assertLess(t.hp, after)
        self.assertEqual(sum(len(x["instances"]) for x in e.hazards.values()), 2)

    def test_court_change_identity_snapshot_tamper_and_encounter_cleanup(self):
        e, a, t = self.install("move/압정뿌리기")
        before = {(row["id"], row["region_id"], row["cell"], row["owner_actor_id"])
                  for env in e.hazards.values() for row in env["instances"]}
        # Court Change is a separate actual activation; refresh the actor turn.
        e.end_of_turn(a)
        e.start_round([a, t])
        e.start_of_turn(a, initiative_count=20)
        e.use_move_on(a, a, "move/코트체인지", [a, t])
        after = {(row["id"], row["region_id"], row["cell"], row["owner_actor_id"])
                 for env in e.hazards.values() for row in env["instances"]}
        self.assertEqual(after, before)
        self.assertEqual({row["owner_side"] for env in e.hazards.values() for row in env["instances"]}, {"wild"})

        blob = json.loads(json.dumps(e.export_state(), ensure_ascii=False))
        restored = Engine.import_state(self.r, blob)
        HAZARDS.validate_world(restored)
        first = next(row for env in restored.hazards.values() for row in env["instances"])
        first["source_row_sha256"] = "tampered"
        with self.assertRaisesRegex(ValueError, "source provenance"):
            HAZARDS.validate_world(restored)
        e.end_encounter([a, t])
        self.assertFalse(e.hazards)
        self.assertTrue(all(cell not in e.grid.slow for cell in CELLS8))


if __name__ == "__main__":
    unittest.main()
