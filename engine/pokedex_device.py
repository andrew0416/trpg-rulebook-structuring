"""Chapter 9 Pokedex state on the existing physical item, with GM observations.

The host supplies recognized scan readouts and service/download observations.
No private move slots, invented species facts or real network services are read.
"""
from copy import deepcopy
from math import isfinite

import common_checks as C
import item_stock as STOCK
import state_grants as G
import world_entities as W
import turn as TURN
import action_lifecycle as ACTION

RULE = 'item/포켓몬-도감'
FIELD = 'pokedex_device'
SOURCE = 'input/ch09-equipment.md:21-25'
SOURCE_FILE_SHA256 = 'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'
BUILTINS = ('phone', 'radio', 'internet')


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError('nonempty ' + label + ' required')
    return value


def _fields(value, names, label):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError('explicit ' + label + ' fields required')


def _measurement(value):
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise ValueError('observed nonnegative finite Pokedex measurement required')


def _source(engine):
    if engine.r._selected_rule(RULE) != RULE:
        raise ValueError('selected Pokedex source needs its own device policy')
    from source_context import verified_source
    verified_source(engine.r, {'file': 'input/ch09-equipment.md', 'sha256': SOURCE_FILE_SHA256}, label='Pokedex')


def _trainer(engine, actor):
    W.require_actors(engine, actor)
    if actor.kind != 'trainer':
        raise ValueError('actual trainer Pokedex operator required')
    _source(engine)


def _readout(value):
    _fields(value, ('species', 'average', 'individual', 'learnable_moves', 'learnset_source', 'knowledge', 'source'), 'GM scan readout')
    _text(value['species'], 'recognized species identity')
    _text(value['source'], 'disclosed scan information source')
    _text(value['learnset_source'], 'species learnset information source')
    for key in ('average', 'individual'):
        _fields(value[key], ('height_m', 'weight_kg'), key + ' measurements')
        for measurement in value[key].values():
            _measurement(measurement)
    moves = value['learnable_moves']
    if type(moves) is not list:
        raise ValueError('distinct disclosed species learnable moves required')
    for move in moves:
        _text(move, 'species learnable move')
    if len(set(moves)) != len(moves):
        raise ValueError('distinct disclosed species learnable moves required')
    knowledge = value['knowledge']
    if type(knowledge) is not dict or not knowledge:
        raise ValueError('explicit disclosed Pokedex knowledge required')
    for topic, answer in knowledge.items():
        _text(topic, 'disclosed knowledge topic')
        _text(answer, 'disclosed knowledge answer')
    return deepcopy(value)


def validate(engine, obj):
    """Validate only this new per-instance state; physical integrity stays shared."""
    if FIELD not in obj:
        return None
    _source(engine)
    if obj.get('kind') != 'item_instance' or obj.get('item_rule_id') != RULE:
        raise ValueError('Pokedex device state belongs to another physical rule')
    state = obj[FIELD]
    _fields(state, ('version', 'source', 'value_points', 'builtin_functions', 'origin', 'scans', 'apps', 'uses'), 'Pokedex state')
    if state['version'] != 1 or type(state['version']) is not int or state['source'] != SOURCE or state['builtin_functions'] != list(BUILTINS):
        raise ValueError('Pokedex version/source/builtin functions changed')
    C.integer(state['value_points'], 'Pokedex value', 12000)
    _fields(state['origin'], ('kind', 'by', 'reason', 'at'), 'Pokedex origin')
    if state['origin']['kind'] not in ('existing', 'starting_free'):
        raise ValueError('explicit Pokedex acquisition context required')
    for key in ('by', 'reason'):
        _text(state['origin'][key], 'Pokedex origin ' + key)
    C.integer(state['origin']['at'], 'Pokedex observation time', 0)
    if type(state['scans']) is not list or type(state['apps']) is not dict or type(state['uses']) is not list:
        raise ValueError('Pokedex scan/app/use collections required')
    for scan in state['scans']:
        _fields(scan, ('target_id', 'by', 'at', 'distance_m', 'readout', 'reason'), 'Pokedex scan')
        for key in ('target_id', 'by', 'reason'):
            _text(scan[key], 'scan ' + key)
        C.integer(scan['at'], 'scan time', 0)
        C.integer(scan['distance_m'], 'scan distance', 0, 10)
        _readout(scan['readout'])
    for app, receipt in state['apps'].items():
        _text(app, 'downloaded application identity')
        if app in BUILTINS:
            raise ValueError('builtin function is not an additional application')
        _fields(receipt, ('by', 'at', 'source', 'reason'), 'completed download')
        for key in ('by', 'source', 'reason'):
            _text(receipt[key], 'download ' + key)
        C.integer(receipt['at'], 'download time', 0)
    for use in state['uses']:
        _fields(use, ('function', 'by', 'at', 'observation', 'reason'), 'Pokedex use')
        _function(state, use['function'])
        for key in ('by', 'reason'):
            _text(use[key], 'Pokedex use ' + key)
        C.integer(use['at'], 'Pokedex use time', 0)
        _service(use['observation'])
    return state


