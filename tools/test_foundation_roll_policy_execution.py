from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_roll_context as R
from state_codec import dump_engine,load_engine
import common_checks as C

class RollPolicyExecutionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):R.RollContextTests.setUpClass()
 def setUp(self):
  self.fixture=R.RollContextTests();self.fixture.setUp();self.f=self.fixture.f
  self.declaration=self.fixture.policy_document();self.declaration['options']={'fixed':[2,2,2,2]}
  self.f.c.spec['edges']=['edge/메딕-훈련']
 def submissions(self):
  f=self.f;return [dict(actor=f.c,target=f.c,document=f.doc,purpose='climbing')]
 def execute(self,request='policy/check'):
  return self.f.e.execute_source_policy_rolls(self.submissions(),{'kind':'dc','dc':8},request_id=request)
 def test_execute_selected_replacement_and_detached_replay_after_restore(self):
  f=self.f;out=self.execute();self.assertEqual(out['status'],'PolicyRollsCompleted');self.assertTrue(out['outcome']['result']['passed'])
  self.assertEqual(out['outcome']['plans'][0]['selected_skill'],'acrobatics')
  f.c.spec['edges']=[];before=dump_engine(f.e);again=self.execute();self.assertTrue(again['replayed']);self.assertEqual(dump_engine(f.e),before)
  loaded=load_engine(f.r,before);actor=loaded.everyone[0];before=dump_engine(loaded)
  again=loaded.execute_source_policy_rolls([dict(actor=actor,target=actor,document=f.doc,purpose='climbing')],{'kind':'dc','dc':8},request_id='policy/check')
  self.assertTrue(again['replayed']);self.assertEqual(dump_engine(loaded),before)
  again['outcome']['rolls'].clear();self.assertTrue(self.execute()['outcome']['rolls'])
 def test_removed_provider_requirement_denies_new_request_without_rng(self):
  f=self.f;f.e.evaluate_source_policy_roll_plan(f.c,f.c,f.doc,purpose='climbing');f.c.spec['edges']=[];before=dump_engine(f.e)
  out=self.execute();self.assertEqual(out['status'],'PolicyRollsDenied');self.assertEqual(dump_engine(f.e),before)
 def test_stale_source_or_changed_request_cannot_replay(self):
  f=self.f;self.execute();before=dump_engine(f.e);self.declaration['options']['fixed']=[3,3,3,3]
  with self.assertRaisesRegex(ValueError,'changed input'):self.execute()
  self.assertEqual(dump_engine(f.e),before)
  self.declaration['options']['fixed']=[2,2,2,2];f.row['source']['sha256']='0'*64
  with self.assertRaises(ValueError):self.execute()
  self.assertEqual(dump_engine(f.e),before)
 def test_unknown_permission_stays_pending_without_consumption(self):
  f=self.f;self.declaration['replacement']['allowed']=None;before=dump_engine(f.e)
  out=self.execute();self.assertEqual(out['status'],'PolicyRollsPending');self.assertFalse(out['consumed']);self.assertEqual(dump_engine(f.e),before)
 def test_all_policy_participants_admitted_before_opposed_roll(self):
  f=self.f;spec=deepcopy(f.c.spec);spec['id']='trainer/second';spec['name']='second';spec['edges']=[]
  other=R.F.Combatant(f.r,spec);f.e.everyone.append(other)
  document=deepcopy(f.doc);declaration=document['variants'][0]['values']['roll_plan'];declaration['provider_id']=other.entity_id
  for key in ('actor_id','target_id','provider_id'):declaration['replacement'][key]=other.entity_id
  submissions=self.submissions()+[dict(actor=other,target=other,document=document,purpose='climbing')]
  procedure={'kind':'opposed','status_quo_defender_id':other.entity_id};before=dump_engine(f.e)
  denied=f.e.execute_source_policy_rolls(submissions,procedure,request_id='pair')
  self.assertEqual(denied['status'],'PolicyRollsDenied');self.assertEqual(dump_engine(f.e),before)
  other.spec['edges']=['edge/메딕-훈련']
  out=f.e.execute_source_policy_rolls(submissions,procedure,request_id='pair')
  self.assertEqual(out['outcome']['result']['winner_id'],other.entity_id);self.assertEqual(len(out['policies']),2)
 def test_late_failure_rolls_back_and_does_not_record_success(self):
  f=self.f;self.declaration['options']={};before=dump_engine(f.e)
  with patch.object(C,'against_dc',side_effect=ValueError('late failure')):
   with self.assertRaisesRegex(ValueError,'late failure'):self.execute()
  self.assertEqual(dump_engine(f.e),before);self.assertFalse(getattr(f.e,'_roll_policy_requests',{}))
  self.assertEqual(self.execute()['status'],'PolicyRollsCompleted')

if __name__=='__main__':unittest.main()
