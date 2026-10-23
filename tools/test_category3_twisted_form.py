"""Whole C3-EX-103 actual Branded acquisition, native skill/type consumers."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from ruleset import RuleFilter,ExcludedRuleSelection,UnresolvedRuleSelection
import blessing_skill_features as B
import effects
SCOPE='01dcdfa3f368afaf5f055663b793a4c8afcf66023aa25f157ab4cc796d18cd2c'
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='fantasy')
 def setUp(self):
  self.e=Engine(self.rules,seed=123)
  def actor(uid,kind,types):return Combatant(self.rules,{'id':uid,'name':uid,'kind':kind,'level':20,'types':types,
   'stats':{'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},'skills':{'협박':'초보','매력':'초보','교활':'초보','통찰':'초보'}})
  self.a=actor('trainer/branded','trainer',[]);self.p=actor('pokemon/patron','pokemon',['불꽃','고스트']);self.t=actor('trainer/target','trainer',[])
  self.e.everyone=[self.a,self.p,self.t];self.e.gm.everyone=self.e.everyone
 def own(self):self.a.spec.update(feats=[B.BRANDED],gifts=[B.TWISTED])
 def confirm(self):return self.e.confirm_twisted_form(self.a,self.p,appearance='flame-like skin and spectral arms',contract='GM confirms an actual supernatural pact',reason='specific Twisted Form Brand bestowed by this patron')
 def acquired(self):self.own();return self.confirm()
 def reject(self,call):
  before=(deepcopy(self.a.spec),list(self.a._types),self.e.rng.getstate(),list(self.e.log_lines))
  with self.assertRaises((ValueError,ExcludedRuleSelection,UnresolvedRuleSelection)):call()
  self.assertEqual((self.a.spec,self.a._types,self.e.rng.getstate(),self.e.log_lines),before)
 def test_fixed_source_and_full_anchor(self):
  rows=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries']
  row=next(x for x in rows if x['id']=='C3-EX-103');self.assertEqual(row['scope_sha256'],SCOPE)
  for a in row['source_snapshot']['source_anchors']:
   raw=(ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines();excerpt='\n'.join(raw[a['start_line']-1:a['end_line']])
   self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),a['excerpt_sha256'])
 def test_requires_actual_branded_feature_gift_and_explicit_gm_contract(self):
  self.reject(self.confirm);self.a.spec['gifts']=[B.TWISTED];self.reject(self.confirm)
  self.own();self.reject(lambda:self.e.skill_roll(self.a,'협박',fixed=[1]*3))
  self.reject(lambda:self.e.confirm_twisted_form(self.a,self.p,appearance='',contract='pact',reason='approved'))
  self.acquired();self.assertTrue(self.a.spec['_twisted_form']['gm_approved']);self.assertTrue(any('트위스트 폼' in str(x) for x in self.e.log_lines))
 def test_actual_brander_identity_no_clone_no_self_no_missing_type(self):
  self.own();clone=Combatant(self.rules,deepcopy(self.p.spec))
  self.reject(lambda:self.e.confirm_twisted_form(self.a,clone,appearance='a',contract='b',reason='c'))
  self.reject(lambda:self.e.confirm_twisted_form(self.a,self.a,appearance='a',contract='b',reason='c'))
  self.p.types=[];self.reject(self.confirm)
 def test_real_common_skill_consumers_both_penalties_and_bonus(self):
  self.acquired()
  for skill,expected in [('협박',7),('매력',-1),('교활',-1),('통찰',3)]:
   result=self.e.skill_roll(self.a,skill,fixed=[1]*3);self.assertEqual(result.total,expected)
  out=self.e.common_action(self.a,'협박',7,mode='skill',fixed=[1]*3);self.assertTrue(out.check.passed)
 def test_type_grant_drives_native_stab_chart_and_status_immunity(self):
  self.acquired();self.assertEqual(self.a.types,['불꽃','고스트']);self.assertEqual(self.a._types,[])
  mv=self.rules.move('move/불꽃세례');self.assertEqual(self.e.damage_base(self.a,mv),self.e.damage_base(self.t,mv)+2)
  self.assertEqual(self.e.type_multiplier('노말',self.a)[0],0)
  self.assertEqual(self.e.type_multiplier('물',self.a)[0],1.5)
  self.assertFalse(self.e.apply_status(self.a,'화상'));self.assertNotIn('화상',self.a.conditions)
 def test_base_types_and_shared_patron_type_are_not_duplicated(self):
  self.a.types=['불꽃','물'];self.acquired();self.assertEqual(self.a.types,['불꽃','물','고스트'])
  self.a.spec['gifts']=[];self.assertEqual(self.a.types,['불꽃','물'])
 def test_no_free_reselection_and_no_live_remote_patron_transform(self):
  record=self.acquired();self.reject(self.confirm)
  self.p.types=['전기'];self.assertEqual(self.a.types,record['granted_types'])
  self.e.end_scene();self.assertEqual(self.a.types,record['granted_types'])
 def test_source_change_rejected_by_both_skill_and_type_consumers(self):
  self.acquired();old=self.rules.ruleset
  self.rules.ruleset=RuleFilter({'sources':['core','blessings'],'exclude_units':[B.TWISTED]});self.rules._apply_ruleset()
  try:
   self.reject(lambda:self.e.skill_roll(self.a,'협박',fixed=[1]*3))
   self.reject(lambda:self.e.type_multiplier('물',self.a))
  finally:self.rules.ruleset=old;self.rules._apply_ruleset()
 def test_changed_identity_or_duplicate_ownership_cannot_reuse_approval(self):
  self.acquired();self.a.spec['id']='trainer/copied';self.reject(lambda:self.a.types)
  self.a.spec['id']='trainer/branded';self.a.spec['gifts'].append('트위스트 폼');self.reject(lambda:self.a.types)
 def test_gm_snapshot_stores_only_base_types_and_no_ghost_grant_after_removal(self):
  self.a.types=['물'];self.acquired();self.e.gm.snapshot('brand')
  self.a.spec['gifts']=[];self.a.types=['전기'];self.e.gm.restore('brand')
  self.assertEqual(self.a.types,['물','불꽃','고스트']);self.assertEqual(self.a._types,['물'])
  self.a.spec['gifts']=[];self.assertEqual(self.a.types,['물'])
 def test_native_type_mutation_does_not_lose_changes_or_bake_gift_into_base(self):
  self.acquired()
  effects.h_type_change(self.e,self.a,self.a,{'add_type':'물'},{});self.assertIn('물',self.a.types)
  effects.h_type_change(self.e,self.a,self.a,{'lose_type':'물'},{});self.assertNotIn('물',self.a.types)
  effects.h_type_change(self.e,self.a,self.a,{'set_type':'전기'},{});self.assertEqual(self.a.types,['전기','불꽃','고스트'])
  self.a.spec['gifts']=[];self.assertEqual(self.a.types,['전기'])
 def test_getter_is_read_only_and_removing_acquisition_stops_all_grants(self):
  self.acquired();before=(deepcopy(self.a.spec),deepcopy(self.a._types),list(self.e.log_lines))
  for _ in range(3):self.assertEqual(self.a.types,['불꽃','고스트'])
  self.assertEqual((self.a.spec,self.a._types,self.e.log_lines),before)
  self.a.spec['gifts']=[];self.assertEqual(self.e.skill_roll(self.a,'협박',fixed=[1]*3).total,3);self.assertEqual(self.a.types,[])

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=[str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py')]+['tools/test_category3_twisted_form.py','input/supp-blessings.md','data/rulesets.json','data/core-rules.json','output/ruleunits.jsonl']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'completion_scopes':['C3-EX-103'],'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
 (ROOT/'output/category3-twisted-form-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
