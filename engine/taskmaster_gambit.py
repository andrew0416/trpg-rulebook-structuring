"""Durable Deadly Gambit declarations and native parent/counter continuations.

The native Move owns payment, accuracy and effects. Only data/observations live
in passive events; Heavy tokens and paired damage scopes are reissued by the
original native producer after restore, never serialized as permissions.
"""
from contextlib import contextmanager
from copy import deepcopy
import common_checks as C
import root_resolution as R
import world_entities as W

KEY='taskmaster_gambit'
LINK='taskmaster_gambit_parent'
MARKER='_taskmaster_gambit_event'
CACHE='taskmaster_gambit_damage'


def _root(engine,event):
    seen=set()
    while event.get('defense_parent'):
        if event['id'] in seen:raise ValueError('cyclic native defense ancestry')
        seen.add(event['id']);event=engine._passive_events[event['defense_parent']]
    return event


def parent(engine,event):
    event=_root(engine,event)
    if KEY in event:return event
    uid=event.get(LINK)
    return engine._passive_events.get(uid) if uid is not None else None


def interested(engine,attacker,target,move):
    import taskmaster as T,frequency as F,weapon_actions as WEAPONS
    active=getattr(engine,'_taskmaster_gambit',None)
    if active is not None:
        return (active['pokemon'] is attacker and active['incoming_attacker'] is target
                and active['counter_id']==move['id'])
    if (target is None or target.kind!='pokemon' or target.fainted or not T._side(attacker)
            or not T._side(target) or T._side(attacker)==T._side(target)
            or move.get('class') not in ('물리','특수')
            or WEAPONS.range_spec(engine,move,attacker).get('origin')!='melee'):
        return False
    owner=W.actor_index(engine).get(target.spec.get('trainer_id'))
    return bool(owner is not None and T.acquired(owner,T.GAMBIT) is not None
                and F.activation_allowed(owner,T.GAMBIT,{'kind':'scene','uses':T.DEFINITIONS[T.GAMBIT]['parameters']['scene']},engine=engine))


def frame_interested(engine,actor,target):
    if getattr(engine,'_taskmaster_gambit',None) is not None:return True
    if target is None or target.kind!='pokemon':return False
    import taskmaster as T
    owner=W.actor_index(engine).get(target.spec.get('trainer_id'))
    return owner is not None and T.acquired(owner,T.GAMBIT) is not None


def _progress(row):
    return {key:row[key] for key in ('counter_event','counter_completion','damage_event','wait','done','cancel_reason')}


def _seal(row):
    row['progress_fingerprint']=R.fingerprint(_progress(row))


