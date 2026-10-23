"""Explicit optional effects, sharing the native Move activation and scene clock.

Projection is read-only. A native activation owns its one receipt; on-hit modes
commit only at resolution. Multi-target projections reuse that same receipt.
"""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import hashlib
import json

KEY = 'optional_move_modes'
POLICY = 'data/optional-move-modes.json'


@lru_cache(maxsize=8)
def _read_policy(path, policy_stamp):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or data.get('contract') != 'explicit_scene_move_effect':
        raise ValueError('optional Move policy identity changed')
    return data


@lru_cache(maxsize=16)
def _source_digest(path, stamp):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def policy(rules):
    path = Path(__file__).resolve().parents[1]/POLICY
    if not path.exists(): path = Path(rules.root)/POLICY
    data = _read_policy(str(path), (path.stat().st_mtime_ns, path.stat().st_size))
    for name, digest in data['source_files'].items():
        source = Path(rules.root)/name
        stamp = (source.stat().st_mtime_ns, source.stat().st_size)
        if _source_digest(str(source), stamp) != digest:
            raise ValueError('optional Move source anchor changed: '+name)
    return data


def definition(rules, mid):
    row = policy(rules)['moves'].get(mid)
    if row is None: return None
    if rules._selected_rule(mid) != mid:
        raise ValueError('optional Move selected source changed')
    move = rules.move(mid)
    if ({k: move.get(k) for k in row['native_move']} != row['native_move']
            or rules.move_mech(mid)[0] != row['native_mechanics']):
        raise ValueError('optional Move definition changed from reviewed source')
    return row


def scene(actor):
    import frequency
    return frequency.state(actor)['scene']


def history(actor):
    return actor.spec.get(KEY, {}).get('history', [])


def validate_actor(actor):
    state = actor.spec.get(KEY)
    if state is None: return True
    if (actor.spec.get('kind') not in ('pokemon', 'trainer') or not isinstance(state, dict)
            or set(state) != {'version', 'history'} or state['version'] != 1
            or not isinstance(state['history'], list)):
        raise ValueError('optional Move history needs an actual actor owner')
    seen = set()
    for record in history(actor):
        if not isinstance(record, dict) or set(record) != {
                'id', 'actor_id', 'move_id', 'clause_id', 'source_row_sha256',
                'scene', 'selected_at', 'reason', 'use'}:
            raise ValueError('optional Move receipt shape changed')
        row = definition(actor.r, record['move_id'])
        if (row is None or record['actor_id'] != actor.entity_id
                or record['clause_id'] != row['clause_id']
                or record['source_row_sha256'] != row['source_row_sha256']):
            raise ValueError('optional Move receipt ownership or provenance changed')
        identity = (record['move_id'], record['scene'])
        if (type(record['scene']) is not int or not 0 <= record['scene'] <= scene(actor)
                or identity in seen):
            raise ValueError('optional Move scene budget changed')
        seen.add(identity)
        expected = f'optional:{actor.entity_id}:{record["move_id"]}:{record["scene"]}'
        if record['id'] != expected or not isinstance(record['reason'], str) or not record['reason'].strip():
            raise ValueError('optional Move choice identity or reason invalid')
        if type(record['selected_at']) is not int or record['selected_at'] < 0:
            raise ValueError('optional Move selection time invalid')
        use = record['use']
        if use is not None:
            if (not isinstance(use, dict) or set(use) != {'at', 'boundary', 'target_ids'}
                    or use['boundary'] != row['consume'] or type(use['at']) is not int
                    or use['at'] < record['selected_at']):
                raise ValueError('optional Move use boundary changed')
            ids = use['target_ids']
            if (not isinstance(ids, list) or not ids
                    or any(not isinstance(uid, str) or not uid for uid in ids)
                    or len(set(ids)) != len(ids)):
                raise ValueError('optional Move actual target identities required')
    return True


def validate_world(engine, index):
    for actor in index.values():
        validate_actor(actor)
        for record in history(actor):
            use = record['use']
            if (record['selected_at'] > engine.elapsed_seconds or use is not None
                    and (use['at'] > engine.elapsed_seconds
                         or any(uid not in index for uid in use['target_ids']))):
                raise ValueError('optional Move receipt references missing target or future time')
    return True


