"""Original-source outside-combat expiry through actual actors and restore.

Shared timer checks do not certify every temporary-HP producer or stacking
exception. Honey Thief fixtures supply an actual stolen digestion effect.
"""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_temporary_hp_state as _fixture_test_category2_temporary_hp_state
import temporary_hp as T,state_codec as CODEC

class TemporaryHPLifetimeTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_temporary_hp_state.TemporaryHPStateTests.setUpClass.__func__)
 setUp=_fixture_test_category2_temporary_hp_state.TemporaryHPStateTests.setUp
 add=_fixture_test_category2_temporary_hp_state.TemporaryHPStateTests.add
 restored=_fixture_test_category2_temporary_hp_state.TemporaryHPStateTests.restored
 snap=_fixture_test_category2_temporary_hp_state.TemporaryHPStateTests.snap
 grant=_fixture_test_category2_temporary_hp_state.TemporaryHPStateTests.grant
 def native_grant(self,c):
  self.target.spec.setdefault('items',{})['초코바']=1
  acquired=self.e.use_item(self.target,'초코바',duration_minutes=1,duration_reason='actual victim digestion buff before Bug Bite')
  uid=acquired['buff_id']
  _fixture_test_category2_temporary_hp_state.TemporaryHPStateTests.native_grant(self,c)
  self.assertFalse(self.target.buffs)
  self.assertTrue(any(row.get('id')==uid for row in c.buffs))
  receipts=[r for r in self.e._effect_dispatch_receipts.values() if r.get('source_id')=='move/벌레먹기']
  self.assertTrue(receipts);self.assertTrue(all(r['status']=='completed' for r in receipts))
  self.assertEqual(c.custom_conditions[T.STATE]['grant_source'],'ability/꿀도둑')
  return c.temp_hp
 def test_native_grants_for_both_actor_kinds_pause_in_combat_then_expire_at_300(self):
  for role in ['a','p']:
   with self.subTest(role=role):
    self.setUp();c=getattr(self,role);value=self.native_grant(c)
    self.e.advance_time(900);self.assertEqual(c.temp_hp,value)
    self.assertEqual(c.custom_conditions[T.STATE]['minimum_seconds'],300)
    self.e.end_encounter();self.e.advance_time(299);self.assertEqual(c.temp_hp,value)
    self.e.advance_time(1);self.assertEqual(c.temp_hp,0);self.assertNotIn(T.STATE,c.custom_conditions)
 def test_lower_equal_grants_keep_deadline_higher_grant_restarts_outside_clock(self):
  for c in self.actors:
   self.grant(c,10)
  self.e.advance_time(100);self.e.begin_encounter(self.actors);self.e.advance_time(900)
  for c in self.actors:
   for amount in [0,8,10]:self.grant(c,amount)
   self.assertEqual(c.custom_conditions[T.STATE]['minimum_seconds'],200)
  self.e.end_encounter();self.e.advance_time(199)
  self.grant(self.p,15);self.e.advance_time(1)
  self.assertEqual((self.a.temp_hp,self.p.temp_hp),(0,15))
  self.e.advance_time(298);self.assertEqual(self.p.temp_hp,15)
  self.e.advance_time(1);self.assertEqual(self.p.temp_hp,0)
 def test_native_status_cure_preserves_barrier_and_observed_ball_recall_clears_it(self):
  for role in ['a','p']:
   with self.subTest(role=role):
    self.setUp();c=getattr(self,role);value=self.native_grant(c)
    self.e.gm.set_move(c,'move/리프레시',True,reason='actual recovery Move')
    self.e.apply_status(c,'독');self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(c)
    self.e.use_move(c,c,'move/리프레시')
    self.assertNotIn('독',c.conditions);self.assertEqual(c.temp_hp,value)
  self.e.gm.recall(self.p,reason='actual observed return to owned Poke Ball')
  self.assertEqual(self.p.temp_hp,0);self.assertNotIn(T.STATE,self.p.custom_conditions)
 def test_gm_and_durable_restore_preserve_partial_outside_time_and_combat_pause(self):
  self.native_grant(self.p);self.e.end_encounter();self.e.advance_time(123)
  saved=self.e.gm.snapshot('outside-clock');value=self.p.temp_hp
  loaded=self.restored();clone=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
  for engine,c in [(self.e,self.p),(loaded,clone)]:
   engine.begin_encounter(engine.gm.everyone);engine.advance_time(900)
   self.assertEqual(c.custom_conditions[T.STATE]['minimum_seconds'],177)
   engine.end_encounter();engine.advance_time(176);self.assertEqual(c.temp_hp,value)
   engine.advance_time(1);self.assertEqual(c.temp_hp,0)
  self.e.gm.restore(saved);self.assertEqual(self.p.custom_conditions[T.STATE]['minimum_seconds'],177)
  self.e.advance_time(177);self.assertEqual(self.p.temp_hp,0)
 def test_legacy_clock_survives_storage_but_cannot_be_relabelled_or_used_without_reconciliation(self):
  for case in ['old_rule_clock','opaque_balance']:
   with self.subTest(case=case):
    self.setUp();self.grant(self.a,20);state=self.a.custom_conditions[T.STATE]
    if case=='old_rule_clock':state.pop('contributions');state.pop('clock_basis');state.update(minimum_seconds=100,maximum_seconds=200)
    else:self.a.custom_conditions.pop(T.STATE)
    loaded=self.restored();clone=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id)
    for engine,c in [(self.e,self.a),(loaded,clone)]:
     before=(c.hp,c.temp_hp,deepcopy(c.custom_conditions.get(T.STATE)),engine.rng.getstate())
     with self.assertRaisesRegex(ValueError,'temporary HP expiry'):engine.take_damage(c,1)
     self.assertEqual((c.hp,c.temp_hp,c.custom_conditions.get(T.STATE),engine.rng.getstate()),before)
     engine.advance_time(900);self.assertEqual(c.custom_conditions.get(T.STATE),before[2])
     engine.gm.set_temp_hp(c,20,duration_seconds=7,reason='GM observed remaining duration for legacy save')
     engine.advance_time(7);self.assertEqual(c.temp_hp,0)
 def test_honey_thief_no_food_miss_suppressed_or_unowned_never_grants(self):
  for case in ['no_food','miss','suppressed','unowned']:
   with self.subTest(case=case):
    self.setUp();c=self.a;c.pos=(1,1);self.target.pos=(2,1)
    if case!='no_food':
     self.target.spec.setdefault('items',{})['초코바']=1
     self.e.use_item(self.target,'초코바',duration_minutes=1,duration_reason='actual food')
    if case!='unowned':self.e.gm.set_ability(c,'꿀도둑',True,reason='actual ability')
    self.e.gm.set_move(c,'move/벌레먹기',True,reason='actual Move')
    if case=='suppressed':c.abilities_suppressed=True
    self.e.start_round([c,self.target]);self.e.start_of_turn(c)
    with patch.object(type(self.e),'d20',new=lambda engine:1 if case=='miss' else 18):self.e.use_move(c,self.target,'move/벌레먹기',set_damage=True)
    self.assertEqual(c.temp_hp,0);self.assertNotIn(T.STATE,c.custom_conditions)
    if case=='miss':self.assertEqual(len(self.target.buffs),1)
    if case in ['suppressed','unowned']:self.assertEqual(len(c.buffs),1)
 def test_honey_thief_grant_occurs_after_actual_hit_and_transfer_not_declaration(self):
  original=type(self.e).accuracy_check
  def observe(engine,a,t,*args,**kw):
   self.assertEqual(a.temp_hp,0);self.assertTrue(t.buffs)
   return original(engine,a,t,*args,**kw)
  with patch.object(type(self.e),'accuracy_check',new=observe):value=self.native_grant(self.a)
  self.assertGreater(value,0)
 def test_explicit_gm_clock_and_unbounded_override_keep_their_declared_meaning(self):
  self.e.begin_encounter(self.actors)
  self.e.gm.set_temp_hp(self.a,10,duration_seconds=25,reason='explicit elapsed-time override')
  self.e.gm.set_temp_hp(self.p,10,reason='explicit unbounded override')
  self.e.advance_time(24);self.assertEqual((self.a.temp_hp,self.p.temp_hp),(10,10))
  self.e.advance_time(1);self.assertEqual((self.a.temp_hp,self.p.temp_hp),(0,10))
  self.e.end_encounter();self.e.advance_time(900);self.assertEqual(self.p.temp_hp,10)

 def test_actual_membership_pauses_only_participants_and_native_send_out_joins(self):
  for c in self.actors:self.grant(c,10)
  self.e.begin_encounter([self.a]);self.e.advance_time(120)
  self.assertEqual([c.custom_conditions[T.STATE]['minimum_seconds'] for c in self.actors],[300,180])
  self.e.gm.send_out(self.p,reason='observed entry into this encounter')
  self.e.advance_time(200)
  self.assertEqual([c.custom_conditions[T.STATE]['minimum_seconds'] for c in self.actors],[300,180])
  self.e.end_encounter();self.e.advance_time(179)
  self.assertEqual((self.a.temp_hp,self.p.temp_hp),(10,10))
  self.e.advance_time(1);self.assertEqual((self.a.temp_hp,self.p.temp_hp),(10,0))
  self.assertEqual(self.a.custom_conditions[T.STATE]['minimum_seconds'],120)
 def test_unknown_final_round_only_widens_outsider_clock_and_survives_restore(self):
  for c in self.actors:self.grant(c,10)
  self.e.start_round([self.a]);self.e.end_encounter()
  self.assertEqual([self.a.custom_conditions[T.STATE][k] for k in ('minimum_seconds','maximum_seconds')],[300,300])
  self.assertEqual([self.p.custom_conditions[T.STATE][k] for k in ('minimum_seconds','maximum_seconds')],[290,300])
  loaded=self.restored()
  for engine in (self.e,loaded):
   actors={c.entity_id:c for c in engine.gm.everyone};a,p=[actors[c.entity_id] for c in self.actors]
   engine.advance_time(290)
   engine.take_damage(a,1);self.assertEqual(a.temp_hp,9)
   before=(p.hp,p.temp_hp,deepcopy(p.custom_conditions),engine.rng.getstate())
   with self.assertRaisesRegex(ValueError,'temporary HP expiry'):engine.take_damage(p,1)
   self.assertEqual((p.hp,p.temp_hp,p.custom_conditions,engine.rng.getstate()),before)
   engine.advance_time(10)
   self.assertEqual((a.temp_hp,p.temp_hp),(0,0))

 def test_successor_round_finishes_old_membership_before_joining_newcomer(self):
  for c in self.actors:self.grant(c,10)
  self.e.start_round([self.a]);self.e.at_round_offset(4)
  loaded=self.restored()
  for engine in (self.e,loaded):
   actors={c.entity_id:c for c in engine.gm.everyone};a,p=[actors[c.entity_id] for c in self.actors]
   engine.start_round([a,p])
   self.assertEqual([c.custom_conditions[T.STATE]['minimum_seconds'] for c in [a,p]],[300,290])
   engine.end_round()
   self.assertEqual([c.custom_conditions[T.STATE]['minimum_seconds'] for c in [a,p]],[300,290])

if __name__=='__main__':unittest.main()
