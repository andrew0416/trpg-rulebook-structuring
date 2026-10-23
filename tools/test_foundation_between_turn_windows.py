"""Actual between-turn admission reuses the certified native reaction/debt graph."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json, sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_initiative_schedule as F
import initiative_interrupts as I
import turn
from state_codec import dump_engine,load_engine,StateCodecError
from engine import Rules


class BetweenTurnWindowTests(unittest.TestCase):
    setUpClass=classmethod(F.InitiativeScheduleTests.setUpClass.__func__)
    setUp=F.InitiativeScheduleTests.setUp
    actor=F.InitiativeScheduleTests.actor
    prepare=F.InitiativeScheduleTests.prepare
    close=F.InitiativeScheduleTests.close
    borrow=F.InitiativeScheduleTests.borrow
    reaction=F.InitiativeScheduleTests.reaction

    def open_round(self):
        self.prepare();self.e.start_round([self.a,self.b,self.c])

    def queue_between(self,request):
        return self.e.queue_initiative_reactions([request],trigger=I.between_trigger(self.e))

    def test_unacted_borrow_executes_native_turn_and_closes_current_right_once(self):
        self.open_round();q=self.queue_between(self.borrow(self.b))
        self.e.begin_initiative_reaction(q['window_id'],'borrow')
        self.assertIs(self.e._active_turn_actor,self.b)
        self.assertTrue(I.between_frame(self.e))
        self.assertEqual(self.b.custom_conditions['combat_turn_serial'],1)
        hp=self.a.hp;self.e.use_move(self.b,self.a,'struggle')
        self.assertEqual(self.b.budget['standard'],0)
        self.assertLess(self.a.hp,hp)
        self.assertTrue(turn.spend(self.e,self.b,'shift'))
        self.e.finish_initiative_reaction();self.assertIsNone(self.e._active_turn_actor)
        self.close(self.a)
        with self.assertRaises(ValueError):self.e.start_of_turn(self.b)
        self.e.settle_borrowed_turn();self.close(self.c);self.e.end_round()
        self.assertEqual(self.b.custom_conditions['combat_turn_serial'],1)
        self.assertEqual(self.e.initiative_reaction_status()['owed_turns'],[])
        dump_engine(self.e)

    def test_action_only_frame_has_no_owner_clock_and_preserves_normal_remainder(self):
        self.open_round();q=self.queue_between(self.reaction(self.b))
        self.e.begin_initiative_reaction(q['window_id'],'react')
        self.assertEqual(self.b.custom_conditions.get('combat_turn_serial',0),0)
        self.assertEqual(self.b.budget,{'standard':1,'shift':0,'swift':0})
        self.e.use_move(self.b,self.a,'struggle')
        self.assertFalse(turn.spend(self.e,self.b,'shift'))
        self.e.finish_initiative_reaction();self.close(self.a)
        self.e.start_of_turn(self.b)
        self.assertEqual(self.b.budget,{'standard':0,'shift':1,'swift':1})
        self.assertEqual(self.b.custom_conditions['combat_turn_serial'],1)
        self.assertTrue(turn.spend(self.e,self.b,'shift'))
        self.e.end_of_turn(self.b);self.close(self.c);self.e.end_round();dump_engine(self.e)

    def test_acted_borrow_owes_next_round_slot_and_restore_keeps_the_debt(self):
        self.open_round();self.close(self.a)
        q=self.queue_between(self.borrow(self.a))
        self.e.begin_initiative_reaction(q['window_id'],'borrow')
        self.assertEqual(self.e.initiative_reaction_status()['owed_turns'][0]['due_round'],2)
        self.e.finish_initiative_reaction();self.close(self.b);self.close(self.c);self.e.end_round()
        e=load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(dump_engine(self.e))))
        a,b,c=[next(x for x in e.everyone if x.entity_id==v.entity_id) for v in (self.a,self.b,self.c)]
        with self.assertRaises(ValueError):e.prepare_initiative_schedule([b,c],source='gm/test-schedule')
        e.prepare_initiative_schedule([a,b,c],source='gm/test-schedule');e.start_round([a,b,c])
        e.settle_borrowed_turn();self.assertEqual(a.custom_conditions['combat_turn_serial'],2)
        e.start_of_turn(b);e.end_of_turn(b);e.start_of_turn(c);e.end_of_turn(c);e.end_round()
        self.assertEqual(e.initiative_reaction_status()['owed_turns'],[]);dump_engine(e)

    def test_open_frame_gm_and_fresh_rules_restore_preserve_none_parent(self):
        self.open_round();q=self.queue_between(self.borrow(self.b))
        self.e.begin_initiative_reaction(q['window_id'],'borrow')
        self.assertTrue(turn.spend(self.e,self.b,'standard'))
        self.e.gm.snapshot('between');self.e.finish_initiative_reaction();self.e.gm.restore('between')
        self.assertTrue(I.between_frame(self.e));self.assertEqual(self.b.budget['standard'],0)
        e=load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(dump_engine(self.e))))
        self.assertIsNone(I.frame(e)['parent']);e.finish_initiative_reaction()
        self.assertIsNone(e._active_turn_actor)
        with self.assertRaises(ValueError):e.begin_initiative_reaction(q['window_id'],'borrow')

    def test_wrong_or_stale_boundary_rejects_without_payment_rng_or_progress(self):
        self.open_round();stale=I.between_trigger(self.e);self.close(self.a)
        before=dump_engine(self.e)
        for bad in (stale,dict(I.between_trigger(self.e),epoch=99),dict(I.between_trigger(self.e),surplus=True)):
            with self.assertRaises(ValueError):self.e.queue_initiative_reactions([self.borrow(self.b)],trigger=bad)
            self.assertEqual(before,dump_engine(self.e))
        self.e.start_of_turn(self.b);before=dump_engine(self.e)
        with self.assertRaises(ValueError):I.between_trigger(self.e)
        self.assertEqual(before,dump_engine(self.e))

    def test_late_start_failure_restores_between_boundary_and_all_debts(self):
        self.open_round();q=self.queue_between(self.borrow(self.b));before=dump_engine(self.e)
        with patch('turn.reset_budget',side_effect=ValueError('late reset')):
            with self.assertRaises(ValueError):self.e.begin_initiative_reaction(q['window_id'],'borrow')
        self.assertEqual(before,dump_engine(self.e));self.assertIsNone(self.e._active_turn_actor)

    def test_nested_reaction_returns_to_borrow_then_actual_between_boundary(self):
        self.open_round();q=self.queue_between(self.borrow(self.b))
        self.e.begin_initiative_reaction(q['window_id'],'borrow')
        trigger={'kind':'reaction','window_id':q['window_id'],'request_id':'borrow'}
        nested=self.e.queue_initiative_reactions([self.reaction(self.c,'child')],trigger=trigger)
        self.e.begin_initiative_reaction(nested['window_id'],'child')
        self.assertTrue(turn.spend(self.e,self.c,'standard'));dump_engine(self.e)
        self.e.finish_initiative_reaction();self.assertIs(self.e._active_turn_actor,self.b)
        self.e.finish_initiative_reaction();self.assertIsNone(self.e._active_turn_actor);dump_engine(self.e)

    def test_ordered_whole_turns_keep_one_boundary_across_their_native_closures(self):
        self.open_round()
        requests=[self.borrow(self.b,'second'),self.borrow(self.c,'third')]
        boundary=I.between_trigger(self.e)
        ordinary_next=self.e.initiative_schedule_status()['next']
        q=self.e.queue_initiative_reactions(requests,trigger=boundary,order=['third','second'])
        self.assertEqual(q['order'],['third','second'])
        before=dump_engine(self.e)
        with self.assertRaises(ValueError):self.e.begin_initiative_reaction(q['window_id'],'second')
        self.assertEqual(before,dump_engine(self.e))
        for uid,actor in (('third',self.c),('second',self.b)):
            self.e.begin_initiative_reaction(q['window_id'],uid)
            self.assertIs(self.e._active_turn_actor,actor)
            self.assertEqual(I.frame(self.e)['window_id'],q['window_id'])
            self.assertIsNone(I.frame(self.e)['parent'])
            self.assertEqual(actor.custom_conditions['combat_turn_serial'],1)
            self.e.finish_initiative_reaction()
            self.assertIsNone(self.e._active_turn_actor)
            self.assertEqual(self.e.initiative_schedule_status()['next'],ordinary_next)
            self.assertEqual(I.between_trigger(self.e)['schedule_cursor'],boundary['schedule_cursor'])
        self.assertEqual([row['actor'] for row in self.e._turn_closures],[self.c,self.b])
        self.assertEqual(len(self.e.initiative_reaction_status()['owed_turns']),2)
        self.assertEqual({row['due_round'] for row in self.e.initiative_reaction_status()['owed_turns']},{1})
        self.close(self.a)
        for actor in (self.b,self.c):
            before=(actor.custom_conditions['combat_turn_serial'],self.e.elapsed_seconds,self.e.rng.getstate())
            with self.assertRaises(ValueError):self.e.start_of_turn(actor)
            self.e.settle_borrowed_turn()
            self.assertEqual((actor.custom_conditions['combat_turn_serial'],self.e.elapsed_seconds,self.e.rng.getstate()),before)
        self.assertEqual(self.e.initiative_reaction_status()['owed_turns'],[])
        self.e.end_round();dump_engine(self.e)
        self.assertEqual(self.e.elapsed_seconds,10)


if __name__=='__main__':unittest.main()
