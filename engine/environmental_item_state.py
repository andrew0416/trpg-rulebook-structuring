"""Observed physical-item use blocks, independent of equipment-benefit suppression.

The GM/source adapter owns exposure and the source's eligibility policy. This
module owns exact-instance block identity, selective recovery and admission.
It does not infer exposure from a hit or disable anonymous quantity inventory.
"""
from copy import deepcopy
import common_checks as C
import state_grants as G
import resolution_transaction as TX
import world_entities as W

FIELD = 'environmental_use_blocks'
ENDS = {'frozen': 'thaw', 'electrical_failure': 'repair'}
# ch07:25 defines a ten-second round; ch07:538 specifies three rounds.
RECOVERY_SECONDS = 30


def _signed(row):
    return dict(row, sha256=TX.request_fingerprint(row))


def _blocks(obj):
    rows = obj.get(FIELD, {})
    if type(rows) is not dict:
        raise ValueError('environmental item blocks must preserve event identity')
    for event_id, row in rows.items():
        if type(row) is not dict or set(row) - {'recovery'} != {
                'event_id', 'instance_id', 'item_rule_id', 'holder_id', 'condition',
                'source', 'reason', 'exposed', 'at', 'released', 'sha256'}:
            raise ValueError('environmental item evidence is malformed')
        if row['sha256'] != TX.request_fingerprint({k: v for k, v in row.items() if k != 'sha256'}):
            raise ValueError('environmental item evidence changed')
        if (row['event_id'] != event_id or row['instance_id'] != obj.get('id')
                or row['item_rule_id'] != obj.get('item_rule_id')
                or row['condition'] not in ENDS or type(row['exposed']) is not bool):
            raise ValueError('environmental block belongs to a different item or condition')
        for key in ('event_id', 'holder_id', 'source', 'reason'):
            G._text(row[key], 'environmental item ' + key)
        C.integer(row['at'], 'observed environmental item time', 0)
        policy = row.get('recovery')
        if policy is not None:
            if row['condition'] != 'electrical_failure' or type(policy) is not dict:
                raise ValueError('automatic recovery requires electrical failure')
            if policy.get('kind') == 'scene':
                if set(policy) != {'kind'}:
                    raise ValueError('scene recovery has no invented clock')
            elif policy.get('kind') == 'three_rounds':
                if not row['exposed'] and set(policy) == {'kind'}:
                    pass
                else:
                    expected = {'kind'}
                    if 'elapsed_anchor' in policy:
                        expected.add('elapsed_anchor')
                        if policy['elapsed_anchor'] is not None:
                            C.integer(policy['elapsed_anchor'], 'known recovery time anchor', row['at'])
                    if 'observed_offset' in policy:
                        expected.add('observed_offset')
                        C.integer(policy['observed_offset'], 'observed recovery round offset', 0, 10)
                        if policy.get('elapsed_anchor') != row['at'] or 'started_round' not in policy:
                            raise ValueError('explicit failure timestamp lost its combat origin')
                    if 'started_round' in policy:
                        expected |= {'started_round', 'deadline_round', 'count'}
                        C.integer(policy['started_round'], 'electrical failure round', 1)
                        C.integer(policy['count'], 'electrical failure initiative count')
                        if policy['deadline_round'] != policy['started_round'] + 3:
                            raise ValueError('shielded electronic tool recovery is three rounds')
                    if 'deadline_seconds' in policy:
                        expected.add('deadline_seconds')
                        C.integer(policy['deadline_seconds'], 'electrical recovery deadline', 0)
                        if policy.get('elapsed_anchor') is None or policy['deadline_seconds'] != policy['elapsed_anchor'] + RECOVERY_SECONDS:
                            raise ValueError('electrical recovery must retain its original elapsed deadline')
                        if 'started_round' in policy:
                            expected.add('combat_exit_at')
                            C.integer(policy.get('combat_exit_at'), 'electrical recovery combat exit', row['at'])
                    if set(policy) != expected or expected == {'kind'}:
                        raise ValueError('electronic recovery needs its actual clock deadline')
            else:
                raise ValueError('unsupported electrical recovery policy')
        released = row['released']
        if released is not None:
            if type(released) is not dict or set(released) != {'end', 'reason', 'at'}:
                raise ValueError('environmental item recovery evidence is malformed')
            allowed = {ENDS[row['condition']]}
            if policy is not None:allowed.add(policy['kind'])
            if not row['exposed'] or released['end'] not in allowed:
                raise ValueError('environmental item recovery does not end this condition')
            G._text(released['reason'], 'observed environmental recovery')
            C.integer(released['at'], 'environmental recovery time', row['at'])
    return rows


