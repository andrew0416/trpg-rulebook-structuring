"""Reviewed native CSV Ability actions sharing one owned-state path.

Every activation is admitted from an exact CSV row, paid through the native
action/frequency ledgers, committed in ``state_grants.transition`` and linked
to the existing combat, weather, food, injury, cultivation and roll consumers.
"""
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import json
from contextvars import ContextVar

import common_checks as C
import resolution_transaction as _FINGERPRINTS


KEY = 'ability_native_actions'
HISTORY = 'ability_native_action_history'
SEQUENCE = 'ability_native_action_sequence'
TARGET_RECORDS = 'ability_native_action_effects'
PREFIX = 'ability-native:'
POLICY = 'data/ability-native-actions-policy.json'
_WEATHER_ACTIVATION=ContextVar('native_ability_weather',default=None)
SUPPORTED_KINDS = {
    'frighten',
    'sunset',
    'lunchbox',
    'designer',
    'color_theory',
    'air_lock',
    'forewarn',
    'threat',
    'gardener',
    'death_resistance',
    'leaf_guard',
    'weather',
}
COLOR_STATS = ('atk', 'def', 'spa', 'spd', 'spe', 'hp')
COLOR_NAMES = ('빨강', '주황', '노랑', '초록', '파랑', '보라')


def _digest(value):
    return _FINGERPRINTS.json_fingerprint(value, sort_keys=False, compact=True, allow_nan=True)


def policy(rules):
    data = getattr(rules, '_ability_native_actions_policy', None)
    if data is not None:
        return data
    data = json.loads((Path(rules.root) / POLICY).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or len(data.get('sources', {})) != 12:
        raise ValueError('reviewed twelve-source native Ability policy required')
    for file, digest in data.get('source_files', {}).items():
        path = Path(rules.root) / file
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('native Ability source changed: ' + file)
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.reader(stream))
    for source, row in data['sources'].items():
        expected_row_id = 'C2CSV-ABILITY-R' + str(row.get('record')).zfill(4)
        if row.get('row_id') != expected_row_id or row.get('name') is None:
            raise ValueError('exact native Ability row identity required')
        if _digest(rows[row['record'] - 1]) != row.get('source_row_sha256'):
            raise ValueError('native Ability source row changed: ' + source)
        if row.get('kind') not in SUPPORTED_KINDS:
            raise ValueError('unsupported native Ability operation')
        if rules.ability_effects.get(row['name']) != row.get('effects'):
            raise ValueError('native Ability extraction changed: ' + source)
    catalog_path = Path(rules.root) / 'output/entities/abilities.json'
    catalog_rows = json.loads(catalog_path.read_text(encoding='utf-8'))
    catalog = {
        entry['id']: entry
        for entry in catalog_rows
        if entry['id'] in data['sources']
    }
    if set(catalog) != set(data['sources']):
        raise ValueError('native Ability catalog identity missing')
    for source, row in data['sources'].items():
        if catalog[source].get('name') != row['name']:
            raise ValueError('native Ability catalog name changed: ' + source)
    rules._ability_native_actions_policy = data
    rules._ability_native_actions_catalog = catalog
    return data


# Exact CSV editions; automatic Core-book effects are deliberately separate.
WEATHER_ACTIONS = {
    'ability/촉촉바디-playtest': dict(record=388, name='촉촉바디 [Playtest]', eng='Hydration', kind='hydration', weather='rain', frequency_text='장면 - 신속 행동', frequency={'kind':'scene','uses':1,'scope':[]}, trigger='', text='사용자는 상태 이상 하나를 치료합니다. 촉촉바디의 빈도는 비바라기 날씨에서 사용할 때에는 소모되지 않습니다.'),
    'ability/선파워-playtest': dict(record=234, name='선파워 [Playtest]', eng='Solar Power', kind='solar_power', weather='sunny', frequency_text='장면 x2 - 신속 행동', frequency={'kind':'scene','uses':2,'scope':[]}, trigger='피해굴림을 굴릴 때', text='사용자는 소량의 체력을 잃고, 발동한 피해 굴림에 5 + 소량의 체력값을 보너스로 받습니다. 선파워는 쾌청날씨일 때는 빈도를 무시하고 활성할 수 있습니다.'),
    'ability/아이스바디-playtest': dict(record=276, name='아이스바디 [Playtest]', eng='Ice Body', kind='weather_heal', weather='hail', frequency_text='하루 x5 - 신속 행동', frequency={'kind':'daily','uses':5,'scope':[]}, trigger='', text='사용자는 소량의 체력을 얻습니다. 아이스바디는 오직 사용자가 체력이 절반 미만일 때 또는 싸라기눈 날씨일 때만 사용 가능합니다.\n보너스: 사용자는 싸라기눈으로부터 체력을 잃지 않습니다.'),
    'ability/젖은접시-playtest': dict(record=364, name='젖은접시 [Playtest]', eng='Rain Dish', kind='weather_heal', weather='rain', frequency_text='하루 x5 - 신속 행동', frequency={'kind':'daily','uses':5,'scope':[]}, trigger='', text='사용자는 소량의 체력을 얻습니다. 젖은접시는 오직 사용자가 체력이 절반보다 적거나 비바라기 날씨일 때만 사용할 수 있습니다.'),
    'ability/햇볕-playtest': dict(record=461, name='햇볕 [Playtest]', eng='Sun Blanket', kind='weather_heal', weather='sunny', frequency_text='하루 x5 - 신속 행동', frequency={'kind':'daily','uses':5,'scope':[]}, trigger='이니셔티브를 얻을 때', text='사용자는 소량의 체력을 얻습니다. 햇볕은 오직 체력이 절반 미만이거나 쾌청 날씨일 때 발동할 수 있습니다.'),
    'ability/햇볕-playtest-2': dict(record=496, name='햇볕 [Playtest]', eng='Sun Blanket [Playtest]', kind='weather_heal', weather='sunny', frequency_text='하루 x5 - 신속 행동', frequency={'kind':'daily','uses':5,'scope':[]}, trigger='이니셔티브를 얻을 때', text='사용자는 소량의 체력을 얻습니다. 햇볕은 오직 체력이 절반 미만이거나 쾌청 날씨일 때 발동할 수 있습니다.'),
    'ability/플라워기프트-playtest': dict(record=449, name='플라워기프트 [Playtest]', eng='Flower Gift', kind='flower_gift', weather='sunny', frequency_text='장면 - 신속 행동', frequency={'kind':'scene','uses':1,'scope':[]}, trigger='', text='플라워기프트는 오직 쾌청 날씨일 때나 체력이 절반 미만일 때 사용할 수 있습니다. 활성할 때, 사용자는 두 스탯을 고를 수 있고, 각 스탯은 +2 전투단계를 얻습니다. 2미터 이내의 모든 대상은 또한 선택한 각 스탯에서 +1 전투단계를 얻습니다.'),
}
SOLAR_POWER = 'ability/선파워-playtest'
SUN_BLANKET = ('ability/햇볕-playtest', 'ability/햇볕-playtest-2')
WEATHER_TRIGGER = 'native_weather_ability_trigger'
SOLAR_INTENT = 'native_solar_power_intent'


