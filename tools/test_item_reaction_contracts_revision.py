"""Native regressions for inventory 108, 129, 130, 131; no game execution at authoring time."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import csv_item_physical_contracts as PHYSICAL
import equipment_variant_contracts as VARIANTS
import forced_move_lock as FORCED_MOVE
import items as ITEMS
import state_grants as GRANTS
import test_category2_csv_remaining_item_contracts as CSV_FIX
import test_category2_equipment_variant_contracts as EQUIPMENT_FIX
import test_switch_replacement_f19 as SWITCH_FIX
import turn as TURN
import world_entities as WORLD
from engine import Engine
from grid import Grid
from native_scenario_fixture import assert_rejected_unchanged


class ItemReactionContractsRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CSV_FIX.RemainingCsvItemContractTests.setUpClass()
        cls.r = CSV_FIX.RemainingCsvItemContractTests.r

    def setUp(self):
        self.f = CSV_FIX.RemainingCsvItemContractTests()
        self.equipment = EQUIPMENT_FIX.EquipmentVariantContractTests()
        self.equipment.r = self.r
        self.switch = SWITCH_FIX.SwitchReplacementTests()
        self.switch.f = self.f

    def restore(self, engine, *actors, mode):
        if mode == "json":
            engine = Engine.import_state(self.r, json.loads(json.dumps(engine.export_state(), ensure_ascii=False)))
        elif mode == "gm":
            engine.gm.snapshot("item-reaction-window")
            engine.gm.restore("item-reaction-window", reason="restore actual pending item response")
        indexed = WORLD.actor_index(engine)
        return (engine, *(indexed[actor.entity_id] for actor in actors))

    def cloak_scene(self, move_id, *, accept=True):
        engine, attacker, wearer = self.equipment.fixture(moves=(move_id,))
        attacker.pos, wearer.pos = (2, 2), (3, 2)
        attacker.side, wearer.side = "foe", "party"
        self.equipment.equip(engine, wearer, "item/은밀망토", "recipient-scope")
        engine.start_round([attacker, wearer])
        engine.start_of_turn(attacker, initiative_count=20)
        VARIANTS.authorize_covert_cloak(engine, wearer, expected_move_id=move_id, accept=accept)
        return engine, attacker, wearer

    def test_cloak_preserves_native_attacker_stage_changes_and_rapid_spin_release(self):
        for move_id, stat, delta in (("move/오버히트", "spa", -2),
                                     ("move/니트로차지", "spe", 1),
                                     ("move/고속스핀", "spe", 1)):
            for accept in (False, True):
                with self.subTest(move=move_id, cloak=accept):
                    engine, attacker, wearer = self.cloak_scene(move_id, accept=accept)
                    if move_id == "move/고속스핀":
                        engine.grid = Grid(16, 16)
                        engine.gm.place_hazard((4, 2), "압정", reason="actual hazard inside Rapid Spin radius")
                        engine.gm.place_hazard((12, 12), "압정", reason="actual hazard outside Rapid Spin radius")
                        engine.gm.add_condition(attacker, "구속", reason="actual Rapid Spin user is Stuck")
                        engine.gm.add_condition(attacker, "수렁", reason="actual Rapid Spin user is Trapped")
                    hp = wearer.hp
                    with patch.object(Engine, "d20", return_value=18):
                        engine.use_move(attacker, wearer, move_id, set_damage=True)
                    self.assertLess(wearer.hp, hp)
                    self.assertEqual(attacker.stages[stat], delta)
                    if move_id == "move/고속스핀":
                        self.assertNotIn("구속", attacker.conditions)
                        self.assertNotIn("수렁", attacker.conditions)
                        self.assertNotIn((4, 2), engine.hazards)
                        self.assertIn((12, 12), engine.hazards)
                    self.assertTrue(engine.validate_state()["valid"])

    def test_cloak_still_blocks_wearer_status_and_stage_but_preserves_damage(self):
        for move_id in ("move/불꽃펀치", "move/아이언테일"):
            for accept in (False, True):
                with self.subTest(move=move_id, cloak=accept):
                    engine, attacker, wearer = self.cloak_scene(move_id, accept=accept)
                    hp = wearer.hp
                    with patch.object(Engine, "d20", return_value=20):
                        engine.use_move(attacker, wearer, move_id, set_damage=True)
                    self.assertLess(wearer.hp, hp)
                    if move_id == "move/불꽃펀치":
                        self.assertEqual("화상" in wearer.conditions, not accept)
                    else:
                        self.assertEqual(wearer.stages["def"], 0 if accept else -1)

    def test_cloak_one_area_recipient_does_not_protect_other_recipients(self):
        engine, attacker, wearer = self.cloak_scene("move/땅고르기")
        other = self.equipment.trainer("unprotected-area-recipient")
        engine.gm.add_combatant(other, pos=(2, 3), side="party", reason="actual additional area member")
        engine.grid = Grid(10, 10)
        hp = wearer.hp, other.hp
        with patch.object(Engine, "d20", return_value=18):
            engine.use_move_on(attacker, wearer, "move/땅고르기", engine.everyone, set_damage=True)
        self.assertLess(wearer.hp, hp[0])
        self.assertLess(other.hp, hp[1])
        self.assertEqual((wearer.stages["spe"], other.stages["spe"]), (0, -1))

    def test_cloak_recipient_filter_preserves_other_half_direct_hp_and_field_owner(self):
        engine, attacker, wearer = self.cloak_scene("move/니트로차지")
        move = self.r.move("move/니트로차지")
        VARIANTS._begin_covert_hit(engine, attacker, wearer, move)
        effects = [{"type": "stage_change", "stat": "atk", "delta": -1, "target": "both"},
                   {"type": "hp_loss", "value": 1, "target": "target"},
                   {"type": "drain", "fraction": [1, 2]},
                   {"type": "destroy_hazards", "area": "5m"},
                   {"type": "field_effect", "field": "미스트", "rounds": 5},
                   {"type": "repeat_each_turn", "until": "miss or no target"},
                   {"type": "destroy_hazards", "area": "line", "_activation_scope": "field"}]
        original = deepcopy(effects)
        result = VARIANTS.filter_move_effects(
            dict(engine=engine, attacker=attacker, target=wearer, move=move, hit=True), effects)
        self.assertEqual(effects, original)
        self.assertEqual(result, [dict(effects[0], target="self"), *effects[1:]])

    def test_cloak_preserves_native_rollout_source_owned_continuation(self):
        engine, attacker, wearer = self.cloak_scene("move/구르기")
        hp = wearer.hp
        with patch.object(Engine, "d20", return_value=18):
            engine.use_move(attacker, wearer, "move/구르기", set_damage=True)
        self.assertLess(wearer.hp, hp)
        self.assertEqual(FORCED_MOVE.current(engine, attacker), "move/구르기")
        engine, attacker = self.restore(engine, attacker, mode="json")
        self.assertEqual(FORCED_MOVE.current(engine, attacker), "move/구르기")

    def test_sleeping_eject_pack_native_growl_rejects_free_action_atomically(self):
        for mode in ("live", "json", "gm"):
            with self.subTest(mode=mode):
                engine, holder, attacker, reserves, _, uid = self.switch.fixture("eject_pack", reserve_count=1)
                engine.gm.set_move(attacker, "move/울음소리", reason="actual known Growl")
                engine.gm.add_condition(holder, "잠듦", reason="sleep does not cure from a stage drop")
                hp = holder.hp
                with patch.object(Engine, "d20", return_value=18):
                    engine.use_move(attacker, holder, "move/울음소리")
                self.assertEqual(holder.stages["atk"], -1)
                self.assertEqual(holder.hp, hp)
                self.assertIn("잠듦", holder.conditions)
                engine, holder, incoming = self.restore(engine, holder, reserves[0], mode=mode)
                assert_rejected_unchanged(engine, lambda: PHYSICAL.resolve_pending(
                    engine, holder, "eject_pack", send=incoming), reason_pattern="Free Action unavailable")
                self.assertNotIn("consumed", engine._physical_objects[uid])

    def test_eject_acceptance_records_one_free_action_after_json_and_gm_restore(self):
        for kind in ("eject_button", "eject_pack"):
            for mode in ("live", "json", "gm"):
                with self.subTest(kind=kind, mode=mode):
                    engine, holder, attacker, reserves, _, uid = self.switch.fixture(kind, reserve_count=1)
                    self.switch.trigger(engine, holder, attacker, kind)
                    engine, holder, attacker, incoming = self.restore(engine, holder, attacker, reserves[0], mode=mode)
                    budgets = deepcopy((holder.budget, attacker.budget))
                    history = list(holder._action_history)
                    result = PHYSICAL.resolve_pending(engine, holder, kind, send=incoming)
                    self.assertEqual(result["sent_id"], incoming.entity_id)
                    self.assertEqual((holder.budget, attacker.budget), budgets)
                    self.assertEqual(holder._action_history, history + ["free"])
                    self.assertFalse(holder.on_field)
                    self.assertTrue(incoming.on_field)
                    self.assertIn("consumed", engine._physical_objects[uid])
                    self.assertNotIn(kind, holder.spec.get(PHYSICAL.PENDING, {}))
                    self.assertTrue(engine.validate_state()["valid"])

    def test_next_recorded_action_expires_immediate_reactions_without_consuming_items(self):
        for kind in ("eject_button", "eject_pack"):
            engine, holder, attacker, reserves, _, uid = self.switch.fixture(kind, reserve_count=1)
            self.switch.trigger(engine, holder, attacker, kind)
            self.assertTrue(TURN.spend(engine, attacker, "shift", "actual subsequent Shift action"))
            self.assertNotIn(kind, holder.spec.get(PHYSICAL.PENDING, {}))
            assert_rejected_unchanged(engine, lambda: PHYSICAL.resolve_pending(
                engine, holder, kind, send=reserves[0]), reason_pattern="live remaining-item")
            self.assertNotIn("consumed", engine._physical_objects[uid])
            self.assertEqual(engine._physical_objects[uid][PHYSICAL.OBJECT_STATE]["scene_uses"], [])

    def test_area_attack_keeps_each_hit_recipient_immediate_window_until_a_new_action(self):
        engine, holder, attacker, reserves, _, _ = self.switch.fixture("eject_button", reserve_count=1)
        engine.gm.set_move(attacker, "move/땅고르기", reason="actual known multi-recipient Move")
        attacker.pos, holder.pos = (4, 4), (5, 4)
        for actor in engine.gm.everyone:
            if actor.kind == "trainer":
                actor.pos = (10, 10)
        other = self.f.pokemon("second-eject-recipient")
        other.spec["trainer_id"] = holder.spec["trainer_id"]
        engine.gm.add_combatant(other, pos=(4, 5), side="party", reason="actual second on-field recipient")
        self.f.equip(engine, other, "revision/second-button", "item/탈출버튼")
        engine.grid = Grid(16, 16)
        with patch.object(Engine, "d20", return_value=18):
            engine.use_move_on(attacker, holder, "move/땅고르기", engine.everyone, set_damage=True)
        self.assertIn("eject_button", holder.spec[PHYSICAL.PENDING])
        self.assertIn("eject_button", other.spec[PHYSICAL.PENDING])
        self.assertTrue(PHYSICAL.resolve_pending(engine, holder, "eject_button", send=reserves[0])["switched"])
        self.assertNotIn("eject_button", other.spec[PHYSICAL.PENDING])

    def test_turn_and_round_boundaries_expire_saved_immediate_reactions(self):
        for kind in ("eject_button", "eject_pack"):
            for next_round in (False, True):
                with self.subTest(kind=kind, next_round=next_round):
                    engine, holder, attacker, reserves, _, uid = self.switch.fixture(kind, reserve_count=1)
                    self.switch.trigger(engine, holder, attacker, kind)
                    engine.end_of_turn(attacker)
                    if next_round:
                        engine.end_round()
                        engine.start_round([attacker, holder])
                        engine.start_of_turn(holder, initiative_count=30)
                    engine, holder, incoming = self.restore(engine, holder, reserves[0], mode="json")
                    assert_rejected_unchanged(engine, lambda: PHYSICAL.resolve_pending(
                        engine, holder, kind, send=incoming), reason_pattern="window expired")
                    self.assertNotIn("consumed", engine._physical_objects[uid])

    def test_new_stage_trigger_replaces_expired_window_and_missing_legacy_window_cannot_replay(self):
        engine, holder, attacker, reserves, _, _ = self.switch.fixture("eject_pack", reserve_count=1)
        self.switch.trigger(engine, holder, attacker, "eject_pack")
        holder.spec[PHYSICAL.PENDING]["eject_pack"].pop("window")
        engine, holder, incoming = self.restore(engine, holder, reserves[0], mode="json")
        assert_rejected_unchanged(engine, lambda: PHYSICAL.resolve_pending(
            engine, holder, "eject_pack", send=incoming), reason_pattern="window expired")
        engine.change_stage(holder, "def", -1)
        self.assertEqual(holder.spec[PHYSICAL.PENDING]["eject_pack"]["event"]["stage"]["stat"], "def")
        self.assertTrue(PHYSICAL.resolve_pending(engine, holder, "eject_pack", send=incoming)["switched"])

    def test_eject_rejects_changed_physical_instance_before_consumption(self):
        for kind, item in (("eject_button", "item/탈출버튼"), ("eject_pack", "item/탈출팩")):
            engine, holder, attacker, reserves, _, uid = self.switch.fixture(kind, reserve_count=1)
            self.switch.trigger(engine, holder, attacker, kind)
            ITEMS.unregister_item(engine, holder, item)
            self.f.equip(engine, holder, uid + "/replacement", item)
            assert_rejected_unchanged(engine, lambda: PHYSICAL.resolve_pending(
                engine, holder, kind, send=reserves[0]), reason_pattern="actual held item changed")
            self.assertNotIn("consumed", engine._physical_objects[uid + "/replacement"])

    def test_failed_acceptance_and_rolled_back_next_action_preserve_window_history_and_rng(self):
        engine, holder, attacker, reserves, _, uid = self.switch.fixture("eject_button", reserve_count=1)
        self.switch.trigger(engine, holder, attacker, "eject_button")
        with patch.object(PHYSICAL, "_immediate_switch", side_effect=ValueError("late native switch failure")):
            assert_rejected_unchanged(engine, lambda: PHYSICAL.resolve_pending(
                engine, holder, "eject_button", send=reserves[0]), reason_pattern="late native switch failure")
        def failed_action(staged, actor):
            self.assertTrue(TURN.spend(staged, actor, "shift", "rolled-back subsequent action"))
            raise ValueError("later action rolled back")
        assert_rejected_unchanged(engine, lambda: GRANTS.transition(engine, attacker, failed_action),
                                  reason_pattern="later action rolled back")
        self.assertTrue(PHYSICAL.resolve_pending(engine, holder, "eject_button", send=reserves[0])["switched"])
        self.assertIn("consumed", engine._physical_objects[uid])

    def test_trapped_red_card_attacker_completes_hit_consumes_once_without_random_draw(self):
        for mode in ("live", "json", "gm"):
            with self.subTest(mode=mode):
                engine, holder, attacker, reserves, _, uid = self.switch.fixture("red_card", reserve_count=2)
                engine.gm.add_condition(attacker, "수렁", reason="actual Trapped attacker cannot recall")
                engine, holder, attacker, first, second = self.restore(engine, holder, attacker, *reserves, mode=mode)
                hp = holder.hp
                with patch.object(type(engine.rng), "choice", autospec=True,
                                  side_effect=type(engine.rng).choice) as choose:
                    self.switch.trigger(engine, holder, attacker, "red_card")
                choose.assert_not_called()
                self.assertLess(holder.hp, hp)
                self.assertTrue(attacker.on_field)
                self.assertFalse(first.on_field or second.on_field)
                self.assertIn("수렁", attacker.conditions)
                self.assertNotIn("red_card", holder.spec.get(PHYSICAL.PENDING, {}))
                obj = engine._physical_objects[uid]
                self.assertEqual(sum(row["event"] == "consumed" for row in obj[PHYSICAL.OBJECT_STATE]["history"]), 1)
                self.assertEqual(len(holder.spec["stock_consumption_receipts"]), 1)
                self.assertTrue(engine.validate_state()["valid"])

    def test_weakness_policy_keeps_its_separate_existing_scene_window(self):
        attacker = self.f.pokemon("weakness-attacker", moves=("move/번개펀치",))
        holder = self.f.pokemon("weakness-holder", types=("물",))
        engine = self.f.fixture(attacker, holder)
        self.f.equip(engine, holder, "revision/weakness", "item/약점보험")
        engine.start_round([attacker, holder])
        engine.start_of_turn(attacker, initiative_count=20)
        with patch.object(Engine, "d20", return_value=18):
            engine.use_move(attacker, holder, "move/번개펀치", set_damage=True)
        self.assertIn("weakness_policy", holder.spec[PHYSICAL.PENDING])
        self.assertTrue(TURN.spend(engine, attacker, "shift", "later action keeps separate Weakness Policy contract"))
        result = PHYSICAL.resolve_pending(engine, holder, "weakness_policy")
        self.assertEqual(result["damage_bonus"], 10)


if __name__ == "__main__":
    unittest.main()
