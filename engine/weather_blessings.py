"""Weather-linked payloads in the existing shared-team Blessing container.

The weather occurrence is the lifetime authority; decisions are the capacity
ledger. Attack selection is deliberately not inferred from damage previews.
"""
from copy import deepcopy
import common_checks as C
import effect_instances as E
import homebrew_weather as H

PAYLOAD='weather_effectiveness'


def definition(rules,source):
    row=H.definition(rules,source)
    if row is None:return None
    rules._selected_rule(source)
    return {'payload':{'kind':PAYLOAD,'boost_types':deepcopy(row['boost_types']),
                      'reduce_type':row['reduce_type']},
            'capacity':2,'lifetime':H.LIFETIME,'creation_weather':row['weather'],
            'stacking':'weather_occurrence','name':row['blessing_name']}


def is_weather(record):return record.get('effect',{}).get('kind')==PAYLOAD


def validate_record(actor,record,*,terminal=False):
    # Common source, capacity, ownership and scope checks run in blessing_effects.
    import blessing_effects as B
    expected={'id','source','effect','at',E.KEY,'scope_history','creation_weather',
              'decisions','weather_occurrence_id','weather_policy'}
    if set(record)!=expected:raise ValueError('unexpected weather Blessing state')
    C.integer(record.get('weather_occurrence_id'),'weather occurrence link',1)
    if record.get('weather_policy')!=H.provenance(record['source']):
        raise ValueError('weather Blessing selected source changed')
    validate_decisions(actor,record,terminal=terminal)
    if terminal:
        m=record[E.KEY];end=m['end_event']
        if m['state']=='consumed':
            if end!={'kind':'blessing_exhausted','event_id':record['decisions'][-1]['event_id']}:
                raise ValueError('weather exhaustion must name the final consumed attack')
            return
        if end.get('kind')=='weather_ended':
            if (set(end)!={'kind','occurrence_id','source','reason'} or
                type(end['occurrence_id']) is not int or end['occurrence_id']!=record['weather_occurrence_id']):
                raise ValueError('weather charge ending has a different parent')
            E.text(end['source'],'weather ending source');E.text(end['reason'],'weather ending reason')
        elif not B._removed(actor.r,end):
            raise ValueError('weather charge removal requires an actual source')


def validate_world(engine,index):
    import blessing_effects as B
    import weather_state as W
    s=getattr(engine,W.KEY,None)
    pools=[(owner,r,terminal) for owner in index.values()
           for r,terminal in [(r,False) for r in B.live(owner)]+
             [(r,True) for r in owner.spec.get(B.HISTORY,[]) if isinstance(r,dict) and is_weather(r)]
           if is_weather(r)]
    if s is None:
        if pools:raise ValueError('weather Blessing has no weather history')
        return
    W.validate(engine,index=index)
    occurrences={r['id']:r for r in s['history']+([s['active']] if s['active'] else [])}
    counts={}
    for owner,r,terminal in pools:
        identity=r['weather_occurrence_id'];parent=occurrences.get(identity)
        if (parent is None or parent.get('policy')!=r['weather_policy'] or
            parent['source_id']!=r['source'] or parent['actor_id']!=owner.entity_id or
            parent['started_seconds']!=r['at'] or parent['weather']!=r['creation_weather']):
            raise ValueError('weather Blessing differs from its actual native parent')
        counts[identity]=counts.get(identity,0)+1
        if not terminal and parent is not s['active']:
            raise ValueError('live weather charges outlast their parent')
        if terminal and r[E.KEY]['end_event']['kind']=='weather_ended':
            end=r[E.KEY]['end_event']
            if (parent is s['active'] or parent.get('end_source')!=end['source'] or
                parent.get('end_reason')!=end['reason']):
                raise ValueError('weather charge ending differs from actual weather ending')
    for owner,r,terminal in pools:
        for event in r['decisions']:
            attacker=index[event['attacker_id']]
            if attacker.spec.get(ATTACK_SEQUENCE,0)<event['activation_sequence']:
                raise ValueError('weather decision lacks an issued attack activation')
    for identity,parent in occurrences.items():
        if parent.get('policy') is not None and counts.get(identity)!=1:
            raise ValueError('native weather must issue exactly one shared charge pool')


