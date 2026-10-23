"""Source-owned remote command routes over actual devices and connections."""
from copy import deepcopy
import common_checks as C,crafting_recipes as Q,world_entities as W,state_grants as G
import resolution_transaction as TX,perception_observe as O,perception_communicate as COMM
import skill_modifiers as SK

FIELD='_remote_control'
COMMANDS=('move','fire')
TRANSPORTS=('wired','wireless','network','communication')


def declaration(value):
    Q._fields(value,('id','source','capabilities','requirements','kinds','devices','transport','range','path','medium','commands','waivers','maximum','dependency'))
    if value['dependency']=='core_wired':
        import wired_capability as WIRED
        if _body(value)!=_body(WIRED.native()):raise ValueError('exact source-specific core Wired policy required')
        Q._text(value['id']);return deepcopy(value)
    Q._text(value['id']);Q._text(value['source']);O._names(value['capabilities'],empty=True);O._names(value['kinds']);O._names(value['commands'])
    if not set(value['kinds'])<={'vehicle','pokebot'} or not set(value['commands'])<=set(COMMANDS):raise ValueError('finite actual remote machine kinds and commands required')
    if value['transport'] not in TRANSPORTS:raise ValueError('explicit remote transport required')
    if type(value['requirements']) is not list:raise ValueError('remote qualification list required')
    for node in value['requirements']:Q._condition(node)
    route=O.native(value['source'],value['capabilities']);route.update({k:deepcopy(value[k]) for k in ('range','path','medium')});O.declaration(route)
    if type(value['devices']) is not list:raise ValueError('actual required installation declarations required')
    for device in value['devices']:
        Q._fields(device,('host','module_id','item_rule_id'))
        if device['host'] not in ('operator','machine'):raise ValueError('actual installation host role required')
        for name in ('module_id','item_rule_id'):
            if device[name] is not None:Q._text(device[name])
    Q._fields(value['waivers'],('body','pilot_requirements','weapons'))
    if any(type(v) is not bool for v in value['waivers'].values()):raise ValueError('explicit sourced interface permissions required')
    C.integer(value['maximum'],'actual remote route limit',1)
    if value['dependency'] not in ('none','network','communication','wired_projection'):raise ValueError('known remote dependency required')
    if value['transport']=='network' and value['dependency']!='network' or value['transport']=='communication' and value['dependency']!='communication':raise ValueError('remote transport must bind its actual connection dependency')
    return deepcopy(value)


def _body(value):return {k:deepcopy(v) for k,v in value.items() if k!='id'}
def _sign(row):return dict(row,sha256=TX.request_fingerprint(row))
def _verify(row):
    if type(row) is not dict or row.get('sha256')!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('remote control record changed')
def _state(e):return getattr(e,FIELD,{'version':1,'installations':{},'policies':{},'routes':{}})
def _key(left,right):return TX.request_fingerprint([left,right])


def binding(value,policy):
    Q._fields(value,('devices','avatar_id','node_id','recipient_id','communication_source','component_id'))
    O._names(value['devices'],empty=True)
    if len(value['devices'])!=len(policy['devices']):raise ValueError('one actual device per declared installation required')
    required={'network':('avatar_id','node_id'),'communication':('recipient_id','communication_source'),'wired_projection':('component_id',)}.get(policy['dependency'],())
    for name in ('avatar_id','node_id','recipient_id','communication_source','component_id'):
        if name in required:Q._text(value[name])
        elif value[name] is not None:raise ValueError('unrelated remote dependency is not an authority grant')
    return deepcopy(value)


def observe_device(e,device_id,host_id,source,installed,*,reason):
    for value in (device_id,host_id,source,reason):Q._text(value)
    Q._selected(e,source);entities=W.entity_index(e)
    if device_id not in getattr(e,'_physical_objects',{}) or host_id not in entities or device_id==host_id:raise ValueError('actual device and distinct installation host required')
    if type(installed) is not bool:raise ValueError('explicit actual installed state required')
    def apply(staged,primary):
        validate_world(staged,W.actor_index(staged));state=_state(staged);key=_key(device_id,host_id);old=state['installations'].get(key)
        row=_sign({'device_id':device_id,'host_id':host_id,'source':source,'installed':installed,'reason':reason,'at':staged.elapsed_seconds,'revision':1 if old is None else old['revision']+1})
        state['installations'][key]=row;setattr(staged,FIELD,state);boundary(staged,'device_changed');staged.gm._rec('control device installation',old,row,reason)
        return deepcopy(row)
    return G.transition(e,None,apply,include_rulings=True)


