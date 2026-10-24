"""Direct contracts for C11-116/117/118/120/121/122/124-133/135-137."""
from pathlib import Path
from unittest.mock import patch
import sys, unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine")]

from engine import Rules, Engine, Combatant
import actor_templates as T
import boss_transitions as B
import builder, frequency as F, state_fields as S, turn as TURN


class BossTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def setUp(self):
        self.e = Engine(self.r, 1901)
        self.a = Combatant(self.r, builder.build_trainer(
            self.r, "observer", 10, {key: 5 for key in S.STATS}, pos=(1, 1)))
        self.p = Combatant(self.r, builder.build_pokemon(self.r, "꼬렛", 10, pos=(2, 1)))
        self.p.side = "wild"
        self.e.everyone = self.e.gm.everyone = [self.a, self.p]

    def configure(self, *, count=3, effects=(), capture_level=None):
        self.p.stages["atk"] = 2
        return self.e.gm.set_encounter_template(
            self.p, kind="boss", total_bars=None, action_slots=None,
            action_basis={"pokemon_turns": count - 1, "combat_trainers": 1,
                          "focused_command_extra": 0},
            base_initiative=20, reason="selected boss encounter",
            transition_effects=effects, capture_level=capture_level,
            capture_choices=None if capture_level is None else {'strategy':'balanced','moves':[],'abilities':[]})

    def test_party_basis_derives_slots_bars_and_keeps_selected_baseline(self):
        view = self.configure(count=5)
        self.assertEqual([slot["initiative"] for slot in view["action_slots"]],
                         [20, 15, 10, 5, 25])
        self.assertEqual((view["action_count"], view["remaining_bars"]), (5, 5))
        self.assertEqual(view["baseline_stages"]["atk"], 2)
        self.assertEqual(view["boss_runtime"]["action_basis"]["result"], 5)
        self.assertEqual(view["boss_runtime"]["hp_bar_basis"], "one_per_action")
        self.assertEqual(view["transition_automation"], "native_boss_transition")
        validation = self.e.validate_state()
        self.assertTrue(validation["valid"], validation)

    def test_each_boss_slot_is_a_turn_for_eot_and_scene_x2_spacing(self):
        self.configure()
        eot, scene = "move/공격지령", "move/벌레의야단법석"
        for mid in (eot, scene):
            if mid not in self.p.moves:
                self.p.moves.append(mid)
        self.e.start_round([self.a, self.p])
        self.e.start_of_turn(self.p, initiative_count=20)
        self.assertTrue(F.move_allowed(self.e, self.p, eot)[0])
        F.consume_move(self.e, self.p, eot)
        F.consume_move(self.e, self.p, scene)
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.p, initiative_count=15)
        self.assertFalse(F.move_allowed(self.e, self.p, eot)[0])
        self.assertFalse(F.move_allowed(self.e, self.p, scene)[0])
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.p, initiative_count=10)
        self.assertTrue(F.move_allowed(self.e, self.p, eot)[0])
        self.assertTrue(F.move_allowed(self.e, self.p, scene)[0])
        F.consume_move(self.e, self.p, scene)
        self.assertFalse(F.move_allowed(self.e, self.p, scene)[0])
        self.assertEqual(T.projection(self.p)["frequency_ledger"][scene]["used"], 2)

    def test_bar_loss_scopes_hp_ignores_markers_carries_injury_and_runs_choices(self):
        # C11-127 refreshes a possessed Scene-frequency Move. Attack Order is
        # EOT, so it must not bypass the runtime's Scene-only validation.
        locked_move = "move/나비춤"
        if locked_move not in self.p.moves:
            self.p.moves.append(locked_move)
        effects = [
            {"when": "bar_lost", "kind": "vulnerable_until_damaged"},
            {"when": "bar_lost", "kind": "skip_next_turn"},
            {"when": "bar_lost", "kind": "raise_stage", "stage": "spa"},
            {"when": "bar_lost", "kind": "refresh_scene_move", "move_id": locked_move},
            {"when": "final_bar", "kind": "set_attack_stage_6"},
            {"when": "final_bar", "kind": "unlock_move", "move_id": "move/벌레의야단법석"},
        ]
        self.configure(count=4, effects=effects)
        self.p.move_uses[locked_move] = 1; self.p.spec["move_uses"] = {locked_move: 1}
        first_capacity = self.p.max_hp
        self.e.lose_hp(self.p, self.p.hp + 5, source="percentage/set HP",
                       loss_kind="hp_setting")
        view = T.projection(self.p)
        self.assertEqual((view["remaining_bars"], self.p.hp, self.p.injuries),
                         (3, first_capacity, 0))
        self.assertEqual(view["bar_transition_receipts"][-1]["discarded_overflow"], 5)
        self.assertEqual(self.p.move_uses[locked_move],0)
        self.assertEqual(self.p.stages["spa"], 1)
        B.start_turn(self.e, self.p, 20)
        self.assertFalse(B.action_permission(self.p))
        self.assertFalse(TURN.spend(self.e, self.p, "standard", "staggered turn"))
        # Ordinary HP loss carries its exact remainder and the half-bars injury
        # remains in force for all later bars; HP marker injuries never appear.
        current_capacity = self.p.max_hp
        self.e.lose_hp(self.p, self.p.hp + 5, source="ordinary HP loss")
        self.assertEqual(self.p.hp, self.p.max_hp - 5)
        self.assertEqual(self.p.injuries, 1)
        self.assertLess(self.p.max_hp, current_capacity)
        self.assertEqual(T.projection(self.p)["action_count"], 4)
        self.assertEqual(T.projection(self.p)["bar_transition_receipts"][-1]["carried_over"], 5)
        self.e.take_damage(self.p, 1)
        self.assertFalse(T.projection(self.p)["boss_runtime"]["vulnerable_until_damaged"])
        # Entering the final bar executes only the explicitly selected final effects.
        self.e.lose_hp(self.p, self.p.hp)
        self.assertEqual(T.projection(self.p)["remaining_bars"], 1)
        self.assertEqual(self.p.stages["atk"], 6)
        self.assertIn("move/벌레의야단법석", self.p.moves)

    def test_round_loss_and_slot_bound_conditions_have_one_actual_consumer(self):
        self.configure()
        self.assertTrue(self.e.apply_status(self.p, "화상", source="test/burn"))
        before = self.p.hp
        self.e.start_round([self.a, self.p])
        after_round = self.p.hp
        self.assertEqual(before - after_round, self.e.tick(self.p))
        # Re-entering the same boundary is replay-safe and each boss turn omits the tick.
        B.start_round(self.e, self.p)
        self.assertEqual(self.p.hp, after_round)
        self.e.start_of_turn(self.p, initiative_count=20); self.e.end_of_turn(self.p)
        self.assertEqual(self.p.hp, after_round)
        self.assertTrue(self.e.apply_status(self.p, "마비", source="test/paralysis"))
        binding = T.projection(self.p)["condition_bindings"]["마비"]
        self.assertEqual(binding["slot_id"], "boss-action-2")
        with patch.object(Engine, "d20", return_value=1):
            limit = self.e.start_of_turn(self.p, initiative_count=15)
        self.assertIsNotNone(limit)
        self.e.end_of_turn(self.p)
        with patch.object(Engine, "d20", return_value=1):
            limit = self.e.start_of_turn(self.p, initiative_count=10)
        self.assertIsNone(limit)
        self.assertTrue(self.e.validate_state()["valid"])

    def test_variants_preserve_actions_halve_evasion_and_penalize_one_damage_roll(self):
        self.configure()
        self.e.start_round([self.a, self.p])
        ordinary = self.p.evasion("물리")
        self.assertTrue(self.e.apply_status(self.p, "잠듦", source="test/sleep"))
        self.assertIn("졸음", self.p.conditions); self.assertNotIn("잠듦", self.p.conditions)
        self.assertEqual(self.p.evasion("물리"), ordinary // 2)
        self.e.start_of_turn(self.p, initiative_count=20)
        self.assertTrue(TURN.spend(self.e, self.p, "standard", "drowsy still acts"))
        with patch.object(Engine, "d20", return_value=1):
            self.e.end_of_turn(self.p)
        self.assertEqual(T.projection(self.p)["boss_runtime"]["damage_roll_penalty"], -10)
        baseline = self.e.roll_damage(self.p, self.a, self.r.move("move/몸통박치기"), set_damage=True)
        again = self.e.roll_damage(self.p, self.a, self.r.move("move/몸통박치기"), set_damage=True)
        self.assertEqual(again - baseline, 10)
        self.e.take_damage(self.p, 1)
        self.assertIn("졸음", self.p.conditions)
        self.e.cure_status(self.p, "잠듦")
        self.assertNotIn("졸음", self.p.conditions)

    def test_disabled_flinch_and_capture_lifetime_are_bounded(self):
        self.configure(count=2, capture_level=5)
        first, second = "move/공격지령", "move/벌레의야단법석"
        for mid in (first, second):
            if mid not in self.p.moves:self.p.moves.append(mid)
        self.e.start_round([self.a, self.p])
        self.assertTrue(self.e.apply_status(self.p, "사슬묶기", parameters={"move_id": first}, source="test/disabled"))
        with self.assertRaises(ValueError):
            self.e.apply_status(self.p, "사슬묶기", parameters={"move_id": second}, source="test/disabled-2")
        self.e.start_of_turn(self.p, initiative_count=20)
        self.assertTrue(self.e.apply_status(self.p, "풀죽음", source="test/flinch"))
        self.assertFalse(self.e.apply_status(self.p, "풀죽음", source="test/flinch-2"))
        self.e.end_of_turn(self.p)
        self.a.spec["items"] = {"몬스터볼": 2}
        before_items = dict(self.a.spec["items"])
        self.assertFalse(self.e.throw_ball(self.a, self.p, fixed_accuracy=20, fixed_capture=20))
        self.assertEqual(self.a.spec["items"], before_items)
        self.e.lose_hp(self.p, self.p.hp)
        self.assertFalse(T.projection(self.p)["capture_immune"])
        self.e.start_of_turn(self.a, initiative_count=10)
        self.assertTrue(self.e.throw_ball(self.a, self.p, fixed_accuracy=20, fixed_capture=20),
                        self.e.log_lines[-20:])
        self.e.end_of_turn(self.a)
        self.assertTrue(self.p.captured)
        self.assertEqual(self.p.level, 5)
        self.assertNotIn("encounter_template", self.p.spec)
        self.assertEqual(self.p.spec["retired_encounter_templates"][-1]["source_id"], "C11-137")
        validation = self.e.validate_state()
        self.assertTrue(validation["valid"], validation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