def preflight(engine,actor,source):
    import blessing_effects as B
    index=B.checked(engine)
    if index.get(actor.entity_id) is not actor:raise ValueError('weather Blessing needs an actual creator')
    E.text(actor.side,'weather beneficiary side')
    E.validate_actor(actor)
    row=definition(engine.r,source)
    if row is None:raise ValueError('selected weather Blessing source required')
    for owner in index.values():
        if type(owner.spec.get(B.HISTORY,[])) is not list:raise ValueError('effect history must be a list')
        if owner.side==actor.side and any(isinstance(r,dict) and E.KEY not in r and
            r.get('name')==row['name'] for r in owner.blessings):
            raise ValueError('legacy weather Blessing cannot merge into the native pool')


def grant(engine,actor,parent):
    # Called only after producer preflight, in the same synchronous mutation.
    row=definition(engine.r,parent['source_id'])
    r=E.create(engine,actor,kind='team_blessing',source=parent['source_id'],payload=row['payload'],
               capacity={'bucket':'team_blessing','source':parent['source_id'],'limit':2},
               lifetime={'boundary':H.LIFETIME},applied_by=actor)
    r.update(scope_history=[{'kind':'created','side':actor.side,'source':parent['source_id'],
                             'actor_id':actor.entity_id,'at':engine.elapsed_seconds}],
             creation_weather=parent['weather'],decisions=[],weather_occurrence_id=parent['id'],
             weather_policy=deepcopy(parent['policy']))
    actor.blessings.append(r)
    engine.time_actors([actor])
    return r


def retire(engine,parent,source,reason):
    import blessing_effects as B
    index=B.checked(engine)
    for owner in index.values():
        if type(owner.spec.get(B.HISTORY,[])) is not list:raise ValueError('effect history must be a list')
    for owner in index.values():
        for r in list(B.live(owner)):
            if is_weather(r) and r['weather_occurrence_id']==parent['id']:
                E.archive(engine,owner,r,state='expired',event={'kind':'weather_ended',
                          'occurrence_id':parent['id'],'source':source,'reason':reason})
                owner.blessings.remove(r)


ATTACK_SEQUENCE='weather_attack_sequence'
STEPS={0.125:-3,0.25:-2,0.5:-1,1.0:0,1.5:1,2.0:2,3.0:3}


def shifted(rules,multiplier,direction):
    if type(multiplier) not in (int,float) or multiplier not in STEPS:
        raise ValueError('weather response requires a nonimmune standard type multiplier')
    delta={'offense':1,'defense':-1}.get(direction)
    if delta is None:raise ValueError('explicit weather offense or defense required')
    return rules.mech('combat/type-effectiveness')['multiplier_by_net_steps'][str(max(-3,min(3,STEPS[multiplier]+delta)))]


def candidates(engine,attacker,target,damage_type):
    import blessing_effects as B
    result=[]
    for owner in B.checked(engine).values():
        for r in B.live(owner):
            if not is_weather(r):continue
            direction=None
            if B.side(r)==attacker.side and damage_type in r['effect']['boost_types']:direction='offense'
            if B.side(r)==target.side and damage_type==r['effect']['reduce_type']:direction='defense'
            if direction:result.append((owner,r,direction))
    return result


def preflight_attack(engine,attacker,target,move,mm):
    if move['class'] not in ('물리','특수'):return
    import effects_ext as EXT
    if not candidates(engine,attacker,target,EXT.effective_type(engine,attacker,target,move,mm,consume=False)):return
    C.integer(attacker.spec.get(ATTACK_SEQUENCE,0),'weather attack issuance',0)


