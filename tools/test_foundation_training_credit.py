"""Completed grooming credit uses one shared validation and consumption path."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as fixtures
from builder import build_pokemon
import pokemon_teaching as T

class TrainingCreditTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.ProgressionStateTests.setUpClass.__func__)
 add=fixtures.ProgressionStateTests.add
 snap=fixtures.ProgressionStateTests.snap
 restored=fixtures.ProgressionStateTests.restored
 def setUp(self):
  fixtures.ProgressionStateTests.setUp(self)
  self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
  self.p=self.add(build_pokemon(self.r,'근육몬',35,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':6}))
  self.e.pokemon_activity(self.a,'groom',targets=[self.p],safe=True)
 def xp(self):return self.e.pokemon_activity(self.a,'experience_training',targets=[self.p],from_grooming=True,bonus_skill='포켓몬학',safe=True)
 def edge(self):return T.teach_edge(self.e,self.a,target=self.p,edge=T.EDGE,skill='육상',from_grooming=True,safe=True)
 def test_future_completion_cannot_pay_experience_training(self):
  self.p.spec['training_credit']['completed_at']=self.e.elapsed_seconds+1;before=self.snap()
  with self.assertRaises(ValueError):self.xp()
  self.assertEqual(before,self.snap())
 def test_malformed_credit_rejected_before_either_consumer_changes_state(self):
  original=deepcopy(self.p.spec['training_credit'])
  cases=[('hours',True),('hours',float('nan')),('hours',0),('day',False),('completed_at',-1),('completed_at',None),('applications','not-a-list'),('applications',['same','same']),('applications',[None])]
  for field,value in cases:
   for consumer in (self.xp,self.edge):
    with self.subTest(field=field,value=value,consumer=consumer.__name__):
     self.setUp();self.p.spec['training_credit']=dict(deepcopy(original),**{field:value});before=self.snap()
     with self.assertRaises(ValueError):consumer()
     self.assertEqual(before,self.snap())
 def test_explicit_consumed_application_blocks_reuse_even_without_daily_marker(self):
  self.p.spec['training_credit']['applications']=['experience_training'];before=self.snap()
  with self.assertRaisesRegex(ValueError,'already consumed'):self.xp()
  self.assertEqual(before,self.snap())
 def test_late_second_target_failure_rolls_back_xp_and_credit_consumption(self):
  other=self.add(build_pokemon(self.r,'근육몬',35,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':6}))
  self.e.pokemon_activity(self.a,'groom',targets=[self.p,other],safe=True);before=self.snap();native=T.consume_credit
  def fail_after_consume(target,application):
   native(target,application)
   if target.entity_id==other.entity_id:raise ValueError('late credit failure')
  with patch.object(T,'consume_credit',side_effect=fail_after_consume):
   with self.assertRaisesRegex(ValueError,'late credit failure'):
    self.e.pokemon_activity(self.a,'experience_training',targets=[self.p,other],from_grooming=True,bonus_skill='포켓몬학',safe=True)
  self.assertEqual(before,self.snap())
 def test_completed_hour_funds_distinct_consumers_and_survives_restore(self):
  self.xp();self.edge()
  self.assertEqual(self.e.elapsed_seconds,3600);self.assertEqual(self.p.spec['tutor_points'],5)
  apps=self.p.spec['training_credit']['applications'];self.assertIn('experience_training',apps);self.assertEqual(len(apps),2)
  loaded=self.restored();actors={a.entity_id:a for a in loaded.gm.everyone}
  before=deepcopy(actors[self.p.entity_id].spec)
  with self.assertRaises(ValueError):loaded.pokemon_activity(actors[self.a.entity_id],'experience_training',targets=[actors[self.p.entity_id]],from_grooming=True,bonus_skill='포켓몬학',safe=True)
  self.assertEqual(before,actors[self.p.entity_id].spec)

if __name__=='__main__':unittest.main()
