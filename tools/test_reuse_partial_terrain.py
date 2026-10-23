"""Base terrain is consumed by real paid movement and real accuracy contexts."""
from pathlib import Path
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_reuse_partial_completion as FIX
from engine import Rules
from grid import Grid
import map_terrain as TERRAIN
import movement_actions as MOVE
from state_codec import dump_engine,load_engine,StateCodecError

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  FIX.Tests.setUp(self)
  self.e.grid=Grid(7,1);self.a.pos=(0,0);self.b.pos=(5,0);self.c.on_field=False
  self.e.gm.set_movement_capabilities(self.a,{'land':6,'swim':4,'burrow':4},basis='current',reason='actual terrain test capabilities')
 def test_underwater_uses_swim_not_faster_land_in_native_approach(self):
  self.e.observe_map_terrain([(x,0) for x in range(1,5)],base='underwater',reason='actual immersed corridor')
  self.e.approach(self.a,self.b,movement_mode='land');self.assertEqual(self.a.pos,(0,0))
  self.a.budget['shift']=1
  result=self.e.approach(self.a,self.b,movement_mode='swim')
  self.assertEqual((self.a.pos,result['distance'],result['mode']),((4,0),4,'수중'))
 def test_slow_overlay_preserves_base_and_doubles_actual_swim_cost(self):
  self.e.observe_map_terrain([(x,0) for x in range(1,5)],base='underwater',slow=True,rough=True,reason='actual slow underwater corridor')
  result=self.e.approach(self.a,self.b,movement_mode='swim')
  self.assertEqual((self.a.pos,result['distance']),((2,0),4))
  self.assertEqual(TERRAIN.base_at(self.e.grid,(2,0)),'underwater');self.assertIn((2,0),self.e.grid.rough)
 def test_second_diagonal_slow_step_costs_four(self):
  self.e.grid=Grid(5,5,slow=[(1,1),(2,2)]);self.b.on_field=False
  self.assertEqual(self.e.grid.diagonal_cost([(0,0),(1,1),(2,2)]),6)
  result=MOVE.follow_paid_path(self.e,self.a,[(1,1),(2,2)],mode='육상',maximum_distance=5)
  self.assertEqual((result['distance'],self.a.pos),(2,(1,1)))
 def test_earth_requires_actual_burrow_mode_and_underground_state(self):
  self.e.observe_map_terrain([(1,0)],base='earth',reason='solid underground soil')
  self.assertFalse(TERRAIN.can_travel(self.e,self.a,(1,0),'육상'))
  self.assertFalse(TERRAIN.can_travel(self.e,self.a,(1,0),'burrow',underground=False))
  self.assertTrue(TERRAIN.can_travel(self.e,self.a,(1,0),'burrow',underground=True))
  self.e.burrow_move(self.a,[(0,0),(1,0)],diggable=True,surface=False,reason_text='observed diggable ground')
  self.assertEqual(self.a.pos,(1,0));self.assertTrue(self.a.spec['_burrow']['underground'])
 def test_occupied_intermediate_space_is_rough_but_not_blocking(self):
  self.c.on_field=True;self.c.pos=(2,0)
  move=self.r.move('move/불꽃세례')
  self.assertFalse(self.e.grid.blocked(self.a.pos,self.b.pos))
  self.assertEqual(self.e._prepare_accuracy_context(self.a,self.b,move)['zone_pen'],-2)
  self.c.on_field=False
  self.assertEqual(self.e._prepare_accuracy_context(self.a,self.b,move)['zone_pen'],0)
 def test_rough_line_and_blocking_share_actual_grid(self):
  self.e.observe_map_terrain([(2,0)],base='regular',rough=True,reason='observed intervening brush')
  self.assertEqual(TERRAIN.accuracy_penalty(self.e,self.a,self.b),-2)
  self.e.observe_map_terrain([(2,0)],base='regular',blocking=True,reason='observed wall')
  self.assertTrue(self.e.grid.blocked(self.a.pos,self.b.pos))
  self.assertFalse(__import__('body_state').can_place(self.e,self.a,(2,0)))
 def test_roundtrip_keeps_base_and_overlay_invalid_base_is_rejected(self):
  self.e.observe_map_terrain([(1,0)],base='underwater',slow=True,reason='actual map')
  e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
  self.assertEqual((e.grid.base_terrain,e.grid.slow),({'1,0':'underwater'},{(1,0)}))
  e.grid.base_terrain['1,0']='invented'
  with self.assertRaises(StateCodecError):dump_engine(e)
 def test_observation_commits_to_actual_grid_and_preserves_existing_container_aliases(self):
  grid=self.e.grid;slow=grid.slow;rough=grid.rough
  self.e.observe_map_terrain([(1,0)],base='underwater',slow=True,rough=True,reason='actual observed map')
  self.assertIs(self.e.grid,grid);self.assertIs(grid.slow,slow);self.assertIs(grid.rough,rough)
  self.assertEqual((slow,rough),({(1,0)},{(1,0)}))
 def test_invalid_staged_grid_or_observation_rolls_back_every_field(self):
  import state_grants as G
  before=dump_engine(self.e);grid=self.e.grid
  def invalid(staged,actor):
   staged.grid.base_terrain={'1,0':'invented'}
   staged.grid.slow.add((1,0));actor.hp-=3
  with self.assertRaises(ValueError):G.transition(self.e,self.a,invalid,include_grid=True)
  self.assertEqual(dump_engine(self.e),before);self.assertIs(self.e.grid,grid)
  with self.assertRaises(ValueError):self.e.observe_map_terrain([(1,0),(20,0)],base='underwater',slow=True,reason='invalid mixed observation')
  self.assertEqual(dump_engine(self.e),before)

if __name__=='__main__':unittest.main()
