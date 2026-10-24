"""Adopted Nicolette gym sample: observed map, deployment and terrain hooks."""
from copy import deepcopy

import common_checks as C
import state_grants as GRANTS
import world_entities as WORLD


SOURCE = "input/ch11-running-the-game.md:2034-2038,2153-2154"
TRAINING_SOURCE = "ch11/nicolette-gym-special-training"
KEY = "nicolette_gym"
ICE_TYPES = frozenset(("얼음", "Ice"))
AP_KEY = 'nicolette_gym_ap'
AP_SOURCE = 'ch11-running-the-game/빠른-포켓몬-스탯분배/니콜렛의-포켓몬'
AP_REFERENCE = {'file': 'input/ch11-running-the-game.md',
                'sha256': '5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad'}
CLIMATE_SOURCE='ch04-trainer-classes/프로페셔널-클래스/연구원-연구-분야'
CLIMATE_REFERENCE={'file':'input/ch04-trainer-classes.md',
 'sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'}


def configure_weather(engine,nicolette,*,gm_id,reason,winter):
    """Adopt the printed winter mountain; this observes no Feature/AP payment."""
    import weather_state as W,homebrew_weather as HOME
    WORLD.require_actors(engine,nicolette);_ap_source(engine.r)
    if nicolette.kind!='trainer' or winter is not True:raise ValueError('actual adopted winter Nicolette Trainer required')
    if HOME.enabled(engine.r):raise ValueError('core mountain weather requires core weather semantics')
    _text(gm_id,'GM identity');_text(reason,'GM winter weather observation reason')
    if 'nicolette' in getattr(engine,W.KEY,{}):raise ValueError('mountain weather has already been adopted')
    def apply(e,c):
        record=W.set_weather(e,'hail',rounds=None,source_id=AP_SOURCE,origin='encounter',actor=c,reason=reason)
        value=W.state(e)
        value.update(layers=[],nicolette=dict(source=AP_SOURCE,reference=deepcopy(AP_REFERENCE),
            trainer_id=c.entity_id,gm_id=gm_id,reason=reason,winter=True,hail_id=record['id'],
            rudolf_id=None,ground_weather_ball=False,suppression=None,cloud_nine={}))
        e.gm._rec('Nicolette winter weather observation',None,value['nicolette'],reason,c)
        return deepcopy(record)
    return GRANTS.transition(engine,nicolette,apply,include_rulings=True)


def configure_rudolf(engine,actor,*,gm_id,reason,ground_weather_ball=False):
    """Identify the actual sample individual explicitly; names never confer it."""
    import weather_state as W,ability_transitions as A
    WORLD.require_actors(engine,actor);value=W.state(engine);sample=value.get('nicolette')
    if (sample is None or actor.kind!='pokemon' or actor.spec.get('species')!='pokemon/캐스퐁'
            or actor.spec.get('trainer_id')!=sample['trainer_id'] or gm_id!=sample['gm_id']):
        raise ValueError('actual adopted Nicolette-owned Castform required')
    if 'ability/기분파' not in A.known(actor):raise ValueError('sample Rudolf requires its actual Forecast ability')
    if type(ground_weather_ball) is not bool:raise ValueError('explicit Ground Weather Ball option required')
    _text(reason,'GM Rudolf observation reason')
    if sample['rudolf_id'] not in (None,actor.entity_id):raise ValueError('sample Rudolf identity is already bound')
    def apply(e,c):
        row=getattr(e,W.KEY)['nicolette'];row['rudolf_id']=c.entity_id;row['ground_weather_ball']=ground_weather_ball
        __import__('ability_state_projection').weather_changed(e)
        e.gm._rec('Nicolette Rudolf observation',None,dict(actor_id=c.entity_id,ground_weather_ball=ground_weather_ball),reason,c)
        return deepcopy(row)
    return GRANTS.transition(engine,actor,apply,include_rulings=True)


