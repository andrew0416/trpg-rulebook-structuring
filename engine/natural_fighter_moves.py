"""Reviewed Astonish and Sand Attack clauses through native status owners."""
from copy import deepcopy

ASTONISH = 'move/놀래키기'
SAND = 'move/모래뿌리기'
PREDICATE = 'Astonish native Flinch condition'
QUOTA = ASTONISH + '/unaware'
ONCE = {'kind': 'scene', 'uses': 1}
FLINCH = {'type': 'apply_status', 'status': '풀죽음', 'target': 'target'}
BLIND = {'type': 'apply_status', 'status': '실명', 'target': 'target',
         'until': "end of target's next turn"}


def definition(rules, source):
    if source not in (ASTONISH, SAND):return
    from source_context import verified_source
    # Existing registered CSV authority, also used by the native Substitute owner.
    verified_source(rules, {'file': 'input/db/moves.csv',
        'sha256': 'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'},
        label='Astonish and Sand Attack Core 1.05 clauses')
    if rules._selected_rule(source) != source:
        raise ValueError('selected Astonish/Sand Attack edition needs its own adapter')


def mechanics(rules, source, mechanics):
    if source not in (ASTONISH, SAND):return mechanics
    definition(rules, source)
    semantic = deepcopy(mechanics)
    semantic['effects_exec'] = [{k: v for k, v in e.items() if not k.startswith('_')}
                                for e in semantic.get('effects_exec', [])]
    expected = ({'apply_status': '풀죽음', 'effects_exec': [dict(FLINCH, on_natural_roll_min=15)]}
                if source == ASTONISH else {'apply_status': '실명', 'effects_exec': []})
    if semantic != expected:
        raise ValueError('selected Astonish/Sand Attack extraction changed')
    effects = ([dict(FLINCH, on_natural_roll_min=15), dict(FLINCH, **{'if': PREDICATE})]
               if source == ASTONISH else [deepcopy(BLIND)])
    return {'effects_exec': effects}


def awareness_key(engine, actor, target):
    import frequency as F
    state = F.state(actor)
    return ':'.join((QUOTA, actor.entity_id, target.entity_id,
        str(state['scene']), str(engine.round_no),
        str(actor.custom_conditions.get('combat_turn_serial', 0)),
        str(actor.move_uses.get(ASTONISH, 0) + 1)))


def prepare_move(engine, actor, target, move):
    if move['id'] != ASTONISH:return move
    definition(engine.r, ASTONISH)
    import world_entities as W
    import frequency as F
    W.require_actors(engine, actor, target)
    if not F.activation_allowed(actor, QUOTA, ONCE, engine=engine):return move
    key = awareness_key(engine, actor, target)
    answer = engine.rulings.decide({'type': key, 'unit': ASTONISH,
        'actor': actor.name, 'target': target.name, 'actor_id': actor.entity_id,
        'target_id': target.entity_id, 'observation_key': key,
        'text': 'Before this attack, is this actual target unaware of this user presence? '
                'Return {observation_key: the exact key, unaware: boolean}.'})
    if (type(answer) is not dict or set(answer) != {'observation_key', 'unaware'}
            or answer['observation_key'] != key or type(answer['unaware']) is not bool):
        raise ValueError('Astonish requires an explicit actual-target presence-awareness observation before cost')
    return dict(move, _astonish_awareness={'target_id': target.entity_id,
                'actor_id': actor.entity_id, 'observation_key': key, 'unaware': answer['unaware'],
                'scene': F.state(actor)['scene'], 'round': engine.round_no,
                'turn_serial': actor.custom_conditions.get('combat_turn_serial', 0),
                'next_use': actor.move_uses.get(ASTONISH, 0) + 1})


def natural_flinch(engine, actor, target, ctx):
    import effect_contracts as C
    test = dict(FLINCH, on_natural_roll_min=15)
    verdict = C.condition(engine, test, ctx, source=ASTONISH)
    if verdict.truth is C.ROOT.Truth.UNKNOWN:return None
    return verdict.truth is C.ROOT.Truth.TRUE


