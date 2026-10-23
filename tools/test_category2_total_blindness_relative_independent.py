"""Independent C07-166 relative Shift checks against actual source consumers."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from engine import Rules,Engine
from grid import Grid
import test_category2_vision_impairment as VISION_FIXTURE
import relative_movement as RELATIVE
import test_category2_total_blindness_relative as RELATIVE_FIXTURE
import state_grants as GRANTS
import stamina as STAMINA
import survivalist_features as SURVIVALIST

ROOT=Path(__file__).resolve().parents[1]


class TotalBlindnessRelativeIndependentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def fixture(self,*,movement=6,placement='before_entry',frame=True):
        e=Engine(self.rules,seed=7166);e.grid=Grid(20,4)
        a=VISION_FIXTURE.combatant(self.rules,'relative-independent',pos=(1,1))
        a.spec['movement']={'land':movement};a.movement=movement
        e.gm.add_combatant(a);e.start_round(e.everyone);e.start_of_turn(a)
        self.assertTrue(e.apply_status(a,'완전 실명',parameters={'cause':'external'}))
        if frame:
            public=e.observe_relative_directions(a,directions={'hand-forward':(1,0)},
                quickly_trip_placement=placement,
                reason='GM translates the actor understood direction and settles hazardous trip placement')
            self.assertEqual(public,{'directions':['hand-forward'],'quickly_trip_placement':placement})
        return e,a

    def options(self,*,passed=True):
        return {'frequency':'once_per_shift','reason':'GM chooses one actual traversal check per Shift',
            'check_options':[{'skill':'곡예','fixed':[3,3,3,3] if passed else [1,1,1,1]}]}

    def move(self,e,a,*,pace='slowly',identity='declared-relative-shift',options='default'):
        if options=='default':options=self.options()
        return e.move_relative(a,direction='hand-forward',distance=6,pace=pace,
            movement_id=identity,blindness_options=options)

    def test_unbound_direction_or_undeclared_pace_refuses_before_native_cost_or_rng(self):
        e,a=self.fixture(frame=False);before=e.export_state()
        with self.assertRaises(ValueError):self.move(e,a)
        self.assertEqual(e.export_state(),before)
        e.observe_relative_directions(a,directions={'hand-forward':(1,0)},
            quickly_trip_placement='before_entry',reason='GM translates only the understood relative label')
        before=e.export_state()
        with self.assertRaises(ValueError):self.move(e,a,pace='ordinary')
        self.assertEqual(e.export_state(),before)

    def test_slowly_uses_native_minimum_and_odd_even_slowness_once_without_status_grant(self):
        for movement,slowed,expected in ((1,False,1),(5,False,2),(6,False,3),(6,True,3)):
            with self.subTest(movement=movement,slowed=slowed):
                e,a=self.fixture(movement=movement)
                if slowed:self.assertTrue(e.apply_status(a,'둔화'))
                before=deepcopy(a.conditions);rng=e.rng.getstate()
                result=self.move(e,a)
                self.assertEqual(a.pos,(1+expected,1));self.assertEqual(result['distance'],expected)
                self.assertEqual(a.conditions,before);self.assertEqual(a._action_history,['shift'])
                self.assertEqual(e.rng.getstate(),rng)
                self.assertEqual(set(result),{'movement_id','state','distance','tripped'})
                self.assertTrue(e.validate_state()['valid'])

    def test_quickly_hazard_placement_keeps_automatic_trip_and_actual_entry_checks(self):
        for terrain in ('blocking','rough','slow'):
            for placement in ('before_entry','enter_passable'):
                for passed in ((True,False) if placement=='enter_passable' and terrain!='blocking' else (True,)):
                    with self.subTest(terrain=terrain,placement=placement,passed=passed):
                        e,a=self.fixture(placement=placement);getattr(e.grid,terrain).add((2,1))
                        options=None if placement=='before_entry' else self.options(passed=passed)
                        result=self.move(e,a,pace='quickly',options=options)
                        entered=placement=='enter_passable' and terrain!='blocking'
                        self.assertEqual(a.pos,(2,1) if entered else (1,1))
                        self.assertTrue(result['tripped']);self.assertIn('넘어짐',a.conditions)
                        checks=a.spec[RELATIVE.KEY]['declared-relative-shift']['checks']
                        self.assertEqual(len(checks),1 if entered else 0)
                        if entered:self.assertEqual(checks[0]['result'].passed,passed)
                        self.assertEqual(a._action_history,['shift'])
                        self.assertTrue(e.validate_state()['valid'])

    def test_completed_relative_receipt_cold_restores_without_repayment_or_coordinate_leak(self):
        e,a=self.fixture();result=self.move(e,a);identity=a.entity_id
        state=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
        e=Engine.import_state(Rules(ROOT,ruleset='core'),state)
        a=next(actor for actor in e.everyone if actor.entity_id==identity)
        before=e.export_state()
        with patch.object(e,'skill_roll',side_effect=AssertionError('completed Shift cannot roll again')):
            again=self.move(e,a)
        self.assertEqual(again,result);self.assertEqual(e.export_state(),before)
        self.assertEqual(set(again),{'movement_id','state','distance','tripped'})
        self.assertEqual(a._action_history,['shift'])

    def test_cure_during_actual_opportunity_stamina_wait_resumes_without_vision_checks_or_second_cost(self):
        fixture=RELATIVE_FIXTURE.TotalBlindnessRelativeTests('runTest');fixture.rules=self.rules
        for pace,paid_maximum in (('slowly',3),('quickly',6)):
            with self.subTest(pace=pace):
                e,a,target=fixture.fixture()
                enemy=VISION_FIXTURE.combatant(self.rules,'cure-relative-aoo',pos=(1,4))
                enemy.side='enemies';e.gm.add_combatant(enemy);enemy_id=enemy.entity_id
                def acquire(engine,actor):
                    actor.spec.setdefault('edges',[]).append(STAMINA.SOURCE)
                    actor.spec['skills']={'Athletics':5,'Acrobatics':4,'Combat':6}
                # Leave a clear step for the actual AoO departure to suspend.
                # A Quickly before-entry hazard at (3,3) would trip before
                # that departure and never produce the intended paid wait.
                GRANTS.transition(e,a,acquire);e.grid.rough.add((4,3));e.rng.seed(5)
                declaration=fixture.declaration(pace=pace,
                    options=fixture.options(faces=[6]*4) if pace=='slowly' else None)
                result=e.move_relative(a,**declaration)
                self.assertEqual((result['state'],a.pos),('pending',(2,3)))
                self.assertTrue(enemy.aoo_used);self.assertEqual(a._action_history,['shift'])
                row=a.spec[RELATIVE.KEY]['relative-one']
                self.assertEqual(row['facts']['budget'],paid_maximum)
                paid_budget=deepcopy(a.budget)
                action=next(item for item in e._native_action_resolutions.values()
                    if any(trigger['actor'] is a and trigger['source']==STAMINA.SOURCE for trigger in item['triggers']))
                action_id=action['id']
                e.cure_status(a,'완전 실명')
                self.assertEqual(SURVIVALIST.vision(e,a)[0],'none')
                e,a,target=fixture.fresh(e,a,target)
                e.resolve_stamina(a,action_id,skill='육상')
                completion_count=len(e._move_completions);rng=e.rng.getstate()
                with patch.object(e,'skill_roll',side_effect=AssertionError('cured actor has no blindness traversal check')):
                    result=e.move_relative(a,**declaration)
                self.assertEqual((result['state'],a.pos),('complete',(1+paid_maximum,3)))
                self.assertEqual(result['distance'],paid_maximum);self.assertFalse(result['tripped'])
                self.assertNotIn('넘어짐',a.conditions)
                self.assertEqual(a.spec[RELATIVE.KEY]['relative-one']['checks'],[])
                self.assertEqual(a.spec[RELATIVE.KEY]['relative-one']['facts']['budget'],paid_maximum)
                self.assertEqual(a._action_history,['shift']);self.assertEqual(a.budget,paid_budget)
                self.assertEqual(len(e._move_completions),completion_count);self.assertEqual(e.rng.getstate(),rng)
                self.assertTrue(next(actor for actor in e.everyone if actor.entity_id==enemy_id).aoo_used)
                fixture.fresh(e,a,target)
