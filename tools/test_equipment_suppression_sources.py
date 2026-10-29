"""Actual registration, native events, independent source removal and restore."""
from pathlib import Path
from copy import deepcopy
from contextlib import contextmanager
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_global_rooms_gravity as _fixture_test_category2_global_rooms_gravity
import test_category2_held_item_reactions as _fixture_test_category2_held_item_reactions
from engine import Rules,Engine
from ruleset import RuleFilter
import items as I,state_grants as G,world_entities as W,field_effects as FIELD
import weather_state as WEATHER,equipment_suppression as S,event_effects as EVENTS
import effects as FX


class SuppressionTests(unittest.TestCase):
 @staticmethod
 def selected_rules():
  rules=Rules(str(ROOT),ruleset='core')
  rules.ruleset=RuleFilter({'sources':['core'],'variants':['소실']})
  rules._apply_ruleset()
  return rules
 @classmethod
 def setUpClass(cls):cls.r=cls.selected_rules()
 setUp=_fixture_test_category2_global_rooms_gravity.GlobalRoomGravityTests.setUp
 effect=_fixture_test_category2_global_rooms_gravity.GlobalRoomGravityTests.effect
 install=_fixture_test_category2_global_rooms_gravity.GlobalRoomGravityTests.install
 equip=_fixture_test_category2_held_item_reactions.HeldItemReactionTests.equip
 def klutz(self,actor,enabled=True):
  G.replace_baseline(self.e,actor,'abilities',[S.KLUTZ_NAME] if enabled else [])
 @contextmanager
 def temporary_rule_profile(self,profile):
  rules=self.e.r;previous=rules.ruleset
  try:
   rules.ruleset=RuleFilter(profile)
   rules._apply_ruleset()
   yield
  finally:
   rules.ruleset=previous
   rules._apply_ruleset()
 def test_overlap_orders_and_creation_time_weather_are_source_owned(self):
  for remove_field_first in (True,False):
   self.setUp()
   uid=self.equip(self.e,self.a,'item/선제공격손톱','claw')
   held=deepcopy(self.a.spec['held_equipment'])
   self.assertEqual(self.a.initiative_bonus,10)
   self.klutz(self.a);self.assertEqual(self.a.initiative_bonus,0)
   self.install('move/매직룸')
   record=next(iter(self.a._item_reg.values()))
   self.assertEqual(len(record[S.KEY]['reasons']),2)
   if remove_field_first:self.install('move/원더룸')
   else:self.klutz(self.a,False)
   self.assertEqual(self.a.initiative_bonus,0)
   if remove_field_first:self.klutz(self.a,False)
   else:self.install('move/원더룸')
   self.assertEqual(self.a.initiative_bonus,10)
   I.synchronize_equipment_suppression(self.e)
   self.assertEqual(self.a.initiative_bonus,10)
   self.assertEqual(self.a.spec['held_equipment'],held)
   I.drop_item(self.e,self.a,selection=uid)
   self.equip(self.e,self.a,'item/축축한바위','rock')
   self.e.start_of_turn(self.a,initiative_count=20)
   WEATHER.set_weather(self.e,'rain',rounds=5,source_id='move/비바라기',origin='move',actor=self.a)
   original=deepcopy(self.e._weather_state['active'])
   self.assertEqual(self.e.weather_rounds,7)
   self.klutz(self.a)
   self.assertEqual(self.e._weather_state['active'],original)
   WEATHER.set_weather(self.e,'rain',rounds=5,source_id='move/비바라기',origin='move',actor=self.a)
   self.assertEqual(self.e.weather_rounds,5)
   self.assertNotIn('item_extension',self.e._weather_state['active'])
 def test_native_reaction_and_consumption_are_distinct_from_held_benefit(self):
  self.e,self.a,self.t=_fixture_test_category2_held_item_reactions.HeldItemReactionTests.fixture(self)
  self.equip(self.e,self.t,'item/울퉁불퉁멧','helmet')
  self.klutz(self.t)
  self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a,initiative_count=20)
  before=self.a.hp
  dealt=self.e.use_move(self.a,self.t,'move/드래곤클로',situational=100,set_damage=True)
  self.assertGreater(dealt,0);self.assertEqual(self.a.hp,before)
  # Native global suppression producer removes the Klutz reason, not the item.
  G.transition(self.e,self.t,lambda e,c:FX.h_suppress_ability(e,c,c,{},{}))
  self.assertTrue(self.t.abilities_suppressed)
  self.assertTrue(I.equipment_benefit_active(self.t,next(iter(self.t._item_reg.values()))))
  self.e.end_of_turn(self.a)
  self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a,initiative_count=20)
  before=self.a.hp
  self.e.use_move(self.a,self.t,'move/드래곤클로',situational=100,set_damage=True)
  self.assertEqual(self.a.hp,before-self.e.tick(self.a))
  self.klutz(self.a)
  self.a.spec.setdefault('items',{})['불꽃주얼']=1
  out=self.e.use_item(self.a,'불꽃주얼')
  self.assertEqual(out['status'],'stored_effect')
  paid=deepcopy(EVENTS.live(self.a))
  self.install('move/매직룸');self.klutz(self.a,False)
  self.assertEqual(EVENTS.live(self.a),paid)
  self.assertEqual(self.a.spec['items']['불꽃주얼'],0)
 def test_native_holder_changes_gm_cold_restore_and_forged_source_rejection(self):
  uid=self.equip(self.e,self.a,'item/선제공격손톱','restore-claw')
  self.klutz(self.a);self.install('move/매직룸')
  self.e.gm.snapshot('both')
  self.klutz(self.a,False);self.install('move/원더룸')
  self.e.gm.restore('both');self.assertEqual(self.a.initiative_bonus,0)
  fresh=self.selected_rules()
  loaded=Engine.import_state(fresh,json.loads(json.dumps(self.e.export_state())))
  a=W.actor_index(loaded)[self.a.entity_id];t=W.actor_index(loaded)[self.t.entity_id]
  self.assertEqual(a.initiative_bonus,0)
  row=next(iter(a._item_reg.values()));old=deepcopy(row[S.KEY])
  row[S.KEY]['reasons'][-1]['holder_id']=t.entity_id
  with self.assertRaises(ValueError):loaded.export_state()
  row[S.KEY]=old
  FIELD.install(loaded,a,fresh.move_mech('move/원더룸')[0]['effects_exec'][0],'move/원더룸')
  I.transfer_equipment(loaded,a,t,uid)
  self.assertEqual((a.initiative_bonus,t.initiative_bonus),(0,10))
  self.assertEqual(loaded._physical_objects[uid]['equipped_by'],t.entity_id)
  I.drop_item(loaded,t,selection=uid)
  self.assertEqual(loaded._physical_objects[uid]['location'],W.location_of(t))
  I.equip_held(loaded,a,'item/선제공격손톱',source_instance_id=uid)
  self.assertEqual(a.initiative_bonus,0)
  loaded.export_state()

 def test_selected_native_ability_operation_revoke_reactivates_exact_reason(self):
  from test_category2_ability_transitions import AbilityTransitionTests as A
  self.actor=A.actor.__get__(self)
  A.setUp(self)
  self.equip(self.e,self.t,'item/선제공격손톱','selected-claw')
  self.klutz(self.t)
  self.assertEqual(self.t.initiative_bonus,0)
  self.e.gm.choose_ability_transition(self.a,self.t,'move/위액',ability=S.KLUTZ_NAME,reason='actual selected ability')
  self.e.use_move(self.a,self.t,'move/위액',situational=100)
  self.assertFalse(self.t.abilities_suppressed)
  self.assertEqual(self.t.initiative_bonus,10)
  self.e.end_of_turn(self.a)
  self.e.end_encounter(self.e.everyone)
  self.assertEqual(self.t.initiative_bonus,0)
  self.assertEqual(next(iter(self.t._item_reg.values()))[S.KEY]['reasons'][0]['source'],S.KLUTZ)

 def test_authenticated_legacy_restore_and_marker_independent_classification(self):
  import state_codec as CODEC
  self.equip(self.e,self.a,'item/선제공격손톱','legacy-claw')
  self.install('move/매직룸')
  self.e.gm.snapshot('legacy')
  snapshot=self.e.gm.snapshots['legacy']
  for attrs in snapshot['combatants'].values():
   for row in attrs.get('_item_reg',{}).values():row.pop(S.KEY,None)
  self.e.gm.restore('legacy')
  row=next(iter(self.a._item_reg.values()))
  self.assertIn(S.KEY,row);self.assertEqual(self.a.initiative_bonus,0)
  payload=self.e.export_state()
  row.pop(S.KEY)
  # Encode the historical marker-only graph without invoking current-save
  # validation; import still runs every native current-world validator.
  encoder=CODEC._Encoder(self.e)
  payload['root']=encoder.value(self.e);payload['nodes']=encoder.nodes
  loaded=Engine.import_state(self.selected_rules(),json.loads(json.dumps(payload)))
  a=W.actor_index(loaded)[self.a.entity_id]
  self.assertIn(S.KEY,next(iter(a._item_reg.values())))
  self.assertEqual(a.initiative_bonus,0)
  S.upgrade_legacy(self.e,W.actor_index(self.e))
  with self.temporary_rule_profile({'sources':['core'],'variants':['소실','홈브류']}):
   for item_id in ('item/상처약','item/귀여운-패션-1'):
    fake={'item_id':item_id,I.MAGIC_ROOM_KEY:deepcopy(row[I.MAGIC_ROOM_KEY])}
    self.assertFalse(I._passive_registration(self.e,self.a,fake))
    self.assertEqual(S.reasons(self.e,self.a,'forged',fake),[])
    self.a._item_reg['forged']=fake
    with self.assertRaises(ValueError):S.upgrade_legacy(self.e,W.actor_index(self.e))
    fake[S.KEY]={'reasons':[{'kind':'field','source':self.e.field['source_id'],'holder_id':self.a.entity_id,'registration_key':'forged'}]}
    with self.assertRaises(ValueError):S.validate(self.e,W.actor_index(self.e))
    del self.a._item_reg['forged']
  marker=deepcopy(row[I.MAGIC_ROOM_KEY]);row.pop(S.KEY)
  row[I.MAGIC_ROOM_KEY]['field_source']='move/원더룸'
  with self.assertRaises(ValueError):S.upgrade_legacy(self.e,W.actor_index(self.e))
  self.assertNotIn(S.KEY,row)
  row[I.MAGIC_ROOM_KEY]=marker
  S.upgrade_legacy(self.e,W.actor_index(self.e))

 def test_shared_profile_restores_after_failure_and_legacy_then_holder_cold_roundtrip(self):
  import state_codec as CODEC
  shared=self.r;previous=shared.ruleset;fingerprint=CODEC.rules_fingerprint(shared)
  with self.assertRaisesRegex(RuntimeError,'fixture profile failure'):
   with self.temporary_rule_profile({'sources':['core'],'variants':['소실','홈브류']}):
    raise RuntimeError('fixture profile failure')
  self.assertIs(shared.ruleset,previous)
  self.assertEqual(CODEC.rules_fingerprint(shared),fingerprint)
  # Reproduce the actual failing sequence with one shared Rules and fresh worlds.
  self.test_authenticated_legacy_restore_and_marker_independent_classification()
  self.assertIs(self.r,shared);self.assertIs(shared.ruleset,previous)
  self.assertEqual(CODEC.rules_fingerprint(shared),fingerprint)
  self.setUp();self.assertIs(self.e.r,shared)
  self.test_native_holder_changes_gm_cold_restore_and_forged_source_rejection()
  payload=json.loads(json.dumps(self.e.export_state()))
  with self.assertRaisesRegex(CODEC.StateCodecError,'selected rule/profile/source fingerprint mismatch'):
   Engine.import_state(Rules(str(ROOT),ruleset='core'),payload)
  self.assertIs(shared.ruleset,previous)
  self.assertEqual(CODEC.rules_fingerprint(shared),fingerprint)

 def test_actual_crafted_attachment_stays_suppressed_across_native_clock(self):
  from test_foundation_crafting_product import ProductTests as P
  fixture=P();fixture.rules=self.r
  fixture.setUp()
  self.e=fixture.e
  fixture.made(owner=fixture.p,seconds=600)
  fixture.equip(fixture.p)
  self.assertEqual(fixture.p.save_mod,2)
  self.klutz(fixture.p)
  self.assertEqual(fixture.p.save_mod,0)
  self.e.advance_time(1,self.e.everyone)
  self.assertEqual(fixture.p.save_mod,0)
  self.e.gm.snapshot('crafted-suppressed')
  self.e.export_state()
  self.klutz(fixture.p,False)
  self.assertEqual(fixture.p.save_mod,2)
  self.e.gm.restore('crafted-suppressed')
  self.assertEqual(fixture.p.save_mod,0)
  self.klutz(fixture.p,False)
  self.assertEqual(fixture.p.save_mod,2)
  self.e.advance_time(1,self.e.everyone)
  self.assertEqual(fixture.p.save_mod,2)


if __name__=='__main__':unittest.main()