def checked(engine,event,*,live=False):
    import taskmaster as T,move_activation as ACT,effect_contracts as CONTRACTS
    row=event.get(KEY)
    expected={'facts','fingerprint','counter_event','counter_completion','damage_event','wait','done','cancel_reason','progress_fingerprint'}
    if type(row)is not dict or set(row)!=expected:raise ValueError('actual paid Gambit declaration required')
    f=row['facts'];fields={'event_id','completion_id','owner_id','pokemon_id','attacker_id','move_id','counter_id','counter_options','roll_effects','acquisition','profile','boundary','source_profile'}
    if type(f)is not dict or set(f)!=fields or row['fingerprint']!=R.fingerprint(f):
        raise ValueError('paid Gambit declaration changed')
    index=W.actor_index(engine)
    if (f['event_id']!=event['id'] or f['completion_id']!=event['completion_id']
            or event['producer']!='Engine.use_move' or event['actor'] is not index.get(f['attacker_id'])
            or event['target'] is not index.get(f['pokemon_id']) or f['move_id']!=event['move_id']
            or f['owner_id'] not in index):
        raise ValueError('Gambit actual producer identity changed')
    owner=index[f['owner_id']]
    if not any(r['request_id']==f['acquisition'] for r in T.acquisitions(owner,T.GAMBIT)):
        raise ValueError('Gambit lost its actual acquisition observation')
    if type(f['roll_effects'])is not bool or type(f['counter_options'])is not dict:
        raise ValueError('Gambit selected counter contract changed')
    if f['counter_id'] is not None and f['counter_id'] not in engine.r.moves:
        raise ValueError('Gambit selected counter Move missing')
    completion=engine._move_completions.get(f['completion_id'])
    if completion is None or completion['actor'] is not event['actor'] or completion['move_id']!=f['move_id']:
        raise ValueError('Gambit paid parent completion missing')
    if row['progress_fingerprint']!=R.fingerprint(_progress(row)) or type(row['done'])is not bool:
        raise ValueError('Gambit continuation progress changed')
    if (row['counter_event'] is None)!=(row['counter_completion'] is None):
        raise ValueError('Gambit counter event/completion must agree')
    if row['counter_event'] is not None:
        child=engine._passive_events.get(row['counter_event'])
        if (child is None or child.get(LINK)!=event['id'] or child['actor'] is not event['target']
                or child['target'] is not event['actor'] or child['move_id']!=f['counter_id']
                or child['completion_id']!=row['counter_completion']):
            raise ValueError('Gambit counter is not the actual paid reverse attack')
        counter=engine._move_completions.get(row['counter_completion'])
        if counter is None or counter['actor'] is not event['target'] or counter['move_id']!=f['counter_id'] or counter['targets']!=[event['actor']]:
            raise ValueError('Gambit counter completion changed its actual participants')
    if row['damage_event'] is not None:
        native=engine._passive_events.get(row['damage_event'])
        if native is None or _root(engine,native) is not event or CACHE not in native:
            raise ValueError('Gambit parent damage observation missing')
    wait=row['wait']
    if wait is not None:
        if type(wait)is not dict or set(wait)!={'event_id','phase'} or wait['phase'] not in ('before_damage','after_damage','external','parent_cancelled'):
            raise ValueError('actual Gambit native wait required')
        pending=engine._passive_events.get(wait['event_id'])
        if pending is None or row['counter_event'] is None or row['done']:
            raise ValueError('Gambit wait lost its actual counter producer')
        if wait['phase']=='parent_cancelled' and (row['cancel_reason']!='incoming_cancelled' or not _native_cancelled(engine,event)):
            raise ValueError('cancelled Gambit parent needs its actual native cancellation')
        if wait['phase']=='before_damage' and _root(engine,pending)['id']!=row['counter_event']:
            raise ValueError('Gambit pre-damage wait is not its counter')
    if live and (f['profile']!=ACT._profile(engine) or tuple(f['boundary'])!=tuple(ACT._transition_lifetime(engine)[1:])
                 or f['source_profile']!=CONTRACTS.source_profile(engine,T.GAMBIT)):
        raise ValueError('paid Gambit source or action boundary changed')
    return row


def create(engine,attacker,pokemon,owner,move,counter,options,roll_effects,event_id,completion_id):
    import taskmaster as T,move_activation as ACT,effect_contracts as CONTRACTS
    event=engine._passive_events.get(event_id)
    if event is None or event['actor'] is not attacker or event['target'] is not pokemon or event['completion_id']!=completion_id or KEY in event:
        raise ValueError('Gambit needs the actual native selected target occurrence')
    facts={'event_id':event_id,'completion_id':completion_id,'owner_id':owner.entity_id,
           'pokemon_id':pokemon.entity_id,'attacker_id':attacker.entity_id,'move_id':move['id'],
           'counter_id':counter,'counter_options':deepcopy(options),'roll_effects':roll_effects,
           'acquisition':T.acquired(owner,T.GAMBIT)['request_id'],'profile':ACT._profile(engine),
           'boundary':ACT._transition_lifetime(engine)[1:],'source_profile':CONTRACTS.source_profile(engine,T.GAMBIT)}
    row={'facts':facts,'fingerprint':R.fingerprint(facts),'counter_event':None,'counter_completion':None,
         'damage_event':None,'wait':None,'done':False,'cancel_reason':None}
    _seal(row);event[KEY]=row
    engine._taskmaster_gambit=runtime(engine,event)
    return dict(move,**{MARKER:event_id})


def runtime(engine,event):
    row=checked(engine,event);f=row['facts'];index=W.actor_index(engine)
    return {'event_id':event['id'],'incoming_attacker':index[f['attacker_id']],'pokemon':index[f['pokemon_id']],
            'move_id':f['move_id'],'counter_id':None if row['cancel_reason'] else f['counter_id'],
            'counter_options':deepcopy(f['counter_options']),'roll_effects':f['roll_effects'],
            'phase':'incoming','applied':bool(row['wait'] and row['wait']['phase']=='after_damage')}


