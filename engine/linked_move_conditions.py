"""Move conditions that consume their actual applying actor or holder turns."""
from copy import deepcopy
import common_checks as C
import condition_instances as CONDITIONS
import effect_instances as E
import world_entities as W

OPERATIONS = {'seed_drain', 'perish_count', 'known_move_lock'}
PERISH = 'move/멸망의노래'


def owns(row):
    return row.get('payload', row.get('effect', {})).get('operation') in OPERATIONS


def _semantic(effect):
    result = {k: v for k, v in effect.items() if not k.startswith('_')}
    if result.get('on') == 'all including self': result['on'] = 'target'
    return result


def project(engine, move, mechanics):
    if move['id'] != PERISH: return mechanics
    import custom_condition_effects as CUSTOM
    row = CUSTOM.definition(engine.r, move['id'])
    if row is None or not owns(row): raise ValueError('reviewed Perish Song policy required')
    result = deepcopy(mechanics)
    result['effects_exec'] = [_semantic(effect) for effect in result.get('effects_exec', [])]
    return result


def prepare(engine, actor, target, effect, source, row):
    W.require_actors(engine, actor, target)
    if _semantic(effect) != _semantic(row['raw']): raise ValueError('linked condition extraction changed')
    name = row['payload']['condition']
    old = CONDITIONS.records(target, name)
    if name in target.conditions and not old: raise ValueError('legacy condition needs explicit cure before sourced application')
    if any(r['source'] != source or r[E.KEY].get('applied_by_actor_id') != actor.entity_id for r in old):
        raise ValueError('overlapping linked conditions require an explicit source composition policy')
    return row


def _seed_immune(engine, actor, target, source):
    if '풀' in target.types: return True
    import effects as FX
    move = engine.r.move(source)
    _, _, _, immune, absorb = FX.passive_damage_mods(engine, actor, target, move, {})
    return bool(immune or absorb)


def grant(engine, actor, target, effect, source, row):
    name = row['payload']['condition']
    if CONDITIONS.records(target, name) or engine.immune_to(target, name): return False
    if row['payload']['operation'] == 'seed_drain' and _seed_immune(engine, actor, target, source): return False
    record = E.create(engine, target, kind='condition', source=source, payload=row['payload'],
        capacity={'bucket': 'condition:' + name, 'source': source},
        lifetime={'boundary': 'scene_end' if row['payload']['operation'] == 'known_move_lock' else 'condition_cure_or_volatile_end'},
        applied_by=actor)
    record.update(issued_turn=target.custom_conditions.get('combat_turn_serial', 0), applications=[])
    target.custom_conditions.setdefault(CONDITIONS.KEY, []).append(record)
    target.conditions.add(name)
    engine.time_actors([actor, target])
    validate_record(target, record, row=row)
    return True


def validate_record(actor, record, *, row, terminal=False):
    E.validate(record, actor=actor, terminal=terminal)
    payload = row['payload']; meta = record[E.KEY]; operation = payload['operation']
    if record['effect'] != payload or meta['kind'] != 'condition': raise ValueError('linked condition payload changed')
    boundary = 'scene_end' if operation == 'known_move_lock' else 'condition_cure_or_volatile_end'
    if meta['capacity'] != {'bucket': 'condition:' + payload['condition'], 'source': record['source']} or meta['lifetime'] != {'boundary': boundary}:
        raise ValueError('linked condition ownership or lifetime changed')
    E.text(meta.get('applied_by_actor_id'), 'actual condition applying actor')
    if not terminal and payload['condition'] not in actor.conditions: raise ValueError('linked condition projection missing')
    turn = C.integer(record.get('issued_turn'), 'condition issue turn', 0)
    at = record['at']
    applications = record.get('applications')
    if not isinstance(applications, list): raise ValueError('condition applications must be a list')
    if operation == 'known_move_lock' and applications: raise ValueError('move lock has no turn ticks')
    for index, event in enumerate(applications):
        turn = C.integer(event.get('turn'), 'actual holder turn', turn + 1, actor.custom_conditions.get('combat_turn_serial', 0))
        at = C.integer(event.get('at'), 'actual holder time', at)
        if event.get('holder_id') != actor.entity_id or event.get('kind') != operation: raise ValueError('actual linked holder event required')
        if operation == 'perish_count':
            if index > 2 or event.get('remaining') != 2 - index: raise ValueError('Perish countdown changed')
        elif operation == 'seed_drain':
            maximum = C.integer(event.get('maximum_hp'), 'actual maximum HP', 1)
            if event.get('requested') != maximum // 10: raise ValueError('seed drain amount changed')
            C.integer(event.get('lost'), 'actual seed HP loss', 0, event['requested'])
    if terminal and meta['end_event'].get('kind') != 'condition_cure': raise ValueError('actual linked condition cure required')
    return True


def turn_start(engine, actor, record):
    operation = record['effect']['operation']
    if operation == 'known_move_lock': return
    turn = actor.custom_conditions.get('combat_turn_serial', 0)
    applications = record['applications']
    last = applications[-1]['turn'] if applications else record['issued_turn']
    if turn <= last: return
    event = {'kind': operation, 'holder_id': actor.entity_id, 'turn': turn, 'at': engine.elapsed_seconds}
    if operation == 'perish_count':
        event['remaining'] = 2 - len(applications)
        applications.append(event)
        if event['remaining'] == 0:
            engine.lose_hp(actor, max(0, actor.hp), source=record['source'], unpreventable=True, loss_kind='hp_setting')
        return
    caster = W.actor_index(engine).get(record[E.KEY]['applied_by_actor_id'])
    if caster is None: raise ValueError('seed drain applying actor missing')
    maximum = actor.max_hp
    event.update(maximum_hp=maximum, requested=maximum // 10, lost=0)
    applications.append(event)
    before = actor.hp
    engine.lose_hp(actor, event['requested'], source=record['source'])
    lost = max(0, before - actor.hp)
    # Fainting archives a copy during lose_hp; finish that same event receipt.
    closed = next((r for r in actor.spec.get('effect_instance_history', []) if r['id'] == record['id']), None)
    (closed['applications'][-1] if closed is not None else event)['lost'] = lost
    if lost: engine.heal(caster, lost, source_kind='move')


def check_move(engine, actor, move_id):
    for record in CONDITIONS.records(actor):
        if record.get('effect', {}).get('operation') != 'known_move_lock': continue
        caster = W.actor_index(engine).get(record[E.KEY]['applied_by_actor_id'])
        if caster is None: raise ValueError('Imprison applying actor missing')
        if move_id in caster.moves: raise ValueError('봉인: 시전자가 현재 알고 있는 기술은 사용할 수 없습니다')


def end_scene(engine, actors):
    for actor in actors:
        for record in list(CONDITIONS.records(actor)):
            if record.get('effect', {}).get('operation') == 'known_move_lock':
                CONDITIONS.end(engine, actor, record, {'kind': 'condition_cure', 'condition': record['effect']['condition']})
