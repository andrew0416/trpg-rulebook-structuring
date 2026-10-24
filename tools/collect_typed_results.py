"""Read-only typed CI evidence accounting; never execute a test or grant ordinary PASS credit."""
import hashlib
import json
import re
from fnmatch import fnmatchcase

MODES=('cold','connected','connected_first_failure')
INJECTED='tools.test_frequencies.FrequencyTests.test_source_move_0000'
INJECTION='INJECTED_FREQUENCY_CHAIN_FAILURE_AFTER_ORIGINAL_BODY'
REPORTS={'frequency_equivalence_gate':('physical/frequency-equivalence.json','equivalence_report','equivalence_report_sha256'),
         'procedural_runner_gate':('physical/procedural-runner.json','procedural_report','procedural_report_sha256')}


def base_id(value):return value.split(' (',1)[0] if type(value)is str else ''


def read_original(archive,physical):
    """Bind raw bytes inside the authenticated archive; preserve missing/corrupt evidence explicitly."""
    kind=physical.get('execution_kind')
    if kind not in REPORTS:return None
    member,path_key,hash_key=REPORTS[kind];problems=[];expected=physical.get(hash_key)
    path=physical.get(path_key,'')
    if type(path)is not str or not path.replace('\\','/').endswith(member):problems.append('original report path does not bind the expected archive member')
    if type(expected)is not str or re.fullmatch(r'[0-9a-f]{64}',expected) is None:problems.append('original report SHA256 is absent or malformed')
    raw=None;value=None;digest=None
    if member not in archive.namelist():problems.append('original typed report is missing')
    else:
        raw=archive.read(member);digest=hashlib.sha256(raw).hexdigest()
        if digest!=expected:problems.append('original typed report SHA256 mismatch')
        try:value=json.loads(raw)
        except (UnicodeError,ValueError):problems.append('original typed report is not valid JSON')
        if type(value)is not dict:problems.append('original typed report must be an object');value=None
    result={'kind':kind,'member':member,'sha256':digest,'declared_sha256':expected,
            'original_path':path,'present':raw is not None,'report':value,'integrity_errors':problems}
    if kind=='procedural_runner_gate':
        result['original_script_report']=read_script_report(archive,value)
        result['generated_capture']=read_generated_capture(archive,physical,value)
    return result


def read_generated_capture(archive,physical,wrapper):
    issues=[];events=[];proofs={};member='physical/ci-native-events.jsonl';event_sha=None
    if member in archive.namelist():
        raw=archive.read(member);event_sha=hashlib.sha256(raw).hexdigest()
        try:
            events=[json.loads(line) for line in raw.decode('utf-8').splitlines()]
            if any(type(row)is not dict for row in events):raise ValueError('event must be object')
        except (ValueError,UnicodeError):issues.append('procedural event log malformed');events=[]
    else:issues.append('procedural event log missing')
    wrapper=wrapper if type(wrapper)is dict else {}
    mutation=wrapper.get('mutation_evidence',{})
    mutation=mutation if type(mutation)is dict else {}
    groups=[physical.get('procedural_generated_first_reads',[]),mutation.get('generated_final_artifacts',[]),wrapper.get('additional_outputs',[])]
    for rows in groups:
        if type(rows)is not list:issues.append('generated evidence declarations malformed');continue
        for row in rows:
            if type(row)is not dict:issues.append('generated evidence row malformed');continue
            path=row.get('archive_member');expected=row.get('sha256')
            if type(path)is not str or path.startswith('/') or any(x in path for x in ('\\',':')) or any(x in ('','..','.') for x in path.split('/')):
                issues.append('unsafe generated archive member');continue
            if type(expected)is not str or re.fullmatch('[0-9a-f]{64}',expected)is None:
                issues.append('generated evidence SHA malformed');continue
            if not (path=='physical/procedural-generated/'+expected+'.bin' or path.startswith('physical/procedural-additional/')):
                issues.append('generated archive member outside protocol');continue
            if path not in archive.namelist():issues.append('generated original bytes missing: '+path);continue
            actual=hashlib.sha256(archive.read(path)).hexdigest();proofs[path]=actual
            if actual!=expected:issues.append('generated original byte SHA mismatch: '+path)
    return {'events_member':member,'events_sha256':event_sha,'events':events,'member_sha256':proofs,'integrity_errors':issues}


