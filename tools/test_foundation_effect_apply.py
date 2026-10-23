from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_food_instances as F
import effect_instances as E,food_effects as FOOD,condition_instances as CI

class EffectApplyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.FoodInstanceTests.setUpClass()
 def fixture(self):
  f=F.FoodInstanceTests();f.setUp();return f
 def test_invalid_transfer_does_not_change_owner_history_or_capacity(self):
  f=self.fixture();f.feed(f.p);record=f.p.buffs[0];before=deepcopy(record)
  with self.assertRaises(ValueError):
   E.transfer(f.e,f.p,f.other,record,source='move/벌레먹기',capacity={})
  self.assertEqual(record,before);self.assertIs(f.p.buffs[0],record);self.assertFalse(f.other.buffs)
 def test_native_transfer_rolls_back_storage_and_metadata_on_late_failure(self):
  f=self.fixture();f.feed(f.p);before=f.snap()
  with patch.object(FOOD,'honey_thief_after_transfer',side_effect=ValueError('late transfer rejection')):
   with self.assertRaisesRegex(ValueError,'late transfer rejection'):
    FOOD.transfer_live(f.e,f.other,f.p,'move/벌레먹기')
  self.assertEqual(f.snap(),before);f.valid()
 def test_unregistered_applying_actor_rejects_before_sequence(self):
  f=self.fixture();f.feed(f.p);original=deepcopy(f.p.spec)
  from engine import Combatant
  outsider=Combatant(f.r,dict(f.a.spec,id='outside-effect-actor',name='outsider'))
  with self.assertRaisesRegex(ValueError,'registered'):
   E.create(f.e,f.p,kind='fixture',source='fixture/source',payload={'kind':'fixture'},
    capacity={'bucket':'fixture','source':'fixture/source'},lifetime={'boundary':'explicit'},applied_by=outsider)
  self.assertEqual(f.p.spec,original)
 def test_immunity_blocks_instance_and_explicit_exception_applies(self):
  f=self.fixture();before=f.p.spec.get(E.SEQUENCE,0)
  with patch.object(f.e,'immune_to',return_value='fixture/immunity'):
   self.assertFalse(f.e.apply_status(f.p,'사슬묶기',parameters={'move_id':'struggle'},applied_by=f.a))
   self.assertEqual(f.p.spec.get(E.SEQUENCE,0),before);self.assertFalse(CI.records(f.p))
   self.assertTrue(f.e.apply_status(f.p,'사슬묶기',parameters={'move_id':'struggle'},applied_by=f.a,force=True))
  self.assertEqual(CI.records(f.p)[0][E.KEY]['applied_by_actor_id'],f.a.entity_id)
 def test_duplicate_archive_is_rejected_without_second_history(self):
  f=self.fixture();f.e.apply_status(f.p,'사슬묶기',parameters={'move_id':'struggle'},applied_by=f.a)
  row=CI.records(f.p)[0];f.e.cure_status(f.p,'사슬묶기');before=deepcopy(f.p.spec['effect_instance_history'])
  with self.assertRaisesRegex(ValueError,'already archived'):
   E.archive(f.e,f.p,row,state='expired',event={'kind':'condition_cure','condition':'사슬묶기'})
  self.assertEqual(f.p.spec['effect_instance_history'],before);f.valid()

if __name__=='__main__':unittest.main()