def weather_action_sources(rules):
    cached = getattr(rules, '_native_weather_action_sources', None)
    if cached is not None:
        return cached
    with (Path(rules.root) / 'input/db/abilities.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    catalog = {entry['id']: entry for entry in json.loads(
        (Path(rules.root) / 'output/entities/abilities.json').read_text(encoding='utf-8'))}
    result = {}
    for source, row in WEATHER_ACTIONS.items():
        raw = rows[row['record'] - 1]
        # NBSP and line endings are typography, not an alternate rule edition.
        actual = [raw[0], raw[1], ' '.join(raw[2].split()), raw[3], raw[5], raw[7]]
        expected = [row['name'], row['frequency_text'], ' '.join(row['text'].split()), row['trigger'], '2-16 Playtest', row['eng']]
        entry = catalog.get(source, {})
        if actual != expected or entry.get('name') != row['name'] or entry.get('_source', {}).get('record_span') != [row['record'], row['record']]:
            raise ValueError('native weather Ability exact CSV source changed: ' + source)
        result[source] = dict(deepcopy(row), action='swift', effects=[])
    rules._native_weather_action_sources = result
    return result


def _weather_registration(rules, value):
    rows = weather_action_sources(rules)
    matches = [source for source, row in rows.items() if value in (source, row['name'], row['eng'])]
    if not matches:
        return None
    source = value if value in rows else matches[0]
    if rules._selected_rule(source) != source:
        raise ValueError('native weather Ability source selection changed')
    equivalent = list(SUN_BLANKET) if source in SUN_BLANKET else [source]
    return {'name': rows[source]['name'], 'source_id': source, 'equivalent_source_ids': equivalent}

def definition(rules, source):
    return weather_action_sources(rules).get(source) or policy(rules)['sources'].get(source)


def registration(rules, value):
    added = _weather_registration(rules, value)
    if added is not None:
        return added
    rows = policy(rules)['sources']
    catalog = rules._ability_native_actions_catalog
    candidates = [
        uid
        for uid, row in catalog.items()
        if value in (uid, row.get('name'), row.get('eng'))
    ]
    if not candidates:
        return None
    uid = value if value in rows else candidates[0] if len(candidates) == 1 else None
    if uid is None:
        return None
    if rules._selected_rule(uid) != uid:
        raise ValueError('native Ability source selection changed')
    return {
        'name': rows[uid]['name'],
        'source_id': uid,
        'equivalent_source_ids': [uid],
    }


def deferred_registration(rules, effect):
    source = effect.get('_rule_id') if isinstance(effect, dict) else None
    if source is None and isinstance(effect, dict):
        source = (registration(rules, effect.get('_ability')) or {}).get('source_id')
    return definition(rules, source) is not None


def _state(actor):
    value = actor.spec.setdefault(KEY, {})
    if not isinstance(value, dict):
        raise ValueError('native Ability state must be a mapping')
    return value


def _history(actor):
    value = actor.spec.setdefault(HISTORY, [])
    if not isinstance(value, list):
        raise ValueError('native Ability history must be a list')
    return value


def _outer_source(actor, name):
    return getattr(actor, '_state_registration_source', None) or 'ability:' + name


def register(engine, actor, value):
    """Own registration and suppress the legacy passive/prompt fallback."""
    reg = registration(engine.r, value)
    if reg is None:
        return False
    import state_grants as G
    outer = _outer_source(actor, reg['name'])
    if outer not in G.state(actor)['sources']:
        G._source(
            actor,
            outer,
            'ability_native_registration',
            owner_id=actor.entity_id,
            rule_id=reg['source_id'],
            lifetime='while ability owned',
            tutor_points=0,
        )
    row = _state(actor).setdefault(
        reg['source_id'],
        {'source': reg['source_id'], 'registered': True},
    )
    if row.get('source') != reg['source_id'] or row.get('registered') is not True:
        raise ValueError('native Ability registration state changed')
    if reg['source_id'] == 'ability/아이스바디-playtest':
        import effects as FX
        FX.apply_passives(engine, actor, [{'type':'immunity', 'to':'hail', '_ability':reg['name'], '_rule_id':reg['source_id']}])
    if definition(engine.r,reg['source_id'])['kind']=='weather':
        # Registration grants the printed Static exception, never the weather.
        import effects as FX
        FX.apply_passives(engine,actor,[dict(effect,_ability=reg['name'],_rule_id=reg['source_id'])
            for effect in definition(engine.r,reg['source_id'])['effects'] if effect['type']=='immunity'])
    if definition(engine.r, reg['source_id'])['kind'] == 'color_theory':
        color = actor.spec.get('color_theory_birth')
        if color is None:
            row.setdefault('birth_observation_pending', True)
        else:
            if not isinstance(color, dict) or set(color) != {'roll', 'source', 'reason'}:
                raise ValueError('Color Theory needs an actual birth observation')
            _apply_color(engine, actor, reg['source_id'], color)
    return True


def _parse_request(target):
    if (
        isinstance(target, (tuple, list))
        and len(target) == 2
        and isinstance(target[1], dict)
    ):
        return (target[0], deepcopy(target[1]))
    return (target, {})


def _actual_owner(actor, reg):
    if actor.abilities_suppressed:
        raise ValueError('suppressed Ability cannot activate')
    for value in actor.abilities:
        found = registration(actor.r, value)
        if found and found['source_id'] in reg['equivalent_source_ids']:
            return
    raise ValueError('actor does not own the reviewed Ability')


def _frequency(engine, actor, target, source, declaration, action):
    import frequency as F
    if action is not None and not __import__('glitch_bender').frequency_allowed(actor,declaration['kind']):
        raise ValueError('Access Denied permits only At-Will actions this round')
    if action is not None and not __import__('focused_command').frequency_allowed(engine,actor,declaration['kind']):
        raise ValueError('Focused Command permits only At-Will actions this round')
    if declaration['kind'] == 'encounter':
        if not engine.encounter_active:
            raise ValueError('encounter Ability requires an active encounter')
        used = _state(actor).setdefault(
            source,
            {'source': source, 'registered': True},
        ).get('encounter_used')
        if used:
            raise ValueError('Ability encounter frequency exhausted')
        return ('encounter', source)
    key = F.declaration_key(engine, actor, target, source, action, declaration)
    if not F.activation_allowed(actor, key, declaration, engine=engine):
        raise ValueError('Ability frequency exhausted')
    return ('native', key)


def _consume_frequency(engine, actor, source, declaration, plan, *, action=None):
    if plan[0] == 'encounter':
        _state(actor)[source]['encounter_used'] = {
            'round': engine.round_no,
            'at': engine.elapsed_seconds,
        }
        if action is not None:__import__('focused_command').record_fact(engine,actor,source,declaration['kind'])
    else:
        import frequency as F
        F.consume_activation(actor, plan[1], declaration, engine=engine,action_actor=actor if action is not None else None)


def _pay(engine, actor, target, source, row, *, action=None, declaration=None):
    import turn as TURN
    action = row.get('action') if action is None else action
    declaration = row['frequency'] if declaration is None else declaration
    quota_source = SUN_BLANKET[0] if source in SUN_BLANKET else source
    plan = _frequency(engine, actor, target, quota_source, declaration, action)
    if action is not None and (not TURN.spend(engine, actor, action, row['name'])):
        raise ValueError('Ability action unavailable')
    _consume_frequency(engine, actor, source, declaration, plan,action=action)
    return plan


def _receipt(engine, actor, source, target_id, operation, details):
    sequence = C.integer(actor.spec.get(SEQUENCE, 0), 'native Ability sequence', 0) + 1
    frequency_state = actor.spec.get('frequency_state', {})
    record = {
        'id': actor.entity_id + ':ability-native:' + str(sequence),
        'sequence': sequence,
        'source': source,
        'actor_id': actor.entity_id,
        'target_id': target_id,
        'operation': operation,
        'details': deepcopy(details),
        'at': engine.elapsed_seconds,
        'round': engine.round_no,
        'day': frequency_state.get('day', 0),
        'scene': frequency_state.get('scene', 0),
    }
    actor.spec[SEQUENCE] = sequence
    _history(actor).append(record)
    return record


