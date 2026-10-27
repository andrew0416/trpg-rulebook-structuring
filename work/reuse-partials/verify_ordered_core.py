"""Verify a staged ordered core/class publication without changing canonical files."""
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
from urllib.parse import unquote
from audit_vault_quality import audit as audit_quality
from acceptance_evidence import verify_acceptance_evidence
import argparse, ast, json, posixpath, re, sys
from reconcile_batch import candidate_file_path, validate_candidate_metadata, validate_candidate_shape, REGISTRIES, registry_included, registry_status, shared_feature_count, new_shared_feature_records, resolve_shared_feature_consumers


# Publication checks compare reviewed bytes and bookkeeping; they do not accept rules.
_PUBLICATION_PROGRESS = 'data/verification/category2-progress.json'
_PUBLICATION_FREEZE = 'data/verification/category2-scope-freeze.json'
_PUBLICATION_FIXED = ('engine/world_entities.py', 'work/reuse-partials/verify_overlay_tests.py')
_PUBLICATION_METADATA = frozenset((
    'status', 'category2_status', 'category2_implemented', 'field_authority',
    'producers', 'consumers', 'producer', 'consumer', 'tests',
    'canonical_state_references', 'evidence_scope', 'completion_evidence',
    'verified_at', 'implementation_evidence', 'test_evidence', 'validation_result',
    'category2_obligations', 'remaining', 'completion_credit',
    'field_authority_evidence', 'reused_test_ids', 'retained_verification',
    'completed_clause_verification',
))


def _publication_require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _publication_digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')).encode('utf8')).hexdigest()


def _publication_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _publication_hash(path):
    return sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _publication_name(name, root):
    return candidate_file_path(name, 'publication', root).as_posix()


def _publication_baseline(stage, root):
    baseline = _publication_json(stage/'baseline.json')
    _publication_require(isinstance(baseline, dict), 'baseline must be a flat dictionary')
    for name, value in baseline.items():
        _publication_require(_publication_name(name, root) == name,
                             'baseline path must be normalized: '+str(name))
        _publication_require(value is None or isinstance(value, str) and
                             re.fullmatch('[a-f0-9]{64}', value) is not None,
                             'baseline must map paths to SHA256 or null: '+name)
    return baseline


def _publication_protected(root, names):
    paths = {path.relative_to(root).as_posix()
             for folder in ('engine', 'tools') for path in (root/folder).glob('*.py')
             if path.is_file()}
    paths = {name for name in paths if name.casefold() not in {item.casefold() for item in names}}
    paths.update(_PUBLICATION_FIXED)
    result = {name: _publication_hash(root/name) for name in sorted(paths)}
    _publication_require(all(result.values()), 'missing protected Python input')
    return result


def _publication_source_part(row, child=False):
    ignored = {'status', 'evidence', 'implementation_verified'} if child else _PUBLICATION_METADATA
    result = {key: value for key, value in row.items() if key not in ignored}
    if 'children' in result:
        result['children'] = [_publication_source_part(value, True)
                              for value in result['children']]
    return result


