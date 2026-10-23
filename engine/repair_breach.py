"""Actual vehicle damage events, marker history, patches and structural repair."""
from copy import deepcopy
from fractions import Fraction
import common_checks as C,crafting_recipes as Q,world_entities as W,state_grants as G
import special_entities as S,resolution_transaction as TX,control_remote as REMOTE

FIELD='_vehicle_breaches'


def _ratio(value,label):
    if type(value) is not list or len(value)!=2:raise ValueError('explicit '+label+' fraction required')
    C.integer(value[0],label+' numerator',1);C.integer(value[1],label+' denominator',1)
    return Fraction(*value)


def declaration(value):
    Q._fields(value,('id','source','marker_fraction','single_hit_fraction','combine','repeated_crossing'))
    Q._text(value['id']);Q._text(value['source']);_ratio(value['marker_fraction'],'breach marker')
    if value['single_hit_fraction'] is not None:_ratio(value['single_hit_fraction'],'single hit breach')
    if value['combine'] not in ('add','max') or value['repeated_crossing'] not in ('repeat','once'):raise ValueError('explicit breach combination and recrossing policies required')
    return deepcopy(value)


def _state(e):return getattr(e,FIELD,{'version':1,'policies':{},'history':{},'events':{}})
def _sign(row):return dict(row,sha256=TX.request_fingerprint(row))
def _verify(row):
    if type(row) is not dict or row.get('sha256')!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('actual vehicle breach evidence changed')
def _body(value):return {k:deepcopy(v) for k,v in value.items() if k!='id'}


def view(row):
    total=row['breaches'];patched=row['patched_breaches']
    return {'max_hp':row['max_hp'],'breaches_for_capacity':total,'breaches_for_protection':total-patched,'occupants_protected':total-patched<row['breach_security'],'operable':not row['destroyed'] and row['hp']>0 and total<row['breach_capacity'],'destroyed':row['destroyed']}


def _vehicle(e,uid,usable=False):
    row=getattr(e,'_physical_objects',{}).get(uid)
    if not row or row.get('kind')!='vehicle':raise ValueError('actual registered vehicle required')
    S.validate_record(e,row)
    if usable:W.require_usable_object(row)
    return row


def exposure(e,uid):
    row=_vehicle(e,uid);state=view(row)
    return {'vehicle_id':uid,'protected':state['occupants_protected'],'actual_passenger_ids':list(row['passenger_ids']),'exposed_passenger_ids':[] if state['occupants_protected'] else list(row['passenger_ids']),'breaches':row['breaches'],'patches':row['patched_breaches']}


def _merge(intervals,interval):
    result=[]
    for lo,hi in sorted([*intervals,*([interval] if interval is not None else [])]):
        if result and lo<=result[-1][1]+1:result[-1][1]=max(hi,result[-1][1])
        else:result.append([lo,hi])
    return result


def _crossing(maximum,before,after,value):
    step=maximum*_ratio(value['marker_fraction'],'breach marker')
    first=max(1,(Fraction(maximum-before)/step).__floor__()+1);last=(Fraction(maximum-after)/step).__floor__()
    return None if last<first else [first,last]


def _marker_count(interval,seen,repeat):
    if interval is None:return 0
    lo,hi=interval;count=hi-lo+1
    if not repeat:count-=sum(max(0,min(hi,b)-max(lo,a)+1) for a,b in seen)
    return count


def damage(e,actor,target_id,amount,value,*,event_id,reason):
    W.require_actors(e,actor);value=declaration(value);Q._text(event_id);Q._text(reason);C.integer(amount,'actual resolved vehicle HP damage',0);Q._selected(e,value['source']);validate_world(e,W.actor_index(e))
    intent={'actor_id':actor.entity_id,'target_id':target_id,'amount':amount,'declaration':value,'reason':reason};saved=_state(e)['events'].get(event_id)
    if saved is not None:
        if saved['fingerprint']!=TX.request_fingerprint(intent):raise ValueError('actual damage event changed intent')
        return deepcopy(saved['result'])
    _vehicle(e,target_id,usable=True)
    def apply(staged,c):
        target=_vehicle(staged,target_id,usable=True);state=_state(staged);setattr(staged,FIELD,state);old=state['policies'].get(target_id)
        if old is not None and old['body']!=_body(value):raise ValueError('actual vehicle breach policy cannot change by renaming')
        seen=state['history'].get(target_id,{'intervals':[]})['intervals'];before=target['hp'];after=before-amount;maximum=target['max_hp'];interval=_crossing(maximum,before,after,value)
        marker=_marker_count(interval,seen,value['repeated_crossing']=='repeat');massive=int(value['single_hit_fraction'] is not None and amount>=maximum*_ratio(value['single_hit_fraction'],'single hit breach'))
        created=marker+massive if value['combine']=='add' else max(marker,massive);old_breaches=target['breaches'];target['hp']=after;target['breaches']+=created
        if after<=-2*maximum or target['breaches']>=2*target['breach_capacity']:target['destroyed']=True
        if target.get('native_vehicle') is not None:
            import vehicle_native as NATIVE
            NATIVE._salvage(staged,target,NATIVE.validate_record(staged,target))
        S.validate_record(staged,target);REMOTE.boundary(staged,'actual_vehicle_damage',c)
        result={'actor_id':c.entity_id,'vehicle_id':target_id,'source':value['source'],'at':staged.elapsed_seconds,'amount':amount,'maximum_hp':maximum,'before_hp':before,'after_hp':after,'marker_interval':interval,'marker_breaches':marker,'single_hit_breaches':massive,'created':created,'before_breaches':old_breaches,'after_breaches':target['breaches'],'patches':target['patched_breaches'],'state':view(target),'exposure':exposure(staged,target_id)}
        state['policies'].setdefault(target_id,_sign({'target_id':target_id,'body':_body(value)}));state['history'][target_id]=_sign({'target_id':target_id,'intervals':_merge(seen,interval)});state['events'][event_id]=_sign({'intent':deepcopy(intent),'fingerprint':TX.request_fingerprint(intent),'result':deepcopy(result)})
        validate_world(staged,W.actor_index(staged));return result
    return G.transition(e,actor,apply)


