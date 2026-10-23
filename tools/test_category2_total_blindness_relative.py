"""Real relative Shift and native Priority consumers for C07-166."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Rules
from grid import Grid
import test_category2_total_blindness_consumers as BASE
import test_category2_vision_impairment as ACTORS
import movement_actions as MOVEMENT
import relative_movement as RELATIVE
import state_grants as GRANTS
import stamina as STAMINA
import turn as TURN


class TotalBlindnessRelativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def fixture(self,*,placement='before_entry',cause='external',capabilities=()):
        base=BASE.TotalBlindnessConsumersTests('runTest');base.rules=self.rules
        e,a,t=base.fixture(capabilities=capabilities);e.grid=Grid(12,8);a.pos=(1,3);t.pos=(10,6)
        e.observe_relative_directions(a,directions={'forward':(1,0),'back':(-1,0)},
            quickly_trip_placement=placement,reason='GM binds known facing and trip placement on this grid')
        if cause=='external':e.apply_status(a,'완전 실명',parameters={'cause':'external'})
        elif cause=='darkness':base.observe(e,a)
        return e,a,t

    def options(self,*,faces=None,frequency='once_per_shift'):
        return {'frequency':frequency,'reason':'GM chooses the unspecified check repetition',
                'check_options':[] if faces is None else [{'fixed':faces}]}

    def declaration(self,*,pace='slowly',identity='relative-one',distance=6,options=None):
        return dict(direction='forward',distance=distance,pace=pace,movement_id=identity,
                    blindness_options=self.options() if options is None and pace=='slowly' else options)

    def fresh(self,e,a,t):
        restored=Engine.import_state(Rules(ROOT,ruleset='core'),json.loads(json.dumps(e.export_state())))
        index={actor.entity_id:actor for actor in restored.everyone}
        return restored,index[a.entity_id],index[t.entity_id]

    def test_slowly_reuses_slowed_rounding_minimum_without_status_or_double_halving(self):
        for movement,expected,slowed in ((1,1,False),(5,2,False),(6,3,False),(6,3,True)):
            with self.subTest(movement=movement,slowed=slowed):
                e,a,t=self.fixture();MOVEMENT.set_capabilities(e,a,{'land':movement},basis='current',reason_text='actual capability')
                if slowed:e.apply_status(a,'둔화')
                before=set(a.conditions);rng=e.rng.getstate()
                result=e.move_relative(a,**self.declaration())
                self.assertEqual((a.pos,result['distance']),((1+expected,3),expected))
                self.assertEqual(a.conditions,before);self.assertEqual(e.rng.getstate(),rng)
                self.assertEqual(a._action_history,['shift']);self.assertEqual(a.budget,{'standard':1,'shift':0,'swift':1})
                self.assertNotIn('position',result);self.assertNotIn('path',result)

    def test_quickly_clear_terrain_full_distance_and_explicit_world_frame(self):
        e,a,t=self.fixture(cause='darkness');rng=e.rng.getstate()
        declaration=self.declaration(pace='quickly')
        result=e.move_relative(a,**declaration)
        self.assertEqual(a.pos,(7,3));self.assertEqual(result['distance'],6)
        self.assertEqual(e.rng.getstate(),rng);self.assertNotIn('넘어짐',a.conditions)
        e,a,t=self.fresh(e,a,t);before=e.export_state()
        self.assertEqual(e.move_relative(a,**declaration),result)
        self.assertEqual(e.export_state(),before)

    def test_unbound_direction_or_unsettled_check_frequency_rejects_before_cost(self):
        e,a,t=self.fixture();before=e.export_state()
        bad=self.declaration();bad['direction']='north'
        with self.assertRaises(ValueError):e.move_relative(a,**bad)
        self.assertEqual(e.export_state(),before)
        bad=self.declaration();bad['blindness_options']=None
        with self.assertRaises(ValueError):e.move_relative(a,**bad)
        self.assertEqual(e.export_state(),before)
        bad=self.declaration();bad['destination']=(6,3)
        with self.assertRaises(TypeError):e.move_relative(a,**bad)
        self.assertEqual(e.export_state(),before)

    def test_quickly_actual_blocking_rough_and_slow_attempt_trip_without_illegal_entry(self):
        for kind in ('blocking','rough','slow'):
            with self.subTest(kind=kind):
                e,a,t=self.fixture();getattr(e.grid,kind).add((3,3));rng=e.rng.getstate()
                result=e.move_relative(a,**self.declaration(pace='quickly'))
                self.assertEqual(a.pos,(2,3));self.assertTrue(result['tripped'])
                self.assertEqual(a._action_history,['shift']);self.assertEqual(e.rng.getstate(),rng)
                self.fresh(e,a,t)

    def test_passable_quickly_entry_roll_success_cannot_cancel_automatic_trip(self):
        e,a,t=self.fixture(placement='enter_passable');e.grid.rough.add((2,3))
        result=e.move_relative(a,**self.declaration(pace='quickly',options=self.options(faces=[6]*4)))
        record=a.spec[RELATIVE.KEY]['relative-one']
        self.assertEqual(a.pos,(2,3));self.assertTrue(result['tripped'])
        self.assertEqual(record['checks'][0]['result'].total,24)
        self.assertTrue(record['checks'][0]['result'].passed)
        self.fresh(e,a,t)

    def test_slowly_actual_hazard_failure_trips_and_once_choice_does_not_preroll_unreached_cells(self):
        e,a,t=self.fixture();e.grid.rough.update({(2,3),(3,3)});rng=e.rng.getstate()
        result=e.move_relative(a,**self.declaration(options=self.options(faces=[1]*4)))
        self.assertEqual(a.pos,(2,3));self.assertTrue(result['tripped'])
        self.assertEqual(len(a.spec[RELATIVE.KEY]['relative-one']['checks']),1)
        self.assertEqual(e.rng.getstate(),rng)

    def test_priority_and_interrupt_moves_reject_both_native_entry_points_atomically(self):
        for source in ('move/전광석화','move/방어'):
            for method in ('use_move','use_move_on'):
                with self.subTest(source=source,method=method):
                    e,a,t=self.fixture();t.pos=(2,3)
                    GRANTS.replace_baseline(e,a,'moves',['move/할퀴기',source]);before=e.export_state()
                    with self.assertRaisesRegex(ValueError,'Priority or Interrupt'):
                        if method=='use_move':e.use_move(a,t,source,set_damage=True)
                        else:e.use_move_on(a,t,source,e.everyone)
                    self.assertEqual(e.export_state(),before)

    def test_blindsense_uses_normal_relative_allowance_and_ordinary_move_is_not_forbidden(self):
        e,a,t=self.fixture(cause='darkness',capabilities=['Blindsense'])
        declaration=self.declaration();declaration['blindness_options']=None
        result=e.move_relative(a,**declaration)
        self.assertEqual((a.pos,result['distance']),((7,3),6))
        t.pos=(8,3);e.use_move(a,t,'move/전광석화',set_damage=True)
        self.assertEqual(a.move_uses['move/전광석화'],1)

    def test_absolute_shift_cannot_bypass_relative_declaration_and_nonland_needs_native_observation(self):
        e,a,t=self.fixture();before=e.export_state()
        with self.assertRaisesRegex(ValueError,'relative declaration'):
            TURN.spend(e,a,'shift','unbound absolute producer',movement=True)
        self.assertEqual(e.export_state(),before)
        with self.assertRaisesRegex(ValueError,'relative declaration'):e.disengage(a,(2,3))
        self.assertEqual(e.export_state(),before)
        declaration=self.declaration();declaration['movement_mode']='sky'
        with self.assertRaisesRegex(ValueError,'native geometry/transfer'):e.move_relative(a,**declaration)
        self.assertEqual(e.export_state(),before)
        result=e.move_relative(a,**self.declaration())
        self.assertEqual(result['distance'],3);self.assertEqual(a._action_history,['shift'])

    def test_pending_relative_prefix_rejects_retargeting_and_cold_graph_tampering(self):
        # Reuse the actual unresolved check boundary, without inventing a paid
        # cursor. A skill callback failure cannot make a new Shift free.
        e,a,t=self.fixture();e.grid.rough.add((2,3));declaration=self.declaration()
        original=e.skill_roll
        with patch.object(e,'skill_roll',side_effect=ValueError('observed skill unavailable')):
            with self.assertRaisesRegex(ValueError,'observed skill'):e.move_relative(a,**declaration)
        e,a,t=self.fresh(e,a,t);before=e.export_state()
        changed=deepcopy(declaration);changed['direction']='back'
        with self.assertRaisesRegex(ValueError,'replace'):e.move_relative(a,**changed)
        self.assertEqual(e.export_state(),before)
        with self.assertRaisesRegex(ValueError,'already paid'):e.end_of_turn(a)
        row=a.spec[RELATIVE.KEY]['relative-one'];row['facts']['budget']+=1
        with self.assertRaises(ValueError):e.export_state()

    def test_real_opportunity_stamina_wait_cold_restore_resumes_same_shift_and_check_once(self):
        e,a,t=self.fixture();enemy=ACTORS.combatant(self.rules,'relative-aoo',pos=(1,4))
        enemy.side='enemies';e.gm.add_combatant(enemy)
        def acquire(engine,actor):
            actor.spec.setdefault('edges',[]).append(STAMINA.SOURCE)
            actor.spec['skills']={'Athletics':5,'Acrobatics':4,'Combat':6}
        GRANTS.transition(e,a,acquire);e.grid.rough.add((3,3));e.rng.seed(5)
        declaration=self.declaration(options=self.options(faces=[6]*4))
        result=e.move_relative(a,**declaration)
        self.assertEqual(result['state'],'pending');self.assertEqual(a.pos,(2,3));self.assertTrue(enemy.aoo_used)
        self.assertEqual(a._action_history,['shift'])
        action=next(row for row in e._native_action_resolutions.values()
            if any(trigger['actor'] is a and trigger['source']==STAMINA.SOURCE for trigger in row['triggers']))
        e,a,t=self.fresh(e,a,t)
        with self.assertRaises(ValueError):e.end_of_turn(a)
        e.resolve_stamina(a,action['id'],skill='육상')
        completions=len(e._move_completions);result=e.move_relative(a,**declaration)
        self.assertEqual(result['state'],'complete');self.assertEqual(a.pos,(4,3))
        self.assertEqual(len(e._move_completions),completions);self.assertEqual(a._action_history,['shift'])
        self.assertEqual(len(a.spec[RELATIVE.KEY]['relative-one']['checks']),1)
        self.fresh(e,a,t)


if __name__=='__main__':unittest.main()
