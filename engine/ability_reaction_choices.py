"""Source choices after the native whole Move and its actual recipient return."""
from contextlib import contextmanager
from copy import deepcopy

import ability_transitions as ABILITIES
import action_lifecycle as ACTION
import frequency as FREQUENCY
import move_completion as COMPLETE
import root_resolution as ROOT
import state_grants as GRANTS
import world_entities as WORLD

SOURCE='ability/멸망의바디'
WATCH='_ability_reaction_watch'
KEY='ability_reaction_choices'
SCOPE='_ability_reaction_scope'


def _adapter(e,source):
    import perish_body as PB
    if source!=SOURCE or not PB.registration(e.r,source):
        raise ValueError('exact selected post-return Reaction source required')
    return PB


def _reason(reason):
    if type(reason)is not str or not reason.strip():
        raise ValueError('explicit Reaction decision reason required')


def _eligible(e,owner):
    import turn as TURN, boss_transitions as BOSS, body_modes as BODY
    WORLD.require_actors(e,owner)
    if (owner.dead or owner.captured or not owner.on_field or
            not ABILITIES.active(owner,SOURCE) or not TURN.can_act(e,owner) or
            not BOSS.action_permission(owner) or not BODY.permits(owner,'standard') or
            not ACTION.status_permission(e,owner,'standard')):
        raise ValueError('surviving source owner with Standard Reaction permission required')


def watch(e,owner,source,*,reason):
    import passive_events as PASSIVE
    PASSIVE.ensure_clear(e);_reason(reason);adapter=_adapter(e,source);_eligible(e,owner)
    if not FREQUENCY.activation_allowed(owner,source,adapter.definition(e.r)['frequency'],engine=e):
        raise ValueError('Reaction daily frequency unavailable')
    owner.spec.setdefault(WATCH,{})[source]={'source':source,'reason':reason}
    return deepcopy(owner.spec[WATCH][source])


def interested(e):
    return any(actor.spec.get(WATCH) for actor in WORLD.actor_index(e).values())


def bound(e,event_id):
    return bool(getattr(e,'_passive_events',{}).get(event_id,{}).get('ability_reaction_watch'))


def bind_event(e,event):
    watches={actor.entity_id:deepcopy(actor.spec[WATCH])
             for actor in WORLD.actor_index(e).values() if actor.spec.get(WATCH)}
    if watches:event['ability_reaction_watch']=watches


def _offer(e,event_id):
    event=e._passive_events.get(event_id)
    completion=None if event is None else getattr(e,COMPLETE.KEY,{}).get(event.get('completion_id'))
    row=None if completion is None else completion.get(KEY,{}).get('offers',{}).get(event_id)
    if row is None:raise ValueError('actual watched recipient Reaction offer required')
    return completion,row,event


def observe_return(e,event_id):
    """Capture a candidate; eligibility remains gated by the whole completion."""
    import reactive_ability_events as REACTIVE
    if event_id is None:return
    event=e._passive_events[event_id];owner=event['target']
    if SOURCE not in event.get('ability_reaction_watch',{}).get(owner.entity_id,{}):return
    completion=getattr(e,COMPLETE.KEY)[event['completion_id']]
    result=COMPLETE.recipient_result(completion,owner)
    returned=completion['native_returns'][event_id]['facts']
    if (result is None or not result['hit'] or result.get('cancelled') or returned['hit_prevented'] or
            not REACTIVE._melee(COMPLETE.event_move(e,event)) or owner is event['actor'] or
            (owner.entity_id in completion.get('received',{}) and result['child_event']!=event_id)):
        return
    try:_eligible(e,owner)
    except ValueError:return
    offers=completion.setdefault(KEY,{'offers':{}})['offers']
    if event_id in offers:return
    import move_defense_reactions as DEFENSE
    facts={'event_id':event_id,'completion_id':completion['id'],
           'parent_event_id':event.get('defense_parent',event_id),
           'owner_id':owner.entity_id,'attacker_id':event['actor'].entity_id,'source':SOURCE,
           'move':DEFENSE._move_facts(COMPLETE.event_move(e,event)),'native_return':deepcopy(returned),
           'watch':deepcopy(event['ability_reaction_watch'][owner.entity_id][SOURCE])}
    offers[event_id]={'facts':facts,'fingerprint':ROOT.fingerprint(facts),
                      'status':'offered','decision':None,'attempt':None}
    owner.spec.get(WATCH,{}).pop(SOURCE,None)


