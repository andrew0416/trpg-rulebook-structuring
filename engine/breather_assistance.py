"""Actual assisted Breather over existing Full budgets, reaction and movement paths."""
from contextlib import contextmanager
from copy import copy,deepcopy
import action_lifecycle as ACTION
import body_state as BODY
import breather as B
import common_checks as C
import initiative_interrupts as INTERRUPTS
import movement_actions as MOVEMENT
import observed_resolution as OBS
import turn as TURN
import world_entities as W

GRANT='native_assisted_breather'

@contextmanager
def _grant(engine,actor,helper,request_id):
    token=object()
    engine._action_grants.append((token,actor,helper,request_id,'full',GRANT))
    try:yield token
    finally:
        engine._action_grants[:]=[row for row in engine._action_grants if row[0] is not token]

def permission(engine,actor,kind,token):
    if token is None:return False
    issued=[row for row in engine._action_grants if row[0] is token]
    if len(issued)!=1:raise ValueError('actual issued assisted Breather Full authority required')
    _,target,helper,request_id,cost,source=issued[0]
    observation=getattr(engine,B.FIELD,{}).get(request_id,{}).get(OBS.KEY,{})
    stack=getattr(engine,'_native_action_stack',[]);frame=INTERRUPTS.frame(engine)
    if (source!=GRANT or cost!='full' or kind!='full' or target is not actor
            or observation.get('participants')!=(actor,helper) or observation.get('state')!='pending'
            or observation.get('observation',{}).get('phase')!='participant_cost'
            or not stack or stack[-1]['source']!=B.SOURCE or stack[-1]['kind']!='assisted_breather'
            or stack[-1]['actor'] is not helper or not frame or frame['actor'] is not actor
            or frame['parent'] is not helper or frame['request_id']!=request_id):
        raise ValueError('assisted Breather grant belongs only to its actual participant Full cost')
    return True

def consume(engine,token):
    engine._action_grants[:]=[row for row in engine._action_grants if row[0] is not token]

def _path(engine,actor,path,reason,*,mode=None,options=None):
    plan=B._retreat(engine,actor,path,reason,movement_mode=mode,movement_options=options,require_highest=False)
    if isinstance(plan,C.PendingDecision):return plan
    points=[node['position'] if type(node)is dict else node for node in plan['path']]
    if plan['mode']=='teleport':diagonals=getattr(actor,'_diagonal_steps',0)
    else:diagonals=plan.get('diagonals',getattr(actor,'_diagonal_steps',0)+sum(a[0]!=b[0] and a[1]!=b[1] for a,b in zip(points,points[1:])))
    return dict(plan,diagonals=diagonals)

def _state(actor):
    return {'position':actor.pos,'altitude':actor.spec.get('_movement_altitude',0),
            'underground':bool(actor.spec.get('_burrow',{}).get('underground'))}

def _states(actor,plan):
    result=[];mode=plan.get('mode','육상');parameters=plan.get('parameters',{})
    for index,node in enumerate(plan['path']):
        state={'position':node['position'] if type(node)is dict else node,
               'altitude':node['altitude'] if type(node)is dict else plan.get('origin_altitude',actor.spec.get('_movement_altitude',0)),
               'underground':plan.get('origin_underground',False)}
        if index and mode=='teleport':state.update(altitude=parameters['altitude'],underground=False)
        if index and mode=='burrow':state.update(altitude=0,underground=not(parameters['surface'] and index==len(plan['path'])-1))
        result.append(state)
    return result

