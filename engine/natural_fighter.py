"""Natural Fighter (ch04:2146-2154): bounded native Move adapter.

All nine mapped routes use native Move owners; urban requires a real projectile.
Astonish's redirected low-roll awareness still needs its own native continuation.
Registered native waits retain their payment and one-activation permission.
"""
import action_points as AP
import contest_features as OWN
import frequency as F
import state_grants as G
import survivalist_class as SC
import survivalist_features as V
import world_entities as W

MOVES = {
    'grassland': 'move/목화포자', 'forest': 'move/풀피리',
    'wetland': 'move/진흙뿌리기', 'ocean': 'move/아쿠아링',
    'tundra': 'move/흑안개', 'mountain': 'move/떨어뜨리기',
    'cave': 'move/놀래키기', 'urban': 'move/내던지기',
    'desert': 'move/모래뿌리기',
}

SELF_ANCHORS = {'grassland', 'ocean', 'tundra'}


def activate(engine, trainer, *, subject, terrain_name, target=None, set_damage=False, fling=None):
    """Pay trainer AP once; subject uses the mapped Move's native Standard."""
    if type(set_damage) is not bool:
        raise ValueError('boolean Set Damage declaration required')
    terrain = V.terrain(terrain_name)
    W.require_actors(engine, trainer, subject)
    SC._require(engine, trainer, SC.NATURAL)
    if SC.acquired(trainer, SC.NATURAL) is None:
        raise ValueError('actual acquired Natural Fighter receipt required')
    if subject is not trainer:
        OWN.owner(trainer, subject)
    if not engine.encounter_active or getattr(engine, '_active_turn_actor', None) is not subject:
        raise ValueError('Natural Fighter requires the subject actual encounter turn')
    if not subject.on_field or subject.fainted or subject.captured:
        raise ValueError('available on-field Natural Fighter subject required')
    environment = SC.effective_environment(engine, subject)
    if environment is None or terrain not in environment['terrains']:
        raise ValueError('Natural Fighter requires the subject observed current terrain')
    if terrain == 'urban':
        if (type(fling) is not dict or not isinstance(fling.get('instance_id'), str) or not fling['instance_id']
                or set(fling) - {'instance_id', 'edition', 'capture', 'capture_options', 'consumer_options'}):
            raise ValueError('urban Natural Fighter requires an explicit actual Fling projectile choice')
    elif fling is not None:
        raise ValueError('Fling projectile choices require the urban Natural Fighter route')
    if terrain in SELF_ANCHORS:
        if target is not None and target is not subject:
            raise ValueError('this Natural Fighter Move requires its user anchor')
        target = subject
    elif target is None:
        raise ValueError('actual Natural Fighter Move target required')
    W.require_actors(engine, target)
    mid = MOVES[terrain]
    if AP.available(trainer) < 1:
        raise ValueError('Natural Fighter requires 1 available trainer AP')
    if getattr(subject, 'budget', {}).get('standard', 0) < 1:
        raise ValueError('Natural Fighter requires an available Standard Action')

    pending = []

    def apply(staged, owner, actor, recipient):
        if current(actor) is not None:
            raise ValueError('finish the existing Natural Fighter activation')
        fling_choice = None
        if terrain == 'urban':
            fling_choice = __import__('fling_move').declare(staged, actor, recipient, **fling)
        uses = actor.spec.setdefault(KEY, {})
        source = SC.NATURAL + ':activation:' + actor.entity_id + ':' + str(len(uses) + 1)
        G.grant_moves(actor, [mid], source, 'effect', owner_id=owner.entity_id,
                      rule_id=SC.NATURAL, mode='permission')
        allowed, reason = F.move_allowed(staged, actor, mid)
        if not allowed:
            raise ValueError(reason)
        from action_point_account import ActionPointAccount
        payment = ActionPointAccount(owner).charge(1, retain_receipt=True)
        record = dict(id=source, owner_id=owner.entity_id, subject_id=actor.entity_id,
                      terrain=terrain, move_id=mid, payment=payment,
                      before_uses=actor.move_uses.get(mid, 0), phase='starting',
                      entered=False, frame=None, completion_id=None, heavy_event=None, termination=None)
        if fling_choice is not None:record['fling_choice'] = fling_choice
        record['cost_proof'] = _proof(record)
        uses[source] = record
        staged._natural_fighter_launch = source
        result = None
        try:
            try:
                result = staged.use_move_on(actor, recipient, mid, staged.everyone,
                                            set_damage=set_damage)
            except Exception as error:
                if not G.record_native_pending(staged, error, pending):
                    raise
                import heavy_injury_adapter as HEAVY
                if type(error) is HEAVY.HeavyPending:
                    # Heavy's existing packet explicitly has no executable suffix.
                    record['heavy_event'] = error.event_id
                    record['cost_proof'] = _proof(record)
                if record['phase'] not in TERMINAL:
                    record['phase'] = 'waiting'
        finally:
            del staged._natural_fighter_launch
        if not pending and record['phase'] not in TERMINAL:
            import action_lifecycle as ACTION
            completion = getattr(staged, '_move_completions', {}).get(record['completion_id'])
            if completion is None or not ACTION.pending_resolution_effects(staged, completion):
                raise ValueError('Natural Fighter requires an actual native activation')
            record['phase'] = 'waiting'
        return {'source': SC.NATURAL, 'terrain': terrain, 'move_id': mid,
                'subject_id': actor.entity_id, 'activation_id': source,
                'completion_id': record['completion_id'], 'status': record['phase'], 'result': result}

    result = G.transition(engine, trainer, apply, participants=(subject, target),
                          include_rulings=True, include_grid=engine.grid is not None)
    if pending:
        exception, event_id = pending[0]
        raise exception(event_id)
    return result


