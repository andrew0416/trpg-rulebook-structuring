"""Full-paid Breather reuses real native Burrow and Teleport producers."""
import json
from pathlib import Path
from unittest.mock import patch
import unittest
from engine import Rules,Engine
from grid import Grid
import test_category2_breather_nonland as NONLAND
import breather as B,common_checks as C,condition_recovery as RECOVERY
import effects_ext as EXT,movement_actions as M,state_codec as CODEC
import state_grants as G,temporary_hp as TEMP

ROOT=Path(__file__).resolve().parents[1]

class BreatherTransferTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 setUp=NONLAND.NonlandBreatherTests.setUp
 movement=NONLAND.NonlandBreatherTests.movement
 options=NONLAND.NonlandBreatherTests.options
 take=NONLAND.NonlandBreatherTests.take
 def pokemon(self):
  self.e=Engine(self.r,seed=5);self.e.grid=Grid(7,5)
  self.a=self.make_actor('pokemon/retreater','pokemon');self.a.side='party';self.a.pos=(2,2)
  self.e.everyone=self.e.gm.everyone=[self.a,self.b]
  self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a);self.b.aoo_used=True
  TEMP.grant(self.e,self.a,12)
 def transfer_options(self,mode,**changes):
  if mode=='teleport':
   self.pokemon();self.movement(teleport=6)
   result=self.options(path=[(2,2),(6,2)],movement_mode=mode,movement_options={'surface_contact':True})
  else:
   self.movement(burrow=6)
   result=self.options(movement_mode=mode,movement_options={'diggable':True,'surface':False})
  result.update(changes);return result
 def test_burrow_full_creates_actual_tunnel_without_ground_entries_and_defers_real_upkeep(self):
  options=self.transfer_options('burrow');self.e.grid.blocking.add((4,2))
  with patch.object(M,'follow_paid_transfer',wraps=M.follow_paid_transfer) as transfer,patch.object(EXT,'on_enter_cell',side_effect=AssertionError('underground path is not ground entry')):
   result=self.e.take_breather(self.a,**options)
  self.assertTrue(result['completed']);self.assertEqual((result['movement']['distance'],result['movement']['steps']),(4,4))
  self.assertEqual((self.a.pos,self.a.temp_hp,self.a._action_history.count('full'),transfer.call_count),((6,2),5,1,1))
  self.assertTrue(self.a.spec['_burrow']['underground']);self.assertEqual(self.e._burrow_tunnels[-1]['body_size'],'medium')
  self.assertEqual(self.e._burrow_tunnels[-1]['path'],tuple(options['path']))
  self.assertEqual(self.a.budget,{'standard':0,'shift':0,'swift':1})
  self.e.end_of_turn(self.a);self.assertTrue(self.a.spec['_burrow']['standard_debt'])
  self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a)
  self.assertEqual(self.a.budget['standard'],0);self.assertFalse(self.a.spec['_burrow']['standard_debt'])
 def test_burrow_from_actual_underground_surfaces_before_recovery_and_no_new_upkeep_debt(self):
  self.movement(burrow=6)
  self.e.burrow_move(self.a,[(2,2),(3,2)],diggable=True,reason_text='actual prior turn tunnel')
  self.e.end_of_turn(self.a);self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a)
  entries=[];original=EXT.on_enter_cell
  with patch.object(EXT,'on_enter_cell',side_effect=lambda e,c,p:(entries.append(p),original(e,c,p))[-1]):
   result=self.take(path=[(3,2),(4,2),(5,2),(6,2)],movement_mode='burrow',movement_options={'diggable':True,'surface':True})
  self.assertTrue(result['completed']);self.assertEqual(entries,[(6,2)]);self.assertFalse(self.a.spec['_burrow']['underground'])
  self.assertEqual((self.a.temp_hp,len(self.e._burrow_tunnels)),(5,2))
  self.e.end_of_turn(self.a);self.assertFalse(self.a.spec['_burrow'].get('standard_debt',False))
 def test_teleport_full_uses_actual_once_per_round_and_no_walking_or_extra_shift(self):
  options=self.transfer_options('teleport');self.e.apply_status(self.a,'혼란')
  with patch.object(M,'follow_paid_transfer',wraps=M.follow_paid_transfer) as transfer,patch.object(M,'follow_paid_path',side_effect=AssertionError('Teleport is not walking')):
   result=self.e.take_breather(self.a,**options)
  self.assertTrue(result['completed']);self.assertEqual((self.a.pos,self.a.temp_hp,transfer.call_count),((6,2),0,1))
  self.assertEqual(self.a.budget,{'standard':0,'shift':0,'swift':1});self.assertEqual(self.a._action_history.count('full'),1)
  self.assertEqual(self.a.spec['_teleport']['used_round'],self.e.round_no);self.assertNotIn('혼란',self.a.conditions)
  before=CODEC.dump_engine(self.e);self.assertEqual(self.e.take_breather(self.a,**options),result)
  self.assertEqual(CODEC.dump_engine(self.e),before)
  with self.assertRaisesRegex(ValueError,'once per combat round'):
   self.e.teleport(self.a,(5,2),surface_contact=True,reason_text='second actual same-round attempt')
 def test_missing_or_invalid_teleport_world_observations_fail_before_full_or_save(self):
  cases=[({'surface_contact':False},[(2,2),(6,2)],ValueError),
         ({},[(2,2),(6,2)],C.PendingDecision),
         ({'surface_contact':True,'altitude':1},[(2,2),(3,2)],ValueError),
         ({'surface_contact':True},[(2,2),(3,2),(6,2)],ValueError)]
  for observations,path,result_type in cases:
   with self.subTest(observations=observations,path=path):
    self.setUp();options=self.transfer_options('teleport',movement_options=observations,path=path);before=CODEC.dump_engine(self.e)
    if result_type is C.PendingDecision:self.assertIsInstance(self.e.take_breather(self.a,**options),result_type)
    else:
     with self.assertRaises(result_type):self.e.take_breather(self.a,**options)
    self.assertEqual(CODEC.dump_engine(self.e),before)
  self.setUp();self.movement(teleport=6);before=CODEC.dump_engine(self.e)
  self.assertIsInstance(self.take(path=[(2,2),(6,2)],movement_mode='teleport',movement_options={'surface_contact':True}),C.PendingDecision)
  self.assertEqual(CODEC.dump_engine(self.e),before)
 def test_actual_teleport_reaction_then_changed_destination_resumes_after_json_without_repay_or_aoo(self):
  options=self.transfer_options('teleport');self.b.aoo_used=False;departure=M.departure
  def obstruct(e,c,q,altitude):
   permitted=departure(e,c,q,altitude);e.grid.blocking.add((6,2));return permitted
  with patch.object(M,'departure',side_effect=obstruct),patch.object(self.e,'use_move',wraps=self.e.use_move) as attack:
   with self.assertRaisesRegex(ValueError,'line of sight'):self.e.take_breather(self.a,**options)
   self.assertEqual(attack.call_count,1)
  self.assertEqual((self.a.pos,self.a._action_history.count('full')),((2,2),1));self.assertNotIn('_teleport',self.a.spec)
  restored=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  current=next(c for c in restored.everyone if c.entity_id==self.a.entity_id);restored.grid.blocking.remove((6,2))
  hp=current.hp
  with patch.object(RECOVERY,'saving_check',side_effect=AssertionError('permission save cannot repeat')),patch.object(restored,'use_move',side_effect=AssertionError('same reaction cannot repeat')):
   result=restored.take_breather(current,**options)
  self.assertTrue(result['completed']);self.assertEqual((current.pos,current.hp,current._action_history.count('full')),((6,2),hp,1))
 def test_arrived_transfer_recovery_error_restores_and_does_not_repeat_tunnel_or_teleport_frequency(self):
  for mode in ('burrow','teleport'):
   with self.subTest(mode=mode):
    self.setUp();options=self.transfer_options(mode);self.e.apply_status(self.a,'혼란')
    with patch.object(B,'_disadvantage',side_effect=RuntimeError('actual post-transfer recovery')):
     with self.assertRaisesRegex(RuntimeError,'post-transfer'):self.e.take_breather(self.a,**options)
    self.assertEqual((self.a.pos,self.a.temp_hp),((6,2),12));self.assertIn('혼란',self.a.conditions)
    restored=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
    current=next(c for c in restored.everyone if c.entity_id==self.a.entity_id)
    tunnels=len(getattr(restored,'_burrow_tunnels',[]));used=current.spec.get('_teleport',{}).get('used_round')
    with patch.object(RECOVERY,'saving_check',side_effect=AssertionError('permission save cannot repeat')):
     result=restored.take_breather(current,**options)
    self.assertTrue(result['completed']);self.assertNotIn('혼란',current.conditions)
    self.assertEqual((current.temp_hp,current._action_history.count('full')),(5 if mode=='burrow' else 0,1))
    self.assertEqual((len(getattr(restored,'_burrow_tunnels',[])),current.spec.get('_teleport',{}).get('used_round')),(tunnels,used))
    self.assertEqual(restored.take_breather(current,**options),result)
 def test_burrow_observations_and_underground_curse_hold_before_payment(self):
  self.movement(burrow=6);before=CODEC.dump_engine(self.e)
  self.assertIsInstance(self.take(movement_mode='burrow',movement_options={}),C.PendingDecision)
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.e.grid.blocking.add((6,2));before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'blocked'):
   self.take(movement_mode='burrow',movement_options={'diggable':True,'surface':True})
  self.assertEqual(CODEC.dump_engine(self.e),before);self.e.grid.blocking.clear()
  self.e.apply_status(self.a,'저주',source='move/저주',applied_by=self.b);before=CODEC.dump_engine(self.e)
  self.assertIsInstance(self.take(movement_mode='burrow',movement_options={'diggable':True}),C.PendingDecision)
  self.assertEqual(CODEC.dump_engine(self.e),before)
 def test_stationary_highest_native_mode_does_not_create_a_transfer_or_frequency_use(self):
  for mode in ('burrow','teleport'):
   with self.subTest(mode=mode):
    self.setUp()
    if mode=='teleport':self.pokemon()
    self.movement(**{mode:6});self.e.apply_status(self.a,'구속')
    result=self.take(path=[(2,2)],movement_mode=mode,retreat_reason='Actual Stuck permits no retreat; actual maximum distance is zero')
    self.assertTrue(result['completed']);self.assertNotIn('구속',self.a.conditions);self.assertEqual(self.a.pos,(2,2))
    self.assertNotIn('_teleport',self.a.spec);self.assertFalse(getattr(self.e,'_burrow_tunnels',[]))
 def test_native_shift_entries_use_same_actual_transfer_and_preserve_cost(self):
  for mode in ('burrow','teleport'):
   with self.subTest(mode=mode):
    self.setUp()
    if mode=='teleport':self.pokemon()
    self.movement(**{mode:6})
    with patch.object(M,'follow_paid_transfer',wraps=M.follow_paid_transfer) as transfer:
     if mode=='burrow':result=self.e.burrow_move(self.a,[(2,2),(3,2)],diggable=True,reason_text='actual native tunnel')
     else:result=self.e.teleport(self.a,(6,2),surface_contact=True,reason_text='actual native destination')
    self.assertTrue(result);self.assertEqual((transfer.call_count,self.a.budget['standard'],self.a.budget['shift']),(1,1,0))
 def test_changed_actual_curse_origin_altitude_after_surface_entry_cannot_use_planar_cure(self):
  self.movement(burrow=6);self.e.apply_status(self.a,'저주',source='move/저주',applied_by=self.b)
  original=EXT.on_enter_cell
  def entry(e,c,p):
   original(e,c,p)
   G.transition(e,self.b,lambda s,origin:origin.spec.__setitem__('_movement_altitude',1))
  with patch.object(EXT,'on_enter_cell',side_effect=entry):
   with self.assertRaisesRegex(ValueError,'3D or underground'):
    self.take(movement_mode='burrow',movement_options={'diggable':True,'surface':True})
  self.assertEqual((self.a.pos,self.a.temp_hp),((6,2),12));self.assertIn('저주',self.a.conditions)
  self.assertEqual(self.b.spec['_movement_altitude'],1)

if __name__=='__main__':unittest.main()
