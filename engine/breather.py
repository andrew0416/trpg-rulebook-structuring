"""Native Take a Breather producer; unprinted table decisions remain explicit.

The selected prose gives no universal saving DC or failed-save cost. Those are
table adjudications, not invented rule constants. Mapped retreat uses an observed
route: its maximality is a GM world observation, not an attack flag.
"""
from copy import copy,deepcopy
import common_checks as C
import action_lifecycle as ACTION
import movement_actions as MOVEMENT
import observed_resolution as OBS
import turn as TURN
import world_entities as W

SOURCE='ch07-combat/전투의-다른-행동/숨돌리기'
SOURCE_REF={'file':'input/ch07-combat.md','sha256':'57abb79c4f70c64246cd7927bffe2377e951bdc32dfa4c9a5c14b4ad97618c18'}
FIELD='_breather_attempts'

def selected(rules):
    from source_context import verified_source
    if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Take a Breather source required')
    verified_source(rules,SOURCE_REF,label='Take a Breather')
    if rules.selection.units[SOURCE]['source']['lines']!=[550,559]:raise ValueError('Take a Breather literal source changed')

def ensure_clear(engine,*,resume=None):
    if any(frame['source']==SOURCE for frame in getattr(engine,'_native_action_stack',())):return
    if any(row[OBS.KEY]['state']!='complete' and row[OBS.KEY] is not resume for row in getattr(engine,FIELD,{}).values()):
        raise ValueError('unfinished actual Take a Breather producer must resolve before another action')

def validate_continuation(engine,actor,source,kind,record):
    if type(record) is not dict:raise ValueError('actual interrupted Breather observation required')
    actual=any(row[OBS.KEY] is record for row in getattr(engine,FIELD,{}).values())
    participants=record.get('participants',())
    expected=participants[0] if kind=='breather' and len(participants)==1 else participants[-1] if kind=='assisted_breather' and len(participants)==2 else None
    observed=record.get('observation',{})
    family='take_a_breather' if kind=='breather' else 'assisted_breather'
    if (not actual or record.get('state')!='pending' or record.get('family')!=family or source!=SOURCE or actor is not expected
            or observed.get('phase')!='retreat' or observed.get('turn')!=_turn(engine,actor)):
        raise ValueError('actual interrupted Breather continuation requires the same producer and owner turn')

def _turn(engine,actor):
    return (actor,engine.round_no,actor.custom_conditions.get('combat_turn_serial'),engine._active_turn_actor)

def _move(engine,actor,plan,progress,reason):
    if not progress:
        first=plan['path'][0];position=first['position'] if type(first)is dict else first
        if (actor.pos!=position or actor.spec.get('_movement_altitude',0)!=plan.get('origin_altitude',actor.spec.get('_movement_altitude',0))
                or bool(actor.spec.get('_burrow',{}).get('underground'))!=plan.get('origin_underground',bool(actor.spec.get('_burrow',{}).get('underground')))):
            raise ValueError('actual Breather movement origin changed after observation')
        engine.gm._rec('숨돌리기 실제 최장 후퇴 경로',actor.pos,plan['path'],reason,actor)
    if plan.get('mode') in ('burrow','teleport'):
        result=MOVEMENT.follow_paid_transfer(engine,actor,plan,progress=progress)
    else:
        result=MOVEMENT.follow_paid_path(engine,actor,plan['path'][1:],mode=plan.get('mode','육상'),
                                        maximum_distance=plan['budget'],progress=progress)
    if result['steps']:actor._regular_shift_movement_used=True
    return result

