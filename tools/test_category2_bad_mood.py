"""Bad Mood reads actual status categories at native critical determination."""
import unittest
from tools import test_category3_combat_precision as fixtures
import combat_precision_features as C
import items as I

class BadMoodTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixtures.CombatPrecisionTests.setUpClass()
 def setUp(self):
  self.f=fixtures.CombatPrecisionTests();self.f.setUp()
  self.f.a.spec['edges']=[C.BAD_MOOD];self.f.a.spec['skills']['협박']=5
 def crit(self,face=19,move='move/몸통박치기'):
  f=self.f;return f.accuracy(f.a,f.t,move,face)[2]
 def test_categories_count_once_and_combine_at_real_d20_boundary(self):
  f=self.f
  for conditions,bonus in [(set(),0),({'화상'},1),({'독','화상'},1),({'혼란'},1),({'독','혼란'},2)]:
   with self.subTest(conditions=conditions):
    f.a.conditions=set(conditions)
    self.assertEqual(C.bad_mood_critical_bonus(f.e,f.a),bonus)
    self.assertTrue(self.crit(20-bonus));self.assertFalse(self.crit(19-bonus))
 def test_live_cure_and_acquisition_loss_remove_bonus_without_registration(self):
  f=self.f;f.e.apply_status(f.a,'화상');self.assertTrue(self.crit())
  f.e.cure_status(f.a,'화상');self.assertFalse(self.crit())
  f.e.apply_status(f.a,'화상');f.a.spec['edges']=[];self.assertFalse(self.crit())
 def test_registration_does_not_double_bonus_or_make_status_move_critical(self):
  f=self.f;f.a.conditions={'화상'}
  I.register_feats(f.e,f.a);I.register_feats(f.e,f.a)
  self.assertTrue(self.crit());self.assertFalse(self.crit(18));self.assertFalse(self.crit(19,'move/째려보기'))
 def test_bad_prerequisite_and_duplicate_aliases_reject_before_rng(self):
  f=self.f
  for edges,rank in [([C.BAD_MOOD],4),([C.BAD_MOOD,'Bad Mood'],5)]:
   f.a.spec['edges']=edges;f.a.spec['skills']['협박']=rank;before=f.e.rng.getstate()
   with self.assertRaises(ValueError):f.e.accuracy_check(f.a,f.t,f.r.move('move/몸통박치기'))
   self.assertEqual(f.e.rng.getstate(),before)

if __name__=='__main__':unittest.main()
