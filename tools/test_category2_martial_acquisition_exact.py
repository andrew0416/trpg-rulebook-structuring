"""Exact Martial Artist Ability acquisition and three move-table consumers."""
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
from ruleset import ExcludedRuleSelection
from state_codec import dump_engine, load_engine
from tools.report_category2_progress import collect as collect_category2
import ability_transitions as ABILITIES
import class_move_grants as MOVES
import items
import state_grants as GRANTS
import trainer_feature_acquisition as ACQUISITION


TABLES = {
    "input/ch04-trainer-classes.md:2414-2426": "a656dc81ac5ea9519da4bd5697c6e769727a9482ca9ac8b8850f0421f3e9d707",
    "input/ch04-trainer-classes.md:2428-2439": "75ed72b13e736873ac11bd7528a6cde2452b267e5a39b9f848d95754c5c90128",
    "input/ch04-trainer-classes.md:2441-2450": "851b00e31d1e54b8b2a480f8bdb7c0f97c33893d3b707e90df7713445f62899e",
}
RANGES = ((2414, 2426), (2428, 2439), (2441, 2450))
EXPECTED_RANKS = {
    1: ("경혈찌르기", "손바닥치기", "두번차기", "기충전", "태권당수", "로킥", "마하펀치", "돌려차기", "받아던지기"),
    2: ("깨트리기", "배대뒤치기", "연속펀치", "카운터", "안다리걸기", "점프킥", "파워트릭", "패스트가드"),
    3: ("크로스촙", "인파이트", "트리플킥", "무릎차기", "스카이어퍼", "업어후리기"),
}
STYLE_CASES = {
    "ability/근성": [["받아던지기", "두번차기"], ["배대뒤치기", "깨트리기"], ["업어후리기", "인파이트"]],
    "ability/정신력": [["태권당수", "두번차기"], ["안다리걸기", "깨트리기"], ["크로스촙", "인파이트"]],
    "ability/철주먹": [["마하펀치", "두번차기"], ["연속펀치", "깨트리기"], ["스카이어퍼", "인파이트"]],
    "ability/유연": [["경혈찌르기", "두번차기"], ["카운터", "파워트릭"], ["인파이트", "로킥"]],
    "ability/이판사판": [["돌려차기", "두번차기"], ["점프킥", "깨트리기"], ["무릎차기", "인파이트"]],
    "ability/테크니션": [["손바닥치기", "두번차기"], ["패스트가드", "깨트리기"], ["트리플킥", "인파이트"]],
}


class MartialArtistAcquisitionExactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")

    def fixture(self, *, edge=True, combat=6, name="martial-owner"):
        engine = Engine(self.rules, seed=2414)
        spec = build_trainer(
            self.rules,
            name,
            30,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
            moves=[],
        )
        spec.update(
            skills={"전투": combat},
            classes=[],
            feats=[],
            edges=["edge/기본-무술"] if edge else [],
            abilities=[],
            feature_choices={},
        )
        actor = Combatant(self.rules, spec)
        engine.everyone = engine.gm.everyone = [actor]
        return engine, actor

    def acquire(self, engine, actor, ability, request="martial/acquire"):
        return ACQUISITION.acquire_martial_artist(
            engine,
            actor,
            acquisition_request_id=request,
            selected_ability=ability,
            lifecycle_policy=ACQUISITION.LIFECYCLE_WHILE_OWNED,
        )

    @staticmethod
    def select_moves(actor, choices):
        actor.spec["feats"] = ["feat/무술-훈련"]
        actor.spec["feat_ranks"] = {"feat/무술-훈련": len(choices)}
        actor.spec["feature_choices"] = {"feat/무술-훈련": deepcopy(choices)}

    def test_exact_sources_tables_and_source_scoped_core_identities(self):
        source = ROOT / "input/ch04-trainer-classes.md"
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), ACQUISITION.MARTIAL_ARTIST_SOURCE["sha256"])
        lines = source.read_text(encoding="utf-8").splitlines()
        for clause_id, bounds, digest in zip(TABLES, RANGES, TABLES.values()):
            with self.subTest(clause=clause_id):
                excerpt = "\n".join(lines[bounds[0] - 1:bounds[1]])
                self.assertEqual(hashlib.sha256(excerpt.encode("utf-8")).hexdigest(), digest)
        self.assertEqual(MOVES.RANKED["feat/무술-훈련"], EXPECTED_RANKS)
        self.assertEqual(set(ACQUISITION.MARTIAL_ABILITY_BINDINGS), set(STYLE_CASES))
        for uid in ("ability/정신력", "ability/이판사판"):
            unit = self.rules.selection.units[uid]
            self.assertEqual(unit["source"]["lines"], [2394, 2402])
            definition=self.rules.core_abilities[uid]
            self.assertEqual(self.rules.ability_effects[unit['title']],definition['effects'])
            self.assertEqual(definition['official_source']['file'],'source-audit/core-1.05-martial-abilities.txt')
            self.assertEqual(unit.get('keyword'),'방어적' if uid=='ability/정신력' else None)
        for uid in ("ability/정신력-playtest", "ability/이판사판-playtest"):
            with self.assertRaises(ExcludedRuleSelection):
                self.rules._selected_rule(uid)

    def test_all_six_exact_receipts_drive_their_full_rank_move_paths(self):
        for index, (ability, choices) in enumerate(STYLE_CASES.items()):
            with self.subTest(ability=ability):
                engine, actor = self.fixture(name="martial-" + str(index))
                receipt = self.acquire(engine, actor, ability, request="martial/" + str(index))
                self.select_moves(actor, choices)
                items.register_feats(engine, actor)
                self.assertEqual(receipt["selection"]["values"], [ability])
                self.assertEqual(ACQUISITION.martial_ability(actor), ability)
                expected_moves = [self.rules.move_id(name) for pair in choices for name in pair]
                self.assertTrue(set(expected_moves).issubset(actor.moves))
                move_row = actor.spec[GRANTS.KEY]["sources"]["feature:" + actor.entity_id + ":feat/무술-훈련"]
                self.assertEqual(move_row["class_move_selection"], [[self.rules.move_id(name) for name in pair] for pair in choices])
                self.assertEqual((move_row["owner_id"], move_row["lifetime"]), (actor.entity_id, "while_owned"))
                ability_row = actor.spec[GRANTS.KEY]["sources"][ACQUISITION.martial_ability_source(actor)]
                title = ACQUISITION.MARTIAL_ABILITY_BINDINGS[ability]["title"]
                self.assertEqual(ability_row["grants"], {"abilities": [title]})
                self.assertEqual(ABILITIES.known(actor), [ability])

    def test_receipt_and_native_source_are_both_required_before_move_mutation(self):
        engine, actor = self.fixture()
        self.acquire(engine, actor, "철주먹")
        self.select_moves(actor, STYLE_CASES["ability/철주먹"])
        items.register_feats(engine, actor)
        engine.gm.snapshot("martial-exact")
        GRANTS.revoke(actor, ACQUISITION.martial_ability_source(actor), engine=engine)
        before = deepcopy((actor.spec, actor.moves, actor.abilities, engine.rng.getstate()))
        with self.assertRaisesRegex(ValueError, "exact while-owned native source"):
            MOVES.register_all(engine, actor)
        self.assertEqual((actor.spec, actor.moves, actor.abilities, engine.rng.getstate()), before)
        engine.gm.restore("martial-exact", reason="restore Martial Artist acquisition")
        self.assertEqual(ACQUISITION.martial_ability(actor), "ability/철주먹")
        self.assertEqual(MOVES.register_all(engine, actor), 0)

        restored = load_engine(self.rules, json.loads(json.dumps(dump_engine(engine), ensure_ascii=False)))
        copy = restored.everyone[0]
        self.assertEqual(ACQUISITION.martial_ability(copy), "ability/철주먹")
        self.assertEqual(copy.spec[ACQUISITION.PROJECTION_KEY], actor.spec[ACQUISITION.PROJECTION_KEY])
        self.assertTrue(restored.validate_state()["valid"])

    def test_wrong_style_and_unreceipted_baseline_fail_atomically(self):
        engine, actor = self.fixture()
        self.acquire(engine, actor, "철주먹")
        self.select_moves(actor, [["태권당수", "두번차기"]])
        before = deepcopy((actor.spec, actor.moves, actor.abilities, engine.rng.getstate()))
        with self.assertRaisesRegex(ValueError, "exact acquired Ability receipt"):
            MOVES.register_all(engine, actor)
        self.assertEqual((actor.spec, actor.moves, actor.abilities, engine.rng.getstate()), before)

        engine, actor = self.fixture(name="unreceipted")
        actor.spec["classes"] = ["class/무술가"]
        self.select_moves(actor, [["마하펀치", "두번차기"]])
        GRANTS.set_baseline(actor, "abilities", ["철주먹"])
        before = deepcopy((actor.spec, actor.moves, actor.abilities, engine.rng.getstate()))
        with self.assertRaisesRegex(ValueError, "committed selection-only Feature instance"):
            MOVES.register_all(engine, actor)
        self.assertEqual((actor.spec, actor.moves, actor.abilities, engine.rng.getstate()), before)

    def test_acquisition_prerequisites_domain_replay_and_tamper_fail_closed(self):
        cases = [
            (dict(edge=False), "Basic Martial Arts", "철주먹"),
            (dict(combat=2), "Novice Combat", "철주먹"),
            (dict(), "printed domain", "invented"),
        ]
        for index, (options, message, ability) in enumerate(cases):
            with self.subTest(case=index):
                engine, actor = self.fixture(name="bad-" + str(index), **options)
                before = deepcopy((actor.spec, actor.moves, actor.abilities, engine.rng.getstate()))
                with self.assertRaisesRegex(ValueError, message):
                    self.acquire(engine, actor, ability)
                self.assertEqual((actor.spec, actor.moves, actor.abilities, engine.rng.getstate()), before)

        engine, actor = self.fixture()
        receipt = self.acquire(engine, actor, "정신력")
        self.assertEqual(self.acquire(engine, actor, "ability/정신력"), receipt)
        with self.assertRaisesRegex(ValueError, "different payload"):
            self.acquire(engine, actor, "철주먹")
        actor.spec[ACQUISITION.LEDGER_KEY]["martial/acquire"]["selection"]["values"] = ["ability/철주먹"]
        with self.assertRaisesRegex(ValueError, "integrity"):
            ACQUISITION.validate_actor(actor)

    def test_shadow_progress_is_atomic_for_all_three_move_tables(self):
        before = collect_category2(ROOT)
        self.assertEqual(before["denominator"], 2352)
        ledger_path = ROOT / "data/verification/category2-class-clause-status.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        rows = {row["source_clause_id"]: row for row in ledger["entries"]}
        pending = {clause_id for clause_id in TABLES if rows[clause_id]["status"] == "incomplete"}
        self.assertIn(len(pending), (0, 3))
        with tempfile.TemporaryDirectory(prefix="martial-tables-", dir=ROOT / "tmp") as tmp:
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
            found = set()
            for row in ledger["entries"]:
                if row["source_clause_id"] in pending:
                    row["status"] = "implemented"
                    found.add(row["source_clause_id"])
            self.assertEqual(found, pending)
            path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            after = collect_category2(shadow)
        self.assertEqual(after["validation_errors"], [])
        self.assertEqual(after["denominator"], before["denominator"])
        self.assertEqual(after["completed_clause_count"] - before["completed_clause_count"], len(pending))


if __name__ == "__main__":
    unittest.main(verbosity=2)