def require_counter_grant(engine,actor,target,move_id):
    """Authorize issuance before the actual counter Move receives its marker."""
    active=getattr(engine,'_taskmaster_gambit',None)
    if (active is None or active.get('phase')!='counter_issuing'
            or active['pokemon'] is not actor or active['incoming_attacker'] is not target
            or active['counter_id']!=move_id):
        raise ValueError('actual Deadly Gambit counter issuance scope required')
    original=engine._passive_events.get(active['event_id'])
    if original is None:raise ValueError('actual paid Gambit parent required')
    row=checked(engine,original,live=True)
    prepared=active.get('prepared')
    if (row['done'] or row['counter_event'] is not None or row['wait'] is not None
            or row['facts']['counter_id']!=move_id or original['target'] is not actor
            or original['actor'] is not target or row['damage_event'] is None
            or not prepared or prepared['attacker'] is not target or prepared['target'] is not actor
            or side(engine,target,actor,prepared['move'])!='incoming'
            or not counter_eligible(engine,original)):
        raise ValueError('Gambit counter requires its actual prepared paid incoming hit')
    # The source is the still-running parent producer with its live Heavy
    # receipt, not a raw Move ID or a prematurely fabricated counter marker.
    import heavy_injury_adapter as HEAVY
    if HEAVY.validate_native_receipt(engine,prepared['context'],target,actor,prepared['move']) is None:
        raise ValueError('Gambit counter requires the live original native damage receipt')


def counter_reaction_origin(engine,event_id,*,live):
    """Join a counter defense to the actual incoming attack's suspended turn."""
    event=engine._passive_events.get(event_id)
    if event is None or event.get('producer')!='Engine.use_move' or LINK not in event:return None
    original=engine._passive_events.get(event[LINK])
    if original is None:raise ValueError('Gambit counter reaction lost its original attack')
    row=checked(engine,original,live=live)
    if row['counter_event']!=event_id:raise ValueError('Gambit defense is not its actual paid counter')
    # An AoO can be nested inside another actor's paid movement. The native
    # parent records the suspended turn separately from its attacking actor.
    suspended=W.actor_index(engine).get(row['facts']['boundary'][2])
    if suspended is None:return None
    if live:
        active=getattr(engine,'_taskmaster_gambit',None)
        if (row['done'] or suspended is not engine._active_turn_actor
                or event['phase']!='accuracy_boundary' or active is None
                or active.get('event_id')!=original['id']
                or active.get('phase') not in ('counter','counter_issuing')):
            return None
        prepared=active.get('prepared')
        if (not prepared or prepared['attacker'] is not original['actor']
                or prepared['target'] is not original['target']
                or side(engine,prepared['attacker'],prepared['target'],prepared['move'])!='incoming'):
            raise ValueError('Gambit defense needs its still-running original native producer')
        import heavy_injury_adapter as HEAVY
        if HEAVY.validate_native_receipt(engine,prepared['context'],prepared['attacker'],prepared['target'],prepared['move']) is None:
            raise ValueError('Gambit defense lost the live original native receipt')
    return {'source':__import__('taskmaster').GAMBIT,'event_id':event_id,
            'completion_id':event['completion_id'],'parent_event_id':original['id'],
            'parent_completion_id':original['completion_id'],'owner_id':suspended.entity_id,
            'actor_id':event['actor'].entity_id,'target_id':event['target'].entity_id,
            'round':event['round'],'declaration':row['fingerprint']}


def bind_counter(engine,attacker,target,move,event_id,completion_id):
    active=getattr(engine,'_taskmaster_gambit',None)
    if (active is None or active.get('phase')!='counter_issuing' or active['pokemon'] is not attacker
            or active['incoming_attacker'] is not target or active['counter_id']!=move['id']):
        return move
    original=engine._passive_events[active['event_id']];row=checked(engine,original)
    event=engine._passive_events.get(event_id)
    if event is None or row['counter_event'] is not None or event['actor'] is not attacker or event['target'] is not target or event['completion_id']!=completion_id:
        raise ValueError('one actual Gambit counter activation required')
    row.update(counter_event=event_id,counter_completion=completion_id);_seal(row)
    event[LINK]=original['id']
    return dict(move,**{MARKER:original['id']})


def side(engine,attacker,target,move):
    active=getattr(engine,'_taskmaster_gambit',None)
    if not active or move.get(MARKER)!=active.get('event_id'):return None
    if active['incoming_attacker'] is attacker and active['pokemon'] is target and active['move_id']==move['id']:return 'incoming'
    if active['pokemon'] is attacker and active['incoming_attacker'] is target and active['counter_id']==move['id']:return 'counter'
    return None


@contextmanager
def restored_scope(engine,event):
    original=parent(engine,event)
    if original is None:yield;return
    row=checked(engine,original,live=not original[KEY]['done'])
    if row['done']:yield;return
    old=getattr(engine,'_taskmaster_gambit',None)
    if old is not None:
        if old.get('event_id')!=original['id']:raise ValueError('another Gambit owns the native pair scope')
        yield;return
    existed=hasattr(engine,'_taskmaster_gambit')
    engine._taskmaster_gambit=runtime(engine,original)
    try:yield
    finally:
        if existed:engine._taskmaster_gambit=old
        else:vars(engine).pop('_taskmaster_gambit',None)


