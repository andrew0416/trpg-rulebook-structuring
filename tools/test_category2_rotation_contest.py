"""Direct regressions for core clauses C08-085..C08-089."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path.insert(0, str(STAGE / "engine"))
sys.path.insert(1, str(ROOT / "engine"))

from contest import ContestEngine, ContestRules, Contestant
from state_codec import StateCodecError, dump_contest, load_contest


MOVES = ("연속자르기", "꼬리흔들기", "회복지령")
TYPES = ("근사함", "귀여움", "슬기로움")


class Pause(Exception):
    pass


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = ContestRules(ROOT)

    def setUp(self):
        self.engine = ContestEngine(self.rules, seed=8085)
        self.teams = tuple(tuple(
            Contestant(
                f"team-{team}-pokemon-{member}",
                {stat: 12 for stat in TYPES}, list(MOVES),
                "매력", 1, "귀여움")
            for member in range(3)) for team in range(3))
        self.representatives = tuple(team[1] for team in self.teams)

    def flat(self, teams=None):
        return tuple(member for team in (teams or self.teams) for member in team)

    @staticmethod
    def round_move(round_number):
        return MOVES[round_number - 1]

    def run_choice(self, *, spend=2, selector=None, chooser=None, contest_id=None):
        selector = selector or (lambda representative, round_number, available: available[0])
        chooser = chooser or (lambda actor, round_number, adjacent, center:
                              (self.round_move(round_number), spend))
        return self.engine.run_rotation(
            self.teams, "근사함", chooser,
            representatives=self.representatives,
            performer_selector=selector, contest_id=contest_id)

    def test_round_choice_uses_every_declared_pokemon_once_and_shares_cap(self):
        calls = []
        def chooser(actor, round_number, adjacent, center):
            calls.append((actor, round_number, tuple(adjacent), center))
            return self.round_move(round_number), 2
        result = self.run_choice(chooser=chooser)
        rotation = self.engine._standard_run["rotation"]
        self.assertEqual(set(result), set(self.representatives))
        self.assertEqual(len(calls), 9)
        for representative, team in zip(self.representatives, self.teams):
            self.assertEqual(rotation["performed"][representative], set(team))
            self.assertEqual(rotation["spent"][representative], 6)
            self.assertEqual(rotation["pool_cap"], 6)
            self.assertIs(team[0]._paired_state, team[1]._paired_state)
            self.assertIs(team[1]._paired_state, team[2]._paired_state)
        self.assertEqual({row["spent_stat_dice"] for row in self.engine.last_standings}, {6})

    def test_predetermined_order_and_round_types_are_locked_before_intro(self):
        orders = tuple(tuple(reversed(team)) for team in self.teams)
        observed = []
        def chooser(actor, round_number, adjacent, center):
            observed.append((round_number, actor, self.engine._standard_run["round_type"]))
            return self.round_move(round_number), 0
        self.engine.run_rotation(
            self.teams, None, chooser, representatives=self.representatives,
            orders=orders, round_types=TYPES, contest_id="rotation:typed")
        for round_number in range(1, 4):
            round_rows = [row for row in observed if row[0] == round_number]
            self.assertEqual({row[1] for row in round_rows},
                             {order[round_number - 1] for order in orders})
            self.assertEqual({row[2] for row in round_rows}, {TYPES[round_number - 1]})
        with self.assertRaises(ValueError):
            self.engine.run_rotation(
                self.teams, None, chooser, representatives=self.representatives,
                orders=tuple(self.teams), round_types=TYPES,
                contest_id="rotation:typed")

    def test_shared_dice_limit_rejects_before_roll_and_can_resume(self):
        def over(actor, round_number, adjacent, center):
            return self.round_move(round_number), 3
        with self.assertRaisesRegex(ValueError, "shared contest-die limit"):
            self.run_choice(chooser=over, contest_id="rotation:cap")
        state = self.engine._standard_run
        rotation = state["rotation"]
        self.assertEqual(state["round"], 2)
        self.assertEqual(state["slot"], 0)
        self.assertEqual(state["phase"], "perform")
        self.assertEqual(set(rotation["spent"].values()), {6})
        third = dict(rotation["current"])
        before = {member: dict(member.stat_dice) for member in third.values()}
        self.engine.run_rotation(
            self.teams, "근사함",
            lambda actor, round_number, adjacent, center: (self.round_move(round_number), 0),
            representatives=self.representatives,
            performer_selector=lambda representative, round_number, available: available[0],
            contest_id="rotation:cap")
        self.assertEqual(self.engine._standard_run["phase"], "complete")
        self.assertTrue(all(rotation["spent"][rep] == 6 for rep in self.representatives))
        self.assertTrue(all(before[member] == member.stat_dice for member in before))

    def test_selection_is_atomic_and_cannot_reuse_a_team_member(self):
        chosen = {rep: team[0] for rep, team in zip(self.representatives, self.teams)}
        def selector(rep, round_number, available):
            return chosen[rep]
        with self.assertRaisesRegex(ValueError, "unused"):
            self.run_choice(selector=selector, spend=0, contest_id="rotation:selection")
        state = self.engine._standard_run
        self.assertEqual(state["round"], 1)
        self.assertEqual(state["phase"], "round")
        self.assertEqual(state["rotation"]["current"], {})
        self.assertTrue(all(len(values) == 1 for values in state["rotation"]["performed"].values()))

    def test_excitement_and_last_move_follow_the_team_slot(self):
        seen = []
        def chooser(actor, round_number, adjacent, center):
            seen.append((round_number, actor.name, actor.excitement, actor.last_move))
            return self.round_move(round_number), 0
        self.run_choice(chooser=chooser, contest_id="rotation:shared")
        for representative in self.representatives:
            team_names = {member.name for member in self.teams[self.representatives.index(representative)]}
            rows = sorted((row for row in seen if row[1] in team_names), key=lambda row: row[0])
            self.assertEqual(rows[0][2:], (0, None))
            self.assertEqual(rows[1][2], 0)  # Reliable does not add excitement unless repeated.
            self.assertEqual(rows[1][3], self.rules.move("연속자르기")["id"])
            self.assertEqual(rows[2][2], 2)
            self.assertEqual(rows[2][3], self.rules.move("꼬리흔들기")["id"])

    def test_pause_json_restore_and_tamper_validation(self):
        calls = []
        def pause(actor, round_number, adjacent, center):
            calls.append(actor)
            if len(calls) == 2:
                raise Pause()
            return self.round_move(round_number), 1
        with self.assertRaises(Pause):
            self.run_choice(chooser=pause, contest_id="rotation:save")
        payload = json.loads(json.dumps(dump_contest(self.engine, self.flat())))
        restored, participants = load_contest(self.rules, payload)
        rotation = restored._standard_run["rotation"]
        teams = rotation["teams"]
        reps = rotation["representatives"]
        restored.run_rotation(
            teams, "근사함",
            lambda actor, round_number, adjacent, center: (self.round_move(round_number), 1),
            representatives=reps,
            performer_selector=lambda representative, round_number, available: available[0],
            contest_id="rotation:save")
        self.assertEqual(restored._standard_run["phase"], "complete")
        dump_contest(restored, participants)
        rotation["spent"][reps[0]] += 1
        with self.assertRaises(StateCodecError):
            dump_contest(restored, participants)


if __name__ == "__main__":
    unittest.main(verbosity=2)
