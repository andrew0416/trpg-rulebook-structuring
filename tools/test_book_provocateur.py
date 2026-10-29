"""Entire Provocateur class: actual acquisition, public actions, consumers and distinct lifetimes."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from provocateur_fixture import ProvocateurScene
from engine import Rules,Engine
import provocateur as P
import combat_timing as TIME
import frequency as F
import ability_transitions as ABILITIES
import action_points as AP
import condition_instances as CONDITIONS
import combat_maneuvers as M
import condition_recovery as RECOVERY
import trainer_retraining as RETRAIN
import state_grants as GRANTS

class ProvocateurTests(ProvocateurScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 def test_class_template_acquisition_speed_and_independent_move_sources(self):
  self.assertEqual(len(P.DEFINITIONS),7);before=self.a.stats['spe'];self.acquire(P.CLASS)
  self.assertEqual(self.a.stats['spe'],before+1);self.assertTrue({'move/천사의키스','move/도발'}<=set(self.a.moves))
  self.assertIsNone(P.acquired(self.a,P.POWER));self.assertEqual(set(self.a.spec['feats']),{P.CLASS})
  self.acquire(P.MIXED);self.assertEqual(self.a.stats['spe'],before+2)
  self.assertTrue({'move/악마의키스','move/트집'}<=set(self.a.moves));self.valid();self.restore();self.valid()
 def test_prerequisites_and_selection_rejections_are_atomic(self):
  self.reject(lambda:self.acquire(P.QUICK),'prerequisite');self.acquire(P.CLASS)
  self.skills(매력=3,교활=3,협박=3)
  self.reject(lambda:self.acquire(P.QUICK),'skill ranks');self.reject(lambda:self.acquire(P.POWER),'skill ranks')
  self.skills(매력=4);self.acquire(P.QUICK)
  self.reject(lambda:self.acquire(P.GAZE),'skill ranks');self.reject(lambda:self.acquire(P.FIDDLE),'prerequisite')
  self.reject(lambda:self.acquire(P.PUSH,selection={'edge':'edge/몬스터볼'}),'already owned Demoralize')
 def test_declared_extended_social_ranks_keep_native_acquisition_and_restore(self):
  self.reject(lambda:self.e.gm.set_skill(self.a,'매력',7,reason='undeclared social rank'),'unresolved ordinary numeric')
  self.rules.rulings.set_mech('gameplay/skill-rank-dice','by_rank_name.초월',
   {'rank':7,'dice':'7d6','eng':'Transcendent'},reason='U-001 explicitly declared campaign rank',rules=self.rules)
  for skill in ('매력','교활'):self.e.gm.set_skill(self.a,skill,7,reason='actual declared extended social skill')
  self.whole()
  for uid in P.FEATURES:self.assertEqual(P.acquired(self.a,uid)['snapshot']['skills']['매력'],7)
  self.valid();self.restore();self.valid()
  for uid in P.FEATURES:self.assertEqual(P.acquired(self.a,uid)['snapshot']['skills']['교활'],7)
 def test_push_optional_decline_and_low_intimidate_waiver(self):
  self.skills(협박=1);self.acquire(P.CLASS);self.acquire(P.PUSH)
  self.assertTrue(P.waive_demoralize(self.a));self.assertIn(P.DEMO,self.a.spec['edges'])
  self.begin();row=self.use(self.a,self.t,'move/째려보기',face=18)
  self.assertTrue(row['results'][self.t.entity_id]['hit']);self.assertLess(self.t.hp,self.t.max_hp)
  self.setup();self.acquire(P.CLASS);self.acquire(P.PUSH,selection={'edge':None})
  self.assertNotIn(P.DEMO,self.a.spec['edges']);self.assertFalse(P.waive_demoralize(self.a));self.valid()
 def test_existing_demoralize_replacement_requires_actual_qualified_edge(self):
  self.setup(edges=['edge/호감인',P.DEMO]);self.acquire(P.CLASS)
  chosen={'edge':'edge/몬스터볼','requirements':self.policy('edge/몬스터볼','기술학',3)}
  self.skills(기술학=2);self.reject(lambda:self.acquire(P.PUSH,selection=chosen),'prerequisites')
  self.skills(기술학=3);self.acquire(P.PUSH,selection=chosen)
  self.assertIn('edge/몬스터볼',self.a.spec['edges']);self.assertEqual(self.a.spec['edges'].count(P.DEMO),1)
  self.reject(lambda:self.acquire(P.PUSH,selection={'edge':None}),'replay');self.valid()
 def test_source_loss_revokes_only_push_granted_edge_and_stat(self):
  self.acquire(P.CLASS);self.acquire(P.PUSH);before=self.a.stats['spe']
  dependencies={RETRAIN.owned_source(self.e,self.a,uid):[] for uid in RETRAIN._owned(self.a) if uid not in (P.PUSH,P.DEMO)}
  RETRAIN.retrain(self.e,self.a,P.PUSH,request_id='remove-push',reason='actual retraining',gm_decision={'allowed':True,'reason':'actual consultation'},retained_dependencies=dependencies)
  self.assertNotIn(P.DEMO,self.a.spec['edges']);self.assertEqual(self.a.stats['spe'],before-1)
  self.assertIn('move/도발',self.a.moves);self.valid()
 def test_push_miss_refunds_quota_but_keeps_actual_completion_and_last_move(self):
  self.acquire(P.CLASS);self.acquire(P.PUSH);self.begin()
  row=self.use(self.a,self.t,'move/천사의키스',face=1)
  self.assertFalse(row['results'][self.t.entity_id]['hit']);self.assertEqual(self.a.last_move,'move/천사의키스')
  self.assertNotIn('move/천사의키스',self.a.move_uses);self.assertTrue(F.move_allowed(self.e,self.a,'move/천사의키스')[0])
  self.next_round();hit=self.use(self.a,self.t,'move/천사의키스',face=15)
  self.assertTrue(hit['results'][self.t.entity_id]['hit']);self.assertEqual(self.a.move_uses['move/천사의키스'],1)
 def test_push_area_all_miss_and_mixed_hit_charge_once(self):
  self.acquire(P.CLASS);self.acquire(P.PUSH);self.begin()
  for face in (1,20):
   with patch.object(Engine,'d20',return_value=face):self.e.use_move_on(self.a,self.t,'move/째려보기',self.e.everyone,aim=(5,2),set_damage=True)
   row=list(self.e._move_completions.values())[-1]
   self.assertGreaterEqual(len(row['targets']),2)
   self.assertEqual(self.a.move_uses.get('move/째려보기',0),0 if face==1 else 1)
   self.next_round()
  self.valid()
 def test_push_17_18_19_status_and_nonsocial_tick_boundaries(self):
  for face in (17,18,19):
   with self.subTest(face=face):
    self.setup();self.acquire(P.CLASS);self.acquire(P.PUSH);self.begin()
    self.use(self.a,self.t,'move/째려보기',face=face)
    self.assertEqual(self.t.max_hp-self.t.hp,0 if face==17 else self.e.tick(self.t))
  self.setup();self.acquire(P.CLASS);self.acquire(P.PUSH);self.begin();self.use(self.a,self.t,'move/꼬리흔들기',face=18)
  self.assertEqual(self.t.hp,self.t.max_hp)
 def test_quick_wit_learned_social_swift_and_original_frequency(self):
  self.acquire(P.CLASS);self.acquire(P.QUICK);self.begin()
  with patch.object(Engine,'d20',return_value=15):self.e.quick_wit(self.a,self.t,move_id='move/천사의키스',set_damage=True)
  self.assertEqual(self.a.budget['swift'],0);self.assertEqual(self.a.budget['standard'],1)
  self.assertEqual(self.a.move_uses['move/천사의키스'],1)
  self.reject(lambda:self.e.quick_wit(self.a,self.t,move_id='move/천사의키스'),'연속|다른 턴|소진')
  self.reject(lambda:self.e.quick_wit(self.a,self.t,move_id='move/몸통박치기'),'Social')
 def test_quick_wit_manipulate_quota_and_three_scene_uses(self):
  self.acquire(P.CLASS);self.acquire(P.QUICK);self.begin()
  for i,kind in enumerate(('bon_mot','terrorize','flirt')):
   self.assertTrue(self.e.quick_wit(self.a,self.t,manipulation=kind,defender_skill='집중',fixed_accuracy=15,
    challenger_options={'fixed':[6]*5},defender_options={'fixed':[1]*3}))
   self.assertEqual(self.a.budget['standard'],1);self.assertEqual(self.a.budget['swift'],0)
   self.next_round()
  self.reject(lambda:self.e.quick_wit(self.a,self.u,manipulation='terrorize',defender_skill='집중',fixed_accuracy=15,
   challenger_options={'fixed':[6]*5},defender_options={'fixed':[1]*3}),'Scene frequency')
 def test_power_all_seven_hit_and_miss_install_one_full_round(self):
  for mid in P.MOVES:
   for face in (1,15):
    with self.subTest(mid=mid,face=face):
     self.setup();self.family(P.POWER);self.begin();self.trigger(mid,face)
     rows=[r for r in TIME.records(self.t) if r['source']==P.POWER]
     self.assertEqual(len(rows),1);self.assertEqual(rows[0]['count_deadline'],(self.e.round_no+1,30))
     self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone)
     self.e.at_initiative_count(31);self.assertIn(rows[0],TIME.records(self.t))
     self.e.at_initiative_count(30);self.assertNotIn(rows[0],TIME.records(self.t))
 def test_power_prevents_real_critical_and_effect_range(self):
  for mid,attack in ((P.MOVES[0],'move/몸통박치기'),(P.MOVES[1],'move/화염방사')):
   with self.subTest(mid=mid):
    self.setup();self.family(P.POWER);self.begin();self.trigger(mid,1);self.turn(self.t)
    with patch.object(Engine,'d20',return_value=20):row=self.use(self.t,self.b,attack,20)
    if mid==P.MOVES[0]:self.assertFalse(any('치명타!' in str(x) for x in self.e.log_lines[-20:]))
    else:self.assertNotIn('화상',self.b.conditions)
 def test_power_slow_evasion_accuracy_and_all_saving_checks_are_consumed(self):
  self.family(P.POWER);self.begin();self.trigger(P.MOVES[2],1);self.assertIn('둔화',self.t.conditions)
  self.assertEqual(self.e.move_profile(self.t)[0],3)
  for mid,key in ((P.MOVES[3],'evasion_modifier'),(P.MOVES[4],'accuracy_modifier'),(P.MOVES[6],'save_modifier')):
   self.setup();self.family(P.POWER);self.begin();self.trigger(mid,1)
   if key=='save_modifier':
    for cond in (None,'독','혼란'):
     save=RECOVERY.saving_check(self.e,self.t,cond,16,fixed=18);self.assertEqual(save['dc'],19);self.assertFalse(save['passed'])
   elif key=='evasion_modifier':self.assertEqual(self.t.evasion('물리'),0)
   else:
    self.turn(self.t)
    hit,nat,crit=self.e.accuracy_check(self.t,self.b,self.rules.move('move/몸통박치기'),fixed_roll=4)
    self.assertFalse(hit);self.assertEqual(nat,4)
 def test_power_torment_damage_penalty_only_against_provocateur_allies(self):
  self.family(P.POWER);move=self.rules.move('move/몸통박치기')
  baselines={key:self.e.roll_damage(self.t,getattr(self,key),move,set_damage=True) for key in ('a','b','u')}
  self.begin();self.trigger(P.MOVES[5],1)
  for key in baselines:
   self.assertEqual(self.e.roll_damage(self.t,getattr(self,key),move,set_damage=True),baselines[key]-(10 if key=='b' else 0))
 def test_fiddle_requires_actual_hit_and_per_move_scene_once(self):
  self.whole();self.begin();token=self.trigger(P.MOVES[2],1)
  self.reject(lambda:self.e.play_them_like_a_fiddle(self.a,self.t,token),'actual hit')
  self.next_round();token=self.trigger(P.MOVES[2]);self.e.play_them_like_a_fiddle(self.a,self.t,token)
  self.assertEqual(self.t.stages['def'],-2);self.assertEqual(self.t.stages['spd'],-2)
  self.next_round();token=self.trigger(P.MOVES[2]);self.reject(lambda:self.e.play_them_like_a_fiddle(self.a,self.t,token),'used this Scene')
 def test_fiddle_three_uses_scene_total_is_shared_across_effects(self):
  self.whole();self.begin()
  for mid in (P.MOVES[2],P.MOVES[4],P.MOVES[6]):
   self.fiddle(mid);self.next_round()
  token=self.trigger(P.MOVES[0]);self.reject(lambda:self.e.play_them_like_a_fiddle(self.a,self.t,token),'Scene frequency')
 def test_fiddle_infatuation_cannot_cure_but_hp_healing_still_works_until_scene(self):
  self.whole();self.begin();self.fiddle(P.MOVES[0]);self.assertIn('헤롱헤롱',self.t.conditions)
  self.assertIs(CONDITIONS.beloved(self.t)[0],self.a);self.assertFalse(self.e.cure_status(self.t,'헤롱헤롱'))
  self.e.take_damage(self.t,20);hp=self.t.hp;self.e.heal(self.t,10,source_kind='move');self.assertEqual(self.t.hp,hp+10)
  self.e.end_scene(round_elapsed_seconds=0);self.assertNotIn('헤롱헤롱',self.t.conditions);self.valid()
 def test_fiddle_infatuation_breather_does_not_cure_and_immunity_stays(self):
  self.whole();self.begin();self.fiddle(P.MOVES[0]);self.turn(self.t)
  with patch.object(Engine,'d20',return_value=20):result=self.e.take_breather(self.t,request_id='infatuation-breather',save_dc=12,save_reason='explicit table DC',save_cost='full',fixed_save=20,path=[(4,2),(5,3),(5,4),(5,5),(5,6),(5,7),(5,8)],retreat_reason='full land allowance away from both foes')
  self.assertTrue(result['completed']);self.assertEqual(self.t.budget['standard'],0);self.assertEqual(self.t.budget['shift'],0)
  self.assertIn('헤롱헤롱',self.t.conditions)
  self.setup(abilities=['둔감']);self.whole();self.begin();self.fiddle(P.MOVES[0])
  self.assertNotIn('헤롱헤롱',self.t.conditions);self.assertFalse(P.blocked(self.t,'uncurable_infatuation'))
 def test_fiddle_confide_selects_actual_scene_history_not_only_last_move(self):
  self.whole();self.begin(self.t);self.use(self.t,self.b,'move/몸통박치기');self.next_round(self.t)
  self.use(self.t,self.b,'move/째려보기');self.next_round(self.a)
  token=self.trigger(P.MOVES[1]);self.reject(lambda:self.e.play_them_like_a_fiddle(self.a,self.t,token,move_choice='move/화염방사'),'used this Scene')
  self.e.play_them_like_a_fiddle(self.a,self.t,token,move_choice='move/몸통박치기')
  self.assertEqual(CONDITIONS.records(self.t,'사슬묶기')[0]['effect']['move_id'],'move/몸통박치기')
  self.next_round();self.assertIn('사슬묶기',self.t.conditions)
  self.assertFalse(F.move_allowed(self.e,self.t,'move/몸통박치기')[0]);self.e.cure_status(self.t,'사슬묶기');self.assertNotIn('사슬묶기',self.t.conditions)
 def test_fiddle_confide_old_scene_use_does_not_qualify(self):
  self.whole();self.begin(self.t);self.use(self.t,self.b,'move/몸통박치기');self.e.end_scene(round_elapsed_seconds=0)
  self.begin();token=self.trigger(P.MOVES[1]);self.reject(lambda:self.e.play_them_like_a_fiddle(self.a,self.t,token,move_choice='move/몸통박치기'),'used this Scene')
 def test_fiddle_sweet_kiss_prevents_disengage_only_while_confused(self):
  self.whole();self.begin();self.fiddle(P.MOVES[3]);self.turn(self.t)
  self.reject(lambda:self.e.disengage(self.t,(5,1)),'Fiddle forbids')
  self.e.cure_status(self.t,'혼란');self.assertFalse(P.blocked(self.t,'confusion_opportunities'))
  self.assertTrue(self.e.disengage(self.t,(5,1)))
 def test_fiddle_confusion_self_hit_triggers_each_adjacent_enemy_once(self):
  self.rules=Rules(str(ROOT),ruleset='core-confusion-feb2016');self.setup()
  self.whole();self.e.gm.set_position(self.a,(3,2),reason='actual adjacent foe');self.e.gm.set_position(self.b,(4,1),reason='actual second adjacent foe')
  self.begin();self.fiddle(P.MOVES[3]);self.turn(self.t)
  with patch('roll_pools.die',return_value=1):self.use(self.t,self.a,'move/몸통박치기',face=1)
  self.assertTrue(self.a.aoo_used);self.assertTrue(self.b.aoo_used)
  row=[r for r in self.e._move_completions.values() if r['actor'] is self.t][-1]
  hp=self.t.hp;self.e.resume_confusion_completion(row['id']);self.assertEqual(self.t.hp,hp)
 def test_fiddle_taunt_next_damage_hit_dice_once_miss_status_do_not_consume(self):
  self.whole();self.begin();self.fiddle(P.MOVES[4]);self.turn(self.b)
  self.use(self.b,self.t,'move/째려보기');self.assertTrue(P.blocked(self.t,'next_damage_dice'))
  self.next_round(self.b,count=31);self.use(self.b,self.t,'move/몸통박치기',face=1);self.assertTrue(P.blocked(self.t,'next_damage_dice'))
  self.turn(self.a,count=31)
  baseline=self.e.roll_damage(self.a,self.t,self.rules.move('move/화염방사'),set_damage=True);before=self.t.hp
  with patch('roll_pools.die',return_value=4):self.use(self.a,self.t,'move/화염방사',face=15)
  self.assertEqual(before-self.t.hp,baseline+22)
  self.assertFalse(P.blocked(self.t,'next_damage_dice'));history=self.t.spec['provocateur_damage_history']
  self.assertEqual(history[-1]['faces'],[4,4,4]);self.assertEqual(history[-1]['total'],22)
 def test_fiddle_taunt_unspent_bonus_expires_at_same_count(self):
  self.whole();self.begin();self.fiddle(P.MOVES[4]);self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone)
  self.e.at_initiative_count(31);self.assertTrue(P.blocked(self.t,'next_damage_dice'))
  self.e.at_initiative_count(30);self.assertFalse(P.blocked(self.t,'next_damage_dice'))
 def test_fiddle_torment_optional_cancel_selected_suppression_and_encounter_end(self):
  self.setup(abilities=['불면','단순']);self.whole();self.begin();token=self.trigger(P.MOVES[5])
  before=self.a.budget.copy();self.assertEqual(self.e.play_them_like_a_fiddle(self.a,self.t,token)['status'],'cancelled');self.assertEqual(self.a.budget,before)
  self.e.play_them_like_a_fiddle(self.a,self.t,token,ability_choice='ability/불면')
  self.assertFalse(ABILITIES.active(self.t,'ability/불면'));self.assertTrue(ABILITIES.active(self.t,'ability/단순'))
  self.restore();self.next_round();self.assertFalse(ABILITIES.active(self.t,'ability/불면'))
  self.e.end_encounter(round_elapsed_seconds=0);self.assertTrue(ABILITIES.active(self.t,'ability/불면'));self.valid()
 def test_fiddle_torment_protected_ability_not_suppressed(self):
  self.setup(abilities=['멀티타입']);self.whole();self.begin();self.fiddle(P.MOVES[5],ability_choice='ability/멀티타입')
  self.assertTrue(ABILITIES.active(self.t,'ability/멀티타입'));self.valid()
 def test_fiddle_lovely_kiss_evasion_is_scene_not_round(self):
  self.whole();self.begin();self.fiddle(P.MOVES[6]);self.next_round()
  self.assertTrue(any(r.get('evasion_modifier')==-2 for r in TIME.records(self.t)))
  self.e.end_scene(round_elapsed_seconds=0);self.assertFalse(any(r.get('evasion_modifier')==-2 for r in TIME.records(self.t)))
 def test_gaze_all_three_effects_cone_all_foes_two_ap_standard_no_opposed_rng(self):
  for kind in M.MANIPULATIONS:
   with self.subTest(kind=kind):
    self.setup();self.family(P.GAZE);self.begin();before=AP.available(self.a);rng=self.e.rng.getstate()
    with patch.object(Engine,'opposed_check',side_effect=AssertionError('Gaze must not oppose')):
     result=self.e.enchanting_gaze(self.a,kind,aim=(5,2))
    self.assertEqual(len(result),2);self.assertTrue(all(result));self.assertEqual(self.a.budget['standard'],0)
    self.assertEqual(AP.available(self.a),before-2);self.assertEqual(self.e.rng.getstate(),rng)
    for target in (self.t,self.u):self.assertTrue(any(r.get('manipulation')==kind for r in TIME.records(target)))
    self.assertFalse(TIME.records(self.b));self.valid()
 def test_gaze_bypasses_maneuver_quota_without_changing_ordinary_quota(self):
  self.family(P.GAZE);self.begin();opts=dict(defender_skill='집중',fixed_accuracy=15,challenger_options={'fixed':[6]*5},defender_options={'fixed':[1]*3})
  self.e.manipulate(self.a,self.t,'terrorize',**opts);self.next_round()
  self.assertEqual(self.e.enchanting_gaze(self.a,'terrorize',aim=(5,2)),[True,True]);self.next_round()
  self.reject(lambda:self.e.manipulate(self.a,self.t,'terrorize',**opts),'already been used')
 def test_gaze_insufficient_ap_and_invalid_choice_preserve_everything(self):
  self.family(P.GAZE);self.begin();AP.spend(self.a,AP.available(self.a)-1)
  self.reject(lambda:self.e.enchanting_gaze(self.a,'terrorize',aim=(5,2)),'2 AP')
  self.reject(lambda:self.e.enchanting_gaze(self.a,'unknown',aim=(5,2)),'Manipulate')
 def test_snapshot_preserves_actual_recipients_usage_and_independent_lifetimes(self):
  self.whole();self.begin();self.fiddle(P.MOVES[4]);self.restore()
  rec=next(r for r in TIME.records(self.t) if r.get('next_damage_dice'));self.assertIs(rec['attacker'],self.a)
  self.assertEqual(F.state(self.a)['activations'][P.FIDDLE]['used'],1);self.valid()

 def test_native_detect_status_return_refunds_push_installs_miss_power_and_refuses_fiddle(self):
  import passive_events as PASSIVE,move_completion as COMPLETE
  self.whole();self.e.gm.set_move(self.t,'move/판별',reason='actual learned Detect');self.begin()
  self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,'source':'move/판별'}],reason='actual status hit Detect')
  with patch.object(Engine,'d20',return_value=15):
   with self.assertRaises(PASSIVE.PassiveEventPending):self.e.use_move(self.a,self.t,P.MOVES[4])
  event=self.e._passive_pending
  self.e.choose_move_defense(event,self.t,use=True,reason='native Detect on actual social hit')
  row=next(r for r in self.e._move_completions.values() if r['actor'] is self.a)
  self.assertEqual(row['phase'],'complete');self.assertFalse(COMPLETE.recipient_result(row,self.t)['hit'])
  self.assertNotIn(P.MOVES[4],self.a.move_uses)
  self.assertTrue(any(r.get('accuracy_modifier')==-3 for r in TIME.records(self.t)))
  self.reject(lambda:self.e.play_them_like_a_fiddle(self.a,self.t,row['id']),'actual hit')
  self.valid()
 def test_area_mixed_hit_uses_actual_recipients_and_one_fiddle_activation(self):
  import move_completion as COMPLETE
  self.whole();self.begin()
  with patch.object(Engine,'d20',return_value=4):self.e.use_move_on(self.a,self.t,P.MOVES[2],self.e.everyone,aim=(5,2))
  row=list(self.e._move_completions.values())[-1]
  self.assertFalse(COMPLETE.recipient_result(row,self.t)['hit']);self.assertTrue(COMPLETE.recipient_result(row,self.u)['hit'])
  self.assertEqual(self.a.move_uses[P.MOVES[2]],1)
  self.reject(lambda:self.e.play_them_like_a_fiddle(self.a,self.t,row['id']),'actual hit')
  result=self.e.play_them_like_a_fiddle(self.a,self.u,row['id'])
  self.assertEqual(result['targets'],[self.u.entity_id]);self.assertEqual(self.u.stages['def'],-2);self.assertEqual(self.u.stages['spd'],-2)
  self.assertEqual(self.t.stages['def'],0);self.assertEqual(F.state(self.a)['activations'][P.FIDDLE]['used'],1)
  before=len(TIME.records(self.u));COMPLETE.refresh(self.e);self.assertEqual(len(TIME.records(self.u)),before);self.valid()

 def test_quick_wit_pending_detect_survives_restore_without_repaying_or_rerolling(self):
  import passive_events as PASSIVE,move_completion as COMPLETE
  self.family(P.QUICK);self.e.gm.set_move(self.t,'move/판별',reason='actual learned Detect');self.begin()
  self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,'source':'move/판별'}],reason='actual Quick Wit status defense')
  with patch.object(Engine,'d20',return_value=15):
   with self.assertRaises(PASSIVE.PassiveEventPending):self.e.quick_wit(self.a,self.t,move_id=P.MOVES[3])
  event=self.e._passive_pending;self.assertEqual(F.state(self.a)['activations'][P.QUICK]['used'],1)
  self.assertEqual(self.a.budget['swift'],0);self.assertEqual(self.a.budget['standard'],1)
  self.restore()
  with patch.object(Engine,'d20',side_effect=AssertionError('do not reroll the existing hit')):
   self.e.choose_move_defense(event,self.t,use=True,reason='continue native Quick Wit hit')
  row=next(r for r in self.e._move_completions.values() if r['actor'] is self.a)
  self.assertFalse(COMPLETE.recipient_result(row,self.t)['hit']);self.assertEqual(F.state(self.a)['activations'][P.QUICK]['used'],1)
  self.assertEqual(self.a.move_uses[P.MOVES[3]],1);self.valid()
 def test_timed_effect_payload_and_optional_edge_cannot_diverge_from_sources(self):
  self.whole();self.begin();self.trigger(P.MOVES[3],1);self.valid()
  rec=next(r for r in TIME.records(self.t) if r['source']==P.POWER);rec['evasion_modifier']=-9
  self.assertFalse(self.e.validate_state()['valid']);rec['evasion_modifier']=-3
  sid='feature:'+self.a.entity_id+':'+P.PUSH;source=self.a.spec[GRANTS.KEY]['sources'][sid]
  source['provocateur_edge']='edge/몬스터볼';self.assertFalse(self.e.validate_state()['valid'])
  source['provocateur_edge']=P.DEMO;self.valid()

 def test_push_replacement_edge_registration_is_owned_and_revoked_with_its_parent(self):
  self.setup(edges=['edge/호감인',P.DEMO]);self.acquire(P.CLASS)
  self.acquire(P.PUSH,selection={'edge':'edge/몬스터볼','requirements':self.policy('edge/몬스터볼','기술학',3)})
  parent='feature:'+self.a.entity_id+':'+P.PUSH;child='feature:'+self.a.entity_id+':edge/몬스터볼'
  self.assertIn(child,self.a.spec[GRANTS.KEY]['sources'][parent]['effect_sources'])
  dependencies={RETRAIN.owned_source(self.e,self.a,uid):[] for uid in RETRAIN._owned(self.a) if uid not in (P.PUSH,'edge/몬스터볼')}
  RETRAIN.retrain(self.e,self.a,P.PUSH,request_id='retrain-replacement',reason='actual removal',gm_decision={'allowed':True,'reason':'table consultation'},retained_dependencies=dependencies)
  self.assertNotIn('edge/몬스터볼',self.a.spec['edges']);self.assertIn(P.DEMO,self.a.spec['edges'])
  self.assertNotIn(child,self.a.spec[GRANTS.KEY]['sources']);self.valid()
