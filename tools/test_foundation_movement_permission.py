from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from physical_limits import classify_load

class LoadBoundaryTests(unittest.TestCase):
 def test_boundaries_need_explicit_choice_and_ordinary_intervals_cannot_be_overridden(self):
  self.assertEqual(classify_load(10,[10,20],30),'boundary')
  self.assertEqual(classify_load(10,[10,20],30,'normal'),'normal')
  self.assertEqual(classify_load(20,[10,20],30,'staggering'),'staggering')
  for weight,band in [(0,'normal'),(15,'heavy'),(25,'staggering'),(31,'too_heavy')]:
   self.assertEqual(classify_load(weight,[10,20],30),band)
  with self.assertRaises(ValueError):classify_load(15,[10,20],30,'normal')
 def test_invalid_physical_declarations_never_authorize_movement(self):
  for weight,heavy,limit in [(True,[10,20],30),(-1,[10,20],30),(float('nan'),[10,20],30),(1,[20,10],30),(1,[10,20],15),(1,[10,10],30),(1,[10,20],float('inf')),(1,[10],30)]:
   with self.subTest(weight=weight,heavy=heavy,limit=limit):
    with self.assertRaises(ValueError):classify_load(weight,heavy,limit)

if __name__=='__main__':unittest.main()
