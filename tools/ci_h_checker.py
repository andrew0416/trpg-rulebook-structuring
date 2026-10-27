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
from io import BytesIO
import importlib.util


LOG_HEADERS = re.compile(
    r'^(?:(?P<test>test_\w+) \((?P<case>[-\w.]+)\)(?:\r?\n[^\r\n]+)?|'
    r'(?P<fixture>setUpClass|setUpModule|tearDownClass|tearDownModule) '
    r'\((?P<owner>[-\w.]+)\)) \.\.\.', re.M)


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


FREQUENCY_COLLECTOR_SHA256='22052132a3df2d7542971bb096f2a522f0679172f2037e9b0649c0f3484011ab'
FREQUENCY_PACKET_SHA256='6b95ef86b663ee2039ad351c04cf52e0f3a5d8ca59d5d5404a01af66c0434093'
FREQUENCY_HARNESS_SHA256='2ebcc689bd1d3012273437590f49e64967a6306158aaa58c19dcbb905f67b11e'
FREQUENCY_ORIGINAL_INPUTS_SHA256={
    'tools/test_frequencies.py':'d600b212b6b0ec3a3975af39fccc8349b1a2b22a53cd3beed111acc0d82ddf3d',
    'tools/frequency_source_connection_fixture.py':'a2f01dc69fff6cc61649e60fbd65fefb4d7445362542341c226ecb3ee1aeab1c',
    'tools/frequency_source_connection_contract.json':'ecbcf0bbdc90c6e7331abf680ba25175ffe4c10721b9bacdd0d7aec702d00113',
}


