"""Groundshaper and Gilled: native environment state, cost, consumers and saves."""
from copy import deepcopy
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
from grid import Grid
import state_grants as G,terrain_actions as T,state_codec as CODEC,movement_actions as M

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 def grant(self,c,name='지형변화',source='fixture:environment'):G.grant(c,'capabilities',name,source,'fixture')
 def change(self,c,*changes):return self.e.shape_ground(c,[{'cell':cell,'terrain':kind} for cell,kind in changes],reason='actual selected adjacent ground')
 def test_one_action_changes_selected_cells_independently_for_both_actor_kinds(self):
  grid=self.e.grid;rough=grid.rough;slow=grid.slow
  for c in (self.a,self.p):
   self.grant(c);self.begin(c);x,y=c.pos
   chosen=[((x,y-1),'rough'),((x+1,y),'slow'),((x,y+1),'both')]
   row=self.change(c,*chosen)
   self.assertEqual(c.budget['standard'],0);self.assertEqual(c._action_history.count('standard'),1)
   self.assertIs(self.e.grid,grid);self.assertIs(self.e.grid.rough,rough);self.assertIs(self.e.grid.slow,slow)
   for cell,kind in chosen:self.assertEqual((cell in rough,cell in slow),T.TERRAINS[kind])
   self.assertEqual(row['source'],T.SOURCE);self.assertEqual(row['actor_id'],c.entity_id);self.assertEqual(len(row['changes']),3)
 def test_all_cells_preflight_before_cost_and_no_partial_map_change(self):
  self.begin(self.p)
  with self.assertRaises(ValueError):self.change(self.p,((3,2),'rough'))
  self.grant(self.p)
  for bad in [((4,2),'both'),((3,3),'slow'),((30,3),'rough'),((3,2),'unknown'),((4,3),'normal')]:
   before=deepcopy((self.p.spec,self.p.budget,self.e.grid.rough,self.e.grid.slow,self.e.rng.getstate()))
   with self.assertRaises(ValueError):self.change(self.p,((3,2),'rough'),bad)
   self.assertEqual((self.p.spec,self.p.budget,self.e.grid.rough,self.e.grid.slow,self.e.rng.getstate()),before)
  with self.assertRaises(ValueError):self.change(self.p,((3,2),'rough'),((3,2),'slow'))
  self.change(self.p,((3,2),'rough'));before=deepcopy((self.p.spec,self.e.grid.rough,self.e.grid.slow))
  with self.assertRaises(ValueError):self.change(self.p,((4,3),'slow'))
  self.assertEqual((self.p.spec,self.e.grid.rough,self.e.grid.slow),before)
 def test_large_body_uses_cardinal_edge_and_leaves_unselected_and_blocking_ground(self):
  self.grant(self.p);self.p.spec['size']='大' # unknown body cannot infer adjacency
  self.begin(self.p)
  with self.assertRaises(ValueError):self.change(self.p,((5,3),'rough'))
  self.p.spec['size']='Large';self.e.grid.rough.add((2,3));self.e.grid.blocking.add((5,3))
  self.change(self.p,((5,3),'both'))
  self.assertIn((5,3),self.e.grid.blocking);self.assertIn((2,3),self.e.grid.rough)
  self.begin(self.p);self.change(self.p,((5,3),'normal'))
  self.assertNotIn((5,3),self.e.grid.rough);self.assertNotIn((5,3),self.e.grid.slow);self.assertIn((5,3),self.e.grid.blocking)
 def test_changed_rough_ground_changes_actual_accuracy_without_extra_flag_registry(self):
  self.grant(self.p);self.t.pos=(4,3);move=self.r.move('move/물대포');face=move['ac']+self.t.evasion('특수')
  self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=face)[0])
  self.begin(self.p);self.change(self.p,((4,3),'both'))
  self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=face)[0])
  self.assertEqual(M.slow_terrain_penalty(self.e,self.a,(4,3),'육상'),1)
 def test_changed_slow_ground_limits_actual_shift_and_normalization_restores_it(self):
  self.e.grid=Grid(1,5);self.a.pos=(0,0);self.p.pos=(0,2);self.p.on_field=False;self.t.pos=(0,4)
  self.e.gm.set_movement_capabilities(self.a,{'land':2},basis='current',reason='observed two-metre land movement');self.grant(self.a);self.begin(self.a);self.change(self.a,((0,1),'both'))
  self.e.gm.snapshot('slow lane');self.e.approach(self.a,self.t);self.assertEqual(self.a.pos,(0,1))
  self.e.gm.restore('slow lane');self.begin(self.a);self.change(self.a,((0,1),'normal'))
  self.e.approach(self.a,self.t);self.assertEqual(self.a.pos,(0,2))
 def test_terrain_persists_after_capability_loss_and_both_restores_with_valid_receipts(self):
  self.grant(self.p);self.begin(self.p);self.change(self.p,((3,2),'rough'),((4,3),'slow'))
  self.e.end_of_turn(self.p);self.e.end_encounter(self.e.everyone);G.revoke(self.p,'fixture:environment')
  self.e.gm.snapshot('terrain');e=self.restored();p=next(c for c in e.everyone if c.entity_id==self.p.entity_id)
  self.assertIn((3,2),e.grid.rough);self.assertIn((4,3),e.grid.slow);self.assertEqual(p.spec[T.HISTORY],self.p.spec[T.HISTORY])
  self.e.grid.rough.clear();self.e.gm.restore('terrain');self.assertIn((3,2),self.e.grid.rough)
  self.p.spec[T.HISTORY][0]['changes'][0]['cell']=[15,8]
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
 def test_gilled_live_sources_long_elapsed_time_recovery_and_both_restores(self):
  from builder import build_pokemon
  nongilled=self.add(build_pokemon(self.r,'이상해씨',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  for c in (self.a,nongilled):
   self.grant(c,'아가미');self.grant(c,'Gilled','fixture:gills2')
   self.e.observe_breathing(c,air_available=False,medium='water',reason='actual immersion')
   self.e.advance_time(7*86400);self.assertEqual(c.injuries,0);self.assertIsNone(c.spec['_respiration']['deprivation_started_at'])
   self.e.gm.snapshot('gills');e=self.restored();loaded=next(a for a in e.everyone if a.entity_id==c.entity_id)
   e.advance_time(86400);self.assertEqual(loaded.injuries,0);self.assertTrue(loaded.spec['_respiration']['breathing'])
   G.revoke(c,'fixture:environment');self.e.advance_time(3600);self.assertEqual(c.injuries,0)
   G.revoke(c,'fixture:gills2');before=self.e.elapsed_seconds
   with self.assertRaises(ValueError):self.e.advance_time(1)
   self.assertEqual(self.e.elapsed_seconds,before)
   self.e.observe_breathing(c,air_available=False,medium='water',reason='gills lost now',timing_policy='grace_boundary')
   self.e.advance_time(60);self.assertEqual(c.injuries,1)
   self.e.gm.restore('gills');self.assertEqual(c.injuries,0);self.assertTrue(c.spec['_respiration']['breathing'])

if __name__=='__main__':unittest.main()
