"""Mutation guards for authority draft integrity; these do not prove rule semantics."""
import argparse
import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from audit_root_authority_atoms import SPEC, REVIEWS, GRAPH, TARGETS, validate, build_report, input_hashes, digest

ROOT = Path(__file__).resolve().parents[1]
REAL_ROOT = ROOT
REAL_SPEC = ROOT / SPEC


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fixture(root):
    """Two live review files, two target-linked candidates and one unrelated leaf."""
    snapshots, rows = [], []
    for n in (1, 2):
        source = f'input/ch{n}.md'
        path = root / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'Header {n}\nClause {n}\nBoundary {n}\n', encoding='utf-8')
        cid = f'C{n}'
        symbol = 'source.authority' if n == 1 else 'rules.precedence'
        clause = dict(id=cid, block_ids=[f'{source}:2-2'], statement=f'Clause {n}', symbol_refs=[symbol])
        clauses = [clause]
        if n == 1:
            clauses.append(dict(id='LEAF', block_ids=[f'{source}:3-3'], statement='Other', symbol_refs=['choice.selection']))
        review_file = f'{REVIEWS}/ch{n}.json'
        review = dict(file=source, source_sha256=digest(path), clauses=clauses)
        write_json(root / review_file, review)
        snapshots.append(dict(review_file=review_file, review_sha256=digest(root / review_file), source_file=source, source_sha256=digest(path), candidate_count=1))
        rows.append(dict(candidate_id=cid, review_file=review_file, source_file=source,
                         source_block_ids=clause['block_ids'], matched_symbols=[symbol], statement_index=clause['statement'],
                         disposition='partially_atomized_draft' if n == 1 else 'indexed_pending_atomic_review',
                         reason='Draft split' if n == 1 else 'Pending, not excluded', atom_ids=['A1'] if n == 1 else []))
    write_json(root / GRAPH, dict(nodes=[dict(id=x, kind='symbol') for x in sorted(TARGETS)]))
    atom = dict(id='A1', symbol='source.authority',
                source=dict(file='input/ch1.md', start=2, end=2, excerpt='Clause 1', excerpt_sha256=hashlib.sha256(b'Clause 1').hexdigest()),
                parent_candidate_ids=['C1'], statement='Authority is scoped.', conditions=['Within the source scope'], exceptions=[],
                formal_relation='in_scope -> may_decide', positive_case='Within scope', negative_or_boundary_case='Outside scope',
                remaining=['Semantic review pending'], status='draft', modality='normative')
    return dict(scope=dict(symbols=sorted(TARGETS), indexed_candidate_count=2, review_file_count=2, snapshots=snapshots),
                completion=False, atoms=[atom], candidate_dispositions=rows, index_gaps=[], remaining=['Not semantically complete'])


class AuthorityAtomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spec = fixture(self.root)

    def errors(self, spec=None):
        return validate(self.spec if spec is None else spec, self.root)

    def test_live_project_index_sources_and_links(self):
        spec = json.loads(REAL_SPEC.read_text(encoding='utf-8-sig'))
        self.assertEqual(validate(spec, REAL_ROOT), [])

    def test_dynamic_fixture_denominator_is_not_hardcoded(self):
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.spec['scope']['indexed_candidate_count'], 2)

    def test_excerpts_hashes_and_ranges_detect_independent_tampering(self):
        for field, value, error in [('excerpt', 'Invented', 'stale_authority_excerpt:A1'),
                                    ('excerpt_sha256', '0'*64, 'stale_authority_excerpt_hash:A1'),
                                    ('start', 0, 'invalid_authority_source_range:A1'),
                                    ('end', 99, 'invalid_authority_source_range:A1'),
                                    ('start', True, 'invalid_authority_source:A1')]:
            with self.subTest(field=field, value=value):
                spec = copy.deepcopy(self.spec)
                spec['atoms'][0]['source'][field] = value
                self.assertIn(error, self.errors(spec))

    def test_equal_text_at_wrong_line_still_requires_matching_span(self):
        self.spec['atoms'][0]['source']['start'] = 3
        self.spec['atoms'][0]['source']['end'] = 3
        self.assertIn('stale_authority_excerpt:A1', self.errors())

    def test_source_path_escape_is_rejected_without_reading_it(self):
        for path in ['../outside.md', str(self.root.parent / 'outside.md')]:
            with self.subTest(path=path):
                spec = copy.deepcopy(self.spec)
                spec['atoms'][0]['source']['file'] = path
                self.assertIn('invalid_authority_source:A1', self.errors(spec))

    def test_actual_source_change_invalidates_snapshot_and_excerpt(self):
        (self.root / 'input/ch1.md').write_text('Header 1\nChanged\nBoundary 1\n', encoding='utf-8')
        errors = self.errors()
        self.assertIn('stale_authority_excerpt:A1', errors)
        self.assertIn(f'stale_authority_snapshot:{REVIEWS}/ch1.json:source_file', errors)
        self.assertIn(f'stale_review_source:{REVIEWS}/ch1.json', errors)

    def test_review_change_invalidates_snapshot_even_without_union_change(self):
        path = self.root / REVIEWS / 'ch1.json'
        review = json.loads(path.read_text())
        review['audit_note'] = 'changed'
        write_json(path, review)
        self.assertIn(f'stale_authority_snapshot:{REVIEWS}/ch1.json:review_file', self.errors())

    def test_snapshot_omission_duplication_and_false_counts(self):
        for mutation, expected in [
            (lambda s: s['scope']['snapshots'].pop(), 'authority_snapshot_set_mismatch'),
            (lambda s: s['scope']['snapshots'].append(copy.deepcopy(s['scope']['snapshots'][0])), 'duplicate_authority_snapshot'),
            (lambda s: s['scope'].update(indexed_candidate_count=578), 'wrong_authority_count:indexed_candidate_count'),
            (lambda s: s['scope'].update(review_file_count=20), 'wrong_authority_count:review_file_count')]:
            spec = copy.deepcopy(self.spec)
            mutation(spec)
            self.assertIn(expected, self.errors(spec))

    def test_new_linked_candidate_is_visible_in_live_dynamic_union(self):
        path = self.root / REVIEWS / 'ch1.json'
        review = json.loads(path.read_text())
        review['clauses'][1]['symbol_refs'].append('source.authority')
        write_json(path, review)
        errors = self.errors()
        self.assertIn('authority_candidate_set_mismatch', errors)
        self.assertIn('wrong_authority_count:indexed_candidate_count', errors)

    def test_removed_candidate_and_duplicate_review_id_are_rejected(self):
        path = self.root / REVIEWS / 'ch2.json'
        review = json.loads(path.read_text())
        review['clauses'][0]['id'] = 'C1'
        write_json(path, review)
        errors = self.errors()
        self.assertIn('duplicate_review_candidate:C1', errors)
        self.assertIn('unknown_authority_candidate:C2', errors)

    def test_disposition_omission_duplicate_and_invented_candidate(self):
        for mutation, expected in [
            (lambda s: s['candidate_dispositions'].pop(), 'authority_candidate_set_mismatch'),
            (lambda s: s['candidate_dispositions'].append(copy.deepcopy(s['candidate_dispositions'][0])), 'duplicate_authority_disposition:C1'),
            (lambda s: s['candidate_dispositions'][1].update(candidate_id='UNKNOWN'), 'unknown_authority_candidate:UNKNOWN')]:
            spec = copy.deepcopy(self.spec)
            mutation(spec)
            self.assertIn(expected, self.errors(spec))

    def test_disposition_evidence_cannot_drift_from_parent_review(self):
        for field, value, error in [('source_block_ids', [], 'wrong_disposition_blocks:C1'),
                                    ('statement_index', 'Changed', 'stale_disposition_statement:C1'),
                                    ('matched_symbols', ['rules.precedence'], 'wrong_disposition_symbols:C1')]:
            spec = copy.deepcopy(self.spec)
            spec['candidate_dispositions'][0][field] = value
            self.assertIn(error, self.errors(spec))

    def test_parent_and_child_links_are_checked_both_directions(self):
        spec = copy.deepcopy(self.spec)
        spec['candidate_dispositions'][0]['atom_ids'] = []
        self.assertIn('missing_reverse_authority_link:A1:C1', self.errors(spec))
        spec = copy.deepcopy(self.spec)
        spec['candidate_dispositions'][1].update(disposition='partially_atomized_draft', atom_ids=['A1'])
        self.assertIn('missing_forward_authority_link:C2:A1', self.errors(spec))
        spec = copy.deepcopy(self.spec)
        spec['candidate_dispositions'][0]['atom_ids'] = ['UNKNOWN']
        self.assertIn('unknown_disposition_atom:C1:UNKNOWN', self.errors(spec))

    def test_parent_source_must_match_even_if_excerpt_and_hash_are_valid(self):
        self.spec['atoms'][0]['parent_candidate_ids'].append('C2')
        self.spec['candidate_dispositions'][1].update(disposition='partially_atomized_draft', atom_ids=['A1'])
        self.assertIn('wrong_authority_parent_source:A1:C2', self.errors())

    def test_same_file_unrelated_span_cannot_be_attached_to_parent(self):
        source = self.spec['atoms'][0]['source']
        source.update(start=3, end=3, excerpt='Boundary 1',
                      excerpt_sha256=hashlib.sha256(b'Boundary 1').hexdigest())
        errors = self.errors()
        self.assertIn('unrelated_authority_parent_span:A1:C1', errors)
        self.assertNotIn('stale_authority_excerpt:A1', errors)
        self.assertNotIn('stale_authority_excerpt_hash:A1', errors)
        self.assertNotIn('wrong_authority_parent_source:A1:C1', errors)

    def test_duplicate_atom_and_duplicate_links_are_rejected(self):
        self.spec['atoms'].append(copy.deepcopy(self.spec['atoms'][0]))
        self.spec['candidate_dispositions'][0]['atom_ids'].append('A1')
        errors = self.errors()
        self.assertIn('duplicate_authority_atom:A1', errors)
        self.assertIn('invalid_disposition_atom_ids:C1', errors)

    def test_symbol_must_be_one_of_targets_and_present_in_real_graph(self):
        spec = copy.deepcopy(self.spec)
        spec['atoms'][0]['symbol'] = 'invented.symbol'
        self.assertIn('invalid_authority_atom_symbol:A1', self.errors(spec))
        write_json(self.root / GRAPH, dict(nodes=[]))
        self.assertIn('missing_authority_graph_symbols', self.errors())

    def test_missing_conditions_cases_and_unknown_modality_are_rejected(self):
        for field, value, error in [('conditions', [], 'invalid_authority_atom_list:A1:conditions'),
                                    ('positive_case', '', 'missing_authority_atom_field:A1:positive_case'),
                                    ('negative_or_boundary_case', None, 'missing_authority_atom_field:A1:negative_or_boundary_case'),
                                    ('formal_relation', '', 'missing_authority_atom_field:A1:formal_relation'),
                                    ('exceptions', None, 'invalid_authority_atom_list:A1:exceptions'),
                                    ('modality', 'proven', 'invalid_authority_modality:A1')]:
            spec = copy.deepcopy(self.spec)
            spec['atoms'][0][field] = value
            self.assertIn(error, self.errors(spec))

    def test_completion_certification_and_verified_atom_status_are_rejected(self):
        self.spec['completion'] = True
        self.spec['whole_rule_certified'] = True
        self.spec['atoms'][0]['status'] = 'verified'
        errors = self.errors()
        self.assertIn('unsupported_authority_completion', errors)
        self.assertIn('unsupported_authority_certification:whole_rule_certified', errors)
        self.assertIn('unsupported_authority_atom_status:A1', errors)

    def test_pending_and_exclusion_require_reason_and_cannot_hide_atom_links(self):
        self.spec['candidate_dispositions'][0].update(disposition='excluded_from_root_scope', reason='')
        errors = self.errors()
        self.assertIn('missing_disposition_reason:C1', errors)
        self.assertIn('unexpected_disposition_links:C1', errors)

    def test_index_gaps_stay_outside_target_union(self):
        self.spec['index_gaps'] = [dict(candidate_id='LEAF', reason='Authority might be under another symbol')]
        self.assertEqual(self.errors(), [])
        self.spec['index_gaps'][0]['candidate_id'] = 'C1'
        self.assertIn('invalid_authority_gap_candidate:C1', self.errors())

    def test_malformed_parent_and_status_fields_return_errors_instead_of_crashing(self):
        self.spec['atoms'][0]['parent_candidate_ids'] = None
        self.spec['atoms'][0]['symbol'] = {}
        self.spec['atoms'][0]['modality'] = []
        self.spec['candidate_dispositions'][0]['disposition'] = []
        errors = self.errors()
        self.assertIn('invalid_authority_parents:A1', errors)
        self.assertIn('invalid_authority_atom_symbol:A1', errors)
        self.assertIn('invalid_authority_modality:A1', errors)
        self.assertIn('invalid_disposition_status:C1', errors)
        self.assertIn('missing_forward_authority_link:C1:A1', errors)

    def test_integrity_pass_report_never_claims_semantic_coverage(self):
        spec_path = self.root / SPEC
        write_json(spec_path, self.spec)
        report = build_report(self.spec, self.root, spec_path)
        self.assertEqual(report['status'], 'draft_integrity_pass')
        self.assertFalse(report['whole_rule_certified'])
        self.assertFalse(report['semantic_completeness_proved'])
        self.assertIsNone(report['coverage_percent'])
        self.assertEqual(report['draft_records'], 1)
        self.assertIn(GRAPH, report['input_hashes'])
        self.assertIn(f'{REVIEWS}/ch2.json', report['input_hashes'])
        self.assertIn('input/ch2.md', report['input_hashes'])