def _installed(e,operator,machine,policy,links):
    registry=getattr(e,'_physical_objects',{})
    for uid,required in zip(links['devices'],policy['devices']):
        device=registry.get(uid)
        if device is None:raise ValueError('installed remote device missing')
        W.require_usable_object(device)
        if any(W.physical_lifecycle(device)[x] for x in ('disabled','suppressed')):raise ValueError('remote device disabled or suppressed')
        host=operator.entity_id if required['host']=='operator' else machine['id'];row=_state(e)['installations'].get(_key(uid,host))
        component=next((x for x in machine.get('components',[]) if x['instance_id']==uid),None) if required['host']=='machine' else None
        augmentation=False
        if required['host']=='operator' and required['module_id']=='augmentation/datajack':
            import vehicle_native as NATIVE
            augmentation=NATIVE.installed_datajack(e,operator,uid)
            if not augmentation:raise ValueError('actual active Datajack installation required')
        if component is None and not augmentation and not (row and row['installed']):raise ValueError('actual remote device is not installed on the declared host')
        if row is not None:_verify(row);Q._selected(e,row['source'])
        if required['module_id'] is not None and not augmentation and (component is None or component.get('module_id')!=required['module_id']):raise ValueError('actual installed remote component required')
        if required['item_rule_id'] is not None and device.get('item_rule_id')!=required['item_rule_id']:raise ValueError('actual remote equipment rule required')


def _dependency(e,operator,machine,policy,links):
    kind=policy['dependency'];registry=getattr(e,'_physical_objects',{})
    if kind=='network':
        import special_entities as SPECIAL
        avatar=registry.get(links['avatar_id']);node=registry.get(links['node_id'])
        if avatar is None or avatar.get('kind')!='digital_avatar' or node is None or node.get('kind')!='digital_node':raise ValueError('actual avatar and command node required')
        SPECIAL.validate_record(e,avatar);SPECIAL.validate_record(e,node)
        if avatar['actor_id']!=operator.entity_id or avatar['network_id']!=node['network_id'] or avatar['status']!='connected' or node['status']!='connected':raise ValueError('actual avatar/node network connection lost')
        if node.get('controller_id')!=operator.entity_id or node.get('bot_id')!=machine['id']:raise ValueError('network node does not authorize this actual machine')
    elif kind=='communication':
        recipient=W.actor_index(e).get(links['recipient_id']);Q._selected(e,links['communication_source'])
        if recipient is None:raise ValueError('actual command receiver required')
        COMM.validate_world(e,W.actor_index(e));link=COMM._state(e)['connections'].get(COMM._pair(links['communication_source'],operator.entity_id,recipient.entity_id))
        if not link or link['status']!='live':raise ValueError('actual command communication connection lost')
        if recipient.entity_id not in (machine.get('owner_id'),machine.get('controller_id'),machine.get('driver_id')):raise ValueError('command receiver lacks an actual machine relation')
        value=COMM._state(e)['policies'][links['communication_source']]['declaration'];COMM._qualify(e,operator,value)
        if COMM.receiver_block(e,recipient,value) is not None or value['consent']['kind']=='willing' and not COMM._willing(e,operator,recipient,value['source']):raise ValueError('command communication receiving permission lost')
        if not COMM.L.holds(e,COMM._record(e,link)) or COMM.L._ended(e,COMM._record(e,link),'reconcile',None):raise ValueError('command communication lifetime ended')
        blocked,_=COMM._route(e,operator,recipient,value)
        if blocked is not None:raise ValueError('actual command communication path lost')
    elif kind=='wired_projection':
        component=next((x for x in machine.get('components',[]) if x['instance_id']==links['component_id'] and x.get('module_id')=='wired_core'),None)
        if machine['kind']!='pokebot' or component is None or component.get('choice',{}).get('controller_id')!=operator.entity_id:raise ValueError('actual installed wired core/controller relation required')
        if not {SK.key(x) for x in G.effective_capabilities(operator)} & {SK.key(x) for x in ('접속','capability/접속','Wired')}:raise ValueError('current wired interface capability required')


def _failure(e,row,*,skip_machine=False):
    policy=row['policy'];operator=W.actor_index(e).get(row['operator_id']);machine=getattr(e,'_physical_objects',{}).get(row['machine_id'])
    try:
        Q._selected(e,policy['source'])
        if operator is None or machine is None or machine.get('kind') not in policy['kinds']:raise ValueError('actual remote participants missing')
        if not operator.on_field or operator.captured or operator.fainted:raise ValueError('actual remote operator unavailable')
        if policy['capabilities'] and not {SK.key(x) for x in G.effective_capabilities(operator)} & {SK.key(x) for x in policy['capabilities']}:raise ValueError('remote capability source lost')
        if policy['dependency']=='core_wired':
            import wired_capability as WIRED
            WIRED.require_connection(e,operator,machine,row['binding']);return None
        if not all([Q._observe(e,operator,node,set()) for node in policy['requirements']]):raise ValueError('remote qualification lost')
        _installed(e,operator,machine,policy,row['binding']);_dependency(e,operator,machine,policy,row['binding'])
        route=O.native(policy['source'],policy['capabilities']);route.update({k:deepcopy(policy[k]) for k in ('range','path','medium')})
        _,_,blocked=O.route(e,operator,machine,route)
        if blocked is not None:raise ValueError('remote path '+blocked['reason'])
        if not skip_machine:
            import control_vehicle as V
            V._machine(e,machine['id'])
        elif machine.get('destroyed') or machine.get('hp',0)<=0:raise ValueError('actual remote machine inoperable')
    except (ValueError,KeyError,TypeError) as exc:return str(exc)
    return None


