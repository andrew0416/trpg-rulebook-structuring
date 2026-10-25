"""Reviewed global field producer, state, consumers, and finite lifetime.

The generic ``field_effect`` opcode used to retain an anonymous dictionary.
Terrain replaces Terrain; reviewed Rooms and Gravity retain independent
source-bound occurrences while unrelated legacy fields keep their format.
"""
from copy import deepcopy
import json
import os


KIND = "global_terrain"
INDEPENDENT_KEY = "_independent_field_effects"
INDEPENDENT_SOURCES = frozenset((
    "move/중력", "move/매직룸", "move/트릭룸", "move/원더룸", "move/거다이천도",
))
DEFERRED = "_misty_deferred_statuses"
LOCAL_KEY = '_local_grass_occurrences'
LOCAL_SOURCE = 'ability/곰팡이군주'
LOCAL_SNOW_SOURCE = 'ability/아이스제트'


if __package__:
    from . import resolution_transaction as _FINGERPRINTS
else:
    import resolution_transaction as _FINGERPRINTS

def _grass_policy(rules):
    """Only the selected R0636 state component, never arbitrary field input."""
    from pathlib import Path
    import csv
    import hashlib
    path = Path(__file__).resolve().parents[1] / 'data/local-grass-field-policy.json'
    if not path.exists():
        path = Path(rules.root) / 'data/local-grass-field-policy.json'
    row = json.loads(path.read_text(encoding='utf-8'))
    source = Path(rules.root) / 'input/db/abilities.csv'
    if hashlib.sha256(source.read_bytes()).hexdigest() != row['file_sha256']:
        raise ValueError('local Grass source file changed')
    with source.open(encoding='utf-8-sig', newline='') as stream:
        cells = list(csv.reader(stream))[635]
    digest = _FINGERPRINTS.json_fingerprint(cells, sort_keys=False, compact=True, allow_nan=True)
    if (row['source_id'] != LOCAL_SOURCE or row['clause_id'] != 'C2CSV-ABILITY-R0636'
            or row['record'] != 636 or row['file'] != 'input/db/abilities.csv'
            or row['row_sha256'] != digest or cells[0] != row['name']
            or row['action'] != 'shift' or row['frequency'] != {'kind':'scene','uses':1}
            or row['geometry'] != {'shape':'burst','size':2}
            or row['until'] != 'scene_end' or row['field'] != '그래스'
            or row['effect'] != {'grounded_heal_turn_start':'max_hp/10','grounded_grass_damage_bonus':10}):
        raise ValueError('local Grass exact source contract changed')
    if rules._selected_rule(LOCAL_SOURCE) != LOCAL_SOURCE:
        raise ValueError('local Grass selected ability changed')
    return row



def local_policy(rules, source_id=LOCAL_SOURCE):
    if source_id == LOCAL_SOURCE:
        return _grass_policy(rules)
    if source_id != LOCAL_SNOW_SOURCE:
        raise ValueError('unreviewed local-field producer')
    from pathlib import Path
    import csv,hashlib
    import homebrew_weather as HOME
    path=Path(__file__).resolve().parents[1]/'data/local-snow-field-policy.json'
    if not path.exists():path=Path(rules.root)/'data/local-snow-field-policy.json'
    definition=json.loads(path.read_text(encoding='utf-8'))
    source=Path(rules.root)/'input/db/abilities.csv'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=definition['file_sha256']:
        raise ValueError('local Snow source file changed')
    with source.open(encoding='utf-8-sig',newline='') as stream:
        cells=list(csv.reader(stream))[641]
    digest=_FINGERPRINTS.json_fingerprint(cells,sort_keys=False,compact=True,allow_nan=True)
    expected={'source_id':LOCAL_SNOW_SOURCE,'clause_id':'CHB-WEATHER-003',
        'file':'input/db/abilities.csv','record':642,'row_sha256':digest,'name':'아이스제트',
        'action':'shift','frequency':{'kind':'scene','uses':1},'geometry':{'shape':'burst','size':2},
        'until':'next_round_end','field':'hail','effect':{'weather':'hail'},
        'native_effect':{'type':'create_terrain','terrain':'snow (설경)','shape':'burst 2','until':"end of user's next round"}}
    if cells[0]!='아이스제트' or any(definition.get(k)!=v for k,v in expected.items()):
        raise ValueError('local Snow exact source contract changed')
    native=json.loads((Path(rules.root)/'data/abilities-llm.json').read_text(encoding='utf-8'))['abilities']['아이스제트']
    if native!=[expected['native_effect']] or rules._selected_rule(LOCAL_SNOW_SOURCE)!=LOCAL_SNOW_SOURCE:
        raise ValueError('local Snow selected native producer changed')
    if HOME.canonical_weather(rules,'snow')!='hail':
        raise ValueError('local Snow requires the selected homebrew alias')
    return definition

def handles_local_snow(engine,source_id,effect):
    import homebrew_weather as HOME
    return source_id==LOCAL_SNOW_SOURCE and HOME.enabled(engine.r) and effect.get('type')=='create_terrain'

