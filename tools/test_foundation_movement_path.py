from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from grid import Grid
import movement_actions as M

class MovementPathTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r);self.e.grid=Grid(10,10)
  self.a=self.actor('a','large',(1,1));self.b=self.actor('b','medium',(5,1))
  self.e.everyone=self.e.gm.everyone=[self.a,self.b]
  self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a)
 def actor(self,identity,size,pos):
  c=Combatant(self.r,{'id':identity,'name':identity,'kind':'pokemon','level':20,'size':size,'stats':{'hp':30,'atk':15,'def':10,'spa':15,'spd':10,'spe':10},'movement':{'land':6,'sky':10,'burrow':10,'teleport':10},'moves':[]})
  c.pos=pos;c.side=identity;return c
 def snap(self):return deepcopy((self.a.spec,self.a.pos,self.a.budget,getattr(self.a,'airborne',None),self.e.rng.getstate(),self.e.log_lines))
 def test_teleport_rejects_full_body_overlap_before_cost(self):
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'body'):
   M.teleport(self.e,self.a,(4,1),surface_contact=True,reason_text='selected surface')
  self.assertEqual(self.snap(),before)
 def test_aerial_overlap_depends_on_actual_altitude(self):
  self.b.spec['_movement_altitude']=2;before=self.snap()
  with self.assertRaisesRegex(ValueError,'body'):
   M.aerial_move(self.e,self.a,(4,1),mode='sky',altitude=2,gm_distance=5,reason_text='observed flight')
  self.assertEqual(self.snap(),before)
  self.b.spec['_movement_altitude']=0
  out=M.aerial_move(self.e,self.a,(4,1),mode='sky',altitude=2,gm_distance=5,reason_text='observed flight')
  self.assertEqual(out['position'],(4,1));self.assertEqual(self.a.spec['_movement_altitude'],2)
 def test_map_edge_and_nonanchor_blocking_reject_before_cost(self):
  self.b.pos=(8,8)
  for destination,blocking in [((9,1),set()),((4,1),{(5,1)})]:
   self.e.grid.blocking=blocking;before=self.snap()
   with self.assertRaises(ValueError):M.teleport(self.e,self.a,destination,surface_contact=True,reason_text='selected surface')
   self.assertEqual(self.snap(),before)
 def test_burrow_surface_checks_whole_body_and_underground_map_bounds(self):
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'surface destination'):
   M.burrow_move(self.e,self.a,[(1,1),(2,1),(3,1),(4,1)],surface=True,diggable=True,reason_text='diggable path')
  self.assertEqual(self.snap(),before)
  self.a.pos=(8,1);before=self.snap()
  with self.assertRaisesRegex(ValueError,'outside mapped path'):
   M.burrow_move(self.e,self.a,[(8,1),(9,1)],diggable=True,reason_text='diggable path')
  self.assertEqual(self.snap(),before)

 def test_departure_interrupt_keeps_spent_shift_but_not_destination(self):
  from unittest.mock import patch
  import turn as TURN
  self.b.pos=(3,1);origin=self.a.pos
  def interrupt(*args,**kwargs):self.a.hp=0
  with patch.object(TURN,'trigger_aoo',side_effect=interrupt) as event:
   out=M.teleport(self.e,self.a,(6,1),surface_contact=True,reason_text='selected surface')
  self.assertFalse(out);event.assert_called_once()
  self.assertEqual(self.a.pos,origin);self.assertEqual(self.a.budget['shift'],0)
  self.assertNotIn('_teleport',self.a.spec)

if __name__=='__main__':unittest.main()