def _distance(left, right, maximum):
    import world_entities as W
    value = W.distance_known(left, right)
    if value is None:
        raise ValueError('Ability range needs actual mapped positions')
    if value > maximum:
        raise ValueError('Ability target is outside ' + str(maximum) + 'm')
    return value


def _threat(engine, actor, target, source, row, options):
    if options:
        raise ValueError('Threat takes no activation options')
    _distance(actor, target, 5)
    _pay(engine, actor, target, source, row)
    import effects as FX
    note = FX.h_stage_change(
        engine,
        actor,
        target,
        row['effects'][0],
        {'engine': engine, 'source_id': source, 'attacker': actor, 'target': target},
    )
    if note:
        raise ValueError(str(note))
    return _receipt(
        engine,
        actor,
        source,
        target.entity_id,
        'stage_change',
        {'stat': 'atk', 'delta': -1},
    )


def _death_resistance(engine, actor, target, source, row, options):
    if target is not actor:
        raise ValueError('Death Resistance targets its user')
    count = options.get('count', min(3, actor.injuries))
    if set(options) - {'count'}:
        raise ValueError('unsupported Death Resistance option')
    C.integer(count, 'Death Resistance injury count', 1, 3)
    if actor.dead or actor.injuries < count:
        raise ValueError('insufficient removable injuries')
    import injury_recovery as INJURY
    if INJURY.exempt_remaining(actor, source, 3) < count:
        raise ValueError('Death Resistance daily injury limit exhausted')
    _pay(engine, actor, target, source, row)
    healed = INJURY.heal_exempt(engine, actor, count, source=source, daily_cap=3)
    if healed != count:
        raise ValueError('Death Resistance injury result changed after preflight')
    hp = engine.heal(actor, engine.tick(actor) * healed, source_kind='feature')
    return _receipt(
        engine,
        actor,
        source,
        actor.entity_id,
        'heal_injury',
        {'injuries': healed, 'hp_gained': hp, 'tick_each': True},
    )


def _learned_moves(target):
    import move_state as M
    result = []
    for value in M.owned_list(target.spec, 'moves', target.moves,rules=target.r):
        try:
            mid = target.r.move_id(value)
            if mid is None or mid == 'struggle':
                continue
            target.r.move(mid)
        except Exception:
            continue
        if mid not in result:
            result.append(mid)
    return result


def _strongest_moves(target, choice=None):
    """Compare printed numeric DB under the user's 2026-10-23 Forewarn ruling."""
    ranked = []
    for mid in _learned_moves(target):
        move = target.r.move(mid)
        db = move.get('damage_base')
        if type(db) is int and db > 0:
            ranked.append((db, mid))
    if not ranked:
        raise ValueError('target knows no damaging Move')
    best = max((x[0] for x in ranked))
    ties = sorted((mid for db, mid in ranked if db == best))
    if choice is not None and choice not in ties:
        raise ValueError('selected Move is not strongest by printed damage base')
    return (ties, best)


def _install_owned_row(
    engine,
    actor,
    target,
    source,
    sequence,
    row,
    *,
    encounter_end=False,
    scene_end=False,
    stage_deltas=None,
):
    import combat_timing as T
    import state_grants as G

    sid = PREFIX + source + ':' + actor.entity_id + ':' + str(sequence)
    if encounter_end:
        lifetime = 'encounter_end'
    elif scene_end:
        lifetime = 'scene_end'
    else:
        lifetime = 'until replaced'
    G._source(
        target,
        sid,
        'ability_native_action',
        owner_id=actor.entity_id,
        rule_id=source,
        lifetime=lifetime,
        tutor_points=0,
    )
    G.apply_owned(engine, target, sid, lambda: target.registry.append(deepcopy(row)))
    if stage_deltas:
        import combat_stage_sources as CS
        for stat,delta in stage_deltas.items():
            CS.add_base(target,sid,stat,delta,source=sid,ends=sid)
        target.spec[G.KEY]['effects'][sid]['stages']=True
    if encounter_end or scene_end:
        timing = {'source': source, 'grant_source': sid, 'effect_contract': True}
        if encounter_end:
            timing['encounter_end'] = True
        T.install(engine, target, timing)
    return sid


def _forewarn(engine, actor, target, source, row, options):
    if set(options) - {'move_id'}:
        raise ValueError('unsupported Forewarn option')
    move_ids, db = _strongest_moves(target, options.get('move_id'))
    _pay(engine, actor, target, source, row)
    sequence = C.integer(
        actor.spec.get(SEQUENCE, 0),
        'native Ability sequence',
        0,
    ) + 1
    sid = _install_owned_row(
        engine,
        actor,
        target,
        source,
        sequence,
        {
            'type': 'accuracy_mod',
            'value': -2,
            'moves': move_ids,
            'ability_native': source,
        },
        encounter_end=True,
    )
    receipt = _receipt(
        engine,
        actor,
        source,
        target.entity_id,
        'forewarn',
        {
            'move_id': move_ids[0] if len(move_ids) == 1 else None,
            'move_ids': move_ids,
            'damage_base': db,
            'tied_candidates': move_ids,
            'grant_source': sid,
        },
    )
    target.spec.setdefault(TARGET_RECORDS, []).append(
        {
            'source': source,
            'grant_source': sid,
            'receipt_id': receipt['id'],
            'giver_id': actor.entity_id,
        }
    )
    return receipt


def _sunset(engine, actor, target, source, row, options):
    if target is not actor:
        raise ValueError('Sunset targets its user')
    mode = options.get('mode')
    if set(options) - {'mode'} or mode not in ('charge', 'spend'):
        raise ValueError('Sunset requires charge or spend mode')
    state = _state(actor)[source]
    if mode == 'charge':
        if __import__('effects').effective_weather(engine,actor) != 'sunny':
            raise ValueError('Radiant requires actual sunlight exposure')
        if state.get('radiant') is not None:
            raise ValueError('Radiant is already charged')
        _pay(engine, actor, target, source, row)
        state['radiant'] = {
            'source': source,
            'weather': 'sunny',
            'at': engine.elapsed_seconds,
            'round': engine.round_no,
        }
        return _receipt(
            engine,
            actor,
            source,
            actor.entity_id,
            'radiant_charge',
            state['radiant'],
        )
    if state.get('radiant') is None:
        raise ValueError('Sunset has no Radiant state to spend')
    if not engine.encounter_active:
        raise ValueError('Sunset combat-stage benefit requires an active encounter')
    import turn as TURN
    if not TURN.spend(engine, actor, 'swift', row['name']):
        raise ValueError('Ability action unavailable')
    state.pop('radiant')
    sequence = C.integer(
        actor.spec.get(SEQUENCE, 0),
        'native Ability sequence',
        0,
    ) + 1
    sid = _install_owned_row(
        engine,
        actor,
        actor,
        source,
        sequence,
        {
            'type': 'accuracy_mod',
            'value': 2,
            'moves': 'all',
            'ability_native': source,
        },
        scene_end=True,
        stage_deltas={'atk': 2},
    )
    return _receipt(
        engine,
        actor,
        source,
        actor.entity_id,
        'radiant_spend',
        {'attack_stage': 2, 'accuracy': 2, 'grant_source': sid},
    )


def _trainer_for(engine, target):
    import world_entities as W
    index = W.actor_index(engine)
    identity = target.spec.get('trainer_id')
    if identity in index:
        return index[identity]
    name = target.spec.get('trainer')
    return next(
        (c for c in index.values() if c.kind == 'trainer' and c.name == name),
        None,
    )


