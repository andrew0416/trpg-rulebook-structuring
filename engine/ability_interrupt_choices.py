"""Explicit source choices over actual native recipient accuracy evidence.

The existing passive continuation owns suspension and resume. Source adapters
own their effects. Free reactions share the already established Dodge payment.
"""
from contextlib import contextmanager
from copy import deepcopy
import json

import ability_transitions as ABILITIES
import action_lifecycle as ACTION
import frequency as FREQUENCY
import root_resolution as ROOT
import state_grants as GRANTS
import world_entities as WORLD

WATCH='_ability_interrupt_watch'
KEY='ability_interrupts'
SOURCE='ability/테라셸'
SOURCES=(SOURCE,'feat/예견')


def _adapter(e,source):
    if source=='feat/예견':
        if e.r._selected_rule(source)!=source:raise ValueError('selected Prescience required')
        return __import__('oracle')
    import tera_shell as TS
    if source!=SOURCE or e.r._selected_rule(source)!=source or not TS.registration(e.r,source):
        raise ValueError('exact selected recipient Interrupt source required')
    return TS


def _reason(reason):
    if type(reason)is not str or not reason.strip():raise ValueError('explicit Interrupt decision reason required')


def _eligible(e,actor,source):
    import reactive_ability_events as REACTIVE
    import vision_impairment as VISION
    WORLD.require_actors(e,actor)
    owned=bool(__import__('oracle').acquired(actor,source)) if source=='feat/예견' else ABILITIES.active(actor,source)
    if (actor.dead or actor.captured or not actor.on_field or not owned
            or not REACTIVE._reaction_allowed(e,actor) or source!='feat/예견' and VISION.accuracy_level(e,actor)=='total'):
        raise ValueError('actual available source owner and Interrupt permission required')


def pay_free(e,actor,source,frequency):
    """Pay only inside an authenticated source caller's native atomic scope."""
    import reactive_ability_events as REACTIVE
    if not REACTIVE._reaction_allowed(e,actor) or not FREQUENCY.activation_allowed(actor,source,frequency,engine=e,action_actor=actor):
        raise ValueError('Free reaction action or source frequency unavailable')
    ACTION.record_action(e,actor,'free')
    FREQUENCY.consume_activation(actor,source,frequency,engine=e,action_actor=actor)


def watch(e,owner,source,*,reason):
    import passive_events as PASSIVE
    PASSIVE.ensure_clear(e);_reason(reason);adapter=_adapter(e,source);_eligible(e,owner,source)
    if not FREQUENCY.activation_allowed(owner,source,adapter.definition(e.r)['frequency'],engine=e):
        raise ValueError('recipient Interrupt scene frequency exhausted')
    owner.spec.setdefault(WATCH,{})[source]={'source':source,'reason':reason}
    return deepcopy(owner.spec[WATCH][source])


def interested(e):
    return any(a.spec.get(WATCH) for a in WORLD.actor_index(e).values())


def bound(e,event_id):
    event=getattr(e,'_passive_events',{}).get(event_id,{})
    return bool(event.get('ability_interrupt_watch') or event.get(KEY))


def bind_event(e,event,move,completion_id):
    watches={a.entity_id:deepcopy(a.spec[WATCH]) for a in WORLD.actor_index(e).values() if a.spec.get(WATCH)}
    if not watches:return
    import move_defense_reactions as DEFENSE
    event['completion_id']=completion_id;DEFENSE._row(e,event)
    event['ability_interrupt_watch']=watches


def wants_boundary(event):
    return bool(event.get('ability_interrupt_watch') and event.get('hit') is True)


def _recipients(e,event):
    import move_defense_reactions as DEFENSE
    defense=DEFENSE._defense(e,event)
    if defense is not None:
        if defense['phase'] not in ('resolving','complete'):
            raise ValueError('recipient choices require completed defense routing')
        return deepcopy(defense['recipients'])
    return [{'actor_id':event['target'].entity_id,'hit':event['hit'],'intercepted':False}]


def _facts(e,event,args):
    import move_defense_reactions as DEFENSE
    completion=DEFENSE._row(e,event)
    return {'event_id':event['id'],'completion_id':completion['id'],
        'attacker_id':event['actor'].entity_id,'original_id':event['target'].entity_id,
        'move':DEFENSE._move_facts(args['move']),'recipients':_recipients(e,event),
        'watch':deepcopy(event['ability_interrupt_watch'])}