def choose(engine, actor, move_id, *, reason):
    import world_entities as WORLD
    WORLD.require_actors(engine, actor)
    validate_actor(actor)
    mid = engine.r.move_id(move_id)
    row = definition(engine.r, mid)
    if row is None: raise ValueError('Move has no reviewed optional effect')
    if actor.spec.get('kind') not in ('pokemon', 'trainer') or mid not in actor.moves:
        raise ValueError('actual actor must currently know the selected Move')
    if not isinstance(reason, str) or not reason.strip(): raise ValueError('selection reason required')
    if any(r['move_id'] == mid and r['scene'] == scene(actor) for r in history(actor)):
        raise ValueError('optional Move already selected or used this scene')
    record = dict(id=f'optional:{actor.entity_id}:{mid}:{scene(actor)}', actor_id=actor.entity_id,
                  move_id=mid, clause_id=row['clause_id'], source_row_sha256=row['source_row_sha256'],
                  scene=scene(actor), selected_at=engine.elapsed_seconds, reason=reason.strip(), use=None)
    actor.spec.setdefault(KEY, dict(version=1, history=[]))['history'].append(record)
    engine.log(f'    {actor.name}: {engine.r.move(mid)["name"]} 장면 1회 효과 선택', mid)
    return deepcopy(record)


def _choice(engine, actor, target, mid):
    import move_activation
    group = move_activation.current_scope(engine, actor, target, mid)
    if group is not None and 'optional_move_choice' in group:
        return next((r for r in history(actor) if r['id'] == group['optional_move_choice']), None)
    return next((r for r in history(actor)
                 if r['move_id'] == mid and r['scene'] == scene(actor) and r['use'] is None), None)


def project(engine, actor, target, move, mechanics, *, native=False):
    row = definition(engine.r, move['id'])
    if row is None: return move, mechanics
    validate_actor(actor)
    record = _choice(engine, actor, target, move['id'])
    move = dict(move, keywords=list(row['default_keywords']))
    mm = deepcopy(row['normal_mechanics'])
    if record is None: return move, mm
    move['_optional_move_choice'] = record['id']
    move.update(deepcopy(row.get('selected_move', {})))
    mm = deepcopy(row['selected_mechanics'])
    if 'selected_range' in row:
        move['_optional_move_range'] = deepcopy(row['selected_range'])
        if native and not any(s['actor'] is actor and s['move_id'] == move['id']
                and 0 < s['index'] <= len(s['targets']) and s['targets'][s['index']-1] is target
                for s in getattr(engine, '_move_activation_scopes', ())):
            raise ValueError('optional area mode requires actual use_move_on target selection')
    if row.get('requires') == 'ally' and actor.side != target.side:
        raise ValueError('optional healing mode requires an actual ally')
    if row.get('requires') == 'afflicted_target' and '_actual_targets' in move and record['use'] is None:
        import status_sets
        if not any(status_sets.afflictions(t) for t in move['_actual_targets']):
            raise ValueError('optional damage mode requires a previously afflicted actual target')
    return move, mm


def filter_targets(engine, actor, move, targets):
    if '_optional_move_choice' not in move: return targets
    row = definition(engine.r, move['id'])
    if row.get('exclude_allies'):
        return [target for target in targets if target.side != actor.side]
    return targets


def _commit(engine, actor, record, row, targets):
    if record['use'] is not None: return
    record['use'] = dict(at=engine.elapsed_seconds, boundary=row['consume'],
                         target_ids=[t.entity_id for t in targets])
    validate_actor(actor)
    engine.log('    장면 1회 선택 효과 사용', record['move_id'])


def begin_move_use(engine, actor, target, move, mechanics):
    row = definition(engine.r, move['id'])
    if row is None: return
    import move_activation
    move_activation._require_started_event_use(engine, actor, target, move['id'],
        scope_error='optional Move requires actual native activation',
        move_error='optional Move activation mismatch', move_id_required=True)
    record = _choice(engine, actor, target, move['id'])
    group = move_activation.current_scope(engine, actor, target, move['id'])
    choice = None if record is None else record['id']
    if move.get('_optional_move_choice') != choice: raise ValueError('optional Move projection changed')
    if group is not None: group['optional_move_choice'] = choice
    if record is not None and row['consume'] == 'activation':
        _commit(engine, actor, record, row, group['targets'] if group is not None else (target,))


def on_hit(engine, actor, target, move, completion_id):
    choice = move.get('_optional_move_choice')
    if choice is None: return
    row = definition(engine.r, move['id'])
    record = next(r for r in history(actor) if r['id'] == choice)
    import move_completion
    completion = getattr(engine, move_completion.KEY, {}).get(completion_id)
    import move_defense_reactions as DEFENSE
    native_token=getattr(engine,'_defense_recipient_scope',None)
    routed=False
    if native_token is not None:
        DEFENSE.require_recipient(engine,native_token,actor,target,move,completion_id)
        routed=True
    if (completion is None or completion['actor'] is not actor
            or completion['move_id'] != move['id']
            or completion['move'].get('_optional_move_choice') != choice
            or (not routed and target.entity_id not in completion['started'])
            or target.entity_id in completion['results']):
        raise ValueError('optional on-hit mode requires actual unfinished Move resolution')
    if row['consume'] == 'hit': _commit(engine, actor, record, row, (target,))
