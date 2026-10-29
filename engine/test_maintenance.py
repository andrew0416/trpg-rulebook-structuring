"""Regression coverage for source recovery, PTK schema, growth history and GM handoff."""
import copy
import io
import json
import sys
import unittest
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "tools"))
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer, allocation_base, add_stat_points
import downtime as DT
import effects as FX
import items as ITEMS
from ptk_structure import block_source
from validate_ruleunits import validate_rows, check_schema

class MaintenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT))
        cls.rows = [json.loads(x) for x in (ROOT / "output/ruleunits.jsonl").read_text(encoding="utf-8").splitlines()]
        cls.units = {x["id"]: x for x in cls.rows}
        cls.schema = json.loads((ROOT / "schema/rule-unit.schema.json").read_text(encoding="utf-8"))

    def pokemon(self, level=5):
        return build_pokemon(self.rules, "이상해씨", level)

    def test_full_source_recovered(self):
        for uid, phrase in [("feat/생명의-샘", "그 수치의 두 배"), ("feat/힘의-전달", "코트"), ("gift/축복받은-타격", "노타입")]:
            with self.subTest(uid=uid):
                u = self.units[uid]
                self.assertIn(phrase, u["text"]["body"])
                start, end = u["source"]["lines"]
                lines = (ROOT / "input" / u["source"]["file"]).read_text(encoding="utf-8").splitlines()
                self.assertEqual(u["text"]["body"], "\n".join(lines[start-1:end]))
                self.assertNotIn("고통 약화", u["text"]["body"])

    def test_source_boundary_and_table(self):
        lines = ["**첫째(First)**", "**효과 하나 선택:**", "» 선택 A", "", "<table>", "|a|b|", "</table>", "**둘째(Second)**", "**효과:** 다음"]
        text, end = block_source(lines, 0)
        self.assertEqual(end, 7)
        self.assertIn("|a|b|", text)
        self.assertNotIn("둘째", text)

    def test_current_db_matches_schema(self):
        self.assertEqual(validate_rows(self.rows, self.schema), [])

    def test_schema_rejects_invalid_contracts(self):
        original = copy.deepcopy(self.units["feat/생명의-샘"])
        mutants = []
        x = copy.deepcopy(original); del x["source"]["license"]; mutants.append(x)
        x = copy.deepcopy(original); x["id"] = "bad id"; mutants.append(x)
        x = copy.deepcopy(original); x["mech"]["confidence"] = "unverified-new"; mutants.append(x)
        x = copy.deepcopy(original); x["mech"]["data"]["effects"] = ["wrong"]; mutants.append(x)
        x = copy.deepcopy(original); x["source"]["lines"] = [True, 2]; mutants.append(x)
        x = copy.deepcopy(original); x["source"]["lines"] = [3, 2]; mutants.append(x)
        for i, value in enumerate(mutants):
            with self.subTest(i=i):
                self.assertTrue(validate_rows([value], self.schema))
        self.assertTrue(validate_rows([original, original], self.schema))

    def test_schema_unknown_keyword_fails(self):
        with self.assertRaises(ValueError):
            check_schema({"type": "string", "misspelled_constraint": True})

    def test_growth_preserves_player_allocation(self):
        spec = self.pokemon()
        base = allocation_base(self.rules, spec)
        chosen = max(base, key=base.get)
        spec["stats"] = dict(base)
        spec["stats"][chosen] += spec["level"] + 10
        before = dict(spec["stats"])
        DT.level_up(self.rules, spec, stat_choice=chosen)
        self.assertEqual(spec["stats"], {s: v + (s == chosen) for s, v in before.items()})
        self.assertEqual(spec["stat_history"][-2]["event"], "external_adjustment")
        self.assertEqual(spec["stat_history"][-1]["delta"], {chosen: 1})
        self.assertEqual(sum(spec["stat_allocation"].values()), 16)

    def test_legacy_spec_imports_without_reset(self):
        spec = self.pokemon(); spec.pop("stat_history"); spec.pop("stat_allocation")
        before = dict(spec["stats"])
        DT.level_up(self.rules, spec)
        self.assertEqual(spec["stat_history"][0]["event"], "import")
        self.assertEqual(spec["stat_history"][0]["stats"], before)
        self.assertTrue(all(spec["stats"][s] >= before[s] for s in before))
        self.assertEqual(sum(spec["stats"].values()), sum(before.values()) + 1)

    def test_reject_choice_without_mutation(self):
        spec = self.pokemon(); before = copy.deepcopy(spec)
        with self.assertRaises(ValueError):
            DT.level_up(self.rules, spec, stat_choice="unknown")
        self.assertEqual(spec, before)
        spec["stats"] = {s: 30 for s in spec["stats"]}
        choice = min(allocation_base(self.rules, spec), key=allocation_base(self.rules, spec).get)
        before = copy.deepcopy(spec)
        with self.assertRaises(ValueError):
            DT.level_up(self.rules, spec, stat_choice=choice)
        self.assertEqual(spec, before)

    def test_multilevel_failure_is_atomic(self):
        spec = self.pokemon(); before = copy.deepcopy(spec); log = []
        with self.assertRaises(ValueError):
            DT.gain_exp(self.rules, spec, 50, log, stat_choices={7: "unknown"})
        self.assertEqual(spec, before)
        self.assertEqual(log, [])

    def test_multilevel_history_and_serialization(self):
        spec = self.pokemon(); old = dict(spec["stats"])
        DT.gain_exp(self.rules, spec, 50)
        self.assertEqual(spec["level"], 10)
        self.assertEqual([x["level"] for x in spec["stat_history"] if x["event"] == "level_up"], [6,7,8,9,10])
        self.assertEqual(sum(spec["stats"].values()) - sum(old.values()), 5)
        restored = json.loads(json.dumps(spec, ensure_ascii=False))
        DT.level_up(self.rules, restored)
        self.assertEqual(restored["stat_history"][:-1], spec["stat_history"])

    def test_evolution_records_reallocation(self):
        spec = self.pokemon(15); old = copy.deepcopy(spec)
        self.assertTrue(DT.evolve(self.rules, spec, "이상해풀"))
        self.assertEqual(spec["stat_history"][:-1], old["stat_history"])
        self.assertEqual(spec["stat_history"][-1]["previous_stats"], old["stats"])
        self.assertEqual(sum(spec["stat_allocation"].values()), 25)

    def test_max_level_unchanged(self):
        spec = self.pokemon(100); before = copy.deepcopy(spec)
        DT.level_up(self.rules, spec)
        self.assertEqual(spec, before)

    def test_vitamins_survive_level_and_evolution(self):
        e = Engine(self.rules, 1)
        pc = Combatant(self.rules, self.pokemon(15))
        tr = Combatant(self.rules, build_trainer(self.rules, "test", 5, {s: 10 for s in pc.stats}, items={"타우린":1}))
        before = dict(pc.stats)
        result = ITEMS.use_item(e, tr, "타우린", pc, free=True)
        self.assertEqual(pc.spec.get("vitamin_bonus", {}).get("atk"), 1, result)
        self.assertEqual(pc.spec["stats"]["atk"], before["atk"] + 1)
        DT.gain_exp_combatant(e, pc, "to next level")
        self.assertGreaterEqual(pc.stats["atk"], before["atk"] + 1)
        DT.evolve(self.rules, pc.spec, "이상해풀")
        self.assertEqual(pc.spec["vitamin_bonus"]["atk"], 1)
        self.assertEqual(sum(pc.spec["stat_allocation"].values()), 26)

    def test_reviewed_beats_auto_full(self):
        for name in ("폭군의 울부짖기", "생명의 샘"):
            effects, header = self.rules.feat_effects(name)
            self.assertEqual(header["confidence"], "reviewed")
            self.assertTrue(any(e["type"] == "gm" for e in effects))
        effects, _, conf = self.rules._pick({"coverage":"full", "effects":[{"type":"wrong"}]}, None, [{"type":"gm"}])
        self.assertEqual((effects, conf), ([{"type":"gm"}], "reviewed"))

    def test_manual_feat_keeps_gm_prompt(self):
        e = Engine(self.rules, 1)
        c = Combatant(self.rules, build_trainer(self.rules, "test", 5, {s:10 for s in self.pokemon()["stats"]}, extra={"feats":["생명의 샘"]}))
        ITEMS.register_feats(e,c)
        self.assertTrue(any(x.get("type") == "feat_manual" for x in c.registry))
        ITEMS.manual_feat(e,c,"생명의 샘")
        self.assertTrue(e.gm_prompts)
        self.assertIn("그 수치의 2배", e.gm_prompts[-1]["effect"]["choice"])

    def test_unknown_selectors_held_not_silently_executed(self):
        e=Engine(self.rules,1); c=Combatant(self.rules,self.pokemon())
        ctx={"attacker":c,"target":c,"hit":True,"engine":e}
        for effect in [{"type":"stage_change","stat":"same chosen","delta":1}, {"type":"cure_status","status":"up to 3"}]:
            with self.subTest(effect=effect):
                done,held=FX.run_effects(e,c,c,[effect],ctx,"test")
                self.assertEqual((done,held),(0,1))

    def test_sheet_item_ids_and_effects_are_independent(self):
        from item_records import sheet_items
        rows = sheet_items(ROOT)
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)))
        for row in rows:
            auto = self.rules.items_mech[row["id"]]
            self.assertEqual(auto["desc"], row.get("desc", ""))
        for name, stat in [("구애 도구(방어)", "def"), ("구애 도구(특수방어)", "spd")]:
            effects, header = self.rules.item_effects(name)
            self.assertEqual(next(e["stat"] for e in effects if e["type"] == "stage_change"), stat)
        effects, _ = self.rules.item_effects("구애 도구")
        self.assertEqual(effects[0]["type"], "gm")

    def test_homebrew_food_keeps_own_condition(self):
        effects, _ = self.rules.item_effects("이유식 [홈브류]")
        self.assertIn("초기레벨+5", str(effects))
        self.assertNotIn("20레벨", str(effects))
        effects, _ = self.rules.item_effects("이유식")
        self.assertIn("20레벨", str(effects))

    def test_item_gm_prompt_is_not_discarded(self):
        e=Engine(self.rules,1); c=Combatant(self.rules,self.pokemon())
        ITEMS.register_item(e,c,"구애 도구")
        self.assertTrue(e.gm_prompts)
        self.assertIn("연관된 스탯", e.gm_prompts[-1]["text"])

    def test_crosscheck_translation_aliases(self):
        from crosscheck_drafts import check_effect
        self.assertEqual(check_effect({"type":"stat_base_mod", "stat":"all", "value":1}, "각 기본 스탯이 +1 증가합니다."), [])
        self.assertEqual(check_effect({"type":"grant_capability", "capability":"파워 +2"}, "+2 bonus to their Power Capability"), [])
        self.assertTrue(check_effect({"type":"stage_change", "stat":"spd", "delta":2}, "방어 스탯 +2"))

    def test_unsure_entries_still_queued(self):
        # A reviewed fallback must remain queued when a future review is unsure.
        from review_queue import main
        u = copy.deepcopy(self.units["feat/과장된-동작"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/"output").mkdir(); (root/"data").mkdir()
            (root/"output/ruleunits.jsonl").write_text(json.dumps(u, ensure_ascii=False)+"\n", encoding="utf-8")
            (root/"data/review-verdicts.json").write_text(json.dumps({u["id"]:{"verdict":"unsure","note":"new evidence"}}), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                main(root)
            queue = [json.loads(x) for x in (root/"output/review-queue.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([x["id"] for x in queue], [u["id"]])

    def test_source_resolution_counts_and_partial_coverage(self):
        # Recompute first: cached empty reports can hide a changed source reference.
        from crosscheck_drafts import main, load_resolutions, evidence_matches, check_effect
        with redirect_stdout(io.StringIO()):
            main(ROOT)
        unresolved = [json.loads(x) for x in (ROOT/"output/draft-crosscheck.jsonl").read_text(encoding="utf-8").splitlines()]
        resolved = [json.loads(x) for x in (ROOT/"output/draft-crosscheck-resolved.jsonl").read_text(encoding="utf-8").splitlines()]
        cases = load_resolutions(ROOT)
        # Keep all 23 original decisions. New source-backed effect clauses may add flags;
        # check every current flag is accounted for instead of freezing the old total at 24.
        self.assertEqual(len(cases), 23)
        self.assertEqual({r["id"] for r in unresolved+resolved}, set(cases))
        for uid in cases:
            unit = self.units[uid]
            body = (unit["text"].get("body") or "") + " " + (unit["text"].get("summary") or "")
            expected = [dict(effect=e, flag=flag, token=token)
                        for e in unit["mech"]["data"]["effects"] for flag,token in check_effect(e, body)]
            actual = [f for row in unresolved+resolved if row["id"] == uid for f in row["flags"]]
            self.assertCountEqual(actual, expected)
        for row in resolved:
            self.assertTrue(evidence_matches(ROOT, self.units[row["id"]], cases[row["id"]]))
        for row in unresolved:
            self.assertFalse(evidence_matches(ROOT, self.units[row["id"]], cases[row["id"]]))
        # An unresolved rule blocks the aggregate gate; it is not a broken invalidation mechanism.
        for uid in ["feat/과장된-동작", "feat/가디언의-심판", "feat/오버클럭", "item/플래시뱅"]:
            self.assertEqual(self.units[uid]["mech"]["confidence"], "reviewed")
            self.assertEqual(self.units[uid]["mech"]["coverage"], "partial")
        self.assertIn("19-10", self.units["item/플래시뱅"]["text"]["body"])

    def test_source_resolution_rejects_changed_effects_and_text(self):
        from crosscheck_drafts import load_resolutions, partition_flags
        cases = load_resolutions(ROOT); uid = "item/분홍진주"
        original = self.units[uid]; flags = cases[uid]["crosscheck_resolution"]["flags"]
        self.assertEqual(partition_flags(ROOT, original, flags, cases), ([],flags))
        for change in ("body", "value", "condition"):
            u = copy.deepcopy(original)
            if change == "body": u["text"]["body"] += " 수정"
            elif change == "value": u["mech"]["data"]["effects"][0]["value"] = 50
            else: u["mech"]["data"]["effects"][1]["if"] = "species == 이상해씨"
            self.assertEqual(partition_flags(ROOT, u, flags, cases), (flags,[]))
        extra = {"effect":{"type":"injury","value":99}, "flag":"수치 없음", "token":"value=99"}
        self.assertEqual(partition_flags(ROOT, original, flags+[extra], cases), ([extra],flags))

    def test_source_resolution_rejects_changed_reference(self):
        from crosscheck_drafts import load_resolutions, evidence_matches
        case = load_resolutions(ROOT)["item/억제제"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for ref in case["evidence"]:
                if "file" in ref:
                    dest = root/ref["file"]; dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes((ROOT/ref["file"]).read_bytes())
            self.assertTrue(evidence_matches(root, self.units[case["id"]], case))
            dest.write_text("changed reference", encoding="utf-8")
            self.assertFalse(evidence_matches(root, self.units[case["id"]], case))
            dest.unlink()
            self.assertFalse(evidence_matches(root, self.units[case["id"]], case))

    def test_resolved_features_surface_confirmed_procedures(self):
        expected = {"과장된 동작":["굴림 20", "첫 내성 체크 -4", "임시 HP 1 tick"],
                    "가디언의 심판":["적의 데미지 롤", "1 full round"],
                    "오버클럭":["주는 피해와 받는 피해가 모두", "임시 HP 2 ticks"]}
        for name, phrases in expected.items():
            e = Engine(self.rules, 1)
            c = Combatant(self.rules, build_trainer(self.rules, "test", 5, {s:10 for s in self.pokemon()["stats"]}, extra={"feats":[name]}))
            ITEMS.register_feats(e,c)
            before=copy.deepcopy((c.spec,getattr(c,'_action_history',[])))
            result=ITEMS.manual_feat(e,c,name)
            record=next(x for x in c.registry if x.get('type')=='feat_manual' and x.get('name')==name)
            if record['activation_header']['frequency'].get('action')=='static':
                self.assertEqual(result,(0,1))
                self.assertEqual((c.spec,getattr(c,'_action_history',[])),before)
                self.assertFalse(e.gm_prompts)
                # Source procedure text only: Static event eligibility is not
                # implemented by directly invoking this GM payload component.
                FX.run_effects(e,c,c,record['effects'],{'attacker':c,'target':c,'hit':True,'engine':e},record['usage_key'])
            self.assertTrue(e.gm_prompts)
            for phrase in phrases:
                self.assertIn(phrase, e.gm_prompts[-1]["text"])

    def test_flashbang_use_surfaces_corrected_range(self):
        e = Engine(self.rules, 1); c = Combatant(self.rules, self.pokemon())
        before = set(c.conditions)
        ITEMS.use_item(e, c, "플래시뱅 [위험:전문 기술학]", c, free=True)
        self.assertTrue(e.gm_prompts)
        self.assertIn("19–20", e.gm_prompts[-1]["text"])
        self.assertEqual(c.conditions, before)  # No automatic flinch without an accuracy roll.

if __name__ == "__main__":
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MaintenanceTests))
    text=stream.getvalue()
    (ROOT/"output/maintenance-tests.md").write_text("# Maintenance regression tests\n\n```text\n"+text+"```\n",encoding="utf-8")
    print(text)
    sys.exit(0 if result.wasSuccessful() else 1)