def _relative_path(value):
    return type(value)is str and bool(value) and not any(c in value for c in ('\\',':')) and all(p not in ('','..','.') for p in value.split('/'))


def validate_generated_capture(physical,packet,wrapper,evidence):
    """Check declared generated exceptions against raw bytes and ordered write/read events."""
    issues=list(evidence.get('integrity_errors',[]));runner=packet.get('runner',{});mutation=wrapper.get('mutation_evidence',{})
    rows=physical.get('procedural_generated_first_reads',[]);stage=physical.get('execution_stage','').replace('\\','/').rstrip('/')
    before=physical.get('runtime_test_data_sha256_before',{});reads=physical.get('first_actual_read_sha256',{})
    norm=lambda path:path.replace('\\','/').casefold()
    if type(before)is not dict or type(reads)is not dict:return issues+['captured/read hash maps malformed']
    prior={norm(k):v for k,v in before.items()};actual={norm(k):v for k,v in reads.items()}
    events=evidence.get('events',[]);starts=[i for i,e in enumerate(events) if e.get('event')=='procedural_start' and e.get('unit_id')==packet.get('unit_id')]
    if len(starts)!=1:issues.append('one original procedural start event required')
    start=starts[0] if len(starts)==1 else len(events)
    if type(rows)is not list:return issues+['generated first-read metadata malformed']
    if type(mutation)is not dict:mutation={};issues.append('mutation evidence malformed')
    declared=runner.get('mutations',{});patterns=declared.get('generated_retained',[])
    outputs=[runner.get('report',{}).get('path'),*runner.get('additional_outputs',[])]
    def allowed(rel):
        return _relative_path(rel) and (rel in outputs or any(_relative_path(p) and len(rel.split('/'))==len(p.split('/')) and all(fnmatchcase(a,b) for a,b in zip(rel.split('/'),p.split('/'))) for p in patterns))
    generated={};expected_wrapper=[]
    for row in rows:
        if type(row)is not dict:issues.append('generated first-read row malformed');continue
        rel=row.get('path');file=row.get('file');digest=row.get('sha256');member=row.get('archive_member')
        if not allowed(rel):issues.append('generated path outside frozen output/mutation scope');continue
        if type(file)is not str or norm(file)!=norm(stage+'/'+rel):issues.append('generated absolute path differs from stage/source');continue
        key=norm(file)
        if key in generated:issues.append('duplicate generated input path')
        generated[key]=digest;expected_wrapper.append({k:row.get(k) for k in ('path','sha256','archive_member')})
        if key in prior:issues.append('generated input was already captured before execution')
        if actual.get(key)!=digest:issues.append('generated first-read SHA differs from physical read')
        if member!='physical/procedural-generated/'+str(digest)+'.bin' or evidence.get('member_sha256',{}).get(member)!=digest:
            issues.append('generated input lacks exact raw byte evidence')
        writes=[(i,e) for i,e in enumerate(events) if e.get('event')=='procedural_write' and type(e.get('path'))is str and norm(e['path'])==key]
        generated_events=[(i,e) for i,e in enumerate(events) if e.get('event')=='procedural_generated_first_read' and type(e.get('path'))is str and norm(e['path'])==key]
        read_events=[(i,e) for i,e in enumerate(events) if e.get('event')=='first_read' and type(e.get('file'))is str and norm(e['file'])==key]
        if not writes or len(generated_events)!=1 or len(read_events)!=1:issues.append('generated write/read event sequence missing or duplicated');continue
        wi,we=writes[0];gi,ge=generated_events[0];ri,revent=read_events[0]
        if not(start<wi<gi<ri):issues.append('generated read was not preceded by original execution write')
        if we.get('first_write')is not True or we.get('existed_before_write')is not False:issues.append('generated first write lacks absent-preimage proof')
        if type(we.get('mode'))is not str or not any(c in we['mode'] for c in 'wax+'):issues.append('generated write mode is not a write')
        if ge.get('sha256')!=digest or ge.get('archive_member')!=member or revent.get('sha256')!=digest or revent.get('captured_before')is not False or revent.get('declared_generated_input')is not True:
            issues.append('generated event hash/source flags disagree')
    if set(actual)-set(prior)!=set(generated):issues.append('uncaptured actual reads differ from declared generated inputs')
    for key,digest in actual.items():
        if key in prior and digest!=prior[key]:issues.append('original captured input first-read SHA differs')
    if wrapper.get('status')in ('passed','failed'):
        if mutation.get('temporary_inputs_restored')is not True:issues.append('temporary inputs not restored')
        if mutation.get('generated_first_reads')!=expected_wrapper:issues.append('wrapper generated reads differ from physical metadata')
    final_rows=mutation.get('generated_final_artifacts',[]);final_paths=set()
    if type(final_rows)is not list:issues.append('final generated evidence list malformed');final_rows=[]
    for row in final_rows:
        if type(row)is not dict:issues.append('final generated evidence row malformed');continue
        rel=row.get('path');digest=row.get('sha256');member=row.get('archive_member')
        if type(rel)is not str:issues.append('final generated path malformed');continue
        if rel in final_paths:issues.append('duplicate final generated path')
        final_paths.add(rel)
        if not allowed(rel) or rel in outputs or norm(stage+'/'+rel) in prior:issues.append('final generated artifact outside declared fresh mutation scope')
        if member!='physical/procedural-generated/'+str(digest)+'.bin' or evidence.get('member_sha256',{}).get(member)!=digest:issues.append('final generated artifact bytes missing/mismatched')
        if rel in declared.get('temporarily_modified_restored',[]) and generated.get(norm(stage+'/'+rel))!=digest:issues.append('generated temporary input not restored to first-read SHA')
    if wrapper.get('status')in ('passed','failed'):
        for rel in declared.get('temporarily_modified_restored',[]):
            if norm(stage+'/'+rel) not in prior and rel not in final_paths:issues.append('generated temporary restoration lacks final byte evidence')
        write_rows=mutation.get('writes',[])
        event_writes=[{'path':e['path'].replace('\\','/')[len(stage)+1:],'mode':e.get('mode'),
                       'first_write':e.get('first_write'),'existed_before_write':e.get('existed_before_write')} for e in events
                      if e.get('event')=='procedural_write' and type(e.get('path'))is str and norm(e['path']).startswith(norm(stage+'/'))]
        if write_rows!=event_writes:issues.append('wrapper writes differ from original event sequence')
        additional=wrapper.get('additional_outputs',[])
        if type(additional)is not list:issues.append('additional output declarations malformed');additional=[]
        expected_additional=set(runner.get('additional_outputs',[]));seen=set()
        for row in additional:
            if type(row)is not dict:issues.append('additional output row malformed');continue
            path=row.get('path');member=row.get('archive_member');digest=row.get('sha256')
            rel=path.replace('\\','/')[len(stage)+1:] if type(path)is str and norm(path).startswith(norm(stage+'/')) else None
            if rel not in expected_additional or rel in seen:issues.append('additional output differs from frozen scope')
            seen.add(rel)
            if member!='physical/procedural-additional/'+str(rel) or evidence.get('member_sha256',{}).get(member)!=digest:issues.append('additional output bytes missing/mismatched')
        if seen!=expected_additional:issues.append('declared additional output missing')
    return list(dict.fromkeys(issues))


