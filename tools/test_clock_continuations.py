"""Actual timed dispatch, committed prefixes and exact child replies."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'data/examples').is_dir():ROOT=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
import effects as FX,clock_invocations as CLOCK,combat_timing as LIFE,world_entities as W
from state_codec import dump_engine,load_engine


class ClockContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        self.e=Engine(self.rules,seed=817)
        self.a=Combatant(self.rules,build_trainer(self.rules,'clock',10,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'명령':3},extra={'items':{},'edges':[]}))
        self.e.gm.add_combatant(self.a,pos=(0,0),side='party',reason='actual clock participant')
    def install(self,*,seconds=5,times=1,conditional=True,stat='atk'):
        effect={'type':'stage_change','stat':stat,'delta':1,'repeat':{'seconds':seconds,'times':times}}
        if conditional:effect['if']='target was asleep'
        result=FX.run_effects(self.e,self.a,self.a,[effect],{'hit':True,'target_was_asleep':True},'external/timed-stage')
        self.assertEqual(result,(1,0))
        return LIFE.records(self.a)[-1]
    def advance(self,identity='clock-test',seconds=12):
        return self.e.advance_time(seconds,[self.a],request_id=identity,source='external/clock',resumable=True)
    def answer(self,clock,*,truth=True,reason='GM observed sleep immediately before this occurrence'):
        receipt=clock['children'][-1]['record']['receipt']
        return self.e.resolve_effect_condition(self.a,receipt,target_was_asleep=truth,reason=reason)
    def test_prefix_wait_resume_executes_actual_effect_once(self):
        native=self.install();state=self.e.rng.getstate()
        clock=self.advance()
        self.assertEqual((clock['status'],self.e.elapsed_seconds,self.a.stages['atk']),('waiting',5,0))
        self.assertIs(clock['children'][0]['record'],native['lifetime_deliveries'][0])
        self.assertEqual(self.advance()['status'],'waiting');self.assertEqual(self.e.rng.getstate(),state)
        self.answer(clock);self.assertEqual(self.a.stages['atk'],1)
        final=self.advance();self.assertEqual((final['status'],self.e.elapsed_seconds),('complete',12))
        self.answer(clock);self.advance();self.assertEqual((self.a.stages['atk'],self.e.elapsed_seconds),(1,12))
        self.assertIs(final['children'][0]['record'],self.a.custom_conditions['effect_lifetime_history'][0]['deliveries'][0])
    def test_false_fact_completes_actual_no_effect_result(self):
        self.install();clock=self.advance();self.answer(clock,truth=False)
        self.assertEqual(self.advance()['status'],'complete');self.assertEqual(self.a.stages['atk'],0)
        actual=self.e._effect_dispatch_receipts[clock['children'][0]['record']['receipt']]
        self.assertEqual(actual['result'],{'condition':False,'applied':False})
    def test_wrong_owner_receipt_and_changed_interval_are_inert(self):
        self.install();clock=self.advance();before=dump_engine(self.e)
        for call in (lambda:self.advance(seconds=13),lambda:self.e.advance_time(1,[self.a]),
                     lambda:self.e.resolve_effect_condition(self.a,object(),target_was_asleep=True,reason='wrong original')):
            with self.assertRaises(ValueError):call()
            self.assertEqual(before,dump_engine(self.e))
        self.answer(clock)
        with self.assertRaises(ValueError):self.answer(clock,truth=False)
    def test_save_restore_keeps_pending_original_and_completed_replay(self):
        self.install();clock=self.advance();saved=json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False))
        self.e=load_engine(self.rules,saved);self.a=W.actor_index(self.e)[self.a.entity_id]
        clock=self.e._clock_invocations['clock-test'];self.answer(clock);self.advance()
        self.assertEqual((self.e.elapsed_seconds,self.a.stages['atk']),(12,1))
        self.e=load_engine(self.rules,json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False)))
        self.a=W.actor_index(self.e)[self.a.entity_id]
        before=dump_engine(self.e);self.advance();self.assertEqual(before,dump_engine(self.e))
    def test_completed_old_query_and_reply_do_not_release_later_wait(self):
        self.install();old=self.advance();self.answer(old);self.advance()
        self.install();current=self.advance('second',9)
        self.assertEqual((current['status'],self.e.elapsed_seconds),('waiting',17))
        before=dump_engine(self.e);self.advance();self.answer(old)
        self.assertEqual(before,dump_engine(self.e));self.assertEqual(current['status'],'waiting')
    def test_two_due_children_wait_separately_without_replaying_prefix(self):
        self.install(stat='atk');self.install(stat='def')
        clock=self.advance();self.answer(clock);again=self.advance()
        self.assertEqual((again['status'],self.e.elapsed_seconds,len(again['children'])),('waiting',5,2))
        self.assertEqual((self.a.stages['atk'],self.a.stages['def']),(1,0))
        self.answer(again);self.advance();self.assertEqual((self.a.stages['atk'],self.a.stages['def']),(1,1))
    def test_late_failure_preserves_time_and_finished_earlier_boundary(self):
        self.install(seconds=3,conditional=False,stat='atk')
        self.install(seconds=6,conditional=False,stat='def')
        original=FX.HANDLERS['stage_change']
        def fail_later(e,a,t,effect,ctx):
            if e.elapsed_seconds==6:raise ValueError('late native consequence failure')
            return original(e,a,t,effect,ctx)
        with patch.dict(FX.HANDLERS,stage_change=fail_later):
            with self.assertRaisesRegex(ValueError,'did not complete'):self.advance()
        self.assertEqual((self.e.elapsed_seconds,self.a.stages['atk'],self.a.stages['def']),(6,1,0))
        self.assertEqual(self.advance()['status'],'complete')
        self.assertEqual((self.e.elapsed_seconds,self.a.stages['atk'],self.a.stages['def']),(12,1,1))
    def test_native_job_waits_for_clock_before_crediting_work(self):
        self.install()
        self.e.start_activity_job(self.a,[],job_id='work',source='external/job',definition={'required_seconds':12})
        def work():return self.e.advance_activity_job('work',interval_id='one',seconds=12,resumable=True)
        pending=work();self.assertEqual((pending['clock_status'],pending['worked_seconds']),('waiting',0))
        clock=self.e._clock_invocations[pending['clock_id']];self.answer(clock)
        result=work();self.assertEqual((result['status'],result['worked_seconds'],self.e.elapsed_seconds),('complete',12,12))
        self.assertEqual(work()['worked_seconds'],12)
        job=self.e._activity_jobs['jobs']['work'];self.assertIs(clock['bindings'][0]['record'],job['events'][-1])
    def test_saved_pending_job_resumes_same_work_without_duplicate_credit(self):
        self.install()
        self.e.start_activity_job(self.a,[],job_id='saved',source='external/job',definition={'required_seconds':12})
        self.e.advance_activity_job('saved',interval_id='one',seconds=12,resumable=True)
        self.e=load_engine(self.rules,json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False)))
        self.a=W.actor_index(self.e)[self.a.entity_id]
        job=self.e._activity_jobs['jobs']['saved'];clock=self.e._clock_invocations[job['pending_work']['clock_id']]
        self.answer(clock)
        result=self.e.advance_activity_job('saved',interval_id='one',seconds=12,resumable=True)
        self.assertEqual((result['worked_seconds'],self.e.elapsed_seconds),(12,12))
        self.assertEqual(len([r for r in job['events'] if r['kind']=='work']),1)
    def test_copied_delivery_and_completion_flag_without_actual_reply_rejected(self):
        self.install();clock=self.advance();child=clock['children'][0];original=child['record']
        child['record']=dict(original)
        with self.assertRaises(ValueError):CLOCK.validate(self.e)
        child['record']=original
        effect=self.e._effect_dispatch_receipts[original['receipt']];effect['status']='completed'
        with self.assertRaises(ValueError):self.advance()
        effect['status']='condition_unknown';self.answer(clock);self.advance()
    def test_clock_zero_interval_and_automatic_id_collision(self):
        first=self.e.advance_time(0,[self.a],request_id='clock:2',source='external/clock')
        second=self.e.advance_time(0,[self.a],source='external/clock')
        self.assertEqual((first['id'],second['id']),('clock:2','clock:3'))
        result=self.advance('zero',0);self.assertEqual((result['status'],self.e.elapsed_seconds),('complete',0))
    def test_rng_observed_by_completed_prefix_is_not_drawn_again(self):
        self.install(seconds=3,conditional=False,stat='def');self.install(seconds=5)
        original=FX.HANDLERS['stage_change']
        def with_observation(e,a,t,effect,ctx):
            e.d20()
            return original(e,a,t,effect,ctx)
        with patch.dict(FX.HANDLERS,stage_change=with_observation):
            clock=self.advance();before=self.e.rng.getstate();self.advance()
            self.assertEqual(self.e.rng.getstate(),before)
            self.answer(clock);after=self.e.rng.getstate();self.answer(clock);self.advance()
            self.assertEqual(self.e.rng.getstate(),after)


if __name__=='__main__':unittest.main()