def verify_frequency_equivalence_archive(archive_path,*,archive_sha256,packet_path,packet_sha256,collector_path):
    """Read-only typed acceptance from full raw evidence; never ordinary method PASS."""
    archive_path,packet_path,collector_path=map(Path,(archive_path,packet_path,collector_path))
    require(type(archive_sha256)is str and re.fullmatch('[a-f0-9]{64}',archive_sha256)
            and sha256(archive_path.read_bytes()).hexdigest()==archive_sha256,'frequency full archive SHA differs')
    require(packet_sha256==FREQUENCY_PACKET_SHA256==sha256(packet_path.read_bytes()).hexdigest(),'frequency fixed packet SHA differs')
    require(sha256(collector_path.read_bytes()).hexdigest()==FREQUENCY_COLLECTOR_SHA256,'frequency fixed collector SHA differs')
    packet=json.loads(packet_path.read_bytes())
    require(packet['execution_kind']=='frequency_equivalence' and packet['harness_sha256']==FREQUENCY_HARNESS_SHA256,'frequency frozen harness differs')
    specification=importlib.util.spec_from_file_location('independent_frozen_typed_collector',collector_path)
    collector=importlib.util.module_from_spec(specification);specification.loader.exec_module(collector)
    modes=('cold','connected','connected_first_failure')
    expected=[uid for row in packet['completed'].values() for uid in row['tests']]
    require(len(expected)==len(set(expected))==1029,'frequency original scope differs')
    with ZipFile(archive_path) as archive:
        names=archive.namelist()
        require(len(names)==len(set(names)) and all(type(n)is str and not n.startswith('/') and '\\' not in n and ':' not in n and all(p not in ('','..','.') for p in n.split('/')) for n in names),'unsafe/duplicate frequency archive member')
        require('diagnostic-scope.json' not in names,'diagnostic frequency evidence is ineligible')
        metadata_body=archive.read('physical/ci-native.json');meta=json.loads(metadata_body)
        require(meta.get('execution_kind')=='frequency_equivalence_gate','not a frequency typed execution')
        pre=meta.get('runtime_test_data_sha256_before');post=meta.get('runtime_test_data_sha256_after')
        require(type(pre)is dict and bool(pre) and all(type(k)is str and type(v)is str and re.fullmatch('[a-f0-9]{64}',v) for k,v in pre.items()),'invalid frequency pre SHA map')
        require(pre==post,'frequency pre/post bytes differ')
        for flag in ('stable_hashes','complete_pre_input_capture','complete_loaded_input_capture','physical_open_saved_before_overlay','successful'):
            require(meta.get(flag)is True,'frequency physical flag not confirmed: '+flag)
        for field in ('changed_origin_errors','input_read_errors','input_paths_missing_pre_execution_capture','loaded_inputs_missing_pre_execution_capture','failure_ids','error_ids'):
            require(field in meta and not meta[field],'frequency physical errors/missing field: '+field)
        require(type(meta.get('exit_code'))is int and meta['exit_code']==0 and meta.get('exception')is None,'frequency execution failed')
        started,ended=(datetime.fromisoformat(meta[field]) for field in ('started_utc','finished_utc'))
        require(all(value.utcoffset() is not None and value.utcoffset().total_seconds()==0 for value in (started,ended)) and ended>=started,'frequency UTC interval invalid')
        root=PureWindowsPath(meta['execution_stage'])
        require(root.is_absolute() and '..' not in root.parts,'invalid frequency physical stage')
        def relative(value):
            require(type(value)is str,'frequency physical path must be text')
            physical=PureWindowsPath(value)
            require(physical.is_absolute() and '..' not in physical.parts and physical.is_relative_to(root),'frequency input leaves execution stage')
            return physical.relative_to(root).as_posix()
        frozen_body=archive.read('physical/ci-native-inputs.zip')
        with ZipFile(BytesIO(frozen_body)) as frozen:
            entries=frozen.namelist();wanted={'physical-sha256.json'};normalized=set();captured={}
            require(len(entries)==len(set(entries)),'duplicate frequency frozen member')
            require(json.loads(frozen.read('physical-sha256.json'))==pre,'frequency frozen pre manifest differs')
            for physical,digest in pre.items():
                rel=relative(physical);entry='stage/'+rel
                require(rel.casefold() not in normalized,'frequency aliased input path')
                normalized.add(rel.casefold());wanted.add(entry);body=frozen.read(entry)
                require(sha256(body).hexdigest()==digest,'frequency frozen input bytes differ: '+rel)
                captured[rel]=digest
            require(set(entries)==wanted,'unaccounted frequency frozen input bytes')
        require(captured.get('.ci/suites/frequency_equivalence.json')==packet_sha256,'frequency packet not captured as original input')
        require(captured.get(packet['harness'])==FREQUENCY_HARNESS_SHA256,'frequency immutable harness bytes not captured')
        require(all(captured.get(rel)==digest for rel,digest in FREQUENCY_ORIGINAL_INPUTS_SHA256.items()),'frequency original test/helper/contract source differs')
        reads=meta.get('first_actual_read_sha256')
        require(type(reads)is dict and bool(reads) and set(meta.get('actual_read_paths',[]))==set(reads)
                and len(meta['actual_read_paths'])==len(reads) and all(pre.get(k)==v for k,v in reads.items()),'frequency uncaptured/changed actual read')
        require(all(any(relative(k)==rel and v==captured[rel] for k,v in reads.items()) for rel in ('.ci/suites/frequency_equivalence.json',packet['harness'],'tools/test_frequencies.py')),'frequency packet/harness/test was not actually read')
        def origins(value):
            require(type(value)is dict and bool(value),'frequency actual origins missing')
            require(all(type(v)is dict and set(v)=={'file','sha256'} and pre.get(v['file'])==v['sha256'] for v in value.values()),'frequency actual origin outside frozen bytes')
        origins(meta['loaded_module_origins_before_execution']);origins(meta['loaded_module_origins'])
        require(set(meta.get('equivalence_mode_origins',{}))==set(modes),'frequency origins do not cover all modes')
        for value in meta['equivalence_mode_origins'].values():origins(value)
        test_origin={'file':next(key for key in pre if relative(key)=='tools/test_frequencies.py'),'sha256':captured['tools/test_frequencies.py']}
        require(all(value.get('tools.test_frequencies')==test_origin for value in meta['equivalence_mode_origins'].values()),'frequency original test origin differs between modes')
        require(meta['loaded_module_origins_before_execution']==meta['equivalence_mode_origins'][modes[-1]],'frequency final before-mode origin differs')
        raw_events=archive.read('physical/ci-native-events.jsonl')
        events=[json.loads(line) for line in raw_events.decode('utf-8-sig').splitlines()]
        require(events and all(type(row)is dict for row in events),'frequency event stream malformed')
        require(events[0].get('event')=='capture_ready' and events[0].get('runtime_test_data_sha256_before')==pre
                and events[0].get('execution_stage')==meta['execution_stage']
                and events[0].get('started_utc')==meta['started_utc'],'frequency initial capture event differs')
        finishes=[row for row in events if row.get('event')=='finished']
        require(len(finishes)==1 and events[-1] is finishes[0] and finishes[0].get('exit_code')==0
                and finishes[0].get('runtime_test_data_sha256_after')==post
                and finishes[0].get('loaded_module_origins')==meta['loaded_module_origins'],'frequency final physical event differs')
        before=[row for row in events if row.get('event')=='before_execution']
        require([row.get('mode') for row in before]==list(modes) and all(row.get('loaded_module_origins')==meta['equivalence_mode_origins'][row['mode']] for row in before),'frequency raw mode boundaries/origins differ')
        read_events=[row for row in events if row.get('event')=='first_read']
        require(len(read_events)==len(reads) and len({row.get('file') for row in read_events})==len(reads)
                and {row.get('file') for row in read_events}==set(reads)
                and all(reads.get(row.get('file'))==row.get('sha256') and row.get('captured_before')is True and row.get('declared_generated_input')is False for row in read_events),'frequency raw first-read evidence differs')
        verifier_names=[name for name in names if re.fullmatch('verifier/tests-[^/]+\\.json',name)]
        require(len(verifier_names)==1,'one original frequency collection report required')
        verifier_body=archive.read(verifier_names[0]);verifier=json.loads(verifier_body)
        require(verifier.get('successful')is True and verifier.get('discovery_errors')==[] and verifier.get('tests_run')==0,'frequency original collection failed or ran ordinary tests')
        original=collector.read_original(archive,meta)
        execution=collector.frequency(verifier,meta,packet,original,diagnostic=False);gate=execution['frequency_gate']
        require(gate['status']=='equivalent' and not gate['integrity_errors'] and not gate['gate_failures']
                and gate['verified_equivalent_method_ids']==sorted(expected),'frequency independent collector refused original gate')
        report=original['report'];started=[row for row in events if row.get('event')=='test_start']
        require(len(started)==3087 and [row.get('id') for row in started]==meta['equivalence_actual_test_ids']==finishes[0].get('actual_test_ids'),'frequency raw 3087 starts differ')
        active=None;starts_by_mode={mode:[] for mode in modes}
        for row in events:
            if row.get('event')=='before_execution':active=row['mode']
            if row.get('event')=='test_start':
                require(row.get('mode')==active and active in starts_by_mode,'frequency start outside its raw mode boundary')
                starts_by_mode[active].append(row.get('id'))
        for mode in modes:
            outcome=report['outcomes'][mode]
            require(starts_by_mode[mode]==outcome['started_ids']==outcome['finished_ids'],'frequency raw/original per-mode order differs')
            require(outcome.get('expected_failure_injection')is (mode==modes[-1]),'frequency expected injection mode differs')
        wanted=[collector.INJECTED.rsplit('_',1)[0]+'_'+str(i).zfill(4) for i in range(1,32)]
        require(report['expected_blocked_after_injection']==wanted,'frequency exact first-chain 31 blocked IDs differ')
        observations=report.get('observations')
        require(type(observations)is dict and set(observations)==set(modes),'frequency original observations lack three modes')
        for mode in modes:
            observed=observations[mode]
            require(type(observed)is dict and set(observed)==set(expected),'frequency observation ID coverage differs')
            for uid,trace in observed.items():
                require(type(trace)is list and (not trace if mode==modes[-1] and uid in wanted else bool(trace)),'frequency blocked/unblocked assertion trace empty contract differs')
                require(all(type(row)is dict and set(row)=={'assertion','arguments'} and type(row['assertion'])is str and row['assertion'].startswith('assert') for row in trace),'frequency original assertion trace shape differs')
        require(all(observations[modes[-1]][uid]==observations['connected'][uid] for uid in set(expected)-set(wanted)),'frequency unblocked injected-mode original assertions differ')
        diagnostics=[row for row in events if row.get('event')=='test_diagnostic']
        require(len(diagnostics)==1 and diagnostics[0].get('mode')==modes[-1]
                and diagnostics[0].get('outcome')=='failures' and diagnostics[0].get('id')==collector.INJECTED
                and collector.INJECTION in diagnostics[0].get('traceback','')
                and diagnostics[0]['traceback']==report['outcomes'][modes[-1]]['failures'][0][1],'frequency raw intentional diagnostic differs')
        log=archive.read('physical/ci-native.log')
        original_log=verifier_names[0].removesuffix('.json')+'.log'
        require(archive.read(original_log)==log and PureWindowsPath(meta['original_cli_report']).name==verifier_names[0].split('/')[-1]
                and PureWindowsPath(meta['original_cli_log']).name==original_log.split('/')[-1],'frequency original collection log/report binding differs')
        require(type(meta.get('metadata_path'))is str and type(meta.get('raw_log'))is str and type(meta.get('frozen_inputs'))is str,'frequency evidence references missing')
        for field in ('metadata_path','raw_log','frozen_inputs'):
            value=meta[field]
            require(not PureWindowsPath(value).is_absolute() and '..' not in PureWindowsPath(value).parts,'unsafe frequency evidence reference')
        run=dict(metadata=meta['metadata_path'],execution_kind='frequency_equivalence_gate',acceptance_eligible=True,stable_hashes=True,
            complete_pre_input_capture=True,metadata_sha256=sha256(metadata_body).hexdigest(),raw_log_sha256=sha256(log).hexdigest(),
            frozen_inputs_sha256=sha256(frozen_body).hexdigest(),events_sha256=sha256(raw_events).hexdigest(),
            equivalence_report_sha256=original['sha256'],verifier_sha256=sha256(verifier_body).hexdigest(),
            ordinary_test_pass_credit=0,observed_start_events=3087,original_method_count=1029,
            mode_counts={mode:dict(started=len(report['outcomes'][mode]['started_ids']),blocked=len(report['outcomes'][mode]['blocked_body_ids']),failures=len(report['outcomes'][mode]['failures']),errors=len(report['outcomes'][mode]['errors'])) for mode in modes})
        return dict(mode='physical',execution_kind='frequency_equivalence_gate',typed_status='equivalent',
            equivalence_verified_method_ids=sorted(expected),ordinary_test_pass_credit=0,latest_valid_pass_count=0,
            ordinary_test_invocations=0,typed_native_commands=1,observed_start_events=3087,runs=[run],
            archive_sha256=archive_sha256,packet_sha256=packet_sha256,collector_sha256=FREQUENCY_COLLECTOR_SHA256,
            control_commit='860985b46ec5d376409c03b176329acde453bf26',completion_credit=0)


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
    """Keep calls separate from subTest failures, fixture errors and explicit skips."""
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
        statuses = list(re.finditer(
            r"^[ \t]*(ok|FAIL|ERROR|skipped (?:'[^\r\n]*'|\"[^\r\n]*\"))[ \t]*\r?$", segment, re.M))
        require(len(statuses) <= 1, 'multiple actual log results: ' + case)
        status = statuses[0] if statuses else None
        subresults = re.findall(r'^[ \t]+' + re.escape(header['test']) +
                               r' \(' + re.escape(case) + r'\) (.+?) \.\.\. (FAIL|ERROR)[ \t]*\r?$',
                               segment, re.M)
        for suffix, outcome in subresults:
            (failures if outcome == 'FAIL' else errors).append(case + ' ' + suffix)
        require(status is not None or subresults, 'missing actual log result: ' + case)
        skipped = status is not None and status[1].startswith('skipped ')
        if skipped:
            require(not subresults and type(ast.literal_eval(status[1][8:])) is str,
                    'invalid skipped log result: ' + case)
        if not subresults and not skipped and status[1] != 'ok':
            (failures if status[1] == 'FAIL' else errors).append(case)
        outcome = (('ERROR' if any(value == 'ERROR' for _, value in subresults) else 'FAIL')
                   if subresults else 'skipped' if skipped else status[1])
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
    epilogue = 'Required packet tests were skipped or expected failures; run remains unverified.'
    unverified = tail.endswith('\n' + epilogue)
    if unverified:
        tail = tail[:-len(epilogue)].rstrip()
    skipped_count = sum(value == 'skipped' for value in cases.values())
    expected = {key: count for key, count in
                (('failures', len(failures)), ('errors', len(errors)), ('skipped', skipped_count)) if count}
    ok = re.search(r'(?:^|\n)OK(?: \(skipped=(\d+)\))?\Z', tail)
    failed = re.search(r'(?:^|\n)FAILED \(((?:failures=\d+|errors=\d+|skipped=\d+)'
                       r'(?:, (?:failures=\d+|errors=\d+|skipped=\d+))*)\)\Z', tail)
    require(ok or failed, 'missing final unittest status')
    if ok:
        observed = {'skipped': int(ok[1])} if ok[1] is not None else {}
        require(observed == expected, 'log OK counts contradict cases')
    else:
        require(bool(failures or errors), 'log FAILED status contradicts cases')
        require(failed[1] == ', '.join(key + '=' + str(count) for key, count in expected.items()),
                'log failure/error/skip counts contradict cases')
    require(unverified == bool(skipped_count), 'skipped log requires exact unverified epilogue')
    passed = bool(ok) and not unverified
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


