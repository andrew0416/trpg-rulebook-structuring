"""Assisted actual movement modes reuse native plans, budgets and continuations."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,unittest
from engine import Rules,Engine,Combatant
import test_category2_breather_assistance as BASE
import action_resources as RESOURCES,breather as B,common_checks as C
import effects_ext as EXT,movement_actions as M,state_codec as CODEC
import state_grants as G,temporary_hp as TEMP

ROOT=Path(__file__).resolve().parents[1]

class JointMovementTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 setUp=BASE.AssistedBreatherTests.setUp
 options=BASE.AssistedBreatherTests.options
 own=BASE.AssistedBreatherTests.own
 def caps(self,actor,land=4,**values):
  self.e.gm.set_movement_capabilities(actor,dict(land=land,**values),basis='current',reason='actual observed participant movement values')
 def air(self,start,end,altitude):
  return [{'position':(x,2),'altitude':altitude} for x in range(start,end+1)]
 def prepare(self):
  self.own(self.t);TEMP.grant(self.e,self.t,12);TEMP.grant(self.e,self.h,9)
 def flying(self):
  self.prepare();self.caps(self.h,sky=8);self.caps(self.t,levitate=6)
  G.transition(self.e,self.t,lambda e,c:c.spec.__setitem__('_movement_altitude',2))
  options=self.options(path=self.air(3,9,2))
  options['assistance'].update(approach_path=[{'position':(2,2),'altitude':h} for h in (0,1,2)],
      helper_path=self.air(2,8,2),movement={'approach':{'mode':'sky'},'helper':{'mode':'sky'},'target':{'mode':'levitate'}})
  return options
 def test_swimming_shared_lower_allowance_keeps_two_fulls_and_target_only_recovery(self):
  self.prepare();self.caps(self.t,swim=6);self.caps(self.h,swim=8)
  options=self.options(path=[(x,2) for x in range(3,10)])
  options['assistance'].update(helper_path=[(x,2) for x in range(2,9)],movement={'target':{'mode':'swim'},'helper':{'mode':'swim'}})
  result=self.e.take_breather(self.t,**options)
  self.assertTrue(result['completed']);self.assertEqual((self.t.pos,self.h.pos),((9,2),(8,2)))
  self.assertEqual([result['movement'][name]['distance'] for name in ('target','helper')],[6,6])
  self.assertEqual((self.t.temp_hp,self.h.temp_hp),(5,9));self.assertEqual(RESOURCES.pending(self.t),{'standard':1,'shift':1})
  self.assertEqual((self.h._action_history.count('full'),self.t._action_history.count('full')),(1,1))
 def test_aerial_approach_changes_actual_height_before_each_different_flying_retreat(self):
  options=self.flying()
  with patch.object(EXT,'on_enter_cell',side_effect=AssertionError('airborne path is not surface entry')):
   result=self.e.take_breather(self.t,**options)
  self.assertTrue(result['completed']);self.assertEqual((self.t.pos,self.h.pos),((9,2),(8,2)))
  self.assertEqual((self.t.spec['_movement_altitude'],self.h.spec['_movement_altitude']),(2,2))
  self.assertEqual([result['movement'][name]['distance'] for name in ('approach','target','helper')],[2,6,6])
  self.assertEqual((self.t.temp_hp,self.h.temp_hp),(5,9))
 def test_pokemon_teleport_and_trainer_walking_share_actual_lower_limit(self):
  spec=deepcopy(self.t.spec);spec.update(id='pokemon/target',name='pokemon target',kind='pokemon')
  self.t=Combatant(self.r,spec);self.t.pos=(3,2);self.t.side='party'
  self.e=Engine(self.r,seed=17);self.e.grid=BASE.Grid(12,8);self.e.everyone=self.e.gm.everyone=[self.h,self.t]
  self.e.start_round([self.h,self.t]);self.e.start_of_turn(self.h);self.e.apply_status(self.t,'난동');TEMP.grant(self.e,self.t,12)
  self.caps(self.t,teleport=6);self.caps(self.h,land=8)
  options=self.options(path=[(3,2),(9,2)])
  options['assistance'].update(helper_path=[(x,2) for x in range(2,9)],movement={'target':{'mode':'teleport','options':{'surface_contact':True}}})
  with patch.object(M,'follow_paid_transfer',wraps=M.follow_paid_transfer) as transfer:
   result=self.e.take_breather(self.t,**options)
  self.assertTrue(result['completed']);self.assertEqual((transfer.call_count,self.t.pos,self.h.pos),(1,(9,2),(8,2)))
  self.assertEqual(self.t.spec['_teleport']['used_round'],self.e.round_no);self.assertEqual(self.t.temp_hp,0)
 def test_other_participant_same_plane_collision_rejects_but_burrow_plane_does_not_block_surface(self):
  self.prepare();self.caps(self.t,burrow=6);self.caps(self.h,land=8)
  options=self.options(path=[(x,2) for x in range(3,9)])
  options['assistance'].update(helper_path=[(x,2) for x in range(2,9)],movement={'target':{'mode':'burrow','options':{'diggable':True,'surface':True}}})
  before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'other participant body'):self.e.take_breather(self.t,**options)
  self.assertEqual(CODEC.dump_engine(self.e),before)
  options['assistance']['movement']['target']['options']['surface']=False
  result=self.e.take_breather(self.t,**options)
  self.assertTrue(result['completed']);self.assertEqual((self.t.pos,self.h.pos),((8,2),(8,2)))
  self.assertTrue(self.t.spec['_burrow']['underground']);self.assertFalse(self.h.spec.get('_burrow',{}).get('underground',False))
  self.assertEqual((self.t.temp_hp,self.h.temp_hp),(5,9))
 def test_borrowed_full_payment_keeps_actual_underground_upkeep_provenance(self):
  self.prepare();self.caps(self.t,burrow=6);self.caps(self.h,land=8)
  options=self.options(path=[(x,2) for x in range(3,9)])
  options['assistance'].update(helper_path=[(x,2) for x in range(2,9)],movement={'target':{'mode':'burrow','options':{'diggable':True,'surface':False}}})
  self.assertTrue(self.e.take_breather(self.t,**options)['completed'])
  self.e=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  self.h,self.t=[next(c for c in self.e.everyone if c.entity_id==old.entity_id) for old in (self.h,self.t)]
  self.e.end_of_turn(self.h);self.e.start_of_turn(self.t)
  self.assertEqual((self.t.budget['standard'],self.t.budget['shift']),(0,0))
  self.assertFalse(self.t.took_standard);self.assertEqual(self.t._action_history,[])
  self.e=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  self.t=next(c for c in self.e.everyone if c.entity_id==self.t.entity_id)
  self.e.end_of_turn(self.t)
  self.assertTrue(self.t.spec['_burrow']['standard_debt'])
  self.assertEqual(RESOURCES.pending(self.t),{'standard':1})
 def test_unsourced_standard_loss_cannot_pose_as_an_actual_paid_full(self):
  self.own(self.t)
  G.transition(self.e,self.t,lambda e,c:c.spec.update(_burrow={'underground':True}))
  RESOURCES.schedule(self.t,{'standard':1,'shift':1})
  self.e.end_of_turn(self.h);self.e.start_of_turn(self.t)
  with self.assertRaisesRegex(ValueError,'unknown Standard loss conjunction'):self.e.end_of_turn(self.t)
 def test_cross_altitude_contact_needs_actual_measurement_and_surface_can_pass_below_flyer(self):
  self.prepare();self.caps(self.t,sky=6);self.caps(self.h,land=8)
  G.transition(self.e,self.t,lambda e,c:c.spec.__setitem__('_movement_altitude',1))
  options=self.options(path=self.air(3,8,1))
  options['assistance'].update(helper_path=[(x,2) for x in range(2,9)],movement={'target':{'mode':'sky'}})
  before=CODEC.dump_engine(self.e)
  self.assertIsInstance(self.e.take_breather(self.t,**options),C.PendingDecision)
  self.assertEqual(CODEC.dump_engine(self.e),before)
  options['assistance'].update(reach_distance=0.5,reach_reason='actual three-dimensional contact')
  with self.assertRaisesRegex(ValueError,'shorter'):self.e.take_breather(self.t,**options)
  self.assertEqual(CODEC.dump_engine(self.e),before)
  options['assistance']['reach_distance']=1
  result=self.e.take_breather(self.t,**options)
  self.assertTrue(result['completed']);self.assertEqual((self.t.pos,self.h.pos),((8,2),(8,2)))
  self.assertEqual((self.t.spec['_movement_altitude'],self.h.spec.get('_movement_altitude',0)),(1,0))
 def test_saved_assisted_air_prefix_resumes_only_helper_without_command_or_other_legs(self):
  options=self.flying();departure=M.departure
  def obstruct(e,c,q,h,**kwargs):
   permitted=departure(e,c,q,h,**kwargs)
   if c.entity_id==self.h.entity_id and c.pos==(3,2):e.grid.blocking.add((4,2))
   return permitted
  with patch.object(M,'departure',side_effect=obstruct):
   with self.assertRaisesRegex(ValueError,'interrupted'):self.e.take_breather(self.t,**options)
  self.assertEqual((self.t.pos,self.h.pos,self.t.temp_hp),((9,2),(3,2),12))
  restored=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  target=next(c for c in restored.everyone if c.entity_id==self.t.entity_id)
  helper=next(c for c in restored.everyone if c.entity_id==self.h.entity_id);options['helper']=helper;restored.grid.blocking.remove((4,2))
  with patch.object(restored,'skill_check',side_effect=AssertionError('actual Command cannot repeat')):
   result=restored.take_breather(target,**options)
  self.assertTrue(result['completed']);self.assertEqual((target.pos,helper.pos,target.temp_hp),((9,2),(8,2),5))
  self.assertEqual([result['movement'][name]['distance'] for name in ('approach','target','helper')],[2,6,6])
  self.assertEqual((helper._action_history.count('full'),target._action_history.count('full')),(1,1))
 def test_actual_late_approach_cost_cannot_create_extra_helper_retreat(self):
  self.prepare();self.h.pos=(1,2);self.caps(self.h,land=7);self.caps(self.t,land=6)
  options=self.options(path=[(x,2) for x in range(3,10)])
  options['assistance'].update(approach_path=[(1,2),(2,2)],helper_path=[(x,2) for x in range(2,9)])
  departure=M.departure
  def terrain(e,c,q,h):
   permitted=departure(e,c,q,h)
   if c.entity_id==self.h.entity_id and c.pos==(1,2):e.grid.slow.add((2,2))
   return permitted
  with patch.object(M,'departure',side_effect=terrain):
   with self.assertRaisesRegex(ValueError,'interrupted'):self.e.take_breather(self.t,**options)
  observed=self.e._breather_attempts[options['request_id']]['observed_resolution']['observation']
  self.assertEqual((observed['movement']['approach']['distance'],observed['progress']['helper']['distance']),(2,5))
  self.assertEqual((self.t.pos,self.h.pos,self.t.temp_hp),((9,2),(7,2),12))
 def test_changed_command_world_cannot_replace_the_actual_observed_contact(self):
  self.prepare();options=self.options();check=self.e.skill_check
  def moved(*args,**kwargs):
   result=check(*args,**kwargs);self.t.pos=(9,4);return result
  with patch.object(self.e,'skill_check',side_effect=moved):
   with self.assertRaisesRegex(ValueError,'contact changed'):self.e.take_breather(self.t,**options)
  self.assertEqual((self.h.pos,self.t.pos,self.t.temp_hp),((2,2),(9,4),12))

if __name__=='__main__':unittest.main()
