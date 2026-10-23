"""Direct tests for three trainer features sharing native attack damage."""
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
from grid import Grid
import action_lifecycle as ACTION
import class_actor_state_reactions as REACTIONS
import frequency as FREQUENCY
import state_codec as CODEC
import world_entities as WORLD


class ClassActorStateReactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="all")

    def fixture(self, *, feats=(), partner_types=("풀",), partner_moves=("냉동빔",), weather=None):
        engine = Engine(self.rules, seed=1818)
        engine.grid = Grid(14, 8)
        if weather is not None:
            # The reaction owner reads the sourced weather registry through
            # effects.effective_weather, so the fixture must place weather through
            # the actual GM weather path rather than a direct engine.weather value.
            engine.gm.set_weather(weather, rounds=None, reason="actual sourced field weather for the reaction fixture")
        trainer = Combatant(
            self.rules,
            build_trainer(
                self.rules,
                "Owner",
                30,
                {"hp": 40, "atk": 12, "def": 12, "spa": 12, "spd": 12, "spe": 12},
                moves=[],
                abilities=[],
                skills={"생존": "숙련", "일반지식": "숙련", "명령": "숙련", "협박": "숙련"},
                extra={
                    "feats": list(feats),
                    "edges": [],
                    "type_link_skills": {"풀": "생존"},
                },
            ),
        )
        partner = Combatant(
            self.rules,
            build_pokemon(
                self.rules,
                "이상해씨",
                20,
                name="Partner",
                moves=list(partner_moves),
                abilities=[],
                extra={
                    "trainer_id": trainer.entity_id,
                    "trainer": trainer.name,
                    "types": list(partner_types),
                },
            ),
        )
        enemy = Combatant(
            self.rules,
            build_pokemon(
                self.rules,
                "꼬부기",
                20,
                name="Enemy",
                moves=["화염방사", "몸통박치기"],
                abilities=[],
            ),
        )
        for actor, position, side in (
            (trainer, (0, 0), "party"),
            (partner, (1, 0), "party"),
            (enemy, (3, 0), "foe"),
        ):
            engine.gm.add_combatant(actor, pos=position, side=side, reason="actual actor-state reaction fixture")
        engine.begin_encounter(engine.everyone)
        engine.start_round(engine.everyone)
        return engine, trainer, partner, enemy

    def start(self, engine, actor, count=10):
        engine.start_of_turn(actor, initiative_count=count)

    def hit(self, engine, attacker, target, move_name, *, critical=False):
        move = self.rules.move("move/" + move_name)
        return engine.resolve_attack_damage(attacker, target, move, crit=critical, set_damage=True)

    def pending_one(self, engine, trainer, source):
        rows = [row for row in engine.pending_class_actor_state_reactions(trainer) if row["source"] == source]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def snapshot(self, engine, *actors):
        return {
            "specs": [deepcopy(actor.spec) for actor in actors],
            "stages": [deepcopy(actor.stages) for actor in actors],
            "temp_hp": [actor.temp_hp for actor in actors],
            "history": [deepcopy(getattr(actor, "_action_history", [])) for actor in actors],
            "rng": engine.rng.getstate(),
        }

    def test_exact_three_policy_rows_and_separate_csv_native_statuses(self):
        policy = REACTIONS.policy(self.rules)
        self.assertEqual(set(policy["clauses"]), set(REACTIONS.CLAUSE_BY_RULE.values()))
        source_path = ROOT / policy["source_file"]
        self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), policy["source_file_sha256"])
        with source_path.open(encoding="utf-8-sig", newline="") as source_file:
            rows = list(csv.reader(source_file))
        registry = json.loads(
            (ROOT / "data/verification/category2-class-csv-clause-status.json").read_text(encoding="utf-8")
        )
        indexed = {row["id"]: row for row in registry["rows"]}
        for rule_id, clause_id in REACTIONS.CLAUSE_BY_RULE.items():
            clause = policy["clauses"][clause_id]
            self.assertEqual(rows[clause["source_record"] - 1], clause["source_cells"])
            self.assertEqual(indexed[clause_id]["status"], "implemented")
            self.assertTrue(indexed[clause_id]["include_category2"])
            self.assertIsNone(indexed[clause_id]["dedupe_target"])
            self.assertEqual(self.rules._selected_rule(rule_id), rule_id)
        native_registry = json.loads(
            (ROOT / "data/verification/category2-class-clause-status.json").read_text(encoding="utf-8")
        )
        native = {row["source_clause_id"]: row for row in native_registry["entries"]}
        # CSV behavior completion and whole native clause completion are
        # independent ledgers. The Enduring Bloom native clause (1637-1641) was
        # completed by the published Type Ace batch (book_type_ace_full_completion),
        # so all three native rows are now pinned as implemented.
        expected = {
            "input/ch04-trainer-classes.md:1454-1458": "implemented",
            "input/ch04-trainer-classes.md:1701-1705": "implemented",
            "input/ch04-trainer-classes.md:1637-1641": "implemented",
        }
        for clause_id, status in expected.items():
            self.assertEqual(native[clause_id]["status"], status)
            self.assertTrue(native[clause_id]["include_category2"])

    def test_this_will_not_stand_critical_massive_and_target_scene_limit(self):
        source = REACTIONS.THIS_WILL_NOT_STAND
        engine, trainer, partner, enemy = self.fixture(feats=[source], partner_types=("드래곤",))
        self.start(engine, enemy)
        before = {stat: partner.stages[stat] for stat in ("atk", "spa", "spe")}
        self.hit(engine, enemy, partner, "몸통박치기", critical=True)
        event = self.pending_one(engine, trainer, source)
        self.assertTrue(event["critical"])
        with self.assertRaisesRegex(ValueError, "accepted or declined"):
            ACTION.ensure_resolutions_clear(engine)
        result = engine.resolve_class_actor_state_reaction(trainer, event["id"], use=True)
        self.assertTrue(result["used"])
        for stat in before:
            self.assertEqual(partner.stages[stat], before[stat] + 1)
        self.hit(engine, enemy, partner, "몸통박치기", critical=True)
        self.assertFalse(engine.pending_class_actor_state_reactions(trainer))

        other_engine, other_trainer, other_partner, other_enemy = self.fixture(
            feats=[source], partner_types=("드래곤",)
        )
        self.start(other_engine, other_enemy)
        other_enemy.stats["atk"] = 100
        other_enemy.spec["stats"]["atk"] = 100
        self.hit(other_engine, other_enemy, other_partner, "몸통박치기")
        massive = self.pending_one(other_engine, other_trainer, source)
        self.assertTrue(massive["massive"])

    def test_enduring_bloom_native_super_effective_hit_rank_sunny_and_atomic_failure(self):
        source = REACTIONS.ENDURING_BLOOM
        engine, trainer, partner, enemy = self.fixture(feats=[source], weather="sunny")
        self.start(engine, enemy)
        self.hit(engine, enemy, partner, "화염방사")
        event = self.pending_one(engine, trainer, source)
        self.assertEqual(event["actual_type"], "불꽃")
        self.assertGreater(event["type_multiplier"], 1)
        before = self.snapshot(engine, trainer, partner, enemy)
        with self.assertRaisesRegex(ValueError, "distinct"):
            engine.resolve_class_actor_state_reaction(
                trainer, event["id"], use=True, stats=("def", "def")
            )
        self.assertEqual(self.snapshot(engine, trainer, partner, enemy), before)
        result = engine.resolve_class_actor_state_reaction(
            trainer, event["id"], use=True, stats=("def", "spd")
        )
        self.assertEqual(result["type_link_rank"], 4)
        self.assertEqual(result["temporary_hp_granted"], 8)
        self.assertEqual(partner.temp_hp, 8)
        self.assertEqual(partner.stages["def"], 1)
        self.assertEqual(partner.stages["spd"], 1)
        frequency = FREQUENCY.state(trainer)["activations"][source]
        self.assertEqual(frequency["kind"], "scene")
        self.assertEqual(frequency["used"], 1)

    def test_enduring_bloom_decline_consumes_nothing_and_non_sunny_has_one_choice(self):
        source = REACTIONS.ENDURING_BLOOM
        engine, trainer, partner, enemy = self.fixture(feats=[source])
        self.start(engine, enemy)
        self.hit(engine, enemy, partner, "화염방사")
        event = self.pending_one(engine, trainer, source)
        engine.resolve_class_actor_state_reaction(trainer, event["id"], use=False)
        self.assertNotIn(source, FREQUENCY.state(trainer)["activations"])
        self.hit(engine, enemy, partner, "화염방사")
        retry = self.pending_one(engine, trainer, source)
        before = self.snapshot(engine, trainer, partner)
        with self.assertRaisesRegex(ValueError, "one stat"):
            engine.resolve_class_actor_state_reaction(
                trainer, retry["id"], use=True, stats=("def", "spd")
            )
        self.assertEqual(self.snapshot(engine, trainer, partner), before)
        engine.resolve_class_actor_state_reaction(trainer, retry["id"], use=True, stats=("def",))
        self.assertEqual(partner.stages["def"], 1)

    def test_deep_cold_daily_target_limit_and_one_round_frozen_lifetime(self):
        source = REACTIONS.DEEP_COLD
        engine, trainer, partner, enemy = self.fixture(feats=[source], partner_types=("얼음",))
        self.start(engine, partner, count=10)
        self.hit(engine, partner, enemy, "냉동빔")
        event = self.pending_one(engine, trainer, source)
        result = engine.resolve_class_actor_state_reaction(trainer, event["id"], use=True)
        self.assertTrue(result["frozen"])
        self.assertIn("얼음", enemy.conditions)
        self.assertEqual((enemy.stages["atk"], enemy.stages["spa"], enemy.stages["spe"]), (-1, -1, -1))
        daily = FREQUENCY.state(trainer)["activations"][source]
        self.assertEqual((daily["kind"], daily["used"]), ("daily", 1))
        self.hit(engine, partner, enemy, "냉동빔")
        self.assertFalse(engine.pending_class_actor_state_reactions(trainer))
        engine.end_of_turn(partner)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(trainer, initiative_count=20)
        self.assertIn("얼음", enemy.conditions)
        engine.end_of_turn(trainer)
        engine.start_of_turn(enemy, initiative_count=10)
        self.assertNotIn("얼음", enemy.conditions)

    def test_pending_reaction_save_restore_keeps_decision_and_actual_participants(self):
        source = REACTIONS.DEEP_COLD
        engine, trainer, partner, enemy = self.fixture(feats=[source], partner_types=("얼음",))
        self.start(engine, partner, count=10)
        self.hit(engine, partner, enemy, "냉동빔")
        event = self.pending_one(engine, trainer, source)
        payload = json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False))
        loaded = CODEC.load_engine(self.rules, payload)
        index = WORLD.actor_index(loaded)
        loaded_trainer = index[trainer.entity_id]
        loaded_enemy = index[enemy.entity_id]
        restored = loaded.pending_class_actor_state_reactions(loaded_trainer)
        self.assertEqual([row["id"] for row in restored], [event["id"]])
        loaded.resolve_class_actor_state_reaction(loaded_trainer, event["id"], use=True)
        self.assertIn("얼음", loaded_enemy.conditions)
        self.assertEqual(FREQUENCY.state(loaded_trainer)["activations"][source]["used"], 1)

    def test_wrong_type_and_non_super_effective_hits_offer_no_reaction(self):
        deep = REACTIONS.DEEP_COLD
        bloom = REACTIONS.ENDURING_BLOOM
        engine, trainer, partner, enemy = self.fixture(feats=[deep, bloom])
        self.start(engine, partner)
        self.hit(engine, partner, enemy, "몸통박치기")
        self.assertFalse(engine.pending_class_actor_state_reactions(trainer))
        engine.end_of_turn(partner)
        engine.start_of_turn(enemy, initiative_count=5)
        partner._types = ["노말"]
        self.hit(engine, enemy, partner, "화염방사")
        self.assertFalse(engine.pending_class_actor_state_reactions(trainer))


if __name__ == "__main__":
    unittest.main(verbosity=2)
