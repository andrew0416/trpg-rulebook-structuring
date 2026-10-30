"""Draft historical-artifact recovery; no approved offline anchors are installed."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import urllib.error
import urllib.request
from urllib.parse import urlparse

import ci_validate as ci
from ci_remote_h import crypt

# An empty map is intentional. Source preparation does not approve trust anchors.
# Future reviewed entries: history_id -> {ciphertext_sha256, approval_reference}.
APPROVED_RECOVERY_ANCHORS = {}


def require(value, message):
    if not value:
        raise ValueError(message)


def history_id(bound):
    return f"gh-actions-{bound['run']}-attempt-1-artifact-{bound['id']}"


def api_url(repository, bound):
    return f"https://api.github.com/repos/{repository}/actions/artifacts/{bound['id']}"


def verify_api(record, bound):
    require(record['id'] == bound['id'] and record['name'] == bound['name']
            and record['size_in_bytes'] == bound['size']
            and record['workflow_run']['id'] == bound['run']
            and record['workflow_run']['head_sha'] == bound['head']
            and record['digest'] == 'sha256:' + bound['digest']
            and type(record['expired']) is bool, 'Original API artifact binding differs')


class ArtifactUnavailable(Exception):
    """Availability failure only; never content or provenance disagreement."""


class ArtifactRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        target = urlparse(url)
        host = target.hostname or ''
        require(target.scheme == 'https' and (host == 'api.github.com'
                or host.endswith('.blob.core.windows.net')
                or host.endswith('.githubusercontent.com')), 'Unexpected artifact redirect')
        redirected = super().redirect_request(request, fp, code, message, headers, url)
        if host != 'api.github.com':
            redirected.remove_header('Authorization')
        return redirected


def unavailable(error):
    # Auth/permission errors and malformed replies are not alternate-source permission.
    if isinstance(error, urllib.error.HTTPError):
        return error.code in {404, 410, 429, 500, 502, 503, 504}
    return isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError))


def safe_file(root, relative):
    relative = ci.fixture_path(relative)
    root = Path(root)
    require(root.is_absolute() and not root.is_symlink(), 'Recovery root must be explicit and not a symlink')
    resolved = root.resolve(strict=True)
    require(resolved.drive.upper() == 'D:', 'Recovery inputs must stay on D:')
    target = root / relative
    require(target.resolve(strict=True).is_relative_to(resolved), 'Recovery input leaves its root')
    current = target
    while current != root:
        require(not current.is_symlink(), 'Recovery input contains a symlink')
        current = current.parent
    require(target.is_file(), 'Recovery object is missing or not a file')
    return target


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate acquisition-anchor JSON key')
        result[key] = value
    return result


def load_anchor(checkout, work, key, repository, bound, recovery_root):
    evidence_id = history_id(bound)
    approval = APPROVED_RECOVERY_ANCHORS.get(evidence_id)
    require(approval is not None and recovery_root is not None,
            'Offline recovery requires an explicitly approved sealed acquisition anchor')
    require(set(approval) == {'ciphertext_sha256', 'approval_reference'}
            and re.fullmatch(r'[0-9a-f]{64}', approval['ciphertext_sha256'])
            and isinstance(approval['approval_reference'], str)
            and approval['approval_reference'].strip(), 'Invalid recovery approval configuration')
    sealed = safe_file(recovery_root, evidence_id + '/acquisition.json.enc')
    require(ci.file_hash(sealed) == approval['ciphertext_sha256'], 'Approved sealed anchor bytes differ')
    plaintext = work / 'records' / (evidence_id + '-acquisition.json')
    crypt(checkout, 'decrypt', sealed, plaintext, key)
    anchor = json.loads(plaintext.read_bytes(), object_pairs_hook=unique_object)
    require(set(anchor) == {'schema_version', 'kind', 'evidence_id', 'repository',
                           'acquired_at', 'api_url', 'api', 'run', 'h_summary', 'objects'}
            and type(anchor['schema_version']) is int and anchor['schema_version'] == 1 and anchor['kind'] == 'aa_history_acquisition'
            and anchor['evidence_id'] == evidence_id and anchor['repository'] == repository
            and anchor['api_url'] == api_url(repository, bound), 'Acquisition anchor scope differs')
    acquired = datetime.fromisoformat(anchor['acquired_at'])
    require(acquired.utcoffset() == timezone.utc.utcoffset(acquired), 'Acquisition time must identify UTC')
    verify_api(anchor['api'], bound)
    require(anchor['api']['expired'] is False, 'Anchor was not acquired from an available original artifact')
    run, summary = anchor['run'], anchor['h_summary']
    require(run['git_sha'] == bound['head']
            and run['ci']['GITHUB_REPOSITORY'] == repository
            and run['ci']['GITHUB_RUN_ID'] == str(bound['run'])
            and run['ci']['GITHUB_RUN_ATTEMPT'] == '1'
            and summary['run'] == str(bound['run']) and summary['attempt'] == '1'
            and summary['head'] == bound['head'], 'Acquisition run/head/attempt differs')
    kinds = {'github_artifact_zip', 'encrypted_evidence', 'full_evidence_zip', 'frozen_inputs_zip'}
    objects = anchor['objects']
    require(isinstance(objects, list) and len(objects) == 4
            and {row['kind'] for row in objects} == kinds
            and len({row['id'].casefold() for row in objects}) == 4, 'Acquisition object kinds or IDs differ')
    for row in objects:
        require(type(row['size']) is int and row['size'] > 0
                and isinstance(row['sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', row['sha256']),
                'Approved anchor cannot contain unknown object sizes or digests')
    return anchor, dict(kind='approved_sealed_anchor', evidence_id=evidence_id,
                       sealed_anchor_sha256=approval['ciphertext_sha256'],
                       approval_reference=approval['approval_reference'])


def retrieve_artifact(checkout, bound, work, token, key, repository, recovery_root=None):
    opener = urllib.request.build_opener(ArtifactRedirect())
    url = api_url(repository, bound)
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28'}
    try:
        try:
            with opener.open(urllib.request.Request(url, headers=headers), timeout=90) as response:
                record = json.load(response)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if not unavailable(error):
                raise
            raise ArtifactUnavailable(type(error).__name__) from error
        # Validate identity before checking expiry. A live mismatch must never fall back.
        verify_api(record, bound)
        if record['expired']:
            raise ArtifactUnavailable('expired')
        output = work / f"artifact-{bound['id']}.zip"
        try:
            with opener.open(urllib.request.Request(url + '/zip', headers=headers), timeout=180) as response, output.open('xb') as stream:
                shutil.copyfileobj(response, stream)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if not unavailable(error):
                raise
            # Preserve partial downloads as failed-attempt evidence, never overwrite them.
            raise ArtifactUnavailable(type(error).__name__) from error
        require(output.stat().st_size == bound['size'] and ci.file_hash(output) == bound['digest'],
                'Original artifact archive bytes differ')
        return output, record, None, dict(kind='live_api', evidence_id=history_id(bound),
            acquired_at=datetime.now(timezone.utc).isoformat(), api_url=url)
    except ArtifactUnavailable as error:
        anchor, acquisition = load_anchor(checkout, work, key, repository, bound, recovery_root)
        output = safe_file(recovery_root, history_id(bound) + '/github-artifact.zip')
        require(output.stat().st_size == bound['size'] and ci.file_hash(output) == bound['digest'],
                'Retained original GitHub artifact bytes differ')
        acquisition['live_unavailability'] = str(error)
        return output, anchor['api'], anchor, acquisition


def history_objects(bound, repository, outer, cipher, full, frozen, meta, members):
    evidence_id = history_id(bound)
    paths = dict(execution_stage=meta['execution_stage'], metadata=meta['metadata_path'],
                 raw_log=meta['raw_log'], frozen_inputs=meta['frozen_inputs'])
    specs = (
        ('github_artifact_zip', outer, dict(kind='github_artifact', url=api_url(repository, bound),
                                          recovery_path=evidence_id + '/github-artifact.zip')),
        ('encrypted_evidence', cipher, dict(kind='archive_member',
            parent_id=evidence_id + '/github_artifact_zip', member=members['evidence.zip.enc'])),
        ('full_evidence_zip', full, dict(kind='authenticated_decryption',
            parent_id=evidence_id + '/encrypted_evidence', gate_path=evidence_id + '/full-evidence.zip')),
        ('frozen_inputs_zip', frozen, dict(kind='archive_member',
            parent_id=evidence_id + '/full_evidence_zip', member='physical/ci-native-inputs.zip')),
    )
    return [dict(id=evidence_id + '/' + kind, kind=kind, size=path.stat().st_size,
                 sha256=ci.file_hash(path), location=location, run=bound['run'], attempt=1,
                 head=bound['head'], original_paths=paths) for kind, path, location in specs]


def gate_reference(history, bound, evidence_root):
    relative = history_id(bound) + '/full-evidence.zip'
    full = safe_file(evidence_root, relative)
    require(full.resolve() == history['archive'].resolve()
            and ci.file_hash(full) == bound['archive'], 'Materialized full-archive reference differs')
    return dict(evidence_id=history_id(bound) + '/full_evidence_zip', kind='full_evidence_zip',
                path=relative, sha256=bound['archive'])