def use_climate_control(engine,nicolette,producer,*,gm_id,reason):
    """Compose the explicitly observed Feature selection with a native Move.

    This adopts the sampled state outcome. Feature acquisition and AP payment
    remain the external script/GM's separate procedure; the ordinary native
    Sandstorm retains its actual Standard, frequency, producer and deadline.
    """
    import weather_state as W
    WORLD.require_actors(engine,nicolette,producer);value=W.state(engine);sample=value.get('nicolette')
    if (sample is None or nicolette.entity_id!=sample['trainer_id'] or gm_id!=sample['gm_id']
            or producer.kind!='pokemon' or producer.spec.get('trainer_id')!=nicolette.entity_id):
        raise ValueError('actual adopted Nicolette and her weather producer required')
    selected=engine.r.select_source_definition(CLIMATE_SOURCE,source=CLIMATE_REFERENCE)
    if selected['selected_id']!=CLIMATE_SOURCE:raise ValueError('selected Climate Control source required')
    _text(reason,'GM completed Climate Control observation reason')
    if not W.sample_hail_live(engine):raise ValueError('actual live permanent mountain hail required')
    if getattr(engine,'_nicolette_climate_control_scope',None) is not None:raise ValueError('nested Climate Control selection')
    def apply(e,c,p):
        before=getattr(e,W.KEY)['sequence']
        e._nicolette_climate_control_scope={'trainer':c,'producer':p,'gm_id':gm_id,'reason':reason,
            'source':CLIMATE_SOURCE,'reference':deepcopy(CLIMATE_REFERENCE),'hail_id':sample['hail_id']}
        try:e.use_move(p,p,'move/모래바람')
        finally:vars(e).pop('_nicolette_climate_control_scope',None)
        state=getattr(e,W.KEY)
        if state['sequence']==before or not state['layers']:raise ValueError('Climate Control needs the successful actual native Sandstorm')
        storm=state['layers'][-1]
        e.gm._rec('Nicolette Climate Control state outcome',None,storm['climate_control'],reason,c)
        return deepcopy(storm)
    return GRANTS.transition(engine,nicolette,apply,participants=(producer,),include_rulings=True)


def climate_scope(engine,weather,source_id,origin,actor):
    scope=getattr(engine,'_nicolette_climate_control_scope',None)
    if scope is None:return None
    import weather_state as W
    sample=getattr(engine,W.KEY,{}).get('nicolette',{})
    if (weather!='sandstorm' or source_id!='move/모래바람' or origin!='move'
            or actor is not scope.get('producer') or scope.get('source')!=CLIMATE_SOURCE
            or scope.get('reference')!=CLIMATE_REFERENCE or not W.sample_hail_live(engine)
            or scope['hail_id']!=sample['hail_id'] or scope['trainer'].entity_id!=sample['trainer_id']
            or actor.spec.get('trainer_id')!=sample['trainer_id'] or scope['gm_id']!=sample['gm_id']):
        raise ValueError('Climate Control must bind its actual adopted source and native weather producer')
    return scope


def observe_weather_negation(engine,actor,*,source_id,gm_id,reason):
    """Observe a completed Cloud Nine outcome at the existing GM/script boundary."""
    import weather_state as W,ability_transitions as A
    WORLD.require_actors(engine,actor);sample=W.state(engine).get('nicolette')
    if (sample is None or gm_id!=sample['gm_id'] or source_id!='ability/날씨부정'
            or not actor.on_field or actor.fainted or source_id not in A.known(actor) or not A.active(actor,source_id)):
        raise ValueError('actual active Cloud Nine owner and adopted GM observation required')
    _text(reason,'GM completed Cloud Nine observation reason')
    if not W.sample_hail_live(engine):raise ValueError('live permanent mountain hail required')
    import resolution_transaction as TX
    prior=TX.replay_result(sample['cloud_nine'],actor.entity_id,cloud_nine_intent(sample,actor.entity_id),fingerprint_field='intent_fingerprint')
    if prior is not None:return prior['suppression']
    def apply(e,c):
        result=W.suppress_sample(e,source_id=source_id,reason=reason,actor=c,gm_id=gm_id)
        if not result:raise ValueError('live permanent mountain hail required')
        e.gm._rec('Nicolette completed Cloud Nine observation',None,source_id,reason,c)
        return deepcopy(getattr(e,W.KEY)['nicolette']['cloud_nine'][c.entity_id]['suppression'])
    return GRANTS.transition(engine,actor,apply,include_rulings=True)


