"""Actual digital entry/exit and atomic anchor-dependent ejection."""
from copy import deepcopy
import common_checks as C,crafting_recipes as Q,world_entities as W,state_grants as G
import special_entities as S,supplemental_state as SUP,skill_modifiers as SK
import arithmetic_policy as M,resolution_transaction as TX,turn as TURN

FIELD='_network_connections'


def declaration(value):
    Q._fields(value,('id','source','qualification','entry_action','exit_action','access','anchor','forced_loss','voluntary_dependents'))
    Q._text(value['id']);Q._text(value['source']);q=value['qualification'];Q._fields(q,('skill','rank','interfaces','edges'));Q._text(q['skill']);C.integer(q['rank'],'digital entry rank',1)
    for name in ('interfaces','edges'):
        if type(q[name]) is not list:raise ValueError('explicit digital entry acquisition alternatives required')
        for item in q[name]:Q._text(item)
    if value['entry_action'] not in ('standard','shift','swift') or value['exit_action'] not in ('standard','shift','swift'):raise ValueError('actual digital action cost required')
    Q._fields(value['access'],('kind','maximum'))
    if value['access']['kind']=='local':C.integer(value['access']['maximum'],'actual network access range',0)
    elif value['access']['kind']!='observed' or value['access']['maximum'] is not None:raise ValueError('explicit observed/local network access required')
    anchor=value['anchor'];Q._fields(anchor,('skill','maximum','maximum_depth'));Q._text(anchor['skill'])
    if anchor['maximum'] is not None:C.integer(anchor['maximum'],'authored anchor capacity',0)
    C.integer(anchor['maximum_depth'],'supported sourced anchor depth',1,1)
    fraction=value['forced_loss']
    if type(fraction) is not list or len(fraction)!=2:raise ValueError('explicit anchor-ejection Integrity fraction required')
    C.integer(fraction[0],'ejection numerator',0);C.integer(fraction[1],'ejection denominator',1)
    if fraction[0]>fraction[1]:raise ValueError('ejection loss cannot exceed one maximum Integrity')
    if value['voluntary_dependents'] not in ('reject','disconnect'):raise ValueError('explicit voluntary dependent exit policy required')
    return deepcopy(value)


def native():
    return {'id':'native:digital-connection','source':'supp-polygon/디지털-전투-룰',
        'qualification':{'skill':'기술학','rank':4,'interfaces':['접속','capability/접속','Wired'],'edges':['디지털-아바타','poke_edge/디지털-아바타','디지털 아바타']},
        'entry_action':'standard','exit_action':'standard','access':{'kind':'observed','maximum':None},
        'anchor':{'skill':'기술학','maximum':None,'maximum_depth':1},'forced_loss':[1,2],'voluntary_dependents':'reject'}


def _body(value):return {k:deepcopy(v) for k,v in value.items() if k!='id'}
def _sign(row):return dict(row,sha256=TX.request_fingerprint(row))
def _verify(row):
    if type(row) is not dict or row.get('sha256')!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('network connection execution record changed')
def _state(e):return getattr(e,FIELD,{'version':1,'policies':{},'requests':{}})


def _network(e,uid):
    Q._text(uid);obj=getattr(e,'_physical_objects',{}).get(uid)
    if obj is None:raise ValueError('actual registered network/server required')
    W.require_usable_object(obj)
    if any(W.physical_lifecycle(obj)[x] for x in ('disabled','suppressed')):raise ValueError('actual network/server unavailable')
    return obj


