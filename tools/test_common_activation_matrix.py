from pathlib import Path
import sys,unittest,json,copy,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from audit_common_activation_matrix import validate,REL
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.spec=json.loads((ROOT/REL).read_text(encoding='utf8'))
 def rejects(self,mutate,match):
  x=copy.deepcopy(self.spec);mutate(x);self.assertTrue(any(match in e for e in validate(x,ROOT)),match)
 def test_001_real_matrix_exact_links(self):self.assertEqual(validate(self.spec,ROOT),[])
 def test_002_missing_condition(self):self.rejects(lambda x:x['conditions'].pop(),'condition_set_mismatch')
 def test_003_duplicate_condition(self):self.rejects(lambda x:x['conditions'].append(copy.deepcopy(x['conditions'][0])),'condition_set_mismatch')
 def test_004_missing_interface(self):self.rejects(lambda x:x['interfaces'].pop(),'interface_set_mismatch')
 def test_005_missing_transition(self):self.rejects(lambda x:x['transitions'].pop(),'transition_set_mismatch')
 def test_006_missing_transition_obligation(self):self.rejects(lambda x:x['transitions'][0]['condition_ids'].pop(),'transition_link_mismatch')
 def test_007_invented_source(self):self.rejects(lambda x:x['source_anchors'][0].update(excerpt='invented'),'source_excerpt_drift')
 def test_008_pending_is_not_implementation(self):self.rejects(lambda x:x['conditions'][0].update(runtime_status='pending_only',semantic_support_counted=True),'pending_counted_as_implementation')
 def test_009_missing_exit(self):self.rejects(lambda x:x['conditions'][0].pop('exit_evidence'),'missing_semantics_or_exit')
 def test_010_whole_closure_rejected(self):self.rejects(lambda x:x.update(whole_root_complete=True),'unsupported_global_closure')
 def test_011_no_evidence_completion_rejected(self):
  self.rejects(lambda x:next(c for c in x['conditions'] if c['id']=='ROOT-08').update(evidence_refs=[]),'unsupported_bounded_closure')
 def test_012_bad_category(self):self.rejects(lambda x:x['conditions'][0].update(exit_category='GM_can_fix_everything'),'bad_exit_category')
 def test_013_fake_runtime_location(self):
  self.rejects(lambda x:next(c for c in x['conditions'] if c['id']=='ROOT-08')['runtime_paths'][0].update(start=1),'runtime_excerpt_drift')
 def test_014_orphan_remaining_rejected(self):self.rejects(lambda x:x['conditions'][0].update(work_packet_ids=[]),'orphan_remaining')
 def test_015_work_backlink_missing(self):self.rejects(lambda x:x['known_remaining_work_packets'][0].update(condition_ids=[]),'work_link_mismatch')
 def test_016_missing_domain(self):self.rejects(lambda x:next(c for c in x['conditions'] if c['id']=='ROOT-08').pop('bounded_domain'),'missing_bounded_domain')
 def test_017_missing_independent_case(self):self.rejects(lambda x:next(c for c in x['conditions'] if c['id']=='ROOT-08').update(independent_test_ids=[]),'missing_independent_case')
class Result(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'ACTIVATION-MATRIX-'+t._testMethodName,'status':'pass'})
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':'ACTIVATION-MATRIX-'+t._testMethodName,'status':'fail'})
 def addError(self,t,e):super().addError(t,e);self.rows.append({'id':'ACTIVATION-MATRIX-'+t._testMethodName,'status':'error'})
if __name__=='__main__':
 r=unittest.TextTestRunner(verbosity=1,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests));files=[REL,'tools/audit_common_activation_matrix.py','tools/test_common_activation_matrix.py'];report={'results':r.rows,'tests_run':r.testsRun,'test_kind':'integrity/adversarial metadata, no new gameplay runtime proof','input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}}
 (ROOT/'output/common-activation-matrix-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');sys.exit(not r.wasSuccessful())