def cloud_nine_intent(sample,actor_id):
    return dict(source_id='ability/날씨부정',actor_id=actor_id,hail_id=sample['hail_id'],
        trainer_id=sample['trainer_id'],gm_id=sample['gm_id'],sample_source=AP_SOURCE,reference=deepcopy(AP_REFERENCE))


def validate_weather(engine,value,*,index=None):
    """Validate the optional sample inside the existing weather owner."""
    _ap_source(engine.r);sample=value['nicolette']
    keys={'source','reference','trainer_id','gm_id','reason','winter','hail_id','rudolf_id','ground_weather_ball','suppression','cloud_nine'}
    if type(sample) is not dict or set(sample)!=keys or sample['source']!=AP_SOURCE or sample['reference']!=AP_REFERENCE or sample['winter'] is not True:
        raise ValueError('adopted mountain source changed')
    _text(sample['gm_id'],'sample GM identity');_text(sample['reason'],'winter weather observation reason')
    index=WORLD.actor_index(engine) if index is None else index
    trainer=index.get(sample['trainer_id'])
    if trainer is None or trainer.kind!='trainer':raise ValueError('actual mountain Trainer identity required')
    records=value['history']+([value['active']] if value['active'] else [])+value['layers']
    hail=next((r for r in records if r['id']==sample['hail_id']),None)
    if (hail is None or hail['source_id']!=AP_SOURCE or hail['actor_id']!=trainer.entity_id
            or hail['weather']!='hail' or hail['duration'] is not None or hail['origin']!='encounter'):
        raise ValueError('permanent mountain hail differs from its original occurrence')
    if type(sample['hail_id']) is not int or type(sample['ground_weather_ball']) is not bool:raise ValueError('invalid sample weather identity/option')
    if sample['rudolf_id'] is not None:
        actor=index.get(sample['rudolf_id'])
        if actor is None or actor.kind!='pokemon' or actor.spec.get('species')!='pokemon/캐스퐁' or actor.spec.get('trainer_id')!=trainer.entity_id:
            raise ValueError('sample Rudolf individual identity changed')
    if len(value['layers'])>1 or value['layers'] and value['active'] is not hail:raise ValueError('sample layering requires the original live hail')
    for layer in records:
        if 'climate_control' not in layer:
            if layer in value['layers']:raise ValueError('sample layer requires its source observation')
            continue
        fact=layer.get('climate_control')
        producer=index.get(layer.get('actor_id'))
        if (layer['weather']!='sandstorm' or layer['source_id']!='move/모래바람' or layer['origin']!='move'
                or producer is None or producer.kind!='pokemon' or producer.spec.get('trainer_id')!=trainer.entity_id
                or type(fact) is not dict or set(fact)!={'source','reference','trainer_id','producer_id','hail_id','occurrence_id','gm_id','reason'}
                or fact['source']!=CLIMATE_SOURCE or fact['reference']!=CLIMATE_REFERENCE
                or fact['trainer_id']!=trainer.entity_id or fact['producer_id']!=layer['actor_id']
                or fact['hail_id']!=hail['id'] or fact['occurrence_id']!=layer['id'] or fact['gm_id']!=sample['gm_id']):
            raise ValueError('sample Sandstorm lacks its actual Climate Control outcome')
        _text(fact['reason'],'completed Climate Control reason')
        selected=engine.r.select_source_definition(CLIMATE_SOURCE,source=CLIMATE_REFERENCE)
        if selected['selected_id']!=CLIMATE_SOURCE:raise ValueError('selected Climate Control source changed')
    import resolution_transaction as TX
    if type(sample['cloud_nine']) is not dict:raise ValueError('sample completed Cloud Nine observations required')
    for actor_id,receipt in sample['cloud_nine'].items():
        if type(receipt) is not dict or set(receipt)!={'intent_fingerprint','suppression'}:
            raise ValueError('completed Cloud Nine source observation changed')
        TX.replay_result(sample['cloud_nine'],actor_id,cloud_nine_intent(sample,actor_id),fingerprint_field='intent_fingerprint')
        _validate_suppression(engine,receipt['suppression'],sample,hail,index)
        if receipt['suppression']['source_id']!='ability/날씨부정' or receipt['suppression']['actor_id']!=actor_id:
            raise ValueError('completed Cloud Nine observation actor/source changed')
    suppression=sample['suppression']
    if suppression is not None:
        if value['active'] is not hail:raise ValueError('active sample negation requires its original live Hail')
        _validate_suppression(engine,suppression,sample,hail,index)
        if suppression['source_id']=='ability/날씨부정' and sample['cloud_nine'].get(suppression['actor_id'],{}).get('suppression') is not suppression:
            raise ValueError('active Cloud Nine differs from its completed source observation')


