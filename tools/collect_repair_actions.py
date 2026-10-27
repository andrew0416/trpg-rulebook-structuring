"""Collect small authenticated diagnostics first, then preserve full CI evidence."""
import argparse,ctypes,datetime,hashlib,json,os,re,subprocess,sys,time,zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4
import collect_typed_results as TYPED

DEFAULT_BASE=Path('D:/trpg-rulebook-structuring/work/public-actions-20261023')
DEFAULT_NODE=Path('C:/Users/admin/AppData/Local/hermes/node/node.exe')

def stamp():return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')

def emit(event,**values):print(json.dumps(dict(event=event,**values),ensure_ascii=False),flush=True)

def create_json(path,value):
 with path.open('x',encoding='utf-8') as out:json.dump(value,out,ensure_ascii=False,indent=2)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def gh(*args):
 result=subprocess.run([sys.executable,'-B','-X','utf8',str(WRAPPER),*args],capture_output=True,text=True,encoding='utf-8',timeout=300)
 if result.returncode:raise RuntimeError('authenticated GitHub command failed with code '+str(result.returncode))
 return result.stdout

class Blob(ctypes.Structure):
 _fields_=[('cbData',ctypes.c_ulong),('pbData',ctypes.POINTER(ctypes.c_ubyte))]

def decrypt_new(source,destination):
 encrypted=(B/'.local/fixture-key.dpapi').read_bytes()
 raw=(ctypes.c_ubyte*len(encrypted)).from_buffer_copy(encrypted)
 incoming=Blob(len(encrypted),raw);outgoing=Blob()
 crypt32=ctypes.WinDLL('crypt32',use_last_error=True)
 kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
 crypt32.CryptUnprotectData.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(Blob)]
 crypt32.CryptUnprotectData.restype=ctypes.c_int
 kernel32.LocalFree.argtypes=[ctypes.c_void_p];kernel32.LocalFree.restype=ctypes.c_void_p
 key=bytearray();env=None
 try:
  if not crypt32.CryptUnprotectData(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(outgoing)):
   raise RuntimeError('DPAPI unprotect failed')
  if outgoing.cbData!=32:raise RuntimeError('DPAPI key length is not 32 bytes')
  key=bytearray(ctypes.string_at(outgoing.pbData,outgoing.cbData))
  env=os.environ.copy();env['PTK_FIXTURE_KEY']=key.hex()
  result=subprocess.run([str(NODE),str(CRYPTO),'decrypt',str(source),str(destination)],env=env,capture_output=True,text=True,encoding='utf-8',timeout=300)
  if result.returncode:raise RuntimeError('authenticated evidence decryption failed')
  return 'aes_256_gcm_authenticated'
 finally:
  if env is not None:env.pop('PTK_FIXTURE_KEY',None)
  for i in range(len(key)):key[i]=0
  key.clear()
  if outgoing.pbData:
   ctypes.memset(outgoing.pbData,0,outgoing.cbData);kernel32.LocalFree(outgoing.pbData)

def base_id(uid):
 return uid.split(' (',1)[0] if isinstance(uid,str) else ''

def item_id(item):return item.get('id','') if isinstance(item,dict) else item[0] if isinstance(item,(list,tuple)) and item else item if isinstance(item,str) else ''

