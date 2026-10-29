"""Full Martial Artist use paths through actual native acquisitions and turns."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import trainer_feature_acquisition as T
import martial_artist as MA
import state_codec as CODEC
import action_points as AP
import class_move_grants as CM
import turn as TURN
import body_state as BODY

STYLES={
 '근성':[['받아던지기','두번차기'],['배대뒤치기','깨트리기'],['업어후리기','인파이트']],
 '정신력':[['태권당수','기충전'],['안다리걸기','로킥'],['크로스촙','인파이트']],
 '철주먹':[['마하펀치','두번차기'],['연속펀치','깨트리기'],['스카이어퍼','인파이트']],
 '유연':[['경혈찌르기','기충전'],['카운터','파워트릭'],['인파이트','로킥']],
 '이판사판':[['돌려차기','두번차기'],['점프킥','깨트리기'],['무릎차기','인파이트']],
 '테크니션':[['손바닥치기','두번차기'],['패스트가드','깨트리기'],['트리플킥','인파이트']]}

class MartialArtistTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old)
  self.setup()
 def setup(self,style='철주먹',combat=6):
  self.e=Engine(self.rules,seed=347209);self.e.grid=Grid(12,12)
  def actor(name,side,pos,speed):
   spec=dict(id='trainer/'+name,name=name,kind='trainer',level=30,size='중형',weight_class=3,weight_kg=30,
    stats=dict(hp=100,atk=10,**{'def':10},spa=10,spd=10,spe=speed),moves=['move/몸통박치기'],abilities=[],classes=[],feats=[],edges=[],
    feature_choices={},skills={'전투':combat,'육상':6,'곡예':6,'은신':6},movement={'land':6,'power':4,'high_jump':0,'sky':0},exp_bank=100)
   if name=='martial':spec['edges']=['edge/기본-무술']
   c=Combatant(self.rules,spec);self.e.gm.add_combatant(c,pos=pos,side=side,reason='actual observed Martial Artist scene')
   prepare_body(self.e,c,size='중형',offsets=[(0,0)],reason='actual single-cell body');return c
  self.a=actor('martial','party',(3,3),30);self.t=actor('foe','foe',(4,3),20);self.u=actor('other','foe',(2,3),10)
  self.e.gm.set_position(self.u,(9,9),reason='uninvolved foe initially away')
  self.chosen=style
 def acquire(self,style=None,training=0,features=(MA.ACHIEVEMENT,)):
  T.acquire_martial_artist(self.e,self.a,acquisition_request_id='martial/class',selected_ability=style or self.chosen,lifecycle_policy=T.LIFECYCLE_WHILE_OWNED)
  for rank,pair in enumerate(STYLES[style or self.chosen][:training],1):
   T.acquire_static(self.e,self.a,MA.TRAINING,rank=rank,branch=[self.rules.move_id(x) for x in pair],acquisition_request_id='martial/training/'+str(rank))
  for feat in features:T.acquire_static(self.e,self.a,feat,acquisition_request_id='martial/'+feat)
 def start(self,a=None,count=30):
  self.e.start_round(self.e.everyone);self.e.start_of_turn(a or self.a,initiative_count=count)
 def next(self,a=None,count=30):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.end_round();self.start(a,count)
 def use(self,mid,face=20,target=None):
  with patch.object(Engine,'d20',return_value=face):return self.e.use_move(self.a,target or self.t,self.rules.move_id(mid),set_damage=True)
 def restore(self):
  ids=[self.a.entity_id,self.t.entity_id,self.u.entity_id]
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  import world_entities as W
  self.a,self.t,self.u=[W.actor_index(self.e)[i] for i in ids]
 def valid(self):
  r=self.e.validate_state();self.assertTrue(r['valid'],r['issues'])
 def rejected(self,fn,pattern):return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)
 def options(self,win=False):
  return dict(challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,
   challenger_options={'fixed':[6 if win else 1]*6},defender_options={'fixed':[1 if win else 6]*6})

 def test_six_actual_class_acquisitions_all_ranks_and_full_domain_keep_one_chosen_achievement(self):
  seen=set()
  for style in STYLES:
   with self.subTest(style=style):
    self.setup(style);self.acquire(training=3,features=(MA.ACHIEVEMENT,MA.KUNG,MA.SECOND))
    self.assertEqual(MA.style(self.a),MA._data['styles']['ability/'+style])
    self.assertEqual(self.a.spec['feat_ranks'][MA.TRAINING],3)
    expected={self.rules.move_id(n) for pair in STYLES[style] for n in pair};seen.update(expected)
    self.assertTrue(expected<=set(self.a.moves));self.assertEqual(len(MA.records(self.a,MA.TRAINING,True)),3)
    import acquired_features as A
    self.assertEqual(A.count_for_class(self.a,MA.CLASS),7)
    self.restore();self.valid()
  self.assertEqual(seen,{self.rules.move_id(n) for group in CM.RANKED[MA.TRAINING].values() for n in group})

 def test_acquisition_prerequisites_rank_choices_and_replay_are_atomic(self):
  self.rejected(lambda:T.acquire_static(self.e,self.a,MA.ACHIEVEMENT,acquisition_request_id='no-class'),'class|selection|receipt')
  self.acquire(features=())
  self.rejected(lambda:T.acquire_static(self.e,self.a,MA.KUNG,acquisition_request_id='no-training'),'Rank 1')
  self.rejected(lambda:T.acquire_static(self.e,self.a,MA.TRAINING,rank=2,branch=['move/깨트리기','move/연속펀치'],acquisition_request_id='skip'),'next')
  self.rejected(lambda:T.acquire_static(self.e,self.a,MA.TRAINING,rank=1,branch=['move/경혈찌르기','move/두번차기'],acquisition_request_id='wrong-ability'),'Ability')
  moves=['마하펀치','두번차기'];r=T.acquire_static(self.e,self.a,MA.TRAINING,rank=1,branch=moves,acquisition_request_id='real')
  self.assertEqual(T.acquire_static(self.e,self.a,MA.TRAINING,rank=1,branch=moves,acquisition_request_id='real')['integrity'],r['integrity'])
  self.rejected(lambda:T.acquire_static(self.e,self.a,MA.TRAINING,rank=1,branch=['move/로킥','move/기충전'],acquisition_request_id='real'),'intent')

 def test_kung_fu_actual_opportunity_rock_smash_effect_range_and_default_struggle(self):
  self.acquire(training=1,features=(MA.KUNG,));self.start(self.t)
  MA.arm(self.e,self.a,'kung_fu')
  before=self.t.hp
  with patch.object(Engine,'d20',return_value=15):TURN.trigger_aoo(self.e,self.t,'actual departure',[self.a])
  self.assertLess(self.t.hp,before);self.assertEqual(self.t.stages['def'],-1);self.assertTrue(self.a.aoo_used)
  self.assertEqual(self.a.last_move,MA.ROCK)
  self.assertEqual(MA.effect_range(self.e,self.a,self.rules.move(MA.ROCK)),0)
  after=self.t.hp;TURN.trigger_aoo(self.e,self.t,'same round',[self.a]);self.assertEqual(after,self.t.hp)
  self.next(self.t);MA.disarm(self.e,self.a,'kung_fu')
  with patch.object(Engine,'d20',return_value=20):TURN.trigger_aoo(self.e,self.t,'ordinary',[self.a])
  self.assertTrue(any('발버둥' in line and '명중 d20=' in line for line in self.e.log_lines));self.restore();self.valid()

 def test_second_strike_uses_real_failed_opposed_push_trip_grapple_but_not_accuracy_miss(self):
  for method in ('push','trip','grapple'):
   with self.subTest(method=method):
    self.setup();self.acquire(features=(MA.SECOND,));self.start();MA.arm(self.e,self.a,'second_strike',move=MA.ROCK)
    before=self.t.hp
    with patch.object(Engine,'d20',return_value=20):getattr(self.e,method)(self.a,self.t,**self.options())
    self.assertLess(self.t.hp,before);self.assertEqual(self.a.budget['standard'],0)
    self.assertNotIn('second_strike',self.a.spec[MA.ARMED]);self.valid()
  self.setup();self.acquire(features=(MA.SECOND,));self.start();MA.arm(self.e,self.a,'second_strike',move='struggle')
  before=self.t.hp;self.e.trip(self.a,self.t,**dict(self.options(),fixed_accuracy=1))
  self.assertEqual(self.t.hp,before);self.assertIn('second_strike',self.a.spec[MA.ARMED])

 def test_heightened_intensity_uses_two_ap_shift_and_native_focus_without_learning(self):
  self.setup('정신력');self.acquire();self.start();before=AP.available(self.a)
  self.assertNotIn(MA.FOCUS,self.a.moves);MA.heightened_intensity(self.e,self.a)
  self.assertEqual(AP.available(self.a),before-2);self.assertEqual(self.a.budget,{'standard':1,'shift':0,'swift':1})
  self.assertNotIn(MA.FOCUS,self.a.moves)
  import declarative_move_contracts as D
  self.assertLess(D.critical_threshold(self.a,20),20)
  self.restore();self.valid()

 def test_pummeling_real_completed_hits_target_bonus_rank_cap_and_missed_turn_expiry(self):
  self.acquire(training=2);self.start();MA.arm(self.e,self.a,'pummeling_momentum',target=self.t)
  before=AP.available(self.a);self.use('마하펀치')
  self.assertEqual(MA.bonus(self.a,self.t),1);self.assertEqual(MA.bonus(self.a,self.u),0)
  self.assertEqual(AP.available(self.a),before-1)
  baseline=self.a.evasion('물리',attacker=self.u,engine=self.e)
  self.assertEqual(self.a.evasion('물리',attacker=self.t,engine=self.e),min(9,baseline+1))
  self.restore();self.valid()
  for expected in (2,3,4,5,6,6):
   self.next();self.use('마하펀치');self.assertEqual(MA.bonus(self.a,self.t),expected)
  self.next();self.use('두번차기');self.e.end_of_turn(self.a)
  self.assertEqual(MA.bonus(self.a,self.t),6)  # any successful hit retains; only punching hits increase
  self.e.end_round();self.start();self.e.end_of_turn(self.a);self.assertNotIn(MA.TAG,self.a.spec)

 def test_pummeling_nonpunch_or_miss_does_not_pay_or_tag(self):
  self.acquire(training=1);self.start();MA.arm(self.e,self.a,'pummeling_momentum',target=self.t)
  before=AP.available(self.a);self.use('두번차기');self.assertNotIn(MA.TAG,self.a.spec);self.assertEqual(AP.available(self.a),before)
  self.next();self.use('마하펀치',face=1);self.assertNotIn(MA.TAG,self.a.spec);self.assertEqual(AP.available(self.a),before)

 def test_willow_answers_actual_against_holder_miss_and_failed_opposed_with_same_maneuver(self):
  for face in (1,20):
   self.setup('유연');self.acquire();self.start(self.t)
   MA.arm(self.e,self.a,'bend_like_the_willow',options={'maneuver/걸기':self.options(win=True)})
   before=AP.available(self.a)
   options=dict(self.options(),fixed_accuracy=face)
   self.e.trip(self.t,self.a,**options)
   self.assertIn('넘어짐',self.t.conditions);self.assertNotIn('넘어짐',self.a.conditions);self.assertEqual(AP.available(self.a),before-2)
   self.assertNotIn('bend_like_the_willow',self.a.spec[MA.ARMED]);self.restore();self.valid()

 def test_willow_does_not_answer_an_attack_against_another_actor(self):
  self.setup('유연');self.acquire();self.start(self.t)
  MA.arm(self.e,self.a,'bend_like_the_willow',options={'maneuver/걸기':self.options(win=True)})
  self.e.gm.set_position(self.u,(5,3),reason='actual target adjacent to foe')
  before=AP.available(self.a);self.e.trip(self.t,self.u,**dict(self.options(),fixed_accuracy=1))
  self.assertEqual(AP.available(self.a),before);self.assertNotIn('넘어짐',self.t.conditions)

 def test_wrestlemania_two_distinct_native_effects_one_full_action_after_starting_dominant(self):
  self.setup('근성');self.acquire();self.start();self.e.grapple(self.a,self.t,**self.options(win=True));self.next()
  before=AP.available(self.a);MA.wrestlemania(self.e,self.a)
  result=MA.grapple_pair(self.e,self.a,[{'kind':'secure'},{'kind':'attack'}])
  self.assertEqual([x['action'] for x in result],['secure','attack']);self.assertEqual(AP.available(self.a),before-1)
  self.assertEqual(self.a.budget,{'standard':0,'shift':0,'swift':0});self.restore();self.valid()

 def test_wrestlemania_rejects_new_grapple_this_turn_and_duplicate_effects(self):
  self.setup('근성');self.acquire();self.start();self.e.grapple(self.a,self.t,**self.options(win=True))
  self.rejected(lambda:MA.wrestlemania(self.e,self.a),'turn start|actual own turn')
  self.next();MA.wrestlemania(self.e,self.a)
  self.rejected(lambda:MA.grapple_pair(self.e,self.a,[{'kind':'attack'},{'kind':'attack'}]),'different')

 def test_soft_landing_native_jump_kick_miss_suppresses_hp_loss_once_and_ordinary_miss_still_loses(self):
  self.setup('이판사판');self.acquire(training=3);self.start();MA.arm(self.e,self.a,'soft_landing')
  before=self.a.hp;ap=AP.available(self.a);self.use('점프킥',face=1)
  self.assertEqual(self.a.hp,before);self.assertEqual(AP.available(self.a),ap-1)
  self.next();self.use('무릎차기',face=1);self.assertLess(self.a.hp,before,'\n'.join(self.e.log_lines[-20:]))
  self.restore();self.valid()

 def test_soft_landing_actual_fall_reduces_all_distance_results_by_half_combat_rank(self):
  self.setup('이판사판');self.acquire();self.start();ap=AP.available(self.a)
  result=MA.soft_landing_fall(self.e,self.a,action_id='fall/actual',meters=7,intentional=False,reason='actual fall',natural_sky=False,natural_sky_reason='Trainer has no natural flight')
  self.assertEqual(result['meters'],7);self.assertEqual(result['damage_distance'],4);self.assertEqual(AP.available(self.a),ap-1)
  self.assertEqual(result['height_injuries'],2);self.restore();self.valid()

 def test_whirlwind_one_ap_full_action_many_adjacent_foes_and_one_full_round_unflanked(self):
  self.setup('테크니션');self.acquire();self.e.gm.set_position(self.u,(2,3),reason='actual flanking foe');self.start()
  self.assertTrue(BODY.flanking(self.e,self.a)['flanked']);before=(self.t.hp,self.u.hp,AP.available(self.a))
  with patch.object(Engine,'d20',return_value=20):MA.whirlwind_strikes(self.e,self.a,[self.t,self.u])
  self.assertLess(self.t.hp,before[0]);self.assertLess(self.u.hp,before[1]);self.assertEqual(AP.available(self.a),before[2]-1)
  self.assertEqual(self.a.budget,{'standard':0,'shift':0,'swift':1});self.assertFalse(BODY.flanking(self.e,self.a)['flanked'])
  self.restore();self.valid();self.next();self.assertTrue(BODY.flanking(self.e,self.a)['flanked'])

 def test_wrong_style_or_nonadjacent_whirlwind_and_forged_move_token_reject_without_state_change(self):
  self.acquire();self.start()
  self.rejected(lambda:MA.whirlwind_strikes(self.e,self.a,[self.t]),'does not grant')
  import action_lifecycle as A
  def forged():
   with A.move_grant(self.e,self.a,self.t,MA.ROCK,source=MA.KUNG,kind='free'):pass
  self.rejected(forged,'unreviewed')

 def test_tag_tampering_and_acquired_move_choice_tampering_are_detected(self):
  self.acquire(training=1);self.start();MA.arm(self.e,self.a,'pummeling_momentum',target=self.t);self.use('마하펀치')
  saved=self.e.export_state();self.a.spec[MA.TAG]['bonus']=2;self.assertFalse(self.e.validate_state()['valid'])
  self.e=CODEC.load_engine(self.rules,saved)
  import world_entities as W
  self.a=W.actor_index(self.e)['trainer/martial'];self.a.spec['feature_choices'][MA.TRAINING][0][0]='move/경혈찌르기'
  self.assertFalse(self.e.validate_state()['valid'])

 def test_pummeling_intercept_tags_only_actual_recipient_and_restores_the_same_hit(self):
  self.acquire(training=1);self.e.gm.set_position(self.u,(4,5),reason='actual interceptor');self.e.gm.set_stat(self.u,'spe',40,reason='observed interceptor Speed above Priority attacker');self.start()
  MA.arm(self.e,self.a,'pummeling_momentum',target=self.u)
  self.e.watch_move_defense(self.t,[{'actor_id':self.u.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual native Intercept')
  import passive_events as P
  with patch.object(Engine,'d20',return_value=20),self.assertRaises(P.PassiveEventPending):self.use('마하펀치')
  event=self.e._passive_pending;self.restore()
  self.e.choose_move_defense(event,self.u,use=True,options={'path':[(4,5),(4,4),(4,3)],'skill':'육상','mode':'land','shove_destination':[5,3],'roll_options':{'fixed':[6]*6}},reason='actual successful Intercept')
  self.assertEqual(MA.bonus(self.a,self.u),1);self.assertEqual(MA.bonus(self.a,self.t),0)
  self.restore();self.valid()

 def test_reference_vital_throw_answers_finished_melee_attack_only_before_owner_turn(self):
  import combat_move_reactions as REACT,action_resources as RES
  self.setup('근성');self.acquire(training=1);self.start(self.t)
  REACT.arm(self.e,self.a,REACT.VITAL)
  before=self.t.hp
  with patch.object(Engine,'d20',return_value=20):self.e.use_move(self.t,self.a,'move/몸통박치기',set_damage=True)
  self.assertLess(self.t.hp,before);self.assertEqual(self.a.move_uses[REACT.VITAL],1)
  self.assertEqual(RES.pending(self.a),{'standard':1});self.assertIs(self.e._active_turn_actor,self.t)
  self.restore();self.valid()

 def test_reference_vital_throw_pending_child_resumes_original_completion_and_finishes_once(self):
  import combat_move_reactions as REACT,passive_events as P,initiative_interrupts as I,action_resources as RES
  self.setup('근성');self.acquire(training=1)
  self.e.gm.set_position(self.u,(4,5),reason='actual reactive Move interceptor')
  self.e.gm.set_stat(self.u,'spe',40,reason='actual interceptor Speed');self.start(self.t)
  self.e.watch_move_defense(self.t,[{'actor_id':self.u.entity_id,'source':'maneuver/근접-가로채기'}],reason='intercept only the actual return attack')
  REACT.arm(self.e,self.a,REACT.VITAL)
  with patch.object(Engine,'d20',return_value=20),self.assertRaises(P.PassiveEventPending):
   self.e.use_move(self.t,self.a,'move/몸통박치기',set_damage=True)
  event=self.e._passive_pending;hp=(self.a.hp,self.t.hp,self.u.hp);self.restore()
  self.e.choose_move_defense(event,self.u,use=False,reason='explicitly decline Intercept; Vital Throw cannot be Intercepted')
  self.assertEqual(self.a.hp,hp[0]);self.assertLess(self.t.hp,hp[1]);self.assertEqual(self.u.hp,hp[2])
  self.assertEqual(self.a.move_uses[REACT.VITAL],1);self.assertEqual(self.t.move_uses['move/몸통박치기'],1)
  self.assertIsNone(I.frame(self.e));self.assertIs(self.e._active_turn_actor,self.t)
  self.assertEqual(RES.pending(self.a),{'standard':1});self.assertEqual(self.t.budget['standard'],0)
  self.assertTrue(all(r['status']=='complete' for r in self.a.spec[REACT.EVENTS].values()))
  self.assertTrue(all(r['phase']=='complete' for r in self.e._move_completions.values()))
  self.restore();self.valid()

 def test_reference_sky_uppercut_pending_child_resumes_paid_setup_and_uses_actual_recipient(self):
  import combat_move_reactions as REACT,passive_events as P,initiative_interrupts as I,setup_move_state as SETUP,action_resources as RES
  for intercept in (False,True):
   with self.subTest(intercept=intercept):
    self.setup();self.acquire(training=3)
    self.e.gm.choose_learned_capability_policy(self.t,'move/공중날기','move_entry',reason='actual selected Fly source')
    self.e.gm.set_move(self.t,'move/공중날기',reason='actual learned Fly')
    self.e.gm.set_position(self.u,(4,5),reason='actual reactive Move interceptor')
    self.e.gm.set_stat(self.u,'spe',40,reason='actual interceptor Speed');self.start(self.t)
    self.e.watch_move_defense(self.t,[{'actor_id':self.u.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual response to Sky Uppercut')
    REACT.arm(self.e,self.a,REACT.UPPER);hp=self.t.hp
    with patch.object(Engine,'d20',return_value=20),self.assertRaises(P.PassiveEventPending):
     self.e.use_setup_move_on(self.t,self.a,'move/공중날기',self.e.everyone)
    event=self.e._passive_pending;self.restore()
    options={'path':[(4,5),(4,4),(4,3)],'skill':'육상','mode':'land','shove_destination':[5,3],'roll_options':{'fixed':[6]*6}} if intercept else None
    self.e.choose_move_defense(event,self.u,use=intercept,options=options,reason='explicit Intercept choice')
    if intercept:
     self.assertEqual(self.t.hp,hp);self.assertIsNotNone(SETUP.pending(self.t));self.assertEqual(self.t.setup_move,'move/공중날기')
    else:
     self.assertLess(self.t.hp,hp);self.assertIsNone(SETUP.pending(self.t));self.assertIsNone(self.t.setup_move)
     self.assertEqual(self.t.move_uses['move/공중날기'],1)
    self.assertEqual(self.a.move_uses[REACT.UPPER],1);self.assertEqual(self.t.budget['standard'],0)
    self.assertIsNone(I.frame(self.e));self.assertIs(self.e._active_turn_actor,self.t)
    self.assertEqual(RES.pending(self.a),{'standard':1})
    self.assertTrue(all(r['status']=='complete' for r in self.a.spec[REACT.EVENTS].values()))
    self.restore();self.valid()

 def test_reference_counter_actual_hp_loss_resistance_and_fighting_immunity(self):
  import combat_move_reactions as REACT,attack_damage_history as H
  self.setup('유연');self.acquire(training=2);self.start(self.t)
  REACT.arm(self.e,self.a,REACT.COUNTER);before=(self.a.hp,self.t.hp)
  with patch.object(Engine,'d20',return_value=20):self.e.use_move(self.t,self.a,'move/몸통박치기',set_damage=True)
  loss=before[0]-self.a.hp
  self.assertGreater(loss,0);self.assertEqual(before[1]-self.t.hp,2*loss)
  self.assertEqual(self.a.move_uses[REACT.COUNTER],1)
  self.assertTrue(any('저항 1단계' in line for line in self.e.log_lines))
  self.restore();self.valid()
  self.setup('유연');self.acquire(training=2);self.e.gm.set_types(self.t,['고스트'],reason='actual Fighting-immune attacker');self.start(self.t)
  REACT.arm(self.e,self.a,REACT.COUNTER);before=self.t.hp
  with patch.object(Engine,'d20',return_value=20):self.e.use_move(self.t,self.a,'move/몸통박치기',set_damage=True)
  self.assertEqual(self.t.hp,before);self.assertEqual(self.a.move_uses[REACT.COUNTER],1)
  self.restore();self.valid()

 def test_reference_counter_answers_actual_aoo_with_a_distinct_suspended_turn_owner(self):
  import combat_move_reactions as REACT,initiative_interrupts as I,action_resources as RES
  self.setup('유연');self.acquire(training=2);self.start();REACT.arm(self.e,self.a,REACT.COUNTER)
  hp=(self.a.hp,self.t.hp);budget=deepcopy(self.a.budget)
  with patch.object(Engine,'d20',return_value=20):TURN.trigger_aoo(self.e,self.a,'actual adjacent departure',[self.t])
  loss=hp[0]-self.a.hp;self.assertGreater(loss,0);self.assertEqual(hp[1]-self.t.hp,2*loss)
  self.assertTrue(self.t.aoo_used);self.assertEqual(self.a.move_uses[REACT.COUNTER],1)
  self.assertIsNone(I.frame(self.e));self.assertIs(self.e._active_turn_actor,self.a);self.assertEqual(self.a.budget,budget)
  self.assertEqual(RES.pending(self.a),{'standard':1})
  event=list(self.a.spec[REACT.EVENTS].values())[-1]
  self.assertEqual(event['attacker_id'],self.t.entity_id);self.assertEqual(event['turn_owner_id'],self.a.entity_id);self.assertEqual(event['status'],'complete')
  self.restore();self.valid()

 def test_reference_counter_area_parent_pending_child_finishes_activation_and_debt_once(self):
  import combat_move_reactions as REACT,passive_events as P,initiative_interrupts as I,action_resources as RES
  self.setup('유연');self.acquire(training=2);self.e.gm.set_move(self.t,'move/지진',reason='actual learned area Move')
  self.e.gm.set_position(self.u,(4,5),reason='second actual recipient in the Burst and nearby defense observer')
  self.e.gm.set_stat(self.u,'spe',40,reason='actual defense observer Speed');self.start(self.t)
  self.e.watch_move_defense(self.t,[{'actor_id':self.u.entity_id,'source':'maneuver/근접-가로채기'}],reason='explicit optional defense watch for the return attack')
  REACT.arm(self.e,self.a,REACT.COUNTER);hp=(self.a.hp,self.t.hp)
  with patch.object(Engine,'d20',return_value=20),self.assertRaises(P.PassiveEventPending):
   self.e.use_move_on(self.t,self.a,'move/지진',self.e.everyone,set_damage=True)
  event=self.e._passive_pending;loss=hp[0]-self.a.hp;self.assertGreater(loss,0);self.restore()
  self.e.choose_move_defense(event,self.u,use=False,reason='explicit legal decline for a never-miss response')
  self.assertEqual(self.a.hp,hp[0]-loss);self.assertEqual(self.t.hp,hp[1]-2*loss)
  self.assertEqual(self.a.move_uses[REACT.COUNTER],1);self.assertEqual(self.t.move_uses['move/지진'],1)
  self.assertIsNone(I.frame(self.e));self.assertIs(self.e._active_turn_actor,self.t)
  self.assertEqual(RES.pending(self.a),{'standard':1});self.assertTrue(all(r['phase']=='complete' for r in self.e._move_completions.values()))
  self.e.end_of_turn(self.t);self.e.start_of_turn(self.a,initiative_count=20);self.assertEqual(self.a.budget['standard'],0)
  self.e.end_of_turn(self.a);self.e.end_round();self.start();self.assertEqual(self.a.budget['standard'],1)
  self.restore();self.valid()

 def test_reference_quick_guard_protects_adjacent_ally_only_from_actual_priority_hit(self):
  import combat_move_reactions as REACT
  self.setup('테크니션');self.acquire(training=2);self.e.gm.set_move(self.t,'move/전광석화',reason='actual learned Priority Move')
  self.start(self.t);REACT.arm(self.e,self.a,REACT.GUARD)
  before=self.a.hp
  with patch.object(Engine,'d20',return_value=20):self.e.use_move(self.t,self.a,'move/전광석화',set_damage=True)
  self.assertEqual(self.a.hp,before);self.assertEqual(self.a.move_uses[REACT.GUARD],1)
  self.restore();self.valid()

 def test_reference_sky_uppercut_interrupts_actual_fly_initiation_and_leaves_next_turn(self):
  import combat_move_reactions as REACT,setup_move_state as SETUP
  self.acquire(training=3);self.e.gm.choose_learned_capability_policy(self.t,'move/공중날기','move_entry',reason='actual selected learned Fly source')
  self.e.gm.set_move(self.t,'move/공중날기',reason='actual learned Fly');self.start(self.t)
  REACT.arm(self.e,self.a,REACT.UPPER);before=self.t.hp
  with patch.object(Engine,'d20',return_value=20):self.e.use_setup_move_on(self.t,self.a,'move/공중날기',self.e.everyone)
  self.assertLess(self.t.hp,before);self.assertIsNone(SETUP.pending(self.t));self.assertIsNone(self.t.setup_move)
  self.assertEqual(self.t.budget['standard'],0);self.assertEqual(self.a.move_uses[REACT.UPPER],1)
  self.restore();self.valid()

 def test_reference_reaction_cannot_be_used_as_an_untriggered_ordinary_move(self):
  self.setup('유연');self.acquire(training=2);self.start()
  self.rejected(lambda:self.use('카운터'),'actual armed native reaction')

 def test_double_strike_rolls_twice_combines_base_once_and_keeps_each_critical(self):
  import multi_strike as M
  self.acquire(training=1);self.start()
  with patch.object(Engine,'d20',side_effect=[20,1]):self.e.use_move(self.a,self.t,'move/두번차기',set_damage=True)
  row=self.a.spec[M.KEY][-1];self.assertEqual(row['rolls'],[[True,20,True],[False,1,False]])
  complete=list(self.e._move_completions.values())[-1];move=complete['target_moves'][self.t.entity_id]
  self.assertEqual(M.base(self.a,move,3),3);self.assertEqual(M.critical_dice(self.e,self.a,move,True),9)
  self.next()
  with patch.object(Engine,'d20',side_effect=[12,12]):self.e.use_move(self.a,self.t,'move/두번차기',set_damage=True)
  move=list(self.e._move_completions.values())[-1]['target_moves'][self.t.entity_id]
  self.assertEqual(M.base(self.a,move,3),6);self.assertEqual(self.a.move_uses['move/두번차기'],2)
  self.restore();self.valid()

 def test_triple_kick_uses_one_activation_and_printed_one_three_six_damage_bases(self):
  import multi_strike as M
  self.setup('테크니션');self.acquire(training=3);self.start()
  for faces,expected in [([12,1,1],1),([12,12,1],3),([12,12,12],6)]:
   with patch.object(Engine,'d20',side_effect=faces):self.e.use_move(self.a,self.t,'move/트리플킥',set_damage=True)
   row=list(self.e._move_completions.values())[-1];self.assertEqual(M.base(self.a,row['target_moves'][self.t.entity_id],'variable'),expected)
   self.next()
  self.assertEqual(self.a.move_uses['move/트리플킥'],3);self.restore();self.valid()

 def test_core_inner_focus_blocks_flinch_and_zero_initiative_but_not_other_reductions(self):
  import combat_timing as CT,initiative_derivation as I
  self.setup('정신력');self.acquire();self.start()
  self.assertFalse(self.e.apply_status(self.a,'풀죽음'));self.assertNotIn('풀죽음',self.a.conditions)
  CT.install(self.e,self.a,{'source':'maneuver/치사한-짓','initiative_zero':True,'turn_owner':self.a,'turn_deadline':2})
  self.assertIsNone(self.a.initiative_override)
  import effects as FX
  FX.run_effects(self.e,self.t,self.a,[{'type':'initiative','delta':-5}],{'hit':True,'attacker':self.t,'target':self.a,'engine':self.e},'extension/observed-initiative-reduction')
  self.assertEqual(self.a.initiative_bonus,-5)
  self.restore();self.valid()

 def test_core_reckless_adds_two_only_to_jump_kicks_and_recoil_without_playtest_exhaust_bonus(self):
  self.setup('이판사판');self.acquire(training=3);self.start()
  import martial_artist_ability_identities as A
  for mid,expected in [('move/점프킥',2),('move/무릎차기',2),('move/이판사판태클',2),('move/인파이트',0),('move/기가임팩트',0)]:
   self.assertEqual(A.damage_base_bonus(self.e,self.a,self.rules.move(mid)),expected,mid)
  self.assertEqual(self.e.damage_base(self.a,self.rules.move('move/점프킥'),target=self.t),12)
  self.e.gm.set_move(self.t,'move/위액',reason='actual learned suppression Move')
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=20)
  with patch.object(Engine,'d20',return_value=20):self.e.use_move(self.t,self.a,'move/위액')
  self.assertEqual(A.damage_base_bonus(self.e,self.a,self.rules.move('move/점프킥')),0)

 def test_reference_acupressure_and_power_trick_apply_real_state_and_restore(self):
  self.setup('유연');self.acquire(training=2);self.start()
  self.use('경혈찌르기',target=self.a)
  self.assertEqual(sum(self.a.stages.values()),2)
  self.next();self.e.gm.set_stat(self.a,'def',20,reason='observed asymmetric base stats for Power Trick')
  before=(self.a.stats['atk'],self.a.stats['def']);self.use('파워트릭',target=self.a)
  self.assertEqual((self.a.stats['atk'],self.a.stats['def']),tuple(reversed(before)))
  self.restore();self.valid()

 def test_reference_five_strike_moves_use_the_existing_one_roll_combined_damage_owner(self):
  import five_strike as FIVE
  for style,mid in [('철주먹','연속펀치'),('테크니션','손바닥치기')]:
   self.setup(style);self.acquire(training=2);self.start();before=self.t.hp
   self.use(mid)
   self.assertLess(self.t.hp,before);self.assertEqual(len(self.a.spec[FIVE.KEY]),1)
   self.assertEqual(self.a.spec[FIVE.KEY][0]['move_id'],self.rules.move_id(mid))
   self.restore();self.valid()

 def test_reference_ordinary_attack_effects_run_through_their_native_consumers(self):
  groups={'근성':['배대뒤치기','업어후리기'],'정신력':['태권당수','로킥','안다리걸기','크로스촙'],'이판사판':['돌려차기','깨트리기','인파이트']}
  for style,names in groups.items():
   self.setup(style);self.acquire(training=3);self.start()
   for number,mid in enumerate(names):
    with self.subTest(move=mid):
     if number:self.next();self.e.gm.set_position(self.t,(4,3),reason='actual fresh adjacent attack geometry')
     hp=self.t.hp;self.use(mid);self.assertLess(self.t.hp,hp)
     if mid=='배대뒤치기':self.assertNotEqual(tuple(self.t.pos),(4,3));self.assertIn('넘어짐',self.t.conditions)
     if mid=='로킥':self.assertLess(self.t.stages['spe'],0)
     if mid=='돌려차기':self.assertIn('풀죽음',self.t.conditions)
     if mid=='인파이트':self.assertLess(self.a.stages['def'],0);self.assertLess(self.a.stages['spd'],0)
   self.restore();self.valid()

 def test_reference_brick_break_bypasses_reflect_without_spending_or_removing_the_team_pool(self):
  import blessing_effects as B
  self.setup('철주먹');self.acquire(training=2);self.e.gm.set_move(self.t,'move/리플렉터',reason='actual learned Reflect')
  self.start(self.t);self.e.use_move(self.t,self.t,'move/리플렉터')
  row=next(r for r in B.live(self.t) if r['source']=='move/리플렉터');left=B.remaining(row)
  self.e.end_of_turn(self.t);self.e.start_of_turn(self.a,initiative_count=20)
  with patch.object(self.e.rulings,'decide',return_value=True) as choose:self.use('깨트리기')
  self.assertEqual(B.remaining(row),left)
  self.assertFalse(any(call.args[0].get('type')=='team_blessing' for call in choose.call_args_list))
  self.assertFalse(any(r.get('type')=='ignore_effects' for r in self.a.registry))
  self.next()
  with patch.object(self.e.rulings,'decide',return_value=True):self.use('몸통박치기')
  self.assertEqual(B.remaining(next(r for r in B.live(self.t) if r['source']=='move/리플렉터')),left-1)
  self.restore();self.valid()


 def test_wrestlemania_first_attack_faint_keeps_actual_damage_and_full_cost_when_grapple_ends(self):
  import grapple_state as GS
  self.setup('근성');self.acquire();self.start();self.e.grapple(self.a,self.t,**self.options(win=True));self.next()
  self.e.lose_hp(self.t,self.t.hp-1,source='actual prior HP loss')
  MA.wrestlemania(self.e,self.a)
  results=MA.grapple_pair(self.e,self.a,[{'kind':'attack'},{'kind':'secure'}])
  self.assertEqual(len(results),1);self.assertTrue(self.t.fainted);self.assertIsNone(GS.relation(self.e,self.a))
  self.assertEqual(self.a.budget,{'standard':0,'shift':0,'swift':0});self.restore();self.valid()

 def test_retraining_achievement_withdraws_its_tag_and_one_stat_tag_but_keeps_class_moves(self):
  from test_book_hunter_acquisition import HunterScene
  self.acquire(training=1);self.start();MA.arm(self.e,self.a,'pummeling_momentum',target=self.t);self.use('마하펀치')
  self.assertIn(MA.TAG,self.a.spec);before=self.a.stats['def']
  options=HunterScene.decisions(self,self.a,MA.ACHIEVEMENT)
  self.e.retrain_trainer_source(self.a,MA.ACHIEVEMENT,**options)
  self.assertNotIn(MA.TAG,self.a.spec);self.assertIsNone(MA.style(self.a));self.assertEqual(self.a.stats['def'],before-1)
  self.assertIn('철주먹',self.a.abilities);self.assertIn('move/마하펀치',self.a.moves)
  self.restore();self.valid()
