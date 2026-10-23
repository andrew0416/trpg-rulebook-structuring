"""Native mounted bodies and one shared pool consume abstract place travel."""
from copy import deepcopy
import json,unittest
from unittest.mock import patch
import test_mapless_space as BASE,test_mapless_environment as ENV
import control_mount as M,world_entities as W,turn as TURN
from state_codec import load_engine

class Tests(unittest.TestCase):
    setUpClass=classmethod(BASE.MaplessTests.setUpClass.__func__)
    setUp=BASE.MaplessTests.setUp;actor=BASE.MaplessTests.actor
    configure=BASE.MaplessTests.configure;snap=BASE.MaplessTests.snap
    def mounted(self,*,owner='mover',contacts=None,second=False):
        self.b.side='party';self.placements[self.b.entity_id]='stairs'
        self.configure(contacts)
        self.a.kind=self.a.spec['kind']='trainer';self.a.spec['edges']=['edge/탑승-기량']
        self.a.spec['skills']={'곡예':6,'육상':6}
        self.policy=M.native_declaration('곡예');self.policy['movement']['action_owner']=owner
        self.assertTrue(self.e.board_mount(self.a,self.b,self.policy,gm_mountable=True)['passed'])
        if second:
            self.placements[self.d.entity_id]='stairs';self.configure(contacts)
            self.d.kind=self.d.spec['kind']='trainer';self.d.spec['edges']=['edge/탑승-기량'];self.d.spec['skills']={'곡예':3}
            TURN.reset_budget(self.e,self.d)
            self.assertTrue(self.e.board_mount(self.d,self.b,self.policy,gm_mountable=True)['passed'])
        TURN.reset_budget(self.e,self.a);TURN.reset_budget(self.e,self.b)

    def travel(self,actor=None,*,destination='fountain',cost=2,event='ride'):
        actor=actor or self.a
        self.e.gm.observe_mapless_movement(actor,event_id=event,destination=destination,movement_cost=cost,
            contacts_after=[],reason='GM observes actual mounted travel cost and final contacts')
        return self.e.move_abstract(actor,event_id=event)

    def test_rider_and_mount_use_one_actual_pool_and_move_all_bodies(self):
        self.mounted();self.assertEqual(self.travel()['phase'],'complete')
        self.assertEqual((getattr(self.b,M.POOL)['used'],self.a.budget['shift'],self.b.budget['shift']),(2,0,1))
        for c in (self.a,self.b):self.assertEqual(W.location_of(c)['place_id'],'fountain')
        TURN.reset_budget(self.e,self.b)
        self.e.gm.observe_mapless_movement(self.b,event_id='too-far',destination='corridor',movement_cost=3,contacts_after=[],reason='observed remaining journey')
        before=self.snap()
        with self.assertRaisesRegex(ValueError,'allowance'):self.e.move_abstract(self.b,event_id='too-far')
        self.assertEqual(before,self.snap())
        self.travel(self.b,destination='corridor',event='mount-turn');self.assertEqual(getattr(self.b,M.POOL)['used'],4)
        self.assertEqual(self.a._action_history,['standard','shift']);self.assertEqual(self.b._action_history,['shift'])
        for c in (self.a,self.b):self.assertEqual(W.location_of(c)['place_id'],'corridor')

    def test_declared_mount_action_owner_and_multiple_passengers(self):
        self.mounted(owner='mount',second=True);self.d.hp=0
        result=self.travel();self.assertEqual(result['phase'],'complete')
        self.assertEqual((self.a.budget['shift'],self.b.budget['shift']),(1,0))
        self.assertEqual(self.a._action_history,['standard']);self.assertEqual(getattr(self.b,M.POOL)['used'],2)
        for c in (self.a,self.b,self.d):self.assertEqual(W.location_of(c)['place_id'],'fountain')
        before=self.snap();self.assertEqual(result,self.e.move_abstract(self.a,event_id='ride'));self.assertEqual(before,self.snap())

    def test_actual_group_both_restores_preserve_shared_remaining_and_payment(self):
        self.mounted();self.assertEqual(self.travel()['phase'],'complete')
        saved=self.e.gm.snapshot();export=json.loads(json.dumps(self.snap(),ensure_ascii=False))
        for restored in (load_engine(self.r,deepcopy(export)),self.e):
            if restored is self.e:self.e.gm.restore(saved)
            actors=W.actor_index(restored);a,b=actors[self.a.entity_id],actors[self.b.entity_id]
            self.assertIs(W.mount_relation(actors,a),b);self.assertIs(getattr(b,M.RIDERS)[0],a)
            before=restored.export_state();paid=deepcopy(a.budget);hp=b.hp;rng=restored.rng.getstate()
            self.assertEqual(restored.move_abstract(a,event_id='ride')['phase'],'complete')
            self.assertEqual(a.budget,paid);self.assertEqual(b.hp,hp);self.assertEqual(restored.rng.getstate(),rng)
            self.assertEqual(getattr(b,M.POOL)['used'],2)
            for c in (a,b):self.assertEqual(W.location_of(c)['place_id'],'fountain')
            self.assertEqual(before,restored.export_state())
            TURN.reset_budget(restored,b)
            restored.gm.observe_mapless_movement(b,event_id='next',destination='corridor',movement_cost=3,contacts_after=[],reason='actual shared remaining')
            before=restored.export_state()
            with self.assertRaisesRegex(ValueError,'allowance'):restored.move_abstract(b,event_id='next')
            self.assertEqual(before,restored.export_state())

    def test_native_retention_loss_stops_paid_group_without_refund_or_transport(self):
        self.mounted(contacts=[[self.b.entity_id,self.c.entity_id]])
        self.c.stats['atk']+=20;self.c.spec['stats']['atk']=self.c.stats['atk']
        before_hp=self.b.hp
        self.e.rng.seed(5);original=M.retain
        def fixed(e,rider,**options):return original(e,rider,roll_options={'fixed':[1]*6},**options)
        with patch.object(M,'retain',side_effect=fixed):result=self.travel()
        self.assertEqual(result['phase'],'stopped');self.assertTrue(self.c.aoo_used)
        self.assertGreaterEqual(before_hp-self.b.hp,self.b.base_max_hp/4)
        self.assertNotIn('mount_id',self.a.spec);self.assertEqual(self.a.budget['shift'],0)
        self.assertEqual(self.a.custom_conditions['mount_retention_history'][-1]['event'],'damage')
        self.assertEqual(getattr(self.b,M.POOL)['used'],0)
        for c in (self.a,self.b):self.assertEqual(W.location_of(c)['place_id'],'stairs')

    def test_actual_donor_knockout_stops_after_the_real_departure_attack(self):
        self.mounted(contacts=[[self.b.entity_id,self.c.entity_id]])
        self.b.hp=1;self.e.rng.seed(6);result=self.travel()
        self.assertEqual(result['phase'],'stopped');self.assertTrue(self.b.fainted);self.assertTrue(self.c.aoo_used)
        self.assertEqual(self.a.budget['shift'],0);self.assertEqual(getattr(self.b,M.POOL)['used'],0)
        before=self.snap();self.assertEqual(result,self.e.move_abstract(self.a,event_id='ride'));self.assertEqual(before,self.snap())

    def test_late_group_location_failure_preserves_all_bodies_pool_budget_hp_and_rng(self):
        self.mounted(contacts=[[self.b.entity_id,self.c.entity_id]])
        self.e.gm.observe_mapless_movement(self.a,event_id='ride',destination='fountain',movement_cost=2,contacts_after=[],reason='actual transport')
        self.e.rng.seed(6);before=self.snap();original=W.observe_location;seen=[]
        def fail(e,c,*args,**options):
            out=original(e,c,*args,**options);seen.append(c.entity_id)
            if len(seen)==2:raise ValueError('late actual passenger location failure')
            return out
        with patch.object(W,'observe_location',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'late actual passenger'):self.e.move_abstract(self.a,event_id='ride')
        self.assertEqual(before,self.snap());self.assertFalse(getattr(self.c,'aoo_used',False))

    def test_all_actual_carried_environments_enter_together(self):
        self.mounted();ENV.Tests.environment(self,air_available=False,medium='water')
        policy=json.loads((BASE.ROOT/'data/examples/environment-derive.json').read_text(encoding='utf8'))
        policy['rules']=[row for row in policy['rules'] if row['family']!='terrain']
        self.e.bind_environment(self.b,policy,region_id='dry',reason='actual mount environment baseline')
        self.e.gm.observe_mapless_movement(self.a,event_id='ride',destination='fountain',movement_cost=2,contacts_after=[],timing_policy='grace_boundary',reason='actual group immersion')
        self.assertEqual(self.e.move_abstract(self.a,event_id='ride')['phase'],'complete')
        for c in (self.a,self.b):
            self.assertEqual(self.e.environment_context(c)['region_id'],'entry')
            self.assertFalse(c.spec['_respiration']['breathing']);self.assertEqual(W.location_of(c)['place_id'],'fountain')

if __name__=='__main__':unittest.main()
