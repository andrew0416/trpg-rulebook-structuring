"""PTK capability limits connected to native actor state and action execution.

GM observations establish actual carried objects and contextual hand restrictions.
They do not grant an action, a hit, or an unspecified result after a failed check.
Generic threshold arithmetic lives in physical_limits; PTK numbers are data.
"""
import json
from pathlib import Path
from copy import deepcopy
import common_checks as C
import skill_modifiers as S
from physical_limits import number, classify_load, shifted_stage

def policy(actor):
    if not hasattr(actor.r, 'capability_policy'):
        actor.r.capability_policy=json.loads((Path(actor.r.root)/'data/capability-policy.json').read_text(encoding='utf-8'))
    return actor.r.capability_policy

def power(actor):
    import trainer_capabilities as TRAINER
    basis=actor.spec.get('power_basis','current')
    if basis not in ('current','base','derived'):raise ValueError('Power basis must be current, base, or derived')
    value=(actor.spec.get('movement') or {}).get('power')
    if basis=='derived':
        if actor.kind!='trainer' or value is not None:raise ValueError('derived trainer Power cannot also have a supplied current value')
        value=TRAINER.derived_power(actor)
    if value is None:raise ValueError('actual sheet Power required for current or base Power basis')
    if basis in ('base','derived') and TRAINER.has_edge(actor,'edge/파워-부스트'):value+=2
    if basis in ('base','derived'):
        import move_capabilities as MOVE_CAPABILITIES
        value=MOVE_CAPABILITIES.numeric_values(actor,{'power':value},('power',))['power']
    else:
        import move_capabilities as MOVE_CAPABILITIES
        value=MOVE_CAPABILITIES.current_values(actor,{'power':value},('power',))['power']
    import pokemon_capability_edges as CAP_EDGES
    value+=CAP_EDGES.bonus(actor,'power')
    import csv_item_capability_contracts as CSV_CAPABILITIES
    value+=CSV_CAPABILITIES.muscle_power_bonus(actor)
    import csv_item_form_contracts as CSV_FORMS
    value=CSV_FORMS.power_projection(actor,value)
    if actor.kind=='pokemon':
        import baby_templates as BABY
        value=BABY.limit_power(actor,value)
    return C.integer(value,'Power',1)


def limits(actor):
    value=power(actor);table=policy(actor)['weight_limits_kg']
    if str(value) not in table:raise ValueError('Power value has no published weight limits; explicit GM lifting policy required')
    return deepcopy(table[str(value)])

def load(actor):
    state=actor.spec.get('_carried_load')
    import control_mount as MOUNT
    rider_weight,rider_boundary=MOUNT.rider_load(actor)
    import equipped_transport_saddle as EQUIPMENT
    rider_weight+=EQUIPMENT.physical_load(actor)
    if (not state or not state['objects']) and not rider_weight:return {'band':'normal','weight_kg':0,'penalty':0}
    state=state or {'objects':[],'mode':'physical','boundary_band':rider_boundary}
    import telekinetic_load as TK
    mode=state.get('mode','physical')
    if mode not in ('physical','telekinetic'):raise ValueError('known carrying mode required')
    if rider_weight and mode=='telekinetic':raise ValueError('physical rider and telekinetic objects need an explicit separate load policy')
    TK.validate(actor)
    table=TK.table(actor) if mode=='telekinetic' else limits(actor)
    weight=sum(number(o['weight_kg'],'object weight',minimum=0) for o in state['objects'])+rider_weight
    band=classify_load(weight,table['heavy'],table['staggering'],state.get('boundary_band'))
    if band=='boundary':raise ValueError('heavy interval endpoint needs an explicit GM boundary ruling')
    if band=='too_heavy':raise ValueError('current carried load exceeds the actor Power limit; GM world response required')
    return {'band':band,'weight_kg':weight,'penalty':0 if band=='normal' else policy(actor)[band]['speed_stages']}

