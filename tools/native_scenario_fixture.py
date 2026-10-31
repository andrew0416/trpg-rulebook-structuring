"""Accepted native scene inputs, not proof of legal creation or acquisition.

prepare_scene owns fresh Rules; prepare_body preserves an existing native actor.
Supply actual observations and complete known moves; native validators retain
source and capacity guards. Acquisition, mounting and turns remain explicit.
prepare_object returns the live registered object, not a detached observation.
Action-scene fixtures take caller-owned Rules and explicitly start a turn.
"""
from copy import deepcopy

from builder import build_pokemon, build_trainer
from engine import Rules, Engine, Combatant
from grid import Grid
import body_state as BODY
import move_state as MOVES
import state_fields as FIELDS
import world_entities as WORLD


def prepare_setup_move_scene(rules, *, seed=162287386801):
    """Return the existing learned Set-Up Move fixture at its first active turn."""
    engine = Engine(rules, seed=seed)
    engine.grid = Grid(20, 12)
    stats = dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 30)
    actor = Combatant(rules, build_trainer(
        rules, 'setup user', 30, stats,
        extra={'moves': ['move/지오컨트롤'], 'side': 'party', 'pos': (2, 2), 'size': '중형'}))
    engine.gm.add_combatant(actor)
    target = Combatant(rules, build_trainer(
        rules, 'setup target', 30, stats,
        extra={'moves': ['move/몸통박치기'], 'side': 'opponent', 'pos': (5, 2), 'size': '중형'}))
    engine.gm.add_combatant(target)
    engine.gm.choose_learned_capability_policy(
        actor, 'move/공중날기', 'move_entry', reason='record 287 Move entry is selected')
    engine.gm.set_movement_capabilities(
        actor, {'land': 4, 'sky': 0, 'burrow': 0, 'swim': 0}, basis='base',
        reason='observed pre-learning movement capabilities')
    for move_id in ('move/공중날기', 'move/구멍파기', 'move/다이빙'):
        engine.gm.set_move(actor, move_id, reason='actual learned setup Move')
    engine.start_round(engine.everyone)
    engine.start_of_turn(actor, initiative_count=20)
    return engine, actor, target


def prepare_gmax_scene(rules, declaration, *, seed=1):
    """Return the existing active G-Max fixture using an actual declaration."""
    actor = Combatant(rules, build_pokemon(
        rules, declaration['species_eng'], 50, side='party'))
    target = Combatant(rules, build_pokemon(rules, 'Pikachu', 20, side='wild'))
    engine = Engine(rules, seed=seed)
    engine.gm.add_combatant(actor)
    engine.gm.add_combatant(target)
    engine.start_round([actor, target])
    engine.start_of_turn(actor, initiative_count=20)
    derived = rules.move(declaration['move_id'])
    base = next(mid for mid in actor.moves
                if rules.move(mid)['type'] == derived['type'] and
                rules.move(mid)['class'] in ('물리', '특수'))
    if declaration['clause_id'] == 'C2CSV-MOVE-R1046':
        target.last_move = target.moves[0]
    engine.enter_gigantamax(actor, source_id='test/gmax-source', reason='direct G-Max fixture')
    return engine, actor, target, base, declaration['move_id']


def prepare_object(engine, object_id, *, location, reason, **observations):
    """Observe a real object and return its native record for fixture consumers.

    Registration still validates every observation and does not acquire an
    inventory item. Its public detached return is intentionally not reused.
    """
    WORLD.register_object(engine, object_id, location=location, reason=reason,
                          **observations)
    return engine._physical_objects[object_id]


def assert_rejected_unchanged(engine, operation, *, reason_pattern):
    """Require the named ValueError and unchanged native world/RNG; never repair it."""
    return assert_rejections_unchanged(engine, [operation], reason_pattern=reason_pattern)[0]


def assert_rejections_unchanged(engine, operations, *, reason_pattern):
    """Check each rejection against one unchanged baseline, including native RNG."""
    import re
    if not isinstance(operations, (list, tuple)) or not operations:
        raise ValueError('nonempty list or tuple of rejected operations required')
    patterns = [reason_pattern] * len(operations) if isinstance(reason_pattern, str) else reason_pattern
    if (not isinstance(patterns, (list, tuple)) or len(patterns) != len(operations)
            or any(not isinstance(pattern, str) or not pattern.strip() for pattern in patterns)):
        raise ValueError('explicit nonempty rejection reason pattern required for each operation')
    expected = [re.compile(pattern) for pattern in patterns]
    before = engine.snapshot_state()  # Same payload as export_state (RNG included), without the validation pass.
    errors = []
    for operation, pattern, check in zip(operations, patterns, expected):
        try:
            operation()
        except ValueError as error:
            if not check.search(str(error)):
                raise AssertionError('rejection reason did not match ' + repr(pattern) + ': ' + str(error)) from error
            errors.append(error)
        else:
            raise AssertionError('expected ValueError matching ' + repr(pattern))
        finally:
            if engine.snapshot_state() != before:
                raise AssertionError('rejection changed engine state or RNG')
    return errors


