"""Diagnose one fixed failed Actions run; never execute tests or accept evidence."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = 'andrew0416/trpg-rulebook-structuring'
SOURCE_RUN = 40991471600
SOURCE_ATTEMPT = 1
SOURCE_HEAD = '15e20544ae47ec2aa26814ad7a3f7661120da559'
ARTIFACT_ID = 12949268134
ARTIFACT_NAME = 'diagnostics-changed_revisions-40991471600-1'
ARTIFACT_SHA256 = 'ff850fd3147509cfedd38d06f2fc89af101fa576a0f02d6bf2b540620f83c834'
ARTIFACT_SIZE = 826708
API = 'https://api.github.com/repos/' + REPOSITORY
PACKET = '.ci/suites/changed_revisions.json'
STAGE = 'D:/trpg-rulebook-structuring/ci/40991471600-1-changed_revisions'
STATUSES = {'pass', 'fail', 'error', 'skip', 'expected_failure', 'unexpected_success', 'unverified', 'not_run'}
EXCEPTIONS = {'AssertionError', 'ValueError', 'TypeError', 'KeyError', 'NameError', 'AttributeError',
              'RuntimeError', 'IndexError', 'ZeroDivisionError', 'UnboundLocalError', 'ImportError',
              'ModuleNotFoundError', 'FileNotFoundError', 'PermissionError', 'TimeoutError', 'StateCodecError'}


def require(condition):
    if not condition:
        raise ValueError('Fixed diagnostic binding rejected')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def fetch(url, token=None, redirect=False):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == 'https' and not parsed.username and not parsed.password)
    headers = {'User-Agent': 'fixed-existing-run-diagnostic'}
    if token is not None:
        require(parsed.netloc == 'api.github.com' and url.startswith(API + '/actions/'))
        headers.update(Authorization='Bearer ' + token, Accept='application/vnd.github+json')
    else:
        require(parsed.hostname and (parsed.hostname.endswith('.blob.core.windows.net')
                or parsed.hostname.endswith('.actions.githubusercontent.com')))
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=60) as response:
            require(response.status == 200 and not redirect)
            body = response.read(2 * 1024 * 1024 + 1)
            require(len(body) <= 2 * 1024 * 1024)
            return body
    except urllib.error.HTTPError as error:
        require(redirect and error.code == 302)
        return error.headers['Location']


def git(root, *arguments):
    result = subprocess.run(['git', '-C', str(root), *arguments], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    require(result.returncode == 0)
    return result.stdout


def member(archive, name):
    names = archive.namelist()
    require(len(names) == len(set(names)) and names.count(name) == 1)
    info = archive.getinfo(name)
    require(not info.is_dir() and info.file_size <= 16 * 1024 * 1024)
    return archive.read(info)



TEST = 'tools.test_book_trickster_full.TricksterFullTests.test_stacked_all_four_save_conditions_and_all_four_volatile_conditions'
FAILED = TEST + " (condition='얼음')"
REST = ('조이기', '잠듦', '혼란', '난동', '억압', '헤롱헤롱')
PHASE = 'environment'


def shape(value):
    return {'type': type(value).__name__,
            'count': len(value) if isinstance(value, (list, dict)) else None}


def predicates(native, report, physical, log, report_name, output_path, source_hashes):
    checks, observed = {}, {}
    def check(code, actual, expected):
        checks[code] = actual == expected
        observed[code] = shape(actual)

    check('run_suite', native.get('suite'), 'changed_revisions')
    check('run_head', native.get('git_sha'), SOURCE_HEAD)
    check('run_ci_head', native.get('ci', {}).get('GITHUB_SHA'), SOURCE_HEAD)
    checks['run_clean'] = native.get('tracked_changes') is False
    checks['run_inputs_unchanged'] = native.get('inputs_unchanged') is True
    check('verifier_exit', native.get('verifier_outcome', {}).get('exit_code'), 1)
    check('report_kind', report.get('kind'), 'run')
    checks['report_unsuccessful'] = report.get('successful') is False
    check('report_tests_run', report.get('tests_run'), 1)
    for field in ('collected', 'requested', 'retry_ids'):
        check('report_' + field, report.get(field), [TEST])
    check('report_stage', report.get('stage'), native.get('execution_stage'))
    for field in ('discovery_errors', 'errors', 'expected_failures', 'unexpected_successes'):
        check('report_' + field, report.get(field), [])
    durations = report.get('test_durations')
    check('report_duration_ids', [row.get('id') if isinstance(row, dict) else None
          for row in durations] if isinstance(durations, list) else None, [TEST])
    failures = report.get('failures')
    checks['report_single_failure'] = isinstance(failures, list) and len(failures) == 1
    observed['report_failures'] = shape(failures)
    failure = failures[0] if checks['report_single_failure'] and isinstance(failures[0], dict) else {}
    check('report_failure_id', failure.get('id'), FAILED)
    trace = failure.get('traceback')
    observed['report_trace'] = shape(trace)
    terminal = trace.strip().splitlines()[-1] if isinstance(trace, str) and trace.strip() else ''
    checks['trace_terminal_2_ne_1'] = terminal == 'AssertionError: 2 != 1'
    checks['trace_group_assertion'] = isinstance(trace, str) and "self.assertEqual(record['group'],1)" in trace
    expected_skips = [{'id': TEST + " (condition='" + condition + "')",
                       'reason': 'blocked by failed preceding actual condition: 얼음'} for condition in REST]
    check('report_skips', report.get('skipped'), expected_skips)
    method = TEST.rsplit('.', 1)[1]
    expected_header = 'FAIL: ' + method + ' (' + TEST + ") (condition='얼음')"
    lines = log.splitlines()
    checks['log_fail_header'] = expected_header in lines
    checks['log_assertion_2_ne_1'] = 'AssertionError: 2 != 1' in lines
    checks['log_one_test_footer'] = re.search(r'(?m)^Ran 1 test in [0-9.]+s\s*$', log) is not None
    checks['log_failure_skip_footer'] = re.search(r'(?m)^FAILED \(failures=1, skipped=6\)\s*$', log) is not None
    checks['physical_unsuccessful'] = physical.get('successful') is False
    for field, expected in (('exit_code', 1), ('test_ids', [TEST]), ('actual_test_ids', [TEST]),
                            ('tests', 1), ('failure_ids', [FAILED]), ('error_ids', [])):
        check('physical_' + field, physical.get(field), expected)
    checks['physical_exception_none'] = physical.get('exception') is None
    observed['physical_exception'] = shape(physical.get('exception'))
    for field in ('stable_hashes', 'complete_pre_input_capture', 'complete_loaded_input_capture'):
        checks['physical_' + field] = physical.get(field) is True
    for field in ('changed_origin_errors', 'input_read_errors'):
        checks['physical_' + field + '_empty'] = not physical.get(field)
        observed['physical_' + field] = shape(physical.get(field))
    report_path = output_path / Path(report_name)
    log_path = report_path.with_suffix('.log')
    check('physical_report_path', physical.get('original_cli_report'), str(report_path))
    check('physical_log_path', physical.get('original_cli_log'), str(log_path))
    pins = physical.get('runtime_test_data_sha256_before')
    observed['physical_before_pins'] = shape(pins)
    observed['physical_after_pins'] = shape(physical.get('runtime_test_data_sha256_after'))
    for relative, label in (('engine/trickster.py', 'runtime'), ('tools/test_book_trickster_full.py', 'oracle')):
        expected_key = str(Path(native['execution_stage']) / relative)
        checks['pin_' + label + '_exact'] = isinstance(pins, dict) and pins.get(expected_key) == source_hashes[relative]
        checks['pin_' + label + '_normalized'] = isinstance(pins, dict) and any(
            isinstance(name, str) and name.replace('\\', '/').casefold() == expected_key.replace('\\', '/').casefold()
            and value == source_hashes[relative] for name, value in pins.items())
    check('physical_pin_maps_equal', physical.get('runtime_test_data_sha256_after'), pins)
    # Auxiliary observations do not replace the original exact path/header checks.
    path_shapes = {}
    for field, expected in (('original_cli_report', report_path), ('original_cli_log', log_path)):
        value = physical.get(field)
        path_shapes[field] = {
            'type': type(value).__name__,
            'normalized_equal': isinstance(value, str) and value.replace('\\', '/').casefold() == str(expected).replace('\\', '/').casefold(),
            'has_backslash': isinstance(value, str) and '\\' in value,
            'has_forward_slash': isinstance(value, str) and '/' in value}
    failed = [code for code, passed in checks.items() if not passed]
    return {
        'checks': checks, 'failed_reason_codes': failed,
        'first_failed_reason_code': failed[0] if failed else None, 'observed_shapes': observed,
        'path_shapes': path_shapes,
        'assertion_category': 'expected_2_ne_1' if checks['trace_terminal_2_ne_1'] else ('missing' if not terminal else 'other'),
        'log_fail_header_count': sum(line.startswith('FAIL: ') for line in lines),
        'log_header_contains_allowlisted_parent': any(line.startswith('FAIL: ') and TEST in line for line in lines),
        'public_counts': {
            'report_tests_run': report.get('tests_run') if type(report.get('tests_run')) is int and 0 <= report['tests_run'] <= 10000 else None,
            'physical_tests': physical.get('tests') if type(physical.get('tests')) is int and 0 <= physical['tests'] <= 10000 else None},
        'test_ids': [TEST] if isinstance(report.get('collected'), list) and TEST in report['collected'] else []}


def inspect_original_cleanliness(root, private, native, physical):
    """Compare retained tracked bytes, then observe a new checkout; never rewrite run_clean."""
    tree = {}
    for entry in git(root, 'ls-tree', '-r', '-z', '--full-tree', SOURCE_HEAD).split(b'\0'):
        if not entry:
            continue
        info, name = entry.split(b'\t', 1)
        mode, kind, oid = info.decode('ascii').split()
        name = name.decode('utf-8')
        path = PurePosixPath(name)
        require(kind == 'blob' and mode in ('100644', '100755')
                and not path.is_absolute() and '..' not in path.parts and path.as_posix() == name)
        require(name not in tree)
        tree[name] = oid
    require(bool(tree))
    pins = physical['runtime_test_data_sha256_before']
    after = physical['runtime_test_data_sha256_after']
    require(isinstance(pins, dict) and isinstance(after, dict))
    expected = {name:pins.get(str(PureWindowsPath(STAGE)/name)) for name in tree}
    missing = [name for name, value in expected.items()
               if not isinstance(value, str) or re.fullmatch('[a-f0-9]{64}', value) is None]
    mismatches, eol_candidates = [], {}
    # One cat-file process avoids one Git process per public tracked source.
    with (private/'blob-read.stderr').open('xb') as errors:
        reader = subprocess.Popen(['git', '-C', str(root), 'cat-file', '--batch'],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
        try:
            for name, oid in tree.items():
                reader.stdin.write((oid+'\n').encode('ascii'))
                reader.stdin.flush()
                header = reader.stdout.readline().decode('ascii').strip().split()
                require(len(header) == 3 and header[0] == oid and header[1] == 'blob')
                size = int(header[2])
                digest, remaining = hashlib.sha256(), size
                small = bytearray() if size <= 4*1024*1024 else None
                while remaining:
                    chunk = reader.stdout.read(min(1024*1024, remaining))
                    require(bool(chunk))
                    digest.update(chunk)
                    if small is not None:
                        small.extend(chunk)
                    remaining -= len(chunk)
                require(reader.stdout.read(1) == b'\n')
                if name not in missing and digest.hexdigest() != expected[name]:
                    mismatches.append(name)
                    if small is not None:
                        raw = bytes(small)
                        eol_candidates[name] = (
                            hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest() == expected[name]
                            or hashlib.sha256(raw.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')).hexdigest() == expected[name])
            reader.stdin.close()
            require(reader.wait(timeout=60) == 0)
        finally:
            if reader.poll() is None:
                reader.kill()
                reader.wait()
            reader.stdout.close()
    fresh = private/'fresh-source-checkout'
    clone = subprocess.run(['git', 'clone', '--shared', '--no-checkout', str(root), str(fresh)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    require(clone.returncode == 0)
    checkout = subprocess.run(['git', '-C', str(fresh), 'checkout', '--detach', SOURCE_HEAD],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    require(checkout.returncode == 0 and git(fresh, 'rev-parse', 'HEAD').decode().strip() == SOURCE_HEAD)
    status = subprocess.run(['git', '-C', str(fresh), 'status', '--porcelain', '--untracked-files=no'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    require(status.returncode == 0)
    dirty = [name.decode('utf-8') for name in
             git(fresh, 'diff', '--name-only', '-z', 'HEAD').split(b'\0') if name]
    require(set(dirty) <= set(tree))
    reproduced = {}
    for name in mismatches:
        target = fresh/name
        require(not target.is_symlink() and target.resolve().is_relative_to(fresh))
        with target.open('rb') as stream:
            reproduced[name] = hashlib.file_digest(stream, 'sha256').hexdigest() == expected[name]
    stderr_categories = []
    for needle, label in ((b'LF will be replaced by CRLF', 'lf_to_crlf_warning'),
                          (b'CRLF will be replaced by LF', 'crlf_to_lf_warning'),
                          (b'warning:', 'git_warning')):
        if needle in status.stderr:
            stderr_categories.append(label)
    if status.stderr and not stderr_categories:
        stderr_categories.append('other_stderr_not_published')
    return dict(
        original_tracked_changes_is_true=native.get('tracked_changes') is True,
        original_status_stdout_stderr_not_recorded=True,
        recorded_scope='Git-tracked subset of original physical pre/post input maps; copy_stage verifies root-to-stage bytes',
        tracked_file_count=len(tree), missing_pin_count=len(missing),
        missing_public_tracked_paths=sorted(missing)[:100],
        blob_mismatch_count=len(mismatches), mismatch_public_tracked_paths=sorted(mismatches)[:100],
        all_recorded_tracked_bytes_equal_source_tree=not missing and not mismatches,
        recorded_pre_post_maps_equal=pins == after,
        newline_only_mismatch_count=sum(eol_candidates.values()),
        all_recorded_mismatches_reproduced_in_fresh_checkout=bool(mismatches) and all(reproduced.values()),
        fresh_reproduced_public_paths=sorted(name for name, matched in reproduced.items() if matched)[:100],
        fresh_diff_tracked_count=len(dirty), fresh_diff_public_paths=sorted(dirty)[:100],
        fresh_porcelain_stdout_nonempty=bool(status.stdout), fresh_status_stderr_nonempty=bool(status.stderr),
        fresh_legacy_merged_boolean=bool(status.stdout+status.stderr),
        fresh_stderr_only_false_dirty_reproduced=not status.stdout and bool(status.stderr),
        fresh_status_stderr_categories=stderr_categories,
        fresh_status_stdout_sha256=hashlib.sha256(status.stdout).hexdigest(),
        fresh_status_stderr_sha256=hashlib.sha256(status.stderr).hexdigest(),
        fresh_git_version_matches_original=git(fresh, '--version').decode().strip() == native.get('git_version'),
        historical_dirty_flag_rewritten=False, historical_cause_certified=False,
        mutation_acceptance='not_decided', native_runs=0, verifier_reruns=0, h_reruns=0)

def inspect_aa_fresh_checkout(root, private):
    """Observe this exact AA head afresh; do not infer historical byte identity."""
    head = 'a5ae917e182e3caf129ad4df6fc78ff9057c6001'
    tree = {}
    for entry in git(root, 'ls-tree', '-r', '-z', '--full-tree', head).split(b'\0'):
        if not entry:
            continue
        info, name = entry.split(b'\t', 1)
        mode, kind, oid = info.decode('ascii').split()
        name = name.decode('utf-8')
        path = PurePosixPath(name)
        require(kind == 'blob' and mode in ('100644', '100755')
                and not path.is_absolute() and '..' not in path.parts and path.as_posix() == name)
        require(name not in tree)
        tree[name] = oid
    require(bool(tree))
    fresh = private/'fresh-aa-source-checkout'
    clone = subprocess.run(['git', 'clone', '--shared', '--no-checkout', str(root), str(fresh)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    require(clone.returncode == 0)
    checkout = subprocess.run(['git', '-C', str(fresh), 'checkout', '--detach', head],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    require(checkout.returncode == 0 and git(fresh, 'rev-parse', 'HEAD').decode().strip() == head)
    status = subprocess.run(['git', '-C', str(fresh), 'status', '--porcelain', '--untracked-files=no'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    require(status.returncode == 0)
    dirty = [name.decode('utf-8') for name in
             git(fresh, 'diff', '--name-only', '-z', 'HEAD').split(b'\0') if name]
    require(set(dirty) <= set(tree))
    compared = []
    for name in dirty:
        target = fresh/name
        require(not target.is_symlink() and target.resolve().is_relative_to(fresh))
        if not target.is_file():
            compared.append(dict(path=name, kind='missing_file'))
            continue
        original = git(root, 'cat-file', 'blob', tree[name])
        actual = target.read_bytes()
        compared.append(dict(
            path=name, kind='present_file',
            bytes_equal=actual == original,
            newline_normalized_equal=actual.replace(b'\r\n', b'\n') == original.replace(b'\r\n', b'\n'),
            original_sha256=hashlib.sha256(original).hexdigest(),
            fresh_sha256=hashlib.sha256(actual).hexdigest()))
    categories = []
    for needle, label in ((b'LF will be replaced by CRLF', 'lf_to_crlf_warning'),
                          (b'CRLF will be replaced by LF', 'crlf_to_lf_warning'),
                          (b'warning:', 'git_warning')):
        if needle in status.stderr:
            categories.append(label)
    if status.stderr and not categories:
        categories.append('other_stderr_not_published')
    return dict(
        source_head=head, observation_scope='fresh checkout reproduction only',
        historical_status_stdout_was_nonempty=True,
        historical_physical_map_compared=False, historical_cause_certified=False,
        tracked_file_count=len(tree), fresh_diff_tracked_count=len(dirty),
        fresh_diff_public_paths=sorted(dirty)[:100], fresh_dirty_byte_comparisons=compared[:100],
        fresh_porcelain_stdout_nonempty=bool(status.stdout),
        fresh_status_stderr_nonempty=bool(status.stderr), fresh_status_stderr_categories=categories,
        fresh_status_stdout_sha256=hashlib.sha256(status.stdout).hexdigest(),
        fresh_status_stderr_sha256=hashlib.sha256(status.stderr).hexdigest(),
        aa_acceptance='not_decided', native_runs=0, verifier_reruns=0, h_reruns=0)

def diagnose(root, private, key, token):
    global PHASE
    PHASE = 'run_api_binding'
    run = json.loads(fetch(API + '/actions/runs/' + str(SOURCE_RUN), token))
    require(run['id'] == SOURCE_RUN and run['run_attempt'] == SOURCE_ATTEMPT
            and run['head_sha'] == SOURCE_HEAD and run['head_branch'] == 'codex/clause-oracle-mutation-1030'
            and run['status'] == 'completed' and run['conclusion'] == 'failure'
            and run['repository']['full_name'] == REPOSITORY)
    PHASE = 'artifact_api_binding'
    artifact = json.loads(fetch(API + '/actions/artifacts/' + str(ARTIFACT_ID), token))
    require(artifact['id'] == ARTIFACT_ID and artifact['name'] == ARTIFACT_NAME
            and artifact['expired'] is False and artifact['size_in_bytes'] == ARTIFACT_SIZE
            and artifact['digest'] == 'sha256:' + ARTIFACT_SHA256
            and artifact['workflow_run']['id'] == SOURCE_RUN
            and artifact['workflow_run']['head_sha'] == SOURCE_HEAD)
    PHASE = 'artifact_bytes_binding'
    location = fetch(API + '/actions/artifacts/' + str(ARTIFACT_ID) + '/zip', token, redirect=True)
    body = fetch(location)
    require(len(body) == ARTIFACT_SIZE and hashlib.sha256(body).hexdigest() == ARTIFACT_SHA256)
    token = None
    PHASE = 'source_binding'
    packet_body = git(root, 'show', SOURCE_HEAD + ':' + PACKET)
    packet = json.loads(packet_body)
    require(packet['id'] == 'clause-oracle-mutation-1030' and packet['required_unique_count'] == 1
            and [uid for row in packet['completed'].values() for uid in row['tests']] == [TEST])
    # Never import engine/tests; compare the retained source commit's bytes remotely.
    source_hashes = {name: hashlib.sha256(git(root, 'show', SOURCE_HEAD + ':' + name)).hexdigest()
                     for name in ('engine/trickster.py', 'tools/test_book_trickster_full.py')}
    for name in ('tools/ci_remote_h.py', 'tools/ci_fixtures.mjs'):
        require((root / name).read_bytes() == git(root, 'show', SOURCE_HEAD + ':' + name))
    PHASE = 'outer_archive_binding'
    with zipfile.ZipFile(io.BytesIO(body)) as outer:
        names = outer.namelist()
        require(len(names) == 3 and len(set(names)) == 3)
        paths = [PurePosixPath(name) for name in names]
        require(all(not p.is_absolute() and '..' not in p.parts and p.as_posix() == name for p, name in zip(paths, names)))
        require(len({p.parent for p in paths}) == 1 and {p.name for p in paths} == {'run.json', 'summary.json', 'diagnostics.zip.enc'})
        folder = paths[0].parent
        native = json.loads(member(outer, (folder / 'run.json').as_posix()))
        summary = json.loads(member(outer, (folder / 'summary.json').as_posix()))
        cipher = member(outer, (folder / 'diagnostics.zip.enc').as_posix())
    PHASE = 'native_cipher_binding'
    require(native['suite'] == 'changed_revisions' and native['git_sha'] == SOURCE_HEAD
            and native['ci']['GITHUB_RUN_ID'] == str(SOURCE_RUN)
            and native['ci']['GITHUB_RUN_ATTEMPT'] == str(SOURCE_ATTEMPT)
            and native['ci']['GITHUB_SHA'] == SOURCE_HEAD and native['exit_code'] != 0
            and native['execution_stage'].replace('\\', '/') == STAGE)
    compact = native['encrypted_evidence']['diagnostics']
    require(compact['file'] == 'diagnostics.zip.enc' and compact['complete_input_capture'] is False
            and hashlib.sha256(cipher).hexdigest() == compact['sha256'] and summary['suite'] == 'changed_revisions')
    command = native['verifier_outcome']['command']
    require(isinstance(command, list) and command.count('--output') == 1)
    output_path = Path(command[command.index('--output') + 1])
    require(output_path.is_absolute() and output_path.drive.upper() == 'D:'
            and output_path.parent.name == 'ci' and output_path.parent.parent.name == 'output'
            and re.fullmatch('[0-9a-f]{32}', output_path.name) is not None
            and output_path.name == native['evidence_id'])
    PHASE = 'authenticated_decryption'
    sealed, plaintext = private / 'diagnostics.zip.enc', private / 'diagnostics.zip'
    sealed.write_bytes(cipher)
    from ci_remote_h import crypt
    crypt(root, 'decrypt', sealed, plaintext, key)
    PHASE = 'inner_archive_binding'
    with zipfile.ZipFile(plaintext) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        require(len(names) == len(set(names)) and len(names) <= 32
                and sum(item.file_size for item in entries) <= 64 * 1024 * 1024
                and all(not item.is_dir() and not item.flag_bits & 1 for item in entries))
        scope = json.loads(member(archive, 'diagnostic-scope.json'))
        require(scope['kind'] == 'diagnostic_only' and scope['complete_input_capture'] is False
                and scope['full_evidence']['sha256'] == native['encrypted_evidence']['sha256'])
        reports = [name for name in names if re.fullmatch(r'verifier/tests-[0-9a-f]{32}\.json', name)]
        require(len(reports) == 1)
        report_name = reports[0]
        report_body = member(archive, report_name)
        log_body = member(archive, report_name[:-5] + '.log')
        physical_body = member(archive, 'physical/ci-native.json')
        report, physical = json.loads(report_body), json.loads(physical_body)
        require(isinstance(report, dict) and isinstance(physical, dict))
        log = log_body.decode('utf-8-sig')
    PHASE = 'original_predicate_observation'
    reduced = predicates(native, report, physical, log, report_name, output_path, source_hashes)
    PHASE = 'original_tracked_bytes_and_fresh_checkout'
    reduced['cleanliness_followup'] = inspect_original_cleanliness(root, private, native, physical)
    PHASE = 'aa_fresh_checkout_observation'
    reduced['aa_cleanliness_followup'] = inspect_aa_fresh_checkout(root, private)
    return dict(status='DIAGNOSTIC_ONLY_SOURCE_FAILURE_PRESERVED', source_run=SOURCE_RUN,
                source_attempt=SOURCE_ATTEMPT, source_head=SOURCE_HEAD, artifact_id=ARTIFACT_ID,
                artifact_sha256=ARTIFACT_SHA256, original_native_status='FAIL', original_h_not_reassessed=True,
                diagnostic_only=True, mutation_acceptance='not_decided',
                native_runs=0, verifier_reruns=0, h_reruns=0, completion_credit=0,
                raw_sha256={label: hashlib.sha256(data).hexdigest() for label, data in
                            (('raw_report', report_body), ('raw_log', log_body), ('physical_metadata', physical_body))},
                **reduced)


def main():
    key, token = os.environ.pop('PTK_FIXTURE_KEY', None), os.environ.pop('GITHUB_TOKEN', None)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root.resolve()
    result = {'status': 'DIAGNOSTIC_REJECTED_SOURCE_FAILURE_PRESERVED', 'source_run': SOURCE_RUN,
              'source_head': SOURCE_HEAD, 'native_runs': 0, 'verifier_reruns': 0, 'h_reruns': 0,
              'completion_credit': 0, 'mutation_acceptance': 'not_decided'}
    code, output_allowed = 1, False
    try:
        require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('CI_SUITE') == 'diagnose_oracle_mutation'
                and os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
                and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
                and os.environ.get('GITHUB_REF') == 'refs/heads/codex/clause-oracle-mutation-1030'
                and key and token)
        temporary = Path(os.environ['RUNNER_TEMP']).resolve()
        require(temporary.drive.upper() == 'D:' and root.drive.upper() == 'D:'
                and root == Path(os.environ['GITHUB_WORKSPACE']).resolve())
        output_allowed = True
        with tempfile.TemporaryDirectory(prefix='ptk-oracle-diagnostic-', dir=temporary) as directory:
            result = diagnose(root, Path(directory), key, token)
        code = 0
    except Exception as exc:
        # Only constant phase/type categories; never exception messages or private frames.
        result.update(rejected_phase=PHASE,
                      exception_class=type(exc).__name__ if type(exc).__name__ in EXCEPTIONS else 'DiagnosticError')
    finally:
        key = token = None
    if output_allowed:
        try:
            output = root / 'output/ci/oracle-diagnostic'
            output.mkdir(parents=True, exist_ok=True)
            (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        except Exception:
            result['status'], code = 'DIAGNOSTIC_SUMMARY_WRITE_REJECTED_SOURCE_FAILURE_PRESERVED', 1
    print(json.dumps(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
