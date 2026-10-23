"""Exact ten-Ability native producers, consumers, costs and lifetimes."""
from copy import deepcopy
from pathlib import Path
import csv,hashlib,json,sys,unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
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
  flame=self.r.move('move/화염방사');tackle=self.r.move('move/몸통박치기')
  self.assertEqual(EXT.accuracy_hook(e,target,user,flame,flame,{})[2],-2)
  self.assertEqual(EXT.accuracy_hook(e,target,user,tackle,tackle,{})[2],0)
  e.end_of_turn(user);e.end_encounter([user,target],round_elapsed_seconds=0)
  self.assertFalse(any(x.get('ability_native')=='ability/예지몽' for x in target.registry));self.valid(e)

 def test_sunset_charges_from_actual_sun_then_spends_daily_swift_for_scene_stage_and_accuracy(self):
  user=self.pokemon('sunset-user','노을 [Playtest]',moves=('몸통박치기',),pos=(2,2));e=self.engine(user)
  e.gm.set_weather('sunny',reason='actual sunlight');charged=e.activate_ability(user,'노을 [Playtest]',(user,{'mode':'charge'}))
  self.assertEqual(charged['operation'],'radiant_charge');self.turn(e,user,[user])
  spent=e.activate_ability(user,'노을 [Playtest]',(user,{'mode':'spend'}));move=self.r.move('move/몸통박치기')
  self.assertEqual((user.stages['atk'],user.budget['swift'],EXT.accuracy_hook(e,user,user,move,move,{})[2]),(2,0,2))
  self.assertEqual(spent['details']['accuracy'],2);e.end_of_turn(user);e.end_scene([user],round_elapsed_seconds=0)
  self.assertFalse(any(x.get('ability_native')=='ability/노을-playtest' for x in user.registry));self.valid(e)

 def test_frighten_moves_with_highest_capability_and_applies_one_round_slow_with_target_scene_limit(self):
  trainer=self.trainer('frightened-trainer',pos=(12,5));user=self.pokemon('frighten-user','겁주기',pos=(5,5));target=self.pokemon('frighten-target',None,pos=(6,5),side='wild',extra={'trainer_id':trainer.entity_id,'movement':{'land':4}})
  e=self.engine(trainer,user,target);self.turn(e,user,[user,target,trainer]);result=e.activate_ability(user,'겁주기',target)
  from grid import cheb
  self.assertEqual(result['details']['displacement']['moved'],3);self.assertEqual(cheb(target.pos,trainer.pos),3);self.assertEqual(cheb(target.pos,user.pos),4);self.assertIn('둔화',target.conditions)
  before=deepcopy((user.spec,user.budget,target.pos,target.conditions))
  with self.assertRaises(ValueError):e.activate_ability(user,'겁주기',target)
  self.assertEqual(before,(user.spec,user.budget,target.pos,target.conditions));e.end_of_turn(user);e.end_encounter([user,target,trainer],round_elapsed_seconds=0)
  self.assertNotIn('둔화',target.conditions);self.valid(e)

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
  self.assertEqual(user.temp_hp,before+e.tick(user));self.assertEqual(result['details']['temporary_hp'],e.tick(user))
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