def _validate(e,event,row,index):
    import passive_events as PASSIVE,move_defense_reactions as DEFENSE,move_completion as COMPLETE
    facts=row['facts']
    if row['fingerprint']!=ROOT.fingerprint(facts):raise ValueError('recipient Interrupt facts changed')
    completion=DEFENSE._row(e,event)
    if (facts['event_id']!=event['id'] or facts['completion_id']!=completion['id']
            or facts['attacker_id']!=event['actor'].entity_id or facts['original_id']!=event['target'].entity_id
            or facts['move']!=DEFENSE._move_facts(COMPLETE.event_move(e,event))
            or facts['watch']!=event['ability_interrupt_watch']):
        raise ValueError('recipient Interrupt lost its actual native Move evidence')
    accuracy=next((x['facts'] for x in PASSIVE.observations(e,event['id']) if x['stage']=='accuracy'),None)
    if accuracy is None or accuracy['hit'] is not True:raise ValueError('recipient Interrupt requires actual successful accuracy')
    if row['phase'] not in ('choices','complete','cancelled'):raise ValueError('recipient Interrupt phase changed')
    if row['phase']=='cancelled' and (event.get('continuation_cancelled')!='actor_no_longer_eligible'
            or event.get('continuation') is not None
            or not completion['results'].get(facts['original_id'],{}).get('cancelled')):
        raise ValueError('cancelled recipient choice lacks the native cancelled Move result')
    if row['phase']!='cancelled' and facts['recipients']!=_recipients(e,event):
        raise ValueError('recipient Interrupt routing changed')
    offers=row['offers']
    expected=[{'owner_id':r['actor_id'],'source':source}
              for r in facts['recipients'] if r['hit']
              for source in facts['watch'].get(r['actor_id'],{})]
    if offers!=expected or any(o['source'] not in SOURCES or o['owner_id'] not in index for o in offers):
        raise ValueError('recipient Interrupt offers differ from actual watched recipients')
    if type(row['cursor'])is not int or not 0<=row['cursor']<=len(offers) or len(row['attempts'])!=row['cursor']:
        raise ValueError('recipient Interrupt attempted prefix changed')
    if row['phase']=='complete' and row['cursor']!=len(offers):raise ValueError('recipient Interrupt skipped a choice')
    if set(row['decisions'])!={str(i) for i in range(row['cursor'])}:
        # One newly accepted choice may exist while its atomic adapter runs.
        if (set(row['decisions'])!={str(i) for i in range(row['cursor']+1)}
                or (getattr(e,'_ability_interrupt_scope',None) is None
                    and getattr(e,'_ability_choice_delivery',None)!=event['id'])):
            raise ValueError('recipient Interrupt decision prefix changed')
    for number,attempt in enumerate(row['attempts']):
        offer=offers[number];decision=row['decisions'][str(number)]
        if (set(decision)!={'use','options','reason'} or type(decision['use'])is not bool
                or type(decision['options'])is not dict):
            raise ValueError('explicit typed recipient decision required')
        _reason(decision['reason'])
        if any(attempt[k]!=offer[k] for k in ('owner_id','source')):raise ValueError('Interrupt paid owner/source changed')
        if attempt['paid']:
            actor=index[offer['owner_id']];at=attempt['history_index']
            proof=attempt['payment']
            if (not decision['use'] or attempt['outcome']!='activated' or proof['actions']!=['free']
                    or proof['frequency']['kind']!='scene' or proof['frequency']['used']!=1 or
                    attempt['payment_fingerprint']!=ROOT.fingerprint(proof) or
                    attempt['plan_fingerprint']!=ROOT.fingerprint(attempt['plan'])):
                raise ValueError('Interrupt lacks its actual Free action or effect plan')
            plan=attempt['plan']
            wrong_options=(bool(decision['options']) if offer['source']=='feat/예견' else set(decision['options'])!={'chosen_type'} or plan['chosen_type']!=decision['options']['chosen_type'])
            if (wrong_options
                    or plan['move']!=facts['move'] or plan['event_id']!=facts['event_id']
                    or plan['completion_id']!=facts['completion_id'] or plan['attacker_id']!=facts['attacker_id']
                    or plan['owner_id']!=offer['owner_id'] or plan['source']!=offer['source']):
                raise ValueError('Interrupt effect plan differs from the actual Move or chosen recipient')
            # Action history belongs to one turn and is reset by its owner.
            # Past choices retain a sealed payment receipt across that reset.
            if row['phase']=='choices' and getattr(actor,'_action_history',[])[at:at+1]!=['free']:
                raise ValueError('pending Interrupt has lost its paid Free action')
        elif attempt['outcome'] not in ('declined','unavailable'):
            raise ValueError('unpaid recipient Interrupt result changed')
        elif attempt['outcome']=='declined' and decision['use']:
            raise ValueError('declined Interrupt decision changed')