def prepare_local_snow(engine,actor,target,effect,source_id):
    import world_entities as WORLD,ability_transitions as ABILITIES,body_state as BODY
    WORLD.require_actors(engine,actor)
    definition=local_policy(engine.r,source_id)
    if not handles_local_snow(engine,source_id,effect) or {k:v for k,v in effect.items() if k!='_src'}!=definition['native_effect']:
        raise ValueError('local Snow needs its exact selected native effect')
    if target is not actor or not ABILITIES.active(actor,source_id):
        raise ValueError('local Snow needs its actual active ability owner')
    if not engine.encounter_active or engine.round_start_seconds is None or engine.grid is None:
        raise ValueError('local Snow needs an actual mapped open combat round')
    for other in WORLD.actor_index(engine).values():
        if other.on_field:BODY.cells(other,require_complete=True)
    if not engine.grid.inside(tuple(actor.pos)):
        raise ValueError('local Snow origin outside map')
    validate_local(engine)
    scene=actor.spec.get('frequency_state',{}).get('scene',0)
    if any(r['source_id']==source_id and r['creator_id']==actor.entity_id and r['scene']==scene
           for r in getattr(engine,LOCAL_KEY,{}).get('receipts',{}).values()):
        raise ValueError('local Snow already observed for this source Scene')
    return definition

def install_local_snow(engine,actor,target,effect,source_id,receipt,occurrence):
    import effect_contracts as CONTRACTS,frequency as FREQUENCY
    definition=prepare_local_snow(engine,actor,target,effect,source_id)
    CONTRACTS.validate_receipt(engine,receipt,source_id,occurrence,actor,target,effect)
    grid=engine.grid;origin=tuple(actor.pos)
    state=getattr(engine,LOCAL_KEY,{'version':1,'receipts':{}})
    row={'request_id':occurrence,'source_id':source_id,'clause_id':definition['clause_id'],
        'source_row_sha256':definition['row_sha256'],'creator_id':actor.entity_id,
        'scene':FREQUENCY.state(actor)['scene'],'round':engine.round_no,'origin':list(origin),
        'geometry':{'width':grid.w,'height':grid.h,'blocking':[list(p) for p in sorted(grid.blocking)],
            'walls':[[list(p) for p in wall] for wall in sorted(grid.walls)],'shape':'burst','size':2},
        'cells':[list(p) for p in sorted(grid.burst(origin,2))],
        'until':definition['until'],'name':'hail','effect':deepcopy(definition['effect']),
        'action':definition['action'],'frequency':deepcopy(definition['frequency']),'ended':False,
        'expires_round':engine.round_no+1,'effect_occurrence':occurrence,'observation_only':True}
    row['seal']=_local_seal(row);state['receipts'][occurrence]=row;setattr(engine,LOCAL_KEY,state)
    validate_local(engine)
    refresh_local_weather(engine)
    engine.log('Ice Jet local Snow observed as hail',source_id)
    return deepcopy(row)

def local_boundary(engine,*,round_end=False):
    if not round_end:return
    for row in validate_local(engine):
        if row['source_id']==LOCAL_SNOW_SOURCE and engine.round_no>=row['expires_round']:
            row['ended']=True;row['seal']=_local_seal(row)
    refresh_local_weather(engine)

def refresh_local_weather(engine):
    # Existing location/state reconciliation also refreshes owned Forecast.
    # Transitions clone this transient guard, preventing recursive reconciliation.
    if getattr(engine,'_local_weather_refreshing',False):return
    if not any(row.get('source_id')==LOCAL_SNOW_SOURCE for row in
               getattr(engine,LOCAL_KEY,{}).get('receipts',{}).values()):return
    engine._local_weather_refreshing=True
    try:
        import ability_state_projection as PROJECTION
        PROJECTION.weather_changed(engine)
    finally:
        vars(engine).pop('_local_weather_refreshing',None)

def local_weather_for(engine,actor):
    import world_entities as WORLD,body_state as BODY
    WORLD.require_actors(engine,actor)
    rows=[r for r in validate_local(engine) if r['source_id']==LOCAL_SNOW_SOURCE]
    if not rows or not actor.on_field:return None
    occupied=BODY.cells(actor,require_complete=True)
    matches=[r for r in rows if occupied.intersection(tuple(p) for p in r['cells'])]
    if not matches:return None
    # This finite producer has one identical Hail payload, independent of order.
    return dict(deepcopy(matches[0]),weather='hail',origin='ability-local',duration=None,local_to_actor=True)


def _local_seal(row):
    from resolution_transaction import request_fingerprint
    return request_fingerprint({k:v for k,v in row.items() if k != 'seal'})