def _finish(engine,actor,request_id,origin,*,helper=None,movement=None):
    import state_grants as G
    import effect_contracts as EFFECTS
    EFFECTS.ensure_clear(engine)
    observed=getattr(engine,FIELD)[request_id][OBS.KEY]['observation']
    cursors=[observed['progress']] if helper is None else observed['progress'].values()
    if any(ACTION.pending_resolution_effects(engine,{'effects':cursor.get('effects',[])}) for cursor in cursors):
        raise ValueError('actual retreat effects must resolve before Breather recovery')
    def recover(staged,target,*assistants):
        staged_origin=None if origin is None else W.actor_index(staged)[origin.entity_id]
        _recover(staged,target,staged_origin)
        if assistants:_disadvantage(staged,assistants[0],assisting=True)
        import stamina as STAMINA
        STAMINA.observe(staged,target,'take_a_breather',request_id=request_id,
                        **({} if not assistants else {'helper':assistants[0].entity_id}))
        record=getattr(staged,FIELD)[request_id][OBS.KEY]
        result={'completed':True,'movement':movement,'source':SOURCE}
        if assistants:result.update(command=record['observation']['command'],helper=assistants[0].entity_id)
        else:result['save']=record['observation']['check']
        staged.log('  '+target.name+': 숨돌리기 해결',SOURCE)
        return OBS.complete(record,result)
    return G.transition(engine,actor,recover,participants=() if helper is None else (helper,),include_rulings=True)

def _continue(engine,actor,request_id,record):
    validate_continuation(engine,actor,SOURCE,'breather',record)
    MOVEMENT.boundary(engine,'take_breather_continuation')
    with ACTION.resolution(engine,actor,SOURCE,kind='breather',_breather_attempt=record):
        observed=record['observation']
        movement=_move(engine,actor,observed['retreat'],observed['progress'],observed['retreat']['reason'])
        record=getattr(engine,FIELD)[request_id][OBS.KEY]
        if not TURN.can_act(engine,actor):
            return OBS.complete(record,{'completed':False,'save':record['observation']['check'],'movement':movement,'reason':'incapacitated_during_retreat'})
        if movement['steps']!=len(record['observation']['retreat']['path'])-1:
            raise ValueError('actual Breather path interrupted; continue the same paid and observed producer')
        return _finish(engine,actor,request_id,record['observation']['origin'],movement=movement)

def _text(value,label):
    if not isinstance(value,str) or not value.strip():raise ValueError('explicit '+label+' required')
    return value

def _allowance(engine,actor,movement_mode=None,*,highest=True):
    mode='land' if movement_mode is None else movement_mode
    if mode not in MOVEMENT.MODES:raise ValueError('unknown Breather movement capability')
    caps=MOVEMENT.capabilities(engine,actor)
    available={key:engine.move_profile(actor,movement_mode=key)[0] for key in MOVEMENT.MODES if caps.get(key,0)>0}
    if not available.get(mode,0) or (highest and available[mode]<max(available.values())):
        return C.PendingDecision('Breather must use its actual highest available movement capability')
    if any(key in actor.spec for key in ('mount_id','vehicle_id')) or (actor.spec.get('_burrow',{}).get('underground') and mode!='burrow'):
        return C.PendingDecision('Breather mounted/vehicle/underground retreat composition')
    if mode in ('land','swim','burrow') and actor.spec.get('_movement_altitude',0)!=0:
        return C.PendingDecision('actual aerial retreat needs Sky or Levitate and observed altitudes')
    return available[mode],mode

def _land_allowance(engine,actor):
    result=_allowance(engine,actor,'land')
    return result if isinstance(result,C.PendingDecision) else result[0]

