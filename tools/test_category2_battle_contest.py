"""Direct contract tests for Battle Contest clauses C08-097..C08-104."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path.insert(0, str(STAGE / "engine"))
sys.path.insert(1, str(ROOT / "engine"))

from builder import build_pokemon, build_trainer
from contest import ContestEngine, ContestRules
from engine import Combatant, Engine, Rules
import battle_contest as BATTLE
import state_codec as CODEC


MOVES = ["move/보복", "move/유턴", "move/배턴터치", "move/볼트체인지"]
STATS = {"hp": 12, "atk": 12, "def": 10, "spa": 10, "spd": 10, "spe": 10}


class BattleContestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")
        cls.contest_rules = ContestRules(str(ROOT), ruleset="core")

    def fixture(self, *, size=3, format_size=1, contest_id="battle:test"):
        engine = Engine(self.rules, seed=8088)
        contest = ContestEngine(self.contest_rules, seed=8089)
        trainers, rosters = [], []
        for side in range(2):
            trainer = Combatant(self.rules, build_trainer(
                self.rules, f"trainer-{side}", 30, STATS,
                skills={"매력": 5, "직감": 4, "교활": 4, "협박": 4, "명령": 4}))
            trainers.append(trainer)
            team = []
            for member in range(size):
                pokemon = Combatant(self.rules, build_pokemon(
                    self.rules, "이상해씨", 30, f"pokemon-{side}-{member}",
                    abilities=[], moves=MOVES))
                pokemon.spec["trainer_id"] = trainer.entity_id
                pokemon.stats["spe"] = 10 + side * 10 + member
                pokemon.on_field = member < format_size
                pokemon.pos = (side * 5 + member, side)
                team.append(pokemon)
            rosters.append(tuple(team))
        everyone = [*trainers, *(p for team in rosters for p in team)]
        engine.everyone = engine.gm.everyone = everyone
        for team in rosters:
            for pokemon in team:
                engine.gm.observe_loyalty(
                    pokemon, 6, reason="actual Battle Contest Trainer relationship")
        introductions = {}
        for trainer, team in zip(trainers, rosters):
            introductions[trainer.entity_id] = contest.contestant_from_combatants(
                engine, team[0], trainer, "매력",
                stat_dice={"근사함": 3, "귀여움": 2, "슬기로움": 1,
                           "아름다움": 1, "강인함": 1})
        BATTLE.create(
            engine, contest, trainers, rosters,
            tuple(tuple(team[:format_size]) for team in rosters), "근사함",
            introductions, contest_id=contest_id, format_size=format_size)
        return engine, contest, tuple(trainers), tuple(rosters), contest_id

    @staticmethod
    def state(engine, contest_id):
        return BATTLE.validate(engine, contest_id)[1]

    def test_two_equal_three_to_six_rosters_create_exact_two_n_round_lifetime(self):
        for size in (3, 6):
            with self.subTest(size=size):
                engine, contest, trainers, teams, cid = self.fixture(
                    size=size, contest_id=f"battle:size:{size}")
                state = self.state(engine, cid)
                self.assertEqual((state["max_rounds"], len(state["pokemon"])),
                                 (size * 2, size * 2))
                self.assertEqual(BATTLE.result(engine, cid)["status"], "ready")
        engine, contest, trainers, teams, cid = self.fixture()
        with self.assertRaisesRegex(ValueError, "already used"):
            BATTLE.create(engine, contest, trainers, teams,
                          ((teams[0][0],), (teams[1][0],)), "근사함", {},
                          contest_id=cid)

    def test_introduction_pool_is_copied_per_pokemon_and_never_changes_initiative(self):
        engine, contest, trainers, teams, cid = self.fixture()
        state = self.state(engine, cid)
        first, bench = teams[0][0], teams[0][1]
        before_bench = deepcopy(state["pokemon"][bench.entity_id]["stat_dice"])
        state["pokemon"][first.entity_id]["stat_dice"]["근사함"] -= 1
        self.assertEqual(state["pokemon"][bench.entity_id]["stat_dice"], before_bench)
        expected = [p.entity_id for p in engine.initiative((teams[0][0], teams[1][0]))]
        state["pokemon"][first.entity_id]["excitement"] = 5
        actual = [p.entity_id for p in BATTLE.begin_round(engine, cid)]
        self.assertEqual(actual, expected)

    def test_native_move_also_rolls_appeal_and_all_opposing_field_pokemon_are_adjacent(self):
        engine, contest, trainers, teams, cid = self.fixture(format_size=2)
        BATTLE.begin_round(engine, cid)
        attacker, target = teams[0][0], teams[1][0]
        engine.start_of_turn(attacker)
        receipt = BATTLE.perform_move(engine, contest, cid, attacker, target,
                                      "move/보복", combat_options={"set_damage": True})
        self.assertTrue(receipt["appeal_committed"])
        state = self.state(engine, cid)
        # Payback has Special Attention: every opposing field Pokemon gains one
        # Voltage because Battle Contest treats all of them as adjacent.
        self.assertEqual([state["pokemon"][p.entity_id]["excitement"]
                          for p in teams[1][:2]], [1, 1])
        self.assertEqual(state["pokemon"][teams[1][2].entity_id]["excitement"], 0)
        self.assertIn(state["pokemon"][attacker.entity_id]["last_move"],
                      ("move/보복", self.rules.move("move/보복")["id"]))

    def test_attack_knockout_awards_voltage_and_replacement_center_on_first_appeal(self):
        engine, contest, trainers, teams, cid = self.fixture()
        BATTLE.begin_round(engine, cid)
        attacker, target, replacement = teams[0][0], teams[1][0], teams[1][1]
        target.hp = 1
        target.stats["def"] = 1
        target.stats["spe"] = 1
        engine.start_of_turn(attacker)
        receipt = BATTLE.perform_move(engine, contest, cid, attacker, target,
                                      "move/보복", combat_options={"set_damage": True})
        self.assertTrue(receipt["knockout"])
        state = self.state(engine, cid)
        self.assertEqual(state["pokemon"][attacker.entity_id]["excitement"], 2)
        switch = BATTLE.switch(engine, cid, trainers[1], target, replacement)
        self.assertFalse(switch["turn_spent"])
        self.assertTrue(self.state(engine, cid)["pokemon"][replacement.entity_id]["center_pending"])
        engine.end_of_turn(attacker)
        engine.start_of_turn(replacement)
        BATTLE.perform_move(engine, contest, cid, replacement, attacker,
                            "move/보복", combat_options={"set_damage": True})
        self.assertFalse(self.state(engine, cid)["pokemon"][replacement.entity_id]["center_pending"])

    def test_end_turn_damage_routes_voltage_to_active_opponents_and_switch_spends_pokemon_turn(self):
        engine, contest, trainers, teams, cid = self.fixture()
        BATTLE.begin_round(engine, cid)
        victim = teams[1][0]
        victim.hp = 1
        victim.conditions.add("독")
        engine.start_of_turn(victim)
        victim.took_standard = True
        receipt = BATTLE.finish_turn(engine, cid, victim)
        self.assertTrue(receipt["knockout"])
        self.assertEqual(self.state(engine, cid)["pokemon"][teams[0][0].entity_id]["excitement"], 2)

        # A fresh occurrence demonstrates voluntary switching and recall loss.
        engine, contest, trainers, teams, cid = self.fixture(contest_id="battle:switch")
        BATTLE.begin_round(engine, cid)
        outgoing, incoming = teams[0][0], teams[0][1]
        state = self.state(engine, cid)
        state["pokemon"][outgoing.entity_id]["excitement"] = 4
        engine.start_of_turn(outgoing)
        receipt = BATTLE.switch(engine, cid, trainers[0], outgoing, incoming)
        self.assertTrue(receipt["turn_spent"])
        self.assertEqual(self.state(engine, cid)["pokemon"][outgoing.entity_id]["excitement"], 2)

    def test_recall_exception_multi_formats_round_limit_and_json_restore(self):
        engine, contest, trainers, teams, cid = self.fixture(format_size=3)
        state = self.state(engine, cid)
        outgoing, incoming = teams[0][0], teams[0][0]  # all three slots occupied
        self.assertEqual([len(side["active"]) for side in state["sides"]], [3, 3])
        payload = json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False))
        restored = CODEC.load_engine(self.rules, payload)
        restored_state = BATTLE.validate(restored, cid)[1]
        self.assertEqual((restored_state["format_size"], restored_state["max_rounds"]), (3, 6))

        engine, contest, trainers, teams, cid = self.fixture(contest_id="battle:exception")
        BATTLE.begin_round(engine, cid)
        outgoing, incoming = teams[0][0], teams[0][1]
        self.state(engine, cid)["pokemon"][outgoing.entity_id]["excitement"] = 4
        engine.start_of_turn(outgoing)
        receipt = BATTLE.switch(engine, cid, trainers[0], outgoing, incoming,
                                source="move/유턴")
        self.assertTrue(receipt["loss_exempt"])
        self.assertEqual(self.state(engine, cid)["pokemon"][outgoing.entity_id]["excitement"], 4)
        engine.end_of_turn(outgoing)
        # Complete the finite six-round clock without fabricating turns.
        BATTLE.finish_round(engine, cid)
        for _ in range(5):
            BATTLE.begin_round(engine, cid)
            BATTLE.finish_round(engine, cid)
        final = BATTLE.result(engine, cid)
        self.assertEqual((final["status"], final["rounds_completed"],
                          final["completion_reason"]), ("complete", 6, "round_limit"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

