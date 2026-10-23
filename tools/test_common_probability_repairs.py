"""Independent exact oracles and source-preserving correction validation."""
from pathlib import Path
from fractions import Fraction
from collections import Counter
from pypdf import PdfReader
import copy,hashlib,importlib.util,itertools,json,math,subprocess,sys,unittest
from audit_common_probabilities import audit,probability,agrees,validate_annotations
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'data/verification/common-probability-corrections.json'
def inclusion_exclusion(k,d):
    fail=sum((-1)**j*math.comb(k,j)*math.comb(d-1-6*j,k)
             for j in range(k+1) if d-1-6*j>=k)
    return Fraction(6**k-fail,6**k)
def load():return json.loads(ART.read_text(encoding='utf8'))
class Tests(unittest.TestCase):
    def test_001_cartesian_and_bounded_composition_agree_at_all_boundaries(self):
        for k in range(1,7):
            counts=Counter(map(sum,itertools.product(range(1,7),repeat=k)))
            for dc in range(0,6*k+3):
                exact=Fraction(sum(n for total,n in counts.items() if total>=dc),6**k)
                self.assertEqual(inclusion_exclusion(k,dc),exact)
                self.assertEqual(probability(k,dc),exact)
    def test_002_four_corrected_values_hard_coded_independently(self):
        expected={(4,10):Fraction(65,72),(3,10):Fraction(5,8),
                  (6,22):Fraction(3527,7776),(5,26):Fraction(7,432)}
        j=load();self.assertEqual(len(j['corrections']),4)
        for c in j['corrections']:
            self.assertEqual(Fraction(c['derived']['numerator'],c['derived']['denominator']),expected[c['rank'],c['dc']])
    def test_003_dc10_mixed_comparator_symptom_not_global_strict_rule(self):
        self.assertTrue(agrees({'stated':'84.1','relation':'approx'},inclusion_exclusion(4,11)))
        self.assertEqual(inclusion_exclusion(3,11),Fraction(1,2))
        self.assertTrue(agrees({'stated':'16.67','relation':'approx'},inclusion_exclusion(2,10)))
        self.assertFalse(agrees({'stated':'16.67','relation':'approx'},inclusion_exclusion(2,11)))
    def test_004_dc26_previous_threshold_matches_but_dc22_neither_neighbor(self):
        self.assertTrue(agrees({'stated':'3.24','relation':'approx'},inclusion_exclusion(5,25)))
        self.assertFalse(agrees({'stated':'3.24','relation':'approx'},inclusion_exclusion(5,26)))
        for k,dc,stated in [(6,22,'45.43')]:
            for d in [dc-1,dc,dc+1]:
                self.assertFalse(agrees({'stated':stated,'relation':'approx'},inclusion_exclusion(k,d)))
    def test_005_audit_epsilon_bug_rejects_neither_round_nor_truncate(self):
        self.assertFalse(agrees({'stated':'50.0','relation':'approx'},Fraction(4991,10000)))
        self.assertFalse(agrees({'stated':'50','relation':'approx'},Fraction(491,1000)))
    def test_006_display_round_and_truncation_exact_boundaries(self):
        for stated,p,expected in [('50.0',Fraction(999,2000),True),
                                   ('50.0',Fraction(10019,20000),True),
                                   ('50.0',Fraction(501,1000),False),
                                   ('0.0',Fraction(0),True),
                                   ('100',Fraction(1),True)]:
            self.assertEqual(agrees({'stated':stated,'relation':'approx'},p),expected)
    def test_007_qualifiers_remain_exact(self):
        self.assertFalse(agrees({'stated':'1','relation':'lt'},Fraction(1,100)))
        self.assertTrue(agrees({'stated':'90','relation':'ge'},Fraction(9,10)))
        self.assertFalse(agrees({'stated':'0','relation':'zero'},Fraction(1,10**9)))
    def test_008_raw_conflicts_preserved_six_locations_and_54_claims(self):
        report=audit(ROOT)
        self.assertEqual(report['status'],'source_conflicts')
        self.assertEqual(len(report['conflicts']),6);self.assertEqual(len(report['claims']),54)
        self.assertTrue(report['derived_annotations']['arithmetic_derivations_verified'])
        self.assertFalse(report['derived_annotations']['raw_source_agreement'])
        self.assertEqual(len(report['derived_annotations']['corrected_guidance']),4)
    def test_009_cli_keeps_nonzero_source_conflict_exit(self):
        p=subprocess.run([sys.executable,'-B','-X','utf8',str(ROOT/'tools/audit_common_probabilities.py')],capture_output=True,text=True,encoding='utf8')
        self.assertEqual(p.returncode,1);self.assertEqual(json.loads(p.stdout)['status'],'source_conflicts')
    def test_010_all_source_anchors_match_actual_files_and_pdf_pages(self):
        readers={}
        for key,a in load()['source_anchors'].items():
            p=ROOT/a['file'];self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),a['file_sha256'])
            if 'start' in a:ex='\n'.join(p.read_text(encoding='utf8').splitlines()[a['start']-1:a['end']])
            else:
                if p not in readers:readers[p]=PdfReader(str(p))
                ex=readers[p].pages[a['page_index']].extract_text()
            self.assertEqual(ex,a['excerpt']);self.assertEqual(hashlib.sha256(ex.encode()).hexdigest(),a['excerpt_sha256'])
    def test_011_inclusive_rule_and_explicit_equality_example_preserved(self):
        a=load()['source_anchors']
        self.assertIn('충족하거나 초과',a['inclusive_success']['excerpt'])
        self.assertIn('meet or exceed',a['PTU-219']['excerpt'])
        self.assertIn('12 to 14',a['PTU-220']['excerpt'])
        self.assertIn('A result of 11',a['PTU-220']['excerpt'])
    def test_012_corrupt_derived_fraction_is_rejected(self):
        j=load();j['corrections'][0]['derived']['numerator']+=1
        self.assertTrue(any(x.startswith('incorrect_derived_fraction') for x in validate_annotations(ROOT,j)))
    def test_013_missing_duplicate_and_unknown_locations_rejected(self):
        for mode in ['missing','duplicate','unknown']:
            j=load()
            if mode=='missing':j['corrections'].pop()
            elif mode=='duplicate':j['corrections'].append(copy.deepcopy(j['corrections'][0]))
            else:j['corrections'][0]['claim_ids'][0]='FAKE'
            self.assertTrue(validate_annotations(ROOT,j))
    def test_014_source_changes_and_false_closure_rejected(self):
        for mode in ['hash','excerpt','remove','closure','model']:
            j=load()
            if mode=='hash':j['source_anchors']['rank_dice']['file_sha256']='0'*64
            elif mode=='excerpt':j['source_anchors']['rank_dice']['excerpt']+='changed'
            elif mode=='remove':j['source_anchors'].clear()
            elif mode=='closure':j['semantic_closure']=True
            else:j['model']['check']='sum(dice)>DC'
            self.assertTrue(validate_annotations(ROOT,j))
    def test_015_existing_runtime_check_uses_inclusive_threshold(self):
        # Read-only copied production common procedure; no engine probabilities imported.
        path=ROOT/'engine/common_checks.py';spec=importlib.util.spec_from_file_location('checks_evidence',path)
        m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
        # The production calculator now has an exact-arithmetic dependency.
        # Load it from the same engine directory; this does not import the
        # probability implementation used by the independent combinatorial oracle.
        engine_path=str(ROOT/'engine');sys.path.insert(0,engine_path)
        try:spec.loader.exec_module(m)
        finally:sys.path.remove(engine_path)
        for faces,dc,passed in [((6,6),12,True),((5,6),12,False),((3,3,4),10,True)]:
            self.assertEqual(m.against_dc(m.SkillRoll(len(faces),faces),dc).passed,passed)
    def test_016_modifier_equivalence_preserves_equality(self):
        for k in range(1,7):
            counts=Counter(map(sum,itertools.product(range(1,7),repeat=k)))
            for mod in [-4,0,4]:
                expected=Fraction(sum(n for total,n in counts.items() if total+mod>=14),6**k)
                self.assertEqual(expected,inclusion_exclusion(k,14-mod))
    def test_017_published_values_are_also_in_saved_english_edition(self):
        text=load()['source_anchors']['PTU-465']['excerpt']
        for value in ['84.1% at Adept','50% at Novice','45.43% at Master','3.24% at Expert']:
            self.assertIn(value,text)
class Result(unittest.TextTestResult):
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
    def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='PROB-REPAIR-'+t._testMethodName,status='pass'))
    def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='PROB-REPAIR-'+t._testMethodName,status='fail',detail=self._exc_info_to_string(e,t)))
    def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='PROB-REPAIR-'+t._testMethodName,status='error',detail=self._exc_info_to_string(e,t)))
if __name__=='__main__':
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    files={'engine/capability_actions.py','engine/physical_limits.py','data/capability-policy.json','engine/temporary_hp.py',Path(__file__).relative_to(ROOT).as_posix(),'tools/audit_common_probabilities.py','data/verification/common-probability-corrections.json','engine/common_checks.py'}
    files.update(a['file'] for a in load()['source_anchors'].values())
    report=dict(successful=r.wasSuccessful(),results=r.rows,tests_run=r.testsRun,source_conflicts_hidden=False,semantic_closure=False,
                input_hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in sorted(files)})
    (ROOT/'output').mkdir(exist_ok=True)
    (ROOT/'output/common-probability-repair-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    sys.exit(not r.wasSuccessful())
