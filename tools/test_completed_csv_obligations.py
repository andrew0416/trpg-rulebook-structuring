"""Source-derived behavioral boundaries for the completed CSV cohort.

The canonical fixtures provide real Engine/actor/item objects; this file adds
only missing oracles, without treating source lookup as effect verification.
"""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import csv_item_capability_contracts as CAP
import state_grants as GRANTS
from engine import Engine
from engine import Combatant
from builder import build_pokemon
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts
import test_category2_fashion_item_contracts as _fixture_test_category2_fashion_item_contracts
import fashion_items as FASHION
import frequency as FREQUENCY
import five_strike as FIVE
import items as ITEMS


class CompletedCsvObligationTests(unittest.TestCase):
    setUpClass = classmethod(_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass.__func__)
    trainer = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.trainer
    pokemon = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.pokemon
    fixture = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.fixture
    physical = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.physical
    egg = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.egg
    equip = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.equip

    def test_unown_dc16_relationship_uses_success_not_failed_check(self):
        # inventory source: item-data.csv record84 columns5..6: failing DC16
        # does not make the summoned creature an immediate ally.
        for total, allied in ((15, False), (16, True), (17, True)):
            with self.subTest(occult_total=total):
                actor = self.pokemon("summoner-" + str(total), capabilities=("안농모으기",))
                unown = self.pokemon("unown-" + str(total), species="안농", level=15)
                actor.side = "party"
                unown.side = "wild"
                engine = self.fixture(actor)
                engine.start_round([actor]); engine.start_of_turn(actor, initiative_count=20)
                before = actor.budget["standard"]
                result = CAP.gather_unown(engine, actor, unown, occult_total=total)
                self.assertEqual(result["immediate_ally"], allied)
                self.assertEqual(unown.side, "party" if allied else "wild")
                self.assertEqual(actor.budget["standard"], before - 1)
                self.assertIn(unown, engine.everyone)
                self.assertEqual(result["unown_id"], unown.entity_id)

    def test_unown_four_session_receipt_restores_and_failed_repeat_costs_nothing(self):
        actor = self.pokemon("summoner-clock", capabilities=("안농모으기",))
        unown = self.pokemon("unown-clock", species="안농", level=15)
        engine = self.fixture(actor)
        engine.start_round([actor]); engine.start_of_turn(actor, initiative_count=20)
        CAP.gather_unown(engine, actor, unown, occult_total=16)
        loaded = Engine.import_state(self.r, json.loads(json.dumps(engine.export_state())))
        actual = next(a for a in loaded.everyone if a.entity_id == actor.entity_id)
        candidate = Combatant(loaded.r, build_pokemon(loaded.r,"안농",15,name="unown-second",abilities=[]))
        before = deepcopy((actual.budget, actual.spec, loaded.rng.getstate()))
        with self.assertRaisesRegex(ValueError, "four-session"):
            CAP.gather_unown(loaded, actual, candidate, occult_total=16)
        self.assertEqual((actual.budget, actual.spec, loaded.rng.getstate()), before)
        loaded.session_epoch = 4
        loaded.end_of_turn(actual);loaded.end_encounter(round_elapsed_seconds=0)
        loaded.start_round([actual]);loaded.start_of_turn(actual,initiative_count=20)
        self.assertTrue(CAP.gather_unown(loaded, actual, candidate, occult_total=16)["summoned"])
        self.assertEqual(CAP.hidden_power_frequency(actual, "Scene"), "At-Will")

    def test_unown_hidden_power_actual_frequency_and_consecutive_turns(self):
        actor = self.pokemon("hidden-owner", capabilities=("안농모으기",), moves=("move/잠재파워",))
        target = self.pokemon("hidden-target")
        engine = self.fixture(actor, target)
        self.assertEqual(FREQUENCY.move_frequency(engine, "move/잠재파워", actor), ("at_will", 1))
        for _ in range(2):
            engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
            with patch.object(engine, "d20", return_value=20):
                engine.use_move(actor, target, "move/잠재파워", set_damage=True)
            self.assertEqual(actor.budget["standard"], 0)
            engine.end_of_turn(actor)
        actor.spec["capabilities"] = []
        self.assertEqual(FREQUENCY.move_frequency(engine, "move/잠재파워", actor), ("every_other_turn", 1))

    def test_loaded_dice_native_five_strike_chooses_better_actual_d8_and_saves_receipt(self):
        actor = self.pokemon("dice-native", moves=("move/씨기관총",))
        target = self.pokemon("dice-target")
        engine = self.fixture(actor, target)
        self.equip(engine, actor, "csv/dice-native", "item/속임수주사위")
        engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
        with patch.object(engine, "d20", return_value=20), patch.object(engine.rng, "randint", side_effect=(1, 8)) as rng:
            engine.use_move(actor, target, "move/씨기관총", set_damage=True)
        row = actor.spec[FIVE.KEY][0]
        self.assertEqual((row["face"], row["hits"]), (8, 5))
        self.assertEqual(rng.call_count, 2)
        self.assertEqual(row["loaded_dice"]["rolls"], [1, 8])
        self.assertEqual(row["loaded_dice"]["instance_id"], "csv/dice-native")
        ITEMS.unregister_item(engine, actor, "item/속임수주사위")
        loaded = Engine.import_state(self.r, json.loads(json.dumps(engine.export_state())))
        restored = next(a for a in loaded.everyone if a.entity_id == actor.entity_id)
        self.assertEqual(restored.spec[FIVE.KEY], actor.spec[FIVE.KEY])
        restored.spec[FIVE.KEY][0]["loaded_dice"]["rolls"] = [1, 2]
        with self.assertRaises(ValueError):
            loaded.export_state()

    def test_loaded_dice_rejects_trainer_and_unequip_restores_one_native_die(self):
        trainer = self.trainer("dice-trainer")
        engine = self.fixture(trainer)
        with self.assertRaisesRegex(ValueError, "Pokemon-only"):
            self.equip(engine, trainer, "csv/dice-wrong-kind", "item/속임수주사위")
        actor = self.pokemon("dice-unequipped", moves=("move/씨기관총",))
        target = self.pokemon("dice-ordinary-target")
        engine = self.fixture(actor, target)
        self.equip(engine, actor, "csv/dice-removed", "item/속임수주사위")
        ITEMS.unregister_item(engine, actor, "item/속임수주사위")
        engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
        with patch.object(engine, "d20", return_value=20), patch.object(engine, "roll_expr", return_value=(2, [2])) as roll:
            engine.use_move(actor, target, "move/씨기관총", set_damage=True)
        self.assertEqual(roll.call_count, 1)
        row = actor.spec[FIVE.KEY][0]
        self.assertEqual((row["face"], row["hits"]), (2, 2))
        self.assertNotIn("loaded_dice", row)

    def test_loaded_dice_does_not_invent_rolls_for_explicit_fixed_five_strike_mode(self):
        actor = self.pokemon("dice-fixed", moves=("move/독침천발",))
        target = self.pokemon("dice-fixed-target")
        engine = self.fixture(actor, target)
        self.equip(engine, actor, "csv/dice-fixed", "item/속임수주사위")
        engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
        engine.apply_status(target, "마비", source="move/전기자석파", applied_by=actor)
        engine.gm.choose_optional_move_effect(actor, "move/독침천발", reason="actual selected fixed-eight source")
        with patch.object(engine, "d20", return_value=20), patch.object(engine, "roll_expr", side_effect=AssertionError("fixed mode owns no d8")):
            engine.use_move(actor, target, "move/독침천발", set_damage=True)
        row = actor.spec[FIVE.KEY][0]
        self.assertEqual((row["face"], row["hits"]), (8, 5))
        self.assertNotIn("loaded_dice", row)


if __name__ == "__main__":
    unittest.main()


class CompletedFashionBranchTests(_fixture_test_category2_fashion_item_contracts.FashionItemContractTests):
    def test_five_equipped_sources_gate_their_own_stat_and_contest_receipt(self):
        for item, stat in (("귀여운", "귀여움"), ("아름다운", "아름다움"),
                           ("근사한", "근사함"), ("강인한", "강인함"),
                           ("슬기로운", "슬기로움")):
            with self.subTest(item=item):
                self.setUp()
                self.make("item/" + item + "-패션-1")
                used = set()
                key, _ = FASHION.contest_plan(self.e, self.p, stat, used)
                with self.assertRaisesRegex(ValueError, "matching equipped"):
                    FASHION.contest_plan(self.e, self.p,
                        "강인함" if stat != "강인함" else "귀여움", used)
                used.add(key)
                with self.assertRaisesRegex(ValueError, "already used"):
                    FASHION.contest_plan(self.e, self.p, stat, used)
                with self.assertRaisesRegex(ValueError, "Pokemon-only"):
                    FASHION.contest_plan(self.e, self.a, stat, set())