def summarise(verifier,physical,expected):
 kind=verifier.get('kind','missing')
 durations=verifier.get('test_durations',[]) if kind=='run' else []
 timed={r['id'] for r in durations if isinstance(r,dict) and isinstance(r.get('id'),str)}
 physical_timed={r['id'] for r in physical.get('method_timings',[]) if isinstance(r,dict) and isinstance(r.get('id'),str)}
 count=verifier.get('tests_run',0) if kind=='run' else 0
 ordinary_fail=set();fixture=[];records=[]
 for field in ('failures','errors','unexpected_successes'):
  for item in verifier.get(field,[]):
   uid=item_id(item);method=base_id(uid)
   trace=item.get('traceback','') if isinstance(item,dict) else ''
   cause=next((line.strip() for line in reversed(trace.splitlines()) if line.strip()),field)
   category='method_failure' if method in timed else 'fixture_failure'
   if category=='method_failure':ordinary_fail.add(method)
   else:fixture.append(uid)
   records.append({'kind':category,'outcome':field,'id':uid,'method_id':method,'cause':cause[:700]})
 for item in verifier.get('discovery_errors',[]):
  uid=item_id(item)
  records.append({'kind':'discovery_error','id':uid,'cause':str(item.get('error',item.get('traceback','discovery error')))[:700] if isinstance(item,dict) else str(item)[:700]})
 skipped={base_id(item_id(x)) for x in verifier.get('skipped',[])} & timed
 xfailed={base_id(item_id(x)) for x in verifier.get('expected_failures',[])} & timed
 passed=timed-ordinary_fail-skipped-xfailed
 gaps=[]
 if count!=len(timed):gaps.append('tests_run differs from timed unique methods')
 if physical and timed!=physical_timed:gaps.append('verifier and physical method timings differ')
 if timed-expected:gaps.append('timed method outside this exact suite')
 if kind!='run':gaps.append('no kind=run report')
 return {'kind':kind,'reported_tests_run':count,'collected_count':len(verifier.get('collected',[])),'executed_method_ids':sorted(timed),'passed_method_ids':sorted(passed),'failed_method_ids':sorted(ordinary_fail),'skipped_method_ids':sorted(skipped),'expected_failure_method_ids':sorted(xfailed),'not_executed_method_ids':sorted(expected-timed),'fixture_failure_ids':fixture,'count_evidence_gaps':gaps,'records':records}

def summary_for_suite(suite,verifier,physical,original=None,diagnostic=False):
    declaration=packet_documents[suite]
    kind=declaration.get('execution_kind')
    actual=physical.get('execution_kind')
    if kind=='frequency_equivalence' or actual=='frequency_equivalence_gate':
        result=TYPED.frequency(verifier,physical,declaration,original,diagnostic=diagnostic)
        gate=result['frequency_gate'];credit='verified_equivalent_method_ids'
    elif kind=='procedural_runner' or actual=='procedural_runner_gate':
        result=TYPED.procedural(verifier,physical,declaration,original,diagnostic=diagnostic)
        gate=result['procedural_gate'];credit='verified_runner_ids'
    else:return summarise(verifier,physical,packets[suite])
    expected_hash=packet_hashes[suite];suffix='/.ci/suites/'+suite+'.json'
    for field in ('runtime_test_data_sha256_before','runtime_test_data_sha256_after'):
        values=physical.get(field,{})
        matches=[digest for path,digest in values.items() if path.replace(chr(92),'/').endswith(suffix)] if type(values)is dict else []
        if matches!=[expected_hash]:gate['integrity_errors'].append('frozen packet SHA lacks exact '+field+' binding')
    if gate['integrity_errors']:
        gate[credit]=[]
        gate['status']='evidence_incomplete' if gate['observed'] else 'not_observed'
        result['count_evidence_gaps']=gate['integrity_errors']
    return result