def _close(e,row,reason):
    row.pop('sha256',None);row.update(status='closed',ended_at=e.elapsed_seconds,ending=reason);row['sha256']=TX.request_fingerprint(row)


def has_routes(e):return any(row['status']=='live' for row in _state(e)['routes'].values())


def boundary(e,event,actor=None):
    for row in _state(e)['routes'].values():
        _verify(row)
        if row['status']=='live':
            reason=_failure(e,row)
            if reason is not None:_close(e,row,reason)
    if 'wired' in _state(e):
        import wired_capability as WIRED
        WIRED.sync(e)


def refresh(e):
    if not has_routes(e):return
    def apply(staged,primary):validate_world(staged,W.actor_index(staged));boundary(staged,'reconcile')
    return G.transition(e,None,apply)


def connect(e,operator,machine_id,value,links,*,route_id,connected,reason):
    value=declaration(value);links=binding(links,value);W.require_actors(e,operator);Q._text(route_id);Q._text(machine_id);Q._text(reason)
    if connected is not True:raise ValueError('actual established connection observation required')
    validate_world(e,W.actor_index(e))
    def apply(staged,c):
        state=_state(staged);boundary(staged,'reconcile');key=_key(c.entity_id,value['source']);policy=state['policies'].get(key)
        if policy is not None and policy['body']!=_body(value):raise ValueError('new declaration name cannot change remote source policy')
        previous=state['routes'].get(route_id)
        if previous is not None:
            if previous['operator_id']!=c.entity_id or previous['machine_id']!=machine_id or previous['policy']!=_body(value) or previous['binding']!=links:raise ValueError('remote route identity changed')
            if previous['status']!='live':raise ValueError('closed route requires a new actual connection identity')
            return deepcopy(previous)
        row={'operator_id':c.entity_id,'machine_id':machine_id,'policy':_body(value),'binding':links,'status':'live','opened_at':staged.elapsed_seconds,'reason':reason,'ended_at':None,'ending':None}
        failed=_failure(staged,row)
        if failed is not None:raise ValueError(failed)
        if value['maximum'] is not None and sum(x['status']=='live' and x['operator_id']==c.entity_id and x['policy']['source']==value['source'] for x in state['routes'].values())>=value['maximum']:raise ValueError('actual remote connection limit exhausted')
        state['policies'].setdefault(key,_sign({'operator_id':c.entity_id,'source':value['source'],'body':_body(value)}));state['routes'][route_id]=_sign(row);setattr(staged,FIELD,state)
        boundary(staged,'connected')
        validate_world(staged,W.actor_index(staged));return deepcopy(state['routes'][route_id])
    return G.transition(e,operator,apply)


def disconnect(e,operator,route_id,*,reason):
    W.require_actors(e,operator);Q._text(route_id);Q._text(reason)
    def apply(staged,c):
        validate_world(staged,W.actor_index(staged));row=_state(staged)['routes'].get(route_id)
        if row is None or row['operator_id']!=c.entity_id:raise ValueError('actual operator route required')
        if row['status']=='live':_close(staged,row,reason)
        boundary(staged,'disconnected')
        return deepcopy(row)
    return G.transition(e,operator,apply)


def permission(e,operator,machine_id,route_id,command=None):
    W.require_actors(e,operator);Q._text(route_id);validate_world(e,W.actor_index(e));row=_state(e)['routes'].get(route_id)
    if row is None or row['operator_id']!=operator.entity_id or row['machine_id']!=machine_id:raise ValueError('remote route does not control this actual machine/operator')
    if row['status']!='live':raise ValueError('actual remote connection closed: '+str(row['ending']))
    failed=_failure(e,row)
    if failed is not None:raise ValueError(failed)
    if command is not None and command not in row['policy']['commands']:raise ValueError('command exceeds this actual remote route')
    if command=='fire' and not row['policy']['waivers']['weapons']:raise ValueError('remote interface has no installed weapon permission')
    return deepcopy(row['policy']['waivers'])


def routes(e,operator):
    W.require_actors(e,operator);refresh(e)
    return {uid:deepcopy(row) for uid,row in _state(e)['routes'].items() if row['operator_id']==operator.entity_id}


