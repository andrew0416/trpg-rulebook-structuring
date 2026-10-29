"""Selected CSV89 reuses actual target-aware elemental rolls without core extras."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,unittest
from engine import Rules,Engine,Combatant
import test_category3_elemental_connection as BASE
import elemental_connection as E,items as ITEMS,state_grants as G,state_codec as CODEC
from ruleset import ExcludedRuleSelection

ROOT=Path(__file__).resolve().parents[1]

class HomebrewElementalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all');cls.core=Rules(ROOT,ruleset='core')
 actor=BASE.ElementalTests.actor
 roll=BASE.ElementalTests.roll
 def setUp(self):
  BASE.ElementalTests.setUp(self)
  self.a.spec.update(edges=[E.HOMEBREW],edge_choices={E.HOMEBREW:'불꽃'})
 def test_five_actual_target_skills_and_shared_composition_keep_csv_source(self):
  import composition_derive as C
  with patch.object(C,'derive',wraps=C.derive) as shared:
   for skill in E.SKILLS:self.assertEqual(self.roll(skill).total,14)
  self.assertTrue(any(any(row['source']==E.HOMEBREW for row in call.args[1]) for call in shared.call_args_list))
  for skill in ('집중','육상','포켓몬학'):self.assertEqual(self.roll(skill).total,12)
  self.assertEqual(self.e.skill_check(self.a,'매력',14,skill_target=self.p,fixed=[3]*4),(True,14))
 def test_actual_types_targets_and_missing_context_do_not_grant_flat_bonus(self):
  for target in (None,self.other,self.actor('trainer',types=['불꽃'])):self.assertEqual(self.roll(target=target).total,12)
  self.p.types=['물'];self.assertEqual(self.roll().total,12)
  self.p.types=['불꽃','비행'];self.assertEqual(self.roll().total,14)
 def test_no_unprinted_mystic_exclusion_or_repeat_permission(self):
  self.a.spec['edges'].append(E.MYSTIC)
  with self.assertRaisesRegex(ValueError,'mutually exclusive'):ITEMS.register_feats(self.e,self.a)
  with self.assertRaisesRegex(ValueError,'mutually exclusive'):self.roll()
  self.a.spec['edges'][-1]=E.HB_MYSTIC;ITEMS.register_feats(self.e,self.a)
  self.assertEqual(self.roll().total,14)
  self.a.spec['edges'].append(E.HOMEBREW)
  with self.assertRaisesRegex(ValueError,'one acquired'):self.roll()
 def test_distinct_core_policy_is_not_an_alias_or_a_double_bonus(self):
  self.a.spec['edges'].append(E.SOURCE);self.a.spec['edge_choices'][E.SOURCE]='물'
  before=self.e.rng.getstate()
  with self.assertRaisesRegex(ValueError,'family source selection'):self.roll()
  self.assertEqual(self.e.rng.getstate(),before)
  query=E.family_source_choices(self.e,self.a)
  E.observe_family_source(self.e,self.a,{'value':E.HOMEBREW+'|','reason':'actual HB alternative is active','scope':query['decision_scope']})
  self.assertEqual(self.roll().total,14);self.assertEqual(self.roll(target=self.other).total,12)
 def test_invalid_choice_ownership_and_actor_kind_refuse_before_rng(self):
  for change in ('missing','invalid','duplicate','unowned','pokemon'):
   self.setUp();before=self.e.rng.getstate()
   if change=='missing':self.a.spec['edge_choices']={}
   elif change=='invalid':self.a.spec['edge_choices'][E.HOMEBREW]='에러'
   elif change=='duplicate':self.a.spec['edge_choices']['원소 교감 [홈브류]']='물'
   elif change=='unowned':self.a.spec['edges']=[]
   else:self.a.kind='pokemon';self.a.spec['kind']='pokemon'
   with self.assertRaises(ValueError):self.e.skill_roll(self.a,'매력',skill_target=self.p)
   self.assertEqual(self.e.rng.getstate(),before)
 def test_core_profile_keeps_homebrew_excluded(self):
  e=Engine(self.core,seed=3);a=Combatant(self.core,dict(self.a.spec,edges=[],edge_choices={}))
  a.spec.update(edges=[E.HOMEBREW],edge_choices={E.HOMEBREW:'불꽃'})
  with self.assertRaises(ExcludedRuleSelection):E.choices(e,a,E.HOMEBREW)
 def test_json_restore_repeated_registration_and_actual_source_removal(self):
  ITEMS.register_feats(self.e,self.a);ITEMS.register_feats(self.e,self.a)
  self.assertEqual(self.roll().total,14)
  restored=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  a,p=[next(c for c in restored.everyone if c.entity_id==old.entity_id) for old in (self.a,self.p)]
  self.assertEqual(restored.skill_roll(a,'매력',skill_target=p,fixed=[3]*4).total,14)
  def remove(e,c):c.spec.update(edges=[],edge_choices={})
  G.transition(restored,a,remove)
  self.assertEqual(restored.skill_roll(a,'매력',skill_target=p,fixed=[3]*4).total,12)

if __name__=='__main__':unittest.main()
