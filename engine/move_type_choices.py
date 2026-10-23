"""Source-required monotype choices, applied through shared timed type grants."""
from copy import deepcopy
from pathlib import Path
import json
import common_checks as C
import type_state as TYPES
import attack_damage_history as DAMAGE_HISTORY

KEY = 'move_type_choices'
POLICY = 'data/move-type-choice-policy.json'


def definition(rules, mid):
    data = getattr(rules, '_move_type_choice_policy', None)
    if data is None:
        data = json.loads((Path(rules.root)/POLICY).read_text(encoding='utf-8'))
        from optional_move_modes import _source_digest
        for relative, digest in data['source_files'].items():
            path = Path(rules.root)/relative
            if _source_digest(str(path), (path.stat().st_mtime_ns, path.stat().st_size)) != digest:
                raise ValueError('type choice source changed')
        rules._move_type_choice_policy = data
    row = data['moves'].get(mid)
    if row is not None:
        if rules._selected_rule(mid) != mid or rules.move_mech(mid)[0] != row['native_mechanics']:
            raise ValueError('selected type choice definition changed')
    return row


def records(actor): return actor.spec.get(KEY, [])


def validate_actor(actor):
    if not isinstance(records(actor), list): raise ValueError('type choices must be a list')
    for number, row in enumerate(records(actor), 1):
        if not isinstance(row, dict) or set(row) != {
                'sequence', 'actor_id', 'source', 'type', 'basis', 'reason', 'at', 'used_at', 'cancelled_at'}:
            raise ValueError('type choice shape changed')
        policy = definition(actor.r, row['source'])
        if policy is None or row['sequence'] != number or row['actor_id'] != actor.entity_id:
            raise ValueError('type choice identity changed')
        TYPES.validate_types(actor.r, [row['type']])
        C.integer(row['at'], 'choice time', 0)
        if row['used_at'] is not None: C.integer(row['used_at'], 'type choice use time', row['at'])
        if row['cancelled_at'] is not None:
            C.integer(row['cancelled_at'], 'type choice cancellation time', row['at'])
            if row['used_at'] is not None: raise ValueError('used type choice cannot be cancelled')
        if not isinstance(row['reason'], str) or not row['reason'].strip():
            raise ValueError('type choice reason required')
        basis = row['basis']
        if policy['choice'] == 'known_move':
            if set(basis) != {'move_id'} or basis['move_id'] not in actor.r.moves:
                raise ValueError('known Move choice basis changed')
        else:
            if set(basis) != {'damage_sequence'}:
                raise ValueError('actual damage choice basis required')
            seq = C.integer(basis['damage_sequence'], 'damage sequence', 1, len(DAMAGE_HISTORY.records(actor)))
            attack = DAMAGE_HISTORY.records(actor)[seq-1]
            if DAMAGE_HISTORY.amount(attack) <= 0 or TYPES.matchup(actor.r, attack['move_type'], row['type']) != .5:
                raise ValueError('type choice does not resist observed damaging Move')
    return True


def _pending(actor, mid):
    return next((row for row in reversed(records(actor))
                 if row['source'] == mid and row['used_at'] is None and row['cancelled_at'] is None), None)


def _basis(engine, actor, mid, chosen_type, known_move=None):
    import homebrew_state as HOME
    policy = definition(engine.r, mid)
    if policy is None or mid not in actor.moves: raise ValueError('known type-changing Move required')
    if HOME.type_change_blocked(actor): raise ValueError('current state blocks type changes')
    TYPES.validate_types(engine.r, [chosen_type])
    if policy['choice'] == 'known_move':
        if known_move is None: raise ValueError('choose an actual known Move')
        known_move = engine.r.move_id(known_move)
        import move_type_sync as SYNC
        current_move = SYNC.prepare(engine,actor,engine.r.move(known_move))
        if known_move not in actor.moves or current_move['type'] != chosen_type:
            raise ValueError('chosen type must equal the selected known Move type')
        return {'move_id': known_move}
    if known_move is not None: raise ValueError('Conversion 2 uses actual received damage')
    last = DAMAGE_HISTORY.last_damage(actor)
    if last is None or TYPES.matchup(engine.r, last['move_type'], chosen_type) != .5:
        raise ValueError('choose a type resisting the last actually damaging Move')
    return {'damage_sequence': last['sequence']}


def choose(engine, actor, mid, chosen_type, *, known_move=None, reason):
    import world_entities as WORLD
    WORLD.require_actors(engine, actor)
    mid = engine.r.move_id(mid)
    validate_actor(actor)
    basis = _basis(engine, actor, mid, chosen_type, known_move)
    if not isinstance(reason, str) or not reason.strip(): raise ValueError('type choice reason required')
    pending = _pending(actor, mid)
    row = dict(sequence=len(records(actor))+1, actor_id=actor.entity_id, source=mid,
               type=chosen_type, basis=basis, reason=reason, at=engine.elapsed_seconds, used_at=None, cancelled_at=None)
    if pending is not None: pending['cancelled_at'] = engine.elapsed_seconds
    actor.spec.setdefault(KEY, []).append(row)
    return deepcopy(row)


def project(engine, actor, target, move, mechanics):
    policy = definition(engine.r, move['id'])
    if policy is None: return move, mechanics
    validate_actor(actor)
    row = _pending(actor, move['id'])
    if row is None: raise ValueError('explicit type choice required before Move cost')
    basis = _basis(engine, actor, move['id'], row['type'], row['basis'].get('move_id'))
    if basis != row['basis']: raise ValueError('type choice basis changed before activation')
    if actor is not target: raise ValueError('type-changing Move targets its actual user')
    effect = {'type': 'type_change', 'set_type': row['type'], 'single_type': True,
              'target': 'self', 'until': 'encounter_end'}
    return dict(move, _type_choice=row['sequence']), dict(effects_exec=[effect])


def begin_move_use(engine, actor, target, move):
    if '_type_choice' not in move: return
    scopes = getattr(engine, '_event_use_scopes', [])
    if not scopes or scopes[-1].get('move_id') != move['id'] or scopes[-1]['actor'] is not actor:
        raise ValueError('actual type-changing Move activation required')
    row = _pending(actor, move['id'])
    if row is None or row['sequence'] != move['_type_choice']: raise ValueError('type choice already consumed')
    row['used_at'] = engine.elapsed_seconds


def validate_world(engine, index):
    for actor in index.values():
        validate_actor(actor)
        for row in records(actor):
            if max(row['at'], row['used_at'] or 0, row['cancelled_at'] or 0) > engine.elapsed_seconds:
                raise ValueError('type choice has a future timestamp')
