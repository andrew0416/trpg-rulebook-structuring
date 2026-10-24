"""Partial common-action contracts from ch07:24,38,63,584-587,615.
Ordinary combat turns only. Priority variants and unspecified grants stay held.
Outside-encounter helpers are component execution, not certified turn authority.
"""
from contextlib import contextmanager
from action_metadata import ActionCost

@contextmanager
def resolution(engine,actor,source,*,kind,join=False,_breather_attempt=None,_move_completion=None,_combat_reaction=None):
    """Native producer scope, distinct from action cost and per-hit resolution.

    Only actual same-activation children join their parent. A nested reaction
    owns its own boundary. A failed producer never certifies a complete action.
    Receipts are issued lazily when a native consumer actually observes a fact.
    """
    stack=getattr(engine,'_native_action_stack',[])
    if join and stack:
        yield stack[-1]
        return
    if _breather_attempt is not None:
        import breather as BREATHER
        BREATHER.validate_continuation(engine,actor,source,kind,_breather_attempt)
    import confusion_attacks as CONFUSION
    resume=CONFUSION.resuming_action(engine,actor,source,kind)
    retained=None
    if _move_completion is not None:
        retained=move_frame(engine,engine._move_completions[_move_completion])
    elif _combat_reaction is not None:
        retained=__import__('combat_move_reactions').resume_frame(engine,_combat_reaction)
    if _move_completion is not None or _combat_reaction is not None:
        if retained is None or retained['actor'] is not actor or retained['source']!=source or kind!='move':
            raise ValueError('actual native Move action continuation required')
        retained.pop('deferred',None)
        resume=retained['id']
        if resume is not None:
            row=engine._native_action_resolutions[resume]
            if row['phase']!='interrupted':raise ValueError('native Move action is not awaiting its producer')
            row['phase']='resolving'
    ensure_resolutions_clear(engine,_breather_attempt=_breather_attempt)
    frame=retained if retained is not None else {'actor':actor,'source':source,'kind':kind,'id':resume,
           'before_effects':tuple(getattr(engine,'_effect_dispatch_receipts',{}))}
    if resume is not None:engine._native_action_resolutions[resume]['phase']='resolving'
    engine._native_action_stack=stack
    stack.append(frame)
    try:
        yield frame
    except BaseException:
        frame=engine._native_action_stack[-1]
        if frame['id'] is not None:engine._native_action_resolutions[frame['id']]['phase']='interrupted'
        raise
    else:
        frame=engine._native_action_stack[-1]
        if frame['id'] is not None:
            row=engine._native_action_resolutions[frame['id']]
            row['effects']=list(dict.fromkeys([*row['effects'],*[key for key in getattr(engine,'_effect_dispatch_receipts',{}) if key not in frame['before_effects']]]))
            row['phase']='interrupted' if frame.get('deferred') else 'producer_returned'
            if not frame.get('deferred'):finish_resolution(engine,row)
    finally:
        # Native state transactions may replace the staged stack, preserving IDs.
        current=engine._native_action_stack
        current.pop()
        if not current:del engine._native_action_stack


def move_frame(engine,completion):
    frame=completion.get('native_action_frame')
    if frame is None:return None
    if frame['actor'] is not completion['actor'] or frame['kind']!='move':
        raise ValueError('native Move action participant changed')
    if frame['id'] is not None:
        row=getattr(engine,'_native_action_resolutions',{}).get(frame['id'])
        if row is None or any(row[key]!=frame[key] for key in ('actor','source','kind')):
            raise ValueError('native Move action resolution identity changed')
    return frame


@contextmanager
def resume_move(engine,event,*,enabled=True):
    """Reopen the same enclosing action until all resumed targets have returned."""
    parent=engine._passive_events.get(event.get('defense_parent'),event)
    completion=getattr(engine,'_move_completions',{}).get(parent.get('completion_id'),{})
    frame=move_frame(engine,completion)
    if (not enabled or frame is None or not parent.get('continuation') or
            any(active is frame for active in getattr(engine,'_native_action_stack',()))):
        yield;return
    with resolution(engine,frame['actor'],frame['source'],kind='move',_move_completion=completion['id']):
        yield


def finish_resolution(engine,row):
    import confusion_attacks as CONFUSION
    if not CONFUSION.finish_action(engine,row):return
    import stamina as STAMINA
    return STAMINA.finish(engine,row)


def resolved_native(actor_parameter,source,kind):
    """Scope a known native producer; its actual attack point observes facts."""
    from functools import wraps
    from inspect import signature
    def decorate(fn):
        sig=signature(fn)
        @wraps(fn)
        def run(engine,*args,**kwargs):
            actor=sig.bind(engine,*args,**kwargs).arguments[actor_parameter]
            with resolution(engine,actor,source,kind=kind):return fn(engine,*args,**kwargs)
        return run
    return decorate