def _ids(value,label,issues):
    if type(value)is not list or any(type(uid)is not str or not uid for uid in value):
        issues.append(label+' must contain exact text IDs');return []
    if len(set(value))!=len(value):issues.append(label+' contains duplicate IDs')
    return value


def _entries(value,label,issues):
    if type(value)is not list:issues.append(label+' must be a list');return []
    rows=[]
    for item in value:
        if not isinstance(item,(list,tuple)) or len(item)!=2 or any(type(v)is not str for v in item):
            issues.append(label+' contains malformed outcome');continue
        rows.append({'id':item[0],'method_id':base_id(item[0]),'detail':item[1]})
    return rows


def _capture_issues(physical):
    issues=[]
    for key in ('stable_hashes','complete_pre_input_capture','complete_loaded_input_capture','physical_open_saved_before_overlay'):
        if physical.get(key)is not True:issues.append('physical '+key+' is not confirmed')
    if physical.get('runtime_test_data_sha256_before')!=physical.get('runtime_test_data_sha256_after'):
        issues.append('physical input hashes changed')
    for key in ('changed_origin_errors','input_read_errors','input_paths_missing_pre_execution_capture','loaded_inputs_missing_pre_execution_capture'):
        if physical.get(key):issues.append('physical '+key+' is nonempty')
    return issues


