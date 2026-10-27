"""Observed abstract travel consumes actual native environmental entry facts."""
from copy import deepcopy
import json,unittest
from unittest.mock import patch
import test_mapless_space as BASE
import test_mapless_departure as DEPARTURE
import environment_change as EC,environment_derive as ED,movement_actions as MOVE
import state_grants as G,world_entities as W,turn as TURN,stamina as STAMINA
from gameplay_validation import WorldIntegrityError
from state_codec import load_engine

class Tests(unittest.TestCase):
    setUpClass=classmethod(BASE.MaplessTests.setUpClass.__func__)
    setUp=BASE.MaplessTests.setUp
    actor=BASE.MaplessTests.actor;configure=BASE.MaplessTests.configure
    movement=BASE.MaplessTests.movement;snap=BASE.MaplessTests.snap
    native_pending=DEPARTURE.Tests.native_pending

    def environment(self,*,contacts=None,**destination):
        self.configure(contacts)
        policy=json.loads((BASE.ROOT/'data/examples/environment-derive.json').read_text(encoding='utf8'))
        policy['rules']=[row for row in policy['rules'] if row['family']!='terrain']
        self.source=policy['source']
        for region,changes in [('dry',{}),('entry',destination),('far',destination)]:
            facts=dict(gravity=1,pressure=1,air_available=True,medium='air');facts.update(changes)
            self.e.observe_environment(region,facts,source=self.source,reason='actual observed environment')
        self.e.bind_environment(self.a,policy,region_id='dry',reason='actual unmapped actor baseline')
        self.regions=dict(stairs='dry',fountain='entry',corridor='far')
        self.e.gm.observe_mapless_scene(scene_id='lobby',places=self.places,placements=self.placements,
            contacts=contacts or [],reason='GM relates observed places to actual environment regions',environment_regions=self.regions)

    def travel(self,destination='fountain',event='walk',**options):
        self.e.gm.observe_mapless_movement(self.a,event_id=event,destination=destination,movement_cost=1,
            contacts_after=[],reason='actual observed travel',**options)
        return self.e.move_abstract(self.a,event_id=event)

    def test_entry_consumes_actual_pressure_gravity_and_native_movement(self):
        self.environment(gravity=2,pressure=0)
        self.assertEqual(MOVE.capabilities(self.e,self.a)['land'],4)
        result=self.travel()
        self.assertEqual(result['phase'],'complete');self.assertEqual(W.location_of(self.a)['place_id'],'fountain')
        self.assertEqual(self.e.environment_context(self.a)['region_id'],'entry')
        self.assertEqual(MOVE.capabilities(self.e,self.a)['land'],2)
        self.assertEqual(ED.derive(self.e,self.a,'skill','생존',0)['value'],-5)
        self.assertEqual(self.a.movement,4);self.assertEqual(self.a._action_history,['shift'])
        before=self.snap();self.assertEqual(result,self.e.move_abstract(self.a,event_id='walk'));self.assertEqual(before,self.snap())

    def test_actual_water_entry_native_clock_and_air_recovery_preserve_protected_injury(self):
        self.environment(air_available=False,medium='water')
        self.travel(timing_policy='grace_boundary');self.assertFalse(self.a.spec['_respiration']['breathing'])
        self.e.advance_time(60);self.assertEqual(self.a.injuries,1)
        TURN.reset_budget(self.e,self.a);self.travel('stairs','return')
        self.assertTrue(self.a.spec['_respiration']['breathing'])
        self.assertEqual(self.a.injuries,0)
        self.e.advance_time(60);self.assertEqual(self.a.injuries,0)

    def test_same_deprivation_crosses_regions_without_restart_and_both_restore(self):
        self.environment(air_available=False,medium='water')
        self.travel(timing_policy='grace_boundary');self.e.advance_time(30)
        previous=deepcopy(self.a.spec['_respiration']);TURN.reset_budget(self.e,self.a)
        self.travel('corridor','second');self.assertEqual(self.a.spec['_respiration'],previous)
        saved=self.e.gm.snapshot();export=json.loads(json.dumps(self.snap(),ensure_ascii=False))
        for restored in (load_engine(self.r,deepcopy(export)),self.e):
            if restored is self.e:self.e.gm.restore(saved)
            actor=next(c for c in restored.everyone if c.entity_id==self.a.entity_id)
            self.assertEqual(restored.environment_context(actor)['region_id'],'far')
            restored.advance_time(30);self.assertEqual(actor.injuries,1)

    def test_actual_departure_wait_keeps_origin_environment_until_resume(self):
        self.a.kind=self.a.spec['kind']='trainer';self.a.spec['edges']=[STAMINA.SOURCE]
        self.a.spec['skills']={'Athletics':5,'Acrobatics':4,'Combat':6}
        self.environment(contacts=[[self.a.entity_id,self.b.entity_id]],air_available=False,medium='water')
        self.e.rng.seed(5);self.assertEqual(self.travel(timing_policy='grace_boundary')['phase'],'pending')
        self.assertEqual(ED.context(self.e,self.a)['region_id'],'dry')
        paid=deepcopy(self.a.budget);hp=self.a.hp;rng=self.e.rng.getstate()
        self.e.resolve_stamina(self.a,self.native_pending(),skill='육상')
        self.assertEqual(self.e.move_abstract(self.a,event_id='walk')['phase'],'complete')
        self.assertEqual(ED.context(self.e,self.a)['region_id'],'entry')
        self.assertFalse(self.a.spec['_respiration']['breathing'])
        self.assertEqual(self.a.budget,paid);self.assertEqual(self.a.hp,hp);self.assertEqual(self.e.rng.getstate(),rng)

    def test_late_entry_failure_rolls_back_real_departure_environment_and_payment(self):
        self.environment(contacts=[[self.a.entity_id,self.b.entity_id]],gravity=2)
        self.movement(1);self.e.rng.seed(6);before=self.snap();original=EC.transfer
        def fail(*args,**options):
            original(*args,**options);raise ValueError('late actual environment entry failure')
        with patch.object(EC,'transfer',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'late actual'):self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(self.snap(),before);self.assertFalse(getattr(self.b,'aoo_used',False))
        self.assertEqual(self.e.move_abstract(self.a,event_id='walk')['phase'],'complete')

    def test_unknown_destination_atmosphere_refuses_before_cost_or_reaction(self):
        self.environment(contacts=[[self.a.entity_id,self.b.entity_id]],air_available=None)
        self.movement(1);before=self.snap()
        with self.assertRaisesRegex(ValueError,'known atmospheric'):self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(before,self.snap());self.assertFalse(getattr(self.b,'aoo_used',False))

    def test_actual_origin_mismatch_refuses_and_binding_cannot_change_or_be_tampered(self):
        self.environment();self.movement(1)
        self.e.transfer_environment(self.a,'far',reason='actual external transfer');before=self.snap()
        with self.assertRaisesRegex(ValueError,'mapless origin'):self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(before,self.snap())
        with self.assertRaisesRegex(ValueError,'replacing its environment'):
            self.e.gm.observe_mapless_scene(scene_id='lobby',places=self.places,placements=self.placements,contacts=[],
                reason='cannot silently replace place environment',environment_regions=dict(self.regions,fountain='far'))
        saved=self.e.gm.snapshot();before=self.snap()
        self.e.gm.snapshots[saved]['engine']['_mapless_space']['environment']['places']['fountain']='far'
        with self.assertRaisesRegex(WorldIntegrityError,r'^world reference integrity: mapless_space \(mapless spatial observation changed\)$'):self.e.gm.restore(saved)
        self.assertEqual(before,self.snap())

    def test_actual_gills_use_water_and_bound_actor_requires_observed_places(self):
        self.environment(air_available=False,medium='water')
        G.grant(self.a,'capabilities','Gilled','test:gills','actual sourced water breathing')
        self.travel();self.assertTrue(self.a.spec['_respiration']['breathing'])
        self.e.advance_time(120);self.assertEqual(self.a.injuries,0)
        self.e.end_scene();self.configure();self.movement(1);before=self.snap()
        with self.assertRaisesRegex(ValueError,'both actual mapless'):self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(before,self.snap())

if __name__=='__main__':unittest.main()
