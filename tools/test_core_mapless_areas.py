"""C07-045 source169: actual described areas, ordinary Shift/Sprint and turn closure."""
from copy import deepcopy
import json,unittest
import test_mapless_space as BASE
import test_mapless_departure as DEPART
import world_entities as W,stamina as STAMINA
from state_codec import load_engine

class Tests(unittest.TestCase):
    setUpClass=classmethod(BASE.MaplessTests.setUpClass.__func__)
    setUp=BASE.MaplessTests.setUp;actor=BASE.MaplessTests.actor
    configure=BASE.MaplessTests.configure;snap=BASE.MaplessTests.snap

    def open_turn(self):
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
        self.assertIs(self.e._active_turn_actor,self.a)
        self.assertIsNone(self.e.grid)

    def quote(self,*,event='walk',destination='fountain',cost=4):
        return self.e.gm.observe_mapless_movement(self.a,event_id=event,
            destination=destination,movement_cost=cost,contacts_after=[],
            reason='GM source169: stairs to lobby center costs four; stairs to side corridor costs six')

    def test_actual_ordinary_turn_shift_between_described_areas_then_closes(self):
        self.open_turn();self.quote()
        result=self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(result['phase'],'complete')
        self.assertEqual(W.location_of(self.a),{'kind':'abstract','place_id':'fountain'})
        self.assertEqual(self.a._action_history,['shift']);self.assertEqual(self.a.budget['shift'],0)
        before=self.snap();self.assertEqual(result,self.e.move_abstract(self.a,event_id='walk'));self.assertEqual(before,self.snap())
        self.e.end_of_turn(self.a)
        self.assertIsNone(self.e._active_turn_actor);self.assertIs(self.e._turn_closures[-1]['actor'],self.a)
        self.assertEqual(W.location_of(self.a)['place_id'],'fountain')

    def test_source_corridor_requires_real_sprint_and_native_standard_plus_shift(self):
        self.open_turn();self.quote(destination='corridor',cost=6)
        before=self.snap()
        with self.assertRaisesRegex(ValueError,'allowance'):self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(before,self.snap())
        self.assertTrue(self.e.sprint(self.a,source_policy='ch06_once'))
        result=self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(result['phase'],'complete');self.assertEqual(W.location_of(self.a)['place_id'],'corridor')
        self.assertEqual(self.a._action_history,['standard','shift'])
        self.assertEqual((self.a.budget['standard'],self.a.budget['shift']),(0,0));self.assertNotIn('질주',self.a.custom_conditions)
        self.e.end_of_turn(self.a);self.assertIsNone(self.e._active_turn_actor)

    def test_actual_open_turn_and_observed_cost_restore_before_consumption(self):
        self.open_turn();self.quote()
        saved=self.e.gm.snapshot();export=json.loads(json.dumps(self.snap(),ensure_ascii=False))
        for restored in (load_engine(self.r,deepcopy(export)),self.e):
            if restored is self.e:self.e.gm.restore(saved)
            actor=W.actor_index(restored)[self.a.entity_id]
            self.assertIs(restored._active_turn_actor,actor)
            result=restored.move_abstract(actor,event_id='walk')
            self.assertEqual(result['phase'],'complete');self.assertEqual(actor._action_history,['shift'])
            before=restored.export_state();self.assertEqual(result,restored.move_abstract(actor,event_id='walk'));self.assertEqual(before,restored.export_state())
            restored.end_of_turn(actor);self.assertIsNone(restored._active_turn_actor)
            self.assertEqual(W.location_of(actor)['place_id'],'fountain')

    def test_actual_stamina_reaction_keeps_turn_open_until_same_shift_resumes(self):
        self.a.kind=self.a.spec['kind']='trainer';self.a.spec['edges']=[STAMINA.SOURCE]
        self.a.spec['skills']={'Athletics':5,'Acrobatics':4,'Combat':6}
        self.configure([[self.a.entity_id,self.b.entity_id]])
        self.open_turn();self.quote();self.e.rng.seed(5)
        result=self.e.move_abstract(self.a,event_id='walk');self.assertEqual(result['phase'],'pending')
        self.assertEqual(W.location_of(self.a)['place_id'],'stairs');self.assertEqual(self.a.budget['shift'],0)
        before=self.snap()
        with self.assertRaisesRegex(ValueError,'Stamina'):self.e.end_of_turn(self.a)
        self.assertEqual(before,self.snap())
        native=DEPART.Tests.native_pending(self);self.e.resolve_stamina(self.a,native,skill='육상')
        result=self.e.move_abstract(self.a,event_id='walk');self.assertEqual(result['phase'],'complete')
        self.assertEqual(self.a._action_history,['shift']);self.e.end_of_turn(self.a)
        self.assertIsNone(self.e._active_turn_actor);self.assertEqual(W.location_of(self.a)['place_id'],'fountain')

if __name__=='__main__':unittest.main()