def _captured_hash(physical,suffix,digest):
    reads=physical.get('first_actual_read_sha256',{})
    return type(reads)is dict and any(type(path)is str and path.replace('\\','/').endswith('/'+suffix)
                                     and value==digest for path,value in reads.items())


def empty_execution(kind):
    return {'kind':kind,'reported_tests_run':0,'collected_count':0,'executed_method_ids':[],
            'passed_method_ids':[],'failed_method_ids':[],'skipped_method_ids':[],
            'expected_failure_method_ids':[],'not_executed_method_ids':[],
            'fixture_failure_ids':[],'count_evidence_gaps':[],'records':[]}


def frequency(verifier,physical,packet,original,*,diagnostic=False):
    expected={uid for group in packet['completed'].values() for uid in group['tests']}
    execution=empty_execution('frequency_equivalence_gate')
    integrity=list(original['integrity_errors']) if original else ['original frequency report unavailable']
    integrity+=_capture_issues(physical);problems=[];regressions=[];intentional=[];modes={}
    if packet.get('execution_kind')!='frequency_equivalence':integrity.append('frozen packet execution kind mismatch')
    if verifier.get('kind')!='collection':integrity.append('original verifier collection-only report missing')
    if set(_ids(verifier.get('collected',[]),'original verifier collection',integrity))!=expected:integrity.append('original verifier collection differs from frozen gate methods')
    raw=(original or {}).get('report')
    observed=bool((original or {}).get('present') or physical.get('equivalence_actual_test_ids') or physical.get('equivalence_mode_origins'))
    starts=physical.get('equivalence_actual_test_ids',[])
    if type(starts)is not list or any(type(uid)is not str for uid in starts):integrity.append('physical frequency starts malformed');starts=[]
    observed_ids=set(starts)&expected
    if set(starts)-expected:integrity.append('physical frequency start outside declared scope')
    if physical.get('execution_kind')!='frequency_equivalence_gate':integrity.append('physical execution kind mismatch')
    if set(_ids(physical.get('equivalence_declared_test_ids',[]),'physical frequency declaration',integrity))!=expected:integrity.append('physical frequency declaration mismatch')
    if physical.get('test_ids')!=[] or physical.get('actual_test_ids')!=[] or physical.get('tests')!=0 or physical.get('ordinary_test_pass_credit')!=0:
        integrity.append('frequency gate leaked ordinary method accounting')
    if not _captured_hash(physical,packet.get('harness',''),packet.get('harness_sha256')):integrity.append('frozen frequency harness hash lacks actual captured read')
    declared_count=packet.get('required_method_count')
    if type(declared_count)is not int or declared_count!=1029 or declared_count!=len(expected):integrity.append('frozen frequency count mismatch')
    if raw is not None:
        declared=_ids(raw.get('expected_ids'),'frequency report declaration',integrity)
        if set(declared)!=expected or raw.get('expected_method_count')!=len(expected):integrity.append('frequency report omitted/changed declared methods')
        outcomes=raw.get('outcomes',{})
        if type(outcomes)is not dict or set(outcomes)!=set(MODES):integrity.append('all three frequency modes are required');outcomes=outcomes if type(outcomes)is dict else {}
        origins=physical.get('equivalence_mode_origins',{})
        all_starts=[]
        for mode in MODES:
            row=outcomes.get(mode,{})
            if type(row)is not dict:integrity.append(mode+' outcome malformed');row={}
            begun=_ids(row.get('started_ids',[]),mode+' starts',integrity)
            finished=_ids(row.get('finished_ids',[]),mode+' finishes',integrity)
            blocked=_ids(row.get('blocked_body_ids',[]),mode+' blocked bodies',integrity)
            never=_ids(row.get('never_started_ids',[]),mode+' never started',integrity)
            failures=_entries(row.get('failures',[]),mode+' failures',integrity)
            errors=_entries(row.get('errors',[]),mode+' errors',integrity)
            skipped=_entries(row.get('skipped',[]),mode+' skips',integrity)
            all_starts.extend(begun);observed_ids.update(set(begun)&expected)
            if set(begun)-expected or set(finished)-set(begun) or set(blocked)-set(begun):integrity.append(mode+' IDs outside actual declared/start set')
            if set(never)!=expected-set(begun):integrity.append(mode+' never-started set disagrees with starts')
            if type(row.get('testsRun'))is not int or row.get('testsRun')!=len(begun) or set(finished)!=set(begun):integrity.append(mode+' execution count/finish mismatch')
            if len(begun)!=len(expected):problems.append(mode+' did not start every declared method')
            if type(origins)is not dict or mode not in origins or type(origins[mode])is not dict or not origins[mode]:integrity.append(mode+' actual loaded origins absent')
            if row.get('body_unexecuted_due_to_block')!=len(blocked):integrity.append(mode+' blocked-body count mismatch')
            modes[mode]={'started_ids':begun,'finished_ids':finished,'body_not_executed_due_to_block':blocked,
                         'never_started_ids':never,'failures':failures,'errors':errors,'skipped':skipped,
                         'intentional_failure_mode':mode=='connected_first_failure','elapsed_seconds':row.get('elapsed_seconds')}
            if mode!='connected_first_failure':
                regressions += [dict(event,mode=mode,outcome=outcome) for outcome,events in (('failure',failures),('error',errors),('skip',skipped)) for event in events]
                if blocked:problems.append(mode+' unexpectedly blocked bodies')
        if starts!=all_starts:integrity.append('physical starts disagree with original per-mode starts')
        failure=modes['connected_first_failure'];wanted=_ids(raw.get('expected_blocked_after_injection',[]),'expected injected blocks',integrity)
        if len(wanted)!=31 or set(wanted)-expected or INJECTED in wanted:integrity.append('frozen first-failure chain must have31 distinct dependent blocks')
        actual_injected=[item for item in failure['failures'] if item['id']==INJECTED and INJECTION in item['detail']]
        intentional=actual_injected
        regressions += [dict(item,mode='connected_first_failure',outcome='unexpected_failure') for item in failure['failures'] if item not in actual_injected]
        regressions += [dict(item,mode='connected_first_failure',outcome='error') for item in failure['errors']]
        if (len(actual_injected)!=1 or len(failure['failures'])!=1 or failure['errors']
                or failure['body_not_executed_due_to_block']!=wanted
                or [item['id'] for item in failure['skipped']]!=wanted
                or any(not item['detail'].startswith('blocked connected predecessor:') for item in failure['skipped'])
                or failure['never_started_ids'] or raw.get('blocking_check_passed')is not True):
            problems.append('intentional first-failure/dependent-block contract did not hold')
        observations=raw.get('observations',{});mismatched=[]
        if (type(observations)is not dict or any(type(observations.get(mode))is not dict or set(observations[mode])!=expected for mode in ('cold','connected'))):
            integrity.append('cold/connected original assertion observations incomplete')
        else:mismatched=sorted(uid for uid in expected if observations['cold'][uid]!=observations['connected'][uid])
        if raw.get('mismatched_assertion_traces')!=mismatched:integrity.append('reported assertion mismatches disagree with original observations')
        if mismatched:problems.append('cold/connected assertion traces differ')
        if raw.get('unknown_observation_types')!=[]:problems.append('unknown assertion observation types prevent equivalence')
        if raw.get('status')!='equivalent':problems.append('original gate did not report equivalence')
    else:mismatched=[];integrity.append('original frequency result cannot be inspected')
    if regressions:problems.append('unexpected native outcomes in equivalence modes')
    passed=not integrity and not problems and physical.get('successful')is True and physical.get('exit_code')==0 and not physical.get('exception')
    status='equivalent' if passed else 'evidence_incomplete' if integrity else 'failed'
    if not observed:status='not_observed'
    gate={'status':status,'observed':observed,'diagnostic_only':diagnostic,'source_report':{key:value for key,value in (original or {}).items() if key!='report'},
          'declared_method_ids':sorted(expected),'observed_method_ids':sorted(observed_ids),'observed_start_events':len(starts),
          'verified_equivalent_method_ids':sorted(expected) if passed and not diagnostic else [],
          'mode_results':modes,'intentional_failure_records':intentional,'unexpected_outcomes':regressions,
          'assertion_trace_mismatch_ids':mismatched,'integrity_errors':list(dict.fromkeys(integrity)),
          'gate_failures':list(dict.fromkeys(problems)),'ordinary_test_pass_credit':0,'ordinary_test_fail_credit':0}
    execution['frequency_gate']=gate
    execution['records']=[{'kind':'frequency_gate_failure','id':item.get('id','frequency_equivalence'),'method_id':item.get('method_id',''),'cause':item.get('detail','')[-700:],'outcome':item['outcome']} for item in regressions]
    execution['count_evidence_gaps']=gate['integrity_errors']
    return execution


