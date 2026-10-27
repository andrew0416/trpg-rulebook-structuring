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
VIGOR=('ability/생기','ability/생기-홈브류')
# Same reviewed Connection paragraph as the canonical derived excerpt: Core
# p310, Ability Keywords, original LF line 9755. No consumer parsed that text;
# the native learner below owns learn/replace/permanent/one-TP semantics.
# Retain the derivation locator, not a new private excerpt dependency.
CONNECTION_ENGLISH={'file':'source-audit/ptu-core-1.05.pdf',
    'sha256':'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907',
    'page':310,'section':'Ability Keywords','keyword':'Connection','original_lf_line':9755,
    'reviewed_excerpt_sha256':'3aba519dd9fe123ed32102455f2699fde1fb92e69665db7257d10e18fbd04754',
    'original_text_sha256':'a0e5f0bf0eaf9d79cf2a268b3647c077b7175cc3172e35d620a476dad73992b1'}


def registration(rules,value):
    if value in VIGOR:uid=value
    elif value in ('생기','Vigor'):uid=rules._selected_rule(VIGOR[0])
    elif value=='생기[홈브류]':uid=VIGOR[1]
    else:return None
    connection_move(rules,uid)
    return {'name':rules.selection.units[uid]['title'],'source_id':uid}


def vigor_source(e,actor):
    import ability_transitions as AB
    from source_context import verified_source
    projected=AB.project_components(actor)
    active=[uid for uid in VIGOR if projected.get(uid)]
    if len(active)>1:raise ValueError('one selected Vigor source required')
    if not active:return None
    uid=active[0]
    if e.r._selected_rule(uid)!=uid:raise ValueError('selected Vigor source required')
    verified_source(e.r,{'file':'input/db/abilities.csv','sha256':'87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'},label='Vigor')
    if e.r.selection.units[uid]['source'].get('record_span')!=([229,229] if uid==VIGOR[0] else [684,684]):
        raise ValueError('Vigor actual source row changed')
    return uid


def connection_move(rules,ability):
    """The literal Vigor Connection omitted from typed ability effects."""
    from source_context import verified_source
    if ability not in VIGOR or rules._selected_rule(ability)!=ability:
        raise ValueError('selected Vigor Connection source required')
    verified_source(rules,{'file':'input/db/abilities.csv','sha256':'87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'},label='Vigor Connection')
    if rules.selection.units[ability]['source'].get('record_span')!=([229,229] if ability==VIGOR[0] else [684,684]):
        raise ValueError('Vigor actual Connection source row changed')
    mid=rules._selected_rule(SOURCES[0])
    if mid not in SOURCES:raise ValueError('selected Endure Connection source required')
    return mid


def learn_connection(e,actor,*,replace=None,advanced=False,teacher=None):
    """Called by the real Ability lesson, with shared permanent Move learning."""
    import move_state as M
    from source_context import verified_source
    verified_source(e.r,CONNECTION_ENGLISH,
        label='Vigor Connection English omission',source_root='source-audit')
    uid=vigor_source(e,actor)
    if uid is None:raise ValueError('actual Vigor Ability required for Connection')
    if type(advanced)is not bool:raise ValueError('explicit immediate Advanced Connection choice required')
    if advanced and replace is not None:raise ValueError('Advanced Connection avoids replacement')
    import advanced_connection as CONNECTION
    mid=connection_move(e.r,uid)
    known=M.known(e.r,actor.spec)
    if mid in known:
        if replace is not None:raise ValueError('known Connection Move needs no replacement')
        actor.spec.setdefault('move_learning_log',[]).append({'move_id':mid,'method':'connection','source':uid,
            'connection_ability':uid,'reason':'already known Move becomes an unforgettably linked Connection',
            'paid_tp':0,'lifetime':'permanent'})
    choice={'actor_id':actor.entity_id,'ability':uid,'advanced_connection':True} if advanced else (
        {'actor_id':actor.entity_id,'ability':uid,'forget':replace} if replace is not None else None)
    CONNECTION._learn(e,actor,uid,{mid},reason='Connection learns Endure on actual Vigor acquisition',
        choice=choice,prompt=False,learning_source=uid)
    return mid


def _vigor_receipt(e,actor):
    frame=getattr(e,'_endure_receiving',None)
    if not frame or frame['recipient'] is not actor:return None
    parent=getattr(e,'_move_completions',{}).get(frame['completion_id'])
    receipt=parent.get('endure',{}).get(actor.entity_id) if parent and parent['phase']=='targets' else None
    return receipt if receipt and receipt.get('used') and receipt.get('vigor',{}).get('used') else None


def prevent_massive(e,actor):
    receipt=_vigor_receipt(e,actor)
    if receipt is None:return False
    receipt['vigor']['prevented_massive_injury']=True
    return True


def after_damage(e,actor):
    receipt=_vigor_receipt(e,actor)
    if receipt is None or receipt['vigor'].get('resolved'):return
    vigor=receipt['vigor'];vigor['resolved']=True;vigor['healed']=0
    if receipt.get('hp_replacements'):
        vigor['healed']=e.heal(actor,e.tick(actor),source_kind='feature')


def known(e,actor):
    # An observer must not try to activate/select unrelated learned Moves.
    # The actual matching Endure still goes through ordinary source admission.
    names={mid for mid in SOURCES}
    names.update(e.r.moves[mid]['name'] for mid in SOURCES if mid in e.r.moves)
    return next((mid for name in actor.moves if name in names and (mid:=e.r.move_id(name)) in SOURCES),None)


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
    uid=vigor_source(e,target)
    if uid is not None and F.activation_allowed(target,uid,{'kind':'daily','uses':1},engine=e):
        choice=e.rulings.decide({'type':'vigor','unit':uid,'actor':target.name,'actor_id':target.entity_id,
            'move_id':mid,'event_id':event_id,'text':'Activate Vigor on this actual Endure use?'})
        if choice is not None and type(choice)is not bool:raise ValueError('explicit Vigor use or decline required')
        if choice is True:
            ACTION.triggered_free_action(e,target,uid)
            F.consume_activation(target,uid,{'kind':'daily','uses':1},engine=e)
            receipt=e._move_completions[completion_id]['endure'][target.entity_id]
            receipt['vigor']={'source':uid,'used':True,'resolved':False,'healed':0,'prevented_massive_injury':False}


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
    if receipt['source']==SOURCES[1]:
        denominator=2 if vigor_source(e,target)==VIGOR[1] else 4
        if proposed*denominator<=-target.base_max_hp:return proposed
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
            vigor=receipt.get('vigor')
            if vigor is not None:
                if (not receipt['used'] or vigor.get('source') not in VIGOR or vigor.get('used') is not True
                        or type(vigor.get('resolved'))is not bool or type(vigor.get('healed'))is not int or vigor['healed']<0
                        or type(vigor.get('prevented_massive_injury'))is not bool):
                    raise ValueError('actual source-owned Vigor Endure receipt required')
    return True
