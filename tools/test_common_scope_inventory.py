"""Integrity mutations for draft scope reviews; semantic coverage stays unknown."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_common_source_inventory as PHYSICAL
from audit_common_scope_inventory import validate, summarize


class CommonScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "input").mkdir()
        (self.root / "input/a.md").write_text("# A heading containing a rule\n\nA conditional rule [img]\n\nReading guidance.\n", encoding="utf-8")
        (self.root / "input/b.md").write_text("# Unreviewed source\n", encoding="utf-8")
        (self.root / "input/c.csv").write_text("name,value\nx,1\n", encoding="utf-8")
        self.inventory = PHYSICAL.build(self.root)
        self.graph = dict(nodes=[dict(id="rulebook"), dict(id="time.duration")])
        blocks = [b for b in self.inventory["blocks"] if b["file"] == "input/a.md"]
        self.review = dict(file="input/a.md", source_sha256=self.inventory["files"][0]["sha256"],
                           review_scope="Direct saved-text reading; visuals unresolved.", whole_source_complete=False,
                           blocks=[], clauses=[], remaining=["Original illustrations and atomicity remain unverified."])
        for i, b in enumerate(blocks):
            cid = "CA-" + str(i)
            self.review["blocks"].append(dict(block_id=b["id"], classification="common_normative" if i < 2 else "guidance",
                reason="A directly inspected definition." if i < 2 else "Reading advice, no executable condition.",
                clause_ids=[cid] if i < 2 else [], unresolved=["Original image not reviewed"] if i == 1 else []))
            if i < 2:
                self.review["clauses"].append(dict(id=cid, block_ids=[b["id"]], statement="Conditional rule candidate.",
                    conditions=["Declared event"], exceptions=[], symbol_refs=["time.duration"], status="draft",
                    atomicity="atomic_candidate", remaining=["Independent semantic review pending"]))

    def tearDown(self):
        self.temp.cleanup()

    def errors(self, review=None, inventory=None, graph=None, reviews=None):
        return validate(self.inventory if inventory is None else inventory,
                        reviews if reviews is not None else [self.review if review is None else review],
                        self.graph if graph is None else graph, self.root)

    def assert_error(self, prefix, **kwargs):
        errors = self.errors(**kwargs)
        self.assertTrue(any(e.startswith(prefix) for e in errors), errors)

    def test_valid_draft_including_normative_heading_is_accepted(self):
        self.assertEqual(self.errors(), [])

    def test_counts_distinguish_reviewed_blocks_candidates_and_unknown_denominator(self):
        report = summarize(self.inventory, [self.review], self.errors())
        self.assertEqual((report["source_files"], report["reviewed_files"], report["unreviewed_files"]), (3, 1, 2))
        self.assertEqual((report["source_blocks"], report["reviewed_blocks"], report["unreviewed_blocks"]), (4, 3, 1))
        self.assertEqual(report["candidate_clauses"], 2)
        self.assertIsNone(report["common_clause_total"])
        self.assertIsNone(report["semantic_coverage_percent"])
        self.assertFalse(report["whole_rule_certified"])
        self.assertEqual(report["classifications"], {"common_normative":2, "guidance":1})

    def test_zero_reviews_are_incomplete_but_not_fabricated_error(self):
        self.assertEqual(self.errors(reviews=[]), [])
        report = summarize(self.inventory, [])
        self.assertEqual((report["reviewed_files"], report["unreviewed_files"], report["unreviewed_blocks"]), (0, 3, 4))
        self.assertIsNone(report["common_clause_total"])

    def test_stale_review_hash_is_rejected(self):
        self.review["source_sha256"] = "0" * 64
        self.assert_error("stale_review_source:")

    def test_modified_source_is_rejected_even_when_review_matches_old_inventory(self):
        (self.root / "input/a.md").write_text("changed\n", encoding="utf-8")
        self.assert_error("source_file_changed:")

    def test_unknown_review_file_is_rejected(self):
        self.review["file"] = "input/missing.md"
        self.assert_error("unknown_review_file:")

    def test_duplicate_review_file_is_rejected(self):
        self.assert_error("duplicate_review_file:", reviews=[self.review, copy.deepcopy(self.review)])

    def test_missing_review_block_is_rejected(self):
        self.review["blocks"].pop()
        self.assert_error("review_block_partition_mismatch:")

    def test_duplicate_review_block_is_rejected(self):
        self.review["blocks"].append(copy.deepcopy(self.review["blocks"][0]))
        self.assert_error("duplicate_review_block:")

    def test_unknown_review_block_is_rejected(self):
        self.review["blocks"][2]["block_id"] = "input/a.md:99-99"
        self.assert_error("unknown_review_block:")

    def test_physical_overlap_is_rejected(self):
        self.inventory["blocks"].append(copy.deepcopy(self.inventory["blocks"][0]))
        self.assert_error("overlapping_source_blocks:")

    def test_physical_gap_is_rejected(self):
        self.inventory["blocks"].pop(0)
        self.assert_error("nonblank_line_partition_mismatch:")

    def test_fabricated_physical_id_is_rejected(self):
        self.inventory["blocks"][0]["id"] = "invented"
        self.assert_error("physical_block_mismatch:")

    def test_removing_physical_image_flag_is_rejected(self):
        self.inventory["blocks"][1]["flags"] = []
        self.assert_error("physical_block_mismatch:")

    def test_image_cannot_be_silently_classified_resolved(self):
        self.review["blocks"][1]["classification"] = "guidance"
        self.review["blocks"][1]["unresolved"] = []
        self.assert_error("unresolved_visual_erased:")

    def test_normative_block_requires_clause(self):
        self.review["blocks"][0]["clause_ids"] = []
        self.assert_error("normative_block_without_clause:")

    def test_mixed_block_requires_clause(self):
        self.review["blocks"][2]["classification"] = "mixed"
        self.assert_error("normative_block_without_clause:")

    def test_unknown_clause_link_is_rejected(self):
        self.review["blocks"][0]["clause_ids"].append("missing")
        self.assert_error("unknown_clause_link:")

    def test_missing_clause_backlink_is_rejected(self):
        self.review["clauses"][0]["block_ids"] = [self.review["blocks"][1]["block_id"]]
        self.assert_error("missing_clause_backlink:")

    def test_missing_block_backlink_is_rejected(self):
        self.review["clauses"][0]["block_ids"].append(self.review["blocks"][2]["block_id"])
        self.assert_error("missing_block_backlink:")

    def test_clause_cannot_reference_other_source_block(self):
        self.review["clauses"][0]["block_ids"].append("input/b.md:1-1")
        self.assert_error("unknown_clause_block:")

    def test_duplicate_candidate_ids_are_rejected(self):
        self.review["clauses"].append(copy.deepcopy(self.review["clauses"][0]))
        self.assert_error("duplicate_clause_id:")

    def test_duplicate_links_are_rejected(self):
        self.review["blocks"][0]["clause_ids"] *= 2
        self.review["clauses"][0]["block_ids"] *= 2
        self.assert_error("duplicate_block_clause_link:")
        self.assert_error("duplicate_clause_block_link:")

    def test_unknown_symbol_is_rejected(self):
        self.review["clauses"][0]["symbol_refs"] = ["invented.symbol"]
        self.assert_error("unknown_or_empty_clause_symbols:")

    def test_missing_symbol_binding_is_rejected(self):
        self.review["clauses"][0]["symbol_refs"] = []
        self.assert_error("unknown_or_empty_clause_symbols:")

    def test_verified_candidate_status_is_rejected(self):
        self.review["clauses"][0]["status"] = "verified"
        self.assert_error("unsupported_clause_status:")

    def test_unsupported_atomicity_is_rejected(self):
        self.review["clauses"][0]["atomicity"] = "proven_atomic"
        self.assert_error("invalid_clause_atomicity:")

    def all_markdown_reviews(self):
        b=next(b for b in self.inventory['blocks'] if b['file']=='input/b.md')
        f=next(f for f in self.inventory['files'] if f['file']=='input/b.md')
        other=dict(file=f['file'],source_sha256=f['sha256'],review_scope='Heading only.',whole_source_complete=False,
            blocks=[dict(block_id=b['id'],classification='structural',reason='Heading only.',clause_ids=[],unresolved=[])],
            clauses=[],remaining=['Live original unverified'])
        return [self.review,other]

    def test_complete_markdown_partition_does_not_certify_rules_or_tabular_sources(self):
        reviews=self.all_markdown_reviews()
        self.assertEqual(self.errors(reviews=reviews),[])
        report=summarize(self.inventory,reviews,self.errors(reviews=reviews))
        self.assertTrue(report['saved_markdown_partition_complete'])
        self.assertEqual(report['unreviewed_files'],1)
        self.assertEqual(report['nonmarkdown_files'],1)
        self.assertIsNone(report['common_clause_total'])
        self.assertIsNone(report['semantic_coverage_percent'])
        self.assertFalse(report['whole_rule_certified'])
        self.assertFalse(report['whole_source_complete'])

    def test_integrity_error_prevents_partition_completion(self):
        reviews=self.all_markdown_reviews()
        reviews[0]['blocks'][0]['classification']='invalid'
        report=summarize(self.inventory,reviews,self.errors(reviews=reviews))
        self.assertFalse(report['saved_markdown_partition_complete'])

    def test_missing_markdown_file_prevents_partition_completion(self):
        report=summarize(self.inventory,[self.review],self.errors())
        self.assertFalse(report['saved_markdown_partition_complete'])

    def errata_review(self):
        return json.loads((ROOT/'data/verification/common-source-reviews/supp-errata.json').read_text(encoding='utf-8'))

    def test_errata_preamble_scope_is_document_wide(self):
        c=next(c for c in self.errata_review()['clauses'] if c['id']=='ERRATA-001')
        self.assertEqual(c['packet'],'document-wide')
        self.assertIn('input/supp-errata.md:5-5',c['block_ids'])
        self.assertIn('input/supp-errata.md:7-7',c['block_ids'])

    def test_study_manual_scope_constraint_is_not_excluded_as_flavor(self):
        d=self.errata_review()
        b=next(b for b in d['blocks'] if b['block_id']=='input/supp-errata.md:282-282')
        c=next(c for c in d['clauses'] if c['id']=='ERRATA-031')
        self.assertEqual(b['classification'],'domain_normative')
        self.assertIn(c['id'],b['clause_ids'])
        self.assertIn(b['block_id'],c['block_ids'])
        self.assertIn('단일 스킬',c['source_text'])
        self.assertTrue(any('좁은 분야' in condition for condition in c['conditions']))

    def test_errata_use_trigger_is_not_strengthened_to_hit(self):
        c=next(c for c in self.errata_review()['clauses'] if c['id']=='ERRATA-045')
        self.assertIn('사용할 때마다',c['source_text'])
        self.assertIn('맞힐 때마다',c['source_text'])
        self.assertEqual(c['trigger_terms']['rank_1'],'use_spray_on_target')
        self.assertEqual(c['trigger_terms']['rank_2'],'hit_target_with_spray_or_filth_bomb')

    def test_capture_example_arithmetic_conflict_is_retained(self):
        c=next(c for c in self.errata_review()['clauses'] if c['id']=='ERRATA-078')
        conflict=c['arithmetic_conflict']
        self.assertEqual(conflict['arithmetic_result'],10+8-4-2-4)
        self.assertEqual(conflict['source_result'],10)
        self.assertNotEqual(conflict['arithmetic_result'],conflict['source_result'])
        self.assertEqual(conflict['status'],'unresolved_source_conflict')
        self.assertIn('= 10',c['source_text'])
        self.assertFalse(self.errata_review()['whole_source_complete'])

    def test_full_source_certification_is_rejected(self):
        self.review["whole_source_complete"] = True
        self.assert_error("unsupported_source_completion:")

    def test_numeric_false_is_not_explicit_false(self):
        self.review["whole_source_complete"] = 0
        self.assert_error("unsupported_source_completion:")

    def test_invented_semantic_denominator_is_rejected(self):
        self.inventory["source_clause_total"] = 2
        self.assert_error("unsupported_physical_semantic_denominator")

    def test_invalid_classification_or_missing_reason_is_rejected(self):
        self.review["blocks"][0]["classification"] = "verified"
        self.review["blocks"][0]["reason"] = ""
        self.assert_error("invalid_block_classification:")
        self.assert_error("missing_block_reason:")

    def test_conditions_exceptions_and_remaining_are_explicit_lists(self):
        self.review["clauses"][0]["conditions"] = None
        self.review["clauses"][0]["exceptions"] = "none"
        self.review["clauses"][0]["remaining"] = None
        self.assert_error("invalid_clause_conditions:")
        self.assert_error("invalid_clause_exceptions:")
        self.assert_error("invalid_clause_remaining:")

    def test_statement_group_still_counts_only_as_candidate(self):
        self.review["clauses"][0]["atomicity"] = "statement_group"
        self.assertEqual(self.errors(), [])
        report = summarize(self.inventory, [self.review])
        self.assertEqual(report["candidate_clauses"], 2)
        self.assertIsNone(report["common_clause_total"])


if __name__ == "__main__":
    class Result(unittest.TextTestResult):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.rows = []
        def addSuccess(self, t):
            super().addSuccess(t)
            self.rows.append(dict(id="COMMON-SCOPE-" + t._testMethodName, status="pass"))
        def addFailure(self, t, err):
            super().addFailure(t, err)
            self.rows.append(dict(id="COMMON-SCOPE-" + t._testMethodName, status="fail"))
        def addError(self, t, err):
            super().addError(t, err)
            self.rows.append(dict(id="COMMON-SCOPE-" + t._testMethodName, status="error"))
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(CommonScopeTests))
    paths = ["tools/test_common_scope_inventory.py", "tools/audit_common_scope_inventory.py", "tools/audit_common_source_inventory.py", "data/verification/common-source-reviews/supp-errata.json", "input/supp-errata.md"]
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), scope="Integrity mutations and independently found source-review regression guards; no runtime or semantic completeness proof.",
                  tests_run=result.testsRun, results=result.rows, common_clause_total=None,
                  input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (ROOT / "output/common-scope-inventory-tests.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
