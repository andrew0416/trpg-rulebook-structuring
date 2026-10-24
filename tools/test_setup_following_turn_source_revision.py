"""Following own-turn Set-Up readiness and real interruption consequences."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from engine import Rules, Engine
from native_scenario_fixture import prepare_setup_move_scene, assert_rejected_unchanged
import test_category2_native_setup_state as GENERIC
import setup_move_state as SETUP
import combat_state_lifecycle as COMBAT
import world_entities as WORLD

BLADE, BEAM = GENERIC.BLADE, GENERIC.BEAM
GEOMANCY, FLY, DIG, DIVE = ("move/지오컨트롤", "move/공중날기", "move/구멍파기", "move/다이빙")


class SetupFollowingTurnSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset="all")

    def generic(self, role="trainer"):
        case = GENERIC.NativeSetupStateTests()
        case.r = self.r
        case.fixture(role)
        return case.e, case.a, case.b

    def four(self):
        return prepare_setup_move_scene(self.r)

    def next_turn(self, e, actor):
        if e._active_turn_actor is actor:
            e.end_of_turn(actor)
        e.start_round(e.everyone)
        e.start_of_turn(actor, initiative_count=20)

    def prepare_options(self, e, actor, move):
        if move == GEOMANCY:
            return {"terrain_cells": [(1, 1), (3, 3)]}
        if move == DIG:
            return {"diggable": True, "reason": "actual loose-earth origin"}
        if move == DIVE:
            e.observe_map_terrain(
                [(2, 2), (3, 2), (4, 2), (5, 2), (3, 3)], base="underwater",
                reason="actual continuous twelve-meter water region")
            return {"water_depth_m": 12, "reason": "actual measured twelve-meter water"}
        return {}

    def prepare(self, e, actor, target, move):
        if move in (BLADE, BEAM):
            return e.use_move(actor, target, move)
        return e.use_setup_move_on(
            actor, actor if move == GEOMANCY else target, move, e.everyone,
            setup_options=self.prepare_options(e, actor, move))

    def restored(self, e, *actors):
        loaded = Engine.import_state(self.r, json.loads(json.dumps(e.export_state())))
        index = WORLD.actor_index(loaded)
        return loaded, *(index[actor.entity_id] for actor in actors)

    def test_generic_readiness_uses_next_own_turn_not_other_actor_turn_or_later_round(self):
        for role in ("trainer", "pokemon"):
            with self.subTest(role=role):
                e, a, b = self.generic(role)
                hp, rng = b.hp, e.rng.getstate()
                self.assertEqual(self.prepare(e, a, b, BLADE), 0)
                turn = deepcopy(a.custom_conditions[SETUP.TURN_STATE])
                self.assertEqual(turn["prepared_turn"], a.custom_conditions["combat_turn_serial"])
                self.assertEqual((b.hp, a.move_uses, e.rng.getstate()), (hp, {}, rng))
                e.end_of_turn(a)
                e.start_of_turn(b, initiative_count=10)
                e.end_of_turn(b)
                self.assertEqual(a.custom_conditions[SETUP.TURN_STATE], turn)
                self.next_turn(e, a)
                self.assertEqual(a.custom_conditions["combat_turn_serial"], turn["prepared_turn"] + 1)
                self.assertEqual(a.setup_move, BLADE)
                e.end_of_turn(a)
                self.assertIsNone(a.setup_move)
                self.assertNotIn(SETUP.TURN_STATE, a.custom_conditions)
                self.assertEqual((b.hp, a.move_uses, e.rng.getstate()), (hp, {}, rng))
                self.next_turn(e, a)
                stages = deepcopy(a.stages)
                self.assertEqual(self.prepare(e, a, b, BLADE), 0)
                self.assertEqual((b.hp, a.move_uses, e.rng.getstate()), (hp, {}, rng))
                self.assertEqual((a.stages["atk"], a.stages["spd"]),
                                 (stages["atk"] + 1, stages["spd"] + 1))
                self.assertEqual(a.budget["standard"], 0)
                self.next_turn(e, a)
                with patch.object(Engine, "d20", return_value=10):
                    self.assertGreater(e.use_move_on(a, b, BLADE, e.everyone, set_damage=True), 0)
                self.assertEqual(a.move_uses[BLADE], 1)
                self.assertIsNone(a.setup_move)
                self.assertNotIn(SETUP.TURN_STATE, a.custom_conditions)

    def test_all_four_unused_readiness_expires_without_fabricated_physical_exit(self):
        for move in (GEOMANCY, FLY, DIG, DIVE):
            with self.subTest(move=move):
                e, a, b = self.four()
                hp, rng, pos = b.hp, e.rng.getstate(), a.pos
                closures = len(e._turn_closures)
                self.assertEqual(self.prepare(e, a, b, move), 0)
                prepared = deepcopy(SETUP.pending(a))
                self.assertEqual(prepared["prepared_turn"], a.custom_conditions["combat_turn_serial"])
                ends = move in (DIG, DIVE)
                self.assertEqual(e._active_turn_actor is None, ends)
                self.assertEqual(len(e._turn_closures), closures + int(ends))
                self.assertEqual(a.setup_move, move)
                self.assertEqual(a.custom_conditions[SETUP.TURN_STATE]["prepared_turn"],
                                 prepared["prepared_turn"])
                self.assertEqual((b.hp, a.move_uses, a.pos, e.rng.getstate()), (hp, {}, pos, rng))
                self.next_turn(e, a)
                e.end_of_turn(a)
                self.assertIsNone(SETUP.pending(a))
                self.assertIsNone(a.setup_move)
                self.assertNotIn(SETUP.TURN_STATE, a.custom_conditions)
                self.assertEqual((b.hp, a.move_uses, a.pos, e.rng.getstate()), (hp, {}, pos, rng))
                if move == GEOMANCY:
                    self.assertTrue({tuple(cell) for cell in prepared["rough_cells"]} <= e.grid.rough)
                    self.assertEqual([a.stages[key] for key in ("spa", "spd", "spe")], [0, 0, 0])
                elif move == FLY:
                    self.assertEqual((a.spec["_movement_altitude"], a.airborne), (25, True))
                    self.next_turn(e, a)
                    e.aerial_move(a, a.pos, mode="sky", altitude=22,
                                  reason_text="actual paid controlled descent after cancelled Fly")
                    self.assertEqual((a.spec["_movement_altitude"], a.airborne, a.budget["shift"]), (22, True, 0))
                    self.assertEqual(a.move_uses, {})
                elif move == DIG:
                    self.assertEqual((a.spec["_burrow"]["underground"], a.spec["_burrow"]["depth_m"]), (True, 25))
                    self.next_turn(e, a)
                    e.burrow_move(a, [a.pos, (3, 2)], diggable=True, surface=True,
                                  reason_text="actual paid native surface exit after cancelled Dig")
                    self.assertFalse(a.spec["_burrow"]["underground"])
                    self.assertEqual((a.pos, a.budget["shift"], a.move_uses), ((3, 2), 0, {}))
                else:
                    self.assertTrue(a.custom_conditions[SETUP.EXIT_STATE]["submerged_observation"])
                    with self.assertRaisesRegex(ValueError, "actual GM Dive physical exit observation"):
                        SETUP.targetable(a, engine=e)
                    with self.assertRaisesRegex(ValueError, "actual GM Dive physical exit observation"):
                        SETUP.require_targetable(e, b, a, "move/몸통박치기")
                e.export_state()

    def test_both_restores_preserve_exact_following_turn_and_do_not_extend_unused_window(self):
        for move in (BLADE, GEOMANCY):
            for restore in ("gm", "json"):
                with self.subTest(move=move, restore=restore):
                    e, a, b = self.generic() if move == BLADE else self.four()
                    self.prepare(e, a, b, move)
                    self.next_turn(e, a)
                    due = deepcopy(a.custom_conditions[SETUP.TURN_STATE])
                    if restore == "gm":
                        e.gm.snapshot("actual-following-turn")
                        e.end_of_turn(a)
                        self.assertIsNone(a.setup_move)
                        e.gm.restore("actual-following-turn")
                    else:
                        e, a, b = self.restored(e, a, b)
                    self.assertEqual(a.custom_conditions[SETUP.TURN_STATE], due)
                    self.assertIs(e._active_turn_actor, a)
                    with patch.object(Engine, "d20", return_value=10):
                        if move == BLADE:
                            self.assertGreater(e.use_move_on(a, b, move, e.everyone, set_damage=True), 0)
                        else:
                            e.use_setup_move_on(a, a, move, e.everyone, setup_options={})
                            self.assertEqual([a.stages[key] for key in ("spa", "spd", "spe")], [2, 2, 2])
                    self.assertEqual(a.move_uses[move], 1)
                    self.assertIsNone(a.setup_move)
                    self.assertNotIn(SETUP.TURN_STATE, a.custom_conditions)

    def test_actual_recall_faint_and_encounter_end_cancel_generic_and_four_readiness(self):
        for move in (BLADE, GEOMANCY, FLY, DIG, DIVE):
            for event in ("recall", "faint", "encounter"):
                with self.subTest(move=move, event=event):
                    e, a, b = self.generic("pokemon")
                    if move not in a.moves:
                        if move in (FLY, DIG, DIVE):
                            e.gm.choose_learned_capability_policy(
                                a, move, "move_entry", reason="actual selected printed learned capability")
                        e.gm.set_move(a, move, reason="actual complete known Set-Up Move")
                    self.prepare(e, a, b, move)
                    self.assertEqual(a.setup_move, move)
                    hp, pos = b.hp, a.pos
                    if event == "recall":
                        COMBAT.recall(e, a)
                        self.assertFalse(a.on_field)
                    elif event == "faint":
                        e.take_damage(a, a.hp)
                        self.assertTrue(a.fainted)
                    else:
                        e.end_encounter(e.everyone, round_elapsed_seconds=0)
                        self.assertFalse(e.encounter_active)
                    self.assertIsNone(a.setup_move)
                    self.assertIsNone(SETUP.pending(a))
                    self.assertNotIn(SETUP.TURN_STATE, a.custom_conditions)
                    self.assertEqual((b.hp, a.pos, a.move_uses.get(move, 0)), (hp, pos, 0))
                    if move == FLY:
                        self.assertEqual((a.spec["_movement_altitude"], a.airborne), (25, True))
                    if move == DIG:
                        self.assertEqual((a.spec["_burrow"]["underground"], a.spec["_burrow"]["depth_m"]), (True, 25))
                    if move == DIVE:
                        self.assertEqual(SETUP.EXIT_STATE in a.custom_conditions, event != "recall")
                    loaded, actor = self.restored(e, a)
                    self.assertIsNone(actor.setup_move)
                    self.assertNotIn(SETUP.TURN_STATE, actor.custom_conditions)

        for move in (DIG, DIVE):
            with self.subTest(move=move, event="actual preparation end poison tick"):
                e, a, b = self.four()
                e.gm.set_hp(a, 1, reason="actual one-HP user before Set-Up preparation")
                e.apply_status(a, "독", source="condition/독")
                self.assertIn("독", a.conditions)
                tick = next(row for row in self.r.condition_effects("독")
                            if row.get("type") == "tick_damage" and row.get("when") == "end_of_turn")
                expected_hp = 1 - e.tick_loss(a, tick["ticks"])
                hp, rng, pos, closures = b.hp, e.rng.getstate(), a.pos, len(e._turn_closures)
                self.assertEqual(self.prepare(e, a, b, move), 0)
                self.assertEqual(a.hp, expected_hp)
                self.assertTrue(a.fainted)
                self.assertIn("기절", a.conditions)
                self.assertNotIn("독", a.conditions)
                self.assertIsNone(e._active_turn_actor)
                self.assertEqual(len(e._turn_closures), closures + 1)
                self.assertIsNone(a.setup_move)
                self.assertIsNone(SETUP.pending(a))
                self.assertNotIn(SETUP.TURN_STATE, a.custom_conditions)
                self.assertFalse(hasattr(e, "_setup_move_scopes"))
                self.assertEqual((b.hp, a.pos, a.move_uses, e.rng.getstate()), (hp, pos, {}, rng))
                if move == DIG:
                    self.assertEqual((a.spec["_burrow"]["underground"], a.spec["_burrow"]["depth_m"]),
                                     (True, 25))
                else:
                    self.assertEqual(a.custom_conditions[SETUP.EXIT_STATE]["reason"], "faint")
                loaded, actor = self.restored(e, a)
                self.assertEqual(actor.hp, expected_hp)
                self.assertTrue(actor.fainted)
                self.assertIsNone(actor.setup_move)

    def test_generic_preparation_cannot_cross_encounter_and_legacy_receipt_is_not_invented(self):
        e, a, b = self.generic()
        self.prepare(e, a, b, BLADE)
        e.end_encounter(e.everyone, round_elapsed_seconds=0)
        self.assertIsNone(a.setup_move)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        hp, rng = b.hp, e.rng.getstate()
        self.assertEqual(self.prepare(e, a, b, BLADE), 0)
        self.assertEqual((b.hp, a.move_uses, e.rng.getstate()), (hp, {}, rng))
        self.assertEqual(a.custom_conditions[SETUP.TURN_STATE]["prepared_turn"], a.custom_conditions["combat_turn_serial"])
        # Preserve a historical marker-only record through a real native save.
        # Its missing actual turn is never guessed from the load time.
        a.custom_conditions.pop(SETUP.TURN_STATE)
        e, a, b = self.restored(e, a, b)
        assert_rejected_unchanged(
            e, lambda: e.use_move(a, b, BLADE), reason_pattern="no actual own-turn receipt")
        self.next_turn(e, a)
        self.assertIsNone(a.setup_move)
        self.assertEqual(self.prepare(e, a, b, BLADE), 0)
        self.assertEqual((b.hp, a.move_uses), (hp, {}))

    def test_solar_beam_real_preparation_ends_own_turn_while_blade_and_sunny_skip_do_not(self):
        for move, sunny, ends in ((BEAM, False, True), (BLADE, False, False), (BEAM, True, False)):
            with self.subTest(move=move, sunny=sunny):
                e, a, b = self.generic()
                if sunny:
                    e.gm.set_weather("sunny", rounds=3, reason="actual Sunny weather")
                hp, closures = b.hp, len(e._turn_closures)
                with patch.object(Engine, "d20", return_value=10):
                    result = e.use_move_on(a, b, move, e.everyone, set_damage=True)
                self.assertEqual(e._active_turn_actor is None, ends)
                self.assertEqual(len(e._turn_closures), closures + int(ends))
                if sunny:
                    self.assertGreater(result, 0)
                    self.assertLess(b.hp, hp)
                    self.assertIsNone(a.setup_move)
                    self.assertNotIn(SETUP.TURN_STATE, a.custom_conditions)
                    self.assertEqual(a.move_uses[move], 1)
                else:
                    self.assertEqual((result, b.hp, a.move_uses), (0, hp, {}))
                    self.assertEqual(a.setup_move, move)
                    self.assertIn(SETUP.TURN_STATE, a.custom_conditions)
                    self.next_turn(e, a)
                    with patch.object(Engine, "d20", return_value=10):
                        self.assertGreater(e.use_move_on(a, b, move, e.everyone, set_damage=True), 0)
                    self.assertIs(e._active_turn_actor, a)
                    self.assertEqual(a.move_uses[move], 1)

    def test_expired_dive_requires_actual_scoped_exit_without_permanent_protection_or_travel(self):
        e, a, b = self.four()
        self.prepare(e, a, b, DIVE)
        self.next_turn(e, a)
        e.end_of_turn(a)
        observation = deepcopy(a.custom_conditions[SETUP.EXIT_STATE])
        e.gm.snapshot("pending-physical-dive-exit")
        e.observe_setup_move_exit(a, expected_state=observation, submerged=False,
                                  reason="first actual observed surfacing before checkpoint restoration")
        self.assertNotIn(SETUP.EXIT_STATE, a.custom_conditions)
        e.gm.restore("pending-physical-dive-exit")
        self.assertEqual(a.custom_conditions[SETUP.EXIT_STATE], observation)
        e, a, b = self.restored(e, a, b)
        self.assertEqual(a.custom_conditions[SETUP.EXIT_STATE], observation)
        for operation, message in (
                (lambda: e.observe_setup_move_exit(a, expected_state=observation, submerged=True,
                    reason="cannot infer continued protection"), "explicit observed Dive exit"),
                (lambda: e.observe_setup_move_exit(a, expected_state=dict(observation, water_depth_m=99),
                    submerged=False, reason="wrong actual physical observation"), "observation changed"),
                (lambda: e.use_move(b, a, "move/몸통박치기"), "actual GM Dive physical exit observation"),
                (lambda: e.use_setup_move_on(a, b, DIVE, e.everyone, setup_options={"path": []}),
                    "actual GM Dive physical exit observation")):
            assert_rejected_unchanged(e, operation, reason_pattern=message)
        before = deepcopy((a.pos, a.hp, a.budget, a.move_uses, b.hp, e.rng.getstate()))
        receipt = e.observe_setup_move_exit(
            a, expected_state=observation, submerged=False, reason="GM observed actual surfacing at the same location")
        self.assertFalse(receipt["submerged"])
        self.assertEqual(before, (a.pos, a.hp, a.budget, a.move_uses, b.hp, e.rng.getstate()))
        self.assertNotIn(SETUP.EXIT_STATE, a.custom_conditions)
        self.assertTrue(SETUP.targetable(a, engine=e))
        self.assertIsNone(a.setup_move)
        self.assertEqual(a.custom_conditions["setup_move_exit_history"][-1], receipt)
        assert_rejected_unchanged(e, lambda: e.observe_setup_move_exit(
            a, expected_state=observation, submerged=False, reason="same already-recorded exit"),
            reason_pattern="observation changed")


if __name__ == "__main__":
    unittest.main()
