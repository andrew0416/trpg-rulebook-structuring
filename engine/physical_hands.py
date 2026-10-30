"""Observed hands for actually carried objects, separate from item benefits."""
from copy import deepcopy
import state_grants as G
import world_entities as W

KEY = 'physical_hand_objects'
HANDS = ('주요손', '반대손')


def entries(actor):
    rows = actor.spec.get(KEY, {})
    if type(rows) is not dict or set(rows) - set(HANDS):
        raise ValueError('actual main/off-hand object mapping required')
    for hand, row in rows.items():
        if (type(row) is not dict or set(row) != {'instance_id', 'reason'}
                or not isinstance(row['instance_id'], str) or not row['instance_id']
                or not isinstance(row['reason'], str) or not row['reason'].strip()):
            raise ValueError('hand observation requires an actual object and reason')
    if len({row['instance_id'] for row in rows.values()}) != len(rows):
        raise ValueError('one held object cannot occupy two separately observed hands')
    return rows


def occupied(actor):return set(entries(actor))


def release_removed(actor, retained_ids):
    rows = entries(actor)
    for hand in list(rows):
        if rows[hand]['instance_id'] not in retained_ids:del rows[hand]
    if not rows:actor.spec.pop(KEY, None)


def inspect(engine, actor, instance_id):
    W.require_actors(engine, actor)
    rows = entries(actor)
    hand = next((h for h, row in rows.items() if row['instance_id'] == instance_id), None)
    if hand is None:return None
    obj = getattr(engine, '_physical_objects', {}).get(instance_id)
    if not isinstance(obj, dict):raise ValueError('observed hand object is missing')
    W.require_physical_access(obj)
    __import__('environmental_item_state').require_usable(engine, obj)
    load = actor.spec.get('_carried_load', {})
    if (actor.kind != 'trainer' or obj.get('carrier_id') != actor.entity_id
            or obj.get('equipped_by') is not None or obj.get('telekinetic_holder_id') is not None
            or load.get('mode', 'physical') != 'physical'
            or load.get('blocked_actions') or load.get('failure_pending')
            or not any(row['id'] == instance_id and row['weight_kg'] == obj.get('weight_kg')
                       for row in load.get('objects', []))):
        raise ValueError('hand object must retain its actual resolved physical possession')
    equipped = [*getattr(actor, '_item_reg', {}).values(),
                *actor.custom_conditions.get('equipped_weapons', {}).values()]
    if any(hand in row.get('slots', ()) for row in equipped):
        raise ValueError('observed object and equipped item occupy the same hand')
    return {'hand': hand, 'instance_id': instance_id}


def observe(engine, actor, instance_id, *, hand, reason):
    """GM observation of an existing grip; does not pick up or equip anything."""
    W.require_actors(engine, actor)
    if hand not in HANDS or not isinstance(reason, str) or not reason.strip():
        raise ValueError('explicit hand and actual-world observation reason required')
    def apply(e, a):
        rows = entries(a)
        if hand in rows or any(r['instance_id'] == instance_id for r in rows.values()):
            raise ValueError('release the actual old grip before a new observation')
        before = deepcopy(rows)
        a.spec.setdefault(KEY, {})[hand] = {'instance_id': instance_id, 'reason': reason}
        result = inspect(e, a, instance_id)
        e.gm._rec('physical object in hand', before, entries(a), reason, a)
        return result
    return G.transition(engine, actor, apply)




def release(engine, actor, *, hand, reason):
    """GM observes a released grip; physical carrying and ownership remain."""
    W.require_actors(engine, actor)
    if hand not in HANDS or not isinstance(reason, str) or not reason.strip():
        raise ValueError('explicit actual grip-release observation required')
    def apply(e, a):
        rows = entries(a)
        if hand not in rows:raise ValueError('actual observed grip required')
        inspect(e, a, rows[hand]['instance_id'])
        before = deepcopy(rows)
        del rows[hand]
        if not rows:a.spec.pop(KEY, None)
        e.gm._rec('physical grip released', before, entries(a), reason, a)
    return G.transition(engine, actor, apply)
