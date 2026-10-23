from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_policy_replay as F
from state_codec import dump_engine

class CompositionPolicyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.PolicyReplayTests.setUpClass()
 def setUp(self):
  self.f=F.PolicyReplayTests();self.f.setUp();f=self.f
  self.decl={'base':{'$input':'level'},'rounding':'floor','contributions':[
   {'id':'bonus','source':'combat/struggle','value':{'numerator':1,'denominator':2}}],
   'steps':[{'law':'percent_add','contributors':['bonus']}]}
  f.row['values']={'composition':self.decl}
  f.row['inputs']={'level':{'type':'integer','authority':'state','question':'Actual target level','binding':{'subject':'target','field':'level'}}}
 def evaluate(self,**kw):
  f=self.f;return f.e.evaluate_source_policy_composition(f.c,f.c,f.doc,**kw)
 def test_actual_state_read_and_preview_are_nonconsuming(self):
  f=self.f;before=dump_engine(f.e);out=self.evaluate()
  self.assertEqual(out['status'],'PolicyCompositionEvaluated');self.assertEqual(out['composition']['value'],15)
  self.assertEqual(out['composition']['base'],10);self.assertEqual(out['input_values']['level'],10)
  self.assertFalse(out['effects_executed']);self.assertFalse(out['consumed']);self.assertEqual(dump_engine(f.e),before)
  f.c.spec['level']=12
  self.assertEqual(self.evaluate()['composition']['value'],18)
  before=dump_engine(f.e)
  with self.assertRaises(ValueError):self.evaluate(context={'level':99})
  self.assertEqual(dump_engine(f.e),before)
 def test_source_mismatch_and_stale_hash_cannot_produce_values(self):
  f=self.f;before=dump_engine(f.e)
  self.decl['contributions'][0]['source']='combat/other'
  with self.assertRaisesRegex(ValueError,'selected policy source'):self.evaluate()
  self.decl['contributions'][0]['source']='combat/struggle';f.row['source']['sha256']='0'*64
  with self.assertRaises(ValueError):self.evaluate()
  self.assertEqual(dump_engine(f.e),before)
 def test_pending_and_false_conditions_keep_preview_read_only(self):
  f=self.f;before=dump_engine(f.e)
  self.decl['contributions'][0]['active']={'op':'ge','left':{'$input':'level'},'right':11}
  self.assertEqual(self.evaluate()['composition']['value'],10)
  self.decl['contributions'][0]['active']=None
  out=self.evaluate();self.assertEqual(out['status'],'PolicyCompositionPending');self.assertNotIn('value',out['composition'])
  self.assertEqual(dump_engine(f.e),before)
 def test_missing_gm_input_is_not_a_default_and_changed_input_is_recomputed(self):
  f=self.f;f.row['inputs']['bonus']={'type':'integer','authority':'gm','question':'Chosen additive amount?'}
  self.decl['steps'][0]['law']='add';self.decl['contributions'][0]['value']={'$input':'bonus'}
  before=dump_engine(f.e);self.assertEqual(self.evaluate()['status'],'PolicyInputsRequired')
  self.assertEqual(self.evaluate(decisions={'bonus':{'value':3,'reason':'chosen amount'}})['composition']['value'],13)
  self.assertEqual(self.evaluate(decisions={'bonus':{'value':5,'reason':'new amount'}})['composition']['value'],15)
  self.assertEqual(dump_engine(f.e),before)
if __name__=='__main__':unittest.main()
