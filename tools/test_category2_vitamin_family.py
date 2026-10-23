"""All eight sourced Vitamins use the same stock/payment/application boundary."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_medicine_stock as _fixture_test_category2_medicine_stock
import vitamin_moves as V,frequency as F,move_state as M,builder

class VitaminFamilyTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_medicine_stock.MedicineStockTests.setUpClass.__func__)
 setUp=_fixture_test_category2_medicine_stock.MedicineStockTests.setUp
 add=_fixture_test_category2_medicine_stock.MedicineStockTests.add
 restored=_fixture_test_category2_medicine_stock.MedicineStockTests.restored
 held=_fixture_test_category2_medicine_stock.MedicineStockTests.held
 snap=_fixture_test_category2_medicine_stock.MedicineStockTests.snap

 def prepare(self,uid):
  self.a.spec['items']={uid:2}
  self.e.gm.set_move(self.p,'move/용의춤',True,reason='actual learned Move before dose')
  return {'selected_move':'move/용의춤'} if uid==V.PP else {}

 def test_eight_source_rows_actual_effects_and_prices_survive_both_restore_paths(self):
  expected={'item/맥스업':('hp',4900),'item/타우린':('atk',4900),'item/사포닌':('def',4900),
            'item/리보플라빈':('spa',4900),'item/키토산':('spd',4900),'item/알칼로이드':('spe',4900),
            V.HEART:(None,9800),V.PP:(None,9800)}
  for uid,(stat,price) in expected.items():
   with self.subTest(uid=uid):
    self.setUp();opts=self.prepare(uid)
    header=self.r.item_effects(uid)[1]
    self.assertEqual((header['id'],header['price'],header['use']),(uid,price,'consumable'))
    before=deepcopy(self.p.spec['stats']);runtime=deepcopy(self.p.stats);tp=self.p.spec['tutor_points'];hp=self.p.base_max_hp
    self.assertEqual(self.e.use_item(self.a,uid,self.p,**opts),(1,0))
    if stat:before[stat]+=1;runtime[stat]+=1
    self.assertEqual(self.p.spec['stats'],before);self.assertEqual(self.p.stats,runtime)
    self.assertEqual(self.p.base_max_hp,hp+(3 if stat=='hp' else 0))
    self.assertEqual(self.p.spec['tutor_points'],tp+(2 if uid==V.HEART else 0))
    self.assertEqual(F.move_frequency(self.e,'move/용의춤',self.p),('at_will',1) if uid==V.PP else ('every_other_turn',1))
    self.assertEqual(self.p.spec['vitamins'],[uid]);self.assertEqual(self.a.spec['items'][uid],1)
    if stat:
     record=[r for r in self.p.spec['stat_history'] if r['event']=='vitamin'][-1]
     self.assertEqual((record['source'],record['actor_id'],record['stat'],record['delta']),(uid,self.p.entity_id,stat,1))
     self.assertEqual(record['item_stock']['count'],1)
    snapshot=self.e.gm.snapshot();loaded=self.restored();self.e.gm.restore(snapshot)
    for e in (self.e,loaded):
     p=next(c for c in e.gm.everyone if c.entity_id==self.p.entity_id)
     self.assertEqual((p.spec['stats'],p.stats,p.spec['vitamins']),(before,runtime,[uid]))
     self.assertEqual(M.vitamin_state(e.r,p.spec)['occupied'],1)
     self.assertTrue(e.validate_state()['valid'])

 def test_all_eight_use_one_standard_and_cannot_spend_or_apply_twice_in_same_turn(self):
  for uid in sorted(V.ALL_ITEMS):
   with self.subTest(uid=uid):
    self.setUp();opts=self.prepare(uid)
    self.e.start_round([self.a,self.p]);self.e.start_of_turn(self.a)
    self.e.use_item(self.a,uid,self.p,**opts)
    self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.spec['items'][uid],1)
    before=self.snap()
    self.assertEqual(self.e.use_item(self.a,uid,self.p,**opts),(0,0));self.assertEqual(self.snap(),before)
    self.assertEqual(len(self.p.spec['vitamins']),1)

 def test_late_stat_application_failure_keeps_stock_instance_stats_and_action_unspent(self):
  original=builder.record_allocation
  def fail_after_application(*args,**kwargs):
   original(*args,**kwargs)
   raise ValueError('injected post-allocation failure')
  for physical in (False,True):
   with self.subTest(physical=physical):
    self.setUp();self.prepare('item/타우린')
    opts={}
    if physical:self.held(self.a,'타우린');opts['held_selection']='medicine'
    self.e.start_round([self.a,self.p]);self.e.start_of_turn(self.a);before=self.snap()
    with patch.object(builder,'record_allocation',side_effect=fail_after_application):
     with self.assertRaisesRegex(ValueError,'post-allocation'):self.e.use_item(self.a,'타우린',self.p,**opts)
    self.assertEqual(self.snap(),before)
    self.assertEqual(self.e.use_item(self.a,'타우린',self.p,**opts),(1,0))
    self.assertEqual(self.a.spec['items']['item/타우린'],2 if physical else 1)
    if physical:self.assertIn('consumed',self.e._physical_objects['medicine'])
    self.assertEqual(self.a.budget['standard'],0)

 def test_unknown_source_history_and_noninteger_stat_effect_fail_before_payment(self):
  self.prepare('item/타우린');self.p.spec['vitamins']=['상처약'];before=self.snap()
  with self.assertRaises(ValueError):self.e.use_item(self.a,'타우린',self.p)
  self.assertEqual(self.snap(),before);self.p.spec.pop('vitamins')
  original=self.r.item_effects
  def corrupt(name):
   effects,header=original(name)
   if header.get('id')=='item/타우린':effects=deepcopy(effects);effects[0]['value']=True
   return effects,header
  before=self.snap()
  with patch.object(self.r,'item_effects',side_effect=corrupt):
   with self.assertRaisesRegex(ValueError,'reviewed exact effect'):self.e.use_item(self.a,'타우린',self.p)
  self.assertEqual(self.snap(),before)

if __name__=='__main__':unittest.main()