def _publication_reporter(root):
    from importlib.util import module_from_spec, spec_from_file_location
    module_spec = spec_from_file_location('_publication_reporter',
                                          root/'tools/report_category2_progress.py')
    module = module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _publication_snapshot(root, reporter, stage=None, names=()):
    original_text, original_bytes = Path.read_text, Path.read_bytes
    original_file, original_exists = Path.is_file, Path.exists
    declared_names = {name.casefold(): name for name in names}
    def overlay(path):
        if stage is not None and path.is_relative_to(root):
            name = path.relative_to(root).as_posix()
            if name.casefold() in declared_names:
                return stage/declared_names[name.casefold()]
        return path
    with patch.object(Path, 'read_text', lambda p, *a, **k: original_text(overlay(p), *a, **k)), \
         patch.object(Path, 'read_bytes', lambda p: original_bytes(overlay(p))), \
         patch.object(Path, 'is_file', lambda p: original_file(overlay(p))), \
         patch.object(Path, 'exists', lambda p: original_exists(overlay(p))):
        report = reporter.collect(root)
        _publication_require(not report['validation_errors'] and
                             not report['edge_reuse_inspection'].get('validation_errors'),
                             'report validation errors: '+str(report['validation_errors']))
        _publication_require(report['denominator_frozen'] and report['denominator'] == 2352,
                             'frozen denominator must remain 2352')
        reuse = report['edge_reuse_inspection']
        _publication_require(reuse['completed'] == reuse['denominator'], 'reuse evidence pending')
        _publication_require(report == _publication_json(root/_PUBLICATION_PROGRESS),
                             'canonical collect differs from saved progress')
        rows, included, files = {}, set(), {}
        for group, filename, rows_key in reporter.SOURCES:
            adapter, identity_key = next(((key, value[2]) for key, value in REGISTRIES.items()
                                         if value[0] == filename), ('core-additional', 'clause_id'))
            name = 'data/verification/'+filename
            document = _publication_json(root/name)
            files[name] = _publication_hash(root/name)
            _publication_require(files[name] == report['groups'][group]['registry_sha256'],
                                 'registry changed during collect: '+name)
            for row in document[rows_key]:
                uid = row.get(identity_key) or row['id']
                _publication_require(uid not in rows, 'duplicate registry identity: '+uid)
                member = registry_included(row, adapter)
                if group == 'csv-abilities-moves':
                    member = member and row['denominator_contribution'] == 1
                rows[uid] = (group, row, registry_status(row, adapter))
                if member:
                    included.add(uid)
        _publication_require(len(rows) == 6080, 'registry must contain exactly 6080 unique rows')
        _publication_require(sorted(included) == report['included_clause_ids'] and len(included) == 2352,
                             'registry adapters differ from frozen included IDs')
        freeze = _publication_json(root/_PUBLICATION_FREEZE)
        refs = [*freeze['source_manifest'], *freeze.get('reference_only_sources', [])]
        inputs = {ref['file']: _publication_hash(root/ref['file']) for ref in refs}
        _publication_require(len(inputs) == len(refs) == 40, 'saved input inventory must remain 40')
        files.update({name: _publication_hash(root/name)
                      for name in (_PUBLICATION_FREEZE, _PUBLICATION_PROGRESS)})
        return dict(report=report, rows=rows, included=included, inputs=inputs, files=files,
                    freeze=_publication_hash(root/_PUBLICATION_FREEZE))


def _publication_row_hashes(snapshot, omit=()):
    return {uid: _publication_digest([group, row])
            for uid, (group, row, _) in snapshot['rows'].items() if uid not in omit}


def _publication_source_hash(snapshot):
    return _publication_digest({uid: [group, _publication_source_part(row)]
                                for uid, (group, row, _) in snapshot['rows'].items()})


