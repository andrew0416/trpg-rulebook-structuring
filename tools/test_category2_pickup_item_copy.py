"""R0173/R0174/R0455 physical held-item reuse and Pickup lifetime tests."""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine"))

from engine import Engine
from tools import test_category2_equipment_protection as FIX
import held_equipment as HELD
import item_stock as STOCK
import items as ITEMS
import pickup_item_copy as PICKUP
import state_grants as GRANTS
import world_entities as WORLD


ROW_HASHES = {
    173: "42b52b4f29c2fb0888319dc6628aad0d4a2b22e20d3a9496a58e7f33e19ea9cb",
    174: "c3b5ee48b8eed546de73a738e7d3d5978275931966e55185fd7f58dc851a74ae",
    455: "bbfb4bdebcf8cd6a2610a22cf5cacb771324e096ac6d62fa06c47ae96116a016",
    555: "42b52b4f29c2fb0888319dc6628aad0d4a2b22e20d3a9496a58e7f33e19ea9cb",
}


class PickupItemCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.ProtectionTests.setUpClass()
        cls.fixture_owner = FIX.ProtectionTests()

    def fixture(self, *, item="선제공격손톱", user_abilities=("픽업",), target_abilities=()):
        engine, user, target, _ = self.fixture_owner.fixture(
            "몸통박치기", held=(None, None), abilities=((), ())
        )
        GRANTS.replace_baseline(engine, user, "abilities", list(user_abilities))
        GRANTS.replace_baseline(engine, target, "abilities", list(target_abilities))
        if item:
            self.add(engine, target, item, "original")
        engine.start_round([user, target])
        engine.start_of_turn(user)
        return engine, user, target

    def add(self, engine, actor, name, instance_id, slot=None):
        WORLD.register_object(
            engine, instance_id, location={"kind": "unknown"}, reason="test actual held item",
            kind="item_instance", item_rule_id="item/" + name, owner_id=actor.entity_id,
        )
        ITEMS.register_item(engine, actor, name, source_instance_id=instance_id,
                            as_held=True, held_slot=slot)
        return instance_id

    def valid(self, engine):
        state = engine.validate_state()
        self.assertTrue(state["valid"], state["issues"])

    def roundtrip(self, engine):
        return Engine.import_state(engine.r, json.loads(json.dumps(engine.export_state())))

    def consume_copy(self, engine, actor, copy_id, item_id):
        prepared = STOCK.prepare(engine, actor, item_id, held_selection=copy_id)
        return GRANTS.transition(engine, actor, lambda staged, user: STOCK.debit(staged, user, prepared))

    def test_exact_source_rows_duplicate_denominator_and_reviewed_registration(self):
        raw = (ROOT / "input/db/abilities.csv").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae")
        with (ROOT / "input/db/abilities.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        for record, expected in ROW_HASHES.items():
            actual = hashlib.sha256(json.dumps(rows[record - 1], ensure_ascii=False,
                                               separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(actual, expected)
        self.assertEqual(rows[172][0], rows[554][0])
        self.assertEqual(rows[172], rows[554])
        self.assertEqual(PICKUP.registration(self.fixture_owner.r, "픽업")["source_id"], "ability/픽업")
        for source in ("배달부", "ability/배달부", "ability/배달부-2", "배달새", "ability/배달새"):
            import held_equipment
            self.assertIsNotNone(held_equipment.registration(self.fixture_owner.r, source))

    def test_scavenger_grant_and_selected_two_held_original_with_actual_copy_effect(self):
        engine, user, target = self.fixture(item=None, target_abilities=("배달부",))
        self.add(engine, target, "예리한손톱", "first", "held:1")
        self.add(engine, target, "선제공격손톱", "second", "held:2")
        self.assertIn("청소부", GRANTS.effective_capabilities(user))
        before = deepcopy((user.spec, user.budget, engine._physical_objects, engine.log_lines))
        pending = engine.activate_ability(user, "픽업", target)
        self.assertEqual(pending.basis["chooser_id"], target.entity_id)
        self.assertEqual((user.budget, engine._physical_objects, engine.log_lines), before[1:])
        initial = user.initiative_bonus
        receipt = engine.resolve_pickup_choice(target, pending.basis["choice_id"], selection="second")
        self.assertEqual(receipt["original_instance_id"], "second")
        self.assertEqual(receipt["destination_slot"], "held:1")
        self.assertEqual(user.initiative_bonus, initial + 10)
        self.assertEqual({row["instance_id"] for row in HELD.entries(target)}, {"first", "second"})
        copy = engine._physical_objects[receipt["copy_instance_id"]]
        self.assertEqual(copy["pickup_copy"]["original_instance_id"], "second")
        self.assertEqual(copy["item_rule_id"], "item/선제공격손톱")
        self.valid(engine)
        GRANTS.replace_baseline(engine, user, "abilities", [])
        self.assertNotIn("청소부", GRANTS.effective_capabilities(user))

    def test_delivery_capacity_supplies_real_destination_slot_and_scene_cost(self):
        for capacity in ("배달부", "배달새"):
            with self.subTest(capacity=capacity):
                engine, user, target = self.fixture(user_abilities=("픽업", capacity))
                self.add(engine, user, "예리한손톱", "user-existing", "held:1")
                receipt = engine.activate_ability(
                    user, "ability/픽업", target,
                    held_selection="original", destination_slot="held:2",
                )
                self.assertEqual({row["slot_id"] for row in HELD.entries(user)}, {"held:1", "held:2"})
                self.assertEqual(receipt["destination_slot"], "held:2")
                self.assertEqual(user.budget["swift"], 0)
                quota = user.spec["frequency_state"]["activations"]["ability:픽업"]
                self.assertEqual((quota["kind"], quota["used"]), ("scene", 1))
                before = deepcopy((user.spec, user.budget, engine._physical_objects))
                with self.assertRaises(ValueError):
                    engine.activate_ability(user, "픽업", target, held_selection="original")
                self.assertEqual((user.spec, user.budget, engine._physical_objects), before)
                self.valid(engine)

    def test_range_slot_source_and_handler_failures_are_atomic(self):
        engine, user, target = self.fixture()
        cases = []
        target.pos = (6, 0)
        cases.append(lambda: engine.activate_ability(user, "픽업", target, held_selection="original"))
        for call in cases:
            before = deepcopy((user.spec, user.budget, engine._physical_objects, engine.log_lines))
            with self.assertRaises(ValueError):
                call()
            self.assertEqual((user.spec, user.budget, engine._physical_objects, engine.log_lines), before)
        target.pos = (1, 0)
        before = deepcopy((user.spec, user.budget, engine._physical_objects, engine.log_lines))
        import effects_ext
        with self.assertRaisesRegex(ValueError, "physical-instance adapter"):
            effects_ext.h_copy_item(engine, user, target, PICKUP.COPY_EFFECT,
                                    {"source_id": "ability/다른출처"})
        self.assertEqual((user.spec, user.budget, engine._physical_objects, engine.log_lines), before)
        GRANTS.replace_baseline(engine, user, "abilities", [])
        before = deepcopy((user.spec, user.budget, engine._physical_objects))
        with self.assertRaises(ValueError):
            engine.activate_ability(user, "픽업", target, held_selection="original")
        self.assertEqual((user.spec, user.budget, engine._physical_objects), before)

    def test_nonconsumable_copy_expires_and_original_remains(self):
        engine, user, target = self.fixture()
        receipt = engine.activate_ability(user, "픽업", target, held_selection="original")
        copy_id = receipt["copy_instance_id"]
        engine.end_encounter([user, target])
        self.assertIn("destroyed", engine._physical_objects[copy_id])
        self.assertNotIn("destroyed", engine._physical_objects["original"])
        self.assertFalse(HELD.entries(user))
        history = user.spec[PICKUP.HISTORY][0]
        self.assertEqual((history["copy_terminal"], history["original_terminal"]),
                         ("destroyed", "retained"))
        self.valid(engine)

    def test_unconsumed_consumable_copy_destroys_copy_and_original(self):
        engine, user, target = self.fixture(item="상처약")
        receipt = engine.activate_ability(user, "픽업", target, held_selection="original")
        engine.end_encounter([user, target])
        self.assertIn("destroyed", engine._physical_objects[receipt["copy_instance_id"]])
        self.assertIn("destroyed", engine._physical_objects["original"])
        self.assertFalse(HELD.entries(user))
        self.assertFalse(HELD.entries(target))
        self.valid(engine)

    def test_sticky_original_survives_pickup_expiry_and_both_native_restores(self):
        engine, user, target = self.fixture(item='상처약', target_abilities=('점착',))
        receipt = engine.activate_ability(user,'픽업',target,held_selection='original')
        before = deepcopy(engine._physical_objects['original'])
        engine.gm.snapshot('protected original')
        engine.end_encounter([user,target])
        self.assertEqual(engine._physical_objects['original'],before)
        self.assertIn('destroyed',engine._physical_objects[receipt['copy_instance_id']])
        self.assertEqual(user.spec[PICKUP.HISTORY][0]['original_terminal'],'retained_protected')
        engine.gm.restore('protected original',reason='restore actual linked copies before boundary')
        loaded = self.roundtrip(engine);actors=WORLD.actor_index(loaded)
        loaded.end_encounter(list(actors.values()))
        self.assertEqual(loaded._physical_objects['original'],before)
        self.assertEqual(HELD.entries(actors[target.entity_id])[0]['instance_id'],'original')
        self.assertEqual(actors[user.entity_id].spec[PICKUP.HISTORY][0]['original_terminal'],'retained_protected')
        self.assertFalse(actors[user.entity_id].spec[PICKUP.ACTIVE]);self.valid(loaded)

    def test_pickup_original_protection_is_evaluated_at_boundary_not_at_copy_time(self):
        for originally_protected in (False,True):
            with self.subTest(originally_protected=originally_protected):
                engine,user,target=self.fixture(item='상처약',target_abilities=('점착',) if originally_protected else ())
                receipt=engine.activate_ability(user,'픽업',target,held_selection='original')
                GRANTS.replace_baseline(engine,target,'abilities',[] if originally_protected else ['점착'])
                engine.end_encounter([user,target])
                self.assertEqual('destroyed' in engine._physical_objects['original'],originally_protected)
                self.assertIn('destroyed',engine._physical_objects[receipt['copy_instance_id']])
                self.assertEqual(user.spec[PICKUP.HISTORY][0]['original_terminal'],
                                 'destroyed' if originally_protected else 'retained_protected')
                self.valid(engine)

    def test_transferred_original_uses_current_holder_sticky_protection(self):
        engine,user,target,receiver,_=self.fixture_owner.fixture(
            '몸통박치기',held=(None,None,None),abilities=((),(),()))
        GRANTS.replace_baseline(engine,user,'abilities',['픽업'])
        GRANTS.replace_baseline(engine,receiver,'abilities',['점착'])
        self.add(engine,target,'상처약','original')
        engine.start_round([user,target,receiver]);engine.start_of_turn(user)
        receipt=engine.activate_ability(user,'픽업',target,held_selection='original')
        ITEMS.transfer_equipment(engine,target,receiver,'original')
        before=deepcopy(engine._physical_objects['original'])
        engine.end_encounter([user,target,receiver])
        self.assertEqual(engine._physical_objects['original'],before)
        self.assertEqual(HELD.entries(receiver)[0]['instance_id'],'original')
        self.assertIn('destroyed',engine._physical_objects[receipt['copy_instance_id']]);self.valid(engine)

    def test_consumed_copy_uses_item_stock_and_preserves_original(self):
        engine, user, target = self.fixture(item="상처약")
        receipt = engine.activate_ability(user, "픽업", target, held_selection="original")
        copy_id = receipt["copy_instance_id"]
        self.consume_copy(engine, user, copy_id, "item/상처약")
        self.assertEqual(engine._physical_objects[copy_id]["consumed"]["source"], "item/상처약")
        engine.end_encounter([user, target])
        self.assertNotIn("destroyed", engine._physical_objects["original"])
        self.assertEqual(user.spec[PICKUP.HISTORY][0]["original_terminal"],
                         "retained_copy_consumed")
        self.valid(engine)

    def test_dropped_copy_still_expires_by_physical_identity(self):
        engine, user, target = self.fixture()
        receipt = engine.activate_ability(user, "픽업", target, held_selection="original")
        copy_id = receipt["copy_instance_id"]
        ITEMS.drop_item(engine, user, selection=copy_id)
        self.assertNotIn("equipped_by", engine._physical_objects[copy_id])
        engine.end_encounter([user, target])
        self.assertIn("destroyed", engine._physical_objects[copy_id])
        self.valid(engine)

    def test_copy_survives_pickup_loss_or_suppression_until_encounter_end(self):
        for mode in ("lost", "suppressed"):
            with self.subTest(mode=mode):
                engine, user, target = self.fixture()
                initial = user.initiative_bonus
                receipt = engine.activate_ability(user, "픽업", target, held_selection="original")
                copy_id = receipt["copy_instance_id"]
                self.assertEqual(user.initiative_bonus, initial + 10)
                if mode == "lost":
                    GRANTS.replace_baseline(engine, user, "abilities", [])
                    self.assertNotIn("픽업", user.abilities)
                else:
                    user.abilities_suppressed = True
                self.assertEqual(ITEMS.selected_equipment(user, copy_id, ("held",))["instance_id"], copy_id)
                self.assertNotIn("destroyed", engine._physical_objects[copy_id])
                engine.end_encounter([user, target])
                self.assertIn("destroyed", engine._physical_objects[copy_id])
                self.assertEqual(user.spec[PICKUP.HISTORY][0]["copy_terminal"], "destroyed")
                self.valid(engine)

    def test_original_terminal_first_is_not_repeated_at_boundary(self):
        for terminal in ("consumed", "destroyed"):
            with self.subTest(terminal=terminal):
                engine, user, target = self.fixture(item="상처약")
                receipt = engine.activate_ability(user, "픽업", target, held_selection="original")
                if terminal == "consumed":
                    self.consume_copy(engine, target, "original", "item/상처약")
                else:
                    ITEMS.destroy_equipment(engine, target, "original", reason="test observed destruction")
                evidence = deepcopy(engine._physical_objects["original"])
                engine.end_encounter([user, target])
                self.assertEqual(engine._physical_objects["original"], evidence)
                history = user.spec[PICKUP.HISTORY][0]
                self.assertEqual(history["original_terminal"], terminal)
                self.assertEqual(history["copy_terminal"], "destroyed")
                self.assertIn("destroyed", engine._physical_objects[receipt["copy_instance_id"]])
                self.valid(engine)

    def test_different_users_and_copies_have_independent_lifetimes(self):
        engine, user1, user2, target1, target2, _ = self.fixture_owner.fixture(
            "몸통박치기", held=(None, None, None, None), abilities=((), (), (), ())
        )
        for actor in (user1, user2):
            GRANTS.replace_baseline(engine, actor, "abilities", ["픽업"])
        self.add(engine, target1, "상처약", "original-1")
        self.add(engine, target2, "상처약", "original-2")
        engine.start_round([user1, user2, target1, target2])
        engine.start_of_turn(user1)
        first = engine.activate_ability(user1, "픽업", target1, held_selection="original-1")
        engine.end_of_turn(user1)
        engine.start_of_turn(user2)
        second = engine.activate_ability(user2, "픽업", target2, held_selection="original-2")
        self.assertNotEqual(first["copy_instance_id"], second["copy_instance_id"])
        self.consume_copy(engine, user1, first["copy_instance_id"], "item/상처약")
        self.assertNotIn("consumed", engine._physical_objects[second["copy_instance_id"]])
        engine.end_of_turn(user2)
        engine.end_encounter([user1, user2, target1, target2])
        self.assertNotIn("destroyed", engine._physical_objects["original-1"])
        self.assertIn("destroyed", engine._physical_objects["original-2"])
        self.assertEqual(user1.spec[PICKUP.HISTORY][0]["original_terminal"],
                         "retained_copy_consumed")
        self.assertEqual(user2.spec[PICKUP.HISTORY][0]["original_terminal"], "destroyed")
        self.valid(engine)

    def test_same_rule_duplicate_uses_existing_pending_path_without_stacking(self):
        engine, user, target = self.fixture(user_abilities=("픽업", "배달부"))
        self.add(engine, user, "선제공격손톱", "user-existing", "held:1")
        initial = user.initiative_bonus
        receipt = engine.activate_ability(
            user, "픽업", target, held_selection="original", destination_slot="held:2"
        )
        copy_row = HELD.select(user, receipt["copy_instance_id"])
        self.assertTrue(copy_row["effects_pending"])
        self.assertEqual(user.initiative_bonus, initial)
        self.assertEqual(HELD.pending(user), [{
            "kind": "identical_effect_stacking",
            "slots": ["held:2"],
            "resolution": "same-rule objects are distinct; stacking is not stated by capacity source",
        }])
        self.valid(engine)

    def test_empty_target_and_foreign_actual_actor_are_rejected_atomically(self):
        engine, user, empty = self.fixture(item=None)
        before = deepcopy((user.spec, user.budget, engine._physical_objects, engine.log_lines))
        with self.assertRaises(ValueError):
            engine.activate_ability(user, "픽업", empty)
        self.assertEqual((user.spec, user.budget, engine._physical_objects, engine.log_lines), before)

        other, _, foreign, _ = self.fixture_owner.fixture(
            "몸통박치기", held=(None, None), abilities=((), ())
        )
        self.add(other, foreign, "선제공격손톱", "foreign-original")
        before = deepcopy((user.spec, user.budget, engine._physical_objects, engine.log_lines))
        with self.assertRaises(ValueError):
            engine.activate_ability(user, "픽업", foreign, held_selection="foreign-original")
        self.assertEqual((user.spec, user.budget, engine._physical_objects, engine.log_lines), before)
        self.valid(engine)

    def test_transferred_copy_expires_from_current_holder_by_identity(self):
        engine, user, target, receiver, _ = self.fixture_owner.fixture(
            "몸통박치기", held=(None, None, None), abilities=((), (), ())
        )
        GRANTS.replace_baseline(engine, user, "abilities", ["픽업"])
        self.add(engine, target, "선제공격손톱", "original")
        engine.start_round([user, target, receiver])
        engine.start_of_turn(user)
        receipt = engine.activate_ability(user, "픽업", target, held_selection="original")
        copy_id = receipt["copy_instance_id"]
        transfer = ITEMS.transfer_equipment(engine, user, receiver, copy_id)
        self.assertEqual(transfer["instance_id"], copy_id)
        self.assertEqual(engine._physical_objects[copy_id]["equipped_by"], receiver.entity_id)
        self.assertEqual(ITEMS.selected_equipment(receiver, copy_id, ("held",))["instance_id"], copy_id)
        engine.end_encounter([user, target, receiver])
        self.assertIn("destroyed", engine._physical_objects[copy_id])
        self.assertFalse(HELD.entries(receiver))
        self.valid(engine)

    def test_gm_restore_and_json_roundtrip_preserve_link_then_expire_once(self):
        engine, user, target = self.fixture()
        receipt = engine.activate_ability(user, "픽업", target, held_selection="original")
        copy_id = receipt["copy_instance_id"]
        engine.gm.snapshot("pickup-active")
        ITEMS.drop_item(engine, user, selection=copy_id)
        engine.gm.restore("pickup-active", reason="rewind physical Pickup copy")
        self.assertEqual(ITEMS.selected_equipment(user, copy_id, ("held",))["instance_id"], copy_id)
        loaded = self.roundtrip(engine)
        index = WORLD.actor_index(loaded)
        loaded_user = index[user.entity_id]
        self.assertEqual(loaded._physical_objects[copy_id]["pickup_copy"]["original_instance_id"], "original")
        loaded.end_encounter(list(index.values()))
        self.assertEqual(len(loaded_user.spec[PICKUP.HISTORY]), 1)
        self.valid(loaded)

    def test_tampered_original_link_is_rejected_before_save_or_boundary(self):
        engine, user, target = self.fixture()
        receipt = engine.activate_ability(user, "픽업", target, held_selection="original")
        copy = engine._physical_objects[receipt["copy_instance_id"]]
        copy["pickup_copy"]["original_instance_id"] = "forged"
        state = engine.validate_state()
        self.assertFalse(state["valid"])
        self.assertIn("pickup_item_copy", {row["code"] for row in state["issues"]})
        with self.assertRaises(ValueError):
            engine.gm.snapshot("tampered")
        before = deepcopy((user.spec, engine._physical_objects, engine.encounter_active))
        with self.assertRaises(ValueError):
            engine.end_encounter([user, target])
        self.assertEqual((user.spec, engine._physical_objects, engine.encounter_active), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
