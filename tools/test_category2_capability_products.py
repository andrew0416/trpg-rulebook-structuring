"""Actual three-source daily production into reusable jars and native consumers."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
import test_category2_medicine_stock as _fixture_test_category2_medicine_stock
from builder import build_pokemon
from ruleset import UnresolvedRuleSelection
import capability_products as P,item_containers as J,state_grants as G,state_codec as CODEC,frequency as F

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 held=_fixture_test_category2_medicine_stock.MedicineStockTests.held
 def jar(self,holder=None,uid='jar'):
  holder=holder or self.a;self.held(holder,'item/빈병',uid)
  self.e.gm.observe_empty_container(holder,container_selection=uid,reason='actual empty collection jar')
 def producer(self,species,level=20):return self.add(build_pokemon(self.r,species,level,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
 def collect(self,c,source,**kw):
  args=dict(holder=self.a,container_selection='jar',minutes=2,reason='GM observed actual collection duration and environment');args.update(kw)
  return self.e.collect_capability_product(c,source,**args)
 def test_three_native_sources_share_container_provenance_and_daily_budget(self):
  for species,source,item,plants in [('몽나','capability/꿈안개','item/꿈안개',False),('밀탱크','capability/우유짜기','튼튼밀크',False),('세꿀버리','capability/꿀모으기','꿀',True)]:
   with self.subTest(source=source):
    self.setUp();self.jar();c=self.producer(species);row=self.collect(c,source,living_plants=plants)
    obj=self.e._physical_objects['jar'];portion=obj[J.KEY]['portions'][row['id']]
    self.assertEqual(portion['item_id'],self.r.item_effects(item)[1]['id']);self.assertEqual(portion['source'],source)
    self.assertEqual(self.e.elapsed_seconds,120);self.assertNotIn('consumed',obj)
    self.jar(self.p,'second-jar');before=deepcopy(c.spec)
    with self.assertRaises(ValueError):self.collect(c,source,holder=self.p,container_selection='second-jar',living_plants=plants)
    self.assertEqual(c.spec,before);self.assertEqual(self.e.elapsed_seconds,120)
    F.new_day(c);second=self.collect(c,source,holder=self.p,container_selection='second-jar',living_plants=plants)
    self.assertNotEqual(row['id'],second['id']);self.assertEqual(len(c.spec[P.KEY]),2)
 def test_collected_dream_mist_attack_and_milk_drinking_consume_only_contents(self):
  info=next(x for x in self.e.capability_product_catalog() if x['source']=='capability/꿈안개')
  self.assertEqual(info['item_id'],'item/꿈안개')
  with self.assertRaises(UnresolvedRuleSelection):self.r.item_effects('꿈안개')
  self.assertEqual(self.r.item_effects('item/꿈안개-1')[1]['id'],'item/꿈안개-1')
  self.assertEqual(info['price'],500);self.assertEqual(info['shop_availability'],{'kind':'occasional','shop':'occult','guaranteed_stock':False})
  self.jar();c=self.producer('몽나');row=self.collect(c,'capability/꿈안개')
  self.a.pos=(1,3);self.t.pos=(2,3);G.grant(self.p,'capabilities','Dream Reader','fixture:dream','fixture');self.begin(self.a)
  out=self.e.use_item(self.a,'item/꿈안개',self.t,container_selection='jar',fixed_accuracy=20)
  self.assertTrue(out['status_applied']);self.assertEqual(out['payment']['kind'],'container_contents')
  self.e.gm.observe_dream(self.t,'collected mist dream',reason='actual dream')
  self.assertEqual(self.e.read_dream(self.p,self.t,share=True)['content'],'collected mist dream')
  self.assertIsNone(self.e._physical_objects['jar'][J.KEY]['current']);self.assertNotIn('consumed',self.e._physical_objects['jar'])
  self.setUp();self.jar();c=self.producer('밀탱크');self.collect(c,'capability/우유짜기');self.t.hp=1
  self.e.use_item(self.a,'튼튼밀크',self.t,container_selection='jar',duration_minutes=1,duration_reason='actual collected milk intake')
  self.assertEqual(self.t.hp,min(self.t.max_hp,81));self.assertIsNone(self.e._physical_objects['jar'][J.KEY]['current'])
  F.new_day(c);second=self.collect(c,'capability/우유짜기');self.assertEqual(len(c.spec[P.KEY]),2)
  self.assertEqual(self.e._physical_objects['jar'][J.KEY]['current'],second['id'])
 def test_both_restores_keep_quota_and_receipt_references(self):
  self.jar();c=self.producer('몽나');row=self.collect(c,'capability/꿈안개');self.e.gm.snapshot('products');e=self.restored();idx={x.entity_id:x for x in e.everyone}
  self.assertEqual(idx[c.entity_id].spec[P.KEY],c.spec[P.KEY]);self.assertEqual(e._physical_objects['jar'],self.e._physical_objects['jar'])
  F.new_day(c);self.e.gm.restore('products');self.assertFalse(F.activation_allowed(c,'capability/꿈안개',P.DAILY,engine=self.e))
  c.spec[P.KEY][row['id']]['container_id']='missing';before=deepcopy(c.spec)
  with self.assertRaises(ValueError):self.e.gm.snapshot('bad')
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  self.assertEqual(c.spec,before)
 def test_missing_capability_level_plants_empty_jar_or_time_is_atomic(self):
  self.jar();c=self.producer('몽나',19);before=deepcopy(c.spec)
  with self.assertRaises(ValueError):self.collect(c,'capability/꿈안개')
  self.assertEqual(c.spec,before)
  honey=self.producer('세꿀버리',5)
  for source,opts in [('capability/꿀모으기',{}),('capability/꿈안개',{}),('capability/꿀모으기',{'living_plants':True,'minutes':0})]:
   before=deepcopy(honey.spec)
   with self.assertRaises(ValueError):self.collect(honey,source,**opts)
   self.assertEqual(honey.spec,before);self.assertEqual(self.e.elapsed_seconds,0)
  self.collect(honey,'capability/꿀모으기',living_plants=True);milk=self.producer('밀탱크');before=deepcopy(milk.spec)
  with self.assertRaises(ValueError):self.collect(milk,'capability/우유짜기')
  self.assertEqual(milk.spec,before)

 def test_replaced_product_source_rejects_before_any_collection_payment(self):
  self.jar();c=self.producer('몽나');before=self.e.export_state();original=self.r._selected_rule
  def selected(uid):return 'item/꿈안개-1' if uid=='item/꿈안개' else original(uid)
  with patch.object(self.r,'_selected_rule',side_effect=selected):
   with self.assertRaisesRegex(ValueError,'exact sourced product'):self.collect(c,'capability/꿈안개')
  self.assertEqual(self.e.export_state(),before)
 def test_forged_csv_product_identity_cannot_replace_collected_core_source_on_save(self):
  self.jar();c=self.producer('몽나');row=self.collect(c,'capability/꿈안개')
  self.assertEqual(row['item_id'],'item/꿈안개')
  c.spec[P.KEY][row['id']]['item_id']='item/꿈안개-1'
  self.e._physical_objects['jar'][J.KEY]['portions'][row['id']]['item_id']='item/꿈안개-1'
  before=deepcopy((c.spec,self.e._physical_objects,self.e.elapsed_seconds,self.e.rng.getstate()))
  with self.assertRaisesRegex(ValueError,'produced item does not match capability source'):P.validate(c)
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):self.e.gm.snapshot('forged-source')
  self.assertEqual((c.spec,self.e._physical_objects,self.e.elapsed_seconds,self.e.rng.getstate()),before)

if __name__=='__main__':unittest.main()
