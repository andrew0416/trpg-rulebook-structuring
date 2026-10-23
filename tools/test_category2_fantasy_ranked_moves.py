"""Printed ranked move tables through native registration and shared grants."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from builder import build_trainer
from engine import Combatant, Engine, Rules
import class_move_grants as MOVES
import encounter
import items
import state_codec as CODEC
import state_grants as GRANTS
import static_feature_state_grants as STATIC

CASES = {
    "feat/스톰-위자드": [["차지빔", "스파크"], ["충전", "괴전파"], ["번개", "전기자석파"]],
    "feat/휘몰아치는-바람": [["제비반환", "에어커터"], ["바람일으키기", "안개제거"], ["폭풍", "따라하기"]],
    "feat/자연의-포용": [["목화포자", "달콤한향기"], ["에너지볼", "아로마테라피"], ["꽃잎댄스", "씨뿌리기"]],
    "feat/해류의-부름": [["아쿠아제트", "아쿠아링"], ["물의파동", "거품광선"], ["파도타기", "비바라기"]],
}


class FantasyRankedMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="all")
        cls.tables = MOVES._ranked_tables(cls.rules)

    def fixture(self, uid, rank=1, *, branch="꽃의 맹약", parent=None):
        row = self.tables[uid]
        owner = parent or row["parent"]
        spec = build_trainer(self.rules, "ranked-owner", 30,
                             dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
                             moves=[], abilities=[])
        spec.update(classes=[], edges=[], feats=[owner, uid], feat_ranks={uid: rank},
                    skills={"곡예": 6, "집중": 6, "직감": 6, "육상": 6, "생존": 6, "일반지식": 6},
                    feature_choices={uid: deepcopy(CASES[uid][:rank])},
                    static_feature_choices={owner: branch} if row.get("branch_for_move") else {})
        actor = Combatant(self.rules, spec)
        engine = Engine(self.rules, seed=1196)
        engine.everyone = engine.gm.everyone = [actor]
        return engine, actor

    def fingerprint(self, engine, actor):
        return deepcopy((actor.spec, actor.moves, actor.stats, engine.rng.getstate()))

    def register(self, engine, actor):
        return items.register_feats(engine, actor)

    def assert_rejected(self, engine, actor):
        before = self.fingerprint(engine, actor)
        with self.assertRaises(ValueError):
            self.register(engine, actor)
        self.assertEqual(self.fingerprint(engine, actor), before)

    def test_every_printed_cell_and_pact_guard_matches_the_native_table(self):
        lines = (ROOT / "input/supp-fantasy.md").read_text(encoding="utf-8").splitlines()
        for uid, row in self.tables.items():
            with self.subTest(source=uid):
                actual = {"1": [], "2": [], "3": []}
                guards = {}
                for line in lines[row["lines"][0]-1:row["lines"][1]]:
                    if not line.startswith("|") or "**" in line:
                        continue
                    cells = [cell.strip() for cell in line.strip("|").split("|")]
                    step = 2 if row.get("branch_for_move") else 1
                    for index in range(3):
                        name = cells[index*step]
                        if name == "-":
                            continue
                        mid = self.rules.move_id(name.replace(" ", ""))
                        self.assertIsNotNone(mid, name)
                        actual[str(index+1)].append(mid)
                        if step == 2 and cells[index*step+1] != "없음":
                            guards[mid] = cells[index*step+1]
                self.assertEqual(actual, row["moves_by_rank"])
                self.assertEqual(guards, row.get("branch_for_move", {}))

    def test_four_native_sources_progress_preserve_rank_history_and_restore(self):
        for uid, choices in CASES.items():
            with self.subTest(source=uid):
                engine, actor = self.fixture(uid)
                baseline = self.rules.move_id(choices[0][0])
                independent = self.rules.move_id(choices[0][1])
                GRANTS.set_baseline(actor, "moves", [baseline])
                GRANTS.grant(actor, "moves", independent, "equipment:independent", "equipment")
                for rank in (1, 2, 3):
                    actor.spec["feat_ranks"][uid] = rank
                    actor.spec["feature_choices"][uid] = deepcopy(choices[:rank])
                    self.register(engine, actor)
                    before = self.fingerprint(engine, actor)
                    self.register(engine, actor)
                    self.assertEqual(self.fingerprint(engine, actor), before)
                    expected = [self.rules.move_id(name) for pair in choices[:rank] for name in pair]
                    self.assertTrue(set(expected).issubset(encounter.usable_moves(engine, actor)))
                    self.assertEqual([actor.moves.count(mid) for mid in expected], [1]*len(expected))
                    receipt = actor.spec[GRANTS.KEY]["sources"]["feature:" + actor.entity_id + ":" + uid]
                    self.assertEqual((receipt["owner_id"], receipt["rule_id"], receipt["lifetime"], receipt["tutor_points"]),
                                     (actor.entity_id, uid, "while_owned", 0))
                engine.gm.snapshot("rank-three")
                actor.spec["feat_ranks"][uid] = 1
                actor.spec["feature_choices"][uid] = deepcopy(choices[:1])
                self.register(engine, actor)
                self.assertNotIn(self.rules.move_id(choices[2][0]), actor.moves)
                engine.gm.restore("rank-three")
                self.assertIn(self.rules.move_id(choices[2][0]), actor.moves)
                loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False)))
                restored = loaded.everyone[0]
                self.register(loaded, restored)
                self.assertTrue(set(expected).issubset(encounter.usable_moves(loaded, restored)))
                restored.spec.update(feats=[], feat_ranks={}, feature_choices={}, static_feature_choices={})
                self.register(loaded, restored)
                self.assertEqual(set(restored.moves), {baseline, independent})
                GRANTS.revoke(restored, "equipment:independent", engine=loaded)
                self.assertEqual(restored.moves, [baseline])

    def test_each_pact_reads_the_existing_druid_choice_and_rejects_other_cells(self):
        uid = "feat/자연의-포용"
        row = self.tables[uid]
        for branch in ("꽃의 맹약", "곰팡이의 맹약", "나무의 맹약"):
            for use_csv in (False, True):
                with self.subTest(branch=branch, csv=use_csv):
                    parent = "C2CSV/input/db/feats.csv:R643:main" if use_csv else None
                    engine, actor = self.fixture(uid, branch=branch, parent=parent)
                    pairs = [[next(mid for mid in row["moves_by_rank"][str(rank)]
                                   if row["branch_for_move"].get(mid) == branch),
                              next(mid for mid in row["moves_by_rank"][str(rank)]
                                   if mid not in row["branch_for_move"])] for rank in (1, 2, 3)]
                    actor.spec["feat_ranks"][uid] = 3
                    actor.spec["feature_choices"][uid] = pairs
                    self.register(engine, actor)
                    self.assertEqual(STATIC.class_branch(actor, row["parent"]), branch)
                    self.assertTrue(set(sum(pairs, [])).issubset(encounter.usable_moves(engine, actor)))
                    changed = deepcopy(pairs)
                    changed[0][0] = next(mid for mid in row["moves_by_rank"]["1"]
                                               if mid in row["branch_for_move"] and row["branch_for_move"][mid] != branch)
                    actor.spec["feature_choices"][uid] = changed
                    self.assert_rejected(engine, actor)

    def test_parent_skill_alternatives_and_rank_thresholds_are_not_inferred(self):
        for uid, row in self.tables.items():
            for rank in (1, 2, 3):
                for skill in row["skills"]:
                    with self.subTest(source=uid, rank=rank, skill=skill):
                        engine, actor = self.fixture(uid, rank)
                        minimum = row["minimum_skill_rank"][rank-1]
                        actor.spec["skills"] = {skill: max(1, minimum)}
                        self.register(engine, actor)
                        if minimum:
                            actor.spec["skills"] = {skill: minimum-1}
                            self.assert_rejected(engine, actor)
            engine, actor = self.fixture(uid)
            actor.spec["feats"].remove(row["parent"])
            self.assert_rejected(engine, actor)
        engine, actor = self.fixture("feat/휘몰아치는-바람", 2)
        actor.spec["skills"] = {"직감": 6}
        self.assert_rejected(engine, actor)

    def test_invalid_history_dash_duplicates_and_last_batch_source_are_atomic(self):
        for uid, choices in CASES.items():
            for bad in ([], [[choices[0][0]]], [[choices[0][0]]*2],
                        [[choices[0][0], "-"]], [[choices[0][0], choices[2][0]]]):
                with self.subTest(source=uid, bad=bad):
                    engine, actor = self.fixture(uid)
                    actor.spec["feature_choices"][uid] = bad
                    self.assert_rejected(engine, actor)
            engine, actor = self.fixture(uid, 2)
            actor.spec["feature_choices"][uid][1][0] = choices[0][0]
            self.assert_rejected(engine, actor)
            engine, actor = self.fixture(uid)
            self.register(engine, actor)
            actor.spec["feature_choices"][uid][0] = list(reversed(choices[0]))
            self.assert_rejected(engine, actor)
        first, last = "feat/스톰-위자드", "feat/해류의-부름"
        engine, actor = self.fixture(first)
        actor.spec["feats"] += [self.tables[last]["parent"], last]
        actor.spec["feat_ranks"][last] = 1
        actor.spec["feature_choices"][last] = [["아쿠아제트", "파도타기"]]
        self.assert_rejected(engine, actor)

    def test_changed_source_binding_fails_before_granting_any_moves(self):
        uid = "feat/스톰-위자드"
        engine, actor = self.fixture(uid)
        original = self.rules.selection.units[uid]
        changed = deepcopy(original)
        changed["source"]["lines"][0] += 1
        cached = self.rules._ranked_class_move_tables
        del self.rules._ranked_class_move_tables
        try:
            with patch.dict(self.rules.selection.units, {uid: changed}):
                self.assert_rejected(engine, actor)
        finally:
            self.rules._ranked_class_move_tables = cached


if __name__ == "__main__":
    unittest.main()
