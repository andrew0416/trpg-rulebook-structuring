"""Deep Cold shares a foe's Scene quota, with explicit current legacy adoption."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
import test_category2_class_actor_state_reactions as F
from builder import build_pokemon, build_trainer
from engine import Combatant, Rules
import class_actor_state_reactions as C
import frequency as Q
import gm_state as GM
import state_codec as CODEC
import world_entities as W


class DeepColdTargetSceneTests(unittest.TestCase):
    setUpClass = classmethod(F.ClassActorStateReactionTests.setUpClass.__func__)
    fixture = F.ClassActorStateReactionTests.fixture
    start = F.ClassActorStateReactionTests.start
    hit = F.ClassActorStateReactionTests.hit
    pending_one = F.ClassActorStateReactionTests.pending_one

    def pair(self):
        e, a, p, q = self.fixture(feats=[C.DEEP_COLD], partner_types=("얼음",))
        b = Combatant(self.rules, build_trainer(self.rules, "Second Owner", 30,
            {"hp": 40, "atk": 12, "def": 12, "spa": 12, "spd": 12, "spe": 12},
            moves=[], abilities=[], skills={"명령": "숙련"}, extra={"feats": [C.DEEP_COLD], "edges": []}))
        r = Combatant(self.rules, build_pokemon(self.rules, "이상해씨", 20,
            name="Second Partner", moves=["냉동빔"], abilities=[],
            extra={"trainer_id": b.entity_id, "trainer": b.name, "types": ["얼음"]}))
        e.gm.add_combatant(b, pos=(0, 2), side="party", reason="actual second feature owner")
        e.gm.add_combatant(r, pos=(1, 2), side="party", reason="actual second owned Ice attacker")
        return e, a, p, q, b, r

    def target(self, e, name, pos):
        q = Combatant(self.rules, build_pokemon(self.rules, "꼬부기", 20,
            name=name, moves=["몸통박치기"], abilities=[]))
        e.gm.add_combatant(q, pos=pos, side="foe", reason="actual distinct target quota")
        return q

    def world(self, e):
        return (deepcopy(CODEC.dump_engine(e)), e.rng.getstate(), deepcopy(e.rulings.log))

    def legacy(self, e, owner, pokemon, target):
        """Project a real completed use to the exact pre-repair owner-only schema."""
        self.hit(e, pokemon, target, "냉동빔")
        event = self.pending_one(e, owner, C.DEEP_COLD)
        e.resolve_class_actor_state_reaction(owner, event["id"], use=True)
        key = C._target_key(e, owner, target, C.DEEP_COLD)
        row = Q.state(target)["activations"].pop(key)
        Q.state(owner)["activations"][key] = row
        actual = next(item for item in owner.spec[C.STATE]["events"] if item["id"] == event["id"])
        actual["result"].pop("target_scene_quota")
        target.spec.pop(C.DEEP_QUOTA)
        return key, deepcopy(actual), deepcopy(row)

    def test_two_actual_owners_share_pending_target_cap_and_keep_daily_payments_separate(self):
        e, a, p, q, b, r = self.pair()
        e.gm.observe_loyalty(p, 6, reason="actual paid command obedience")
        self.start(e, p)
        hp = q.hp
        with patch.object(e, "d20", return_value=10):
            dealt = e.use_move(p, q, "move/냉동빔", set_damage=True)
        self.assertEqual((q.hp, p.budget["standard"], p.move_uses["move/냉동빔"]), (hp-dealt, 0, 1))
        self.assertGreater(dealt, 0)
        first = self.pending_one(e, a, C.DEEP_COLD)
        self.hit(e, r, q, "냉동빔")
        second = self.pending_one(e, b, C.DEEP_COLD)
        self.assertEqual(first["target_scene_quota"]["status"], "available")
        e.resolve_class_actor_state_reaction(a, first["id"], use=False)
        self.assertNotIn(C.DEEP_COLD, Q.state(a)["activations"])
        self.assertEqual(C.deep_cold_target_quota(e, q)["status"], "available")
        self.hit(e, p, q, "냉동빔")
        retry = self.pending_one(e, a, C.DEEP_COLD)
        free_before = deepcopy(getattr(b, "_action_history", []))
        result = e.resolve_class_actor_state_reaction(b, second["id"], use=True)
        self.assertTrue(result["used"])
        self.assertEqual(len(b._action_history), len(free_before)+1)
        self.assertEqual(Q.state(b)["activations"][C.DEEP_COLD]["used"], 1)
        self.assertNotIn(C.DEEP_COLD, Q.state(a)["activations"])
        key = C._target_key(e, a, q, C.DEEP_COLD)
        self.assertNotIn(key, Q.state(a)["activations"])
        self.assertNotIn(key, Q.state(b)["activations"])
        self.assertEqual(Q.state(q)["activations"][key], {"kind": "scene", "period": 0, "used": 1})
        receipt = result["target_scene_quota"]
        self.assertEqual((receipt["target_id"], receipt["feature_owner_id"], receipt["key"]),
                         (q.entity_id, b.entity_id, key))
        self.assertIn(receipt, q.spec[C.DEEP_QUOTA]["uses"])
        closed = next(row for row in a.spec[C.STATE]["events"] if row["id"] == retry["id"])
        self.assertEqual((closed["status"], closed["result"]["reason"]), ("superseded", "target_scene_limit_spent"))
        cold = CODEC.load_engine(Rules(ROOT, ruleset="all"),
            json.loads(json.dumps(CODEC.dump_engine(e), ensure_ascii=False)))
        restored_target = W.actor_index(cold)[q.entity_id]
        self.assertEqual(restored_target.spec[C.DEEP_QUOTA]["uses"], [receipt])
        self.assertEqual(C.deep_cold_target_quota(cold, restored_target)["status"], "spent")
        before = self.world(e)
        with self.assertRaisesRegex(ValueError, "pending"):
            e.resolve_class_actor_state_reaction(a, retry["id"], use=True)
        self.assertEqual(self.world(e), before)
        self.hit(e, p, q, "냉동빔")
        self.assertFalse(e.pending_class_actor_state_reactions(a))
        for i in range(2):
            other = self.target(e, "Other foe " + str(i), (6+i, 0))
            self.hit(e, r, other, "냉동빔")
            offered = self.pending_one(e, b, C.DEEP_COLD)
            e.resolve_class_actor_state_reaction(b, offered["id"], use=True)
        unused = self.target(e, "Daily boundary foe", (8, 0))
        self.hit(e, r, unused, "냉동빔")
        self.assertFalse(e.pending_class_actor_state_reactions(b))
        self.assertEqual(Q.state(b)["activations"][C.DEEP_COLD]["used"], 3)
        self.hit(e, p, unused, "냉동빔")
        offered = self.pending_one(e, a, C.DEEP_COLD)
        e.resolve_class_actor_state_reaction(a, offered["id"], use=True)
        self.assertEqual(Q.state(a)["activations"][C.DEEP_COLD]["used"], 1)
        self.assertTrue(e.validate_state()["valid"])

    def test_partial_local_scene_offfield_legacy_periods_need_current_adoption_then_renew(self):
        for boundary in ("target", "owner"):
            with self.subTest(boundary=boundary):
                e, a, p, q, b, r = self.pair()
                self.start(e, p)
                key, old_event, old_row = self.legacy(e, a, p, q)
                e.end_of_turn(p)
                # The actual public local Scene boundary intentionally excludes
                # either the old feature owner or the target's quota calendar.
                e.end_scene([q] if boundary == "target" else [a], round_elapsed_seconds=10)
                a.on_field = False  # current fixture body fact, still a registered world owner
                self.assertIs(W.actor_index(e)[a.entity_id], a)
                self.assertEqual(Q.state(a)["activations"][key], old_row)
                self.assertEqual(old_row["period"] == Q.state(a)["scene"], boundary == "target")
                query = C.deep_cold_target_quota(e, q)
                self.assertEqual(query["status"], "observation_required")
                e.begin_encounter([b, r, q])
                e.start_round([b, r, q])
                self.start(e, r)
                hp = q.hp
                self.hit(e, r, q, "냉동빔")
                self.assertLess(q.hp, hp)
                pending = self.pending_one(e, b, C.DEEP_COLD)
                self.assertEqual(pending["target_scene_quota"]["status"], "observation_required")
                self.assertNotIn("target_scene_quota", b.spec[C.STATE]["events"][-1])
                before = self.world(e)
                with self.assertRaisesRegex(ValueError, "current scoped GM observation"):
                    e.resolve_class_actor_state_reaction(b, pending["id"], use=True)
                self.assertEqual(self.world(e), before)
                scope = pending["target_scene_quota"]["scope"]
                receipt = C.observe_deep_cold_target_quota(e, q, used=0, scope=scope,
                    reason="GM observed this target has not been affected in its current local Scene")
                self.assertEqual(e.rulings.log[-1]["after"], receipt)
                self.assertEqual(e.rulings.log[-1]["reason"], receipt["reason"])
                self.assertEqual(C.deep_cold_target_quota(e, q)["status"], "available")
                before = self.world(e)
                with self.assertRaisesRegex(ValueError, "fresh scoped"):
                    C.observe_deep_cold_target_quota(e, q, used=0, scope=scope, reason="duplicate observation")
                self.assertEqual(self.world(e), before)
                e.resolve_class_actor_state_reaction(b, pending["id"], use=True)
                self.assertEqual(Q.state(a)["activations"][key], old_row)
                self.assertEqual(a.spec[C.STATE]["events"][0], old_event)
                self.assertEqual(C.deep_cold_target_quota(e, q)["status"], "spent")
                e.end_of_turn(r)
                e.end_scene([q], round_elapsed_seconds=10)
                self.assertEqual(C.deep_cold_target_quota(e, q)["status"], "available")
                self.assertEqual(a.spec[C.STATE]["events"][0], old_event)
                self.assertEqual(Q.state(a)["activations"][key], old_row)
                self.assertEqual(q.spec[C.DEEP_QUOTA]["adoptions"], [receipt])
                self.assertTrue(e.validate_state()["valid"])

    def test_new_unbound_legacy_evidence_after_observed_zero_can_be_adopted_without_clearing_spend(self):
        e, a, p, q, b, r = self.pair()
        self.start(e, p)
        key, old_event, old_row = self.legacy(e, a, p, q)
        first = C.deep_cold_target_quota(e, q)
        C.observe_deep_cold_target_quota(e, q, used=0, scope=first["scope"], reason="observed current target available")
        # Exact old producer leaf: a newly recovered surviving owner-only row,
        # using its actual native frequency schema, not a fabricated old event.
        Q.consume_activation(b, key, {"kind": "scene", "uses": 1}, engine=e)
        fresh = C.deep_cold_target_quota(e, q)
        self.assertEqual(fresh["status"], "observation_required")
        self.assertNotEqual(fresh["scope"], first["scope"])
        before = self.world(e)
        with self.assertRaisesRegex(ValueError, "fresh scoped"):
            C.observe_deep_cold_target_quota(e, q, used=0, scope=first["scope"], reason="stale before recovered row")
        self.assertEqual(self.world(e), before)
        self.hit(e, p, q, "냉동빔")
        pending = self.pending_one(e, a, C.DEEP_COLD)
        e.resolve_class_actor_state_reaction(a, pending["id"], use=False)
        self.assertEqual(C.deep_cold_target_quota(e, q)["status"], "observation_required")
        C.observe_deep_cold_target_quota(e, q, used=0, scope=fresh["scope"], reason="current observation covers newly recovered row")
        self.assertEqual(len(q.spec[C.DEEP_QUOTA]["adoptions"]), 2)
        self.hit(e, r, q, "냉동빔")
        pending = self.pending_one(e, b, C.DEEP_COLD)
        e.resolve_class_actor_state_reaction(b, pending["id"], use=True)
        spent = C.deep_cold_target_quota(e, q)
        self.assertEqual(spent["status"], "spent")
        before = self.world(e)
        with self.assertRaisesRegex(ValueError, "fresh scoped"):
            C.observe_deep_cold_target_quota(e, q, used=0, scope=spent["scope"], reason="cannot clear known native spend")
        self.assertEqual(self.world(e), before)
        self.assertEqual(a.spec[C.STATE]["events"][0], old_event)
        self.assertEqual(Q.state(a)["activations"][key], old_row)

    def test_observed_spent_closes_both_pending_atomically_and_survives_fresh_rules_json_and_gm(self):
        e, a, p, q, b, r = self.pair()
        self.start(e, p)
        key, old_event, old_row = self.legacy(e, a, p, q)
        self.hit(e, p, q, "냉동빔")
        self.hit(e, r, q, "냉동빔")
        self.assertTrue(e.pending_class_actor_state_reactions(a))
        self.assertTrue(e.pending_class_actor_state_reactions(b))
        query = C.deep_cold_target_quota(e, q)
        before = self.world(e)
        original_record = GM.GMState._rec
        def reject_after_journal(gm, *args, **kwargs):
            original_record(gm, *args, **kwargs)
            raise RuntimeError("observation journal failure")
        with patch.object(GM.GMState, "_rec", reject_after_journal), self.assertRaisesRegex(RuntimeError, "journal failure"):
            C.observe_deep_cold_target_quota(e, q, used=1, scope=query["scope"], reason="current GM observation")
        self.assertEqual(self.world(e), before)
        for invalid in (True, -1, 2, 0.0):
            with self.assertRaisesRegex(ValueError, "integer 0 or 1"):
                C.observe_deep_cold_target_quota(e, q, used=invalid, scope=query["scope"], reason="invalid value")
        with self.assertRaisesRegex(ValueError, "reason"):
            C.observe_deep_cold_target_quota(e, q, used=1, scope=query["scope"], reason=" ")
        impostor = Combatant(self.rules, deepcopy(q.spec))
        with self.assertRaisesRegex(ValueError, "actual registered"):
            C.observe_deep_cold_target_quota(e, impostor, used=1, scope=query["scope"], reason="wrong object")
        self.assertEqual(self.world(e), before)
        receipt = C.observe_deep_cold_target_quota(e, q, used=1, scope=query["scope"],
            reason="GM observed this target already affected in its current Scene")
        self.assertFalse(e.pending_class_actor_state_reactions(a))
        self.assertFalse(e.pending_class_actor_state_reactions(b))
        self.assertNotIn(C.DEEP_COLD, Q.state(b)["activations"])
        self.assertEqual(Q.state(a)["activations"][C.DEEP_COLD]["used"], 1)
        self.assertEqual(a.spec[C.STATE]["events"][0], old_event)
        self.assertEqual(Q.state(a)["activations"][key], old_row)
        e.gm.snapshot("observed-target-quota")
        e.end_of_turn(p)
        e.end_scene([q], round_elapsed_seconds=10)
        self.assertEqual(C.deep_cold_target_quota(e, q)["status"], "available")
        e.gm.restore("observed-target-quota", reason="restore actual current quota snapshot")
        self.assertEqual(C.deep_cold_target_quota(e, q)["status"], "spent")
        payload = json.loads(json.dumps(CODEC.dump_engine(e), ensure_ascii=False))
        restored = CODEC.load_engine(Rules(ROOT, ruleset="all"), payload)
        index = W.actor_index(restored)
        actual_target = index[q.entity_id]
        self.assertEqual(C.deep_cold_target_quota(restored, actual_target)["status"], "spent")
        self.assertEqual(actual_target.spec[C.DEEP_QUOTA]["adoptions"], [receipt])
        self.assertEqual(index[a.entity_id].spec[C.STATE]["events"][0], old_event)
        self.assertEqual(Q.state(index[a.entity_id])["activations"][key], old_row)
        self.assertIn(receipt, [entry["after"] for entry in restored.rulings.log])
        before = self.world(restored)
        with self.assertRaisesRegex(ValueError, "fresh scoped"):
            C.observe_deep_cold_target_quota(restored, actual_target, used=0,
                scope=C.deep_cold_target_quota(restored, actual_target)["scope"], reason="cannot erase observed spend")
        self.assertEqual(self.world(restored), before)
        self.assertTrue(restored.validate_state()["valid"])


if __name__ == "__main__":
    unittest.main()
