"""Relative declarations over the existing paid physical movement consumer.

The actor owns each paid Shift and its cell cursors. World coordinates remain
private execution data; the caller declares a direction and distance only.
"""
from copy import deepcopy
import json

import common_checks as CHECKS
import movement_actions as MOVEMENT
import root_resolution as ROOT
import survivalist_features as SURVIVALIST
import turn as TURN

KEY='_relative_shifts'
FRAME='_relative_direction_frame'
SOURCE='condition/완전-실명'


def _vector(value):
    if (not isinstance(value,(tuple,list)) or len(value) not in (2,3)
            or any(type(x)is not int or x not in (-1,0,1) for x in value) or not any(value)):
        raise ValueError('one physical grid direction per understood label required')
    return tuple(value) if len(value)==3 else (*value,0)


def observe_directions(e,a,*,directions,quickly_trip_placement,reason):
    """GM binds understood relative labels; this does not reveal a map."""
    MOVEMENT.reason(reason);ensure_clear(a)
    if type(directions)is not dict or not directions:raise ValueError('GM direction frame required')
    normalized={}
    for label,vector in directions.items():
        MOVEMENT.reason(label)
        _vector(vector)
        normalized[label]=tuple(vector)
    if quickly_trip_placement not in ('before_entry','enter_passable'):
        raise ValueError('GM must settle unspecified Quickly trip placement')
    a.spec[FRAME]={'directions':normalized,'quickly_trip_placement':quickly_trip_placement,
                   'reason':reason,'source':'gm/relative-movement-frame'}
    return {'directions':list(normalized),'quickly_trip_placement':quickly_trip_placement}


def ensure_clear(actor,*,engine=None):
    pending=[r for r in actor.spec.get(KEY,{}).values() if r['state']!='complete']
    if pending and (engine is None or getattr(engine,'_relative_mover',None)!=actor.entity_id):
        raise ValueError('finish the already paid relative Shift before another action or turn end')


def _clock(e,a):
    return [e.encounter_active,e.round_no,a.turns_taken]


def _seal(row):
    return ROOT.fingerprint({'declaration':row['declaration'],'facts':row['facts']})


def _public(row):
    return {'movement_id':row['declaration']['movement_id'],'state':row['state'],
            'distance':row['distance'],'tripped':row['tripped']}


def _complete(row):
    row['state']='complete'
    return _public(row)


def _checks(e,a,options,level):
    if level=='none':
        if options is not None:raise ValueError('blindness checks require actual impaired vision')
        return None
    if type(options)is not dict or set(options)-{'frequency','reason','check_options'}:
        raise ValueError('an explicit GM blindness check repetition policy is required')
    if options.get('frequency') not in ('once_per_shift','each_hazard_cell'):
        raise ValueError('GM must choose the unspecified blindness check repetition')
    MOVEMENT.reason(options.get('reason'))
    choices=options.get('check_options',[])
    if type(choices)is not list:raise ValueError('blindness roll option list required')
    # A pool avoids disclosing how many unseen hazard cells lie ahead. Unused
    # options are not rolled; omitted entries use the normal native dice.
    for choice in choices or [{}]:SURVIVALIST.blinded_plan(e,a,choice,allow_total=True)
    json.dumps(options,ensure_ascii=False,allow_nan=False)
    return deepcopy(options)


def _native_options(mode,vector,options):
    if mode not in MOVEMENT.MODES:raise ValueError('unknown relative movement capability')
    if mode=='land':
        if options is not None:raise ValueError('ordinary land movement has no native transfer options')
        if vector[2]:raise ValueError('land movement cannot declare an aerial direction')
        return None
    if type(options)is not dict:
        raise ValueError('relative non-land movement requires its native geometry/transfer observations')
    allowed={'reason_text'}
    if mode in ('sky','levitate','teleport'):allowed.add('gm_step_distance')
    if mode=='burrow':allowed|={'diggable','surface'}
    if mode=='teleport':allowed|={'surface_contact','sky_air_policy'}
    if set(options)-allowed:raise ValueError('only native mode observations are supported')
    MOVEMENT.reason(options.get('reason_text'))
    if mode in ('swim','burrow') and vector[2]:raise ValueError('this native movement has no altitude adapter')
    if vector[2] and any(vector[:2]) and 'gm_step_distance' not in options:
        raise ValueError('mixed vertical/horizontal movement requires an explicit GM measured segment')
    if 'gm_step_distance' in options:CHECKS.integer(options['gm_step_distance'],'GM measured relative segment',1)
    if mode=='burrow' and (type(options.get('diggable'))is not bool or type(options.get('surface'))is not bool):
        raise ValueError('explicit native diggable and surface observations required')
    if mode=='teleport' and type(options.get('surface_contact'))is not bool:
        raise ValueError('actual destination surface contact must be specified')
    json.dumps(options,ensure_ascii=False,allow_nan=False)
    return deepcopy(options)