def resolved_move(fn):
    from functools import wraps
    from inspect import signature
    sig=signature(fn)
    @wraps(fn)
    def run(engine,*args,**kwargs):
        values=sig.bind(engine,*args,**kwargs).arguments
        participants=[values['attacker'],values.get('target',values.get('primary')),*values.get('everyone',())]
        import partial_entities as PARTIAL
        for participant in participants:
            PARTIAL.require_complete(participant,fn.__name__)
        depth=getattr(engine,'_native_move_resolution_depth',0)
        if not depth:
            ensure_resolutions_clear(engine)
        engine._native_move_resolution_depth=depth+1
        try:
            import stamina as STAMINA
            actor=values['attacker'];source=values['move_id']
            if not any(c is not None and STAMINA.interested(c) for c in participants) and not __import__('combat_move_reactions').interested(engine):
                return fn(engine,*args,**kwargs)
            stack=getattr(engine,'_native_action_stack',[])
            same=bool(stack and stack[-1]['kind']=='move' and stack[-1]['actor'] is actor
                      and (fn.__name__=='_finish_move_resolution' or
                           (fn.__name__=='use_move' and (values.get('_activation') is not None or
                            values.get('_field_activation') is not None or
                            any(g[0] is values.get('_action_grant') and g[5]=='same_move_activation' for g in engine._action_grants)))))
            with resolution(engine,actor,source,kind='move',join=same):
                return fn(engine,*args,**kwargs)
        finally:
            if depth:
                engine._native_move_resolution_depth=depth
            else:
                del engine._native_move_resolution_depth
    return run

def observe_resolution(engine,actor,source,fact):
    """Called by actual native observations, never by a declared GM hit flag."""
    stack=getattr(engine,'_native_action_stack',[])
    frame=stack[-1] if stack else None
    if frame is None or frame['id'] is None:
        number=getattr(engine,'_native_action_sequence',0)+1
        engine._native_action_sequence=number
        identity='native-action:'+str(number)
        if not hasattr(engine,'_native_action_resolutions'):engine._native_action_resolutions={}
        row={'id':identity,'actor':frame['actor'] if frame else actor,
             'source':frame['source'] if frame else None,'kind':frame['kind'] if frame else 'damage_component',
             'phase':'resolving' if frame else 'component_only','triggers':[],'effects':[]}
        engine._native_action_resolutions[identity]=row
        if frame is not None:frame['id']=identity
    else:row=engine._native_action_resolutions[frame['id']]
    trigger=next((t for t in row['triggers'] if t['actor'] is actor and t['source']==source),None)
    if trigger is None:
        trigger={'actor':actor,'source':source,'observations':[],'status':'pending'}
        row['triggers'].append(trigger)
    trigger['observations'].append(fact)
    return row

def pending_resolution_effects(engine,row):
    import effect_contracts as EC
    rows=getattr(engine,'_effect_dispatch_receipts',{})
    unfinished=('condition_unknown','awaiting_input','unsupported_execution','unresolved_source','execution_failed','deferred_suffix')
    def pending(token,ancestors):
        if token in ancestors:raise ValueError('cyclic native effect completion evidence')
        effect=rows[token];result=effect.get('result')
        if isinstance(result,EC.BatchResult):
            return any(pending(o.receipt,ancestors|{token}) if o.receipt is not None
                       else o.status in unfinished for o in result.outcomes)
        return effect.get('status') in (*unfinished,'dispatching')
    return any(pending(token,set()) for token in row['effects'])


def _turn_end_members(engine,meta):
    """Follow the existing actual suffix graph, including later child receipts."""
    import effect_contracts as EC
    rows=getattr(engine,'_effect_dispatch_receipts',{})
    seen=set()
    def visit(token,ancestors):
        if type(token) is not object or token not in rows:
            raise ValueError('turn-end producer lost an actual effect receipt')
        if token in ancestors:raise ValueError('cyclic turn-end effect graph')
        if token in seen:return
        row=rows[token];ancestors=ancestors|{token}
        continuation=row.get('continuation')
        if continuation is not None:
            if type(continuation) is not object or continuation not in rows or rows[continuation].get('blocked_on') is not token:
                raise ValueError('turn-end producer continuation lost its actual predecessor')
            visit(continuation,ancestors)
        child=row.get('result')
        if isinstance(child,EC.BatchResult):
            if (type(child.outcomes) is not tuple or any(type(o) is not EC.Outcome for o in child.outcomes)
                    or (hasattr(child,'engine') and child.engine is not engine)):
                raise ValueError('turn-end producer lost its actual child batch')
            receipts=[o.receipt for o in child.outcomes if o.receipt is not None]
            if any(type(t) is not object for t in receipts):raise ValueError('actual opaque turn-end child receipt required')
            if len(set(receipts))!=len(receipts):raise ValueError('duplicate turn-end child receipt')
            for outcome in child.outcomes:
                if outcome.receipt is None:
                    if outcome.status not in ('completed','condition_false','deferred_consumer'):
                        raise ValueError('unfinished turn-end child lacks an actual receipt')
                    continue
                visit(outcome.receipt,ancestors)
                actual=rows[outcome.receipt]
                if outcome.source_id!=actual['source_id'] or outcome.occurrence!=actual['occurrence']:
                    raise ValueError('turn-end child source or occurrence changed')
        seen.add(token)
    for token in meta['effects']:visit(token,set())
    return seen


