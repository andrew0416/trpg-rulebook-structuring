"""Stdlib-only reporter regressions; never import or execute the game engine."""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

EVIDENCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVIDENCE / 'tools'))
import report_category2_progress as P


def load_file(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReporterFixtureEvidenceTests(unittest.TestCase):
    def test_described_whole_success_preserves_ids_and_rejects_forged_results(self):
        class Described(unittest.TestCase):
            __module__ = 'test_reporter_described'
            __qualname__ = 'Described'

            def test_a(self):
                """실제 설명 ... with an ellipsis."""
                pass

        case = Described('test_a')
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite([case]))
        self.assertTrue(result.wasSuccessful())
        body = stream.getvalue()
        self.assertIn(case.id() + ')\n실제 설명 ... with an ellipsis. ... ok', body)
        for raw in (body, body.replace('\n', '\r\n')):
            self.assertEqual(P._verified_test_ids(raw), {case.id()})
            self.assertEqual(P._verified_test_ids(raw, [case.id()]), {case.id()})
        for changed in (
            body.replace('Ran 1 test', 'Ran 2 tests'),
            body.replace(' ... ok', ' ...'),
            body.replace(' ... ok', ' ... FAIL'),
            body.replace('test_a)', 'test_other)'),
            body.replace('test_a (', 'test_other ('),
            body + 'arbitrary tail\n',
        ):
            with self.subTest(log=changed):
                self.assertIsNone(P._verified_test_ids(changed, [case.id()]))

    def test_described_fail_error_and_subtest_keep_only_actual_named_successes(self):
        class Mixed(unittest.TestCase):
            __module__ = 'test_reporter_described'
            __qualname__ = 'Mixed'

            def test_a(self):
                """An actual described PASS."""
                pass

            def test_b(self):
                """An actual described assertion failure."""
                self.fail('original assertion')

            def test_c(self):
                """An actual described ERROR."""
                raise RuntimeError('original error')

            def test_d(self):
                """An actual described subTest failure."""
                with self.subTest(value=1):
                    self.fail('original subtest')

        cases = [Mixed('test_' + letter) for letter in 'abcd']
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite(cases))
        self.assertEqual((result.testsRun, len(result.failures), len(result.errors)), (4, 2, 1))
        body = stream.getvalue()
        good = cases[0].id()
        self.assertEqual(P._verified_test_ids(body, [good]), {good})
        self.assertIsNone(P._verified_test_ids(body))
        for case in cases[1:]:
            self.assertIsNone(P._verified_test_ids(body, [case.id()]))
        for changed in (
            body.replace('FAILED (failures=2, errors=1)', 'OK'),
            body.replace('failures=2', 'failures=1'),
            body.replace('errors=1', 'errors=2'),
            body.replace('Ran 4 tests', 'Ran 5 tests'),
            body.replace('  test_d (' + cases[3].id(), '  test_b (' + cases[1].id()),
        ):
            with self.subTest(log=changed):
                self.assertIsNone(P._verified_test_ids(changed, [good]))

    def test_existing_case_scoped_proof_regressions(self):
        source = EVIDENCE / 'tools/test_category2_progress.py'
        if not source.is_file():
            source = EVIDENCE / 'baseline/tools/test_category2_progress.py'
        existing = load_file('_existing_reporter_tests', source)
        existing.EdgeReuseProgressTests.test_explicit_success_cases_require_actual_unittest_evidence_and_modules(self)
        name = 'data/verification/foundation-common-damage-test_foundation_combat_damage.log'
        compact_path = EVIDENCE / name
        if not compact_path.is_file():
            compact_path = EVIDENCE / 'baseline' / name
        raw = compact_path.read_bytes()
        self.assertEqual(sha256(raw).hexdigest(), '51e073f745f1795cd06ac8371f7b57f1002e87a1ea67d2e78abaace39a960eea')
        compact = raw.decode('utf-8-sig')
        self.assertEqual(P._verified_test_ids(compact), set())
        self.assertEqual(P._verified_test_ids(compact + 'UTC end 2026-10-20T00:01:02+00:00\n'), set())
        self.assertIsNone(P._verified_test_ids(compact, ['test_foundation_combat_damage.Tests.test_fake']))
        compact = compact.replace('\r\n', '\n')
        fixture = 'setUpClass (test_compact.Fixture)'
        fixture_detail = '=' * 70 + '\nERROR: ' + fixture + '\n'
        changes = [
            ('compact wrong Ran count', compact.replace('Ran 7 tests', 'Ran 8 tests')),
            ('compact error marker', compact.replace('.......\n', '......E\n')),
            ('compact failed diagnostic', 'FAIL: test_hidden.Tests.test_bad\n' + compact),
            ('compact fixture diagnostic', compact.replace('.......\n', '.......\n' + fixture_detail)),
            ('verbose fixture forged OK', compact.replace('.......\n', fixture + ' ... ERROR\n' + fixture_detail)),
            ('malformed fixture forged OK', 'setUpClass (bad-owner) ... ERROR\n' + compact),
        ]
        for label, changed in changes:
            with self.subTest(compact_mutation=label):
                self.assertNotEqual(changed, compact)
                self.assertIsNone(P._verified_test_ids(changed))
        self.assertEqual(compact_path.read_bytes(), raw)

    def test_real_class_and_module_fixture_errors_count_without_becoming_test_calls(self):
        class Ready(unittest.TestCase):
            __module__ = 'test_reporter_ready'
            __qualname__ = 'Ready'

            def test_a(self):
                pass

            def test_b(self):
                pass

        good = [Ready('test_a').id(), Ready('test_b').id()]
        for kind in ('setUpClass', 'setUpModule', 'tearDownClass', 'tearDownModule'):
            with self.subTest(fixture=kind):
                module = types.ModuleType('test_reporter_fixture_module')

                class Fixture(Ready):
                    __module__ = module.__name__
                    __qualname__ = 'Fixture'

                def fail(*args):
                    raise RuntimeError('actual ' + kind + ' failure')

                if kind.endswith('Class'):
                    setattr(Fixture, kind, classmethod(fail))
                    owner = module.__name__ + '.Fixture'
                else:
                    setattr(module, kind, fail)
                    owner = module.__name__
                stream = io.StringIO()
                with patch.dict(sys.modules, {module.__name__: module}):
                    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite([
                        Ready('test_a'), Fixture('test_a'), Fixture('test_b'), Ready('test_b')]))
                body = stream.getvalue()
                calls = 2 if kind.startswith('setUp') else 4
                fixture = kind + ' (' + owner + ')'
                self.assertEqual((result.testsRun, len(result.failures), len(result.errors)), (calls, 0, 1))
                self.assertEqual([case.id() for case, _ in result.errors], [fixture])
                self.assertEqual(P._verified_test_ids(body, good), set(good))
                self.assertEqual(P._verified_test_ids(body + 'UTC end 2026-10-20T00:01:02+00:00\n', good), set(good))
                self.assertIsNone(P._verified_test_ids(body, None))
                self.assertIsNone(P._verified_test_ids(body, [fixture]))
                fixture_test = Fixture('test_a').id()
                self.assertEqual(P._verified_test_ids(body, [fixture_test]),
                                 None if kind.startswith('setUp') else {fixture_test})
                changes = [
                    ('forged OK', body.replace('FAILED (errors=1)', 'OK')),
                    ('fixture counted as call', body.replace('Ran ' + str(calls), 'Ran ' + str(calls + 1))),
                    ('missing actual header', body.replace('test_a (' + good[0] + ') ... ok\n', '', 1)),
                    ('duplicate actual header', ('test_a (' + good[0] + ') ... ok\n' + body).replace(
                        'Ran ' + str(calls), 'Ran ' + str(calls + 1))),
                    ('fixture cannot pass', body.replace(fixture + ' ... ERROR', fixture + ' ... ok')),
                    ('fixture diagnostic ID', body.replace('ERROR: ' + fixture, 'ERROR: ' + kind + ' (other.Module)')),
                    ('wrong errors count', body.replace('FAILED (errors=1)', 'FAILED (errors=2)')),
                    ('non UTC footer', body + 'UTC end 2026-10-20T00:01:02+09:00\n'),
                ]
                for label, changed in changes:
                    with self.subTest(fixture=kind, mutation=label):
                        self.assertIsNone(P._verified_test_ids(changed, good))
                        if label == 'forged OK':
                            self.assertIsNone(P._verified_test_ids(changed, None))
                if kind.endswith('Class'):
                    self.assertIsNone(P._verified_test_ids(body.replace(owner, 'UnscopedClass'), good))

    def test_fixture_cannot_hide_a_noncontiguous_repeated_subtest_parent(self):
        good, bad = 'test_guard.Ready.test_good', 'test_guard.Mixed.test_bad'
        fixture = 'tearDownClass (test_guard.Mixed)'
        body = f'test_good ({good}) ... ok\ntest_bad ({bad}) ... \n'
        body += f'  test_bad ({bad}) (value=1) ... FAIL\n'
        body += fixture + f' ... ERROR\ntest_bad ({bad}) ... ERROR\n\n'
        body += '=' * 70 + '\nERROR: ' + fixture + '\n'
        body += '\n' + '-' * 70 + '\nRan 2 tests in 0.001s\n\nFAILED (failures=1, errors=2)\n'
        self.assertIsNone(P._verified_test_ids(body, [good]))

    def test_actual_herb_original_failure_retains_exactly_four_named_passes(self):
        prefix = EVIDENCE / 'data/verification/core-herb-mushroom-rules-01'
        if not prefix.with_suffix('.log').is_file():
            prefix = EVIDENCE.parent / 'herb-mushroom-rules/data/verification/core-herb-mushroom-rules-01'
        raw = prefix.with_suffix('.log').read_bytes()
        self.assertEqual(sha256(raw).hexdigest(), '644c5a01b79075a9ef2236bac8afe48470003292c89d1b6d92f5696ae894e60f')
        meta = json.loads(prefix.with_suffix('.json').read_text(encoding='utf-8-sig'))
        self.assertEqual((len(meta['test_ids']), len(meta['actual_test_ids']), meta['tests'],
                          len(meta['failure_ids']), len(meta['error_ids'])), (11, 10, 10, 5, 3))
        good = [
            'test_core_herb_mushroom_rules.HerbMushroomTests.test_poultice_uses_revised_shared_herbal_history_and_native_dressing',
            'test_core_herb_mushroom_rules.HerbMushroomTests.test_poultice_resumable_application_restores_and_attaches_herbal_use_once',
            'test_category2_herbal_state.HerbalStateTests.test_actual_counts_are_recipient_scoped_and_all_herbs_share_one_history',
            'test_core_herb_mushroom_rules.HerbMushroomTests.test_energy_root_grows_as_herb_but_never_enters_snack_route',
        ]
        body = raw.decode('utf-8-sig')
        self.assertEqual(P._verified_test_ids(body, good), {P._case_identity(case) for case in good})
        for case in good:
            with self.subTest(pass_case=case):
                self.assertEqual(P._verified_test_ids(body, [case]), {P._case_identity(case)})
        for cases in ([meta['error_ids'][0]], [meta['test_ids'][3]], [meta['test_ids'][1]],
                      [meta['test_ids'][7]], good + [good[0]], None):
            with self.subTest(nonpass_scope=cases):
                self.assertIsNone(P._verified_test_ids(body, cases))
        for label, changed in (
            ('forged OK', body.replace('FAILED (failures=5, errors=3)', 'OK')),
            ('fixture counted as call', body.replace('Ran 10 tests', 'Ran 11 tests')),
            ('fixture omitted from error count', body.replace('errors=3', 'errors=2')),
        ):
            with self.subTest(mutation=label):
                self.assertIsNone(P._verified_test_ids(changed, good))
        self.assertEqual(prefix.with_suffix('.log').read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
