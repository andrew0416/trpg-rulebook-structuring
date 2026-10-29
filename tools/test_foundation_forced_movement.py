from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_movement_path as FIX
import forced_movement as F,effects as FX,coat_effects as COATS,effects_ext as EXT

class ForcedMovementTests(unittest.TestCase):
 setUpClass=classmethod(FIX.MovementPathTests.setUpClass.__func__)
 actor=FIX.MovementPathTests.actor
 setUp=FIX.MovementPathTests.setUp
 def test_effect_push_stops_at_other_body_without_spending_target_movement(self):
  self.a.pos=(1,1);self.b.pos=(3,1)
  block=self.actor('block','large',(5,1));self.e.everyone.append(block)
  budget=deepcopy(getattr(self.b,'budget',None));hp=self.b.hp
  FX.h_push(self.e,self.a,self.b,{'meters':4},{'source_id':'move/test'})
  self.assertEqual(self.b.pos,(4,1));self.assertEqual(self.b.hp,hp);self.assertEqual(getattr(self.b,'budget',None),budget)
 def test_large_body_collision_checks_nonanchor_cells(self):
  self.a.pos=(1,4);self.b.pos=(3,4);self.b.spec['size']='large'
  self.e.grid.blocking.add((5,5))
  out=F.displace(self.e,self.a,self.b,direction=(1,0),distance=3,source='observed push')
  self.assertEqual(out['moved'],0);self.assertEqual(out['stopped_by'],'collision')
 def test_very_large_vector_stops_at_actual_obstruction_without_materializing_unused_distance(self):
  self.a.pos=(1,1);self.b.pos=(3,1);self.e.grid.blocking.add((5,1))
  budget=deepcopy(getattr(self.b,'budget',None));hp=self.b.hp
  out=F.displace(self.e,self.a,self.b,direction=(1,0),distance=10**12,source='actual sourced displacement')
  self.assertEqual((out['requested'],out['moved'],out['position'],out['stopped_by']),(10**12,1,(4,1),'collision'))
  self.assertEqual(out['path'],[(3,1),(4,1)]);self.assertEqual(self.b.hp,hp)
  self.assertEqual(getattr(self.b,'budget',None),budget)
 def test_immunity_and_invalid_direction_leave_position_untouched(self):
  origin=self.b.pos
  with patch.object(COATS,'blocks_displacement',return_value=True):
   out=F.displace(self.e,self.a,self.b,direction=(1,0),distance=3,source='observed push')
  self.assertEqual(out['stopped_by'],'immune');self.assertEqual(self.b.pos,origin)
  with self.assertRaises(ValueError):F.displace(self.e,self.a,self.b,direction=(0,0),distance=3,source='observed push')
  self.assertEqual(self.b.pos,origin)
 def test_entry_effect_interrupts_remaining_displacement(self):
  self.b.pos=(3,1);budget=deepcopy(getattr(self.b,'budget',None))
  def stop(e,c,cell):c.hp=0
  with patch.object(EXT,'on_enter_cell',side_effect=stop) as entry:
   out=F.displace(self.e,self.a,self.b,direction=(1,0),distance=3,source='observed push')
  self.assertEqual(out['moved'],1);self.assertEqual(out['stopped_by'],'interrupted')
  entry.assert_called_once();self.assertEqual(getattr(self.b,'budget',None),budget)

 def test_descriptive_forced_effect_does_not_invent_distance_or_trainer_direction(self):
  before=deepcopy((self.b.spec,self.b.pos,getattr(self.b,'budget',None),self.e.log_lines))
  error=EXT.h_forced_movement(self.e,self.a,self.b,{'away_from_user':'max movement toward trainer'}, {})
  self.assertIn('explicit',error)
  self.assertEqual((self.b.spec,self.b.pos,getattr(self.b,'budget',None),self.e.log_lines),before)
  EXT.h_forced_movement(self.e,self.a,self.b,{'distance':1,'direction':[1,0]}, {'source_id':'observed slide'})
  self.assertEqual(self.b.pos,(6,1))
 def test_no_map_does_not_claim_displacement_and_boolean_distance_rejects(self):
  before=(self.b.pos,list(self.e.log_lines));self.e.grid=None
  self.assertIn('grid',FX.h_push(self.e,self.a,self.b,{'meters':2},{}))
  self.assertEqual((self.b.pos,self.e.log_lines),before)
  self.assertIn('nonnegative',FX.h_push(self.e,self.a,self.b,{'meters':True},{}))

 def test_declared_inertial_vector_stops_at_selected_surface_through_dispatch(self):
  self.b.pos=(3,1)
  out=FX.run_effects(self.e,self.a,self.b,[{'type':'forced_movement','distance':5,'direction':[1,0],'stop_cells':[[5,1]]}],{'hit':True},'move/몸통박치기')
  self.assertFalse(out.pending);self.assertEqual(self.b.pos,(5,1))
 def test_unavailable_and_invalid_stop_policy_reject_before_motion(self):
  origin=self.b.pos
  with self.assertRaises(ValueError):F.displace(self.e,self.a,self.b,direction=(1,0),distance=3,source='slide',stop_cells=[[99,1]])
  self.b.captured=True
  with self.assertRaises(ValueError):F.displace(self.e,self.a,self.b,direction=(1,0),distance=3,source='slide')
  self.assertEqual(self.b.pos,origin)
 def test_entry_relocation_ends_original_vector(self):
  self.b.pos=(3,1)
  def relocate(e,c,cell):c.pos=(1,8)
  with patch.object(EXT,'on_enter_cell',side_effect=relocate):
   out=F.displace(self.e,self.a,self.b,direction=(1,0),distance=4,source='slide')
  self.assertEqual(self.b.pos,(1,8));self.assertEqual(out['stopped_by'],'relocated')

 def test_dispatch_keeps_unresolved_description_pending_without_motion(self):
  before=self.b.pos
  out=FX.run_effects(self.e,self.a,self.b,[{'type':'forced_movement','away_from_user':'max movement toward trainer'}],{'hit':True},'move/몸통박치기')
  self.assertTrue(out.pending);self.assertEqual(self.b.pos,before)

if __name__=='__main__':unittest.main()
