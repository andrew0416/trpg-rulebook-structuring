"""Selected passive capacity sources; family consumers retain their own units."""
import json
from pathlib import Path

CORE_GLUTTONY = 'ability/먹보'
CORE_SOURCE = {'file':'source-audit/core-gluttony.txt','sha256':'1076875c78d4a783be0ecd57f22e9b2d815dea0fa187c4c6bf4b1e19d4a71796'}
CORE_CONTRACT = {'type':'food_capacity','stored':None,'per_encounter':3,'drink_seconds':1800,'drinks':2,
                 'encounter_interpretation':'actual_digestion_buff_exchanges'}


def validate_core_gluttony(rules,row):
    """The bilingual lesson names Gluttony; the complete core excerpt supplies its effect."""
    from source_context import verified_source
    source = row.get('source', {}); official = row.get('official_source', {})
    if (row.get('id') != CORE_GLUTTONY or row.get('name') != '먹보' or row.get('eng') != 'Gluttony'
            or row.get('frequency') != '항상' or row.get('native_contract') != CORE_CONTRACT or row.get('effects') != []
            or source != {'file':'ch04-trainer-classes.md','lines':[1893,1897],
                'sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4',
                'additional_snapshots':{CORE_SOURCE['file']:CORE_SOURCE['sha256']}}
            or official.get('extract') != CORE_SOURCE['file'] or official.get('sha256') != CORE_SOURCE['sha256']):
        raise ValueError('complete source-bound core Gluttony contract required')
    verified_source(rules,{'file':'input/'+source['file'],'sha256':source['sha256']},label='Culinary Appreciation Gluttony reference')
    text = verified_source(rules,CORE_SOURCE,label='core Gluttony',source_root='source-audit').decode('utf-8')
    if text != 'Ability: Gluttony\nStatic Effect: The user may eat up to three Food Items per encounter, and up to two refreshments per half hour.\n':
        raise ValueError('complete core Gluttony excerpt required')


def install(rules):
    rules.ability_capacity_policy=json.loads((Path(rules.root)/'data/ability-capacity-policy.json').read_text(encoding='utf-8'))
    expected = {'name':'먹보','aliases':['Core Gluttony'],'kind':'food_capacity',
                **{key:value for key,value in CORE_CONTRACT.items() if key != 'type'}}
    if rules.ability_capacity_policy['abilities'].get(CORE_GLUTTONY) != expected:
        raise ValueError('core Gluttony capacity policy changed')


def registration(rules,name):
    rows=rules.ability_capacity_policy['abilities']
    candidates=[uid for uid,row in rows.items()
                if name in (uid,row['name'],*row['aliases'])
                or (name is not None and name==rules.selection.units.get(uid,{}).get('eng'))]
    if not candidates:return None
    if name in rows:uid=name
    else:
        from ruleset import ExcludedRuleSelection,UnresolvedRuleSelection
        selected=set()
        for candidate in candidates:
            try:selected.add(rules.selection.resolve(candidate))
            except ExcludedRuleSelection:continue
        if not selected:return None
        if len(selected)!=1:raise UnresolvedRuleSelection(name,sorted(selected))
        uid=selected.pop()
        if uid not in rows:return None
    if rules._selected_rule(uid)!=uid:
        raise ValueError('selected capacity ability requires its own source policy')
    rules.selection.require_supported_version(uid)
    return {'name':rows[uid]['name'],'source_id':uid}


def sources(rules,names,kind):
    result={}
    for name in names:
        registered=registration(rules,name)
        if registered:
            uid=registered['source_id'];row=rules.ability_capacity_policy['abilities'][uid]
            if row['kind']==kind:result[uid]=row
    return result


def food_capacity(engine,actor):
    if actor.abilities_suppressed:return None
    values=sources(engine.r,actor.abilities,'food_capacity')
    # Keep an unsupported older/different Gluttony interpretation explicit.
    if not values and any('먹보' in name or name=='Gluttony' for name in actor.abilities):
        raise ValueError('this Gluttony version needs its own food policy')
    if len(values)>1:raise ValueError('one actual Gluttony source definition required for food capacity')
    return next(iter(values.values()),None)
