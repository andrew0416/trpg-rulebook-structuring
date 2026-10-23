"""Data-declared lifetimes over actual native clocks, actors and boundaries.

This module owns scheduling, not effect arithmetic. Repeated consequences use
the existing dispatcher, and each delivery retains its actual receipt.
"""
from copy import deepcopy
import common_checks as C
import combat_timing as TIME

KEY = 'lifetime_policy'
CONTROLS = ('duration', 'until', 'while', 'repeat')
TURN_EVENTS = {'turn_start', 'turn_end'}
OWNER_EVENTS = TURN_EVENTS | {'extended_rest'}
EVENTS = OWNER_EVENTS | {'round_end', 'scene_end', 'encounter_end'}
REPEAT_KINDS = {'stage_change', 'heal', 'hp_loss', 'apply_status', 'cure_status'}


def owner(record, selector):
    return record['lifetime_actor' if selector == 'user' else 'lifetime_target']


def _event(value, *, repeating=False):
    if type(value) is not dict:
        raise ValueError('event lifetime needs an explicit data declaration')
    allowed = {'event', 'owner', 'times'} if repeating else {'event', 'owner', 'after'}
    if set(value) - allowed or value.get('event') not in EVENTS:
        raise ValueError('unknown lifetime event or field')
    event = value['event']
    if event in OWNER_EVENTS:
        if value.get('owner') not in ('user', 'target'):
            raise ValueError('actor boundary needs its actual user or target owner')
    elif 'owner' in value:
        raise ValueError('world boundary cannot have a turn owner')
    count = C.integer(value.get('times' if repeating else 'after', 1), 'boundary count', 1)
    if event == 'extended_rest' and (repeating or count != 1):
        raise ValueError('extended rest ends at the next actual owner milestone')
    if event in ('scene_end', 'encounter_end') and (repeating or count != 1):
        raise ValueError('scene and encounter declarations end at the next actual boundary')
    return dict(value, **{'times' if repeating else 'after': count})


def _predicate(engine, actor, target, value):
    if type(value) is not dict or value.get('owner') not in ('user', 'target'):
        raise ValueError('while needs an actual owner and an explicit state predicate')
    selected = actor if value['owner'] == 'user' else target
    if set(value) == {'owner', 'condition'}:
        if type(value['condition']) is not str or not value['condition'].strip():
            raise ValueError('named condition required')
        engine.r.condition_effects(value['condition'])
    elif set(value) == {'owner', 'cells', 'membership'}:
        import body_state as BODY
        BODY.cells(selected, require_complete=True)
        cells = value['cells']
        if (not isinstance(cells, (list, tuple)) or not cells or
            any(not isinstance(q, (list, tuple)) or len(q) != 2 or
                any(type(n) is not int for n in q) for q in cells)):
            raise ValueError('region needs concrete grid cells')
        if len({tuple(q) for q in cells}) != len(cells):
            raise ValueError('region cells must be distinct')
        if engine.grid is None or any(not engine.grid.inside(tuple(q)) for q in cells):
            raise ValueError('region must belong to the actual map')
        if value['membership'] not in ('any', 'all'):
            raise ValueError('region needs an explicit body membership policy')
    else:
        raise ValueError('unknown continuous lifetime predicate')
    return deepcopy(value)