def _access(engine, actor, selection, *, configured=True):
    _trainer(engine, actor)
    obj = STOCK.inspect_held(engine, actor, RULE, selection)
    if any(W.physical_lifecycle(obj)[key] for key in ('disabled', 'suppressed')):
        raise ValueError('actual Pokedex device is unavailable')
    state = validate(engine, obj)
    if configured and state is None:
        raise ValueError('actual Pokedex device needs its observation or starting grant')
    return obj, state


def validate_world(engine, index):
    for uid, obj in getattr(engine, '_physical_objects', {}).items():
        state = validate(engine, obj)
        if state is None or state['origin']['kind'] != 'starting_free':
            continue
        recipient = index.get(state['origin']['by'])
        if recipient is None or recipient.kind != 'trainer' or recipient.spec.get('pokedex_starting_instance') != uid:
            raise ValueError('starting Pokedex disagrees with its actual recipient receipt')
    for actor in index.values():
        if 'pokedex_starting_instance' not in actor.spec:
            continue
        uid = _text(actor.spec['pokedex_starting_instance'], 'starting Pokedex identity')
        state = getattr(engine, '_physical_objects', {}).get(uid, {}).get(FIELD, {})
        if state.get('origin', {}).get('kind') != 'starting_free' or state['origin'].get('by') != actor.entity_id:
            raise ValueError('starting Pokedex receipt lacks its actual physical origin')


def _new_state(actor, value_points, kind, reason, at):
    C.integer(value_points, 'Pokedex value', 12000)
    _text(reason, 'Pokedex observation reason')
    return dict(version=1, source=SOURCE, value_points=value_points,
                builtin_functions=list(BUILTINS),
                origin=dict(kind=kind, by=actor.entity_id, reason=reason, at=at),
                scans=[], apps={}, uses=[])


def configure(engine, actor, selection, *, value_points=12000, reason):
    obj, state = _access(engine, actor, selection, configured=False)
    proposed = _new_state(actor, value_points, 'existing', reason, engine.elapsed_seconds)
    if state is not None:
        if state['value_points'] != value_points:
            raise ValueError('Pokedex observation cannot reset an existing device')
        return deepcopy(state)
    def apply(e, c):
        target, _ = _access(e, c, selection, configured=False)
        target[FIELD] = deepcopy(proposed)
        return deepcopy(proposed)
    return G.transition(engine, actor, apply)


def starting(engine, actor, instance_id, *, starting_character, value_points=12000, reason):
    """GM starting-equipment observation, not category-6 creation certification."""
    _trainer(engine, actor)
    _text(instance_id, 'new actual Pokedex instance identity')
    if starting_character is not True:
        raise ValueError('GM must confirm this is a starting character')
    import campaign_rewards as REWARDS
    REWARDS.base(engine, actor, reward_source=False)
    if 'pokedex_starting_instance' in actor.spec:
        raise ValueError('this trainer already received its starting Pokedex')
    state = _new_state(actor, value_points, 'starting_free', reason, engine.elapsed_seconds)
    if instance_id in W.entity_index(engine):
        raise ValueError('starting Pokedex requires a fresh physical identity')
    def apply(e, c):
        import items as ITEMS
        W.register_object(e, instance_id, kind='item_instance', item_rule_id=RULE,
                          owner_id=c.entity_id, location={'kind': 'unknown'}, reason=reason, source=SOURCE)
        e._physical_objects[instance_id][FIELD] = deepcopy(state)
        ITEMS.register_item(e, c, RULE, source_instance_id=instance_id, as_held=True)
        c.spec['pokedex_starting_instance'] = instance_id
        e.gm._rec('starting Pokedex', None, instance_id, reason, c)
        return dict(instance_id=instance_id, price_paid=0, value_points=value_points,
                    state=deepcopy(state))
    return G.transition(engine, actor, apply, include_rulings=True)