def _retreat(engine,actor,path,reason,*,start=None,maximum_distance=None,ignore_actors=(),diagonals=None,
             movement_mode=None,movement_options=None,start_altitude=None,start_underground=None,require_highest=True):
    _text(reason,'GM maximal retreat route observation')
    if not isinstance(path,(list,tuple)) or not path:raise ValueError('actual observed retreat path required')
    probe=copy(actor);probe.spec=dict(actor.spec);probe.pos=actor.pos if start is None else start
    if start_altitude is not None:probe.spec['_movement_altitude']=start_altitude
    if start_underground is not None:probe.spec['_burrow']=dict(actor.spec.get('_burrow',{}),underground=start_underground)
    if diagonals is not None:probe._diagonal_steps=diagonals
    allowance=_allowance(engine,probe,movement_mode,highest=require_highest)
    if isinstance(allowance,C.PendingDecision):return allowance
    budget,capability=allowance
    if maximum_distance is not None:budget=min(budget,C.integer(maximum_distance,'joint retreat allowance',0))
    if capability in ('burrow','teleport'):
        points=tuple(MOVEMENT._point(p) for p in path)
        if points[0]!=probe.pos:raise ValueError('retreat path must start at the actual actor position')
        if movement_options is not None and type(movement_options)is not dict:raise ValueError('actual movement observation options required')
        options={} if movement_options is None else movement_options
        if len(points)==1:
            if options:raise ValueError('stationary Breather does not perform a native transfer')
            return {'mode':capability,'path':points,'distance':0,'budget':budget,'reason':reason,'parameters':{},
                    'origin_altitude':probe.spec.get('_movement_altitude',0),'origin_underground':bool(probe.spec.get('_burrow',{}).get('underground'))}
        if not TURN.movement_permission(engine,actor):raise ValueError('actual condition prevents the declared retreat path')
        if capability=='burrow':
            if set(options)-{'diggable','surface'}:raise ValueError('unknown actual Burrow observation')
            plan=MOVEMENT.burrow_plan(engine,probe,points,maximum_distance=budget,reason_text=reason,
                diggable=options.get('diggable'),surface=options.get('surface',False),ignore_actors=ignore_actors)
        else:
            if len(points)!=2:raise ValueError('Teleport retreat is one actual origin and destination, not a walking path')
            if set(options)-{'surface_contact','altitude','gm_distance','sky_air_policy'}:raise ValueError('unknown actual Teleport observation')
            if 'surface_contact' not in options:return C.PendingDecision('actual Teleport destination surface contact required')
            plan=MOVEMENT.teleport_plan(engine,probe,points[-1],maximum_distance=budget,reason_text=reason,ignore_actors=ignore_actors,**options)
        if isinstance(plan,C.PendingDecision):return plan
        return dict(plan,reason=reason)
    if movement_options is not None:raise ValueError('movement options belong to actual Burrow or Teleport observations')
    aerial=capability in ('sky','levitate')
    if aerial:
        if any(type(node)is not dict or set(node) not in ({'position','altitude'},{'position','altitude','gm_distance'}) for node in path):
            raise ValueError('aerial retreat requires actual position, altitude and optional measured distance')
        points=[dict(node,position=MOVEMENT._point(node['position'])) for node in path]
        if points[0]['altitude']!=probe.spec.get('_movement_altitude',0) or 'gm_distance' in points[0]:
            raise ValueError('aerial retreat must start at actual current altitude')
        for node in points:MOVEMENT._aerial_height(engine,probe,capability,node['altitude'])
        positions=[node['position'] for node in points]
        mode=capability
    else:
        points=[MOVEMENT._point(p) for p in path];positions=points
        mode=engine.move_profile(actor,movement_mode=capability)[1]
    if positions[0]!=(actor.pos if start is None else start):raise ValueError('retreat path must start at the actual actor position')
    if len(points)>1:
        if not TURN.movement_permission(engine,actor):raise ValueError('actual condition prevents the declared retreat path')
        nodes=points if aerial else [{'position':p,'altitude':0} for p in points]
        observed=MOVEMENT.observed_path(engine,probe,nodes,ignore_actors=ignore_actors)
        import map_terrain as TERRAIN
        if any(not TERRAIN.can_travel(engine,actor,p,mode,altitude=(node['altitude'] if aerial else 0)) for p,node in zip(positions[1:],nodes[1:])):raise ValueError('retreat lacks the actual base-terrain movement capability')
        diagonals=getattr(actor,'_diagonal_steps',0);penalty=0
        for start_point,end_point in zip(positions,positions[1:]):
            step,diagonals=MOVEMENT.step_cost(start_point,end_point,diagonals)
            penalty+=MOVEMENT.slow_terrain_penalty(engine,actor,end_point,mode,step=step)
        distance=observed['distance']+penalty
        if distance>budget:raise ValueError('retreat exceeds actual highest movement allowance')
    else:distance=0
    return {'path':points,'distance':distance,'budget':budget,'reason':reason,'mode':mode,
            'origin_altitude':probe.spec.get('_movement_altitude',0),'origin_underground':bool(probe.spec.get('_burrow',{}).get('underground'))}

