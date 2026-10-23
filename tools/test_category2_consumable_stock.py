"""Real Vitamin and grouped bandage stock through the common adapter."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_medicine_stock as _fixture_test_category2_medicine_stock
import item_stock as STOCK,vitamin_moves as V,frequency as F,held_equipment as H,state_grants as G,common_checks as C

class ConsumableStockTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_medicine_stock.MedicineStockTests.setUpClass.__func__)
 setUp=_fixture_test_category2_medicine_stock.MedicineStockTests.setUp
 add=_fixture_test_category2_medicine_stock.MedicineStockTests.add
 restored=_fixture_test_category2_medicine_stock.MedicineStockTests.restored
 held=_fixture_test_category2_medicine_stock.MedicineStockTests.held
 snap=_fixture_test_category2_medicine_stock.MedicineStockTests.snap
 def bandage(self,user,target,selection,**kw):
  opts=dict(count=2,duration_minutes=1,duration_reason='GM actual grouped application');opts.update(kw)
  return self.e.use_item(user,'붕대',target,held_selection=selection,**opts)
 def pair(self,user):
  G.replace_baseline(self.e,user,'abilities',['배달부'])
  self.held(user,'붕대','b1');self.held(user,'붕대','b2')
 def test_all_six_stat_vitamins_use_real_physical_dose_and_preserve_quantity_stock(self):
  for name,stat in [('맥스업','hp'),('타우린','atk'),('사포닌','def'),('리보플라빈','spa'),('키토산','spd'),('알칼로이드','spe')]:
   self.setUp();self.held(self.a,name);self.a.spec['items']={name:3};before=self.p.spec['stats'][stat]
   self.e.use_item(self.a,name,self.p,held_selection='medicine')
   self.assertEqual(self.p.spec['stats'][stat],before+1);self.assertEqual(len(self.p.spec['vitamins']),1)
   self.assertEqual(self.a.spec['items'][name],3);self.assertIn('consumed',self.e._physical_objects['medicine'])
   self.assertTrue(self.e.validate_state()['valid'])
 def test_special_vitamins_share_stock_preserve_once_limit_selected_move_and_durable_result(self):
  before=self.p.spec['tutor_points'];self.held(self.a,'하트 부스터');self.e.use_item(self.a,V.HEART,self.p,held_selection='medicine')
  self.assertEqual(self.p.spec['tutor_points'],before+2);self.held(self.a,'하트 부스터','second')
  self.e.use_item(self.a,V.HEART,self.p,held_selection='second');self.assertEqual(self.p.spec['tutor_points'],before+2)
  self.assertIn('consumed',self.e._physical_objects['second']);self.assertEqual(len(self.p.spec['vitamins']),1)
  self.e.gm.set_move(self.p,'move/화염방사',True,reason='observed learned move');self.held(self.p,'PP업','pp')
  self.e.use_item(self.p,V.PP,selected_move='move/화염방사',held_selection='pp');self.assertEqual(F.move_frequency(self.e,'move/화염방사',self.p),('at_will',1))
  loaded=self.restored();p=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(p.spec['tutor_points'],before+2);self.assertEqual(F.move_frequency(loaded,'move/화염방사',p),('at_will',1))
  self.assertEqual(p.spec['vitamin_special_uses'][V.PP]['item_stock']['instance_id'],'pp')
 def test_all_vitamins_reject_trainer_target_before_physical_or_action_payment(self):
  for uid in V.ALL_ITEMS:
   self.setUp();self.held(self.a,uid);before=self.snap()
   with self.assertRaises(ValueError):self.e.use_item(self.a,uid,held_selection='medicine')
   self.assertEqual(self.snap(),before)
 def test_grouped_physical_bandages_use_one_interval_and_both_restore_paths(self):
  for reverse in (False,True):
   self.setUp();user,target=(self.p,self.a) if reverse else (self.a,self.p)
   self.pair(user);user.spec['items']={'붕대':5};target.injuries=2
   result=self.bandage(user,target,['b1','b2']);record=result['record']
   self.assertEqual(record['count'],2);self.assertEqual(record['item_stock']['count'],2);self.assertEqual(self.e.elapsed_seconds,60)
   self.assertFalse(H.entries(user));self.assertEqual(user.spec['items']['붕대'],5)
   self.assertEqual({r['instance_id'] for r in record['item_stock']['items']},{'b1','b2'})
   snap=self.e.gm.snapshot();loaded=self.restored();copy=next(c for c in loaded.gm.everyone if c.entity_id==target.entity_id)
   for e,c in ((self.e,target),(loaded,copy)):
    e.advance_time(21600,[c]);self.assertEqual(c.injuries,0);self.assertEqual(c.spec['bandages'][-1]['injuries_healed'],2)
   self.e.gm.restore(snap);self.assertEqual(target.injuries,2);self.assertEqual(target.spec['bandages'][-1]['status'],'active')
 def test_missing_duration_duplicate_selection_and_wrong_counts_never_consume(self):
  self.pair(self.p);before=self.snap()
  self.assertIsInstance(self.e.use_item(self.p,'붕대',self.a,count=2,held_selection=['b1','b2']),C.PendingDecision);self.assertEqual(self.snap(),before)
  for selection,count in ((['b1','b1'],2),(['b1'],2),(['b1','b2'],1),('b1',2)):
   with self.assertRaises(ValueError):self.bandage(self.p,self.a,selection,count=count)
   self.assertEqual(self.snap(),before)
  self.bandage(self.p,self.a,['b1','b2'],accepted=False);self.assertEqual(self.snap(),before)
 def test_group_payment_failure_rolls_back_every_instance_and_application_time(self):
  self.pair(self.p);before=self.snap();original=STOCK.debit
  def fail(e,c,plan):
   result=original(e,c,plan)
   if plan.get('kind')=='held_batch':raise ValueError('injected group payment failure')
   return result
  with patch.object(STOCK,'debit',side_effect=fail):
   with self.assertRaises(ValueError):self.bandage(self.p,self.a,['b1','b2'])
  self.assertEqual(self.snap(),before)

if __name__=='__main__':unittest.main()
