"""Shared weather appearance uses real weather producers, source ownership and restores."""
from copy import deepcopy
import unittest
from unittest.mock import patch
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
 def view(self,c):return self.e.capability_traits(c)['weathershape_appearance']
 def test_native_castform_four_actual_weather_moves_and_expiry(self):
  c=self.add(build_pokemon(self.r,'캐스퐁',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  baseline=deepcopy((c.stats,c.stages,c.types,c.hp,c.spec.get('species')))
  self.assertIsNone(self.view(c)['appearance'])
  for move,weather,color in [('쾌청','sunny','orange'),('비바라기','rain','blue and grey'),('싸라기눈','hail','light blue'),('모래바람','sandstorm','rocky brown')]:
   with self.subTest(weather=weather):
    self.known(self.p,move);self.begin(self.p);self.e.use_move(self.p,self.p,'move/'+move)
    state=self.view(c);self.assertEqual((state['weather'],state['appearance'],state['weather_source']),(weather,color,'move/'+move))
    self.assertTrue(state['weather_occurrence_id'])
    self.assertEqual((c.stats,c.stages,c.types,c.hp,c.spec.get('species')),baseline)
  self.e.end_of_turn(self.e._active_turn_actor)
  self.e.gm.set_weather('sunny',rounds=1);self.e.start_round(self.e.everyone);WEATHER.boundary(self.e,round_end=True)
  self.assertIsNone(self.view(c)['appearance'])
 def test_both_owners_both_restores_and_revocation_keep_shared_sources(self):
  for c in (self.a,self.p):
   G.grant(c,'capabilities','Weathershape','fixture:shape','fixture')
   G.grant(c,'capabilities','Bloom','fixture:bloom','fixture')
  self.e.gm.set_weather('rain',reason='observed rain');before={c.entity_id:self.e.capability_traits(c) for c in (self.a,self.p)}
  self.e.gm.snapshot('shape');e=self.restored();index={c.entity_id:c for c in e.everyone}
  for uid,view in before.items():self.assertEqual(e.capability_traits(index[uid]),view)
  self.e.gm.set_weather('sunny');self.assertEqual(self.view(self.a)['appearance'],'orange')
  self.assertEqual(self.e.capability_traits(self.a)['bloom_appearance']['appearance'],'pink flower')
  self.e.gm.restore('shape');self.assertEqual(self.e.capability_traits(self.a),before[self.a.entity_id])
  G.revoke(self.a,'fixture:shape');self.assertIsNone(self.view(self.a));self.assertIsNotNone(self.view(self.p))
  self.assertIsNotNone(self.e.capability_traits(self.a)['bloom_appearance'])
 def test_unclassified_weather_context_and_source_override_do_not_invent_forms(self):
  G.grant(self.p,'capabilities','날씨 형상','fixture:shape','fixture')
  WEATHER.observe_natural(self.e,'rain clouds',reason='appearance without rules equivalence')
  self.assertIsNone(self.view(self.p)['appearance'])
  WEATHER.observe_natural(self.e,'actual rain',treat_as='rain',reason='GM weather classification')
  self.assertEqual(self.view(self.p)['appearance'],'blue and grey')
  import survivalist_features as V
  V.vision(self.e,self.p)
  original=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid:uid+'/other' if uid=='capability/날씨-형상' else original(uid)):
   with self.assertRaises(ValueError):self.view(self.p)
  with self.assertRaises(ValueError):TRAITS.projection(self.p)
  WEATHER.clear(self.e,reason='weather cleared');self.e.weather='sunny'
  with self.assertRaises(ValueError):self.view(self.p)

if __name__=='__main__':unittest.main()
