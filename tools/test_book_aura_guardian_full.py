"""Whole Aura Guardian obligations; source-specific native consumers and boundaries."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from aura_guardian_fixture import AuraScene
from engine import Rules,Engine
import aura_guardian as A
import trainer_feature_acquisition as T
import state_grants as G
import action_points as AP
import combat_timing as TIME
import frequency as F

class AuraGuardianTests(AuraScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def test_six_independent_features_rank_two_stats_and_selected_moves(self):
  initial=dict(self.a.stats);self.acquire(A.CLASS,moves=['move/진공파','move/발경'])
  self.assertEqual(self.a.spec['feats'],[A.CLASS]);self.assertEqual(self.a.stats['atk'],initial['atk']+1)
  self.assertNotIn('move/판별',self.a.moves);self.assertNotIn('파동 감지',G.effective_capabilities(self.a))
  for uid in (A.READER,A.SWORD,A.AMBIENT):self.acquire(uid,stat='spa')
  self.acquire(A.MASTERY,stat='spa',moves=['move/파동탄','move/드레인펀치'])
  self.acquire(A.POWER,rank=1,ability=A.SCRAPPY);self.acquire(A.POWER,rank=2,ability=A.STORM,stat='spa')
  self.assertEqual(len(A.records(self.a,active=True)),7);self.assertEqual(self.a.stats['atk'],initial['atk']+2);self.assertEqual(self.a.stats['spa'],initial['spa']+5)
  self.assertIn('배짱',self.a.abilities);self.assertIn('파동바람',self.a.abilities);self.valid();self.restore();self.valid()
 def test_actual_fighting_element_and_parent_receipts_are_required(self):
  self.setup(element='불꽃');self.reject(lambda:self.acquire(A.CLASS),'Elemental|parent')
  self.setup();self.reject(lambda:self.acquire(A.READER),'parent');self.acquire(A.CLASS)
  self.reject(lambda:self.acquire(A.AMBIENT),'parent')
 def test_expert_and_adept_prerequisites_are_ordinary_rank(self):
  self.setup(rank=3);self.acquire(A.CLASS);self.acquire(A.READER)
  for uid in (A.SWORD,A.AMBIENT,A.MASTERY):self.reject(lambda uid=uid:self.acquire(uid),'rank')
  self.acquire(A.POWER,rank=1);self.reject(lambda:self.acquire(A.POWER,rank=2,ability=A.STORM),'rank')
 def test_exact_two_move_choices_and_stat_tag_reject_atomically(self):
  self.reject(lambda:self.acquire(A.CLASS,moves=['move/판별','move/판별']),'choice')
  self.reject(lambda:self.acquire(A.CLASS,moves=['move/판별','move/물대포']),'choice')
  self.reject(lambda:self.acquire(A.CLASS,stat='def'),'stat tag')
  self.acquire(A.CLASS);self.reject(lambda:self.acquire(A.MASTERY,moves=['move/파동탄','move/발경']),'choice')
 def test_rank_duplicate_skips_and_replay_change_reject(self):
  self.acquire(A.CLASS);self.reject(lambda:self.acquire(A.POWER,rank=2),'next actual rank')
  old=self.acquire(A.POWER,rank=1);self.assertEqual(self.acquire(A.POWER,rank=1),old)
  self.reject(lambda:self.acquire(A.POWER,rank=1,ability=A.STORM),'replay')
  self.reject(lambda:self.acquire(A.POWER,rank=2,ability=A.SCRAPPY),'distinct')
 def test_acquisition_tampering_detects_stat_and_move_projection(self):
  self.acquire(A.CLASS);sid='feature:'+self.a.entity_id+':'+A.CLASS
  self.a.spec['feature_choices'][A.CLASS]=['move/물대포','move/판별']
  self.assertFalse(self.e.validate_state()['valid'])
 def test_reader_novice_scene_capability_native_observation(self):
  self.setup(rank=3);self.family(A.READER);self.begin();before=AP.available(self.a);self.e.activate_aura_reader(self.a)
  self.assertEqual(AP.available(self.a),before-2);self.assertIn('파동 감지',G.effective_capabilities(self.a));self.assertNotIn('파동술',G.effective_capabilities(self.a))
  self.e.gm.observe_aura(self.t,living=True,color='blue',brightness='bright',intentions='help',reason='observed actual aura')
  self.assertEqual(self.e.read_aura(self.a,self.t)['brightness_information']['intentions'],'help')
  self.restore();self.valid();self.e.end_of_turn(self.a);self.e.end_round();self.e.end_scene()
  self.reject(lambda:self.e.read_aura(self.a,self.t),'capability')
 def test_reader_adept_pulse_requires_actual_willingness(self):
  self.setup(rank=4);self.reader();self.e.gm.observe_surface_thought(self.t,'welcome',reason='observed current surface thought')
  self.reject(lambda:self.e.read_aura_thought(self.a,self.t),'willingly')
  self.e.set_aura_openness(self.t,self.a,True,reason='actual consent')
  self.assertEqual(self.e.read_aura_thought(self.a,self.t)['surface_thought'],'welcome')
  result=self.e.project_aura_thought(self.a,self.t,'hello');self.assertEqual(result['text'],'hello');self.valid()
 def test_reader_requires_native_turn_and_pays_one_swift(self):
  self.family(A.READER);self.e.begin_encounter(self.e.everyone);self.reject(lambda:self.e.activate_aura_reader(self.a),'Swift')
  self.begin();self.e.activate_aura_reader(self.a);self.assertEqual(self.a._action_history,['swift']);self.assertEqual(self.a.budget['swift'],0)
 def test_ambient_actual_aura_use_holds_only_one_and_uses_scene_frequency(self):
  held=self.ambient();self.assertIsNotNone(held);self.assertEqual(self.a._action_history,['standard','swift'])
  self.next_round();before=dict(self.a.move_uses);self.use(self.a,self.t,'move/진공파')
  self.assertEqual(A.blessing(self.a)['completion_id'],held['completion_id']);self.assertEqual(self.a.budget['swift'],1)
  self.e.spend_aura_blessing(self.a,'blindsense');self.next_round();self.use(self.a,self.t,'move/진공파')
  self.assertIsNotNone(A.blessing(self.a));self.assertFalse(F.activation_allowed(self.a,A.AMBIENT,{'kind':'scene','uses':2},engine=self.e));self.valid()
 def test_ambient_requires_pulse_and_ignores_non_aura_body_mentions(self):
  self.family(A.AMBIENT);self.begin();self.decision('ambient_aura',True);self.use(self.a,self.t,'move/진공파');self.assertIsNone(A.blessing(self.a))
  self.next_round();self.e.activate_aura_reader(self.a);self.next_round();self.use(self.a,self.t,'move/물대포');self.assertIsNone(A.blessing(self.a));self.assertEqual(self.a.budget['swift'],1)
 def test_core_force_palm_aura_header_is_sourced_and_reaches_ambient(self):
  self.acquire(A.CLASS,moves=['move/발경','move/판별']);self.family(A.AMBIENT);self.reader();self.next_round();self.decision('ambient_aura',True)
  self.assertIn('파동',self.rules.move('move/발경')['range']);self.assertNotIn('파동',self.rules.moves['move/발경']['range'])
  self.use(self.a,self.t,'move/발경',18);self.assertIn('마비',self.t.conditions);self.assertIsNotNone(A.blessing(self.a));self.valid()
 def test_barrier_actual_free_interrupt_self_and_five_metre_ally(self):
  self.ambient();self.e.gm.set_position(self.ally,(7,2),reason='ally five metres away');self.e.spend_aura_blessing(self.a,'barrier',target=self.ally)
  self.assertEqual(__import__('effect_lifetimes').numeric(self.ally,'damage_reduction'),15);self.assertIsNone(A.blessing(self.a));self.assertEqual(self.a._action_history[-1],'free')
  self.restore();self.valid();self.next_round();self.assertEqual(__import__('effect_lifetimes').numeric(self.ally,'damage_reduction'),15)
  self.e.end_of_turn(self.a);self.assertEqual(__import__('effect_lifetimes').numeric(self.ally,'damage_reduction'),0)
 def test_barrier_wrong_side_six_metres_and_invalid_choice_preserve_blessing(self):
  self.ambient();self.reject(lambda:self.e.spend_aura_blessing(self.a,'barrier',target=self.t),'ally')
  self.e.gm.set_position(self.ally,(8,2),reason='ally six metres away');self.reject(lambda:self.e.spend_aura_blessing(self.a,'barrier',target=self.ally),'five')
  self.reject(lambda:self.e.spend_aura_blessing(self.a,'invented'),'printed');self.assertIsNotNone(A.blessing(self.a))
 def test_barrier_uses_effect_rank_virtuoso_not_check_dice(self):
  self.setup(rank=6,extra_edges=['edge/거장'],edge_choices={'edge/거장':['직감']});self.ambient();self.e.spend_aura_blessing(self.a,'barrier')
  self.assertEqual(__import__('skill_modifiers').rank(self.rules,self.a,'직감')[2],6)
  self.assertEqual(__import__('effect_lifetimes').numeric(self.a,'damage_reduction'),24);self.valid()
 def test_blessing_cures_exact_one_volatile_and_preserves_persistent(self):
  self.ambient();self.e.apply_status(self.a,'혼란');self.e.apply_status(self.a,'독')
  self.reject(lambda:self.e.spend_aura_blessing(self.a,'cure',status='독'),'Volatile')
  self.e.spend_aura_blessing(self.a,'cure',status='혼란');self.assertNotIn('혼란',self.a.conditions);self.assertIn('독',self.a.conditions);self.assertIsNone(A.blessing(self.a));self.valid()
 def test_blindsense_native_immunity_and_scene_expiry(self):
  self.ambient();self.e.spend_aura_blessing(self.a,'blindsense')
  self.assertIn('blindsense',__import__('capability_traits').owned(self.a));self.assertFalse(self.e.apply_status(self.a,'실명'))
  self.restore();self.valid();self.e.end_of_turn(self.a);self.e.end_round();self.e.end_scene();self.assertNotIn('blindsense',__import__('capability_traits').owned(self.a))
 def test_blessing_spends_during_actual_foe_damage_and_resumes_original_hit(self):
  self.ambient();self.turn(self.t,20);self.decision('aura_blessing_interrupt',{'choice':'barrier','target_id':self.a.entity_id})
  before=self.a.hp;dealt=self.use(self.t,self.a,'move/몸통박치기');self.assertEqual(before-self.a.hp,dealt);self.assertIsNone(A.blessing(self.a));self.assertEqual(self.t.move_uses['move/몸통박치기'],1)
  self.assertEqual(self.t._action_history,['standard']);self.assertEqual(self.a._action_history[-1],'free');self.valid()
 def test_blessing_origin_tamper_rejected_after_actual_creation(self):
  self.ambient();A.blessing(self.a)['completion_id']='invented';self.assertFalse(self.e.validate_state()['valid'])
 def test_sword_native_damage_uses_both_stats_and_selected_defense(self):
  self.acquire(A.CLASS,moves=['move/발경','move/판별']);self.family(A.SWORD);self.e.gm.set_stat(self.t,'spd',value=25,reason='observed Special Defense')
  self.begin();before=AP.available(self.a);self.decision('sword_of_body_and_soul','특수');dealt=self.use(self.a,self.t,'move/발경')
  expected=__import__('arithmetic_policy').product(max(1,15+self.a.staged('atk')+self.a.staged('spa')-self.t.staged('spd')),1.5)
  self.assertEqual(dealt,expected);self.assertEqual(AP.available(self.a),before-2);self.assertEqual(self.a._action_history,['standard','swift']);self.valid();self.restore();self.valid()
 def test_sword_miss_pays_activation_once_and_nonadjacent_does_not(self):
  self.family(A.SWORD);self.begin();self.decision('sword_of_body_and_soul','물리');before=AP.available(self.a);self.use(self.a,self.t,'move/진공파',1)
  self.assertEqual(AP.available(self.a),before-2);self.next_round();self.e.gm.set_position(self.t,(5,3),reason='actual distant foe');before=AP.available(self.a);self.use(self.a,self.t,'move/진공파');self.assertEqual(AP.available(self.a),before)
 def test_sword_nonclass_move_and_ally_do_not_trigger(self):
  self.family(A.SWORD);self.begin();self.decision('sword_of_body_and_soul','물리');before=AP.available(self.a);self.use(self.a,self.t,'move/물대포');self.assertEqual(AP.available(self.a),before)
  self.next_round();self.e.gm.set_position(self.ally,(3,3),reason='actual adjacent ally');self.use(self.a,self.ally,'move/진공파');self.assertEqual(AP.available(self.a),before)
 def test_sword_invalid_choice_rolls_back_native_action_frequency_and_rng(self):
  self.family(A.SWORD);self.begin();self.decision('sword_of_body_and_soul','invented');self.reject(lambda:self.use(self.a,self.t,'move/진공파'),'Physical')
 def test_reference_aura_sphere_never_misses_and_focus_blast_lowers_stage(self):
  self.family(A.MASTERY,moves=['move/파동탄','move/기합구슬']);self.begin();self.assertGreater(self.use(self.a,self.t,'move/파동탄',1),0)
  self.next_round();self.use(self.a,self.t,'move/기합구슬',18);self.assertEqual(self.t.stages['spd'],-1);self.valid()
 def test_reference_drain_punch_heals_half_actual_damage(self):
  self.family(A.MASTERY,moves=['move/드레인펀치','move/힘껏펀치']);self.e.gm.set_hp(self.a,value=self.a.max_hp//2,reason='actual prior damage');self.begin();before=self.a.hp;dealt=self.use(self.a,self.t,'move/드레인펀치')
  self.assertEqual(self.a.hp-before,__import__('arithmetic_policy').ratio(dealt,2));self.valid()
 def test_reference_detect_actual_native_defense_and_original_resume(self):
  self.acquire(A.CLASS,moves=['move/판별','move/발경']);self.begin(self.t);self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':'move/판별'}],reason='actual Detect choice')
  import passive_events as P
  before=self.a.hp
  with self.assertRaises(P.PassiveEventPending):self.use(self.t,self.a,'move/몸통박치기')
  event=self.e._passive_pending;self.restore();self.e.choose_move_defense(event,self.a,use=True,options={},reason='use actual Detect')
  self.assertEqual(self.a.hp,before);self.assertEqual(self.a.move_uses['move/판별'],1);self.assertEqual(self.t.move_uses['move/몸통박치기'],1);self.valid()
 def test_scrappy_actual_ghost_dual_type_matchup(self):
  self.acquire(A.CLASS,moves=['move/발경','move/판별']);self.acquire(A.POWER,rank=1,ability=A.SCRAPPY);self.e.gm.set_types(self.t,['고스트','바위'],reason='actual Ghost Rock foe');self.begin()
  self.assertGreater(self.use(self.a,self.t,'move/발경'),0);self.valid()
 def test_actual_core_and_playtest_aura_storm_have_distinct_damage_contracts(self):
  for profile,uid in [('core',A.STORM),('playtest',A.STORM_TEST)]:
   with self.subTest(profile=profile):
    self.rules=Rules(ROOT,ruleset=profile);self.setup();self.family(A.CLASS);self.acquire(A.POWER,rank=1,ability=uid);self.begin()
    base=self.use(self.a,self.t,'move/진공파');self.next_round();self.e.gm.set_injuries(self.a,value=1,reason='actual injury');self.e.gm.set_hp(self.a,value=self.a.base_max_hp//2,reason='actual real half HP, independent of injury healing cap')
    changed=self.use(self.a,self.t,'move/진공파');self.assertGreater(changed,base)
    self.assertEqual(A.storm_bonus(self.e,self.a,self.rules.move('move/물대포')),3 if profile=='playtest' else 0)
    self.assertEqual(A.storm_bonus(self.e,self.a,self.rules.move('move/진공파')),3 if profile=='playtest' else 6);self.valid()
    self.next_round();actual=self.use(self.a,self.t,'move/물대포');self.assertEqual(actual,11+self.a.staged('spa')-self.t.staged('spd')+(3 if profile=='playtest' else 0));self.valid()


 def retraining_operation(self,uid):
  import trainer_retraining as R
  owned=R._owned(self.a);sources={u:R.owned_source(self.e,self.a,u) for u in owned}
  parents=R._native_dependencies(self.e,self.a,owned)
  retained={sid:[sources[p] for p in parents.get(u,[])] for u,sid in sources.items() if u!=uid}
  return lambda:R.retrain(self.e,self.a,uid,request_id='aura-retrain:'+uid,reason='actual GM reviewed retraining',gm_decision={'allowed':True,'reason':'reviewed'},retained_dependencies=retained)
 def test_independent_move_source_survives_mastery_withdrawal(self):
  self.family(A.MASTERY,moves=['move/파동탄','move/드레인펀치']);self.e.gm.set_move(self.a,'move/파동탄',reason='independent permanent lesson')
  before=self.a.stats['atk'];self.retraining_operation(A.MASTERY)();self.assertIn('move/파동탄',self.a.moves);self.assertNotIn('move/드레인펀치',self.a.moves);self.assertEqual(self.a.stats['atk'],before-1);self.restore();self.valid()
 def test_retained_parent_dependency_blocks_class_withdrawal(self):
  self.family(A.READER);self.reject(self.retraining_operation(A.CLASS),'depend|prerequisite')
 def test_power_rank_two_individual_retraining_remains_explicit_shared_dependency(self):
  self.acquire(A.CLASS);self.acquire(A.POWER,rank=1);self.acquire(A.POWER,rank=2,ability=A.STORM)
  self.reject(self.retraining_operation(A.POWER),'rank|one|selection|selected')


 def test_twisted_power_actual_ability_adds_half_other_stat_but_sword_does_not_stack(self):
  self.acquire(A.CLASS,moves=['move/발경','move/판별']);self.e.gm.set_ability(self.a,'트위스트파워',reason='actual separately acquired Twisted Power');self.begin();self.decision('twisted_power',True)
  dealt=self.use(self.a,self.t,'move/발경');other=__import__('arithmetic_policy').ratio(self.a.staged('spa'),2)
  self.assertEqual(dealt,__import__('arithmetic_policy').product(max(1,15+self.a.staged('atk')+other-self.t.staged('def')),1.5))
  self.family(A.SWORD);self.next_round();self.decision('sword_of_body_and_soul','물리');dealt=self.use(self.a,self.t,'move/발경')
  self.assertEqual(dealt,__import__('arithmetic_policy').product(max(1,15+self.a.staged('atk')+self.a.staged('spa')-self.t.staged('def')),1.5));self.valid()
 def test_sword_ignores_actual_aura_barrier_damage_reduction(self):
  self.acquire(A.CLASS,moves=['move/발경','move/판별']);self.family(A.SWORD)
  rival=self.add('rival','trainer',(3,3),side='foes',extra_skills={'직감':5},edges=['edge/원소-교감'],edge_choices={'edge/원소-교감':['격투']})
  for uid in (A.CLASS,A.READER,A.AMBIENT):self.acquire(uid,actor=rival,request='rival:'+uid)
  self.begin(rival);self.e.activate_aura_reader(rival);self.e.end_of_turn(rival);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(rival,initiative_count=40)
  self.decision('ambient_aura',True);self.use(rival,self.a,'move/진공파');self.e.spend_aura_blessing(rival,'barrier');self.assertEqual(__import__('effect_lifetimes').numeric(rival,'damage_reduction'),15)
  self.turn(self.a,30);self.decision('sword_of_body_and_soul','특수');dealt=self.use(self.a,rival,'move/발경')
  self.assertEqual(dealt,__import__('arithmetic_policy').product(max(1,15+self.a.staged('atk')+self.a.staged('spa')-rival.staged('spd')),1.5));self.valid()

class FocusPunchTests(AuraScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def prepare(self,path=(),target_at_start=True):
  self.family(A.MASTERY,moves=['move/힘껏펀치','move/드레인펀치']);self.e.gm.set_stat(self.ally,'spe',value=15,reason='observed distinct initiative')
  self.e.prepare_initiative_schedule(self.e.everyone,source='gm/actual-aura-focus-order');self.e.start_round(self.e.everyone)
  return self.e.declare_focus_punch(self.a,self.t if target_at_start else None,request_id='focus-declaration',path=path,reason='actual round-start Focus Punch choice')
 def close(self,actions=None):
  for actor in (self.a,self.t,self.ally,self.u):
   self.e.start_of_turn(actor)
   if actions and actor.entity_id in actions:actions[actor.entity_id]()
   self.e.end_of_turn(actor)
 def release(self):
  import focus_punch as FOCUS,world_entities as W
  row=FOCUS.active(self.e,self.a)
  if row and row['phase']=='declared' and row.get('release_choice') is None and FOCUS.cancellation(self.e,self.a,row) is None:
   self.e.choose_focus_punch(self.a,use=True,target=W.actor_index(self.e).get(row['intent']['target_id'],self.t),path=row['intent']['path'],mode=row['intent']['mode'],request_id='actual-release',reason='actual round-end use target and Shift choice')
  with patch.object(Engine,'d20',return_value=15):return self.e.end_round()
 def threshold_attacker(self,actor,delta=0):
  self.e.gm.set_stat(self.a,'hp',value=6,reason='observed actual HP allocation')
  self.e.gm.set_hp(self.a,value=self.a.max_hp,reason='actual fresh HP')
  amount=self.a.base_max_hp//4+delta
  base=self.rules.mech('combat/damage-chart')['by_damage_base']['4']['set']['mid']
  self.e.gm.set_stat(actor,'spa',value=amount+self.a.staged('spd')-base,reason='observed actual attacker Special Attack')
  return amount
 def test_priority_limited_pays_standard_without_advancing_owner_turn_then_real_shift_release(self):
  self.e.gm.set_position(self.t,(4,2),reason='actual target three squares from starting centre');self.prepare(path=[(3,2)])
  self.assertNotIn('move/힘껏펀치',self.a.move_uses);self.assertEqual(self.a.custom_conditions.get('combat_turn_serial',0),0)
  self.e.start_of_turn(self.a);self.assertEqual(self.a.budget,{'standard':0,'shift':1,'swift':1});self.e.end_of_turn(self.a)
  for actor in (self.t,self.ally,self.u):self.e.start_of_turn(actor);self.e.end_of_turn(actor)
  before=self.t.hp;self.release();self.assertEqual(self.a.pos,(3,2));self.assertLess(self.t.hp,before);self.assertEqual(self.a.move_uses['move/힘껏펀치'],1)
  self.assertEqual(self.a.spec['focus_punch_actions'][0]['phase'],'complete');self.valid();self.restore();self.valid()
 def test_exact_quarter_hit_from_third_party_cancels_without_frequency(self):
  self.prepare();amount=self.threshold_attacker(self.u);self.assertEqual(amount*4,self.a.base_max_hp)
  self.close({self.u.entity_id:lambda:self.use(self.u,self.a,'move/물대포')});self.restore();self.release()
  row=self.a.spec['focus_punch_actions'][0];self.assertEqual(row['phase'],'cancelled');self.assertIsNotNone(row['cancellation_event']);self.assertNotIn('move/힘껏펀치',self.a.move_uses);self.valid()
 def test_multiple_below_quarter_hits_are_not_aggregated(self):
  self.prepare();self.threshold_attacker(self.t,-1);self.threshold_attacker(self.u,-1)
  self.close({self.t.entity_id:lambda:self.use(self.t,self.a,'move/물대포'),self.u.entity_id:lambda:self.use(self.u,self.a,'move/물대포')});self.release()
  self.assertEqual(self.a.spec['focus_punch_actions'][0]['phase'],'complete');self.assertEqual(self.a.move_uses['move/힘껏펀치'],1);self.valid()
 def test_target_receiving_damage_and_passive_user_hp_loss_do_not_cancel(self):
  self.prepare();self.e.lose_hp(self.a,self.a.base_max_hp//4+1,source='condition/독')
  self.e.gm.set_stat(self.u,'spa',value=80,reason='observed attacker Special Attack')
  self.close({self.u.entity_id:lambda:self.use(self.u,self.t,'move/물대포')});self.release()
  self.assertEqual(self.a.spec['focus_punch_actions'][0]['phase'],'complete');self.assertEqual(self.a.move_uses['move/힘껏펀치'],1);self.valid()
 def test_late_or_ordinary_use_rejects_without_fabricating_declaration(self):
  self.family(A.MASTERY,moves=['move/힘껏펀치','move/드레인펀치']);self.begin();self.reject(lambda:self.use(self.a,self.t,'move/힘껏펀치'),'declaration')
  self.reject(lambda:self.e.declare_focus_punch(self.a,self.t,request_id='late',reason='late request'),'between-turn')
  self.e.gm.set_move(self.t,'move/판별',reason='actual learned Detect for ordinary control');self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,'source':'move/판별'}],reason='actual ordinary Move response watch')
  with self.assertRaises(__import__('passive_events').PassiveEventPending):self.use(self.a,self.t,'move/몸통박치기')
  event=self.e._passive_pending;self.e.choose_move_defense(event,self.t,use=False,options={},reason='decline actual ordinary defense');self.e.end_of_turn(self.a)
  self.reject(lambda:__import__('initiative_interrupts').queue(self.e,[{'id':'no-owner-control','actor_id':self.a.entity_id,'source':'move/판별','priority':0,'mode':'reaction','payment':'next','budget':{'standard':1},'clock':'none','move_id':'move/판별'}],trigger={'kind':'accuracy','event_id':event}),'owner turn')
 def test_declaration_replay_and_changed_intent(self):
  row=self.prepare();self.assertEqual(self.e.declare_focus_punch(self.a,self.t,request_id='focus-declaration',reason='actual round-start Focus Punch choice'),row)
  self.reject(lambda:self.e.declare_focus_punch(self.a,self.u,request_id='focus-declaration',reason='actual round-start Focus Punch choice'),'replay')
  self.close();self.release();self.valid()
  self.a.spec['focus_punch_actions'][0]['intent']['target_id']=self.u.entity_id;self.assertFalse(self.e.validate_state()['valid'])
 def test_pending_shield_restores_and_resume_preserves_declared_cost_and_frequency(self):
  self.prepare();self.e.gm.set_move(self.t,'move/판별',reason='actual learned Detect');self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,'source':'move/판별'}],reason='actual pending Focus Punch defense');self.close()
  import passive_events as P
  with self.assertRaises(P.PassiveEventPending):self.release()
  pending=self.e._passive_pending;uses=self.a.move_uses['move/힘껏펀치'];self.restore();self.e.choose_move_defense(pending,self.t,use=True,options={},reason='actual shield response');self.release()
  self.assertEqual(self.a.move_uses['move/힘껏펀치'],uses);self.assertEqual(self.a.spec['focus_punch_actions'][0]['phase'],'complete');self.valid()


 def test_round_end_use_is_optional_and_declaration_needs_no_target(self):
  self.prepare(target_at_start=False);self.close();before=self.t.hp
  result=self.e.end_round();self.assertIsInstance(result,__import__('common_checks').PendingDecision);self.assertIsNotNone(self.e.round_start_seconds);self.assertEqual(self.t.hp,before);self.assertNotIn('move/힘껏펀치',self.a.move_uses)
  self.e.choose_focus_punch(self.a,use=False,request_id='decline-focus',reason='actual round-end decline');self.e.end_round()
  self.assertEqual(self.a.spec['focus_punch_actions'][0]['phase'],'declined');self.assertNotIn('move/힘껏펀치',self.a.move_uses);self.valid()
 def test_round_end_selects_new_actual_target_and_shift_once_after_hint_target_faints(self):
  self.prepare();self.close();self.e.gm.set_hp(self.t,value=0,reason='actual original hint target fainted');self.e.gm.set_position(self.u,(5,3),reason='actual new target position')
  options=dict(use=True,target=self.u,path=[(2,3),(3,3),(4,3)],request_id='choose-new-target',reason='actual round-end target and Shift')
  selected=self.e.choose_focus_punch(self.a,**options);before=self.u.hp;self.release();self.assertLess(self.u.hp,before);self.assertEqual(self.a.pos,(4,3));self.assertEqual(self.a.move_uses['move/힘껏펀치'],1)
  self.assertEqual(self.e.choose_focus_punch(self.a,**options),selected);self.reject(lambda:self.e.choose_focus_punch(self.a,**dict(options,target=self.t)),'replay');self.valid()
 def test_endure_hp_replacement_does_not_reduce_actual_attack_cancellation_threshold(self):
  self.prepare();amount=self.threshold_attacker(self.u);self.e.gm.set_move(self.a,'move/버티기',reason='actual learned Endure');self.e.gm.set_hp(self.a,value=5,reason='actual low remaining HP');self.decision('endure',True)
  self.close({self.u.entity_id:lambda:self.use(self.u,self.a,'move/물대포')});self.assertEqual(self.a.hp,1);self.assertEqual(self.a.move_uses['move/버티기'],1);self.release()
  row=self.a.spec['focus_punch_actions'][0];event=self.e._heavy_events[row['cancellation_event']]
  self.assertEqual(row['phase'],'cancelled');self.assertEqual(event['focus_punch_damage']['amount'],amount);self.assertLess(event['before']['hp']-event['observed_after']['hp'],amount);self.assertNotIn('move/힘껏펀치',self.a.move_uses);self.valid()


 def test_round_end_shift_pending_effect_restores_actual_prefix_and_resumes_once(self):
  self.e.gm.set_position(self.t,(4,4),reason='actual target for optional Shift');self.prepare(path=[(2,3),(3,3)]);self.close()
  import effects_ext as EXT,effects as FX,focus_punch as FOCUS
  original=EXT.on_enter_cell
  def actual_entry(e,actor,point,**options):
   original(e,actor,point,**options)
   if actor.entity_id==self.a.entity_id and point==(2,3):FX.run_effects(e,actor,actor,[{'type':'stage_change','stat':'def','delta':1,'if':'target was asleep'}],{'hit':True},'hazard/actual-focus-entry')
  with patch.object(EXT,'on_enter_cell',side_effect=actual_entry):result=self.release()
  self.assertIsInstance(result,__import__('common_checks').PendingDecision);self.assertEqual(self.a.pos,(2,3));self.assertNotIn('move/힘껏펀치',self.a.move_uses);self.assertEqual(FOCUS.active(self.e,self.a)['shift_progress']['phase'],'entry_pending');self.valid();self.restore()
  token=next(k for k,v in self.e._effect_dispatch_receipts.items() if v['status']=='condition_unknown')
  self.e.resolve_effect_condition(self.a,token,target_was_asleep=True,reason='actual authored entry condition observed')
  self.release();self.assertEqual(self.a.pos,(3,3));self.assertEqual(self.a.stages['def'],1);self.assertEqual(self.a.move_uses['move/힘껏펀치'],1);self.assertEqual(self.a.spec['focus_punch_actions'][0]['phase'],'complete');self.valid()


 def test_round_end_aerial_shift_uses_shared_observed_path_and_restores_choice(self):
  self.e.gm.set_movement_capabilities(self.a,{'land':6,'sky':4},basis='base',reason='actual observed flying movement capability');self.e.gm.set_position(self.t,(4,2),reason='actual target for aerial approach');self.e.gm.set_position(self.u,(10,8),reason='actual other foe distant from the observed flying route')
  self.prepare();self.close();self.e.choose_focus_punch(self.a,use=True,target=self.t,path=[{'position':(2,3),'altitude':1,'gm_distance':2},{'position':(3,2),'altitude':0,'gm_distance':2}],mode='sky',request_id='aerial-release',reason='actual round-end aerial Shift')
  self.restore();before=self.t.hp;self.release();self.assertEqual(self.a.pos,(3,2));self.assertEqual(self.a.spec['_movement_altitude'],0);self.assertFalse(self.a.airborne);self.assertEqual(self.a.spec['focus_punch_actions'][0]['shift_progress']['distance'],4);self.assertEqual(self.a.spec['focus_punch_actions'][0]['shift_progress']['next'],2);self.assertLess(self.t.hp,before);self.assertEqual(self.a.move_uses['move/힘껏펀치'],1);self.valid()

if __name__=='__main__':unittest.main()
