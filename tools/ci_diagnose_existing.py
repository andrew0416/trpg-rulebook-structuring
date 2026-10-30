"""Diagnose one fixed failed Actions run; never execute tests or accept evidence."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = 'andrew0416/trpg-rulebook-structuring'
SOURCE_RUN = 41000288952
SOURCE_ATTEMPT = 1
SOURCE_HEAD = '10ca2acf2917ca55b996df50f30c12c2880c1b5f'
ARTIFACT_ID = 12953981205
ARTIFACT_NAME = 'diagnostics-changed_revisions-41000288952-1'
ARTIFACT_SHA256 = 'c4737ff55df7f0b72766fb57111d0ba2bc4b13f710ad2cd7fa2c23bc40d89ac0'
ARTIFACT_SIZE = 954919
API = 'https://api.github.com/repos/' + REPOSITORY
PACKET = '.ci/suites/changed_revisions.json'
STAGE = 'D:/trpg-rulebook-structuring/ci/41000288952-1-changed_revisions'
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
    entries = archive.infolist()
    names = [entry.filename for entry in entries]
    require(len(names) <= 4096 and len(names) == len(set(names)) == len({value.casefold() for value in names})
            and names.count(name) == 1 and sum(entry.file_size for entry in entries) <= 64 * 1024 * 1024)
    for entry in entries:
        path = PurePosixPath(entry.filename)
        require(not path.is_absolute() and '..' not in path.parts and path.as_posix() == entry.filename
                and '\\' not in entry.filename and ':' not in entry.filename
                and not entry.is_dir() and not entry.flag_bits & 1
                and stat.S_IFMT(entry.external_attr >> 16) in (0, stat.S_IFREG))
    info = archive.getinfo(name)
    require(not info.is_dir() and info.file_size <= 16 * 1024 * 1024)
    return archive.read(info)


def public_parent(label, allowed):
    if not isinstance(label, str):
        return None
    return next((uid for uid in allowed if label == uid or label.startswith((uid + ' (', uid + ' ['))), None)


def diagnose(root, private, key, token):
    run = json.loads(fetch(API + '/actions/runs/' + str(SOURCE_RUN), token))
    require(run['id'] == SOURCE_RUN and run['run_attempt'] == SOURCE_ATTEMPT
            and run['head_sha'] == SOURCE_HEAD and run['status'] == 'completed'
            and run['conclusion'] == 'failure' and run['repository']['full_name'] == REPOSITORY)
    artifact = json.loads(fetch(API + '/actions/artifacts/' + str(ARTIFACT_ID), token))
    require(artifact['id'] == ARTIFACT_ID and artifact['name'] == ARTIFACT_NAME
            and artifact['expired'] is False and artifact['size_in_bytes'] == ARTIFACT_SIZE
            and artifact['digest'] == 'sha256:' + ARTIFACT_SHA256
            and artifact['workflow_run']['id'] == SOURCE_RUN
            and artifact['workflow_run']['head_sha'] == SOURCE_HEAD)
    location = fetch(API + '/actions/artifacts/' + str(ARTIFACT_ID) + '/zip', token, redirect=True)
    body = fetch(location)  # The signed GitHub artifact storage request receives no GitHub token.
    require(len(body) == ARTIFACT_SIZE and hashlib.sha256(body).hexdigest() == ARTIFACT_SHA256)
    token = None
    packet_body = (root / PACKET).read_bytes()
    require(git(root, 'show', SOURCE_HEAD + ':' + PACKET) == packet_body
            and git(root, 'show', 'HEAD:' + PACKET) == packet_body)
    packet = json.loads(packet_body)
    ids = [uid for row in packet['completed'].values() for uid in row['tests']]
    require(len(ids) == len(set(ids)) == packet['required_unique_count'] == 112)
    require(all(isinstance(uid, str) and re.fullmatch(r'(?:tools|tests)(?:\.[A-Za-z_][A-Za-z0-9_]*){2,}\.test_[A-Za-z0-9_]+', uid) for uid in ids))
    allowed = set(ids)
    rows = {uid: {'id': uid, 'status': 'not_reported', 'exception_classes': [], 'public_frames': []} for uid in ids}
    with zipfile.ZipFile(io.BytesIO(body)) as outer:
        names = outer.namelist()
        require(len(names) == 3 and len(set(names)) == 3)
        paths = [PurePosixPath(name) for name in names]
        require(all(not p.is_absolute() and '..' not in p.parts and p.as_posix() == name for p, name in zip(paths, names)))
        require(len({p.parent for p in paths}) == 1 and {p.name for p in paths} == {'run.json', 'summary.json', 'diagnostics.zip.enc'})
        folder = paths[0].parent
        require(folder.as_posix() == '52a30a479bc343b2b438aca27c4c9f7d')
        native = json.loads(member(outer, (folder / 'run.json').as_posix()))
        summary = json.loads(member(outer, (folder / 'summary.json').as_posix()))
        cipher = member(outer, (folder / 'diagnostics.zip.enc').as_posix())
    require(native['suite'] == 'changed_revisions' and native['git_sha'] == SOURCE_HEAD
            and native['ci']['GITHUB_RUN_ID'] == str(SOURCE_RUN)
            and native['ci']['GITHUB_RUN_ATTEMPT'] == str(SOURCE_ATTEMPT)
            and native['ci']['GITHUB_SHA'] == SOURCE_HEAD and native['exit_code'] != 0
            and native['execution_stage'].replace('\\', '/') == STAGE)
    compact = native['encrypted_evidence']['diagnostics']
    require(compact['file'] == 'diagnostics.zip.enc' and compact['complete_input_capture'] is False
            and hashlib.sha256(cipher).hexdigest() == compact['sha256'] and summary['suite'] == 'changed_revisions')
    for report in summary['reports']:
        for row in report['tests']:
            if row.get('id') in allowed and row.get('status') in STATUSES:
                rows[row['id']]['status'] = row['status']
    sealed, plaintext = private / 'diagnostics.zip.enc', private / 'diagnostics.zip'
    sealed.write_bytes(cipher)
    from ci_remote_h import crypt
    crypt(root, 'decrypt', sealed, plaintext, key)
    public_paths = set(git(root, 'ls-tree', '-r', '--name-only', SOURCE_HEAD, '--', 'engine', 'tools', 'tests').decode('utf-8').splitlines())
    source_line_counts = {}
    with zipfile.ZipFile(plaintext) as archive:
        scope = json.loads(member(archive, 'diagnostic-scope.json'))
        require(scope['kind'] == 'diagnostic_only' and scope['complete_input_capture'] is False
                and scope['full_evidence']['sha256'] == native['encrypted_evidence']['sha256'])
        physical = json.loads(member(archive, 'physical/ci-native.json'))
        require(set(physical['test_ids']) == allowed and physical['exit_code'] != 0
                and physical['execution_stage'].replace('\\', '/') == STAGE)
        integrity = {field: physical.get(field) is True for field in
                     ('stable_hashes', 'complete_pre_input_capture', 'complete_loaded_input_capture')}
        integrity.update({field + '_count': len(physical.get(field, [])) for field in
                          ('input_paths_missing_pre_execution_capture', 'loaded_inputs_missing_pre_execution_capture',
                           'changed_origin_errors', 'input_read_errors', 'ordinary_extended_generated_errors')})
        integrity.update(exception_present=bool(physical.get('exception')),
                         native_inputs_unchanged=native.get('inputs_unchanged') is True)
        for field, status in (('failure_ids', 'fail'), ('error_ids', 'error')):
            for label in physical[field]:
                uid = public_parent(label, allowed)
                if uid is not None:
                    rows[uid]['status'] = status
        for line in member(archive, 'physical/ci-native-events.jsonl').decode('utf-8').splitlines():
            event = json.loads(line)
            if event.get('event') != 'test_diagnostic' or event.get('outcome') not in ('failures', 'errors'):
                continue
            uid = public_parent(event.get('id'), allowed)
            detail = event.get('traceback')
            if uid is None or not isinstance(detail, str):
                continue
            for text in detail.splitlines():
                kind = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)(?::|$)', text)
                if kind and kind[1] in EXCEPTIONS and kind[1] not in rows[uid]['exception_classes']:
                    rows[uid]['exception_classes'].append(kind[1])
                frame = re.fullmatch(r'  File "([^"\r\n]+)", line ([1-9][0-9]*)(?:, in [^\r\n]*)?', text)
                if not frame:
                    continue
                path = frame[1].replace('\\', '/')
                relative = path[len(STAGE) + 1:] if path.startswith(STAGE + '/') else ''
                if relative in public_paths and re.fullmatch(r'(?:tools|engine|tests)/[A-Za-z0-9_/]+\.py', relative):
                    if relative not in source_line_counts:
                        source_line_counts[relative] = len(git(root, 'show', SOURCE_HEAD + ':' + relative).splitlines())
                    if int(frame[2]) > source_line_counts[relative]:
                        continue
                    position = {'file': relative, 'line': int(frame[2])}
                    if position not in rows[uid]['public_frames']:
                        rows[uid]['public_frames'].append(position)
    return {'status': 'DIAGNOSTIC_ONLY_SOURCE_FAILURE_PRESERVED', 'source_run': SOURCE_RUN,
            'source_attempt': SOURCE_ATTEMPT, 'source_head': SOURCE_HEAD, 'artifact_id': ARTIFACT_ID,
            'artifact_sha256': ARTIFACT_SHA256, 'source_result': 'failure', 'diagnostic_only': True,
            'native_runs': 0, 'verifier_reruns': 0, 'h_reruns': 0, 'completion_credit': 0, 'integrity': integrity,
            'status_counts': {status: sum(row['status'] == status for row in rows.values())
                              for status in sorted(STATUSES | {'not_reported'})},
            'tests': [rows[uid] for uid in sorted(rows)]}


def main():
    key, token = os.environ.pop('PTK_FIXTURE_KEY', None), os.environ.pop('GITHUB_TOKEN', None)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root.resolve()
    result = {'status': 'DIAGNOSTIC_REJECTED_SOURCE_FAILURE_PRESERVED', 'source_run': SOURCE_RUN,
              'source_head': SOURCE_HEAD, 'native_runs': 0, 'verifier_reruns': 0, 'h_reruns': 0, 'completion_credit': 0}
    code, output_allowed = 1, False
    try:
        require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('CI_SUITE') == 'diagnose_existing'
                and os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
                and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
                and os.environ.get('GITHUB_REF_NAME', '').startswith('codex/') and key and token)
        temporary = Path(os.environ['RUNNER_TEMP']).resolve()
        require(temporary.drive.upper() == 'D:' and root.drive.upper() == 'D:'
                and root == Path(os.environ['GITHUB_WORKSPACE']).resolve())
        git(root, 'merge-base', '--is-ancestor', SOURCE_HEAD, 'HEAD')
        require(set(git(root, 'diff', '--name-only', SOURCE_HEAD, 'HEAD').decode().splitlines())
                <= {'tools/ci_diagnose_existing.py', '.github/workflows/validate.yml'})
        output_allowed = True
        with tempfile.TemporaryDirectory(prefix='ptk-existing-diagnostic-', dir=temporary) as directory:
            result = diagnose(root, Path(directory), key, token)
        code = 0
    except Exception as exc:
        lines, trace = [], exc.__traceback__
        while trace is not None:
            if trace.tb_frame.f_code.co_filename == __file__ and type(trace.tb_lineno) is int and trace.tb_lineno > 0:
                lines.append(trace.tb_lineno)
            trace = trace.tb_next
        result.update(public_helper_lines=lines,
                      exception_class=type(exc).__name__ if type(exc).__name__ in EXCEPTIONS else 'DiagnosticError')
    finally:
        key = token = None
    if output_allowed:
        try:
            output = root / 'output/ci/existing-diagnostic'
            output.mkdir(parents=True, exist_ok=True)
            (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        except Exception:
            result['status'], code = 'DIAGNOSTIC_SUMMARY_WRITE_REJECTED_SOURCE_FAILURE_PRESERVED', 1
    print(json.dumps(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