def _contact(helper,actor,helper_state,target_state,assistance):
    if (helper_state['altitude']==target_state['altitude'] and not helper_state['underground'] and not target_state['underground']):
        return BODY.adjacent(helper,actor,left_position=helper_state['position'],right_position=target_state['position'])
    if 'reach_distance' not in assistance:
        return C.PendingDecision('actual 3D/underground assisting contact distance and reason required')
    B._text(assistance.get('reach_reason'),'actual assisting contact measurement reason')
    from physical_limits import number
    from grid import cheb
    distance=number(assistance['reach_distance'],'actual assisting contact distance',minimum=0)
    horizontal=min(cheb(a,b) for a in BODY.at_position(helper,helper_state['position']) for b in BODY.at_position(actor,target_state['position']))
    if distance<max(horizontal,abs(helper_state['altitude']-target_state['altitude'])):
        raise ValueError('assisting contact measurement is shorter than actual displacement')
    return 0<distance<=1

def _move(engine,actor,plan,reason,*,budget,progress):
    result=B._move(engine,actor,dict(plan,budget=min(budget,plan.get('budget',budget))),progress,reason)
    if result['steps']!=len(plan['path'])-1 or not TURN.can_act(engine,actor):
        raise ValueError('actual assisted Breather path interrupted; paid cost and observed Command cannot replay')
    return result

def _retreat(engine,actor,helper,request_id,record):
    observed=record['observation'];movement=observed['movement']
    parties={'target':actor,'helper':helper}
    legs=[('approach',helper,observed['approach'],observed['allowances'][1],observed['assistance_reason'])]
    legs.extend((name,parties[name],observed['plans'][name],observed['shared'],observed['retreat_reason']) for name in observed['order'])
    for name,mover,plan,budget,reason in legs:
        if name not in movement:
            if name!='approach' and not observed.get('contact_confirmed',False):
                contact=observed.get('contact')
                if contact is not None and (contact['helper']!=_state(helper) or contact['target']!=_state(actor)):
                    raise ValueError('actual assisting contact changed after the observed approach')
                if contact is None and not BODY.adjacent(helper,actor):
                    raise ValueError('actual assisting contact required after approach')
                observed['contact_confirmed']=True
            if name=='helper':budget=min(budget,max(0,observed['allowances'][1]-movement['approach']['distance']))
            movement[name]=_move(engine,mover,plan,reason,budget=budget,progress=observed['progress'].setdefault(name,{}))
    return B._finish(engine,actor,request_id,observed['origin'],helper=helper,movement=movement)

def _continue(engine,actor,helper,request_id,record):
    B.validate_continuation(engine,helper,B.SOURCE,'assisted_breather',record)
    with ACTION.resolution(engine,helper,B.SOURCE,kind='assisted_breather',_breather_attempt=record):
        MOVEMENT.boundary(engine,'assisted_breather_continuation');INTERRUPTS.require_clear(engine)
        return _retreat(engine,actor,helper,request_id,record)

