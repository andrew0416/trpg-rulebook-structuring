"""R764 changes only the selectable Tornado Charge target predicate."""
import unittest
from unittest.mock import patch

import test_book_type_ace_acquisition as FIX
import test_book_type_ace_actions as ACTIONS
import test_book_type_ace_csv_full as CSV
from engine import Rules
import combat_timing as TIME
import frequency as FREQUENCY
import state_grants as GRANTS
import trainer_feature_acquisition as ACQUIRE
import turn as TURN
import type_ace as TA


class CsvTornadoEditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(FIX.ROOT, ruleset='all')

    setUp = FIX.TypeAceAcquisitionTests.setUp
    setup = FIX.TypeAceAcquisitionTests.setup
    add = FIX.TypeAceAcquisitionTests.add
    rejected = FIX.TypeAceAcquisitionTests.rejected
    valid = FIX.TypeAceAcquisitionTests.valid
    restore = FIX.TypeAceAcquisitionTests.restore
    combat = FIX.TypeAceAcquisitionTests.combat
    next_turn = FIX.TypeAceAcquisitionTests.next_turn
    branch = ACTIONS.TypeAceActionsTests.branch
    known = ACTIONS.TypeAceActionsTests.known
    native = ACTIONS.TypeAceActionsTests.native
    special = ACTIONS.TypeAceActionsTests.special

    def acquire(self, feature=None, branch='비행'):
        edition = getattr(self, 'tornado_edition', 'local_csv') if feature is not None and TA.uid(feature) == TA.uid('Tornado Charge') else None
        return CSV.TypeAceCsvTests.acquire(self, feature, branch, edition=edition)

    def test_csv_flying_predicate_does_not_replace_book_owned_sky_or_levitate_targets(self):
        for edition in (None, 'local_csv'):
            for types, mode in ((['비행'], 'land'), (['노말'], 'sky'), (['노말'], 'levitate')):
                with self.subTest(edition=edition, types=types, mode=mode):
                    self.tornado_edition = edition
                    self.branch('비행', 'Celerity', 'Tornado Charge')
                    self.e.gm.set_types(self.p, types, reason='actual selected Tornado target type')
                    self.e.gm.set_movement_capabilities(self.p,
                        {'land':6, 'sky':6 if mode == 'sky' else 0, 'levitate':6 if mode == 'levitate' else 0},
                        basis='base', reason='actual owned Sky or Levitate alternative')
                    self.restore()
                    self.assertEqual(TA.local_csv(self.t, TA.uid('Tornado Charge')), bool(edition))
                    self.combat(self.p)
                    operation = lambda:TA.tornado(self.e, self.t, self.p)
                    if edition and types == ['노말']:
                        self.rejected(operation, 'CSV Tornado Charge requires an actual Flying Pokemon')
                        self.assertIsNone(TA._tornado(self.p))
                    else:
                        operation()
                        self.assertEqual(self.p.budget['standard'], 3)
                        self.assertIsNotNone(TA._tornado(self.p))
                        self.restore()
                        self.e.end_of_turn(self.p)
                        self.assertIsNone(TA._tornado(self.p))
                    self.valid()

    def test_selected_csv_reuses_native_three_actions_shared_shift_cap_and_daily_limits(self):
        # The original full native scenario runs unchanged with only acquisition edition selected.
        ACTIONS.TypeAceActionsTests.test_tornado_three_restricted_standards_and_between_shifts_share_actual_cap_and_daily_target(self)
        self.restore()
        feature = TA.uid('Tornado Charge')
        self.assertEqual(TA.acquired(self.t, feature)['snapshot']['source']['record'], 764)
        self.next_turn(self.q)
        TA.tornado(self.e, self.t, self.q)
        self.assertEqual(self.q.budget['standard'], 3)
        self.u = self.add('third actual owned Flying Pokemon', 'pokemon', (11, 8),
            trainer_id=self.t.entity_id, types=['비행'])
        self.next_turn(self.u)
        TA.tornado(self.e, self.t, self.u)
        self.assertEqual(FREQUENCY.state(self.t)['activations'][feature]['used'], 3)
        self.v = self.add('fourth actual owned Flying Pokemon', 'pokemon', (12, 8),
            trainer_id=self.t.entity_id, types=['비행'])
        self.next_turn(self.v)
        self.rejected(lambda:TA.tornado(self.e, self.t, self.v), 'Feature frequency exhausted')
        self.assertIsNone(TA._tornado(self.v))
        self.valid()

    def test_csv_source_choice_replay_and_restore_keep_exact_homebrew_receipt(self):
        acquire = lambda edition:CSV.TypeAceCsvTests.acquire(self, 'Tornado Charge', '비행', edition=edition)
        with patch.object(self, 'rules', Rules(FIX.ROOT, ruleset='core')):
            self.branch('비행', 'Celerity')
            self.rejected(lambda:acquire('local_csv'), 'variant:홈브류')
        self.branch('비행', 'Celerity')
        self.rejected(lambda:acquire('unknown'), 'exact Type Ace CSV')
        with patch.object(TA, 'CSV_SHA256', '0' * 64):
            self.rejected(lambda:acquire('local_csv'), 'source changed')
        receipt = acquire('local_csv')
        self.assertEqual(acquire('local_csv')['request_id'], receipt['request_id'])
        self.rejected(lambda:acquire(None), 'optional selection')
        self.restore()
        feature = TA.uid('Tornado Charge')
        self.assertEqual(TA.acquired(self.t, feature)['snapshot']['source'], TA.csv_source(self.rules, feature))
        self.assertTrue(TA.local_csv(self.t, feature))
        self.valid()
        sid = next(k for k, value in self.t.spec[GRANTS.KEY]['sources'].items()
            if value.get('static_acquisition', {}).get('feature_id') == feature)
        self.t.spec[GRANTS.KEY]['sources'][sid]['static_acquisition']['snapshot']['source']['record'] = 260
        with self.assertRaisesRegex(ValueError, 'integrity|receipt'):
            ACQUIRE.validate_actor(self.t)

    def test_selected_csv_keeps_owned_target_and_before_action_initiative_boundary(self):
        self.branch('비행', 'Celerity', 'Tornado Charge')
        self.rejected(lambda:TA.tornado(self.e, self.t, self.p), 'gains-initiative boundary')
        self.combat(self.p)
        self.assertTrue(TURN.spend(self.e, self.p, 'swift', 'actual prior Swift action'))
        self.rejected(lambda:TA.tornado(self.e, self.t, self.p), 'gains-initiative boundary')
        self.e.gm.set_types(self.b, ['비행'], reason='actual foreign Flying Pokemon')
        self.next_turn(self.b)
        self.rejected(lambda:TA.tornado(self.e, self.t, self.b), 'actual owned Pokemon')
        self.assertFalse(any(row.get('ace_tornado') for row in TIME.records(self.b)))
        self.valid()


if __name__ == '__main__':
    unittest.main()
