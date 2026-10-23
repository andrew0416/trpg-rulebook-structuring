"""Observable transitions, evidence boundaries and process-safe hook counting."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import architecture_review as REVIEW


def checkpoint(root, count=0):
    path = root / REVIEW.CHECKPOINT
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        'unrelated_progress': {'implemented': 627, 'denominator': 2352},
        'architecture_review': {
            'scope_thread_id': REVIEW.THREAD_ID,
            'cadence': {'interval': 5, 'turns_since_last_review': count, 'phase': 'counter'},
            'last_review': {'kind': 'prior bounded review', 'evidence': 'preserve'},
        },
    }
    path.write_text(json.dumps(document), encoding='utf-8')
    return path


class ReviewControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ptk-review-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = checkpoint(self.root)
        self.source = self.root / 'runtime.py'
        self.source.write_text('original actual owner\n', encoding='utf-8')
        self.reference = self.root / 'model.md'
        self.reference.write_text('reference object ownership\n', encoding='utf-8')
        self.log = self.root / 'checks.log'
        self.log.write_text(
            'test_fix (module.Case.test_fix) ... ok\n\nRan 1 test in 0.001s\n\nOK\n',
            encoding='utf-8',
        )

    def proof(self, path):
        return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def event(self, turn, event='PreToolUse', **extra):
        return REVIEW.hook_status(dict(
            session_id=REVIEW.THREAD_ID, hook_event_name=event, turn_id=turn, **extra,
        ), self.root)

    def state(self):
        return REVIEW.ReviewStore(self.root).transact(REVIEW.snapshot)

    def due(self):
        for i in range(5):
            self.event(f'turn-{i}')
        self.assertEqual(self.state()['phase'], 'discovery')

    def report(self, findings=True):
        return {
            'reference_files': [self.proof(self.reference)],
            'scope': [self.proof(self.source)],
            'summary': 'Compare actual state ownership with the reference object model.',
            'findings': [dict(self.proof(self.source), id='owner',
                              impact='Two independent state owners diverge.',
                              correction='Keep one authoritative owner.')] if findings else [],
        }

    def discover(self, findings=True):
        return REVIEW.ReviewStore(self.root).transact(
            lambda review: REVIEW.discover(review, self.report(findings), self.root))

    def correction(self):
        return {'corrections': [{
            'id': 'owner', 'summary': 'Use the existing actual owner.',
            'changed_files': [self.proof(self.source)],
            'verification': [dict(self.proof(self.log), tests=['module.Case.test_fix'])],
        }]}

    def correct(self, report=None):
        value = self.correction() if report is None else report
        return REVIEW.ReviewStore(self.root).transact(
            lambda review: REVIEW.correct(review, value, self.root))

    def complete(self):
        return REVIEW.ReviewStore(self.root).transact(
            lambda review: REVIEW.complete(review, 'Actual correction and direct checks complete.', self.root))

    def rejected_unchanged(self, operation):
        before = self.path.read_bytes()
        with self.assertRaises((ValueError, KeyError)):
            operation()
        self.assertEqual(self.path.read_bytes(), before)

    def test_pause_freezes_all_phases_and_keeps_review_evidence(self):
        for phase in REVIEW.PHASES:
            with self.subTest(phase=phase):
                document = json.loads(self.path.read_text(encoding='utf-8'))
                review = document['architecture_review']
                review['cadence'].update(phase=phase, turns_since_last_review=2 if phase == 'counter' else 5)
                review['controller'] = {'version': 1, 'seen_turn_ids': ['already-counted'], 'cycle': 8}
                review['review_history'] = [{'cycle': 7, 'evidence': 'keep prior proof'}]
                review['active_cycle'] = {'cycle': 8, 'findings': [{'id': 'pending-owner', 'status': 'open'}]}
                self.path.write_text(json.dumps(document), encoding='utf-8')
                self.state()
                before = json.loads(self.path.read_text(encoding='utf-8'))
                paused = REVIEW.ReviewStore(self.root).transact(lambda value: REVIEW.set_paused(value, True, 'User paused cadence.'))
                self.assertTrue(paused['paused'])
                frozen = self.path.read_bytes()
                for event in ('SessionStart', 'UserPromptSubmit', 'PreToolUse'):
                    state = self.event('paused-' + event, event)
                    self.assertTrue(state['paused'])
                    self.assertEqual(state['phase'], phase)
                    self.assertEqual(state['counter'], 2 if phase == 'counter' else 5)
                    self.assertEqual(self.path.read_bytes(), frozen)
                for operation in (self.discover, self.correct, self.complete):
                    self.rejected_unchanged(operation)
                after = json.loads(frozen)
                old, new = before['architecture_review'], after['architecture_review']
                for key in ('cadence', 'review_history', 'active_cycle', 'last_review'):
                    self.assertEqual(old[key], new[key])
                self.assertEqual({k:v for k,v in new['controller'].items() if k != 'suspension'}, old['controller'])
                self.assertEqual(before['unrelated_progress'], after['unrelated_progress'])

    def test_pause_resume_cli_is_idempotent_and_continues_saved_counter(self):
        self.event('first')
        self.event('second')
        def command(name):
            result = subprocess.run([sys.executable, '-B', str(Path(REVIEW.__file__)),
                '--project-root', str(self.root), name, '--reason', 'Explicit user request.'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertEqual(command('pause')['counter'], 2)
        paused = self.path.read_bytes()
        command('pause')
        self.assertEqual(self.path.read_bytes(), paused)
        self.event('not-counted-while-paused')
        self.assertEqual(self.path.read_bytes(), paused)
        state = command('resume')
        self.assertFalse(state['paused'])
        self.assertEqual(state['counter'], 2)
        resumed = self.path.read_bytes()
        command('resume')
        self.assertEqual(self.path.read_bytes(), resumed)
        self.assertEqual(self.event('second')['counter'], 2)
        self.assertEqual(self.event('third')['counter'], 3)

    def test_blank_pause_reason_cannot_change_state(self):
        self.state()
        self.rejected_unchanged(lambda: REVIEW.ReviewStore(self.root).transact(
            lambda review: REVIEW.set_paused(review, True, ' ')))

    def test_five_distinct_turns_and_all_phase_boundaries(self):
        for i in range(5):
            for event in ('UserPromptSubmit', 'PreToolUse', 'PreToolUse'):
                state = self.event(f'turn-{i}', event)
                self.assertEqual(state['counter'], i + 1)
        self.assertEqual(state['phase'], 'discovery')
        self.assertEqual(self.event('correction-turn')['counter'], 5)
        self.assertEqual(self.state()['phase'], 'discovery')
        self.discover()
        self.assertEqual(self.event('another-correction-turn')['phase'], 'correction')
        self.assertEqual(self.state()['counter'], 5)
        self.source.write_text('single actual owner\n', encoding='utf-8')
        self.assertEqual(self.correct()['phase'], 'complete')
        self.assertEqual(self.state()['counter'], 5)
        self.assertEqual(self.complete()['phase'], 'counter')
        self.assertEqual(self.state()['counter'], 0)
        self.assertEqual(self.event('another-correction-turn')['counter'], 0)
        self.assertEqual(self.event('new-cycle-turn')['counter'], 1)

    def test_restart_and_replayed_older_turn_do_not_double_count(self):
        self.event('first')
        self.event('second')
        self.assertEqual(self.event('first')['counter'], 2)
        self.assertEqual(self.event('second')['counter'], 2)

    def test_session_start_and_missing_turn_id_never_guess_a_new_turn(self):
        self.assertEqual(self.event('session', 'SessionStart')['counter'], 0)
        result = self.event(None)
        self.assertEqual(result['counter'], 0)
        self.assertTrue(result['turn_id_missing'])
        self.assertIn('세지 않았다', REVIEW.context(result))

    def test_other_chat_subagent_and_unsupported_event_are_silent_without_files(self):
        missing = self.root / 'does-not-exist'
        for payload in (
            {'session_id': 'other', 'hook_event_name': 'PreToolUse'},
            {'session_id': REVIEW.THREAD_ID, 'agent_id': 'child', 'hook_event_name': 'PreToolUse'},
            {'session_id': REVIEW.THREAD_ID, 'hook_event_name': 'Stop'},
        ):
            self.assertIsNone(REVIEW.hook_status(payload, missing))
        self.assertFalse(missing.exists())

    def test_unresolved_or_deferred_work_cannot_declare_completion(self):
        self.due()
        self.discover()
        self.rejected_unchanged(self.complete)
        self.assertEqual(self.state()['pending'], ['owner'])

    def test_cannot_skip_discovery_or_correction_with_completion_text(self):
        self.state()
        self.rejected_unchanged(self.complete)
        self.rejected_unchanged(self.correct)
        self.rejected_unchanged(self.discover)

    def test_unchanged_code_failed_log_and_wrong_named_test_are_rejected(self):
        self.due()
        self.discover()
        self.rejected_unchanged(self.correct)
        self.source.write_text('one owner\n', encoding='utf-8')
        self.log.write_text('Ran 1 test in 0.001s\n\nFAILED (failures=1)\n', encoding='utf-8')
        self.rejected_unchanged(self.correct)
        self.log.write_text('test_other (module.Case.test_other) ... ok\n\nRan 1 test in 0.001s\n\nOK\n', encoding='utf-8')
        self.rejected_unchanged(self.correct)

    def test_verified_files_changing_before_declaration_refuse_reset(self):
        self.due()
        self.discover()
        self.source.write_text('correct owner\n', encoding='utf-8')
        self.correct()
        self.source.write_text('changed after verification\n', encoding='utf-8')
        self.rejected_unchanged(self.complete)
        self.assertEqual(self.state()['phase'], 'complete')
        self.assertEqual(self.state()['counter'], 5)

    def test_no_findings_still_needs_explicit_declaration(self):
        self.due()
        self.assertEqual(self.discover(False)['phase'], 'complete')
        self.assertEqual(self.event('still-same-cycle')['counter'], 5)
        self.assertEqual(self.complete()['counter'], 0)
        saved = json.loads(self.path.read_text(encoding='utf-8'))
        review = saved['architecture_review']
        pointer = review['last_completed_cycle']
        completed = review[pointer['record']][pointer['index']]
        self.assertEqual(completed['completed_phase'], 'complete')
        self.assertEqual(completed['cycle'], pointer['cycle'])
        self.assertEqual(review['review_history'][0]['kind'], 'prior bounded review')
        self.assertEqual(saved['unrelated_progress'], {'implemented': 627, 'denominator': 2352})

    def test_no_findings_review_becomes_stale_if_reviewed_code_changes(self):
        self.due()
        self.discover(False)
        self.source.write_text('not reviewed\n', encoding='utf-8')
        self.rejected_unchanged(self.complete)

    def test_source_hash_and_project_path_checks_fail_atomically(self):
        self.due()
        bad = self.report()
        bad['reference_files'][0]['sha256'] = '0' * 64
        self.rejected_unchanged(lambda: REVIEW.ReviewStore(self.root).transact(
            lambda review: REVIEW.discover(review, bad, self.root)))
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / 'external.py'
            path.write_text('external', encoding='utf-8')
            bad = self.report()
            bad['scope'] = [self.proof(path)]
            self.rejected_unchanged(lambda: REVIEW.ReviewStore(self.root).transact(
                lambda review: REVIEW.discover(review, bad, self.root)))

    def test_failed_batch_correction_rolls_back_earlier_items(self):
        self.due()
        self.discover()
        self.source.write_text('single owner\n', encoding='utf-8')
        report = self.correction()
        report['corrections'].append(dict(report['corrections'][0], id='missing'))
        self.rejected_unchanged(lambda: self.correct(report))
        self.assertEqual(self.state()['pending'], ['owner'])

    def test_concurrent_hook_processes_count_same_turn_once(self):
        script = (
            'import json,sys;from pathlib import Path;from tools import architecture_review as r;'
            'print(json.dumps(r.hook_status(json.loads(sys.argv[1]),Path(sys.argv[2]))))'
        )
        payload = json.dumps(dict(session_id=REVIEW.THREAD_ID,
                                  hook_event_name='PreToolUse', turn_id='concurrent'))
        processes = [subprocess.Popen(
            [sys.executable, '-B', '-c', script, payload, str(self.root)],
            cwd=REVIEW.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) for _ in range(4)]
        for process in processes:
            output, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(json.loads(output)['counter'], 1)
        self.assertEqual(self.state()['counter'], 1)

    def test_cli_completion_is_a_real_state_transition_not_a_chat_phrase(self):
        self.due()
        self.discover(False)
        command = [sys.executable, '-B', str(Path(REVIEW.__file__)),
                   '--project-root', str(self.root), 'complete', '--reason', '교정 완료']
        result = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['phase'], 'counter')
        self.assertEqual(self.state()['counter'], 0)

    def test_legacy_count_is_migrated_without_reset_or_extra_turn(self):
        document = json.loads(self.path.read_text(encoding='utf-8'))
        cadence = document['architecture_review']['cadence']
        cadence.update(phase='counting', turns_since_last_review=2)
        self.path.write_text(json.dumps(document), encoding='utf-8')
        self.assertEqual(self.state()['counter'], 2)
        self.assertEqual(self.event('first-controller-turn')['counter'], 3)

    def test_stale_correction_can_be_verified_again_without_skipping_the_gate(self):
        self.due()
        self.discover()
        self.source.write_text('first correction\n', encoding='utf-8')
        self.correct()
        self.source.write_text('second correction\n', encoding='utf-8')
        self.rejected_unchanged(self.complete)
        self.assertEqual(self.correct()['phase'], 'complete')
        self.assertEqual(self.complete()['counter'], 0)

    def test_changed_empty_review_can_be_reexamined_before_declaration(self):
        self.due()
        self.discover(False)
        self.source.write_text('changed and reviewed again\n', encoding='utf-8')
        self.rejected_unchanged(self.complete)
        self.assertEqual(self.discover(False)['phase'], 'complete')
        self.assertEqual(self.complete()['counter'], 0)

    def test_completed_correction_evidence_survives_later_cycles_and_restart(self):
        self.due()
        self.discover()
        self.source.write_text('single authoritative history owner\n', encoding='utf-8')
        verification = self.correction()['corrections'][0]['verification']
        self.correct()
        self.complete()
        for i in range(5):
            self.event(f'next-cycle-{i}')
        self.discover(False)
        self.complete()

        # Read the saved checkpoint afresh: earlier completion evidence must
        # survive a process restart and completion of a later review cycle.
        review = json.loads(self.path.read_text(encoding='utf-8'))['architecture_review']
        completed = [item for item in review['review_history']
                     if item.get('cycle') == 1 and item.get('completed_at')]
        self.assertEqual(len(completed), 1, 'The first completed review lost its evidence.')
        finding = completed[0]['findings'][0]
        self.assertEqual(finding['status'], 'verified')
        self.assertEqual(finding['resolution']['verification'], verification)
        self.assertEqual(completed[0]['completed_phase'], 'complete')
        self.assertTrue(completed[0]['completion_declaration'])
        latest = review['last_completed_cycle']
        self.assertEqual(review['last_review'], latest)
        self.assertEqual(latest['cycle'], 2)
        self.assertEqual(review[latest['record']][latest['index']]['cycle'], 2)
        self.assertFalse(any(item.get('cycle') == 1 and not item.get('completed_at')
                             for item in review['review_history']))

    def test_empty_review_recheck_keeps_the_same_cycle_and_prior_observation(self):
        self.due()
        first = self.discover(False)
        old_hash = self.proof(self.source)['sha256']
        self.source.write_text('changed and examined in the same cycle\n', encoding='utf-8')
        self.rejected_unchanged(self.complete)
        rechecked = self.discover(False)
        self.assertEqual(rechecked['cycle'], first['cycle'])
        self.assertEqual(rechecked['counter'], 5)
        self.complete()
        review = json.loads(self.path.read_text(encoding='utf-8'))['architecture_review']
        completed = next(item for item in review['review_history']
                         if item.get('cycle') == first['cycle'] and item.get('completed_at'))
        self.assertEqual(completed['discovery_revisions'][0]['runtime_files'][0]['sha256'], old_hash)
        self.assertEqual(completed['runtime_files'][0]['sha256'], self.proof(self.source)['sha256'])


if __name__ == '__main__':
    unittest.main()