def native_observation(engine, actor, target, ctx):
    """The live native recipient and its issued completion own this observation."""
    import attack_damage_history as HISTORY
    import frequency as F
    frame = HISTORY.native_recipient(engine, actor, target, dict(ctx, source_id=ASTONISH))
    if frame is None:return None
    if frame[2] is not ctx.get('move'):
        raise ValueError('Astonish needs the actual native Move object')
    completion = engine._move_completions.get(frame[3])
    if (completion is None or completion['actor'] is not actor
            or completion['move_id'] != ASTONISH or completion['phase'] != 'targets'
            or completion['round'] != engine.round_no
            or completion['turn_serial'] != actor.custom_conditions.get('combat_turn_serial', 0)):
        raise ValueError('Astonish needs its current issued native completion')
    row = frame[2].get('_astonish_awareness', {})
    if row.get('actor_id') != actor.entity_id or row.get('target_id') != target.entity_id:
        return redirected_observation(engine, actor, target, ctx)
    if (target.entity_id not in completion['started'] or target not in completion['targets']
            or completion['move'].get('_astonish_awareness') != row
            or row.get('scene') != F.state(actor)['scene']
            or row.get('round') != completion['round']
            or row.get('turn_serial') != completion['turn_serial']
            or type(row.get('next_use')) is not int or row['next_use'] < 1
            or type(row.get('unaware')) is not bool):
        raise ValueError('Astonish awareness does not belong to this native occurrence')
    key = ':'.join((QUOTA, actor.entity_id, target.entity_id, str(row['scene']),
        str(row['round']), str(row['turn_serial']), str(row['next_use'])))
    if row.get('observation_key') != key:
        raise ValueError('Astonish native observation key changed')
    return row


def qualifies(engine, actor, target, ctx):
    definition(engine.r, ASTONISH)
    move = ctx.get('move') or {}
    if move.get('id') != ASTONISH:return False
    import attack_damage_history as HISTORY
    if HISTORY.native_recipient(engine, actor, target, dict(ctx, source_id=ASTONISH)) is None:
        return False
    natural = natural_flinch(engine, actor, target, ctx)
    if natural is not False:return None if natural is None else False
    import frequency as F
    if not F.activation_allowed(actor, QUOTA, ONCE, engine=engine):return False
    row = native_observation(engine, actor, target, ctx)
    return None if row is None else row['unaware']


def apply(engine, actor, target, effect, ctx):
    expected = dict(FLINCH, **{'if': PREDICATE})
    if {k: v for k, v in effect.items() if not k.startswith('_')} != expected:
        raise ValueError('Astonish automatic Flinch requires its exact final effect')
    if ctx.get('source_id') != ASTONISH or qualifies(engine, actor, target, ctx) is not True:
        raise ValueError('actual native Astonish Flinch observation required')
    import effect_contracts as C
    receipt = ctx.get('effect_receipt')
    C.validate_receipt(engine, receipt, ASTONISH, ctx.get('effect_occurrence'), actor, target, effect)
    issued = engine._effect_dispatch_receipts[receipt]
    if issued['status'] != 'dispatching' or 'astonish_auto' in issued:
        raise ValueError('one actual issued Astonish Flinch occurrence required')
    observation = native_observation(engine, actor, target, ctx)
    issued['astonish_auto'] = {'completion_id': ctx['move_completion'],
        'observation_key': observation['observation_key'], 'target_id': target.entity_id}
    import frequency as F
    F.consume_activation(actor, QUOTA, ONCE, engine=engine)
    engine.apply_status(target, '풀죽음', source=ASTONISH, applied_by=actor)


AWARENESS = 'astonish_recipient_awareness'
AWARENESS_WAIT = 'astonish_actual_recipient_awareness'


def _awareness_proof(record):
    import root_resolution as ROOT
    return ROOT.fingerprint({key: record[key] for key in ('facts', 'answer', 'cancelled')})


