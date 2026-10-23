"""Voluntary sound suppression uses actual grants and native action contexts."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
import state_grants as G,sound_state as SOUND,state_codec as CODEC

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 known=_fixture_test_category2_body_modes.Tests.known
 def grant(self,c,name):G.grant(c,'capabilities',name,'fixture:sound','fixture')
 def choose(self,c,quiet=True):return self.e.choose_silence(c,quiet,reason='actor chooses whether to make noise')
 def test_dead_silent_covers_breath_heartbeat_and_other_sounds_without_stat_bonus(self):
  for c in (self.a,self.p):
   self.begin(c);self.grant(c,'숨죽이기');self.assertIsNone(self.e.sound_state(c)['all_sounds'])
   before=deepcopy((c.budget,c.stats,c.spec.get('skills'),c._action_history))
   view=self.choose(c)
   for name in ('all_sounds','breathing','heartbeat','movement','ranged_attack'):self.assertEqual(view[name],'capability/숨죽이기')
   self.assertEqual((c.budget,c.stats,c.spec.get('skills'),c._action_history),before)
   self.choose(c,False);self.assertIsNone(self.e.sound_state(c)['all_sounds'])
 def test_native_movement_observes_stealth_source_without_extra_roll_or_speed(self):
  self.grant(self.a,'은밀');self.choose(self.a);self.begin(self.a)
  rng=self.e.rng.getstate();self.e.approach(self.a,self.t)
  event=self.e.sound_state(self.a)['last_event'];self.assertEqual(event['activity'],'movement');self.assertEqual(event['source'],'capability/은밀')
  self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.a.budget['shift'],0)
  self.assertIsNone(self.e.sound_state(self.a)['heartbeat'])
 def test_native_ranged_attack_distinguishes_dead_silent_from_stealth(self):
  for name,source in (('은밀',None),('Dead Silent','capability/숨죽이기')):
   self.setUp();self.grant(self.p,name);self.choose(self.p);self.known(self.p,'물대포');self.begin(self.p)
   with patch.object(self.e,'d20',return_value=15):self.e.use_move(self.p,self.t,'move/물대포',set_damage=True)
   event=self.e.sound_state(self.p)['last_event']
   self.assertEqual(event['activity'],'ranged_attack');self.assertEqual(event['source'],source);self.assertEqual(event['move_id'],'move/물대포')
 def test_preferences_and_actual_event_restore_but_revoked_grants_do_not_silence(self):
  self.grant(self.a,'Dead Silent');self.choose(self.a);self.begin(self.a);self.e.approach(self.a,self.t)
  self.e.gm.snapshot('silent');view=self.e.sound_state(self.a)
  e=self.restored();a=next(c for c in e.everyone if c.entity_id==self.a.entity_id);self.assertEqual(e.sound_state(a),view)
  G.revoke(self.a,'fixture:sound');self.assertIsNone(self.e.sound_state(self.a)['all_sounds'])
  self.assertEqual(self.e.sound_state(self.a)['last_event'],view['last_event'])
  self.e.gm.restore('silent');self.assertEqual(self.e.sound_state(self.a),view)
  self.a.spec[SOUND.KEY]['quiet']=1
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
 def test_invalid_choice_has_no_state_cost_and_quiet_is_not_automatic(self):
  self.begin(self.p);before=deepcopy((self.p.spec,self.p.budget))
  with self.assertRaises(ValueError):self.choose(self.p)
  self.assertEqual((self.p.spec,self.p.budget),before)
  self.grant(self.p,'숨죽이기')
  with self.assertRaises(ValueError):self.choose(self.p,1)
  self.assertNotIn(SOUND.KEY,self.p.spec)

 def test_native_species_source_and_malformed_choice_are_not_overwritten(self):
  from builder import build_pokemon
  c=self.add(build_pokemon(self.r,'코일',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  self.assertEqual(self.choose(c)['all_sounds'],'capability/숨죽이기')
  c.spec[SOUND.KEY]['quiet']=1;before=deepcopy(c.spec)
  with self.assertRaises(ValueError):self.choose(c,False)
  self.assertEqual(c.spec,before)

if __name__=='__main__':unittest.main()
