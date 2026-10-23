"""Native voluntary Breather, actual effects and common action boundaries."""
from pathlib import Path
from unittest.mock import patch
import unittest
from engine import Rules,Engine,Combatant
from grid import Grid
import breather as BREATHER,stamina as STAMINA,temporary_hp as TEMP
import state_grants as G,state_codec as CODEC,combat_timing as TIMING
import effects_ext as EXT,movement_actions as MOVEMENT,common_checks as C

ROOT=Path(__file__).resolve().parents[1]

class BreatherTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=5);self.e.grid=Grid(7,5)
  def actor(identity,kind='trainer'):
   return Combatant(self.r,{'id':identity,'name':identity,'kind':kind,'level':20,'size':'medium',
    'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),30),'movement':{'land':4},
    'skills':{'육상':5,'전투':5},'moves':['struggle'],'edges':[],'abilities':[],'types':[]})
  self.make_actor=actor
  self.a,self.b=actor('trainer/retreater'),actor('trainer/enemy')
  self.a.side='party';self.b.side='enemy';self.a.pos=(2,2);self.b.pos=(1,2)
  self.e.everyone=self.e.gm.everyone=[self.a,self.b]
  self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a)
  self.b.aoo_used=True
 def own(self):G.transition(self.e,self.a,lambda e,c:c.spec['edges'].append(STAMINA.SOURCE))
 def options(self,**overrides):
  result={'request_id':'breather:one','path':[(2,2),(3,2),(4,2),(5,2),(6,2)],
   'retreat_reason':'GM observes the actual four-metre route reaches the furthest feasible map edge away from the enemy',
   'save_dc':16,'save_reason':'Explicit table adjudication: DC16 general permission; failed attempt pays Full',
   'save_cost':'full','fixed_save':20}
  result.update(overrides);return result
 def take(self,**overrides):return self.e.take_breather(self.a,**self.options(**overrides))
 def test_actual_recovery_and_full_cost_finish_before_stamina(self):
  self.own();self.e.apply_status(self.a,'혼란');self.e.change_stage(self.a,'atk',3);TEMP.grant(self.e,self.a,12)
  seen=[];observe=STAMINA.observe
  def fact(e,a,event,**kw):
   if event=='take_a_breather':seen.append((a.temp_hp,set(a.conditions),dict(a.stages)))
   return observe(e,a,event,**kw)
  with patch.object(STAMINA,'observe',side_effect=fact),patch.object(MOVEMENT,'follow_paid_path',wraps=MOVEMENT.follow_paid_path) as follow:
   result=self.take()
  self.assertTrue(result['completed']);self.assertEqual(self.a.pos,(6,2))
  self.assertEqual(self.a.budget,{'standard':0,'shift':0,'swift':1})
  self.assertEqual((self.a.temp_hp,follow.call_count),(5,1));self.assertNotIn('혼란',self.a.conditions)
  self.assertEqual(seen,[(0,{'넘어짐','취약'},dict.fromkeys(self.a.stages,0))])
  row=list(self.e._native_action_resolutions.values())[-1]
  self.assertEqual((row['kind'],row['source'],row['phase']),('breather',BREATHER.SOURCE,'producer_returned'))
 def test_rooted_stationary_breather_cures_other_conditions_and_preserves_persistent_default(self):
  self.e.apply_status(self.a,'구속');self.e.apply_status(self.a,'둔화');self.e.apply_status(self.a,'독')
  self.e.change_stage(self.a,'def',2);TEMP.grant(self.e,self.a,9)
  result=self.take(path=[(2,2)],retreat_reason='Actual Stuck prevents any retreat; the farthest feasible distance is zero')
  self.assertTrue(result['completed']);self.assertEqual(self.a.pos,(2,2))
  self.assertEqual(self.a.conditions,{'독','넘어짐','취약'});self.assertEqual(self.a.temp_hp,0)
 def test_failed_observed_save_never_recovers_or_triggers_and_cannot_be_rerolled(self):
  self.own();self.e.apply_status(self.a,'혼란');TEMP.grant(self.e,self.a,9)
  result=self.take(fixed_save=1);state=CODEC.dump_engine(self.e)
  self.assertEqual(result['reason'],'save_failed');self.assertIn('혼란',self.a.conditions)
  self.assertEqual((self.a.temp_hp,self.a.budget['standard'],self.a.budget['shift']),(9,0,0))
  self.assertEqual(self.take(fixed_save=1),result);self.assertEqual(CODEC.dump_engine(self.e),state)
  with self.assertRaisesRegex(ValueError,'declaration'):self.take(fixed_save=20)
 def test_success_only_is_explicit_table_policy_not_an_invented_failed_save_charge(self):
  result=self.take(fixed_save=1,save_cost='success_only')
  self.assertFalse(result['completed']);self.assertEqual((self.a.budget['standard'],self.a.budget['shift']),(1,1))
 def test_missing_unprinted_dc_cost_and_unimplemented_assistance_hold_before_rng_or_cost(self):
  before=CODEC.dump_engine(self.e)
  for changes in ({'save_dc':None},{'save_cost':None},{'helper':self.b}):
   self.assertIsInstance(self.take(**changes),C.PendingDecision)
   self.assertEqual(CODEC.dump_engine(self.e),before)
 def test_actual_curse_origin_at_twelve_metres_is_retained_beyond_twelve_cured(self):
  for endpoint,cured in ((14,False),(15,True)):
   with self.subTest(endpoint=endpoint):
    self.setUp();self.e.grid=Grid(endpoint+1,5);self.b.pos=(2,2);self.a.pos=(endpoint-1,2)
    self.e.apply_status(self.a,'저주',source='move/저주',applied_by=self.b)
    self.assertIs(self.a.custom_conditions['curse_origin'],self.b)
    result=self.take(path=[self.a.pos,(endpoint,2)])
    self.assertTrue(result['completed']);self.assertEqual('저주' not in self.a.conditions,cured)
    self.assertEqual('curse_origin' not in self.a.custom_conditions,cured)
 def test_fainted_curse_origin_cures_and_unknown_origin_does_not_guess(self):
  self.e.apply_status(self.a,'저주')
  before=CODEC.dump_engine(self.e);self.assertIsInstance(self.take(),C.PendingDecision)
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.e.lose_hp(self.b,self.b.base_max_hp,source='test actual fainting')
  result=self.take(curse_origin=self.b,curse_reason='GM identifies the actual now-fainted Curse user')
  self.assertTrue(result['completed']);self.assertNotIn('저주',self.a.conditions)
 def test_next_owner_turn_end_lifetime_and_completed_restore_do_not_reaward(self):
  self.own();result=self.take();saved=CODEC.dump_engine(self.e)
  restored=CODEC.load_engine(self.r,saved);a=next(c for c in restored.everyone if c.entity_id==self.a.entity_id)
  self.assertEqual(restored.take_breather(a,**self.options()),result);self.assertEqual(a.temp_hp,5)
  self.e.end_of_turn(self.a);self.assertIn('넘어짐',self.a.conditions)
  self.e.start_of_turn(self.b);self.e.end_of_turn(self.b)
  self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a)
  self.assertIn('넘어짐',self.a.conditions)
  self.e.end_of_turn(self.a);self.assertNotIn('넘어짐',self.a.conditions);self.assertNotIn('취약',self.a.conditions)
 def test_actual_opportunity_attack_resolves_before_breather_reset_and_final_stamina(self):
  self.own();self.b.aoo_used=False;seen=[];clear=TEMP.clear
  def cleared(e,a,reason):
   if a.entity_id==self.a.entity_id and reason=='숨돌리기':seen.append(a.temp_hp)
   return clear(e,a,reason)
  with patch.object(TEMP,'clear',side_effect=cleared):
   result=self.take()
  self.assertTrue(result['completed']);self.assertTrue(self.b.aoo_used)
  self.assertEqual(seen,[5]);self.assertEqual(self.a.temp_hp,5)
  self.assertEqual([r['kind'] for r in self.e._native_action_resolutions.values()],['move','breather'])
 def test_late_native_movement_error_keeps_observed_save_and_cost_without_claiming_completion(self):
  with patch.object(EXT,'on_enter_cell',side_effect=RuntimeError('native cell hook failed')):
   with self.assertRaisesRegex(RuntimeError,'cell hook'):self.take()
  self.assertEqual((self.a.budget['standard'],self.a.budget['shift']),(0,0))
  self.assertEqual(self.e._breather_attempts['breather:one']['observed_resolution']['observation']['check']['natural'],20)
  with self.assertRaisesRegex(ValueError,'unfinished'):self.take(request_id='breather:retry')
  with self.assertRaisesRegex(ValueError,'unfinished'):self.e.end_of_turn(self.a)
 def test_invalid_route_and_slower_capability_are_not_silent_partial_success(self):
  before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'continuous'):self.take(path=[(2,2),(6,2)])
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.a.spec['movement']['sky']=8
  self.assertIsInstance(self.take(),C.PendingDecision)
  self.assertEqual(self.a.budget['standard'],1)
 def test_pokemon_uses_same_actual_full_recovery_without_requiring_a_trainer_edge(self):
  self.e=Engine(self.r,seed=5);self.e.grid=Grid(7,5)
  self.a=self.make_actor('pokemon/retreater','pokemon');self.a.side='party';self.a.pos=(2,2)
  self.e.everyone=self.e.gm.everyone=[self.a,self.b]
  self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a);self.b.aoo_used=True
  self.e.apply_status(self.a,'혼란');TEMP.grant(self.e,self.a,8)
  result=self.take(save_dc=None)
  self.assertTrue(result['completed']);self.assertEqual(result['save']['base_dc'],16)
  self.assertEqual(self.a.temp_hp,0);self.assertEqual(self.a.pos,(6,2))
 def test_breather_completion_waits_for_actual_stamina_skill_choice_after_clearing_old_temp_hp(self):
  self.a.spec['skills']['전투']=6;self.own();TEMP.grant(self.e,self.a,20)
  self.assertTrue(self.take()['completed']);self.assertEqual(self.a.temp_hp,0)
  row=list(self.e._native_action_resolutions.values())[-1]
  with self.assertRaisesRegex(ValueError,'Stamina'):self.e.end_of_turn(self.a)
  restored=CODEC.load_engine(self.r,CODEC.dump_engine(self.e))
  actor=next(c for c in restored.everyone if c.entity_id==self.a.entity_id)
  restored.resolve_stamina(actor,row['id'],skill='전투')
  self.assertEqual(actor.temp_hp,6);self.assertEqual(actor.budget['standard'],0)
  self.assertNotIn('혼란',actor.conditions)
 def test_fabricated_curse_origin_is_rejected_before_status_or_lifetime_changes(self):
  before=CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):
   self.e.apply_status(self.a,'저주',source='move/저주',applied_by=self.make_actor('trainer/foreign'))
  self.assertEqual(CODEC.dump_engine(self.e),before)

if __name__=='__main__':unittest.main()
