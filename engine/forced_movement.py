"""Shared sourced displacement; no movement ability, action or collision damage."""
import body_state as BODY
import world_entities as WORLD
import common_checks as C


def can_step(engine,target,destination):
    if engine.grid is None:return False
    if type(target)is dict:
        origin=WORLD.grid_cell(target)
        if not engine.grid.inside(destination) or engine.grid.blocked(origin,destination):return False
        for other in WORLD.actors(engine):
            if other.on_field and not other.captured and other.spec.get('_movement_altitude',0)==0 and destination in BODY.cells(other,require_complete=True):return False
        return True
    return BODY.can_place(engine,target,destination,origin=target.pos,
                          altitude=target.spec.get('_movement_altitude',0))


def _managed(engine,target):
    if type(target)is dict:return False
    import control_mount as MOUNT,environment_change as EC,grapple_state as GRAPPLE
    return MOUNT.managed_subject(target) or EC.managed(engine,target) or GRAPPLE.relation(engine,target) is not None


def displace(engine,actor,target,*,direction,distance,source,stop_cells=(),allow_fainted=False):
    import state_grants as G
    if _managed(engine,target):
        return G.transition(engine,actor,lambda e,c,other:_displace(e,c,other,direction=direction,distance=distance,
            source=source,stop_cells=stop_cells,allow_fainted=allow_fainted),participants=(target,))
    return _displace(engine,actor,target,direction=direction,distance=distance,source=source,stop_cells=stop_cells,allow_fainted=allow_fainted)


def _displace(engine,actor,target,*,direction,distance,source,stop_cells=(),allow_fainted=False):
    C.integer(distance,'forced movement distance',0)
    if not isinstance(direction,(tuple,list)) or len(direction)!=2 or any(type(x)is not int or x not in (-1,0,1) for x in direction) or tuple(direction)==(0,0):
        raise ValueError('explicit unit displacement direction required')
    return _along_path(engine,actor,target,points=None,source=source,stop_cells=stop_cells,
                      allow_fainted=allow_fainted,_vector=(tuple(direction),distance))


def along_path(engine,actor,target,*,points,source,allow_fainted=False):
    """Explicit continuous forced route for an actual body or registered object."""
    import state_grants as G
    if _managed(engine,target):
        return G.transition(engine,actor,lambda e,c,other:_along_path(e,c,other,points=points,source=source,
            allow_fainted=allow_fainted),participants=(target,))
    return _along_path(engine,actor,target,points=points,source=source,allow_fainted=allow_fainted)


def _along_path(engine,actor,target,*,points,source,stop_cells=(),allow_fainted=False,_vector=None):
    WORLD.require_actors(engine,actor)
    is_object=type(target)is dict
    if is_object:
        if getattr(engine,'_physical_objects',{}).get(target.get('id'))is not target:raise ValueError('actual registered forced-movement object required')
        WORLD.require_usable_object(target)
        if any(target.get(k) for k in ('carrier_id','equipped_by','telekinetic_holder_id')):raise ValueError('held object requires explicit release before forced movement')
    else:
        WORLD.require_actors(engine,target)
        if not target.on_field or target.captured or (target.fainted and not allow_fainted):raise ValueError('displacement target is unavailable under declared policy')
    if type(source)is not str or not source.strip():raise ValueError('displacement source required')
    if type(allow_fainted)is not bool:raise ValueError('explicit unconscious displacement policy required')
    if engine.grid is None:raise ValueError('mapped displacement required')
    origin=WORLD.grid_cell(target)
    if _vector is None:
        if not isinstance(points,(list,tuple)) or not points or any(not isinstance(p,(list,tuple)) or len(p)!=2 or any(type(v)is not int for v in p) for p in points):
            raise ValueError('explicit integer forced movement path required')
        route=[tuple(p) for p in points]
        if route[0]!=origin or any(max(abs(b[i]-a[i]) for i in (0,1))!=1 for a,b in zip(route,route[1:])):raise ValueError('continuous forced route from actual origin required')
        requested=len(route)-1;steps=iter(route[1:])
    else:
        direction,requested=_vector
        steps=((origin[0]+direction[0]*n,origin[1]+direction[1]*n) for n in range(1,requested+1))
    if not isinstance(stop_cells,(list,tuple)) or any(not isinstance(q,(list,tuple)) or len(q)!=2 or any(type(v)is not int for v in q) for q in stop_cells):
        raise ValueError('explicit mapped stopping cells required')
    stops={tuple(q) for q in stop_cells}
    if len(stops)!=len(stop_cells) or any(not engine.grid.inside(q) for q in stops):raise ValueError('distinct in-map stopping cells required')
    import coat_effects as COATS
    path=[origin];stop=None
    if not is_object and COATS.blocks_displacement(engine,target):stop='immune'
    else:
        for destination in steps:
            if not can_step(engine,target,destination):stop='collision';break
            if is_object:
                WORLD.observe_location(engine,target,dict(WORLD.location_of(target),cell=destination),reason='source-owned forced object displacement',source=source)
            else:
                target.pos=destination
            path.append(destination)
            if not is_object:
                import effects_ext as EXT
                EXT.on_enter_cell(engine,target,destination,previous_position=path[-2])
                if (target.fainted and not allow_fainted) or not target.on_field or target.captured:stop='interrupted';break
                if tuple(target.pos)!=destination:stop='relocated';break
            if destination in stops:stop='declared_stop';break
    if not is_object:
        import control_mount as MOUNT
        MOUNT.sync(engine,target)
        if len(path)>1:MOUNT.notify(engine,target,'forced_move')
    return {'source':source,'origin':origin,'position':WORLD.grid_cell(target),'path':path,
            'moved':len(path)-1,'requested':requested,'stopped_by':stop}