def _frighten_can_travel(engine, target, position, mode):
    import body_state as BODY
    import map_terrain as TERRAIN
    bases = {TERRAIN.base_at(engine.grid, point) for point in BODY.at_position(target, position)}
    if mode == 'swim' and bases != {'underwater'}:
        return False
    if mode == 'burrow' and (bases != {'earth'} or not target.spec.get('_burrow', {}).get('underground')):
        return False
    return TERRAIN.can_travel(engine, target, position, mode)


def _frighten_path(engine, actor, target, distance, mode):
    import body_state as BODY
    import map_terrain as TERRAIN
    import movement_actions as MOVEMENT
    import world_entities as W
    from grid import cheb
    origin = tuple(W.grid_cell(target))
    user = tuple(W.grid_cell(actor))
    trainer = _trainer_for(engine, target)
    trainer_cell = None if trainer is None else tuple(W.grid_cell(trainer))
    paths = [((origin,), 0, getattr(target, '_diagonal_steps', 0))]
    choices = list(paths)
    for _ in range(distance):
        expanded = []
        for path, spent, diagonals in paths:
            x, y = path[-1]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (x + dx, y + dy)
                    cannot_place = not BODY.can_place(
                        engine,
                        target,
                        q,
                        origin=path[-1],
                    )
                    if ((dx, dy) == (0, 0) or q in path or cannot_place
                            or not _frighten_can_travel(engine, target, q, mode)):
                        continue
                    step, next_diagonals = MOVEMENT.step_cost(path[-1], q, diagonals)
                    cost = spent + step * TERRAIN.slow_multiplier(engine, target, q, mode)
                    if cost <= distance:
                        expanded.append((path + (q,), cost, next_diagonals))
        if not expanded:
            break
        paths = expanded
        choices.extend(paths)
    if len(choices) == 1:
        return [origin]
    start = cheb(origin, user)

    def score(choice):
        path, spent, _ = choice
        end = path[-1]
        away = cheb(end, user)
        toward = 0 if trainer_cell is None else -cheb(end, trainer_cell)
        return (
            away > start,
            away,
            toward,
            tuple(-v for point in path for v in point),
        )
    return list(max(choices, key=score)[0])


def _frighten(engine, actor, target, source, row, options):
    if set(options) - {'source_policy'}:
        raise ValueError('unsupported Frighten activation options')
    selected = options.get('source_policy', 'kr_csv_r0015_movement')
    if selected not in ('kr_csv_r0015_movement', 'en_core105_speed_stages'):
        raise ValueError('unknown Frighten source policy')
    if target is actor:
        raise ValueError('Frighten requires another target')
    _distance(actor, target, 5)
    if selected == 'en_core105_speed_stages':
        from source_context import verified_source
        verified_source(engine.r, {'file': 'source-audit/frighten-core105.txt',
            'sha256': '516309f168855376068b87d5b2016bca92ba118ceeb64447375c0cf8e4a577cf'},
            label='Frighten Core1.05', source_root='source-audit')
        _pay(engine, actor, target, source, row,
             declaration={'kind': 'scene', 'uses': 1, 'scope': []})
        import effects as FX
        note = FX.h_stage_change(engine, actor, target,
            {'type': 'stage_change', 'stat': 'spe', 'delta': -2, 'target': 'target'},
            {'engine': engine, 'source_id': source, 'attacker': actor, 'target': target})
        if note:
            raise ValueError(str(note))
        return _receipt(engine, actor, source, target.entity_id, 'frighten',
            {'source_policy': selected, 'source_reference': 'PTU Core1.05 p318 / Frighten',
             'stat': 'spe', 'delta': -2})
    import frequency as F
    import movement_actions as MOVEMENT

    movement = MOVEMENT.capabilities(engine, target)
    origin = tuple(target.pos)
    mode, value = max(
        ((key, engine.move_profile(target, movement_mode=key)[0])
         for key, value in movement.items() if key in MOVEMENT.MODES and value > 0
         and _frighten_can_travel(engine, target, origin, key)),
        key=lambda item: (item[1], item[0]),
        default=("land", 0),
    )
    requested = min(3, value)
    path = _frighten_path(engine, actor, target, requested, mode)
    global_plan = _frequency(
        engine,
        actor,
        target,
        source,
        row['frequency'],
        row['action'],
    )
    target_key = F.declaration_key(
        engine,
        actor,
        target,
        source,
        row['action'],
        row['target_frequency'],
    )
    if not F.activation_allowed(actor, target_key, row['target_frequency'], engine=engine):
        raise ValueError('Frighten already used on this target this scene')
    import turn as TURN
    if not TURN.spend(engine, actor, row['action'], row['name']):
        raise ValueError('Ability action unavailable')
    _consume_frequency(engine, actor, source, row['frequency'], global_plan,action=row['action'])
    F.consume_activation(actor, target_key, row['target_frequency'], engine=engine)
    import forced_movement as FORCED
    import coat_effects as COATS
    if len(path) > 1 and not any(record['effect']['blocks_push_pull'] for record in COATS.live(target)):
        MOVEMENT.entry_mode(target, '공중/부유' if mode in ('sky', 'levitate') else mode)
    result = FORCED.along_path(
        engine,
        actor,
        target,
        points=path,
        source=source,
    )
    import combat_timing as TIMING
    import effect_lifetimes as LIFE

    effect = row['effects'][1]
    record = LIFE.prepare(engine, actor, target, effect, source)
    TIMING.install(engine, target, record)
    return _receipt(
        engine,
        actor,
        source,
        target.entity_id,
        'frighten',
        {
            'source_policy': selected,
            'source_reference': 'C2CSV-ABILITY-R0015',
            'movement_mode': mode,
            'movement_value': value,
            'displacement': result,
            'slow': '1 round',
        },
    )


def _air_lock(engine, actor, target, source, row, options):
    if target is not actor or set(options) - {'mode'}:
        raise ValueError('Air Lock targets its user')
    if not engine.encounter_active or engine.round_start_seconds is None:
        raise ValueError('Air Lock requires an open combat round')
    state = _state(actor)[source]
    active = state.get('air_lock')
    mode = options.get('mode', 'sustain' if active else 'start')
    if mode == 'start':
        if active:
            raise ValueError('Air Lock is already active')
        _pay(engine, actor, target, source, row)
        import weather_state as WEATHER
        WEATHER.clear(
            engine,
            source_id=source,
            reason='Air Lock holds normal weather',
        )
        state['air_lock'] = {
            'source': source,
            'started_round': engine.round_no,
            'sustain_round': engine.round_no,
            'at': engine.elapsed_seconds,
        }
        return _receipt(
            engine,
            actor,
            source,
            actor.entity_id,
            'air_lock_start',
            state['air_lock'],
        )
    if mode != 'sustain' or not active:
        raise ValueError('Air Lock sustain needs its active source')
    if active['sustain_round'] >= engine.round_no:
        raise ValueError('Air Lock already sustained this round')
    import turn as TURN
    if not TURN.spend(engine, actor, 'swift', row['name'] + ' sustain'):
        raise ValueError('Air Lock sustain action unavailable')
    active['sustain_round'] = engine.round_no
    return _receipt(
        engine,
        actor,
        source,
        actor.entity_id,
        'air_lock_sustain',
        {'sustain_round': engine.round_no},
    )