def _basis(e,actor,value,selected,anchor_id):
    q=value['qualification'];available=[]
    if SK.rank(e.r,actor,q['skill'])[2]>=q['rank']:available.append('technology')
    if {SK.key(x) for x in G.effective_capabilities(actor)} & {SK.key(x) for x in q['interfaces']}:available.append('interface')
    owned=actor.spec.get('poke_edges',actor.spec.get('edges',[]))
    if {SK.key(x) for x in owned if type(x) is str} & {SK.key(x) for x in q['edges']}:available.append('digital_avatar_edge')
    if anchor_id is not None:available.append('anchor')
    if selected is None:
        if not available:raise ValueError('actual digital entry qualification or allied anchor required')
        selected=available[0]
    if selected not in available:raise ValueError('actual selected digital entry basis is absent')
    if (selected=='anchor')!=(anchor_id is not None):raise ValueError('only dependent entry acquires an actual anchor')
    return selected


def _policy(e,avatar_id):
    record=_state(e)['policies'].get(avatar_id)
    if record is None:return native()
    _verify(record);return declaration(dict(record['body'],id='stored'))


def _anchor(e,actor,network_id,anchor_id,value,*,allied,avatar_id):
    if anchor_id is None:return
    if allied is not True:raise ValueError('actual allied anchor relationship observation required')
    parent=getattr(e,'_physical_objects',{}).get(anchor_id)
    if parent is None or parent.get('kind')!='digital_avatar' or parent['status']!='connected':raise ValueError('actual connected allied anchor required')
    S.validate_record(e,parent)
    if parent['actor_id']==actor.entity_id or parent['id']==avatar_id or parent['network_id']!=network_id:raise ValueError('anchor must be another actual actor in the same network')
    seen={avatar_id};cursor=parent;depth=0
    while cursor is not None:
        if cursor['id'] in seen:raise ValueError('network anchor cycle forbidden')
        seen.add(cursor['id']);depth+=1
        if depth>value['anchor']['maximum_depth']:raise ValueError('anchor must independently qualify under the selected source')
        cursor=None if cursor['anchor_id'] is None else e._physical_objects.get(cursor['anchor_id'])
    owner=W.actor_index(e)[parent['actor_id']];parent_value=_policy(e,parent['id']);limit=parent_value['anchor']['maximum']
    if limit is None:limit=SK.effective_rank(e.r,owner,parent_value['anchor']['skill'])
    count=sum(row.get('kind')=='digital_avatar' and row.get('status')=='connected' and row.get('anchor_id')==anchor_id and row['id']!=avatar_id for row in e._physical_objects.values())
    if count>=limit:raise ValueError('actual anchor connected-ally capacity exhausted')


def _replay(e,request,intent):
    Q._text(request);validate_world(e,W.actor_index(e));saved=_state(e)['requests'].get(request)
    if saved is None:return None
    if saved['fingerprint']!=TX.request_fingerprint(intent):raise ValueError('network request identity has changed intent')
    return deepcopy(saved['result'])


def _save(e,request,intent,result):
    state=_state(e);state['requests'][request]=_sign({'fingerprint':TX.request_fingerprint(intent),'intent':deepcopy(intent),'result':deepcopy(result)});setattr(e,FIELD,state)
    validate_world(e,W.actor_index(e));return result


