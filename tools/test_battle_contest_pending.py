"""Native Battle Contest continuation through actual Pokemon Intercept."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

from builder import build_pokemon, build_trainer
from contest import ContestEngine, ContestRules
from engine import Combatant, Engine, Rules
from grid import Grid
from native_scenario_fixture import assert_rejected_unchanged
import battle_contest as BATTLE
import move_completion as COMPLETE
import passive_events as PASSIVE
import state_codec as CODEC


MOVE = "move/막치기"


class BattleContestPendingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")
        cls.contest_rules = ContestRules(str(ROOT), ruleset="core")

    def fixture(self, *, center=False, target_ko=False):
        self.e = Engine(self.rules, seed=530)
        self.e.grid = Grid(20, 20)
        self.c = ContestEngine(self.contest_rules, seed=8089)
        stats = dict(hp=12, atk=12, spa=10, spd=10, spe=10)
        stats["def"] = 10
        self.trainers, self.teams = [], []
        positions = (((2, 2), (2, 5), (12, 12)), ((3, 2), (3, 5), (13, 12)))
        for number in range(2):
            side = "opponent" if number == 0 else "party"
            trainer = Combatant(self.rules, build_trainer(self.rules, "same trainer name", 30, stats,
                skills={"협박": 6}, pos=(15, 14 + number), side=side))
            self.trainers.append(trainer)
            team = []
            for member in range(3):
                pokemon = Combatant(self.rules, build_pokemon(self.rules, "이상해씨", 30,
                    name="same Pokemon name", moves=[MOVE, "move/할퀴기"], abilities=[], side=side,
                    pos=positions[number][member], extra={"trainer_id": trainer.entity_id, "size": "중형"}))
                pokemon.stats["def"] = 20
                pokemon.stats["atk"] = 30
                pokemon.on_field = member < 2
                team.append(pokemon)
            self.teams.append(team)
        self.e.everyone = self.e.gm.everyone = [*self.trainers, *(p for team in self.teams for p in team)]
        for team in self.teams:
            for pokemon in team:
                self.e.gm.observe_loyalty(pokemon, 6, reason="actual Trainer and loyal Pokemon relationship")
        introductions = {trainer.entity_id: self.c.contestant_from_combatants(
            self.e, team[0], trainer, "협박", smart_stat_policy="ptu-original-special-defense")
            for trainer, team in zip(self.trainers, self.teams)}
        self.cid = "battle:actual-pending"
        BATTLE.create(self.e, self.c, self.trainers, self.teams,
            tuple(tuple(team[:2]) for team in self.teams), "근사함", introductions,
            contest_id=self.cid, format_size=2, smart_stat_policy="ptu-original-special-defense")
        self.a, self.t, self.r = self.teams[0][0], self.teams[1][0], self.teams[1][1]
        BATTLE.begin_round(self.e, self.cid)
        if center:
            self.a.hp = 1
            BATTLE.start_turn(self.e, self.cid, self.t)
            BATTLE.perform_move(self.e, self.c, self.cid, self.t, self.a, MOVE,
                                combat_options={"set_damage": True, "situational": 100})
            self.assertTrue(self.a.fainted)
            BATTLE.switch(self.e, self.cid, self.trainers[0], self.a, self.teams[0][2])
            BATTLE.finish_turn(self.e, self.cid, self.t)
            self.a = self.teams[0][2]
            self.assertTrue(self.state()["pokemon"][self.a.entity_id]["center_pending"])
        if target_ko:
            self.t.hp = 1
        self.e.rng.seed(530)
        BATTLE.start_turn(self.e, self.cid, self.a)
        self.assertGreaterEqual(self.state()["sides"][0]["intro_dice"]["강인함"], 1)

    def state(self):
        return BATTLE.validate(self.e, self.cid)[1]

    def watch(self):
        self.e.watch_move_defense(self.t, [{"actor_id": self.r.entity_id,
            "source": "maneuver/근접-가로채기"}], reason="actual loyalty-six Pokemon Intercept")

    def options(self, *, success=True):
        count = self.e._prepare_skill_roll(self.r, "육상")[-1]["dice_count"]
        return {"path": [(3, 5), (3, 4), (3, 3), (3, 2)], "skill": "육상", "mode": "land",
                "shove_destination": [4, 2], "roll_options": {"fixed": [6 if success else 1] * count}}

    def pending(self):
        self.watch()
        self.before_rows = deepcopy(self.state()["pokemon"])
        self.before_intro = self.state()["sides"][0]["intro_dice"]["강인함"]
        self.before_rng = self.c.rng.getstate()
        self.log_count_before = len(self.c.log_lines)
        with self.assertRaises(PASSIVE.PassiveEventPending):
            BATTLE.perform_move(self.e, self.c, self.cid, self.a, self.t, MOVE,
                spend_stat_dice=2, spend_intro_dice=1,
                combat_options={"set_damage": True, "situational": 100})
        event = self.e._passive_pending
        token = self.e._passive_events[event]["completion_id"]
        record = self.state()["performances"][token]
        self.assertFalse(record["appeal_committed"])
        self.assertEqual(self.state()["pokemon"], self.before_rows)
        self.assertEqual(self.state()["sides"][0]["intro_dice"]["강인함"], self.before_intro)
        self.assertNotEqual(record["plan"]["rng_after"], self.before_rng)
        self.assertEqual(self.c.rng.getstate(), record["plan"]["rng_after"])
        self.assertEqual(self.a.move_uses[MOVE], 1)
        self.assertEqual(self.a._action_history, ["standard"])
        return event, token, deepcopy(record["plan"])

    def choose(self, event, *, use=True, success=True):
        return self.e.choose_move_defense(event, self.r, use=use,
            options=self.options(success=success) if use else None, reason="actual pending defense answer")

    def assert_committed(self, token, plan, knocked_out):
        state = self.state()
        record = state["performances"][token]
        self.assertTrue(record["appeal_committed"])
        self.assertTrue(record["native_complete"])
        self.assertEqual(record["plan"], plan)
        self.assertEqual(state["performance_rng_state"], plan["rng_after"])
        self.assertEqual(len(state["performance_log_lines"]), self.log_count_before + len(plan["logs"]))
        self.assertEqual(record["result"]["knockout_ids"], [knocked_out.entity_id])
        self.assertEqual(state["pokemon"][self.a.entity_id]["stat_dice"]["강인함"],
                         plan["rows_before"][self.a.entity_id]["stat_dice"]["강인함"] - 1)
        self.assertEqual(state["sides"][0]["intro_dice"]["강인함"], self.before_intro - 1)
        self.assertEqual(state["pokemon"][self.a.entity_id]["appeal"], plan["rows_after"][self.a.entity_id]["appeal"])
        self.assertEqual(state["pokemon"][self.a.entity_id]["excitement"],
                         plan["rows_after"][self.a.entity_id]["excitement"] + 2)
        teammate = self.teams[0][1]
        self.assertEqual(state["pokemon"][teammate.entity_id]["excitement"],
                         plan["rows_before"][teammate.entity_id]["excitement"])
        self.assertIn(knocked_out.entity_id, state["sides"][1]["replacement_center_due"])
        self.assertEqual(state["pokemon"][self.a.entity_id]["acted_rounds"], [state["current_round"]])
        before = (deepcopy(state), self.e.export_state())
        COMPLETE.refresh(self.e, token)
        COMPLETE.refresh(self.e, token)
        self.assertEqual((self.state(), self.e.export_state()), before)
        BATTLE.finish_turn(self.e, self.cid, self.a)
        self.assertEqual(self.state()["pokemon"][teammate.entity_id]["excitement"],
                         plan["rows_before"][teammate.entity_id]["excitement"])

    def test_native_preflight_refusal_creates_no_performance_spend_or_rng_change(self):
        self.fixture()
        before = (self.c.rng.getstate(), list(self.c.log_lines))
        assert_rejected_unchanged(self.e, lambda: BATTLE.perform_move(
            self.e, self.c, self.cid, self.a, self.t, MOVE, spend_stat_dice=2, spend_intro_dice=1,
            combat_options={"versatile_stat": "atk"}), reason_pattern="Versatile keyword")
        self.assertEqual((self.c.rng.getstate(), self.c.log_lines), before)
        self.assertNotIn("performances", self.state())
        self.assertNotIn("performance_declaration", self.state())

    def test_synchronous_native_completion_spends_and_scores_once(self):
        self.fixture()
        before = self.state()["pokemon"][self.a.entity_id]["appeal"]
        receipt = BATTLE.perform_move(self.e, self.c, self.cid, self.a, self.t, MOVE,
            spend_stat_dice=2, spend_intro_dice=1, fixed_rolls=[6] * 7,
            combat_options={"set_damage": True, "situational": 100})
        self.assertTrue(receipt["appeal_committed"])
        self.assertEqual(self.state()["pokemon"][self.a.entity_id]["appeal"], before + 14)
        self.assertEqual(self.a.move_uses[MOVE], 1)
        self.assertEqual(self.a._action_history, ["standard"])
        saved = deepcopy(self.state())
        COMPLETE.refresh(self.e, receipt["completion_id"])
        self.assertEqual(self.state(), saved)

    def test_invalid_pending_answer_then_decline_keeps_original_roll_and_cost(self):
        self.fixture(target_ko=True)
        event, token, plan = self.pending()
        assert_rejected_unchanged(self.e, lambda: self.e.choose_move_defense(
            event, self.r, use="yes", reason="invalid answer"), reason_pattern="Boolean")
        assert_rejected_unchanged(self.e, lambda: BATTLE.perform_move(
            self.e, self.c, self.cid, self.a, self.t, MOVE), reason_pattern="actual pending")
        self.choose(event, use=False)
        self.assertTrue(self.t.fainted)
        self.assertFalse(self.r.fainted)
        self.assert_committed(token, plan, self.t)

    def test_failed_actual_intercept_credits_only_attackers_original_target_ko(self):
        self.fixture(target_ko=True)
        event, token, plan = self.pending()
        self.choose(event, success=False)
        self.assertTrue(self.t.fainted)
        self.assertFalse(self.r.fainted)
        self.assert_committed(token, plan, self.t)

    def test_successful_actual_intercept_credits_actual_recipient_once(self):
        self.fixture()
        self.r.hp = 1
        target_hp = self.t.hp
        event, token, plan = self.pending()
        self.choose(event)
        self.assertTrue(self.r.fainted)
        self.assertEqual(self.t.hp, target_hp)
        self.assert_committed(token, plan, self.r)

    def test_json_pending_restore_preserves_real_recipient_and_first_center_performance(self):
        self.fixture(center=True)
        self.r.hp = 1
        event, token, plan = self.pending()
        actor_ids = [self.a.entity_id, self.t.entity_id, self.r.entity_id]
        team_ids = [[actor.entity_id for actor in team] for team in self.teams]
        self.e = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index = {actor.entity_id: actor for actor in self.e.everyone}
        self.a, self.t, self.r = [index[uid] for uid in actor_ids]
        self.teams = [[index[uid] for uid in team] for team in team_ids]
        self.assertIs(self.e._move_completions[token]["actor"], self.a)
        self.assertEqual(self.state()["performance_rng_state"], plan["rng_after"])
        self.assertTrue(self.state()["pokemon"][self.a.entity_id]["center_pending"])
        self.assertTrue(any("[관심의 중심]" in line for line in plan["logs"]))
        self.choose(event)
        self.assertFalse(self.state()["pokemon"][self.a.entity_id]["center_pending"])
        self.assert_committed(token, plan, self.r)

    def test_saved_pending_choice_and_completion_binding_tampering_are_rejected(self):
        self.fixture()
        event, token, plan = self.pending()
        record = self.state()["performances"][token]
        assert_rejected_unchanged(self.e, lambda: BATTLE.complete_move(
            self.e, dict(self.e._move_completions[token])), reason_pattern="actual native Move completion")
        record["plan"]["spend_intro_dice"] = 0
        with self.assertRaises(CODEC.StateCodecError):
            CODEC.dump_engine(self.e)
        record["plan"]["spend_intro_dice"] = 1
        original = self.e._move_completions[token]["battle_contest"]["fingerprint"]
        self.e._move_completions[token]["battle_contest"]["fingerprint"] = "changed"
        with self.assertRaises(CODEC.StateCodecError):
            CODEC.dump_engine(self.e)
        self.e._move_completions[token]["battle_contest"]["fingerprint"] = original
        self.state()["performance_rng_state"] = plan["rng_before"]
        with self.assertRaises(CODEC.StateCodecError):
            CODEC.dump_engine(self.e)
        self.state()["performance_rng_state"] = plan["rng_after"]
        self.choose(event, use=False)
        self.assertEqual(self.state()["performances"][token]["plan"], plan)


if __name__ == "__main__":
    unittest.main(verbosity=2)