def counter_eligible(engine,event):
    import taskmaster as T,move_state as MOVES,frequency as F,turn as TURN,action_lifecycle as ACTION,body_modes as BODY
    row=checked(engine,event,live=True);f=row['facts'];index=W.actor_index(engine)
    owner=index[f['owner_id']];pokemon=event['target'];foe=event['actor']
    acquired=T.acquired(owner,T.GAMBIT)
    return bool(acquired and acquired['request_id']==f['acquisition']
                and pokemon.spec.get('trainer_id')==owner.entity_id
                and pokemon.on_field and not pokemon.captured and not pokemon.dead and not pokemon.fainted
                and foe.on_field and not foe.captured and not foe.dead and not foe.fainted
                and TURN.can_act(engine,pokemon) and BODY.permits(pokemon,'free')
                and ACTION.status_permission(engine,pokemon,'free',new_action=True)
                and (f['counter_id']=='struggle' or f['counter_id'] in MOVES.known(engine.r,pokemon.spec))
                and F.move_allowed(engine,pokemon,f['counter_id'],outside_combat=False)[0])


def retain_damage(engine,attacker,target,move,event_id,snapshot,precision_event):
    if side(engine,attacker,target,move)!='incoming':return
    if CACHE in engine._passive_events.get(event_id,{}):return
    active=engine._taskmaster_gambit
    if active['counter_id'] is None:return
    original=engine._passive_events[active['event_id']];row=checked(engine,original)
    native=engine._passive_events[event_id]
    if _root(engine,native) is not original:raise ValueError('Gambit damage has another recipient producer')
    import coordinator as OBS
    memo={id(a):a for a in W.actor_index(engine).values()};memo[id(engine)]=engine
    cached={'event_id':event_id,'parent_event':original['id'],'actor_id':attacker.entity_id,
            'target_id':target.entity_id,'move_id':move['id'],'snapshot':deepcopy(snapshot,memo),
            'precision_event_id':None if precision_event is None else precision_event['id']}
    cached['sha256']=OBS._damage_seal(cached);native[CACHE]=cached
    row['damage_event']=event_id;_seal(row)


def restore_damage(engine,attacker,target,move,event_id):
    native=engine._passive_events.get(event_id);cached=None if native is None else native.get(CACHE)
    if cached is None:return None
    import coordinator as OBS
    if (cached.get('sha256')!=OBS._damage_seal(cached) or cached['event_id']!=event_id
            or cached['actor_id']!=attacker.entity_id or cached['target_id']!=target.entity_id
            or cached['move_id']!=move['id'] or side(engine,attacker,target,move)!='incoming'):
        raise ValueError('actual Gambit damage observation changed')
    original=engine._passive_events[cached['parent_event']];row=checked(engine,original,live=True)
    if row['damage_event']!=event_id:raise ValueError('Gambit damage lost its actual parent')
    memo={id(a):a for a in W.actor_index(engine).values()};memo[id(engine)]=engine
    return deepcopy(cached['snapshot'],memo)


def retained_recipient(engine,original,target,token):
    row=original.get(KEY)
    if row is None or row['wait'] is None or row['wait']['phase']!='before_damage':return None
    row=checked(engine,original,live=True)
    native=engine._passive_events.get(row['damage_event'])
    if native is None or native.get('defense_parent')!=original['id'] or native['target'] is not target:
        return None
    if tuple(native.get('defense_token',()))!=tuple(token):raise ValueError('Gambit recipient token changed')
    return native


def retained_precision(engine,event):
    cached=event.get(CACHE)
    if cached is None:return None
    identity=cached['precision_event_id']
    if identity is None:return None
    rows=[row for row in engine._precision_events if row['id']==identity]
    if len(rows)!=1:raise ValueError('Gambit precision observation missing')
    return rows[0]