def set_carried(engine,actor,objects,reason,*,blocked_actions=(),boundary_band=None):
    if not isinstance(reason,str) or not reason.strip():raise ValueError('GM observation reason required')
    if not isinstance(objects,(list,tuple)):raise ValueError('actual carried object records required')
    copied=[]
    for item in objects:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id'].strip():
            raise ValueError('each object needs a stable identity')
        number(item.get('weight_kg'),'object weight',minimum=0)
        copied.append({'id':item['id'],'weight_kg':item['weight_kg']})
    if len({x['id'] for x in copied})!=len(copied):raise ValueError('duplicate carried object')
    if not isinstance(blocked_actions,(list,tuple)) or any(not isinstance(x,str) or not x.strip() for x in blocked_actions):
        raise ValueError('contextual blocked action identifiers required')
    if boundary_band not in (None,'normal','heavy','staggering'):raise ValueError('unknown boundary band')
    before=deepcopy(actor.spec.get('_carried_load'))
    state={'objects':copied,'blocked_actions':list(blocked_actions),'boundary_band':boundary_band,'reason':reason,
           'checked_round':None,'failure_pending':False}
    # Validate the proposed observation without altering the live sheet.
    from copy import copy
    probe=copy(actor);probe.spec=dict(actor.spec,_carried_load=state);current=load(probe)
    if not copied and blocked_actions:raise ValueError('hand restrictions require carried objects')
    import world_entities as WORLD
    world_objects=WORLD.prepare_carried(engine,actor,copied,reason)
    actor.spec['_carried_load']=state
    WORLD.commit_objects(engine,world_objects)
    import legendary_commands as LEGENDARY
    LEGENDARY.boundary(engine,'carried_objects_changed')
    engine.gm._rec('운반 물체',before,state,reason,actor)
    return current

def speed_stage(actor):
    return shifted_stage(actor.stages['spe'],load(actor)['penalty'],-6,6)

def accuracy(actor):
    return load(actor)['penalty']

def evasion(actor):
    import body_modes as MODES
    return load(actor)['penalty']+MODES.evasion(actor)

def movement_limit(actor,value):
    return min(value,1) if load(actor)['band']=='staggering' else value

def action_permission(engine,actor,kind,action_id=None):
    import csv_item_form_contracts as CSV_FORMS
    CSV_FORMS.require_independent(engine,actor)
    state=actor.spec.get('_carried_load')
    band=load(actor)['band']
    if state and state.get('failure_pending'):
        engine.log(f'    {actor.name}: 비틀거림 체크 실패 결과의 GM 결정 대기','capability/staggering')
        return False
    if band=='staggering' and kind in ('standard','full'):
        engine.log(f'    {actor.name}: 비틀거리는 무게를 들어 기본 행동 불가','capability/staggering')
        return False
    if state and action_id in state['blocked_actions']:
        engine.log(f'    {actor.name}: 운반 중 손/몸 사용 제약 — {action_id}','capability/heavy')
        return False
    return True

def carry_check(engine,actor,*,fixed=None,round_id=None,**roll_options):
    import turn as TURN
    if not TURN.can_act(engine,actor):return C.PendingDecision('unconscious carrying world response')
    state=actor.spec.get('_carried_load')
    if load(actor)['band']!='staggering':raise ValueError('staggering load required')
    if not engine.encounter_active:
        if not isinstance(round_id,str) or not round_id.strip():return C.PendingDecision('GM identified noncombat round')
        key='noncombat:'+round_id
    else:
        if engine.round_start_seconds is None:raise ValueError('open combat round required')
        key=engine.round_no
    if state and state['checked_round']==key:raise ValueError('carrying check already made for this round')
    if state and state['failure_pending']:return C.PendingDecision('GM consequence for previous failed carrying check')
    import skill_feature_actions as SF
    options=dict(roll_options,fixed=fixed)
    inflight=state.get('skill_inflight') if state else None
    use_feature=options.get('feature') is not None
    if inflight is not None and (not use_feature or inflight!={'round':key,'roll_id':options.get('roll_id')}):
        raise ValueError('resume the same observed carrying check before another declaration')
    skill,dc=('집중',10) if state and state.get('mode')=='telekinetic' else ('육상',policy(actor)['staggering']['athletics_dc'])
    if state and state.get('mode')=='telekinetic':
        options['skill_context']={'purpose':'telekinetic_carry','reason':'actual remote load carrying check'}
    prepared=engine._prepare_skill_roll(actor,skill,**options)
    if options.get('fixed') is not None:options['fixed']=prepared[3]
    if options.get('fixed_penalties') is not None:options['fixed_penalties']=prepared[4]
    if state is None:
        # A real rider can be the whole physical load. Reuse the ordinary
        # check ledger only after the actual roll declaration has validated.
        import control_mount as MOUNT
        _,boundary=MOUNT.rider_load(actor)
        set_carried(engine,actor,[],'actual mounted rider load',boundary_band=boundary)
        state=actor.spec['_carried_load']
    if use_feature:
        basis={'round':key,'load':deepcopy(state['objects']),'dc':dc}
        state['skill_inflight']={'round':key,'roll_id':options.get('roll_id')}
        check=SF.sequence(engine,'carry:'+options['roll_id'],basis,[(actor,skill,options)],lambda rolls:C.against_dc(rolls[0],basis['dc']))
        state=actor.spec['_carried_load']
        state.pop('skill_inflight',None)
    else:
        check=C.against_dc(engine.skill_roll(actor,skill,**options),dc)
        SF.finish(engine,actor,options.get('roll_id'))
    state['checked_round']=key;state['failure_pending']=not check.passed
    engine.log(f'    {actor.name}: 비틀거리는 무게 운반 {check.total} vs DC{dc}','capability/staggering')
    return check if check.passed else C.PendingDecision('GM failed carrying consequence (drop, stop, damage not specified)',check)

