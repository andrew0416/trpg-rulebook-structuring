"""Occupied planter ownership must survive native and both persistence gates."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import test_category2_cultivation_state as _fixture_test_category2_cultivation_state
from engine import Engine
import cultivation_state as P,cultivation_growth as GROWTH,state_codec as CODEC

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_cultivation_state.CultivationStateTests.setUpClass.__func__)
 setUp=_fixture_test_category2_cultivation_state.CultivationStateTests.setUp
 actor=_fixture_test_category2_cultivation_state.CultivationStateTests.actor
 act=_fixture_test_category2_cultivation_state.CultivationStateTests.act
 own=_fixture_test_category2_cultivation_state.CultivationStateTests.own
 plant_setup=_fixture_test_category2_cultivation_state.CultivationStateTests.plant_setup
 plant=_fixture_test_category2_cultivation_state.CultivationStateTests.plant
 restored=_fixture_test_category2_cultivation_state.CultivationStateTests.restored
 def setup_policy(self,policy):
  if policy=='sheet-current':
   self.e=Engine(self.rules,session_frequency=True,defer_session_refresh=True);self.e.gm.everyone=[self.a,self.p];self.e.begin_session('s0',[self.a])
 def prepare(self,policy='book-literal'):
  self.setup_policy(policy);self.plant_setup();self.plant('버치열매','p',planter_slot=0,planter_policy=policy)
 def test_orphaned_slots_and_selected_ownership_limit_fail_all_boundaries(self):
  for policy,count,slot in [('book-literal',0,0),('book-literal',1,1),('sheet-current',2,0)]:
   with self.subTest(policy=policy,count=count,slot=slot):
    self.setUp();self.prepare(policy)
    self.a.spec['items']['나무열매플랜터']=count
    self.a.spec['plants']['p']['planter_slot']=slot
    before=deepcopy(self.a.spec)
    for check in (lambda:P.validate(self.a),lambda:self.e.gm.snapshot('invalid'),lambda:CODEC.dump_engine(self.e),lambda:self.e.apply_mulch(self.a,'p',reason='must reject dangling container')):
     with self.assertRaises(ValueError):check()
     self.assertEqual(self.a.spec,before)
 def test_corrupt_external_restore_is_rejected_without_mutating_live_state(self):
  self.prepare();self.e.gm.snapshot('valid')
  self.a.spec['items']['나무열매플랜터']=0
  with patch.object(P,'validate',return_value={}),patch.object(GROWTH,'validate_world',return_value=True):
   saved=CODEC.dump_engine(self.e);self.e.gm.snapshot('invalid')
  self.a.spec['items']['나무열매플랜터']=1;before=deepcopy(self.a.spec)
  with self.assertRaises(ValueError):CODEC.load_engine(self.rules,saved)
  with self.assertRaises(ValueError):self.e.gm.restore('invalid')
  self.assertEqual(self.a.spec,before)
  self.e.gm.restore('valid');self.assertEqual(self.a.spec['items']['나무열매플랜터'],1)
 def test_valid_separate_owned_slots_and_sheet_capacity_roundtrip(self):
  for policy,count,slots in [('book-literal',2,[0,1]),('sheet-current',1,[0,0,0,0])]:
   with self.subTest(policy=policy):
    self.setUp();self.setup_policy(policy);self.plant_setup();self.a.spec['items']['나무열매플랜터']=count
    for n,slot in enumerate(slots):self.plant('버치열매',str(n),planter_slot=slot,planter_policy=policy)
    self.e.gm.snapshot('plants');loaded=self.restored()
    a=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id)
    self.assertEqual(P.validate(a),P.validate(self.a))
    self.e.gm.restore('plants');self.assertEqual(len(P.validate(self.a)),len(slots))

if __name__=='__main__':unittest.main()