def begin_attack(engine,attacker,target,move):
    if move['class'] not in ('물리','특수'):return None
    import blessing_effects as B
    if not any(is_weather(r) for c in B.checked(engine).values() for r in B.live(c)):return None
    import move_activation as A
    scope=A.current_scope(engine,attacker,target,move['id'])
    activation=None if scope is None else scope['activation']
    if activation is not None and 'weather_attack' in activation:return deepcopy(activation['weather_attack'])
    seq=C.integer(attacker.spec.get(ATTACK_SEQUENCE,0),'weather attack issuance',0)+1
    attacker.spec[ATTACK_SEQUENCE]=seq
    result={'activation_sequence':seq,'activation_id':attacker.entity_id+':weather-attack:'+str(seq)}
    if activation is not None:activation['weather_attack']=deepcopy(result)
    return result


def validate_decisions(actor,record,*,terminal):
    import blessing_effects as B
    import arithmetic_policy as M
    import math
    seen=set();at=record['at'];scope=record['scope_history']
    fields={'event_id','sequence','at','target_id','attacker_id','side','scope_index','move_id',
            'move_type','move_class','selected','damage_before','damage_after','multiplier_before',
            'multiplier_after','formula','direction','activation_id','activation_sequence'}
    for event in record['decisions']:
        if type(event) is not dict or set(event)!=fields or type(event['selected']) is not bool:
            raise ValueError('typed explicit weather attack decision required')
        at=C.integer(event['at'],'weather decision time',at)
        who=E.text(event['target_id'],'actual weather damage target')
        attacker=E.text(event['attacker_id'],'actual weather attacker')
        seq=C.integer(event['sequence'],'actual weather damage sequence',1)
        if event['event_id']!=who+':blessing-damage:'+str(seq):raise ValueError('weather damage identity changed')
        activation=C.integer(event['activation_sequence'],'weather activation sequence',1)
        if event['activation_id']!=attacker+':weather-attack:'+str(activation):raise ValueError('weather activation identity changed')
        key=(event['activation_id'],who)
        if key in seen:raise ValueError('weather charge cannot be decided twice for one attack target')
        seen.add(key)
        i=C.integer(event['scope_index'],'weather scope index',0,len(scope)-1)
        if event['side']!=scope[i]['side'] or event['at']<scope[i]['at']:raise ValueError('weather decision has different beneficiary scope')
        ty=E.text(event['move_type'],'actual weather damage type');E.text(event['move_id'],'actual weather Move')
        if event['move_class'] not in ('물리','특수'):raise ValueError('weather decision requires a damaging Move')
        direction=event['direction']
        if (direction=='offense' and ty not in record['effect']['boost_types'] or
            direction=='defense' and ty!=record['effect']['reduce_type']):raise ValueError('weather attack type mismatch')
        before=event['multiplier_before'];step=shifted(actor.r,before,direction)
        after=step if event['selected'] else before
        if type(event['multiplier_after']) not in (int,float) or event['multiplier_after']!=after:raise ValueError('weather type step changed')
        f=event['formula']
        if type(f) is not dict or set(f)!={'after_defense','other_multiplier','adjustment'}:raise ValueError('weather requires actual damage formula')
        C.integer(f['after_defense'],'weather damage after defense',1);C.integer(f['adjustment'],'weather final adjustment')
        other=f['other_multiplier']
        if type(other) not in (int,float) or not math.isfinite(other) or other<0:raise ValueError('invalid other damage multiplier')
        C.integer(event['damage_before'],'weather incoming damage',1);C.integer(event['damage_after'],'weather selected damage',0)
        if event['damage_before']!=max(0,M.product(f['after_defense'],before,other)+f['adjustment']) or event['damage_after']!=max(0,M.product(f['after_defense'],after,other)+f['adjustment']):raise ValueError('weather damage receipt changed')
    left=B.remaining(record)
    if left<0 or (not terminal and left==0):raise ValueError('weather charge capacity exhausted without archive')
    if terminal and record[E.KEY]['state']=='consumed' and (left!=0 or not record['decisions'] or not record['decisions'][-1]['selected']):
        raise ValueError('weather exhaustion requires two selected real attacks')


