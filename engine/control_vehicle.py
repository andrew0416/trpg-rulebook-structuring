"""Actual machine commands over selected bodies, operators and shared budgets.

Weapon check/damage values are authored inputs, not guessed vehicle move stats.
Ordinary machine state remains in the existing special-entity registry.
"""
from copy import deepcopy
from dataclasses import asdict
import common_checks as C,crafting_recipes as Q,world_entities as W,state_grants as G
import special_entities as S,body_state as BODY,movement_actions as MOVE,turn as TURN
import roll_context as R,resolution_transaction as TX,initiative_derivation as INIT

FIELD='_machine_operations'
KINDS=('vehicle','pokebot','physical_object')


def declaration(value):
    Q._fields(value,('id','source','kinds','pilot','access','body','movement','initiative','actions','weapons','concurrent'))
    Q._text(value['id']);Q._text(value['source']);Q._names(value['kinds'])
    if not set(value['kinds'])<=set(KINDS):raise ValueError('vehicle or Pokebot body policy required')
    pilot=value['pilot'];Q._fields(pilot,('authority','requirements'))
    if pilot['authority'] not in ('assigned','owner','gm'):raise ValueError('actual pilot authority required')
    _requirements(pilot['requirements'])
    if value['access'] not in ('aboard','adjacent','gm'):raise ValueError('explicit actual machine access required')
    body=value['body'];Q._fields(body,('offsets','maximum_occupants'))
    if type(body['offsets']) is not list or not body['offsets']:raise ValueError('observed machine footprint required')
    cells=[MOVE._point(x) for x in body['offsets']]
    if len(set(cells))!=len(cells) or (0,0) not in cells:raise ValueError('distinct machine footprint including anchor required')
    if body['maximum_occupants'] is not None:C.integer(body['maximum_occupants'],'machine occupants',1)
    movement=value['movement'];Q._fields(movement,('provider','mode','value','maximum','action','override','check'))
    if movement['provider'] not in ('machine','pilot','declared') or movement['mode'] not in ('land','swim','levitate','sky'):raise ValueError('explicit actual machine movement basis required')
    if movement['provider']=='declared':C.integer(movement['value'],'authored movement',0)
    elif movement['value'] is not None:raise ValueError('actual movement does not also take a fabricated value')
    if movement['maximum'] is not None:C.integer(movement['maximum'],'machine movement cap',0)
    _action(movement['action'])
    if movement['override'] is not None:
        Q._fields(movement['override'],('condition','action'));Q._condition(movement['override']['condition']);_action(movement['override']['action'])
    _check(movement['check'])
    initiative=value['initiative'];Q._fields(initiative,('provider','value','procedure'))
    if initiative['provider'] not in ('driver','pilot','machine','declared'):raise ValueError('explicit initiative basis required')
    if initiative['provider']=='declared':C.integer(initiative['value'],'authored machine initiative')
    elif initiative['value'] is not None:raise ValueError('actual initiative does not also take a supplied total')
    if initiative['procedure'] is not None and type(initiative['procedure']) is not dict:raise ValueError('native initiative composition procedure required')
    actions=value['actions'];Q._fields(actions,('standard','shift','swift','share_with_operator'))
    for kind in ('standard','shift','swift'):C.integer(actions[kind],'shared '+kind+' limit',0)
    if type(actions['share_with_operator']) is not bool:raise ValueError('explicit operator action sharing required')
    if type(value['weapons']) is not list:raise ValueError('explicit installed weapon declarations required')
    ids=[]
    for weapon in value['weapons']:
        Q._fields(weapon,('id','source','authority','requirements','action','range','check','damage'))
        Q._text(weapon['id']);Q._text(weapon['source']);ids.append(weapon['id']);_action(weapon['action']);_requirements(weapon['requirements']);_check(weapon['check'])
        if weapon['authority'] not in ('pilot','occupant','owner','gm'):raise ValueError('actual weapon operator authority required')
        Q._fields(weapon['range'],('metric','maximum'))
        if weapon['range']['metric'] not in ('chebyshev','euclidean'):raise ValueError('declared machine weapon range metric required')
        C.integer(weapon['range']['maximum'],'machine weapon range',0)
        Q._fields(weapon['damage'],('kind','amount'))
        if weapon['damage']['kind'] not in ('attack_damage','hp_loss'):raise ValueError('explicit sourced weapon result kind required')
        C.integer(weapon['damage']['amount'],'authored weapon amount',0)
    if len(set(ids))!=len(ids):raise ValueError('distinct installed weapon identities required')
    if value['concurrent'] is not None:Q._condition(value['concurrent'])
    return deepcopy(value)


