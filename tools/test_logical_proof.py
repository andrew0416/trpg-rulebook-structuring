import copy,hashlib,json,unittest
from pathlib import Path
from datetime import datetime,timezone
from prove_logical_coverage import prove
ROOT=Path(__file__).resolve().parents[1]
class LogicProofTests(unittest.TestCase):
    def fixture(self):
        model=dict(id='x',variables={'P':'boolean','Q':'boolean'},expression={'op':'and','args':[{'var':'P'},{'var':'Q'}]},scope='fixture',assumptions=[],excluded_obligations=[],independent_truth_table=[
            dict(inputs={'P':False,'Q':False},expected=False),dict(inputs={'P':False,'Q':True},expected=False),dict(inputs={'P':True,'Q':False},expected=False),dict(inputs={'P':True,'Q':True},expected=True)])
        results={str(i):{'status':'pass'} for i in range(4)}
        witnesses={str(i):dict(model_id='x',inputs=r['inputs']) for i,r in enumerate(model['independent_truth_table'])}
        return model,results,witnesses
    def test_exhaustive_truth_table_and_independence(self):
        result=prove(*self.fixture())
        self.assertEqual(result['proof_status'],'proved_for_declared_boolean_model')
        self.assertEqual((result['covered_valuations'],result['valuation_count']),(4,4))
        self.assertTrue(all(c['covered'] for c in result['independent_condition_effects']))
        self.assertFalse(result['whole_rule_certified'])
    def test_missing_execution_witness_is_a_hole(self):
        m,r,w=self.fixture();w.pop('0');result=prove(m,r,w)
        self.assertEqual(result['covered_valuations'],3);self.assertEqual(result['proof_status'],'incomplete')
    def test_skipped_or_failed_test_never_proves_a_valuation(self):
        for status in ['skip','fail','expected_failure']:
            m,r,w=self.fixture();r['3']['status']=status
            self.assertEqual(prove(m,r,w)['proof_status'],'incomplete')
    def test_mutated_operator_has_counterexamples(self):
        m,r,w=self.fixture();m['expression']['op']='or';result=prove(m,r,w)
        self.assertEqual(len(result['counterexamples']),2);self.assertEqual(result['proof_status'],'incomplete')
    def test_missing_oracle_not_self_generated(self):
        m,r,w=self.fixture();m['independent_truth_table'].pop()
        self.assertIn('incomplete_independent_truth_table',prove(m,r,w)['errors'])
    def test_other_model_witness_does_not_count(self):
        m,r,w=self.fixture();w['3']['model_id']='other'
        self.assertEqual(prove(m,r,w)['covered_valuations'],3)
    def test_non_boolean_domain_rejected(self):
        m,r,w=self.fixture();m['variables']['P']='integer'
        with self.assertRaises(ValueError):prove(m,r,w)
    def test_unused_declared_condition_is_not_independently_covered(self):
        m,r,w=self.fixture();m['expression']={'var':'P'}
        for row in m['independent_truth_table']:row['expected']=row['inputs']['P']
        result=prove(m,r,w)
        self.assertFalse(next(c for c in result['independent_condition_effects'] if c['condition']=='Q')['covered'])
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='LOGIC-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='LOGIC-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='LOGIC-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(LogicProofTests))
    paths=[Path(__file__),ROOT/'tools/prove_logical_coverage.py']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Finite-model certificate checker mutation tests, not rule coverage.',results=r.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/logical-proof-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if r.wasSuccessful() else 1)
