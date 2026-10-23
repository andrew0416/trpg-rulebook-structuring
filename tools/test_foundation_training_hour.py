"""One safe native hour funds XP, Training and a Poke Edge without extra time."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_policy_training as fixtures
import pokemon_teaching as TEACHING,training_features as T,training_sessions as H
from state_codec import dump_engine,load_engine
import world_entities as W

class TrainingHourTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.PolicyTrainingTests.setUpClass.__func__)
 add=fixtures.PolicyTrainingTests.add
 load=fixtures.PolicyTrainingTests.load
 run_policy=fixtures.PolicyTrainingTests.run_policy
 def setUp(self):
  fixtures.PolicyTrainingTests.setUp(self)
  self.a.spec['feats']=list(T.RULES)
  self.a.spec['skills'].update({'육상':3,'협박':3,'매력':3})
  for p in self.ps:p.spec['tutor_points']=6
 def hour(self,**kw):return self.e.complete_training_hour(self.a,self.ps,safe=kw.pop('safe',True),reason='observed safe training ground',request_id=kw.pop('request_id','hour'),**kw)
 def test_hour_funds_three_consumers_and_survives_save(self):
  receipt=self.hour();self.assertEqual(self.e.elapsed_seconds,3600)
  self.e.pokemon_activity(self.a,'experience_training',targets=self.ps,from_training=True)
  self.e.train_pokemon(self.a,[(p,[next(iter(T.RULES))]) for p in self.ps],minutes=30,reason='training in completed hour',request_id='regime',from_training=True)
  TEACHING.teach_edge(self.e,self.a,target=self.ps[0],edge=TEACHING.EDGE,skill='육상',from_training=True)
  self.assertEqual(self.e.elapsed_seconds,3600);self.assertEqual(self.ps[0].spec['tutor_points'],5)
  self.assertEqual(len(self.ps[0].spec[H.KEY]['applications']),3)
  restored=load_engine(self.r,dump_engine(self.e));actors=W.actor_index(restored);before=dump_engine(restored)
  self.assertEqual(restored.complete_training_hour(actors[self.a.entity_id],[actors[p.entity_id] for p in self.ps],safe=True,reason='observed safe training ground',request_id='hour'),receipt)
  self.assertEqual(before,dump_engine(restored))
 def test_unsafe_and_missing_hour_reject_without_changes(self):
  for safety in (False,None,1):
   before=dump_engine(self.e)
   with self.assertRaises(ValueError):self.hour(safe=safety)
   self.assertEqual(before,dump_engine(self.e))
  before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'experience_training',targets=self.ps,from_training=True)
  self.assertEqual(before,dump_engine(self.e))
 def test_later_invalid_credit_rolls_back_group_awards(self):
  self.hour();self.ps[-1].spec[H.KEY]['completed_at']+=1;before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'experience_training',targets=self.ps,from_training=True)
  self.assertEqual(before,dump_engine(self.e))
 def test_typed_receipt_and_late_consumption_failure(self):
  self.hour();original=deepcopy(self.ps[0].spec[H.KEY])
  for key,value in (('day',False),('hours',True),('applications',['duplicate','duplicate'])):
   self.ps[0].spec[H.KEY]=dict(deepcopy(original),**{key:value});before=dump_engine(self.e)
   with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'experience_training',targets=self.ps,from_training=True)
   self.assertEqual(before,dump_engine(self.e))
  self.ps[0].spec[H.KEY]=original;before=dump_engine(self.e);native=H.consume
  def fail(target,application):
   native(target,application)
   if target.entity_id==self.ps[-1].entity_id:raise ValueError('late application failure')
  with patch.object(H,'consume',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'late application failure'):self.e.pokemon_activity(self.a,'experience_training',targets=self.ps,from_training=True)
  self.assertEqual(before,dump_engine(self.e))
 def test_policy_hour_then_policy_xp(self):
  self.op.update(kind='hour',safe=True,reason='observed safe training ground',request_id='native-hour');self.load()
  self.assertEqual(self.run_policy(request_id='policy-hour')['status'],'PolicyTrainingCompleted')
  for k in ('safe','reason','request_id'):self.op.pop(k)
  self.op.update(kind='experience',from_training=True)
  self.assertEqual(self.run_policy(request_id='policy-xp')['training_result']['awards'],[7,7]);self.assertEqual(self.e.elapsed_seconds,3600)
 def test_mutually_exclusive_credit_sources_reject(self):
  self.hour();before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'experience_training',targets=self.ps,from_training=True,from_grooming=True)
  self.assertEqual(before,dump_engine(self.e))

if __name__=='__main__':unittest.main()