def _requirements(nodes):
    if type(nodes) is not list:raise ValueError('explicit qualification list required')
    for node in nodes:Q._condition(node)


def _action(kind):
    if kind not in ('standard','shift','swift'):raise ValueError('explicit finite machine action required')


def _check(value):
    if value is None:return
    Q._fields(value,('skill','dc','purpose'));Q._text(value['skill']);Q._text(value['purpose']);C.integer(value['dc'],'machine check DC',0)


def _body(value):return {k:deepcopy(v) for k,v in value.items() if k!='id'}
def _sign(row):return dict(row,sha256=TX.request_fingerprint(row))
def _verify(row):
    if type(row) is not dict or row.get('sha256')!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('machine execution record changed')


def body_view(row,projection=None):
    if row['kind']=='vehicle':
        operable=not row['destroyed'] and row['hp']>0 and row['breaches']<row['breach_capacity']
        movement={'land':row['overland']}
        if row.get('native_vehicle') is not None:
            import vehicle_native as NATIVE
            # The exact template/upgrade values are validated by special_entities.
            movement=NATIVE._derived(NATIVE.policy_for_body(row),row['native_vehicle']['config'])['movement']
        controller=row.get('driver_id');occupants=list(row['passenger_ids']);weapons=list(row['weapon_ids'])
    else:
        operable=not row['destroyed'] and row['hp']>0;movement=deepcopy((projection or {})['movement'])
        controller=row.get('controller_id');occupants=[];weapons=[c['instance_id'] for c in row['components'] if c.get('module_id') in ('basic_combat','advanced_combat','sympathetic_drive')]
    return {'common_operation_adapter_available':True,'operable':operable,'machine_movement':movement,
            'actual_controller_id':controller,'actual_occupant_ids':occupants,'actual_weapon_ids':weapons}


def _machine(engine,identity):
    Q._text(identity);row=getattr(engine,'_physical_objects',{}).get(identity)
    if row is None or row.get('kind') not in KINDS:raise ValueError('actual registered vehicle or Pokebot required')
    if row['kind']=='physical_object':
        import equipped_transport_saddle as EQUIPMENT
        view=EQUIPMENT.view(engine,row)
    else:view=S.validate_record(engine,row)
    if not view['operable']:raise ValueError('disabled, destroyed or over-capacity machine cannot act')
    return row,view


def _state(engine):
    state=getattr(engine,FIELD,None)
    return {'version':1,'policies':{},'budgets':{},'requests':{}} if state is None else state


def _occupants(engine,row,view,value):
    index=W.actor_index(engine);occupants=[index[uid] for uid in view['actual_occupant_ids']]
    maximum=value['body']['maximum_occupants']
    if maximum is not None and len(occupants)>maximum:raise ValueError('actual machine occupancy exceeds declared capacity')
    return occupants


def _cells(row,value,position=None):
    origin=W.grid_cell(row) if position is None else position
    return {(origin[0]+dx,origin[1]+dy) for dx,dy in value['body']['offsets']}


def occupied_cells(engine,except_actor=None,*,altitude=0):
    if altitude!=0:return set()
    result=set();identity=None if except_actor is None else except_actor.entity_id
    for row in getattr(engine,'_physical_objects',{}).values():
        if row.get('kind') not in KINDS or W.location_of(row)['kind']!='grid':continue
        if row['kind']=='physical_object':
            import equipped_transport_saddle as EQUIPMENT
            if not EQUIPMENT.is_body(row):continue
            if except_actor is not None and getattr(except_actor,EQUIPMENT.LINK,None) is row:continue
        if identity in row.get('passenger_ids',[]):continue
        if except_actor is not None and W.location_of(row).get('map_id')!=W.location_of(except_actor).get('map_id'):continue
        policy=_state(engine)['policies'].get(row['id'])
        if policy is not None:_verify(policy);result.update(_cells(row,policy['body']))
        else:result.add(tuple(W.grid_cell(row)))
    return result