KEY = 'natural_fighter_uses'
TERMINAL = ('complete', 'cancelled', 'interrupted', 'heavy_adjudicated')


def current(actor):
    rows = [r for r in actor.spec.get(KEY, {}).values() if r['phase'] not in TERMINAL]
    if len(rows) > 1:
        raise ValueError('one active Natural Fighter permission required')
    return rows[0] if rows else None


def _proof(record):
    import root_resolution as R
    payload = {key: record[key] for key in
        ('id', 'owner_id', 'subject_id', 'terrain', 'move_id', 'payment', 'before_uses', 'completion_id', 'heavy_event', 'termination')}
    if 'fling_choice' in record:payload['fling_choice'] = record['fling_choice']
    return R.fingerprint(payload)


def _fling_binding(engine, actor, record, completion=None):
    choice = record.get('fling_choice')
    if record['terrain'] != 'urban':
        if choice is not None:raise ValueError('nonurban Natural Fighter cannot own a Fling declaration')
        return
    expected = {'instance_id', 'actor_id', 'target_id', 'edition', 'capture', 'capture_options',
                'consumer_options', 'round', 'scene', 'turn_serial'}
    if (type(choice) is not dict or set(choice) != expected or choice['actor_id'] != actor.entity_id
            or not isinstance(choice['instance_id'], str) or not choice['instance_id']
            or choice['target_id'] not in W.actor_index(engine)
            or choice['instance_id'] not in getattr(engine, '_physical_objects', {})
            or choice['edition'] not in ('core_105', 'korean') or type(choice['capture']) is not bool
            or type(choice['capture_options']) is not dict or type(choice['consumer_options']) is not dict):
        raise ValueError('Natural Fighter lost its actual Fling projectile declaration')
    if completion is None:return
    plan = completion['move'].get('_fling')
    if (not isinstance(plan, dict) or any(plan.get(key) != value for key, value in choice.items())
            or choice['target_id'] not in {target.entity_id for target in completion['targets']}
            or choice['round'] != completion['round'] or choice['turn_serial'] != completion['turn_serial']):
        raise ValueError('Natural Fighter Fling choice differs from its actual native completion')
    launch = completion.get('fling_launch')
    if launch is not None and launch.get('plan') != plan:
        raise ValueError('Natural Fighter Fling lost its original physical launch')


def interested(actor, move_id):
    record = current(actor)
    return record is not None and record['move_id'] == move_id


