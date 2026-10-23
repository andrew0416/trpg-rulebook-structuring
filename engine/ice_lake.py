"""C11-080/081: an adopted lake on the actual map and Move completion owners.

The source supplies no Acrobatics DC.  Its explicit GM adoption supplies that
choice. Water is native base terrain, and falling into it is not Tripped.
"""
from copy import deepcopy
import common_checks as C
import map_terrain as MAP
import body_state as BODY
import world_entities as WORLD
import state_grants as GRANTS
import root_resolution as ROOT

SOURCE = 'definition/극도로-추운-전투'
REFERENCE = {'file': 'input/ch11-running-the-game.md',
             'sha256': '5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad'}
KEY = '_ice_lake'


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(label + ' required')


def _source(e):
    chosen = e.r.select_source_definition(SOURCE, source=REFERENCE)
    if (chosen['selected_id'] != SOURCE or e.rulings.mech.get(SOURCE)
            or e.rulings.effects.get(SOURCE)):
        raise ValueError('selected ice lake variant requires its own adapter')


def state(e):
    if e.grid is None:
        return None
    row = getattr(e.grid, 'terrain_observations', {}).get(KEY)
    if row is None:
        return None
    _source(e)
    if (type(row) is not dict or set(row) != {'source', 'reference', 'shallow', 'thick',
            'slow', 'breaking_moves', 'injury_check', 'water_air_available',
            'water_timing_policy', 'gm_id', 'reason', 'fingerprint'}
            or row['source'] != SOURCE or row['reference'] != REFERENCE
            or row['fingerprint'] != ROOT.fingerprint({k:v for k,v in row.items() if k != 'fingerprint'})):
        raise ValueError('actual adopted ice lake observation changed')
    _text(row['gm_id'], 'GM identity'); _text(row['reason'], 'GM adoption reason')
    if type(row['slow']) is not bool:
        raise ValueError('explicit ice slow terrain choice required')
    shallow = _cells(e, row['shallow']); thick = _cells(e, row['thick'])
    if not shallow and not thick or set(shallow).intersection(thick):
        raise ValueError('distinct adopted shallow and thick ice required')
    _moves(e, row['breaking_moves']); _check(row['injury_check'])
    _water_policy(row['water_air_available'], row['water_timing_policy'])
    return row


def _cells(e, values):
    if type(values) not in (list, tuple):
        raise ValueError('actual ice map cells required')
    points = tuple(MAP.point(p) for p in values)
    if len(set(points)) != len(points) or any(not e.grid.inside(p) for p in points):
        raise ValueError('distinct in-map ice cells required')
    return points


def _moves(e, values):
    if type(values) is not list or len(set(values)) != len(values):
        raise ValueError('explicit GM selected ice-breaking Moves required')
    for uid in values:
        if type(uid) is not str or e.r.move_id(uid) != uid or e.r._selected_rule(uid) != uid:
            raise ValueError('actual selected ice-breaking Move required')


def _check(value):
    if value is None:
        return
    if type(value) is not dict or set(value) != {'dc', 'reason'}:
        raise ValueError('explicit GM ice Acrobatics DC and reason required')
    C.integer(value['dc'], 'GM selected ice Acrobatics DC', 0)
    _text(value['reason'], 'GM ice Acrobatics policy reason')


def _water_policy(air_available, timing):
    import environmental_effects as ENV
    if type(air_available) is not bool or timing not in (None, *ENV.TIMINGS):
        raise ValueError('explicit actual lake-water air availability and native timing required')


