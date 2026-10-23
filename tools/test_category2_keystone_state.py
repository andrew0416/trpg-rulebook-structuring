"""Actual collected stones, two-point payment and both restoration paths."""
from copy import deepcopy,copy
from unittest.mock import patch
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
from builder import build_pokemon
import keystone_state as K,world_entities as W,state_codec as CODEC
class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 def setUp(self):
  _fixture_test_category2_body_modes.Tests.setUp(self)
  self.s=self.add(build_pokemon(self.r,'화강돌',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':6}))
 def stone(self,uid,original=None):
  W.register_object(self.e,uid,location={'kind':'grid','cell':(5,5)},reason='actual recovered stone')
  return self.e.gm.observe_collected_keystone(self.a,uid,reason='trainer recovered an Odd Keystone',original_for=original)
 def link(self,uid):return self.e.link_keystone(self.s,uid,collector=self.a,reason='synchronize collected stone')
 def test_multiple_actual_stones_pay_once_per_pokemon_link(self):
  for uid in ('stone1','stone2'):self.stone(uid);self.link(uid)
  self.assertEqual(self.s.spec['tutor_points'],2)
  self.assertEqual({x['object']['id'] for x in self.e.linked_keystones(self.s)},{'stone1','stone2'})
  before=deepcopy(self.s.spec)
  with self.assertRaises(ValueError):self.link('stone1')
  self.assertEqual(self.s.spec,before)
  other=self.add(build_pokemon(self.r,'화강돌',20,moves=[],abilities=[],extra={'tutor_points':2}))
  self.e.link_keystone(other,'stone1',collector=self.a,reason='independent synchronization')
  self.assertEqual(other.spec['tutor_points'],0)
  self.assertEqual(self.s.spec['tutor_points'],2)
 def test_invalid_collection_original_missing_balance_and_capability_are_atomic(self):
  self.stone('original',self.s);self.stone('extra')
  for uid in ('original','missing'):
   before=deepcopy(self.s.spec)
   with self.assertRaises(ValueError):self.link(uid)
   self.assertEqual(self.s.spec,before)
  with self.assertRaises(ValueError):self.e.gm.observe_collected_keystone(self.a,'extra',reason='overwrite')
  for balance in (0,1,True,None):
   self.s.spec['tutor_points']=balance;before=deepcopy(self.s.spec)
   with self.assertRaises(ValueError):self.link('extra')
   self.assertEqual(self.s.spec,before)
  self.s.spec['tutor_points']=2
  with self.assertRaises(ValueError):self.e.link_keystone(self.p,'extra',collector=self.a,reason='wrong species')
  with self.assertRaises(ValueError):self.e.link_keystone(copy(self.s),'extra',collector=self.a,reason='copied actor')
  with patch.object(K.G,'effective_capabilities',return_value=[]):
   with self.assertRaises(ValueError):self.link('extra')
  selected=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid:uid+'/variant' if uid==K.SOURCE else selected(uid)):
   with self.assertRaises(ValueError):self.link('extra')
  self.e._physical_objects['extra']['destroyed']={'reason':'broken'}
  with self.assertRaises(ValueError):self.link('extra')
  self.assertEqual(self.s.spec['tutor_points'],2)
 def test_native_links_and_paid_balance_survive_both_restores(self):
  self.stone('extra');self.link('extra');expected=self.e.linked_keystones(self.s)
  self.e.gm.snapshot('keystones');loaded=self.restored();s=next(c for c in loaded.everyone if c.entity_id==self.s.entity_id)
  self.assertEqual(loaded.linked_keystones(s),expected);self.assertEqual(s.spec['tutor_points'],4)
  self.stone('second');self.link('second');self.e.gm.restore('keystones')
  self.assertEqual(self.e.linked_keystones(self.s),expected);self.assertEqual(self.s.spec['tutor_points'],4)
 def test_dangling_links_reject_save_and_both_load_paths(self):
  self.stone('extra');self.link('extra');before=deepcopy(self.s.spec)
  self.s.spec[K.KEY]['extra']['stone_id']='missing'
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  self.s.spec.clear();self.s.spec.update(deepcopy(before))
  obj=self.e._physical_objects.pop('extra')
  with self.assertRaises(ValueError):self.e.gm.snapshot('bad')
  with patch.object(K,'validate_world',return_value=True):saved=CODEC.dump_engine(self.e);self.e.gm.snapshot('bad')
  self.e._physical_objects['extra']=obj
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,saved)
  with self.assertRaises(ValueError):self.e.gm.restore('bad')
  self.assertEqual(self.s.spec,before);self.assertIn('extra',self.e._physical_objects)
 def prepare_warp(self):
  self.s.pos=(2,5)
  self.e.gm.observe_loyalty(self.s,6,reason='known obedience')
  self.stone('near');self.link('near')
  W.register_object(self.e,'near',location={'kind':'grid','cell':(12,5)},reason='grounded Keystone position')
 def test_warp_native_standard_ten_metres_no_shift_or_tutor_repayment(self):
  self.prepare_warp();_fixture_test_category2_body_modes.Tests.begin(self,self.s);before=self.s.spec['tutor_points']
  self.s.spec['_teleport']={'used_round':self.e.round_no}
  out=self.e.keystone_warp(self.s,'near',reason='actual grounded destination')
  self.assertEqual(out['distance'],10);self.assertEqual(self.s.pos,(12,5))
  self.assertEqual(self.s.budget['standard'],0);self.assertEqual(self.s.budget['shift'],1)
  self.assertEqual(self.s.spec['tutor_points'],before)
 def test_warp_range_occupancy_unknown_and_unlinked_do_not_spend(self):
  from common_checks import PendingDecision
  self.prepare_warp();_fixture_test_category2_body_modes.Tests.begin(self,self.s)
  before=(self.s.pos,deepcopy(self.s.budget),self.s.spec['tutor_points'])
  for position in [(13,5),self.t.pos]:
   W.register_object(self.e,'near',location={'kind':'grid','cell':position},reason='ground observation')
   with self.assertRaises(ValueError):self.e.keystone_warp(self.s,'near',reason='test boundary')
   self.assertEqual((self.s.pos,self.s.budget,self.s.spec['tutor_points']),before)
  W.register_object(self.e,'near',location={'kind':'unknown'},reason='location lost')
  self.assertIsInstance(self.e.keystone_warp(self.s,'near',reason='unknown'),PendingDecision)
  with self.assertRaises(ValueError):self.e.keystone_warp(self.s,'unlinked',reason='not synchronized')
  self.assertEqual((self.s.pos,self.s.budget,self.s.spec['tutor_points']),before)
 def test_warp_uses_restored_links_and_repositioned_actual_object(self):
  self.prepare_warp();self.e.gm.snapshot('warp');loaded=self.restored()
  actor=next(c for c in loaded.everyone if c.entity_id==self.s.entity_id)
  loaded.keystone_warp(actor,'near',reason='restored target');self.assertEqual(actor.pos,(12,5))
  W.register_object(self.e,'near',location={'kind':'grid','cell':(9,5)},reason='moved physical stone')
  self.e.keystone_warp(self.s,'near',reason='current target');self.assertEqual(self.s.pos,(9,5))
  self.e.gm.restore('warp');self.e.keystone_warp(self.s,'near',reason='restored target')
  self.assertEqual(self.s.pos,(12,5));self.assertEqual(self.s.spec['tutor_points'],4)
if __name__=='__main__':unittest.main()
