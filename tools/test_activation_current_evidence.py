"""Stdlib-only synthetic protocol controls; no game imports, runs or H acceptance."""
import ast
import copy
import hashlib
import io
import json
from pathlib import Path, PureWindowsPath
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
import activation_current_evidence as E

class CurrentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='activation-proof-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'candidate'
        self.root.mkdir()
        self.uid = 'tools.test_toy.Cases.test_one'
        self.key = 'new-run/suite'
        self.old = {'file': 'engine/toy.py', 'function': 'f', 'start': 1, 'end': 2,
                    'file_sha256': '1' * 64, 'excerpt_sha256': '2' * 64}
        self.spec = {'source_anchors': [], 'conditions': [{'id': 'ROOT-08', 'runtime_paths': [self.old]}],
                     'evidence_catalog': {'toy': {'passing_test_ids': ['OLD-test_one']}}}
        self.write('engine/toy.py', b'def f():\n    return 1\n')
        self.write('tools/test_toy.py', b'# synthetic-only native identity fixture\n')
        self.write('tools/activation_current_evidence.py', Path(E.__file__).read_bytes())
        self.write('tools/audit_common_activation_matrix.py', b'# synthetic-only consumer fixture\n')
        self.history = 'data/verification/history.json'
        self.write(self.history, E.encoded(self.spec))
        node = ast.parse((self.root / 'engine/toy.py').read_text()).body[0]
        self.requirements = {'historical_matrix': {'path': self.history, 'sha256': E.digest((self.root / self.history).read_bytes())},
            'report_scopes': {'toy': {'producer_source': 'tools/test_toy.py',
                'historical_to_native_ids': {'OLD-test_one': self.uid}, 'required_native_ids': [self.uid]}},
            'required_native_ids': [self.uid], 'source_anchors_unchanged': [],
            'runtime_locators': {'engine/toy.py:f': {'file': 'engine/toy.py', 'symbol': 'f',
                'observed_AST_sha256': E.digest(ast.dump(node, include_attributes=False).encode())}},
            'bounded_support_symbols': [], 'historical_runtime_references': {'ROOT-08': [self.old]}}
        self.write(E.REQUIREMENTS, E.encoded(self.requirements))
        before = {str(PureWindowsPath('D:/synthetic-stage') / p.relative_to(self.root).as_posix()): E.digest(p.read_bytes())
                  for p in self.root.rglob('*') if p.is_file()}
        origin = {'toy': {'file': str(PureWindowsPath('D:/synthetic-stage/engine/toy.py')),
                          'sha256': E.digest((self.root / 'engine/toy.py').read_bytes())}}
        self.meta = {'execution_stage': 'D:/synthetic-stage', 'runtime_test_data_sha256_before': before,
            'runtime_test_data_sha256_after': copy.deepcopy(before), 'stable_hashes': True,
            'loaded_module_origins_before_execution': origin, 'loaded_module_origins': copy.deepcopy(origin),
            'started_utc': '2026-10-25T00:00:00+00:00', 'finished_utc': '2026-10-25T00:01:00+00:00',
            'actual_test_ids': [self.uid], 'failure_ids': [], 'error_ids': [], 'exception': None,
            'method_timings': [{'id': self.uid, 'seconds': 0.1}],
            'actual_read_paths': [], 'first_actual_read_sha256': {}}
        self.fact = {'acceptance_eligible': True, 'stable_hashes': True}
        self.raw_log = b'# wholly synthetic accepted-log protocol fixture; not game execution\n'
        self.frequency = None
        self.envelope_overrides = {}
        self.archive = self.base / 'synthetic.zip'
        self.refresh_pins()

    def write(self, name, body):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def refresh_pins(self):
        body = E.encoded(self.meta)
        frozen = io.BytesIO()
        stage = PureWindowsPath(self.meta['execution_stage'])
        with zipfile.ZipFile(frozen, 'w') as captured:
            for name in self.meta['runtime_test_data_sha256_before']:
                physical = PureWindowsPath(name)
                if physical.is_relative_to(stage):
                    rel = physical.relative_to(stage).as_posix()
                    captured.writestr('stage/' + rel, self.envelope_overrides.get(rel, (self.root / rel).read_bytes()))
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('physical/ci-native.json', body)
            archive.writestr('physical/ci-native.log', self.raw_log)
            archive.writestr('physical/ci-native-inputs.zip', frozen.getvalue())
            if self.frequency is not None:
                archive.writestr('physical/frequency-equivalence.json', E.encoded(self.frequency))
        archive_sha = E.digest(self.archive.read_bytes())
        fact = dict(self.fact, metadata_sha256=E.digest(body), raw_log_sha256=E.digest(self.raw_log),
                    actual_test_ids=self.meta['actual_test_ids'], frozen_inputs_sha256=E.digest(frozen.getvalue()))
        self.cache = {'executions': {self.key: {'archive': str(self.archive), 'archive_sha256': archive_sha,
            'facts': {'mode': 'physical', 'runs': [fact]}, 'validated_actual_statuses': {E.norm(self.uid): 'ok'}}}}
        self.collector = {'executions': {self.key: {'original_archive': str(self.archive), 'original_archive_sha256': archive_sha}}}

    def pins(self):
        body = E.encoded(self.cache)
        hpath = self.base / ('physical-evidence-' + E.digest(body) + '.json')
        hpath.write_bytes(body)
        cpath = self.base / 'collector.json'
        cpath.write_bytes(E.encoded(self.collector))
        return ({'path': str(hpath), 'sha256': E.digest(body)},
                {'path': str(cpath), 'sha256': E.digest(cpath.read_bytes())})

    def derive(self):
        h, c = self.pins()
        return E.derive(self.root, h, c, 'new-run')

    def install(self):
        proof, files = self.derive()
        for name, body in files.items():
            self.write(name, body)
        return proof

    def rejects_derivation(self):
        with self.assertRaises((ValueError, KeyError)):
            self.derive()

    def test_synthetic_roundtrip_preserves_history_and_has_no_game_run_credit(self):
        before = (self.root / self.history).read_bytes()
        proof = self.install()
        self.assertEqual(E.validate_current(self.root, self.spec), [])
        self.assertEqual((self.root / self.history).read_bytes(), before)
        self.assertEqual(proof['game_runs_by_this_producer'], 0)
        self.assertEqual(proof['completion_credit'], 0)

    def test_missing_fresh_proof_cannot_reuse_old_pass(self):
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_current_run_is_not_an_old_H_cache(self):
        self.cache['executions']['old-run/suite'] = self.cache['executions'].pop(self.key)
        self.rejects_derivation()

    def test_capture_eligible_boolean_is_not_independent_H_acceptance(self):
        self.cache['executions'][self.key]['facts'] = {'capture_eligible': True}
        self.rejects_derivation()

    def test_collector_full_archive_sha_is_mandatory(self):
        self.collector['executions'][self.key]['original_archive_sha256'] = None
        self.rejects_derivation()

    def test_changed_full_archive_is_rejected(self):
        with self.archive.open('ab') as stream:
            stream.write(b'changed')
        self.rejects_derivation()

    def test_raw_outcome_bytes_must_match_independent_H_reference(self):
        self.cache['executions'][self.key]['facts']['runs'][0]['raw_log_sha256'] = '0' * 64
        self.rejects_derivation()

    def test_raw_actual_ID_order_must_match_independent_H_reference(self):
        self.cache['executions'][self.key]['facts']['runs'][0]['actual_test_ids'] = []
        self.rejects_derivation()

    def test_changed_candidate_input_is_rejected_before_derivation(self):
        self.write('engine/toy.py', b'def f():\n    return 2\n')
        self.rejects_derivation()

    def test_actual_method_must_be_observed(self):
        self.meta['actual_test_ids'] = []
        self.refresh_pins()
        self.rejects_derivation()

    def test_method_completion_timing_must_be_observed(self):
        self.meta['method_timings'] = []
        self.refresh_pins()
        self.rejects_derivation()

    def test_duplicate_required_method_timing_is_rejected(self):
        self.meta['method_timings'].append(dict(self.meta['method_timings'][0]))
        self.refresh_pins()
        self.rejects_derivation()

    def test_nan_or_boolean_duration_is_not_completion(self):
        for value in (float('nan'), True):
            with self.subTest(value=value):
                self.meta['method_timings'][0]['seconds'] = value
                self.refresh_pins()
                self.rejects_derivation()

    def test_real_failure_cannot_be_turned_into_current_pass(self):
        self.cache['executions'][self.key]['validated_actual_statuses'][E.norm(self.uid)] = 'FAIL'
        self.rejects_derivation()

    def test_raw_failure_id_cannot_contradict_H_pass(self):
        self.meta['failure_ids'] = [self.uid]
        self.refresh_pins()
        self.rejects_derivation()

    def test_native_proof_contract_must_exist_in_pre_capture(self):
        key = str(PureWindowsPath('D:/synthetic-stage') / E.REQUIREMENTS)
        del self.meta['runtime_test_data_sha256_before'][key]
        del self.meta['runtime_test_data_sha256_after'][key]
        self.refresh_pins()
        self.rejects_derivation()

    def test_unknown_or_changed_origin_is_rejected(self):
        self.meta['loaded_module_origins']['toy']['sha256'] = '0' * 64
        self.refresh_pins()
        self.rejects_derivation()

    def test_unfinished_or_reversed_invocation_is_rejected(self):
        self.meta['finished_utc'] = '2026-10-24T00:00:00+00:00'
        self.refresh_pins()
        self.rejects_derivation()

    def test_repeated_required_ID_across_executions_is_ambiguous(self):
        self.cache['executions']['new-run/suite2'] = copy.deepcopy(self.cache['executions'][self.key])
        self.collector['executions']['new-run/suite2'] = copy.deepcopy(self.collector['executions'][self.key])
        self.rejects_derivation()

    def test_historical_required_ID_cannot_be_removed(self):
        self.requirements['report_scopes']['toy']['historical_to_native_ids'] = {}
        self.write(E.REQUIREMENTS, E.encoded(self.requirements))
        self.rejects_derivation()

    def test_metadata_self_dependency_is_rejected(self):
        self.requirements['required_native_ids'].append('tools.test_common_activation_matrix.Tests.test_001_real_matrix_exact_links')
        self.write(E.REQUIREMENTS, E.encoded(self.requirements))
        self.rejects_derivation()

    def test_fake_historical_runtime_location_still_rejects_exact_obligation(self):
        self.install()
        mutated = copy.deepcopy(self.spec)
        mutated['conditions'][0]['runtime_paths'][0]['start'] = 999
        self.assertIn('runtime_excerpt_drift:ROOT-08', E.validate_current(self.root, mutated))

    def test_fake_current_runtime_location_is_rejected(self):
        proof = self.install()
        proof['current_runtime_symbols']['engine/toy.py:f']['start'] = 999
        self.write(E.CURRENT, E.encoded(proof))
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_current_report_rows_cannot_be_removed(self):
        proof = self.install()
        proof['reports']['toy']['results'] = []
        self.write(E.CURRENT, E.encoded(proof))
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_H_support_bytes_cannot_change_after_freeze(self):
        proof = self.install()
        self.write(proof['H_accepted_reference']['path'], b'{}')
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_wrong_schema_and_false_credit_are_rejected(self):
        proof = self.install()
        for field, value in [('schema_version', 99), ('schema_version', True),
                             ('completion_credit', 1), ('completion_credit', False)]:
            with self.subTest(field=field):
                changed = copy.deepcopy(proof)
                changed[field] = value
                self.write(E.CURRENT, E.encoded(changed))
                self.assertTrue(E.validate_current(self.root, self.spec))

    def test_malformed_current_bytes_are_recorded_not_audit_crash(self):
        self.write(E.CURRENT, b'{')
        self.assertTrue(E.validate_current(self.root, self.spec))
        self.assertEqual(E.proof_input_paths(self.root), [E.CURRENT])

    def prepare_synthetic_frequency(self):
        self.uid = 'tools.test_frequencies.FrequencyTests.test_source_move_0000'
        scope = self.requirements['report_scopes']['toy']
        scope['historical_to_native_ids']['OLD-test_one'] = self.uid
        scope['required_native_ids'] = [self.uid]
        self.requirements['required_native_ids'] = [self.uid]
        self.write(E.REQUIREMENTS, E.encoded(self.requirements))
        req_key = str(PureWindowsPath('D:/synthetic-stage') / E.REQUIREMENTS)
        for field in ('runtime_test_data_sha256_before', 'runtime_test_data_sha256_after'):
            self.meta[field][req_key] = E.digest((self.root / E.REQUIREMENTS).read_bytes())
        row = {'started_ids': [self.uid], 'finished_ids': [self.uid], 'testsRun': 1,
               'failures': [], 'errors': [], 'skipped': [], 'never_started_ids': []}
        negative = dict(copy.deepcopy(row), failures=[[self.uid, 'INJECTED_FREQUENCY_CHAIN_FAILURE_AFTER_ORIGINAL_BODY']], blocked_body_ids=[])
        self.frequency = {'status': 'equivalent', 'blocking_check_passed': True,
            'expected_ids': [self.uid], 'expected_method_count': 1, 'mismatched_assertion_traces': [],
            'unknown_observation_types': [], 'expected_blocked_after_injection': [],
            'outcomes': {'cold': row, 'connected': copy.deepcopy(row), 'connected_first_failure': negative}}
        self.refresh_frequency()

    def refresh_frequency(self):
        self.meta.update(execution_kind='frequency_equivalence_gate', actual_test_ids=[],
            ordinary_test_pass_credit=0,
            equivalence_report_sha256=E.digest(E.encoded(self.frequency)))
        self.refresh_pins()
        saved = self.cache['executions'].pop(self.key)
        del saved['validated_actual_statuses']
        saved['facts'].update(execution_kind='frequency_equivalence_gate', typed_status='equivalent',
            equivalence_verified_method_ids=[self.uid], ordinary_test_pass_credit=0)
        self.cache['typed_executions'] = {self.key: saved}

    def test_synthetic_frequency_cold_connected_negative_raw_protocol(self):
        self.prepare_synthetic_frequency()
        proof = self.install()
        self.assertEqual(E.validate_current(self.root, self.spec), [])
        self.assertEqual(proof['native']['ordinary_pass_ids'], [])
        self.assertEqual(proof['reports']['toy']['results'][0]['status'], 'equivalent')

    def test_frequency_is_not_accepted_as_ordinary_cached_PASS(self):
        self.prepare_synthetic_frequency()
        saved = self.cache['typed_executions'].pop(self.key)
        saved['validated_actual_statuses'] = {E.norm(self.uid): 'ok'}
        self.cache['executions'][self.key] = saved
        self.rejects_derivation()

    def test_frequency_true_flag_cannot_replace_missing_injected_failure(self):
        self.prepare_synthetic_frequency()
        self.frequency['outcomes']['connected_first_failure']['failures'] = []
        self.refresh_frequency()
        self.rejects_derivation()

    def test_frequency_assertion_trace_mismatch_is_rejected(self):
        self.prepare_synthetic_frequency()
        self.frequency['mismatched_assertion_traces'] = [self.uid]
        self.refresh_frequency()
        self.rejects_derivation()

    def test_frequency_cold_finished_body_is_required(self):
        self.prepare_synthetic_frequency()
        self.frequency['outcomes']['cold']['finished_ids'] = []
        self.refresh_frequency()
        self.rejects_derivation()

    def prepare_synthetic_envelope(self):
        for rel in sorted(E.NATIVE_ENVELOPE):
            self.write(rel, ('synthetic original envelope ' + rel).encode())
        self.write('.ci/suites/metadata.json', b'{"synthetic_pre_wired":true}\n')
        self.write('.ci/requirements.txt', b'# synthetic unchanged dependency policy\n')
        for rel in [*E.NATIVE_ENVELOPE, '.ci/suites/metadata.json', '.ci/requirements.txt']:
            name = str(PureWindowsPath(self.meta['execution_stage']) / rel)
            for field in ('runtime_test_data_sha256_before', 'runtime_test_data_sha256_after'):
                self.meta[field][name] = E.digest((self.root / rel).read_bytes())
        self.refresh_pins()

    def migrate_synthetic_envelope(self):
        for rel in E.NATIVE_ENVELOPE:
            self.write(rel, ('synthetic phase-two envelope ' + rel).encode())

    def test_phase_two_fixed_three_envelopes_may_migrate_but_original_bytes_are_preserved(self):
        self.prepare_synthetic_envelope()
        originals = {rel: (self.root / rel).read_bytes() for rel in E.NATIVE_ENVELOPE}
        proof = self.install()
        self.migrate_synthetic_envelope()
        self.assertEqual(E.validate_current(self.root, self.spec), [])
        self.assertEqual(set(proof['native_envelope_references']), E.NATIVE_ENVELOPE)
        self.assertFalse(set(proof['native']['input_hashes']) & E.NATIVE_ENVELOPE)
        for rel, body in originals.items():
            ref = proof['native_envelope_references'][rel]
            self.assertEqual(E.read_support(self.root, ref), body)
            self.assertEqual(proof['native']['native_envelope_hashes'][rel], E.digest(body))

    def test_phase_two_changed_runtime_is_not_envelope_migration(self):
        self.prepare_synthetic_envelope()
        self.install()
        self.migrate_synthetic_envelope()
        self.write('engine/toy.py', b'def f():\n    return 99\n')
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_phase_two_changed_test_source_is_not_envelope_migration(self):
        self.prepare_synthetic_envelope()
        self.install()
        self.migrate_synthetic_envelope()
        self.write('tools/test_toy.py', b'# changed native assertion source\n')
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_phase_two_suite_selection_must_be_pre_wired_and_unchanged(self):
        self.prepare_synthetic_envelope()
        self.install()
        self.migrate_synthetic_envelope()
        self.write('.ci/suites/metadata.json', b'{"silent_denominator_reduction":true}\n')
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_phase_two_unlisted_ci_path_is_not_blanket_exempt(self):
        self.prepare_synthetic_envelope()
        self.install()
        self.migrate_synthetic_envelope()
        self.write('.ci/requirements.txt', b'# changed dependency policy\n')
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_original_native_envelope_support_tamper_is_rejected(self):
        self.prepare_synthetic_envelope()
        proof = self.install()
        self.migrate_synthetic_envelope()
        self.write(proof['native_envelope_references']['.ci/source-snapshot.json']['path'], b'forged')
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_original_physical_input_zip_requires_H_digest(self):
        self.prepare_synthetic_envelope()
        self.cache['executions'][self.key]['facts']['runs'][0]['frozen_inputs_sha256'] = '0' * 64
        self.rejects_derivation()

    def test_archived_envelope_bytes_must_match_native_pre_capture(self):
        self.prepare_synthetic_envelope()
        self.envelope_overrides['.ci/source-snapshot.json'] = b'not original pre-captured bytes'
        self.refresh_pins()
        self.rejects_derivation()

    def test_envelope_actually_read_by_native_body_cannot_migrate(self):
        self.prepare_synthetic_envelope()
        name = str(PureWindowsPath(self.meta['execution_stage']) / '.ci/source-snapshot.json')
        self.meta['actual_read_paths'] = [name]
        self.meta['first_actual_read_sha256'] = {name: self.meta['runtime_test_data_sha256_before'][name]}
        self.refresh_pins()
        self.install()
        self.migrate_synthetic_envelope()
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_original_envelope_reference_cannot_claim_arbitrary_ci_or_runtime_path(self):
        self.prepare_synthetic_envelope()
        proof = self.install()
        proof['native_envelope_references']['.ci/requirements.txt'] = proof['native_envelope_references']['.ci/source-snapshot.json']
        self.write(E.CURRENT, E.encoded(proof))
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_missing_original_envelope_reference_is_rejected(self):
        self.prepare_synthetic_envelope()
        proof = self.install()
        del proof['native_envelope_references']['.ci/source-snapshot.json']
        self.write(E.CURRENT, E.encoded(proof))
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_phase_two_rule_data_change_is_not_envelope_migration(self):
        self.prepare_synthetic_envelope()
        self.write('input/rules.json', b'{"synthetic_rule":1}\n')
        name = str(PureWindowsPath(self.meta['execution_stage']) / 'input/rules.json')
        for field in ('runtime_test_data_sha256_before', 'runtime_test_data_sha256_after'):
            self.meta[field][name] = E.digest((self.root / 'input/rules.json').read_bytes())
        self.refresh_pins()
        self.install()
        self.migrate_synthetic_envelope()
        self.write('input/rules.json', b'{"synthetic_rule":2}\n')
        self.assertTrue(E.validate_current(self.root, self.spec))

    def test_ordinary_H_legacy_input_zip_hash_field_remains_supported(self):
        self.prepare_synthetic_envelope()
        fact = self.cache['executions'][self.key]['facts']['runs'][0]
        fact['archive_sha256'] = fact.pop('frozen_inputs_sha256')
        self.install()
        self.migrate_synthetic_envelope()
        self.assertEqual(E.validate_current(self.root, self.spec), [])

    def phase_two_input_map(self):
        self.prepare_synthetic_envelope()
        proof = self.install()
        self.migrate_synthetic_envelope()
        current = {path: E.digest((self.root / path).read_bytes())
                   for path in [*proof['native']['input_hashes'], *proof['native']['native_envelope_hashes'], *E.proof_input_paths(self.root)]}
        return proof, current

    def test_caller_phase_two_exact_three_controls_and_proof_additions(self):
        proof, current = self.phase_two_input_map()
        result = E.verify_phase_two_inputs(proof['native'], current, E.proof_input_paths(self.root))
        self.assertEqual(set(result['changed_envelope_paths']), E.NATIVE_ENVELOPE)

    def test_caller_phase_two_new_runtime_input_is_rejected(self):
        proof, current = self.phase_two_input_map()
        current['engine/new_runtime.py'] = 'a' * 64
        with self.assertRaises(ValueError):
            E.verify_phase_two_inputs(proof['native'], current, E.proof_input_paths(self.root))

    def test_caller_phase_two_dropped_native_input_is_rejected(self):
        proof, current = self.phase_two_input_map()
        del current['tools/test_toy.py']
        with self.assertRaises(ValueError):
            E.verify_phase_two_inputs(proof['native'], current, E.proof_input_paths(self.root))

if __name__ == '__main__':
    unittest.main()
