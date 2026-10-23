from pathlib import Path
import sys, unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import combat_hit as H
import test_category2_move_accuracy_admission as F

class HitTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): F.MoveAccuracyAdmissionTests.setUpClass()
 def test_precedence_and_boundary(self):
  base=dict(natural=1,modifier=100,accuracy=2,evasion=0)
  self.assertFalse(H.resolve(**base)['hit'])
  self.assertTrue(H.resolve(**base,automatic=True)['hit'])
  self.assertFalse(H.resolve(**base,automatic=True,cannot_hit='blocked')['hit'])
  base.update(natural=20,modifier=-100)
  self.assertTrue(H.resolve(**base)['hit'])
  self.assertFalse(H.resolve(**base,cannot_hit='blocked')['hit'])
  base.update(natural=10,modifier=2,accuracy=3,evasion=9)
  self.assertTrue(H.resolve(**base)['hit'])
  base['modifier']=1
  self.assertFalse(H.resolve(**base)['hit'])
 def test_invalid_declaration(self):
  base=dict(natural=10,modifier=0,accuracy=2,evasion=0)
  for change in [dict(natural=True),dict(natural=21),dict(modifier=float('nan')),
                 dict(accuracy=True),dict(evasion=float('inf')),dict(automatic=1),
                 dict(cannot_hit=''),dict(auto_hit_natural=1)]:
   with self.subTest(change=change),self.assertRaises(ValueError):H.resolve(**(base|change))
 def test_native_automatic_and_cannot_hit_use_common_comparator(self):
  f=F.MoveAccuracyAdmissionTests();f.setUp();move=f.r.move('move/스피드스타')
  with patch.object(H,'resolve',wraps=H.resolve) as common:
   self.assertTrue(f.e.accuracy_check(f.other,f.p,move,fixed_roll=1)[0])
   self.assertEqual(common.call_count,1)
  import effects_ext as EXT
  with patch.object(EXT,'blocks_hit',return_value='fixture immunity'):
   self.assertFalse(f.e.accuracy_check(f.other,f.p,move,fixed_roll=20)[0])
 def test_native_target_defenses_are_not_shared(self):
  f=F.MoveAccuracyAdmissionTests();f.setUp()
  move=dict(f.r.move('move/빛의장막'),ac=2)
  with patch.object(f.p,'evasion',return_value=0):
   low=f.e.accuracy_check(f.a,f.p,move,fixed_roll=5)
  with patch.object(f.p,'evasion',return_value=9):
   high=f.e.accuracy_check(f.a,f.p,move,fixed_roll=5)
  self.assertTrue(low[0]);self.assertFalse(high[0])
 def test_direct_ranged_attack_rejects_before_die_and_cost(self):
  f=F.MoveAccuracyAdmissionTests();f.setUp()
  from grid import Grid
  f.e.grid=Grid(40,40);f.other.pos=(1,1);f.p.pos=(30,1)
  f.begin(f.other);before=f.snap()
  with patch.object(f.e,'d20',side_effect=AssertionError('out of range must not roll')):
   self.assertEqual(f.e.use_move(f.other,f.p,'move/물대포'),0)
  self.assertEqual(f.snap()[:-1],before[:-1])
 def test_two_roll_move_observes_two_distinct_faces(self):
  f=F.MoveAccuracyAdmissionTests();f.setUp();f.begin(f.other)
  f.e.rule_effect('move/물대포','add',{'type':'multi_roll','rolls':2},reason='explicit two roll procedure')
  with patch.object(f.e,'d20',side_effect=[1,20]) as die:
   f.e.use_move(f.other,f.p,'move/물대포',set_damage=True)
  self.assertEqual(die.call_count,2)
  self.assertEqual(f.other.counters['multi_hits'],1)
if __name__=='__main__':unittest.main()
