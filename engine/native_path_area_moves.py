"""Fairy Lock source endings and Steel Roller's actual paid path effects."""
from copy import deepcopy
from pathlib import Path
import json

FAIRY='move/페어리록'
ROLLER='move/아이언롤러'
FAIRY_SOURCE='fairy_lock_source'
STEPS='steel_roller_entries'
_POLICY=json.loads((Path(__file__).resolve().parents[1]/'data/native-area-hit-effects.json').read_text(encoding='utf-8'))['moves']


def definition(rules,mid):
    row=_POLICY[mid]
    from source_context import verified_source
    verified_source(rules,row['source_reference'],label='native Fairy Lock/Steel Roller source')
    if rules._selected_rule(mid)!=mid or rules.move(mid)!=row['definition']:
        raise ValueError('actual selected Fairy Lock/Steel Roller definition required')
    return row


def mechanics(rules,mid,value):
    if mid not in (FAIRY,ROLLER):return value
    row=definition(rules,mid)
    if value!=row['raw_mechanics']:raise ValueError('native source-owned area Move extraction changed')
    return deepcopy(row['mechanics'])


def fairy_prepare(e,actor,target,effect,source):
    import world_entities as W
    W.require_actors(e,actor,target)
    row=definition(e.r,FAIRY)
    plain={key:value for key,value in effect.items() if not key.startswith('_')}
    if source!=FAIRY or plain not in row['mechanics']['effects_exec']:
        raise ValueError('exact Fairy Lock status and source-bound lifetime required')
    if not e.encounter_active or actor.fainted or actor.captured or not actor.on_field:
        raise ValueError('Fairy Lock requires its conscious present encounter user')
    return {'source':FAIRY,'effect_contract':True,'timing_text':deepcopy(plain),'manual_end':True,
            FAIRY_SOURCE:actor,'statuses':[plain['status']]}


def _validate_fairy(e,target,record,*,ending=False):
    import world_entities as W,effect_contracts as CONTRACTS
    source=record.get(FAIRY_SOURCE);index=W.actor_index(e)
    if source is None or index.get(getattr(source,'entity_id',None)) is not source:
        raise ValueError('Fairy Lock needs its actual source actor')
    effect=record.get('timing_text');row=definition(e.r,FAIRY)
    if (record.get('source')!=FAIRY or record.get('effect_contract') is not True or record.get('manual_end') is not True
            or effect not in row['mechanics']['effects_exec'] or record.get('statuses')!=[effect['status']]
            or set(record)!={'source','effect_contract','timing_text','manual_end',FAIRY_SOURCE,'statuses',
                              'effect_occurrence','effect_receipt','owned_statuses','installing'}):
        raise ValueError('Fairy Lock source/lifetime contribution changed')
    if (type(record.get('owned_statuses'))is not set or not record['owned_statuses']<=set(record['statuses'])
            or type(record.get('installing'))is not bool
            or record['installing'] and not getattr(e,'_native_action_stack',())):
        raise ValueError('Fairy Lock can own only its actual installed status contribution')
    CONTRACTS.validate_receipt(e,record['effect_receipt'],FAIRY,record['effect_occurrence'],source,target,effect)
    if not ending and (not e.encounter_active or not source.on_field or source.captured or source.fainted):
        raise ValueError('ended Fairy Lock source retained an active contribution')
    return True


def end_fairy_source(e,source):
    import world_entities as W,combat_timing as TIME
    planned=[(actor,row) for actor in W.actor_index(e).values() for row in TIME.records(actor)
             if row.get(FAIRY_SOURCE) is source]
    for actor,row in planned:_validate_fairy(e,actor,row,ending=True)
    for actor,row in planned:TIME.expire(e,actor,row)


def reconcile_fairy(e):
    import world_entities as W,combat_timing as TIME
    sources={id(row[FAIRY_SOURCE]):row[FAIRY_SOURCE] for actor in W.actor_index(e).values()
             for row in TIME.records(actor) if FAIRY_SOURCE in row}
    for source in sources.values():
        if not e.encounter_active or not source.on_field or source.captured or source.fainted:end_fairy_source(e,source)


def validate_world(e,index):
    import combat_timing as TIME
    for actor in index.values():
        for row in TIME.records(actor):
            if FAIRY_SOURCE in row:_validate_fairy(e,actor,row)


def roller_preflight(e,mid):
    if mid!=ROLLER:return
    definition(e.r,mid)
    import field_effects as FIELD,hazard_state as HAZARDS
    FIELD.validate(e);FIELD.validate_local(e);HAZARDS.validate_world(e)
    if e.grid is None or e.hazards_nogrid:raise ValueError('Steel Roller needs actual mapped hazard/terrain locations')
    if e.field is not None and FIELD._validate_state(e,e.field) is None:
        raise ValueError('Steel Roller needs the actual sourced Terrain or Room identity')


def roller_entry(e,actor,scope,position):
    if scope is None or scope.get('move_id')!=ROLLER:return
    import pass_moves as PASS,body_state as BODY,hazard_state as HAZARDS,field_effects as FIELD
    PASS.require_scope(e,actor,scope)
    row=scope.get('receipt')
    if (not scope.get('paid') or row is None or actor.pos!=tuple(position)
            or actor.pos!=tuple(scope['path'][scope['cell_index']])):
        raise ValueError('Steel Roller clearing requires its actual paid entered path cell')
    entries=row.setdefault(STEPS,[])
    # Only a committed first step authorizes clearing the starting footprint;
    # a refused departure must not erase hazards on an untraversed route.
    points=([tuple(row['origin'])] if not entries else [])+[tuple(position)]
    for point in points:
        if list(point) in [entry['position'] for entry in entries]:continue
        occupied=BODY.at_position(actor,point)
        adjacent=set().union(*(e.grid.burst(cell,1)|{cell} for cell in occupied))
        removed=HAZARDS.remove_cells(e,adjacent)
        terrain=FIELD.clear_terrain_at(e,occupied)
        entries.append({'position':list(point),'hazards_removed':removed,'terrain_ended':terrain})


def validate_roller(e,row):
    if row['move_id']!=ROLLER:
        if STEPS in row:raise ValueError('Steel Roller path history belongs only to its source')
        return
    entries=row.get(STEPS)
    path=[list(row['origin']),*[list(p) for p in row['path']]]
    if (type(entries)is not list or not entries or len(entries)>len(path)
            or [entry.get('position') for entry in entries]!=path[:len(entries)]
            or row.get('phase','complete')=='complete' and len(entries)!=len(path)):
        raise ValueError('Steel Roller clearing must follow its actual traversed prefix')
    for entry in entries:
        if (set(entry)!={'position','hazards_removed','terrain_ended'}
                or type(entry['hazards_removed'])is not int or entry['hazards_removed']<0
                or type(entry['terrain_ended'])is not list or any(type(uid)is not str for uid in entry['terrain_ended'])):
            raise ValueError('actual Steel Roller clearing receipt required')
