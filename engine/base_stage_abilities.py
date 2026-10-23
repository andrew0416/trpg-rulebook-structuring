"""Reviewed declarative ability baselines; share the ordinary CS source ledger.

Acquisition/identity comes from state_grants. Active presence, suppression,
fainting and physical held items derive contributions, never replay CS events.
"""
from pathlib import Path
from copy import deepcopy
import csv,hashlib,json
import common_checks as C
PREFIX='ability-base:'
GUARD='_ability_base_stage_refreshing'


def definitions(rules):
    root=Path(rules.root);path=root/'data/base-stage-abilities.json'
    if not path.exists():return {}
    policy=json.loads(path.read_text(encoding='utf-8'))
    if policy.get('schema_version')!=1 or policy.get('source_file')!='input/db/abilities.csv':raise ValueError('unsupported base-stage ability policy')
    source=root/policy['source_file']
    if hashlib.sha256(source.read_bytes()).hexdigest()!=policy['source_sha256']:raise ValueError('base-stage ability source changed')
    with source.open(encoding='utf-8-sig',newline='') as stream:original=list(csv.reader(stream))
    entities={r['id']:r for r in json.loads((root/'output/entities/abilities.json').read_text(encoding='utf-8'))}
    out={}
    for row in policy['definitions']:
        if row['name'] in out or row['id'] not in row['source_ids'] or row['frequency']!='항상':raise ValueError('unique always-active base-stage definition required')
        if len(row['source_ids'])!=len(row['source_rows']):raise ValueError('source identities must retain exact CSV records')
        for uid,ref in zip(row['source_ids'],row['source_rows']):
            if original[ref['record']-1]!=ref['cells']:raise ValueError('base-stage CSV row changed')
            entity=entities[uid]
            if entity['_source']['record_span']!=[ref['record'],ref['record']] or any(entity[k]!=row[k] for k in ('name','effect','frequency','keyword')):raise ValueError('base-stage equivalent source semantics changed')
        for field in ('base_deltas','held_deltas'):
            values=row[field]
            if not isinstance(values,dict) or not set(values)<=set(('atk','def','spa','spd','spe')):raise ValueError('non-HP base stages required')
            for n in values.values():C.integer(n,'ability base-stage delta',-6,6)
        if not row['base_deltas']:raise ValueError('base-stage definition must supply a baseline')
        out[row['name']]=row
    return out


def registration(rules,name):
    for row in getattr(rules,'base_stage_abilities',{}).values():
        if name not in row['aliases'] and name not in row['source_ids']:continue
        if row['name'] in getattr(rules,'excluded_abilities',{}):return None
        uid=name if name in row['source_ids'] else row['id']
        if rules._selected_rule(uid)!=uid:raise ValueError('selected base-stage ability variant requires its own source policy')
        return {'name':row['name'],'source_id':uid,'equivalent_source_ids':list(row['source_ids'])}
    return None


def _record(row,field):
    return {'source':row['id'],'ends':'while ability active'+(' and held item equipped' if field=='held_deltas' else ''),'deltas':dict(row[field])}


def refresh(actor):
    raw=vars(actor)
    if raw.get(GUARD) or 'stages' not in raw:return
    import combat_stage_sources as CS
    old=actor.spec.get(CS.STATE)
    owned={k:v for k,v in (old or {}).get('base',{}).items() if k.startswith(PREFIX)}
    receipts=actor.spec.get('state_grants',{}).get('ability_receipts',{})
    definitions=getattr(actor.r,'base_stage_abilities',{})
    if not owned and not any(name in receipts for name in definitions):return
    raw[GUARD]=True
    try:
        allowed={}
        for row in definitions.values():
            allowed[PREFIX+row['id']]=_record(row,'base_deltas')
            if row['held_deltas']:allowed[PREFIX+row['id']+':held']=_record(row,'held_deltas')
        if any(key not in allowed or value!=allowed[key] for key,value in owned.items()):raise ValueError('unreviewed or altered ability base-stage source record')
        desired={}
        if not raw.get('abilities_suppressed',False) and not actor.fainted:
            names=set()
            for ability in raw.get('abilities',[]):
                slot=registration(actor.r,ability)
                if slot and slot['name'] in receipts:names.add(slot['name'])
            import held_equipment as HELD
            holding=bool(HELD.entries(actor))
            for name in names:
                row=definitions[name];key=PREFIX+row['id'];desired[key]=allowed[key]
                if holding and row['held_deltas']:desired[key+':held']=allowed[key+':held']
        if owned==desired:return
        state=CS.prepared(actor)
        state['base']={k:v for k,v in state['base'].items() if not k.startswith(PREFIX)}
        state['base'].update(deepcopy(desired));CS.write(actor,state)
    finally:raw.pop(GUARD,None)