def _native_route(a,vector,budget,options,mode):
    """Private translation only; native owners still authorize every transfer."""
    dx,dy,dz=vector;position=tuple(a.pos);height=a.spec.get('_movement_altitude',0)
    # Teleporter uses its native endpoint distance, independent of a walking
    # diagonal prefix. Other modes carry the actual physical step alternation.
    diagonals=0 if mode=='teleport' else getattr(a,'_diagonal_steps',0)
    spent=0;route=[]
    while spent<budget:
        q=(position[0]+dx,position[1]+dy);altitude=height+dz
        horizontal,next_diagonals=MOVEMENT.step_cost(position,q,diagonals)
        measured=options.get('gm_step_distance')
        cost=measured if measured is not None else max(horizontal,abs(dz))
        if cost<max(horizontal,abs(dz)):raise ValueError('GM measured segment is shorter than actual displacement')
        if spent+cost>budget:break
        if altitude<0:raise ValueError('native relative altitude cannot be below the surface')
        node={'position':q,'altitude':altitude}
        if measured is not None:node['gm_distance']=measured
        route.append(node);spent+=cost;position=q;height=altitude;diagonals=next_diagonals
    if not route:raise ValueError('declared relative movement cannot reach one native segment')
    return route,spent


def _native_preflight(e,a,mode,route,budget,options,distance):
    if mode in ('sky','levitate'):
        for node in route:MOVEMENT._aerial_height(e,a,mode,node['altitude'])
    elif mode=='burrow' and options['diggable'] is not True:
        # The native producer supplies the unresolved diggable decision. Actual
        # geometry/surface placement belongs to each attempted paid step; a
        # future blocked surface exit must not bypass Quickly's automatic trip.
        return MOVEMENT.burrow_plan(e,a,[a.pos,route[0]['position']],
            maximum_distance=budget,**options)
    elif mode=='teleport':
        parameters={k:v for k,v in options.items() if k!='gm_step_distance'}
        end=route[-1]
        return MOVEMENT.teleport_plan(e,a,end['position'],altitude=end['altitude'],
            maximum_distance=budget,gm_distance=distance if 'gm_step_distance' in options else None,**parameters)
    return None


def _resume_policy(e,a,row,options):
    if options is None:return
    previous=row.get('resumed_policy')
    if previous is not None:
        if previous['options']!=options:raise ValueError('cannot replace the resumed traversal check policy')
        return
    if row['state']=='complete' or row['facts']['checks'] is not None:
        raise ValueError('only a pending newly impaired movement needs a resumed traversal check policy')
    level,_=SURVIVALIST.vision(e,a)
    prepared=_checks(e,a,options,level)
    if prepared is None:raise ValueError('resumed traversal check policy requires actual impaired vision')
    policy={'options':prepared,'level':level,'after_check':len(row['checks']),
            'source':'gm/relative-blindness-resumption'}
    row['resumed_policy']=dict(policy,fingerprint=ROOT.fingerprint(policy))


