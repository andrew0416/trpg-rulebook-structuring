"""Paid native cancellation settles its one frozen Battle performance."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE
sys.path[:0] = [str(STAGE / "engine"), str(STAGE / "tools"), str(ROOT / "engine"), str(ROOT / "tools")]

import test_battle_contest_pending as FIXTURE
import action_resources as RESOURCES
import battle_contest as BATTLE
import move_completion as COMPLETE
import state_codec as CODEC


class BattleContestCancellationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = FIXTURE.Rules(str(ROOT), ruleset="core")
        cls.contest_rules = FIXTURE.ContestRules(str(ROOT), ruleset="core")

    fixture = FIXTURE.BattleContestPendingTests.fixture
    state = FIXTURE.BattleContestPendingTests.state
    watch = FIXTURE.BattleContestPendingTests.watch
    pending = FIXTURE.BattleContestPendingTests.pending

    def test_paid_attacker_faint_cancellation_settles_once_restores_and_allows_next_performer(self):
        self.fixture(center=True)
        event_id, completion_id, plan = self.pending()
        target_hp = (self.t.hp, self.r.hp)
        opposing_voltage = {actor.entity_id: self.state()["pokemon"][actor.entity_id]["excitement"]
                            for actor in self.teams[1]}
        # Same real native cancellation setup as the existing independent test.
        self.a.hp = 0
        self.a.conditions.add("기절")
        self.e.deliver_passive_event(event_id)
        completion = self.e._move_completions[completion_id]
        event = self.e._passive_events[event_id]
        record = self.state()["performances"][completion_id]
        self.assertEqual(event["continuation_cancelled"], "actor_no_longer_eligible")
        self.assertNotIn(event_id, completion.get("native_returns", {}))
        self.assertTrue(completion["results"][self.t.entity_id]["cancelled"])
        self.assertEqual(completion["results"][self.t.entity_id]["dealt"], 0)
        self.assertEqual((self.t.hp, self.r.hp), target_hp)
        self.assertEqual(RESOURCES.pending(self.r), {})
        self.assertEqual(self.a.move_uses[FIXTURE.MOVE], 1)
        self.assertEqual(self.a._action_history, ["standard"])
        self.assertIsNone(self.e._passive_pending)
        self.assertTrue(record["appeal_committed"])
        self.assertTrue(record["native_complete"])
        self.assertEqual(record["plan"], plan)
        self.assertEqual(record["result"]["knockout_ids"], [])
        row = self.state()["pokemon"][self.a.entity_id]
        self.assertEqual(row["appeal"], plan["rows_after"][self.a.entity_id]["appeal"])
        self.assertEqual(row["excitement"], plan["rows_after"][self.a.entity_id]["excitement"])
        self.assertEqual(row["stat_dice"]["강인함"], plan["rows_before"][self.a.entity_id]["stat_dice"]["강인함"] - 1)
        self.assertEqual(self.state()["sides"][0]["intro_dice"]["강인함"], self.before_intro - 1)
        self.assertFalse(row["center_pending"])
        self.assertEqual(row["acted_rounds"], [self.state()["current_round"]])
        self.assertIn(self.a.entity_id, self.state()["sides"][0]["replacement_center_due"])
        self.assertEqual({actor.entity_id: self.state()["pokemon"][actor.entity_id]["excitement"]
                          for actor in self.teams[1]}, opposing_voltage)
        self.assertEqual(self.state()["performance_rng_state"], plan["rng_after"])
        self.assertEqual(len(self.state()["performance_log_lines"]), self.log_count_before + len(plan["logs"]))
        frozen = deepcopy(self.state())
        COMPLETE.refresh(self.e, completion_id)
        COMPLETE.refresh(self.e, completion_id)
        self.assertEqual(self.state(), frozen)

        ids = (self.a.entity_id, self.teams[0][1].entity_id, self.r.entity_id)
        self.e = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index = {actor.entity_id: actor for actor in self.e.everyone}
        attacker, teammate, target = [index[uid] for uid in ids]
        self.assertIs(self.e._move_completions[completion_id]["actor"], attacker)
        self.assertEqual(self.state(), frozen)
        self.assertEqual(self.state()["performances"][completion_id]["result"]["knockout_ids"], [])
        BATTLE.finish_turn(self.e, self.cid, attacker)
        BATTLE.start_turn(self.e, self.cid, teammate)
        outcome = BATTLE.perform_move(self.e, self.c, self.cid, teammate, target, FIXTURE.MOVE,
                                     combat_options={"set_damage": True, "situational": 100})
        self.assertTrue(outcome["appeal_committed"])
        self.assertEqual(attacker.move_uses[FIXTURE.MOVE], 1)
        self.assertTrue(all(row["appeal_committed"] for row in self.state()["performances"].values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
