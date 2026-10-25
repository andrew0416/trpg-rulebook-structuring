"""Exact source/version binding for twelve fixed Feature Ability grants."""
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

from builder import build_trainer
from engine import Combatant, Engine, Rules
from state_codec import dump_engine, load_engine
from tools.report_category2_progress import collect as collect_category2, SOURCES as PROGRESS_SOURCES
import ability_transitions as ABILITIES
import items
import source_scoped_ability_grants as SOURCE_SCOPED
import state_grants as GRANTS


WEIGHTLESS = {
    "clause_id": "input/ch04-trainer-classes.md:2980-2984",
    "rule_id": "feat/무중력-스텝",
    "ability_id": "ability/틈새포착",
    "ability_title": "틈새포착",
}
BLOCKED_SUN = {
    "clause_id": "C2ADD/supp-blessings:602",
    "rule_id": "feat/파이어의-메이저-기프트-햇볕",
    "candidates": ["ability/햇볕-playtest", "ability/햇볕-playtest-2"],
}


class SourceScopedFixedAbilityGrantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="all")
        cls.policy = json.loads(
            (ROOT / SOURCE_SCOPED.POLICY).read_text(encoding="utf-8")
        )
        cls.cases = [WEIGHTLESS] + [
            {
                "clause_id": row["clause_id"],
                "rule_id": rule_id,
                "ability_id": row["ability_id"],
                "ability_title": row["ability_title"],
            }
            for rule_id, row in cls.policy["rules"].items()
        ]

    def fixture(self, rule_id):
        engine = Engine(self.rules, seed=127)
        spec = build_trainer(
            self.rules,
            "fixed-ability-owner",
            30,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
            moves=[],
        )
        spec.update(classes=[], edges=[], feats=[rule_id], abilities=[], feature_choices={})
        actor = Combatant(self.rules, spec)
        engine.everyone = engine.gm.everyone = [actor]
        return engine, actor

    @staticmethod
    def source(actor, rule_id):
        return "feature:" + actor.entity_id + ":" + rule_id

    def test_policy_pins_every_source_unit_and_excludes_ambiguous_sun_blanket(self):
        self.assertEqual(len(self.cases), 12)
        self.assertEqual(set(SOURCE_SCOPED.clause_ids(self.rules)), {
            row["clause_id"] for row in self.policy["rules"].values()
        })
        for name, digest in self.policy["source_files"].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)
        effects, header = self.rules.feat_effects(BLOCKED_SUN["rule_id"])
        self.assertEqual(header["id"], BLOCKED_SUN["rule_id"])
        self.assertEqual(
            SOURCE_SCOPED._candidate_ids(self.rules, effects[0]["grant_ability"]),
            BLOCKED_SUN["candidates"],
        )
        self.assertNotIn(BLOCKED_SUN["rule_id"], self.policy["rules"])
        with self.assertRaisesRegex(ValueError, "explicit selected-source identity"):
            GRANTS.ability_grant(self.rules, effects[0], BLOCKED_SUN["rule_id"])

    def test_all_twelve_register_exact_native_identity_once_and_remove_cleanly(self):
        for case in self.cases:
            with self.subTest(clause=case["clause_id"]):
                engine, actor = self.fixture(case["rule_id"])
                self.assertEqual(items.register_feats(engine, actor), 1)
                source = self.source(actor, case["rule_id"])
                row = actor.spec[GRANTS.KEY]["sources"][source]
                self.assertEqual(row["grants"], {"abilities": [case["ability_title"]]})
                self.assertEqual(
                    (row["kind"], row["owner_id"], row["lifetime"], row["rule_id"]),
                    ("feature", actor.entity_id, "while_owned", case["rule_id"]),
                )
                self.assertEqual(actor.abilities, [case["ability_title"]])
                self.assertEqual(GRANTS.effective(actor, "abilities"), [case["ability_title"]])
                self.assertEqual(ABILITIES.known(actor), [case["ability_id"]])
                self.assertIn(case["ability_title"], actor.spec[GRANTS.KEY]["ability_receipts"])
                self.assertTrue(self.rules.ability_effects[case["ability_title"]])
                before = deepcopy((actor.spec, actor.abilities, actor.modifiers, actor.registry, actor.ability_triggers))
                self.assertEqual(items.register_feats(engine, actor), 0)
                self.assertEqual((actor.spec, actor.abilities, actor.modifiers, actor.registry, actor.ability_triggers), before)
                GRANTS.revoke(actor, source, engine=engine)
                self.assertNotIn(source, actor.spec[GRANTS.KEY]["sources"])
                self.assertNotIn(case["ability_title"], actor.abilities)
                self.assertNotIn(case["ability_title"], actor.spec[GRANTS.KEY]["ability_receipts"])
                self.assertTrue(engine.validate_state()["valid"])

    def test_all_twelve_survive_snapshot_and_json_restore_then_follow_owner_loss(self):
        for case in self.cases:
            with self.subTest(clause=case["clause_id"]):
                engine, actor = self.fixture(case["rule_id"])
                items.register_feats(engine, actor)
                source = self.source(actor, case["rule_id"])
                engine.gm.snapshot("fixed-source-ability")
                GRANTS.revoke(actor, source, engine=engine)
                self.assertNotIn(case["ability_title"], actor.abilities)
                engine.gm.restore("fixed-source-ability", reason="restore exact fixed Ability source")
                self.assertEqual(actor.abilities, [case["ability_title"]])
                restored = load_engine(
                    self.rules,
                    json.loads(json.dumps(dump_engine(engine), ensure_ascii=False)),
                )
                copy = restored.everyone[0]
                self.assertEqual(ABILITIES.known(copy), [case["ability_id"]])
                self.assertIn(source, copy.spec[GRANTS.KEY]["sources"])
                GRANTS.revoke(copy, source, engine=restored)
                self.assertNotIn(source, copy.spec[GRANTS.KEY]["sources"])
                self.assertNotIn(case["ability_title"], copy.abilities)

    def test_report_collect_shadow_adds_exactly_twelve_denominator_clauses(self):
        targets = {case["clause_id"] for case in self.cases}
        with tempfile.TemporaryDirectory(prefix="fixed-ability-report-") as tmp:
            shadow = Path(tmp)
            plan_path = ROOT / "data/verification/category2-edge-work-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            # Rebase only this shadow fixture; original ledger and proof bytes stay unchanged.
            historical_log = r"C:\Users\admin\Documents\ChatGPT\trpg-rulebook-structuring\work\reuse-partials\resume-core-1257\dementia-printed-band-repair\execution\union-03.log"
            fixture_log = "data/verification/fixture-inputs/dementia-printed-band/union-03.log"
            for route in plan["post_foundation_reuse"]["itemized_audit"]["routes"].values():
                for proof in route["evidence"]:
                    if proof["log"] == historical_log:
                        self.assertEqual(hashlib.sha256((ROOT / fixture_log).read_bytes()).hexdigest(), proof["sha256"])
                        proof["log"] = fixture_log
            files = {p for p in (ROOT / "input").rglob("*") if p.is_file()}
            files.update(ROOT / "data/verification" / name for _, name, _ in PROGRESS_SOURCES)
            files.add(ROOT / "data/verification/category2-scope-freeze.json")
            files.update(ROOT / proof["log"] for route in plan["post_foundation_reuse"]["itemized_audit"]["routes"].values()
                         for proof in route["evidence"])
            for source in sorted(files):
                target = shadow / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(source, target)
                except OSError:
                    target.write_bytes(source.read_bytes())

            (shadow / plan_path.relative_to(ROOT)).write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            paths = {
                "classes": ("category2-class-clause-status.json", "entries", "source_clause_id"),
                "optional": ("category2-optional-clause-status.json", "rows", "clause_id"),
                "additional": ("category2-optional-additional-clause-status.json", "rows", "clause_id"),
            }
            registries = {}
            found = set()
            for filename, key, identity_key in paths.values():
                path = shadow / "data/verification" / filename
                path.unlink()
                doc = json.loads((ROOT / "data/verification" / filename).read_text(encoding="utf-8"))
                for row in doc[key]:
                    identity = row.get(identity_key)
                    if identity in targets:
                        if identity_key == "source_clause_id":
                            self.assertTrue(row["include_category2"])
                        else:
                            self.assertTrue(row["category2_in_scope"])
                        row["status"] = "incomplete"
                        found.add(identity)
                registries[path] = (doc, key, identity_key)
                path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertEqual(found, targets)
            # The old incomplete state belongs to the fixture, never the current ledger.
            before = collect_category2(shadow)
            self.assertEqual(before["validation_errors"], [])
            self.assertTrue(before["denominator_frozen"])
            self.assertEqual(before["denominator"], 2352)
            for path, (doc, key, identity_key) in registries.items():
                for row in doc[key]:
                    if row[identity_key] in targets: row["status"] = "implemented"
                path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            after = collect_category2(shadow)
        self.assertEqual(after["validation_errors"], [])
        self.assertEqual(after["denominator"], before["denominator"])
        self.assertEqual(after["included_clause_ids"], before["included_clause_ids"])
        self.assertEqual(after["completed_clause_count"] - before["completed_clause_count"], 12)

    def test_unreviewed_source_or_mutated_runtime_effect_fails_closed(self):
        rule_id, row = next(iter(self.policy["rules"].items()))
        effect = deepcopy(row["expected_effects"][0])
        self.assertIsNone(SOURCE_SCOPED.resolve(self.rules, effect, "feat/not-reviewed"))
        mutated = dict(effect, target="your pokemon")
        with self.assertRaisesRegex(ValueError, "runtime target changed"):
            SOURCE_SCOPED.resolve(self.rules, mutated, rule_id)


if __name__ == "__main__":
    unittest.main()

