"""Reusable maneuver stages with real native costs, effects and exceptions."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category3_physics_maneuvers as _fixture_test_category3_physics_maneuvers
import maneuver_opposed as OP,state_grants as G,turn as TURN,effects as FX,state_codec as CODEC
import common_checks as C

class OpposedTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category3_physics_maneuvers.Tests.setUpClass.__func__)
 setUp=_fixture_test_category3_physics_maneuvers.Tests.setUp;actor=_fixture_test_category3_physics_maneuvers.Tests.actor;options=_fixture_test_category3_physics_maneuvers.Tests.options
 def policy(self,index=0):return json.loads((ROOT/'data/examples/maneuvers-opposed.json').read_text(encoding='utf8'))[index]
 def run_maneuver(self,value=None,**changes):return self.e.opposed_maneuver(self.a,self.b,value or self.policy(),**self.options(**changes))
 def snap(self):return CODEC.dump_engine(self.e)
 def test_data_declared_action_hit_opposed_and_result_use_native_world(self):
  out=self.run_maneuver(fixed_accuracy=6);self.assertTrue(out['success']);self.assertIn('넘어짐',self.b.conditions);self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a._action_history.count('standard'),1)
 def test_accuracy_miss_spends_one_action_and_never_runs_opposed_or_effect(self):
  out=self.run_maneuver(fixed_accuracy=4);self.assertFalse(out);self.assertNotIn('넘어짐',self.b.conditions);self.assertEqual(self.a.budget['standard'],0)
 def test_status_quo_defender_wins_equal_opposed_totals(self):
  self.assertFalse(self.run_maneuver(defender_options={'fixed':[3]*4}));self.assertNotIn('넘어짐',self.b.conditions)
 def test_each_participant_has_its_own_allowed_skill_list(self):
  value=self.policy();value['challenger_skills']=['곡예'];before=self.snap()
  with self.assertRaises(ValueError):self.run_maneuver(value)
  self.assertEqual(self.snap(),before);self.assertTrue(self.run_maneuver(value,challenger_skill='곡예')['success'])
 def test_unknown_geometry_is_pending_without_cost_or_rng(self):
  value=self.policy();value['geometry']['range']=None;before=self.snap();out=self.run_maneuver(value)
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.snap(),before)
 def grant(self):G.grant(self.a,'capabilities','Telekinetic','test:remote','actual current acquired remote capability')
 def test_remote_source_owned_automatic_stages_use_actual_capability_and_shift_without_rng(self):
  value=self.policy(1);self.b.pos=(4,1);self.grant();before=self.e.rng.getstate()
  out=self.run_maneuver(value);self.assertTrue(out['success']);self.assertEqual(self.e.rng.getstate(),before);self.assertEqual((self.a.budget['standard'],self.a.budget['shift']),(1,0));self.assertIn('넘어짐',self.b.conditions)
 def test_automatic_stage_does_not_consume_skill_ap_rolls_or_require_skill_choices(self):
  self.grant();value=self.policy(1);before=self.e.rng.getstate()
  out=self.e.opposed_maneuver(self.a,self.b,value);self.assertTrue(out['success']);self.assertEqual(self.e.rng.getstate(),before);self.assertNotIn('_skill_maneuver_receipts',self.a.custom_conditions)
 def test_remote_loss_and_actual_range_fail_before_cost_and_rng(self):
  value=self.policy(1);self.b.pos=(4,1);before=self.snap()
  with self.assertRaisesRegex(ValueError,'qualification'):self.run_maneuver(value)
  self.assertEqual(self.snap(),before);self.grant();G.revoke(self.a,'test:remote');before=self.snap()
  with self.assertRaisesRegex(ValueError,'qualification'):self.run_maneuver(value)
  self.assertEqual(self.snap(),before)
  self.grant();self.b.pos=(7,1);before=self.snap()
  with self.assertRaises(ValueError):self.run_maneuver(value)
  self.assertEqual(self.snap(),before)
 def test_source_cannot_request_remote_without_declared_acquired_qualification(self):
  value=self.policy(1);value['requirements']=[]
  with self.assertRaisesRegex(ValueError,'qualification'):OP.declaration(value)
 def test_opportunity_interruption_after_action_stops_accuracy_and_result(self):
  before=self.e.rng.getstate()
  def interrupted(e,a,*args):e.lose_hp(a,a.hp);e.check_fainted(a)
  with patch.object(TURN,'trigger_aoo',interrupted):out=self.run_maneuver(fixed_accuracy=None)
  self.assertFalse(out);self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.e.rng.getstate(),before);self.assertNotIn('넘어짐',self.b.conditions)
 def test_late_result_failure_rolls_back_real_action_rng_and_target(self):
  before=self.snap()
  with patch.object(FX,'run_effects',side_effect=ValueError('late effect failure')):
   with self.assertRaisesRegex(ValueError,'late effect'):self.run_maneuver()
  self.assertEqual(self.snap(),before)
 def test_declared_accuracy_class_uses_actual_special_evasion(self):
  value=self.policy();value['accuracy_class']='특수'
  self.assertFalse(self.run_maneuver(value,fixed_accuracy=6));self.assertNotIn('넘어짐',self.b.conditions)
 def test_unregistered_participant_and_unknown_effect_cannot_spend_action(self):
  from copy import copy
  before=self.snap()
  with self.assertRaises(ValueError):self.e.opposed_maneuver(self.a,copy(self.b),self.policy(),**self.options())
  value=self.policy();value['effects']=[{'type':'unimplemented-effect'}]
  with self.assertRaises(ValueError):self.run_maneuver(value)
  self.assertEqual(self.snap(),before)
 def test_effect_and_real_source_survive_json_and_gm_restore(self):
  self.run_maneuver();self.e.gm.snapshot('opposed result');e=CODEC.load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)));b=next(c for c in e.everyone if c.entity_id==self.b.entity_id)
  self.assertIn('넘어짐',b.conditions);self.b.conditions.discard('넘어짐');self.e.gm.restore('opposed result');self.assertIn('넘어짐',self.b.conditions)

if __name__=='__main__':unittest.main()

