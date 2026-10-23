"""Source/parser and stored-data regression for paralysis saves, not runtime proof."""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


class ConditionSaveTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("condition_parser_under_test", ROOT / "tools/mechanize_conditions.py")
        cls.parser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.parser)
        cls.entities = json.loads((ROOT / "output/entities/condition.json").read_text(encoding="utf-8"))
        cls.saved = json.loads((ROOT / "data/conditions.json").read_text(encoding="utf-8"))
        cls.raw_paralysis = next(x for x in cls.entities if x["name"] == "마비")

    def save(self, unit):
        rows = [e for e in unit["mech"]["data"]["effects"] if e["type"] == "save"]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_original_source_paralysis_start_and_normal_acting(self):
        lines = (ROOT / "input/ch07-combat.md").read_text(encoding="utf-8").splitlines()
        heading = next(i for i, line in enumerate(lines) if line.startswith("**마비(Paralysis):"))
        raw = copy.deepcopy(self.raw_paralysis)
        raw["text"] = lines[heading].split("**마비(Paralysis): **", 1)[1] + "\n" + lines[heading + 1]
        result = self.parser.mechanize(raw)
        effect = self.save(result)
        self.assertEqual((effect["dc"], effect["timing"], effect["on_success"]), (11, "start_of_turn", "act_normally"))
        self.assertIn("정상적으로 행동할 수", effect["_success_src"])
        self.assertEqual(result["mech"]["data"]["class"], "persistent")
        self.assertTrue(any(e["type"] == "action_limit" and e["if"] == "save_failed" for e in result["mech"]["data"]["effects"]))
        # Persistent paralysis still needs a separate cure; save success is not it.
        self.assertTrue(any("마비, 독 상태" in line and "치료해야" in line for line in lines))

    def test_saved_paralysis_data_does_not_cure_on_save(self):
        effect = self.save(next(x for x in self.saved if x["id"] == "condition/마비"))
        self.assertEqual(effect["timing"], "start_of_turn")
        self.assertEqual(effect["dc"], 11)
        self.assertEqual(effect["on_success"], "act_normally")
        self.assertNotEqual(effect["on_success"], "cure")

    def test_subject_prefix_does_not_hide_start_timing(self):
        for subject in ("", "대상의 ", "포켓몬의 "):
            with self.subTest(subject=subject):
                raw = copy.deepcopy(self.raw_paralysis)
                raw["text"] = subject + "턴이 시작될 때 11+의 내성 체크를 수행하세요. 내성 체크에 성공했으면 사용자는 정상적으로 행동할 수 있습니다."
                effect = self.save(self.parser.mechanize(raw))
                self.assertEqual(effect["timing"], "start_of_turn")
                self.assertEqual(effect["on_success"], "act_normally")

    def test_normal_acting_outcome_is_text_driven_not_condition_name_or_dc(self):
        # Synthetic language fixture, not an authorized new game condition.
        raw = copy.deepcopy(self.raw_paralysis)
        raw.update(name="parser_fixture", eng="ParserFixture")
        raw["text"] = "대상의 턴이 시작될 때 DC 13 내성 체크를 수행하세요. 내성 체크에 성공했으면 사용자는 정상적으로 행동할 수 있습니다."
        effect = self.save(self.parser.mechanize(raw))
        self.assertEqual((effect["dc"], effect["on_success"]), (13, "act_normally"))

    def test_normal_acting_success_clause_survives_line_wrap(self):
        raw = copy.deepcopy(self.raw_paralysis)
        raw["text"] = raw["text"].replace("내성 체크에 성공했으면", "내성 체크에\n성공했으면")
        self.assertEqual(self.save(self.parser.mechanize(raw))["on_success"], "act_normally")

    def test_start_timing_alone_does_not_change_cure_outcome(self):
        raw = copy.deepcopy(self.raw_paralysis)
        raw["text"] = "대상의 턴이 시작될 때 DC 16 내성 체크를 수행하여 치료할 수 있습니다."
        effect = self.save(self.parser.mechanize(raw))
        self.assertEqual((effect["timing"], effect["on_success"]), ("start_of_turn", "cure"))
        self.assertNotIn("_success_src", effect)

    def test_existing_end_turn_curing_saves_are_preserved(self):
        expected = {"얼음": 16, "혼란": 16, "난동": 15, "헤롱헤롱": 16, "잠듦": 16}
        for name, dc in expected.items():
            with self.subTest(condition=name):
                raw = next(x for x in self.entities if x["name"] == name)
                effect = self.save(self.parser.mechanize(raw))
                self.assertEqual((effect["dc"], effect["timing"], effect["on_success"]), (dc, "end_of_turn", "cure"))
                self.assertNotIn("_success_src", effect)

    def test_parsed_units_match_and_reviewed_vortex_keeps_its_separate_source(self):
        self.assertEqual(len(self.entities), 22)
        self.assertEqual(len(self.saved), 23)
        expected = {x["id"]: self.parser.mechanize(x) for x in self.entities}
        actual = {x["id"]: x for x in self.saved}
        self.assertEqual({uid: actual[uid] for uid in expected}, expected)
        self.assertEqual(set(actual) - set(expected), {"condition/조이기"})
        # Vortex is sourced from the keyword chapter, outside this parser's22 rows.
        vortex = actual["condition/조이기"]
        self.assertEqual(vortex["_category3_source"], "C3-EX-095")
        self.assertEqual(vortex["source"]["chapter"], "ch10-index-reference")
        lines = (ROOT / "input/ch10-index-reference.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(vortex["text"]["body"], lines[vortex["source"]["line"] - 1])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    ROOT = args.root.resolve()
    class Result(unittest.TextTestResult):
        def __init__(self, *a, **k): super().__init__(*a, **k); self.rows = []
        def addSuccess(self, test): super().addSuccess(test); self.rows.append({"id": "CONDITION-SAVE-" + test._testMethodName, "status": "pass"})
        def addFailure(self, test, err): super().addFailure(test, err); self.rows.append({"id": "CONDITION-SAVE-" + test._testMethodName, "status": "fail"})
        def addError(self, test, err): super().addError(test, err); self.rows.append({"id": "CONDITION-SAVE-" + test._testMethodName, "status": "error"})
        def addSubTest(self, test, subtest, err):
            super().addSubTest(test, subtest, err)
            if err: self.rows.append({"id": "CONDITION-SAVE-" + test._testMethodName + str(subtest), "status": "fail"})
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(ConditionSaveTimingTests))
    files = ["tools/mechanize_conditions.py", "tools/test_condition_save_timing.py", "data/conditions.json", "output/entities/condition.json", "input/ch07-combat.md"]
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "scope": "Paralysis parser/source timing and successful normal-acting outcome, stored-data regression and other existing saves; no engine runtime conformance or semantic completeness proof", "whole_rule_certified": False, "semantic_completeness_proved": False, "results": result.rows, "input_hashes": {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}}
    output = args.output or ROOT / "output/condition-save-timing-tests.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
