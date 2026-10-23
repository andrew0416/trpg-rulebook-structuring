from pathlib import Path
from random import Random
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
import roll_pools as P

class DieProcedureTests(unittest.TestCase):
 def test_keep_drop_preserve_original_order_and_index_evidence(self):
  self.assertEqual(P.select([1,6,3,6],operation='keep',indices=[3,1])['faces'],(6,6))
  out=P.select([1,6,3,6],operation='drop',indices=[1]);self.assertEqual(out['faces'],(1,3,6));self.assertEqual(out['retained_indices'],(0,2,3))
 def test_replace_and_reroll_use_declared_index_order_once(self):
  rng=Random(6);expected=Random(6);a,b=expected.randint(1,6),expected.randint(1,6)
  out=P.select([1,4,1],operation='reroll',indices=[2,0],rng=rng)
  self.assertEqual(out['faces'],(b,4,a));self.assertEqual(rng.getstate(),expected.getstate());self.assertEqual(out['original'],(1,4,1))
  out=P.select(out['faces'],operation='replace',indices=[1],replacements=[6]);self.assertEqual(out['faces'],(b,6,a))
 def test_invalid_indices_or_replacement_fail_before_rng(self):
  rng=Random(2);before=rng.getstate()
  for indices in ([1,1],[3],[True]):
   with self.assertRaises(ValueError):P.select([2,3],operation='reroll',indices=indices,rng=rng)
  self.assertEqual(rng.getstate(),before)
 def test_table_scoring_is_not_sum_and_override_is_per_dimension(self):
  table={str(i):{'appeal':1,'fumble':0} for i in range(1,7)};table['1']={'appeal':0,'fumble':1};table['6']={'appeal':2,'fumble':0}
  out=P.score_faces([1,6,6],table,dimensions=['appeal','fumble'],override={'1':{'appeal':3}})
  self.assertEqual(out['totals'],{'appeal':7,'fumble':1});self.assertEqual(len(out['trace']),3);self.assertEqual(table['1']['appeal'],0)
 def test_incomplete_table_and_unknown_dimensions_rejected(self):
  with self.assertRaises(ValueError):P.score_faces([1],{'1':{'appeal':1}},dimensions=['appeal'])
  table={str(i):{'appeal':1} for i in range(1,7)}
  with self.assertRaises(ValueError):P.score_faces([1],table,dimensions=['appeal'],override={'1':{'unknown':2}})

if __name__=='__main__':unittest.main()
