"""Tumbler reactions use actual non-Move Attack producers and the shared signed hit history."""
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from tumbler_fixture import TumblerScene
from engine import Rules,Engine
import tumbler as T,action_points as AP,combat_timing as TIME,action_resources as RESOURCES
import grapple_state as G,frequency as F

class NativeAttackTests(TumblerScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def test_quick_manipulate_accuracy_hit_is_independent_of_opposed_success(self):
  self.setup(extra_skills={'협박':6});self.family(T.QUICK);self.begin();self.decision('quick_gymnastics',True);before=AP.available(self.a)
  result=self.e.manipulate(self.a,self.t,'terrorize',defender_skill='집중',fixed_accuracy=20,challenger_options={'fixed':[1]*6},defender_options={'fixed':[6]*3})
  self.assertFalse(result);self.assertEqual(AP.available(self.a),before-1);self.assertTrue(T.immune(self.a));self.assertEqual(self.a._action_history,['standard','free']);self.valid()
 def test_quick_actual_push_trip_and_dirty_trick_share_accuracy_producer(self):
  for source in ('push','trip','dirty'):
   with self.subTest(source=source):
    self.setup();self.family(T.QUICK);self.begin();self.decision('quick_gymnastics',True);before=AP.available(self.a)
    if source=='dirty':self.e.dirty_trick(self.a,self.t,'low_blow',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*6})
    else:getattr(self.e,source)(self.a,self.t,challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,challenger_options={'fixed':[6]*4},defender_options={'fixed':[1]*4})
    self.assertEqual(AP.available(self.a),before-1);self.assertFalse(self.u.aoo_used);self.assertTrue(T.immune(self.a));self.valid()
 def test_quick_disarm_hit_uses_actual_held_equipment(self):
  self.family(T.QUICK);self.hold_item(self.t);self.begin();self.decision('quick_gymnastics',True);before=AP.available(self.a)
  self.e.disarm(self.a,self.t,attacker_skill='전투',defender_skill='전투',fixed_accuracy=20,challenger_options={'fixed':[6]*4},defender_options={'fixed':[1]*4})
  self.assertEqual(AP.available(self.a),before-1);self.assertTrue(T.immune(self.a));self.assertFalse(self.u.aoo_used);self.valid()
 def test_nonmove_miss_and_effect_only_helpers_are_not_hits(self):
  self.setup(extra_skills={'협박':6});self.family(T.QUICK);self.begin();self.decision('quick_gymnastics',True);before=AP.available(self.a)
  self.e.manipulate(self.a,self.t,'terrorize',defender_skill='집중',fixed_accuracy=1,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*3})
  self.assertEqual(AP.available(self.a),before)
  __import__('combat_maneuvers')._manipulate_outcome(self.e,self.a,self.t,'terrorize',None,40)
  self.assertEqual(AP.available(self.a),before);self.assertFalse(T.immune(self.a))
 def test_declined_nonmove_quick_opportunity_ko_prevents_effect(self):
  self.setup(extra_skills={'협박':6});self.family(T.QUICK);self.begin();self.e.gm.set_position(self.t,(5,2),reason='actual ranged maneuver target');self.e.gm.set_hp(self.a,1,reason='actual wounded attacker');self.decision('quick_gymnastics',False)
  with patch.object(Engine,'d20',return_value=15):result=self.e.manipulate(self.a,self.t,'terrorize',defender_skill='집중',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*3})
  self.assertFalse(result);self.assertTrue(self.a.fainted);self.assertFalse(any(r.get('manipulation')=='terrorize' for r in TIME.records(self.t)));self.valid()
 def test_splash_reacts_to_actual_status_maneuver_then_resumes_opposed_effect(self):
  self.family(T.FLIP);foe=self.add('social attacker','trainer',(3,3),side='foes',speed=35,extra_skills={'협박':6});self.begin(foe,40)
  self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='actual incoming Attack watch');self.decision('native_attack_splash',{'jump':{'destination':(2,3),'difficult':False,'clear_path':True}})
  result=self.e.manipulate(foe,self.a,'terrorize',defender_skill='집중',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*3})
  self.assertTrue(result);self.assertEqual(self.a.pos,(2,3));self.assertEqual(RESOURCES.pending(self.a).get('shift'),1);self.assertIs(self.e._active_turn_actor,foe);self.assertEqual(foe.budget['standard'],0)
  self.assertTrue(any(r.get('manipulation')=='terrorize' for r in TIME.records(self.a)));self.valid();self.restore();self.valid()
 def test_splash_nonmove_miss_and_effect_helper_leave_scene_frequency(self):
  self.family(T.FLIP);foe=self.add('social attacker','trainer',(3,3),side='foes',extra_skills={'협박':6});self.begin(foe,40)
  self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='actual watch');self.decision('native_attack_splash',{'jump':None})
  self.e.manipulate(foe,self.a,'terrorize',defender_skill='집중',fixed_accuracy=1,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*3})
  __import__('combat_maneuvers')._manipulate_outcome(self.e,foe,self.a,'terrorize',None,40)
  self.assertTrue(F.activation_allowed(self.a,T.FLIP+':Splash',{'kind':'scene','uses':1},engine=self.e));self.assertNotIn(T.SPLASH,self.a.move_uses)
 def test_quick_native_grapple_struggle_has_one_signed_completed_hit(self):
  self.family(T.QUICK);self.begin();self.e.grapple(self.a,self.t,challenger_skill='육상',defender_skill='육상',fixed_accuracy=20,challenger_options={'fixed':[6]*4},defender_options={'fixed':[1]*4});self.next_round();self.decision('quick_gymnastics',True)
  before=AP.available(self.a);result=self.e.grapple_action(self.a,'attack',request_id='actual-grapple-hit');relation=G.relation(self.e,self.a);index=len(relation['history'])-1
  event=G.completed_attack_event(self.e,relation['id'],index);self.assertEqual(event['result'],'damaging_hit');self.assertEqual(AP.available(self.a),before-1);self.assertTrue(T.immune(self.a));self.valid();self.restore()
  self.e.grapple_action(self.a,'attack',request_id='actual-grapple-hit');self.assertEqual(AP.available(self.a),before-1);self.valid()
 def test_grapple_forbids_splash_without_cost_and_actual_attack_continues(self):
  self.family(T.FLIP);foe=self.add('grappler','trainer',(2,3),side='foes',speed=35);self.begin(foe,40)
  self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='watch before actual Grappled restriction');self.decision('native_attack_splash',False)
  self.e.grapple(foe,self.a,challenger_skill='육상',defender_skill='육상',fixed_accuracy=20,challenger_options={'fixed':[6]*4},defender_options={'fixed':[1]*4})
  self.reject(lambda:self.e.declare_jump_move(self.a,self.a,T.SPLASH,event_id='illegal-grapple-splash',jump=None,reason='attempt ordinary Splash'),'Grappled')
  self.reject(lambda:self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='attempt reaction Splash'),'Grappled')
  self.e.end_of_turn(foe);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(foe,initiative_count=40)
  self.decision('native_attack_splash',{'jump':None});hp=self.a.hp
  result=self.e.grapple_action(foe,'attack',request_id='grapple-no-illegal-splash');row=G.relation(self.e,foe);event=G.completed_attack_event(self.e,row['id'],len(row['history'])-1)
  self.assertEqual(hp-self.a.hp,result['damage']);self.assertGreater(result['damage'],0);self.assertNotIn('native_attack_defense',event);self.assertNotIn(T.SPLASH,self.a.move_uses);self.assertFalse(RESOURCES.pending(self.a).get('shift',0));self.assertTrue(F.activation_allowed(self.a,T.FLIP+':Splash',{'kind':'scene','uses':1},engine=self.e));self.valid()
  self.turn(self.u,10);hp=self.a.hp;self.use(self.u,self.a,'move/몸통박치기');self.assertLess(self.a.hp,hp);self.assertIsNone(self.e._passive_pending);self.assertNotIn(T.SPLASH,self.a.move_uses);self.valid()

 def test_normal_struggle_attack_splash_reduces_only_that_actual_hit(self):
  import passive_events as P
  self.family(T.FLIP);self.begin(self.t,40);hp=self.a.hp
  baseline=self.e.roll_damage(self.t,self.a,self.rules.move('struggle'),set_damage=True)
  self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='actual generic Struggle Attack response')
  with self.assertRaises(P.PassiveEventPending):self.use(self.t,self.a,'struggle')
  event_id=self.e._passive_pending
  self.e.choose_move_defense(event_id,self.a,use=True,options={'jump':None},reason='actual Splash against generic Struggle')
  event=self.e._passive_events[event_id];self.assertEqual(event['move_id'],'struggle');self.assertEqual(hp-self.a.hp,max(1,baseline-12));self.assertEqual(self.a.move_uses[T.SPLASH],1)
  self.assertEqual(RESOURCES.pending(self.a).get('shift'),1);self.assertNotIn('struggle',self.t.moves);self.valid()
  self.e.end_of_turn(self.t);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t,initiative_count=40)
  hp=self.a.hp;self.use(self.t,self.a,'struggle');self.assertEqual(hp-self.a.hp,baseline);self.assertEqual(self.a.move_uses[T.SPLASH],1);self.valid()

 def test_native_splash_failed_jump_restore_resumes_paid_maneuvers_without_repeating_hit(self):
  import jump_actions as J,common_checks as C,world_entities as W
  for kind in ('manipulate','dirty','trip','disarm'):
   with self.subTest(kind=kind):
    self.setup();self.family(T.FLIP);foe=self.add('reaction attacker','trainer',(3,3),side='foes',speed=35,extra_skills={'협박':6})
    if kind=='disarm':self.hold_item(name='소형 방패',as_held=False)
    self.begin(foe,40);self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='actual native hit wait')
    self.decision('native_attack_splash',{'jump':{'destination':(1,3),'difficult':True,'difficulty_skill':'곡예','difficulty_dc':100,'difficulty_options':{'fixed':[1]*6},'clear_path':True}})
    def invoke(actor):
     if kind=='manipulate':return self.e.manipulate(actor,self.a,'terrorize',defender_skill='집중',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*3})
     if kind=='dirty':return self.e.dirty_trick(actor,self.a,'low_blow',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*6})
     if kind=='trip':return self.e.trip(actor,self.a,challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,challenger_options={'fixed':[6]*4},defender_options={'fixed':[1]*4})
     return self.e.disarm(actor,self.a,attacker_skill='전투',defender_skill='전투',fixed_accuracy=20,challenger_options={'fixed':[6]*4},defender_options={'fixed':[1]*4})
    result=invoke(foe);self.assertIsInstance(result,C.PendingDecision);jump_id=self.a.spec['_jump_pending'];foe_id=foe.entity_id;self.valid();self.restore();foe=W.actor_index(self.e)[foe_id]
    J.resolve_failure(self.e,self.a,decision='land',reason_text='resolve actual failed reaction Jump')
    self.e.resume_jump_move(self.a,event_id=jump_id);self.assertEqual(self.a.pos,(1,3));self.assertIs(self.e._active_turn_actor,foe)
    with patch.object(Engine,'accuracy_check',side_effect=AssertionError('already hit; never repeat accuracy')):result=invoke(foe)
    self.assertTrue(result);self.assertEqual(foe._action_history,['standard']);self.assertEqual(self.a.move_uses[T.SPLASH],1);self.assertEqual(RESOURCES.pending(self.a).get('shift'),1);self.valid();self.restore();self.valid()

 def test_acquired_dodge_avoids_actual_grapple_attack_without_fake_move(self):
  self.family(T.REFLEX);foe=self.add('grappler','trainer',(2,3),side='foes',speed=35);self.begin(foe,40)
  self.e.grapple(foe,self.a,challenger_skill='육상',defender_skill='육상',fixed_accuracy=20,challenger_options={'fixed':[6]*4},defender_options={'fixed':[1]*4})
  self.e.end_of_turn(foe);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(foe,initiative_count=40)
  self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':'ability/회피'}],reason='actual damaging grapple response');self.decision('native_attack_dodge',True);hp=self.a.hp
  result=self.e.grapple_action(foe,'attack',request_id='dodged-grapple');row=G.relation(self.e,foe);event=G.completed_attack_event(self.e,row['id'],len(row['history'])-1)
  self.assertEqual(result['damage'],0);self.assertEqual(self.a.hp,hp);self.assertEqual(event['result'],'hit_prevented');self.assertFalse(F.activation_allowed(self.a,'ability/회피',{'kind':'daily','uses':1},engine=self.e));self.valid()
