"""Every direct training consumer requires explicit safety before committing."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_training_hour as fixtures
import pokemon_teaching as T,training_features as F
from state_codec import dump_engine

class TrainingSafetyTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.TrainingHourTests.setUpClass.__func__)
 add=fixtures.TrainingHourTests.add
 load=fixtures.TrainingHourTests.load
 run_policy=fixtures.TrainingHourTests.run_policy
 def setUp(self):
  fixtures.TrainingHourTests.setUp(self)
  self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
 def test_each_direct_consumer_requires_true_safety_without_mutation(self):
  consumers=[lambda **kw:self.e.pokemon_activity(self.a,'experience_training',targets=self.ps,**kw),
   lambda **kw:self.e.pokemon_activity(self.a,'groom',targets=self.ps,**kw),
   lambda **kw:self.e.train_pokemon(self.a,[(p,[next(iter(F.RULES))]) for p in self.ps],minutes=30,reason='observed training',request_id='safety',**kw),
   lambda **kw:T.teach_edge(self.e,self.a,target=self.ps[0],edge=T.EDGE,skill='육상',**kw)]
  for consumer in consumers:
   for options in ({},{'safe':False},{'safe':1}):
    before=dump_engine(self.e)
    with self.assertRaisesRegex(ValueError,'safe|safety'):consumer(**options)
    self.assertEqual(before,dump_engine(self.e))
 def test_external_unknown_safety_is_pending_and_false_cannot_execute(self):
  row=self.doc['variants'][0];row['inputs']['safety']={'type':'boolean','authority':'context','question':'Is this training environment safe?'}
  self.op['safe']={'$input':'safety'};self.load();before=dump_engine(self.e)
  self.assertEqual(self.run_policy()['status'],'PolicyInputsRequired');self.assertEqual(before,dump_engine(self.e))
  self.context['safety']=False
  with self.assertRaisesRegex(ValueError,'safe'):self.run_policy()
  self.assertEqual(before,dump_engine(self.e))
  self.context['safety']=True;self.assertEqual(self.run_policy()['status'],'PolicyTrainingCompleted')
 def test_old_grooming_credit_without_safety_cannot_pay_training(self):
  self.e.pokemon_activity(self.a,'groom',targets=self.ps,safe=True)
  self.ps[0].spec['training_credit'].pop('safe');before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'safe'):self.e.pokemon_activity(self.a,'experience_training',targets=self.ps,from_grooming=True,bonus_skill='포켓몬학')
  self.assertEqual(before,dump_engine(self.e))

if __name__=='__main__':unittest.main()
