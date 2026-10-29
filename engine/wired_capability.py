"""Core Wired: actual electronic devices/cords and device-specific GM permissions.

The existing remote-control state owns routes and boundaries. Observations here
describe physical electronics, a cord's current two endpoints and an explicit
GM move list; they grant no vehicle authority, learned slots or refreshes.
"""
from copy import deepcopy
from pathlib import Path
import json

import crafting_recipes as Q
import state_grants as G
import world_entities as W
from source_context import verified_source

SOURCE = 'capability/접속'
DEPENDENCY = 'core_wired'
PREFIX = 'core-wired:'


def policy():
    return json.loads((Path(__file__).resolve().parents[1]/'data/core-wired-native.json').read_text(encoding='utf8'))


def native():return deepcopy(policy()['declaration'])


def require_source(e):
    Q._selected(e, SOURCE)
    verified_source(e.r, policy()['source_reference'], label='core Wired')


def _remote():
    import control_remote as R
    return R


def _state(e, *, create=False):
    R = _remote(); state = R._state(e)
    if create:
        setattr(e, R.FIELD, state)
        return state.setdefault('wired', {'devices': {}, 'cords': {}, 'permissions': {}})
    return state.get('wired', {'devices': {}, 'cords': {}, 'permissions': {}})


def _object(e, uid):
    obj = getattr(e, '_physical_objects', {}).get(uid)
    if obj is None:raise ValueError('actual Wired physical device or cord required')
    W.require_usable_object(obj)
    if any(W.physical_lifecycle(obj)[key] for key in ('disabled', 'suppressed')):
        raise ValueError('actual Wired device or cord unavailable')
    return obj


def _observe(e, bucket, key, values, reason):
    Q._text(reason); require_source(e)
    def apply(staged, actor):
        R = _remote(); R.validate_world(staged, W.actor_index(staged))
        records = _state(staged, create=True)[bucket]; old = records.get(key)
        row = R._sign(dict(values, reason=reason, at=staged.elapsed_seconds,
            revision=1 if old is None else old['revision']+1))
        records[key] = row
        R.boundary(staged, 'wired_observation')
        staged.gm._rec('core Wired '+bucket, old, row, reason)
        return deepcopy(row)
    return G.transition(e, None, apply, include_rulings=True)


def observe_device(e, device_id, *, electronic, reason):
    Q._text(device_id); _object(e, device_id)
    if type(electronic) is not bool:raise ValueError('explicit actual electronic-device observation required')
    return _observe(e, 'devices', device_id, dict(device_id=device_id, electronic=electronic), reason)


def observe_cord(e, pokemon, device_id, cord_id, *, connected, reason):
    W.require_actors(e, pokemon)
    if pokemon.kind != 'pokemon':raise ValueError('actual Wired Pokemon required')
    for uid in (device_id, cord_id):Q._text(uid); _object(e, uid)
    if cord_id == device_id:raise ValueError('actual cord must be distinct from its electronic device')
    if type(connected) is not bool:raise ValueError('explicit actual physical cord connection required')
    return _observe(e, 'cords', cord_id, dict(operator_id=pokemon.entity_id,
        device_id=device_id, cord_id=cord_id, connected=connected), reason)


def _moves(e, values):
    if type(values) is not list:raise ValueError('explicit GM device move list required; empty list permits none')
    result = []
    for value in values:
        Q._text(value); mid = e.r.move_id(value)
        if mid is None or mid not in e.r.moves or not mid.startswith('move/') or e.r.move(mid).get('source') == 'weapon':
            raise ValueError('GM device permission requires actual ordinary catalog Moves')
        Q._selected(e, mid)
        if mid in result:raise ValueError('unique GM device Moves required')
        result.append(mid)
    return result


def allow_moves(e, device_id, moves, *, reason):
    Q._text(device_id); _object(e, device_id)
    row = _state(e)['devices'].get(device_id)
    if row is None or row['electronic'] is not True:raise ValueError('actual observed electronic device required')
    return _observe(e, 'permissions', device_id, dict(device_id=device_id, moves=_moves(e, moves)), reason)


def require_connection(e, operator, machine, links):
    require_source(e)
    if operator.kind != 'pokemon':raise ValueError('core Wired requires an actual Pokemon')
    import partial_entities as PARTIAL
    PARTIAL.require_complete(operator, 'core Wired')
    _object(e, machine['id'])
    state = _state(e); device = state['devices'].get(machine['id'])
    if device is None or device['electronic'] is not True:raise ValueError('actual observed electronic device required')
    cord_id = links['devices'][0]; _object(e, cord_id)
    cord = state['cords'].get(cord_id)
    if cord is None or cord['connected'] is not True or cord['operator_id'] != operator.entity_id or cord['device_id'] != machine['id']:
        raise ValueError('current actual physical cord endpoints required')


def _rotom(e, actor):
    from builder import species_lookup
    species = species_lookup(e.r, actor.spec.get('species'))
    Q._selected(e, species['id'])
    return species['id'] == 'pokemon/로토무'


def _desired(e):
    R = _remote(); desired = {}
    for route_id, route in R._state(e)['routes'].items():
        if route['policy']['dependency'] != DEPENDENCY or route['status'] != 'live':continue
        actor = W.actor_index(e).get(route['operator_id'])
        if actor is None or R._failure(e, route) is not None or not _rotom(e, actor):continue
        permission = _state(e)['permissions'].get(route['machine_id'])
        if permission is None or not permission['moves']:continue
        key = PREFIX+R._key(actor.entity_id, route_id)
        desired[key] = (actor, route_id, route['machine_id'], _moves(e, permission['moves']))
    return desired


