"""Actual physical food intake and shared actor/item stock state."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as FIX
from builder import build_pokemon
from engine import Engine
import items as I,world_entities as W,held_equipment as H,state_grants as G
import capability_actions as CAP,food_effects as FOOD,common_checks as C

class ItemStockTests(unittest.TestCase):
 setUpClass=classmethod(FIX.ProgressionStateTests.setUpClass.__func__)
 add=FIX.ProgressionStateTests.add
 restored=FIX.ProgressionStateTests.restored
 def setUp(self):
  FIX.ProgressionStateTests.setUp(self)
  self.p=self.add(build_pokemon(self.r,'이브이',20,moves=[],abilities=[]))
 def held(self,actor,name,uid):
  W.register_object(self.e,uid,location={'kind':'unknown'},reason='observed actual food instance',kind='item_instance',item_rule_id='item/'+name,owner_id=actor.entity_id)
  I.equip_held(self.e,actor,name,source_instance_id=uid)
 def eat(self,actor,name='오랭열매',uid='berry',**options):
  return self.e.use_item(actor,name,held_selection=uid,duration_minutes=1,duration_reason='GM actual intake interval',**options)
 def snap(self):
  return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(x) for x in self.e.gm.everyone],getattr(self.e,'_physical_objects',{}),self.e.log_lines),{id(self.r):self.r})
 def test_same_real_food_consumer_for_both_actor_kinds_and_stock_sources(self):
  for actor in [self.a,self.p]:
   uid='berry:'+actor.entity_id;self.held(actor,'오랭열매',uid);actor.spec['items']={'오랭열매':2}
   before=actor.hp;result=self.eat(actor,uid=uid)
   self.assertEqual(actor.hp,before);self.assertEqual(actor.spec['items']['오랭열매'],2)
   self.assertEqual(result['item_stock']['instance_id'],uid);self.assertFalse(H.entries(actor))
   self.assertIn('consumed',self.e._physical_objects[uid]);actor.hp=actor.base_max_hp//2;hp=actor.hp
   self.e.consume_food_buff(actor,buff_id=result['buff_id'],action_kind='swift',action_reason='actual source-approved buff use')
   self.assertEqual(actor.hp,hp+5)
   result=self.e.use_item(actor,'오랭열매',duration_minutes=1,duration_reason='same intake from quantity stock')
   self.assertEqual(actor.spec['items']['오랭열매'],1);self.assertEqual(result['item_stock']['kind'],'quantity')
 def test_selected_of_two_held_objects_is_consumed_other_effect_stays(self):
  G.replace_baseline(self.e,self.p,'abilities',['배달부'])
  self.held(self.p,'오랭열매','berry');self.held(self.p,'선제공격손톱','claw')
  bonus=self.p.initiative_bonus;self.eat(self.p)
  self.assertEqual([r['instance_id'] for r in H.entries(self.p)],['claw'])
  self.assertEqual(self.p.initiative_bonus,bonus)
  self.assertEqual(self.e._physical_objects['claw']['equipped_by'],self.p.entity_id)
  self.assertTrue(self.e.validate_state()['valid'])
 def test_pending_refused_wrong_item_and_buff_limit_leave_object_time_and_stock(self):
  self.held(self.p,'오랭열매','berry');before=self.snap()
  self.assertIsInstance(self.e.use_item(self.p,'오랭열매',held_selection='berry'),C.PendingDecision)
  self.assertEqual(self.snap(),before)
  self.eat(self.p,accepted=False);self.assertEqual(self.snap(),before)
  with self.assertRaises(ValueError):self.eat(self.p,name='자뭉열매')
  self.assertEqual(self.snap(),before)
  self.p.buffs.append({'id':'existing','source':FOOD.FOOD});before=self.snap()
  with self.assertRaises(ValueError):self.eat(self.p)
  self.assertEqual(self.snap(),before)
 def test_actual_food_failure_after_payment_rolls_back_entire_shared_state(self):
  self.held(self.p,'오랭열매','berry');before=self.snap()
  with patch.object(FOOD,'grant_buff',side_effect=ValueError('injected later food state failure')):
   with self.assertRaises(ValueError):self.eat(self.p)
  self.assertEqual(self.snap(),before)
 def test_consumed_instance_cannot_be_reused_reequipped_or_recarried(self):
  self.held(self.p,'오랭열매','berry');self.eat(self.p);before=self.snap()
  for action in [lambda:self.eat(self.p),lambda:I.equip_held(self.e,self.p,'오랭열매',source_instance_id='berry'),lambda:CAP.set_carried(self.e,self.p,[{'id':'berry','weight_kg':0.1}],'attempted reuse')]:
   with self.assertRaises(ValueError):action()
   self.assertEqual(self.snap(),before)
 def test_destroyed_remnant_can_be_carried_but_cannot_be_equipped_or_eaten(self):
  self.held(self.p,'오랭열매','berry')
  I.destroy_equipment(self.e,self.p,'berry',reason='actual resolved destruction')
  CAP.set_carried(self.e,self.p,[{'id':'berry','weight_kg':0.1}],'actual remnant weighed and lifted')
  self.assertEqual(self.e._physical_objects['berry']['carrier_id'],self.p.entity_id)
  self.assertIn('destroyed',self.e._physical_objects['berry']);self.assertTrue(self.e.validate_state()['valid'])
  with self.assertRaises(ValueError):I.equip_held(self.e,self.p,'오랭열매',source_instance_id='berry')
  with self.assertRaises(ValueError):self.eat(self.p)
  loaded=self.restored();self.assertIn('destroyed',loaded._physical_objects['berry'])
  self.assertEqual(loaded._physical_objects['berry']['carrier_id'],self.p.entity_id)
 def test_actual_carry_load_is_released_when_that_held_instance_is_consumed(self):
  self.held(self.a,'오랭열매','berry')
  CAP.set_carried(self.e,self.a,[{'id':'berry','weight_kg':0.1}],'actual weighed held berry')
  self.eat(self.a)
  self.assertFalse(self.a.spec['_carried_load']['objects'])
  self.assertIsNone(self.e._physical_objects['berry'].get('carrier_id'))
  self.assertTrue(self.e.validate_state()['valid'])
 def test_saved_consumption_and_gm_rewind_preserve_exact_instance_and_buff_source(self):
  self.held(self.p,'오랭열매','berry');snapshot=self.e.gm.snapshot();self.eat(self.p)
  loaded=self.restored();p=next(x for x in loaded.gm.everyone if x.entity_id==self.p.entity_id)
  self.assertFalse(H.entries(p));self.assertEqual(p.buffs[0]['item_stock']['instance_id'],'berry')
  self.assertIn('consumed',loaded._physical_objects['berry'])
  with self.assertRaises(ValueError):I.equip_held(loaded,p,'오랭열매',source_instance_id='berry')
  self.e.gm.restore(snapshot);self.assertNotIn('consumed',self.e._physical_objects['berry'])
  self.assertEqual(H.entries(self.p)[0]['instance_id'],'berry');self.assertFalse(self.p.buffs)
  self.eat(self.p);self.assertEqual(len(self.p.buffs),1)
 def test_physical_drink_reuses_existing_healing_and_hourly_limit(self):
  self.held(self.a,'맛있는물','water');self.a.hp=1
  self.eat(self.a,name='맛있는물',uid='water');self.assertEqual(self.a.hp,21)
  self.assertEqual(self.a.spec['drink_history'][-1]['item_stock']['instance_id'],'water')
  self.held(self.a,'맛있는물','water2');before=self.snap()
  with self.assertRaises(ValueError):self.eat(self.a,name='맛있는물',uid='water2')
  self.assertEqual(self.snap(),before)
 def test_consumption_receipt_and_terminal_membership_are_validated_on_load(self):
  self.held(self.p,'오랭열매','berry');self.eat(self.p)
  obj=self.e._physical_objects['berry'];obj['consumed']['at']=True
  self.assertFalse(self.e.validate_state()['valid'])
  with self.assertRaises(ValueError):self.e.export_state()
  obj['consumed']['at']=60;obj['equipped_by']=self.p.entity_id
  self.assertFalse(self.e.validate_state()['valid'])

if __name__=='__main__':unittest.main()