def prepare(engine, actor, target, effect, source):
    import world_entities as W
    W.require_actors(engine, actor, target)
    if 'duration' in effect and 'until' in effect:
        raise ValueError('duration and until require an explicit composition rule')
    plan = {'declaration': deepcopy({k: effect[k] for k in CONTROLS if k in effect}),
            'started_at': engine.elapsed_seconds, 'started_round': engine.round_no,
            'started_turns': {k: c.custom_conditions.get('combat_turn_serial', 0)
                              for k, c in (('user', actor), ('target', target))}}
    if 'duration' in effect:
        value = effect['duration']
        if type(value) is not dict or set(value) != {'seconds'}:
            raise ValueError('data duration requires a positive seconds interval')
        plan['end_at'] = engine.elapsed_seconds + C.integer(value['seconds'], 'duration seconds', 1)
    if 'until' in effect:
        value = effect['until']
        if value in ('scene_end', 'encounter_end'):
            value = {'event': value}
        plan['until'] = _event(value)
        if plan['until']['event'] in TURN_EVENTS | {'round_end', 'encounter_end'} and not engine.encounter_active:
            raise ValueError('combat lifetime requires an actual encounter')
    if 'while' in effect:
        plan['while'] = _predicate(engine, actor, target, effect['while'])
    if 'repeat' in effect:
        value = effect['repeat']
        if type(value) is dict and set(value) == {'seconds', 'times'}:
            plan['repeat'] = {'seconds': C.integer(value['seconds'], 'repeat interval', 1),
                              'times': C.integer(value['times'], 'repeat count', 1)}
        else:
            plan['repeat'] = _event(value, repeating=True)
            if not engine.encounter_active:
                raise ValueError('combat repetition requires an actual encounter')
        if effect['type'] not in REPEAT_KINDS:
            raise ValueError('repeat requires an existing immediate consequence consumer')
        payload = {k: deepcopy(v) for k, v in effect.items() if k not in CONTROLS + ('target', 'on')}
        payload['target'] = 'target'
        import effect_contracts as CONTRACTS
        issue = CONTRACTS.inspect(engine, actor, target, payload, source)
        if issue is not None:
            raise ValueError('repeat consequence is unresolved: ' + issue.detail)
        plan['repeat_effect'] = payload
    return {'source': source, 'effect_contract': True, 'timing_text': deepcopy(plan['declaration']),
            KEY: plan, 'lifetime_actor': actor, 'lifetime_target': target, 'lifetime_deliveries': []}


def holds(engine, record):
    value = record[KEY].get('while')
    if value is None:
        return True
    actor = owner(record, value['owner'])
    if 'condition' in value:
        return value['condition'] in actor.conditions
    import body_state as BODY
    occupied = BODY.cells(actor, require_complete=True)
    region = {tuple(q) for q in value['cells']}
    return bool(occupied & region) if value['membership'] == 'any' else occupied <= region


def reconcile(engine):
    # Expiring an imposed condition can invalidate another contribution.
    if getattr(engine, '_lifetime_delivery_depth', 0):
        return
    import state_grants as G
    G.sync_capability_losses(engine)
    import network_integrity as INTEGRITY
    INTEGRITY.boundary(engine,'reconcile')
    import environment_change as EC
    EC.boundary(engine,'reconcile')
    import grapple_state as GRAPPLE
    GRAPPLE.boundary(engine)
    import perception_communicate as COMM
    COMM.boundary(engine,'reconcile')
    import control_remote as REMOTE
    REMOTE.boundary(engine,'reconcile')
    import legendary_commands as LEGENDARY
    LEGENDARY.boundary(engine,'reconcile')
    while True:
        expired = False
        for actor in list(getattr(engine, '_time_actors', ())):
            for record in list(TIME.records(actor)):
                if KEY in record and not holds(engine, record):
                    TIME.expire(engine, actor, record, event={'kind': 'condition_ended'})
                    expired = True
        if not expired:
            import field_effects as FIELD
            FIELD.refresh_local_weather(engine)
            return


def _matches(record, declaration, event, actor):
    return declaration['event'] == event and (event not in OWNER_EVENTS or owner(record, declaration['owner']) is actor)


def _ended(engine, record, event, actor):
    plan = record[KEY]
    if plan.get('end_at') is not None and engine.elapsed_seconds >= plan['end_at']:
        return True
    until = plan.get('until')
    if until is None or not _matches(record, until, event, actor):
        return False
    if event in TURN_EVENTS:
        return actor.custom_conditions.get('combat_turn_serial', 0) >= plan['started_turns'][until['owner']] + until['after']
    if event == 'round_end':
        return engine.round_no >= plan['started_round'] + until['after'] - 1
    return True


