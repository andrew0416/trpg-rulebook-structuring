"""Author's independent recheck of peer ownership/tombstone fix, no source closure."""
import copy,json,hashlib,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_bound_ap_release as _fixture_test_bound_ap_release
import effects as FX,action_points as AP
class Recheck(unittest.TestCase):
 @classmethod
 def setUpClass(cls):_fixture_test_bound_ap_release.BoundAPTests.setUpClass()
 def fixture(self):return _fixture_test_bound_ap_release.BoundAPTests().fixture()
 def release(self,e,a,event='R'):return e.release_bound_ap(a,'effect-A',event_id=event)
 def passive(self,x):
  if type(x) in (str,int,float,bool,type(None)):return True
  if type(x) is dict:return all(type(k) is str and self.passive(v) for k,v in x.items())
  if type(x) in (list,tuple):return all(self.passive(v) for v in x)
  return False
 def state(self,e,a,b):return copy.deepcopy((a.spec,a.modifiers,b.modifiers,a.hp,a.temp_hp,a.injuries,a.budget,a._action_history,e.rng.getstate(),e.elapsed_seconds))
 def test_public_share_after_adoption_holds_before_mutation(self):
  e,a,b,m,o=self.fixture();FX.apply_passives(e,b,[m]);before=self.state(e,a,b)
  z=self.release(e,a);self.assertEqual(z.status,'pending');self.assertEqual(z.reason,'shared_modifier_ownership_unresolved')
  self.assertEqual(self.state(e,a,b),before);self.assertIs(a._ap_bound_effects['effect-A']['modifier'],m)
 def test_equal_value_different_owner_object_is_not_shared(self):
  e,a,b,m,o=self.fixture();other=dict(m);FX.apply_passives(e,b,[other]);before=AP.available(a)
  self.assertEqual(self.release(e,a).status,'released');self.assertIs(b.modifiers[0],other)
  self.assertEqual(AP.available(a),before+2);self.assertIs(a.modifiers[0],o)
 def test_tombstone_is_passive_keeps_accounting_and_duplicate_identity(self):
  e,a,b,m,o=self.fixture();before=AP.available(a);self.assertEqual(self.release(e,a).status,'released')
  record=a._ap_bound_effects['effect-A'];self.assertEqual(record['state'],'ended');self.assertTrue(self.passive(record))
  for field in ('owner','modifier'):self.assertNotIn(field,record)
  self.assertEqual(record['amount'],2);self.assertEqual(record['end_event']['id'],'R');self.assertEqual(AP.available(a),before+2)
  snap=self.state(e,a,b);z=self.release(e,a,'new-event');self.assertEqual(z.reason,'effect_already_ended');self.assertEqual(self.state(e,a,b),snap)
 def test_pre_and_post_snapshots_preserve_distinct_lifecycle_shapes(self):
  e,a,b,m,o=self.fixture();before=AP.available(a);e.gm.snapshot('active');self.release(e,a);e.gm.snapshot('ended')
  e.gm.restore('active');r=a._ap_bound_effects['effect-A'];self.assertIs(r['owner'],a);self.assertIs(r['modifier'],a.modifiers[0]);self.assertEqual(AP.available(a),before)
  self.assertEqual(self.release(e,a,'replay').status,'released')
  e.gm.restore('ended');r=a._ap_bound_effects['effect-A'];self.assertTrue(self.passive(r));self.assertEqual(r['end_event']['id'],'R')
  self.assertEqual(AP.available(a),before+2);self.assertEqual(self.release(e,a,'again').reason,'effect_already_ended')
  self.assertEqual(len(a.modifiers),1)
 def test_used_event_id_remains_reserved_after_snapshot(self):
  e,a,b,m,o=self.fixture();self.assertEqual(e.adopt_bound_ap_modifier(a,'effect-B',modifier=o,ending_method='none_specified',source_ref='test_fixture').status,'adopted')
  self.release(e,a);e.gm.snapshot('endedA-activeB');e.gm.restore('endedA-activeB');before=self.state(e,a,b)
  z=e.release_bound_ap(a,'effect-B',event_id='R');self.assertEqual(z.reason,'event_id_already_used');self.assertEqual(self.state(e,a,b),before)
  self.assertEqual(e.release_bound_ap(a,'effect-B',event_id='other').status,'released');self.assertTrue(self.passive(a._ap_bound_effects))
 def test_snapshot_preserves_shared_object_so_revalidation_still_holds(self):
  e,a,b,m,o=self.fixture();FX.apply_passives(e,b,[m]);e.gm.snapshot('shared');e.gm.restore('shared')
  self.assertIs(a.modifiers[0],b.modifiers[0]);self.assertIs(a._ap_bound_effects['effect-A']['modifier'],a.modifiers[0]);before=self.state(e,a,b)
  self.assertEqual(self.release(e,a).reason,'shared_modifier_ownership_unresolved');self.assertEqual(self.state(e,a,b),before)
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'BAP-AUTHOR-RECHECK-'+t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':'BAP-AUTHOR-RECHECK-'+t._testMethodName,'status':'fail','detail':self._exc_info_to_string(e,t)})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':'BAP-AUTHOR-RECHECK-'+t._testMethodName,'status':'error','detail':self._exc_info_to_string(e,t)})
 r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Recheck))
 paths=[Path(__file__),ROOT/'tools/test_bound_ap_release.py']+list((ROOT/'engine').glob('*.py'))+list((ROOT/'data').glob('*.json'))+list((ROOT/'output/entities').glob('*.json'))+[ROOT/'output/ruleunits.jsonl',ROOT/'output/source-audit/2026-10-10/xlsx-cells.json',ROOT/'data/verification/common-bound-ap-release-contract.json']
 out={'scope':'Minimal ownership recheck and passive ended receipts; imported bindings only. No generic binding producer or whole R04 closure.','results':r.rows,'input_hashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()},'semantic_closure':False}
 (ROOT/'output/bound-ap-author-recheck-tests.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not r.wasSuccessful())
