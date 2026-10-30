"""Bounded read-only diagnostic of AA run40997127480; no admission or games."""
import ast
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
FAILED_HEAD = '0a02f079925b993daf703ce1c6759a4daa820035'
BRANCH = 'refs/heads/codex/aa-admission-diagnostic-1030'
RUN = 40997127480
ARTIFACT = 12951832286
OUTER_SHA = 'ae75e5b0618cc2f00259c9bad223231e81aada07e10851f67f22ccecb34030eb'
CIPHER_SHA = '38d0a5aa56ab59193bc1131d79721d7b6c1d13094500e26a2eae1f27edc74100'
BUNDLE = '.ci/aa-acceptance.zip.enc'
BLOB = '5778c37c9e25549de67dcaf2babf02ddb13cd0ef'
PUBLIC_SOURCES = ('tools/ci_aa_acceptance.py', 'tools/ci_validate.py',
                  'tools/ci_remote_h.py', 'tools/ci_aa_recovery.py',
                  'work/reuse-partials/reconcile_batch.py',
                  'work/reuse-partials/acceptance_evidence.py',
                  'tools/report_category2_progress.py', 'tools/build_reuse_vault.py')
def require(ok, message):
    if not ok:
        raise ValueError(message)


def git(root, *args):
    return subprocess.run(['git','-C',str(root),*args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def reduce_error(body, sources):
    body = body.replace('\r\n', '\n')
    constants = {node.value for source in sources.values() for node in ast.walk(ast.parse(source))
                 if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value)<=240}
    reasons = re.findall(r'^(ValueError|RuntimeError|AssertionError|FileNotFoundError|OSError|KeyError|TypeError|ImportError|ModuleNotFoundError|AttributeError|PermissionError):? ?([^\r\n]*)$',body,re.MULTILINE)
    reason = reasons[-1][1] if reasons else None
    result = dict(exception_type=reasons[-1][0] if reasons else 'unclassified',
                  static_reason=reason if reason in constants else None,
                  static_reason_prefixes=sorted(value for value in constants
                      if len(value)>=16 and value.endswith(': ') and reason is not None and reason.startswith(value)),
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
            and all(not e.is_dir() and not e.flag_bits & 1 and stat.S_IFMT(e.external_attr>>16) in (0,stat.S_IFREG)
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
                diagnostic_head=os.environ['GITHUB_SHA'],game_runs=0,admission_runs=0,gate_runs=0,h_reruns=0,
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
                and metadata['size_in_bytes']==1323453 and metadata['digest']=='sha256:'+OUTER_SHA
                and metadata['expired'] is False and metadata['workflow_run']['id']==RUN
                and metadata['workflow_run']['head_sha']==FAILED_HEAD,'Fixed failure artifact identity differs')
        outer=work/'original-failure.zip'
        with opener.open(urllib.request.Request(url+'/zip',headers=headers),timeout=90) as response,outer.open('xb') as out:
            shutil.copyfileobj(response,out)
        require(outer.stat().st_size==1323453 and ci.file_hash(outer)==OUTER_SHA,'Fixed outer bytes differ')
        with zipfile.ZipFile(outer) as archive:
            names=archive_names(archive,{'summary.json','acceptance.zip.enc','adapter-console.log.enc'},4194304)
            require(names=={'summary.json','acceptance.zip.enc','adapter-console.log.enc'},'Fixed outer members differ')
            summary=json.loads(archive.read('summary.json'))
            require(summary['status']=='AA_ADMISSION_NOT_ACCEPTED' and summary['run']==str(RUN)
                    and summary['head']==FAILED_HEAD and summary['failure_stage']=='current17_transform_and_existing_gate'
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
        for kind in ('RuntimeError','AssertionError','FileNotFoundError'):
            check=reduce_error(kind+': PRIVATE_MARKER_DO_NOT_EMIT',sources)
            require(check['exception_type']==kind and 'PRIVATE_MARKER_DO_NOT_EMIT' not in json.dumps(check),
                    'Gate diagnostic reducer leaked unknown text')
        check=reduce_error('  File "D:/PRIVATE_MARKER_DO_NOT_EMIT/unknown.py", line 1, in secret\n'
                           'RuntimeError: retained input SHA256 mismatch: PRIVATE_MARKER_DO_NOT_EMIT',sources)
        require(not check['frames'] and check['static_reason_prefixes']==['retained input SHA256 mismatch: ']
                and 'PRIVATE_MARKER_DO_NOT_EMIT' not in json.dumps(check),'Gate diagnostic prefix or frame reduction differs')
        check=reduce_error('  File "D:/PRIVATE_MARKER_DO_NOT_EMIT/work/reuse-partials/reconcile_batch.py", line 581, in require\n'
                           'RuntimeError: retained proof contains unassigned named coverage',sources)
        require(len(check['frames'])==1 and check['frames'][0]['path']=='work/reuse-partials/reconcile_batch.py'
                and check['static_reason']=='retained proof contains unassigned named coverage'
                and 'PRIVATE_MARKER_DO_NOT_EMIT' not in json.dumps(check),'Public gate frame reduction differs')
        with zipfile.ZipFile(full) as archive:
            entries=archive.infolist()
            records={'records/private-error.txt','records/package-manifest-shape.json',
                     'records/authenticated-package.json','records/original-physical-binding.json',
                     'records/current-physical-binding.json','records/current17-physical-binding.json',
                     'records/current8-to-current17-reviewed.patch','records/current17-transform.json',
                     'records/canonical-pre-migration.json','records/publication-baseline-binding.json',
                     'records/preflight.log','records/reconcile.log'}
            require(len(entries)<=4096,'Bounded retained diagnostic member count required')
            for entry in entries:
                ci.fixture_path(entry.orig_filename)
            allowed=records|{entry.filename for entry in entries if entry.filename.startswith('publication-stage/')}
            names=archive_names(archive,allowed,67108864)
            require(len(names)==len({name.casefold() for name in names})
                    and {'records/private-error.txt','records/preflight.log'}<=names,
                    'Original retained gate diagnostic shape differs')
            require(archive.getinfo('records/private-error.txt').file_size<=2097152,'Bounded original error required')
            report['original_failure']=reduce_error(archive.read('records/private-error.txt').decode('utf-8-sig'),sources)
            report['retained_gate_logs']={}
            for label in ('preflight','reconcile'):
                name='records/'+label+'.log'
                if name not in names:
                    report['retained_gate_logs'][label]={'present':False}
                    continue
                require(archive.getinfo(name).file_size<=2097152,'Bounded retained gate log required')
                body=archive.read(name).decode('utf-8-sig')
                report['retained_gate_logs'][label]=dict(present=True,**reduce_error(body,sources))
                if label=='preflight':
                    report['retained_gate_logs'][label]['pass_marker_present']='Candidate metadata preflight PASS' in body.splitlines()
        report['reducer_self_checks_passed']=True
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