def _validate_suppression(engine,suppression,sample,hail,index):
    if (type(suppression) is not dict or set(suppression)!={'source_id','reason','started_round','deadline_round','deadline_count','actor_id','gm_id','hail_id'}
            or suppression['source_id'] not in ('move/안개제거','ability/날씨부정','ability/에어록')
            or type(suppression['started_round']) is not int or not 0<=suppression['started_round']<=engine.round_no
            or suppression['deadline_round']!=suppression['started_round']+2
            or suppression['deadline_count'] is not None and type(suppression['deadline_count']) is not int
            or type(suppression['hail_id']) is not int or suppression['hail_id']!=hail['id']):
        raise ValueError('sample negation must retain its exact two-round boundary')
    if suppression['source_id']=='ability/날씨부정':
        if index.get(suppression['actor_id']) is None or suppression['gm_id']!=sample['gm_id']:
            raise ValueError('completed Cloud Nine observation lost its actual source actor or GM authority')
    elif suppression['actor_id'] is not None or suppression['gm_id'] is not None:
        raise ValueError('native weather negation cannot acquire external observation authority')
    _text(suppression['reason'],'actual weather-negation reason')


def _ap_source(rules):
    selected=rules.select_source_definition(AP_SOURCE,source=AP_REFERENCE)
    if selected['selected_id']!=AP_SOURCE:
        raise ValueError('selected Nicolette AP sample requires its own adapter')
    if rules.rulings.mech.get(AP_SOURCE) or rules.rulings.effects.get(AP_SOURCE):
        raise ValueError('overridden Nicolette AP sample requires its own adapter')


def ap_policy(actor):
    """Read this actor's adopted AP-only sample; it has no encounter expiry."""
    if AP_KEY not in actor.spec:return None
    row=actor.spec[AP_KEY]
    _ap_source(actor.r)
    if (actor.kind!='trainer' or actor.spec.get('id')!=actor.entity_id
            or type(row) is not dict or set(row)!={'actor_id','source','reference',
                'ap_level','bonus_ap','gm_id','reason'}
            or row['actor_id']!=actor.entity_id or row['source']!=AP_SOURCE
            or row['reference']!=AP_REFERENCE):
        raise ValueError('actual Nicolette AP sample adoption required')
    C.integer(row['ap_level'],'Nicolette AP-only Trainer level',40)
    C.integer(row['bonus_ap'],'explicit GM bonus AP',0)
    _text(row['gm_id'],'GM identity');_text(row['reason'],'GM sample adoption reason')
    return deepcopy(row)


