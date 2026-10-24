"""Actual Smokescreen occurrences behind the existing accuracy cell projection."""
from copy import deepcopy


def _state(engine):
    state=getattr(engine,'_smoke_regions',None)
    if state:
        return state
    # A historical flat field is current smoke, not evidence of its producers.
    return {'regions':{},'legacy_cells':dict(engine.zone_cells),'legacy_zones':dict(engine.zones)}


def _project(engine,state):
    engine.zone_cells.clear();engine.zone_cells.update(state['legacy_cells'])
    engine.zones.clear();engine.zones.update(state['legacy_zones'])
    for row in state['regions'].values():
        penalty=row['accuracy_penalty']
        for cell in row['cells']:
            engine.zone_cells[cell]=min(engine.zone_cells.get(cell,0),penalty)
        if row['target_id'] is not None:
            key=row['target_id'];engine.zones[key]=min(engine.zones.get(key,0),penalty)
    engine._smoke_regions=state if state['regions'] or state['legacy_cells'] or state['legacy_zones'] else {}


def _region(engine,state,*,cells=(),target_id=None,penalty,source,reason=None):
    sequence=getattr(engine,'_smoke_region_sequence',0)+1
    engine._smoke_region_sequence=sequence
    identity='smoke:'+str(sequence)
    state['regions'][identity]={'id':identity,'source':source,'cells':set(cells),
        'target_id':target_id,'accuracy_penalty':penalty,'observation_reason':reason}
    _project(engine,state)
    return identity


def require_bound_line(engine,cells):
    if set(cells).intersection(_state(engine)['legacy_cells']):
        raise ValueError('Whirlwind touches legacy smoke without observed region membership; observe the actual smoke region before action cost')


def observe_region(engine,cells,*,reason):
    """Adopt an observed current legacy occurrence without inventing its history."""
    import common_checks as C
    import state_grants as G
    if engine.grid is None:raise ValueError('observed smoke region requires actual mapped cells')
    if type(reason) is not str or not reason.strip():raise ValueError('actual smoke region observation reason required')
    if not isinstance(cells,(list,tuple,set,frozenset)) or not cells:raise ValueError('actual smoke region cells required')
    selected=set()
    for cell in cells:
        if not isinstance(cell,(list,tuple)) or len(cell)!=2:raise ValueError('actual smoke cell pair required')
        selected.add(tuple(C.integer(v,'observed smoke coordinate') for v in cell))
    state=_state(engine)
    if any(not engine.grid.inside(c) or c not in state['legacy_cells'] for c in selected):
        raise ValueError('observed region must stay within actual existing legacy smoke cells')
    penalties={state['legacy_cells'][c] for c in selected}
    if len(penalties)!=1:raise ValueError('one observed smoke occurrence needs its actual common penalty')
    def commit(e,_actor):
        state=_state(e)
        for cell in selected:state['legacy_cells'].pop(cell,None)
        identity=_region(e,state,cells=selected,penalty=next(iter(penalties)),
                         source='gm/observed-current-smoke',reason=reason)
        e.gm._rec('현재 연막 영역 관측',None,deepcopy(state['regions'][identity]),reason)
        return identity
    return G.transition(engine,None,commit,include_rulings=True)


def disperse_intersecting(engine,cells):
    require_bound_line(engine,cells)
    state=_state(engine);area=set(cells)
    gone=[key for key,row in state['regions'].items() if row['cells'].intersection(area)]
    for key in gone:state['regions'].pop(key)
    _project(engine,state)
    return gone


def remove_cells(engine,cells):
    """Razor Wind explicitly destroys smoke on only the occupied/adjacent cells."""
    state=_state(engine);area=set(cells)
    for cell in area:state['legacy_cells'].pop(cell,None)
    for key,row in list(state['regions'].items()):
        row['cells'].difference_update(area)
        if not row['cells'] and row['target_id'] is None:state['regions'].pop(key)
    _project(engine,state)


def clear(engine):
    engine.zone_cells.clear();engine.zones.clear();engine._smoke_regions={}


def apply(engine,target,move,zone,source,confidence):
    state=_state(engine);penalty=zone['accuracy_penalty']
    if engine.grid is not None:
        cells=move['_effect_area_cells']
        identity=_region(engine,state,cells=cells,penalty=penalty,source=source)
        engine.log(f"    {move['_area_aim']} 중심 {len(cells)}칸에 연막: 명중 {penalty}",f'{source} ({confidence})')
        return {'cells':sorted(cells),'accuracy_penalty':penalty,'region_id':identity}
    identity=_region(engine,state,target_id=target.entity_id,penalty=penalty,source=source)
    engine.log(f"    {target.name} 주변에 연막: 명중 {penalty}",f'{source} ({confidence})')
    return {'target_id':target.entity_id,'accuracy_penalty':penalty,'region_id':identity}