def move(e,a,*,direction,distance,pace,movement_id,movement_mode='land',blindness_options=None,
         native_options=None,resumed_blindness_options=None):
    frame=a.spec.get(FRAME)
    if type(frame)is not dict or direction not in frame.get('directions',{}):
        raise ValueError('relative direction requires its explicit GM world translation')
    CHECKS.integer(distance,'declared relative distance',1)
    if pace not in ('slowly','quickly'):raise ValueError('explicit Slowly or Quickly required')
    MOVEMENT.reason(movement_id)
    vector=_vector(frame['directions'][direction])
    native=_native_options(movement_mode,vector,native_options)
    if e.grid is None:raise ValueError('relative movement requires the GM physical map')
    import world_entities as WORLD
    if WORLD.actor_index(e).get(a.entity_id) is not a:raise ValueError('actual relative movement actor required')
    declaration={'actor_id':a.entity_id,'movement_id':movement_id,'direction':direction,
                 'distance':distance,'pace':pace,'movement_mode':movement_mode,
                 'blindness_options':deepcopy(blindness_options)}
    if native_options is not None:declaration['native_options']=deepcopy(native_options)
    old=a.spec.get(KEY,{}).get(movement_id)
    if old is not None:
        if old['declaration']!=declaration:raise ValueError('cannot replace a paid relative Shift declaration')
        _validate(e,a,old)
        _resume_policy(e,a,old,resumed_blindness_options)
        if old['state']=='complete':return _public(old)
    else:
        if resumed_blindness_options is not None:raise ValueError('resumed traversal check policy requires an already paid Shift')
        ensure_clear(a)
        level,_=SURVIVALIST.vision(e,a)
        if level=='total' and e.r._selected_rule(SOURCE)!=SOURCE:
            raise ValueError('selected Total Blindness requires its exact source contract')
        # The source leaves placement at a hazardous attempted step unspecified.
        # The GM binds that choice. If a passable cell is actually entered, its
        # inherited DC 10 check remains real and cannot prevent automatic trip.
        automatic=level=='total' and pace=='quickly'
        stops_before=automatic and frame['quickly_trip_placement']=='before_entry'
        checks=None if stops_before else _checks(e,a,blindness_options,level)
        if stops_before and blindness_options is not None:
            raise ValueError('a stopped attempted entry performs no actual traversal check')
        budget,mode=e.move_profile(a,movement_mode,as_slowed=level=='total' and pace=='slowly')
        sprint_rate=False
        if movement_mode!='teleport' and '질주' in a.custom_conditions:
            import arithmetic_policy as M
            sprint_rate=__import__('athlete').sprint_rate(e,a)
            budget=M.increase(budget,sprint_rate,quantity='movement',base_id='current_capability',stage='sprint')
        import capability_actions as LOAD
        budget=LOAD.movement_limit(a,budget)
        budget=min(distance,budget)
        route=None;plan=None
        if movement_mode in ('sky','levitate','burrow','teleport'):
            route,native_distance=_native_route(a,vector,budget,native,movement_mode)
            plan=_native_preflight(e,a,movement_mode,route,budget,native,native_distance)
            if isinstance(plan,CHECKS.PendingDecision):return plan
        if movement_mode in ('sky','levitate'):mode=movement_mode
        facts={'origin':tuple(a.pos),'altitude':a.spec.get('_movement_altitude',0),
               'diagonals':getattr(a,'_diagonal_steps',0),'clock':_clock(e,a),
               'level':level,'mode':mode,'budget':budget,'automatic_trip':automatic,
               'checks':checks,'history_index':len(getattr(a,'_action_history',[])),
               'direction_vector':tuple(frame['directions'][direction]),
               'direction_frame':deepcopy(frame),'sprint_rate':sprint_rate}
        if native is not None:facts['native_options']=native
        if route is not None:facts['native_route']=route
        if movement_mode=='teleport':facts['transfer_plan']=plan
        row={'declaration':declaration,'facts':facts,'state':'pending','cells':[],
             'distance':0,'checks':[],'tripped':False}
        row['fingerprint']=_seal(row)
        import state_grants as GRANTS
        def pay(engine,actor):
            engine._relative_mover=actor.entity_id
            try:paid=TURN.spend(engine,actor,'shift',SOURCE,movement=True)
            finally:del engine._relative_mover
            if not paid:return False
            actor.spec.setdefault(KEY,{})[movement_id]=deepcopy(row)
            if movement_mode!='teleport' and '질주' in actor.custom_conditions:MOVEMENT.consume_sprint(actor)
            return True
        if not GRANTS.transition(e,a,pay):return False
    previous=getattr(e,'_relative_mover',None)
    e._relative_mover=a.entity_id
    try:return _continue(e,a,movement_id)
    finally:
        if previous is None:del e._relative_mover
        else:e._relative_mover=previous


def _trip(e,a,row):
    e.apply_status(a,'넘어짐')
    row['tripped']='넘어짐' in a.conditions
    return _complete(row)


def _hazard(e,a,q,mode):
    import body_state as BODY
    return (mode not in ('공중/부유','비행/부유')
            and mode not in ('sky','levitate')
            and any((p in e.grid.rough or p in e.grid.slow) and not MOVEMENT.ordinary_terrain(e,a,p)
                    for p in BODY.at_position(a,q)))


