"""Direct contracts for two source-explicit CSV item variants."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(ROOT / "engine"), str(CANONICAL / "engine"), str(CANONICAL / "tools")]

# Pin staged implementations before canonical fixtures change sys.path.
import food_effects as FOOD
import special_entities as SPECIAL
import state_codec as CODEC
import pokemon_progression as PROGRESSION
from builder import build_pokemon
import test_category3_food_effects as FOOD_FIXTURE
import test_category2_special_entities as AUGMENT_FIXTURE


class HomebrewBabyFoodTests(unittest.TestCase):
    setUpClass = classmethod(FOOD_FIXTURE.FoodTests.setUpClass.__func__)
    setUp = FOOD_FIXTURE.FoodTests.setUp
    actor = FOOD_FIXTURE.FoodTests.actor
    state = FOOD_FIXTURE.FoodTests.state
    built_pokemon = FOOD_FIXTURE.FoodTests.built_pokemon

    def feed(self, level, initial_level):
        self.built_pokemon(level)
        self.p.spec[PROGRESSION.LEVEL_STATE]["initial_level"] = initial_level
        self.a.spec["items"]["이유식"] = 1
        return self.e.use_item(
            self.a, "이유식", self.p, duration_minutes=1,
            duration_reason="actual homebrew Baby Food intake",
            food_policy="homebrew_initial_plus5",
        )

    def test_initial_level_plus_five_is_the_feed_boundary_and_actual_training_consumer(self):
        for level, eligible, expected_level in ((20, True, 21), (21, False, 21)):
            self.setUp()
            result = self.feed(level, 15)
            record = self.p.spec["baby_food"]
            self.assertEqual(result["eligible"], eligible)
            self.assertEqual(record["eligibility"], {
                "kind": "initial_level_window", "initial_level": 15,
                "maximum_level": 20, "clause_id": "C2CSV/inventory:94:7",
            })
            if eligible:
                # Preserve the native level-up move-slot decision before time.
                self.e.gm.set_move(
                    self.p, next(move for move in self.p.moves if move != "struggle"), False,
                    reason="player chose a slot for the actual Baby Food level",
                )
            self.e.pokemon_activity(self.a, "experience_training", targets=[self.p], safe=True)
            self.assertEqual(self.p.level, expected_level)
            self.assertEqual(self.p.spec["baby_food"]["consumed"], eligible)

    def test_missing_or_changed_initial_level_rejects_before_cost_or_training_time(self):
        self.built_pokemon(20)
        del self.p.spec[PROGRESSION.LEVEL_STATE]
        self.a.spec["items"]["이유식"] = 1
        before = self.state()
        with self.assertRaisesRegex(ValueError, "initial-level anchor"):
            self.e.use_item(
                self.a, "이유식", self.p, duration_minutes=1,
                duration_reason="missing source anchor", food_policy="homebrew_initial_plus5",
            )
        self.assertEqual(self.state(), before)

        self.setUp()
        self.feed(20, 15)
        self.p.spec["baby_food"]["eligibility"]["maximum_level"] = 99
        before = self.state()
        with self.assertRaisesRegex(ValueError, "eligibility source changed"):
            self.e.pokemon_activity(self.a, "experience_training", targets=[self.p], safe=True)
        self.assertEqual(self.state(), before)

    def test_homebrew_feed_identity_and_consumption_survive_json_restore(self):
        self.feed(20, 15)
        record = deepcopy(self.p.spec["baby_food"])
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        actor = next(c for c in loaded.gm.everyone if c.entity_id == self.a.entity_id)
        target = next(c for c in loaded.gm.everyone if c.entity_id == self.p.entity_id)
        self.assertEqual(target.spec["baby_food"], record)
        loaded.gm.set_move(
            target, next(move for move in target.moves if move != "struggle"), False,
            reason="restored player chose a slot for the actual Baby Food level",
        )
        loaded.pokemon_activity(actor, "experience_training", targets=[target], safe=True)
        self.assertEqual((target.level, target.spec["baby_food"]["consumed"]), (21, True))

    def test_existing_book_and_level20_profiles_keep_their_distinct_consumers(self):
        import downtime as DOWNTIME
        self.built_pokemon(15); self.a.spec["items"]["이유식"] = 1
        self.e.use_item(
            self.a, "이유식", self.p, duration_minutes=1,
            duration_reason="actual book Baby Food intake", food_policy="book_xp20_level15",
        )
        self.assertEqual(self.p.spec["baby_food"]["eligibility"], {
            "kind": "maximum_level", "maximum_level": 15,
        })
        before = self.p.spec["exp"]
        DOWNTIME.gain_exp_combatant(self.e, self.p, 9)
        self.assertEqual(self.p.spec["exp"] - before, 10)

        self.setUp(); self.built_pokemon(20); self.a.spec["items"]["이유식"] = 1
        self.e.use_item(
            self.a, "이유식", self.p, duration_minutes=1,
            duration_reason="actual level20 Baby Food intake", food_policy="raw_training_level20",
        )
        self.assertEqual(self.p.spec["baby_food"]["eligibility"], {
            "kind": "maximum_level", "maximum_level": 20,
        })
        self.e.gm.set_move(
            self.p, next(move for move in self.p.moves if move != "struggle"), False,
            reason="player chose a slot for the actual level20 Baby Food level",
        )
        self.e.pokemon_activity(self.a, "experience_training", targets=[self.p], safe=True)
        self.assertEqual((self.p.level, self.p.spec["baby_food"]["consumed"]), (21, True))


class SoftAugmentationProfileTests(unittest.TestCase):
    setUpClass = classmethod(AUGMENT_FIXTURE.SpecialTests.setUpClass.__func__)
    setUp = AUGMENT_FIXTURE.SpecialTests.setUp
    trainer = AUGMENT_FIXTURE.SpecialTests.trainer
    object = AUGMENT_FIXTURE.SpecialTests.object
    augment = AUGMENT_FIXTURE.SpecialTests.augment

    def soft(self, actor=None, uid="augmentation/1", instance="implant/1"):
        actor = actor or self.a
        return {
            "id": uid, "kind": "augmentation_set", "location": {"kind": "unknown"},
            "actor_id": actor.entity_id, "body_slots": ["eyes", "limbs", "body", "skin"],
            "installations": [{
                "instance_id": instance, "augmentation_id": "smart_vision", "external": True,
            }],
            "allow_added_parts": False, "essence_enabled": False,
            "capacity_profile": "inventory_soft_capacity10_extended",
        }

    def test_soft_source_policy_is_exact_and_external_trainer_installation_spends_capacity(self):
        policy_path = ROOT / "data" / "augmentation-soft-profile-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        source = CANONICAL / policy["source_file"]
        self.assertEqual(sha256(source.read_bytes()).hexdigest(), policy["source_file_sha256"])
        self.object("implant/1")
        result = SPECIAL.observe(self.e, self.soft(), reason="actual external trainer augmentation")
        view = result["state_view"]
        self.assertEqual((view["base_capacity"], view["capacity_limit"], view["used_capacity"]), (10, 10, 2))
        self.assertEqual(view["external_instance_ids"], ["implant/1"])
        self.assertEqual(view["action_execution_category"], [3, 6])

    def test_same_soft_capacity_contract_accepts_pokemon_and_survives_json_restore(self):
        pokemon = type(self.a)(self.poly, build_pokemon(self.poly, "이상해씨", 5, name="augmented-pokemon"))
        self.e.everyone.append(pokemon)
        self.object("implant/pokemon")
        row = self.soft(pokemon, "augmentation/pokemon", "implant/pokemon")
        SPECIAL.observe(self.e, row, reason="actual external Pokemon augmentation")
        loaded = CODEC.load_engine(self.poly, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        view = SPECIAL.view(loaded, "augmentation/pokemon")
        self.assertEqual((view["entity"]["actor_id"], view["state_view"]["remaining_capacity"]), (pokemon.entity_id, 8))
        self.assertEqual(view["state_view"]["external_instance_ids"], ["implant/pokemon"])

    def test_invalid_external_marker_or_profile_rejects_without_rewriting_actual_state(self):
        self.object("implant/1")
        row = self.soft()
        SPECIAL.observe(self.e, row, reason="actual soft augmentation baseline")
        before = deepcopy(self.e._physical_objects)
        row["installations"][0]["external"] = "yes"
        with self.assertRaisesRegex(ValueError, "external augmentation"):
            SPECIAL.observe(self.e, row, reason="invalid external marker")
        self.assertEqual(self.e._physical_objects, before)
        row = self.soft(); row["capacity_profile"] = "unsourced"
        with self.assertRaisesRegex(ValueError, "soft augmentation profile"):
            SPECIAL.observe(self.e, row, reason="invalid source profile")
        self.assertEqual(self.e._physical_objects, before)


if __name__ == "__main__":
    unittest.main()
