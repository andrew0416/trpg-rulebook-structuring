"""Direct native-path checks for ten optional weapon/equipment clauses."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest


STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

from builder import build_trainer
from engine import Combatant, Engine, Rules
from grid import Grid
import condition_recovery as RECOVERY
import items as ITEMS
import movement_actions as MOVEMENT
import optional_physical_equipment as OPTIONAL
import perception_communicate as COMMUNICATION
import roll_context as ROLLS
import state_grants as GRANTS
import weapon_actions as WEAPONS
import world_entities as WORLD


CLAUSES = {
    "FAN-020", "FAN-034", "FAN-037", "FAN-038", "FAN-040",
    "FAN-041", "FAN-048", "FAN-062", "SPOL-004", "SPOL-106",
}


class OptionalPhysicalEquipmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")

    def actor(self, name, *, edges=()):
        stats = dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 25)
        spec = build_trainer(
            self.r, name, 30, stats,
            extra={
                "moves": ["move/몸통박치기"], "abilities": [], "edges": list(edges),
                "skills": {"전투": 4, "오컬트학": 3, "집중": 3, "명령": 3},
                "movement": {"land": 6}, "movement_basis": "current",
            },
        )
        return Combatant(self.r, spec)

    def fixture(self, *, edges=()):
        engine = Engine(self.r, seed=112210)
        engine.grid = Grid(30, 12)
        actor = self.actor("optional-owner-" + str(id(engine)), edges=edges)
        ally = self.actor("optional-ally-" + str(id(engine)))
        enemy = self.actor("optional-enemy-" + str(id(engine)))
        actor.side = ally.side = "player"; enemy.side = "wild"
        actor.pos = (2, 2); ally.pos = (4, 2); enemy.pos = (6, 2)
        for value in (actor, ally, enemy):
            engine.gm.add_combatant(value)
        return engine, actor, ally, enemy

    def equip(self, engine, actor, item_id, suffix):
        uid = "optional-equipment/" + suffix
        WORLD.register_object(
            engine, uid, kind="item_instance", item_rule_id=item_id,
            owner_id=actor.entity_id, location={"kind": "unknown"},
            reason="actual optional equipment fixture",
        )
        ITEMS.register_item(engine, actor, item_id, source_instance_id=uid)
        self.assertEqual(engine._physical_objects[uid]["equipped_by"], actor.entity_id)
        return uid

    def restored(self, engine):
        payload = json.loads(json.dumps(engine.export_state(), ensure_ascii=False))
        return Engine.import_state(self.r, payload)

    def test_policy_and_existing_weapon_choice_cover_exact_ten_clause_batch(self):
        policy = OPTIONAL.policy(self.r)
        rows = [row for row in policy["rows"].values() if row["clause_id"] in CLAUSES]
        clauses = {row["clause_id"] for row in rows}
        self.assertEqual(clauses, CLAUSES - {"FAN-020", "FAN-062"})
        status = json.loads((ROOT / "data/verification/category2-optional-clause-status.json").read_text(encoding="utf-8"))
        indexed = {row["clause_id"]: row for row in status["rows"]}
        for row in rows:
            expected = [(x["file"], x["start"], x["end"], x["excerpt_sha256"]) for x in row["source"]]
            observed = [(x["file"], x["start"], x["end"], x["excerpt_sha256"]) for x in indexed[row["clause_id"]]["source"]]
            self.assertEqual(observed, expected)
        self.assertEqual(WEAPONS.CHOICE_EDGE, "edge/선택한-무기")
        self.assertEqual(self.r._selected_rule(WEAPONS.CHOICE_EDGE), WEAPONS.CHOICE_EDGE)

    def test_crafted_weapons_add_recipe_moves_to_native_weapon_moves_and_revoke(self):
        cases = (
            ("crafted_item/스톰-글러브", "move/아쿠아제트", None, "storm"),
            ("crafted_item/뇌수-창", "move/번개엄니", "투쟁심", "skewer"),
            ("crafted_item/엑스칼리버", "move/성스러운칼", "제왕의 요구", "excalibur"),
        )
        for item_id, move_id, ability, suffix in cases:
            with self.subTest(item=item_id):
                engine, actor, _, _ = self.fixture()
                uid = self.equip(engine, actor, item_id, suffix)
                entry = next(row for row in actor.custom_conditions["equipped_weapons"].values()
                             if row.get("instance_id") == uid)
                self.assertIn(move_id, entry["crafted_grants"])
                self.assertIn(move_id, actor.moves)
                if ability is not None:
                    self.assertIn(ability, actor.abilities)
                prepared = WEAPONS.prepare(engine, actor, self.r.move(move_id), weapon_id=item_id)
                self.assertEqual(prepared["_weapon_attack"]["source"], item_id)
                self.assertGreaterEqual(prepared["_weapon_attack"]["db_bonus"], 1)
                ITEMS.unregister_item(engine, actor, item_id)
                self.assertNotIn(move_id, actor.moves)
                self.assertFalse(actor.custom_conditions.get("equipped_weapons"))
                self.assertNotIn("equipped_by", engine._physical_objects[uid])

    def test_weapon_slot_failure_is_atomic_before_physical_registration(self):
        engine, actor, _, _ = self.fixture()
        first = self.equip(engine, actor, "crafted_item/스톰-글러브", "occupied")
        uid = "optional-equipment/refused"
        WORLD.register_object(engine, uid, kind="item_instance", item_rule_id="crafted_item/뇌수-창",
            owner_id=actor.entity_id, location={"kind": "unknown"}, reason="atomic refusal fixture")
        before = json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True)
        with self.assertRaisesRegex(ValueError, "physical weapon slots"):
            ITEMS.register_item(engine, actor, "crafted_item/뇌수-창", source_instance_id=uid)
        self.assertEqual(json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True), before)
        self.assertEqual(engine._physical_objects[first]["equipped_by"], actor.entity_id)
        self.assertNotIn("equipped_by", engine._physical_objects[uid])

    def test_conditional_save_consumers_and_space_suit_movement_revoke_cleanly(self):
        engine, actor, _, _ = self.fixture()
        robes = self.equip(engine, actor, "crafted_item/명금의-로브", "robes")
        sleep = RECOVERY.saving_check(engine, actor, "잠듦", 10, fixed=8)
        paralysis = RECOVERY.saving_check(engine, actor, "마비", 10, fixed=8)
        self.assertEqual((sleep["optional_equipment_bonus"], sleep["dc"], sleep["passed"]), (2, 8, True))
        self.assertEqual(paralysis["optional_equipment_bonus"], 0)
        self.assertIn("날씨부정", actor.abilities)
        ITEMS.unregister_item(engine, actor, registration_key=next(k for k,v in actor._item_reg.items() if v.get("instance_id")==robes))
        boots = self.equip(engine, actor, "crafted_item/경쟁-부츠", "boots")
        check = RECOVERY.saving_check(engine, actor, "마비", 10, fixed=8)
        self.assertEqual(check["optional_equipment_bonus"], 2)
        self.assertIn("도움닫기", actor.abilities)
        self.assertIn("자연걸음(산)", GRANTS.effective(actor, "capabilities"))
        ITEMS.unregister_item(engine, actor, registration_key=next(k for k,v in actor._item_reg.items() if v.get("instance_id")==boots))
        suit = self.equip(engine, actor, "item/우주복", "space-suit")
        self.assertEqual(MOVEMENT.capabilities(engine, actor, environment=False)["levitate"], 4)
        self.assertIn("진공면역", GRANTS.effective(actor, "capabilities"))
        ITEMS.unregister_item(engine, actor, registration_key=next(k for k,v in actor._item_reg.items() if v.get("instance_id")==suit))
        self.assertEqual(MOVEMENT.capabilities(engine, actor, environment=False).get("levitate", 0), 0)

    def test_mental_shield_is_either_focus_bonus_or_mindlock_and_opposed_consumer_reads_it(self):
        engine, sender, recipient, _ = self.fixture()
        self.equip(engine, recipient, "item/정신방패", "mental")
        consent = {"sender_skill": "명령", "recipient_skill": "집중", "purpose": "telepathy resistance"}
        value = {"consent": consent}
        with patch.object(ROLLS, "resolve", return_value={"winner_id": recipient.entity_id}) as resolve:
            COMMUNICATION._opposed(engine, sender, recipient, value, {}, 0)
        requests = resolve.call_args.args[1]
        self.assertEqual(requests[1]["options"]["mods"], 6)
        self.assertNotIn("정신봉인", GRANTS.effective(recipient, "capabilities"))

        other_engine, iron, _, _ = self.fixture(edges=("edge/강철의-정신",))
        self.equip(other_engine, iron, "item/정신방패", "mental-iron")
        self.assertEqual(OPTIONAL.mental_resistance_bonus(iron), 0)
        self.assertIn("정신봉인", GRANTS.effective(iron, "capabilities"))

    def test_excalibur_swift_type_choice_is_physical_persistent_and_failure_atomic(self):
        engine, actor, _, _ = self.fixture()
        uid = self.equip(engine, actor, "crafted_item/엑스칼리버", "type-state")
        engine.start_round(engine.everyone); engine.start_of_turn(actor, initiative_count=20)
        out = OPTIONAL.change_excalibur_type(engine, actor, uid, "불꽃")
        self.assertTrue(out["changed"])
        move = WEAPONS.prepare(engine, actor, self.r.move("move/성스러운칼"), weapon_id=uid)
        self.assertEqual(move["type"], "불꽃")
        before = json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True)
        with self.assertRaises(ValueError):
            OPTIONAL.change_excalibur_type(engine, actor, uid, "사탕")
        self.assertEqual(json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True), before)
        loaded = self.restored(engine)
        loaded_actor = next(value for value in loaded.everyone if value.entity_id == actor.entity_id)
        loaded_move = WEAPONS.prepare(loaded, loaded_actor, loaded.r.move("move/성스러운칼"), weapon_id=uid)
        self.assertEqual(loaded_move["type"], "불꽃")

    def test_virtuoso_flute_accepts_eight_allies_and_rejects_nine_before_payment(self):
        import skill_modifiers as SKILLS
        engine, actor, ally, _ = self.fixture()
        self.equip(engine, actor, "crafted_item/따스한-플루트", "virtuoso-flute")
        engine.gm.set_skill(actor, "오컬트학", 6, reason="actual Master Occult before Virtuoso acquisition")
        GRANTS.transition(engine, actor, lambda e, owner: owner.spec.update(
            edges=[*owner.spec.get("edges", []), "edge/거장"], edge_choices={"edge/거장": ["오컬트학"]}))
        self.assertEqual((SKILLS.rank(engine.r, actor, "오컬트학")[2],
                          SKILLS.effective_rank(engine.r, actor, "오컬트학")), (6, 8))
        protected = [ally]
        for number in range(8):
            extra = self.actor("virtuoso-flute-ally-" + str(number))
            extra.side = actor.side
            extra.pos = (7 + number, 2)
            engine.gm.add_combatant(extra)
            protected.append(extra)
        engine.start_round(engine.everyone)
        engine.start_of_turn(actor, initiative_count=20)
        before = json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True)
        with self.assertRaisesRegex(ValueError, "exceeds the wielder's Occult rank"):
            OPTIONAL.activate_heartwarming_flute(engine, actor, protected_allies=protected)
        self.assertEqual(json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True), before)
        result = OPTIONAL.activate_heartwarming_flute(engine, actor, protected_allies=protected[:8])
        self.assertTrue(result["activated"])
        self.assertEqual(set(result["protected"]), {value.entity_id for value in protected[:8]})
        ghost = {"type": "고스트", "class": "특수"}
        self.assertEqual([ITEMS.item_damage_reduction(value, ghost, engine=engine)
                          for value in protected], [5] * 8 + [0])

    def test_heartwarming_flute_scene_action_cures_radius_and_scoped_dr_expires(self):
        engine, actor, ally, enemy = self.fixture()
        self.equip(engine, actor, "crafted_item/따스한-플루트", "flute")
        actor.conditions.add("마비"); ally.conditions.add("마비"); enemy.conditions.add("마비")
        engine.start_round(engine.everyone); engine.start_of_turn(actor, initiative_count=20)
        result = OPTIONAL.activate_heartwarming_flute(engine, actor, protected_allies=(actor, ally))
        self.assertTrue(result["activated"])
        self.assertFalse(any("마비" in value.conditions for value in (actor, ally, enemy)))
        ghost = {"type": "고스트", "class": "특수"}; fire = {"type": "불꽃", "class": "특수"}
        self.assertEqual(ITEMS.item_damage_reduction(ally, ghost, engine=engine), 5)
        self.assertEqual(ITEMS.item_damage_reduction(ally, fire, engine=engine), 0)
        with self.assertRaisesRegex(ValueError, "frequency spent"):
            OPTIONAL.activate_heartwarming_flute(engine, actor, protected_allies=(ally,))
        engine.end_scene(engine.everyone, round_elapsed_seconds=10)
        self.assertEqual(ITEMS.item_damage_reduction(ally, ghost, engine=engine), 0)

    def test_restore_and_world_validation_keep_physical_owner_and_projection_linked(self):
        engine, actor, _, _ = self.fixture()
        uid = self.equip(engine, actor, "crafted_item/경쟁-부츠", "restore")
        loaded = self.restored(engine)
        self.assertTrue(loaded.validate_state()["valid"])
        loaded_actor = next(value for value in loaded.everyone if value.entity_id == actor.entity_id)
        self.assertIn("도움닫기", loaded_actor.abilities)
        self.assertEqual(loaded._physical_objects[uid]["equipped_by"], loaded_actor.entity_id)
        loaded._physical_objects[uid]["equipped_by"] = "missing-owner"
        result = loaded.validate_state()
        self.assertFalse(result["valid"])
        self.assertTrue(any(row["code"] == "optional_physical_equipment" for row in result["issues"]))


if __name__ == "__main__":
    unittest.main()
