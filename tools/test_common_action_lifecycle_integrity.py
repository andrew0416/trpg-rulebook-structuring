"""Adversarial provenance gates: passing here never proves game semantics."""
import copy,json,unittest
import audit_common_action_lifecycle as audit
ROOT=audit.ROOT
class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((ROOT/audit.SPEC).read_text(encoding='utf8'))
        self.bindings=json.loads((ROOT/audit.BINDINGS).read_text(encoding='utf8'))
    def check(self):return audit.validate(self.spec,ROOT,self.bindings)
    def test_current_integrity(self):self.assertEqual(self.check(),[])
    def test_false_whole_closure_rejected(self):
        self.spec['semantic_completeness_proved']=True;self.assertIn('unsupported_action_lifecycle_closure:semantic_completeness_proved',self.check())
    def test_rehashed_false_source_excerpt_rejected(self):
        key=next(iter(self.spec['source_anchors']));a=self.spec['source_anchors'][key];a['excerpt']+=' invented';a['excerpt_sha256']=audit.sha(a['excerpt'].encode());self.assertIn('stale_action_lifecycle_anchor:'+key,self.check())
    def test_missing_clause_rejected(self):
        self.spec['clauses'].pop();self.assertIn('action_lifecycle_clause_set',self.check())
    def test_unknown_symbol_rejected(self):
        self.spec['clauses'][0]['symbol_refs']=['not.a.symbol'];self.assertIn('invalid_action_lifecycle_symbols:COMMON-ACTION-001',self.check())
    def test_unknown_runtime_test_rejected(self):
        self.bindings['bindings'][0]['tests']=['test_nonexistent'];self.assertIn('unknown_action_lifecycle_test:COMMON-ACTION-001',self.check())
    def test_source_aoo_quota_cannot_be_replenished_per_turn(self):
        self.spec['quotas']['aoo']['max_per_round']=2;self.assertIn('changed_source_action_quota',self.check())
    def test_partial_cases_cannot_certify_whole_clause(self):
        self.bindings['bindings'][0]['whole_clause_verified']=True;self.assertIn('unsupported_action_binding_closure:COMMON-ACTION-001',self.check())
    def test_removed_remaining_is_not_completion(self):
        self.bindings['remaining']=[];self.assertIn('unsupported_action_bindings_closure',self.check())
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='ACTION-INTEGRITY-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='ACTION-INTEGRITY-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='ACTION-INTEGRITY-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(IntegrityTests))
    spec=json.loads((ROOT/audit.SPEC).read_text(encoding='utf8'));bindings=json.loads((ROOT/audit.BINDINGS).read_text(encoding='utf8'))
    paths=audit.input_files(spec,bindings)+['tools/test_common_action_lifecycle_integrity.py']
    report=dict(scope='Source/link integrity only',whole_rule_certified=False,results=r.rows,input_hashes={p:audit.sha((ROOT/p).read_bytes()) for p in paths})
    (ROOT/'output/common-action-lifecycle-integrity-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');raise SystemExit(not r.wasSuccessful())
