"""Check referenced physical run evidence; never execute tests or award credit.

Source completeness, change impact and the continued validity of reused passes
remain the reviewer's responsibility. Historical nonphysical packets stay valid
under their existing acceptance path.
"""
from datetime import datetime
from hashlib import sha256
import ast
import json
from pathlib import Path, PureWindowsPath
import re
from zipfile import ZipFile


LOG_HEADERS = re.compile(
    r'^(?:(?P<test>test_\w+) \((?P<case>[-\w.]+)\)'
    r'(?: \.\.\.|\r?\n[^\r\n]+ \.\.\.)|'
    r'(?P<fixture>setUpClass|setUpModule|tearDownClass|tearDownModule) '
    r'\((?P<owner>[-\w.]+)\) \.\.\.)', re.M)


# shortcut: recognize only this existing physical preamble; review any changed runner separately.
PREVALIDATED_BASELINE_PREFIX = """import io,sys,os,json,hashlib,zipfile,time,datetime,unittest,importlib.util,builtins
from pathlib import Path
physical_open=io.open;physical_builtin_open=builtins.open;physical_isfile=os.path.isfile
base=Path('STAGE').resolve()
canonical=Path('ROOT').resolve()
verifier=base.parents[1]/'verify_overlay_tests.py'
output=base/'data/verification';casefile=base/'execution-cases.json'
def physical_bytes(path):
    with physical_open(path,'rb') as stream:return stream.read()
def physical_sha(path):return hashlib.sha256(physical_bytes(path)).hexdigest()
context=json.loads(physical_bytes(base/'run-context.json'))
assert context['stable_window_authorized'] is True
progress=json.loads(physical_bytes(canonical/'data/verification/category2-progress.json'))
assert progress['completed_clause_count']==context['completed_before']
assert physical_sha(canonical/'engine/engine.py')==context['canonical_engine_sha256']
assert physical_sha(canonical/'engine/turn.py')==context['canonical_turn_sha256']
baseline=json.loads(physical_bytes(base/'current-inputs.json'))
assert all((physical_sha(canonical/name) if physical_isfile(canonical/name) else None)==digest for name,digest in baseline.items())
"""


def require(condition, message):
    if not condition:
        raise RuntimeError('acceptance evidence: ' + message)


def identity(case):
    return case[6:] if case.startswith('tools.test_') else case


def prevalidated_metadata_capture(archive, pre, meta, stage, repo_root):
    """Check frozen pre-overlay SHA assertions; never relabel a late ZIP capture."""
    command = 'stage/verification-command.txt'
    baseline = 'stage/current-inputs.json'
    for entry in (command, baseline):
        physical = str(stage / entry.removeprefix('stage/'))
        require(physical in pre and sha256(archive.read(entry)).hexdigest() == pre[physical],
                'prevalidated baseline was not physically captured: ' + entry)
    match = re.fullmatch(r"python -B -X utf8 -c @'\r?\n(.*?)\r?\n'@\r?\nexit \$LASTEXITCODE\s*",
                         archive.read(command).decode('utf-8-sig').strip(), re.S)
    require(match is not None, 'prevalidated command must retain assertions and the physical wrapper')
    tree, expected = ast.parse(match[1]), ast.parse(PREVALIDATED_BASELINE_PREFIX)
    prefix = ast.Module(body=tree.body[:len(expected.body)], type_ignores=[])
    require(not any(isinstance(node, ast.Constant) and node.value in ('STAGE', 'ROOT') for node in ast.walk(prefix)),
            'prevalidated command must name the actual physical roots')
    for node in ast.walk(prefix):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for physical, label in ((stage, 'STAGE'), (repo_root, 'ROOT')):
                if PureWindowsPath(node.value) == PureWindowsPath(physical):
                    node.value = label
    require(ast.dump(prefix) == ast.dump(expected), 'prevalidated command physical baseline prefix differs')
    emissions = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'metadata' for target in node.targets)]
    require(len(emissions) == 1 and isinstance(emissions[0], ast.Dict), 'prevalidated command metadata emitter differs')
    literals = {key.value: value.value for key, value in zip(emissions[0].keys, emissions[0].values)
                if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)}
    require(all(literals.get(field) == meta[field] for field in ('frozen_inputs', 'raw_log')),
            'prevalidated command belongs to a different physical run')
    declared = json.loads(archive.read(baseline))
    require(isinstance(declared, dict), 'prevalidated baseline is not a SHA map')
    proven = {}
    for physical in meta['input_paths_missing_pre_execution_capture']:
        captured, root = PureWindowsPath(physical), PureWindowsPath(repo_root)
        require(captured.is_relative_to(root), 'prevalidated missing input is not canonical metadata')
        name = captured.relative_to(root).as_posix()
        require(re.fullmatch(r'data/verification/category2-[a-z0-9-]+-clause-status\.json', name),
                'prevalidated missing input is not a category2 clause-status ledger')
        require(declared.get(name) == pre.get(physical) == meta['first_actual_read_sha256'].get(physical)
                and physical in pre, 'prevalidated baseline SHA differs: ' + name)
        proven[physical] = pre[physical]
    return dict(inputs=proven, baseline=baseline, baseline_sha256=sha256(archive.read(baseline)).hexdigest(),
                command=command, command_sha256=sha256(archive.read(command)).hexdigest(),
                basis='Frozen physical baseline SHA assertion before overlay/import; ZIP capture itself was late.')


