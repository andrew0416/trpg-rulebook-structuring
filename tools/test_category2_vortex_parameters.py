"""Snap Trap extends the actual target Vortex instead of a world-wide save rule."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
from state_codec import dump_engine,load_engine
import effect_contracts as CONTRACTS

TRAP='move/집게덫';VORTEX='move/바다회오리'

class VortexParameterTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,708);self.e.grid=Grid(20,10)
  self.a=self.actor('source',(2,2),'party');self.t=self.actor('target',(3,2),'enemy');self.other=self.actor('ordinary target',(2,3),'enemy')
 def actor(self,name,pos,side):
  spec=build_trainer(self.r,name,30,{'hp':60,'atk':20,'def':20,'spa':20,'spd':20,'spe':20},extra={'moves':[TRAP,VORTEX],'pos':pos,'side':side,'size':'중형','abilities':[]})
  actor=Combatant(self.r,spec);self.e.gm.add_combatant(actor);return actor
 def begin(self):self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=30)
 def hit(self,mid=TRAP,target=None,roll=18):
  with patch.object(Engine, 'd20',return_value=roll):return self.e.use_move(self.a,target or self.t,mid,set_damage=True)
 def end_target(self,roll):
  self.e.start_of_turn(self.t,initiative_count=20)
  with patch.object(Engine, 'd20',return_value=roll):self.e.end_of_turn(self.t)
 def test_native_hit_cost_tick_slow_and_trap_end_with_the_same_vortex(self):
  self.begin();base=self.e.move_profile(self.t)[0];hp=self.t.hp
  self.assertGreater(self.hit(),0);self.assertLess(self.t.hp,hp)
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.move_uses[TRAP],1)
  self.assertTrue({'조이기','둔화','수렁'}<=self.t.conditions);self.assertLess(self.e.move_profile(self.t)[0],base)
  self.assertEqual(self.t.custom_conditions['vortex']['escape_dc_bonus'],3);self.assertEqual(self.e.condition_params,{})
  self.assertEqual(self.e.apply_effect(self.t,self.t,{'type':'switch_out'},None,True,0,'gm/trap-switch'),(0,1))
  self.e.end_of_turn(self.a);hp=self.t.hp;self.end_target(20)
  self.assertEqual(self.t.hp,hp-self.e.tick(self.t));self.assertIn('조이기',self.t.conditions)
  self.e.cure_status(self.t,'조이기');self.assertFalse({'조이기','둔화','수렁'}&self.t.conditions)
  self.assertNotIn('vortex',self.t.custom_conditions);self.assertEqual(self.e.move_profile(self.t)[0],base)
  self.assertEqual(self.e.apply_effect(self.t,self.t,{'type':'switch_out'},None,True,0,'gm/after-vortex-switch'),(1,0))
 def test_bonus_belongs_only_to_target_and_strict_progress_uses_23_17_11(self):
  self.begin();self.hit();self.e.end_of_turn(self.a)
  self.e.apply_status(self.other,'조이기');self.assertNotIn('escape_dc_bonus',self.other.custom_conditions['vortex'])
  self.end_target(20)
  self.e.start_round(self.e.everyone);self.end_target(17);self.assertEqual(self.t.custom_conditions['vortex']['ends'],2)
  self.e.start_of_turn(self.other,initiative_count=10)
  with patch.object(Engine, 'd20',return_value=20):self.e.end_of_turn(self.other)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.other,initiative_count=25)
  with patch.object(Engine, 'd20',return_value=15):self.e.end_of_turn(self.other)
  self.assertNotIn('조이기',self.other.conditions);self.assertIn('조이기',self.t.conditions)
  self.end_target(12);self.assertNotIn('조이기',self.t.conditions);self.assertEqual(self.e.condition_params,{})
 def test_fifth_turn_still_ends_without_an_escape_roll(self):
  self.begin();self.hit();self.e.end_of_turn(self.a)
  for roll in (20,17,11,5):
   self.end_target(roll);self.assertIn('조이기',self.t.conditions);self.e.start_round(self.e.everyone)
  self.e.start_of_turn(self.t,initiative_count=20)
  with patch.object(Engine, 'd20',side_effect=AssertionError('fifth-turn escape must not roll')):self.e.end_of_turn(self.t)
  self.assertFalse({'조이기','둔화','수렁'}&self.t.conditions)
 def test_duplicate_native_application_keeps_progress_and_does_not_stack_bonus(self):
  self.begin();self.hit();self.e.end_of_turn(self.a);self.end_target(20)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=30);self.hit()
  state=self.t.custom_conditions['vortex'];self.assertEqual((state['ends'],state['escape_dc_bonus']),(1,3))
  self.e.apply_status(self.t,'조이기');self.assertEqual((state['ends'],state['escape_dc_bonus']),(1,3))
  self.e.cure_status(self.t,'조이기');self.e.apply_status(self.t,'조이기')
  self.assertEqual(self.t.custom_conditions['vortex']['ends'],0);self.assertNotIn('escape_dc_bonus',self.t.custom_conditions['vortex'])
 def test_independent_reapplications_survive_and_bonus_ends_only_with_vortex(self):
  self.begin();self.hit();self.e.apply_status(self.t,'둔화');self.e.apply_status(self.t,'수렁')
  self.e.cure_status(self.t,'조이기');self.assertTrue({'둔화','수렁'}<=self.t.conditions)
  self.e.apply_status(self.t,'조이기',source=TRAP,parameters={'escape_dc_bonus':3},applied_by=self.a)
  self.assertEqual(self.t.custom_conditions['vortex']['escape_dc_bonus'],3)
  self.e.end_encounter(self.e.everyone)
  self.assertIn('조이기',self.t.conditions);self.assertEqual(self.t.custom_conditions['vortex']['escape_dc_bonus'],3)
  self.e.cure_status(self.t,'조이기');self.assertNotIn('vortex',self.t.custom_conditions)
  self.e.apply_status(self.t,'조이기');self.assertNotIn('escape_dc_bonus',self.t.custom_conditions['vortex'])
 def test_gm_and_json_restore_continue_the_actual_bonus_and_escape_progress(self):
  for restoration in ('gm','json'):
   with self.subTest(restoration=restoration):
    self.setUp();self.begin();self.hit();self.e.end_of_turn(self.a);self.end_target(20)
    if restoration=='gm':
     self.e.gm.snapshot('parameter-vortex');self.e.cure_status(self.t,'조이기');self.e.gm.restore('parameter-vortex')
    else:self.e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
    actors={c.name:c for c in self.e.everyone};self.a=actors['source'];self.t=actors['target'];self.other=actors['ordinary target']
    self.assertEqual((self.t.custom_conditions['vortex']['ends'],self.t.custom_conditions['vortex']['escape_dc_bonus']),(1,3))
    self.e.start_round(self.e.everyone);self.end_target(17);self.assertIn('조이기',self.t.conditions)
    self.e.start_round(self.e.everyone);self.end_target(12);self.assertFalse({'조이기','둔화','수렁'}&self.t.conditions)
    self.assertTrue(self.e.validate_state()['valid'])
 def test_miss_has_no_vortex_or_world_parameter_mutation(self):
  self.begin();hp=self.t.hp;self.hit(roll=1)
  self.assertEqual(self.t.hp,hp);self.assertNotIn('vortex',self.t.custom_conditions);self.assertEqual(self.e.condition_params,{})
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.move_uses[TRAP],1)
 def test_invalid_effect_parameters_reject_before_action_payment_and_rolls(self):
  self.begin();mm,_=self.r.move_mech(TRAP);broken=deepcopy(mm)
  broken['effects_exec'][0]['parameters']={'escape_dc_bonus':True}
  before=deepcopy((self.a.budget,self.a.move_uses,self.t.hp,self.t.conditions,self.t.custom_conditions,self.e.rng.getstate()))
  real=self.r.move_mech
  with patch.object(self.r,'move_mech',side_effect=lambda mid: (broken,{}) if mid==TRAP else real(mid)):
   with self.assertRaises(CONTRACTS.EffectContractError) as raised:self.e.use_move(self.a,self.t,TRAP)
  self.assertEqual(raised.exception.issue.field,'parameters')
  self.assertEqual((self.a.budget,self.a.move_uses,self.t.hp,self.t.conditions,self.t.custom_conditions,self.e.rng.getstate()),before)

if __name__=='__main__':unittest.main()
