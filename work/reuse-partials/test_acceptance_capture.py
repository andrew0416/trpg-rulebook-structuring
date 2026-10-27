"""Workflow regressions; synthetic unit evidence is never game completion proof."""
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from acceptance_evidence import verify_acceptance_evidence
import reconcile_batch


CASE = 'test_capture.CaptureTests.test_one'


class AcceptanceCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(dir=os.environ['TEMP'], prefix='acceptance-capture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / 'stage'
        self.stage.mkdir()
        self.canonical = self.root / 'canonical'
        self.canonical.mkdir()
        self.runtime = self.stage / 'runtime.py'
        self.runtime.write_text('# synthetic workflow fixture\n', encoding='utf-8')
        self.runner = self.canonical / 'work/reuse-partials/verify_overlay_tests.py'
        self.runner.parent.mkdir(parents=True)
        self.runner.write_text('# synthetic tooling fixture\n', encoding='utf-8')
        self.runs = []
        self.logs = []

    def record(self, name, raw_status='ok', archive_canonical=None, **changes):
        captured = {path: path.read_bytes() for path in (self.runtime, self.runner)}
        pre = {str(path): sha256(data).hexdigest() for path, data in captured.items()}
        origin = {'runtime': {'file': str(self.runtime), 'sha256': pre[str(self.runtime)]}}
        meta = dict(runtime_test_data_sha256_before=pre, runtime_test_data_sha256_after=pre,
                    stable_hashes=True, physical_open_saved_before_overlay=True,
                    input_paths_missing_pre_execution_capture=[], complete_pre_input_capture=True,
                    actual_read_paths=list(pre), first_actual_read_sha256=pre,
                    loaded_module_origins_before_execution=origin, loaded_module_origins=origin,
                    loaded_inputs_missing_pre_execution_capture=[], complete_loaded_input_capture=True,
                    changed_origin_errors=[], capture_errors=[], frozen_inputs=name + '.zip',
                    test_ids=[CASE], actual_test_ids=[CASE], tests=1, failure_ids=[], error_ids=[],
                    raw_log=name + '.log', successful=True, exit_code=0, exception=None)
        if raw_status == 'FAIL':
            meta.update(failure_ids=[CASE], successful=False, exit_code=1)
        meta.update(changes)
        with ZipFile(self.stage / meta['frozen_inputs'], 'w') as archive:
            for physical, data in captured.items():
                for root, prefix in ((self.stage, 'stage/'),
                                     (archive_canonical or self.canonical, 'canonical/')):
                    if physical.is_relative_to(root):
                        entry = prefix + physical.relative_to(root).as_posix()
                        break
                else:
                    entry = 'tooling/' + physical.name
                archive.writestr(entry, data)
            archive.writestr('physical-sha256.json', json.dumps(pre))
        (self.stage / meta['raw_log']).write_text(
            f'test_one ({CASE}) ... {raw_status}\n\nRan 1 test in 0.001s\n\n' +
            ('OK\n' if raw_status == 'ok' else 'FAILED (failures=1)\n'), encoding='utf-8')
        (self.stage / (name + '.json')).write_text(json.dumps(meta), encoding='utf-8')
        self.runs.append({'metadata': name + '.json'})
        self.logs.append(meta['raw_log'])

    def verify(self):
        return verify_acceptance_evidence(self.stage, dict(
            game_runs=len(self.runs), test_executions=len(self.runs), required_test_ids=[CASE],
            completed={'synthetic-unit-only': {'tests': [CASE]}}, execution_history=self.runs,
            logs=self.logs), self.canonical)

    def test_complete_capture_remains_eligible(self):
        self.record('complete')
        self.assertTrue(self.verify()['runs'][0]['acceptance_eligible'])

    def command(self, canonical=None):
        return ['python', str(self.runner), '--stage', str(self.stage),
                '--canonical', str(canonical or self.canonical)]

    def test_mixed_historical_stage_and_current_canonical_use_each_recorded_root(self):
        self.record('history-stage', raw_status='FAIL', archive_canonical=self.stage,
                    command=self.command(self.stage), execution_stage=str(self.stage))
        self.record('current-canonical', command=self.command(), execution_stage=str(self.stage))
        result = self.verify()
        self.assertFalse(result['runs'][0]['successful'])
        self.assertEqual(result['runs'][0]['failure_ids'], [CASE])
        self.assertEqual(result['latest_valid_passes'], {CASE: 'current-canonical.json'})
        self.assertEqual((result['game_commands'], result['test_invocations']), (2, 2))

    def test_equals_root_switches_keep_exact_zip_mapping(self):
        self.record('equals', archive_canonical=self.stage,
                    command=['python', str(self.runner), '--stage=' + str(self.stage),
                             '--canonical=' + str(self.stage)], execution_stage=str(self.stage))
        self.assertTrue(self.verify()['runs'][0]['acceptance_eligible'])

    def test_external_or_relative_recorded_roots_are_rejected(self):
        for index, root in enumerate((self.root / 'external', Path('relative'))):
            with self.subTest(root=root):
                self.runs.clear()
                self.logs.clear()
                self.record('outside' + str(index), command=self.command(root))
                with self.assertRaisesRegex(RuntimeError, 'recorded canonical root'):
                    self.verify()

    def test_conflicting_recorded_stages_are_rejected(self):
        for index, changes in enumerate((
                dict(command=['python', '--stage', str(self.root), '--canonical', str(self.canonical)]),
                dict(command=self.command(), execution_stage=str(self.root)))):
            with self.subTest(changes=changes):
                self.runs.clear()
                self.logs.clear()
                self.record('stage-conflict' + str(index), **changes)
                with self.assertRaisesRegex(RuntimeError, 'recorded execution stage'):
                    self.verify()

    def test_duplicate_or_missing_recorded_root_switches_are_rejected(self):
        commands = [self.command() + ['--canonical=' + str(self.canonical)],
                    self.command() + ['--stage', str(self.stage)],
                    ['python', '--stage', str(self.stage)],
                    ['python', '--stage', str(self.stage), '--canonical'],
                    ['python', '--canonical', str(self.canonical)],
                    'python --canonical ' + str(self.canonical)]
        for index, command in enumerate(commands):
            with self.subTest(command=command):
                self.runs.clear()
                self.logs.clear()
                self.record('invalid-command' + str(index), command=command)
                with self.assertRaisesRegex(RuntimeError, 'recorded physical command'):
                    self.verify()

    def test_recorded_stage_root_does_not_relax_zip_byte_checks(self):
        self.record('changed-zip', archive_canonical=self.stage, command=self.command(self.stage))
        path = self.stage / 'changed-zip.zip'
        with ZipFile(path) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        entries['tooling/verify_overlay_tests.py'] = b'changed after capture\n'
        with ZipFile(path, 'w') as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        with self.assertRaisesRegex(RuntimeError, 'ZIP bytes SHA mismatch: tooling/verify_overlay_tests.py'):
            self.verify()

    def test_recorded_stage_root_does_not_promote_capture_errors(self):
        self.record('bad-stage', archive_canonical=self.stage, command=self.command(self.stage),
                    capture_errors=['unresolved file-descriptor read: 4'])
        self.record('good-current', command=self.command())
        result = self.verify()
        self.assertFalse(result['runs'][0]['acceptance_eligible'])
        self.assertEqual(result['latest_valid_passes'], {CASE: 'good-current.json'})

    def test_unresolved_descriptor_read_is_not_an_eligible_pass(self):
        self.record('descriptor', capture_errors=['unresolved file-descriptor read: 4'])
        with self.assertRaisesRegex(RuntimeError, 'acceptance-eligible execution'):
            self.verify()

    def test_changed_module_origin_is_not_an_eligible_pass(self):
        self.record('origin', changed_origin_errors=['module origin changed'])
        with self.assertRaisesRegex(RuntimeError, 'acceptance-eligible execution'):
            self.verify()

    def test_incomplete_loaded_flag_is_not_an_eligible_pass(self):
        self.record('loaded', complete_loaded_input_capture=False)
        with self.assertRaisesRegex(RuntimeError, 'acceptance-eligible execution'):
            self.verify()

    def test_missing_loaded_inputs_are_not_an_eligible_pass(self):
        self.record('missing', loaded_inputs_missing_pre_execution_capture=['unseen.py'])
        with self.assertRaisesRegex(RuntimeError, 'acceptance-eligible execution'):
            self.verify()

    def record_uncaptured_origin(self, name, *, legacy=False, rows=None):
        """Synthetic bytes live only in this test's TemporaryDirectory stage."""
        unseen = self.stage / 'uncaptured.py'
        assert unseen.is_relative_to(Path(self.temp.name))
        unseen.write_text('# synthetic uncaptured origin\n', encoding='utf-8')
        paths = (self.runtime, self.runner, unseen)
        reads = {str(p): sha256(p.read_bytes()).hexdigest() for p in paths}
        missing = {'file': str(unseen), 'sha256': reads[str(unseen)]}
        origins = {str(n): {'file': str(p), 'sha256': reads[str(p)]}
                   for n, p in enumerate((self.runtime, unseen))}
        self.record(name, input_paths_missing_pre_execution_capture=[str(unseen)],
                    complete_pre_input_capture=False, actual_read_paths=list(reads),
                    first_actual_read_sha256=reads, loaded_module_origins=origins,
                    loaded_inputs_missing_pre_execution_capture=(
                        rows if rows is not None else [str(unseen) if legacy else missing]),
                    complete_loaded_input_capture=False,
                    capture_errors=['read inputs missing pre-capture'], successful=False, exit_code=1)
        return missing

    def test_producer_dict_missing_origin_history_is_retained_never_promoted_or_rewritten(self):
        self.record_uncaptured_origin('dict-missing')
        evidence = [self.stage / ('dict-missing' + suffix) for suffix in ('.json', '.log', '.zip')]
        before = {p: sha256(p.read_bytes()).hexdigest() for p in evidence}
        self.record('good-after-dict')
        result = self.verify()
        self.assertFalse(result['runs'][0]['acceptance_eligible'])
        self.assertEqual(result['latest_valid_passes'], {CASE: 'good-after-dict.json'})
        self.assertEqual(before, {p: sha256(p.read_bytes()).hexdigest() for p in evidence})

    def test_producer_dict_missing_origin_alone_and_after_good_pass_remain_ineligible(self):
        self.record_uncaptured_origin('only-dict')
        with self.assertRaisesRegex(RuntimeError, 'acceptance-eligible execution'):
            self.verify()
        self.runs.clear()
        self.logs.clear()
        self.record('earlier-good')
        self.record_uncaptured_origin('later-dict')
        with self.assertRaisesRegex(RuntimeError, 'acceptance-eligible execution'):
            self.verify()

    def test_legacy_string_missing_origin_history_keeps_its_original_form(self):
        self.record_uncaptured_origin('legacy-missing', legacy=True)
        self.record('good-after-string')
        result = self.verify()
        self.assertFalse(result['runs'][0]['acceptance_eligible'])
        self.assertEqual(result['latest_valid_passes'], {CASE: 'good-after-string.json'})

    def test_structured_missing_origin_requires_exact_keys_file_and_digest_format(self):
        original = self.record_uncaptured_origin('bad-shape')
        path = self.stage / 'bad-shape.json'
        good = json.loads(path.read_text(encoding='utf-8'))
        invalid = [None, {}, {'file': original['file']}, {'sha256': original['sha256']},
                   dict(original, extra=True), dict(original, file=1), dict(original, file=''),
                   dict(original, file='relative.py'), dict(original, sha256=True),
                   dict(original, sha256='G' * 64), dict(original, sha256='a' * 63)]
        for value in invalid:
            with self.subTest(value=value):
                meta = dict(good, loaded_inputs_missing_pre_execution_capture=[value])
                path.write_text(json.dumps(meta), encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, 'invalid physical capture field'):
                    self.verify()

    def test_missing_origin_duplicates_and_omitted_records_are_rejected(self):
        original = self.record_uncaptured_origin('duplicates')
        path = self.stage / 'duplicates.json'
        good = json.loads(path.read_text(encoding='utf-8'))
        for rows in ([original, original], [original['file'], original['file']],
                     [original, original['file']], [], ['']):
            with self.subTest(rows=rows):
                path.write_text(json.dumps(dict(good,
                    loaded_inputs_missing_pre_execution_capture=rows)), encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, 'invalid physical capture field'):
                    self.verify()
        omitted = dict(good)
        omitted.pop('loaded_inputs_missing_pre_execution_capture')
        path.write_text(json.dumps(omitted), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'invalid physical capture field'):
            self.verify()

    def test_structured_missing_origin_must_match_actual_origin_and_first_read(self):
        original = self.record_uncaptured_origin('forged')
        path = self.stage / 'forged.json'
        good = json.loads(path.read_text(encoding='utf-8'))
        forged = [dict(original, file=str(self.stage / 'not-observed.py')),
                  dict(original, sha256='b' * 64),
                  {'file': str(self.runtime), 'sha256': sha256(self.runtime.read_bytes()).hexdigest()}]
        for value in forged:
            with self.subTest(value=value):
                path.write_text(json.dumps(dict(good,
                    loaded_inputs_missing_pre_execution_capture=[value])), encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, 'invalid physical capture field'):
                    self.verify()
        meta = dict(good, loaded_module_origins=good['loaded_module_origins_before_execution'])
        path.write_text(json.dumps(meta), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'invalid physical capture field'):
            self.verify()

    def test_structured_origin_shape_does_not_relax_string_only_error_diagnostics(self):
        self.record('strict-diagnostics')
        path = self.stage / 'strict-diagnostics.json'
        good = json.loads(path.read_text(encoding='utf-8'))
        for field in ('capture_errors', 'changed_origin_errors'):
            with self.subTest(field=field):
                value = dict(good, **{field: [{'file': str(self.runtime), 'sha256': 'a' * 64}]})
                path.write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, 'invalid physical capture field'):
                    self.verify()

    def test_malformed_capture_fields_are_rejected(self):
        self.record('malformed', capture_errors='not a diagnostic list')
        with self.assertRaisesRegex(RuntimeError, 'invalid physical capture field'):
            self.verify()

    def test_malformed_loaded_flag_is_rejected(self):
        self.record('malformed-flag', complete_loaded_input_capture=None)
        with self.assertRaisesRegex(RuntimeError, 'invalid physical capture field'):
            self.verify()

    def test_error_history_is_retained_but_only_new_complete_run_proves_pass(self):
        self.record('bad', capture_errors=['unresolved file-descriptor read: 5'])
        self.record('good')
        result = self.verify()
        self.assertFalse(result['runs'][0]['acceptance_eligible'])
        self.assertIn('capture', result['runs'][0]['acceptance_ineligible_reason'])
        self.assertTrue(result['runs'][1]['acceptance_eligible'])
        self.assertEqual(result['latest_valid_passes'], {CASE: 'good.json'})
        self.assertEqual((result['game_commands'], result['test_invocations']), (2, 2))

    def test_new_ineligible_execution_invalidates_older_pass(self):
        self.record('good')
        self.record('bad', capture_errors=['unresolved file-descriptor read: 5'])
        with self.assertRaisesRegex(RuntimeError, 'acceptance-eligible execution'):
            self.verify()

    def test_capture_failure_wrapper_is_preserved_but_never_proves_pass(self):
        self.record('capture-failed', capture_errors=['read inputs missing pre-capture'],
                    successful=False, exit_code=1)
        self.record('good')
        result = self.verify()
        self.assertFalse(result['runs'][0]['acceptance_eligible'])
        self.assertEqual(result['latest_valid_passes'], {CASE: 'good.json'})
        self.assertEqual((result['game_commands'], result['test_invocations']), (2, 2))

    def test_capture_failure_wrapper_without_later_pass_stays_ineligible(self):
        self.record('capture-failed', capture_errors=['read inputs missing pre-capture'],
                    successful=False, exit_code=1)
        with self.assertRaisesRegex(RuntimeError, 'acceptance-eligible execution'):
            self.verify()

    def test_complete_capture_cannot_explain_wrapper_failure(self):
        self.record('unexplained-wrapper', successful=False, exit_code=1)
        with self.assertRaisesRegex(RuntimeError, 'contradict raw results'):
            self.verify()

    def test_capture_error_does_not_excuse_wrapper_claiming_failed_tests_passed(self):
        self.record('failed-tests', raw_status='FAIL', capture_errors=['capture failed'],
                    successful=True, exit_code=0)
        with self.assertRaisesRegex(RuntimeError, 'contradict raw results'):
            self.verify()

    def test_older_schema_without_optional_diagnostics_keeps_existing_checks(self):
        self.record('legacy')
        path = self.stage / 'legacy.json'
        meta = json.loads(path.read_text(encoding='utf-8'))
        for field in ('capture_errors', 'changed_origin_errors',
                      'loaded_inputs_missing_pre_execution_capture', 'complete_loaded_input_capture'):
            meta.pop(field)
        path.write_text(json.dumps(meta), encoding='utf-8')
        self.assertTrue(self.verify()['runs'][0]['acceptance_eligible'])


