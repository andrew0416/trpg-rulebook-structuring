"""Blender source end-of-next-turn timing, native evasion and persistence."""
from copy import deepcopy
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
import state_grants as G,blender_state as B

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 known=_fixture_test_category2_body_modes.Tests.known
 def activate(self,c):return self.e.activate_blender(c,reason='match observed surroundings')
 def grant(self,c):G.grant(c,'capabilities','녹아들기','fixture:blender','fixture')
 def test_both_kinds_shift_cost_and_end_of_next_owner_turn_not_start(self):
  for kind in ('trainer','pokemon'):
   self.setUp();c=self.a if kind=='trainer' else self.p;self.grant(c);self.begin(c);self.activate(c)
   self.assertEqual(c.budget['shift'],0);self.e.end_of_turn(c);self.assertTrue(self.e.blender_state(c)['active'])
   self.begin(self.t);self.e.end_of_turn(self.t);self.assertTrue(self.e.blender_state(c)['active'])
   self.begin(c);self.assertTrue(self.e.blender_state(c)['active']);self.e.end_of_turn(c)
   self.assertFalse(self.e.blender_state(c)['active'])
 def test_native_accuracy_distinguishes_ranges_and_does_not_stack(self):
  melee=self.r.move('move/몸통박치기');ranged=self.r.move('move/물대포')
  baselines=[next(n for n in range(2,16) if self.e.accuracy_check(self.p,self.t,m,fixed_roll=n)[0]) for m in (melee,ranged)]
  self.grant(self.t);self.begin(self.t);self.activate(self.t)
  for m,n,bonus in zip((melee,ranged),baselines,(2,4)):
   self.assertFalse(self.e.accuracy_check(self.p,self.t,m,fixed_roll=n+bonus-1)[0])
   self.assertTrue(self.e.accuracy_check(self.p,self.t,m,fixed_roll=n+bonus)[0])
  self.activate(self.t) # Standard downgraded to Shift; refresh same effect, no stacking.
  self.assertEqual(len(B.records(self.t)),1);self.assertEqual(self.t.budget['standard'],0)
 def test_both_restores_keep_owner_identity_and_actual_expiry(self):
  self.grant(self.p);self.begin(self.p);self.activate(self.p);self.e.gm.snapshot('blend');view=self.e.blender_state(self.p)
  e=self.restored();p=next(c for c in e.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(e.blender_state(p),view);self.assertIs(B.validate(p)['turn_owner'],p)
  e.end_of_turn(p);e.start_round(e.everyone);e.start_of_turn(p,initiative_count=20)
  self.assertTrue(e.blender_state(p)['active']);e.end_of_turn(p);self.assertFalse(e.blender_state(p)['active'])
  self.e.end_of_turn(self.p);self.begin(self.p);self.e.end_of_turn(self.p);self.e.gm.restore('blend')
  self.assertEqual(self.e.blender_state(self.p),view);self.assertIs(B.validate(self.p)['turn_owner'],self.p)
 def test_missing_grant_and_unknown_area_are_atomic(self):
  self.begin(self.t);before=deepcopy((self.t.spec,self.t.budget,self.e.rng.getstate()))
  with self.assertRaises(ValueError):self.activate(self.t)
  self.assertEqual((self.t.spec,self.t.budget,self.e.rng.getstate()),before)
  self.grant(self.t);self.activate(self.t);self.e.end_of_turn(self.t);self.t.pos=(6,3);self.known(self.p,'지진');self.begin(self.p)
  self.e.use_move(self.p,self.t,'move/지진')
  self.assertEqual(self.p.budget['standard'],0)
  rows=[row for row in self.e._move_completions.values() if row['actor'] is self.p and row['move_id']=='move/지진']
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['phase'],'complete')
  self.assertIn(self.t.entity_id,rows[0]['results'])

if __name__=='__main__':unittest.main()
