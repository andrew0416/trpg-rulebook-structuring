"""Completed source-owned Set-Up Move terrain and transit lifecycles."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import csv
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]

from engine import Rules, Engine, Combatant
from builder import build_trainer
from grid import Grid
from native_scenario_fixture import prepare_setup_move_scene
import movement_actions as MOVEMENT
import setup_move_state as SETUP
import state_codec as CODEC
import turn as TURN


GEOMANCY = "move/지오컨트롤"
FLY = "move/공중날기"
DIG = "move/구멍파기"
DIVE = "move/다이빙"
TACKLE = "move/몸통박치기"


class SetupMoveStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")

    def add(self, spec):
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def setUp(self):
        self.e, self.a, self.b = prepare_setup_move_scene(self.r)

    def next_turn(self):
        self.e.end_of_turn(self.a)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def test_exact_four_source_rows_and_four_deferred_resume_conditions(self):
        rows = SETUP.declarations(self.r)
        self.assertEqual([row["clause_id"] for row in rows], [
            "C2CSV-MOVE-R0162", "C2CSV-MOVE-R0287",
            "C2CSV-MOVE-R0386", "C2CSV-MOVE-R0801"])
        self.assertEqual([row["record"] for row in rows], [162, 287, 386, 801])
        deferred = SETUP.deferred(self.r)
        self.assertEqual([row["record"] for row in deferred], [195, 314, 320, 629])
        self.assertTrue(all(row["resume_when"].strip() for row in deferred))
        with (ROOT / "input/db/moves.csv").open(encoding="utf-8-sig", newline="") as stream:
            source_rows = list(csv.reader(stream))
        for row in rows:
            source = source_rows[row["record"] - 1]
            digest = hashlib.sha256(json.dumps(
                source, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(digest, row["source_row_sha256"])
            mechanics, _ = self.r.move_mech(row["move_id"])
            actual = [{k: v for k, v in effect.items() if not k.startswith("_")}
                      for effect in mechanics["effects_exec"]]
            self.assertEqual(actual, row["expected_effects"])

    def test_geomancy_selected_burst_rough_lock_and_native_resolution(self):
        selected = [(1, 1), (3, 3), (5, 2)]
        before = deepcopy((self.a.budget, self.a.stages, self.a.move_uses,
                           self.e.rng.getstate()))
        self.assertEqual(self.e.use_setup_move_on(
            self.a, self.a, GEOMANCY, self.e.everyone,
            setup_options={"terrain_cells": selected}), 0)
        self.assertEqual(before[1:], (self.a.stages, self.a.move_uses, self.e.rng.getstate()))
        self.assertTrue(set(selected) <= self.e.grid.rough)
        self.assertEqual(SETUP.pending(self.a)["rough_cells"], [list(row) for row in selected])
        self.assertFalse(TURN.movement_permission(self.e, self.a))
        self.assertEqual(self.a.budget["standard"], 0)
        self.assertFalse(self.a.move_uses)
        self.e.gm.snapshot("geomancy prepared")
        self.a.custom_conditions.clear()
        self.e.grid.rough.clear()
        self.e.gm.restore("geomancy prepared")
        self.next_turn()
        self.assertTrue(TURN.movement_permission(self.e, self.a))
        self.e.use_setup_move_on(self.a, self.a, GEOMANCY, self.e.everyone,
                                 setup_options={})
        self.assertEqual({key: self.a.stages[key] for key in ("spa", "spd", "spe")},
                         {"spa": 2, "spd": 2, "spe": 2})
        self.assertIsNone(SETUP.pending(self.a))
        self.assertIsNone(self.a.setup_move)
        self.assertEqual(self.a.move_uses[GEOMANCY], 1)
        self.assertTrue(set(selected) <= self.e.grid.rough)

    def test_fly_reuses_learned_sky_and_actual_paid_path_then_descends(self):
        self.assertEqual(MOVEMENT.capabilities(self.e, self.a)["sky"], 3)
        self.assertEqual(self.e.use_setup_move_on(
            self.a, self.b, FLY, self.e.everyone, setup_options={}), 0)
        self.assertEqual((self.a.pos, self.a.spec["_movement_altitude"], self.a.airborne),
                         ((2, 2), 25, True))
        self.assertFalse(TURN.movement_permission(self.e, self.a))
        payload = json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False))
        self.e = CODEC.load_engine(self.r, payload)
        by_id = {row.entity_id: row for row in self.e.everyone}
        self.a, self.b = by_id[self.a.entity_id], by_id[self.b.entity_id]
        self.next_turn()
        hp = self.b.hp
        path = [{"position": (3, 2), "altitude": 25},
                {"position": (4, 2), "altitude": 25}]
        with patch.object(self.e, "d20", return_value=10):
            self.e.use_setup_move_on(self.a, self.b, FLY, self.e.everyone,
                                     setup_options={"path": path})
        self.assertEqual((self.a.pos, self.a.spec["_movement_altitude"], self.a.airborne),
                         ((4, 2), 0, False))
        self.assertLess(self.b.hp, hp)
        self.assertIsNone(SETUP.pending(self.a))
        self.assertEqual(self.a.move_uses[FLY], 1)

    def test_dig_reuses_land_or_burrow_budget_surfaces_and_hits_burst(self):
        self.assertEqual(MOVEMENT.capabilities(self.e, self.a)["burrow"], 3)
        self.assertEqual(self.e.use_setup_move_on(
            self.a, self.b, DIG, self.e.everyone,
            setup_options={"diggable": True, "reason": "actual loose-earth origin"}), 0)
        self.assertTrue(self.a.spec["_burrow"]["underground"])
        self.assertEqual(self.a.spec["_burrow"]["depth_m"], 25)
        self.assertEqual(self.a.budget, {"standard": 0, "shift": 0, "swift": 0})
        self.next_turn()
        hp = self.b.hp
        with patch.object(self.e, "d20", return_value=10):
            self.e.use_setup_move_on(
                self.a, self.b, DIG, self.e.everyone,
                setup_options={"path": [(3, 2), (4, 2)], "diggable": True,
                               "reason": "observed continuous loose-earth path"})
        self.assertEqual(self.a.pos, (4, 2))
        self.assertFalse(self.a.spec["_burrow"]["underground"])
        self.assertLess(self.b.hp, hp)
        self.assertIsNone(SETUP.pending(self.a))
        self.assertEqual(self.a.move_uses[DIG], 1)
        self.assertEqual(self.e._burrow_tunnels[-1]["source"], DIG)

    def test_dive_depth_targetability_swim_path_burst_and_atomic_failure(self):
        self.e.observe_map_terrain(
            [(2, 2), (3, 2), (4, 2), (5, 2)], base="underwater",
            reason="observed continuous deep-water lane")
        before = deepcopy((self.a.custom_conditions, self.a.budget, self.a.pos,
                           self.e.rng.getstate(), self.e.grid.__dict__))
        with self.assertRaises(ValueError):
            self.e.use_setup_move_on(
                self.a, self.b, DIVE, self.e.everyone,
                setup_options={"water_depth_m": 9, "reason": "measured shallow water"})
        self.assertEqual((self.a.custom_conditions, self.a.budget, self.a.pos,
                          self.e.rng.getstate(), self.e.grid.__dict__), before)
        self.e.use_setup_move_on(
            self.a, self.b, DIVE, self.e.everyone,
            setup_options={"water_depth_m": 12, "reason": "measured twelve-metre water"})
        self.assertFalse(SETUP.targetable(self.a))
        target_budget = deepcopy(getattr(self.b, "budget", None))
        with self.assertRaisesRegex(ValueError, "cannot be targeted"):
            self.e.use_move_on(self.b, self.a, TACKLE, self.e.everyone)
        self.assertEqual(getattr(self.b, "budget", None), target_budget)
        self.next_turn()
        hp = self.b.hp
        with patch.object(self.e, "d20", return_value=10):
            self.e.use_setup_move_on(
                self.a, self.b, DIVE, self.e.everyone,
                setup_options={"path": [(3, 2), (4, 2)]})
        self.assertEqual(self.a.pos, (4, 2))
        self.assertTrue(SETUP.targetable(self.a))
        self.assertLess(self.b.hp, hp)
        self.assertEqual(self.a.move_uses[DIVE], 1)

    def test_direct_bypass_other_move_same_round_and_encounter_cleanup(self):
        before = deepcopy((self.a.budget, self.a.custom_conditions, self.e.rng.getstate()))
        with self.assertRaisesRegex(ValueError, "use_setup_move_on"):
            self.e.use_move(self.a, self.b, FLY)
        self.assertEqual((self.a.budget, self.a.custom_conditions, self.e.rng.getstate()), before)
        self.e.use_setup_move_on(
            self.a, self.b, DIG, self.e.everyone,
            setup_options={"diggable": True, "reason": "actual loose earth"})
        with self.assertRaisesRegex(ValueError, "must resolve"):
            self.e.use_move(self.a, self.b, TACKLE)
        self.e.end_encounter(self.e.everyone, round_elapsed_seconds=0)
        self.assertIsNone(SETUP.pending(self.a))
        self.assertFalse(self.a.spec["_burrow"]["underground"])
        self.assertIsNone(self.a.setup_move)


if __name__ == "__main__":
    unittest.main()
