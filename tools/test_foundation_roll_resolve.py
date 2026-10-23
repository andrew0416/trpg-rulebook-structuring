from pathlib import Path
from copy import deepcopy
from random import Random
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_policy_replay as F
from state_codec import dump_engine,load_engine
import common_checks as C

class RollResolveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.PolicyReplayTests.setUpClass()
 def setUp(self):
  self.f=F.PolicyReplayTests();self.f.setUp();self.f.c.spec['skills']={'Athletics':3}
 def request(self,actor=None,**options):
  f=self.f;actor=f.c if actor is None else actor
  return dict(actor=actor,target=actor,provider=actor,skill='Athletics',purpose='climbing',replacement=None,options=options,
   expected_plan=f.e.plan_skill_check(actor,'Athletics',purpose='climbing',**options))
 def second(self):
  f=self.f;b=F.Combatant(f.r,F.build_trainer(f.r,'defender',10,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  b.spec['skills']={'Athletics':3};f.e.everyone.append(b);return b
 def test_dc_equality_and_separate_penalty_pool_larger_than_positive(self):
  f=self.f;request=self.request(fixed=[6,6,6],penalty_count=4,fixed_penalties=[1,2,3,4]);before=f.e.rng.getstate()
  out=f.e.resolve_roll_context([request],{'kind':'dc','dc':8})
  self.assertTrue(out['result']['passed']);self.assertEqual(out['result']['margin'],0)
  self.assertEqual(out['rolls'][0]['faces'],(6,6,6));self.assertEqual(out['rolls'][0]['penalties'],(1,2,3,4))
  self.assertEqual(f.e.rng.getstate(),before)
 def test_actual_rng_matches_fixed_observations_and_advances_exactly(self):
  f=self.f;rng=Random();rng.setstate(f.e.rng.getstate());faces=[rng.randint(1,6) for _ in range(3)];penalties=[rng.randint(1,6) for _ in range(4)]
  actual=f.e.resolve_roll_context([self.request(penalty_count=4)],{'kind':'dc','dc':0})
  self.assertEqual(f.e.rng.getstate(),rng.getstate())
  fixed=f.e.resolve_roll_context([self.request(fixed=faces,penalty_count=4,fixed_penalties=penalties)],{'kind':'dc','dc':0})
  self.assertEqual(actual['rolls'],fixed['rolls']);self.assertEqual(actual['result'],fixed['result'])
 def test_stale_plan_and_changed_penalty_declaration_fail_before_rng(self):
  f=self.f;request=self.request();before=dump_engine(f.e);request['options']['penalty_count']=4
  with self.assertRaisesRegex(ValueError,'stale'):f.e.resolve_roll_context([request],{'kind':'dc','dc':5})
  self.assertEqual(dump_engine(f.e),before)
  request=self.request();f.c.spec['skills']['Athletics']=4;before=dump_engine(f.e)
  with self.assertRaisesRegex(ValueError,'stale'):f.e.resolve_roll_context([request],{'kind':'dc','dc':5})
  self.assertEqual(dump_engine(f.e),before)
 def test_native_ordinary_late_failure_preserves_prepaid_bonus_and_retries_once(self):
  import skill_feature_actions as SF
  import action_points as AP
  f=self.f;f.e.boost_roll(f.c,f.c,roll_id='ordinary/paid',kind='skill')
  paid=AP.available(f.c);before=dump_engine(f.e)
  with patch.object(C,'adjudicate',side_effect=ValueError('late adjudication')):
   with self.assertRaisesRegex(ValueError,'late adjudication'):
    f.e.common_action(f.c,'Athletics',5,mode='skill',roll_id='ordinary/paid')
  self.assertEqual(dump_engine(f.e),before);self.assertIsNone(SF.event(f.e,f.c,'ordinary/paid'))
  result=f.e.common_action(f.c,'Athletics',5,mode='skill',roll_id='ordinary/paid')
  self.assertIsNotNone(result.check);self.assertEqual(AP.available(f.c),paid)
  self.assertEqual(SF.event(f.e,f.c,'ordinary/paid').state,'final')

 def test_opposed_tie_requires_actual_defender(self):
  f=self.f;b=self.second();requests=[self.request(fixed=[2,2,2]),self.request(b,fixed=[2,2,2])]
  before=dump_engine(f.e)
  with self.assertRaisesRegex(ValueError,'defender'):f.e.resolve_roll_context(requests,{'kind':'opposed','status_quo_defender_id':f.c.entity_id})
  self.assertEqual(dump_engine(f.e),before)
  out=f.e.resolve_roll_context(requests,{'kind':'opposed','status_quo_defender_id':b.entity_id})
  self.assertEqual(out['result']['winner_id'],b.entity_id)
 def test_team_and_weighted_team_preserve_declared_threshold(self):
  f=self.f;b=self.second();requests=[self.request(fixed=[1,1,1]),self.request(b,fixed=[2,2,2])]
  out=f.e.resolve_roll_context(requests,{'kind':'team','dc':5,'required_people':2})
  self.assertFalse(out['result']['passed']);self.assertEqual(out['result']['dc'],10)
  out=f.e.resolve_roll_context(requests,{'kind':'weighted_team','dc':5,'required_people':2,'weights':[2,1]})
  self.assertTrue(out['result']['passed']);self.assertEqual(out['result']['total'],12)
 def test_failure_after_roll_does_not_commit_rng_or_events(self):
  f=self.f;request=self.request();before=dump_engine(f.e)
  with patch.object(C,'against_dc',side_effect=ValueError('late failure')):
   with self.assertRaisesRegex(ValueError,'late failure'):f.e.resolve_roll_context([request],{'kind':'dc','dc':5})
  self.assertEqual(dump_engine(f.e),before)

class RollReplayTests(unittest.TestCase):
 setUpClass=classmethod(RollResolveTests.setUpClass.__func__)
 setUp=RollResolveTests.setUp
 request=RollResolveTests.request
 def test_completed_request_replay_survives_changed_rank_and_save_restore(self):
  f=self.f;request=self.request(penalty_count=2);procedure={'kind':'dc','dc':4}
  first=f.e.resolve_roll_context([request],procedure,request_id='climb/one')
  self.assertFalse(first['replayed']);f.c.spec['skills']['Athletics']=4
  before=dump_engine(f.e);again=f.e.resolve_roll_context([request],procedure,request_id='climb/one')
  self.assertTrue(again['replayed']);self.assertEqual(again['rolls'],first['rolls']);self.assertEqual(dump_engine(f.e),before)
  loaded=load_engine(f.r,before);owner=loaded.everyone[0];restored=dict(request,actor=owner,target=owner,provider=owner)
  before=dump_engine(loaded);again=loaded.resolve_roll_context([restored],procedure,request_id='climb/one')
  self.assertEqual(again['rolls'],first['rolls']);self.assertEqual(dump_engine(loaded),before)
  again['rolls'].clear();self.assertEqual(loaded.resolve_roll_context([restored],procedure,request_id='climb/one')['rolls'],first['rolls'])
 def test_changed_completed_input_rejected_without_rng(self):
  f=self.f;request=self.request();procedure={'kind':'dc','dc':4}
  f.e.resolve_roll_context([request],procedure,request_id='climb/one');before=dump_engine(f.e)
  with self.assertRaisesRegex(ValueError,'changed input'):
   f.e.resolve_roll_context([request],dict(procedure,dc=5),request_id='climb/one')
  self.assertEqual(dump_engine(f.e),before)
 def test_paid_ap_roll_replay_keeps_cost_and_final_observation_once(self):
  import action_points as AP
  f=self.f;f.e.boost_roll(f.c,f.c,roll_id='boosted',kind='skill');paid=AP.available(f.c)
  request=self.request(roll_id='boosted',fixed=[2,2,2]);self.assertEqual(request['expected_plan']['ap_bonus'],1)
  first=f.e.resolve_roll_context([request],{'kind':'dc','dc':7},request_id='boosted/check')
  self.assertTrue(first['result']['passed']);self.assertEqual(AP.available(f.c),paid)
  before=dump_engine(f.e);again=f.e.resolve_roll_context([request],{'kind':'dc','dc':7},request_id='boosted/check')
  self.assertTrue(again['replayed']);self.assertEqual(dump_engine(f.e),before)
 def test_ap_added_after_plan_requires_new_plan_before_roll(self):
  f=self.f;request=self.request(roll_id='boosted');f.e.boost_roll(f.c,f.c,roll_id='boosted',kind='skill');before=dump_engine(f.e)
  with self.assertRaisesRegex(ValueError,'stale'):
   f.e.resolve_roll_context([request],{'kind':'dc','dc':7},request_id='boosted/check')
  self.assertEqual(dump_engine(f.e),before)
 def test_failed_request_has_no_receipt_and_can_retry(self):
  f=self.f;request=self.request();procedure={'kind':'dc','dc':4};before=dump_engine(f.e)
  with patch.object(C,'against_dc',side_effect=ValueError('late failure')):
   with self.assertRaises(ValueError):f.e.resolve_roll_context([request],procedure,request_id='climb/one')
  self.assertEqual(dump_engine(f.e),before);self.assertFalse(getattr(f.e,'_roll_context_requests',{}))
  out=f.e.resolve_roll_context([request],procedure,request_id='climb/one');self.assertFalse(out['replayed'])

if __name__=='__main__':unittest.main()