def end_turn(engine,actor):
    if engine.encounter_active and load(actor)['band']=='staggering':
        state=actor.spec.get('_carried_load')
        if state is None or state['checked_round']!=engine.round_no:raise ValueError('staggering load requires this round Athletics DC4 check')
        if state['failure_pending']:raise ValueError('failed carrying consequence is unresolved')

def resolve_carry_failure(engine,actor,*,outcome,reason):
    state=actor.spec.get('_carried_load')
    if not state or not state['failure_pending']:raise ValueError('no failed carrying result pending')
    if not isinstance(reason,str) or not reason.strip():raise ValueError('GM consequence reason required')
    if outcome not in ('release','continue'):raise ValueError('explicit release or continue decision required')
    before=deepcopy(state)
    if outcome=='release':
        import world_entities as WORLD
        # Validate the complete replacement before clearing either side of the
        # carrier relation. Landing is unknown until separately observed.
        world_objects=WORLD.prepare_carried(engine,actor,[],reason)
        state['objects']=[];state['blocked_actions']=[]
        WORLD.commit_objects(engine,world_objects)
    state['failure_pending']=False
    engine.gm._rec('운반 실패 결과',before,state,reason,actor)
    return deepcopy(state)

def throwing_range(engine,actor,*,category='small_object'):
    if actor.kind!='trainer':raise ValueError('trainer small-object throwing capability required')
    import throwing_masteries as THROWING
    base=policy(actor)['throwing']['trainer_small_object_base']+S.effective_rank(engine.r,actor,'육상')
    return THROWING.extend(actor,base,category)

def throw_small_object(engine,actor,*,item,destination,small_object,action_cost,reason):
    import turn as TURN
    from grid import cheb
    if small_object is not True:return C.PendingDecision('GM confirmation that the object is small')
    if not isinstance(reason,str) or not reason.strip():raise ValueError('GM object/action-cost ruling reason required')
    if not isinstance(item,str) or not item.strip():raise ValueError('actual inventory item required')
    inventory=actor.spec.get('items') or {}
    if type(inventory.get(item)) is not int or inventory[item]<1:raise ValueError('thrown item is not owned')
    if not isinstance(destination,(tuple,list)) or len(destination)!=2 or any(type(x)is not int for x in destination):
        raise ValueError('explicit grid destination required')
    destination=tuple(destination)
    if engine.grid is None:return C.PendingDecision('mapped origin and destination')
    distance=cheb(actor.pos,destination)
    if distance>throwing_range(engine,actor):raise ValueError('destination exceeds trainer throwing capability')
    if not engine.grid.inside(destination) or engine.grid.blocked(actor.pos,destination):
        raise ValueError('destination is outside the mapped throwing path')
    if action_cost not in ('standard','shift','swift','free','full'):raise ValueError('GM action cost required for unspecified generic throw')
    if not action_permission(engine,actor,action_cost,'throw:'+item):return False
    if not TURN.spend(engine,actor,action_cost,'작은 물체 투척'):return False
    inventory[item]-=1
    actor.spec.setdefault('thrown_objects',[]).append({'item':item,'origin':list(actor.pos),'destination':list(destination),'reason':reason})
    engine.log(f'    {actor.name}: {item}을 {distance}m 투척 (명중/공격 결과는 부여하지 않음)','capability/throwing')
    return {'item':item,'destination':destination,'distance':distance,'hit':None}

def set_object(engine,object_id,*,weight_kg,position,reason):
    import world_entities as WORLD
    number(weight_kg,'object weight',minimum=0)
    return WORLD.register_object(engine,object_id,weight_kg=weight_kg,
        location={'kind':'grid','cell':position},reason=reason)


def drag_object(engine,actor,*,object_id,destination,action_cost,reason,actor_destination=None,favorable_limit=None,round_id=None):
    # Hazard entry either completes or raises; this producer has no issued
    # continuation for a paid partial drag. Keep that ordinary failure atomic.
    import state_grants as G
    return G.transition(engine,actor,lambda e,c:_drag_object(e,c,object_id=object_id,
        destination=destination,action_cost=action_cost,reason=reason,
        actor_destination=actor_destination,favorable_limit=favorable_limit,round_id=round_id),
        include_grid=engine.grid is not None)