def log_results(body):
    """Keep test calls separate from subTest failures and fixture errors."""
    headers = list(LOG_HEADERS.finditer(body))
    cases, failures, errors = {}, [], []
    fixtures = []
    subtest_parents = set()
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(body)
        segment = body[header.end():end].split('\n' + '=' * 70, 1)[0]
        if header['fixture']:
            fixture = header['fixture'] + ' (' + header['owner'] + ')'
            require(segment.strip() == 'ERROR', 'invalid fixture log result: ' + fixture)
            fixtures.append(fixture)
            errors.append(fixture)
            continue
        case = header['case']
        require(header['test'] == case.rsplit('.', 1)[-1], 'log test name differs from ID: ' + case)
        status = re.search(r'^[ \t]*(ok|FAIL|ERROR)[ \t]*\r?$', segment, re.M)
        subresults = re.findall(r'^[ \t]+' + re.escape(header['test']) +
                               r' \(' + re.escape(case) + r'\) (.+?)(?: \.\.\.|\r?\n[^\r\n]+ \.\.\.) '
                               r'(FAIL|ERROR)[ \t]*\r?$',
                               segment, re.M)
        for suffix, outcome in subresults:
            (failures if outcome == 'FAIL' else errors).append(case + ' ' + suffix)
        require(status is not None or subresults, 'missing actual log result: ' + case)
        if not subresults and status[1] != 'ok':
            (failures if status[1] == 'FAIL' else errors).append(case)
        outcome = ('ERROR' if any(value == 'ERROR' for _, value in subresults) else 'FAIL') if subresults else status[1]
        if case in cases:
            require(index > 0 and headers[index-1]['case'] == case and case in subtest_parents
                    and not subresults and outcome in ('FAIL', 'ERROR'), 'duplicate actual log ID: ' + case)
            cases[case] = 'ERROR' if 'ERROR' in (cases[case], outcome) else 'FAIL'
            subtest_parents.remove(case)
        else:
            cases[case] = outcome
            if subresults:
                subtest_parents.add(case)
    fixture_details = re.findall(r'^ERROR: ((?:setUpClass|setUpModule|tearDownClass|tearDownModule) '
                                 r'\([-\w.]+\))\r?$', body, re.M)
    require(fixtures == fixture_details, 'fixture ERROR details contradict log results')
    counts = re.findall(r'^Ran (\d+) tests? in ([\d.]+)s\r?$', body, re.M)
    require(len(counts) == 1 and int(counts[0][0]) == len(cases), 'log Ran count differs from actual IDs')
    tail = body.rstrip()
    footer = re.search(r'\r?\nUTC end ([^\r\n]+)\Z', tail)
    if footer:
        offset = datetime.fromisoformat(footer[1]).utcoffset()
        require(offset is not None and offset.total_seconds() == 0, 'non-UTC log footer')
        tail = tail[:footer.start()].rstrip()
    passed = bool(re.search(r'(?:^|\n)OK\Z', tail))
    failed = re.search(r'(?:^|\n)FAILED \((failures=\d+(?:, errors=\d+)?|errors=\d+)\)\Z', tail)
    require(passed or failed, 'missing final unittest status')
    require(passed == (not failures and not errors), 'log final status contradicts cases')
    if failed:
        expected = {'failures': len(failures), 'errors': len(errors)}
        observed = dict((label, int(count)) for label, count in
                        re.findall(r'(failures|errors)=(\d+)', failed[1]))
        require(observed == {key: count for key, count in expected.items() if count},
                'log failure/error counts contradict cases')
    return cases, passed, failures, errors


