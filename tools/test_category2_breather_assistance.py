"""Actual assisted Full costs, native Command, shared recovery and owner deadlines."""
from pathlib import Path
from copy import deepcopy
import unittest
from unittest.mock import patch
from engine import Rules,Engine,Combatant
from grid import Grid
import action_resources as RESOURCES,breather as B,breather_assistance as ASSIST
import combat_timing as TIMING,common_checks as C,initiative_interrupts as INTERRUPTS
import movement_actions as MOVEMENT,stamina as STAMINA,state_codec as CODEC,state_grants as G
import temporary_hp as TEMP,turn as TURN

ROOT=Path(__file__).resolve().parents[1]

class AssistedBreatherTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=17);self.e.grid=Grid(12,8)
  def actor(uid,kind='trainer'):
   return Combatant(self.r,{'id':uid,'name':uid,'kind':kind,'level':20,'size':'medium',
    'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),30),'movement':{'land':4},
    'skills':{'육상':5,'전투':5,'명령':3},'moves':['struggle'],'edges':[],'abilities':[],'types':[]})
  self.h,self.t=actor('trainer/helper'),actor('trainer/target')
  self.h.side=self.t.side='party';self.h.pos=(2,2);self.t.pos=(3,2)
  self.e.everyone=self.e.gm.everyone=[self.h,self.t]
  self.e.start_round([self.h,self.t]);self.e.start_of_turn(self.h)
  self.e.apply_status(self.t,'난동')
 def options(self,**changes):
  result={'request_id':'assisted:one','helper':self.h,'path':[(3,2),(4,2),(5,2),(6,2),(7,2)],
   'retreat_reason':'GM observes these actual ordered routes retreat maximally away from the encounter enemies',
   'assistance':{'reason':'Actual target is Enraged and needs this Trainer to assist',
    'approach_path':[(2,2)],'helper_path':[(2,2),(3,2),(4,2),(5,2),(6,2)],
    'retreat_order':['target','helper'],'retreat_order_reason':'GM selects the target to clear the first cell before the helper follows',
    'target_payment':'next','payment_reason':'GM applies this actual target Full against its next owner-turn budget',
    'command_options':{'fixed':[6,6,6]}}}
  result.update(changes);return result
 def take(self,**changes):return self.e.take_breather(self.t,**self.options(**changes))
 def own(self,actor):G.transition(self.e,actor,lambda e,c:c.spec['edges'].append(STAMINA.SOURCE))
 def test_success_pays_both_native_fulls_target_recovers_helper_does_not(self):
  self.own(self.t);self.own(self.h);TEMP.grant(self.e,self.t,12);TEMP.grant(self.e,self.h,9)
  self.e.change_stage(self.t,'atk',2);self.e.change_stage(self.h,'atk',2);self.e.apply_status(self.h,'독')
  observed=[];old=STAMINA.observe
  def fact(e,a,event,**kw):
   if event=='take_a_breather':observed.append((a.entity_id,a.temp_hp,set(a.conditions),dict(a.stages)))
   return old(e,a,event,**kw)
  with patch.object(STAMINA,'observe',side_effect=fact),patch.object(INTERRUPTS,'begin',wraps=INTERRUPTS.begin) as begin:
   result=self.take()
  self.assertTrue(result['completed']);self.assertEqual(begin.call_count,1)
  self.assertEqual((self.h.pos,self.t.pos),((6,2),(7,2)))
  self.assertEqual(self.h.budget,{'standard':0,'shift':0,'swift':1})
  self.assertEqual(RESOURCES.pending(self.t),{'standard':1,'shift':1})
  self.assertEqual((self.t.temp_hp,self.h.temp_hp),(5,9));self.assertEqual((self.t.stages['atk'],self.h.stages['atk']),(0,2))
  self.assertNotIn('난동',self.t.conditions);self.assertIn('독',self.h.conditions);self.assertNotIn('취약',self.h.conditions)
  self.assertEqual(observed,[(self.t.entity_id,0,{'넘어짐','취약'},dict.fromkeys(self.t.stages,0))])
  self.assertIs(self.e._active_turn_actor,self.h);self.assertIsNone(INTERRUPTS.frame(self.e))
  self.assertEqual(self.t.custom_conditions.get('combat_turn_serial',0),0)
  self.assertFalse(self.e._action_grants)
 def test_failed_command_has_no_movement_cure_stage_temp_or_stamina_effect(self):
  self.own(self.t);TEMP.grant(self.e,self.t,9);self.e.change_stage(self.t,'def',2)
  options=self.options();options['assistance']['command_options']['fixed']=[1,1,1]
  with patch.object(MOVEMENT,'follow_paid_path',wraps=MOVEMENT.follow_paid_path) as follow:
   result=self.e.take_breather(self.t,**options)
  self.assertFalse(result['completed']);self.assertEqual(result['command'],{'passed':False,'total':3,'dc':12})
  self.assertEqual(follow.call_count,0);self.assertEqual((self.h.pos,self.t.pos),((2,2),(3,2)))
  self.assertEqual((self.t.temp_hp,self.t.stages['def']),(9,2));self.assertIn('난동',self.t.conditions)
  self.assertNotIn('넘어짐',self.h.conditions);self.assertNotIn('넘어짐',self.t.conditions)
  self.assertEqual((self.h.budget['standard'],self.h.budget['shift']),(0,0))
  self.assertEqual(RESOURCES.pending(self.t),{'standard':1,'shift':1})
 def test_source_qualified_request_replay_does_not_roll_move_or_charge_again(self):
  options=self.options();first=self.e.take_breather(self.t,**options);rng=self.e.rng.getstate()
  with patch.object(self.e,'skill_check',side_effect=AssertionError('must not reroll')):
   self.assertEqual(self.e.take_breather(self.t,**options),first)
  self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(RESOURCES.pending(self.t),{'standard':1,'shift':1})
  changed=self.options();changed['assistance']['command_options']['fixed']=[5,5,5]
  with self.assertRaisesRegex(ValueError,'cannot change'):self.e.take_breather(self.t,**changed)
 def test_confused_target_can_decline_voluntary_save_for_actual_command(self):
  self.e.cure_status(self.t,'난동');self.e.apply_status(self.t,'혼란')
  self.assertTrue(self.take()['completed']);self.assertNotIn('혼란',self.t.conditions)
 def test_helper_stands_but_evasion_zero_remains_until_actual_next_owner_end(self):
  baseline=self.h.evasion('물리');self.assertGreater(baseline,0)
  self.take();self.assertEqual(self.h.evasion('물리'),0)
  self.e.end_of_turn(self.h);self.assertTrue(TIMING.evasion_zero(self.h))
  self.e.start_of_turn(self.t);self.assertEqual(self.t.budget,{'standard':0,'shift':0,'swift':1})
  self.e.end_of_turn(self.t);self.e.start_round([self.h,self.t]);self.e.start_of_turn(self.h)
  self.assertTrue(self.e.stand_up(self.h));self.assertNotIn('넘어짐',self.h.conditions)
  self.assertEqual(self.h.evasion('물리'),0);self.e.end_of_turn(self.h)
  self.assertFalse(TIMING.evasion_zero(self.h));self.assertEqual(self.h.evasion('물리'),baseline)
 def test_invalid_routes_and_unknown_policy_are_held_before_cost_or_rng(self):
  before=(deepcopy(self.h.budget),self.e.rng.getstate(),self.h.pos,self.t.pos)
  options=self.options();options['assistance']['helper_path']=[(2,2),(3,2)]
  options['assistance']['retreat_order']=['helper','target']
  with self.assertRaisesRegex(ValueError,'other participant body'):self.e.take_breather(self.t,**options)
  self.assertEqual(before,(self.h.budget,self.e.rng.getstate(),self.h.pos,self.t.pos))
  options=self.options();options['assistance']['target_payment']=None
  with self.assertRaisesRegex(ValueError,'current/next'):self.e.take_breather(self.t,**options)
  self.assertFalse(hasattr(self.e,B.FIELD));self.assertEqual(RESOURCES.pending(self.t),{})
 def test_current_payment_deducts_actual_prior_budget_without_new_turn_clock(self):
  self.e.end_of_turn(self.h);self.e.start_of_turn(self.t);self.e.end_of_turn(self.t)
  self.e.start_round([self.h,self.t]);self.e.start_of_turn(self.t);self.e.end_of_turn(self.t);self.e.start_of_turn(self.h)
  self.e.apply_status(self.t,'난동')
  serial=self.t.custom_conditions['combat_turn_serial'];options=self.options();options['assistance']['target_payment']='current'
  self.assertTrue(self.e.take_breather(self.t,**options)['completed'])
  self.assertEqual(self.t.budget,{'standard':0,'shift':0,'swift':1});self.assertEqual(RESOURCES.pending(self.t),{})
  self.assertEqual(self.t.custom_conditions['combat_turn_serial'],serial)
 def test_target_permission_failure_rolls_back_both_participant_costs(self):
  options=self.options();before=(deepcopy(self.h.budget),self.e.rng.getstate())
  original=TURN.spend
  def blocked(e,c,kind,*args,**kwargs):
   if c.entity_id==self.t.entity_id and kwargs.get('_assisted_breather') is not None:return False
   return original(e,c,kind,*args,**kwargs)
  with patch.object(TURN,'spend',side_effect=blocked),self.assertRaisesRegex(ValueError,'target cannot pay'):
   self.e.take_breather(self.t,**options)
  self.assertEqual(before,(self.h.budget,self.e.rng.getstate()));self.assertEqual(RESOURCES.pending(self.t),{})
  self.assertFalse(hasattr(self.e,B.FIELD));self.assertIs(self.e._active_turn_actor,self.h)
 def test_forged_assisted_authority_does_not_bypass_ordinary_rage_or_cost(self):
  before=deepcopy(self.h.budget)
  with self.assertRaisesRegex(ValueError,'actual issued'):TURN.spend(self.e,self.h,'full',_assisted_breather=object())
  self.assertEqual(self.h.budget,before)
 def test_completed_codec_restore_preserves_helper_flag_debt_and_replay(self):
  options=self.options();self.e.take_breather(self.t,**options)
  restored=CODEC.load_engine(self.r,CODEC.dump_engine(self.e));index={c.entity_id:c for c in restored.everyone}
  helper,target=index[self.h.entity_id],index[self.t.entity_id]
  self.assertEqual(helper.evasion('물리'),0);self.assertTrue(TIMING.evasion_zero(helper))
  self.assertEqual(RESOURCES.pending(target),{'standard':1,'shift':1})
  again=deepcopy(options);again['helper']=helper
  self.assertTrue(restored.take_breather(target,**again)['completed'])
 def test_helper_can_actually_approach_then_use_the_lower_shared_movement(self):
  self.h.pos=(0,2);G.transition(self.e,self.h,lambda e,c:setattr(c,'movement',6))
  options=self.options();options['assistance']['approach_path']=[(0,2),(1,2),(2,2)]
  result=self.e.take_breather(self.t,**options)
  self.assertTrue(result['completed']);self.assertEqual(result['movement']['approach']['distance'],2)
  self.assertEqual(result['movement']['helper']['distance'],4);self.assertEqual(result['movement']['target']['distance'],4)
  self.assertEqual((self.h.pos,self.t.pos),((6,2),(7,2)))
 def test_shared_maximum_is_lower_participant_allowance_before_cost(self):
  G.transition(self.e,self.t,lambda e,c:setattr(c,'movement',3))
  before=deepcopy(self.h.budget)
  with self.assertRaisesRegex(ValueError,'movement allowance'):self.take()
  self.assertEqual(self.h.budget,before);self.assertEqual(RESOURCES.pending(self.t),{})
 def test_current_payment_cannot_reuse_a_previous_round_budget(self):
  self.e.end_of_turn(self.h);self.e.start_of_turn(self.t);self.e.end_of_turn(self.t)
  self.e.start_round([self.h,self.t]);self.e.start_of_turn(self.h);self.e.apply_status(self.t,'난동')
  self.assertEqual(self.t.budget['standard'],1)
  before=deepcopy(self.h.budget);options=self.options();options['assistance']['target_payment']='current'
  with self.assertRaisesRegex(ValueError,'current-round prior budget'):self.e.take_breather(self.t,**options)
  self.assertEqual(self.h.budget,before);self.assertEqual(RESOURCES.pending(self.t),{})
 def test_native_curse_origin_does_not_rewrite_request_or_break_replay(self):
  self.e.apply_status(self.t,'저주',applied_by=self.h)
  options=self.options();result=self.e.take_breather(self.t,**options)
  self.assertTrue(result['completed']);self.assertIn('저주',self.t.conditions)
  self.assertIs(self.t.custom_conditions['curse_origin'],self.h)
  self.assertEqual(self.e.take_breather(self.t,**options),result)
 def test_late_departure_obstacle_stops_before_cell_and_keeps_assisted_attempt_unresolved(self):
  original=MOVEMENT.departure
  def changed(e,c,destination,altitude,**kwargs):
   allowed=original(e,c,destination,altitude,**kwargs)
   if c is self.t:e.grid.blocking.add(destination)
   return allowed
  with patch.object(MOVEMENT,'departure',side_effect=changed),self.assertRaisesRegex(ValueError,'path interrupted'):
   self.take()
  self.assertEqual(self.t.pos,(3,2));self.assertIn('난동',self.t.conditions)
  self.assertEqual(getattr(self.e,B.FIELD)['assisted:one']['observed_resolution']['state'],'pending')
 def test_late_departure_obstacle_cannot_complete_ordinary_breather_or_award_stamina(self):
  self.own(self.h);TEMP.grant(self.e,self.h,9);original=MOVEMENT.departure
  def changed(e,c,destination,altitude,**kwargs):
   allowed=original(e,c,destination,altitude,**kwargs);e.grid.blocking.add(destination);return allowed
  with patch.object(MOVEMENT,'departure',side_effect=changed),self.assertRaisesRegex(ValueError,'path interrupted'):
   self.e.take_breather(self.h,request_id='ordinary:changed',path=[(2,2),(2,3),(2,4),(2,5),(2,6)],
    retreat_reason='GM observes maximal actual vertical retreat before the late world change',
    save_dc=16,save_reason='Explicit table DC16 and Full on failed saving check',save_cost='full',fixed_save=20)
  self.assertEqual(self.h.pos,(2,2));self.assertEqual(self.h.temp_hp,9)
  self.assertNotIn('넘어짐',self.h.conditions)
 def test_native_command_prefix_continues_without_repeating_cost_or_observed_command(self):
  original=MOVEMENT.follow_paid_path
  def late(e,c,path,**kwargs):
   result=original(e,c,path,**kwargs)
   if c is self.t:raise RuntimeError('late actual target route hook')
   return result
  options=self.options()
  with patch.object(MOVEMENT,'follow_paid_path',side_effect=late),self.assertRaisesRegex(RuntimeError,'actual target'):
   self.e.take_breather(self.t,**options)
  row=getattr(self.e,B.FIELD)[options['request_id']]['observed_resolution']
  self.assertEqual(row['observation']['command']['total'],18);self.assertEqual(row['state'],'pending')
  self.assertEqual((self.h.budget['standard'],self.h.budget['shift']),(0,0))
  with self.assertRaisesRegex(ValueError,'unfinished actual'):self.e.end_of_turn(self.h)
  with patch.object(self.e,'skill_check',side_effect=AssertionError('cannot reroll actual Command')):
   result=self.e.take_breather(self.t,**options)
  self.assertTrue(result['completed']);self.assertEqual((self.h.pos,self.t.pos),((6,2),(7,2)))
  self.assertEqual(RESOURCES.pending(self.t),{'standard':1,'shift':1})
  self.assertEqual((self.h.budget['standard'],self.h.budget['shift']),(0,0))

if __name__=='__main__':unittest.main()
