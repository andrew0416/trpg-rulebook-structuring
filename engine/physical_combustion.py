"""Actual paid fire attacks and observed non-HP ignition on physical objects.

The GM supplies combustible material and actual ignition, not a made-up forest
HP, spread rate, periodic damage, or automatic battlefield Hazard.
"""
from copy import deepcopy
from pathlib import Path
import json
import physical_object_attacks as ATTACKS
import state_grants as G
import world_entities as W

FIELD='physical_combustion'


def _profile(e,obj):
    ATTACKS._object(e,obj['id'])
    state=obj.get(FIELD)
    if type(state) is not dict or set(state)!={'profile','profile_hash','attacks','extinguished'}:
        raise ValueError('actual observed combustion profile required')
    p=state['profile']
    if (type(p) is not dict or set(p)!={'combustible','source','reason','observed_by'}
            or type(p['combustible']) is not bool or p['observed_by'] not in W.actor_index(e)
            or state['profile_hash']!=ATTACKS._hash(p)):
        raise ValueError('combustion material observation changed')
    for key in ('source','reason'):ATTACKS._text(p[key],'combustion '+key)
    return state


def observe(e,c,uid,*,combustible,source,reason):
    W.require_actors(e,c)
    for v,k in ((source,'source'),(reason,'reason')):ATTACKS._text(v,'GM combustion '+k)
    if type(combustible) is not bool:raise ValueError('explicit actual combustible-material observation required')
    obj=ATTACKS._object(e,uid);W.require_usable_object(obj)
    profile=dict(combustible=combustible,source=source,reason=reason,observed_by=c.entity_id)
    if FIELD in obj:
        validate_world(e)
        if _profile(e,obj)['profile']!=profile:raise ValueError('combustion profile cannot be reclassified')
        return deepcopy(obj[FIELD])
    def apply(staged,actor):
        state=dict(profile=profile,profile_hash=ATTACKS._hash(profile),attacks={},extinguished={})
        staged._physical_objects[uid][FIELD]=state
        return deepcopy(state)
    return G.transition(e,c,apply)


def require_unused_event(e,event_id):
    for obj in e._physical_objects.values():
        if event_id in obj.get(FIELD,{}).get('attacks',{}):
            raise ValueError('attack event identity already belongs to a combustion attack')


def _policy(e,mid):
    policy=json.loads((Path(e.r.root)/ATTACKS.POLICY).read_text(encoding='utf-8'))['moves'].get(mid)
    if (not policy or e.r.move(mid)!=policy['definition'] or e.r.move_mech(mid)[0]!=policy['mechanics']
            or policy['definition']['type']!='불꽃'):
        raise ValueError('combustion requires unchanged reviewed actual fire Move')
    return policy


def _record(rows,key,payload):
    row=deepcopy(payload);row['receipt_hash']=ATTACKS._hash(row);rows[key]=row
    return deepcopy(row)


def attack(e,c,uid,move_id,*,event_id,hit,ignite,source,reason):
    W.require_actors(e,c)
    for v,k in ((event_id,'event'),(source,'source'),(reason,'reason')):ATTACKS._text(v,'actual environmental attack '+k)
    if type(hit) is not bool or type(ignite) is not bool or ignite and not hit:
        raise ValueError('actual hit and ignition require consistent explicit booleans')
    intent=dict(actor_id=c.entity_id,object_id=uid,requested_move_id=move_id,hit=hit,ignite=ignite,source=source,reason=reason)
    validate_world(e)
    for obj in e._physical_objects.values():
        prior=obj.get(FIELD,{}).get('attacks',{}).get(event_id)
        if prior:
            if prior['intent']!=intent:raise ValueError('environmental attack event changed intent')
            return deepcopy(prior)
        if any(r['event_id']==event_id for r in obj.get(ATTACKS.FIELD,{}).get('attacks',[])):
            raise ValueError('attack event identity already belongs to a physical HP attack')
    obj=ATTACKS._object(e,uid);W.require_usable_object(obj);state=_profile(e,obj)
    if ignite and not state['profile']['combustible']:raise ValueError('noncombustible observation cannot ignite')
    _,move,mm,policy=ATTACKS._move(e,c,move_id);_policy(e,move['id'])
    def apply(staged,actor):
        target=staged._physical_objects[uid];state=_profile(staged,target)
        kind=ATTACKS._permission(staged,actor,target,move,mm)
        ATTACKS._pay_move(staged,actor,move,kind)
        import confusion_attacks as CONFUSION
        confusion=CONFUSION.begin_native(staged,actor,move,producer='combustion',event_id=event_id)
        row=_record(state['attacks'],event_id,dict(event_id=event_id,intent=intent,move_id=move['id'],
            definition_hash=ATTACKS._hash(policy),profile_hash=state['profile_hash'],action_kind=kind,at=staged.elapsed_seconds))
        if confusion is not None:
            row['confusion']=CONFUSION.finish_native(staged,actor,move,confusion,producer='combustion',event_id=event_id)
            row=_record(state['attacks'],event_id,{k:v for k,v in row.items() if k!='receipt_hash'})
        validate_world(staged)
        return row
    return G.transition(e,c,apply)


