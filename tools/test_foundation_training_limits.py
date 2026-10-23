"""Six ordinary participants and Command-ranked XP recipients are separate."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_training_hour as fixtures
from builder import build_pokemon
import training_features as F
from state_codec import dump_engine

class TrainingLimitsTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.TrainingHourTests.setUpClass.__func__)
 add=fixtures.TrainingHourTests.add
 def setUp(self):
  fixtures.TrainingHourTests.setUp(self)
  self.ps += [self.add(build_pokemon(self.r,'이상해씨',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id})) for _ in range(6)]
 def test_six_training_targets_but_only_four_daily_xp_recipients(self):
  self.e.complete_training_hour(self.a,self.ps[:6],safe=True,reason='six observed training participants',request_id='six')
  self.e.train_pokemon(self.a,[(p,[next(iter(F.RULES))]) for p in self.ps[:6]],minutes=30,reason='completed shared hour',request_id='regimes',from_training=True)
  self.e.pokemon_activity(self.a,'experience_training',targets=self.ps[:4],from_training=True)
  self.assertEqual(self.e.elapsed_seconds,3600);self.assertEqual(self.a.spec['experience_training']['count'],4)
  self.assertTrue(all(F.records(p) for p in self.ps[:6]));before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'daily training target limit'):self.e.pokemon_activity(self.a,'experience_training',targets=[self.ps[4]],from_training=True)
  self.assertEqual(before,dump_engine(self.e))
 def test_eight_target_example_does_not_override_six_target_prose(self):
  for count in (7,8):
   before=dump_engine(self.e)
   with self.assertRaisesRegex(ValueError,'six'):self.e.complete_training_hour(self.a,self.ps[:count],safe=True,reason='example cannot enlarge prose limit',request_id='too-many')
   self.assertEqual(before,dump_engine(self.e))
   with self.assertRaisesRegex(ValueError,'six'):self.e.train_pokemon(self.a,[(p,[next(iter(F.RULES))]) for p in self.ps[:count]],minutes=30,reason='example cannot enlarge prose limit',request_id='too-many',safe=True)
   self.assertEqual(before,dump_engine(self.e))

if __name__=='__main__':unittest.main()