def _ready(e,event_id,owner):
    import passive_events as PASSIVE, heavy_injury_adapter as HEAVY, effect_contracts as EFFECTS
    PASSIVE.ensure_clear(e);HEAVY.ensure_clear(e);EFFECTS.ensure_clear(e)
    completion,row,event=_offer(e,event_id)
    facts=row['facts'];attacker=event['actor'];native=facts['native_return']
    if (row['status']!='offered' or facts['owner_id']!=owner.entity_id or
            e._active_turn_actor is not attacker or completion['round']!=e.round_no or
            completion['seconds']!=e.elapsed_seconds or
            next(reversed(getattr(e,COMPLETE.KEY)))!=completion['id'] or
            native['turn_serial']!=attacker.custom_conditions.get('combat_turn_serial',0) or
            native['action_history']!=getattr(attacker,'_action_history',[])):
        raise ValueError('Reaction belongs to another recipient or expired Move boundary')
    return COMPLETE.require_hit_return(e,event_id,owner)


def pending(e):
    result=[];index=WORLD.actor_index(e)
    for completion in getattr(e,COMPLETE.KEY,{}).values():
        for event_id,row in completion.get(KEY,{}).get('offers',{}).items():
            owner=index[row['facts']['owner_id']]
            try:_ready(e,event_id,owner);_eligible(e,owner)
            except ValueError:continue
            result.append({'event_id':event_id,'completion_id':completion['id'],
                           'owner_id':owner.entity_id,'source':SOURCE})
    return result


@contextmanager
def _scope(e,event_id,owner):
    previous=getattr(e,SCOPE,None);setattr(e,SCOPE,(event_id,owner.entity_id,SOURCE))
    try:yield
    finally:
        if previous is None:delattr(e,SCOPE)
        else:setattr(e,SCOPE,previous)


def require_post_return_reaction(e,owner,source,event_id):
    if source!=SOURCE or getattr(e,SCOPE,None)!=(event_id,owner.entity_id,source):
        raise ValueError('actual native post-return Reaction execution required')
    completion,row,event=_offer(e,event_id)
    COMPLETE.require_hit_return(e,event_id,owner);_eligible(e,owner)
    if row['facts']['owner_id']!=owner.entity_id:
        raise ValueError('actual Reaction owner changed')
    return {'event_id':event_id,'completion_id':completion['id'],'attacker':event['actor'],
            'recipient':owner,'move':completion['move']}


def _payment(e,owner):
    import initiative_interrupts as INIT
    # Off-turn Limited/Advanced spends the next upcoming owner action. Only
    # a real suspended action frame can retain a current budget to consume.
    frames=getattr(e,INIT.KEY,{}).get('frames',[])
    current=any(frame['parent'] is owner for frame in frames)
    budget=getattr(owner,'budget',None)
    return 'current' if current and budget and budget.get('standard',0)>0 else 'next'


def choose(e,event_id,owner,*,use,reason):
    _reason(reason);WORLD.require_actors(e,owner)
    if type(use)is not bool:raise ValueError('explicit typed Reaction choice required')
    _ready(e,event_id,owner)
    def apply(staged,actor):
        import initiative_interrupts as INIT, turn as TURN
        _ready(staged,event_id,actor)
        if not use:
            row=_offer(staged,event_id)[1]
            row.update(status='declined',decision={'use':False,'reason':reason})
            return deepcopy(row)
        _eligible(staged,actor);adapter=_adapter(staged,SOURCE)
        frequency=adapter.definition(staged.r)['frequency']
        if not FREQUENCY.activation_allowed(actor,SOURCE,frequency,engine=staged):
            raise ValueError('Reaction daily frequency unavailable')
        with _scope(staged,event_id,actor):
            plan=adapter.prepare(staged,actor,event_id)
            payment=_payment(staged,actor);parent=_offer(staged,event_id)[2].get('defense_parent',event_id)
            request='ability-reaction:'+event_id+':'+actor.entity_id
            queued=INIT.queue(staged,[{'id':request,'actor_id':actor.entity_id,'source':SOURCE,
                'priority':0,'mode':'reaction','payment':payment,'budget':{'standard':1},'clock':'none'}],
                trigger={'kind':'move','event_id':parent})
            window=queued['window_id'];INIT.begin(staged,window,request)
            if not TURN.spend(staged,actor,'standard',SOURCE):
                raise ValueError('actual Standard Reaction action unavailable')
            FREQUENCY.consume_activation(actor,SOURCE,frequency,engine=staged)
            import cheerleader as CHEER
            cheer_snapshot=CHEER.support_snapshot(staged,actor)
            activation=adapter.activate(staged,actor,plan)
            proof={'frequency':deepcopy(actor.spec['frequency_state']['activations'][SOURCE]),
                   'payment':payment,'window_id':window,'request_id':request}
            row=_offer(staged,event_id)[1]
            row.update(status='activated',decision={'use':True,'reason':reason},
                attempt={'source':SOURCE,'owner_id':actor.entity_id,'paid':True,'plan':deepcopy(plan),
                         'activation':activation,'payment':proof,'window_id':window,'request_id':request,
                         'fingerprint':ROOT.fingerprint({'plan':plan,'activation':activation,'payment':proof})})
            INIT.finish(staged)
        index=WORLD.actor_index(staged)
        targets=[index[entry['holder_id']] for entry in activation['conditions'] if entry['record_id'] is not None]
        CHEER.support(staged,cheer_snapshot,targets,{'kind':'choice_ability','source':SOURCE,'event_id':event_id})
        return deepcopy(_offer(staged,event_id)[1])
    return GRANTS.transition(e,owner,apply,include_grid=e.grid is not None,include_rulings=True)