def _blocking(e,a,q,*,transfer=False):
    import body_state as BODY
    if any(p in e.grid.blocking for p in BODY.at_position(a,q)):return True
    if transfer:return False
    dx=q[0]-a.pos[0];dy=q[1]-a.pos[1]
    return any(e.grid.blocked(p,(p[0]+dx,p[1]+dy)) for p in BODY.cells(a,require_complete=True))


def _automatic(e,a,row):
    # Costs and the declared maximum are fixed when paid. Vision remains a
    # live condition: a cure during a real reaction wait ends its penalties.
    return (SURVIVALIST.vision(e,a)[0]=='total'
            and row['declaration']['pace']=='quickly')


def _check_entry(e,a,row,cell):
    if not cell['hazard']:return True
    if SURVIVALIST.vision(e,a)[0]=='none':return True
    options=row.get('resumed_policy',{}).get('options',row['facts']['checks'])
    automatic=_automatic(e,a,row)
    if options is None:
        raise ValueError('changed impaired vision requires an explicit traversal check policy')
    if options['frequency']=='once_per_shift' and row['checks']:
        if automatic:_trip(e,a,row)
        return not automatic
    ordinal=len(row['checks']);choices=options.get('check_options',[])
    choice_index=ordinal-row.get('resumed_policy',{}).get('after_check',0)
    choice=choices[choice_index] if choice_index<len(choices) else {}
    skill,opts=SURVIVALIST.blinded_plan(e,a,choice,allow_total=True)
    import skill_feature_actions as SKILLS
    if opts.get('feature') is not None:
        identity='relative:'+a.entity_id+':'+row['declaration']['movement_id']+':'+str(ordinal)
        result=SKILLS.sequence(e,identity,{'declaration':row['declaration'],'cell':cell['destination']},
            [(a,skill,opts)],lambda rolls:SKILLS.resolve_check(e,a,skill,10,rolls[0],opts))
    else:
        result=SKILLS.resolve_check(e,a,skill,10,e.skill_roll(a,skill,**opts),opts)
        SKILLS.finish(e,a,opts.get('roll_id'))
    row['checks'].append({'cell_index':len(row['cells'])-1,'skill':skill,'result':result})
    if not result.passed or automatic:
        _trip(e,a,row);return False
    return True