def _curse_retreat(actor,origin,plan):
    if origin is not None and not origin.fainted:
        height=(plan['path'][-1]['altitude'] if plan['mode'] in ('sky','levitate') else
                plan.get('parameters',{}).get('altitude',plan.get('origin_altitude',actor.spec.get('_movement_altitude',0))))
        underground=(plan['mode']=='burrow' and not plan['parameters'].get('surface',not plan.get('origin_underground',False)))
        if height!=0 or underground or origin.spec.get('_burrow',{}).get('underground'):
            return C.PendingDecision('Breather Curse distance requires actual 3D/underground measurement')
    return origin

def _curse(engine,actor,origin,reason):
    known=actor.custom_conditions.get('curse_origin')
    if known is not None and origin is not None and known is not origin:raise ValueError('cannot replace the actual Curse origin')
    origin=known if known is not None else origin
    if '저주' not in actor.conditions:
        if origin is not None or reason is not None:raise ValueError('Curse observation requires an actual cursed actor')
        return None
    if origin is None:return C.PendingDecision('actual Curse origin required for Breather cure exception')
    W.require_actors(engine,origin)
    if known is None:_text(reason,'GM observation of actual Curse origin')
    if origin.spec.get('_movement_altitude',0)!=0:return C.PendingDecision('Breather Curse distance requires actual 3D measurement')
    return origin

def _recover(engine,actor,origin):
    import status_sets as STATUSES,combat_state_lifecycle as STATE,temporary_hp as TEMP
    import body_state as BODY
    from grid import cheb
    for condition in STATUSES.afflictions(actor,'volatile'):
        if condition=='저주':
            if not origin.fainted:
                if (actor.spec.get('_movement_altitude',0)!=origin.spec.get('_movement_altitude',0)
                        or any(c.spec.get('_burrow',{}).get('underground') for c in (actor,origin))):
                    raise ValueError('actual Breather Curse distance requires 3D or underground observation')
                distance=min(cheb(a,b) for a in BODY.cells(actor,require_complete=True) for b in BODY.cells(origin,require_complete=True))
                if distance<=12:continue
        engine.cure_status(actor,condition)
    import healing_blocks as HEALING_BLOCKS
    HEALING_BLOCKS.boundary(engine,(actor,),'breather')
    for condition in ('둔화','구속'):engine.cure_status(actor,condition)
    STATE.reset_actor(engine,actor)
    TEMP.clear(engine,actor,'숨돌리기')
    _disadvantage(engine,actor)

def _disadvantage(engine,actor,*,assisting=False):
    import effect_lifetimes as LIFETIMES,combat_timing as TIMING
    record=LIFETIMES.prepare(engine,actor,actor,
        {'type':'apply_status','status':'넘어짐','until':"end of user's next turn"},SOURCE)
    record['statuses']=['넘어짐'] if assisting else ['넘어짐','취약']
    if assisting:record['evasion_zero']=True
    TIMING.install(engine,actor,record)

