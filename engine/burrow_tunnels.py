"""Actual dug passage geometry, shared by native walking and body placement.

Old size/path-only history remains history; it cannot invent missing entrances
or a body footprint. New passages outlive their maker and keep creation size.
"""
from copy import copy, deepcopy
import common_checks as C
import body_state as BODY

SOURCE = 'capability/burrow'
SIZES = {
    '소형': 1, 'Small': 1, 'small': 1,
    '중형': 2, 'Medium': 2, 'medium': 2,
    '대형': 3, 'Large': 3, 'large': 3,
    '거대': 4, '거대형': 4, 'Huge': 4, 'huge': 4,
    '초거대': 5, '초거대형': 5, 'Gigantic': 5, 'gigantic': 5,
}


def validate(engine):
    rows = getattr(engine, '_burrow_tunnels', [])
    if type(rows) is not list:
        raise ValueError('actual burrow tunnel history required')
    import map_terrain as T
    for row in rows:
        if type(row) is not dict:
            raise ValueError('identified burrow tunnel record required')
        passage = row.get('passage')
        if passage is None:
            continue  # Never upgrade old history by guessing its geometry.
        if type(passage) is not dict or set(passage) != {'source', 'offsets', 'entries', 'map_id', 'map_size'} or passage['source'] != SOURCE:
            raise ValueError('sourced tunnel footprint and entrances required')
        if type(passage['map_id']) is not str or not passage['map_id'].strip():
            raise ValueError('actual creation map identity required')
        size = passage['map_size']
        if type(size) not in (list, tuple) or len(size) != 2:
            raise ValueError('actual creation map dimensions required')
        width, height = (C.integer(v, 'creation map size', 1) for v in size)
        if row.get('body_size') not in SIZES or type(row.get('actor')) is not str or not row['actor']:
            raise ValueError('actual tunnel maker and creation size required')
        C.integer(row.get('round'), 'tunnel creation round', 0)
        path = row.get('path')
        if type(path) not in (list, tuple) or len(path) < 2:
            raise ValueError('actual dug path required')
        path = [T.point(p) for p in path]
        if any(T.cheb(a, b) != 1 for a, b in zip(path, path[1:])):
            raise ValueError('continuous actual dug path required')
        offsets = passage['offsets']
        if type(offsets) not in (list, tuple) or not offsets:
            raise ValueError('actual tunnel body offsets required')
        offsets = [tuple(C.integer(v, 'tunnel body offset') for v in p) for p in offsets]
        if any(len(p) != 2 for p in offsets) or (0, 0) not in offsets or len(set(offsets)) != len(offsets):
            raise ValueError('distinct tunnel footprint including anchor required')
        entries = passage['entries']
        if type(entries) not in (list, tuple) or any(T.point(p) not in (path[0], path[-1]) for p in entries):
            raise ValueError('actual surface tunnel entrances required')
        if any(not (0 <= x+dx < width and 0 <= y+dy < height) for x,y in path for dx,dy in offsets):
            raise ValueError('dug passage must remain on its actual map')


def record(engine, actor, plan, *, surface):
    shape = BODY.offsets(actor)
    row = {'actor': actor.entity_id, 'path': deepcopy(plan['path']),
           'body_size': actor.spec['size'], 'round': engine.round_no}
    # Unsupported/unknown imported body categories retain only their old history.
    map_id = getattr(engine.grid, '_tunnel_map_id', None)
    if shape is not None and actor.spec['size'] in SIZES and map_id is not None:
        entries = [] if plan['origin_underground'] else [plan['path'][0]]
        if surface:
            entries.append(plan['path'][-1])
        row['passage'] = {'source': SOURCE, 'offsets': deepcopy(shape), 'entries': entries,
                          'map_id': map_id, 'map_size': [engine.grid.w, engine.grid.h]}
    engine.__dict__.setdefault('_burrow_tunnels', []).append(row)
    validate(engine)
    return row


def _geometry(engine, actor):
    if engine.grid is None or actor.spec.get('size') not in SIZES:
        return set(), set()
    shape = BODY.offsets(actor)
    if shape is None:
        return set(), set()
    validate(engine)
    holes, entries = set(), set()
    for row in getattr(engine, '_burrow_tunnels', []):
        passage = row.get('passage')
        if (passage is None or passage['map_id'] != getattr(engine.grid, '_tunnel_map_id', None)
                or SIZES[actor.spec['size']] > SIZES[row['body_size']]):
            continue
        if not set(shape) <= {tuple(p) for p in passage['offsets']}:
            continue
        offsets = passage['offsets']
        holes.update((x+dx, y+dy) for x,y in row['path'] for dx,dy in offsets)
        entries.update((x+dx, y+dy) for x,y in passage['entries'] for dx,dy in offsets)
    return holes, entries


def can_pass(engine, actor, position):
    import map_terrain as T
    holes, entries = _geometry(engine, actor)
    if engine.grid is None:
        return False
    destination = {p for p in BODY.at_position(actor, position) if T.base_at(engine.grid, p) == 'earth'}
    if not destination or not destination <= holes:
        return False
    old = BODY.at_position(actor, actor.pos)
    old_earth = {p for p in old if T.base_at(engine.grid, p) == 'earth'}
    return old_earth <= holes if old_earth else bool(old & entries)


def can_exit(engine, actor, position):
    import map_terrain as T
    holes, entries = _geometry(engine, actor)
    if engine.grid is None:
        return False
    destination = BODY.at_position(actor, position)
    old_earth = {p for p in BODY.at_position(actor, actor.pos) if T.base_at(engine.grid, p) == 'earth'}
    return bool(destination) and destination <= entries and old_earth <= holes


def plane(engine, actor, position):
    """The same destination plane for collision checks and actual traversal."""
    if can_pass(engine, actor, position):
        return True
    state = actor.spec.get('_burrow', {})
    if state.get('underground') and can_exit(engine, actor, position):
        return False
    return bool(state.get('underground'))


def enter(engine, actor, mode):
    if mode not in ('land', '육상'):
        return
    state = actor.spec.get('_burrow', {})
    if can_pass(engine, actor, actor.pos):
        actor.spec.setdefault('_burrow', {}).update(underground=True, via_tunnel=True)
    elif state.get('underground') and can_exit(engine, actor, actor.pos):
        state.update(underground=False, via_tunnel=False)


def at_origin(engine, actor, position):
    """A read-only planning body follows the same surface/tunnel plane."""
    if position == actor.pos:
        return actor
    probe = copy(actor)
    probe.pos = position
    probe.spec = dict(actor.spec)
    probe.spec['_burrow'] = dict(actor.spec.get('_burrow', {}), underground=plane(engine, actor, position))
    return probe