def ordinary_generated_capture(meta, pre, reads, descriptor, metadata_path, frozen_path):
    """Independently bind source, active-test write/close/read events and archived bytes."""
    require(isinstance(descriptor,dict) and set(descriptor)=={'path','sha256'}, 'explicit full archive descriptor required')
    require(isinstance(descriptor['path'],str) and isinstance(descriptor['sha256'],str) and re.fullmatch(r'[a-f0-9]{64}',descriptor['sha256']), 'invalid generated full archive descriptor')
    outer=Path(descriptor['path'])
    require(outer.is_file() and sha256(outer.read_bytes()).hexdigest()==descriptor['sha256'], 'generated full archive SHA differs')
    rows=meta.get('ordinary_generated_first_reads')
    require(isinstance(rows,list) and bool(rows), 'generated proof rows missing')
    fields={'file','path','mode','test_id','writer_source','writer_source_sha256','writer_function','writer_line',
            'source_frozen_before_import','absent_before_write','write_closed_sha256','sha256','archive_member'}
    open_fields=fields-{'write_closed_sha256','sha256','archive_member'}
    closed_fields=fields-{'sha256','archive_member'}
    root=PureWindowsPath(meta['execution_stage']);proven={}
    with ZipFile(outer) as archive:
        names=archive.namelist()
        require(len(names)==len(set(names)) and 'diagnostic-scope.json' not in names, 'generated acceptance requires unique full evidence, never diagnostics')
        require(archive.read('physical/ci-native.json')==Path(metadata_path).read_bytes(), 'generated metadata differs from original full archive')
        frozen=archive.read('physical/ci-native-inputs.zip')
        require(sha256(frozen).hexdigest()==sha256(Path(frozen_path).read_bytes()).hexdigest(), 'generated frozen archive differs')
        events=[json.loads(line) for line in archive.read('physical/ci-native-events.jsonl').decode('utf-8-sig').splitlines()]
        require(all(isinstance(row,dict) for row in events), 'invalid generated event rows')
        require([row.get('id') for row in events if row.get('event')=='test_start']==meta['actual_test_ids'], 'generated test-start events differ from actual IDs')
        active=None;owners=[]
        for event in events:
            if event.get('event')=='test_start':active=event['id']
            elif event.get('event')=='finished':active=None
            owners.append(active)
        require(len([x for x in events if x.get('event')=='finished'])==1 and events[-1].get('event')=='finished', 'generated event stream did not finish')
        with ZipFile(BytesIO(frozen)) as source_archive:
            for row in rows:
                require(isinstance(row,dict) and set(row)==fields, 'generated proof shape differs')
                require(all(isinstance(row[key],str) for key in fields-{'writer_line','source_frozen_before_import','absent_before_write'}), 'generated proof field types differ')
                key=row['file'];physical=PureWindowsPath(key)
                require(key not in proven and key not in pre and reads.get(key)==row['sha256']==row['write_closed_sha256'], 'generated proof aliases preexisting, duplicate, unknown, or changed input')
                require(isinstance(row['sha256'],str) and re.fullmatch(r'[a-f0-9]{64}',row['sha256']), 'invalid generated SHA')
                require(physical.is_relative_to(root), 'generated input leaves execution stage')
                relative=physical.relative_to(root).as_posix()
                require(relative==row['path'] and '..' not in physical.parts and re.fullmatch(r'work/tmp[^/:\\]+/[^/:\\]+\.(?:json|jsonl|txt|csv|md)',relative), 'unreviewed generated scratch path')
                require(row['mode'] in ('w','wt','wb','x','xt','xb') and row['absent_before_write'] is True and row['source_frozen_before_import'] is True, 'generated creation provenance missing')
                require(row['test_id'] in meta['actual_test_ids'] and type(row['writer_line']) is int, 'generated writer test or line missing')
                module,cls,method=row['test_id'].rsplit('.',2)
                source=PureWindowsPath(row['writer_source']);digest=row['writer_source_sha256']
                require(source.is_relative_to(root) and pre.get(str(source))==digest, 'generated writer source not frozen')
                origin={'file':str(source),'sha256':digest}
                require(all(meta[field].get(module)==origin for field in ('loaded_module_origins_before_execution','loaded_module_origins')), 'generated writer origin differs')
                entry='stage/'+source.relative_to(root).as_posix();body=source_archive.read(entry)
                require(sha256(body).hexdigest()==digest, 'generated writer archived source SHA differs')
                tree=ast.parse(body.decode('utf-8-sig'))
                classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls]
                require(len(classes)==1, 'generated writer class missing or ambiguous')
                methods={n.name:n for n in classes[0].body if isinstance(n,ast.FunctionDef)}
                writer=methods.get(row['writer_function']);test=methods.get(method)
                require(writer is not None and test is not None and writer.lineno<=row['writer_line']<=writer.end_lineno, 'generated writer function/line differs')
                require(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('write_text','write_bytes','open') and n.lineno==row['writer_line'] for n in ast.walk(writer)), 'generated writer line is not a physical write/open')
                require(writer is test or any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='self' and n.func.attr==writer.name for n in ast.walk(test)), 'generated test does not directly call frozen writer')
                ordered=[]
                for kind,keys in [('ordinary_generated_write_open',open_fields),('ordinary_generated_write_closed',closed_fields),('ordinary_generated_first_read',fields)]:
                    matches=[(i,event) for i,event in enumerate(events) if event.get('event')==kind and event.get('file')==key]
                    require(len(matches)==1, 'generated open/close/first-read event missing or repeated')
                    index,event=matches[0]
                    require(set(event)==keys|{'event'} and all(event[k]==row[k] for k in keys) and owners[index]==row['test_id'], 'generated event provenance differs from active writer')
                    ordered.append(index)
                first=[(i,event) for i,event in enumerate(events) if event.get('event')=='first_read' and event.get('file')==key]
                require(len(first)==1, 'generated physical first-read event missing or repeated')
                index,event=first[0]
                require(event.get('sha256')==row['sha256'] and event.get('captured_before') is False and event.get('declared_generated_input') is True and owners[index]==row['test_id'], 'generated physical first-read differs')
                require(ordered==sorted(ordered) and ordered[-1]<index, 'generated write-close/read ordering differs')
                member='physical/ordinary-generated/'+row['sha256']+'.bin'
                require(row['archive_member']==member and sha256(archive.read(member)).hexdigest()==row['sha256'], 'generated archived first-read bytes differ')
                proven[key]=dict(row)
        require(set(proven)==set(reads)-set(pre), 'generated proof does not exactly cover non-preexisting first reads')
        require({x.get('file') for x in events if x.get('event')=='ordinary_generated_first_read'}==set(proven), 'unaccounted generated first-read event')
        require({n for n in names if n.startswith('physical/ordinary-generated/')}=={x['archive_member'] for x in rows}, 'unaccounted generated raw bytes')
    return proven


