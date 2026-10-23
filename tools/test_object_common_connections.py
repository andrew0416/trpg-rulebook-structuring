"""Common contracts exercised through actual native consumers and JSON restore."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch
import json,sys,unittest

ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'data/examples').is_dir():ROOT=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_consumable_stock as stock_fixtures
import test_category2_container_contents as container_fixtures
import test_category2_frequency_state as frequency_fixtures
import test_category2_homebrew_state as tera_fixtures
import test_category2_dream_state as dream_fixtures
import test_foundation_activity_job as job_fixtures
import test_foundation_crafting_product as product_fixtures
import test_foundation_fossil_creation as fossil_fixtures
import test_category3_food_effects as food_fixtures
import resolution_transaction as TX,consumption_history as HISTORY,consumption_execution as CONSUMPTION
import recovery_receipts as RECOVERY,state_episodes as EPISODES,clock_invocations as CLOCK
import materialization_origins as ORIGINS,action_points as AP,frequency as F
import homebrew_state as TERA,dream_state as DREAM,food_effects as FOOD,bandages as BANDAGES
import crafting_products as PRODUCTS,vitamin_moves as V,world_entities as W,state_codec as CODEC


class CommonConnectionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures=(stock_fixtures.ConsumableStockTests,container_fixtures.ContainerContentsTests,
            frequency_fixtures.FrequencyStateTests,tera_fixtures.HomebrewTests,dream_fixtures.Tests,
            job_fixtures.ActivityJobTests,product_fixtures.ProductTests,fossil_fixtures.FossilTests,food_fixtures.FoodTests)
        for fixture in cls.fixtures:fixture.setUpClass()

    def fixture(self,index):
        value=self.fixtures[index]();value.setUp();return value

    def restore(self,f):
        e=CODEC.load_engine(f.e.r,json.loads(json.dumps(CODEC.dump_engine(f.e),ensure_ascii=False)))
        return e,W.actor_index(e)

    def test_saved_native_and_compact_fingerprints_stay_compatible(self):
        value={'source':'외부/한글','facts':[1,{'b':False,'a':None}]}
        native=sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        compact=sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        self.assertEqual(TX.request_fingerprint(value),native)
        self.assertEqual(PRODUCTS._hash(value),compact)
        records={'same':{'payload_sha256':native,'result':{'units':1}}}
        replay=TX.replay_result(records,'same',value,fingerprint_field='payload_sha256')
        replay['result']['units']=99;self.assertEqual(records['same']['result']['units'],1)
        with self.assertRaises(ValueError):TX.replay_result(records,'same',{'source':'other'},fingerprint_field='payload_sha256')

    def test_exposure_exact_boundary_and_unknown_time_preserve_original_rows(self):
        first={'source':'drink','at':0,'gap_count':0};second={'source':'drink','at':1,'gap_count':1}
        found=HISTORY.select([first,second],source='drink',when=3600,seconds=3600,gap_count=2)
        self.assertEqual(found['count'],1);self.assertIs(found['records'][0],second);self.assertTrue(found['uncertain'])
        self.assertEqual(HISTORY.select([first],source='drink',when=3600,seconds=3600,gap_count=2)['count'],0)
        with self.assertRaises(ValueError):HISTORY.select([first],source='herb')

    def test_herbal_rest_does_not_erase_actual_drink_history(self):
        f=self.fixture(8);f.a.spec['items']['맛있는물']=1;f.drink();f.herb()
        original=f.p.spec['drink_history'];row=original[0]
        self.assertEqual(FOOD.herbal_state(f.p)['count'],1)
        FOOD.extended_rest(f.e,f.p)
        self.assertEqual(FOOD.herbal_state(f.p)['count'],0)
        self.assertIs(f.p.spec['drink_history'],original);self.assertIs(original[0],row)
        payment=next(iter(f.a.spec[CONSUMPTION.KEY].values()))
        self.assertIs(payment['item_stock'],row['item_stock']);self.assertEqual(payment['outcome'],'applied')

    def test_paid_no_effect_vitamin_has_no_growth_and_keeps_original_after_restore(self):
        f=self.fixture(0);f.a.spec['items']={V.HEART:2};before=f.p.spec['tutor_points']
        f.e.use_item(f.a,V.HEART,f.p);f.e.use_item(f.a,V.HEART,f.p)
        rows=list(f.a.spec[CONSUMPTION.KEY].values())
        self.assertEqual([r['outcome'] for r in rows],['applied','no_effect'])
        self.assertEqual(f.p.spec['tutor_points'],before+2);self.assertEqual(len(f.p.spec['vitamins']),1)
        self.assertEqual(f.a.spec['items'][V.HEART],0);self.assertEqual(rows[1]['results'],[])
        with self.assertRaises(ValueError):CONSUMPTION.finish(f.a,deepcopy(rows[0]['item_stock']),target_id=f.p.entity_id,outcome='applied',results=rows[0]['results'])
        e,idx=self.restore(f);paid=list(idx[f.a.entity_id].spec[CONSUMPTION.KEY].values())[0]
        self.assertIs(paid['item_stock'],idx[f.p.entity_id].spec['vitamin_special_uses'][V.HEART]['item_stock'])

    def test_container_transfer_then_intake_never_charges_original_stock_twice(self):
        f=self.fixture(1);f.jar();f.a.spec['items']['튼튼밀크']=2
        loaded=f.e.load_container(f.a,container_selection='jar',item_name='튼튼밀크',reason='actual portion')
        f.a.hp=1;f.e.use_item(f.a,'튼튼밀크',container_selection='jar',duration_minutes=1,duration_reason='actual intake')
        self.assertEqual(f.a.spec['items']['튼튼밀크'],1)
        rows=list(f.a.spec[CONSUMPTION.KEY].values())
        self.assertEqual([r['outcome'] for r in rows],['loaded','applied'])
        self.assertEqual(rows[0]['results'][0]['id'],loaded['content_id'])
        self.assertEqual(rows[1]['item_stock']['kind'],'container_contents')
        self.assertIs(rows[1]['item_stock'],f.a.spec['drink_history'][-1]['item_stock'])
        self.restore(f)

    def test_recovery_parent_cannot_restore_a_later_drain_or_spend(self):
        f=self.fixture(2);AP.spend(f.a,2,{'frequency':{'raw':'2 AP 제거'}})
        first=AP.extended_rest(f.a,request_id='rest-one');self.assertEqual(f.a.spec['ap_removed'],0)
        AP.spend(f.a,1,{'frequency':{'raw':'1 AP 제거'}})
        replay=AP.extended_rest(f.a,request_id='rest-one')
        self.assertEqual(first,replay);self.assertEqual(f.a.spec['ap_removed'],1)
        AP.extended_rest(f.a,request_id='rest-two');self.assertEqual(f.a.spec['ap_removed'],0)
        AP.spend(f.a,1);AP.end_scene(f.a,request_id='scene-one');AP.spend(f.a,1)
        AP.end_scene(f.a,request_id='scene-one');self.assertEqual(f.a.spec['ap_spent'],1)
        e,idx=self.restore(f);a=idx[f.a.entity_id]
        AP.end_scene(a,request_id='scene-one');self.assertEqual(a.spec['ap_spent'],1)

    def test_unknown_daily_usage_stays_unknown_and_changed_recovery_policy_rejects(self):
        f=self.fixture(2);mid=frequency_fixtures.DAILY;f.p.move_uses[mid]=1;f.p.spec['move_uses']=dict(f.p.move_uses)
        first=F.restore_daily_moves(f.e,f.p,request_id='native-rest')
        self.assertFalse(first['applied']);self.assertFalse(first['eligibility']['moves'][0]['eligible'])
        self.assertEqual(f.p.move_uses[mid],1)
        before=CODEC.dump_engine(f.e)
        with self.assertRaises(ValueError):F.restore_daily_moves(f.e,f.p,center=True,request_id='native-rest')
        self.assertEqual(before,CODEC.dump_engine(f.e))
        F.restore_daily_moves(f.e,f.p,center=True,request_id='native-center');self.assertNotIn(mid,f.p.move_uses)

    def test_old_form_end_never_ends_new_activation_and_save_checks_binding(self):
        f=self.fixture(3);TERA.observe_type(f.e,f.a,'불꽃',reason='actual permanent type')
        one=TERA.observe_active(f.e,f.a,True,reason='first')['episode_id']
        TERA.end_active(f.a,reason='encounter_end');two=TERA.observe_active(f.e,f.a,True,reason='second')['episode_id']
        self.assertNotEqual(one,two);TERA.end_active(f.a,reason='old reply',episode_id=one)
        self.assertTrue(TERA.tera_active(f.a));self.assertEqual(f.a.spec[EPISODES.KEY][one]['cause'],'encounter_end')
        self.restore(f);f.a.spec[TERA.KEY]['episode_id']=one
        with self.assertRaises(ValueError):CODEC.dump_engine(f.e)

    def test_old_sleep_reply_never_clears_current_sleep_origin(self):
        f=self.fixture(4);f.e.apply_status(f.t,'잠듦',source='item/꿈안개-1')
        one=f.t.spec[DREAM.KEY]['active']['episode_id'];f.e.cure_status(f.t,'잠듦')
        f.e.apply_status(f.t,'잠듦',source='move/최면술');two=f.t.spec[DREAM.KEY]['active']['episode_id']
        DREAM.cured(f.t,episode_id=one)
        self.assertEqual(f.t.spec[DREAM.KEY]['active']['episode_id'],two)
        self.assertEqual(f.t.spec[DREAM.KEY]['active']['source'],'move/최면술');self.restore(f)

    def test_state_cleanup_waits_for_exact_native_child_and_physical_end_runs_once(self):
        f=self.fixture(0);f.a.spec['items']={'붕대':1};f.p.injuries=1
        f.e.use_item(f.a,'붕대',f.p,duration_minutes=1,duration_reason='actual bandage')
        native=f.p.spec['bandages'][-1];calls=[]
        identity=EPISODES.start(f.p,family='external_state',source='external/state',native_ref={'slot':'observed'})
        def done(row):
            if not any(row is value for value in f.p.spec['bandages']):raise ValueError('actual native child required')
            return row['status']=='expired'
        end=lambda cause:EPISODES.end(f.p,identity,cause=cause,cleanup=lambda:calls.append('cleanup'),
            children=[native],child_complete=done,physical=lambda:calls.append('physical'))
        self.assertEqual(end('first end')['phase'],'waiting_children');self.assertEqual(calls,['cleanup'])
        e,idx=self.restore(f);episode=idx[f.p.entity_id].spec[EPISODES.KEY][identity]
        self.assertIs(episode['children'][0],idx[f.p.entity_id].spec['bandages'][-1])
        f.e.advance_time(21600,[f.p]);self.assertEqual(end('late reply')['phase'],'ended');end('again')
        self.assertEqual(calls,['cleanup','physical']);self.assertEqual(f.p.spec[EPISODES.KEY][identity]['cause'],'first end')

    def test_exact_clock_replay_does_not_advance_time_or_rng_after_later_time(self):
        f=self.fixture(5);first=f.e.advance_time(30,[f.a],request_id='clock-one',source='external/job-policy')
        f.e.advance_time(20,[f.a]);before=CODEC.dump_engine(f.e)
        self.assertEqual(f.e.advance_time(30,[f.a],request_id='clock-one',source='external/job-policy'),first)
        self.assertEqual(before,CODEC.dump_engine(f.e))
        with self.assertRaises(ValueError):f.e.advance_time(31,[f.a],request_id='clock-one',source='external/job-policy')
        e,idx=self.restore(f);before=CODEC.dump_engine(e)
        e.advance_time(30,[idx[f.a.entity_id]],request_id='clock-one',source='external/job-policy')
        self.assertEqual(before,CODEC.dump_engine(e))

    def test_clock_job_binding_rejects_an_equal_detached_work_record(self):
        f=self.fixture(5);f.start();f.work();row=f.e._activity_jobs['jobs']['job']['events'][-1]
        clock=f.e._clock_invocations[row['clock_invocation_id']]
        self.assertIs(clock['bindings'][0]['record'],row)
        e,idx=self.restore(f);restored=e._activity_jobs['jobs']['job']['events'][-1]
        self.assertIs(e._clock_invocations[restored['clock_invocation_id']]['bindings'][0]['record'],restored)
        clock['bindings'][0]['record']=deepcopy(row)
        with self.assertRaises(ValueError):CODEC.dump_engine(f.e)

    def test_timer_child_belongs_to_exact_clock_and_failure_rolls_back_everything(self):
        f=self.fixture(0);f.a.spec['items']={'붕대':1};f.p.injuries=1
        f.e.use_item(f.a,'붕대',f.p,duration_minutes=1,duration_reason='actual bandage')
        receipt=f.e.advance_time(21600,[f.p],request_id='expiry',source='external/timer')
        self.assertEqual(receipt['status'],'complete')
        native=f.p.spec['bandages'][-1];self.assertIs(f.e._clock_invocations['expiry']['children'][0]['record'],native)
        before=CODEC.dump_engine(f.e)
        def fail(e,c):e.rng.random();raise ValueError('late timer failure')
        with patch.object(BANDAGES,'advance',side_effect=fail):
            with self.assertRaises(ValueError):f.e.advance_time(1,[f.p],request_id='failed',source='external/timer')
        self.assertEqual(before,CODEC.dump_engine(f.e));self.assertNotIn('failed',f.e._clock_invocations)

    def test_origin_view_distinguishes_new_product_and_retained_repair(self):
        f=self.fixture(6);recipe,policy,result=f.made(seconds=200);identity='crafted:goggles'
        original=ORIGINS.read(f.e,identity)
        self.assertEqual(original['new_outputs'],[identity]);self.assertEqual(original['retained'],[])
        f.e._physical_objects[identity]['disabled']=True
        repaired=f.craft(recipe,product_policy={'mode':'repair','instance_ids':[identity],'owner_id':f.a.entity_id,'state':'intact','attachments':[]},event_id='repair-one')
        repair=ORIGINS.read(f.e,identity,production_id=repaired['production_id'])
        self.assertEqual(repair['new_outputs'],[]);self.assertEqual(repair['retained'],[identity]);self.assertEqual(repair['kind'],'repair')
        self.assertEqual(ORIGINS.read(f.e,identity),original)
        e,idx=self.restore(f);self.assertEqual(ORIGINS.read(e,identity,production_id=repaired['production_id']),repair)

    def test_fossil_birth_origin_reads_the_actual_fossil_egg_and_child(self):
        f=self.fixture(7);egg=f.default()['egg'];child=f.hatch(egg)['pokemon']
        view=ORIGINS.read(f.e,child.entity_id)
        self.assertEqual(view['inputs'],[f.fossil['entity_id'],egg['entity_id']]);self.assertEqual(view['new_outputs'],[child.entity_id])
        e,idx=self.restore(f);self.assertEqual(ORIGINS.read(e,child.entity_id),view)
        child.spec['egg_entity_id']='egg/forged'
        with self.assertRaises(ValueError):ORIGINS.read(f.e,child.entity_id)

    def test_product_origin_keeps_the_actual_consumed_physical_input(self):
        f=self.fixture(6);recipe=f.ready();recipe['materials']=[f.ingredient()]
        recipe['output']={'item_id':'item/방진고글','key':'item/방진고글'}
        f.craft(recipe,inputs={'ingredient':{'option':0,'scrap_value':0,'instances':['real:ingredient']}},
                product_policy=f.policy(),event_id='physical-input')
        origin=ORIGINS.read(f.e,'crafted:goggles')
        self.assertEqual(origin['inputs'],['real:ingredient']);self.assertEqual(origin['new_outputs'],['crafted:goggles'])
        self.assertIn('consumed',f.e._physical_objects['real:ingredient']);self.restore(f)


if __name__=='__main__':unittest.main()