def validate_local(engine, index=None):
    state = getattr(engine, LOCAL_KEY, None)
    if state is None:
        return []
    if not isinstance(state, dict) or set(state) != {'version','receipts'} or state['version'] != 1 or not isinstance(state['receipts'], dict):
        raise ValueError('invalid local Grass envelope')
    if index is None:
        import world_entities as WORLD
        index = WORLD.actor_index(engine)
    from grid import Grid
    seen = set()
    active_rows = []
    for request, receipt in state['receipts'].items():
        required = {'request_id','source_id','clause_id','source_row_sha256','creator_id','scene','round','origin','geometry','cells','until','name','effect','action','frequency','seal','ended'}
        if isinstance(receipt,dict) and receipt.get('source_id')==LOCAL_SNOW_SOURCE:
            required |= {'expires_round','effect_occurrence','observation_only'}
        if (not isinstance(receipt,dict) or set(receipt) != required
                or not isinstance(request,str) or not request.strip() or receipt['request_id'] != request
                or receipt['seal'] != _local_seal(receipt)):
            raise ValueError('local Grass original receipt changed')
        definition=local_policy(engine.r,receipt['source_id'])
        for key, value in {'source_id':definition['source_id'],'clause_id':definition['clause_id'],
                'source_row_sha256':definition['row_sha256'],'until':definition['until'],'name':definition['field'],
                'effect':definition['effect'],'action':definition['action'],'frequency':definition['frequency']}.items():
            if receipt[key] != value:
                raise ValueError('local Grass source or lifetime changed')
        owner = index.get(receipt['creator_id'])
        if owner is None:
            raise ValueError('local Grass creator missing')
        if type(receipt['scene']) is not int or receipt['scene'] < 0 or type(receipt['round']) is not int or not 0 <= receipt['round'] <= engine.round_no:
            raise ValueError('invalid local Grass creation clock')
        current_scene = owner.spec.get('frequency_state',{}).get('scene',0)
        if receipt['scene'] > current_scene or (receipt['creator_id'],receipt['source_id'],receipt['scene']) in seen:
            raise ValueError('local Grass duplicate or future activation')
        seen.add((receipt['creator_id'],receipt['source_id'],receipt['scene']))
        if type(receipt['ended']) is not bool or (not receipt['ended'] and receipt['scene'] != current_scene):
            raise ValueError('local Grass scene expiry changed')
        geo = receipt['geometry']
        if not isinstance(geo,dict) or set(geo) != {'width','height','blocking','walls','shape','size'} or geo['shape'] != 'burst' or geo['size'] != 2:
            raise ValueError('local Grass geometry changed')
        if any(type(geo[k]) is not int or geo[k] < 1 for k in ('width','height')):
            raise ValueError('local Grass map dimensions changed')
        def point(p):
            return isinstance(p,(list,tuple)) and len(p)==2 and all(type(x) is int for x in p) and 0<=p[0]<geo['width'] and 0<=p[1]<geo['height']
        if not point(receipt['origin']) or not all(point(p) for p in geo['blocking']) or not all(len(w)==2 and all(point(p) for p in w) for w in geo['walls']):
            raise ValueError('local Grass original map coordinates changed')
        grid = Grid(geo['width'],geo['height'],blocking=[tuple(p) for p in geo['blocking']],walls=[tuple(tuple(p) for p in w) for w in geo['walls']])
        expected = [list(p) for p in sorted(grid.burst(tuple(receipt['origin']),2))]
        if receipt['cells'] != expected:
            raise ValueError('local Grass cells disagree with native original geometry')
        if receipt['source_id']==LOCAL_SNOW_SOURCE:
            if (type(receipt['expires_round']) is not int or receipt['expires_round']!=receipt['round']+1
                    or receipt['effect_occurrence']!=request or receipt['observation_only'] is not True):
                raise ValueError('local Snow next-round deadline changed')
            rows=[row for row in getattr(engine,'_effect_dispatch_receipts',{}).values()
                  if row.get('occurrence')==request and row.get('source_id')==LOCAL_SNOW_SOURCE]
            if (len(rows)!=1 or rows[0].get('actor') is not owner or rows[0].get('target') is not owner
                    or {k:v for k,v in rows[0]['effect'].items() if k!='_src'}!=definition['native_effect']
                    or rows[0].get('status') not in ('dispatching','completed')):
                raise ValueError('local Snow lacks its actual native effect receipt')
            if not receipt['ended'] and engine.round_no>receipt['expires_round']:
                raise ValueError('local Snow survived its next round end')
        if not receipt['ended']:
            if receipt['source_id']==LOCAL_SOURCE:
                quota = owner.spec.get('frequency_state',{}).get('activations',{}).get(LOCAL_SOURCE,{})
                if quota != {'kind':'scene','period':receipt['scene'],'used':1}:
                    raise ValueError('local Grass lacks native Scene payment')
            active_rows.append(receipt)
    return active_rows