def _target(engine, holder, instance_id):
    W.require_actors(engine, holder)
    G._text(instance_id, 'physical item identity')
    obj = getattr(engine, '_physical_objects', {}).get(instance_id)
    if not isinstance(obj, dict) or obj.get('kind') != 'item_instance':
        raise ValueError('environmental effects need an actual registered physical item')
    W.require_usable_object(obj)
    if holder.entity_id not in (obj.get('owner_id'), obj.get('carrier_id'), obj.get('equipped_by')):
        raise ValueError('environmental observation needs the actual item holder/owner')
    _blocks(obj)
    return obj


def observe(engine, holder, instance_id, *, event_id, condition, source, reason, exposed=False,
            recovery=None, round_offset_seconds=None):
    """Record explicit GM/source observation; unobserved exposure stays protected."""
    for value, label in ((event_id, 'event'), (source, 'source'), (reason, 'reason')):
        G._text(value, 'environmental item ' + label)
    if condition not in ENDS or type(exposed) is not bool:
        raise ValueError('explicit supported environmental condition and exposure required')
    if recovery not in (None, 'scene', 'three_rounds') or recovery and condition != 'electrical_failure':
        raise ValueError('automatic lifetime belongs to an electrical failure source')
    if round_offset_seconds is not None:
        C.integer(round_offset_seconds, 'environmental round offset', 0, 10)
        if recovery != 'three_rounds' or not exposed:
            raise ValueError('timestamp belongs to an exposed three-round failure')

    def apply(staged, actual):
        obj = _target(staged, actual, instance_id)
        payload = dict(event_id=event_id, instance_id=instance_id,
                       item_rule_id=obj['item_rule_id'], holder_id=actual.entity_id,
                       condition=condition, source=source, reason=reason, exposed=exposed)
        rows = _blocks(obj)
        if event_id in rows:
            if (any(rows[event_id][key] != value for key, value in payload.items())
                    or (rows[event_id].get('recovery') or {}).get('kind') != recovery
                    or (rows[event_id].get('recovery') or {}).get('observed_offset') != round_offset_seconds):
                raise ValueError('environmental event identity cannot change its observation')
            return deepcopy(rows[event_id])
        if recovery is not None:
            policy = dict(kind=recovery)
            if recovery == 'three_rounds' and exposed:
                import combat_timing as TIMING
                if round_offset_seconds is not None:
                    staged.at_round_offset(round_offset_seconds)
                    policy['observed_offset'] = round_offset_seconds
                if staged.encounter_active:
                    if staged.round_start_seconds is None:
                        raise ValueError('three-round tool recovery needs the actual combat clock')
                    policy.update(started_round=staged.round_no, deadline_round=staged.round_no + 3,
                                  count=TIMING.current(staged),
                                  elapsed_anchor=staged.elapsed_seconds if round_offset_seconds is not None else None)
                else:
                    policy['elapsed_anchor'] = staged.elapsed_seconds
                    policy['deadline_seconds'] = staged.elapsed_seconds + RECOVERY_SECONDS
            payload['recovery'] = policy
        row = _signed(dict(payload, at=staged.elapsed_seconds, released=None))
        obj.setdefault(FIELD, {})[event_id] = row
        return deepcopy(row)
    return G.transition(engine, holder, apply)


def recover(engine, holder, instance_id, *, event_id, end, reason):
    """End just the selected observed condition; never clear another source."""
    G._text(reason, 'actual environmental item recovery')

    def apply(staged, actual):
        obj = _target(staged, actual, instance_id)
        row = _blocks(obj).get(event_id)
        if row is None or not row['exposed'] or end != ENDS[row['condition']]:
            raise ValueError('actual matching environmental item recovery required')
        if row['released'] is not None:
            return deepcopy(row)
        _release(staged, obj, event_id, end, reason)
        return deepcopy(obj[FIELD][event_id])
    return G.transition(engine, holder, apply)