def extended_ordinary_generated_capture(meta, pre, reads, descriptor, metadata_path, frozen_path):
    """Replay reviewed shadow copy/link and helper-write lifetimes, not producer flags."""
    pins = {'tools/test_category2_csv_timed_type_additions.py':'2f1dacd24178fec1f65aae3c2a94123ef0b61799ae1e19634bdcbf5627e53d09',
            'engine/test_maintenance.py':'364edeed6eb3e748de441e58c6924a614f52ed2c30189f95312f5fbdbe50180f',
            'tools/crosscheck_drafts.py':'cf554f7c08fae37d2ce1fc3e8f780c7323673674b781b7ad2242a05159f99c93'}
    csv_id='tools.test_category2_csv_timed_type_additions.CsvTimedTypeAdditionTests.test_report_collect_adds_exactly_four_denominator_completions'
    report_id='engine.test_maintenance.MaintenanceTests.test_source_resolution_counts_and_partial_coverage'
    require(isinstance(descriptor,dict) and set(descriptor)=={'path','sha256'}, 'extended full archive binding missing')
    outer=Path(descriptor['path'])
    require(outer.is_file() and sha256(outer.read_bytes()).hexdigest()==descriptor['sha256'], 'extended full archive SHA differs')
    require(meta.get('ordinary_extended_generated_errors')==[], 'extended writer did not close cleanly')
    rows=meta.get('ordinary_extended_generated_first_reads')
    require(isinstance(rows,list) and bool(rows), 'extended rows missing')
    root=PureWindowsPath(meta['execution_stage']);proven={};members=set()
    fields={'file','path','policy','test_id','caller_source','caller_source_sha256','caller_function','sha256','archive_member','transitions'}
    base={'file','path','policy','test_id','caller_source','caller_source_sha256','caller_function','writer_source','writer_source_sha256','writer_function','writer_line','operation','mode','existed_before','before_sha256','source_frozen_before_import','source_preimage','phase'}
    with ZipFile(outer) as archive:
        names=archive.namelist()
        require(len(names)==len(set(names)) and 'diagnostic-scope.json' not in names, 'extended proof requires unique full archive, not diagnostics')
        require(archive.read('physical/ci-native.json')==Path(metadata_path).read_bytes(), 'extended raw metadata differs')
        frozen=archive.read('physical/ci-native-inputs.zip')
        require(frozen==Path(frozen_path).read_bytes(), 'extended frozen archive differs')
        events=[json.loads(line) for line in archive.read('physical/ci-native-events.jsonl').decode('utf-8-sig').splitlines()]
        require(all(isinstance(e,dict) for e in events), 'extended event shape differs')
        require([e.get('id') for e in events if e.get('event')=='test_start']==meta['actual_test_ids'], 'extended starts differ')
        require(events[-1].get('event')=='finished' and sum(e.get('event')=='finished' for e in events)==1, 'extended stream not finished')
        active=None;owners=[]
        for event in events:
            if event.get('event')=='test_start':active=event['id']
            if event.get('event')=='finished':active=None
            owners.append(active)
        with ZipFile(BytesIO(frozen)) as source_zip:
            trees={}
            def source(relative):
                require(pre.get(str(root/relative))==pins[relative], 'extended source not frozen at reviewed SHA')
                body=source_zip.read('stage/'+relative)
                require(sha256(body).hexdigest()==pins[relative], 'extended archived source differs')
                if relative not in trees:trees[relative]=ast.parse(body.decode('utf-8-sig'))
                return trees[relative]
            for row in rows:
                require(isinstance(row,dict) and set(row)==fields, 'extended row shape differs')
                key=row['file'];physical=PureWindowsPath(key)
                require(physical.is_relative_to(root) and '..' not in physical.parts and key not in pre and key not in proven, 'extended path is preexisting, duplicate or escaping')
                relative=physical.relative_to(root).as_posix()
                require(relative==row['path'] and reads.get(key)==row['sha256'], 'extended first-read path/SHA differs')
                require(row['test_id'] in meta['actual_test_ids'] and row['test_id'] in (csv_id,report_id), 'extended test not reviewed')
                csv=row['test_id']==csv_id;caller_rel='tools/test_category2_csv_timed_type_additions.py' if csv else 'engine/test_maintenance.py'
                caller=str(root/caller_rel);module,cls,method=row['test_id'].rsplit('.',2)
                require(row['caller_source']==caller and row['caller_source_sha256']==pins[caller_rel] and row['caller_function']==method, 'extended caller binding differs')
                require(all(meta[f].get(module)=={'file':caller,'sha256':pins[caller_rel]} for f in ('loaded_module_origins_before_execution','loaded_module_origins')), 'extended caller origin differs')
                classes=[n for n in source(caller_rel).body if isinstance(n,ast.ClassDef) and n.name==cls]
                require(len(classes)==1, 'extended caller class ambiguous')
                methods=[n for n in classes[0].body if isinstance(n,ast.FunctionDef) and n.name==method]
                require(len(methods)==1, 'extended caller method missing')
                if csv:
                    require(row['policy']=='csv_shadow_copy' and re.fullmatch(r'csv-timed-type-report-[^/:\\]+/(?:input/.+|data/verification/.+)',relative), 'extended shadow outside fixture')
                    original=str(root/PureWindowsPath(*physical.relative_to(root).parts[1:]))
                    require(original in pre, 'extended shadow has no frozen original')
                else:
                    require(row['policy']=='crosscheck_report' and relative in ('output/draft-crosscheck.jsonl','output/draft-crosscheck-resolved.jsonl','output/draft-crosscheck.md'), 'extended output outside contract')
                    require(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='main' for n in ast.walk(methods[0])), 'extended caller does not call helper')
                witnesses=[(i,e) for i,e in enumerate(events) if e.get('event')=='ordinary_extended_generated_first_read' and e.get('file')==key]
                require(len(witnesses)==1, 'extended first read missing/repeated')
                read_index,witness=witnesses[0]
                require(witness==dict(row,event='ordinary_extended_generated_first_read') and owners[read_index]==row['test_id'], 'extended first-read row/owner differs')
                first=[(i,e) for i,e in enumerate(events) if e.get('event')=='first_read' and e.get('file')==key]
                require(len(first)==1 and first[0][0]>read_index and first[0][1].get('sha256')==row['sha256'] and first[0][1].get('captured_before') is False and first[0][1].get('declared_generated_input') is True, 'extended physical first read differs')
                transitions=row['transitions'];require(isinstance(transitions,list) and bool(transitions), 'extended history missing')
                observed=[(i,e) for i,e in enumerate(events[:read_index]) if e.get('file')==key and e.get('event') in ('ordinary_extended_generated_open','ordinary_extended_generated_closed','ordinary_extended_generated_unlinked','ordinary_extended_generated_failed')]
                require([{k:v for k,v in e.items() if k!='event'} for _,e in observed]==transitions and all(owners[i]==row['test_id'] for i,_ in observed), 'extended mutation events/active writer differ')
                current=None;pending=None;ever_closed=False
                for t in transitions:
                    require(isinstance(t,dict) and set(t)==base|({'sha256','archive_member'} if t.get('phase')=='closed' else set()), 'extended transition shape differs')
                    require(all(t[k]==row[k] for k in ('file','path','policy','test_id','caller_source','caller_source_sha256','caller_function')) and t['source_frozen_before_import'] is True, 'extended transition caller differs')
                    writer_rel=caller_rel if csv else 'tools/crosscheck_drafts.py'
                    require(t['writer_source']==str(root/writer_rel) and t['writer_source_sha256']==pins[writer_rel], 'extended writer source differs')
                    writer_tree=source(writer_rel)
                    writer=methods[0] if csv else next(n for n in writer_tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
                    if not csv:require(meta['loaded_module_origins'].get('crosscheck_drafts')=={'file':str(root/writer_rel),'sha256':pins[writer_rel]}, 'extended helper origin differs')
                    require(t['writer_function']==writer.name and type(t['writer_line']) is int and any(isinstance(n,ast.Call) and n.lineno==t['writer_line'] and ((isinstance(n.func,ast.Attribute) and n.func.attr in ('write_text','write_bytes','open','link','unlink')) or isinstance(n.func,ast.Name) and n.func.id=='open') for n in ast.walk(writer)), 'extended writer line not original physical operation')
                    phase=t['phase'];operation=t['operation']
                    operations={'link':('link',),'unlink':('unlink',),'write':('write_text','write_bytes','open')}
                    require(operation in operations and any(isinstance(n,ast.Call) and n.lineno==t['writer_line'] and ((isinstance(n.func,ast.Attribute) and n.func.attr in operations[operation]) or isinstance(n.func,ast.Name) and n.func.id=='open' and operation=='write') for n in ast.walk(writer)), 'extended operation differs from frozen write/link/unlink call')
                    if phase=='open':
                        require(pending is None and operation in (('link','write') if csv else ('write',)), 'extended open invalid')
                        require(t['existed_before'] is (current is not None) and t['before_sha256']==current, 'extended absence/preimage differs')
                        require(operation!='link' or current is None, 'extended link overwrites file')
                        require(operation!='write' or t['mode'] in ('w','wt','wb','x','xt','xb'), 'extended write mode invalid')
                        if csv and (operation=='link' or not ever_closed):
                            require(t['source_preimage']=={'source':original,'source_sha256':pre[original]}, 'extended copy/link source differs')
                            require(sha256(source_zip.read('stage/'+PureWindowsPath(original).relative_to(root).as_posix())).hexdigest()==pre[original], 'extended source preimage bytes differ')
                        else:require(t['source_preimage'] is None, 'extended helper/rewrite invented a source preimage')
                        if ever_closed:require(csv and relative.split('/',1)[1]=='data/verification/category2-csv-abilities-moves-status.json', 'extended rewrite not original registry')
                        pending=t
                    elif phase=='closed':
                        require(pending is not None and all(t[k]==pending[k] for k in base-{'phase'}), 'extended close lacks matching open')
                        member='physical/ordinary-extended-generated/'+t['sha256']+'.bin'
                        require(t['archive_member']==member and sha256(archive.read(member)).hexdigest()==t['sha256'], 'extended raw closed bytes differ')
                        members.add(member)
                        if t['source_preimage'] is not None:require(t['sha256']==t['source_preimage']['source_sha256'], 'extended linked/copied bytes differ')
                        current=t['sha256'];pending=None;ever_closed=True
                    elif phase=='failed':
                        require(pending is not None and operation=='link' and all(t[k]==pending[k] for k in base-{'phase'}), 'extended failed link lacks attempt')
                        pending=None
                    elif phase=='unlinked':
                        require(csv and ever_closed and pending is None and operation=='unlink' and relative.split('/',1)[1]=='data/verification/category2-csv-abilities-moves-status.json' and t['existed_before'] is True and t['before_sha256']==current, 'extended unlink not original registry replacement')
                        current=None
                    else:require(False,'extended phase unknown')
                require(pending is None and current==row['sha256'] and row['archive_member']=='physical/ordinary-extended-generated/'+current+'.bin', 'extended first read is not exact closed bytes')
                proven[key]=dict(row)
        require({e.get('file') for e in events if e.get('event')=='ordinary_extended_generated_first_read'}==set(proven), 'unaccounted extended read')
        require({n for n in names if n.startswith('physical/ordinary-extended-generated/')}==members, 'unaccounted extended raw bytes')
    return proven


def verify_acceptance_evidence(stage, spec, repo_root, *, generated_archives=None):
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
        generated = {}
        extended = {}
        if generated_archives is not None and meta.get('ordinary_extended_generated_first_reads'):
            check(isinstance(generated_archives,dict) and name in generated_archives, 'explicit extended archive binding missing')
            extended = extended_ordinary_generated_capture(meta,pre,reads,generated_archives[name],path(name),path(meta['frozen_inputs']))
        if generated_archives is not None and meta.get('ordinary_generated_first_reads'):
            check(isinstance(generated_archives,dict) and name in generated_archives, 'explicit generated archive binding missing')
            generated = ordinary_generated_capture(meta,pre,{key:value for key,value in reads.items() if key not in extended},generated_archives[name],path(name),path(meta['frozen_inputs']))
        generated.update(extended)
        check(all((key in pre and pre[key] == digest) or (key in generated and generated[key]['sha256']==digest) for key, digest in reads.items()),
              'first-read SHA missing from pre capture')
        check(all(value in reads and '..' not in PureWindowsPath(value).parts for value in missing),
              'missing pre capture path has no physical first-read evidence or is not normalized')
        for field in ('loaded_module_origins_before_execution', 'loaded_module_origins'):
            check(all(origin['file'] in pre and pre[origin['file']] == origin['sha256']
                      for origin in meta[field].values()), field + ' SHA missing from pre capture')
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
                elif captured.is_relative_to(PureWindowsPath(repo_root)):
                    entry = 'canonical/' + captured.relative_to(PureWindowsPath(repo_root)).as_posix()
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
        eligible = not missing or supplement is not None
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
        check(meta.get('exception') is None and meta['successful'] is passed
              and type(meta['exit_code']) is int and (meta['exit_code'] == 0) == passed,
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
                     skip_count=sum(status == 'skipped' for status in cases.values()),
                     skipped_test_ids=[case for case, status in cases.items() if status == 'skipped'],
                     physical_inputs=len(pre), first_reads=len(reads),
                     pre_execution_origins=len(meta['loaded_module_origins_before_execution']),
                     loaded_origins=len(meta['loaded_module_origins']), stable_hashes=True,
                     complete_pre_input_capture=meta['complete_pre_input_capture'], raw_log=meta['raw_log'],
                     input_paths_missing_pre_execution_capture=list(missing),
                     acceptance_eligible=eligible,
                     acceptance_ineligible_reason=None if eligible else 'Incomplete pre-input capture without a valid metadata supplement.',
                     physical_zip=meta['frozen_inputs'])
        if supplement:
            facts.update(prevalidated_metadata_capture=supplement,
                         prevalidated_metadata_input_count=len(supplement['inputs']))
        if generated:
            facts.update(ordinary_generated_input_count=len(generated),ordinary_generated_inputs=generated,
                         generated_full_archive_sha256=generated_archives[name]['sha256'])
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
