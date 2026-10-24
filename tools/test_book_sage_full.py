"""Whole Sage through real acquisition, native Moves, healing and injury events."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import sage as S,trainer_feature_acquisition as T,blessing_effects as B,effect_instances as E
import state_codec as CODEC,world_entities as W,combat_timing as TIME,action_points as AP
import ability_transitions as AB,frequency as F,state_grants as G

class SageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old);self.setup()
 def setup(self,rank=6):
  self.e=Engine(self.rules,seed=29672978);self.e.grid=Grid(40,40)
  self.a=self.add('Sage',(2,2),rank=rank);self.b=self.add('foe',(4,2),side='foe')
  self.c=self.add('ally',(3,2));self.p=self.add('Pokemon',(2,3),kind='pokemon',hp=10)
 def add(self,name,pos,*,side='party',kind='trainer',rank=6,hp=40):
  spec=dict(name=name,kind=kind,level=30,size='중형',stats={'hp':hp,'atk':30,'def':20,'spa':30,'spd':20,'spe':30},moves=['move/몸통박치기','move/물대포','move/째려보기','move/맹독'],types=['노말'],abilities=[],classes=[],feats=[],edges=[],skills={'오컬트학':rank,'육상':4,'곡예':4,'전투':4,'집중':4,'은신':4,'직감':3},movement={'land':8,'power':4},exp_bank=100,weight_kg=30,gender='수컷')
  if kind=='pokemon':spec['species']='피카츄'
  actor=Combatant(self.rules,spec);self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual Sage participant')
  prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed native body');self.e.register_abilities(actor);return actor
 def acquire(self,uid=S.CLASS,actor=None,selection=None):
  actor=actor or self.a
  return T.acquire_static(self.e,actor,uid,selection=selection,acquisition_request_id='sage:'+actor.entity_id+':'+uid)
 def family(self,uid,actor=None,choice=S.TOUCH):
  actor=actor or self.a
  for parent in S.PARENTS[uid][:1] if uid==S.BENEDICTION else S.PARENTS[uid]:
   if not S.acquired(actor,parent):self.family(parent,actor,choice)
  if not S.acquired(actor,uid):self.acquire(uid,actor,choice if uid==S.HANDS else None)
 def close(self):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
 def begin(self,actor=None,count=60):
  self.close();self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=count)
 def turn(self,actor,count=50):self.close();self.e.start_of_turn(actor,initiative_count=count)
 def reject(self,fn,reason=None):
  provider=self.e.rulings.provider;self.e.rulings.provider=None
  try:return assert_rejected_unchanged(self.e,fn,reason_pattern=reason)
  finally:self.e.rulings.provider=provider
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  ids=[x.entity_id for x in (self.a,self.b,self.c,self.p)]
  provider=self.e.rulings.provider;self.e.rulings.provider=None
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  self.e.rulings.provider=provider
  self.a,self.b,self.c,self.p=[W.actor_index(self.e)[uid] for uid in ids]
 def answer(self,*,blessing=True,benediction=True,prayers=False):
  self.e.rulings.provider=lambda q:{'team_blessing':blessing,'sage_benediction':benediction,'sage_prayers':prayers}.get(q['type'])
 def cast(self,move,actor=None):
  actor=actor or self.a;self.family(S.MOVES[move],actor);self.begin(actor)
  self.e.use_move(actor,actor,move)
  return next(r for r in B.live(actor) if r['source']==move)
 def attack(self,move='move/몸통박치기',target=None,face=18):
  self.begin(self.b)
  with patch.object(Engine,'d20',return_value=face):return self.e.use_move(self.b,target or self.c,move,set_damage=True)
 def retrain(self,uid):
  import trainer_retraining as R
  owned=R._owned(self.a);sources={u:R.owned_source(self.e,self.a,u) for u in owned};required=R._native_dependencies(self.e,self.a,owned)
  deps={source:[sources[p] for p in required.get(u,[])] for u,source in sources.items() if u!=uid}
  return self.e.retrain_trainer_source(self.a,uid,request_id='retire:'+uid,reason='actual retraining consultation',gm_decision={'allowed':True,'reason':'approved'},retained_dependencies=deps)

 def test_seven_independent_actual_acquisitions_hp_tags_no_automatic_siblings_restore(self):
  hp=self.a.stats['hp'];self.acquire();self.assertEqual(len(S.records(self.a,active=True)),1);self.assertEqual(self.a.stats['hp'],hp+1)
  self.assertFalse(S.acquired(self.a,S.SHIELD));self.assertNotIn('move/리플렉터',self.a.moves)
  for uid in S.FEATURES:self.family(uid)
  self.assertEqual(len(S.records(self.a,active=True)),7);self.assertEqual(self.a.stats['hp'],hp+7)
  __import__('items').register_feats(self.e,self.a);self.assertEqual(self.a.stats['hp'],hp+7)
  self.assertTrue(AB.active(self.a,S.TOUCH));self.assertFalse(AB.active(self.a,'ability/축복의손길'));self.assertFalse(AB.active(self.a,S.HEALER))
  self.restore();self.valid()

 def test_prerequisites_rank_boundaries_and_benediction_or_are_actual_receipts(self):
  self.setup(rank=2);self.reject(lambda:self.acquire(),'rank')
  self.setup(rank=3);self.reject(lambda:self.acquire(S.SHIELD),'parent');self.family(S.SHIELD)
  self.reject(lambda:self.acquire(S.BENEDICTION),'rank');self.reject(lambda:self.acquire(S.HANDS,selection=S.TOUCH),'rank')
  self.setup(rank=4);self.family(S.DEFENSE);self.acquire(S.BENEDICTION);self.assertFalse(S.acquired(self.a,S.SHIELD))
  self.reject(lambda:self.acquire(S.WIND),'rank');self.setup(rank=5);self.family(S.HANDS);self.family(S.PRAYERS)
  self.reject(lambda:self.acquire(S.WIND),'parent|rank')

 def test_hands_exact_two_choices_immutable_and_source_owned_withdrawal(self):
  self.acquire();self.reject(lambda:self.acquire(S.HANDS),'choice|exactly')
  self.acquire(S.HANDS,selection=S.HEALER);self.assertTrue(AB.active(self.a,S.HEALER));self.assertFalse(AB.active(self.a,S.TOUCH))
  self.reject(lambda:self.acquire(S.HANDS,selection=S.TOUCH),'selection|intent')
  self.e.gm.set_ability(self.a,'치유의마음',reason='independent imported ability')
  self.retrain(S.HANDS);self.assertTrue(AB.active(self.a,S.HEALER));self.assertEqual(self.a.stats['hp'],41)
  self.restore();self.valid()

 def test_sage_both_formula_operands_actual_damage_and_ignore_dr(self):
  self.acquire();self.begin();self.e.use_sage(self.a,self.p);self.assertEqual(S.reduction(self.p),12)
  self.turn(self.b);move=self.rules.move('move/몸통박치기');normal=self.e.roll_damage(self.b,self.p,move,set_damage=True)
  with patch.object(S,'reduction',return_value=0):baseline=self.e.roll_damage(self.b,self.p,move,set_damage=True)
  self.assertEqual(baseline-normal,12)
  ignored=deepcopy(self.rules.move_mech(move['id'])[0]);ignored.setdefault('effects_exec',[]).append({'type':'ignore_defense_modifiers','ignore':'all damage reduction'})
  self.assertEqual(__import__('effects_ext').defense_hook(self.e,self.b,self.p,move,ignored,'def')[1],0)
  self.begin();self.e.use_sage(self.a,self.c);self.assertEqual(S.reduction(self.c),self.e.tick(self.c));self.valid()
  self.close();self.e.end_scene(round_elapsed_seconds=10);self.assertEqual(S.reduction(self.c),0);self.valid()

 def test_sage_actual_range_ally_action_and_full_round_same_initiative_count(self):
  self.acquire();self.begin()
  self.reject(lambda:self.e.use_sage(self.a,self.b),'ally');self.e.gm.set_position(self.c,(10,10),reason='outside five metres')
  self.reject(lambda:self.e.use_sage(self.a,self.c),'range');self.e.gm.set_position(self.c,(3,2),reason='actual ally returns')
  self.e.use_sage(self.a,self.c);self.assertEqual(self.a.budget['standard'],0);self.close();self.e.end_round()
  self.assertGreater(S.reduction(self.c),0);self.e.start_round(self.e.everyone);self.e.at_initiative_count(61)
  self.assertGreater(S.reduction(self.c),0);self.e.at_initiative_count(60);self.assertEqual(S.reduction(self.c),0);self.valid()

 def test_ordinary_sage_never_adds_multiple_casters_or_repeated_instances(self):
  self.acquire();self.family(S.CLASS,self.c);self.begin();self.e.use_sage(self.a,self.p)
  self.turn(self.c);self.e.use_sage(self.c,self.p);self.assertEqual(S.reduction(self.p),12)
  self.assertEqual(len([r for r in TIME.records(self.p) if r.get('effect',{}).get('kind')=='sage_dr']),2)
  self.restore();self.valid()

 def test_reflect_benediction_after_entire_attack_not_in_triggering_defense(self):
  self.family(S.BENEDICTION);r=self.cast('move/리플렉터');self.answer()
  seen=[];original=Engine.roll_damage
  def damage(e,a,t,*args,**kw):seen.append(t.stages['def']);return original(e,a,t,*args,**kw)
  before=AP.available(self.a)
  with patch.object(Engine,'roll_damage',damage):self.attack()
  self.assertTrue(seen);self.assertEqual(set(seen),{0});self.assertEqual(self.c.stages['def'],1)
  self.assertEqual(AP.available(self.a),before-1);self.assertEqual(B.remaining(r),1);self.valid()

 def test_light_screen_and_lucky_chant_actual_consumers_and_exact_bonuses(self):
  self.family(S.BENEDICTION);r=self.cast('move/빛의장막');self.answer();self.attack('move/물대포')
  self.assertEqual(self.c.stages['spd'],1);self.assertEqual(B.remaining(r),1)
  lucky=self.cast('move/주술');self.attack(face=20)
  self.assertEqual(self.c.accuracy_stage,1);self.assertEqual(B.remaining(lucky),2);self.assertEqual(lucky['decisions'][0]['kind'],'critical_guard');self.valid()

 def test_benediction_other_creator_decline_and_no_feature_do_not_grant_or_spend(self):
  self.family(S.BENEDICTION);self.cast('move/리플렉터',self.c);self.answer();before=AP.available(self.a);self.attack()
  self.assertEqual(self.c.stages['def'],0);self.assertEqual(AP.available(self.a),before)
  self.cast('move/빛의장막');self.answer(blessing=False);self.attack('move/물대포')
  self.assertEqual(self.c.stages['spd'],0);self.assertEqual(AP.available(self.a),before);self.valid()

 def test_safeguard_received_status_then_ignore_only_next_personal_turn_restore(self):
  self.family(S.BENEDICTION);r=self.cast('move/신비의부적');self.answer();self.turn(self.b)
  self.e.apply_status(self.c,'화상',source='move/도깨비불',applied_by=self.b)
  self.assertIn('화상',self.c.conditions);self.assertFalse(B.ignored(self.c,'화상'));self.assertEqual(self.c.evasion_mod,1);self.assertEqual(B.remaining(r),2)
  self.restore();self.turn(self.c,40);self.assertTrue(B.ignored(self.c,'화상'));self.assertIn('화상',self.c.conditions)
  self.assertEqual(self.c.staged('def'),self.c.stats['def']);hp=self.c.hp
  self.e.use_move(self.c,self.b,'move/몸통박치기',set_damage=True);self.close();self.assertEqual(self.c.hp,hp)
  self.assertIn('화상',self.c.conditions);self.assertFalse(B.ignored(self.c,'화상'));self.assertLess(self.c.staged('def'),self.c.stats['def']);self.valid()

 def test_safeguard_shared_three_actual_receipts_decline_duplicate_and_other_status(self):
  r=self.cast('move/신비의부적');self.answer(benediction=False)
  for actor,status in ((self.c,'화상'),(self.p,'독'),(self.a,'마비')):self.assertTrue(self.e.apply_status(actor,status,source='condition/'+status))
  self.assertFalse(B.live(self.a));self.assertEqual(len(self.a.spec[B.HISTORY][-1]['decisions']),3)
  self.assertFalse(self.e.apply_status(self.c,'화상'));self.assertEqual(len(self.c.spec['blessing_status_ignores']),1)
  self.e.apply_status(self.c,'독',source='condition/독');self.turn(self.c,50)
  self.assertTrue(B.ignored(self.c,'화상'));self.assertFalse(B.ignored(self.c,'독'));self.restore();self.valid()

 def test_safeguard_sleep_action_evasion_and_slowed_movement_effect_consumers(self):
  self.cast('move/신비의부적');self.answer(benediction=False)
  self.e.apply_status(self.c,'잠듦',source='move/최면술');self.e.apply_status(self.c,'둔화',source='condition/둔화')
  self.turn(self.c,50);self.assertTrue(B.ignored(self.c,'잠듦'));self.assertGreater(self.c.evasion('물리'),0)
  profile=__import__('effects_ext').movement_profile(self.e,self.c,8,0);self.assertEqual(profile[0],8)
  self.e.use_move(self.c,self.b,'move/몸통박치기',set_damage=True);self.close();self.assertIn('잠듦',self.c.conditions);self.valid()

 def test_core_blessed_touch_daily_two_standard_quarter_actual_maximum_hp(self):
  self.family(S.HANDS);self.begin();self.e.gm.set_hp(self.c,self.c.max_hp-70,reason='actual missing HP');hp=self.c.hp
  used=self.e.activate_ability(self.a,S.TOUCH,self.c);self.assertEqual(used['changed'],self.c.base_max_hp//4);self.assertEqual(self.c.hp-hp,self.c.base_max_hp//4);self.assertEqual(self.a.budget['standard'],0)
  self.assertEqual(self.c.temp_hp,0);self.assertFalse(self.c.next_attack)
  self.begin();self.e.activate_ability(self.a,S.TOUCH,self.p);self.begin()
  self.reject(lambda:self.e.activate_ability(self.a,S.TOUCH,self.c),'frequency');self.restore();self.valid()

 def test_healer_scene_free_real_all_status_cure_preserves_physical_cause_exception(self):
  self.family(S.HANDS,choice=S.HEALER);self.begin();self.e.apply_status(self.c,'화상');self.e.apply_status(self.c,'독')
  standard=self.a.budget['standard'];used=self.e.activate_ability(self.a,S.HEALER,self.c)
  self.assertEqual(used['changed'],2);self.assertNotIn('화상',self.c.conditions);self.assertNotIn('독',self.c.conditions);self.assertEqual(self.a.budget['standard'],standard)
  self.reject(lambda:self.e.activate_ability(self.a,S.HEALER,self.c),'frequency')
  self.close();self.e.end_scene(round_elapsed_seconds=10);self.begin();self.e.apply_status(self.p,'기절')
  self.e.activate_ability(self.a,S.HEALER,self.p);self.assertIn('기절',self.p.conditions);self.valid()

 def test_both_actual_healing_abilities_trigger_free_prayer_once_including_zero_recovery(self):
  self.family(S.PRAYERS);self.begin();self.e.gm.set_hp(self.c,self.c.max_hp-60,reason='actual wounded ally');self.answer(benediction=False,prayers=True)
  receipt=self.e.activate_ability(self.a,S.TOUCH,self.c);self.assertGreater(S.reduction(self.c),0)
  self.assertFalse(S.prayer(self.e,self.a,self.c,receipt));self.assertFalse(S.prayer(self.e,self.a,self.c,{'kind':'injury','sequence':999}))
  self.assertEqual(F.state(self.a)['activations'][S.PRAYERS]['used'],1)
  self.begin();full=self.e.activate_ability(self.a,S.TOUCH,self.p);self.assertEqual(full['changed'],0);self.assertGreater(S.reduction(self.p),0)
  self.setup();self.family(S.PRAYERS,choice=S.HEALER);self.begin();self.answer(benediction=False,prayers=True)
  self.e.activate_ability(self.a,S.HEALER,self.c);self.assertGreater(S.reduction(self.c),0);self.valid()

 def test_actual_injury_prayers_scene_three_stack_only_own_instances_and_individual_expiry(self):
  self.family(S.PRAYERS);self.family(S.PRAYERS,self.c);self.begin();self.answer(benediction=False,prayers=True)
  self.e.take_damage(self.p,36);count=len([r for r in TIME.records(self.p) if r['effect']['kind']=='sage_dr']);self.assertGreater(count,0)
  self.turn(self.b,50);self.e.gm.set_hp(self.p,60,reason='actual heal before next injury');self.e.take_damage(self.p,36);self.assertGreater(S.reduction(self.p),12)
  groups={}
  for row in TIME.records(self.p):
   if row.get('effect',{}).get('kind')=='sage_dr':groups[row['effect']['caster_id']]=groups.get(row['effect']['caster_id'],0)+row['effect']['amount']
  self.assertEqual(S.reduction(self.p),max(groups.values()));self.assertEqual(F.state(self.a)['activations'][S.PRAYERS]['used'],3)
  self.e.take_damage(self.c,self.c.base_max_hp//2+1);self.assertEqual(S.reduction(self.c),0);self.assertEqual(F.state(self.a)['activations'][S.PRAYERS]['used'],3)
  self.close();self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(60);self.assertEqual(S.reduction(self.p),12)
  self.e.at_initiative_count(50);self.assertEqual(S.reduction(self.p),0)
  self.restore();self.valid()

 def test_divine_wind_preserves_identity_consumed_history_and_three_to_two_capacity(self):
  self.family(S.WIND);r=self.cast('move/주술');self.family(S.DEFENSE);self.answer(benediction=False)
  self.attack(face=20);uid=r['id'];history=deepcopy(r['decisions']);scope=deepcopy(r['scope_history']);meta=deepcopy(r[E.KEY]);self.begin(self.b);before=AP.available(self.a)
  result=self.e.divine_wind(self.a,'move/리플렉터');self.assertEqual(result,(uid,));r=B.live(self.a)[0]
  self.assertEqual(r['id'],uid);self.assertEqual(r['source'],'move/주술');self.assertEqual(r[E.KEY],meta);self.assertEqual(r['scope_history'],scope);self.assertEqual(r['decisions'],history);self.assertEqual(B.remaining(r),1);self.assertEqual(AP.available(self.a),before-2)
  self.reject(lambda:self.e.divine_wind(self.a,'move/리플렉터'),'Scene');self.restore();self.attack()
  ended=next(r for r in self.a.spec[B.HISTORY] if r['id']==uid);self.assertEqual(B.remaining(ended),0);self.assertEqual(ended['decisions'][-1]['move_class'],'물리');self.valid()

 def test_wind_all_own_other_types_only_excludes_other_creator_and_unavailable_type(self):
  self.family(S.WIND);first=self.cast('move/주술');self.cast('move/빛의장막');foreign=self.cast('move/리플렉터',self.c)
  self.begin();self.reject(lambda:self.e.divine_wind(self.a,'move/흰안개'),'Sage');changed=self.e.divine_wind(self.a,'move/리플렉터')
  self.assertEqual(len(changed),2);self.assertNotIn(foreign['id'],changed);self.assertEqual(B.effective_source(foreign),'move/리플렉터')
  self.begin();self.e.divine_wind(self.a,'move/신비의부적');self.assertEqual({r['effect']['kind'] for r in B.live(self.a)},{'team_status_guard'})
  self.answer(benediction=False);self.e.apply_status(self.p,'독');self.assertEqual(sum(len(r['decisions']) for r in B.live(self.a)),1);self.valid()

 def test_wind_late_failure_rolls_back_ap_pool_history_and_scene_selection(self):
  self.family(S.WIND);self.cast('move/주술');self.begin()
  original=B.convert_sage
  def fail(*args):original(*args);raise ValueError('late conversion consumer failure')
  with patch.object(B,'convert_sage',fail):self.reject(lambda:self.e.divine_wind(self.a,'move/리플렉터'),'late conversion')
  self.e.divine_wind(self.a,'move/리플렉터');self.restore();self.valid()

 def test_native_retraining_removes_only_sage_owned_hp_moves_ability_and_timed_source(self):
  self.acquire();self.begin();self.e.use_sage(self.a,self.p);before=self.a.stats['hp'];self.retrain(S.CLASS)
  self.assertEqual(self.a.stats['hp'],before-1);self.assertEqual(S.reduction(self.p),0);self.restore();self.valid()
