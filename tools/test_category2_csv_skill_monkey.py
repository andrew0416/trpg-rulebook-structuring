"""The frozen CSV source reuses native observed rerolls, costs and finalization."""
from pathlib import Path
from unittest.mock import patch
import json,unittest
from engine import Rules
from ruleset import RuleFilter
import test_category3_skill_feature_actions as _fixture_test_category3_skill_feature_actions
from state_codec import dump_engine,load_engine
import skill_feature_actions as F,world_entities as W

ROOT=Path(__file__).resolve().parents[1]

class CsvSkillMonkeyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')
 actor=_fixture_test_category3_skill_feature_actions.Tests.actor
 roll=_fixture_test_category3_skill_feature_actions.Tests.roll
 def fixture(self,r=None):
  _fixture_test_category3_skill_feature_actions.Tests.fixture(self,r)
  for actor in self.e.everyone:actor.spec['feats']=[F.MONKEY_CSV]
 def setUp(self):self.fixture()
 def opts(self,roll_id='r',**kw):
  options=_fixture_test_category3_skill_feature_actions.Tests.opts(self,roll_id,**kw);options['feature']=F.MONKEY_CSV;return options
 def used(self,actor=None):return (actor or self.t).spec.get('frequency_state',{}).get('activations',{}).get(F.MONKEY_CSV,{}).get('used',0)
 test_native_observed_first_optional_choice_new_dice_plus_two=_fixture_test_category3_skill_feature_actions.Tests.test_native_observed_first_optional_choice_new_dice_plus_two
 test_decline_success_and_failed_checks_are_all_legal_choices=_fixture_test_category3_skill_feature_actions.Tests.test_decline_success_and_failed_checks_are_all_legal_choices
 test_daily_three_in_one_scene_and_source_new_day_refresh=_fixture_test_category3_skill_feature_actions.Tests.test_daily_three_in_one_scene_and_source_new_day_refresh
 test_resolved_identity_cannot_reactivate_change_actor_or_recreate_initial_roll=_fixture_test_category3_skill_feature_actions.Tests.test_resolved_identity_cannot_reactivate_change_actor_or_recreate_initial_roll
 test_observed_choice_error_preserves_first_and_retry_cannot_change_it=_fixture_test_category3_skill_feature_actions.Tests.test_observed_choice_error_preserves_first_and_retry_cannot_change_it
 test_common_action_actual_check_and_outcome_use_final_observed_roll=_fixture_test_category3_skill_feature_actions.Tests.test_common_action_actual_check_and_outcome_use_final_observed_roll
 test_native_check_closes_raw_observation_against_post_result_feature=_fixture_test_category3_skill_feature_actions.Tests.test_native_check_closes_raw_observation_against_post_result_feature
 test_real_ap_assistance_owned_edge_timing_and_penalty_carry_once=_fixture_test_category3_skill_feature_actions.Tests.test_real_ap_assistance_owned_edge_timing_and_penalty_carry_once
 test_triggered_free_outside_turn_and_status_permission_without_general_grant=_fixture_test_category3_skill_feature_actions.Tests.test_triggered_free_outside_turn_and_status_permission_without_general_grant
 test_late_reroll_rng_error_keeps_first_but_rolls_back_new_cost=_fixture_test_category3_skill_feature_actions.Tests.test_late_reroll_rng_error_keeps_first_but_rolls_back_new_cost
 def test_actual_csv_ownership_and_three_distinct_adept_skills_are_required(self):
  for feats in ([],[F.MONKEY_CSV,F.MONKEY_CSV],[F.MONKEY_CSV,F.MONKEY]):
   self.t.spec['feats']=feats;before=self.e.rng.getstate()
   with self.assertRaises(ValueError):self.roll()
   self.assertEqual(self.e.rng.getstate(),before);self.assertFalse(self.e._ap_rolls)
  self.t.spec['feats']=[F.MONKEY_CSV]
  self.t.spec['skills']={'육상':4,'Athletics':4,'통찰':4}
  with self.assertRaises(ValueError):self.roll()
  self.assertFalse(self.e._ap_rolls)
 def test_excluded_or_changed_csv_source_refuses_before_first_observation(self):
  old=self.r.ruleset;self.r.ruleset=RuleFilter({'sources':['core'],'exclude_units':[F.MONKEY_CSV]});self.r._apply_ruleset()
  try:
   with self.assertRaises(ValueError):self.roll()
   self.assertFalse(self.e._ap_rolls)
  finally:self.r.ruleset=old;self.r._apply_ruleset()
  original=Path.read_bytes
  def changed(path):
   raw=original(path);return raw+b'changed' if path.name=='feats.csv' else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaises(ValueError):self.roll()
  self.assertFalse(self.e._ap_rolls)
 def test_json_restore_keeps_final_result_daily_cost_and_exact_source(self):
  self.roll();restored=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
  actor=W.actor_index(restored)[self.t.entity_id];event=F.event(restored,actor,'r')
  self.assertEqual((event.feature,event.final.total),(F.MONKEY_CSV,10))
  self.assertEqual(actor.spec['frequency_state']['activations'][F.MONKEY_CSV]['used'],1)
  with self.assertRaises(ValueError):restored.skill_roll(actor,'육상',**self.opts())

if __name__=='__main__':unittest.main()
