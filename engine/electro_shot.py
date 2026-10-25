"""CSV Electro Shot: one actual line, one round, and an ally's free exit distance."""
from copy import deepcopy
from pathlib import Path
import csv
import io
import json

SOURCE='move/일렉트로빔'
KEY='electro_shot_zone'
from contextvars import ContextVar
_TRANSACTION=ContextVar('electro_shot_native',default=False)



def native_move(fn):
    """Commit the whole source activation and its map identity together."""
    from functools import wraps
    @wraps(fn)
    def run(engine,actor,target,move_id,*args,**kwargs):
        if move_id not in (SOURCE,'일렉트로빔') or _TRANSACTION.get():return fn(engine,actor,target,move_id,*args,**kwargs)
        import state_grants as G
        pending=[]
        def apply(e,a):
            staged_args,staged_kwargs=G._stage_transition_payload(engine,e,((target,move_id,*args),kwargs))
            before=set(getattr(e,'_effect_dispatch_receipts',{}));token=_TRANSACTION.set(True)
            try:
                result=fn(e,a,*staged_args,**staged_kwargs)
                for key,row in e._effect_dispatch_receipts.items():
                    if key not in before and row['source_id']==SOURCE and row['status']=='execution_failed':
                        error=row.get('result')
                        if isinstance(error,Exception):raise error
                        raise ValueError('Electro Shot native field failed')
                return result
            except Exception as error:
                if G.record_native_pending(e,error,pending):return None
                raise
            finally:_TRANSACTION.reset(token)
        result=G.transition(engine,actor,apply,include_rulings=True,include_grid=engine.grid is not None)
        if pending:
            exception,event_id=pending[0];raise exception(event_id)
        return result
    return run


def policy(rules):
    from source_context import verified_source
    row=json.loads((Path(__file__).resolve().parents[1]/'data/electro-shot-policy.json').read_text(encoding='utf-8'))
    content=verified_source(rules,row['source_reference'],label='Electro Shot')
    cells=list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))[119]
    if (row['source_reference'].get('record')!=120 or cells[0]!='일렉트로빔'
            or cells[7]!=row['definition']['effect'] or rules._selected_rule(SOURCE)!=SOURCE
            or rules.move(SOURCE)!=row['definition']):
        raise ValueError('exact selected Electro Shot CSV source required')
    if row['effect']!={'type':'zone_rule','allies_adjacent_free_shift':True,'duration':'1라운드'}:
        raise ValueError('Electro Shot source-owned zone declaration changed')
    if row['action_effect']!={'type':'action_type_change','to':'standard','if_weather':'rain'}:
        raise ValueError('Electro Shot rain action contract changed')
    return row


def mechanics(rules,mid,declaration):
    if mid!=SOURCE:return declaration
    row=policy(rules)
    if declaration!={'effects_exec':[row['effect'],row['action_effect']]}:
        raise ValueError('Electro Shot extraction changed; source review required')
    return dict(declaration,effects_exec=[dict(row['effect'],_activation_scope='field'),row['action_effect']])


def field_effects(declaration):
    effects=declaration.get('effects_exec',[])
    expected={'type':'zone_rule','allies_adjacent_free_shift':True,'duration':'1라운드','_activation_scope':'field'}
    return [effects[0]] if effects==[expected,{'type':'action_type_change','to':'standard','if_weather':'rain'}] else []



def line_cells(rules,geometry):
    """Rebuild the printed line on its captured actual map, never from saved cells."""
    import common_checks as C
    from grid import Grid
    from area_targets import point
    from custom_species import parse_range
    if type(geometry)is not dict or set(geometry)!={'size','blocking','walls','origin','aim'}:
        raise ValueError('exact original Electro Shot map geometry required')
    if type(geometry['size'])is not tuple or len(geometry['size'])!=2:
        raise ValueError('actual original map dimensions required')
    width,height=(C.integer(v,'original map dimension',1) for v in geometry['size'])
    if type(geometry['blocking'])is not set or type(geometry['walls'])is not set:
        raise ValueError('actual original map obstacles required')
    grid=Grid(width,height,blocking=geometry['blocking'],walls=geometry['walls'])
    origin,aim=(point(geometry[k]) for k in ('origin','aim'))
    if not grid.inside(origin) or not grid.inside(aim) or origin==aim:
        raise ValueError('original Electro Shot origin and directional aim required')
    source=parse_range(policy(rules)['definition']['range'])
    if source.get('shape')!='line' or source.get('size')!=4:
        raise ValueError('selected Electro Shot requires its printed four-metre line')
    direction=((aim[0]>origin[0])-(aim[0]<origin[0]),(aim[1]>origin[1])-(aim[1]<origin[1]))
    cells=grid.line(origin,direction,source['size'])
    if not cells:raise ValueError('Electro Shot line has no actual cells')
    return cells


