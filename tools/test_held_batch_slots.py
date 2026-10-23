"""Public stock batches retain each actual source's eligible equipment slots."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys
import unittest

OVERLAY = Path(__file__).resolve().parents[1]
ROOT = OVERLAY if (OVERLAY / "data").is_dir() and (OVERLAY / "output").is_dir() else Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(OVERLAY / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]
import item_stock as STOCK
import test_category2_csv_remaining_item_contracts as FIX
import items as ITEMS
import capability_actions as CAP
import state_grants as GRANTS
import world_entities as WORLD
import state_codec as CODEC


class HeldBatchSlotsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.RemainingCsvItemContractTests.setUpClass()

    def fixture(self):
        helper = FIX.RemainingCsvItemContractTests()
        actor = helper.trainer("batch-slots")
        engine = helper.fixture(actor)
        for uid, held in (("batch/accessory", False), ("batch/held", True)):
            helper.equip(engine, actor, uid, "item/달인의띠", held=held)
        self.assertEqual({row["instance_id"] for row in ITEMS.equipment_options(actor, ("held", "장신구"))},
                         {"batch/accessory", "batch/held"})
        CAP.set_carried(engine, actor, [{"id": uid, "weight_kg": 1}
            for uid in ("batch/accessory", "batch/held")], "weighed actual batch")
        prepared = STOCK.prepare(engine, actor, "item/달인의띠",
            held_selection=["batch/accessory", "batch/held"], count=2,
            equipment_slots=("held", "장신구"))
        return engine, actor, prepared

    def test_public_prepared_batch_consumes_actual_accessory_and_held(self):
        engine, actor, prepared = self.fixture()
        self.assertEqual([entry["equipment_slots"] for entry in prepared["entries"]],
                         [["held", "장신구"], ["held", "장신구"]])
        paid = GRANTS.transition(engine, actor, lambda e, c: STOCK.debit(e, c, prepared))
        self.assertEqual((paid["kind"], paid["count"]), ("held_batch", 2))
        self.assertEqual({item["instance_id"] for item in paid["items"]}, {"batch/accessory", "batch/held"})
        self.assertFalse(ITEMS.equipment_options(actor, ("held", "장신구")))
        self.assertEqual(actor.spec["_carried_load"]["objects"], [])
        self.assertEqual(len(actor.spec["stock_consumption_receipts"]), 1)
        for uid in ("batch/accessory", "batch/held"):
            self.assertIn("consumed", engine._physical_objects[uid])
            self.assertNotIn("carrier_id", engine._physical_objects[uid])
        self.assertTrue(engine.validate_state()["valid"])

    def test_batch_preflight_duplicate_stale_slots_and_late_failure_are_atomic(self):
        engine, actor, prepared = self.fixture()
        before = CODEC.dump_engine(engine)
        for invalid in ("duplicate", "stale_slots"):
            changed = deepcopy(prepared)
            if invalid == "duplicate":
                changed["entries"][1] = deepcopy(changed["entries"][0])
            else:
                changed["entries"][0]["equipment_slots"] = ["held"]
            with self.assertRaises(ValueError), patch.object(ITEMS, "_unregister_selected") as removed:
                GRANTS.transition(engine, actor, lambda e, c: STOCK.debit(e, c, changed))
            removed.assert_not_called()
            self.assertEqual(CODEC.dump_engine(engine), before)
        finish = WORLD.finish_physical_use
        calls = []
        def fail_second(e, obj, *args, **kwargs):
            calls.append(obj["id"])
            if len(calls) == 2:
                raise ValueError("late batch terminal failure")
            return finish(e, obj, *args, **kwargs)
        with patch.object(WORLD, "finish_physical_use", side_effect=fail_second):
            with self.assertRaisesRegex(ValueError, "late batch terminal failure"):
                GRANTS.transition(engine, actor, lambda e, c: STOCK.debit(e, c, prepared))
        self.assertEqual(calls, ["batch/accessory", "batch/held"])
        self.assertEqual(CODEC.dump_engine(engine), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)

