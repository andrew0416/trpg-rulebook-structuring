"""Source-owned environment changes on the native clock and actor transitions."""
from copy import deepcopy
import common_checks as C,crafting_recipes as Q,world_entities as W,state_grants as G
import environment_derive as ED,environmental_effects as ENV

FIELD='_environment_changes'


def _state(e):return getattr(e,FIELD,{'version':1,'requests':{},'active':[]})
def has_pending(e):return bool(ED._state(e)['actors'] or _state(e)['active'])
def managed(e,c):return ED.bound(e,c) and not getattr(e,'_environment_change_depth',0)


def run(e,c,callback,*,participants=()):
    def apply(staged,actor,*others):
        staged._environment_change_depth=getattr(staged,'_environment_change_depth',0)+1
        try:return callback(staged,actor,*others)
        finally:staged._environment_change_depth-=1
    return G.transition(e,c,apply,participants=participants)


def effective(e,region):
    result=deepcopy(region['facts'])
    for uid in _state(e)['active']:
        row=_state(e)['requests'][uid];ED._verify(row)
        if row['region_id']==region['id']:result.update(row['changes'])
    return ED.facts(result)


def next_interval(e,end_at):
    deadlines=[row['expires_at'] for uid in _state(e)['active'] for row in [_state(e)['requests'][uid]] if e.elapsed_seconds<row['expires_at']<end_at]
    return min([end_at,*deadlines])-e.elapsed_seconds


def boundary(e,event='environment'):
    if not has_pending(e):return
    state=_state(e)
    state['active'][:]=[uid for uid in state['active'] if state['requests'][uid]['expires_at']>e.elapsed_seconds]
    index=W.actor_index(e)
    for uid in ED._state(e)['actors']:
        actor=index[uid];actual=ED.context(e,actor);old=actor.spec.get('_respiration')
        if actual['air_available'] is None or actual['medium'] is None:raise ValueError('changed region requires known atmospheric facts')
        breathing=ENV._breathes(e,actor,actual)
        if old and (old['air_available'],old['medium'],old['breathing'])==(actual['air_available'],actual['medium'],breathing):continue
        timing=getattr(e,'_environment_change_timing',None) or (old or {}).get('timing_policy')
        offset=None if e.round_start_seconds is None else e.elapsed_seconds-e.round_start_seconds
        result=ENV.observe_breathing(e,actor,air_available=actual['air_available'],medium=actual['medium'],reason='actual environment boundary: '+event,timing_policy=timing,round_offset_seconds=offset)
        if isinstance(result,C.PendingDecision):raise ValueError('environment change requires resolved breathing timestamp: '+str(result))


def change(e,region_id,changes,*,source,request_id,reason,duration_seconds=None,timing_policy=None):
    Q._text(request_id);Q._text(reason);Q._selected(e,source)
    if region_id not in ED._state(e)['regions']:raise ValueError('actual observed region required')
    if type(changes) is not dict or not changes or set(changes)-{'gravity','pressure','air_available','medium','environ'}:raise ValueError('explicit region fact changes required')
    if duration_seconds is not None:C.integer(duration_seconds,'environment duration',1)
    if timing_policy not in (None,*ENV.TIMINGS):raise ValueError('explicit native suffocation timing policy required')
    intent=dict(region_id=region_id,changes=deepcopy(changes),source=source,request_id=request_id,reason=reason,duration_seconds=duration_seconds,timing_policy=timing_policy)
    previous=_state(e)['requests'].get(request_id)
    if previous:
        ED._verify(previous)
        if previous['intent']!=intent:raise ValueError('environment request changed intent')
        return deepcopy(previous)
    def apply(staged,actor):
        state=deepcopy(_state(staged));region=ED._state(staged)['regions'][region_id];before=effective(staged,region)
        ED.facts(dict(before,**changes))
        state['active']=[uid for uid in state['active'] if (state['requests'][uid]['region_id'],state['requests'][uid]['source'])!=(region_id,source)]
        row=ED._sign(dict(intent=intent,region_id=region_id,changes=deepcopy(changes),source=source,request_id=request_id,reason=reason,started_at=staged.elapsed_seconds,expires_at=None if duration_seconds is None else staged.elapsed_seconds+duration_seconds,before=before))
        state['requests'][request_id]=row
        if duration_seconds is None:
            updated={k:deepcopy(v) for k,v in region.items() if k!='sha256'}
            updated['facts']=ED.facts(dict(region['facts'],**changes));updated.update(source=source,seconds=staged.elapsed_seconds,reason=reason)
            ED._state(staged)['regions'][region_id]=ED._sign(updated)
        else:state['active'].append(request_id)
        setattr(staged,FIELD,state);staged._environment_change_timing=timing_policy
        try:boundary(staged,'region change')
        finally:staged.__dict__.pop('_environment_change_timing',None)
        staged.gm._rec('environment '+region_id,before,effective(staged,ED._state(staged)['regions'][region_id]),reason)
        return deepcopy(row)
    return run(e,None,apply)


