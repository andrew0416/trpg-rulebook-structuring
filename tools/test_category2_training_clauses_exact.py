"""Exact source and native lifecycle checks for the seven core Training clauses."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from engine import Combatant, Engine, Rules
from state_codec import dump_engine, load_engine
from tools.report_category2_progress import collect as collect_category2
import downtime as DOWNTIME
import initiative as INITIATIVE
import items
import pokemon_entities as ENTITIES
import state_grants as GRANTS
import training_features as TRAINING


CLAUSES = {
    "C03-081": "c7142bcc8dc822426f1e8043640005df62656182c0fc1938e2895b48d070c974",
    "C03-082": "c7142bcc8dc822426f1e8043640005df62656182c0fc1938e2895b48d070c974",
    "C03-087": "baec4ee368d5261d6e630f057366ab84dff39d1829beab77d1fd384c3bd67b52",
    "input/ch03-skills-edges-feats.md:696-700": "2b340e894cf8b8c08158b316bbeca89699373192ae302a993c4ef417f4a260c9",
    "input/ch03-skills-edges-feats.md:702-706": "79f3cdca4b2e766af9a3ed911177a23216818754e37b7c66961dfebabe58acce",
    "input/ch03-skills-edges-feats.md:708-712": "1eb06349d51b3894179aad313563543d7e7d107ec3a8e739bd3e0c63b949a8b7",
    "input/ch03-skills-edges-feats.md:714-718": "08bc95ffaace130e0b090c243b035cb57f07652193bb167c5bb2d46e09fbc542",
}
FEATURE_CLAUSES = {
    TRAINING.AGILITY: "input/ch03-skills-edges-feats.md:696-700",
    TRAINING.BRUTAL: "input/ch03-skills-edges-feats.md:702-706",
    TRAINING.FOCUSED: "input/ch03-skills-edges-feats.md:708-712",
    TRAINING.INSPIRED: "input/ch03-skills-edges-feats.md:714-718",
}
EXPECTED_RULES = {
    TRAINING.AGILITY: {"skills": {"육상": 3, "명령": 2}, "bonuses": {"movement": 1, "initiative": 4}},
    TRAINING.BRUTAL: {"skills": {"협박": 3, "명령": 2}, "bonuses": {"critical": 1, "effect": 1}},
    TRAINING.FOCUSED: {"skills": {"명령": 3}, "bonuses": {"accuracy": 1, "skill": 2}},
    TRAINING.INSPIRED: {"skills": {"매력": 3, "명령": 2}, "bonuses": {"evasion": 1, "save": 2}},
}


class TrainingClauseExactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")
        cls.ledger_path = ROOT / "data/verification/category2-class-clause-status.json"
        cls.ledger = json.loads(cls.ledger_path.read_text(encoding="utf-8"))

    def fixture(self):
        engine = Engine(self.rules, seed=708)
        common = dict(
            level=20,
            stats={"hp": 60, "atk": 20, "def": 15, "spa": 20, "spd": 15, "spe": 10},
            movement={"land": 6, "swim": 3, "sky": 0},
            pos=(0, 0),
        )
        trainer = Combatant(self.rules, dict(
            common, name="training-owner", kind="trainer", feats=list(TRAINING.RULES),
            skills={"육상": 3, "명령": 3, "협박": 3, "매력": 3}, moves=[],
        ))
        pokemon = Combatant(self.rules, dict(
            common, name="training-target", kind="pokemon", trainer_id=trainer.entity_id,
            trainer=trainer.name, skills={"육상": "2d6+1"}, moves=["move/불꽃세례"], pos=(1, 0),
        ))
        engine.everyone = engine.gm.everyone = [trainer, pokemon]
        engine.time_actors(engine.everyone)
        trainer.side = pokemon.side = "party"
        ENTITIES.observe_loyalty(engine, pokemon, 3, reason="actual willing owned training target")
        items.register_feats(engine, trainer)
        return engine, trainer, pokemon

    def test_exact_source_hashes_anchors_and_feature_policy_match(self):
        source = ROOT / "input/ch03-skills-edges-feats.md"
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).hexdigest(),
            "b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23",
        )
        lines = source.read_text(encoding="utf-8").splitlines()
        rows = {row["source_clause_id"]: row for row in self.ledger["entries"]}
        self.assertEqual(set(CLAUSES), set(FEATURE_CLAUSES.values()) | {"C03-081", "C03-082", "C03-087"})
        for clause_id, digest in CLAUSES.items():
            with self.subTest(clause=clause_id):
                row = rows[clause_id]
                self.assertIn(row["status"], {"incomplete", "implemented"})
                self.assertTrue(row["include_category2"])
                anchor = row["anchors"][0]
                excerpt = "\n".join(lines[anchor["start"] - 1:anchor["end"]])
                self.assertEqual(hashlib.sha256(excerpt.encode("utf-8")).hexdigest(), digest)
                self.assertEqual(anchor["sha256"], digest)
        self.assertEqual(
            {uid: {key: deepcopy(policy[key]) for key in ("skills", "bonuses")}
             for uid, policy in TRAINING.RULES.items()},
            EXPECTED_RULES,
        )
        self.assertEqual(set(TRAINING.CSV_CLAUSES), set(FEATURE_CLAUSES))

    def test_training_and_order_share_consumers_but_keep_independent_lifetimes(self):
        engine, trainer, pokemon = self.fixture()
        receipt = engine.train_pokemon(
            trainer,
            [(pokemon, [TRAINING.AGILITY])],
            minutes=30,
            reason="observed exact core Training session",
            request_id="exact-training-clause",
            safe=True,
        )
        self.assertEqual((engine.elapsed_seconds, trainer._action_history), (1800, ["extended"]))
        self.assertEqual(engine.move_profile(pokemon, "land")[0], 7)
        self.assertEqual(INITIATIVE.value(self.rules, pokemon).value, 14)
        trained = TRAINING.records(pokemon)
        self.assertEqual([row["mode"] for row in trained], ["training"])
        training_source = trained[0][GRANTS.TAG]
        self.assertEqual(
            (trained[0]["owner"], pokemon.spec[GRANTS.KEY]["sources"][training_source]["owner_id"]),
            (trainer, trainer.entity_id),
        )
        self.assertEqual(receipt["sources"][0]["source"], training_source)

        engine.start_round(engine.everyone)
        engine.gm.observe_sensory_environment(
            trainer,
            pokemon,
            paths={"auditory": True},
            present=True,
            reason="actual audible Training Order",
        )
        order = engine.manual_feat(trainer, TRAINING.FOCUSED, pokemon)
        self.assertEqual(order["status"], "applied")
        self.assertEqual([row["mode"] for row in TRAINING.records(pokemon)], ["training", "orders"])
        self.assertEqual(TRAINING.bonus(pokemon, "movement"), 1)
        self.assertEqual(TRAINING.bonus(pokemon, "accuracy"), 1)

        restored = load_engine(
            self.rules,
            json.loads(json.dumps(dump_engine(engine), ensure_ascii=False)),
        )
        actors = {actor.entity_id: actor for actor in restored.everyone}
        owner = actors[trainer.entity_id]
        target = actors[pokemon.entity_id]
        self.assertEqual([row["mode"] for row in TRAINING.records(target)], ["training", "orders"])
        self.assertTrue(all(row["owner"] is owner for row in TRAINING.records(target)))
        restored.start_of_turn(owner)
        self.assertEqual([row["mode"] for row in TRAINING.records(target)], ["training"])
        self.assertEqual((TRAINING.bonus(target, "movement"), TRAINING.bonus(target, "accuracy")), (1, 0))
        restored.end_of_turn(owner)
        restored.end_encounter()
        DOWNTIME.extended_rest(restored, owner, 4)
        self.assertFalse(TRAINING.records(target))
        self.assertEqual(restored.move_profile(target, "land")[0], 6)

    def test_shadow_progress_is_atomic_for_all_seven_frozen_rows(self):
        before = collect_category2(ROOT)
        self.assertEqual(before["denominator"], 2352)
        rows = {row["source_clause_id"]: row for row in self.ledger["entries"]}
        pending = {clause for clause in CLAUSES if rows[clause]["status"] == "incomplete"}
        self.assertIn(len(pending), (0, 7))
        with tempfile.TemporaryDirectory(prefix="training-clauses-") as tmp:
            shadow = Path(tmp)
            for tree in ("input", "data/verification"):
                for source in (ROOT / tree).rglob("*"):
                    if not source.is_file():
                        continue
                    target = shadow / source.relative_to(ROOT)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        os.link(source, target)
                    except OSError:
                        target.write_bytes(source.read_bytes())
            path = shadow / "data/verification/category2-class-clause-status.json"
            path.unlink()
            doc = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            found = set()
            for row in doc["entries"]:
                if row["source_clause_id"] in pending:
                    row["status"] = "implemented"
                    found.add(row["source_clause_id"])
            self.assertEqual(found, pending)
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            after = collect_category2(shadow)
        self.assertEqual(after["validation_errors"], [])
        self.assertEqual(after["denominator"], before["denominator"])
        self.assertEqual(after["completed_clause_count"] - before["completed_clause_count"], len(pending))


if __name__ == "__main__":
    unittest.main(verbosity=2)

