"""Independent recovery evidence guards and shared injury-ledger composition."""
import copy,hashlib,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import injury_recovery as INJURY
import effects_ext as EXT
import downtime as DT
from audit_recovery_semantics import validate

class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def fixture(self):
        e=Engine(self.rules);c=Combatant(self.rules,dict(name='Recovery',level=1,kind='pokemon',stats={'hp':23,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},types=['노말'],moves=[]))
        e.everyone=e.gm.everyone=[c];return e,c
    def test_source_and_test_links_integrity(self):
        s=json.loads((ROOT/'data/verification/recovery-semantics.json').read_text(encoding='utf-8'))
        self.assertEqual(validate(s,ROOT),[])
    def test_false_certification_and_changed_excerpt_rejected(self):
        s=json.loads((ROOT/'data/verification/recovery-semantics.json').read_text(encoding='utf-8'))
        bad=copy.deepcopy(s);bad['certification']['whole_rule_certified']=True
        self.assertIn('unsupported_recovery_certification',validate(bad,ROOT))
        bad=copy.deepcopy(s);bad['clauses'][0]['sources'][0]['excerpt']='invented'
        self.assertIn('stale_recovery_source:RECOVERY-01',validate(bad,ROOT))
    def test_nonexistent_test_and_empty_remaining_rejected(self):
        s=json.loads((ROOT/'data/verification/recovery-semantics.json').read_text(encoding='utf-8'))
        s['runtime_contract']['partial_tests'][0]['method']='test_does_not_exist';s['runtime_contract']['remaining']=[]
        errors=validate(s,ROOT)
        self.assertIn('unknown_recovery_test:test_does_not_exist',errors)
        self.assertIn('unsupported_recovery_runtime_closure',errors)
    def test_generic_recovery_after_center_cannot_exceed_shared_allowance(self):
        e,c=self.fixture();c.injuries=5;DT.pokemon_center(e,c)
        self.assertEqual(c.injuries,2)
        EXT.h_heal_injury(e,c,c,{'value':2},{})
        self.assertEqual(c.injuries,2);self.assertEqual(c.spec['injuries_healed_today'],3)
    def test_full_restore_uses_same_ledger_and_hp_per_injury_requires_actual_healing(self):
        e,c=self.fixture();c.injuries=5
        EXT.h_full_restore(e,c,c,{'heal_injuries':2},{})
        self.assertEqual(c.injuries,3);self.assertEqual(c.spec['injuries_healed_today'],2)
        c.hp=1;EXT.h_heal_injury(e,c,c,{'value':3,'heal_per_injury':'tick'},{'healing_source_kind':'move'})
        self.assertEqual(c.injuries,2);self.assertEqual(c.hp,9)
        EXT.h_heal_injury(e,c,c,{'value':1,'heal_per_injury':'tick'},{'healing_source_kind':'move'})
        self.assertEqual(c.hp,9)
    def test_snapshot_rewinds_daily_allowance_and_healing_history(self):
        e,c=self.fixture();c.injuries=5;INJURY.heal(e,c,1,source='test_ordinary')
        e.gm.snapshot('recover');INJURY.heal(e,c,2,source='test_ordinary');DT.new_day(c)
        e.gm.restore('recover')
        self.assertEqual((c.injuries,c.spec['injuries_healed_today']),(4,1))
        self.assertEqual(len(c.spec['injury_healing_history']),1)
        self.assertEqual(INJURY.heal(e,c,4,source='test_ordinary'),2)
    def test_rejected_count_does_not_consume_allowance(self):
        e,c=self.fixture();c.injuries=2;before=copy.deepcopy(c.spec)
        for n in (-1,True,1.5):
            with self.assertRaises(ValueError):INJURY.heal(e,c,n,source='test_ordinary')
        self.assertEqual(c.injuries,2);self.assertEqual(c.spec,before)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='RECOVERY-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='RECOVERY-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='RECOVERY-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryTests))
    paths=['tools/test_recovery_semantics.py','tools/audit_recovery_semantics.py','data/verification/recovery-semantics.json','engine/injury_recovery.py','engine/downtime.py','engine/effects_ext.py','engine/engine.py','engine/gm_state.py','data/core-rules.json','input/ch07-combat.md']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),whole_rule_certified=False,results=r.rows,input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/recovery-semantics-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if r.wasSuccessful() else 1)
