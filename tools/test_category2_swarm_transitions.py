"""Direct native contracts for C11-086 through C11-091."""
from pathlib import Path
from unittest.mock import patch
import os
import sys
import unittest


HERE = Path(__file__).resolve()
STAGE = HERE.parents[1]
ROOT = STAGE if (STAGE / "data").exists() else Path(os.environ["PTK_EXPERIMENT_ROOT"])
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
import actor_templates as TEMPLATES
import frequency as FREQ
import swarm_transitions as SWARM
import turn as TURN
import condition_recovery as RECOVERY


AT_WILL = "move/벌레먹기"
EOT = "move/공격지령"
SCENE = "move/나비춤"
DAILY = "move/회복지령"
SCENE_SWIFT = "move/꿰뚫어보기"
AT_WILL_SWIFT = "move/몸통박치기"


class SwarmTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")

    def setUp(self):
        self.e = Engine(self.r, seed=1186)
        stats = {key: 20 for key in ("hp", "atk", "def", "spa", "spd", "spe")}
        self.t = Combatant(self.r, build_trainer(self.r, "observer", 20, stats,
                                                  pos=(1, 1), side="party"))
        self.p = Combatant(self.r, build_pokemon(self.r, "뿔충이", 20,
            moves=[AT_WILL, EOT, SCENE, DAILY, SCENE_SWIFT, AT_WILL_SWIFT], abilities=[],
            pos=(2, 1), side="wild"))
        self.e.gm.add_combatant(self.t)
        self.e.gm.add_combatant(self.p)

    def configure(self, bars=3):
        return self.e.gm.set_encounter_template(self.p, kind="swarm", total_bars=bars,
            action_slots=[{"id": "native", "initiative": 20}],
            reason="selected Chapter 11 swarm", member_count_or_band="25_to_40")

    def open_turn(self, bars=3, condition=None):
        self.configure(bars)
        if condition:
            self.p.conditions.add(condition)
        self.e.start_round(self.e.everyone)
        if condition:
            with patch.object(RECOVERY, "saving_check", return_value={"passed": False}):
                self.e.start_of_turn(self.p, initiative_count=20)
        else:
            self.e.start_of_turn(self.p, initiative_count=20)
        return self.p.spec["encounter_template"]

    def spend_move(self, move_id):
        allowed, reason = FREQ.move_allowed(self.e, self.p, move_id)
        if not allowed:
            return False, reason
        move = self.r.move(move_id)
        kind = TURN.action_kind_of_move(self.e, self.p, move, self.r.move_mech(move_id)[0])
        if not TURN.spend(self.e, self.p, kind, move["name"], _native_move=move):
            return False, "action rejected"
        FREQ.consume_move(self.e, self.p, move_id)
        return True, ""

    def test_c11_086_actual_damage_depletes_one_bar_without_injuries_or_new_identity(self):
        view = self.configure(3)
        identity = self.p.entity_id
        capacity = self.p.max_hp
        self.e.take_damage(self.p, capacity + 40)
        row = self.p.spec["encounter_template"]
        self.assertEqual((row["hp_bars"]["spent"], row["multiplier"], self.p.hp), (1, 2, capacity))
        self.assertEqual((self.p.injuries, self.p.entity_id, len(self.e.everyone)), (0, identity, 2))
        self.assertEqual(row["bar_transition_receipts"][-1]["remaining_bars"], 2)
        self.e.take_damage(self.p, capacity + 1)
        self.assertEqual((row["hp_bars"]["spent"], row["multiplier"], self.p.hp), (2, 1, capacity))
        self.e.take_damage(self.p, capacity + 1)
        self.assertEqual((row["hp_bars"]["spent"], row["multiplier"]), (3, 0))
        self.assertTrue(self.p.fainted)

    def test_c11_087_and_089_turn_points_free_first_action_and_frequency_costs(self):
        row = self.open_turn(5)
        self.assertEqual(row["swarm_points"], 5)
        self.assertEqual(SWARM.standard_cost(self.e, self.p, self.r.move(AT_WILL)), (1, "at_will"))
        self.assertEqual(SWARM.standard_cost(self.e, self.p, self.r.move(EOT)), (2, "every_other_turn"))
        self.assertEqual(SWARM.standard_cost(self.e, self.p, self.r.move(SCENE)), (3, "scene"))
        self.assertEqual(SWARM.standard_cost(self.e, self.p, self.r.move(DAILY)), (4, "daily"))
        self.assertTrue(self.spend_move(DAILY)[0])
        self.assertEqual(row["swarm_points"], 5)
        self.assertTrue(self.spend_move(DAILY)[0])
        self.assertEqual(row["swarm_points"], 1)
        allowed, reason = FREQ.move_allowed(self.e, self.p, DAILY)
        self.assertFalse(allowed)
        self.assertIn("포인트", reason)
        self.assertEqual(self.p.move_uses[DAILY], 2)

    def test_c11_088_additional_actions_descend_by_five_and_repeat_at_zero(self):
        row = self.open_turn(5)
        for _ in range(6):
            self.assertTrue(self.spend_move(AT_WILL)[0])
        receipt = row["round_trigger_receipts"][row["own_turn_key"]]
        self.assertEqual([x["initiative"] for x in receipt["actions"]], [20, 15, 10, 5, 0, 0])
        self.assertEqual([x["point_cost"] for x in receipt["actions"]], [0, 1, 1, 1, 1, 1])
        self.assertEqual(row["swarm_points"], 0)
        self.assertFalse(self.spend_move(AT_WILL)[0])

    def test_c11_090_scene_swift_cap_and_at_will_swift_once_per_swarm_action(self):
        row = self.open_turn(3)
        for _ in range(3):
            self.assertTrue(self.spend_move(SCENE_SWIFT)[0])
        self.assertFalse(self.spend_move(SCENE_SWIFT)[0])
        quick = self.r.move(AT_WILL_SWIFT)
        self.p.registry.append({"type": "action_type_change", "moves": quick["name"], "to": "swift"})
        self.assertTrue(self.spend_move(AT_WILL_SWIFT)[0])
        self.assertFalse(self.spend_move(AT_WILL_SWIFT)[0])
        self.assertTrue(self.spend_move(EOT)[0])
        self.assertTrue(self.spend_move(AT_WILL_SWIFT)[0])
        self.assertEqual(row["frequency_ledger"][AT_WILL_SWIFT]["action_index"], 1)

    def test_c11_091_incapacitation_costs_one_point_but_preserves_one_action(self):
        row = self.open_turn(3, "잠듦")
        turn = row["swarm_turn"]
        receipt = row["round_trigger_receipts"][row["own_turn_key"]]
        self.assertEqual((row["swarm_points"], receipt["condition_point_cost"]), (2, 1))
        self.assertTrue(turn["minimum_action"])
        move = self.r.move(AT_WILL)
        self.assertTrue(TURN.spend(self.e, self.p, "standard", move["name"], _native_move=move))
        self.assertTrue(turn["minimum_action_used"])
        self.assertFalse(TURN.spend(self.e, self.p, "standard", move["name"], _native_move=move))


if __name__ == "__main__":
    unittest.main(verbosity=2)