def _lunchbox(engine, actor, target, source, row, options):
    if target is not actor or set(options) != {'receipt_sequence'}:
        raise ValueError('Lunchbox requires one actual consumed-food receipt')
    sequence = C.integer(
        options['receipt_sequence'],
        'food consumption receipt sequence',
        1,
    )
    receipts = actor.spec.get('food_consumption_receipts', [])
    if not isinstance(receipts, list) or sequence > len(receipts):
        raise ValueError('actual consumed-food receipt required')
    food = receipts[sequence - 1]
    if __import__('food_effects').retained_activation(food):
        raise ValueError('Lunchbox requires consumed food, not a retained Harvest activation')
    if (
        food.get('sequence') != sequence
        or food.get('at') != engine.elapsed_seconds
        or not isinstance(food.get('benefit'), dict)
    ):
        raise ValueError('Lunchbox must follow the actual completed Food Buff consumption')
    if source in food.get('ability_native_claims', []):
        raise ValueError('Food Buff receipt already used by Lunchbox')
    import temporary_hp as TEMP
    blocked = TEMP.blocked_reason(actor)
    if blocked is not None:
        raise ValueError('Lunchbox temporary HP grant was blocked: ' + blocked)
    _pay(engine, actor, target, source, row)
    provenance = {
        'source': source,
        'food_receipt': sequence,
        'buff_id': food.get('buff_id'),
    }
    gained = TEMP.grant(
        engine,
        actor,
        engine.tick(actor),
        stack=True,
        provenance=provenance,
        contribution_source=TEMP.food_source(actor, 'lunchbox', food),
    )
    food.setdefault('ability_native_claims', []).append(source)
    return _receipt(
        engine,
        actor,
        source,
        actor.entity_id,
        'lunchbox',
        {
            'food_receipt': sequence,
            'buff_id': food.get('buff_id'),
            'temporary_hp': gained,
        },
    )


def _designer(engine, actor, target, source, row, options):
    if target is not actor or set(options) != {'types'}:
        raise ValueError('Designer requires exactly two clothing types')
    values = options['types']
    if (
        not isinstance(values, (list, tuple))
        or len(values) != 2
        or len(set(values)) != 2
    ):
        raise ValueError('Designer requires two distinct types')
    import state_grants as G
    import type_state as TYPES
    import ability_state_projection as PROJECTION

    TYPES.validate_types(engine.r, values, label='Designer leaf clothing types')
    leafy = PROJECTION.prepare_designer(engine, actor)
    _pay(engine, actor, target, source, row)
    state = _state(actor)[source]
    old = state.get('garment')
    if old is not None:
        G.revoke(actor, old['grant_source'], engine=engine)
        state.setdefault('destroyed_garments', []).append(
            dict(old, destroyed_at=engine.elapsed_seconds)
        )
    sequence = C.integer(
        actor.spec.get(SEQUENCE, 0),
        'native Ability sequence',
        0,
    ) + 1
    sid = PREFIX + source + ':garment:' + str(sequence)
    G._source(
        actor,
        sid,
        'ability_native_action',
        owner_id=actor.entity_id,
        rule_id=source,
        lifetime='until replaced',
        tutor_points=0,
    )
    effects = [
        {
            'type': 'resistance_step',
            'value': 1,
            'types': [value],
            'ability_native': source,
        }
        for value in values
    ]
    G.apply_owned(
        engine,
        actor,
        sid,
        lambda: actor.modifiers.extend(deepcopy(effects)),
    )
    garment = {
        'grant_source': sid,
        'types': list(values),
        'created_at': engine.elapsed_seconds,
        'sequence': sequence,
    }
    if leafy is not None:
        garment['leafy_cloak'] = leafy
    state['garment'] = garment
    receipt = _receipt(engine, actor, source, actor.entity_id, 'designer', garment)
    PROJECTION.complete_designer(engine, actor, receipt)
    return receipt


def _leaf_guard(engine, actor, target, source, row, options):
    if target is not actor or set(options)-{'status'}:
        raise ValueError('Leaf Guard cures one affliction of its actual user')
    import status_sets as STATUS
    import effects as FX
    afflictions = STATUS.afflictions(actor)
    status = options.get('status')
    if status is None and len(afflictions) == 1:
        status = afflictions[0]
    if not isinstance(status, str) or STATUS.normalize(status) not in afflictions:
        raise ValueError('Leaf Guard requires one actual chosen Status Affliction')
    status = STATUS.normalize(status)
    sunny = FX.weather_matches(engine, 'sunny', actor) and not __import__('survivalist_class').weather_ability_suppressed(engine,actor,source)
    _pay(engine, actor, target, source, row,
         declaration={'kind': 'at_will', 'uses': 1, 'scope': []} if sunny else row['frequency'])
    engine.cure_status(actor, status)
    return _receipt(engine, actor, source, actor.entity_id, 'leaf_guard',
                    {'status': status, 'ignored_scene_frequency': sunny})


def _weather_benefit(engine, actor, source, weather):
    import effects as FX
    import survivalist_class as SC
    return FX.weather_matches(engine, weather, actor) and not SC.weather_ability_suppressed(engine, actor, source)


def _weather_or_low_hp(engine, actor, source, row):
    return actor.hp * 2 < actor.base_max_hp or _weather_benefit(engine, actor, source, row['weather'])


def _weather_owner(engine, actor):
    import turn as TURN
    import heavy_injury_adapter as HEAVY
    import effect_contracts as CONTRACTS
    import passive_events as PASSIVE
    HEAVY.ensure_clear(engine)
    CONTRACTS.ensure_clear(engine)
    PASSIVE.ensure_clear(engine)
    if actor.dead or actor.fainted or actor.captured or not actor.on_field or not TURN.can_act(engine, actor):
        raise ValueError('weather Ability requires its actual able user')


def _hydration(engine, actor, target, source, row, options):
    _weather_owner(engine, actor)
    if target is not actor or set(options) - {'status'}:
        raise ValueError('Hydration cures one affliction of its actual user')
    import status_sets as STATUS
    afflictions = STATUS.afflictions(actor)
    status = options.get('status')
    if status is None and len(afflictions) == 1:
        status = afflictions[0]
    if not isinstance(status, str) or STATUS.normalize(status) not in afflictions:
        raise ValueError('Hydration requires one actual chosen Status Affliction')
    status = STATUS.normalize(status)
    rain = _weather_benefit(engine, actor, source, row['weather'])
    _pay(engine, actor, target, source, row,
         declaration={'kind':'at_will','uses':1,'scope':[]} if rain else row['frequency'])
    engine.cure_status(actor, status)
    return _receipt(engine, actor, source, actor.entity_id, 'hydration',
                    {'status':status, 'ignored_scene_frequency':rain})


def initiative_gained(engine, actor):
    """Native turn producer; a caller-supplied initiative flag is not authority."""
    actor.spec.pop(SOLAR_INTENT, None)
    if not any((_weather_registration(engine.r, value) or {}).get('source_id') in SUN_BLANKET for value in actor.abilities):
        return
    actor.spec[WEATHER_TRIGGER] = {
        'round':engine.round_no, 'turn':actor.custom_conditions.get('combat_turn_serial', 0),
        'at':engine.elapsed_seconds, 'actions':deepcopy(getattr(actor, '_action_history', [])),
        'used':False,
    }
    event = actor.spec[WEATHER_TRIGGER]
    event['fingerprint'] = _digest({key:value for key,value in event.items() if key != 'used'})


def _initiative_trigger(engine, actor):
    event = actor.spec.get(WEATHER_TRIGGER)
    if (not isinstance(event, dict) or event.get('used') is not False
            or event.get('fingerprint') != _digest({key:value for key,value in event.items() if key not in ('used','fingerprint')})
            or getattr(engine, '_active_turn_actor', None) is not actor
            or event.get('round') != engine.round_no or event.get('at') != engine.elapsed_seconds
            or event.get('turn') != actor.custom_conditions.get('combat_turn_serial', 0)
            or event.get('actions') != getattr(actor, '_action_history', [])):
        raise ValueError('Sun Blanket requires its actual initiative-gain boundary before another action')
    return event