def _deliver(engine, actor, record, event, token):
    import effects as FX
    plan = record[KEY]
    previous_depth = getattr(engine, '_lifetime_delivery_depth', 0)
    engine._lifetime_delivery_depth = previous_depth + 1
    try:
        result = FX.run_effects(engine, record['lifetime_actor'], actor, [plan['repeat_effect']],
                               {'hit': True, 'lifetime_event': event}, record['source'])
    finally:
        if previous_depth:engine._lifetime_delivery_depth = previous_depth
        else:vars(engine).pop('_lifetime_delivery_depth', None)
    if (not result.pending and (result != (1, 0) or any(row.status != 'completed' for row in result.outcomes))
            or result.pending and any(row.status not in ('completed','condition_unknown','awaiting_input','deferred_suffix') for row in result.outcomes)):
        raise ValueError('repeat consequence did not complete at its actual boundary')
    delivery={'event':event,'token':token,'receipt':result.outcomes[0].receipt}
    record['lifetime_deliveries'].append(delivery)
    import clock_invocations as CLOCK
    CLOCK.child(engine,actor,delivery,kind='lifetime_delivery')
    if result.pending:
        if not CLOCK.executing_resumable(engine):
            raise ValueError('pending repeat requires a resumable clock invocation')
        return False
    if len(record['lifetime_deliveries']) >= plan['repeat']['times']:
        TIME.expire(engine, actor, record, ending='consumed', event={'kind': event, 'token': token})
    return True


def boundary(engine, event, actor=None):
    import state_grants as G
    G.sync_capability_losses(engine)
    import perception_communicate as COMM
    import control_remote as REMOTE
    import network_integrity as INTEGRITY
    import environment_change as EC
    import grapple_state as GRAPPLE
    import legendary_commands as LEGENDARY
    import temporary_ap as TEMP_AP
    if not TEMP_AP.has_duration(engine) and not LEGENDARY.has_controls(engine) and not GRAPPLE.has_pending(engine) and not EC.has_pending(engine) and not INTEGRITY.has_pending(engine) and not REMOTE.has_routes(engine) and not COMM.has_connections(engine) and not any(KEY in record for target in getattr(engine, '_time_actors', ()) for record in TIME.records(target)):
        return
    import state_grants as G
    def apply(staged, primary, *participants):
        return _boundary(staged, event, participants[0] if participants else None)
    return G.transition(engine, None, apply, participants=() if actor is None else (actor,))


def _boundary(engine, event, actor=None):
    import temporary_ap as TEMP_AP
    TEMP_AP.boundary(engine,event)
    # An ending boundary precedes repetition at the same instant.
    import perception_communicate as COMM
    COMM.boundary(engine,event,actor)
    import legendary_commands as LEGENDARY
    LEGENDARY.boundary(engine,event,actor)
    import grapple_state as GRAPPLE
    GRAPPLE.boundary(engine,event,actor)
    reconcile(engine)
    for target in list(getattr(engine, '_time_actors', ())):
        for record in list(TIME.records(target)):
            if KEY not in record:
                continue
            deliveries=record['lifetime_deliveries']
            if deliveries:
                last=deliveries[-1]
                if engine._effect_dispatch_receipts[last['receipt']]['status']!='completed':
                    return False
                if len(deliveries)==record[KEY].get('repeat',{}).get('times'):
                    TIME.expire(engine,target,record,ending='consumed',event={'kind':last['event'],'token':last['token']})
                    continue
            if _ended(engine, record, event, actor):
                TIME.expire(engine, target, record, event={'kind': event})
                continue
            repeat = record[KEY].get('repeat')
            if repeat is None:
                continue
            if 'seconds' in repeat and event == 'time_advanced':
                while record in TIME.records(target):
                    due = record[KEY]['started_at'] + repeat['seconds'] * (len(record['lifetime_deliveries']) + 1)
                    if due > engine.elapsed_seconds or not holds(engine, record):
                        break
                    if not _deliver(engine,target,record,event,due):return False
                    import clock_invocations as CLOCK
                    if CLOCK.executing_resumable(engine):return 'progress'
            elif 'event' in repeat and _matches(record, repeat, event, actor):
                token = (engine.round_no, None if actor is None else actor.entity_id,
                         None if actor is None else actor.custom_conditions.get('combat_turn_serial', 0))
                if not any(row['event'] == event and row['token'] == token for row in record['lifetime_deliveries']):
                    if not _deliver(engine,target,record,event,token):return False
    reconcile(engine)
    return True


