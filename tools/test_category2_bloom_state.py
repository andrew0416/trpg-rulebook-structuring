"""Bloom is a live source-owned appearance, not Flower Gift's stat effect."""
from copy import deepcopy
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
from builder import build_pokemon
import state_grants as G,weather_state as WEATHER,capability_traits as TRAITS

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 known=_fixture_test_category2_body_modes.Tests.known
 def view(self,c):return self.e.capability_traits(c)['bloom_appearance']
 def test_native_species_and_actual_sunny_move_change_only_appearance(self):
  c=self.add(build_pokemon(self.r,'체리꼬',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  before=deepcopy((c.stats,c.stages,c.types,c.hp,c.spec.get('species')))
  import survivalist_features as V
  vision=V.vision(self.e,c)
  self.assertEqual(self.view(c)['form'],'overcast')
  self.known(self.p,'쾌청');self.begin(self.p);self.e.use_move(self.p,self.p,'move/쾌청')
  self.assertEqual(self.view(c)['appearance'],'pink flower');self.assertEqual(self.view(c)['weather_source'],'move/쾌청')
  self.assertEqual((c.stats,c.stages,c.types,c.hp,c.spec.get('species')),before)
  self.assertEqual(V.vision(self.e,c),vision)
  WEATHER.clear(self.e,reason='sun ended');self.assertEqual(self.view(c)['appearance'],'purple bud')
 def test_grants_both_kinds_and_both_restores_follow_replacement_and_revocation(self):
  for c in (self.a,self.p):G.grant(c,'capabilities','Bloom','fixture:bloom','fixture')
  self.e.gm.set_weather('sunny',reason='observed source');views=[self.view(c) for c in (self.a,self.p)]
  self.e.gm.snapshot('bloom');e=self.restored();idx={c.entity_id:c for c in e.everyone}
  for c,view in zip((self.a,self.p),views):self.assertEqual(e.capability_traits(idx[c.entity_id])['bloom_appearance'],view)
  self.e.gm.set_weather('rain');self.assertTrue(all(self.view(c)['form']=='overcast' for c in (self.a,self.p)))
  self.e.gm.restore('bloom');self.assertEqual(self.view(self.a),views[0])
  G.revoke(self.a,'fixture:bloom');self.assertIsNone(self.view(self.a));self.assertEqual(self.view(self.p)['form'],'sunshine')
 def test_natural_weather_requires_explicit_equivalence_and_timer_expiry_is_live(self):
  G.grant(self.p,'capabilities','만개','fixture:bloom','fixture')
  WEATHER.observe_natural(self.e,'bright sky',reason='description only')
  self.assertEqual(self.view(self.p)['form'],'overcast')
  WEATHER.observe_natural(self.e,'bright sky',treat_as='sunny',reason='GM classifies sunlight')
  self.assertEqual(self.view(self.p)['form'],'sunshine')
  self.e.gm.set_weather('sunny',rounds=1);self.e.start_round(self.e.everyone)
  WEATHER.boundary(self.e,round_end=True);self.assertEqual(self.view(self.p)['form'],'overcast')
  self.e.weather='sunny'
  with self.assertRaises(ValueError):self.view(self.p)
  with self.assertRaises(ValueError):TRAITS.projection(self.p)

if __name__=='__main__':unittest.main()
