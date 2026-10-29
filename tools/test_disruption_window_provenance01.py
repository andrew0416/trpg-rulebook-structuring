"""Ordinary Free is not authority to keep an old Disruption hit alive."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import turn as TURN
import action_lifecycle as ACTION
import test_disruption_window_review01 as BASE


class DisruptionWindowProvenanceTests(unittest.TestCase):
    setUp = BASE.DisruptionWindowTests.setUp
    setup = BASE.DisruptionWindowTests.setup
    add = BASE.DisruptionWindowTests.add
    acquire = BASE.DisruptionWindowTests.acquire
    combat = BASE.DisruptionWindowTests.combat
    family = BASE.DisruptionWindowTests.family
    known = BASE.DisruptionWindowTests.known
    native = BASE.DisruptionWindowTests.native
    completed = BASE.DisruptionWindowTests.completed
    actual_hit = BASE.DisruptionWindowTests.actual_hit
    restored = BASE.DisruptionWindowTests.restored
    reject_unchanged = BASE.DisruptionWindowTests.reject_unchanged

    def test_unrelated_native_free_action_closes_window_even_with_same_kind_as_trickster(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                original = self.actual_hit()
                boundary = dict(ACTION.current_full_turn(self.e))
                before = list(self.p._action_history)
                self.assertTrue(TURN.spend(self.e, self.p, 'free', 'unrelated ordinary native Free action'))
                self.assertEqual(self.p._action_history, before + ['free'])
                self.assertEqual(ACTION.current_full_turn(self.e), boundary)
                if cold:
                    self.restored()
                self.reject_unchanged(original)


if __name__ == '__main__':
    unittest.main()
