"""C09-069: actual four-egg boxes and contained-time progress.

The egg owns membership intervals. Physical identity, location, access, elapsed
time, transactions, restoration and actual births retain their native owners.
"""
from copy import deepcopy
import common_checks as C
import resolution_transaction as TX
import source_selection as SOURCES
import state_grants as G
import world_entities as W

ITEM='item/부화기'
KEY='physical_incubator'
HISTORY='physical_incubation_intervals'
LOCATION='released_incubator_location'
SOURCE_REFERENCE={'file':'input/ch09-equipment.md','sha256':'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'}


def _source(engine):
    if SOURCES.select(engine.r,ITEM,source=SOURCE_REFERENCE)['selected_id']!=ITEM:
        raise ValueError('selected core physical Incubator source required')


def _box(engine,identity,*,usable=True):
    _source(engine)
    obj=getattr(engine,'_physical_objects',{}).get(identity)
    if type(obj) is not dict or obj.get('id')!=identity or obj.get('kind')!='item_instance' or obj.get('item_rule_id')!=ITEM:
        raise ValueError('actual core physical Incubator body required')
    if usable:W.require_usable_object(obj)
    return obj


def _configured(engine,identity,*,usable=True):
    obj=_box(engine,identity,usable=usable);state=obj.get(KEY)
    if type(state) is not dict or set(state)!= {'source','capacity','hatch_rate','price','observed_empty'} or state['source']!=ITEM or type(state['capacity']) is not int or state['capacity']!=4 or type(state['hatch_rate']) is not int or state['hatch_rate']!=2 or type(state['price']) is not int or state['price']!=2500:
        raise ValueError('actual sourced four-egg Incubator configuration required')
    fact=state['observed_empty']
    if type(fact) is not dict or set(fact)!={'actor_id','at','reason'} or fact['actor_id'] not in W.actor_index(engine):
        raise ValueError('actual empty Incubator observation required')
    C.integer(fact['at'],'empty Incubator observation time',0,engine.elapsed_seconds)
    W._text(fact['reason'],'actual empty Incubator observation reason')
    return obj


def _access(engine,actor,obj):
    W.require_actors(engine,actor)
    W.require_physical_access(obj)
    holder=obj.get('carrier_id') or obj.get('equipped_by')
    if holder is not None:
        if holder!=actor.entity_id:raise ValueError('actor must physically access the actual Incubator holder')
    else:
        distance=W.distance_known(actor,obj)
        if distance is None or distance>1:raise ValueError('actor must physically reach the actual Incubator')


def _active(egg):
    rows=egg.get(HISTORY,[])
    return rows[-1] if rows and rows[-1]['ended_at'] is None else None


def _signature(row):return TX.request_fingerprint({key:value for key,value in row.items() if key!='sha256'})


def validate_egg(engine,egg):
    if LOCATION in egg:
        import state_fields as F
        if F.location(egg[LOCATION])!=egg[LOCATION]:raise ValueError('actual released egg location required')
    if HISTORY not in egg:return
    rows=egg[HISTORY]
    if type(rows) is not list or not rows:raise ValueError('actual Incubator interval history required')
    previous=0 if egg.get('produced_at') is None else C.integer(egg['produced_at'],'actual incubated egg production time',0,engine.elapsed_seconds)
    actors=W.actor_index(engine)
    for n,row in enumerate(rows):
        if type(row) is not dict or set(row)!={'source','egg_id','box_id','started_at','started_by','reason','ended_at','ended_by','end_reason','sha256'} or row.get('source')!=ITEM or row.get('egg_id')!=egg['entity_id'] or row.get('sha256')!=_signature(row):
            raise ValueError('actual egg Incubator history identity/source changed')
        obj=_configured(engine,row['box_id'],usable=False)
        C.integer(row['started_at'],'actual Incubator insertion time',max(previous,obj[KEY]['observed_empty']['at']),engine.elapsed_seconds)
        if row['started_by'] not in actors:raise ValueError('actual egg insertion actor required')
        W._text(row['reason'],'actual egg insertion reason')
        if row['ended_at'] is None:
            if n!=len(rows)-1 or row['ended_by'] is not None or row['end_reason'] is not None or egg['hatched'] or LOCATION in egg:
                raise ValueError('one actual unhatched egg can occupy one current Incubator only')
            W.require_usable_object(obj)
        else:
            previous=C.integer(row['ended_at'],'actual Incubator removal time',row['started_at'],engine.elapsed_seconds)
            if row['ended_by'] not in actors:raise ValueError('actual egg removal actor required')
            W._text(row['end_reason'],'actual egg removal reason')


def validate_world(engine,eggs):
    counts={}
    for identity,obj in getattr(engine,'_physical_objects',{}).items():
        if KEY in obj:_configured(engine,identity,usable=False)
    for _,egg in eggs.values():
        validate_egg(engine,egg);row=_active(egg)
        if row:counts[row['box_id']]=counts.get(row['box_id'],0)+1
    if any(count>4 for count in counts.values()):raise ValueError('an actual Incubator holds at most four eggs')


def extra_seconds(engine,egg):
    validate_egg(engine,egg)
    return sum((engine.elapsed_seconds if row['ended_at'] is None else row['ended_at'])-row['started_at'] for row in egg.get(HISTORY,[]))


def location(engine,egg):
    validate_egg(engine,egg);row=_active(egg)
    if row:return W.effective_location(engine,_configured(engine,row['box_id']))
    if LOCATION in egg:return deepcopy(egg[LOCATION])
    owner=W.actor_index(engine).get(egg['owner_id'])
    if owner is None:raise ValueError('actual egg owner required')
    return W.location_of(owner)


