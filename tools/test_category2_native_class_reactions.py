"""Two native source bindings over the established attack-reaction consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
import test_category2_class_actor_state_reactions as BASELINE
from builder import build_pokemon
from engine import Combatant, Rules
import class_actor_state_reactions as R
import frequency as F
import state_codec as CODEC
import survivalist_features as SURVIVALIST
import world_entities as WORLD


class NativeReactionTests(unittest.TestCase):
    fixture = BASELINE.ClassActorStateReactionTests.fixture
    start = BASELINE.ClassActorStateReactionTests.start
    hit = BASELINE.ClassActorStateReactionTests.hit
    pending_one = BASELINE.ClassActorStateReactionTests.pending_one
    snapshot = BASELINE.ClassActorStateReactionTests.snapshot

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="all")

    def assert_native(self, row, source):
        policy = R.native_policy(self.rules)["sources"][source]
        self.assertEqual(row["native_clause_id"], R.NATIVE_CLAUSE_BY_RULE[source])
        self.assertEqual(row["native_source_sha256"], policy["excerpt_sha256"])
        self.assertEqual(row["acquisition_source"], source)
        self.assertEqual(row["clause_id"], R.CLAUSE_BY_RULE[source])

    def pending_hit(self, source):
        attacking = source == R.DEEP_COLD
        e, owner, pokemon, enemy = self.fixture(
            feats=[source], partner_types=("얼음",) if attacking else ("드래곤",))
        self.start(e, pokemon if attacking else enemy)
        self.hit(e, pokemon if attacking else enemy, enemy if attacking else pokemon,
                 "냉동빔" if attacking else "몸통박치기", critical=not attacking)
        return e, owner, pokemon, enemy, self.pending_one(e, owner, source)

    def test_exact_two_hash_pinned_sources_use_existing_independent_contracts(self):
        policy = R.native_policy(self.rules)
        self.assertEqual(set(policy["sources"]), {R.THIS_WILL_NOT_STAND, R.DEEP_COLD})
        for source, row in policy["sources"].items():
            path = ROOT / row["file"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["file_sha256"])
            excerpt = "\n".join(path.read_text(encoding="utf-8").splitlines()[row["start"] - 1:row["end"]])
            self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(), row["excerpt_sha256"])
            self.assertEqual(row["source_text"], excerpt)
            self.assertEqual(row["behavior_clause_id"], R.CLAUSE_BY_RULE[source])
        self.assertNotIn(R.ENDURING_BLOOM, policy["sources"])

    def test_actual_critical_and_massive_damage_produce_native_stage_receipts(self):
        source = R.THIS_WILL_NOT_STAND
        for critical in (True, False):
            e, owner, pokemon, enemy = self.fixture(feats=[source], partner_types=("드래곤",))
            self.start(e, enemy)
            if not critical:
                enemy.stats["atk"] = enemy.spec["stats"]["atk"] = 100
            self.hit(e, enemy, pokemon, "몸통박치기", critical=critical)
            row = self.pending_one(e, owner, source)
            self.assert_native(row, source)
            self.assertTrue(row["critical"] if critical else row["massive"])
            result = e.resolve_class_actor_state_reaction(owner, row["id"], use=True)
            self.assert_native(result, source)
            self.assertEqual(tuple(pokemon.stages[s] for s in ("atk", "spa", "spe")), (1, 1, 1))
            if critical:
                self.hit(e, enemy, pokemon, "몸통박치기", critical=True)
                self.assertFalse(e.pending_class_actor_state_reactions(owner))

    def test_deep_cold_three_daily_uses_and_one_use_per_actual_target(self):
        source = R.DEEP_COLD
        e, owner, pokemon, first = self.fixture(feats=[source], partner_types=("얼음",))
        enemies = [first]
        for i in range(3):
            other = Combatant(self.rules, build_pokemon(self.rules, "꼬부기", 20,
                              name="Enemy " + str(i), moves=[], abilities=[]))
            e.gm.add_combatant(other, pos=(4 + i, 0), side="foe", reason="distinct actual reaction target")
            enemies.append(other)
        self.start(e, pokemon)
        for target in enemies[:3]:
            self.hit(e, pokemon, target, "냉동빔")
            event = self.pending_one(e, owner, source)
            self.assert_native(event, source)
            e.resolve_class_actor_state_reaction(owner, event["id"], use=True)
            self.assertEqual(tuple(target.stages[s] for s in ("atk", "spa", "spe")), (-1, -1, -1))
        self.assertEqual(F.state(owner)["activations"][source]["used"], 3)
        for target in (first, enemies[3]):
            self.hit(e, pokemon, target, "냉동빔")
            self.assertFalse(e.pending_class_actor_state_reactions(owner))
        e.end_encounter()
        e.advance_time(86400)
        # Elapsed time and the campaign's declared daily boundary are distinct
        # native authorities. Merely leaving combat does not refresh features.
        self.assertFalse(F.activation_allowed(owner, source, {"kind": "daily", "uses": 3}, engine=e))
        F.new_day(owner)
        e.begin_encounter(e.everyone)
        e.start_round(e.everyone)
        self.start(e, pokemon)
        self.hit(e, pokemon, enemies[3], "냉동빔")
        event = self.pending_one(e, owner, source)
        e.resolve_class_actor_state_reaction(owner, event["id"], use=True)
        self.assertEqual(F.state(owner)["activations"][source]["used"], 1)

    def test_unowned_sources_and_wrong_types_do_not_offer_native_reactions(self):
        e, owner, pokemon, enemy = self.fixture(feats=[], partner_types=("얼음",))
        self.start(e, pokemon)
        self.hit(e, pokemon, enemy, "냉동빔")
        self.assertFalse(e.pending_class_actor_state_reactions(owner))
        e2, owner2, pokemon2, enemy2 = self.fixture(feats=[R.THIS_WILL_NOT_STAND], partner_types=("노말",))
        self.start(e2, enemy2)
        self.hit(e2, enemy2, pokemon2, "몸통박치기", critical=True)
        self.assertFalse(e2.pending_class_actor_state_reactions(owner2))

    def test_pending_source_withdrawal_and_owner_change_fail_without_consumption(self):
        for changed in ("source", "owner"):
            e, owner, pokemon, enemy, event = self.pending_hit(R.DEEP_COLD)
            if changed == "source":
                owner.spec["feats"] = []
            else:
                pokemon.spec.pop("trainer_id")
                pokemon.spec.pop("trainer", None)
            before = self.snapshot(e, owner, pokemon, enemy)
            with self.assertRaisesRegex(ValueError, "acquisition ended|ownership changed"):
                e.resolve_class_actor_state_reaction(owner, event["id"], use=True)
            self.assertEqual(before, self.snapshot(e, owner, pokemon, enemy))
            e.resolve_class_actor_state_reaction(owner, event["id"], use=False)
            self.assertNotIn(R.DEEP_COLD, F.state(owner)["activations"])

    def test_pending_json_and_gm_restore_keep_source_and_resolve_once(self):
        for source in R.NATIVE_CLAUSE_BY_RULE:
            e, owner, pokemon, enemy, event = self.pending_hit(source)
            payload = CODEC.dump_engine(e)
            e.gm.snapshot("pending native reaction")
            e.resolve_class_actor_state_reaction(owner, event["id"], use=False)
            e.gm.restore("pending native reaction", reason="restore preserved actual hit decision")
            loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(payload, ensure_ascii=False)))
            for world in (e, loaded):
                actual_owner = WORLD.actor_index(world)[owner.entity_id]
                restored = world.pending_class_actor_state_reactions(actual_owner)
                self.assertEqual(len(restored), 1)
                self.assert_native(restored[0], source)
                result = world.resolve_class_actor_state_reaction(actual_owner, event["id"], use=True)
                self.assert_native(result, source)
                with self.assertRaisesRegex(ValueError, "pending"):
                    world.resolve_class_actor_state_reaction(actual_owner, event["id"], use=True)

    def test_applied_restore_and_source_withdrawal_keep_frozen_lifetime_and_spent_quota(self):
        source = R.DEEP_COLD
        e, owner, pokemon, enemy, event = self.pending_hit(source)
        e.resolve_class_actor_state_reaction(owner, event["id"], use=True)
        owner.spec["feats"] = []
        payload = CODEC.dump_engine(e)
        e.gm.snapshot("applied native reaction")
        e.change_stage(enemy, "atk", 1)
        e.gm.restore("applied native reaction", reason="restore actual effect and quota")
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(payload, ensure_ascii=False)))
        for world in (e, loaded):
            actors = WORLD.actor_index(world)
            actual_owner, actual_pokemon, actual_enemy = (actors[x.entity_id] for x in (owner, pokemon, enemy))
            self.assertIn("얼음", actual_enemy.conditions)
            self.assertEqual(actual_enemy.stages["atk"], -1)
            self.assertEqual(F.state(actual_owner)["activations"][source]["used"], 1)
            self.assert_native(actual_owner.spec[R.STATE]["events"][-1]["result"], source)
            world.end_of_turn(actual_pokemon)
            world.end_round()
            world.start_round(world.everyone)
            world.start_of_turn(actual_owner, initiative_count=20)
            self.assertIn("얼음", actual_enemy.conditions)
            world.end_of_turn(actual_owner)
            world.start_of_turn(actual_enemy, initiative_count=10)
            self.assertNotIn("얼음", actual_enemy.conditions)
            self.assertEqual(actual_enemy.stages["atk"], -1)

    def test_late_quota_failure_rolls_back_effect_action_rng_and_pending_event(self):
        e, owner, pokemon, enemy, event = self.pending_hit(R.DEEP_COLD)
        before = CODEC.dump_engine(e)
        aliases = owner.spec, owner.spec[R.STATE], enemy.stages, enemy.conditions
        real = F.consume_activation
        def fail_after_consuming(actor, key, declaration, **kwargs):
            value = real(actor, key, declaration, **kwargs)
            if key != R.DEEP_COLD:
                raise ValueError("late target quota failure")
            return value
        with patch.object(F, "consume_activation", fail_after_consuming):
            with self.assertRaisesRegex(ValueError, "late target quota"):
                e.resolve_class_actor_state_reaction(owner, event["id"], use=True)
        self.assertEqual(CODEC.dump_engine(e), before)
        for actual, alias in zip((owner.spec, owner.spec[R.STATE], enemy.stages, enemy.conditions), aliases):
            self.assertIs(actual, alias)

    def test_both_world_validators_and_both_restores_preserve_survivalist_hook(self):
        e, owner, pokemon, enemy = self.fixture(feats=[R.DEEP_COLD], partner_types=("얼음",))
        e.end_encounter()
        owner.spec["classes"] = [SURVIVALIST.SURVIVALIST]
        owner.spec["skills"]["생존"] = 6
        e.survivalist_activity(owner, "select_csv_terrains", clause_id=SURVIVALIST.CSV_CLAUSES[0],
                              terrains=["forest"], minutes=2, reason="existing daily action before encounter")
        e.survivalist_activity(owner, "observe_environment", terrains=["forest"], light="normal",
                              reason="actual forest observation")
        e.begin_encounter(e.everyone)
        e.start_round(e.everyone)
        self.start(e, pokemon)
        self.hit(e, pokemon, enemy, "냉동빔")
        event = self.pending_one(e, owner, R.DEEP_COLD)
        self.assertTrue(WORLD.validate_world(e)["valid"])
        payload = CODEC.dump_engine(e)
        e.gm.snapshot("both source validators")
        owner.spec[SURVIVALIST.CSV_STATE]["owner_id"] = "trainer/wrong"
        owner.spec[R.STATE]["events"][-1]["native_clause_id"] = "wrong-clause"
        codes = {row["code"] for row in WORLD.validate_world(e)["issues"]}
        self.assertTrue({"survivalist_csv_selection", "class_actor_state_reaction"} <= codes)
        with self.assertRaises(CODEC.StateCodecError):
            CODEC.dump_engine(e)
        e.gm.restore("both source validators", reason="restore both independently owned sources")
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(payload, ensure_ascii=False)))
        for world in (e, loaded):
            actual_owner = WORLD.actor_index(world)[owner.entity_id]
            self.assertTrue(WORLD.validate_world(world)["valid"])
            self.assertEqual(world.skill_roll(actual_owner, "생존", fixed=[1] * 6).total, 8)
            self.assert_native(world.pending_class_actor_state_reactions(actual_owner)[0], R.DEEP_COLD)
            world.resolve_class_actor_state_reaction(actual_owner, event["id"], use=True)

    def test_legacy_v1_events_restore_without_retroactive_native_authority(self):
        e, owner, pokemon, enemy, event = self.pending_hit(R.DEEP_COLD)
        state = owner.spec[R.STATE]
        state["version"] = 1
        for key in ("acquisition_source", "native_clause_id", "native_source_sha256"):
            state["events"][0].pop(key)
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(e), ensure_ascii=False)))
        actual_owner = WORLD.actor_index(loaded)[owner.entity_id]
        row = loaded.pending_class_actor_state_reactions(actual_owner)[0]
        self.assertNotIn("native_clause_id", row)
        result = loaded.resolve_class_actor_state_reaction(actual_owner, event["id"], use=True)
        self.assertNotIn("native_clause_id", result)
        self.assertIn("얼음", WORLD.actor_index(loaded)[enemy.entity_id].conditions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
