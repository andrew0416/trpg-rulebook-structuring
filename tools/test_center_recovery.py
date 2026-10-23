"""Independent Pokemon Center duration, injury ledger and scope regressions."""
import copy,hashlib,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import downtime as DT
import effects_ext as EXT
import frequency as FREQ

class CenterRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def fixture(self,injuries=0,name='Center',kind='pokemon'):
        e=Engine(self.rules);c=Combatant(self.rules,dict(name=name,kind=kind,level=1,stats={'hp':23,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},types=['노말'],moves=[]))
        c.injuries=injuries;c.hp=1;e.everyone=e.gm.everyone=[c];return e,c
    def daily_move(self,e,c):
        # Saved moves.csv:532: a core daily move; only its usage ledger is exercised.
        mid='move/대폭발'
        self.assertEqual(e.r.selection.require_supported_version(mid),mid)
        self.assertEqual(FREQ.move_frequency(e,mid,c),('daily',1))
        return mid
    def test_duration_uses_all_initial_injuries_and_heavy_rate(self):
        # Expected minutes transcribed from ch07:754/756, not engine data constants.
        for injuries,minutes in [(0,60),(1,90),(4,180),(5,360),(8,540)]:
            with self.subTest(injuries=injuries):
                e,c=self.fixture(injuries);DT.pokemon_center(e,c)
                self.assertEqual(e.elapsed_seconds,minutes*60)
                self.assertEqual(c.injuries,max(0,injuries-3))
                self.assertEqual(c.hp,c.max_hp)
    def test_exhausted_legacy_ledger_still_pays_for_existing_injuries(self):
        e,c=self.fixture(2);c.spec['center_injuries_today']=3;DT.pokemon_center(e,c)
        self.assertEqual((e.elapsed_seconds,c.injuries,c.hp),(7200,2,64))
    def test_generic_injury_heal_counts_toward_center_limit(self):
        e,c=self.fixture(4);EXT.h_heal_injury(e,c,c,{'value':1},{'healing_source_kind':'feature'})
        self.assertEqual((c.injuries,c.spec.get('injuries_healed_today')),(3,1))
        DT.pokemon_center(e,c)
        self.assertEqual((c.injuries,c.spec.get('injuries_healed_today')),(1,3))
    def test_natural_injury_heal_counts_toward_center_limit(self):
        e,c=self.fixture(4);DT.extended_rest(e,c,24)
        self.assertEqual((c.injuries,c.spec.get('injuries_healed_today')),(3,1))
        DT.pokemon_center(e,c)
        self.assertEqual((c.injuries,c.spec.get('injuries_healed_today')),(1,3))
    def test_global_and_legacy_ledgers_use_max_not_sum_or_overwrite(self):
        for modern,legacy in [(2,1),(1,2),(2,2)]:
            with self.subTest(modern=modern,legacy=legacy):
                e,c=self.fixture(3);c.spec.update(injuries_healed_today=modern,center_injuries_today=legacy)
                DT.pokemon_center(e,c)
                self.assertEqual((c.injuries,c.spec.get('injuries_healed_today')),(2,3))
    def test_new_day_restores_injury_allowance(self):
        e,c=self.fixture(2);c.spec.update(injuries_healed_today=3,center_injuries_today=3)
        DT.new_day(c);DT.pokemon_center(e,c)
        self.assertEqual((c.injuries,c.spec.get('injuries_healed_today')),(0,2))
    def test_extended_rest_does_not_reset_or_exceed_injury_allowance(self):
        e,c=self.fixture(4);c.spec['injuries_healed_today']=3;DT.extended_rest(e,c,24)
        self.assertEqual(c.injuries,4);self.assertEqual(c.spec['injuries_healed_today'],3)
    def test_center_does_not_resurrect_dead_actor(self):
        e,c=self.fixture();c.hp=-160;e.check_fainted(c);self.assertTrue(c.dead)
        before=(c.hp,c.injuries,e.elapsed_seconds,copy.deepcopy(c.spec))
        DT.pokemon_center(e,c)
        self.assertTrue(c.dead);self.assertEqual((c.hp,c.injuries,e.elapsed_seconds,c.spec),before)
    def test_living_fainted_actor_recovers_after_treatment_interval(self):
        e,c=self.fixture();c.hp=-1;e.check_fainted(c);DT.pokemon_center(e,c)
        self.assertEqual(e.elapsed_seconds,3600);self.assertEqual(c.hp,80);self.assertFalse(c.fainted)
    def test_other_actor_recovery_clock_advances_with_center_time(self):
        e,c=self.fixture();_,other=self.fixture(name='Waiting')
        self.assertNotEqual(c.entity_id,other.entity_id)
        e.everyone=e.gm.everyone=[c,other];other.hp=-1;e.check_fainted(other);e.heal(other,2,source_kind='ordinary_item')
        self.assertEqual(other.faint_recovery_seconds,600)
        DT.pokemon_center(e,c)
        self.assertEqual(e.elapsed_seconds,3600);self.assertFalse(other.fainted);self.assertEqual(other.hp,1)
    def test_advance_refusal_does_not_apply_treatment(self):
        e,c=self.fixture(4);e.apply_status(c,'독');mid=self.daily_move(e,c);FREQ.consume_move(e,c,mid)
        e.start_round([c]);before=(c.hp,c.injuries,set(c.conditions),dict(c.move_uses),copy.deepcopy(c.spec),e.elapsed_seconds)
        with self.assertRaises(ValueError):DT.pokemon_center(e,c)
        self.assertEqual((c.hp,c.injuries,c.conditions,c.move_uses,c.spec,e.elapsed_seconds),before)
    def test_center_restores_daily_moves_used_today(self):
        e,c=self.fixture();mid=self.daily_move(e,c);FREQ.consume_move(e,c,mid)
        self.assertEqual(c.move_uses[mid],1);day=FREQ.state(c)['day'];DT.pokemon_center(e,c)
        self.assertEqual(c.move_uses.get(mid,0),0);self.assertEqual(FREQ.state(c)['day'],day)
        # Scene-specific repeat restrictions are separately scoped; no assertion
        # of same-scene usability is made by this restoration test.
    def test_center_does_not_reset_scene_ap_or_daily_features(self):
        e,c=self.fixture(kind='trainer');c.spec.update(ap_spent=1,ap_bound={'sustain':1},ap_removed=1)
        FREQ.consume_activation(c,'audit/shared-daily-feature','하루');st=FREQ.state(c)
        before=(st['scene'],st['day'],copy.deepcopy(st['activations']),c.spec['ap_spent'],copy.deepcopy(c.spec['ap_bound']),c.spec['ap_removed'])
        DT.pokemon_center(e,c);st=FREQ.state(c)
        self.assertEqual((st['scene'],st['day'],st['activations'],c.spec['ap_spent'],c.spec['ap_bound'],c.spec['ap_removed']),before)
    def test_affliction_cure_preserves_other_conditions_and_temporary_hp(self):
        e,c=self.fixture();e.apply_status(c,'독');e.apply_status(c,'혼란')
        c.conditions.update(['실명','넘어짐','구속','임시 체력']);c.temp_hp=12
        DT.pokemon_center(e,c)
        self.assertFalse({'독','혼란'}&c.conditions)
        self.assertTrue({'실명','넘어짐','구속','임시 체력'}<=c.conditions)
        self.assertEqual(c.temp_hp,12);self.assertEqual(c.stages['spd'],0)

class Result(unittest.TextTestResult):
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
    def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='CENTER-'+t._testMethodName,status='pass'))
    def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='CENTER-'+t._testMethodName,status='fail'))
    def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='CENTER-'+t._testMethodName,status='error'))
    def addSubTest(self,t,subtest,err):
        super().addSubTest(t,subtest,err)
        if err:self.rows.append(dict(id='CENTER-'+t._testMethodName+':'+str(subtest),status='fail'))

def anchor(start,end):
    file='input/ch07-combat.md';lines=(ROOT/file).read_text(encoding='utf-8').splitlines();excerpt='\n'.join(lines[start-1:end])
    return dict(file=file,start=start,end=end,excerpt=excerpt,excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest())
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=1,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(CenterRecoveryTests))
    paths=list((ROOT/'engine').glob('*.py'))+list((ROOT/'data').glob('*.json'))+[Path(__file__),ROOT/'input/ch07-combat.md',ROOT/'input/db/moves.csv']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Common center treatment timing, injury cap, life recovery and scoped resources; incomplete total source coverage.',whole_rule_certified=False,tests_run=result.testsRun,results=result.rows,source_anchors=[anchor(700,704),anchor(629,635),anchor(748,758)],input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)})
    (ROOT/'output/center-recovery-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
