"""Actions-only additive control preparation; never run tests or rewrite fixtures."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import traceback

PLAN = '.ci/reviewed-runtime-plan.json'
FULL = [f'.ci/suites/final_revisions_{n:02d}.json' for n in range(1, 19)]
WRITABLE = set(FULL) | {'.ci/suites/changed_revisions.json', '.ci/source-snapshot.json'}
SOURCE_INPUTS = {
    '.ci/remote-source-inputs/chronicler.json',
    '.ci/remote-source-inputs/berries-gmax.json',
    '.ci/remote-source-inputs/blessings.json',
    '.ci/remote-source-inputs/freefloat.json',
    '.ci/remote-source-inputs/self-cost-bide.json',
}
BOOTSTRAP = {PLAN, '.github/workflows/validate.yml',

             'tools/ci_h_checker.py',
             'tools/ci_remote_h.py', 'tools/ci_prepare_reviewed_controls.py'} | SOURCE_INPUTS


def require(condition):
    if not condition:
        raise ValueError('Reviewed control preparation guard rejected the input')


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError('Git operation failed; nothing is accepted as test evidence')
    return result.stdout


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(body):
    return hashlib.sha256(body).hexdigest()


def methods(path, body):
    if not Path(path).name.startswith('test_'):
        return set()
    module = path[:-3].replace('/', '.')
    return {module+'.'+cls.name+'.'+method.name
            for cls in ast.parse(body).body if isinstance(cls, ast.ClassDef)
            for method in cls.body if isinstance(method, ast.FunctionDef)
            and method.name.startswith('test_')}


def packet_ids(packet):
    result = [uid for row in packet['completed'].values() for uid in row['tests']]
    require(len(result) == len(set(result)))
    if 'required_unique_count' in packet:
        require(len(result) == packet['required_unique_count'])
    return result


assert methods('tools/test_control_selection.py', b'class Checks:\n def test_present(self): pass\n def helper(self): pass\n') == {'tools.test_control_selection.Checks.test_present'}
assert not all(part.isidentifier() for part in 'tools..outside'.split('.'))


def selected_ids(root, plan):
    paths = plan['selection_input_paths']
    require(len(paths) == len(SOURCE_INPUTS) and set(paths) == SOURCE_INPUTS)
    folder = root/'.ci/remote-source-inputs'
    rows = []
    rows.append(read(folder/'chronicler.json')['required_test_ids'])
    packets = read(folder/'berries-gmax.json')['packets']
    require(isinstance(packets, list))
    rows.extend(packet['selected_test_ids'] for packet in packets)
    rows.append(read(folder/'blessings.json')['selected_test_ids'])
    completed = read(folder/'freefloat.json')['completed']
    require(isinstance(completed, (dict, list)))
    rows.extend(row['tests'] for row in (completed.values() if isinstance(completed, dict) else completed))
    last = read(folder/'self-cost-bide.json')
    rows.extend((last['affected_test_ids_from_156'], last['affected_test_ids_from_168']))
    rows.append(plan.get('extra_selected_method_ids', []))
    require(all(isinstance(row, list) and all(isinstance(uid, str) and
            re.fullmatch(r'(?:tools|tests)\.[A-Za-z0-9_.]+\.test_[A-Za-z0-9_]+', uid)
            for uid in row) for row in rows))
    # All other metadata, including local provenance paths, is inert and never followed.
    return sorted({uid for row in rows for uid in row})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--expected-parent', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    require(os.environ.get('GITHUB_ACTIONS') == 'true')
    require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch')
    require(os.environ.get('GITHUB_REPOSITORY') == 'andrew0416/trpg-rulebook-structuring')
    branch = os.environ['GITHUB_REF_NAME']
    require(branch.startswith('codex/') and re.fullmatch(r'[A-Za-z0-9_./-]+', branch))
    parent = args.expected_parent
    require(re.fullmatch(r'[0-9a-f]{40}', parent) is not None)
    require(git(root, 'rev-parse', 'HEAD').decode().strip() == parent == os.environ['GITHUB_SHA'])
    require(not git(root, 'status', '--porcelain').strip())
    remote = git(root, 'ls-remote', '--exit-code', 'origin', 'refs/heads/'+branch).decode().split()
    require(remote == [parent, 'refs/heads/'+branch])
    plan_body = (root/PLAN).read_bytes()
    require(git(root, 'show', parent+':'+PLAN) == plan_body)
    plan = json.loads(plan_body)
    require(plan['schema_version'] == 1 and plan['status'] == 'ROOT_REVIEWED_SOURCE_SELECTION_NOT_PASS')
    require(plan['branch'] == branch and plan['completion_credit'] == 0)
    base = plan['reviewed_base_commit']
    require(re.fullmatch(r'[0-9a-f]{40}', base) is not None)
    git(root, 'merge-base', '--is-ancestor', base, parent)
    private = {row['path'] for row in read(root/'.ci/fixtures-manifest.json')['files']}
    private_folded={path.casefold() for path in private}
    for path in ('.ci/fixtures.zip.enc', '.ci/fixtures-manifest.json'):
        require(git(root, 'show', base+':'+path) == (root/path).read_bytes())
    cipher_sha = digest((root/'.ci/fixtures.zip.enc').read_bytes())
    manifest_sha = digest((root/'.ci/fixtures-manifest.json').read_bytes())
    reviewed = plan['reviewed_python_paths']
    require(reviewed and len(reviewed) == len(set(reviewed)))
    for path in reviewed:
        p = PurePosixPath(path)
        require(not p.is_absolute() and '..' not in p.parts and p.as_posix() == path)
        require(path.endswith('.py') and path.startswith(('engine/', 'tools/', 'tests/')))
        require(not path.startswith('tools/ci_') and path not in private)
    changes = [line.split('\t') for line in git(root, 'diff', '--name-status', '--no-renames', base, parent).decode().splitlines()]
    require(all(len(row) == 2 and row[0] in ('A', 'M') for row in changes))
    changed = {row[1] for row in changes}
    require(changed <= set(reviewed) | BOOTSTRAP and changed - BOOTSTRAP == set(reviewed))
    additions = set()
    for status, path in changes:
        if path not in reviewed:
            continue
        new = methods(path, (root/path).read_bytes())
        old = methods(path, git(root, 'show', base+':'+path)) if status == 'M' else set()
        require(old <= new)
        additions.update(new-old)
    if 'added_method_ids' in plan:
        require(plan['added_method_ids'] == sorted(additions))
    packets = {path:read(root/path) for path in FULL}
    owners, original = {}, []
    for path, packet in packets.items():
        original.extend(packet_ids(packet))
        for cls, row in packet['completed'].items():
            require(cls not in owners and all(uid.rsplit('.', 1)[0] == cls for uid in row['tests']))
            owners[cls] = path
    require(len(original) == len(set(original)) and not additions & set(original))
    typed = set(packet_ids(read(root/'.ci/suites/frequency_equivalence.json')))
    metadata = set(packet_ids(read(root/'.ci/suites/metadata_revisions.json')))
    selected = selected_ids(root, plan)
    source_additions=set(additions)
    existing_additions=set(selected)-set(original)-typed-metadata-additions
    if existing_additions:
        require(plan.get('include_reviewed_existing_methods') is True)
        for uid in sorted(existing_additions):
            module=uid.rsplit('.',2)[0]
            require(all(part.isidentifier() for part in module.split('.')))
            path=module.replace('.','/')+'.py'
            require(path.casefold() not in private_folded and uid in methods(path,git(root,'show',parent+':'+path)))
        additions.update(existing_additions)
    require(not {uid.rsplit('.',1)[0] for uid in additions} & {uid.rsplit('.',1)[0] for uid in typed|metadata})
    new_classes = {uid.rsplit('.', 1)[0] for uid in additions} - set(owners)
    require(plan['new_class_shard'] in FULL)
    for uid in sorted(additions):
        cls = uid.rsplit('.', 1)[0]
        path = owners[cls] if cls in owners else plan['new_class_shard']
        packets[path]['completed'].setdefault(cls, {'tests':[]})['tests'].append(uid)
    resulting = [uid for packet in packets.values() for row in packet['completed'].values() for uid in row['tests']]
    require(len(resulting) == len(set(resulting)) and set(resulting) == set(original) | additions)
    for cls, owner in owners.items():
        require(cls in packets[owner]['completed'] and sum(cls in p['completed'] for p in packets.values()) == 1)
    require(len(typed) == 1029 and len(metadata) == 65 and not set(resulting) & (typed | metadata) and not typed & metadata)
    full = set(resulting) | typed | metadata
    require(selected and selected == sorted(set(selected)) and set(selected) <= full and not set(selected) & metadata)
    require(additions <= set(selected))
    groups = {}
    for uid in selected:
        groups.setdefault(uid.rsplit('.', 1)[0], {'tests':[]})['tests'].append(uid)
    replacement = {'.ci/suites/changed_revisions.json':dict(schema_version=1, id='changed_revisions',
                    purpose='Root-reviewed bounded ordinary scope; no full-run or clause credit',
                    completion_credit=0, required_unique_count=len(selected), completed=groups)}
    for path, packet in packets.items():
        packet['required_unique_count'] = sum(len(row['tests']) for row in packet['completed'].values())
        if packet != read(root/path):
            replacement[path] = packet
    snapshot = read(root/'.ci/source-snapshot.json')
    snapshot.pop('active_repair_candidate_sha256', None)
    snapshot.update(active_repair='remote-reviewed-runtime', active_repair_phase='runtime_corrections',
        active_repair_groups=['changed_revisions'], active_repair_required_tests=len(selected),
        active_repair_frequency_methods=0, active_repair_procedural_runners=0,
        phase2_metadata_methods_mandatory=0, phase2_additional_procedural_runners=0,
        full_method_obligations=len(full), selected_method_obligations=len(selected),
        full_method_scope_executed=False, activation_current_evidence_current=False,
        completion_credit=0, active_repair_source_commit=parent,
        active_repair_source_plan_sha256=digest(plan_body),
        remote_control_preparation=dict(status='PREPARED_NOT_EXECUTED',
            added_method_count=len(additions), added_source_method_count=len(source_additions),
            added_existing_method_count=len(existing_additions), existing_class_owners_preserved=True,
            fixture_cipher_sha256=cipher_sha, fixture_manifest_sha256=manifest_sha))
    replacement['.ci/source-snapshot.json'] = snapshot
    require(set(replacement) <= WRITABLE)
    for path, data in replacement.items():
        (root/path).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    actual = set(git(root, 'diff', '--name-only').decode().splitlines())
    require(actual and actual <= set(replacement) and actual <= WRITABLE)
    require(not git(root, 'ls-files', '--others', '--exclude-standard').strip())
    require(digest((root/'.ci/fixtures.zip.enc').read_bytes()) == cipher_sha)
    require(digest((root/'.ci/fixtures-manifest.json').read_bytes()) == manifest_sha)
    git(root, 'add', '--', *sorted(actual))
    require(set(git(root, 'diff', '--cached', '--name-only').decode().splitlines()) == actual)
    for path in actual:
        require(git(root, 'show', ':'+path) == (root/path).read_bytes())
    require(git(root, 'ls-remote', '--exit-code', 'origin', 'refs/heads/'+branch).decode().split() == [parent, 'refs/heads/'+branch])
    git(root, '-c', 'user.name=github-actions[bot]', '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
        'commit', '-m', 'Prepare exact reviewed runtime validation controls; no test credit')
    child = git(root, 'rev-parse', 'HEAD').decode().strip()
    require(git(root, 'rev-parse', 'HEAD^').decode().strip() == parent)
    require(set(git(root, 'diff', '--name-only', parent, child).decode().splitlines()) == actual)
    git(root, 'push', 'origin', 'HEAD:refs/heads/'+branch)
    summary = dict(status='CONTROLS_PREPARED_NO_TESTS', parent=parent, commit=child,
        branch=branch, changed_control_paths=sorted(actual), selected_methods=len(selected),
        full_method_obligations=len(full), additive_methods=len(additions),
        added_source_methods=len(source_additions), added_existing_methods=len(existing_additions),
        fixture_cipher_sha256=cipher_sha, fixture_manifest_sha256=manifest_sha,
        native_runs=0, completion_credit=0)
    print(json.dumps(summary))
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
        stream.write('prepared_commit='+child+'\n')
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
        stream.write('Prepared controls at `'+child+'`. No tests executed or acceptance awarded.\n')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        lines=[frame.lineno for frame in traceback.extract_tb(exc.__traceback__) if frame.filename==__file__]
        assert all(type(line) is int and line>0 for line in lines)
        print(json.dumps(dict(status='CONTROL_PREPARATION_REJECTED', public_helper_lines=lines,
            exception_type=type(exc).__name__, native_runs=0, completion_credit=0)))
        raise SystemExit(1)


