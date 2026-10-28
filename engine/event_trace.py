"""Detached execution evidence. Read history, never infer execution from ownership."""
from copy import deepcopy

ATTRIBUTE_FIELDS=('hp','temp_hp','stages','injuries','budget','move_uses','pending_action_loss')
SPEC_DEFAULTS={'ap_spent':0,'ap_removed':0,'ap_bound':0,'frequency_state':{}}
RESOURCE_FIELDS=ATTRIBUTE_FIELDS+tuple(SPEC_DEFAULTS)

def snapshot(actor):
    row={name:deepcopy(getattr(actor,name)) for name in ATTRIBUTE_FIELDS if hasattr(actor,name)}
    row.update({name:deepcopy(actor.spec.get(name,default)) for name,default in SPEC_DEFAULTS.items()})
    return row

def resources(engine):
    import world_entities as WORLD
    return {identity:snapshot(actor) for identity,actor in WORLD.actor_index(engine).items()}

def changes(before,after):
    result=[]
    for identity in sorted(set(before)|set(after)):
        old,new=before.get(identity,{}),after.get(identity,{})
        for name in RESOURCE_FIELDS:
            if old.get(name)!=new.get(name):
                row={'entity_id':identity,'resource':name,
                     'before':old.get(name),'after':new.get(name)}
                if type(row['before']) in (int,float) and type(row['after']) in (int,float):
                    row['delta']=row['after']-row['before']
                # An HP delta alone is not proof of damage.
                if name in ('hp','temp_hp'):row['classification']='resource_change'
                result.append(row)
    return result

def event(engine,event_id):
    import passive_events as PE
    import source_policy as POLICY
    ev=getattr(engine,'_passive_events',{}).get(event_id)
    if ev is None:raise KeyError('no actual event: '+str(event_id))
    observations=PE.observations(engine,event_id)
    listeners=[]
    for key,outcome in ev.get('outcomes',{}).items():
        row={'listener_id':key,**deepcopy(outcome)}
        if outcome.get('status')=='applied' and outcome.get('reason') in getattr(engine,'_source_policy_executions',{}):
            row['execution']=POLICY.execution_record(engine,outcome['reason'])
        listeners.append(row)
    return {'schema':1,'event_id':event_id,'state':ev.get('status'),
            'phase':ev.get('phase'),'actor_id':ev['actor'].entity_id,
            'target_id':ev['target'].entity_id,'observations':observations,
            'listeners':listeners,'reason':ev.get('reason')}


from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from inspect import signature
_ACTIVE=ContextVar('native_trace_stack',default=())

@contextmanager
def staged_scope(original,staged):
    token=_ACTIVE.set(tuple((staged if owner is original else owner,identity,row)
                           for owner,identity,row in _ACTIVE.get()))
    try:yield
    finally:_ACTIVE.reset(token)


def enable(engine,enabled=True):
    if type(enabled) is not bool:raise ValueError('trace enabled must be boolean')
    engine._execution_trace_enabled=enabled

def records(engine,trace_id=None):
    rows=getattr(engine,'_execution_traces',{})
    if trace_id is not None:
        if trace_id not in rows:raise KeyError('no actual execution trace: '+str(trace_id))
        return deepcopy(rows[trace_id])
    return deepcopy(list(rows.values()))

def _value(value):
    if hasattr(value,'entity_id'):return {'entity_id':value.entity_id}
    if isinstance(value,dict):return {str(k):_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_value(v) for v in value]
    if value is None or type(value) in (str,int,float,bool):return value
    return {'runtime_type':type(value).__name__}

def calculation(engine,**facts):
    scopes=_ACTIVE.get()
    if scopes and scopes[-1][0] is engine:
        scopes[-1][2]['calculations'].append(_value(facts))

def operation(kind,*fields):
    """Opt-in native evidence; does not reinterpret a successful return as a hit."""
    def decorate(fn):
        sig=signature(fn)
        @wraps(fn)
        def run(engine,*args,**kwargs):
            bound=sig.bind(engine,*args,**kwargs)
            call_args,call_kwargs=bound.args,bound.kwargs
            if not getattr(engine,'_execution_trace_enabled',False):return fn(*call_args,**call_kwargs)
            import source_context as SC
            bound.apply_defaults()
            number=getattr(engine,'_execution_trace_sequence',0)+1
            engine._execution_trace_sequence=number
            identity='native-trace:'+str(number)
            stack=_ACTIVE.get()
            parent=next((row[1] for row in reversed(stack) if row[0] is engine),None)
            row={'schema':1,'trace_id':identity,'parent_id':parent,'producer':fn.__name__,
                 'kind':kind,'state':'running','inputs':{k:_value(bound.arguments[k]) for k in fields},
                 'calculations':[],'round':engine.round_no,'elapsed_seconds':engine.elapsed_seconds,
                 'resource_scope':list(RESOURCE_FIELDS),'resource_changes_include_children':True}
            before=resources(engine)
            # Explicit participants can be used before everyone registration.
            participants=[v for v in bound.arguments.values() if hasattr(v,'entity_id') and hasattr(v,'hp')]
            for actor in participants:before[actor.entity_id]=snapshot(actor)
            token=_ACTIVE.set(stack+((engine,identity,row),))
            try:
                with SC.capture_reads(engine.r) as reads:
                    try:
                        result=fn(*call_args,**call_kwargs)
                        row.update(state='returned',result=_value(result))
                        return result
                    except Exception as exc:
                        row.update(state='pending' if 'Pending' in type(exc).__name__ else 'raised',
                                   exception={'type':type(exc).__name__,'message':str(exc)})
                        raise
                    finally:row['source_reads']=deepcopy(reads)
            finally:
                _ACTIVE.reset(token)
                after=resources(engine)
                for actor in participants:after[actor.entity_id]=snapshot(actor)
                row['resource_changes']=changes(before,after)
                engine.__dict__.setdefault('_execution_traces',{})[identity]=deepcopy(row)
        return run
    return decorate