def main():
    global REAL_ROOT, REAL_SPEC
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    REAL_ROOT = args.root.resolve()
    REAL_SPEC = args.spec.resolve() if args.spec else REAL_ROOT / SPEC
    class Result(unittest.TextTestResult):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.rows = []
        def addSuccess(self, test):
            super().addSuccess(test)
            self.rows.append(dict(id='ROOT-AUTHORITY-' + test._testMethodName, status='pass'))
        def addFailure(self, test, error):
            super().addFailure(test, error)
            self.rows.append(dict(id='ROOT-AUTHORITY-' + test._testMethodName, status='fail'))
        def addError(self, test, error):
            super().addError(test, error)
            self.rows.append(dict(id='ROOT-AUTHORITY-' + test._testMethodName, status='error'))
        def addSubTest(self, test, subtest, error):
            super().addSubTest(test, subtest, error)
            if error is not None:
                self.rows.append(dict(id='ROOT-AUTHORITY-' + test._testMethodName + ':' + str(subtest), status='fail'))
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(AuthorityAtomTests))
    spec = json.loads(REAL_SPEC.read_text(encoding='utf-8-sig'))
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), whole_rule_certified=False,
                  semantic_completeness_proved=False, tests_run=result.testsRun, results=result.rows,
                  limitation='Mutation tests establish validator integrity, not semantic completeness of the rulebook.',
                  input_hashes=input_hashes(spec, REAL_ROOT, REAL_SPEC, [('tools/test_root_authority_atoms.py', Path(__file__))]))
    output = args.output or REAL_ROOT / 'output/root-authority-atoms-tests.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