def _weather_heal(engine, actor, target, source, row, options):
    _weather_owner(engine, actor)
    if target is not actor or options:
        raise ValueError('weather healing targets its actual user without options')
    event = _initiative_trigger(engine, actor) if source in SUN_BLANKET else None
    if not _weather_or_low_hp(engine, actor, source, row):
        raise ValueError('weather healing requires unsuppressed weather or HP below half')
    tick = engine.tick(actor)
    _pay(engine, actor, target, source, row)
    gained = engine.heal(actor, tick, source_kind='feature')
    if event is not None:
        actor.spec[WEATHER_TRIGGER]['used'] = True
    return _receipt(engine, actor, source, actor.entity_id, 'weather_heal',
                    {'tick':tick, 'healed':gained, 'initiative_turn':event['turn'] if event else None})


def _flower_gift(engine, actor, target, source, row, options):
    _weather_owner(engine, actor)
    stats = options.get('stats')
    if (target is not actor or set(options) != {'stats'} or not isinstance(stats, (list, tuple))
            or len(stats) != 2 or any(stat not in ('atk','def','spa','spd','spe') for stat in stats)
            or stats[0] == stats[1]):
        raise ValueError('Flower Gift requires two distinct non-HP combat stats')
    if not _weather_or_low_hp(engine, actor, source, row):
        raise ValueError('Flower Gift requires unsuppressed sun or HP below half')
    import world_entities as W
    import effects as FX
    recipients = []
    for other in W.actor_index(engine).values():
        if other is actor or not other.on_field or other.dead:
            continue
        distance = W.distance_known(actor, other)
        if distance is None:
            raise ValueError('Flower Gift requires actual positions for all field recipients')
        if distance <= 2:
            recipients.append(other)
    _pay(engine, actor, target, source, row)
    for recipient in [actor] + recipients:
        for stat in stats:
            note = FX.h_stage_change(engine, actor, recipient,
                {'type':'stage_change','stat':stat,'delta':2 if recipient is actor else 1},
                {'engine':engine,'source_id':source,'attacker':actor,'target':recipient})
            if note:
                raise ValueError(str(note))
    return _receipt(engine, actor, source, actor.entity_id, 'flower_gift',
        {'stats':list(stats), 'self_delta':2, 'other_delta':1, 'recipient_ids':[other.entity_id for other in recipients]})


def _solar_power(engine, actor, target, source, row, options):
    """Choose a forthcoming native roll; payment occurs only at that roll."""
    _weather_owner(engine, actor)
    if target is not actor or set(options) != {'move_id'}:
        raise ValueError('Solar Power requires the chosen actual damaging Move')
    move_id = options['move_id']
    if (getattr(engine, '_active_turn_actor', None) is not actor or move_id not in actor.moves
            or engine.r.move(move_id).get('class') not in ('물리', '특수')):
        raise ValueError('Solar Power requires the user turn and a known damaging Move')
    if actor.spec.get(SOLAR_INTENT) is not None:
        raise ValueError('Solar Power already has a chosen damage roll')
    details = {'move_id':move_id, 'turn':actor.custom_conditions.get('combat_turn_serial', 0),
               'round':engine.round_no, 'at':engine.elapsed_seconds}
    receipt = _receipt(engine, actor, source, actor.entity_id, 'solar_power_choice', details)
    actor.spec[SOLAR_INTENT] = dict(details, receipt_id=receipt['id'])
    return receipt


def solar_power_interested(actor):
    return isinstance(actor.spec.get(SOLAR_INTENT), dict)


def _solar_power_damage(engine, actor, target, move, event):
    """Consume one choice at an actual native damage roll, never a preview."""
    intent = actor.spec.get(SOLAR_INTENT)
    if intent is None or intent.get('move_id') != move['id']:
        return 0
    if event is None:
        return 0
    if (engine._passive_events.get(event.get('id')) is not event or event.get('phase') != 'activated'
            or event.get('actor') is not actor or event.get('target') is not target
            or event.get('move_id') != move['id']):
        raise ValueError('Solar Power requires its actual native damage event')
    import passive_events as PASSIVE
    observations = PASSIVE.observations(engine, event['id'])
    if not observations or observations[-1]['stage'] != 'accuracy' or not observations[-1]['facts']['hit']:
        raise ValueError('Solar Power requires an actual hit before damage')
    if (intent.get('round') != engine.round_no or intent.get('at') != engine.elapsed_seconds
            or intent.get('turn') != actor.custom_conditions.get('combat_turn_serial', 0)):
        raise ValueError('Solar Power choice belongs to an expired turn')
    choices = [r for r in actor.spec.get(HISTORY, []) if r['id'] == intent.get('receipt_id')]
    if len(choices) != 1 or choices[0]['source'] != SOLAR_POWER or choices[0]['operation'] != 'solar_power_choice' or choices[0]['details'] != {k:v for k,v in intent.items() if k != 'receipt_id'}:
        raise ValueError('Solar Power lost its actual source choice receipt')
    reg = registration(engine.r, SOLAR_POWER)
    _actual_owner(actor, reg)
    _weather_owner(engine, actor)
    row = definition(engine.r, SOLAR_POWER)
    sunny = _weather_benefit(engine, actor, SOLAR_POWER, row['weather'])
    tick = engine.tick(actor)
    if actor.hp + actor.temp_hp < tick:
        raise ValueError('Solar Power requires its full tick HP cost')
    # The damage producer issued its receipt before this real Swift payment.
    # Authenticate it while its original action count is still current, then
    # advance only that receipt across the exact action this owner produces.
    import heavy_injury_adapter as HEAVY
    candidates = [(token, receipt) for token, receipt in engine._heavy_native_receipts.items()
                  if receipt['attacker'] is actor and receipt['target'] is target
                  and receipt['move_id'] == move['id']
                  and receipt.get('completion_id') == event.get('completion_id')]
    if len(candidates) != 1:
        raise ValueError('Solar Power requires one actual native damage receipt')
    token, receipt = candidates[0]
    HEAVY.validate_native_receipt(engine, token, actor, target, move)
    history = list(actor._action_history)
    _pay(engine, actor, actor, SOLAR_POWER, row,
         declaration={'kind':'at_will','uses':1,'scope':[]} if sunny else row['frequency'])
    if actor._action_history != history + ['swift']:
        raise ValueError('Solar Power payment must append exactly its Swift action')
    receipt['history_length'] = len(actor._action_history)
    HEAVY.validate_native_receipt(engine, token, actor, target, move)
    before = actor.hp + actor.temp_hp
    engine.lose_hp(actor, tick, source=SOLAR_POWER)
    if before - actor.hp - actor.temp_hp != tick:
        raise ValueError('Solar Power tick HP cost was prevented')
    actor.spec.pop(SOLAR_INTENT)
    _receipt(engine, actor, SOLAR_POWER, target.entity_id, 'solar_power',
             {'event_id':event['id'], 'move_id':move['id'], 'tick_cost':tick,
              'bonus':5 + tick, 'ignored_scene_frequency':sunny, 'choice_receipt':intent['receipt_id']})
    return 5 + tick

def solar_power_damage(engine, actor, target, move, event):
    if not solar_power_interested(actor) or event is None:
        return 0
    import state_grants as G
    # roll_damage receives resolve_attack_damage's reaction envelope. Its
    # passive_event key identifies the registered native accuracy occurrence.
    native = engine._passive_events.get(event.get('passive_event'))
    if (native is None or event.get('attacker') is not actor or event.get('target') is not target
            or event.get('move', {}).get('id') != move['id']):
        raise ValueError('Solar Power requires its actual native damage event')
    event_id = native['id']
    return G.transition(engine, actor,
        lambda staged, owner, recipient: _solar_power_damage(
            staged, owner, recipient, move, staged._passive_events[event_id]),
        participants=(target,), include_rulings=True)