def _detect_dependency(engine,original,pending,*,returned=False):
    """Recognize only the actual selected Detect Move interrupting this counter."""
    import move_defense_reactions as D,initiative_interrupts as I,move_completion as COMPLETE
    row=original[KEY];counter=engine._passive_events.get(row['counter_event'])
    if counter is None:return None
    state=D._defense(engine,counter)
    attempt=None if state is None else state.get('active_attempt')
    if not attempt or attempt.get('kind')!='detect':return None
    facts=attempt['facts'];current=I.frame(engine)
    if attempt['fingerprint']!=R.fingerprint(facts):
        raise ValueError('Gambit foreign Detect attempt changed')
    # A deeper native reaction (for example Quick Guard reacting to Detect)
    # can own the top frame. It is outside this narrow Detect continuation;
    # preserve its real pending event instead of converting it to rejection.
    if (current is None or current['window_id']!=facts['window_id']
            or current['request_id']!=facts['request_id']):
        return None
    if current['status']!='open':
        raise ValueError('Gambit foreign Detect lost its actual native interrupt frame')
    window=getattr(engine,I.KEY)['windows'][current['window_id']]
    request=next((r for r in window['requests'] if r['id']==current['request_id']),None)
    foreign=_root(engine,pending)
    if (window['signature']!=I._signature(window['trigger'],window['requests'])
            or window['trigger'].get('kind')!='accuracy' or window['trigger'].get('event_id')!=counter['id']
            or request is None or request['status']!='open' or window['requests'][window['cursor']] is not request
            or facts['source']!=D.DETECT or facts['actor_id']!=foreign['actor'].entity_id
            or request.get('move_id')!=D.DETECT or request['source']!=D.DETECT
            or current['actor'] is not foreign['actor'] or request['actor'] is not foreign['actor']
            or foreign['actor'] is not counter['target'] or foreign['target'] is not foreign['actor']
            or foreign['producer']!='Engine.use_move' or foreign['move_id']!=D.DETECT):
        return None
    completions=[c for uid,c in engine._move_completions.items()
                 if uid not in current['completion_ids_before'] and c['actor'] is current['actor']]
    if len(completions)!=1 or completions[0]['id']!=foreign['completion_id']:
        raise ValueError('Gambit foreign wait is not the actual selected Detect completion')
    if returned:
        if completions[0]['phase']!='complete':return None
        COMPLETE.require_returned_event(engine,foreign['id'])
    return counter


def pair_checkpoint(engine,event_id,pending_id):
    original=engine._passive_events.get(event_id)
    if original is None or KEY not in original:return False
    wait=original[KEY]['wait']
    if not wait or wait['event_id']!=pending_id:return False
    if wait['phase']=='before_damage':return True
    pending=engine._passive_events.get(pending_id)
    return bool(wait['phase']=='external' and pending is not None and _detect_dependency(engine,original,pending) is not None)


def counter_parent(engine,pending,completion_id):
    for original in engine._passive_events.values():
        if KEY not in original or original['completion_id']!=completion_id:continue
        row=checked(engine,original);wait=row['wait']
        if wait and wait['event_id']==pending['id']:return original
    return None


def _returned_counter(engine,row):
    if row['counter_event'] is None:return False
    child=engine._passive_events[row['counter_event']]
    completion=engine._move_completions[row['counter_completion']]
    if child['id'] not in completion.get('native_returns',{}):return False
    __import__('move_completion').require_returned_event(engine,child['id'],_recipient_only=True)
    return True


def parent_refresh_needed(engine,attacker,target,move,event_id,token):
    if side(engine,attacker,target,move)!='incoming':return
    original=parent(engine,engine._passive_events[event_id]);row=checked(engine,original,live=True)
    if not _returned_counter(engine,row):return
    receipt=engine._heavy_native_receipts.get(token)
    if receipt is None:return
    # Reissue only the still-live original producer after a completed native
    # counter. Never edit a token's old history/epoch or admit a caller assertion.
    if (receipt['attacker'] is not attacker or receipt['target'] is not target
            or receipt['move_id']!=move['id'] or receipt['round']!=engine.round_no
            or receipt['active_actor'] is not engine._active_turn_actor
            or receipt['move_uses']!=attacker.move_uses.get(move['id'],0)
            or receipt['history_length']>len(attacker._action_history)):
        raise ValueError('parent receipt lost its actual paid native producer')
    if (receipt['activation_epoch']!=engine._heavy_activation_sequence
            or receipt['history_length']!=len(attacker._action_history)):
        return True


def validate_parent_refresh(engine,result,attacker,target,move,event_id,token):
    if result!={'_gambit_parent_receipt_refresh':event_id}:
        raise ValueError('parent receipt refresh has another native issuer')
    if not parent_refresh_needed(engine,attacker,target,move,event_id,token):
        raise ValueError('parent receipt refresh lacks an actual returned counter')

