"""Direct --auto scope, using the actual CLI and stdlib-only marked fixtures."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'work/reuse-partials/verify_overlay_tests.py'
MODULE = 'tools.test_scope_dummy'
ALPHA = MODULE + '.Case.test_alpha'
BETA = MODULE + '.Case.test_beta'
OTHER = MODULE + '.Other.test_gamma'


class VerifierSelectionScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='verifier-scope-', dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage, self.canonical = self.root / 'stage', self.root / 'canonical'
        (self.stage / 'tools').mkdir(parents=True)
        (self.canonical / 'tools').mkdir(parents=True)
        (self.canonical / 'tools/__init__.py').write_text('', encoding='utf-8')
        self.marker = self.root / 'events.jsonl'
        self.source = self.stage / 'tools/test_scope_dummy.py'
        self.source.write_text(
            'import unittest\nfrom pathlib import Path\nimport json\n'
            'def mark(event):\n'
            ' with Path(' + repr(str(self.marker)) + ').open("a", encoding="utf-8") as f:f.write(json.dumps(event)+"\\n")\n'
            'def setUpModule():mark("module")\n'
            'class Case(unittest.TestCase):\n'
            ' @classmethod\n def setUpClass(cls):mark("Case")\n'
            ' def test_alpha(self):mark("alpha")\n'
            ' def test_beta(self):mark("beta")\n'
            'class Other(unittest.TestCase):\n'
            ' @classmethod\n def setUpClass(cls):mark("Other")\n'
            ' def test_gamma(self):mark("gamma")\n', encoding='utf-8')
        self.sequence = 0

    def run_cli(self, *targets):
        self.sequence += 1
        output = self.root / ('run-' + str(self.sequence))
        scratch = self.root / 'scratch'
        scratch.mkdir(exist_ok=True)
        env = dict(os.environ, TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch),
                   PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.run(
            [sys.executable, '-B', '-X', 'utf8', str(RUNNER), '--auto', *map(str, targets),
             '--stage', str(self.stage), '--canonical', str(self.canonical), '--record', str(output)],
            capture_output=True, text=True, encoding='utf-8', timeout=20, env=env)
        reports = list(output.glob('*.json'))
        self.assertEqual(len(reports), 1, process.stdout + process.stderr)
        return process, json.loads(reports[0].read_text(encoding='utf-8'))

    def events(self):
        return [json.loads(line) for line in self.marker.read_text(encoding='utf-8').splitlines()] if self.marker.exists() else []

    def assert_run(self, targets, ids, events):
        process, data = self.run_cli(*targets)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(data['kind'], 'run')
        self.assertTrue(data['successful'])
        self.assertEqual(data['selected_case_ids'], ids)
        self.assertEqual(data['collected'], ids)
        self.assertEqual(data['tests_run'], len(ids))
        self.assertEqual([row['id'] for row in data['test_durations']], ids)
        self.assertEqual(self.events(), events)
        return data

    def test_direct_qualified_method_runs_only_that_method(self):
        self.assert_run([ALPHA], [ALPHA], ['module', 'Case', 'alpha'])

    def test_bare_method_gets_tools_prefix_without_losing_tail(self):
        self.assert_run(['test_scope_dummy.Case.test_beta'], [BETA], ['module', 'Case', 'beta'])

    def test_direct_class_keeps_every_method_in_only_that_class(self):
        self.assert_run([MODULE + '.Case'], [ALPHA, BETA], ['module', 'Case', 'alpha', 'beta'])

    def test_module_keeps_both_classes(self):
        self.assert_run([MODULE], [ALPHA, BETA, OTHER], ['module', 'Case', 'alpha', 'beta', 'Other', 'gamma'])

    def test_file_path_keeps_whole_module(self):
        self.assert_run([self.source], [ALPHA, BETA, OTHER], ['module', 'Case', 'alpha', 'beta', 'Other', 'gamma'])

    def test_dotted_module_py_alias_keeps_whole_module(self):
        self.assert_run([MODULE + '.py'], [ALPHA, BETA, OTHER], ['module', 'Case', 'alpha', 'beta', 'Other', 'gamma'])

    def test_relative_file_path_keeps_whole_module(self):
        self.assert_run(['tools/test_scope_dummy.py'], [ALPHA, BETA, OTHER], ['module', 'Case', 'alpha', 'beta', 'Other', 'gamma'])

    def test_selector_py_suffix_is_not_silently_removed(self):
        for selector in (MODULE + '.Case.py', ALPHA + '.py'):
            with self.subTest(selector=selector):
                process, data = self.run_cli(selector)
                self.assertNotEqual(process.returncode, 0, (data['collected'], self.events()))
                self.assertEqual(data['kind'], 'discovery_error')
                self.assertEqual(data['tests_run'], 0)
                self.assertTrue(data['discovery_errors'])
                self.assertEqual(data['requested'], [selector])
                self.assertEqual(self.events(), [])

    def test_unknown_class_or_method_stops_before_any_fixture(self):
        for selector in (MODULE + '.Missing', MODULE + '.Case.test_missing', MODULE + '.Case.test_alpha.extra',
                         MODULE + '.Case..test_alpha', MODULE + '.Case.bad!selector'):
            with self.subTest(selector=selector):
                process, data = self.run_cli(selector)
                self.assertNotEqual(process.returncode, 0)
                self.assertEqual(data['kind'], 'discovery_error')
                self.assertEqual(data['tests_run'], 0)
                self.assertTrue(data['discovery_errors'])
                self.assertEqual(data['requested'], [selector])
                self.assertEqual(self.events(), [])

    def test_overlapping_direct_scopes_retain_duplicate_guard(self):
        process, data = self.run_cli(MODULE, ALPHA)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(data['kind'], 'discovery_error')
        self.assertEqual(data['tests_run'], 0)
        self.assertTrue(any('duplicate test IDs' in error for error in data['discovery_errors']))
        self.assertEqual(self.events(), [])

    def packet(self):
        packet = self.stage / 'packet.json'
        packet.write_text(json.dumps({'completed': {'all': {'tests': [ALPHA, BETA, OTHER]}}}), encoding='utf-8')
        return packet

    def test_packet_still_runs_all_declared_obligations(self):
        data = self.assert_run([self.packet()], [ALPHA, BETA, OTHER], ['module', 'Case', 'alpha', 'beta', 'Other', 'gamma'])
        self.assertEqual(data['workflow']['route'], 'packet_full')

    def test_saved_method_report_still_expands_to_current_whole_module(self):
        report = self.root / 'saved.json'
        report.write_text(json.dumps({'version': 1, 'kind': 'run', 'stage': str(self.stage),
            'canonical': str(self.canonical), 'requested': [ALPHA], 'collected': [ALPHA],
            'successful': True}), encoding='utf-8')
        data = self.assert_run([report], [ALPHA, BETA, OTHER], ['module', 'Case', 'alpha', 'beta', 'Other', 'gamma'])
        self.assertIn('expand_saved_selection_to_current_whole_modules', data['workflow']['decisions'])

    def test_partial_report_restores_current_full_packet(self):
        packet = self.packet()
        report = self.root / 'partial.json'
        report.write_text(json.dumps({'version': 1, 'kind': 'run', 'stage': str(self.stage),
            'canonical': str(self.canonical), 'requested': [ALPHA], 'collected': [ALPHA],
            'successful': True, 'allocation_scope': 'partial',
            'allocation': [{'packet': str(packet), 'group': 'all', 'tests': [ALPHA]}],
            'omitted_case_ids': [BETA, OTHER]}), encoding='utf-8')
        data = self.assert_run([report], [ALPHA, BETA, OTHER], ['module', 'Case', 'alpha', 'beta', 'Other', 'gamma'])
        self.assertEqual(data['workflow']['route'], 'packet_full')

    def test_navigation_sample_still_expands_to_whole_contract_module(self):
        navigation = self.canonical / 'tools/reuse_navigation.py'
        note = {'tests': [{'file': 'tools/test_scope_dummy.py', 'tests': ['Case.test_alpha']}],
                'contract': {'required_test_modules': []}, 'checks': []}
        navigation.write_text('def load(root):return ' + repr({'scope-owner': note}) + '\n'
                              'def resolve(notes,target):return target,"owner"\n', encoding='utf-8')
        data = self.assert_run(['scope-owner'], [ALPHA, BETA, OTHER], ['module', 'Case', 'alpha', 'beta', 'Other', 'gamma'])
        self.assertIn('whole_contract_modules:scope-owner', data['workflow']['decisions'])


if __name__ == '__main__':
    unittest.main()
