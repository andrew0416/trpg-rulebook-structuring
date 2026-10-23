"""C09-084 observable surface/Focus lifecycle over the existing native owners."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json, sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_cleanse_tags as _fixture_test_category2_cleanse_tags
from engine import Rules, Engine
from grid import Grid
import cleanse_tags as TAG, state_codec as CODEC, world_entities as W
import skill_feature_actions as SF, common_checks as C, grapple_state as GR
import effects_ext as EXT


class BarrierTests(unittest.TestCase):
    actor=_fixture_test_category2_cleanse_tags.CleanseTagTests.actor
    craft=_fixture_test_category2_cleanse_tags.CleanseTagTests.craft
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        _fixture_test_category2_cleanse_tags.CleanseTagTests.setUp(self)
        self.a.spec['skills']['집중']=4
        self.p.spec['skills']['집중']=4
        for actor,pos in ((self.a,(1,1)),(self.p,(2,1)),(self.q,(7,7))):
            actor.spec.update(size='Medium',capabilities=['Phasing'],movement={'land':6})
            actor.pos=pos
        self.e.everyone=[self.a,self.p,self.q]
        self.e.grid=Grid(90,90,walls=[((2,y),(3,y)) for y in range(80)]+[((5,1),(6,1))])
        self.craft()
        self.mount()
    def mount(self,event='mount',engine=None,**options):
        value=dict(event_id=event,surface_id='actual:continuous-wall',
            walls=[[[2,y],[3,y]] for y in range(80)],anchor_wall=[[2,1],[3,1]],
            method='taped',reason='GM observed actual tag taped to this existing continuous surface')
        value.update(options)
        return (engine or self.e).gm.observe_cleanse_barrier('tag:one',**value)
    def gate(self,actor=None,dest=(4,1),attempt='focus',faces=None,engine=None,**options):
        opts={'fixed':faces or [2,2,3,3]};opts.update(options)
        return TAG.phasing_passage(engine or self.e,actor or self.p,dest,
            checks={'tag:one':dict(attempt_id=attempt,skill_options=opts)})
    def restore(self):
        loaded=CODEC.load_engine(Rules(str(ROOT),ruleset='core'),CODEC.dump_engine(self.e))
        return loaded,W.actor_index(loaded)
    def test_actual_surface_and_radius_do_not_make_a_general_movement_wall(self):
        before=CODEC.dump_engine(self.e)
        self.assertTrue(TAG.phasing_passage(self.e,self.p,(2,4)))
        self.p.pos=(5,1)
        self.assertTrue(TAG.phasing_passage(self.e,self.p,(7,1)))
        self.p.pos=(2,32)
        self.assertTrue(TAG.phasing_passage(self.e,self.p,(4,32)))
        self.p.pos=(2,31)
        self.assertIsInstance(TAG.phasing_passage(self.e,self.p,(4,31)),C.PendingDecision)
        self.p.pos=(2,1)
        self.assertTrue(self.e.grid.wall_blocked((2,1),(4,1)))
        # Ordinary walking has no Cleanse Tag gate. A non-crossing movement is
        # allowed by the native body owner and the tag charges no invented cost.
        import body_state as BODY
        self.assertTrue(BODY.can_place(self.e,self.p,(2,2),origin=(2,1)))
        self.assertEqual(CODEC.dump_engine(self.e),before)
    def test_equal_focus_fails_individual_clock_and_exact_3600_retry_destroys_same_tag(self):
        maker=deepcopy(self.e._physical_objects['tag:one'][TAG.PROFILE])
        self.assertFalse(self.gate()) # tag power10, Focus10: strict greater
        row=self.e._physical_objects['tag:one'][TAG.BARRIER]['attempts']['focus']
        event=SF.event(self.e,self.p,row['roll_id'])
        self.assertEqual((event.state,event.final.total),('final',10))
        self.assertEqual(TAG.level(self.e,'tag:one'),10)
        self.e.advance_time(3599,[self.a,self.p,self.q])
        before=CODEC.dump_engine(self.e)
        self.assertFalse(self.gate(attempt='too-early',faces=[6]*4))
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.e.advance_time(1,[self.a,self.p,self.q])
        self.assertTrue(self.gate(attempt='retry',faces=[3]*4))
        obj=self.e._physical_objects['tag:one']
        self.assertEqual(obj[TAG.PROFILE],maker)
        self.assertEqual(obj['destroyed']['cleanse_attempt_id'],'retry')
        self.assertEqual(obj['destroyed']['by_actor_id'],self.p.entity_id)
        with self.assertRaises(ValueError):TAG.level(self.e,'tag:one')
        self.assertTrue(TAG.phasing_passage(self.e,self.a,(4,1)))
    def test_other_encroacher_and_remount_preserve_same_physical_lock(self):
        self.assertFalse(self.gate())
        self.e.gm.observe_cleanse_barrier('tag:one',event_id='remove',attached=False,reason='GM observed removal')
        self.mount(event='remount')
        before=CODEC.dump_engine(self.e)
        self.assertFalse(self.gate(attempt='bypass-remount',faces=[6]*4))
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.assertTrue(self.gate(actor=self.a,attempt='independent-A',faces=[3]*4))
    def test_retry_order_survives_dictionary_order_and_old_surface_removal(self):
        self.assertFalse(self.gate(attempt='z-first'))
        self.e.advance_time(3600,[self.a,self.p,self.q])
        self.assertFalse(self.gate(attempt='a-second'))
        loaded,index=self.restore()
        state=loaded._physical_objects['tag:one'][TAG.BARRIER]
        state['attempts']=dict(sorted(state['attempts'].items()))
        self.assertFalse(self.gate(actor=index[self.p.entity_id],attempt='third-too-early',engine=loaded,faces=[6]*4))
        # An old observation cannot invent a wall after that real surface is gone.
        loaded.grid.walls.clear()
        self.assertTrue(TAG.phasing_passage(loaded,index[self.p.entity_id],(4,1)))
        CODEC.dump_engine(loaded)
    def test_large_body_crossing_and_existing_wall_corner_geometry(self):
        self.p.spec['footprint']={'kind':'observed_cells','offsets':[[0,0],[1,-1]],'reason':'GM body cells'}
        self.p.pos=(1,32)
        self.assertIsInstance(TAG.phasing_passage(self.e,self.p,(3,32)),C.PendingDecision)
        grid=Grid(8,8,walls=[((1,1),(2,1))])
        self.assertFalse(grid.wall_blocked((1,1),(2,2)))
        grid.walls.add(((1,2),(2,2)))
        self.assertTrue(grid.wall_blocked((1,1),(2,2)))
        self.assertEqual(len(grid.wall_crossings((1,1),(2,2))),1)
    def test_unknown_partial_round_time_needs_actual_observation(self):
        self.assertFalse(self.gate())
        self.e.advance_time(3595,[self.a,self.p,self.q])
        self.e.unresolved_time_intervals.append({'known_seconds':0})
        self.assertIsInstance(self.gate(attempt='uncertain',faces=[6]*4),C.PendingDecision)
        before=CODEC.dump_engine(self.e)
        with self.assertRaises(ValueError):self.e.gm.observe_cleanse_retry_elapsed('tag:one',self.p,3606,reason='outside bounds')
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.e.gm.observe_cleanse_retry_elapsed('tag:one',self.p,3600,reason='GM observed five actual extra seconds')
        self.assertTrue(self.gate(attempt='observed-ready',faces=[3]*4))
    def test_both_restores_keep_failures_and_reject_forged_native_result_or_source(self):
        self.assertFalse(self.gate())
        self.e.gm.snapshot('barrier-failure')
        loaded,index=self.restore()
        self.assertFalse(self.gate(actor=index[self.p.entity_id],attempt='restored-early',engine=loaded,faces=[6]*4))
        self.e.gm.restore('barrier-failure')
        self.assertFalse(self.gate(attempt='gm-early',faces=[6]*4))
        self.assertTrue(self.e.validate_state()['valid'])
        row=loaded._physical_objects['tag:one'][TAG.BARRIER]['attempts']['focus']
        row['status']='passed';TAG._seal(row)
        with self.assertRaises(ValueError):CODEC.dump_engine(loaded)
        native=self.rules._selected_rule
        before=CODEC.dump_engine(self.e)
        with patch.object(self.rules,'_selected_rule',side_effect=lambda uid:'other' if uid==TAG.ITEM else native(uid)):
            with self.assertRaises(ValueError):self.gate()
        self.assertEqual(CODEC.dump_engine(self.e),before)
    def test_invalid_attachment_and_options_reject_before_any_actual_observation(self):
        before=CODEC.dump_engine(self.e)
        for options in ({'method':'balanced'},{'walls':[[[4,1],[5,1]]]}, {'anchor_wall':[[5,1],[6,1]]}):
            with self.assertRaises(ValueError):self.mount(event='invalid',**options)
            self.assertEqual(CODEC.dump_engine(self.e),before)
        with self.assertRaises(ValueError):self.gate(total=100)
        with self.assertRaises(ValueError):self.gate(faces=[7]*4)
        self.assertEqual(CODEC.dump_engine(self.e),before)
    def test_observed_feature_error_resumes_same_focus_after_json_restore(self):
        self.p.kind='trainer';self.p.spec['kind']='trainer'
        self.p.spec['feats']=[SF.MONKEY]
        self.p.spec['skills'].update({'전투':4,'집중':4,'육상':4})
        with self.assertRaisesRegex(ValueError,'boolean'):
            self.gate(feature=SF.MONKEY,feature_options={'decision':lambda first:None})
        state=self.e._physical_objects['tag:one'][TAG.BARRIER]
        row=state['attempts']['focus'];first=SF.event(self.e,self.p,row['roll_id']).first
        loaded,index=self.restore();actor=index[self.p.entity_id]
        before=loaded.rng.getstate()
        with self.assertRaises(ValueError):self.gate(actor=actor,attempt='new-ID',engine=loaded)
        self.assertFalse(self.gate(actor=actor,engine=loaded,feature=SF.MONKEY,feature_options={'decision':lambda seen:False}))
        self.assertEqual(SF.event(loaded,actor,row['roll_id']).first,first)
        self.assertEqual(loaded.rng.getstate(),before)
    def combat(self):
        for actor in (self.a,self.p):actor.spec['skills']['전투']=4
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
        self.e.grapple(self.a,self.p,challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,
            challenger_options={'fixed':[3]*4},defender_options={'fixed':[2]*4})
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.p,initiative_count=10)
    def escape(self,faces=None,request='escape'):
        return self.e.grapple_action(self.p,'escape',request_id=request,escape=dict(capability='Phasing',cost='shift',destination=[4,1],
            cleanse_checks={'tag:one':dict(attempt_id='native-focus',skill_options={'fixed':faces or [2,2,3,3]})}))
    def test_native_phasing_movement_consumer_keeps_failed_observation_and_blocks_real_position(self):
        self.combat();before=deepcopy(self.p.budget)
        self.assertFalse(self.escape())
        self.assertEqual((self.p.pos,self.p.budget),((2,1),before))
        self.assertIsNotNone(GR.relation(self.e,self.p))
        self.assertEqual(self.e._physical_objects['tag:one'][TAG.BARRIER]['attempts']['native-focus']['status'],'failed')
    def test_native_escape_without_tags_does_not_depend_on_cleanse_source_selection(self):
        from test_foundation_maneuvers_grapple import GrappleTests
        fixture=GrappleTests('test_phasing_escape_requires_actual_capability_own_turn_and_legal_range')
        fixture.r=self.rules;fixture.setUp();fixture.enter();fixture.turn_b()
        fixture.b.spec['capabilities']=['Phasing']
        native=self.rules._selected_rule
        with patch.object(self.rules,'_selected_rule',side_effect=lambda uid,**kw:'other' if uid==TAG.ITEM else native(uid,**kw)):
            out=fixture.e.grapple_action(fixture.b,'escape',escape=dict(capability='Phasing',cost='shift',destination=[4,1]))
        self.assertTrue(out['ended']);self.assertEqual(fixture.b.pos,(4,1))
    def test_success_destroys_tag_before_actual_native_movement_and_late_fault_cannot_erase_it(self):
        self.combat();before=deepcopy(self.p.budget)
        with patch.object(EXT,'on_enter_cell',side_effect=ValueError('late movement fault')):
            with self.assertRaisesRegex(ValueError,'late movement fault'):self.escape(faces=[3]*4)
        self.assertEqual((self.p.pos,self.p.budget),((2,1),before))
        self.assertTrue(W.physical_lifecycle(self.e._physical_objects['tag:one'])['destroyed'])
        self.assertTrue(self.escape(faces=[3]*4)['ended'])
        self.assertEqual((self.p.pos,self.p.budget['shift']),((4,1),0))
        before=CODEC.dump_engine(self.e)
        self.assertTrue(self.escape(faces=[3]*4)['ended'])
        self.assertEqual(CODEC.dump_engine(self.e),before)


if __name__=='__main__':unittest.main()