def validate_turn_end_closures(engine,*,ready=False):
    """Validate optional producer metadata in the existing effect receipt owner."""
    import effect_contracts as EC
    import root_resolution as ROOT
    import world_entities as WORLD
    rows=getattr(engine,'_effect_dispatch_receipts',{})
    owners={token:row for token,row in rows.items() if 'turn_end_close' in row}
    for row in rows.values():
        if 'turn_end_owner' in row and (type(row['turn_end_owner']) is not object or row['turn_end_owner'] not in owners):
            raise ValueError('turn-end producer close phase is missing')
    for token,root in owners.items():
        meta=root['turn_end_close']
        fields={'actor','boundary','effects','profiles','status','expected_closure','closed_by'}
        if (type(meta) is not dict or set(meta)!=fields or root.get('turn_end_owner') is not token
                or type(meta['effects']) is not tuple or not meta['effects']
                or any(type(key) is not object for key in meta['effects'])
                or len(set(meta['effects']))!=len(meta['effects']) or meta['effects'][0] is not token
                or type(meta['profiles']) is not dict or meta['status'] not in ('pending','closed')
                or type(meta['boundary']) is not tuple or len(meta['boundary'])!=6):
            raise ValueError('invalid turn-end producer close phase')
        actor=meta['actor'];initial=meta['effects'];boundary=meta['boundary']
        actual={key for key,row in rows.items() if row.get('turn_end_owner') is token}
        if (set(initial)!=actual or any(key not in rows for key in initial)
                or actor is not root['actor']):
            raise ValueError('turn-end producer actor or receipt membership changed')
        members=_turn_end_members(engine,meta)
        sources={rows[key]['source_id'] for key in members}
        if set(meta['profiles'])!=sources or any(type(v) is not str for v in meta['profiles'].values()):
            raise ValueError('turn-end producer source profiles changed')
        if type(boundary[2]) is not bool or (boundary[2] and boundary[3] is not actor):
            raise ValueError('turn-end producer original actor boundary changed')
        for key in members:
            row=rows[key]
            WORLD.require_actors(engine,row['actor'],row['target'])
            if (row.get('receipt') is not key or row.get('fingerprint')!=ROOT.fingerprint(row.get('effect'))
                    or row.get('source_id') not in meta['profiles']):
                raise ValueError('turn-end producer actual effect identity or payload changed')
            if row.get('status')=='condition_unknown' and 'condition_request' not in row:
                child=row.get('result')
                if row['effect'].get('type')!='alternate_effect' or not isinstance(child,EC.BatchResult):
                    raise ValueError('actual suspended condition request required')
                direct=tuple(o.receipt for o in child.outcomes if o.receipt is not None)
                descendants=_turn_end_members(engine,{'effects':direct})
                if (not direct or not any('condition_request' in rows[t] for t in descendants)
                        or any(rows[t]['source_id']!=row['source_id'] or rows[t]['actor'] is not row['actor']
                               or rows[t]['target'] is not row['target'] for t in direct)):
                    raise ValueError('unknown turn-end branch lacks its actual conditional child')
            # A branch can inherit its child's unknown status without issuing
            # a question itself. The actual batch edges above bind that child;
            # only direct questions require their own suspended request.
            if ('condition_request' in row or
                    (row.get('status')=='condition_unknown' and not isinstance(row.get('result'),EC.BatchResult))):
                request=EC.validate_condition_request(engine,row,completed='condition_reply' in row)
                if request['profile']!=meta['profiles'][row['source_id']]:
                    raise ValueError('turn-end producer condition source profile changed')
                original=request['boundary']
            else:original=row.get('boundary')
            if original is not None:
                # A native child can have its own actor/target lifetime stamps.
                # It shares this producer's world boundary, not its owner body.
                same_owner=row['actor'] is actor and row['target'] is actor
                if (type(original) is not tuple or len(original)!=6 or original[:4]!=boundary[:4]
                        or (same_owner and original!=boundary)
                        or (meta['status']=='pending' and original!=EC.boundary(engine,row['actor'],row['target']))):
                    raise ValueError('turn-end producer original effect boundary changed')
            if ('blocked_on' in row and ROOT.fingerprint({'type':'_deferred_batch','effects':row.get('effects')})!=row['fingerprint']):
                raise ValueError('turn-end producer deferred effect payload changed')
        expected=meta['expected_closure']
        if (boundary[2] and (type(expected) is not int or expected<1)) or (not boundary[2] and expected is not None):
            raise ValueError('turn-end producer native closure sequence changed')
        pending=pending_resolution_effects(engine,meta)
        if meta['status']=='pending':
            if meta['closed_by'] is not None or boundary!=EC.boundary(engine,actor,actor):
                raise ValueError('pending turn-end producer boundary changed')
            if not pending and not ready and getattr(engine,'_effect_resuming_receipt',None) not in _turn_end_members(engine,meta):
                raise ValueError('turn-end producer pending phase lacks an unfinished effect')
            for source,profile in meta['profiles'].items():
                if EC.source_profile(engine,source)!=profile:raise ValueError('turn-end producer source changed')
        else:
            if pending:raise ValueError('closed turn-end producer still has unfinished effects')
            if expected is not None:
                closures=getattr(engine,'_turn_closures',[])
                if (type(meta['closed_by']) is not dict or expected>len(closures) or meta['closed_by'] is not closures[expected-1]
                        or meta['closed_by'].get('actor') is not actor
                        or meta['closed_by'].get('round')!=boundary[0]
                        or meta['closed_by'].get('sequence')!=expected):
                    raise ValueError('closed turn-end producer lacks its actual native closure')
            elif meta['closed_by'] is not None:raise ValueError('outside-encounter turn-end has no native turn closure')
    return owners