def enter(e,actor,network_id,value=None,*,avatar_id,request_id,access_established,reason,entry_basis=None,anchor_id=None,anchor_allied=False,program_ids=None,optional_trainer_stats=None):
    value=declaration(native() if value is None else value);W.require_actors(e,actor);Q._text(avatar_id);Q._text(reason);Q._selected(e,value['source']);_network(e,network_id)
    if access_established is not True:raise ValueError('actual network access must be established')
    if optional_trainer_stats is not None and type(optional_trainer_stats) is not bool or type(anchor_allied) is not bool:raise ValueError('explicit digital option/ally observation required')
    if program_ids is not None:
        if not isinstance(program_ids,(list,tuple)) or len(set(program_ids))!=len(program_ids):raise ValueError('distinct actual installed program identities required')
        for uid in program_ids:Q._text(uid)
    intent={'kind':'enter','actor_id':actor.entity_id,'network_id':network_id,'avatar_id':avatar_id,'policy':_body(value),
        'access_established':access_established,'reason':reason,'entry_basis':entry_basis,'anchor_id':anchor_id,'anchor_allied':anchor_allied,'program_ids':None if program_ids is None else list(program_ids),'optional_trainer_stats':optional_trainer_stats}
    replay=_replay(e,request_id,intent)
    if replay is not None:return replay
    def apply(staged,c):
        network=_network(staged,network_id);state=_state(staged);policy=state['policies'].get(avatar_id)
        if policy is not None and policy['body']!=_body(value):raise ValueError('new declaration name cannot replace the avatar connection policy')
        if value['access']['kind']=='local':
            distance=W.distance_known(c,network)
            if distance is None or distance>value['access']['maximum']:raise ValueError('actual local network access unavailable')
        basis=_basis(staged,c,value,entry_basis,anchor_id);_anchor(staged,c,network_id,anchor_id,value,allied=anchor_allied,avatar_id=avatar_id)
        old=staged._physical_objects.get(avatar_id)
        if any(row.get('kind')=='digital_avatar' and row.get('actor_id')==c.entity_id and row.get('status')=='connected' for row in staged._physical_objects.values()):raise ValueError('one actual actor cannot enter through two connected avatars')
        if old is not None:
            if old.get('kind')!='digital_avatar' or old['actor_id']!=c.entity_id:raise ValueError('actual avatar identity belongs to another body')
            S.validate_record(staged,old)
            if old['integrity']<=0 or old['status']=='disabled':raise ValueError('avatar must actually recover positive Integrity before reentry')
            import network_integrity as INTEGRITY
            INTEGRITY.require_reentry(staged,avatar_id)
            row=deepcopy(old)
        else:
            maximum=SUP.avatar_maximum(staged,c)
            row={'id':avatar_id,'kind':'digital_avatar','integrity':maximum,'max_integrity':maximum,'temp_integrity':0}
        row.update(location={'kind':'abstract','place_id':network_id+'/entry'},actor_id=c.entity_id,network_id=network_id,status='connected',anchor_id=anchor_id,entry_basis=basis,
            optional_trainer_stats=row.get('optional_trainer_stats',False) if optional_trainer_stats is None else optional_trainer_stats,
            program_ids=row.get('program_ids',[]) if program_ids is None else list(program_ids))
        S.validate_record(staged,row)
        if not TURN.spend(staged,c,value['entry_action'],'digital network entry'):return C.PendingDecision('actual digital entry action unavailable')
        S.observe(staged,row,reason=reason);state['policies'].setdefault(avatar_id,_sign({'avatar_id':avatar_id,'actor_id':c.entity_id,'body':_body(value)}));setattr(staged,FIELD,state)
        result={'kind':'enter','actor_id':c.entity_id,'avatar_id':avatar_id,'network_id':network_id,'basis':basis,'anchor_id':anchor_id,'status':'connected','integrity':row['integrity'],'action':value['entry_action'],'at':staged.elapsed_seconds}
        return _save(staged,request_id,intent,result)
    return G.transition(e,actor,apply)


def _connected(e,actor,avatar_id,*,forced=False):
    row=getattr(e,'_physical_objects',{}).get(avatar_id)
    if row is None or row.get('kind')!='digital_avatar' or row['actor_id']!=actor.entity_id or row['status']!='connected':raise ValueError('actual actor connected avatar required')
    if not forced:S.validate_record(e,row)
    return row


