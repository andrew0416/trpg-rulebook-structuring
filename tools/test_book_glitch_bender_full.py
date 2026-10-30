"""Whole Glitch Bender: actual acquisition, native execution and restoration.

Every referenced Move is exercised through Engine.use_move. No recorded hit,
handler name or teaching permission substitutes for an actual native result.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import glitch_bender as B,trainer_feature_acquisition as T,acquired_features as AC
import state_grants as G,world_entities as W,frequency as F,action_points as AP
import move_completion as MC,combat_timing as TIME,move_state as MOVES


class GlitchBenderFullTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rules=Rules(ROOT,ruleset='polygon');cls.base_rulings=deepcopy(cls.rules.rulings)
  import setup_move_state,stellar_tera_blast
  setup_move_state._policy(cls.rules);stellar_tera_blast._policy(cls.rules)
 def setUp(self):self.scene()
 def scene(self,*,edition='supplement',rank=6,cure='korean_glitch_only',moves=None):
  self.rules.rulings=deepcopy(self.base_rulings);self.e=Engine(self.rules,seed=1026763);self.e.grid=Grid(24,16)
  self.edition=edition;self.cure=cure;self.people=[]
  for n,pos in enumerate(((2,4),(3,4),(9,4))):
   extra={'movement':{'land':6},'movement_basis':'current','edges':['feat/버그의-존재'],'items':{}}
   if edition=='homebrew':extra.update(edges=['edge/원소-교감'],edge_choices={'edge/원소-교감':{'type':'에러','authority':B.HB_AUTHORITY}},type_link_skills={'에러':'집중'})
   a=Combatant(self.rules,build_trainer(self.rules,'Glitch actual '+str(n),40,{'hp':300,'atk':20,'def':10,'spa':20,'spd':10,'spe':30-n*3},moves=moves if moves is not None else ['move/몸통박치기','move/울음소리','move/칼춤'],abilities=[],pos=pos,side='party' if n==0 else 'foes',skills={'집중':rank,'오컬트학':rank,'통찰':rank,'전투':3,'육상':3,'곡예':3,'직감':3},extra=extra))
   self.e.gm.add_combatant(a);prepare_body(self.e,a,size='중형',offsets=[(0,0)],reason='actual complete Glitch Bender participant');self.people.append(a)
  self.a,self.b,self.c=self.people;self.base_spd=self.a.stats['spd']
 def acquire(self,feature=B.CLASS,*,edition=None,actor=None,request=None):
  a=actor or self.a;choice={'edition':edition or (self.edition if self.edition!='homebrew' or feature in B.HB_ROWS else 'supplement')}  # parents without a homebrew row keep the supplement source
  if feature==B.CLASS:choice['gm_permission']='GM admits this actual campaign Glitch class'
  if feature==B.BURST:choice['confusion_cure']=self.cure
  return T.acquire_static(self.e,a,feature,acquisition_request_id=request or a.entity_id+'/'+feature,selection=choice)
 def family(self,feature,*,actor=None):
  a=actor or self.a
  if feature!=B.CLASS:
   parent={B.CODE:B.REALITY,B.BURST:B.SHUFFLE}.get(feature,B.CLASS)
   if not B.acquired(a,parent):self.family(parent,actor=a)
  if not B.acquired(a,feature):self.acquire(feature,actor=a)
 def begin(self,actor=None,count=50):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=count)
 def turn(self,actor,count=40):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.start_of_turn(actor,initiative_count=count)
 def reject(self,fn,reason='actual|source|requires|required|already|exhausted|native|frequency|Glitch|lesson|choice|Feature|parent|rank|Range|range'):
  return assert_rejected_unchanged(self.e,fn,reason_pattern=reason)
 def valid(self):
  r=self.e.validate_state();self.assertTrue(r['valid'],r['issues'])
 def restore(self,*,fresh_rules=False):
  rules=Rules(ROOT,ruleset='polygon') if fresh_rules else self.rules
  ids=[a.entity_id for a in self.people];self.e=Engine.import_state(rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)));self.people=[W.actor_index(self.e)[u] for u in ids];self.a,self.b,self.c=self.people[:3]
 def pupil(self,*,points=20):
  p=Combatant(self.rules,build_pokemon(self.rules,'폴리곤',30,moves=[],abilities=[],side='party',pos=(4+len(self.people),8),extra={'tutor_points':points,'trainer_id':self.a.entity_id}))
  self.e.gm.add_combatant(p);prepare_body(self.e,p,size=p.spec.get('size') or '중형',offsets=[(0,0)],reason='actual teaching target body');self.people.append(p);return p
 def native(self,actor,target,mid,*,accuracy=20):
  with patch.object(Engine,'d20',return_value=accuracy):return self.e.use_move(actor,target,mid,set_damage=True)
 def event(self,actor,mid,recipient=None):
  rows=[r for r in self.e._passive_events.values() if r['actor'] is actor and r['move_id']==mid and (recipient is None or r['target'] is recipient)]
  return rows[-1]['id']
 def retrain(self,feature):
  import trainer_retraining as R
  owned=R._owned(self.a);sources={u:R.owned_source(self.e,self.a,u) for u in owned};requirements=R._native_dependencies(self.e,self.a,owned)
  deps={sid:[sources[p] for p in requirements.get(u,[])] for u,sid in sources.items() if u!=feature}
  return self.e.retrain_trainer_source(self.a,feature,request_id='glitch/retire/'+feature,reason='actual consultation',gm_decision={'allowed':True,'reason':'GM approved retraining'},retained_dependencies=deps)

 def test_01_all_book_and_csv_acquisitions_source_owned_tags_slots_replay_restore(self):
  for edition in ('supplement','local_csv'):
   self.scene(edition=edition)
   for feature in B.FEATURES:self.family(feature)
   self.assertEqual(self.a.stats['spd'],self.base_spd+7);self.assertEqual(len(B.records(self.a,active=True)),7)
   self.assertEqual([r['source_id'] for r in AC.class_instances(self.a)],[B.CLASS]);self.assertEqual(set(B.CLASS_MOVES)&set(self.a.moves),set(B.CLASS_MOVES))
   for feature in B.FEATURES:
    row=B.acquired(self.a,feature);self.assertEqual(row['snapshot']['source']['edition'],edition)
    if edition=='local_csv':self.assertEqual(row['snapshot']['source']['row'],B.CSV_ROWS[feature])
   self.assertEqual(self.acquire(B.ERROR),self.acquire(B.ERROR));self.restore();self.valid()

 def test_02_exact_prerequisites_source_choices_and_no_auto_feature_grant(self):
  self.scene(rank=2);self.reject(lambda:self.acquire())
  self.scene();self.a.spec['edges']=[];self.reject(lambda:self.acquire())
  self.scene();self.reject(lambda:self.acquire(B.CODE));self.acquire();self.assertEqual(set(self.a.spec['feats']),{B.CLASS});self.assertFalse(set(B.CLASS_MOVES)&set(self.a.moves))
  self.reject(lambda:T.acquire_static(self.e,self.a,B.ERROR,rank=1,selection={'edition':'supplement'},acquisition_request_id='fake/rank'))
  self.reject(lambda:T.acquire_static(self.e,self.b,B.CLASS,selection={'edition':'supplement','gm_permission':''},acquisition_request_id='no/gm'))

 def test_03_shuffle_expert_book_adept_csv_and_master_burst(self):
  self.scene(rank=4);self.acquire();self.reject(lambda:self.acquire(B.SHUFFLE))
  self.acquire(B.SHUFFLE,edition='local_csv');self.reject(lambda:self.acquire(B.BURST))
  self.scene(rank=5);self.family(B.SHUFFLE);self.assertTrue(set(B.CLASS_MOVES[2:])<=set(self.a.moves));self.reject(lambda:self.acquire(B.BURST))

 def test_31_declared_upper_ranks_acquire_and_restore_without_authorizing_undeclared_history(self):
  try:
   for ordinal in (7,10):
    with self.subTest(ordinal=ordinal):
     self.scene()
     self.rules.rulings.set_mech('gameplay/skill-rank-dice','by_rank_name.버그초월',
      {'rank':ordinal,'dice':'7d6','eng':'GlitchAscendant'},reason='U-001 explicit campaign rank declaration',rules=self.rules)
     for skill in B.SKILLS:
      self.e.gm.set_skill(self.a,skill,ordinal,reason='actual declared ordinary skill sheet',request_id='declared/'+skill)
     self.family(B.BURST)
     self.assertEqual(B.acquired(self.a,B.BURST)['snapshot']['skills'],dict.fromkeys(B.SKILLS,ordinal))
     self.restore();self.valid()
     self.assertEqual(B.acquired(self.a,B.BURST)['snapshot']['skills'],dict.fromkeys(B.SKILLS,ordinal))
     for value in (ordinal+1,True,float(ordinal)):
      with self.subTest(invalid=value):
       snapshot=deepcopy(B.acquired(self.a,B.CLASS)['snapshot']);snapshot['skills']['집중']=value
       self.reject(lambda:B.qualification(self.a,B.CLASS,snapshot,None),reason='declared|actual class skill rank')
     self.reject(lambda:self.e.gm.set_skill(self.a,'집중',ordinal+1,reason='undeclared sheet must not authorize acquisition'),reason='unresolved ordinary numeric')
  finally:self.rules.rulings=deepcopy(self.base_rulings)

 def test_04_raw_class_names_not_permission_and_four_slot_guard(self):
  self.a.spec['feats']=[B.CLASS,B.ERROR];self.reject(lambda:B.arm_error(self.e,self.a,lambda _:True))
  self.scene();self.a.spec['classes']=['class/운동선수','class/멘토','class/지휘관','class/코디네이터'];self.reject(lambda:self.acquire(),reason='four slots')

 def test_05_error_native_replacement_two_ap_and_already_held_reroll(self):
  self.family(B.ERROR);self.begin();self.e.apply_status(self.a,'독',source='gm/actual prior poison',applied_by=self.b)
  before=AP.available(self.a);B.arm_error(self.e,self.a,lambda seen:seen['condition']=='화상',fixed=[5,6]);self.e.apply_status(self.a,'화상',source='gm/actual burn',applied_by=self.b)
  self.assertNotIn('화상',self.a.conditions);self.assertTrue({'독','혼란'}<=self.a.conditions);self.assertEqual(AP.available(self.a),before-2);self.valid()

 def test_06_error_duplicate_immunity_decline_and_failed_callback_keep_native_boundary(self):
  self.family(B.ERROR);self.begin();self.e.apply_status(self.a,'독',source='gm/prior poison');before=AP.available(self.a)
  B.arm_error(self.e,self.a,lambda _:True,fixed=[6]);self.assertFalse(self.e.apply_status(self.a,'독',source='gm/duplicate'));self.assertEqual(AP.available(self.a),before)
  B.arm_error(self.e,self.a,lambda _:False,fixed=[6]);self.e.apply_status(self.a,'화상',source='gm/declined');self.assertIn('화상',self.a.conditions);self.assertEqual(AP.available(self.a),before)
  B.arm_error(self.e,self.a,lambda _:'invented',fixed=[6]);self.reject(lambda:self.e.apply_status(self.a,'얼음',source='gm/actual freeze'))
  self.scene();self.family(B.ERROR);G.replace_baseline(self.e,self.a,'abilities',['불면']);self.begin();before=AP.available(self.a);B.arm_error(self.e,self.a,lambda _:True,fixed=[6]);self.assertFalse(self.e.apply_status(self.a,'잠듦',source='gm/immune sleep'));self.assertEqual(AP.available(self.a),before)

 def test_07_error_parameterized_random_actual_enemy_and_known_move(self):
  for face,condition in ((4,'헤롱헤롱'),(9,'사슬묶기'),(10,'억압')):
   self.scene();self.family(B.ERROR);self.begin();B.arm_error(self.e,self.a,lambda _:True,fixed=[face]);self.e.apply_status(self.a,'화상',source='gm/actual status',applied_by=self.b)
   self.assertIn(condition,self.a.conditions);rows=__import__('condition_instances').records(self.a)
   actual=[r for r in rows if r['effect']['condition']==condition][-1]
   if face==4:self.assertIn(actual['effect']['beloved_id'],{self.b.entity_id,self.c.entity_id})
   if face==9:self.assertIn(actual['effect']['move_id'],MOVES.known(self.rules,self.a.spec))
   self.restore();self.valid()

 def test_08_corrupt_reality_actual_foe_skill_accuracy_damage_pool_and_scene(self):
  for purpose in ('skill','accuracy','damage','external_pool'):
   self.scene();self.family(B.REALITY);self.begin(self.b);before=AP.available(self.a)
   fixed=[6]*6 if purpose=='skill' else [20] if purpose=='accuracy' else [8,8] if purpose=='external_pool' else None
   B.arm_reality(self.e,self.a,self.b,purpose=purpose,decision=lambda first:True,reroll_fixed=fixed)
   if purpose=='skill':self.assertGreater(self.e.skill_check(self.b,'집중',10,fixed=[1]*6)[1],6)
   elif purpose=='external_pool':self.assertEqual(self.e.resolve_native_pool(self.b,purpose=purpose,source=B.REALITY,count=2,sides=8,fixed=[1,1])['total'],16)
   else:self.native(self.b,self.a,'move/몸통박치기',accuracy=1 if purpose=='accuracy' else 18);self.assertLess(self.a.hp,self.a.max_hp)
   self.assertEqual(AP.available(self.a),before);self.assertEqual(F.state(self.a)['activations'][B.REALITY]['used'],1);self.reject(lambda:B.arm_reality(self.e,self.a,self.b,purpose=purpose,decision=lambda _:True));self.valid()

 def test_09_reality_decline_ally_rejection_codec_fresh_choice_and_tamper(self):
  self.family(B.REALITY);self.begin(self.b);self.reject(lambda:B.arm_reality(self.e,self.a,self.a,purpose='skill',decision=lambda _:True))
  B.arm_reality(self.e,self.a,self.b,purpose='skill',decision=lambda _:False);self.e.skill_check(self.b,'집중',10,fixed=[1]*6);self.assertNotIn(B.REALITY,F.state(self.a)['activations'])
  B.arm_reality(self.e,self.a,self.b,purpose='skill',decision=lambda _:True,reroll_fixed=[6]*6);self.restore();self.reject(lambda:self.e.skill_check(self.b,'집중',10,fixed=[1]*6),reason='fresh|authentication')
  B.authenticate_reality(self.e,self.a,lambda _:True);self.e.skill_check(self.b,'집중',10,fixed=[1]*6);self.valid()

 def test_10_code_native_ac2_miss_range_bug_and_recipient_scene_limits(self):
  self.family(B.CODE);self.begin();before=AP.available(self.a);B.code_injection(self.e,self.a,self.b,'blue_screen',fixed_accuracy=1)
  self.assertFalse(B.code_rows(self.b));self.assertEqual(AP.available(self.a),before-1);self.assertEqual(self.a.budget['standard'],0)
  self.begin();self.reject(lambda:B.code_injection(self.e,self.a,self.c,'blue_screen',fixed_accuracy=20))
  self.reject(lambda:B.code_injection(self.e,self.a,self.c,'access_denied',fixed_accuracy=20),reason='range|outside')
  B.code_injection(self.e,self.a,self.b,'access_denied',fixed_accuracy=20);self.begin();self.reject(lambda:B.code_injection(self.e,self.a,self.b,'object_not_found',fixed_accuracy=20))

 def test_11_code_blind_vulnerable_native_accuracy_evasion_and_exact_full_round(self):
  self.family(B.CODE);self.begin(count=50);B.code_injection(self.e,self.a,self.b,'blue_screen',fixed_accuracy=20)
  self.assertTrue({'실명','취약'}<=self.b.conditions);self.assertEqual(__import__('vision_impairment').accuracy_level(self.e,self.b),'ordinary')
  self.turn(self.b,count=40);self.native(self.b,self.a,'move/몸통박치기',accuracy=20);self.restore();self.valid()
  self.e.end_of_turn(self.b);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(51);self.assertIn('실명',self.b.conditions);self.e.at_initiative_count(50);self.assertFalse(B.code_rows(self.b));self.assertNotIn('실명',self.b.conditions)

 def test_12_code_access_native_slowed_at_will_only_and_recipient_global(self):
  self.family(B.CODE);self.begin();B.code_injection(self.e,self.a,self.b,'access_denied',fixed_accuracy=20);self.assertIn('둔화',self.b.conditions)
  self.family(B.CODE,actor=self.c);self.turn(self.c);self.reject(lambda:B.code_injection(self.e,self.c,self.b,'blue_screen',fixed_accuracy=20))
  self.turn(self.b,count=30);before=self.a.hp;self.native(self.b,self.a,'move/몸통박치기');self.assertLess(self.a.hp,before)
  self.begin(self.b);G.replace_baseline(self.e,self.b,'moves',list(self.b.spec['moves'])+[B.METRONOME]);B.arm_metronome(self.e,self.b,lambda ids:{'move_id':ids[0],'target_id':self.a.entity_id});before=deepcopy(self.b.move_uses);self.e.use_move(self.b,self.b,B.METRONOME);self.assertEqual(self.b.move_uses,before)

 def test_13_code_object_native_equipment_and_consumable_benefits_not_ownership(self):
  from test_category2_held_item_reactions import HeldItemReactionTests
  uid=HeldItemReactionTests.equip(self,self.e,self.b,'item/선제공격손톱','glitch-claw');held=deepcopy(self.b.spec['held_equipment']);self.assertEqual(self.b.initiative_bonus,10)
  self.family(B.CODE);self.begin();B.code_injection(self.e,self.a,self.b,'object_not_found',fixed_accuracy=20);self.assertEqual(self.b.initiative_bonus,0);self.assertEqual(self.b.spec['held_equipment'],held)
  self.e.gm.set_hp(self.b,self.b.hp-20,reason='actual damaged recipient');self.b.spec['items']['item/상처약']=1;hp=self.b.hp;self.turn(self.b,count=40)
  self.e.use_item(self.b,'item/상처약',target=self.b);self.assertEqual(self.b.hp,hp);self.assertEqual(self.b.spec['items']['item/상처약'],0);self.assertEqual(self.b.budget['standard'],0)
  paid=list(__import__('consumption_execution').validate(self.b).values())[-1];self.assertEqual(paid['outcome'],'no_effect');self.assertIn('benefit_suppression',paid)
  self.restore();self.assertEqual(self.b.initiative_bonus,0);self.assertEqual(self.b.spec['held_equipment'],held)

 def test_14_code_receipt_deadline_actor_tamper_rejected_and_source_loss_retains_hit(self):
  self.family(B.CODE);self.begin();B.code_injection(self.e,self.a,self.b,'blue_screen',fixed_accuracy=20)
  self.reject(lambda:G.transition(self.e,self.b,lambda se,c:B.code_rows(c)[0].update(count_deadline=(999,99))),reason='lifetime|deadline|changed')
  self.reject(lambda:G.transition(self.e,self.b,lambda se,c:B.code_rows(c)[0]['glitch_code'].update(target_id=self.a.entity_id)),reason='recipient|receipt|changed|evidence')
  self.e.end_of_turn(self.a);self.e.end_round();self.retrain(B.CODE);self.assertTrue(B.code_rows(self.b));self.begin();self.reject(lambda:B.code_injection(self.e,self.a,self.c,'blue_screen',fixed_accuracy=20));self.restore();self.valid()

 def test_15_actual_disable_free_no_command_attacker_move_not_last_move(self):
  self.family(B.NULL);self.begin(self.b);self.native(self.b,self.a,'move/몸통박치기');eid=self.event(self.b,'move/몸통박치기',self.a);self.b.last_move='move/울음소리'
  B.use_disable(self.e,self.a,eid);self.assertEqual(self.a.move_uses[B.DISABLE],1);self.assertIn('사슬묶기',self.b.conditions)
  rows=__import__('condition_instances').records(self.b);self.assertEqual([r for r in rows if r['effect']['condition']=='사슬묶기'][-1]['effect']['move_id'],'move/몸통박치기');self.assertEqual(self.a._action_history,['free']);self.restore();self.valid()

 def test_16_disable_fake_trigger_decline_miss_source_loss_and_free_grant_forgery(self):
  self.family(B.NULL);self.begin(self.b);self.reject(lambda:B.use_disable(self.e,self.a,'fake/event'))
  self.native(self.b,self.a,'move/몸통박치기',accuracy=1);eid=self.event(self.b,'move/몸통박치기',self.a);self.reject(lambda:B.use_disable(self.e,self.a,eid))
  self.reject(lambda:self.e.use_move(self.a,self.b,B.DISABLE,free_action=True,count_use=False))

 def test_17_snatch_actual_interrupt_self_effect_recipient_and_no_duplicated_effect(self):
  self.family(B.NULL);self.begin(self.b);B.arm_snatch(self.e,self.a,target=self.b);self.native(self.b,self.b,'move/칼춤')
  self.assertEqual(self.b.stages['atk'],0);self.assertEqual(self.a.stages['atk'],2);self.assertEqual(self.a.move_uses[B.SNATCH],1);self.restore();self.valid()

 def test_18_metronome_all_move_pool_printed_exclusions_unknown_child_real_completion(self):
  self.family(B.SHUFFLE);self.begin();pool=B.metronome_pool(self.rules);self.assertNotIn(B.SNATCH,pool);self.assertIn('move/물대포',pool);self.assertNotIn('move/물대포',self.a.moves)
  B.arm_metronome(self.e,self.a,lambda ids:{'move_id':ids[0],'target_id':self.b.entity_id,'set_damage':True});before=self.b.hp
  with patch.object(self.e.rng,'choice',return_value='move/물대포'):self.native(self.a,self.a,B.METRONOME)
  self.assertLess(self.b.hp,before);self.assertEqual(self.a.move_uses[B.METRONOME],1);self.assertNotIn('move/물대포',self.a.moves);self.assertNotIn('move/물대포',self.a.move_uses)
  child=[r for r in self.e._move_completions.values() if r['move_id']=='move/물대포'];self.assertEqual(child[-1]['phase'],'complete');self.restore();self.valid()

 def test_19_metronome_burst_three_actual_choices_costs_and_child_anti_forgery(self):
  self.family(B.BURST);self.begin();seen=[]
  def choose(ids):seen.extend(ids);return {'move_id':ids[1],'target_id':self.b.entity_id,'set_damage':True}
  B.arm_metronome(self.e,self.a,choose,burst=True);before=AP.available(self.a)
  with patch.object(self.e.rng,'choice',side_effect=['move/울음소리','move/물대포','move/몸통박치기']):self.native(self.a,self.a,B.METRONOME)
  self.assertEqual(seen,['move/울음소리','move/물대포','move/몸통박치기']);self.assertEqual(AP.available(self.a),before-2);self.assertEqual(self.a.budget['swift'],0);self.assertEqual(self.a.budget['standard'],0)
  self.reject(lambda:B.metronome_effect(self.e,self.a,self.a,{'type':'random_move'},{'move_completion':'forged'}));self.valid()

 def test_20_metronome_child_native_pending_prefix_restore_and_no_reroll_repay(self):
  import passive_events as P
  self.family(B.SHUFFLE);G.replace_baseline(self.e,self.a,'abilities',['자기과신']);self.begin();self.b.side=None;self.e.gm.set_hp(self.b,1,reason='actual lethal child target')
  B.arm_metronome(self.e,self.a,lambda ids:{'move_id':ids[0],'target_id':self.b.entity_id,'set_damage':True})
  with patch.object(self.e.rng,'choice',return_value='move/몸통박치기'):
   with self.assertRaises(P.PassiveEventPending):self.native(self.a,self.a,B.METRONOME)
  self.assertEqual(self.a.move_uses[B.METRONOME],1);self.assertEqual(self.a._action_history,['standard','free']);self.assertLessEqual(self.b.hp,0);before=deepcopy(self.e.export_state());self.restore()
  with self.assertRaises(P.PassiveEventPending):self.e.end_of_turn(self.a)
  self.assertEqual(self.a.move_uses[B.METRONOME],1);self.assertEqual(self.a._action_history,['standard','free']);self.assertTrue(before['_move_completions'] if '_move_completions' in before else self.e._move_completions)

 def test_21_burst_topsy_actual_hit_stages_miss_and_both_cure_editions(self):
  for cure,clears in (('korean_glitch_only',False),('english_target',True)):
   self.scene(cure=cure);self.family(B.BURST);self.begin();self.e.change_stage(self.b,'atk',2);self.native(self.a,self.b,B.TOPSY);self.assertEqual(self.b.stages['atk'],-2)
   before=AP.available(self.a);B.burst(self.e,self.a,self.event(self.a,B.TOPSY,self.b));self.assertIn('혼란',self.b.conditions);self.assertEqual(AP.available(self.a),before-2);self.turn(self.b);self.e.end_of_turn(self.b);self.assertEqual('혼란' not in self.b.conditions,clears);self.valid()
  self.scene();self.family(B.BURST);self.begin();self.native(self.a,self.b,B.TOPSY,accuracy=1);self.reject(lambda:B.burst(self.e,self.a,self.event(self.a,B.TOPSY,self.b)))

 def test_22_homebrew_error_connection_type_ace_equivalence_no_auto_other_class(self):
  self.scene(edition='homebrew');self.acquire();self.assertEqual(B.type_ace_skill(self.e,self.a,'에러'),6)
  self.assertEqual(len(AC.class_instances(self.a)),1);self.assertNotIn('class/타입-에이스',self.a.spec['classes']);self.family(B.NULL);self.family(B.SHUFFLE)
  self.assertEqual(AC.count_for_class(self.a,'class/타입-에이스'),3);self.assertEqual(len(B.type_ace_features(self.a)),3);self.restore();self.valid()

 def test_23_homebrew_actual_two_tp_extended_ability_once_each_pokemon_native_branch(self):
  self.scene(edition='homebrew');self.acquire();p=self.pupil(points=4);before=self.e.elapsed_seconds
  B.teach(self.e,self.a,p,B.CLASS,'last_chance',seconds=60,reason='GM observed complete Extended lesson');self.assertEqual(p.spec['tutor_points'],2);self.assertEqual(self.e.elapsed_seconds,before+60)
  self.assertEqual(__import__('type_ace').ability_branches(self.e,p,'last_chance'),{'에러'});self.assertTrue(__import__('type_ace').ability_registration(self.e,p,'ability/마지막기회'))
  self.reject(lambda:B.teach(self.e,self.a,p,B.CLASS,'strategist',seconds=60,reason='second prohibited lesson'))
  self.restore();p=self.people[-1];self.assertEqual(B.taught_branches(p,'last_chance'),{'에러'});self.valid()

 def test_24_homebrew_all_ten_moves_native_teaching_routes_tp_slots_and_source(self):
  self.scene(edition='homebrew')
  for feature in B.TEACHING:
   self.family(feature)
   for name in B.TEACHING[feature]:
    p=self.pupil(points=2);B.teach(self.e,self.a,p,feature,name,seconds=30,reason='actual printed pool lesson')
    mid=self.rules.move_id(name);self.assertIn(mid,p.moves);self.assertEqual(p.spec['tutor_points'],0);self.assertEqual(MOVES.classifications(self.rules,p.spec)[mid],'taught')
  self.assertEqual(sum(len(v) for v in B.TEACHING.values()),10);self.restore();self.valid()

 def test_25_homebrew_teaching_failure_foreign_target_tp_expiry_and_receipt_tamper(self):
  self.scene(edition='homebrew');self.family(B.CODE);p=self.pupil(points=1);self.reject(lambda:B.teach(self.e,self.a,p,B.CODE,'데이터 드레인',seconds=30,reason='insufficient actual TP'))
  self.scene();self.family(B.CODE);p=self.pupil();self.reject(lambda:B.teach(self.e,self.a,p,B.CODE,'데이터 드레인',seconds=30,reason='book has no HB lesson'))
  self.scene(edition='homebrew');self.acquire();p=self.pupil();B.teach(self.e,self.a,p,B.CLASS,'strategist',seconds=60,reason='actual lesson')
  self.reject(lambda:G.transition(self.e,p,lambda se,c:c.spec[G.KEY]['sources']['glitch-ability-lesson:'+c.entity_id+':ability']['glitch_bender_lesson'].update(choice='last_chance')),reason='changed|receipt')

 def test_26_disable_burst_actual_own_turn_opportunity_hit_suppression_and_cost(self):
  import movement_actions as MOVE,turn
  self.family(B.NULL);self.family(B.BURST);self.begin();before=AP.available(self.a)
  self.assertTrue(turn.spend(self.e,self.a,'shift','actual movement provoking native hit',movement=True))
  with patch.object(Engine,'d20',return_value=20):MOVE.follow_paid_path(self.e,self.a,[(2,3),(1,3)],mode='land',maximum_distance=6)
  eid=self.event(self.b,'struggle',self.a);B.use_disable(self.e,self.a,eid);disable=self.event(self.a,B.DISABLE,self.b)
  B.burst(self.e,self.a,disable);self.assertIn('억압',self.b.conditions);self.assertEqual(AP.available(self.a),before-2);self.assertEqual(self.a.budget['swift'],0)
  self.reject(lambda:B.burst(self.e,self.a,disable));self.restore();self.valid()

 def test_27_snatch_burst_regains_one_native_use_per_move_per_scene_not_extra_cast(self):
  self.family(B.NULL);self.family(B.BURST);self.begin(self.b);B.arm_snatch(self.e,self.a,target=self.b);self.native(self.b,self.b,'move/칼춤')
  eid=self.event(self.a,B.SNATCH,self.b);before=dict(self.a.move_uses)
  # ch07:59 is explicit: a Trainer's Swift is own-turn only. Snatch's
  # Interrupt does not grant a second action or invent next-turn Swift debt.
  self.reject(lambda:B.burst(self.e,self.a,eid,regain=B.SNATCH),reason='swift|Swift|actual|requires')
  self.assertEqual(self.a.move_uses,before);self.assertEqual(self.a.stages['atk'],2);self.restore();self.valid()

 def test_28_korean_glitch_pokemon_confusion_cure_next_actual_owner_turn(self):
  import type_state
  self.family(B.BURST);p=self.pupil();self.e.gm.set_types(p,['에러'],reason='actual selected Polygon Glitch type');type_state.validate_types(self.rules,p.types,label='actual Glitch Pokemon')
  self.begin();self.native(self.a,p,B.TOPSY);B.burst(self.e,self.a,self.event(self.a,B.TOPSY,p));self.assertIn('혼란',p.conditions)
  self.turn(p);self.assertIn('혼란',p.conditions);self.e.end_of_turn(p);self.assertNotIn('혼란',p.conditions);self.restore();self.valid()

 def test_29_source_loss_owned_class_moves_and_tags_permanent_lessons_survive(self):
  self.scene(edition='homebrew');self.family(B.NULL);p=self.pupil();B.teach(self.e,self.a,p,B.NULL,'폴리곤 쇼크',seconds=30,reason='actual permanent teaching')
  before=self.a.stats['spd'];self.retrain(B.NULL);self.assertEqual(self.a.stats['spd'],before-1);self.assertFalse(set(B.CLASS_MOVES[:2])&set(self.a.moves));self.assertIn('move/폴리곤-쇼크',p.moves)
  self.reject(lambda:B.teach(self.e,self.a,p,B.NULL,'액세스 거부',seconds=30,reason='withdrawn teacher Feature'));self.restore();self.valid()

 def test_30_all_homebrew_taught_references_require_native_effects_not_placeholder(self):
  for feature in B.TEACHING:
   for name in B.TEACHING[feature]:
    self.scene(edition='homebrew');self.family(feature)
    p=self.pupil(points=2);B.teach(self.e,self.a,p,feature,name,seconds=30,reason='actual native taught reference');mid=self.rules.move_id(name)
    self.e.gm.set_position(p,(2,6),reason='actual native reference user');self.e.gm.set_position(self.b,(3,6),reason='actual native reference recipient');self.e.gm.set_position(self.c,(4,6),reason='second actual reference recipient')
    self.native(self.b,self.a,'move/울음소리');self.begin(p);before=set(getattr(self.e,'_effect_dispatch_receipts',{}))
    if mid==__import__('glitch_moves').TELE:__import__('glitch_moves').declare_tele_crash(self.e,p,(1,0),reason='actual declared Teleport Crash direction')  # composed 2026-10-30: printed Move now needs its declared direction
    with patch.object(Engine,'d20',return_value=20):
     if name in ('방해 웨이브','블루 스크린','고통 교환'):self.e.use_move_on(p,self.b,mid,[p,self.b,self.c],aim=self.b.pos,set_damage=True)
     else:self.e.use_move(p,self.b,mid,set_damage=True)
    actual=[r for token,r in getattr(self.e,'_effect_dispatch_receipts',{}).items() if token not in before and r['source_id']==mid]
    self.assertTrue(actual,'printed nontrivial native reference produced no actual effect receipts: '+mid);self.assertTrue(all(r['status']=='completed' for r in actual),'native reference effects did not finish: '+mid)


 def test_32_error_restored_offer_requires_fresh_choice_and_failed_roll_keeps_offer(self):
  self.family(B.ERROR);self.begin();B.arm_error(self.e,self.a,lambda _:True,fixed=[6]);self.restore()
  self.reject(lambda:self.e.apply_status(self.a,'화상',source='gm/observed burn',applied_by=self.b),reason='fresh|authentication')
  B.authenticate_error(self.e,self.a,lambda _:True);before=AP.available(self.a)
  self.e.apply_status(self.a,'화상',source='gm/observed burn',applied_by=self.b)
  self.assertIn('혼란',self.a.conditions);self.assertNotIn('화상',self.a.conditions)
  self.assertEqual(AP.available(self.a),before-2);self.assertNotIn('glitch_error_offer',self.a.spec)
  B.arm_error(self.e,self.a,lambda _:True,fixed=[6])
  self.reject(lambda:self.e.apply_status(self.a,'독',source='gm/observed poison',applied_by=self.b),reason='sequence exhausted')
  self.assertIn('glitch_error_offer',self.a.spec);self.restore();self.valid()

 def test_33_error_parameterized_gain_notifies_only_actual_replacement_once(self):
  import blessing_effects as BLE,boss_transitions as BOSS
  self.family(B.ERROR);self.begin();B.arm_error(self.e,self.a,lambda _:True,fixed=[9])
  with patch.object(BLE,'status_received',wraps=BLE.status_received) as received,patch.object(BOSS,'condition_applied',wraps=BOSS.condition_applied) as applied:
   self.assertTrue(self.e.apply_status(self.a,'억압',source='gm/actual suppressed',applied_by=self.b))
  self.assertEqual([call.args[2] for call in received.call_args_list],['사슬묶기'])
  self.assertEqual([call.args[2] for call in applied.call_args_list],['사슬묶기'])
  self.assertNotIn('억압',self.a.conditions)
  rows=__import__('condition_instances').records(self.a)
  self.assertEqual([row['effect']['condition'] for row in rows],['사슬묶기'])
  self.assertEqual(self.a._action_history,['free']);self.restore();self.valid()

 def test_34_error_actual_self_status_move_keeps_original_payment_and_replacement_lifetime(self):
  self.scene(moves=['move/몸통박치기','move/울음소리','move/칼춤','move/냉동빔'])
  self.family(B.ERROR);self.begin();before=AP.available(self.a)
  B.arm_error(self.e,self.a,lambda _:True,fixed=[6]);hp=self.a.hp;self.native(self.a,self.a,'move/냉동빔')
  self.assertEqual(self.a.move_uses['move/냉동빔'],1);self.assertEqual(self.a._action_history,['standard','free'])
  self.assertLess(self.a.hp,hp);self.assertEqual(AP.available(self.a),before-2);self.assertIn('혼란',self.a.conditions);self.assertNotIn('얼음',self.a.conditions)
  self.restore();self.valid()


 def test_35_hb_error_type_ace_children_use_real_parent_receipts_and_three_feature_requirement(self):
  import type_ace as TA
  self.scene(edition='homebrew');self.acquire()
  def acquire(feature):return T.acquire_static(self.e,self.a,feature,branch='에러',acquisition_request_id='actual-error/'+feature)
  self.reject(lambda:acquire(TA.SYNC),reason='three actual')
  acquire(TA.REFRESH);self.family(B.NULL);acquire(TA.SYNC)
  self.assertEqual(TA.acquired(self.a,TA.REFRESH,'에러')['snapshot']['parents'],[B.acquired(self.a,B.CLASS)['request_id']])
  self.assertEqual(set(TA.acquired(self.a,TA.SYNC,'에러')['snapshot']['features']),{B.acquired(self.a,B.CLASS)['request_id'],B.acquired(self.a,B.NULL)['request_id'],TA.acquired(self.a,TA.REFRESH,'에러')['request_id']})
  self.assertEqual(len(AC.class_instances(self.a)),1);self.assertIsNone(TA.acquired(self.a,TA.CLASS,'에러'))
  self.reject(lambda:self.retrain(B.CLASS),reason='prerequisite|retained|depend')
  self.restore();self.valid()
  self.scene();self.family(B.NULL)
  self.reject(lambda:T.acquire_static(self.e,self.a,TA.REFRESH,branch='에러',acquisition_request_id='book-no-equivalence'),reason='type required')

 def test_36_hb_error_type_ace_move_sync_pays_once_and_native_move_uses_error_projection(self):
  import type_ace as TA,pokemon_move_edges as EDGES
  self.scene(edition='homebrew');self.family(B.NULL);self.family(B.SHUFFLE)
  T.acquire_static(self.e,self.a,TA.SYNC,branch='에러',acquisition_request_id='actual-error/sync')
  p=self.pupil(points=2);self.e.gm.set_move(p,'move/몸통박치기',reason='actual known Move before Error Move Sync')
  before=self.e.elapsed_seconds
  TA.sync(self.e,self.a,p,'에러',seconds=60,application_id='error-move-sync',move_id='move/몸통박치기',new_name='에러 몸통박치기',effect_decision={'mode':'preserve','reason':'GM retains the printed push effect.','effects_exec':None},feasibility_review='GM permits this actual Glitch Move conversion.',power_review='Base DB and effects remain unchanged.',reason='actual completed Error Move Sync')
  self.assertEqual(p.spec['tutor_points'],1);self.assertEqual(self.e.elapsed_seconds,before+60)
  self.restore();p=self.people[-1];self.assertEqual(EDGES.prepare(self.e,p,self.rules.move('move/몸통박치기'))['type'],'에러')
  self.e.gm.set_position(p,(2,6),reason='actual adjacent Move user');self.e.gm.set_position(self.b,(3,6),reason='actual adjacent Move recipient')
  self.begin(p);before=self.b.hp;self.native(p,self.b,'move/몸통박치기')
  self.assertLess(self.b.hp,before);self.assertEqual(p.move_uses['move/몸통박치기'],1);self.valid()


 def test_37_error_native_effect_callback_failure_rolls_back_damage_payment_and_receipts(self):
  for area in (False,True):
   for choice in ('cold','invalid','throws'):
    with self.subTest(area=area,choice=choice):
     self.scene(moves=['move/몸통박치기','move/울음소리','move/칼춤','move/냉동빔'])
     self.family(B.ERROR);self.begin();observed=[]
     def callback(facts):
      observed.append(facts['condition'])
      if choice=='throws':raise ValueError('observed player callback failed')
      return 'invalid choice' if choice=='invalid' else True
     B.arm_error(self.e,self.a,callback,fixed=[6])
     if choice=='cold':self.restore()
     def native():
      with patch.object(Engine,'d20',return_value=20):
       return self.e.use_move_on(self.a,self.a,'move/냉동빔',self.e.everyone,set_damage=True) if area else self.e.use_move(self.a,self.a,'move/냉동빔',set_damage=True)
     self.reject(native,reason='fresh|authentication|explicit observed|callback failed|unfinished|pending|effect')
     if choice!='cold':self.assertEqual(observed,['얼음'])
     self.assertIn('glitch_error_offer',self.a.spec);self.assertNotIn('얼음',self.a.conditions);self.valid()

 def test_38_dormant_foe_roll_offer_survives_natural_faint_and_source_withdrawal(self):
  self.family(B.REALITY);self.begin(self.b)
  expected=self.e.skill_roll(self.b,'집중',fixed=[1]*6).total
  B.arm_reality(self.e,self.a,self.b,purpose='skill',decision=lambda _:True,reroll_fixed=[6]*6)
  self.e.gm.set_hp(self.a,0,reason='actual knockout before watched roll');self.assertTrue(self.a.fainted)
  self.restore();self.valid();result=self.e.skill_roll(self.b,'집중',fixed=[1]*6)
  self.assertEqual(result.total,expected);self.assertNotIn(B.REALITY,F.state(self.a)['activations'])
  self.e.gm.set_hp(self.a,self.a.max_hp,reason='actual restored positive HP')
  self.e.end_encounter(self.e.everyone);self.retrain(B.REALITY);self.restore();self.valid()
  self.assertIn('native_roll_offer',self.a.spec)
  result=self.e.skill_roll(self.b,'집중',fixed=[1]*6);self.assertEqual(result.total,expected)
  self.assertNotIn(B.REALITY,F.state(self.a)['activations'])


 def test_39_topsy_burst_requires_actual_current_return_before_another_action(self):
  self.family(B.BURST);self.begin();self.e.change_stage(self.b,'atk',2)
  self.native(self.a,self.b,B.TOPSY);event=self.event(self.a,B.TOPSY,self.b)
  self.assertEqual(self.b.stages['atk'],-2)
  self.e.disengage(self.a,(1,4));self.assertEqual(tuple(self.a.pos),(1,4));self.assertEqual(self.a.budget['shift'],0)
  self.reject(lambda:B.burst(self.e,self.a,event),reason='immediate|unrelated')
  self.assertNotIn('혼란',self.b.conditions);self.restore();self.valid()



 def test_40_snatch_native_costs_recipient_provenance_and_forged_use_rejection(self):
  import combat_move_reactions as R,action_resources as RES,initiative_interrupts as I
  self.family(B.NULL);self.begin(self.b)
  self.reject(lambda:self.e.use_move(self.a,self.b,B.SNATCH),reason='actual|armed|turn|selected')
  B.arm_snatch(self.e,self.a,target=self.b);self.native(self.b,self.b,'move/칼춤')
  parent=next(r for r in self.e._move_completions.values() if r['actor'] is self.b and r['move_id']=='move/칼춤')
  self.assertIsNone(MC.recipient_result(parent,self.b));self.assertTrue(MC.recipient_result(parent,self.a)['hit'])
  self.assertEqual(self.b.move_uses['move/칼춤'],1);self.assertEqual(self.a.move_uses[B.SNATCH],1)
  self.assertEqual(self.b._action_history,['standard']);self.assertEqual(self.a._action_history,['standard'])
  self.assertEqual(RES.pending(self.a),{'standard':1});self.assertIsNone(I.frame(self.e));self.assertIs(self.e._active_turn_actor,self.b)
  effects=[r for r in self.e._effect_dispatch_receipts.values() if r['source_id']=='move/칼춤']
  self.assertTrue(effects);self.assertTrue(all(r['actor'] is self.b and r['target'] is self.a and r['status']=='completed' for r in effects))
  self.reject(lambda:G.transition(self.e,self.a,lambda se,a:a.spec[R.EVENTS][next(iter(a.spec[R.EVENTS]))].update(target_id=self.c.entity_id)),reason='changed|source|recipient|evidence')
  self.restore();self.valid();self.assertEqual((self.a.stages['atk'],self.b.stages['atk']),(2,0))
  parent=next(r for r in self.e._move_completions.values() if r['actor'] is self.b and r['move_id']=='move/칼춤')
  self.reject(lambda:R.snatch_recipient(self.e,self.b,self.a,'move/칼춤',{'move_completion':parent['id']}),reason='actual|retained')

 def test_41_snatch_only_printed_self_and_actual_range_and_owned_source(self):
  import combat_move_reactions as R
  self.family(B.NULL);self.begin(self.b)
  self.reject(lambda:B.arm_snatch(self.e,self.c,target=self.b),reason='owned|known|source|Move')
  self.reject(lambda:B.arm_snatch(self.e,self.a,target=self.c),reason='six|range')
  B.arm_snatch(self.e,self.a,target=self.b);self.native(self.b,self.a,'move/울음소리')
  self.assertNotIn(B.SNATCH,self.a.move_uses);self.assertIn(B.SNATCH,self.a.spec[R.CHOICES])
  self.begin(self.b);self.e.gm.set_position(self.b,(15,4),reason='actual target left Snatch range')
  self.native(self.b,self.b,'move/칼춤');self.assertEqual(self.b.stages['atk'],2);self.assertNotIn(B.SNATCH,self.a.move_uses)
  self.restore();self.valid()

 def snatch_checkpoint(self,owner,event):
  import passive_events as P
  # Explicit authored transport fixture, with no invented Move effect.
  return P.subscribe_policy(self.e,owner,'snatch-native-checkpoint',{
   'schema':1,'id':'test-only-snatch-checkpoint','variants':[{
    'rule_id':'ability/스텔라버스트','source':{'file':'input/db/abilities.csv','sha256':'87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'},
    'values':{'effects':[]},'when':{'$input':'continue_fixture'},
    'inputs':{'continue_fixture':{'type':'boolean','authority':'gm','question':'Test-only transport checkpoint; decline the empty effect'}}}]},event=event)

 def test_42_snatch_pending_response_restore_resumes_parent_without_repay_or_duplicate(self):
  import passive_events as P,initiative_interrupts as I,action_resources as RES
  self.family(B.NULL);key=self.snatch_checkpoint(self.a,'accuracy_resolved');self.begin(self.b)
  B.arm_snatch(self.e,self.a,target=self.b)
  with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,'move/칼춤')
  pending=self.e._passive_pending;self.assertEqual(self.e._passive_events[pending]['move_id'],B.SNATCH)
  self.assertEqual((self.a.stages['atk'],self.b.stages['atk']),(0,0))
  paid=deepcopy((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history));rng=self.e.rng.getstate()
  self.restore()
  with patch.object(Engine,'d20',side_effect=AssertionError('native paid accuracy must not reroll')):
   P.choose(self.e,pending,self.a,key,{'decisions':{'continue_fixture':{'value':False,'reason':'resume the original paid source'}}})
  self.assertEqual((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history),paid)
  self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual((self.a.stages['atk'],self.b.stages['atk']),(2,0))
  self.assertEqual(RES.pending(self.a),{'standard':1});self.assertIsNone(I.frame(self.e));self.assertIsNone(self.e._passive_pending)
  self.assertTrue(all(row['phase']=='complete' for row in self.e._move_completions.values()));self.restore();self.valid()

 def test_43_snatch_nested_external_reaction_own_turn_burst_restores_once_per_move_scene(self):
  import initiative_interrupts as I,action_resources as RES
  self.family(B.NULL);self.family(B.BURST);self.e.gm.set_position(self.c,(4,4),reason='actual second Self Move user within range')
  for n,other in enumerate((self.b,self.c)):
   self.begin();B.arm_snatch(self.e,self.a,target=other)
   # Existing external-rule boundary supplies another actor's paid Standard;
   # it does not grant Snatch or relax the Trainer's own-turn Swift rule.
   request={'id':'snatch-outer-'+str(n),'actor_id':other.entity_id,'source':'homebrew/declared-reaction','priority':0,'mode':'reaction','payment':'next','budget':{'standard':1},'clock':'none'}
   queued=I.queue(self.e,[request],trigger={'kind':'turn','actor_id':self.a.entity_id,'serial':self.a.custom_conditions['combat_turn_serial'],'round':self.e.round_no})
   I.begin(self.e,queued['window_id'],request['id']);self.native(other,other,'move/칼춤')
   self.assertIs(I.frame(self.e)['actor'],other);I.finish(self.e);self.assertIs(self.e._active_turn_actor,self.a)
   event=self.event(self.a,B.SNATCH,other);uses=self.a.move_uses[B.SNATCH];ap=AP.available(self.a)
   if n==0:
    B.burst(self.e,self.a,event,regain=B.SNATCH)
    self.assertEqual(self.a.move_uses[B.SNATCH],uses-1);self.assertEqual(AP.available(self.a),ap-2);self.assertEqual(self.a.budget['swift'],0)
   else:
    self.reject(lambda:B.burst(self.e,self.a,event,regain=B.SNATCH),reason='already|Scene')
    self.assertEqual(self.a.move_uses[B.SNATCH],uses);self.assertEqual(AP.available(self.a),ap)
   self.assertEqual(other.stages['atk'],0);self.assertEqual(RES.pending(self.a),{'standard':1});self.restore();self.valid()
  self.assertEqual(self.a.stages['atk'],4)

 def test_44_snatch_routed_recipient_pending_restore_applies_self_effect_once(self):
  import passive_events as P
  self.family(B.NULL);key=self.snatch_checkpoint(self.b,'move_resolved');self.begin(self.b)
  B.arm_snatch(self.e,self.a,target=self.b)
  with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,'move/칼춤')
  pending=self.e._passive_pending;self.assertEqual((self.a.stages['atk'],self.b.stages['atk']),(2,0));self.restore()
  paid=deepcopy((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history))
  # The original event and its routed recipient share one authored activation receipt.
  for _ in range(2):
   if self.e._passive_pending is None:break
   try:P.choose(self.e,self.e._passive_pending,self.b,key,{'decisions':{'continue_fixture':{'value':False,'reason':'resume actual routed return'}}})
   except P.PassiveEventPending:pass
  self.assertIsNone(self.e._passive_pending);self.assertEqual((self.a.stages['atk'],self.b.stages['atk']),(2,0))
  self.assertEqual((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history),paid);self.restore();self.valid()


 def test_45_snatch_native_multieffect_and_healing_keep_actual_recipient_values(self):
  for name in ('명상','HP회복'):
   with self.subTest(move=name):
    mid=self.rules.move_id(name);self.scene(moves=['move/몸통박치기',mid]);self.family(B.NULL)
    if name=='HP회복':
     self.e.gm.set_hp(self.a,1,reason='actual damaged Snatch recipient')
     self.e.gm.set_hp(self.b,2,reason='actual damaged original Self user')
    self.begin(self.b);B.arm_snatch(self.e,self.a,target=self.b);before=self.a.hp
    self.native(self.b,self.b,mid)
    if name=='명상':
     self.assertEqual((self.a.stages['spa'],self.a.stages['spd']),(1,1));self.assertEqual((self.b.stages['spa'],self.b.stages['spd']),(0,0))
    else:
     self.assertEqual(self.a.hp,min(self.a.max_hp,before+self.a.max_hp//2));self.assertEqual(self.b.hp,2)
    self.assertEqual(self.a.move_uses[B.SNATCH],1);self.assertEqual(self.b.move_uses[mid],1);self.restore();self.valid()


 def test_46_snatch_printed_target_has_no_other_actor_exclusion_own_turn_burst(self):
  import action_resources as RES,initiative_interrupts as I
  self.family(B.NULL);self.family(B.BURST);self.begin();before=AP.available(self.a)
  B.arm_snatch(self.e,self.a,target=self.a);self.native(self.a,self.a,'move/칼춤')
  self.assertEqual(self.a.stages['atk'],2);self.assertEqual(self.a.move_uses['move/칼춤'],1)
  self.assertEqual(self.a.move_uses[B.SNATCH],1);self.assertEqual(RES.pending(self.a),{'standard':1});self.assertIsNone(I.frame(self.e))
  B.burst(self.e,self.a,self.event(self.a,B.SNATCH,self.a),regain=B.SNATCH)
  self.assertEqual(self.a.move_uses[B.SNATCH],0);self.assertEqual(AP.available(self.a),before-2);self.assertEqual(self.a.budget['swift'],0)
  self.assertEqual(self.a.stages['atk'],2);self.restore();self.valid()

 def cold_metronome_restore(self):
  ids=[actor.entity_id for actor in self.people]
  saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
  self.rules=Rules(ROOT,ruleset='polygon')
  self.e=Engine.import_state(self.rules,saved)
  self.people=[W.actor_index(self.e)[uid] for uid in ids];self.a,self.b,self.c=self.people[:3]

 def metronome_parent(self):
  rows=[row for row in self.e._move_completions.values() if row['move_id']==B.METRONOME]
  self.assertEqual(len(rows),1);return rows[0]

 def metronome_dodge(self,actor):
  G.replace_baseline(self.e,actor,'abilities',['회피'])
  self.e.watch_move_defense(actor,[{'actor_id':actor.entity_id,'source':'ability/회피'}],reason='actual optional defense of the generated native Move')

 def test_47_metronome_child_listener_cold_restore_resumes_parent_without_generation_or_repayment(self):
  import passive_events as P
  self.family(B.SHUFFLE);key=self.snatch_checkpoint(self.a,'move_resolved');self.begin()
  calls=[]
  def decide(ids):calls.append(ids);return {'move_id':ids[0],'target_id':self.b.entity_id,'set_damage':True}
  B.arm_metronome(self.e,self.a,decide)
  with patch.object(self.e.rng,'choice',return_value='move/물대포'):
   with self.assertRaises(P.PassiveEventPending):self.native(self.a,self.a,B.METRONOME)
  parent=self.metronome_parent();state=parent['metronome_child'];child_id=state['child_completion']
  self.assertEqual(state['phase'],'waiting');self.assertEqual(self.e._passive_events[self.e._passive_pending]['move_id'],'move/물대포')
  self.assertEqual(len(calls),1);self.assertEqual(self.a._action_history,['standard','free'])
  paid=deepcopy((self.a.move_uses,self.a._action_history,self.a.budget));hp=self.b.hp;rng=self.e.rng.getstate()
  self.cold_metronome_restore()
  with patch.object(self.e.rng,'choice',side_effect=AssertionError('selected child must not be regenerated')),patch.object(Engine,'d20',side_effect=AssertionError('already observed accuracy must not reroll')):
   for _ in range(2):
    if self.e._passive_pending is None:break
    try:P.choose(self.e,self.e._passive_pending,self.a,key,{'decisions':{'continue_fixture':{'value':False,'reason':'resume the retained native return'}}})
    except P.PassiveEventPending:pass
  self.assertIsNone(self.e._passive_pending);self.assertEqual(self.b.hp,hp);self.assertEqual(self.e.rng.getstate(),rng)
  self.assertEqual((self.a.move_uses,self.a._action_history,self.a.budget),paid)
  self.assertEqual(self.metronome_parent()['metronome_result']['child_completion'],child_id)
  self.assertEqual(self.metronome_parent()['phase'],'complete');self.assertEqual(self.e._move_completions[child_id]['phase'],'complete')
  self.assertNotIn('move/물대포',self.a.moves);self.assertNotIn('move/물대포',self.a.move_uses)
  self.cold_metronome_restore();self.valid()

 def test_48_metronome_actual_child_accuracy_wait_retains_selection_and_rejects_tampering(self):
  import passive_events as P,action_lifecycle as A
  self.family(B.SHUFFLE);self.begin();self.metronome_dodge(self.b)
  B.arm_metronome(self.e,self.a,lambda ids:{'move_id':ids[0],'target_id':self.b.entity_id,'set_damage':True})
  with patch.object(self.e.rng,'choice',return_value='move/물대포'):
   with self.assertRaises(P.PassiveEventPending):self.native(self.a,self.a,B.METRONOME)
  pending=self.e._passive_pending;hp=self.b.hp;parent_id=self.metronome_parent()['id']
  self.reject(lambda:G.transition(self.e,self.a,lambda se,a:se._move_completions[parent_id]['metronome_child']['choice'].update(target_id=self.c.entity_id)),reason='choice|changed|recipient')
  self.reject(lambda:G.transition(self.e,self.a,lambda se,a:se._move_completions[parent_id].pop('metronome_child')),reason='Metronome|parent|receipt')
  self.cold_metronome_restore();paid=deepcopy((self.a.move_uses,self.a._action_history,self.a.budget))
  with patch.object(self.e.rng,'choice',side_effect=AssertionError('native selection already exists')),patch.object(Engine,'d20',side_effect=AssertionError('native accuracy already exists')):
   self.e.choose_move_defense(pending,self.b,use=False,reason='decline actual child defense')
  self.assertLess(self.b.hp,hp);self.assertEqual((self.a.move_uses,self.a._action_history,self.a.budget),paid)
  self.assertEqual(self.metronome_parent()['phase'],'complete')
  def forged():
   with A.move_grant(self.e,self.a,self.b,'move/물대포',source=B.METRONOME,kind='free'):pass
  self.reject(forged,reason='grant|source|producer');self.cold_metronome_restore();self.valid()

 def test_49_metronome_snatch_actual_effect_user_child_defense_restore_keeps_paid_parent_actor(self):
  import passive_events as P,action_resources as RES
  self.family(B.NULL);self.family(B.SHUFFLE,actor=self.b);self.e.gm.set_position(self.c,(4,4),reason='actual generated child recipient')
  self.begin(self.b);self.metronome_dodge(self.c);B.arm_snatch(self.e,self.a,target=self.b)
  B.arm_metronome(self.e,self.b,lambda ids:self.fail('the original user must not select the stolen effect'))
  B.arm_metronome(self.e,self.a,lambda ids:{'move_id':ids[0],'target_id':self.c.entity_id,'set_damage':True})
  with patch.object(self.e.rng,'choice',return_value='move/물대포'):
   with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,B.METRONOME)
  parent=self.metronome_parent();state=parent['metronome_child'];child_id=state['child_completion'];pending=self.e._passive_pending
  self.assertIs(parent['actor'],self.b);self.assertIs(self.e._move_completions[child_id]['actor'],self.a)
  self.assertIs(MC.recipient_result(parent,self.a)['actor'],self.a);self.assertIsNone(MC.recipient_result(parent,self.b))
  self.assertIs(self.e._effect_dispatch_receipts[state['receipt']]['actor'],self.b);self.assertIs(self.e._effect_dispatch_receipts[state['receipt']]['target'],self.a)
  self.assertNotIn(B.METRONOME,self.a.moves);self.assertNotIn(B.METRONOME,self.a.move_uses);self.assertEqual(self.b.move_uses[B.METRONOME],1)
  parent_id=parent['id'];self.reject(lambda:G.transition(self.e,self.a,lambda se,a:se._move_completions[parent_id]['metronome_child'].update(effect_user_id=self.b.entity_id)),reason='changed|user|choice')
  paid=deepcopy((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history));hp=self.c.hp
  self.cold_metronome_restore()
  with patch.object(self.e.rng,'choice',side_effect=AssertionError('Snatched selection is already durable')),patch.object(Engine,'d20',side_effect=AssertionError('native child accuracy already observed')):
   self.e.choose_move_defense(pending,self.c,use=False,reason='decline actual stolen-child defense')
  self.assertLess(self.c.hp,hp);self.assertEqual((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history),paid)
  self.assertEqual(self.a._action_history,['standard','free']);self.assertEqual(self.b._action_history,['standard'])
  self.assertEqual(RES.pending(self.a),{'standard':1});self.assertEqual(self.metronome_parent()['phase'],'complete')
  self.cold_metronome_restore();self.valid()

 def test_50_metronome_preinitiation_sucker_wait_resumes_or_cancels_without_child_frequency(self):
  import passive_events as P,combat_move_reactions as R,initiative_interrupts as I
  for knockout in (False,True):
   with self.subTest(knockout=knockout):
    self.scene();self.family(B.NULL);self.family(B.SHUFFLE,actor=self.b)
    self.e.gm.set_position(self.c,(3,5),reason='actual adjacent Sucker Punch responder')
    G.replace_baseline(self.e,self.c,'moves',list(self.c.moves)+[R.SUCKER])
    self.begin(self.b);self.metronome_dodge(self.a)
    if knockout:self.e.gm.set_hp(self.a,1,reason='actual fragile effect user before generated child initiation')
    B.arm_snatch(self.e,self.a,target=self.b);R.arm(self.e,self.c,R.SUCKER)
    B.arm_metronome(self.e,self.b,lambda ids:self.fail('original paid user does not select the Snatched effect'))
    B.arm_metronome(self.e,self.a,lambda ids:{'move_id':ids[0],'target_id':self.c.entity_id,'set_damage':True})
    hp=self.c.hp
    with patch.object(self.e.rng,'choice',return_value='move/물대포'):
     with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,B.METRONOME)
    pending=self.e._passive_pending;state=self.metronome_parent()['metronome_child']
    self.assertIsNone(state['child_completion']);self.assertIsNotNone(state['frame'])
    self.assertEqual(self.e._passive_events[pending]['move_id'],R.SUCKER)
    self.cold_metronome_restore()
    with patch.object(self.e.rng,'choice',side_effect=AssertionError('child choice must survive pre-initiation wait')),patch.object(Engine,'d20',return_value=20):
     self.e.choose_move_defense(pending,self.a,use=False,reason='decline real Sucker Punch defense')
    result=self.metronome_parent()['metronome_result']
    self.assertEqual(result['cancelled'],knockout);self.assertEqual(self.metronome_parent()['phase'],'complete')
    self.assertEqual(self.b.move_uses[B.METRONOME],1);self.assertEqual(self.a.move_uses[B.SNATCH],1);self.assertEqual(self.c.move_uses[R.SUCKER],1)
    self.assertNotIn('move/물대포',self.a.move_uses);self.assertEqual(self.a._action_history,['standard','free'])
    if knockout:self.assertEqual(self.c.hp,hp);self.assertIsNone(result['child_completion'])
    else:self.assertLess(self.c.hp,hp);self.assertEqual(self.e._move_completions[result['child_completion']]['phase'],'complete')
    self.assertIsNone(I.frame(self.e));self.cold_metronome_restore();self.valid()

 def test_51_metronome_restored_unselected_callback_must_be_fresh_and_invalid_child_rolls_back(self):
  self.family(B.SHUFFLE);self.begin()
  B.arm_metronome(self.e,self.a,lambda ids:{'move_id':ids[0],'target_id':self.b.entity_id})
  self.cold_metronome_restore()
  self.reject(lambda:self.native(self.a,self.a,B.METRONOME),reason='fresh|callback|choice')
  B.arm_metronome(self.e,self.a,lambda ids:{'move_id':B.SNATCH,'target_id':self.b.entity_id})
  with patch.object(self.e.rng,'choice',return_value='move/물대포'):
   self.reject(lambda:self.native(self.a,self.a,B.METRONOME),reason='generated|recipient|select')
  self.assertNotIn(B.METRONOME,self.a.move_uses);self.assertEqual(self.a._action_history,[]);self.valid()

 def test_52_metronome_snatch_response_restore_requires_fresh_receiver_choice_then_preserves_second_wait(self):
  import passive_events as P
  self.family(B.NULL);self.family(B.SHUFFLE,actor=self.b);self.e.gm.set_position(self.c,(4,4),reason='actual generated child target')
  key=self.snatch_checkpoint(self.a,'accuracy_resolved');self.begin(self.b);B.arm_snatch(self.e,self.a,target=self.b)
  def arm():
   B.arm_metronome(self.e,self.b,lambda ids:self.fail('Snatch transfers effect selection'))
   B.arm_metronome(self.e,self.a,lambda ids:{'move_id':ids[0],'target_id':self.c.entity_id,'set_damage':True})
  arm()
  with patch.object(self.e.rng,'choice',side_effect=AssertionError('Snatch response precedes random generation')):
   with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,B.METRONOME)
  pending=self.e._passive_pending;self.assertEqual(self.e._passive_events[pending]['move_id'],B.SNATCH)
  self.assertNotIn('metronome_child',self.metronome_parent());self.cold_metronome_restore()
  self.assertNotIn('_glitch_metronome_choices',vars(self.e));arm()
  with patch.object(self.e.rng,'choice',return_value='move/물대포'),patch.object(Engine,'d20',return_value=20):
   with self.assertRaises(P.PassiveEventPending):P.choose(self.e,pending,self.a,key,{'decisions':{'continue_fixture':{'value':False,'reason':'complete actual restored Snatch response'}}})
  child_wait=self.e._passive_pending;self.assertNotEqual(child_wait,pending)
  self.assertEqual(self.e._passive_events[child_wait]['move_id'],'move/물대포')
  selected=deepcopy(self.metronome_parent()['metronome_child']['choice']);paid=deepcopy((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history))
  self.cold_metronome_restore()
  with patch.object(self.e.rng,'choice',side_effect=AssertionError('second wait must not regenerate')),patch.object(Engine,'d20',side_effect=AssertionError('child accuracy already paid and observed')):
   P.choose(self.e,child_wait,self.a,key,{'decisions':{'continue_fixture':{'value':False,'reason':'resume selected native child after second restore'}}})
  self.assertEqual(self.metronome_parent()['metronome_child']['choice'],selected)
  self.assertEqual((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history),paid)
  self.assertIsNone(self.e._passive_pending);self.assertEqual(self.metronome_parent()['phase'],'complete');self.cold_metronome_restore();self.valid()

 def code_attack_row(self):
  return [r for r in self.e._effect_dispatch_receipts.values() if 'code_injection' in r][-1]

 def test_47_code_actual_shield_and_substitute_preserve_recipient_quota(self):
  for defense in ('move/방어','move/대타출동'):
   with self.subTest(defense=defense):
    self.scene(moves=['move/몸통박치기',defense]);self.family(B.CODE);self.begin(self.b,count=60);self.native(self.b,self.b,defense);self.turn(self.a,count=50)
    before=AP.available(self.a);result=B.code_injection(self.e,self.a,self.b,'blue_screen',fixed_accuracy=20)
    self.assertFalse(result.pending);self.assertFalse(B.code_rows(self.b));self.assertEqual(AP.available(self.a),before-1);self.assertEqual(self.a._action_history,['standard'])
    self.assertTrue(F.activation_allowed(self.b,B.CODE+':recipient',B.SCENE,engine=self.e));self.assertFalse(F.activation_allowed(self.a,B.CODE+':blue_screen',B.SCENE,engine=self.e))
    self.assertEqual(self.code_attack_row()['code_injection']['phase'],'complete');self.restore();self.valid()

 def test_48_code_splash_real_jump_restore_resumes_once_without_reroll_or_repayment(self):
  from tumbler_fixture import TumblerScene
  import tumbler as TUM,jump_actions as J,action_resources as RES
  for failed,knocked_out in ((False,False),(True,False),(True,True)):
   with self.subTest(failed_jump=failed,knocked_out=knocked_out):
    self.scene();self.family(B.CODE)
    defender=TumblerScene.add(self,'actual Code Splash defender','trainer',(3,3),edges=[TUM.ACROBAT],side='foes');self.people.append(defender);identity=defender.entity_id
    for feature in (TUM.CLASS,TUM.AERIAL,TUM.FLIP):T.acquire_static(self.e,defender,feature,acquisition_request_id=identity+'/'+feature)
    self.begin();self.e.watch_move_defense(defender,[{'actor_id':identity,'source':TUM.SPLASH}],reason='actual Code Attack response')
    jump={'destination':(4,3),'difficult':failed,'clear_path':True}
    if failed:jump.update(difficulty_skill='곡예',difficulty_dc=100,difficulty_options={'fixed':[1]*6})
    self.rules.rulings.add_answer('native_attack_splash',{'jump':jump},reason='actual received Code hit',scope='scene')
    before=AP.available(self.a);result=B.code_injection(self.e,self.a,defender,'blue_screen',fixed_accuracy=20)
    if failed:
     self.assertTrue(result.pending);self.assertFalse(B.code_rows(defender));jump_id=defender.spec['_jump_pending']
     if knocked_out:self.e.gm.set_hp(self.a,0,reason='actual parent knockout while Splash awaits landing')
     self.valid();self.restore(fresh_rules=True);defender=W.actor_index(self.e)[identity]
     self.reject(lambda:self.e.end_of_turn(self.a),reason='finish|unfinished|pending|original')
     J.resolve_failure(self.e,defender,decision='land',reason_text='finish actual failed Splash landing');self.e.resume_jump_move(defender,event_id=jump_id)
     with patch.object(Engine,'accuracy_check',side_effect=AssertionError('paid hit must not reroll')):
      B.resume_code_injection(self.e,self.a,self.code_attack_row()['receipt'])
    self.assertEqual(AP.available(self.a),before-1);self.assertEqual(self.a._action_history,['standard']);self.assertEqual(defender.move_uses[TUM.SPLASH],1);self.assertEqual(RES.pending(defender).get('shift'),1)
    self.assertEqual(len(B.code_rows(defender)),0 if knocked_out else 1);self.assertEqual(self.code_attack_row()['code_injection']['phase'],'complete');self.assertIs(self.e._active_turn_actor,self.a)
    if knocked_out:self.assertTrue(F.activation_allowed(defender,B.CODE+':recipient',B.SCENE,engine=self.e));self.assertEqual(self.code_attack_row()['code_injection']['cancelled'],'participant_unavailable_after_defense')
    self.restore();self.valid()
    before=self.e.export_state();B.resume_code_injection(self.e,self.a,self.code_attack_row()['receipt']);self.assertEqual(self.e.export_state(),before)

 def test_49_code_same_user_and_preexisting_blind_survive_exact_expiry(self):
  self.family(B.CODE);self.begin(count=50);self.e.apply_status(self.a,'실명',source='gm/earlier independent Blind')
  B.code_injection(self.e,self.a,self.a,'blue_screen',fixed_accuracy=20);self.assertTrue(B.code_rows(self.a));self.assertIn('취약',self.a.conditions)
  self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(51);self.assertTrue(B.code_rows(self.a))
  self.e.at_initiative_count(50);self.assertFalse(B.code_rows(self.a));self.assertIn('실명',self.a.conditions);self.assertNotIn('취약',self.a.conditions);self.restore();self.valid()

 def test_50_code_paid_candy_preserves_lifetime_dose_without_growth_and_rejects_tamper(self):
  import lifetime_consumables as L,consumption_execution as X
  self.family(B.CODE);p=self.pupil();self.e.gm.set_position(p,(4,4),reason='actual Code recipient within range');self.c.spec['items']['item/이상한사탕-1']=1
  self.e.gm.set_position(self.c,(5,4),reason='actual adjacent item user');self.begin();B.code_injection(self.e,self.a,p,'object_not_found',fixed_accuracy=20);before=(p.level,p.spec['exp'])
  self.turn(self.c,count=40);self.e.use_item(self.c,'item/이상한사탕-1',p)
  self.assertEqual((p.level,p.spec['exp']),before);self.assertEqual(self.c.spec['items']['item/이상한사탕-1'],0);self.assertEqual(self.c.budget['standard'],0)
  dose=p.spec[L.KEY]['quotas']['rare_candy']['receipts'][-1];self.assertEqual(dose['ordinal'],1);self.assertTrue(dose['benefit_suppressed']);self.assertEqual(dose['before'],dose['after'])
  receipt=list(X.validate(self.c).values())[-1];self.assertEqual(receipt['outcome'],'no_effect');self.restore();self.valid();p=self.people[-1]
  self.reject(lambda:G.transition(self.e,self.c,lambda se,c:list(X.validate(c).values())[-1]['benefit_suppression'].update(count=99)),reason='lifetime|outside')
  self.reject(lambda:G.transition(self.e,p,lambda se,c:c.spec[L.KEY]['quotas']['rare_candy']['receipts'][-1].pop('benefit_suppressed')),reason='growth|threshold')

 def test_51_code_paid_vitamin_and_gem_no_benefits_and_equipment_restores(self):
  import event_effects as EVENTS
  for item in ('item/타우린','item/불꽃주얼'):
   with self.subTest(item=item):
    self.scene();self.family(B.CODE);p=self.pupil();self.e.gm.set_position(p,(4,4),reason='actual nearby Pokemon item recipient');p.spec.setdefault('items',{})[item]=1;self.begin();B.code_injection(self.e,self.a,p,'object_not_found',fixed_accuracy=20);self.turn(p,count=40)
    stats=deepcopy(p.stats);vitamins=deepcopy(p.spec.get('vitamins',[]));self.e.use_item(p,item,p)
    self.assertEqual(p.spec['items'][item],0);self.assertEqual(p.stats,stats);self.assertEqual(p.spec.get('vitamins',[]),vitamins);self.assertFalse(EVENTS.live(p));self.restore();self.valid()
  self.scene();from test_category2_held_item_reactions import HeldItemReactionTests
  HeldItemReactionTests.equip(self,self.e,self.b,'item/선제공격손톱','code-expiring-claw');held=deepcopy(self.b.spec['held_equipment']);self.family(B.CODE);self.begin(count=50);B.code_injection(self.e,self.a,self.b,'object_not_found',fixed_accuracy=20)
  self.assertEqual(self.b.initiative_bonus,0);self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(50)
  self.assertEqual(self.b.initiative_bonus,10);self.assertEqual(self.b.spec['held_equipment'],held);self.restore();self.valid()

 def test_52_code_original_accuracy_application_and_frame_tampering_rejected(self):
  self.family(B.CODE);self.begin();B.code_injection(self.e,self.a,self.b,'blue_screen',fixed_accuracy=20)
  def attack(se):return next(r['code_injection'] for r in se._effect_dispatch_receipts.values() if 'code_injection' in r)
  for mutate in (lambda state:state['accuracy'].__setitem__(0,False),lambda state:state['application'].update(count=99),lambda state:state['native_frame'].update(source='forged/source'),lambda state:state['facts']['payment'].update(amount=0)):
   self.reject(lambda:G.transition(self.e,self.a,lambda se,c:mutate(attack(se))),reason='changed|receipt|native')
  self.restore();self.valid()

 def test_53_code_fresh_rules_restores_actual_miss_and_hit_without_priming_attack(self):
  for face in (1,20):
   with self.subTest(accuracy=face):
    self.scene();self.family(B.CODE);self.begin();B.code_injection(self.e,self.a,self.b,'blue_screen',fixed_accuracy=face)
    saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False));fresh=Rules(ROOT,ruleset='polygon')
    loaded=Engine.import_state(fresh,saved);self.assertTrue(loaded.validate_state()['valid'])
    restored=W.actor_index(loaded)[self.b.entity_id];self.assertEqual(bool(B.code_rows(restored)),face==20)

 def test_54_code_foreign_same_source_native_frame_is_not_the_original_attack(self):
  self.family(B.CODE);self.begin();B.code_injection(self.e,self.a,self.b,'blue_screen',fixed_accuracy=1)
  self.begin();B.code_injection(self.e,self.a,self.b,'access_denied',fixed_accuracy=20)
  def transplant(se,actor):
   rows=[r['code_injection'] for r in se._effect_dispatch_receipts.values() if 'code_injection' in r]
   rows[-1]['native_frame']=rows[0]['native_frame']
  self.reject(lambda:G.transition(self.e,self.a,transplant),reason='another attack|occurrence');self.restore();self.valid()

 def test_55_code_access_denies_actual_non_at_will_feature_and_ability_actions(self):
  self.family(B.CODE);self.family(B.REALITY,actor=self.b);self.begin();B.code_injection(self.e,self.a,self.b,'access_denied',fixed_accuracy=20);self.turn(self.b,count=40)
  self.reject(lambda:B.arm_reality(self.e,self.b,self.a,purpose='skill',decision=lambda _:True),reason='frequency|exhausted|actual')
  before=self.a.hp;self.native(self.b,self.a,'move/몸통박치기');self.assertLess(self.a.hp,before)
  self.scene();self.family(B.CODE);p=self.pupil();G.replace_baseline(self.e,p,'abilities',['위협']);self.e.gm.set_position(p,(4,4),reason='actual nearby Ability owner');self.begin();B.code_injection(self.e,self.a,p,'access_denied',fixed_accuracy=20);self.turn(p,count=40)
  self.reject(lambda:self.e.activate_ability(p,'위협',self.b),reason='At-Will|frequency');self.assertEqual(self.b.stages['atk'],0);self.assertEqual(p.budget['swift'],1);self.restore();self.valid()

 def test_56_code_object_self_repel_pays_stock_without_stored_benefit(self):
  import repels as R,consumption_execution as X
  self.family(B.CODE);self.b.spec['items']['item/벌레회피스프레이']=1;self.begin();B.code_injection(self.e,self.a,self.b,'object_not_found',fixed_accuracy=20);self.turn(self.b,count=40)
  result=self.e.use_item(self.b,'item/벌레회피스프레이',aim={'reason':'actual self spray application'})
  self.assertEqual(result['outcome'],'no_effect');self.assertEqual(self.b.spec['items']['item/벌레회피스프레이'],0);self.assertFalse(self.b.spec.get(R.KEY));self.assertIn('benefit_suppression',list(X.validate(self.b).values())[-1]);self.restore();self.valid()

 def test_57_code_object_consumed_mushroom_keeps_drawback_and_stock_payment(self):
  import items as ITEMS,consumption_execution as X
  self.family(B.CODE);p=self.pupil();self.e.gm.set_position(p,(4,4),reason='actual Mushroom consumer near Code user')
  W.register_object(self.e,'code-small-mushroom',location={'kind':'unknown'},reason='actual held mushroom',kind='item_instance',item_rule_id='item/작은버섯',owner_id=p.entity_id)
  ITEMS.equip_held(self.e,p,'작은버섯',source_instance_id='code-small-mushroom');self.begin();B.code_injection(self.e,self.a,p,'object_not_found',fixed_accuracy=20);self.turn(p,count=40);hp=p.hp;stages=deepcopy(p.stages)
  self.e.use_item(p,'작은버섯',held_selection='code-small-mushroom')
  self.assertEqual(p.hp,hp-5);self.assertEqual(p.stages,stages);self.assertEqual(p.budget['swift'],0);self.assertIn('consumed',self.e._physical_objects['code-small-mushroom'])
  self.assertEqual(list(X.validate(p).values())[-1]['outcome'],'no_effect');self.restore();self.valid()

 def test_53_metronome_upper_cancels_generated_setup_without_child_frequency(self):
  import passive_events as P,combat_move_reactions as R,initiative_interrupts as I,action_resources as RES
  child='move/뛰어오르기'
  def prepare(*,wait=False,armed=True):
   self.scene();self.family(B.NULL);self.family(B.SHUFFLE,actor=self.b)
   self.e.gm.set_position(self.c,(2,5),reason='actual adjacent Sky Uppercut responder')
   G.replace_baseline(self.e,self.c,'moves',list(self.c.moves)+[R.UPPER])
   self.begin(self.b)
   if wait:self.metronome_dodge(self.a)
   B.arm_snatch(self.e,self.a,target=self.b)
   if armed:R.arm(self.e,self.c,R.UPPER)
   B.arm_metronome(self.e,self.b,lambda ids:self.fail('paid original user does not select the Snatched effect'))
   B.arm_metronome(self.e,self.a,lambda ids:{'move_id':ids[0],'target_id':self.c.entity_id,'set_damage':True})
  for wait in (False,True):
   with self.subTest(wait=wait):
    prepare(wait=wait)
    with patch.object(self.e.rng,'choice',return_value=child):
     if wait:
      with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,B.METRONOME)
     else:self.native(self.b,self.b,B.METRONOME)
    if wait:
     pending=self.e._passive_pending;state=self.metronome_parent()['metronome_child']
     self.assertEqual(self.e._passive_events[pending]['move_id'],R.UPPER)
     self.assertIsNone(state['child_completion']);self.assertIsNotNone(state['frame'])
     paid=deepcopy((self.a.move_uses,self.b.move_uses,self.c.move_uses,self.a._action_history,self.b._action_history,self.c._action_history))
     self.cold_metronome_restore()
     with patch.object(self.e.rng,'choice',side_effect=AssertionError('selected Bounce must not regenerate')),patch.object(Engine,'d20',side_effect=AssertionError('Upper accuracy was already observed')):
      self.e.choose_move_defense(pending,self.a,use=False,reason='decline actual Upper defense after cold restore')
     self.assertEqual((self.a.move_uses,self.b.move_uses,self.c.move_uses,self.a._action_history,self.b._action_history,self.c._action_history),paid)
    parent=self.metronome_parent();state=parent['metronome_child'];result=parent['metronome_result']
    self.assertEqual(parent['phase'],'complete');self.assertTrue(result['cancelled']);self.assertIsNone(result['child_completion'])
    self.assertFalse([row for row in self.e._move_completions.values() if row['actor'] is self.a and row['move_id']==child])
    self.assertIsNone(self.a.setup_move);self.assertNotIn(child,self.a.move_uses)
    self.assertEqual(self.b.move_uses[B.METRONOME],1);self.assertEqual(self.a.move_uses[B.SNATCH],1);self.assertEqual(self.c.move_uses[R.UPPER],1)
    self.assertEqual(self.b._action_history,['standard']);self.assertEqual(self.a._action_history,['standard','free']);self.assertEqual(self.c._action_history,['standard'])
    self.assertEqual(RES.pending(self.a),{'standard':1});self.assertEqual(RES.pending(self.c),{'standard':1})
    response=self.c.spec[R.EVENTS][state['cancelled_by']]
    R.validate_event(self.e,self.c,response)
    self.assertEqual(response['source'],R.UPPER);self.assertEqual(response['native_action_id'],state['frame']['id'])
    received=MC.recipient_result(self.e._move_completions[response['result_completion']],self.a)
    self.assertTrue(received['hit']);self.assertFalse(received.get('cancelled',False))
    parent_id=parent['id']
    self.reject(lambda:G.transition(self.e,self.a,lambda se,a:se._move_completions[parent_id]['metronome_child'].update(cancelled_by='not-an-actual-response')),reason='disposition|reaction|cancel')
    self.assertIsNone(I.frame(self.e));self.assertIsNone(self.e._passive_pending)
    self.cold_metronome_restore();self.valid()
  # Without a successful actual Upper response, generic Bounce preparation
  # still has no compatible completed child. Keep that explicit dependency;
  # neither a miss nor an unarmed choice may fabricate cancellation success.
  native_accuracy=Engine.accuracy_check
  def upper_miss(e,actor,target,move,*args,**kwargs):
   if move['id']==R.UPPER:kwargs['fixed_roll']=1
   return native_accuracy(e,actor,target,move,*args,**kwargs)
  for armed in (True,False):
   with self.subTest(upper_miss=armed,upper_declined=not armed):
    prepare(armed=armed)
    with patch.object(self.e.rng,'choice',return_value=child),patch.object(Engine,'accuracy_check',new=upper_miss):
     self.reject(lambda:self.native(self.b,self.b,B.METRONOME),reason='Metronome native child did not return|setup')
    self.assertNotIn(B.METRONOME,self.b.move_uses);self.assertNotIn(child,self.a.move_uses)
    self.assertIsNone(self.a.setup_move);self.valid()

 def test_58_code_encounter_end_expires_all_bugs_without_scene_refund(self):
  from test_category2_held_item_reactions import HeldItemReactionTests
  for bug in B.BUGS:
   with self.subTest(bug=bug):
    self.scene();HeldItemReactionTests.equip(self,self.e,self.b,'item/선제공격손톱','code-ending-claw')
    held=deepcopy(self.b.spec['held_equipment']);self.family(B.CODE);self.begin()
    self.e.apply_status(self.b,'실명',source='preexisting/blind')
    B.code_injection(self.e,self.a,self.b,bug,fixed_accuracy=20);self.restore()
    self.assertTrue(B.code_rows(self.b,bug));before=F.state(self.b)['scene']
    self.e.end_encounter(self.e.everyone)
    self.assertFalse(B.code_rows(self.b));self.assertTrue(B.frequency_allowed(self.b,'scene'))
    self.assertFalse(B.benefits_blocked(self.b));self.assertNotIn('둔화',self.b.conditions);self.assertNotIn('취약',self.b.conditions)
    self.assertIn('실명',self.b.conditions);self.assertEqual(self.b.initiative_bonus,10);self.assertEqual(self.b.spec['held_equipment'],held)
    self.assertEqual(F.state(self.b)['scene'],before);self.assertFalse(F.activation_allowed(self.b,B.CODE+':recipient',B.SCENE,engine=self.e))
    self.assertFalse(F.activation_allowed(self.a,B.CODE+':'+bug,B.SCENE,engine=self.e));self.restore();self.valid()

if __name__=='__main__':unittest.main()

