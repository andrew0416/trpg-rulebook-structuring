from pathlib import Path
from copy import deepcopy
from random import Random
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category3_skill_feature_actions as N
import skill_feature_actions as SF
from state_codec import dump_engine,load_engine

class RollChoiceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):N.Tests.setUpClass()
 def setUp(self):self.f=N.Tests();self.f.setUp()
 def request(self,actor=None,roll_id='r',**options):
  f=self.f;actor=f.t if actor is None else actor;options=dict(options,roll_id=roll_id)
  return dict(actor=actor,target=actor,provider=actor,skill='Athletics',purpose='climbing',replacement=None,options=options,
   expected_plan=f.e.plan_skill_check(actor,'Athletics',purpose='climbing',**options))
 def choice(self,decision,**options):return {'feature':SF.MONKEY,'options':dict(options,decision=decision)}
 def test_accepts_worse_reroll_once_and_completed_replay_does_not_call_choice(self):
  f=self.f;request=self.request(fixed=[6]*4);seen=[]
  choices={'r':self.choice(lambda first:seen.append(first.faces) or True,reroll_faces=[1]*4)}
  out=f.e.resolve_roll_context([request],{'kind':'dc','dc':10},request_id='choice/one',observed_choices=choices)
  self.assertEqual(seen,[(6,6,6,6)]);self.assertEqual(out['result']['total'],6);self.assertFalse(out['result']['passed']);self.assertEqual(f.used(),1)
  self.assertEqual(out['observations'][0]['first']['total'],24);self.assertEqual(out['observations'][0]['state'],'final')
  before=dump_engine(f.e);again=f.e.resolve_roll_context([request],{'kind':'dc','dc':10},request_id='choice/one',observed_choices=choices)
  self.assertTrue(again['replayed']);self.assertEqual(len(seen),1);self.assertEqual(dump_engine(f.e),before)
 def test_choice_failure_preserves_actual_first_and_resume_after_restore(self):
  f=self.f;request=self.request();rng=Random();rng.setstate(f.e.rng.getstate());expected=tuple(rng.randint(1,6) for _ in range(4))
  choices={'r':self.choice(lambda first:'invalid')}
  with self.assertRaisesRegex(ValueError,'boolean'):
   f.e.resolve_roll_context([request],{'kind':'dc','dc':10},request_id='choice/one',observed_choices=choices)
  self.assertEqual(SF.event(f.e,f.t,'r').first.faces,expected);self.assertEqual(f.e.rng.getstate(),rng.getstate());self.assertEqual(f.used(),0)
  saved=dump_engine(f.e);loaded=load_engine(f.e.r,saved);actor=loaded.everyone[0]
  restored=dict(request,actor=actor,target=actor,provider=actor);seen=[]
  out=loaded.resolve_roll_context([restored],{'kind':'dc','dc':10},request_id='choice/one',observed_choices={'r':self.choice(lambda first:seen.append(first.faces) or False)})
  self.assertEqual(seen,[expected]);self.assertEqual(out['rolls'][0]['faces'],expected);self.assertEqual(loaded.rng.getstate(),rng.getstate())
 def test_changed_pending_reroll_observations_are_rejected(self):
  f=self.f;request=self.request(fixed=[1]*4);choices={'r':self.choice(lambda first:'invalid',reroll_faces=[2]*4)}
  with self.assertRaises(ValueError):f.e.resolve_roll_context([request],{'kind':'dc','dc':10},request_id='choice/one',observed_choices=choices)
  before=dump_engine(f.e);choices={'r':self.choice(lambda first:True,reroll_faces=[6]*4)}
  with self.assertRaisesRegex(ValueError,'observed scoped'):
   f.e.resolve_roll_context([request],{'kind':'dc','dc':10},request_id='choice/one',observed_choices=choices)
  self.assertEqual(dump_engine(f.e),before)
 def test_later_participant_failure_keeps_first_paid_resolution(self):
  f=self.f;requests=[self.request(fixed=[1]*4),self.request(f.b,'b',fixed=[2]*4)]
  choices={'r':self.choice(lambda first:True,reroll_faces=[3]*4),'b':self.choice(lambda first:'invalid')}
  procedure={'kind':'opposed','status_quo_defender_id':f.b.entity_id}
  with self.assertRaises(ValueError):f.e.resolve_roll_context(requests,procedure,request_id='choice/pair',observed_choices=choices)
  self.assertEqual(f.used(),1);self.assertEqual(f.used(f.b),0);self.assertEqual(SF.event(f.e,f.t,'r').state,'final')
  calls=[];choices['r']=self.choice(lambda first:calls.append(first) or True,reroll_faces=[3]*4);choices['b']=self.choice(lambda first:False)
  out=f.e.resolve_roll_context(requests,procedure,request_id='choice/pair',observed_choices=choices)
  self.assertEqual(out['result']['winner_id'],f.t.entity_id);self.assertFalse(calls);self.assertEqual(f.used(),1)

if __name__=='__main__':unittest.main()