def defer_turn_end(engine,actor,before):
    """Keep only the native close phase; the event and native ticks already ran."""
    import effect_contracts as EC
    rows=getattr(engine,'_effect_dispatch_receipts',{})
    effects=tuple(token for token in rows if token not in before)
    if not pending_resolution_effects(engine,{'effects':effects}):return None
    anchor=effects[0]
    meta={'actor':actor,'boundary':EC.boundary(engine,actor,actor),'effects':effects,
          'profiles':{rows[token]['source_id']:EC.source_profile(engine,rows[token]['source_id']) for token in effects},
          'status':'pending','expected_closure':len(engine._turn_closures)+1 if engine.encounter_active else None,
          'closed_by':None}
    for token in effects:rows[token]['turn_end_owner']=anchor
    rows[anchor]['turn_end_close']=meta
    validate_turn_end_closures(engine)
    members=_turn_end_members(engine,meta)
    receipt=next((token for token,row in rows.items() if token in members
                  and row['status']=='condition_unknown' and 'condition_request' in row
                  and 'condition_reply' not in row),anchor)
    return {'status':'awaiting_input','phase':'turn_end','receipt':receipt,'producer_receipt':anchor}


def refresh_turn_end(engine):
    """The existing continuation transaction owns this final native phase too."""
    for root in validate_turn_end_closures(engine,ready=True).values():
        meta=root['turn_end_close']
        if meta['status']!='pending' or pending_resolution_effects(engine,meta):continue
        engine._close_end_of_turn(meta['actor'])
        meta['closed_by']=None if meta['expected_closure'] is None else engine._turn_closures[meta['expected_closure']-1]
        meta['status']='closed'
    validate_turn_end_closures(engine)


def retain_turn_end_children(engine,preceding_receipt,issued):
    """Bind newly emitted native children through their actual suffix graph.

    Initial receipt membership stays fixed. Only sources of newly issued,
    reachable children acquire a profile, before the regular read-only owner
    validation checks every child's original actor, target and boundary.
    """
    import effect_contracts as EC
    rows=getattr(engine,'_effect_dispatch_receipts',{})
    for root in tuple(rows.values()):
        meta=root.get('turn_end_close')
        if meta is None or meta['status']!='pending':continue
        members=_turn_end_members(engine,meta)
        if preceding_receipt not in members:continue
        for token in members & issued:
            source=rows[token]['source_id']
            if source not in meta['profiles']:meta['profiles'][source]=EC.source_profile(engine,source)


def ensure_turn_end_clear(engine):
    for root in validate_turn_end_closures(engine).values():
        meta=root['turn_end_close']
        if meta['status']!='pending':continue
        if getattr(engine,'_effect_resuming_receipt',None) in _turn_end_members(engine,meta):continue
        raise ValueError('unfinished turn-end producer must finish its actual effects before a new action or boundary')