def publication_check(stage, candidate, artifact_manifest, repo_root, *, pre_record=None):
    """Read only; returns a pre/post record for Root's existing publication records."""
    stage, root = Path(stage).resolve(), Path(repo_root).resolve()
    _publication_require(stage != root, 'publication stage and repo root must differ')
    candidate = (stage/candidate).resolve()
    artifact_manifest = (stage/artifact_manifest).resolve()
    spec = _publication_json(candidate)
    names = _publication_json(artifact_manifest)
    _publication_require(isinstance(names, list) and bool(names), 'artifact manifest must be a nonempty list')
    names = [_publication_name(name, stage) for name in names]
    _publication_require(len(names) == len({name.casefold() for name in names}),
                         'artifact names must be unique')
    for name in names:
        _publication_name(name, root)
        _publication_require((stage/name).is_file(), 'missing staged artifact: '+name)
    _publication_require(not {name.casefold() for name in names}.intersection(
                         name.casefold() for name in _PUBLICATION_FIXED),
                         'World and native runner cannot be publication artifacts')
    artifact_hashes = {name: _publication_hash(stage/name) for name in names}
    baseline = _publication_baseline(stage, root)
    baseline_hash = _publication_hash(stage/'baseline.json')
    _publication_require(set(names) <= baseline.keys(), 'artifact missing baseline entry')
    reporter_path = root/'tools/report_category2_progress.py'
    reporter_hash = _publication_hash(reporter_path)
    if 'tools/report_category2_progress.py' in names:
        _publication_require(artifact_hashes['tools/report_category2_progress.py'] == reporter_hash,
                             'publication checker cannot change its reporter')
    pins = dict(candidate_sha256=_publication_hash(candidate),
                artifact_manifest_sha256=_publication_hash(artifact_manifest),
                artifacts=artifact_hashes, reporter_sha256=reporter_hash)
    def stable_inputs(phase, snapshot):
        _publication_require(_publication_hash(candidate) == pins['candidate_sha256'] and
                             _publication_hash(artifact_manifest) == pins['artifact_manifest_sha256'] and
                             _publication_hash(reporter_path) == pins['reporter_sha256'] and
                             all(_publication_hash(stage/name) == expected
                                 for name, expected in artifact_hashes.items()) and
                             _publication_hash(stage/'baseline.json') == baseline_hash and
                             _publication_json(stage/'baseline.json') == baseline,
                             'publication inputs changed during '+phase)
        _publication_require(all(_publication_hash(root/name) == expected
                                 for name, expected in {**snapshot['files'], **snapshot['inputs']}.items()),
                             'canonical inputs changed during '+phase)
    reporter = _publication_reporter(root)
    ids = set(spec['completed'])
    if pre_record is None:
        validate_candidate_metadata(spec, repo_root=root, stage=stage)
        for name, expected in baseline.items():
            _publication_require(_publication_hash(root/name) == expected,
                                 'concurrent baseline change: '+name)
        protected = _publication_protected(root, names)
        before = _publication_snapshot(root, reporter)
        projected = _publication_snapshot(root, reporter, stage, set(names))
        _publication_require(spec['completed_before'] == before['report']['completed_clause_count'],
                             'candidate completed_before differs from current canonical report')
        _publication_require(before['rows'].keys() == projected['rows'].keys(),
                             'registry identity set changed')
        changed = {uid for uid in before['rows'] if before['rows'][uid] != projected['rows'][uid]}
        _publication_require(changed == ids, 'registry changes differ from exact completed targets')
        _publication_require(before['included'] == projected['included'] and
                             before['freeze'] == projected['freeze'] and
                             before['inputs'] == projected['inputs'],
                             'source inputs, freeze or included IDs changed')
        _publication_require(_publication_source_hash(before) == _publication_source_hash(projected),
                             'source/include/dedupe fields changed')
        _publication_require(all(uid in before['included'] and before['rows'][uid][2] != 'implemented'
                                 and projected['rows'][uid][2] == 'implemented' for uid in ids),
                             'target completion status transition is not incomplete to implemented')
        _publication_require(projected['report']['completed_clause_count'] ==
                             spec['completed_before'] + len(ids), 'completion delta differs from exact targets')
        _publication_require(_publication_protected(root, names) == protected,
                             'protected Python changed during pre-check')
        for name, expected in baseline.items():
            _publication_require(_publication_hash(root/name) == expected,
                                 'baseline changed during pre-check: '+name)
        stable_inputs('pre-check', before)
        result = dict(schema_version=1, mode='publication_pre', status='prepublication_gate_pass',
                      repo_root=str(root), stage=str(stage), before=spec['completed_before'],
                      after=projected['report']['completed_clause_count'], denominator=2352,
                      exact_ids=sorted(ids), registry_rows=6080, non_target_unchanged=6080-len(ids),
                      artifact_count=len(names), metadata_preflight='existing_W_pass',
                      pins=pins, baseline_sha256=baseline_hash, preimages=baseline, protected=protected,
                      projected_report_sha256=_publication_digest(projected['report']),
                      projected_rows_sha256=_publication_digest(_publication_row_hashes(projected)),
                      non_target_rows_sha256=_publication_digest(_publication_row_hashes(projected, ids)),
                      source_scope_sha256=_publication_source_hash(projected),
                      included_ids_sha256=_publication_digest(sorted(projected['included'])),
                      source_inputs=projected['inputs'], frozen_scope_sha256=projected['freeze'])
    else:
        pre_path = (stage/pre_record).resolve()
        pre = _publication_json(pre_path)
        _publication_require(pre.get('schema_version') == 1 and pre.get('mode') == 'publication_pre'
                             and pre.get('status') == 'prepublication_gate_pass',
                             'post-check requires a complete publication_pre record; legacy summaries are not sufficient')
        _publication_require(pre['repo_root'] == str(root) and pre['stage'] == str(stage)
                             and pre['pins'] == pins and pre['exact_ids'] == sorted(ids),
                             'pre record roots, candidate, manifest, artifacts or reporter changed')
        for name, expected in artifact_hashes.items():
            _publication_require(_publication_hash(root/name) == expected,
                                 'canonical artifact differs from accepted stage: '+name)
        _publication_require(_publication_protected(root, names) == pre['protected'],
                             'protected Python set or bytes changed')
        for name, expected in pre['preimages'].items():
            if name not in names:
                _publication_require(_publication_hash(root/name) == expected,
                                     'nonpublication preimage changed: '+name)
        published_baseline = dict(pre['preimages'], **artifact_hashes)
        _publication_require(baseline in (pre['preimages'], published_baseline),
                             'publisher baseline changed outside exact artifact hashes')
        current = _publication_snapshot(root, reporter)
        _publication_require(current['report']['completed_clause_count'] == pre['after']
                             and pre['after']-pre['before'] == len(ids), 'post completion delta differs')
        for actual, expected, label in (
            (_publication_digest(current['report']), pre['projected_report_sha256'], 'report'),
            (_publication_digest(_publication_row_hashes(current)), pre['projected_rows_sha256'], 'all registry rows'),
            (_publication_digest(_publication_row_hashes(current, ids)), pre['non_target_rows_sha256'], 'non-target rows'),
            (_publication_source_hash(current), pre['source_scope_sha256'], 'source/include/dedupe fields'),
            (_publication_digest(sorted(current['included'])), pre['included_ids_sha256'], 'included IDs'),
            (current['inputs'], pre['source_inputs'], 'source input bytes'),
            (current['freeze'], pre['frozen_scope_sha256'], 'scope freeze'),
        ):
            _publication_require(actual == expected, 'post-check changed '+label)
        stable_inputs('post-check', current)
        _publication_require(_publication_protected(root, names) == pre['protected'] and
                             all(_publication_hash(root/name) == expected
                                 for name, expected in published_baseline.items()),
                             'protected Python or preimages changed during post-check')
        result = dict(schema_version=1, mode='publication_post', status='published_postgate_pass',
                      before=pre['before'], after=pre['after'], denominator=2352, exact_ids=sorted(ids),
                      registry_rows=6080, non_target_unchanged=6080-len(ids),
                      published_artifacts=len(names), protected_count=len(pre['protected']),
                      pins=pins, pre_record_sha256=_publication_hash(pre_path))
    result.update(protected_count=len(protected) if pre_record is None else len(pre['protected']),
                  root_new_game_runs=0, authority='read_only_byte_and_bookkeeping_check_not_acceptance')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',type=Path)
    parser.add_argument('--repo-root',type=Path,default=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment'))
    parser.add_argument('--published',action='store_true')
    parser.add_argument('--publication-check',choices=('pre','post'))
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--artifact-manifest',type=Path)
    parser.add_argument('--publication-pre',type=Path)
    parser.add_argument('--report',type=Path,help='create a new UTF-8 publication-check result inside stage; never overwrite')
    parser.add_argument('--evidence-only',action='store_true',help='check referenced input/run evidence before finalization; no game execution')
    args=parser.parse_args();S=args.stage.resolve();R=args.repo_root.resolve()
    if args.publication_check:
        if not any(value == '--repo-root' or value.startswith('--repo-root=') for value in sys.argv[1:]):
            parser.error('--repo-root is required for publication checks')
        if args.evidence_only or args.published or not args.artifact_manifest:
            parser.error('publication checks require --artifact-manifest and cannot combine legacy modes')
        if (args.publication_check == 'post') != bool(args.publication_pre):
            parser.error('--publication-pre is required only for post')
        result = publication_check(S, args.candidate or S/'candidate.json',
                                   args.artifact_manifest, R, pre_record=args.publication_pre)
        body = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
        if args.report:
            target = (S/args.report).resolve()
            _publication_require(target.is_relative_to(S) and not target.is_relative_to(R),
                                 'report must stay in stage, outside canonical')
            with target.open('x', encoding='utf8') as stream:
                stream.write(body)
            print(json.dumps({key: result[key] for key in
                              ('status','before','after','registry_rows','protected_count')} |
                             {'report': str(target)}, ensure_ascii=False))
        else:
            print(body, end='')
        return
    if args.report:
        parser.error('--report requires --publication-check')
    spec = json.loads((S/'candidate.json').read_text(encoding='utf8'))
    evidence = verify_acceptance_evidence(S,spec,R)
    if args.evidence_only:
        print(json.dumps(evidence,ensure_ascii=False,indent=2))
        raise SystemExit(0)
    print('Input evidence:',evidence['mode'],'verified game commands',evidence['game_commands'],'first run covers required',evidence.get('first_run_includes_all_required'))
    validate_candidate_shape(spec);repair=spec.get('repair_only',False)
    key = spec['id']
    published = args.published
    names = json.loads((S/(key+'-artifacts.json')).read_text(encoding='utf8'))
    baseline = json.loads((S/'baseline.json').read_text(encoding='utf8'))
    ids = set(spec['completed'])
    registries = {details['registry'] for details in spec['completed'].values()}
    assert len(registries) <= 1 and registries <= {'core', 'class'}, 'Ordered bundles require one core or class registry'
    section = next(iter(registries), spec['selection'].get('reporting', {}).get('section', 'core'))
    assert section in ('core', 'class'), 'Ordered bundles support core or class only'
    section_initial = 118 if section == 'core' else 221
    for field, expected in [('section', section), ('section_initial', section_initial), ('section_initial_remaining', section_initial), ('overall_total', 2352)]:
        if field in spec['selection'].get('reporting', {}):
            assert spec['selection']['reporting'][field] == expected, ('incorrect reporting scope', field)
    assert len(names) == len(set(names))

    def raw(name):
        return (S/name if name in names else R/name).read_bytes()

    def read(name):
        return raw(name).decode('utf8')

    def obj(name):
        return json.loads(read(name))

    for name in names:
        assert not Path(name).is_absolute() and '..' not in Path(name).parts, name
        if published:
            assert (R/name).read_bytes() == (S/name).read_bytes(), name
        else:
            current = sha256((R/name).read_bytes()).hexdigest() if (R/name).is_file() else None
            assert current == baseline[name], ('concurrent change', name)

    plan_name = 'data/verification/category2-edge-work-plan.json'
    cp_name = 'data/verification/category2-work-checkpoint.json'
    core_name = 'data/verification/category2-core-clause-status.json'
    filename, rows_key, id_key = REGISTRIES[section]
    registry_name = 'data/verification/'+filename
    p, c = obj(plan_name), obj(cp_name)
    b = p['latest_reassessment'][key+'_completion']
    cycle = p['latest_reassessment']['skip_prerequisite_cycle']
    reporting = b['selection']['reporting']
    assert p['latest_reassessment']['original_clause_resumption']['section_initial'] == 118
    newrows = {row[id_key]: row for row in obj(registry_name)[rows_key]}
    assert all(uid in newrows and registry_included(newrows[uid], section) for uid in {*spec['traversal'], *spec['deferred'], *ids}), 'Traversal must remain in the selected registry'
    rem = sum(registry_included(row, section) and registry_status(row, section) in (('incomplete', 'known-rule-choice') if section == 'class' else ('incomplete',)) for row in newrows.values())
    solved = section_initial-rem
    core_rows = obj(core_name)['clause_mappings']
    core_rem = sum(row['category2_included'] is True and row['category2_status'] == 'incomplete' for row in core_rows)
    core = 118-core_rem
    assert 0 <= core <= 118
    assert 0 <= solved <= section_initial
    section_skip = len(cycle['skip_review']['unresolved_clause_ids']) if section == 'core' else sum(uid in newrows and registry_included(newrows[uid], section) for uid in cycle['skip_review']['unresolved_clause_ids'])
    after = spec['completed_before'] + len(ids)
    assert set(b['clause_ids']) == ids
    assert b['completion_delta'] == b['completion_credit'] == len(ids)
    assert b['implementation_credit'] == spec.get('implementation_credit', 0)
    assert b['status'] == ('repair_verified' if repair else 'implemented_and_verified')
    assert b['shared_feature_credit'] == spec.get('shared_feature_credit', 0)
    assert reporting['overall_completed'] == after
    assert reporting['section_completed'] == solved
    assert reporting['section_remaining'] == rem
    assert reporting['section_skipped'] == section_skip
    assert reporting['overall_remaining'] == 2352-after
    if section == 'class':
        assert reporting['section'] == 'class' and reporting['section_initial'] == 221 and reporting['overall_total'] == 2352
        assert reporting['core_completed'] == core and reporting['core_total'] == 118 and reporting['core_remaining'] == core_rem
        assert reporting['core_skipped'] == sum(row['clause_id'] in cycle['skip_review']['unresolved_clause_ids'] for row in core_rows if row['category2_included'] is True)
        hook = p['latest_reassessment']['original_clause_resumption']
        assert hook['current_section_solved'] == core and hook['current_section_remaining'] == core_rem
        if not repair:
            assert hook['current_class_initial'] == 221 and hook['current_class_solved'] == solved and hook['current_class_remaining'] == rem
    additional = cycle['additional_shared_features']
    common = shared_feature_count(additional)
    shared_records = new_shared_feature_records(spec, b, newrows, section, read)
    if not published:
        for record in shared_records:
            for name in record['runtime_paths']:
                assert baseline[name] != sha256(raw(name)).hexdigest(), ('new shared-feature owner has no change', name)
    shared_ids = [record['id'] for record in shared_records]
    assert b.get('shared_feature_ids', []) == shared_ids
    completion_reference = plan_name+'#latest_reassessment.'+key+'_completion'
    assert resolve_shared_feature_consumers(additional['features'],ids,completion_reference) == additional['features'], 'Completed originals remain in shared-feature waiting consumers'
    assert [record for record in additional['features'] if record['canonical_reference'] == completion_reference] == shared_records
    implementation_batches = [row for row in cycle['implementation']['batches'] if row['id'] == key]
    assert len(implementation_batches) == b['implementation_credit']
    if implementation_batches:
        assert implementation_batches[0]['shared_feature_ids'] == shared_ids
    interval = cycle['implementation']['vault_quality_interval']
    assert interval == 10
    assert 0 <= cycle['implementation']['since_vault_quality'] < interval
    quality = spec.get('vault_quality_review')
    if quality:
        latest_quality = cycle['vault_quality']['history'][-1]
        assert latest_quality['after_implementation_total'] == cycle['implementation']['total']
        assert latest_quality['implementation_batch_ids'] == quality['implementation_batch_ids']
        assert latest_quality['findings'] == quality['findings']
        assert latest_quality['fixes'] == quality['fixes']
        assert latest_quality['files'] == quality['files']
        assert latest_quality['verification'] == audit_quality(read, lambda n: (S/n if n in names else R/n).is_file(), quality)
        assert latest_quality['completion_credit'] == latest_quality['implementation_credit'] == latest_quality['shared_feature_credit'] == 0
        assert cycle['implementation']['since_vault_quality'] == 0
    assert cycle['skip_review']['current_count'] == len(cycle['skip_review']['window_clause_ids'])
    assert cycle['skip_review']['current_count'] < cycle['skip_review']['trigger_at']
    assert not cycle['latest_user_correction']['active_grouped_clause_ids']
    assert c['current_work']['implementation_delegation']['implementation'] == 'fresh_context_subagents'
    assert cycle['execution_method'] == 'fresh_context_subagent'
    assert c['current_work']['execution_method'] == spec['selection']['execution_method']
    assert c['current_work']['pending_rule_questions'] == []
    if not repair:
        assert c['current_work']['ordered_traversal']['last_visited_clause_id'] == spec['traversal'][-1]
        assert c['current_work']['ordered_traversal']['section'] == section
        if spec.get('next_clause_id'):
            assert c['current_work']['next_clause_id'] == c['current_work']['next_clause'] == spec['next_clause_id']
            if section == 'class':
                next_clause = spec['next_clause_id']
                assert next_clause in newrows and registry_included(newrows[next_clause], section) and registry_status(newrows[next_clause], section) in ('incomplete', 'known-rule-choice')
    assert c['architecture_review']['controller']['suspension']['paused']
    assert set(c['last_goal_turn']['completed_clause_ids']) == ids
    assert c['last_goal_turn']['clause_delta'] == len(ids)
    assert '엔트리포인트.md' not in names, 'Entry-point instructions are outside this batch'
    for reference, expected in b['current_file_hashes'].items():
        name = re.sub(r':R?\d+$', '', reference.split('#', 1)[0])
        assert sha256(raw(name)).hexdigest() == expected, reference
    for name in b['runtime_changes'] + b['test_changes']:
        ast.parse(read(name))
    assert all(registry_status(newrows[uid], section) == 'implemented' for uid in ids)
    if not published:
        oldp = json.loads((R/plan_name).read_text(encoding='utf8'))
        oldc = json.loads((R/cp_name).read_text(encoding='utf8'))
        oldcycle = oldp['latest_reassessment']['skip_prerequisite_cycle']
        oldadditional = oldcycle['additional_shared_features']
        assert common-shared_feature_count(oldadditional) == b['shared_feature_credit']
        assert not set(shared_ids) & {record['id'] for record in oldadditional['features']}
        assert additional == dict(oldadditional, count=common, features=resolve_shared_feature_consumers(oldadditional['features'],ids,completion_reference)+shared_records)
        oldhook = oldp['latest_reassessment']['original_clause_resumption']
        if oldhook.get('status') == 'active':
            assert p['latest_reassessment']['original_clause_resumption'].get('common_credit_delta', 0) == oldhook.get('common_credit_delta', 0) + b['shared_feature_credit']
        assert p['foundation_discovery'] == oldp['foundation_discovery']
        assert p['latest_reassessment']['whole_rule_template_audit']['reuse_elements_progress'] == oldp['latest_reassessment']['whole_rule_template_audit']['reuse_elements_progress']
        assert c['architecture_review'] == oldc['architecture_review']
        if repair:
            assert cycle['skip_review'] == oldcycle['skip_review']
            assert cycle['completion_credit'] == oldcycle['completion_credit']
            assert c['current_work']['ordered_traversal'] == oldc['current_work']['ordered_traversal']
            assert c['current_work']['next_step'] == oldc['current_work']['next_step']
            assert c['current_work']['latest_completion'] == oldc['current_work']['latest_completion']
            assert p['post_foundation_reuse']['itemized_audit'] == oldp['post_foundation_reuse']['itemized_audit']
            assert p['latest_reassessment']['ready_sweep'] == oldp['latest_reassessment']['ready_sweep']
            assert p['latest_reassessment']['last_native_completion_at'] == oldp['latest_reassessment']['last_native_completion_at']
        assert cycle['implementation']['vault_quality_interval'] == oldcycle['implementation']['vault_quality_interval']
        if quality:
            assert oldcycle['implementation']['since_vault_quality'] + b['implementation_credit'] == interval
            assert cycle['vault_quality']['completed_rounds'] == oldcycle['vault_quality']['completed_rounds'] + 1
            assert cycle['vault_quality']['history'][:-1] == oldcycle['vault_quality']['history']
        else:
            assert cycle['vault_quality'] == oldcycle['vault_quality']
        assert cycle['implementation']['total'] == oldcycle['implementation']['total'] + b['implementation_credit']
        assert cycle['implementation']['since_vault_quality'] == (0 if quality else oldcycle['implementation']['since_vault_quality'] + b['implementation_credit'])
        oldrows = {row[id_key]: row for row in json.loads((R/registry_name).read_text(encoding='utf8'))[rows_key]}
        oldsection = section_initial-sum(registry_included(row, section) and registry_status(row, section) in (('incomplete', 'known-rule-choice') if section == 'class' else ('incomplete',)) for row in oldrows.values())
        oldcore = 118-sum(row['category2_included'] is True and row['category2_status'] == 'incomplete' for row in json.loads((R/core_name).read_text(encoding='utf8'))['clause_mappings'])
        assert solved-oldsection == len(ids)
        assert core-oldcore == (len(ids) if section == 'core' else 0)
        if section == 'class':
            assert raw(core_name) == (R/core_name).read_bytes(), 'Class bundles must preserve the core registry'
        assert {uid for uid in oldrows if oldrows[uid] != newrows[uid]} == ids
        oldpool = set(oldcycle['skip_review']['unresolved_clause_ids'])
        added = set(spec['traversal']) & set(spec['deferred']) - oldpool
        assert set(cycle['skip_review']['unresolved_clause_ids']) == oldpool - ids | added
        assert cycle['skip_review']['current_count'] == oldcycle['skip_review']['current_count'] + len(added)

    oldtext, oldraw, oldfile = Path.read_text, Path.read_bytes, Path.is_file

    def overlay(path):
        try:
            name = path.relative_to(R).as_posix()
        except ValueError:
            return path
        return S/name if name in names else path

    sys.path.insert(0, str(R/'tools'))
    report_path = 'tools/report_category2_progress.py'
    if report_path in names:
        from importlib.util import module_from_spec, spec_from_file_location
        report_spec = spec_from_file_location('_staged_category2_progress', S/report_path)
        REPORT = module_from_spec(report_spec)
        report_spec.loader.exec_module(REPORT)
    else:
        import report_category2_progress as REPORT
    with patch.object(Path, 'read_text', lambda path, *a, **kw: oldtext(overlay(path), *a, **kw)), patch.object(Path, 'read_bytes', lambda path: oldraw(overlay(path))), patch.object(Path, 'is_file', lambda path: oldfile(overlay(path))):
        report = REPORT.collect(R)
    assert report['completed_clause_count'] == after and report['denominator'] == 2352
    assert not report['validation_errors'], report['validation_errors']
    reuse = report['edge_reuse_inspection']
    assert reuse['completed'] == reuse['denominator']
    for name in spec['notes']:
        for href in re.findall(r'\]\(([^)]+)\)', read(name)):
            href = unquote(href.strip('<>').split('#', 1)[0])
            if not href or '://' in href or re.match(r'^[A-Z]:', href, re.I):
                continue
            target = posixpath.normpath((Path(name).parent/href).as_posix())
            assert (S/target if target in names else R/target).is_file(), (name, href)
    body = read('vaults/작업/잔여-구현목록.md')
    assert f'추가 공통 기능{common} |' in body.split('## 눈에 띄는 남은 기능', 1)[0]
    assert f"추가 공통 기능{common}·구현{cycle['implementation']['total']}회" in read('vaults/인덱스.md')
    assert not any(re.search(r'^#### `'+uid+'`', body, re.M) for uid in ids)
    assert f"| {section_initial} | {solved} | {section_skip} | {rem} |" in body
    assert f"| **1,118** | **{after-1234}** | **{len(cycle['skip_review']['unresolved_clause_ids'])}** | **{2352-after:,}** |" in body
    if section == 'class':
        assert f"| 118 | {core} | {reporting['core_skipped']} | {core_rem} |" in body
        block = re.search(r'^## 본문 엣지·재주·트레이너 클래스 — (\d+)개\r?\n(.*?)(?=^## |\Z)', body, re.M | re.S)
        assert block and int(block[1]) == rem and len(re.findall(r'^#### `', block[2], re.M)) == rem
        for count, entries in re.findall(r'^### input/[^\n]+ — (\d+)개\r?\n(.*?)(?=^### |\Z)', block[2], re.M | re.S):
            assert int(count) == len(re.findall(r'^#### `', entries, re.M))
    section_summary=f"core{core}/skips{section_skip}/rem{rem}" if section=='core' else f"class{solved}/221/skips{section_skip}/rem{rem};core{core}/118/rem{core_rem}"
    print('Verified', 'canonical' if published else 'staged', f"originals+{len(ids)};{after}/2352;{section_summary};reuse{reuse['completed']};common{common}(+{b['shared_feature_credit']})/code{cycle['implementation']['total']}/quality{cycle['vault_quality']['completed_rounds']}/next{cycle['implementation']['since_vault_quality']}/{interval};window{cycle['skip_review']['current_count']}/{cycle['skip_review']['trigger_at']};protected invariants preserved")


if __name__ == '__main__':
    main()
