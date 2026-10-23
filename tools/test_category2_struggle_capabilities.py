"""Shared native elemental Struggle declaration, no implicit ranged grant."""
import unittest
from copy import deepcopy
from unittest.mock import patch
from tools import test_category2_move_edge_state as fixtures
import struggle_capabilities as S

class StruggleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixtures.MoveEdgeStateTests.setUpClass()
 def setUp(self):
  self.f=fixtures.MoveEdgeStateTests();self.f.setUp()
  self.f.p.spec['capabilities']=list(S.DEFINITIONS)
 def test_six_types_both_classes_are_idempotent_and_do_not_change_global_move(self):
  f=self.f;raw=f.r.move('struggle');before=deepcopy(raw)
  for name,(_,element) in S.DEFINITIONS.items():
   for special in (False,True):
    with self.subTest(name=name,special=special):
     move=S.prepare(f.e,f.p,raw,{'capability':name,'special':special})
     self.assertEqual((move['type'],move['class']),(element,'특수' if special else '물리'))
     self.assertEqual(S.prepare(f.e,f.p,move),move)
     self.assertEqual(f.r.move('struggle'),before)
  self.assertIs(S.prepare(f.e,f.p,raw),raw)
 def test_native_target_dispatch_delivers_same_choice_to_damage(self):
  f=self.f;f.e.start_round([f.p,f.t]);f.e.start_of_turn(f.p)
  observed=[];original=f.e.damage_base
  def damage(actor,move,**kw):
   observed.append((move['type'],move['class']));return original(actor,move,**kw)
  with patch.object(f.e,'damage_base',side_effect=damage),patch.object(f.e.rng,'randint',return_value=10):
   f.e.use_move_on(f.p,f.t,'struggle',[f.p,f.t],struggle_choice={'capability':'Zapper','special':True})
  self.assertIn(('전기','특수'),observed)
  self.assertEqual(f.p.budget['standard'],0)
 def test_missing_capability_wrong_move_and_forged_actor_are_rejected(self):
  f=self.f;choice={'capability':'재퍼','special':True}
  move=S.prepare(f.e,f.p,f.r.move('struggle'),choice)
  with self.assertRaises(ValueError):S.prepare(f.e,f.t,move)
  with self.assertRaises(ValueError):S.prepare(f.e,f.p,f.r.move('move/메가톤펀치'),choice)
  f.p.spec['capabilities']=[]
  with self.assertRaises(ValueError):S.prepare(f.e,f.p,f.r.move('struggle'),choice)

if __name__=='__main__':unittest.main()