class ReusedProofTests(unittest.TestCase):
    def run_record(self, *, eligible=True, mixed=False):
        result = dict(log='original.log', sha256='a' * 64, tests=2, seconds=0.1,
                      result='FAILED' if mixed else 'PASS', cases=['one', 'two'],
                      acceptance_eligible=eligible)
        if mixed:
            result['case_results'] = {'one': 'ok', 'two': 'FAIL'}
        return result

    def test_ineligible_full_pass_is_not_reused(self):
        self.assertEqual(reconcile_batch.eligible_run_proofs([self.run_record(eligible=False)]), [])

    def test_ineligible_individual_pass_is_not_reused(self):
        self.assertEqual(reconcile_batch.eligible_run_proofs(
            [self.run_record(eligible=False, mixed=True)]), [])

    def test_eligible_full_pass_keeps_existing_proof_shape(self):
        run = self.run_record()
        expected = {key: run[key] for key in ('log', 'sha256', 'tests', 'seconds')}
        self.assertEqual(reconcile_batch.eligible_run_proofs([run]), [expected])

    def test_eligible_mixed_run_reuses_only_actual_passes_without_mutating_history(self):
        run = self.run_record(mixed=True)
        before = json.dumps(run, sort_keys=True)
        proof = reconcile_batch.eligible_run_proofs([run])
        self.assertEqual(proof[0]['cases'], ['one'])
        self.assertEqual(json.dumps(run, sort_keys=True), before)

    def test_nonphysical_legacy_proof_shape_is_unchanged(self):
        run = self.run_record()
        run.pop('acceptance_eligible')
        self.assertEqual(len(reconcile_batch.eligible_run_proofs([run])), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