def _speed(engine,pilot,row,view,value):
    policy=value['movement'];provider=policy['provider']
    if row['kind']=='physical_object':
        import equipped_transport_saddle as EQUIPMENT
        speed=EQUIPMENT.speed(engine,row,value)
        return speed if policy['maximum'] is None else min(speed,policy['maximum'])
    if row.get('native_vehicle') is not None and not engine.encounter_active:
        raise ValueError('native template speed is combat maneuverability; travel needs an authored speed')
    if provider=='machine':speed=view['machine_movement'].get(policy['mode'])
    elif provider=='pilot':speed=MOVE.distance_budget(engine,pilot,policy['mode'])
    else:speed=policy['value']
    if type(speed) is not int or speed<0:raise ValueError('machine movement is unresolved under the selected source; explicit authored basis required')
    return speed if policy['maximum'] is None else min(speed,policy['maximum'])


def _initiative(engine,pilot,row,value):
    policy=value['initiative'];provider=policy['provider']
    if provider=='declared':return {'value':policy['value'],'provider':'declared','source':value['source']}
    if provider=='machine':
        if row['kind']!='pokebot':raise ValueError('vehicle has no Speed stat; select actual driver initiative')
        result=INIT.derive(row['stats']['spe'],[],policy['procedure']);return dict(result,provider='machine',subject_id=row['id'])
    subject=row if provider=='driver' else pilot
    result=engine.initiative_value(subject,procedure=policy['procedure'])
    if result.value is None:raise ValueError('actual machine initiative unresolved: '+str(result.unresolved))
    return {'value':result.value,'provider':provider,'derivation':deepcopy(result.derivation)}


def context(engine,operator,identity,value,*,body_eligible,reason,gm_authorized=False,weapon_id=None,remote_route=None,command=None):
    value=declaration(value);W.require_actors(engine,operator);Q._selected(engine,value['source']);Q._text(reason)
    remote=None
    if remote_route is not None:
        import control_remote as REMOTE
        remote=REMOTE.permission(engine,operator,identity,remote_route,command or ('fire' if weapon_id is not None else None))
    if body_eligible is not True and not (remote and remote['body']):raise ValueError('actual appropriate control body must be established')
    if type(gm_authorized) is not bool:raise ValueError('explicit GM authority boolean required')
    if not operator.on_field or operator.captured or operator.fainted:raise ValueError('available actual machine operator required')
    row,view=_machine(engine,identity)
    if row['kind'] not in value['kinds']:raise ValueError('machine kind is outside declared control permission')
    occupants=_occupants(engine,row,view,value);index=W.actor_index(engine)
    if occupants:
        cells=_cells(row,value)
        if any(W.location_of(c).get('map_id')!=row['location'].get('map_id') or tuple(W.grid_cell(c)) not in cells for c in occupants):raise ValueError('actual passenger bodies must be inside the machine')
    authority=value['pilot']['authority'];requirements=value['pilot']['requirements'];weapon=None
    if weapon_id is not None:
        weapon=next((x for x in value['weapons'] if x['id']==weapon_id),None)
        if weapon is None or weapon_id not in view['actual_weapon_ids']:raise ValueError('actual installed and declared machine weapon required')
        Q._selected(engine,weapon['source']);requirements=weapon['requirements'];authority={'pilot':'assigned','occupant':'occupant'}.get(weapon['authority'],weapon['authority'])
    permitted=operator.entity_id==view['actual_controller_id'] if authority=='assigned' else operator.entity_id==row.get('owner_id') if authority=='owner' else operator in occupants if authority=='occupant' else gm_authorized
    if weapon is not None and remote and remote['weapons'] and operator.entity_id==view['actual_controller_id']:permitted=True
    if not permitted:raise ValueError('actual operator lacks declared machine authority')
    import vehicle_native as NATIVE
    trained=row['kind']=='vehicle' and value['source']==NATIVE.SOURCE and weapon_id is None and NATIVE.training_permission(engine,operator)
    if row['kind']=='vehicle' and operator.kind=='pokemon' and value['source']==NATIVE.SOURCE and remote is None and not trained:
        raise ValueError('actual Pokemon Vehicle Training or a live interface route required')
    if not trained and not (remote and remote['pilot_requirements'] and weapon_id is None) and not all([Q._observe(engine,operator,node,set()) for node in requirements]):raise ValueError('actual machine control qualification required')
    if remote is not None:pass
    elif value['access']=='aboard':
        if operator not in occupants or tuple(W.grid_cell(operator)) not in _cells(row,value):raise ValueError('actual operator must be aboard the machine')
    elif value['access']=='adjacent':
        distance=W.distance_known(operator,row)
        if distance is None or distance>1:raise ValueError('actual local machine access required')
    elif not gm_authorized:raise ValueError('GM must establish the independent physical control route')
    state=_state(engine);policy=state['policies'].get(identity)
    if policy is not None:
        _verify(policy)
        if policy['body']!=_body(value):raise ValueError('a new declaration ID cannot change the shared machine policy')
    pilot=index.get(view['actual_controller_id'])
    if pilot is None:
        if row['kind']=='vehicle' or weapon_id is not None:raise ValueError('actual machine pilot relation required')
        pilot=operator
    return {'machine':row,'view':view,'pilot':pilot,'occupants':occupants,'weapon':weapon,
            'speed':_speed(engine,pilot,row,view,value),'initiative':_initiative(engine,pilot,row,value)}