def configure_ap(engine,nicolette,*,gm_id,reason,ap_level=40,bonus_ap=0):
    """Adopt ch11:2147 on one actual actor, without changing its real level.

    The AP-only level is a floor; a higher actual level remains effective. A
    replacement edits that same maximum and never resets usage or reservations.
    """
    WORLD.require_actors(engine,nicolette)
    if nicolette.kind!='trainer':raise ValueError('actual Nicolette Trainer required')
    _ap_source(engine.r)
    C.integer(ap_level,'Nicolette AP-only Trainer level',40)
    C.integer(bonus_ap,'explicit GM bonus AP',0)
    _text(gm_id,'GM identity');_text(reason,'GM sample adoption reason')
    import action_points as AP
    AP.validate(nicolette)
    row=dict(actor_id=nicolette.entity_id,source=AP_SOURCE,reference=deepcopy(AP_REFERENCE),
             ap_level=ap_level,bonus_ap=bonus_ap,gm_id=gm_id,reason=reason)
    def apply(e,a):
        before=deepcopy(a.spec.get(AP_KEY))
        a.spec[AP_KEY]=deepcopy(row)
        bound=a.spec.get('ap_bound',0)
        used=a.spec.get('ap_spent',0)+a.spec.get('ap_removed',0)+(sum(bound.values()) if isinstance(bound,dict) else bound)
        if used>AP.maximum(a):raise ValueError('adopted AP maximum cannot erase existing commitments')
        e.gm._rec('Nicolette AP sample adoption',before,row,reason,a)
        return deepcopy(row)
    return GRANTS.transition(engine,nicolette,apply)


def configure_commands(engine, nicolette, *, pc_trainers, pokemon, gm_id, reason):
    """Adopt this sample's entire-team command exception, without AP/weather."""
    import party_actions as PARTY
    pool=tuple(pokemon);pcs=tuple(pc_trainers)
    gym_count=sum(p.spec.get('trainer_id')==nicolette.entity_id for p in pool)
    if not gym_count:raise ValueError('actual Nicolette team required')
    row=PARTY.configure_gym(engine,nicolette,pc_trainers=pcs,gym_trainers=(),pokemon=pool,
        leader_turn_limit=gym_count,gm_id=gm_id,reason=reason,sample='nicolette')
    return row


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " required")
    return value


def _point(grid, value):
    if not isinstance(value, (tuple, list)) or len(value) != 2 or any(type(v) is not int for v in value):
        raise ValueError("integer map cell required")
    value = tuple(value)
    if not grid.inside(value):
        raise ValueError("scenario cell outside actual map")
    return value


def _key(cell):
    return str(cell[0]) + "," + str(cell[1])


def state(engine, *, required=False):
    row = getattr(engine.grid, KEY, None) if engine.grid is not None else None
    if required and (not isinstance(row, dict) or row.get("source") != SOURCE):
        raise ValueError("adopted Nicolette gym map observation required")
    return row