def activate_local_grass(engine, actor, target, *, request_id):
    import world_entities as WORLD
    import state_grants as GRANTS
    WORLD.require_actors(engine, actor)
    if target is not actor or not isinstance(request_id,str) or not request_id.strip():
        raise ValueError('local Grass needs actual user and explicit replay request')
    def apply(staged, owner):
        definition = local_policy(staged.r)
        validate_local(staged)
        state = getattr(staged,LOCAL_KEY,{'version':1,'receipts':{}})
        prior = state['receipts'].get(request_id)
        if prior is not None:
            if prior['creator_id'] != owner.entity_id:
                raise ValueError('local Grass request belongs to another actor')
            return deepcopy(prior)
        import ability_transitions as ABILITIES
        import body_state as BODY
        import frequency as FREQUENCY
        import turn as TURN
        if not ABILITIES.active(owner,LOCAL_SOURCE):
            raise ValueError('actual active Fungus Lord ability required')
        if staged.grid is None:
            raise ValueError('local Grass needs actual mapped geometry')
        BODY.cells(owner,require_complete=True)
        # Missing geometry must not be discovered after native payment.
        for other in WORLD.actor_index(staged).values():
            if other.on_field:
                BODY.cells(other,require_complete=True)
        origin = tuple(owner.pos)
        grid = staged.grid
        if not grid.inside(origin):
            raise ValueError('local Grass origin outside map')
        if not FREQUENCY.activation_allowed(owner,LOCAL_SOURCE,definition['frequency'],engine=staged,action_actor=owner):
            raise ValueError('local Grass Scene frequency exhausted')
        if not TURN.spend(staged,owner,'shift',definition['name']):
            raise ValueError('local Grass Shift action unavailable')
        FREQUENCY.consume_activation(owner,LOCAL_SOURCE,definition['frequency'],engine=staged,action_actor=owner)
        receipt = {'request_id':request_id,'source_id':LOCAL_SOURCE,'clause_id':definition['clause_id'],
            'source_row_sha256':definition['row_sha256'],'creator_id':owner.entity_id,
            'scene':owner.spec['frequency_state']['scene'],'round':staged.round_no,
            'origin':list(origin),'geometry':{'width':grid.w,'height':grid.h,
                'blocking':[list(p) for p in sorted(grid.blocking)],
                'walls':[[list(p) for p in wall] for wall in sorted(grid.walls)],'shape':'burst','size':2},
            'cells':[list(p) for p in sorted(grid.burst(origin,2))],'until':'scene_end',
            'name':'그래스','effect':deepcopy(definition['effect']),'action':'shift',
            'frequency':deepcopy(definition['frequency']),'ended':False}
        receipt['seal'] = _local_seal(receipt)
        state['receipts'][request_id] = receipt
        setattr(staged,LOCAL_KEY,state)
        validate_local(staged)
        return deepcopy(receipt)
    return GRANTS.transition(engine,actor,apply,include_grid=True)


def local_scene_end(engine):
    for row in validate_local(engine):
        row['ended'] = True
        row['seal'] = _local_seal(row)
    refresh_local_weather(engine)


def terrain_for(engine, actor, name=None, *, include_virtual=True):
    """Read activation conditions, or only actual local/global Terrain effects."""
    import csv_item_physical_contracts as CSV_ITEMS
    virtual = CSV_ITEMS.effective_terrain(engine, actor) if include_virtual else None
    if virtual is not None:
        fields = [row for row in policy(engine.r)['moves'].values()
                  if row['field'] == virtual]
        if not fields:
            raise ValueError('Booster Energy Terrain lacks its selected native field payload')
        field = fields[0]
        return {'name': virtual, 'effect': deepcopy(field['effect']), 'source_id': 'item/부스트에너지'} if name is None or virtual == name else None
    rows = [row for row in validate_local(engine) if row['source_id']==LOCAL_SOURCE]
    selected = None
    if rows and getattr(actor,'on_field',True):
        import body_state as BODY
        occupied = BODY.cells(actor,require_complete=True)
        matches = [row for row in rows if occupied.intersection(tuple(p) for p in row['cells'])]
        if matches:
            # The closed producer supports only identical Grass payloads.
            # No order-dependent choice is made between distinct fields.
            if any((r['name'],r['effect']) != (matches[0]['name'],matches[0]['effect']) for r in matches):
                raise ValueError('unresolved local Terrain source conflict')
            selected = matches[0]
    if selected is None:
        selected = active(engine)
    if selected is None or selected['name'] not in ('그래스','미스트','일렉트릭','사이코') or name is not None and selected['name'] != name:
        return None
    return selected


def _policy_path(rules):
    canonical = os.path.join(rules.root, "data", "field-effect-policy.json")
    staged = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "field-effect-policy.json"))
    return canonical if os.path.exists(canonical) else staged


def policy(rules):
    path = _policy_path(rules)
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if value.get("schema_version") != 1 or not isinstance(value.get("moves"), dict):
        raise ValueError("global Terrain policy schema changed")
    return value


def _semantic(effect):
    return {key: deepcopy(value) for key, value in effect.items() if key != "_src"}


def prepare(engine, effect, source_id):
    """Validate the complete selected producer before action/frequency spend."""
    validate(engine)
    if not isinstance(effect, dict) or effect.get("type") != "field_effect":
        raise ValueError("field effect producer requires one typed effect")
    rounds = effect.get("rounds", 5)
    if type(rounds) is not int or rounds <= 0:
        raise ValueError("field duration must be a positive integer")
    if not isinstance(effect.get("field"), str) or not isinstance(effect.get("effect"), dict):
        raise ValueError("field effect requires its name and typed payload")
    row = policy(engine.r)["moves"].get(source_id)
    if row is None:
        # Preserve existing behavior for sources outside this reviewed bundle.
        return {"reviewed": False, "effect": _semantic(effect)}
    expected = {
        "type": "field_effect",
        "field": row["field"],
        "rounds": row["rounds"],
        "effect": row["effect"],
    }
    if _semantic(effect) != expected:
        raise ValueError("selected global Terrain effect differs from reviewed source policy")
    return {"reviewed": True, "row": deepcopy(row), "effect": expected}