def transfer(e,c,region_id,*,reason,timing_policy=None):
    W.require_actors(e,c);Q._text(reason)
    if e.grid is not None or not ED.bound(e,c) or region_id not in ED._state(e)['regions']:raise ValueError('actual unmapped actor and observed destination region required')
    if timing_policy not in (None,*ENV.TIMINGS):raise ValueError('explicit native suffocation timing required')
    def apply(staged,actor):
        before=ED.context(staged,actor)
        row={k:deepcopy(v) for k,v in ED._state(staged)['actors'][actor.entity_id].items() if k!='sha256'}
        row.update(region_id=region_id,reason=reason,seconds=staged.elapsed_seconds)
        ED._state(staged)['actors'][actor.entity_id]=ED._sign(row);staged._environment_change_timing=timing_policy
        try:boundary(staged,'region transfer')
        finally:staged.__dict__.pop('_environment_change_timing',None)
        after=ED.context(staged,actor);staged.gm._rec('environment transfer',before,after,reason,actor)
        return after
    return run(e,c,apply)


def validate_world(e,index):
    if not hasattr(e,FIELD):return
    state=_state(e);Q._fields(state,('version','requests','active'))
    if state['version']!=1 or type(state['requests']) is not dict or type(state['active']) is not list or any(type(uid) is not str for uid in state['active']) or len(set(state['active']))!=len(state['active']):raise ValueError('environment change world schema required')
    bindings=set()
    for uid,row in state['requests'].items():
        ED._verify(row)
        Q._fields({k:v for k,v in row.items() if k!='sha256'},('intent','region_id','changes','source','request_id','reason','started_at','expires_at','before'))
        if uid!=row['request_id'] or row['region_id'] not in ED._state(e)['regions']:raise ValueError('actual environment request and region identities required')
        Q._selected(e,row['source']);Q._text(row['reason']);C.integer(row['started_at'],'environment change time',0)
        if type(row['changes']) is not dict or not row['changes'] or set(row['changes'])-{'gravity','pressure','air_available','medium','environ'}:raise ValueError('explicit region changes required')
        ED.facts(row['before']);ED.facts(dict(row['before'],**row['changes']))
        intent=row['intent']
        if type(intent) is not dict or intent!=dict(region_id=row['region_id'],changes=row['changes'],source=row['source'],request_id=uid,reason=row['reason'],duration_seconds=None if row['expires_at'] is None else row['expires_at']-row['started_at'],timing_policy=intent.get('timing_policy')):raise ValueError('environment producer intent differs')
        if row['started_at']>e.elapsed_seconds or intent['timing_policy'] not in (None,*ENV.TIMINGS):raise ValueError('actual environment clock and timing required')
        if row['expires_at'] is not None:C.integer(row['expires_at'],'environment expiry',row['started_at']+1)
        if uid in state['active']:
            key=(row['region_id'],row['source'])
            if row['expires_at'] is None or row['expires_at']<=e.elapsed_seconds or key in bindings:raise ValueError('one current unexpired contribution per region/source required')
            bindings.add(key)
    if any(uid not in state['requests'] for uid in state['active']):raise ValueError('actual environment change producer required')

