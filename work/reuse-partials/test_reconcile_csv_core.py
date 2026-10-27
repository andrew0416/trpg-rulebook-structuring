"""Metadata-only regression checks for the existing CSV core-table registry."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest

import reconcile_batch as batch


class CsvCoreRegistryTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(id='C2TAB/tm/r078c4-5', source_file='input/db/tm.csv',
                        row=78, columns=[4, 5], name='혼란', statement='세 가지 내성 결과\n',
                        source_sha256='f' * 64, include_category2=True,
                        denominator_contribution=1, status='incomplete',
                        completion_credit=False, deduplication_status='independent-state-source-contract')
        self.statement_sha = batch.digest(self.row['statement'].encode('utf-8'))
        self.details = dict(registry='csv-core', source_statement_sha256=self.statement_sha,
                            obligation='Complete selected source state contract.',
                            field_authority=['engine/confusion_attacks.py:start_turn'],
                            producers=['Engine.start_of_turn'], consumers=['Engine.move'],
                            tests=['tools.test_existing.ExistingTests.test_three_bands'],
                            canonical_state_references=['actor.conditions'])

    def spec(self):
        return dict(id='csv-core-registry-test', implementation_credit=0,
                    native_paths=['Engine.start_of_turn'], foundation_ids=['existing'],
                    changes=['Connect existing source registry.'],
                    reviewed_files=['engine/confusion_attacks.py'], logs=['actual.log'],
                    required_test_modules=['tools.test_existing'],
                    runtime_changes=[], test_changes=[], source_corrections=[],
                    staged_artifacts=[], selection={'queried_clause_ids':[self.row['id']]}, deferred={},
                    completed={self.row['id']:deepcopy(self.details)})

    def preflight(self, spec, rows):
        with tempfile.TemporaryDirectory(prefix='csv-core-registry-', dir=Path(__file__).parent) as folder:
            root = Path(folder)
            target = root / 'data/verification'
            target.mkdir(parents=True)
            (root / batch.PLAN).write_text(json.dumps(dict(
                foundation_discovery=dict(foundation_freeze=dict(unit_ids=['existing'])))), encoding='utf-8')
            registry=next(iter(spec['completed'].values()))['registry']
            filename,key,_=batch.REGISTRIES[registry]
            (target / filename).write_text(json.dumps({key:rows}), encoding='utf-8')
            (root / 'engine').mkdir()
            (root / 'engine/confusion_attacks.py').write_text('# existing owner\n', encoding='utf-8')
            batch.validate_candidate_metadata(spec, repo_root=root)

    def test_registered_independent_row_uses_status_and_statement_digest(self):
        self.assertEqual(batch.REGISTRIES['csv-core'],
                         ('category2-tabular-core-status.json', 'entries', 'id'))
        self.assertTrue(batch.registry_included(self.row, 'csv-core'))
        self.assertEqual(batch.registry_status(self.row, 'csv-core'), 'incomplete')
        self.assertEqual(batch.registry_source_digests(self.row, 'csv-core'), {self.statement_sha})
        other = dict(self.row, statement='A different obligation in the same CSV.')
        self.assertNotEqual(batch.registry_source_digests(other, 'csv-core'), {self.statement_sha})
        self.assertNotIn(self.row['source_sha256'], batch.registry_source_digests(self.row, 'csv-core'))

    def test_parent_duplicates_and_out_of_scope_rows_cannot_receive_credit(self):
        for patch in (dict(denominator_contribution=0), dict(include_category2=False),
                      dict(denominator_contribution=None)):
            row = dict(self.row, **patch)
            self.assertFalse(batch.registry_included(row, 'csv-core'))
            with self.assertRaisesRegex(RuntimeError, 'included CSV core registry ID'):
                self.preflight(self.spec(), [row])

    def test_source_reference_preserves_exact_locator_and_whole_file_hash(self):
        ref = batch.registry_source_reference(self.row['id'], self.row, 'csv-core', self.statement_sha)
        self.assertEqual(ref['sha256'], self.statement_sha)
        self.assertEqual(ref['source_file_sha256'], self.row['source_sha256'])
        self.assertEqual(ref['blocks'], ['input/db/tm.csv:R78:4-5'])
        self.assertEqual(ref['columns'], [4, 5])
        ref['columns'].append(6)
        self.assertEqual(self.row['columns'], [4, 5])
        repeated = dict(self.row, source_file='input/db/learnsets.csv', columns=[13],
                        source_occurrences=[dict(row=369, species='example'), dict(row=370, species='other')])
        del repeated['row']
        refs = batch.registry_source_reference(repeated['id'], repeated, 'csv-core', self.statement_sha)
        self.assertEqual(refs['blocks'], ['input/db/learnsets.csv:R369:13-13',
                                         'input/db/learnsets.csv:R370:13-13'])

    def test_completion_keeps_source_scope_and_records_actual_evidence(self):
        old = deepcopy(self.row)
        verification = dict(unique_tests=1, runs=[dict(log='data/verification/actual.log')])
        batch.complete_registry_row(self.row, 'csv-core', self.details,
                                    'plan#actual', verification, '2026-10-26', self.row['id'])
        self.assertEqual(self.row['status'], 'implemented')
        self.assertIs(self.row['completion_credit'], True)
        self.assertEqual(self.row['tests'], self.details['tests'])
        self.assertEqual(self.row['evidence_scope'], 'plan#actual')
        self.assertEqual(self.row['completion_evidence']['verification']['logs'],
                         ['data/verification/actual.log'])
        self.assertNotIn('category2_status', self.row)
        for key, value in old.items():
            if key not in ('status', 'completion_credit'):
                self.assertEqual(self.row[key], value, key)

    def test_preflight_rejects_wrong_row_digest_and_file_digest(self):
        self.preflight(self.spec(), [self.row])
        for digest in ('0' * 64, self.row['source_sha256']):
            spec = self.spec()
            spec['completed'][self.row['id']]['source_statement_sha256'] = digest
            with self.assertRaisesRegex(RuntimeError, 'CSV core source digest'):
                self.preflight(spec, [self.row])
        conflict = self.spec()
        conflict['completed'][self.row['id']]['source_sha256'] = self.row['source_sha256']
        with self.assertRaisesRegex(RuntimeError, 'CSV core source digest'):
            self.preflight(conflict, [self.row])
        with self.assertRaisesRegex(RuntimeError, 'included CSV core registry ID'):
            self.preflight(self.spec(), [dict(self.row, id='another-row')])

    def test_existing_registry_adapters_unchanged(self):
        csv = dict(include_category2=True, dedupe_target=None, status='incomplete',
                   cell_sha256='c' * 64)
        self.assertTrue(batch.registry_included(csv, 'class_csv'))
        self.assertEqual(batch.registry_source_digests(csv, 'class_csv'), {'c' * 64})
        self.assertEqual(batch.registry_status(csv, 'class_csv'), 'incomplete')
        core = dict(category2_included=True, category2_status='incomplete', statement_sha256='d' * 64)
        self.assertTrue(batch.registry_included(core, 'core'))
        self.assertEqual(batch.registry_source_digests(core, 'core'), {'d' * 64})
        self.assertEqual(batch.registry_status(core, 'core'), 'incomplete')
        self.assertFalse(batch.registry_included(dict(csv, dedupe_target='book-parent'), 'class_csv'))

    def source_registry_cases(self):
        uid=self.row['id'];row_sha=self.statement_sha;file_sha=self.row['source_sha256']
        rows={
            'core':dict(clause_id=uid,category2_included=True,statement_sha256=row_sha),
            'class_csv':dict(id=uid,include_category2=True,dedupe_target=None,cell_sha256=row_sha),
            'class':dict(source_clause_id=uid,include_category2=True,anchors=[dict(sha256=row_sha)]),
            'optional':dict(clause_id=uid,category2_in_scope=True,source=[dict(excerpt_sha256=row_sha)]),
            'csv-items':dict(clause_id=uid,category2_in_scope=True,source=[dict(raw_cells_sha256=row_sha)]),
            'csv-core':deepcopy(self.row),
            'csv':dict(row_id=uid,category2_included=True,source_row_sha256=row_sha),
        }
        rows['optional-additional']=deepcopy(rows['optional'])
        for alias in ('csv_moves','csv_abilities'):rows[alias]=deepcopy(rows['csv'])
        for registry,row in rows.items():
            spec=self.spec();details=spec['completed'][uid]
            details.update(registry=registry,source_row_sha256=row_sha,source_file_sha256=file_sha)
            yield registry,row,spec

    def test_all_registries_reject_whole_file_precedence_without_rewriting_candidate(self):
        for registry,row,spec in self.source_registry_cases():
            with self.subTest(registry=registry):
                self.preflight(spec,[row])
                details=spec['completed'][self.row['id']]
                details['source_sha256']=self.row['source_sha256']
                before=deepcopy(spec)
                with self.assertRaisesRegex(RuntimeError,'source digest.*selected source_sha256'):
                    self.preflight(spec,[row])
                self.assertEqual(spec,before)
                del details['source_sha256']
                self.preflight(spec,[row])

    def test_all_registries_require_actual_included_id_with_existing_dedupe_adapter(self):
        for registry,row,spec in self.source_registry_cases():
            with self.subTest(registry=registry):
                _,_,id_field=batch.REGISTRIES[registry]
                with self.assertRaisesRegex(RuntimeError,'included .* registry ID'):
                    self.preflight(spec,[dict(row,**{id_field:'UNREGISTERED'})])
                excluded=deepcopy(row)
                flag=('include_category2' if registry in ('csv-core','class_csv','class') else
                      'category2_in_scope' if registry in ('optional','optional-additional','csv-items') else
                      'category2_included')
                excluded[flag]=False
                with self.assertRaisesRegex(RuntimeError,'included .* registry ID'):
                    self.preflight(spec,[excluded])
                if registry=='class_csv':
                    with self.assertRaisesRegex(RuntimeError,'included class_csv registry ID'):
                        self.preflight(spec,[dict(row,dedupe_target='BOOK_PARENT')])

    def test_main_and_preflight_use_the_same_declared_digest_priority(self):
        fields=('source_sha256','source_row_sha256','cell_sha256','source_statement_sha256')
        details=dict(source_file_sha256='whole-file-only')
        self.assertEqual(batch.candidate_source_identity(details),(None,None))
        for field in reversed(fields):
            details[field]=field
            self.assertEqual(batch.candidate_source_identity(details),(field,field))
        details['source_sha256']=''
        self.assertEqual(batch.candidate_source_identity(details),('source_row_sha256','source_row_sha256'))


class MetadataPreflightTests(unittest.TestCase):
    """Preparation mistakes must fail before evidence reconciliation or writes."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='metadata-preflight-', dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data/verification').mkdir(parents=True)
        (self.root / batch.PLAN).write_text(json.dumps(dict(
            foundation_discovery=dict(foundation_freeze=dict(unit_ids=['existing'])))), encoding='utf-8')
        (self.root / 'engine').mkdir()
        (self.root / 'engine/owner.py').write_text('# synthetic existing owner\n', encoding='utf-8')
        self.stage = self.root / 'stage'
        self.stage.mkdir()
        (self.stage / 'baseline.json').write_text('{}', encoding='utf-8')
        source_sha='a'*64
        (self.root / 'data/verification/category2-optional-clause-status.json').write_text(
            json.dumps({'rows':[dict(clause_id='SYNTHETIC',category2_in_scope=True,
                                    source=[dict(excerpt_sha256=source_sha)])]}),encoding='utf-8')
        details = dict(registry='optional', source_sha256=source_sha, obligation='Whole independent clause.',
                       field_authority=['input/source'], producers=['Owner.produce'],
                       consumers=['Owner.consume'], tests=['tools.test_owner.Tests.test_contract'],
                       canonical_state_references=['actor.existing_state'])
        self.spec = dict(id='metadata-preflight-test', implementation_credit=0,
                         native_paths=['Owner.consume'], foundation_ids=['existing'],
                         changes=['Reuse existing contract.'], reviewed_files=['engine/owner.py'],
                         logs=['actual.log'], required_test_modules=['tools.test_owner'],
                         runtime_changes=[], test_changes=[], source_corrections=[],
                         staged_artifacts=[], selection={'queried_clause_ids':['SYNTHETIC']},
                         completed={'SYNTHETIC':details}, deferred={})

    def check(self):
        batch.validate_candidate_metadata(self.spec, repo_root=self.root, stage=self.stage)

    def test_missing_reconciliation_fields_fail_before_any_output(self):
        for field in ('field_authority', 'producers', 'consumers', 'tests', 'canonical_state_references'):
            original = self.spec['completed']['SYNTHETIC'].pop(field)
            with self.assertRaisesRegex(RuntimeError, field):
                self.check()
            self.spec['completed']['SYNTHETIC'][field] = original
        self.check()
        self.assertEqual(list(self.stage.iterdir()), [self.stage / 'baseline.json'])

    def test_baseline_is_required_dictionary_not_owner_flat_list(self):
        baseline = self.stage / 'baseline.json'
        baseline.unlink()
        with self.assertRaisesRegex(RuntimeError, 'baseline.json'):
            self.check()
        for value in ([], {'engine/owner.py':'not-a-sha'}):
            baseline.write_text(json.dumps(value), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'baseline'):
                self.check()
        baseline.write_text(json.dumps({'engine/owner.py':None}), encoding='utf-8')
        self.check()

    def test_range_and_fragment_locators_resolve_existing_containing_file(self):
        for reference in ('engine/owner.py:12-34', 'engine/owner.py:R12-R34',
                          'engine/owner.py#L12-L34', 'engine/owner.py:12'):
            self.spec['reviewed_files'] = [reference]
            self.check()
            self.assertEqual(batch.reviewed_file_name(reference), 'engine/owner.py')

    def test_reviewed_missing_or_unsafe_path_fails_early(self):
        for reference in ('engine/missing.py#L1', '../outside.py', 'engine/owner.py:all16columns'):
            self.spec['reviewed_files'] = [reference]
            with self.assertRaisesRegex(RuntimeError, 'reviewed_files'):
                self.check()

    def test_reviewed_staged_payload_uses_same_file_selection_as_main(self):
        self.spec['source_corrections'] = ['review.md']
        self.spec['reviewed_files'] = ['review.md#contract']
        (self.stage / 'review.md').write_text('Source review.\n', encoding='utf-8')
        self.check()

    def test_queried_clause_ids_cannot_fail_late_after_staging_outputs(self):
        for selection in ({}, {'queried_clause_ids':[]}, {'queried_clause_ids':['OTHER']},
                          {'queried_clause_ids':['SYNTHETIC','SYNTHETIC']}):
            self.spec['selection'] = selection
            with self.assertRaisesRegex(RuntimeError, 'selection.queried_clause_ids'):
                self.check()

    def test_required_module_declaration_cannot_fail_late_in_reuse_audit(self):
        del self.spec['required_test_modules']
        with self.assertRaisesRegex(RuntimeError, 'required_test_modules'):
            self.check()

    def test_required_module_paths_fail_before_staging_not_in_final_reuse_audit(self):
        for module in ('tools/test_owner.py', 'tools\\test_owner.py', 'tools.test_owner.py'):
            self.spec['required_test_modules']=[module]
            with self.subTest(module=module), self.assertRaisesRegex(RuntimeError,'module names, not file paths'):
                self.check()
            self.assertEqual(list(self.stage.iterdir()),[self.stage / 'baseline.json'])
        self.spec['required_test_modules']=['tools.test_owner']
        self.check()

    def test_legacy_sweep_deferred_fields_fail_before_staging_outputs(self):
        plan_path=self.root / batch.PLAN
        plan=json.loads(plan_path.read_text(encoding='utf-8'))
        plan['latest_reassessment']={'ready_sweep':{'rows':[{'id':'HELD'}]}}
        plan_path.write_text(json.dumps(plan),encoding='utf-8')
        self.spec['deferred']={'HELD':{'reason':'Source is missing.'}}
        for field in ('observed','prerequisite','resume_when'):
            with self.assertRaisesRegex(RuntimeError,field):
                self.check()
            self.spec['deferred']['HELD'][field]='Exact source-backed missing requirement.'
        self.check()
        self.assertEqual(list(self.stage.iterdir()),[self.stage / 'baseline.json'])

    def test_later_registry_deferred_clause_does_not_require_legacy_sweep_fields(self):
        self.spec['deferred']={'LATER_CSV_PARENT':{'reason':'Exact source is missing.'}}
        self.check()

    def test_retained_and_repair_keep_their_existing_metadata_shapes(self):
        original=deepcopy(self.spec)
        self.spec.update(existing_proof_only=True,logs=[])
        self.spec['completed']['SYNTHETIC'].update(tests=[],reused_test_ids=['tools.test_owner.Tests.test_contract'])
        self.check()
        self.spec=original
        self.spec.update(repair_only=True,completed={},deferred={},traversal=[],
                         selection={'queried_clause_ids':[],'admitted_clause_ids':[]})
        (self.root / 'data/verification/category2-optional-clause-status.json').unlink()
        self.check()


if __name__ == '__main__':
    unittest.main()
