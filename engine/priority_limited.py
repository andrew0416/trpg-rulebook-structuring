"""Common Priority (Limited) reservation over the native action budget.

The action happens between turns.  Its declared token is reserved as a
next-turn loss, while the actor keeps the other actions for its initiative.
"""
from copy import deepcopy

import action_resources as RESOURCES
import common_checks as C
import world_entities as WORLD
from action_metadata import ActionCost


KEY = '_priority_limited_receipts'
SOURCE = 'input/ch07-combat.md:65-68'


def _scope(engine):
    return (C.integer(getattr(engine, '_party_encounter_epoch', 0), 'encounter epoch', 0),
            C.integer(engine.round_no, 'combat round', 1))


def records(actor):
    value = actor.custom_conditions.get(KEY, [])
    if type(value) is not list:
        raise ValueError('Priority Limited receipts must be a list')
    return value


def _cost(action):
    if type(action) is ActionCost:
        return list(action.components), {kind: 1 for kind in action.components}
    if type(action) is not str or action not in RESOURCES.KINDS:
        raise ValueError('Priority Limited requires a supported action cost')
    return action, {action: 1}


def preflight(engine, actor, *, action='standard', source):
    """Require a legal between-turn declaration without mutating its budget."""
    WORLD.require_actors(engine, actor)
    if actor.kind != 'trainer':
        raise ValueError('this Priority Limited order requires an actual trainer')
    declared, funded = _cost(action)
    if type(source) is not str or not source.strip() or engine.r._selected_rule(source) != source:
        raise ValueError('selected Priority Limited source required')
    if not engine.encounter_active or engine.round_start_seconds is None:
        raise ValueError('Priority Limited requires an open combat round')
    if engine._active_turn_actor is not None:
        raise ValueError('Priority actions must be declared between turns')
    if engine._ordinary_turn_rounds.get(actor) == engine.round_no:
        raise ValueError('ordinary turn already taken this round')
    if actor.dead or actor.fainted or actor.hp <= 0:
        raise ValueError('conscious Priority Limited actor required')
    if actor.conditions.intersection({'잠듦', '얼음', '완전 실명'}):
        raise ValueError('current condition prevents this Priority action')
    current = [row for row in records(actor)
               if tuple(row['scope']) == _scope(engine) and row['payment']['phase'] == 'reserved']
    if current:
        raise ValueError('this actor already reserved a Priority Limited action this round')
    RESOURCES.plan_debt(actor, funded)
    return {'scope': list(_scope(engine)), 'action': declared, 'funded': funded, 'source': source}


def reserve(engine, actor, *, action='standard', source, subject, communication=None):
    """Reserve one declared activation's costs with source/target evidence."""
    plan = preflight(engine, actor, action=action, source=source)
    if type(subject) is not str or not subject.strip():
        raise ValueError('Priority Limited subject identity required')
    if communication is not None and (type(communication) is not dict or communication.get('status') != 'delivered'):
        raise ValueError('delivered communication evidence required')
    sequence = len(records(actor)) + 1
    receipt = {
        'id': 'priority-limited:' + actor.entity_id + ':' + str(sequence),
        'actor_id': actor.entity_id,
        'subject_id': subject,
        'source': source,
        'priority_source': SOURCE,
        'scope': plan['scope'],
        'kind': 'priority_limited',
        'payment': {'declared': plan['action'], 'funded': plan['funded'], 'phase': 'reserved'},
        'communication': deepcopy(communication),
    }
    RESOURCES.schedule(actor, plan['funded'])
    actor.custom_conditions.setdefault(KEY, []).append(receipt)
    engine.log('  ' + actor.name + ': Priority (Limited) ' + str(action) + ' reserved', SOURCE)
    return receipt


def settle(engine, actor, owed):
    """Mark the single reserved receipt paid when reset consumes its debt."""
    epoch = getattr(engine, '_party_encounter_epoch', 0)
    pending = [row for row in records(actor)
               if row['payment']['phase'] == 'reserved' and row['scope'][0] == epoch]
    if not pending:
        return
    if len(pending) != 1 or pending[0]['payment']['funded'] != owed:
        raise ValueError('Priority Limited receipt differs from the actual action loss')
    row = pending[0]
    row['payment'].update(phase='paid', paid_round=engine.round_no,
                          paid_turn=actor.custom_conditions.get('combat_turn_serial', 0))


def validate(actor):
    seen = set()
    for row in records(actor):
        required = {'id','actor_id','subject_id','source','priority_source','scope','kind','payment','communication'}
        if set(row) != required or row['id'] in seen or row['actor_id'] != actor.entity_id:
            raise ValueError('invalid Priority Limited receipt identity')
        seen.add(row['id'])
        if row['priority_source'] != SOURCE or row['kind'] != 'priority_limited':
            raise ValueError('invalid Priority Limited source contract')
        if type(row['scope']) is not list or len(row['scope']) != 2 or any(type(v) is not int or v < 0 for v in row['scope']):
            raise ValueError('invalid Priority Limited combat scope')
        payment = row['payment']
        action=payment.get('declared')
        _,funded=_cost(ActionCost(tuple(action)) if type(action) is list else action)
        if payment.get('funded') != funded or payment.get('phase') not in ('reserved','paid'):
            raise ValueError('invalid Priority Limited payment')
        if payment['phase'] == 'paid':
            if set(payment) != {'declared','funded','phase','paid_round','paid_turn'}:
                raise ValueError('paid Priority Limited receipt lacks its turn')
        elif set(payment) != {'declared','funded','phase'}:
            raise ValueError('reserved Priority Limited receipt has unsupported fields')
        if row['communication'] is not None and (type(row['communication']) is not dict or row['communication'].get('status') != 'delivered'):
            raise ValueError('Priority Limited receipt lacks delivered communication')
    return True
