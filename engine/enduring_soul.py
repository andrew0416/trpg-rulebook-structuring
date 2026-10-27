"""Enduring Soul's pre-faint adapter; life, reactions and Moves keep their owners."""
from copy import deepcopy
import breather as B
import frequency as F
import world_entities as W

SOURCE=B.NOT_YET
BANNED={'move/대폭발','move/아픔나누기','move/자폭'}
LOSS={'standard':1,'shift':1,'swift':1}


class _Occurrence:
    """Only the live LIFE.sync call creates this non-serializable authority."""
    def __init__(self,e,actor,owner,receipt,move_id,target):
        self.engine=e;self.actor=actor;self.owner=owner;self.parent=e._active_turn_actor
        self.phase='offered';self.move_id=move_id;self.target=target
        self.proof={'actor_id':actor.entity_id,'owner_id':owner.entity_id,
            'acquisition_request':receipt['request_id'],'hp':actor.hp,'maximum_hp':actor.base_max_hp,
            'injuries_before':actor.injuries,'scene':F.state(owner)['scene'],
            'move_id':move_id,'target_id':target.entity_id,'round':e.round_no}
        self.request_id='not-yet:'+owner.entity_id+':'+str(self.proof['scene'])


def conscious(actor):
    live=getattr(actor,'_enduring_not_yet_live',None)
    return bool(isinstance(live,_Occurrence) and live.actor is actor and live.phase in ('offered','moving')
        and not actor.dead and '기절' not in actor.conditions)


def _owner(e,actor):
    import acquired_features as A
    if actor.kind!='pokemon':return None
    owner=W.actor_index(e).get(actor.spec.get('trainer_id'))
    return owner if owner is not None and A.owned_rule_count(owner,SOURCE) else None


def interested(e,actor):return _owner(e,actor) is not None


def move_interested(e):return any(interested(e,c) for c in e.everyone)


def move_scope(e,actor):
    if not conscious(actor):return False
    import initiative_interrupts as I
    selected=I.selected_move_frame(e,actor)
    return bool(selected and selected[1]['source']==SOURCE)


def authorize_trigger(e,raw):
    if set(raw)!={'kind','actor_id','request_id'} or raw.get('kind')!='pre_faint':
        raise ValueError('actual Not Yet pre-faint trigger fields required')
    actor=W.actor_index(e).get(raw['actor_id'])
    live=getattr(actor,'_enduring_not_yet_live',None)
    if (not isinstance(live,_Occurrence) or live.engine is not e
            or live.actor is not actor or live.request_id!=raw['request_id'] or not conscious(actor)):
        raise ValueError('actual live LIFE pre-faint occurrence required; data is not authority')
    return dict(raw,owner=live.parent,round=e.round_no,proof=deepcopy(live.proof))


def authorize_request(e,actor,row,evidence):
    proof=evidence.get('proof',{})
    actor_id=row.get('actor_id',getattr(row.get('actor'),'entity_id',None))
    if (row['source']!=SOURCE or actor_id!=actor.entity_id or row['id']!=evidence['request_id']
            or row['move_id']!=proof.get('move_id') or row['mode']!='reaction' or row['payment']!='next'
            or row['clock']!='none' or row['budget']!=LOSS or row.get('debt_policy','hold')!='hold'):
        raise ValueError('Not Yet grants exactly one known native Interrupt and its next ordinary turn cost')
    actual=authorize_trigger(e,{k:evidence[k] for k in ('kind','actor_id','request_id')})
    if actual['proof']!=proof:raise ValueError('Not Yet live occurrence facts changed')


def begin_move(e,actor,move,completion_id):
    """Bind the source occurrence only at the existing native Move producer."""
    live=getattr(actor,'_enduring_not_yet_live',None)
    if not isinstance(live,_Occurrence):return
    import initiative_interrupts as I
    selected=I.selected_move_frame(e,actor)
    if selected is None or selected[1]['source']!=SOURCE:return
    authorize_request(e,actor,selected[1],getattr(e,I.KEY)['windows'][selected[0]['window_id']]['trigger'])
    if move['id']!=live.move_id:raise ValueError('Not Yet native selected Move changed')
    e._move_completions[completion_id]['not_yet_trigger']=deepcopy(live.proof)