def install(engine, actor, effect, source_id):
    plan = prepare(engine, effect, source_id)
    if not plan["reviewed"]:
        state = {
            "name": effect["field"], "rounds": effect.get("rounds", 5),
            "effect": deepcopy(effect["effect"]),
        }
        _store(engine, state)
        import items as ITEMS
        ITEMS.synchronize_field_suppression(engine)
        engine.log(f"    전장 효과: {effect['field']} ({effect.get('rounds', 5)}라운드)")
        return state
    row = plan["row"]
    actor_id = getattr(actor, "entity_id", None)
    if not isinstance(actor_id, str) or not actor_id:
        raise ValueError("global Terrain requires its actual creating actor")
    duration_source = None
    rounds = row["rounds"]
    if row.get("duration_item") == "terrain_extender":
        import static_equipment_contracts as STATIC_EQUIPMENT
        rounds,duration_source=STATIC_EQUIPMENT.terrain_duration_source(engine,actor,row["rounds"])
    state = {
        "kind": KIND,
        "name": row["field"],
        "source_id": source_id,
        "clause_id": row["clause_id"],
        "source_row_sha256": row["source_row_sha256"],
        "creator_id": actor_id,
        "rounds": rounds,
        "installed_round": engine.round_no,
        "last_tick_round": engine.round_no,
        "activation_round": engine.round_no + int(bool(row.get("activate_next_round"))),
        "effect": deepcopy(row["effect"]),
    }
    if row["effect"].get("airborne_move_scope") == "enemies":
        if not isinstance(actor.side, str) or not actor.side:
            raise ValueError("enemy-only field requires actual creator side")
        state["creator_side"] = actor.side
    if duration_source is not None:state["duration_source"]=duration_source
    validate(engine, state)
    _store(engine, state)
    import items as ITEMS
    ITEMS.synchronize_field_suppression(engine)
    engine.log(f"    전장 효과: {row['field']} ({row['rounds']}라운드)", source_id)
    return state


def _validate_state(engine, state):
    if state is None:
        return None
    if not isinstance(state, dict):
        raise ValueError("global field state must be a dictionary")
    if state.get("kind") != KIND:
        return None
    required = {"kind", "name", "source_id", "clause_id", "source_row_sha256", "creator_id",
                "rounds", "installed_round", "last_tick_round", "activation_round", "effect"}
    if not isinstance(state.get("source_id"), str):
        raise ValueError("global Terrain source identity changed")
    row = policy(engine.r)["moves"].get(state["source_id"])
    if row is None:
        raise ValueError("global Terrain source is not reviewed")
    if row["effect"].get("airborne_move_scope") == "enemies":
        required.add("creator_side")
        if not isinstance(state.get("creator_side"), str) or not state["creator_side"]:
            raise ValueError("enemy-only field creator side is missing")
    if set(state) not in (required, required | {"duration_source"}):
        raise ValueError("global Terrain state shape changed")
    expected = (row["field"], row["clause_id"], row["source_row_sha256"], row["effect"])
    actual = (state["name"], state["clause_id"], state["source_row_sha256"], state["effect"])
    if actual != expected:
        raise ValueError("global Terrain provenance or payload changed")
    maximum=row["rounds"]
    if "duration_source" in state:
        if row.get("duration_item") != "terrain_extender":
            raise ValueError("this global field cannot use a Terrain Extender")
        import static_equipment_contracts as STATIC_EQUIPMENT
        maximum=STATIC_EQUIPMENT.validate_terrain_duration(engine,state["duration_source"],row["rounds"])
    if type(state["rounds"]) is not int or not 1 <= state["rounds"] <= maximum:
        raise ValueError("global Terrain remaining lifetime changed")
    for key in ("installed_round", "last_tick_round"):
        if type(state[key]) is not int or state[key] < 0:
            raise ValueError("global Terrain round receipt changed")
    if state["last_tick_round"] < state["installed_round"] or state["last_tick_round"] > engine.round_no:
        raise ValueError("global Terrain tick receipt is outside the combat clock")
    expected_activation = state["installed_round"] + int(bool(row.get("activate_next_round")))
    if state["activation_round"] != expected_activation:
        raise ValueError("global field activation round changed")
    if not isinstance(state["creator_id"], str) or not state["creator_id"]:
        raise ValueError("global Terrain creator identity changed")
    if getattr(engine, "everyone", None):
        import world_entities as WORLD
        if state["creator_id"] not in WORLD.actor_index(engine):
            raise ValueError("global Terrain creator is missing from the restored world")
    return state


def _states(engine):
    primary = _validate_state(engine, engine.field)
    independent = getattr(engine, INDEPENDENT_KEY, {})
    if not isinstance(independent, dict):
        raise ValueError("independent fields must be a source mapping")
    rows = [] if primary is None else [primary]
    for source_id, state in independent.items():
        if (source_id not in INDEPENDENT_SOURCES or not isinstance(state, dict)
                or state.get("source_id") != source_id or state.get("kind") != KIND):
            raise ValueError("independent field slot differs from its reviewed source")
        if primary is not None and primary["source_id"] == source_id:
            raise ValueError("duplicate independent field source")
        rows.append(_validate_state(engine, state))
    return rows


