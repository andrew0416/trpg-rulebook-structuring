from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_policy_replay as F
import growth_stats as G,nature_state as N,action_points as AP
from builder import build_pokemon,species_lookup
from state_codec import dump_engine,load_engine

class NatureCommitTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.PolicyReplayTests.setUpClass()
 def setUp(self):
  self.f=F.PolicyReplayTests();self.f.setUp();f=self.f
  self.p=F.Combatant(f.r,build_pokemon(f.r,'잉어킹',5,moves=[],abilities=[]));f.e.everyone.append(self.p)
  self.nature=next(name for name in f.r.mech('pokemon/natures')['by_name'] if not N.describe(f.r,name)['neutral'])
  plan=G.allocate(species_lookup(f.r,self.p.spec['species'])['base_stats'],15,nature=self.nature,rules=f.r)
  self.args=dict(investment=plan['investment'],source='combat/struggle',reason='explicit host-adjudicated migration',ap_cost=1,hp_policy='preserve_fraction',request_id='nature/one')
 def run_change(self):return self.f.e.commit_growth_nature(self.f.c,self.p,self.nature,**self.args)
 def test_commit_paid_once_and_restored_replay_keeps_investment(self):
  f=self.f;available=AP.available(f.c);initial=self.p.spec['initial_allocation'];out=self.run_change()
  self.assertEqual(out['status'],'NatureChanged');self.assertEqual(AP.available(f.c),available-1)
  self.assertEqual(self.p.spec['initial_allocation'],initial);self.assertEqual(self.p.spec['nature'],self.nature)
  self.assertEqual(sum(G.project(f.r,self.p.spec)['investment'].values()),15)
  before=dump_engine(f.e);self.assertTrue(self.run_change()['replayed']);self.assertEqual(dump_engine(f.e),before)
  loaded=load_engine(f.r,before);payer,target=loaded.everyone
  before=dump_engine(loaded);out=loaded.commit_growth_nature(payer,target,self.nature,**self.args)
  self.assertTrue(out['replayed']);self.assertEqual(dump_engine(loaded),before)
 def test_insufficient_ap_or_invalid_budget_changes_nothing(self):
  f=self.f;before=dump_engine(f.e);self.args['ap_cost']=AP.available(f.c)+1
  with self.assertRaises(ValueError):self.run_change()
  self.assertEqual(dump_engine(f.e),before);self.args['ap_cost']=1;self.args['investment']['atk']+=1
  with self.assertRaisesRegex(ValueError,'budget'):self.run_change()
  self.assertEqual(dump_engine(f.e),before)
 def test_late_projection_error_rolls_back_payment_and_nature(self):
  f=self.f;before=dump_engine(f.e);original=G.project_actor;calls=[]
  def fail_late(*args):
   calls.append(1)
   if len(calls)==2:raise ValueError('late projection failure')
   return original(*args)
  with patch.object(G,'project_actor',side_effect=fail_late):
   with self.assertRaisesRegex(ValueError,'late projection'):self.run_change()
  self.assertEqual(dump_engine(f.e),before)
 def test_changed_replay_cost_rejected(self):
  self.run_change();before=dump_engine(self.f.e);self.args['ap_cost']=2
  with self.assertRaisesRegex(ValueError,'changed input'):self.run_change()
  self.assertEqual(dump_engine(self.f.e),before)

if __name__=='__main__':unittest.main()
