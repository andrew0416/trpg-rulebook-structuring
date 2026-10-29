"""Actual acquired Martial Artist rank/stat projections; no acquisition approval.

The fixture starts with a native authenticated class acquisition. Later sheet
changes describe already-approved current ownership, not retraining semantics.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from engine import Rules, Engine, Combatant
from builder import build_trainer
from state_codec import dump_engine, load_engine
import acquired_features as ACQUIRED
import items
import state_fields as FIELDS
import state_grants as GRANTS
import static_feature_state_grants as STATIC
import trainer_feature_acquisition as ACQUISITION
from test_category2_martial_acquisition_exact import STYLE_CASES

CID = "C2CSV/input/db/feats.csv:R404:main"
STATS = ("hp", "atk", "def", "spa", "spd", "spe")
STYLE_STATS = {
    "ability/근성": "hp", "ability/정신력": "spe", "ability/철주먹": "def",
    "ability/유연": "spe", "ability/이판사판": "atk", "ability/테크니션": "spe",
}


class AcquiredStatTagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")

    def fixture(self, ability="ability/근성", *, before_acquire=None):
        engine = Engine(self.rules, seed=1223)
        spec = build_trainer(self.rules, "rank-stat-owner", 30,
                             dict.fromkeys(STATS, 10), moves=[], abilities=[])
        spec.update(classes=[], feats=[], edges=["edge/기본-무술"],
                    skills={"전투": 6}, feature_choices={})
        actor = Combatant(self.rules, spec)
        engine.everyone = engine.gm.everyone = [actor]
        if before_acquire is not None:before_acquire(engine,actor)
        ACQUISITION.acquire_martial_artist(
            engine, actor, acquisition_request_id="martial/stat-proof",
            selected_ability=ability,
            lifecycle_policy=ACQUISITION.LIFECYCLE_WHILE_OWNED)
        return engine, actor

    @staticmethod
    def ranks(actor, ability, rank):
        actor.spec["feats"] = ["feat/무술-훈련"] if rank else []
        actor.spec["feat_ranks"] = {"feat/무술-훈련": rank} if rank else {}
        actor.spec["feature_choices"] = (
            {"feat/무술-훈련": deepcopy(STYLE_CASES[ability][:rank])} if rank else {})

    @staticmethod
    def source(actor):
        return "static-feature:" + actor.entity_id + ":" + CID

    def assert_stat(self, actor, ability, count, *, baseline=10, independent=0):
        stat = STYLE_STATS[ability]
        self.assertEqual(actor.stats[stat], baseline + independent + count)
        self.assertEqual(actor.spec["stats"][stat], baseline)
        source = self.source(actor)
        owner = actor.spec[GRANTS.KEY]["sources"][source]
        self.assertEqual((owner["owner_id"], owner["rule_id"], owner["lifetime"],
                          owner["clause_id"], owner["selection"]),
                         (actor.entity_id, "class/무술가", "while_owned", CID, ability))
        receipt = actor.spec[GRANTS.KEY]["stat_sources"][stat]["sources"][source]
        self.assertEqual(receipt, {"feature_count": {"delta": count, "minimum": None}})
        self.assertTrue(STATIC.validate(actor))

    def test_six_styles_exact_stat_source_and_repeated_registration_core(self):
        for ability in STYLE_STATS:
            with self.subTest(ability=ability):
                engine, actor = self.fixture(ability)
                items.register_feats(engine, actor)
                self.assert_stat(actor, ability, 1)
                self.assertEqual({s: actor.stats[s] for s in STATS if s != STYLE_STATS[ability]},
                                 {s: 10 for s in STATS if s != STYLE_STATS[ability]})
                before = deepcopy((actor.spec, actor.stats, actor.hp, engine.rng.getstate()))
                items.register_feats(engine, actor)
                self.assertEqual((actor.spec, actor.stats, actor.hp, engine.rng.getstate()), before)

    def test_same_feature_rank_one_two_three_counts_each_rank_and_ignores_other_class(self):
        for ability in STYLE_STATS:
            with self.subTest(ability=ability):
                engine, actor = self.fixture(ability)
                for rank in (1, 2, 3):
                    self.ranks(actor, ability, rank)
                    items.register_feats(engine, actor)
                    self.assertEqual(ACQUIRED.count_for_class(actor, "class/무술가"), rank + 1)
                    self.assert_stat(actor, ability, rank + 1)
                    learned = [self.rules.move_id(name)
                               for pair in STYLE_CASES[ability][:rank] for name in pair]
                    self.assertTrue(set(learned).issubset(actor.moves))
                # An already acquired Feature in another class adds no martial tag.
                other = next(uid for uid, row in self.rules.selection.units.items()
                             if uid.startswith("feat/") and
                             "분기" not in row.get("tags", []) and
                             any(str(p).split("(", 1)[0].strip() == "텀블러"
                                 for p in row.get("source", {}).get("path", [])))
                actor.spec["feats"].append(other)
                STATIC.register_all(engine, actor)
                self.assert_stat(actor, ability, 4)

    def test_approved_current_rank_decrease_and_removal_reconcile_exact_contribution(self):
        engine, actor = self.fixture("ability/철주먹")
        for rank in (3, 2, 1, 0):
            self.ranks(actor, "ability/철주먹", rank)
            items.register_feats(engine, actor)
            self.assert_stat(actor, "ability/철주먹", rank + 1)
        self.assertEqual(actor.stats["def"], 11)
        self.assertTrue(engine.validate_state()["valid"])

    def test_independent_stat_source_and_base_growth_survive_martial_rank_change(self):
        ability = "ability/철주먹"
        engine, actor = self.fixture(ability)
        items.register_feats(engine, actor)
        source = "gm/stat/independent-defense"
        GRANTS._source(actor, source, "gm", owner_id=actor.entity_id,
                       lifetime="permanent", rule_id="gm/observed-stat", tutor_points=0)
        GRANTS.stat(actor, "def", 3, source, operation_id="approved-stat-adjustment")
        proposed = dict(actor.spec["stats"], **{"def": 12})
        FIELDS.base_patch(actor, {"stats": proposed},
                          source="gm/state", reason="approved permanent baseline growth")
        for rank in (3, 1, 0):
            self.ranks(actor, ability, rank)
            items.register_feats(engine, actor)
            self.assert_stat(actor, ability, rank + 1, baseline=12, independent=3)
        # Revoking this independent source leaves the authenticated martial tag.
        GRANTS.revoke(actor, source, engine=engine)
        self.assert_stat(actor, ability, 1, baseline=12)

    def test_guts_actual_hp_capacity_and_native_healing_damage_without_implicit_heal(self):
        before={}
        def observe(engine,actor):before.update(base=actor.base_max_hp,hp=actor.hp)
        engine, actor = self.fixture(before_acquire=observe)
        base = before['base']
        initial_hp = before['hp']
        items.register_feats(engine, actor)
        self.assert_stat(actor, "ability/근성", 1)
        one = actor.base_max_hp
        self.assertGreater(one, base)
        self.assertEqual(actor.hp, initial_hp)
        self.ranks(actor, "ability/근성", 3)
        items.register_feats(engine, actor)
        self.assert_stat(actor, "ability/근성", 4)
        self.assertEqual(actor.base_max_hp - base, 4 * (one - base))
        self.assertEqual(actor.max_hp, actor.base_max_hp)
        self.assertEqual(actor.hp, initial_hp)
        self.assertEqual(engine.heal(actor, 10000, source_kind="feature"), actor.max_hp - initial_hp)
        self.assertEqual(actor.hp, actor.max_hp)
        cap = actor.max_hp
        engine.take_damage(actor, 1)
        self.assertEqual(actor.hp, cap - 1)
        self.assertEqual(actor.injuries, 0)
        self.assertEqual(engine.heal(actor, 10000, source_kind="feature"), 1)
        self.assertEqual(actor.hp, cap)

    def test_gm_and_json_fresh_rules_restore_rank_stat_receipts_without_reapplication(self):
        engine, actor = self.fixture()
        self.ranks(actor, "ability/근성", 3)
        items.register_feats(engine, actor)
        expected = deepcopy((actor.stats, actor.spec[GRANTS.KEY], actor.base_max_hp, actor.hp))
        engine.gm.snapshot("martial-ranked-stats")
        self.ranks(actor, "ability/근성", 1)
        items.register_feats(engine, actor)
        self.assert_stat(actor, "ability/근성", 2)
        engine.gm.restore("martial-ranked-stats", reason="restore approved rank projection")
        self.assertEqual((actor.stats, actor.spec[GRANTS.KEY], actor.base_max_hp, actor.hp), expected)
        self.assert_stat(actor, "ability/근성", 4)
        payload = json.loads(json.dumps(dump_engine(engine), ensure_ascii=False))
        fresh = Rules(str(ROOT), ruleset="core")
        restored = load_engine(fresh, payload)
        copy = restored.everyone[0]
        self.assertEqual((copy.stats, copy.spec[GRANTS.KEY], copy.base_max_hp, copy.hp), expected)
        self.assert_stat(copy, "ability/근성", 4)
        before = deepcopy((copy.spec, copy.stats, restored.rng.getstate()))
        items.register_feats(restored, copy)
        self.assertEqual((copy.spec, copy.stats, restored.rng.getstate()), before)
        self.assertTrue(restored.validate_state()["valid"])

    def test_missing_receipt_withdrawn_ability_and_invalid_rank_refuse_before_mutation(self):
        for invalid in ("missing-receipt", "withdrawn-ability", "rank-over-maximum"):
            with self.subTest(invalid=invalid):
                engine, actor = self.fixture("ability/철주먹")
                self.ranks(actor, "ability/철주먹", 1)
                items.register_feats(engine, actor)
                if invalid == "missing-receipt":
                    actor.spec[ACQUISITION.LEDGER_KEY].clear()
                elif invalid == "withdrawn-ability":
                    GRANTS.revoke(actor, ACQUISITION.martial_ability_source(actor), engine=engine)
                else:
                    actor.spec["feat_ranks"]["feat/무술-훈련"] = 4
                before = deepcopy((actor.spec, actor.stats, actor.moves, actor.abilities,
                                   actor.hp, engine.rng.getstate(), engine.log_lines))
                with self.assertRaises(ValueError):
                    items.register_feats(engine, actor)
                self.assertEqual((actor.spec, actor.stats, actor.moves, actor.abilities,
                                  actor.hp, engine.rng.getstate(), engine.log_lines), before)

    def test_tampered_martial_stat_count_is_rejected_on_validation_and_cold_load(self):
        engine, actor = self.fixture("ability/철주먹")
        self.ranks(actor, "ability/철주먹", 2)
        items.register_feats(engine, actor)
        payload = json.loads(json.dumps(dump_engine(engine), ensure_ascii=False))
        row = actor.spec[GRANTS.KEY]["stat_sources"]["def"]
        row["sources"][self.source(actor)]["feature_count"]["delta"] = 9
        with self.assertRaises(ValueError):
            STATIC.validate(actor)
        # Alter the saved exact source receipt while retaining the real count.
        changed = False
        for node in payload["nodes"].values():
            if node["kind"] != "dict":
                continue
            for key, value in node["items"]:
                if key == "feature_count":
                    operation = payload["nodes"][value["$ref"]]["items"]
                    self.assertEqual(dict(operation), {"delta": 3, "minimum": None})
                    next(pair for pair in operation if pair[0] == "delta")[1] = 9
                    changed = True
        self.assertTrue(changed)
        with self.assertRaises(ValueError):
            load_engine(self.rules, payload)


ATHLETIC_CID = "input/ch04-trainer-classes.md:2247-2253"
ATHLETIC_UID = "feat/육상-기술"
ATHLETIC_PAIRS = [["조이기", "블록"], ["누르기", "돌진"], ["메가톤킥", "객기"]]


class AthleticStatTagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")

    def fixture(self, rank=1):
        engine = Engine(self.rules, seed=1223)
        spec = build_trainer(self.rules, "athletic-stat-owner", 30,
                             dict.fromkeys(STATS, 10), moves=[], abilities=[])
        spec.update(classes=["class/운동선수"], feats=[], edges=[],
                    skills={"육상": 6}, feature_choices={})
        actor = Combatant(self.rules, spec)
        engine.everyone = engine.gm.everyone = [actor]
        self.rank(actor, rank)
        return engine, actor

    @staticmethod
    def rank(actor, rank):
        actor.spec["feats"] = [ATHLETIC_UID] if rank else []
        actor.spec["feat_ranks"] = {ATHLETIC_UID: rank} if rank else {}
        actor.spec["feature_choices"] = (
            {ATHLETIC_UID: deepcopy(ATHLETIC_PAIRS[:rank])} if rank else {})

    @staticmethod
    def source(actor):
        return "feature:" + actor.entity_id + ":" + ATHLETIC_UID

    def assert_hp_tag(self, actor, rank, independent=0):
        self.assertEqual(actor.stats["hp"], actor.spec["stats"]["hp"] + rank + independent)
        source = self.source(actor)
        self.assertEqual(actor.spec[GRANTS.KEY]["stat_sources"]["hp"]["sources"][source],
                         {"feature_count": {"delta": rank, "minimum": None}})
        row = actor.spec[GRANTS.KEY]["sources"][source]
        self.assertEqual((row["clause_id"], row["owner_id"], row["lifetime"]),
                         (ATHLETIC_CID, actor.entity_id, "while_owned"))
        expected = [actor.r.move_id(name) for pair in ATHLETIC_PAIRS[:rank] for name in pair]
        self.assertTrue(set(expected).issubset(actor.moves))
        self.assertTrue(STATIC.validate(actor))

    def test_athletic_same_rank_hp_and_exact_move_pairs_share_one_source_without_duplicate(self):
        engine, actor = self.fixture()
        initial_hp, initial_cap = actor.hp, actor.base_max_hp
        for rank in (1, 2, 3):
            self.rank(actor, rank)
            items.register_feats(engine, actor)
            self.assert_hp_tag(actor, rank)
            self.assertEqual(actor.hp, initial_hp)
            self.assertGreater(actor.base_max_hp, initial_cap)
            before = deepcopy((actor.spec, actor.stats, actor.moves, engine.rng.getstate()))
            items.register_feats(engine, actor)
            self.assertEqual((actor.spec, actor.stats, actor.moves, engine.rng.getstate()), before)
        self.assertEqual(engine.heal(actor, 10000, source_kind="feature"), actor.max_hp - initial_hp)
        self.assertEqual(actor.hp, actor.max_hp)

    def test_athletic_removal_preserves_independent_hp_and_baseline_move(self):
        engine, actor = self.fixture(3)
        GRANTS.set_baseline(actor, "moves", [self.rules.move_id("조이기")])
        independent = "gm/independent-athletic-hp"
        GRANTS._source(actor, independent, "gm", owner_id=actor.entity_id,
                       lifetime="permanent", rule_id="gm/observed-stat", tutor_points=0)
        GRANTS.stat(actor, "hp", 2, independent)
        items.register_feats(engine, actor)
        self.assert_hp_tag(actor, 3, 2)
        self.rank(actor, 1)
        items.register_feats(engine, actor)
        self.assert_hp_tag(actor, 1, 2)
        self.rank(actor, 0)
        items.register_feats(engine, actor)
        self.assertEqual(actor.stats["hp"], actor.spec["stats"]["hp"] + 2)
        self.assertNotIn(self.source(actor), actor.spec[GRANTS.KEY]["sources"])
        self.assertIn(self.rules.move_id("조이기"), actor.moves)
        self.assertNotIn(self.rules.move_id("블록"), actor.moves)
        GRANTS.revoke(actor, independent, engine=engine)
        self.assertEqual(actor.stats["hp"], actor.spec["stats"]["hp"])
        self.assertTrue(engine.validate_state()["valid"])

    def test_athletic_hp_move_receipts_restore_gm_and_fresh_rules(self):
        engine, actor = self.fixture(3)
        items.register_feats(engine, actor)
        expected = deepcopy((actor.stats, actor.spec[GRANTS.KEY], actor.moves, actor.base_max_hp))
        engine.gm.snapshot("athletic-ranked-hp")
        self.rank(actor, 1)
        items.register_feats(engine, actor)
        engine.gm.restore("athletic-ranked-hp", reason="restore approved Athletic rank state")
        self.assertEqual((actor.stats, actor.spec[GRANTS.KEY], actor.moves, actor.base_max_hp), expected)
        payload = json.loads(json.dumps(dump_engine(engine), ensure_ascii=False))
        restored = load_engine(Rules(str(ROOT), ruleset="core"), payload)
        copy = restored.everyone[0]
        self.assertEqual((copy.stats, copy.spec[GRANTS.KEY], copy.moves, copy.base_max_hp), expected)
        self.assert_hp_tag(copy, 3)
        before = deepcopy((copy.spec, copy.stats, restored.rng.getstate()))
        items.register_feats(restored, copy)
        self.assertEqual((copy.spec, copy.stats, restored.rng.getstate()), before)
        self.assertTrue(restored.validate_state()["valid"])

    def test_athletic_invalid_rank_or_pair_or_skill_refuses_hp_and_move_mutation(self):
        for invalid in ("rank", "pair", "skill"):
            with self.subTest(invalid=invalid):
                engine, actor = self.fixture(1)
                items.register_feats(engine, actor)
                self.rank(actor, 2)
                if invalid == "rank":
                    actor.spec["feat_ranks"][ATHLETIC_UID] = 4
                elif invalid == "pair":
                    actor.spec["feature_choices"][ATHLETIC_UID][1] = ["맹독", "괴력"]
                else:
                    actor.spec["skills"]["육상"] = 4
                before = deepcopy((actor.spec, actor.stats, actor.hp, actor.moves, engine.rng.getstate()))
                with self.assertRaises(ValueError):
                    items.register_feats(engine, actor)
                self.assertEqual((actor.spec, actor.stats, actor.hp, actor.moves, engine.rng.getstate()), before)


if __name__ == "__main__":
    unittest.main()
