"""Future Sight and Doom Desire through the shared delayed-attack producer."""
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]

from builder import build_trainer
from engine import Combatant, Engine, Rules
import frequency as FREQ
import move_completion as COMPLETE
import state_codec as CODEC


MOVES = ("move/미래예지", "move/파멸의소원")


class DelayedAttackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="core")

    def world(self, move_id):
        engine = Engine(self.rules, 674)

        def actor(name, side, stats, moves=()):
            value = Combatant(self.rules, build_trainer(
                self.rules, name, 30, stats, moves=list(moves), side=side,
                abilities=[], extra={"types": []}))
            engine.gm.add_combatant(value, reason="delayed attack fixture")
            return value

        attacker = actor("seer", "party",
            {"hp": 90, "atk": 15, "def": 15, "spa": 35, "spd": 15, "spe": 20},
            (move_id,))
        target = actor("target", "enemy",
            {"hp": 120, "atk": 10, "def": 10, "spa": 10, "spd": 5, "spe": 10})
        engine.start_round(engine.everyone)
        engine.start_of_turn(attacker, initiative_count=30)
        return engine, attacker, target

    def finish_target_turn(self, engine, attacker, target):
        engine.end_of_turn(attacker)
        engine.start_of_turn(target, initiative_count=20)
        before = target.hp
        with patch.object(Engine, "accuracy_check",
                          side_effect=AssertionError("delayed attack must not roll accuracy")):
            engine.end_of_turn(target)
        self.assertLess(target.hp, before)
        return before - target.hp

    def assert_live_queue(self, engine, attacker, target, move_id):
        self.assertEqual(len(engine.delayed), 1)
        queued = engine.delayed[0]
        self.assertIs(queued["attacker"], attacker)
        self.assertIs(queued["who"], target)
        self.assertEqual(queued["move_id"], move_id)
        completion = engine._move_completions[queued["completion_id"]]
        self.assertEqual(completion["phase"], "targets")
        self.assertEqual(completion["results"], {})
        return queued

    def next_attacker_turn(self, engine, attacker):
        engine.end_of_turn(attacker)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(attacker, initiative_count=30)

    def rejection_state(self, engine, attacker, target):
        delayed = [
            (row.get("kind"), row.get("src"), row.get("turns"),
             row.get("attacker").entity_id, row.get("who").entity_id,
             row.get("move_id"), row.get("completion_id"))
            for row in engine.delayed
        ]
        completions = {
            token: (row["actor"].entity_id,
                    tuple(value.entity_id for value in row["targets"]),
                    row["move_id"], tuple(row["started"]),
                    deepcopy(row["results"]), row["sealed"], row["phase"])
            for token, row in engine._move_completions.items()
        }
        actors = []
        for actor in (attacker, target):
            actors.append((actor.entity_id, actor.hp, actor.temp_hp, actor.fainted,
                           deepcopy(getattr(actor, "budget", None)),
                           deepcopy(actor.move_uses),
                           deepcopy(actor.spec.get("move_uses", {})), actor.last_move,
                           getattr(actor.last_target, "entity_id", None),
                           deepcopy(getattr(actor, "_action_history", None)),
                           deepcopy(actor.counters)))
        return deepcopy((engine.rng.getstate(), engine.round_no,
                         engine.elapsed_seconds, delayed, completions, actors,
                         getattr(engine._active_turn_actor, "entity_id", None)))

    def test_use_commit_consumes_action_and_scene_frequency_without_attack_roll(self):
        for move_id in MOVES:
            with self.subTest(move=move_id):
                engine, attacker, target = self.world(move_id)
                before = target.hp
                with patch.object(engine, "accuracy_check", wraps=engine.accuracy_check) as accuracy, \
                     patch.object(engine, "roll_damage", wraps=engine.roll_damage) as damage:
                    result = engine.use_move(attacker, target, move_id)
                self.assertEqual(result, 0)
                self.assertEqual(target.hp, before)
                self.assertEqual(accuracy.call_count, 0)
                self.assertEqual(damage.call_count, 0)
                self.assertEqual(attacker.budget["standard"], 0)
                self.assertEqual(FREQ.move_frequency(engine, move_id, attacker), ("scene", 2))
                self.assertEqual(attacker.move_uses[move_id], 1)
                self.assertEqual(attacker.spec["move_uses"][move_id], 1)
                self.assertEqual(attacker.last_move, move_id)
                self.assertIs(attacker.last_target, target)
                self.assert_live_queue(engine, attacker, target, move_id)

    def test_target_turn_end_hits_with_absent_fainted_user(self):
        for move_id in MOVES:
            with self.subTest(move=move_id):
                engine, attacker, target = self.world(move_id)
                engine.use_move(attacker, target, move_id)
                engine.end_of_turn(attacker)
                engine.gm.recall(attacker, reason="verify off-field delayed hit")
                engine.gm.faint(attacker, reason="verify fainted delayed hit")
                engine.start_of_turn(target, initiative_count=20)
                before = target.hp
                with patch.object(Engine, "accuracy_check",
                                  side_effect=AssertionError("delayed attack must not roll accuracy")):
                    engine.end_of_turn(target)
                self.assertLess(target.hp, before)
                self.assertFalse(engine.delayed)
                row = list(engine._move_completions.values())[-1]
                self.assertEqual(row["phase"], "complete")
                self.assertEqual(row["results"][target.entity_id]["hit"], True)

    def test_gm_snapshot_restores_pending_queue_and_executes(self):
        for move_id in MOVES:
            with self.subTest(move=move_id):
                engine, attacker, target = self.world(move_id)
                engine.use_move(attacker, target, move_id)
                engine.gm.snapshot("queued")
                engine.delayed.clear()
                engine._move_completions.clear()
                engine.gm.restore("queued", reason="verify delayed queue restore")
                self.assert_live_queue(engine, attacker, target, move_id)
                self.assertGreater(self.finish_target_turn(engine, attacker, target), 0)
                self.assertFalse(engine.delayed)

    def test_json_roundtrip_preserves_pending_queue_and_executes(self):
        for move_id in MOVES:
            with self.subTest(move=move_id):
                engine, attacker, target = self.world(move_id)
                engine.use_move(attacker, target, move_id)
                payload = json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False))
                loaded = CODEC.load_engine(self.rules, payload)
                restored = {actor.entity_id: actor for actor in loaded.everyone}
                restored_attacker = restored[attacker.entity_id]
                restored_target = restored[target.entity_id]
                self.assert_live_queue(loaded, restored_attacker, restored_target, move_id)
                self.assertGreater(self.finish_target_turn(
                    loaded, restored_attacker, restored_target), 0)
                self.assertFalse(loaded.delayed)

    def test_legacy_turn_end_roll_and_post_damage_failures_restore_exact_state(self):
        original_roll_damage = Engine.roll_damage
        original_finish_target = COMPLETE.finish_target
        for move_id in MOVES:
            for failure in ("roll_damage", "finish_target"):
                with self.subTest(move=move_id, failure=failure):
                    engine, attacker, target = self.world(move_id)
                    self.assertIsNone(getattr(engine, "_initiative_schedule", None))
                    engine.use_move(attacker, target, move_id)
                    completion_id = engine.delayed[0]["completion_id"]
                    engine.end_of_turn(attacker)
                    engine.start_of_turn(target, initiative_count=20)
                    before = CODEC.dump_engine(engine)

                    if failure == "roll_damage":
                        def fail_after_roll(staged, source, recipient, move, crit=False,
                                            set_damage=False, fixed_dice=None,
                                            _reaction_event=None,
                                            _precision_observation=None):
                            original_roll_damage(
                                staged, source, recipient, move, crit, set_damage,
                                fixed_dice, _reaction_event, _precision_observation)
                            recipient.hp -= 7
                            staged._move_completions[completion_id][
                                "phase"] = "interrupted"
                            raise RuntimeError("late delayed roll failure")
                        context = patch.object(Engine, "roll_damage", new=fail_after_roll)
                        message = "late delayed roll failure"
                    else:
                        def fail_after_finish(staged, token, source, recipient, **kwargs):
                            original_finish_target(
                                staged, token, source, recipient, **kwargs)
                            raise RuntimeError("late delayed completion failure")
                        context = patch.object(
                            COMPLETE, "finish_target", new=fail_after_finish)
                        message = "late delayed completion failure"

                    with context, self.assertRaisesRegex(RuntimeError, message):
                        engine.end_of_turn(target)
                    self.assertEqual(CODEC.dump_engine(engine), before)
                    self.assert_live_queue(engine, attacker, target, move_id)
                    old_hp = target.hp
                    engine.end_of_turn(target)
                    self.assertLess(target.hp, old_hp)
                    self.assertFalse(engine.delayed)

    def test_delayed_completion_link_rejects_missing_or_mismatched_save_state(self):
        mutations = {
            "missing": lambda engine, queued, row, attacker, target: queued.__setitem__(
                "completion_id", "move-complete:missing"),
            "actor": lambda engine, queued, row, attacker, target: queued.__setitem__(
                "attacker", target),
            "target": lambda engine, queued, row, attacker, target: queued.__setitem__(
                "who", attacker),
            "move": lambda engine, queued, row, attacker, target: queued.__setitem__(
                "move_id", "move/invalid-delayed-link"),
            "phase": lambda engine, queued, row, attacker, target: row.__setitem__(
                "phase", "interrupted"),
            "deleted": lambda engine, queued, row, attacker, target:
                engine.delayed.clear(),
            "duplicate": lambda engine, queued, row, attacker, target:
                engine.delayed.append(dict(queued)),
        }
        for mismatch, mutate in mutations.items():
            with self.subTest(mismatch=mismatch):
                engine, attacker, target = self.world(MOVES[0])
                engine.use_move(attacker, target, MOVES[0])
                queued = engine.delayed[0]
                row = engine._move_completions[queued["completion_id"]]
                mutate(engine, queued, row, attacker, target)
                report = engine.validate_state()
                self.assertFalse(report["valid"])
                self.assertTrue(any(
                    "delayed attack" in issue["message"]
                    for issue in report["issues"]), report)
                with self.assertRaisesRegex(
                        CODEC.StateCodecError, "world reference integrity"):
                    CODEC.dump_engine(engine)

    def test_each_move_allows_two_scene_uses_then_rejects_third_without_cost(self):
        for move_id in MOVES:
            with self.subTest(move=move_id):
                engine, attacker, target = self.world(move_id)
                self.assertEqual(engine.use_move(attacker, target, move_id), 0)
                self.next_attacker_turn(engine, attacker)
                self.next_attacker_turn(engine, attacker)
                self.assertEqual(engine.use_move(attacker, target, move_id), 0)
                self.assertEqual(attacker.move_uses[move_id], 2)
                self.assertEqual(len(engine.delayed), 2)
                self.next_attacker_turn(engine, attacker)
                self.next_attacker_turn(engine, attacker)
                before = self.rejection_state(engine, attacker, target)
                self.assertEqual(engine.use_move(attacker, target, move_id), 0)
                self.assertEqual(self.rejection_state(engine, attacker, target), before)
                self.assertEqual(attacker.budget["standard"], 1)
                self.assertEqual(attacker.move_uses[move_id], 2)
                self.assertEqual(len(engine.delayed), 2)


if __name__ == "__main__":
    unittest.main()