def _period(engine):return {'round':engine.round_no,'encounter':engine.encounter_active}


def _budget(engine,identity,value):
    old=_state(engine)['budgets'].get(identity)
    if old is not None and old['period']==_period(engine):_verify(old);return deepcopy(old)
    return _sign({'period':_period(engine),'actions':{x:0 for x in ('standard','shift','swift')},'distance':0,'diagonals':0,'operators':{},'body':_body(value)})


def _place(engine,row,value,point,origin,occupants):
    if engine.grid is None:raise ValueError('actual mapped machine body required')
    cells=_cells(row,value,point)
    if any(not engine.grid.inside(p) or p in engine.grid.blocking for p in cells):raise ValueError('machine whole body meets blocking terrain or map edge')
    if any(engine.grid.wall_blocked((origin[0]+dx,origin[1]+dy),(point[0]+dx,point[1]+dy)) for dx,dy in value['body']['offsets']):raise ValueError('machine body cannot cross actual wall')
    excluded={id(c) for c in occupants}
    for actor in W.actor_index(engine).values():
        if id(actor) in excluded or not actor.on_field or actor.captured:continue
        if cells & BODY.cells(actor):raise ValueError('machine body overlaps another actual actor')
    for other in getattr(engine,'_physical_objects',{}).values():
        if other is row or other.get('kind') not in KINDS:continue
        if other['kind']=='physical_object':
            import equipped_transport_saddle as EQUIPMENT
            if not EQUIPMENT.is_body(other):continue
        if W.distance_known(row,other) is None:continue
        policy=_state(engine)['policies'].get(other['id'])
        occupied=_cells(other,dict(policy['body'],id='stored')) if policy else {tuple(W.grid_cell(other))}
        if cells & occupied:raise ValueError('machine body overlaps another actual machine')
    return cells


def _path(engine,ctx,value,path,budget):
    if type(path) not in (list,tuple) or len(path)<2:raise ValueError('explicit actual machine path required')
    points=[MOVE._point(x) for x in path];row=ctx['machine']
    if points[0]!=tuple(W.grid_cell(row)):raise ValueError('machine path must begin at actual current location')
    distance=0;diagonals=budget['diagonals']
    for old,new in zip(points,points[1:]):
        if not (0<max(abs(old[i]-new[i]) for i in (0,1))<=1):raise ValueError('continuous adjacent machine path required')
        cells=_place(engine,row,value,new,old,ctx['occupants'])
        step,diagonals=MOVE.step_cost(old,new,diagonals);distance+=step
        if value['movement']['mode']!='sky' and cells & engine.grid.slow:distance+=1
    if distance+budget['distance']>ctx['speed']:raise ValueError('shared machine movement distance exhausted')
    if row['kind']=='physical_object':
        import equipped_transport_saddle as EQUIPMENT
        EQUIPMENT.donor_path(engine,row,value,points)
    return points,distance,diagonals


def _range(engine,row,target,weapon):
    a=W.location_of(row);b=W.location_of(target)
    if a['kind']!='grid' or b['kind']!='grid' or a.get('map_id')!=b.get('map_id'):raise ValueError('actual machine and target positions required')
    origin=a['cell'];cells=BODY.cells(target);maximum=weapon['range']['maximum']
    within=any(max(abs(origin[i]-p[i]) for i in (0,1))<=maximum if weapon['range']['metric']=='chebyshev' else sum((origin[i]-p[i])**2 for i in (0,1))<=maximum**2 for p in cells)
    if not within or engine.grid is None or all(engine.grid.blocked(origin,p) for p in cells):raise ValueError('actual installed weapon range or path is blocked')