def wired_routes(e,machine,controller_id):
    if machine.get('destroyed') or machine.get('hp',0)<=0:return []
    return [uid for uid,row in _state(e)['routes'].items() if row['status']=='live' and row['operator_id']==controller_id and row['machine_id']==machine['id'] and row['policy']['dependency']=='wired_projection' and _failure(e,row,skip_machine=True) is None]


def motion_permission(e,operator,machine,route_id,points,occupants):
    permission(e,operator,machine['id'],route_id,'move');policy=_state(e)['routes'][route_id]['policy'];reach=policy['range']
    if policy['path'] is not None or policy['medium']:
        raise ValueError('moving endpoint needs explicit future remote path/medium observations')
    if reach is None or operator in occupants:return
    location=W.effective_location(e,operator);target=W.location_of(machine)
    if location['kind']!='grid' or location.get('map_id')!=target.get('map_id'):raise ValueError('actual remote movement range unknown')
    for point in points:
        delta=[abs(location['cell'][i]-point[i]) for i in (0,1)]
        distance=max(delta) if reach['metric']=='chebyshev' else sum(x*x for x in delta)**.5
        if distance>reach['maximum']:raise ValueError('machine path would lose its actual remote connection range')


def native_wired_vehicle():
    return {'id':'native:wired-vehicle','source':'supp-polygon/차량-제작-가이드라인','capabilities':['접속','capability/접속','Wired'],
        'requirements':[],'kinds':['vehicle'],'devices':[{'host':'machine','module_id':None,'item_rule_id':None}],
        'transport':'wired','range':None,'path':None,'medium':[],'commands':['move','fire'],
        'waivers':{'body':True,'pilot_requirements':True,'weapons':True},'maximum':1,'dependency':'none'}


def connect_wired_vehicle(e,pokemon,machine_id,electronics_id,**observation):
    W.require_actors(e,pokemon)
    if pokemon.kind!='pokemon':raise ValueError('native Wired vehicle exception requires an actual Pokemon')
    links={'devices':[electronics_id],'avatar_id':None,'node_id':None,'recipient_id':None,'communication_source':None,'component_id':None}
    return connect(e,pokemon,machine_id,native_wired_vehicle(),links,**observation)


def validate_world(e,index):
    state=_state(e);Q._fields(state,('version','installations','policies','routes')+(('wired',) if 'wired' in state else ()))
    if state['version']!=1 or any(type(state[x]) is not dict for x in ('installations','policies','routes')):raise ValueError('known remote control state required')
    entities=W.entity_index(e)
    for key,row in state['installations'].items():
        _verify(row);Q._fields(row,('device_id','host_id','source','installed','reason','at','revision','sha256'));Q._text(row['source']);Q._text(row['reason'])
        if key!=_key(row['device_id'],row['host_id']) or row['device_id'] not in getattr(e,'_physical_objects',{}) or row['host_id'] not in entities or type(row['installed']) is not bool:raise ValueError('actual remote installation evidence required')
        C.integer(row['at'],'remote installation time',0,e.elapsed_seconds);C.integer(row['revision'],'installation revision',1)
    for key,row in state['policies'].items():
        _verify(row);Q._fields(row,('operator_id','source','body','sha256'));declaration(dict(row['body'],id='stored'))
        if row['operator_id'] not in index or key!=_key(row['operator_id'],row['source']) or row['body']['source']!=row['source']:raise ValueError('remote policy actual owner required')
    for uid,row in state['routes'].items():
        Q._text(uid);_verify(row);Q._fields(row,('operator_id','machine_id','policy','binding','status','opened_at','reason','ended_at','ending','sha256'))
        policy=declaration(dict(row['policy'],id='stored'));binding(row['binding'],policy);Q._text(row['reason'])
        stored=state['policies'].get(_key(row['operator_id'],policy['source']))
        if row['operator_id'] not in index or row['machine_id'] not in entities or stored is None or stored['body']!=row['policy']:raise ValueError('remote route actual participants/policy required')
        C.integer(row['opened_at'],'remote connection time',0,e.elapsed_seconds)
        if row['status']=='closed':C.integer(row['ended_at'],'remote disconnection time',row['opened_at'],e.elapsed_seconds);Q._text(row['ending'])
        elif row['status']!='live' or row['ended_at'] is not None or row['ending'] is not None:raise ValueError('explicit current remote connection state required')
    for row in state['policies'].values():
        if row['body']['maximum'] is not None and sum(x['status']=='live' and x['operator_id']==row['operator_id'] and x['policy']['source']==row['source'] for x in state['routes'].values())>row['body']['maximum']:raise ValueError('remote source connection limit exceeded')
    if 'wired' in state:
        import wired_capability as WIRED
        WIRED.validate_world(e,index)
    return True