def archive(engine, actor, record, *, ending, event):
    history = actor.custom_conditions.setdefault('effect_lifetime_history', [])
    if any(row['occurrence'] == record['effect_occurrence'] for row in history):
        raise ValueError('lifetime occurrence already ended')
    history.append({'source': record['source'], 'occurrence': record['effect_occurrence'],
                    'receipt': record['effect_receipt'], 'policy': deepcopy(record[KEY]),
                    'started_at': record[KEY]['started_at'], 'ended_at': engine.elapsed_seconds,
                    'state': ending, 'event': deepcopy(event),
                    'deliveries': list(record['lifetime_deliveries'])})


def next_interval(engine, end_at):
    """Split a shared interval at actual due instants, before applying consequences."""
    import perception_communicate as COMM
    next_at = end_at
    for actor in getattr(engine, '_time_actors', ()):
        for record in TIME.records(actor):
            plan = record.get(KEY)
            if plan is None:
                continue
            deadlines = [plan.get('end_at')]
            repeat = plan.get('repeat', {})
            if 'seconds' in repeat:
                deadlines.append(plan['started_at'] + repeat['seconds'] * (len(record['lifetime_deliveries']) + 1))
            for deadline in deadlines:
                if deadline is not None and engine.elapsed_seconds < deadline < next_at:
                    next_at = deadline
    import network_integrity as INTEGRITY
    import environment_change as EC
    import environmental_item_state as ITEMS
    import legendary_commands as LEGENDARY
    import temporary_ap as TEMP_AP
    return min(TEMP_AP.next_interval(engine,end_at),next_at - engine.elapsed_seconds,COMM.next_interval(engine,end_at),INTEGRITY.next_interval(engine,end_at),EC.next_interval(engine,end_at),ITEMS.next_interval(engine,end_at),LEGENDARY.next_interval(engine,end_at))


def end_selected(engine, actor, *, source=None, occurrence=None):
    import world_entities as W
    import state_grants as G
    W.require_actors(engine, actor, actor)
    if source is None and occurrence is None:
        raise ValueError('bulk lifetime ending needs an explicit source or occurrence selector')
    if any(value is not None and (type(value) is not str or not value.strip()) for value in (source, occurrence)):
        raise ValueError('nonempty lifetime selectors required')
    def apply(staged, target):
        count = 0
        for record in list(TIME.records(target)):
            if (record.get('effect_contract') and (source is None or record['source'] == source)
                and (occurrence is None or record['effect_occurrence'] == occurrence)):
                TIME.expire(staged, target, record, ending='ended', event={'kind': 'source_ended'})
                count += 1
        return count
    return G.transition(engine, actor, apply)