def post_action_condition(engine,context,source):
    """A completed native trigger is effect authority, not a fabricated hit."""
    import root_resolution as ROOT
    row=getattr(engine,'_native_action_resolutions',{}).get(context.get('native_action'))
    if row is None or row['phase']!='producer_returned' or pending_resolution_effects(engine,row):
        return ROOT.Predicate(ROOT.Truth.UNKNOWN,'actual completed native action and effects')
    owner=context.get('attacker')
    if owner is not context.get('target') or not any(t['actor'] is owner and t['source']==source and t['status']!='completed' for t in row['triggers']):
        return ROOT.Predicate(ROOT.Truth.UNKNOWN,'actual source-owned post-action trigger')
    return ROOT.TRUE

def ensure_resolutions_clear(engine,*,_breather_attempt=None):
    ensure_turn_end_clear(engine)
    import dynamic_chain_moves as CHAIN
    CHAIN.ensure_clear(engine)
    import confusion_attacks as CONFUSION
    CONFUSION.ensure_clear(engine)
    import breather as BREATHER
    BREATHER.ensure_clear(engine,resume=_breather_attempt)
    import class_actor_state_reactions as CLASS_REACTIONS
    CLASS_REACTIONS.ensure_clear(engine)
    import class_actor_state_actions as CLASS_STATE_ACTIONS
    CLASS_STATE_ACTIONS.ensure_clear(engine)
    for row in getattr(engine,'_native_action_resolutions',{}).values():
        if row['phase']=='resolving':continue
        if row['id'] in (getattr(engine,'_confusion_resuming_action',None),getattr(engine,'_confusion_applying',None)):continue
        if any(t['status']!='completed' for t in row['triggers']):
            raise ValueError('unfinished post-action Stamina/Confusion requires its actual action completion, effects and skill choice')

def triggered_free_action(engine,actor,source):
    """Record a source-proved triggered Free Action, including off-turn use."""
    import world_entities as WORLD
    WORLD.require_actors(engine,actor)
    import heavy_injury_adapter as HEAVY
    HEAVY.ensure_clear(engine)
    import turn as TURN
    if not TURN.can_act(engine,actor) or not status_permission(engine,actor,'free',new_action=True):
        raise ValueError('triggered Free Action unavailable')
    record_action(engine,actor,'free')
    engine.log('  '+actor.name+': 발동조건 충족, 자유 행동 '+source,source)

def begin_turn(engine, actor, *, initiative_count=None):
    import party_actions as PARTY_ACTIONS
    import swarm_transitions as SWARM
    swarm_slot = SWARM.continuation_pending(engine,actor)
    if not swarm_slot:PARTY_ACTIONS.require_turn(engine,actor)
    import initiative_interrupts as INTERRUPTS
    import initiative_schedule as SCHEDULE
    SCHEDULE.preflight_turn(engine,actor)
    borrowed = INTERRUPTS.is_borrow_start(engine,actor)
    boss_slot = False
    if borrowed:
        INTERRUPTS.borrow_started(engine,actor)
    elif engine.encounter_active:
        if engine.round_start_seconds is None:
            raise ValueError("ordinary turn requires an open round")
        if engine._active_turn_actor is not None:
            raise ValueError("an ordinary turn is already active")
        import boss_transitions as BOSS
        boss_slot = BOSS.begin_action_lifecycle(engine,actor,initiative_count)
        if engine._ordinary_turn_rounds.get(actor) == engine.round_no and not (boss_slot or swarm_slot):
            raise ValueError("ordinary turn already taken this round")
        engine._active_turn_actor = actor
        engine._ordinary_turn_rounds[actor] = engine.round_no
    if not borrowed:
        SCHEDULE.turn_started(engine,actor)
        if not swarm_slot:PARTY_ACTIONS.record_turn(engine,actor)
    if swarm_slot:
        SWARM.start_turn(engine,actor,initiative_count)
        actor._turn_start_decisions_pending = False
        return
    actor._turn_start_decisions_pending = True
    actor.took_standard = False
    actor._turn_action_limit = None
    actor._restricted_action_taken = False
    actor._action_history = []
    import action_resources as RESOURCES
    RESOURCES.begin_turn_lock(engine,actor)
    if not borrowed:
        import stage_change_history as STAGE_HISTORY
        STAGE_HISTORY.begin_turn(engine, actor)

