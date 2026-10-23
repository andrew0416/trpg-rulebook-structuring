"""Actual pair-specific willingness gates only current surface-thought exchange."""
from copy import deepcopy,copy
from unittest.mock import patch
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
from builder import build_pokemon
import aura_pulse as P,state_grants as G,state_codec as CODEC
from common_checks import PendingDecision

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 def grant(self,c):G.grant(c,'capabilities','Aura Pulse','fixture:pulse','fixture')
 def opening(self,target,reader,allowed=True):return self.e.set_aura_openness(target,reader,allowed,reason='target voluntary declaration')
 def thought(self,text):return self.e.gm.observe_surface_thought(self.t,text,reason='current surface thought observed')
 def test_native_capability_projection_does_not_grant_reading_permission(self):
  sender=self.add(build_pokemon(self.r,'자시안 검왕',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  receipt=self.e.project_aura_thought(sender,self.t,'I want to talk')
  self.assertEqual(receipt['text'],'I want to talk');self.assertEqual(receipt['recipient_id'],self.t.entity_id)
  self.thought('What does this stranger want?');self.t.spec['hidden_memory']='never exposed'
  with self.assertRaises(ValueError):self.e.read_aura_thought(sender,self.t)
  self.opening(self.t,sender)
  result=self.e.read_aura_thought(sender,self.t);self.assertEqual(result['surface_thought'],'What does this stranger want?')
  self.assertNotIn('hidden_memory',str(result));self.assertNotIn('never exposed',str(result))
 def test_pair_specific_revoke_refresh_and_both_owner_kinds(self):
  for c in (self.a,self.p):self.grant(c)
  self.opening(self.t,self.a)
  self.assertIsInstance(self.e.read_aura_thought(self.a,self.t),PendingDecision)
  self.thought('first thought')
  with self.assertRaises(ValueError):self.e.read_aura_thought(self.p,self.t)
  self.opening(self.t,self.p);self.assertEqual(self.e.read_aura_thought(self.p,self.t)['surface_thought'],'first thought')
  self.thought('second thought');self.assertEqual(self.e.read_aura_thought(self.a,self.t)['thought_revision'],2)
  self.opening(self.t,self.a,False)
  with self.assertRaises(ValueError):self.e.read_aura_thought(self.a,self.t)
  self.assertEqual(self.e.read_aura_thought(self.p,self.t)['surface_thought'],'second thought')
  G.revoke(self.p,'fixture:pulse')
  with self.assertRaises(ValueError):self.e.read_aura_thought(self.p,self.t)
 def test_both_restores_preserve_pair_permission_thought_and_delivered_message(self):
  self.grant(self.a);self.opening(self.t,self.a);self.thought('saved thought');self.e.project_aura_thought(self.a,self.t,'saved message')
  expected=self.e.read_aura_thought(self.a,self.t);state=deepcopy(self.t.spec[P.KEY])
  self.e.gm.snapshot('pulse');loaded=self.restored();idx={c.entity_id:c for c in loaded.everyone}
  self.assertEqual(loaded.read_aura_thought(idx[self.a.entity_id],idx[self.t.entity_id]),expected)
  self.assertEqual(idx[self.t.entity_id].spec[P.KEY],state)
  self.opening(self.t,self.a,False);self.thought('new thought');self.e.gm.restore('pulse')
  self.assertEqual(self.e.read_aura_thought(self.a,self.t),expected);self.assertEqual(self.t.spec[P.KEY],state)
 def test_invalid_permission_foreign_actor_and_dangling_saved_relationship_reject(self):
  self.grant(self.a);self.opening(self.t,self.a);before=deepcopy(self.t.spec)
  for reader,allowed in [(self.a,1),(copy(self.a),True),(self.t,True)]:
   with self.assertRaises(ValueError):self.opening(self.t,reader,allowed)
   self.assertEqual(self.t.spec,before)
  del self.t.spec[P.KEY]['surface']
  with self.assertRaises(ValueError):self.e.read_aura_thought(self.a,self.t)
  self.t.spec.clear();self.t.spec.update(deepcopy(before))
  original=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid:uid+'/variant' if uid==P.SOURCE else original(uid)):
   with self.assertRaises(ValueError):self.e.read_aura_thought(self.a,self.t)
  self.t.spec[P.KEY]['open_to']['missing-reader']={'allowed':True,'reason':'invalid','revision':1}
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):self.e.gm.snapshot('bad')
  with patch.object(P,'validate_world',return_value=True):saved=CODEC.dump_engine(self.e);self.e.gm.snapshot('bad')
  self.t.spec.clear();self.t.spec.update(before)
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,saved)
  with self.assertRaises(ValueError):self.e.gm.restore('bad')
  self.assertEqual(self.t.spec,before)

if __name__=='__main__':unittest.main()
