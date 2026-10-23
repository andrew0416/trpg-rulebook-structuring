"""Observed bodies and map tokens, including explicitly shaped large bodies.

An unknown body remains unknown. Its token is a known occupied cell, not evidence
that its whole physical body occupies exactly one cell. Movement/range legality
must use an exact projection when complete body geometry is required.
Source: ch07-combat.md:121-125.
"""
from copy import deepcopy
import state_fields as F
import world_entities as W

WIDTH={"소형":1,"중형":1,"대형":2,"거대":3,"거대형":3,"초거대":4,"초거대형":4,
       "Small":1,"Medium":1,"Large":2,"Huge":3,"Gigantic":4,
       "small":1,"medium":1,"large":2,"huge":3,"gigantic":4}


def validate(actor):
    validate_appendages(actor)
    validate_parts(actor)
    validate_reach_observation(actor)
    import body_modes as MODES
    mode=MODES.validate(actor)
    shape=mode["footprint"] if mode else actor.spec.get("footprint")
    if shape is None:return True
    if not isinstance(shape,dict) or shape.get("kind")!="observed_cells":
        raise ValueError("explicit observed-cell body shape required")
    W._text(shape.get("reason"),"observed footprint reason")
    cells=shape.get("offsets")
    if not isinstance(cells,(list,tuple)) or not cells:
        raise ValueError("body shape needs occupied cell offsets")
    seen=set()
    for cell in cells:
        if not isinstance(cell,(list,tuple)) or len(cell)!=2:
            raise ValueError("body offset is a coordinate pair")
        for value in cell:F.integer(value,"body offset")
        if tuple(cell) in seen:raise ValueError("body contains a repeated cell")
        seen.add(tuple(cell))
    if (0,0) not in seen:
        raise ValueError("the map anchor must be an occupied body cell")
    return True


def validate_appendages(actor):
    rows=actor.spec.get('observed_appendages',{})
    if type(rows) is not dict:raise ValueError('actual appendage identity mapping required')
    for uid,row in rows.items():
        W._text(uid,'observed actual appendage identity')
        if (type(row) is not dict or set(row)!={'actor_id','appendage_id','source','reason'}
                or row['actor_id']!=actor.entity_id or row['appendage_id']!=uid
                or row['source']!='gm/observation'):
            raise ValueError('actual body appendage observation required')
        W._text(row['reason'],'appendage observation reason')
    return True


def observe_appendage(engine,actor,appendage_id,*,reason):
    """Identity observation only; no anatomy, reach or attack grants are inferred."""
    import state_grants as G
    W.require_actors(engine,actor);W._text(appendage_id,'actual appendage identity')
    W._text(reason,'appendage observation reason')
    row=dict(actor_id=actor.entity_id,appendage_id=appendage_id,source='gm/observation',reason=reason)
    old=actor.spec.get('observed_appendages',{}).get(appendage_id)
    if old is not None:
        if old!=row:raise ValueError('actual appendage identity observation changed')
        return deepcopy(old)
    def apply(e,a):
        a.spec.setdefault('observed_appendages',{})[appendage_id]=deepcopy(row)
        validate_appendages(a)
        e.gm._rec('body appendage',None,row,reason,a)
        return deepcopy(row)
    return G.transition(engine,actor,apply)