def _active(obj):
    state=obj[FIELD]
    ended={uid for row in state['extinguished'].values() for uid in row['ignition_ids']}
    return sorted(uid for uid,row in state['attacks'].items() if row['intent']['ignite'] and uid not in ended)


def current(e,uid):
    """Consume actual enduring fire sources, independent of object HP or scene."""
    validate_world(e);obj=ATTACKS._object(e,uid);_profile(e,obj)
    active=[] if W.physical_lifecycle(obj)['destroyed'] else _active(obj)
    return dict(object_id=uid,burning=bool(active),ignition_ids=active)


def extinguish(e,c,uid,*,event_id,ignition_ids,source,reason):
    """GM-observed extinction; no implicit water, cost, timing or spread policy."""
    W.require_actors(e,c)
    for v,k in ((event_id,'event'),(source,'source'),(reason,'reason')):ATTACKS._text(v,'observed extinguishing '+k)
    if (type(ignition_ids) is not list or not ignition_ids or any(type(x) is not str for x in ignition_ids)
            or len(set(ignition_ids))!=len(ignition_ids)):raise ValueError('distinct actual ignition identities required')
    validate_world(e);obj=ATTACKS._object(e,uid);state=_profile(e,obj)
    intent=dict(object_id=uid,event_id=event_id,ignition_ids=sorted(ignition_ids),observed_by=c.entity_id,source=source,reason=reason)
    prior=state['extinguished'].get(event_id)
    if prior:
        if any(prior[k]!=v for k,v in intent.items()):raise ValueError('extinction event changed observation')
        return deepcopy(prior)
    W.require_present_object(obj)
    if not set(ignition_ids)<=set(_active(obj)):raise ValueError('actual still-burning ignition sources required')
    def apply(staged,actor):
        row=_record(staged._physical_objects[uid][FIELD]['extinguished'],event_id,dict(intent,at=staged.elapsed_seconds))
        validate_world(staged)
        return row
    return G.transition(e,c,apply)


def validate_world(e):
    index=W.actor_index(e);seen=set()
    hp_events={row['event_id'] for obj in e._physical_objects.values() for row in obj.get(ATTACKS.FIELD,{}).get('attacks',[])}
    for obj in e._physical_objects.values():
        if FIELD not in obj:continue
        state=_profile(e,obj)
        if type(state['attacks']) is not dict or type(state['extinguished']) is not dict:raise ValueError('combustion histories required')
        for uid,row in state['attacks'].items():
            if type(row) is not dict or set(row)-{'confusion'}!={'event_id','intent','move_id','definition_hash','profile_hash','action_kind','at','receipt_hash'}:
                raise ValueError('actual combustion attack receipt required')
            intent=row['intent'];policy=_policy(e,row['move_id'])
            if 'confusion' in row:
                import confusion_attacks as CONFUSION
                CONFUSION.validate_native(index[intent['actor_id']],policy['definition'],row['confusion'],
                    producer='combustion',event_id=uid)
            if (row['receipt_hash']!=ATTACKS._hash({k:v for k,v in row.items() if k!='receipt_hash'})
                    or set(intent)!={'actor_id','object_id','requested_move_id','hit','ignite','source','reason'}
                    or uid!=row['event_id'] or uid in seen or uid in hp_events or intent['actor_id'] not in index
                    or intent['object_id']!=obj['id'] or e.r.move_id(intent['requested_move_id'])!=row['move_id']
                    or row['profile_hash']!=state['profile_hash'] or row['definition_hash']!=ATTACKS._hash(policy)
                    or type(intent['hit']) is not bool or type(intent['ignite']) is not bool
                    or intent['ignite'] and (not intent['hit'] or not state['profile']['combustible'])):
                raise ValueError('combustion attack identity, material or source mismatch')
            for key in ('source','reason'):ATTACKS._text(intent[key],'actual ignition '+key)
            ATTACKS._text(uid,'actual ignition identity');ATTACKS._integer(row['at'],'actual ignition time')
            if row['at']>e.elapsed_seconds or row['action_kind'] not in ('standard','swift','free','full'):
                raise ValueError('actual combustion attack time/action required')
            seen.add(uid)
        ended=set()
        for uid,row in state['extinguished'].items():
            if (type(row) is not dict or set(row)!={'object_id','event_id','ignition_ids','observed_by','source','reason','at','receipt_hash'}
                    or row['receipt_hash']!=ATTACKS._hash({k:v for k,v in row.items() if k!='receipt_hash'})
                    or row['object_id']!=obj['id'] or row['event_id']!=uid or row['observed_by'] not in index):
                raise ValueError('extinction observation changed')
            for key in ('event_id','source','reason'):ATTACKS._text(row[key],'observed extinction '+key)
            ATTACKS._integer(row['at'],'actual extinction time')
            ids=row['ignition_ids']
            if type(ids) is not list or not ids or any(type(x) is not str for x in ids) or ids!=sorted(set(ids)) or ended.intersection(ids):
                raise ValueError('distinct ended ignition sources required')
            if row['at']>e.elapsed_seconds or any(x not in state['attacks'] or not state['attacks'][x]['intent']['ignite'] or state['attacks'][x]['at']>row['at'] for x in ids):
                raise ValueError('extinction lost its prior actual ignition')
            ended.update(ids)
    return True
