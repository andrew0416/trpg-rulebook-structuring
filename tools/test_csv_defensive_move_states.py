"""Native consumers for CSV466/629/832; reuse existing state and action owners."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from engine import Rules
from action_metadata import ActionCost
from native_scenario_fixture import prepare_scene, assert_rejected_unchanged
import body_modes as MODES
import body_state as BODY
import combat_state_lifecycle as COMBAT
import declarative_move_contracts as DMC
import defense_curl as CURL_OWNER
import effects_ext as EXT
import invisibility_state as INV
import map_terrain as TERRAIN
import movement_actions as MOVEMENT
import setup_move_state as SETUP
import state_codec as CODEC
import turn as TURN
import world_entities as WORLD

CURL = "move/웅크리기"
WITHDRAW = "move/껍질에숨기"
ACID = "move/녹기"
TACKLE = "move/몸통박치기"
ROLL = "move/구르기"
ICE = "move/아이스볼"
FLAME = "move/니트로차지"
WATER = "move/물대포"


class DefensiveMoveStateTests(unittest.TestCase):
    def fixture(self, moves=(CURL, WITHDRAW, ACID, TACKLE), *, role="trainer"):
        stats = dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 20)
        actor = dict(key="user", kind=role,
                     sheet=dict(name="defensive user", level=30, moves=list(moves), abilities=[],
                                pos=(2, 2), side="party"),
                     body=dict(size="중형", offsets=[(0, 0)], reason="actual one-cell body"))
        if role == "trainer":
            actor["sheet"]["stats"] = stats
        else:
            actor["sheet"]["species"] = "이브이"
        enemy = dict(key="enemy", kind="trainer",
                     sheet=dict(name="defensive enemy", level=30, stats=stats,
                                moves=[TACKLE, FLAME, WATER], abilities=[], pos=(5, 2), side="enemy"),
                     body=dict(size="중형", offsets=[(0, 0)], reason="actual one-cell opponent"))
        self.e, actors = prepare_scene(str(ROOT), ruleset="all", seed=466629832,
                                       grid=dict(width=12, height=8), actors=[actor, enemy])
        self.a, self.b = actors["user"], actors["enemy"]
        self.r = self.e.r
        self.e.gm.set_movement_capabilities(self.a, {"land": 4}, basis="base",
                                           reason="actual Overland four")
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def turn(self, actor=None):
        if self.e._active_turn_actor is not None:
            self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor or self.a, initiative_count=20)

    def cast(self, source, *, variant=None):
        if variant is not None:
            if source == CURL:
                self.e.choose_defense_curl_source(self.a, "september_playtest",
                                                  reason="explicit actual CSV September source choice")
            else:
                DMC.choose(self.e, self.a, self.a, source, variant=variant,
                           reason="explicit actual CSV September source choice")
        with patch.object(self.e, "d20", side_effect=AssertionError("Self status Move has no AC")):
            self.e.use_move(self.a, self.a, source)
        self.assertEqual(self.a.budget["standard"], 0)

    def prepare_acid(self):
        with patch.object(self.e, "d20", side_effect=AssertionError("Acid preparation has no AC")):
            self.e.use_setup_move_on(self.a, self.a, ACID, self.e.everyone, setup_options={})
        self.assertEqual(self.a.budget["standard"], 0)
        self.assertTrue(SETUP.liquefied(self.a))
        self.assertNotIn(ACID, self.a.move_uses)

    def test_exact_three_source_contracts_and_immutable_variant_admission(self):
        self.fixture()
        rows = DMC.policy(self.r)["moves"]
        self.assertNotIn(CURL, rows)
        self.assertEqual(CURL_OWNER.MOVE, CURL)
        CURL_OWNER.policy(self.r)
        self.assertEqual(rows[WITHDRAW]["record"], 832)
        acid = next(row for row in SETUP.declarations(self.r) if row["move_id"] == ACID)
        self.assertEqual((acid["record"], acid["kind"]), (629, "acid_armor"))
        self.assertNotIn(629, [row["record"] for row in SETUP.deferred(self.r)])
        assert_rejected_unchanged(self.e, lambda: DMC.choose(
            self.e, self.a, self.b, WITHDRAW, variant="korean_csv_september", reason="wrong target"),
            reason_pattern="self source variant")
        assert_rejected_unchanged(self.e, lambda: DMC.choose(
            self.e, self.a, self.a, WITHDRAW, variant="invented", reason="unreviewed edition"),
            reason_pattern="self source variant")
        assert_rejected_unchanged(self.e, lambda: self.e.use_move(self.a, self.a, ACID),
                                  reason_pattern="use_setup_move_on")

    def test_core_curl_actual_dr_critical_accuracy_slow_and_paid_swift_end(self):
        for role in ("trainer", "pokemon"):
            with self.subTest(role=role):
                self.fixture(role=role)
                attack = self.r.move(TACKLE)
                if role == "trainer":
                    self.e.gm.set_stat(self.a, "def", value=1, reason="actual low Defense for falling DR observation")
                    self.e.gm.observe_trainer_weight(self.a, 150, unit="lb", reason="actual falling body weight")
                    fall_options = dict(meters=2, intentional=False, reason="actual two-metre fall",
                                        natural_sky=False, natural_sky_reason="observed no natural Sky", fixed_damage=[6])
                    before_fall = self.e.falling_damage(self.a, action_id="curl-fall-before", **fall_options)
                before_damage = self.e.roll_damage(self.b, self.a, attack, set_damage=True)
                ctx = dict(attacker=self.a, target=self.b, move=attack, hit=True, nat=10, engine=self.e)
                before_accuracy = EXT.accuracy_hook(self.e, self.a, self.b, attack, self.r.move_mech(TACKLE)[0], ctx)[2]
                self.cast(CURL)
                self.assertEqual(self.e.move_profile(self.a, "land")[0], 2)
                self.assertEqual(self.e.roll_damage(self.b, self.a, attack, set_damage=True),
                                 max(1, before_damage - 10))
                self.assertEqual(EXT.accuracy_hook(self.e, self.a, self.b, attack, self.r.move_mech(TACKLE)[0], ctx)[2],
                                 before_accuracy - 4)
                self.assertFalse(self.e.accuracy_check(self.b, self.a, attack, fixed_roll=20)[2])
                if role == "trainer":
                    protected_fall = self.e.falling_damage(self.a, action_id="curl-fall-protected", **fall_options)
                    self.assertEqual(protected_fall["damage"], max(1, before_fall["damage"] - 10))
                self.assertIsNotNone(CURL_OWNER.live(self.a))
                self.assertTrue(self.e.stop_defense_curl(self.a))
                self.assertEqual(self.a.budget["swift"], 0)
                self.assertIsNone(CURL_OWNER.live(self.a))
                self.assertEqual(self.e.move_profile(self.a, "land")[0], 4)
                self.assertEqual(self.e.roll_damage(self.b, self.a, attack, set_damage=True), before_damage)
                ended = self.a.spec["effect_instance_history"][-1]["effect_instance"]["end_event"]
                ended["boundary"] = "shift"
                with self.assertRaises(CODEC.StateCodecError):
                    CODEC.dump_engine(self.e)
                ended["boundary"] = "swift"
                self.e.validate_state()

    def test_curl_current_rolling_move_list_exception_and_real_damage_roll_bonus(self):
        self.fixture((CURL, TACKLE, ROLL, ICE))
        for source in (ROLL, ICE):
            with self.subTest(source=source):
                move = self.r.move(source)
                before = self.e.roll_damage(self.a, self.b, move, set_damage=True)
                if CURL_OWNER.live(self.a) is None:
                    self.cast(CURL)
                self.assertEqual(self.e.move_profile(self.a, "land")[0], 4)
                self.assertEqual(CURL_OWNER.accuracy(self.a, move), 0)
                self.assertEqual(self.e.roll_damage(self.a, self.b, move, set_damage=True), before + 10)
                self.assertTrue(self.e.stop_defense_curl(self.a))
                self.turn()
        self.cast(CURL)
        self.e.gm.set_move(self.a, ROLL, add=False, reason="actual forgetting")
        self.e.gm.set_move(self.a, ICE, add=False, reason="actual forgetting")
        self.assertEqual(self.e.move_profile(self.a, "land")[0], 2)
        self.e.gm.set_move(self.a, ICE, reason="actual current learned Ice Ball")
        self.assertEqual(self.e.move_profile(self.a, "land")[0], 4)

    def test_core_withdraw_actual_restrictions_dr_restore_and_paid_shift_end(self):
        self.fixture()
        attack = self.r.move(TACKLE)
        baseline = self.e.roll_damage(self.b, self.a, attack, set_damage=True)
        self.cast(WITHDRAW)
        self.assertFalse(TURN.movement_permission(self.e, self.a))
        self.assertEqual(self.e.roll_damage(self.b, self.a, attack, set_damage=True), max(1, baseline - 15))
        self.assertFalse(self.e.accuracy_check(self.b, self.a, attack, fixed_roll=20)[2])
        self.turn()
        for operation in (
                lambda: self.e.use_move(self.a, self.b, TACKLE),
                lambda: self.e.use_move_on(self.a, self.b, TACKLE, self.e.everyone)):
            assert_rejected_unchanged(self.e, operation, reason_pattern="Self-range")
        DMC.require_defensive_move(self.a, self.r.move(ACID))  # Self, Set-Up remains a Self Move.
        self.e.gm.snapshot("withdraw")
        restored = CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        holder = next(row for row in restored.everyone if row.entity_id == self.a.entity_id)
        self.assertFalse(TURN.movement_permission(restored, holder))
        DMC.end_defensive_stance(restored, holder, WITHDRAW, reason="actual paid emergence")
        self.assertEqual(holder.budget["shift"], 0)
        self.assertTrue(TURN.movement_permission(restored, holder))
        self.assertTrue(DMC.live(self.a, "defensive_stance"))
        self.e.gm.restore("withdraw")
        self.assertFalse(TURN.movement_permission(self.e, self.a))
        restored.validate_state()

    def test_september_variants_never_mix_core_bonuses_and_native_curl_boundaries(self):
        for boundary in ("scene", "switch", "breather"):
            with self.subTest(boundary=boundary):
                self.fixture((CURL, WITHDRAW, ROLL))
                self.cast(CURL, variant="korean_csv_september")
                self.assertEqual(self.a.stages["def"], 1)
                self.assertEqual(CURL_OWNER.reduction(self.a), 0)
                self.assertFalse(CURL_OWNER.critical_immune(self.a))
                self.assertEqual(CURL_OWNER.accuracy(self.a, self.r.move(TACKLE)), 0)
                self.assertEqual(CURL_OWNER.damage_bonus(self.a, self.r.move(ROLL)), 10)
                self.assertEqual(self.e.move_profile(self.a, "land")[0], 4)
                self.turn()
                if boundary == "scene":
                    self.e.end_scene(self.e.everyone, round_elapsed_seconds=0)
                elif boundary == "switch":
                    COMBAT.recall(self.e, self.a)
                else:
                    self.e.apply_status(self.a, "구속")
                    result = self.e.take_breather(
                        self.a, request_id="september-curl-breather", path=[self.a.pos],
                        retreat_reason="actual Stuck prevents retreat", save_dc=16,
                        save_reason="explicit table permission DC", save_cost="full", fixed_save=20)
                    self.assertTrue(result["completed"])
                    self.assertEqual(self.a.budget["standard"], 0)
                self.assertIsNone(CURL_OWNER.live(self.a))
        self.fixture((WITHDRAW, TACKLE))
        self.cast(WITHDRAW, variant="korean_csv_september")
        self.assertEqual(self.a.stages["def"], 1)
        self.assertFalse(DMC.live(self.a, "defensive_stance"))
        self.assertTrue(TURN.movement_permission(self.e, self.a))
        self.assertEqual(DMC.defensive_reduction(self.a), 0)
        self.assertEqual(DMC.history(self.a)[-1]["payload"]["variant"], "korean_csv_september")
        self.e.validate_state()

    def test_acid_native_preparation_action_lock_exact_later_resolution_and_restore(self):
        self.fixture()
        self.prepare_acid()
        actual_turn = self.a.custom_conditions.pop(SETUP.TURN_STATE)
        try:
            with self.assertRaisesRegex(ValueError, "actual own-turn liquid state"):
                SETUP.liquefied(self.a)
        finally:
            self.a.custom_conditions[SETUP.TURN_STATE] = actual_turn
        self.assertEqual(SETUP.pending(self.a)["prepared_turn"], actual_turn["prepared_turn"])
        self.assertEqual(self.a.stages["def"], 0)
        self.assertTrue(TURN.movement_permission(self.e, self.a))
        self.assertEqual(self.e.move_profile(self.a, "land")[0], 2)
        assert_rejected_unchanged(self.e, lambda: self.e.use_setup_move_on(
            self.a, self.a, ACID, self.e.everyone, setup_options={}),
            reason_pattern="following actual own turn")
        self.turn()
        resources = deepcopy((self.a.budget, self.a.move_uses, self.e.rng.getstate()))
        for cost in ("standard", "full", ActionCost(("standard", "swift"))):
            self.assertFalse(TURN.spend(self.e, self.a, cost, "liquid prohibited Standard"))
        assert_rejected_unchanged(self.e, lambda: self.e.use_move(self.a, self.b, TACKLE),
                                  reason_pattern="prepared setup Move")
        self.assertEqual((self.a.budget, self.a.move_uses, self.e.rng.getstate()), resources)
        self.assertTrue(TURN.spend(self.e, self.a, "swift", "legal liquid Swift"))
        self.e = CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        by_id = {row.entity_id: row for row in self.e.everyone}
        self.a, self.b = by_id[self.a.entity_id], by_id[self.b.entity_id]
        self.assertTrue(SETUP.liquefied(self.a))
        self.e.use_setup_move_on(self.a, self.a, ACID, self.e.everyone, setup_options={})
        self.assertFalse(SETUP.liquefied(self.a))
        self.assertIsNone(self.a.setup_move)
        self.assertEqual(self.a.stages["def"], 1)
        self.assertEqual(self.a.budget["standard"], 0)
        self.assertEqual(self.a.move_uses[ACID], 1)
        self.assertEqual(self.e.move_profile(self.a, "land")[0], 4)
        self.e.validate_state()

    def test_acid_real_physical_hit_keeps_secondary_effect_special_hurts_and_fall_is_typed(self):
        self.fixture()
        self.b.pos = (3, 2)
        self.prepare_acid()
        hp = self.a.hp
        self.turn(self.b)
        with patch.object(self.e, "d20", return_value=20):
            self.e.use_move(self.b, self.a, FLAME, set_damage=True)
        self.assertEqual(self.a.hp, hp)
        self.assertEqual(self.b.stages["spe"], 1)  # Immune damage is not a prevented hit.
        self.turn(self.b)
        with patch.object(self.e, "d20", return_value=10):
            self.e.use_move(self.b, self.a, WATER, set_damage=True)
        self.assertLess(self.a.hp, hp)
        hp = self.a.hp
        self.e.gm.observe_trainer_weight(self.a, 150, unit="lb", reason="actual observed falling body weight")
        fall = self.e.falling_damage(
            self.a, action_id="acid-observed-fall", meters=2, intentional=False,
            reason="actual two-metre fall", natural_sky=False,
            natural_sky_reason="observed actor has no natural Sky", fixed_damage=[6])
        self.assertEqual(fall["damage"], 0)
        self.assertEqual(self.a.hp, hp)
        self.e.validate_state()

    def test_acid_actual_paid_tiny_aperture_and_rough_slow_terrain_not_sealed_wall(self):
        self.fixture()
        self.e.grid.slow.add((2, 3))
        assert_rejected_unchanged(self.e, lambda: self.e.disengage(self.a, (2, 3), movement_mode="land"),
                                  reason_pattern="exceeds its one-metre movement allowance")
        edge = tuple(sorted(((2, 2), (3, 2))))
        self.e.grid.walls.add(edge)
        self.e.grid.slow.add((3, 2)); self.e.grid.rough.add((3, 2))
        WORLD.register_object(self.e, "liquid-door", location={"kind": "grid", "cell": (2, 2)},
                              reason="actual stationary wall surface")
        self.e.gm.observe_body_passage("liquid-door", edge, passage_id="tiny",
                                     height_m=0, width_m=0, reason="observed sealed wall")
        self.prepare_acid()
        assert_rejected_unchanged(self.e, lambda: self.e.disengage(self.a, (4, 2), movement_mode="land"),
                                  reason_pattern="exactly one metre")
        self.assertTrue(MODES.movement_blocked(self.e, self.a, (2, 2), (3, 2), altitude=0, underground=False))
        self.e.gm.observe_body_passage("liquid-door", edge, passage_id="tiny",
                                     height_m=0.000001, width_m=0.000001,
                                     reason="actual measured microscopic opening")
        self.assertTrue(MOVEMENT.ordinary_terrain(self.e, self.a, (3, 2), movement=True))
        self.assertFalse(MOVEMENT.ordinary_terrain(self.e, self.a, (3, 2)))
        self.assertFalse(MODES.movement_blocked(self.e, self.a, (2, 2), (3, 2), altitude=0, underground=False))
        self.assertTrue(self.e.disengage(self.a, (3, 2), movement_mode="land"))
        self.assertEqual((self.a.pos, self.a.budget["shift"]), ((3, 2), 0))
        self.assertIn(edge, self.e.grid.walls)
        self.assertIn((3, 2), self.e.grid.slow)
        self.e.grid.rough.add((4, 2))
        self.assertEqual(TERRAIN.accuracy_penalty(self.e, self.a, self.b), -2)
        self.turn()
        self.e.use_setup_move_on(self.a, self.a, ACID, self.e.everyone, setup_options={})
        self.assertTrue(MODES.movement_blocked(self.e, self.a, (3, 2), (2, 2), altitude=0, underground=False))
        self.e.validate_state()

    def test_acid_full_immersion_visibility_uses_current_body_and_survives_both_restores(self):
        self.fixture()
        self.prepare_acid()
        self.assertIsNone(INV.visual_block(self.e, self.a, observer=self.b))
        self.assertEqual(INV.accuracy_penalty(self.e, self.a, observer=self.b), 0)
        SETUP.observe_liquid(self.e, self.a, fully_submerged=False, liquid="oil",
                             reason="actual partial immersion")
        self.assertIsNone(INV.visual_block(self.e, self.a, observer=self.b))
        SETUP.observe_liquid(self.e, self.a, fully_submerged=True, liquid="oil",
                             reason="actual entire body submerged in oil")
        self.assertEqual(INV.visual_block(self.e, self.a, observer=self.b), "target_invisible")
        self.assertEqual(INV.accuracy_penalty(self.e, self.a, observer=self.b), 4)
        self.e.gm.snapshot("fully liquid")
        restored = CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        holder = next(row for row in restored.everyone if row.entity_id == self.a.entity_id)
        self.assertTrue(SETUP.hidden_in_liquid(restored, holder))
        self.assertTrue(self.e.disengage(self.a, (3, 2), movement_mode="land"))
        self.assertFalse(SETUP.hidden_in_liquid(self.e, self.a))
        self.e.gm.restore("fully liquid")
        self.assertTrue(SETUP.hidden_in_liquid(self.e, self.a))
        self.turn()
        self.e.use_setup_move_on(self.a, self.a, ACID, self.e.everyone, setup_options={})
        self.assertIsNone(INV.visual_block(self.e, self.a, observer=self.b))
        self.assertEqual(INV.accuracy_penalty(self.e, self.a, observer=self.b), 0)


    def test_acid_actual_power_herb_skips_liquid_state_and_consumes_only_once(self):
        self.fixture((ACID,))
        self.e.end_encounter(self.e.everyone, round_elapsed_seconds=0)
        self.a.spec.setdefault("items", {})["파워풀허브"] = 1
        result = self.e.use_item(self.a, "파워풀허브", self.a, duration_minutes=1,
                                 duration_reason="actual Extended Snack intake")
        self.assertEqual(result["status"], "digestion_buff_gained")
        self.assertEqual(self.a.spec["items"].get("파워풀허브", 0), 0)
        buff_id = self.a.buffs[-1]["id"]
        self.e.consume_food_buff(self.a, buff_id=buff_id, move_id=ACID)
        self.turn()
        with patch.object(self.e, "d20", side_effect=AssertionError("Self resolution has no AC")):
            self.e.use_setup_move_on(self.a, self.a, ACID, self.e.everyone, setup_options={})
        self.assertEqual(self.a.stages["def"], 1)
        self.assertFalse(SETUP.liquefied(self.a))
        self.assertIsNone(self.a.setup_move)
        self.assertEqual(self.a.budget["standard"], 0)
        self.assertEqual(self.a.move_uses[ACID], 1)
        self.assertFalse(any(row["id"] == buff_id for row in self.a.buffs))
        receipts = [row for row in self.a.spec["food_consumption_receipts"] if row["buff_id"] == buff_id]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["producer"], ACID)
        self.assertEqual(receipts[0]["benefit"], {"kind": "skip_setup", "move_id": ACID})
        self.assertFalse(SETUP.physical_immunity(self.a, "물리"))
        self.e.validate_state()


if __name__ == "__main__":
    unittest.main()

