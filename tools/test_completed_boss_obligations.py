"""Source branches omitted by existing tests; all state changes use native consumers."""
from copy import deepcopy
from unittest.mock import patch
import unittest
from engine import Engine
from grid import Grid
import actor_templates as T
import boss_transitions as B
import condition_recovery as RECOVERY
import frequency as F
import turn as TURN
import test_category2_boss_transitions as BASE
import test_category2_swarm_transitions as SWARM


class BossObligationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not hasattr(BASE.BossTransitionTests, "r"):
            BASE.BossTransitionTests.setUpClass()
        cls.r = BASE.BossTransitionTests.r
    setUp = BASE.BossTransitionTests.setUp
    configure = BASE.BossTransitionTests.configure

    def test_party_basis_focused_turns_and_all_actual_slots_keep_baseline(self):
        self.e.gm.set_stage(self.p, "atk", value=2, reason="selected elevated baseline")
        view = self.e.gm.set_encounter_template(self.p, kind="boss", total_bars=None,
            action_slots=None, action_basis={"pokemon_turns": 2, "combat_trainers": 1,
            "focused_command_extra": 2}, base_initiative=20, reason="explicit party counts")
        self.assertEqual((view["action_count"], view["remaining_bars"]), (5, 5))
        self.e.start_round([self.a, self.p])
        for count in (25, 20, 15, 10, 5):
            self.e.start_of_turn(self.p, initiative_count=count)
            self.assertTrue(TURN.spend(self.e, self.p, "standard", "actual boss slot"))
            self.e.end_of_turn(self.p)
        receipts = self.p.spec["encounter_template"]["round_trigger_receipts"]
        self.assertEqual(sum(r.get("lifecycle") == "closed" for r in receipts.values()), 5)
        self.e.lose_hp(self.p, self.p.hp, loss_kind="hp_setting")
        self.assertEqual((self.p.stages["atk"], T.projection(self.p)["action_count"]), (2, 5))
        self.e.start_round([self.a, self.p])
        self.e.start_of_turn(self.p, initiative_count=25)
        self.assertTrue(TURN.spend(self.e, self.p, "standard", "next round actual slot"))
        self.e.end_of_turn(self.p)

    def test_current_bar_healing_hp_setting_and_damage_overflow_are_distinct(self):
        self.configure(count=5)
        self.e.lose_hp(self.p, self.p.hp + 7, loss_kind="hp_setting")
        self.assertEqual(T.projection(self.p)["remaining_bars"], 4)
        self.e.lose_hp(self.p, 10, loss_kind="hp_setting")
        self.assertEqual(self.e.heal(self.p, 10000, source_kind="move"), 10)
        self.assertEqual((self.p.hp, T.projection(self.p)["remaining_bars"]), (self.p.max_hp, 4))
        self.e.take_damage(self.p, self.p.hp + 3)
        self.assertEqual((T.projection(self.p)["remaining_bars"], self.p.hp), (3, self.p.max_hp - 3))
        self.assertEqual(self.p.spec["encounter_template"]["bar_transition_receipts"][-1]["carried_over"], 3)
        self.assertEqual(self.p.injuries, 1)  # Massive damage, not half-bar loss yet.
        self.e.heal(self.p, 10000, source_kind="move")
        self.assertEqual(T.projection(self.p)["remaining_bars"], 3)
        self.setUp(); self.configure(count=5)
        self.e.gm.set_temp_hp(self.p, 100, reason="direct HP-setting remains distinct", duration_seconds=300)
        self.e.apply_effect(self.p, self.p, {"type": "damage_cap", "value": 1},
            nat=20, hit=True, dealt=0, src="test/existing-loss-cap")
        before = self.p.hp
        self.e.lose_hp(self.p, 7, loss_kind="hp_setting")
        self.assertEqual((self.p.hp, self.p.temp_hp), (before - 7, 100))
        snapshot = deepcopy((self.p.hp, self.p.temp_hp, self.p.injuries, self.p.spec))
        for invalid in (None, False, [], {}, "other"):
            with self.subTest(invalid_loss_kind=invalid):
                with self.assertRaisesRegex(ValueError, "^loss_kind must be loss, percentage or hp_setting$"):
                    self.e.lose_hp(self.p, 1, loss_kind=invalid)
                self.assertEqual((self.p.hp, self.p.temp_hp, self.p.injuries, self.p.spec), snapshot)

    def test_marker_exclusion_massive_damage_and_explicit_injury_remain_distinct(self):
        self.configure(count=5)
        self.e.lose_hp(self.p, (self.p.base_max_hp + 1) // 2)
        self.assertEqual(self.p.injuries, 0)
        self.e.heal(self.p, 10000, source_kind="move")
        self.e.take_damage(self.p, (self.p.base_max_hp + 1) // 2)
        self.assertEqual(self.p.injuries, 1)
        self.e.apply_effect(self.a, self.p, {"type": "injury", "value": 1, "target": "target"},
                            nat=20, hit=True, dealt=0, src="C11-124/explicit-injury")
        self.assertEqual(self.p.injuries, 2)
        self.e.lose_hp(self.p, self.p.hp, loss_kind="hp_setting")
        self.assertEqual(self.p.hp, self.p.max_hp)
        self.assertEqual(self.p.injuries, 2)
        self.assertEqual(T.projection(self.p)["remaining_bars"], 4)

    def test_stagger_has_no_default_and_selected_volatile_cure_and_scene_refresh(self):
        self.configure(count=4)
        self.e.apply_status(self.p, "혼란", source="test/confusion")
        self.e.lose_hp(self.p, self.p.hp, loss_kind="hp_setting")
        view = T.projection(self.p)
        self.assertFalse(view["boss_runtime"]["vulnerable_until_damaged"])
        self.assertEqual(view["boss_runtime"]["pending_skip_turns"], 0)
        self.assertIn("혼란", self.p.conditions)
        self.assertEqual(view["bar_transition_receipts"][-1]["effects"], [])
        self.setUp()
        mid = "move/나비춤"
        self.e.gm.set_move(self.p, mid, True, reason="possessed Scene move")
        self.configure(count=4, effects=[
            {"when": "bar_lost", "kind": "cure_volatile", "condition": "혼란"},
            {"when": "bar_lost", "kind": "refresh_scene_move", "move_id": mid}])
        self.e.start_round([self.a, self.p])
        self.e.start_of_turn(self.p, initiative_count=20)
        self.assertIsNot(self.e.use_move(self.p, self.p, mid), False)
        self.e.end_of_turn(self.p)
        self.e.apply_status(self.p, "혼란", source="test/confusion")
        self.e.lose_hp(self.p, self.p.hp, loss_kind="hp_setting")
        self.assertNotIn("혼란", self.p.conditions)
        self.assertNotIn(mid, self.p.move_uses)
        self.e.start_of_turn(self.p, initiative_count=15)
        self.assertTrue(F.move_allowed(self.e, self.p, mid)[0])
        self.assertIsNot(self.e.use_move(self.p, self.p, mid), False)
        self.assertEqual(self.p.move_uses[mid], 1)
        self.e.end_of_turn(self.p)

    def test_public_boss_move_use_respects_eot_and_scene_spacing_between_real_slots(self):
        for mid in ("move/공격지령", "move/벌레의야단법석"):
            with self.subTest(move=mid):
                self.setUp()
                self.e.gm.set_move(self.p, self.p.moves[0], False, reason="explicit forgotten move")
                self.e.gm.set_move(self.p, mid, True, reason="boss attack with sourced frequency")
                self.e.gm.set_stat(self.a, "hp", value=100, reason="durable training target")
                self.e.gm.set_hp(self.a, value=self.a.max_hp, reason="target at full health")
                self.configure(); self.e.start_round([self.a, self.p])
                for count in (20, 15, 10):
                    self.e.start_of_turn(self.p, initiative_count=count)
                    with patch.object(Engine, "d20", return_value=20):
                        result = self.e.use_move(self.p, self.a, mid, situational=100, set_damage=True)
                    if count == 15:
                        self.assertEqual(result, 0)
                        self.assertEqual(self.p.budget["standard"], 1)
                        self.assertEqual(self.p.move_uses[mid], 1)
                    else:
                        self.assertIsNot(result, False)
                        self.assertEqual(self.p.budget["standard"], 0)
                    self.e.end_of_turn(self.p)
                self.assertEqual(self.p.move_uses[mid], 2)

    def test_final_bar_clear_debuffs_is_selected_and_not_implicit(self):
        for selected in (False, True):
            with self.subTest(selected=selected):
                self.setUp()
                self.configure(count=3, effects=[{"when": "final_bar", "kind": "clear_debuffs"}] if selected else [])
                self.e.gm.set_stage(self.p, "def", value=-2, reason="encounter debuff")
                self.e.apply_status(self.p, "독", source="test/poison")
                for _ in range(2):
                    self.e.lose_hp(self.p, self.p.hp, loss_kind="hp_setting")
                self.assertEqual(self.p.stages["def"], 0 if selected else -2)
                self.assertEqual("독" in self.p.conditions, not selected)
                self.assertEqual(self.p.stages["atk"], 2)

    def test_periodic_percentage_loss_cannot_damage_the_next_bar(self):
        for source in ("화상", "독", "저주", "sandstorm", "hail"):
            with self.subTest(source=source):
                self.setUp(); self.configure(count=5)
                self.e.gm.set_hp(self.p, value=1, reason="current bar near exhaustion")
                if source not in ("sandstorm", "hail"):
                    self.e.apply_status(self.p, source, source="test/percent-boundary")
                else:
                    self.e.gm.set_weather(source, rounds=5, reason="percentage weather loss")
                self.e.start_round([self.a, self.p])
                self.assertEqual(T.projection(self.p)["remaining_bars"], 4)
                self.assertEqual(self.p.hp, self.p.max_hp)

    def test_percentage_bar_scope_preserves_existing_temp_hp_and_damage_cap_layers(self):
        # C11-122 scopes a percentage loss to one bar; it does not turn the
        # actual condition/weather loss into a direct HP-setting operation.
        for source in ("화상", "독", "저주", "sandstorm", "hail"):
            for capped in (False, True):
                with self.subTest(source=source, capped=capped):
                    self.setUp(); self.configure(count=5)
                    self.e.gm.set_hp(self.p, value=1, reason="current bar near exhaustion")
                    self.e.gm.set_temp_hp(self.p, 100, reason="existing shared barrier", duration_seconds=300)
                    if capped:
                        self.e.apply_effect(self.p, self.p, {"type": "damage_cap", "value": 1},
                            nat=20, hit=True, dealt=0, src="test/existing-loss-cap")
                    if source in ("sandstorm", "hail"):
                        self.e.gm.set_weather(source, rounds=5, reason="percentage weather loss")
                    else:
                        self.e.apply_status(self.p, source, source="test/percentage-loss-layers")
                    self.e.start_round([self.a, self.p])
                    self.assertEqual((self.p.hp, T.projection(self.p)["remaining_bars"]), (1, 5))
                    self.assertLess(self.p.temp_hp, 100)
                    if capped:
                        self.assertEqual(self.p.temp_hp, 99)

    def test_final_bar_clear_debuffs_includes_boss_sleep_variants(self):
        for condition, variant in (("잠듦", "졸음"), ("얼음", "냉각")):
            with self.subTest(condition=condition):
                self.setUp()
                self.configure(count=3, effects=[{"when": "final_bar", "kind": "clear_debuffs"}])
                self.e.apply_status(self.p, condition, source="test/variant-clear")
                for _ in range(2):
                    self.e.lose_hp(self.p, self.p.hp, loss_kind="hp_setting")
                self.assertNotIn(variant, self.p.conditions)
                self.assertNotIn(variant, T.projection(self.p)["condition_bindings"])

    def test_drowsy_retains_original_natural_recovery_entrypoint(self):
        self.configure()
        self.e.apply_status(self.p, "잠듦", source="test/natural-sleep")
        receipt = self.e.recover_condition(self.p, "잠듦", duration_minutes=1, reason="GM observed natural rest")
        self.assertEqual(receipt["condition"], "잠듦")
        self.assertNotIn("졸음", self.p.conditions)

    def test_original_named_effect_medicine_berry_and_ally_cures_accept_boss_aliases(self):
        cases = [("ally", "잠듦", "졸음"), ("effect", "잠듦", "졸음"),
                 ("effect", "얼음", "냉각"), ("medicine", "얼음", "냉각"),
                 ("유루열매", "잠듦", "졸음"), ("배리열매", "얼음", "냉각")]
        for method, condition, stored in cases:
            with self.subTest(method=method, condition=condition):
                self.setUp(); self.configure(); self.p.side = self.a.side
                self.e.grid = Grid(10, 10)
                for actor in (self.a, self.p):
                    self.e.gm.set_footprint(actor, [(0, 0)], reason="actual adjacent ally bodies")
                self.e.apply_status(self.p, condition, source="test/normal-cure-contract")
                self.e.apply_status(self.p, "독", source="test/unrelated-status")
                before_hp = self.p.hp
                if method == "ally":
                    self.e.start_round([self.a, self.p]); self.e.start_of_turn(self.a, initiative_count=30)
                    before_hp = self.p.hp
                    self.assertTrue(self.e.wake_ally(self.a, self.p))
                    self.assertEqual(self.a.budget["standard"], 0)
                elif method == "effect":
                    self.e.apply_effect(self.a, self.p,
                        {"type": "cure_status", "status": condition, "target": "target"},
                        nat=20, hit=True, dealt=0, src="test/selected-named-cure-effect")
                elif method == "medicine":
                    self.a.spec["items"] = {"얼음상태치료제": 1}
                    self.e.use_item(self.a, "얼음상태치료제", self.p)
                    self.assertEqual(self.a.spec["items"]["얼음상태치료제"], 0)
                else:
                    self.a.spec["items"] = {method: 1}
                    food = self.e.use_item(self.a, method, self.p, duration_minutes=1,
                        duration_reason="GM observed actual Berry intake")
                    self.assertEqual(self.a.spec["items"][method], 0)
                    result = self.e.consume_food_buff(self.p, buff_id=food["buff_id"],
                        action_kind="swift", action_reason="GM declared actual digestion timing")
                    self.assertTrue(result["cured"])
                    self.assertFalse(self.p.buffs)
                self.assertNotIn(stored, self.p.conditions)
                self.assertNotIn(stored, T.projection(self.p)["condition_bindings"])
                self.assertEqual(self.p.hp, before_hp)
                self.assertIn("독", self.p.conditions)
                self.assertTrue(self.e.validate_state()["valid"])

    def test_chilled_retains_post_combat_thaw_through_scene_and_actual_recovery(self):
        self.configure()
        self.e.apply_status(self.p, "얼음", source="test/post-combat-thaw")
        self.e.start_round([self.a, self.p])
        self.e.end_encounter([self.a, self.p], round_elapsed_seconds=10)
        self.e.end_scene([self.a, self.p])
        receipt = self.e.recover_condition(self.p, "냉각", duration_minutes=1, reason="GM observed post-combat thaw")
        self.assertEqual(receipt["condition"], "얼음")
        self.assertNotIn("냉각", self.p.conditions)
        self.assertNotIn("condition_recovery_available", self.p.custom_conditions)
        self.assertTrue(self.e.validate_state()["valid"])

    def test_chilled_keeps_sourced_typed_attack_cure_and_drowsy_stays_volatile(self):
        for mid in ("move/불꽃세례", "move/깨트리기", "move/돌떨구기", "move/메탈클로", "move/몸통박치기"):
            with self.subTest(move=mid):
                self.setUp(); self.configure(count=5)
                self.e.gm.set_move(self.a, mid, True, reason="selected sourced thaw attack")
                self.e.apply_status(self.p, "얼음", source="test/typed-thaw")
                self.e.start_round([self.a, self.p]); self.e.start_of_turn(self.a, initiative_count=30)
                with patch.object(Engine, "d20", return_value=20):
                    self.e.use_move(self.a, self.p, mid, situational=100, set_damage=True)
                self.assertEqual("냉각" in self.p.conditions, mid == "move/몸통박치기")
                self.e.end_of_turn(self.a)
        self.setUp(); self.configure()
        self.e.apply_status(self.p, "잠듦", source="test/volatile-drowsy")
        self.e.begin_encounter([self.a, self.p]); self.e.end_encounter([self.a, self.p])
        self.assertNotIn("졸음", self.p.conditions)

    def test_all_periodic_losses_consume_round_boundary_once(self):
        for source in ("화상", "독", "저주", "sandstorm", "hail"):
            with self.subTest(source=source):
                self.setUp(); self.configure(count=3)
                if source in ("sandstorm", "hail"):
                    self.e.gm.set_weather(source, rounds=5, reason="observed hazardous weather")
                else:
                    self.assertTrue(self.e.apply_status(self.p, source, source="test/periodic"))
                before = self.p.hp
                self.e.start_round([self.a, self.p])
                after = self.p.hp
                self.assertLess(after, before)
                B.start_round(self.e, self.p)
                for count in (20, 15, 10):
                    self.e.start_of_turn(self.p, initiative_count=count)
                    self.e.end_of_turn(self.p)
                    self.assertEqual(self.p.hp, after)
                self.e.start_round([self.a, self.p])
                self.assertLess(self.p.hp, after)

    def test_confusion_and_paralysis_bind_next_slot_across_rounds_until_cured(self):
        for condition in ("혼란", "마비"):
            with self.subTest(condition=condition):
                self.setUp(); self.configure()
                self.e.start_round([self.a, self.p])
                self.e.start_of_turn(self.p, initiative_count=20); self.e.end_of_turn(self.p)
                self.e.apply_status(self.p, condition, source="test/slot-condition")
                for _ in range(2):
                    for count in ((15, 10) if _ == 0 else (20, 15, 10)):
                        with patch.object(RECOVERY, "saving_check", return_value={"passed": False}), patch.object(Engine, "d20", return_value=1):
                            self.e.start_of_turn(self.p, initiative_count=count)
                            self.assertEqual(B.condition_applies_this_turn(self.p, condition), count == 15)
                            self.e.end_of_turn(self.p)
                    if _ == 0:
                        self.e.start_round([self.a, self.p])
                self.e.cure_status(self.p, condition)
                self.assertNotIn(condition, T.projection(self.p)["condition_bindings"])

    def test_both_sleep_variants_keep_all_turns_and_share_save_and_explicit_cure(self):
        for condition, variant in (("잠듦", "졸음"), ("얼음", "냉각")):
            with self.subTest(condition=condition):
                self.setUp(); self.configure()
                ordinary = self.p.evasion("물리")
                self.e.apply_status(self.p, condition, source="test/variant")
                self.e.start_round([self.a, self.p])
                for count in (20, 15):
                    self.e.start_of_turn(self.p, initiative_count=count)
                    self.assertTrue(TURN.spend(self.e, self.p, "standard", "variant still acts"))
                    self.assertEqual(self.p.evasion("물리"), ordinary // 2)
                    with patch.object(RECOVERY, "saving_check", return_value={"passed": False}):
                        self.e.end_of_turn(self.p)
                    penalized = self.e.roll_damage(self.p, self.a, self.r.move("move/몸통박치기"), set_damage=True)
                    normal = self.e.roll_damage(self.p, self.a, self.r.move("move/몸통박치기"), set_damage=True)
                    self.assertEqual(normal - penalized, 10)
                self.e.take_damage(self.p, 1)
                self.assertIn(variant, self.p.conditions)
                self.e.start_of_turn(self.p, initiative_count=10)
                with patch.object(RECOVERY, "saving_check", return_value={"passed": True}):
                    self.e.end_of_turn(self.p)
                self.assertNotIn(variant, self.p.conditions)
                self.e.apply_status(self.p, condition, source="test/explicit-cure")
                self.e.cure_status(self.p, condition)
                self.assertNotIn(variant, self.p.conditions)

    def test_disabled_one_move_and_flinch_skip_only_one_actual_slot(self):
        first, other = "move/공격지령", "move/벌레의야단법석"
        for mid in [m for m in self.p.moves if m != "struggle"][:2]:
            self.e.gm.set_move(self.p, mid, False, reason="explicit forgotten-move choice")
        for mid in (first, other):
            self.e.gm.set_move(self.p, mid, True, reason="selected boss move")
        self.configure(); self.e.start_round([self.a, self.p])
        self.e.apply_status(self.p, "사슬묶기", parameters={"move_id": first}, source="test/disabled")
        self.e.start_of_turn(self.p, initiative_count=20)
        self.assertFalse(self.e.use_move(self.p, self.a, first))
        self.assertTrue(TURN.spend(self.e, self.p, "standard", "unlocked action"))
        self.assertTrue(self.e.apply_status(self.p, "풀죽음", source="test/flinch"))
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.p, initiative_count=15)
        self.assertFalse(TURN.spend(self.e, self.p, "standard", "one lost slot"))
        self.assertFalse(self.e.apply_status(self.p, "풀죽음", source="test/second-flinch"))
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.p, initiative_count=10)
        self.assertTrue(TURN.spend(self.e, self.p, "standard", "later slot retained"))
        self.e.end_of_turn(self.p)

    def test_capture_restores_normal_form_removes_template_and_preserves_identity(self):
        self.configure(count=2, capture_level=5, effects=[
            {"when": "final_bar", "kind": "unlock_move", "move_id": "move/벌레의야단법석"}])
        normal = deepcopy(self.p.spec["encounter_template"]["normal_form_baseline"])
        identity = self.p.entity_id
        self.a.spec["items"] = {"몬스터볼": 2}
        self.e.start_round([self.a, self.p]); self.e.start_of_turn(self.a, initiative_count=30)
        budget = dict(self.a.budget); before_rng = self.e.rng.getstate()
        self.assertFalse(self.e.throw_ball(self.a, self.p, fixed_accuracy=20, fixed_capture=20))
        self.assertEqual((self.a.budget, self.a.spec["items"], self.e.rng.getstate()), (budget, {"몬스터볼": 2}, before_rng))
        self.e.lose_hp(self.p, self.p.hp, loss_kind="hp_setting")
        self.assertFalse(T.projection(self.p)["capture_immune"])
        self.assertTrue(self.e.throw_ball(self.a, self.p, fixed_accuracy=20, fixed_capture=20))
        self.e.end_of_turn(self.a)
        self.assertEqual((self.p.entity_id, self.p.level), (identity, 5))
        for field in ("stats", "moves", "abilities", "types"):
            self.assertEqual(getattr(self.p, field), normal[field])
        self.assertIsNone(T.active(self.p))
        self.assertNotIn("move/벌레의야단법석", self.p.moves)
        self.assertTrue(self.e.validate_state()["valid"])
        loaded = Engine.import_state(self.r, self.e.export_state())
        restored = next(c for c in loaded.everyone if c.entity_id == identity)
        self.assertIsNone(T.active(restored))
        self.assertEqual(restored.level, 5)


class SwarmPublicObligationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not hasattr(SWARM.SwarmTransitionTests, "r"):
            SWARM.SwarmTransitionTests.setUpClass()
        cls.r = SWARM.SwarmTransitionTests.r
    setUp = SWARM.SwarmTransitionTests.setUp
    configure = SWARM.SwarmTransitionTests.configure
    open_turn = SWARM.SwarmTransitionTests.open_turn

    def test_all_standard_costs_are_consumed_by_public_use_move(self):
        for mid, cost in ((SWARM.AT_WILL, 1), (SWARM.EOT, 2), (SWARM.SCENE, 3), (SWARM.DAILY, 4)):
            with self.subTest(move=mid):
                self.setUp(); row = self.open_turn(5)
                target = self.p if mid in (SWARM.SCENE, SWARM.DAILY) else self.t
                for _ in range(2):
                    with patch.object(Engine, "d20", return_value=20):
                        # Successful non-damaging moves return integer 0.
                        result = self.e.use_move(self.p, target, mid, situational=100, set_damage=True)
                        self.assertIsNot(result, False, self.e.log_lines[-10:])
                self.assertEqual(row["swarm_points"], 5 - cost)
                self.assertEqual(self.p.move_uses[mid], 2)
                receipt = row["round_trigger_receipts"][row["own_turn_key"]]
                self.assertEqual([a["point_cost"] for a in receipt["actions"]], [0, cost])
                self.e.end_of_turn(self.p)
                self.e.take_damage(self.p, self.p.hp + 1)
                self.e.start_round(self.e.everyone); self.e.start_of_turn(self.p, initiative_count=20)
                self.assertEqual(self.p.spec["encounter_template"]["swarm_points"], 4)

    def test_swift_and_free_scene_eot_and_at_will_consume_separate_quotas(self):
        for kind in ("swift", "free"):
            for mid, frequency in ((SWARM.SCENE_SWIFT, "scene"), (SWARM.AT_WILL_SWIFT, "at_will"), (SWARM.EOT, "every_other_turn")):
                with self.subTest(kind=kind, move=mid):
                    self.setUp(); row = self.open_turn(3)
                    self.p.registry.append({"type": "action_type_change", "moves": self.r.move(mid)["name"], "to": kind})
                    allowance = 3 if frequency == "scene" else 1
                    for _ in range(allowance):
                        self.assertTrue(F.move_allowed(self.e, self.p, mid)[0])
                        self.assertTrue(TURN.spend(self.e, self.p, kind, "swarm quick move", _native_move=self.r.move(mid)))
                        F.consume_move(self.e, self.p, mid)
                    self.assertFalse(F.move_allowed(self.e, self.p, mid)[0])
                    self.assertEqual(row["swarm_points"], 3)
                    self.assertTrue(TURN.spend(self.e, self.p, "standard", "next swarm action", _native_move=self.r.move(SWARM.AT_WILL)))
                    self.assertEqual(F.move_allowed(self.e, self.p, mid)[0], frequency != "scene")

    def test_sleep_and_ice_at_multiplier_one_preserve_minimum_action_and_next_turn_points(self):
        for condition in ("잠듦", "얼음"):
            with self.subTest(condition=condition):
                self.setUp(); row = self.open_turn(1, condition)
                self.assertEqual(row["swarm_points"], 0)
                self.assertTrue(TURN.spend(self.e, self.p, "standard", "minimum action", _native_move=self.r.move(SWARM.AT_WILL)))
                self.assertFalse(TURN.spend(self.e, self.p, "standard", "no points for second", _native_move=self.r.move(SWARM.AT_WILL)))
                self.e.end_of_turn(self.p)
                self.e.cure_status(self.p, condition)
                self.e.start_round(self.e.everyone); self.e.start_of_turn(self.p, initiative_count=20)
                self.assertEqual(row["swarm_points"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
