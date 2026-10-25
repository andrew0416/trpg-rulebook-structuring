"""Endure's selected native reaction, scoped to the actual triggering Move recipient."""
from functools import wraps
from inspect import signature
from copy import deepcopy
import action_lifecycle as ACTION
import frequency as F
from pathlib import Path
import json
_policy=json.loads((Path(__file__).resolve().parents[1]/"data/endure-policy.json").read_text(encoding="utf8"))
SOURCES=('move/버티기','move/버티기-홈브류')


def known(e,actor):
    return next((mid for name in actor.moves if (mid:=e.r.move_id(name)) in SOURCES),None)


def authority(e,actor):
    from source_context import verified_source
    verified_source(e.r,_policy['csv_source'],label='Endure selected source')
    verified_source(e.r,_policy['english_supplement'],label='Endure English supplement',source_root='source-audit')
    frame=getattr(e,'_endure_trigger',None)
    if not frame or frame['recipient'] is not actor:raise ValueError('Endure requires its actual hit trigger')
    row=e._move_completions.get(frame['completion_id']);event=e._passive_events.get(frame['event_id'])
    if (not row or not event or row['phase']!='targets' or event['completion_id']!=row['id']
            or event['target'] is not actor or event['actor'] is not row['actor']
            or row['move_id']!=frame['move_id'] or row['move'].get('class') not in ('물리','특수')
            or not getattr(e,'_native_move_resolution_depth',0)):
        raise ValueError('actual native damaging Move recipient required')
    return frame,row,event


def project(e,actor,target,move,mechanics):
    if move['id'] not in SOURCES:return move,mechanics
    authority(e,actor)
    if target is not actor:raise ValueError('Endure is Self')
    # The incoming Move's actual HP producer consumes the reaction; this is not a held shield.
    return move,{'effects_exec':[]}


def recipient_scope(fn):
    sig=signature(fn)
    @wraps(fn)
    def run(e,*args,**kwargs):
        values=sig.bind(e,*args,**kwargs).arguments
        prior=getattr(e,'_endure_receiving',None)
        e._endure_receiving={'recipient':values['target'],'completion_id':values['completion_id'],
                             'event_id':values['passive_event'],'move_id':values['move_id']}
        try:return fn(e,*args,**kwargs)
        finally:
            if prior is None:del e._endure_receiving
            else:e._endure_receiving=prior
    return run


def offer(e,actor,target,move,completion_id,event_id):
    if move.get('class') not in ('물리','특수') or target.hp<=0:return
    mid=known(e,target)
    if mid is None or not F.move_allowed(e,target,mid)[0]:return
    receiving=getattr(e,'_endure_receiving',None)
    if (not receiving or receiving['recipient'] is not target or receiving['event_id']!=event_id
            or receiving['completion_id']!=completion_id):raise ValueError('actual native recipient scope required')
    row=e._move_completions[completion_id]
    if target.entity_id in row.get('endure',{}):return
    answer=e.rulings.decide({'type':'endure','unit':mid,'actor':target.name,'actor_id':target.entity_id,
                             'move_id':move['id'],'event_id':event_id,'text':'Use Endure for this damaging Move?'})
    if answer is not None and type(answer) is not bool:raise ValueError('explicit Endure use or decline required')
    receipt={'source':mid,'event_id':event_id,'recipient_id':target.entity_id,'used':answer is True,'own_completion':None}
    row.setdefault('endure',{})[target.entity_id]=receipt
    if answer is not True:return
    old=getattr(e,'_endure_trigger',None);e._endure_trigger=dict(receiving)
    before=target.move_uses.get(mid,0)
    try:
        with ACTION.move_grant(e,target,target,mid,source=mid,kind='free') as token:
            e.use_move(target,target,mid,free_action=True,_action_grant=token)
        if target.move_uses.get(mid,0)!=before+1:raise ValueError('actual Endure Move activation refused')
    finally:
        if old is None:del e._endure_trigger
        else:e._endure_trigger=old
    # Native transactions preserve identities but can replace receipt dictionaries.
    receipt=e._move_completions[completion_id]['endure'][target.entity_id]
    own=e._move_completions.get(receipt['own_completion'])
    if own is None or own['phase']!='complete':raise ValueError('Endure Move has not completed')


def begin(e,actor,move,completion_id):
    if move['id'] not in SOURCES:return
    frame,parent,_=authority(e,actor)
    receipt=parent['endure'][actor.entity_id]
    if receipt['own_completion'] is not None:raise ValueError('Endure trigger already consumed')
    receipt['own_completion']=completion_id
    e._move_completions[completion_id]['endure_trigger']={'completion_id':parent['id'],'event_id':frame['event_id'],'recipient_id':actor.entity_id}


def replace_hp(e,target,before,proposed,*,source,loss_kind,preview=False):
    """Endure changes final HP, not Damage or its Massive-Damage injury (PTU 1.05 Sturdy and Vigor)."""
    if before<=0 or proposed>0:return proposed
    frame=getattr(e,'_endure_receiving',None)
    if not frame or frame['recipient'] is not target:return proposed
    if loss_kind!='damage' and source!=frame['move_id']:return proposed
    row=getattr(e,'_move_completions',{}).get(frame['completion_id'])
    receipt=row.get('endure',{}).get(target.entity_id) if row and row['phase']=='targets' else None
    if not receipt or not receipt['used'] or receipt['own_completion'] is None:return proposed
    own=e._move_completions[receipt['own_completion']]
    if own['phase']!='complete' or own['actor'] is not target:return proposed
    if receipt['source']==SOURCES[1] and proposed*4<=-target.base_max_hp:return proposed
    if not preview:receipt.setdefault('hp_replacements',[]).append({'before':before,'proposed':proposed,'after':1,'loss_kind':loss_kind,'source':source})
    return 1


def validate(e,index):
    for row in getattr(e,'_move_completions',{}).values():
        for uid,receipt in row.get('endure',{}).items():
            actor=index.get(uid);event=e._passive_events.get(receipt['event_id'])
            if (actor is None or event is None or event['target'] is not actor or event['completion_id']!=row['id']
                    or receipt['source'] not in SOURCES or receipt['recipient_id']!=uid or type(receipt['used']) is not bool):
                raise ValueError('Endure original actual hit evidence changed')
            if receipt['used']:
                active=getattr(e,'_endure_trigger',None)
                if row['phase']=='targets' and active and active['recipient'] is actor and active['event_id']==event['id']:continue
                own=e._move_completions.get(receipt['own_completion'])
                if (not own or own['actor'] is not actor or own['move_id']!=receipt['source'] or own['phase']!='complete'
                        or own.get('endure_trigger')!={'completion_id':row['id'],'event_id':event['id'],'recipient_id':uid}):
                    raise ValueError('Endure native Move completion changed')
    return True
