"""Typed equivalence gate; private traces stay in the existing physical archive."""
import importlib.util
import json
import math
from pathlib import Path
import sys

KIND='frequency_equivalence'
HARNESS='tools/ci_frequency_equivalence.py'
MODES=('cold','connected','connected_first_failure')
PREFIX='tools.test_frequencies.FrequencyTests.'


def packet(value):
    if not isinstance(value,dict) or value.get('execution_kind')!=KIND:
        return None
    if value.get('harness')!=HARNESS or value.get('required_method_count')!=1029:
        raise ValueError('fixed frequency equivalence harness and1029-method scope required')
    declared=[name for group in value['completed'].values() for name in group['tests']]
    if (len(declared)!=1029 or len(set(declared))!=1029
            or any(not isinstance(name,str) or not name.startswith(PREFIX) for name in declared)):
        raise ValueError('exact distinct frequency method allocation required')
    return {'declared_ids':declared,'harness_sha256':value['harness_sha256']}


def execute(stage, declaration, destination, before_mode):
    import hashlib
    harness=stage/HARNESS
    if hashlib.sha256(harness.read_bytes()).hexdigest()!=declaration['harness_sha256']:
        raise ValueError('immutable equivalence harness changed')
    spec=importlib.util.spec_from_file_location('ci_frequency_equivalence',harness)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    original=module.RecordedResult;modes=iter(MODES)
    class ObservedResult(original):
        def __init__(self):
            super().__init__();self._ci_equivalence_mode=next(modes)
            before_mode(self._ci_equivalence_mode)
    module.RecordedResult=ObservedResult
    previous=list(sys.argv);code=1
    try:
        sys.argv=[str(harness),'--stage',str(stage),'--report',str(destination),'--authorized-native-run']
        try:module.main()
        except SystemExit as done:code=done.code if isinstance(done.code,int) else 1
    finally:
        sys.argv=previous;module.RecordedResult=original
    if not destination.exists():raise ValueError('equivalence report missing')
    report=json.loads(destination.read_text(encoding='utf-8'))
    expected=set(declaration['declared_ids'])
    if report.get('expected_method_count')!=1029 or len(report.get('expected_ids',()))!=1029 or set(report.get('expected_ids',()))!=expected:
        raise ValueError('equivalence report omitted declared original methods')
    if set(report.get('outcomes',{}))!=set(MODES):raise ValueError('all three equivalence modes required')
    for mode in MODES:
        outcome=report['outcomes'][mode]
        if len(outcome.get('started_ids',()))!=1029 or set(outcome['started_ids'])!=expected:
            code=1
    if report.get('status')!='equivalent' or report.get('blocking_check_passed') is not True:code=1
    for mode in ('cold','connected'):
        row=report['outcomes'][mode]
        if any(row.get(k) for k in ('failures','errors','skipped','never_started_ids')):code=1
    return code,report


def public_summary(path, outcome):
    """Only fixed statuses, counts and finite timings may leave encrypted traces."""
    def number(v):return v if type(v) in (int,float) and math.isfinite(v) and v>=0 else None
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else {}
        if not isinstance(value,dict):value={}
    except (OSError,ValueError):value={}
    modes={}
    for name in MODES:
        outcomes=value.get('outcomes',{})
        row=outcomes.get(name,{}) if isinstance(outcomes,dict) else {}
        if not isinstance(row,dict):row={}
        def count(field):return len(row[field]) if isinstance(row.get(field),list) else 0
        modes[name]={'started':count('started_ids'),
                     'failures':count('failures'),
                     'errors':count('errors'),
                     'skipped':count('skipped'),
                     'blocked_bodies':count('blocked_body_ids'),
                     'never_started':count('never_started_ids'),
                     'elapsed_seconds':number(row.get('elapsed_seconds')),
                     'intentional_failure_mode':name=='connected_first_failure'}
    successful=value.get('status')=='equivalent' and outcome.get('exit_code')==0
    return {'schema_version':1,'suite':KIND,'kind':'equivalence_gate',
            'successful':successful,'status':'equivalent' if successful else 'failed_or_incomplete',
            'source_method_scope':1029,'ordinary_test_pass_credit':0,'clause_credit':0,
            'mode_results':modes,'assertion_trace_mismatch_count':len(value['mismatched_assertion_traces']) if isinstance(value.get('mismatched_assertion_traces'),list) else 0,
            'unknown_observation_type_count':len(value['unknown_observation_types']) if isinstance(value.get('unknown_observation_types'),list) else 0,
            'blocking_check_passed':value.get('blocking_check_passed') is True,
            'initialization_elapsed_seconds':number(value.get('initialization_elapsed_seconds')),
            'total_wall_seconds':number(value.get('total_wall_seconds')),
            'timing_clock':'time.perf_counter','wall_time_speedup_claimed':False,
            'private_trace_location':'encrypted physical/frequency-equivalence.json'}
