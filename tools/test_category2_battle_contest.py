"""Direct contract tests for Battle Contest clauses C08-097..C08-104."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE
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

    def fixture(self, *, size=3, format_size=1, contest_id="battle:test", moves=None,
                trainer_extra=None, trainer_skills=None):
        engine = Engine(self.rules, seed=8088)
        contest = ContestEngine(self.contest_rules, seed=8089)
        trainers, rosters = [], []
        for side in range(2):
            trainer = Combatant(self.rules, build_trainer(
                self.rules, f"trainer-{side}", 30, STATS,
                skills=trainer_skills or {"매력": 5, "직감": 4, "교활": 4, "협박": 4, "명령": 4},
                extra=trainer_extra))
            trainers.append(trainer)
            team = []
            for member in range(size):
                pokemon = Combatant(self.rules, build_pokemon(
                    self.rules, "이상해씨", 30, f"pokemon-{side}-{member}",
                    abilities=[], moves=moves or MOVES))
                pokemon.spec["trainer_id"] = trainer.entity_id
                pokemon.stats["spe"] = 10 + side * 10 + member
                pokemon.stats["atk"] = (30, 5, 20, 10, 15, 25)[member]
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
                smart_stat_policy="ptu-original-special-defense")
        BATTLE.create(
            engine, contest, trainers, rosters,
            tuple(tuple(team[:format_size]) for team in rosters), "근사함",
            introductions, contest_id=contest_id, format_size=format_size,
            smart_stat_policy="ptu-original-special-defense")
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
        # Keep the historical ID, correcting its former copied-pool expectation.
        engine, contest, trainers, teams, cid = self.fixture()
        state = self.state(engine, cid)
        first, bench = teams[0][0], teams[0][1]
        before_bench = deepcopy(state["pokemon"][bench.entity_id]["stat_dice"])
        self.assertEqual(state["pokemon"][first.entity_id]["stat_dice"]["근사함"], 3)
        self.assertEqual(state["pokemon"][bench.entity_id]["stat_dice"]["근사함"], 0)
        self.assertGreater(state["sides"][0]["intro_dice"]["귀여움"], 0)
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
        BATTLE.perform_move(engine, contest, cid, outgoing, teams[1][0],
                            "move/유턴", combat_options={"set_damage": True})
        excitement = self.state(engine, cid)["pokemon"][outgoing.entity_id]["excitement"]
        receipt = BATTLE.switch(engine, cid, trainers[0], outgoing, incoming,
                                source="move/유턴")
        self.assertTrue(receipt["loss_exempt"])
        self.assertFalse(receipt["turn_spent"])
        self.assertEqual(self.state(engine, cid)["pokemon"][outgoing.entity_id]["excitement"], excitement)
        engine.end_of_turn(outgoing)
        # Complete the finite six-round clock without fabricating turns.
        BATTLE.finish_round(engine, cid)
        for _ in range(5):
            BATTLE.begin_round(engine, cid)
            BATTLE.finish_round(engine, cid)
        final = BATTLE.result(engine, cid)
        self.assertEqual((final["status"], final["rounds_completed"],
                          final["completion_reason"]), ("complete", 6, "round_limit"))

    def test_shared_intro_spend_is_explicit_single_balance_and_survives_restore(self):
        engine, contest, trainers, teams, cid = self.fixture(format_size=2)
        state = self.state(engine, cid)
        before = state["sides"][0]["intro_dice"]["귀여움"]
        self.assertGreaterEqual(before, 1)
        user, opponent = teams[0][1], teams[1][0]
        personal = deepcopy(state["pokemon"][user.entity_id]["stat_dice"])
        BATTLE.begin_round(engine, cid)
        BATTLE.start_turn(engine, cid, user)
        BATTLE.perform_move(engine, contest, cid, user, opponent, "move/유턴",
                            spend_stat_dice=1, spend_intro_dice=1,
                            combat_options={"set_damage": True, "situational": 100})
        state = self.state(engine, cid)
        self.assertEqual(state["sides"][0]["intro_dice"]["귀여움"], before - 1)
        self.assertEqual(state["pokemon"][user.entity_id]["stat_dice"], personal)
        self.assertNotEqual(state["pokemon"][user.entity_id]["contestant_id"],
                            state["pokemon"][teams[0][0].entity_id]["contestant_id"])
        restored = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(engine))))
        self.assertEqual(self.state(restored, cid)["sides"][0]["intro_dice"], state["sides"][0]["intro_dice"])

    def test_native_hail_start_knockout_records_one_bonus_and_exact_replacement(self):
        engine, contest, trainers, teams, cid = self.fixture(format_size=2)
        victim = teams[1][0]
        victim.hp = 1
        engine.gm.set_weather("hail", rounds=5, reason="actual start-of-turn hail")
        BATTLE.begin_round(engine, cid)
        receipt = BATTLE.start_turn(engine, cid, victim)
        self.assertTrue(receipt["knockout"])
        self.assertTrue(victim.fainted)
        state = self.state(engine, cid)
        self.assertEqual([state["pokemon"][p.entity_id]["excitement"] for p in teams[0][:2]], [2, 2])
        self.assertEqual(state["sides"][1]["replacement_center_due"], [victim.entity_id])
        BATTLE.finish_turn(engine, cid, victim)
        self.assertEqual([state["pokemon"][p.entity_id]["excitement"] for p in teams[0][:2]], [2, 2])
        BATTLE.switch(engine, cid, trainers[1], victim, teams[1][2])
        self.assertTrue(self.state(engine, cid)["pokemon"][teams[1][2].entity_id]["center_pending"])
        self.assertEqual(self.state(engine, cid)["sides"][1]["replacement_center_due"], [])

    def test_recoil_knockout_also_marks_the_attackers_replacement(self):
        engine, contest, trainers, teams, cid = self.fixture(moves=[*MOVES, "move/이판사판태클"])
        user, target = teams[0][0], teams[1][0]
        user.hp = 1
        target.hp = target.max_hp
        BATTLE.begin_round(engine, cid)
        BATTLE.start_turn(engine, cid, user)
        BATTLE.perform_move(engine, contest, cid, user, target, "move/이판사판태클",
                            combat_options={"set_damage": True, "situational": 100})
        self.assertTrue(user.fainted)
        self.assertIn(user.entity_id, self.state(engine, cid)["sides"][0]["replacement_center_due"])
        BATTLE.switch(engine, cid, trainers[0], user, teams[0][1])
        self.assertTrue(self.state(engine, cid)["pokemon"][teams[0][1].entity_id]["center_pending"])

    def test_grace_expires_and_unspent_prepare_expires_after_its_next_round(self):
        for move, flag in (("move/고속이동", "immune_fumble"), ("move/손톱갈기", "double_next")):
            with self.subTest(move=move):
                engine, contest, trainers, teams, cid = self.fixture(moves=[*MOVES, move])
                actor = teams[0][0]
                BATTLE.begin_round(engine, cid)
                BATTLE.start_turn(engine, cid, actor)
                receipt = BATTLE.perform_move(engine, contest, cid, actor, actor, move)
                self.assertTrue(receipt["appeal_committed"])
                self.assertTrue(self.state(engine, cid)["pokemon"][actor.entity_id][flag])
                BATTLE.finish_turn(engine, cid, actor)
                BATTLE.finish_round(engine, cid)
                if flag == "double_next":
                    self.assertTrue(self.state(engine, cid)["pokemon"][actor.entity_id][flag])
                    restored = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(engine))))
                    self.assertTrue(self.state(restored, cid)["pokemon"][actor.entity_id][flag])
                    BATTLE.begin_round(restored, cid)
                    BATTLE.finish_round(restored, cid)
                    self.assertFalse(self.state(restored, cid)["pokemon"][actor.entity_id][flag])
                else:
                    self.assertFalse(self.state(engine, cid)["pokemon"][actor.entity_id][flag])




    def test_move_recall_needs_actual_fresh_source_and_charges_no_second_standard(self):
        from native_scenario_fixture import assert_rejected_unchanged
        for move in ("move/유턴", "move/볼트체인지", "move/배턴터치"):
            with self.subTest(move=move):
                engine, contest, trainers, teams, cid = self.fixture()
                old, new, target = teams[0][0], teams[0][1], teams[1][0]
                BATTLE.begin_round(engine, cid)
                BATTLE.start_turn(engine, cid, old)
                assert_rejected_unchanged(engine, lambda: BATTLE.switch(
                    engine, cid, trainers[0], old, new, source=move), reason_pattern="completed")
                if move == "move/배턴터치":
                    import native_switch_transfer as SWITCH
                    SWITCH.select(engine, old, new, source=move, reason="actual Battle Contest Baton replacement")
                    engine.change_stage(old, "atk", 2)
                BATTLE.perform_move(engine, contest, cid, old, old if move == "move/배턴터치" else target,
                                    move, combat_options={"set_damage": True, "situational": 100})
                self.assertFalse(old.on_field)
                self.assertEqual(old.budget["standard"], 0)
                before = deepcopy(old._action_history)
                receipt = BATTLE.switch(engine, cid, trainers[0], old, new, source=move)
                self.assertFalse(receipt["turn_spent"])
                self.assertTrue(receipt["loss_exempt"])
                self.assertEqual(old._action_history, before)
                self.assertTrue(new.on_field)
                self.assertEqual(len(self.state(engine, cid)["consumed_recalls"]), 1)
                if move == "move/배턴터치":
                    self.assertEqual(new.stages["atk"], 2)
                    self.assertEqual(old.stages["atk"], 0)


    def test_round_trip_uses_real_move_trigger_trainer_ap_and_ignores_trapped(self):
        import action_points as AP
        engine, contest, trainers, teams, cid = self.fixture(trainer_extra={
            "classes": ["class/저글러"], "feats": ["feat/퀵-스위치", "feat/왕복-여행"]})
        trainer, old, new, target = trainers[0], teams[0][0], teams[0][1], teams[1][0]
        BATTLE.begin_round(engine, cid)
        BATTLE.start_turn(engine, cid, old)
        BATTLE.perform_move(engine, contest, cid, old, target, "move/보복",
                            combat_options={"set_damage": True, "situational": 100})
        engine.gm.add_condition(old, "수렁", reason="actual trapped outgoing Pokemon")
        before_ap, before_actions = AP.available(trainer), deepcopy(old._action_history)
        receipt = BATTLE.switch(engine, cid, trainer, old, new, source="feat/왕복-여행")
        self.assertFalse(receipt["turn_spent"])
        self.assertTrue(receipt["loss_exempt"])
        self.assertEqual(AP.available(trainer), before_ap - 1)
        self.assertEqual(old._action_history, before_actions)
        self.assertTrue(new.on_field)


    def test_tag_in_actual_recall_transfers_stages_and_charges_only_its_real_costs(self):
        import action_points as AP
        import native_switch_transfer as SWITCH
        for after_move in (False, True):
            with self.subTest(after_move=after_move):
                engine, contest, trainers, teams, cid = self.fixture(
                    trainer_extra={"classes": ["class/저글러"],
                                   "feats": ["feat/퀵-스위치", "feat/왕복-여행", "feat/태그-인"]},
                    trainer_skills={"매력": 5, "곡예": 3, "교활": 5})
                trainer, old, new, target = trainers[0], teams[0][0], teams[0][1], teams[1][0]
                BATTLE.begin_round(engine, cid)
                BATTLE.start_turn(engine, cid, old)
                engine.change_stage(old, "atk", 2)
                if after_move:
                    SWITCH.select_tag_in(engine,trainer,old,reason="actual Tag selection before native recall")
                    BATTLE.perform_move(engine, contest, cid, old, target, "move/유턴",
                                        combat_options={"set_damage": True, "situational": 100})
                    self.assertFalse(old.on_field)
                before_ap = AP.available(trainer)
                before_history = deepcopy(old._action_history)
                receipt = BATTLE.switch(engine, cid, trainer, old, new, source=SWITCH.TAG_IN)
                self.assertEqual(receipt["turn_spent"], not after_move)
                self.assertTrue(receipt["loss_exempt"])
                self.assertEqual(AP.available(trainer), before_ap - (0 if after_move else 1))
                self.assertEqual(new.stages["atk"], 2)
                self.assertEqual(old.stages["atk"], 0)
                if after_move:
                    self.assertEqual(old._action_history, before_history)
                self.assertEqual(old.budget["standard"], 0)
                use = trainer.spec[SWITCH.USES][-1]
                self.assertEqual((use["source"], use["outgoing_id"], use["incoming_id"], use["paid_ap"]),
                                 (SWITCH.TAG_IN, old.entity_id, new.entity_id, 1))
                restored = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(engine))))
                restored_trainer = next(a for a in restored.everyone if a.entity_id == trainer.entity_id)
                self.assertEqual(restored_trainer.spec[SWITCH.USES][-1]["recall_id"], use["recall_id"])
                self.assertEqual(self.state(restored, cid)["sides"][0]["active"], [new.entity_id])

    def test_actual_move_json_before_switch_preserves_voltage_recipient_and_consumes_once(self):
        import native_switch_transfer as SWITCH
        from native_scenario_fixture import assert_rejected_unchanged
        for move in ("move/유턴","move/볼트체인지",SWITCH.BATON):
            with self.subTest(move=move):
                engine,contest,trainers,teams,cid=self.fixture()
                trainer,old,new,foe=trainers[0],teams[0][0],teams[0][1],teams[1][0]
                BATTLE.begin_round(engine,cid);BATTLE.start_turn(engine,cid,old)
                if move==SWITCH.BATON:SWITCH.select(engine,old,new,reason="actual already-sent recipient")
                BATTLE.perform_move(engine,contest,cid,old,old if move==SWITCH.BATON else foe,move,
                    combat_options={"set_damage":True,"situational":100})
                voltage=self.state(engine,cid)["pokemon"][old.entity_id]["excitement"]
                restored=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(engine))))
                actors={actor.entity_id:actor for actor in restored.everyone}
                trainer,old,new=[actors[actor.entity_id] for actor in (trainer,old,new)]
                actions=deepcopy(old._action_history);recalls=deepcopy(old.spec[SWITCH.RECALLS])
                sent=trainer.spec.get('native_send_serial',0)
                result=BATTLE.switch(restored,cid,trainer,old,new,source=move)
                self.assertEqual((result['outgoing'],result['incoming']),(old.entity_id,new.entity_id))
                self.assertFalse(result['turn_spent']);self.assertEqual(old._action_history,actions)
                self.assertEqual(old.spec[SWITCH.RECALLS],recalls)
                self.assertEqual(trainer.spec['native_send_serial'],sent+(move!=SWITCH.BATON))
                self.assertEqual(self.state(restored,cid)['pokemon'][old.entity_id]['excitement'],voltage)
                assert_rejected_unchanged(restored,lambda:BATTLE.switch(restored,cid,trainer,old,new,source=move),
                    reason_pattern='active outgoing')

    def test_switch_source_substitution_wrong_native_recipient_and_later_action_are_atomic(self):
        import native_switch_transfer as SWITCH
        import turn as TURN
        from native_scenario_fixture import assert_rejected_unchanged
        engine,contest,trainers,teams,cid=self.fixture()
        trainer,old,new,other=trainers[0],teams[0][0],teams[0][1],teams[0][2]
        BATTLE.begin_round(engine,cid);BATTLE.start_turn(engine,cid,old)
        SWITCH.select(engine,old,new,reason='actual recorded Baton recipient')
        BATTLE.perform_move(engine,contest,cid,old,old,SWITCH.BATON,combat_options={'set_damage':True})
        assert_rejected_unchanged(engine,lambda:BATTLE.switch(engine,cid,trainer,old,new,source='move/유턴'),
            reason_pattern='native recall')
        assert_rejected_unchanged(engine,lambda:BATTLE.switch(engine,cid,trainer,old,other,source=SWITCH.BATON),
            reason_pattern='actual native send-out')
        self.assertTrue(TURN.spend(engine,old,'shift','actual subsequent action'))
        assert_rejected_unchanged(engine,lambda:BATTLE.switch(engine,cid,trainer,old,new,source=SWITCH.BATON),
            reason_pattern='native action boundary')


    def test_prepare_is_consumed_once_in_the_due_battle_round(self):
        engine, contest, trainers, teams, cid = self.fixture(moves=[*MOVES, "move/손톱갈기", "move/단단해지기"])
        actor = teams[0][0]
        BATTLE.begin_round(engine, cid)
        BATTLE.start_turn(engine, cid, actor)
        BATTLE.perform_move(engine, contest, cid, actor, actor, "move/손톱갈기")
        BATTLE.finish_turn(engine, cid, actor)
        BATTLE.finish_round(engine, cid)
        BATTLE.begin_round(engine, cid)
        BATTLE.start_turn(engine, cid, actor)
        BATTLE.perform_move(engine, contest, cid, actor, actor, "move/단단해지기", fixed_rolls=[2] * 6)
        row = self.state(engine, cid)["pokemon"][actor.entity_id]
        self.assertFalse(row["double_next"])
        self.assertIsNone(row["double_round"])
        self.assertEqual(self.state(engine, cid)["pokemon"][teams[1][0].entity_id]["fumble"], 6)
        self.assertEqual(sum("준비하기: 기술 주사위 두 배" in line for line in contest.log_lines), 1)

    def test_grace_blocks_same_round_sabotage_then_actual_next_round_fumbles_apply(self):
        engine, contest, trainers, teams, cid = self.fixture(moves=["move/고속이동", "move/웅크리기", "move/단단해지기"])
        protected, opponent = teams[0][0], teams[1][0]
        BATTLE.begin_round(engine, cid)
        BATTLE.start_turn(engine, cid, protected)
        BATTLE.perform_move(engine, contest, cid, protected, protected, "move/고속이동", fixed_rolls=[2, 2])
        BATTLE.finish_turn(engine, cid, protected)
        BATTLE.start_turn(engine, cid, opponent)
        BATTLE.perform_move(engine, contest, cid, opponent, opponent, "move/웅크리기", fixed_rolls=[6, 6])
        self.assertEqual(self.state(engine, cid)["pokemon"][protected.entity_id]["fumble"], 0)
        BATTLE.finish_turn(engine, cid, opponent)
        BATTLE.finish_round(engine, cid)
        BATTLE.begin_round(engine, cid)
        BATTLE.start_turn(engine, cid, opponent)
        BATTLE.perform_move(engine, contest, cid, opponent, opponent, "move/단단해지기", fixed_rolls=[6, 6, 6])
        self.assertEqual(self.state(engine, cid)["pokemon"][protected.entity_id]["fumble"], 6)

    def test_prepare_doubles_matching_and_opposing_move_dice_but_not_spent_dice(self):
        for move, spend_intro, expected in (("move/고속이동", 0, 6), ("move/웅크리기", 1, 6)):
            with self.subTest(move=move):
                engine, contest, trainers, teams, cid = self.fixture(moves=[*MOVES, "move/손톱갈기", move])
                actor = teams[0][0]
                BATTLE.begin_round(engine, cid)
                BATTLE.start_turn(engine, cid, actor)
                BATTLE.perform_move(engine, contest, cid, actor, actor, "move/손톱갈기", fixed_rolls=[2, 2])
                BATTLE.finish_turn(engine, cid, actor)
                BATTLE.finish_round(engine, cid)
                BATTLE.begin_round(engine, cid)
                BATTLE.start_turn(engine, cid, actor)
                before = BATTLE.result(engine, cid)["scores"]
                BATTLE.perform_move(engine, contest, cid, actor, actor, move,
                                    spend_stat_dice=2, spend_intro_dice=spend_intro, fixed_rolls=[2] * expected)
                after = BATTLE.result(engine, cid)["scores"]
                if move == "move/고속이동":
                    self.assertEqual(after[0] - before[0], 6)  # (1 effect + 1 match) * 2 + 2 spent.
                else:
                    self.assertEqual(before[1] - after[1], 6)  # (3 effect - 1 opposing) * 2 + 2 spent.

    def test_global_consecutive_move_rule_rejects_battle_retry_before_native_cost(self):
        from native_scenario_fixture import assert_rejected_unchanged
        engine, contest, trainers, teams, cid = self.fixture(moves=[*MOVES, "move/꼬리흔들기"])
        actor, target = teams[0][0], teams[1][0]
        BATTLE.begin_round(engine, cid)
        BATTLE.start_turn(engine, cid, actor)
        BATTLE.perform_move(engine, contest, cid, actor, target, "move/꼬리흔들기",
                            combat_options={"situational": 100})
        BATTLE.finish_turn(engine, cid, actor)
        BATTLE.finish_round(engine, cid)
        BATTLE.begin_round(engine, cid)
        BATTLE.start_turn(engine, cid, actor)
        before = (contest.rng.getstate(), list(contest.log_lines))
        assert_rejected_unchanged(engine, lambda: BATTLE.perform_move(
            engine, contest, cid, actor, target, "move/꼬리흔들기"), reason_pattern="Consecutive")
        self.assertEqual((contest.rng.getstate(), contest.log_lines), before)

    def test_native_rank_seven_intro_preserves_selected_rank_and_json_identity(self):
        rules = Rules(str(ROOT), ruleset="core")
        engine = Engine(rules, seed=8093)
        contest = ContestEngine(ContestRules(str(ROOT), ruleset="core"), seed=8094)
        trainer = Combatant(rules, build_trainer(rules, "rank-seven", 30, STATS, skills={"매력": 6}))
        pokemon = Combatant(rules, build_pokemon(rules, "이상해씨", 30, "same name", abilities=[], moves=MOVES))
        pokemon.spec["trainer_id"] = trainer.entity_id
        engine.everyone = engine.gm.everyone = [trainer, pokemon]
        rules.rulings.set_mech("gameplay/skill-rank-dice", "by_rank_name.초월",
                              {"rank": 7, "dice": "7d6", "eng": "Epic"},
                              reason="explicit campaign rank seven", rules=rules)
        engine.gm.set_skill(trainer, "매력", 7, reason="actual selected native skill rank")
        candidate = contest.contestant_from_combatants(engine, pokemon, trainer, "매력",
                                                       smart_stat_policy="ptu-original-special-defense")
        self.assertEqual(candidate.intro_rank_dice, 7)
        before = contest.rng.getstate()
        candidate.intro_rank_dice = 8
        with self.assertRaisesRegex(ValueError, "Native introduction state changed"):
            contest.intro_stage([candidate], "근사함")
        self.assertEqual(contest.rng.getstate(), before)
        candidate.intro_rank_dice = 7
        contest.intro_stage([candidate], "근사함")
        payload = json.loads(json.dumps(CODEC.dump_contest(contest, [candidate])))
        restored, participants = CODEC.load_contest(contest.r, payload, native_rules=rules)
        self.assertEqual((participants[0].entity_id, participants[0].intro_rank_dice),
                         (candidate.entity_id, 7))
        native, bound_pokemon, bound_trainer, _, _ = restored._native_intro_bindings[participants[0]]
        self.assertIs(next(a for a in native.everyone if a.entity_id == pokemon.entity_id), bound_pokemon)
        self.assertIs(next(a for a in native.everyone if a.entity_id == trainer.entity_id), bound_trainer)


if __name__ == "__main__":
    unittest.main(verbosity=2)

