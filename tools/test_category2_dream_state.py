"""Partial Dream Reader prerequisite: actual sleep episode provenance and lifecycle."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
import dream_state as D,state_grants as G,state_codec as CODEC
from common_checks import PendingDecision

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 def reader(self):G.grant(self.p,'capabilities','Dream Reader','fixture:dream','fixture')
 def observe(self):return self.e.gm.observe_dream(self.t,'a distant blue mountain',reason='GM observed current dream')
 def test_actual_sleep_source_reapplication_cure_and_next_episode(self):
  self.reader();self.assertTrue(self.e.apply_status(self.t,'잠듦',source='item/꿈안개-1'))
  self.assertIsInstance(self.e.read_dream(self.p,self.t,share=True),PendingDecision)
  self.observe();first=self.e.read_dream(self.p,self.t,share=True)
  self.assertEqual(first['mode'],'brief_moving_image');self.assertEqual(first['sleep_serial'],1)
  self.assertFalse(self.e.apply_status(self.t,'잠듦',source='move/최면술'))
  self.assertEqual(self.e.read_dream(self.p,self.t,share=True),first)
  self.e.cure_status(self.t,'잠듦')
  with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t,share=True)
  self.e.apply_status(self.t,'잠듦',source='move/최면술')
  self.assertIsInstance(self.e.read_dream(self.p,self.t),PendingDecision)
  self.observe();self.assertEqual(self.e.read_dream(self.p,self.t)['sleep_serial'],2)
  with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t,share=True)
 def test_mindlock_current_capability_and_unknown_sleep_never_grant_sharing(self):
  self.reader();self.e.gm.add_condition(self.t,'잠듦',reason='GM sleep',force=True);self.observe()
  self.assertEqual(self.e.read_dream(self.p,self.t)['sleep_source'],'gm/state')
  with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t,share=True)
  G.grant(self.t,'capabilities','Mindlock','fixture:mindlock','fixture')
  with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t)
  G.revoke(self.t,'fixture:mindlock');self.assertEqual(self.e.read_dream(self.p,self.t)['content'],'a distant blue mountain')
  G.revoke(self.p,'fixture:dream')
  with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t)
  self.e.gm.remove_condition(self.t,'전부');self.assertIsNone(self.t.spec[D.KEY]['active'])
 def test_both_restores_and_corrupt_awake_episode_rejection(self):
  self.reader();self.e.apply_status(self.t,'잠듦',source='item/꿈안개-1');self.observe()
  expected=self.e.read_dream(self.p,self.t,share=True);self.e.gm.snapshot('dream')
  e=self.restored();idx={c.entity_id:c for c in e.everyone}
  self.assertEqual(e.read_dream(idx[self.p.entity_id],idx[self.t.entity_id],share=True),expected)
  self.e.cure_status(self.t,'잠듦');self.e.gm.restore('dream');self.assertEqual(self.e.read_dream(self.p,self.t,share=True),expected)
  self.t.conditions.remove('잠듦')
  with self.assertRaises(ValueError):self.e.gm.snapshot('bad')
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  with patch.object(D,'validate',return_value=None):saved=CODEC.dump_engine(self.e);self.e.gm.snapshot('bad')
  self.t.conditions.add('잠듦');before=deepcopy(self.t.spec)
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,saved)
  with self.assertRaises(ValueError):self.e.gm.restore('bad')
  self.assertEqual(self.t.spec,before);self.assertIn('잠듦',self.t.conditions)

if __name__=='__main__':unittest.main()
