"""Exact native Ability producers, consumers, costs and lifetimes."""
from copy import deepcopy
from pathlib import Path
import csv,hashlib,json,sys,unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(ROOT/'tools')]

import ability_native_actions as NATIVE
import cultivation_growth as GROWTH
import effects_ext as EXT
import injury_recovery as INJURY
import state_grants as GRANTS
import temporary_hp as TEMP
from builder import build_pokemon,build_trainer
from engine import Rules,Engine,Combatant
from grid import Grid


class AbilityNativeActionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')

 def pokemon(self,identity,ability,*,moves=(),pos=(0,0),side='party',extra=None):
  supplied={'id':identity}
  if extra:supplied.update(extra)
  return Combatant(self.r,build_pokemon(self.r,'이상해씨',20,name=identity,moves=list(moves),
   abilities=[ability] if ability else [],pos=pos,side=side,extra=supplied))

 def trainer(self,identity,*,pos=(0,0),side='party'):
  spec=build_trainer(self.r,identity,20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),pos=pos,side=side,
   extra={'id':identity})
  return Combatant(self.r,spec)

 def engine(self,*actors,grid=True):
  e=Engine(self.r,seed=419)
  if grid:e.grid=Grid(24,24)
  for actor in actors:e.gm.add_combatant(actor)
  return e

 def turn(self,e,actor,actors=None,count=20):
  e.start_round(list(actors or e.gm.everyone));e.start_of_turn(actor,initiative_count=count)

 def valid(self,e):
  result=e.validate_state();self.assertTrue(result['valid'],result)

 def test_exact_ten_source_rows_policy_and_registry_are_bound(self):
  expected={
    'ability/리프가드-playtest':'85990e74c797c1657422f8623bd3e4d1c376e94bd7075ea011f633d4ab48ac83',
   'ability/겁주기':'ad5c193917a8c34e2d7a10170c037948a515581fbcaa421781d5c9cf4a9990e3',
   'ability/노을-playtest':'10e5eb3f92b428ed071511daaaaba7b84fbf807785dc62a41575c485e6a029a0',
   'ability/도시락통-playtest':'da477453268d0ea20d341ef7f79a0144ab9005885e8827d3209ffcdbbbf04ad8',
   'ability/디자이너':'05de703ffd3913f2f544abbcb87af0de8925220bcb0c8cde70757aa14f9501e5',
   'ability/색채이론':'6c58f3f2861df93f4183898b5f6a4f0d7764180de65d8f5d18c12ca0c2be52f9',
   'ability/에어록':'b8873228d1f48ab3e9cb68c2932319133ebd1188a828c56528ab64c7ca29e599',
   'ability/예지몽':'601320b479c70a5f4d160f95d4db5bd31063ae83e4054ce9aa8ce4868ee7dac4',
   'ability/위협':'2105807a959c8dfcc0dcd55c96b471cf6568775fe50113eac29a6cd5e5360002',
   'ability/정원사':'76f5a13bbe53b382c5bb5ba107609d16876eeeaad74a0fd8c12e6154791098d6',
   'ability/죽음저항-playtest':'2a435378f78b157c21cb476ee88775c2808eec770dddb646302d3049cc11b8c8'}
  policy=NATIVE.policy(self.r);self.assertEqual(set(policy['sources']),set(expected))
  with (ROOT/'input/db/abilities.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
  for source,digest in expected.items():
   row=policy['sources'][source];actual=hashlib.sha256(json.dumps(rows[row['record']-1],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
   self.assertEqual(actual,digest);self.assertEqual(NATIVE.registration(self.r,source)['source_id'],source)

 def test_threat_pays_swift_once_per_encounter_and_changes_actual_attack_stage(self):
  user=self.pokemon('threat-user','위협',pos=(3,3));target=self.pokemon('threat-target',None,pos=(7,3),side='wild')
  e=self.engine(user,target);self.turn(e,user);result=e.activate_ability(user,'위협',target)
  self.assertEqual((result['source'],target.stages['atk'],user.budget['swift']),('ability/위협',-1,0))
  before=deepcopy((user.spec,user.budget,target.stages,e.log_lines))
  with self.assertRaises(ValueError):e.activate_ability(user,'위협',target)
  self.assertEqual(before,(user.spec,user.budget,target.stages,e.log_lines));self.valid(e)

 def test_death_resistance_uses_independent_three_injury_daily_ledger(self):
  user=self.pokemon('death-user','죽음저항 [Playtest]',pos=(2,2));e=self.engine(user)
  e.gm.set_injuries(user,value=4,reason='actual severe injuries');e.gm.set_hp(user,value=1,reason='actual damaged HP')
  self.turn(e,user,[user]);ordinary=INJURY.healed_today(user);tick=e.tick(user)
  result=e.activate_ability(user,'죽음저항 [Playtest]',(user,{'count':3}))
  self.assertEqual((result['details']['injuries'],user.injuries,INJURY.healed_today(user)),(3,1,ordinary))
  self.assertEqual(user.hp,min(user.max_hp,1+tick*3));self.assertEqual(INJURY.exempt_remaining(user,'ability/죽음저항-playtest',3),0)
  before=deepcopy((user.spec,user.hp,user.injuries,user.budget))
  with self.assertRaises(ValueError):e.activate_ability(user,'죽음저항 [Playtest]',(user,{'count':1}))
  self.assertEqual(before,(user.spec,user.hp,user.injuries,user.budget));self.valid(e)

 def test_forewarn_reveals_highest_damage_move_and_penalizes_only_that_move_until_encounter_end(self):
  user=self.pokemon('forewarn-user','예지몽',pos=(2,2));target=self.pokemon('forewarn-target',None,moves=('몸통박치기','화염방사'),pos=(3,2),side='wild')
  e=self.engine(user,target);e.gm.set_move(target,'move/몸통박치기',reason='actual learned Move');e.gm.set_move(target,'move/화염방사',reason='actual learned Move')
  self.turn(e,user);result=e.activate_ability(user,'예지몽',target)
  self.assertEqual(result['details']['move_id'],'move/화염방사')
  self.assertEqual(result['details']['move_ids'],['move/화염방사'])
  flame=self.r.move('move/화염방사');tackle=self.r.move('move/몸통박치기')
  self.assertEqual(EXT.accuracy_hook(e,target,user,flame,flame,{})[2],-2)
  self.assertEqual(EXT.accuracy_hook(e,target,user,tackle,tackle,{})[2],0)
  e.end_of_turn(user);e.end_encounter([user,target],round_elapsed_seconds=0)
  self.assertFalse(any(x.get('ability_native')=='ability/예지몽' for x in target.registry));self.valid(e)

 def test_forewarn_reveals_all_ties_and_native_accuracy_excludes_same_type_lower_move(self):
  user=self.pokemon('forewarn-ties-user','예지몽',pos=(2,2))
  target=self.pokemon('forewarn-ties-target',None,pos=(3,2),side='wild')
  e=self.engine(user,target)
  tied=['move/번개펀치','move/불꽃펀치'];lower='move/불꽃세례'
  for mid in tied+[lower]:e.gm.set_move(target,mid,reason='actual learned Move for tied damage comparison')
  e.gm.set_types(target,['불꽃'],reason='actual STAB differs; Forewarn uses the selected printed DB policy')
  self.turn(e,user)
  for mid in tied+[lower]:
   self.assertTrue(e.accuracy_check(target,user,self.r.move(mid),waive=True,fixed_roll=2)[0])
  rng=e.rng.getstate();budgets=deepcopy(user.budget)
  result=e.activate_ability(user,'예지몽',target)
  self.assertEqual(result['details']['move_ids'],tied)
  self.assertEqual(result['details']['damage_base'],8)
  self.assertIsNone(result['details']['move_id'])
  self.assertEqual((e.rng.getstate(),user.budget),(rng,budgets))
  for mid in tied:
   self.assertFalse(e.accuracy_check(target,user,self.r.move(mid),waive=True,fixed_roll=2)[0])
  self.assertTrue(e.accuracy_check(target,user,self.r.move(lower),waive=True,fixed_roll=2)[0])
  self.valid(e)

 def test_forewarn_legacy_tie_hint_cannot_narrow_revelation_and_wrong_hint_is_atomic(self):
  from native_scenario_fixture import assert_rejected_unchanged
  user=self.pokemon('forewarn-hint-user','예지몽',pos=(2,2))
  target=self.pokemon('forewarn-hint-target',None,pos=(3,2),side='wild')
  e=self.engine(user,target)
  tied=['move/10만볼트','move/화염방사']
  for mid in tied+['move/몸통박치기']:e.gm.set_move(target,mid,reason='actual known Forewarn target Move')
  self.turn(e,user)
  assert_rejected_unchanged(e,lambda:e.activate_ability(user,'예지몽',(target,{'move_id':'move/몸통박치기'})),reason_pattern='not strongest')
  result=e.activate_ability(user,'예지몽',(target,{'move_id':'move/화염방사'}))
  self.assertEqual(result['details']['move_ids'],tied)
  for mid in tied:
   self.assertFalse(e.accuracy_check(target,user,self.r.move(mid),waive=True,fixed_roll=2)[0])
  assert_rejected_unchanged(e,lambda:e.activate_ability(user,'예지몽',target),reason_pattern='frequency exhausted')
  self.valid(e)

 def test_forewarn_trainer_ties_survive_native_restore_and_json_then_expire_together(self):
  from native_scenario_fixture import assert_rejected_unchanged
  user=self.pokemon('forewarn-cold-user','예지몽',pos=(2,2))
  target=self.trainer('forewarn-cold-target',pos=(3,2),side='wild')
  e=self.engine(user,target);tied=['move/10만볼트','move/화염방사']
  for mid in tied:e.gm.set_move(target,mid,reason='actual Trainer learned Move')
  self.turn(e,user);result=e.activate_ability(user,'예지몽',target)
  e.gm.snapshot('all-revealed');e.end_of_turn(user);e.end_encounter([user,target],round_elapsed_seconds=0)
  e.gm.restore('all-revealed',reason='restore actual Forewarn encounter effects')
  n=Engine.import_state(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
  user2=next(c for c in n.everyone if c.entity_id==user.entity_id)
  target2=next(c for c in n.everyone if c.entity_id==target.entity_id)
  self.assertEqual(user2.spec[NATIVE.HISTORY][-1]['details']['move_ids'],tied)
  for mid in tied:
   self.assertFalse(n.accuracy_check(target2,user2,self.r.move(mid),waive=True,fixed_roll=2)[0])
  assert_rejected_unchanged(n,lambda:n.activate_ability(user2,'예지몽',target2),reason_pattern='frequency exhausted')
  n.end_of_turn(user2);n.end_encounter([user2,target2],round_elapsed_seconds=0)
  self.assertFalse(any(x.get('_state_source')==result['details']['grant_source'] for x in target2.registry))
  for mid in tied:
   move=self.r.move(mid);self.assertEqual(EXT.accuracy_hook(n,target2,user2,move,move,{})[2],0)
  assert_rejected_unchanged(n,lambda:n.activate_ability(user2,'예지몽',target2),reason_pattern='frequency exhausted')
  self.valid(n)

 def test_forewarn_no_damage_dice_target_rejects_before_scene_cost(self):
  from native_scenario_fixture import assert_rejected_unchanged
  user=self.pokemon('forewarn-status-user','예지몽',pos=(2,2))
  target=self.trainer('forewarn-status-target',pos=(3,2),side='wild')
  e=self.engine(user,target)
  for mid in ('move/튀어오르기','move/용의분노','move/풀묶기','move/매그니튜드'):
   e.gm.set_move(target,mid,reason='actual Move without a numeric printed DB')
  self.assertIn('struggle',target.moves)
  self.turn(e,user)
  assert_rejected_unchanged(e,lambda:e.activate_ability(user,'예지몽',target),reason_pattern='no damaging Move')
  e.gm.set_move(target,'move/흡수',reason='actual later learned DB2 Move; Struggle is not a learned Move')
  result=e.activate_ability(user,'예지몽',target)
  self.assertEqual(result['details']['move_ids'],['move/흡수']);self.valid(e)

 def test_sunset_charges_from_actual_sun_then_spends_daily_swift_for_scene_stage_and_accuracy(self):
  user=self.pokemon('sunset-user','노을 [Playtest]',moves=('몸통박치기',),pos=(2,2));e=self.engine(user)
  e.gm.set_weather('sunny',reason='actual sunlight');self.turn(e,user,[user])
  charged=e.activate_ability(user,'노을 [Playtest]',(user,{'mode':'charge'}))
  self.assertEqual((charged['operation'],user.budget['swift']),('radiant_charge',0))
  quota=deepcopy(user.spec['frequency_state']['activations']['ability/노을-playtest'])
  self.assertEqual((quota['kind'],quota['used']),('daily',1))
  e.end_of_turn(user);e.end_round();self.turn(e,user,[user])
  spent=e.activate_ability(user,'노을 [Playtest]',(user,{'mode':'spend'}));move=self.r.move('move/몸통박치기')
  self.assertEqual(user.spec['frequency_state']['activations']['ability/노을-playtest'],quota)
  self.assertEqual((user.stages['atk'],user.budget['swift'],EXT.accuracy_hook(e,user,user,move,move,{})[2]),(2,0,2))
  self.assertEqual(spent['details']['accuracy'],2);e.end_of_turn(user);e.end_scene([user],round_elapsed_seconds=0)
  self.assertFalse(any(x.get('ability_native')=='ability/노을-playtest' for x in user.registry));self.valid(e)

 def test_sunset_daily_charge_survives_restore_and_spend_does_not_recharge(self):
  from native_scenario_fixture import assert_rejected_unchanged
  user=self.pokemon('sunset-restore','노을 [Playtest]',pos=(2,2));e=self.engine(user)
  e.gm.set_weather('sunny',reason='observed sunlight outside battle')
  e.activate_ability(user,'노을 [Playtest]',(user,{'mode':'charge'}))
  self.assertEqual(user.spec['frequency_state']['activations']['ability/노을-playtest']['used'],1)
  e.gm.snapshot('radiant');self.turn(e,user,[user]);e.activate_ability(user,'노을 [Playtest]',(user,{'mode':'spend'}))
  e.gm.restore('radiant',reason='restore unspent actual charge')
  n=Engine.import_state(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
  restored=next(c for c in n.everyone if c.entity_id==user.entity_id);self.turn(n,restored,[restored])
  n.activate_ability(restored,'노을 [Playtest]',(restored,{'mode':'spend'}))
  assert_rejected_unchanged(n,lambda:n.activate_ability(restored,'노을 [Playtest]',(restored,{'mode':'charge'})),reason_pattern='frequency exhausted')
  assert_rejected_unchanged(n,lambda:n.activate_ability(restored,'노을 [Playtest]',(restored,{'mode':'spend'})),reason_pattern='no Radiant')
  self.assertEqual(restored.spec['frequency_state']['activations']['ability/노을-playtest']['used'],1);self.valid(n)

 def test_sunset_charge_rejects_without_sun_or_available_action_before_daily_cost(self):
  from native_scenario_fixture import assert_rejected_unchanged
  import turn as TURN
  user=self.pokemon('sunset-reject','노을 [Playtest]',pos=(2,2));e=self.engine(user);self.turn(e,user,[user])
  assert_rejected_unchanged(e,lambda:e.activate_ability(user,'노을 [Playtest]',(user,{'mode':'charge'})),reason_pattern='sunlight')
  e.gm.set_weather('sunny',reason='actual sunlight')
  self.assertTrue(TURN.spend(e,user,'standard','actual earlier action'));self.assertTrue(TURN.spend(e,user,'swift','actual earlier action'))
  assert_rejected_unchanged(e,lambda:e.activate_ability(user,'노을 [Playtest]',(user,{'mode':'charge'})),reason_pattern='action unavailable')
  self.assertNotIn('ability/노을-playtest',user.spec['frequency_state']['activations'])

 def test_frighten_moves_with_highest_capability_and_applies_one_round_slow_with_target_scene_limit(self):
  trainer=self.trainer('frightened-trainer',pos=(12,5));user=self.pokemon('frighten-user','겁주기',pos=(5,5));target=self.pokemon('frighten-target',None,pos=(6,5),side='wild',extra={'trainer_id':trainer.entity_id,'movement':{'land':4}})
  e=self.engine(trainer,user,target);self.turn(e,user,[user,target,trainer]);result=e.activate_ability(user,'겁주기',target)
  from grid import cheb
  self.assertEqual(result['details']['displacement']['moved'],3);self.assertEqual(cheb(target.pos,trainer.pos),3);self.assertEqual(cheb(target.pos,user.pos),4);self.assertIn('둔화',target.conditions)
  before=deepcopy((user.spec,user.budget,target.pos,target.conditions))
  with self.assertRaises(ValueError):e.activate_ability(user,'겁주기',target)
  self.assertEqual(before,(user.spec,user.budget,target.pos,target.conditions));e.end_of_turn(user);e.end_encounter([user,target,trainer],round_elapsed_seconds=0)
  self.assertNotIn('둔화',target.conditions);self.valid(e)

 def test_frighten_uses_current_land_not_unavailable_swim_or_burrow_and_keeps_speed_stages(self):
  trainer=self.trainer('frighten-dry-trainer',pos=(12,5))
  user=self.pokemon('frighten-dry-user','겁주기',pos=(5,5))
  target=self.pokemon('frighten-dry-target',None,pos=(6,5),side='wild',
   extra={'trainer_id':trainer.entity_id,'movement':{'land':4,'swim':9,'burrow':10},'initial_stages':{'spe':-4}})
  other=self.pokemon('frighten-dry-other',None,pos=(6,7),side='wild',extra={'movement':{'land':2}})
  third=self.pokemon('frighten-dry-third',None,pos=(6,8),side='wild',extra={'movement':{'land':2}})
  e=self.engine(trainer,user,target,other,third);self.turn(e,user)
  result=e.activate_ability(user,'겁주기',target)
  self.assertEqual((result['details']['source_policy'],result['details']['movement_mode'],result['details']['movement_value']),
                   ('kr_csv_r0015_movement','land',2))
  from grid import cheb
  self.assertEqual((result['details']['displacement']['moved'],cheb(target.pos,user.pos),
                    cheb(target.pos,trainer.pos),target.stages['spe']),(2,3,4,-4))
  self.assertIn('둔화',target.conditions)
  e.end_of_turn(user);e.end_round();self.turn(e,user)
  second=e.activate_ability(user,'겁주기',(other,{'source_policy':'kr_csv_r0015_movement'}))
  self.assertEqual(second['details']['source_reference'],'C2CSV-ABILITY-R0015')
  e.end_of_turn(user);e.end_round();self.turn(e,user)
  from native_scenario_fixture import assert_rejected_unchanged
  assert_rejected_unchanged(e,lambda:e.activate_ability(user,'겁주기',third),reason_pattern='frequency exhausted')
  self.valid(e)

 def test_frighten_swim_stops_at_real_water_boundary_and_never_uses_dry_route(self):
  import map_terrain as TERRAIN
  trainer=self.trainer('frighten-water-trainer',pos=(12,5))
  user=self.pokemon('frighten-water-user','겁주기',pos=(5,5))
  target=self.pokemon('frighten-water-target',None,pos=(6,5),side='wild',
   extra={'trainer_id':trainer.entity_id,'movement':{'land':8,'swim':7}})
  e=self.engine(trainer,user,target)
  TERRAIN.observe(e,[(6,5),(7,5),(8,5)],base='underwater',reason='observed short water channel')
  self.turn(e,user);result=e.activate_ability(user,'겁주기',target)
  path=result['details']['displacement']['path']
  self.assertEqual(result['details']['movement_mode'],'swim')
  self.assertEqual((result['details']['displacement']['moved'],target.pos),(2,(8,5)))
  self.assertTrue(all(TERRAIN.base_at(e.grid,point)=='underwater' for point in path));self.valid(e)

 def test_frighten_terrain_path_uses_real_diagonal_and_slow_distance_toward_trainer(self):
  import map_terrain as TERRAIN
  import movement_actions as MOVEMENT
  trainer=self.trainer('frighten-distance-trainer',pos=(12,8))
  user=self.pokemon('frighten-distance-user','겁주기',pos=(4,4))
  target=self.pokemon('frighten-distance-target',None,pos=(5,5),side='wild',extra={'trainer_id':trainer.entity_id,'movement':{'land':8}})
  e=self.engine(trainer,user,target)
  TERRAIN.observe(e,[(6,6),(7,7),(8,8)],base='regular',slow=True,reason='observed slow diagonal shortcut')
  TERRAIN.observe(e,[(6,5),(7,5)],base='underwater',reason='water blocks the direct dry east route')
  self.turn(e,user);result=e.activate_ability(user,'겁주기',target)
  path=result['details']['displacement']['path'];cost=0;diagonals=0
  for origin,destination in zip(path,path[1:]):
   step,diagonals=MOVEMENT.step_cost(origin,destination,diagonals)
   cost+=step*TERRAIN.slow_multiplier(e,target,destination,'land')
   self.assertTrue(TERRAIN.can_travel(e,target,destination,'land'))
  self.assertLessEqual(cost,3)
  from grid import cheb
  self.assertGreater(cheb(target.pos,user.pos),1)
  self.assertLess(cheb(target.pos,trainer.pos),7);self.valid(e)

 def test_frighten_explicit_core105_choice_changes_only_speed_with_original_scene_frequency(self):
  from native_scenario_fixture import assert_rejected_unchanged
  user=self.pokemon('frighten-core-user','겁주기',pos=(5,5))
  target=self.pokemon('frighten-core-target',None,pos=(6,5),side='wild')
  other=self.trainer('frighten-core-other',pos=(7,5),side='wild')
  e=self.engine(user,target,other);self.turn(e,user)
  before=target.pos
  assert_rejected_unchanged(e,lambda:e.activate_ability(user,'겁주기',(target,{'source_policy':'unreviewed'})),reason_pattern='unknown Frighten source policy')
  result=e.activate_ability(user,'겁주기',(target,{'source_policy':'en_core105_speed_stages'}))
  self.assertEqual((result['details']['source_policy'],target.pos,target.stages['spe'],user.budget['swift']),
                   ('en_core105_speed_stages',before,-2,0))
  self.assertNotIn('둔화',target.conditions)
  e.end_of_turn(user);e.end_round();self.turn(e,user)
  assert_rejected_unchanged(e,lambda:e.activate_ability(user,'겁주기',(other,{'source_policy':'en_core105_speed_stages'})),reason_pattern='frequency exhausted')
  self.assertEqual((other.stages['spe'],other.pos),(0,(7,5)));self.valid(e)

 def test_frighten_selected_sky_and_levitate_reach_actual_entry_grounding_before_later_land(self):
  import movement_actions as MOVEMENT
  import move_state as MOVES
  import turn as TURN
  for mode in ('sky','levitate'):
   with self.subTest(mode=mode):
    trainer=self.trainer('frighten-air-trainer-'+mode,pos=(12,5),side='wild')
    user=self.pokemon('frighten-air-user-'+mode,'겁주기',pos=(5,5))
    setter=Combatant(self.r,build_pokemon(self.r,'클레피',20,moves=['압정뿌리기'],abilities=[],
     pos=(4,4),side='party',extra={'id':'frighten-air-spikes-'+mode}))
    target=self.pokemon('frighten-air-target-'+mode,None,pos=(6,5),side='wild',
     extra={'trainer_id':trainer.entity_id,'movement':{'land':4,mode:8}})
    e=self.engine(setter,trainer,user,target);self.turn(e,setter,count=30)
    self.assertEqual(MOVES.classifications(self.r,setter.spec,require_routes=True)['move/압정뿌리기'],'natural')
    cells=[(x,y) for x in range(7,11) for y in (5,6)]
    e.use_move_on(setter,setter,'move/압정뿌리기',[setter,user,target,trainer],aim=cells)
    e.end_of_turn(setter);e.start_of_turn(user,initiative_count=20)
    hp=target.hp;result=e.activate_ability(user,'겁주기',target)
    from grid import cheb
    self.assertEqual((result['details']['movement_mode'],cheb(target.pos,user.pos),
                      cheb(target.pos,trainer.pos),target.hp),(mode,4,3,hp))
    self.assertTrue(target.airborne)
    e.end_of_turn(user);e.start_of_turn(target,initiative_count=10)
    self.assertTrue(TURN.spend(e,target,'shift','actual later land entry',movement=True))
    landed=MOVEMENT.follow_paid_path(e,target,[(10,5)],mode='land',maximum_distance=2)
    self.assertEqual(landed['steps'],1);self.assertFalse(target.airborne)
    self.assertEqual(target.hp,hp-max(1,target.max_hp//10));self.valid(e)

 def test_air_lock_clears_and_blocks_weather_while_active_then_expires_without_sustain(self):
  user=self.pokemon('air-user','에어록',pos=(2,2));e=self.engine(user);e.gm.set_weather('sunny',reason='actual weather')
  self.turn(e,user,[user]);e.activate_ability(user,'에어록',(user,{'mode':'start'}));self.assertIsNone(e.weather)
  with self.assertRaises(ValueError):e.gm.set_weather('rain',reason='blocked by Air Lock')
  e.end_of_turn(user);e.end_round();e.start_round([user]);e.start_of_turn(user,initiative_count=20)
  e.activate_ability(user,'에어록',(user,{'mode':'sustain'}));self.assertEqual(user.budget['swift'],0)
  e.end_of_turn(user);e.end_round();e.start_round([user]);e.start_of_turn(user,initiative_count=20);e.end_of_turn(user);e.end_round()
  e.gm.set_weather('rain',reason='Air Lock was not sustained');self.assertEqual(e.weather,'rain');self.valid(e)

 def test_lunchbox_consumes_one_completed_food_receipt_and_stacks_sourced_temporary_hp(self):
  user=self.pokemon('lunch-user','도시락통 [Playtest]',pos=(2,2),extra={'items':{'초코바':1}});e=self.engine(user)
  buff=e.use_item(user,'초코바',user,duration_minutes=1,duration_reason='actual meal duration');user.hp=1
  e.consume_food_buff(user,buff_id=buff['buff_id'],action_kind='free',action_reason='actual completed food benefit')
  TEMP.grant(e,user,3);before=user.temp_hp;result=e.activate_ability(user,'도시락통 [Playtest]',(user,{'receipt_sequence':1}))
  self.assertEqual(user.temp_hp,max(before,e.tick(user)));self.assertEqual(result['details']['temporary_hp'],max(0,e.tick(user)-before))
  event=user.custom_conditions[TEMP.STATE]['grant_events'][-1];self.assertTrue(event['stack']);self.assertEqual(event['provenance']['food_receipt'],1)
  before_state=deepcopy((user.spec,user.temp_hp,user.custom_conditions))
  with self.assertRaises(ValueError):e.activate_ability(user,'도시락통 [Playtest]',(user,{'receipt_sequence':1}))
  self.assertEqual(before_state,(user.spec,user.temp_hp,user.custom_conditions));self.valid(e)

 def test_designer_replaces_one_owned_two_type_garment_and_native_resistance_consumer_reads_it(self):
  user=self.pokemon('designer-user','디자이너',moves=('화염방사','물대포'),pos=(2,2));e=self.engine(user)
  first=e.activate_ability(user,'디자이너',(user,{'types':['불꽃','물']}));self.assertEqual({x['types'][0] for x in user.modifiers if x.get('ability_native')=='ability/디자이너'},{'불꽃','물'})
  flame=self.r.move('move/화염방사');self.assertEqual(__import__('effects').passive_damage_mods(e,user,user,flame,{} )[2],1)
  second=e.activate_ability(user,'디자이너',(user,{'types':['풀','전기']}));self.assertNotEqual(first['details']['grant_source'],second['details']['grant_source'])
  self.assertEqual({x['types'][0] for x in user.modifiers if x.get('ability_native')=='ability/디자이너'},{'풀','전기'});self.valid(e)

 def test_color_theory_applies_one_immutable_birth_roll_as_owned_base_stats(self):
  user=self.pokemon('color-user','색채이론',pos=(2,2));e=self.engine(user);before=dict(user.stats)
  result=e.activate_ability(user,'색채이론',(user,{'birth_roll':2,'reason':'recorded actual birth d12'}))
  self.assertEqual((user.stats['atk']-before['atk'],user.stats['def']-before['def']),(3,3));self.assertEqual(result['details']['color'],'빨강-주황')
  snapshot=deepcopy((user.spec,user.stats))
  with self.assertRaises(ValueError):e.activate_ability(user,'색채이론',(user,{'birth_roll':3,'reason':'cannot alter birth'}))
  self.assertEqual(snapshot,(user.spec,user.stats));GRANTS.replace_baseline(e,user,'abilities',[])
  self.assertEqual((user.stats['atk'],user.stats['def']),(before['atk'],before['def']))
  GRANTS.replace_baseline(e,user,'abilities',['색채이론'])
  self.assertEqual((user.stats['atk']-before['atk'],user.stats['def']-before['def']),(3,3));self.valid(e)

 def test_gardener_adds_one_ability_backed_fertilizer_application_per_plant_day_without_item_debit(self):
  extra={'edges':['edge/원예가'],'skills':{'생존':'숙련'},'items':{'버치열매':1}}
  user=self.pokemon('gardener-user','정원사',pos=(2,2),extra=extra);e=self.engine(user)
  declaration=json.loads((ROOT/'data/examples/cultivation-growth.json').read_text(encoding='utf-8'))[0]
  e.observe_cultivation_site(user,'actual:site',capacity=2,soil_quality=0,soft_soil=True,allows_growth=True,reason='actual two-plant patch')
  e.plant_growth(user,declaration,plant_id='plant:first',site_id='actual:site',reason='actual admitted seed and site')
  result=e.activate_ability(user,'정원사',(user,{'plant_id':'plant:first'}));plant=user.spec['plants']['plant:first'];application=plant['mulch_applications'][0]
  self.assertEqual((result['details']['soil_delta'],application['payment']['count'],e.growth_status(user,'plant:first')['fertilizer_bonus']),(1,0,1))
  self.assertNotIn('비료',user.spec['items']);before=deepcopy((user.spec,user._action_history))
  with self.assertRaises(ValueError):e.activate_ability(user,'정원사',(user,{'plant_id':'plant:first'}))
  self.assertEqual(before,(user.spec,user._action_history));self.valid(e)


if __name__=='__main__':unittest.main(verbosity=2)