def configure(engine, *, heights, ladder_links, snow_cells, brush_cells, ice_cells,
              pc_deploy_cells, gym_deploy_cells, nicolette_cell, reason):
    """Observe only the coordinates chosen for this adopted sample map."""
    if engine.grid is None:
        raise ValueError("Nicolette gym requires an actual grid")
    _text(reason, "GM adopted sample-map observation reason")
    grid = engine.grid
    if not isinstance(heights, dict) or not heights:
        raise ValueError("observed height map required")
    observed_heights = {}
    for cell, value in heights.items():
        point = _point(grid, cell)
        C.integer(value, "map height", 0)
        if value % 3:
            raise ValueError("Nicolette sample height levels are 3m increments")
        observed_heights[_key(point)] = value
    links = []
    for pair in ladder_links:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError("ladder link needs two actual cells")
        left, right = (_point(grid, pair[0]), _point(grid, pair[1]))
        if left == right or _key(left) not in observed_heights or _key(right) not in observed_heights:
            raise ValueError("ladder endpoints need distinct observed heights")
        difference = abs(observed_heights[_key(left)] - observed_heights[_key(right)])
        if difference not in (3, 6):
            raise ValueError("sample ladders join observed 3m or 6m height gaps")
        links.append((left, right))
    groups = {}
    for name, values in (("snow", snow_cells), ("brush", brush_cells), ("ice", ice_cells),
                         ("pc_deploy", pc_deploy_cells), ("gym_deploy", gym_deploy_cells)):
        points = tuple(_point(grid, value) for value in values)
        if not points or len(set(points)) != len(points):
            raise ValueError("distinct nonempty " + name + " cells required")
        groups[name] = points
    observer = _point(grid, nicolette_cell)
    if observer in set(groups["pc_deploy"]) | set(groups["gym_deploy"]):
        raise ValueError("Nicolette observer cell is outside both deployment zones")

    import map_terrain as MAP
    import movement_actions as MOVEMENT

    def apply(staged, _):
        MAP.observe(staged, groups["snow"], base="regular", slow=True,
                    reason=reason + ": deep snow")
        MAP.observe(staged, groups["brush"], base="regular", slow=True, rough=True,
                    reason=reason + ": brush")
        # Ice has an explicit walk/fall break transition.  Its ordinary movement
        # exception is observed through the same Tundra Naturewalk consumer.
        MAP.observe(staged, groups["ice"], base="regular", slow=True,
                    reason=reason + ": frozen river")
        MOVEMENT.observe_cell_terrain(staged, groups["snow"], ["툰드라"], reason + ": deep snow")
        MOVEMENT.observe_cell_terrain(staged, groups["ice"], ["툰드라"], reason + ": ice")
        MOVEMENT.observe_cell_terrain(staged, groups["brush"], ["숲"], reason + ": brush")
        row = {
            "source": SOURCE,
            "reason": reason,
            "heights": deepcopy(observed_heights),
            "ladder_links": [[list(a), list(b)] for a, b in links],
            "snow_cells": [list(x) for x in groups["snow"]],
            "brush_cells": [list(x) for x in groups["brush"]],
            "ice_cells": [list(x) for x in groups["ice"]],
            "broken_ice": [],
            "pc_deploy_cells": [list(x) for x in groups["pc_deploy"]],
            "gym_deploy_cells": [list(x) for x in groups["gym_deploy"]],
            "nicolette_cell": list(observer),
            "deployment": None,
        }
        setattr(staged.grid, KEY, row)
        staged.log("  Nicolette gym map observed", SOURCE)
        return deepcopy(row)

    return GRANTS.transition(engine, None, apply, include_grid=True)


def train_team(engine, nicolette, pokemon):
    """Give only this sample team its sourced Tundra and Wallclimber access."""
    values = tuple(pokemon)
    if not values or nicolette.kind != "trainer":
        raise ValueError("Nicolette Trainer and one or more Pokemon required")
    index = WORLD.actor_index(engine, extra=(nicolette, *values))
    if index.get(nicolette.entity_id) is not nicolette:
        raise ValueError("actual registered Nicolette required")
    for actor in values:
        if index.get(actor.entity_id) is not actor or actor.kind != "pokemon" or actor.spec.get("trainer_id") != nicolette.entity_id:
            raise ValueError("actual Nicolette-owned Pokemon required")

    def apply(staged, owner, *targets):
        rows = []
        for target in targets:
            source = TRAINING_SOURCE + ":" + target.entity_id
            GRANTS.grant(target, "capabilities", "자연걸음 (툰드라)", source,
                         "scenario_training", owner_id=owner.entity_id,
                         lifetime="nicolette_gym_team", rule_id=SOURCE)
            GRANTS.grant(target, "capabilities", "벽타기", source,
                         "scenario_training", owner_id=owner.entity_id,
                         lifetime="nicolette_gym_team", rule_id=SOURCE)
            rows.append({"pokemon_id": target.entity_id, "source_id": source,
                         "capabilities": ["자연걸음 (툰드라)", "벽타기"]})
        return rows

    return GRANTS.transition(engine, nicolette, apply, participants=values)


