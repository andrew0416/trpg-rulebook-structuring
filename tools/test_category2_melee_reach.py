"""Reach is a live body capability; attack distance is not adjacency."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
import body_state as B,state_grants as G,state_codec as CODEC,weapon_actions as W

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 known=_fixture_test_category2_body_modes.Tests.known
 def grant(self,c):G.grant(c,'capabilities','도달','fixture:reach','fixture')
 def test_live_size_matrix_and_independent_grant_lifetimes(self):
  for actor in (self.a,self.p):
   self.assertEqual(B.melee_reach(actor),1);self.grant(actor)
   for size,expected in [('소형',2),('중형',2),('대형',3),('거대',3),('초거대',3),('Small',2),('Medium',2),('Large',3),('Huge',3),('Gigantic',3)]:
    actor.spec['size']=size;self.assertEqual(B.melee_reach(actor),expected)
   G.grant(actor,'capabilities','도달','fixture:second','fixture')
   G.revoke(actor,'fixture:reach');self.assertEqual(B.melee_reach(actor),3)
   G.revoke(actor,'fixture:second');self.assertEqual(B.melee_reach(actor),1)
 def test_exceptional_anatomy_observation_source_loss_and_both_restores(self):
  self.grant(self.p);self.p.spec['size']='중형'
  self.assertEqual(self.e.gm.observe_melee_reach(self.p,4,anatomy='long_limbs',reason='GM measured long arms'),4)
  self.e.gm.snapshot('reach');e=self.restored();p=next(c for c in e.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(B.melee_reach(p),4);self.assertEqual(p.spec[B.REACH_OBSERVATION]['source'],'capability/도달')
  self.p.spec['size']='대형';self.assertEqual(B.melee_reach(self.p),3)
  self.e.gm.observe_melee_reach(self.p,5,anatomy='very_large_body',reason='observed exceptional large body')
  self.assertEqual(B.melee_reach(self.p),5)
  self.e.gm.restore('reach');self.assertEqual(B.melee_reach(self.p),4)
  G.revoke(self.p,'fixture:reach');self.assertEqual(B.melee_reach(self.p),1)
  self.grant(self.p);self.assertEqual(B.melee_reach(self.p),4)
  self.p.spec[B.REACH_OBSERVATION]['value']=float('nan')
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
 def test_native_attack_and_automatic_approach_use_live_reach(self):
  self.grant(self.p);self.p.spec['size']='중형';self.t.pos=(5,3)
  self.known(self.p,'몸통박치기');self.begin(self.p)
  oldpos=self.p.pos;shift=self.p.budget['shift'];hp=self.t.hp
  with patch.object(self.e,'d20',return_value=15):self.e.use_move_on(self.p,self.t,'move/몸통박치기',self.e.everyone)
  self.assertEqual(self.p.pos,oldpos);self.assertEqual(self.p.budget['shift'],shift);self.assertLess(self.t.hp,hp)
  self.assertFalse(B.adjacent(self.p,self.t))
  self.begin(self.p);G.revoke(self.p,'fixture:reach')
  before=(self.t.hp,dict(self.p.budget),deepcopy(self.p.move_uses),self.e.rng.getstate())
  self.assertEqual(self.e.use_move(self.p,self.t,'move/몸통박치기'),0)
  self.assertEqual((self.t.hp,self.p.budget,self.p.move_uses,self.e.rng.getstate()),before)
 def test_observed_exception_changes_targeting_without_increasing_ranged_or_area(self):
  self.grant(self.p);self.t.pos=(7,3);self.p.spec['size']='중형'
  melee=self.r.move('move/몸통박치기');ranged=self.r.move('move/물대포')
  self.assertNotIn(self.t,self.e.targets_in_range(self.p,melee,self.e.everyone,self.t))
  old=deepcopy(W.range_spec(self.e,ranged))
  self.e.gm.observe_melee_reach(self.p,4,anatomy='long_limbs',reason='actual long reach')
  self.assertIn(self.t,self.e.targets_in_range(self.p,melee,self.e.everyone,self.t))
  self.assertEqual(W.range_spec(self.e,ranged),old)
  weapon=deepcopy(melee);weapon['_weapon_attack']={'range':{'origin':'melee'},'minimum_distance':0}
  W.validate_target(self.e,self.p,self.t,weapon)
  self.e.grid.blocking.add((5,3))
  self.assertNotIn(self.t,self.e.targets_in_range(self.p,melee,self.e.everyone,self.t))
  with self.assertRaises(ValueError):W.validate_target(self.e,self.p,self.t,weapon)
 def test_actual_equipped_weapon_attacks_at_extended_reach_after_restore(self):
  import turn as T
  self.grant(self.a)
  key=T.equip_weapon(self.e,self.a,{'name':'reach sword','kind':'소형 근접무기','grade':'조잡'})
  self.begin(self.a);self.e.gm.snapshot('armed reach')
  e=self.restored();a=next(c for c in e.everyone if c.entity_id==self.a.entity_id);target=next(c for c in e.everyone if c.entity_id==self.p.entity_id)
  before=target.hp
  with patch.object(e,'d20',return_value=15):damage=e.use_move(a,target,key,set_damage=True)
  self.assertGreater(damage,0);self.assertLess(target.hp,before);self.assertEqual(a.pos,(1,3))
  self.assertEqual(a.budget['standard'],0);self.assertFalse(B.adjacent(a,target))
 def test_native_unarmed_struggle_has_the_same_melee_boundary(self):
  self.t.pos=(5,3);self.begin(self.p)
  self.assertEqual(W.range_spec(self.e,self.r.move('struggle'))['origin'],'melee')
  before=(self.t.hp,dict(self.p.budget),self.e.rng.getstate())
  self.assertEqual(self.e.use_move(self.p,self.t,'struggle'),0)
  self.assertEqual((self.t.hp,self.p.budget,self.e.rng.getstate()),before)
  self.grant(self.p)
  with patch.object(self.e,'d20',return_value=15):damage=self.e.use_move(self.p,self.t,'struggle',set_damage=True)
  self.assertGreater(damage,0);self.assertEqual(self.p.budget['standard'],0)
 def test_invalid_observations_unknown_size_and_foreign_actor_are_atomic(self):
  with self.assertRaises(ValueError):self.e.gm.observe_melee_reach(self.p,4,anatomy='long_limbs',reason='no grant')
  self.grant(self.p);self.p.spec['size']='중형'
  for value,anatomy,reason in [(2,'long_limbs','too short'),(True,'long_limbs','bool'),(float('inf'),'long_limbs','infinite'),(4,'magic','unsourced'),(4,'long_limbs','')]:
   before=deepcopy(self.p.spec)
   with self.assertRaises(ValueError):self.e.gm.observe_melee_reach(self.p,value,anatomy=anatomy,reason=reason)
   self.assertEqual(self.p.spec,before)
  clone=deepcopy(self.p)
  with self.assertRaises(ValueError):self.e.gm.observe_melee_reach(clone,4,anatomy='long_limbs',reason='foreign actor')
  self.p.spec['size']=None
  with self.assertRaises(ValueError):B.melee_reach(self.p)

if __name__=='__main__':unittest.main()
