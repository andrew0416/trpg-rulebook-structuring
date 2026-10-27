"""Derive current matrix witnesses from pinned independently accepted native runs.

This is a metadata producer/consumer, never a game runner. The historical matrix
and reports are not rewritten. Root freezes this output before the final gate.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import zipfile

REQUIREMENTS = 'data/verification/common-activation-current-requirements.json'
CURRENT = 'data/verification/activation-current-proof/current.json'
SUPPORT = 'data/verification/activation-current-proof/'
# Phase-two transport changes are not reused gameplay inputs. Prewire all
# suites/adapter code before phase one; no other .ci path gets this exception.
NATIVE_ENVELOPE = frozenset(('.ci/source-snapshot.json', '.ci/fixtures-manifest.json', '.ci/fixtures.zip.enc'))

def digest(body):
    return hashlib.sha256(body).hexdigest()

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()

def relative(root, name):
    if not isinstance(name, str) or '\\' in name or ':' in name:
        raise ValueError('unsafe relative input')
    p = PurePosixPath(name)
    if p.is_absolute() or p.as_posix() != name or any(x in ('', '.', '..') for x in p.parts):
        raise ValueError('unsafe relative input')
    result = Path(root) / name
    if result.is_symlink() or not result.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('input leaves candidate')
    return result

def bound_read(reference):
    p = Path(reference['path'])
    body = p.read_bytes()
    if digest(body) != reference['sha256']:
        raise ValueError('pinned reference changed: ' + str(p))
    return body

def read_support(root, reference):
    return bound_read({'path': relative(root, reference['path']), 'sha256': reference['sha256']})

def norm(uid):
    return uid.removeprefix('tools.')

def current_symbols(root, requirements):
    result, parsed = {}, {}
    def walk(nodes, prefix=''):
        for node in nodes:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + node.name
                yield name, node
                yield from walk(node.body, name + '.')
    all_specs = list(requirements['runtime_locators'].values()) + requirements['bounded_support_symbols']
    for row in all_specs:
        name = row['file']
        if name not in parsed:
            parsed[name] = dict(walk(ast.parse(relative(root, name).read_text(encoding='utf-8-sig')).body))
        node = parsed[name].get(row['symbol'])
        if node is None:
            raise ValueError('current runtime symbol missing: ' + name + ':' + row['symbol'])
        observed = digest(ast.dump(node, include_attributes=False).encode())
        expected = row.get('reviewed_AST_sha256', row.get('observed_AST_sha256'))
        if observed != expected:
            raise ValueError('current runtime contract requires re-review: ' + name + ':' + row['symbol'])
        result[name + ':' + row['symbol']] = {'file': name, 'symbol': row['symbol'],
            'start': node.lineno, 'end': node.end_lineno, 'AST_sha256': observed,
            'file_sha256': digest(relative(root, name).read_bytes())}
    return result

def requirements_check(root, spec, requirements):
    history = requirements['historical_matrix']
    if digest(relative(root, history['path']).read_bytes()) != history['sha256']:
        raise ValueError('historical matrix bytes changed')
    original = json.loads(relative(root, history['path']).read_bytes())
    if set(requirements['report_scopes']) != set(original['evidence_catalog']):
        raise ValueError('current proof omits historical report scope')
    expected = set()
    for key, row in requirements['report_scopes'].items():
        required = row['required_native_ids']
        aliases = row['historical_to_native_ids']
        if (len(required) != len(set(required)) or not required
                or set(aliases) != set(original['evidence_catalog'][key]['passing_test_ids'])
                or not set(aliases.values()) <= set(required)):
            raise ValueError('current proof reduces required historical/current IDs')
        expected.update(required)
    if sorted(expected) != requirements['required_native_ids'] or any('common_activation_matrix' in uid for uid in expected):
        raise ValueError('invalid or cyclic current native proof requirements')
    if requirements['source_anchors_unchanged'] != original['source_anchors']:
        raise ValueError('source anchors cannot be refreshed')
    return original

def stage_inputs(root, meta, envelope_bytes):
    before = meta['runtime_test_data_sha256_before']
    if not before or before != meta['runtime_test_data_sha256_after'] or meta.get('stable_hashes') is not True:
        raise ValueError('native inputs changed')
    stage = PureWindowsPath(meta['execution_stage'])
    inputs, envelope = {}, {}
    for name, expected in before.items():
        physical = PureWindowsPath(name)
        if not physical.is_relative_to(stage):
            # Independently H-validated external tooling is not candidate code.
            continue
        rel = physical.relative_to(stage).as_posix()
        current = digest(relative(root, rel).read_bytes())
        if rel in NATIVE_ENVELOPE:
            if rel not in envelope_bytes or digest(envelope_bytes[rel]) != expected:
                raise ValueError('original native envelope is missing or changed: ' + rel)
            if current != expected:
                # Even a transport path is a gameplay dependency if native code
                # read it. Such a witness cannot migrate unchanged to phase two.
                if ('actual_read_paths' not in meta or 'first_actual_read_sha256' not in meta
                        or name in meta['actual_read_paths'] or name in meta['first_actual_read_sha256']):
                    raise ValueError('changed native-read envelope input: ' + rel)
            envelope[rel] = expected
            continue
        if current != expected:
            raise ValueError('native candidate input differs: ' + rel)
        inputs[rel] = expected
    if set(envelope_bytes) != set(envelope):
        raise ValueError('unknown or unbound native envelope reference')
    if envelope and set(envelope) != NATIVE_ENVELOPE:
        raise ValueError('partial native envelope capture')
    if not inputs:
        raise ValueError('no frozen candidate inputs')
    for field in ('loaded_module_origins_before_execution', 'loaded_module_origins'):
        if any(before.get(v['file']) != v['sha256'] for v in meta[field].values()):
            raise ValueError('native source origin not frozen')
    return inputs, envelope

def accepted_native(root, requirements, cache, collector, run_id, metadata_reader):
    """H authenticates execution; rebind its exact native IDs/bytes to this candidate."""
    wanted = set(requirements['required_native_ids'])
    statuses, inputs, runs, typed_ids, envelopes = {}, {}, [], set(), {}
    invocations = [(key, saved, False) for key, saved in cache.get('executions', {}).items()]
    invocations += [(key, saved, True) for key, saved in cache.get('typed_executions', {}).items()]
    for key, saved, typed in sorted(invocations, key=lambda row: (row[0], row[2])):
        if not key.startswith(str(run_id) + '/'):
            continue
        facts = saved['facts']
        if typed:
            verified = facts['equivalence_verified_method_ids']
            if (facts.get('execution_kind') != 'frequency_equivalence_gate'
                    or facts.get('typed_status') != 'equivalent' or type(facts.get('ordinary_test_pass_credit')) is not int
                    or facts['ordinary_test_pass_credit'] != 0
                    or len(verified) != len(set(verified)) or 'validated_actual_statuses' in saved):
                raise ValueError('typed equivalence is not ordinary native PASS')
            seen = wanted.intersection(verified)
        else:
            seen = {uid for uid in wanted if norm(uid) in saved.get('validated_actual_statuses', {})}
        if not seen:
            continue
        entry = collector['executions'].get(key, {})
        full_hash = entry.get('original_archive_sha256')
        if not isinstance(full_hash, str) or len(full_hash) != 64 or full_hash != saved['archive_sha256']:
            raise ValueError('collector full archive binding missing or changed: ' + key)
        if facts.get('mode') != 'physical' or not facts.get('runs'):
            raise ValueError('independent H physical acceptance missing: ' + key)
        physical_facts = facts['runs']
        if len(physical_facts) != 1:
            raise ValueError('one exact physical invocation per execution key required')
        fact = physical_facts[0]
        if fact.get('acceptance_eligible') is not True or fact.get('stable_hashes') is not True:
            raise ValueError('H rejected physical eligibility: ' + key)
        if fact.get('ordinary_generated_input_count') and fact.get('generated_full_archive_sha256') != full_hash:
            raise ValueError('generated first-read archive not collector bound')
        body, extras = metadata_reader(key, saved, entry)
        if digest(body) != fact['metadata_sha256']:
            raise ValueError('raw metadata differs from H accepted metadata')
        if digest(extras['raw_log']) != fact['raw_log_sha256']:
            raise ValueError('raw outcomes differ from H accepted raw log')
        meta = json.loads(body)
        if datetime.fromisoformat(meta['started_utc']) > datetime.fromisoformat(meta['finished_utc']):
            raise ValueError('native invocation unfinished or reversed')
        local, envelope = stage_inputs(root, meta, extras['native_envelope'])
        for rel, h in envelope.items():
            if rel in envelopes and envelopes[rel] != h:
                raise ValueError('native proof mixes original envelopes: ' + rel)
            envelopes[rel] = h
        for rel, h in local.items():
            if rel in inputs and inputs[rel] != h:
                raise ValueError('native proof mixes candidate inputs: ' + rel)
            inputs[rel] = h
        if typed != (meta.get('execution_kind') == 'frequency_equivalence_gate'):
            raise ValueError('typed execution stored as ordinary PASS or wrong execution kind')
        if typed:
            equivalent = json.loads(extras['frequency'])
            if digest(extras['frequency']) != meta['equivalence_report_sha256']:
                raise ValueError('frequency raw report changed')
            if equivalent.get('status') != 'equivalent' or equivalent.get('blocking_check_passed') is not True:
                raise ValueError('frequency cold/connected/negative equivalence incomplete')
            actual = set(equivalent['expected_ids'])
            if (set(verified) != actual or type(meta.get('ordinary_test_pass_credit')) is not int
                    or meta['ordinary_test_pass_credit'] != 0):
                raise ValueError('H typed accepted IDs differ from raw equivalence scope')
            if (len(equivalent['expected_ids']) != len(actual)
                    or equivalent['expected_method_count'] != len(actual)
                    or equivalent['mismatched_assertion_traces'] or equivalent['unknown_observation_types']):
                raise ValueError('frequency assertion trace comparison incomplete')
            for mode in ('cold', 'connected'):
                row = equivalent['outcomes'][mode]
                if (len(row['started_ids']) != len(actual) or set(row['started_ids']) != actual
                        or row['finished_ids'] != row['started_ids']
                        or row['testsRun'] != len(actual)
                        or any(row[k] for k in ('failures', 'errors', 'skipped', 'never_started_ids'))):
                    raise ValueError('frequency native bodies incomplete')
            negative = equivalent['outcomes']['connected_first_failure']
            injection = 'tools.test_frequencies.FrequencyTests.test_source_move_0000'
            blocked = equivalent['expected_blocked_after_injection']
            if (set(negative['started_ids']) != actual or len(negative['started_ids']) != len(actual)
                    or negative['finished_ids'] != negative['started_ids'] or negative['testsRun'] != len(actual)
                    or negative['errors'] or negative['never_started_ids']
                    or len(negative['failures']) != 1 or negative['failures'][0][0] != injection
                    or 'INJECTED_FREQUENCY_CHAIN_FAILURE_AFTER_ORIGINAL_BODY' not in negative['failures'][0][1]
                    or len(blocked) != len(set(blocked)) or not set(blocked) <= actual - {injection}
                    or negative['blocked_body_ids'] != blocked
                    or [row[0] for row in negative['skipped']] != blocked):
                raise ValueError('frequency deliberate failure/blocking proof incomplete')
        else:
            actual_list = meta['actual_test_ids']
            if len(actual_list) != len(set(actual_list)) or meta.get('exception') is not None:
                raise ValueError('duplicate or interrupted actual native IDs')
            if actual_list != fact['actual_test_ids']:
                raise ValueError('raw actual IDs differ from H accepted invocation')
            actual = set(actual_list)
            timings = meta.get('method_timings', [])
            observed = {row['id'] for row in timings if type(row.get('seconds')) in (int, float)
                        and math.isfinite(row['seconds']) and row['seconds'] >= 0}
            if not seen <= observed or any(sum(row['id'] == uid for row in timings) != 1 for uid in seen):
                raise ValueError('native method timing/completion evidence missing')
            if seen.intersection(meta['failure_ids'] + meta['error_ids']):
                raise ValueError('required current native method failed')
        if not seen <= actual or (not typed and any(saved['validated_actual_statuses'].get(norm(uid)) != 'ok' for uid in seen)):
            raise ValueError('required native ID lacks H-validated actual PASS')
        if typed:
            typed_ids.update(seen)
        for uid in seen:
            if uid in statuses:
                raise ValueError('ambiguous repeated execution for required native ID')
            statuses[uid] = key
        runs.append({'execution': key, 'archive_sha256': full_hash, 'metadata_sha256': digest(body),
                     'required_actual_ids': sorted(seen), 'started_utc': meta['started_utc'],
                     'finished_utc': meta['finished_utc'], 'raw_log_sha256': fact['raw_log_sha256'],
                     'execution_kind': 'frequency_equivalence_gate' if typed else 'ordinary',
                     'ordinary_test_pass_credit': 0 if typed else len(seen)})
    if set(statuses) != wanted:
        raise ValueError('current H accepted methods missing: ' + ','.join(sorted(wanted - set(statuses))[:8]))
    for row in requirements['report_scopes'].values():
        if row['producer_source'] not in inputs:
            raise ValueError('native test source SHA missing: ' + row['producer_source'])
    for name in (REQUIREMENTS, 'tools/activation_current_evidence.py',
                 'tools/audit_common_activation_matrix.py', requirements['historical_matrix']['path']):
        if name not in inputs:
            raise ValueError('current proof contract/consumer was not frozen before native execution: ' + name)
    reviewed_files = {row['file'] for row in requirements['runtime_locators'].values()}
    reviewed_files.update(row['file'] for row in requirements['bounded_support_symbols'])
    reviewed_files.update(row['file'] for row in requirements['source_anchors_unchanged'])
    if not reviewed_files <= inputs.keys():
        raise ValueError('reviewed current runtime/source-anchor bytes missing from native pre-capture')
    return {'method_executions': statuses, 'input_hashes': inputs, 'runs': runs,
            'native_envelope_hashes': envelopes,
            'ordinary_pass_ids': sorted(wanted - typed_ids), 'typed_equivalence_ids': sorted(typed_ids)}

def current_report(scope, accepted):
    typed = set(accepted['typed_equivalence_ids'])
    ids = scope['required_native_ids']
    return {'required_native_ids': ids, 'historical_to_native_ids': scope['historical_to_native_ids'],
            'ordinary_test_pass_credit': len(set(ids) - typed),
            'typed_equivalence_method_count': len(set(ids) & typed),
            'results': [{'id': uid, 'status': 'equivalent' if uid in typed else 'pass',
                         'execution': accepted['method_executions'][uid]} for uid in ids]}

def verify_phase_two_inputs(native, current_inputs, derived_paths):
    """Root calls this on the authenticated freeze map before metadata import."""
    before = dict(native['input_hashes'])
    before.update(native['native_envelope_hashes'])
    if not before.keys() <= current_inputs.keys():
        raise ValueError('phase two drops a native frozen input')
    if any(current_inputs[path] != h for path, h in before.items() if path not in NATIVE_ENVELOPE):
        raise ValueError('phase two changes native base source/data or prewired controls')
    added = current_inputs.keys() - before.keys()
    if added != set(derived_paths) - before.keys():
        raise ValueError('phase two adds non-proof inputs or omits derived raw evidence')
    return {'status': 'fixed_three_envelope_only', 'base_source_input_count': len(native['input_hashes']),
            'changed_envelope_paths': sorted(path for path in NATIVE_ENVELOPE if path in before and current_inputs[path] != before[path]),
            'added_derived_paths': sorted(added)}

def derive(root, cache_reference, collector_reference, run_id):
    root = Path(root)
    requirements_body = relative(root, REQUIREMENTS).read_bytes()
    requirements = json.loads(requirements_body)
    spec = requirements_check(root, None, requirements)
    symbols = current_symbols(root, requirements)
    cache_body, collector_body = bound_read(cache_reference), bound_read(collector_reference)
    if Path(cache_reference['path']).name != 'physical-evidence-' + digest(cache_body) + '.json':
        raise ValueError('immutable H physical-evidence SHA reference required')
    cache, collector = json.loads(cache_body), json.loads(collector_body)
    copies = {}
    def support(name, body):
        path = SUPPORT + name
        copies[path] = body
        return {'path': path, 'sha256': digest(body)}
    cache_ref = support('H-accepted.json', cache_body)
    collector_ref = support('collector.json', collector_body)
    metadata_refs, envelope_refs = {}, {}
    def archived(key, saved, entry):
        archive = Path(saved['archive'])
        if str(archive) != entry['original_archive'] or digest(archive.read_bytes()) != saved['archive_sha256']:
            raise ValueError('exact full native archive differs from pinned H/collector')
        with zipfile.ZipFile(archive) as z:
            body = z.read('physical/ci-native.json')
            meta = json.loads(body)
            extras = {}
            record = {'metadata': support(digest(body) + '-metadata.json', body)}
            extras['raw_log'] = z.read('physical/ci-native.log')
            record['raw_log'] = support(digest(extras['raw_log']) + '-raw-log.txt', extras['raw_log'])
            frozen = z.read('physical/ci-native-inputs.zip')
            fact = saved['facts']['runs'][0]
            if digest(frozen) != fact.get('frozen_inputs_sha256', fact.get('archive_sha256')):
                raise ValueError('original physical input ZIP differs from H acceptance')
            extras['native_envelope'] = {}
            with zipfile.ZipFile(io.BytesIO(frozen)) as captured:
                stage = PureWindowsPath(meta['execution_stage'])
                for rel in sorted(NATIVE_ENVELOPE):
                    name = str(stage / rel)
                    expected = meta['runtime_test_data_sha256_before'].get(name)
                    if expected is None:
                        continue
                    original = captured.read('stage/' + rel)
                    if digest(original) != expected:
                        raise ValueError('archived native envelope differs from pre-capture: ' + rel)
                    ref = support(digest(original) + '-native-envelope.bin', original)
                    if rel in envelope_refs and envelope_refs[rel] != ref:
                        raise ValueError('native invocations have different original envelopes')
                    envelope_refs[rel] = ref
                    extras['native_envelope'][rel] = original
            if meta.get('execution_kind') == 'frequency_equivalence_gate':
                extras['frequency'] = z.read('physical/frequency-equivalence.json')
                record['frequency'] = support(digest(extras['frequency']) + '-frequency.json', extras['frequency'])
            metadata_refs[key] = record
            return body, extras
    accepted = accepted_native(root, requirements, cache, collector, run_id, archived)
    reports = {}
    for key, row in requirements['report_scopes'].items():
        reports[key] = current_report(row, accepted)
    proof = {'schema_version': 2, 'kind': 'H_accepted_current_activation_derivation', 'run': str(run_id),
        'requirements_sha256': digest(requirements_body), 'historical_matrix': requirements['historical_matrix'],
        'H_accepted_reference': cache_ref, 'collector_reference': collector_ref,
        'original_H_reference': cache_reference, 'original_collector_reference': collector_reference,
        'raw_metadata_references': metadata_refs, 'native_envelope_references': envelope_refs,
        'native': accepted, 'reports': reports,
        'current_runtime_symbols': symbols, 'game_runs_by_this_producer': 0, 'completion_credit': 0}
    copies[CURRENT] = encoded(proof)
    return proof, copies

def validate_current(root, spec):
    """Return explicit errors; never fall back to old PASS or silently rebase hashes."""
    errors = []
    try:
        requirement_bytes = relative(root, REQUIREMENTS).read_bytes()
        requirements = json.loads(requirement_bytes)
        original = requirements_check(root, spec, requirements)
        for condition in spec.get('conditions', []):
            old = requirements['historical_runtime_references'].get(condition.get('id'))
            if old is not None and condition.get('runtime_paths', []) != old:
                errors.append('runtime_excerpt_drift:' + condition['id'])
        symbols = current_symbols(root, requirements)
        proof = json.loads(relative(root, CURRENT).read_bytes())
        if (type(proof.get('schema_version')) is not int or proof['schema_version'] != 2
                or proof.get('kind') != 'H_accepted_current_activation_derivation'
                or proof.get('requirements_sha256') != digest(requirement_bytes)
                or proof.get('historical_matrix') != requirements['historical_matrix']):
            raise ValueError('current derivation schema/input binding differs')
        if proof.get('current_runtime_symbols') != symbols:
            raise ValueError('current runtime location or source bytes changed')
        cache = json.loads(read_support(root, proof['H_accepted_reference']))
        collector = json.loads(read_support(root, proof['collector_reference']))
        if (proof['original_H_reference']['sha256'] != proof['H_accepted_reference']['sha256']
                or Path(proof['original_H_reference']['path']).name != 'physical-evidence-' + proof['H_accepted_reference']['sha256'] + '.json'
                or proof['original_collector_reference']['sha256'] != proof['collector_reference']['sha256']):
            raise ValueError('derived support does not preserve pinned independent H/collector references')
        def frozen_metadata(key, saved, entry):
            record = proof['raw_metadata_references'][key]
            envelope = proof['native_envelope_references']
            if not set(envelope) <= NATIVE_ENVELOPE:
                raise ValueError('native envelope scope is not the fixed three controls')
            extras = {'raw_log': read_support(root, record['raw_log']),
                'native_envelope': {rel: read_support(root, ref) for rel, ref in envelope.items()}}
            if 'frequency' in record:
                extras['frequency'] = read_support(root, record['frequency'])
            return read_support(root, record['metadata']), extras
        accepted = accepted_native(root, requirements, cache, collector, proof['run'], frozen_metadata)
        if accepted != proof['native'] or set(proof['reports']) != set(requirements['report_scopes']):
            raise ValueError('derived actual evidence differs from accepted native facts')
        for key, scope in requirements['report_scopes'].items():
            wanted = current_report(scope, accepted)
            if proof['reports'][key] != wanted:
                raise ValueError('current report scope reduced or fabricated: ' + key)
        if any(type(proof.get(field)) is not int or proof[field] != 0 for field in ('game_runs_by_this_producer', 'completion_credit')):
            raise ValueError('derivation cannot claim executions or clause credit')
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, SyntaxError) as exc:
        errors.append('current_activation_evidence_unavailable_or_invalid:' + str(exc))
    return sorted(set(errors))

def proof_input_paths(root):
    try:
        proof = json.loads(relative(root, CURRENT).read_bytes())
        references = [proof['H_accepted_reference'], proof['collector_reference']]
        references += [ref for row in proof['raw_metadata_references'].values() for ref in row.values()]
        references += list(proof['native_envelope_references'].values())
        return [CURRENT] + sorted({ref['path'] for ref in references})
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return [CURRENT]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--H-reference', type=Path, required=True)
    parser.add_argument('--H-sha256', required=True)
    parser.add_argument('--collector-reference', type=Path, required=True)
    parser.add_argument('--collector-sha256', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    if args.destination.resolve().is_relative_to(args.root.resolve()) or args.destination.exists():
        raise ValueError('new output directory outside immutable candidate required')
    proof, copies = derive(args.root, {'path': str(args.H_reference), 'sha256': args.H_sha256},
        {'path': str(args.collector_reference), 'sha256': args.collector_sha256}, args.run)
    for name, body in copies.items():
        dest = relative(args.destination, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream:
            stream.write(body)
    print(json.dumps({'status': 'derived_from_pinned_H_evidence', 'run': proof['run'],
        'required_actual_methods': len(proof['native']['method_executions']), 'outputs': len(copies),
        'current_manifest_sha256': digest(copies[CURRENT]), 'game_runs': 0, 'completion_credit': 0}))

if __name__ == '__main__':
    main()
