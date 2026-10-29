"""Unexecuted native probes for the remaining Disruption trigger-window obligation.

No synthetic completion, action-history edit, clock edit, or callback is used.
The first four methods distinguish stale-trigger rejection from ordinary play;
the last preserves two different legitimate reactions to one actual Bug hit.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
import action_lifecycle as ACTION
import action_points as AP
import combat_timing as TIME
import frequency as F
import move_completion as COMPLETE
import trainer_feature_acquisition as ACQUIRE
import trickster as TRICK
import turn as TURN
import type_ace as TA
import test_disruption_trigger07 as BASE


class DisruptionWindowTests(unittest.TestCase):
    setup = BASE.DisruptionTriggerTests.setup
    add = BASE.DisruptionTriggerTests.add
    acquire = BASE.DisruptionTriggerTests.acquire
    combat = BASE.DisruptionTriggerTests.combat
    family = BASE.DisruptionTriggerTests.family
    known = BASE.DisruptionTriggerTests.known
    native = BASE.DisruptionTriggerTests.native
    completed = BASE.DisruptionTriggerTests.completed
    valid = BASE.DisruptionTriggerTests.valid
    restored = BASE.DisruptionTriggerTests.restored

    def setUp(self):
        self.rules = Rules(ROOT, ruleset='core')

    def actual_hit(self, *, encounter=True):
        self.family('벌레', 'Insectoid Utility', 'Disruption Order')
        if encounter:
            self.combat(self.p)
        self.native(self.p, self.b, 'move/시그널빔')
        row = self.completed()
        self.assertTrue(COMPLETE.recipient_result(row, self.b)['hit'])
        self.assertEqual(row['move']['type'], '벌레')
        self.assertEqual(row['full_turn'], ACTION.current_full_turn(self.e))
        return row['id']

    def reject_unchanged(self, completion_id):
        before = self.e.export_state()
        with self.assertRaises(ValueError):
            TA.react(self.e, self.t, self.p, TA.uid('Disruption Order'), completion_id)
        self.assertEqual(self.e.export_state(), before)
        self.assertFalse(any(r.get('ace_disruption') for r in TIME.records(self.b)))

    def apply_once(self, completion_id):
        trainer_history = list(getattr(self.t, '_action_history', []))
        self.assertTrue(TA.react(self.e, self.t, self.p, TA.uid('Disruption Order'), completion_id))
        rows = [r for r in TIME.records(self.b) if r.get('ace_disruption')]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['accuracy_modifier'], -3)
        self.assertEqual(self.t._action_history, trainer_history + ['free'])
        before = self.e.export_state()
        with self.assertRaisesRegex(ValueError, 'already consumed'):
            TA.react(self.e, self.t, self.p, TA.uid('Disruption Order'), completion_id)
        self.assertEqual(self.e.export_state(), before)
        self.assertIs(self.e.rulings, self.e.r.rulings)
        self.valid()

    def test_unrelated_own_swift_or_shift_closes_hit_window_in_same_full_turn(self):
        for kind in ('swift', 'shift'):
            for cold in (False, True):
                with self.subTest(kind=kind, cold=cold):
                    original = self.actual_hit()
                    witness = dict(ACTION.current_full_turn(self.e))
                    history = list(self.p._action_history)
                    # The actual shared ordinary-action owner, as in candidate06's
                    # existing Devious control; this is not a triggered Free action.
                    self.assertTrue(TURN.spend(self.e, self.p, kind, 'unrelated native ordinary action'))
                    self.assertEqual(self.p._action_history, history + [kind])
                    self.assertEqual(ACTION.current_full_turn(self.e), witness)
                    if cold:
                        self.restored()
                    self.reject_unchanged(original)

    def test_immediate_outside_combat_hit_remains_available_once(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                original = self.actual_hit(encounter=False)
                self.assertFalse(self.e.encounter_active)
                self.assertIsNone(ACTION.current_full_turn(self.e))
                if cold:
                    self.restored()
                self.apply_once(original)

    def test_elapsed_time_outside_combat_closes_old_hit_window(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                original = self.actual_hit(encounter=False)
                seconds, round_no = self.e.elapsed_seconds, self.e.round_no
                self.e.advance_time(1, self.e.everyone)
                self.assertEqual(self.e.elapsed_seconds, seconds + 1)
                self.assertEqual(self.e.round_no, round_no)
                self.assertIsNone(ACTION.current_full_turn(self.e))
                if cold:
                    self.restored()
                self.reject_unchanged(original)

    def test_new_scene_outside_combat_closes_old_hit_window(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                original = self.actual_hit(encounter=False)
                scene, round_no = F.state(self.p)['scene'], self.e.round_no
                self.e.end_scene()
                self.assertNotEqual(F.state(self.p)['scene'], scene)
                self.assertEqual(self.e.round_no, round_no)
                self.assertIsNone(ACTION.current_full_turn(self.e))
                if cold:
                    self.restored()
                self.reject_unchanged(original)

    def test_same_bug_hit_trickster_pokemon_free_action_preserves_distinct_disruption(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                self.family('벌레', 'Insectoid Utility', 'Disruption Order')
                self.e.gm.set_skill(self.t, '교활', 6, reason='actual Trickster prerequisite')
                ACQUIRE.acquire_static(self.e, self.t, TRICK.CLASS,
                    selection={'source': 'core'}, acquisition_request_id='disruption-window/trickster')
                self.e.gm.set_position(self.b, (3, 2), reason='actual Bug cone recipient')
                self.combat(self.p)
                self.native(self.p, self.b, 'move/실뿜기', aim=(3, 2))
                row = self.completed()
                original = row['id']
                self.assertEqual(row['move']['type'], '벌레')
                self.assertEqual(row['move']['class'], '변화')
                self.assertTrue(COMPLETE.recipient_result(row, self.b)['hit'])
                history = list(self.p._action_history)
                ap = AP.available(self.t)
                self.assertTrue(self.e.trickster_maneuver(
                    self.t, self.p, self.b, original, 'manipulate', 'terrorize',
                    defender_skill='집중', challenger_options={'fixed': [6] * 6},
                    defender_options={'fixed': [1] * 6}))
                self.assertEqual(self.p._action_history, history + ['free'])
                self.assertEqual(AP.available(self.t), ap - 1)
                self.assertEqual(self.e._move_completions[original]['full_turn'], ACTION.current_full_turn(self.e))
                # Explicitly demonstrates why copying Devious's exact-history
                # equality would reject a real same-hit reaction chain.
                self.assertNotEqual(self.e._move_completions[original]['skirmisher_boundary']['history'], self.p._action_history)
                if cold:
                    self.restored()
                self.apply_once(original)


if __name__ == '__main__':
    unittest.main()
