"""Actions-only ordinary H proof; no tests, ledger updates, or public raw facts."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import traceback
import zipfile

H_SHA256 = '8df797f3faf505643e68ce05148d4ba3af36d47efe72ed08a0ef72aa5bd4ce07'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def crypt(root, mode, source, destination, key):
    env = dict(os.environ, PTK_FIXTURE_KEY=key)
    result = subprocess.run(['node', str(root/'tools/ci_fixtures.mjs'), mode,
                             str(source), str(destination)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    env.pop('PTK_FIXTURE_KEY', None)
    require(result.returncode == 0, 'Fixture cryptographic operation failed')


def stage_path(stage, relative):
    p = PurePosixPath(relative.replace('\\', '/'))
    require(not p.is_absolute() and '..' not in p.parts and ':' not in relative,
            'Invalid stage evidence path')
    target = (stage/Path(*p.parts)).resolve()
    require(target.is_relative_to(stage), 'Evidence leaves execution stage')
    return target


def main():
    key = os.environ.pop('PTK_FIXTURE_KEY', None)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions execution required')
    require(os.environ.get('CI_SUITE') == 'changed_revisions', 'Reviewed ordinary route required')
    identity = {k: os.environ[k] for k in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA')}
    public = root/'output/ci/remote-h'
    public.mkdir(parents=True, exist_ok=True)
    summary = dict(status='H_NOT_ACCEPTED', run=identity['GITHUB_RUN_ID'],
                   attempt=identity['GITHUB_RUN_ATTEMPT'], head=identity['GITHUB_SHA'],
                   suite='changed_revisions', checker_sha256=H_SHA256,
                   ordinary_verified=0, native_runs=0, completion_credit=0)
    proof = dict(identity=identity, status='H_NOT_ACCEPTED', completion_credit=0)
    exit_code = 1
    temp_root = Path(os.environ['RUNNER_TEMP']).resolve()
    require(temp_root.drive.upper() == 'D:', 'D-drive runner temporary root required')
    with tempfile.TemporaryDirectory(prefix='ptk-independent-h-', dir=temp_root) as temp:
        private = Path(temp)
        try:
            require(key is not None, 'Missing fixture key')
            checker_path = root/'tools/ci_h_checker.py'
            require(digest(checker_path) == H_SHA256, 'Unchanged H bytes required')
            matches = []
            for path in (root/'output/ci').glob('*/run.json'):
                data = read(path)
                if data.get('suite') == 'changed_revisions' and all(
                        data.get('ci', {}).get(k) == v for k, v in identity.items()):
                    matches.append((path, data))
            require(len(matches) == 1, 'Unique exact-run native evidence required')
            run_path, run = matches[0]
            require(run['git_sha'] == identity['GITHUB_SHA'] and run['exit_code'] == 0
                    and run.get('inputs_unchanged') is True, 'Successful stable native run required')
            cipher = run_path.parent/'evidence.zip.enc'
            require(run['encrypted_evidence']['file'] == cipher.name
                    and digest(cipher) == run['encrypted_evidence']['sha256'],
                    'Original encrypted evidence binding differs')
            archive_path = private/'native-evidence.zip'
            crypt(root, 'decrypt', cipher, archive_path, key)
            archive_sha = digest(archive_path)
            packet = read(root/'.ci/suites/changed_revisions.json')
            required = [uid for row in packet['completed'].values() for uid in row['tests']]
            require(required and len(required) == len(set(required)) == packet['required_unique_count'],
                    'Exact unique public method selection required')
            with zipfile.ZipFile(archive_path) as archive:
                names = archive.namelist()
                require(len(names) == len(set(names)) and 'diagnostic-scope.json' not in names,
                        'Unique complete original archive required')
                meta = json.loads(archive.read('physical/ci-native.json'))
                require(meta.get('execution_kind', 'run') == 'run', 'Ordinary evidence only')
                require(set(meta['test_ids']) == set(required), 'Physical selection differs')
                stage = Path(meta['execution_stage']).resolve()
                require(stage == Path(run['execution_stage']).resolve()
                        and stage.is_relative_to(Path('D:/trpg-rulebook-structuring/ci').resolve()),
                        'Original execution-stage binding differs')
                for relative, member in ((meta['metadata_path'], 'physical/ci-native.json'),
                                         (meta['raw_log'], 'physical/ci-native.log'),
                                         (meta['frozen_inputs'], 'physical/ci-native-inputs.zip')):
                    target = stage_path(stage, relative)
                    body = archive.read(member)
                    if target.exists():
                        require(target.read_bytes() == body, 'Existing physical evidence differs')
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with target.open('xb') as stream:
                            stream.write(body)
            loader = importlib.util.spec_from_file_location('unchanged_independent_H', checker_path)
            checker = importlib.util.module_from_spec(loader)
            loader.loader.exec_module(checker)
            spec = dict(repair_only=True, required_test_ids=sorted(required),
                        logs=[meta['raw_log']], execution_history=[{'metadata':meta['metadata_path']}],
                        game_runs=1, test_executions=meta['tests'])
            generated = None
            if meta.get('ordinary_generated_first_reads') or meta.get('ordinary_extended_generated_first_reads'):
                generated = {meta['metadata_path']:{'path':str(archive_path), 'sha256':archive_sha}}
            facts = checker.verify_acceptance_evidence(stage, spec, stage, generated_archives=generated)
            require(facts['mode'] == 'physical' and facts['latest_valid_pass_count'] == len(required),
                    'Independent H did not accept every required ordinary method')
            proof.update(status='H_PHYSICAL_ACCEPTED', spec=spec, facts=facts,
                         checker_sha256=H_SHA256, run_metadata_sha256=digest(run_path),
                         original_archive_sha256=archive_sha, encrypted_native_sha256=digest(cipher),
                         required_test_ids=sorted(required), source_plan_sha256=digest(root/'.ci/suites/changed_revisions.json'))
            summary.update(status='H_PHYSICAL_ACCEPTED', ordinary_verified=len(required),
                           required_ids_sha256=hashlib.sha256(json.dumps(sorted(required)).encode()).hexdigest(),
                           original_archive_sha256=archive_sha, encrypted_native_sha256=digest(cipher))
            exit_code = 0
        except Exception as exc:
            proof.update(error_type=type(exc).__name__, private_traceback=traceback.format_exc())
            summary.update(status='H_REJECTED', ordinary_verified=0)
        try:
            plaintext = private/'h-proof.json'
            plaintext.write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            sealed = public/'h-proof.json.enc'
            crypt(root, 'encrypt', plaintext, sealed, key)
            summary['encrypted_h_proof_sha256'] = digest(sealed)
        except Exception:
            summary.update(status='H_PROOF_ENCRYPTION_FAILED', ordinary_verified=0)
            exit_code = 1
        finally:
            key = None
        (public/'h-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())

