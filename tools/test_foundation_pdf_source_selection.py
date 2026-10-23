"""Explicit PDF provenance and supplemental policy selection, no core override."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules
from ruleset import RuleFilter,RuleSelection

class PDFSourceSelectionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.loaded=Rules(ROOT,ruleset='all')
  cls.package=json.loads((ROOT/'data/gravity-source-policy-package.json').read_text(encoding='utf-8'))
 def setUp(self):self.rules=copy(self.loaded)
 def load(self):
  result=self.rules.load_source_policy_package(self.package)
  self.assertEqual(result[0]['status'],'PolicyInputsRequired')
  return self.rules.source_policy_document(self.package['policies'][0]['id'])
 def choices(self):
  document=self.rules.source_policy_document(self.package['policies'][0]['id'])
  scope=self.rules.resolve_source_policy(document)['decision_scope']
  return {name:{'value':value,'reason':'explicit scoped table choice',**({'scope':scope} if name!='use_supplement' else {})} for name,value in [('use_supplement',True),('jump_composition','compound_per_step'),('jump_rounding','floor_final')]}
 def test_pdf_pages_and_snapshot_survive_common_selection_without_core_override(self):
  before=deepcopy(self.rules.move(self.rules.move_id('중력')))
  document=self.load();source=self.package['sources'][0]
  record=self.rules.select_source_definition(source['id'])
  self.assertEqual(record['source']['pages'],[21,22])
  self.assertEqual(record['verified_reference'],source['source'])
  self.assertEqual(self.rules.validate_source_selection(record),record)
  self.assertEqual(self.rules.move(self.rules.move_id('중력')),before)
  pending=self.rules.resolve_source_policy(document)
  self.assertIsNone(pending['values']);self.assertEqual(len(pending['obligations']),5)
 def test_explicit_nondefault_home_gravity_and_arithmetic_stay_policy_values_only(self):
  document=self.load()
  result=self.rules.resolve_source_policy(document,context={'home_gravity':1,'environment_gravity':0},decisions=self.choices())
  self.assertEqual(result['values']['home_gravity'],1)
  self.assertEqual(result['values']['environment_gravity'],0)
  self.assertEqual(result['values']['supplemental_gravity_move_environment'],5)
  self.assertFalse(result['effects_executed'])
  choices=self.choices();choices['use_supplement']['value']=False
  self.assertIs(self.rules.resolve_source_policy(document,context={'home_gravity':3,'environment_gravity':5},decisions=choices)['values']['use_supplement'],False)
 def test_missing_arithmetic_is_pending_and_out_of_range_gravity_is_rejected(self):
  document=self.load();decisions={'use_supplement':self.choices()['use_supplement']}
  result=self.rules.resolve_source_policy(document,context={'home_gravity':3,'environment_gravity':4},decisions=decisions)
  self.assertEqual(result['status'],'PolicyInputsRequired');self.assertIsNone(result['values'])
  for bad in (-1,6,True):
   with self.assertRaises(ValueError):self.rules.resolve_source_policy(document,context={'home_gravity':bad,'environment_gravity':0},decisions=self.choices())
 def test_invalid_pdf_page_bounds_publish_no_partial_registration(self):
  for bounds in ([0,21],[21,157],[True,22],[22,21],[21]):
   package=deepcopy(self.package);package['sources'][0]['locator']['pages']=bounds
   before=self.rules.selection
   with self.assertRaisesRegex(ValueError,'PDF'):self.rules.load_source_policy_package(package)
   self.assertIs(self.rules.selection,before)
   self.assertNotIn(package['sources'][0]['id'],self.rules.selection.units)
 def test_changed_pdf_is_rejected_without_a_caller_hash(self):
  self.load();original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b'changed' if path.name=='supp-polygon-original.pdf' else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'source changed'):self.rules.select_source_definition(self.package['sources'][0]['id'])
 def test_excluded_supplement_cannot_enter_through_authored_registration(self):
  self.rules.ruleset=RuleFilter({'sources':['core']})
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.loaded.selection.units.values()))
  before=self.rules.selection
  with self.assertRaises(ValueError):self.load()
  self.assertIs(self.rules.selection,before)

if __name__=='__main__':unittest.main()