def parse_script_rows(text,kind):
    """Recount the original scripts' emitted rows, independently of wrapper claims."""
    issues=[];statuses=[];identities=[]
    if kind=='json_results_array':
        document=json.loads(text)
        rows=document.get('results') if type(document)is dict else None
        if type(rows)is not list:
            return {},['original JSON report has no results array']
        for row in rows:
            if type(row)is not dict:
                issues.append('malformed original JSON result row');statuses.append(None);continue
            identity=row.get('id')
            if type(identity)is not str or not identity:issues.append('missing original JSON result identity')
            else:identities.append(identity)
            statuses.append(row.get('status'))
        passed=sum(status in ('pass','passed') for status in statuses)
        failed=sum(status in ('fail','failed') for status in statuses)
        for key,count in (('passed',passed),('failed',failed)):
            if key in document and (type(document[key])is not int or document[key]!=count):
                issues.append('original JSON '+key+' summary disagrees with rows')
    elif kind=='markdown_result_table':
        text=text.replace('\r\n','\n')
        lines=text.splitlines()
        headers=[i for i,line in enumerate(lines) if re.fullmatch(r'\| # \| (?:규칙(?: \(원문 예시\))?|검사) \| 결과 \| 비고 \|',line)]
        summary_rows=re.findall(r'(?m)^(?:\*\*(\d+)/(\d+) 통과\*\*|(\d+)/(\d+) 통과)(?: — [^\r\n]+)?$',text)
        summaries=[(a or c,b or d) for a,b,c,d in summary_rows]
        if len(headers)!=1 or len(summaries)!=1:
            return {},['original Markdown header/summary missing, partial or duplicated']
        header=headers[0]
        if any(line.lstrip().startswith('|') for line in lines[:header]):
            issues.append('original Markdown contains rows outside its result table')
        if header+1>=len(lines) or lines[header+1]!='|---|---|---|---|':
            return {},['original Markdown table separator missing or malformed']
        for line in lines[header+2:]:
            if not line.strip():continue
            match=re.fullmatch(r'\| (\d+) \| ([^|]+) \| ([^|]+) \| (.*) \|',line)
            if match is None:
                issues.append('malformed original Markdown result row');statuses.append(None);continue
            identity,name,status,detail=match.groups();identities.append(identity);statuses.append(status)
            if int(identity)!=len(statuses):issues.append('original Markdown row order/gap mismatch')
            if not name.strip():issues.append('empty original Markdown result name')
        passed=sum(status=='PASS' for status in statuses);failed=sum(status=='FAIL' for status in statuses)
        if tuple(map(int,summaries[0]))!=(passed,len(statuses)):
            issues.append('original Markdown summary disagrees with rows')
    else:return {},['unknown original report format']
    if len(set(identities))!=len(identities):issues.append('duplicate original result identity')
    if not statuses:issues.append('original result table is empty')
    unknown=len(statuses)-passed-failed
    if unknown:issues.append('unknown original result status')
    return {'result_count':len(statuses),'passed_count':passed,'failed_count':failed,
            'unknown_count':unknown,'complete':bool(statuses) and not issues},issues


