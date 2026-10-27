"""Native crafting integration; DOMAIN074 remains partial while planter variants conflict."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'));sys.path.insert(0,str(ROOT/'tools'))
from engine import Rules,Engine,Combatant
from contest import ContestRules,ContestEngine
import test_category3_pokemon_activities as _fixture_test_category3_pokemon_activities
import crafting_activities as C
class CraftTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core');cls.contest_rules=ContestRules(str(ROOT),ruleset='core')
 setUp=_fixture_test_category3_pokemon_activities.PokemonActivityTests.setUp
 actor=_fixture_test_category3_pokemon_activities.PokemonActivityTests.actor
 act=_fixture_test_category3_pokemon_activities.PokemonActivityTests.act
 state=_fixture_test_category3_pokemon_activities.PokemonActivityTests.state
 own=_fixture_test_category3_pokemon_activities.PokemonActivityTests.own
 def dowsing(self,rank='숙련'):
  self.a.spec['items']['다우징 로드']=1;self.a.spec['skills']['오컬트학']=rank
 def poffins(self):
  self.a.spec['items'].update({'포핀 혼합기':1,'버치열매':3,'유루열매':2});self.a.spec['cooking_materials_value']=1000
  return self.act('cook_poffins',ingredients={'버치열매':1},minutes=10,reason='GM recipe duration')['batch']['id']
 def test_dowsing_four_boundary_six_yields_before_optional_reroll_and_ten_minutes(self):
  self.dowsing();result=self.act('dowse',outdoors=True,fixed={'0':3,'1':4,'2':5,'3':6})
  self.assertEqual(sum(result['gained'].values()),3);self.assertEqual(self.e.elapsed_seconds,600);self.assertEqual(result['remaining_uses'],1)
  self.assertFalse(result['results'][-1]['rerolled']);self.assertEqual(sum(self.a.spec['shards'].values()),3)
 def test_dowsing_individual_six_rerolls_can_chain_and_other_six_can_stop(self):
  self.dowsing();result=self.act('dowse',outdoors=True,reroll_sixes={'0','0.1'},fixed={'0':6,'1':6,'2':2,'3':1,'0.1':6,'0.1.1':4})
  self.assertEqual(sum(result['gained'].values()),4);self.assertEqual(len(result['results']),6);self.assertFalse(result['results'][1]['rerolled'])
 def test_dowsing_rock_and_acquired_gm_approved_stunt_each_add_one_die(self):
  self.dowsing();self.a.spec['edges']=['edge/고난이도-스킬'];self.a.spec['edge_choices']={'고난이도 스킬':[{'skill':'오컬트학','use':'다우징','gm_approved':True}]}
  result=self.act('dowse',outdoors=True,rock_or_sand=True,fixed={str(i):4 for i in range(6)})
  self.assertEqual(result['pool'],6);self.assertEqual(sum(result['gained'].values()),6)
 def test_dowsing_virtuoso_rank8_and_daily_reset(self):
  self.dowsing('달인');self.a.spec['edges']=['edge/거장'];self.a.spec['edge_choices']={'거장':['오컬트학']}
  for _ in range(4):self.assertEqual(self.act('dowse',outdoors=True,fixed={str(i):1 for i in range(8)})['pool'],8)
  before=self.state()
  with self.assertRaises(ValueError):self.act('dowse',outdoors=True)
  self.assertEqual(before,self.state());self.a.spec.setdefault('frequency_state',{})['day']=1
  self.assertEqual(self.act('dowse',outdoors=True,fixed={str(i):1 for i in range(8)})['remaining_uses'],3)
 def test_dowsing_tool_outdoor_stunt_and_invalid_branch_do_not_spend(self):
  self.dowsing();self.a.spec['items']['다우징 로드']=0;before=self.state()
  with self.assertRaises(ValueError):self.act('dowse',outdoors=True)
  self.assertEqual(before,self.state());self.a.spec['items']['다우징 로드']=1
  for options in ({'outdoors':False},{'outdoors':True,'fixed':{'0':7,'1':1,'2':1,'3':1}},{'outdoors':True,'reroll_sixes':{'0'},'fixed':{'0':4,'1':1,'2':1,'3':1}}):
   before=self.state()
   with self.assertRaises(ValueError):self.act('dowse',**options)
   self.assertEqual(before,self.state())
 def test_poffin_500_owned_ingredients_create_two_then_actual_consumption_changes_contest(self):
  batch=self.poffins();self.assertEqual(self.a.spec['items']['버치열매'],2);self.assertEqual(self.a.spec['cooking_materials_value'],650)
  self.assertEqual(self.a.spec['poffin_batches'][batch]['count'],2)
  contest=ContestEngine(self.contest_rules);before=contest.stat_pool_from_combatant(self.p,smart_stat_policy='ptk-literal-defense')
  self.act('feed_poffin',batch_id=batch,target=self.p,minutes=1,reason='GM meal duration')
  after=contest.stat_pool_from_combatant(self.p,smart_stat_policy='ptk-literal-defense');self.assertEqual(after['근사함'],before['근사함']+1)
  self.assertEqual(self.a.spec['poffin_batches'][batch]['count'],1);self.assertEqual(self.p.spec['poffin_consumption'][0]['batch_id'],batch)
 def test_poffin_dominant_berry_counts_and_tie_needs_explicit_gm_choice(self):
  self.poffins();result=self.act('cook_poffins',ingredients={'버치열매':2,'유루열매':1},minutes=10,reason='GM duration');self.assertEqual(result['batch']['contest_stat'],'근사함')
  self.a.spec['items']['버치열매']=1;before=self.state()
  with self.assertRaises(ValueError):self.act('cook_poffins',ingredients={'버치열매':1,'유루열매':1},minutes=10,reason='GM duration')
  self.assertEqual(before,self.state())
  result=self.act('cook_poffins',ingredients={'버치열매':1,'유루열매':1},minutes=10,reason='GM tie adjudication',tie_choice='아름다움');self.assertEqual(result['batch']['contest_stat'],'아름다움')
 def test_poffin_refusal_allowance_and_six_limit(self):
  batch=self.poffins();before=self.state();self.act('feed_poffin',batch_id=batch,target=self.p,minutes=1,reason='GM duration',accepted=False);self.assertEqual(before,self.state())
  self.p.level=4;self.p.spec['poffins']=['아름다움'];before=self.state()
  with self.assertRaises(ValueError):self.act('feed_poffin',batch_id=batch,target=self.p,minutes=1,reason='GM duration')
  self.assertEqual(before,self.state());self.p.level=25;self.p.spec['poffins']=['아름다움']*6
  result=self.act('feed_poffin',batch_id=batch,target=self.p,minutes=1,reason='GM duration');self.assertFalse(result['effective']);self.assertEqual(len(self.p.spec['poffins']),6)
 def test_dismantle_ice_heal_200_becomes_100_medical_scrap_then_crafts_potion(self):
  self.a.spec['items'].update({'얼음상태치료제':1,'화학 세트':1});result=self.act('dismantle',item='얼음상태치료제')
  self.assertEqual(result['category'],'약');self.assertEqual(result['value'],100);self.assertEqual(self.a.spec['items']['얼음상태치료제'],0)
  self.apothecary();result=self.act('craft_item',item='상처약',scrap_value=100,minutes=10,reason='GM duration')
  self.assertEqual(result['money_spent'],0);self.assertEqual(self.a.spec['crafting_scrap']['약'],0);self.assertEqual(self.a.spec['items']['상처약'],1)
 def test_scrap_wrong_category_unacquired_recipe_and_damaged_item_refused(self):
  self.a.spec['items'].update({'몬스터볼 공구함':1,'얼음상태치료제':1});self.a.spec['crafting_scrap']={'약':100};self.own('basic_balls');before=self.state()
  with self.assertRaises(ValueError):self.act('craft_item',item='몬스터볼',scrap_value=100,minutes=10,reason='GM duration')
  self.assertEqual(before,self.state());self.a.spec['crafting_scrap']['몬스터볼']=100;self.a.spec['edges']=[];before=self.state()
  with self.assertRaises(ValueError):self.act('craft_item',item='몬스터볼',scrap_value=100,minutes=10,reason='GM duration')
  self.assertEqual(before,self.state());self.a.spec['damaged_items']=['얼음상태치료제'];before=self.state()
  with self.assertRaises(ValueError):self.act('dismantle',item='얼음상태치료제')
  self.assertEqual(before,self.state())
 def test_scrap_partial_payment_consumes_actual_money_and_tool_required(self):
  self.own('basic_balls');self.a.spec['crafting_scrap']={'몬스터볼':75};self.a.spec['money']=100;before=self.state()
  with self.assertRaises(ValueError):self.act('craft_item',item='슈퍼볼',scrap_value=75,minutes=10,reason='GM duration')
  self.assertEqual(before,self.state());self.a.spec['items']['몬스터볼 공구함']=1
  self.act('craft_item',item='슈퍼볼',scrap_value=75,minutes=10,reason='GM duration');self.assertEqual(self.a.spec['money'],0);self.assertEqual(self.a.spec['items']['슈퍼볼'],1)
 def apothecary(self):
  self.a.spec['classes']=['class/연구원'];self.a.spec['research_fields']=['약사','일반 지식'];self.a.spec['feats']=['약사'];self.a.spec['skills']['의학']='초보';self.a.spec['items']['화학 세트']=1;self.a.spec['money']=100
 def test_chemical_set_actual_potion_recipe_consumes_scrap_money_and_restores_hp(self):
  self.apothecary();self.a.spec['crafting_scrap']={'약':60};self.p.hp=1;self.act('craft_item',item='상처약',scrap_value=60,minutes=5,reason='GM Extended laboratory time')
  self.assertEqual(self.e.elapsed_seconds,300);self.assertEqual(self.a.spec['money'],60);self.assertEqual(self.a.spec['crafting_scrap']['약'],0);self.assertEqual(self.a.spec['items']['상처약'],1)
  self.e.use_item(self.a,'상처약',self.p);self.assertEqual(self.a.spec['items']['상처약'],0);self.assertEqual(self.p.hp,21)
 def test_apothecary_actual_field_feature_skill_tool_and_source_are_preconditions(self):
  self.apothecary()
  for key,value in [('classes',[]),('research_fields',['식물학','일반 지식']),('feats',[]),('skills',{'의학':'미숙'}),('items',{})]:
   old=deepcopy(self.a.spec[key]);self.a.spec[key]=value;before=self.state()
   with self.assertRaises(ValueError):self.act('craft_item',item='상처약',minutes=1,reason='GM duration')
   self.assertEqual(before,self.state());self.a.spec[key]=old
  original=self.e.r._selected_rule
  try:
   self.e.r._selected_rule=lambda uid, *args, **kwargs: uid + '/unsupported' if uid == C.RESEARCH_SOURCE else original(uid, *args, **kwargs);before=self.state()
   with self.assertRaises(ValueError):self.act('craft_item',item='상처약',minutes=1,reason='GM duration')
   self.assertEqual(before,self.state())
  finally:self.e.r._selected_rule=original
 def researcher_caretaker(self,canonical=False):
  from builder import build_pokemon
  self.apothecary();self.a.spec['feats']+=['feat/후원자','feat/스킬-트레이너']
  self.p=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',20,extra={'trainer_id':self.a.spec['id'],'skills':{'육상':4}}));self.e.gm.everyone=[self.a,self.p,self.q]
  self.a.spec['research_fields']=['약사','포켓몬 관리']
  if canonical:
   self.a.spec.pop('research_fields');self.a.spec['feature_choices']={'class/연구원':[['apothecary','pokemon_caretaking']]}
 def test_same_researcher_legacy_and_canonical_choices_drive_crafting_and_actual_skill_training(self):
  for canonical in (False,True):
   self.setUp();self.researcher_caretaker(canonical);self.act('craft_item',item='상처약',minutes=1,reason='one shared acquired Researcher')
   r=self.act('experience_training',targets=[self.p],pushed_skills={self.p.spec['id']:'육상'},safe=True)
   self.assertEqual(self.a.spec['items']['상처약'],1);self.assertEqual(self.a.spec['money'],0);self.assertEqual(self.e.elapsed_seconds,3660);self.assertGreater(r['awards'][0],0)
   self.assertEqual(len(self.e.skill_roll(self.p,'육상',fixed=[2]*5).faces),5)
 def test_conflicting_researcher_acquisition_is_rejected_by_both_real_consumers_before_cost(self):
  self.researcher_caretaker();self.a.spec['feature_choices']={'class/연구원':[['apothecary','general']]};before=self.state()
  with self.assertRaises(ValueError):self.act('craft_item',item='상처약',minutes=1,reason='conflicting choices')
  self.assertEqual(before,self.state())
  with self.assertRaises(ValueError):self.act('experience_training',targets=[self.p],pushed_skills={self.p.spec['id']:'육상'},safe=True)
  self.assertEqual(before,self.state());self.assertNotIn('pushed_skill',self.p.spec)
 def test_chef_actual_meal_planner_each_rank_produces_drink_at_source_price(self):
  self.own('basic_cooking');self.a.spec['classes']=['Chef'];self.a.spec['items']['요리 세트']=1
  for item,(rank,price) in C.MEAL_RECIPES.items():
   self.a.spec['skills']['직감']={3:'초보',4:'숙련',5:'전문',6:'달인'}[rank];self.a.spec['money']=price
   r=self.act('craft_item',item=item,minutes=1,reason='GM Extended cooking time');self.assertEqual(r['money_spent'],price);self.assertEqual(self.a.spec['money'],0);self.assertEqual(self.a.spec['items'][item],1)
 def test_meal_planner_missing_class_rank_tool_or_source_never_spends(self):
  self.own('basic_cooking');self.a.spec['classes']=['요리사'];self.a.spec['items']['요리 세트']=1;self.a.spec['money']=250
  for key,value in [('classes',[]),('skills',{'직감':'초보'}),('items',{}),('edges',[])]:
   old=deepcopy(self.a.spec[key]);self.a.spec[key]=value;before=self.state()
   with self.assertRaises(ValueError):self.act('craft_item',item='튼튼밀크',minutes=1,reason='GM duration')
   self.assertEqual(before,self.state());self.a.spec[key]=old
  self.a.spec['skills']['직감']='달인';original=self.e.r._selected_rule
  try:
   self.e.r._selected_rule=lambda uid, *args, **kwargs: uid + '/unsupported' if uid == C.CHEF_SOURCE else original(uid, *args, **kwargs);before=self.state()
   with self.assertRaises(ValueError):self.act('craft_item',item='튼튼밀크',minutes=1,reason='GM duration')
   self.assertEqual(before,self.state())
  finally:self.e.r._selected_rule=original
 def test_damaged_canonical_item_and_invalid_output_inventory_fail_before_cost(self):
  self.a.spec['items']['얼음상태치료제']=1;self.a.spec['damaged_items']=['item/얼음상태치료제'];before=self.state()
  with self.assertRaises(ValueError):self.act('dismantle',item='얼음상태치료제')
  self.assertEqual(before,self.state());self.apothecary();self.a.spec['items']['상처약']='invalid';before=self.state()
  with self.assertRaises(ValueError):self.act('craft_item',item='상처약',minutes=1,reason='GM duration')
  self.assertEqual(before,self.state())
 def test_source_scope_is_unchanged(self):
  e=next(x for x in json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries'] if x['id']=='DOMAIN-074')
  for a in e['source_snapshot']['anchors']:
   actual='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start']-1:a['end']]);self.assertEqual(actual,a['excerpt'])
 def test_dowsed_shard_becomes_only_related_type_gem_with_actual_edge_and_cost(self):
  self.dowsing();self.own('gem_lore');result=self.act('dowse',outdoors=True,fixed={'0':4,'1':1,'2':1,'3':1});color=next(iter(result['gained']))
  wrong=next(t for types in C.SHARDS.values() for t in types if t not in C.SHARDS[color]);before=self.state()
  with self.assertRaises(ValueError):self.act('craft_gem',color=color,gem_type=wrong,minutes=5,reason='GM extended crafting')
  self.assertEqual(before,self.state());gem_type=C.SHARDS[color][0]
  self.act('craft_gem',color=color,gem_type=gem_type,minutes=5,reason='GM extended crafting');self.assertEqual(self.a.spec['shards'][color],0);self.assertEqual(self.a.spec['items'][gem_type+'주얼'],1)
 def plant_setup(self):
  self.own('green_thumb');self.a.spec['items'].update({'나무열매플랜터':1,'버치열매':5})
 def test_planter_policy_unselected_no_consumption_and_book_one_capacity(self):
  self.plant_setup();before=self.state()
  with self.assertRaises(ValueError):self.act('plant_berry',berry='버치열매',plant_id='one',planter_slot=0)
  self.assertEqual(before,self.state());self.act('plant_berry',berry='버치열매',plant_id='one',planter_slot=0,planter_policy='book-literal');before=self.state()
  with self.assertRaises(ValueError):self.act('plant_berry',berry='버치열매',plant_id='two',planter_slot=0,planter_policy='book-literal')
  self.assertEqual(before,self.state())
 def test_book_planter_two_days_real_harvest_protected_from_weather_and_fertile_without_mulch(self):
  self.plant_setup();self.act('plant_berry',berry='버치열매',plant_id='one',planter_slot=0,planter_policy='book-literal')
  self.act('plant_berry',berry='버치열매',plant_id='ground',soft_soil=True);self.e.advance_time(172799,[self.a]);before=self.state()
  with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='one',fixed=1)
  self.assertEqual(before,self.state());self.e.advance_time(1,[self.a]);result=self.act('harvest_berry',plant_id='one',environment_allows_growth=False,soil_quality=-9,fixed=1)
  self.assertEqual(result['amount'],1);self.assertEqual(result['soil_bonus'],1);self.assertTrue(result['protected'])
  from common_checks import PendingDecision
  self.assertIsInstance(self.act('harvest_berry',plant_id='ground',environment_allows_growth=False,fixed=1),PendingDecision)
  with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='one',fixed=3)
 def test_sheet_planter_four_capacity_one_owned_and_three_actual_session_boundaries(self):
  self.e=Engine(self.rules,session_frequency=True,defer_session_refresh=True);self.e.gm.everyone=[self.a,self.p];self.e.begin_session('s0',[self.a]);self.plant_setup()
  for i in range(4):self.act('plant_berry',berry='버치열매',plant_id=str(i),planter_slot=0,planter_policy='sheet-current')
  with self.assertRaises(ValueError):self.act('plant_berry',berry='버치열매',plant_id='five',planter_slot=0,planter_policy='sheet-current')
  for sid in ('s1','s2'):self.e.begin_session(sid,[self.a])
  with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='0',fixed=2)
  self.e.begin_session('s2',[self.a])
  with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='0',fixed=2)
  self.e.begin_session('s3',[self.a]);self.assertEqual(self.act('harvest_berry',plant_id='0',fixed=2)['amount'],2)
  self.a.spec['items']['나무열매플랜터']=2
  with self.assertRaises(ValueError):self.act('plant_berry',berry='버치열매',plant_id='second',planter_slot=1,planter_policy='sheet-current')
 def botany(self,rank='숙련'):
  self.plant_setup();self.a.spec['classes']=['class/연구원'];self.a.spec['research_fields']=['식물학','일반 지식'];self.a.spec['feats'].append('최상급 열매');self.a.spec['skills']['일반 지식']=rank;self.a.spec['skills']['생존']=rank
 def test_qualified_botany_actual_herb_uses_same_one_plant_protected_container(self):
  self.botany();self.a.spec['items']['멘탈허브']=2
  result=self.act('plant_berry',berry='멘탈허브',plant_id='herb',planter_slot=0,planter_policy='book-literal');self.assertEqual(result['plant']['crop']['kind'],'herb');self.assertEqual(self.a.spec['items']['멘탈허브'],1)
  with self.assertRaises(ValueError):self.act('plant_berry',berry='멘탈허브',plant_id='extra',planter_slot=0,planter_policy='book-literal')
  self.e.advance_time(172800);r=self.act('harvest_berry',plant_id='herb',fixed=3,environment_allows_growth=False);self.assertEqual(r['amount'],2);self.assertEqual(self.a.spec['items']['멘탈허브'],3)
 def test_herb_requires_actual_researcher_fields_top_tier_and_green_thumb(self):
  self.botany();self.a.spec['items']['멘탈허브']=1
  for key,value in [('classes',[]),('research_fields',['일반 지식','약사']),('research_fields',['식물학','invented field']),('feats',[]),('edges',[])]:
   old=deepcopy(self.a.spec[key]);self.a.spec[key]=value;before=self.state()
   with self.assertRaises(ValueError):self.act('plant_berry',berry='멘탈허브',plant_id='herb',planter_slot=0,planter_policy='book-literal')
   self.assertEqual(before,self.state());self.a.spec[key]=old
 def test_top_tier_threshold_and_master_soil_are_actual_effective_rank(self):
  self.botany();self.a.spec['items']['과사열매']=1;before=self.state()
  with self.assertRaises(ValueError):self.act('plant_berry',berry='과사열매',plant_id='tier3',soft_soil=True)
  self.assertEqual(before,self.state());self.a.spec['skills']['생존']='전문';self.act('plant_berry',berry='과사열매',plant_id='tier3',soft_soil=True)
  self.a.spec['skills']['생존']='달인';self.e.advance_time(172800);r=self.act('harvest_berry',plant_id='tier3',fixed=4);self.assertEqual(r['soil_bonus'],2);self.assertEqual(r['amount'],3)
 def test_green_thumb_apricorn_die_two_minus_two_and_zero_still_spends_daily_harvest(self):
  self.plant_setup();self.a.spec['items']['빨간규토리']=1;self.act('plant_berry',berry='빨간규토리',plant_id='apricorn',soft_soil=True);self.e.advance_time(172800)
  r=self.act('harvest_berry',plant_id='apricorn',fixed=1);self.assertEqual(r['amount'],0)
  with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='apricorn',fixed=2)
  self.a.spec.setdefault('frequency_state',{})['day']=1;self.assertEqual(self.act('harvest_berry',plant_id='apricorn',fixed=2)['amount'],1)
 def test_sold_planter_cannot_still_protect_or_harvest_contained_plant(self):
  self.plant_setup();self.act('plant_berry',berry='버치열매',plant_id='p',planter_slot=0,planter_policy='book-literal');self.e.advance_time(172800);self.a.spec['items']['나무열매플랜터']=0;before=self.state()
  with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='p',fixed=3)
  self.assertEqual(before,self.state())
 def test_all_five_dual_stat_poffin_berries_need_valid_explicit_choice(self):
  self.a.spec['items']['포핀 혼합기']=1;self.a.spec['cooking_materials_value']=2500
  for berry,stats in C.POFFIN_ALTERNATIVES.items():
   self.a.spec['items'][berry]=1;before=self.state()
   with self.assertRaises(ValueError):self.act('cook_poffins',ingredients={berry:1},minutes=1,reason='GM duration')
   self.assertEqual(before,self.state());r=self.act('cook_poffins',ingredients={berry:1},minutes=1,reason='GM stat selection',tie_choice=stats[-1]);self.assertEqual(r['batch']['contest_stat'],stats[-1])
 def test_cultivation_tiers_are_exact_current_source_rows(self):
  import re
  expected={}
  for line in (ROOT/'input/ch09-equipment.md').read_text(encoding='utf-8-sig').splitlines()[299:377]:
   m=re.match(r'\| ([123]) \| ([^|]+) \|',line)
   if m:expected[m[2].strip()]=int(m[1])
  self.assertEqual({k:v['tier'] for k,v in C._cultivation(self.e)['berries'].items()},expected)
 def test_source_tool_prices_apply_to_actual_intact_dismantling(self):
  expected={'화학 세트':1000,'요리 세트':1000,'다우징 로드':2000,'포핀 혼합기':500,'몬스터볼 공구함':500,'나무열매플랜터':2000}
  self.assertEqual(C.KIT_PRICES,expected)
  for name,price in expected.items():
   self.a.spec['items'][name]=1;r=self.act('dismantle',item={'화학 세트':'item/화학-세트-1','다우징 로드':'item/다우징-로드-1','포핀 혼합기':'item/포핀-혼합기-1'}.get(name,name),scrap_kind='제작 키트 재료',scrap_reason='GM identifies intact tool parts as related kit materials');self.assertEqual(r['value'],price//2);self.assertEqual(self.a.spec['items'][name],0)
 def test_energy_root_spacing_alias_uses_actual_inventory_and_known_herb_source(self):
  self.botany('전문');self.a.spec['items']['힘의 뿌리']=1;self.act('plant_berry',berry='힘의 뿌리',plant_id='root',soft_soil=True);self.assertEqual(self.a.spec['items']['힘의 뿌리'],0)
  self.e.advance_time(172800);self.assertEqual(self.act('harvest_berry',plant_id='root',fixed=4)['amount'],2);self.assertEqual(self.a.spec['items']['힘의뿌리'],2)
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(CraftTests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/precise_actions.py','engine/wild_equipment.py','engine/downtime.py','engine/common_action_checks.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_maneuvers.py','data/context-check-policy.json','engine/researcher_features.py','engine/net_capsule.py','engine/combat_timing.py','engine/environmental_effects.py','data/cultivation-policy.json','engine/frequency.py','engine/bandages.py','engine/injury_recovery.py','input/ch04-trainer-classes.md','engine/crafting_activities.py','engine/pokemon_activities.py','engine/engine.py','engine/contest.py','engine/items.py','engine/skill_modifiers.py','data/skill-check-policy.json','data/items-mech.json','data/items-reviewed.json','data/planter-policy.json','input/db/inventory.csv','data/core-rules.json','data/contest-rules.json','data/lookup-tables.json','data/rulesets.json','output/ruleunits.jsonl','input/ch03-skills-edges-feats.md','input/ch08-contests.md','input/ch09-equipment.md','tools/test_category3_crafting.py','tools/test_category3_pokemon_activities.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['DOMAIN-074'],'completion':'review pending; berries and qualified herbs use explicit book-literal or sheet-current planter policy','results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-crafting-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
