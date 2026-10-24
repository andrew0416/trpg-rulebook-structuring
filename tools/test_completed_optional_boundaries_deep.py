"""Original optional clauses at their actual native damage and time consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest
import test_category2_optional_state_effect_eight as _fixture_test_category2_optional_state_effect_eight
import test_category2_optional_catalog_nine as _fixture_test_category2_optional_catalog_nine
import optional_state_effect_contracts as STATE
import optional_physical_equipment as OPTIONAL
import effects_ext as EXT
import items as ITEMS
import weapon_actions as WEAPONS
import life as LIFE


class StateBoundaryTests(_fixture_test_category2_optional_state_effect_eight.OptionalStateEffectEightTests):
 def test_public_validation_without_optional_state_remains_read_only(self):
  e,owner,a,b,foe=self.fixture(None)
  before=e.export_state()
  self.assertTrue(e.validate_state()['valid'])
  self.assertEqual(e.export_state(),before)
  self.assertFalse(any(STATE.STATE in c.spec for c in e.everyone))

 def test_one_round_common_clock_rejects_changed_source_value_and_deadline_on_restore(self):
  import combat_timing as CLOCK
  from state_codec import StateCodecError
  e,owner,a,b,foe=self.fixture('feat/응원-문구-1')
  e.activate_optional_state_effect(owner,'ERRATA-056',choice='evasion')
  record=next(row for row in CLOCK.records(a) if row.get('optional_clause_id')=='ERRATA-056')
  before=deepcopy(record)
  for change in (lambda r:r.update(evasion_modifier=3),lambda r:r.update(count_deadline=(e.round_no+1,30)),
                 lambda r:r.update(source='feat/시야-아래-조준')):
   change(record);self.assertFalse(e.validate_state()['valid'])
   with self.assertRaises(StateCodecError):e.export_state()
   record.clear();record.update(deepcopy(before))
  self.assertTrue(e.validate_state()['valid'])

 def test_evasion_cheer_uses_exact_full_round_count_not_changed_owner_initiative(self):
  e,owner,a,b,foe=self.fixture('feat/응원-문구-1')
  baseline=a.evasion('물리')
  e.activate_optional_state_effect(owner,'ERRATA-056',choice='evasion')
  self.assertEqual(a.evasion('물리'),min(9,baseline+2))
  e.end_of_turn(owner);e.end_round();e.start_round(e.everyone)
  # A changed owner initiative is not the application count of one full round.
  e.start_of_turn(owner,initiative_count=30)
  self.assertEqual(a.evasion('물리'),min(9,baseline+2))
  e.end_of_turn(owner);e.start_of_turn(foe,initiative_count=21)
  self.assertEqual(a.evasion('물리'),min(9,baseline+2))
  e.end_of_turn(foe)
  from engine import Engine
  loaded=Engine.import_state(e.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
  restored_a=next(c for c in loaded.everyone if c.entity_id==a.entity_id)
  loaded.start_of_turn(restored_a,initiative_count=20)
  self.assertEqual(restored_a.evasion('물리'),baseline)
  loaded.end_of_turn(restored_a)
  self.assertTrue(loaded.validate_state()['valid'])

 def test_three_round_gifts_reach_native_round_end_and_survive_restore(self):
  from engine import Engine
  cases=[('SB-099','feat/메이저-기프트-거신의-행진'),
         ('SB-107','feat/레시라무의-메이저-기프트-하얀-양'),
         ('SB-110','feat/제크로무의-메이저-기프트-검은-음')]
  for clause,feature in cases:
   with self.subTest(clause=clause):
    e,owner,a,b,_=self.fixture(feature)
    atk=a.staged('atk');speed=a.staged('spe');ev=a.evasion('물리')
    if clause=='SB-099':e.activate_optional_state_effect(owner,clause,target=a)
    else:e.activate_optional_state_effect(owner,clause,targets=(a,b))
    for number in range(3):
     if clause=='SB-099':self.assertEqual((a.staged('atk'),a.staged('spe')),(atk//2,speed//2))
     elif clause=='SB-107':
      self.assertEqual(EXT.movement_profile(e,a,4,0)[0],6)
      self.assertGreater(a.staged('atk'),atk)
      self.assertEqual(__import__('combat_modifiers').accuracy_stage(a),-2)
     else:
      self.assertEqual(EXT.movement_profile(e,a,8,0)[0],1)
      self.assertEqual(a.evasion('물리'),min(9,ev+2))
     if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
     e.end_round()
     if number<2:
      self.assertTrue(STATE.records(a))
      e=Engine.import_state(e.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
      owner=next(c for c in e.everyone if c.entity_id==owner.entity_id)
      a=next(c for c in e.everyone if c.entity_id==a.entity_id)
      e.start_round(e.everyone);e.start_of_turn(owner,initiative_count=20)
    if clause!='SB-099':
     self.assertTrue(STATE.records(a))
     e.start_round(e.everyone)
     e.at_initiative_count(21)
     self.assertTrue(STATE.records(a))
     e.at_initiative_count(20)
    self.assertFalse(STATE.records(a))
    if clause=='SB-099':self.assertEqual((a.stages['atk'],a.stages['spe']),(2,2))
    elif clause=='SB-107':
     self.assertEqual(a.staged('atk'),atk);self.assertEqual(EXT.movement_profile(e,a,4,0)[0],4)
    else:self.assertEqual(a.evasion('물리'),ev);self.assertEqual(EXT.movement_profile(e,a,8,0)[0],8)
    self.assertTrue(e.validate_state()['valid'])


class CatalogConsumerTests(_fixture_test_category2_optional_catalog_nine.OptionalCatalogNineTests):
 def test_yata_actual_target_observation_loses_mirror_reflection_on_source_withdrawal(self):
  import state_grants as G
  e,a,_,foe=self.fixture();uid=self.equip(e,a,'crafted_item/야타의-거울','native-yata')
  G.grant(a,'capabilities','Blindsense','test:actual-native-sense','actual owned observation route')
  declaration=json.loads((Path(self.r.root)/'data/examples/perception-observe.json').read_text(encoding='utf-8'))[0]
  foe.spec['disguise']='actual observed disguise';foe.custom_conditions['transformed']={'source':'test:actual-transformation'}
  e.gm.observe_sensory_environment(a,foe,paths={'spatial':True},medium='air',present=True,reason='actual target observation path')
  seen=e.observe_target(a,foe,declaration)
  self.assertEqual(seen['status'],'observed');self.assertEqual(seen['values'],{'presence':True})
  self.assertEqual(seen['yata_reflection'],{'target_id':foe.entity_id,'disguised':True,'transformed':True})
  self.assertTrue(seen['illusion_immunity'])
  ITEMS.unregister_item(e,a,registration_key=self.registration_key(a,uid))
  seen=e.observe_target(a,foe,declaration)
  self.assertNotIn('yata_reflection',seen);self.assertNotIn('illusion_immunity',seen)

 def test_actual_damage_creates_blood_healing_and_kaladanda_awakening_lifetime(self):
  e,a,_,foe=self.fixture();uid=self.equip(e,a,'crafted_item/피의-낫','native-blood')
  a.hp-=40;move=WEAPONS.prepare(e,a,self.r.move('move/베어가르기'),uid)
  observed={};before=foe.hp
  e.resolve_attack_damage(a,foe,move,_damage_observation=observed)
  loss=before-foe.hp;self.assertGreater(loss,0);self.assertEqual(observed['net_hp_loss'],loss)
  self.assertEqual(a.custom_conditions['blood_scythe_healing']['damage'],loss)
  hp=a.hp;out=OPTIONAL.claim_blood_scythe_healing(e,a)
  self.assertEqual(out['eligible_damage'],loss);self.assertEqual(a.hp-hp,min(loss//2,a.max_hp-hp))
  ITEMS.unregister_item(e,a,registration_key=self.registration_key(a,uid))
  with self.assertRaises(ValueError):OPTIONAL.claim_blood_scythe_healing(e,a)
  e,a,_,foe=self.fixture();uid=self.equip(e,a,'crafted_item/카라단다','native-kaladanda')
  move=WEAPONS.prepare(e,a,self.r.move('move/섀도클로'),uid)
  # A real incoming hit crosses zero; no fabricated damage receipt or faint flag.
  foe.hp=1;observed={};e.resolve_attack_damage(a,foe,move,_damage_observation=observed)
  self.assertGreater(observed['net_hp_loss'],0);self.assertIn('기절',foe.conditions)
  self.assertEqual(foe.custom_conditions[OPTIONAL.NO_AWAKENING]['move_id'],'move/섀도클로')
  e.heal(foe,foe.max_hp+abs(foe.hp),source_kind='feature');self.assertIn('기절',foe.conditions)
  self.assertFalse(LIFE.revive(e,foe,10))
  e=self.restored(e);foe=next(c for c in e.everyone if c.entity_id==foe.entity_id)
  remaining=foe.custom_conditions[OPTIONAL.NO_AWAKENING]['until']-e.elapsed_seconds
  e.advance_time(remaining-1,(foe,));self.assertIn('기절',foe.conditions)
  self.assertFalse(LIFE.revive(e,foe,10))
  e.advance_time(1,(foe,));self.assertNotIn('기절',foe.conditions)
  self.assertNotIn(OPTIONAL.NO_AWAKENING,foe.custom_conditions)

 def test_native_damage_formula_consumes_exact_weapon_profiles_and_svalinn_source(self):
  cases=[('crafted_item/나인플레임의-스태프','move/불꽃튀기기',['노말'],1.0,'특수'),
         ('crafted_item/요정의-엉덩이-차는-거친-불검','move/베어가르기',['페어리'],1.5,'물리'),
         ('crafted_item/캔디-해머',None,['고스트'],1.0,'물리'),
         ('crafted_item/카오스-던커','move/지진',['비행'],1.0,'물리')]
  for index,(item,mid,types,expected,cls) in enumerate(cases):
   with self.subTest(item=item):
    e,a,_,foe=self.fixture();uid=self.equip(e,a,item,'native-profile-'+str(index))
    if mid is None:mid=next(row['struggle_id'] for row in a.custom_conditions['equipped_weapons'].values() if row['instance_id']==uid)
    move=WEAPONS.prepare(e,a,self.r.move(mid),uid);foe.types=types
    event={};damage=e.roll_damage(a,foe,move,_reaction_event=event)
    self.assertEqual(event['damage_formula']['multiplier'],expected)
    self.assertEqual(move['class'],cls);self.assertGreater(damage,0)
    ITEMS.unregister_item(e,a,registration_key=self.registration_key(a,uid))
    with self.assertRaises(ValueError):WEAPONS.prepare(e,a,self.r.move(mid),uid)
  e,a,ally,foe=self.fixture();uid=self.equip(e,a,'crafted_item/스-발린','native-svalinn')
  e.time_actors(e.everyone);fire=self.r.move('move/불꽃세례');rng=e.rng.getstate()
  protected={};e.roll_damage(foe,ally,fire,_reaction_event=protected)
  self.assertEqual(protected['damage_formula']['multiplier'],0.5)
  self.assertFalse(e.apply_status(a,'화상',source='move/불꽃세례',applied_by=foe))
  ITEMS.unregister_item(e,a,registration_key=self.registration_key(a,uid));e.rng.setstate(rng)
  exposed={};e.roll_damage(foe,ally,fire,_reaction_event=exposed)
  self.assertEqual(exposed['damage_formula']['multiplier'],1.0)
  self.assertGreater(exposed['damage'],protected['damage'])
  self.assertTrue(e.apply_status(a,'화상',source='move/불꽃세례',applied_by=foe))

if __name__=='__main__':unittest.main()