def group_entry(engine, actor, move_id):
    record = current(actor)
    if record is None or record['move_id'] != move_id:
        return
    if (record['entered'] or record['phase'] != 'starting' or
            getattr(engine, '_natural_fighter_launch', None) != record['id']):
        raise ValueError('Natural Fighter permission belongs to its existing native activation')
    record['entered'] = True


def target_entry(engine, actor, move_id, activation):
    record = current(actor)
    if record is None or record['move_id'] != move_id:
        return
    scopes = [s for s in getattr(engine, '_move_activation_scopes', ())
              if s['actor'] is actor and s['move_id'] == move_id
              and s['activation'] is activation]
    if (activation is None or len(scopes) != 1 or not record['entered'] or
            record['heavy_event'] is not None or
            (record['completion_id'] is not None and
             scopes[0].get('completion_id') != record['completion_id'])):
        raise ValueError('Natural Fighter requires its actual native target continuation')


def bind_frame(engine, frame):
    record = current(frame['actor'])
    if record is None or frame['kind'] != 'move' or frame['source'] != record['move_id']:
        return
    if record['frame'] is None:
        if getattr(engine, '_natural_fighter_launch', None) != record['id']:
            raise ValueError('Natural Fighter native frame lost its paid producer')
        record['frame'] = frame
    elif record['frame'] is frame:
        record['phase'] = 'running'


def begin_move(engine, completion):
    record = current(completion['actor'])
    if record is None or record['move_id'] != completion['move_id']:
        return
    if (record['frame'] is not completion.get('native_action_frame') or
            record['completion_id'] not in (None, completion['id'])):
        raise ValueError('Natural Fighter cannot authorize a second native Move')
    _fling_binding(engine, completion['actor'], record, completion)
    record['completion_id'] = completion['id']
    record['cost_proof'] = _proof(record)
    completion['natural_fighter'] = record['id']


def _all_cancelled(completion):
    return (completion is not None and completion['sealed']
            and completion['phase'] in ('complete', 'interrupted')
            and bool(completion['results'])
            and set(completion['started']) <= set(completion['results'])
            and all(result['cancelled'] is True for result in completion['results'].values()))


def _cancelling_reaction(engine, actor, record, identity=None):
    import combat_move_reactions as REACTION
    found = []
    for reactor in W.actor_index(engine).values():
        for event in reactor.spec.get(REACTION.EVENTS, {}).values():
            if (event['source'] != REACTION.SUCKER or event['kind'] != 'initiation'
                    or event['status'] != 'complete' or event['completion_id'] is not None
                    or event['native_action_id'] != record['frame']['id']
                    or event['attacker_id'] != actor.entity_id
                    or event['trigger_move'] != record['move_id']
                    or identity is not None and event['id'] != identity):
                continue
            REACTION.validate_event(engine, reactor, event)
            if event['result_completion'] is not None:
                found.append(event)
    if len(found) != 1:
        raise ValueError('Natural Fighter cancellation requires its actual initiation reaction')
    return found[0]


def _terminal_authority(engine, actor, record, completion):
    phase, terminal = record['phase'], record.get('termination')
    if not isinstance(terminal, dict) or terminal.get('phase') != phase:
        raise ValueError('Natural Fighter terminal classification changed')
    if phase == 'complete':
        if completion is None or completion['phase'] != 'complete' or not completion['sealed'] or _all_cancelled(completion):
            raise ValueError('Natural Fighter completion contradicts its native results')
    elif phase == 'cancelled':
        if completion is not None:
            if not _all_cancelled(completion) or __import__('action_lifecycle').pending_resolution_effects(engine, completion):
                raise ValueError('Natural Fighter cancellation requires all-cancelled native results')
        else:
            evidence = terminal.get('initiation')
            if not isinstance(evidence, dict):
                raise ValueError('Natural Fighter cancellation lost its native initiation evidence')
            event = _cancelling_reaction(engine, actor, record, evidence.get('reaction_id'))
            if evidence != {'reaction_id': event['id'], 'response_completion_id': event['result_completion'],
                            'native_action_id': event['native_action_id'], 'fainted': True,
                            'move_uses_after': record['before_uses'] + 1}:
                raise ValueError('Natural Fighter initiation cancellation evidence changed')
    elif phase == 'interrupted':
        if (completion is None or completion['phase'] != 'interrupted' or not completion['sealed']
                or not completion['results'] or _all_cancelled(completion)
                or terminal.get('actor_ineligible') is not True
                or __import__('action_lifecycle').pending_resolution_effects(engine, completion)):
            raise ValueError('Natural Fighter interruption requires its actual partial native result')
    elif phase == 'heavy_adjudicated':
        packet = getattr(engine, '_heavy_events', {}).get(record['heavy_event'])
        resolution = None if packet is None else packet.get('resolution')
        if (packet is None or packet['status'] != 'resolved_by_external_ruling'
                or not isinstance(resolution, dict) or resolution.get('event_id') != record['heavy_event']
                or resolution.get('target') is not packet['target']
                or not any(resolution is row for row in engine._heavy_resolution_history)):
            raise ValueError('Natural Fighter Heavy cleanup requires its actual external disposition')