def _redirect_facts(engine, event, recipient_id):
    import move_defense_reactions as DEFENSE
    import move_completion as COMPLETE
    state = DEFENSE._defense(engine, event)
    completion = DEFENSE._row(engine, event)
    move = COMPLETE.event_move(engine, event)
    original = move.get('_astonish_awareness')
    if (move.get('id') != ASTONISH or type(original) is not dict
            or original.get('actor_id') != event['actor'].entity_id
            or original.get('target_id') != event['target'].entity_id
            or type(original.get('unaware')) is not bool
            or original.get('round') != completion['round']
            or original.get('turn_serial') != completion['turn_serial']
            or type(original.get('next_use')) is not int or original['next_use'] < 1
            or state is None or state['facts']['move'] != DEFENSE._move_facts(move)
            or recipient_id == event['target'].entity_id):
        raise ValueError('Astonish recipient request lost its actual original observation')
    original_key = ':'.join((QUOTA, original['actor_id'], original['target_id'],
        str(original['scene']), str(original['round']), str(original['turn_serial']), str(original['next_use'])))
    if original['observation_key'] != original_key:
        raise ValueError('Astonish original occurrence key changed')
    key = ':'.join((original_key, 'recipient', str(event['id']), str(completion['id']), recipient_id))
    return {'source': ASTONISH, 'parent_id': event['id'], 'completion_id': completion['id'],
        'actor_id': event['actor'].entity_id, 'original_id': event['target'].entity_id,
        'recipient_id': recipient_id, 'original': deepcopy(original),
        'profile': deepcopy(completion['profile']), 'defense_fingerprint': state['fingerprint'],
        'observation_key': key}


def _redirect_record(engine, event, recipient_id):
    import move_defense_reactions as DEFENSE
    completion = DEFENSE._row(engine, event)
    records = completion.get(AWARENESS, {}).get(event['id'], {})
    record = records.get(recipient_id)
    if (type(record) is not dict or set(record) != {'facts', 'answer', 'cancelled', 'fingerprint'}
            or event.get(AWARENESS, {}).get(recipient_id) is not record
            or record['facts'] != _redirect_facts(engine, event, recipient_id)
            or type(record['cancelled']) is not bool
            or record['fingerprint'] != _awareness_proof(record)):
        raise ValueError('Astonish actual-recipient awareness receipt changed or missing')
    answer = record['answer']
    if answer is not None and (type(answer) is not dict or set(answer) != {'observation_key', 'unaware'}
            or answer['observation_key'] != record['facts']['observation_key']
            or type(answer['unaware']) is not bool):
        raise ValueError('Astonish actual-recipient awareness answer changed')
    state = DEFENSE._defense(engine, event)
    if record['cancelled']:
        if (answer is not None or state['phase'] != 'cancelled'
                or event.get('continuation_cancelled') != 'actor_no_longer_eligible'
                or not completion['results'].get(event['target'].entity_id, {}).get('cancelled')):
            raise ValueError('Astonish awareness cancellation lacks native cancellation authority')
    elif not any(p['actor_id'] == recipient_id and p['intercepted'] and p['hit']
                 for p in state['recipients']):
        raise ValueError('Astonish awareness recipient differs from actual native route')
    return record


def prepare_redirected_recipient(engine, event, recipient, args, token, *, hit):
    """Pause the paid parent before creating its actual redirected child."""
    if args['move_id'] != ASTONISH or recipient is event['target'] or not hit:return
    import move_defense_reactions as DEFENSE
    import passive_events as PASSIVE
    import frequency as F
    if not DEFENSE.require_recipient(engine, token, args['attacker'], recipient,
                                    args['move'], args['completion_id']):return
    completion = DEFENSE._row(engine, event)
    records = completion.get(AWARENESS, {}).get(event['id'], {})
    record = records.get(recipient.entity_id)
    if record is None:
        if recipient.entity_id in event.get(AWARENESS, {}):
            raise ValueError('Astonish actual-recipient awareness receipt missing')
        if not F.activation_allowed(args['attacker'], QUOTA, ONCE, engine=engine):return
        import effects_ext as EXT
        if EXT.blocks_hit(engine, args['attacker'], recipient, args['move'], args['mm']):return
        ctx = {'attacker': args['attacker'], 'target': recipient, 'move': args['move'],
            'hit': True, 'nat': args['nat'], 'crit': args['crit'], 'engine': engine,
            'actual_damage_type': EXT.effective_type(engine, args['attacker'], recipient,
                                                     args['move'], args['mm'], consume=False)}
        if natural_flinch(engine, args['attacker'], recipient, ctx) is True:return
        facts = _redirect_facts(engine, event, recipient.entity_id)
        record = {'facts': facts, 'answer': None, 'cancelled': False}
        record['fingerprint'] = _awareness_proof(record)
        completion.setdefault(AWARENESS, {}).setdefault(event['id'], {})[recipient.entity_id] = record
        event.setdefault(AWARENESS, {})[recipient.entity_id] = record
    record = _redirect_record(engine, event, recipient.entity_id)
    if record['cancelled']:raise ValueError('cancelled Astonish awareness cannot resume')
    if record['answer'] is not None:return
    key = record['facts']['observation_key']
    answer = engine.rulings.decide({'type': key, 'unit': ASTONISH,
        'actor': args['attacker'].name, 'target': recipient.name,
        'actor_id': args['attacker'].entity_id, 'target_id': recipient.entity_id,
        'observation_key': key, 'text': 'Before this attack, was this actual redirected recipient '
        'unaware of this user presence? Return {observation_key: the exact key, unaware: boolean}.'})
    if answer is None:return PASSIVE._pending(engine, event, AWARENESS_WAIT)
    if (type(answer) is not dict or set(answer) != {'observation_key', 'unaware'}
            or answer['observation_key'] != key or type(answer['unaware']) is not bool):
        raise ValueError('Astonish requires a typed current actual-recipient awareness answer')
    record['answer'] = deepcopy(answer)
    record['fingerprint'] = _awareness_proof(record)


