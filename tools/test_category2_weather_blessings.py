"""Native weather pool lifecycle; attack spending remains a separate adapter."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_category2_homebrew_weather as _fixture_test_category2_homebrew_weather
import blessing_effects as B, weather_blessings as WB, effect_instances as E
from state_codec import StateCodecError

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_homebrew_weather.Tests.setUpClass.__func__)
 fixture=_fixture_test_category2_homebrew_weather.Tests.fixture
 cast=_fixture_test_category2_homebrew_weather.Tests.cast
 restored=_fixture_test_category2_homebrew_weather.Tests.restored
 resources=_fixture_test_category2_homebrew_weather.Tests.resources
 def pool(self,a):return next(r for r in B.live(a) if WB.is_weather(r))
 def test_replacement_and_end_remove_only_parent_linked_weather_pools(self):
  e,a,b=self.fixture();e.gm.set_move(a,'move/빛의장막',reason='known screen')
  self.cast(e,a,b,'move/빛의장막');screen=B.live(a)[0]['id']
  self.cast(e,a,b,'move/비바라기');old=deepcopy(self.pool(a))
  self.cast(e,a,b,'move/쾌청');new=self.pool(a)
  self.assertNotEqual(old['id'],new['id']);self.assertEqual(B.remaining(new),2)
  archived=next(r for r in a.spec[B.HISTORY] if r['id']==old['id'])
  self.assertEqual(archived[E.KEY]['end_event']['occurrence_id'],old['weather_occurrence_id'])
  self.assertIn(screen,[r['id'] for r in B.live(a)])
  e.gm.snapshot('linked');e.gm.set_weather(None);e.gm.restore('linked')
  n=self.restored(e);self.assertTrue(n.validate_state()['valid'])
  n.end_encounter();actors=n.gm.everyone;owner=next(c for c in actors if c.entity_id==a.entity_id)
  self.assertFalse(any(WB.is_weather(r) for r in B.live(owner)))
  self.assertIn(screen,[r['id'] for r in B.live(owner)])
  self.restored(n)

 def test_native_court_change_moves_scope_then_weather_change_retires_swapped_pool(self):
  e,a,b=self.fixture();a.side='party';b.side='wild'
  e.gm.observe_loyalty(b,6,reason='known obedience')
  self.cast(e,a,b,'move/모래바람');identity=self.pool(a)['id']
  e.gm.set_move(b,'move/코트체인지',reason='known exchange')
  e.start_round([a,b]);e.start_of_turn(b,initiative_count=12)
  e.use_move(b,b,'move/코트체인지');e.end_of_turn(b)
  self.assertEqual(B.side(self.pool(a)),'wild');self.assertEqual(B.remaining(self.pool(a)),2)
  self.assertEqual(self.pool(a)['id'],identity);self.assertFalse(B.live(b))
  a.side='third';self.assertEqual(B.side(self.pool(a)),'wild')
  n=self.restored(e);n.gm.observe_natural_weather('storm',treat_as='rain',reason='GM equivalence')
  self.assertFalse(any(WB.is_weather(r) for c in n.gm.everyone for r in B.live(c)))
  self.restored(n)

 def test_native_defog_removes_weather_and_pool_without_regenerating_it(self):
  e,a,b=self.fixture();self.cast(e,a,b,'move/싸라기눈')
  e.gm.set_move(a,'move/안개제거',reason='known clearing')
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=12)
  with patch.object(e,'d20',return_value=20):e.use_move(a,a,'move/안개제거')
  self.assertFalse(any(WB.is_weather(r) for r in B.live(a)))
  self.assertIsNone(e.weather);n=self.restored(e)
  self.assertFalse(any(WB.is_weather(r) for c in n.gm.everyone for r in B.live(c)))
  n.gm.set_weather(None);self.restored(n)

 def test_missing_or_forged_pool_rejects_restore_without_mutating_live_state(self):
  e,a,b=self.fixture();self.cast(e,a,b,'move/비바라기');baseline=deepcopy(a.blessings)
  pool=self.pool(a)
  for change in ('missing','wrong_parent','capacity','fake_use'):
   a.blessings=deepcopy(baseline)
   if change=='missing':a.blessings=[]
   elif change=='wrong_parent':self.pool(a)['weather_occurrence_id']=999
   elif change=='capacity':self.pool(a)[E.KEY]['capacity']['limit']=3
   else:self.pool(a)['decisions']=[{'selected':True}]
   self.assertFalse(e.validate_state()['valid'])
   with self.assertRaises(StateCodecError):e.export_state()
  a.blessings=baseline;self.restored(e)
  payload=e.export_state()
  node=next(n for n in payload['nodes'].values() if n['kind']=='dict' and
            any(pair[0]=='weather_occurrence_id' for pair in n['items']))
  node['items']=[pair if pair[0]!='weather_occurrence_id' else [pair[0],999] for pair in node['items']]
  from engine import Engine
  with self.assertRaises(StateCodecError):Engine.import_state(e.r,payload)
  self.assertEqual(a.blessings,baseline)

 def test_invalid_team_preflight_preserves_weather_cost_rng_and_existing_pool(self):
  e,a,b=self.fixture();self.cast(e,a,b,'move/비바라기')
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=12);a.side=''
  before=(self.resources(e,a),deepcopy(a.blessings),deepcopy(a.spec))
  with self.assertRaisesRegex(ValueError,'beneficiary side'):e.use_move(a,a,'move/쾌청')
  self.assertEqual((self.resources(e,a),a.blessings,a.spec),before)

 def test_overridden_weather_cannot_pay_before_invalid_outgoing_pool_is_rejected(self):
  e,a,b=self.fixture();self.cast(e,a,b,'move/비바라기')
  e.rule_effect('move/쾌청','set',{'effects_exec':[{'type':'set_weather','weather':'sunny','rounds':2}]},
                reason='explicit finite weather override')
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=12)
  a.blessings=[];before=self.resources(e,a)
  with self.assertRaisesRegex(ValueError,'exactly one'):e.use_move(a,a,'move/쾌청')
  self.assertEqual(self.resources(e,a),before)