def _close(engine, actor, record, phase):
    completion = getattr(engine, '_move_completions', {}).get(record['completion_id'])
    terminal = {'phase': phase}
    if phase == 'cancelled' and completion is None:
        if (not actor.fainted or not any(record['frame'] is frame for frame in getattr(engine, '_native_action_stack', ()))
                or actor.move_uses.get(record['move_id'], 0) != record['before_uses'] + 1):
            raise ValueError('Natural Fighter requires the actual paid initiation cancellation boundary')
        event = _cancelling_reaction(engine, actor, record)
        terminal['initiation'] = {'reaction_id': event['id'], 'response_completion_id': event['result_completion'],
                                  'native_action_id': event['native_action_id'], 'fainted': True,
                                  'move_uses_after': actor.move_uses[record['move_id']]}
    elif phase == 'interrupted':
        terminal['actor_ineligible'] = bool(actor.fainted or actor.dead)
    _terminal_authority(engine, actor, dict(record, phase=phase, termination=terminal), completion)
    G.revoke(actor, record['id'], engine=engine)
    if record['terrain'] == 'urban':
        import fling_move as FLING
        if actor.spec.get(FLING.CHOICE) == record.get('fling_choice'):
            actor.spec.pop(FLING.CHOICE, None)
    record.update(phase=phase, termination=terminal)
    record['cost_proof'] = _proof(record)


def complete_move(engine, completion):
    source = completion.get('natural_fighter')
    if source is None:
        return
    actor = completion['actor']
    record = actor.spec[KEY][source]
    if record['phase'] in TERMINAL or completion['phase'] != 'complete':
        return
    cancelled = _all_cancelled(completion)
    _close(engine, actor, record, 'cancelled' if cancelled else 'complete')


def finish_action(engine, frame):
    record = current(frame['actor'])
    if record is None or record['frame'] is not frame:
        return
    completion = getattr(engine, '_move_completions', {}).get(record['completion_id'])
    if completion is not None and completion['phase'] == 'complete':
        complete_move(engine, completion)
        return
    if completion is not None and __import__('action_lifecycle').pending_resolution_effects(engine, completion):
        record['phase'] = 'waiting'
        return
    if (frame.get('deferred') or getattr(engine, '_passive_pending', None) is not None
            or getattr(engine, '_heavy_pending', None) is not None):
        return
    # Native initiation cancellation can consume frequency before any target starts.
    if (completion is None or completion['phase'] == 'interrupted') and frame['actor'].move_uses.get(record['move_id'], 0) > record['before_uses']:
        phase = 'cancelled' if completion is None or _all_cancelled(completion) else 'interrupted'
        _close(engine, frame['actor'], record, phase)


def finish_heavy(engine, trainer, *, subject):
    """Release only after the real Heavy owner records its external disposition."""
    W.require_actors(engine, trainer, subject)
    def apply(staged, owner, actor):
        record = current(actor)
        if record is None or record['owner_id'] != owner.entity_id or record['heavy_event'] is None:
            raise ValueError('actual Natural Fighter Heavy wait required')
        packet = staged._heavy_events[record['heavy_event']]
        resolution = packet.get('resolution')
        if (packet['status'] != 'resolved_by_external_ruling' or not resolution or
                resolution not in staged._heavy_resolution_history):
            raise ValueError('acknowledge the actual Heavy ruling before permission cleanup')
        _close(staged, actor, record, 'heavy_adjudicated')
        return {'activation_id': record['id'], 'heavy_event': packet['event_id'],
                'disposition': resolution['disposition'], 'native_resume': False}
    return G.transition(engine, trainer, apply, participants=(subject,))