def scan(engine, actor, target, selection, *, recognized=None, readout=None, reason):
    _access(engine, actor, selection)
    W.require_actors(engine, target)
    if target.kind != 'pokemon':
        raise ValueError('actual Pokemon scan subject required')
    _text(reason, 'scan observation reason')
    if recognized is not None and type(recognized) is not bool:
        raise ValueError('explicit camera recognition observation required')
    if recognized is not True or readout is None:
        return C.PendingDecision('GM camera recognition and sourced, disclosed scan readout')
    _fields(readout, ('species', 'average', 'individual', 'learnable_moves', 'knowledge', 'source'), 'GM scan observation')
    disclosed = deepcopy(readout)
    if disclosed['learnable_moves'] is None:
        from builder import species_lookup
        try:
            species = species_lookup(engine.r, target.spec.get('species'))
        except KeyError:
            return C.PendingDecision('GM sourced learnable moves for this uncatalogued species')
        catalog = engine.r.learnset_links.get(species['name'])
        if type(catalog) is not dict or type(catalog.get('moves')) is not list:
            return C.PendingDecision('GM sourced species learnset; no known-move-slot fallback')
        disclosed['learnable_moves'] = list(dict.fromkeys(row['to'] for row in catalog['moves'] if row.get('to')))
        disclosed['learnset_source'] = 'output/entities/learnset_links.json#' + species['name']
    else:
        disclosed['learnset_source'] = disclosed['source']
    disclosed = _readout(disclosed)
    if disclosed['species'] != target.spec.get('species'):
        raise ValueError('recognized scan species differs from the actual subject')
    for key, value in disclosed['individual'].items():
        if target.spec.get(key) is not None and value != target.spec[key]:
            raise ValueError('scan measurement differs from the observed individual')
    distance = W.distance_known(actor, target)
    if distance is None:
        return C.PendingDecision('actual shared-map scan distance; no implicit origin')
    if distance > 10:
        raise ValueError('Pokemon is outside the Pokedex 10m scan range')
    import body_modes as BODY
    if not target.on_field or target.captured or not BODY.target_visible(engine, actor, target):
        raise ValueError('actual Pokemon cannot be recognized by this camera scan')
    if engine.grid is not None and engine.grid.blocked(actor.pos, target.pos):
        raise ValueError('camera scan path is blocked')
    def apply(e, c, subject):
        obj, state = _access(e, c, selection)
        with ACTION.resolution(e, c, RULE, kind='standard'):
            if not TURN.spend(e, c, 'standard', 'Pokedex scan'):
                return C.PendingDecision('actual Pokedex Standard action unavailable')
            result = dict(target_id=subject.entity_id, by=c.entity_id, at=e.elapsed_seconds,
                          distance_m=distance, readout=deepcopy(disclosed), reason=reason)
            state['scans'].append(result)
            return deepcopy(result)
    return G.transition(engine, actor, apply, participants=(target,))


def knowledge_entry(engine, actor, selection, target, topic):
    """Read saved species information; never read the subject's current moves."""
    obj, state = _access(engine, actor, selection)
    for scan_record in reversed(state['scans']):
        readout = scan_record['readout']
        if readout['species'] != target.spec.get('species'):
            continue
        if topic == 'learnset':
            return dict(instance_id=obj['id'], answer='종의 배울 수 있는 기술 목록: ' + ', '.join(readout['learnable_moves']))
        if topic in readout['knowledge']:
            return dict(instance_id=obj['id'], answer=readout['knowledge'][topic])
    return dict(instance_id=obj['id'], answer=None)


def download(engine, actor, selection, app_id, *, download_completed, source, reason):
    _access(engine, actor, selection)
    _text(app_id, 'additional application identity')
    _text(source, 'actual completed download source')
    _text(reason, 'download observation reason')
    if type(download_completed) is not bool or app_id in BUILTINS:
        raise ValueError('explicit additional-application download observation required')
    if not download_completed:
        return C.PendingDecision('additional application must actually finish downloading')
    def apply(e, c):
        _, state = _access(e, c, selection)
        state['apps'].setdefault(app_id, dict(by=c.entity_id, at=e.elapsed_seconds, source=source, reason=reason))
        return deepcopy(state['apps'][app_id])
    return G.transition(engine, actor, apply)


def _function(state, name):
    _text(name, 'Pokedex function')
    if name not in state['builtin_functions'] and (not name.startswith('app:') or name[4:] not in state['apps']):
        raise ValueError('Pokedex application is not downloaded on this physical device')


def _service(observation):
    _fields(observation, ('source', 'available', 'content'), 'observed service result')
    _text(observation['source'], 'observed service source')
    if type(observation['available']) is not bool:
        raise ValueError('explicit actual service availability required')
    if observation['available']:
        _text(observation['content'], 'GM disclosed service result')
    elif observation['content'] is not None:
        raise ValueError('unavailable service cannot disclose a result')


def use(engine, actor, selection, function, *, observation=None, reason):
    """Consume device capabilities and GM service facts; no real-world I/O."""
    _, state = _access(engine, actor, selection)
    _text(reason, 'device function observation reason')
    _function(state, function)
    if not TURN.can_act(engine, actor):
        return C.PendingDecision('conscious actual Pokedex operator required')
    if observation is None:
        return C.PendingDecision('GM actual phone/radio/internet/application service observation')
    _service(observation)
    def apply(e, c):
        _, current = _access(e, c, selection)
        result = dict(function=function, by=c.entity_id, at=e.elapsed_seconds,
                      observation=deepcopy(observation), reason=reason)
        current['uses'].append(result)
        return deepcopy(result)
    return G.transition(engine, actor, apply)
