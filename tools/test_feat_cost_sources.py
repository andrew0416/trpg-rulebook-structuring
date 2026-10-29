"""Every standalone AP frequency line in feat source spans must survive each pipeline stage."""
import hashlib,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'engine')]
from engine import Rules,Engine,Combatant
import items as ITEMS
import action_points as AP
from ptk_structure import parse_blocks
CASES=json.loads((ROOT/'data/source-feat-cost-cases.json').read_text(encoding='utf-8'))
class FeatCostSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entities={(u['chapter']+'.md',u['line']):u for u in json.loads((ROOT/'output/entities/feat.json').read_text(encoding='utf-8'))}
        cls.auto=json.loads((ROOT/'data/feats-mech.json').read_text(encoding='utf-8'))
        cls.units={u['id']:u for u in map(json.loads,(ROOT/'output/ruleunits.jsonl').read_text(encoding='utf-8').splitlines())}
        cls.rules=Rules(str(ROOT),ruleset='all')
def make(case):
    def test(self):
        lines=(ROOT/case['file']).read_text(encoding='utf-8').splitlines()
        original=lines[case['line']-1]
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),case['sha256'])
        block=parse_blocks(lines[case['start']-1:case['end']])
        self.assertTrue(block)
        self.assertEqual(block[0]['freq'],case['raw'],'fresh source parser')
        self.assertEqual(self.entities[(case['file'].removeprefix('input/'),case['start'])]['frequency'],case['raw'],'saved entity')
        for label,h in [('auto',self.auto[case['id']]['header']),('export',self.units[case['id']]['mech']['data']['header']),('runtime',self.rules.feat_effects(case['id'])[1])]:
            self.assertEqual(h['frequency']['raw'],case['raw'],label)
            self.assertEqual(h['frequency']['ap'],case['ap'],label)
            self.assertEqual(h['frequency']['action'],case['action'],label)
        if case['mode']=='bind':
            engine=Engine(self.rules,seed=1)
            actor=Combatant(self.rules,dict(name='AP source audit',kind='trainer',level=10,stats={s:20 for s in ['hp','atk','def','spa','spd','spe']},types=[],abilities=[],moves=[],feats=[case['id']]))
            before=(dict(actor.stats),dict(actor.stages),actor.evasion_mod,actor.accuracy_stage,actor.damage_reduction,list(actor.abilities),list(actor.moves))
            ITEMS.register_feats(engine,actor)
            after=(dict(actor.stats),dict(actor.stages),actor.evasion_mod,actor.accuracy_stage,actor.damage_reduction,list(actor.abilities),list(actor.moves))
            self.assertEqual(after,before,'binding cannot apply free permanent benefits at registration')
            effects,header=self.rules.feat_effects(case['id'])
            self.assertIsNone(AP.quote(header,effects)[0],'unimplemented binding must stay explicit')
    return test
for i,c in enumerate(CASES):
    setattr(FeatCostSourceTests,'test_source_'+str(i).zfill(3),make(c))
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='FEATCOST-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='FEATCOST-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='FEATCOST-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(FeatCostSourceTests))
    paths=[p for folder,pat in [('engine','*.py'),('data','*.json')] for p in (ROOT/folder).glob(pat)]
    paths += [Path(__file__),ROOT/'tools/ptk_structure.py',ROOT/'tools/mechanize_feats.py',ROOT/'output/entities/feat.json',ROOT/'output/ruleunits.jsonl']
    paths += [ROOT/p for p in sorted({c['file'] for c in CASES})]
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Standalone AP frequency/action source fidelity through parser/entity/mechanization/export/runtime. Not whole feat semantics.',results=r.rows,source_cases={'FEATCOST-test_source_'+str(i).zfill(3):c['id'] for i,c in enumerate(CASES)},input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/feat-cost-source-tests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if r.wasSuccessful() else 1)
