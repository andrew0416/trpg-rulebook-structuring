"""Actual native skill/DC/opposed checks share the sourced contextual +2."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,unittest
from engine import Rules
from ruleset import RuleFilter
import test_category2_progression_state as _fixture_test_category2_progression_state
import skill_modifiers as S,state_codec as CODEC,state_grants as G

ROOT=Path(__file__).resolve().parents[1]

class GlitchEdgeTests(unittest.TestCase):
 SOURCE=S.GLITCH_SOURCE
 ALIAS='버그화'
 SOURCE_FILE='edges.csv'
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.a.spec['edges']=[self.SOURCE]
 def context(self,**changes):
  context=dict(purpose='glitch_phenomenon',reason='GM classifies this check as dealing with the observed Glitch phenomenon')
  context.update(changes);return context
 def options(self,skill='명령',**extra):return dict(fixed=[1]*S.rank(self.r,self.a,skill)[2],**extra)
 def test_every_actual_skill_gains_two_without_changing_rank_or_unrelated_checks(self):
  skills=deepcopy(self.a.spec['skills'])
  with patch.object(S.COMPOSITION,'derive',wraps=S.COMPOSITION.derive) as common:
   for skill in self.r.skill_policy['skills']:
    options=self.options(skill);ordinary=self.e.skill_roll(self.a,skill,**options)
    out=self.e.skill_roll(self.a,skill,skill_context=self.context(),**options)
    self.assertEqual(out.total,ordinary.total+2,skill)
    self.assertEqual(out.modifier,ordinary.modifier+2)
  self.assertTrue(common.called);self.assertEqual(self.a.spec['skills'],skills)
 def test_actual_dc_and_common_nonconsuming_plan_use_same_bonus(self):
  options=self.options();ordinary=self.e.skill_roll(self.a,'명령',**options)
  before=self.snap();planned=self.e.plan_skill_check(self.a,'명령',purpose='resolve_glitch',skill_context=self.context(),**options)
  self.assertEqual(before,self.snap());self.assertEqual(planned['modifier'],2)
  self.assertEqual(sum(x[0]==self.SOURCE for x in planned['sources']),1)
  out=self.e.skill_check(self.a,'명령',ordinary.total+2,skill_context=self.context(),**options)
  self.assertEqual(out,(True,ordinary.total+2))
 def test_actual_opposition_keeps_bonus_on_only_its_bound_actor(self):
  other=self.add(dict(self.a.spec,id='trainer/other',edges=[]))
  out=self.e.opposed_check(self.a,'명령',other,'명령',challenger_options=self.options(skill_context=self.context()),defender_options=self.options())
  self.assertTrue(out)
  self.assertFalse(self.e.opposed_check(self.a,'명령',other,'명령',challenger_options=self.options(),defender_options=self.options()))
 def test_unowned_and_unrelated_context_do_not_gain_bonus(self):
  plain=self.e.skill_roll(self.a,'명령',**self.options()).total
  for context in (None,{'purpose':'climb','reason':'GM observes an ordinary climbing check'}):
   self.assertEqual(self.e.skill_roll(self.a,'명령',skill_context=context,**self.options()).total,plain)
  self.a.spec['edges']=[]
  self.assertEqual(self.e.skill_roll(self.a,'명령',skill_context=self.context(),**self.options()).total,plain)
 def test_bad_scope_missing_observation_and_duplicate_ownership_refuse_before_rng(self):
  for changes in ({'purpose':'unknown_purpose'},{'reason':''},{'reason':1},{'unexpected':True}):
   before=self.snap()
   with self.assertRaises(ValueError):self.e.skill_roll(self.a,'명령',skill_context=self.context(**changes))
   self.assertEqual(before,self.snap())
  self.a.spec['edges'].append(self.ALIAS);before=self.snap()
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'명령',skill_context=self.context())
  self.assertEqual(before,self.snap())
 def test_excluded_or_changed_selected_source_refuses_before_rng(self):
  old=self.r.ruleset;self.r.ruleset=RuleFilter({'sources':['core'],'exclude_units':[self.SOURCE]});self.r._apply_ruleset()
  try:
   before=self.snap()
   with self.assertRaises(ValueError):self.e.skill_roll(self.a,'명령',skill_context=self.context())
   self.assertEqual(before,self.snap())
  finally:self.r.ruleset=old;self.r._apply_ruleset()
  original=Path.read_bytes
  def changed(path):
   raw=original(path);return raw+b'changed' if path.name==self.SOURCE_FILE else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaises(ValueError):self.e.skill_roll(self.a,'명령',skill_context=self.context())
  self.assertEqual(before,self.snap())
 def test_json_and_native_source_removal_preserve_scoped_behavior(self):
  restored=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  actor=next(c for c in restored.gm.everyone if c.entity_id==self.a.entity_id)
  self.assertEqual(restored.skill_roll(actor,'명령',skill_context=self.context(),**self.options()).total,6)
  G.transition(self.e,self.a,lambda e,c:c.spec.update(edges=[]))
  self.assertEqual(self.e.skill_roll(self.a,'명령',skill_context=self.context(),**self.options()).total,4)

 def test_printed_alias_preserves_the_actual_selected_source(self):
  self.a.spec['edges']=[self.ALIAS]
  planned=self.e.plan_skill_check(self.a,'명령',purpose='resolve_glitch',skill_context=self.context(),**self.options())
  self.assertEqual(planned['modifier'],2)
  self.assertEqual(sum(source[0]==self.SOURCE for source in planned['sources']),1)


class GlitchedExistenceTests(GlitchEdgeTests):
 SOURCE=S.GLITCH_BODY_SOURCE
 ALIAS='버그의 존재'
 SOURCE_FILE='supp-polygon.md'

 def test_mixed_source_versions_require_one_actual_acquisition_before_rng(self):
  self.a.spec['edges']=[self.SOURCE,S.GLITCH_SOURCE]
  before=self.snap()
  with self.assertRaises(ValueError):
   self.e.skill_roll(self.a,'명령',skill_context=self.context())
  self.assertEqual(self.snap(),before)


if __name__=='__main__':unittest.main()