def adopt(e, *, shallow_cells, thick_cells=(), slow=False, breaking_moves=(),
          injury_check=None, water_air_available, water_timing_policy=None, gm_id, reason):
    """Observe the chosen sample. No ice, move selection, or DC is inferred."""
    if e.grid is None:
        raise ValueError('ice lake adoption requires an actual map')
    if getattr(e.grid, 'terrain_observations', {}).get(KEY) is not None:
        raise ValueError('this map already has an adopted ice lake')
    _source(e); _text(gm_id, 'GM identity'); _text(reason, 'GM adoption reason')
    shallow = _cells(e, shallow_cells); thick = _cells(e, thick_cells)
    if not shallow and not thick or set(shallow).intersection(thick):
        raise ValueError('distinct adopted shallow and thick ice required')
    if type(slow) is not bool:
        raise ValueError('explicit ice slow terrain choice required')
    moves = list(breaking_moves); _moves(e, moves); _check(injury_check)
    _water_policy(water_air_available, water_timing_policy)
    row = dict(source=SOURCE, reference=deepcopy(REFERENCE),
               shallow=[list(p) for p in shallow], thick=[list(p) for p in thick],
               slow=slow, breaking_moves=moves, injury_check=deepcopy(injury_check),
               water_air_available=water_air_available, water_timing_policy=water_timing_policy,
               gm_id=gm_id, reason=reason)
    row['fingerprint'] = ROOT.fingerprint(row)
    def apply(staged, _):
        MAP.observe(staged, (*shallow, *thick), base='regular', slow=slow, reason=reason)
        staged.grid.terrain_observations[KEY] = deepcopy(row)
        for actor in WORLD.actor_index(staged).values():
            if actor.on_field and not actor.captured:
                enter(staged, actor)
        staged.gm._rec('adopted ice lake', None, row, reason)
        return deepcopy(row)
    return GRANTS.transition(e, None, apply, include_grid=True)


def interested(e, actor=None, target=None):
    return e.grid is not None and KEY in getattr(e.grid, 'terrain_observations', {})


def empty_area_adopted(e, actor, move):
    row = state(e)
    if row is None or move.get('id') not in row['breaking_moves']:
        return False
    WORLD.require_actors(e, actor)
    import weapon_actions as WEAPON
    import area_targets as AREA
    if not WEAPON.range_spec(e, move, actor).get('shape'):
        return False
    return bool(AREA.cells(e, actor, move))


def watch_attack(e, event):
    row = state(e)
    if row is None:
        return
    event[KEY] = {'adoption': row['fingerprint'],
                  'ice_contact': [], 'damage_contact': [], 'injuries': 0}


def _contact(e, target):
    row = state(e)
    if row is None or not _surface(target):
        return set()
    return {p for p in BODY.cells(target).intersection(_ice(row)) if MAP.base_at(e.grid, p) == 'regular'}


def note_injury(e, event_id, gained, *, contact=None):
    """Consume actual injury deltas at native damage/effect occurrence only."""
    event = getattr(e, '_passive_events', {}).get(event_id)
    if event is None or KEY not in event or gained <= 0:
        return
    if event['phase'] != 'activated':
        raise ValueError('ice injury observation requires its native recipient')
    contact = set(map(tuple, event[KEY]['damage_contact'])) if contact is None else contact
    if contact:
        proof = event[KEY]
        proof['ice_contact'] = sorted(set(map(tuple, proof['ice_contact'])).union(contact))
        proof['injuries'] += gained


def before_damage(e, event_id):
    event = getattr(e, '_passive_events', {}).get(event_id)
    if event is not None and KEY in event:
        event[KEY]['damage_contact'] = sorted(_contact(e, event['target']))


def injury_effect(e, actor, target, context):
    """Read the live Move recipient before an explicit native injury effect."""
    if context.get('hit') is not True:
        return None
    for event_id, event in getattr(e, '_passive_events', {}).items():
        if (KEY in event and event['phase'] == 'activated' and event['actor'] is actor
                and event['target'] is target and event['completion_id'] == context.get('move_completion')
                and event['move_id'] == context.get('source_id')):
            return event_id, target.injuries, _contact(e, target)
    return None


def _surface(actor):
    return (not getattr(actor, 'airborne', False) and actor.spec.get('_movement_altitude', 0) == 0
            and not actor.spec.get('_burrow', {}).get('underground'))


