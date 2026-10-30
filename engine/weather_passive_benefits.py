"""CSV passive weather components; acquisition and real weather stay owned elsewhere."""
from pathlib import Path
import csv
import common_checks as C

THERMO = 'ability/감온성'
DRY = 'ability/건조피부'
DESERT = 'ability/사막날씨-playtest'
PROTO = 'ability/고대활성'
PREFIX = 'weather-passive:'
GUARD = '_weather_passive_refreshing'
ENGINE_REF = '_conditional_stage_engine'
SOURCES = {
    THERMO: ('감온성', '항상', '쾌청한 날씨 아래에서 공격과 특공이 2단계 증가하지만, 싸라기눈 아래에서 이동능력이 절반으로 줄어듭니다.', ''),
    DRY: ('건조피부', '항상', '불타입 공격기에 맞거나 쾌청한 날씨 아래에서 턴을 끝낼때마다 소량의 체력을 잃습니다. 물타입 기술의 피해와 효과에 무효화이며, 물타입 공격기에 적중당하거나 비바라기 아래에서 턴을 끝낼때마다 소량의 체력을 회복합니다.', ''),
    DESERT: ('사막날씨 [Playtest]', '항상', '사용자는 모래바람 피해에 면역이 되고, 쾌청 날씨에서 불꽃타입 기술에 반감되며, 비바라기 날씨 상태일 때 각 턴이 끌날 때 소량의 임시 체력을 얻습니다.', '2-16 Playtest'),
    PROTO: ('고대활성', '항상', '쾌청 날씨 상태 또는 최대 체력 50% 미만에서는 체력을 제외한 가장 높은 스탯에서 전투 단계 +1을 받습니다.', ''),
}


def definition(rules, source):
    """Bind selected identity to the complete authored CSV row, not extraction output."""
    if source not in SOURCES:
        raise ValueError('reviewed passive weather source required')
    if rules._selected_rule(source) != source:
        raise ValueError('selected passive weather edition needs its own contract')
    checked = getattr(rules, '_weather_passive_checked', set())
    if source in checked:
        return SOURCES[source]
    name, frequency, effect, keyword = SOURCES[source]
    unit = rules.selection.units[source]
    provenance = unit['source']
    span = provenance.get('record_span')
    if (unit['title'] != name or provenance.get('file') != 'db/abilities.csv'
            or not isinstance(span, list) or len(span) != 2 or span[0] != span[1]):
        raise ValueError('passive weather identity must retain its actual CSV record')
    with (Path(rules.root) / 'input/db/abilities.csv').open(encoding='utf-8-sig', newline='') as handle:
        row = list(csv.reader(handle))[span[0] - 1]
    if len(row) != 8 or tuple(row[:3]) != (name, frequency, effect) or row[3:6] != ['', '', keyword]:
        raise ValueError('passive weather source text or action contract changed')
    rules._weather_passive_checked = checked | {source}
    return SOURCES[source]


def _identity(name):
    return next((source for source, row in SOURCES.items() if name in (source, row[0])), None)


def bind(engine, actor, name):
    source = _identity(name)
    if source is None:
        return
    definition(engine.r, source)
    previous = vars(actor).get(ENGINE_REF)
    if previous is not None and previous is not engine:
        raise ValueError('passive weather actor already bound to another engine')
    vars(actor)[ENGINE_REF] = engine


def owned(actor, source):
    import ability_transitions as ABILITIES
    if actor.fainted or actor.abilities_suppressed:
        return False
    if not any(_identity(name) == source for name in actor.abilities):
        return False
    definition(actor.r, source)
    return ABILITIES.active(actor, source)


def weather_benefit(engine, actor, source, weather):
    import effects as FX
    import survivalist_class as SC
    return (FX.weather_matches(engine, weather, actor)
            and not SC.weather_ability_suppressed(engine, actor, source))


def highest_stats(actor):
    import combat_stage_sources as CS
    values = {stat: C.integer(actor.stats[stat], 'Protosynthesis non-HP Stat', 0) for stat in CS.STATS}
    highest = max(values.values())
    return [stat for stat, value in values.items() if value == highest]


def choose_highest_stat(engine, actor, stat, *, reason):
    """Only resolve an actual tie; choosing cannot create ownership or weather."""
    import world_entities as WORLD
    WORLD.require_actors(engine, actor)
    definition(engine.r, PROTO)
    if not owned(actor, PROTO) or stat not in highest_stats(actor):
        raise ValueError('choose one actual highest non-HP Stat for owned Protosynthesis')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Protosynthesis tie decision reason required')
    actor.spec['protosynthesis_stat_choice'] = {'source': PROTO, 'stat': stat, 'reason': reason}
    refresh(actor)


