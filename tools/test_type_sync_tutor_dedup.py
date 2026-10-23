"""Call-count regression only; actual Type Sync learning keeps its existing tests."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, call, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
import type_sync as S


class TypeSyncTutorDedupTests(unittest.TestCase):
    def test_normalized_names_resolve_once_in_first_seen_order_without_merging_aliases(self):
        resolved = {'Water Pulse': 'move/pulse', 'Pulse Alias': 'move/pulse',
                    'None': None, 'missing': None}
        rules = SimpleNamespace(
            learnsets={'one': {'tutor': ['Water Pulse (N)', 'Pulse Alias', None]},
                       'two': {'tutor': ['Water Pulse', 'Pulse Alias (n)', 'None (N)', 'missing']}},
            move=Mock(return_value={'type': 'Water'}),
            move_id=Mock(side_effect=resolved.__getitem__))
        spec = {'types': ['Water'], S.KEY: {'history': [{'chosen_type': 'Water'}]}}
        with patch.object(S, 'active', return_value={'learning': {'exceptions': {}}}):
            self.assertIs(S.learning_permission(rules, spec, 'move/pulse', 'tutor'), True)
        self.assertEqual(rules.move_id.call_args_list,
                         [call('Water Pulse'), call('Pulse Alias'), call('None'), call('missing')])

    def test_each_call_reselects_names_and_propagates_current_source_failure(self):
        rules = SimpleNamespace(
            learnsets={'one': {'tutor': ['Water Pulse', 'Water Pulse (N)']}},
            move=Mock(return_value={'type': 'Water'}),
            move_id=Mock(return_value=None))
        spec = {'types': ['Water'], S.KEY: {'history': [{'chosen_type': 'Water'}]}}
        with patch.object(S, 'active', return_value={'learning': {'exceptions': {}}}):
            self.assertIsNone(S.learning_permission(rules, spec, 'move/pulse', 'tutor'))
            rules.move_id.return_value = 'move/pulse'
            self.assertIs(S.learning_permission(rules, spec, 'move/pulse', 'tutor'), True)
            rules.move_id.side_effect = ValueError('selected source changed')
            with self.assertRaisesRegex(ValueError, 'selected source changed'):
                S.learning_permission(rules, spec, 'move/pulse', 'tutor')
        self.assertEqual(rules.move_id.call_args_list, [call('Water Pulse')] * 3)


if __name__ == '__main__':
    unittest.main()
