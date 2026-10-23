"""Extended Invisibility real investment and historical clock boundaries."""
import unittest
from tools import test_category2_move_edge_state as fixtures
import invisibility_edge as E
import invisibility_state as V
import state_grants as G

class ExtendedTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixtures.MoveEdgeStateTests.setUpClass()
 def setUp(self):
  self.f=fixtures.MoveEdgeStateTests();self.f.setUp();self.f.p.spec['capabilities']=['투명']
 def teach(self,**kw):
  f=self.f;return f.e.pokemon_activity(f.a,'teach_edge',target=f.p,edge='C2CSV/input/db/poke-edges.csv:R52:main',**kw,safe=True)
 def start(self):return self.f.e.change_invisibility(self.f.p,True,reason='actual activation')
 def view(self):return V.projection(self.f.e,self.f.p)
 def test_real_tp_and_eight_minute_expiry_with_actual_cooldown(self):
  f=self.f;self.teach();self.assertEqual((f.p.spec['tutor_points'],f.e.elapsed_seconds),(7,3600));self.start()
  f.e.advance_time(479);self.assertTrue(self.view()['active']);f.e.advance_time(1)
  self.assertEqual((self.view()['phase'],self.view()['ready_after_elapsed']),('cooldown',1080))
  loaded=f.restored();p=next(x for x in loaded.gm.everyone if x.entity_id==f.p.entity_id)
  self.assertEqual(V.projection(loaded,p),self.view())
  f.e.advance_time(599);self.assertEqual(self.view()['phase'],'cooldown');f.e.advance_time(1);self.assertEqual(self.view()['phase'],'ready')
 def test_manual_end_after_four_minutes_preserves_actual_duration(self):
  f=self.f;self.teach();self.start();f.e.advance_time(300)
  f.e.change_invisibility(f.p,False,reason='actual end')
  self.assertEqual(self.view()['ready_after_elapsed'],720)
 def test_level_loss_after_four_minutes_refunds_once_without_backdating(self):
  f=self.f;self.teach();self.start();f.e.advance_time(450)
  f.e.gm.set_level(f.p,19,reason='actual level loss')
  self.assertEqual((f.p.spec['tutor_points'],self.view()['phase'],self.view()['ready_after_elapsed']),(8,'cooldown',1020))
  f.e.gm.set_level(f.p,18,reason='later level loss');self.assertEqual(f.p.spec['tutor_points'],8)
 def test_early_level_loss_keeps_base_duration_but_capability_loss_ends_now(self):
  f=self.f;self.teach();self.start();f.e.advance_time(100);f.e.gm.set_level(f.p,19,reason='early level loss')
  self.assertTrue(self.view()['active']);self.assertEqual(self.view()['ready_after_elapsed'],600)
  self.setUp();f=self.f;self.teach();self.start();f.e.advance_time(100)
  G.replace_baseline(f.e,f.p,'capabilities',[])
  self.assertEqual((f.p.spec['tutor_points'],self.view()['phase'],self.view()['ready_after_elapsed']),(8,'cooldown',320))
 def test_uncertain_late_loss_requires_observation_without_partial_refund(self):
  f=self.f;self.teach();self.start();f.e.advance_time(450)
  f.e.start_round(f.e.everyone);f.e.start_of_turn(f.p);f.e.end_encounter()
  self.assertEqual(self.view()['elapsed_bounds'],[450,460]);before=f.snap()
  with self.assertRaises(ValueError):f.e.gm.set_level(f.p,19,reason='unknown loss time')
  self.assertEqual(f.snap(),before)
  f.e.observe_invisibility_elapsed(f.p,455,reason='actual partial round observed')
  f.e.gm.set_level(f.p,19,reason='observed loss time')
  self.assertEqual(self.view()['ready_after_elapsed'],1030)
 def test_valid_credit_extends_current_live_session_without_resetting_clock(self):
  f=self.f;f.a.spec['edges']=['미용사'];f.a.spec['items']['미용사 킷']=1
  f.e.pokemon_activity(f.a,'groom',targets=[f.p],safe=True);self.start();f.e.advance_time(60)
  self.teach(from_grooming=True)
  self.assertEqual((self.view()['elapsed_bounds'],self.view()['ready_after_elapsed']),([60,60],1080))

 def test_missing_prerequisite_duplicate_and_grooming_credit_are_atomic(self):
  f=self.f;f.p.spec['capabilities']=[];before=f.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(f.snap(),before);f.p.spec['capabilities']=['투명']
  before=f.snap()
  with self.assertRaises(ValueError):self.teach(from_grooming=True)
  self.assertEqual(f.snap(),before)
  f.a.spec['edges']=['미용사'];f.a.spec['items']['미용사 킷']=1;f.e.pokemon_activity(f.a,'groom',targets=[f.p],safe=True);self.teach(from_grooming=True)
  self.assertEqual(f.e.elapsed_seconds,3600);before=f.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(f.snap(),before)

if __name__=='__main__':unittest.main()
