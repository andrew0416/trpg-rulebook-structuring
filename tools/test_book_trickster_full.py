"""Whole Trickster: real acquisitions, completed Moves and native consumers.

Core 1.05 is primary; KR/CSV choices retain their printed differences.
No manually authored completion, effect, interrupt or skill-roll receipt is used.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib,json,sys,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import test_category2_training_state as FIX
import trainer_feature_acquisition as ACQ
import trickster as T
import action_points as AP
import action_lifecycle as ACTION
import blessing_effects as B
import combat_maneuvers as MANEUVERS
import combat_timing as TIME
import condition_instances as CONDITIONS
import condition_recovery as RECOVERY
import effects_ext as EXT
import frequency as F
import hazard_state as H
import state_codec as CODEC
import substitute as SUBSTITUTE
import temporary_hp as TEMP
import turn as TURN
import weather_state as WEATHER
import world_entities as W

CELLS8=((3,1),(3,2),(3,3),(4,1),(4,2),(4,3),(5,1),(5,2))


class TricksterFullTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

 def setUp(self):
  previous=self.rules.rulings;self.rules.rulings=deepcopy(previous)
  self.addCleanup(setattr,self.rules,'rulings',previous)
  self.setup()

 def setup(self,*,guile=6,abilities=()):
  helper=FIX.TrainingStateTests();helper.r=self.rules;helper.setUp()
  self.e,self.t,self.ps,self.foe=helper.e,helper.t,helper.ps,helper.enemy
  self.p,self.q=self.ps[:2];self.serial=0
  self.t.spec['feats']=[];self.t.spec['classes']=[]
  self.t.spec['skills']={'교활':guile,'육상':3,'은신':3,'곡예':3,'매력':3,'집중':3}
  self.foe.spec['skills']={'교활':2,'육상':2,'은신':2,'곡예':2,'매력':2,'집중':2}
  for ability in abilities:
   self.e.gm.set_ability(self.foe,ability,reason='actual starting Ability fixture, not a class effect')
  self.e.grid=Grid(24,16)
  for a,pos in zip([self.t,*self.ps,self.foe],[(2,2),(3,2),(3,3),(12,12),(13,12),(4,2)]):
   self.e.gm.set_position(a,pos,reason='actual Trickster scene geometry')
   prepare_body(self.e,a,size='중형',offsets=[(0,0)],reason='actual Trickster participant body')

 def acquire(self,feature=T.CLASS,*,rank=None,source='core',techniques=None,origins=None):
  self.serial+=1;selection={'source':source}
  if techniques is not None:selection['techniques']=list(techniques)
  if origins is not None:selection['technique_sources']=origins
  return ACQ.acquire_static(self.e,self.t,feature,rank=rank,selection=selection,
   acquisition_request_id='trickster/'+str(self.serial)+'/'+feature)

 def family(self,*,source='core',techniques=(T.MIND,T.ESCAPE),origins=None):
  self.acquire();self.acquire(T.BAG,rank=1,techniques=techniques,origins=origins)
  self.acquire(T.STACK,source=T.CSV[T.STACK] if source=='csv' else source)
  self.acquire(T.FLOURISH,source=T.CSV[T.FLOURISH] if source=='csv' else source)
  self.acquire(T.ENCORE,source=T.CSV[T.ENCORE] if source=='csv' else source)
  self.acquire(T.BAG,rank=2,techniques=(T.SHELL,T.IMPROMPTU),origins=origins)
  self.acquire(T.SLEIGHT)

 def learn(self,move,actor=None):
  self.e.gm.set_move(actor or self.p,move,reason='actual learned Trickster Move')

 def close(self):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)

 def begin(self,actor=None,count=60):
  self.close();self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.p,initiative_count=count)

 def completion(self,actor=None):
  return [r for r in self.e._move_completions.values() if r['actor'] is (actor or self.p)][-1]

 def use(self,move,*,actor=None,target=None,face=18,aim=None,begin=True):
  actor=actor or self.p;target=target or self.foe
  self.learn(move,actor)
  if begin:self.begin(actor)
  previous=set(getattr(self.e,'_move_completions',{}))
  with patch.object(Engine,'d20',return_value=face):
   if B.definition(self.e.r,move) is not None:self.e.use_move(actor,actor,move)
   else:self.e.use_move_on(actor,target,move,self.e.everyone,aim=aim,
     set_damage=self.e.r.move(move)['class'] in ('물리','특수'))
  row=self.completion(actor);self.assertEqual(row['phase'],'complete');self.assertTrue(row['sealed'])
  self.assertNotIn(row['id'],previous,'native Move must actually activate, not reuse an earlier completion')
  return row

 def reject(self,operation,reason):
  return assert_rejected_unchanged(self.e,operation,reason_pattern=reason)

 def restore(self):
  ids=[a.entity_id for a in [self.t,*self.ps,self.foe]]
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  actors=W.actor_index(self.e);self.t=actors[ids[0]];self.ps=[actors[x] for x in ids[1:-1]]
  self.p,self.q=self.ps[:2];self.foe=actors[ids[-1]]

 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])

 def hazards(self,kind=None):
  return [r for env in self.e.hazards.values() for r in env['instances'] if kind is None or r['kind']==kind]

 def source_condition(self,condition,target=None):
  previous=getattr(self.e,'_inflictor',None);self.e._inflictor=self.p
  try:self.e.apply_status(target or self.foe,condition)
  finally:self.e._inflictor=previous
  self.assertIn(condition,(target or self.foe).conditions)

 def other_pair(self):
  common={'level':20,'stats':deepcopy(self.t.spec['stats']),'movement':{'land':6,'swim':3,'sky':0},'moves':[],'side':'party'}
  trainer=Combatant(self.rules,dict(common,name='other Trickster',kind='trainer',skills={'교활':6,'육상':3,'은신':3,'곡예':3,'매력':3,'집중':3},pos=(2,1)))
  pokemon=Combatant(self.rules,dict(common,name='other Pokemon',kind='pokemon',trainer_id=trainer.entity_id,trainer=trainer.name,pos=(3,1)))
  for actor in (trainer,pokemon):
   self.e.gm.add_combatant(actor,reason='actual independent Trickster pair fixture')
   prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='actual independent participant body')
  self.e.gm.observe_loyalty(pokemon,3,reason='actual independent willing Pokemon relationship, same native fixture boundary')
  ACQ.acquire_static(self.e,trainer,T.CLASS,selection={'source':'core'},acquisition_request_id='other/class')
  ACQ.acquire_static(self.e,trainer,T.BAG,rank=1,selection={'source':'core','techniques':[T.MIND,T.ESCAPE]},acquisition_request_id='other/bag')
  ACQ.acquire_static(self.e,trainer,T.STACK,selection={'source':'core'},acquisition_request_id='other/stack')
  return trainer,pokemon

 def test_actual_class_acquisition_has_no_automatic_feature_or_technique(self):
  self.acquire();self.assertEqual([r['feature_id'] for r in T.records(self.t,active=True)],[T.CLASS])
  self.assertIsNone(T.technique(self.t,T.MIND));self.assertIsNone(T.acquired(self.t,T.STACK))
  self.restore();self.assertEqual(T.source(self.t,T.CLASS),'core');self.valid()

 def test_guile_parent_feature_count_and_rank_are_actual_acquisition_gates(self):
  self.setup(guile=2)
  self.reject(lambda:self.acquire(),'Guile')
  self.setup();self.reject(lambda:self.acquire(T.STACK),'Trickster class')
  self.acquire();self.reject(lambda:self.acquire(T.ENCORE),'number of Trickster')
  self.reject(lambda:self.acquire(T.BAG,rank=2,techniques=(T.SHELL,T.IMPROMPTU)),'next actual rank|first Bag rank')
  self.reject(lambda:self.acquire(T.BAG,rank=1,techniques=(T.MIND,)),'two real Techniques')
  self.reject(lambda:self.acquire(T.STACK,source='official-playtest'),'reviewed Trickster source')

 def test_two_rank_choices_remain_explicit_and_survive_restore(self):
  self.acquire();self.acquire(T.BAG,rank=1,techniques=(T.MIND,T.ESCAPE))
  self.assertIsNone(T.technique(self.t,T.SHELL))
  self.acquire(T.BAG,rank=2,techniques=(T.SHELL,T.IMPROMPTU))
  self.restore();self.assertEqual({k for k in T.TECHNIQUES if T.technique(self.t,k)},set(T.TECHNIQUES))
  self.assertEqual(len(T.records(self.t,T.BAG,True)),2);self.valid()

 def test_base_dirty_trick_is_pokemon_free_automatic_accuracy_with_real_opposed_roll(self):
  self.acquire();row=self.use('move/애교부리기');before=AP.available(self.t)
  with patch.object(self.e,'accuracy_check',side_effect=AssertionError('automatic accuracy has no roll')):
   result=self.e.trickster_maneuver(self.t,self.p,self.foe,row['id'],'dirty_trick','hinder',
    challenger_options={'fixed':[6,6]},defender_options={'fixed':[1,1]})
  self.assertTrue(result);self.assertIn('둔화',self.foe.conditions)
  self.assertEqual(AP.available(self.t),before-1);self.assertEqual(self.p.budget['standard'],0)
  self.assertEqual(self.p.kind,'pokemon');self.valid()

 def test_base_manipulate_rolls_trainer_guile_but_pokemon_executes(self):
  self.acquire();row=self.use('move/애교부리기');before=AP.available(self.t)
  with patch.object(self.e,'opposed_check',wraps=self.e.opposed_check) as opposed:
   self.assertTrue(self.e.trickster_maneuver(self.t,self.p,self.foe,row['id'],'manipulate','terrorize',
    defender_skill='집중',challenger_options={'fixed':[6]*6},defender_options={'fixed':[1,1]}))
  args=opposed.call_args.args;self.assertIs(args[0],self.t);self.assertEqual(args[1],'교활')
  self.assertIs(opposed.call_args.kwargs['defender_options']['skill_target'],self.t)
  record=next(r for r in TIME.records(self.foe) if r.get('manipulation')=='terrorize')
  self.assertIs(record['attacker'],self.p);self.assertEqual(self.p.kind,'pokemon')
  self.assertEqual(AP.available(self.t),before-1);self.valid()

 def test_base_rejects_miss_wrong_foe_other_owner_and_stale_trigger(self):
  self.acquire();row=self.use('move/애교부리기',face=1)
  self.reject(lambda:self.e.trickster_maneuver(self.t,self.p,self.foe,row['id'],'dirty_trick','blind'),'completed hit')
  row=self.use('move/울음소리')
  self.reject(lambda:self.e.trickster_maneuver(self.t,self.q,self.foe,row['id'],'dirty_trick','blind'),'completed whole Move')
  ACTION.triggered_free_action(self.e,self.t,'homebrew/other-action')
  self.reject(lambda:self.e.trickster_maneuver(self.t,self.p,self.foe,row['id'],'dirty_trick','blind'),'immediate')

 def test_base_real_hazard_entry_on_foe_can_trigger_manipulate(self):
  self.acquire();self.use('move/압정뿌리기',target=self.p,aim=CELLS8)
  self.assertEqual(len(self.hazards()),8)
  self.begin(self.foe);self.e.approach(self.foe,self.t)
  self.assertIn(self.foe.pos,CELLS8)
  token=self.e._trickster_trigger;self.assertTrue(token.startswith('trickster-hazard:'))
  self.assertTrue(self.e.trickster_maneuver(self.t,self.p,self.foe,token,'manipulate','terrorize',
   defender_skill='집중',challenger_options={'fixed':[6]*6},defender_options={'fixed':[1,1]}))
  self.reject(lambda:self.e.trickster_maneuver(self.t,self.p,self.foe,token,'manipulate','bon_mot',
   defender_skill='집중',challenger_options={'fixed':[6]*6},defender_options={'fixed':[1,1]}),'already consumed')

 def test_base_each_actual_hazard_owner_in_same_entry_retains_its_immediate_trigger(self):
  self.acquire();self.use('move/압정뿌리기',target=self.p,aim=CELLS8)
  self.use('move/압정뿌리기',actor=self.q,target=self.q,aim=CELLS8)
  self.begin(self.foe);self.e.approach(self.foe,self.t)
  self.assertIn(self.foe.pos,CELLS8);tokens=self.e._trickster_trigger
  self.assertIsInstance(tokens,tuple);self.assertEqual(len(tokens),2)
  for actor,choice in ((self.p,'terrorize'),(self.q,'bon_mot')):
   token=next(uid for uid in tokens if uid in actor.custom_conditions['_trickster_hazard_events'])
   self.assertTrue(self.e.trickster_maneuver(self.t,actor,self.foe,token,'manipulate',choice,
    defender_skill='집중',challenger_options={'fixed':[6]*6},defender_options={'fixed':[1,1]}))
  self.valid()

 def test_stacked_burn_only_adds_five_on_actual_selected_condition_hp_loss(self):
  self.family();self.source_condition('화상');row=self.use('move/애교부리기')
  self.e.stacked_deck(self.t,self.p,self.foe,row['id'],'화상')
  before=self.foe.hp;self.e.lose_hp(self.foe,2,source='독');self.assertEqual(self.foe.hp,before-2)
  before=self.foe.hp;self.e.lose_tick_hp(self.foe,1,source='화상');self.assertEqual(self.foe.hp,before-self.e.tick(self.foe)-5)
  self.e.cure_status(self.foe,'화상');before=self.foe.hp
  self.e.lose_tick_hp(self.foe,1,source='화상');self.assertEqual(self.foe.hp,before-self.e.tick(self.foe))
  self.valid()

 def test_stacked_seeded_uses_actual_linked_move_turn_tick(self):
  self.family();self.use('move/씨뿌리기');row=self.use('move/애교부리기')
  self.e.stacked_deck(self.t,self.p,self.foe,row['id'],'씨뿌리기')
  self.e.gm.set_hp(self.p,self.p.hp-20,reason='actual missing caster HP to observe only native seed drain healing')
  caster_before=self.p.hp
  self.close();before=self.foe.hp
  self.e.start_of_turn(self.foe,initiative_count=40)
  self.assertEqual(self.foe.hp,before-self.e.tick(self.foe)-5)
  drain=CONDITIONS.records(self.foe,'씨뿌리기')[0]['applications'][-1]
  self.assertLessEqual(drain['lost'],drain['requested'])
  self.assertEqual(self.p.hp,min(self.p.max_hp,caster_before+drain['lost']))
  self.assertTrue(CONDITIONS.records(self.foe,'씨뿌리기'));self.valid()

 def test_stacked_poison_curse_and_bad_dreams_use_native_condition_loss_producers(self):
  for condition in ('독','저주','악몽'):
   with self.subTest(condition=condition):
    self.setup();self.family()
    if condition=='악몽':self.source_condition('잠듦')
    self.source_condition(condition);row=self.use('move/애교부리기')
    self.e.stacked_deck(self.t,self.p,self.foe,row['id'],condition)
    before=self.foe.hp
    if condition=='악몽':
     RECOVERY.saving_check(self.e,self.foe,'잠듦',16,fixed=1)
     self.assertEqual(self.foe.hp,before-2*self.e.tick(self.foe)-5)
    else:
     self.close();before=self.foe.hp;self.e.start_of_turn(self.foe,initiative_count=40)
     with patch.object(Engine,'d20',return_value=18):self.e.use_move_on(self.foe,self.p,'struggle',self.e.everyone,set_damage=True)
     before=self.foe.hp;self.e.end_of_turn(self.foe)
     self.assertEqual(self.foe.hp,before-self.e.tick(self.foe)*(2 if condition=='저주' else 1)-5)
    self.valid()

 def test_stacked_failed_save_does_not_consume_next_success_and_success_trips_slows(self):
  self.family();row=self.use('move/저리가루')
  self.e.stacked_deck(self.t,self.p,self.foe,row['id'],'마비')
  self.assertFalse(RECOVERY.saving_check(self.e,self.foe,'마비',11,fixed=1)['passed'])
  self.assertNotIn('넘어짐',self.foe.conditions)
  self.assertFalse(self.foe.custom_conditions[T.STACK_KEY][0]['consumed'])
  self.assertTrue(RECOVERY.saving_check(self.e,self.foe,'마비',11,fixed=20)['passed'])
  self.assertTrue({'넘어짐','둔화'}<=self.foe.conditions)
  self.assertTrue(self.foe.custom_conditions[T.STACK_KEY][0]['consumed']);self.valid()

 def test_stacked_accuracy_evasion_minus_two_lasts_only_selected_volatile_condition(self):
  self.family();row=self.use('move/이상한빛');base=self.foe.evasion('특수')
  self.e.stacked_deck(self.t,self.p,self.foe,row['id'],'혼란')
  self.assertEqual(self.foe.evasion('특수'),max(0,base-2))
  effects=[r for r in TIME.records(self.foe) if r.get('trickster_condition')=='혼란']
  self.assertEqual(len(effects),1);self.assertEqual(effects[0]['accuracy_modifier'],-2)
  self.e.cure_status(self.foe,'혼란');self.assertFalse([r for r in TIME.records(self.foe) if r.get('trickster_condition')])
  self.assertEqual(self.foe.evasion('특수'),base);self.valid()

 def test_stacked_all_four_save_conditions_and_all_four_volatile_conditions(self):
  for condition in ('마비','얼음','조이기','잠듦','혼란','난동','억압','헤롱헤롱'):
   with self.subTest(condition=condition):
    self.setup();self.family();self.begin();self.source_condition(condition)
    row=self.use('move/애교부리기',begin=False);self.e.stacked_deck(self.t,self.p,self.foe,row['id'],condition)
    record=self.foe.custom_conditions[T.STACK_KEY][0]
    if condition in T.GROUPS[1]:
     self.assertEqual(record['group'],1)
     RECOVERY.saving_check(self.e,self.foe,condition,20,fixed=1)
     self.assertFalse(self.foe.custom_conditions[T.STACK_KEY][0]['consumed'])
     RECOVERY.saving_check(self.e,self.foe,condition,20,fixed=20)
     self.assertTrue({'넘어짐','둔화'}<=self.foe.conditions)
    else:
     self.assertEqual(record['group'],2)
     self.assertTrue(any(r.get('trickster_condition')==condition and r['accuracy_modifier']==-2 and r['evasion_modifier']==-2 for r in TIME.records(self.foe)))
    self.e.cure_status(self.foe,condition);self.assertNotIn(T.STACK_KEY,self.foe.custom_conditions)
    self.valid()

 def test_stacked_scene_per_foe_quota_is_not_per_condition(self):
  self.family();self.source_condition('화상');row=self.use('move/저리가루')
  self.e.stacked_deck(self.t,self.p,self.foe,row['id'],'화상')
  self.reject(lambda:self.e.stacked_deck(self.t,self.p,self.foe,row['id'],'마비'),'this foe this Scene')

 def test_stacked_once_per_foe_is_shared_across_trainers_after_cure_restore_and_next_scene(self):
  self.family();other,partner=self.other_pair();self.source_condition('화상')
  row=self.use('move/애교부리기');self.e.stacked_deck(self.t,self.p,self.foe,row['id'],'화상')
  self.e.cure_status(self.foe,'화상');self.assertNotIn(T.STACK_KEY,self.foe.custom_conditions)
  self.source_condition('독');row=self.use('move/애교부리기',actor=partner)
  self.reject(lambda:self.e.stacked_deck(other,partner,self.foe,row['id'],'독'),'this foe this Scene')
  owner_id,partner_id=other.entity_id,partner.entity_id;self.restore()
  actors=W.actor_index(self.e);other,partner=actors[owner_id],actors[partner_id]
  self.reject(lambda:self.e.stacked_deck(other,partner,self.foe,row['id'],'독'),'this foe this Scene')
  self.close();self.e.end_round();self.e.end_scene()
  row=self.use('move/애교부리기',actor=partner)
  self.e.stacked_deck(other,partner,self.foe,row['id'],'독')
  self.assertIs(self.foe.custom_conditions[T.STACK_KEY][0]['trainer'],other);self.valid()

 def test_flourish_ignores_nonstat_evasion_but_preserves_stat_evasion_and_natural_one(self):
  import double_team as DOUBLE
  self.family();move=self.rules.move('move/애교부리기')
  self.use('move/그림자분신',actor=self.foe,target=self.foe)
  DOUBLE.choose(self.e,self.foe,'evasion',reason='actual selected being-targeted Double Team use')
  self.e.gm.set_stage(self.foe,'eva',value=5,reason='actual situational nonstat evasion fixture')
  self.use('move/애교부리기',face=6)
  self.assertEqual(self.foe.stages['atk'],-2)
  self.assertEqual([r['kind'] for r in DOUBLE.records(self.foe)[0]['applications']],['evasion'])
  self.assertNotIn('double_team_choice',self.foe.spec)
  evasion=self.rules.mech('combat/evasion')
  self.assertEqual(self.foe.evasion('변화',ignore_nonstats=True),min(evasion['cap'],self.foe.staged('spe')//evasion['per_points']))
  hit,_,critical=self.e.accuracy_check(self.p,self.foe,move,fixed_roll=6)
  self.assertTrue(hit);self.assertFalse(critical)
  self.assertFalse(self.e.accuracy_check(self.p,self.foe,move,fixed_roll=1)[0])

 def test_flourish_natural_twenty_critical_and_extra_stage_lowering(self):
  self.family();row=self.use('move/거짓울음',face=20);before=self.foe.stages['spd']
  self.e.flourish(self.t,self.p,row['id'],'stage',stat='spd')
  self.assertEqual(self.foe.stages['spd'],before-1)
  self.reject(lambda:self.e.flourish(self.t,self.p,row['id'],'temporary_hp'),'already resolved')
  self.valid()

 def test_flourish_temp_hp_tick_and_no_ac_status_does_not_invent_critical_roll(self):
  self.family();row=self.use('move/애교부리기',face=20)
  self.e.flourish(self.t,self.p,row['id'],'temporary_hp')
  self.assertEqual(self.p.temp_hp,self.e.tick(self.p))
  self.learn('move/칼춤');self.begin()
  with patch.object(Engine,'d20',side_effect=AssertionError('no AC has no accuracy d20')):
   self.e.use_move_on(self.p,self.p,'move/칼춤',self.e.everyone)
  row=self.completion();self.reject(lambda:self.e.flourish(self.t,self.p,row['id'],'temporary_hp'),'natural-roll Status critical')

 def test_flourish_first_save_minus_four_consumes_actual_first_attempt_only(self):
  self.family();row=self.use('move/저리가루',face=20)
  self.e.flourish(self.t,self.p,row['id'],'first_save')
  first=RECOVERY.saving_check(self.e,self.foe,'마비',11,fixed=14)
  self.assertFalse(first['passed']);self.assertEqual(first['dc'],15)
  second=RECOVERY.saving_check(self.e,self.foe,'마비',11,fixed=14)
  self.assertTrue(second['passed']);self.assertEqual(second['dc'],11);self.valid()

 def test_flourish_uses_normal_critical_range_modifiers_not_automatic_status_critical(self):
  self.family();row=self.use('move/애교부리기',face=19)
  self.reject(lambda:self.e.flourish(self.t,self.p,row['id'],'temporary_hp'),'natural-roll Status critical')
  self.e.gm.set_ability(self.p,'대운',reason='actual native critical-range Ability fixture')
  row=self.use('move/거짓울음',face=19)
  self.e.flourish(self.t,self.p,row['id'],'temporary_hp')
  self.assertEqual(self.p.temp_hp,self.e.tick(self.p));self.valid()

 def test_flourish_all_actual_condition_recipients_each_get_first_save_penalty(self):
  self.family();self.q.side='enemy';self.q.spec['side']='enemy'
  row=self.use('move/흔들흔들댄스',face=20)
  self.e.flourish(self.t,self.p,row['id'],'first_save')
  for target in (self.foe,self.q):
   self.assertIn('혼란',target.conditions)
   with patch.object(Engine,'d20',return_value=19):self.begin(target)
   first=target.custom_conditions['core_confusion_turns'][-1]['save']
   self.assertEqual(first['dc'],20);self.assertFalse(first['passed'])
   self.assertEqual(RECOVERY.saving_check(self.e,target,'혼란',16,fixed=19)['dc'],16)
  self.valid()

 def test_encore_core_stat_gate_is_per_selected_stat_not_any_stat(self):
  self.family();row=self.use('move/칼춤',target=self.p)
  self.e.encore_performance(self.t,self.p,row['id'],'stage',stat='def')
  self.assertEqual(self.p.stages['atk'],2);self.assertEqual(self.p.stages['def'],1)
  self.valid()

 def test_encore_kr_and_csv_keep_global_no_stat_rise_wording(self):
  for source in ('kr','csv'):
   with self.subTest(source=source):
    self.setup();self.family(source=source);row=self.use('move/칼춤',target=self.p)
    self.reject(lambda:self.e.encore_performance(self.t,self.p,row['id'],'stage',stat='def'),'already rose')

 def test_encore_second_standard_is_at_will_only_not_full_turn_and_cannot_recurse(self):
  self.family();row=self.use('move/칼춤',target=self.p)
  self.e.encore_performance(self.t,self.p,row['id'],'standard')
  before=dict(self.p.budget);self.learn('move/도발')
  self.reject(lambda:self.e.use_move_on(self.p,self.foe,'move/도발',self.e.everyone),'At-Will only')
  self.assertEqual(self.p.budget,before)
  row=self.use('move/단단해지기',target=self.p,begin=False)
  self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.p.budget['shift'],before['shift'])
  self.assertTrue(row['trickster_encore_action'])
  self.reject(lambda:self.e.encore_performance(self.t,self.p,row['id'],'stage',stat='def'),'cannot trigger itself')
  ordinary=self.use('move/울음소리')
  self.assertFalse(ordinary['trickster_encore_action'])
  self.assertNotIn('_trickster_encore_pending',self.p.custom_conditions)
  self.valid()

 def test_encore_hazard_adds_two_real_units_weather_two_rounds_blessing_same_pool_one(self):
  for choice,move in [('hazard','move/압정뿌리기'),('weather','move/비바라기'),('blessing','move/빛의장막')]:
   with self.subTest(choice=choice):
    self.setup();self.family();row=self.use(move,target=self.p,aim=CELLS8 if choice=='hazard' else None)
    before={r['id'] for r in self.hazards()} if choice=='hazard' else self.e.weather_rounds if choice=='weather' else B.live(self.p)[0]['id']
    self.e.encore_performance(self.t,self.p,row['id'],choice,cells=((5,3),(6,3)) if choice=='hazard' else None)
    if choice=='hazard':self.assertEqual(len(self.hazards()),10);self.assertTrue(before<={r['id'] for r in self.hazards()})
    elif choice=='weather':self.assertEqual(self.e.weather_rounds,before+2)
    else:self.assertEqual(B.live(self.p)[0]['id'],before);self.assertEqual(B.remaining(B.live(self.p)[0]),3)
    self.restore();self.valid()

 def test_encore_second_standard_field_move_keeps_real_empty_completion_and_cannot_recurse(self):
  self.family();row=self.use('move/압정뿌리기',target=self.p,aim=CELLS8)
  self.e.encore_performance(self.t,self.p,row['id'],'standard')
  row=self.use('move/압정뿌리기',target=self.p,aim=CELLS8,begin=False)
  self.assertEqual(row['targets'],[]);self.assertTrue(row['trickster_encore_action'])
  self.reject(lambda:self.e.encore_performance(self.t,self.p,row['id'],'hazard',cells=((5,3),(6,3))),'cannot trigger itself')
  self.valid()

 def test_encore_daily_three_across_real_status_moves_and_no_enemy_target(self):
  self.family()
  for _ in range(3):
   row=self.use('move/압정뿌리기',target=self.p,aim=CELLS8)
   self.e.encore_performance(self.t,self.p,row['id'],'standard')
  row=self.use('move/비바라기',target=self.p)
  self.reject(lambda:self.e.encore_performance(self.t,self.p,row['id'],'weather'),'frequency exhausted')
  row=self.use('move/애교부리기')
  self.reject(lambda:self.e.encore_performance(self.t,self.p,row['id'],'stage',stat='def'),'not targeting foes')

 def test_encore_blessing_extension_preserves_shared_pool_through_actual_uses(self):
  self.family();row=self.use('move/빛의장막',target=self.p)
  self.e.encore_performance(self.t,self.p,row['id'],'blessing')
  identity=B.live(self.p)[0]['id']
  self.e.rulings.add_answer('team_blessing',True,reason='actual player spends shared Blessing use')
  for target,left in ((self.p,2),(self.q,1)):
   self.use('move/물대포',actor=self.foe,target=target)
   record=B.live(self.p)[0];self.assertEqual(record['id'],identity);self.assertEqual(B.remaining(record),left)
  self.restore();record=B.live(self.p)[0]
  self.assertEqual(record['id'],identity);self.assertEqual(B.remaining(record),1);self.valid()

 def test_mind_games_actual_social_hit_full_round_and_real_pokemon_infatuation(self):
  self.family();self.source_condition('혼란');row=self.use('move/애교부리기')
  self.e.mind_games(self.t,self.p,self.foe,row['id'],replace='혼란',with_condition='헤롱헤롱')
  self.assertNotIn('혼란',self.foe.conditions);self.assertIn('헤롱헤롱',self.foe.conditions)
  self.assertEqual(CONDITIONS.beloved(self.foe),[self.p]);self.assertEqual(self.p.kind,'pokemon')
  self.close();self.e.end_round();self.assertIn('취약',self.foe.conditions)
  self.e.start_round(self.e.everyone);TIME.at_count(self.e,61);self.assertIn('취약',self.foe.conditions)
  TIME.at_count(self.e,60);self.assertNotIn('취약',self.foe.conditions);self.valid()

 def test_mind_games_requires_social_and_scene_per_target_and_two_total(self):
  self.family();row=self.use('move/저리가루')
  self.reject(lambda:self.e.mind_games(self.t,self.p,self.foe,row['id']),'Social Move hit')
  row=self.use('move/애교부리기');self.e.mind_games(self.t,self.p,self.foe,row['id'])
  self.reject(lambda:self.e.mind_games(self.t,self.p,self.foe,row['id']),'this foe this Scene')
  self.q.side='enemy';self.q.spec['side']='enemy'
  third=self.ps[2];third.side='enemy';third.spec['side']='enemy'
  self.e.gm.set_position(third,(4,3),reason='actual third distinct foe for Scene x2')
  self.use('move/단단해지기',target=self.p)
  row=self.use('move/애교부리기',target=self.q);self.e.mind_games(self.t,self.p,self.q,row['id'])
  self.use('move/단단해지기',target=self.p);row=self.use('move/애교부리기',target=third)
  self.reject(lambda:self.e.mind_games(self.t,self.p,third,row['id']),'frequency exhausted')

 def test_mind_once_per_foe_survives_expiry_other_trainer_and_restore_then_next_scene(self):
  self.family();other,partner=self.other_pair();row=self.use('move/애교부리기')
  self.e.mind_games(self.t,self.p,self.foe,row['id'])
  self.close();self.e.end_round();self.e.start_round(self.e.everyone);TIME.at_count(self.e,60)
  self.assertNotIn('취약',self.foe.conditions)
  row=self.use('move/애교부리기',actor=partner)
  self.reject(lambda:self.e.mind_games(other,partner,self.foe,row['id']),'this foe this Scene')
  self.assertNotIn(T.MIND,other.spec.get('frequency_state',{}).get('activations',{}))
  owner_id,partner_id=other.entity_id,partner.entity_id;self.restore()
  actors=W.actor_index(self.e);other,partner=actors[owner_id],actors[partner_id]
  self.reject(lambda:self.e.mind_games(other,partner,self.foe,row['id']),'this foe this Scene')
  self.close();self.e.end_round();self.e.end_scene();row=self.use('move/애교부리기',actor=partner)
  self.e.mind_games(other,partner,self.foe,row['id']);self.assertIn('취약',self.foe.conditions);self.valid()

 def test_escape_artist_actual_status_move_no_aoo_then_free_one_metre_disengage(self):
  self.family();self.learn('move/애교부리기');self.begin();before=AP.available(self.t)
  with patch.object(Engine,'d20',return_value=18):
   self.e.escape_artist(self.t,self.p,self.foe,'move/애교부리기',(2,3))
  self.assertEqual(self.p.pos,(2,3));self.assertEqual(self.p.budget['standard'],0)
  self.assertEqual(self.p.budget['shift'],1);self.assertFalse(self.foe.aoo_used)
  self.assertEqual(AP.available(self.t),before-1);self.assertEqual(self.completion()['move_id'],'move/애교부리기')
  self.valid()

 def test_escape_invalid_destination_and_nonstatus_do_not_pay_ap_or_use_move(self):
  self.family();self.learn('move/애교부리기');self.begin()
  self.reject(lambda:self.e.escape_artist(self.t,self.p,self.foe,'move/애교부리기',(10,10)),'one|1|Disengage|disengage')
  self.learn('move/물대포')
  self.reject(lambda:self.e.escape_artist(self.t,self.p,self.foe,'move/물대포',(2,3)),'adjacent foe targeted by a Status')

 def test_escape_once_per_pokemon_survives_actual_owner_transfer_but_other_pokemon_and_next_scene_work(self):
  import pokemon_party as PARTY
  self.family();other,partner=self.other_pair()
  PARTY.configure(self.e,self.t,mode='unlimited',reason='actual original complete roster',roster=self.ps)
  PARTY.configure(self.e,other,mode='unlimited',reason='actual independent roster',roster=[partner])
  self.learn('move/애교부리기');self.begin()
  with patch.object(Engine,'d20',return_value=18):self.e.escape_artist(self.t,self.p,self.foe,'move/애교부리기',(2,3))
  self.close();self.e.end_round();self.e.end_encounter()
  PARTY.transfer(self.e,self.t,target=self.p,new_owner=other,reason='actual ownership transfer in same Scene',request_id='escape-transfer')
  self.e.gm.send_out(self.p,pos=(3,2),reason='actual new owner fields transferred Pokemon')
  self.e.gm.observe_loyalty(self.p,3,reason='actual new owner willing relationship')
  self.begin()
  self.reject(lambda:self.e.escape_artist(other,self.p,self.foe,'move/애교부리기',(2,3)),'this Pokemon this Scene')
  self.learn('move/애교부리기',partner);self.begin(partner)
  with patch.object(Engine,'d20',return_value=18):self.e.escape_artist(other,partner,self.foe,'move/애교부리기',(2,0))
  owner_id=other.entity_id;self.restore();other=W.actor_index(self.e)[owner_id]
  self.begin();self.reject(lambda:self.e.escape_artist(other,self.p,self.foe,'move/애교부리기',(2,3)),'this Pokemon this Scene')
  self.close();self.e.end_round();self.e.end_scene();self.begin()
  with patch.object(Engine,'d20',return_value=18):self.e.escape_artist(other,self.p,self.foe,'move/애교부리기',(2,3))
  self.assertEqual(self.p.pos,(2,3));self.assertEqual(self.p.spec['trainer_id'],other.entity_id);self.valid()

 def test_shell_core_standalone_standard_moves_all_allied_ids_noncontiguously(self):
  self.family();self.use('move/압정뿌리기',target=self.p,aim=CELLS8)
  original={r['id']:deepcopy(r) for r in self.hazards()};self.begin(self.t)
  destinations={uid:(r['cell'][0]+(2 if i%2 else -1),r['cell'][1]+2) for i,(uid,r) in enumerate(original.items())}
  self.e.shell_game(self.t,self.p,'spikes',destinations)
  self.assertEqual(self.t.budget['standard'],0)
  after={r['id']:r for r in self.hazards()};self.assertEqual(set(after),set(original))
  for uid,row in after.items():
   self.assertEqual(row['cell'],destinations[uid]);self.assertEqual({k:v for k,v in row.items() if k!='cell'},{k:v for k,v in original[uid].items() if k!='cell'})
  self.restore();self.valid()

 def test_shell_placement_free_limit_distance_all_instances_and_csv_adjacency_distinction(self):
  self.family();row=self.use('move/압정뿌리기',target=self.p,aim=CELLS8)
  original=self.hazards();destinations={r['id']:(r['cell'][0],r['cell'][1]+1) for r in original}
  self.reject(lambda:self.e.shell_game(self.t,self.p,'spikes',{original[0]['id']:(3,4)},placement=row['id']),'all allied instances')
  far={r['id']:(r['cell'][0]+4,r['cell'][1]) for r in original}
  self.reject(lambda:self.e.shell_game(self.t,self.p,'spikes',far,placement=row['id']),'half the Trainer Guile')
  self.e.shell_game(self.t,self.p,'spikes',destinations,placement=row['id'])
  self.assertFalse(getattr(self.t,'budget',{}).get('standard',0)==0 and 'standard' in self.t._action_history)
  self.setup();self.acquire();self.acquire(T.BAG,rank=1,techniques=(T.SHELL,T.MIND),origins={T.SHELL:T.CSV[T.SHELL]})
  row=self.use('move/압정뿌리기',target=self.p,aim=CELLS8);destinations={r['id']:r['cell'] for r in self.hazards()}
  self.reject(lambda:self.e.shell_game(self.t,self.p,'spikes',destinations,placement=row['id']),'nonadjacent')
  self.reject(lambda:self.e.shell_game(self.t,self.p,'spikes',destinations),'printed placement trigger')

 def test_encore_and_shell_preserve_independent_slow_at_original_extra_and_destination_cells(self):
  self.family();baseline={(3,1),(5,3),(6,5)}
  for cell in baseline:self.e.gm.set_terrain(cell,'slow',reason='independent mapped difficult terrain')
  row=self.use('move/압정뿌리기',target=self.p,aim=CELLS8)
  self.e.encore_performance(self.t,self.p,row['id'],'hazard',cells=((5,3),(6,3)))
  destinations={r['id']:(r['cell'][0]+1,r['cell'][1]+2) for r in self.hazards()}
  self.begin(self.t);self.e.shell_game(self.t,self.p,'spikes',destinations)
  self.restore();self.e.end_encounter(self.e.everyone)
  self.assertFalse(self.e.hazards);self.assertEqual(self.e.grid.slow,baseline);self.valid()

 def test_csv157_158_159_are_actual_selected_acquisitions_with_native_effects(self):
  for feature,move,choice in ((T.STACK,'move/애교부리기','화상'),(T.FLOURISH,'move/애교부리기','temporary_hp'),(T.ENCORE,'move/비바라기','weather')):
   with self.subTest(feature=feature):
    self.setup();self.family(source='csv');self.assertEqual(T.source(self.t,feature),T.CSV[feature])
    if feature==T.STACK:self.source_condition('화상')
    row=self.use(move,face=20,target=self.p if feature==T.ENCORE else self.foe)
    if feature==T.STACK:
     self.e.stacked_deck(self.t,self.p,self.foe,row['id'],choice);before=self.foe.hp
     self.e.lose_tick_hp(self.foe,1,source='화상');self.assertEqual(self.foe.hp,before-self.e.tick(self.foe)-5)
    elif feature==T.FLOURISH:
     self.e.flourish(self.t,self.p,row['id'],choice);self.assertEqual(self.p.temp_hp,self.e.tick(self.p))
    else:
     before=self.e.weather_rounds;self.e.encore_performance(self.t,self.p,row['id'],choice)
     self.assertEqual(self.e.weather_rounds,before+2)
    self.restore();self.valid()

 def test_csv21_and22_techniques_use_actual_source_choices_and_native_consumers(self):
  self.acquire();self.acquire(T.BAG,rank=1,techniques=(T.MIND,T.ESCAPE),origins={T.MIND:T.CSV[T.MIND],T.ESCAPE:T.CSV[T.ESCAPE]})
  row=self.use('move/애교부리기');self.e.mind_games(self.t,self.p,self.foe,row['id'])
  self.assertEqual(T.technique(self.t,T.MIND)['source'],T.CSV[T.MIND]);self.assertIn('취약',self.foe.conditions)
  self.learn('move/애교부리기',self.q);self.begin(self.q)
  with patch.object(Engine,'d20',return_value=18):self.e.escape_artist(self.t,self.q,self.foe,'move/애교부리기',(2,3))
  self.assertEqual(T.technique(self.t,T.ESCAPE)['source'],T.CSV[T.ESCAPE]);self.assertEqual(self.q.pos,(2,3));self.valid()

 def test_csv23_shell_positive_nonadjacent_positions_preserve_all_physical_ids(self):
  self.acquire();self.acquire(T.BAG,rank=1,techniques=(T.SHELL,T.MIND),origins={T.SHELL:T.CSV[T.SHELL]})
  row=self.use('move/압정뿌리기',target=self.p,aim=CELLS8)
  mapping=dict(zip(CELLS8,((1,0),(3,0),(5,0),(1,2),(5,2),(1,4),(3,4),(5,4))))
  before={r['id'] for r in self.hazards()};destinations={r['id']:mapping[r['cell']] for r in self.hazards()}
  self.e.shell_game(self.t,self.p,'spikes',destinations,placement=row['id'])
  self.assertEqual({r['id'] for r in self.hazards()},before)
  self.assertEqual({r['cell'] for r in self.hazards()},set(mapping.values()));self.restore();self.valid()

 def scheduled(self):
  self.close()
  if self.e.round_start_seconds is not None:self.e.end_round()
  for actor,speed in zip([self.t,*self.ps,self.foe],[60,50,40,30,20,10]):
   self.e.gm.set_stat(actor,'spe',value=speed,reason='actual distinct initiative fixture')
  self.e.prepare_initiative_schedule(self.e.everyone,source='gm/actual-trickster-initiative')
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t)
  return {'kind':'turn','actor_id':self.t.entity_id,'serial':self.t.custom_conditions['combat_turn_serial'],'round':self.e.round_no}

 def test_sleight_uses_actual_borrowed_pokemon_turn_and_preserves_trainer_turn(self):
  self.family();self.learn('move/저리가루');trigger=self.scheduled()
  trainer_budget=dict(self.t.budget)
  with patch.object(Engine,'d20',return_value=18):
   result=self.e.sleight(self.t,self.p,move_id='move/저리가루',target=self.foe,trigger=trigger)
  self.assertEqual(result['status'],'applied');self.assertIn('마비',self.foe.conditions)
  self.assertIs(self.e._active_turn_actor,self.t);self.assertEqual(self.t.budget,trainer_budget)
  self.assertEqual(self.p.kind,'pokemon');self.assertEqual(self.completion()['move_id'],'move/저리가루')
  self.assertTrue(self.e._initiative_interrupts['loans']);self.restore();self.valid()

 def test_sleight_bypasses_real_substitute_for_only_its_status_move(self):
  self.family();self.use('move/대타출동',actor=self.foe,target=self.foe)
  coat=SUBSTITUTE.live(self.foe)[0];coat_id=coat['id'];hp=coat['hp']
  self.use('move/최면술');self.assertNotIn('잠듦',self.foe.conditions)
  self.learn('move/저리가루')
  trigger=self.scheduled()
  with patch.object(Engine,'d20',return_value=18):
   self.e.sleight(self.t,self.p,move_id='move/저리가루',target=self.foe,trigger=trigger)
  self.assertIn('마비',self.foe.conditions);self.assertEqual(SUBSTITUTE.live(self.foe)[0]['id'],coat_id)
  self.assertEqual(SUBSTITUTE.live(self.foe)[0]['hp'],hp);self.assertFalse(hasattr(self.e,'_trickster_sleight'))

 def test_sleight_blessing_uses_native_creator_completion_and_borrowed_standard(self):
  self.family();self.learn('move/빛의장막');trigger=self.scheduled()
  budget=dict(self.t.budget);self.assertFalse(hasattr(self.p,'budget'))
  with patch.object(Engine,'d20',side_effect=AssertionError('Blessing has no accuracy roll')):
   result=self.e.sleight(self.t,self.p,move_id='move/빛의장막',target=self.p,trigger=trigger)
  self.assertEqual(self.completion()['move_id'],'move/빛의장막')
  receipt=self.e._initiative_interrupts['windows'][result['window']]['requests'][0]['receipt']
  self.assertEqual(self.completion()['phase'],'complete');self.assertEqual(receipt['remaining_budget']['standard'],0)
  self.assertTrue(hasattr(self.p,'budget'));self.assertIsNone(self.p.budget)
  self.assertEqual(B.live(self.p)[0]['effect_instance']['applied_by_actor_id'],self.p.entity_id)
  self.assertEqual(self.t.budget,budget);self.restore();self.valid()

 def test_sleight_ignores_actual_printed_defensive_ability_without_erasing_it(self):
  self.setup(abilities=('불면',));self.family();self.learn('move/최면술')
  self.use('move/최면술');self.assertNotIn('잠듦',self.foe.conditions)
  self.learn('move/수면가루')
  trigger=self.scheduled()
  with patch.object(Engine,'d20',return_value=18):
   self.e.sleight(self.t,self.p,move_id='move/수면가루',target=self.foe,trigger=trigger)
  self.assertIn('잠듦',self.foe.conditions);self.assertIn('불면',self.foe.abilities)
  self.e.cure_status(self.foe,'잠듦');self.assertTrue(self.e.immune_to(self.foe,'잠듦'));self.valid()

 def test_sleight_defensive_stage_immunity_and_nonability_immunity_stay_distinct(self):
  self.setup(abilities=('부풀린가슴',));self.family();self.learn('move/꼬리흔들기')
  self.use('move/꼬리흔들기');self.assertEqual(self.foe.stages['def'],0)
  trigger=self.scheduled()
  with patch.object(Engine,'d20',return_value=18):
   self.e.sleight(self.t,self.p,move_id='move/꼬리흔들기',target=self.foe,trigger=trigger)
  self.assertEqual(self.foe.stages['def'],-1);self.assertIn('부풀린가슴',self.foe.abilities);self.valid()

 def test_sleight_blessing_exception_does_not_spend_or_remove_enemy_mist_pool(self):
  self.family();self.use('move/흰안개',actor=self.foe,target=self.foe)
  pool=B.live(self.foe)[0];identity=pool['id'];remaining=B.remaining(pool)
  self.learn('move/꼬리흔들기');trigger=self.scheduled()
  self.e.rulings.add_answer('team_blessing',True,reason='actual opponent would answer with Mist')
  with patch.object(Engine,'d20',return_value=18):
   self.e.sleight(self.t,self.p,move_id='move/꼬리흔들기',target=self.foe,trigger=trigger)
  self.assertEqual(self.foe.stages['def'],-1);pool=B.live(self.foe)[0]
  self.assertEqual(pool['id'],identity);self.assertEqual(B.remaining(pool),remaining);self.valid()

 def test_sleight_preserves_actual_type_based_powder_immunity(self):
  self.family();self.e.gm.set_types(self.foe,['풀'],reason='actual Grass target fixture, not a Defensive Ability')
  self.learn('move/독가루');trigger=self.scheduled()
  with patch.object(Engine,'d20',return_value=18):
   self.e.sleight(self.t,self.p,move_id='move/독가루',target=self.foe,trigger=trigger)
  self.assertNotIn('독',self.foe.conditions);self.valid()

 def test_sleight_requires_learned_status_actual_boundary_and_scene_two_quota(self):
  self.family();self.learn('move/애교부리기');self.learn('move/물대포');self.begin(self.t)
  self.reject(lambda:self.e.sleight(self.t,self.p,move_id='move/물대포',target=self.foe,trigger={}),'learned Status Move')
  self.reject(lambda:self.e.sleight(self.t,self.p,move_id='move/애교부리기',target=self.foe),'actual initiative interrupt boundary')
  for actor in self.ps[:3]:self.learn('move/칼춤',actor)
  trigger=self.scheduled()
  for actor in (self.p,self.q):
   self.e.sleight(self.t,actor,move_id='move/칼춤',target=actor,trigger=trigger)
   self.assertEqual(actor.stages['atk'],2)
  third=self.ps[2]
  self.reject(lambda:self.e.sleight(self.t,third,move_id='move/칼춤',target=third,trigger=trigger),'frequency exhausted')
  self.restore();self.valid()

 def test_impromptu_replaces_actual_opportunity_attack_with_real_status_move_and_ap(self):
  self.family();self.learn('move/애교부리기');self.begin(self.foe);before=AP.available(self.t)
  self.e.rulings.provider=lambda prompt: {'move_id':'move/애교부리기'} if prompt.get('type')=='trickster_impromptu' and prompt.get('pokemon')==self.p.name else None
  with patch.object(Engine,'d20',return_value=18):TURN.trigger_aoo(self.e,self.foe,'인접 칸 밖으로 이동')
  self.assertTrue(self.p.aoo_used);self.assertEqual(AP.available(self.t),before-1)
  self.assertEqual(self.completion()['move_id'],'move/애교부리기');self.assertEqual(self.foe.stages['atk'],-2)
  before=len(self.e._move_completions);TURN.trigger_aoo(self.e,self.foe,'인접 칸 밖으로 이동')
  self.assertEqual(len(self.e._move_completions),before);self.valid()

 def test_impromptu_hazard_branch_uses_actual_field_aim_and_places_all_units(self):
  self.family();self.learn('move/압정뿌리기');self.begin(self.foe)
  self.e.rulings.provider=lambda prompt: {'move_id':'move/압정뿌리기','aim':CELLS8} if prompt.get('type')=='trickster_impromptu' and prompt.get('pokemon')==self.p.name else None
  TURN.trigger_aoo(self.e,self.foe,'인접 칸 밖으로 이동')
  self.assertEqual(len(self.hazards()),8);self.assertTrue(self.p.aoo_used)
  self.assertEqual(self.completion()['move']['_hazard_cells'],CELLS8)
  self.assertEqual(self.completion()['targets'],[]);self.valid()

 def test_impromptu_invalid_daily_status_is_rejected_without_aoo_ap_rng_mutation(self):
  self.family();self.learn('move/비바라기');self.begin(self.foe)
  with patch.object(type(self.e.rulings),'decide',autospec=True,side_effect=lambda rulings,prompt: {'move_id':'move/비바라기'} if prompt.get('type')=='trickster_impromptu' and prompt.get('pokemon')==self.p.name else None):
   self.reject(lambda:TURN.trigger_aoo(self.e,self.foe,'인접 칸 밖으로 이동'),'Hazard OR At-Will/EOT Status')
  self.assertFalse(self.p.aoo_used)

 def test_optional_immunity_query_preserves_absence_and_rejects_explicit_invalid_sets(self):
  for field,value in (('keyword_immune','Sound'),('status_immune','잠듦')):
   self.assertFalse(hasattr(self.foe,field))
   self.assertFalse(T.set_contains(self.e,self.foe,field,value))
   self.assertFalse(hasattr(self.foe,field))
   for invalid in (None,[]):
    setattr(self.foe,field,invalid)
    with self.assertRaisesRegex(ValueError,'actual immunity set'):T.set_contains(self.e,self.foe,field,value)
    self.assertIs(getattr(self.foe,field),invalid)
   delattr(self.foe,field)

 def test_source_contract_keeps_original_inventory_and_separate_candidate_totals(self):
  contract=json.loads((ROOT/'data/trickster-source-contract.json').read_text(encoding='utf-8'))
  for file,sha in contract['source_files'].items():self.assertEqual(hashlib.sha256((ROOT/file).read_bytes()).hexdigest(),sha,file)
  self.assertEqual({k:contract['original_inventory'][k] for k in ('book','csv','references')},{'book':8,'csv':11,'references':9})
  self.assertEqual(contract['original_inventory']['potential_primary'],3)
  self.assertEqual(contract['original_inventory']['potential_separate_csv'],6)
  self.assertEqual(contract['original_inventory']['dedupe_changes'],0);self.assertEqual(contract['original_inventory']['category_changes'],0)
  self.assertEqual(contract['official_playtest']['direct_named_amendments_in_retained_may2015_sep2015_feb2016'],0)


if __name__=='__main__':unittest.main()
