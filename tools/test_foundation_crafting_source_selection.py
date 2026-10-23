"""Craft-only monetary materials retain their selected scope at actual payment."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_crafting_resource_state as fixtures
import crafting_resources as R
from ruleset import RuleSelection

class CraftSourceTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.CraftingResourceStateTests.setUpClass.__func__)
 setUp=fixtures.CraftingResourceStateTests.setUp
 actor=fixtures.CraftingResourceStateTests.actor
 act=fixtures.CraftingResourceStateTests.act
 own=fixtures.CraftingResourceStateTests.own
 snap=fixtures.CraftingResourceStateTests.snap
 restored=fixtures.CraftingResourceStateTests.restored
 def prepare(self):
  self.own('basic_balls');self.a.spec['items']={'몬스터볼 공구함':1}
  self.a.spec['money']=0;self.a.spec['crafting_scrap']={'몬스터볼':100,'약':1000}
 def craft(self):return self.act('craft_item',item='몬스터볼',scrap_value=100,minutes=1,reason='source-specific material payment')
 def test_scrap_cannot_pay_shop_but_matching_craft_uses_it_without_cash(self):
  self.prepare()
  self.e.campaign_reward(self.a,'observe_ball_shop',event_id='observed-shop',merchant='shop',stock={'item/몬스터볼-2':1},reason='GM observes the actual ball stock before attempted payment')
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'insufficient actual money'):
   self.e.campaign_reward(self.a,'purchase',event_id='ordinary-purchase',merchant='shop',items={'item/몬스터볼-2':1},reason='actual purchase')
  self.assertEqual(self.snap(),before)
  result=self.craft();self.assertEqual((result['money_spent'],result['scrap_spent']),(0,100))
  self.assertEqual(self.a.spec['money'],0);self.assertEqual(self.a.spec['crafting_scrap'],{'몬스터볼':0,'약':1000})
  self.assertEqual(self.a.spec['items']['item/몬스터볼-2'],1)
  import item_stock
  stock=item_stock.prepare(self.e,self.a,'item/몬스터볼-2')
  self.assertEqual(stock['key'],'item/몬스터볼-2')
 def test_wrong_kind_missing_provider_and_missing_cash_do_not_convert_scrap(self):
  self.prepare();self.a.spec['crafting_scrap'].pop('몬스터볼');before=self.snap()
  with self.assertRaisesRegex(ValueError,'matching scrap'):self.craft()
  self.assertEqual(before,self.snap());self.a.spec['crafting_scrap']['몬스터볼']=100
  self.a.spec['edges']=[];before=self.snap()
  with self.assertRaises(ValueError):self.craft()
  self.assertEqual(before,self.snap())
 def test_recipe_output_identity_does_not_borrow_same_named_variant(self):
  self.prepare();before=self.snap()
  with self.assertRaisesRegex(ValueError,'source-reviewed recipe definition'):
   self.act('craft_item',item='item/몬스터볼',scrap_value=100,minutes=1,reason='different source definition')
  self.assertEqual(before,self.snap())
  result=self.act('craft_item',item='item/몬스터볼-2',scrap_value=100,minutes=1,reason='exact recipe output')
  self.assertEqual(result['item_id'],'item/몬스터볼-2');self.assertEqual(self.a.spec['items']['item/몬스터볼-2'],1)
  self.assertIn('item/몬스터볼-2',R.validate(self.a)[-1]['sources'])
 def test_changed_or_excluded_material_source_rejects_before_time_and_payment(self):
  self.prepare();native=Path.read_bytes
  def changed(path):return native(path)+(b'changed' if path.name=='ch09-equipment.md' else b'')
  before=self.snap()
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'changed'):self.craft()
  self.assertEqual(before,self.snap())
  profile=deepcopy(self.rules.ruleset);profile.exclude_units.add(R.SOURCE)
  selection=RuleSelection(profile,list(self.rules.selection.units.values()))
  with patch.object(self.rules,'ruleset',profile),patch.object(self.rules,'selection',selection):
   before=self.snap()
   with self.assertRaises(ValueError):self.craft()
   self.assertEqual(before,self.snap())

if __name__=='__main__':unittest.main()
