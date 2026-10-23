"""Paid physical weapon areas use an explicit point and actual covered bodies."""
from pathlib import Path
import sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_reuse_partial_completion as FIX
from engine import Rules
from grid import Grid
from state_codec import dump_engine
import turn as TURN
import weapon_actions as WEAPONS
import area_targets as AREA

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  FIX.Tests.setUp(self)
  self.e.grid=Grid(20,20);self.a.pos=(0,1);self.b.pos=(5,1);self.c.pos=(6,2)
  self.a.spec['skills']['전투']='달인'
  self.key=TURN.equip_weapon(self.e,self.a,{'name':'실제 활','kind':'장거리 사격무기','grade':'좋음','moves':['일제사격']})
  self.mid='move/일제사격'
 def test_native_area_hits_actual_covered_targets_and_pays_once(self):
  hp=(self.b.hp,self.c.hp)
  with patch.object(self.e,'accuracy_check',return_value=(True,10,False)),patch.object(self.e,'roll_damage',return_value=5):
   self.e.use_move_on(self.a,self.b,self.mid,self.e.everyone,weapon_id=self.key,aim=(5,1))
  self.assertLess(self.b.hp,hp[0]);self.assertLess(self.c.hp,hp[1]);self.assertEqual(self.a.budget['standard'],0)
  row=list(self.e._move_completions.values())[-1]
  self.assertEqual((row['phase'],len(row['results'])),('complete',2))
 def test_missing_invalid_near_and_far_points_do_not_spend_or_advance_rng(self):
  before=dump_engine(self.e)
  for aim in (None,(True,1),(-1,1),(3,1),(15,1)):
   with self.subTest(aim=aim),self.assertRaises(ValueError):
    self.e.use_move_on(self.a,self.b,self.mid,self.e.everyone,weapon_id=self.key,aim=aim)
   self.assertEqual(dump_engine(self.e),before)
 def test_target_set_comes_from_aim_point_not_primary_direction(self):
  move=AREA.bind(self.e,self.a,WEAPONS.prepare(self.e,self.a,self.r.move(self.mid),self.key),(5,1))
  self.c.pos=(9,8)
  self.assertEqual(self.e.targets_in_range(self.a,move,self.e.everyone,self.c),[self.b])
  with self.assertRaisesRegex(ValueError,'outside explicitly aimed'):
   self.e.use_move(self.a,self.c,self.mid,weapon_id=self.key,aim=(5,1))
 def test_blocked_aim_has_no_cost(self):
  self.e.grid.blocking.add((3,1));before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'line of sight'):
   self.e.use_move_on(self.a,self.b,self.mid,self.e.everyone,weapon_id=self.key,aim=(5,1))
  self.assertEqual(dump_engine(self.e),before)
 def test_equipment_and_current_qualification_remain_required(self):
  self.a.spec['skills']['전투']='미숙';before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'rank prerequisite'):
   self.e.use_move_on(self.a,self.b,self.mid,self.e.everyone,weapon_id=self.key,aim=(5,1))
  self.assertEqual(dump_engine(self.e),before)
  self.a.spec['skills']['전투']='달인';TURN.unequip_weapon(self.e,self.a,self.key)
  self.a.moves.append(self.mid)
  with self.assertRaisesRegex(ValueError,'equipped granting weapon'):
   self.e.use_move_on(self.a,self.b,self.mid,self.e.everyone,aim=(5,1))

if __name__=='__main__':unittest.main()
