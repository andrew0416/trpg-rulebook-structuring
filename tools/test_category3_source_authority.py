"""C3-CORE-003/C3-EX-001: actual read authority without invented precedence."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from ruleset import RuleFilter,RuleSelection,UnresolvedRuleSelection,ExcludedRuleSelection
import source_context as SC
SCOPES={'C3-CORE-003':'6c2cc1cd72437d09965e6f00919cb9ec887ac97c222814bffed3e1aa8bbddedc','C3-EX-001':'ef173a26fd41ab5739cf93440d349f4030c2dd5cbf71c4ea41dfa9c7982858df'}
class Tests(unittest.TestCase):
 def setUp(self):self.r=Rules(ROOT,ruleset='core');self.e=Engine(self.r,seed=313)
 def actor(self):return Combatant(self.r,{'id':'trainer/source','name':'Source','kind':'trainer','level':10,'types':['불꽃'],'stats':{'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5}})
 def explanation(self,uid='combat/hit-points'):
  return SC.add_ptu_explanation(self.r,uid,reference='PTU 1.05: HP explanatory reference',explanation='An explanation may describe PTU differences; it never installs an HP formula.',reason='Use PTU to explain details omitted by the PTK house revision')
 def test_fixed_scopes_and_full_original_anchors(self):
  rows=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries']
  for uid,sha in SCOPES.items():
   row=next(r for r in rows if r['id']==uid);self.assertEqual(row['scope_sha256'],sha)
   ss=row['source_snapshot'];anchors=ss.get('source_anchors',[ss.get('source')])
   for a in anchors:
    lines=(ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines();excerpt='\n'.join(lines[a.get('start_line',a.get('start'))-1:a.get('end_line',a.get('end'))])
    self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),a['excerpt_sha256'])
 def test_native_hp_retains_explicit_ptk_formula_after_ptu_explanation(self):
  row=self.explanation();a=self.actor();self.assertEqual(a.base_max_hp,60)
  rec=SC.latest(self.r,'formula:max_hp.trainer');self.assertEqual(rec['authority'],'selected_source')
  self.assertEqual(rec['resolved_value'],'level*2 + hp*3 + 10');self.assertEqual(rec['ptu_supplemental_explanations'],[row])
  self.assertFalse(row['executable']);self.assertFalse(rec['automatic_edition_precedence'])
 def test_supplement_annotation_cannot_supply_a_missing_mechanical_field(self):
  self.explanation();self.assertNotIn('invented_rule',self.r.mech('combat/hit-points'))
  with self.assertRaises(KeyError):self.e.formula('invented_rule')
  self.assertFalse(hasattr(self.r,'invented_rule'));self.assertFalse(self.r.rulings.formulas)
 def test_unknown_or_excluded_reference_does_not_admit_sources(self):
  with self.assertRaises(UnresolvedRuleSelection):self.explanation('ptu/missing-rule')
  self.r.ruleset=RuleFilter({'sources':['core'],'exclude_units':['combat/hit-points']});self.r._apply_ruleset()
  with self.assertRaises(ExcludedRuleSelection):self.explanation()
  with self.assertRaises(ExcludedRuleSelection):self.r.mech('combat/hit-points')
  self.assertFalse(getattr(self.r,'_ptu_explanations',{}))
 def test_explicit_gm_formula_drives_actual_hp_and_stays_table_authority(self):
  a=self.actor();original=deepcopy(self.r.units['combat/hit-points']);self.explanation()
  self.e.rule_formula('max_hp.trainer','level + hp*5 + 10',reason='This table explicitly changes HP',scope='scene')
  self.assertEqual(a.base_max_hp,70)
  rec=SC.latest(self.r,'formula:max_hp.trainer');self.assertEqual(rec['authority'],'table_ruling');self.assertFalse(rec['ruling_is_source_text'])
  self.assertEqual(rec['table_ruling']['reason'],'This table explicitly changes HP');self.assertEqual(self.r.units['combat/hit-points'],original)
  self.assertTrue(rec['ptu_supplemental_explanations']);self.e.end_scene();self.assertEqual(a.base_max_hp,60)
  self.assertEqual(SC.latest(self.r,'formula:max_hp.trainer')['authority'],'selected_source')
 def test_table_only_formula_has_no_fictional_source_identity(self):
  self.e.rule_formula('table.only','x+3',reason='Explicit table invention')
  self.assertEqual(self.e.formula('table.only',x=4),7)
  rec=SC.latest(self.r,'formula:table.only');self.assertEqual(rec['authority'],'table_ruling');self.assertIsNone(rec['selected_id']);self.assertIsNone(rec['selected_source'])
 def test_gm_formula_keeps_existing_authority_when_ordinary_source_excluded(self):
  self.e.rule_formula('stab','4',reason='Explicit table-only STAB decision')
  self.r.ruleset=RuleFilter({'sources':['core'],'exclude_units':['combat/stab']});self.r._apply_ruleset()
  self.assertEqual(self.e.formula('stab'),4)
  rec=SC.latest(self.r,'formula:stab');self.assertEqual(rec['authority'],'table_ruling');self.assertIsNone(rec['selected_id'])
  self.assertEqual(rec['source_selection_status'],'ExcludedRuleSelection');self.assertFalse(rec['ruling_is_source_text'])
  with self.assertRaises(ExcludedRuleSelection):self.r.mech('combat/stab')
 def test_table_mech_patch_changes_real_damage_base_without_changing_book(self):
  a=self.actor();move=self.r.move('move/불꽃세례');before=self.e.damage_base(a,move)
  original=deepcopy(self.r.units['combat/stab']);self.e.rule_mech('combat/stab','damage_base_bonus',5,reason='This table uses STAB +5',scope='scene')
  self.assertEqual(self.e.damage_base(a,move),before+3)
  rec=SC.latest(self.r,'mech:combat/stab');self.assertEqual(rec['original_value']['damage_base_bonus'],2)
  self.assertEqual(rec['resolved_value']['damage_base_bonus'],5);self.assertEqual(rec['authority'],'table_ruling');self.assertEqual(self.r.units['combat/stab'],original)
  self.e.end_scene();self.assertEqual(self.e.damage_base(a,move),before)
 def test_selected_unit_version_is_explicit_not_an_automatic_ptu_override(self):
  before=self.r.mech('pokemon/capture-rate');self.assertEqual(before['roll'],'1d20 + trainer_bonus')
  self.r.ruleset=RuleFilter({'sources':['core'],'unit_versions':{'pokemon/capture-rate':'_superseded_version'}});self.r._apply_ruleset()
  after=self.r.mech('pokemon/capture-rate');self.assertEqual(after['roll'],'1d100 - trainer_level')
  rec=SC.latest(self.r,'mech:pokemon/capture-rate');self.assertEqual(rec['unit_version'],'_superseded_version');self.assertFalse(rec['profile_is_source_authority'])
  self.assertFalse(rec['automatic_edition_precedence'])
 def test_conflicting_variants_need_explicit_choice_and_receipt_does_not_certify_engine(self):
  def unit(uid,title):return {'id':uid,'title':title,'kind':'entity:move','source':{'file':'db/moves.csv'}}
  selection=RuleSelection(RuleFilter({'sources':['core'],'variants':'*','variant_replaces_core':True}),[unit('move/x','X'),unit('move/x-playtest','X [Playtest]'),unit('move/x-홈브류','X [홈브류]')])
  with self.assertRaises(UnresolvedRuleSelection):selection.resolve('move/x')
  self.e.formula('stab');self.assertFalse(SC.latest(self.r,'formula:stab')['whole_engine_certified'])
 def test_provenance_copies_do_not_mutate_original_or_active_ruling(self):
  row=self.explanation();row['explanation']='caller mutation';self.e.rule_formula('stab','4',reason='table')
  self.e.formula('stab');rec=SC.latest(self.r,'formula:stab');rec['table_ruling']['expr']='99'
  self.assertEqual(self.e.formula('stab'),4);self.assertNotEqual(self.r._ptu_explanations['combat/hit-points'][0]['explanation'],'caller mutation')
 def test_profile_change_with_gm_patch_does_not_reuse_old_version_cache(self):
  uid='pokemon/capture-rate';self.r.rulings.set_mech(uid,'throw.ac',7,reason='table target AC')
  self.assertEqual(self.r.mech(uid)['roll'],'1d20 + trainer_bonus')
  self.r.ruleset=RuleFilter({'sources':['core'],'unit_versions':{uid:'_superseded_version'}});self.r._apply_ruleset()
  self.assertEqual(self.r.mech(uid)['roll'],'1d100 - trainer_level');self.assertEqual(self.r.mech(uid)['throw']['ac'],7)

 def test_explanation_cannot_attach_to_a_changed_target_source(self):
  from unittest.mock import patch
  uid='combat/hit-points';source=self.r.selection.units[uid]['source']['file']
  original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b'\nchanged' if path.as_posix().endswith('/input/'+source) else raw
  before=deepcopy(getattr(self.r,'_ptu_explanations',{}))
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'source changed'):self.explanation(uid)
  self.assertEqual(getattr(self.r,'_ptu_explanations',{}),before)

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=[str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py')]+['tools/test_category3_source_authority.py','input/ch00-front.md','input/ch01-intro.md','data/rulesets.json','data/core-rules.json','output/ruleunits.jsonl']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'completion_scopes':list(SCOPES),'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
 (ROOT/'output/category3-source-authority-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