def check_end(engine, actor, *, continuation=False):
    ensure_resolutions_clear(engine)
    import mapless_space as MAPLESS
    MAPLESS.ensure_clear(engine,actor)
    import relative_movement as RELATIVE
    RELATIVE.ensure_clear(actor)
    import initiative_interrupts as INTERRUPTS
    INTERRUPTS.preflight_native_end(engine,actor)
    if engine.encounter_active and engine._active_turn_actor is not actor:
        raise ValueError("actor does not own an open ordinary turn")
    if continuation:
        import maneuver_grants as GRANTS
        GRANTS.ensure_clear(engine)
        import effect_contracts as EFFECTS
        EFFECTS.ensure_clear(engine)
        return
    import maneuver_grants as GRANTS
    GRANTS.check_end(engine, actor)
    import effect_contracts as EFFECTS
    EFFECTS.ensure_clear(engine)
    import capability_actions as CAPABILITIES
    CAPABILITIES.end_turn(engine,actor)
    import movement_actions as MOVEMENT
    MOVEMENT.finish_turn(engine,actor)

def close_swarm_window(engine, actor):
    """Yield initiative without closing the same ordinary turn's lifetimes."""
    import swarm_transitions as SWARM
    if not SWARM.continuation_pending(engine,actor):
        raise ValueError('actual pending swarm action required')
    import action_resources as RESOURCES
    RESOURCES.close_turn_lock(engine,actor)
    import initiative_schedule as SCHEDULE
    SCHEDULE.turn_closed(engine,actor,continuation=True)
    engine._active_turn_actor = None


def close_turn(engine, actor):
    import swarm_transitions as SWARM
    SWARM.finish_turn(actor)
    import action_resources as RESOURCES
    RESOURCES.close_turn_lock(engine,actor)
    import maneuver_grants as GRANTS
    GRANTS.close_turn(engine, actor)
    import initiative_interrupts as INTERRUPTS
    if INTERRUPTS.borrow_closed(engine,actor):
        return
    import initiative_schedule as SCHEDULE
    SCHEDULE.turn_closed(engine,actor)
    if engine.encounter_active:
        import boss_transitions as BOSS
        BOSS.close_action_lifecycle(engine,actor)
        engine._active_turn_actor = None
        engine._turn_closures.append(dict(actor=actor, round=engine.round_no, sequence=len(engine._turn_closures)+1))
    import stage_change_history as STAGE_HISTORY
    STAGE_HISTORY.end_turn(engine, actor)

def ordinary_permission(engine, actor):
    ensure_resolutions_clear(engine)
    import mapless_space as MAPLESS
    MAPLESS.ensure_clear(engine,actor)
    import relative_movement as RELATIVE
    RELATIVE.ensure_clear(actor,engine=engine)
    import initiative_interrupts as INTERRUPTS
    if not INTERRUPTS.permission(engine,actor):
        return False
    import effect_contracts as EFFECTS
    EFFECTS.ensure_clear(engine)
    import maneuver_grants as GRANTS
    GRANTS.ensure_clear(engine)
    if not engine.encounter_active:
        return True
    import action_resources as RESOURCES
    if RESOURCES.action_locked(actor):return False
    state=getattr(engine,INTERRUPTS.KEY,None)
    overflow=bool(state and any(frame['status']=='open' and frame['mode']=='duelist_interrupt'
        and state['windows'][frame['window_id']]['trigger']['kind']=='duelist_overflow'
        for frame in state['frames']))
    if (engine.round_start_seconds is None and not overflow) or engine._active_turn_actor is not actor or actor.budget is None:
        engine.log(f"    {actor.name}: 열린 본인 턴과 행동 예산이 필요 → 행동 보류", "common/action-lifecycle")
        return False
    return True

def self_cures_sleep(actor, target, effects):
    # Supported unconditional cure forms only. A conditional/nested effect is
    # not silently promoted to a permission; its entailment still needs review.
    for effect in effects:
        if not isinstance(effect, dict) or effect.get("type") not in ("cure_status", "cure_all_status"):
            continue
        supported = {"type", "status", "target"}
        if any(k not in supported and not k.startswith("_") for k in effect):
            continue
        selector = effect.get("target", "target")
        if selector not in ("self", "self_and_allies", "target"):
            continue
        if selector == "target" and target is not actor:
            continue
        if effect["type"] == "cure_all_status":
            return True
        statuses = effect.get("status", [])
        statuses = [statuses] if isinstance(statuses, str) else statuses
        # Only exact executable status names. Unsupported aliases/list members
        # make the cure handler hold, so they cannot establish this exception.
        if isinstance(statuses, list) and statuses and all(s in ("잠듦", "all") for s in statuses):
            return True
    return False

