"""Source-specific provider domains through the public policy resolver."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules
from ruleset import RuleFilter,RuleSelection

class ProviderSelectionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.loaded=Rules(ROOT,ruleset='all')
  cls.loaded.load_source_policy_package((ROOT/'data/foundation-source-policy-package.json').read_text(encoding='utf-8'))
 def setUp(self):self.r=copy(self.loaded)
 def doc(self,name):return self.r.source_policy_document('source-selection/'+name+'-edge')
 def choose(self,name,uid):return self.r.resolve_source_policy(self.doc(name),context={'choice':uid})
 def test_hobbyist_errata_accepts_only_rank_raising_skill_edges(self):
  for uid in self.doc('hobbyist-errata')['variants'][0]['inputs']['choice']['choices']:
   out=self.choose('hobbyist-errata',uid)
   self.assertEqual(out['values'],{'eligible_definition':uid,'acquisition_approved':False})
   self.assertEqual(out['definition_selections']['choice']['selected_id'],uid)
  for uid in ('edge/스킬-향상','edge/고난이도-스킬','edge/거장','edge/미용사'):
   with self.assertRaisesRegex(ValueError,'invalid policy input'):self.choose('hobbyist-errata',uid)
 def test_dilettante_all_printed_edges_resolve_but_not_arbitrary_edges(self):
  choices=self.doc('dilettante')['variants'][0]['inputs']['choice']['choices']
  self.assertEqual(len(choices),22)
  for uid in choices:
   with self.subTest(uid=uid):self.assertEqual(self.choose('dilettante',uid)['status'],'PolicyValuesReady')
  with self.assertRaisesRegex(ValueError,'invalid policy input'):self.choose('dilettante','edge/기본-스킬')
 def test_dilettante_general_and_training_feature_domain(self):
  doc=self.r.source_policy_document('source-selection/dilettante-feature')
  choices=doc['variants'][0]['inputs']['choice']['choices']
  self.assertEqual(len(choices),18)
  training={uid for uid,u in self.r.selection.units.items() if uid.startswith('feat/') and '훈련' in u.get('tags',[])}
  self.assertEqual(training,{'feat/민첩성-훈련','feat/잔혹성-훈련','feat/집중성-훈련','feat/영감성-훈련'})
  self.assertTrue(training<=set(choices))
  for uid in choices:
   with self.subTest(uid=uid):
    out=self.r.resolve_source_policy(doc,context={'choice':uid})
    self.assertEqual(out['status'],'PolicyValuesReady')
    self.assertEqual(out['definition_selections']['choice']['selected_id'],uid)
    self.assertFalse(out['values']['acquisition_approved'])
  for uid in ('feat/딜레당트','edge/미용사','class/하비스트'):
   with self.subTest(uid=uid),self.assertRaises(ValueError):self.r.resolve_source_policy(doc,context={'choice':uid})
 def test_provider_feature_record_is_invalidated_when_candidate_is_excluded(self):
  doc=self.r.source_policy_document('source-selection/dilettante-feature');uid='feat/퀵-스위치'
  result=self.r.resolve_source_policy(doc,context={'choice':uid})
  self.r.ruleset=RuleFilter({'exclude_units':[uid]})
  self.r.selection=RuleSelection(self.r.ruleset,list(self.loaded.selection.units.values()))
  with self.assertRaises(ValueError):self.r.validate_source_selection(result['definition_selections']['choice'])
  with self.assertRaises(ValueError):self.r.resolve_source_policy(doc,context={'choice':uid})
 def test_missing_choice_stays_pending_and_does_not_grant(self):
  out=self.r.resolve_source_policy(self.doc('hobbyist-errata'))
  self.assertEqual(out['status'],'PolicyInputsRequired');self.assertIsNone(out['values'])
  self.assertFalse(out['effects_executed']);self.assertEqual(out['definition_selections'],{})
 def test_changed_candidate_source_rejects_even_with_unchanged_provider(self):
  native=Path.read_bytes
  def changed(path):return native(path)+(b'changed' if path.name=='ch03-skills-edges-feats.md' else b'')
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'changed'):self.choose('hobbyist-errata','edge/기본-스킬')
 def test_excluded_candidate_rejects_instead_of_returning_stale_choice(self):
  self.r.ruleset=RuleFilter({'exclude_units':['edge/기본-스킬']})
  self.r.selection=RuleSelection(self.r.ruleset,list(self.loaded.selection.units.values()))
  with self.assertRaises(ValueError):self.choose('hobbyist-errata','edge/기본-스킬')
 def test_catalog_kind_and_exact_identity_are_not_plain_strings(self):
  doc=self.doc('dilettante');spec=doc['variants'][0]['inputs']['choice'];spec.pop('choices')
  for uid in ('미용사','feat/딜레당트','edge/not-a-definition'):
   with self.assertRaises(ValueError):self.r.resolve_source_policy(doc,context={'choice':uid})
  spec['type']='integer'
  with self.assertRaisesRegex(ValueError,'definition input'):self.r.resolve_source_policy(doc)

if __name__=='__main__':unittest.main()