PARTS='observed_body_parts'
PART_SOURCE={'file':'input/ch10-index-reference.md','sha256':'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}


def validate_parts(actor):
    """Observations identify actual anatomy; no species anatomy is inferred."""
    import resolution_transaction as TX
    rows=actor.spec.get(PARTS,{})
    if type(rows)is not dict:raise ValueError('actual body part observations required')
    for uid,row in rows.items():
        W._text(uid,'actual body part identity')
        if type(row)is not dict or set(row)!={'actor_id','part_id','offset','body','source','reason','sha256'}:
            raise ValueError('exact body part observation required')
        if row['actor_id']!=actor.entity_id or row['part_id']!=uid or row['source']!='gm/observation':
            raise ValueError('body part belongs to another actual actor')
        W._text(row['reason'],'body part observation reason')
        F.location({'kind':'grid','cell':row['offset']})
        if type(row['body'])is not dict or row['sha256']!=TX.json_fingerprint({k:v for k,v in row.items() if k!='sha256'}):
            raise ValueError('body part observation changed')
    return rows


def _part_body(actor):
    import body_modes as MODES
    mode=MODES.validate(actor)
    return {'offsets':[list(p) for p in offsets(actor)],
            'footprint':deepcopy(actor.spec.get('footprint')),
            'mode':None if mode is None else {k:deepcopy(mode.get(k)) for k in ('mode','footprint','appearance','form')}}


def _require_part_body(engine,actor):
    from source_context import verified_source
    verified_source(actor.r,PART_SOURCE,label='ranged single body origin')
    W.require_actors(engine,actor)
    if engine.grid is None:raise ValueError('body part origin requires an actual grid')
    occupied=cells(actor,require_complete=True)
    if len(occupied)<2:raise ValueError('body part origin requires a non-square multi-cell body')
    xs={p[0] for p in occupied};ys={p[1] for p in occupied}
    if len(xs)==len(ys) and len(occupied)==len(xs)*len(ys) and max(xs)-min(xs)+1==len(xs) and max(ys)-min(ys)+1==len(ys):
        raise ValueError('body part origin requires a non-square multi-cell body')
    if any(not engine.grid.inside(p) for p in occupied):raise ValueError('current body extends outside the map')
    return occupied


def observe_part(engine,actor,part_id,cell,*,reason):
    """Bind an observed actual part to its current body-relative occupied cell."""
    import state_grants as G,resolution_transaction as TX
    W._text(part_id,'actual body part identity');W._text(reason,'body part observation reason')
    cell=F.location({'kind':'grid','cell':cell})['cell']
    def apply(e,a):
        if cell not in _require_part_body(e,a):raise ValueError('body part cell must be inside the current actual body')
        anchor=W.grid_cell(a)
        row=dict(actor_id=a.entity_id,part_id=part_id,offset=[cell[0]-anchor[0],cell[1]-anchor[1]],
                 body=_part_body(a),source='gm/observation',reason=reason)
        row['sha256']=TX.json_fingerprint(row)
        old=deepcopy(a.spec.get(PARTS,{}).get(part_id))
        a.spec.setdefault(PARTS,{})[part_id]=row
        validate_parts(a);e.gm._rec('body part',old,row,reason,a)
        return deepcopy(row)
    return G.transition(engine,actor,apply)


def part_cell(engine,actor,part_id,*,position=None):
    W._text(part_id,'selected actual body part')
    occupied=_require_part_body(engine,actor)
    row=validate_parts(actor).get(part_id)
    if row is None:raise ValueError('selected body part has not been observed')
    if row['body']!=_part_body(actor):raise ValueError('selected body part needs a current body observation')
    anchor=W.grid_cell(actor);dx,dy=row['offset'];cell=(anchor[0]+dx,anchor[1]+dy)
    if cell not in occupied:raise ValueError('selected body part lies outside the current body')
    if position is not None:
        position=F.location({'kind':'grid','cell':position})['cell']
        cell=(position[0]+dx,position[1]+dy)
    return cell


def bind_origin(engine,actor,move,part_id):
    if part_id is None:return move
    import weapon_actions as WEAPONS
    rng=WEAPONS.range_spec(engine,move,actor)
    if rng.get('shape') or type(rng.get('origin')) not in (int,float) or rng.get('targets',1)!=1:
        raise ValueError('body part origin belongs only to ranged single-target moves')
    part_cell(engine,actor,part_id)
    return dict(move,_body_origin_part=part_id)


def attack_cells(engine,actor,move=None,*,position=None):
    part=(move or {}).get('_body_origin_part')
    return {part_cell(engine,actor,part,position=position)} if part is not None else at_position(actor,position)


def offsets(actor):
    validate(actor)
    import body_modes as MODES
    mode=MODES.validate(actor)
    shape=mode["footprint"] if mode else actor.spec.get("footprint")
    if shape is not None:
        return tuple(tuple(x) for x in shape["offsets"])
    width=WIDTH.get(actor.spec.get("size"))
    if width is None:return None
    return tuple((x,y) for x in range(width) for y in range(width))


def projection(actor):
    shape=offsets(actor);loc=W.location_of(actor)
    result={"entity_id":actor.entity_id,"size":actor.spec.get("size"),"location":loc,
            "offsets":shape,"geometry_complete":shape is not None and loc["kind"]=="grid",
            "weight_class":actor.weight_class,
            "weight_kg":weight_kg(actor),
            "weight_observation":deepcopy(actor.spec.get("trainer_weight_observation"))}
    import body_modes as MODES
    mode=MODES.validate(actor)
    result["body_mode"]=deepcopy(mode)
    result["size_ratio"]=mode["size_ratio"] if mode else 1
    result["height_m"]=(actor.spec.get("height_m")*result["size_ratio"] if actor.spec.get("height_m") is not None and result["size_ratio"] is not None else None)
    result["appearance"]=deepcopy(mode.get("appearance")) if mode else None
    result["appearance_limits"]=None
    if mode and mode["mode"]=="shapeshift" and mode["appearance"]["kind"] in ("complex_machine","pokemon"):
        result["appearance_limits"]={"source":mode["source"],"appearance_only":True,
                                     "simplified_machine":mode["appearance"]["kind"]=="complex_machine",
                                     "grants_copied_mechanics":False}
    result["mass_ratio"]=mode.get("mass_ratio") if mode else None
    result["volume_ratio"]=None
    if mode and mode["mode"]=="shapeshift":
        # Mass does not determine height, volume or isotropic scaling.
        result["height_m"]=mode["height_m"]
        result["size_ratio"]=None
    if mode and mode["mode"]=="amorphous":
        result["height_m"]=mode["height_m"]
    result['flat_surface_form']=bool(mode and mode['mode']=='shadow')
    if result['flat_surface_form']:result['height_m']=None
    if loc["kind"]!="grid":result["cells"]=None
    else:
        anchor=loc["cell"]
        result["cells"]={(anchor[0]+dx,anchor[1]+dy) for dx,dy in (shape or ((0,0),))}
    import baby_templates as BABY
    result["baby_template"]=BABY.body_projection(actor) if actor.kind=="pokemon" else None
    return result


def shapeshift_mass(actor,row):
    """The unchanged individual sheet is the original body, never the last form."""
    from math import isfinite
    base=actor.spec.get('weight_kg')
    if base is None:
        if row['mass_ratio']!=1:raise ValueError('observed original body mass required to change shapeshift mass')
        return None
    if type(base) not in (int,float) or not isfinite(base) or base<0:
        raise ValueError('original body mass must be finite and nonnegative')
    mass=base*row['mass_ratio']
    if not isfinite(mass):raise ValueError('shapeshift mass exceeds finite measurement range')
    return mass


def shapeshift_weight_class(actor,row):
    """Reuse the selected Weight Class reference; shared endpoints need observation."""
    chosen=row['mass_weight_class']
    if row['mass_ratio']==1:
        if chosen is not None:raise ValueError('unchanged shapeshift mass keeps its original Weight Class')
        return actor.spec.get('weight_class')
    mass=shapeshift_mass(actor,row)
    table='pokemon/weight-classes'
    if actor.r._selected_rule(table)!=table:raise ValueError('selected Weight Class table needs its own physical policy')
    # These are the kg intervals preserved by the existing selected table. Its
    # overlapping endpoints do not authorize silently choosing the upper class.
    expected=('0~11kg / 0~25 lbs','11~25kg / 25~55 lbs','25~50kg / 55~110 lbs',
              '50~100kg / 110~220 lbs','100~200kg / 220~440 lbs','200kg / 440lbs 이상')
    rows=actor.r.mech(table)['by_weight_class']
    if any(rows[str(n)]['description']!=text for n,text in enumerate(expected,1)):
        raise ValueError('changed Weight Class table needs its own physical policy')
    intervals=((0,11),(11,25),(25,50),(50,100),(100,200))
    candidates=[n for n,(lo,hi) in enumerate(intervals,1) if lo<=mass<=hi]
    if mass>200:candidates.append(6) # Official Core1.05 p342 says heavier than200kg.
    if chosen is None:
        if len(candidates)!=1:raise ValueError('shared Weight Class boundary requires observed mass_weight_class')
        return candidates[0]
    if type(chosen)is not int or chosen not in candidates:
        raise ValueError('observed shapeshift Weight Class disagrees with actual mass interval')
    return chosen


def weight_kg(actor):
    """One current body-mass authority; catalog and original sheet stay unchanged."""
    import body_modes as MODES
    row=MODES.validate(actor)
    return shapeshift_mass(actor,row) if row and row['mode']=='shapeshift' else actor.spec.get('weight_kg')


def weight_class(actor):
    """Apply current body class beneath the existing ordered source modifiers."""
    import body_modes as MODES,state_grants as GRANTS
    row=MODES.validate(actor)
    if not row or row['mode']!='shapeshift' or row['mass_ratio']==1:
        return actor._weight_class if actor._weight_class is not None else actor.spec.get('weight_class')
    physical=shapeshift_weight_class(actor,row)
    modified=GRANTS.prepare_weight_baseline(actor,physical)
    return modified if modified is not None else physical


def cells(actor,*,require_complete=False):
    view=projection(actor)
    if view["cells"] is None or (require_complete and not view["geometry_complete"]):
        raise ValueError("full observed body geometry and concrete location are required")
    return set(view["cells"])


def observe(engine,actor,offsets,*,reason):
    W._text(reason,"body observation reason")
    if W.actor_index(engine).get(actor.entity_id) is not actor:
        raise ValueError("actual registered actor required")
    import copy
    staged=copy.copy(actor);staged.spec=dict(actor.spec)
    staged.spec["footprint"]={"kind":"observed_cells","offsets":deepcopy(offsets),"reason":reason}
    # The observation changes the base shape. An effective mode must not hide
    # its structure; current-map fit still uses the effective active shape.
    import body_modes as MODES
    base=copy.copy(staged);base.spec=dict(staged.spec);base.spec.pop(MODES.KEY,None)
    validate(base)
    validate(staged)
    import actor_templates as TEMPLATES
    if W.location_of(staged)["kind"]=="grid" and not TEMPLATES.multipart_can_place(engine,staged,staged.pos):
        raise ValueError("observed multipart body exceeds its starting-position region")
    if W.location_of(actor)["kind"]=="grid" and getattr(engine,"grid",None) is not None:
        if any(not engine.grid.inside(cell) for cell in cells(staged,require_complete=True)):
            raise ValueError("observed body extends outside the current map")
    old=deepcopy(actor.spec.get("footprint"))
    actor.spec["footprint"]=staged.spec["footprint"]
    actor._state_revision+=1
    engine.gm._rec("body footprint",old,actor.spec["footprint"],reason,actor)
    return projection(actor)


TRAINER_WEIGHT_SOURCE="input/ch02-character-creation.md:147,222"


def trainer_weight(value,*,unit="lb"):
    """Exact source intervals; rounded kg annotations do not replace lb bounds."""
    from decimal import Decimal,InvalidOperation
    if isinstance(value,bool) or not isinstance(value,(str,int,float)):
        raise ValueError("observed trainer weight must be a finite nonnegative number")
    try:quantity=Decimal(str(value))
    except InvalidOperation as exc:raise ValueError("invalid trainer weight") from exc
    if not quantity.is_finite() or quantity<0:
        raise ValueError("observed trainer weight must be a finite nonnegative number")
    if unit not in ("lb","kg"):raise ValueError("weight unit must be lb or kg")
    pounds=quantity if unit=="lb" else quantity/Decimal("0.45359237")
    kg=quantity if unit=="kg" else quantity*Decimal("0.45359237")
    from math import isfinite
    if not isfinite(float(kg)):raise ValueError("weight exceeds supported finite measurement range")
    weight_class=3 if 55<=pounds<=110 else 4 if 111<=pounds<=220 else 5 if pounds>220 else None
    return {"value":str(quantity),"unit":unit,"pounds":str(pounds),"weight_kg":float(kg),
            "source":TRAINER_WEIGHT_SOURCE,"weight_class":weight_class,
            "classification":"source_interval" if weight_class is not None else "source_unspecified",
            "reason":None if weight_class is not None else "Source does not classify weights below55lb or strictly between110lb and111lb."}


def observe_trainer_weight(engine,actor,value,*,unit="lb",weight_class=None,reason):
    """Record actual weight and its source/GM class together without hiding grants."""
    W._text(reason,"trainer weight observation reason")
    if actor.kind!="trainer" or W.actor_index(engine).get(actor.entity_id) is not actor:
        raise ValueError("actual registered trainer required")
    observation=trainer_weight(value,unit=unit)
    if weight_class is not None:
        F.integer(weight_class,"explicit Weight Class",1,7)
        if observation["weight_class"] not in (None,weight_class):
            raise ValueError("explicit class disagrees with the sourced weight interval")
        if observation["weight_class"] is None:
            observation.update(weight_class=weight_class,classification="gm_explicit",reason=reason)
    before=deepcopy(actor.spec.get("trainer_weight_observation"))
    F.base_patch(actor,{"weight_kg":observation["weight_kg"],"weight_class":observation["weight_class"]},
                 reason=reason,source=TRAINER_WEIGHT_SOURCE)
    actor.spec["trainer_weight_observation"]=observation
    engine.gm._rec("trainer weight",before,observation,reason,actor)
    return projection(actor)


SPATIAL_SOURCE="input/ch07-combat.md:123,134,158,160"


def at_position(actor, position=None, *, require_complete=True):
    """Translate one authoritative body, without changing the actor or its token."""
    if not isinstance(getattr(actor,'spec',None),dict):raise ValueError('actual actor body required')
    occupied=cells(actor,require_complete=require_complete)
    if position is None:return occupied
    position=F.location({'kind':'grid','cell':position})['cell']
    origin=W.grid_cell(actor)
    return {(x+position[0]-origin[0],y+position[1]-origin[1]) for x,y in occupied}


def adjacent(left,right,*,cardinal=False,left_position=None,right_position=None):
    """Any two occupied squares touching; overlap is not adjacency."""
    from grid import cheb
    a=at_position(left,left_position);b=at_position(right,right_position)
    if a.intersection(b):return False
    distance=(lambda x,y:abs(x[0]-y[0])+abs(x[1]-y[1])) if cardinal else cheb
    return any(distance(x,y)==1 for x in a for y in b)


def in_range(engine,left,right,reach,*,left_position=None,move=None):
    from grid import cheb
    a=attack_cells(engine,left,move,position=left_position);b=at_position(right)
    import body_modes as MODES
    return any(cheb(x,y)<=reach and not engine.grid.blocked(x,y) and not MODES.blocks_line(engine,x,y,ignored=(left,right)) for x in a for y in b)


def can_place(engine,actor,position,*,origin=None,altitude=None,ignore_actors=(),underground=None):
    """Known body fits the map and clears other bodies/blocking cells."""
    proposed=at_position(actor,position)
    import actor_templates as TEMPLATES
    if not TEMPLATES.multipart_can_place(engine,actor,position):return False
    import living_weapon as LIVING
    proposed=LIVING.placement_cells(engine,actor,position,proposed)
    if any(not engine.grid.inside(q) or q in engine.grid.blocking for q in proposed):return False
    from physical_limits import number
    if altitude is None:altitude=actor.spec.get('_movement_altitude',0)
    number(altitude,'destination altitude',minimum=0)
    if underground is None:
        import burrow_tunnels as TUNNELS
        underground=TUNNELS.plane(engine,actor,position) if altitude==0 else False
    if type(underground)is not bool:raise ValueError('actual underground placement state required')
    occupied=set()
    import control_mount as MOUNT
    ignored=MOUNT.travel_group(engine,actor)
    ignored=(*ignored,*LIVING.group(engine,actor))
    ignored_ids={member.entity_id for member in ignored}
    import body_modes as MODES
    for other in getattr(engine,'everyone',[]):
        if other.entity_id in ignored_ids or other in ignore_actors or other.fainted or not other.on_field or other.captured:continue
        if MODES.flat(actor) or MODES.flat(other):continue
        other_altitude=number(other.spec.get('_movement_altitude',0),'body altitude',minimum=0)
        if other_altitude==altitude and bool(other.spec.get('_burrow',{}).get('underground'))==underground:
            occupied.update(at_position(other))
    import control_vehicle as CONTROL
    if not underground:occupied.update(CONTROL.occupied_cells(engine,actor,altitude=altitude))
    if proposed.intersection(occupied):return False
    if origin is not None:
        old=at_position(actor,origin);dx=position[0]-origin[0];dy=position[1]-origin[1]
        import body_modes as MODES
        if any(MODES.movement_blocked(engine,actor,q,(q[0]+dx,q[1]+dy),altitude=altitude,underground=underground) for q in old):return False
    return True


PASSAGES='observed_body_passages'


def _passages(obj):
    """Real surface measurements, never an instruction to remove a map wall."""
    import map_terrain as TERRAIN,resolution_transaction as TX
    from physical_limits import number
    rows=obj.get(PASSAGES,{})
    if type(rows)is not dict:raise ValueError('identified body passage observations required')
    for uid,row in rows.items():
        W._text(uid,'passage identity')
        if type(row)is not dict or set(row)!={'passage_id','object_id','source','reason','edge','height_m','width_m','surface_location','map_id','map_size','sha256'}:raise ValueError('exact physical passage observation required')
        if row['passage_id']!=uid or row['object_id']!=obj.get('id') or row['source']!='gm/observation':raise ValueError('passage belongs to another actual surface')
        W._text(row['reason'],'passage observation reason');W._text(row['map_id'],'passage map identity')
        if row['sha256']!=TX.json_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('physical passage observation changed')
        edge=row['edge']
        if not isinstance(edge,(list,tuple)) or len(edge)!=2:raise ValueError('cardinal passage surface required')
        a,b=(TERRAIN.point(p) for p in edge)
        if abs(a[0]-b[0])+abs(a[1]-b[1])!=1 or tuple(sorted((a,b)))!=(a,b):raise ValueError('canonical cardinal passage surface required')
        size=row['map_size']
        if not isinstance(size,(list,tuple)) or len(size)!=2:raise ValueError('passage map dimensions required')
        width,height=(F.integer(v,'passage map dimension',1) for v in size)
        if any(not(0<=x<width and 0<=y<height) for x,y in (a,b)):raise ValueError('passage outside observed map')
        loc=F.location(row['surface_location'])
        if loc['kind']!='grid' or loc['cell'] not in (a,b):raise ValueError('passage must be on its actual surface location')
        number(row['height_m'],'observed passage height',minimum=0)
        number(row['width_m'],'observed passage width',minimum=0)
    return rows


def validate_passages(engine):
    for obj in getattr(engine,'_physical_objects',{}).values():
        if type(obj)is dict:_passages(obj)
    return True


def observe_passage(engine,object_id,edge,*,passage_id,height_m,width_m,reason):
    """Observe a real gap on a registered physical surface in the current map."""
    import state_grants as G,map_terrain as TERRAIN,resolution_transaction as TX
    W._text(object_id,'actual passage surface');W._text(passage_id,'passage identity');W._text(reason,'passage observation reason')
    if not isinstance(edge,(list,tuple)) or len(edge)!=2:raise ValueError('cardinal passage surface required')
    edge=tuple(sorted(TERRAIN.point(p) for p in edge))
    def apply(e,_):
        if e.grid is None or edge not in e.grid.walls:raise ValueError('passage requires its actual mapped wall surface')
        obj=getattr(e,'_physical_objects',{}).get(object_id)
        if type(obj)is not dict:raise ValueError('actual registered passage surface required')
        W.require_usable_object(obj)
        if any(obj.get(k) for k in ('carrier_id','equipped_by','telekinetic_holder_id')):raise ValueError('passage surface must be stationary')
        _passages(obj)
        if not hasattr(e.grid,'_tunnel_map_id'):
            from uuid import uuid4
            e.grid._tunnel_map_id=str(uuid4())
        row=dict(passage_id=passage_id,object_id=object_id,source='gm/observation',reason=reason,
                 edge=[list(p) for p in edge],height_m=height_m,width_m=width_m,
                 surface_location=W.location_of(obj),map_id=e.grid._tunnel_map_id,map_size=[e.grid.w,e.grid.h])
        row['sha256']=TX.json_fingerprint(row)
        old=deepcopy(obj.get(PASSAGES,{}).get(passage_id))
        obj.setdefault(PASSAGES,{})[passage_id]=row
        _passages(obj)
        e.gm._rec('body passage '+object_id,old,row,reason)
        return deepcopy(row)
    return G.transition(engine,None,apply,include_grid=True)


def fits_observed_passage(engine,edge,*,height_m,width_m):
    """Consume only current-map, same-location, present physical measurements."""
    for obj in getattr(engine,'_physical_objects',{}).values():
        for row in _passages(obj).values():
            if (row['map_id']!=getattr(engine.grid,'_tunnel_map_id',None)
                    or row['map_size']!=[engine.grid.w,engine.grid.h]
                    or tuple(tuple(p) for p in row['edge'])!=edge
                    or W.location_of(obj)!=row['surface_location']
                    or any(obj.get(k) for k in ('carrier_id','equipped_by','telekinetic_holder_id'))):continue
            life=W.physical_lifecycle(obj)
            if life['consumed'] or life['destroyed']:continue
            if height_m<=row['height_m'] and width_m<=row['width_m']:return True
    return False


def _known_overlap(engine,left,right):
    import control_mount as MOUNT,living_weapon as LIVING,pass_moves as PASS
    return (right in MOUNT.travel_group(engine,left) or right in LIVING.group(engine,left)
            or PASS.transient_overlap(engine,left,right))


def flanking(engine,target):
    """Derived weighted non-adjacent foe set; never store a second condition flag.

    Unknown geometry is a pending state, not a claim that a token is a full body.
    The source is a planar grid rule; unresolved cross-plane membership stays pending.
    """
    result={'source':SPATIAL_SOURCE,'target_id':target.entity_id,'flanked':False,
            'required':None,'foes':[],'contributors':[],'pending':[],'evasion_penalty':0}
    if __import__('martial_artist').unflanked(target):return result
    seen=set();foes=[]
    for c in getattr(engine,'everyone',[]) or []:
        if c is target or id(c) in seen:continue
        seen.add(id(c))
        if c.side!=target.side and c.on_field and not c.fainted and not c.captured:foes.append(c)
    if len(foes)<2 or not target.on_field or target.fainted or target.captured:return result
    width=WIDTH.get(target.spec.get('size'))
    if engine.grid is None or width is None or not projection(target)['geometry_complete']:
        result.update(flanked=None,evasion_penalty=None,pending=['mapped target size and complete footprint required']);return result
    result['required']=width+1
    tcells=cells(target,require_complete=True);weighted=[]
    from grid import cheb
    for c in foes:
        if not projection(c)['geometry_complete'] or WIDTH.get(c.spec.get('size')) is None:
            result['pending'].append('complete foe size/footprint: '+c.entity_id);continue
        if c.spec.get('_movement_altitude',0)!=target.spec.get('_movement_altitude',0) or bool(c.spec.get('_burrow',{}).get('underground'))!=bool(target.spec.get('_burrow',{}).get('underground')):
            result['pending'].append('cross-plane foe membership: '+c.entity_id);continue
        body=cells(c,require_complete=True)
        if body.intersection(tcells):
            if _known_overlap(engine,c,target):continue
            result['pending'].append('overlapping bodies: '+c.entity_id);continue
        contacts=sorted(q for q in body if any(cheb(q,t)==1 for t in tcells))
        if not contacts:continue
        weight=len(contacts) if WIDTH[c.spec['size']]>1 else 1
        result['foes'].append({'entity_id':c.entity_id,'contact_cells':contacts,'weight':weight})
        weighted.append((c,weight))
    for i,(a,_) in enumerate(weighted):
        for b,_ in weighted[i+1:]:
            if cells(a).intersection(cells(b)) and not _known_overlap(engine,a,b):result['pending'].append('overlapping foes: '+a.entity_id+', '+b.entity_id)
    # Every distinct selected foe must be non-adjacent to every other selected foe.
    def choose(index,chosen,total):
        if len(chosen)>=2 and total>=result['required']:return chosen
        if total+sum(n for _,n in weighted[index:])<result['required']:return None
        for i in range(index,len(weighted)):
            actor,count=weighted[i]
            if all(not cells(actor).intersection(cells(prior)) and not adjacent(actor,prior) for prior in chosen):
                found=choose(i+1,chosen+[actor],total+count)
                if found:return found
        return None
    witnesses=choose(0,[],0)
    if witnesses:result.update(flanked=True,contributors=[c.entity_id for c in witnesses],evasion_penalty=-2)
    elif result['pending']:result.update(flanked=None,evasion_penalty=None)
    return result


REACH_SOURCE="capability/도달"
REACH_OBSERVATION="melee_reach_observation"


def validate_reach_observation(actor):
    from math import isfinite
    row=actor.spec.get(REACH_OBSERVATION)
    if row is None:return None
    if not isinstance(row,dict) or set(row)!={'source','value','basis_size','anatomy','reason'}:
        raise ValueError('exact sourced reach observation required')
    if row['source']!=REACH_SOURCE or actor.r._selected_rule(REACH_SOURCE)!=REACH_SOURCE:
        raise ValueError('selected Reach source mismatch')
    width=WIDTH.get(row['basis_size'])
    value=row['value']
    if width is None or type(value) not in (int,float) or not isfinite(value) or value<=(2 if width==1 else 3):
        raise ValueError('exceptional reach must exceed sourced size baseline')
    if row['anatomy'] not in ('very_large_body','long_limbs'):
        raise ValueError('exceptional reach requires large body or long limbs')
    W._text(row['reason'],'observed exceptional reach reason')
    return row


def melee_reach(actor):
    """Live capability, not an independent range buff or an adjacency change."""
    import state_grants as G
    row=validate_reach_observation(actor)
    if '도달' not in G.effective_capabilities(actor,only=('도달',)):return 1
    if actor.r._selected_rule(REACH_SOURCE)!=REACH_SOURCE:
        raise ValueError('selected Reach source needs its own policy')
    width=WIDTH.get(actor.spec.get('size'))
    if width is None:raise ValueError('Reach requires observed body size')
    baseline=2 if width==1 else 3
    if row and row['basis_size']==actor.spec.get('size'):return row['value']
    return baseline


def observe_melee_reach(engine,actor,value,*,anatomy,reason):
    """Record the GM's unspecified exceptional distance, without granting Reach."""
    import state_grants as G
    from copy import copy
    if W.actor_index(engine).get(actor.entity_id) is not actor or '도달' not in G.effective_capabilities(actor,only=('도달',)):
        raise ValueError('registered actor with Reach required')
    row={'source':REACH_SOURCE,'value':value,'basis_size':actor.spec.get('size'),'anatomy':anatomy,'reason':reason}
    probe=copy(actor);probe.spec=dict(actor.spec);probe.spec[REACH_OBSERVATION]=row
    validate_reach_observation(probe)
    before=deepcopy(actor.spec.get(REACH_OBSERVATION));actor.spec[REACH_OBSERVATION]=deepcopy(row)
    actor._state_revision+=1
    engine.gm._rec('exceptional melee reach',before,row,reason,actor)
    return melee_reach(actor)