def read_script_report(archive,wrapper):
    """Preserve the original report's raw hash; absence may be an actual script error, not a fictitious PASS."""
    declaration=wrapper.get('original_report') if type(wrapper)is dict else None
    issues=[];member=None;actual=None;present=False;recount={}
    if type(declaration)is not dict:
        return {'present':False,'integrity_errors':['original script report declaration unavailable']}
    kind=declaration.get('kind');expected_member={'markdown_result_table':'physical/procedural-original-report.md',
                                               'json_results_array':'physical/procedural-original-report.json'}.get(kind)
    member=declaration.get('archive_member')
    if expected_member is None or member!=expected_member:issues.append('original script report kind/member mismatch')
    elif member not in archive.namelist():issues.append('original script report raw bytes missing')
    else:
        raw=archive.read(member);present=True;actual=hashlib.sha256(raw).hexdigest()
        if actual!=declaration.get('sha256'):issues.append('original script report SHA256 mismatch')
        if not raw:issues.append('original script report is empty')
        try:
            text=raw.decode('utf-8-sig')
            recount,row_issues=parse_script_rows(text,kind);issues+=row_issues
            for key,value in recount.items():
                if type(declaration.get(key))is not type(value) or declaration.get(key)!=value:
                    issues.append('original report '+key+' disagrees with wrapper')
        except (UnicodeError,ValueError):issues.append('original script report encoding/JSON invalid')
    return {'member':member,'present':present,'sha256':actual,'declared_sha256':declaration.get('sha256'),
            'original_path':declaration.get('path'),'kind':kind,'recomputed_counts':recount,'integrity_errors':issues}


