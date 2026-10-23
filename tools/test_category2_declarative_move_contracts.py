"""Direct producer/consumer/lifetime checks for ten reviewed Move clauses."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import csv
import hashlib
import json
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

# Pin every replaced import before engine.py imports the canonical module path.
import declarative_move_contracts as DMC
import alternate_move_modes as ALTERNATE
import effects as _EFFECTS
import event_effects as _EVENTS
import effects_ext as _EXT
import effect_instances as _INSTANCES
import combat_state_lifecycle as COMBAT_STATE
import gm_state as _GM_STATE
from engine import Rules, Engine, Combatant
from builder import build_pokemon
from grid import Grid


IDS = {
    "C2CSV-MOVE-R0069", "C2CSV-MOVE-R0627", "C2CSV-MOVE-R0129",
    "C2CSV-MOVE-R0757", "C2CSV-MOVE-R0517", "C2CSV-MOVE-R0490",
    "C2CSV-MOVE-R0719", "C2CSV-MOVE-R0370", "C2CSV-MOVE-R0554",
    "C2CSV-MOVE-R0673",
}


class DeclarativeMoveContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def battle(self, user_moves, target_moves=("move/몸통박치기",), *, species="이상해씨", target_species="꼬부기"):
        e = Engine(self.r, seed=10690627)
        e.grid = Grid(30, 30)
        user = Combatant(self.r, build_pokemon(self.r, species, 30, moves=list(user_moves), abilities=["심록"]))
        target = Combatant(self.r, build_pokemon(self.r, target_species, 30, moves=list(target_moves), abilities=["급류"], side="wild"))
        user.pos = (1, 1); target.pos = (2, 1)
        e.gm.add_combatant(user); e.gm.add_combatant(target)
        e.start_round([user, target]); e.start_of_turn(user, initiative_count=20)
        return e, user, target

    def test_policy_anchors_exact_rows_and_only_exact_mechanics_are_admitted(self):
        policy = DMC.policy(self.r)
        self.assertEqual({row["clause_id"] for row in policy["moves"].values()}, IDS)
        with (ROOT / "input/db/moves.csv").open(encoding="utf-8-sig", newline="") as stream:
            records = list(csv.reader(stream))
        for source, row in policy["moves"].items():
            actual = hashlib.sha256(json.dumps(records[row["record"] - 1], ensure_ascii=False,
                                                separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(actual, row["source_row_sha256"], source)
            mechanics = self.r.move_mech(source)[0]
            if row["executor"] == DMC.NATIVE:
                self.assertEqual(mechanics["effects_exec"], [DMC.marker(source, row)])
            else:
                self.assertIsNotNone(ALTERNATE.definition(self.r, source))

    def test_catastropika_owns_both_statuses_until_actual_recall(self):
        e, user, target = self.battle(["move/카타스트로피"])
        e.d20 = lambda: 20
        e.use_move(user, target, "move/카타스트로피")
        self.assertTrue({"저주", "취약"} <= target.conditions)
        self.assertEqual(len(DMC.live(target, "statuses_until_switch")), 1)
        COMBAT_STATE.recall(e, target)
        self.assertFalse({"저주", "취약"} & target.conditions)
        self.assertEqual(DMC.history(target)[-1]["end"]["kind"], "switch")
        e.validate_state()

    def test_yawn_never_rolls_and_applies_sleep_at_target_next_turn_end(self):
        e, user, target = self.battle(["move/하품"])
        with patch.object(e, "d20", side_effect=AssertionError("Yawn must not roll accuracy")):
            e.use_move(user, target, "move/하품")
        self.assertNotIn("잠듦", target.conditions)
        e.end_of_turn(user); e.start_of_turn(target, initiative_count=10); e.end_of_turn(target)
        self.assertIn("잠듦", target.conditions)
        self.assertFalse(DMC.live(target, "delayed_status"))
        self.assertEqual(DMC.history(target)[-1]["end"]["kind"], "target_turn_end")
        e.validate_state()

    def test_plasma_fists_is_consumed_by_the_next_actual_normal_attack(self):
        e, user, target = self.battle(["move/플라스마피스트"], ["move/몸통박치기"])
        e.d20 = lambda: 20; e.use_move(user, target, "move/플라스마피스트")
        self.assertEqual(len(DMC.live(target, "next_normal_attack_type")), 1)
        e.end_of_turn(user); e.start_of_turn(target, initiative_count=10)
        observed = []; original = e.type_multiplier
        e.type_multiplier = lambda move_type, recipient: (observed.append(move_type) or original(move_type, recipient))
        e.use_move(target, user, "move/몸통박치기")
        self.assertIn("전기", observed)
        self.assertFalse(DMC.live(target, "next_normal_attack_type"))
        self.assertEqual(DMC.history(target)[-1]["end"]["kind"], "matching_move_activation")
        e.validate_state()

    def test_autotomize_weight_and_speed_share_one_encounter_lifetime(self):
        e, user, target = self.battle(["move/바디퍼지"], species="롱스톤")
        before_weight = user.weight_class; before_speed = user.stages["spe"]
        e.use_move(user, user, "move/바디퍼지")
        self.assertEqual(user.weight_class, max(1, before_weight - 1))
        self.assertEqual(user.stages["spe"], before_speed + (2 if before_weight > 1 else 0))
        self.assertEqual(len(DMC.live(user, "encounter_weight_and_stage")), 1)
        e.end_of_turn(user); e.end_encounter([user, target], round_elapsed_seconds=0)
        self.assertEqual(user.weight_class, before_weight)
        self.assertFalse(DMC.live(user, "encounter_weight_and_stage"))
        e.validate_state()

    def test_last_resort_gate_reads_only_authenticated_uses_since_switch(self):
        others = ["move/몸통박치기", "move/할퀴기", "move/물기", "move/박치기", "move/전광석화"]
        e, user, target = self.battle([*others, "move/비장의무기"], ["move/기충전"])
        self.assertIn("struggle", user.moves)
        before = deepcopy(user.move_uses)
        with self.assertRaisesRegex(ValueError, "not yet used"):
            e.use_move(user, target, "move/비장의무기")
        self.assertEqual(user.move_uses, before)
        for index, source in enumerate(others):
            e.d20 = lambda: 1
            e.use_move(user, target, source)
            e.end_of_turn(user); e.start_of_turn(target, initiative_count=10); e.end_of_turn(target)
            e.start_round([user, target]); e.start_of_turn(user, initiative_count=20)
        e.use_move(user, target, "move/비장의무기")
        self.assertIn("move/비장의무기", {row["move_id"] for row in DMC.state(user)["uses"]})
        e.end_of_turn(user)
        COMBAT_STATE.recall(e, user)
        self.assertEqual(DMC.state(user)["uses"], [])
        e.validate_state()

    def test_focus_energy_changes_the_real_critical_threshold_and_ends_on_recall(self):
        e, user, target = self.battle(["move/기충전", "move/몸통박치기"])
        e.use_move(user, user, "move/기충전")
        result = e.accuracy_check(user, target, self.r.move("move/몸통박치기"), fixed_roll=18)
        self.assertEqual(result, (True, 18, True))
        COMBAT_STATE.recall(e, user)
        self.assertFalse(DMC.live(user, "focus_until_switch"))
        e.validate_state()

    def test_rest_is_atomic_blocks_saves_and_cures_on_its_second_future_turn(self):
        e, user, target = self.battle(["move/잠자기"])
        user.hp = max(1, user.max_hp - 12); e.apply_status(user, "독", source="test")
        e.use_move(user, user, "move/잠자기")
        self.assertEqual(user.hp, user.max_hp); self.assertNotIn("독", user.conditions); self.assertIn("잠듦", user.conditions)
        e.end_of_turn(user); e.start_of_turn(target, initiative_count=10); e.end_of_turn(target)
        for number in (1, 2):
            e.start_round([user, target]); e.start_of_turn(user, initiative_count=20)
            self.assertIn("잠듦", user.conditions)
            e.end_of_turn(user)
            if number == 1: self.assertIn("잠듦", user.conditions)
            e.start_of_turn(target, initiative_count=10); e.end_of_turn(target)
        self.assertNotIn("잠듦", user.conditions)
        self.assertEqual(DMC.history(user)[-1]["end"]["kind"], "owner_second_turn_end")
        e.validate_state()

        blocked, sleeper, other = self.battle(["move/잠자기"])
        sleeper.abilities = ["불면"]
        sleeper.spec["abilities"] = ["불면"]
        before = (sleeper.hp, deepcopy(sleeper.move_uses), deepcopy(sleeper.spec))
        with self.assertRaisesRegex(ValueError, "Insomnia|Sleep"):
            blocked.use_move(sleeper, sleeper, "move/잠자기")
        self.assertEqual((sleeper.hp, sleeper.move_uses, sleeper.spec), before)

    def test_spicy_extract_choice_is_consumed_and_same_stat_cannot_repeat_in_scene(self):
        e, user, ally = self.battle(["move/하바네로엑기스"])
        ally.side = user.side
        receipt = e.gm.choose_declarative_move(user, ally, "move/하바네로엑기스", stat="atk", reason="player chose Attack")
        before = ally.stages["atk"]; e.use_move(user, ally, "move/하바네로엑기스")
        self.assertEqual(ally.stages["atk"], before + 3)
        self.assertEqual(next(row for row in DMC.state(user)["choices"] if row["id"] == receipt["id"])["status"], "used")
        with self.assertRaisesRegex(ValueError, "same Spicy Extract"):
            e.gm.choose_declarative_move(user, ally, "move/하바네로엑기스", stat="atk", reason="illegal repeat")
        e.validate_state()

    def test_reflect_type_uses_explicit_current_types_and_scene_revokes_its_grant(self):
        e, user, target = self.battle(["move/미러타입"])
        original = list(user.types); selected = target.types[0]
        e.gm.choose_declarative_move(user, target, "move/미러타입", own_type=user.types[0], target_type=selected,
                                      reason="player chose both source types")
        e.d20 = lambda: 20; e.use_move(user, target, "move/미러타입")
        self.assertIn(selected, user.types); self.assertEqual(len(DMC.live(user, "scene_type_replacement")), 1)
        e.end_of_turn(user); e.end_scene([user, target], round_elapsed_seconds=0)
        self.assertEqual(user.types, original); self.assertFalse(DMC.live(user, "scene_type_replacement"))
        e.validate_state()

    def test_freezing_glare_reuses_alternate_mode_and_preserves_natural_19_freeze(self):
        e, user, target = self.battle(["move/얼어붙는시선"])
        e.gm.choose_alternate_move_type(user, "move/얼어붙는시선", "얼음", reason="player chose the scene mode")
        observed = []; original = e.type_multiplier
        e.type_multiplier = lambda move_type, recipient: (observed.append(move_type) or original(move_type, recipient))
        e.d20 = lambda: 19; e.use_move(user, target, "move/얼어붙는시선")
        self.assertIn("얼음", observed); self.assertIn("얼음", target.conditions)
        self.assertEqual(ALTERNATE.status(user, "move/얼어붙는시선")[0]["status"], "used")
        e.validate_state()

    def test_snapshot_restore_and_provenance_tamper_rejection(self):
        e, user, target = self.battle(["move/기충전"])
        e.use_move(user, user, "move/기충전")
        e.gm.snapshot("declarative-focus"); e.gm.restore("declarative-focus")
        blob = json.loads(json.dumps(e.export_state(), ensure_ascii=False))
        restored = Engine.import_state(self.r, blob)
        restored.validate_state()
        actor = next(row for row in restored.everyone if row.entity_id == user.entity_id)
        actor.spec[DMC.KEY]["live"][0]["source_row_sha256"] = "tampered"
        with self.assertRaisesRegex(ValueError, "provenance changed"):
            import world_entities as WORLD
            DMC.validate_world(restored, WORLD.actor_index(restored))


if __name__ == "__main__":
    unittest.main()
