"""Keen Eye compositions through actual named producers; source-only revision02.

Fixture modules are imported inside methods, never inherited or recollected.
Only die inputs and pass-through observation of the native hit resolver are mocked.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import importlib
import json
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Combatant
import combat_hit as HIT
import keen_eye as KEEN
import state_codec as CODEC
import world_entities as WORLD


class KeenEyeCompositionTests(unittest.TestCase):
 def fixture(self,module,name,*,setup=True):
  cls=getattr(importlib.import_module(module),name)
  cls.setUpClass();f=cls(methodName='runTest')
  self.addCleanup(f.doCleanups)
  if setup:f.setUp()
  return f

 def keen(self,e,actor):
  e.gm.set_ability(actor,'날카로운눈',reason='actual independently possessed Keen Eye')
  self.assertTrue(KEEN.active(e,actor))

 def observed(self,operation):
  values=[];original=HIT.resolve
  def capture(**options):
   values.append(deepcopy(options));return original(**options)
  with patch.object(HIT,'resolve',capture):result=operation()
  return result,values

 def test_actual_aim_double_shot_retains_plus_two_and_removes_each_minus_two(self):
  import marksman as M,optional_state_effect_contracts as O,action_points as AP
  for keen in (False,True):
   with self.subTest(keen=keen):
    f=self.fixture('test_book_marksman_full','MarksmanFullTests')
    f.scene(features=(M.AIM,M.DOUBLE));f.weapon(moves=());f.combat()
    if keen:self.keen(f.e,f.a)
    M.aim(f.e,f.a);before=AP.available(f.a)
    with patch.object(Engine,'d20',return_value=20):
     result,seen=self.observed(lambda:M.double_shot(f.e,f.a,f.b,f.key))
    self.assertEqual(result,[True,True])
    self.assertEqual([r['modifier'] for r in seen],[2,2] if keen else [0,0])
    self.assertFalse(O.records(f.a,M.AIM))
    self.assertEqual(AP.available(f.a),before-1)
    self.assertEqual(f.a.budget['standard'],0)
    f.restore();self.assertTrue(f.e.validate_state()['valid'])

 def improved_enemy(self,f):
  """Actual second Type Ace and two owned Normal Pokemon, with printed purchases."""
  t=f.add('opposing Normal Ace','trainer',(8,7),side='foe',classes=[],feats=[],exp_bank=100,
          type_link_skills={'노말':'매력'})
  f.e.gm.set_position(f.b,(12,10),reason='original foe leaves the new actual attacker cell')
  f.b=f.add('improved opposing attacker','pokemon',(4,2),side='foe',trainer_id=t.entity_id,types=['노말'])
  partner=f.add('second owned Normal Pokemon','pokemon',(10,9),side='foe',trainer_id=t.entity_id,types=['노말'])
  for actor in (f.b,partner):f.e.gm.observe_loyalty(actor,6,reason='actual willing owned Pokemon')
  f.acquire(branch='노말',actor=t)
  f.acquire('Extra Ordinary','노말',actor=t)
  f.acquire('Simple Improvements','노말',actor=t)
  f.answer('type_ace_choice',True)
  return t

 def test_actual_simple_improvements_keeps_six_against_zephyr_and_face_me(self):
  import type_ace as TA
  for source in ('Zephyr Shield','Face Me Whelp'):
   for keen in (False,True):
    with self.subTest(source=source,keen=keen):
     if source=='Zephyr Shield':
      f=self.fixture('test_book_type_ace_actions','TypeAceActionsTests')
      f.branch('비행','Celerity','Zephyr Shield');self.improved_enemy(f)
      f.combat(f.p);f.special('Zephyr Shield',action='shift')
      target=f.p;move='move/물대포';penalty=1
     else:
      f=self.fixture('test_book_type_ace_reactions','TypeAceReactionTests')
      f.family('격투','Close Quarters Mastery','Face Me Whelp');self.improved_enemy(f)
      f.e.gm.set_position(f.p,(3,2),reason='actual adjacent Fighting marker')
      f.sustain('Close Quarters Mastery');f.native(f.p,f.b,'move/태권당수')
      self.assertIs(TA.marked(f.e,f.b),f.p)
      f.e.gm.set_position(f.q,(5,3),reason='actual adjacent target other than marker')
      target=f.q;move='move/몸통박치기';penalty=3
     if keen:self.keen(f.e,f.b)
     f.e.end_of_turn(f.p);f.e.start_of_turn(f.b,initiative_count=20)
     self.assertEqual(TA.all_rolls(f.b),6)
     f.known(f.b,move)
     result,seen=self.observed(lambda:f.native(f.b,target,move,face=20))
     self.assertTrue(result)
     self.assertEqual([row['modifier'] for row in seen],[6 if keen else 6-penalty])
     actual=f.completed(f.b)['move']
     self.assertEqual(TA.accuracy(f.e,f.b,target,actual,{}),6 if keen else 6-penalty)
     self.assertEqual(TA.damage_bonus(f.e,f.b,target,actual,1),-4)
     self.assertTrue(f.e.validate_state()['valid'])

 def test_actual_kinesis_still_consumes_reaction_but_cannot_reduce_keen_accuracy(self):
  import telekinetic as TK,combat_move_reactions as REACTIONS,move_completion as MC
  import action_resources as RES
  for keen in (False,True):
   with self.subTest(keen=keen):
    f=self.fixture('test_book_telekinetic_full','TelekineticTests')
    f.family(TK.ALPHA);REACTIONS.arm(f.e,f.a,TK.KINESIS,protect=f.c)
    if keen:self.keen(f.e,f.b)
    f.begin(f.b);f.e.gm.set_position(f.b,(4,3),reason='actual adjacent Kinesis attacker')
    f.e.gm.set_stat(f.c,'def',value=40,reason='actual defender whose natural11 hit is changed by Kinesis')
    before=f.c.hp
    with patch.object(Engine,'d20',return_value=11) as die:
     f.e.use_move(f.b,f.c,'move/몸통박치기',set_damage=True)
    original=f.completion(f.b,'move/몸통박치기')
    self.assertEqual(MC.recipient_result(original,f.c)['hit'],keen)
    self.assertEqual(f.c.hp<before,keen)
    self.assertEqual(f.completion(f.a,TK.KINESIS)['phase'],'complete')
    self.assertEqual(f.a.move_uses[TK.KINESIS],1)
    self.assertEqual(RES.pending(f.a),{'standard':1})
    self.assertEqual(die.call_count,1)
    self.assertIsNone(__import__('initiative_interrupts').frame(f.e))
    f.restore();f.valid()

 def test_actual_living_weapon_no_guard_cancellation_preserves_sweet_timer_over_interference(self):
  from builder import build_pokemon
  import telekinetic as TK,native_scenario_fixture as NATIVE
  import combat_timing as TIME,combat_modifiers as MODS
  for keen in (False,True):
   with self.subTest(keen=keen):
    f=self.fixture('test_living_weapon_movement_noguard_source_revision','LivingWeaponMovementNoGuardSourceRevisionTests')
    f.world()
    snack=self.fixture('test_category2_chef_snacks','ChefSnackTests',setup=False);snack.r=f.e.r
    nature=snack.nature('단맛','liked')
    f.e.gm.recall(f.p,reason='replace fixture weapon with actual sweet-preferring Honedge')
    f.p=Combatant(f.e.r,build_pokemon(f.e.r,'단칼빙',40,name='sweet-preferring Living Weapon',nature=nature,
        moves=['move/몸통박치기'],abilities=[],extra={'wild':True,'movement':{'land':2,'power':3},'movement_basis':'current'}))
    f.e.gm.add_combatant(f.p,pos=(3,2),side='party',reason='actual Nature-bearing Living Weapon')
    NATIVE.prepare_body(f.e,f.p,size='소형',offsets=[(0,0)],reason='actual complete replacement weapon body')
    food=snack.feed(f.e,f.p,'item/단맛-과자')
    f.equip('english_no_own_benefit')
    f.e.gm.set_ability(f.p,'노가드 [Playtest]',reason='actual own No Guard cancelled by Living Weapon')
    f.e.gm.set_ability(f.t,TK.INTERFERENCE,reason='actual opposing Core Interference Ability')
    if keen:self.keen(f.e,f.p)
    f.e.gm.set_position(f.t,(4,2),reason='actual Interference source within three metres')
    f.turn(f.t);f.e.activate_ability(f.t,TK.INTERFERENCE,f.t)
    self.assertTrue(any(r.get('telekinetic_interference') and r.get('accuracy_modifier')==-2 for r in TIME.records(f.p)))
    f.turn(f.p)
    consumed=f.e.consume_food_buff(f.p,buff_id=food['buff_id']);self.assertEqual(consumed['accuracy'],4)
    self.assertEqual(f.p.accuracy_stage,3)
    f.restore()
    self.assertEqual(f.modifiers(((f.p,f.t),)),[4 if keen else 2])
    # The retained Ability exists, but its +3 is still excluded by Living Weapon.
    self.assertIn('노가드 [Playtest]',f.p.abilities)
    self.assertEqual(MODS.accuracy_stage(f.p,f.e),6)
    self.assertTrue(f.e.validate_state()['valid'])

 def test_actual_helping_hand_shared_area_replays_mixed_gm_entries_once_per_roll(self):
  from grid import Grid
  import roll_effects as R,native_scenario_fixture as NATIVE
  f=self.fixture('test_category2_roll_components','RollComponentTests')
  f.e.grid=Grid(8,8);self.keen(f.e,f.p)
  issued=f.grant();f.a.pos=(2,1);f.e.start_of_turn(f.p)
  for value in (2,-3):
   f.e.rulings.add_situational('accuracy',value,who=f.p.name,uses=1,
       reason='independent observed accuracy '+str(value),scope='scene')
  NATIVE.assert_rejected_unchanged(f.e,lambda:f.e.accuracy_check(f.p,f.other,f.r.move('move/메가톤펀치'),shared_roll={}),reason_pattern='authority')
  self.assertEqual(len(f.e.rulings.situational),2)
  with patch.object(Engine,'d20',return_value=18):
   result,seen=self.observed(lambda:f.e.use_move_on(f.p,f.other,'move/스피드스타',[f.p,f.other,f.a],set_damage=True))
  self.assertTrue(result)
  self.assertEqual([r['modifier'] for r in seen],[4,4])
  self.assertFalse(f.e.rulings.situational)
  closed=next(r for r in R.closed(f.p) if r['id']==issued['id'])
  accuracy=[a for a in closed['applications'] if a['component']=='accuracy']
  self.assertEqual(len(accuracy),1)
  self.assertEqual(set(accuracy[0]['target_ids']),{f.a.entity_id,f.other.entity_id})
  self.assertEqual(accuracy[0]['amount'],2)
  self.assertEqual(len(closed['applications']),2)
  restored=f.restored();index=WORLD.actor_index(restored)
  restored_record=next(r for r in R.closed(index[f.p.entity_id]) if r['id']==issued['id'])
  self.assertEqual(restored_record['applications'],closed['applications'])
  self.assertTrue(restored.validate_state()['valid'])

 def test_selected_gastro_acid_and_replacement_remove_actual_keen_then_restore(self):
  import ability_transitions as A,effects as FX
  for source,replacement in (('move/위액',None),('move/고민씨','ability/불면'),('move/심플빔','ability/단순')):
   with self.subTest(source=source):
    f=self.fixture('test_category2_ability_transitions','AbilityTransitionTests')
    self.keen(f.e,f.t);original=deepcopy(f.t.spec['abilities'])
    f.select(source,'날카로운눈')
    with patch.object(Engine,'d20',return_value=20):f.use(source)
    self.assertFalse(f.t.abilities_suppressed)
    self.assertFalse(KEEN.active(f.e,f.t))
    self.assertEqual(f.t.spec['abilities'],original)
    self.assertTrue(A.active(f.t,'ability/불요의검'))
    if replacement:self.assertTrue(A.active(f.t,replacement))
    loaded=CODEC.load_engine(f.r,json.loads(json.dumps(CODEC.dump_engine(f.e),ensure_ascii=False)))
    index=WORLD.actor_index(loaded);actor=index[f.t.entity_id];issuer=index[f.a.entity_id]
    self.assertFalse(KEEN.active(loaded,actor))
    before=actor.accuracy_stage
    FX.apply_stage_changes(loaded,issuer,actor,{'acc':-1},source_id='move/모래뿌리기')
    self.assertLess(actor.accuracy_stage,before)
    self.assertTrue(loaded.apply_status(actor,'실명',source='gm/actual-blinding-light',parameters={'cause':'external'}))
    loaded.end_encounter(loaded.everyone)
    self.assertTrue(KEEN.active(loaded,actor))
    self.assertEqual(loaded.immune_to(actor,'실명'),KEEN.SOURCE)
    self.assertTrue(loaded.validate_state()['valid'])

 def test_ride_as_one_keeps_shared_stat_max_but_not_equal_speed_plus_one(self):
  for equal in (False,True):
   with self.subTest(equal=equal):
    f=self.fixture('test_ride_as_one_blind_partner_source_revision','RideAsOneBlindPartnerSourceRevisionTests')
    f.scene()
    if equal:f.e.gm.set_stat(f.a,'spe',25,reason='actual equal rider and mount Speed Stats')
    self.keen(f.e,f.enemy)
    for target in (f.a,f.p):
     self.assertEqual(target.evasion('변화',engine=f.e),6 if equal else 5)
     self.assertEqual(target.evasion('변화',engine=f.e,attacker=f.enemy),5)
    move=f.rules.move('move/몸통박치기')
    _,seen=self.observed(lambda:f.e.accuracy_check(f.enemy,f.a,move,fixed_roll=10))
    self.assertEqual(seen[-1]['evasion'],5)
    payload=json.loads(json.dumps(CODEC.dump_engine(f.e),ensure_ascii=False))
    loaded=CODEC.load_engine(f.rules,payload);index=WORLD.actor_index(loaded)
    self.assertEqual(index[f.a.entity_id].evasion('변화',engine=loaded,attacker=index[f.enemy.entity_id]),5)
    self.assertTrue(loaded.validate_state()['valid'])

 def test_virtual_keen_restores_blind_mount_stat_donor_then_loses_it_at_exact_expiry(self):
  import survivalist_class as SC,trainer_feature_acquisition as ACQUIRE
  import survivalist_features as SURVIVAL,vision_impairment as VISION
  f=self.fixture('test_ride_as_one_blind_partner_source_revision','RideAsOneBlindPartnerSourceRevisionTests')
  mount,rider=f.scene()
  f.e.gm.set_skill(rider,'생존',6,reason='actual Master Survival before acquisition')
  for feature in (SC.CLASS,SC.NATURAL,SC.TRAPPER,SC.GUIDE):
   options={'selection':{'edition':'csv_hb'}} if feature==SC.GUIDE else {}
   ACQUIRE.acquire_static(f.e,rider,feature,acquisition_request_id='mounted-keen/'+feature,**options)
  for actor in (rider,mount):
   SURVIVAL.observe_environment(f.e,actor,terrains=['mountain'],light='normal',reason='actual mountain Guide location')
  f.e.gm.observe_sensory_environment(rider,mount,paths={'auditory':True},present=True,reason='actual audible mounted Order')
  self.assertTrue(f.e.apply_status(mount,'실명',parameters={'cause':'external'}))
  self.assertEqual(rider.evasion('변화',engine=f.e),2)
  f.e.start_round(f.e.everyone);f.e.start_of_turn(rider,initiative_count=20)
  f.e.survivalist_activity(rider,'wilderness_guide',reason='actual HB mountain Guide')
  self.assertEqual(VISION.accuracy_level(f.e,mount),'none')
  self.assertIn('실명',mount.conditions)
  self.assertEqual(rider.evasion('변화',engine=f.e),5)
  self.assertTrue(f.e.apply_status(mount,'완전 실명',parameters={'cause':'external'}))
  self.assertEqual(rider.evasion('변화',engine=f.e),2)
  f.e.cure_status(mount,'완전 실명')
  self.assertEqual(rider.evasion('변화',engine=f.e),5)
  loaded=CODEC.load_engine(f.rules,json.loads(json.dumps(CODEC.dump_engine(f.e),ensure_ascii=False)))
  index=WORLD.actor_index(loaded);r=index[rider.entity_id];m=index[mount.entity_id]
  self.assertEqual(r.evasion('변화',engine=loaded),5)
  loaded.end_of_turn(r);loaded.end_round();loaded.start_round(loaded.everyone)
  loaded.at_initiative_count(21);self.assertEqual(r.evasion('변화',engine=loaded),5)
  loaded.at_initiative_count(20)
  self.assertFalse(KEEN.active(loaded,m));self.assertIn('실명',m.conditions)
  self.assertEqual(r.evasion('변화',engine=loaded),2)
  self.assertEqual(m.evasion('변화',engine=loaded),0)
  self.assertTrue(loaded.validate_state()['valid'])

if __name__=='__main__':unittest.main()