def missing_method_errors(body, ids, cases, meta):
    """Link only exact unittest missing-method diagnostics, never test results."""
    diagnostics = {}
    for actual, status in cases.items():
        if not actual.startswith('unittest.loader._FailedTest.'):
            continue
        method = actual.removeprefix('unittest.loader._FailedTest.')
        require(re.fullmatch(r'test_\w+', method) and status == 'ERROR'
                and meta['error_ids'].count(actual) == 1
                and not any(value == actual or value.startswith(actual + ' ') for value in meta['failure_ids'])
                and not any(value.startswith(actual + ' ') for value in meta['error_ids']),
                'invalid missing-method loader result: ' + actual)
        heading = method + ' (' + actual + ')'
        details = re.findall(r'^ERROR: ' + re.escape(heading) +
                             r'\r?\n-{70}\r?\n(.*?)(?=\r?\n\r?\n[=-]{70}\r?\n)', body, re.M | re.S)
        detail = re.fullmatch(r"AttributeError: type object '(\w+)' has no attribute '(test_\w+)'",
                              details[0]) if len(details) == 1 else None
        require(detail is not None and detail[2] == method,
                'missing-method loader ERROR detail differs: ' + actual)
        matches = [case for case in ids if case.rsplit('.', 2)[-2:] == [detail[1], method]]
        require(len(matches) == 1 and matches[0] not in cases,
                'missing-method loader request is unknown or ambiguous: ' + actual)
        requested = matches[0]
        module = requested.rsplit('.', 2)[0]
        origin = meta['loaded_module_origins_before_execution'].get(module)
        require(origin is not None and origin == meta['loaded_module_origins'].get(module)
                and PureWindowsPath(origin['file']).name == module.rsplit('.', 1)[-1] + '.py',
                'missing-method loader module origin differs: ' + requested)
        diagnostics[actual] = dict(requested_test_id=requested, module=module, origin=origin)
    detail_headers = re.findall(r'^(FAIL|ERROR): (test_\w+) \((unittest\.loader\._FailedTest\.[-\w.]+)\)\r?$', body, re.M)
    require(detail_headers == [('ERROR', actual.rsplit('.', 1)[-1], actual) for actual in diagnostics],
            'missing-method loader ERROR headers differ')
    return diagnostics