def validate_world(e,index):
    import initiative_interrupts as INIT, move_defense_reactions as DEFENSE
    for actor in index.values():
        watches=actor.spec.get(WATCH,{})
        if type(watches)is not dict:raise ValueError('Reaction watches must be a mapping')
        for source,watch in watches.items():
            if source!=SOURCE or set(watch)!={'source','reason'} or watch['source']!=source:
                raise ValueError('Reaction watch source changed')
            _reason(watch['reason'])
    for completion in getattr(e,COMPLETE.KEY,{}).values():
        for event_id,row in completion.get(KEY,{}).get('offers',{}).items():
            event=e._passive_events.get(event_id);facts=row['facts']
            if (event is None or row['fingerprint']!=ROOT.fingerprint(facts) or
                    facts['event_id']!=event_id or facts['completion_id']!=completion['id'] or
                    facts['owner_id']!=event['target'].entity_id or facts['attacker_id']!=event['actor'].entity_id or
                    facts['source']!=SOURCE or facts['parent_event_id']!=event.get('defense_parent',event_id) or
                    facts['move']!=DEFENSE._move_facts(COMPLETE.event_move(e,event)) or
                    facts['native_return']!=completion.get('native_returns',{}).get(event_id,{}).get('facts') or
                    facts['watch']!=event.get('ability_reaction_watch',{}).get(facts['owner_id'],{}).get(SOURCE)):
                raise ValueError('Reaction offer lost its actual watched native recipient')
            if row['status']=='offered':
                if row['decision'] is not None or row['attempt'] is not None:raise ValueError('undecided Reaction has paid facts')
                continue
            decision=row['decision'];_reason(decision['reason'])
            if set(decision)!={'use','reason'} or type(decision['use'])is not bool:
                raise ValueError('exact Reaction decision required')
            if row['status']=='declined':
                if decision['use'] or row['attempt'] is not None:raise ValueError('declined Reaction cannot pay')
                continue
            if row['status']!='activated' or not decision['use']:raise ValueError('known Reaction decision required')
            COMPLETE.require_hit_return(e,event_id,index[facts['owner_id']])
            attempt=row['attempt'];proof=attempt['payment'];plan=attempt['plan']
            if (attempt['source']!=SOURCE or attempt['owner_id']!=facts['owner_id'] or attempt['paid'] is not True or
                    plan['event_id']!=event_id or plan['completion_id']!=completion['id'] or
                    plan['move']!=facts['move'] or plan['attacker_id']!=facts['attacker_id'] or
                    plan['owner_id']!=facts['owner_id'] or
                    attempt['fingerprint']!=ROOT.fingerprint({'plan':plan,'activation':attempt['activation'],'payment':proof}) or
                    proof['frequency'].get('kind')!='daily' or proof['frequency'].get('used')!=1):
                raise ValueError('Reaction lacks its paid exact source activation')
            window=getattr(e,INIT.KEY,{}).get('windows',{}).get(attempt['window_id'])
            request=None if window is None else next((r for r in window['requests'] if r['id']==attempt['request_id']),None)
            if (request is None or request['actor'] is not index[facts['owner_id']] or request['source']!=SOURCE or
                    request['mode']!='reaction' or request['budget']!={'standard':1} or
                    request['payment']!=proof['payment'] or proof['window_id']!=window['id'] or
                    proof['request_id']!=request['id'] or window['trigger']['event_id']!=facts['parent_event_id']):
                raise ValueError('Reaction lacks its actual Standard frame')
            if request['status']=='open' and getattr(e,SCOPE,None)==(event_id,facts['owner_id'],SOURCE):continue
            if request['status']!='completed' or request['receipt']['actions']!=['standard']:
                raise ValueError('Reaction Standard frame did not finish exactly once')
    return True
