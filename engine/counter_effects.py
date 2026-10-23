"""Bounded counters with separately owned stage contributions."""
from copy import deepcopy
import operator,re
import common_checks as C
import combat_stage_sources as STAGES
KEY='counter_stage_sources'

def prerequisite(actor,text):
    match=re.fullmatch(r'(?:user\.)?([A-Za-z_][A-Za-z_0-9]*)\s*(==|>=|>|<=|<)\s*(\d+)',text or '')
    if match is None:raise ValueError('selected counter prerequisite requires an explicit executable predicate')
    name,comparison,threshold=match.groups()
    actual=C.integer(actor.counters.get(name,0),'prerequisite counter',0)
    return {'==':operator.eq,'>=':operator.ge,'>':operator.gt,'<=':operator.le,'<':operator.lt}[comparison](actual,int(threshold))

def preflight(actor,effects,source):
    validate(actor)
    names={x.get('name') for x in effects if x.get('type')=='counter'}
    for effect in effects:
        if effect.get('type')=='counter':
            if type(effect.get('name')) is not str or not effect['name']:raise ValueError('identified counter required')
            if effect.get('requires') and not prerequisite(actor,effect['requires']):raise ValueError('actual counter prerequisite not met')
            for field in ('set','delta'):
                if field in effect:C.integer(effect[field],'counter '+field)
            if 'max' in effect:C.integer(effect['max'],'counter cap',1)
        if effect.get('type')=='stage_change' and effect.get('linked_to'):
            name=effect['linked_to']
            if name not in names and not linked(actor,name,source):raise ValueError('linked stage requires its actual counter producer')


def validate(actor):
    rows=actor.spec.get(KEY,{})
    if type(rows) is not dict:raise ValueError('counter stage ownership mapping required')
    if not rows:return
    state=STAGES.validate(actor)
    for name,row in rows.items():
        count=C.integer(actor.counters.get(name,0),'actual counter',0,row['cap'])
        expected={s:d*count for s,d in row['per_stack'].items()} if count else {}
        actual=(state or {}).get('base',{}).get('counter:'+name)
        if expected:
            if actual!={'source':row['source'],'ends':'counter_zero','deltas':expected}:
                raise ValueError('counter and its owned combat stages disagree')
        elif actual is not None:raise ValueError('zero counter retains owned combat stages')


def linked(actor,name,source):
    row=actor.spec.get(KEY,{}).get(name)
    return row is not None and row['source']==source


def change(engine,actor,effect,source):
    validate(actor)
    name=effect.get('name','counter')
    if type(name) is not str or not name:raise ValueError('named counter required')
    old=C.integer(actor.counters.get(name,0),'actual counter',0)
    if effect.get('requires') and not prerequisite(actor,effect['requires']):return False
    owner=actor.spec.get(KEY,{}).get(name)
    cap=effect.get('max',owner['cap'] if owner else None)
    if cap is not None:C.integer(cap,'counter cap',1)
    value=effect.get('set',old+effect.get('delta',1))
    C.integer(value,'counter value')
    value=max(0,value if cap is None else min(cap,value))
    effects=engine.r.move_mech(source)[0].get('effects_exec',[]) if source in engine.r.moves else []
    links=[x for x in effects if x.get('type')=='stage_change' and x.get('linked_to')==name]
    if links:
        per={}
        for row in links:
            if row.get('target','self')!='self' or row.get('stat') not in STAGES.STATS:
                raise ValueError('counter stages require explicit self-owned five-stat contributions')
            delta=C.integer(row.get('delta'),'per-stack stage delta')
            per[row['stat']]=per.get(row['stat'],0)+delta
        proposed={'source':source,'cap':cap,'per_stack':per}
        if owner is not None and owner!=proposed:raise ValueError('counter source policy changed')
        if owner is None and old:raise ValueError('existing counter requires native stage ownership import')
        owner=proposed
    if owner is not None:
        state=STAGES.prepared(actor)
        key='counter:'+name
        if value:state['base'][key]={'source':owner['source'],'ends':'counter_zero',
                                  'deltas':{s:d*value for s,d in owner['per_stack'].items()}}
        else:state['base'].pop(key,None)
        # All preparation is complete before either visible value is published.
        actor.spec.setdefault(KEY,{})[name]=deepcopy(owner)
        STAGES.write(actor,state)
    actor.counters[name]=value
    validate(actor)
    engine.log('    '+actor.name+' '+name+' = '+str(value),source)
    return True