def _color_payload(roll):
    C.integer(roll, 'Color Theory birth d12', 1, 12)
    if roll % 2:
        idx = (roll - 1) // 2
        return {
            'roll': roll,
            'color': COLOR_NAMES[idx],
            'deltas': {COLOR_STATS[idx]: 6},
        }
    left = roll // 2 - 1
    right = (left + 1) % 6
    return {
        'roll': roll,
        'color': COLOR_NAMES[left] + '-' + COLOR_NAMES[right],
        'deltas': {
            COLOR_STATS[left]: 3,
            COLOR_STATS[right]: 3,
        },
    }


def _apply_color(engine, actor, source, observation):
    payload = _color_payload(observation['roll'])
    state = _state(actor)[source]
    current = state.get('color_theory')
    import state_grants as G
    if current is not None:
        if current['observation'] != observation:
            raise ValueError('Color Theory birth roll cannot change')
        sid = _outer_source(actor, definition(engine.r, source)['name'])
        ledgers = actor.spec.get(G.KEY, {}).get('stat_sources', {})
        for index, (stat, delta) in enumerate(payload['deltas'].items()):
            operation = 'color:' + str(index)
            source_operations = (
                ledgers.get(stat, {})
                .get('sources', {})
                .get(sid, {})
            )
            if operation not in source_operations:
                G.stat(actor, stat, delta, sid, operation_id=operation)
        return current
    sid = _outer_source(actor, definition(engine.r, source)['name'])
    for index, (stat, delta) in enumerate(payload['deltas'].items()):
        G.stat(actor, stat, delta, sid, operation_id='color:' + str(index))
    current = {'source': source, 'observation': deepcopy(observation), **payload}
    state['color_theory'] = current
    state.pop('birth_observation_pending', None)
    return current


def _color_theory(engine, actor, target, source, row, options):
    if target is not actor or set(options) != {'birth_roll', 'reason'}:
        raise ValueError('Color Theory needs its actual birth roll and reason')
    if not isinstance(options['reason'], str) or not options['reason'].strip():
        raise ValueError('Color Theory observation reason required')
    observation = {
        'roll': options['birth_roll'],
        'source': 'ability/색채이론',
        'reason': options['reason'],
    }
    result = _apply_color(engine, actor, source, observation)
    actor.spec['color_theory_birth'] = deepcopy(observation)
    return _receipt(engine, actor, source, actor.entity_id, 'color_theory', result)


def _gardener(engine, actor, target, source, row, options):
    if not hasattr(target, 'spec') or set(options) != {'plant_id'}:
        raise ValueError('Gardener requires an actual plant owner and plant ID')
    plant_id = options['plant_id']
    if not isinstance(plant_id, str) or not plant_id.strip():
        raise ValueError('actual plant identity required')
    plant = target.spec.get('plants', {}).get(plant_id)
    if not isinstance(plant, dict):
        raise ValueError('actual identified harvest plant required')
    import crafting_activities as ACTIVITIES
    import cultivation_growth as GROWTH

    day = ACTIVITIES._day(target)
    already_applied = any(
        application.get('ability_application', {}).get('source') == source
        and application.get('day') == day
        for application in plant.get('mulch_applications', [])
    )
    if already_applied:
        raise ValueError('Gardener already applied to this plant today')
    value = (
        plant.get('growth', {})
        .get('definition', {})
        .get('fertilizer', GROWTH.native_fertilizer())
    )
    observed = GROWTH.status(
        engine,
        target,
        plant_id,
        environment_allows_growth=True,
        soil_quality=0,
    )
    before = (
        observed['soil_base']
        + observed['site_bonus']
        + observed['fertilizer_bonus']
    )
    if before + value['delta'] > value['soil_cap']:
        raise ValueError('Gardener cannot exceed the fertilizer soil cap')
    _pay(engine, actor, target, source, row)
    sequence = C.integer(
        actor.spec.get(SEQUENCE, 0),
        'native Ability sequence',
        0,
    ) + 1
    application = {
        'source': source,
        'sequence': len(plant.setdefault('mulch_applications', [])) + 1,
        'day': day,
        'soil_base': observed['soil_base'],
        'site_bonus': observed['site_bonus'],
        'before_soil': before,
        'after_soil': before + value['delta'],
        'timing_policy': 'ability-current-day',
        'reason': 'Gardener Ability application',
        'payment': {
            'kind': 'ability',
            'source': source,
            'actor_id': actor.entity_id,
            'count': 0,
            'at': engine.elapsed_seconds,
        },
        'growth_policy': deepcopy(value),
        'applied_at': engine.elapsed_seconds,
        'applied_session': engine.session_epoch,
        'ability_application': {
            'source': source,
            'provider_id': actor.entity_id,
            'activation_sequence': sequence,
        },
    }
    plant['mulch_applications'].append(application)
    import cultivation_state as CULTIVATION
    CULTIVATION.validate(target)
    GROWTH.validate_world(engine, __import__('world_entities').actor_index(engine))
    return _receipt(
        engine,
        actor,
        source,
        plant_id,
        'gardener',
        {
            'plant_id': plant_id,
            'plant_owner_id': target.entity_id,
            'application_sequence': application['sequence'],
            'soil_delta': value['delta'],
        },
    )


def weather_contract(engine,actor,source,weather,rounds):
    frame=_WEATHER_ACTIVATION.get()
    if (frame is None or frame['engine'] is not engine or frame['actor'] is not actor
            or frame['source']!=source or frame['weather']!=weather or frame['rounds']!=rounds):
        raise ValueError('actual paid native Ability weather activation required')
    return frame['activation_id']


def validate_weather_record(engine,record,index=None):
    import world_entities as W
    row=definition(engine.r,record['source_id'])
    actor=(W.actor_index(engine) if index is None else index).get(record.get('actor_id'))
    if row is None or row['kind']!='weather' or actor is None:
        raise ValueError('weather needs its actual reviewed Ability producer')
    histories=actor.spec.get(HISTORY,[])
    receipt=next((r for r in histories if r.get('id')==record.get('ability_activation_id')),None)
    if (receipt is None or receipt.get('source')!=record['source_id'] or receipt.get('actor_id')!=actor.entity_id
            or receipt.get('target_id')!=actor.entity_id or receipt.get('operation')!='weather'
            or receipt.get('details')!={'weather':row['weather'],'rounds':row['rounds']}
            or record['weather']!=row['weather'] or record['duration']!=row['rounds']+2*len(record.get('trickster_extensions',[]))
            or receipt.get('round')!=record['started_round']):
        raise ValueError('Ability weather occurrence differs from its actual paid producer')


def _weather(engine,actor,target,source,row,options):
    if target is not actor or options:raise ValueError('weather Ability is an explicit Self activation without options')
    import environment_change as EC
    if EC.has_pending(engine) and not getattr(engine,'_environment_change_depth',0):
        return EC.run(engine,actor,lambda e,a:_weather(e,a,a,source,row,options))
    import weather_state as WEATHER
    _pay(engine,actor,target,source,row)
    receipt=_receipt(engine,actor,source,actor.entity_id,'weather',{'weather':row['weather'],'rounds':row['rounds']})
    token=_WEATHER_ACTIVATION.set({'engine':engine,'actor':actor,'source':source,'weather':row['weather'],
        'rounds':row['rounds'],'activation_id':receipt['id']})
    try:
        weather=WEATHER.set_weather(engine,row['weather'],rounds=row['rounds'],source_id=source,
            origin='ability',actor=actor,reason='actual explicit native Ability activation')
    finally:_WEATHER_ACTIVATION.reset(token)
    return receipt


