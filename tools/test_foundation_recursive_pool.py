from pathlib import Path
from random import Random
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
import roll_pools as P

class RecursivePoolTests(unittest.TestCase):
 def test_breadth_first_paths_and_repeat_each_child(self):
  out=P.recursive(Random(2),2,repeat=True,fixed={'0':6,'1':2,'0.1':6,'0.1.1':4})
  self.assertEqual([(r['path'],r['face'],r['rerolled']) for r in out],[('0',6,True),('1',2,False),('0.1',6,True),('0.1.1',4,False)])
 def test_explicit_choice_keeps_unselected_six_and_rejects_non_six(self):
  out=P.recursive(Random(2),2,repeat={'0'},fixed={'0':6,'1':6,'0.1':6})
  self.assertEqual([r['rerolled'] for r in out],[True,False,False])
  with self.assertRaisesRegex(ValueError,'repeat face'):P.recursive(Random(2),1,repeat={'0'},fixed={'0':3})
 def test_rng_observer_order_matches_native_reward_interleaving(self):
  actual=Random(6);expected=Random(6);queue=['0','1'];reference=[]
  while queue:
   path=queue.pop(0);face=expected.randint(1,6);reward=expected.choice(('a','b','c')) if face>=4 else None
   again=face==6
   if again:queue.append(path+'.1')
   reference.append(dict(path=path,face=face,rerolled=again,reward=reward))
  out=P.recursive(actual,2,repeat=True,on_face=lambda path,face:{'reward':actual.choice(('a','b','c')) if face>=4 else None})
  self.assertEqual(out,reference);self.assertEqual(actual.getstate(),expected.getstate())
 def test_fixed_requires_exact_reachable_observations(self):
  for fixed in ({'0':6},{'0':1,'0.1':2},{'0':7}):
   with self.assertRaises(ValueError):P.recursive(Random(2),1,repeat=True,fixed=fixed)
 def test_declared_sides_and_repeat_faces_are_not_hardcoded(self):
  out=P.recursive(Random(2),1,sides=8,repeat_faces=[7,8],repeat=True,fixed={'0':7,'0.1':8,'0.1.1':1})
  self.assertEqual([r['face'] for r in out],[7,8,1])

if __name__=='__main__':unittest.main()
