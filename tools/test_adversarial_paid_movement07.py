"""Unexecuted adversarial probes over Stage5's real paid departure fixture."""
from copy import deepcopy
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch

ROOT = Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine
import action_metadata as META
import movement_actions as MOVE
import turn as TURN
import test_authority_candidate_pending02 as BASE


class PaidMovementCrossBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.CandidatePending02Tests.setUpClass()

    def returned_departure(self, kind):
        case = BASE.CandidatePending02Tests('runTest')
        f, mover, destination = case.completed_departure_wait(kind)
        self.assertIn(MOVE.COMMAND, mover.spec)
        self.assertIsNone(f.e._passive_pending)
        return case, f, mover, destination

    def test_returned_departure_tripped_refusal_does_not_lock_recovery_and_turn_end(self):
        case, f, mover, destination = self.returned_departure('burrow')
        origin = mover.pos
        paid = case.movement_payment(mover)
        f.e.gm.add_condition(mover, '넘어짐', reason='actual independent fall after returned departure')
        self.assertIn('넘어짐', mover.conditions)
        self.assertFalse(TURN.movement_permission(f.e, mover))
        with patch.object(Engine, 'd20', side_effect=AssertionError('returned departure cannot reroll')):
            result = case.transfer(f.e, mover, destination, 'burrow')
        self.assertFalse(result)
        self.assertEqual(mover.pos, origin)
        self.assertEqual(case.movement_payment(mover), paid)
        self.assertNotIn(MOVE.COMMAND, mover.spec,
            'terminal False with no unresolved reaction must not block native stand-up or turn end')
        self.assertIn('넘어짐', mover.conditions, 'cancelling movement must not cure the independent fall')
        with patch.object(Engine, 'd20', side_effect=AssertionError('spent opportunity must not reroll')):
            self.assertTrue(f.e.stand_up(mover))
        self.assertNotIn('넘어짐', mover.conditions)
        self.assertEqual(mover.budget, {'standard': 0, 'shift': 0, 'swift': 1})
        f.e.end_of_turn(mover)
        self.assertIsNone(f.e._active_turn_actor)

    def test_aerial_resume_cannot_spend_a_stale_larger_movement_allowance(self):
        case, f, mover, destination = self.returned_departure('aerial')
        origin = mover.pos
        paid = case.movement_payment(mover)
        progress = mover.spec[MOVE.COMMAND]['progress']
        self.assertEqual((progress['next'], progress['distance']), (0, 0),
            'the action is paid but no physical path distance has been spent')
        self.assertFalse(MOVE.capabilities(f.e, mover, environment=False).get('free_float', 0),
            'probe targets ordinary Sky, not the separate Free Floating live-distance adapter')
        f.e.gm.set_movement_capabilities(mover,
            {'land': 6, 'sky': 1, 'levitate': 6, 'burrow': 6, 'teleport': 6},
            basis='current', reason='actual Sky allowance reduced after returned departure')
        current = MOVE.distance_budget(f.e, mover, 'sky')
        self.assertLess(current, mover.spec[MOVE.COMMAND]['plan']['distance'])
        f.e, f.a, f.b, f.c, mover = case.restore_actors(f.e, f.a, f.b, f.c, mover)
        with patch.object(Engine, 'd20', side_effect=AssertionError('returned departure cannot reroll')):
            result = case.transfer(f.e, mover, destination, 'aerial')
        self.assertFalse(result)
        self.assertNotIn(MOVE.COMMAND, mover.spec, 'untravelled refused remainder must settle its paid command')
        self.assertEqual(mover.pos, origin,
            'same paid intent must not move farther than the currently permitted Sky allowance')
        self.assertEqual(case.movement_payment(mover), paid)
        self.assertEqual(MOVE.distance_budget(f.e, mover, 'sky'), current)

    def test_aerial_current_exact_allowance_still_resumes_once_after_cold_restore(self):
        case, f, mover, destination = self.returned_departure('aerial')
        paid = case.movement_payment(mover)
        f.e.gm.set_movement_capabilities(mover,
            {'land': 6, 'sky': 3, 'levitate': 6, 'burrow': 6, 'teleport': 6},
            basis='current', reason='actual current allowance equals the untravelled declared distance')
        self.assertEqual(MOVE.distance_budget(f.e, mover, 'sky'),
                         mover.spec[MOVE.COMMAND]['plan']['distance'])
        f.e, f.a, f.b, f.c, mover = case.restore_actors(f.e, f.a, f.b, f.c, mover)
        with patch.object(Engine, 'd20', side_effect=AssertionError('paid departure must not reroll')):
            result = case.transfer(f.e, mover, destination, 'aerial')
        self.assertTrue(result);self.assertEqual(mover.pos, destination)
        self.assertEqual(case.movement_payment(mover), paid)
        self.assertNotIn(MOVE.COMMAND, mover.spec)

    def test_aerial_live_allowance_reuses_unspent_native_sprint_modifier_without_repayment(self):
        case = BASE.CandidatePending02Tests('runTest')
        f, mover, destination = case.movement_world(overwatch=False)
        self.assertTrue(f.e.sprint(mover, source_policy='ch06_once'))
        import passive_events as PASSIVE
        with patch.object(Engine, 'd20', return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending) as caught:
                case.transfer(f.e, mover, destination, 'aerial')
        with patch.object(Engine, 'd20', side_effect=AssertionError('actual departure accuracy already observed')):
            f.e.choose_move_defense(caught.exception.event_id, mover, use=False,
                                   reason='finish actual departure before current capability observation')
        paid = case.movement_payment(mover)
        self.assertEqual((mover.spec[MOVE.COMMAND]['progress']['next'],
                          mover.spec[MOVE.COMMAND]['progress']['distance']), (0, 0))
        self.assertIn('질주', mover.custom_conditions)
        f.e.gm.set_movement_capabilities(mover,
            {'land': 6, 'sky': 2, 'levitate': 6, 'burrow': 6, 'teleport': 6},
            basis='current', reason='current Sky plus the still-unspent native Sprint funds this exact remainder')
        self.assertEqual(MOVE.distance_budget(f.e, mover, 'sky'), 3)
        f.e, f.a, f.b, f.c, mover = case.restore_actors(f.e, f.a, f.b, f.c, mover)
        with patch.object(Engine, 'd20', side_effect=AssertionError('paid Sprint movement must not reroll')):
            result = case.transfer(f.e, mover, destination, 'aerial')
        self.assertTrue(result);self.assertEqual(mover.pos, destination)
        self.assertEqual(case.movement_payment(mover), paid)
        self.assertNotIn('질주', mover.custom_conditions)
        self.assertNotIn(MOVE.COMMAND, mover.spec)

    def test_compound_cost_cannot_escape_returned_paid_departure(self):
        case, f, mover, destination = self.returned_departure('burrow')
        before = f.e.export_state()
        with self.assertRaisesRegex(ValueError, 'paid movement'):
            TURN.spend(f.e, mover, META.ActionCost(('standard', 'swift')),
                       'unrelated compound activation during paid movement')
        self.assertEqual(f.e.export_state(), before)
        with patch.object(Engine, 'd20', side_effect=AssertionError('returned departure cannot reroll')):
            case.transfer(f.e, mover, destination, 'burrow')
        self.assertNotIn(MOVE.COMMAND, mover.spec)
        self.assertTrue(TURN.spend(f.e, mover, META.ActionCost(('standard', 'swift')),
                                  'compound activation after completed movement'))
        self.assertEqual(mover.budget, {'standard': 0, 'shift': 0, 'swift': 0})


if __name__ == '__main__':
    unittest.main()