def validate_world(engine, index):
    __import__('natural_fighter_moves').validate_world(engine, index)
    for actor in index.values():
        rows = actor.spec.get(KEY, {})
        if type(rows) is not dict:
            raise ValueError('Natural Fighter activation mapping required')
        current(actor)
        sources = actor.spec.get(G.KEY, {}).get('sources', {})
        for identity, record in rows.items():
            owner = index.get(record.get('owner_id'))
            if (record.get('id') != identity or record.get('subject_id') != actor.entity_id
                    or owner is None or owner.kind != 'trainer'
                    or MOVES.get(record.get('terrain')) != record.get('move_id')
                    or record.get('cost_proof') != _proof(record)
                    or record.get('phase') not in (*TERMINAL, 'starting', 'running', 'waiting')
                    or type(record.get('entered')) is not bool):
                raise ValueError('Natural Fighter native activation identity changed')
            _fling_binding(engine, actor, record)
            payment = record['payment']
            if (payment['actor_id'] != owner.entity_id or payment['amount'] != 1
                    or payment['mode'] != 'spend' or payment['refunded'] is not False):
                raise ValueError('Natural Fighter requires its one actual trainer AP payment')
            grant = sources.get(identity)
            if record['phase'] in TERMINAL:
                if grant is not None:
                    raise ValueError('finished Natural Fighter retained its Move permission')
            elif (grant is None or grant.get('rule_id') != SC.NATURAL
                    or grant.get('owner_id') != owner.entity_id
                    or grant.get('move_mode') != 'permission'
                    or grant['grants'].get('moves') != [record['move_id']]):
                raise ValueError('Natural Fighter lost its source-owned Move permission')
            frame = record['frame']
            launching = getattr(engine, '_natural_fighter_launch', None) == identity
            if frame is None:
                if not launching:
                    raise ValueError('Natural Fighter lost its actual native frame')
                continue
            if frame['actor'] is not actor or frame['source'] != record['move_id'] or frame['kind'] != 'move':
                raise ValueError('Natural Fighter native frame participant changed')
            native = getattr(engine, '_native_action_resolutions', {}).get(frame['id'])
            if frame['id'] is not None and (native is None or native['actor'] is not actor or native['source'] != record['move_id']):
                raise ValueError('Natural Fighter native action identity changed')
            completion = getattr(engine, '_move_completions', {}).get(record['completion_id'])
            if record['completion_id'] is not None:
                if (completion is None or completion['actor'] is not actor
                        or completion['move_id'] != record['move_id']
                        or completion.get('natural_fighter') != identity
                        or completion.get('native_action_frame') is not frame):
                    raise ValueError('Natural Fighter completion lost its paid native frame')
                _fling_binding(engine, actor, record, completion)
            live_frame = any(frame is active for active in getattr(engine, '_native_action_stack', ()))
            if record['phase'] in ('starting', 'running') and not launching and not live_frame:
                raise ValueError('Natural Fighter unresolved action lacks its live producer')
            if record['phase'] in TERMINAL:
                _terminal_authority(engine, actor, record, completion)
            elif record.get('termination') is not None:
                raise ValueError('unfinished Natural Fighter retained a terminal disposition')
            if record['heavy_event'] is not None:
                packet = getattr(engine, '_heavy_events', {}).get(record['heavy_event'])
                # A nested reaction may own the Heavy event; the original frame
                # still owns its paid prefix, and Heavy owns all unresolved order.
                if packet is None:
                    raise ValueError('Natural Fighter lost its actual Heavy wait')
            elif record['phase'] == 'waiting' and completion is None:
                if native is None or not native.get('combat_move_continuations'):
                    raise ValueError('Natural Fighter lost its native initiation continuation')
        for source, grant in sources.items():
            if grant.get('rule_id') == SC.NATURAL and grant.get('move_mode') == 'permission' and source not in rows:
                raise ValueError('Natural Fighter permission has no paid activation')


