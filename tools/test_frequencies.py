"""Independent source-frequency regressions. Test payloads isolate frequency from move effects."""
import json,hashlib,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from synthetic_rule_fixture import register_synthetic
from frequency_source_connection_fixture import (source_fixture, source_case_contract,
    connected_source_suite, prepare_source_frequency_cases, verify_source_connection_inputs)
import items as ITEMS
import effects as FX
import effects_ext as EXT
import downtime as DT
import frequency as FREQ
from encounter import usable_moves

class FrequencyTests(unittest.TestCase):
    @classmethod
    def prepare_chained_cases(cls, cases):
        return prepare_source_frequency_cases(cls, cases, CASES, root=ROOT)

    @classmethod
    def setUpClass(cls):
        review=json.loads((ROOT/'data/frequency-source-review.json').read_text(encoding='utf-8'))
        assert hashlib.sha256((ROOT/review['file']).read_bytes()).hexdigest()==review['sha256'], 'reviewed original PDF changed'
        cls.rules=Rules(str(ROOT),ruleset='all')
        # Shared frequency fixtures register their synthetic ID once per Rules instance.
        register_synthetic(cls.rules,'audit/frequency',name='빈도 검사')
        cls.source=json.loads((ROOT/'output/source-audit/2026-10-10/xlsx-cells.json').read_text(encoding='utf-8'))
    def fixture(self,kind='scene',uses=2):
        r=self.rules;mid='audit/frequency'
        raw='턴1회' if kind=='every_other_turn' else ('장면' if kind=='scene' else '하루')+f' x{uses}'
        r.moves[mid]=dict(id=mid,name='빈도 검사',type='노말',frequency=raw,range='근접, 대상 1',ac=None,damage_base=None,**{'class':'변화'},effect='',mech_auto={})
        r.moves_mech[mid]=dict(name='빈도 검사',coverage='full',header=dict(frequency=dict(kind=kind,uses=uses)),effects=[dict(type='injury',value=1,target='target')])
        e=Engine(r,seed=17)
        def actor(name):return Combatant(r,dict(name=name,kind='trainer',level=10,stats={s:30 for s in ['hp','atk','def','spa','spd','spe']},abilities=[],types=[],moves=[mid]))
        a,b=actor('actor'),actor('target')
        e.everyone=e.gm.everyone=[a,b]
        return e,a,b,mid
    def cast(self,e,a,b,mid):return e.use_move(a,b,mid,free_action=True)
    def turn(self,e,a):e.start_of_turn(a)
    def combat_turn(self,e,a):
        if getattr(e,'_active_turn_actor',None) is not None:e.end_of_turn(e._active_turn_actor)
        if e.round_start_seconds is not None:e.end_round()
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
    def auto(self,a,frequency):
        a.ability_triggers=[dict(name='감사 빈도',spec={'event':'audit'},frequency=frequency,effects=[dict(type='injury',value=1,target='target')])]
    def fire(self,e,a,b):FX.fire_event(e,a,{'event':'audit'},b)
    def test_scene_move_cannot_repeat_same_turn_even_when_free(self):
        e,a,b,m=self.fixture();self.cast(e,a,b,m);self.cast(e,a,b,m)
        self.assertEqual(b.injuries,1);self.assertEqual(a.move_uses[m],1)
    def test_scene_move_cap_and_no_action_cost_on_rejection(self):
        e,a,b,m=self.fixture()
        for _ in range(2):self.combat_turn(e,a);self.combat_turn(e,a);self.cast(e,a,b,m)
        self.combat_turn(e,a);before=dict(a.budget);e.use_move(a,b,m)
        self.assertEqual(b.injuries,2);self.assertEqual(a.budget,before)
    def test_scene_end_refreshes_scene_move(self):
        e,a,b,m=self.fixture(uses=1);self.cast(e,a,b,m);e.end_scene([a,b]);self.cast(e,a,b,m)
        self.assertEqual(b.injuries,2);self.assertEqual(a.move_uses[m],1)
    def test_daily_move_once_per_scene_across_turns(self):
        e,a,b,m=self.fixture('daily',3);self.cast(e,a,b,m);self.turn(e,a);self.cast(e,a,b,m)
        self.assertEqual(b.injuries,1);self.assertNotIn(m,usable_moves(e,a))
    def test_daily_move_cap_persists_across_scene_end(self):
        e,a,b,m=self.fixture('daily',2)
        for _ in range(3):self.cast(e,a,b,m);e.end_scene([a,b])
        self.assertEqual(b.injuries,2);self.assertEqual(a.move_uses[m],2)
    def test_new_day_alone_does_not_restore_daily_move(self):
        e,a,b,m=self.fixture('daily',1);self.cast(e,a,b,m);DT.new_day(a);e.end_scene([a,b]);self.cast(e,a,b,m)
        self.assertEqual(b.injuries,1)
    def test_same_day_extended_rest_does_not_restore_daily_move(self):
        e,a,b,m=self.fixture('daily',1);self.cast(e,a,b,m);DT.extended_rest(e,a,4);e.end_scene([a,b]);self.cast(e,a,b,m)
        self.assertEqual(b.injuries,1);self.assertEqual(a.move_uses[m],1)
    def test_short_rest_next_day_does_not_restore_daily_move(self):
        e,a,b,m=self.fixture('daily',1);self.cast(e,a,b,m);DT.new_day(a);DT.extended_rest(e,a,3.99);e.end_scene([a,b]);self.cast(e,a,b,m)
        self.assertEqual(b.injuries,1)
    def test_extended_rest_next_day_restores_daily_move(self):
        e,a,b,m=self.fixture('daily',1);self.cast(e,a,b,m);DT.new_day(a);DT.extended_rest(e,a,4);e.end_scene([a,b]);self.cast(e,a,b,m)
        self.assertEqual(b.injuries,2);self.assertEqual(a.move_uses[m],1)
    def test_center_restores_daily_move_even_same_day(self):
        e,a,b,m=self.fixture('daily',1);self.cast(e,a,b,m);DT.pokemon_center(e,a);e.end_scene([a,b]);self.cast(e,a,b,m)
        self.assertEqual(b.injuries,2);self.assertEqual(a.move_uses[m],1)
    def test_daily_move_usage_persists_in_saved_spec(self):
        e,a,b,m=self.fixture('daily',1);self.cast(e,a,b,m)
        restored=Combatant(self.rules,json.loads(json.dumps(a.spec)))
        # A sheet restoration creates the same identity in a new world. Keeping
        # both live actors in the original roster is not a legal replacement.
        with self.assertRaisesRegex(ValueError,'distinct actors share identity'):
            self.cast(e,restored,b,m)
        fresh=Engine(self.rules,seed=17)
        fresh.everyone=fresh.gm.everyone=[restored,b]
        self.cast(fresh,restored,b,m)
        self.assertEqual(restored.move_uses[m],1)
        self.assertEqual(b.injuries,1)
    def test_auto_daily_ability_not_refreshed_by_scene_end(self):
        e,a,b,m=self.fixture();self.auto(a,'하루 x1')
        self.fire(e,a,b);e.end_scene([a,b]);self.fire(e,a,b)
        self.assertEqual(b.injuries,1)
    def test_auto_daily_ability_refreshed_by_explicit_new_day(self):
        e,a,b,m=self.fixture();self.auto(a,'하루 x1')
        self.fire(e,a,b);DT.new_day(a);self.fire(e,a,b)
        self.assertEqual(b.injuries,2)
    def test_auto_scene_ability_cap_and_reset(self):
        e,a,b,m=self.fixture();self.auto(a,'장면 x2')
        for _ in range(3):self.fire(e,a,b)
        self.assertEqual(b.injuries,2)
        e.end_scene([a,b]);self.fire(e,a,b);self.assertEqual(b.injuries,3)
    # These synthetic fixtures test frequency/rewind; their independent action cost is explicit Free.
    def test_manual_scene_feat_cap_and_reset(self):
        e,a,b,m=self.fixture()
        a.registry.append(dict(type='feat_manual',name='검사 재주',frequency=dict(kind='scene',uses=2,raw='장면 x2 - 자유 행동',action='free'),effects=[dict(type='injury',value=1,target='target')]))
        for _ in range(3):ITEMS.manual_feat(e,a,'검사 재주',b)
        self.assertEqual(b.injuries,2)
        e.end_scene([a,b]);ITEMS.manual_feat(e,a,'검사 재주',b);self.assertEqual(b.injuries,3)
    def test_snapshot_restores_manual_daily_resource(self):
        e,a,b,m=self.fixture()
        a.registry.append(dict(type='feat_manual',name='검사 재주',frequency=dict(kind='daily',uses=1,raw='하루 x1 - 자유 행동',action='free'),effects=[dict(type='injury',value=1,target='target')]))
        e.gm.snapshot('before')
        ITEMS.manual_feat(e,a,'검사 재주',b);e.gm.restore('before')
        self.assertEqual(ITEMS.manual_feat(e,a,'검사 재주',b),(1,0));self.assertEqual(b.injuries,1)
    def test_manual_daily_cap_resets_only_its_daily_pool(self):
        e,a,b,m=self.fixture()
        for name,kind,uses in [('daily-contract','daily',1),('scene-contract','scene',2)]:
            a.registry.append(dict(type='feat_manual',name=name,
                frequency=dict(kind=kind,uses=uses,raw=kind+' - 자유 행동',action='free'),
                effects=[dict(type='injury',value=1,target='target')]))
        self.assertEqual(ITEMS.manual_feat(e,a,'daily-contract',b),(1,0))
        self.assertEqual(ITEMS.manual_feat(e,a,'scene-contract',b),(1,0))
        self.assertEqual(ITEMS.manual_feat(e,a,'scene-contract',b),(1,0))
        e.end_scene([a,b])
        self.assertEqual(ITEMS.manual_feat(e,a,'daily-contract',b),(0,1))
        self.assertEqual(ITEMS.manual_feat(e,a,'scene-contract',b),(1,0))
        DT.new_day(a)
        self.assertEqual(ITEMS.manual_feat(e,a,'daily-contract',b),(1,0))
        self.assertEqual(ITEMS.manual_feat(e,a,'daily-contract',b),(0,1))
        self.assertEqual(b.injuries,5)
    def test_exhausted_aoe_does_not_hit_secondary_targets(self):
        e,a,b,m=self.fixture('daily',1);self.cast(e,a,b,m)
        c=Combatant(self.rules,dict(a.spec,name='second'))
        e.targets_in_range=lambda *args:[b,c]
        e.use_move_on(a,b,m,[a,b,c])
        self.assertEqual((b.injuries,c.injuries),(1,0))
    def test_explicit_repeat_bypasses_frequency_without_consuming_extra_use(self):
        e,a,b,m=self.fixture('daily',1);self.cast(e,a,b,m);e.use_move(a,b,m,count_use=False)
        self.assertEqual(b.injuries,2);self.assertEqual(a.move_uses[m],1)
    def test_frequency_restore_resets_usage_and_allows_use(self):
        e,a,b,m=self.fixture('daily',1);self.cast(e,a,b,m)
        EXT.h_full_restore(e,a,a,dict(restore_frequencies=True,target='self'),{})
        self.cast(e,a,b,m);self.assertEqual(b.injuries,2)

    def test_scene_move_cannot_repeat_consecutive_turns(self):
        e,a,b,m=self.fixture();self.combat_turn(e,a);self.cast(e,a,b,m)
        self.combat_turn(e,a);self.cast(e,a,b,m);self.assertEqual(b.injuries,1)
        self.combat_turn(e,a);self.cast(e,a,b,m);self.assertEqual(b.injuries,2)
    def test_eot_cannot_repeat_same_or_next_turn(self):
        e,a,b,m=self.fixture('every_other_turn');self.turn(e,a);self.cast(e,a,b,m)
        self.cast(e,a,b,m);self.assertEqual(b.injuries,1)
        self.turn(e,a);self.cast(e,a,b,m);self.assertEqual(b.injuries,1)
    def test_eot_waiting_without_other_move_allows_after_gap(self):
        e,a,b,m=self.fixture('every_other_turn');self.turn(e,a);self.cast(e,a,b,m)
        self.turn(e,a);self.turn(e,a);e.advance_time(10,[a,b]);self.cast(e,a,b,m);self.assertEqual(b.injuries,2)
    def test_eot_other_action_does_not_bypass_interval(self):
        e,a,b,m=self.fixture('every_other_turn');self.cast(e,a,b,m)
        a.last_move='struggle';self.cast(e,a,b,m);self.assertEqual(b.injuries,1)
    def test_eot_new_scene_clears_old_interval(self):
        e,a,b,m=self.fixture('every_other_turn');self.cast(e,a,b,m)
        from copy import deepcopy
        e.end_scene([a,b])
        # A narrative scene boundary does not advance the outside world clock.
        snapshot=lambda:(deepcopy(a.spec),deepcopy(b.spec),deepcopy(a.stages),deepcopy(b.stages),
                         hasattr(a,'budget'),deepcopy(getattr(a,'budget',None)),
                         hasattr(b,'budget'),deepcopy(getattr(b,'budget',None)),b.injuries,e.rng.getstate(),e.elapsed_seconds)
        before=snapshot();self.cast(e,a,b,m);self.assertEqual(snapshot(),before)
        e.advance_time(9,[a,b])
        before=snapshot();self.cast(e,a,b,m);self.assertEqual(snapshot(),before)
        e.advance_time(1,[a,b]);self.cast(e,a,b,m);self.assertEqual(b.injuries,2)


