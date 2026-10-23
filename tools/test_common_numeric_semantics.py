"""Mutation tests for source/spec integrity; no runtime arithmetic certification."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_common_numeric_semantics as audit
ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT/'data/verification/common-numeric-semantics.json'


class NumericSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(SPEC_PATH.read_text(encoding='utf-8'))

    def rejected(self, change, fragment):
        spec = deepcopy(self.spec)
        change(spec)
        errors = audit.validate(spec, ROOT)
        self.assertTrue(any(fragment in error for error in errors), errors)

    def test_actual_sources_and_references(self):
        self.assertEqual(audit.validate(self.spec, ROOT), [])

    def test_explicit_local_status_inventory(self):
        from collections import Counter
        self.assertEqual(Counter(r['status'] for r in self.spec['typed_semantics']['relations']), {'resolved':7,'provisional':3,'unresolved':4})
        self.assertEqual(Counter(a['kind'] for a in self.spec['source_anchors']), {'markdown':11,'pdf':6})

    def test_unknown_anchor_kind(self):
        self.rejected(lambda s:s['source_anchors'][0].update(kind='html'), 'unknown anchor kind')

    def test_unknown_anchor_kind_shape(self):
        self.rejected(lambda s:s['source_anchors'][0].update(kind=[]), 'unknown anchor kind')

    def test_missing_anchor(self):
        self.rejected(lambda s:s['source_anchors'].pop(), 'missing/unknown ids')

    def test_duplicate_anchor(self):
        self.rejected(lambda s:s['source_anchors'].append(deepcopy(s['source_anchors'][0])), 'duplicate id')

    def test_source_file_hash_tamper(self):
        self.rejected(lambda s:s['source_anchors'][0].update(file_sha256='0'*64), 'actual source hash mismatch')

    def test_excerpt_hash_tamper(self):
        self.rejected(lambda s:s['source_anchors'][0].update(excerpt_sha256='0'*64), 'excerpt hash mismatch')

    def test_rehashed_false_markdown_excerpt(self):
        def change(s):
            a=s['source_anchors'][0];a['excerpt']='fabricated excerpt';a['excerpt_sha256']=audit.sha(a['excerpt'].encode())
        self.rejected(change, 'actual line excerpt mismatch')

    def test_invalid_markdown_line_range(self):
        self.rejected(lambda s:s['source_anchors'][0].update(line_start=0), 'invalid line range')

    def test_wrong_markdown_line_range(self):
        self.rejected(lambda s:s['source_anchors'][0].update(line_start=6), 'actual line excerpt mismatch')

    def test_path_escape(self):
        self.rejected(lambda s:s['source_anchors'][0].update(file='../outside.md'), 'source path escapes root')

    def test_pdf_page_hash_tamper(self):
        self.rejected(lambda s:next(a for a in s['source_anchors'] if a['kind']=='pdf').update(page_text_sha256='0'*64), 'actual PDF page text hash mismatch')

    def test_rehashed_false_pdf_excerpt(self):
        def change(s):
            a=next(a for a in s['source_anchors'] if a['kind']=='pdf');a['excerpt']='fabricated excerpt';a['excerpt_sha256']=audit.sha(a['excerpt'].encode())
        self.rejected(change, 'PDF excerpt not found')

    def test_pdf_wrong_page(self):
        def change(s):
            a=next(a for a in s['source_anchors'] if a['kind']=='pdf');a['page_index']+=1;a['printed_page']+=1
        self.rejected(change, 'actual PDF page text hash mismatch')

    def test_symbol_must_exist(self):
        self.rejected(lambda s:s['typed_semantics']['relations'][0].update(symbol='math.invented'), 'unknown symbol')

    def test_missing_relation(self):
        self.rejected(lambda s:s['typed_semantics']['relations'].pop(), 'missing/unknown ids')

    def test_unknown_relation_status(self):
        self.rejected(lambda s:s['typed_semantics']['relations'][0].update(status='certified'), 'reviewed local status')

    def test_provisional_cannot_be_upgraded(self):
        self.rejected(lambda s:s['typed_semantics']['relations'][3].update(status='resolved'), 'reviewed local status')

    def test_condition_sources_must_exist(self):
        self.rejected(lambda s:s['typed_semantics']['relations'][0]['sources'].append('K-missing'), 'unknown source reference')

    def test_condition_must_retain_local_scope(self):
        self.rejected(lambda s:s['typed_semantics']['relations'][0].update(resolution_scope='global'), 'local_only')

    def test_condition_requires_applicability(self):
        self.rejected(lambda s:s['typed_semantics']['relations'][0].update(conditions=[]), 'conditions must be')

    def test_case_condition_backreference(self):
        self.rejected(lambda s:s['boundary_oracles'][0].update(condition='N14'), 'backreference')

    def test_case_unknown_condition(self):
        self.rejected(lambda s:s['boundary_oracles'][0].update(condition='N99'), 'unknown condition')

    def test_case_source_cannot_escape_condition(self):
        self.rejected(lambda s:s['boundary_oracles'][0]['source_anchors'].append('K-hp'), 'not grounded in condition')

    def test_missing_oracle_reference(self):
        self.rejected(lambda s:s['typed_semantics']['relations'][0].update(oracle_refs=[]), 'backreference')

    def test_missing_oracle_payload(self):
        self.rejected(lambda s:s['boundary_oracles'][0].pop('expected'), 'missing boundary case payload')

    def test_unresolved_case_cannot_pass_gate(self):
        self.rejected(lambda s:s['boundary_oracles'][6].update(gate_pass_allowed=True), 'unresolved case must prohibit')

    def test_conditional_boundary_cannot_be_global(self):
        self.rejected(lambda s:s['boundary_oracles'][2].update(does_not_set_global_boundary=False), 'global boundary')

    def test_ceil_does_not_resolve_contest_operand(self):
        self.rejected(lambda s:s['boundary_oracles'][3].update(contest_input_count_unresolved=False), 'operand uncertainty')

    def test_unknown_oracle_kind(self):
        self.rejected(lambda s:s['boundary_oracles'][0].update(kind='runtime_verified'), 'unknown oracle kind')

    def test_no_whole_semantic_completion(self):
        for flag in ('whole_semantic_complete','implementation_conformance_proved','semantic_coverage_proved'):
            with self.subTest(flag=flag):
                self.rejected(lambda s,flag=flag:s.update({flag:True}), flag+' must remain false')

    def test_source_authority_cannot_auto_override(self):
        self.rejected(lambda s:s['source_authority'].update(ptu_automatically_overrides_ptk=True), 'must remain false')

    def test_source_resolution_does_not_complete_whole_rule(self):
        self.rejected(lambda s:s['source_authority'].update(resolved_means_whole_rule=True), 'must remain false')

    def test_runtime_review_and_old_hashes_are_forbidden(self):
        for field in ('runtime_review','input_hashes','current_conformance'):
            self.rejected(lambda s,field=field:s.update({field:{}}), 'historical/runtime evidence forbidden')

    def test_nested_old_observation_is_forbidden(self):
        self.rejected(lambda s:s['boundary_oracles'][12]['cases'][0].update(actual_per_player=50), 'historical/runtime evidence forbidden')

    def test_no_unchecked_runtime_conformance_in_oracle(self):
        self.rejected(lambda s:s['boundary_oracles'][12].update(runtime_conformance='pass'), 'without runtime conformance')

    def test_source_mutation_and_pdf_cache_use_current_hash(self):
        # Independent temporary corpus: never modify project inputs during a test.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            files={a['file'] for a in self.spec['source_anchors']}|{'data/verification/rule-symbol-graph.json'}
            for relative in files:
                target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
            spec=deepcopy(self.spec)
            self.assertEqual(audit.validate(spec,root),[])
            cached=audit._pdf_text.cache_info()
            self.assertEqual(audit.validate(spec,root),[])
            self.assertEqual(audit._pdf_text.cache_info().misses,cached.misses)
            pdf=next(a['file'] for a in spec['source_anchors'] if a['kind']=='pdf')
            with (root/pdf).open('ab') as handle:handle.write(b'\n')
            self.assertTrue(any('actual source hash mismatch' in x for x in audit.validate(spec,root)))
            digest=audit.sha((root/pdf).read_bytes())
            for a in spec['source_anchors']:
                if a['file']==pdf:a['file_sha256']=digest
            self.assertEqual(audit.validate(spec,root),[])
            self.assertGreater(audit._pdf_text.cache_info().misses,cached.misses)
            md=root/spec['source_anchors'][0]['file']
            with md.open('ab') as handle:handle.write(b'\nchanged source\n')
            self.assertTrue(any('actual source hash mismatch' in x for x in audit.validate(spec,root)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--spec',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();ROOT=args.root.resolve();SPEC_PATH=args.spec or ROOT/'data/verification/common-numeric-semantics.json'
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='MATH-SPEC-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='MATH-SPEC-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='MATH-SPEC-'+t._testMethodName,status='error'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(NumericSpecTests))
    spec=json.loads(SPEC_PATH.read_text(encoding='utf-8'))
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Supporting numeric spec integrity and rejection of mutations; no runtime arithmetic or complete semantic proof.',results=result.rows,input_hashes=audit.input_hashes(spec,ROOT,[Path(__file__),Path(audit.__file__),SPEC_PATH]),whole_semantic_complete=False)
    output=args.output or ROOT/'output/common-numeric-semantics-tests.json'
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