def validate_world(engine, index):
    import effect_contracts as CONTRACTS
    import perception_communicate as COMM
    COMM.validate_world(engine,index)
    for target in index.values():
        seen = set()
        for history in target.custom_conditions.get('effect_lifetime_history', []):
            occurrence = history.get('occurrence')
            if occurrence in seen:
                raise ValueError('lifetime occurrence has multiple endings')
            seen.add(occurrence)
            try:
                producer = engine._effect_dispatch_receipts.get(history.get('receipt'))
            except TypeError:
                raise ValueError('opaque lifetime ending receipt required')
            if not producer or producer.get('status') != 'completed':
                raise ValueError('lifetime ending requires its completed producer')
            CONTRACTS.validate_receipt(engine,history['receipt'],history['source'],occurrence,
                                      producer['actor'],producer['target'],producer['effect'])
            contract = producer.get('lifetime_contracts', {}).get(target.entity_id)
            if not contract or contract['policy'] != history['policy'] or target not in CONTRACTS.recipients(producer['actor'],producer['target'],producer['effect']):
                raise ValueError('lifetime ending differs from its actual recipient and policy')
            C.integer(history['started_at'],'ended lifetime start',0)
            C.integer(history['ended_at'],'ended lifetime end',history['started_at'])
            if history['started_at'] != history['policy']['started_at'] or history['ended_at'] > engine.elapsed_seconds:
                raise ValueError('lifetime ending clock mismatch')
            if history.get('state') not in ('ended','expired','consumed') or type(history.get('event')) is not dict or type(history['event'].get('kind')) is not str:
                raise ValueError('actual lifetime ending event required')
            deliveries = history['deliveries']
            limit = history['policy'].get('repeat', {}).get('times', 0)
            if len(deliveries) > limit or (history['state'] == 'consumed' and len(deliveries) != limit):
                raise ValueError('ended lifetime repetition count mismatch')
            _validate_deliveries(engine,producer['actor'],target,history['source'],history['policy'],deliveries)
        for record in TIME.records(target):
            if KEY not in record:
                continue
            actor = record.get('lifetime_actor')
            if actor is None or index.get(actor.entity_id) is not actor or record.get('lifetime_target') is not target:
                raise ValueError('lifetime actors must resolve to their actual participants')
            receipt = record.get('effect_receipt')
            try:
                row = getattr(engine, '_effect_dispatch_receipts', {}).get(receipt)
            except TypeError:
                raise ValueError('opaque lifetime producer receipt required')
            if not row or row.get('status') != 'completed':
                raise ValueError('lifetime requires a completed producer receipt')
            CONTRACTS.validate_receipt(engine, receipt, record['source'], record['effect_occurrence'],
                                      row['actor'], row['target'], row['effect'])
            if row['actor'] is not actor or target not in CONTRACTS.recipients(row['actor'], row['target'], row['effect']):
                raise ValueError('lifetime recipient differs from the producer receipt')
            if record['source'] in engine.r.selection.units and engine.r._selected_rule(record['source']) != record['source']:
                raise ValueError('lifetime source selection changed')
            plan = record[KEY]
            if plan['declaration'] != {k: row['effect'][k] for k in CONTROLS if k in row['effect']}:
                raise ValueError('lifetime declaration differs from its actual producer')
            C.integer(plan['started_at'], 'lifetime start', 0)
            if plan['started_at'] > engine.elapsed_seconds:
                raise ValueError('lifetime cannot start in the future')
            contribution = {k: record[k] for k in ('accuracy_modifier','evasion_modifier','damage_reduction','save_modifier',
                                                    'statuses','initiative_zero','initiative_operation','type_operation','forbidden_actions','pledge_rainbow') if k in record}
            contract = row.get('lifetime_contracts', {}).get(target.entity_id)
            if contract != {'policy': plan, 'contribution': contribution} or record.get('timing_text') != plan['declaration']:
                raise ValueError('lifetime policy differs from its declared clocks and payload')
            deliveries = record['lifetime_deliveries']
            if (deliveries and 'repeat' not in plan) or len(deliveries) > plan.get('repeat', {}).get('times', float('inf')):
                raise ValueError('consumed lifetime cannot remain live')
            _validate_deliveries(engine,actor,target,record['source'],plan,deliveries)
    import pledge_state as PLEDGE
    PLEDGE.validate_world(engine,index)
    import directive_features as DIRECTIVES
    DIRECTIVES.validate_world(engine, index)
    return True


def _validate_deliveries(engine, actor, target, source, plan, deliveries):
    import effect_contracts as CONTRACTS
    tokens = set()
    for delivery in deliveries:
        token = (delivery['event'], delivery['token'])
        if token in tokens:
            raise ValueError('repeated lifetime boundary receipt')
        tokens.add(token)
        child = engine._effect_dispatch_receipts.get(delivery['receipt'])
        if not child or child['actor'] is not actor or child['target'] is not target or child['effect'] != plan.get('repeat_effect'):
            raise ValueError('repeat needs its actual consequence receipt')
        CONTRACTS.validate_receipt(engine,delivery['receipt'],source,child['occurrence'],actor,target,child['effect'])
        if child.get('status')!='completed':
            import clock_invocations as CLOCK
            if (child.get('status') not in ('condition_unknown','awaiting_input')
                    or delivery is not deliveries[-1] or not CLOCK.owns_delivery(engine,target,delivery)):
                raise ValueError('pending repeat requires its actual waiting clock')