def configure(args):
    global B,F,E,RUN,HEAD,ATTEMPT,WRAPPER,NODE,CRYPTO,required,packets,packet_documents,packet_hashes,required_runners,original_scope
    B=Path(args.base).resolve();F=Path(args.freeze).resolve()
    RUN=str(args.run);HEAD=args.head;ATTEMPT=str(args.attempt);NODE=Path(args.node)
    if not re.fullmatch(r'[1-9][0-9]*',RUN) or not re.fullmatch(r'[0-9a-f]{40}',HEAD):
        raise ValueError('explicit numeric run and full lowercase commit SHA required')
    if not re.fullmatch(r'[1-9][0-9]*',ATTEMPT):
        raise ValueError('positive run attempt required')
    plan=json.loads((F/'focused-required-union.json').read_text(encoding='utf-8-sig'))
    values=plan['required_test_ids'];required=set(values)
    if len(required)!=len(values) or any(type(v)is not str or not v for v in values):
        raise ValueError('nonempty unique frozen required IDs needed')
    original_scope=plan.get('original_final_union_preserved')
    declaration=F/'focused-freeze.json'
    names=([row['id'] for row in json.loads(declaration.read_text(encoding='utf-8-sig'))['suites']]
           if declaration.exists() else [p.stem for p in sorted((F/'stage/.ci/suites').glob('repair_revisions_*.json'))])
    if not names or len(set(names))!=len(names):
        raise ValueError('distinct frozen suite names required')
    packets={};packet_documents={};packet_hashes={};required_runners=set()
    for name in names:
        if not re.fullmatch(r'[A-Za-z0-9_-]+',name):raise ValueError('unsafe suite identity')
        data=json.loads((F/'stage/.ci/suites'/ (name+'.json')).read_text(encoding='utf-8-sig'))
        packet_documents[name]=data
        packet_hashes[name]=sha(F/'stage/.ci/suites'/(name+'.json'))
        if data.get('execution_kind')=='procedural_runner':
            ids=data.get('required_runner_ids')
            if type(ids)is not list or len(ids)!=1 or type(ids[0])is not str or ids[0]!=data.get('unit_id') or not ids[0].startswith('script:') or data.get('completed')!={}:
                raise ValueError('procedural packet requires its separate exact original runner identity')
            if required_runners.intersection(ids):raise ValueError('procedural runner allocated more than once')
            required_runners.update(ids);packets[name]=set()
        else:
            if data.get('execution_kind') not in (None,'frequency_equivalence'):raise ValueError('unknown suite execution kind')
            declared=[uid for row in data['completed'].values() for uid in row['tests']]
            if any(type(uid)is not str or not uid for uid in declared):raise ValueError('exact frozen method IDs required')
            if len(declared)!=len(set(declared)):raise ValueError('duplicate methods within frozen suite')
            if set(declared).intersection(set().union(*packets.values())):raise ValueError('method allocated to multiple suites')
            packets[name]=set(declared)
    if not required and not required_runners:raise ValueError('nonempty frozen method or runner scope required')
    if 'required_runner_ids' in plan and set(plan['required_runner_ids'])!=required_runners:
        raise ValueError('frozen procedural runner union differs from separate required IDs')
    if set().union(*packets.values())!=required:
        raise ValueError('frozen suite union differs from required IDs')
    WRAPPER=B/'review/gh_authenticated.py';CRYPTO=B/'repository/tools/ci_fixtures.mjs'
    E=F/'actions-evidence';E.mkdir(parents=True,exist_ok=True)

def decrypt(source,destination):
    # Existing plaintext is reauthenticated, never trusted merely because it exists.
    if destination.is_symlink() or not destination.resolve().is_relative_to(E.resolve()):
        raise ValueError('evidence output leaves its freeze')
    temporary=destination.with_name(destination.name+'.reauth-'+uuid4().hex) if destination.exists() else None
    output=temporary or destination
    try:
        result=decrypt_new(source,output)
        if temporary is not None:
            if sha(temporary)!=sha(destination):raise RuntimeError('existing plaintext differs from authenticated archive')
            return 'aes_256_gcm_authenticated_rechecked'
        return result
    finally:
        if temporary is not None and temporary.exists():
            if not temporary.resolve().is_relative_to(E.resolve()):raise ValueError('temporary evidence leaves its freeze')
            temporary.unlink()

def artifact_metadata(suite,diagnostic=False):
    prefix='diagnostics' if diagnostic else 'validation'
    folder=E/(prefix+'-'+suite+'-'+RUN+'-'+ATTEMPT)
    if not folder.exists():gh('run','download',RUN,'--name',folder.name,'--dir',str(folder))
    else:emit('preserving_artifact_folder',suite=suite,kind=prefix)
    paths=list(folder.glob('*/run.json'))
    if len(paths)!=1:raise RuntimeError('artifact must contain exactly one direct UUID/run.json')
    path=paths[0]
    if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
        raise RuntimeError('artifact metadata leaves its download folder')
    metadata=json.loads(path.read_text(encoding='utf-8-sig'))
    if (metadata.get('git_sha')!=HEAD or metadata.get('suite')!=suite
        or metadata.get('ci',{}).get('GITHUB_RUN_ID')!=RUN
        or metadata.get('ci',{}).get('GITHUB_RUN_ATTEMPT')!=ATTEMPT
        or metadata.get('ci',{}).get('GITHUB_SHA')!=HEAD
        or metadata.get('evidence_id')!=path.parent.name):
        raise RuntimeError('artifact run/head/attempt/suite/evidence identity mismatch')
    return folder,path.parent,metadata

