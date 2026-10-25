"""Entire Coordinator contract: acquisition, observed native Move damage, Contest,
physical Poffins, created Moves, AP, clocks and data-only restore. No ledger credit."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_book_dancer_acquisition as FIX
from engine import Rules,Engine
from contest import ContestRules,ContestEngine
import coordinator as C
import trainer_feature_acquisition as TFA
import state_codec as CODEC
import state_grants as G
import frequency as F
import action_points as AP
import poffin_state as P
import world_entities as W
import move_completion as MC
import combat_precision_features as CPF


class CoordinatorFullTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core');cls.cr=ContestRules(ROOT,ruleset='core')
 add=FIX.DancerAcquisitionTests.add
 combat=FIX.DancerAcquisitionTests.combat
 next_turn=FIX.DancerAcquisitionTests.next_turn
 use=FIX.DancerAcquisitionTests.use
 rejected=FIX.DancerAcquisitionTests.rejected
 valid=FIX.DancerAcquisitionTests.valid
 invalid=FIX.DancerAcquisitionTests.invalid
 restore=FIX.DancerAcquisitionTests.restore
 def setUp(self):
  FIX.DancerAcquisitionTests.setUp(self)
  self.t.spec['edges']=['edge/우아함']
  self.p=self.add('Coordinator Pokemon','pokemon',(2,1),trainer_id=self.t.entity_id,moves=['move/몸통박치기','move/불꽃세례','move/울음소리'],tutor_points=9,speed=25,poffins=['근사함','근사함','아름다움'])
  self.q=self.add('second Pokemon','pokemon',(2,2),trainer_id=self.t.entity_id,moves=['move/몸통박치기','move/불꽃세례'],tutor_points=9,speed=24)
  self.foe=self.add('enemy','pokemon',(3,1),side='enemy',moves=['move/몸통박치기'],tutor_points=9,speed=10)
  self.e.gm.observe_sensory_environment(self.t,self.foe,paths={'auditory':True},present=True,reason='actual unowned Pokemon hears the current Director Order')
 def acquire(self,feature,choice='core_1.05',trainer=None):
  return TFA.acquire_static(self.e,trainer or self.t,feature,selection={'source_contract':choice},acquisition_request_id='coordinator/'+feature+'/'+choice)
 def own(self,*features,choice='core_1.05'):
  self.acquire(C.CLASS,choice)
  for uid in C.FEATURES:
   if uid!=C.CLASS and uid in features:self.acquire(uid,choice)
 def created(self,template=1,stat='근사함',pokemon=None,effect=None):
  p=pokemon or self.p
  out=C.innovate(self.e,self.t,p,name='Created '+str(template)+' '+stat,template=template,contest_type=stat,contest_effect=effect or next(iter(self.cr.mech('contest/effects'))),seconds=60,reason='actual named player creation')
  return out['records'][0]['move_id']
 def before(self):return deepcopy((self.t.spec,self.p.spec,self.e.elapsed_seconds,self.e.rng.getstate()))
 def contest(self):
  ce=ContestEngine(self.cr,seed=432)
  cs=[ce.contestant_from_combatants(self.e,p,self.t,'매력',{'근사함':3,'아름다움':3,'귀여움':3,'슬기로움':3,'강인함':3}) for p in (self.p,self.q)]
  third=self.add('third Pokemon','pokemon',(2,3),trainer_id=self.t.entity_id,moves=['move/몸통박치기','move/불꽃세례'],speed=23)
  cs.append(ce.contestant_from_combatants(self.e,third,self.t,'매력',{'근사함':3,'아름다움':3,'귀여움':3,'슬기로움':3,'강인함':3}))
  return ce,cs

 def test_all_seven_actual_acquisitions_preserve_source_parent_and_no_auto_children(self):
  self.acquire(C.CLASS);self.assertEqual([r['feature_id'] for r in C.records(self.t)],[C.CLASS]);self.assertEqual(C.contract(self.t),'core_1.05')
  for uid in list(C.FEATURES)[1:]:self.acquire(uid)
  self.assertEqual({r['feature_id'] for r in C.records(self.t)},set(C.FEATURES));self.assertEqual(self.t.spec.get('ap_spent',0),0)
  for r in C.records(self.t):self.assertEqual(set(r['snapshot']['parents']),set(C.PARENTS[r['feature_id']]))
  self.valid();self.restore('t','p');self.assertEqual(C.contract(self.t,C.DIRECTOR),'core_1.05')
 def test_novice_adept_expert_master_acquisition_boundaries(self):
  self.t.spec['edges']=[]
  self.rejected(lambda:self.acquire(C.CLASS),'prerequisite')
  self.t.spec['edges']=['edge/우아함'];self.t.spec['skills'].update(dict.fromkeys(__import__('contest_features').SKILLS,2))
  self.rejected(lambda:self.acquire(C.CLASS),'skill')
  self.t.spec['skills']['매력']=3;self.own(C.ADAPTABLE)
  self.rejected(lambda:self.acquire(C.FLEXIBLE),'skill');self.rejected(lambda:self.acquire(C.NUANCED),'skill')
  self.t.spec['skills']['매력']=4;self.acquire(C.FLEXIBLE)
  self.t.spec['skills']['매력']=5;self.acquire(C.NUANCED);self.rejected(lambda:self.acquire(C.RELIABLE),'skill')
  self.t.spec['skills']['매력']=6;self.acquire(C.RELIABLE)
 def test_feature_acquisition_replay_and_changed_source_choice(self):
  a=self.acquire(C.CLASS);self.assertEqual(self.acquire(C.CLASS),a)
  with self.assertRaises(ValueError):TFA.acquire_static(self.e,self.t,C.CLASS,selection={'source_contract':'local_csv'},acquisition_request_id='coordinator/'+C.CLASS+'/core_1.05')
  with self.assertRaises(ValueError):C.source(self.rules,'ptk_literal',C.DIRECTOR)
 def test_actual_core_source_and_selected_parent_guards(self):
  self.own(C.ADAPTABLE)
  original=self.rules._selected_rule
  with patch.object(self.rules,'_selected_rule',side_effect=lambda uid,*a,**kw:'invalid/source' if uid==C.ADAPTABLE else original(uid,*a,**kw)):
   with self.assertRaises(ValueError):C.require(self.e,self.t,C.ADAPTABLE)
  with patch('source_context.verified_source',side_effect=ValueError('changed Core bytes')):
   with self.assertRaisesRegex(ValueError,'changed Core'):C.source(self.rules,'core_1.05')
 def test_acquisition_receipt_source_and_parent_tampering_rejected(self):
  self.own(C.ADAPTABLE);receipt=C.records(self.t,C.ADAPTABLE)[0];receipt['snapshot']['selection']['source_contract']='official_playtest'
  self.invalid('integrity')
 def test_core_director_user_next_turn_end_and_standard_action(self):
  self.own(C.DIRECTOR);self.combat(self.t);base=self.e.initiative_value(self.foe).value
  out=self.e.use_decisive_director(self.t,self.foe,adjustment='increase');self.assertEqual(out['delta'],12);self.assertEqual(out['source'],C.DIRECTOR)
  self.e.end_of_turn(self.t);self.assertEqual(self.e.initiative_value(self.foe).value,base+12)
  self.e.start_of_turn(self.foe,initiative_count=10);self.e.end_of_turn(self.foe);self.assertEqual(self.e.initiative_value(self.foe).value,base+12)
  self.e.end_round();self.combat(self.t);self.e.end_of_turn(self.t);self.assertEqual(self.e.initiative_value(self.foe).value,base)
 def test_core_director_negative_and_restore_preserve_user_clock(self):
  self.own(C.DIRECTOR);self.combat(self.t);base=self.e.initiative_value(self.foe).value
  self.e.use_decisive_director(self.t,self.foe,adjustment='decrease');self.assertEqual(self.e.initiative_value(self.foe).value,base-12)
  self.restore('t','foe');self.assertEqual(self.e.initiative_value(self.foe).value,base-12)
 def test_csv_director_original_target_clock_contract_retained(self):
  self.own(C.DIRECTOR,choice='local_csv');self.combat(self.t);base=self.e.initiative_value(self.foe).value
  out=self.e.use_decisive_director(self.t,self.foe,adjustment='increase');self.assertEqual(out['source'],__import__('directive_features').SOURCE)
  self.e.end_of_turn(self.t);self.e.start_of_turn(self.foe,initiative_count=10);self.e.end_of_turn(self.foe);self.assertEqual(self.e.initiative_value(self.foe).value,base)
 def test_director_unowned_pokemon_allowed_trainer_target_rejected(self):
  self.own(C.DIRECTOR);self.combat(self.t);self.rejected(lambda:self.e.use_decisive_director(self.t,self.t,adjustment='increase'),'Pokemon')
  self.e.use_decisive_director(self.t,self.foe,adjustment='increase')
 def test_first_damage_roll_observed_before_hp_and_whole_pool_rerolled(self):
  self.own();seen=[];hp=self.foe.hp
  C.arm_damage(self.e,self.t,self.p,decision=lambda row:seen.append((row,self.foe.hp)) or True)
  self.combat(self.p,count=25);self.use(self.p,self.foe,'move/몸통박치기',face=12)
  self.assertEqual(len(seen),1);self.assertEqual(seen[0][1],hp);self.assertGreater(len(seen[0][0]['pools']),0)
  ev=next(ev for ev in self.e._passive_events.values() if 'coordinator_damage' in ev);row=ev['coordinator_damage']
  self.assertTrue(row['decision']);self.assertEqual(len(row['pools']),len(row['rerolled_pools']));self.assertEqual(hp-self.foe.hp,row['chosen_damage'])
  self.assertEqual(self.p.move_uses['move/몸통박치기'],1);self.assertEqual(self.t._action_history.count('free'),1);self.valid()
 def test_completed_damage_choice_result_tampering_fails_codec(self):
  self.own();C.arm_damage(self.e,self.t,self.p,decision=lambda row:True);self.combat(self.p,count=25);self.use(self.p,self.foe,'move/몸통박치기',face=12)
  ev=next(ev for ev in self.e._passive_events.values() if 'coordinator_damage' in ev);ev['coordinator_damage']['chosen_damage']+=1
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
 def test_damage_decline_costs_nothing_and_same_pokemon_can_accept_later(self):
  self.own();C.arm_damage(self.e,self.t,self.p,decision=lambda row:False);self.combat(self.p,count=25);self.use(self.p,self.foe,'move/몸통박치기',face=12)
  self.assertNotIn('free',getattr(self.t,'_action_history',[]));C.arm_damage(self.e,self.t,self.p,decision=lambda row:True)
 def test_core_damage_scene_quota_is_per_pokemon_and_scene_reset(self):
  self.own();C.arm_damage(self.e,self.t,self.p,decision=lambda row:True);self.combat(self.p,count=25);self.use(self.p,self.foe,'move/몸통박치기',face=12)
  with self.assertRaises(ValueError):C.arm_damage(self.e,self.t,self.p,decision=lambda row:True)
  C.arm_damage(self.e,self.t,self.q,decision=lambda row:True)
  self.e.end_of_turn(self.p);self.e.end_round();self.e.end_scene();C.arm_damage(self.e,self.t,self.p,decision=lambda row:True)
 def test_local_csv_damage_scene_quota_remains_trainer_wide(self):
  self.own(choice='local_csv');C.arm_damage(self.e,self.t,self.p,decision=lambda row:True);self.combat(self.p,count=25);self.use(self.p,self.foe,'move/몸통박치기',face=12)
  with self.assertRaises(ValueError):C.arm_damage(self.e,self.t,self.q,decision=lambda row:True)
 def test_pending_damage_roundtrip_resumes_same_move_without_repayment_or_second_hp(self):
  import passive_events as PASSIVE
  self.own();seen=[]
  def pause(row):seen.append(deepcopy(row));raise ValueError('player paused after observation')
  C.arm_damage(self.e,self.t,self.p,decision=pause);self.combat(self.p,count=25);hp=self.foe.hp
  with self.assertRaises(PASSIVE.PassiveEventPending):self.use(self.p,self.foe,'move/몸통박치기',face=12)
  self.assertEqual(self.foe.hp,hp);self.assertEqual(self.p.move_uses['move/몸통박치기'],1)
  self.restore('t','p','foe');self.assertEqual(self.foe.hp,hp)
  C.restore_damage_choice(self.e,self.t,decision=lambda row:self.assertEqual(row,seen[0]) or True)
  self.assertLess(self.foe.hp,hp);self.assertEqual(self.p.move_uses['move/몸통박치기'],1);self.assertEqual(self.t._action_history.count('free'),1);self.valid()
 def test_damage_observed_free_action_failure_keeps_first_roll_pending(self):
  import passive_events as PASSIVE
  self.own();seen=[];C.arm_damage(self.e,self.t,self.p,decision=lambda row:seen.append(deepcopy(row)) or True);self.combat(self.p,count=25);hp=self.foe.hp
  with patch('contest_features.trigger_free_action',side_effect=ValueError('actual triggered Free Action unavailable')):
   with self.assertRaises(PASSIVE.PassiveEventPending):self.use(self.p,self.foe,'move/몸통박치기',face=12)
  self.assertEqual(self.foe.hp,hp);self.assertEqual(self.p.move_uses['move/몸통박치기'],1);self.assertFalse(getattr(self.t,'_action_history',[]))
  C.restore_damage_choice(self.e,self.t,decision=lambda row:self.assertEqual(row,seen[0]) or False)
  self.assertEqual(hp-self.foe.hp,seen[0]['first_damage']);self.assertEqual(self.p.move_uses['move/몸통박치기'],1)
 def test_commander_strike_parent_cursor_survives_actual_coordinator_damage_pending(self):
  import commander as COMMANDER,commander_orders as ORDERS,passive_events as PASSIVE
  self.own();TFA.acquire_static(self.e,self.t,COMMANDER.CLASS,branch='feat/유린-지시',acquisition_request_id='coordinator/actual-commander-parent')
  self.e.gm.observe_sensory_environment(self.t,self.p,paths={'auditory':True},present=True,reason='actual immediate Order hearing')
  C.arm_damage(self.e,self.t,self.p,decision=lambda first:'waiting player');self.combat(self.t);hp=self.foe.hp;pokemon_budget=deepcopy(getattr(self.p,'budget',None))
  with patch.object(Engine,'d20',return_value=12):
   with self.assertRaises(PASSIVE.PassiveEventPending):self.e.issue_orders(self.t,ORDERS.STRIKE,self.p,options={'attack':{'move':'move/몸통박치기','target_id':self.foe.entity_id}})
  parent=self.e._commander_order_scope;self.assertEqual(parent['cursor'],0);self.assertIsNotNone(parent['waiting_use']);self.assertTrue(parent['paid'])
  self.assertEqual(self.foe.hp,hp);self.assertEqual(self.t.budget['standard'],0);self.assertEqual(self.p.move_uses['move/몸통박치기'],1)
  self.restore('t','p','foe');C.restore_damage_choice(self.e,self.t,decision=lambda first:True)
  self.assertIsNone(self.e._commander_order_scope);self.assertLess(self.foe.hp,hp);self.assertEqual(self.t.budget['standard'],0)
  self.assertEqual(getattr(self.p,'budget',None),pokemon_budget);self.assertEqual(self.p.move_uses['move/몸통박치기'],1);self.assertEqual(self.t._action_history.count('free'),1)
  self.assertEqual(self.t.spec[ORDERS.USES][0]['phase'],'complete');self.valid()
 def test_damage_observation_tampering_and_changed_parent_move_fail(self):
  import passive_events as PASSIVE
  self.own();C.arm_damage(self.e,self.t,self.p,decision=lambda row:'undecided');self.combat(self.p,count=25)
  with self.assertRaises(PASSIVE.PassiveEventPending):self.use(self.p,self.foe,'move/몸통박치기',face=12)
  ev=self.e._passive_events[self.e._passive_pending];ev['coordinator_damage']['pools'][0]['faces'][0]=99
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
 def test_damage_wrong_owner_set_damage_and_simultaneous_provider_rejected(self):
  self.own();self.rejected(lambda:C.arm_damage(self.e,self.t,self.foe,decision=lambda row:True),'own')
  C.arm_damage(self.e,self.t,self.p,decision=lambda row:True);self.combat(self.p,count=25)
  self.rejected(lambda:self.use(self.p,self.foe,'move/몸통박치기',face=12,set_damage=True),'Set Damage')
 def test_class_appeal_actual_observation_once_contest_and_no_ap(self):
  self.own();ce,cs=self.contest();seen=[]
  ce.perform(cs[0],'move/몸통박치기','근사함',[],False,reroll_decision=lambda row:seen.append(row) or True)
  self.assertEqual(len(seen),1);self.assertEqual(len(ce._coordinator_used),1);self.assertEqual(self.t.spec.get('ap_spent',0),0)
  with self.assertRaises(ValueError):ce.perform(cs[1],'move/몸통박치기','근사함',[],False,reroll_decision=lambda row:True)
 def test_adaptable_real_contest_mixes_known_type_effect_and_locks_only_two_next_round(self):
  self.own(C.ADAPTABLE);ce,cs=self.contest();observed=[]
  def choose(c,rnd,adj,center):
   if c is cs[0] and rnd==1:return 'move/몸통박치기',0,{'adaptable':['move/몸통박치기','move/불꽃세례']}
   if c is cs[0] and rnd==2:
    with self.assertRaisesRegex(ValueError,'next-round'):C.contest_preflight(ce,c,'move/몸통박치기')
    with self.assertRaisesRegex(ValueError,'next-round'):C.contest_preflight(ce,c,'move/불꽃세례')
    C.contest_preflight(ce,c,'move/울음소리');observed.append(True);return 'move/울음소리',0
   return 'move/불꽃세례' if rnd%2 else 'move/몸통박치기',0
  ce.run(cs,'근사함',choose,contest_id='actual Coordinator Contest')
  self.assertEqual(observed,[True]);self.assertEqual(len(ce._adaptable_uses),1);self.assertEqual(self.t._action_history.count('free'),1)
  mixed=ce._adaptable_plan['move_id'];self.assertEqual(self.cr.move_contest(mixed),(self.cr.move_contest('move/몸통박치기')[0],self.cr.move_contest('move/불꽃세례')[1]))
 def test_csv_adaptable_actual_next_round_forbids_all_moves_and_skips_performance(self):
  self.own(C.ADAPTABLE,choice='local_csv');ce,cs=self.contest();blocked=[]
  def choose(c,rnd,adj,center):
   if c is cs[0] and rnd==1:return 'move/몸통박치기',0,{'adaptable':['move/몸통박치기','move/불꽃세례']}
   if c is cs[0] and rnd==2:
    for mid in ('move/몸통박치기','move/불꽃세례','move/울음소리'):
     with self.assertRaisesRegex(ValueError,'next-round'):C.contest_preflight(ce,c,mid)
    blocked.append(c.last_move);return 'move/울음소리',0
   return 'move/불꽃세례' if rnd%2 else 'move/몸통박치기',0
  ce.run(cs,'근사함',choose,contest_id='local CSV92 actual skip')
  self.assertEqual(len(blocked),1);self.assertEqual(ce._adaptable_uses[self.t.entity_id]['skipped_round'],1)
  self.assertTrue(any('공연 없음' in line for line in ce.log_lines))
 def test_adaptable_requires_actual_contest_known_moves_and_ownership(self):
  self.own(C.ADAPTABLE);ce,cs=self.contest()
  with self.assertRaises(ValueError):ce.perform(cs[0],'move/몸통박치기','근사함',[],False,adaptable=['move/몸통박치기','move/불꽃세례'])
  self.assertFalse(ce._adaptable_uses)
 def test_flexible_reallocates_two_poffin_units_preserves_physical_history_and_day_expiry(self):
  self.own(C.ADAPTABLE,C.FLEXIBLE);physical=deepcopy(self.p.spec['poffins']);old=P.available(self.p,engine=self.e)
  C.flexible(self.e,self.t,self.p,from_stat='근사함',to_stat='귀여움',dice=2,seconds=60,reason='actual performance preparation')
  new=P.available(self.p,engine=self.e);self.assertEqual(self.p.spec['poffins'],physical);self.assertEqual(len(new),len(old));self.assertEqual(new.count('귀여움'),2)
  self.restore('t','p');self.assertEqual(P.available(self.p,engine=self.e).count('귀여움'),2)
  F.new_day(self.p);self.assertEqual(P.available(self.p,engine=self.e),tuple(physical))
 def test_flexible_current_owner_grace_transfer_preserves_eight_physical_records(self):
  self.own(C.ADAPTABLE,C.FLEXIBLE);self.p.spec['poffins']=['근사함']*6+['아름다움']*2
  C.flexible(self.e,self.t,self.p,from_stat='아름다움',to_stat='귀여움',dice=2,seconds=60,reason='actual last two Grace dice')
  self.assertEqual(P.available(self.p,engine=self.e).count('귀여움'),2)
  receiver=self.add('new owner','trainer',(8,8),speed=9,edges=[],feats=[],classes=[],moves=[])
  self.p.spec['trainer_id']=receiver.entity_id;self.assertEqual(P.available(self.p,engine=self.e),('근사함',)*6);self.assertEqual(len(self.p.spec['poffins']),8)
 def test_adaptable_observed_pause_and_data_only_restore_keep_two_actual_constituents(self):
  import observed_resolution as OBS
  self.own(C.ADAPTABLE);ce,cs=self.contest();paused=[]
  def choose(c,rnd,adj,center):
   if c is cs[0] and rnd==1:return 'move/몸통박치기',0,{'adaptable':['move/불꽃세례','move/몸통박치기'],'reroll_decision':lambda first:'wait'}
   return 'move/불꽃세례' if rnd%2 else 'move/몸통박치기',0
  with self.assertRaises(ValueError):ce.run(cs,'근사함',choose,contest_id='observed mixed performance')
  self.assertEqual(len(ce._adaptable_uses),1);before=self.t._action_history.count('free')
  payload=CODEC.dump_contest(ce,cs);ce,cs=CODEC.load_contest(self.cr,json.loads(json.dumps(payload,ensure_ascii=False)),native_rules=self.rules)
  def resume(c,rnd,adj,center):
   if c is cs[0] and rnd==1:return 'move/몸통박치기',0,{'adaptable':['move/불꽃세례','move/몸통박치기'],'reroll_decision':lambda first:False}
   if c is cs[0] and rnd==2:return 'move/울음소리',0
   return 'move/불꽃세례' if rnd%2 else 'move/몸통박치기',0
  ce.run(cs,'근사함',resume,contest_id='observed mixed performance');self.assertEqual(len(ce._adaptable_uses),1)
  owner=ce._native_intro_bindings[cs[0]][2];self.assertEqual(owner._action_history.count('free'),before)
 def test_flexible_any_pokemon_current_owner_grace_and_style_independent(self):
  self.own(C.ADAPTABLE,C.FLEXIBLE);self.foe.spec['poffins']=['아름다움']*2
  C.flexible(self.e,self.t,self.foe,from_stat='아름다움',to_stat='강인함',dice=2,seconds=60,reason='prepare consenting other Pokemon')
  self.assertEqual(P.available(self.foe,engine=self.e),('강인함','강인함'))
 def test_flexible_adept_daily_extended_and_single_source_stat_validation(self):
  self.own(C.ADAPTABLE,C.FLEXIBLE)
  for n in (0,3):self.rejected(lambda:C.flexible(self.e,self.t,self.p,from_stat='근사함',to_stat='귀여움',dice=n,seconds=60,reason='real'),'reallocated')
  C.flexible(self.e,self.t,self.p,from_stat='근사함',to_stat='귀여움',dice=1,seconds=60,reason='real')
  self.rejected(lambda:C.flexible(self.e,self.t,self.q,from_stat='근사함',to_stat='귀여움',dice=1,seconds=60,reason='real'),'Poffin|Daily')
 def test_innovation_four_templates_five_types_and_all_22_selected_contest_effects(self):
  self.own(C.ADAPTABLE,C.INNOVATION);effects=self.cr.mech('contest/effects');self.assertEqual(len(effects),22)
  effect=next(iter(effects))
  for template in range(1,5):
   for stat in C.STATS:
    row={'trainer_id':self.t.entity_id,'name':'Immutable Move','template':template,'contest_type':stat,'contest_effect':effect,'source_contract':'core_1.05'}
    mid=C._encode(C.PREFIX,row);self.assertEqual(C.innovation_instance(self.rules,mid),row)
    self.assertEqual(self.cr.move_contest(mid),(stat,effect));self.assertEqual(self.rules.move(mid)['type'],'노말')
    mm,_=self.rules.move_mech(mid)
    if template in (2,4):self.assertEqual(mm['effects_exec'][0]['stat'],C.STATS[stat])
  for effect in effects:
   row={'trainer_id':self.t.entity_id,'name':'Effect choice','template':1,'contest_type':'근사함','contest_effect':effect,'source_contract':'core_1.05'}
   self.assertEqual(self.cr.move_contest(C._encode(C.PREFIX,row)),('근사함',effect))

 def test_innovation_permanent_learning_tp1_no_ownership_limit_and_restore(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created(pokemon=self.foe);self.assertIn(mid,self.foe.moves);self.assertEqual(self.foe.spec['tutor_points'],8)
  rec=self.foe.spec['move_learning'][mid];self.assertEqual((rec['teacher_id'],rec['paid_tp'],rec['lifetime']),(self.t.entity_id,1,'permanent'))
  self.restore('t','foe');self.assertIn(mid,self.foe.moves);self.assertEqual(self.rules.move(mid)['name'],'Created 1 근사함')
 def test_actual_created_move_reaches_existing_contest_performance_consumer(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created(template=2,stat='귀여움');ce,cs=self.contest()
  self.assertIn(mid,cs[0].moves);ce.perform(cs[0],mid,'귀여움',[],False)
  self.assertEqual(cs[0].last_move,mid);self.assertTrue(ce.log_lines);self.assertEqual(self.cr.move_contest(mid)[0],'귀여움')
 def test_innovation_one_at_time_slots_daily_extended_and_forged_learning(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created()
  self.rejected(lambda:self.created(template=2),'already knows')
  self.p.spec['move_learning'][mid]['paid_tp']=0
  with self.assertRaises(ValueError):__import__('move_state').validate_spec(self.rules,self.p.spec)
 def test_innovation_slot_limit_and_explicit_forgetting_allows_later_creation(self):
  import move_state as MOVES,pokemon_teaching as TEACH
  self.own(C.ADAPTABLE,C.INNOVATION);self.p.spec['moves']=['move/할퀴기','move/불꽃세례','move/울음소리','move/몸통박치기','move/연속자르기','move/헤롱헤롱']
  G.set_baseline(self.p,'moves',list(self.p.spec['moves']))
  self.rejected(lambda:self.created(),'six|6|slot|공간|maximum|limit|capacity')
  self.e.gm.set_move(self.p,'move/헤롱헤롱',add=False,reason='explicit actual forgetting frees one slot')
  mid=self.created();self.e.gm.set_move(self.p,mid,add=False,reason='explicitly forget the created Move');F.new_day(self.t);F.new_day(self.p)
  replacement=self.created(template=2);self.assertNotIn(mid,self.p.moves);self.assertIn(replacement,self.p.moves)
 def test_innovation_no_tutor_point_failure_preserves_daily_action_and_time(self):
  self.own(C.ADAPTABLE,C.INNOVATION);self.p.spec['tutor_points']=0
  self.rejected(lambda:self.created(),'Tutor Point');self.assertFalse(getattr(self.t,'_action_history',[]))
 def test_innovation_boon_producer_three_swift_own_turn_and_scene_use(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created();self.combat(self.p,count=25);self.use(self.p,self.p,mid)
  self.assertEqual(self.p.spec['innovation_boons'][0]['remaining'],3)
  C.spend_boon(self.e,self.p,move_id=mid,attack_move='move/몸통박치기');self.assertEqual(self.p.spec['innovation_boons'][0]['remaining'],2);self.assertEqual(self.p.budget['swift'],0)
  self.assertEqual(C.attack_boon(self.p,self.rules.move('move/몸통박치기'),'근사함'),3)
  self.use(self.p,self.foe,'move/몸통박치기',face=17) if self.p.budget['standard'] else None
 def test_beauty_boon_effect_range_three_preserves_actual_natural(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created(stat='아름다움');self.combat(self.p,count=25);self.use(self.p,self.p,mid);self.next_turn(self.p,count=25)
  move=self.rules.move('move/불꽃세례');base=CPF.effect_natural(self.e,self.p,move,17);C.spend_boon(self.e,self.p,move_id=mid,attack_move=move['id'])
  self.assertEqual(CPF.effect_natural(self.e,self.p,move,17),base+3)
  hit,natural,crit=self.e.accuracy_check(self.p,self.foe,move,fixed_roll=1);self.assertFalse(hit);self.assertEqual(natural,1)
 def test_attack_boon_declaration_cannot_follow_observed_native_accuracy(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created(stat='아름다움');self.combat(self.p,count=25);self.use(self.p,self.p,mid);self.next_turn(self.p,count=25)
  def decide(first):
   with self.assertRaisesRegex(ValueError,'precede actual accuracy'):C.spend_boon(self.e,self.p,move_id=mid,attack_move='move/몸통박치기')
   return False
  C.arm_damage(self.e,self.t,self.p,decision=decide);self.use(self.p,self.foe,'move/몸통박치기',face=12)
  self.assertEqual(self.p.spec['innovation_boons'][0]['remaining'],3);self.assertEqual(self.p.budget['swift'],1)
 def test_cool_boon_actual_critical_range_and_smart_actual_accuracy(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created();self.combat(self.p,count=25);self.use(self.p,self.p,mid);self.next_turn(self.p,count=25)
  C.spend_boon(self.e,self.p,move_id=mid,attack_move='move/몸통박치기');self.assertTrue(self.e.accuracy_check(self.p,self.foe,self.rules.move('move/몸통박치기'),fixed_roll=17)[2])
 def test_smart_boon_actual_accuracy_plus_three_and_one_attack_cleanup(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created(stat='슬기로움');self.combat(self.p,count=25);self.use(self.p,self.p,mid);self.next_turn(self.p,count=25)
  move=self.rules.move('move/몸통박치기');self.foe.evasion_mod=0
  before=self.e.accuracy_check(self.p,self.foe,move,fixed_roll=4)[0]
  C.spend_boon(self.e,self.p,move_id=mid,attack_move=move['id']);after=self.e.accuracy_check(self.p,self.foe,move,fixed_roll=4)[0]
  self.assertFalse(before);self.assertTrue(after);self.use(self.p,self.foe,move['id'],face=12,set_damage=True);self.assertNotIn('innovation_attack_boon',self.p.spec)
 def test_cute_boon_evasion_full_round_expires_at_matching_count(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created(stat='귀여움');self.combat(self.p,count=25);self.use(self.p,self.p,mid);self.next_turn(self.p,count=25)
  before=self.p.evasion('물리');C.spend_boon(self.e,self.p,move_id=mid);self.assertEqual(self.p.evasion('물리'),before+3)
  self.next_turn(self.p,count=25);self.assertEqual(self.p.evasion('물리'),before)
 def test_tough_boon_prevents_actual_status_weather_recoil_only_that_turn(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created(stat='강인함');self.combat(self.p,count=25);self.use(self.p,self.p,mid)
  self.e.end_of_turn(self.p);self.e.end_round();C.arm_tough_boon(self.e,self.p,mid);hp=self.p.hp;self.combat(self.p,count=25)
  self.assertEqual(self.p.budget['swift'],0)
  self.use(self.p,self.foe,'move/이판사판태클',face=12,set_damage=True);self.assertEqual(self.p.hp,hp)
  for source in ('독','화상','모래바람','recoil'):self.e.lose_hp(self.p,3,source=source)
  self.assertEqual(self.p.hp,hp);self.e.lose_hp(self.p,2,source='ordinary cost');self.assertEqual(self.p.hp,hp-2)
  self.e.end_of_turn(self.p);self.e.lose_hp(self.p,3,source='화상');self.assertEqual(self.p.hp,hp-5)
 def test_template2_cannot_miss_six_range_stat_down_two_and_scene_twice(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created(template=2,stat='슬기로움');self.combat(self.p,count=25)
  with patch.object(Engine,'d20',side_effect=AssertionError('no accuracy roll')):self.e.use_move_on(self.p,self.foe,mid,self.e.everyone)
  self.assertEqual(self.foe.stages['spd'],-2);self.assertEqual(F.move_frequency(self.e,mid,self.p),('scene',2))
 def test_template3_modified_native_struggle_fixed_five_eot_and_surge(self):
  import struggle_capabilities as STRUGGLE,roll_pools as POOLS
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created(template=3,stat='근사함')
  G.set_baseline(self.p,'capabilities',['불쏘시개'])
  self.p.spec['innovation_struggle_choice']={'capability':'불쏘시개','special':True}
  self.combat(self.p,count=25);move=C.prepare(self.e,self.p,self.rules.move(mid))
  self.assertEqual((move['type'],move['class']),('불꽃','특수'));self.assertIn(STRUGGLE.MARKER,move)
  base=STRUGGLE.prepare(self.e,self.p,self.rules.move('struggle'),self.p.spec['innovation_struggle_choice']);ordinary={}
  original_pool=POOLS.expression
  def fixed(rng,expr,**opts):
   count=int(expr.split('d')[0])*opts.get('dice_multiplier',1)
   return original_pool(rng,expr,**dict(opts,fixed=[3]*count))
  with patch.object(POOLS,'expression',side_effect=fixed):
   normal=self.e.roll_damage(self.p,self.foe,base,_reaction_event=ordinary)
   C.arm_damage(self.e,self.t,self.p,decision=lambda first:False)
   self.use(self.p,self.foe,mid,face=18)
  event=next(ev for ev in self.e._passive_events.values() if 'coordinator_damage' in ev);actual=event['coordinator_damage']['reaction_event']
  self.assertEqual(actual['move']['type'],'불꽃');self.assertEqual(actual['move']['class'],'특수')
  self.assertEqual(actual['coordinator_formula']['modifiers'],ordinary['coordinator_formula']['modifiers']+5)
  self.assertEqual(event['coordinator_damage']['first_damage'],normal+5);self.assertEqual(self.p.stages['atk'],1)
  self.assertEqual(F.move_frequency(self.e,mid,self.p),('every_other_turn',1))
  self.next_turn(self.p,count=25);self.assertFalse(F.move_allowed(self.e,self.p,mid)[0]);self.next_turn(self.p,count=25);self.assertTrue(F.move_allowed(self.e,self.p,mid)[0])
 def test_literal_template3_actual_turn_once_and_explicit_up_to_five(self):
  self.own(C.ADAPTABLE,C.INNOVATION,choice='ptk_literal');mid=self.created(template=3)
  self.p.spec['innovation_damage_bonus']=2;self.combat(self.p,count=25);self.use(self.p,self.foe,mid,face=12)
  self.assertEqual(F.move_frequency(self.e,mid,self.p),('turn',1));self.assertFalse(F.move_allowed(self.e,self.p,mid)[0])
  self.next_turn(self.p,count=25);self.assertTrue(F.move_allowed(self.e,self.p,mid)[0]);self.p.spec['innovation_damage_bonus']=5
  self.use(self.p,self.foe,mid,face=12)
  self.p.spec['innovation_damage_bonus']=6
  with self.assertRaises(ValueError):C.damage_bonus(self.e,self.p,self.rules.move(mid))
 def test_template4_native_burst_two_allies_only_excludes_user_and_enemies(self):
  self.own(C.ADAPTABLE,C.INNOVATION);mid=self.created(template=4,stat='귀여움');self.combat(self.p,count=25);self.use(self.p,self.q,mid)
  self.assertEqual(self.q.stages['spe'],1);self.assertEqual(self.t.stages['spe'],1);self.assertEqual(self.p.stages['spe'],0);self.assertEqual(self.foe.stages['spe'],0)
 def test_nuanced_whole_move_miss_ap1_free_restores_only_move_frequency(self):
  self.own(C.ADAPTABLE,C.INNOVATION,C.NUANCED);move=self.created(template=3)
  C.arm_nuanced(self.e,self.t,self.p,decision=lambda first:True);self.combat(self.p,count=25);before=AP.available(self.t);self.use(self.p,self.foe,move,face=1)
  self.assertEqual(AP.available(self.t),before-1);self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.t._action_history.count('free'),1)
  self.assertTrue(F.move_allowed(self.e,self.p,move)[0])
 def test_nuanced_post_miss_idempotent_explicit_decline(self):
  self.own(C.ADAPTABLE,C.INNOVATION,C.NUANCED);mid=self.created(template=3)
  C.arm_nuanced(self.e,self.t,self.p,decision=lambda first:False);self.combat(self.p,count=25);self.use(self.p,self.foe,mid,face=1)
  row=next(r for r in self.e._move_completions.values() if r.get('nuanced'));self.assertFalse(row['nuanced_decided']['accepted']);before=AP.available(self.t)
  C.decide_nuanced(self.e,self.t,row['id'],False);self.assertEqual(AP.available(self.t),before)
  with self.assertRaises(ValueError):C.decide_nuanced(self.e,self.t,row['id'],True)
 def test_nuanced_all_targets_must_miss_no_first_recipient_refund(self):
  self.own(C.NUANCED);mid=next(mid for mid,row in self.rules.moves.items() if F.parse(row.get('frequency'))[0]=='scene' and row.get('class') in ('물리','특수') and '파열' in row.get('range',''))
  self.e.gm.set_move(self.p,mid,reason='actual learned area scene Move');self.q.side='enemy';seen=[]
  C.arm_nuanced(self.e,self.t,self.p,decision=lambda first:seen.append(first) or True);self.combat(self.p,count=25);before=AP.available(self.t)
  self.use(self.p,self.foe,mid,face=1,set_damage=True)
  completion=next(r for r in self.e._move_completions.values() if r.get('nuanced'))
  self.assertGreaterEqual(len(completion['targets']),2);self.assertEqual(len(seen),1);self.assertEqual(AP.available(self.t),before-1)
 def test_nuanced_actual_hit_in_area_preserves_all_frequency_and_ap(self):
  self.own(C.NUANCED);mid=next(mid for mid,row in self.rules.moves.items() if F.parse(row.get('frequency'))[0]=='scene' and row.get('class') in ('물리','특수') and '파열' in row.get('range',''))
  self.e.gm.set_move(self.p,mid,reason='actual learned area scene Move');self.q.side='enemy'
  C.arm_nuanced(self.e,self.t,self.p,decision=lambda first:True);self.combat(self.p,count=25);before=AP.available(self.t)
  self.use(self.p,self.foe,mid,face=12,set_damage=True);self.assertEqual(AP.available(self.t),before);self.assertEqual(self.p.move_uses[mid],1)
 def test_nuanced_daily_exact_frequency_restore_and_ap_failure_preserve_original_move(self):
  self.own(C.NUANCED);mid=next(mid for mid,row in self.rules.moves.items() if F.parse(row.get('frequency'))[0]=='daily' and row.get('class') in ('물리','특수') and type(row.get('ac'))is int and '자신' not in row.get('range','') and '일격' not in row.get('effect',''))
  self.e.gm.set_move(self.p,mid,reason='actual learned Daily attack');C.arm_nuanced(self.e,self.t,self.p,decision=lambda first:True);self.combat(self.p,count=25);before=AP.available(self.t)
  self.use(self.p,self.foe,mid,face=1,set_damage=True);self.assertEqual(self.p.move_uses[mid],0);self.assertEqual(AP.available(self.t),before-1);self.assertEqual(self.p.budget['standard'],0)
 def test_nuanced_execute_activation_failure_cannot_refund_frequency(self):
  self.own(C.NUANCED);mid=next((mid for mid,row in self.rules.moves.items() if '일격' in str(row.get('effect','')) and row.get('class') in ('물리','특수')),None)
  self.assertIsNotNone(mid);self.e.gm.set_move(self.p,mid,reason='actual Execute Move');C.arm_nuanced(self.e,self.t,self.p,decision=lambda first:True);self.combat(self.p,count=25);before=AP.available(self.t)
  self.use(self.p,self.foe,mid,face=1,set_damage=True);self.assertEqual(AP.available(self.t),before)
 def test_nuanced_hit_and_no_frequency_do_not_refund(self):
  self.own(C.NUANCED);C.arm_nuanced(self.e,self.t,self.p,decision=lambda first:True);self.combat(self.p,count=25);before=AP.available(self.t);self.use(self.p,self.foe,'move/몸통박치기',face=12,set_damage=True)
  self.assertEqual(AP.available(self.t),before);self.assertEqual(self.p.move_uses['move/몸통박치기'],1)
 def test_reliable_actual_accuracy_ten_ap2_free_keeps_natural_effect_threshold(self):
  self.own(C.NUANCED,C.RELIABLE);self.combat(self.p,count=25);before=AP.available(self.t)
  self.e.use_move(self.p,self.foe,'move/불꽃세례',reliable_trainer=self.t,set_damage=True)
  self.assertEqual(AP.available(self.t),before-2);self.assertEqual(self.t._action_history.count('free'),1);self.assertNotIn('화상',self.foe.conditions)
 def test_reliable_actual_contest_faces_three_ap2_and_no_random_roll(self):
  self.own(C.NUANCED,C.RELIABLE);ce,cs=self.contest();before=AP.available(self.t)
  with patch.object(ce,'d6',side_effect=AssertionError('Reliable uses fixed threes')):ce.perform(cs[0],'move/몸통박치기','근사함',[],False,reliable_performance=True)
  self.assertEqual(AP.available(self.t),before-2);self.assertEqual(self.t._action_history.count('free'),1)
 def test_reliable_wrong_owner_and_insufficient_ap_reject_before_move_payment(self):
  self.own(C.NUANCED,C.RELIABLE);self.combat(self.p,count=25);self.t.spec['ap_spent']=AP.maximum(self.t)
  self.rejected(lambda:self.e.use_move(self.p,self.foe,'move/몸통박치기',reliable_trainer=self.t),'AP')


if __name__=='__main__':unittest.main()