def operate(engine,operator,identity,value,*,command,request_id,body_eligible,reason,path=None,weapon_id=None,target=None,roll_options=None,gm_authorized=False,remote_route=None):
    value=declaration(value);Q._text(request_id);Q._text(reason);W.require_actors(engine,operator)
    if command not in ('move','fire'):raise ValueError('declared machine move or installed weapon command required')
    if command=='move' and (target is not None or weapon_id is not None):raise ValueError('movement does not also select a weapon target')
    if command=='fire' and (target is None or path is not None or weapon_id is None):raise ValueError('installed weapon and actual target required')
    if target is not None:W.require_actors(engine,target)
    options={} if roll_options is None else deepcopy(roll_options)
    if type(options) is not dict:raise ValueError('native machine check options required')
    if remote_route is not None:
        import control_remote as REMOTE
        REMOTE.refresh(engine)
    intent={'operator':operator.entity_id,'machine':identity,'declaration':_body(value),'command':command,'path':path,'weapon':weapon_id,'remote_route':remote_route,
            'target':None if target is None else target.entity_id,'body_eligible':body_eligible,'reason':reason,'gm_authorized':gm_authorized,'roll_options':options}
    fingerprint=TX.request_fingerprint(intent);validate_world(engine,W.actor_index(engine));saved=_state(engine)['requests'].get(request_id)
    if saved is not None:
        if saved['fingerprint']!=fingerprint:raise ValueError('machine request identity has changed intent')
        return deepcopy(saved['result'])
    context(engine,operator,identity,value,body_eligible=body_eligible,reason=reason,gm_authorized=gm_authorized,weapon_id=weapon_id,remote_route=remote_route,command=command)
    def apply(e,c,*targets):
        actual_target=targets[0] if targets else None
        ctx=context(e,c,identity,value,body_eligible=body_eligible,reason=reason,gm_authorized=gm_authorized,weapon_id=weapon_id,remote_route=remote_route,command=command);row=ctx['machine'];budget=_budget(e,identity,value)
        policy=value['movement'] if command=='move' else ctx['weapon'];action=policy['action'];check=policy['check']
        if command=='move' and policy['override'] is not None and Q._observe(e,c,policy['override']['condition'],set()):action=policy['override']['action']
        previous=budget['operators'].get(c.entity_id,[])
        if previous and command not in previous and (value['concurrent'] is None or not Q._observe(e,c,value['concurrent'],set())):raise ValueError('concurrent moving and firing requires an eligible operator or separate gunner')
        if budget['actions'][action]>=value['actions'][action]:raise ValueError('actual machine shared action limit exhausted')
        planned=None
        if command=='move':planned=_path(e,ctx,value,path,budget)
        else:_range(e,row,actual_target,ctx['weapon'])
        if command=='move' and remote_route is not None:REMOTE.motion_permission(e,c,row,remote_route,planned[0],ctx['occupants'])
        if not TURN.can_act(e,c):raise ValueError('current operator cannot act')
        if check is None and options:raise ValueError('a check-free machine command does not consume roll resources')
        if check is not None:R.plan(e,c,check['skill'],purpose=check['purpose'],target=actual_target,**options)
        if value['actions']['share_with_operator'] and not TURN.spend(e,c,action,'machine '+command,movement=False):return C.PendingDecision('actual operator action unavailable')
        budget['actions'][action]+=1;budget['operators'].setdefault(c.entity_id,[]).append(command)
        roll=None if check is None else C.against_dc(e.skill_roll(c,check['skill'],skill_target=actual_target,**options),check['dc'])
        passed=roll is None or roll.passed
        result={'machine_id':identity,'operator_id':c.entity_id,'command':command,'source':value['source'],'passed':passed,'action':action,
                'check':None if roll is None else asdict(roll),'initiative':ctx['initiative'],'at':e.elapsed_seconds,'round':e.round_no}
        if passed and command=='move':
            points,distance,diagonals=planned;origin=points[0]
            for point in points[1:]:
                W._set_object_location(row,dict(row['location'],cell=point))
                for occupant in ctx['occupants']:
                    offset=(occupant.pos[0]-origin[0],occupant.pos[1]-origin[1]);occupant.pos=(point[0]+offset[0],point[1]+offset[1])
                origin=point
            budget['distance']+=distance;budget['diagonals']=diagonals;result.update(path=points,distance=distance,remaining=ctx['speed']-budget['distance'],position=row['location']['cell'])
            if row['kind']=='physical_object':
                import equipped_transport_saddle as EQUIPMENT
                result['remaining']=min(result['remaining'],EQUIPMENT.moved(e,row,value,points))
        elif passed:
            damage=ctx['weapon']['damage'];before=actual_target.hp
            if damage['kind']=='attack_damage':e.take_damage(actual_target,damage['amount'])
            else:
                import attack_damage_history as HISTORY
                HISTORY.received_loss(e,actual_target,damage['amount'],source=ctx['weapon']['source'])
            result.update(weapon_id=weapon_id,target_id=actual_target.entity_id,damage_kind=damage['kind'],before=before,after=actual_target.hp)
        state=e.__dict__.setdefault(FIELD,_state(e));state['policies'].setdefault(identity,_sign({'body':_body(value),'machine_id':identity}))
        state['budgets'][identity]=_sign({k:v for k,v in budget.items() if k!='sha256'})
        state['requests'][request_id]=_sign({'fingerprint':fingerprint,'intent':deepcopy(intent),'result':deepcopy(result)})
        if remote_route is not None:REMOTE.boundary(e,'machine_command')
        validate_world(e,W.actor_index(e));return result
    return G.transition(engine,operator,apply,participants=() if target is None else (target,))


