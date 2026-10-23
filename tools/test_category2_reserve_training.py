"""Train the Reserves native daily limit without altered XP rank."""
import unittest
from tools import test_category2_progression_state as fixtures

class ReserveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixtures.ProgressionStateTests.setUpClass()
 def setUp(self):
  self.f=fixtures.ProgressionStateTests();self.f.setUp()
  self.f.a.spec['edges']=['예비 훈련']
  self.targets=[self.f.pokemon(5,id='reserve-'+str(i),name='reserve-'+str(i)) for i in range(9)]
 def test_twice_command_daily_across_actual_training_hours(self):
  f=self.f
  a=f.train(*self.targets[:6],use_reserves=True)
  b=f.train(*self.targets[6:8],use_reserves=True)
  self.assertEqual((a['limit'],b['limit'],b['xp_rank']),(8,8,4))
  self.assertEqual((f.a.spec['experience_training']['count'],f.e.elapsed_seconds),(8,7200))
  before=f.snap()
  with self.assertRaises(ValueError):f.train(self.targets[8],use_reserves=True)
  self.assertEqual(f.snap(),before)
  loaded=f.restored();owner=next(x for x in loaded.gm.everyone if x.entity_id==f.a.entity_id)
  self.assertEqual(owner.spec['experience_training'],f.a.spec['experience_training'])
 def test_both_substitutions_missing_edge_and_low_rank_rejected_atomically(self):
  f=self.f;f.a.spec['edges']+=['미용사','비스트 마스터'];f.a.spec['skills']['협박']=4
  for options in ({'from_grooming':True,'bonus_skill':'포켓몬학'},{'use_intimidate':True}):
   before=f.snap()
   with self.assertRaises(ValueError):f.train(self.targets[0],use_reserves=True,**options)
   self.assertEqual(f.snap(),before)
  for edges,rank in [([],4),(['예비 훈련'],2)]:
   f.a.spec['edges']=edges;f.a.spec['skills']['명령']=rank;before=f.snap()
   with self.assertRaises(ValueError):f.train(self.targets[0],use_reserves=True)
   self.assertEqual(f.snap(),before)

if __name__=='__main__':unittest.main()
