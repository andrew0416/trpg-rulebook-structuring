"""Independent dice enumeration and source-census corruption tests."""
import copy,hashlib,itertools,json,tempfile,unittest
from collections import Counter
from datetime import datetime,timezone
from fractions import Fraction
from pathlib import Path
from audit_common_probabilities import distribution,probability,parse_claims,agrees,audit
from audit_common_source_inventory import build,validate
ROOT=Path(__file__).resolve().parents[1]
class CommonSourceTests(unittest.TestCase):
    def test_all_base_rank_distributions_match_cartesian_enumeration(self):
        for k in range(1,7):
            with self.subTest(rank=k):
                brute=Counter(map(sum,itertools.product(range(1,7),repeat=k)))
                self.assertEqual(distribution(k),brute)
                self.assertEqual(sum(brute.values()),6**k)
    def test_dc_equality_succeeds(self):
        self.assertEqual(probability(1,6),Fraction(1,6))
        self.assertEqual(probability(1,7),0)
        self.assertEqual(probability(1,1),1)
    def test_known_corrected_common_probabilities(self):
        self.assertEqual(probability(3,10),Fraction(5,8))
        self.assertEqual(probability(4,10),Fraction(65,72))
        self.assertEqual(probability(5,26),Fraction(7,432))
        self.assertEqual(probability(6,22),Fraction(46656-4332,2*46656))
    def test_probability_qualifiers_preserved(self):
        c=parse_claims('초보에서 1% 미만. 달인에서 90%이상의 성공률.',18,1)
        self.assertEqual([x['relation'] for x in c],['lt','ge'])
        self.assertTrue(agrees(c[0],Fraction(1,216)))
        self.assertFalse(agrees(c[0],Fraction(1,100)))
        self.assertTrue(agrees(c[1],Fraction(9,10)))
    def test_rank_and_above_expands_explicitly(self):
        c=parse_claims('미숙 이상에서 90% 이상 성공률',4,1)
        self.assertEqual([x['rank'] for x in c],[2,3,4,5,6])
    def test_impossible_claim_means_zero(self):
        c=parse_claims('미숙은 불가능',14,1)[0]
        self.assertTrue(agrees(c,Fraction(0)));self.assertFalse(agrees(c,Fraction(1,100000)))
    def test_current_probability_source_claim_set(self):
        r=audit(ROOT)
        expected={4:{1,2,3,4,5,6},6:{1,2,3,4,5,6},8:{1,2,3},10:{2,3,4},12:{2,3,4,5,6},14:{2,3,4,5},16:{3,4,5,6},18:{3,4,5,6},20:{3,4,5,6},22:{4,5,6},24:{4,5,6},26:{4,5,6},28:{5,6},30:{6}}
        self.assertEqual({(c['dc'],c['rank']) for c in r['claims'] if c['line']==1441},{(dc,k) for dc,ks in expected.items() for k in ks})
        self.assertEqual(len(r['claims']),54)
    def test_current_source_conflicts_are_exposed(self):
        r=audit(ROOT)
        self.assertEqual(set(r['conflicts']),{'SKILL-PROB-L1439-DC10-R4','SKILL-PROB-L1439-DC10-R3','SKILL-PROB-L1441-DC10-R4','SKILL-PROB-L1441-DC10-R3','SKILL-PROB-L1441-DC22-R6','SKILL-PROB-L1441-DC26-R5'})
        self.assertEqual(r['status'],'source_conflicts')
    def test_invalid_base_rank_rejected(self):
        for rank in [0,7,True,1.5]:
            with self.assertRaises(ValueError):distribution(rank)
    def fixture(self):
        tmp=tempfile.TemporaryDirectory(prefix='common-rule-audit-');self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);(root/'input').mkdir();(root/'input/book.md').write_text('# Book\n\nRule one.\nRule two.\n\n|a|b|\n\n[img]\n',encoding='utf-8');return root,build(root)
    def test_nonblank_inventory_exact_partition(self):
        root,inv=self.fixture();self.assertEqual(validate(inv,root),[])
        self.assertEqual([(b['start'],b['end']) for b in inv['blocks']],[(1,1),(3,4),(6,6),(8,8)])
        self.assertIn('image_candidate',inv['blocks'][-1]['flags'])
    def test_missing_source_block_rejected(self):
        root,inv=self.fixture();inv['blocks'].pop(1)
        self.assertIn('nonblank_line_partition_mismatch:input/book.md',validate(inv,root))
    def test_duplicate_source_span_rejected(self):
        root,inv=self.fixture();inv['blocks'].append(copy.deepcopy(inv['blocks'][0]))
        self.assertIn('duplicate_source_block',validate(inv,root))
        self.assertIn('overlapping_source_blocks:input/book.md',validate(inv,root))
    def test_changed_source_rejected(self):
        root,inv=self.fixture();(root/'input/book.md').write_text('Replacement\n',encoding='utf-8')
        self.assertIn('source_file_changed:input/book.md',validate(inv,root))
    def test_new_source_file_rejected(self):
        root,inv=self.fixture();(root/'input/new.md').write_text('New rule',encoding='utf-8')
        self.assertIn('input_file_set_mismatch',validate(inv,root))
    def test_actual_saved_input_census(self):
        inv=json.loads((ROOT/'data/verification/common-source-inventory.json').read_text(encoding='utf-8'))
        self.assertEqual(validate(inv,ROOT),[])
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='COMMON-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='COMMON-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='COMMON-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(CommonSourceTests))
    paths=[Path(__file__),ROOT/'tools/audit_common_source_inventory.py',ROOT/'tools/audit_common_probabilities.py',ROOT/'data/verification/common-source-inventory.json',*sorted(p for p in (ROOT/'input').rglob('*') if p.is_file())]
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Physical source census and exact probability audit checker; not full engine/source conformance.',results=r.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/common-source-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if r.wasSuccessful() else 1)
