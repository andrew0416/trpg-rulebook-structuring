"""Selected passive capacity sources; family consumers retain their own units."""
import json
from pathlib import Path


def install(rules):
    rules.ability_capacity_policy=json.loads((Path(rules.root)/'data/ability-capacity-policy.json').read_text(encoding='utf-8'))


def registration(rules,name):
    for uid,row in rules.ability_capacity_policy['abilities'].items():
        if name in (uid,row['name'],*row['aliases']):
            if rules._selected_rule(uid)!=uid:
                raise ValueError('selected capacity ability requires its own source policy')
            rules.selection.require_supported_version(uid)
            return {'name':row['name'],'source_id':uid}
    return None


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
    return next(iter(values.values()),None)
