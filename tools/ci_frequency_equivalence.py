"""Future authorized equivalence for ALL1029 original frequency methods.
Cold, connected, and injected-first-chain-failure runs are reported separately.
This file is not executed during source-only integration preparation.
"""
import argparse,collections,copy,hashlib,importlib.util,json,math,pathlib,sys,time,types,unittest

class RecordedResult(unittest.TestResult):
    def __init__(self):
        super().__init__();self.started=[];self.finished=[]
    def startTest(self,test):
        self.started.append(test.id());super().startTest(test)
    def stopTest(self,test):
        self.finished.append(test.id());super().stopTest(test)

class AssertionTrace:
    """Normalize only witnessed fixture roles and verified native recovery hashes.

    Original unittest assertions receive their untouched arguments. Unknown
    objects/invalid receipts prevent equivalence; arbitrary UUIDs remain literal.
    """
    def __init__(self, issues):
        self.issues=issues;self.ids={};self.objects={};self.environments=set();self.derived={}

    def bind(self, environment):
        e,a,b,_=environment;key=(id(e),id(a),id(b))
        if key in self.environments:return
        number=len(self.environments);self.environments.add(key)
        for label,actor in (('actor',a),('target',b)):
            role='fixture['+str(number)+'].'+label;uid=actor.entity_id
            if uid in self.ids and self.ids[uid]!=role:self.issues.add('conflicting_fixture_role_identity')
            self.ids[uid]=role;self.objects[id(actor)]=role

    @staticmethod
    def digest(value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()

    def _identity_value(self,value):
        if isinstance(value,str) and value in self.ids:return {'known_fixture_role_id':self.ids[value]}
        if isinstance(value,dict):return {k:self._identity_value(v) for k,v in value.items()}
        if isinstance(value,list):return [self._identity_value(v) for v in value]
        return value

    def _receipts(self,value,visited):
        if id(value) in visited:return
        visited.add(id(value))
        if isinstance(value,dict):
            ledger=value.get('resource_recovery_receipts')
            if isinstance(ledger,dict):
                for key,row in ledger.items():
                    try:
                        intent=row['intent'];owner=row['owner_id'];parent=intent['parent_request']
                        if owner not in self.ids or intent['owner_id']!=owner:raise ValueError('unknown owner')
                        if row['id']!=key or key!=self.digest([parent,intent['resource'],intent['source']]):raise ValueError('receipt identity')
                        if row['intent_fingerprint']!=self.digest(intent):raise ValueError('intent fingerprint')
                        canonical=self._identity_value(intent)
                        prefix=owner+':recovery:'
                        if isinstance(parent,str) and parent.startswith(prefix) and parent[len(prefix):].isdigit():
                            canonical['parent_request']={'native_recovery_request':self.ids[owner],'sequence':int(parent[len(prefix):])}
                        tokens={key:{'verified_native_recovery_id':{'parent_request':canonical['parent_request'],'resource':intent['resource'],'source':intent['source']}},
                                row['intent_fingerprint']:{'verified_native_recovery_intent':canonical}}
                        if canonical['parent_request']!=parent:tokens[parent]=canonical['parent_request']
                        for raw,token in tokens.items():
                            if raw in self.derived and self.derived[raw]!=token:raise ValueError('ambiguous derived identity')
                            self.derived[raw]=token
                    except (KeyError,TypeError,ValueError):self.issues.add('unresolved_or_invalid_native_recovery_receipt')
            for child in value.values():self._receipts(child,visited)
        elif isinstance(value,(list,tuple,set,frozenset)):
            for child in value:self._receipts(child,visited)

    def normalize(self,value):
        self._receipts(value,set());memo={}
        def encode(v):
            if isinstance(v,str):
                if v in self.ids:return {'known_fixture_role_id':self.ids[v]}
                return self.derived.get(v,v)
            if v is None or type(v) in (int,bool):return v
            if type(v)is float:return v if math.isfinite(v) else {'nonfinite':repr(v)}
            if type(v)is bytes:return {'bytes':v.hex()}
            if isinstance(v,type):return {'python_type':v.__module__+'.'+v.__qualname__}
            if id(v) in self.objects:return {'known_fixture_role_object':self.objects[id(v)]}
            if isinstance(v,(dict,list,tuple,set,frozenset)):
                if id(v) in memo:return {'$ref':memo[id(v)]}
                node=len(memo);memo[id(v)]=node
                if isinstance(v,dict):items=[[encode(k),encode(x)] for k,x in v.items()]
                elif isinstance(v,(set,frozenset)):
                    # No set of native objects occurs in the original25 traces.
                    # Refuse such a new observation rather than invent an order.
                    if any(not (x is None or type(x) in (str,int,bool,float)) for x in v):self.issues.add('unreviewed_non_scalar_set')
                    items=[encode(x) for x in sorted(v,key=lambda x:repr(self._identity_value(x)))]
                else:items=[encode(x) for x in v]
                return {'$id':node,'kind':type(v).__name__,'items':items}
            name=type(v).__module__+'.'+type(v).__qualname__;self.issues.add(name)
            return {'unresolved_observation_type':name}
        return encode(value)


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',type=pathlib.Path,required=True);p.add_argument('--report',type=pathlib.Path,required=True);p.add_argument('--authorized-native-run',action='store_true');args=p.parse_args()
    if not args.authorized_native_run:raise SystemExit('Native execution disabled: explicit authorization flag required.')
    if args.report.exists():raise SystemExit('Report must be a new file; preserve prior evidence.')
    total_started=time.perf_counter()
    stage=args.stage.resolve();sys.dont_write_bytecode=True
    for directory in (stage,stage/'tools',stage/'engine'):sys.path.insert(0,str(directory))
    package=types.ModuleType('tools');package.__path__=[str(stage/'tools')];sys.modules['tools']=package
    spec=importlib.util.spec_from_file_location('tools.test_frequencies',stage/'tools/test_frequencies.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    m.verify_source_connection_inputs(stage)
    from frequency_source_connection_fixture import source_case_contract
    contract=json.loads((stage/'tools/frequency_source_connection_contract.json').read_text(encoding='utf-8'))
    cls=m.FrequencyTests;prefix='tools.test_frequencies.FrequencyTests.'
    expected={prefix+name for name in contract['original_direct_method_names']}
    expected.update(prefix+'test_source_move_'+str(i).zfill(4) for i in range(len(m.CASES)))
    assert len(expected)==contract['expected_native_method_count']==1029
    fixture=cls.fixture;counts=collections.Counter();mode=None;opaque=set();traces={}
    def trace(test):
        value=traces.setdefault((mode,test.id()),AssertionTrace(opaque))
        chain=getattr(test,'_source_frequency_chain',None)
        if chain is not None and chain.environment is not None:value.bind(chain.environment)
        return value
    def factory(self,*a,**k):
        counts[mode]+=1;environment=fixture(self,*a,**k);trace(self).bind(environment);return environment
    cls.fixture=factory
    def suite(capture,connected):
        selected=list(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
        assert {t.id() for t in selected}==expected
        for test in selected:
            capture[test.id()]=[]
            for name in dir(test):
                if not name.startswith('assert'):continue
                original=getattr(test,name)
                if not callable(original):continue
                def observer(*a,_name=name,_original=original,_tid=test.id(),_test=test,**k):
                    capture[_tid].append({'assertion':_name,'arguments':trace(_test).normalize({'args':a,'kwargs':k})})
                    return _original(*a,**k)
                setattr(test,name,observer)
        if connected:
            prepared=cls.prepare_chained_cases(tuple(selected))
            prepared=selected if prepared is None else list(prepared)
            assert [id(t) for t in prepared]==[id(t) for t in selected]
            assert [t.id() for t in prepared]==[t.id() for t in selected]
        return unittest.TestSuite(selected),selected
    observations={};outcomes={};expected_blocked=[];injected_id=prefix+'test_source_move_0000'
    original_first=cls.test_source_move_0000;injected_message='INJECTED_FREQUENCY_CHAIN_FAILURE_AFTER_ORIGINAL_BODY'
    initialization_elapsed_seconds=time.perf_counter()-total_started
    for mode in ('cold','connected','connected_first_failure'):
        mode_started=time.perf_counter()
        if mode=='connected_first_failure':
            def injected(self):
                original_first.__wrapped__(self)
                raise AssertionError(injected_message)
            cls.test_source_move_0000=source_case_contract(m.CASES[0],injected)
        capture={};tests,selected=suite(capture,mode!='cold')
        if mode=='connected_first_failure':
            first=next(t for t in selected if t.id()==injected_id);chain=first._source_frequency_chain
            expected_blocked=[t.id() for t in selected if getattr(t,'_source_frequency_chain',None) is chain and t is not first]
        result=RecordedResult();tests.run(result)
        observations[mode]=capture
        blocked=[t.id() for t,reason in result.skipped if reason.startswith('blocked connected predecessor:')]
        outcomes[mode]={'elapsed_seconds':time.perf_counter()-mode_started,'testsRun':result.testsRun,'started_ids':result.started,'finished_ids':result.finished,
            'failures':[(t.id(),e) for t,e in result.failures],'errors':[(t.id(),e) for t,e in result.errors],
            'skipped':[(t.id(),e) for t,e in result.skipped],'blocked_body_ids':blocked,
            'never_started_ids':sorted(expected-set(result.started)),
            'body_unexecuted_due_to_block':len(blocked),'expected_failure_injection':mode=='connected_first_failure'}
    cls.test_source_move_0000=original_first
    mismatches=[tid for tid in sorted(expected) if observations['cold'][tid]!=observations['connected'][tid]]
    complete=all(outcomes[name]['testsRun']==1029 and not outcomes[name]['failures'] and not outcomes[name]['errors'] and not outcomes[name]['skipped'] and not outcomes[name]['never_started_ids'] for name in ('cold','connected'))
    failure=outcomes['connected_first_failure']
    blocked_ok=(len(failure['failures'])==1 and failure['failures'][0][0]==injected_id and injected_message in failure['failures'][0][1]
                and not failure['errors'] and failure['blocked_body_ids']==expected_blocked
                and len(failure['skipped'])==len(expected_blocked) and not failure['never_started_ids'] and failure['testsRun']==1029)
    report={'status':'equivalent' if complete and not mismatches and blocked_ok and not opaque else 'not_equivalent_or_incomplete',
        'timing_clock':'time.perf_counter',
        'initialization_elapsed_seconds':initialization_elapsed_seconds,
        'total_wall_seconds':time.perf_counter()-total_started,
        'total_wall_scope':'authorized startup, all three modes, trace normalization and comparison; excludes final report write',
        'timing_caveat':'Sequential modes share interpreter/import caches; measured timings are not an automatic speedup claim.',
        'normalization_scope':'Only witnessed fixture actor/target role IDs and cryptographically verified resource_recovery_receipts identities. Unknown objects prevent equivalence; arbitrary UUIDs stay literal; container aliases retain graph references.',
        'scope':'All25 original direct methods and1004 original generated methods; no native class method omitted.',
        'expected_method_count':1029,'expected_ids':sorted(expected),'outcomes':outcomes,
        'mismatched_assertion_traces':mismatches,'unknown_observation_types':sorted(opaque),
        'fixture_calls':dict(counts),'observations':observations,'expected_blocked_after_injection':expected_blocked,
        'blocking_check_passed':blocked_ok,'wall_time_speedup_claimed':False}
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if report['status']=='equivalent' else 1)
if __name__=='__main__':main()


