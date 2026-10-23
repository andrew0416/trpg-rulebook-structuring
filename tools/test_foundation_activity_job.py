"""Common jobs: real intervals, participants, rolls, limits and shared credits."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as fixtures
import activity_jobs as J,world_entities as W,pokemon_teaching as T,training_features as TRAINING,downtime as D
import resolution_transaction as TX
from state_codec import dump_engine,load_engine


class ActivityJobTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.ProgressionStateTests.setUpClass.__func__)
    add=fixtures.ProgressionStateTests.add
    pokemon=fixtures.ProgressionStateTests.pokemon
    def setUp(self):
        fixtures.ProgressionStateTests.setUp(self)
        self.ps=[self.pokemon() for _ in range(2)]
    def start(self,identity='job',policy=None,context=None,participants=None):
        return self.e.start_activity_job(self.a,self.ps if participants is None else participants,job_id=identity,
            source='external/job-policy',definition={'required_seconds':60} if policy is None else policy,context=context)
    def work(self,identity='job',interval='one',seconds=30,**kw):
        return self.e.advance_activity_job(identity,interval_id=interval,seconds=seconds,**kw)
    def attempt(self,identity='job',interval='one',face=1,**kw):
        return self.e.attempt_activity_job(identity,self.a,'명령',interval_id=interval,options={'fixed':[face]*4},**kw)
    def unchanged(self,call,pattern=None):
        before=dump_engine(self.e);rng=self.e.rng.getstate()
        with self.assertRaisesRegex(ValueError,pattern or '.*'):call()
        self.assertEqual(before,dump_engine(self.e));self.assertEqual(rng,self.e.rng.getstate())
    def restore(self):
        restored=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False)))
        return restored,W.actor_index(restored)
    def test_actual_group_time_progress_and_completion(self):
        self.start();first=self.work();self.assertEqual((first['status'],first['progress_seconds'],self.e.elapsed_seconds),('active',30,30))
        final=self.work(interval='two');self.assertEqual((final['status'],final['worked_seconds'],self.e.elapsed_seconds),('complete',60,60))
        row=self.e._activity_jobs['jobs']['job'];self.assertIs(row['owner'],self.a);self.assertIs(row['participants'][1],self.ps[1])
        self.unchanged(lambda:self.work(interval='three'))
    def test_same_interval_and_job_identity_cannot_charge_twice(self):
        self.start();self.work();self.unchanged(lambda:self.work(), 'already recorded')
        self.unchanged(lambda:self.start(),'already used')
    def test_continuity_gap_rejects_and_explicit_new_job_starts_fresh(self):
        self.start();self.work();self.e.advance_time(1,[self.a,*self.ps])
        self.unchanged(lambda:self.work(interval='two'),'adjacent')
        fresh=self.start('fresh');self.assertEqual(fresh['progress_seconds'],0)
    def test_changed_context_does_not_silently_retain_progress(self):
        self.start(context={'site':'A'});self.work()
        self.unchanged(lambda:self.work(interval='two',context={'site':'B'}),'context')
    def test_forbidden_resume_is_inert(self):
        self.start();self.work();self.e.interrupt_activity_job('job',reason='participant interrupted')
        self.unchanged(lambda:self.work(interval='two'),'paused')
        self.unchanged(lambda:self.e.resume_activity_job('job',reason='return'),'forbids')
    def test_selected_retention_allows_explicit_resume_and_context_change(self):
        self.start(policy={'required_seconds':60,'resume':'retain'},context={'site':'A'});self.work()
        self.e.interrupt_activity_job('job',reason='travel');self.e.advance_time(20,[self.a,*self.ps])
        out=self.e.resume_activity_job('job',reason='returned',context={'site':'B'});self.assertEqual(out['progress_seconds'],30)
        out=self.work(interval='two');self.assertEqual((out['status'],self.e.elapsed_seconds),('complete',80))
    def test_reset_discards_progress_but_keeps_spent_time_and_attempts(self):
        self.start(policy={'target':100,'attempt_limit':2,'interval_seconds':30,'resume':'reset'})
        self.attempt();self.e.interrupt_activity_job('job',reason='new approach')
        out=self.e.resume_activity_job('job',reason='restart');self.assertEqual((out['total'],out['attempts'],out['worked_seconds']),(0,1,30))
        out=self.attempt(interval='two');self.assertEqual((out['status'],out['attempts'],out['total']),('failed',2,4))
        self.unchanged(lambda:self.attempt(interval='three'),'terminal')
    def test_limited_attempts_use_native_roll_and_actual_interval(self):
        self.start(policy={'target':12,'attempt_limit':2,'interval_seconds':60})
        first=self.attempt();last=self.attempt(interval='two',face=2)
        self.assertEqual((first['total'],last['total'],last['status'],self.e.elapsed_seconds),(4,12,'complete',120))
        row=self.e._activity_jobs['jobs']['job'];self.assertEqual(row['events'][1]['contribution'],{'actor_id':self.a.entity_id,'skill':'명령'})
        restored,_=self.restore();self.assertEqual(restored.activity_job_status('job'),last)
    def test_exhausted_zero_attempts_draw_no_dice_or_time(self):
        out=self.start(policy={'target':100,'attempt_limit':0,'interval_seconds':60})
        self.assertEqual(out['status'],'failed');self.unchanged(lambda:self.attempt(),'terminal');self.assertEqual(self.e.elapsed_seconds,0)
    def test_interval_duration_and_wrong_contributor_are_inert(self):
        self.start(policy={'target':100,'attempt_limit':2,'interval_seconds':60})
        self.unchanged(lambda:self.work(seconds=30),'native skill')
        other=self.add(deepcopy(fixtures.build_trainer(self.r,'other',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'명령':4})))
        self.unchanged(lambda:self.e.attempt_activity_job('job',other,'명령',interval_id='x'),'contributor')
    def test_required_pause_cannot_be_replaced_with_a_boolean_claim(self):
        self.start(policy={'target':100,'attempt_limit':2,'interval_seconds':60,'continuity':'resumable','required_pause_seconds':30})
        self.attempt();self.unchanged(lambda:self.attempt(interval='two'),'pause')
        self.e.advance_time(30,[self.a,*self.ps]);self.assertEqual(self.attempt(interval='two')['status'],'failed')
    def test_eight_hour_sessions_have_actual_shared_clock_and_daily_limit(self):
        policy={'required_seconds':8*3600,'daily_limits':{'sessions':2,'seconds':16*3600}}
        self.start('dream1',policy);self.work('dream1',seconds=8*3600)
        self.start('dream2',policy);self.work('dream2',seconds=8*3600)
        self.assertEqual(self.e.elapsed_seconds,16*3600)
        self.unchanged(lambda:self.start('dream3',policy),'daily job sessions')
        for c in (self.a,*self.ps):D.new_day(c)
        self.start('dream3',policy);self.work('dream3',seconds=8*3600)
        self.assertEqual(self.e.elapsed_seconds,24*3600)
    def test_daily_bucket_cannot_silently_raise_its_limit(self):
        self.start(policy={'required_seconds':60,'daily_limits':{'sessions':1}})
        self.unchanged(lambda:self.start('new',{'required_seconds':60,'daily_limits':{'sessions':2}}),'cannot change')
    def test_daily_attempt_and_seconds_limits_survive_reset(self):
        self.start(policy={'target':100,'interval_seconds':60,'resume':'reset','daily_limits':{'attempts':1,'seconds':60}})
        self.attempt();self.e.interrupt_activity_job('job',reason='reset');self.e.resume_activity_job('job',reason='return')
        self.unchanged(lambda:self.attempt(interval='two'),'daily job')
    def test_bad_definition_or_calendar_cannot_create_jobs(self):
        for policy in ({'continuity':'unknown'},{'resume':None},{'required_seconds':True},{'target':10},{'attempt_limit':2},{'daily_limits':{'unknown':1}}, {'required_seconds':60,'credit':{'family':'hour','applications':[[1]],'same_day':True}}):
            self.unchanged(lambda p=policy:self.start(policy=p))
        D.new_day(self.ps[-1])
        self.unchanged(lambda:self.start(),'calendars')
    def test_duplicate_or_detached_participants_reject(self):
        self.unchanged(lambda:self.start(participants=[self.ps[0],self.ps[0]]),'distinct')
        detached=deepcopy(self.ps[0],{id(self.r):self.r})
        self.unchanged(lambda:self.start(participants=[detached]))
    def test_credit_family_and_application_compatibility_and_duplicate_use(self):
        self.start(policy={'required_seconds':60,'credit':{'family':'lesson','applications':['xp','teach:*'],'same_day':True}})
        done=self.work(seconds=60);credit_id=done['credit_ids'][self.ps[0].entity_id]
        def apply(app='xp',family='lesson',seconds=60):return self.e.apply_activity_credit(self.a,self.ps[0],credit_id=credit_id,application=app,family=family,minimum_seconds=seconds)
        self.unchanged(lambda:apply('unrelated'),'incompatible');self.unchanged(lambda:apply(family='other'),'incompatible')
        self.unchanged(lambda:apply(seconds=61),'incompatible');apply();apply('teach:skill')
        self.assertEqual(self.e.elapsed_seconds,60);self.unchanged(apply,'already consumed')
    def test_native_hour_shares_three_consumers_and_cannot_replay_removed_marker(self):
        self.a.spec['feats']=list(TRAINING.RULES)
        self.a.spec['skills'].update({'육상':3,'협박':3,'매력':3})
        for p in self.ps:p.spec['tutor_points']=6
        self.e.complete_training_hour(self.a,self.ps,safe=True,reason='safe observed ground',request_id='native')
        self.e.pokemon_activity(self.a,'experience_training',targets=self.ps,from_training=True)
        self.e.train_pokemon(self.a,[(p,[next(iter(TRAINING.RULES))]) for p in self.ps],minutes=30,reason='same hour',request_id='regime',from_training=True)
        T.teach_edge(self.e,self.a,target=self.ps[0],edge=T.EDGE,skill='육상',from_training=True)
        row=self.ps[0].spec['completed_training_hour'];actual=self.ps[0].custom_conditions[J.CREDITS][row['credit_id']]
        self.assertEqual(len(actual['claims']),3);self.assertEqual(self.e.elapsed_seconds,3600)
        row['applications'].remove('training_regime')
        self.unchanged(lambda:self.e.train_pokemon(self.a,[(self.ps[0],[next(iter(TRAINING.RULES))])],minutes=30,reason='again',request_id='duplicate',from_training=True),'already consumed')
    def test_json_and_gm_restore_preserve_credit_and_participant_aliases(self):
        self.e.complete_training_hour(self.a,self.ps,safe=True,reason='safe',request_id='native')
        for restored in (self.restore()[0],):
            actors=W.actor_index(restored);job=next(iter(restored._activity_jobs['jobs'].values()))
            self.assertIs(job['owner'],actors[self.a.entity_id]);target=actors[self.ps[0].entity_id]
            self.assertIs(job['credits'][target.entity_id],target.custom_conditions[J.CREDITS][target.spec['completed_training_hour']['credit_id']])
        snapshot=self.e.gm.snapshot();self.e.advance_time(1,[self.a,*self.ps]);self.e.gm.restore(snapshot,reason='restore job')
        J.validate_world(self.e,W.actor_index(self.e));self.assertEqual(self.e.elapsed_seconds,3600)
    def test_changed_definition_and_false_progress_are_rejected_on_use(self):
        self.start();row=self.e._activity_jobs['jobs']['job'];row['definition']['required_seconds']=30
        with self.assertRaises(ValueError):self.work()
        row['definition']['required_seconds']=60;row['progress_seconds']=30
        with self.assertRaises(ValueError):self.work()
    def test_copied_or_forged_credit_and_future_interval_fail_integrity(self):
        self.e.complete_training_hour(self.a,self.ps,safe=True,reason='safe',request_id='native')
        job=next(iter(self.e._activity_jobs['jobs'].values()));receipt=job['credits'][self.ps[0].entity_id]
        self.ps[0].custom_conditions[J.CREDITS][receipt['id']]=deepcopy(receipt)
        with self.assertRaises(ValueError):J.validate_world(self.e,W.actor_index(self.e))
        self.ps[0].custom_conditions[J.CREDITS][receipt['id']]=receipt;receipt['seconds']+=1
        with self.assertRaises(ValueError):J.credit(self.e,self.a,self.ps[0],credit_id=receipt['id'],application='xp',family='training_hour',minimum_seconds=1)
        receipt['seconds']-=1;job['events'][1]['end']+=1
        with self.assertRaises(ValueError):J.validate_world(self.e,W.actor_index(self.e))
    def test_late_roll_failure_rolls_back_time_rng_progress_and_participants(self):
        self.start(policy={'target':100,'interval_seconds':60});native=type(self.e).skill_roll
        def fail(e,c,*args,**kw):
            native(e,c,*args,**kw);c.spec['late_job_failure']=True
            raise ValueError('late roll failure')
        with patch.object(type(self.e),'skill_roll',fail):self.unchanged(lambda:self.attempt(),'late roll failure')
    def native_extended(self,identity='one',**kw):
        options={'mode':'extended','task_id':'native-check','interval_id':identity,'interval':{'amount':1,'unit':'minute'},
                 'interval_completed':True,'complexity':2,'limited':True,'fixed':[1]*4}
        options.update(kw)
        return self.e.common_action(self.a,'명령',5,**options)
    def test_existing_extended_adapter_uses_job_clock_and_stops_at_limit(self):
        first=self.native_extended();last=self.native_extended('two')
        self.assertEqual((first.result.total,last.result.total,last.result.status,self.e.elapsed_seconds),(4,8,'exhausted',120))
        job=self.e._activity_jobs['jobs']['extended-check:native-check']
        self.assertEqual((job['status'],job['attempts'],job['worked_seconds']),('failed',2,120))
        self.unchanged(lambda:self.native_extended('three'),'terminal')
        restored,actors=self.restore();self.assertIs(restored._extended_checks['native-check']['actor'],actors[self.a.entity_id])
    def test_native_extended_unknown_duration_and_missing_interval_do_not_draw(self):
        before=dump_engine(self.e)
        out=self.native_extended(interval={'amount':1,'unit':'unselected-scene'});self.assertIn('duration',out.required)
        self.assertEqual(before,dump_engine(self.e))
        out=self.native_extended(interval_completed=False);self.assertIn('interval',out.required);self.assertEqual(before,dump_engine(self.e))
    def test_native_extended_zero_target_has_no_phantom_interval(self):
        out=self.native_extended(fixed=[1]*4,complexity=2,limited=False)
        self.assertEqual(self.e.elapsed_seconds,60)
        before=self.e.elapsed_seconds
        result=self.e.common_action(self.a,'명령',0,mode='extended',task_id='zero',interval_id='one',interval={'amount':1,'unit':'hour'},interval_completed=True,complexity=2,limited=True,fixed=[1]*4)
        self.assertEqual((result.result.status,result.result.attempts_used,self.e.elapsed_seconds),('complete',0,before))
    def test_gm_restore_rejects_forged_progress_before_mutating_world(self):
        self.start();self.work();self.e.gm.snapshot('saved')
        self.e.gm.snapshots['saved']['engine']['_activity_jobs']['jobs']['job']['progress_seconds']+=1
        self.unchanged(lambda:self.e.gm.restore('saved'),'progress')
    def test_credit_cannot_cross_explicit_calendar_or_provider(self):
        self.start(policy={'required_seconds':60,'credit':{'family':'lesson','applications':['xp'],'same_day':True}})
        done=self.work(seconds=60);identity=done['credit_ids'][self.ps[0].entity_id]
        for c in (self.a,*self.ps):D.new_day(c)
        self.unchanged(lambda:self.e.apply_activity_credit(self.a,self.ps[0],credit_id=identity,application='xp',family='lesson',minimum_seconds=60),'calendar')
    def test_typed_common_credit_and_native_roll_are_validated(self):
        self.start(policy={'required_seconds':60,'credit':{'family':'lesson','applications':['xp'],'same_day':True}})
        done=self.work(seconds=60);job=self.e._activity_jobs['jobs']['job'];receipt=job['credits'][self.ps[0].entity_id]
        for key,value in (('day',False),('seconds',True),('end',False)):
            old=receipt[key];receipt[key]=value
            with self.assertRaises(ValueError):J.validate_world(self.e,W.actor_index(self.e))
            receipt[key]=old
        self.start('roll',{'target':100,'interval_seconds':60});self.attempt('roll')
        roll=self.e._activity_jobs['jobs']['roll']['events'][1]['roll'];old=roll.faces
        object.__setattr__(roll,'faces',(7,7,7,7))
        with self.assertRaises(ValueError):J.validate_world(self.e,W.actor_index(self.e))
        object.__setattr__(roll,'faces',old)
    def test_reset_time_credit_uses_only_work_after_selected_restart(self):
        self.start(policy={'required_seconds':60,'resume':'reset','credit':{'family':'lesson','applications':['xp'],'same_day':True}})
        self.work();self.e.interrupt_activity_job('job',reason='discard interrupted progress');self.e.resume_activity_job('job',reason='restart')
        self.work(interval='two');done=self.work(interval='three');receipt=self.e._activity_jobs['jobs']['job']['credits'][self.ps[0].entity_id]
        self.assertEqual((done['worked_seconds'],done['progress_seconds'],receipt['start'],receipt['end'],receipt['seconds']),(90,60,30,90,60))
        self.restore()
    def test_existing_projection_cannot_inflate_shared_hour(self):
        self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
        self.e.pokemon_activity(self.a,'groom',targets=self.ps,safe=True)
        self.ps[0].spec['training_credit']['hours']=2
        self.unchanged(lambda:T.training_credit(self.e,self.a,self.ps[0],'training_regime'),'duration')
        self.ps[0].spec['training_credit']['hours']=1;self.ps[0].spec['training_credit']['completed_at']-=1
        self.unchanged(lambda:T.training_credit(self.e,self.a,self.ps[0],'training_regime'),'projection')
    def test_duplicated_past_job_interval_is_not_a_second_time_proof(self):
        self.start();self.work(seconds=60);original=self.e._activity_jobs['jobs']['job']
        duplicate=deepcopy(original,{id(c):c for c in (self.a,*self.ps)})
        duplicate['id']='copied';duplicate['intent']=TX.request_fingerprint(J._intent(duplicate))
        self.e._activity_jobs['jobs']['copied']=duplicate
        with self.assertRaisesRegex(ValueError,'overlap'):J.validate_world(self.e,W.actor_index(self.e))
    def test_resume_history_cannot_precede_the_interruption(self):
        self.start(policy={'required_seconds':60,'resume':'retain'});self.work();self.e.advance_time(10,[self.a,*self.ps])
        self.e.interrupt_activity_job('job',reason='interrupt');self.e.resume_activity_job('job',reason='return')
        job=self.e._activity_jobs['jobs']['job'];job['events'][-2]['at']=35;job['events'][-1]['at']=34;job['end_seconds']=34
        with self.assertRaisesRegex(ValueError,'chronology'):J.validate_world(self.e,W.actor_index(self.e))
    def test_job_native_feature_choice_preserves_observation_without_charging_interval_twice(self):
        import skill_feature_actions as F
        self.a.spec.setdefault('feats',[]).append(F.MONKEY)
        self.start(policy={'target':10,'attempt_limit':1,'interval_seconds':60})
        options={'fixed':[1]*4,'feature':F.MONKEY,'roll_id':'job-roll','feature_options':{'decision':lambda first:'invalid'}}
        with self.assertRaises(ValueError):self.e.attempt_activity_job('job',self.a,'명령',interval_id='one',options=options)
        observed=F.event(self.e,self.a,'job-roll').first
        self.assertEqual((observed.total,self.e.elapsed_seconds,self.e.activity_job_status('job')['attempts']),(4,0,0))
        options['feature_options']={'decision':lambda first:True,'reroll_faces':[2]*4}
        done=self.e.attempt_activity_job('job',self.a,'명령',interval_id='one',options=options)
        self.assertEqual((done['status'],done['total'],self.e.elapsed_seconds),('complete',10,60))
        self.assertIs(F.event(self.e,self.a,'job-roll').first,observed)
        self.unchanged(lambda:self.e.attempt_activity_job('job',self.a,'명령',interval_id='one',options=options),'terminal')
    def test_job_skill_options_keep_actual_target_binding(self):
        self.start(policy={'target':100,'interval_seconds':60});native=type(self.e)._prepare_skill_roll
        def prepare(e,c,*args,**options):
            W.require_actors(e,options['skill_target'])
            return native(e,c,*args,**options)
        with patch.object(type(self.e),'_prepare_skill_roll',prepare):
            out=self.e.attempt_activity_job('job',self.a,'명령',interval_id='one',options={'fixed':[1]*4,'skill_target':self.ps[0]})
        self.assertEqual((out['total'],self.e.elapsed_seconds),(4,60))


if __name__=='__main__':unittest.main()