def deploy(engine, *, pcs, gym_pokemon, nicolette, pc_positions, gym_positions, reason):
    """Place both teams and keep Nicolette's observed body outside combat."""
    row = state(engine, required=True)
    _text(reason, "actual gym deployment reason")
    pcs, gym_pokemon = tuple(pcs), tuple(gym_pokemon)
    if not pcs or not gym_pokemon or len(pc_positions) != len(pcs) or len(gym_positions) != len(gym_pokemon):
        raise ValueError("each actual combatant needs one deployment cell")
    actors = (*pcs, *gym_pokemon, nicolette)
    index = WORLD.actor_index(engine, extra=actors)
    if any(index.get(actor.entity_id) is not actor for actor in actors):
        raise ValueError("actual registered gym actors required")
    if len({actor.entity_id for actor in actors}) != len(actors):
        raise ValueError("distinct gym actor identities required")
    pc_zone = {tuple(x) for x in row["pc_deploy_cells"]}
    gym_zone = {tuple(x) for x in row["gym_deploy_cells"]}
    pc_positions = tuple(_point(engine.grid, value) for value in pc_positions)
    gym_positions = tuple(_point(engine.grid, value) for value in gym_positions)
    if not set(pc_positions) <= pc_zone or not set(gym_positions) <= gym_zone:
        raise ValueError("combatants must deploy in their observed side's zone")
    if len(set((*pc_positions, *gym_positions, tuple(row["nicolette_cell"])))) != len(actors):
        raise ValueError("deployment bodies need distinct map cells")
    def apply(staged, _, *subjects):
        staged_pcs = subjects[:len(pcs)]
        staged_gym = subjects[len(pcs):-1]
        observer = subjects[-1]
        staged_row = state(staged, required=True)
        for actor, position in zip(staged_pcs, pc_positions):
            actor.pos = position
            actor.side = "party"
            actor.on_field = True
        for actor, position in zip(staged_gym, gym_positions):
            actor.pos = position
            actor.side = "gym"
            actor.on_field = True
        observer.pos = tuple(staged_row["nicolette_cell"])
        observer.side = "gym"
        observer.on_field = False
        staged_row["deployment"] = {
            "reason": reason,
            "pc_ids": [actor.entity_id for actor in staged_pcs],
            "gym_ids": [actor.entity_id for actor in staged_gym],
            "nicolette_id": observer.entity_id,
            "participant_ids": [actor.entity_id for actor in (*staged_pcs, *staged_gym)],
        }
        staged.begin_encounter((*staged_pcs, *staged_gym))
        return deepcopy(staged_row["deployment"])

    return GRANTS.transition(engine, None, apply, participants=actors, include_grid=True)


def _pair(row, origin, destination):
    pair = {tuple(origin), tuple(destination)}
    return any({tuple(a), tuple(b)} == pair for a, b in row["ladder_links"])


