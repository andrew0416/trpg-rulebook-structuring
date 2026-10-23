"""Public source-reader dispatch preserves extension policy and native freshness."""
from copy import copy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MethodType, SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('SOURCE_READER_TEST_ROOT', ROOT)).resolve()
sys.path.insert(0, str(ROOT / 'engine'))

from engine import Rules
from ruleset import RuleFilter, RuleSelection
import source_context
import source_selection

UID = 'C2CSV/input/db/edges.csv:R24:main'
DENIAL = 'extension policy denies this selection'


class ReaderProxy:
    """Forward wrapped metadata while retaining its own callable policy."""

    def __init__(self, native, *, deny=False, after_read=None):
        self.native = native
        self.deny = deny
        self.after_read = after_read
        self.calls = []

    def __getattr__(self, name):
        return getattr(self.native, name)

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.deny:
            raise ValueError(DENIAL)
        selected = self.native(*args, **kwargs)
        if self.after_read is not None:
            self.after_read()
        return selected


class ClassForwardingProxy(ReaderProxy):
    @property
    def __class__(self):
        return self.native.__class__


class PolicyRules(Rules):
    def _selected_rule(self, *args, **kwargs):
        self.policy_calls.append((args, kwargs))
        raise ValueError(DENIAL)


class SourceReaderProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loaded = Rules(str(ROOT), ruleset='core')

    def setUp(self):
        self.rules = copy(self.loaded)

    def test_direct_proxy_denial_control(self):
        proxy = ReaderProxy(self.rules._selected_rule, deny=True)
        with self.assertRaisesRegex(ValueError, DENIAL):
            proxy(UID)
        self.assertEqual(proxy.calls, [((UID,), {})])

    def test_forwarding_proxy_denial_is_honored(self):
        proxy = ReaderProxy(self.rules._selected_rule, deny=True)
        self.rules._selected_rule = proxy
        with self.assertRaisesRegex(ValueError, DENIAL):
            self.rules.select_source_definition(UID)
        self.assertEqual(proxy.calls, [((UID,), {})])

    def test_class_forwarding_proxy_cannot_bypass_policy_as_a_method(self):
        proxy = ClassForwardingProxy(self.rules._selected_rule, deny=True)
        # __class__ forwarding can satisfy isinstance, despite being a proxy.
        self.assertIsInstance(proxy, MethodType)
        self.assertIsNot(type(proxy), MethodType)
        self.rules._selected_rule = proxy
        with self.assertRaisesRegex(ValueError, DENIAL):
            self.rules.select_source_definition(UID)
        self.assertEqual(proxy.calls, [((UID,), {})])

    def test_allowing_proxy_is_called_and_keeps_public_reverification(self):
        proxy = ReaderProxy(self.rules._selected_rule)
        self.rules._selected_rule = proxy
        with patch.object(source_context, 'verified_source', wraps=source_context.verified_source) as observed:
            selected = self.rules.select_source_definition(UID)
        self.assertEqual(selected['selected_id'], UID)
        self.assertEqual(proxy.calls, [((UID,), {})])
        self.assertEqual([call.args[1]['file'] for call in observed.call_args_list],
                         ['input/db/edges.csv', 'input/db/edges.csv'])

    def test_plain_override_denial_control(self):
        calls = []

        def reader(*args, **kwargs):
            calls.append((args, kwargs))
            raise ValueError(DENIAL)

        self.rules._selected_rule = reader
        with self.assertRaisesRegex(ValueError, DENIAL):
            self.rules.select_source_definition(UID)
        self.assertEqual(calls, [((UID,), {})])

    def test_real_bound_custom_override_keeps_its_policy(self):
        rules = PolicyRules.__new__(PolicyRules)
        rules.__dict__.update(self.rules.__dict__)
        rules.policy_calls = []
        self.assertIs(type(rules._selected_rule), MethodType)
        with self.assertRaisesRegex(ValueError, DENIAL):
            rules.select_source_definition(UID)
        self.assertEqual(rules.policy_calls, [((UID,), {})])

    def test_duck_external_reader_is_called_and_source_is_verified(self):
        calls = []

        def reader(*args, **kwargs):
            calls.append((args, kwargs))
            return UID

        duck = SimpleNamespace(root=self.rules.root, ruleset=self.rules.ruleset,
                               selection=self.rules.selection, _selected_rule=reader)
        with patch.object(source_context, 'verified_source', wraps=source_context.verified_source) as observed:
            selected = source_selection.select(duck, UID)
        self.assertEqual(selected['selected_id'], UID)
        self.assertEqual(calls, [((UID,), {})])
        self.assertEqual([call.args[1]['file'] for call in observed.call_args_list], ['input/db/edges.csv'])

    def test_foreign_bound_native_reader_keeps_foreign_admission(self):
        foreign = copy(self.rules)
        foreign.ruleset = RuleFilter({'exclude_units': [UID]})
        foreign.selection = RuleSelection(foreign.ruleset, list(self.rules.selection.units.values()))
        self.rules._selected_rule = foreign._selected_rule
        with patch.object(foreign.selection, 'require_supported_version',
                          wraps=foreign.selection.require_supported_version) as observed:
            with self.assertRaises(ValueError):
                self.rules.select_source_definition(UID)
        observed.assert_called_once_with(UID, False)

    def test_native_reads_exact_source_once_per_call_and_again_next_call(self):
        original = Path.read_bytes
        target = (ROOT / 'input/db/edges.csv').resolve()
        reads = []

        def read(path):
            if path.resolve() == target:
                reads.append(path)
            return original(path)

        with patch.object(Path, 'read_bytes', read), patch.object(
                source_context, 'verified_source', wraps=source_context.verified_source) as observed:
            self.rules.select_source_definition(UID)
            self.assertEqual(len(reads), 1)
            self.assertEqual(len(observed.call_args_list), 1)
            self.rules.select_source_definition(UID)
            self.assertEqual(len(reads), 2)
            self.assertEqual(len(observed.call_args_list), 2)

    def test_native_rejects_actual_source_mutation_after_previous_call(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'input/db/edges.csv'
            path.parent.mkdir(parents=True)
            path.write_bytes((ROOT / 'input/db/edges.csv').read_bytes())
            self.rules.root = directory
            self.assertEqual(self.rules.select_source_definition(UID)['selected_id'], UID)
            path.write_bytes(path.read_bytes() + b'\nchanged after prior selection\n')
            with self.assertRaisesRegex(ValueError, 'source changed'):
                self.rules.select_source_definition(UID)

    def test_proxy_cannot_lend_freshness_evidence_after_its_own_call(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'input/db/edges.csv'
            path.parent.mkdir(parents=True)
            original = (ROOT / 'input/db/edges.csv').read_bytes()
            path.write_bytes(original)
            self.rules.root = directory
            proxy = ReaderProxy(self.rules._selected_rule,
                                after_read=lambda: path.write_bytes(original + b'\nchanged inside proxy\n'))
            self.rules._selected_rule = proxy
            with self.assertRaisesRegex(ValueError, 'source changed'):
                self.rules.select_source_definition(UID)
            self.assertEqual(proxy.calls, [((UID,), {})])

    def test_native_and_proxy_preserve_explicit_version_support(self):
        self.rules.ruleset = RuleFilter({'unit_versions': {UID: 'reviewed-version'}})
        self.rules.selection = RuleSelection(self.rules.ruleset, list(self.rules.selection.units.values()))
        with self.assertRaisesRegex(ValueError, 'version_not_supported_by_reader'):
            self.rules.select_source_definition(UID)
        self.assertEqual(self.rules.select_source_definition(UID, supports_versions=True)['version'],
                         'reviewed-version')
        proxy = ReaderProxy(self.rules._selected_rule)
        self.rules._selected_rule = proxy
        with self.assertRaisesRegex(ValueError, 'version_not_supported_by_reader'):
            self.rules.select_source_definition(UID)
        record = self.rules.select_source_definition(UID, supports_versions=True)
        self.assertEqual(record['version'], 'reviewed-version')
        self.assertTrue(record['supports_versions'])
        self.assertEqual(proxy.calls, [((UID,), {}), ((UID,), {'supports_versions': True})])


if __name__ == '__main__':
    unittest.main()
