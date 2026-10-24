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
    raw = vars(actor)
    engine = raw.get(ENGINE_REF)
    if engine is None or raw.get(GUARD) or 'stages' not in raw:
        return
    if actor.r is not engine.r:
        raise ValueError('conditional stage actor and engine rule contexts differ')
    raw[GUARD] = True
    try:
        desired = 0
        if NAME in raw.get('abilities', []) and not raw.get('abilities_suppressed', False):
            selected = engine.r.selection.resolve_name(NAME, ('ability/',))
            if selected == RULE and __import__('effects').effective_weather(engine,actor) == 'sunny':
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
