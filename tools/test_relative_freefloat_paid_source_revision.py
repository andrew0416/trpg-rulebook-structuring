"""Actual relative Shift consumers retain their paid rate and action-wide boundary."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]

from engine import Rules
from grid import Grid
from state_codec import load_engine,StateCodecError
import test_book_athlete_acquisition as ATHLETE_FIX
import athlete as ATHLETE
import movement_actions as MOVEMENT
import relative_movement as RELATIVE
import world_entities as WORLD
import test_electro_shot_source_zone as ELECTRO_FIX


class RelativeFreeFloatPaidTests(ATHLETE_FIX.AthleteScene,unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(str(ROOT),ruleset='all')

    def scene(self,*,sky=2,free_float=4,enhanced=False):
        self.setup(positions={'t':(2,2),'p':(2,10),'q':(12,2)})
        if enhanced:
            self.acquire()
            self.acquire(ATHLETE.REGIME)
            self.exercise(('atk','spe'))
        self.e.gm.set_movement_capabilities(self.t,{'land':6,'sky':sky,'free_float':free_float},
            basis='current',reason='actual native Sky and independently declared Free Floating')
        self.e.observe_relative_directions(self.t,directions={'forward':(1,0)},
            quickly_trip_placement='before_entry',reason='GM observes the understood physical direction')

    def region(self,identity,gravity,*,cells=None):
        source=json.loads((ROOT/'data/examples/environment-derive.json').read_text(encoding='utf-8'))['source']
        self.e.observe_environment(identity,dict(gravity=gravity,pressure=1,air_available=True,medium='air'),
            cells=cells,source=source,reason='actual gravity along the declared relative Sky route')

    def declaration(self,identity,*,distance=8,measured=None):
        native={'reason_text':'actual continuous relative Sky segments'}
        if measured is not None:native['gm_step_distance']=measured
        return dict(direction='forward',distance=distance,pace='quickly',movement_id=identity,
            movement_mode='sky',native_options=native)

    def test_relative_measured_step_keeps_actual_paid_sprint_rate_for_both_source_policies(self):
        for enhanced in (False,True):
            for policy in ('ch06_once','ch07_turn'):
                for free_float in (0,4):
                    with self.subTest(enhanced=enhanced,policy=policy,free_float=free_float):
                        self.scene(free_float=free_float,enhanced=enhanced)
                        self.region('normal',1)
                        self.combat(self.t)
                        self.assertTrue(self.e.sprint(self.t,source_policy=policy))
                        expected=4 if enhanced else 3
                        self.assertEqual(ATHLETE.sprint_rate(self.e,self.t),'1' if enhanced else '0.5')
                        self.assertEqual(MOVEMENT.distance_budget(self.e,self.t,'sky'),expected)
                        declaration=self.declaration('measured-paid',distance=expected,measured=expected)
                        result=self.e.move_relative(self.t,**declaration)
                        self.assertEqual((result['distance'],result['state'],self.t.pos),(expected,'complete',(3,2)))
                        self.assertEqual((self.t.budget['standard'],self.t.budget['shift']),(0,0))
                        self.assertEqual('질주' in self.t.custom_conditions,policy=='ch07_turn')
                        before=self.e.export_state()
                        self.assertEqual(self.e.move_relative(self.t,**declaration),result)
                        self.assertEqual(self.e.export_state(),before)
                        self.next_turn(self.t)
                        self.assertNotIn('질주',self.t.custom_conditions)
                        later=self.e.move_relative(self.t,**self.declaration('later-unboosted',distance=8))
                        self.assertEqual((later['distance'],self.t.pos),(2,(5,2)))
                        self.assertEqual((self.t.budget['standard'],self.t.budget['shift']),(1,0))

    def test_relative_cells_share_native_sky_boundary_across_observed_gravity_regions(self):
        cases=(
            ('zero_to_normal',1,4,1),
            ('all_zero',1,4,4),
            ('normal_to_zero',2,4,2),
            ('all_normal',2,4,2),
            ('ordinary_sky',1,0,1),
        )
        for case,sky,free_float,expected in cases:
            with self.subTest(case=case):
                self.scene(sky=sky,free_float=free_float)
                if case in ('zero_to_normal','normal_to_zero'):
                    self.region('origin',0 if case=='zero_to_normal' else 1,cells=[[2,2]])
                    self.region('route',1 if case=='zero_to_normal' else 0,cells=[[x,2] for x in range(3,11)])
                else:
                    self.region('whole-route',1 if case=='all_normal' else 0)
                self.combat(self.t)
                declaration=self.declaration(case,distance=4)
                result=self.e.move_relative(self.t,**declaration)
                self.assertEqual((result['distance'],result['state'],self.t.pos),(expected,'complete',(2+expected,2)))
                self.assertEqual((self.t.budget['standard'],self.t.budget['shift']),(1,0))
                before=self.e.export_state()
                self.assertEqual(self.e.move_relative(self.t,**declaration),result)
                self.assertEqual(self.e.export_state(),before)

    def test_relative_cold_restore_keeps_cell_prefix_and_rejects_forged_offsets_or_discounts(self):
        self.scene()
        self.region('normal',1)
        self.combat(self.t)
        self.assertTrue(self.e.sprint(self.t,source_policy='ch06_once'))
        declaration=self.declaration('restored-paid',distance=3)
        result=self.e.move_relative(self.t,**declaration)
        self.assertEqual((result['distance'],self.t.pos),(3,(5,2)))
        actor_id=self.t.entity_id
        saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
        self.e=load_engine(self.rules,deepcopy(saved))
        self.t=WORLD.actor_index(self.e)[actor_id]
        before=self.e.export_state()
        self.assertEqual(self.e.move_relative(self.t,**declaration),result)
        self.assertEqual(self.e.export_state(),before)
        self.assertEqual((self.t.budget['standard'],self.t.budget['shift']),(0,0))
        for field,value in (('free_float_distance_offset',0),('free_float_distance_offset',-1),('charged_distance',0)):
            with self.subTest(field=field,value=value):
                engine=load_engine(self.rules,deepcopy(saved))
                actor=WORLD.actor_index(engine)[actor_id]
                progress=actor.spec[RELATIVE.KEY]['restored-paid']['cells'][-1]['progress']
                progress[field]=value
                with self.assertRaises(ValueError):engine.move_relative(actor,**declaration)
                with self.assertRaises(StateCodecError):engine.export_state()

    def test_relative_parent_prefix_uses_actual_zero_charged_exit_not_physical_distance(self):
        fixture=ELECTRO_FIX.ElectroShotZoneTests('runTest')
        fixture.rules=self.rules
        engine,user,actor,enemy,_=fixture.world()
        engine.grid=Grid(14,8)
        fixture.cast(engine,user,enemy)
        fixture.ally_turn(engine,user,actor)
        engine.gm.set_movement_capabilities(actor,{'land':2,'sky':2,'free_float':4},
            basis='current',reason='actual independent Sky with dormant Free Floating')
        source=json.loads((ROOT/'data/examples/environment-derive.json').read_text(encoding='utf-8'))['source']
        engine.observe_environment('exit-normal',dict(gravity=1,pressure=1,air_available=True,medium='air'),
            source=source,reason='actual normal gravity along the free exit and paid suffix')
        engine.observe_relative_directions(actor,directions={'forward':(0,1)},
            quickly_trip_placement='before_entry',reason='GM observes direction out of the actual source area')
        declaration=self.declaration('actual-free-exit',distance=2)
        result=engine.move_relative(actor,**declaration)
        self.assertEqual((result['distance'],actor.pos),(2,(2,3)))
        cells=actor.spec[RELATIVE.KEY]['actual-free-exit']['cells']
        self.assertEqual((cells[0]['progress']['distance'],cells[0]['progress']['charged_distance']),(1,0))
        self.assertEqual(cells[1]['progress']['free_float_distance_offset'],0)
        self.assertEqual(cells[1]['progress']['distance'],1)
        self.assertEqual((actor.budget['standard'],actor.budget['shift']),(1,0))
        actor_id=actor.entity_id
        saved=json.loads(json.dumps(engine.export_state(),ensure_ascii=False))
        restored=load_engine(self.rules,saved)
        restored_actor=WORLD.actor_index(restored)[actor_id]
        before=restored.export_state()
        self.assertEqual(restored.move_relative(restored_actor,**declaration),result)
        self.assertEqual(restored.export_state(),before)


if __name__=='__main__':
    unittest.main()
