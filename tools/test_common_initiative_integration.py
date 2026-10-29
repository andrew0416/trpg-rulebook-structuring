"""Initiative-only production dispatcher contracts, with explicit GM policy."""
import hashlib, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant,scenario
import encounter

class InitiativeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def policy_path(self, folder):
        p=Path(folder)/'explicit-initiative-policy.json'
        p.write_text(json.dumps({'rulings':[{'kind':'answer','key':'initiative_tie_order','scope':'campaign','reason':'검증 fixture가 선택한 운영정책; 룰북 확정 아님','answer':{'policy':'highest_d20','same_face':'reroll','max_rounds':100,'reason':'이 검증의 명시 동률 정책'}}]},ensure_ascii=False),encoding='utf-8')
        return str(p)
    def test_actual_scenario_missing_policy_stops_before_first_round(self):
        e=scenario(str(ROOT),5,ruleset='core')
        self.assertEqual((e.round_no,e.elapsed_seconds),(0,0))
        self.assertIsNone(e.round_start_seconds)
        self.assertEqual(e.unresolved_time_intervals,[])
        self.assertTrue(any('전투 보류' in line for line in e.log_lines))
        self.assertFalse(e.encounter_active)
    def test_actual_scenario_explicit_policy_can_advance(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            e=scenario(str(ROOT),5,ruleset='core',rulings_path=self.policy_path(folder))
        self.assertGreater(e.round_no,0)
        self.assertTrue(any(row['kind']=='initiative_adjudication' for row in e.rulings.log))
    def test_actual_encounter_missing_policy_preserves_both_living_sides(self):
        # Lakeside explicitly selects Chlorophyll [Playtest]; core must not admit it.
        e,party,wild=encounter.run_encounter(str(ROOT),'data/encounters/lakeside.json',seed=5,ruleset='all',write=False)
        self.assertEqual((e.round_no,e.elapsed_seconds),(0,0))
        self.assertTrue(any(not c.fainted for c in party));self.assertTrue(any(not c.fainted for c in wild))
        self.assertIsNone(e.round_start_seconds);self.assertEqual(e.unresolved_time_intervals,[])
        self.assertTrue(any('전투 보류' in line for line in e.log_lines))
    def test_actual_encounter_explicit_policy_can_advance(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            e,party,wild=encounter.run_encounter(str(ROOT),'data/encounters/lakeside.json',seed=5,ruleset='all',rulings_path=self.policy_path(folder),write=False)
        self.assertGreater(e.round_no,0)
        self.assertTrue(any(row['kind']=='initiative_adjudication' for row in e.rulings.log))
    def test_lakeside_explicit_playtest_chlorophyll_stays_excluded_from_core(self):
        from ruleset import ExcludedRuleSelection
        declared=json.loads((ROOT/'data/encounters/lakeside.json').read_text(encoding='utf-8'))
        self.assertTrue(declared['wild'])
        self.assertTrue(all(row['abilities']==['엽록소 [Playtest]'] for row in declared['wild']))
        with self.assertRaisesRegex(ExcludedRuleSelection,'ability/엽록소-playtest'):
            encounter.load_encounter(str(ROOT),'data/encounters/lakeside.json',ruleset='core')
    def test_later_pending_round_does_not_end_encounter_or_add_time(self):
        from rulings import Rulings
        e=Engine(self.rules);e.rulings=Rulings()
        def actor(name,speed):return Combatant(self.rules,dict(name=name,kind='trainer',level=5,stats={'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':speed},types=['노말'],moves=[]))
        a,b=actor('a',20),actor('b',10);a.side='party';b.side='wild';a.stages['atk']=2;e.everyone=e.gm.everyone=[a,b]
        original=e.end_of_turn
        def finish(c):
            original(c)
            if c is b:a.stats['spe']=10
        e.end_of_turn=finish
        with patch.object(encounter,'load_encounter',return_value=(e,{'rounds':3,'name':'pending-next'},[a],[b])),patch.object(encounter,'describe',side_effect=lambda s:s['name']),patch.object(encounter,'choose_action',return_value=(None,None,None)):
            encounter.run_encounter(str(ROOT),'unused.json',write=False)
        self.assertEqual((e.round_no,e.elapsed_seconds),(1,10));self.assertTrue(e.encounter_active)
        self.assertEqual(a.stages['atk'],2);self.assertIsNone(e.round_start_seconds);self.assertEqual(e.unresolved_time_intervals,[])

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'INIT-INTEGRATION-'+t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':'INIT-INTEGRATION-'+t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':'INIT-INTEGRATION-'+t._testMethodName,'status':'error'})
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(InitiativeIntegrationTests))
    files=['engine/initiative.py','engine/engine.py','engine/encounter.py','engine/rulings.py','tools/test_common_initiative_integration.py','data/verification/common-initiative-semantics.json']
    report={'scope':'Production callers propagate pending before round start; explicit fixture GM policy allows ordinary progress. Not complete initiative semantics.','whole_semantic_complete':False,'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
    (ROOT/'output/common-initiative-integration-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');raise SystemExit(0 if result.wasSuccessful() else 1)
