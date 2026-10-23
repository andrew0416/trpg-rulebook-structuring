"""Style Expert actual acquisition, twenty native Moves and both play modes."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from contest import ContestEngine,ContestRules
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import style_expert as S,trainer_feature_acquisition as A,acquired_features as AC
import action_points as AP,state_grants as G,state_codec as CODEC,world_entities as WORLD
import contest_features as CF,combat_timing as TIME,frequency as F
import common_checks as C


class StyleExpertTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core');cls.cr=ContestRules(ROOT,'core')
 def setUp(self):
  original=self.rules.rulings;self.rules.rulings=deepcopy(original)
  self.addCleanup(setattr,self.rules,'rulings',original)
  self.setup()
 def setup(self,stat='아름다움'):
  self.stat=stat;self.e=Engine(self.rules,seed=115117);self.e.grid=Grid(20,16)
  common=dict(level=25,size='중형',stats={'hp':100,'atk':30,'def':30,'spa':30,'spd':30,'spe':30},
   moves=['move/몸통박치기','move/연속자르기','move/염동력','move/거품','move/은빛바람'],abilities=[],types=['노말'],movement={'land':6,'swim':4,'sky':4,'power':4},weight_kg=30,
   skills={'직감':6,'명령':6,'매력':6,'교활':6,'협박':6,'육상':4,'곡예':4,'집중':4},gender='수컷',weight_class=3)
  self.a=Combatant(self.rules,dict(deepcopy(common),name='actual Style owner',kind='trainer',classes=[],feats=[],exp_bank=50))
  self.e.gm.add_combatant(self.a,pos=(0,0),side='party',reason='actual owner')
  self.partners=[]
  for n,pos in enumerate(((5,5),(1,0),(1,1))):
   p=Combatant(self.rules,dict(deepcopy(common),name='actual Style partner '+str(n),kind='pokemon',trainer_id=self.a.entity_id,poffins=[stat]*3))
   self.e.gm.add_combatant(p,pos=pos,side='party',reason='three distinct trained Pokemon');self.partners.append(p)
   self.e.gm.observe_loyalty(p,6,reason='actual willing partner')
  self.p,self.q,self.r=self.partners
  self.b=Combatant(self.rules,dict(deepcopy(common),name='actual recipient',kind='pokemon',gender='암컷',wild=True))
  self.e.gm.add_combatant(self.b,pos=(6,5),side='wild',reason='actual opposite gender recipient')
  for actor in self.e.everyone:prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='actual body')
 def acquire(self,feature=S.CLASS,stat=None,rank=None):
  branch=(stat or self.stat) if feature in (S.CLASS,S.FLOURISH,S.ENTRAINMENT) else None
  return A.acquire_static(self.e,self.a,feature,branch=branch,rank=rank,
   acquisition_request_id='Style/'+feature+'/'+str(branch)+'/'+str(rank))
 def family(self,stat=None,*,rank=1,effect=False,extra=False,flourish=False,entrainment=False):
  if stat is not None:self.setup(stat)
  self.acquire();self.acquire(S.RANKED[self.stat],rank=1)
  if rank==2:self.acquire(S.RANKED[self.stat],rank=2)
  if effect:self.acquire(S.IMPROVE[self.stat])
  if extra:self.acquire(CF.RANKED[self.stat][2][1])
  if flourish:self.acquire(S.FLOURISH)
  if entrainment:self.acquire(S.ENTRAINMENT)
 def combat(self,actor=None):self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.p,initiative_count=30)
 def use(self,mid='move/몸통박치기',target=None,**kw):
  with patch.object(Engine,'d20',return_value=19):return self.e.style_move(self.a,self.p,target or self.b,mid,set_damage=True,**kw)
 def rejected(self,fn,pattern=None):return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)
 def contest(self):
  ce=ContestEngine(self.cr,seed=115)
  c=ce.contestant_from_combatants(self.e,self.p,self.a,'직감',smart_stat_policy='ptu-original-special-defense')
  return ce,c
 def restored(self):
  ids=[a.entity_id for a in (self.a,self.p,self.q,self.r,self.b)]
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  self.a,self.p,self.q,self.r,self.b=[WORLD.actor_index(self.e)[uid] for uid in ids]
 def answer(self,key,value):self.e.rulings.add_answer(key,value,reason='actual player choice',scope='permanent')

 def test_template_has_all_features_and_actual_acquisition_does_not_grant_children(self):
  self.assertEqual(len(S.DEFINITIONS),18)
  self.acquire();self.assertEqual(len(AC.class_instances(self.a)),1)
  self.assertFalse(S.acquired(self.a,S.RANKED[self.stat]));self.assertEqual(CF.style_stat_dice(self.e,self.a,self.p),{self.stat:2})
  for p in self.partners:p.spec['poffins']=[]
  self.assertEqual(CF.style_stat_dice(self.e,self.a,self.p),{self.stat:2})
  self.restored();self.assertTrue(self.e.validate_state()['valid'])

 def test_actual_physical_poffins_and_wrong_owner_do_not_bootstrap_acquisition(self):
  self.q.spec['poffins']=[];self.r.spec['poffins']=[]
  self.rejected(self.acquire,'three trained')
  self.rejected(lambda:self.acquire(S.RANKED[self.stat],rank=1),'prerequisite')

 def test_rank2_requires_actual_rank1_and_receipt_projection_tamper_is_rejected(self):
  self.acquire();self.rejected(lambda:self.acquire(S.RANKED[self.stat],rank=2),'next actual rank')
  self.acquire(S.RANKED[self.stat],rank=1)
  old=self.a.spec['feat_ranks'][S.RANKED[self.stat]];self.a.spec['feat_ranks'][S.RANKED[self.stat]]=2
  with self.assertRaisesRegex(ValueError,'projection'):A.validate_actor(self.a)
  self.a.spec['feat_ranks'][S.RANKED[self.stat]]=old
  self.acquire(S.RANKED[self.stat],rank=2);self.restored();self.assertTrue(self.e.validate_state()['valid'])

 def test_flourish_counts_as_prior_feature_for_entrainment(self):
  self.family(rank=2,flourish=True)
  self.assertEqual(AC.count_for_class(self.a,S.CLASS),4)
  self.acquire(S.ENTRAINMENT);self.assertEqual(len(S.records(self.a,S.ENTRAINMENT,True)),1)

 def test_all_twenty_ranked_moves_use_native_battle_effect_and_frequency(self):
  self.observed=[]
  for stat,ranks in S.MOVES.items():
   for index,moves in enumerate(ranks,1):
    for mid in moves:
     if mid in ('move/울부짖기','move/참기','move/원한'):continue
     with self.subTest(stat=stat,move=mid):
      self.setup(stat);self.family(rank=index)
      if mid=='move/원한':
       self.combat(self.b)
       with patch.object(Engine,'d20',return_value=19):self.e.use_move_on(self.b,self.p,'move/몸통박치기',self.e.everyone,set_damage=True)
       self.e.end_of_turn(self.b);self.e.start_of_turn(self.p,initiative_count=29)
      else:self.combat()
      before_moves=list(self.p.moves);before=AP.available(self.a)
      native=self.rules.move(mid);rng=__import__('weapon_actions').range_spec(self.e,native,self.p)
      target=self.p if rng.get('origin')=='self' and not rng.get('shape') else self.b
      result=self.use(mid,target,ranked=S.RANKED[stat])
      self.assertNotIsInstance(result,C.PendingDecision)
      self.assertEqual(AP.available(self.a),before-1)
      self.assertEqual(self.p.moves,before_moves)
      self.assertGreater(self.p.move_uses.get(mid,0),0)
      rows=[row for row in getattr(self.e,'_move_completions',{}).values() if row['move_id']==mid]
      self.assertTrue(rows and all(row['phase']=='complete' for row in rows),mid)
      expected={'move/유혹':('spa',-2),'move/부르짖기':('atk',-1),'move/애교부리기':('atk',-2),'move/거짓울음':('spd',-2),'move/부추기기':('spa',1),'move/겁나는얼굴':('spe',-2)}
      if mid in expected:
       stat_name,delta=expected[mid];self.assertEqual(self.b.stages[stat_name],delta)
      if mid=='move/부르짖기':self.assertEqual(self.b.stages['spa'],-1)
      statuses={'move/악마의키스':{'잠듦'},'move/검은눈빛':{'수렁','둔화'},'move/블록':{'구속','수렁'},'move/흔들흔들댄스':{'혼란'},'move/헤롱헤롱':{'헤롱헤롱'},'move/도발':{'난동'},'move/부추기기':{'혼란'},'move/뱀눈초리':{'마비'}}
      if mid in statuses:self.assertTrue(statuses[mid]<=self.b.conditions,(mid,self.b.conditions))
      if mid=='move/명상':self.assertEqual((self.p.stages['spa'],self.p.stages['spd']),(1,1))
      if mid=='move/기충전':self.assertTrue(__import__('declarative_move_contracts').live(self.p,'focus_until_switch'))
      if mid=='move/흰안개':self.assertEqual(sum(__import__('blessing_effects').remaining(r) for _,r in __import__('blessing_effects').beneficiaries(self.e,self.p)),3)
      if mid=='move/그림자분신':self.assertEqual(len(__import__('double_team').records(self.p)),1)
      self.observed.append(mid)
  self.assertEqual(len(self.observed),17)

 def test_all_twenty_ranked_moves_perform_in_native_contest_without_learning(self):
  for stat,ranks in S.MOVES.items():
   for index,moves in enumerate(ranks,1):
    for mid in moves:
     with self.subTest(stat=stat,move=mid):
      self.setup(stat);self.family(rank=index);ce,c=self.contest();before=AP.available(self.a);learned=list(c.moves)
      battle=(deepcopy(self.p.move_uses),deepcopy(self.p.spec.get('frequency_state')))
      ce.perform(c,mid,stat,[],False,style_ranked=S.RANKED[stat])
      self.assertEqual(c.last_move,mid);self.assertEqual(AP.available(self.a),before-1);self.assertEqual(c.moves,learned)
      self.assertTrue(ce.log_lines)
      self.assertEqual((self.p.move_uses,self.p.spec.get('frequency_state')),battle)
  for stat,mid in (('아름다움','move/흰안개'),('근사함','move/부르짖기')):
   with self.subTest(performance_frequency_exception=mid):
    self.setup(stat);self.family();ce,c=self.contest();before=AP.available(self.a)
    battle=(deepcopy(self.p.move_uses),deepcopy(self.p.spec.get('frequency_state')))
    ce.perform(c,mid,stat,[],False,style_ranked=S.RANKED[stat])
    snapshot=(deepcopy(vars(c)),AP.available(self.a),ce.rng.getstate(),list(ce.log_lines))
    with self.assertRaisesRegex(ValueError,'Consecutive'):
     ce.perform(c,mid,stat,[],False,style_ranked=S.RANKED[stat])
    self.assertEqual((vars(c),AP.available(self.a),ce.rng.getstate(),ce.log_lines),snapshot)
    ce.perform(c,'move/몸통박치기',stat,[],False)
    ce.perform(c,mid,stat,[],False,style_ranked=S.RANKED[stat])
    self.assertEqual(AP.available(self.a),before-2)
    self.assertEqual((self.p.move_uses,self.p.spec.get('frequency_state')),battle)

 def test_ranked_move_wrong_rank_type_ap_and_native_turn_failure_are_atomic(self):
  self.family();self.combat()
  self.rejected(lambda:self.use('move/악마의키스',ranked=S.RANKED[self.stat]),'outside')
  self.rejected(lambda:self.use('move/흰안개',ranked=S.RANKED['근사함']),'acquired')
  self.e.end_of_turn(self.p)
  self.rejected(lambda:self.use('move/흰안개',target=self.p,ranked=S.RANKED[self.stat]),'Style|activation|turn')

 def test_flourish_battle_after_native_effect_and_target_scene_once_across_restore(self):
  self.family(rank=2,flourish=True);self.combat()
  before=AP.available(self.a)
  self.use('move/유혹',ranked=S.RANKED[self.stat],flourish=True)
  self.assertEqual(self.p.stages['spa'],1);self.assertEqual(AP.available(self.a),before-2)
  self.assertTrue(any(row.get('style_flourish') for row in TIME.records(self.p)))
  self.restored();self.rejected(lambda:self.use('move/유혹',ranked=S.RANKED[self.stat],flourish=True),'already affected')

 def test_fabulous_max_converts_ranged_and_native_hit_targets_once(self):
  self.family(effect=True);self.combat()
  self.use('move/유혹',ranked=S.RANKED[self.stat],effect=S.IMPROVE[self.stat])
  row=list(self.e._move_completions.values())[-1]
  self.assertEqual(len(row['targets']),len(set(t.entity_id for t in row['targets'])))
  self.assertEqual(self.b.stages['spa'],-2)
  self.assertNotIn('_style_move_scope',vars(self.e))

 def test_each_alignment_effect_native_contest_opposing_neutral_and_matching(self):
  for stat in S.STATS:
   for alignment in ('opposing','neutral','matching'):
    with self.subTest(stat=stat,alignment=alignment):
     self.setup(stat);self.family(rank=2,effect=True);ce,c=self.contest()
     mid=dict(zip(S.STATS,('move/은빛바람','move/연속자르기','move/거품','move/염동력','move/몸통박치기')))[stat]
     match=ce.type_mod(stat,stat)[0];kinds={'opposing':-match,'neutral':0,'matching':match}
     contest_stat=next(t for t in S.STATS if ce.type_mod(stat,t)[0]==kinds[alignment])
     ranked=S.RANKED[stat] if any(mid in r for r in S.MOVES[stat]) else None
     ce.perform(c,mid,contest_stat,[],False,style_ranked=ranked,style_effect=S.IMPROVE[stat])
     self.assertIn('Style alignment','\n'.join(ce.log_lines))
     with self.assertRaisesRegex(ValueError,'already used'):ce.perform(c,mid,contest_stat,[],False,style_ranked=ranked,style_effect=S.IMPROVE[stat])

 def test_rule_of_cool_critical_delta_is_only_actual_move_scope(self):
  import passive_events as PASSIVE
  self.setup('근사함');self.family(effect=True)
  self.e.gm.set_move(self.b,'move/판별',reason='actual learned Detect')
  self.combat();self.e.watch_move_defense(self.b,[{'actor_id':self.b.entity_id,'source':'move/판별'}],reason='actual Detect hit response')
  with patch.object(Engine,'d20',return_value=17),self.assertRaises(PASSIVE.PassiveEventPending):self.e.style_move(self.a,self.p,self.b,'move/연속자르기',effect=S.IMPROVE[self.stat],set_damage=True)
  event=self.e._passive_pending
  self.rejected(lambda:self.e.choose_move_defense(event,self.b,use=True,reason='actual reacting Detect'),'Rule of Cool')
  self.e.choose_move_defense(event,self.b,use=False,reason='actual decline after prohibited Interrupt')
  self.assertTrue(any('d20=17' in line and '치명타!' in line for line in self.e.log_lines))
  row=list(self.e._move_completions.values())[-1]
  self.assertEqual(row['style_expert']['effect'],S.IMPROVE[self.stat])
  self.assertTrue(S.blocks_interrupt_move(self.e,{'completion_id':row['id']}))
  self.assertEqual(S.critical(self.e,self.p,self.rules.move('move/연속자르기')),0)

 def test_gleeful_steps_grants_physical_half_shift_without_regular_shift_cost(self):
  self.setup('귀여움');self.family(effect=True);self.combat();before=self.p.budget['shift']
  self.use('move/애교부리기',ranked=S.RANKED[self.stat],effect=S.IMPROVE[self.stat],destination=[(5,6),(5,7),(5,8)])
  self.assertEqual(self.p.pos,(5,8));self.assertEqual(self.p.budget['shift'],before)

 def test_calculated_assault_allies_expires_at_actual_next_owner_turn_end(self):
  self.setup('슬기로움');self.family(effect=True);self.combat()
  self.use('move/거짓울음',ranked=S.RANKED[self.stat],effect=S.IMPROVE[self.stat],choice='allies')
  self.assertEqual(S.accuracy(self.e,self.q,self.b,self.rules.move('move/몸통박치기')),1)
  self.e.end_of_turn(self.p);self.assertEqual(S.accuracy(self.e,self.q,self.b,self.rules.move('move/몸통박치기')),1)
  self.restored();self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=30)
  self.e.end_of_turn(self.p);self.assertEqual(S.accuracy(self.e,self.q,self.b,self.rules.move('move/몸통박치기')),0)

 def test_calculated_assault_focus_counts_actual_distinct_allies_current_round(self):
  self.setup('슬기로움');self.family(effect=True)
  self.q.pos=(6,6);self.combat(self.q)
  with patch.object(Engine,'d20',return_value=19):self.e.use_move_on(self.q,self.b,'move/몸통박치기',self.e.everyone,set_damage=True)
  self.e.end_of_turn(self.q);self.e.start_of_turn(self.p,initiative_count=29)
  observed=[];original=S.accuracy
  def observe(e,a,t,m):
   value=original(e,a,t,m)
   if a.entity_id==self.p.entity_id:observed.append(value)
   return value
  with patch.object(S,'accuracy',side_effect=observe):self.use('move/거짓울음',ranked=S.RANKED[self.stat],effect=S.IMPROVE[self.stat],choice='focus')
  self.assertEqual(observed,[1]);self.assertTrue(any('d20=19+1=20' in line for line in self.e.log_lines))

 def test_macho_charge_uses_actual_hit_and_forced_geometry_without_maneuver(self):
  self.setup('강인함');self.family(effect=True);self.combat();origin=self.b.pos
  self.use('move/겁나는얼굴',ranked=S.RANKED[self.stat],effect=S.IMPROVE[self.stat])
  self.assertEqual(self.b.pos,(origin[0]+3,origin[1]));self.assertEqual(self.b.stages['spe'],-2)

 def test_enticing_beauty_real_alluring_daily_bait_and_poffin_lure_bonus(self):
  self.family(extra=True);self.e.enticing_beauty(self.a,self.p)
  self.assertIn('매혹',G.effective_capabilities(self.p));self.assertEqual(S.lure_bonus(self.p),5)
  import wild_equipment as W
  W.attract(self.e,self.p,phase='place',bait_id='actual-scent',habitat={'region':'native garden','species':['이상해씨'],'reason':'actual nearby species'})
  out=W.attract(self.e,self.p,phase='wait',bait_id='actual-scent',fixed=10)
  self.assertEqual(out['checks'][-1]['total'],15);self.assertEqual(out['status'],'awaiting_encounter')
  self.e.end_scene(self.e.everyone);self.assertEqual(S.lure_bonus(self.p),0)

 def test_endurance_native_heavy_acting_loss_only_and_full_round_expiry(self):
  self.setup('강인함');self.family(extra=True);self.p.injuries=5;self.combat()
  self.assertEqual(self.e.style_endurance(self.a,self.p,'heavy'),2)
  import taskmaster as TASK
  self.assertTrue(TASK.ignores_acting_loss(self.p));self.assertFalse(TASK.immune_loss(self.p))
  before=self.p.hp
  with patch.object(Engine,'d20',return_value=19):self.e.use_move_on(self.p,self.b,'move/몸통박치기',self.e.everyone,set_damage=True)
  self.assertEqual(self.p.hp,before)
  self.e.end_of_turn(self.p);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(30)
  self.assertTrue(S.endurance_active(self.p));self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(30)
  self.assertFalse(S.endurance_active(self.p))

 def test_endurance_native_suffocation_extends_existing_grace_and_resets_on_breathing(self):
  self.setup('강인함');self.family(extra=True)
  import environmental_effects as E
  E.observe_breathing(self.e,self.p,air_available=False,medium='airless',reason='actual deprivation',timing_policy='grace_boundary')
  self.e.style_endurance(self.a,self.p,'suffocation');self.assertEqual(self.p.spec['_respiration']['grace_seconds'],80)
  self.e.advance_time(79,[self.p]);self.assertEqual(self.p.injuries,0)
  self.e.advance_time(1,[self.p]);self.assertEqual(self.p.injuries,1)
  E.observe_breathing(self.e,self.p,air_available=True,medium='air',reason='actual breathing')
  self.assertEqual(self.p.spec['_respiration']['grace_seconds'],60);self.assertEqual(self.p.injuries,0)

 def test_endurance_native_fall_reduces_damage_distance_and_uses_scene_frequency(self):
  self.setup('강인함');self.family(extra=True)
  result=self.e.style_endurance(self.a,self.p,'fall',action_id='actual-fall',meters=3,intentional=False,reason='actual observed fall',natural_sky=False,natural_sky_reason='native grounded species')
  self.assertEqual(result['damage_distance'],1)
  self.rejected(lambda:self.e.style_endurance(self.a,self.p,'heavy'),'Heavy Injury')