def capture_geometry(e,actor,move):
    geometry={'size':(e.grid.w,e.grid.h),'blocking':set(e.grid.blocking),'walls':set(e.grid.walls),
              'origin':actor.pos,'aim':tuple(move['_area_aim'])}
    if set(move['_effect_area_cells'])!=line_cells(e.r,geometry):
        raise ValueError('Electro Shot area differs from its selected source geometry')
    return dict(move,_electro_origin=actor.pos,_electro_geometry=geometry)


def prepare(e,actor,target,effect,source):
    import world_entities as W,combat_timing as TIME,body_state as BODY
    W.require_actors(e,actor,target)
    row=policy(e.r)
    if (source!=SOURCE or effect!=dict(row['effect'],_activation_scope='field')):
        raise ValueError('only the native Electro Shot field effect owns this lifetime')
    if e.grid is None or not e.encounter_active:
        raise ValueError('Electro Shot needs its actual mapped encounter')
    BODY.cells(actor,require_complete=True)
    return {'source':SOURCE,'effect_contract':True,'timing_text':'1라운드',
            'count_deadline':(e.round_no+1,TIME.current(e)),'encounter_end':True,'electro_shot_owned':True}


def install(e,actor,target,effect,source,receipt,occurrence):
    import combat_timing as TIME,effect_contracts as CONTRACTS
    record=prepare(e,actor,target,effect,source);record.pop('electro_shot_owned')
    rows=[r for r in getattr(e,'_move_completions',{}).values()
          if r['actor'] is actor and r['move_id']==SOURCE and r['phase']=='applying'
          and r['sealed'] and effect in r['post_effects']]
    if len(rows)!=1:raise ValueError('Electro Shot needs its actual once-per-activation field producer')
    row=rows[0];move=row['move']
    if any(r.get(KEY,{}).get('completion')==row['id'] for r in TIME.records(actor)):
        raise ValueError('Electro Shot field already installed for this activation')
    cells=move.get('_effect_area_cells')
    if not cells or not move.get('_electro_origin') or not move.get('_area_aim'):
        raise ValueError('Electro Shot needs the captured original line geometry')
    if set(cells)!=line_cells(e.r,move.get('_electro_geometry')):
        raise ValueError('Electro Shot producer line changed')
    CONTRACTS.validate_receipt(e,receipt,SOURCE,occurrence,actor,target,effect)
    if not hasattr(e.grid,'_tunnel_map_id'):
        from uuid import uuid4
        e.grid._tunnel_map_id=str(uuid4())
    zone={'completion':row['id'],'map_id':e.grid._tunnel_map_id,'map_size':(e.grid.w,e.grid.h),'cells':set(cells),
          'origin':tuple(move['_electro_origin']),'aim':tuple(move['_area_aim']),
          'birth_round':e.round_no,'birth_count':TIME.current(e),'target':target,'effect':deepcopy(effect)}
    record.update(effect_receipt=receipt,effect_occurrence=occurrence)
    record[KEY]=zone
    # Retain the producer link; geometry is independently rebuilt below.
    row[KEY]={'map_id':zone['map_id'],'map_size':zone['map_size'],'cells':set(cells),'origin':zone['origin'],'aim':zone['aim'],
              'birth_round':zone['birth_round'],'birth_count':zone['birth_count'],'receipt':receipt,'occurrence':occurrence}
    TIME.install(e,actor,record)
    return record