def refresh(actor):
    raw = vars(actor)
    engine = raw.get(ENGINE_REF)
    if engine is None or raw.get(GUARD) or 'stages' not in raw:
        return
    import combat_stage_sources as CS
    old = actor.spec.get(CS.STATE)
    existing = {key: row for key, row in (old or {}).get('base', {}).items() if key.startswith(PREFIX)}
    if not existing and not any(_identity(name) in (THERMO, PROTO) for name in actor.abilities):
        return
    raw[GUARD] = True
    try:
        desired = {}
        if owned(actor, THERMO) and weather_benefit(engine, actor, THERMO, 'sunny'):
            desired[PREFIX + THERMO] = {'source': THERMO, 'ends': 'while active sunny weather benefit',
                                       'deltas': {'atk': 2, 'spa': 2}}
        if owned(actor, PROTO) and (actor.hp * 2 < actor.base_max_hp or weather_benefit(engine, actor, PROTO, 'sunny')):
            highest = highest_stats(actor)
            if len(highest) == 1:
                stat = highest[0]
            else:
                choice = actor.spec.get('protosynthesis_stat_choice', {})
                if choice.get('source') != PROTO or choice.get('stat') not in highest or not choice.get('reason'):
                    raise ValueError('Protosynthesis tied highest Stats require an explicit choice before benefit resolution')
                stat = choice['stat']
            desired[PREFIX + PROTO] = {'source': PROTO, 'ends': 'while active sun benefit or below half HP', 'deltas': {stat: 1}}
        if desired == existing:
            return
        state = CS.prepared(actor)
        state['base'] = {key: row for key, row in state['base'].items() if not key.startswith(PREFIX)}
        state['base'].update(desired)
        CS.write(actor, state)
    finally:
        raw.pop(GUARD, None)


def movement(engine, actor, values):
    """Hail is a penalty, so Wilderness Guide does not remove it."""
    import effects as FX
    if not owned(actor, THERMO) or not FX.weather_matches(engine, 'hail', actor):
        return values
    import arithmetic_policy as M
    from movement_actions import MODES
    return {mode: M.ratio(value, 2) if mode in MODES else value for mode, value in values.items()}


def end_turn(engine, actor):
    """Called only by the actual native owner-turn completion, once per serial."""
    relevant = [source for source in (DRY, DESERT) if owned(actor, source)]
    if not relevant:
        return
    if getattr(engine, '_active_turn_actor', None) is not actor:
        raise ValueError('weather end-turn Ability requires the actual open owner turn')
    serial = C.integer(actor.custom_conditions.get('combat_turn_serial'), 'weather end-turn serial', 1)
    stamp = [getattr(engine, '_party_encounter_epoch', 0), serial]
    if actor.spec.get('weather_passive_end_turn') == stamp:
        return
    actor.spec['weather_passive_end_turn'] = stamp
    import effects as FX
    if DRY in relevant:
        if FX.weather_matches(engine, 'sunny', actor):
            engine.lose_tick_hp(actor, source=DRY)
        if not actor.fainted and weather_benefit(engine, actor, DRY, 'rain'):
            engine.heal(actor, engine.tick(actor))
    if DESERT in relevant and not actor.fainted and weather_benefit(engine, actor, DESERT, 'rain'):
        import temporary_hp as TEMP
        TEMP.grant(engine, actor, engine.tick(actor), provenance={'source': DESERT, 'event': 'owner_turn_end', 'turn_serial': serial})


def _native_hit(engine, attacker, target, move, completion_id, defense_token=None):
    import attack_damage_history as HISTORY
    frame = HISTORY.native_recipient(engine, attacker, target,
        {'move_completion': completion_id, 'hit': True, 'source_id': move['id']})
    if frame is None or frame[2] is not move:
        raise ValueError('Dry Skin requires the active native hit producer')
    completion = getattr(engine, '_move_completions', {}).get(completion_id)
    if (not completion or completion['actor'] is not attacker or completion['move_id'] != move['id']
            or completion['phase'] != 'targets'):
        raise ValueError('Dry Skin needs the unresolved recipient of an actual paid Move')
    if defense_token is not None:
        # An actual Intercept retains the declared target in completion['targets'].
        # Its separate native recipient scope owns the interceptor, not a forged list edit.
        import move_defense_reactions as DEFENSE
        DEFENSE.require_recipient(engine, defense_token, attacker, target, move, completion_id)
        if target.entity_id in completion.get('received', {}):
            raise ValueError('Dry Skin recipient has already returned its actual hit')
    elif (target not in completion['targets'] or target.entity_id not in completion['started']
            or target.entity_id in completion['results']):
        raise ValueError('Dry Skin needs the unresolved recipient of an actual paid Move')
    return completion