@contextmanager
def _scope(e,event_id,owner,source):
    previous=getattr(e,'_ability_interrupt_scope',None)
    e._ability_interrupt_scope=(event_id,owner.entity_id,source)
    try:yield
    finally:
        if previous is None:del e._ability_interrupt_scope
        else:e._ability_interrupt_scope=previous


def require_accuracy_interrupt(e,owner,source,event_id):
    import passive_events as PASSIVE
    if getattr(e,'_ability_interrupt_scope',None)!=(event_id,owner.entity_id,source):
        raise ValueError('actual native recipient Interrupt execution required')
    event=e._passive_events.get(event_id)
    if event is None or event['phase']!='accuracy_boundary' or event.get('continuation') is None:
        raise ValueError('recipient Interrupt requires its native accuracy continuation')
    frame=event['continuation']
    if ROOT.fingerprint(PASSIVE._continuation_facts(e,event,frame))!=frame['fingerprint']:
        raise ValueError('recipient Interrupt continuation changed')
    row=event[KEY];_validate(e,event,row,WORLD.actor_index(e))
    offer=row['offers'][row['cursor']]
    if offer!={'owner_id':owner.entity_id,'source':source}:raise ValueError('recipient Interrupt owner or source changed')
    _eligible(e,owner,source)
    return dict(event_id=event_id,completion_id=event['completion_id'],recipient=owner,
                attacker=event['actor'],move=deepcopy(frame['args']['move']))


def deliver_boundary(e,event,args):
    import passive_events as PASSIVE, effects_ext as EXT
    if not wants_boundary(event):return
    row=event.get(KEY)
    if row is None:
        facts=_facts(e,event,args)
        offers=[{'owner_id':r['actor_id'],'source':source}
                for r in facts['recipients'] if r['hit']
                for source in facts['watch'].get(r['actor_id'],{})]
        row={'facts':facts,'fingerprint':ROOT.fingerprint(facts),'offers':offers,
             'cursor':0,'decisions':{},'attempts':[],'phase':'choices'}
        event[KEY]=row
        index=WORLD.actor_index(e)
        for offer in offers:index[offer['owner_id']].spec.get(WATCH,{}).pop(offer['source'],None)
    if row['phase']!='choices':return
    _validate(e,event,row,WORLD.actor_index(e))
    while row['cursor']<len(row['offers']):
        number=row['cursor'];offer=row['offers'][number];owner=WORLD.actor_index(e)[offer['owner_id']]
        source=offer['source'];decision=row['decisions'].get(str(number))
        decoy=source=='feat/예견' and __import__('substitute').intercept(e,event['actor'],owner,args['move']) is not None
        if decision is None:
            if decoy or EXT.blocks_hit(e,event['actor'],owner,args['move'],args['mm']):
                row['decisions'][str(number)]={'use':False,'options':{},'reason':'actual Move cannot hit recipient'}
                row['attempts'].append(dict(offer,outcome='unavailable',paid=False));row['cursor']+=1;continue
            return PASSIVE._pending(e,event,'actual_ability_interrupt_choice')
        if not decision['use']:
            row['attempts'].append(dict(offer,outcome='declined',paid=False));row['cursor']+=1;continue
        if source=='feat/예견':
            if decision['options']:raise ValueError('Prescience has no type choice')
        elif set(decision['options'])!={'chosen_type'}:raise ValueError('exact type choice required for this source')
        if decoy or EXT.blocks_hit(e,event['actor'],owner,args['move'],args['mm']):
            raise ValueError('actual Move no longer hits recipient')
        adapter=_adapter(e,source)
        with _scope(e,event['id'],owner,source):
            plan=adapter.prepare(e,owner,event['id']) if source=='feat/예견' else adapter.prepare(e,owner,event['id'],decision['options']['chosen_type'])
            json.dumps(plan,ensure_ascii=False,allow_nan=False)
            history=len(getattr(owner,'_action_history',[]))
            pay_free(e,owner,source,adapter.definition(e.r)['frequency'])
            payment={'actions':getattr(owner,'_action_history',[])[history:history+1],
                'frequency':deepcopy(owner.spec['frequency_state']['activations'][source]),
                'owner_turn':owner.turns_taken,'round':e.round_no}
            import cheerleader as CHEER
            cheer_snapshot=CHEER.support_snapshot(e,owner)
            activation=adapter.activate(e,owner,plan)
        # Adapters may use existing nested source transitions; reacquire state.
        event=e._passive_events[event['id']];row=event[KEY]
        row['attempts'].append(dict(offer,outcome='activated',paid=True,plan=deepcopy(plan),
            plan_fingerprint=ROOT.fingerprint(plan),history_index=history,activation=activation,
            payment=payment,payment_fingerprint=ROOT.fingerprint(payment)))
        row['cursor']+=1
        CHEER.support(e,cheer_snapshot,[owner],{'kind':'choice_ability','source':source,'event_id':event['id']})
    row['phase']='complete'


