"""Shared temporary-HP balance through native grants, attacks and persistence."""
from copy import deepcopy
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_condition_recovery as FIX
import temporary_hp as T,effects as FX,state_codec as CODEC,state_fields as FIELDS

class TemporaryHPStateTests(unittest.TestCase):
 setUpClass=classmethod(FIX.ConditionRecoveryTests.setUpClass.__func__)
 setUp=FIX.ConditionRecoveryTests.setUp
 add=FIX.ConditionRecoveryTests.add
 restored=FIX.ConditionRecoveryTests.restored
 snap=FIX.ConditionRecoveryTests.snap
 def grant(self,c,value):
  return FX.run_effects(self.e,c,c,[{'type':'temp_hp','value':value}],{'hit':True,'attacker':c,'target':c,'engine':self.e},'temporary HP component')
 def native_grant(self,c):
  if not self.target.buffs:
   self.target.spec.setdefault('items',{})['초코바']=1
   self.e.use_item(self.target,'초코바',duration_minutes=1,duration_reason='actual food buff before Honey Thief')
  self.e.gm.set_ability(c,'꿀도둑',True,reason='observed native ability')
  self.e.gm.set_move(c,'move/벌레먹기',True,reason='observed native move')
  c.pos=(1,1);self.target.pos=(2,1)
  self.e.start_round([c,self.target]);self.e.start_of_turn(c)
  self.e.rng.seed(6)
  self.e.use_move(c,self.target,'move/벌레먹기',set_damage=True)
  self.assertEqual(c.move_uses['move/벌레먹기'],1)
  self.e.end_of_turn(c);self.e.end_round()
 def test_native_honey_gather_grants_above_full_actual_hp_for_both_kinds(self):
  for kind in ('trainer','pokemon'):
   self.setUp();c=self.a if kind=='trainer' else self.p;hp=c.hp
   self.native_grant(c)
   self.assertEqual((c.hp,c.temp_hp,c.base_max_hp),(hp,self.e.tick(c),hp))
   self.assertEqual(c.custom_conditions[T.STATE]['source'],'condition/임시-체력')
 def test_grants_max_merge_and_never_heal_or_lower_actual_hp(self):
  for c in self.actors:
   self.e.gm.set_hp(c,1,reason='low actual HP')
   for value,expected in ((10,10),(8,10),(10,10),(15,15),(0,15)):
    before=deepcopy(c.custom_conditions.get(T.STATE));self.grant(c,value)
    self.assertEqual((c.hp,c.temp_hp),(1,expected))
    if before and value<=10:self.assertEqual(c.custom_conditions[T.STATE],before)
 def test_damage_and_ordinary_loss_share_absorption_and_clear_spent_lifetime(self):
  for c in self.actors:
   hp=c.hp;self.grant(c,10);self.e.take_damage(c,7)
   self.assertEqual((c.hp,c.temp_hp),(hp,3));self.assertIn(T.STATE,c.custom_conditions)
   self.e.lose_hp(c,5,source='ordinary effect')
   self.assertEqual((c.hp,c.temp_hp),(hp-2,0));self.assertNotIn(T.STATE,c.custom_conditions)
   self.e.take_damage(c,1);self.assertEqual(c.hp,hp-3)
 def test_native_attack_consumes_barrier_before_actual_hp_for_both_targets(self):
  for kind in ('trainer','pokemon'):
   self.setUp();c=self.a if kind=='trainer' else self.p
   attacker=self.p if kind=='trainer' else self.a
   attacker.pos=(1,1);c.pos=(2,1);self.e.gm.set_move(attacker,'move/메가톤펀치',True,reason='actual attack')
   self.grant(c,1000);hp=c.hp
   self.e.start_round([attacker,c]);self.e.start_of_turn(attacker);self.e.rng.seed(6)
   self.e.use_move(attacker,c,'move/메가톤펀치',set_damage=True)
   self.assertEqual(c.hp,hp);self.assertLess(c.temp_hp,1000);self.assertGreater(c.temp_hp,0)
   self.assertEqual(attacker.move_uses['move/메가톤펀치'],1)
 def test_invalid_damage_or_loss_cannot_turn_into_bonus_hp(self):
  for c in self.actors:
   self.grant(c,9)
   for fn in (self.e.take_damage,self.e.lose_hp):
    for bad in (-1,True,1.5,float('nan')):
     before=self.snap()
     with self.assertRaises(ValueError):fn(c,bad)
     self.assertEqual(self.snap(),before)
 def test_actual_blaze_damage_uses_actual_one_hp_despite_large_barrier(self):
  for c in self.actors:
   self.e.gm.set_ability(c,'맹화',True,reason='actual low HP ability')
   self.e.gm.set_hp(c,1,reason='actual 1 HP');move=self.r.move('move/불꽃세례')
   target=self.p if c is self.a else self.a
   low=self.e.roll_damage(c,target,move,set_damage=True)
   self.grant(c,1000)
   self.assertEqual(self.e.roll_damage(c,target,move,set_damage=True),low)
   self.e.gm.set_hp(c,c.base_max_hp,reason='full actual HP')
   high=self.e.roll_damage(c,target,move,set_damage=True)
   self.assertEqual(low-high,5)
 def test_tick_capture_and_maximum_ignore_temporary_hp(self):
  for c in self.actors:
   self.e.gm.set_hp(c,1,reason='actual HP');before=(c.base_max_hp,c.max_hp,self.e.tick(c))
   self.grant(c,50);self.assertEqual((c.base_max_hp,c.max_hp,self.e.tick(c)),before)
  self.p.temp_hp=0;before=self.e.capture_rate(self.p);self.grant(self.p,1000)
  self.assertEqual(self.e.capture_rate(self.p),before)
 def test_temporary_hp_does_not_revive_actual_zero_hp(self):
  for c in self.actors:
   self.e.gm.faint(c,reason='observed faint');self.grant(c,50)
   self.assertEqual(c.hp,0);self.assertTrue(c.fainted);self.assertEqual(c.temp_hp,50)
 def test_gm_and_durable_restore_replay_native_grant_and_consumption(self):
  for kind in ('trainer','pokemon'):
   self.setUp();c=self.a if kind=='trainer' else self.p;self.native_grant(c)
   hp,temp=c.hp,c.temp_hp;state=deepcopy(c.custom_conditions[T.STATE])
   self.e.gm.snapshot('barrier');loaded=self.restored();copy=next(x for x in loaded.gm.everyone if x.entity_id==c.entity_id)
   self.assertEqual((copy.hp,copy.temp_hp,copy.custom_conditions[T.STATE]),(hp,temp,state))
   for engine,actor in ((self.e,c),(loaded,copy)):
    engine.lose_hp(actor,temp+1);self.assertEqual((actor.hp,actor.temp_hp),(hp-1,0));self.assertNotIn(T.STATE,actor.custom_conditions)
   self.e.gm.restore('barrier');self.assertEqual((c.hp,c.temp_hp,c.custom_conditions[T.STATE]),(hp,temp,state))
   self.e.lose_hp(c,temp+1);self.assertEqual((c.hp,c.temp_hp),(hp-1,0))
   again=self.restored();copy=next(x for x in again.gm.everyone if x.entity_id==c.entity_id)
   self.assertEqual((copy.hp,copy.temp_hp),(hp-1,0));self.assertNotIn(T.STATE,copy.custom_conditions)
 def test_combat_paused_timer_survives_restore_then_expires_outside_combat(self):
  self.e.start_round(self.actors);self.grant(self.a,20);self.e.end_round();self.e.advance_time(600)
  loaded=self.restored();copy=next(x for x in loaded.gm.everyone if x.entity_id==self.a.entity_id)
  self.assertEqual(copy.custom_conditions[T.STATE],self.a.custom_conditions[T.STATE])
  for engine,c in ((self.e,self.a),(loaded,copy)):
   hp=c.hp;engine.take_damage(c,1);self.assertEqual((c.hp,c.temp_hp),(hp,19))
   engine.end_encounter();engine.advance_time(299);self.assertEqual(c.temp_hp,19)
   engine.advance_time(1);self.assertEqual(c.temp_hp,0)
 def test_malformed_lifetime_rejected_before_consumption_and_persistence(self):
  self.grant(self.a,12);good=deepcopy(self.a.custom_conditions[T.STATE])
  for changes in ({'source':'gm/state'},{'minimum_seconds':True},{'maximum_seconds':-1},{'minimum_seconds':301,'maximum_seconds':300},{'birth_round':False},{'unknown_elapsed':1},{'expiry_policy':'explicit_unbounded'}):
   self.a.custom_conditions[T.STATE]={**good,**changes};before=self.snap()
   with self.assertRaises(ValueError):self.e.take_damage(self.a,1)
   self.assertEqual(self.snap(),before)
   with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  self.a.custom_conditions[T.STATE]=good
  FIELDS.validate_actor(self.a)
 def test_explicit_gm_zero_removes_lifetime_without_affecting_actual_hp(self):
  for c in self.actors:
   hp=c.hp;self.e.gm.set_temp_hp(c,15,duration_seconds=25);self.e.gm.set_temp_hp(c,0)
   self.assertEqual((c.hp,c.temp_hp),(hp,0));self.assertNotIn(T.STATE,c.custom_conditions)

if __name__=='__main__':unittest.main()
