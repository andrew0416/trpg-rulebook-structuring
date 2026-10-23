"""Frozen training obligation: completed grooming funds native Training feats."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_training_state as fixtures
import training_features as T,pokemon_teaching as TEACHING,downtime as D
import state_codec as CODEC

class SharedTimeTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.TrainingStateTests.setUpClass.__func__)
 load=fixtures.TrainingStateTests.load
 def setUp(self):
  fixtures.TrainingStateTests.setUp(self)
  self.t.spec['edges']=['edge/미용사'];self.t.spec['skills']['포켓몬학']=3;self.t.spec['items']={'미용사 킷':1}
 def groom(self):self.e.pokemon_activity(self.t,'groom',targets=self.ps,safe=True)
 def train(self,**kw):
  return self.e.train_pokemon(self.t,[(p,[uid]) for p,uid in zip(self.ps,T.RULES)],minutes=kw.pop('minutes',30),reason='apply Training to completed grooming',request_id=kw.pop('request_id','shared'),from_grooming=True,**kw,safe=True)
 def test_group_uses_completed_hour_and_retains_native_effect_expiry_and_replay(self):
  self.groom();receipt=self.train();self.assertEqual(self.e.elapsed_seconds,3600);self.assertEqual(receipt['time_cost_seconds'],0)
  self.assertEqual(len(receipt['completed_training_credits']),4);self.assertEqual(self.e.move_profile(self.ps[0],'land')[0],7)
  self.assertTrue(all(p.spec['training_credit']['applications']==['training_regime'] for p in self.ps))
  self.assertEqual(self.train(),receipt)
  e,actors=self.load();choices=[(actors[p.entity_id],[uid]) for p,uid in zip(self.ps,T.RULES)]
  before=CODEC.dump_engine(e);self.assertEqual(e.train_pokemon(actors[self.t.entity_id],choices,minutes=30,reason='apply Training to completed grooming',request_id='shared',from_grooming=True,safe=True),receipt);self.assertEqual(before,CODEC.dump_engine(e))
  D.extended_rest(e,actors[self.t.entity_id],4);self.assertFalse(T.records(actors[self.ps[0].entity_id]))
 def test_missing_later_credit_and_excess_duration_change_nothing(self):
  self.groom();self.ps[-1].spec.pop('training_credit');before=CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):self.train()
  self.assertEqual(before,CODEC.dump_engine(self.e));self.groom();before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'cover training duration'):self.train(minutes=61)
  self.assertEqual(before,CODEC.dump_engine(self.e))
 def test_new_request_cannot_consume_same_credit_twice(self):
  self.groom();self.train();before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'already consumed'):self.train(request_id='second')
  self.assertEqual(before,CODEC.dump_engine(self.e))
 def test_late_credit_failure_rolls_back_all_effects_and_consumption(self):
  self.groom();before=CODEC.dump_engine(self.e);native=TEACHING.consume_credit
  def fail(target,application):
   native(target,application)
   if target.entity_id==self.ps[-1].entity_id:raise ValueError('late consumption')
  with patch.object(TEACHING,'consume_credit',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'late consumption'):self.train()
  self.assertEqual(before,CODEC.dump_engine(self.e))

if __name__=='__main__':unittest.main()