def validate(engine, state=None):
    if state is not None:
        return _validate_state(engine, state)
    _states(engine)
    return _validate_state(engine, engine.field)


def _store(engine, state):
    # Historical saves kept a Room/Gravity in the terrain slot; retain it.
    previous = _validate_state(engine, engine.field)
    independent = getattr(engine, INDEPENDENT_KEY, {})
    if previous is not None and previous["source_id"] in INDEPENDENT_SOURCES:
        independent[previous["source_id"]] = previous
        engine.field = None
    if state.get("source_id") in INDEPENDENT_SOURCES:
        independent[state["source_id"]] = state
    else:
        engine.field = state
    if independent or hasattr(engine, INDEPENDENT_KEY):
        setattr(engine, INDEPENDENT_KEY, independent)


def clear(engine, *, terrain_only=False):
    validate(engine)
    primary = _validate_state(engine, engine.field)
    if not terrain_only or primary is None or primary["source_id"] not in INDEPENDENT_SOURCES:
        engine.field = None
    if not terrain_only and hasattr(engine, INDEPENDENT_KEY):
        setattr(engine, INDEPENDENT_KEY, {})
    import items as ITEMS
    ITEMS.synchronize_field_suppression(engine)


def clear_terrain_at(engine,cells):
    """End actual contacted Terrain occurrences without ending Rooms or local weather."""
    occupied=set(cells);ended=[]
    primary=_validate_state(engine,engine.field)
    if primary is not None and primary['source_id'] not in INDEPENDENT_SOURCES:
        ended.append(primary['source_id']);clear(engine,terrain_only=True)
    for row in validate_local(engine):
        if row['source_id']==LOCAL_SOURCE and occupied.intersection(tuple(p) for p in row['cells']):
            row['ended']=True;row['seal']=_local_seal(row);ended.append(row['request_id'])
    return ended


def active_fields(engine, name=None):
    return [state for state in _states(engine)
            if engine.round_no >= state["activation_round"]
            and (name is None or state["name"] == name)]


def active(engine, name=None):
    rows = active_fields(engine, name)
    if name is None:
        return next((state for state in rows if state is engine.field), None)
    return next(iter(rows), None)


def round_started(engine):
    for state in _states(engine):
        if state["last_tick_round"] == engine.round_no or engine.round_no < state["activation_round"]:
            continue
        state["last_tick_round"] = engine.round_no
        # Delayed Trick Room starts with five complete active rounds.
        if engine.round_no == state["activation_round"] and state["activation_round"] > state["installed_round"]:
            continue
        state["rounds"] -= 1
        if state["rounds"] <= 0:
            engine.log(f"  전장 효과 {state['name']} 종료", state["source_id"])
            if state is engine.field:
                engine.field = None
            else:
                getattr(engine, INDEPENDENT_KEY).pop(state["source_id"])
    import items as ITEMS
    ITEMS.synchronize_field_suppression(engine)
    return validate(engine)


def accuracy_modifier(engine, actor):
    return sum(state["effect"]["accuracy_roll_bonus"] for state in active_fields(engine, "왜곡"))


def defense_stat(engine, actor, stat):
    """Project Wonder Room at the native defense/evasion read boundary."""
    state = active(engine, "원더")
    if state is None or actor.kind != "pokemon" or not state["effect"].get("swap_defense_stats"):
        return stat
    return {"def": "spd", "spd": "def"}.get(stat, stat)


def evasion_class(engine, actor, move_class):
    state = active(engine, "원더")
    if state is None or actor.kind != "pokemon" or not state["effect"].get("swap_defense_stats"):
        return move_class
    return {"물리": "특수", "특수": "물리", "Physical": "Special", "Special": "Physical"}.get(move_class, move_class)


def initiative_ascending(engine, round_no=None):
    at = engine.round_no if round_no is None else round_no
    return any(state["name"] == "트릭룸" and at >= state["activation_round"]
               and state["effect"].get("initiative_order") == "ascending"
               for state in _states(engine))


def validate_aerial_height(engine, actor, altitude):
    if (actor.kind == "pokemon" and any(
            altitude > state["effect"]["max_sky_or_levitate_end_height"]
            for state in active_fields(engine, "왜곡"))):
        raise ValueError("Gravity prevents Pokemon from ending above 1 metre")


def preflight_end_turn(engine, actor):
    if not active_fields(engine, "왜곡") or actor.kind != "pokemon":
        return
    altitude = actor.spec.get("_movement_altitude", 0)
    if type(altitude) not in (int, float):
        raise ValueError("movement altitude must be numeric")
    validate_aerial_height(engine, actor, altitude)


def suppresses_ground_immunity(engine, target, source=None):
    if not active_fields(engine, "왜곡") or target.kind != "pokemon":
        return False
    if "비행" in target.types or "Flying" in target.types:
        return True
    ability = str((source or {}).get("_ability", ""))
    return ability in ("부유", "Levitate")


def passive_equipment_suppressed(engine, actor, registration=None):
    state = active(engine, "신비")
    if state is None:
        return False
    if actor.kind == "pokemon":
        return registration is None or registration.get("held_slot") is not None
    if actor.kind == "trainer":
        return registration is None or "장신구" in registration.get("slots", ())
    return False