def validate_world(engine,index):
    state=_state(engine);Q._fields(state,('version','policies','budgets','requests'))
    if state['version']!=1:raise ValueError('known machine state version required')
    for name in ('policies','budgets','requests'):
        if type(state[name]) is not dict:raise ValueError('machine state mappings required')
    for identity,policy in state['policies'].items():
        _verify(policy);Q._fields(policy,('body','machine_id','sha256'));value=declaration(dict(policy['body'],id='stored'));Q._selected(engine,value['source'])
        row=getattr(engine,'_physical_objects',{}).get(identity)
        if policy['machine_id']!=identity or row is None or row.get('kind') not in value['kinds']:raise ValueError('actual machine policy body missing')
        if row['kind']!='physical_object':S.validate_record(engine,row)
    for identity,budget in state['budgets'].items():
        _verify(budget);Q._fields(budget,('period','actions','distance','diagonals','operators','body','sha256'))
        if identity not in state['policies'] or budget['body']!=state['policies'][identity]['body']:raise ValueError('shared machine policy and budget disagree')
        Q._fields(budget['period'],('round','encounter'));C.integer(budget['period']['round'],'machine budget round',0,engine.round_no)
        if type(budget['period']['encounter']) is not bool:raise ValueError('actual encounter scope required')
        Q._fields(budget['actions'],('standard','shift','swift'))
        for kind,used in budget['actions'].items():C.integer(used,'used shared machine '+kind,0,budget['body']['actions'][kind])
        C.integer(budget['distance'],'used shared machine distance',0);C.integer(budget['diagonals'],'machine diagonals',0)
        if type(budget['operators']) is not dict:raise ValueError('actual machine operator usage required')
        for uid,commands in budget['operators'].items():
            if uid not in index or type(commands) is not list or any(x not in ('move','fire') for x in commands):raise ValueError('actual machine operator command history required')
    for request,row in state['requests'].items():
        Q._text(request);_verify(row);Q._fields(row,('fingerprint','intent','result','sha256'))
        if row['fingerprint']!=TX.request_fingerprint(row['intent']):raise ValueError('machine request intent changed')
        result=row['result'];intent=row['intent']
        if intent['operator'] not in index or intent['machine'] not in state['policies'] or result['machine_id']!=intent['machine'] or result['operator_id']!=intent['operator'] or result['command']!=intent['command']:raise ValueError('machine result identity changed')
        C.integer(result['at'],'machine execution time',0,engine.elapsed_seconds);C.integer(result['round'],'machine execution round',0,engine.round_no)
    import equipped_transport_saddle as EQUIPMENT
    EQUIPMENT.validate_world(engine,index)
    return True


def describe_context(engine,operator,identity,value,**observations):
    import equipped_transport_saddle as EQUIPMENT
    EQUIPMENT.validate_world(engine,W.actor_index(engine))
    ctx=context(engine,operator,identity,value,**observations)
    return {'machine_id':identity,'operator_id':operator.entity_id,'pilot_id':ctx['pilot'].entity_id,
            'control_permission_checked':True,'speed':ctx['speed'],'initiative':deepcopy(ctx['initiative']),
            'occupant_ids':[c.entity_id for c in ctx['occupants']],'state_view':deepcopy(ctx['view'])}
