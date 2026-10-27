"""Exact old/new native-wait classification checks, not rule-completion evidence."""
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

STAGE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE / 'engine'), str(STAGE / 'tools')]
import state_grants as G
import passive_events as PASSIVE
import heavy_injury_adapter as HEAVY


class NativePendingClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).parent / 'fixtures/native-pending-classifiers.json'
        cls.rows = json.loads(fixture.read_text())['classifiers']
        cls.originals = []
        for row in cls.rows:
            namespace = {}
            exec(compile(row['source'], '<frozen-native-wait-classifier>', 'exec'), namespace)
            cls.originals.append((row, namespace['original']))

    def outcome(self, callback, engine, error):
        try:
            return callback(engine, error), None
        except Exception as failure:
            return None, (type(failure), str(failure))

    @staticmethod
    def current(engine, error):
        pending = []
        if not G.record_native_pending(engine, error, pending):
            raise error
        return pending

    def test_exact_type_pending_id_registry_and_malformed_order_match_all_ten_originals(self):
        class PassiveSubclass(PASSIVE.PassiveEventPending):
            pass
        class HeavySubclass(HEAVY.HeavyPending):
            pass
        errors = [ValueError('unrelated'), PASSIVE.PassiveEventPending('p'),
                  HEAVY.HeavyPending('h'), PassiveSubclass('p'), HeavySubclass('h')]
        states = [{}, {'_passive_pending': None, '_heavy_pending': None},
                  {'_passive_pending': 'p', '_heavy_pending': 'h'},
                  *({'_passive_pending': p, '_heavy_pending': h,
                     '_passive_events': pe, '_heavy_events': he}
                    for p in (None, 'p', 'wrong') for h in (None, 'h', 'wrong')
                    for pe, he in (({}, {}), ({'p': {}}, {'h': {}}), (None, None)))]
        for row, original in self.originals:
            for state in states:
                for error in errors:
                    with self.subTest(module=row['module'], state=state, error=type(error).__name__):
                        engine = SimpleNamespace(**state)
                        self.assertEqual(self.outcome(self.current, engine, error),
                                         self.outcome(original, engine, error))

    def test_only_the_matching_exact_registered_wait_is_appended_to_the_existing_list(self):
        engine = SimpleNamespace(_passive_pending='p', _heavy_pending='h',
                                 _passive_events={'p': {}}, _heavy_events={'h': {}})
        existing = [('existing', 'receipt')]
        before = dict(vars(engine))
        for error, expected in ((PASSIVE.PassiveEventPending('p'), PASSIVE.PassiveEventPending),
                                (HEAVY.HeavyPending('h'), HEAVY.HeavyPending)):
            self.assertTrue(G.record_native_pending(engine, error, existing))
            self.assertEqual(existing[-1], (expected, error.event_id))
        self.assertFalse(G.record_native_pending(engine, RuntimeError('not native'), existing))
        self.assertEqual(len(existing), 3)
        self.assertEqual(vars(engine), before)

    def test_strict_consumers_use_one_owner_and_keep_the_distinct_type_ace_contract(self):
        self.assertEqual(len(self.rows), 10)
        for row in self.rows:
            source = STAGE / 'engine' / (row['module'] + '.py')
            tree = ast.parse(source.read_text(encoding='utf-8-sig'))
            owner = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == row['owner'])
            calls = [n for n in ast.walk(owner) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == 'record_native_pending']
            self.assertEqual(len(calls), 1, row['module'])
            for handler in (n for n in ast.walk(owner) if isinstance(n, ast.ExceptHandler)):
                self.assertFalse(any(isinstance(n, ast.Attribute) and n.attr in ('_passive_pending', '_heavy_pending')
                                     for n in ast.walk(handler)), row['module'])
        type_ace = (STAGE / 'engine/type_ace.py').read_text(encoding='utf-8-sig')
        self.assertNotIn('record_native_pending', type_ace)


if __name__ == '__main__':
    unittest.main()
