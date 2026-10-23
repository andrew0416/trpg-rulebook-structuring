from pathlib import Path
from hashlib import sha256
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_policy_replay as F
import native_rule_policy as N
from state_codec import dump_engine

class BundleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.PolicyReplayTests.setUpClass()
 def setUp(self):
  self.f=F.PolicyReplayTests();self.f.setUp();self.second=N.PRECEDENCE_SOURCE
  self.plan={'base':100,'rounding':'floor','members':{
   'a':{'policy_id':'bonus-a','source':'combat/struggle'},'b':{'policy_id':'bonus-b','source':self.second}},
   'steps':[{'law':'percent_add','contributors':['a','b']}]}
  self.p=self.doc('plan','combat/struggle',{'composition_plan':self.plan})
  self.a=self.doc('bonus-a','combat/struggle',{'composition_contributions':[{'id':'a','source':'combat/struggle','value':{'numerator':1,'denominator':5}}]})
  self.b=self.doc('bonus-b',self.second,{'composition_contributions':[{'id':'b','source':self.second,'value':{'numerator':3,'denominator':10}}]})
 def doc(self,identity,source,values):
  file=self.f.r.selection.units[source]['source']['file']
  return {'schema':1,'id':identity,'variants':[{'rule_id':source,'source':{'file':'input/'+file,'sha256':sha256((ROOT/'input'/file).read_bytes()).hexdigest()},'inputs':{},'values':values}]}
 def run_bundle(self,contributors=None):
  f=self.f
  return f.e.evaluate_source_policy_composition_bundle(f.c,f.c,{'document':self.p},contributors if contributors is not None else [{'document':self.a},{'document':self.b}])
 def test_independent_sources_compose_with_selected_law_without_consumption(self):
  before=dump_engine(self.f.e);out=self.run_bundle()
  self.assertEqual(out['composition']['value'],150)
  self.assertEqual(out['contributors']['bonus-b']['selected_id'],self.second)
  self.plan['steps'][0]['law']='percent_product'
  self.assertEqual(self.run_bundle()['composition']['value'],156)
  self.assertEqual(dump_engine(self.f.e),before)
 def test_inapplicable_source_leaves_independent_contribution(self):
  self.b['variants'][0]['when']=False
  out=self.run_bundle();self.assertEqual(out['composition']['value'],120);self.assertEqual(out['excluded'],['b'])
  self.plan['steps'][0]['contributors'].append('b')
  with self.assertRaises(ValueError):self.run_bundle()
 def test_one_unresolved_source_never_becomes_zero(self):
  row=self.b['variants'][0];row['inputs']['amount']={'type':'integer','authority':'gm','question':'Explicit amount'}
  row['values']['composition_contributions'][0]['value']={'$input':'amount'}
  before=dump_engine(self.f.e);out=self.run_bundle()
  self.assertEqual(out['status'],'PolicyCompositionPending');self.assertNotIn('composition',out)
  self.assertEqual(out['pending_policies'],['bonus-b']);self.assertEqual(dump_engine(self.f.e),before)
 def test_stale_or_impersonated_source_rejects_before_any_state_change(self):
  before=dump_engine(self.f.e)
  row=self.b['variants'][0];row['values']['composition_contributions'][0]['source']='combat/struggle'
  with self.assertRaisesRegex(ValueError,'independently selected'):self.run_bundle()
  row['values']['composition_contributions'][0]['source']=self.second;row['source']['sha256']='0'*64
  with self.assertRaises(ValueError):self.run_bundle()
  self.assertEqual(dump_engine(self.f.e),before)
 def test_exact_membership_rejects_missing_duplicate_and_extra_rows(self):
  for docs in [[{'document':self.a}],[{'document':self.a},{'document':self.b},{'document':self.b}]]:
   with self.assertRaises(ValueError):self.run_bundle(docs)
  self.b['variants'][0]['values']['composition_contributions'].append({'id':'extra','source':self.second,'value':100})
  with self.assertRaisesRegex(ValueError,'manifest'):self.run_bundle()
if __name__=='__main__':unittest.main()