def _resume_counter_boundary(engine,child,wait):
    """Resume the actual counter's paid accuracy or already-produced hit tail."""
    import passive_events as P
    pending=child if wait is None else engine._passive_events[wait['event_id']]
    if _root(engine,pending) is not child:
        raise ValueError('Gambit counter continuation has another native producer')
    if pending['phase']=='accuracy_boundary':
        if pending is not child:raise ValueError('Gambit counter accuracy must be its actual selected target')
        return P._deliver_accuracy(engine,child['id'])
    if pending['phase']!='producer_return_boundary':
        raise ValueError('Gambit counter has no supported actual native continuation')
    # A missed/avoided counter can already have produced its recipient result
    # while its completion listener still awaits GM input. Its damage did not
    # rendezvous with the parent, so finish this real tail before parent HP.
    frame=pending.get('continuation')
    own_return=frame is not None and frame.get('kind')=='recipient_return'
    routed=pending.get('defense_parent')==child['id'] and child['phase']=='accuracy_boundary'
    if not own_return and not routed:
        raise ValueError('Gambit counter listener lacks its actual native caller tail')
    previous=getattr(engine,'_event_use_scopes',None)
    source_frame=frame if own_return else child['continuation']
    engine._event_use_scopes=source_frame['scopes']
    try:
        P._deliver(engine,pending['id'])
        if own_return:result=P._resume_recipient_return(engine,pending)
        if routed:
            return P._deliver_accuracy(engine,child['id'])
        return result
    finally:
        if previous is None:vars(engine).pop('_event_use_scopes',None)
        else:engine._event_use_scopes=previous


def run_counter(engine,attacker,target,move,damage,context,before,actual_damage_type):
    import action_lifecycle as ACTION,passive_events as P
    active=engine._taskmaster_gambit;original=engine._passive_events[active['event_id']]
    row=checked(engine,original,live=True)
    if _returned_counter(engine,row):return None
    if row['counter_event'] is None and not counter_eligible(engine,original):
        row['cancel_reason']='counter_no_longer_eligible';_seal(row)
        active['counter_id']=None
        return None
    active['prepared']={'attacker':attacker,'target':target,'move':move,'damage':damage,
                        'context':context,'before':before,'actual_damage_type':actual_damage_type}
    try:
        if row['counter_event'] is None:
            active['phase']='counter_issuing'
            with ACTION.move_grant(engine,target,attacker,active['counter_id'],source=__import__('taskmaster').GAMBIT,kind='free') as grant:
                engine.use_move(target,attacker,active['counter_id'],count_use=True,free_action=True,
                                _action_grant=grant,**active['counter_options'])
        else:
            active['phase']='counter'
            child=engine._passive_events[row['counter_event']]
            with ACTION.resume_move(engine,child):
                result=_resume_counter_boundary(engine,child,row['wait'])
                __import__('move_activation').resume_after_event(engine,child,result)
        row=engine._passive_events[original['id']][KEY]
        if row['wait'] and row['wait']['phase']=='before_damage':row['wait']=None;_seal(row)
        current=getattr(engine,'_taskmaster_gambit',None)
        return current['incoming_receipt'] if current and current.get('applied') else None
    except P.PassiveEventPending as pending:
        current=engine._taskmaster_gambit
        row=engine._passive_events[original['id']][KEY]
        child=engine._passive_events[pending.event_id]
        phase='after_damage' if current.get('applied') else 'before_damage'
        if phase=='before_damage' and _root(engine,child)['id']!=row['counter_event']:
            phase='external'
        row['wait']={'event_id':pending.event_id,'phase':phase};_seal(row)
        if phase=='after_damage':
            engine._passive_pending=None
            return current['incoming_receipt']
        raise


def _native_cancelled(engine,event):
    completion=engine._move_completions.get(event['completion_id'],{})
    result=completion.get('results',{}).get(event['target'].entity_id)
    return bool(event.get('continuation_cancelled')=='actor_no_longer_eligible'
                and event['phase']=='producer_return_boundary'
                and event['status'] in ('applied','inapplicable')
                and 'continuation' not in event and result is not None
                and result.get('cancelled') is True and result.get('dealt')==0)


def _cancelled_wait(engine,original,row):
    wait=row['wait']
    if (wait and wait['phase']=='external' and row['cancel_reason']=='incoming_cancelled'
            and _native_cancelled(engine,original)):
        # Migrate the old issued wait only on actual resume, never on load.
        row['wait']=dict(wait,phase='parent_cancelled');_seal(row)
    return row['wait']