def restoration(target,resource,amount,*,maximum=None,subset=None):
    if target['kind']!='vehicle' or target['destroyed']:raise ValueError('actual non-destroyed vehicle structure required')
    C.integer(amount,'actual structural repair quantity',0)
    if maximum is not None:amount=min(amount,maximum)
    total=target['breaches'];patched=target['patched_breaches']
    if resource=='patches':
        applied=min(amount,total-patched);target['patched_breaches']+=applied
    elif resource=='breaches':
        if subset not in ('patched_first','unpatched_first'):raise ValueError('explicit actual structural repair subset required')
        applied=min(amount,total);target['breaches']-=applied
        removed=min(applied,patched) if subset=='patched_first' else max(0,applied-(total-patched))
        target['patched_breaches']-=removed
    else:raise ValueError('actual patch or structure resource required')
    return {'resource':resource,'requested':amount,'applied':applied,'before':{'breaches':total,'patches':patched},'after':{'breaches':target['breaches'],'patches':target['patched_breaches']},'subset':subset}


def structural_policy(count,seconds,subset):
    import repair_restore as REPAIR
    C.integer(count,'actual breach repair count',1)
    if subset not in ('patched_first','unpatched_first'):raise ValueError('actual structure selection policy required')
    value=REPAIR.vehicle_policy(100*count,seconds);value['id']='native-vehicle-structural-repair'
    value['effects']=[{'resource':'breaches','provider':'declared','amount':count,'ratio':[1,1],'maximum':None,'subset':subset}]
    return value


def emergency_policy(source):
    if source not in ('feat/긴급-수리','feat/긴급-수리-1'):raise ValueError('explicit selected Emergency Repairs source required')
    return {'id':'native-emergency-vehicle-repair','source':source,'target_kinds':['vehicle'],'method':'repair','access':'adjacent','requirements':[{'kind':'owned','fields':['edges','feats'],'names':[source,'긴급 수리','Emergency Repairs']},{'kind':'skill','skill':'기술학','rank':2,'effective':False}],'materials':[],'action':'standard','seconds':0,'check':{'skill':'기술학','dc':None},'effects':[{'resource':'hp','provider':'check','amount':None,'ratio':[1,1],'maximum':None},{'resource':'patches','provider':'declared','amount':1,'ratio':[1,1],'maximum':None}],'module':None,'trigger':None,'daily_limit':None}


def validate_world(e,index):
    state=_state(e);Q._fields(state,('version','policies','history','events'))
    if state['version']!=1 or any(type(state[x]) is not dict for x in ('policies','history','events')):raise ValueError('known actual breach state required')
    registry=getattr(e,'_physical_objects',{});expected={}
    for uid,row in state['policies'].items():
        _verify(row);Q._fields(row,('target_id','body','sha256'));declaration(dict(row['body'],id='validate'))
        if uid!=row['target_id'] or uid not in registry or registry[uid].get('kind')!='vehicle':raise ValueError('actual breach policy vehicle required')
    for uid,row in state['events'].items():
        Q._text(uid);_verify(row);Q._fields(row,('intent','fingerprint','result','sha256'));intent=row['intent'];result=row['result'];value=declaration(intent['declaration']);target_id=intent['target_id']
        if row['fingerprint']!=TX.request_fingerprint(intent) or intent['actor_id'] not in index or result['actor_id']!=intent['actor_id'] or result['vehicle_id']!=target_id or target_id not in state['policies'] or state['policies'][target_id]['body']!=_body(value):raise ValueError('actual damage event participants/policy required')
        C.integer(result['at'],'actual breach event time',0,e.elapsed_seconds)
        if result['amount']!=intent['amount'] or result['before_hp']-intent['amount']!=result['after_hp'] or result['after_breaches']-result['before_breaches']!=result['created']:raise ValueError('actual vehicle damage/breach event arithmetic changed')
        interval=_crossing(result['maximum_hp'],result['before_hp'],result['after_hp'],value)
        if interval!=result['marker_interval']:raise ValueError('actual breach crossing evidence changed')
        marker=_marker_count(interval,expected.get(target_id,[]),value['repeated_crossing']=='repeat')
        massive=int(value['single_hit_fraction'] is not None and intent['amount']>=result['maximum_hp']*_ratio(value['single_hit_fraction'],'single hit breach'))
        created=marker+massive if value['combine']=='add' else max(marker,massive)
        if (result['marker_breaches'],result['single_hit_breaches'],result['created'])!=(marker,massive,created):raise ValueError('actual breach count needs its real damage criterion')
        expected[target_id]=_merge(expected.get(target_id,[]),interval)
    if set(state['history'])!=set(state['policies']) or set(expected)!=set(state['policies']):raise ValueError('actual breach history needs damage events')
    for uid,row in state['history'].items():
        _verify(row);Q._fields(row,('target_id','intervals','sha256'))
        if row['target_id']!=uid or row['intervals']!=expected[uid]:raise ValueError('actual breach marker history diverged from its events')
    return True
