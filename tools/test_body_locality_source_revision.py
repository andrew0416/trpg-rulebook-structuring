"""Changed native body/range/entry boundaries only; prepared without imports or runs."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import os
import sys
import unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT=STAGE if (STAGE/'data/core-rules.json').exists() else Path(os.environ.get(
    'PTK_CANONICAL_ROOT',r'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository'))
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(STAGE/'tools'),str(ROOT/'tools')]
from engine import Rules
import body_state as BODY
import condition_instances as CONDITIONS
import forced_movement as FORCED
import hazard_state as HAZARDS
import ice_lake as ICE
import map_terrain as MAP
import movement_actions as MOVE
import native_scenario_fixture as NATIVE
import nicolette_gym as NICOLETTE
import native_switch_transfer as SWITCH
import turn as TURN
import world_entities as WORLD
import test_category3_manipulate as MANIPULATE
import test_category2_telekinetic_load as TELEKINETIC
import test_category2_hazard_state as HAZARD
import test_reuse_partial_party as PARTY
import test_category2_core_g041_g045_g050 as TERRAIN
import test_native_switch_transfer_revision as SWITCH_FIXTURE


def _rules(cls):
    cls.r=Rules(str(ROOT),ruleset='core')


class ManipulateBodyTests(unittest.TestCase):
    setUpClass=classmethod(_rules)
    setUp=MANIPULATE.ManipulateTests.setUp
    actor=MANIPULATE.ManipulateTests.actor
    begin=MANIPULATE.ManipulateTests.begin
    options=MANIPULATE.ManipulateTests.options
    perform=MANIPULATE.ManipulateTests.perform

    def test_native_manipulate_uses_nearest_body_square_and_an_unblocked_body_line(self):
        self.a.pos=(7,1);self.t.pos=(0,1)
        BODY.observe(self.e,self.t,[(0,0),(1,0),(0,1),(1,1)],reason='actual two by two target')
        self.e.grid.blocking.update((3,y) for y in range(5))
        self.begin()
        NATIVE.assert_rejected_unchanged(self.e,lambda:self.perform(),
            reason_pattern='visible on-field target within six')
        self.e.grid.blocking.remove((3,2))
        self.assertTrue(self.e.grid.blocked(self.a.pos,self.t.pos))
        self.assertTrue(self.perform())
        self.assertEqual(self.a.budget['standard'],0)
        self.assertIn('난동',self.t.conditions)


class TelekineticBodyTests(unittest.TestCase):
    setUpClass=classmethod(_rules)
    setUp=TELEKINETIC.Tests.setUp
    actor=TELEKINETIC.Tests.actor
    turn=TELEKINETIC.Tests.turn

    def test_native_remote_lift_and_path_use_current_body_edge_and_keep_outside_rejection_atomic(self):
        BODY.observe(self.e,self.a,[(0,0),(1,0)],reason='actual extended caster footprint')
        WORLD.register_object(self.e,'body-edge-object',location={'kind':'grid','cell':(10,2)},
            weight_kg=1,reason='eight metres from body edge, nine from token')
        self.turn()
        self.assertEqual(self.e.telekinetic_lift(self.a,['body-edge-object'],action_cost='shift',
            reason='actual body-edge remote lift')['weight_kg'],1)
        NATIVE.assert_rejected_unchanged(self.e,lambda:self.e.move_telekinetic_objects(
            self.a,{'body-edge-object':[(10,2),(11,2)]},action_cost='standard',maximum_distance=1,
            reason='actual path leaves the eight metre body range'),reason_pattern='beyond eight metres')
        result=self.e.move_telekinetic_objects(self.a,{'body-edge-object':[(10,2),(10,3)]},
            action_cost='standard',maximum_distance=1,reason='actual path stays within body-edge range')
        self.assertEqual(result['objects']['body-edge-object']['distance'],1)
        self.assertEqual(WORLD.location_of(self.e._physical_objects['body-edge-object'])['cell'],(10,3))


class HazardBodyTests(unittest.TestCase):
    setUpClass=classmethod(_rules)
    world=HAZARD.HazardStateTests.world
    install=HAZARD.HazardStateTests.install

    def prepare_body(self,engine,owner,actor,position=(1,1)):
        owner.pos=(0,0);actor.pos=position
        BODY.observe(engine,actor,[(0,0),(1,0),(0,1),(1,1)],reason='actual two by two hazard entrant')

    def step(self,engine,owner,actor,destination):
        return FORCED.along_path(engine,owner,actor,points=[actor.pos,destination],source='move/밀기')

    def test_paid_and_forced_entries_apply_each_new_physical_instance_once_and_skip_retained_cells(self):
        e,a,t=self.install('move/압정뿌리기');self.prepare_body(e,a,t)
        e.end_of_turn(a);e.start_of_turn(t,initiative_count=10)
        before=t.hp
        self.assertTrue(e.disengage(t,(2,1)))
        self.assertEqual(before-t.hp,2*(t.base_max_hp//10))
        self.assertIn('둔화',t.conditions)
        after=t.hp
        self.assertEqual(self.step(e,a,t,(2,0))['moved'],1)
        self.assertEqual(t.hp,after)

    def test_two_body_contacts_with_one_toxic_installation_are_not_two_layers(self):
        e,a,t=self.install('move/독압정');self.prepare_body(e,a,t)
        self.assertEqual(self.step(e,a,t,(2,1))['moved'],1)
        self.assertIn('독',t.conditions)
        records=CONDITIONS.records(t,'독')
        self.assertTrue(records)
        self.assertTrue(all(row['effect'].get('variant')!='맹독' for row in records))

    def test_actual_altitude_zero_air_to_land_hits_the_single_retained_body_hazard_once(self):
        for producer in ('paid_land_path','disengage'):
            with self.subTest(producer=producer):
                e,a,t=self.install('move/압정뿌리기');self.prepare_body(e,a,t,position=(3,0))
                MOVE.entry_mode(t,'공중/부유')
                self.assertTrue(t.airborne);self.assertEqual(t.spec.get('_movement_altitude',0),0)
                e.end_of_turn(a);e.start_of_turn(t,initiative_count=10)
                before=t.hp
                if producer=='paid_land_path':
                    self.assertTrue(TURN.spend(e,t,'shift','actual land contact',movement=True))
                    self.assertEqual(MOVE.follow_paid_path(e,t,[(2,0)],mode='land',maximum_distance=6)['steps'],1)
                else:self.assertTrue(e.disengage(t,(2,0),movement_mode='land'))
                self.assertFalse(t.airborne)
                self.assertEqual(BODY.cells(t).intersection(e.hazards),{(3,1)})
                self.assertEqual(before-t.hp,t.base_max_hp//10)

    def test_two_actual_toxic_installations_overlapping_one_entered_square_are_deadly(self):
        e,a,t=self.install('move/독압정')
        effect=self.r.move_mech('move/독압정')[0]['effects_exec'][0]
        HAZARDS.install(e,a,effect,{'source_id':'move/독압정',
            'move':{'id':'move/독압정','_hazard_cells':HAZARD.CELLS8}})
        self.prepare_body(e,a,t)
        self.assertEqual(self.step(e,a,t,(2,1))['moved'],1)
        self.assertEqual(CONDITIONS.records(t,'독')[0]['effect']['variant'],'맹독')

    def test_body_edge_proximity_uses_one_rock_and_preserves_native_reentry_immunity(self):
        e,a,t=self.install('move/스텔스록');self.prepare_body(e,a,t,position=(0,6))
        before=t.hp;expected=int(e.tick(t)*e.type_multiplier('바위',t)[0])
        self.assertEqual(self.step(e,a,t,(0,5))['moved'],1)
        self.assertEqual(before-t.hp,expected)
        self.assertEqual(sum(len(row['instances']) for row in e.hazards.values()),3)
        after=t.hp
        self.assertEqual(self.step(e,a,t,(1,5))['moved'],1)
        self.assertEqual(t.hp,after)

    def test_gm_send_loads_shallow_ice_without_traversing_spike_hazards(self):
        e,a,t=self.install('move/압정뿌리기')
        e.gm.recall(t,reason='actual off-field subject before placement')
        t.spec['weight_class']=5
        ICE.adopt(e,shallow_cells=[HAZARD.CELLS8[0]],thick_cells=[],water_air_available=False,
            gm_id='actual-gm',reason='actual shallow lake at the send destination')
        before=t.hp;hazards=deepcopy(e.hazards)
        e.gm.send_out(t,HAZARD.CELLS8[0],reason='actual placement onto shallow lake ice')
        self.assertEqual(MAP.base_at(e.grid,HAZARD.CELLS8[0]),'underwater')
        self.assertEqual((t.spec['_respiration']['medium'],t.spec['_respiration']['breathing']),('water',False))
        self.assertEqual(t.hp,before);self.assertEqual(e.hazards,hazards)
        self.assertNotIn('둔화',t.conditions)
        self.assertNotIn('_fall_events',t.spec)


class SendBodyTests(unittest.TestCase):
    setUpClass=classmethod(_rules)
    setup_world=PARTY.Tests.setup_world

    def test_actual_party_send_commits_ice_and_breathing_together_and_late_failure_rolls_back(self):
        self.setup_world()
        for actor in self.e.everyone:
            if actor.spec.get('kind')=='pokemon':actor.spec['weight_class']=1
        self.q.spec['weight_class']=5
        ICE.adopt(self.e,shallow_cells=[(5,0)],thick_cells=[],water_air_available=False,
            gm_id='actual-gm',reason='actual shallow lake for paid send')
        def send():
            return self.e.act_on_party(self.a,send=[(self.q,(5,0))],request_id='body-ice-send',
                reason='actual paid send onto shallow lake')
        original=ICE._water
        def late_failure(*args,**kwargs):
            original(*args,**kwargs)
            raise ValueError('actual send-water late failure')
        with patch.object(ICE,'_water',side_effect=late_failure):
            NATIVE.assert_rejected_unchanged(self.e,send,reason_pattern='send-water late failure')
        before=self.q.hp;receipt=send()
        self.assertEqual((self.q.on_field,self.q.pos,self.a.budget['shift']),(True,(5,0),0))
        self.assertEqual(MAP.base_at(self.e.grid,(5,0)),'underwater')
        self.assertEqual((self.q.spec['_respiration']['medium'],self.q.spec['_respiration']['breathing']),('water',False))
        self.assertEqual(self.q.hp,before)
        frozen=self.e.export_state()
        self.assertEqual(send(),receipt);self.assertEqual(self.e.export_state(),frozen)


class NativeSwitchIceTests(unittest.TestCase):
    setUpClass=classmethod(_rules)
    setup=SWITCH_FIXTURE.NativeSwitchTransferRevisionTests.setup
    open=SWITCH_FIXTURE.NativeSwitchTransferRevisionTests.open
    mapped=SWITCH_FIXTURE.NativeSwitchTransferRevisionTests.mapped
    baton=SWITCH_FIXTURE.NativeSwitchTransferRevisionTests.baton

    def setUp(self):
        self.setup(juggler=True);self.mapped()
        for actor in (self.p,self.q,self.foe):actor.spec['weight_class']=1
        self.q.spec['weight_class']=5
        ICE.adopt(self.e,shallow_cells=[self.p.pos],thick_cells=[],water_air_available=False,
            gm_id='actual-gm',reason='actual replacement destination with light outgoing body')

    def assert_water(self):
        self.assertFalse(self.p.on_field);self.assertTrue(self.q.on_field)
        self.assertEqual(self.q.pos,self.p.pos)
        self.assertEqual(MAP.base_at(self.e.grid,self.q.pos),'underwater')
        self.assertEqual((self.q.spec['_respiration']['medium'],self.q.spec['_respiration']['breathing']),('water',False))

    def test_actual_baton_replacement_commits_nested_send_ice_and_water(self):
        self.open();self.baton();self.assert_water()

    def test_actual_round_trip_commits_all_nested_send_ice_and_water_and_late_failure_is_atomic(self):
        self.open();self.e.use_move(self.p,self.p,'move/칼춤')
        SWITCH.select(self.e,self.p,self.q,source=SWITCH.ROUND_TRIP,reason='actual immediate replacement')
        original=ICE._water
        def late_failure(*args,**kwargs):
            original(*args,**kwargs)
            raise ValueError('actual nested send-water late failure')
        with patch.object(ICE,'_water',side_effect=late_failure):
            NATIVE.assert_rejected_unchanged(self.e,
                lambda:self.e.manual_feat(self.t,SWITCH.ROUND_TRIP,self.p),
                reason_pattern='nested send-water late failure')
        self.e.manual_feat(self.t,SWITCH.ROUND_TRIP,self.p);self.assert_water()


class NicoletteBodyTests(unittest.TestCase):
    setUpClass=classmethod(_rules)
    _ice_engine=TERRAIN.NicoletteTerrainTests._ice_engine

    def test_bank_anchor_walk_breaks_all_body_ice_and_cold_turn_loses_one_stage_only(self):
        e,p=self._ice_engine(weight=6,position=(0,0),identity='wide-walker')
        e.everyone[0].pos=(5,5)
        BODY.observe(e,p,[(0,0),(1,0),(0,1),(1,1)],reason='actual two by two bank-anchor body')
        e.start_round([p]);e.start_of_turn(p)
        self.assertTrue(TURN.spend(e,p,'shift','actual bank-edge walk',movement=True))
        self.assertEqual(MOVE.follow_paid_path(e,p,[(0,1)],mode='land',maximum_distance=6)['steps'],1)
        self.assertEqual({tuple(q) for q in NICOLETTE.state(e)['broken_ice']},{(1,1),(1,2)})
        self.assertEqual(MAP.base_at(e.grid,p.pos),'regular')
        before=p.stages['spe'];e.end_of_turn(p)
        self.assertEqual(p.stages['spe'],before-1)
        self.assertEqual(p.spec['_nicolette_cold_water_turns'][-1]['cells'],[(1,1),(1,2)])
        p.airborne=True;p.spec['_movement_altitude']=1
        e.start_round([p]);e.start_of_turn(p);before=p.stages['spe'];e.end_of_turn(p)
        self.assertEqual(p.stages['spe'],before)

    def test_native_weight_three_fall_breaks_body_intersection_with_bank_anchor(self):
        e,p=self._ice_engine(weight=3,position=(0,1),identity='wide-faller')
        BODY.observe(e,p,[(0,0),(1,0),(0,1),(1,1)],reason='actual wide falling body')
        e.falling_damage(p,action_id='wide-bank-fall',meters=1,intentional=False,
            reason='actual fall with body contacting frozen river',fixed_damage=[1])
        self.assertEqual({tuple(q) for q in NICOLETTE.state(e)['broken_ice']},{(1,1),(1,2)})
        self.assertEqual(MAP.base_at(e.grid,p.pos),'regular')


if __name__=='__main__':unittest.main()
