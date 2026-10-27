"""Exact TM rows109-110 through the existing native crafting transaction."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import csv,hashlib,io,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_crafting_resource_state as fixture
import crafting_resources as R,crafting_recipes as RECIPES
import state_codec as CODEC,native_scenario_fixture as NATIVE

SHOP={'source':'gm/observation','reason':'GM observed a nearby Friendly Shop open for material purchases'}


class CsvMaterialsTests(unittest.TestCase):
 setUpClass=classmethod(fixture.CraftingResourceStateTests.setUpClass.__func__)
 actor=fixture.CraftingResourceStateTests.actor
 act=fixture.CraftingResourceStateTests.act
 own=fixture.CraftingResourceStateTests.own
 restored=fixture.CraftingResourceStateTests.restored

 def setUp(self):
  fixture.CraftingResourceStateTests.setUp(self)
  self.choice=patch.dict(self.rules.rulings.mech,{R.SOURCE:{'materials_edition':'csv-homebrew'}})
  self.choice.start();self.addCleanup(self.choice.stop)

 def ready(self):
  self.own('basic_balls');self.a.spec['items']={'몬스터볼 공구함':1}
  self.a.spec['money']=1000

 def craft(self,**options):
  return self.act('craft_item',item='item/몬스터볼-2',minutes=1,reason='actual native Basic Balls recipe',**options)

 def rejected(self,fn,reason):
  return NATIVE.assert_rejected_unchanged(self.e,fn,reason_pattern=reason)

 def recipe(self):
  return json.loads((ROOT/'data/examples/crafting-recipes.json').read_text(encoding='utf-8'))[0]

 def test_exact_logical_rows_source_hash_and_unchanged_frozen_scope(self):
  raw=(ROOT/'input/db/tm.csv').read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),R.CSV_SHA)
  rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
  ledger=json.loads((ROOT/'data/verification/category2-tabular-core-status.json').read_text(encoding='utf-8'))
  entries={r['id']:r for r in ledger['entries']}
  for number in (109,110):
   row=entries[f'C2TAB/tm/r{number:03d}c4-5']
   self.assertEqual((row['name'],row['statement']),(rows[number-1][3],rows[number-1][4]))
   self.assertTrue(row['include_category2']);self.assertEqual(row['source_sha256'],R.CSV_SHA)
  self.assertEqual(entries[R.CSV_SOURCE]['denominator_contribution'],1)
  self.assertEqual(entries['C2TAB/tm/r110c4-5']['denominator_contribution'],0)
  self.assertEqual(entries[R.CSV_SOURCE]['additional_source_children'],['C2TAB/tm/r110c4-5'])
  self.assertEqual(len(set(R.MATERIAL_KINDS.values())),5)

 def test_cash_without_shop_cannot_pay_and_matching_material_auto_pays_by_value(self):
  self.ready();self.rejected(self.craft,'nearby Friendly Shop')
  self.a.spec['crafting_scrap']={'의학 재료':1000}
  self.rejected(self.craft,'nearby Friendly Shop')
  self.a.spec['crafting_scrap']['기계 재료']=150
  result=self.craft()
  self.assertEqual((result['scrap_spent'],result['money_spent'],result['category']),(100,0,'기계 재료'))
  self.assertEqual(self.a.spec['crafting_scrap'],{'의학 재료':1000,'기계 재료':50})
  self.assertEqual((self.a.spec['money'],self.a.spec['items']['item/몬스터볼-2']),(1000,1))
  self.assertIn(R.CSV_SOURCE,R.validate(self.a)[-1]['sources'])

 def test_shop_immediate_purchase_and_buy_one_to_one_sell_half_floor(self):
  self.ready();self.a.spec['crafting_scrap']={'기계 재료':35}
  result=self.craft(scrap_value=35,friendly_shop=SHOP)
  self.assertEqual((result['scrap_spent'],result['money_spent']),(35,65))
  self.assertEqual(result['materials'][0]['purchased_material_value'],65)
  self.assertEqual(self.a.spec['crafting_scrap']['기계 재료'],0)
  self.act('trade_materials',category='음식 재료',value=101,direction='buy',friendly_shop=SHOP)
  self.act('trade_materials',category='음식 재료',value=101,direction='sell',friendly_shop=SHOP)
  self.assertEqual((self.a.spec['money'],self.a.spec['crafting_scrap']['음식 재료']),(884,0))
  self.assertEqual(R.validate(self.a)[-1]['result']['money_spent'],-50)
  self.assertTrue(all(c['unit']=='value' for c in R.validate(self.a)[-1]['resources']))

 def test_craftable_dismantle_is_recipe_price_ninety_percent_floor_per_item(self):
  self.a.spec['items']={'슈퍼볼':2,'초코바':1,'상처약':1}
  for item,value,kind in [('슈퍼볼',314,'기계 재료'),('초코바',45,'음식 재료'),('상처약',90,'의학 재료')]:
   result=self.act('dismantle',item=item,count=2 if item=='슈퍼볼' else 1)
   self.assertEqual((result['value'],result['category'],result['valuation']),(value,kind,'recipe90'))
  self.assertEqual(self.a.spec['crafting_scrap'],{'기계 재료':314,'음식 재료':45,'의학 재료':90})

 def test_nonmaterial_recipe_or_noncraftable_requires_suitability_and_shop_half(self):
  self.a.spec['items']={'초코바':2,'화학 세트':2}
  recipe=self.recipe();recipe['output']={'item_id':'item/초코바','key':'초코바'}
  recipe['materials']=[{'id':'berry','options':[{'kind':'item','item_id':'item/버치열매','key':'버치열매','amount':1}]}]
  self.rejected(lambda:self.act('dismantle',item='초코바',recipe=recipe),'suitability judgment')
  result=self.act('dismantle',item='초코바',recipe=recipe,scrap_reason='GM judged this non-material recipe item yields food material')
  self.assertEqual((result['value'],result['valuation']),(37,'shop50'))
  self.rejected(lambda:self.act('dismantle',item='item/화학-세트-1',scrap_kind='기계 재료'),'suitability judgment')
  result=self.act('dismantle',item='item/화학-세트-1',scrap_kind='기계 재료',scrap_reason='GM judged intact equipment reusable mechanical material')
  self.assertEqual((result['value'],result['category']),(500,'기계 재료'))

 def test_all_five_categories_and_overlapping_x_items_and_capsules(self):
  cases=[('이유식','음식 재료'),('맥스업','의학 재료'),('실버스프레이','화학 재료'),
   ('item/몬스터볼-2','기계 재료'),('콘테스트 옷','장비 재료'),
   ('플러스파워','의학 재료'),('플러스파워','화학 재료'),('네트캡슐','화학 재료'),('네트캡슐','기계 재료')]
  for item,kind in cases:
   self.a.spec['items'][item]=self.a.spec['items'].get(item,0)+1
   result=self.act('dismantle',item=item,scrap_kind=kind,scrap_reason='GM judged intact source-category item suitable to dismantle')
   self.assertEqual(result['category'],kind)
  self.a.spec['items']['상처약']=1
  self.rejected(lambda:self.act('dismantle',item='상처약',scrap_kind='화학 재료'),'contradicts')

 def test_external_value_recipe_and_counted_non_dollar_inputs_keep_units(self):
  self.ready();recipe=self.recipe();recipe['materials'][0]['options'][0]['amount']=137
  self.a.spec['crafting_scrap']={'기계 재료':300}
  result=self.e.craft_recipe(self.a,recipe,count=2,reason='same authored recipe selected material edition')
  self.assertEqual((result['scrap_spent'],result['money_spent']),(274,0))
  result=self.act('dismantle',item='item/몬스터볼-2')
  self.assertEqual((result['value'],result['unit_basis']),(123,137))
  recipe['materials']=[{'id':'berry','options':[{'kind':'item','item_id':'item/버치열매','key':'버치열매','amount':2}]}]
  self.a.spec['items']['버치열매']=2
  self.e.craft_recipe(self.a,recipe,reason='non-dollar source ingredients unchanged')
  self.assertEqual(self.a.spec['items']['버치열매'],0)
  self.assertEqual(R.validate(self.a)[-1]['result']['materials'][0]['kind'],'item')

 def test_aggregate_groups_cannot_double_spend_materials_or_shop_money(self):
  self.ready();recipe=self.recipe();recipe['materials'].append(dict(deepcopy(recipe['materials'][0]),id='second'))
  self.a.spec['crafting_scrap']={'기계 재료':100}
  self.rejected(lambda:self.e.craft_recipe(self.a,recipe,reason='aggregate materials'),'nearby Friendly Shop')
  self.a.spec['money']=150
  inputs={key:{'option':0,'scrap_value':0,'shop':SHOP} for key in ('cost','second')}
  self.rejected(lambda:self.e.craft_recipe(self.a,recipe,inputs=inputs,reason='aggregate purchase'),'aggregate recipe ingredients')

 def test_late_failure_rolls_back_trade_purchase_and_native_recipe_then_both_restores(self):
  self.ready();original=R.record
  def fail(*args,**kwargs):original(*args,**kwargs);raise ValueError('late CSV receipt failure')
  with patch.object(R,'record',side_effect=fail):
   self.rejected(lambda:self.craft(friendly_shop=SHOP),'late CSV receipt')
   self.rejected(lambda:self.act('trade_materials',category='기계 재료',value=201,direction='buy',friendly_shop=SHOP),'late CSV receipt')
  self.act('trade_materials',category='기계 재료',value=201,direction='buy',friendly_shop=SHOP)
  snapshot=self.e.gm.snapshot();loaded=self.restored()
  self.craft();self.e.gm.restore(snapshot)
  self.assertEqual(self.a.spec['crafting_scrap']['기계 재료'],201)
  for engine in (self.e,loaded):
   actor=next(a for a in engine.gm.everyone if a.entity_id==self.a.entity_id)
   result=engine.pokemon_activity(actor,'craft_item',item='item/몬스터볼-2',minutes=1,reason='restored CSV materials')
   self.assertEqual(result['scrap_spent'],100)
   self.assertEqual(actor.spec['crafting_scrap']['기계 재료'],101)
   self.assertEqual(len(R.validate(actor)),2)

 def test_explicit_choice_keeps_book_default_and_live_source_hash_is_not_cached(self):
  self.ready()
  with patch.dict(self.rules.rulings.mech,{R.SOURCE:{'materials_edition':'book'}}):
   result=self.craft();self.assertEqual((result['money_spent'],result['category']),(100,'몬스터볼'))
  original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b' ' if path.as_posix().endswith('/input/db/tm.csv') else raw
  self.assertTrue(R.csv_materials(self.rules))
  with patch.object(Path,'read_bytes',changed):
   self.rejected(self.craft,'CSV materials.*source changed')


if __name__=='__main__':unittest.main()