def suspend_action(engine, frame, error):
    record = current(frame['actor'])
    if record is None or record['frame'] is not frame:
        return
    registered = []
    if not G.record_native_pending(engine, error, registered):
        return
    import heavy_injury_adapter as HEAVY
    if type(error) is HEAVY.HeavyPending:
        record['heavy_event'] = error.event_id
        record['cost_proof'] = _proof(record)
    record['phase'] = 'waiting'



def pending_initiation(engine, scope, error):
    """The existing Combat Move reaction owns the pre-completion paid suffix."""
    import passive_events as P
    import combat_move_reactions as REACTION
    record = current(scope['actor'])
    if (record is None or type(error) is not P.PassiveEventPending
            or engine._passive_pending != error.event_id or scope.get('completion_id') is not None):
        return False
    for actor in engine.everyone:
        for event in actor.spec.get(REACTION.EVENTS, {}).values():
            if event.get('pending_event_id') != error.event_id or event['status'] != 'resolving':
                continue
            context = REACTION._context(engine, event)
            if context is None or context['frame'] is not record['frame']:
                continue
            args = context['args']
            if (args['attacker'] is not scope['actor'] or args['move_id'] != scope['move_id']
                    or args['move_id'] != record['move_id']):
                continue
            saved = [s for s in context['activation_scopes']
                     if s['activation'] is args['_activation'] and s['actor'] is scope['actor']]
            if len(saved) == 1 and saved[0]['targets'] == scope['targets'] and saved[0]['index'] == scope['index']:
                return True
    return False


def resume_initiation(engine, context, result):
    """Continue the actual target group after its first paid native suffix."""
    import move_activation as ACTIVATION
    import move_completion as COMPLETE
    import action_lifecycle as ACTION
    actor = context['args']['attacker']
    record = current(actor)
    if record is None or record['frame'] is not context['frame']:
        return result
    scopes = [s for s in context['activation_scopes']
              if s['actor'] is actor and s['activation'] is context['args']['_activation']]
    if not scopes:
        return result
    if len(scopes) != 1 or not any(scopes[0] is s for s in getattr(engine, '_move_activation_scopes', ())):
        raise ValueError('Natural Fighter lost its actual resumed native group')
    scope = scopes[0]
    if scope.get('completion_id') is None:
        return result
    if scope['lifetime'][1:] != ACTIVATION._lifetime(engine)[1:] or scope['profile'] != ACTIVATION._profile(engine):
        raise ValueError('Natural Fighter resumed native group boundary changed')
    scope['lifetime'] = ACTIVATION._lifetime(engine)
    try:
        interrupted = ACTIVATION.note_result(engine, scope['activation'], result)
        while not interrupted and scope['index'] < len(scope['targets']):
            target = scope['targets'][scope['index']]
            with ACTION.move_grant(engine, actor, target, scope['move_id'], source='same_move_activation') as grant:
                dealt = engine.use_move(actor, target, scope['move_id'], count_use=False,
                    _activation=scope['activation'], _shared_accuracy=scope['accuracy'],
                    _action_grant=grant, **scope['options'])
            interrupted = ACTIVATION.note_result(engine, scope['activation'], dealt)
        COMPLETE.seal(engine, scope, interrupted=interrupted)
        return scope['total']
    except BaseException as error:
        if not ACTIVATION.suspend(engine, scope, error):
            COMPLETE.seal(engine, scope, interrupted=True)
        raise



def continue_initiation(engine, context):
    """A second wait can arise inside the resumed first recipient itself."""
    actor = context['args']['attacker']
    record = current(actor)
    if record is None or record['frame'] is not context['frame']:
        return engine._continue_move_after_payment(**context['args'])
    scopes = [s for s in context['activation_scopes']
              if s['actor'] is actor and s['activation'] is context['args']['_activation']]
    try:
        return engine._continue_move_after_payment(**context['args'])
    except BaseException as error:
        if len(scopes) == 1:
            import move_activation as ACTIVATION
            import move_completion as COMPLETE
            if not ACTIVATION.suspend(engine, scopes[0], error):
                COMPLETE.seal(engine, scopes[0], interrupted=True)
        raise






