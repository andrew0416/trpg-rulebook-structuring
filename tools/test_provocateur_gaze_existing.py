"""R-PROV-02: same-beloved Flirt through shared condition/timing owners, with both lifetime directions."""
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
from provocateur_fixture import ProvocateurScene
import provocateur as P
import combat_maneuvers as M
import combat_timing as TIME
import condition_instances as CONDITIONS
import action_points as AP
import frequency as F

class ExistingGazeTests(ProvocateurScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def flirt(self,actor,target,quick=False):
  options=dict(defender_skill='집중',fixed_accuracy=15,challenger_options={'fixed':[6]*5},defender_options={'fixed':[1]*3})
  return self.e.quick_wit(actor,target,manipulation='flirt',**options) if quick else self.e.manipulate(actor,target,'flirt',**options)
 def test_gaze_mixed_cone_preserves_longer_existing_infatuation_after_full_round(self):
  self.family(P.GAZE);self.family(P.FIDDLE);self.begin();self.fiddle(P.MOVES[0]);self.next_round()
  before=AP.available(self.a);self.assertEqual(self.e.enchanting_gaze(self.a,'flirt',aim=(5,2)),[True,True])
  self.assertEqual(AP.available(self.a),before-2);self.assertEqual(self.a.budget['standard'],0)
  for t in (self.t,self.u):self.assertEqual(M.save_disposition(t,'헤롱헤롱'),'automatic_failure')
  self.restore();self.assertTrue(all(person is self.a for person in CONDITIONS.beloved(self.t)))
  self.turn(self.t,count=20)
  with patch.object(Engine,'d20',side_effect=AssertionError('Flirt saving check must automatically fail')):self.e.end_of_turn(self.t)
  self.assertIn('헤롱헤롱',self.t.conditions)
  self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(31)
  self.assertEqual(M.save_disposition(self.t,'헤롱헤롱'),'automatic_failure')
  self.e.at_initiative_count(30)
  self.assertIsNone(M.save_disposition(self.t,'헤롱헤롱'));self.assertIn('헤롱헤롱',self.t.conditions)
  self.assertNotIn('헤롱헤롱',self.u.conditions);self.assertFalse(self.e.cure_status(self.t,'헤롱헤롱'))
  self.e.end_scene(round_elapsed_seconds=0);self.assertNotIn('헤롱헤롱',self.t.conditions);self.valid()
 def test_gaze_extends_shorter_same_beloved_through_existing_timed_status_ownership(self):
  self.family(P.GAZE);self.begin();self.assertTrue(self.flirt(self.a,self.t))
  self.assertTrue(any(r.get('count_deadline')==(1+1,30) and '헤롱헤롱' in r['owned_statuses'] for r in TIME.records(self.t)))
  self.next_round(count=31);self.assertEqual(self.e.enchanting_gaze(self.a,'flirt',aim=(5,2)),[True,True])
  self.e.end_of_turn(self.a);self.e.at_initiative_count(30)
  self.assertIn('헤롱헤롱',self.t.conditions)
  self.assertTrue(any(r.get('count_deadline')==(3,31) and '헤롱헤롱' in r['owned_statuses'] for r in TIME.records(self.t)))
  self.assertEqual(M.save_disposition(self.t,'헤롱헤롱'),'automatic_failure')
  self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(32)
  self.assertIn('헤롱헤롱',self.t.conditions);self.e.at_initiative_count(31)
  for t in (self.t,self.u):self.assertNotIn('헤롱헤롱',t.conditions)
  self.valid()
 def test_different_beloved_in_mixed_cone_rejects_atomically_without_invented_merge(self):
  self.family(P.GAZE);self.begin(self.b);self.assertTrue(self.flirt(self.b,self.t));self.turn(self.a,count=20)
  self.reject(lambda:self.e.enchanting_gaze(self.a,'flirt',aim=(5,2)),'multiple different Infatuation')
  self.assertTrue(all(person is self.b for person in CONDITIONS.beloved(self.t)))
  self.assertNotIn('헤롱헤롱',self.u.conditions);self.valid()
 def test_quick_wit_same_beloved_after_gaze_keeps_ordinary_manipulate_scene_quota(self):
  self.family(P.GAZE);self.begin();self.e.enchanting_gaze(self.a,'flirt',aim=(5,2))
  self.assertTrue(self.flirt(self.a,self.t,quick=True))
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.budget['swift'],0)
  self.assertEqual(F.state(self.a)['activations'][P.QUICK]['used'],1)
  self.assertEqual(self.a.custom_conditions['manipulate_uses'],[('flirt',self.t)])
  self.next_round();self.reject(lambda:self.flirt(self.a,self.t,quick=True),'already been used')
  self.assertEqual(F.state(self.a)['activations'][P.QUICK]['used'],1);self.valid()
