"""Direct contracts for three CSV Moves backed by actual stage-change history."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import os
import sys
import unittest


HERE = Path(__file__).resolve()
STAGE = HERE.parents[1]
ROOT = Path(os.environ.get("PTK_EXPERIMENT_ROOT") or
            r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

# Cache every overlay module before engine.py promotes its canonical directory.
import stage_change_history as STAGES
import post_resolution_stage_effects as POST_STAGE
import conditional_damage_base as CONDITIONAL_DB
import action_lifecycle as _STAGED_ACTION_LIFECYCLE
import move_completion as _STAGED_MOVE_COMPLETION
import event_effects as _STAGED_EVENT_EFFECTS
import gm_state as _STAGED_GM_STATE
from engine import Rules, Engine, Combatant
from builder import build_trainer
from grid import Grid


class CSVStageHistoryMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")
        cls.alluring = "move/매혹의보이스"
        cls.jealousy = "move/질투의불꽃"
        cls.lash = "move/분풀이"
        cls.leer = "move/째려보기"

    def add(self, name, side, pos, moves=()):
        spec = build_trainer(
            self.r, name, 30,
            {key: 30 for key in ("hp", "atk", "def", "spa", "spd", "spe")},
            moves=list(moves), pos=pos, side=side, extra={"abilities": []})
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def setUp(self):
        self.e = Engine(self.r, seed=19057)
        self.e.grid = Grid(20, 20)
        self.user = self.add("stage-history user", "party", (2, 2),
            (self.alluring, self.jealousy, self.lash))
        self.foe = self.add("near enemy", "enemy", (3, 2), (self.leer,))
        self.other = self.add("other enemy", "enemy", (5, 2), (self.leer,))
        self.ally = self.add("near ally", "party", (4, 2))
        self.far = self.add("far enemy", "enemy", (12, 12))
        self.e.start_round(self.e.everyone)

    def start(self, actor):
        self.e.start_of_turn(actor, initiative_count=30)

    def close(self, actor):
        self.e.end_of_turn(actor)

    def next_round(self):
        self.e.end_round()
        self.e.start_round(self.e.everyone)

    def actual_damage(self, source, target, move_id, amount=7):
        with patch.object(self.e, "roll_damage", return_value=amount):
            return self.e.resolve_attack_damage(source, target, self.r.move(move_id))

    def use(self, actor, target, move_id, *, roll=10, damage=7, count_use=True):
        with patch.object(self.e, "d20", return_value=roll), \
             patch.object(self.e, "roll_damage", return_value=damage):
            return self.e.use_move(actor, target, move_id, count_use=count_use)

    def rise_on_turn(self, actor, stat="atk", amount=1):
        self.start(actor)
        self.e.change_stage(actor, stat, amount)
        self.close(actor)

    def test_exact_three_source_rows_and_policy_provenance(self):
        registry = json.loads((ROOT / "data/verification/category2-csv-abilities-moves-status.json")
                              .read_text(encoding="utf-8"))
        ids = {"C2CSV-MOVE-R0057", "C2CSV-MOVE-R0148", "C2CSV-MOVE-R0237"}
        rows = {row["row_id"]: row for row in registry["rows"] if row["row_id"] in ids}
        self.assertEqual(set(rows), ids)
        post = POST_STAGE.policy(self.r)
        self.assertEqual({row["clause_id"] for row in post["moves"].values()}, ids - {"C2CSV-MOVE-R0057"})
        conditional = CONDITIONAL_DB.policy(self.r.move(self.lash))
        self.assertEqual(conditional["clause_id"], "C2CSV-MOVE-R0057")
        for row in post["moves"].values():
            self.assertEqual(row["source_row_sha256"], rows[row["clause_id"]]["source_row_sha256"])
        self.assertEqual(conditional["source_row_sha256"], rows["C2CSV-MOVE-R0057"]["source_row_sha256"])

    def test_turn_windows_record_only_committed_changes_and_keep_event_history(self):
        self.start(self.foe)
        self.foe.stages["atk"] = 5
        self.e.change_stage(self.foe, "atk", 3)
        first = STAGES.rises_since_turn_start(self.foe)
        self.assertEqual([(row["before"], row["after"], row["actual_delta"])
                          for row in first], [(5, 6, 1)])
        self.e.change_stage(self.foe, "atk", 1)
        self.assertEqual(STAGES.rises_since_turn_start(self.foe), first)
        self.e.change_stage(self.foe, "atk", -2)
        self.assertEqual(STAGES.rises_since_turn_start(self.foe), first)
        self.close(self.foe)
        self.assertTrue(STAGES.rises_since_turn_start(self.foe))
        self.e.end_scene(self.e.everyone)
        self.assertEqual(STAGES.rises_since_turn_start(self.foe), [])

    def test_alluring_voice_uses_actual_history_for_every_near_enemy_only(self):
        self.rise_on_turn(self.foe)
        self.rise_on_turn(self.other, stat="spe")
        self.rise_on_turn(self.ally)
        self.rise_on_turn(self.far)
        self.start(self.user)
        self.e.gm.choose_post_resolution_stage_effect(
            self.user, self.alluring, reason="player invokes the optional post-resolution effect")
        self.use(self.user, self.foe, self.alluring, damage=0)
        self.assertIn("혼란", self.foe.conditions)
        self.assertIn("혼란", self.other.conditions)
        self.assertNotIn("혼란", self.ally.conditions)
        self.assertNotIn("혼란", self.far.conditions)
        record = self.user.spec[POST_STAGE.KEY]["history"][0]
        self.assertEqual(set(record["use"]["eligible_target_ids"]),
                         {self.foe.entity_id, self.other.entity_id})
        self.assertEqual(set(record["use"]["stage_event_ids"]),
                         {self.foe.entity_id, self.other.entity_id})
        self.assertTrue(record["use"]["completion_id"].startswith("move-complete:"))

    def test_no_choice_or_current_positive_snapshot_does_not_invent_eligibility(self):
        self.foe.stages["atk"] = 3
        self.start(self.user)
        self.use(self.user, self.foe, self.alluring, damage=0)
        self.assertNotIn("혼란", self.foe.conditions)
        self.assertNotIn(POST_STAGE.KEY, self.user.spec)

    def test_empty_eligible_set_keeps_choice_pending_until_later_activation(self):
        self.start(self.user)
        self.e.gm.choose_post_resolution_stage_effect(
            self.user, self.alluring, reason="retain the option until a qualifying rise exists")
        self.use(self.user, self.foe, self.alluring, damage=0)
        self.assertIsNone(self.user.spec[POST_STAGE.KEY]["history"][0]["use"])
        self.close(self.user)
        self.start(self.foe)
        self.e.change_stage(self.foe, "atk", 1)
        self.close(self.foe)
        self.next_round()
        self.start(self.user)
        self.close(self.user)
        self.next_round()
        self.start(self.user)
        self.use(self.user, self.foe, self.alluring, damage=0)
        self.assertIn("혼란", self.foe.conditions)
        self.assertIsNotNone(self.user.spec[POST_STAGE.KEY]["history"][0]["use"])

    def test_burning_jealousy_is_independent_and_applies_after_a_real_miss(self):
        self.rise_on_turn(self.foe)
        self.start(self.user)
        self.e.gm.choose_post_resolution_stage_effect(
            self.user, self.alluring, reason="first independent Move choice")
        self.e.gm.choose_post_resolution_stage_effect(
            self.user, self.jealousy, reason="second independent Move choice")
        self.use(self.user, self.foe, self.jealousy, roll=1)
        self.assertIn("화상", self.foe.conditions)
        records = self.user.spec[POST_STAGE.KEY]["history"]
        by_move = {record["move_id"]: record for record in records}
        self.assertIsNone(by_move[self.alluring]["use"])
        self.assertIsNotNone(by_move[self.jealousy]["use"])
        with self.assertRaisesRegex(ValueError, "already selected or used"):
            self.e.gm.choose_post_resolution_stage_effect(
                self.user, self.jealousy, reason="illegal duplicate selection")

    def test_lash_out_reads_external_loss_and_consumes_each_target_independently(self):
        self.start(self.user)
        self.close(self.user)
        self.start(self.foe)
        self.use(self.foe, self.user, self.leer)
        self.close(self.foe)
        losses = STAGES.losses_since_turn_end(self.user, external_only=True)
        self.assertEqual(len(losses), 1)
        self.assertEqual(losses[0]["source_actor_id"], self.foe.entity_id)
        self.assertEqual(losses[0]["source_id"], self.leer)
        self.next_round()
        self.start(self.user)
        move = self.r.move(self.lash)
        self.assertEqual(self.e.damage_base(self.user, move, target=self.foe), 15)
        self.assertEqual(self.e.damage_base(self.user, move, target=self.other), 15)
        self.actual_damage(self.user, self.foe, self.lash)
        self.assertEqual(self.e.damage_base(self.user, move, target=self.foe), 8)
        self.assertEqual(self.e.damage_base(self.user, move, target=self.other), 15)
        self.actual_damage(self.user, self.other, self.lash)
        self.assertEqual(self.e.damage_base(self.user, move, target=self.other), 8)

    def test_lash_out_rejects_self_source_and_scene_expired_evidence(self):
        self.start(self.user)
        self.close(self.user)
        self.next_round()
        self.start(self.user)
        self.e._inflictor = self.user
        try:
            self.e.change_stage(self.user, "def", -1)
        finally:
            del self.e._inflictor
        self.assertTrue(STAGES.losses_since_turn_end(self.user))
        self.assertEqual(STAGES.losses_since_turn_end(self.user, external_only=True), [])
        self.assertEqual(self.e.damage_base(self.user, self.r.move(self.lash), target=self.foe), 8)
        self.e.end_scene(self.e.everyone)
        self.assertEqual(STAGES.losses_since_turn_end(self.user), [])

    def test_json_restore_preserves_pending_choice_and_history_and_rejects_tamper(self):
        self.rise_on_turn(self.foe)
        self.start(self.user)
        self.e.gm.choose_post_resolution_stage_effect(
            self.user, self.alluring, reason="durable pending optional effect")
        blob = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        restored = Engine.import_state(self.r, blob)
        actors = {actor.entity_id: actor for actor in restored.everyone}
        restored_user = actors[self.user.entity_id]
        restored_foe = actors[self.foe.entity_id]
        self.assertTrue(restored.validate_state()["valid"], restored.validate_state())
        self.assertTrue(STAGES.rises_since_turn_start(restored_foe))
        self.assertIsNone(restored_user.spec[POST_STAGE.KEY]["history"][0]["use"])
        restored_user.spec[POST_STAGE.KEY]["history"][0]["source_row_sha256"] = "tampered"
        self.assertFalse(restored.validate_state()["valid"])

    def test_invalid_selection_and_failed_stage_change_are_atomic(self):
        self.start(self.user)
        before = deepcopy(self.user.spec)
        with self.assertRaisesRegex(ValueError, "selection reason required"):
            self.e.gm.choose_post_resolution_stage_effect(self.user, self.alluring, reason="")
        self.assertEqual(self.user.spec, before)
        stranger = self.add("unqualified stranger", "party", (1, 2), ())
        stranger_before = deepcopy(stranger.spec)
        with self.assertRaisesRegex(ValueError, "currently know"):
            self.e.gm.choose_post_resolution_stage_effect(
                stranger, self.alluring, reason="does not know the Move")
        self.assertEqual(stranger.spec, stranger_before)
        history_before = deepcopy(STAGES.rises_since_turn_start(self.user))
        self.user.stages["atk"] = 6
        self.e.change_stage(self.user, "atk", 1)
        self.assertEqual(STAGES.rises_since_turn_start(self.user), history_before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
