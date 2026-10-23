"""Independent shared rest/day and live-condition transition regressions."""
import hashlib,json,sys,unittest
from unittest.mock import patch
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import downtime as DT

class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def fixture(self,hp_stat=9,level=3,name='Boundary'):
        e=Engine(self.rules);c=Combatant(self.rules,dict(name=name,kind='pokemon',level=level,stats={'hp':hp_stat,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},types=['노말'],moves=[]))
        e.everyone=e.gm.everyone=[c];return e,c
    def test_extended_rest_preserves_same_day_rest_total(self):
        e,c=self.fixture(23,1);self.assertEqual(c.base_max_hp,80);c.hp=1
        DT.extended_rest(e,c,4)
        self.assertEqual((c.hp,c.spec['rested_minutes_today']),(41,240))
    def test_two_extended_rests_exhaust_daily_healing_allowance(self):
        e,c=self.fixture(23,1);c.hp=1;DT.extended_rest(e,c,4)
        c.hp=1;DT.extended_rest(e,c,4)
        self.assertEqual((c.hp,c.spec['rested_minutes_today']),(41,480))
        c.hp=1;DT.extended_rest(e,c,4)
        self.assertEqual((c.hp,c.spec['rested_minutes_today']),(1,720))
    def test_rest_fraction_uses_real_maximum_before_injury_cap(self):
        e,c=self.fixture(23,1);c.injuries=3;c.hp=1
        self.assertEqual((c.base_max_hp,c.max_hp),(80,56))
        self.assertEqual(DT.rest(e,c,30),5)
        self.assertEqual(c.hp,6)
    def test_rest_real_maximum_fraction_is_limited_by_recovery_ceiling(self):
        e,c=self.fixture(23,1);c.injuries=3;c.hp=54
        self.assertEqual(DT.rest(e,c,30),2)
        self.assertEqual(c.hp,56)
    def test_heavy_injuries_still_prevent_natural_hp_recovery(self):
        e,c=self.fixture(23,1);c.injuries=5;c.hp=1
        self.assertEqual(DT.rest(e,c,30),0)
        self.assertEqual(c.hp,1)
    def test_only_new_day_restores_daily_healing_allowance(self):
        e,c=self.fixture(23,1);c.hp=1;c.spec['rested_minutes_today']=480
        self.assertEqual(DT.rest(e,c,30),0)
        DT.new_day(c)
        self.assertEqual(DT.rest(e,c,30),5)
        self.assertEqual(c.spec['rested_minutes_today'],30)
    def test_extended_rest_still_restores_drained_ap(self):
        e,c=self.fixture();c.spec['ap_removed']=2
        DT.extended_rest(e,c,4)
        self.assertEqual(c.spec['ap_removed'],0)
        self.assertEqual(c.spec['rested_minutes_today'],240)
    def test_faint_cleanup_cancels_later_poison_burn_snapshot(self):
        e,c=self.fixture();c.hp=3;c.took_standard=True
        e.apply_status(c,'독');e.apply_status(c,'화상');e.end_of_turn(c)
        self.assertEqual(c.hp,-1)  # First4HP tick faints; second4HP tick is no longer applicable.
        self.assertTrue(c.fainted);self.assertNotIn('독',c.conditions);self.assertNotIn('화상',c.conditions)
        self.assertEqual((c.stages['spd'],c.stages['def']),(0,0))
    def test_alive_actor_still_receives_both_applicable_ticks(self):
        e,c=self.fixture();c.hp=20;c.took_standard=True
        e.apply_status(c,'독');e.apply_status(c,'화상');e.end_of_turn(c)
        self.assertEqual(c.hp,12);self.assertTrue({'독','화상'}<=c.conditions)
    def test_cured_condition_cancels_remaining_effects_in_same_snapshot(self):
        e,c=self.fixture();c.hp=3;c.took_standard=True;e.apply_status(c,'독')
        original=e.r.condition_effects
        def effects(name):
            result=original(name)
            if name=='독':return result+[{'type':'save','timing':'end_of_turn','dc':10,'on_success':'cure'}]
            return result
        with patch.object(e.r,'condition_effects',side_effect=effects),patch.object(e,'d20',side_effect=AssertionError('Cured status must not roll another save')):
            e.end_of_turn(c)
        self.assertEqual(c.hp,-1)
    def test_parallel_rest_advances_one_interval_for_distinct_actors(self):
        e,a=self.fixture(23,1,'A');b=Combatant(e.r,dict(a.spec,name='B',id='boundary:distinct-b'));a.hp=b.hp=1;e.everyone=e.gm.everyone=[a,b]
        with patch.object(e,'advance_time',wraps=e.advance_time) as clock:
            result=DT.rest_many(e,[a,b],30)
        self.assertEqual(clock.call_count,1);self.assertEqual(clock.call_args.args[0],1800)
        self.assertEqual(set(map(id,clock.call_args.args[1])),{id(a),id(b)})
        self.assertEqual((a.hp,b.hp),(6,6))
        self.assertEqual((a.spec['rested_minutes_today'],b.spec['rested_minutes_today']),(30,30))
    def test_parallel_duplicate_actor_not_double_credited(self):
        e,a=self.fixture(23,1);a.hp=1
        with patch.object(e,'advance_time',wraps=e.advance_time) as clock:DT.rest_many(e,[a,a],30)
        self.assertEqual(clock.call_count,1);self.assertEqual(a.hp,6);self.assertEqual(a.spec['rested_minutes_today'],30)
    def test_separate_rest_calls_are_sequential_intervals(self):
        e,a=self.fixture(23,1,'A');b=Combatant(e.r,dict(a.spec,name='B',id='boundary:distinct-b'));e.everyone=e.gm.everyone=[a,b]
        with patch.object(e,'advance_time',wraps=e.advance_time) as clock:
            DT.rest(e,a,30);DT.rest(e,b,30)
        self.assertEqual(clock.call_count,2);self.assertEqual(sum(call.args[0] for call in clock.call_args_list),3600)
    def test_invalid_parallel_duration_has_no_mutation(self):
        for minutes in [-1,True,1.5]:
            e,a=self.fixture();before=dict(a.spec)
            with patch.object(e,'advance_time',wraps=e.advance_time) as clock:
                with self.assertRaises(ValueError):DT.rest_many(e,[a],minutes)
            self.assertEqual(clock.call_count,0);self.assertEqual(a.spec,before)
    def test_empty_rest_group_does_not_advance_time(self):
        e,a=self.fixture()
        with patch.object(e,'advance_time',wraps=e.advance_time) as clock:self.assertEqual(DT.rest_many(e,[],30),[])
        self.assertEqual(clock.call_count,0)

class Result(unittest.TextTestResult):
    def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
    def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='REST-STATUS-'+t._testMethodName,status='pass'))
    def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='REST-STATUS-'+t._testMethodName,status='fail'))
    def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='REST-STATUS-'+t._testMethodName,status='error'))
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=1,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests))
    paths=list((ROOT/'engine').glob('*.py'))+list((ROOT/'data').glob('*.json'))+[Path(__file__),ROOT/'input/ch07-combat.md']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Shared daily rest allowance, concurrent rest interval accounting and live affliction cleanup; not full rule certification.',whole_rule_certified=False,tests_run=result.testsRun,results=result.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)})
    (ROOT/'output/rest-and-status-boundary-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