def _end(e,row,*,forced,value,reason):
    registry=e._physical_objects;affected=[row];seen=set()
    for parent in affected:
        if parent['id'] in seen:raise ValueError('network anchor cycle forbidden')
        seen.add(parent['id']);affected.extend(x for x in registry.values() if x.get('kind')=='digital_avatar' and x.get('status')=='connected' and x.get('anchor_id')==parent['id'])
    if not forced and len(affected)>1 and value['voluntary_dependents']=='reject':raise ValueError('connected dependents must exit before their anchor')
    proposed=[];changes=[]
    for subject in affected:
        updated=deepcopy(subject);updated['status']='ejected' if forced else 'disconnected';loss=0
        if forced and subject is not row:
            policy=_policy(e,subject['id']);fraction=policy['forced_loss'];loss=M.ratio(subject['max_integrity']*fraction[0],fraction[1]);updated['integrity']=max(0,subject['integrity']-loss)
        proposed.append(updated);changes.append({'avatar_id':subject['id'],'actor_id':subject['actor_id'],'before':subject['integrity'],'after':updated['integrity'],'loss':loss,'status':updated['status']})
    S.observe_batch(e,proposed,reason=reason)
    return changes


def exit(e,actor,avatar_id,*,request_id,reason,forced=False):
    W.require_actors(e,actor);Q._text(avatar_id);Q._text(reason)
    if type(forced) is not bool:raise ValueError('explicit actual forced ejection required')
    value=_policy(e,avatar_id);Q._selected(e,value['source']);intent={'kind':'eject' if forced else 'exit','actor_id':actor.entity_id,'avatar_id':avatar_id,'policy':_body(value),'reason':reason}
    replay=_replay(e,request_id,intent)
    if replay is not None:return replay
    def apply(staged,c):
        row=_connected(staged,c,avatar_id,forced=forced)
        if not forced:
            if value['voluntary_dependents']=='reject' and any(x.get('kind')=='digital_avatar' and x.get('status')=='connected' and x.get('anchor_id')==avatar_id for x in staged._physical_objects.values()):raise ValueError('connected dependents must exit before their anchor')
            if not TURN.spend(staged,c,value['exit_action'],'digital network exit'):return C.PendingDecision('actual digital exit action unavailable')
        changes=_end(staged,row,forced=forced,value=value,reason=reason)
        result={'kind':intent['kind'],'avatar_id':avatar_id,'actor_id':c.entity_id,'changes':changes,'action':None if forced else value['exit_action'],'at':staged.elapsed_seconds}
        return _save(staged,request_id,intent,result)
    return G.transition(e,actor,apply)


def validate_world(e,index,*,registry=None):
    state=_state(e);Q._fields(state,('version','policies','requests'))
    if state['version']!=1 or type(state['policies']) is not dict or type(state['requests']) is not dict:raise ValueError('known actual network connection state required')
    registry=getattr(e,'_physical_objects',{}) if registry is None else registry
    for uid,row in state['policies'].items():
        _verify(row);Q._fields(row,('avatar_id','actor_id','body','sha256'));declaration(dict(row['body'],id='stored'));avatar=registry.get(uid)
        if avatar is None or avatar.get('kind')!='digital_avatar' or uid!=row['avatar_id'] or avatar['actor_id']!=row['actor_id'] or row['actor_id'] not in index:raise ValueError('actual avatar connection policy identity required')
        if avatar['status']=='connected':
            limit=row['body']['anchor']['maximum']
            if limit is None:limit=SK.effective_rank(e.r,index[row['actor_id']],row['body']['anchor']['skill'])
            count=sum(x.get('kind')=='digital_avatar' and x.get('status')=='connected' and x.get('anchor_id')==uid for x in registry.values())
            if count>limit:raise ValueError('actual declared anchor capacity exceeded')
    for uid,row in state['requests'].items():
        Q._text(uid);_verify(row);Q._fields(row,('fingerprint','intent','result','sha256'))
        if row['fingerprint']!=TX.request_fingerprint(row['intent']):raise ValueError('network connection request changed')
        intent=row['intent'];result=row['result']
        if intent['actor_id'] not in index or intent['avatar_id'] not in registry or result['avatar_id']!=intent['avatar_id'] or result['actor_id']!=intent['actor_id'] or result['kind']!=intent['kind']:raise ValueError('actual network execution identity required')
        C.integer(result['at'],'network connection execution time',0,e.elapsed_seconds)
    return True
