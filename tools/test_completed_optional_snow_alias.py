"""CHB-WEATHER-003 requires actual generation and conditional-state consumers."""
from copy import deepcopy
from pathlib import Path
import unittest
from engine import Rules
import test_category2_homebrew_weather as _fixture_test_category2_homebrew_weather
import effects as EFFECTS
import homebrew_weather as H

ROOT=Path(__file__).resolve().parents[1]


class SnowAliasTests(_fixture_test_category2_homebrew_weather.Tests):
 @classmethod
 def setUpClass(cls):
  cls.r=Rules(ROOT,ruleset='all');cls.core=Rules(ROOT,ruleset='core');cls.errata=Rules(ROOT,ruleset='core+errata')
  cls._weather_fixture_rulings=deepcopy(cls.r.rulings)

 def test_actual_selected_snowscape_generates_hail_and_existing_conditions_read_the_alias(self):
  e,a,b=self.fixture();e.gm.set_move(a,'move/설경',reason='actual selected ninth generation move')
  self.cast(e,a,b,'move/설경')
  self.assertEqual(e.weather,'hail')
  self.assertTrue(EFFECTS.weather_matches(e,'snow'))
  self.assertTrue(EFFECTS.weather_matches(e,'hail'))
  self.assertEqual(a.move_uses['move/설경'],1);self.assertEqual(a.budget['standard'],0)
  self.assertEqual(e._weather_state['active']['source_id'],'move/설경')
  self.restored(e)

 def test_actual_snow_effect_producer_and_hail_condition_share_one_canonical_state(self):
  e,a,b=self.fixture()
  e.gm.set_weather('snow',rounds=5,reason='actual observed ninth generation Snow')
  self.assertEqual(e.weather,'hail');self.assertTrue(EFFECTS.weather_matches(e,'snow|sunny'))
  self.assertEqual(e._weather_state['active']['weather'],'hail')
  self.assertTrue(e.validate_state()['valid']);self.restored(e)


 def test_snowscape_actual_charge_damage_retirement_and_restore_keep_the_native_identity(self):
  import blessing_effects as B
  import weather_blessings as WB
  from test_category2_weather_charge_attacks import Tests as Attacks
  for kind in ('trainer','pokemon'):
   with self.subTest(kind=kind):
    e,a,b=self.fixture();user=a if kind=='trainer' else b;other=b if user is a else a
    e.gm.observe_loyalty(b,6,reason='actual known obedience')
    e.gm.set_move(user,'move/설경',reason='actual selected ninth generation Snow')
    self.cast(e,user,other,'move/설경')
    active=e._weather_state['active'];pool=next(r for r in B.live(user) if WB.is_weather(r))
    self.assertEqual(active['policy'],H.provenance('move/설경'))
    self.assertEqual(active['policy']['native_move_id'],'move/설경')
    self.assertIn('CHB-WEATHER-003',active['policy']['clause_ids'])
    self.assertEqual(pool['source'],'move/설경');self.assertEqual(pool['weather_occurrence_id'],active['id'])
    self.assertEqual(pool['weather_policy'],active['policy']);self.assertEqual(B.remaining(pool),2)
    self.assertEqual(pool['effect'],{'kind':'weather_effectiveness','boost_types':['얼음','비행'],'reduce_type':'불꽃'})
    self.assertEqual(user.move_uses['move/설경'],1)
    for _ in range(7):e.start_round([a,b])
    self.assertEqual((e.weather,e.weather_rounds),('hail',None));self.restored(e)
    e.end_encounter();self.assertIsNone(e.weather);self.assertFalse(any(WB.is_weather(r) for r in B.live(user)))
    self.assertEqual(e._weather_state['history'][-1]['source_id'],'move/설경');self.restored(e)
  e,a,b=self.fixture();a.side='party';b.side='wild'
  e.gm.observe_loyalty(b,6,reason='actual target obedience');e.gm.set_move(a,'move/설경',reason='known Snow')
  self.cast(e,a,b,'move/설경');pool=next(r for r in B.live(a) if WB.is_weather(r));identity=pool['id']
  Attacks.attack(self,e,a,b,'얼음뭉치');self.assertEqual(B.remaining(pool),1)
  self.assertEqual(pool['decisions'][-1]['multiplier_after'],1.5)
  Attacks.attack(self,e,b,a,'불꽃세례');closed=next(r for r in a.spec[B.HISTORY] if r['id']==identity)
  self.assertEqual(B.remaining(closed),0);self.assertEqual(closed['decisions'][-1]['multiplier_after'],0.5)
  self.assertEqual(e.weather,'hail');self.restored(e)
  e.gm.set_weather('rain',rounds=5,reason='actual replacement retires Snow parent')
  self.assertEqual(e._weather_state['history'][-1]['source_id'],'move/설경');self.restored(e)

 def test_native_snow_weather_policy_forgery_is_rejected_before_live_restore(self):
  from state_codec import StateCodecError
  e,a,b=self.fixture();e.gm.set_move(a,'move/설경',reason='known Snow');self.cast(e,a,b,'move/설경')
  before=deepcopy(e._weather_state['active']);e._weather_state['active']['policy']['native_move_id']='move/싸라기눈'
  self.assertFalse(e.validate_state()['valid'])
  with self.assertRaises(StateCodecError):e.export_state()
  e._weather_state['active']=before;self.assertTrue(e.validate_state()['valid']);self.restored(e)


if __name__=='__main__':unittest.main()
