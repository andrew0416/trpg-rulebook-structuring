"""Source boundaries absent from the frozen modes19 cases; native consumers only."""
from copy import deepcopy
import json
import unittest

from builder import build_pokemon, build_trainer
from contest import ContestEngine, ContestRules
from engine import Combatant, Engine, Rules
from grid import Grid
import battle_contest as BATTLE
import state_codec as CODEC
import test_category2_battle_contest as _fixture_test_category2_battle_contest


from test_category2_battle_contest import ROOT as SOURCE_ROOT, STATS


class Pause(Exception):
    pass


class BattleBoundaryTests(unittest.TestCase):
    fixture = _fixture_test_category2_battle_contest.BattleContestTests.fixture
    state = staticmethod(_fixture_test_category2_battle_contest.BattleContestTests.state)

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(SOURCE_ROOT), ruleset="core")
        cls.contest_rules = ContestRules(str(SOURCE_ROOT), ruleset="core")

    def test_all_roster_fainted_completes_early_and_appeal_can_make_the_defeated_side_win(self):
        engine, contest, trainers, teams, cid = self.fixture()
        BATTLE.begin_round(engine, cid)
        scorer, opponent = teams[1][0], teams[0][0]
        engine.start_of_turn(scorer)
        receipt = BATTLE.perform_move(
            engine, contest, cid, scorer, opponent, "move/보복",
            fixed_rolls=[6] * 6, combat_options={"set_damage": True})
        self.assertTrue(receipt["appeal_committed"])
        BATTLE.finish_turn(engine, cid, scorer)
        lead = BATTLE.result(engine, cid)["scores"]
        self.assertGreater(lead[1], lead[0])
        for reserve in teams[1][1:]:
            engine.lose_hp(reserve, reserve.hp, source="earlier native combat damage")
        scorer.hp = 1
        scorer.stats["def"] = 1
        engine.start_of_turn(opponent)
        receipt = BATTLE.perform_move(
            engine, contest, cid, opponent, scorer, "struggle",
            combat_options={"situational": 100, "set_damage": True})
        self.assertTrue(receipt["knockout"])
        self.assertFalse(receipt["appeal_committed"])
        self.assertTrue(all(p.fainted for p in teams[1]))
        final = receipt["result"]
        self.assertEqual((final["status"], final["completion_reason"],
                          final["rounds_completed"], final["winner_trainer_id"]),
                         ("complete", "all_pokemon_fainted", 0, trainers[1].entity_id))
        self.assertEqual(final["scores"], lead)
        BATTLE.finish_turn(engine, cid, opponent)
        with self.assertRaisesRegex(ValueError, "completed"):
            BATTLE.begin_round(engine, cid)
        restored = CODEC.load_engine(
            self.rules, json.loads(json.dumps(CODEC.dump_engine(engine))))
        self.assertEqual(BATTLE.result(restored, cid), final)

    def test_actual_struggle_and_trip_spend_combat_actions_without_appeal_or_dice(self):
        for action in ("struggle", "trip"):
            with self.subTest(action=action):
                engine, contest, trainers, teams, cid = self.fixture()
                actor, target = teams[0][0], teams[1][0]
                actor.pos, target.pos = (1, 1), (2, 1)
                actor.side, target.side = "party", "wild"
                if action == "trip":
                    engine.grid = Grid(12, 12)
                BATTLE.begin_round(engine, cid)
                engine.start_of_turn(actor)
                before = deepcopy(self.state(engine, cid)["pokemon"])
                rng, logs = contest.rng.getstate(), list(contest.log_lines)
                if action == "struggle":
                    hp = target.hp
                    receipt = BATTLE.perform_move(
                        engine, contest, cid, actor, target, action,
                        combat_options={"situational": 100, "set_damage": True})
                    self.assertFalse(receipt["appeal_committed"])
                    self.assertLess(target.hp, hp)
                else:
                    from skill_modifiers import rank
                    count_a = rank(self.rules, actor, "전투")[2]
                    count_b = rank(self.rules, target, "전투")[2]
                    self.assertTrue(engine.trip(
                        actor, target, challenger_skill="전투", defender_skill="전투",
                        fixed_accuracy=20,
                        challenger_options={"fixed": [6] * count_a},
                        defender_options={"fixed": [1] * count_b}))
                    self.assertIn("넘어짐", target.conditions)
                self.assertEqual(actor.budget["standard"], 0)
                self.assertEqual(self.state(engine, cid)["pokemon"], before)
                self.assertEqual(contest.rng.getstate(), rng)
                self.assertEqual(contest.log_lines, logs)

    def test_replacement_center_fumble_reduces_final_score_and_reverses_the_raw_appeal_leader(self):
        engine, contest, trainers, teams, cid = self.fixture()
        BATTLE.begin_round(engine, cid)
        actor, target, replacement = teams[0][0], teams[1][0], teams[1][1]
        target.hp, target.stats["def"] = 1, 1
        engine.start_of_turn(actor)
        receipt = BATTLE.perform_move(
            engine, contest, cid, actor, target, "move/보복",
            fixed_rolls=[6, 6, 2, 2, 2, 1],
            combat_options={"situational": 100, "set_damage": True})
        self.assertTrue(receipt["knockout"])
        BATTLE.finish_turn(engine, cid, actor)
        BATTLE.switch(engine, cid, trainers[1], target, replacement)
        self.assertTrue(self.state(engine, cid)["pokemon"][replacement.entity_id]["center_pending"])
        engine.start_of_turn(replacement)
        receipt = BATTLE.perform_move(
            engine, contest, cid, replacement, actor, "move/보복",
            fixed_rolls=[6, 6, 4, 1, 1, 2],
            combat_options={"situational": 100, "set_damage": True})
        self.assertTrue(receipt["appeal_committed"])
        self.assertFalse(receipt["knockout"])
        BATTLE.finish_turn(engine, cid, replacement)
        state = self.state(engine, cid)
        self.assertEqual((state["pokemon"][actor.entity_id]["appeal"],
                          state["pokemon"][replacement.entity_id]["appeal"],
                          state["pokemon"][replacement.entity_id]["fumble"]), (7, 8, 2))
        current_scores = BATTLE.result(engine, cid)["scores"]
        BATTLE.finish_round(engine, cid)
        for _ in range(5):
            BATTLE.begin_round(engine, cid)
            BATTLE.finish_round(engine, cid)
        final = BATTLE.result(engine, cid)
        self.assertEqual((final["scores"], final["winner_trainer_id"],
                          final["completion_reason"]),
                         ([7, 6], trainers[0].entity_id, "round_limit"))
        self.assertEqual(current_scores, [7, 6])
        self.assertEqual(self.state(engine, cid)["scores"], [7, 6])
        self.assertEqual(self.state(engine, cid)["pokemon"][replacement.entity_id]["appeal"], 8)
        restored = CODEC.load_engine(
            self.rules, json.loads(json.dumps(CODEC.dump_engine(engine))))
        self.assertEqual(BATTLE.result(restored, cid), final)


class RotationNativeBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(SOURCE_ROOT), ruleset="core")
        cls.contest_rules = ContestRules(str(SOURCE_ROOT), ruleset="core")

    def fixture(self, mode="team"):
        native = Engine(self.rules, seed=8600)
        contest = ContestEngine(self.contest_rules, seed=8800)
        teams, trainers, pokemon = [], [], []
        stats = {s: 12 for s in ("근사함", "귀여움", "슬기로움", "아름다움", "강인함")}
        for team_number in range(3):
            owner_count = {"solo": 1, "team": 3, "mixed": 2}[mode]
            owners = [Combatant(self.rules, build_trainer(
                self.rules, f"owner-{team_number}-{member}", 30, STATS,
                skills={"매력": 2 + member})) for member in range(owner_count)]
            trainers.extend(owners)
            members = []
            for member in range(3):
                owner = owners[min(member, owner_count - 1)]
                p = Combatant(self.rules, build_pokemon(
                    self.rules, "이상해씨", 30, f"native-{team_number}-{member}",
                    abilities=[], moves=["연속자르기", "꼬리흔들기", "회복지령"]))
                p.spec["trainer_id"] = owner.entity_id
                pokemon.append(p)
                native.everyone = native.gm.everyone = [*trainers, *pokemon]
                native.gm.observe_loyalty(p, 6, reason="actual rotation ownership")
                members.append(contest.contestant_from_combatants(
                    native, p, owner, "매력", stat_dice=dict(stats)))
            teams.append(tuple(members))
        native.everyone = native.gm.everyone = [*trainers, *pokemon]
        teams = tuple(teams)
        return native, contest, teams, tuple(team[1] for team in teams)

    @staticmethod
    def invoke_rotation(contest, teams, reps, selector=None):
        return contest.run_rotation(
            teams, "근사함", lambda c, rnd, adjacent, center:
                (("연속자르기", "꼬리흔들기", "회복지령")[rnd - 1], 0),
            representatives=reps,
            performer_selector=selector or (lambda rep, rnd, available: available[0]),
            contest_id="rotation:native-source")

    def test_solo_and_team_use_only_the_selected_native_representative_normal_introduction(self):
        for mode in ("solo", "team"):
            with self.subTest(mode=mode):
                native, contest, teams, reps = self.fixture(mode)
                _, ordinary, _, ordinary_reps = self.fixture(mode)
                ordinary.intro_stage(ordinary_reps, "근사함")
                def pause(*args):
                    raise Pause()
                with self.assertRaises(Pause):
                    self.invoke_rotation(contest, teams, reps, pause)
                self.assertEqual(contest.rng.getstate(), ordinary.rng.getstate())
                for representative, expected, team in zip(reps, ordinary_reps, teams):
                    self.assertEqual(
                        (representative.stat_dice, representative.appeal,
                         representative.intro_completed, representative.letter),
                        (expected.stat_dice, expected.appeal,
                         expected.intro_completed, expected.letter))
                    self.assertTrue(all(not c.intro_completed for c in team if c is not representative))
                restored, participants = CODEC.load_contest(
                    self.contest_rules,
                    json.loads(json.dumps(CODEC.dump_contest(
                        contest, tuple(c for team in teams for c in team)))),
                    native_rules=self.rules)
                saved = restored._standard_run["rotation"]
                self.invoke_rotation(restored, saved["teams"], saved["representatives"])
                self.assertEqual(restored._standard_run["phase"], "complete")
                self.assertTrue(all(saved["performed"][rep] == set(team)
                                    for rep, team in zip(saved["representatives"], saved["teams"])))

    def test_native_rotation_rejects_two_trainers_for_three_slots_before_intro(self):
        native, contest, teams, reps = self.fixture("mixed")
        before = contest.rng.getstate()
        with self.assertRaises(ValueError):
            self.invoke_rotation(contest, teams, reps)
        self.assertIsNone(contest._standard_run)
        self.assertEqual(contest.rng.getstate(), before)
        self.assertTrue(all(not c.intro_completed for team in teams for c in team))

    def test_native_rotation_rejects_duplicate_pokemon_wrappers_before_intro(self):
        native, contest, teams, reps = self.fixture()
        binding = contest._native_intro_bindings[teams[0][0]]
        _, p, owner, skill, _ = binding
        clone = contest.contestant_from_combatants(
            native, p, owner, skill, stat_dice=dict(teams[0][0].stat_dice))
        teams = ((teams[0][0], teams[0][1], clone), *teams[1:])
        before = contest.rng.getstate()
        with self.assertRaises(ValueError):
            self.invoke_rotation(contest, teams, reps)
        self.assertIsNone(contest._standard_run)
        self.assertEqual(contest.rng.getstate(), before)

    def test_native_rotation_rejects_stale_nonrepresentative_owner_before_intro(self):
        native, contest, teams, reps = self.fixture()
        contest._native_intro_bindings[teams[0][0]][1].spec["trainer_id"] = "absent-owner"
        before = contest.rng.getstate()
        with self.assertRaises(ValueError):
            self.invoke_rotation(contest, teams, reps)
        self.assertIsNone(contest._standard_run)
        self.assertEqual(contest.rng.getstate(), before)

    def test_native_roster_rejects_missing_foreign_unregistered_and_shared_owner_bindings(self):
        for invalid in ("missing", "foreign", "unregistered", "shared-owner"):
            with self.subTest(invalid=invalid):
                native, contest, teams, reps = self.fixture()
                member = teams[1][0]
                binding = contest._native_intro_bindings[member]
                _, p, owner, skill, choices = binding
                if invalid == "missing":
                    del contest._native_intro_bindings[member]
                elif invalid == "foreign":
                    other = Engine(self.rules)
                    other.everyone = other.gm.everyone = [p, owner]
                    contest._native_intro_bindings[member] = (other, p, owner, skill, choices)
                elif invalid == "unregistered":
                    native.everyone = native.gm.everyone = [a for a in native.everyone if a is not p]
                else:
                    shared_owner = contest._native_intro_bindings[teams[0][0]][2]
                    p.spec["trainer_id"] = shared_owner.entity_id
                    contest._native_intro_bindings[member] = (native, p, shared_owner, skill, choices)
                before = contest.rng.getstate()
                with self.assertRaises(ValueError):
                    self.invoke_rotation(contest, teams, reps)
                self.assertIsNone(contest._standard_run)
                self.assertEqual(contest.rng.getstate(), before)
                self.assertTrue(all(not c.intro_completed for team in teams for c in team))

    def test_saved_native_rotation_rejects_duplicate_binding_and_changed_actual_owner(self):
        native, contest, teams, reps = self.fixture()
        with self.assertRaises(Pause):
            self.invoke_rotation(contest, teams, reps, lambda *args: (_ for _ in ()).throw(Pause()))
        payload = json.loads(json.dumps(CODEC.dump_contest(
            contest, tuple(c for team in teams for c in team))))
        for invalid in ("duplicate", "owner"):
            with self.subTest(invalid=invalid):
                restored, participants = CODEC.load_contest(
                    self.contest_rules, payload, native_rules=self.rules)
                saved = restored._standard_run["rotation"]
                a, b = saved["teams"][0][0], saved["teams"][0][2]
                if invalid == "duplicate":
                    restored._native_intro_bindings[b] = restored._native_intro_bindings[a]
                else:
                    restored._native_intro_bindings[a][1].spec["trainer_id"] = "absent-owner"
                with self.assertRaises(CODEC.StateCodecError):
                    CODEC.dump_contest(restored, participants)

    def test_chooser_changed_owner_is_rejected_before_appeal_or_stat_die_spending(self):
        native, contest, teams, reps = self.fixture()
        before = {}
        def choose(actor, rnd, adjacent, center):
            before["rng"] = contest.rng.getstate()
            before["pools"] = {c: dict(c.stat_dice) for team in teams for c in team}
            before["appeal"] = {c: c.appeal for team in teams for c in team}
            contest._native_intro_bindings[teams[0][0]][1].spec["trainer_id"] = "absent-owner"
            return "연속자르기", 1
        with self.assertRaises(ValueError):
            contest.run_rotation(
                teams, "근사함", choose, representatives=reps,
                performer_selector=lambda rep, rnd, available: available[0])
        self.assertEqual(contest.rng.getstate(), before["rng"])
        self.assertEqual({c: dict(c.stat_dice) for team in teams for c in team}, before["pools"])
        self.assertEqual({c: c.appeal for team in teams for c in team}, before["appeal"])
        self.assertTrue(all(not spent for spent in contest._standard_run["rotation"]["spent"].values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