HANDLERS = {
    'hydration': _hydration,
    'weather_heal': _weather_heal,
    'solar_power': _solar_power,
    'flower_gift': _flower_gift,
    'weather': _weather,
    'threat': _threat,
    'death_resistance': _death_resistance,
    'forewarn': _forewarn,
    'sunset': _sunset,
    'frighten': _frighten,
    'air_lock': _air_lock,
    'lunchbox': _lunchbox,
    'designer': _designer,
    'leaf_guard': _leaf_guard,
    'color_theory': _color_theory,
    'gardener': _gardener,
}


def activate(engine, actor, ability, target):
    reg = registration(engine.r, ability)
    if reg is None:
        raise ValueError('reviewed native Ability required')
    _actual_owner(actor, reg)
    subject, options = _parse_request(target)
    import state_grants as G
    import world_entities as W

    W.require_actors(engine, actor)
    participants = ()
    if hasattr(subject, 'entity_id'):
        W.require_actors(engine, subject)
        participants = () if subject is actor else (subject,)
    else:
        raise ValueError('native Ability target must be an actual actor')
    row = definition(engine.r, reg['source_id'])
    if row['kind'] == 'flower_gift':
        participants = tuple(other for other in W.actor_index(engine).values() if other is not actor)

    def apply(staged, a, *others):
        actual = a if subject is actor else others[0]
        return HANDLERS[row['kind']](
            staged,
            a,
            actual,
            reg['source_id'],
            row,
            options,
        )

    return G.transition(
        engine,
        actor,
        apply,
        participants=participants,
        include_grid=row['kind'] == 'frighten',
    )


def weather_locked(engine):
    import weather_state as WEATHER
    if WEATHER.sample_negation_complete(engine,'ability/에어록'):return None
    import world_entities as W
    for actor in W.actor_index(engine).values():
        record = (
            actor.spec.get(KEY, {})
            .get('ability/에어록', {})
            .get('air_lock')
        )
        available = (
            not actor.abilities_suppressed
            and actor.on_field
            and not actor.captured
            and not actor.fainted
        )
        if record and available:
            owns_air_lock = any(
                (registration(engine.r, ability) or {}).get('source_id')
                == 'ability/에어록'
                for ability in actor.abilities
            )
            if owns_air_lock:
                return actor
    return None


def weather_boundary(engine, *, round_end=False):
    if not round_end:
        return
    import world_entities as W
    for actor in W.actor_index(engine).values():
        state = actor.spec.get(KEY, {}).get('ability/에어록', {})
        record = state.get('air_lock')
        if record and record['sustain_round'] < engine.round_no:
            state.setdefault('air_lock_history', []).append(
                dict(
                    record,
                    ended_round=engine.round_no,
                    reason='swift sustain missing',
                )
            )
            state.pop('air_lock', None)


def end_encounter(engine, actors):
    for actor in actors:
        actor.spec.pop(SOLAR_INTENT, None)
        actor.spec.pop(WEATHER_TRIGGER, None)
        for source, state in actor.spec.get(KEY, {}).items():
            state.pop('encounter_used', None)
            if source == 'ability/에어록' and state.get('air_lock'):
                state.setdefault('air_lock_history', []).append(
                    dict(
                        state['air_lock'],
                        ended_round=engine.round_no,
                        reason='encounter ended',
                    )
                )
                state.pop('air_lock', None)


def validate_world(engine, index):
    policy(engine.r)
    receipts = {}
    for actor in index.values():
        sequence = C.integer(
            actor.spec.get(SEQUENCE, 0),
            'native Ability sequence',
            0,
        )
        history = actor.spec.get(HISTORY, [])
        if not isinstance(history, list) or len(history) != sequence:
            raise ValueError('native Ability sequence/history mismatch')
        for number, record in enumerate(history, 1):
            expected_id = actor.entity_id + ':ability-native:' + str(number)
            invalid_identity = (
                not isinstance(record, dict)
                or record.get('sequence') != number
                or record.get('id') != expected_id
            )
            if invalid_identity:
                raise ValueError('native Ability receipt identity mismatch')
            invalid_provenance = (
                record.get('actor_id') != actor.entity_id
                or definition(engine.r, record.get('source')) is None
                or record.get('at', 0) > engine.elapsed_seconds
                or record.get('round', 0) > engine.round_no
            )
            if invalid_provenance:
                raise ValueError('native Ability receipt provenance invalid')
            receipts[record['id']] = record
        for source, state in actor.spec.get(KEY, {}).items():
            invalid_registration = (
                definition(engine.r, source) is None
                or state.get('source') != source
                or state.get('registered') is not True
            )
            if invalid_registration:
                raise ValueError('native Ability registration invalid')
            if source == 'ability/색채이론' and state.get('color_theory'):
                color = state['color_theory']
                expected = _color_payload(color['roll'])
                changed_payload = any(
                    color.get(key) != value
                    for key, value in expected.items()
                )
                changed_observation = (
                    color.get('observation')
                    != actor.spec.get('color_theory_birth')
                )
                if changed_payload or changed_observation:
                    raise ValueError('Color Theory observation changed')
            if source == 'ability/디자이너' and state.get('garment'):
                garment = state['garment']
                sid = garment.get('grant_source')
                live = [
                    modifier
                    for modifier in actor.modifiers
                    if isinstance(modifier, dict)
                    and modifier.get('_state_source') == sid
                ]
                live_types = {modifier['types'][0] for modifier in live}
                if len(live) != 2 or live_types != set(garment.get('types', [])):
                    raise ValueError('Designer garment lost its owned resistances')
        for food in actor.spec.get('food_consumption_receipts', []):
            claims = food.get('ability_native_claims', [])
            if claims and __import__('food_effects').retained_activation(food):
                raise ValueError('retained Harvest activation cannot carry consumption Ability claims')
            if not isinstance(claims, list) or len(claims) != len(set(claims)):
                raise ValueError('consumed Food Buff Ability claims invalid')
            if any(source != 'ability/도시락통-playtest' for source in claims):
                raise ValueError('unknown consumed Food Buff Ability claim')
        for plant in actor.spec.get('plants', {}).values():
            for application in plant.get('mulch_applications', []):
                grant = application.get('ability_application')
                if grant is None:
                    continue
                if (
                    grant.get('source') != 'ability/정원사'
                    or grant.get('provider_id') not in index
                ):
                    raise ValueError('Gardener application provider missing')
                provider = index[grant['provider_id']]
                matches = [
                    receipt
                    for receipt in provider.spec.get(HISTORY, [])
                    if receipt['source'] == 'ability/정원사'
                    and receipt['sequence'] == grant.get('activation_sequence')
                ]
                invalid_application = (
                    len(matches) != 1
                    or matches[0]['target_id'] != plant.get('id')
                    or matches[0]['details'].get('application_sequence')
                    != application.get('sequence')
                )
                if invalid_application:
                    raise ValueError('Gardener application lost its activation receipt')
    for actor in index.values():
        for record in actor.spec.get(TARGET_RECORDS, []):
            receipt = receipts.get(record.get('receipt_id'))
            sid = record.get('grant_source')
            invalid_receipt = (
                receipt is None
                or receipt['source'] != record.get('source')
                or receipt['actor_id'] != record.get('giver_id')
            )
            if invalid_receipt:
                raise ValueError('native target effect lost its producer receipt')
            live = any(
                isinstance(effect, dict) and effect.get('_state_source') == sid
                for effect in actor.registry
            )
            timed = any(
                effect.get('grant_source') == sid
                for effect in actor.custom_conditions.get('combat_timed_effects', [])
            )
            if live != timed:
                raise ValueError('native target effect and lifetime disagree')
    return True
