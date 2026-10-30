"""Bounded read-only diagnostic of AA run40992541826; no admission or games."""
import ast
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import urllib.request
import zipfile

import ci_validate as ci
from ci_remote_h import crypt
from ci_aa_recovery import ArtifactRedirect

REPO = 'andrew0416/trpg-rulebook-structuring'
FAILED_HEAD = 'a5ae917e182e3caf129ad4df6fc78ff9057c6001'
BRANCH = 'refs/heads/codex/aa-admission-diagnostic-1030'
RUN = 40992541826
ARTIFACT = 12949961574
OUTER_SHA = 'f40eeaa7c9d9d252001244b38eb1303c52a3870c61a79f4f4aa59d8fcc75775a'
CIPHER_SHA = '0ae8f954c4b7711a4d72d884d135a6ed7a30737b25243997af739237e57236b9'
BUNDLE = '.ci/aa-acceptance.zip.enc'
BLOB = '5778c37c9e25549de67dcaf2babf02ddb13cd0ef'
PUBLIC_SOURCES = ('tools/ci_aa_acceptance.py', 'tools/ci_validate.py',
                  'tools/ci_remote_h.py', 'tools/ci_aa_recovery.py')
KNOWN_KEYS = {'version','schema_version','source_count','source_members','member_count',
              'allowed_replacements','files','members','entries','path','role','size',
              'expected_sha256','source','snapshot','hash_status','source_manifest','status'}