def touches_ground(actor):
    if not getattr(actor, "on_field", True):
        return False
    spec = getattr(actor, "spec", {})
    altitude = spec.get("_movement_altitude", 0)
    burrow = spec.get("_burrow") or {}
    if type(altitude) not in (int, float):
        raise ValueError("movement altitude must be numeric")
    if not isinstance(burrow, dict):
        raise ValueError("burrow state must be a dictionary")
    return altitude == 0 and not burrow.get("underground", False) and not getattr(actor, "airborne", False)


def status_immunity(engine, actor, condition):
    if not touches_ground(actor):
        return None
    state = terrain_for(engine, actor, include_virtual=False)
    if state is None:
        return None
    if state["name"] == "일렉트릭" and condition in state["effect"].get("grounded_immune", ()):
        return state["source_id"]
    if (state["name"] == "미스트" and state["effect"].get("grounded_immune_persistent")
            and engine.r.condition_class(condition) == "persistent"):
        return state["source_id"]
    return None


def _pending(actor):
    rows = actor.custom_conditions.get(DEFERRED, [])
    if not isinstance(rows, list):
        raise ValueError("Misty deferred statuses must be a list")
    return rows


def defer_status(engine, actor, condition, *, source=None, parameters=None, applied_by=None):
    """Delay a volatile status until the recipient has ignored one whole turn."""
    state = terrain_for(engine, actor, "미스트", include_virtual=False)
    if state is None or not touches_ground(actor) or engine.r.condition_class(condition) != "volatile":
        return None
    rows = _pending(actor)
    if condition in actor.conditions or any(row.get("condition") == condition for row in rows):
        engine.log(f"    {actor.name}은(는) 이미 {condition} 상태 또는 미스트 지연 중")
        return False
    try:
        frozen_parameters = json.loads(json.dumps(parameters, ensure_ascii=False)) if parameters is not None else None
    except (TypeError, ValueError) as exc:
        raise ValueError("Misty deferred status parameters must be JSON-safe") from exc
    applied_by_id = getattr(applied_by, "entity_id", None) if applied_by is not None else None
    if applied_by is not None and (not isinstance(applied_by_id, str) or not applied_by_id):
        raise ValueError("Misty deferred status needs the actual applying actor")
    engine.time_actors([actor, *([applied_by] if applied_by is not None else [])])
    row = {
        "condition": condition,
        "source": source,
        "parameters": frozen_parameters,
        "applied_by_id": applied_by_id,
        "created_round": engine.round_no,
        "activate_after_turn": actor.turns_taken + 1,
        "terrain_source_id": state["source_id"],
        "terrain_source_row_sha256": state["source_row_sha256"],
    }
    rows.append(row)
    actor.custom_conditions[DEFERRED] = rows
    engine.log(f"    {actor.name}: 미스트필드로 {condition} 첫 턴 무시", state["source_id"])
    return True


def _validate_pending(engine, actor, row):
    required = {"condition", "source", "parameters", "applied_by_id", "created_round",
                "activate_after_turn", "terrain_source_id", "terrain_source_row_sha256"}
    if not isinstance(row, dict) or set(row) not in (required, required | {'dream_mist'}):
        raise ValueError("Misty deferred status receipt changed")
    policy_row = policy(engine.r)["moves"].get(row["terrain_source_id"])
    if policy_row is None or policy_row["field"] != "미스트" or policy_row["source_row_sha256"] != row["terrain_source_row_sha256"]:
        raise ValueError("Misty deferred status provenance changed")
    if engine.r.condition_class(row["condition"]) != "volatile":
        raise ValueError("only volatile status can use the Misty first-turn delay")
    if type(row["created_round"]) is not int or type(row["activate_after_turn"]) is not int:
        raise ValueError("Misty deferred status clock changed")
    if row["activate_after_turn"] < 1 or row["activate_after_turn"] > actor.turns_taken + 1:
        raise ValueError("Misty deferred status turn receipt changed")
    import dream_state as DREAM
    DREAM.validate_deferred(engine, actor, row)
    return row


def validate_pending_world(engine, index):
    import consumption_execution as EXECUTION
    originals = set()
    for actor in index.values():
        for row in _pending(actor):
            if not isinstance(row,dict) or 'dream_mist' not in row:continue
            _validate_pending(engine, actor, row)
            proof = row.get('dream_mist')
            if proof is not None:
                key = (proof['payer_id'], proof['stock_receipt_id'])
                if key in originals:raise ValueError('Dream Mist payment cannot own two deferred statuses')
                originals.add(key)
    for actor in index.values():
        for receipt in EXECUTION.validate(actor).values():
            if receipt['outcome']=='deferred' and any(r.get('kind')=='dream_deferred_sleep' for r in receipt['results']):
                if (actor.entity_id,receipt['receipt_id']) not in originals:
                    raise ValueError('deferred Dream Mist payment lost its native field status')