def read_reports(destination,diagnostic,encrypted):
    with zipfile.ZipFile(destination) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)):raise RuntimeError('duplicate evidence archive member')
        if any('\\' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts for name in names):
            raise RuntimeError('unsafe evidence archive member')
        scope=None
        if diagnostic:
            scope=json.loads(archive.read('diagnostic-scope.json'))
            if (scope.get('schema_version')!=1 or scope.get('kind')!='diagnostic_only'
                or scope.get('complete_input_capture') is not False):
                raise RuntimeError('small artifact is not explicitly diagnostic-only')
            full=scope.get('full_evidence',{})
            if any(full.get(k)!=encrypted.get(k) for k in ('file','sha256','raw_file_count')):
                raise RuntimeError('diagnostic/full archive binding mismatch')
            excluded=scope.get('excluded_input_archives')
            if not isinstance(excluded,dict) or any(not name.endswith('.zip') or name in names
                or not re.fullmatch(r'[0-9a-f]{64}',digest) for name,digest in excluded.items()):
                raise RuntimeError('invalid diagnostic input exclusions')
        elif 'diagnostic-scope.json' in names:
            raise RuntimeError('diagnostic archive cannot stand in for full evidence')
        selected=[name for name in names if re.fullmatch(r'verifier/tests-[^/]+\.json',name)]
        if len(selected)>1:raise RuntimeError('multiple verifier reports need explicit reconciliation')
        verifier_raw=archive.read(selected[0]) if selected else None
        verifier=json.loads(verifier_raw) if verifier_raw is not None else {}
        physical=json.loads(archive.read('physical/ci-native.json')) if 'physical/ci-native.json' in names else {}
        typed=TYPED.read_original(archive,physical)
        reports=[]
        if verifier_raw is not None:
            reports.append({'kind':'original_verifier','member':selected[0],
                            'sha256':hashlib.sha256(verifier_raw).hexdigest(),
                            'original_path':physical.get('original_cli_report')})
        if typed is not None:reports.append({key:value for key,value in typed.items() if key!='report'})
        return verifier,physical,scope,typed,reports

def collect(suite,diagnostic=False):
    folder,directory,metadata=artifact_metadata(suite,diagnostic)
    encrypted=metadata.get('encrypted_evidence')
    if not isinstance(encrypted,dict):
        if diagnostic:raise RuntimeError('terminal artifact has no encrypted diagnostics')
        return {'suite':suite,'run_metadata':metadata,'artifact_path':str(folder),
                'classification':'fixture_failure','collection_error':'terminal artifact has no encrypted native evidence',
                'verifier':{},'physical':{},'execution':summary_for_suite(suite,{}, {},diagnostic=diagnostic)}
    descriptor=encrypted.get('diagnostics') if diagnostic else encrypted
    if not isinstance(descriptor,dict):raise RuntimeError('small diagnostic not produced; full archive required')
    filename=descriptor.get('file')
    if filename!=('diagnostics.zip.enc' if diagnostic else 'evidence.zip.enc'):
        raise RuntimeError('unexpected encrypted evidence filename')
    if not re.fullmatch(r'[0-9a-f]{64}',descriptor.get('sha256','')):
        raise RuntimeError('exact encrypted SHA256 required')
    if diagnostic and descriptor.get('complete_input_capture') is not False:
        raise RuntimeError('diagnostic metadata cannot claim complete inputs')
    source=directory/filename
    if source.is_symlink() or not source.resolve().is_relative_to(folder.resolve()):
        raise RuntimeError('encrypted evidence leaves its artifact')
    if sha(source)!=descriptor['sha256']:raise RuntimeError('encrypted evidence SHA256 mismatch')
    destination=directory/('diagnostics-evidence.zip' if diagnostic else 'native-evidence.zip')
    auth=decrypt(source,destination)
    verifier,physical,scope,typed,reports=read_reports(destination,diagnostic,encrypted)
    result={'suite':suite,'run_metadata':metadata,'artifact_path':str(folder),
            'authenticated_encrypted_sha256':descriptor['sha256'],'decryption':auth,
            'native_archive_sha256':sha(destination),'verifier':verifier,
            'execution':summary_for_suite(suite,verifier,physical,typed,diagnostic),
            'source_reports':reports}
    if diagnostic:
        result.update(kind='diagnostic_only',complete_input_capture=False,acceptance_eligible=False,
                      completion_credit=0,diagnostic_scope=scope,physical_metadata=physical)
    else:
        result['physical']=physical
    if not verifier and result['execution']['kind'] not in TYPED.REPORTS:result['classification']='fixture_failure'
    return result

