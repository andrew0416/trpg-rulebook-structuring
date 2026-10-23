from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import capture_resolution as C
import test_category3_pokemon_activities as F

class CaptureTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.PokemonActivityTests.setUpClass()
 def fixture(self):
  f=F.PokemonActivityTests();f.setUp();f.a.spec['items']['몬스터볼']=1
  return f
 def test_declared_direction_and_natural_exception_are_bound(self):
  new=C.Procedure('fixture/new',20,'>=');old=C.Procedure('fixture/old',100,'<=',(100,))
  self.assertTrue(new.resolve(10,threshold=12,modifiers={'trainer':2})['captured'])
  self.assertFalse(old.resolve(50,threshold=40,modifiers={'trainer':-5})['captured'])
  self.assertTrue(old.resolve(100,threshold=1,modifiers={})['captured'])
  with self.assertRaises(ValueError):new.resolve(100,threshold=1,modifiers={})
 def test_native_success_pending_placement_is_still_success(self):
  f=self.fixture()
  with patch.object(C.Procedure,'resolve',autospec=True,side_effect=C.Procedure.resolve) as compare:
   self.assertTrue(f.e.throw_ball(f.a,f.p,fixed_accuracy=20,fixed_capture=20))
  self.assertEqual(compare.call_count,1)
  row=f.a.spec['capture_attempts']['capture-1']
  self.assertEqual(row['status'],'captured');self.assertEqual(row['placement']['location'],'pending')
  self.assertEqual(row['resolution']['sides'],20);self.assertTrue(f.p.captured)
  self.assertEqual(f.p.spec['trainer_id'],f.a.spec['id']);json.dumps(row)
 def test_miss_and_failed_capture_preserve_distinct_ball_states(self):
  for accuracy,natural,state in [(1,20,'recoverable_on_ground'),(20,1,'failed_capture')]:
   f=self.fixture();self.assertFalse(f.e.throw_ball(f.a,f.p,fixed_accuracy=accuracy,fixed_capture=natural))
   row=f.a.spec['capture_attempts']['capture-1'];self.assertEqual(row['status'],state)
   self.assertEqual(f.a.spec['items']['몬스터볼'],0);self.assertFalse(f.p.captured)
   self.assertEqual('resolution' in row,accuracy==20)
 def test_unregistered_target_rejects_before_cost(self):
  f=self.fixture();f.e.gm.everyone.remove(f.p);before=f.state()
  with self.assertRaisesRegex(ValueError,'registered'):
   f.e.throw_ball(f.a,f.p,fixed_accuracy=20,fixed_capture=20)
  self.assertEqual(f.state(),before)
 def test_mixed_or_incomplete_version_rejects_before_cost(self):
  for change in [{'success':'roll <= capture_rate'},{'_version':'legacy'}, {'roll':'1d100 - trainer_level'}]:
   f=self.fixture();before=f.state();original=f.e.r.mech
   def read(uid):
    value=original(uid)
    return dict(value,**change) if uid=='pokemon/capture-rate' else value
   with patch.object(f.e.r,'mech',side_effect=read),self.assertRaises(ValueError):
    f.e.throw_ball(f.a,f.p,fixed_accuracy=20,fixed_capture=20)
   self.assertEqual(f.state(),before)
if __name__=='__main__':unittest.main()
