"""Ch07:140-152: base terrain, special overlays and actual body queries."""
import common_checks as C
from grid import cheb

BASES=('regular','earth','underwater')
SOURCE='input/ch07-combat.md:140-152'

def point(value):
    if not isinstance(value,(tuple,list)) or len(value)!=2:raise ValueError('actual map cell required')
    return tuple(C.integer(v,'map coordinate',0) for v in value)

def key(cell):return str(cell[0])+','+str(cell[1])

def validate(grid):
    if grid is None:return
    map_id=getattr(grid,'_tunnel_map_id',None)
    if map_id is not None and (type(map_id) is not str or not map_id.strip()):raise ValueError('actual tunnel map identity required')
    rows=getattr(grid,'base_terrain',{})
    if type(rows) is not dict:raise ValueError('base terrain map required')
    for cell,base in rows.items():
        if type(cell) is not str:raise ValueError('identified base terrain cell required')
        try:q=point(tuple(int(v) for v in cell.split(',')))
        except (TypeError,ValueError):raise ValueError('invalid base terrain coordinate') from None
        if key(q)!=cell or not grid.inside(q) or base not in BASES:raise ValueError('actual mapped base terrain required')

def observe(engine,cells,*,base,reason,rough=None,slow=None,blocking=None):
    """An explicit GM map observation, separate from ecological Naturewalk tags."""
    if engine.grid is None:raise ValueError('map observation requires an actual grid')
    if base not in BASES or type(reason) is not str or not reason.strip():raise ValueError('base terrain and observation reason required')
    cells=[point(p) for p in cells]
    if not cells or len(set(cells))!=len(cells) or any(not engine.grid.inside(p) for p in cells):raise ValueError('distinct actual map cells required')
    if any(v is not None and type(v) is not bool for v in (rough,slow,blocking)):raise ValueError('explicit boolean terrain overlays required')
    import state_grants as G
    def apply(e,_):
        grid=e.grid
        if not hasattr(grid,'_tunnel_map_id'):
            from uuid import uuid4
            grid._tunnel_map_id=str(uuid4())
        for p in cells:
            if not hasattr(grid,'base_terrain'):grid.base_terrain={}
            grid.base_terrain[key(p)]=base
            for name,value in (('rough',rough),('slow',slow),('blocking',blocking)):
                if value is not None:
                    values=getattr(grid,name)
                    values.add(p) if value else values.discard(p)
        validate(grid)
        result={'cells':cells,'base':base,'rough':rough,'slow':slow,'blocking':blocking,'source':SOURCE,'reason':reason}
        observations=dict(getattr(grid,'terrain_observations',{}))
        for p in cells:observations.setdefault(key(p),{})['map_terrain']=dict(result)
        grid.terrain_observations=observations
        e.log('  지도 지형 관측: '+base+' '+str(cells)+' ('+reason+')',SOURCE)
        return result
    return G.transition(engine,None,apply,include_grid=True)

def base_at(grid,cell):return getattr(grid,'base_terrain',{}).get(key(cell),'regular')

def can_travel(engine,actor,position,mode,*,altitude=None,underground=None):
    """Movement permission consumes the selected capability, not only placement."""
    import body_state as BODY
    import movement_actions as MOVEMENT
    if engine.grid is None:return True
    cells=BODY.at_position(actor,position)
    bases={base_at(engine.grid,p) for p in cells}
    altitude=actor.spec.get('_movement_altitude',0) if altitude is None else altitude
    underground=bool(actor.spec.get('_burrow',{}).get('underground')) if underground is None else underground
    caps=MOVEMENT.capabilities(engine,actor)
    if mode in ('land','육상') and underground and 'earth' not in bases:
        import burrow_tunnels as TUNNELS
        if not TUNNELS.can_exit(engine,actor,position):return False
    if 'earth' in bases:
        digging=mode in ('burrow','지중') and underground and caps.get('burrow',0)>0
        import burrow_tunnels as TUNNELS
        passage=mode in ('land','육상') and altitude==0 and TUNNELS.can_pass(engine,actor,position)
        if not digging and not passage:return False
    if 'underwater' in bases:
        if mode in ('sky','levitate','공중/부유') and altitude>0:return True
        import ice_lake as ICE_LAKE
        if ICE_LAKE.surface_hole_entry(engine,actor,position,mode,altitude=altitude,underground=underground):return True
        if mode not in ('swim','수중') or caps.get('swim',0)<=0:return False
    return True

def slow_multiplier(engine,actor,position,mode):
    if engine.grid is None or mode in ('sky','levitate','공중/부유'):return 1
    import body_state as BODY
    import movement_actions as MOVEMENT
    return 2 if any(p in engine.grid.slow and not MOVEMENT.ordinary_terrain(engine,actor,p)
                    for p in BODY.at_position(actor,position)) else 1

def accuracy_penalty(engine,attacker,target):
    """Intervening occupied spaces are rough; they do not become blocking walls."""
    if engine.grid is None:return 0
    import body_state as BODY
    import movement_actions as MOVEMENT
    grid=engine.grid;occupied=set()
    for other in getattr(engine,'everyone',()):
        if other is attacker or other is target or not other.on_field or other.captured or other.fainted:continue
        occupied.update(BODY.cells(other,require_complete=True))
    paths=[]
    for a in BODY.cells(attacker,require_complete=True):
        for b in BODY.cells(target,require_complete=True):
            if grid.blocked(a,b):continue
            path=[*grid.line_cells(a,b),b]
            rough=any(p in occupied or (p in grid.rough and not MOVEMENT.ordinary_terrain(engine,attacker,p)) for p in path)
            paths.append(rough)
    return -2 if paths and all(paths) else 0
