from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_move_accuracy_admission as F

class AccuracyPlanTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.MoveAccuracyAdmissionTests.setUpClass()
 def setUp(self):self.f=F.MoveAccuracyAdmissionTests();self.f.setUp()
 def test_numeric_preview_is_nonconsuming_and_actual_check_uses_preparation(self):
  f=self.f;move=dict(f.r.move('move/빛의장막'),ac=0);before=f.snap()
  with patch.object(f.e,'d20',side_effect=AssertionError('preview must not roll')):
   out=f.e.plan_accuracy_context(f.a,f.p,move,situational=2)
  self.assertTrue(out['requires_roll']);self.assertIsNone(out['final_outcome']);self.assertTrue(out['post_roll_effects_pending'])
  self.assertEqual(out['target_id'],f.p.entity_id);self.assertEqual(f.snap(),before)
  with patch.object(f.e,'_prepare_accuracy_context',wraps=f.e._prepare_accuracy_context) as prepare:
   result=f.e.accuracy_check(f.a,f.p,move,fixed_roll=20)
  self.assertEqual(prepare.call_count,1);self.assertTrue(result[0]);self.assertEqual(result[1],20)
 def test_absent_ac_preview_does_not_invent_a_die_or_consume_effect(self):
  f=self.f;before=f.snap()
  out=f.e.plan_accuracy_context(f.a,f.a,f.r.move('move/빛의장막'))
  self.assertFalse(out['requires_roll']);self.assertFalse(out['consumed']);self.assertEqual(f.snap(),before)
  out['preparation']['move']['name']='changed copy'
  self.assertNotEqual(f.r.move('move/빛의장막')['name'],'changed copy')
if __name__=='__main__':unittest.main()
