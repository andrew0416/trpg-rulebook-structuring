"""Sourced material kinds and native transform producers/consumers after restore."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category3_crafting as _fixture_test_category3_crafting
import crafting_resources as R,crafting_activities as C,state_codec as CODEC
from contest import ContestEngine

class CraftingResourceStateTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category3_crafting.CraftTests.setUpClass.__func__)
 setUp=_fixture_test_category3_crafting.CraftTests.setUp
 actor=_fixture_test_category3_crafting.CraftTests.actor
 act=_fixture_test_category3_crafting.CraftTests.act
 own=_fixture_test_category3_crafting.CraftTests.own
 def snap(self):return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(c) for c in self.e.gm.everyone],self.e.log_lines),{id(self.rules):self.rules})
 def restored(self):return CODEC.load_engine(self.rules,CODEC.dump_engine(self.e))
 def gem_setup(self):
  self.own('gem_lore');self.a.spec['skills']['오컬트학']='숙련'
 def test_all_eighteen_source_color_type_pairs_create_actual_gems_and_resume(self):
  expected={'빨강':('불꽃','페어리','에스퍼'),'주황':('노말','격투','드래곤'),'노랑':('전기','바위','강철'),'초록':('벌레','풀','땅'),'파랑':('물','얼음','비행'),'보라':('독','악','고스트')}
  self.assertEqual(C.SHARDS,expected);self.gem_setup();self.a.spec['shards']=dict.fromkeys(expected,3)
  initial=self.e.gm.snapshot();loaded=None
  for number,(color,kind) in enumerate(((color,kind) for color,kinds in expected.items() for kind in kinds),1):
   self.act('craft_gem',color=color,gem_type=kind,minutes=1,reason='source color recipe')
   self.assertEqual(self.a.spec['items'][kind+'주얼'],1)
   if number==9:
    loaded=self.restored();actor=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id)
   elif number>9:
    loaded.pokemon_activity(actor,'craft_gem',color=color,gem_type=kind,minutes=1,reason='source color recipe')
  self.assertTrue(all(n==0 for n in self.a.spec['shards'].values()));self.assertEqual(self.a.spec['items'],actor.spec['items'])
  self.assertEqual(R.validate(self.a),R.validate(actor));self.assertEqual(len(R.validate(actor)),18)
  for entry in R.validate(actor):
   self.assertEqual(entry['operation'],'craft_gem');self.assertEqual({x['unit'] for x in entry['resources']},{'count'})
  self.e.gm.restore(initial);self.assertEqual(self.a.spec['shards'],dict.fromkeys(expected,3));self.assertNotIn('resource_transformations',self.a.spec)
 def test_source_scrap_categories_do_not_reuse_display_categories_or_close_the_kind_list(self):
  rows=[('초코바','음식',75),('맛있는물','음식',75),
        ('item/미끼-2','음식',250),('이유식','음식',100),
        ('상처약','약',200),('플러스파워','약',350),('맥스업','약',4900),
        ('실버스프레이','스프레이',300),('item/오물탄-화상','스프레이',350),
        ('item/몬스터볼-2','몬스터볼',250),('콘테스트 옷','패션 도구',1000)]
  expected={}
  for item,kind,value in rows:
   self.a.spec['items'][item]=2
   result=self.act('dismantle',item=item,count=2);self.assertEqual((result['category'],result['value']),(kind,value))
   expected[kind]=expected.get(kind,0)+value
  self.assertEqual(self.a.spec['crafting_scrap'],expected)
  self.assertEqual(len(R.validate(self.a)),len(rows))
  self.a.spec['items']['상처약']=1;before=self.snap()
  with self.assertRaises(ValueError):self.act('dismantle',item='상처약',scrap_kind='스프레이',scrap_reason='cannot reclassify a known medical item')
  self.assertEqual(self.snap(),before)
  self.a.spec['items']['화학 세트']=1
  with self.assertRaises(ValueError):self.act('dismantle',item='item/화학-세트-1')
  result=self.act('dismantle',item='item/화학-세트-1',scrap_kind='실험용 재료',scrap_reason='GM observed intact laboratory material category')
  self.assertEqual((result['category'],result['value']),('실험용 재료',500))
  loaded=self.restored();actor=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id)
  self.assertEqual(actor.spec['crafting_scrap'],self.a.spec['crafting_scrap'])
  self.assertEqual(actor.spec.get('money',0),0)
  self.assertEqual(R.validate(actor)[-1]['result']['classification_reason'],'GM observed intact laboratory material category')
  # Possession is shared state; crafting authority remains source-specific.
  self.p.spec['crafting_scrap']={'음식':100};self.p.spec['items']={'상처약':1};R.validate(self.p);before=self.snap()
  with self.assertRaises(ValueError):C.dismantle(self.e,self.p,item='상처약')
  self.assertEqual(self.snap(),before)
  again=self.restored();pokemon=next(c for c in again.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(pokemon.spec['crafting_scrap'],{'음식':100})
 def test_spray_recipe_cannot_spend_medical_scrap_and_uses_matching_value_after_restore(self):
  self.own('repel_crafter');self.a.spec['items']={'화학 세트':1,'실버스프레이':1};self.a.spec['crafting_scrap']={'약':100}
  before=self.snap()
  with self.assertRaises(ValueError):self.act('craft_item',item='벌레회피스프레이',scrap_value=100,minutes=1,reason='wrong material kind')
  self.assertEqual(self.snap(),before)
  self.act('dismantle',item='실버스프레이');loaded=self.restored();actor=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id)
  result=loaded.pokemon_activity(actor,'craft_item',item='벌레회피스프레이',scrap_value=100,minutes=1,reason='matching spray material')
  self.assertEqual((result['money_spent'],result['category']),(0,'스프레이'))
  self.assertEqual(actor.spec['crafting_scrap'],{'약':100,'스프레이':50});self.assertEqual(actor.spec['items']['벌레회피스프레이'],1)
  last=R.validate(actor)[-1];spent=[r for r in last['resources'] if r['field']=='crafting_scrap']
  self.assertEqual(spent,[{'field':'crafting_scrap','key':'스프레이','unit':'value','before':150,'after':50,'delta':-100}])
 def test_every_connected_transform_rolls_back_time_input_output_and_history_on_late_failure(self):
  for operation in ('craft_item','craft_gem','cook_poffins','dismantle'):
   self.setUp()
   if operation=='craft_item':
    self.own('basic_balls');self.a.spec['items']={'몬스터볼 공구함':1};self.a.spec['money']=100;options={'item':'몬스터볼','minutes':1,'reason':'source recipe'}
   elif operation=='craft_gem':
    self.gem_setup();self.a.spec['shards']={'빨강':1};options={'color':'빨강','gem_type':'불꽃','minutes':1,'reason':'source recipe'}
   elif operation=='cook_poffins':
    self.a.spec['items']={'포핀 혼합기':1,'버치열매':1};self.a.spec['cooking_materials_value']=350;options={'ingredients':{'버치열매':1},'minutes':1,'reason':'source recipe'}
   else:self.a.spec['items']={'상처약':1};options={'item':'상처약'}
   before=self.snap();original=R.record
   def fail(*args,**kw):original(*args,**kw);raise ValueError('injected failure after actual inputs and outputs')
   with patch.object(R,'record',side_effect=fail):
    with self.assertRaises(ValueError):self.act(operation,**options)
   self.assertEqual(self.snap(),before)
   self.act(operation,**options);self.assertEqual(len(R.validate(self.a)),1)
 def test_dowsing_late_clock_failure_rolls_back_every_participant_and_rng(self):
  self.a.spec['items']['다우징 로드']=1;self.a.spec['skills']['오컬트학']='숙련'
  before=self.snap();engine_type=type(self.e);advance=engine_type.advance_time
  def fail(e,*args,**kwargs):
   advance(e,*args,**kwargs)
   e.gm.everyone[-1].hp-=1
   raise ValueError('failure after shared clock advance')
  with patch.object(engine_type,'advance_time',fail):
   with self.assertRaisesRegex(ValueError,'shared clock'):self.act('dowse',outdoors=True)
  self.assertEqual(self.snap(),before)
  result=self.act('dowse',outdoors=True)
  self.assertEqual(self.e.elapsed_seconds,600);self.assertEqual(self.a.spec['dowsing']['uses'],1)
  self.assertEqual(sum(self.a.spec['shards'].values()),sum(result['gained'].values()))

 def test_dowsing_odd_rank_allowance_and_real_new_day_survive_gm_and_json_restore(self):
  import json,downtime as DT
  self.a.spec['items']['다우징 로드']=1;self.a.spec['skills']['오컬트학']=5
  options={'outdoors':True,'fixed':{str(i):1 for i in range(5)}}
  first=self.act('dowse',**options)
  self.assertEqual(first['pool'],5);self.assertEqual(first['remaining_uses'],1)
  self.assertEqual(self.e.elapsed_seconds,600);self.assertEqual(self.a.spec['dowsing'],{'day':0,'uses':1})
  snapshot=self.e.gm.snapshot()
  loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  self.act('dowse',**options);self.e.gm.restore(snapshot)
  for e in (self.e,loaded):
   actor=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id)
   self.assertEqual(actor.spec['dowsing'],{'day':0,'uses':1});self.assertEqual(e.elapsed_seconds,600)
   result=e.pokemon_activity(actor,'dowse',**options)
   self.assertEqual(result['remaining_uses'],0);self.assertEqual(actor.spec['dowsing'],{'day':0,'uses':2})
   self.assertEqual(e.elapsed_seconds,1200);before=deepcopy(CODEC.dump_engine(e))
   with self.assertRaisesRegex(ValueError,'daily Dowsing Rod allowance exhausted'):
    e.pokemon_activity(actor,'dowse',**options)
   self.assertEqual(CODEC.dump_engine(e),before)
   DT.new_day(actor);result=e.pokemon_activity(actor,'dowse',**options)
   self.assertEqual(result['remaining_uses'],1);self.assertEqual(actor.spec['dowsing'],{'day':1,'uses':1})
   self.assertEqual(actor.spec['items']['다우징 로드'],1);self.assertEqual(e.elapsed_seconds,1800)

 def test_harvest_late_record_failure_rolls_back_roll_inventory_and_daily_use(self):
  import cultivation_state as PLANTS
  self.own('green_thumb');self.a.spec['items']['버치열매']=1
  self.act('plant_berry',berry='버치열매',plant_id='one',soft_soil=True)
  self.e.advance_time(172800,[self.a]);before=self.snap();record=PLANTS.record_harvest
  plant=self.a.spec['plants']['one'];inventory=self.a.spec['items']
  def fail(*args,**kwargs):
   record(*args,**kwargs)
   raise ValueError('failure after harvest receipt')
  with patch.object(PLANTS,'record_harvest',fail):
   with self.assertRaisesRegex(ValueError,'harvest receipt'):self.act('harvest_berry',plant_id='one')
  self.assertEqual(self.snap(),before)
  self.assertIs(self.a.spec['plants']['one'],plant);self.assertIs(self.a.spec['items'],inventory)
  result=self.act('harvest_berry',plant_id='one')
  self.assertEqual(inventory['버치열매'],result['amount'])
  self.assertEqual(len(plant['harvest_history']),1)
 def test_bad_balances_and_receipt_units_reject_before_native_cost_export_or_durable_load(self):
  self.a.spec['items']={'상처약':3};self.act('dismantle',item='상처약');baseline=deepcopy(self.a.spec)
  mutations=[lambda s:s.update(crafting_scrap={'약':True}),lambda s:s.update(crafting_scrap={'약':-1}),lambda s:s.update(shards={'검정':1}),lambda s:s.update(cooking_materials_value=-1),lambda s:s['resource_transformations'][0]['resources'][0].update(unit='count')]
  for mutate in mutations:
   self.a.spec.clear();self.a.spec.update(deepcopy(baseline));mutate(self.a.spec);before=self.snap()
   for action in (lambda:self.act('dismantle',item='상처약'),self.e.export_state):
    with self.assertRaises(ValueError):action()
    self.assertEqual(self.snap(),before)
  with patch.object(R,'validate',return_value=[]):payload=CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):CODEC.load_engine(self.rules,payload)
  self.assertEqual(self.snap(),before)
 def test_produced_poffins_keep_transform_history_when_later_consumed_after_restore(self):
  self.a.spec['items']={'포핀 혼합기':1,'버치열매':1};self.a.spec['cooking_materials_value']=350
  result=self.act('cook_poffins',ingredients={'버치열매':1},minutes=1,reason='source recipe');batch=result['batch']['id']
  receipt=deepcopy(R.validate(self.a)[0]);snapshot=self.e.gm.snapshot();loaded=self.restored()
  actor=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id);target=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
  contest=ContestEngine(self.contest_rules);before=contest.stat_pool_from_combatant(target,smart_stat_policy='ptk-literal-defense')['근사함']
  loaded.pokemon_activity(actor,'feed_poffin',batch_id=batch,target=target,minutes=1,reason='actual produced food intake')
  self.assertEqual(actor.spec['poffin_batches'][batch]['count'],1);self.assertEqual(R.validate(actor)[0],receipt)
  self.assertEqual(contest.stat_pool_from_combatant(target,smart_stat_policy='ptk-literal-defense')['근사함'],before+1)
  self.act('feed_poffin',batch_id=batch,target=self.p,minutes=1,reason='actual produced food intake')
  self.e.gm.restore(snapshot);self.assertEqual(self.a.spec['poffin_batches'][batch]['count'],2);self.assertEqual(R.validate(self.a)[0],receipt)

if __name__=='__main__':unittest.main()