def sync(e):
    """Withdraw only dependent permissions; keep the actor's native usage ledger."""
    desired = _desired(e)
    for actor in W.actor_index(e).values():
        sources = actor.spec.get('state_grants', {}).get('sources', {})
        for key, row in list(sources.items()):
            if key.startswith(PREFIX) and key not in desired:G.revoke(actor, key, engine=e)
    for key, (actor, route_id, device_id, moves) in desired.items():
        old = actor.spec.get('state_grants', {}).get('sources', {}).get(key)
        if old is not None and old['grants'].get('moves', []) != moves:G.revoke(actor, key, engine=e); old = None
        if old is None:
            G.grant_moves(actor, moves, key, 'effect', owner_id=actor.entity_id,
                lifetime='connection', rule_id=SOURCE, mode='permission')
            G.state(actor)['sources'][key]['wired_permission'] = {'route_id': route_id, 'device_id': device_id}


def _borrowed(actor, mid):
    ledger = actor.spec.get('state_grants', {})
    rows = [*ledger.get('sources', {}).items(),
        *((row['source_id'], row['record']) for row in ledger.get('ended_sources', []))]
    return any(key.startswith(PREFIX) and row.get('wired_permission')
        and row.get('move_mode') == 'permission' and row.get('rule_id') == SOURCE
        and mid in row.get('grants', {}).get('moves', []) for key, row in rows)


def require_native_move(e, actor, mid):
    if not _borrowed(actor, mid):return
    R = _remote()
    # Refresh before even a free/non-counting native use. A stale permission
    # never becomes an unknown learned move in owned_list after withdrawal.
    R.boundary(e, 'native_move')
    import move_state as M
    known = M.known(e.r, {'moves': M.owned_list(actor.spec, 'moves', actor.moves,rules=actor.r)})
    allowed = M.known(e.r, {'moves': G.effective(actor, 'moves')})
    if mid not in known and mid not in allowed:
        raise ValueError('Wired Move needs a current Rotom/device/GM/cord permission or independent learned source')


def use_move(e, actor, target, move_id, *, route_id, **options):
    """Use exactly a GM Move of this current actual electronic-device route."""
    R = _remote(); W.require_actors(e, actor, target); Q._text(route_id)
    mid = e.r.move_id(move_id)
    R.boundary(e, 'wired_move')
    row = R._state(e)['routes'].get(route_id)
    if row is None or row['policy']['dependency'] != DEPENDENCY:raise ValueError('actual core Wired route required')
    R.permission(e, actor, row['machine_id'], route_id)
    permission = _state(e)['permissions'].get(row['machine_id'])
    if not _rotom(e, actor) or permission is None or mid not in permission['moves']:
        raise ValueError('exact current Rotom GM device Move permission required')
    return e.use_move(actor, target, mid, **options)


def validate_world(e, index):
    state = _state(e); R = _remote(); Q._fields(state, ('devices', 'cords', 'permissions'))
    for bucket, rows in state.items():
        if type(rows) is not dict:raise ValueError('typed Wired observations required')
        for key, row in rows.items():
            Q._text(key); R._verify(row)
            fields = {'devices': ('device_id', 'electronic'),
                'cords': ('operator_id', 'device_id', 'cord_id', 'connected'),
                'permissions': ('device_id', 'moves')}[bucket]
            Q._fields(row, (*fields, 'reason', 'at', 'revision', 'sha256'))
            Q._text(row['reason'])
            import common_checks as C
            C.integer(row['at'], 'Wired observation time', 0, e.elapsed_seconds)
            C.integer(row['revision'], 'Wired observation revision', 1)
            if row['device_id'] not in getattr(e, '_physical_objects', {}):raise ValueError('actual Wired device identity required')
            if bucket == 'cords':
                if key != row['cord_id'] or row['operator_id'] not in index or row['cord_id'] not in getattr(e, '_physical_objects', {}) or row['cord_id'] == row['device_id']:
                    raise ValueError('actual distinct Wired cord and endpoints required')
                if type(row['connected']) is not bool:raise ValueError('typed Wired cord state required')
            elif key != row['device_id']:raise ValueError('Wired device identity changed')
            elif bucket == 'devices' and type(row['electronic']) is not bool:raise ValueError('typed electronic observation required')
            elif bucket == 'permissions' and _moves(e, row['moves']) != row['moves']:raise ValueError('canonical GM device Move IDs required')
    for actor in index.values():
        for key, row in actor.spec.get('state_grants', {}).get('sources', {}).items():
            if not key.startswith(PREFIX):continue
            marker = row.get('wired_permission', {})
            route = R._state(e)['routes'].get(marker.get('route_id'))
            if route is None or route['policy']['dependency'] != DEPENDENCY or route['operator_id'] != actor.entity_id or marker.get('device_id') != route['machine_id'] or key != PREFIX+R._key(actor.entity_id, marker.get('route_id')) or row.get('move_mode') != 'permission' or row.get('rule_id') != SOURCE or row.get('owner_id') != actor.entity_id or row.get('lifetime') != 'connection':
                raise ValueError('actual Wired permission provenance required')
            permission = state['permissions'].get(route['machine_id'])
            if permission is None or row['grants'].get('moves', []) != permission['moves']:
                raise ValueError('exact GM device move permission required')
            # Match the remote owner's existing validation/boundary split:
            # stale display state may precede refresh after a world observation;
            # it never authorizes native use without live revalidation.
    return True
