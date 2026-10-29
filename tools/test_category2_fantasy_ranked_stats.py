"""Already-counted Fantasy ranked Features: exact +Speed stat consumers.

These fixtures describe approved current acquired ownership. They do not
authorize acquisition, retraining, or an individual learned Move's execution.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from builder import build_trainer
from engine import Rules, Engine, Combatant
from state_codec import dump_engine, load_engine
import class_move_grants as MOVES
import items
import state_fields as FIELDS
import state_grants as GRANTS
import static_feature_state_grants as STATIC

SOURCES = {
    "FAN-140": ("feat/스톰-위자드", [1074, 1088],
                [["차지빔", "스파크"], ["충전", "괴전파"], ["번개", "전기자석파"]]),
    "FAN-158": ("feat/휘몰아치는-바람", [1231, 1244],
                [["제비반환", "에어커터"], ["바람일으키기", "안개제거"], ["폭풍", "따라하기"]]),
    "FAN-216": ("feat/해류의-부름", [1701, 1713],
                [["아쿠아제트", "아쿠아링"], ["물의파동", "거품광선"], ["파도타기", "비바라기"]]),
}


class FantasyRankedStatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="all")
        cls.tables = MOVES._ranked_tables(cls.rules)

    def fixture(self, cid, rank=1):
        uid, _, pairs = SOURCES[cid]
        parent = self.tables[uid]["parent"]
        spec = build_trainer(self.rules, "fantasy-rank-stat", 30,
                             dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
                             moves=[], abilities=[])
        spec.update(classes=[], edges=[], feats=[parent, uid],
                    feat_ranks={uid: rank},
                    skills={"곡예": 6, "집중": 6, "통찰": 6, "육상": 6},
                    feature_choices={uid: deepcopy(pairs[:rank])})
        actor = Combatant(self.rules, spec)
        engine = Engine(self.rules, seed=1225)
        engine.everyone = engine.gm.everyone = [actor]
        return engine, actor

    @staticmethod
    def source(actor, cid):
        return "feature:" + actor.entity_id + ":" + SOURCES[cid][0]

    @staticmethod
    def rank(actor, cid, rank):
        uid, _, pairs = SOURCES[cid]
        actor.spec["feat_ranks"][uid] = rank
        actor.spec["feature_choices"][uid] = deepcopy(pairs[:rank])

    @staticmethod
    def state(engine, actor):
        return deepcopy((actor.spec, actor.stats, actor.moves, actor.abilities,
                         actor.hp, actor.move_uses, engine.rng.getstate(), engine.log_lines))

    def assert_projection(self, actor, cid, rank, *, baseline=10, independent=0):
        uid, _, pairs = SOURCES[cid]
        self.assertEqual(actor.spec["stats"]["spe"], baseline)
        self.assertEqual(actor.stats["spe"], baseline + rank + independent)
        source = self.source(actor, cid)
        row = actor.spec[GRANTS.KEY]["sources"][source]
        self.assertEqual((row["owner_id"], row["rule_id"], row["lifetime"], row["clause_id"]),
                         (actor.entity_id, uid, "while_owned", cid))
        expected = [[actor.r.move_id(name) for name in pair] for pair in pairs[:rank]]
        self.assertEqual(row["class_move_selection"], expected)
        self.assertCountEqual(row["grants"]["moves"], sum(expected, []))
        self.assertTrue(set(sum(expected, [])).issubset(actor.moves))
        self.assertEqual(actor.spec[GRANTS.KEY]["stat_sources"]["spe"]["sources"][source],
                         {"feature_count": {"delta": rank, "minimum": None}})
        self.assertTrue(STATIC.validate(actor))

    def test_exact_three_source_rows_reuse_printed_speed_rank_and_existing_move_contract(self):
        policy = STATIC._policy(self.rules)
        self.assertEqual(len(policy["rules"]), 43)
        source = ROOT / "input/supp-fantasy.md"
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         "a51f5d6592bc1ff12b380f47398db93426b53c58c210810f5041b29eb64b2266")
        lines = source.read_text(encoding="utf-8").splitlines()
        for cid, (uid, bounds, _) in SOURCES.items():
            with self.subTest(source=cid):
                row = policy["rules"][cid]
                self.assertEqual((row["id"], row["owner_id"], row["mode"], row["stat"], row["tag"]),
                                 (cid, uid, "ranked_stat", "spe", "+스피드"))
                text = "\n".join(lines[bounds[0]-1:bounds[1]])
                self.assertEqual((row["lines"], row["excerpt"]), (bounds, text))
                self.assertEqual(row["excerpt_sha256"], hashlib.sha256(text.encode()).hexdigest())
                self.assertEqual(row["excerpt_sha256"], self.tables[uid]["excerpt_sha256"])
        self.assertEqual(self.tables[SOURCES["FAN-140"][0]]["minimum_skill_rank"], [0, 5, 6])
        self.assertEqual(self.tables[SOURCES["FAN-158"][0]]["skills"], ["곡예", "통찰"])
        self.assertEqual(self.tables[SOURCES["FAN-216"][0]]["minimum_skill_rank"], [0, 4, 5])
        self.assertNotIn("항상", policy["rules"]["FAN-216"]["excerpt"])

    def test_all_sources_rank_one_two_three_and_repeated_registration_share_move_stat_source(self):
        for cid, (uid, _, _) in SOURCES.items():
            with self.subTest(source=cid):
                engine, actor = self.fixture(cid)
                other_stats = {k: v for k, v in actor.stats.items() if k != "spe"}
                for rank in (1, 2, 3):
                    self.rank(actor, cid, rank)
                    # Exercise the printed alternate skill at its exact threshold.
                    table = self.tables[uid]
                    actor.spec["skills"] = {table["skills"][-1]: max(1, table["minimum_skill_rank"][rank-1])}
                    items.register_feats(engine, actor)
                    self.assert_projection(actor, cid, rank)
                    self.assertEqual({k: v for k, v in actor.stats.items() if k != "spe"}, other_stats)
                    # Existing unimplemented parent Effects may repeat an
                    # informational log; idempotence concerns gameplay state.
                    before = self.state(engine, actor)[:-1]
                    items.register_feats(engine, actor)
                    self.assertEqual(self.state(engine, actor)[:-1], before)

    def test_rank_reduction_and_removal_preserve_base_growth_independent_speed_and_move(self):
        for cid, (uid, _, pairs) in SOURCES.items():
            with self.subTest(source=cid):
                engine, actor = self.fixture(cid, 3)
                baseline_move = self.rules.move_id(pairs[0][0])
                GRANTS.set_baseline(actor, "moves", [baseline_move])
                separate = "gm/independent-speed"
                GRANTS._source(actor, separate, "gm", owner_id=actor.entity_id,
                               lifetime="permanent", rule_id="gm/observed-stat", tutor_points=0)
                GRANTS.stat(actor, "spe", 2, separate)
                proposed = dict(actor.spec["stats"], spe=12)
                FIELDS.base_patch(actor, {"stats": proposed}, source="gm/state",
                                  reason="approved baseline growth")
                for rank in (3, 2, 1):
                    self.rank(actor, cid, rank)
                    items.register_feats(engine, actor)
                    self.assert_projection(actor, cid, rank, baseline=12, independent=2)
                actor.spec["feats"].remove(uid)
                actor.spec["feat_ranks"].pop(uid)
                actor.spec["feature_choices"].pop(uid)
                items.register_feats(engine, actor)
                self.assertEqual(actor.stats["spe"], 14)
                self.assertNotIn(self.source(actor, cid), actor.spec[GRANTS.KEY]["sources"])
                self.assertEqual(actor.moves, [baseline_move])
                GRANTS.revoke(actor, separate, engine=engine)
                self.assertEqual(actor.stats["spe"], 12)
                self.assertTrue(engine.validate_state()["valid"])

    def test_all_sources_gm_and_fresh_rules_restore_exact_speed_and_move_receipts(self):
        for cid in SOURCES:
            with self.subTest(source=cid):
                engine, actor = self.fixture(cid, 3)
                items.register_feats(engine, actor)
                expected = deepcopy((actor.stats, actor.spec[GRANTS.KEY], actor.moves))
                engine.gm.snapshot("fantasy-ranked-speed")
                self.rank(actor, cid, 1)
                items.register_feats(engine, actor)
                self.assert_projection(actor, cid, 1)
                engine.gm.restore("fantasy-ranked-speed", reason="restore approved ranked state")
                self.assertEqual((actor.stats, actor.spec[GRANTS.KEY], actor.moves), expected)
                payload = json.loads(json.dumps(dump_engine(engine), ensure_ascii=False))
                restored = load_engine(Rules(str(ROOT), ruleset="all"), payload)
                copy = restored.everyone[0]
                self.assertEqual((copy.stats, copy.spec[GRANTS.KEY], copy.moves), expected)
                self.assert_projection(copy, cid, 3)
                before = self.state(restored, copy)[:-1]
                items.register_feats(restored, copy)
                self.assertEqual(self.state(restored, copy)[:-1], before)
                self.assertTrue(restored.validate_state()["valid"])

    def test_actual_native_initiative_reads_each_sources_reconciled_speed(self):
        for cid in SOURCES:
            with self.subTest(source=cid):
                engine, actor = self.fixture(cid)
                self.assertEqual(engine.initiative_value(actor).value, 10)
                for rank in (1, 3, 2):
                    self.rank(actor, cid, rank)
                    items.register_feats(engine, actor)
                    self.assertEqual(actor.staged("spe"), 10 + rank)
                    result = engine.initiative_value(actor)
                    self.assertEqual(result.value, 10 + rank)
                    self.assertEqual(result.unresolved, ())
                    self.assertEqual(result.derivation["speed_actor_id"], actor.entity_id)

    def test_rank_skill_parent_and_move_failure_leave_speed_receipts_and_rng_unchanged(self):
        for cid, (uid, _, pairs) in SOURCES.items():
            for defect in ("skill", "parent", "rank", "move"):
                with self.subTest(source=cid, defect=defect):
                    engine, actor = self.fixture(cid)
                    items.register_feats(engine, actor)
                    self.rank(actor, cid, 2)
                    table = self.tables[uid]
                    if defect == "skill":
                        actor.spec["skills"] = {key: table["minimum_skill_rank"][1]-1 for key in table["skills"]}
                    elif defect == "parent":
                        actor.spec["feats"].remove(table["parent"])
                    elif defect == "rank":
                        actor.spec["feat_ranks"][uid] = 4
                    else:
                        actor.spec["feature_choices"][uid][1] = [pairs[0][0], "맹독"]
                    before = self.state(engine, actor)
                    with self.assertRaises(ValueError):
                        items.register_feats(engine, actor)
                    self.assertEqual(self.state(engine, actor), before)
        # Insight is printed; Intuition never substitutes for it.
        engine, actor = self.fixture("FAN-158", 2)
        actor.spec["skills"] = {"직감": 6}
        before = self.state(engine, actor)
        with self.assertRaises(ValueError):
            items.register_feats(engine, actor)
        self.assertEqual(self.state(engine, actor), before)


if __name__ == "__main__":
    unittest.main()