def _ice(row):
    return set(map(tuple, row['shallow'] + row['thick']))


def surface_hole_entry(e, actor, position, mode, *, altitude, underground):
    """A first step off ice falls into its hole; it grants no swimming travel."""
    if (not interested(e) or mode not in ('land', '육상') or altitude != 0
            or underground or not _surface(actor)):
        return False
    row = state(e)
    if any(MAP.base_at(e.grid, p) == 'underwater' for p in BODY.cells(actor)):
        return False
    water = {p for p in BODY.at_position(actor, position) if MAP.base_at(e.grid, p) == 'underwater'}
    return bool(water) and water.issubset(_ice(row))


def _water(e, actor, cells, *, cause):
    """Use native terrain/altitude; do not invent fall distance or HP loss."""
    actor.spec['_movement_altitude'] = 0
    actor.airborne = False
    row = state(e)
    import environmental_effects as ENV
    breathing = ENV.observe_breathing(e, actor, air_available=row['water_air_available'],
        medium='water', reason='ice lake water: ' + cause,
        timing_policy=row['water_timing_policy'],
        round_offset_seconds=None if e.round_start_seconds is None else e.elapsed_seconds-e.round_start_seconds)
    if isinstance(breathing, C.PendingDecision):
        raise ValueError('actual lake water breathing observation must be resolved: ' + str(breathing))
    e.log('  ' + actor.name + ' falls into lake water at ' + str(sorted(cells)), SOURCE)
    return {'actor_id': actor.entity_id, 'cells': sorted(cells), 'cause': cause,
            'medium': 'water', 'base': 'underwater'}


def _break(e, cells, cause):
    row = state(e)
    actual = _ice(row).intersection(cells)
    newly = {p for p in actual if MAP.base_at(e.grid, p) != 'underwater'}
    if newly:
        MAP.observe(e, sorted(newly), base='underwater', slow=False,
                    reason=row['reason'] + ': ' + cause)
    fallen = []
    for actor in WORLD.actor_index(e).values():
        if actor.on_field and not actor.captured and _surface(actor):
            water = BODY.cells(actor).intersection(newly)
            if water:
                fallen.append(_water(e, actor, water, cause=cause))
    return {'broken': sorted(newly), 'fallen': fallen}


def enter(e, actor, *, actual_fall=False):
    if not interested(e):
        return None
    return GRANTS.transition(e, actor,
        lambda staged, subject: _enter(staged, subject, actual_fall=actual_fall), include_grid=True)


def _enter(e, actor, *, actual_fall=False):
    row = state(e)
    if row is None or not actor.on_field or actor.captured:
        return None
    if not actual_fall and not _surface(actor):
        return None
    if actual_fall:
        actor.airborne = False
        actor.spec['_movement_altitude'] = 0
    body = BODY.cells(actor)
    shallow = body.intersection(map(tuple, row['shallow']))
    cause = 'actual fall' if actual_fall else 'actual surface entry'
    result = {'broken': [], 'fallen': []}
    if actor.kind == 'pokemon' and actor.weight_class >= 5 and shallow:
        result = _break(e, shallow, cause)
    water = {p for p in body.intersection(_ice(row)) if MAP.base_at(e.grid, p) == 'underwater'}
    if water and not any(x['actor_id'] == actor.entity_id for x in result['fallen']):
        result['fallen'].append(_water(e, actor, water, cause=cause))
    old = actor.spec.get('_respiration', {})
    if not water and old.get('reason', '').startswith('ice lake water: '):
        import environmental_effects as ENV
        ENV.observe_breathing(e, actor, air_available=True, medium='air',
            reason='actual surface departure from ice lake water',
            round_offset_seconds=None if e.round_start_seconds is None else e.elapsed_seconds-e.round_start_seconds)
    return result