def verify_acceptance_evidence(stage, spec, repo_root):
    """Validate only metadata referenced by this candidate and return plain facts."""
    stage, repo_root = Path(stage).resolve(), Path(repo_root).resolve()
    scope = spec.get('verification_scope', {})
    declared_runs = bool(spec.get('game_runs') or scope.get('game_commands'))
    empty = dict(game_commands=0, test_invocations=0, latest_valid_pass_count=0)
    if spec.get('existing_proof_only'):
        require(not declared_runs and not spec.get('test_executions', 0)
                and not spec.get('logs') and not spec.get('execution_history'),
                'existing_proof_only cannot claim fresh executions')
        return dict(mode='existing_proof_only', **empty)

    def path(name):
        value = Path(name)
        require(not value.is_absolute() and not value.drive and '..' not in value.parts,
                'evidence reference must stay inside stage: ' + str(name))
        return stage / value

    history = spec.get('execution_history', [])
    references = [row['metadata'] for row in history if row.get('metadata')]
    references += [name for name in spec.get('staged_artifacts', []) if name.endswith('.json')]
    references += [str(Path(name).with_suffix('.json')).replace('\\', '/')
                   for name in spec.get('logs', []) if path(name).with_suffix('.json').is_file()]
    metadata = {}
    for name in dict.fromkeys(references):
        value = json.loads(path(name).read_text(encoding='utf-8-sig'))
        if isinstance(value, dict) and any(key in value for key in
                ('runtime_test_data_sha256_before', 'frozen_inputs')):
            metadata[name] = value
    require(not declared_runs or metadata, 'declared game execution has no physical run metadata')
    if not metadata:
        return dict(mode='legacy_nonphysical', **empty)
    require(not history or all(row.get('metadata') in metadata for row in history),
            'execution_history entry has no physical metadata')
    require(len({row['metadata'] for row in history}) == len(history), 'duplicate history run')
    rows = {row['metadata']: row for row in history}
    require(not history or set(metadata) == set(rows), 'physical metadata missing from execution_history')
    required = {identity(case) for detail in spec.get('completed', {}).values()
                for case in detail.get('tests', [])}
    if 'required_test_ids' in spec:
        cases = spec['required_test_ids']
        label = 'repair ' if spec.get('repair_only') is True else ''
        require(isinstance(cases, list) and bool(cases) and all(
            isinstance(case, str) and case.strip() for case in cases),
            label + 'required_test_ids must be a non-empty string list')
        declared_required = {identity(case) for case in cases}
        require(len(declared_required) == len(cases), 'duplicate ' + label + 'required_test_ids')
        require(spec.get('repair_only') is True or required <= declared_required,
                'required_test_ids omit completed-clause tests')
        required = declared_required
    latest, runs = {}, []
    previous_end = None
    for name, meta in metadata.items():
        def check(condition, message):
            require(condition, name + ': ' + message)

        pre = meta['runtime_test_data_sha256_before']
        check(isinstance(pre, dict) and bool(pre) and all(
            isinstance(key, str) and isinstance(digest, str) and
            re.fullmatch(r'[a-f0-9]{64}', digest) for key, digest in pre.items()), 'invalid pre SHA map')
        check(pre == meta['runtime_test_data_sha256_after'] and meta['stable_hashes'] is True,
              'pre/post SHA maps differ')
        check(meta['physical_open_saved_before_overlay'] is True, 'physical open was not captured')
        missing = meta['input_paths_missing_pre_execution_capture']
        check(isinstance(missing, list) and all(isinstance(value, str) for value in missing)
              and len(missing) == len(set(missing)) and
              ((meta['complete_pre_input_capture'] is True and not missing) or
               (meta['complete_pre_input_capture'] is False and bool(missing))), 'missing pre capture')
        reads = meta['first_actual_read_sha256']
        check(len(meta['actual_read_paths']) == len(set(meta['actual_read_paths']))
              and set(meta['actual_read_paths']) == set(reads), 'first-read paths differ')
        # Declared uncaptured reads remain historical evidence, never eligible PASSes.
        check(all(pre[key] == digest if key in pre else
                  key in missing and isinstance(digest, str) and re.fullmatch(r'[a-f0-9]{64}', digest)
                  for key, digest in reads.items()),
              'first-read SHA missing from pre capture')
        check(all(value in reads and '..' not in PureWindowsPath(value).parts for value in missing),
              'missing pre capture path has no physical first-read evidence or is not normalized')
        for field in ('loaded_module_origins_before_execution', 'loaded_module_origins'):
            check(all(pre[origin['file']] == origin['sha256'] if origin['file'] in pre else
                      origin['file'] in missing and reads[origin['file']] == origin['sha256']
                      for origin in meta[field].values()), field + ' SHA missing from pre capture')
        archive_canonical = PureWindowsPath(repo_root)
        if 'command' in meta:
            command = meta['command']
            check(isinstance(command, list) and bool(command) and
                  all(isinstance(value, str) for value in command), 'invalid recorded physical command')
            roots = {}
            for option in ('--canonical', '--stage'):
                values = []
                for index, value in enumerate(command):
                    if value == option:
                        check(index + 1 < len(command) and not command[index + 1].startswith('--'),
                              'missing root in recorded physical command: ' + option)
                        values.append(command[index + 1])
                    elif value.startswith(option + '='):
                        values.append(value[len(option) + 1:])
                check(len(values) == 1, 'missing or duplicate root in recorded physical command: ' + option)
                roots[option] = PureWindowsPath(values[0])
            recorded_stage = roots['--stage']
            check(recorded_stage.is_absolute() and '..' not in recorded_stage.parts
                  and recorded_stage == PureWindowsPath(stage), 'conflicting recorded execution stage')
            check('execution_stage' not in meta or isinstance(meta['execution_stage'], str)
                  and PureWindowsPath(meta['execution_stage']) == recorded_stage,
                  'conflicting recorded execution stage metadata')
            archive_canonical = roots['--canonical']
            check(archive_canonical.is_absolute() and '..' not in archive_canonical.parts
                  and archive_canonical in (PureWindowsPath(repo_root), recorded_stage),
                  'unapproved recorded canonical root')
        archive_path = path(meta['frozen_inputs'])
        supplement = None
        with ZipFile(archive_path) as archive:
            entries = archive.namelist()
            check(len(entries) == len(set(entries)) == len(pre) + 1, 'ZIP entry count differs')
            check(json.loads(archive.read('physical-sha256.json')) == pre, 'ZIP manifest differs from pre/post')
            expected_names = {'physical-sha256.json'}
            for physical, digest in pre.items():
                captured = PureWindowsPath(physical)
                if captured.is_relative_to(PureWindowsPath(stage)):
                    entry = 'stage/' + captured.relative_to(PureWindowsPath(stage)).as_posix()
                elif captured.is_relative_to(archive_canonical):
                    entry = 'canonical/' + captured.relative_to(archive_canonical).as_posix()
                else:
                    entry = 'tooling/' + captured.name
                check(entry not in expected_names, 'duplicate physical ZIP mapping: ' + entry)
                expected_names.add(entry)
                check(entry in entries and sha256(archive.read(entry)).hexdigest() == digest,
                      'ZIP bytes SHA mismatch: ' + entry)
            check(set(entries) == expected_names, 'ZIP contains unaccounted entries')
            if (missing and {'stage/verification-command.txt', 'stage/current-inputs.json'} <= set(entries)
                    and all(PureWindowsPath(value).is_relative_to(PureWindowsPath(repo_root))
                        and re.fullmatch(r'data/verification/category2-[a-z0-9-]+-clause-status\.json',
                            PureWindowsPath(value).relative_to(PureWindowsPath(repo_root)).as_posix())
                        for value in missing)):
                supplement = prevalidated_metadata_capture(archive, pre, meta, stage, repo_root)
        capture_lists = ('capture_errors', 'changed_origin_errors')
        for field in capture_lists:
            check(field not in meta or isinstance(meta[field], list) and
                  all(isinstance(value, str) for value in meta[field]),
                  'invalid physical capture field: ' + field)
        # Protected runner stores missing loaded origins as exact file/SHA pairs;
        # older diagnostics stored strings. Neither form can prove an eligible PASS.
        field = 'loaded_inputs_missing_pre_execution_capture'
        missing_loaded = meta.get(field, [])
        check(isinstance(missing_loaded, list), 'invalid physical capture field: ' + field)
        expected_loaded = {origin['file']: origin['sha256']
                           for origin in meta['loaded_module_origins'].values()
                           if origin['file'] not in pre}
        seen_loaded = set()
        for value in missing_loaded:
            if isinstance(value, str) and value:
                file = value
            else:
                check(isinstance(value, dict) and set(value) == {'file', 'sha256'}
                      and isinstance(value['file'], str) and bool(value['file'])
                      and PureWindowsPath(value['file']).is_absolute()
                      and '..' not in PureWindowsPath(value['file']).parts
                      and isinstance(value['sha256'], str)
                      and re.fullmatch(r'[a-f0-9]{64}', value['sha256']) is not None,
                      'invalid physical capture field: ' + field)
                file = value['file']
                check(file in missing and expected_loaded.get(file) == value['sha256']
                      and reads.get(file) == value['sha256'],
                      'invalid physical capture field: ' + field)
            check(file not in seen_loaded, 'invalid physical capture field: ' + field)
            seen_loaded.add(file)
        if expected_loaded:
            check(seen_loaded == set(expected_loaded), 'invalid physical capture field: ' + field)
        check('complete_loaded_input_capture' not in meta or
              type(meta['complete_loaded_input_capture']) is bool,
              'invalid physical capture field: complete_loaded_input_capture')
        complete_capture = (not any(meta.get(field) for field in capture_lists) and not missing_loaded and
                            meta.get('complete_loaded_input_capture', True) is True)
        eligible = (not missing or supplement is not None) and complete_capture
        ids, actual = meta['test_ids'], meta['actual_test_ids']
        actual_set = set(actual)
        check(bool(ids) and len(ids) == len(set(ids))
              and len(actual) == len(actual_set) == meta['tests']
              and type(meta['tests']) is int,
              'requested/actual test IDs or counts differ')
        log_path = path(meta['raw_log'])
        body = log_path.read_text(encoding='utf-8-sig')
        cases, passed, failures, errors = log_results(body)
        check(list(cases) == actual, 'raw log IDs differ from actual_test_ids')
        check(meta['failure_ids'] == failures and meta['error_ids'] == errors,
              'FAIL/ERROR IDs contradict raw log')
        # A wrapper may fail after unittest passed because physical capture failed.
        # Retain that history, but never promote it to an acceptance-eligible PASS.
        wrapper_passed = meta['successful']
        check(meta.get('exception') is None and type(wrapper_passed) is bool
              and type(meta['exit_code']) is int and (meta['exit_code'] == 0) == wrapper_passed
              and (wrapper_passed is passed or passed and not eligible and not wrapper_passed),
              'exit/success/exception contradict raw results')
        loader_errors = missing_method_errors(body, ids, cases, meta)
        cursor, seen, fixture_errors = 0, set(), 0
        for header in LOG_HEADERS.finditer(body):
            if header['fixture']:
                fixture_errors += 1
            if header['fixture'] in ('setUpClass', 'setUpModule'):
                start = cursor
                # A failed setup blocks only its next contiguous class/module block.
                parts = 1 if header['fixture'] == 'setUpClass' else 2
                while cursor < len(ids) and ids[cursor].rsplit('.', parts)[0] == header['owner']:
                    check(ids[cursor] not in cases, 'setup fixture error contradicts actual test: ' + ids[cursor])
                    cursor += 1
                check(cursor > start and not passed, 'setup fixture error does not explain omitted requested IDs')
            elif header['case'] and header['case'] not in seen:
                requested = loader_errors.get(header['case'], {}).get('requested_test_id', header['case'])
                check(cursor < len(ids) and ids[cursor] == requested,
                      'unexplained omitted requested ID or log order differs')
                seen.add(header['case'])
                cursor += 1
        check(cursor == len(ids), 'unexplained omitted requested IDs')
        if 'started_utc' in meta:
            started, ended = (datetime.fromisoformat(meta[field]) for field in ('started_utc', 'finished_utc'))
            check(started <= ended and (previous_end is None or previous_end <= started),
                  'run chronology differs from reference order')
            previous_end = ended
        facts = dict(actual_test_calls=len(actual), successful=passed,
                     actual_original_test_calls=len(actual) - len(loader_errors),
                     loader_error_count=len(loader_errors), loader_errors=loader_errors,
                     unexecuted_requested_ids=[case for case in ids if case not in cases],
                     pass_count=sum(status == 'ok' for status in cases.values()), failure_count=len(failures),
                     error_count=len(errors), fixture_error_count=fixture_errors,
                     physical_inputs=len(pre), first_reads=len(reads),
                     pre_execution_origins=len(meta['loaded_module_origins_before_execution']),
                     loaded_origins=len(meta['loaded_module_origins']), stable_hashes=True,
                     complete_pre_input_capture=meta['complete_pre_input_capture'], raw_log=meta['raw_log'],
                     input_paths_missing_pre_execution_capture=list(missing),
                     acceptance_eligible=eligible,
                     acceptance_ineligible_reason=(None if eligible else
                         'Physical read/module capture errors or incomplete loaded input capture.'
                         if not complete_capture else
                         'Incomplete pre-input capture without a valid metadata supplement.'),
                     physical_zip=meta['frozen_inputs'])
        if supplement:
            facts.update(prevalidated_metadata_capture=supplement,
                         prevalidated_metadata_input_count=len(supplement['inputs']))
        if 'completed_before' in meta:
            facts['completed_before'] = meta['completed_before']
        for field, value in facts.items():
            if field in rows.get(name, {}):
                check(rows[name][field] == value, 'history contradicts metadata: ' + field)
        for case, status in cases.items():
            if case not in loader_errors:
                latest[identity(case)] = (status, name)
        for diagnostic in loader_errors.values():
            latest[identity(diagnostic['requested_test_id'])] = ('ERROR', name)
        if not eligible:
            # Failed setup may omit a requested call; it still invalidates an older PASS.
            for case in ids:
                if identity(case) in latest:
                    latest[identity(case)] = ('ineligible', name)
        runs.append(dict(metadata=name, actual_test_ids=actual, failure_ids=failures, error_ids=errors,
                         metadata_sha256=sha256(path(name).read_bytes()).hexdigest(),
                         raw_log_sha256=sha256(log_path.read_bytes()).hexdigest(),
                         archive_sha256=sha256(archive_path.read_bytes()).hexdigest(), **facts))
    require(set(spec.get('logs', [])) == {run['raw_log'] for run in runs},
            'candidate logs differ from physical runs')
    required = required or set(latest)
    require(all(latest.get(case, (None,))[0] == 'ok' for case in required),
            'required test has no latest actual PASS from an acceptance-eligible execution')
    latest_passes = {case: latest[case][1] for case in sorted(required)}
    if 'latest_valid_passes' in spec:
        require({identity(case): name for case, name in spec['latest_valid_passes'].items()} == latest_passes,
                'latest_valid_passes contradict latest actual execution')
    if 'latest_valid_passes_metadata' in spec:
        require(set(latest_passes.values()) == {spec['latest_valid_passes_metadata']},
                'latest_valid_passes_metadata contradicts actual executions')
    count, calls = len(required), sum(run['actual_test_calls'] for run in runs)
    for field, observed in [('mandatory_unique_ids', count), ('latest_valid_pass_count', count),
                            ('game_runs', len(runs)), ('test_executions', calls)]:
        if field in spec:
            require(type(spec[field]) is int and spec[field] == observed, 'candidate count differs: ' + field)
    for field, observed in [('unique_required_tests', count), ('latest_valid_passes', count),
                            ('game_commands', len(runs)), ('test_invocations', calls)]:
        if field in scope:
            require(type(scope[field]) is int and scope[field] == observed, 'verification_scope count differs: ' + field)
    return dict(mode='physical', unique_required_tests=count, observed_unique_tests=len(latest),
                test_invocations=calls, game_commands=len(runs), latest_valid_pass_count=count,
                actual_original_test_calls=sum(run['actual_original_test_calls'] for run in runs),
                loader_error_count=sum(run['loader_error_count'] for run in runs),
                first_run_includes_all_required=required <= {identity(case) for case in runs[0]['actual_test_ids']
                                                           if case not in runs[0]['loader_errors']},
                latest_valid_passes=latest_passes, runs=runs,
                fully_pre_captured_runs=sum(run['complete_pre_input_capture'] for run in runs),
                prevalidated_metadata_runs=sum('prevalidated_metadata_capture' in run for run in runs),
                insufficient_pre_capture_runs=sum(not run['acceptance_eligible'] for run in runs),
                review_limits='Source completeness, change impact, retained PASS validity and credit require Root review.')