def take(engine,actor,*,request_id,path=None,retreat_reason=None,save_dc=None,save_reason=None,
         save_cost=None,fixed_save=None,curse_origin=None,curse_reason=None,helper=None,assistance=None,movement_mode=None,movement_options=None):
    """Ordinary voluntary producer. Unsupported assisted/movement branches hold.

    save_cost is an explicit table decision: full on any attempt, or only after
    a successful permission save. A saved observation cannot be rerolled.
    """
    W.require_actors(engine,actor);selected(engine.r)
    _text(request_id,'Breather request identity')
    if helper is not None:
        if movement_mode is not None or movement_options is not None:return C.PendingDecision('assisted Breather distinct participant movement modes and reach')
        if assistance is not None and any(x is not None for x in (save_dc,save_reason,save_cost,fixed_save)):
            raise ValueError('assisted Breather uses actual Command DC12, not a voluntary saving check')
        import breather_assistance as ASSISTANCE
        return ASSISTANCE.take(engine,actor,helper,request_id=request_id,path=path,retreat_reason=retreat_reason,
            curse_origin=curse_origin,curse_reason=curse_reason,assistance=assistance)
    if assistance is not None:raise ValueError('assistance inputs require an actual assisting Trainer')
    declaration={'actor':actor,'path':deepcopy(path),'retreat_reason':retreat_reason,
        'save_dc':save_dc,'save_reason':save_reason,'save_cost':save_cost,'fixed_save':fixed_save,
        'curse_origin':curse_origin,'curse_reason':curse_reason,'helper':helper}
    if movement_mode is not None:declaration['movement_mode']=movement_mode
    if movement_options is not None:declaration['movement_options']=deepcopy(movement_options)
    records=getattr(engine,FIELD,{})
    if request_id in records:
        old=records[request_id][OBS.KEY];OBS.verify(old,declaration)
        if old['state']=='complete':return old['result']
        return _continue(engine,actor,request_id,old)
    MOVEMENT.boundary(engine,'take_breather');ACTION.ensure_resolutions_clear(engine)
    if actor.kind not in ('trainer','pokemon') or not actor.on_field or actor.captured:raise ValueError('actual participating Trainer or Pokemon required')
    if not engine.encounter_active:return C.PendingDecision('actual combat and next owner-turn boundary required')
    if not TURN.can_act(engine,actor) or not ACTION.ordinary_permission(engine,actor) or not ACTION.status_permission(engine,actor,'full'):return False
    import combat_maneuvers as MANEUVERS
    if MANEUVERS.force_attack(actor):return C.PendingDecision('Enraged actor requires an actual assisting Trainer')
    if not isinstance(actor.budget,dict) or min(actor.budget.get('standard',0),actor.budget.get('shift',0))<=0:return False
    if save_cost not in ('full','success_only') or not isinstance(save_reason,str) or not save_reason.strip():
        return C.PendingDecision('GM Breather permission-save DC and failed-save cost adjudication; prose prints no universal values')
    condition='혼란' if '혼란' in actor.conditions else None
    if save_dc is None and condition:
        save_dc=next(e['dc'] for e in engine.r.condition_effects(condition) if e.get('type')=='save')
    if save_dc is None:return C.PendingDecision('explicit GM general Breather saving DC; no universal DC is printed')
    C.integer(save_dc,'Breather saving DC',1)
    if fixed_save is not None:C.integer(fixed_save,'Breather observed saving d20',1,20)
    import condition_recovery as RECOVERY,combat_state_lifecycle as STATE,temporary_hp as TEMP
    RECOVERY.save_preflight(engine,actor,condition)
    STATE.preflight(actor);TEMP.ensure_certain(engine,actor)
    plan=_retreat(engine,actor,path,retreat_reason,movement_mode=movement_mode,movement_options=movement_options)
    if isinstance(plan,C.PendingDecision):return plan
    origin=_curse(engine,actor,curse_origin,curse_reason)
    if isinstance(origin,C.PendingDecision):return origin
    origin=_curse_retreat(actor,origin,plan)
    if isinstance(origin,C.PendingDecision):return origin
    with ACTION.resolution(engine,actor,SOURCE,kind='breather'):
        if not hasattr(engine,FIELD):setattr(engine,FIELD,{})
        records=getattr(engine,FIELD)
        if save_cost=='full' and not TURN.spend(engine,actor,'full','숨돌리기'):return False
        observation=OBS.begin(records,request_id,'take_a_breather',(actor,),declaration,{},
                              references=() if origin is None else (origin,))
        check=RECOVERY.saving_check(engine,actor,condition,save_dc,fixed=fixed_save)
        observation['observation'].update(check=check,retreat=plan,table_save_adjudication=save_reason,
                                          origin=origin,progress={},turn=_turn(engine,actor))
        if not check['passed']:
            return OBS.complete(observation,{'completed':False,'save':check,'reason':'save_failed'})
        if save_cost=='success_only' and not TURN.spend(engine,actor,'full','숨돌리기'):
            return OBS.complete(observation,{'completed':False,'save':check,'reason':'full_action_unavailable'})
        observation['observation']['phase']='retreat'
        movement=_move(engine,actor,plan,observation['observation']['progress'],retreat_reason)
        observation=getattr(engine,FIELD)[request_id][OBS.KEY]
        if movement['steps']:actor._regular_shift_movement_used=True
        if not TURN.can_act(engine,actor):
            return OBS.complete(observation,{'completed':False,'save':check,'movement':movement,'reason':'incapacitated_during_retreat'})
        if movement['steps']!=len(plan['path'])-1:
            raise ValueError('actual Breather path interrupted; paid cost and observed save cannot replay')
        return _finish(engine,actor,request_id,origin,movement=movement)