def cancel_waiting(e,event):
    row=event.get(KEY)
    if row is None:return
    if row['phase']!='choices':raise ValueError('only unresolved recipient choices can be cancelled')
    # A call to choose may have submitted the next decision immediately before
    # the native continuation discovers that its attacker became ineligible.
    row['decisions'].pop(str(row['cursor']),None)
    row['phase']='cancelled'


def choose(e,event_id,owner,*,use,options=None,reason):
    import passive_events as PASSIVE
    _reason(reason);WORLD.require_actors(e,owner)
    if type(use)is not bool or options is not None and type(options)is not dict:
        raise ValueError('explicit recipient Interrupt choice required')
    options={} if options is None else deepcopy(options)
    if not use and options:raise ValueError('declined Interrupt has no effect options')
    json.dumps(options,ensure_ascii=False,allow_nan=False)
    event=e._passive_events.get(event_id)
    if event is None or e._passive_pending!=event_id or event['phase']!='accuracy_boundary' or KEY not in event:
        raise ValueError('actual waiting recipient Interrupt required')
    row=event[KEY];_validate(e,event,row,WORLD.actor_index(e))
    if row['phase']!='choices' or row['cursor']>=len(row['offers']) or row['offers'][row['cursor']]['owner_id']!=owner.entity_id:
        raise ValueError('this actual recipient is not the next Interrupt choice')
    def apply(staged,actor):
        row=staged._passive_events[event_id][KEY]
        row['decisions'][str(row['cursor'])]={'use':use,'options':options,'reason':reason}
        staged._ability_choice_delivery=event_id
        try:return PASSIVE.deliver(staged,event_id)
        except PASSIVE.PassiveEventPending as pending:
            if staged._passive_pending!=pending.event_id or pending.event_id not in staged._passive_events:raise
        finally:del staged._ability_choice_delivery
    result=GRANTS.transition(e,owner,apply,include_grid=e.grid is not None,include_rulings=True)
    if e._passive_pending is not None:raise PASSIVE.PassiveEventPending(e._passive_pending)
    return result


def validate_world(e,index):
    for actor in index.values():
        watches=actor.spec.get(WATCH,{})
        if type(watches)is not dict:raise ValueError('recipient Interrupt watches required')
        for source,watch in watches.items():
            if source not in SOURCES or set(watch)!={'source','reason'} or watch['source']!=source:
                raise ValueError('recipient Interrupt watch source changed')
            _reason(watch['reason'])
    for event in getattr(e,'_passive_events',{}).values():
        if KEY in event:_validate(e,event,event[KEY],index)
    return True