def require_access(engine,actor,egg):
    validate_egg(engine,egg);row=_active(egg)
    if row:_access(engine,actor,_configured(engine,row['box_id']))
    elif LOCATION in egg:
        distance=W.distance_known(actor,{ 'location':egg[LOCATION] })
        if distance is None or distance>1:raise ValueError('actor must physically reach the actual released egg')


def _record(engine,actor,egg,reason):
    engine.gm._rec('actual Incubator egg '+egg['entity_id'],None,deepcopy(egg.get(HISTORY)),reason,actor)


def observe_empty(engine,actor,box_id,*,reason):
    W._text(reason,'actual empty Incubator observation reason')
    W.require_actors(engine,actor)
    def apply(e,a):
        obj=_box(e,box_id);_access(e,a,obj)
        if KEY in obj:raise ValueError('known Incubator history cannot be reset by an empty observation')
        obj[KEY]={'source':ITEM,'capacity':4,'hatch_rate':2,'price':2500,
                  'observed_empty':{'actor_id':a.entity_id,'at':e.elapsed_seconds,'reason':reason}}
        e.gm._rec('empty Incubator '+box_id,None,obj[KEY],reason,a)
        return deepcopy(obj[KEY])
    return G.transition(engine,actor,apply,include_rulings=True)


def _owned(engine,actor,egg_id):
    import pokemon_entities as P
    W.require_actors(engine,actor)
    entry=P.egg_index(engine).get(egg_id)
    if entry is None or entry[0] is not actor or entry[1]['hatched']:
        raise ValueError('actual owned unhatched egg required')
    return entry[1]


def store(engine,actor,box_id,egg_id,*,reason):
    W._text(reason,'actual Incubator insertion reason')
    W.require_actors(engine,actor)
    def apply(e,a):
        import pokemon_entities as P
        egg=_owned(e,a,egg_id);obj=_configured(e,box_id);_access(e,a,obj)
        if _active(egg):raise ValueError('actual egg already inside an Incubator')
        require_access(e,a,egg)
        eggs=P.egg_index(e);validate_world(e,eggs)
        if sum(1 for _,other in eggs.values() if _active(other) and _active(other)['box_id']==box_id)>=4:
            raise ValueError('actual Incubator holds at most four eggs')
        row={'source':ITEM,'egg_id':egg_id,'box_id':box_id,'started_at':e.elapsed_seconds,'started_by':a.entity_id,
             'reason':reason,'ended_at':None,'ended_by':None,'end_reason':None}
        row['sha256']=_signature(row);egg.setdefault(HISTORY,[]).append(row);egg.pop(LOCATION,None)
        _record(e,a,egg,reason)
        return deepcopy(row)
    return G.transition(engine,actor,apply,include_rulings=True)


def finish_egg(engine,egg,*,actor_id,reason,physical_location=None):
    """Native birth/body lifecycle hook; callers already own the transaction."""
    row=_active(egg)
    if row is None:return
    row.update(ended_at=engine.elapsed_seconds,ended_by=actor_id,end_reason=reason)
    row['sha256']=_signature(row)
    if physical_location is None:egg.pop(LOCATION,None)
    else:egg[LOCATION]=deepcopy(physical_location)


def remove(engine,actor,egg_id,*,reason):
    W._text(reason,'actual Incubator removal reason')
    W.require_actors(engine,actor)
    def apply(e,a):
        egg=_owned(e,a,egg_id)
        if _active(egg) is None:raise ValueError('actual egg is not inside an Incubator')
        require_access(e,a,egg)
        finish_egg(e,egg,actor_id=a.entity_id,reason=reason)
        _record(e,a,egg,reason)
        return deepcopy(egg[HISTORY][-1])
    return G.transition(engine,actor,apply,include_rulings=True)


def finish_body(engine,obj,*,actor_id,reason):
    if KEY not in obj:return
    import pokemon_entities as P
    place=W.effective_location(engine,obj)
    for _,egg in P.egg_index(engine).values():
        row=_active(egg)
        if row and row['box_id']==obj['id']:
            finish_egg(engine,egg,actor_id=actor_id,reason=reason,physical_location=place)


def observe_released_location(engine,actor,egg_id,physical_location,*,reason):
    """GM placement of the same released egg; unknown location stays unknown."""
    import state_fields as F
    W._text(reason,'actual released egg location observation reason')
    place=F.location(physical_location);W.require_actors(engine,actor)
    if place['kind']=='grid' and getattr(engine,'grid',None) is not None and not engine.grid.inside(place['cell']):
        raise ValueError('observed egg position is outside the current grid')
    def apply(e,a):
        egg=_owned(e,a,egg_id)
        if HISTORY not in egg or _active(egg):raise ValueError('actual released egg required; a contained egg follows its box')
        egg[LOCATION]=deepcopy(place)
        _record(e,a,egg,reason)
        return deepcopy(place)
    return G.transition(engine,actor,apply,include_rulings=True)


def describe(engine,box_id):
    import pokemon_entities as P
    obj=_configured(engine,box_id,usable=False);eggs=P.egg_index(engine);validate_world(engine,eggs)
    return {key:deepcopy(obj[KEY][key]) for key in ('source','capacity','hatch_rate','price')} | {
        'egg_ids':[egg['entity_id'] for _,egg in eggs.values() if _active(egg) and _active(egg)['box_id']==box_id]}


def projection(engine,egg):
    validate_egg(engine,egg);row=_active(egg)
    return {'physical_location':location(engine,egg),'protected_by':None if row is None else row['box_id']}