def select_damage(engine,event,native_context):
    import blessing_effects as B
    import arithmetic_policy as M
    import damage_reactions as R
    if event.get('weather_processed'):return event['damage']
    actual=engine._heavy_native_receipts.get(native_context)
    if actual is None or actual.get('weather_attack') is None:return event['damage']
    attacker=event['attacker'];target=event['target'];move=event['move']
    if actual['attacker'] is not attacker or actual['target'] is not target or actual['move_id']!=move['id']:
        raise ValueError('weather response needs the actual native damage producer')
    event['weather_processed']=True
    if B.reaction_blocked(engine,attacker,move):return event['damage']
    potential=min(event['damage'],max(0,target.hp-1)) if event.get('damage_floor') else event['damage']
    f=event['damage_formula']
    if potential<=0 or f['multiplier']==0:return event['damage']
    for owner,r,direction in candidates(engine,attacker,target,event['actual_damage_type']):
        identity=actual['weather_attack']
        if any(d['activation_id']==identity['activation_id'] and d['target_id']==target.entity_id for d in r['decisions']):
            raise ValueError('weather attack target already resolved')
        before=event['damage'];mult=f['multiplier'];after=shifted(engine.r,mult,direction)
        changed=max(0,M.product(f['after_defense'],after,f['other_multiplier'])+f['adjustment'])
        # At the supported step bound the charge cannot buy a change.
        if after==mult or changed==before:continue
        seq=C.integer(target.spec.get(B.DAMAGE_SEQUENCE,0),'actual damage sequence',0)+1
        uid=target.entity_id+':blessing-damage:'+str(seq)
        answer=engine.rulings.decide({'type':'weather_blessing','unit':r['source'],'instance_id':r['id'],
            'event_id':uid,'activation_id':identity['activation_id'],'attacker_id':attacker.entity_id,
            'target_id':target.entity_id,'move':move['id'],'actual_damage_type':event['actual_damage_type'],
            'direction':direction,'damage':before,'changed_damage':changed,'remaining':B.remaining(r),
            'text':'이 공격의 지정 대상 한 명에게 날씨 충전을 사용합니까?'})
        selected=answer is True
        observation=dict(identity,event_id=uid,sequence=seq,at=engine.elapsed_seconds,
            target_id=target.entity_id,attacker_id=attacker.entity_id,side=B.side(r),
            scope_index=len(r['scope_history'])-1,move_id=move['id'],move_type=event['actual_damage_type'],
            move_class=move['class'],selected=selected,damage_before=before,damage_after=changed if selected else before,
            multiplier_before=mult,multiplier_after=after if selected else mult,
            formula={k:f[k] for k in ('after_defense','other_multiplier','adjustment')},direction=direction)
        target.spec[B.DAMAGE_SEQUENCE]=seq
        event.setdefault('weather_pending',[]).append((owner,r,observation))
        if selected:
            event['damage']=changed;f['multiplier']=after;event['context']['multiplier']=after
            resistance=R.resistance_multiplier(engine,after)
            event['resisted_damage']=None if resistance is None else max(0,M.product(f['after_defense'],resistance,f['other_multiplier'])+f['adjustment'])
    return event['damage']


def finish_damage(engine,event,final_damage):
    """Commit after the actual final hook/floor path accepts damage."""
    if event.get('weather_finished'):return
    event['weather_finished']=True
    pending=event.pop('weather_pending',[])
    if not pending:return
    import effects_ext as EXT
    if final_damage<=0 or EXT.cap_damage(engine,event['target'],final_damage)<=0:return
    import blessing_effects as B
    B.checked(engine)
    for owner,r,observation in pending:
        if not any(x is r for x in owner.blessings):raise ValueError('selected weather pool changed during damage responses')
        if any(d['activation_id']==observation['activation_id'] and d['target_id']==observation['target_id'] for d in r['decisions']):
            raise ValueError('weather attack target already committed')
        r['decisions'].append(observation)
        if B.remaining(r)==0:
            E.archive(engine,owner,r,state='consumed',event={'kind':'blessing_exhausted','event_id':observation['event_id']})
            owner.blessings.remove(r)
        else:B.validate_record(owner,r)