def _resume_cancelled_counter(engine,original):
    import passive_events as P,action_lifecycle as ACTION,move_activation as ACT
    row=checked(engine,original,live=True);wait=_cancelled_wait(engine,original,row)
    if not wait or wait['phase']!='parent_cancelled' or not _native_cancelled(engine,original):
        raise ValueError('actual cancelled parent counter remainder required')
    child=engine._passive_events[row['counter_event']]
    pending=engine._passive_events[wait['event_id']]
    foreign=_root(engine,pending) is not child
    if foreign and _detect_dependency(engine,original,pending) is None:
        raise ValueError('cancelled Gambit counter needs its actual native continuation')
    # The native counter keeps its payment and target checks, but a cancelled
    # incoming producer cannot rendezvous with or reapply counter damage.
    old=getattr(engine,'_taskmaster_gambit',None)
    engine._taskmaster_gambit=runtime(engine,original)
    saved_wait=dict(wait)
    row['wait']=None;_seal(row)
    try:
        with ACTION.resume_move(engine,child):
            if foreign:
                P.deliver(engine,pending['id'])
                if _detect_dependency(engine,original,pending,returned=True) is None:
                    raise ValueError('cancelled counter Detect has not actually returned')
                __import__('move_defense_reactions').deliver_boundary(engine,child)
                wait=None
            result=_resume_counter_boundary(engine,child,wait)
            ACT.resume_after_event(engine,child,result)
        row=checked(engine,original)
        completion=engine._move_completions[row['counter_completion']]
        if (completion['phase'] not in ('complete','interrupted') or not completion['sealed']
                or completion.get('activation_continuation')
                or not (_returned_counter(engine,row) or _native_cancelled(engine,child))):
            raise ValueError('cancelled parent counter has not returned its actual native result')
        return result
    except P.PassiveEventPending as pending_error:
        row=engine._passive_events[original['id']][KEY]
        row['wait']={'event_id':pending_error.event_id,'phase':'parent_cancelled'};_seal(row)
        raise
    except BaseException:
        # Heavy and other external owners retain their actual observed state.
        # Losing the dispatch wait must not mark that paid remainder returned.
        row=engine._passive_events[original['id']][KEY]
        row['wait']=saved_wait;_seal(row)
        raise
    finally:
        if old is None:vars(engine).pop('_taskmaster_gambit',None)
        else:engine._taskmaster_gambit=old


def _finish_cancelled_pair(engine,original,result):
    row=checked(engine,original)
    if row['cancel_reason']!='incoming_cancelled':return result
    completion=engine._move_completions[original['completion_id']]
    if (row['wait'] is not None or not _native_cancelled(engine,original)
            or completion.get('activation_continuation')
            or completion['phase'] not in ('complete','interrupted')):
        raise ValueError('cancelled Gambit parent has not returned its actual native tail')
    row['done']=True;_seal(row)
    return result


def _resume_cancelled_pair(engine,original):
    import action_lifecycle as ACTION,move_activation as ACT
    with ACTION.resolution(engine,original['actor'],original['move_id'],kind='move',_move_completion=original['completion_id']):
        _resume_cancelled_counter(engine,original)
        result=ACT.resume_after_event(engine,original,0)
        return _finish_cancelled_pair(engine,original,result)


def resume_pair_wait(engine,event):
    original=parent(engine,event)
    if original is None:return None
    row=checked(engine,original);wait=_cancelled_wait(engine,original,row)
    if not wait:return None
    if wait['phase']=='parent_cancelled':
        if wait['event_id']!=event['id']:return None
        return {'result':_resume_cancelled_pair(engine,original)}
    if wait['phase']=='external' and event['id']==row['counter_event']:
        pending=engine._passive_events[wait['event_id']]
        counter=_detect_dependency(engine,original,pending,returned=True)
        if counter is None:raise ValueError('Gambit foreign caller still lacks its actual completed Detect')
        # Close the already-paid Detect frame first. This restores its real
        # suspended owner (which can differ from the original attack actor).
        __import__('move_defense_reactions').deliver_boundary(engine,counter)
        original=engine._passive_events[original['id']]
        row=checked(engine,original,live=True)
        row['wait']={'event_id':counter['id'],'phase':'before_damage'};_seal(row)
        wait=row['wait'];event=engine._passive_events[counter['id']]
    if wait['event_id']!=event['id']:return None
    if wait['phase']=='external':
        raise ValueError('Gambit descendant wait needs an explicitly reviewed parent continuation')
    if wait['phase']!='before_damage':return None
    if event['phase'] not in ('accuracy_boundary','producer_return_boundary'):
        raise ValueError('Gambit counter requires its actual accuracy or recipient-return continuation')
    import passive_events as P,action_lifecycle as ACTION,move_activation as ACT
    with ACTION.resume_move(engine,original), restored_scope(engine,original):
        result=P._deliver_accuracy(engine,original['id'])
        row=engine._passive_events[original['id']][KEY]
        if row['wait'] and row['wait']['phase']=='before_damage':row['wait']=None;_seal(row)
        result=ACT.resume_after_event(engine,original,result)
        return {'result':_finish_cancelled_pair(engine,original,result)}



