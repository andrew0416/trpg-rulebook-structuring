"""Parent independent review: rendering acceptance and annotation-consumer boundaries."""
from pathlib import Path
from fractions import Fraction
from decimal import Decimal,ROUND_DOWN,ROUND_HALF_UP
import copy,hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import audit_common_probabilities as audit
class Tests(unittest.TestCase):
 def test_display_acceptance_matches_decimal_rendering(self):
  for digits in range(3):
   quantum=Decimal(1).scaleb(-digits)
   for integer in range(0,10001,7):
    percent=Decimal(integer)/100
    allowed={percent.quantize(quantum,rounding=mode) for mode in [ROUND_DOWN,ROUND_HALF_UP]}
    nearest=percent.quantize(quantum,rounding=ROUND_HALF_UP)
    for stated in [nearest-quantum,nearest,nearest+quantum]:
     self.assertEqual(audit.agrees({'stated':format(stated,f'.{digits}f'),'relation':'approx'},Fraction(integer,10000)),stated in allowed)
 def test_exact_threshold_outcomes_explain_dc10_mismatch(self):
  # Coefficients of x^10 in (x+...+x^6)^3 and ^4, calculated by bounded compositions.
  self.assertEqual(audit.probability(3,10)-audit.probability(3,11),Fraction(27,216))
  self.assertEqual(audit.probability(4,10)-audit.probability(4,11),Fraction(80,1296))
  self.assertEqual(audit.probability(2,10),Fraction(1,6))
 def test_annotated_correction_is_not_raw_source_agreement(self):
  report=audit.audit(ROOT)
  self.assertEqual(report['derived_annotations']['status'],'verified')
  self.assertEqual(len(report['derived_annotations']['corrected_guidance']),4)
  self.assertEqual(set(report['conflicts']),{f'SKILL-PROB-L{line}-DC{dc}-R{rank}' for line,dc,rank in [(1439,10,3),(1439,10,4),(1441,10,3),(1441,10,4),(1441,22,6),(1441,26,5)]})
  self.assertFalse(report['derived_annotations']['raw_source_agreement'])
 def test_correct_fraction_cannot_mask_wrong_display_or_location(self):
  original=json.loads((ROOT/'data/verification/common-probability-corrections.json').read_text(encoding='utf8'))
  for field in ['display','location','stated','closure']:
   value=copy.deepcopy(original)
   if field=='display':value['corrections'][0]['derived']['display_percent_2dp']='84.1'
   elif field=='location':value['corrections'][0]['locations'][0]['claim']='wrong source'
   elif field=='stated':value['corrections'][0]['source_stated']='90.28'
   else:value['source_arithmetic_conflicts_resolved']=True
   self.assertTrue(audit.validate_annotations(ROOT,value),field)
 def test_modifier_changes_threshold_not_comparator(self):
  sys.path.insert(0,str(ROOT/'engine'))
  import common_checks as checks
  # Source's +4/DC14 example has equality at raw 10.
  self.assertEqual(audit.probability(3,14-4),Fraction(5,8))
  self.assertTrue(checks.against_dc(checks.SkillRoll(3,(3,3,4),modifier=4),14).passed)
  self.assertFalse(checks.against_dc(checks.SkillRoll(3,(3,3,3),modifier=4),14).passed)
 def test_audit_does_not_rewrite_source_or_annotations(self):
  paths=[ROOT/'input/ch11-running-the-game.md',ROOT/'data/verification/common-probability-corrections.json']
  before=[p.read_bytes() for p in paths];audit.audit(ROOT)
  self.assertEqual(before,[p.read_bytes() for p in paths])
class Result(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'PROB-INDEP-'+t._testMethodName,'status':'pass'})
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':'PROB-INDEP-'+t._testMethodName,'status':'fail'})
 def addError(self,t,e):super().addError(t,e);self.rows.append({'id':'PROB-INDEP-'+t._testMethodName,'status':'error'})
if __name__=='__main__':
 r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/capability_actions.py','engine/physical_limits.py','data/capability-policy.json','engine/temporary_hp.py','tools/test_common_probability_independent.py','tools/audit_common_probabilities.py','data/verification/common-probability-corrections.json','engine/common_checks.py','input/ch06-gameplay.md','input/ch11-running-the-game.md']
 (ROOT/'output/common-probability-independent-tests.json').write_text(json.dumps({'successful':r.wasSuccessful(),'results':r.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},'whole_semantic_closure':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 sys.exit(not r.wasSuccessful())