def bind_move(e, completion):
    row = state(e)
    if row is None:
        return
    import area_targets as AREA
    import weapon_actions as WEAPON
    move = completion['move']; actor = completion['actor']
    breaking = completion['move_id'] in row['breaking_moves']
    cells = set()
    if breaking:
        shape = WEAPON.range_spec(e, move, actor).get('shape')
        if shape:
            if '_area_aim' not in move:
                move = dict(move, _area_aim=actor.pos if shape == 'burst' else completion['targets'][0].pos)
            cells = set(move.get('_effect_area_cells', AREA.cells(e, actor, move)))
        else:
            cells = set().union(*(BODY.cells(t) for t in completion['targets']))
    completion[KEY] = {'adoption': row['fingerprint'], 'cells': sorted(cells),
                       'breaking': breaking, 'injury_checks': {}, 'phase': 'observed'}
    _seal(completion[KEY])


def _seal(proof):
    proof['fingerprint'] = ROOT.fingerprint({k:v for k,v in proof.items() if k != 'fingerprint'})


def _injuries(event):
    return event.get(KEY, {}).get('injuries', 0)


def observe_completion(e, completion):
    evidence = completion.get(KEY)
    if evidence is None or evidence['phase'] == 'resolved':
        return
    if (getattr(e, '_move_completions', {}).get(completion.get('id')) is not completion
            or completion['phase'] != 'completion_effects' or not completion['sealed']
            or set(completion['results']) != {t.entity_id for t in completion['targets']}):
        raise ValueError('actual native ice Move completion boundary required')
    row = state(e)
    if row is None or row['fingerprint'] != evidence['adoption']:
        raise ValueError('actual ice lake completion adoption changed')
    if row['injury_check'] is not None:
        for uid, event in getattr(e, '_passive_events', {}).items():
            if (event.get('completion_id') != completion['id'] or event.get('hit') is not True
                    or event['target'].entity_id in evidence['injury_checks']):
                continue
            target = event['target']; gained = _injuries(event)
            if gained <= 0 or not event.get(KEY, {}).get('ice_contact'):
                continue
            check = C.against_dc(e.skill_roll(target, '곡예'), row['injury_check']['dc'])
            if not check.passed:
                e.apply_status(target, '넘어짐', source=SOURCE)
            evidence['injury_checks'][target.entity_id] = {
                'event_id': uid, 'injuries': gained,
                'dc': check.dc, 'total': check.total, 'passed': check.passed}
            _seal(evidence)
    if evidence['breaking'] and (completion.get('activation') == 'empty_area_field'
            or not all(x['cancelled'] for x in completion['results'].values())):
        _seal(evidence)
        evidence['terrain'] = _break(e, evidence['cells'], 'actual GM-selected Move ' + completion['move_id'])
    evidence['phase'] = 'resolved'
    _seal(evidence)


def validate_world(e, actors):
    row = state(e)
    if row is None:
        return
    for p in _ice(row):
        if MAP.base_at(e.grid, p) not in ('regular', 'underwater'):
            raise ValueError('adopted ice requires native surface or water terrain')
    for completion in getattr(e, '_move_completions', {}).values():
        proof = completion.get(KEY)
        if proof is None:
            continue
        if (proof['adoption'] != row['fingerprint'] or proof['phase'] not in ('observed', 'resolved')
                or proof['breaking'] is not (completion['move_id'] in row['breaking_moves'])
                or proof['fingerprint'] != ROOT.fingerprint({k:v for k,v in proof.items() if k != 'fingerprint'})):
            raise ValueError('actual ice lake Move evidence changed')
        _cells(e, proof['cells'])
        for actor_id, check in proof['injury_checks'].items():
            event = getattr(e, '_passive_events', {}).get(check['event_id'])
            if (actor_id not in actors or event is None or event['target'] is not actors[actor_id]
                    or event['completion_id'] != completion['id'] or event['hit'] is not True
                    or check['injuries'] != _injuries(event)
                    or check['injuries'] <= 0 or check['dc'] != row['injury_check']['dc']
                    or check['passed'] is not (check['total'] >= check['dc'])):
                raise ValueError('native injury-causing ice attack proof changed')