ROLES = {'existing_prior_raw_log','current_canonical_metadata','aa_source_review'}
OVERRIDES = {'data/verification/'+name for name in (
    'category2-edge-work-plan.json','category2-work-checkpoint.json','template-reuse-checks.json',
    'template-reuse-contracts.json','category2-class-csv-clause-status.json',
    'category2-csv-abilities-moves-status.json','category2-optional-clause-status.json',
    'category2-tabular-core-status.json','category2-progress.json')}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def git(root, *args):
    return subprocess.run(['git','-C',str(root),*args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def key_shape(mapping):
    return dict(known=sorted(set(mapping) & KNOWN_KEYS),
                unknown_key_sha256=sorted(hashlib.sha256(key.encode()).hexdigest()
                                          for key in mapping if key not in KNOWN_KEYS))


def manifest_shape(value):
    result = dict(type=type(value).__name__)
    if not isinstance(value, dict):
        return result
    result.update(key_shape(value))
    result['field_types'] = {key:type(value[key]).__name__ for key in sorted(set(value)&KNOWN_KEYS)}
    result['declared_counts'] = {key:value[key] for key in (
        'version','schema_version','source_count','source_members','member_count')
        if type(value.get(key)) is int}
    replacements = value.get('allowed_replacements')
    if isinstance(replacements, list):
        result['replacements'] = dict(count=len(replacements),
            exact_approved_set=all(isinstance(x,str) for x in replacements) and set(replacements)==OVERRIDES)
    result['entry_lists'] = {}
    for label in ('files','members','entries'):
        rows = value.get(label)
        if not isinstance(rows, list):
            continue
        objects = [row for row in rows if isinstance(row,dict)]
        roles = Counter(row.get('role') for row in objects if isinstance(row.get('role'),str))
        result['entry_lists'][label] = dict(count=len(rows), object_count=len(objects),
            key_shapes=[json.loads(text) for text in sorted({json.dumps(key_shape(row),sort_keys=True) for row in objects})],
            known_role_counts={key:roles[key] for key in sorted(ROLES)},
            unknown_roles=[dict(sha256=hashlib.sha256(role.encode()).hexdigest(),count=count)
                           for role,count in sorted(roles.items()) if role not in ROLES],
            hash_field_present=sum('expected_sha256' in row for row in objects),
            null_hash_count=sum('expected_sha256' in row and row['expected_sha256'] is None for row in objects))
    return result


def reduce_error(body, sources):
    body = body.replace('\r\n', '\n')
    constants = {node.value for source in sources.values() for node in ast.walk(ast.parse(source))
                 if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value)<=240}
    reasons = re.findall(r'^ValueError: ([^\r\n]*)$',body,re.MULTILINE)
    reason = reasons[-1] if reasons else None
    result = dict(exception_type='ValueError' if reason is not None else 'unclassified',
                  static_reason=reason if reason in constants else None,
                  unknown_reason_sha256=hashlib.sha256(reason.encode()).hexdigest()
                      if reason is not None and reason not in constants else None, frames=[])
    for filename,number in re.findall(r'^  File "([^"]+)", line ([0-9]+), in .+$',body,re.MULTILINE):
        path = next((path for path in sources if filename.replace('\\','/').endswith('/'+path)),None)
        if path is not None and 0<int(number)<=len(sources[path].splitlines()):
            lines=sources[path].splitlines();line=int(number)
            result['frames'].append(dict(path=path,line=line,public_source=lines[line-1:line+2]))
    return result


def archive_names(archive, allowed, limit):
    entries = archive.infolist()
    require(len(entries)==len({e.filename for e in entries})
            and {e.filename for e in entries}<=allowed
            and sum(e.file_size for e in entries)<=limit
            and all(not e.is_dir() and stat.S_IFMT(e.external_attr>>16) in (0,stat.S_IFREG)
                    for e in entries), 'Bounded diagnostic archive shape differs')
    return {e.filename for e in entries}


def main():
    root=Path(os.environ['GITHUB_WORKSPACE']).resolve()
    temporary=Path(os.environ['RUNNER_TEMP']).resolve()
    require(root.drive.upper()==temporary.drive.upper()=='D:','D-only diagnostic required')
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')==REPO
            and os.environ.get('GITHUB_REF')==BRANCH,'Exact diagnostic Actions branch required')
    key=os.environ.pop('PTK_FIXTURE_KEY',None);token=os.environ.pop('GH_TOKEN',None)
    require(key and token,'Existing fixture key and artifact token required')
    git(root,'merge-base','--is-ancestor',FAILED_HEAD,'HEAD')
    require(set(git(root,'diff','--name-only',FAILED_HEAD,'HEAD').decode().splitlines())
            <= {'tools/ci_aa_failure_diagnostic.py','.github/workflows/validate.yml'},
            'Diagnostic child changes unrelated source')
    require(git(root,'rev-parse','HEAD:'+BUNDLE).decode().strip()==BLOB
            and git(root,'hash-object',BUNDLE).decode().strip()==BLOB,'Existing802 ciphertext differs')
    work=temporary/'aa-failure-diagnostic';work.mkdir(exist_ok=False)
    public=root/'output/ci/aa-failure-diagnostic';public.mkdir(parents=True,exist_ok=False)
    report=dict(status='AA_FAILURE_DIAGNOSTIC_NOT_COMPLETE',source_run=RUN,source_head=FAILED_HEAD,
                diagnostic_head=os.environ['GITHUB_SHA'],game_runs=0,admission_runs=0,
                clause_credit=0,canonical_published=False)
    try:
        report['stage']='authenticate_fixed_failure_artifact'
        opener=urllib.request.build_opener(ArtifactRedirect())
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
                 'X-GitHub-Api-Version':'2022-11-28'}
        url=f'https://api.github.com/repos/{REPO}/actions/artifacts/{ARTIFACT}'
        with opener.open(urllib.request.Request(url,headers=headers),timeout=90) as response:
            metadata=json.load(response)
        require(metadata['id']==ARTIFACT and metadata['name']==f'aa4-retained-admission-{RUN}-1'
                and metadata['size_in_bytes']==2224 and metadata['digest']=='sha256:'+OUTER_SHA
                and metadata['expired'] is False and metadata['workflow_run']['id']==RUN
                and metadata['workflow_run']['head_sha']==FAILED_HEAD,'Fixed failure artifact identity differs')
        outer=work/'original-failure.zip'
        with opener.open(urllib.request.Request(url+'/zip',headers=headers),timeout=90) as response,outer.open('xb') as out:
            shutil.copyfileobj(response,out)
        require(outer.stat().st_size==2224 and ci.file_hash(outer)==OUTER_SHA,'Fixed outer bytes differ')
        with zipfile.ZipFile(outer) as archive:
            names=archive_names(archive,{'summary.json','acceptance.zip.enc','adapter-console.log.enc'},65536)
            require(names=={'summary.json','acceptance.zip.enc','adapter-console.log.enc'},'Fixed outer members differ')
            summary=json.loads(archive.read('summary.json'))
            require(summary['status']=='AA_ADMISSION_NOT_ACCEPTED' and summary['run']==str(RUN)
                    and summary['head']==FAILED_HEAD and summary['failure_stage']=='approved802_prepare_and_manifest_schema'
                    and summary['failure_code']=='AA_ADMISSION_GUARD_OR_RUNTIME_FAILURE'
                    and summary['failure_type']=='ValueError' and summary['encrypted_output_sha256']==CIPHER_SHA
                    and summary['new_game_runs']==summary['completion_credit']==0
                    and summary['canonical_published'] is False,'Original failure summary differs')
            cipher=work/'original-failure.zip.enc';cipher.write_bytes(archive.read('acceptance.zip.enc'))
        require(ci.file_hash(cipher)==CIPHER_SHA,'Failed private diagnostic cipher differs')
        report['stage']='reduce_authenticated_private_error'
        full=work/'original-private-diagnostics.zip';crypt(root,'decrypt',cipher,full,key)
        sources={path:git(root,'show',FAILED_HEAD+':'+path).decode('utf-8-sig') for path in PUBLIC_SOURCES}
        # The reducer may emit only immutable public source and exact static messages.
        check=reduce_error('ValueError: PRIVATE_MARKER_DO_NOT_EMIT',sources)
        require('PRIVATE_MARKER_DO_NOT_EMIT' not in json.dumps(check),'Diagnostic reducer leaked unknown text')
        check_shape=manifest_shape({'PRIVATE_MARKER_DO_NOT_EMIT':[], 'files':[{'role':'PRIVATE_MARKER_DO_NOT_EMIT'}]})
        require('PRIVATE_MARKER_DO_NOT_EMIT' not in json.dumps(check_shape),'Manifest reducer leaked unknown key or role')
        with zipfile.ZipFile(full) as archive:
            names=archive_names(archive,{'records/private-error.txt','records/package-manifest-shape.json'},2097152)
            require('records/private-error.txt' in names,'Original private error missing')
            report['original_failure']=reduce_error(archive.read('records/private-error.txt').decode('utf-8-sig'),sources)
            report['original_shape_record_present']='records/package-manifest-shape.json' in names
        report['stage']='read_existing802_manifest_shape_only'
        package=work/'existing802.zip';crypt(root,'decrypt',root/BUNDLE,package,key)
        with zipfile.ZipFile(package) as archive:
            entries=archive.infolist();name='acceptance-input-manifest.json'
            matches=[entry for entry in entries if entry.filename==name]
            require(len(matches)==1 and matches[0].file_size<=2097152,'Bounded internal manifest required')
            unsafe=0
            for entry in entries:
                try:ci.fixture_path(entry.orig_filename)
                except ValueError:unsafe+=1
            report['package_archive_shape']=dict(member_count=len(entries),
                directory_count=sum(entry.is_dir() for entry in entries),unsafe_path_count=unsafe,
                duplicate_casefold_count=len(entries)-len({entry.filename.casefold() for entry in entries}),
                entry_type_counts=dict(Counter(str(stat.S_IFMT(entry.external_attr>>16)) for entry in entries)))
            report['manifest_shape']=manifest_shape(json.loads(archive.read(matches[0])))
        report.update(status='AA_FAILURE_DIAGNOSTIC_COMPLETE',artifact_id=ARTIFACT,outer_sha256=OUTER_SHA,
                      encrypted_diagnostic_sha256=CIPHER_SHA,approved802_git_blob=BLOB)
        report.pop('stage',None)
        code=0
    except Exception as error:
        # Never publish exception text or private traceback.
        report['diagnostic_failure_type']=type(error).__name__
        public_constants={node.value for node in ast.walk(ast.parse(Path(__file__).read_text(encoding='utf-8')))
                          if isinstance(node,ast.Constant) and isinstance(node.value,str)}
        report['static_diagnostic_reason']=str(error) if str(error) in public_constants else None
        code=1
    ci.write_json(public/'summary.json',report)
    print(json.dumps(report,ensure_ascii=False))
    return code


if __name__=='__main__':
    raise SystemExit(main())
