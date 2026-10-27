"""Whole Oracle: actual source receipts, clocks, d20 producers and recipient hits."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import oracle as O,trainer_feature_acquisition as T,state_codec as CODEC,world_entities as W
import action_points as AP,frequency as F,perception_observe as P,illusion_state as I
import condition_recovery as SAVE,combat_timing as TIME,ability_transitions as AB,passive_events as PASS

class OracleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old);self.setup()
 def setup(self,rank=6,mystic=True):
  self.e=Engine(self.rules,seed=29672978);self.e.grid=Grid(60,40)
  self.a=self.add('Oracle',(2,2),skills={'통찰':rank,'직감':3},edges=['edge/신비한-감각'] if mystic else [])
  __import__('items').register_feats(self.e,self.a)
  self.b=self.add('enemy',(3,2),side='enemy');self.c=self.add('ally',(3,3));self.p=self.add('real Pokemon',(4,3),kind='pokemon')
 def add(self,name,pos,*,side='party',kind='trainer',skills=None,edges=(),abilities=(),capabilities=()):
  spec=dict(name=name,kind=kind,level=30,size='중형',stats={'hp':100,'atk':30,'def':30,'spa':30,'spd':30,'spe':30},
   moves=['move/몸통박치기','move/째려보기','move/하이퍼보이스','move/위액','move/대타출동','move/그림자분신','move/따라하기'],
   types=['노말'],abilities=list(abilities),classes=[],feats=[],edges=list(edges),capabilities=list(capabilities),
   skills=dict({'육상':4,'곡예':4,'전투':4,'집중':4,'은신':6,'오컬트학':4,'직감':3},**(skills or {})),movement={'land':10,'power':4},exp_bank=100,weight_kg=30,gender='수컷')
  if kind=='pokemon':
   spec['species']='피카츄';spec['moves']=['move/몸통박치기','move/째려보기','move/대타출동','move/그림자분신']
  c=Combatant(self.rules,spec);self.e.gm.add_combatant(c,pos=pos,side=side,reason='actual Oracle participant')
  prepare_body(self.e,c,size='중형',offsets=[(0,0)],reason='actual observed body');self.e.register_abilities(c);return c
 def acquire(self,uid=O.CLASS,actor=None):
  actor=actor or self.a;return T.acquire_static(self.e,actor,uid,acquisition_request_id='oracle:'+actor.entity_id+':'+uid)
 def family(self,uid,actor=None):
  actor=actor or self.a;parent=O.DEFINITIONS[uid]['parent']
  if parent and not O.acquired(actor,parent):self.family(parent,actor)
  if uid==O.PREVIEW:
   for feature in (O.DIVINATION,O.SIGHT):
    if not O.acquired(actor,feature):self.family(feature,actor)
  if not O.acquired(actor,uid):self.acquire(uid,actor)
 def begin(self,actor=None):self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=50)
 def next(self,actor=None):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.end_round();self.begin(actor)
 def reject(self,fn,reason=None):return assert_rejected_unchanged(self.e,fn,reason_pattern=reason)
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  ids=[c.entity_id for c in (self.a,self.b,self.c,self.p)]
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  self.a,self.b,self.c,self.p=[W.actor_index(self.e)[uid] for uid in ids]
 def use(self,a,t,move='move/몸통박치기',face=19):
  with patch.object(Engine,'d20',return_value=face):return self.e.use_move(a,t,move,set_damage=True)
 def store(self,face=17):
  self.family(O.SMALL)
  if not self.e.encounter_active:self.begin()
  with patch.object(Engine,'d20',return_value=face):return self.e.small_prophecy(self.a)
 def mark(self,target=None):return self.e.mark_of_vision(self.a,target or self.c,willing=True,seconds=7,reason='observed actual marking activity')
 def divine(self,mode='augury',**kw):return self.e.divine(self.a,mode,seconds=7,reason='observed negotiated divination method',**kw)
 def pending(self,move='move/몸통박치기',target=None):
  self.e.watch_prescience(self.a,reason='actual owner awaits native recipient hit')
  self.begin(self.b)
  with self.assertRaises(PASS.PassiveEventPending):self.use(self.b,target or self.a,move)
  return self.e._passive_pending
 def choose(self,event,use=True):return self.e.choose_prescience(event,self.a,use=use,reason='actual recipient choice')
 def retrain(self,uid):
  import trainer_retraining as R
  owned=R._owned(self.a);sources={u:R.owned_source(self.e,self.a,u) for u in owned}
  required=R._native_dependencies(self.e,self.a,owned)
  deps={s:[sources[p] for p in required.get(u,[])] for u,s in sources.items() if u!=uid}
  if O.PREVIEW in sources and uid!=O.PREVIEW:deps[sources[O.PREVIEW]]=list({sources[u] for u in sources if u in O.FEATURES and u not in (uid,O.PREVIEW)})
  return self.e.retrain_trainer_source(self.a,uid,request_id='retire:'+uid,reason='actual retraining consultation',gm_decision={'allowed':True,'reason':'approved consultation'},retained_dependencies=deps)
 def sight(self):self.family(O.SIGHT)
 def illusion(self,actor=None):
  actor=actor or self.b;self.e.gm.set_ability(actor,'일루전',reason='actual imported Core ability');self.e.register_abilities(actor);return actor
 def sense(self,observer,target,*fields,mode='visual'):
  return P.observe(self.e,observer,target,P.native(O.SIGHT,[],information=fields or ('presence','identity','shape'),mode=mode))

 def test_seven_actual_receipts_special_defense_idempotence_and_restore(self):
  before=self.a.stats['spd']
  for uid in O.FEATURES:self.family(uid)
  self.assertEqual(len(O.records(self.a,active=True)),7);self.assertEqual(self.a.stats['spd'],before+7)
  __import__('items').register_feats(self.e,self.a);self.e.register_abilities(self.a)
  self.assertEqual(self.a.stats['spd'],before+7);self.assertTrue(AB.active(self.a,O.PICKUP));self.assertTrue(AB.active(self.a,'ability/본능'))
  self.assertFalse(AB.active(self.a,'ability/픽업'));self.restore();self.valid()

 def test_mystic_perception_not_intuition_and_actual_parent_prerequisites(self):
  self.setup(rank=2);self.a.spec['skills']['직감']=6
  self.reject(lambda:self.acquire(),'rank');self.setup(mystic=False);self.reject(lambda:self.acquire(),'Mystic')
  self.setup();self.reject(lambda:self.acquire(O.SMALL),'parent')
  self.setup(rank=3);self.family(O.DIVINATION);self.reject(lambda:self.acquire(O.SMALL),'rank')
  self.reject(lambda:self.acquire(O.MARK),'rank')

 def test_preview_three_distinct_actual_features_master_prescience_and_no_replay(self):
  self.acquire();self.reject(lambda:self.acquire(O.PREVIEW),'three')
  self.family(O.PREVIEW);before=self.a.stats['spd'];self.acquire(O.PREVIEW)
  self.assertEqual(self.a.stats['spd'],before);self.assertEqual(len(O.records(self.a,O.PREVIEW,True)),1)
  self.reject(lambda:T.acquire_static(self.e,self.a,O.PREVIEW,acquisition_request_id='different-second-preview-request'),'already')
  self.setup(rank=5);self.family(O.SIGHT);self.reject(lambda:self.acquire(O.PRESCIENCE),'rank')

 def test_pickup_core_daily_five_minutes_actual_rng_and_physical_item(self):
  self.acquire();before=self.e.elapsed_seconds
  def choose(category):return {'item_id':'item/상처약','instance_id':'pickup/physical','category':category,'reason':'GM chooses actual healing item'}
  with patch.object(Engine,'d20',return_value=14):result=self.e.core_pickup(self.a,seconds=300,reason='actual search',choose_item=choose)
  self.assertEqual(result['category'],'healing');self.assertEqual(self.e.elapsed_seconds-before,300)
  self.assertEqual(self.e._physical_objects['pickup/physical']['item_rule_id'],'item/상처약')
  self.reject(lambda:self.e.core_pickup(self.a,seconds=300,reason='second search',choose_item=choose),'daily');self.restore();self.valid()

 def test_pickup_complete_table_none_short_unknown_item_and_rollback(self):
  self.assertEqual([O.pickup_category(x) for x in range(1,21)],[None]*5+['x_item']*2+['berry']*3+['poke_ball']*3+['healing']*3+['stone','vitamin','held','tm'])
  self.acquire();self.reject(lambda:self.e.core_pickup(self.a,seconds=299,reason='too short',choose_item=lambda c:None),'300|five')
  self.reject(lambda:self.e.core_pickup(self.a,seconds=300,reason='bad GM object',choose_item=lambda c:{'item_id':'item/nonexistent','instance_id':'bad','category':c,'reason':'unavailable'}),'exact real|nothing')
  with patch.object(Engine,'d20',return_value=5):result=self.e.core_pickup(self.a,seconds=301,reason='actual empty search',choose_item=lambda c:None)
  self.assertIsNone(result['item']);self.assertEqual(result['natural'],5)

 def test_divination_unknown_and_shared_daily_three_actual_extended_clock(self):
  self.family(O.DIVINATION);before=self.e.elapsed_seconds
  self.assertEqual(self.divine()['status'],'unknown');self.assertEqual(self.divine('scrying')['status'],'unknown');self.divine()
  self.assertEqual(self.e.elapsed_seconds-before,21);self.reject(lambda:self.divine('scrying'),'Daily|frequency')
  self.restore();self.valid()

 def test_augury_gm_past_present_future_clarity_and_forgotten(self):
  self.family(O.DIVINATION)
  events=[{'at':0,'text':'past uncertain meeting'},{'at':100,'text':'possible future'}]
  self.e.record_divination(self.a,'augury',events,clarity='jumbled',memory='partial',reason='GM offered vague dream')
  result=self.divine();self.assertEqual(result['events'],events);self.assertEqual((result['clarity'],result['memory']),('jumbled','partial'))
  self.e.record_divination(self.a,'augury',events,memory='forgotten',reason='GM observed inability to recall')
  self.assertEqual(self.divine()['status'],'unknown');self.restore();self.valid()

 def test_scrying_actual_current_location_last24hours_not_future(self):
  self.family(O.DIVINATION);self.e.advance_time(90000,[self.a])
  self.e.record_divination(self.a,'scrying',[{'at':3590,'text':'outside'},{'at':3607,'text':'boundary'},{'at':89999,'text':'recent'}],reason='actual GM history')
  result=self.divine('scrying');self.assertEqual([x['text'] for x in result['events']],['boundary','recent'])
  self.reject(lambda:self.e.record_divination(self.a,'scrying',[{'at':99999,'text':'future'}],reason='impossible'),'future')
  self.e.gm.set_position(self.a,(20,20),reason='different actual scene');self.assertEqual(self.divine('scrying')['status'],'unknown')

 def test_scrying_item_requires_actual_current_contact_and_no_arbitrary_actor(self):
  self.family(O.DIVINATION)
  W.register_object(self.e,'scry/item',location={'kind':'grid','cell':(2,3)},reason='actual item',kind='item_instance',item_rule_id='item/상처약',owner_id=self.a.entity_id)
  item=self.e._physical_objects['scry/item'];self.reject(lambda:self.divine('scrying',target=item),'contact')
  P.observe_environment(self.e,self.a,item,paths={'touch':True},present=True,reason='GM observed actual physical contact')
  self.e.record_divination(self.a,'scrying',[{'at':0,'text':'item history'}],target=item,reason='GM item fact')
  self.assertEqual(self.divine('scrying',target=item)['events'][0]['text'],'item history')
  self.reject(lambda:self.divine('scrying',target=self.b),'item|location')

 def test_divination_combat_and_tampered_fact_refuse_without_invented_results(self):
  self.family(O.DIVINATION);self.begin();self.reject(lambda:self.divine(),'noncombat')
  self.e.end_encounter(round_elapsed_seconds=10)
  self.e.record_divination(self.a,'augury',[],reason='GM unknown');self.a.spec[P.DIVINATION_FACTS][0]['memory']='forgotten'
  self.assertFalse(self.e.validate_state()['valid'])

 def test_prophecy_actual_swift_ap_rng_pre_modifier_accuracy_once(self):
  before=AP.available(self.a);stored=self.store(17);self.assertEqual(stored['face'],17);self.assertEqual(AP.available(self.a),before-1)
  self.e.choose_prophecy(self.a,self.a);self.a.accuracy_stage=1
  with patch.object(Engine,'d20',return_value=1):self.e.accuracy_check(self.a,self.b,self.rules.move('move/몸통박치기'))
  self.assertFalse(O.prophecies(self.a));self.assertTrue(any('1 -> 17' in x for x in self.e.log_lines));self.valid()

 def test_prophecy_willing_ally_save_and_unwilling_enemy_atomic(self):
  self.store(19);self.reject(lambda:self.e.choose_prophecy(self.a,self.b,willing=True),'ally')
  self.reject(lambda:self.e.choose_prophecy(self.a,self.c,willing=False),'willing')
  self.e.choose_prophecy(self.a,self.c,willing=True);result=SAVE.saving_check(self.e,self.c,'마비',11,fixed=1)
  self.assertTrue(result['passed']);self.assertEqual(result['natural'],19);self.assertFalse(O.prophecies(self.a))

 def test_prophecy_expiry_next_owner_turn_end_not_other_turn_or_round(self):
  self.store(16);self.e.end_of_turn(self.a);self.e.start_of_turn(self.c,initiative_count=30);self.e.end_of_turn(self.c)
  self.assertTrue(O.prophecies(self.a));self.e.end_round();self.begin();self.assertTrue(O.prophecies(self.a))
  self.e.end_of_turn(self.a);self.assertFalse(O.prophecies(self.a));self.valid()

 def test_prophecy_can_replace_actual_new_prophecy_die_and_multiple_storage(self):
  self.store(18);self.e.choose_prophecy(self.a,self.a);self.next()
  with patch.object(Engine,'d20',return_value=2):result=self.e.small_prophecy(self.a)
  self.assertEqual(result['face'],18);self.assertEqual(len(O.prophecies(self.a)),1);self.restore();self.valid()

 def test_prophecy_restore_preserves_actual_face_pending_choice_and_one_consumption(self):
  self.store(13);self.e.choose_prophecy(self.a,self.c,willing=True);self.restore()
  self.assertEqual(SAVE.saving_check(self.e,self.c,'혼란',11,fixed=1)['natural'],13)
  self.assertEqual(SAVE.saving_check(self.e,self.c,'혼란',11,fixed=2)['natural'],2);self.restore();self.valid()

 def test_prophecy_non_d20_skill_pool_does_not_consume_selected_single_die(self):
  self.store(20);self.e.choose_prophecy(self.a,self.a);self.e.skill_check(self.a,'통찰',10)
  self.assertTrue(O.prophecies(self.a));self.assertIn('oracle_prophecy_choice',self.a.spec)

 def test_mark_actual_bound_ap_distinct_trainers_half_perception_and_self_allowed(self):
  self.family(O.MARK);before=AP.available(self.a);self.mark(self.a);self.mark(self.c);self.mark(self.b)
  self.assertEqual(AP.available(self.a),before-3);self.assertTrue(O.mark_for(self.a,self.a))
  self.reject(lambda:self.mark(self.c),'different');extra=self.add('fourth',(20,20));self.reject(lambda:self.mark(extra),'half')
  self.restore();self.valid()

 def test_mark_floor_odd_rank_target_type_consent_and_clock(self):
  self.setup(rank=5);self.family(O.MARK);before=self.e.elapsed_seconds
  self.reject(lambda:self.mark(self.p),'Trainer');self.reject(lambda:self.e.mark_of_vision(self.a,self.b,willing=False,seconds=7,reason='no consent'),'willing')
  self.mark(self.c);self.mark(self.b);self.assertEqual(self.e.elapsed_seconds-before,14)
  self.reject(lambda:self.mark(self.a),'half')

 def test_mark_one_closed_eye_focus_actual_target_senses_and_context(self):
  self.family(O.MARK);self.mark(self.c);self.mark(self.b);self.e.focus_mark(self.a,self.c)
  self.e.observe_channel_information(self.c,senses={'visual':'actual tree','auditory':'birds'},reason='GM sensory observation')
  self.assertEqual(self.e.read_mark(self.a,self.c,senses=True)['senses']['visual'],'actual tree')
  self.assertEqual(self.sense(self.a,self.b,'presence')['reason'],'mark_of_vision_eyes_closed')
  self.e.focus_mark(self.a,self.b);self.reject(lambda:self.e.read_mark(self.a,self.c,senses=True),'focus')
  self.assertEqual(self.e.read_mark(self.a,self.b,senses=True)['status'],'unknown');self.e.focus_mark(self.a)
  self.mark(self.a);self.e.observe_channel_information(self.a,senses={'visual':'before closing own eyes'},reason='actual pre-focus perspective')
  self.e.focus_mark(self.a,self.a);self.assertEqual(self.e.read_mark(self.a,self.a,senses=True)['status'],'unknown')
  self.e.focus_mark(self.a);self.valid()

 def test_mark_temporary_denial_retains_ap_and_permanent_target_end_releases_once(self):
  self.family(O.MARK);before=AP.available(self.a);self.mark();self.e.focus_mark(self.a,self.c)
  self.e.mark_access(self.c,self.a,allow=False);self.assertEqual(self.e.read_mark(self.a,self.c,senses=True)['status'],'denied');self.assertEqual(AP.available(self.a),before-1)
  self.e.mark_access(self.c,self.a,allow=True);self.assertTrue(O.mark_for(self.a,self.c))
  self.e.mark_access(self.c,self.a,end=True);self.assertEqual(AP.available(self.a),before);self.assertIsNone(O.mark_for(self.a,self.c))
  self.reject(lambda:self.e.mark_access(self.c,self.a,end=True),'Mark');self.restore();self.valid()

 def test_mark_unlimited_distance_rounds_and_rough_direction_independent_of_focus(self):
  self.family(O.MARK);self.mark();self.e.gm.set_position(self.c,(55,35),reason='actual far movement')
  result=self.e.read_mark(self.a,self.c);self.assertEqual((result['distance'],result['direction'],result['precision']),(53,[1,1],'rough'))
  self.begin();self.next();self.assertTrue(O.mark_for(self.a,self.c));self.valid()

 def test_mark_blindsense_keeps_native_immunity_and_target_eyes_do_not_close(self):
  self.family(O.MARK);self.mark();self.e.focus_mark(self.a,self.c)
  import vision_impairment as V
  self.assertEqual(V.explicit_level(self.a),'none');self.assertEqual(V.explicit_level(self.c),'none')
  self.assertEqual(self.sense(self.a,self.b,'presence')['reason'],'mark_of_vision_eyes_closed')
  self.e.observe_channel_information(self.c,senses={'visual':'marked target perspective'},reason='actual open target eyes')
  self.assertEqual(self.e.read_mark(self.a,self.c,senses=True)['senses']['visual'],'marked target perspective')
  blind=self.add('actual Blindsense trainer',(2,4),skills={'통찰':6},edges=['edge/신비한-감각'],capabilities=['맹인 감각'])
  __import__('items').register_feats(self.e,blind);self.family(O.MARK,blind)
  self.e.mark_of_vision(blind,self.c,willing=True,seconds=2,reason='actual second owner mark');self.e.focus_mark(blind,self.c)
  self.assertEqual(V.explicit_level(blind),'none')

 def test_preview_actual_instinct_default_evasion_suppression_and_retraining(self):
  self.family(O.PREVIEW);self.assertTrue(AB.active(self.a,'ability/본능'))
  move=self.rules.move('move/몸통박치기');self.e.enable_execution_trace();self.begin(self.b)
  with patch.object(Engine,'d20',return_value=10):self.e.accuracy_check(self.b,self.a,move)
  ordinary=self.a.evasion('물리',attacker=self.b,engine=self.e)
  uncapped=self.a.evasion('물리',attacker=self.b,engine=self.e,ignore_stats=True)
  self.a.abilities_suppressed=True;self.assertFalse(AB.active(self.a,'ability/본능'))
  self.assertEqual(ordinary,min(9,self.a.evasion('물리',attacker=self.b,engine=self.e)+2))
  self.assertEqual(self.a.evasion('물리',attacker=self.b,engine=self.e,ignore_stats=True),uncapped-2);self.a.abilities_suppressed=False
  self.e.end_encounter(round_elapsed_seconds=10);spd=self.a.stats['spd'];self.retrain(O.PREVIEW)
  self.assertFalse(AB.active(self.a,'ability/본능'));self.assertEqual(self.a.stats['spd'],spd-1);self.valid()
  import test_book_chronicler_acquisition as CF,chronicler as CH
  f=CF.ChroniclerAcquisitionTests();f.rules=self.rules;f.setup();f.acquire();f.acquire(CH.PROFILING)
  f.e.gm.set_ability(f.b,'본능',reason='actual Defensive Instinct holder');f.e.register_abilities(f.b)
  f.archive_subject(f.b,'pokemon','actual-instinct-profile');ordinary=f.b.evasion('물리',attacker=f.p,engine=f.e,ignore_stats=True)
  f.communication();f.combat(f.t);CH.profile_order(f.e,f.t,f.p);f.e.end_of_turn(f.t);f.e.start_of_turn(f.p,initiative_count=20)
  self.assertTrue(CH.defensive_ignored(f.e,f.p,f.b))
  self.assertEqual(f.b.evasion('물리',attacker=f.p,engine=f.e,ignore_stats=True),ordinary-2)
  with patch.object(Engine,'d20',return_value=10):f.e.accuracy_check(f.p,f.b,self.rules.move('move/전광석화'))
  f.valid()

 def test_instinct_independent_permanent_source_survives_preview_withdrawal(self):
  self.e.gm.set_ability(self.a,'본능',reason='actual independent permanent ability');self.e.register_abilities(self.a);self.family(O.PREVIEW)
  before=self.a.evasion('물리',attacker=self.b,engine=self.e);self.retrain(O.PREVIEW)
  self.assertTrue(AB.active(self.a,'ability/본능'));self.assertEqual(self.a.evasion('물리',attacker=self.b,engine=self.e),before);self.restore();self.valid()

 def test_unveiled_actual_illusion_keyword_move_immunity_no_secondary(self):
  self.sight();self.begin();hp=self.a.hp;self.use(self.a,self.a,'move/그림자분신')
  self.assertEqual(self.a.hp,hp);self.assertFalse(self.a.coats)
  self.assertTrue(any(O.SIGHT in line for line in self.e.log_lines));self.valid()

 def test_unveiled_actual_illusionist_capability_projection_and_dismissal(self):
  self.sight();producer=self.add('actual Illusionist',(3,4),kind='pokemon',capabilities=['환영술사']);self.begin(producer)
  I.create(self.e,producer,'illusion/oracle',location={'kind':'grid','cell':(4,4)},dimensions_cm={'length':30,'width':20,'height':10},appearance='blue fox',reason='native actual capability image')
  obj=self.e._physical_objects['illusion/oracle'];self.assertIsNone(self.sense(self.c,obj,'identity')['values']['identity'])
  self.assertEqual(self.sense(self.a,obj,'identity')['values']['identity'],'illusion/oracle')
  self.e.end_of_turn(producer);self.e.start_of_turn(self.a,initiative_count=30);self.e.dispel_illusions(self.a)
  self.assertEqual(self.e._physical_objects['illusion/oracle']['status'],'dismissed');self.restore();self.valid()

 def test_illusion_focus_rank_mark_limit_forfeit_and_physical_disguise_preserved(self):
  self.illusion();self.begin(self.b)
  targets=[self.a,self.c,self.p,self.add('fourth object subject',(5,4)),self.add('fifth subject',(5,5))]
  for target in targets[:4]:
   self.e.mark_illusion_appearance(self.b,target);self.next(self.b)
  self.reject(lambda:self.e.mark_illusion_appearance(self.b,targets[4]),'Focus')
  self.e.mark_illusion_appearance(self.b,targets[4],forfeit=self.a.entity_id)
  self.assertNotIn(self.a.entity_id,self.b.spec[I.ABILITY_ILLUSION]['marks']);self.sight()
  W.register_object(self.e,'mundane/prop',kind='item_instance',item_rule_id='item/상처약',location={'kind':'grid','cell':(3,2)},reason='actual physical prop',owner_id=self.b.entity_id)
  self.next(self.a);self.e.dispel_illusions(self.a);self.assertIn('mundane/prop',self.e._physical_objects);self.restore();self.valid()

 def test_illusion_real_standard_marks_focus_limit_exact_appearance_types_moves_unchanged(self):
  self.illusion();self.begin(self.b);types=list(self.b.types);moves=list(self.b.moves)
  self.e.mark_illusion_appearance(self.b,self.c);self.e.mimic_illusion_appearance(self.b,self.c)
  self.assertIsNotNone(I.ability_illusion_active(self.b));self.assertEqual(self.b.types,types);self.assertEqual(self.b.moves,moves)
  self.reject(lambda:self.e.mimic_illusion_appearance(self.b,self.c),'round');self.next(self.b)
  self.e.mark_illusion_appearance(self.b,self.a);self.assertEqual(len(self.b.spec[I.ABILITY_ILLUSION]['marks']),2)
  self.e.end_encounter(round_elapsed_seconds=10);self.e.mimic_illusion_appearance(self.b,self.a)
  self.assertIsNotNone(I.ability_illusion_active(self.b));self.restore();self.valid()

 def test_illusion_vague_audio_truth_for_oracle_and_actual_damaging_hit_ends(self):
  self.sight();self.illusion();self.begin(self.b);self.e.mark_illusion_appearance(self.b,self.c);self.e.mimic_illusion_appearance(self.b,self.c)
  self.assertEqual(self.sense(self.c,self.b,'identity')['reason'],'ability_illusion_appearance')
  self.assertNotEqual(self.sense(self.a,self.b,'identity')['reason'],'ability_illusion_appearance')
  self.assertIsNone(self.sense(self.c,self.b,'text',mode='auditory')['values']['text'])
  self.next(self.a);self.use(self.a,self.b);self.assertIsNone(I.ability_illusion_active(self.b));self.valid()

 def test_illusion_dismiss_and_actual_pokeball_release_free_boundary(self):
  self.illusion(self.p);self.begin(self.p);self.e.mark_illusion_appearance(self.p,self.c)
  I.choose_release_appearance(self.e,self.p,self.c);self.e.gm.recall(self.p,reason='actual recall');self.e.gm.send_out(self.p,pos=(4,3),reason='actual release')
  self.assertIsNotNone(I.ability_illusion_active(self.p));self.e.dismiss_illusion_appearance(self.p);self.assertIsNone(I.ability_illusion_active(self.p));self.restore();self.valid()

 def test_unveiled_actual_genjutsu_and_illusionist_are_fake_and_burst_four(self):
  self.sight();import ninja as N
  T.acquire_static(self.e,self.b,N.CLASS,acquisition_request_id='ninja-class');T.acquire_static(self.e,self.b,N.GENJUTSU,acquisition_request_id='ninja-genjutsu')
  self.begin(self.b);self.e.use_genjutsu(self.b,appearance='ordinary rock')
  self.assertNotEqual(self.sense(self.a,self.b,'identity')['reason'],'genjutsu_mundane_object')
  self.e.end_of_turn(self.b);self.e.start_of_turn(self.a,initiative_count=30);result=self.e.dispel_illusions(self.a)
  self.assertIn(self.b.entity_id+':genjutsu',result['ended']);self.assertIsNone(I.genjutsu_active(self.b));self.valid()

 def test_unveiled_substitute_bypass_and_double_team_not_activated_against_owner(self):
  self.sight();self.begin(self.b);self.use(self.b,self.b,'move/대타출동');self.next(self.a)
  before=self.b.hp;self.use(self.a,self.b);self.assertLess(self.b.hp,before);self.assertTrue(__import__('substitute').live(self.b))
  self.next(self.b);self.use(self.b,self.b,'move/그림자분신');coat=deepcopy(self.b.coats);self.next(self.a)
  with patch.object(Engine,'d20',return_value=19):self.e.accuracy_check(self.a,self.b,self.rules.move('move/몸통박치기'))
  self.assertEqual(self.b.coats,coat);self.valid()

 def test_unveiled_burst_ends_real_illusion_ability_substitute_and_double_team_only_in_range(self):
  self.sight();self.illusion();self.begin(self.b);self.e.mark_illusion_appearance(self.b,self.c);self.e.mimic_illusion_appearance(self.b,self.c)
  self.use(self.b,self.b,'move/대타출동');self.next(self.c);self.use(self.c,self.c,'move/그림자분신')
  self.e.gm.set_position(self.c,(20,20),reason='outside Burst four');self.next(self.a);result=self.e.dispel_illusions(self.a)
  self.assertFalse(__import__('substitute').live(self.b));self.assertIsNone(I.ability_illusion_active(self.b));self.assertTrue(self.c.coats);self.assertTrue(result['ended']);self.restore();self.valid()

 def test_prescience_actual_hit_becomes_miss_no_damage_secondary_scene_free(self):
  self.family(O.PRESCIENCE);hp=self.a.hp;event=self.pending();self.choose(event)
  self.assertEqual(self.a.hp,hp);self.assertIsNone(self.e._passive_pending);self.assertEqual(self.a._action_history,['free'])
  completed=list(self.e._move_completions.values())[-1];self.assertFalse(completed['results'][self.a.entity_id]['hit'])
  self.reject(lambda:self.e.watch_prescience(self.a,reason='second scene use'),'frequency');self.restore();self.valid()

 def test_prescience_actual_miss_never_prompts_or_pays_and_direct_fake_hit_refused(self):
  self.family(O.PRESCIENCE);self.e.watch_prescience(self.a,reason='actual watch');self.begin(self.b);hp=self.a.hp;self.use(self.b,self.a,face=1)
  self.assertEqual(self.a.hp,hp);self.assertIsNone(self.e._passive_pending);self.assertNotIn(O.PRESCIENCE,self.a.spec.get('frequency_state',{}).get('activations',{}))
  self.reject(lambda:O.prepare(self.e,self.a,'fake-event'),'actual native')

 def test_prescience_decline_then_restore_pending_accept_exact_once(self):
  self.family(O.PRESCIENCE);event=self.pending();self.choose(event,False);self.assertLess(self.a.hp,self.a.max_hp)
  self.next(self.b);self.e.watch_prescience(self.a,reason='actual later watch')
  with self.assertRaises(PASS.PassiveEventPending):self.use(self.b,self.a)
  event=self.e._passive_pending;hp=self.a.hp;self.restore();self.choose(event);self.assertEqual(self.a.hp,hp)
  self.reject(lambda:self.choose(event),'pending|choice|actual');self.restore();self.valid()

 def test_prescience_substitute_gets_hit_no_holder_choice_or_scene_payment(self):
  self.begin();self.use(self.a,self.a,'move/대타출동');self.assertTrue(__import__('substitute').live(self.a))
  self.family(O.PRESCIENCE);self.next(self.b);self.e.watch_prescience(self.a,reason='await actual holder hit');hp=self.a.hp
  self.use(self.b,self.a);self.assertIsNone(self.e._passive_pending);self.assertEqual(self.a.hp,hp)
  self.assertNotIn(O.PRESCIENCE,self.a.spec.get('frequency_state',{}).get('activations',{}));self.valid()

 def test_prescience_sonic_bypasses_substitute_actual_holder_can_react(self):
  self.begin();self.use(self.a,self.a,'move/대타출동');self.assertTrue(__import__('substitute').live(self.a))
  self.family(O.PRESCIENCE);self.next(self.b);self.e.watch_prescience(self.a,reason='actual sonic holder hit')
  with patch.object(Engine,'d20',return_value=19):
   with self.assertRaises(PASS.PassiveEventPending):self.e.use_move_on(self.b,self.a,'move/하이퍼보이스',self.e.everyone,set_damage=True)
   hp=self.a.hp;self.choose(self.e._passive_pending)
  self.assertEqual(self.a.hp,hp);self.assertTrue(__import__('substitute').live(self.a));self.valid()

 def test_prescience_area_only_owner_misses_other_actual_recipient_still_hit_once(self):
  self.family(O.PRESCIENCE);self.e.gm.set_position(self.b,(1,2),reason='actual cone origin');self.e.gm.set_position(self.c,(3,2),reason='actual second cone target')
  self.e.watch_prescience(self.a,reason='actual area recipient');self.begin(self.b);hp=(self.a.hp,self.c.hp)
  with patch.object(Engine,'d20',return_value=19):
   with self.assertRaises(PASS.PassiveEventPending):self.e.use_move_on(self.b,self.a,'move/하이퍼보이스',self.e.everyone,set_damage=True)
   self.choose(self.e._passive_pending)
  self.assertEqual(self.a.hp,hp[0]);self.assertLess(self.c.hp,hp[1]);self.assertEqual(self.b.move_uses['move/하이퍼보이스'],1);self.restore();self.valid()

 def test_prescience_routed_actual_interceptor_not_original_accuracy_target(self):
  self.family(O.PRESCIENCE);self.e.watch_prescience(self.a,reason='actual interceptor recipient')
  self.e.watch_move_defense(self.c,[{'actor_id':self.a.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual intercept declaration');self.begin(self.b);hp=(self.a.hp,self.c.hp)
  with self.assertRaises(PASS.PassiveEventPending):self.use(self.b,self.c)
  event=self.e._passive_pending
  with self.assertRaises(PASS.PassiveEventPending):
   self.e.choose_move_defense(event,self.a,use=True,options={'path':[(2,2),(2,3),(3,3)],'skill':'육상','mode':'land','shove_destination':[4,2],'roll_options':{'fixed':[6,6,6,6]}},reason='actual native interception')
  self.choose(self.e._passive_pending);self.assertEqual((self.a.hp,self.c.hp),hp);self.assertEqual(self.a.pos,(3,3));self.restore();self.valid()

 def test_mark_retraining_releases_actual_ap_and_only_owned_stat_source(self):
  self.family(O.MARK);self.family(O.DIVINATION);before=AP.available(self.a);self.mark();self.e.focus_mark(self.a,self.c);spd=self.a.stats['spd'];self.retrain(O.MARK)
  self.assertEqual(AP.available(self.a),before);self.assertFalse(O.marks(self.c));self.assertEqual(self.a.stats['spd'],spd-1);self.assertTrue(O.acquired(self.a,O.DIVINATION));self.restore();self.valid()

if __name__=='__main__':unittest.main()
