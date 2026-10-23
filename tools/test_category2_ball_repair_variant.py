"""CSV repair permission reaches the existing actual failed-capture owner."""
from pathlib import Path
from unittest.mock import patch
import json,unittest
from engine import Rules
from ruleset import RuleFilter
import test_category3_pokemon_activities as _fixture_test_category3_pokemon_activities
import pokemon_activities as P,repair_restore as R,state_codec as CODEC

ROOT=Path(__file__).resolve().parents[1]

class BallRepairVariantTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='all')
 actor=_fixture_test_category3_pokemon_activities.PokemonActivityTests.actor
 act=_fixture_test_category3_pokemon_activities.PokemonActivityTests.act
 own=_fixture_test_category3_pokemon_activities.PokemonActivityTests.own
 state=_fixture_test_category3_pokemon_activities.PokemonActivityTests.state
 repairable=_fixture_test_category3_pokemon_activities.PokemonActivityTests.repairable
 def setUp(self):
  _fixture_test_category3_pokemon_activities.PokemonActivityTests.setUp(self);self.repairable()
  self.a.spec['edges'].remove(P.FEATURES['repair'][0]);self.a.spec['edges'].append(P.REPAIR_CSV)
 def test_actual_csv_ownership_reuses_failed_capture_check_and_restore_once(self):
  with patch.object(R,'finish_ball',wraps=R.finish_ball) as shared,patch.object(self.rules,'_selected_rule',wraps=self.rules._selected_rule) as selected:
   out=self.act('repair_ball',ball_id='b1',fixed=[3,4,4,4])
  shared.assert_called_once();self.assertIn(P.REPAIR_CSV,[call.args[0] for call in selected.call_args_list])
  self.assertEqual((out['check'].total,out['status'],self.a.spec['items']['몬스터볼']),(15,'repaired',0))
  self.assertIn(self.a.spec['broken_balls']['b1']['physical_instance_id'],self.e._physical_objects)
  self.assertEqual(self.a.spec['capture_attempts']['capture-1']['status'],'repaired')
  before=self.state()
  with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1',fixed=[6]*4)
  self.assertEqual(before,self.state())
 def test_failed_actual_repair_and_json_keep_permanent_breakage_without_retry(self):
  out=self.act('repair_ball',ball_id='b1',fixed=[3,3,4,4])
  self.assertEqual((out['check'].total,out['status']),(14,'permanently_broken'))
  restored=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  actor=next(c for c in restored.gm.everyone if c.entity_id==self.a.entity_id)
  self.assertEqual(actor.spec['items']['몬스터볼'],0)
  self.assertEqual(actor.spec['broken_balls']['b1']['status'],'permanently_broken')
  with self.assertRaises(ValueError):restored.pokemon_activity(actor,'repair_ball',ball_id='b1',fixed=[6]*4)
  self.assertEqual(actor.spec['items']['몬스터볼'],0)
 def test_real_crafting_prerequisite_tool_and_failed_capture_are_required(self):
  for case in ('prerequisite','tool','cause','captured','ownership'):
   self.setUp()
   if case=='prerequisite':self.a.spec['edges'].remove(P.FEATURES['basic_balls'][0])
   elif case=='tool':self.a.spec['items'].pop('몬스터볼 공구함')
   elif case=='cause':self.a.spec['broken_balls']['b1']['cause']='terrain_damage'
   elif case=='captured':self.a.spec['capture_attempts']['capture-1']['captured']=True
   else:self.a.spec['edges'].remove(P.REPAIR_CSV)
   before=self.state()
   with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1',fixed=[6]*4)
   self.assertEqual(before,self.state(),case)
 def test_selected_source_exclusion_refuses_without_state_or_rng_change(self):
  old=self.rules.ruleset
  self.rules.ruleset=RuleFilter({'sources':['core'],'exclude_units':[P.REPAIR_CSV]});self.rules._apply_ruleset()
  try:
   before=self.state()
   with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1',fixed=[6]*4)
   self.assertEqual(before,self.state())
  finally:self.rules.ruleset=old;self.rules._apply_ruleset()
 def test_invalid_roll_and_changed_source_refuse_before_observation(self):
  before=self.state()
  with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1',fixed=[6]*3)
  self.assertEqual(before,self.state())
  original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b'changed' if path.name=='edges.csv' else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1',fixed=[6]*4)
  self.assertEqual(before,self.state())
 def test_existing_core_permission_still_works_with_unused_excluded_variant(self):
  self.own('repair');old=self.rules.ruleset
  self.rules.ruleset=RuleFilter({'sources':['core'],'exclude_units':[P.REPAIR_CSV]});self.rules._apply_ruleset()
  try:self.assertEqual(self.act('repair_ball',ball_id='b1',fixed=[3,4,4,4])['status'],'repaired')
  finally:self.rules.ruleset=old;self.rules._apply_ruleset()

if __name__=='__main__':unittest.main()
