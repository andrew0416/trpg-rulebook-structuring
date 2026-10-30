"""Actions-only: append the one approved Survivalist policy to existing fixtures."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

BASE = '5cb633a442822bf477b2edd53d494e9c33201617'
BRANCH = 'codex/weather-integration-1030'
POLICY = 'data/survivalist-hb-definitions.json'
INPUT = '.ci/policy1-survivalist-hb.json.enc'
BUNDLE = '.ci/fixtures.zip.enc'
MANIFEST = '.ci/fixtures-manifest.json'
SNAPSHOT = '.ci/source-snapshot.json'
HELPER = 'tools/ci_prepare_survivalist_policy1.py'
WORKFLOW = '.github/workflows/validate.yml'
OUTPUTS = {BUNDLE, MANIFEST, SNAPSHOT}
OLD_COUNT = 1570


def require(value):
    if not value:
        raise ValueError('Fixed policy1 preparation guard rejected the input')


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(result.returncode == 0)
    return result.stdout


def sha(body):
    return hashlib.sha256(body).hexdigest()


def crypto(root, mode, source, destination, key):
    env = dict(os.environ, PTK_FIXTURE_KEY=key)
    result = subprocess.run(
        ['node', str(root/'tools/ci_fixtures.mjs'), mode, str(source), str(destination)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    env.pop('PTK_FIXTURE_KEY', None)
    require(result.returncode == 0 and destination.is_file())


def metadata(info):
    return (info.filename, info.orig_filename, info.CRC, info.file_size,
            info.compress_size, info.header_offset, info.compress_type,
            info.date_time, info.external_attr, info.internal_attr,
            info.create_system, info.create_version, info.extract_version,
            info.flag_bits, info.extra, info.comment)


def main():
    key = os.environ.pop('PTK_FIXTURE_KEY', None)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--expected-parent', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    parent = args.expected_parent
    require(os.environ.get('GITHUB_ACTIONS') == 'true')
    require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch')
    require(os.environ.get('GITHUB_REPOSITORY') == 'andrew0416/trpg-rulebook-structuring')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/'+BRANCH)
    require(re.fullmatch('[0-9a-f]{40}', parent) is not None)
    require(parent == os.environ.get('GITHUB_SHA') ==
            git(root, 'rev-parse', 'HEAD').decode().strip())
    require(not git(root, 'status', '--porcelain').strip())
    require(git(root, 'ls-remote', '--exit-code', 'origin', 'refs/heads/'+BRANCH).decode().split()
            == [parent, 'refs/heads/'+BRANCH])
    git(root, 'merge-base', '--is-ancestor', BASE, parent)
    changes = [line.split('\t') for line in
               git(root, 'diff', '--name-status', '--no-renames', BASE, parent).decode().splitlines()]
    require({tuple(row) for row in changes} ==
            {('A', HELPER), ('M', WORKFLOW), ('A', INPUT)})
    tracked = git(root, 'ls-files', '-z').decode().split('\0')
    tracked = [name for name in tracked if name]
    require(POLICY.casefold() not in {name.casefold() for name in tracked})
    for path in OUTPUTS | {'tools/ci_validate.py', 'tools/ci_fixtures.mjs'}:
        require(git(root, 'show', BASE+':'+path) == (root/path).read_bytes())
    require(isinstance(key, str) and re.fullmatch('[0-9a-fA-F]{64}', key) is not None)
    require(36 < (root/INPUT).stat().st_size <= 65536+36)
    original = {path: (root/path).read_bytes() for path in OUTPUTS}
    manifest = json.loads(original[MANIFEST])
    snapshot = json.loads(original[SNAPSHOT])
    require(set(manifest) == {'version', 'private_policy', 'files'})
    require(len(manifest['files']) == OLD_COUNT)
    require('survivalist_policy1_fixture_preparation' not in snapshot)
    import ci_validate as CI
    old_rows = CI.fixture_rows(manifest, tracked)
    CI.private_policy_rows({'version': 1, 'files': [manifest['private_policy']]},
                           manifest, tracked)
    require(POLICY.casefold() not in {name.casefold() for name in old_rows})
    temporary = Path(os.environ['RUNNER_TEMP']).resolve()
    require(temporary.is_relative_to(Path('D:/trpg-rulebook-structuring/ci-temp').resolve()))
    with tempfile.TemporaryDirectory(prefix='survivalist-policy1-', dir=temporary) as folder:
        temp = Path(folder)
        old_zip, policy_file = temp/'base.zip', temp/'policy.json'
        crypto(root, 'decrypt', root/BUNDLE, old_zip, key)
        crypto(root, 'decrypt', root/INPUT, policy_file, key)
        content = policy_file.read_bytes()
        require(0 < len(content) <= 65536)
        policy = json.loads(content.decode('utf-8'))
        require(isinstance(policy, dict) and policy.get('schema_version') == 1
                and policy.get('edition') == 'csv_hb'
                and policy.get('source_file') == 'input/db/feats.csv'
                and set(policy.get('features', {})) == {'feat/야생-가이드', 'feat/지리-적응'})
        require(policy['features']['feat/야생-가이드'].get('csv_record') == 755
                and policy['features']['feat/지리-적응'].get('csv_record') == 756)
        stage = temp/'verified-members'
        stage.mkdir()
        before = CI.restore_fixtures(stage, old_zip, manifest, tracked)
        require(len(before) == OLD_COUNT)
        new_row = {'path': POLICY, 'sha256': sha(content), 'size': len(content)}
        updated = deepcopy(manifest)
        updated['files'].append(new_row)
        require(updated['files'][:-1] == manifest['files'])
        require(updated['private_policy'] == manifest['private_policy'])
        CI.fixture_rows(updated, tracked)
        CI.private_policy_rows({'version': 1, 'files': [updated['private_policy']]},
                               updated, tracked)
        with zipfile.ZipFile(old_zip) as archive:
            old_metadata = [metadata(info) for info in archive.infolist()]
            old_comment = archive.comment
        added_zip = temp/'with-policy1.zip'
        shutil.copyfile(old_zip, added_zip)
        # Append one member; existing compressed records are not rebuilt.
        with zipfile.ZipFile(added_zip, 'a') as archive:
            archive.writestr(POLICY, content, compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(added_zip) as archive:
            entries = archive.infolist()
            require(len(entries) == OLD_COUNT+1)
            require([metadata(info) for info in entries[:-1]] == old_metadata)
            require(entries[-1].filename == POLICY and archive.comment == old_comment)
        cipher, authenticated = temp/'fixtures.zip.enc', temp/'authenticated.zip'
        crypto(root, 'encrypt', added_zip, cipher, key)
        crypto(root, 'decrypt', cipher, authenticated, key)
        key = None
        require(authenticated.read_bytes() == added_zip.read_bytes())
        after = CI.restore_fixtures(stage, authenticated, updated, tracked)
        require(after == {**before, POLICY: new_row['sha256']})
        require((stage/POLICY).read_bytes() == content)
        require(len(after) == OLD_COUNT+1 and all(after[name] == value for name, value in before.items()))
        old_zip_sha, new_zip_sha = CI.file_hash(old_zip), CI.file_hash(authenticated)
        cipher_body = cipher.read_bytes()
        snapshot['fixture_files'] = OLD_COUNT+1
        snapshot['fixture_zip_sha256'] = new_zip_sha
        snapshot['survivalist_policy1_fixture_preparation'] = {
            'status': 'AUTHENTICATED_APPEND_ONE_PREPARED_NOT_NATIVE_TESTED',
            'source_base': BASE, 'preparation_parent': parent,
            'policy_path': POLICY, 'policy_size': len(content),
            'policy_sha256': new_row['sha256'],
            'input_cipher_sha256': CI.file_hash(root/INPUT),
            'preserved_members': OLD_COUNT, 'added_members': 1, 'result_members': OLD_COUNT+1,
            'prior_snapshot_fixture_files': json.loads(original[SNAPSHOT]).get('fixture_files'),
            'prior_snapshot_fixture_zip_sha256': json.loads(original[SNAPSHOT]).get('fixture_zip_sha256'),
            'actual_prior_zip_sha256': old_zip_sha, 'fixture_zip_sha256': new_zip_sha,
            'fixture_cipher_sha256': sha(cipher_body),
            'private_policy_sidecar_unchanged': True, 'native_runs': 0,
            'completion_credit': 0, 'main_merge': False,
        }
        replacements = {
            BUNDLE: cipher_body,
            MANIFEST: (json.dumps(updated, ensure_ascii=False, indent=2)+'\n').encode(),
            SNAPSHOT: (json.dumps(snapshot, ensure_ascii=False, indent=2)+'\n').encode(),
        }
    require(not git(root, 'status', '--porcelain').strip())
    require(all((root/path).read_bytes() == body for path, body in original.items()))
    for path, body in replacements.items():
        (root/path).write_bytes(body)
    require(set(git(root, 'diff', '--name-only').decode().splitlines()) == OUTPUTS)
    require(not git(root, 'ls-files', '--others', '--exclude-standard').strip())
    git(root, '-c', 'core.autocrlf=false', 'add', '--', *sorted(OUTPUTS))
    require(set(git(root, 'diff', '--cached', '--name-only').decode().splitlines()) == OUTPUTS)
    require(all(git(root, 'show', ':'+path) == body for path, body in replacements.items()))
    require(git(root, 'ls-remote', '--exit-code', 'origin', 'refs/heads/'+BRANCH).decode().split()
            == [parent, 'refs/heads/'+BRANCH])
    git(root, '-c', 'user.name=github-actions[bot]',
        '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
        'commit', '-m', 'Add approved Survivalist policy1 fixture; preserve existing members')
    child = git(root, 'rev-parse', 'HEAD').decode().strip()
    require(git(root, 'rev-parse', 'HEAD^').decode().strip() == parent)
    require(set(git(root, 'diff', '--name-only', parent, child).decode().splitlines()) == OUTPUTS)
    git(root, 'push', 'origin', 'HEAD:refs/heads/'+BRANCH)
    print(json.dumps({'status': 'POLICY1_FIXTURE_PREPARED_NO_NATIVE_TESTS',
                      'parent': parent, 'commit': child, 'preserved_members': OLD_COUNT,
                      'added_members': 1, 'result_members': OLD_COUNT+1,
                      'changed_paths': sorted(OUTPUTS), 'native_runs': 0, 'completion_credit': 0}))
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
        stream.write('prepared_commit='+child+'\n')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('POLICY1_FIXTURE_PREPARATION_REJECTED; no private content emitted')
        raise SystemExit(1)
