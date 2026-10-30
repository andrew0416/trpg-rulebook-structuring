"""One approved AA4 retained-evidence admission; no gameplay or publication."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import stat
import subprocess
import sys
import traceback
import zipfile

import ci_validate as ci
from ci_remote_h import H_SHA256, crypt, stage_path
from ci_aa_recovery import retrieve_artifact, history_id, history_objects, gate_reference

REPOSITORY = 'andrew0416/trpg-rulebook-structuring'
BRANCH = 'refs/heads/codex/aa-current17-admission-1030'
TESTED_HEAD = 'b47e38089463d57d48692b24e5033a364be7e1ce'
BUNDLE = '.ci/aa-acceptance.zip.enc'
APPROVED_PACKAGE_BLOB = '5778c37c9e25549de67dcaf2babf02ddb13cd0ef'
INTERNAL_MANIFEST = 'acceptance-input-manifest.json'
PREFIX = 'data/verification/ability-exchange-acceptance01/'
PLAN = 'data/verification/category2-edge-work-plan.json'
OVERRIDES = {
    PLAN, 'data/verification/category2-work-checkpoint.json',
    'data/verification/template-reuse-checks.json',
    'data/verification/template-reuse-contracts.json',
    'data/verification/category2-class-csv-clause-status.json',
    'data/verification/category2-csv-abilities-moves-status.json',
    'data/verification/category2-optional-clause-status.json',
    'data/verification/category2-tabular-core-status.json',
    'data/verification/category2-progress.json',
}
REVIEW_FILES = {'acceptance-stage/candidate.json'} | {
    PREFIX + name for name in ('obligation-map.json', 'post-integration-mainbd-review.json',
    'current-impact.json', 'original-source-review.json', 'plan-log-path-migration.json')}
CLAUSES = {'C2CSV-ABILITY-R0112', 'C2CSV-ABILITY-R0157',
           'C2CSV-ABILITY-R0473', 'C2CSV-MOVE-R0479'}
ARTIFACTS = {
    'original': dict(id=12712760267, run=40452378890, tests=249,
        name='implementation-aa-40452378890-1', size=215024217,
        head='ad5ae261d62e5369917593d3c3083116afc13104',
        digest='0462a281fad307542d78485a68e49466ab722a79e9cf2515fb1869347106726a',
        archive='955863cc85274feb633793e7d1b0a989f0c76202c0d719ebf394dad39078e1a7',
        cipher='6c9458387fbc360f47cc9bda5a3d65ad07d70a42811628298a9cad7dc82dc2e7'),
    'current': dict(id=12905459317, run=40894552221, tests=8,
        name='validation-changed_revisions-40894552221-1', size=214319443,
        head='b85bf3f7330c8c2f2df5dc9e16f2862fe19722cc',
        digest='36a85bb1a5751b235f0d71ef342cbc0a1d8894820c8a896aaf2a26f732a5e9fd',
        archive='ebaf0e43a41a94b339934a847eeccfacaa44c82266520e3a5217c4518c972b41',
        cipher='4f0b286032069cdbe30a89cf3affe4b9cb6e6df2e2806b3f6fb385007d65d78d'),
    'current17': dict(id=12948987135, run=40989718755, tests=17,
        name='validation-changed_revisions-40989718755-1', size=281775860,
        head=TESTED_HEAD,
        digest='8612a69e609f9b028700169a4de1809939df1f52d0211ce676ff329785b22349',
        archive='fb58c0946bf5fd59a894058b69c3b25c6bc902f60ec366abe96bde3bb8c44f5f',
        cipher='6c8a96dcab2a31a70331453287c544f5027445760084038e6a6a00bd2beaac5a',
        required_ids_sha256='efa10380ac683766e8bcaade1bf9d494a27b44f095caf9eca6dc17ad79171ea0'),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def git(root, *args):
    # Git warnings must not be parsed as tracked paths or dirty status.
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    ci.write_json(path, value)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def zip_files(archive):
    """Use existing fixture path rules before reading any supplied ZIP member."""
    names = {}
    for entry in archive.infolist():
        name = ci.fixture_path(entry.orig_filename)
        require(name == entry.filename and not entry.is_dir()
                and stat.S_IFMT(entry.external_attr >> 16) in (0, stat.S_IFREG)
                and name.casefold() not in names, 'Unsafe or duplicate archive member')
        names[name.casefold()] = name
    return set(names.values())


def combined_rows(base, extra, tracked):
    base_rows = ci.fixture_rows(base, tracked)
    extra_rows = ci.fixture_rows(extra, tracked)
    require(set(base_rows) & set(extra_rows) == OVERRIDES,
            'Only the nine approved fixture replacements are allowed')
    combined = {**base_rows, **extra_rows}
    result = {'version': 1, 'files': list(combined.values())}
    ci.fixture_rows(result, tracked)
    return result


def prepare_inputs(checkout, work, key, policy, expected_blob):
    require(expected_blob == APPROVED_PACKAGE_BLOB, 'Exact approved package Git blob required')
    tracked = git(checkout, 'ls-files', '-z').decode().rstrip('\0').split('\0')
    require(BUNDLE in tracked, 'Approved ciphertext must be tracked')
    require(git(checkout, 'rev-parse', 'HEAD:'+BUNDLE).decode().strip() == expected_blob
            and git(checkout, 'hash-object', BUNDLE).decode().strip() == expected_blob,
            'Ciphertext differs from the dispatched immutable Git blob')
    require(git(checkout, 'rev-parse', 'HEAD').decode().strip() == os.environ['GITHUB_SHA'],
            'Checkout differs from dispatched head')
    git(checkout, 'merge-base', '--is-ancestor', TESTED_HEAD, 'HEAD')
    changed = set(git(checkout, 'diff', '--name-only', TESTED_HEAD, 'HEAD').decode().splitlines())
    require(changed <= {BUNDLE, 'tools/ci_aa_acceptance.py', 'tools/ci_aa_recovery.py',
                        'tools/test_ci_aa_current17_transform.py', '.gitattributes',
                        REVIEWED_SOURCE_PATCH, '.ci/source-snapshot.json', '.github/workflows/validate.yml'},
            'Admission child contains an unreviewed source change')
    attributes = git(checkout, 'show', TESTED_HEAD+':.gitattributes')
    require(attributes.count(b'CI.md text eol=lf\n') == 1,
            'AA_ATTRIBUTES_PREIMAGE_DIFFERS')
    expected_attributes = attributes.replace(b'CI.md text eol=lf\n', b'CI.md -text\n')
    require(git(checkout, 'show', 'HEAD:.gitattributes') == expected_attributes
            and (checkout/'.gitattributes').read_bytes() == expected_attributes,
            'AA_ATTRIBUTES_CHANGE_EXCEEDS_CI_MD_BYTE_PRESERVATION')
    require(not git(checkout, 'status', '--porcelain', '--untracked-files=no').strip(),
            'Tracked checkout is modified')
    source_pins = ci.input_hashes(checkout, tracked)
    base_manifest = read(checkout/ci.MANIFEST)
    ci.fixture_rows(base_manifest, tracked)
    base_zip, package_zip = work/'base.zip', work/'approved.zip'
    crypt(checkout, 'decrypt', checkout/ci.BUNDLE, base_zip, key)
    crypt(checkout, 'decrypt', checkout/BUNDLE, package_zip, key)
    with zipfile.ZipFile(package_zip) as archive:
        names = zip_files(archive)
        require(INTERNAL_MANIFEST in names, 'AA_PACKAGE_INTERNAL_MANIFEST_MISSING')
        manifest = json.loads(archive.read(INTERNAL_MANIFEST))
        check_package_manifest_shape(manifest, work)
        require(manifest['version'] == 1 and manifest['source_count'] == 802
                and set(manifest['allowed_replacements']) == OVERRIDES,
                'Approved package scope differs')
        entries = manifest['files']
        require(len(entries) == 802 and len({x['path'].casefold() for x in entries}) == 802
                and names == {x['path'] for x in entries} | {INTERNAL_MANIFEST},
                'Package must contain exactly the approved802 plus internal metadata')
        roles = {role: {x['path'] for x in entries if x['role'] == role}
                 for role in ('existing_prior_raw_log', 'current_canonical_metadata', 'aa_source_review')}
        require(roles['current_canonical_metadata'] == OVERRIDES
                and roles['aa_source_review'] == REVIEW_FILES
                and len(roles['existing_prior_raw_log']) == 787
                and all(n.endswith('.log') for n in roles['existing_prior_raw_log'])
                and sum(map(len, roles.values())) == 802, 'Package roles differ')
        require(sum(x['expected_sha256'] is None for x in entries) == 10,
                'Only the approved ten unknown hashes may be established remotely')
        rows = []
        extra_zip = work/'extra.zip'
        with zipfile.ZipFile(extra_zip, 'x', compression=zipfile.ZIP_STORED) as clean:
            for row in entries:
                name = ci.fixture_path(row['path'])
                body = archive.read(name)
                actual = hashlib.sha256(body).hexdigest()
                require(len(body) == row['size'], 'Private member size differs')
                if row['expected_sha256'] is not None:
                    require(actual == row['expected_sha256'], 'Stored private member hash differs')
                else:
                    require(name in REVIEW_FILES or name in {
                        PLAN, 'data/verification/category2-work-checkpoint.json',
                        'data/verification/template-reuse-checks.json',
                        'data/verification/template-reuse-contracts.json'}, 'Unknown private hash not authorized')
                rows.append(dict(path=name, size=len(body), sha256=actual))
                clean.writestr(name, body)
    extra_manifest = {'version': 1, 'files': rows}
    # Both authenticated bundles are verified separately, then combined for a fresh root.
    base_root, extra_root = work/'base-fixtures', work/'extra-fixtures'
    base_root.mkdir(); extra_root.mkdir()
    ci.restore_fixtures(base_root, base_zip, base_manifest, tracked)
    ci.restore_fixtures(extra_root, extra_zip, extra_manifest, tracked)
    combined = combined_rows(base_manifest, extra_manifest, tracked)
    combined_zip = work/'combined.zip'
    with zipfile.ZipFile(combined_zip, 'x', compression=zipfile.ZIP_STORED) as archive:
        for row in combined['files']:
            origin = extra_root if (extra_root/row['path']).is_file() else base_root
            archive.write(origin/row['path'], row['path'])
    root = work/'canonical-inputs'
    ci.copy_stage(checkout, root, source_pins)
    fixture_pins = ci.restore_fixtures(root, combined_zip, combined, tracked)
    private_manifest = {'version': 1, 'files': [base_manifest['private_policy']]}
    fixture_pins.update(ci.restore_private_policy(root, policy, private_manifest, combined, tracked))
    write(work/'records/authenticated-package.json', dict(
        git_head=os.environ['GITHUB_SHA'], package_git_blob=expected_blob,
        ciphertext_sha256=ci.file_hash(checkout/BUNDLE), manifest=manifest,
        actual_private_manifest=extra_manifest, original_fixture_manifest=base_manifest))
    return root, {**source_pins, **fixture_pins}


def authenticate_history(checkout, work, token, key, label, recovery_root=None):
    bound = ARTIFACTS[label]
    outer, api_record, anchor, acquisition = retrieve_artifact(
        checkout, bound, work, token, key, REPOSITORY, recovery_root)
    with zipfile.ZipFile(outer) as artifact:
        names = zip_files(artifact)
        members = {}
        def one(suffix):
            found = [name for name in names if name.endswith('/'+suffix) or name == suffix]
            require(len(found) == 1, 'Original artifact member is not unique')
            members[suffix] = found[0]
            return artifact.read(found[0])
        run = json.loads(one('run.json'))
        require(run['git_sha'] == bound['head'] and run['ci']['GITHUB_RUN_ID'] == str(bound['run'])
                and run['ci']['GITHUB_RUN_ATTEMPT'] == '1'
                and run['ci']['GITHUB_REPOSITORY'] == REPOSITORY
                and run['exit_code'] == 0 and run['inputs_unchanged'] is True,
                'Original run is not the bound stable success')
        cipher = work/(label+'-evidence.zip.enc')
        with cipher.open('xb') as stream:
            stream.write(one('evidence.zip.enc'))
        require(ci.file_hash(cipher) == bound['cipher'] == run['encrypted_evidence']['sha256'],
                'Original encrypted evidence differs')
        h_summary = json.loads(one('h-summary.json'))
        require(h_summary['status'] == 'H_PHYSICAL_ACCEPTED'
                and h_summary['head'] == bound['head'] and h_summary['run'] == str(bound['run'])
                and h_summary['attempt'] == '1'
                and h_summary['checker_sha256'] == H_SHA256
                and h_summary['ordinary_verified'] == bound['tests']
                and h_summary['original_archive_sha256'] == bound['archive'], 'Original H summary differs')
    require(anchor is None or (anchor['run'] == run and anchor['h_summary'] == h_summary),
            'Retained outer archive disagrees with approved acquisition metadata')
    full = work/'evidence-store'/history_id(bound)/'full-evidence.zip'
    full.parent.mkdir(parents=True, exist_ok=False)
    crypt(checkout, 'decrypt', cipher, full, key)
    require(ci.file_hash(full) == bound['archive'], 'Original full archive differs')
    with zipfile.ZipFile(full) as archive:
        names = zip_files(archive)
        require('diagnostic-scope.json' not in names, 'Diagnostic subset cannot prove physical inputs')
        meta = json.loads(archive.read('physical/ci-native.json'))
        stage = Path(meta['execution_stage']).resolve()
        require(stage == Path(run['execution_stage']).resolve()
                and stage.parent == Path('D:/trpg-rulebook-structuring/ci').resolve()
                and stage.name == str(bound['run'])+'-1-changed_revisions'
                and meta['tests'] == bound['tests'], 'Historical execution identity differs')
        stage.mkdir(parents=True, exist_ok=False)
        for relative, member in ((meta['metadata_path'], 'physical/ci-native.json'),
                                 (meta['raw_log'], 'physical/ci-native.log'),
                                 (meta['frozen_inputs'], 'physical/ci-native-inputs.zip')):
            target = stage_path(stage, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(archive.read(member))
    checker_path = checkout/'tools/ci_h_checker.py'
    require(ci.file_hash(checker_path) == H_SHA256, 'Unchanged independent H required')
    checker = module(checker_path, 'aa_independent_H_'+label)
    h_spec = dict(repair_only=True, required_test_ids=meta['test_ids'],
                  logs=[meta['raw_log']], execution_history=[{'metadata': meta['metadata_path']}],
                  game_runs=1, test_executions=meta['tests'])
    generated = {meta['metadata_path']: {'path': str(full), 'sha256': bound['archive']}}
    facts = checker.verify_acceptance_evidence(stage, h_spec, stage, generated_archives=generated)
    require(facts['mode'] == 'physical' and facts['latest_valid_pass_count'] == bound['tests'],
            'Independent historical H acceptance failed')
    objects = history_objects(bound, REPOSITORY, outer, cipher, full,
                              stage_path(stage, meta['frozen_inputs']), meta, members)
    require(anchor is None or anchor['objects'] == objects,
            'Retained object kind/size/digest/location differs from approved acquisition')
    provenance = dict(api=api_record, run=run, original_h_summary=h_summary,
                      acquisition=acquisition, evidence_objects=objects,
                      repeated_h_facts=facts, original_archive_sha256=bound['archive'],
                      raw_log_sha256=ci.file_hash(stage_path(stage, meta['raw_log'])),
                      validation_only=True, new_game_runs=0)
    write(work/('records/'+label+'-physical-binding.json'), provenance)
    return dict(meta=meta, stage=stage, archive=full,
                log=stage_path(stage, meta['raw_log']), provenance=provenance)


def selected_lines(body, required, identity):
    wanted = {identity(case) for case in required}
    selected = []
    for line, text in enumerate(body.decode('utf-8-sig').splitlines(), 1):
        match = re.fullmatch(r'(test_\w+) \((\w+(?:\.\w+){2,})\) \.\.\. ok', text)
        if match and identity(match[2]) in wanted:
            selected.append(dict(line=line, text=text))
    require(len(selected) == len(wanted), 'Exact retained named lines unavailable')
    return selected



CURRENT8_HEAD = 'b85bf3f7330c8c2f2df5dc9e16f2862fe19722cc'
GAS_CASE = ('tools.test_csv_ability_exchange_contracts.AbilityExchangeContractsTests.'
            'test_real_interrupt_offer_use_is_blocked_after_gas_enters_but_decline_is_free')
ENTRAINMENT_CASES = [
    'tools.test_entrainment_header_boundaries.EntrainmentHeaderBoundaryTests.'
    'test_entrainment_scene_quota_survives_encounter_then_resets_at_scene_boundary',
    'tools.test_entrainment_header_boundaries.EntrainmentHeaderBoundaryTests.'
    'test_entrainment_ac2_uses_speed_evasion_threshold',
    'tools.test_entrainment_header_boundaries.EntrainmentHeaderBoundaryTests.'
    'test_entrainment_range_four_accepts_edge_and_rejects_fifth_meter_before_cost',
]
REVIEWED_SOURCE_PATCH = 'tools/aa_current17_reviewed.patch'
CHANGED_EXISTING_SOURCES = (
    'engine/engine.py', 'engine/survivalist_features.py',
    'tools/test_book_trickster_full.py', 'tools/test_csv_ability_exchange_contracts.py')
REPAIR_SOURCE_PATHS = set(CHANGED_EXISTING_SOURCES) | {
    BUNDLE, '.ci/source-snapshot.json', '.ci/suites/changed_revisions.json',
    'tools/test_blinded_living_weapon_movement.py',
    'tools/test_entrainment_header_boundaries.py'}


def check_package_manifest_shape(manifest, work):
    # A schema mismatch is diagnostic evidence, never permission to reinterpret 802.
    fields = {'version', 'source_count', 'allowed_replacements', 'files'}
    entry_fields = {'path', 'role', 'size', 'expected_sha256'}
    shape = dict(type=type(manifest).__name__,
                 keys=sorted(manifest) if isinstance(manifest, dict) else None)
    entries = manifest.get('files') if isinstance(manifest, dict) else None
    shape['files_type'] = type(entries).__name__
    shape['entry_key_sets'] = sorted({','.join(sorted(row)) for row in entries
                                     if isinstance(row, dict)}) if isinstance(entries, list) else []
    write(work/'records/package-manifest-shape.json', shape)
    require(isinstance(manifest, dict) and fields <= set(manifest)
            and type(manifest['version']) is int and type(manifest['source_count']) is int
            and isinstance(manifest['allowed_replacements'], list)
            and all(isinstance(name, str) for name in manifest['allowed_replacements'])
            and isinstance(entries, list),
            'AA_PACKAGE_MANIFEST_SCHEMA_UNCONFIRMED: inspect private package-manifest-shape.json')
    require(all(isinstance(row, dict) and entry_fields <= set(row)
                and isinstance(row['path'], str) and isinstance(row['role'], str)
                and type(row['size']) is int and row['size'] >= 0
                and (row['expected_sha256'] is None or
                     isinstance(row['expected_sha256'], str)
                     and re.fullmatch('[a-f0-9]{64}', row['expected_sha256']))
                for row in entries),
            'AA_PACKAGE_MANIFEST_ENTRY_SCHEMA_UNCONFIRMED: inspect private shape record')


def current17_transform(checkout, root, work, candidate, impact, post, histories,
                        original_pins, normalize):
    old50 = impact['retained_valid_case_ids']
    old8 = post['historical_evidence']['current8_actual_ids']
    old_all = {normalize(case) for row in candidate['completed'].values()
               for case in row['reused_test_ids']}
    old50_norm, old8_norm = ({normalize(case) for case in ids} for ids in (old50, old8))
    require(len(old50) == len(old50_norm) == 50 and len(old8) == len(old8_norm) == 8
            and not old50_norm & old8_norm and old50_norm | old8_norm == old_all
            and GAS_CASE in old8 and GAS_CASE not in old50,
            'AA_RETAINED_SELECTION_PREIMAGE_DIFFERS')
    latest = histories['current17']
    old_current = histories['current']
    require(len(old_current['meta']['test_ids']) == 8
            and {normalize(case) for case in old_current['meta']['test_ids']} == old8_norm
            and old50_norm <= {normalize(case) for case in histories['original']['meta']['test_ids']},
            'AA_HISTORICAL_SELECTED_ID_BINDING_DIFFERS')
    suite = json.loads(git(checkout, 'show', TESTED_HEAD+':.ci/suites/changed_revisions.json'))
    exact17 = [case for row in suite['completed'].values() for case in row['tests']]
    require(len(exact17) == len(set(exact17)) == 17
            and suite['required_unique_count'] == 17
            and len(latest['meta']['test_ids']) == 17
            and set(latest['meta']['test_ids']) == set(exact17),
            'AA_CURRENT17_EXACT_SELECTION_DIFFERS')
    required_digest = hashlib.sha256(json.dumps(sorted(exact17)).encode()).hexdigest()
    require(required_digest == ARTIFACTS['current17']['required_ids_sha256']
            == latest['provenance']['original_h_summary']['required_ids_sha256'],
            'AA_CURRENT17_REQUIRED_ID_BINDING_DIFFERS')
    selected_latest = [GAS_CASE, *ENTRAINMENT_CASES]
    require(set(selected_latest) <= set(exact17)
            and not {normalize(case) for case in ENTRAINMENT_CASES} & old_all,
            'AA_CURRENT17_REQUIRED_CASES_MISSING_OR_DUPLICATED')

    changed = set(git(checkout, 'diff', '--name-only', CURRENT8_HEAD, TESTED_HEAD).decode().splitlines())
    require(changed == REPAIR_SOURCE_PATHS, 'AA_CURRENT8_TO_17_CHANGED_PATHS_DIFFER')
    patch = git(checkout, 'diff', '--full-index', '--binary', '--no-color',
                '--no-ext-diff', '--no-textconv', CURRENT8_HEAD, TESTED_HEAD,
                '--', *CHANGED_EXISTING_SOURCES).decode('utf-8')
    reviewed_patch = (checkout/REVIEWED_SOURCE_PATCH).read_text(encoding='utf-8')
    require(patch.replace('\r\n', '\n') == reviewed_patch.replace('\r\n', '\n'),
            'AA_CURRENT8_TO_17_REVIEWED_SOURCE_DELTA_DIFFERS')
    (work/'records/current8-to-current17-reviewed.patch').write_text(patch, encoding='utf-8')

    old_pins = candidate['retained_proof']['runtime_test_source_sha256']
    ledger = 'data/verification/category2-csv-abilities-moves-status.json'
    old_pre = old_current['meta']['runtime_test_data_sha256_before']
    for name, expected in old_pins.items():
        if name != ledger:
            require(old_pre.get(str(PureWindowsPath(old_current['meta']['execution_stage'])/name)) == expected,
                    'AA_CURRENT8_CANDIDATE_SOURCE_PREIMAGE_DIFFERS: '+name)
    paths = set(old_pins) | set(CHANGED_EXISTING_SOURCES) | {
        'engine/frequency.py', 'engine/body_state.py', 'engine/weapon_actions.py',
        'engine/custom_species.py', 'engine/fast_combat.py',
        'tools/test_entrainment_header_boundaries.py',
        'tools/test_blinded_living_weapon_movement.py',
        '.ci/suites/changed_revisions.json'}
    pre = latest['meta']['runtime_test_data_sha256_before']
    source_pins = {}
    for name in sorted(paths):
        # This metadata comes from sealed802, not from the native run or live ledger.
        expected = (original_pins[name] if name == ledger else
                    pre.get(str(PureWindowsPath(latest['meta']['execution_stage'])/name)))
        require(isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected),
                'AA_CURRENT17_FROZEN_SOURCE_PIN_MISSING: '+name)
        require(ci.file_hash(root/name) == expected, 'AA_CURRENT17_SOURCE_BYTES_DIFFER: '+name)
        source_pins[name] = expected

    selected = [('original', old50),
                ('current', [case for case in old8 if case != GAS_CASE]),
                ('current17', selected_latest)]
    unique = set()
    for label, cases in selected:
        identities = {normalize(case) for case in cases}
        require(len(identities) == len(cases) and not unique & identities,
                'AA_RETAINED_CROSS_HISTORY_IDENTITY_COLLISION')
        # This proves every chosen line exists in the authenticated raw log.
        selected_lines(histories[label]['log'].read_bytes(), cases, normalize)
        unique.update(identities)

    entry = candidate['completed']['C2CSV-MOVE-R0479']
    entry['reused_test_ids'] += ENTRAINMENT_CASES
    mapping = candidate['retained_proof']['obligation_mapping']
    header = mapping['C2CSV-MOVE-R0479']['requirements'][0]
    require('Native source header remains Scene, AC2, range4 one target' in header['obligation'],
            'AA_ENTRAINMENT_HEADER_MAPPING_PREIMAGE_DIFFERS')
    header['shared_owner_scope'] = (
        'Historical source-header/choice/grant support only. The distinct Scene, AC2 and '
        'range4 requirements below bind the authenticated current17 native boundary witnesses.')
    obligations = (
        'Scene cap one: real cast consumes quota; encounter end does not restore it; exhausted retry '
        'has no action/RNG cost; actual Scene end restores a second native cast.',
        'AC2 plus actual Speed evasion2: face3 misses and face4 hits at range4 with zero modifier; '
        'both consume ordinary action and quota, and only the hit grants the ability.',
        'Numeric range4, targets1: distance4 accepts one recipient; distance5 rejects before '
        'die/action/quota/choice/actor-state/RNG changes through the native range owner.')
    for case, obligation in zip(ENTRAINMENT_CASES, obligations):
        mapping['C2CSV-MOVE-R0479']['requirements'].append(dict(
            obligation=obligation, test_ids=[case], current_boundary_pending=[],
            evidence_binding=dict(history='current17', run=ARTIFACTS['current17']['run'],
                                  head=TESTED_HEAD), shared_owner_scope='Native dedicated boundary witness'))
    for row in mapping.values():
        for requirement in row['requirements']:
            if GAS_CASE in requirement['test_ids']:
                requirement['evidence_binding'] = dict(history='current17',
                    run=ARTIFACTS['current17']['run'], head=TESTED_HEAD,
                    reason='Same test ID, strengthened Gas-only refusal and same-event positive control; old8 PASS preserved but not selected.')
            require({normalize(case) for case in requirement.get('current_boundary_pending', [])} <= unique,
                    'AA_UNAUTHENTICATED_PENDING_REQUIREMENT')
            requirement['current_boundary_pending'] = []
    final_ids = {normalize(case) for row in candidate['completed'].values()
                 for case in row['reused_test_ids']}
    require(final_ids == unique, 'AA_TRANSFORMED_CANDIDATE_SELECTION_DIFFERS')
    for uid, row in candidate['completed'].items():
        mapped = {normalize(case) for requirement in mapping[uid]['requirements']
                  for case in requirement['test_ids']}
        require(mapped == {normalize(case) for case in row['reused_test_ids']},
                'AA_TRANSFORMED_OBLIGATION_COVERAGE_DIFFERS: '+uid)
        row['evidence_scope'] = 'Authenticated retained selection; current17 Gas replaces old8 selection only; Entrainment adds three distinct witnesses. Formal gate/publication remain separate.'
    candidate['required_test_ids'] = sorted(set(candidate['required_test_ids']) | set(ENTRAINMENT_CASES))
    candidate['required_test_modules'] = sorted(set(candidate['required_test_modules']) |
                                               {'tools.test_entrainment_header_boundaries'})
    candidate['reviewed_files'] = sorted(set(candidate['reviewed_files']) | paths)
    reference = candidate['retained_proof']
    reference['runtime_test_source_sha256'] = source_pins
    reference['current_boundary_case_ids'] = old8 + ENTRAINMENT_CASES
    reference['historical_related_case_ids'] = sorted(
        set(reference['historical_related_case_ids']) | set(ENTRAINMENT_CASES))
    reference['runtime_test_source_sha256_basis'] = (
        'Current17 H-bound frozen source pins read and compared remotely; sealed802 ledger bytes '
        'are separately identified. No live U009 metadata rebase or publication.')
    reference['impact_review']['basis'] = (
        'Original249 retained50 and current8 retained7 are conditionally reused after exact '
        'current8-to-current17 public delta verification and current17 source-byte binding. '
        'Only Living Weapon unfinished blinded-cursor movement changes runtime: ordinary AA '
        'actors have no Living Weapon pair or unfinished blinded Shift. Trickster edits only '
        'the Stacked Deck oracle, not the retained Sleight witnesses. AA fixture changes only '
        'the Gas pending-choice test, now selected from current17 with its exact Gas refusal '
        'and same-event success control. Existing original-to-current8 impact review remains '
        'historical support. Current17 Entrainment3 separately proves Scene/AC2/range4. '
        'Historical oldGas remains PASS but is excluded from retained7 selection.')
    report = dict(
        status='REMOTE_AUTHENTICATED_TRANSFORM_READY_FOR_EXISTING_GATE',
        tested_head=TESTED_HEAD, selected_by_history={label: cases for label, cases in selected},
        retained_unique_count=len(unique), current17_full_native_count=17,
        current17_selected_count=len(selected_latest), original_candidate_changed_only_in_isolated_root=True,
        reviewed_source_delta=REVIEWED_SOURCE_PATCH, changed_paths=sorted(changed),
        historical_current8_pins=old_pins, current_source_pins=source_pins,
        impact_basis=reference['impact_review']['basis'],
        publication=dict(baseline='sealed802 snapshot', live_U009_metadata_changed=True,
                         completion_count_change_from_U009=0, live_bytes_equivalent=False,
                         rebase_required=True, canonical_published=False))
    write(root/(PREFIX+'current17-impact.json'), report)
    write(work/'records/current17-transform.json', report)
    return source_pins, selected, len(unique)


def reconcile(checkout, root, work, original_pins, histories):
    sys.path.insert(0, str(checkout/'work/reuse-partials'))
    import reconcile_batch as owner
    candidate = read(root/'acceptance-stage/candidate.json')
    require(set(candidate['completed']) == CLAUSES and candidate['completed_before'] == 1798
            and candidate['existing_proof_only'] is True and not candidate['repair_only']
            and not any(candidate[name] for name in ('runtime_changes', 'test_changes', 'source_corrections', 'logs', 'execution_history')),
            'Reviewed AA candidate scope differs')
    impact = read(root/(PREFIX+'current-impact.json'))
    post = read(root/(PREFIX+'post-integration-mainbd-review.json'))
    normalize = owner.case_identity
    source_pins, selections, retained_count = current17_transform(
        checkout, root, work, candidate, impact, post, histories, original_pins, normalize)
    migration = read(root/(PREFIX+'plan-log-path-migration.json'))
    plan = read(root/PLAN)
    evidence = plan['post_foundation_reuse']['itemized_audit']['routes']['core_eldritch_magic']['evidence'][3]
    require(evidence == migration['original_evidence_record']
            and ci.file_hash(root/ci.fixture_path(migration['new_relative_path'])) == evidence['sha256'],
            'Reviewed path-only migration preimage differs')
    write(work/'records/canonical-pre-migration.json', dict(
        original_plan_sha256=original_pins[PLAN], original_evidence_record=evidence,
        new_relative_path=migration['new_relative_path'], metadata_sha256={name:original_pins[name] for name in OVERRIDES}))
    evidence['log'] = migration['new_relative_path']
    (root/PLAN).write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    root_before_evidence = {name:ci.file_hash(root/name) for name in original_pins}
    stage = work/'publication-stage'
    stage.mkdir()
    candidate['staged_artifacts'] = sorted(REVIEW_FILES-{'acceptance-stage/candidate.json'})
    candidate['staged_artifacts'].append(PREFIX+'current17-impact.json')
    reused = []
    for label, selected in selections:
        history = histories[label]
        relative = PREFIX + {'original':'original249.log', 'current':'remote40894552221-current8.log',
                             'current17':'remote40989718755-current17.log'}[label]
        body = history['log'].read_bytes()
        target = root/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(body)
        reused.append(dict(log=relative, raw_sha256=hashlib.sha256(body).hexdigest(),
                           named_pass=selected_lines(body, selected, normalize)))
        candidate['staged_artifacts'].append(relative)
    binding_name = PREFIX+'physical-source-binding.json'
    write(root/binding_name, {label:value['provenance'] for label,value in histories.items()})
    candidate['staged_artifacts'].append(binding_name)
    proof_name = PREFIX+'retained-proof.json'
    proof = dict(runtime_test_source_sha256=source_pins, stable_read_only_inputs=True,
                 new_game_test_count=0, new_game_test_ids=[],
                 remaining_implementation_obligations=[], mandatory_unanswered_questions=[],
                 reused_evidence=reused, physical_source_binding=binding_name,
                 historical_game_runs_unchanged=True)
    write(root/proof_name, proof)
    candidate['staged_artifacts'].append(proof_name)
    candidate['retained_proof']['path'] = proof_name
    candidate['retained_proof']['sha256'] = ci.file_hash(root/proof_name)
    # Historical full archives are pinned as full archives, never as their inner frozen ZIP.
    evidence_root = work/'evidence-store'
    candidate['retained_proof']['impact_review']['historical_inputs'] = [
        gate_reference(history, ARTIFACTS[label], evidence_root)
        for label, history in histories.items()]
    catalog_name = PREFIX+'evidence-catalog.json'
    write(root/catalog_name, dict(schema_version=1, reference_root='materialized-evidence-store',
        objects=[row for history in histories.values() for row in history['provenance']['evidence_objects']],
        recovery='Resolve the stable IDs through the original API or an explicitly approved sealed acquisition anchor; materialize full ZIPs before the unchanged gate.'))
    candidate['staged_artifacts'].append(catalog_name)
    candidate['status'] = 'retained_candidate_ready_for_existing_gate'
    for name in candidate['staged_artifacts']:
        target = stage/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/name, target)
    write(stage/'baseline.json', {name:ci.file_hash(root/name) for name in candidate['staged_artifacts']})
    write(stage/'candidate.json', candidate)
    for label, extra in (('preflight', ['--preflight-only']), ('reconcile', [])):
        outcome = ci.run_command([sys.executable, '-B', '-X', 'utf8',
            str(checkout/'work/reuse-partials/reconcile_batch.py'), str(stage/'candidate.json'),
            '--stage', str(stage), '--repo-root', str(root), *extra],
            evidence_root, work/('records/'+label+'.log'), timeout=1500)
        require(outcome['exit_code'] == 0, 'Existing '+label+' gate rejected admission')
    names = read(stage/(candidate['id']+'-artifacts.json'))
    require(len(names) == len(set(names)), 'Artifact manifest repeats a destination')
    progress = read(stage/'data/verification/category2-progress.json')
    require(progress['completed_clause_count'] == 1802 and not progress['validation_errors'],
            'Existing final reporter did not reconcile the exact proposed delta')
    require(all(ci.file_hash(root/name) == expected for name,expected in root_before_evidence.items()),
            'Admission input root changed during reconciliation')
    remote_baseline = read(stage/'baseline.json')
    write(stage/'baseline.remote-admission.json', remote_baseline)
    # Export canonical preimages separately from the isolated, migrated admission root.
    canonical_baseline = {name: (None if name.startswith(PREFIX) else original_pins.get(name)) for name in names}
    (stage/'baseline.json').write_text(json.dumps(canonical_baseline, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    write(work/'records/publication-baseline-binding.json', dict(
        canonical_pre_migration=canonical_baseline, remote_admission=remote_baseline,
        path_migration=migration, staged_sha256={name:ci.file_hash(stage/name) for name in names},
        no_canonical_publication=True, no_main_merge=True,
        canonical_preimage_scope='sealed802 snapshot, not current live canonical bytes',
        live_U009_metadata_changed=True, U009_completion_count_change=0,
        publication_rebase_required=True))
    return names, retained_count


def self_check():
    rows = [dict(path=name, size=0, sha256='0'*64) for name in sorted(OVERRIDES)]
    replaced = [dict(row, sha256='1'*64) for row in rows]
    combined = combined_rows({'version':1,'files':rows}, {'version':1,'files':replaced}, [])
    assert all(row['sha256'] == '1'*64 for row in combined['files'])
    for bad in ('../outside', 'C:/outside', 'data\\outside', 'tools/ci_attack.py'):
        try:
            ci.fixture_rows({'version':1,'files':[dict(path=bad,size=0,sha256='0'*64)]}, [])
        except ValueError:
            pass
        else:
            raise AssertionError('Unsafe path admitted')
    try:
        combined_rows({'version':1,'files':rows}, {'version':1,'files':replaced}, [rows[0]['path']])
    except ValueError:
        pass
    else:
        raise AssertionError('Protected tracked file admitted')
    print(json.dumps(dict(status='AA_ADAPTER_SELF_CHECK_PASS', game_runs=0, clause_credit=0)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--expected-package-blob')
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--recovery-root', type=Path, help='Optional approved recovery store; no anchors currently installed')
    args = parser.parse_args()
    key = os.environ.pop('PTK_FIXTURE_KEY', None)
    policy = os.environ.pop(ci.PRIVATE_POLICY_ENV, None)
    token = os.environ.pop('GH_TOKEN', None)
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and os.environ.get('GITHUB_REF') == BRANCH, 'Exact approved Actions branch required')
    if args.self_check:
        self_check()
        return 0
    checkout = args.root.resolve()
    temporary = Path(os.environ['RUNNER_TEMP']).resolve()
    require(checkout.drive.upper() == temporary.drive.upper() == 'D:', 'D-only checkout and temporary paths required')
    work = temporary/'aa-admission'
    work.mkdir(exist_ok=False)
    (work/'records').mkdir()
    public = checkout/'output/ci/aa-acceptance'
    public.mkdir(parents=True, exist_ok=False)
    summary = dict(status='AA_ADMISSION_NOT_ACCEPTED', run=os.environ['GITHUB_RUN_ID'],
                   head=os.environ['GITHUB_SHA'], historical_runs=[40452378890,40894552221,40989718755],
                   new_game_runs=0, completion_credit=0, canonical_published=False)
    exit_code = 1
    try:
        require(key and policy and token, 'Existing fixture, policy and artifact credentials required')
        summary['failure_stage'] = 'approved802_prepare_and_manifest_schema'
        root, original_pins = prepare_inputs(checkout, work, key, policy, args.expected_package_blob)
        histories = {}
        for label in ARTIFACTS:
            summary['failure_stage'] = 'authenticate_history_'+label
            histories[label] = authenticate_history(checkout, work, token, key, label, args.recovery_root)
        summary['failure_stage'] = 'current17_transform_and_existing_gate'
        names, retained_count = reconcile(checkout, root, work, original_pins, histories)
        summary.update(status='AA_RETAINED_ADMISSION_PASS_PUBLICATION_PENDING',
                       retained_named_passes=retained_count, proposed_clause_count=4,
                       staged_artifact_count=len(names), current17_native_count=17,
                       current17_selected_count=4, publication_rebase_required=True,
                       baseline_scope='sealed802 snapshot; live U009 metadata bytes differ')
        summary.pop('failure_stage', None)
        exit_code = 0
    except Exception as error:
        message = str(error)
        summary['failure_code'] = (message.split(':', 1)[0] if re.fullmatch(r'AA_[A-Z0-9_]+(?::.*)?', message)
                                   else 'AA_ADMISSION_GUARD_OR_RUNTIME_FAILURE')
        summary['failure_type'] = type(error).__name__
        public_owners = {str(checkout/name).replace('\\', '/').casefold(): name for name in (
            'tools/ci_aa_acceptance.py', 'tools/ci_validate.py',
            'tools/ci_remote_h.py', 'tools/ci_aa_recovery.py')}
        summary['failure_public_frames'] = [dict(path=public_owners[frame.filename.replace('\\', '/').casefold()], line=frame.lineno)
            for frame in traceback.extract_tb(error.__traceback__)
            if frame.filename.replace('\\', '/').casefold() in public_owners]
        (work/'records/private-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
    try:
        plaintext = work/'generated-artifacts.zip'
        with zipfile.ZipFile(plaintext, 'x', compression=zipfile.ZIP_STORED) as archive:
            for directory in (work/'records', work/'publication-stage'):
                if directory.exists():
                    for path in sorted(directory.rglob('*')):
                        if path.is_file():
                            require(not path.is_symlink() and path.resolve().is_relative_to(work), 'Generated artifact escapes private root')
                            archive.write(path, path.relative_to(work).as_posix())
        crypt(checkout, 'encrypt', plaintext, public/'acceptance.zip.enc', key)
        summary['encrypted_output_sha256'] = ci.file_hash(public/'acceptance.zip.enc')
    except Exception:
        summary['status'] = 'AA_OUTPUT_ENCRYPTION_FAILED'
        exit_code = 1
    write(public/'summary.json', summary)
    print(json.dumps(summary))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())