def validate_record(e,actor,record):
    import world_entities as W,effect_contracts as CONTRACTS,combat_timing as TIME
    policy(e.r);index=W.actor_index(e)
    zone=record.get(KEY);allowed={'source','effect_contract','timing_text','count_deadline','encounter_end',
                                 'effect_receipt','effect_occurrence',KEY,'owned_statuses','installing'}
    if (set(record)!=allowed or record['source']!=SOURCE or record['effect_contract'] is not True
            or record['encounter_end'] is not True or record['timing_text']!='1라운드'
            or record['owned_statuses']!=set() or record['installing'] is not False
            or type(zone)is not dict or set(zone)!={'completion','map_id','map_size','cells','origin','aim','birth_round','birth_count','target','effect'}):
        raise ValueError('Electro Shot timer/source contribution changed')
    row=getattr(e,'_move_completions',{}).get(zone['completion'])
    if (index.get(actor.entity_id)is not actor or index.get(getattr(zone['target'],'entity_id',None))is not zone['target']
            or row is None or row['actor'] is not actor or row['move_id']!=SOURCE
            or row['phase'] not in ('applying','completion_effects','complete') or not row['sealed']
            or zone['effect'] not in row['post_effects']
            or zone['cells']!=set(row['move'].get('_effect_area_cells',()))
            or zone['origin']!=tuple(row['move'].get('_electro_origin',()))
            or zone['aim']!=tuple(row['move'].get('_area_aim',()))
            or record['count_deadline']!=(zone['birth_round']+1,zone['birth_count'])
            or zone['birth_round']!=row['round'] or zone['birth_round']>e.round_no):
        raise ValueError('Electro Shot zone differs from its actual activation')
    expected={k:zone[k] for k in ('map_id','map_size','cells','origin','aim','birth_round','birth_count')}
    expected.update(receipt=record['effect_receipt'],occurrence=record['effect_occurrence'])
    if row.get(KEY)!=expected:raise ValueError('Electro Shot producer binding changed')
    geometry=row['move'].get('_electro_geometry')
    if (zone['cells']!=line_cells(e.r,geometry) or geometry['origin']!=zone['origin']
            or geometry['aim']!=zone['aim'] or geometry['size']!=zone['map_size']):
        raise ValueError('Electro Shot area differs from the original source line')
    import common_checks as C
    C.integer(zone['birth_round'],'actual zone creation round',1);C.integer(zone['birth_count'],'actual zone creation count')
    if type(zone['map_id'])is not str or not zone['map_id'] or type(zone['map_size'])is not tuple or len(zone['map_size'])!=2:
        raise ValueError('Electro Shot requires its actual captured map identity')
    width,height=(C.integer(v,'captured map dimension',1) for v in zone['map_size'])
    if type(zone['cells'])is not set or not zone['cells'] or any(not(0<=x<width and 0<=y<height) for x,y in zone['cells']):
        raise ValueError('Electro Shot requires captured in-bounds occupied cells')
    CONTRACTS.validate_receipt(e,record['effect_receipt'],SOURCE,record['effect_occurrence'],actor,zone['target'],zone['effect'])
    if not e.encounter_active:raise ValueError('Electro Shot timer survived its encounter')
    deadline=record['count_deadline'];cursor=getattr(e,'_initiative_cursor',None)
    if e.round_no>deadline[0] or (e.round_no==deadline[0] and cursor and cursor['round']==e.round_no and cursor['count']<=deadline[1]):
        raise ValueError('expired Electro Shot zone retained')
    return zone


def _points(path):
    return [tuple(n['position']) if type(n)is dict else tuple(n[:2]) for n in path]


def _footprint(position,offsets):
    import common_checks as C
    if type(offsets)is not tuple or not offsets or (0,0) not in offsets or len(set(offsets))!=len(offsets):
        raise ValueError('actual captured movement body required')
    return {(position[0]+C.integer(dx,'body offset'),position[1]+C.integer(dy,'body offset')) for dx,dy in offsets}


def trigger_end(e,path,trigger):
    """Derive the exact first exit from the original source and recorded native trigger."""
    import common_checks as C
    from grid import cheb
    points=_points(path)
    expected={'completion','index','position','source_position','body','source_body'}
    if type(trigger)is not dict or set(trigger)!=expected:raise ValueError('exact Electro Shot departure trigger required')
    start=C.integer(trigger['index'],'actual trigger prefix',0,len(points)-1)
    from area_targets import point
    position=point(trigger['position']);source_position=point(trigger['source_position'])
    if start and position!=points[start-1]:raise ValueError('Electro Shot trigger left its actual path prefix')
    row=getattr(e,'_move_completions',{}).get(trigger['completion'])
    if row is None or row['move_id']!=SOURCE or KEY not in row:raise ValueError('actual Electro Shot trigger producer required')
    cells=line_cells(e.r,row['move'].get('_electro_geometry'))
    body=_footprint(position,trigger['body']);source_body=_footprint(source_position,trigger['source_body'])
    if not body&cells or body&source_body or not any(cheb(a,b)==1 for a in body for b in source_body):
        raise ValueError('Electro Shot trigger must be an actual adjacent body inside its line')
    last=next((j for j in range(start,len(points)) if not _footprint(points[j],trigger['body'])&cells),None)
    if last is None:raise ValueError('Electro Shot movement must actually leave its source line')
    segment=[position,*points[start:last+1]]
    if len(segment)!=len(set(segment)):raise ValueError('looping path is not an Electro Shot exit')
    return last+1


