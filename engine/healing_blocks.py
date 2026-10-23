"""Source-owned blockers for HP, revival, and temporary-HP gains.

The condition instance remains the authoritative state.  This module supplies
the shared gain query and the explicit non-volatile boundaries; individual
Move adapters only declare their condition name, class, and lifetime.
"""
from copy import deepcopy
import effect_instances as E
import condition_instances as CONDITIONS


OPERATION = 'healing_gain_block'
CAPACITY = 'healing_gain_block'
EXPLICIT_BOUNDARIES = ('replacement', 'breather', 'encounter_end')


def is_definition(row):
    return isinstance(row, dict) and row.get('payload', {}).get('operation') == OPERATION


def is_record(record):
    return isinstance(record, dict) and record.get('effect', {}).get('operation') == OPERATION


def records(actor):
    return [record for record in CONDITIONS.records(actor) if is_record(record)]


def prepare(engine, actor, target, effect, source, row):
    """Validate the whole proposed contribution before any condition mutation."""
    import world_entities as W
    W.require_actors(engine, actor, target)
    if not is_definition(row):
        raise ValueError('healing gain block policy required')
    if {k: v for k, v in effect.items() if not k.startswith('_')} != row['raw']:
        raise ValueError('healing gain block extraction changed')
    payload = row['payload']
    if set(payload) != {'kind', 'condition', 'class', 'operation'}:
        raise ValueError('healing gain block payload shape changed')
    if payload['kind'] != 'custom_condition' or payload['operation'] != OPERATION:
        raise ValueError('healing gain block operation changed')
    if payload['class'] not in ('healing_block', 'volatile'):
        raise ValueError('healing gain block condition class changed')
    lifetime = row.get('lifetime')
    if payload['class'] == 'healing_block':
        expected = {'boundary': 'explicit_healing_block_end',
                    'ends_on': list(EXPLICIT_BOUNDARIES)}
    else:
        expected = {'boundary': 'condition_cure_or_volatile_end'}
    if lifetime != expected:
        raise ValueError('healing gain block lifetime changed')
    if row.get('recipient') not in ('effect_target', 'selected_primary'):
        raise ValueError('healing gain block recipient policy changed')
    if row['payload']['class'] == 'volatile' and row['recipient'] != 'selected_primary':
        raise ValueError('Psychic Noise requires its selected primary target')
    if row['payload']['class'] == 'healing_block' and row['recipient'] != 'effect_target':
        raise ValueError('Heal Block requires its actual effect target')
    same_name = CONDITIONS.records(target, payload['condition'])
    if payload['condition'] in target.conditions and not same_name:
        raise ValueError('legacy healing block requires explicit reconciliation')
    for record in records(target):
        validate_record(target, record)
    if sum(record['source'] == source for record in records(target)) > 1:
        raise ValueError('duplicate healing block source contribution')
    return row


def grant(engine, actor, target, effect, source, row):
    row = prepare(engine, actor, target, effect, source, row)
    if row['recipient'] == 'selected_primary':
        import move_activation as ACTIVATION
        scope = ACTIVATION.current_scope(engine, actor, target, source)
        # An ordinary single-target use has no group scope and its explicit
        # target is the selection.  A group carries the caller's actual
        # selected primary separately from iteration order.
        if scope is not None and scope.get('primary') is not target:
            return False
    if row['payload']['class'] == 'volatile' and target.fainted:
        # Damage is resolved before post-hit effects.  A volatile condition
        # cannot be reintroduced after that damage has already cured it.
        return False
    if any(record['source'] == source for record in records(target)):
        return False
    payload = row['payload']
    record = E.create(engine, target, kind='condition', source=source,
        payload=payload, capacity={'bucket': CAPACITY, 'source': source},
        lifetime=row['lifetime'], applied_by=actor)
    # All fallible policy checks happen above.  The append and presence
    # projection are the single authoritative condition commit.
    target.custom_conditions.setdefault(CONDITIONS.KEY, []).append(record)
    target.conditions.add(payload['condition'])
    engine.time_actors([actor, target])
    validate_record(target, record)
    engine.log('    '+target.name+': '+payload['condition']+' 회복 획득 차단', source)
    return True