CASES=json.loads((ROOT/'data/source-frequency-cases.json').read_text(encoding='utf-8'))['cases']
def source_case(case):
    def test(self):
        source=case['source'];cells=self.source[source['sheet']]['cells']
        self.assertEqual(cells[source['cell']].strip(),source['raw'])
        variants=case.get('variants') or [dict(types=[],expected=case['expected'])]
        for variant in variants:
            e,a,b,_=source_fixture(self,case,variant);a.types=variant['types'];mid=case['id']
            expected=variant['expected'];kind,cap=expected['kind'],expected['uses']
            self.assertEqual(FREQ.move_frequency(e,mid,a),(kind,cap),mid)
            self.assertTrue(FREQ.move_allowed(e,a,mid)[0])
            if kind=='at_will':
                for _ in range(4):
                    FREQ.consume_move(e,a,mid);self.assertTrue(FREQ.move_allowed(e,a,mid)[0])
            elif kind in ('scene','every_other_turn'):
                for _ in range(cap if kind=='scene' else 2):
                    self.assertTrue(FREQ.move_allowed(e,a,mid)[0])
                    FREQ.consume_move(e,a,mid);self.assertFalse(FREQ.move_allowed(e,a,mid)[0])
                    FREQ.start_turn(a);self.assertFalse(FREQ.move_allowed(e,a,mid)[0])
                    FREQ.start_turn(a)
                if kind=='scene':self.assertFalse(FREQ.move_allowed(e,a,mid)[0])
                FREQ.end_scene(e,a);self.assertTrue(FREQ.move_allowed(e,a,mid)[0])
            elif kind=='daily':
                for _ in range(cap):
                    self.assertTrue(FREQ.move_allowed(e,a,mid)[0]);FREQ.consume_move(e,a,mid)
                    FREQ.start_turn(a);self.assertFalse(FREQ.move_allowed(e,a,mid)[0]);FREQ.end_scene(e,a)
                self.assertFalse(FREQ.move_allowed(e,a,mid)[0])
                FREQ.new_day(a);self.assertFalse(FREQ.move_allowed(e,a,mid)[0])
                FREQ.restore_daily_moves(e,a);self.assertTrue(FREQ.move_allowed(e,a,mid)[0])
    return source_case_contract(case,test)
