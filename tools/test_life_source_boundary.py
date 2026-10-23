"""Original-source recovery paragraph preservation, not life-state execution."""
import hashlib,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from ptk_structure import extract_blocks
from mechanize_conditions import mechanize

class LifeSourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines=(ROOT/'input/ch07-combat.md').read_text(encoding='utf-8').splitlines()
        cls.parsed={r['id']:r for r in extract_blocks(str(ROOT/'input'))['condition']}
        cls.saved={r['id']:r for r in json.loads((ROOT/'output/entities/condition.json').read_text(encoding='utf-8'))}
        cls.units={r['id']:r for r in json.loads((ROOT/'data/conditions.json').read_text(encoding='utf-8'))}
    def test_original_recovery_paragraph_preserved_verbatim(self):
        self.assertIn(self.lines[634],self.parsed['condition/기절']['text'])
        self.assertEqual(self.parsed['condition/기절'].get('end_line'),635)
    def test_no_next_condition_absorption(self):
        text=self.parsed['condition/기절']['text']
        self.assertNotIn('실명(Blindness)',text)
        self.assertNotIn('실명은 대상의 시야',text)
    def test_saved_entity_matches_current_source_extraction(self):
        self.assertEqual(self.saved['condition/기절'],self.parsed['condition/기절'])
        self.assertIn(self.lines[634],self.saved['condition/기절']['text'])
    def test_mechanized_unmapped_recovery_is_not_full(self):
        unit=mechanize(self.parsed['condition/기절'])
        self.assertEqual(unit['mech']['coverage'],'partial')
        narrative=' '.join(unit['mech']['data']['narrative'])
        for clause in ['10분','체력을 양수로','모든 지속성 및 휘발성']:
            self.assertIn(clause,narrative)
    def test_saved_mechanization_preserves_source_and_partial_status(self):
        self.assertEqual(self.units['condition/기절'],mechanize(self.parsed['condition/기절']))
        self.assertIn(self.lines[634],self.units['condition/기절']['text']['body'])
        self.assertEqual(self.units['condition/기절']['mech']['coverage'],'partial')
    def test_other_condition_entities_unchanged(self):
        self.assertEqual(set(self.parsed),set(self.saved))
        for key in self.saved:
            if key!='condition/기절':self.assertEqual(self.parsed[key],self.saved[key],key)
    def test_original_trigger_remains_present(self):
        unit=mechanize(self.parsed['condition/기절'])
        self.assertTrue(any(e.get('type')=='trigger' and e.get('when')=='hp<=0' for e in unit['mech']['data']['effects']))
        self.assertIn('재주이나 특성이 구체적으로 다르게',unit['text']['body'])

class Result(unittest.TextTestResult):
    def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
    def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='LIFE-SOURCE-'+t._testMethodName,status='pass'))
    def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='LIFE-SOURCE-'+t._testMethodName,status='fail'))
    def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='LIFE-SOURCE-'+t._testMethodName,status='error'))
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=1,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(LifeSourceBoundaryTests))
    files=['tools/test_life_source_boundary.py','tools/ptk_structure.py','tools/mechanize_conditions.py','input/ch07-combat.md','output/entities/condition.json','data/conditions.json']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Condition faint source boundary and mechanization only; no runtime semantics certification.',engine_conformance=False,whole_rule_certified=False,tests_run=result.testsRun,results=result.rows,input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files})
    (ROOT/'output/life-source-boundary-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