def analyse(status,results,problems,diagnostic=False):
    executed=set();passed=set();failed=set();skipped=set();xfailed=set();groups={}
    fixture_count=0;discovery_count=0;reported=0
    frequency_gates=[];procedural_gates=[]
    for result in results.values():
        exe=result['execution']
        if 'frequency_gate' in exe:frequency_gates.append(dict(exe['frequency_gate'],suite=result['suite']))
        if 'procedural_gate' in exe:procedural_gates.append(dict(exe['procedural_gate'],suite=result['suite']))
        executed.update(exe['executed_method_ids']);passed.update(exe['passed_method_ids'])
        failed.update(exe['failed_method_ids']);skipped.update(exe['skipped_method_ids'])
        xfailed.update(exe['expected_failure_method_ids']);reported+=exe['reported_tests_run']
        fixture_count+=int(result.get('classification')=='fixture_failure')
        for record in exe['records']:
            kind=record['kind'];fixture_count+=int(kind=='fixture_failure');discovery_count+=int(kind=='discovery_error')
            group=groups.setdefault((kind,record['cause']),{'kind':kind,'cause':record['cause'],'occurrences':0,'items':[]})
            group['occurrences']+=1;group['items'].append({'suite':result['suite'],'id':record['id']})
    conflicts=passed&failed;passed-=failed
    frequency_declared=set().union(*(packets[suite] for suite,packet in packet_documents.items() if packet.get('execution_kind')=='frequency_equivalence'))
    ordinary_required=required-frequency_declared
    frequency_observed=set().union(*(set(gate['observed_method_ids']) for gate in frequency_gates))
    frequency_verified=set().union(*(set(gate['verified_equivalent_method_ids']) for gate in frequency_gates))
    ordinary_unknown=set().union(*(ids for suite,ids in packets.items() if packet_documents[suite].get('execution_kind') not in ('frequency_equivalence','procedural_runner') and (suite not in results or results[suite]['execution']['kind']!='run' or results[suite]['execution']['count_evidence_gaps'])))-executed
    unknown=ordinary_unknown|(frequency_declared-frequency_observed)
    not_executed=ordinary_required-executed-ordinary_unknown
    procedural_observed=set().union(*(set(gate['observed_runner_ids']) for gate in procedural_gates))
    procedural_verified=set().union(*(set(gate['verified_runner_ids']) for gate in procedural_gates))
    procedural_not_executed=set().union(*(set(gate['not_executed_runner_ids']) for gate in procedural_gates))
    procedural_unobserved=required_runners-procedural_observed-procedural_not_executed
    report={'run':RUN,'commit':HEAD,'attempt':ATTEMPT,'status':status,
            'scope':'explicit frozen method selection; no independent acceptance or completion credit',
            'original_final_union_preserved':original_scope,'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'suites':[results[k] for k in sorted(results)],'collection_problems':problems,
            'counts':{'terminal_suites_collected':len(results),'required':len(required),'reported_tests_run':reported,
                      'timed_executed':len(executed),'actual_pass':len(passed),'actual_fail':len(failed),'skipped':len(skipped),
                      'expected_failure':len(xfailed),'not_executed':len(not_executed),'execution_unobserved':len(unknown),
                      'fixture_failure_records':fixture_count,'discovery_error_records':discovery_count,
                      'ordinary_required_methods':len(ordinary_required),'frequency_declared_methods':len(frequency_declared),
                      'method_starts_observed_unique':len(executed|frequency_observed),
                      'frequency_observed_unique_methods':len(frequency_observed),
                      'frequency_verified_unique_methods':len(frequency_verified),
                      'frequency_observed_gates':sum(gate['observed'] for gate in frequency_gates),
                      'frequency_verified_gates':sum(bool(gate['verified_equivalent_method_ids']) for gate in frequency_gates),
                      'frequency_failed_gates':sum(gate['status']=='failed' for gate in frequency_gates),
                      'frequency_incomplete_gates':sum(gate['status']=='evidence_incomplete' for gate in frequency_gates),
                      'frequency_raw_start_events':sum(gate['observed_start_events'] for gate in frequency_gates),
                      'ordinary_pass_plus_verified_equivalence_unique':len((passed|frequency_verified)-failed),
                      'procedural_required_units':len(required_runners),'procedural_observed_units':len(procedural_observed),
                      'procedural_verified_units':len(procedural_verified),'procedural_not_executed_units':len(procedural_not_executed),
                      'procedural_execution_unobserved_units':len(procedural_unobserved),
                      'procedural_failed_gates':sum(gate['status']=='failed' for gate in procedural_gates),
                      'procedural_error_gates':sum(gate['status']=='error' for gate in procedural_gates),
                      'procedural_incomplete_gates':sum(gate['status']=='evidence_incomplete' for gate in procedural_gates)},
            'frequency_equivalence':frequency_gates,'procedural_runners':procedural_gates,
            'frequency_unverified_method_ids':sorted(frequency_declared-frequency_verified),
            'procedural_unobserved_runner_ids':sorted(procedural_unobserved),
            'accounting_note':'Ordinary method PASS/FAIL, equivalence-mode outcomes and procedural runner units are disjoint measures. Injected failure and dependent blocks never become ordinary regression failures. Report-row totals are not method counts.',
            'not_executed_method_ids':sorted(not_executed),'execution_unobserved_method_ids':sorted(unknown),'conflicting_method_outcomes':sorted(conflicts),
            'groups':list(groups.values()),'completion_credit':0,'acceptance_eligible':False}
    if diagnostic:
        report.update(kind='diagnostic_only',complete_input_capture=False,
                      scope='Early diagnostic view only; missing suites are unobserved, not evidence of execution or physical-input acceptance.')
    return report

