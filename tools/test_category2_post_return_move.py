"""Independent whole-Move return receipts; no ability completion claim."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Rules, Engine, Combatant
from state_codec import dump_engine, load_engine
import move_completion as COMPLETE
import passive_events as PASSIVE
import initiative_interrupts as INIT
import maneuver_grants as GRANTS
import test_foundation_initiative_schedule as FOUNDATION
import test_category2_move_defense_reactions as DEFENSE_FIXTURE


class PostReturnMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')
        DEFENSE_FIXTURE.MoveDefenseReactionsTests.setUpClass()

    actor = FOUNDATION.InitiativeScheduleTests.actor
    prepare = FOUNDATION.InitiativeScheduleTests.prepare
    start = FOUNDATION.InitiativeScheduleTests.start
    reaction = FOUNDATION.InitiativeScheduleTests.reaction

    def setUp(self):
        FOUNDATION.InitiativeScheduleTests.setUp(self)
        # The existing Moxie registration supplies a native passive producer.
        spec = deepcopy(self.a.spec)
        spec.update(kind='pokemon', abilities=['자기과신'], types=['불꽃'],
                    moves=['struggle', 'move/불사르기', 'move/괴력'])
        self.a = Combatant(self.r, spec)
        self.a.side, self.b.side, self.c.side = 'party', 'wild', 'wild'
        self.e.everyone = self.e.gm.everyone = [self.a, self.b, self.c]
        self.e.register_abilities(self.a)
        self.start()

    def event(self):
        return list(self.e._passive_events.values())[-1]['id']

    def queue_at(self, engine, event_id):
        return engine.queue_initiative_reactions([self.reaction(self.b)],
            trigger={'kind':'move', 'event_id':event_id})

    def test_native_single_return_and_initiative_join_are_read_only(self):
        self.e.use_move(self.a, self.b, 'struggle', set_damage=True)
        event_id = self.event()
        before = (self.a.budget.copy(), self.a.move_uses.copy(), self.b.hp,
                  self.e.rng.getstate(), deepcopy(self.a._action_history))
        returned = COMPLETE.require_returned_event(self.e, event_id)
        hit = COMPLETE.require_hit_return(self.e, event_id, self.b)
        self.assertEqual(returned['parent_event_id'], event_id)
        self.assertEqual(returned['targets'], [self.b.entity_id])
        self.assertEqual(returned['recipient_id'], self.b.entity_id)
        self.assertTrue(hit['result']['hit'])
        self.assertFalse(hit['result']['hit_prevented'])
        json.dumps(returned)
        queued = self.queue_at(self.e, event_id)
        window = self.e._initiative_interrupts['windows'][queued['window_id']]
        self.assertEqual(window['trigger']['move_return'], returned)
        self.assertEqual(before, (self.a.budget, self.a.move_uses, self.b.hp,
                                 self.e.rng.getstate(), self.a._action_history))

    def test_unsealed_area_target_return_cannot_open_move_reaction(self):
        # Reuse the established completion fixture's explicit target binding.
        self.e.targets_in_range = lambda *args: [self.b, self.c]
        native_return = COMPLETE.record_return
        captured = []

        def observe(engine, event_id, **kwargs):
            native_return(engine, event_id, **kwargs)
            event = engine._passive_events[event_id]
            row = engine._move_completions[event['completion_id']]
            if captured or event['target'].entity_id != self.b.entity_id:
                return
            captured.append(event_id)
            self.assertEqual(event['phase'], 'producer_return_boundary')
            self.assertIn(event['status'], ('applied', 'inapplicable'))
            self.assertFalse(row['sealed'])
            self.assertEqual(set(row['results']), {self.b.entity_id})
            before = (deepcopy(getattr(engine,INIT.KEY,None)), engine.rng.getstate(),
                      event['actor'].budget.copy())
            with self.assertRaises(ValueError):
                COMPLETE.require_returned_event(engine, event_id)
            with self.assertRaises(ValueError):
                self.queue_at(engine, event_id)
            self.assertEqual(before, (getattr(engine,INIT.KEY,None),
                                     engine.rng.getstate(), event['actor'].budget))

        with patch.object(self.e, 'accuracy_check', return_value=(True,10,False)), \
                patch.object(self.e, 'roll_damage', return_value=1), \
                patch.object(COMPLETE, 'record_return', side_effect=observe):
            self.e.use_move_on(self.a, self.b, 'move/불사르기', self.e.everyone)
        del self.e.targets_in_range
        self.assertEqual(len(captured), 1)
        receipt = COMPLETE.require_returned_event(self.e, captured[0])
        self.assertEqual(receipt['targets'], [self.b.entity_id, self.c.entity_id])
        self.assertEqual(set(receipt['results']), {self.b.entity_id, self.c.entity_id})

    def test_real_pending_strength_effect_blocks_return_even_after_target(self):
        from grid import Grid
        import world_entities as WORLD
        import body_state as BODY
        self.e.grid = Grid(10,10)
        for actor, cell in ((self.a,(2,2)), (self.b,(3,2)), (self.c,(8,8))):
            WORLD.observe_location(self.e,actor,{'kind':'grid','cell':cell},
                reason='explicit adjacent positions for the actual Strength maneuver')
            BODY.observe(self.e,actor,[(0,0)],reason='observed one-cell fixture body')
        with patch.object(self.e, 'accuracy_check', return_value=(True,10,False)), \
                patch.object(self.e, 'roll_damage', return_value=20):
            self.e.use_move(self.a, self.b, 'move/괴력')
        event_id = self.event()
        event = self.e._passive_events[event_id]
        row = self.e._move_completions[event['completion_id']]
        self.assertEqual(event['phase'], 'producer_return_boundary')
        self.assertEqual(set(row['results']), {self.b.entity_id})
        pending = [x for x in self.e._effect_dispatch_receipts.values()
                   if x.get('status') == 'awaiting_input']
        self.assertTrue(pending, repr(self.e._effect_dispatch_receipts))
        held = pending[0]
        self.assertNotEqual(row['phase'], 'complete')
        with self.assertRaises(ValueError):
            COMPLETE.require_returned_event(self.e, event_id)
        with self.assertRaises(ValueError):
            self.queue_at(self.e, event_id)
        # The pending child is real and can finish without re-paying the Move.
        before = (self.a.budget.copy(), self.a.move_uses.copy(), self.b.hp,
                  self.e.rng.getstate())
        GRANTS.resolve(self.e, self.a, held['result'].grant_id, accept=False)
        self.assertEqual(row['phase'], 'complete')
        returned = COMPLETE.require_hit_return(self.e,event_id,self.b)
        self.assertEqual(returned['recipient_id'],self.b.entity_id)
        self.queue_at(self.e,event_id)
        json.dumps(returned)
        cold=load_engine(Rules(ROOT,ruleset='core'),
                         json.loads(json.dumps(dump_engine(self.e))))
        b=next(a for a in cold.everyone if a.entity_id==self.b.entity_id)
        self.assertEqual(COMPLETE.require_hit_return(cold,event_id,b),returned)
        self.assertEqual(before, (self.a.budget, self.a.move_uses, self.b.hp,
                                 self.e.rng.getstate()))

    def test_actual_intercept_child_only_authenticates_actual_hit_recipient(self):
        f = DEFENSE_FIXTURE.MoveDefenseReactionsTests(
            'test_melee_success_hits_interceptor_and_preserves_original_accuracy')
        f.setUp()
        f.watch()
        parent_id = f.waiting()
        f.choose(parent_id, options=f.melee())
        row = f.completion()
        child_id = row['received'][f.r.entity_id]['child_event']
        returned = COMPLETE.require_returned_event(f.e, child_id)
        self.assertEqual(returned['parent_event_id'], parent_id)
        self.assertEqual(returned['targets'], [f.t.entity_id])
        self.assertEqual(returned['recipient_id'], f.r.entity_id)
        self.assertTrue(COMPLETE.require_hit_return(f.e, child_id, f.r)['result']['hit'])
        COMPLETE.require_returned_event(f.e, parent_id)
        for event_id, recipient in ((parent_id,f.t), (parent_id,f.r), (child_id,f.t)):
            with self.subTest(event_id=event_id, recipient=recipient.entity_id):
                with self.assertRaises(ValueError):
                    COMPLETE.require_hit_return(f.e, event_id, recipient)
        before = (f.t.hp, f.r.hp, f.a.move_uses.copy(), f.e.rng.getstate())
        cold = load_engine(Rules(ROOT,ruleset='core'),
                           json.loads(json.dumps(dump_engine(f.e))))
        actual = next(a for a in cold.everyone if a.entity_id == f.r.entity_id)
        self.assertEqual(COMPLETE.require_hit_return(cold, child_id, actual),
                         COMPLETE.require_hit_return(f.e, child_id, f.r))
        self.assertEqual(before, (f.t.hp, f.r.hp, f.a.move_uses, f.e.rng.getstate()))

    def test_single_return_cold_restore_retains_native_join_without_replay(self):
        self.e.use_move(self.a, self.b, 'struggle', set_damage=True)
        event_id = self.event()
        receipt = COMPLETE.require_hit_return(self.e, event_id, self.b)
        cold = load_engine(Rules(ROOT,ruleset='core'),
                           json.loads(json.dumps(dump_engine(self.e))))
        b = next(a for a in cold.everyone if a.entity_id == self.b.entity_id)
        before = (cold.everyone[0].move_uses.copy(), b.hp, cold.rng.getstate())
        self.assertEqual(COMPLETE.require_hit_return(cold,event_id,b), receipt)
        self.queue_at(cold, event_id)
        self.assertEqual(before, (cold.everyone[0].move_uses, b.hp, cold.rng.getstate()))


if __name__ == '__main__':
    unittest.main()
