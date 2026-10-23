"""Actual mapless contact departure uses native attacks and paid continuation."""
from copy import deepcopy
import json,unittest
from unittest.mock import patch
import test_mapless_space as BASE
import mapless_space as SPACE,world_entities as W,turn as TURN,action_lifecycle as ACTION
from state_codec import load_engine
import stamina as STAMINA

class Tests(BASE.MaplessFixture):
    def departing(self,*,stamina=False,multiple=False):
        if stamina:
            self.a.kind=self.a.spec['kind']='trainer'
            self.a.spec['edges']=[STAMINA.SOURCE]
            self.a.spec['skills']={'Athletics':5,'Acrobatics':4,'Combat':6}
        contacts=[[self.a.entity_id,self.b.entity_id]]
        if multiple:contacts.append([self.a.entity_id,self.c.entity_id])
        self.configure(contacts)
        self.movement();self.e.rng.seed(5)

    def native_pending(self):
        action=next(row for row in self.e._native_action_resolutions.values()
            if any(t['actor'] is self.a and t['source']==STAMINA.SOURCE for t in row['triggers']))
        return action['id']

    def test_native_contact_departure_attacks_only_the_actual_left_opponent_once(self):
        self.configure([[self.a.entity_id,self.b.entity_id],[self.a.entity_id,self.c.entity_id]])
        self.movement(contacts=[[self.a.entity_id,self.c.entity_id]])
        self.e.rng.seed(6);hp=self.a.hp
        result=self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(result['phase'],'complete');self.assertTrue(self.b.aoo_used)
        self.assertFalse(getattr(self.c,'aoo_used',False));self.assertLess(self.a.hp,hp)
        self.assertEqual(self.a._action_history,['shift']);self.assertEqual(self.a.budget['shift'],0)
        self.assertTrue(self.e.adjacent(self.a,self.c));self.assertFalse(self.e.adjacent(self.a,self.b))
        before=self.snap();self.assertEqual(result,self.e.move_abstract(self.a,event_id='walk'))
        self.assertEqual(self.snap(),before)

    def test_actual_stamina_wait_keeps_origin_and_cost_then_resumes_without_repeat(self):
        self.departing(stamina=True,multiple=True)
        result=self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(result['phase'],'pending');self.assertEqual(W.location_of(self.a)['place_id'],'stairs')
        self.assertEqual(self.a._action_history,['shift']);self.assertEqual(self.a.budget['shift'],0)
        paid=deepcopy(self.a.budget);hp=self.a.hp;first=self.b.entity_id
        self.assertTrue(self.b.aoo_used);self.assertFalse(getattr(self.c,'aoo_used',False))
        with self.assertRaisesRegex(ValueError,'Stamina'):self.e.move_abstract(self.a,event_id='walk')
        self.e.resolve_stamina(self.a,self.native_pending(),skill='육상')
        self.e.move_abstract(self.a,event_id='walk')
        self.assertTrue(next(c for c in self.e.everyone if c.entity_id==first).aoo_used)
        self.assertTrue(self.c.aoo_used);self.assertEqual(self.a.budget,paid)
        if self.e._mapless_space['movements']['walk']['phase']=='pending':
            pending=next(row for row in self.e._native_action_resolutions.values()
                if any(t['actor'] is self.a and t['status']!='completed' for t in row['triggers']))
            self.e.resolve_stamina(self.a,pending['id'],skill='육상')
            self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(W.location_of(self.a)['place_id'],'fountain')
        self.assertEqual(self.a._action_history,['shift']);self.assertEqual(self.a.budget,paid)

    def test_pending_native_departure_cold_and_gm_restore_continue_same_payment(self):
        self.departing(stamina=True)
        self.assertEqual(self.e.move_abstract(self.a,event_id='walk')['phase'],'pending')
        saved=self.e.gm.snapshot();export=json.loads(json.dumps(self.snap(),ensure_ascii=False))
        for restored in (load_engine(self.r,deepcopy(export)),self.e):
            if restored is self.e:self.e.gm.restore(saved)
            actor=next(c for c in restored.everyone if c.entity_id==self.a.entity_id)
            paid=deepcopy(actor.budget);hp=actor.hp;rng=restored.rng.getstate()
            action=next(row for row in restored._native_action_resolutions.values() if any(t['actor'] is actor for t in row['triggers']))
            restored.resolve_stamina(actor,action['id'],skill='육상')
            result=restored.move_abstract(actor,event_id='walk')
            self.assertEqual(result['phase'],'complete');self.assertEqual(actor.budget,paid)
            self.assertEqual(actor.hp,hp);self.assertEqual(restored.rng.getstate(),rng)
            self.assertEqual(W.location_of(actor)['place_id'],'fountain')

    def test_pending_blocks_new_action_reset_and_turn_end_after_choice(self):
        self.departing(stamina=True);self.e.move_abstract(self.a,event_id='walk')
        self.e.resolve_stamina(self.a,self.native_pending(),skill='육상');before=self.snap()
        for action in (lambda:TURN.spend(self.e,self.a,'standard'),lambda:ACTION.check_end(self.e,self.a),
                       lambda:self.configure(),lambda:self.e.end_of_turn(self.a),
                       lambda:self.e.end_encounter(),lambda:self.e.end_round(),
                       lambda:self.e.start_round(self.e.everyone),lambda:self.e.end_scene()):
            with self.assertRaisesRegex(ValueError,'already paid mapless'):action()
            self.assertEqual(before,self.snap())
        self.e.move_abstract(self.a,event_id='walk')
        self.assertTrue(TURN.spend(self.e,self.a,'standard'))

    def test_late_failure_rolls_back_real_aoo_hp_rng_budget_and_frame(self):
        self.departing();before=self.snap();original=W.observe_location
        def fail(*args,**kwargs):
            original(*args,**kwargs);raise ValueError('late observed departure failure')
        with patch.object(W,'observe_location',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'late observed'):self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(self.snap(),before)
        self.assertFalse(getattr(self.b,'aoo_used',False))

    def test_paid_observation_tampering_refuses_before_replay_or_restore(self):
        self.departing(stamina=True);self.e.move_abstract(self.a,event_id='walk')
        saved=self.e.gm.snapshot();before=self.snap()
        row=self.e.gm.snapshots[saved]['engine']['_mapless_space']['movements']['walk']
        row['next_departure']=0
        with self.assertRaisesRegex(ValueError,'observation changed'):self.e.gm.restore(saved)
        self.assertEqual(self.snap(),before)

    def test_native_knockout_at_departure_stops_travel_after_one_paid_attempt(self):
        self.departing();self.a.hp=1
        result=self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(result['phase'],'stopped');self.assertTrue(self.a.fainted)
        self.assertEqual(W.location_of(self.a)['place_id'],'stairs')
        self.assertTrue(self.b.aoo_used);self.assertEqual(self.a._action_history,['shift'])
        before=self.snap();self.assertEqual(self.e.move_abstract(self.a,event_id='walk'),result)
        self.assertEqual(self.snap(),before)

    def test_sprint_allowance_survives_native_reaction_wait_without_second_action(self):
        self.departing(stamina=True)
        self.movement(6,event='sprint-walk')
        self.assertTrue(self.e.sprint(self.a,source_policy='ch06_once'))
        self.assertEqual(self.e.move_abstract(self.a,event_id='sprint-walk')['phase'],'pending')
        paid=deepcopy(self.a.budget)
        self.assertEqual(self.a._action_history,['standard','shift'])
        self.assertNotIn('질주',self.a.custom_conditions)
        self.e.resolve_stamina(self.a,self.native_pending(),skill='육상')
        self.assertEqual(self.e.move_abstract(self.a,event_id='sprint-walk')['phase'],'complete')
        self.assertEqual(self.a.budget,paid);self.assertEqual(W.location_of(self.a)['place_id'],'fountain')

if __name__=='__main__':unittest.main()