def cancel_parent(engine,event):
    if KEY not in event:return
    row=checked(engine,event)
    result=engine._move_completions[event['completion_id']]['results'].get(event['target'].entity_id)
    if not result or not result['cancelled']:
        raise ValueError('Gambit cancellation needs the native parent cancellation')
    row['cancel_reason']='incoming_cancelled'
    if row['counter_event'] is None:
        row['wait']=None;row['done']=True;_seal(row)
        return
    counter=engine._move_completions[row['counter_completion']]
    if counter['phase']=='complete':
        row['wait']=None;row['done']=True;_seal(row)
        return
    # The issued counter is a separate paid native attack. Resume that actual
    # continuation; its own actor/target guards still decide whether it lands.
    identity=row['wait']['event_id'] if row['wait'] else row['counter_event']
    row['wait']={'event_id':identity,'phase':'parent_cancelled'};_seal(row)
    _resume_cancelled_counter(engine,event)


def finish_parent(engine,event_id,dealt):
    event=engine._passive_events.get(event_id)
    if event is None or KEY not in event:return
    row=checked(engine,event);wait=row['wait']
    if wait and wait['phase']=='after_damage':
        import passive_events as P
        engine._passive_pending=wait['event_id']
        raise P.PassiveEventPending(wait['event_id'])
    if wait and wait['phase']=='before_damage' and engine._move_completions[row['counter_completion']]['phase']=='complete':
        row['wait']=None;wait=None
    if wait is None:
        row['done']=True;_seal(row)


def advance_wait(engine,origin_id,error):
    """Carry a real resumed counter's next native wait without replaying HP."""
    import passive_events as P
    if not isinstance(error,P.PassiveEventPending):return
    pending=engine._passive_events.get(error.event_id)
    origin=engine._passive_events.get(origin_id)
    if pending is None or origin is None or engine._passive_pending!=error.event_id:return
    for original in engine._passive_events.values():
        if KEY not in original:continue
        row=checked(engine,original);wait=row['wait']
        if not wait or wait['phase']!='after_damage':continue
        if wait['event_id']!=origin_id and _root(engine,origin)['id']!=row['counter_event']:continue
        row['wait']={'event_id':error.event_id,'phase':'after_damage'};_seal(row)


def resume_after_event(engine,event,result):
    import action_lifecycle as ACTION,move_activation as ACT,move_completion as COMPLETE
    for original in engine._passive_events.values():
        if KEY not in original:continue
        row=checked(engine,original);wait=_cancelled_wait(engine,original,row)
        if event['id']==original['id'] and row['cancel_reason']=='incoming_cancelled' and wait is None and not row['done']:
            return _finish_cancelled_pair(engine,original,result)
        if wait and wait['phase']=='parent_cancelled' and wait['event_id']==event['id']:
            return _resume_cancelled_pair(engine,original)
        if wait and wait['phase']=='external' and wait['event_id']==event['id']:
            counter=_detect_dependency(engine,original,event,returned=True)
            if counter is not None:return resume_pair_wait(engine,counter)['result']
        if not wait or wait['phase']!='after_damage':continue
        if wait['event_id']!=event['id'] and _root(engine,event)['id']!=row['counter_event']:continue
        child=engine._move_completions[row['counter_completion']]
        if not child['sealed'] or child['phase'] not in ('complete','interrupted'):continue
        if ACTION.pending_resolution_effects(engine,child):continue
        COMPLETE.require_returned_event(engine,row['counter_event'],_recipient_only=True)
        COMPLETE.require_returned_event(engine,original['id'],_recipient_only=True)
        dealt=engine._move_completions[original['completion_id']]['results'][original['target'].entity_id]['dealt']
        row['wait']=None;row['done']=True;_seal(row)
        with ACTION.resolution(engine,original['actor'],original['move_id'],kind='move',_move_completion=original['completion_id']):
            result=ACT.resume_after_event(engine,original,dealt)
        return result
    return result


def validate(engine,index):
    import coordinator as OBS
    for event in engine._passive_events.values():
        if KEY in event:checked(engine,event)
        if LINK in event:
            original=engine._passive_events.get(event[LINK])
            if original is None or KEY not in original or original[KEY]['counter_event']!=event['id']:
                raise ValueError('orphan Gambit counter continuation')
        cached=event.get(CACHE)
        if cached is not None:
            if cached.get('sha256')!=OBS._damage_seal(cached) or cached['event_id']!=event['id']:
                raise ValueError('Gambit saved calculation changed')
            original=engine._passive_events.get(cached['parent_event'])
            if original is None or original.get(KEY,{}).get('damage_event')!=event['id']:
                raise ValueError('Gambit saved calculation lost its parent')
            if cached['actor_id']!=event['actor'].entity_id or cached['target_id']!=event['target'].entity_id or cached['move_id']!=event['move_id']:
                raise ValueError('Gambit saved calculation participants changed')
            if not original[KEY]['done'] and original[KEY]['wait'] is not None:
                retained_precision(engine,event)
    return True