def _dry_defense(engine, attacker, target, move):
    if not owned(target, DRY):
        return False
    import chronicler as CHRONICLER
    import trickster as TRICKSTER
    return (not CHRONICLER.defensive_ignored(engine, attacker, target, move)
            and not TRICKSTER.ignores_defensive(engine, target, DRY))


def _water_type(engine, attacker, target, move, mechanics, *, substitute):
    if substitute is not None or not _dry_defense(engine, attacker, target, move):
        return None
    import effects_ext as EXT
    actual_type = EXT.effective_type(engine, attacker, target, move, mechanics, consume=False)
    if actual_type not in ('물', 'Water'):
        return None
    import optional_physical_equipment as EQUIPMENT
    if EQUIPMENT.bypass_ability_immunity(move, actual_type):
        return None
    return actual_type


def absorbs_water(engine, attacker, target, move, mechanics, *, substitute):
    """Pure gate before target-only hit hooks; payment/healing remains native."""
    return _water_type(engine, attacker, target, move, mechanics, substitute=substitute) is not None


def water_hit(engine, attacker, target, move, mechanics, completion_id, *, substitute, natural, critical,
              defense_token=None):
    """Native post-accuracy entry; never called from damage calculations/previews."""
    actual_type = _water_type(engine, attacker, target, move, mechanics, substitute=substitute)
    if actual_type is None:
        return None
    import effects_ext as EXT
    completion = _native_hit(engine, attacker, target, move, completion_id, defense_token)
    rows = completion.setdefault('dry_skin_hits', {})
    if target.entity_id in rows:
        raise ValueError('Dry Skin recipient has already resolved its actual hit')
    # Consume an actual one-shot type conversion only on this resolved hit.
    EXT.effective_type(engine, attacker, target, move, mechanics, consume=True)
    rows[target.entity_id] = {'source': DRY, 'type': actual_type, 'healed': 0}
    if move['class'] in ('물리', '특수'):
        rows[target.entity_id]['healed'] = engine.heal(target, engine.tick(target))
    import effects as FX
    import attack_damage_history as HISTORY
    ctx = {'engine': engine, 'attacker': attacker, 'target': target, 'move': move,
           'hit': True, 'dealt': 0, 'nat': natural, 'crit': critical,
           'actual_damage_type': actual_type, 'move_completion': completion_id}
    before = set(getattr(engine, '_effect_dispatch_receipts', {}))
    # Target immunity does not waive independently paid attacker consequences.
    protected = __import__('substitute').mechanics(move, mechanics)
    self_effects = protected.get('effects_exec', [])
    with HISTORY.native_effects(engine, attacker, target, move, completion_id):
        done, held = FX.run_effects(engine, attacker, target, self_effects, ctx, move['id'])
    for effect in mechanics.get('stage_changes_exec', []):
        if effect.get('target') == 'self':
            stats = ('atk', 'def', 'spa', 'spd', 'spe') if effect['stat'] == 'all' else (effect['stat'],)
            FX.apply_stage_changes(engine, attacker, attacker, {stat: effect['delta'] for stat in stats}, source_id=move['id'])
    engine.effect_stats['done'] += done
    engine.effect_stats['held'] += held
    own_effects = [key for key in getattr(engine, '_effect_dispatch_receipts', {}) if key not in before]
    # These are effects on the user, not effects received by an immune target.
    # The existing completion owner preserves provenance and blocks completion
    # while any retained self-effect suffix is unresolved.
    completion['effects'].extend(key for key in own_effects if key not in completion['effects'])
    rows[target.entity_id]['attacker_effects'] = own_effects
    rows[target.entity_id]['attacker_held'] = held
    return {'hit': True, 'dealt': 0, 'held': 0, 'hit_prevented': True, 'effects': []}


def fire_hit(engine, attacker, target, move, completion_id, actual_type, *, defense_token=None):
    if (move['class'] not in ('물리', '특수') or actual_type not in ('불꽃', 'Fire')
            or not _dry_defense(engine, attacker, target, move)):
        return
    completion = _native_hit(engine, attacker, target, move, completion_id, defense_token)
    rows = completion.setdefault('dry_skin_hits', {})
    if target.entity_id in rows:
        return
    rows[target.entity_id] = {'source': DRY, 'type': actual_type, 'hp_before': target.hp}
    engine.lose_tick_hp(target, source=DRY)
    rows[target.entity_id]['hp_after'] = target.hp


def dry_skin_immunity(engine, attacker, target, move, actual_type):
    """Pure preview contribution; actual healing belongs to the paid hit above."""
    if actual_type in ('물', 'Water') and _dry_defense(engine, attacker, target, move):
        return {'type': 'immunity', 'to': actual_type, '_ability': '건조피부', '_rule_id': DRY}
    return None