def end_turn(engine, actor):
    rows = list(_pending(actor))
    if not rows:
        return []
    remaining, due, activated = [], [], []
    import world_entities as WORLD
    index = WORLD.actor_index(engine)
    for row in rows:
        _validate_pending(engine, actor, row)
        if actor.turns_taken < row["activate_after_turn"]:
            remaining.append(row)
        else:
            due.append(row)
    # Keep paid delayed applications addressable through nested status transactions.
    retained = remaining + [row for row in due if 'dream_mist' in row]
    if retained:
        actor.custom_conditions[DEFERRED] = retained
    else:
        actor.custom_conditions.pop(DEFERRED, None)
    for row in due:
        applier = None if row["applied_by_id"] is None else index.get(row["applied_by_id"])
        if row["applied_by_id"] is not None and applier is None:
            raise ValueError("Misty deferred status applying actor is missing")
        import dream_state as DREAM
        serial_before = actor.spec.get(DREAM.KEY, {}).get('serial', 0)
        result = engine.apply_status(actor, row["condition"], source=row["source"],
            parameters=row["parameters"], applied_by=applier, _field_deferred=True)
        DREAM.finish_deferred(engine, actor, row, applied=bool(result), serial_before=serial_before)
        import eldritch_magic as ELDRITCH
        ELDRITCH.resume_deferred(engine, actor, row)
        activated.append({"condition": row["condition"], "applied": bool(result)})
    return activated


def cancel_deferred_status(engine, actor, condition):
    rows = _pending(actor)
    kept = [row for row in rows if row.get("condition") != condition]
    if len(kept) == len(rows):
        return False
    import eldritch_magic as ELDRITCH
    for row in rows:
        if row.get("condition") == condition:
            ELDRITCH.cancel_deferred(engine, actor, row)
            import dream_state as DREAM
            DREAM.finish_deferred(engine, actor, row)
    if kept:
        actor.custom_conditions[DEFERRED] = kept
    else:
        actor.custom_conditions.pop(DEFERRED, None)
    engine.log(f"    {actor.name}의 미스트 지연 {condition} 치료됨", "move/미스트필드")
    return True


def turn_start(engine, actor):
    state = terrain_for(engine, actor, "그래스", include_virtual=False)
    if state is None or not touches_ground(actor) or getattr(actor, "hp", 0) <= 0:
        return 0
    amount = max(0, actor.base_max_hp // 10)
    if amount:
        engine.heal(actor, amount, source_kind="move")
        engine.log(f"    {actor.name}: 그래스필드 회복 {amount}", state["source_id"])
    return amount


def damage_roll_modifier(engine, attacker, target, move, actual_type):
    state = terrain_for(engine, attacker, include_virtual=False)
    target_state = terrain_for(engine, target, include_virtual=False)
    effect = state["effect"] if state else {}
    name = state['name'] if state else None
    modifier = 0
    if name == "일렉트릭" and actual_type == "전기" and touches_ground(attacker):
        modifier += effect["grounded_electric_damage_bonus"]
    elif name == "그래스" and actual_type == "풀" and touches_ground(attacker):
        modifier += effect["grounded_grass_damage_bonus"]
    elif (name == "사이코" and actual_type == "에스퍼"
          and attacker.kind == "pokemon" and touches_ground(attacker)):
        modifier += effect["grounded_psychic_damage_bonus"]
    elif actual_type == "드래곤":
        mist = [s for s,a in ((state,attacker),(target_state,target)) if s is not None and s['name']=='미스트' and touches_ground(a)]
        if mist:
            state = mist[0]
            modifier += state['effect']["dragon_vs_grounded_damage_roll"]
    if modifier:
        engine.log(f"    {state['name']}필드: {actual_type} 피해 굴림 {modifier:+d}", state["source_id"])
    return modifier


def airborne_move_fields(engine, actor=None):
    """Side limits apply to airborne Move bans, not height or Ground immunity."""
    rows = []
    for gravity in active_fields(engine, "왜곡"):
        if gravity["effect"].get("airborne_move_scope") == "enemies":
            if actor is None:
                raise ValueError("enemy-only field Move check requires its actual actor")
            if actor.side == gravity["creator_side"]:
                continue
        rows.append(gravity)
    return rows


def native_move_block_reason(engine, move_id, actor=None):
    """Return a global field source that rejects this Move before activation."""
    if actor is not None:
        terrain_for(engine,actor,include_virtual=False)
    for gravity in airborne_move_fields(engine, actor):
        if move_id in gravity["effect"].get("blocked_airborne_moves", ()):
            return gravity["source_id"]
    return None


def move_block_reason(engine, attacker, target, move, mech, *, targetless=False):
    global_block = native_move_block_reason(engine, move.get("id"), attacker)
    if global_block is not None:
        return global_block
    if targetless:
        return None
    state = terrain_for(engine, target, "사이코", include_virtual=False)
    if state is None or target.kind != "pokemon" or not touches_ground(target):
        return None
    header = mech.get("header") or {}
    range_info = header.get("range") or {}
    raw = " ".join((str(move.get("range", "")), str(range_info.get("raw", ""))))
    targets = range_info.get("targets")
    single_target = targets == 1 or targets is None and "대상 1" in raw
    if not single_target or range_info.get("shape"):
        return None
    keywords = set(header.get("keywords") or ()) | set(move.get("keywords") or ())
    import turn as TURN
    if TURN.has_priority(engine, attacker, move) or "방해" in keywords or "방해" in raw:
        return state["source_id"]
    return None

