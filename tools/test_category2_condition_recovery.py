"""Shared Slowed/Stuck state through actual movement, recall and recovery."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as FIX
from builder import build_pokemon
from grid import Grid,cheb
import condition_recovery as R,common_checks as C,world_entities as W,frequency as F,state_fields as FIELDS
import effects_ext as EXT,turn as TURN

class ConditionRecoveryTests(unittest.TestCase):
 setUpClass=classmethod(FIX.ProgressionStateTests.setUpClass.__func__)
 add=FIX.ProgressionStateTests.add
 restored=FIX.ProgressionStateTests.restored
 def setUp(self):
  FIX.ProgressionStateTests.setUp(self)
  self.p=self.add(build_pokemon(self.r,'이브이',20,moves=[],abilities=[]))
  self.actors=[self.a,self.p];self.e.grid=Grid(30,10)
  self.target=self.add(build_pokemon(self.r,'잉어킹',10,moves=[],abilities=[]));self.target.pos=(20,1)
  for actor in self.actors:
   self.e.gm.set_movement_capabilities(actor,{'land':7,'sky':6,'levitate':5,'swim':4,'burrow':3,'teleport':2},basis='current',reason='observed current capabilities')
 def apply(self,actor,*conditions):
  for condition in conditions:self.e.gm.add_condition(actor,condition,force=False,reason='actual observed affliction')
 def snap(self):
  return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(x) for x in self.e.gm.everyone]),{id(self.r):self.r})
 def recover(self,actor,condition='둔화',**kw):
  return self.e.recover_condition(actor,condition,duration_minutes=kw.pop('duration_minutes',2),reason=kw.pop('reason','GM actual recovery interval'),**kw)
 def test_slowed_halves_all_existing_modes_after_stages_minimum_one_for_both_kinds(self):
  values={'land':7,'sky':6,'levitate':5,'swim':4,'burrow':3,'teleport':2}
  for actor in self.actors:
   self.apply(actor,'둔화')
   for stage in (0,-6,6):
    self.e.gm.set_stage(actor,'spe',value=stage)
    for mode,value in values.items():
     adjusted=max(min(value,2),value+stage//2) if stage<0 else value+stage//2
     self.assertEqual(self.e.move_profile(actor,movement_mode=mode)[0],max(1,adjusted//2))
   self.e.gm.set_stage(actor,'spe',value=0)
   self.e.gm.set_movement_capabilities(actor,{'land':1,'sky':0},basis='current',reason='actual absent sky and minimum land')
   self.assertEqual(self.e.move_profile(actor),(1,'육상'))
   with self.assertRaises(ValueError):self.e.move_profile(actor,movement_mode='sky')
 def test_actual_shift_uses_slowed_distance_and_spends_one_shift(self):
  self.e.start_round(self.actors)
  for actor in self.actors:
   actor.pos=(1,1);self.apply(actor,'둔화');self.e.start_of_turn(actor)
   self.e.approach(actor,self.target,movement_mode='land')
   self.assertEqual(cheb((1,1),actor.pos),3);self.assertEqual(actor.budget['shift'],0)
   self.e.end_of_turn(actor);actor.pos=(0,8)
 def test_stuck_blocks_actual_land_and_teleport_without_cost_but_not_stationary_shift(self):
  self.e.start_round(self.actors)
  for actor in self.actors:
   actor.pos=(1,1);self.apply(actor,'구속');self.e.start_of_turn(actor);before=self.snap()
   self.e.approach(actor,self.target,movement_mode='land');self.assertEqual(self.snap(),before)
   self.e.teleport(actor,(2,1),surface_contact=True,reason_text='actual visible grounded destination');self.assertEqual(self.snap(),before)
   self.assertTrue(TURN.spend(self.e,actor,'shift','stationary Shift effect component',movement=False))
   self.e.end_of_turn(actor);actor.pos=(0,8)
 def test_stuck_disables_only_speed_evasion_at_actual_accuracy_check(self):
  move=self.r.move('move/메가톤펀치')
  # Distinct target cells keep the other fixture actor out of the attack path.
  # Occupied intervening/target cells independently impose rough-terrain -2.
  self.a.pos=(1,1);self.p.pos=(1,3)
  for actor in self.actors:
   FIELDS.base_patch(actor,{'stats':{'hp':10,'atk':10,'def':10,'spa':10,'spd':15,'spe':30}},reason='observed actual evasion stats')
   self.assertEqual([actor.evasion(k) for k in ('물리','특수','변화')],[6,6,6]);self.apply(actor,'구속')
   self.assertEqual([actor.evasion(k) for k in ('물리','특수','변화')],[2,3,0])
   import map_terrain as TERRAIN
   self.assertEqual(TERRAIN.accuracy_penalty(self.e,self.target,actor),0)
   self.assertFalse(self.e.accuracy_check(self.target,actor,move,fixed_roll=move['ac']+1)[0])
   self.assertTrue(self.e.accuracy_check(self.target,actor,move,fixed_roll=move['ac']+2)[0])
 def test_ghost_type_immunity_reads_actual_types_for_both_kinds(self):
  for actor in self.actors:
   self.e.gm.set_types(actor,['고스트'],reason='actual Ghost type')
   self.assertFalse(self.e.apply_status(actor,'구속'));self.assertNotIn('구속',actor.conditions)
   self.e.gm.set_types(actor,['노말'],reason='actual type replaced');self.assertTrue(self.e.apply_status(actor,'구속'))
 def test_recall_cures_both_other_conditions_but_preserves_persistent_afflictions(self):
  for actor in self.actors:
   self.apply(actor,'둔화','구속','독');self.e.gm.recall(actor,reason='actual recall')
   self.assertFalse({'둔화','구속'}&actor.conditions);self.assertIn('독',actor.conditions);self.assertFalse(actor.on_field)
   self.e.gm.send_out(actor);self.assertEqual(self.e.move_profile(actor,movement_mode='land')[0],7)
 def test_switch_effect_uses_shared_recovery_and_blocked_trapped_switch_cures_nothing(self):
  self.apply(self.p,'둔화','구속','수렁');before=self.snap()
  self.assertIsNotNone(EXT.h_switch_out(self.e,self.p,self.target,{},{}));self.assertEqual(self.snap(),before)
  self.e.cure_status(self.p,'수렁');EXT.h_switch_out(self.e,self.p,self.target,{},{});self.assertFalse({'둔화','구속'}&self.p.conditions)
 def test_scene_end_records_opportunity_without_automatic_cure_and_extended_works(self):
  for actor in self.actors:self.apply(actor,'둔화','구속')
  self.e.begin_encounter(self.actors);self.e.end_encounter()
  self.assertIsInstance(self.recover(self.p),C.PendingDecision)
  self.e.end_scene()
  for actor in self.actors:
   self.assertTrue({'둔화','구속'}<=actor.conditions)
   for condition in ('둔화','구속'):
    when=self.e.elapsed_seconds;receipt=self.recover(actor,condition)
    self.assertEqual(self.e.elapsed_seconds-when,120);self.assertEqual(receipt['source'],'condition/'+condition)
    self.assertNotIn(condition,actor.conditions);self.assertEqual(actor._action_history[-1],'extended')
   self.assertNotIn(R.KEY,actor.custom_conditions)
  self.assertTrue(self.e.validate_state()['valid'])
 def test_missing_duration_active_encounter_and_newly_applied_condition_do_not_clear(self):
  self.apply(self.p,'둔화');self.e.end_scene();before=self.snap()
  self.assertIsInstance(self.e.recover_condition(self.p,'둔화'),C.PendingDecision);self.assertEqual(self.snap(),before)
  for bad in (0,-1,True,1.5):
   with self.assertRaises(ValueError):self.recover(self.p,duration_minutes=bad)
   self.assertEqual(self.snap(),before)
  self.e.begin_encounter([self.p]);before=self.snap();self.assertIsInstance(self.recover(self.p),C.PendingDecision);self.assertEqual(self.snap(),before)
  self.e.end_encounter();self.assertIsInstance(self.recover(self.p),C.PendingDecision)
  self.e.end_scene();self.e.cure_status(self.p,'둔화');self.apply(self.p,'둔화');before=self.snap()
  self.assertIsInstance(self.recover(self.p),C.PendingDecision);self.assertEqual(self.snap(),before)
 def test_uncured_other_statuses_and_action_incapacity_remain_explicit(self):
  self.apply(self.p,'둔화','얼음');self.e.end_scene();before=self.snap()
  self.assertIs(self.recover(self.p),False);self.assertEqual(self.snap(),before)
  self.assertIsInstance(self.recover(self.p,'얼음'),C.PendingDecision)
  self.assertEqual(self.snap(),before)
 def test_failure_after_time_advance_rolls_back_clock_action_and_condition(self):
  from engine import Engine
  self.apply(self.p,'둔화');self.e.end_scene();before=self.snap()
  with patch.object(Engine,'cure_status',side_effect=ValueError('injected post-interval failure')):
   with self.assertRaises(ValueError):self.recover(self.p)
  self.assertEqual(self.snap(),before)
 def test_gm_and_durable_restore_keep_affliction_opportunity_and_cure_receipt(self):
  self.apply(self.p,'둔화','구속');self.e.end_scene();snapshot=self.e.gm.snapshot('eligible')
  saved=deepcopy(self.p.custom_conditions[R.KEY]);self.recover(self.p);self.e.gm.restore(snapshot)
  self.assertEqual(self.p.custom_conditions[R.KEY],saved);self.assertIn('둔화',self.p.conditions)
  loaded=self.restored();p=W.actor_index(loaded)[self.p.entity_id]
  self.assertEqual(p.custom_conditions[R.KEY],saved)
  loaded.recover_condition(p,'둔화',duration_minutes=2,reason='GM actual recovery interval')
  self.assertNotIn('둔화',p.conditions);self.assertIn('구속',p.conditions)
  from engine import Engine
  again=Engine.import_state(self.r,loaded.export_state());p2=W.actor_index(again)[p.entity_id]
  self.assertEqual(p2.spec[R.RECEIPTS],p.spec[R.RECEIPTS]);self.assertNotIn('둔화',p2.conditions)
  before=again.elapsed_seconds
  with self.assertRaises(ValueError):again.recover_condition(p2,'둔화',duration_minutes=2,reason='cannot consume recovery twice')
  self.assertEqual(again.elapsed_seconds,before)
 def test_actual_shift_and_recall_after_both_restore_paths(self):
  self.apply(self.p,'둔화','구속');self.e.start_round(self.actors);self.e.start_of_turn(self.p);snapshot=self.e.gm.snapshot()
  loaded=self.restored();p=W.actor_index(loaded)[self.p.entity_id];target=W.actor_index(loaded)[self.target.entity_id];before=(p.pos,deepcopy(p.budget))
  loaded.approach(p,target,movement_mode='land');self.assertEqual((p.pos,p.budget),before)
  loaded.gm.recall(p);self.assertFalse({'둔화','구속'}&p.conditions)
  self.e.gm.recall(self.p);self.e.gm.restore(snapshot);self.assertTrue({'둔화','구속'}<=self.p.conditions)
  self.e.gm.recall(self.p);self.assertFalse({'둔화','구속'}&self.p.conditions)
 def test_explicit_gm_removal_clears_recovery_opportunity_and_reapplication_needs_new_boundary(self):
  for condition in ('둔화','구속'):
   self.apply(self.a,condition);self.e.end_scene();self.e.gm.remove_condition(self.a,'전부',reason='explicit GM state correction')
   self.assertNotIn(R.KEY,self.a.custom_conditions);self.assertTrue(self.e.validate_state()['valid'])
   self.e.gm.add_condition(self.a,condition,reason='new GM state observation')
   self.assertIsInstance(self.recover(self.a,condition),C.PendingDecision)
   self.e.end_scene();self.e.gm.remove_condition(self.a,condition,reason='explicit individual correction')
   self.assertNotIn(R.KEY,self.a.custom_conditions);self.assertTrue(self.e.validate_state()['valid'])
 def test_recovery_state_rejects_false_scene_and_invalid_receipt_on_export(self):
  self.apply(self.p,'둔화');self.e.end_scene();self.p.custom_conditions[R.KEY]['둔화']['scene']=True
  with self.assertRaises(ValueError):self.e.export_state()
  self.p.custom_conditions[R.KEY]['둔화']['scene']=F.state(self.p)['scene'];self.recover(self.p)
  self.p.spec[R.RECEIPTS][-1]['end']+=1
  with self.assertRaises(ValueError):self.e.export_state()

if __name__=='__main__':unittest.main()