def redirected_observation(engine, actor, target, ctx):
    import move_defense_reactions as DEFENSE
    token = getattr(engine, '_defense_recipient_scope', None)
    if token is None:return None
    DEFENSE.require_recipient(engine, token, actor, target, ctx['move'], ctx['move_completion'])
    event = engine._passive_events[token[0]]
    record = _redirect_record(engine, event, target.entity_id)
    if record['cancelled'] or record['answer'] is None:
        raise ValueError('Astonish requires its accepted actual-recipient awareness answer')
    return record['answer']


def waiting_recipient_awareness(engine, event):
    """Only an issued unpaid-recipient suffix may cancel after attacker knockout."""
    if event.get('reason') != AWARENESS_WAIT:return False
    import move_defense_reactions as DEFENSE
    import passive_events as PASSIVE
    import root_resolution as ROOT
    state = DEFENSE._defense(engine, event)
    frame = event.get('continuation')
    if (state is None or state['phase'] != 'resolving' or state['children'] or state['total']
            or state.get('active_attempt') or event['phase'] != 'accuracy_boundary'
            or frame is None or ROOT.fingerprint(PASSIVE._continuation_facts(engine, event, frame)) != frame['fingerprint']):
        return False
    records = event.get(AWARENESS, {})
    if not records:raise ValueError('Astonish pending actual-recipient awareness receipt missing')
    waiting = [_redirect_record(engine, event, uid) for uid in records]
    return any(row['answer'] is None and not row['cancelled'] for row in waiting)


def cancel_recipient_awareness(engine, event):
    if not waiting_recipient_awareness(engine, event):return
    for record in event[AWARENESS].values():
        if record['answer'] is None:
            record['cancelled'] = True
            record['fingerprint'] = _awareness_proof(record)


def validate_world(engine, index):
    for completion in getattr(engine, '_move_completions', {}).values():
        records = completion.get(AWARENESS, {})
        if type(records) is not dict:raise ValueError('Astonish awareness mapping required')
        for parent_id, recipients in records.items():
            event = engine._passive_events.get(parent_id)
            if (event is None or event.get('completion_id') != completion['id']
                    or type(recipients) is not dict or not recipients
                    or set(event.get(AWARENESS, {})) != set(recipients)):
                raise ValueError('Astonish awareness lost its actual parent')
            for uid in recipients:
                if uid not in index:raise ValueError('Astonish awareness recipient missing')
                _redirect_record(engine, event, uid)
    for event in getattr(engine, '_passive_events', {}).values():
        for uid in event.get(AWARENESS, {}):
            _redirect_record(engine, event, uid)
        if event.get('reason') == AWARENESS_WAIT:
            if not event.get(AWARENESS):
                raise ValueError('Astonish pending actual-recipient awareness receipt missing')
            # Native defense validation separately authenticates paid attempts and movement.
            if not any(row['answer'] is None and not row['cancelled'] for row in event[AWARENESS].values()):
                raise ValueError('Astonish pending reason lacks an unanswered actual request')
