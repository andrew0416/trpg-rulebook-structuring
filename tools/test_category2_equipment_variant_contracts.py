"""Direct native-path checks for ten source-pinned trainer equipment rows."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest


STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

import equipment_variant_contracts as VARIANTS
import damage_coats as DAMAGE_COATS
import items as ITEMS
import move_completion as COMPLETE
import roll_effects as ROLLS
import skill_modifiers as SKILLS
import world_entities as WORLD
from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules


CLAUSES = {
    "C2CSV/inventory:65:17", "C2CSV/inventory:66:17",
    "C2CSV/inventory:67:17", "C2CSV/inventory:69:17",
    "C2CSV/inventory:71:17", "C2CSV/inventory:72:17",
    "C2CSV/inventory:74:17", "C2CSV/inventory:75:17",
    "C2CSV/inventory:107:17", "C2CSV/inventory:108:17",
}


class EquipmentVariantContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def trainer(self, name, *, moves=(), power=7, skills=None):
        spec = build_trainer(
            self.r, name, 30,
            {"hp": 80, "atk": 20, "def": 20, "spa": 20, "spd": 20, "spe": 20},
            extra={"moves": list(moves), "movement": {"land": 6, "power": power},
                   "power_basis": "current", "skills": skills or {"은신": 3}},
        )
        return Combatant(self.r, spec)

    def fixture(self, *, moves=("move/몸통박치기",), target_moves=()):
        engine = Engine(self.r, seed=65108)
        actor = self.trainer("equipment-owner-" + str(id(engine)), moves=moves)
        target = self.trainer("equipment-target-" + str(id(engine)), moves=target_moves)
        engine.gm.add_combatant(actor)
        engine.gm.add_combatant(target)
        return engine, actor, target

    def equip(self, engine, actor, item_id, suffix, *, chosen_type=None, as_held=False):
        uid = "equipment-variant/" + suffix
        WORLD.register_object(engine, uid, location={"kind": "unknown"},
            reason="actual reviewed equipment fixture", kind="item_instance",
            item_rule_id=item_id, owner_id=actor.entity_id)
        if chosen_type is not None:
            VARIANTS.configure_type_armor(engine, actor, uid, chosen_type)
        ITEMS.register_item(engine, actor, item_id, source_instance_id=uid, as_held=as_held)
        self.assertEqual(engine._physical_objects[uid]["equipped_by"], actor.entity_id)
        return uid

    def restored(self, engine):
        payload = json.loads(json.dumps(engine.export_state(), ensure_ascii=False))
        return Engine.import_state(self.r, payload)

    def test_policy_anchors_exact_ten_rows_and_source_column_classifier(self):
        policy = VARIANTS.policy(self.r)
        self.assertEqual({row["clause_id"] for row in policy["rows"].values()}, CLAUSES)
        status = json.loads((ROOT / "data/verification/category2-item-table-status.json").read_text(encoding="utf-8"))
        indexed = {row["clause_id"]: row for row in status["new_clauses"]}
        for row in policy["rows"].values():
            self.assertEqual(indexed[row["clause_id"]]["source"][0]["raw_cells_sha256"], row["source_row_sha256"])
        punch = VARIANTS._punch_moves(self.r)
        self.assertIn("move/암해머", punch)
        self.assertIn("move/스카이어퍼", punch)
        self.assertNotIn("move/몸통박치기", punch)

    def test_both_cannons_require_power_and_spend_physical_one_shot_permission(self):
        for item_id, move_id, suffix in (
            ("item/잽-블래스터", "move/전자포", "zap"),
            ("item/인페르노-캐논", "move/연옥", "inferno"),
        ):
            with self.subTest(item=item_id):
                engine, actor, target = self.fixture()
                actor.spec["movement"]["power"] = 6
                uid = "equipment-variant/low-" + suffix
                WORLD.register_object(engine, uid, location={"kind": "unknown"}, reason="low Power fixture",
                    kind="item_instance", item_rule_id=item_id, owner_id=actor.entity_id)
                with self.assertRaisesRegex(ValueError, "Power greater than 6"):
                    ITEMS.register_item(engine, actor, item_id, source_instance_id=uid)
                self.assertNotIn("equipped_by", engine._physical_objects[uid])
                actor.spec["movement"]["power"] = 7
                ITEMS.register_item(engine, actor, item_id, source_instance_id=uid)
                self.assertIn(move_id, actor.moves)
                engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
                engine.d20 = lambda: 1
                engine.use_move(actor, target, move_id)
                del engine.d20
                state = engine._physical_objects[uid][VARIANTS.OBJECT_STATE]
                self.assertEqual((state["remaining_uses"], len(state["use_history"])), (0, 1))
                budget = dict(actor.budget)
                with self.assertRaisesRegex(ValueError, "one-shot Move permission is spent"):
                    engine.use_move(actor, target, move_id)
                self.assertEqual(actor.budget, budget)
                loaded = self.restored(engine)
                loaded_actor = next(row for row in loaded.everyone if row.entity_id == actor.entity_id)
                with self.assertRaisesRegex(ValueError, "one-shot Move permission is spent"):
                    loaded.use_move(loaded_actor, next(row for row in loaded.everyone if row.entity_id == target.entity_id), move_id)

    def test_ablative_armor_native_hit_depletes_clock_repairs_and_unequip_revokes_base_stage(self):
        engine, attacker, target = self.fixture()
        uid = self.equip(engine, target, "item/분리중갑", "ablative")
        self.assertEqual(target.stages["spe"], -1)
        self.assertEqual(ITEMS.item_damage_reduction(target, {"type": "노말", "class": "물리"}), 15)
        engine.start_round([attacker, target]); engine.start_of_turn(attacker, initiative_count=20)
        engine.d20 = lambda: 20
        engine.use_move(attacker, target, "move/몸통박치기", set_damage=True)
        del engine.d20
        self.assertEqual(ITEMS.item_damage_reduction(target, {"type": "노말", "class": "물리"}), 10)
        # The five-minute repair clock belongs to world time, after the open
        # combat round has been closed with an explicit final-round duration.
        engine._end_encounter([attacker, target], round_elapsed_seconds=10)
        engine.advance_time(300, [target])
        self.assertEqual(ITEMS.item_damage_reduction(target, {"type": "노말", "class": "물리"}), 15)
        self.assertTrue(engine._physical_objects[uid][VARIANTS.OBJECT_STATE]["repair_history"])
        ITEMS.unregister_item(engine, target, "item/분리중갑")
        self.assertEqual(target.stages["spe"], 0)
        self.assertEqual(ITEMS.item_damage_reduction(target, {"type": "노말", "class": "물리"}), 0)

    def test_type_armor_purchase_choice_is_immutable_persistent_and_typed(self):
        engine, actor, _ = self.fixture()
        uid = self.equip(engine, actor, "item/타입-방어복", "type-armor", chosen_type="불꽃")
        self.assertEqual(ITEMS.item_damage_reduction(actor, {"type": "불꽃", "class": "특수"}), 10)
        self.assertEqual(ITEMS.item_damage_reduction(actor, {"type": "물", "class": "특수"}), 0)
        with self.assertRaisesRegex(ValueError, "immutable"):
            VARIANTS.configure_type_armor(engine, actor, uid, "물")
        loaded = self.restored(engine)
        loaded_actor = next(row for row in loaded.everyone if row.entity_id == actor.entity_id)
        self.assertEqual(ITEMS.item_damage_reduction(loaded_actor, {"type": "불꽃", "class": "물리"}), 10)

    def test_trenchcoat_variants_supply_scoped_dr_skill_and_actual_weapon_concealment(self):
        for item_id, accepted, rejected in (
            ("item/보강된-트렌치코트", "물리", "특수"),
            ("item/보강된-특수-트렌치코트", "특수", "물리"),
        ):
            with self.subTest(item=item_id):
                engine, actor, _ = self.fixture()
                self.equip(engine, actor, item_id, accepted + "-trench")
                self.assertEqual(ITEMS.item_damage_reduction(actor, {"type": "노말", "class": accepted}), 5)
                self.assertEqual(ITEMS.item_damage_reduction(actor, {"type": "노말", "class": rejected}), 0)
                resolved = SKILLS.modifiers(self.r, actor, "은신", 0)
                self.assertEqual(resolved["modifier"], 4)
                weapon = "equipment-variant/weapon-" + accepted
                WORLD.register_object(engine, weapon, location={"kind": "unknown"}, reason="actual concealed weapon",
                    kind="physical_object", owner_id=actor.entity_id)
                import optional_weapon_framework as WEAPONS
                import capability_actions as CAP
                WEAPONS.observe_weapon(engine, actor, weapon, name="actual concealed sword",
                    kind="소형 근접무기", grade="간단", arcane=False, metal=True,
                    reason="observed actual weapon identity")
                CAP.set_carried(engine, actor, [{"id": weapon, "weight_kg": 1}], "wearer actually carries the weapon")
                self.assertEqual(VARIANTS.conceal_weapon(engine, actor, weapon, method="visual")["status"], "concealed")
                self.assertEqual(VARIANTS.conceal_weapon(engine, actor, weapon, method="metal_detector")["status"], "concealed")
                self.assertEqual(VARIANTS.conceal_weapon(engine, actor, weapon, method="manual_search")["status"], "detectable")

    def test_both_slipstream_variants_use_one_atomic_swift_escape_per_encounter(self):
        for item_id, accepted, rejected in (
            ("item/마찰저하복", "물리", "특수"),
            ("item/특수마찰저하복", "특수", "물리"),
        ):
            with self.subTest(item=item_id):
                engine, actor, target = self.fixture()
                self.equip(engine, actor, item_id, accepted + "-slipstream")
                self.assertEqual(ITEMS.item_damage_reduction(actor, {"type": "노말", "class": accepted}), 5)
                self.assertEqual(ITEMS.item_damage_reduction(actor, {"type": "노말", "class": rejected}), 0)
                engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
                engine.apply_status(actor, "구속", source="gm/test", applied_by=target)
                actor.budget.update(standard=0, shift=1, swift=0)
                before = (set(actor.conditions), dict(actor.budget))
                self.assertEqual(VARIANTS.activate_slipstream(engine, actor)["reason"], "no_swift_action")
                self.assertEqual((actor.conditions, actor.budget), before)
                actor.budget["swift"] = 1
                self.assertTrue(VARIANTS.activate_slipstream(engine, actor)["activated"])
                self.assertNotIn("구속", actor.conditions)
                engine.apply_status(actor, "구속", source="gm/test", applied_by=target); actor.budget["swift"] = 1
                self.assertEqual(VARIANTS.activate_slipstream(engine, actor)["reason"], "encounter_frequency_spent")
                self.assertIn("구속", actor.conditions)

    def test_punching_glove_uses_source_classifier_and_suppresses_melee_hit_reaction(self):
        engine, actor, _ = self.fixture(moves=("move/암해머", "move/몸통박치기"))
        self.equip(engine, actor, "item/펀치글러브", "punching-glove")
        punch = self.r.move("move/암해머")
        ordinary = self.r.move("move/몸통박치기")
        facts = {"damage_base": 10, "roll_value": 20, "mode": "set"}
        target = self.trainer("roll-target-" + str(id(engine)))
        engine.gm.add_combatant(target)
        self.assertEqual(ROLLS.use(engine, actor, target, punch, "damage", facts), 5)
        self.assertEqual(ROLLS.use(engine, actor, target, ordinary, "damage", facts), 0)

        helmet = Combatant(self.r, build_pokemon(self.r, "피카츄", 30, name="helmet-holder",
            moves=["move/몸통박치기"], abilities=["정전기"], extra={"side": "wild"}))
        engine.gm.add_combatant(helmet)
        helmet_uid = "equipment-variant/rocky-helmet"
        WORLD.register_object(engine, helmet_uid, location={"kind": "unknown"}, reason="actual helmet fixture",
            kind="item_instance", item_rule_id="item/울퉁불퉁멧", owner_id=helmet.entity_id)
        ITEMS.register_item(engine, helmet, "item/울퉁불퉁멧", source_instance_id=helmet_uid, as_held=True)
        before = actor.hp
        move = deepcopy(punch)
        DAMAGE_COATS.after_damage(engine, actor, helmet, move, {
            "observation_boundary": "native_attack_application_including_its_hooks",
            "source": move["id"], "damage_class": move["class"], "requested": 10,
            "net_hp_loss": 10, "net_temporary_hp_loss": 0,
        })
        self.assertTrue(move["_melee_hit_effects_suppressed"])
        self.assertEqual(actor.hp, before)

    def test_covert_cloak_optional_scene_immunity_blocks_direct_secondary_and_caps_stealth(self):
        engine, attacker, target = self.fixture(moves=("move/불꽃펀치",))
        self.equip(engine, target, "item/은밀망토", "covert-cloak")
        self.assertEqual(SKILLS.modifiers(self.r, target, "은신", 0)["modifier"], 0)
        self.assertEqual(SKILLS.modifiers(self.r, target, "은신", 0,
            skill_context={"purpose": "avoid_notice"})["modifier"], 2)
        engine.start_round([attacker, target]); engine.start_of_turn(attacker, initiative_count=20)
        VARIANTS.authorize_covert_cloak(engine, target, expected_move_id="move/불꽃펀치")
        hp = target.hp
        engine.d20 = lambda: 20
        engine.use_move(attacker, target, "move/불꽃펀치", set_damage=True)
        del engine.d20
        self.assertLess(target.hp, hp)
        self.assertNotIn("화상", target.conditions)
        self.assertNotIn("equipment_variant_choices", target.spec)
        self.assertEqual(VARIANTS.authorize_covert_cloak(engine, target)["reason"], "scene_frequency_spent")

        other, wearer, _ = self.fixture()
        self.equip(other, wearer, "item/보강된-트렌치코트", "cap-trench")
        self.equip(other, wearer, "item/은밀망토", "cap-cloak")
        self.assertEqual(SKILLS.modifiers(self.r, wearer, "은신", 0,
            skill_context={"purpose": "avoid_notice"})["modifier"], 4)

    def test_restore_rejects_tampered_physical_state_projection(self):
        engine, actor, _ = self.fixture()
        uid = self.equip(engine, actor, "item/타입-방어복", "tamper", chosen_type="물")
        payload = json.loads(json.dumps(engine.export_state(), ensure_ascii=False))
        # Save graphs encode dictionaries as key/value node pairs.  Change the
        # exact physical object's nested state through that public graph form.
        text = json.dumps(payload, ensure_ascii=False)
        self.assertIn(uid, text)
        self.assertIn(VARIANTS.OBJECT_STATE, text)
        def tamper(value, inside_object=False):
            if isinstance(value, dict):
                pairs = value.get("items")
                if value.get("kind") == "dict" and isinstance(pairs, list):
                    item_pair = next((pair for pair in pairs if pair == ["item_id", "item/타입-방어복"]), None)
                    kind_pair = next((pair for pair in pairs if pair == ["kind", "type_armor"]), None)
                    if item_pair is not None and kind_pair is not None:
                        item_pair[1] = "item/분리중갑"
                        return True
                here = inside_object or uid in value.values()
                if here and value.get("item_id") == "item/타입-방어복" and value.get("kind") == "type_armor":
                    value["item_id"] = "item/분리중갑"
                    return True
                return any(tamper(child, here) for child in value.values())
            if isinstance(value, list):
                here = inside_object or uid in value
                return any(tamper(child, here) for child in value)
            return False
        self.assertTrue(tamper(payload), text[text.index(uid) - 300:text.index(uid) + 1000])
        with self.assertRaises(ValueError):
            Engine.import_state(self.r, payload)


if __name__ == "__main__":
    unittest.main()