def validate_record(actor, record, *, row=None, terminal=False):
    E.validate(record, actor=actor, terminal=terminal)
    if not is_record(record):
        raise ValueError('healing gain block record required')
    if row is None:
        import custom_condition_effects as CUSTOM
        row = CUSTOM.definition(actor.r, record['source'])
    if not is_definition(row) or record.get('effect') != row['payload']:
        raise ValueError('selected healing gain block state required')
    meta = record[E.KEY]
    if meta.get('kind') != 'condition':
        raise ValueError('healing gain block must use the condition family')
    if meta.get('capacity') != {'bucket': CAPACITY, 'source': record['source']}:
        raise ValueError('healing gain block capacity authority mismatch')
    if meta.get('lifetime') != row['lifetime']:
        raise ValueError('healing gain block lifetime authority mismatch')
    name = row['payload']['condition']
    if not terminal:
        if name not in actor.conditions:
            raise ValueError('healing gain block presence projection missing')
        if sum(peer['source'] == record['source'] for peer in records(actor)) != 1:
            raise ValueError('one live healing block per source required')
        return True
    event = meta.get('end_event', {})
    if row['payload']['class'] == 'volatile':
        if event != {'kind': 'condition_cure', 'condition': name}:
            raise ValueError('volatile healing block requires its actual condition cure')
    else:
        expected = {'kind': 'healing_block_boundary',
                    'boundary': event.get('boundary'), 'condition': name,
                    'source': record['source']}
        if event != expected or event.get('boundary') not in EXPLICIT_BOUNDARIES:
            raise ValueError('Heal Block requires replacement, Breather, or encounter end')
    return True


def blocked(actor):
    """Read-only query used by every native gain consumer."""
    live = records(actor)
    import custom_condition_effects as CUSTOM
    for record in live:
        CUSTOM.validate_record(actor, record)
    return bool(live)


def _preflight_end(engine, actor, record, event):
    """Mirror every fallible archive prerequisite before any record ends."""
    validate_record(actor, record)
    history = actor.spec.get('effect_instance_history', [])
    if not isinstance(history, list):
        raise ValueError('effect instance history must be a list')
    if any(not isinstance(row, dict) for row in history):
        raise ValueError('typed ended effect instance required')
    if any(row.get('id') == record['id'] for row in history):
        raise ValueError('effect instance already archived')
    memo = {id(value): value for value in getattr(engine, '_time_actors', [])}
    memo[id(actor)] = actor
    closed = deepcopy(record, memo)
    closed[E.KEY].update(state='expired', ended_at=engine.elapsed_seconds,
                         end_event=deepcopy(event))
    # E.archive and the condition family will run these exact terminal checks
    # during commit; execute them for every planned record first.
    CONDITIONS.validate_record(actor, closed, terminal=True)
    return True


def boundary(engine, actors, name):
    """End only contributions that explicitly own this actual boundary."""
    if name not in EXPLICIT_BOUNDARIES:
        raise ValueError('unknown healing block boundary')
    actors = tuple(dict.fromkeys(actors))
    planned = []
    for actor in actors:
        for record in records(actor):
            validate_record(actor, record)
            if name in record[E.KEY]['lifetime'].get('ends_on', []):
                condition = record['effect']['condition']
                event = {'kind': 'healing_block_boundary', 'boundary': name,
                         'condition': condition, 'source': record['source']}
                planned.append((actor, record, event))
    for actor, record, event in planned:
        _preflight_end(engine, actor, record, event)
    for actor, record, event in planned:
        CONDITIONS.end(engine, actor, record,
            event)
    return len(planned)