STEP_TYPE='_electro_shot_movement'
_OWNER_UNSET=object()


def step_receipt(e,token,*,actor=None,path=None,progress=_OWNER_UNSET):
    """Read native-issued step evidence, never a caller's claimed discount."""
    import world_entities as W,effect_contracts as CONTRACTS,common_checks as C
    from math import isfinite
    from grid import cheb
    row=getattr(e,'_effect_dispatch_receipts',{}).get(token)
    if row is None or row['status']!='completed' or row.get('result')!='committed_electro_shot_step':
        raise ValueError('actual completed Electro Shot movement receipt required')
    owner=row.get('native_movement_progress',_OWNER_UNSET)
    if owner is _OWNER_UNSET or owner is not None and type(owner)is not dict:
        raise ValueError('native movement receipt lost its actual paid-path owner')
    if progress is not _OWNER_UNSET and owner is not progress:
        raise ValueError('exit receipt belongs to another native paid movement owner')
    fact=row['effect'];keys={'type','completion','parent_occurrence','trigger','trigger_occurrence','path','index',
                            'origin','position','distance','altitude_before','altitude_after','diagonals_before','diagonals_after'}
    if type(fact)is not dict or set(fact)!=keys or fact['type']!=STEP_TYPE:
        raise ValueError('exact native Electro Shot step facts required')
    completion=getattr(e,'_move_completions',{}).get(fact['completion'])
    index=W.actor_index(e)
    if (completion is None or completion['move_id']!=SOURCE or completion['actor'] is not row['actor']
            or KEY not in completion or fact['parent_occurrence']!=completion[KEY]['occurrence']
            or index.get(row['actor'].entity_id)is not row['actor'] or index.get(row['target'].entity_id)is not row['target']
            or actor is not None and row['target'] is not actor or path is not None and fact['path']!=path):
        raise ValueError('native exit receipt belongs to another source, actor or paid path')
    CONTRACTS.validate_receipt(e,token,SOURCE,row['occurrence'],row['actor'],row['target'],fact)
    points=_points(fact['path']);step=C.integer(fact['index'],'actual committed free step',0,len(points)-1)
    trigger=fact['trigger'];end=trigger_end(e,fact['path'],trigger)
    if (trigger['completion']!=fact['completion'] or not trigger['index']<=step<end
            or tuple(fact['position'])!=points[step]
            or tuple(fact['origin'])!=(points[step-1] if step else tuple(trigger['position']))):
        raise ValueError('native free step exceeds its actual trigger and first exit')
    for key in ('distance','altitude_before','altitude_after'):
        value=fact[key]
        if type(value)not in (int,float) or not isfinite(value) or value<0 or key=='distance' and value==0:
            raise ValueError('actual finite native movement measurement required')
    if fact['distance']<max(cheb(fact['origin'],fact['position']),abs(fact['altitude_after']-fact['altitude_before'])):
        raise ValueError('native movement measurement is shorter than actual displacement')
    before=C.integer(fact['diagonals_before'],'actual prior diagonal count',0)
    after=C.integer(fact['diagonals_after'],'actual committed diagonal count',0)
    if after-before!=min(abs(fact['origin'][0]-fact['position'][0]),abs(fact['origin'][1]-fact['position'][1])):
        raise ValueError('native movement diagonal history changed')
    first=fact['trigger_occurrence']
    if first is None:
        if step!=trigger['index'] or tuple(fact['origin'])!=tuple(trigger['position']):
            raise ValueError('native trigger receipt must begin at its observed departure')
    else:
        matches=[(k,r) for k,r in e._effect_dispatch_receipts.items() if r['occurrence']==first]
        if len(matches)!=1:raise ValueError('native exit lost its initial departure receipt')
        first_token,first_row=matches[0];initial=first_row['effect']
        if (initial.get('type')!=STEP_TYPE or initial.get('trigger_occurrence') is not None
                or first_row['actor'] is not row['actor'] or first_row['target'] is not row['target']
                or initial.get('path')!=fact['path'] or initial.get('trigger')!=trigger):
            raise ValueError('native exit cannot replace its actual initial trigger')
        step_receipt(e,first_token,actor=actor,path=path,progress=progress)
    return row


