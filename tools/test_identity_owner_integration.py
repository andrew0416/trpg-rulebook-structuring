"""Native registrations use the complete existing world identity index."""
from pathlib import Path
from copy import deepcopy
import sys
import unittest
from unittest.mock import patch

OVERLAY = Path(__file__).resolve().parents[1]
ROOT = OVERLAY if (OVERLAY / "data").is_dir() and (OVERLAY / "output").is_dir() else Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(OVERLAY / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]
import partial_entities as PARTIAL
import pokemon_entities as POKEMON
import test_category2_csv_remaining_item_contracts as FIX
import world_entities as WORLD
import state_codec as CODEC
import pokemon_party as PARTY


class IdentityOwnerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.RemainingCsvItemContractTests.setUpClass()

    def fixture(self):
        helper = FIX.RemainingCsvItemContractTests()
        owner = helper.trainer("identity-owner")
        engine = helper.fixture(owner)
        return engine, owner, self.actual_stores(engine, owner)

    def actual_stores(self, engine, owner):
        WORLD.register_object(engine, "identity/physical", location={"kind": "unknown"}, reason="actual object")
        engine.gm.observe_partial_entity(name="partial", actor_kind="object", entity_id="identity/partial", reason="actual partial")
        egg = POKEMON.prepare_egg(engine, owner, {"id": "egg", "source": "GM observation", "hatched": False})
        owner.spec["eggs"] = [egg]
        fossil = POKEMON.prepare_fossil(engine, owner, "f1", {"species": "pokemon/암나이트", "status": "fossil"})
        owner.spec["fossils"] = {"f1": fossil}
        return {"actor": owner.entity_id, "physical": "identity/physical",
            "partial": "identity/partial", "egg": egg["entity_id"], "fossil": fossil["entity_id"]}

    def test_native_partial_observation_rejects_fossil_before_recording(self):
        engine, owner, ids = self.fixture()
        before = CODEC.dump_engine(engine)
        with self.assertRaises(ValueError):
            engine.gm.observe_partial_entity(name="collision", actor_kind="object",
                entity_id=ids["fossil"], reason="must retain actual fossil")
        self.assertEqual(CODEC.dump_engine(engine), before)
        self.assertNotIn(ids["fossil"], engine._partial_entities)

    def test_partial_registration_rejects_every_other_actual_store(self):
        for kind in ("actor", "physical", "partial", "egg", "fossil"):
            with self.subTest(kind=kind):
                engine, owner, ids = self.fixture()
                before = CODEC.dump_engine(engine)
                with self.assertRaises(ValueError):
                    engine.gm.observe_partial_entity(name="collision", actor_kind="object",
                        entity_id=ids[kind], reason="actual existing identity")
                self.assertEqual(CODEC.dump_engine(engine), before)

    def test_native_egg_producer_rejects_every_actual_store_without_mutation(self):
        for kind in ("actor", "physical", "partial", "egg", "fossil"):
            with self.subTest(kind=kind):
                engine, owner, ids = self.fixture()
                before = CODEC.dump_engine(engine)
                with patch.object(POKEMON.F, "new_id", return_value=ids[kind]):
                    with self.assertRaises(ValueError):
                        engine.pokemon_activity(owner, "observe_egg", egg_id="new-egg", reason="new actual egg")
                self.assertEqual(CODEC.dump_engine(engine), before)

    def test_fossil_preparation_rejects_every_foreign_actual_store(self):
        for kind in ("actor", "physical", "partial", "egg", "fossil"):
            with self.subTest(kind=kind):
                engine, owner, ids = self.fixture()
                before = CODEC.dump_engine(engine)
                with self.assertRaises(ValueError):
                    POKEMON.prepare_fossil(engine, owner, "different-source", {
                        "entity_id": ids[kind], "species": "pokemon/암나이트", "status": "fossil"})
                self.assertEqual(CODEC.dump_engine(engine), before)

    def test_same_fossil_original_can_be_prepared_again_without_identity_change(self):
        engine, owner, ids = self.fixture()
        original = owner.spec["fossils"]["f1"]
        prepared = POKEMON.prepare_fossil(engine, owner, "f1", original)
        self.assertEqual(prepared["entity_id"], ids["fossil"])
        self.assertEqual(prepared, original)
        self.assertIs(owner.spec["fossils"]["f1"], original)
        self.assertIsNot(prepared, original)

    def test_partial_self_exclusion_and_weak_parent_survive_native_restore(self):
        engine, owner, ids = self.fixture()
        view = engine.gm.observe_partial_entity(name="weak part", actor_kind="object", parent_id=ids["partial"],
            known={"hp": 4}, reason="actual HP-only part")
        engine.gm.update_partial_entity(view["entity_id"], facts={"hp": 2}, reason="actual resolved loss")
        PARTIAL.validate_world(engine)
        restored = CODEC.load_engine(engine.r, CODEC.dump_engine(engine))
        self.assertEqual(PARTIAL.project(restored, view["entity_id"])["known"], {"hp": 2})
        self.assertEqual(len(WORLD.entity_index(restored)), 6)
        with self.assertRaisesRegex(ValueError, "complete combat actor"):
            PARTIAL.require_complete(restored._partial_entities[view["entity_id"]], "attack")

    def test_native_reserve_registration_rejects_all_actual_entity_stores(self):
        engine, owner, ids = self.fixture()
        PARTY.configure(engine, owner, mode="standard", roster=[],
            storage={"kind": "center", "id": "actual-center"}, reason="actual reserve policy")
        before = CODEC.dump_engine(engine)
        for kind, identity in ids.items():
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, "reserve identity"):
                    engine.pokemon_activity(owner, "register_owned_reserve", pokemon_id=identity,
                        species="브케인", location="storage", reason="existing world identity")
                self.assertEqual(CODEC.dump_engine(engine), before)
        row = engine.pokemon_activity(owner, "register_owned_reserve", pokemon_id="reserve/new",
            species="브케인", location="storage", reason="actual stored reserve")
        self.assertTrue(row["sheet_pending"])
        self.assertNotIn("stats", row)
        restored = CODEC.load_engine(engine.r, CODEC.dump_engine(engine))
        self.assertEqual(PARTY.registry(restored, restored.everyone[0]), PARTY.registry(engine, owner))

    def test_native_carried_observation_rejects_foreign_stores_and_reuses_physical_body(self):
        for kind in ("actor", "partial", "egg", "fossil"):
            with self.subTest(kind=kind):
                engine, owner, ids = self.fixture()
                before = CODEC.dump_engine(engine)
                with self.assertRaisesRegex(ValueError, "identity collides"):
                    engine.gm.set_carried_objects(owner, [{"id": ids[kind], "weight_kg": 1}],
                        reason="must keep the existing world entity")
                self.assertEqual(CODEC.dump_engine(engine), before)
        engine, owner, ids = self.fixture()
        body = engine._physical_objects[ids["physical"]]
        for weight in (1, 2):
            engine.gm.set_carried_objects(owner, [{"id": ids["physical"], "weight_kg": weight}],
                reason="same actual physical body")
            self.assertIs(engine._physical_objects[ids["physical"]], body)
            self.assertEqual(body["carrier_id"], owner.entity_id)
        engine.gm.set_carried_objects(owner, [], reason="actual release")
        self.assertNotIn("carrier_id", body)
        self.assertEqual(len(WORLD.entity_index(engine)), 5)

    def test_native_multipart_rejects_foreign_stores_and_preserves_same_parent_replacement(self):
        engine, owner, ids = self.fixture()
        helper = FIX.RemainingCsvItemContractTests()
        parts = [helper.pokemon("actual-part-1"), helper.pokemon("actual-part-2")]
        for actor in parts:
            engine.gm.add_combatant(actor)
        part_ids = [actor.entity_id for actor in parts]
        before = CODEC.dump_engine(engine)
        for kind, identity in ids.items():
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    engine.gm.set_multipart_entity(parent_id=identity, part_ids=part_ids,
                        reason="existing actual entity cannot become a multipart parent")
                self.assertEqual(CODEC.dump_engine(engine), before)
        engine.gm.set_multipart_entity(parent_id="multipart/actual", part_ids=part_ids,
            reason="actual independent parts")
        parent = engine._physical_objects["multipart/actual"]
        engine.gm.set_multipart_entity(parent_id="multipart/actual", part_ids=list(reversed(part_ids)),
            reason="same actual parent with observed part order")
        self.assertIs(engine._physical_objects["multipart/actual"], parent)
        self.assertEqual(parent["part_ids"], list(reversed(part_ids)))
        self.assertEqual([actor.spec["multipart_parent_id"] for actor in parts], ["multipart/actual"] * 2)

    def test_native_regional_creation_rejects_all_actual_entity_stores(self):
        from test_category3_batch14_pokemon import Tests as RegionalFixture
        RegionalFixture.setUpClass()
        try:
            helper = RegionalFixture()
            for kind in ("actor", "physical", "partial", "egg", "fossil"):
                with self.subTest(kind=kind):
                    helper.setUp()
                    ids = self.actual_stores(helper.e, helper.a)
                    before = CODEC.dump_engine(helper.e)
                    with self.assertRaisesRegex(ValueError, "individual identity"):
                        helper.region(individual_id=ids[kind])
                    self.assertEqual(CODEC.dump_engine(helper.e), before)
        finally:
            RegionalFixture.tearDownClass()

    def test_native_special_observation_rejects_foreign_stores_and_preserves_batch_reobservation(self):
        from engine import Rules
        from test_category2_special_entities import SpecialTests
        import special_entities as SPECIAL
        helper = SpecialTests()
        helper.poly = Rules(ROOT, ruleset="polygon")
        for kind in ("actor", "partial", "egg", "fossil"):
            with self.subTest(kind=kind):
                helper.setUp()
                ids = self.actual_stores(helper.e, helper.a)
                before = CODEC.dump_engine(helper.e)
                with self.assertRaisesRegex(ValueError, "identity collides"):
                    SPECIAL.observe(helper.e, helper.bot(ids[kind]), reason="existing actual identity")
                self.assertEqual(CODEC.dump_engine(helper.e), before)
        helper.setUp()
        bot = helper.bot("actual/bot")
        SPECIAL.observe(helper.e, bot, reason="actual bot observed")
        body = helper.e._physical_objects[bot["id"]]
        bot["hp"] -= 1
        SPECIAL.observe_batch(helper.e, [bot], reason="same actual bot with observed damage")
        self.assertIs(helper.e._physical_objects[bot["id"]], body)
        self.assertEqual(body["hp"], bot["hp"])

    def test_native_pickup_collision_keeps_original_and_all_costs_unchanged(self):
        from test_category2_pickup_item_copy import PickupItemCopyTests
        import pickup_item_copy as PICKUP
        PickupItemCopyTests.setUpClass()
        helper = PickupItemCopyTests()
        engine, user, target = helper.fixture()
        identity = "pickup-copy:" + user.entity_id + ":1"
        engine.gm.observe_partial_entity(name="actual existing partial", actor_kind="object",
            entity_id=identity, reason="actual identity already observed")
        before = CODEC.dump_engine(engine)
        with self.assertRaises(ValueError):
            PICKUP.activate(engine, user, "픽업", target, held_selection="original")
        self.assertEqual(CODEC.dump_engine(engine), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