def _body_input(body, label):
    for field in ('size', 'offsets', 'reason'):
        if not isinstance(body, dict) or not body.get(field):
            raise ValueError(label + ': actual body.' + field + ' observation required')
    if not isinstance(body['size'], str) or body['size'] not in BODY.WIDTH:
        raise ValueError(label + ': actual body.size needs a native size classification')
    WORLD._text(body['reason'], label + ': actual body.reason')


def prepare_body(engine, actor, *, size, offsets, reason):
    """Observe a registered actor without rebuilding its identity or ownership.

    Existing size is a fact, not a default to replace. The caller declares size
    independently of footprint and supplies the complete native move state.
    """
    WORLD.require_actors(engine, actor)
    _body_input(dict(size=size, offsets=offsets, reason=reason), actor.entity_id)
    if actor.spec.get('size') is not None and actor.spec['size'] != size:
        raise ValueError(actor.entity_id + ': existing size and actual body.size observation disagree')
    MOVES.validate_actor(actor)
    engine.gm.set_footprint(actor, offsets, reason=reason)
    if actor.spec.get('size') is None:
        FIELDS.base_patch(actor, {'size': size}, reason=reason, source='gm/scenario-body-observation')
    BODY.cells(actor, require_complete=True)
    BODY.melee_reach(actor)
    return actor


def prepare_scene(root, *, ruleset, seed, grid, actors):
    """Return ``(engine, actors_by_key)`` before any round or action begins.

    Each row supplies ``key``, ``kind``, native builder ``sheet`` kwargs and
    ``body={size, offsets, reason}``. Size is an accepted actual observation,
    never inferred from the footprint or supplied by this fixture.
    """
    if not isinstance(ruleset, str) or not ruleset.strip():
        raise ValueError('prepare_scene: explicitly selected ruleset required')
    if not isinstance(grid, dict) or any(type(grid.get(k)) is not int or grid[k] < 1
                                         for k in ('width', 'height')):
        raise ValueError('prepare_scene: positive observed grid width and height required')
    if not isinstance(actors, (list, tuple)) or not actors:
        raise ValueError('prepare_scene: explicit actor rows required')
    builders = {'trainer': build_trainer, 'pokemon': build_pokemon}
    keys = set()
    for row in actors:
        if not isinstance(row, dict):
            raise ValueError('prepare_scene: each actor row must be a mapping')
        key = row.get('key')
        if not isinstance(key, str) or not key.strip() or key in keys:
            raise ValueError('prepare_scene: distinct nonempty actor key required')
        keys.add(key)
        if row.get('kind') not in builders:
            raise ValueError(key + ': native trainer or pokemon builder required')
        sheet = row.get('sheet')
        required = ('name', 'level', 'moves', 'abilities', 'pos') + (
            ('stats',) if row['kind'] == 'trainer' else ('species',))
        for field in required:
            if not isinstance(sheet, dict) or sheet.get(field) is None:
                raise ValueError(key + ': explicit native sheet.' + field + ' required')
        FIELDS.location({'kind': 'grid', 'cell': sheet['pos']})
        body = row.get('body')
        _body_input(body, key)
        supplied_size = (sheet.get('extra') or {}).get('size', body['size'])
        if supplied_size != body['size']:
            raise ValueError(key + ': sheet size and actual body.size observation disagree')

    rules = Rules(root, ruleset=ruleset)
    engine = Engine(rules, seed=seed)
    engine.grid = Grid(**grid)
    prepared = {}
    for row in actors:
        sheet, body = deepcopy(row['sheet']), row['body']
        sheet['extra'] = dict(sheet.get('extra') or {}, size=body['size'])
        actor = Combatant(rules, builders[row['kind']](rules, **sheet))
        engine.gm.add_combatant(actor, reason=body['reason'])
        prepare_body(engine, actor, size=body['size'], offsets=body['offsets'], reason=body['reason'])
        prepared[row['key']] = actor
    return engine, prepared


def assert_logged_refusal_unchanged(engine, operation, *, expected_result, expected_logs):
    """Ordinary return-value refusal only: exact declared diagnostics, no other change.

    Exceptions propagate; this never normalizes an exception-rollback assertion.
    Callers supply complete expected messages derived from the actual refusal source.
    """
    from unittest.mock import patch
    if not isinstance(expected_logs, list) or not expected_logs or any(type(line) is not str for line in expected_logs):
        raise ValueError('explicit nonempty exact refusal diagnostic sequence required')
    before = engine.export_state()
    prefix = list(engine.log_lines)
    result = operation()
    if result != expected_result:
        raise AssertionError('unexpected native refusal result')
    if engine.log_lines != prefix + expected_logs:
        raise AssertionError('unexpected native refusal diagnostic sequence')
    with patch.object(engine, 'log_lines', prefix):
        if engine.export_state() != before:
            raise AssertionError('refusal changed native world or RNG beyond its exact diagnostic')
    return result