def validate_window(e,window,row=None):
    import trainer_feature_acquisition as T
    proof=window['trigger'].get('proof',{});index=W.actor_index(e)
    actor=index.get(proof.get('actor_id'));owner=index.get(proof.get('owner_id'))
    if (actor is None or owner is None or type(proof.get('hp'))is not int or type(proof.get('maximum_hp'))is not int
            or not -proof['maximum_hp']<=proof['hp']<=0 or proof['maximum_hp']<=0
            or proof.get('round')!=window['round'] or proof.get('move_id') in BANNED):
        raise ValueError('Not Yet original actual pre-faint evidence changed')
    receipts=[r for _,r in T.static_acquisitions(owner,SOURCE) if r['request_id']==proof.get('acquisition_request')]
    if len(receipts)!=1:raise ValueError('Not Yet actual acquisition provenance required')
    if window['cursor']<len(window['requests']):
        authorize_trigger(e,{k:window['trigger'][k] for k in ('kind','actor_id','request_id')})
    if row is not None:
        if (row['source']!=SOURCE or row['actor'] is not actor or row['move_id']!=proof['move_id']
                or row['mode']!='reaction' or row['payment']!='next' or row['clock']!='none' or row['budget']!=LOSS):
            raise ValueError('Not Yet selected actual Move or normal turn cost changed')
        if row['status']=='completed':
            completed=e._move_completions.get(row['receipt'].get('move_completion'))
            if (completed is None or completed.get('not_yet_trigger')!=proof
                    or proof['target_id'] not in [a.entity_id for a in completed['targets']]):
                raise ValueError('Not Yet lost its actual selected target completion')


def faint_boundary(e,actor):
    live=getattr(actor,'_enduring_not_yet_live',None)
    if isinstance(live,_Occurrence):return conscious(actor)
    owner=_owner(e,actor)
    if (owner is None or actor.dead or '기절' in actor.conditions or actor.hp>0 or actor.hp<-actor.base_max_hp
            or not actor.on_field or actor.captured or not e.encounter_active):return False
    receipt=B.feature_receipt(e,owner,SOURCE)
    if not F.activation_allowed(owner,SOURCE,{'kind':'scene','uses':1},engine=e):return False
    import action_lifecycle as ACTION,turn as TURN
    if not TURN.can_act(e,owner) or not ACTION.status_permission(e,owner,'free',new_action=True):return False
    answer=e.rulings.decide({'type':'not_yet','unit':SOURCE,'actor':owner.name,'target':actor.name,
        'actor_id':owner.entity_id,'target_id':actor.entity_id,'hp':actor.hp,'maximum_hp':actor.base_max_hp,
        'text':'Use Not Yet? Choose one actual known Move and its primary target, or decline.'})
    if answer is None or answer is False:return False
    if type(answer)is not dict or set(answer)!={'move_id','target_id'}:raise ValueError('Not Yet needs an actual Move and primary target')
    mid=e.r.move_id(answer['move_id']);target=W.actor_index(e).get(answer['target_id'])
    if mid is None or mid in BANNED or mid in e.r.excluded_moves or mid not in {e.r.move_id(m) for m in actor.moves}:
        raise ValueError('Not Yet requires an actual known nonexcluded Move, never Explosion/Pain Split/Self-Destruct')
    W.require_actors(e,actor,target)
    live=_Occurrence(e,actor,owner,receipt,mid,target)
    actor._enduring_not_yet_live=live
    try:
        ACTION.triggered_free_action(e,owner,SOURCE)
        F.consume_activation(owner,SOURCE,{'kind':'scene','uses':1},engine=e)
        import precise_actions as PRECISE,life as LIFE,initiative_interrupts as INTERRUPTS
        PRECISE.gain_injury(e,actor,1,SOURCE)
        LIFE.sync(e,actor)
        if actor.dead:return True
        raw={'id':live.request_id,'actor_id':actor.entity_id,'source':SOURCE,'priority':0,
            'mode':'reaction','payment':'next','budget':dict(LOSS),'clock':'none','move_id':mid}
        queued=INTERRUPTS.queue(e,[raw],trigger={'kind':'pre_faint','actor_id':actor.entity_id,'request_id':live.request_id})
        INTERRUPTS.begin(e,queued['window_id'],live.request_id)
        live=getattr(actor,'_enduring_not_yet_live');live.phase='moving'
        result=e.use_move_on(actor,target,mid,e.everyone)
        if not any(r['actor'] is actor and r.get('not_yet_trigger')==live.proof
                for r in getattr(e,'_move_completions',{}).values()):
            raise ValueError('Not Yet selected native Move did not activate: '+repr(result))
        INTERRUPTS.finish(e)
        live=getattr(actor,'_enduring_not_yet_live');live.phase='complete'
        LIFE.faint(e,actor)
        return True
    finally:
        vars(actor).pop('_enduring_not_yet_live',None)