def status_permission(engine, actor, kind, *, sleep_cure=False, new_action=True, _standing_up=False, _condition_recovery=None):
    import action_resources as RESOURCES
    if new_action and RESOURCES.action_locked(actor):return False
    if type(_standing_up) is not bool or (_standing_up and (kind!='shift' or '넘어짐' not in actor.conditions)):
        raise ValueError('standing up requires the actual Tripped Shift action')
    if new_action and '넘어짐' in actor.conditions and not _standing_up:
        engine.log(f'    {actor.name}: 넘어짐 상태에서는 먼저 이동 행동으로 일어나야 함', 'condition/넘어짐')
        return False
    if type(kind) is ActionCost:
        limit = getattr(actor, "_turn_action_limit", None)
        if new_action and limit and len(set(kind.components).intersection(limit.get("choose_one_of", []))) > 1:
            engine.log(f"    {actor.name}: 마비 실패 후 기본·이동을 함께 사용할 수 없음", "condition/마비")
            return False
        return all(status_permission(engine, actor, component, sleep_cure=sleep_cure,
                                     new_action=new_action) for component in kind.components)
    import capability_actions as CAPABILITIES
    if not CAPABILITIES.action_permission(engine,actor,kind):return False
    if getattr(actor, "_turn_start_decisions_pending", False):
        engine.log(f"    {actor.name}: 턴 시작 상태 판정과 발동 순서가 아직 미결 → 능동 행동 보류", "common/action-lifecycle")
        return False
    import condition_recovery as RECOVERY
    import swarm_transitions as SWARM
    replaced = SWARM.incapacitation_replaced(actor,engine=engine)
    if "얼음" in actor.conditions and not replaced and not RECOVERY.permits_action(engine,actor,kind,_condition_recovery):
        engine.log(f"    {actor.name}: 얼음 상태 행동 불가", "condition/얼음")
        return False
    if "잠듦" in actor.conditions and not replaced and not (kind in ("free", "swift") and sleep_cure):
        engine.log(f"    {actor.name}: 잠듦 — 수면을 치료하는 자유·신속 행동만 허용", "condition/잠듦")
        return False
    limit = getattr(actor, "_turn_action_limit", None)
    if limit and new_action:
        choices = limit.get("choose_one_of", [])
        if kind not in choices and kind not in ("swift", "free"):
            engine.log(f"    {actor.name}: 마비 실패 후 기본·이동을 모두 쓰는 행동 불가", "condition/마비")
            return False
        if kind in choices and getattr(actor, "_restricted_action_taken", False):
            engine.log(f"    {actor.name}: 마비로 허용된 기본·이동 중 하나를 이미 사용", "condition/마비")
            return False
    return True

def record_action(engine, actor, kind):
    import initiative_interrupts as INTERRUPTS
    INTERRUPTS.require_recorded_action(engine,actor,kind)
    import csv_item_physical_contracts as CSV_ITEMS
    CSV_ITEMS.expire_immediate_reactions(engine)
    history = getattr(actor, "_action_history", None)
    if history is None:
        actor._action_history = history = []
    history.append({"kind": "compound", "components": list(kind.components)} if type(kind) is ActionCost else kind)
    # Declared type, not the token used to fund it. Full/downgrade consequence
    # interpretation remains unresolved and is not counted as proved Standard.
    if kind == "standard" or (type(kind) is ActionCost and "standard" in kind.components):
        actor.took_standard = True
        actor._standard_action_round = engine.round_no
    limit = getattr(actor, "_turn_action_limit", None)
    components = kind.components if type(kind) is ActionCost else (kind,)
    if limit and set(components).intersection(limit.get("choose_one_of", [])):
        actor._restricted_action_taken = True

def unable_standard(actor, *, engine=None):
    # Current unconditional status restriction is enough for this local branch.
    # Voluntary inaction, a successful paralysis save and modern Flinch are not.
    import swarm_transitions as SWARM
    if actor.conditions & {"잠듦", "얼음"} and not SWARM.incapacitation_replaced(actor,engine=engine):return True
    # A failed modern Paralysis save still permits choosing Standard. Only an
    # actual Shift selection makes Standard unavailable; voluntary waiting does not.
    return bool(getattr(actor,'_turn_action_limit',None) and
        getattr(actor,'_restricted_action_taken',False) and
        any(entry == 'shift' or (type(entry) is dict and entry.get('kind') == 'compound' and
            'shift' in entry.get('components', [])) for entry in getattr(actor,'_action_history',[])) and
        not actor.took_standard)

def already_acted_evidence(ctx):
    """Positive common evidence; other meanings of 'acted' remain unresolved."""
    engine = ctx.get("engine")
    if engine is not None and getattr(ctx["target"], "_standard_action_round", None) == engine.round_no:
        return True
    return None