def _continue(e,a,identity):
    import body_state as BODY,map_terrain as TERRAIN
    row=a.spec[KEY][identity];facts=row['facts'];dx,dy,dz=_vector(facts['direction_vector'])
    native_mode=row['declaration']['movement_mode'];aerial=native_mode in ('sky','levitate')
    transfer=native_mode in ('burrow','teleport')
    while row['state']!='complete':
        cell=row['cells'][-1] if row['cells'] and row['cells'][-1]['state']!='complete' else None
        if cell is None:
            if not TURN.can_act(e,a) or not TURN.movement_permission(e,a):return _complete(row)
            number=len(row['cells'])
            if native_mode=='teleport':
                if number:return _complete(row)
                node=facts['native_route'][-1];q=node['position'];height=node['altitude']
                step=cost=facts['transfer_plan']['distance']
            elif aerial or native_mode=='burrow':
                if number>=len(facts['native_route']):return _complete(row)
                node=facts['native_route'][number];q=node['position'];height=node['altitude']
                horizontal,_=MOVEMENT.step_cost(a.pos,q,getattr(a,'_diagonal_steps',0))
                step=cost=node.get('gm_distance',max(horizontal,abs(height-a.spec.get('_movement_altitude',0))))
            else:
                q=(a.pos[0]+dx,a.pos[1]+dy);height=a.spec.get('_movement_altitude',0)
                step,_=MOVEMENT.step_cost(a.pos,q,getattr(a,'_diagonal_steps',0))
                cost=step+MOVEMENT.slow_terrain_penalty(e,a,q,facts['mode'],step=step)
            if (_automatic(e,a,row) and _hazard(e,a,q,facts['mode'])
                    and row['distance']+step<=facts['budget']
                    and (facts['direction_frame']['quickly_trip_placement']=='before_entry'
                         or row['distance']+cost>facts['budget'])):
                return _trip(e,a,row)
            if row['distance']+cost>facts['budget']:return _complete(row)
            if _automatic(e,a,row) and _blocking(e,a,q,transfer=native_mode=='burrow'):
                return _trip(e,a,row)
            cell={'destination':q,'state':'moving','progress':{},'hazard':False}
            if native_mode!='land':cell['altitude']=height
            row['cells'].append(cell)
        q=cell['destination'];progress=cell['progress']
        if cell['state']=='moving':
            # Native pending receipts precede any renewed destination decision.
            # Otherwise a changed obstruction could abandon an unresolved AoO.
            MOVEMENT._paid_receipts(e,progress)
            if not progress.get('next'):
                height=cell.get('altitude',facts['altitude'])
                if not transfer:
                    if (not e.grid.inside(q) or _blocking(e,a,q)
                            or not TERRAIN.can_travel(e,a,q,facts['mode'],altitude=height)):
                        return _trip(e,a,row) if _automatic(e,a,row) else _complete(row)
                    if not BODY.can_place(e,a,q,origin=a.pos,altitude=height):return _complete(row)
                elif (not e.grid.inside(q)
                        or any(not e.grid.inside(p) for p in BODY.at_position(a,q))):
                    return _complete(row)
                cell['hazard']=_hazard(e,a,q,facts['mode'])
                if transfer and 'plan' not in cell:
                    if native_mode=='teleport':cell['plan']=deepcopy(facts['transfer_plan'])
                    else:
                        opts=dict(facts['native_options'])
                        opts['surface']=opts['surface'] and len(row['cells'])==len(facts['native_route'])
                        cell['plan']=MOVEMENT.burrow_plan(e,a,[a.pos,q],maximum_distance=facts['budget']-row['distance'],**opts)
                        if isinstance(cell['plan'],CHECKS.PendingDecision):raise ValueError('relative paid burrow needs its actual diggable observation')
            if transfer:result=MOVEMENT.follow_paid_transfer(e,a,cell['plan'],progress=progress)
            else:
                path=[facts['native_route'][len(row['cells'])-1]] if aerial else [q]
                if native_mode=='sky':
                    MOVEMENT._paid_progress(a,path,progress)
                    # Keep the cell's own cursor; only its parent action's paid
                    # rate and already charged prefix cross the cell boundary.
                    if 'sprint_rate' in facts:progress['free_float_sprint_rate']=facts['sprint_rate']
                    import electro_shot as ELECTRO
                    charged_prefix=0
                    for prior in row['cells'][:-1]:
                        ELECTRO.validate_progress(e,a,prior['progress'])
                        charged_prefix+=prior['progress'].get('charged_distance',prior['progress']['distance'])
                    progress['free_float_distance_offset']=charged_prefix
                result=MOVEMENT.follow_paid_path(e,a,path,mode=facts['mode'],
                    maximum_distance=facts['budget']-row['distance'],progress=progress)
            row=a.spec[KEY][identity];cell=row['cells'][-1];progress=cell['progress']
            if progress.get('phase') in ('entry_pending','reaction_pending'):return _public(row)
            if not result['steps']:return _complete(row)
            row['distance']+=result['distance'];cell['state']='checking'
        # Only an actually entered cell observes a check or an automatic trip.
        # If an optional roll decision waits, its native sequence locks the roll.
        if not _check_entry(e,a,row,cell):return _public(row)
        cell['state']='complete'
    return _public(row)


