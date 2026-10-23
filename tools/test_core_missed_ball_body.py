"""C05-157's actual projectile, observed landing and native consumers."""
from pathlib import Path
from copy import deepcopy
import json,unittest
from unittest.mock import patch
from engine import Rules,Engine,Combatant
from grid import Grid
import common_checks as C
import missed_ball_body as B
import world_entities as W
import map_terrain as TERRAIN
import items as I
import item_stock as STOCK
import csv_item_physical_contracts as CSV
import pokemon_activities as P
import state_codec as CODEC
import test_category2_csv_remaining_item_contracts as FIX

ROOT=Path(__file__).resolve().parents[1]


class MissedBallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        self.r=self.rules;self.e=Engine(self.r,seed=157)
        def actor(name,kind,pos):
            return Combatant(self.r,{'id':kind+'/'+name,'name':name,'kind':kind,'level':20,'pos':pos,
                'stats':{'hp':40,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},
                'skills':{'육상':'숙련','기술학':'숙련'},'items':{},'edges':[],'feats':[]})
        self.a=actor('thrower','trainer',(1,1));self.t=actor('target','pokemon',(4,1))
        self.t.side='wild';self.t.spec.update(wild=True,side='wild')
        self.e.gm.everyone=self.e.everyone=[self.a,self.t];self.e.grid=Grid(24,12)
        for c in self.e.everyone:self.e.gm.set_footprint(c,[(0,0)],reason='actual observed one-cell body')
        self.a.spec['items']['몬스터볼']=1
        TERRAIN.observe(self.e,[(8,1),(9,2),(14,1),(18,1)],base='regular',reason='actual GM observed ground')
        self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a,initiative_count=20)
    def throw(self,**kw):return self.e.throw_ball(self.a,self.t,**dict({'fixed_accuracy':1,'fixed_capture':1},**kw))
    def attempt(self):return self.a.spec['capture_attempts']['capture-'+str(self.a.spec['capture_attempt_serial'])]
    def ball(self):return self.e._physical_objects[self.attempt()['physical_instance_id']]
    def observe(self,**kw):return self.e.gm.observe_missed_ball_ground(self.a,**dict({'attempt_id':self.attempt()['id'],'cell':(8,1),'intact':True,'reason':'GM sees this same ball land behind the original target'},**kw))
    def recover(self):return self.e.pokemon_activity(self.a,'observe_ball',attempt_id=self.attempt()['id'],condition='recovered_intact',reason='GM retrieves this actual landed ball')
    def next_turn(self):
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a,initiative_count=20)
    def snap(self):
        return deepcopy((self.a.spec,self.a.budget,self.t.spec,self.t.hp,
            getattr(self.e,'_physical_objects',{}),self.e.log_lines,self.e.rulings.log,self.e.rng.getstate()))
    def test_quantity_native_miss_becomes_one_actual_body_then_held_rethrow_uses_it_once(self):
        self.assertFalse(self.throw());attempt=self.attempt();obj=self.ball();uid=obj['id']
        self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.spec['items']['몬스터볼'],0)
        self.assertEqual(W.location_of(obj),{'kind':'unknown'});self.assertTrue(obj['ball_integrity']['intact'])
        self.assertEqual(attempt['landing']['status'],'pending');self.assertIsInstance(self.recover(),C.PendingDecision)
        self.observe(cell=(9,2));self.assertEqual(W.location_of(obj),{'kind':'grid','cell':(9,2)})
        self.assertEqual(self.recover()['physical_instance_id'],uid);self.assertEqual(self.a.spec['items']['몬스터볼'],0)
        self.assertEqual(W.location_of(obj),W.location_of(self.a))
        with self.assertRaises(ValueError):self.recover()
        I.register_item(self.e,self.a,obj['item_rule_id'],source_instance_id=uid,as_held=True)
        self.assertIs(STOCK.inspect_held(self.e,self.a,obj['item_rule_id'],uid),obj)
        self.next_turn();self.assertTrue(self.throw(physical_instance_id=uid,fixed_accuracy=20,fixed_capture=20))
        self.assertEqual(self.attempt()['physical_instance_id'],uid);self.assertEqual(len(self.e._physical_objects),1)
        self.assertTrue(obj['consumed']);self.assertNotIn('equipped_by',obj)
        self.assertEqual(self.a.spec['items']['몬스터볼'],0)
        cold=CODEC.load_engine(Rules(str(ROOT),ruleset='core'),json.loads(json.dumps(CODEC.dump_engine(self.e))))
        self.assertTrue(cold._physical_objects[uid]['consumed'])
        self.assertEqual(len(cold._physical_objects),1)
    def test_recovered_quantity_body_loads_and_misses_from_cannon_without_a_second_ball(self):
        self.throw();self.observe();self.recover();uid=self.ball()['id']
        f=FIX.RemainingCsvItemContractTests();f.r=self.r
        f.equip(self.e,self.a,'miss/cannon','item/몬스터볼-캐논',held=False)
        self.next_turn();CSV.load_cannon(self.e,self.a,'miss/cannon',uid)
        with self.assertRaisesRegex(ValueError,'loaded'):self.throw(physical_instance_id=uid)
        self.assertFalse(self.throw(cannon_instance_id='miss/cannon'));self.assertEqual(self.attempt()['physical_instance_id'],uid)
        self.assertEqual(self.attempt()['cannon']['ball_instance_id'],uid)
        self.assertEqual(W.location_of(self.ball()),{'kind':'unknown'});self.assertEqual(self.a.spec['items']['몬스터볼'],0)
        self.assertIsInstance(self.recover(),C.PendingDecision);self.observe();self.recover()
        self.assertEqual(len([o for o in self.e._physical_objects.values() if o.get('item_rule_id')=='item/몬스터볼-2']),1)
        self.next_turn();self.assertTrue(CSV.load_cannon(self.e,self.a,'miss/cannon',uid)['loaded'])
    def test_original_throw_direction_and_real_map_terrain_gate_ground_without_guessing_distance(self):
        self.throw();before=self.snap();self.t.pos=(0,1)
        for cell in ((2,1),(4,1),(4,7)):
            with self.assertRaisesRegex(ValueError,'behind'):self.observe(cell=cell)
        self.assertEqual(self.snap(),before)
        self.assertIsInstance(self.observe(cell=(7,1)),C.PendingDecision)
        self.assertEqual(W.location_of(self.ball()),{'kind':'unknown'})
        self.observe(cell=(9,2));self.assertEqual(self.attempt()['throw_target']['cell'],(4,1))
        self.assertEqual(self.attempt()['landing']['cell'],[9,2])
    def test_unknown_and_exceptional_ground_require_actual_landing_and_integrity(self):
        self.throw();grid=self.e.grid;self.e.grid=None
        self.assertIsInstance(self.observe(),C.PendingDecision);self.e.grid=grid
        self.assertIsInstance(self.observe(intact=None),C.PendingDecision)
        old=grid._tunnel_map_id;grid._tunnel_map_id='different-map'
        with self.assertRaisesRegex(ValueError,'original throw map'):self.observe()
        grid._tunnel_map_id=old
        TERRAIN.observe(self.e,[(8,1)],base='underwater',blocking=True,reason='GM observed exceptional water behind a wall')
        self.assertIsInstance(self.recover(),C.PendingDecision)
        self.observe(intact=False,reason='GM actually sees the same projectile damaged on the exceptional landing')
        self.assertFalse(self.ball()['ball_integrity']['intact']);self.assertTrue(self.ball()['disabled'])
        with self.assertRaisesRegex(ValueError,'broken'):self.recover()
        with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'observe_ball',attempt_id=self.attempt()['id'],condition='broken',reason='terrain damage is not failed-capture repair eligibility')
        self.assertNotIn('broken_balls',self.a.spec)
        self.setUp();self.e.grid.base_terrain={};self.e.grid.terrain_observations={};del self.e.grid._tunnel_map_id
        self.throw();self.assertTrue(self.attempt()['throw_map_id'])
        self.assertIsInstance(self.observe(),C.PendingDecision)
        TERRAIN.observe(self.e,[(8,1)],base='regular',reason='actual ground observed only after this throw')
        self.observe();self.assertEqual(self.attempt()['landing']['status'],'observed')
    def test_launch_fault_after_actual_object_ruling_and_miss_writes_rolls_back_the_native_throw(self):
        before=self.snap();original=B.miss
        def fail(*args):
            original(*args);self.assertTrue(args[0]._physical_objects);self.assertTrue(args[0].rulings.log)
            raise ValueError('after actual missed body writes')
        with patch.object(B,'miss',side_effect=fail),self.assertRaisesRegex(ValueError,'actual missed body'):self.throw()
        self.assertEqual(self.snap(),before)
        self.throw();self.assertEqual(self.a.spec['capture_attempt_serial'],1)
    def test_ground_fault_after_actual_gm_record_rolls_back_both_logs_and_physical_state(self):
        self.throw();before=self.snap();original=type(self.e.gm)._rec
        def fail(gm,*args,**kw):
            result=original(gm,*args,**kw)
            if args[0].startswith('missed ball '):raise ValueError('after actual GM ground ruling')
            return result
        with patch.object(type(self.e.gm),'_rec',new=fail),self.assertRaisesRegex(ValueError,'actual GM ground'):self.observe()
        self.assertEqual(self.snap(),before);self.observe()
    def test_recovery_fault_after_real_body_move_keeps_ground_and_retry_returns_same_body_once(self):
        self.throw();self.observe();before=self.snap();original=B.recover
        def fail(*args):
            result=original(*args);self.assertEqual(W.location_of(args[0]._physical_objects[self.ball()['id']]),W.location_of(args[1]))
            raise ValueError('after actual recovery move')
        with patch.object(B,'recover',side_effect=fail),self.assertRaisesRegex(ValueError,'actual recovery move'):self.recover()
        self.assertEqual(self.snap(),before);uid=self.ball()['id'];self.assertEqual(self.recover()['physical_instance_id'],uid)
    def test_failed_capture_repair_consumes_the_same_quantity_origin_body_on_both_outcomes(self):
        for repaired in (True,False):
            with self.subTest(repaired=repaired):
                self.setUp();self.throw(fixed_accuracy=20);uid=self.ball()['id'];obj=self.ball()
                self.e.end_encounter([self.a,self.t])
                self.a.spec['edges']=[P.FEATURES[n][0] for n in ('repair','basic_balls')]
                self.a.spec['items']['몬스터볼 공구함']=1
                self.e.pokemon_activity(self.a,'observe_ball',attempt_id=self.attempt()['id'],condition='broken',reason='GM inspects this actual failed-capture body')
                self.assertEqual(self.a.spec['broken_balls'][self.attempt()['id']]['physical_instance_id'],uid)
                out=self.e.pokemon_activity(self.a,'repair_ball',ball_id=self.attempt()['id'],fixed=[6]*4 if repaired else [1]*4)
                self.assertEqual(out['status'],'repaired' if repaired else 'permanently_broken')
                self.assertEqual(self.a.spec['items']['몬스터볼'],0);self.assertIs(self.e._physical_objects[uid],obj)
                if repaired:self.assertEqual(W.location_of(obj),W.location_of(self.a));self.assertNotIn('disabled',obj)
                else:self.assertTrue(obj['destroyed'])
                with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'repair_ball',ball_id=self.attempt()['id'],fixed=[6]*4)
    def test_repair_tail_fault_after_actual_same_ball_recovery_does_not_commit_physical_or_status_writes(self):
        self.throw(fixed_accuracy=20);self.e.end_encounter([self.a,self.t])
        self.a.spec['edges']=[P.FEATURES[n][0] for n in ('repair','basic_balls')]
        self.a.spec['items']['몬스터볼 공구함']=1
        self.e.pokemon_activity(self.a,'observe_ball',attempt_id=self.attempt()['id'],condition='broken',reason='actual failed-capture broken body')
        before=deepcopy((self.a.spec,self.e._physical_objects));original=B.recover
        def fail(*args):
            result=original(*args);self.assertTrue(result)
            raise ValueError('after actual repair recovery')
        with patch.object(B,'recover',side_effect=fail),self.assertRaisesRegex(ValueError,'actual repair recovery'):
            self.e.pokemon_activity(self.a,'repair_ball',ball_id=self.attempt()['id'],fixed=[6]*4)
        self.assertEqual((self.a.spec,self.e._physical_objects),before)
        self.assertEqual(self.e.pokemon_activity(self.a,'repair_ball',ball_id=self.attempt()['id'],fixed=[6]*4)['status'],'repaired')
    def test_gm_and_cold_restore_keep_pending_observed_and_recovered_same_body(self):
        self.throw();uid=self.ball()['id'];self.e.gm.snapshot('pending')
        self.observe();self.recover();self.e.gm.restore('pending',reason='actual rewind of this throw')
        self.assertEqual(W.location_of(self.ball()),{'kind':'unknown'});self.assertIsInstance(self.recover(),C.PendingDecision)
        self.observe();self.e.gm.snapshot('ground');self.recover();self.e.gm.restore('ground',reason='actual ground rewind')
        saved=json.loads(json.dumps(CODEC.dump_engine(self.e)))
        cold=CODEC.load_engine(Rules(str(ROOT),ruleset='core'),saved)
        a=next(a for a in cold.gm.everyone if a.entity_id==self.a.entity_id)
        self.assertEqual(a.spec['capture_attempts']['capture-1']['physical_instance_id'],uid)
        cold.pokemon_activity(a,'observe_ball',attempt_id='capture-1',condition='recovered_intact',reason='same physical ball after cold restore')
        self.assertEqual(a.spec['items']['몬스터볼'],0);self.assertEqual(W.location_of(cold._physical_objects[uid]),W.location_of(a))
        again=CODEC.load_engine(cold.r,json.loads(json.dumps(CODEC.dump_engine(cold))))
        restored=next(a for a in again.gm.everyone if a.entity_id==self.a.entity_id)
        with self.assertRaises(ValueError):again.pokemon_activity(restored,'observe_ball',attempt_id='capture-1',condition='recovered_intact',reason='duplicate after cold restore')
        self.e._physical_objects[uid]['ball_integrity']['intact']=False
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
    def test_selected_source_version_and_warm_source_changes_refuse_before_body_or_ground_writes(self):
        before=self.snap()
        with patch.dict(self.r.ruleset.unit_versions,{B.SOURCE:'unreviewed-version'}),self.assertRaises(ValueError):self.throw()
        self.assertEqual(self.snap(),before)
        self.throw();before=self.snap();original=Path.read_bytes
        def changed(path):
            raw=original(path)
            return raw+b'changed' if path.name=='ch05-pokemon.md' else raw
        with patch.object(Path,'read_bytes',new=changed),self.assertRaises(ValueError):self.observe()
        self.assertEqual(self.snap(),before)
        self.observe();before=self.snap()
        with patch.object(Path,'read_bytes',new=changed),self.assertRaises(ValueError):self.recover()
        self.assertEqual(self.snap(),before)
    def test_legacy_quantity_alias_still_realizes_one_ball_without_an_inventory_refund(self):
        self.a.spec['items']={'poke_ball':1};self.throw();uid=self.ball()['id']
        self.assertEqual(self.a.spec['items'],{'poke_ball':0});self.observe();self.recover()
        self.assertEqual(self.a.spec['items'],{'poke_ball':0});self.assertEqual(self.ball()['id'],uid)
        self.setUp();self.e.end_encounter([self.a,self.t]);self.a.spec.update(items={},money=250)
        self.e.campaign_reward(self.a,'observe_ball_shop',event_id='actual-stock',merchant='Mart',
            stock={'item/몬스터볼-2':1},reason='GM observes the actual ball product for this throw')
        self.e.campaign_reward(self.a,'purchase',event_id='actual-sale',merchant='Mart',
            items={'item/몬스터볼-2':1},reason='actual purchased ball for the native throw')
        self.assertEqual(self.a.spec['items'],{'item/몬스터볼-2':1})
        self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a,initiative_count=20)
        self.assertFalse(self.throw());uid=self.ball()['id'];self.assertEqual(self.ball()['item_rule_id'],'item/몬스터볼-2')
        self.assertEqual(self.a.spec['items'],{'item/몬스터볼-2':0});self.observe();self.recover()
        self.assertEqual(self.ball()['id'],uid);self.assertEqual(self.a.spec['items'],{'item/몬스터볼-2':0})


if __name__=='__main__':unittest.main()
