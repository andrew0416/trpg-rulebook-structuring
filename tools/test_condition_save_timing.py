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

    def assert_parser_rows_with_curated_versions(self, saved, policies, required):
        expected = {x['id']: self.parser.mechanize(x) for x in self.entities}
        actual = {x['id']: copy.deepcopy(x) for x in saved}
        self.assertEqual(len(actual), len(saved))
        for uid, version in required:
            self.assertIn(version, actual[uid]['mech']['data'])
        for uid, versions in policies.items():
            data = actual[uid]['mech']['data']
            for version, policy in versions.items():
                if version in data:
                    # Validate the entire source-derived payload (including
                    # authority and number/bool types) before excluding a key.
                    self.assertEqual(
                        json.dumps(data[version], sort_keys=True, ensure_ascii=False, allow_nan=False),
                        json.dumps(policy, sort_keys=True, ensure_ascii=False, allow_nan=False))
                    del data[version]
        self.assertEqual({uid: actual[uid] for uid in expected}, expected)
        self.assertEqual(set(actual) - set(expected), {'condition/조이기'})
        return actual

    def test_curated_policy_allowlist_rejects_other_data_changes(self):
        sys.path.insert(0, str(ROOT / 'engine'))
        from engine import Rules
        profiles = ('core', 'core-csv-status-1.05', 'core-csv-frozen-homebrew')
        rules = {name: Rules(ROOT, ruleset=name) for name in profiles}
        policies = {'condition/혼란': {
            'core-1.05': {
                'effects': [{'type': 'core_confusion_start_turn', 'self_hit_max': 8,
                             'normal_max': 15, 'cure_min': 16, 'attack': 'typeless_physical_struggle',
                             'resistance_steps': 1, 'no_other_actions': True}],
                'authority': {'document': 'PTU 1.05 Core', 'page': 247}},
            'february-2016': {
                'effects': [{k: v for k, v in effect.items() if not k.startswith('_')}
                            for effect in self.parser.mechanize(
                                next(x for x in self.entities if x['name'] == '혼란'))['mech']['data']['effects']],
                'authority': {'document': 'PTU February 2016 Playtest v2', 'page': 2}}}}
        # Independent canonical oracles: the four recorded CSV payload pins and
        # the complete reviewed TM113/S-001 Frozen contract, not adapter output.
        csv_fingerprints = {
            '마비': '2f38fa2d46648e52f7db15f71e18f107b748c471a2155d9436c19beb8f6b57b0',
            '풀죽음': 'd5bae86ea96de599398030ceae79861d0351b24b1446247ddb609f04b7c5cadf',
            '헤롱헤롱': '8421ee5cae23d2e83b8014c1b922266e5d19e177f643aae75b13e86f5fca3a07',
            '억압': 'e20ea16374ee288007bd759b86a033ca28d2c3cd40a3ed55eb8edbae362b1b5f',
        }
        frozen_policy = {
            'effects': [
                {'type': 'no_actions'}, {'type': 'evasion_disabled'},
                {'type': 'save', 'dc': 12, 'timing': 'end_of_turn', 'on_success': 'cure'},
                {'type': 'immunity', 'types': ['얼음'], 'actor_kind': 'pokemon'},
                {'type': 'save_modifier', 'if_type': '불꽃', 'dc': 8},
                {'type': 'cured_by_damage_of_types', 'types': ['불꽃', '격투', '바위', '강철']},
                {'type': 'save_modifier', 'weather': {'쾌청': 2, '싸라기눈': -4}}],
            'authority': {
                'file': 'input/db/tm.csv', 'row': 113, 'columns': [4, 5],
                'sha256': 'dd06395776044c0c13e698420aead38907d6969f475caf8485ec2cd1a2259f44',
                'timing_authority': 'PTU 1.05 Core p246: end of each turn; S-001 fills omitted Korean timing only'}}
        # Use the real production-installed views, not editions presumed to
        # exist in the private JSON or an invented replacement source body.
        for profile, names, version in (
                ('core-csv-status-1.05', ('마비', '풀죽음', '헤롱헤롱', '억압'), 'csv-core-1.05'),
                ('core-csv-frozen-homebrew', ('얼음',), 'csv-homebrew')):
            for name in names:
                uid = 'condition/' + name
                selected = rules[profile].mech(uid)
                self.assertEqual(selected['_version'], version)
                payload = copy.deepcopy(rules[profile].units[uid]['mech']['data'][version])
                if version == 'csv-core-1.05':
                    self.assertEqual(hashlib.sha256(json.dumps(
                        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                        allow_nan=False).encode()).hexdigest(), csv_fingerprints[name])
                else:
                    self.assertEqual(
                        json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False),
                        json.dumps(frozen_policy, sort_keys=True, ensure_ascii=False, allow_nan=False))
                self.assertEqual(selected['effects'], payload['effects'])
                policies.setdefault(uid, {})[version] = payload
        views = {profile: [copy.deepcopy(view.units[row['id']]) for row in self.saved]
                 for profile, view in rules.items()}
        required = {profile: {('condition/혼란', 'core-1.05'), ('condition/혼란', 'february-2016')} |
                    {(uid, version) for uid, version in view.ruleset.unit_versions.items()
                     if version in policies.get(uid, {})} for profile, view in rules.items()}
        for profile, saved in views.items():
            self.assert_parser_rows_with_curated_versions(saved, policies, required[profile])
            self.assertEqual(self.save(next(x for x in saved if x['id'] == 'condition/마비'))['dc'], 11)
        self.assertEqual(next(e['dc'] for e in rules['core'].condition_effects('마비') if e['type'] == 'save'), 11)
        self.assertEqual(next(e['dc'] for e in rules['core-csv-status-1.05'].condition_effects('마비') if e['type'] == 'save'), 5)
        self.assertEqual(next(e['dc'] for e in rules['core'].condition_effects('얼음') if e['type'] == 'save'), 16)
        self.assertEqual(next(e['dc'] for e in rules['core-csv-frozen-homebrew'].condition_effects('얼음') if e['type'] == 'save'), 12)
        cases = [
            ('core', '마비', ('effects', 1, 'timing'), 'end_of_turn'),
            ('core', '혼란', ('effects', 3, 'dc'), 15),
            ('core', '혼란', ('core-1.05', 'effects', 0, 'cure_min'), 17),
            ('core', '혼란', ('core-1.05', 'authority', 'page'), 248),
            ('core', '혼란', ('february-2016', 'effects', 3, 'timing'), 'start_of_turn'),
            ('core', '혼란', ('february-2016', 'authority', 'unreviewed'), True),
            ('core', '혼란', ('core-1.05',), None),
            ('core', '혼란', ('unreviewed-version',), {}),
            ('core', '마비', ('core-1.05',), {}),
            ('core-csv-status-1.05', '마비', ('csv-core-1.05', 'effects', 1, 'dc'), 6),
            ('core-csv-status-1.05', '억압', ('csv-core-1.05', 'authority', 'row'), 87),
            ('core-csv-status-1.05', '마비', ('csv-core-1.05', 'authority', 'unreviewed'), True),
            ('core-csv-status-1.05', '헤롱헤롱', ('csv-core-1.05',), None),
            ('core-csv-frozen-homebrew', '얼음', ('csv-homebrew', 'effects', 2, 'timing'), 'start_of_turn'),
            ('core-csv-frozen-homebrew', '얼음', ('csv-homebrew', 'authority', 'row'), 112),
            ('core-csv-frozen-homebrew', '얼음', ('csv-homebrew', 'effects', 6, 'weather', '쾌청'), 3),
        ]
        for profile, name, path, value in cases:
            with self.subTest(profile=profile, condition=name, path=path):
                saved = copy.deepcopy(views[profile])
                node = next(x for x in saved if x['id'] == 'condition/' + name)['mech']['data']
                for key in path[:-1]:
                    node = node[key]
                if value is None:
                    del node[path[-1]]
                else:
                    node[path[-1]] = value
                with self.assertRaises(AssertionError):
                    self.assert_parser_rows_with_curated_versions(saved, policies, required[profile])

    def assert_parser_rows_with_reviewed_confusion_versions(self, saved):
        expected = {x["id"]: self.parser.mechanize(x) for x in self.entities}
        actual = {x["id"]: copy.deepcopy(x) for x in saved}
        # The Korean-source parser does not produce the separately reviewed
        # edition policies. Validate their entire payloads before separating
        # only these two keys; every other stored field must still match.
        policies = {
            "core-1.05": {
                "effects": [{"type": "core_confusion_start_turn", "self_hit_max": 8,
                             "normal_max": 15, "cure_min": 16,
                             "attack": "typeless_physical_struggle",
                             "resistance_steps": 1, "no_other_actions": True}],
                "authority": {"document": "PTU 1.05 Core", "page": 247}},
            "february-2016": {
                "effects": [
                    {"type": "no_attack_of_opportunity"},
                    {"type": "on_attack_roll", "die": "1d2", "fail_on": 1},
                    {"type": "self_hp_loss",
                     "by_move_class": {"물리": "atk/2", "특수": "spa/2", "변화": "2 ticks"},
                     "after": "attack_resolves"},
                    {"type": "save", "dc": 16, "timing": "end_of_turn", "on_success": "cure"}],
                "authority": {"document": "PTU February 2016 Playtest v2", "page": 2}},
        }
        data = actual["condition/혼란"]["mech"]["data"]
        for version, policy in policies.items():
            self.assertIn(version, data)
            self.assertEqual(data.pop(version), policy)
        csv_editions = {
            '마비': '2f38fa2d46648e52f7db15f71e18f107b748c471a2155d9436c19beb8f6b57b0',
            '풀죽음': 'd5bae86ea96de599398030ceae79861d0351b24b1446247ddb609f04b7c5cadf',
            '헤롱헤롱': '8421ee5cae23d2e83b8014c1b922266e5d19e177f643aae75b13e86f5fca3a07',
            '억압': 'e20ea16374ee288007bd759b86a033ca28d2c3cd40a3ed55eb8edbae362b1b5f',
        }
        for name, digest in csv_editions.items():
            edition = actual['condition/'+name]['mech']['data'].pop('csv-core-1.05')
            self.assertEqual(hashlib.sha256(json.dumps(edition,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(), digest)
        self.assertEqual({uid: actual[uid] for uid in expected}, expected)
        self.assertEqual(set(actual) - set(expected), {"condition/조이기"})
        return actual

    def test_saved_curated_policy_allowlist_rejects_other_data_changes(self):
        # Metadata-only mutations: no engine import, execution or new rules.
        cases = [
            ("condition/마비", ("effects", 1, "timing"), "end_of_turn"),
            ("condition/혼란", ("effects", 3, "dc"), 15),
            ("condition/혼란", ("core-1.05", "effects", 0, "cure_min"), 17),
            ("condition/혼란", ("core-1.05", "authority", "page"), 248),
            ("condition/혼란", ("february-2016", "effects", 3, "timing"), "start_of_turn"),
            ("condition/혼란", ("february-2016", "authority", "unreviewed"), True),
            ("condition/혼란", ("core-1.05",), None),
            ("condition/혼란", ("unreviewed-version",), {}),
            ("condition/마비", ("core-1.05",), {}),
            ("condition/마비", ("csv-core-1.05", "effects", 1, "dc"), 6),
            ("condition/억압", ("csv-core-1.05", "authority", "row"), 87),
        ]
        for uid, path, value in cases:
            with self.subTest(unit=uid, path=path):
                saved = copy.deepcopy(self.saved)
                node = next(x for x in saved if x["id"] == uid)["mech"]["data"]
                for key in path[:-1]:
                    node = node[key]
                if value is None:
                    del node[path[-1]]
                else:
                    node[path[-1]] = value
                with self.assertRaises(AssertionError):
                    self.assert_parser_rows_with_reviewed_confusion_versions(saved)

    def test_parsed_units_match_and_reviewed_vortex_keeps_its_separate_source(self):
        self.assertEqual(len(self.entities), 22)
        self.assertEqual(len(self.saved), 23)
        actual = self.assert_parser_rows_with_reviewed_confusion_versions(self.saved)
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
