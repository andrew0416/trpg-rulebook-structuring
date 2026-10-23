"""Mutation tests for scope-review integrity, not semantic correctness."""
from __future__ import annotations
import argparse,copy,json,shutil,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from audit_root_authority_scope import validate,build_report,input_hashes,load,digest,SPEC,ROOT,GRAPH,ATOMS,REVIEWS,_anchor

REAL_ROOT=ROOT;REAL_SPEC=ROOT/SPEC
class ScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real_spec=load(REAL_SPEC)
        cls.tmp=tempfile.TemporaryDirectory(prefix='root-authority-scope-tests-')
        cls.root=Path(cls.tmp.name)
        files=set(input_hashes(cls.real_spec,REAL_ROOT,REAL_SPEC))
        files.discard(SPEC);files.discard('tools/audit_root_authority_scope.py')
        for rel in files:
            dest=cls.root/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REAL_ROOT/rel,dest)
        dest=cls.root/SPEC;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REAL_SPEC,dest)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):self.spec=copy.deepcopy(self.real_spec)
    def errors(self):return validate(self.spec,self.root)
    def reject(self,prefix):
        errors=self.errors()
        self.assertTrue(any(e.startswith(prefix) for e in errors),(prefix,errors))
    def test_current_real_data(self):self.assertEqual(validate(self.real_spec,REAL_ROOT),[])
    def test_isolated_fixture_passes(self):self.assertEqual(self.errors(),[])
    def test_missing_candidate(self):
        self.spec['candidate_dispositions'].pop();self.reject('scope_candidate_set')
    def test_duplicate_candidate(self):
        self.spec['candidate_dispositions'].append(copy.deepcopy(self.spec['candidate_dispositions'][0]));self.reject('scope_candidate_set')
    def test_original_candidate_condition_mutation(self):
        self.spec['candidate_dispositions'][0]['original_candidate']['conditions'].append('invented')
        self.reject('scope_original_candidate_mismatch:')
    def test_original_candidate_keeps_all_fields(self):
        del self.spec['candidate_dispositions'][0]['original_candidate']['remaining']
        self.reject('scope_original_candidate_mismatch:')
    def test_same_file_true_but_unrelated_excerpt(self):
        d=self.spec['candidate_dispositions'][0];f=d['anchors'][0]['file']
        d['anchors']=[_anchor(self.root,f+':1-1')]
        self.reject('scope_candidate_anchor_relation:')
        self.assertFalse(any(e.startswith('scope_anchor_mismatch:') for e in self.errors()))
    def test_wrong_excerpt_with_real_parent_range(self):
        self.spec['candidate_dispositions'][0]['anchors'][0]['excerpt']='changed'
        self.reject('scope_anchor_mismatch:')
    def test_wrong_excerpt_hash(self):
        self.spec['candidate_dispositions'][0]['anchors'][0]['excerpt_sha256']='0'*64
        self.reject('scope_anchor_mismatch:')
    def test_source_hash_mismatch(self):
        self.spec['source_and_review_snapshots'][0]['source_sha256']='0'*64
        self.reject('scope_source_hash:')
    def test_five_source_snapshot_missing(self):
        self.spec['source_and_review_snapshots'].pop();self.reject('scope_source_snapshot_set')
    def test_twenty_review_snapshot_missing(self):
        self.spec['authority_index_snapshot']['reviews'].pop();self.reject('scope_review_snapshot_set')
    def test_outside_selected_review_hash_protected(self):
        r=next(r for r in self.spec['authority_index_snapshot']['reviews'] if r['file'].endswith('ch03.json'))
        r['sha256']='0'*64;self.reject('scope_review_snapshot_hash:')
    def test_live_source_change_detected(self):
        rel=self.spec['source_and_review_snapshots'][0]['source_file'];p=self.root/rel;old=p.read_bytes()
        try:
            p.write_bytes(old+b'\nchange\n');self.reject('scope_source_hash:')
        finally:p.write_bytes(old)
    def test_changed_live_review_with_refreshed_hash_still_rejects_stale_candidate(self):
        rel=f'{REVIEWS}/ch00.json';p=self.root/rel;old=p.read_bytes();v=load(p)
        v['clauses'][0]['statement']+=' changed live candidate'
        try:
            p.write_text(json.dumps(v,ensure_ascii=False),encoding='utf-8')
            for d in self.spec['source_and_review_snapshots']:
                if d['review_file']==rel:d['review_sha256']=digest(p)
            for d in self.spec['authority_index_snapshot']['reviews']:
                if d['file']==rel:d['sha256']=digest(p)
            self.reject('scope_original_candidate_mismatch:')
        finally:p.write_bytes(old)
    def test_fake_parent_symbol(self):
        self.spec['candidate_dispositions'][0]['parent_relation']['symbol']='fake.authority'
        self.reject('scope_parent_symbol:')
    def test_fake_atom_reference(self):
        self.spec['candidate_dispositions'][0]['related_existing_atom_ids']=['RA-NONEXISTENT']
        self.reject('scope_atom_reference:')
    def test_original_scope_guard_preserved(self):
        self.spec['candidate_dispositions'][0]['parent_relation']['scope_guard']=[]
        self.reject('scope_parent_conditions:')
    def test_original_exceptions_preserved(self):
        d=next(d for d in self.spec['candidate_dispositions'] if d['original_candidate']['exceptions'])
        d['parent_relation']['exceptions_preserved']=[]
        self.reject('scope_parent_conditions:')
    def test_root_completion_false(self):
        self.spec['completion']=True;self.reject('unsupported_scope_completion')
    def test_whole_completion_false(self):
        self.spec['scope']['whole_rulebook_semantics_complete']=True
        self.reject('unsupported_scope_completion:whole_rulebook_semantics_complete')
    def test_atomic_completion_false(self):
        self.spec['candidate_dispositions'][0]['atomic_coverage_complete']=True
        self.reject('unsupported_scope_candidate_completion:')
    def test_gap_cannot_claim_atom_completion(self):
        self.spec['newly_found_gaps'][0]['atomic_coverage_complete']=True
        self.reject('scope_gap_status:')
    def test_proposal_cannot_claim_verified_status(self):
        self.spec['suggested_atomic_clause_splits'][0]['status']='verified'
        self.reject('scope_proposal_status:')
    def test_proposal_semantic_completion_false(self):
        self.spec['suggested_atomic_clause_splits'][0]['semantic_validation_complete']=True
        self.reject('scope_proposal_status:')
    def test_extra_certification_flag_rejected(self):
        self.spec['whole_rule_certified']=True
        self.reject('unsupported_scope_certification:')
    def test_bad_gap_candidate_relation(self):
        g=next(g for g in self.spec['newly_found_gaps'] if g['existing_review_candidates'])
        g['existing_review_candidates'][0]['candidate_id']='C00-001'
        self.reject('scope_gap_candidate_relation:')
    def test_proposal_bad_gap_reference(self):
        self.spec['suggested_atomic_clause_splits'][0]['source_gap_ids']=['RSG-INVALID']
        self.reject('scope_proposal_gap_reference:')
    def test_proposal_same_file_unrelated_anchor(self):
        p=self.spec['suggested_atomic_clause_splits'][0];f=p['anchors'][0]['file']
        p['anchors']=[_anchor(self.root,f+':1-1')]
        self.reject('scope_proposal_anchor_relation:')
    def test_proposal_missing_boundary(self):
        self.spec['suggested_atomic_clause_splits'][0]['boundary']=''
        self.reject('scope_proposal_boundary:')
    def test_wrong_scope_counts(self):
        self.spec['scope']['denominator']['this_review_candidates']=94
        self.reject('scope_denominator_mismatch')
    def test_malformed_anchor_and_reference_return_errors(self):
        d=self.spec['candidate_dispositions'][0]
        d['anchors']=[dict(file={},start='a',end=None,excerpt='x',excerpt_sha256='x')]
        d['parent_relation']['symbol']={}
        d['related_existing_atom_ids']=[{}]
        d['category']={}
        e=self.errors()
        self.assertTrue(any(x.startswith('invalid_scope_anchor:') for x in e))
        self.assertTrue(any(x.startswith('scope_parent_symbol:') for x in e))
        self.assertTrue(any(x.startswith('scope_atom_reference:') for x in e))
        self.assertTrue(any(x.startswith('scope_category:') for x in e))
    def test_editorial_reason_not_frozen_as_semantic_proof(self):
        self.spec['candidate_dispositions'][0]['reason']='A new manual explanation, requiring independent semantic review.'
        self.spec['suggested_atomic_clause_splits'][0]['suggested_atomic_statements'][0]='Edited draft statement.'
        self.assertEqual(self.errors(),[])
    def test_report_integrity_is_not_semantic_coverage(self):
        r=build_report(self.spec,self.root,self.root/SPEC)
        self.assertEqual(r['status'],'draft_integrity_pass')
        self.assertFalse(r['whole_rule_certified']);self.assertFalse(r['semantic_completeness_proved'])
        self.assertIsNone(r['coverage_percent'])
        self.assertIn(GRAPH,r['input_hashes']);self.assertIn(ATOMS,r['input_hashes'])
        self.assertIn(f'{REVIEWS}/ch03.json',r['input_hashes'])
        self.assertIn('tools/audit_root_authority_scope.py',r['input_hashes'])

def main():
    global REAL_ROOT,REAL_SPEC
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--spec',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    REAL_ROOT=a.root.resolve();REAL_SPEC=a.spec.resolve() if a.spec else REAL_ROOT/SPEC
    class Result(unittest.TextTestResult):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.rows=[]
        def addSuccess(self,test):
            super().addSuccess(test);self.rows.append(dict(id='ROOT-SCOPE-'+test._testMethodName,status='pass'))
        def addFailure(self,test,error):
            super().addFailure(test,error);self.rows.append(dict(id='ROOT-SCOPE-'+test._testMethodName,status='fail'))
        def addError(self,test,error):
            super().addError(test,error);self.rows.append(dict(id='ROOT-SCOPE-'+test._testMethodName,status='error'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(ScopeTests))
    spec=load(REAL_SPEC)
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),whole_rule_certified=False,semantic_completeness_proved=False,
        tests_run=result.testsRun,results=result.rows,limitation='Integrity mutation tests only; no semantic statement snapshots.',
        input_hashes=input_hashes(spec,REAL_ROOT,REAL_SPEC,[('tools/test_root_authority_scope.py',Path(__file__))]))
    out=a.output or REAL_ROOT/'output/root-authority-scope-tests.json'
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())