def validate_progress(e,actor,progress):
    """Bind retained native progress to its source-issued step receipts."""
    import common_checks as C
    from math import isfinite,isclose
    if not any(k in progress for k in ('electro_shot_motion','electro_shot_exits','charged_distance')):return
    motion=progress.get('electro_shot_motion')
    if type(motion)is not dict or set(motion)!={'actor_id','receipts'} or motion['actor_id']!=actor.entity_id or type(motion['receipts'])is not list:
        raise ValueError('Electro Shot movement lost its actual native receipts')
    path=progress['path'];points=_points(path);next_index=C.integer(progress['next'],'committed path prefix',0,len(points))
    discount=0;seen=set();tokens=set()
    for token in motion['receipts']:
        row=step_receipt(e,token,actor=actor,path=path,progress=progress);fact=row['effect'];step=fact['index']
        if token in tokens or step in seen or step>=next_index:raise ValueError('free-step receipts must match distinct committed path steps')
        tokens.add(token);seen.add(step);discount+=fact['distance']
    physical=progress['distance'];charged=progress.get('charged_distance',physical)
    if (type(physical)not in (int,float) or type(charged)not in (int,float)
            or not isfinite(physical) or not isfinite(charged) or charged<0
            or not isclose(physical,charged+discount,rel_tol=1e-12,abs_tol=1e-12)):
        raise ValueError('Electro Shot charged distance differs from actual native step receipts')
    active=progress.get('electro_shot_exits',{})
    if type(active)is not dict:raise ValueError('actual active exit mapping required')
    for completion,span in active.items():
        if type(span)is not dict or set(span)!={'next','end','receipt'} or span['receipt'] not in tokens:
            raise ValueError('actual native departure receipt required')
        fact=step_receipt(e,span['receipt'],actor=actor,path=path,progress=progress)['effect']
        end=trigger_end(e,path,fact['trigger'])
        if (fact['completion']!=completion or fact['trigger_occurrence'] is not None
                or span['next']!=next_index or span['end']!=end or not fact['index']<next_index<end):
            raise ValueError('Electro Shot exit differs from its exact first outside cell')
    if next_index and tuple(progress['position'])!=points[next_index-1]:raise ValueError('actual committed exit position required')


def validate_world(e,index):
    import combat_timing as TIME
    for actor in index.values():
        for record in TIME.records(actor):
            if KEY in record:validate_record(e,actor,record)
    for token,row in getattr(e,'_effect_dispatch_receipts',{}).items():
        if row.get('effect',{}).get('type')==STEP_TYPE:step_receipt(e,token)
    # Native continuations reside in actor state and existing pending producers.
    seen=set()
    def visit(value):
        if type(value)not in (dict,list,tuple,set) or id(value) in seen:return
        seen.add(id(value))
        if type(value)is dict:
            if any(k in value for k in ('electro_shot_motion','electro_shot_exits')):
                uid=value.get('electro_shot_motion',{}).get('actor_id');actor=index.get(uid)
                if actor is None:raise ValueError('exit continuation needs its actual actor')
                validate_progress(e,actor,value)
            for child in value.values():visit(child)
        else:
            for child in value:visit(child)
    for actor in index.values():visit(actor.spec);visit(actor.custom_conditions)
    for key in ('_move_completions','_passive_events','_breather_attempts'):visit(getattr(e,key,{}))
    for row in getattr(e,'_effect_dispatch_receipts',{}).values():
        if row.get('effect',{}).get('type')==STEP_TYPE:visit(row['native_movement_progress'])


