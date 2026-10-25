"""Whole Tumbler: actual acquisition, all native triggers, Move branches and turn authority."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from tumbler_fixture import TumblerScene
from engine import Rules,Engine
import tumbler as T
import jump_actions as J
import combat_timing as TIME
import action_points as AP
import frequency as F
import initiative_schedule as S
import move_completion as COMPLETE
import passive_events as PASSIVE
import action_resources as RESOURCES
import state_grants as G
import trainer_retraining as RETRAIN

class TumblerTests(TumblerScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def test_seven_independent_acquisitions_speed_moves_and_abilities(self):
  speed=self.a.stats['spe'];self.acquire(T.CLASS)
  self.assertEqual(self.a.spec['feats'],[T.CLASS]);self.assertIn('도주',self.a.abilities);self.assertEqual(self.a.stats['spe'],speed+1)
  for uid in T.FEATURES:
   if uid!=T.CLASS:self.acquire(uid)
  self.assertEqual(self.a.stats['spe'],speed+7);self.assertTrue({T.ACE,T.SPLASH,T.ACROBATICS,T.BOUNCE}<=set(self.a.moves));self.assertIn('회피',self.a.abilities);self.valid();self.restore();self.valid()
 def test_prerequisites_use_actual_acrobat_and_parent_acquisition(self):
  self.setup(acrobat=False);self.reject(lambda:self.acquire(T.CLASS),'prerequisite')
  self.setup();self.reject(lambda:self.acquire(T.AERIAL),'prerequisite');self.family(T.AERIAL)
  self.reject(lambda:self.acquire(T.AERIAL,request='distinct-aerial-reacquisition'),'already acquired')
 def test_rank_and_five_feature_boundaries(self):
  self.setup(rank=3);self.family(T.AERIAL);self.reject(lambda:self.acquire(T.FLIP),'rank');self.reject(lambda:self.acquire(T.REFLEX),'rank')
  self.setup(rank=6);self.family(T.QUICK);self.reject(lambda:self.acquire(T.BURST),'five')
 def test_no_unprinted_choices_or_child_auto_grants(self):
  self.acquire(T.CLASS)
  import trainer_feature_acquisition as A
  self.reject(lambda:A.acquire_static(self.e,self.a,T.AERIAL,acquisition_request_id='bad',selection={'move':T.BOUNCE}),'no optional')
  self.assertEqual(set(self.a.moves),{'move/몸통박치기','move/물대포'})
 def test_acrobat_learning_capabilities_reused(self):
  before=J.limits(self.a);self.family(T.AERIAL);after=J.limits(self.a)
  self.assertEqual(after['long_jump'],before['long_jump']+1);self.family(T.DEATH)
  self.assertEqual(J.limits(self.a)['high_jump'],before['high_jump']+1)
 def test_retraining_revokes_only_source_owned_moves_and_speed(self):
  self.family(T.AERIAL);self.e.gm.set_move(self.a,T.ACE,reason='independent actual permanent Move learning')
  speed=self.a.stats['spe'];RETRAIN.retrain(self.e,self.a,T.AERIAL,request_id='retrain-aerial',reason='actual retraining',gm_decision={'allowed':True,'reason':'reviewed'},retained_dependencies={RETRAIN.owned_source(self.e,self.a,T.CLASS):[RETRAIN.owned_source(self.e,self.a,T.ACROBAT)],RETRAIN.owned_source(self.e,self.a,T.ACROBAT):[]})
  self.assertEqual(self.a.stats['spe'],speed-1);self.assertIn(T.ACE,self.a.moves);self.assertNotIn(T.SPLASH,self.a.moves);self.restore();self.valid()
 def test_core_run_away_status_and_shift_only_opportunity(self):
  self.acquire(T.CLASS)
  for status in ('둔화','구속','수렁'):self.assertFalse(self.e.apply_status(self.a,status))
  self.begin();hp=self.a.hp;self.jump((2,3));self.assertEqual(self.a.hp,hp)
  self.assertFalse(self.t.aoo_used);self.assertFalse(self.u.aoo_used)
 def test_run_away_suppression_and_restore(self):
  self.acquire(T.CLASS);self.e.gm.set_move(self.t,'move/위액',reason='actual learned suppression Move');self.begin(self.t)
  __import__('ability_transitions').select(self.e,self.t,self.a,'move/위액',ability='ability/도주',reason='actual selected source');self.use(self.t,self.a,'move/위액')
  self.assertTrue(self.e.apply_status(self.a,'수렁'));self.restore();self.valid()
 def test_quick_actual_hit_spends_one_ap_and_moves_two(self):
  self.family(T.QUICK);self.begin();before=AP.available(self.a)
  self.decision('quick_gymnastics',{'path':[(2,3),(2,4)]});self.use(self.a,self.t,'move/몸통박치기')
  self.assertEqual(AP.available(self.a),before-1);self.assertEqual(self.a.pos,(2,4));self.assertTrue(T.immune(self.a));self.assertEqual(self.a._action_history,['standard','free']);self.valid()
 def test_quick_miss_and_decline_do_not_spend(self):
  self.family(T.QUICK);self.begin();before=AP.available(self.a);self.decision('quick_gymnastics',True)
  self.use(self.a,self.t,'move/몸통박치기',1);self.assertEqual(AP.available(self.a),before);self.assertFalse(T.immune(self.a))
  self.next_round();self.rules.rulings.answers=[];self.decision('quick_gymnastics',False);self.use(self.a,self.t,'move/몸통박치기');self.assertEqual(AP.available(self.a),before)
 def test_quick_jump_trigger_and_no_duplicate_shift_cost(self):
  self.family(T.QUICK);self.begin();self.decision('quick_gymnastics',True);before=AP.available(self.a)
  self.jump();self.assertEqual(AP.available(self.a),before-1);self.assertEqual(self.a.budget['standard'],1);self.assertEqual(self.a.budget['shift'],0);self.valid()
 def test_quick_stand_trigger_suppresses_triggering_opportunity(self):
  self.family(T.QUICK);self.begin();self.e.apply_status(self.a,'넘어짐');self.decision('quick_gymnastics',True)
  hp=self.a.hp;self.e.stand_up(self.a);self.assertEqual(self.a.hp,hp);self.assertNotIn('넘어짐',self.a.conditions);self.assertFalse(self.t.aoo_used);self.assertTrue(T.immune(self.a));self.valid()
 def test_quick_flank_and_opportunity_immunity_expires_next_own_turn_end(self):
  self.family(T.QUICK);self.begin();self.assertTrue(__import__('body_state').flanking(self.e,self.a)['flanked'])
  self.decision('quick_gymnastics',True);self.use(self.a,self.t,'move/몸통박치기');self.assertFalse(__import__('body_state').flanking(self.e,self.a)['flanked'])
  self.e.end_of_turn(self.a);self.assertTrue(T.immune(self.a));self.e.start_of_turn(self.t,initiative_count=20);self.e.end_of_turn(self.t);self.assertTrue(T.immune(self.a))
  self.e.end_round();self.begin();self.assertTrue(T.immune(self.a));self.e.end_of_turn(self.a);self.assertFalse(T.immune(self.a))
 def test_quick_restores_source_and_turn_deadline(self):
  self.family(T.QUICK);self.begin();self.decision('quick_gymnastics',True);self.jump();self.restore();self.assertTrue(T.immune(self.a));self.valid()
 def test_quick_ranged_hit_suppresses_triggering_action_aoo(self):
  self.family(T.QUICK);self.begin();self.e.gm.set_position(self.t,(5,2),reason='observed distant target');self.decision('quick_gymnastics',True)
  hp=self.a.hp;self.use(self.a,self.t,'move/물대포');self.assertEqual(self.a.hp,hp);self.assertFalse(self.u.aoo_used);self.valid()
 def test_quick_ranged_miss_retains_actual_aoo(self):
  self.family(T.QUICK);self.begin();self.e.gm.set_position(self.t,(5,2),reason='observed distant target');self.decision('quick_gymnastics',True)
  self.use(self.a,self.t,'move/물대포',1);self.assertTrue(self.u.aoo_used);self.assertFalse(T.immune(self.a))
 def test_aerial_ace_pass_skips_critical_test_and_uses_existing_path(self):
  self.family(T.FLIP);self.begin()
  with patch.object(Engine,'d20',side_effect=AssertionError('no critical test')):
   self.e.use_pass_move(self.a,T.ACE,(5,2),event_id='ace-pass',object_adjudications={},source='actual terrain observation',reason='choose no critical test',range_source=T.FLIP)
  self.assertEqual(self.a.pos,(5,2));self.assertLess(self.t.hp,self.t.max_hp);self.assertEqual(self.a.budget['shift'],0);self.assertEqual(self.a.budget['standard'],0);self.valid()
 def test_aerial_ace_normal_keeps_critical_and_no_pass(self):
  self.family(T.FLIP);self.begin();pos=self.a.pos;self.use(self.a,self.t,T.ACE,20)
  self.assertEqual(self.a.pos,pos);self.assertTrue(any('치명타' in line for line in self.e.log_lines));self.assertEqual(self.a.budget['shift'],1)
 def test_acrobatics_held_item_optional_extra_damage(self):
  self.family(T.DEATH);self.family(T.FLIP);self.begin();self.hold_item()
  self.e.choose_tumbler_acrobatics(self.a,activate=True,reason='activate Flip Out extra damage')
  before=self.t.hp;self.use(self.a,self.t,T.ACROBATICS);boost=before-self.t.hp
  self.next_round();self.next_round();self.e.choose_tumbler_acrobatics(self.a,activate=False,reason='decline extra damage');before=self.t.hp;self.use(self.a,self.t,T.ACROBATICS)
  self.assertGreater(boost,before-self.t.hp);self.valid()
 def test_splash_actual_shift_jump_evasion_and_learning_bonus(self):
  self.family(T.AERIAL);self.begin();limits=J.limits(self.a)
  self.jump_move(T.SPLASH);self.assertEqual(self.a.pos,(2,3));self.assertEqual(self.a.budget['standard'],1);self.assertEqual(self.a.budget['shift'],0)
  self.assertEqual(__import__('effect_lifetimes').numeric(self.a,'evasion_modifier'),2);self.assertEqual(J.limits(self.a),limits);self.assertEqual(self.a.move_uses[T.SPLASH],1);self.valid()
 def test_splash_evasion_lasts_through_next_own_turn_end(self):
  self.family(T.AERIAL);self.begin();self.jump_move(T.SPLASH);self.e.end_of_turn(self.a);self.assertEqual(__import__('effect_lifetimes').numeric(self.a,'evasion_modifier'),2)
  self.e.end_round();self.begin();self.e.end_of_turn(self.a);self.assertEqual(__import__('effect_lifetimes').numeric(self.a,'evasion_modifier'),0)
 def test_bounce_full_action_movement_then_vulnerable_attack(self):
  self.family(T.DEATH);self.begin();self.e.gm.set_position(self.t,(6,2),reason='actual Bounce target')
  self.jump_move(T.BOUNCE,path=[(3,2),(4,2),(5,2)],face=16)
  self.assertEqual(self.a.pos,(5,2));self.assertIn('취약',self.t.conditions);self.assertIn('마비',self.t.conditions);self.assertEqual((self.a.budget['standard'],self.a.budget['shift']),(0,0));self.assertEqual(self.a.move_uses[T.BOUNCE],1);self.valid()
 def test_bounce_flip_ignores_and_optionally_destroys_landing_hazards(self):
  self.family(T.DEATH);self.family(T.FLIP);self.begin();self.e.gm.set_position(self.t,(5,3),reason='actual target')
  for cell in ((3,2),(4,2),(4,3),(5,2),(6,2)):self.e.gm.place_hazard(cell,'test spikes',[{'type':'hp_loss','value':10}],reason='actual visible hazard')
  hp=self.a.hp;self.jump_move(T.BOUNCE,path=[(3,2),(4,2)],destroy=True)
  self.assertEqual(self.a.hp,hp);self.assertNotIn((4,2),self.e.hazards);self.assertNotIn((5,2),self.e.hazards);self.assertIn((6,2),self.e.hazards);self.assertTrue(__import__('jump_move_actions').hazard_immune(self.a));self.e.end_of_turn(self.a);self.assertFalse(__import__('jump_move_actions').hazard_immune(self.a));self.valid()
 def test_bounce_hazard_decline_preserves_hazards(self):
  self.family(T.DEATH);self.family(T.FLIP);self.begin();self.e.gm.place_hazard((2,3),'test',[{'type':'hp_loss','value':10}],reason='actual hazard')
  self.jump_move(T.BOUNCE,destination=(2,3),destroy=False);self.assertIn((2,3),self.e.hazards)
 def test_jump_move_requires_actual_declaration_and_invalid_path_is_atomic(self):
  self.family(T.DEATH);self.begin();self.reject(lambda:self.use(self.a,self.t,T.BOUNCE),'movement declaration')
  self.reject(lambda:self.e.declare_jump_move(self.a,self.t,T.BOUNCE,event_id='bad',path=[(12,2)],reason='invalid step'),'adjacent|step')
 def test_splash_interrupt_actual_hit_shift_debt_and_once_scene(self):
  self.family(T.FLIP);self.begin(self.t,40);self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='actual Flip Out reaction')
  hp=self.a.hp;baseline=self.e.roll_damage(self.t,self.a,self.rules.move('move/몸통박치기'),set_damage=True)
  with self.assertRaises(PASSIVE.PassiveEventPending):self.use(self.t,self.a,'move/몸통박치기')
  event=self.e._passive_pending;self.e.choose_move_defense(event,self.a,use=True,options={'jump':{'destination':(2,3),'difficult':False,'clear_path':True}},reason='actual Splash choice')
  self.assertEqual(self.a.pos,(2,3));self.assertEqual(RESOURCES.pending(self.a).get('shift'),1);self.assertEqual(hp-self.a.hp,max(1,baseline-12))
  native=self.e._passive_events[event];state=self.e._move_completions[native['completion_id']]['defense'][self.a.entity_id];self.assertEqual(state['attempts'][0]['splash']['damage_reduction'],12)
  self.assertFalse(F.activation_allowed(self.a,T.FLIP+':Splash',{'kind':'scene','uses':1},engine=self.e));self.valid();self.restore();self.valid()
 def test_splash_interrupt_decline_and_miss_do_not_consume(self):
  self.family(T.FLIP);self.begin(self.t,40);self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='actual reaction')
  self.use(self.t,self.a,'move/몸통박치기',1);self.assertIsNone(self.e._passive_pending);self.assertTrue(F.activation_allowed(self.a,T.FLIP+':Splash',{'kind':'scene','uses':1},engine=self.e))
 def test_splash_pending_choice_survives_save_restore(self):
  self.family(T.FLIP);self.begin(self.t,40);self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='actual reaction')
  with self.assertRaises(PASSIVE.PassiveEventPending):self.use(self.t,self.a,'move/몸통박치기')
  event=self.e._passive_pending;self.restore();self.e.choose_move_defense(event,self.a,use=False,reason='decline restored native choice');self.assertEqual(self.a.pos,(2,2));self.valid()
 def test_burst_schedules_actual_half_initiative_extra_turn(self):
  self.family(T.BURST);self.begin();initiative=self.e.initiative_value(self.a).value;count=initiative//2
  self.decision('burst_of_speed',count);self.use(self.a,self.t,'move/몸통박치기');self.e.end_of_turn(self.a)
  self.assertIsNone(self.e._active_turn_actor);self.e.start_of_turn(self.a,initiative_count=count)
  self.assertEqual(self.a.budget,{'standard':1,'shift':1,'swift':1});self.assertEqual(self.a.custom_conditions['combat_turn_serial'],2)
  self.use(self.a,self.t,'move/몸통박치기');self.e.end_of_turn(self.a);self.assertEqual(len(getattr(self.e,S.EXTRA)),1);self.valid()
 def test_burst_invalid_count_rejects_without_closing_turn(self):
  self.family(T.BURST);self.begin();self.decision('burst_of_speed',99)
  self.reject(lambda:self.e.end_of_turn(self.a),'half');self.assertIs(self.e._active_turn_actor,self.a)
 def test_burst_extra_turn_count_cannot_be_skipped_or_replayed(self):
  self.family(T.BURST);self.begin();self.decision('burst_of_speed',10);self.e.end_of_turn(self.a)
  self.reject(lambda:self.e.start_of_turn(self.t,initiative_count=9),'scheduled extra')
  self.e.start_of_turn(self.a,initiative_count=10);self.e.end_of_turn(self.a)
  self.reject(lambda:self.e.start_of_turn(self.a,initiative_count=10),'already taken')
 def test_burst_restore_keeps_actual_closure_and_extra_turn_right(self):
  self.family(T.BURST);self.begin();self.decision('burst_of_speed',10);self.e.end_of_turn(self.a);self.restore();self.e.start_of_turn(self.a,initiative_count=10);self.valid()
 def test_burst_does_not_reset_scene_frequency_or_aoo(self):
  self.family(T.BURST);self.begin();self.decision('burst_of_speed',10);self.e.end_of_turn(self.a);self.e.start_of_turn(self.a,initiative_count=10)
  self.assertFalse(F.activation_allowed(self.a,T.BURST,{'kind':'scene','uses':1},engine=self.e));self.e.end_of_turn(self.a);self.assertEqual(len(getattr(self.e,S.EXTRA)),1)

 def test_actual_core_and_playtest_run_away_are_explicitly_selectable(self):
  for profile,name,immune in [('core','도주',True),('playtest','도주 [Playtest]',False)]:
   with self.subTest(profile=profile):
    self.rules=Rules(ROOT,ruleset=profile);self.setup();self.acquire(T.CLASS)
    self.assertIn(name,self.a.abilities);self.assertEqual(bool(self.e.immune_to(self.a,'둔화')),immune);self.assertTrue(self.e.immune_to(self.a,'수렁'));self.valid()
 def test_low_rank_acrobat_sheet_does_not_bypass_edge_requirement(self):
  self.setup(rank=2);self.reject(lambda:self.acquire(T.CLASS),'rank')
 def test_burst_tampered_count_and_closure_rejected_on_restore(self):
  self.family(T.BURST);self.begin();self.decision('burst_of_speed',10);self.e.end_of_turn(self.a)
  row=getattr(self.e,S.EXTRA)[0];row['origin']['count']=99
  self.assertFalse(self.e.validate_state()['valid'])
 def test_jump_move_tampered_paid_suffix_rejected(self):
  self.family(T.AERIAL);self.begin();self.jump_move(T.SPLASH)
  row=self.a.spec['jump_move_actions'][0];row['suffix']['move_id']=T.BOUNCE
  self.assertFalse(self.e.validate_state()['valid'])
 def test_bounce_restores_actual_movement_and_completion(self):
  self.family(T.DEATH);self.family(T.FLIP);self.begin();self.jump_move(T.BOUNCE,destination=(2,3));self.restore();self.assertEqual(self.a.pos,(2,3));self.valid()

 def test_bounce_optional_attack_decline_keeps_full_cost_and_movement(self):
  self.family(T.DEATH);self.begin();hp=self.t.hp
  self.e.declare_jump_move(self.a,self.t,T.BOUNCE,event_id='decline-attack',path=[(2,3)],attack=False,reason='move but decline optional attack')
  self.use(self.a,self.t,T.BOUNCE);self.assertEqual(self.a.pos,(2,3));self.assertEqual(self.t.hp,hp);self.assertEqual(self.a.move_uses[T.BOUNCE],1);self.assertEqual(self.a.budget['standard'],0);self.valid()
 def test_paid_failed_jump_wait_restores_without_repaying_or_reroll(self):
  self.family(T.AERIAL);self.begin()
  self.e.declare_jump_move(self.a,self.a,T.SPLASH,event_id='failed-splash',jump={'destination':(2,3),'difficult':True,'difficulty_skill':'곡예','difficulty_dc':100,'difficulty_options':{'fixed':[1,1,1,1,1,1]},'clear_path':True},reason='actual unusually difficult Jump')
  result=self.use(self.a,self.a,T.SPLASH);self.assertIsInstance(result,__import__('common_checks').PendingDecision);self.assertEqual(self.a.move_uses[T.SPLASH],1)
  self.reject(lambda:self.e.end_of_turn(self.a),'unfinished');self.restore()
  J.resolve_failure(self.e,self.a,decision='land',reason_text='GM resolves actual failed Jump landing')
  with patch.object(Engine,'skill_roll',side_effect=AssertionError('paid observed Jump must not reroll')):self.e.resume_jump_move(self.a,event_id='failed-splash')
  self.assertEqual(self.a.move_uses[T.SPLASH],1);self.assertEqual(self.a._action_history,['shift']);self.valid()
 def test_burst_extra_turn_preserves_ordinary_schedule_slot(self):
  self.family(T.BURST);self.e.prepare_initiative_schedule(self.e.everyone,source='combat/initiative');self.begin(count=37);self.decision('burst_of_speed',15);self.e.end_of_turn(self.a)
  self.e.start_of_turn(self.t,initiative_count=20);self.e.end_of_turn(self.t);self.e.start_of_turn(self.a,initiative_count=15);self.e.end_of_turn(self.a)
  self.e.start_of_turn(self.u,initiative_count=10);self.e.end_of_turn(self.u);self.e.end_round();self.valid()
 def test_burst_end_encounter_cannot_resurrect_unused_extra_turn(self):
  self.family(T.BURST);self.begin();self.decision('burst_of_speed',10);self.e.end_of_turn(self.a);self.e.end_encounter(self.e.everyone)
  self.assertEqual(getattr(self.e,S.EXTRA)[0]['status'],'expired');self.restore();self.valid()
 def test_quick_gymnastics_inside_actual_splash_interrupt(self):
  self.family(T.FLIP);self.family(T.QUICK);self.begin(self.t,40);self.decision('quick_gymnastics',True)
  self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='actual reaction')
  before=AP.available(self.a)
  with self.assertRaises(PASSIVE.PassiveEventPending):self.use(self.t,self.a,'move/몸통박치기')
  self.e.choose_move_defense(self.e._passive_pending,self.a,use=True,options={'jump':{'destination':(2,3),'difficult':False,'clear_path':True}},reason='react with actual Splash Jump')
  self.assertEqual(AP.available(self.a),before-1);self.assertTrue(T.immune(self.a));self.valid()

 def test_acquired_quick_reflexes_executes_actual_dodge(self):
  self.family(T.REFLEX);self.begin(self.t,40);hp=self.a.hp
  self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':'ability/회피'}],reason='actual acquired Quick Reflexes Dodge')
  with self.assertRaises(PASSIVE.PassiveEventPending):self.use(self.t,self.a,'move/몸통박치기')
  self.e.choose_move_defense(self.e._passive_pending,self.a,use=True,options={},reason='use actual granted Dodge')
  self.assertEqual(self.a.hp,hp);self.assertFalse(F.activation_allowed(self.a,'ability/회피',{'kind':'daily','uses':1},engine=self.e));self.valid()

 def test_quick_jump_extra_shift_starts_at_actual_landing(self):
  self.family(T.QUICK);self.begin();self.decision('quick_gymnastics',{'path':[(2,4),(2,5)]})
  self.jump((2,3));self.assertEqual(self.a.pos,(2,5));self.assertFalse(self.t.aoo_used);self.assertEqual(self.a._action_history,['shift','free']);self.valid()
 def test_quick_failed_jump_waits_for_actual_gm_consequence_before_shift(self):
  self.family(T.QUICK);self.begin();self.decision('quick_gymnastics',{'path':[(2,3),(2,4)]})
  result=self.e.jump(self.a,(2,3),jump_id='qg-fail',difficult=True,difficulty_skill='곡예',difficulty_dc=100,difficulty_options={'fixed':[1,1,1,1,1,1]},clear_path=True,reason_text='actual difficult jump')
  self.assertIsInstance(result,__import__('common_checks').PendingDecision);self.assertEqual(self.a.pos,(2,2))
  J.resolve_failure(self.e,self.a,decision='abort',reason_text='GM keeps actual failed jump at origin');self.assertEqual(self.a.pos,(2,4));self.valid()
 def test_declined_quick_deferred_opportunity_ko_stops_original_attack(self):
  self.family(T.QUICK);self.begin();self.e.gm.set_position(self.t,(5,2),reason='actual distant target');self.e.gm.set_hp(self.a,1,reason='actual wounded attacker')
  self.decision('quick_gymnastics',False);hp=self.t.hp
  self.use(self.a,self.t,'move/물대포');self.assertTrue(self.a.fainted);self.assertEqual(self.t.hp,hp);self.assertTrue(self.u.aoo_used);self.valid()

 def test_quick_shift_actual_hazard_wait_restores_prefix_and_never_repeats_payment(self):
  scenario_rulings=deepcopy(self.rules.rulings)
  for trigger in ('hit','stand','jump'):
   with self.subTest(trigger=trigger):
    self.rules.rulings=deepcopy(scenario_rulings)
    self.setup();self.family(T.QUICK);self.begin();before=AP.available(self.a);hp=self.t.hp
    first,last=((2,4),(2,5)) if trigger=='jump' else ((2,3),(2,4))
    import effects_ext as EXT,effects as FX
    original=EXT.on_enter_cell
    def observed_entry(e,actor,point,**options):
     original(e,actor,point,**options)
     if actor.entity_id==self.a.entity_id and point==first:FX.run_effects(e,actor,actor,[{'type':'stage_change','stat':'def','delta':1,'if':'target was asleep'}],{'hit':True},'hazard/observed-conditional-entry')
    self.decision('quick_gymnastics',{'path':[first,last]})
    with patch.object(EXT,'on_enter_cell',side_effect=observed_entry):
     if trigger=='hit':
      with self.assertRaises(PASSIVE.PassiveEventPending):self.use(self.a,self.t,'move/몸통박치기')
      event=self.e._passive_pending;self.assertEqual(self.t.hp,hp)
     elif trigger=='stand':
      self.e.apply_status(self.a,'넘어짐');self.e.stand_up(self.a)
     else:self.e.jump(self.a,(2,3),jump_id='quick-held-path',difficult=False,clear_path=True,reason_text='actual Jump before optional Quick Shift')
    effect=next(r for r in TIME.records(self.a) if r.get('tumbler_quick'));self.assertEqual(self.a.pos,first);self.assertFalse(effect.get('shift_done'));self.assertEqual(effect['movement']['phase'],'entry_pending');self.assertEqual(AP.available(self.a),before-1)
    token=next(k for k,r in self.e._effect_dispatch_receipts.items() if r['status']=='condition_unknown');occurrence=self.e._effect_dispatch_receipts[token]['occurrence'];self.valid();self.restore()
    token=next(k for k,r in self.e._effect_dispatch_receipts.items() if r['occurrence']==occurrence and r['actor'] is self.a)
    self.e.resolve_effect_condition(self.a,token,target_was_asleep=True,reason='GM observes the actual authored hazard condition')
    if trigger=='hit':
     with patch.object(Engine,'accuracy_check',side_effect=AssertionError('actual attack accuracy already observed')):self.e.deliver_passive_event(event)
     self.assertLess(self.t.hp,hp)
    else:self.e.resume_tumbler_shift(self.a)
    self.assertEqual(self.a.pos,last);self.assertEqual(self.a.stages['def'],1);self.assertEqual(AP.available(self.a),before-1);self.assertEqual(self.a._action_history.count('free'),1);self.valid();self.restore();self.valid()

 def test_quick_paid_path_rejects_resume_after_its_triggering_turn(self):
  import effects_ext as EXT,effects as FX
  self.family(T.QUICK);self.begin();self.e.apply_status(self.a,'넘어짐');self.decision('quick_gymnastics',{'path':[(2,3),(2,4)]});original=EXT.on_enter_cell
  def entry(e,actor,point,**options):
   original(e,actor,point,**options)
   if actor.entity_id==self.a.entity_id and point==(2,3):FX.run_effects(e,actor,actor,[{'type':'stage_change','stat':'def','delta':1,'if':'target was asleep'}],{'hit':True},'hazard/quick-turn-boundary')
  with patch.object(EXT,'on_enter_cell',side_effect=entry):self.e.stand_up(self.a)
  token=next(k for k,r in self.e._effect_dispatch_receipts.items() if r['status']=='condition_unknown')
  self.e.resolve_effect_condition(self.a,token,target_was_asleep=True,reason='actual entry fact resolved before declining remaining movement')
  self.turn(self.t,30);self.reject(lambda:self.e.resume_tumbler_shift(self.a),'triggering turn');self.next_round()
  self.reject(lambda:self.e.resume_tumbler_shift(self.a),'triggering turn');self.assertEqual(self.a.pos,(2,3));self.valid()

 def test_splash_quick_entry_wait_preserves_child_and_original_attack_until_restore(self):
  import effects_ext as EXT,effects as FX
  self.family(T.FLIP);self.family(T.QUICK);self.begin(self.t,40);before=AP.available(self.a);hp=self.a.hp
  self.decision('quick_gymnastics',{'path':[(2,4),(2,5)]});self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='actual nested Jump and Quick movement')
  with self.assertRaises(PASSIVE.PassiveEventPending):self.use(self.t,self.a,'move/몸통박치기')
  event=self.e._passive_pending;original=EXT.on_enter_cell
  def entry(e,actor,point,**options):
   original(e,actor,point,**options)
   if actor.entity_id==self.a.entity_id and point==(2,4):FX.run_effects(e,actor,actor,[{'type':'stage_change','stat':'def','delta':1,'if':'target was asleep'}],{'hit':True},'hazard/nested-splash-quick-entry')
  with patch.object(EXT,'on_enter_cell',side_effect=entry):
   with self.assertRaises(PASSIVE.PassiveEventPending):self.e.choose_move_defense(event,self.a,use=True,options={'jump':{'destination':(2,3),'difficult':False,'clear_path':True}},reason='actual Splash with its nested Quick movement')
  self.assertEqual(self.a.pos,(2,4));self.assertEqual(self.a.hp,hp);self.assertEqual(AP.available(self.a),before-1);self.assertIs(self.e._active_turn_actor,self.a);self.valid();self.restore()
  token=next(k for k,r in self.e._effect_dispatch_receipts.items() if r['status']=='condition_unknown')
  self.e.resolve_effect_condition(self.a,token,target_was_asleep=True,reason='resolve actual nested entry condition')
  self.e.deliver_passive_event(event)
  self.assertEqual(self.a.pos,(2,5));self.assertLess(self.a.hp,hp);self.assertEqual(self.a.move_uses[T.SPLASH],1);self.assertEqual(AP.available(self.a),before-1);self.assertEqual(RESOURCES.pending(self.a).get('shift'),1);self.assertIs(self.e._active_turn_actor,self.t);self.valid();self.restore();self.valid()

 def test_bounce_hazard_destruction_uses_landing_cell_before_quick_shift(self):
  self.family(T.DEATH);self.family(T.FLIP);self.family(T.QUICK);self.begin();self.decision('quick_gymnastics',{'path':[(2,4),(2,5)]})
  for cell in ((2,3),(2,5)):self.e.gm.place_hazard(cell,'actual landing comparison',[{'type':'hp_loss','value':10}],reason='actual visible hazard')
  hp=self.a.hp
  self.e.declare_jump_move(self.a,self.t,T.BOUNCE,event_id='bounce-quick-landing',jump={'destination':(2,3),'difficult':False,'clear_path':True},destroy_hazards=True,attack=False,reason='choose destruction at actual landing and decline optional attack')
  self.use(self.a,self.t,T.BOUNCE);self.assertEqual(self.a.pos,(2,5));self.assertEqual(self.a.hp,hp);self.assertNotIn((2,3),self.e.hazards);self.assertIn((2,5),self.e.hazards);self.valid()