def climb(engine, actor, destination, *, climb_id, route, reason, skill=None, fixed=None):
    """Traverse a linked ladder, or choose the check or Wallclimber cliff route."""
    row = state(engine, required=True)
    _text(climb_id, "climb attempt identity")
    _text(reason, "actual climb reason")
    destination = _point(engine.grid, destination)
    origin = actor.pos
    heights = row["heights"]
    if _key(origin) not in heights or _key(destination) not in heights:
        raise ValueError("climb endpoints need observed height levels")
    rise = abs(heights[_key(destination)] - heights[_key(origin)])
    if route not in ("ladder", "cliff"):
        raise ValueError("explicit ladder or cliff route required")
    if route == "ladder" and not _pair(row, origin, destination):
        raise ValueError("actual observed ladder link required")
    if route == "cliff" and rise != 3:
        raise ValueError("direct sample-map cliff attempts are exactly 3m")
    if route == "cliff" and max(abs(destination[0]-origin[0]), abs(destination[1]-origin[1])) != 1:
        raise ValueError("direct cliff climb requires adjacent horizontal endpoints")
    attempts = actor.spec.setdefault("_nicolette_climbs", {})
    if climb_id in attempts:
        raise ValueError("climb attempt identity already resolved")
    import body_state as BODY
    import movement_actions as MOVEMENT
    import turn as TURN
    if not BODY.can_place(engine, actor, destination, origin=origin):
        raise ValueError("climb destination is blocked or occupied")
    allowance = MOVEMENT.distance_budget(engine, actor, "land")
    wallclimber = "벽타기" in GRANTS.effective_capabilities(actor)
    checked = route == "cliff" and (skill is not None or not wallclimber)
    if checked and skill not in ("곡예", "육상"):
        raise ValueError("direct cliff climb chooses Acrobatics or Athletics")
    cost = rise if route == "ladder" or checked else rise * 2
    if cost > allowance:
        raise ValueError("climb exceeds actual land movement allowance")
    action = "standard" if checked else "shift"
    if not actor.on_field or actor.captured or not TURN.movement_permission(engine, actor):
        return False
    if not TURN.spend(engine, actor, action, "Nicolette gym climb", movement=action == "shift"):
        return False
    check = None
    if checked:
        options = {} if fixed is None else {"fixed": fixed}
        check = C.against_dc(engine.skill_roll(actor, skill, **options), 12)
        if not check.passed:
            attempts[climb_id] = {"route": route, "rise": rise, "skill": skill,
                                  "dc": 12, "passed": False, "reason": reason}
            return deepcopy(attempts[climb_id])
    if not MOVEMENT.departure(engine, actor, destination, actor.spec.get("_movement_altitude", 0)):
        return False
    actor.pos = destination
    enter_cell(engine, actor, "walk")
    attempts[climb_id] = {"route": route, "rise": rise, "cost": cost,
                          "skill": skill, "dc": None if check is None else 12,
                          "passed": True, "destination": destination, "reason": reason}
    engine.log("  " + actor.name + ": " + route + " climb " + str(rise) + "m", SOURCE)
    return deepcopy(attempts[climb_id])


def enter_cell(engine, actor, entry_kind):
    """Break observed river ice on a qualifying actual walk or fall."""
    row = state(engine)
    if row is None:
        return None
    if entry_kind not in ("walk", "fall"):
        raise ValueError("ice entry is an actual walk or fall")
    if entry_kind == "walk":
        import field_effects as FIELD
        if not FIELD.touches_ground(actor):
            return None
    import body_state as BODY
    ice = {tuple(value) for value in row["ice_cells"]}
    broken = {tuple(value) for value in row["broken_ice"]}
    contact = sorted(BODY.cells(actor,require_complete=True).intersection(ice)-broken)
    if not contact:
        return None
    threshold = 5 if entry_kind == "walk" else 3
    if actor.weight_class < threshold:
        return {"cell": contact[0], "cells": contact, "entry": entry_kind, "broken": False,
                "weight_class": actor.weight_class}
    for cell in contact:
        row["broken_ice"].append(list(cell))
        engine.grid.base_terrain[_key(cell)] = "underwater"
        engine.grid.slow.discard(cell)
    result = {"cell": contact[0], "cells": contact, "entry": entry_kind, "broken": True,
              "weight_class": actor.weight_class, "source": SOURCE}
    actor.spec.setdefault("_nicolette_ice_entries", []).append(deepcopy(result))
    engine.log("  frozen river breaks at " + str(contact), SOURCE)
    return result


def end_turn(engine, actor):
    """Apply the cold-water Speed-stage loss through the native stage consumer."""
    row = state(engine)
    if row is None:
        return False
    if actor.kind != "pokemon" or ICE_TYPES.intersection(actor.types):
        return False
    import field_effects as FIELD
    import map_terrain as MAP
    if not FIELD.touches_ground(actor):
        return False
    import body_state as BODY
    water = sorted(cell for cell in BODY.cells(actor,require_complete=True).intersection(map(tuple,row["broken_ice"]))
                   if MAP.base_at(engine.grid,cell)=="underwater")
    if not water:
        return False
    before = actor.stages["spe"]
    engine.change_stage(actor, "spe", -1)
    actor.spec.setdefault("_nicolette_cold_water_turns", []).append({
        "round": engine.round_no, "before": before, "after": actor.stages["spe"],
        "cell": water[0], "cells": water, "source": SOURCE})
    return True

