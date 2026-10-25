"""F24/F25/F26: independent learning, carried weapons, and battle quota upgrades."""
from copy import copy, deepcopy
import json
from pathlib import Path
import unittest

import test_category2_equipment_variant_contracts as BASE
import test_category2_optional_physical_equipment as CATALOG
import capability_actions as CAP
import equipment_variant_contracts as VARIANTS
import items as ITEMS
import optional_weapon_framework as WEAPONS
import state_grants as GRANTS
import turn as TURN
import world_entities as WORLD
from engine import Engine, Rules
from native_scenario_fixture import assert_rejected_unchanged


ROOT = Path(__file__).resolve().parents[1]
CANNONS = (("item/잽-블래스터", "move/전자포"), ("item/인페르노-캐논", "move/연옥"))
COATS = ("item/보강된-트렌치코트", "item/보강된-특수-트렌치코트")
ARMORS = ("item/마찰저하복", "item/특수마찰저하복")


class EquipmentPermissionsScopeRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all_rules = Rules(str(ROOT), ruleset="all")

    def setUp(self):
        self.r = Rules(str(ROOT), ruleset="core")
        self.f = BASE.EquipmentVariantContractTests()
        self.f.r = self.r

    def state(self, engine, uid):
        return engine._physical_objects[uid][VARIANTS.OBJECT_STATE]

    def restore(self, engine, *, fresh_rules=True):
        payload = json.loads(json.dumps(engine.export_state(), ensure_ascii=False))
        original = deepcopy(payload)
        rules = Rules(str(ROOT), ruleset=engine.r.ruleset.name) if fresh_rules else engine.r
        loaded = Engine.import_state(rules, payload)
        self.assertEqual(payload, original)
        return loaded

    def actual(self, engine, actor):
        return WORLD.actor_index(engine)[actor.entity_id]

    def bound_turn(self, engine, actor, target):
        engine.start_round([actor, target])
        engine.start_of_turn(actor, initiative_count=20)
        engine.apply_status(actor, "구속", source="gm/repair", applied_by=target)

    def next_battle(self, engine, actor, target):
        engine.end_of_turn(actor)
        engine.end_encounter([actor, target], round_elapsed_seconds=0)
        self.bound_turn(engine, actor, target)

    def session_fixture(self):
        engine = Engine(self.r, seed=65108, session_frequency=True, defer_session_refresh=False)
        actor = self.f.trainer("session-owner-" + str(id(engine)))
        target = self.f.trainer("session-target-" + str(id(engine)))
        engine.gm.add_combatant(actor); engine.gm.add_combatant(target)
        self.assertEqual(engine.begin_session("session-one", [actor, target]), "initialized")
        return engine, actor, target

    def legacy_used(self, item_id, *, inactive=False, unequipped=False, sessions=False):
        engine, actor, target = self.session_fixture() if sessions else self.f.fixture()
        uid = self.f.equip(engine, actor, item_id, "legacy-" + item_id)
        self.bound_turn(engine, actor, target)
        self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])
        state = self.state(engine, uid)
        state.pop("encounter_scope_version")
        state["encounter_uses"][0].pop("scope_version")
        state["encounter_uses"][0]["encounter"] = [engine.session_epoch, actor.spec["frequency_state"]["scene"]]
        if unequipped:
            ITEMS.unregister_item(engine, actor, item_id)
        if inactive:
            engine.end_of_turn(actor)
            engine.end_encounter([actor, target], round_elapsed_seconds=0)
        return engine, actor, target, uid

    def test_learned_cannons_repeat_native_use_and_json_without_spending_item(self):
        for item, move in CANNONS:
            with self.subTest(item=item):
                engine, actor, target = self.f.fixture(moves=(move,))
                uid = self.f.equip(engine, actor, item, "learned-" + item)
                for repeat in range(2):
                    engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
                    engine.d20 = lambda: 1
                    try:
                        engine.use_move(actor, target, move)
                    finally:
                        del engine.d20
                    self.assertEqual(actor.move_uses[move], repeat + 1)
                    self.assertEqual((self.state(engine, uid)["remaining_uses"], self.state(engine, uid)["use_history"]), (1, []))
                    engine.end_of_turn(actor)
                    if repeat == 0:
                        engine = self.restore(engine)
                        actor, target = self.actual(engine, actor), self.actual(engine, target)
                self.assertTrue(engine.validate_state()["valid"])

    def test_sourced_learning_preserves_charge_and_revoke_restores_permission_only_spending(self):
        for item, move in CANNONS:
            with self.subTest(item=item):
                engine, actor, target = self.f.fixture()
                uid = self.f.equip(engine, actor, item, "sourced-" + item)
                GRANTS.grant_moves(actor, [move], "gm/independent-learning", "gm", mode="learned")
                engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
                engine.d20 = lambda: 1
                try:
                    engine.use_move(actor, target, move)
                finally:
                    del engine.d20
                self.assertEqual(self.state(engine, uid)["remaining_uses"], 1)
                GRANTS.revoke(actor, "gm/independent-learning", engine=engine)
                engine.end_of_turn(actor)
                engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
                engine.d20 = lambda: 1
                try:
                    engine.use_move(actor, target, move)
                finally:
                    del engine.d20
                self.assertEqual(self.state(engine, uid)["remaining_uses"], 0)
                assert_rejected_unchanged(engine, lambda: engine.use_move(actor, target, move),
                                          reason_pattern="one-shot Move permission is spent")
                GRANTS.grant_moves(actor, [move], "gm/later-independent-learning", "gm", mode="learned")
                engine.end_of_turn(actor)
                engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
                engine.d20 = lambda: 1
                try:
                    engine.use_move(actor, target, move)
                finally:
                    del engine.d20
                self.assertEqual(actor.move_uses[move], 3)
                self.assertEqual((self.state(engine, uid)["remaining_uses"], len(self.state(engine, uid)["use_history"])), (0, 1))

    def weapon(self, engine, actor, uid):
        WORLD.register_object(engine, uid, location={"kind": "unknown"}, reason="observed weapon body",
                              owner_id=actor.entity_id, kind="physical_object")
        WEAPONS.observe_weapon(engine, actor, uid, name="repair sword", kind="소형 근접무기",
            grade="간단", arcane=False, metal=True, reason="actual observed metal weapon")

    def assert_concealment(self, engine, actor, uid):
        for method, status in (("visual", "concealed"), ("metal_detector", "concealed"),
                               ("manual_search", "detectable"), ("touch", "detectable")):
            self.assertEqual(VARIANTS.conceal_weapon(engine, actor, uid, method=method)["status"], status)

    def test_coats_reject_property_other_carrier_and_ground_weapon_but_admit_actual_profile(self):
        for item in COATS:
            with self.subTest(item=item):
                engine, actor, other = self.f.fixture()
                self.f.equip(engine, actor, item, "coat-" + item)
                uid = "repair/generic"
                WORLD.register_object(engine, uid, location={"kind": "unknown"}, reason="owned property, no weapon identity",
                                      owner_id=actor.entity_id)
                for carried in (False, True):
                    if carried:
                        CAP.set_carried(engine, actor, [{"id": uid, "weight_kg": 1}], "carried ordinary property")
                    assert_rejected_unchanged(engine, lambda: VARIANTS.conceal_weapon(engine, actor, uid, method="visual"),
                                              reason_pattern="actual (carried|identified) weapon")
                CAP.set_carried(engine, actor, [], "release ordinary property")
                weapon = "repair/profile"
                self.weapon(engine, actor, weapon)
                key = WEAPONS.equip(engine, actor, weapon)
                self.assert_concealment(engine, actor, weapon)
                TURN.unequip_weapon(engine, actor, key)
                assert_rejected_unchanged(engine, lambda: VARIANTS.conceal_weapon(engine, actor, weapon, method="visual"),
                                          reason_pattern="actual carried weapon")
                CAP.set_carried(engine, other, [{"id": weapon, "weight_kg": 1}], "other actor carries the owner's weapon")
                assert_rejected_unchanged(engine, lambda: VARIANTS.conceal_weapon(engine, actor, weapon, method="metal_detector"),
                                          reason_pattern="actual carried weapon")
                CAP.set_carried(engine, other, [], "other actor releases weapon")
                CAP.set_carried(engine, actor, [{"id": weapon, "weight_kg": 1}], "wearer carries observed weapon")
                engine = self.restore(engine, fresh_rules=False); actor = self.actual(engine, actor)
                self.assert_concealment(engine, actor, weapon)

    def test_coats_admit_equipped_and_unequipped_carried_catalog_weapons_after_json(self):
        catalog = CATALOG.OptionalPhysicalEquipmentTests(); catalog.r = self.all_rules
        for item in COATS:
            for weapon_id in ("crafted_item/스톰-글러브", "crafted_item/뇌수-창", "crafted_item/스프레드-니들"):
                for equipped in (False, True):
                    with self.subTest(item=item, weapon=weapon_id, equipped=equipped):
                        engine, actor, other, _ = catalog.fixture()
                        self.f.equip(engine, actor, item, "catalog-coat-" + item)
                        uid = "repair/catalog-weapon"
                        if equipped:
                            uid = catalog.equip(engine, actor, weapon_id, "catalog-weapon")
                        else:
                            WORLD.register_object(engine, uid, location={"kind": "unknown"}, reason="catalog weapon body",
                                kind="item_instance", item_rule_id=weapon_id, owner_id=actor.entity_id)
                            CAP.set_carried(engine, actor, [{"id": uid, "weight_kg": 1}], "actual catalog weapon carried")
                        self.assertNotIn(WEAPONS.PROFILE, engine._physical_objects[uid])
                        engine = self.restore(engine, fresh_rules=False)
                        actor, other = self.actual(engine, actor), self.actual(engine, other)
                        self.assert_concealment(engine, actor, uid)
                        if not equipped:
                            CAP.set_carried(engine, actor, [], "wearer releases catalog weapon")
                            CAP.set_carried(engine, other, [{"id": uid, "weight_kg": 1}], "other carrier takes catalog weapon")
                            assert_rejected_unchanged(engine, lambda: VARIANTS.conceal_weapon(engine, actor, uid, method="visual"),
                                                      reason_pattern="actual carried weapon")

    def test_new_battle_scope_same_battle_denies_and_same_scene_next_battle_allows_at_zero_time(self):
        for item in ARMORS:
            with self.subTest(item=item):
                engine, actor, target = self.f.fixture()
                uid = self.f.equip(engine, actor, item, "new-" + item)
                self.bound_turn(engine, actor, target)
                scene = actor.spec["frequency_state"]["scene"]
                self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])
                engine = self.restore(engine); actor, target = self.actual(engine, actor), self.actual(engine, target)
                self.assertNotIn("legacy_encounter_scope", self.state(engine, uid))
                engine.apply_status(actor, "구속", source="gm/repair", applied_by=target)
                before = engine.export_state()
                self.assertEqual(VARIANTS.activate_slipstream(engine, actor)["reason"], "encounter_frequency_spent")
                self.assertEqual(engine.export_state(), before)
                self.next_battle(engine, actor, target)
                self.assertEqual(actor.spec["frequency_state"]["scene"], scene)
                self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])
                self.assertEqual([r["encounter"][1] for r in self.state(engine, uid)["encounter_uses"]], [1, 2])
                engine.gm.snapshot("modern"); engine.gm.restore("modern", reason="modern quota survives GM restore")
                engine.apply_status(actor, "구속", source="gm/repair", applied_by=target)
                self.assertEqual(VARIANTS.activate_slipstream(engine, actor)["reason"], "encounter_frequency_spent")
                self.assertTrue(engine.validate_state()["valid"])

    def test_new_scope_does_not_reset_on_session_or_scene_counter_within_active_battle(self):
        for item in ARMORS:
            with self.subTest(item=item):
                engine, actor, target = self.session_fixture()
                self.f.equip(engine, actor, item, "counter-" + item)
                self.bound_turn(engine, actor, target)
                self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])
                # Native scene closing also ends the battle; these orthogonal
                # counter observations isolate the consumer's scope contract.
                self.assertEqual(engine.begin_session("session-two", [actor, target]), "refreshed")
                actor.spec["frequency_state"]["scene"] += 1
                engine.apply_status(actor, "구속", source="gm/repair", applied_by=target)
                self.assertEqual(VARIANTS.activate_slipstream(engine, actor)["reason"], "encounter_frequency_spent")

    def test_legacy_active_json_binds_once_preserves_receipts_and_later_battle_unlocks(self):
        for item in ARMORS:
            with self.subTest(item=item):
                engine, actor, target, uid = self.legacy_used(item, sessions=True)
                old = deepcopy(self.state(engine, uid)["encounter_uses"])
                engine = self.restore(engine); actor, target = self.actual(engine, actor), self.actual(engine, target)
                self.assertEqual(self.state(engine, uid)["encounter_uses"], old)
                self.assertEqual(self.state(engine, uid)["legacy_encounter_scope"]["encounter"][1], 1)
                engine.apply_status(actor, "구속", source="gm/repair", applied_by=target)
                self.assertEqual(VARIANTS.activate_slipstream(engine, actor)["reason"], "encounter_frequency_spent")
                self.assertEqual(engine.begin_session("session-two", [actor, target]), "refreshed")
                actor.spec["frequency_state"]["scene"] += 1
                self.assertEqual(VARIANTS.activate_slipstream(engine, actor)["reason"], "encounter_frequency_spent")
                self.next_battle(engine, actor, target)
                engine = self.restore(engine); actor, target = self.actual(engine, actor), self.actual(engine, target)
                self.assertEqual(self.state(engine, uid)["legacy_encounter_scope"]["encounter"][1], 1)
                self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])
                self.assertEqual(self.state(engine, uid)["encounter_uses"][:1], old)
                engine = self.restore(engine); actor, target = self.actual(engine, actor), self.actual(engine, target)
                engine.apply_status(actor, "구속", source="gm/repair", applied_by=target)
                self.assertEqual(VARIANTS.activate_slipstream(engine, actor)["reason"], "encounter_frequency_spent")

    def test_legacy_inactive_json_and_live_boundary_do_not_lock_the_next_battle(self):
        for item in ARMORS:
            for codec in ("live", "json", "gm"):
                with self.subTest(item=item, codec=codec):
                    engine, actor, target, uid = self.legacy_used(item, inactive=True)
                    if codec == "json":
                        engine = self.restore(engine); actor, target = self.actual(engine, actor), self.actual(engine, target)
                    elif codec == "gm":
                        engine.gm.snapshot("inactive"); engine.gm.restore("inactive", reason="old inactive scope")
                    else:
                        duplicate = copy(actor)
                        assert_rejected_unchanged(engine, lambda: engine.begin_encounter([duplicate]),
                                                  reason_pattern="distinct actors share identity")
                        before = engine.export_state()
                        receipt = self.state(engine, uid)["encounter_uses"][0]
                        original_at = receipt["at"]
                        receipt["at"] = -1
                        try:
                            with self.assertRaisesRegex(ValueError, "Slipstream encounter receipt is invalid"):
                                engine.begin_encounter([actor, target])
                        finally:
                            receipt["at"] = original_at
                        self.assertEqual(engine.export_state(), before)
                    self.bound_turn(engine, actor, target)
                    self.assertEqual(self.state(engine, uid)["legacy_encounter_scope"]["encounter"][1], 1)
                    self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])

    def test_ambiguous_old_receipt_in_active_second_battle_locks_only_that_battle(self):
        for item in ARMORS:
            with self.subTest(item=item):
                engine, actor, target, uid = self.legacy_used(item, inactive=True)
                # Reconstruct the actual old runtime's second active battle;
                # new begin_encounter would already perform the one-time upgrade.
                engine.begin_encounter([actor, target])
                state = self.state(engine, uid)
                state.pop("encounter_scope_version"); state.pop("legacy_encounter_scope")
                self.assertEqual(engine._party_encounter_epoch, 2)
                engine = self.restore(engine); actor, target = self.actual(engine, actor), self.actual(engine, target)
                self.bound_turn(engine, actor, target)
                self.assertEqual(self.state(engine, uid)["legacy_encounter_scope"]["encounter"][1], 2)
                self.assertEqual(VARIANTS.activate_slipstream(engine, actor)["reason"], "encounter_frequency_spent")
                self.next_battle(engine, actor, target)
                self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])

    def test_legacy_unequipped_json_and_gm_restore_bind_before_later_equipping(self):
        for item in ARMORS:
            for codec in ("json", "gm"):
                with self.subTest(item=item, codec=codec):
                    engine, actor, target, uid = self.legacy_used(item, unequipped=True)
                    if codec == "json":
                        engine = self.restore(engine); actor, target = self.actual(engine, actor), self.actual(engine, target)
                    else:
                        engine.gm.snapshot("old")
                        engine.gm.restore("old", reason="restore unequipped old item")
                    self.assertEqual(self.state(engine, uid)["legacy_encounter_scope"]["encounter"][1], 1)
                    ITEMS.register_item(engine, actor, item, source_instance_id=uid)
                    engine.apply_status(actor, "구속", source="gm/repair", applied_by=target)
                    self.assertEqual(VARIANTS.activate_slipstream(engine, actor)["reason"], "encounter_frequency_spent")
                    self.next_battle(engine, actor, target)
                    ITEMS.unregister_item(engine, actor, item)
                    engine.gm.snapshot("later-unequipped")
                    engine.gm.restore("later-unequipped", reason="do not rebind the original epoch")
                    ITEMS.register_item(engine, actor, item, source_instance_id=uid)
                    self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])

    def test_legacy_restore_then_no_attempt_until_next_battle_does_not_lazy_lock_next_use(self):
        for item in ARMORS:
            for codec in ("json", "gm"):
                with self.subTest(item=item, codec=codec):
                    engine, actor, target, uid = self.legacy_used(item, unequipped=True)
                    if codec == "json":
                        engine = self.restore(engine); actor, target = self.actual(engine, actor), self.actual(engine, target)
                    else:
                        engine.gm.snapshot("unused"); engine.gm.restore("unused", reason="eager scope binding")
                    self.next_battle(engine, actor, target)
                    ITEMS.register_item(engine, actor, item, source_instance_id=uid)
                    self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])

    def test_gm_upgrade_reaches_actual_graph_and_resnapshot_does_not_rebind_at_next_epoch(self):
        for item in ARMORS:
            with self.subTest(item=item):
                engine, actor, target, uid = self.legacy_used(item)
                old = deepcopy(self.state(engine, uid)["encounter_uses"])
                engine.gm.snapshot("legacy")
                engine.gm.restore("legacy", reason="bind legacy once")
                self.assertEqual(self.state(engine, uid)["encounter_uses"], old)
                self.assertEqual(self.state(engine, uid)["legacy_encounter_scope"]["encounter"][1], 1)
                self.next_battle(engine, actor, target)
                engine.gm.snapshot("upgraded")
                engine.gm.restore("upgraded", reason="same upgraded scope")
                self.assertEqual(self.state(engine, uid)["legacy_encounter_scope"]["encounter"][1], 1)
                self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])

    def test_corrupt_scope_and_receipt_shapes_are_rejected_by_json_and_gm_without_commit(self):
        mutations = (
            lambda s: s.update(encounter_scope_version=True),
            lambda s: s.update(legacy_encounter_scope=None),
            lambda s: s["legacy_encounter_scope"].update(receipt_count=0),
            lambda s: s["legacy_encounter_scope"].update(receipt_count=2),
            lambda s: s["legacy_encounter_scope"].update(encounter=[0, 999]),
            lambda s: s.pop("legacy_encounter_scope"),
            lambda s: s.pop("encounter_scope_version"),
            lambda s: s["encounter_uses"][0].update(encounter=[False, 0]),
            lambda s: s["encounter_uses"][0].update(at=-1),
            lambda s: s["encounter_uses"][0].update(actor_id=""),
            lambda s: s["encounter_uses"][1].pop("scope_version"),
            lambda s: s["encounter_uses"][1].update(scope_version=True),
            lambda s: s["encounter_uses"][1].update(encounter=[0, 999]),
            lambda s: s["encounter_uses"][2].update(encounter=[0, 2]),
        )
        for item in ARMORS:
            engine, actor, target, uid = self.legacy_used(item)
            engine = self.restore(engine); actor, target = self.actual(engine, actor), self.actual(engine, target)
            for _ in range(2):
                self.next_battle(engine, actor, target)
                self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])
            clean = deepcopy(self.state(engine, uid))
            for index, mutate in enumerate(mutations):
                with self.subTest(item=item, mutation=index):
                    engine.gm.snapshot("bad")
                    saved = engine.gm.snapshots["bad"]["engine"]["_physical_objects"][uid][VARIANTS.OBJECT_STATE]
                    mutate(saved)
                    before = engine.export_state()
                    with self.assertRaisesRegex(ValueError, "Slipstream"):
                        engine.gm.restore("bad", reason="must reject malformed saved scope")
                    self.assertEqual(engine.export_state(), before)
                    # Build a malformed import through the normal graph format;
                    # export is taken while valid so no guard is bypassed.
                    payload = deepcopy(before)
                    state_node = next(node for node in payload["nodes"].values()
                        if node.get("kind") == "dict" and ["kind", clean["kind"]] in node["items"]
                        and ["item_id", item] in node["items"] and any(pair[0] == "created_at" for pair in node["items"]))
                    bad = deepcopy(clean); mutate(bad)
                    # Existing nested references stay reachable; edit only
                    # scalars/keys within the already encoded state subtree.
                    def change(ref, original, altered):
                        node = payload["nodes"][ref["$ref"]]
                        pairs = node["items"]
                        for pair in list(pairs):
                            key, value = pair
                            if key not in altered:
                                pairs.remove(pair)
                            elif isinstance(original[key], dict) and isinstance(altered[key], dict):
                                change(value, original[key], altered[key])
                            elif isinstance(original[key], list) and isinstance(altered[key], list):
                                listnode = payload["nodes"][value["$ref"]]
                                for pos, (a, b) in enumerate(zip(original[key], altered[key])):
                                    if isinstance(a, dict):
                                        change(listnode["items"][pos], a, b)
                                    elif type(a) is not type(b) or a != b:
                                        listnode["items"][pos] = b
                            elif type(original[key]) is not type(altered[key]) or original[key] != altered[key]:
                                pair[1] = altered[key]
                    state_ref = {"$ref": next(key for key, value in payload["nodes"].items() if value is state_node)}
                    change(state_ref, clean, bad)
                    with self.assertRaises(ValueError):
                        Engine.import_state(self.r, payload)
                    self.assertEqual(engine.export_state(), before)


if __name__ == "__main__":
    unittest.main()
