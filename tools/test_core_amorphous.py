"""C10-003: one real deformable body through native paid movement."""
from pathlib import Path
from copy import deepcopy,copy
from unittest.mock import patch
import json,sys,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as fixture
from builder import build_pokemon
from grid import Grid
import body_modes as MODES,body_state as BODY,movement_actions as MOVE
import state_grants as GRANTS,state_codec as CODEC,world_entities as WORLD


class AmorphousTests(unittest.TestCase):
    setUpClass=classmethod(fixture.ProgressionStateTests.setUpClass.__func__)
    add=fixture.ProgressionStateTests.add
    restored=fixture.ProgressionStateTests.restored

    def setUp(self):
        fixture.ProgressionStateTests.setUp(self)
        self.p=self.add(build_pokemon(self.r,'질퍽이',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
        self.t=self.add(build_pokemon(self.r,'잉어킹',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
        self.a.pos=(0,0);self.p.pos=(1,2);self.t.pos=(7,2)
        self.p.spec['size']='Large';self.p.spec['height_m']=1.5
        self.e.gm.observe_loyalty(self.p,6,reason='known obedience')
        self.e.gm.observe_loyalty(self.t,6,reason='known obedience')
        self.e.gm.set_movement_capabilities(self.p,{'land':6},basis='base',reason='observed Overland')
        self.e.grid=Grid(9,5,blocking=[(x,y) for x in range(3,9) for y in range(5) if y!=2],
                         walls=[((3,y),(4,y)) for y in range(5)])

    def begin(self):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=20)

    def form(self,kind='flatten',**options):
        values=dict(offsets=[(0,0)],height_m=.03,cross_section={'axis':'x','width_m':.4},
                    form=kind,reason='GM observes the same real body '+kind)
        values.update(options)
        return self.e.change_body_mode(self.p,'amorphous',**values)

    def passage(self,**options):
        if 'door' not in self.e._physical_objects:
            WORLD.register_object(self.e,'door',location={'kind':'grid','cell':(3,2)},reason='actual closed door')
        values=dict(passage_id='under-door',height_m=.04,width_m=.5,reason='GM measures the actual gap under this door')
        values.update(options)
        return self.e.gm.observe_body_passage('door',[(3,2),(4,2)],**values)

    def test_same_body_all_forms_and_native_narrow_corridor_under_door_keep_actual_cost(self):
        self.assertIn('부정형',GRANTS.effective_capabilities(self.p,only=('부정형',)))
        self.begin();self.e.approach(self.p,self.t,movement_mode='land')
        self.assertEqual(self.p.pos,(1,2))
        self.begin();before=deepcopy((self.p.budget,self.p.spec['size'],self.p.spec.get('weight_kg'),self.p.weight_class))
        identity=self.p.entity_id;spec=self.p.spec
        for kind,offsets in [('flatten',[(0,0)]),('stretch',[(0,0),(1,0)]),('condense',[(0,0)]),('reform',[(0,0),(0,1)])]:
            out=self.form(kind,offsets=offsets)
            self.assertEqual(out['offsets'],tuple(offsets));self.assertEqual(out['size_ratio'],None)
            self.assertEqual(out['height_m'],.03);self.assertEqual(out['body_mode']['form'],kind)
        self.form();self.passage();walls=set(self.e.grid.walls)
        self.e.grid.slow.add((4,2))
        result=self.e.approach(self.p,self.t,movement_mode='land')
        self.assertEqual((result['distance'],result['position']),(6,(6,2)))
        self.assertEqual(self.p.budget['shift'],0);self.assertEqual(self.p.budget['standard'],before[0]['standard'])
        self.assertIs(self.p.spec,spec);self.assertEqual(self.p.entity_id,identity)
        self.assertEqual((self.p.spec['size'],self.p.spec.get('weight_kg'),self.p.weight_class),before[1:])
        self.assertEqual(self.e.grid.walls,walls);self.assertTrue(self.e.grid.blocked((3,2),(4,2)))
        self.assertFalse(BODY.in_range(self.e,self.p,self.a,20))
        with self.assertRaisesRegex(ValueError,'does not fit'):self.e.change_body_mode(self.p,'normal',reason='actual attempted reform in narrow corridor')
        self.p.pos=(1,2);budget=dict(self.p.budget)
        self.e.change_body_mode(self.p,'normal',reason='GM observes the original body restored in open space')
        self.assertEqual(self.p.budget,budget);self.assertEqual(BODY.offsets(self.p),((0,0),(0,1),(1,0),(1,1)))

    def test_only_measured_matching_current_gap_and_cross_section_admit_movement(self):
        self.form();self.assertFalse(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)))
        self.passage()
        self.assertTrue(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)))
        self.assertTrue(BODY.can_place(self.e,self.p,(3,2),origin=(4,2)))
        for opts in ({'height_m':.05},{'cross_section':{'axis':'x','width_m':.6}},
                     {'cross_section':{'axis':'y','width_m':.4}},{'cross_section':None}):
            self.form(**opts);self.assertFalse(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)))
        self.form();self.assertFalse(BODY.can_place(self.e,self.p,(4,2),origin=(3,2),altitude=1))
        self.assertFalse(BODY.can_place(self.e,self.p,(4,2),origin=(3,2),underground=True))
        self.assertFalse(MODES.movement_blocked(self.e,self.p,(3,2),(4,2),altitude=0,underground=False))
        self.assertTrue(MODES.movement_blocked(self.e,self.p,(3,1),(4,1),altitude=0,underground=False))
        self.assertTrue(MODES.movement_blocked(self.e,self.p,(3,1),(4,2),altitude=0,underground=False))
        self.passage(height_m=0);self.assertFalse(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)))

    def test_shape_cannot_override_occupancy_blocking_terrain_or_current_capability(self):
        self.form();self.passage()
        self.t.pos=(4,2);self.assertFalse(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)))
        self.t.pos=(7,2);self.e.grid.blocking.add((4,2))
        self.assertFalse(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)));self.e.grid.blocking.remove((4,2))
        self.e.observe_map_terrain([(4,2)],base='underwater',reason='actual water behind the door')
        self.begin();self.e.approach(self.p,self.t,movement_mode='land');self.assertEqual(self.p.pos,(1,2))
        self.e.observe_map_terrain([(4,2)],base='regular',reason='actual dry floor')
        with patch.object(GRANTS,'effective_capabilities',return_value=[]):
            self.assertFalse(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)))
        self.assertTrue(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)))

    def test_physical_gap_never_follows_moved_replaced_terminal_surface_or_new_map(self):
        self.form();self.passage();door=self.e._physical_objects['door']
        WORLD.register_object(self.e,'door',location={'kind':'grid','cell':(2,2)},reason='door physically moved')
        self.assertFalse(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)))
        WORLD.register_object(self.e,'door',location={'kind':'grid','cell':(3,2)},reason='door restored to the measured surface')
        door['destroyed']=dict(source='gm/observation',by_actor_id=self.a.entity_id)
        self.assertFalse(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)));door.pop('destroyed')
        old=self.e.grid;self.e.grid=Grid(9,5,walls=old.walls)
        self.assertFalse(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)));self.e.grid=old
        door[BODY.PASSAGES]['under-door']['object_id']='another-door'
        self.assertFalse(self.e.validate_state()['valid'])

    def test_reaction_closes_actual_gap_after_paid_plan_and_before_entry(self):
        self.form();self.passage();self.begin();original=MOVE.departure
        def close(e,c,destination,altitude,**options):
            allowed=original(e,c,destination,altitude,**options)
            if c.pos==(3,2):self.passage(height_m=0)
            return allowed
        with patch.object(MOVE,'departure',side_effect=close):
            out=self.e.approach(self.p,self.t,movement_mode='land')
        self.assertEqual((self.p.pos,out['distance']),( (3,2),2))
        self.assertEqual(self.p.budget['shift'],0);self.assertTrue(self.e.grid.blocked((3,2),(4,2)))

    def test_native_json_and_gm_restore_keep_same_form_surface_map_and_validation(self):
        self.form('stretch',offsets=[(0,0),(1,0)]);self.passage();snapshot=self.e.gm.snapshot()
        self.form('condense');self.passage(height_m=0);self.e.gm.restore(snapshot)
        self.assertEqual(self.p.spec[MODES.KEY]['form'],'stretch')
        self.assertTrue(BODY.can_place(self.e,self.p,(4,2),origin=(3,2)))
        restored=self.restored();p=next(c for c in restored.everyone if c.entity_id==self.p.entity_id)
        self.assertEqual(p.spec[MODES.KEY],self.p.spec[MODES.KEY])
        self.assertEqual(restored.grid.walls,self.e.grid.walls)
        self.assertTrue(BODY.can_place(restored,p,(4,2),origin=(3,2)))
        restored.gm.observe_body_passage('door',[(3,2),(4,2)],passage_id='under-door',height_m=.01,width_m=.5,reason='current gap changed')
        self.assertFalse(BODY.can_place(restored,p,(4,2),origin=(3,2)))
        restored._physical_objects['door'][BODY.PASSAGES]['under-door']['height_m']=100
        with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(restored)

    def test_invalid_body_form_or_surface_source_fails_without_mutation(self):
        self.begin();before=deepcopy((self.p.spec,self.p.budget,self.e._physical_objects,vars(self.e.grid)))
        for options in ({'size_ratio':.01},{'height_m':True},{'offsets':[]},{'form':''},
                        {'cross_section':{'axis':'z','width_m':.2}}):
            with self.assertRaises(ValueError):self.form(**options)
            self.assertEqual((self.p.spec,self.p.budget,self.e._physical_objects,vars(self.e.grid)),before)
        fake=copy(self.p)
        with self.assertRaises(ValueError):self.e.change_body_mode(fake,'amorphous',offsets=[(0,0)],form='flatten',reason='copied body cannot act')
        selected=self.r._selected_rule
        def changed(uid,*args,**kwargs):return 'unreviewed/Amorphous' if uid=='capability/부정형' else selected(uid,*args,**kwargs)
        with patch.object(self.r,'_selected_rule',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'source'):self.form()
        self.assertEqual((self.p.spec,self.p.budget,self.e._physical_objects,vars(self.e.grid)),before)
        self.form();self.passage();row=deepcopy(self.p.spec[MODES.KEY]);self.t.spec[MODES.KEY]=row
        with self.assertRaisesRegex(ValueError,'another actual body'):BODY.projection(self.t)
        self.t.spec.pop(MODES.KEY)
        before=deepcopy((self.e._physical_objects,vars(self.e.grid)))
        with self.assertRaises(ValueError):self.e.gm.observe_body_passage('door',[(2,2),(3,2)],passage_id='invented',height_m=.1,width_m=1,reason='not an actual wall')
        self.assertEqual((self.e._physical_objects,vars(self.e.grid)),before)


if __name__=='__main__':unittest.main()
