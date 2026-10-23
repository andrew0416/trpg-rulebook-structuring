"""Progress must fail closed on stale/partial evidence and preserve the baseline."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from category3_progress import ROOT, calculate, stable_hash

class Category3ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = json.loads((ROOT / 'data/verification/category3-register.json').read_text(encoding='utf-8'))
        # Freeze this counter fixture at the approved baseline; future real
        # implementations and discoveries must not change these test inputs.
        self.ledger['scope_history'] = self.ledger['scope_history'][:1]
        baseline_ids = set(self.ledger['scope_history'][0]['added_ids'])
        self.ledger['entries'] = [e for e in self.ledger['entries'] if e['id'] in baseline_ids]
        for entry in self.ledger['entries']:
            entry['status'] = 'partial' if entry['id'] in ('DOMAIN-037', 'DOMAIN-041') else 'pending'
        self.entry = next(e for e in self.ledger['entries'] if e['id'] == 'DOMAIN-040')
        self.entry['status'] = 'completed'
        self.entry['review'] = {'full_scope_verified': True, 'remaining_obligations': []}
        self.entry['evidence'] = {'report': 'evidence.json', 'required_tests': ['source-case'],
                                  'required_files': ['implementation.py', 'source.txt', 'test.py']}
        hashes = {}
        for name in self.entry['evidence']['required_files']:
            path = self.root / name
            path.write_text('original ' + name, encoding='utf-8')
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.report = {'successful': True, 'results': [{'id': 'source-case', 'status': 'pass'}], 'input_hashes': hashes}
        self.save_report()

    def save_report(self):
        (self.root / 'evidence.json').write_text(json.dumps(self.report), encoding='utf-8')

    def test_approved_scope_and_partial_units_are_counted_exactly(self):
        result = calculate(self.root, self.ledger)
        self.assertEqual((result['completed'], result['denominator'], result['not_completed']), (1, 352, 351))
        self.assertEqual(result['completion_percent'], '0.2841')
        self.assertEqual(result['counts'], {'completed': 1, 'partial': 2, 'pending': 349})

    def test_stale_implementation_source_or_test_cannot_count_as_done(self):
        for name in ('implementation.py', 'source.txt', 'test.py'):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_text('changed', encoding='utf-8')
                result = calculate(self.root, self.ledger)
                self.assertEqual(result['completed'], 0)
                self.assertEqual(result['counts']['needs_reverification'], 1)
                path.write_bytes(original)

    def test_a_pass_does_not_complete_a_partial_scope(self):
        self.entry['status'] = 'partial'
        self.assertEqual(calculate(self.root, self.ledger)['completed'], 0)
        self.entry['status'] = 'completed'
        self.entry['review']['remaining_obligations'] = ['missing exception']
        self.assertEqual(calculate(self.root, self.ledger)['completed'], 0)

    def test_failed_or_missing_required_evidence_cannot_count(self):
        self.report['results'][0]['status'] = 'fail'
        self.save_report()
        self.assertEqual(calculate(self.root, self.ledger)['completed'], 0)
        self.report['results'][0]['status'] = 'pass'
        del self.report['input_hashes']['source.txt']
        self.save_report()
        self.assertEqual(calculate(self.root, self.ledger)['completed'], 0)
        (self.root / 'evidence.json').unlink()
        self.assertEqual(calculate(self.root, self.ledger)['completed'], 0)

    def test_duplicate_removal_and_unrecorded_addition_are_rejected(self):
        duplicate = deepcopy(self.ledger)
        duplicate['entries'].append(deepcopy(duplicate['entries'][0]))
        with self.assertRaises(ValueError):
            calculate(self.root, duplicate)
        removed = deepcopy(self.ledger)
        removed['entries'].pop()
        with self.assertRaises(ValueError):
            calculate(self.root, removed)
        added = deepcopy(self.ledger)
        entry = deepcopy(added['entries'][0])
        entry['id'] = 'C3-ADD-001'
        added['entries'].append(entry)
        with self.assertRaises(ValueError):
            calculate(self.root, added)

    def test_discovery_appends_one_to_denominator_with_a_revision(self):
        entry = deepcopy(self.ledger['entries'][0])
        entry['id'] = 'C3-ADD-001'
        self.ledger['entries'].append(entry)
        self.ledger['scope_history'].append({'revision': 2, 'added_ids': [entry['id']],
                                            'removed_ids': [], 'denominator': 353})
        result = calculate(self.root, self.ledger)
        self.assertEqual((result['completed'], result['denominator']), (1, 353))
        self.assertEqual(result['completion_percent'], '0.2833')

    def test_original_scope_cannot_be_silently_rewritten(self):
        self.entry['source_snapshot']['conditions_and_results_ko'] = 'narrowed scope'
        with self.assertRaises(ValueError):
            calculate(self.root, self.ledger)

if __name__ == '__main__':
    unittest.main(verbosity=2)

