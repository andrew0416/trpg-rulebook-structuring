"""Current native CSV reactions consume physical items through the stock owner."""
from pathlib import Path
from copy import deepcopy
import sys
import unittest
from unittest.mock import patch

OVERLAY = Path(__file__).resolve().parents[1]
ROOT = OVERLAY if (OVERLAY / "data").is_dir() and (OVERLAY / "output").is_dir() else Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(OVERLAY / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]
import csv_item_physical_contracts as CSV
import item_stock as STOCK
import test_category2_csv_remaining_item_contracts as FIX
import capability_actions as CAP
import state_grants as GRANTS
import world_entities as WORLD
import state_codec as CODEC


class CsvStockOwnerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.RemainingCsvItemContractTests.setUpClass()

    def fixture(self, item_id):
        helper = FIX.RemainingCsvItemContractTests()
        attacker = helper.pokemon("stock-owner-attacker")
        holder = helper.pokemon("stock-owner-holder")
        engine = helper.fixture(attacker, holder)
        attacker.on_field = holder.on_field = True
        obj = helper.equip(engine, holder, "stock-owner/item", item_id)
        CAP.set_carried(engine, holder, [{"id": obj["id"], "weight_kg": 1}], "actual held load")
        return helper, engine, attacker, holder, obj

    def assert_consumed(self, engine, holder, obj, trigger):
        self.assertTrue(WORLD.physical_lifecycle(obj)["consumed"])
        self.assertNotIn("carrier_id", obj)
        self.assertNotIn("equipped_by", obj)
        self.assertEqual(holder.spec["_carried_load"]["objects"], [])
        self.assertEqual(obj["consumed"], dict(source=obj["item_rule_id"],
            by_actor_id=holder.entity_id, at=engine.elapsed_seconds, trigger=trigger))
        receipts = holder.spec["stock_consumption_receipts"]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(next(iter(receipts.values()))["item_stock"]["instance_id"], obj["id"])
        self.assertEqual(next(iter(receipts.values()))["outcome"], "applied")
        self.assertEqual(next(iter(receipts.values()))["results"],
                         [{"kind": "physical_consumption", "id": obj["id"]}])
        self.assertIn("consumed", [row["event"] for row in obj[CSV.OBJECT_STATE]["history"]])

    def test_native_damage_eject_button_releases_actual_carried_stock(self):
        _, engine, attacker, holder, obj = self.fixture("item/탈출버튼")
        requested = engine.resolve_attack_damage(attacker, holder, engine.r.move("move/몸통박치기"), set_damage=True)
        self.assertGreater(requested, 0)
        self.assertIn("eject_button", holder.spec[CSV.PENDING])
        result = CSV.resolve_pending(engine, holder, "eject_button", accept=True)
        self.assertTrue(result["switched"])
        self.assertFalse(holder.on_field)
        self.assert_consumed(engine, holder, obj, "item/eject_button:free-switch")

    def test_native_red_card_uses_same_stock_owner_before_automatic_switch(self):
        _, engine, attacker, holder, obj = self.fixture("item/레드카드")
        engine.resolve_attack_damage(attacker, holder, engine.r.move("move/몸통박치기"), set_damage=True)
        self.assert_consumed(engine, holder, obj, "item/레드카드:attack-hit")
        self.assertIn("red_card", holder.spec[CSV.PENDING])
        CSV.resolve_pending(engine, holder, "red_card", accept=True)
        self.assertFalse(attacker.on_field)
        self.assertEqual(len(holder.spec["stock_consumption_receipts"]), 1)

    def test_eject_pack_keeps_stage_trigger_and_scene_policy(self):
        _, engine, _, holder, obj = self.fixture("item/탈출팩")
        CSV.after_stage_change(engine, holder, "atk", 0, -1)
        CSV.resolve_pending(engine, holder, "eject_pack", accept=True)
        self.assert_consumed(engine, holder, obj, "item/eject_pack:free-switch")
        self.assertEqual(len(obj[CSV.OBJECT_STATE]["scene_uses"]), 1)

    def test_failed_switch_rolls_back_load_effects_history_and_payment(self):
        _, engine, attacker, holder, obj = self.fixture("item/탈출버튼")
        engine.resolve_attack_damage(attacker, holder, engine.r.move("move/몸통박치기"), set_damage=True)
        before_spec, before_obj = deepcopy(holder.spec), deepcopy(obj)
        before_registration = deepcopy(holder._item_reg)
        with patch.object(CSV, "_immediate_switch", side_effect=ValueError("late native switch failure")):
            with self.assertRaisesRegex(ValueError, "late native switch failure"):
                CSV.resolve_pending(engine, holder, "eject_button", accept=True)
        self.assertEqual(holder.spec, before_spec)
        self.assertEqual(obj, before_obj)
        self.assertEqual(holder._item_reg, before_registration)
        self.assertTrue(holder.on_field)
        CSV.resolve_pending(engine, holder, "eject_button", accept=True)
        self.assert_consumed(engine, holder, obj, "item/eject_button:free-switch")

    def test_destroyed_balloon_keeps_physical_remnant_and_no_stock_debit(self):
        _, engine, attacker, holder, obj = self.fixture("item/풍선")
        engine.resolve_attack_damage(attacker, holder, engine.r.move("move/몸통박치기"), set_damage=True)
        self.assertEqual(obj["destroyed"]["source"], "item/풍선:attack-hit")
        self.assertEqual(obj["carrier_id"], holder.entity_id)
        self.assertEqual(holder.spec["_carried_load"]["objects"], [{"id": obj["id"], "weight_kg": 1}])
        self.assertNotIn("consumed", obj)
        self.assertFalse(holder.spec.get("stock_consumption_receipts"))

    def test_ordinary_quantity_and_held_stock_keep_existing_payment_behavior(self):
        helper, engine, _, holder, obj = self.fixture("item/탈출버튼")
        holder.spec["items"]["오랭열매"] = 2
        paid = GRANTS.transition(engine, holder, lambda e, c: STOCK.debit(e, c, STOCK.prepare(e, c, "item/오랭열매")))
        self.assertEqual(paid["kind"], "quantity")
        self.assertEqual(holder.spec["items"]["오랭열매"], 1)
        paid = GRANTS.transition(engine, holder, lambda e, c: STOCK.debit(e, c,
            STOCK.prepare(e, c, obj["item_rule_id"], held_selection=obj["id"])))
        self.assertEqual(paid["kind"], "held_instance")
        self.assertEqual(len(holder.spec["stock_consumption_receipts"]), 2)
        self.assertNotIn("trigger", obj["consumed"])
        self.assertEqual(holder.spec["_carried_load"]["objects"], [])

    def test_json_restore_keeps_terminal_original_and_reaction_completion(self):
        _, engine, attacker, holder, obj = self.fixture("item/레드카드")
        engine.resolve_attack_damage(attacker, holder, engine.r.move("move/몸통박치기"), set_damage=True)
        restored = CODEC.load_engine(engine.r, CODEC.dump_engine(engine))
        restored_holder = WORLD.actor_index(restored)[holder.entity_id]
        restored_attacker = WORLD.actor_index(restored)[attacker.entity_id]
        restored_obj = restored._physical_objects[obj["id"]]
        self.assert_consumed(restored, restored_holder, restored_obj, "item/레드카드:attack-hit")
        CSV.resolve_pending(restored, restored_holder, "red_card", accept=True)
        self.assertFalse(restored_attacker.on_field)
        with self.assertRaisesRegex(ValueError, "live remaining-item reaction"):
            CSV.resolve_pending(restored, restored_holder, "red_card", accept=True)
        self.assertEqual(len(restored_holder.spec["stock_consumption_receipts"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