@contextmanager
def move_grant(engine, actor, target, move_id, *, source, kind=None):
    """Internal scoped, one-use authorization; callers must prove its trigger.
    This is not a general GM boolean override. Only the two reviewed producers
    below (AoO and already-activated multi-target continuation) use this seam.
    """
    ace=__import__('type_ace').extra_authority(engine,actor,target,move_id,source)
    martial=__import__('martial_artist').move_authority(engine,actor,target,move_id,source)
    ace=ace or martial
    if not ace and source not in ("maneuver/기회-공격", "same_move_activation", "feat/치명적인-장기말", "move/원한", "move/버티기", "move/버티기-홈브류"):
        raise ValueError("unreviewed move grant producer")
    expected = "free" if ace or source in ("maneuver/기회-공격","feat/치명적인-장기말","move/원한","move/버티기","move/버티기-홈브류") else None
    if kind != expected or (source == "maneuver/기회-공격" and move_id != "struggle"):
        raise ValueError("move grant cannot broaden its source action or move scope")
    if source=='feat/치명적인-장기말':
        import taskmaster as TASK
        if TASK.gambit_side(engine,actor,target,{'id':move_id})!='counter':raise ValueError('actual Deadly Gambit paired counter required')
    if source in __import__('endure').SOURCES:
        __import__('endure').authority(engine,actor)
        if actor is not target or move_id!=source:raise ValueError('Endure grant is only its actual Self reaction')
    if source=='move/원한':
        import spite as SPITE
        frame=getattr(engine,'_spite_trigger',None)
        if move_id!=source or frame is None or frame[0] is not actor or SPITE.trigger(engine,actor,frame[1])[1]['actor'] is not target:raise ValueError('actual Spite triggering Move and attacker required')
    token = object()
    entry = (token, actor, target, move_id, kind, source)
    engine._action_grants.append(entry)
    try:
        yield token
    finally:
        engine._action_grants[:] = [g for g in engine._action_grants if g[0] is not token]

def consume_move_grant(engine, token, actor, target, move_id, *, count_use=None, free_action=None):
    for index, entry in enumerate(engine._action_grants):
        if entry[0] is token and entry[1] is actor and entry[2] is target and entry[3] == move_id:
            ace=__import__('type_ace').extra_authority(engine,actor,target,move_id,entry[5])
            martial=__import__('martial_artist').move_authority(engine,actor,target,move_id,entry[5])
            ace=ace or martial
            if not ace and entry[5] not in ("maneuver/기회-공격", "same_move_activation", "feat/치명적인-장기말", "move/원한", "move/버티기", "move/버티기-홈브류"):
                raise ValueError("a maneuver child token cannot authorize a Move")
            expected_count=entry[5] in ('feat/치명적인-장기말','move/원한','move/버티기','move/버티기-홈브류')
            if martial:expected_count=True
            elif ace:expected_count=not __import__('type_ace').scope(engine,actor,{'id':move_id}).get('ignore_frequency',False)
            if entry[5] in __import__('endure').SOURCES:__import__('endure').authority(engine,actor)
            if entry[5]=='move/원한':
                import spite as SPITE
                frame=getattr(engine,'_spite_trigger',None)
                if frame is None or frame[0] is not actor:raise ValueError('Spite Free Action needs its authenticated trigger')
                SPITE.trigger(engine,actor,frame[1])
            if count_use is not None and (count_use is not expected_count or free_action is not (entry[5] != "same_move_activation")):
                raise ValueError("move continuation cannot change cost/frequency exemption scope")
            engine._action_grants.pop(index)
            return True, entry[4]
    return False, None


@contextmanager
def maneuver_grant(engine, actor, target, receipt):
    """Internal scoped authority derived only from an actual effect child receipt."""
    import maneuver_grants as GRANTS
    permission = GRANTS.authority(engine, actor, target, receipt)
    token = object()
    entry = (token, actor, target, permission['maneuver'], permission, 'native_maneuver_child')
    engine._action_grants.append(entry)
    try:
        yield token
    finally:
        engine._action_grants[:] = [g for g in engine._action_grants if g[0] is not token]

def maneuver_authority(engine, token, actor, target, maneuver):
    if token is None:
        return dict(action_cost='standard', accuracy='ordinary', opposed='required', success='check')
    for entry in engine._action_grants:
        if entry[0] is token and entry[1] is actor and entry[2] is target and entry[3] == maneuver and entry[5] == 'native_maneuver_child':
            return dict(entry[4])
    raise ValueError('actual live source-bound maneuver token required')


def continued_maneuver(source):
    from functools import wraps
    def decorate(fn):
        @wraps(fn)
        def call(engine,*args,**kwargs):
            import skill_maneuver_actions as SM
            return SM.resume_entry('actor',source)(fn)(engine,*args,**kwargs)
        return call
    return decorate



