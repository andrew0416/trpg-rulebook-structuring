"""Independent original-source boundaries for recovered split-bold rules."""
import hashlib,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from ptk_structure import parse_blocks,match_name,block_source
CASES=json.loads((ROOT/'data/source-boundary-cases.json').read_text(encoding='utf-8'))
class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.units={u['id']:u for u in map(json.loads,(ROOT/'output/ruleunits.jsonl').read_text(encoding='utf-8').splitlines())}
        cls.entities={r['id']:r for kind in ['feat','block'] for r in json.loads((ROOT/f'output/entities/{kind}.json').read_text(encoding='utf-8'))}
    def test_field_value_is_not_a_name(self):
        for line in ['**효과:** 다음 재주를 얻습니다.', '**이름(Name)** 일반 설명', '**랭크 1 전제조건:** 기초', '**효과:** **강화**']:
            self.assertIsNone(match_name(line))
    def test_rank_prerequisites_do_not_terminate_source(self):
        for label in ['모든 랭크 전제조건','랭크 1 전제조건','랭크 2 전제조건','랭크 3 전제조건']:
            source=['**재주(Feature)**','[랭크 3]',f'**{label}:** 기초','항상','**효과:** 대상에게 적용','', '**다음(Next)**']
            self.assertEqual(block_source(source,0), ('\n'.join(source[:5]),5))
    def test_new_rule_ends_previous_source(self):
        for case in CASES:
            heading=(ROOT/case['file']).read_text(encoding='utf-8').splitlines()[case['start']-1]
            before=['**이전(Previous)**','항상','**효과:** 이전 효과','',heading,'**효과:** 다음 효과']
            self.assertEqual(block_source(before,0), ('\n'.join(before[:3]),3))
def make(case):
    def test(self):
        lines=(ROOT/case['file']).read_text(encoding='utf-8').splitlines()
        excerpt='\n'.join(lines[case['start']-1:case['end']])
        self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),case['sha256'])
        blocks=parse_blocks(lines[case['start']-1:case['end']])
        self.assertTrue(blocks)
        self.assertEqual(blocks[0]['name'],case['name'])
        self.assertEqual(blocks[0]['eng'],case['eng'])
        self.assertEqual(blocks[0]['freq'],case['frequency'])
        body,end=block_source(lines,case['start']-1)
        self.assertEqual(end,case['end'])
        self.assertEqual(body,excerpt)
        entity=self.entities[case['id']]
        self.assertEqual(entity['text'],excerpt)
        self.assertEqual(entity['end_line'],case['end'])
        unit=self.units[case['id']]
        self.assertEqual(unit['title'],case['name'])
        self.assertEqual(unit['text']['body'],excerpt)
        self.assertEqual(unit['source']['lines'],[case['start'],case['end']])
        # A following rule cannot inherit this new rule's identity or lose its boundary.
        for other in self.units.values():
            if other['id']==case['id'] or other['source'].get('file')!=case['file'].removeprefix('input/'):continue
            bounds=other['source'].get('lines',[0,0])
            if other['kind']=='entity:feat' and bounds[0]<case['start']:
                self.assertLess(bounds[1],case['start'],other['id'])
    return test
for i,c in enumerate(CASES):setattr(BoundaryTests,'test_source_'+str(i).zfill(3),make(c))
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='BOUNDARY-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='BOUNDARY-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='BOUNDARY-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests))
    paths=[Path(__file__),ROOT/'tools/ptk_structure.py',ROOT/'data/source-boundary-cases.json',ROOT/'output/entities/feat.json',ROOT/'output/entities/block.json',ROOT/'output/ruleunits.jsonl']+[ROOT/f for f in sorted({c['file'] for c in CASES})]
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Source extraction boundaries and text preservation only; not feature semantics.',results=r.rows,source_cases={'BOUNDARY-test_source_'+str(i).zfill(3):c['id'] for i,c in enumerate(CASES)},input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/source-boundary-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if r.wasSuccessful() else 1)
