"""Native invisibility lifecycle, time uncertainty, combat and restoration."""
from copy import deepcopy
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
import state_grants as G,invisibility_state as V,state_codec as CODEC

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 known=_fixture_test_category2_body_modes.Tests.known
 def grant(self,c):G.grant(c,'capabilities','투명','fixture:invisible','fixture')
 def change(self,c,value):return self.e.change_invisibility(c,value,reason='actual voluntary invisibility')
 def view(self,c):return self.e.invisibility_state(c)
 def test_both_kinds_native_shift_and_free_end_no_invented_movement(self):
  for c in (self.a,self.p):
   self.grant(c);self.begin(c);pos=c.pos
   self.assertTrue(self.change(c,True)['active']);self.assertEqual(c.budget['shift'],0);self.assertEqual(c.pos,pos)
   budget=deepcopy(c.budget);self.assertEqual(self.change(c,False)['phase'],'cooldown');self.assertEqual(c.budget,budget)
   self.assertEqual(self.view(c)['ready_after_elapsed'],120)
 def test_native_single_and_multi_target_moves_reject_before_cost_or_rng(self):
  self.grant(self.p);self.known(self.p,'물대포');self.begin(self.p);self.change(self.p,True)
  before=deepcopy((self.p.budget,self.p.move_uses,self.e.rng.getstate(),self.p._action_history))
  for run in (lambda:self.e.use_move(self.p,self.t,'move/물대포'),lambda:self.e.use_move(self.p,self.t,'move/물대포',free_action=True),lambda:self.e.use_move_on(self.p,self.t,'move/물대포',self.e.everyone)):
   with self.assertRaisesRegex(ValueError,'invisibility'):run()
   self.assertEqual((self.p.budget,self.p.move_uses,self.e.rng.getstate(),self.p._action_history),before)
  self.change(self.p,False);self.e.use_move(self.p,self.t,'move/물대포',set_damage=True)
  self.assertEqual(self.p.budget['standard'],0)
 def test_accuracy_requires_four_more_without_changing_natural_twenty(self):
  move=self.r.move('move/물대포')
  base=next(n for n in range(2,20) if self.e.accuracy_check(self.p,self.t,move,fixed_roll=n)[0])
  self.grant(self.t);self.change(self.t,True)
  self.assertFalse(self.e.accuracy_check(self.p,self.t,move,fixed_roll=base+3)[0])
  self.assertTrue(self.e.accuracy_check(self.p,self.t,move,fixed_roll=base+4)[0])
  self.assertTrue(self.e.accuracy_check(self.p,self.t,move,fixed_roll=20)[0])
  self.change(self.t,False);self.assertTrue(self.e.accuracy_check(self.p,self.t,move,fixed_roll=base)[0])
 def test_automatic_expiry_and_overshoot_use_actual_end_not_query_time(self):
  self.grant(self.p);self.change(self.p,True);self.e.advance_time(239)
  self.assertTrue(self.view(self.p)['active']);self.e.advance_time(1)
  self.assertEqual(self.view(self.p)['phase'],'cooldown')
  self.e.advance_time(359)
  with self.assertRaises(ValueError):self.change(self.p,True)
  self.e.advance_time(1);self.assertEqual(self.view(self.p)['phase'],'ready')
  self.change(self.p,True);self.e.advance_time(700);self.assertEqual(self.view(self.p)['phase'],'ready')
  self.change(self.p,True);self.assertEqual(self.view(self.p)['elapsed_bounds'],[0,0])
 def test_manual_elapsed_plus_two_minutes_cooldown_and_both_restores(self):
  self.grant(self.p);self.change(self.p,True);self.e.advance_time(37);self.change(self.p,False)
  self.assertEqual(self.view(self.p)['ready_after_elapsed'],194)
  self.e.gm.snapshot('invisible-cooldown');view=self.view(self.p)
  e=self.restored();p=next(c for c in e.everyone if c.entity_id==self.p.entity_id);self.assertEqual(e.invisibility_state(p),view)
  e.advance_time(156);self.assertEqual(e.invisibility_state(p)['phase'],'cooldown');e.advance_time(1);self.assertEqual(e.invisibility_state(p)['phase'],'ready')
  self.e.advance_time(157);self.e.gm.restore('invisible-cooldown');self.assertEqual(self.view(self.p),view)
  self.e.advance_time(157);self.assertEqual(self.view(self.p)['phase'],'ready')
 def test_unknown_partial_round_is_bounded_and_observation_resolves_boundary(self):
  self.grant(self.p);self.change(self.p,True);self.e.advance_time(235);self.begin(self.p);self.e.end_encounter()
  view=self.view(self.p);self.assertEqual(view['phase'],'uncertain');self.assertEqual(view['elapsed_bounds'],[235,245])
  e=self.restored();p=next(c for c in e.everyone if c.entity_id==self.p.entity_id);self.assertEqual(e.invisibility_state(p),view)
  with self.assertRaises(ValueError):self.e.observe_invisibility_elapsed(self.p,246,reason='impossible')
  with self.assertRaises(ValueError):self.change(self.p,False)
  self.e.observe_invisibility_elapsed(self.p,237,reason='observed two seconds of final round')
  self.assertTrue(self.view(self.p)['active']);self.e.advance_time(3);self.assertEqual(self.view(self.p)['phase'],'cooldown')
 def test_missing_capability_cost_failure_and_corrupt_restore_are_atomic(self):
  before=deepcopy(self.p.spec)
  with self.assertRaises(ValueError):self.change(self.p,True)
  self.assertEqual(self.p.spec,before);self.grant(self.p);self.begin(self.p);self.p.budget['standard']=self.p.budget['shift']=0
  before=deepcopy((self.p.spec,self.p.budget))
  with self.assertRaises(ValueError):self.change(self.p,True)
  self.assertEqual((self.p.spec,self.p.budget),before)
  self.begin(self.p);self.change(self.p,True);G.revoke(self.p,'fixture:invisible')
  self.assertTrue(self.view(self.p)['active']) # Loss prevents new activation, not retroactive cancellation.
  self.e.gm.snapshot('active');e=self.restored();p=next(c for c in e.everyone if c.entity_id==self.p.entity_id);self.assertTrue(e.invisibility_state(p)['active'])
  self.p.spec[V.KEY]['clock_anchor']=self.e.elapsed_seconds+1
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
  self.e.gm.restore('active');self.assertTrue(self.view(self.p)['active'])

 def test_uncertain_target_refuses_attack_before_budget_frequency_or_rng(self):
  self.grant(self.t);self.change(self.t,True);self.e.advance_time(235);self.begin(self.p);self.e.end_encounter()
  self.known(self.p,'물대포');self.begin(self.p)
  before=deepcopy((self.p.budget,self.p.move_uses,self.p.pos,self.e.rng.getstate()))
  for run in (lambda:self.e.use_move(self.p,self.t,'move/물대포'),lambda:self.e.use_move_on(self.p,self.t,'move/물대포',self.e.everyone)):
   with self.assertRaisesRegex(ValueError,'invisibility'):run()
   self.assertEqual((self.p.budget,self.p.move_uses,self.p.pos,self.e.rng.getstate()),before)
 def test_uncertain_manual_duration_requires_observation_and_keeps_restore_bounds(self):
  self.grant(self.p);self.change(self.p,True);self.e.advance_time(30);self.begin(self.p);self.e.end_encounter()
  self.assertEqual(self.view(self.p)['elapsed_bounds'],[30,40]);self.assertTrue(self.view(self.p)['active'])
  with self.assertRaisesRegex(ValueError,'observe actual'):self.change(self.p,False)
  self.e.observe_invisibility_elapsed(self.p,34,reason='four seconds observed')
  self.change(self.p,False);self.assertEqual(self.view(self.p)['ready_after_elapsed'],188)
  self.e.advance_time(153);self.assertEqual(self.view(self.p)['phase'],'cooldown')
  self.e.advance_time(1);self.assertEqual(self.view(self.p)['phase'],'ready')

 def test_uncertain_cooldown_readiness_does_not_block_moves_or_add_accuracy_penalty(self):
  self.grant(self.p);self.change(self.p,True);self.e.advance_time(595);self.begin(self.p);self.e.end_encounter()
  view=self.view(self.p);self.assertEqual(view['phase'],'uncertain');self.assertEqual(view['elapsed_bounds'],[595,605])
  self.assertIs(view['active'],False)
  with self.assertRaises(ValueError):self.change(self.p,True)
  self.assertEqual(V.accuracy_penalty(self.e,self.p),0)
  self.known(self.p,'물대포');self.begin(self.p)
  self.e.use_move(self.p,self.t,'move/물대포',set_damage=True)
  self.assertEqual(self.p.budget['standard'],0)
  e=self.restored();p=next(c for c in e.everyone if c.entity_id==self.p.entity_id)
  self.assertIs(e.invisibility_state(p)['active'],False)

if __name__=='__main__':unittest.main()
