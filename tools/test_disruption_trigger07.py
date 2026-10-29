"""Disruption's actual Bug-hit trigger cannot be stored across full turns."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
import combat_timing as TIME
import type_ace as TA
import test_book_type_ace_reactions as FIX
import test_book_type_ace_acquisition as ACQUIRE_FIX


class DisruptionTriggerTests(unittest.TestCase):
    setup = FIX.TypeAceReactionTests.setup
    add = FIX.TypeAceReactionTests.add
    acquire = FIX.TypeAceReactionTests.acquire
    combat = FIX.TypeAceReactionTests.combat
    family = FIX.TypeAceReactionTests.family
    known = FIX.TypeAceReactionTests.known
    native = FIX.TypeAceReactionTests.native
    completed = FIX.TypeAceReactionTests.completed
    valid = FIX.TypeAceReactionTests.valid

    def setUp(self):
        self.rules = Rules(ROOT, ruleset='core')
        self.setup()

    def hit(self):
        self.family('벌레', 'Insectoid Utility', 'Disruption Order')
        self.known(self.b, 'move/물대포')
        self.combat(self.p)
        self.native(self.p, self.b, 'move/시그널빔')
        self.assertIs(self.e.rulings, self.e.r.rulings)
        return self.completed()['id']

    def restored(self):
        ACQUIRE_FIX.TypeAceAcquisitionTests.restore(self)
        self.assertIs(self.e.rulings, self.e.r.rulings)

    def reject_unchanged(self, original):
        before = self.e.export_state()
        with self.assertRaisesRegex(ValueError, 'triggering native full turn'):
            TA.react(self.e, self.t, self.p, TA.uid('Disruption Order'), original)
        self.assertEqual(self.e.export_state(), before)
        self.assertFalse(any(row.get('ace_disruption') for row in TIME.records(self.b)))

    def test_disruption_native_hit_current_turn_survives_cold_restore_and_pays_once(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                original = self.hit()
                if cold:
                    self.restored()
                before_history = list(getattr(self.t, '_action_history', []))
                self.assertTrue(TA.react(self.e, self.t, self.p, TA.uid('Disruption Order'), original))
                rows = [row for row in TIME.records(self.b) if row.get('ace_disruption')]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['accuracy_modifier'], -3)
                self.assertEqual(rows[0]['turn_deadline'], self.p.custom_conditions['combat_turn_serial'] + 1)
                self.assertEqual(self.t._action_history, before_history + ['free'])
                before = self.e.export_state()
                with self.assertRaisesRegex(ValueError, 'already consumed'):
                    TA.react(self.e, self.t, self.p, TA.uid('Disruption Order'), original)
                self.assertEqual(self.e.export_state(), before)
                self.valid()

    def test_disruption_old_hit_rejected_after_another_native_turn_attack_even_after_restore(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                original = self.hit()
                original_round = self.e.round_no
                self.e.end_of_turn(self.p)
                self.e.start_of_turn(self.b, initiative_count=20)
                self.native(self.b, self.q, 'move/물대포')
                self.assertEqual(self.e.round_no, original_round)
                if cold:
                    self.restored()
                self.reject_unchanged(original)

    def test_disruption_old_hit_rejected_when_native_trigger_turn_has_ended(self):
        original = self.hit()
        self.e.end_of_turn(self.p)
        self.reject_unchanged(original)


if __name__ == '__main__':
    unittest.main()