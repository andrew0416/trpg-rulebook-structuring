"""Actual remote object weights and Focus checks reuse the carrying contract."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_category3_capabilities as _fixture_test_category3_capabilities
import capability_actions as LOAD,state_grants as G,world_entities as W,state_codec as CODEC
from common_checks import PendingDecision
class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category3_capabilities.Tests.setUpClass.__func__)
 actor=_fixture_test_category3_capabilities.Tests.actor
 turn=_fixture_test_category3_capabilities.Tests.turn
 def setUp(self):
  _fixture_test_category3_capabilities.Tests.setUp(self);self.a.spec['skills']['집중']=3
  G.grant(self.a,'capabilities','Telekinetic','fixture:telekinetic','fixture')
 def objects(self,weights):
  for n,weight in enumerate(weights):W.register_object(self.e,'remote'+str(n),location={'kind':'grid','cell':(8+n,2)},weight_kg=weight,reason='actual weighed remote object')
 def lift(self,ids=None):return self.e.telekinetic_lift(self.a,ids or ['remote0'],action_cost='shift',reason='GM declares lifting activity Shift; measured remote positions')
 def test_combined_focus_weight_preserves_independent_positions_and_rejects_overload(self):
  self.objects([15,15]);self.lift(['remote0','remote1'])
  self.assertEqual(LOAD.load(self.a)['weight_kg'],30);self.assertEqual(LOAD.load(self.a)['band'],'staggering')
  for n in range(2):
   obj=self.e._physical_objects['remote'+str(n)]
   self.assertNotIn('carrier_id',obj);self.assertEqual(W.effective_location(self.e,obj)['cell'],(8+n,2))
  self.e.release_telekinetic_load(self.a,reason='released; landing unknown')
  self.objects([24,24]);before=deepcopy((self.a.spec,self.e._physical_objects))
  with self.assertRaises(ValueError):self.lift(['remote0','remote1'])
  self.assertEqual((self.a.spec,self.e._physical_objects),before)
 def test_staggering_uses_focus_dc10_and_actual_failure_release(self):
  self.objects([30]);self.lift();self.turn()
  result=self.e.carry_check(self.a,fixed=[3,3,3]);self.assertIsInstance(result,PendingDecision);self.assertEqual(result.check.total,9)
  self.e.gm.resolve_carry_failure(self.a,outcome='release',reason='failed Focus; released by GM')
  self.assertNotIn('telekinetic_holder_id',self.e._physical_objects['remote0'])
  self.assertEqual(LOAD.load(self.a)['band'],'normal');self.assertTrue(W.validate_world(self.e)['valid'])
 def test_both_restores_keep_remote_holder_and_focus_check_history(self):
  self.objects([30]);self.lift();self.turn();result=self.e.carry_check(self.a,fixed=[4,3,3]);self.assertTrue(result.passed)
  self.e.gm.snapshot('remote');loaded=CODEC.load_engine(self.rules,CODEC.dump_engine(self.e))
  actor=next(c for c in loaded.everyone if c.entity_id==self.a.entity_id)
  self.assertEqual(LOAD.load(actor)['weight_kg'],30)
  self.assertEqual(W.effective_location(loaded,loaded._physical_objects['remote0'])['cell'],(8,2))
  with self.assertRaises(ValueError):loaded.carry_check(actor,fixed=[6,6,6])
  self.e.release_telekinetic_load(self.a,reason='released');self.e.gm.restore('remote')
  self.assertEqual(self.e._physical_objects['remote0']['telekinetic_holder_id'],self.a.entity_id)
  self.e._physical_objects['remote0'].pop('telekinetic_holder_id')
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):self.e.gm.snapshot('invalid')
 def test_eight_metre_boundary_duplicate_and_competing_holder_are_atomic(self):
  self.objects([1,1]);self.lift(['remote1']);self.e.release_telekinetic_load(self.a,reason='release')
  W.register_object(self.e,'remote0',location={'kind':'grid','cell':(10,2)},weight_kg=1,reason='nine metres away')
  before=deepcopy((self.a.spec,self.e._physical_objects))
  for ids in (['remote0'],['remote0','remote0'],['missing']):
   with self.assertRaises(ValueError):self.lift(ids)
   self.assertEqual((self.a.spec,self.e._physical_objects),before)
  W.register_object(self.e,'remote0',location={'kind':'grid','cell':(8,2)},weight_kg=1,reason='within range')
  self.e.gm.set_carried_objects(self.b,[{'id':'remote0','weight_kg':1}],'other actual carrier')
  with self.assertRaises(ValueError):self.lift()
 def test_native_pokemon_capability_uses_actual_focus_rank(self):
  from builder import build_pokemon
  from engine import Combatant
  p=Combatant(self.rules,build_pokemon(self.rules,'캐이시',10,moves=[],abilities=[],pos=(1,2)))
  self.e.everyone.append(p);self.e.gm.everyone.append(p)
  self.objects([1])
  out=self.e.telekinetic_lift(p,['remote0'],action_cost='shift',reason='GM lifting action; actual object')
  self.assertEqual(out['weight_kg'],1);self.assertEqual(self.e._physical_objects['remote0']['telekinetic_holder_id'],p.entity_id)
 def test_actual_remote_paths_validate_whole_batch_before_cost_and_restore(self):
  self.objects([1,1]);self.lift(['remote0','remote1']);self.turn()
  paths={'remote0':[(8,2),(8,3)],'remote1':[(9,2),(10,2)]}
  before=deepcopy((self.a.spec,self.a.budget,self.e._physical_objects))
  with self.assertRaises(ValueError):self.e.move_telekinetic_objects(self.a,paths,action_cost='shift',maximum_distance=1,reason='GM allowance')
  self.assertEqual((self.a.spec,self.a.budget,self.e._physical_objects),before)
  paths['remote1']=[(9,2),(9,3)]
  result=self.e.move_telekinetic_objects(self.a,paths,action_cost='shift',maximum_distance=1,reason='GM allowance')
  self.assertEqual(self.a.budget['shift'],0);self.assertEqual(self.a.pos,(1,2))
  self.assertEqual(result['objects']['remote0']['distance'],1)
  self.e.gm.snapshot('moved');loaded=CODEC.load_engine(self.rules,CODEC.dump_engine(self.e))
  self.assertEqual(W.location_of(loaded._physical_objects['remote0'])['cell'],(8,3))
  self.e.release_telekinetic_load(self.a,reason='released');self.e.gm.restore('moved')
  self.assertEqual(W.location_of(self.e._physical_objects['remote1'])['cell'],(9,3))
 def test_remote_equipment_cannot_bypass_actual_physical_possession(self):
  import items as I
  uid=self.rules.item_effects('오랭열매')[1]['id']
  W.register_object(self.e,'berry',location={'kind':'grid','cell':(8,2)},weight_kg=0.1,kind='item_instance',item_rule_id=uid,owner_id=self.a.entity_id,reason='owned berry at distance')
  self.lift(['berry']);before=deepcopy((self.a.spec,self.e._physical_objects))
  with self.assertRaises(ValueError):I.equip_held(self.e,self.a,'오랭열매',source_instance_id='berry')
  self.assertEqual((self.a.spec,self.e._physical_objects),before)
  self.e.release_telekinetic_load(self.a,reason='released before recovery')
  self.e.gm.set_carried_objects(self.a,[{'id':'berry','weight_kg':0.1}],'physically recovered berry')
  I.equip_held(self.e,self.a,'오랭열매',source_instance_id='berry')
  self.assertEqual(self.e._physical_objects['berry']['equipped_by'],self.a.entity_id)
 def test_remote_registration_cannot_desynchronize_actual_weight_from_held_load(self):
  self.objects([1]);self.lift();before=CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):
   W.register_object(self.e,'remote0',location={'kind':'grid','cell':(8,2)},weight_kg=2,reason='correct actual object weight while remotely held')
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.e.release_telekinetic_load(self.a,reason='release before correcting the actual observed weight')
  W.register_object(self.e,'remote0',location={'kind':'grid','cell':(8,2)},weight_kg=2,reason='correct released object weight')
  self.assertEqual(self.lift()['weight_kg'],2)
 def test_remote_reobservation_cannot_leave_successful_gm_input_with_invalid_world(self):
  self.objects([1]);self.lift();before=CODEC.dump_engine(self.e)
  try:
   W.register_object(self.e,'remote0',location={'kind':'grid','cell':(8,2)},weight_kg=2,reason='new actual weight observation')
  except ValueError:
   self.assertEqual(CODEC.dump_engine(self.e),before)
  report=W.validate_world(self.e);self.assertTrue(report['valid'],report)
  self.assertEqual(LOAD.load(self.a)['weight_kg'],self.e._physical_objects['remote0']['weight_kg'])
 def test_remote_multiobject_late_failure_rolls_back_positions_cost_history_and_rng(self):
  self.objects([1,1]);self.lift(['remote0','remote1']);self.turn();before=CODEC.dump_engine(self.e)
  original=type(self.e.gm)._rec
  def fail_after_record(gm,*args,**kw):
   result=original(gm,*args,**kw)
   if str(args[0]).startswith('Telekinetic object movement'):raise ValueError('late remote movement record failure')
   return result
  with patch.object(type(self.e.gm),'_rec',fail_after_record):
   with self.assertRaisesRegex(ValueError,'late remote'):
    self.e.move_telekinetic_objects(self.a,{'remote0':[(8,2),(8,3)],'remote1':[(9,2),(9,3)]},action_cost='shift',maximum_distance=1,reason='GM allowance')
  self.assertEqual(CODEC.dump_engine(self.e),before)
 def test_caster_movement_rechecks_actual_target_range_before_next_remote_action(self):
  self.objects([1,1]);self.lift(['remote1']);self.turn()
  self.assertTrue(self.e.disengage(self.a,(0,2)))
  self.assertEqual(self.a.pos,(0,2));self.assertEqual(W.location_of(self.e._physical_objects['remote1'])['cell'],(9,2))
  before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'eight'):
   self.e.move_telekinetic_objects(self.a,{'remote1':[(9,2),(8,2)]},action_cost='standard',maximum_distance=1,reason='GM allowance after caster movement')
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.e.release_telekinetic_load(self.a,reason='GM explicitly releases; no automatic landing inferred')
  self.assertNotIn('telekinetic_holder_id',self.e._physical_objects['remote1'])
 def test_lost_current_capability_blocks_remote_move_and_focus_check_before_cost_rng(self):
  self.objects([30]);self.lift();self.turn()
  G.revoke(self.a,'fixture:telekinetic',engine=self.e);before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'current Telekinetic'):
   self.e.move_telekinetic_objects(self.a,{'remote0':[(8,2),(8,3)]},action_cost='shift',maximum_distance=1,reason='GM allowance after capability loss')
  self.assertEqual(CODEC.dump_engine(self.e),before)
  with self.assertRaisesRegex(ValueError,'current Telekinetic'):self.e.carry_check(self.a,fixed=[4,3,3])
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.e.release_telekinetic_load(self.a,reason='GM explicitly releases after capability loss')
  self.assertEqual(LOAD.load(self.a)['band'],'normal')
 def test_current_focus_rank_replaces_physical_power_and_rejected_total_is_atomic(self):
  self.e.gm.set_skill(self.a,'집중',2,reason='current Focus rank observed')
  self.objects([14,14]);before=CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):self.lift(['remote0','remote1'])
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.e.gm.set_skill(self.a,'집중',3,reason='current Focus rank now three')
  self.assertEqual(self.lift(['remote0','remote1'])['weight_kg'],28)
  self.turn();self.assertTrue(self.e.carry_check(self.a,fixed=[4,3,3]).passed)
 def test_unknown_cross_map_and_vertical_target_geometry_are_rejected_before_cost(self):
  self.objects([1])
  for location in ({'kind':'unknown'},{'kind':'grid','cell':(8,2),'map_id':'other-map'}):
   W.register_object(self.e,'remote0',location=location,weight_kg=1,reason='GM records actual target location')
   before=CODEC.dump_engine(self.e)
   with self.assertRaisesRegex(ValueError,'same-map'):self.lift()
   self.assertEqual(CODEC.dump_engine(self.e),before)
  W.register_object(self.e,'remote0',location={'kind':'grid','cell':(8,2)},weight_kg=1,reason='same mapped target')
  self.a.spec['_movement_altitude']=1;before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'vertical'):self.lift()
  self.assertEqual(CODEC.dump_engine(self.e),before)
if __name__=='__main__':unittest.main()
