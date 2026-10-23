"""Actual equipped Umbrella masking and source-owned qualitative appearance."""
import test_category2_optional_catalog_nine as _fixture_test_category2_optional_catalog_nine
import items as ITEMS
import state_grants as GRANTS
import world_entities as WORLD

class WeatherAppearanceMaskTests(_fixture_test_category2_optional_catalog_nine.OptionalCatalogNineTests):
 def test_actual_trainer_umbrella_masks_bloom_and_weathershape_without_unsourcing_global_weather(self):
  e,a,_,_=self.fixture()
  for name in ('만개','날씨 형상'):
   GRANTS.grant(a,'capabilities',name,'test:actual:weather-capabilities','actual owned selected qualitative capability')
  uid='weather-appearance:actual-umbrella'
  WORLD.register_object(e,uid,location={'kind':'unknown'},reason='actual trainer-held selected Umbrella',
       kind='item_instance',item_rule_id='item/만능우산',owner_id=a.entity_id)
  ITEMS.register_item(e,a,'item/만능우산',source_instance_id=uid,as_held=False)
  for weather in ('sunny','rain'):
   e.gm.set_weather(weather,rounds=None,reason='actual independent sourced global weather')
   source=e._weather_state['active']['id']
   view=e.capability_traits(a)
   self.assertEqual(view['bloom_appearance']['form'],'overcast')
   self.assertIsNone(view['bloom_appearance']['weather'])
   self.assertIsNone(view['weathershape_appearance']['appearance'])
   self.assertIsNone(view['weathershape_appearance']['weather_source'])
   self.assertEqual((e.weather,e._weather_state['active']['id']),(weather,source))
   self.assertTrue(e.validate_state()['valid']);self.restored(e)
  ITEMS.unregister_item(e,a,registration_key=self.registration_key(a,uid))
  self.assertEqual(e.capability_traits(a)['weathershape_appearance']['appearance'],'blue and grey')
  e.gm.set_weather('sunny',rounds=None,reason='actual global sun after Umbrella withdrawal')
  view=e.capability_traits(a)
  self.assertEqual(view['weathershape_appearance']['appearance'],'orange')
  self.assertEqual(view['bloom_appearance']['form'],'sunshine')
  GRANTS.revoke(a,'test:actual:weather-capabilities')
  self.assertIsNone(e.capability_traits(a)['bloom_appearance'])
  self.assertIsNone(e.capability_traits(a)['weathershape_appearance'])
  self.assertTrue(e.validate_state()['valid']);self.restored(e)
