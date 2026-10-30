"""Reviewed core weather ability state; ordinary effect execution is separate.

The public stages dictionary is the sole visible and consumed stage value.
Its raw backing remains an ordinary dict for snapshots and the graph codec.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

RULE = 'ability/엽록소'
NAME = '엽록소'
KEY = 'conditional:' + RULE
ENGINE_REF = '_conditional_stage_engine'
GUARD = '_conditional_stage_refreshing'


def definitions(rules):
    path = Path(rules.root) / 'data/abilities-core.json'
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('schema_version') != 1:
        raise ValueError('unsupported core ability definitions')
    result = {}
    expected = {'type':'conditional_combat_stage','weather':'sunny','stat':'spe','delta':4}
    for row in payload['abilities']:
        if row.get('id') == 'ability/흡반':
            __import__('core_suction_cups').validate_core_ability(rules, row)
            if row['id'] in result:raise ValueError('duplicate core Suction Cups identity')
            result[row['id']] = row
            continue
        if row.get('id') in __import__('telepath').CONTRACTS:
            __import__('telepath').validate_core_ability(rules,row)
            if row['id'] in result:raise ValueError('duplicate Telepathy Ability identity')
            result[row['id']]=row;continue
        if row.get('id')==__import__('telekinetic').INTERFERENCE:
            __import__('telekinetic').validate_core_ability(rules,row)
            if row['id'] in result:raise ValueError('duplicate core ability identity')
            result[row['id']]=row;continue
        if row.get('id')==__import__('sage').TOUCH:
            __import__('sage').validate_core_ability(rules,row)
            if row['id'] in result:raise ValueError('duplicate core ability identity')
            result[row['id']]=row;continue
        if row.get('id') in __import__('oracle').CORE_CONTRACTS:
            __import__('oracle').validate_core_ability(rules,row)
            if row['id'] in result:raise ValueError('duplicate core ability identity')
            result[row['id']]=row
            continue
        if row.get('id') == 'ability/파동바람':
            __import__('aura_guardian').validate_core_ability(rules,row)
            if row['id'] in result:raise ValueError('duplicate core ability identity')
            result[row['id']]=row
            continue
        if row.get('id') == 'ability/도주':
            __import__('tumbler').validate_core_ability(rules,row)
            if row['id'] in result:raise ValueError('duplicate core ability identity')
            result[row['id']]=row
            continue
        if row.get('id') == 'ability/먹보':
            __import__('capacity_abilities').validate_core_gluttony(rules,row)
            if row['id'] in result:raise ValueError('duplicate core ability identity')
            result[row['id']]=row
            continue
        if row.get('id') == 'ability/감지':
            __import__('chronicler').validate_core_perception(rules,row)
            if row['id'] in result:raise ValueError('duplicate core ability identity')
            result[row['id']]=row
            continue
        import martial_artist_ability_identities as MARTIAL
        if row.get('id') in MARTIAL.DERIVED:
            MARTIAL.validate_core_definition(rules,row)
            if row['id'] in result:raise ValueError('duplicate core ability identity')
            result[row['id']]=row;continue
        if row.get('id')=='ability/매복':
            __import__('rogue').validate_core_ability(rules,row)
            if row['id'] in result:raise ValueError('duplicate core ability identity')
            result[row['id']]=row
            continue
        if row.get('id') == 'ability/소리묻히기':
            __import__('musician').validate_core_ability(rules,row)
            if row['id'] in result:raise ValueError('duplicate core ability identity')
            result[row['id']]=row
            continue
        if row.get('id') != RULE or row.get('name') != NAME or row.get('native_contract') != expected:
            raise ValueError('unreviewed native core weather ability contract')
        source = row['source']
        if source['file'] != 'ch10-index-reference.md' or source['lines'] != [416,416]:
            raise ValueError('core Chlorophyll source boundary changed')
        line = (Path(rules.root)/'input'/source['file']).read_text(encoding='utf-8').splitlines()[415]
        if hashlib.sha256(line.encode()).hexdigest() != source['text_sha256'] or line != source['text']:
            raise ValueError('core Chlorophyll source text changed')
        if RULE in result:
            raise ValueError('duplicate core ability identity')
        result[RULE] = row
    return result


def bind(engine, actor, name):
    __import__('weather_passive_benefits').bind(engine,actor,name)
    if name != NAME:
        return
    # Resolve before binding, so failed registration does not invent a context.
    engine.r.selection.resolve_name(name, ('ability/',))
    current = vars(actor).get(ENGINE_REF)
    if current is not None and current is not engine:
        raise ValueError('conditional stage actor is already bound to another engine')
    vars(actor)[ENGINE_REF] = engine
    refresh(actor)


def refresh(actor):
    __import__('weather_passive_benefits').refresh(actor)
    raw = vars(actor)
    engine = raw.get(ENGINE_REF)
    if engine is None or raw.get(GUARD) or 'stages' not in raw:
        return
    if actor.r is not engine.r:
        raise ValueError('conditional stage actor and engine rule contexts differ')
    raw[GUARD] = True
    try:
        desired = 0
        import ability_transitions as ABILITIES
        if (not raw.get('abilities_suppressed', False)
                and any(ABILITIES.ability_id(engine.r,value)==RULE for value in raw.get('abilities', []))):
            selected = engine.r.selection.resolve_name(NAME, ('ability/',))
            if (selected == RULE and ABILITIES.active(actor,RULE)
                    and __import__('effects').effective_weather(engine,actor) == 'sunny' and not __import__('survivalist_class').weather_ability_suppressed(engine,actor,RULE)):
                engine.r.selection.require_supported_version(RULE)
                definition = engine.r.core_abilities[RULE]
                desired = definition['native_contract']['delta']
        import combat_stage_sources as CS
        old = actor.spec.get(CS.STATE)
        existing = old.get('base', {}).get(KEY) if old else None
        if desired == 0 and existing is None:
            return
        expected = {'source':RULE,'ends':'while sunny and ability active','deltas':{'spe':desired}}
        if existing == expected:
            CS.validate(actor)
            return
        state = CS.prepared(actor)
        if desired:
            state['base'][KEY] = expected
        else:
            state['base'].pop(KEY, None)
        # Keep existing references to the public stage dictionary coherent.
        visible = CS.render(actor, state)
        raw['stages'].clear(); raw['stages'].update(visible)
        state['snapshot'] = dict(visible)
        actor.spec[CS.STATE] = state
    finally:
        raw.pop(GUARD, None)

# CSV Sand Veil/Snow Cloak and Sun Veil retain their distinct printed branches.
VEILS={'ability/모래숨기-playtest':('sandstorm','sand'),
       'ability/눈숨기-playtest':('hail','snow')}
SUN_VEIL={'ability/햇살베일','ability/햇살베일-2'}


def ground_cover(engine,actor):
    if engine is None:return set()
    import environment_derive as ENV,environment_change as CHANGE
    row=ENV.region(engine,actor,required=False)
    return set(CHANGE.effective(engine,row).get('ground_cover',())) if row is not None else set()


def evasion_contributions(engine,actor):
    import ability_transitions as A
    if actor.abilities_suppressed:return {}
    owned=A.project_components(actor);out={}
    import effects as FX,survivalist_class as GUIDE
    cover=None
    for source,(weather,surface) in VEILS.items():
        if source not in owned:continue
        boosted=(engine is not None and FX.weather_matches(engine,weather,actor)
                 and not GUIDE.weather_ability_suppressed(engine,actor,source))
        if not boosted:
            if cover is None:cover=ground_cover(engine,actor)
            boosted=surface in cover
        out[source]=2 if boosted else 1
    for source in SUN_VEIL.intersection(owned):
        # Its unconditional +1 remains in the existing passive stat owner.
        if (engine is not None and not GUIDE.weather_ability_suppressed(engine,actor,source)
                and FX.weather_matches(engine,'sunny',actor)):
            if cover is None:cover=ground_cover(engine,actor)
            if 'grass' in cover:out[source]=1
    return out


def weather_hp_immunity(engine,actor,weather):
    """Sand Veil/Snow Cloak protect their user and actual adjacent allies."""
    import ability_transitions as A,body_state as BODY,world_entities as W
    import effects as FX,survivalist_class as GUIDE
    for owner in W.actor_index(engine).values():
        if (owner.kind not in ('trainer','pokemon') or owner.fainted or owner.captured
                or not getattr(owner,'on_field',True) or owner.abilities_suppressed):continue
        if owner is not actor and (owner.side is None or owner.side!=actor.side
                                  or not BODY.in_range(engine,owner,actor,1)):continue
        for source in A.project_components(owner):
            rule=VEILS.get(source)
            if (rule is not None and weather==rule[0] and FX.weather_matches(engine,weather,owner)
                    and not GUIDE.weather_ability_suppressed(engine,owner,source)):
                return source
    return None
WEATHER_VARIANTS={
 '엽록소 [Playtest]':('ability/엽록소-playtest',),
 '쓱쓱 [Playtest]':('ability/쓱쓱-playtest','ability/쓱쓱-playtest-2'),
 '모래헤치기 [Playtest]':('ability/모래헤치기-playtest',),
 '눈치우기':('ability/눈치우기','ability/눈치우기-2'),
 '모래숨기 [Playtest]':('ability/모래숨기-playtest',),
 '눈숨기 [Playtest]':('ability/눈숨기-playtest',),
 '햇살베일':('ability/햇살베일','ability/햇살베일-2'),
}


def registration(rules,value):
    """Select the actual CSV edition; only reviewed exact-copy IDs coalesce."""
    for name,ids in WEATHER_VARIANTS.items():
        if value not in (name,*ids):continue
        if value in ids and rules._selected_rule(value)!=value:raise ValueError('selected weather Ability copy changed')
        source=ids[0]
        if rules._selected_rule(source)!=source:raise ValueError('selected weather Ability edition changed')
        return {'name':name,'source_id':source,'equivalent_source_ids':list(ids)}
    return None