def procedural(verifier,physical,packet,original,*,diagnostic=False):
    execution=empty_execution('procedural_runner_gate')
    integrity=list(original['integrity_errors']) if original else ['original procedural wrapper report unavailable']
    integrity+=_capture_issues(physical);problems=[]
    expected=set(_ids(packet.get('required_runner_ids',[]),'frozen procedural units',integrity))
    if packet.get('execution_kind')!='procedural_runner' or len(expected)!=1 or packet.get('unit_id') not in expected or packet.get('completed')!={}:
        integrity.append('frozen procedural packet identity/kind mismatch')
    runner=packet.get('runner',{})
    if type(runner)is not dict:integrity.append('frozen original runner declaration missing');runner={}
    if physical.get('execution_kind')!='procedural_runner_gate':integrity.append('physical procedural execution kind mismatch')
    actual=_ids(physical.get('procedural_actual_runner_ids',[]),'physical actual runner IDs',integrity)
    declared=_ids(physical.get('procedural_declared_runner_ids',[]),'physical declared runner IDs',integrity)
    verified=_ids(physical.get('procedural_verified_runner_ids',[]),'physical verified runner IDs',integrity)
    if set(declared)!=expected or set(actual)-expected or set(verified)-set(actual):integrity.append('physical procedural allocation/start/verification mismatch')
    if physical.get('test_ids')!=[] or physical.get('actual_test_ids')!=[] or physical.get('tests')!=0:
        integrity.append('procedural gate leaked ordinary method accounting')
    if not _captured_hash(physical,runner.get('source_path',''),runner.get('source_sha256')):
        integrity.append('original procedural source hash lacks actual captured read')
    raw=(original or {}).get('report')
    generated_evidence=(original or {}).get('generated_capture',{})
    if type(raw)is dict and (raw.get('status')in ('passed','failed') or physical.get('procedural_generated_first_reads')):
        integrity+=validate_generated_capture(physical,packet,raw,generated_evidence)
    observed=bool((original or {}).get('present') or actual)
    script_evidence=(original or {}).get('original_script_report',{'present':False,'integrity_errors':['original script report evidence unavailable']})
    script_issues=list(script_evidence.get('integrity_errors',[]));original_counts={};raw_status=None;started=set(actual)&expected;not_executed=set();raw_errors=[]
    if raw is not None:
        if raw.get('schema_version')!=1 or raw.get('execution_kind')!='procedural_runner_gate':integrity.append('procedural wrapper schema/kind mismatch')
        raw_declared=_ids(raw.get('declared_runner_ids',[]),'wrapper declared runner IDs',integrity)
        raw_actual=_ids(raw.get('actual_runner_ids',[]),'wrapper actual runner IDs',integrity)
        raw_verified=_ids(raw.get('verified_runner_ids',[]),'wrapper verified runner IDs',integrity)
        if set(raw_declared)!=expected or raw_actual!=actual or set(raw_verified)-set(raw_actual):integrity.append('wrapper/physical original runner identities disagree')
        if physical.get('successful')is True and raw_verified!=verified:integrity.append('outer verified runner IDs disagree with wrapper')
        if physical.get('successful')is not True and verified:integrity.append('outer failure cannot verify procedural units')
        if raw_actual==actual and not actual:not_executed=expected.copy()
        for key in ('source_path','source_sha256'):
            if raw.get(key)!=runner.get(key):integrity.append('original runner '+key+' differs from frozen packet')
        for key in ('original_contract_sha256','inventory_sha256'):
            if raw.get(key)!=packet.get(key) or type(packet.get(key))is not str:integrity.append('original runner '+key+' differs from frozen declaration')
        declared_argv=runner.get('argv');stage=physical.get('execution_stage')
        if type(declared_argv)is not list or len(declared_argv)<6 or any(type(v)is not str for v in declared_argv):
            integrity.append('frozen original full argv malformed')
        elif type(stage)is not str:integrity.append('actual native stage identity missing for argv binding')
        else:
            expected_argv=[value.replace('{stage}',stage) for value in declared_argv[5:]]
            if raw.get('declared_argv')!=declared_argv or raw.get('executed_argv')!=expected_argv:
                integrity.append('original script argv differs from its frozen declaration')
            resolved=raw.get('resolved_argv')
            if type(resolved)is not list or len(resolved)!=len(declared_argv) or resolved[1:]!=[v.replace('{stage}',stage) for v in declared_argv[1:]]:
                integrity.append('resolved Python/script argv differs from frozen contract')
        declaration=raw.get('original_report')
        if type(declaration)is dict:
            report_contract=runner.get('report',{})
            if declaration.get('kind')!=report_contract.get('kind'):script_issues.append('original report kind differs from frozen contract')
            report_path=declaration.get('path','');wanted=report_contract.get('path','')
            if type(report_path)is not str or type(wanted)is not str or not report_path.replace(chr(92),'/').endswith('/'+wanted):
                script_issues.append('original report path differs from frozen contract')
            original_counts={key:declaration.get(key) for key in ('result_count','passed_count','failed_count','unknown_count')}
            if any(type(value)is not int or value<0 for value in original_counts.values()):script_issues.append('original report normalized counts malformed')
            elif original_counts['result_count']!=sum(original_counts[key] for key in ('passed_count','failed_count','unknown_count')):
                script_issues.append('original report normalized totals disagree')
        else:script_issues.append('original report normalized evidence missing')
        raw_status=raw.get('status');raw_errors=raw.get('errors',[])
        if raw_status not in ('passed','failed','error','not_executed'):integrity.append('unknown procedural gate result')
        if type(raw_errors)is not list:integrity.append('procedural error evidence malformed');raw_errors=[]
        if raw_status=='not_executed' and raw_actual:integrity.append('procedural report claims unexecuted after entry was observed')
        if raw_status=='passed':
            if (set(raw_actual)!=expected or set(raw_verified)!=expected or raw.get('script_exit_code')!=0 or raw_errors):problems.append('passed procedural wrapper has incomplete/failed actual execution')
            if (type(declaration)is not dict or declaration.get('newly_created')is not True or declaration.get('complete')is not True
                    or original_counts.get('result_count',0)<=0 or original_counts.get('failed_count')!=0 or original_counts.get('unknown_count')!=0
                    or original_counts.get('passed_count')!=original_counts.get('result_count')):
                script_issues.append('original report is missing, stale, partial, failed or unknown')
            integrity+=script_issues
    else:integrity.append('original procedural wrapper cannot be inspected')
    passed=(not integrity and not problems and raw_status=='passed' and physical.get('successful')is True
            and physical.get('exit_code')==0 and not physical.get('exception') and set(verified)==expected)
    if passed:status='passed'
    elif integrity or raw_status=='passed':status='evidence_incomplete'
    elif raw_status=='error':status='error'
    elif raw_status=='failed':
        status='failed' if original_counts.get('failed_count',0)>0 and not script_issues else 'evidence_incomplete'
    elif raw_status=='not_executed':status='not_executed'
    else:status='not_observed'
    if not observed:status='not_observed'
    gate={'status':status,'observed':observed,'diagnostic_only':diagnostic,'reported_status':raw_status,
          'declared_runner_ids':sorted(expected),'observed_runner_ids':sorted(started),
          'verified_runner_ids':sorted(expected) if passed and not diagnostic else [],
          'not_executed_runner_ids':sorted(not_executed),
          'source_report':{key:value for key,value in (original or {}).items() if key!='report'},
          'original_script_report':script_evidence,'original_report_counts':original_counts,
          'generated_capture':{k:v for k,v in generated_evidence.items() if k!='events'},
          'original_report_issues':list(dict.fromkeys(script_issues)),'errors':raw_errors,
          'integrity_errors':list(dict.fromkeys(integrity)),'gate_failures':problems,
          'ordinary_test_pass_credit':0,'ordinary_test_fail_credit':0,'report_rows_are_method_ids':False}
    execution['procedural_gate']=gate;execution['count_evidence_gaps']=gate['integrity_errors']
    if status in ('failed','error'):
        execution['records']=[{'kind':'procedural_runner_'+status,'id':next(iter(expected),'procedural_runner'),
                              'method_id':'','outcome':status,'cause':str(raw_errors or original_counts)[-700:]}]
    return execution