def _drag_object(engine,actor,*,object_id,destination,action_cost,reason,actor_destination=None,favorable_limit=None,round_id=None):
    import turn as TURN
    from grid import cheb
    if not isinstance(reason,str) or not reason.strip():raise ValueError('GM drag context/action cost reason required')
    obj=engine._physical_objects.get(object_id)
    if obj is None:raise ValueError('actual observed object required')
    import world_entities as WORLD
    WORLD.require_present_object(obj)
    if obj.get('carrier_id'):raise ValueError('carried object must be released before dragging')
    WORLD.grid_cell(obj);WORLD.grid_cell(actor)
    if engine.grid is None:return C.PendingDecision('mapped dragging context')
    if not isinstance(destination,(list,tuple)) or len(destination)!=2 or any(type(x)is not int for x in destination):raise ValueError('object destination required')
    destination=tuple(destination)
    if actor_destination is None:actor_destination=actor.pos
    if not isinstance(actor_destination,(list,tuple)) or len(actor_destination)!=2 or any(type(x)is not int for x in actor_destination):raise ValueError('actor destination required')
    actor_destination=tuple(actor_destination)
    if cheb(actor.pos,obj['pos'])>1 or cheb(actor_destination,destination)>1:raise ValueError('ordinary drag requires continued physical reach')
    if cheb(obj['pos'],destination)!=1 or cheb(actor.pos,actor_destination)>1:raise ValueError('ordinary drag moves one metre per round')
    for origin,target in [(obj['pos'],destination),(actor.pos,actor_destination)]:
        if not engine.grid.inside(target) or engine.grid.blocked(origin,target):raise ValueError('dragging path is blocked')
    import body_state as BODY
    if not BODY.can_place(engine,actor,actor_destination,origin=actor.pos,altitude=actor.spec.get('_movement_altitude',0)):
        raise ValueError('dragging actor body is blocked or occupied')
    if destination in engine.occupied(actor):raise ValueError('dragging destination is occupied')
    if actor_destination in engine.grid.slow or destination in engine.grid.slow:return C.PendingDecision('dragging distance with slow terrain')
    # The chapter does not grant airborne pulling or an arbitrary action cost.
    if getattr(actor,'airborne',False):return C.PendingDecision('airborne object dragging')
    table=limits(actor);weight=obj['weight_kg'];limit=table['drag']
    if weight<=table['staggering']:return C.PendingDecision('ordinary object movement below the stated drag band')
    if favorable_limit is not None:
        number(favorable_limit,'GM favorable drag limit',minimum=limit)
        if favorable_limit<=limit:raise ValueError('favorable limit must actually increase the limit')
        limit=favorable_limit
    if weight==limit:return C.PendingDecision('drag exact-limit equality is unspecified')
    if weight>limit:raise ValueError('object exceeds dragging capability')
    if engine.encounter_active:
        if engine.round_start_seconds is None:raise ValueError('open combat round required')
        key=engine.round_no
    else:
        if not isinstance(round_id,str) or not round_id.strip():return C.PendingDecision('GM identified noncombat round')
        key='noncombat:'+round_id
    if actor.spec.get('_drag_round')==key or obj.get('drag_round')==key:raise ValueError('ordinary one-metre drag already used this round')
    if action_cost not in ('standard','shift','swift','free','full'):raise ValueError('GM action cost required for drag')
    if actor_destination!=actor.pos and not TURN.movement_permission(engine,actor):return False
    if not action_permission(engine,actor,action_cost,'drag:'+object_id):return False
    if not TURN.spend(engine,actor,action_cost,'물체 밀기/끌기',movement=(action_cost=='shift' and actor_destination!=actor.pos)):return False
    before=deepcopy(obj);old_actor=actor.pos
    WORLD._set_object_location(obj,{'kind':'grid','cell':destination})
    obj['drag_round']=key;actor.spec['_drag_round']=key;actor.pos=actor_destination
    engine.log(f'    {actor.name}: {object_id} {before["pos"]} → {destination} (1m/round, 한계 {limit}kg)','capability/drag')
    if actor.pos!=old_actor:
        import effects_ext as EXT
        EXT.on_enter_cell(engine,actor,actor.pos)
    return {'object':object_id,'position':destination,'actor_position':actor.pos,'weight_kg':weight,'limit_kg':limit}

def finish_round(engine):
    for actor in engine._time_actors:
        end_turn(engine,actor)