def persist(status,results,problems,diagnostic=False):
    report=analyse(status,results,problems,diagnostic)
    prefix='diagnostic-analysis' if diagnostic else 'analysis'
    create_json(E/(prefix+'-'+stamp()+'.json'),report)
    target=F/('diagnostic-analysis.json' if diagnostic else 'failure-analysis.json')
    temporary=target.with_name(target.name+'.next')
    temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(target)
    return report

def process_completed(status,diagnostics,full,diagnostic_problems,problems,attempted):
    terminal=[job['name'] for job in status['jobs'] if job['status']=='completed' and job['name'] in packets]
    # Finish the entire small-artifact pass before downloading any full input corpus.
    for suite in terminal:
        if suite in attempted:continue
        attempted.add(suite)
        try:
            diagnostics[suite]=collect(suite,True)
            execution=diagnostics[suite]['execution']
            typed=execution.get('frequency_gate',execution.get('procedural_gate',{}))
            emit('diagnostic_collected',suite=suite,kind='diagnostic_only',
                 execution_kind=execution['kind'],ordinary_failed=len(execution['failed_method_ids']),
                 typed_status=typed.get('status'),typed_observed=typed.get('observed'))
        except Exception as exc:
            diagnostic_problems[suite]={'type':type(exc).__name__,'message':str(exc)[:300],
                                        'fallback':'full_original_archive'}
            emit('diagnostic_fallback',suite=suite,error=type(exc).__name__)
        persist(status['status'],diagnostics,diagnostic_problems,True)
    remaining=[suite for suite in terminal if suite not in full and suite not in problems]
    # Poll again after one large download while other jobs may finish.
    if status['status']!='completed':remaining=remaining[:1]
    for suite in remaining:
        try:
            result=collect(suite)
            previous=diagnostics.get(suite)
            if previous and previous.get('diagnostic_scope'):
                if (previous['run_metadata']['evidence_id']!=result['run_metadata']['evidence_id']
                    or previous['diagnostic_scope']['full_evidence']['sha256']!=result.get('authenticated_encrypted_sha256')
                    or previous['verifier']!=result['verifier']
                    or previous['physical_metadata']!=result['physical']
                    or {row['member']:row['sha256'] for row in previous.get('source_reports',[])}
                       !={row['member']:row['sha256'] for row in result.get('source_reports',[])}):
                    raise RuntimeError('diagnostic view disagrees with full authenticated original')
            full[suite]=result
            typed=result['execution'].get('frequency_gate',result['execution'].get('procedural_gate',{}))
            if typed.get('integrity_errors'):
                problems[suite]={'type':'TypedEvidenceIncomplete','message':'; '.join(typed['integrity_errors'])[:700],
                                 'execution_observed':typed.get('observed',False)}
            if previous is None:
                diagnostics[suite]={k:v for k,v in result.items() if k!='physical'}
                diagnostics[suite].update(kind='diagnostic_only',complete_input_capture=False,
                    acceptance_eligible=False,completion_credit=0,evidence_origin='full_archive_fallback',
                    physical_metadata=result['physical'])
                persist(status['status'],diagnostics,diagnostic_problems,True)
            report=persist(status['status'],full,problems)
            emit('full_suite_collected',suite=suite,**report['counts'])
        except Exception as exc:
            problems[suite]={'type':type(exc).__name__,'message':str(exc)[:300]}
            persist(status['status'],full,problems)
            emit('collection_problem',suite=suite,**problems[suite])

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True);parser.add_argument('--head',required=True)
    parser.add_argument('--freeze',type=Path,required=True);parser.add_argument('--attempt',type=int,default=1)
    parser.add_argument('--base',type=Path,default=DEFAULT_BASE);parser.add_argument('--node',type=Path,default=DEFAULT_NODE)
    args=parser.parse_args(argv);configure(args)
    diagnostics={};full={};diagnostic_problems={};problems={};attempted=set();previous=None;backoff=15
    emit('collector_started',run=RUN,head=HEAD,attempt=ATTEMPT,required=len(required),procedural_required=len(required_runners),suites=len(packets))
    while True:
        try:
            raw=gh('run','view',RUN,'--json','databaseId,headSha,status,conclusion,jobs,updatedAt,url')
            status=json.loads(raw)
        except Exception as exc:
            emit('lookup_error',error=type(exc).__name__);time.sleep(backoff);backoff=min(60,backoff*2);continue
        if str(status.get('databaseId'))!=RUN or status.get('headSha')!=HEAD:
            raise RuntimeError('observed run identity mismatch')
        with (E/('status-'+stamp()+'.json')).open('x',encoding='utf-8') as out:out.write(raw)
        (F/'run-observation.json').write_text(raw,encoding='utf-8')
        compact=[(job['name'],job['status'],job['conclusion']) for job in status['jobs']]
        backoff=15 if compact!=previous else min(60,backoff*2)
        if compact!=previous:emit('run_status',at=status['updatedAt'],status=status['status'],jobs=compact);previous=compact
        process_completed(status,diagnostics,full,diagnostic_problems,problems,attempted)
        if status['status']=='completed':
            for suite in set(packets)-set(full)-set(problems):
                problems[suite]={'type':'MissingSuiteEvidence','message':'Completed workflow has no authenticated original evidence for this required suite; execution remains unobserved.'}
            persist('completed',diagnostics,diagnostic_problems,True);persist('completed',full,problems)
            emit('collector_finished',problems=problems,diagnostic_fallbacks=diagnostic_problems,
                 report=str(F/'failure-analysis.json'));return 0 if not problems else 1
        time.sleep(backoff)

if __name__=='__main__':
    raise SystemExit(main())
