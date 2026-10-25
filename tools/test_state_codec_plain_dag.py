"""Selected-rule normalization preserves bytes and validates each fresh call."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from state_codec import StateCodecError, _plain


class SelectedRuleNormalizationTests(unittest.TestCase):
    def encoded(self, value):
        return json.dumps(_plain(value), sort_keys=True, ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False)

    def test_shared_converted_data_keeps_exact_encoding_and_next_call_mutation(self):
        shared = {'한글': (1, {'z', 'a'}), 'finite': -0.0}
        value = {'b': shared, 'a': [shared, shared]}
        plain = {'한글': [1, {'set': ['a', 'z']}], 'finite': -0.0}
        expected = json.dumps({'b': plain, 'a': [plain, plain]}, sort_keys=True,
                              ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        self.assertEqual(self.encoded(value), expected)
        shared['finite'] = 2.5
        self.assertNotEqual(self.encoded(value), expected)
        shared['hidden'] = object()
        with self.assertRaisesRegex(StateCodecError, 'unsupported selected rule data'):
            self.encoded(value)

    def test_builtin_json_data_is_read_only_and_subclasses_are_not_trusted(self):
        canonical = {'values': [None, True, False, 1, '한글', 1.5]}
        before = json.dumps(canonical)
        self.assertIs(_plain(canonical), canonical)
        self.assertEqual(json.dumps(canonical), before)
        class CustomList(list):
            pass
        class CustomDict(dict):
            pass
        class CustomString(str):
            pass
        for value in (CustomList(), CustomDict(), CustomString('x'),
                      {CustomString('x'): 1}, {'outer': [{1: 'bad key'}]}):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(StateCodecError):
                    _plain(value)

    def test_nonfinite_values_remain_rejected_through_shared_containers(self):
        for number in (float('nan'), float('inf'), float('-inf')):
            shared = [number]
            with self.subTest(number=str(number)):
                with self.assertRaisesRegex(StateCodecError, 'nonfinite'):
                    _plain({'a': shared, 'b': shared})

    def test_rule_cycles_reject_but_shared_acyclic_subtrees_are_legal(self):
        a = []
        a.append(a)
        b = {}
        c = (b,)
        b['back'] = c
        for value in (a, b):
            with self.assertRaises(RecursionError):
                _plain(value)
        shared = ('valid',)
        self.assertEqual(_plain([shared, shared]), [['valid'], ['valid']])


if __name__ == '__main__':
    unittest.main()
