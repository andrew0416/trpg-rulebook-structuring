"""Native scoped precedence and source-preserving normalization counterexamples."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import native_rule_policy as P
from ruleset import RuleFilter

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def values(self,name,**facts):return P.evaluate(self.r,name,facts)['values']
 def test_medicine_scope_matrix_cost_and_debt_are_separate_aspects(self):
  for self_use in (False,True):
   for restorative in (False,True):
    for medic in (False,True):
     actual=self.values('medicine',self_use=self_use,restorative=restorative,medic=medic)
     self.assertEqual(actual['action'],'full' if self_use and restorative else 'standard')
     self.assertEqual(actual['debt'],None if (self_use and restorative) or (medic and not self_use) else {'standard':1,'swift':1})
 def test_dowsing_specific_override_does_not_merge_dice_or_add_six(self):
  self.assertEqual(self.values('skill_stunt',dowsing=False)['pool'],{'dice':-1,'modifier':6})
  self.assertEqual(self.values('skill_stunt',dowsing=True)['pool'],{'dice':1,'modifier':0})
 def test_unknown_and_truthy_strings_cannot_authorize_a_native_effect(self):
  with self.assertRaises(P.PolicyPending):self.values('medicine',self_use=None,restorative=True,medic=False)
  with self.assertRaises(TypeError):self.values('medicine',self_use='false',restorative=True,medic=False)
  with self.assertRaises(P.PolicyPending):P.evaluate(self.r,'future_rule',{})
 def test_applicable_variant_requires_new_policy_but_inapplicable_source_is_not_read(self):
  old=self.r._selected_rule
  def replaced(uid):return uid+'/variant' if uid==P.SOURCE['dowsing'] else old(uid)
  with patch.object(self.r,'_selected_rule',side_effect=replaced):
   self.values('skill_stunt',dowsing=False)
   with self.assertRaises(P.PolicyPending):self.values('skill_stunt',dowsing=True)
 def test_changed_source_does_not_reuse_previous_interpretation(self):
  old=Path.read_bytes
  def changed(path):
   raw=old(path)
   return raw+b'changed' if path.name=='ch09-equipment.md' else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaises(P.PolicyPending) as exc:self.values('medicine',self_use=False,restorative=True,medic=False)
  self.assertEqual(exc.exception.code,'stale_policy_source')
 def test_gm_source_override_cannot_silently_reuse_the_original_policy(self):
  with patch.dict(self.r.rulings.mech,{P.SOURCE['stunt']:{'die':{'value':12}}}):
   with self.assertRaises(P.PolicyPending) as exc:self.values('skill_stunt',dowsing=False)
  self.assertEqual(exc.exception.code,'unreviewed_policy_gm_override')
 def test_receipt_has_contributors_scope_and_profile_without_claiming_engine_certification(self):
  out=P.evaluate(self.r,'skill_stunt',{'dowsing':True})
  self.assertFalse(out['whole_engine_certified']);self.assertFalse(out['model_receipt']['source_ready'])
  self.assertEqual(out['aspects'][0]['contributors'],['stunt.dowsing'])
  self.assertEqual(out['aspects'][0]['dominated'],['stunt.normal'])
 def test_projection_preserves_duration_scope_condition_and_duplicate_effects(self):
  raw=[{'type':'apply_status','status':'독','duration':'1 round'},
       {'type':'stage_change','stat':'atk','delta':1,'on_natural_roll_min':19,'until':'next turn'},
       {'type':'push','meters':1,'if':'hit','target':'all'},
       {'type':'accuracy_mod','value':-1,'target':'self'},
       {'type':'drain','fraction':0.5,'while':'rain'},
       {'type':'zone','shape':'blast'}]
  before=deepcopy(raw);out=Rules.flatten_effects(raw)
  self.assertEqual(out,{'effects_exec':before});self.assertEqual(raw,before)
  raw[0]['duration']='forever';self.assertEqual(out['effects_exec'][0]['duration'],'1 round')
  duplicate=Rules.flatten_effects([{'type':'apply_status','status':'독'},{'type':'apply_status','status':'마비'}])
  self.assertEqual(duplicate['apply_status'],'독');self.assertEqual(duplicate['effects_exec'][0]['status'],'마비')

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 files=['engine/engine.py','engine/native_rule_policy.py','engine/root_resolution.py','engine/items.py','engine/skill_stunts.py','data/native-rule-policy.json','input/ch03-skills-edges-feats.md','input/ch09-equipment.md',__file__]
 files=[str(Path(f).relative_to(ROOT)) if Path(f).is_absolute() else f for f in files]
 (ROOT/'output/native-rule-policy-tests.json').write_text(json.dumps({'passed':result.wasSuccessful(),'tests':result.testsRun,'inputs':[{'file':f,'sha256':hashlib.sha256((ROOT/f).read_bytes()).hexdigest()} for f in files]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
