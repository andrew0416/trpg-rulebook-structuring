"""Native medicine application across quantity and exact physical stock."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_item_stock as _fixture_test_category2_item_stock
import items as I,world_entities as W,held_equipment as H,state_grants as G
import capability_actions as CAP,item_stock as STOCK,common_checks as C
import action_resources as RESOURCES

class MedicineStockTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_item_stock.ItemStockTests.setUpClass.__func__)
 setUp=_fixture_test_category2_item_stock.ItemStockTests.setUp
 add=_fixture_test_category2_item_stock.ItemStockTests.add
 restored=_fixture_test_category2_item_stock.ItemStockTests.restored
 def held(self,actor,name,uid='medicine'):
  rule=self.e.r.item_effects(name)[1]['id']
  W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual medicine instance',kind='item_instance',item_rule_id=rule,owner_id=actor.entity_id)
  I.equip_held(self.e,actor,name,source_instance_id=uid)
 def turn(self,actor):
  self.e.start_round([self.a,self.p]);self.e.start_of_turn(actor)
 def snap(self):
  return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(x) for x in self.e.gm.everyone],getattr(self.e,'_physical_objects',{})),{id(self.r):self.r})
 def test_same_actual_self_healing_and_full_cost_for_both_kinds_and_stock_forms(self):
  for kind in ('trainer','pokemon'):
   for physical in (False,True):
    with self.subTest(kind=kind,physical=physical):
     self.setUp();actor=self.a if kind=='trainer' else self.p
     actor.spec['items']={'상처약':2};actor.hp=1
     if physical:self.held(actor,'상처약')
     self.turn(actor)
     result=self.e.use_item(actor,'상처약',held_selection='medicine' if physical else None)
     self.assertEqual(result,(1,0));self.assertEqual(actor.hp,21)
     self.assertEqual(actor.budget,{'standard':0,'shift':0,'swift':1})
     self.assertIsNone(getattr(actor,'pending_action_loss',None))
     self.assertEqual(actor.spec['items']['상처약'],2 if physical else 1)
     if physical:
      self.assertIn('consumed',self.e._physical_objects['medicine']);self.assertFalse(H.entries(actor))
      with self.assertRaises(ValueError):I.equip_held(self.e,actor,'상처약',source_instance_id='medicine')
 def test_other_recipient_shared_debt_and_qualified_medic_exception(self):
  for reverse,medic in ((False,False),(True,False),(False,True)):
   self.setUp();user,target=(self.p,self.a) if reverse else (self.a,self.p)
   if medic:user.spec['edges']=['edge/메딕-훈련'];user.spec['skills']['의학']='초보'
   self.held(user,'상처약');target.hp=1;self.turn(user)
   self.e.use_item(user,'상처약',target,held_selection='medicine')
   self.assertEqual(target.hp,21);self.assertEqual(user.budget,{'standard':0,'shift':1,'swift':1})
   self.assertEqual(getattr(target,'pending_action_loss',None),None if medic else {'standard':1,'swift':1})
   self.e.end_of_turn(user);self.e.start_of_turn(target)
   self.assertEqual(target.budget,{'standard':1 if medic else 0,'shift':1,'swift':1 if medic else 0})
 def test_native_x_restriction_effect_and_reset_use_same_physical_consumer(self):
  self.held(self.a,'플러스파워');self.turn(self.a);before=self.snap()
  self.assertEqual(self.e.use_item(self.a,'플러스파워',self.a,held_selection='medicine'),(0,0));self.assertEqual(self.snap(),before)
  self.assertEqual(self.e.use_item(self.a,'플러스파워',self.p,held_selection='medicine'),(1,0))
  self.assertEqual(self.p.stages['atk'],2);self.assertIn('consumed',self.e._physical_objects['medicine'])
  self.e.end_encounter([self.a,self.p]);self.assertEqual(self.p.stages['atk'],0)
 def test_declined_invalid_pending_and_unavailable_uses_do_not_consume(self):
  self.held(self.p,'상처약');self.p.hp=1;self.turn(self.p);before=self.snap()
  self.assertEqual(self.e.use_item(self.p,'상처약',held_selection='medicine',accepted=False),(0,0));self.assertEqual(self.snap(),before)
  for opts in ({'count':0.5},{'count':2},{'duration_minutes':1},{'selected_move':'move/몸통'}):
   with self.assertRaises(ValueError):self.e.use_item(self.p,'상처약',held_selection='medicine',**opts)
   self.assertEqual(self.snap(),before)
  self.p.budget['shift']=0;before=self.snap()
  self.assertEqual(self.e.use_item(self.p,'상처약',held_selection='medicine'),(0,0));self.assertEqual(self.snap(),before)
  self.setUp();self.held(self.p,'이펙트가드');self.turn(self.p);before=self.snap()
  self.assertIsInstance(self.e.use_item(self.p,'이펙트가드',held_selection='medicine'),C.PendingDecision);self.assertEqual(self.snap(),before)
  self.setUp();self.held(self.a,'타우린');before=self.snap()
  with self.assertRaises(ValueError):self.e.use_item(self.a,'타우린',held_selection='medicine')
  self.assertEqual(self.snap(),before)
 def test_selected_instance_releases_load_and_preserves_independent_held_effect(self):
  G.replace_baseline(self.e,self.p,'abilities',['배달부'])
  self.held(self.p,'상처약');self.held(self.p,'선제공격손톱','claw')
  CAP.set_carried(self.e,self.p,[{'id':'medicine','weight_kg':0.1}],'actual weighed medicine')
  bonus=self.p.initiative_bonus;self.p.hp=1;self.e.use_item(self.p,'상처약',held_selection='medicine')
  self.assertEqual([x['instance_id'] for x in H.entries(self.p)],['claw']);self.assertEqual(self.p.initiative_bonus,bonus)
  self.assertFalse(self.p.spec['_carried_load']['objects']);self.assertTrue(self.e.validate_state()['valid'])
 def test_native_herbal_and_status_cure_do_not_require_quantity_stock(self):
  for actor_name in ('a','p'):
   self.setUp();actor=getattr(self,actor_name);self.held(actor,'힘의가루');actor.spec.pop('items',None);actor.hp=1
   self.assertEqual(self.e.use_item(actor,'힘의가루',held_selection='medicine'),(1,0));self.assertEqual(actor.hp,26)
   self.assertTrue(actor.buffs);self.assertIn('consumed',self.e._physical_objects['medicine'])
   self.held(actor,'해독제','antidote');self.e.apply_status(actor,'독');self.assertIn('독',actor.conditions)
   self.e.use_item(actor,'해독제',held_selection='antidote');self.assertNotIn('독',actor.conditions)
 def test_native_medicine_refuses_conflicting_shared_debt_before_cost(self):
  for item in ('상처약','플러스파워'):
   for physical in (False,True):
    with self.subTest(item=item,physical=physical):
     self.setUp();self.a.spec['items']={item:1};self.p.hp=1
     if physical:self.held(self.a,item)
     self.turn(self.a);RESOURCES.schedule(self.p,{'standard':1});before=self.snap()
     with self.assertRaisesRegex(ValueError,'conjunction policy'):
      self.e.use_item(self.a,item,self.p,held_selection='medicine' if physical else None)
     self.assertEqual(self.snap(),before)
 def test_payment_failure_is_atomic_before_healing_or_recipient_debt(self):
  self.held(self.a,'상처약');self.p.hp=1;self.turn(self.a);before=self.snap();original=STOCK.debit
  def fail_after_debit(*args,**kwargs):
   original(*args,**kwargs);raise ValueError('injected physical payment failure')
  with patch.object(STOCK,'debit',side_effect=fail_after_debit):
   with self.assertRaises(ValueError):self.e.use_item(self.a,'상처약',self.p,held_selection='medicine')
  self.assertEqual(self.snap(),before)
 def test_consumption_recipient_debt_and_exact_instance_survive_both_restore_paths(self):
  for reverse in (False,True):
   self.setUp();user,target=(self.p,self.a) if reverse else (self.a,self.p)
   self.held(user,'상처약');target.hp=1;self.turn(user);snapshot=self.e.gm.snapshot()
   self.e.use_item(user,'상처약',target,held_selection='medicine')
   loaded=self.restored();saved_user=next(x for x in loaded.gm.everyone if x.entity_id==user.entity_id);saved_target=next(x for x in loaded.gm.everyone if x.entity_id==target.entity_id)
   self.assertEqual(saved_target.hp,21);self.assertEqual(saved_target.pending_action_loss,{'standard':1,'swift':1});self.assertFalse(H.entries(saved_user))
   self.assertEqual(loaded._physical_objects['medicine']['consumed']['by_actor_id'],saved_user.entity_id)
   self.e.gm.restore(snapshot);self.assertEqual(target.hp,1);self.assertNotIn('consumed',self.e._physical_objects['medicine'])
   self.e.use_item(user,'상처약',target,held_selection='medicine');self.assertEqual(target.hp,21)

if __name__=='__main__':unittest.main()
