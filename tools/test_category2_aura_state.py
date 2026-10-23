"""Native Aura Reader information is separate from mind reading and inferred morality."""
from copy import deepcopy,copy
from unittest.mock import patch
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
from builder import build_pokemon
import aura_state as A,state_grants as G,state_codec as CODEC
from common_checks import PendingDecision

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 def observe(self,**kw):
  values=dict(living=True,color='blue-green',personality='patient',worldview='values cooperation',brightness='bright',mood='content',intentions='wants to help',reason='GM current aura observation')
  values.update(kw);return self.e.gm.observe_aura(self.t,**values)
 def grant(self,c):G.grant(c,'capabilities','Aura Reader','fixture:reader','fixture')
 def test_native_species_reads_color_and_brightness_without_exposing_other_thoughts(self):
  reader=self.add(build_pokemon(self.r,'맨돌핀',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  self.t.spec['private_thought']='unrelated hidden information';self.observe()
  out=self.e.read_aura(reader,self.t)
  self.assertEqual(out['color_information'],{'color':'blue-green','personality':'patient','worldview':'values cooperation'})
  self.assertEqual(out['brightness_information'],{'brightness':'bright','mood':'content','intentions':'wants to help'})
  self.assertNotIn('private_thought',str(out));self.assertEqual(out['source'],A.SOURCE)
  G.grant(self.t,'capabilities','Mindlock','fixture:mindlock','fixture')
  self.assertEqual(self.e.read_aura(reader,self.t),out) # Source does not list Aura Reader.
 def test_both_reader_kinds_live_observations_and_both_restores(self):
  for reader in (self.a,self.p):self.grant(reader)
  self.observe();before={c.entity_id:self.e.read_aura(c,self.t) for c in (self.a,self.p)}
  self.e.gm.snapshot('aura');e=self.restored();idx={c.entity_id:c for c in e.everyone}
  for uid,result in before.items():self.assertEqual(e.read_aura(idx[uid],idx[self.t.entity_id]),result)
  self.observe(color='gold',personality='newly resolute',worldview='new priorities',brightness='dark',mood='grieving',intentions=None)
  out=self.e.read_aura(self.a,self.t);self.assertEqual(out['observation_revision'],2)
  self.assertEqual(out['brightness_information']['mood'],'grieving');self.assertIsNone(out['brightness_information']['intentions'])
  self.e.gm.restore('aura');self.assertEqual(self.e.read_aura(self.a,self.t),before[self.a.entity_id])
  G.revoke(self.a,'fixture:reader')
  with self.assertRaises(ValueError):self.e.read_aura(self.a,self.t)
  self.assertEqual(self.e.read_aura(self.p,self.t),before[self.p.entity_id])
 def test_unknown_living_identity_and_capability_are_not_invented(self):
  self.grant(self.a);self.assertIsInstance(self.e.read_aura(self.a,self.t),PendingDecision)
  self.e.gm.observe_aura(self.t,living=True,brightness='dark',reason='appearance only')
  self.assertEqual(self.e.read_aura(self.a,self.t)['brightness_information'],{'brightness':'dark','mood':None,'intentions':None})
  for reader,target in [(self.p,self.t),(self.a,self.a),(self.a,copy(self.t))]:
   with self.assertRaises(ValueError):self.e.read_aura(reader,target)
  self.e.gm.observe_aura(self.t,living=False,reason='GM identifies a nonliving entity')
  with self.assertRaises(ValueError):self.e.read_aura(self.a,self.t)
  self.observe();self.t.dead=True
  with self.assertRaises(ValueError):self.e.read_aura(self.a,self.t)
  before=deepcopy(self.t.spec)
  with self.assertRaises(ValueError):self.observe()
  self.assertEqual(self.t.spec,before)
 def test_invalid_observations_and_external_restores_are_atomic(self):
  self.grant(self.a);self.observe();before=deepcopy(self.t.spec)
  for change in [dict(living='yes'),dict(color=None),dict(brightness='evil'),dict(reason=''),dict(living=False)]:
   with self.assertRaises(ValueError):self.observe(**change)
   self.assertEqual(self.t.spec,before)
  self.t.spec[A.KEY]['target_id']=self.a.entity_id
  with self.assertRaises(ValueError):self.e.gm.snapshot('bad')
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  with patch.object(A,'validate',return_value=None):
   saved=CODEC.dump_engine(self.e);self.e.gm.snapshot('bad')
  self.t.spec.clear();self.t.spec.update(before)
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,saved)
  with self.assertRaises(ValueError):self.e.gm.restore('bad')
  self.assertEqual(self.t.spec,before)
  original=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid:uid+'/variant' if uid==A.SOURCE else original(uid)):
   with self.assertRaises(ValueError):self.e.read_aura(self.a,self.t)

if __name__=='__main__':unittest.main()