def require_usable(engine, obj):
    """Native stock consumers must check the exact object before any payment."""
    W.require_usable_object(obj)
    if getattr(engine, '_physical_objects', {}).get(obj.get('id')) is not obj:
        raise ValueError('environmental admission requires the actual registered item')
    if active(obj):
        raise ValueError('physical item is environmentally unusable until its actual recovery')


def active(obj, condition=None):
    return any(row['exposed'] and row['released'] is None
               and (condition is None or row['condition'] == condition)
               for row in _blocks(obj).values())


def _release(engine, obj, event_id, end, reason):
    row = {k: v for k, v in obj[FIELD][event_id].items() if k != 'sha256'}
    row['released'] = dict(end=end, reason=reason, at=engine.elapsed_seconds)
    obj[FIELD][event_id] = _signed(row)


def repaired(engine, obj):
    """Called only after the native repair succeeds; thaw is a different recovery."""
    for event_id, row in list(_blocks(obj).items()):
        if row['condition'] == 'electrical_failure' and row['exposed'] and row['released'] is None:
            _release(engine, obj, event_id, 'repair', 'completed native physical-item repair')


def boundary(engine, *, count=None, round_end=False, scene_end=False,
             time_advanced=False, encounter_end=False):
    """Consume native world boundaries inside their existing atomic transaction."""
    for obj in getattr(engine, '_physical_objects', {}).values():
        for event_id, row in list(_blocks(obj).items()):
            policy = row.get('recovery')
            if not policy or not row['exposed'] or row['released'] is not None:
                continue
            due = policy['kind'] == 'scene' and scene_end
            if policy['kind'] == 'three_rounds':
                if (round_end and policy.get('started_round') == engine.round_no
                        and policy.get('elapsed_anchor') is None and 'deadline_seconds' not in policy):
                    row = deepcopy(row)
                    row['recovery']['elapsed_anchor'] = engine.round_start_seconds + 10
                    obj[FIELD][event_id] = _signed({k:v for k,v in row.items() if k != 'sha256'})
                    policy = row['recovery']
                if encounter_end and 'deadline_seconds' not in policy:
                    # Keep the observation and credit only known elapsed time.
                    # The native exit does not invent a partial round's duration.
                    row = deepcopy(row)
                    anchor = policy.get('elapsed_anchor')
                    if anchor is None:anchor = engine.elapsed_seconds
                    row['recovery'].update(elapsed_anchor=anchor, deadline_seconds=anchor + RECOVERY_SECONDS,
                                           combat_exit_at=engine.elapsed_seconds)
                    obj[FIELD][event_id] = _signed({k:v for k,v in row.items() if k != 'sha256'})
                    policy = row['recovery']
                if 'deadline_seconds' in policy:
                    due = ((time_advanced or encounter_end)
                           and engine.elapsed_seconds >= policy['deadline_seconds'])
                else:
                    deadline = policy['deadline_round']
                    due = (count is not None and (engine.round_no > deadline
                           or engine.round_no == deadline and count <= policy['count'])
                           or round_end and engine.round_no >= deadline)
            if due:
                _release(engine, obj, event_id, policy['kind'], 'actual native recovery boundary')


def next_interval(engine, end_at):
    """Stop the shared world clock at the actual item recovery instant."""
    next_at = end_at
    for obj in getattr(engine, '_physical_objects', {}).values():
        for row in _blocks(obj).values():
            deadline = (row.get('recovery') or {}).get('deadline_seconds')
            if row['exposed'] and row['released'] is None and deadline is not None:
                if engine.elapsed_seconds < deadline < next_at:
                    next_at = deadline
    return next_at - engine.elapsed_seconds


def validate_world(engine, index=None):
    import environmental_attacks as ATTACKS
    ATTACKS.validate_world(engine)
    for obj in getattr(engine, '_physical_objects', {}).values():
        if FIELD in obj:
            if obj.get('kind') != 'item_instance':
                raise ValueError('environmental item state requires an item instance')
            rows = _blocks(obj)
            if W.physical_lifecycle(obj)['consumed'] and any(
                    row['exposed'] and row['released'] is None for row in rows.values()):
                raise ValueError('unusable environmental item cannot have been consumed')
