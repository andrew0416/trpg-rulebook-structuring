"""One read-only canonical-baseline probe for accepted trigger continuation."""
from copy import deepcopy
import json
import unittest

import effect_contracts as CONTRACTS
from state_codec import dump_engine
import test_historical_effect_source_closure as FIXTURE


class EndTurnBoundaryProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIXTURE.AcceptedTriggerSources.setUpClass()

    def test_accepted_end_turn_condition_receipt_remains_resumable(self):
        f = FIXTURE.AcceptedTriggerSources()
        f.base = FIXTURE.AcceptedTriggerSources.base
        f.setUp()
        f.register(effects=[dict(type='stage_change', stat='atk', delta=1, target='self',
                                 **{'if': 'target was asleep'}),
                            dict(type='stage_change', stat='def', delta=1, target='self')])
        before = dump_engine(f.e)
        invocation_error = None
        try:
            returned = f.e.end_of_turn(f.a)
        except Exception as error:
            returned = None
            invocation_error = (type(error).__name__, str(error))
        rows = getattr(f.e, '_effect_dispatch_receipts', {})
        pending = [(token, row) for token, row in rows.items() if row['status'] == 'condition_unknown']
        summary = dict(invocation_error=invocation_error, returned=returned,
                       state_changed=before != dump_engine(f.e),
                       stage=dict(f.a.stages),
                       rows=[dict(source=row['source_id'], status=row['status'],
                                  effect_type=row['effect']['type']) for row in rows.values()])
        if pending:
            token, row = pending[0]
            summary['request_boundary'] = row['condition_request']['boundary']
            summary['current_boundary'] = CONTRACTS.boundary(f.e, f.a, row['target'])
            stable = dump_engine(f.e)
            try:
                summary['resolve_result'] = f.e.resolve_effect_condition(
                    f.a, token, target_was_asleep=True, reason='actual explicit historical observation')
            except Exception as error:
                summary['resolve_error'] = (type(error).__name__, str(error))
            summary['failed_resolve_changed_state'] = stable != dump_engine(f.e)
            try:
                f.e.advance_time(1, [f.a])
                summary['next_time_boundary'] = 'accepted'
            except Exception as error:
                summary['next_time_boundary_error'] = (type(error).__name__, str(error))
        print('ACTUAL_END_TURN_PENDING_PROBE', json.dumps(summary, ensure_ascii=False, default=str))
        if invocation_error:
            # An explicit rejection before mutation can be a valid unsupported
            # contract; preserve details rather than calling it continuation.
            self.assertEqual(dump_engine(f.e), before)
            return
        self.assertTrue(pending, 'the accepted unknown condition must produce its real request')
        self.assertNotIn('resolve_error', summary,
                         'accepted end_turn condition receipt became stale before its public resolve')
        self.assertEqual((f.a.stages['atk'], f.a.stages['def']), (1, 1))


if __name__ == '__main__':
    unittest.main()
