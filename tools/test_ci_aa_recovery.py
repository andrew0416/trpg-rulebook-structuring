"""Unexecuted synthetic recovery-route regressions; authorized Actions only.

Load the proposed public tools plus unchanged CI helpers through PYTHONPATH.
This file is a validation draft, not another tracked/public upload proposal.
"""
from contextlib import nullcontext
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import zipfile

import ci_aa_recovery as recovery

BOUND = dict(id=1, run=2, name='synthetic', size=3, head='0'*40,
             digest='1'*64, cipher='2'*64, archive='3'*64)


def record():
    return dict(id=1, name='synthetic', size_in_bytes=3, expired=False,
                workflow_run=dict(id=2, head_sha='0'*40), digest='sha256:'+'1'*64)


def response(value):
    return nullcontext(io.BytesIO(json.dumps(value).encode()))


class RecoveryRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('GITHUB_ACTIONS') != 'true' or Path(os.environ.get('RUNNER_TEMP', '')).drive.upper() != 'D:':
            raise RuntimeError('This unexecuted draft requires separately authorized D-drive Actions validation')

    def retrieve(self, work):
        return recovery.retrieve_artifact(Path('D:/synthetic-checkout'), BOUND, work,
            'synthetic-token', 'synthetic-key', 'synthetic/repository', Path('D:/synthetic-store'))

    def test_live_binding_mismatch_never_uses_approved_fallback(self):
        for changes in ({'digest':'sha256:'+'f'*64}, {'id':99},
                        {'expired':True, 'size_in_bytes':99}):
            value = record()
            value.update(changes)
            opener = Mock(open=Mock(return_value=response(value)))
            with self.subTest(changes=changes), patch.object(recovery.urllib.request, 'build_opener', return_value=opener), \
                    patch.object(recovery, 'load_anchor') as fallback:
                with self.assertRaises(ValueError):
                    self.retrieve(Path('D:/unused'))
                fallback.assert_not_called()

    def test_matching_expiry_reaches_only_the_anchor_gate(self):
        value = record()
        value['expired'] = True
        opener = Mock(open=Mock(return_value=response(value)))
        with patch.object(recovery.urllib.request, 'build_opener', return_value=opener), \
                patch.object(recovery, 'load_anchor', side_effect=RuntimeError('anchor gate reached')) as fallback:
            with self.assertRaisesRegex(RuntimeError, 'anchor gate reached'):
                self.retrieve(Path('D:/unused'))
            fallback.assert_called_once()

    def test_permission_failure_does_not_reach_fallback(self):
        for status in (401, 403):
            error = urllib.error.HTTPError('https://api.github.com/synthetic', status, 'denied', {}, None)
            opener = Mock(open=Mock(side_effect=error))
            with self.subTest(status=status), patch.object(recovery.urllib.request, 'build_opener', return_value=opener), \
                    patch.object(recovery, 'load_anchor') as fallback:
                with self.assertRaises(urllib.error.HTTPError):
                    self.retrieve(Path('D:/unused'))
                fallback.assert_not_called()

    def test_download_size_mismatch_does_not_reach_fallback(self):
        opener = Mock(open=Mock(side_effect=[response(record()), nullcontext(io.BytesIO(b'ab'))]))
        with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as directory, \
                patch.object(recovery.urllib.request, 'build_opener', return_value=opener), \
                patch.object(recovery, 'load_anchor') as fallback:
            with self.assertRaisesRegex(ValueError, 'archive bytes differ'):
                self.retrieve(Path(directory))
            fallback.assert_not_called()
            self.assertEqual((Path(directory)/'artifact-1.zip').read_bytes(), b'ab')

    def test_unknown_approval_fails_before_reading_neighbors(self):
        with patch.object(recovery, 'APPROVED_RECOVERY_ANCHORS', {}), patch.object(recovery, 'safe_file') as read:
            with self.assertRaisesRegex(ValueError, 'explicitly approved'):
                recovery.load_anchor(Path('D:/unused'), Path('D:/unused'), None,
                                     'synthetic/repository', BOUND, Path('D:/unused'))
            read.assert_not_called()

    def test_duplicate_anchor_keys_and_traversal_rejected(self):
        with self.assertRaises(ValueError):
            recovery.unique_object([('kind', 'one'), ('kind', 'two')])
        for path in ('../outside', 'safe/../../outside', 'C:/outside', 'safe\\outside'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                recovery.safe_file(Path('D:/unused'), path)



class RecoveryReplayTests(unittest.TestCase):
    """Transport and retained-reference checks, never native H/report acceptance."""
    KEY = '31' * 32

    @classmethod
    def setUpClass(cls):
        RecoveryRouteTests.setUpClass()
        cls.checkout = Path(recovery.ci.__file__).resolve().parent.parent

    def make_store(self, base, mutate_anchor=None):
        bound = dict(BOUND)
        evidence_id = recovery.history_id(bound)
        store = base / 'retained'
        history = store / evidence_id
        history.mkdir(parents=True)
        work = base / 'work'
        (work / 'records').mkdir(parents=True)
        evidence_root = base / 'evidence-store'
        full = evidence_root / evidence_id / 'full-evidence.zip'
        full.parent.mkdir(parents=True)
        frozen = base / 'frozen.zip'
        with zipfile.ZipFile(frozen, 'x') as archive:
            archive.writestr('stage/synthetic.txt', b'synthetic captured input')
        with zipfile.ZipFile(full, 'x') as archive:
            archive.write(frozen, 'physical/ci-native-inputs.zip')
        cipher = base / 'synthetic-evidence.zip.enc'
        recovery.crypt(self.checkout, 'encrypt', full, cipher, self.KEY)
        outer = history / 'github-artifact.zip'
        with zipfile.ZipFile(outer, 'x') as archive:
            archive.write(cipher, 'native/evidence.zip.enc')
        bound.update(size=outer.stat().st_size, digest=recovery.ci.file_hash(outer),
                     archive=recovery.ci.file_hash(full), cipher=recovery.ci.file_hash(cipher))
        api = dict(id=bound['id'], name=bound['name'], size_in_bytes=bound['size'],
                   expired=False, workflow_run=dict(id=bound['run'], head_sha=bound['head']),
                   digest='sha256:' + bound['digest'])
        meta = dict(execution_stage='D:/synthetic/original-stage',
                    metadata_path='physical/ci-native.json', raw_log='physical/ci-native.log',
                    frozen_inputs='physical/ci-native-inputs.zip')
        objects = recovery.history_objects(bound, 'synthetic/repository', outer, cipher,
            full, frozen, meta, {'evidence.zip.enc':'native/evidence.zip.enc'})
        anchor = dict(schema_version=1, kind='aa_history_acquisition',
            evidence_id=evidence_id, repository='synthetic/repository',
            acquired_at='2026-10-30T00:00:00+00:00',
            api_url=recovery.api_url('synthetic/repository', bound), api=api,
            run=dict(git_sha=bound['head'], ci=dict(GITHUB_REPOSITORY='synthetic/repository',
                GITHUB_RUN_ID=str(bound['run']), GITHUB_RUN_ATTEMPT='1')),
            h_summary=dict(head=bound['head'], run=str(bound['run']), attempt='1'),
            objects=objects)
        if mutate_anchor is not None:
            mutate_anchor(anchor)
        plaintext = base / 'synthetic-acquisition.json'
        plaintext.write_text(json.dumps(anchor), encoding='utf-8')
        sealed = history / 'acquisition.json.enc'
        recovery.crypt(self.checkout, 'encrypt', plaintext, sealed, self.KEY)
        approvals = {evidence_id:dict(ciphertext_sha256=recovery.ci.file_hash(sealed),
                                     approval_reference='synthetic-test-only')}
        # This is a real encrypted transport fixture, not a native evidence fixture.
        return dict(bound=bound, store=store, work=work, outer=outer, full=full,
                    frozen=frozen, cipher=cipher, sealed=sealed, anchor=anchor,
                    approvals=approvals, evidence_root=evidence_root, meta=meta)

    def retrieve(self, fixture, opener):
        with patch.object(recovery.urllib.request, 'build_opener', return_value=opener), \
                patch.object(recovery, 'APPROVED_RECOVERY_ANCHORS', fixture['approvals']):
            return recovery.retrieve_artifact(self.checkout, fixture['bound'], fixture['work'],
                'synthetic-token', self.KEY, 'synthetic/repository', fixture['store'])

    def test_approved_retained_replay_authenticates_cipher_and_original_outer(self):
        with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as directory:
            fixture = self.make_store(Path(directory))
            error = urllib.error.HTTPError('https://api.github.com/synthetic', 410, 'gone', {}, None)
            outer, api, anchor, acquisition = self.retrieve(fixture, Mock(open=Mock(side_effect=error)))
            self.assertEqual(outer, fixture['outer'])
            self.assertEqual(api, fixture['anchor']['api'])
            self.assertEqual(anchor, fixture['anchor'])
            self.assertEqual(acquisition['kind'], 'approved_sealed_anchor')
            self.assertEqual(acquisition['sealed_anchor_sha256'],
                             recovery.ci.file_hash(fixture['sealed']))
            self.assertEqual(recovery.ci.file_hash(outer), fixture['bound']['digest'])
            self.assertEqual(outer.stat().st_size, fixture['bound']['size'])
            self.assertEqual(recovery.APPROVED_RECOVERY_ANCHORS, {})
            # Retrieval stops before native H; synthetic run/H fields are not a PASS.

    def test_authenticated_anchor_requires_four_complete_distinct_object_descriptors(self):
        changes = [
            ('kind', lambda anchor: anchor['objects'][0].update(kind='full_evidence_zip')),
            ('size', lambda anchor: anchor['objects'][0].update(size=-1)),
            ('digest', lambda anchor: anchor['objects'][0].update(sha256='not-a-sha256')),
            ('identity', lambda anchor: anchor['objects'][0].update(id=anchor['objects'][1]['id'])),
        ]
        for field, change in changes:
            with self.subTest(field=field), tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as directory:
                fixture = self.make_store(Path(directory), mutate_anchor=change)
                error = urllib.error.HTTPError('https://api.github.com/synthetic', 410, 'gone', {}, None)
                with self.assertRaisesRegex(ValueError, 'object kinds or IDs differ|unknown object sizes or digests'):
                    self.retrieve(fixture, Mock(open=Mock(side_effect=error)))
                self.assertEqual(recovery.ci.file_hash(fixture['outer']), fixture['bound']['digest'])

    def test_even_a_pinned_corrupt_cipher_cannot_authenticate_or_write_plaintext(self):
        with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as directory:
            fixture = self.make_store(Path(directory))
            body = bytearray(fixture['sealed'].read_bytes())
            body[-1] ^= 1
            fixture['sealed'].write_bytes(body)
            evidence_id = recovery.history_id(fixture['bound'])
            fixture['approvals'][evidence_id]['ciphertext_sha256'] = recovery.ci.file_hash(fixture['sealed'])
            error = urllib.error.HTTPError('https://api.github.com/synthetic', 410, 'gone', {}, None)
            with self.assertRaisesRegex(ValueError, 'cryptographic operation failed'):
                self.retrieve(fixture, Mock(open=Mock(side_effect=error)))
            self.assertFalse((fixture['work'] / 'records' / (evidence_id + '-acquisition.json')).exists())
            self.assertEqual(recovery.ci.file_hash(fixture['outer']), fixture['bound']['digest'])

    def test_interrupted_download_keeps_partial_and_uses_authenticated_retained_copy(self):
        class InterruptedBody:
            def __init__(self):
                self.first = True
            def read(self, size=-1):
                if self.first:
                    self.first = False
                    return b'partial-download'
                raise TimeoutError('synthetic interrupted response')

        with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as directory:
            fixture = self.make_store(Path(directory))
            opener = Mock(open=Mock(side_effect=[
                response(fixture['anchor']['api']), nullcontext(InterruptedBody())]))
            outer, _, _, acquisition = self.retrieve(fixture, opener)
            partial = fixture['work'] / ('artifact-' + str(fixture['bound']['id']) + '.zip')
            self.assertEqual(partial.read_bytes(), b'partial-download')
            self.assertNotEqual(partial, outer)
            self.assertEqual(recovery.ci.file_hash(outer), fixture['bound']['digest'])
            self.assertEqual(acquisition['kind'], 'approved_sealed_anchor')
            self.assertEqual(acquisition['live_unavailability'], 'TimeoutError')

    def test_object_kinds_and_materialized_reference_bind_actual_distinct_objects(self):
        with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as directory:
            fixture = self.make_store(Path(directory))
            objects = fixture['anchor']['objects']
            self.assertEqual([row['kind'] for row in objects],
                             ['github_artifact_zip', 'encrypted_evidence',
                              'full_evidence_zip', 'frozen_inputs_zip'])
            for row, key in zip(objects, ('outer', 'cipher', 'full', 'frozen')):
                with self.subTest(kind=row['kind']):
                    self.assertEqual(row['size'], fixture[key].stat().st_size)
                    self.assertEqual(row['sha256'], hashlib.sha256(fixture[key].read_bytes()).hexdigest())
            self.assertEqual(objects[1]['location']['member'], 'native/evidence.zip.enc')
            self.assertEqual(objects[3]['location']['member'], 'physical/ci-native-inputs.zip')
            self.assertEqual({row['id'] for row in objects},
                             {recovery.history_id(fixture['bound']) + '/' + kind for kind in
                              ('github_artifact_zip', 'encrypted_evidence',
                               'full_evidence_zip', 'frozen_inputs_zip')})
            descriptor = recovery.gate_reference({'archive':fixture['full']}, fixture['bound'],
                                                  fixture['evidence_root'])
            self.assertEqual(descriptor['kind'], 'full_evidence_zip')
            self.assertEqual(descriptor['sha256'], fixture['bound']['archive'])
            self.assertNotEqual(descriptor['sha256'], objects[3]['sha256'])
            with self.assertRaisesRegex(ValueError, 'Materialized full-archive reference differs'):
                recovery.gate_reference({'archive':fixture['frozen']}, fixture['bound'],
                                        fixture['evidence_root'])
            fixture['full'].write_bytes(b'changed full archive')
            with self.assertRaisesRegex(ValueError, 'Materialized full-archive reference differs'):
                recovery.gate_reference({'archive':fixture['full']}, fixture['bound'],
                                        fixture['evidence_root'])

    def test_existing_gate_resolves_reference_from_materialized_cwd_before_acceptance(self):
        with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as directory:
            base = Path(directory)
            fixture = self.make_store(base)
            descriptor = recovery.gate_reference({'archive':fixture['full']}, fixture['bound'],
                                                  fixture['evidence_root'])
            stage, root = base / 'stage', base / 'repo'
            (stage / 'data/verification').mkdir(parents=True)
            (root / 'engine').mkdir(parents=True)
            source = root / 'engine/synthetic.py'
            source.write_text('# synthetic source pin only\n', encoding='utf-8')
            proof_path = stage / 'data/verification/proof.json'
            proof_path.write_text(json.dumps(dict(
                runtime_test_source_sha256={'engine/synthetic.py':recovery.ci.file_hash(source)},
                stable_read_only_inputs=False)), encoding='utf-8')
            spec = dict(existing_proof_only=True, staged_artifacts=['data/verification/proof.json'],
                retained_proof=dict(path='data/verification/proof.json',
                    sha256=recovery.ci.file_hash(proof_path),
                    impact_review=dict(basis='synthetic relative-reference boundary',
                                       historical_inputs=[descriptor])))
            candidate = base / 'candidate.json'
            candidate.write_text(json.dumps(spec), encoding='utf-8')
            # Deliberately stop at the next existing guard. No H/reporter PASS is fabricated.
            program = (
                "import json,sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0,sys.argv[1])\n"
                "import reconcile_batch as owner\n"
                "try:\n"
                " owner.verify_retained_proof(json.loads(Path(sys.argv[2]).read_text()),"
                "Path(sys.argv[3]),Path(sys.argv[4]))\n"
                "except Exception as error:\n"
                " if sys.argv[5]=='bound':\n"
                "  assert type(error) is RuntimeError and str(error)=="
                "'retained proof is not existing-evidence-only', repr(error)\n"
                " else:\n"
                "  assert type(error) is FileNotFoundError, repr(error)\n"
                "else:\n"
                " raise AssertionError('Synthetic incomplete proof must never be admitted')\n"
            )
            for cwd, mode in ((fixture['evidence_root'], 'bound'), (base, 'unbound')):
                with self.subTest(cwd=mode):
                    result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', program,
                        str(self.checkout / 'work/reuse-partials'), str(candidate),
                        str(stage), str(root), mode], cwd=cwd, capture_output=True,
                        text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == '__main__':
    unittest.main()