def _validate(e,a,row):
    if type(row)is not dict or row.get('fingerprint')!=_seal(row):
        raise ValueError('relative Shift declaration or paid facts changed')
    d=row['declaration'];facts=row['facts']
    if (d['actor_id']!=a.entity_id or d['direction'] not in facts['direction_frame']['directions']
            or facts['direction_vector']!=facts['direction_frame']['directions'][d['direction']]
            or row['state'] not in ('pending','complete')):
        raise ValueError('relative Shift owner, direction or phase changed')
    CHECKS.integer(row['distance'],'actual relative movement distance',0,facts['budget'])
    if 'sprint_rate' in facts and facts['sprint_rate'] is not False and (type(facts['sprint_rate'])is not str or facts['sprint_rate'] not in ('0.5','1')):
        raise ValueError('actual paid relative Sprint rate required')
    policy=row.get('resumed_policy')
    if policy is not None:
        if policy.get('fingerprint')!=ROOT.fingerprint({k:v for k,v in policy.items() if k!='fingerprint'}):
            raise ValueError('resumed traversal check policy changed')
        if policy.get('source')!='gm/relative-blindness-resumption' or policy.get('level') not in ('ordinary','total'):
            raise ValueError('actual resumed impaired-vision observation required')
        CHECKS.integer(policy['after_check'],'resumed policy check prefix',0,len(row['checks']))
    total=0;charged_total=0;previous=tuple(facts['origin']);previous_height=facts['altitude'];diagonals=facts['diagonals'];dx,dy,dz=_vector(facts['direction_vector'])
    mode=d['movement_mode'];aerial=mode in ('sky','levitate');transfer=mode in ('burrow','teleport')
    for number,cell in enumerate(row['cells']):
        expected=facts['native_route'][-1]['position'] if mode=='teleport' else (previous[0]+dx,previous[1]+dy)
        if tuple(cell['destination'])!=tuple(expected):
            raise ValueError('relative Shift cell differs from its declared direction')
        height=cell.get('altitude',facts['altitude'])
        expected_height=facts['native_route'][-1]['altitude'] if mode=='teleport' else previous_height+dz
        if height!=expected_height:raise ValueError('relative Shift cell differs from its declared altitude')
        progress=cell['progress']
        if progress:
            if mode=='sky':
                if 'sprint_rate' in facts or 'free_float_distance_offset' in progress:
                    offset=CHECKS.integer(progress.get('free_float_distance_offset'),'actual parent movement charged prefix',0)
                    if offset!=charged_total:raise ValueError('relative Sky charged prefix differs from prior paid cells')
                if 'sprint_rate' in facts and (type(progress.get('free_float_sprint_rate'))is not type(facts['sprint_rate']) or progress.get('free_float_sprint_rate')!=facts['sprint_rate']):
                    raise ValueError('relative Sky lost its actual paid Sprint rate')
                horizontal,next_diagonals=MOVEMENT.step_cost(previous,cell['destination'],diagonals)
                physical=facts['native_route'][number].get('gm_distance',max(horizontal,abs(height-previous_height))) if progress.get('next') else 0
                if CHECKS.integer(progress['distance'],'actual relative Sky cell distance',0)!=physical:
                    raise ValueError('relative Sky cell distance differs from its observed native segment')
                import electro_shot as ELECTRO
                ELECTRO.validate_progress(e,a,progress)
                charged_total+=progress.get('charged_distance',physical)
                if progress.get('next'):diagonals=next_diagonals
            if transfer:
                expected_path=(previous,tuple(cell['destination']))
                path_matches=tuple(tuple(p) for p in progress['path'])==expected_path
                if cell.get('plan',{}).get('mode')!=mode or tuple(cell['plan']['path'])!=expected_path:
                    raise ValueError('relative Shift lost its native transfer plan')
                plan=cell['plan']
                if mode=='teleport':
                    if plan!=facts['transfer_plan']:raise ValueError('relative native transfer plan changed')
                else:
                    parameters=dict(facts['native_options'])
                    parameters['surface']=parameters['surface'] and number+1==len(facts['native_route'])
                    if (plan['parameters']!=parameters or plan['origin_altitude']!=previous_height
                            or not 0<plan['distance']<=plan['budget']<=facts['budget']-total):
                        raise ValueError('relative native transfer plan changed')
            elif aerial:path_matches=progress['path']==[facts['native_route'][number]]
            else:path_matches=progress['path']==[cell['destination']]
            if not path_matches or progress['next'] not in (0,1):
                raise ValueError('relative Shift paid cell path or prefix changed')
            if progress['next']:
                if tuple(progress['position'])!=tuple(cell['destination']):raise ValueError('relative paid cell position changed')
                previous=tuple(cell['destination'])
                previous_height=height
            if cell['state']!='moving':total+=progress['distance']
        if number<len(row['cells'])-1 and cell['state']!='complete':
            raise ValueError('relative movement skipped an unfinished paid cell')
    if total!=row['distance']:raise ValueError('relative movement distance differs from paid cells')
    if row['state']=='pending':
        if facts['clock']!=_clock(e,a):raise ValueError('relative Shift outlived its paid turn')
        if tuple(a.pos)!=previous or a.spec.get('_movement_altitude',0)!=previous_height:
            raise ValueError('relative Shift actor moved outside its paid prefix')
        history=getattr(a,'_action_history',[])
        if history[facts['history_index']:facts['history_index']+1]!=['shift']:
            raise ValueError('relative Shift has no actual paid Shift')


def validate_world(e,index):
    for actor in index.values():
        records=actor.spec.get(KEY,{})
        if type(records)is not dict:raise ValueError('relative Shift owner records required')
        if sum(row['state']!='complete' for row in records.values())>1:
            raise ValueError('multiple unfinished relative Shifts for one actor')
        for identity,row in records.items():
            if row['declaration']['movement_id']!=identity:raise ValueError('relative Shift identity changed')
            _validate(e,actor,row)
    return True