def exit_step(e,actor,path,index,active,*,movement_mode=None,progress=None):
    """Prepare an actual eligible departure; no receipt exists until it commits."""
    import world_entities as W,combat_timing as TIME,body_state as BODY
    rows=[(owner,r) for owner in W.actor_index(e).values() for r in TIME.records(owner) if KEY in r]
    if not rows:return None
    W.require_actors(e,actor)
    if e.move_profile(actor,movement_mode=movement_mode)[0]<=0:return None
    chosen=None
    for owner,record in rows:
        zone=validate_record(e,owner,record)
        if (e.grid is None or zone['map_id']!=getattr(e.grid,'_tunnel_map_id',None)
                or zone['map_size']!=(e.grid.w,e.grid.h) or owner is actor
                or owner.location['kind']!='grid' or not owner.on_field or owner.captured):continue
        if owner.side is None or actor.side!=owner.side:continue
        key=zone['completion'];span=active.get(key);receipt=None
        if span is not None:
            receipt=span['receipt'];row=step_receipt(e,receipt,actor=actor,path=path,progress=progress);trigger=row['effect']['trigger']
            end=trigger_end(e,path,trigger)
            if span['next']!=index or span['end']!=end or not index<end:
                raise ValueError('Electro Shot exit differs from its exact first outside cell')
            if tuple(BODY.offsets(actor))!=trigger['body']:raise ValueError('exit body changed during its retained path')
        else:
            if not BODY.at_position(actor)&zone['cells'] or not BODY.adjacent(owner,actor):continue
            trigger={'completion':key,'index':index,'position':actor.pos,'source_position':owner.pos,
                     'body':tuple(BODY.offsets(actor)),'source_body':tuple(BODY.offsets(owner))}
            try:end=trigger_end(e,path,trigger)
            except ValueError:continue
        candidate={'trigger':deepcopy(trigger),'receipt':receipt,'end':end}
        # Overlapping permissions do not add movement; use their furthest exit.
        if chosen is None or end>chosen['end']:chosen=candidate
    return chosen


def restore_exits(e,actor,progress):
    validate_progress(e,actor,progress)
    return dict(progress.get('electro_shot_exits',{}))


def commit_step(e,progress,actor,candidate,index,distance,path,origin,altitude,height,before_diagonals,after_diagonals):
    """Issue evidence only after the shared native movement physically enters a cell."""
    import world_entities as W,body_state as BODY,effect_contracts as CONTRACTS
    if candidate is None:
        if progress is not None:progress.pop('electro_shot_exits',None)
        return {}
    trigger=candidate['trigger'];completion=e._move_completions[trigger['completion']];owner=completion['actor']
    W.require_actors(e,owner,actor)
    if actor.pos!=_points(path)[index] or actor.spec.get('_movement_altitude',0)!=height:
        raise ValueError('exit evidence requires the actually committed native step')
    first=candidate['receipt']
    if first is None:
        if (index!=trigger['index'] or tuple(origin)!=tuple(trigger['position']) or owner.pos!=trigger['source_position']
                or tuple(BODY.offsets(owner))!=trigger['source_body'] or tuple(BODY.offsets(actor))!=trigger['body']):
            raise ValueError('exit trigger differs from the actual native departure bodies')
        first_occurrence=None
    else:first_occurrence=step_receipt(e,first,actor=actor,path=path,progress=progress)['occurrence']
    fact={'type':STEP_TYPE,'completion':completion['id'],'parent_occurrence':completion[KEY]['occurrence'],
          'trigger':deepcopy(trigger),'trigger_occurrence':first_occurrence,'path':deepcopy(path),'index':index,
          'origin':tuple(origin),'position':actor.pos,'distance':distance,'altitude_before':altitude,'altitude_after':height,
          'diagonals_before':before_diagonals,'diagonals_after':after_diagonals}
    occurrence,token=CONTRACTS.issue_receipt(e,SOURCE,owner,actor,fact,index)
    e._effect_dispatch_receipts[token]['native_movement_progress']=progress
    CONTRACTS.finish(e,token,'completed','committed_electro_shot_step')
    if first is None:first=token
    active={completion['id']:{'next':index+1,'end':candidate['end'],'receipt':first}} if index+1<candidate['end'] else {}
    if progress is not None:
        motion=progress.setdefault('electro_shot_motion',{'actor_id':actor.entity_id,'receipts':[]})
        motion['receipts'].append(token)
        if active:progress['electro_shot_exits']=active
        else:progress.pop('electro_shot_exits',None)
    return active
