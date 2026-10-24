"""Whole seven-member Telepath source contracts on actual state and attacks."""
from copy import deepcopy,copy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import test_book_telekinetic_full as FIX
import telepath as TP,telepathy as T,telepathy_core as TC,state_grants as G
import trainer_feature_acquisition as ACQ,world_entities as W,combat_timing as TIME
import action_points as AP,ability_transitions as AB,perception_communicate as M
import perception_observe as O,state_codec as CODEC,body_state as BODY
from native_scenario_fixture import prepare_body

class TelepathTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 setUp=FIX.TelekineticTests.setUp
 setup=FIX.TelekineticTests.setup
 add=FIX.TelekineticTests.add
 close=FIX.TelekineticTests.close
 begin=FIX.TelekineticTests.begin
 turn=FIX.TelekineticTests.turn
 reject=FIX.TelekineticTests.reject
 valid=FIX.TelekineticTests.valid
 restore=FIX.TelekineticTests.restore
 completion=FIX.TelekineticTests.completion
 def acquire(self,u=TP.CLASS,*,actor=None,selection=None):
  a=actor or self.a
  return ACQ.acquire_static(self.e,a,u,selection=selection,acquisition_request_id=a.entity_id+'/'+u)
 def family(self,u,*,selection=TP.CORE,actor=None):
  a=actor or self.a
  for p in TP.PARENTS[u]:
   if not TP.acquired(a,p):self.family(p,selection=selection,actor=a)
  if not TP.acquired(a,u):self.acquire(u,actor=a,selection=selection if u==TP.AWARE else None)
 def capable(self):
  self.family(TP.CLASS);self.begin();self.e.activate_telepath(self.a)
 def grant(self,a,cap='Mindlock'):G.grant(a,'capabilities',cap,'fixture:'+cap,'fixture')
 def know(self,a,mid):self.e.gm.set_move(a,mid,reason='actual learned reference Move')
 def mindread(self,policy='core_1.05'):
  self.family(TP.HONED);self.begin()
  with patch.object(Engine,'d20',return_value=18):self.e.use_mind_reader(self.a,self.b,source_policy=policy)
  return TP.live(self.b,'read')[-1]
 def allow(self,recipient,*,aware=True,willing=True):
  M.permission(self.e,recipient,self.a,TP.CLASS,willing,reason='observed recipient consent')
  TC.awareness(self.e,self.a,recipient,aware,reason='observed actual awareness')
 def fixed(self,win=True):return {'sender':{'fixed':[6 if win else 1]*6},'recipient':{'fixed':[1 if win else 6]*6}}
 def core_read(self,uid,**kw):return self.e.read_telepathic_thought(self.a,self.b,source_policy='core_1.05',request_id=uid,**kw)
 def target_party(self):
  self.e.gm.add_combatant(self.b,side='party',reason='actual ally being caught in own side area attack')
 def attack(self,mid='move/파도타기',*,aim=None,face=18):
  if mid=='move/파도타기':self.e.gm.set_position(self.c,(3,2),reason='observed original horizontal line origin')
  self.know(self.c,mid);self.begin(self.c)
  with patch.object(Engine,'d20',return_value=face):self.e.use_move_on(self.c,self.b,mid,[self.b],aim=aim,set_damage=True)
  row=self.completion(self.c,mid);self.assertEqual(row['phase'],'complete');return row
 def arm(self,source=TP.WARNING,path=None):
  self.e.arm_telepath_reaction(self.a,source,paths={self.b.entity_id:path})
 def retrain(self,u):
  import trainer_retraining as R
  owned=R._owned(self.a);sources={v:R.owned_source(self.e,self.a,v) for v in owned};required=R._native_dependencies(self.e,self.a,owned)
  deps={sid:[sources[p] for p in required.get(v,[])] for v,sid in sources.items() if v!=u}
  return self.e.retrain_trainer_source(self.a,u,request_id='retire:'+u,reason='actual retraining consultation',gm_decision={'allowed':True,'reason':'approved'},retained_dependencies=deps)

 def test_seven_independent_acquisitions_spdef_no_siblings_exact_pairs_restore(self):
  before=self.a.stats['spd'];self.acquire();self.assertEqual(len(TP.records(self.a,active=True)),1);self.assertEqual(self.a.stats['spd'],before+1);self.assertFalse(T.owns(self.a));self.assertNotIn(TP.READER,self.a.moves)
  for u in TP.FEATURES:self.family(u)
  self.assertEqual(len(TP.records(self.a,active=True)),7);self.assertEqual(self.a.stats['spd'],before+7);self.assertTrue({TP.READER,'move/명상',TP.PSYSHOCK,'move/신통력'}<=set(self.a.moves));self.assertTrue(AB.active(self.a,TP.CORE));self.assertNotIn(TP.FEB,AB.project_components(self.a))
  __import__('items').register_feats(self.e,self.a);self.assertEqual(self.a.stats['spd'],before+7);self.restore();self.valid()

 def test_prerequisites_actual_edges_parents_rank_or_choice_and_not_ranked(self):
  self.a.spec['edge_choices']={'edge/원소-교감':'불꽃'};self.reject(lambda:self.acquire(),'Connection|Iron Mind')
  self.setup(rank=3);self.reject(lambda:self.acquire(TP.HONED),'parent');self.family(TP.AWARE);self.reject(lambda:self.acquire(TP.WARNING),'rank');self.reject(lambda:self.acquire(TP.ASSAULT),'rank')
  self.setup(rank=5);self.family(TP.HONED);self.reject(lambda:self.acquire(TP.SUGGEST),'rank');self.a.spec['skills']['직감']=6;self.acquire(TP.SUGGEST)
  self.reject(lambda:ACQ.acquire_static(self.e,self.a,TP.CLASS,rank=1,acquisition_request_id='fake-ranked'),'Ranked|rank')
  self.reject(lambda:self.e.activate_telepath(copy(self.a)),'actual')

 def test_awareness_three_real_choices_immutable_and_core_rejects_playtest(self):
  self.acquire();self.reject(lambda:self.acquire(TP.AWARE),'choose');self.reject(lambda:self.acquire(TP.AWARE,selection=TP.FEB),'selected|source|not allowed|[Ee]xcluded|ruleset')
  for choice in (TP.GENTLE,TP.CORE,TP.FEB):
   with self.subTest(choice=choice):
    if choice==TP.FEB:self.rules=Rules(ROOT,ruleset='all')
    self.setup();self.acquire();self.acquire(TP.AWARE,selection=choice);self.assertTrue(AB.active(self.a,choice));self.assertEqual(self.a.spec['feature_choices'][TP.AWARE],[choice]);self.reject(lambda:self.acquire(TP.AWARE,selection=TP.GENTLE if choice!=TP.GENTLE else TP.CORE),'selection|intent');self.restore();self.valid()

 def test_class_two_ap_swift_scene_capability_and_independent_baseline(self):
  self.acquire();self.assertFalse(T.owns(self.a));self.begin();before=AP.available(self.a);self.e.activate_telepath(self.a);self.assertEqual(AP.available(self.a),before-2);self.assertEqual(self.a.budget['swift'],0);self.assertTrue(T.owns(self.a));self.restore();self.valid();self.close();self.e.end_scene();self.assertFalse(T.owns(self.a));self.grant(self.a,'Telepathy');self.begin();self.e.activate_telepath(self.a);self.close();self.e.end_scene();self.assertTrue(T.owns(self.a));self.valid()

 def test_detection_current_capability_focus_range_count_living_fainted_mindlock(self):
  self.family(TP.DETECT);self.begin();self.reject(lambda:self.e.thought_detection(self.a),'current Telepathy');self.e.activate_telepath(self.a)
  self.e.gm.set_position(self.b,(20,2),reason='exact Focus six times three boundary');self.grant(self.c);self.e.gm.set_hp(self.b,0,reason='fainted living mind remains countable');self.assertTrue(self.b.fainted);self.assertFalse(self.b.dead)
  out=self.e.thought_detection(self.a);self.assertEqual(out['count'],2);self.assertEqual(set(out),{'source','observer_id','count','at'});self.assertEqual(self.a.budget['standard'],0)
  self.begin();self.reject(lambda:self.e.thought_detection(self.a),'frequency');self.close();self.e.end_scene();self.begin();self.e.activate_telepath(self.a);self.e.gm.set_position(self.b,(21,2),reason='outside exact radius');self.assertEqual(self.e.thought_detection(self.a)['count'],1);self.restore();self.valid()

 def test_detection_unknown_geometry_refuses_without_cost_and_dead_is_excluded(self):
  self.family(TP.DETECT);self.capable();self.b.location={'kind':'unknown'};self.reject(lambda:self.e.thought_detection(self.a),'actual distance');self.b.pos=(6,2);self.e.gm.set_hp(self.b,0,reason='actual body has no HP');self.b.dead=True;self.assertEqual(self.e.thought_detection(self.a)['count'],2)

 def test_suggestion_actual_instance_bind_standard_noncompelling_restore_scene_and_exact_release(self):
  self.family(TP.SUGGEST);self.capable();ap=AP.available(self.a);row=self.e.suggestion(self.a,self.b,'The west door might be interesting.');self.assertFalse(row['effect']['compels_action']);self.assertFalse(row['effect']['creates_memories']);self.assertEqual(self.a.ap_account.identified_bindings(),{row['id']:1});self.assertEqual(AP.available(self.a),ap-1);self.assertEqual(self.a.budget['standard'],0);self.assertEqual(len(TP.live(self.b,'psychic_residue')),1)
  self.restore();self.valid();self.close();self.e.end_scene();self.assertFalse(T.owns(self.a));self.assertTrue(TP.live(self.b,'suggestion'));self.begin(self.c);self.reject(lambda:self.e.release_suggestion(self.a,row['id']),'own open turn');self.begin();self.reject(lambda:self.e.release_suggestion(self.a,'not-produced'),'exact live');self.e.release_suggestion(self.a,row['id']);self.assertFalse(TP.live(self.b,'suggestion'));self.assertFalse(self.a.ap_account.identified_bindings());self.assertTrue(TP.live(self.b,'psychic_residue'));self.restore();self.valid()

 def test_suggestion_no_invented_range_resistance_or_simultaneous_limit(self):
  self.family(TP.SUGGEST);self.capable();self.e.gm.set_position(self.b,(30,20),reason='source has no printed range');one=self.e.suggestion(self.a,self.b,'One optional thought');self.begin();two=self.e.suggestion(self.a,self.b,'Another optional thought');self.assertNotEqual(one['id'],two['id']);self.assertEqual(len(self.a.ap_account.identified_bindings()),2);self.assertEqual(len(TP.live(self.b,'suggestion')),2);self.valid()

 def test_retraining_actual_dependency_stat_and_capability_cleanup_binding_survives(self):
  self.acquire();before=self.a.stats['spd'];self.capable();self.retrain(TP.CLASS);self.assertFalse(TP.acquired(self.a));self.assertFalse(T.owns(self.a));self.assertEqual(self.a.stats['spd'],before-1);self.restore();self.valid()
  self.setup();self.family(TP.SUGGEST);self.capable();row=self.e.suggestion(self.a,self.b,'Existing thought');self.retrain(TP.SUGGEST);self.assertTrue(TP.live(self.b,'suggestion'));self.begin();self.e.release_suggestion(self.a,row['id']);self.valid()

 def test_core308_trainer_projection_any_recipient_pokemon_requires_telepath(self):
  self.capable();self.allow(self.b);out=self.e.project_telepathic_thought(self.a,[self.b],'actual projected thought',source_policy='core_1.05',request_id='core-send');self.assertEqual(out['results'][0]['message']['text'],'actual projected thought');self.assertFalse(T.owns(self.b))
  self.reject(lambda:self.e.project_telepathic_thought(self.a,[self.b],'legacy rejects',request_id='legacy-send'),'telepath')
  from builder import build_pokemon
  p=Combatant(self.rules,build_pokemon(self.rules,'잉어킹',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}));self.e.gm.add_combatant(p,pos=(4,4),side='party',reason='actual Pokemon projection sender');self.grant(p,'Telepathy');self.e.gm.set_skill(p,'집중',6,reason='actual Pokemon Focus');prepare_body(self.e,p,size=p.spec['size'],offsets=[(0,0)],reason='actual Pokemon body');self.reject(lambda:self.e.project_telepathic_thought(p,[self.b],'pokemon rejects',source_policy='core_1.05',request_id='pokemon-send'),'Telepathy recipient');self.restore();self.valid()

 def test_core308_actual_read_awareness_unwilling_cumulative_retry_and_24h(self):
  self.capable();O.observe_thought(self.e,self.b,'Actual current surface',reason='spoken observation');self.allow(self.b,aware=False,willing=True)
  first=self.core_read('aware-fail',roll_options=self.fixed(False));self.assertEqual(first['reason'],'opposed_failed');self.assertFalse(first['event']['supernatural_trace']);self.assertIsNotNone(first['check'])
  self.allow(self.b,aware=True,willing=False);second=self.core_read('unwilling-fail',roll_options=self.fixed(False));third=self.core_read('unwilling-fail2',roll_options=self.fixed(False));self.assertEqual((first['retry_modifier'],second['retry_modifier'],third['retry_modifier']),(0,-3,-6));self.assertTrue(second['event']['supernatural_trace'])
  self.allow(self.b);out=self.core_read('aware-deliver');self.assertEqual(out['message']['surface_thought'],'Actual current surface');self.assertIsNone(out['check']);self.restore();self.valid()
  self.e.elapsed_seconds+=86400;out=self.core_read('expired-retry');self.assertEqual(out['retry_modifier'],0)

 def test_core308_focus_twice_range_projection_floor_one_read_unknown_and_mindlock(self):
  self.capable();self.allow(self.b);self.e.gm.set_position(self.b,(14,2),reason='Focus times two boundary');self.assertEqual(self.core_read('boundary')['message']['status'],'unknown');self.e.gm.set_position(self.b,(15,2),reason='outside read range');self.assertNotEqual(self.core_read('outside')['status'],'delivered')
  self.e.gm.set_position(self.b,(6,2),reason='inside mindlock test');self.grant(self.b);self.assertNotEqual(self.core_read('mindlock')['status'],'delivered');many=[self.b,self.c,self.add('fourth',(4,4)),self.add('fifth',(5,4))];self.reject(lambda:self.e.project_telepathic_thought(self.a,many,'too many',source_policy='core_1.05',request_id='too-many'),'maximum');self.restore();self.valid()

 def test_warning_real_attack_optional_shift_interrupt_one_completion_and_residue(self):
  self.family(TP.WARNING);self.capable();self.target_party();self.e.gm.set_position(self.c,(5,2),reason='ally attack origin');self.e.gm.set_position(self.b,(6,2),reason='adjacent ally recipient');self.arm(path=[(6,3),(6,4)]);ap=AP.available(self.a);row=self.attack('move/몸통박치기');self.assertEqual(self.b.pos,(6,4));self.assertFalse(row['results'][self.b.entity_id]['hit']);self.assertEqual(AP.available(self.a),ap-1);self.assertEqual(len(TP.live(self.b,'psychic_residue')),1);self.assertEqual(len([x for x in self.e._move_completions.values() if x['actor'] is self.c]),1);self.restore();self.valid()
  self.setup();self.family(TP.WARNING);self.capable();self.target_party();self.arm(path=[(6,3)]);row=self.attack(face=1);self.assertEqual(self.b.pos,(6,3));self.assertFalse(row['results'][self.b.entity_id]['hit']);self.assertTrue(TP.live(self.b,'psychic_residue'));self.valid()

 def test_warning_attacker_mindlock_blocks_owner_recipient_mindlock_does_not(self):
  for blocked in (True,False):
   with self.subTest(attacker_mindlock=blocked):
    self.setup();self.family(TP.WARNING);self.capable();self.target_party();self.e.gm.set_position(self.c,(5,2),reason='actual attacker');self.e.gm.set_position(self.b,(6,2),reason='actual attack recipient');self.grant(self.c if blocked else self.a);self.grant(self.b);self.arm(path=[(6,3),(6,4)]);ap=AP.available(self.a);row=self.attack('move/몸통박치기');self.assertEqual(self.b.pos,(6,2) if blocked else (6,4));self.assertEqual(AP.available(self.a),ap if blocked else ap-1);self.assertEqual(bool(TP.live(self.b,'psychic_residue')),not blocked);self.valid()

 def test_warning_optional_decline_and_invalid_path_roll_back_original_attack(self):
  self.family(TP.WARNING);self.capable();self.target_party();self.arm(path=None);before=AP.available(self.a);row=self.attack();self.assertEqual(AP.available(self.a),before);self.assertFalse(TP.live(self.b,'psychic_residue'))
  self.setup();self.family(TP.WARNING);self.capable();self.target_party();self.arm(path=[(20,20)]);self.know(self.c,'move/파도타기');self.e.gm.set_position(self.c,(3,2),reason='actual horizontal line before invalid path');self.begin(self.c)
  with patch.object(Engine,'d20',return_value=18):self.reject(lambda:self.e.use_move_on(self.c,self.b,'move/파도타기',[self.b],set_damage=True),'path|adjacent|step|distance')

 def test_core_ability_original_directional_area_avoidance_and_body_overlap(self):
  for offsets,path,still_hit in (([(0,0)],[(6,3),(6,4)],False), ([(0,0),(0,-1)],[(6,3)],True)):
   with self.subTest(body=offsets):
    self.setup();self.family(TP.AWARE,actor=self.b);self.target_party();self.e.gm.set_position(self.c,(3,2),reason='original directional line');prepare_body(self.e,self.b,size='중형',offsets=offsets,reason='actual occupied footprint');self.e.arm_telepath_reaction(self.b,TP.CORE,paths={self.b.entity_id:path});hp=self.b.hp;row=self.attack('move/파도타기',aim=(7,2));self.assertEqual(bool(row['results'][self.b.entity_id]['hit']),still_hit);self.assertEqual(self.b.hp<hp,still_hit);self.restore();self.valid()

 def test_core_ability_original_ranged_blast_does_not_recentre_after_shift(self):
  self.family(TP.AWARE,actor=self.b);self.target_party();self.e.arm_telepath_reaction(self.b,TP.CORE,paths={self.b.entity_id:[(7,2),(8,2),(9,2)]});row=self.attack('move/스톤샤워',aim=(6,2));self.assertFalse(row['results'][self.b.entity_id]['hit']);self.assertEqual(self.b.pos,(9,2));self.restore();self.valid()

 def test_feb2016_ability_static_evasion_damaging_ally_aoe_free_one_metre_disengage(self):
  self.rules=Rules(ROOT,ruleset='all');self.setup();before=self.b.evasion('특수');self.family(TP.AWARE,selection=TP.FEB,actor=self.b);self.assertEqual(self.b.evasion('특수'),before+1);self.target_party();self.e.arm_telepath_reaction(self.b,TP.FEB,paths={self.b.entity_id:[(6,3)]});row=self.attack('move/파도타기',aim=(7,2));self.assertEqual(self.b.pos,(6,3));self.assertFalse(row['results'][self.b.entity_id]['hit']);self.assertIsNone(getattr(self.b,'budget',None));self.restore();self.valid()

 def test_gentle_vibe_burst_two_self_all_targets_reset_volatile_only_mindlock(self):
  self.family(TP.AWARE,selection=TP.GENTLE);self.e.gm.set_position(self.b,(4,2),reason='Burst two endpoint');self.grant(self.b)
  for a in (self.a,self.b,self.c):self.e.change_stage(a,'atk',2);self.e.gm.add_condition(a,'혼란',force=True,reason='observed volatile');self.e.gm.add_condition(a,'독',force=True,reason='observed persistent poison')
  self.begin();out=self.e.activate_ability(self.a,TP.GENTLE,self.b);self.assertEqual({x['target_id'] for x in out['targets']},{self.a.entity_id,self.b.entity_id,self.c.entity_id});self.assertEqual(self.a.stages['atk'],0);self.assertEqual(self.c.stages['atk'],0);self.assertEqual(self.b.stages['atk'],2);self.assertNotIn('혼란',self.a.conditions);self.assertIn('독',self.a.conditions);self.assertIn('혼란',self.b.conditions);self.assertEqual(self.a.budget['standard'],0);self.restore();self.valid();self.begin();self.reject(lambda:self.e.activate_ability(self.a,TP.GENTLE,self.a),'frequency')

 def test_mind_reader_actual_read_optional_korean_hit_consumption_and_core_literal(self):
  row=self.mindread('korean_csv');self.assertEqual(row['effect']['contract'],'korean_csv');self.begin();self.rules.rulings.decide=lambda *a,**k:True
  with patch.object(Engine,'d20',return_value=1):self.e.use_move(self.a,self.b,'move/물대포',set_damage=True)
  self.assertTrue(self.completion(self.a,'move/물대포')['results'][self.b.entity_id]['hit']);self.assertFalse(TP.live(self.b,'read'));self.valid()
  self.setup();self.mindread();self.begin();self.rules.rulings.decide=lambda *a,**k:True
  with patch.object(Engine,'d20',return_value=1):self.e.use_move(self.a,self.b,'move/물대포',set_damage=True)
  self.assertFalse(self.completion(self.a,'move/물대포')['results'][self.b.entity_id]['hit']);self.assertTrue(TP.live(self.b,'read'));self.valid()
  self.setup();self.mindread();self.begin();self.rules.rulings.decide=lambda *a,**k:True
  with patch.object(Engine,'d20',return_value=1):self.e.use_move(self.a,self.a,'move/물대포',set_damage=True)
  self.assertTrue(self.completion(self.a,'move/물대포')['results'][self.a.entity_id]['hit']);self.assertFalse(TP.live(self.b,'read'));self.valid()

 def test_mind_reader_opponent_miss_no_miss_exception_and_optional_decline(self):
  for move,consume in (('move/물대포',True),('move/스피드스타',False)):
   with self.subTest(move=move):
    self.setup();self.mindread();self.know(self.b,move);self.turn(self.b);self.rules.rulings.decide=lambda *a,**k:True
    with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.b,self.a,move,set_damage=True)
    self.assertEqual(self.completion(self.b,move)['results'][self.a.entity_id]['hit'],not consume);self.assertEqual(bool(TP.live(self.b,'read')),not consume);self.valid()

 def test_mind_reader_next_user_turn_end_restore_thought_requires_capability(self):
  self.mindread();self.reject(lambda:self.e.read_mind_reader_thoughts(self.a,self.b),'current Telepathy');self.grant(self.a,'Telepathy');self.assertEqual(self.e.read_mind_reader_thoughts(self.a,self.b)['status'],'unknown');O.observe_thought(self.e,self.b,'real surface thought',reason='actual world fact');self.assertEqual(self.e.read_mind_reader_thoughts(self.a,self.b)['surface_thought'],'real surface thought');self.grant(self.b);self.reject(lambda:self.e.read_mind_reader_thoughts(self.a,self.b),'Mindlock');self.restore();self.valid();self.close();self.assertTrue(TP.live(self.b,'read'));self.begin();self.close();self.assertFalse(TP.live(self.b,'read'));self.valid()

 def test_reference_calm_mind_special_stages_extrasensory_flinch_and_psyshock_defense(self):
  self.family(TP.HONED);self.family(TP.ASSAULT);self.begin();self.e.use_move(self.a,self.a,'move/명상');self.assertEqual((self.a.stages['spa'],self.a.stages['spd']),(1,1));self.begin()
  with patch.object(Engine,'d20',return_value=19):self.e.use_move(self.a,self.b,'move/신통력',set_damage=True)
  self.assertTrue(__import__('condition_instances').records(self.b,'풀죽음'));self.setup();self.family(TP.ASSAULT);self.begin();seen=[];original=Combatant.evasion
  def evasion(a,category,*args,**kw):seen.append(category);return original(a,category,*args,**kw)
  import event_trace as TRACE,effects as FX
  with patch.object(Engine,'d20',return_value=18),patch.object(Combatant,'evasion',evasion),patch.object(TRACE,'calculation',wraps=TRACE.calculation) as calculation:self.e.use_move(self.a,self.b,TP.PSYSHOCK,set_damage=True)
  actual=next(x.kwargs for x in calculation.call_args_list if x.kwargs.get('source')==TP.PSYSHOCK);self.assertEqual((actual['damage_class'],actual['defense_stat']),('특수','def'));self.assertIn('특수',seen);move=self.completion(self.a,TP.PSYSHOCK)['move'];trigger=FX.parse_trigger(self.rules.move('move/미러코트')['effect'].split('.',1)[0]);self.assertTrue(FX.event_matches(trigger,{'event':'on_hit_received','move':move}));self.assertLess(self.b.hp,self.b.max_hp);self.restore();self.valid()

 def test_actual_source_tamper_and_late_native_failure_rollback(self):
  self.family(TP.SUGGEST);self.capable();original=TP.residue
  def late(*a,**k):original(*a,**k);raise ValueError('late actual residue failure')
  with patch.object(TP,'residue',late):self.reject(lambda:self.e.suggestion(self.a,self.b,'actual thought'),'late actual')
  row=self.e.suggestion(self.a,self.b,'actual thought');TP.live(self.b,'suggestion')[0]['effect']['compels_action']=True
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()

if __name__=='__main__':unittest.main()