for index,case in enumerate(CASES):
    setattr(FrequencyTests,f'test_source_move_{index:04d}',source_case(case))

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='FREQ-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='FREQ-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='FREQ-'+t._testMethodName,status='error'))
    verify_source_connection_inputs(ROOT)
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(connected_source_suite(unittest.defaultTestLoader.loadTestsFromTestCase(FrequencyTests),CASES))
    paths=[x for folder,glob in [('engine','*.py'),('data','*.json')] for x in (ROOT/folder).glob(glob)]
    paths += [ROOT/'tools/frequency_source_connection_fixture.py',ROOT/'tools/frequency_source_connection_contract.json',ROOT/'tools/synthetic_rule_fixture.py',Path(__file__),ROOT/'output/source-audit/2026-10-10/ptu-core-1.05.pdf',ROOT/'output/source-audit/2026-10-10/xlsx-cells.json']+[ROOT/'input'/x for x in ['ch03-skills-edges-feats.md','ch07-combat.md','ch10-index-reference.md']]
    report=dict(scope='24 integration/boundary checks plus 1004 source-linked frequency-clause checks. Not complete move certification.',source_cases={f'FREQ-test_source_move_{i:04d}':c['id'] for i,c in enumerate(CASES)},generated_at=datetime.now(timezone.utc).isoformat(),results=result.rows,input_hashes={x.relative_to(ROOT).as_posix():hashlib.sha256(x.read_bytes()).hexdigest() for x in paths})
    (ROOT/'output/frequency-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
