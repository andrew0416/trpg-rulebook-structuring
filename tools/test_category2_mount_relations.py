"""Actual mount relation integrity; shared movement/capacity remain separate."""
from copy import deepcopy
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
import pokemon_activities as A,world_entities as W,state_codec as CODEC

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 known=_fixture_test_category2_body_modes.Tests.known
 def setup_rider(self,c):
  c.spec['edges']=['edge/탑승-기량'];c.spec['skills'].update({'곡예':3,'육상':3})
 def mount(self,c,target):return A.mounting(self.e,c,target=target,phase='mount',gm_mountable=True)
 def test_self_foreign_and_duplicate_identity_reject_before_actions_or_rng(self):
  self.setup_rider(self.p);self.begin(self.p)
  from engine import Combatant
  foreign=Combatant(self.r,deepcopy(self.t.spec))
  before=deepcopy((self.p.spec,self.p.budget,self.e.rng.getstate()))
  for target in (self.p,foreign):
   with self.assertRaises(ValueError):self.mount(self.p,target)
   self.assertEqual((self.p.spec,self.p.budget,self.e.rng.getstate()),before)
 def test_native_boarding_restores_actual_donor_and_rejects_cycles(self):
  self.setup_rider(self.a);self.assertTrue(self.mount(self.a,self.p)['passed'])
  self.e.gm.snapshot('mounted');e=self.restored();idx=W.actor_index(e)
  self.assertIs(W.mount_relation(idx,idx[self.a.entity_id]),idx[self.p.entity_id])
  self.a.spec.pop('mount_id');self.e.gm.restore('mounted')
  self.assertIs(W.mount_relation(W.actor_index(self.e),self.a),self.p)
  self.p.spec['mount_id']=self.t.entity_id
  with self.assertRaisesRegex(ValueError,'cycle'):W.require_mount_target(self.e,self.t,self.p)
  self.t.spec['mount_id']=self.p.entity_id
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
 def test_dangling_wrong_kind_and_self_relations_fail_save_but_valid_snapshot_repairs(self):
  self.setup_rider(self.a);self.mount(self.a,self.p);self.e.gm.snapshot('valid-mounted')
  for uid in ('missing-pokemon',self.a.entity_id,self.t.entity_id):
   self.a.spec['mount_id']=uid
   if uid==self.t.entity_id:self.t.kind='trainer';self.t.spec['kind']='trainer'
   with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
   self.e.gm.restore('valid-mounted')
   self.assertIs(W.mount_relation(W.actor_index(self.e),self.a),self.p)

if __name__=='__main__':unittest.main()
