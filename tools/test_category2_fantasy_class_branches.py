"""Native Fantasy class owners reuse the existing CSV branch projection."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from builder import build_trainer
from engine import Combatant, Engine, Rules
import ability_transitions as ABILITIES
import acquired_feature_projections as PROJECTIONS
import items
import state_codec as CODEC
import state_grants as GRANTS
import static_feature_state_grants as STATIC

CASES = {
    "FAN-117": ("C2CSV/input/db/feats.csv:R587:main",
                "supp-fantasy/벌레-원소술사-무리군주", "feat/거미줄-쏘는-법"),
    "FAN-166": ("C2CSV/input/db/feats.csv:R643:main",
                "supp-fantasy/풀-원소술사-드루이드", "feat/자연의-포용"),
}


class FantasyClassBranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="all")

    def fixture(self, clause, branch):
        cid, owner, _ = CASES[clause]
        spec = build_trainer(
            self.rules, "branch-owner", 30,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
            moves=[], abilities=[], extra={
                "classes": [], "edges": [], "feats": [owner],
                "static_feature_choices": {owner: branch}, "feature_choices": {},
            },
        )
        actor = Combatant(self.rules, spec)
        engine = Engine(self.rules, seed=1192)
        engine.everyone = engine.gm.everyone = [actor]
        return engine, actor, STATIC.rules(self.rules)[cid]

    def test_five_branches_use_native_registration_and_ranked_class_stat_counts(self):
        branches = 0
        for clause, (cid, owner, child) in CASES.items():
            for branch, result in STATIC.rules(self.rules)[cid]["branches"].items():
                with self.subTest(clause=clause, branch=branch):
                    engine, actor, _ = self.fixture(clause, branch)
                    self.assertEqual(STATIC.identity(self.rules, owner), cid)
                    self.assertEqual(items.register_feats(engine, actor), 1)
                    self.assertEqual(STATIC.class_branch(actor, owner), branch)
                    self.assertEqual(actor.stats[result["stat"]], 11)
                    self.assertEqual(ABILITIES.known(actor), [result["abilities"][0]["id"]])
                    self.assertEqual(items.register_feats(engine, actor), 0)
                    actor.spec["feats"].append(child)
                    rank = 3 if clause == "FAN-166" else 1
                    actor.spec["feat_ranks"] = {child: rank}
                    STATIC.register_all(engine, actor)
                    self.assertEqual(actor.stats[result["stat"]], 11 + rank)
                    actor.spec["feat_ranks"][child] = 1
                    STATIC.register_all(engine, actor)
                    self.assertEqual(actor.stats[result["stat"]], 12)
                    actor.spec["feats"].remove(child)
                    STATIC.register_all(engine, actor)
                    self.assertEqual(actor.stats[result["stat"]], 11)
                    STATIC.validate(actor)
                    actor.spec["feats"].remove(owner)
                    STATIC.register_all(engine, actor)
                    self.assertEqual(actor.stats[result["stat"]], 10)
                    self.assertEqual(ABILITIES.known(actor), [])
                    self.assertIsNone(STATIC.class_branch(actor, owner))
                    branches += 1
        self.assertEqual(branches, 5)

    def test_gm_and_json_restore_preserve_branch_and_independent_ability_baseline(self):
        for clause, branch in (("FAN-117", "거미의 포용"), ("FAN-166", "꽃의 맹약")):
            with self.subTest(clause=clause):
                cid, owner, _ = CASES[clause]
                result = STATIC.rules(self.rules)[cid]["branches"][branch]
                engine, actor, _ = self.fixture(clause, branch)
                GRANTS.set_baseline(actor, "abilities", [result["abilities"][0]["title"]])
                items.register_feats(engine, actor)
                engine.gm.snapshot("class-branch")
                actor.hp -= 1
                engine.gm.restore("class-branch", reason="restore class branch")
                restored = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(engine))))
                copy = restored.everyone[0]
                self.assertEqual(STATIC.class_branch(copy, owner), branch)
                self.assertEqual(copy.stats[result["stat"]], 11)
                copy.spec["feats"].remove(owner)
                items.register_feats(restored, copy)
                self.assertEqual(copy.stats[result["stat"]], 10)
                self.assertEqual(ABILITIES.known(copy), [result["abilities"][0]["id"]])

    def test_owned_parent_drives_broodlord_without_a_second_choice(self):
        for branch in ("거미의 포용", "군주의 포용"):
            with self.subTest(branch=branch):
                engine, actor, _ = self.fixture("FAN-117", branch)
                actor.spec["feats"].append("feat/무리어미")
                expected = PROJECTIONS.plan(engine, actor, "feat/무리어미")
                items.register_feats(engine, actor)
                self.assertEqual(expected["selection"], [branch])
                self.assertTrue(set(expected["ability_ids"]).issubset(ABILITIES.known(actor)))
                stat = "atk" if branch == "거미의 포용" else "spa"
                self.assertEqual(actor.stats[stat], 12)

    def test_conflicting_descendant_or_replacement_choice_cannot_mutate_state(self):
        engine, actor, _ = self.fixture("FAN-117", "거미의 포용")
        items.register_feats(engine, actor)
        actor.spec["feats"].append("feat/무리어미")
        actor.spec["feature_choices"] = {CASES["FAN-117"][1]: "군주의 포용"}
        before = deepcopy((actor.spec, actor.stats, actor.abilities, engine.rng.getstate()))
        with self.assertRaisesRegex(ValueError, "disagrees"):
            PROJECTIONS.register_all(engine, actor)
        self.assertEqual((actor.spec, actor.stats, actor.abilities, engine.rng.getstate()), before)
        actor.spec["feature_choices"] = {}
        actor.spec["feats"].remove("feat/무리어미")
        actor.spec["static_feature_choices"][CASES["FAN-117"][1]] = "군주의 포용"
        before = deepcopy((actor.spec, actor.stats, actor.abilities))
        with self.assertRaises(ValueError):
            STATIC.register_all(engine, actor)
        self.assertEqual((actor.spec, actor.stats, actor.abilities), before)
        with self.assertRaisesRegex(ValueError, "silently replaced"):
            STATIC.class_branch(actor, CASES["FAN-117"][1])

    def test_missing_invalid_and_duplicate_owner_choices_fail_before_registration(self):
        for clause in CASES:
            cid, owner, _ = CASES[clause]
            branch = next(iter(STATIC.rules(self.rules)[cid]["branches"]))
            for error in ("missing", "invalid", "duplicate"):
                with self.subTest(clause=clause, error=error):
                    engine, actor, _ = self.fixture(clause, branch)
                    if error == "missing":
                        actor.spec["static_feature_choices"] = {}
                    elif error == "invalid":
                        actor.spec["static_feature_choices"][owner] = "unprinted branch"
                    else:
                        actor.spec["feats"].append(cid)
                    before = deepcopy((actor.spec, actor.stats, actor.abilities))
                    with self.assertRaises(ValueError):
                        items.register_feats(engine, actor)
                    self.assertEqual((actor.spec, actor.stats, actor.abilities), before)

    def test_two_source_bindings_are_hash_pinned_inside_the_existing_37_contracts(self):
        policy = json.loads((Path(self.rules.root) / STATIC.POLICY_PATH).read_text(encoding="utf-8"))
        self.assertEqual(len(policy["rules"]), 37)
        for clause, (cid, owner, _) in CASES.items():
            self.assertEqual(policy["rules"][cid]["equivalent_sources"][clause]["owner_id"], owner)
        policy["rules"][CASES["FAN-117"][0]]["equivalent_sources"]["FAN-117"]["excerpt_sha256"] = "0" * 64
        with TemporaryDirectory() as temp:
            path = Path(temp) / "policy.json"
            path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
            rules = Rules(str(ROOT), ruleset="all")
            with patch.object(STATIC, "_path", return_value=path):
                with self.assertRaisesRegex(ValueError, "equivalent Static Feature source changed"):
                    STATIC.rules(rules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
