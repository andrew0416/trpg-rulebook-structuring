"""Native trap provenance at the two combat-stage protection consumers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

from builder import build_pokemon, build_trainer
from engine import Combatant, Engine
from grid import Grid
import effects as FX
import effects_ext as EXT
import fashion_items as FASHION
import hazard_state as HAZARDS
import native_scenario_fixture as NATIVE
import test_category2_fashion_item_contracts as fashion_fixture
import test_category2_hazard_state as hazard_fixture
import test_category2_static_equipment_batch as gear_fixture
import world_entities as WORLD

WEB = "move/끈적끈적네트"
SPIKES = "move/압정뿌리기"
COURT = "move/코트체인지"
BEAUTY = "item/아름다운-패션-1"
CELLS = hazard_fixture.CELLS8


class HazardStageProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hazard_fixture.HazardStateTests.setUpClass()
        gear_fixture.StaticEquipmentBatchTests.setUpClass()
        fashion_fixture.FashionItemContractTests.setUpClass()

    def hazard_case(self):
        return hazard_fixture.HazardStateTests("test_sticky_web_spikes_immunity_boots_and_timed_slow")

    def trainer(self, e, *, side, name, protected=True, moves=()):
        actor = Combatant(e.r, build_trainer(e.r, name, 25,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 20),
            moves=list(moves), abilities=[]))
        e.gm.add_combatant(actor, pos=(9, 9), side=side, reason="actual trap protection target")
        if protected:
            gear_fixture.StaticEquipmentBatchTests().equip(e, actor, "item/클리어참", name)
        return actor

    def restore(self, e, *actors):
        loaded = Engine.import_state(e.r, json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
        index = WORLD.actor_index(loaded)
        return loaded, *(index[actor.entity_id] for actor in actors)

    def check_clear_web(self, *, restored):
        e, setter, _ = self.hazard_case().install(WEB)
        target = self.trainer(e, side="wild", name="clear-web")
        if restored:
            e, setter, target = self.restore(e, setter, target)
        instance = e.hazards[CELLS[0]]["instances"][0]
        expected = "hazard-instance/" + instance["id"] + "/" + WEB
        EXT.on_enter_cell(e, target, CELLS[0])
        self.assertEqual(target.stages["spe"], 0)
        self.assertIn("둔화", target.conditions)
        receipts = [row for row in e._effect_dispatch_receipts.values()
                    if row["source_id"] == expected]
        self.assertTrue(receipts)
        self.assertTrue(all(row["actor"] is setter and row["target"] is target for row in receipts))
        self.assertEqual(instance["source_id"], WEB)
        self.assertTrue(e.validate_state()["valid"])

    def test_clear_amulet_uses_native_move_origin_and_keeps_tracking_actor_and_slow(self):
        self.check_clear_web(restored=False)

    def test_clear_amulet_native_origin_survives_fresh_json_restore(self):
        self.check_clear_web(restored=True)

    def test_overlap_court_change_and_original_creator_entry_keep_only_stage_protection(self):
        e, setter, enemy = self.hazard_case().install(WEB)
        e.end_of_turn(setter)
        e.start_round(e.everyone)
        e.start_of_turn(setter, initiative_count=20)
        e.use_move_on(setter, setter, SPIKES, e.everyone, aim=CELLS)
        wild = self.trainer(e, side="wild", name="wild-clear")
        party = self.trainer(e, side="party", name="party-clear")
        immutable = {(row["id"], row["region_id"], row["source_id"], row["owner_actor_id"], row["cell"])
                     for env in e.hazards.values() for row in env["instances"]}
        hp = wild.hp
        EXT.on_enter_cell(e, wild, CELLS[0])
        self.assertEqual(wild.stages["spe"], 0)
        self.assertEqual(wild.hp, hp - wild.max_hp // 10)
        self.assertIn("둔화", wild.conditions)
        untouched = (party.hp, party.stages["spe"], deepcopy(party.conditions))
        EXT.on_enter_cell(e, party, CELLS[0])
        self.assertEqual((party.hp, party.stages["spe"], party.conditions), untouched)
        e.end_of_turn(setter)
        e.start_round(e.everyone)
        e.start_of_turn(setter, initiative_count=20)
        e.use_move_on(setter, setter, COURT, e.everyone)
        self.assertEqual({(row["id"], row["region_id"], row["source_id"], row["owner_actor_id"], row["cell"])
                          for env in e.hazards.values() for row in env["instances"]}, immutable)
        self.assertEqual({row["owner_side"] for env in e.hazards.values() for row in env["instances"]}, {"wild"})
        hp = party.hp
        EXT.on_enter_cell(e, party, CELLS[1])
        self.assertEqual(party.stages["spe"], 0)
        self.assertEqual(party.hp, hp - party.max_hp // 10)
        self.assertIn("둔화", party.conditions)
        hp = wild.hp
        EXT.on_enter_cell(e, wild, CELLS[1])
        self.assertEqual(wild.hp, hp)
        # The unprotected original installer is now an enemy of its own trap.
        EXT.on_enter_cell(e, setter, CELLS[2])
        self.assertEqual(setter.stages["spe"], -1)
        self.assertIn("둔화", setter.conditions)
        self.assertTrue(e.validate_state()["valid"])

    def test_clear_amulet_protects_original_trainer_creator_after_side_exchange(self):
        gear = gear_fixture.StaticEquipmentBatchTests()
        e, setter, enemy = gear.fixture(moves=[WEB, COURT])
        e.grid = Grid(16, 16)
        e.gm.set_position(setter, (2, 2), reason="actual trainer trap installation")
        e.gm.set_position(enemy, (12, 12), reason="actual opposite side")
        gear.equip(e, setter, "item/클리어참", "trainer-creator")
        e.start_round(e.everyone)
        e.start_of_turn(setter, initiative_count=20)
        e.use_move_on(setter, setter, WEB, e.everyone, aim=CELLS)
        e.end_of_turn(setter)
        e.start_round(e.everyone)
        e.start_of_turn(setter, initiative_count=20)
        e.use_move_on(setter, setter, COURT, e.everyone)
        EXT.on_enter_cell(e, setter, CELLS[0])
        self.assertEqual(setter.stages["spe"], 0)
        self.assertIn("둔화", setter.conditions)
        self.assertTrue(e.validate_state()["valid"])

    def beauty_world(self, *, original_creator=False):
        case = fashion_fixture.FashionItemContractTests()
        case.setUp()
        installer = Combatant(case.rules, build_pokemon(case.rules, "피카츄", 30,
            name="Fashion trap installer", moves=[WEB, COURT], abilities=["정전기"], side="party",
            extra={"trainer_id": case.a.entity_id}))
        case.e.gm.add_combatant(installer, pos=(2, 2), reason="actual allied trap installer")
        target = installer if original_creator else case.p
        identity = case.make(BEAUTY, wearer=target)
        e = case.e
        e.gm.observe_loyalty(installer, 3, reason="GM observed this actual maker-owned trap installer's loyalty")
        e.begin_encounter(e.everyone)
        e.start_round(e.everyone)
        e.start_of_turn(target, initiative_count=20)
        e.arm_fashion_reaction(target, BEAUTY, instance_id=identity)
        if target is not installer:
            e.end_of_turn(target)
            e.start_of_turn(installer, initiative_count=10)
        e.use_move_on(installer, installer, WEB, e.everyone, aim=CELLS)
        self.assertIn(CELLS[0], e.hazards)
        actions = list(target._action_history)
        EXT.on_enter_cell(e, target, CELLS[0])
        self.assertEqual(target.stages["spe"], 0)
        self.assertEqual(target._action_history, actions)
        self.assertEqual(FASHION._armed_instance(target, "beauty"), identity)
        e.end_of_turn(installer)
        e.start_round(e.everyone)
        e.start_of_turn(installer, initiative_count=20)
        e.use_move_on(installer, installer, COURT, e.everyone)
        return e, installer, target, identity

    def check_swapped_beauty(self, *, restored=False, original_creator=False):
        e, installer, target, identity = self.beauty_world(original_creator=original_creator)
        if restored:
            e, installer, target = self.restore(e, installer, target)
        instance = e.hazards[CELLS[0]]["instances"][0]
        self.assertEqual((instance["owner_side"], installer.side, target.side), ("wild", "party", "party"))
        actions = list(target._action_history)
        EXT.on_enter_cell(e, target, CELLS[0])
        self.assertEqual(target.stages["spe"], 0)
        self.assertIn("둔화", target.conditions)
        self.assertEqual(target._action_history, actions + ["free"])
        self.assertIsNone(FASHION._armed_instance(target, "beauty"))
        receipt = e._physical_objects[identity][FASHION.STATE]["scene_activation"]
        self.assertEqual(receipt["target_id"], installer.entity_id)
        history = deepcopy(e._physical_objects[identity][FASHION.STATE])
        EXT.on_enter_cell(e, target, CELLS[1])
        self.assertEqual(target.stages["spe"], -1)
        self.assertEqual(e._physical_objects[identity][FASHION.STATE], history)
        self.assertEqual(target._action_history, actions + ["free"])
        NATIVE.assert_rejected_unchanged(e,
            lambda: e.arm_fashion_reaction(target, BEAUTY, instance_id=identity),
            reason_pattern="already activated")
        self.assertTrue(e.validate_state()["valid"])

    def test_beauty_uses_current_trap_side_and_consumes_one_free_action_and_scene(self):
        self.check_swapped_beauty()

    def test_beauty_current_side_and_armed_reaction_survive_fresh_json_restore(self):
        self.check_swapped_beauty(restored=True)

    def test_swapped_original_creator_can_react_to_its_now_hostile_trap(self):
        self.check_swapped_beauty(original_creator=True)

    def test_forged_context_source_instance_and_creator_reject_before_stage_or_reaction(self):
        e, setter, target, identity = self.beauty_world()
        row = e.hazards[CELLS[0]]["instances"][0]
        source = "hazard-instance/" + row["id"] + "/" + row["source_id"]
        actual = {"source_id": source, "hazard_instance_id": row["id"],
                  "_hazard_instance": row, "_hazard_activation": HAZARDS._AUTHORITY}
        forged = [
            ({"source_id": source, "hazard_instance_id": row["id"], "owner_side": "wild"}, setter,
             "actual Hazard trigger context"),
            ({**actual, "_hazard_instance": deepcopy(row)}, setter, "actual live Hazard instance"),
            ({**actual, "hazard_instance_id": "hazard:forged"}, setter, "source or participant identity"),
            ({**actual, "source_id": "hazard-instance/" + row["id"] + "/ability/test"}, setter,
             "source or participant identity"),
            (actual, target, "source or participant identity"),
        ]
        for context, actor, reason in forged:
            with self.subTest(reason=reason, actor=actor.entity_id):
                NATIVE.assert_rejected_unchanged(e,
                    lambda: FX.apply_stage_changes(e, actor, target, {"spe": -1},
                        source_id=context["source_id"], context=context), reason_pattern=reason)
        def tampered_source():
            digest = row["source_row_sha256"]
            row["source_row_sha256"] = "forged"
            try:
                FX.apply_stage_changes(e, setter, target, {"spe": -1}, source_id=source, context=actual)
            finally:
                row["source_row_sha256"] = digest
        NATIVE.assert_rejected_unchanged(e, tampered_source, reason_pattern="source provenance")
        self.assertEqual(FASHION._armed_instance(target, "beauty"), identity)
        # Invalid trap hints cannot consume the arm; an ordinary enemy still can.
        enemy = next(actor for actor in WORLD.actor_index(e).values() if actor.side == "wild")
        e.apply_effect(enemy, target, {"type": "stage_change", "stat": "spe", "delta": -1,
            "on": "target"}, 2, True, 0, "move/울음소리")
        self.assertEqual(target.stages["spe"], 0)
        self.assertIsNone(FASHION._armed_instance(target, "beauty"))
        self.assertTrue(e.validate_state()["valid"])


if __name__ == "__main__":
    unittest.main()