def take(engine,actor,helper,*,request_id,path,retreat_reason,curse_origin,curse_reason,assistance):
    W.require_actors(engine,actor,helper)
    if assistance is None:return C.PendingDecision('actual assisted Breather routes and current/next participant payment')
    required={'reason','approach_path','helper_path','retreat_order','retreat_order_reason','target_payment','payment_reason'}
    if type(assistance) is not dict or not required<=set(assistance) or set(assistance)-required-{'command_options','movement','reach_distance','reach_reason'}:
        raise ValueError('exact actual assisted Breather route, order and payment observations required')
    for key in ('reason','payment_reason','retreat_order_reason'):B._text(assistance[key],key)
    command=assistance.get('command_options',{})
    allowed={'mods','helper_rank','fixed','penalty_count','fixed_penalties','roll_id','helper_bonus','skill_context','skill_stunt'}
    if type(command) is not dict or set(command)-allowed:raise ValueError('ordinary native Command check options required')
    movement_specs=assistance.get('movement',{})
    if type(movement_specs)is not dict or set(movement_specs)-{'target','helper','approach'}:raise ValueError('actual participant movement mapping required')
    motions={}
    for name in ('target','helper','approach'):
        spec=movement_specs.get(name,{})
        if type(spec)is not dict or set(spec)-{'mode','options'}:raise ValueError('actual movement mode and observation options required')
        motions[name]={'movement_mode':spec.get('mode'),'movement_options':spec.get('options')}
    declaration={'actor':actor,'helper':helper,'path':deepcopy(path),'retreat_reason':retreat_reason,
        'curse_origin':curse_origin,'curse_reason':curse_reason,'assistance':deepcopy(assistance)}
    records=getattr(engine,B.FIELD,{})
    if request_id in records:
        old=records[request_id][OBS.KEY];OBS.verify(old,declaration)
        if old['state']=='complete':return old['result']
        return _continue(engine,actor,helper,request_id,old)
    MOVEMENT.boundary(engine,'assisted_breather');ACTION.ensure_resolutions_clear(engine);INTERRUPTS.require_clear(engine)
    if actor is helper or helper.kind!='trainer' or actor.kind not in ('trainer','pokemon'):
        raise ValueError('assisted Breather needs distinct actual Trainer and Trainer/Pokemon target')
    if not engine.encounter_active:return C.PendingDecision('actual assisted Breather combat owner-turn boundary')
    if any(not c.on_field or c.captured or not TURN.can_act(engine,c) for c in (actor,helper)):return False
    if not ACTION.ordinary_permission(engine,helper) or not ACTION.status_permission(engine,helper,'full') or not ACTION.status_permission(engine,actor,'full'):return False
    import combat_maneuvers as MANEUVERS
    if MANEUVERS.force_attack(helper):return C.PendingDecision('assisting Trainer cannot perform a non-damaging Full while Enraged')
    if not MANEUVERS.force_attack(actor) and '혼란' not in actor.conditions:
        return C.PendingDecision('source-qualified inability or unwillingness to choose voluntary Breather')
    if not isinstance(helper.budget,dict) or min(helper.budget.get('standard',0),helper.budget.get('shift',0))<=0:return False
    payment=assistance['target_payment']
    if payment not in ('current','next'):raise ValueError('explicit current/next participant Full payment required')
    import action_resources as RESOURCES
    if payment=='current':
        if getattr(engine,'_ordinary_turn_rounds',{}).get(actor)!=engine.round_no or not isinstance(actor.budget,dict):
            raise ValueError('current participant Full requires its actual current-round prior budget')
        if RESOURCES.plan_cost(actor.budget,['standard','shift']) is None:return False
    elif RESOURCES.pending(actor):return C.PendingDecision('distinct participant future Full losses need actual conjunction policy')
    selected=[B._allowance(engine,c,motions[name]['movement_mode']) for name,c in (('target',actor),('helper',helper))]
    pending=next((x for x in selected if isinstance(x,C.PendingDecision)),None)
    if pending is not None:return pending
    allowances=[item[0] for item in selected]
    approach=_path(engine,helper,assistance['approach_path'],assistance['reason'],
                   mode=motions['approach']['movement_mode'],options=motions['approach']['movement_options'])
    if isinstance(approach,C.PendingDecision):return approach
    approach_end=_states(helper,approach)[-1]
    target_start=_state(actor)
    contact=_contact(helper,actor,approach_end,target_start,assistance)
    if isinstance(contact,C.PendingDecision):return contact
    if approach['distance']>allowances[1] or not contact:
        raise ValueError('assisting Trainer must actually be able to reach the target')
    order=assistance['retreat_order']
    if type(order) is not list or sorted(order)!=['helper','target']:raise ValueError('actual two-participant retreat order required')
    shared=min(allowances)
    positions={'helper':approach_end,'target':_state(actor)};parties={'helper':helper,'target':actor};plans={}
    for name in order:
        other='target' if name=='helper' else 'helper';mover=parties[name]
        plan=B._retreat(engine,mover,assistance['helper_path'] if name=='helper' else path,retreat_reason,
            start=positions[name]['position'],start_altitude=positions[name]['altitude'],start_underground=positions[name]['underground'],
            maximum_distance=shared,ignore_actors=(actor,helper),**motions[name],
            diagonals=approach['diagonals'] if name=='helper' else None)
        if isinstance(plan,C.PendingDecision):return plan
        occupied=BODY.at_position(parties[other],positions[other]['position']);states=_states(mover,plan)
        if any(state['altitude']==positions[other]['altitude'] and state['underground']==positions[other]['underground']
               and BODY.at_position(mover,state['position']).intersection(occupied) for state in states[1:]):
            raise ValueError('declared joint retreat crosses the actual other participant body')
        plans[name]=plan;positions[name]=states[-1]
    if approach['distance']+plans['helper']['distance']>allowances[1]:
        return C.PendingDecision('approach plus retreat exceeds helper actual movement; source composition adjudication required')
    origin=B._curse(engine,actor,curse_origin,curse_reason)
    if isinstance(origin,C.PendingDecision):return origin
    origin=B._curse_retreat(actor,origin,plans['target'])
    if isinstance(origin,C.PendingDecision):return origin
    import combat_state_lifecycle as STATE,temporary_hp as TEMP
    STATE.preflight(actor);TEMP.ensure_certain(engine,actor)
    engine._prepare_skill_roll(helper,'명령',**command)
    import state_grants as G
    with ACTION.resolution(engine,helper,B.SOURCE,kind='assisted_breather'):
        def pay(staged,target,trainer):
            if not TURN.spend(staged,trainer,'full','보조 숨돌리기'):raise ValueError('assisting Trainer cannot pay actual Full')
            if not hasattr(staged,B.FIELD):setattr(staged,B.FIELD,{})
            staged_origin=None if curse_origin is None else W.actor_index(staged)[curse_origin.entity_id]
            local=dict(declaration,actor=target,helper=trainer,curse_origin=staged_origin)
            references=() if local['curse_origin'] is None else (local['curse_origin'],)
            observation=OBS.begin(getattr(staged,B.FIELD),request_id,'assisted_breather',(target,trainer),local,
                {'phase':'participant_cost'},references=references)
            queued=INTERRUPTS.queue(staged,[{'id':request_id,'actor_id':target.entity_id,'source':B.SOURCE,'priority':0,
                'mode':'reaction','payment':payment,'budget':{'standard':1,'shift':1},'clock':'none','debt_policy':'hold'}],
                trigger={'kind':'turn','actor_id':trainer.entity_id,'serial':trainer.custom_conditions['combat_turn_serial'],'round':staged.round_no})
            window=queued['window_id'];INTERRUPTS.begin(staged,window,request_id)
            with _grant(staged,target,trainer,request_id) as token:
                if not TURN.spend(staged,target,'full','도움받는 숨돌리기',_assisted_breather=token):
                    raise ValueError('target cannot pay actual assisted Full under its current permissions')
            INTERRUPTS.finish(staged)
            observation=getattr(staged,B.FIELD)[request_id][OBS.KEY]
            observation['observation'].update(phase='costs_paid',window_id=window,payment=payment)
        G.transition(engine,actor,pay,participants=(helper,),include_rulings=True)
        passed,total=engine.skill_check(helper,'명령',12,**command)
        observed=getattr(engine,B.FIELD)[request_id][OBS.KEY]
        observed['observation'].update(phase='command_observed',command={'passed':passed,'total':total,'dc':12})
        if not passed:return OBS.complete(observed,{'completed':False,'command':observed['observation']['command'],'reason':'command_failed'})
        observed['observation'].update(phase='retreat',turn=B._turn(engine,helper),
            approach=approach,plans=plans,allowances=allowances,shared=shared,order=order,
            contact={'helper':approach_end,'target':target_start},
            origin=origin,assistance_reason=assistance['reason'],retreat_reason=retreat_reason,
            movement={},progress={})
        return _retreat(engine,actor,helper,request_id,observed)
