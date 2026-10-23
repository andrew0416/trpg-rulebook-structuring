"""Actual timed consumers wait, restore and finish exactly once."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'data/examples').is_dir():ROOT=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from state_codec import dump_engine,load_engine
import effects as FX,clock_invocations as CLOCK,combat_timing as LIFE,world_entities as W
import skill_feature_actions as SF,item_stock as STOCK,food_effects as FOOD
import test_category2_item_maturation as _fixture_test_category2_item_maturation
import test_category2_medicine_stock as _fixture_test_category2_medicine_stock


class TimedConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        self.e=Engine(self.rules,seed=817)
        self.a=Combatant(self.rules,build_trainer(self.rules,'timed consumer',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
            skills={'명령':4,'육상':4,'매력':4},extra={'items':{'붕대':1,'초코바':1,'맛있는물':1,'이유식':1},'edges':[],'feats':[]}))
        self.e.gm.add_combatant(self.a,pos=(0,0),side='party',reason='actual timed consumer')
        self.p=Combatant(self.rules,build_pokemon(self.rules,'이브이',10,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
        self.e.gm.add_combatant(self.p,pos=(1,0),side='party',reason='actual recipient')
    def install(self,actor=None):
        actor=actor or self.a
        effect={'type':'stage_change','stat':'atk','delta':1,'repeat':{'seconds':5,'times':1},'if':'target was asleep'}
        self.assertEqual(FX.run_effects(self.e,actor,actor,[effect],{'hit':True,'target_was_asleep':True},'external/timed-consumer'),(1,0))
    def answer(self,clock_id):
        clock=self.e._clock_invocations[clock_id];child=clock['children'][-1]
        actor=W.actor_index(self.e)[child['owner_id']]
        self.e.resolve_effect_condition(actor,child['record']['receipt'],target_was_asleep=True,reason='actual GM observation at this boundary')
    def restore(self):
        ids=self.a.entity_id,self.p.entity_id
        self.e=load_engine(self.rules,json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False)))
        self.a,self.p=(W.actor_index(self.e)[uid] for uid in ids)
    def use(self,item,*,identity='intake',target=None,**kwargs):
        options=dict(duration_minutes=1,duration_reason='observed full Extended interval',resumable=True,request_id=identity)
        options.update(kwargs)
        return self.e.use_item(self.a,item,target or self.p,**options)
    def job(self):
        return self.e.start_activity_job(self.a,[],job_id='skill-work',source='external/skill-work',
            definition={'target':10,'attempt_limit':1,'interval_seconds':60})
    def attempt(self,**kwargs):
        options=kwargs.pop('options',{'fixed':[2]*4})
        return self.e.attempt_activity_job('skill-work',self.a,'명령',interval_id='one',resumable=True,options=options,**kwargs)
    def inert(self,call):
        before=dump_engine(self.e)
        with self.assertRaises(ValueError):call()
        self.assertEqual(before,dump_engine(self.e))
    def test_bandage_waits_then_binds_actual_application_once_after_restore(self):
        self.install();out=self.use('붕대',identity='dressing')
        self.assertEqual((out['status'],self.e.elapsed_seconds,self.a.spec['items']['붕대']),('waiting',5,1))
        self.assertFalse(self.p.spec.get('bandages'))
        self.restore();self.answer('dressing');out=self.use('붕대',identity='dressing')
        record=self.p.spec['bandages'][0];clock=self.e._clock_invocations['dressing']
        self.assertEqual((out['activity'],record['started_at'],self.a.spec['items']['붕대']),('apply_bandages',60,0))
        self.assertIs(clock['bindings'][0]['record'],record)
        self.assertIs(clock['activity']['native'],record)
        self.assertIs(clock['activity']['payment'],record['item_stock'])
        self.restore();before=dump_engine(self.e);self.assertEqual(self.use('붕대',identity='dressing'),out)
        self.assertEqual(before,dump_engine(self.e))
    def test_direct_self_bandage_activity_uses_same_resumption(self):
        self.install()
        def apply():return self.e.pokemon_activity(self.a,'apply_bandages',target=self.a,minutes=1,reason='native self application',resumable=True,request_id='self-dressing')
        self.assertEqual(apply()['status'],'waiting');self.answer('self-dressing')
        self.assertEqual(apply()['record']['started_at'],60)
        self.assertEqual((len(self.a.spec['bandages']),self.a.spec['items']['붕대']),(1,0))
    def test_bandage_finish_failure_keeps_clock_but_rolls_back_payment(self):
        self.install();self.use('붕대',identity='dressing');self.answer('dressing')
        original=STOCK.debit
        def fail(*args,**kwargs):
            original(*args,**kwargs)
            raise ValueError('late bandage payment failure')
        with patch.object(STOCK,'debit',fail):
            with self.assertRaisesRegex(ValueError,'late bandage'):self.use('붕대',identity='dressing')
        self.assertEqual((self.e.elapsed_seconds,self.a.spec['items']['붕대']),(60,1))
        self.assertFalse(self.p.spec.get('bandages'));self.inert(lambda:self.e.advance_time(1))
        self.restore();self.assertEqual(self.use('붕대',identity='dressing')['record']['started_at'],60)
    def test_drink_waits_before_healing_and_paid_history_survives_restore(self):
        self.p.hp=1;self.install();self.use('맛있는물')
        self.assertEqual((self.p.hp,self.a.spec['items']['맛있는물'],self.e.elapsed_seconds),(1,1,5))
        self.assertFalse(self.p.spec.get('drink_history'));self.restore();self.answer('intake')
        result=self.use('맛있는물');self.assertEqual((result['healed'],self.e.elapsed_seconds),(20,60))
        clock=self.e._clock_invocations['intake'];self.assertIs(clock['activity']['native'],self.p.spec['drink_history'][0])
        self.restore();before=dump_engine(self.e);self.assertEqual(self.use('맛있는물'),result);self.assertEqual(before,dump_engine(self.e))
    def test_snack_waits_before_storing_buff_and_replay_does_not_restore_consumed_buff(self):
        self.install();self.use('초코바');self.assertFalse(self.p.buffs)
        self.answer('intake');result=self.use('초코바');buff=self.p.buffs[0]
        self.assertIs(self.e._clock_invocations['intake']['activity']['payment'],buff['item_stock'])
        self.e.consume_food_buff(self.p,buff_id=buff['id'],action_kind='swift',action_reason='actual stored benefit consumed')
        self.restore();before=dump_engine(self.e);self.assertEqual(self.use('초코바'),result)
        self.assertEqual(before,dump_engine(self.e));self.assertFalse(self.p.buffs)
    def test_baby_food_waits_with_selected_policy_then_finishes_once(self):
        self.install();self.use('이유식',food_policy='book_xp20_level15')
        self.assertNotIn('baby_food',self.p.spec);self.answer('intake')
        result=self.use('이유식',food_policy='book_xp20_level15');self.assertTrue(result['eligible'])
        self.restore();before=dump_engine(self.e);self.assertEqual(self.use('이유식',food_policy='book_xp20_level15'),result)
        self.assertEqual(before,dump_engine(self.e));self.assertEqual(self.p.spec['baby_food']['at'],60)
    def test_changed_item_target_duration_reason_and_policy_are_inert_while_waiting(self):
        self.install();self.use('맛있는물')
        for call in (lambda:self.use('초코바'),lambda:self.use('맛있는물',target=self.a),
                     lambda:self.use('맛있는물',duration_minutes=2),lambda:self.use('맛있는물',duration_reason='changed'),
                     lambda:self.use('맛있는물',food_policy='book_xp20_level15')):
            self.inert(call)
        self.assertEqual(self.use('맛있는물')['status'],'waiting')
    def test_late_drink_failure_preserves_time_and_retry_does_not_pay_twice(self):
        self.install();self.use('맛있는물');self.answer('intake');self.p.hp=1
        native=type(self.e).heal
        def fail(e,*args,**kwargs):
            native(e,*args,**kwargs);raise ValueError('native healing failure')
        with patch.object(type(self.e),'heal',fail):
            with self.assertRaisesRegex(ValueError,'native healing'):self.use('맛있는물')
        self.assertEqual((self.e.elapsed_seconds,self.p.hp,self.a.spec['items']['맛있는물']),(60,1,1))
        self.assertFalse(self.p.spec.get('drink_history'));self.restore();self.use('맛있는물')
        self.assertEqual((self.e.elapsed_seconds,len(self.p.spec['drink_history'])),(60,1))
    def test_skill_attempt_waits_without_dice_or_credit_then_finishes_once(self):
        self.install();self.job();before=self.e.rng.getstate();out=self.attempt()
        self.assertEqual((out['clock_status'],out['attempts'],out['worked_seconds'],self.e.elapsed_seconds),('waiting',0,0,5))
        self.assertEqual(before,self.e.rng.getstate());self.restore();self.answer(out['clock_id'])
        result=self.attempt();self.assertEqual((result['status'],result['total'],self.e.elapsed_seconds),('failed',8,60))
        event=self.e._activity_jobs['jobs']['skill-work']['events'][-1]
        self.assertIs(SF.event(self.e,self.a,event['attempt_request']['roll_id']).final,event['roll'])
        self.restore();before=dump_engine(self.e);self.assertEqual(self.attempt(),result);self.assertEqual(before,dump_engine(self.e))
    def test_pending_skill_rejects_changed_roll_options_and_context(self):
        self.install();self.job();self.attempt()
        self.inert(lambda:self.attempt(options={'fixed':[3]*4}))
        self.inert(lambda:self.attempt(context={'changed':True}))
        self.inert(lambda:self.e.interrupt_activity_job('skill-work',reason='cannot drop a waiting interval'))
    def test_skill_feature_choice_error_keeps_elapsed_time_and_observed_first_roll(self):
        self.a.spec['feats'].append(SF.MONKEY);self.install();self.job()
        options={'feature':SF.MONKEY,'roll_id':'feature-work','feature_options':{'decision':lambda first:'invalid'}}
        out=self.attempt(options=options);self.answer(out['clock_id'])
        with self.assertRaisesRegex(ValueError,'boolean'):self.attempt(options=options)
        observed=SF.event(self.e,self.a,'feature-work').first;state=self.e.rng.getstate()
        self.assertEqual((self.e.elapsed_seconds,self.e.activity_job_status('skill-work')['attempts']),(60,0))
        self.inert(lambda:self.e.advance_time(1));self.restore()
        options['feature_options']={'decision':lambda first:True,'reroll_faces':[2]*4}
        result=self.attempt(options=options)
        self.assertEqual((result['status'],result['total'],self.e.elapsed_seconds),('complete',10,60))
        self.assertEqual(SF.event(self.e,self.a,'feature-work').first,observed)
        self.assertEqual(state,self.e.rng.getstate());before=dump_engine(self.e);self.attempt(options=options)
        self.assertEqual(before,dump_engine(self.e))
    def test_skill_finish_failure_keeps_observation_for_native_retry(self):
        self.job();native=__import__('activity_jobs')._finish_work
        def fail(*args,**kwargs):
            native(*args,**kwargs);raise ValueError('native work failure')
        with patch('activity_jobs._finish_work',fail):
            with self.assertRaisesRegex(ValueError,'native work'):self.attempt(options={})
        pending=self.e._activity_jobs['jobs']['skill-work']['pending_work']
        observed=SF.event(self.e,self.a,pending['attempt']['roll_id']).final;state=self.e.rng.getstate()
        self.assertEqual((self.e.elapsed_seconds,self.e.activity_job_status('skill-work')['attempts']),(60,0))
        self.restore();result=self.attempt(options={})
        self.assertEqual((result['total'],result['attempts'],self.e.elapsed_seconds),(observed.total,1,60))
        self.assertEqual(state,self.e.rng.getstate())
    def test_held_bandage_waits_and_consumes_only_the_selected_physical_instance(self):
        _fixture_test_category2_medicine_stock.MedicineStockTests.held(self,self.a,'붕대','dressing-instance');self.install()
        self.assertEqual(self.use('붕대',held_selection='dressing-instance')['status'],'waiting')
        self.assertNotIn('consumed',self.e._physical_objects['dressing-instance']);self.answer('intake')
        result=self.use('붕대',held_selection='dressing-instance')
        self.assertEqual((self.a.spec['items']['붕대'],result['record']['item_stock']['instance_id']),(1,'dressing-instance'))
        self.assertEqual(self.e._physical_objects['dressing-instance']['consumed']['at'],60)
        self.restore();before=dump_engine(self.e);self.use('붕대',held_selection='dressing-instance');self.assertEqual(before,dump_engine(self.e))
    def test_container_drink_waits_and_keeps_its_empty_reusable_body_on_replay(self):
        import item_containers as CONTAINERS
        _fixture_test_category2_medicine_stock.MedicineStockTests.held(self,self.a,'item/빈병','jar')
        self.e.gm.observe_empty_container(self.a,container_selection='jar',reason='actual empty jar')
        self.e.load_container(self.a,container_selection='jar',item_name='맛있는물',reason='one actual portion loaded')
        self.install();self.p.hp=1;self.assertEqual(self.use('맛있는물',container_selection='jar')['status'],'waiting')
        self.assertIsNotNone(self.e._physical_objects['jar'][CONTAINERS.KEY]['current']);self.restore();self.answer('intake')
        self.assertEqual(self.use('맛있는물',container_selection='jar')['healed'],20)
        self.assertIsNone(self.e._physical_objects['jar'][CONTAINERS.KEY]['current']);before=dump_engine(self.e)
        self.use('맛있는물',container_selection='jar');self.assertEqual(before,dump_engine(self.e))
        self.assertNotIn('consumed',self.e._physical_objects['jar'])


class TimedPhysicalIntakeTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_item_maturation.ItemMaturationTests.setUpClass.__func__)
    setUp=_fixture_test_category2_item_maturation.ItemMaturationTests.setUp
    add=_fixture_test_category2_item_maturation.ItemMaturationTests.add
    held=_fixture_test_category2_item_maturation.ItemMaturationTests.held
    row=_fixture_test_category2_item_maturation.ItemMaturationTests.row
    def install(self):
        effect={'type':'stage_change','stat':'atk','delta':1,'repeat':{'seconds':5,'times':1},'if':'target was asleep'}
        self.assertEqual(FX.run_effects(self.e,self.p,self.p,[effect],{'hit':True,'target_was_asleep':True},'external/shell-wait'),(1,0))
    def answer(self):
        receipt=self.e._clock_invocations['shell']['children'][-1]['record']['receipt']
        self.e.resolve_effect_condition(self.p,receipt,target_was_asleep=True,reason='actual shell-consumer observation')
    def use(self,**kwargs):
        return self.e.use_item(self.p,'item/나무열매쥬스',shell_batch_id=self.key,duration_minutes=1,
            duration_reason='actual shell Snack intake',resumable=True,request_id='shell',**kwargs)
    def test_shell_paid_at_start_never_matures_or_pays_again_during_wait(self):
        self.e.advance_time(1295970);self.install();hp=self.p.hp
        self.assertEqual(self.use()['status'],'waiting');row=self.row();payment=self.e._clock_invocations['shell']['activity']['payment']
        self.assertEqual((row['stage'],row['removal']['at'],self.e.elapsed_seconds),('consumed',1295970,1295975))
        self.assertFalse(self.p.buffs);self.assertEqual(self.use()['status'],'waiting')
        uid=self.p.entity_id;self.e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False)));self.p=W.actor_index(self.e)[uid]
        self.answer();result=self.use();self.assertEqual((result['status'],self.e.elapsed_seconds,self.p.hp),('digestion_buff_gained',1296030,hp))
        self.assertEqual(payment,self.p.buffs[-1]['item_stock']);self.assertNotIn('candy_at',self.row())
        before=dump_engine(self.e);self.use();self.assertEqual(before,dump_engine(self.e))
    def test_held_berry_intake_stops_maturation_at_start_and_pays_at_end(self):
        self.e.advance_time(86370);self.install()
        def use():return self.e.use_item(self.p,'오랭열매',held_selection='berry',duration_minutes=1,
            duration_reason='actual held Berry intake',resumable=True,request_id='shell')
        self.assertEqual(use()['status'],'waiting');self.assertEqual(self.row()['stage'],'cancelled')
        self.assertNotIn('consumed',self.e._physical_objects['berry']);self.answer();result=use()
        self.assertEqual(result['status'],'digestion_buff_gained');self.assertEqual(self.e._physical_objects['berry']['consumed']['at'],86430)
        before=dump_engine(self.e);use();self.assertEqual(before,dump_engine(self.e))
    def test_copied_pending_shell_payment_is_rejected_on_save(self):
        self.e.advance_time(86400);self.install();self.use()
        activity=self.e._clock_invocations['shell']['activity'];original=activity['payment']
        activity['payment']=dict(original)
        with self.assertRaises(ValueError):dump_engine(self.e)
        activity['payment']=original;dump_engine(self.e)


if __name__=='__main__':unittest.main()
