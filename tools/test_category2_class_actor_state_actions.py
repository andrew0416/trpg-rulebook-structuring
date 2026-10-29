"""Direct tests for four recovery/resource trainer feature clauses."""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]

from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
import action_lifecycle as ACTION
import action_points as AP
import class_actor_state_actions as CLASS_ACTIONS
import downtime as DOWNTIME
from state_codec import dump_engine, load_engine


class ClassActorStateActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="all")

    def fixture(self, *, feats=(), level=20, species="이상해씨", moves=("몸통박치기",)):
        engine = Engine(self.rules, seed=1821)
        trainer = Combatant(
            self.rules,
            build_trainer(
                self.rules,
                "Owner",
                30,
                {"hp": 40, "atk": 12, "def": 12, "spa": 12, "spd": 12, "spe": 12},
                moves=[],
                abilities=[],
                skills={"의학": "숙련", "직감": "숙련", "명령": "숙련", "일반지식": "숙련"},
                extra={"feats": list(feats), "edges": [], "items": {}},
            ),
        )
        pokemon = Combatant(
            self.rules,
            build_pokemon(
                self.rules,
                species,
                level,
                name="Partner",
                moves=list(moves),
                abilities=[],
                extra={"trainer_id": trainer.entity_id, "trainer": trainer.name},
            ),
        )
        other = Combatant(
            self.rules,
            build_pokemon(
                self.rules,
                "꼬부기",
                20,
                name="Other",
                moves=["몸통박치기"],
                abilities=[],
            ),
        )
        for actor in (trainer, pokemon, other):
            engine.gm.add_combatant(actor, reason="class state action fixture")
        return engine, trainer, pokemon, other

    def one(self, engine, trainer, source):
        rows = [event for event in engine.pending_class_actor_state_actions(trainer) if event["source"] == source]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_exact_four_policy_rows_and_incomplete_registry_sources(self):
        policy = CLASS_ACTIONS.policy(self.rules)
        self.assertEqual(set(policy["clauses"]), set(CLASS_ACTIONS.CLAUSE_BY_RULE.values()))
        source_path = ROOT / policy["source_file"]
        self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), policy["source_file_sha256"])
        with source_path.open(encoding="utf-8-sig", newline="") as source_file:
            rows = list(csv.reader(source_file))
        registry = json.loads(
            (ROOT / "data/verification/category2-class-csv-clause-status.json").read_text(encoding="utf-8")
        )
        indexed = {row["id"]: row for row in registry["rows"]}
        for rule_id, clause_id in CLASS_ACTIONS.CLAUSE_BY_RULE.items():
            clause = policy["clauses"][clause_id]
            self.assertEqual(rows[clause["source_record"] - 1], clause["source_cells"])
            self.assertEqual(indexed[clause_id]["status"], "implemented")
            self.assertTrue(indexed[clause_id]["include_category2"])
            self.assertIsNone(indexed[clause_id]["dedupe_target"])
            self.assertEqual(self.rules._selected_rule(rule_id), rule_id)

    def test_emergency_care_tool_full_recovery_limits_and_medical_override(self):
        feats = (CLASS_ACTIONS.EMERGENCY_CARE, CLASS_ACTIONS.MEDICAL_TECHNIQUE)
        engine, trainer, pokemon, other = self.fixture(feats=feats)
        trainer.spec["items"]["응급치료키트"] = 1
        pokemon.hp = 1
        pokemon.injuries = 2
        engine.apply_status(pokemon, "독")
        first = engine.emergency_care_expertise(trainer, pokemon)
        self.assertEqual(first["injuries_removed"], 1)
        self.assertEqual(pokemon.hp, pokemon.max_hp)
        self.assertNotIn("독", pokemon.conditions)
        self.assertEqual(trainer.spec["items"]["응급치료키트"], 1)
        pokemon.hp = 1
        second = engine.emergency_care_expertise(trainer, pokemon)
        self.assertTrue(second["target_daily_limit_waived"])
        self.assertEqual(pokemon.hp, pokemon.base_max_hp)
        other.hp = 1
        engine.emergency_care_expertise(trainer, other)
        before = deepcopy((trainer.spec, pokemon.spec, other.spec, pokemon.hp, other.hp))
        with self.assertRaisesRegex(ValueError, "Daily x3"):
            engine.emergency_care_expertise(trainer, other)
        self.assertEqual(before, (trainer.spec, pokemon.spec, other.spec, pokemon.hp, other.hp))

        engine2, trainer2, pokemon2, _ = self.fixture(feats=(CLASS_ACTIONS.EMERGENCY_CARE,))
        trainer2.spec["items"]["응급치료키트"] = 1
        engine2.emergency_care_expertise(trainer2, pokemon2)
        with self.assertRaisesRegex(ValueError, "target daily"):
            engine2.emergency_care_expertise(trainer2, pokemon2)

    def test_emergency_care_missing_tool_is_failure_atomic(self):
        engine, trainer, pokemon, _ = self.fixture(feats=(CLASS_ACTIONS.EMERGENCY_CARE,))
        pokemon.hp = 1
        pokemon.injuries = 1
        before = deepcopy(
            (trainer.spec, pokemon.spec, pokemon.hp, pokemon.injuries, getattr(trainer, "_action_history", []))
        )
        with self.assertRaisesRegex(ValueError, "inventory"):
            engine.emergency_care_expertise(trainer, pokemon)
        self.assertEqual(
            before,
            (trainer.spec, pokemon.spec, pokemon.hp, pokemon.injuries, getattr(trainer, "_action_history", [])),
        )

    def test_food_receipt_offers_taste_and_stacks_temp_hp_with_atomic_ap_failure(self):
        engine, trainer, pokemon, _ = self.fixture(feats=(CLASS_ACTIONS.THATS_THE_TASTE,))
        trainer.spec["items"]["초코바"] = 1
        acquired = engine.use_item(
            trainer,
            "초코바",
            pokemon,
            duration_minutes=1,
            duration_reason="actual sourced meal",
        )
        engine.consume_food_buff(
            pokemon,
            buff_id=acquired["buff_id"],
            action_kind="free",
            action_reason="actual committed Digestion Buff benefit",
        )
        event = self.one(engine, trainer, CLASS_ACTIONS.THATS_THE_TASTE)
        before_trigger = deepcopy((trainer.spec, pokemon.spec, pokemon.temp_hp))
        trainer.spec["ap_spent"] = AP.maximum(trainer)
        blocked = deepcopy((trainer.spec, pokemon.spec, pokemon.temp_hp))
        with self.assertRaisesRegex(ValueError, "insufficient"):
            engine.resolve_class_actor_state_action(trainer, event["id"], use=True)
        self.assertEqual(blocked, (trainer.spec, pokemon.spec, pokemon.temp_hp))
        trainer.spec["ap_spent"] = before_trigger[0].get("ap_spent", 0)
        import temporary_hp as TEMP_HP
        TEMP_HP.grant(engine, pokemon, 3, provenance={"fixture": "existing sourced temporary HP"})
        result = engine.resolve_class_actor_state_action(trainer, event["id"], use=True)
        self.assertEqual(result["temporary_hp_granted"], 2 * result["intuition_rank"])
        self.assertEqual(pokemon.temp_hp, 3 + result["temporary_hp_granted"])
        self.assertEqual(trainer.spec["ap_spent"], 1)

    def test_medical_technique_uses_actual_medicine_target_and_nonmedicine_exclusion(self):
        engine, trainer, pokemon, _ = self.fixture(feats=(CLASS_ACTIONS.MEDICAL_TECHNIQUE,))
        trainer.spec["items"]["상처약"] = 1
        pokemon.hp = 1
        engine.use_item(trainer, "상처약", pokemon)
        event = self.one(engine, trainer, CLASS_ACTIONS.MEDICAL_TECHNIQUE)
        hp_after_item = pokemon.hp
        result = engine.resolve_class_actor_state_action(trainer, event["id"], use=True)
        self.assertEqual(result["healing_requested"], engine.tick(pokemon) + result["medicine_rank"])
        self.assertEqual(pokemon.hp, min(pokemon.base_max_hp, hp_after_item + result["healing_requested"]))
        self.assertEqual(trainer.spec["items"]["상처약"], 0)

        engine2, trainer2, pokemon2, _ = self.fixture(feats=(CLASS_ACTIONS.MEDICAL_TECHNIQUE,))
        trainer2.spec["items"]["초코바"] = 1
        engine2.use_item(trainer2, "초코바", pokemon2, duration_minutes=1, duration_reason="food is not medicine")
        self.assertFalse(engine2.pending_class_actor_state_actions(trainer2))

    def test_virtuoso_taste_recomputes_sixteen_after_pending_restore_without_eight_dice(self):
        import skill_modifiers as SKILL
        import state_grants as GRANTS
        engine, trainer, pokemon, _ = self.fixture(feats=(CLASS_ACTIONS.THATS_THE_TASTE,))
        engine.gm.set_skill(trainer, "직감", 6, reason="actual Master Intuition before Virtuoso acquisition")
        GRANTS.transition(engine, trainer, lambda e, owner: owner.spec.update(
            edges=[*owner.spec["edges"], "edge/거장"], edge_choices={"edge/거장": ["직감"]}))
        self.assertEqual(SKILL.effective_rank(engine.r, trainer, "직감"), 8)
        trainer.spec["items"]["초코바"] = 1
        acquired = engine.use_item(
            trainer, "초코바", pokemon, duration_minutes=1, duration_reason="actual sourced meal")
        engine.consume_food_buff(
            pokemon, buff_id=acquired["buff_id"], action_kind="free",
            action_reason="actual committed Digestion Buff benefit")
        event = self.one(engine, trainer, CLASS_ACTIONS.THATS_THE_TASTE)
        trainer_id, pokemon_id = trainer.entity_id, pokemon.entity_id
        restored = load_engine(
            Rules(str(engine.r.root), ruleset="all"), json.loads(json.dumps(dump_engine(engine))))
        actors = {actor.entity_id: actor for actor in restored.everyone}
        trainer, pokemon = actors[trainer_id], actors[pokemon_id]
        self.assertEqual(self.one(restored, trainer, CLASS_ACTIONS.THATS_THE_TASTE)["id"], event["id"])
        result = restored.resolve_class_actor_state_action(trainer, event["id"], use=True)
        self.assertEqual((result["intuition_rank"], result["temporary_hp_granted"], pokemon.temp_hp), (8, 16, 16))
        self.assertEqual(SKILL.rank(restored.r, trainer, "직감")[2], 6)
        dump_engine(restored)

    def test_virtuoso_medicine_recomputes_tick_plus_eight_after_pending_restore_without_eight_dice(self):
        import skill_modifiers as SKILL
        import state_grants as GRANTS
        engine, trainer, pokemon, _ = self.fixture(feats=(CLASS_ACTIONS.MEDICAL_TECHNIQUE,))
        engine.gm.set_skill(trainer, "의학", 6, reason="actual Master Medicine before Virtuoso acquisition")
        GRANTS.transition(engine, trainer, lambda e, owner: owner.spec.update(
            edges=[*owner.spec["edges"], "edge/거장"], edge_choices={"edge/거장": ["의학"]}))
        self.assertEqual(SKILL.effective_rank(engine.r, trainer, "의학"), 8)
        trainer.spec["items"]["상처약"] = 1
        pokemon.hp = 1
        engine.use_item(trainer, "상처약", pokemon)
        event = self.one(engine, trainer, CLASS_ACTIONS.MEDICAL_TECHNIQUE)
        trainer_id, pokemon_id = trainer.entity_id, pokemon.entity_id
        restored = load_engine(
            Rules(str(engine.r.root), ruleset="all"), json.loads(json.dumps(dump_engine(engine))))
        actors = {actor.entity_id: actor for actor in restored.everyone}
        trainer, pokemon = actors[trainer_id], actors[pokemon_id]
        self.assertEqual(self.one(restored, trainer, CLASS_ACTIONS.MEDICAL_TECHNIQUE)["id"], event["id"])
        hp_after_item = pokemon.hp
        result = restored.resolve_class_actor_state_action(trainer, event["id"], use=True)
        self.assertEqual((result["medicine_rank"], result["healing_requested"]), (8, restored.tick(pokemon) + 8))
        self.assertEqual(pokemon.hp, min(pokemon.base_max_hp, hp_after_item + restored.tick(pokemon) + 8))
        self.assertEqual(trainer.spec["items"]["상처약"], 0)
        self.assertEqual(SKILL.rank(restored.r, trainer, "의학")[2], 6)
        dump_engine(restored)

    def test_top_percentage_native_level_events_four_use_cap_and_stat_source(self):
        engine, trainer, pokemon, _ = self.fixture(
            feats=(CLASS_ACTIONS.TOP_PERCENTAGE,), level=4, species="메타몽", moves=("변신",)
        )
        initial_points = pokemon.spec["tutor_points"]
        for expected_level in (5, 10, 15, 20):
            while pokemon.level < expected_level:
                DOWNTIME.gain_exp_combatant(engine, pokemon, "to next level")
            event = self.one(engine, trainer, CLASS_ACTIONS.TOP_PERCENTAGE)
            self.assertEqual(event["payload"]["level"], expected_level)
            result = engine.resolve_class_actor_state_action(trainer, event["id"], use=True)
            self.assertEqual(result["target_uses"], expected_level // 5)
        self.assertEqual(pokemon.spec["tutor_points"], initial_points + 8)
        for stat in pokemon.stats:
            self.assertEqual(pokemon.stats[stat], pokemon.spec["stats"][stat] + 1)
            operations = pokemon.spec["state_grants"]["stat_sources"][stat]["sources"]
            self.assertEqual(operations["top-percentage:" + pokemon.entity_id][stat]["delta"], 1)

    def test_maximum_level_exception_and_pending_json_restore(self):
        engine, trainer, pokemon, _ = self.fixture(feats=(CLASS_ACTIONS.TOP_PERCENTAGE,), level=100)
        event_id = engine.offer_top_percentage_at_max_level(trainer, pokemon)
        restored = load_engine(self.rules, json.loads(json.dumps(dump_engine(engine), ensure_ascii=False)))
        actors = {actor.entity_id: actor for actor in restored.everyone}
        restored_trainer = actors[trainer.entity_id]
        restored_pokemon = actors[pokemon.entity_id]
        pending = restored.pending_class_actor_state_actions(restored_trainer)
        self.assertEqual([event["id"] for event in pending], [event_id])
        with self.assertRaisesRegex(ValueError, "accepted or declined|class state action"):
            ACTION.ensure_resolutions_clear(restored)
        result = restored.resolve_class_actor_state_action(restored_trainer, event_id, use=True)
        self.assertTrue(result["used"])
        self.assertEqual(restored_pokemon.spec["tutor_points"], pokemon.spec["tutor_points"] + 1)
        for _ in range(3):
            next_id = restored.offer_top_percentage_at_max_level(restored_trainer, restored_pokemon)
            restored.resolve_class_actor_state_action(restored_trainer, next_id, use=True)
        fifth_id = restored.offer_top_percentage_at_max_level(restored_trainer, restored_pokemon)
        with self.assertRaisesRegex(ValueError, "at most four"):
            restored.resolve_class_actor_state_action(restored_trainer, fifth_id, use=True)

    def test_decline_spends_no_ap_or_feature_use(self):
        engine, trainer, pokemon, _ = self.fixture(feats=(CLASS_ACTIONS.THATS_THE_TASTE,))
        trainer.spec["items"]["초코바"] = 1
        buff = engine.use_item(trainer, "초코바", pokemon, duration_minutes=1, duration_reason="actual food")
        engine.consume_food_buff(pokemon, buff_id=buff["buff_id"], action_kind="free", action_reason="actual benefit")
        event = self.one(engine, trainer, CLASS_ACTIONS.THATS_THE_TASTE)
        before = deepcopy((trainer.spec.get("ap_spent", 0), pokemon.temp_hp))
        self.assertEqual(engine.resolve_class_actor_state_action(trainer, event["id"], use=False), {"used": False})
        self.assertEqual(before, (trainer.spec.get("ap_spent", 0), pokemon.temp_hp))
        self.assertFalse(engine.pending_class_actor_state_actions(trainer))


if __name__ == "__main__":
    unittest.main()
