"""Observed equipment transport over existing physical bodies and controllers."""
from copy import deepcopy
import common_checks as C,crafting_recipes as Q,state_grants as G,world_entities as W
import control_mount as M,control_vehicle as V,body_state as BODY,movement_actions as MOVE
import resolution_transaction as TX,turn as TURN
from physical_limits import number

TRANSPORT='ch05-pokemon/포켓몬-탑승하기'
SADDLE='item/안장'
SADDLES=(SADDLE,'item/안장-1')
REFS={TRANSPORT:{'file':'input/ch05-pokemon.md','sha256':'bdfb5d39fec8fede32cac615a7788301336aaceefc46079c8ed7014ea76d174b'},
      SADDLE:{'file':'input/ch09-equipment.md','sha256':'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'}}
LINK='_equipment_transport_body'
STATE='equipment_transport'


def source(rules,identity):
    selected=rules.select_source_definition(identity,source=REFS[identity])
    line=783 if identity==TRANSPORT else 81
    bounds=selected['source'].get('lines',())
    if selected['selected_id']!=identity or len(bounds)!=2 or not bounds[0]<=line<=bounds[1]:
        raise ValueError('selected equipment transport/saddle version needs its own policy')
    return selected


def saddle_definition(rules,identity,effects,header):
    if identity not in SADDLES:return effects,header
    source(rules,SADDLE)
    selected=rules.select_source_definition(identity)
    if selected['selected_id']!=identity:raise ValueError('selected saddle alias needs its own policy')
    # The conditional source is consumed only by the actual mount check below.
    return [],dict(header,price=2000)


def _body_signature(mount):
    projection=BODY.projection(mount)
    return {'species':mount.spec.get('species'),'form':mount.spec.get('form'),
            'size':mount.spec.get('size'),'height_m':projection.get('height_m'),'size_ratio':projection.get('size_ratio')}


def _saddle(engine,mount,instance_id):
    W.require_actors(engine,mount)
    if mount.kind!='pokemon':raise ValueError('actual Pokemon saddle body required')
    obj=getattr(engine,'_physical_objects',{}).get(instance_id)
    if obj is None or obj.get('item_rule_id') not in SADDLES:raise ValueError('actual saddle instance required')
    W.require_usable_object(obj)
    record=next((r for r in getattr(mount,'_item_reg',{}).values()
                 if r.get('instance_id')==instance_id and r.get('item_id')==obj['item_rule_id']),None)
    if record is None or obj.get('equipped_by')!=mount.entity_id:raise ValueError('actual currently equipped saddle required')
    return obj,record


def fit_saddle(engine,mount,instance_id,*,compatible=None,design_shape=None,observed_shape=None,reason):
    Q._text(reason);selection=source(engine.r,SADDLE);_saddle(engine,mount,instance_id)
    if compatible is None or design_shape is None or observed_shape is None:
        return C.PendingDecision('GM must observe this saddle design and actual Pokemon body-shape fit')
    if type(compatible) is not bool:raise ValueError('explicit observed compatibility boolean required')
    Q._text(design_shape);Q._text(observed_shape)
    def apply(e,c):
        obj,record=_saddle(e,c,instance_id);before=deepcopy(obj.get('saddle_fit'))
        fit={'source':selection,'mount_id':c.entity_id,'instance_id':obj['id'],'body':_body_signature(c),
             'item_selection':e.r.select_source_definition(obj['item_rule_id']),
             'design_shape':design_shape,'observed_shape':observed_shape,'compatible':compatible,'reason':reason}
        obj['saddle_fit']=dict(fit,sha256=TX.request_fingerprint(fit))
        e.gm._rec('saddle fit',before,obj['saddle_fit'],reason,c)
        return deepcopy(obj['saddle_fit'])
    return G.transition(engine,mount,apply,include_rulings=True)


def saddle_bonus(engine,rider,mount,event):
    if rider.kind!='trainer' or event not in ('boarding','damage'):return 0
    for record in getattr(mount,'_item_reg',{}).values():
        if record.get('item_id') not in SADDLES:continue
        try:obj,actual=_saddle(engine,mount,record.get('instance_id'))
        except ValueError:continue
        fit=obj.get('saddle_fit')
        if fit is None:continue
        if fit.get('sha256')!=TX.request_fingerprint({k:v for k,v in fit.items() if k!='sha256'}):raise ValueError('saddle fit observation changed')
        if fit['source']!=source(engine.r,SADDLE):raise ValueError('selected saddle fit source changed')
        if fit['item_selection']!=engine.r.select_source_definition(record['item_id']):raise ValueError('selected actual saddle definition changed')
        if actual is not record or obj.get('suppressed') or obj.get('disabled'):continue
        import equipment_suppression as SUPPRESSION
        if not SUPPRESSION.benefit_active(mount,record):continue
        if fit['compatible'] and fit['mount_id']==mount.entity_id and fit['instance_id']==obj['id'] and fit['body']==_body_signature(mount):return 3
    return 0


def is_body(row):return row.get('kind')=='physical_object' and type(row.get(STATE)) is dict and row[STATE].get('active') is True


def _signed(value):return dict(value,sha256=TX.request_fingerprint(value))
def _verify(value):
    if type(value) is not dict or value.get('sha256')!=TX.request_fingerprint({k:v for k,v in value.items() if k!='sha256'}):raise ValueError('actual transport contract changed')


def _pool_policy():
    value=M.native_declaration('곡예');value.update(id='equipment-transport/donor',source=TRANSPORT)
    return M.declaration(value)


def _state(body):
    if not is_body(body):raise ValueError('actual active equipment transport body required')
    row=body[STATE];_verify(row['contract']);return row,row['contract']


def _mass(body,row):
    return sum(number(obj.get('weight_kg'),'observed transport body/equipment weight',minimum=0) for obj in (body,*row['equipment']))+sum(number(BODY.weight_kg(c),'actual rider weight',minimum=0) for c in row['riders'])


def physical_load(actor):
    body=getattr(actor,LINK,None)
    if body is None:return 0
    row,contract=_state(body)
    if actor not in row['pokemon']:return 0
    W.require_usable_object(body)
    for obj in row['equipment']:W.require_usable_object(obj)
    if abs(_mass(body,row)-contract['physical_mass_kg'])>1e-8:raise ValueError('changed actual transport mass needs a fresh GM load observation')
    return number(contract['load_shares'][actor.entity_id],'GM observed effective transport load',minimum=0)


def independent(engine,actor):
    return getattr(actor,LINK,None) is None


def _current(engine,body):
    row,contract=_state(body)
    if contract['selection']!=source(engine.r,TRANSPORT):raise ValueError('selected transport construction source changed')
    W.require_usable_object(body)
    for obj in row['equipment']:W.require_usable_object(obj)
    if abs(_mass(body,row)-contract['physical_mass_kg'])>1e-8:raise ValueError('changed actual transport mass needs a fresh GM load observation')
    origin=W.grid_cell(body)
    for actor in (*row['pokemon'],*row['riders']):
        if actor.captured or not actor.on_field or actor.fainted:raise ValueError('current available actual transport bodies required')
        offset=contract['offsets'][actor.entity_id]
        if W.location_of(actor).get('map_id')!=W.location_of(body).get('map_id') or W.grid_cell(actor)!=(origin[0]+offset[0],origin[1]+offset[1]):
            raise ValueError('actual transport formation changed; release or observe a new construction')
    cells=set().union(*(BODY.cells(c) for c in (*row['pokemon'],*row['riders'])))
    if not {(p[0]-origin[0],p[1]-origin[1]) for p in cells}<={tuple(p) for p in contract['operation']['body']['offsets']}:
        raise ValueError('changed actual transport body no longer fits the observed footprint')
    for obj in row['equipment']:
        offset=contract['equipment_offsets'][obj['id']]
        if W.location_of(obj).get('map_id')!=W.location_of(body).get('map_id') or W.grid_cell(obj)!=(origin[0]+offset[0],origin[1]+offset[1]):
            raise ValueError('actual connecting equipment left the observed transport')
    return row,contract


def view(engine,body):
    row,contract=_current(engine,body)
    operable=not any(W.physical_lifecycle(obj)['disabled'] for obj in (body,*row['equipment']))
    return {'common_operation_adapter_available':True,'operable':operable,'machine_movement':{},
            'actual_controller_id':row['controller'].entity_id,
            'actual_occupant_ids':[c.entity_id for c in (*row['riders'],*row['pokemon'])],'actual_weapon_ids':[]}


def speed(engine,body,value):
    row,contract=_current(engine,body)
    if V._body(value)!=contract['operation']:raise ValueError('actual transport operation declaration changed')
    for actor in row['pokemon']:
        if not TURN.can_act(engine,actor):raise ValueError('actual transport Pokemon cannot move')
        M.shared_movement(engine,actor,value['movement']['mode'])
    return value['movement']['value']


def donor_path(engine,body,value,points,*,commit=False):
    row,contract=_state(body)
    remaining=[]
    for actor in row['pokemon']:
        if not commit and not TURN.movement_permission(engine,actor,equipment_transport=body):raise ValueError('actual transport Pokemon current movement permission required')
        _,policy,context=M.shared_movement(engine,actor,value['movement']['mode'])
        distance=0;diagonals=context['diagonals']
        for old,new in zip(points,points[1:]):
            step,diagonals=MOVE.step_cost(old,new,diagonals);distance+=step
            if value['movement']['mode']!='sky' and V._cells(body,value,new)&engine.grid.slow:distance+=1
        if distance>context['remaining']:raise ValueError('actual transport Pokemon shared movement distance exhausted')
        remaining.append(context['remaining']-distance)
        if commit:
            M.record_movement(engine,actor,policy,distance=distance,diagonals=diagonals)
            actor._diagonal_steps=diagonals
    return min(remaining)


def moved(engine,body,value,points):
    remaining=donor_path(engine,body,value,points,commit=True)
    row,contract=_state(body)
    origin=W.grid_cell(body)
    for obj in row['equipment']:
        dx,dy=contract['equipment_offsets'][obj['id']]
        W._set_object_location(obj,dict(body['location'],cell=(origin[0]+dx,origin[1]+dy)))
    return remaining


def assemble(engine,controller,body_id,*,pokemon=None,riders=None,equipment=None,load_shares=None,
             operation=None,trained=None,gm_permitted=None,reason):
    Q._text(reason);W.require_actors(engine,controller);selection=source(engine.r,TRANSPORT)
    if gm_permitted is not True or any(x is None for x in (pokemon,riders,equipment,load_shares,operation,trained)):
        return C.PendingDecision('GM must permit and observe actual Pokemon, connecting gear, training, riders, effective loads and transport procedure')
    if type(pokemon) not in (list,tuple) or not pokemon or type(riders) not in (list,tuple) or not riders:raise ValueError('actual transport Pokemon and riders required')
    W.require_actors(engine,*pokemon,*riders)
    actors=[*pokemon,*riders]
    if len({id(c) for c in actors})!=len(actors) or any(c.kind!='pokemon' for c in pokemon):raise ValueError('distinct actual transport Pokemon and riders required')
    if controller not in actors:raise ValueError('actual controller must have physical access to the transport')
    if trained is not True:return C.PendingDecision('GM must establish training for the actual transport Pokemon')
    if any(not M.manages(engine,c) and getattr(c,'_round_marker',None)==engine.round_no and getattr(c,'_regular_shift_movement_used',False) for c in pokemon):
        return C.PendingDecision('ordinary movement already spent without an exact shared remainder; observe the construction before movement or in a fresh round')
    if type(equipment) not in (list,tuple) or not equipment or len(set(equipment))!=len(equipment):raise ValueError('distinct actual connecting gear identities required')
    objects=getattr(engine,'_physical_objects',{});body=objects.get(body_id)
    if body is None or body.get('kind')!='physical_object':raise ValueError('actual registered sled/raft transport body required')
    gear=[objects.get(uid) for uid in equipment]
    if any(obj is None or obj is body for obj in gear):raise ValueError('actual distinct connecting equipment required')
    if is_body(body):raise ValueError('release the existing actual construction first')
    occupied={uid for other in objects.values() if is_body(other) for uid in (other['id'],*other[STATE]['contract']['equipment_ids'])}
    if body_id in occupied or set(equipment)&occupied:raise ValueError('actual equipment already belongs to another active construction')
    for obj in (body,*gear):
        W.require_usable_object(obj)
        if W.physical_lifecycle(obj)['disabled']:raise ValueError('disabled actual transport body or connecting equipment cannot assemble')
        if obj.get('carrier_id') or obj.get('equipped_by') or obj.get('telekinetic_holder_id'):raise ValueError('release carried equipment before actual assembly')
        number(obj.get('weight_kg'),'observed transport body/equipment weight',minimum=0)
    if type(load_shares) is not dict or set(load_shares)!={c.entity_id for c in pokemon}:raise ValueError('GM observed effective load share for every actual Pokemon required')
    for value in load_shares.values():number(value,'GM observed transport load share',minimum=0)
    mass=sum(obj['weight_kg'] for obj in (body,*gear))+sum(number(BODY.weight_kg(c),'actual rider weight',minimum=0) for c in riders)
    if abs(sum(load_shares.values())-mass)>1e-8:raise ValueError('observed load shares must cover the actual body, equipment and rider mass')
    value=V.declaration(operation)
    if value['source']!=TRANSPORT or value['kinds']!=['physical_object'] or value['movement']['provider']!='declared' or value['movement']['mode'] not in ('land','swim') or value['pilot']['authority']!='assigned' or value['access']!='aboard' or value['initiative']['provider']!='pilot' or value['weapons']:
        raise ValueError('explicit authored transport operation over the existing machine owner required')
    origin=W.grid_cell(body);offsets={};equipment_offsets={}
    for actual in (*actors,*gear):
        if W.location_of(actual).get('map_id')!=W.location_of(body).get('map_id'):raise ValueError('actual transport bodies must share a map')
        point=W.grid_cell(actual);offset=(point[0]-origin[0],point[1]-origin[1])
        (equipment_offsets if isinstance(actual,dict) else offsets)[actual['id'] if isinstance(actual,dict) else actual.entity_id]=offset
    occupied=set().union(*(BODY.cells(c) for c in actors))
    if not {(p[0]-origin[0],p[1]-origin[1]) for p in occupied}<={tuple(p) for p in value['body']['offsets']}:raise ValueError('observed transport footprint must include every actual Pokemon and rider body')
    if any(getattr(c,LINK,None) is not None or M.CONTRACT in c.spec or M._riders(c) for c in actors):raise ValueError('release existing mounted or equipment transport relation first')
    old=V._state(engine)['policies'].get(body_id)
    if old is not None and old['body']!=V._body(value):raise ValueError('existing shared transport procedure cannot reset by redeclaration')
    contract={'source':TRANSPORT,'selection':selection,'body_id':body_id,'pokemon_ids':[c.entity_id for c in pokemon],
              'rider_ids':[c.entity_id for c in riders],'equipment_ids':list(equipment),'controller_id':controller.entity_id,
              'load_shares':deepcopy(load_shares),'physical_mass_kg':mass,'operation':V._body(value),'offsets':offsets,
              'equipment_offsets':equipment_offsets,'reason':reason}
    def apply(e,c,*others):
        index=W.actor_index(e);actual=e._physical_objects[body_id]
        state={'contract':_signed(contract),'pokemon':[index[x] for x in contract['pokemon_ids']],
               'riders':[index[x] for x in contract['rider_ids']],
               'equipment':[e._physical_objects[x] for x in equipment],'controller':c,'active':True}
        actual[STATE]=state
        for member in (*state['pokemon'],*state['riders']):setattr(member,LINK,actual)
        for donor in state['pokemon']:
            if not M.manages(e,donor):
                policy=M._body(_pool_policy());setattr(donor,M.POOL,M._signed({'period':M._period(e,donor,policy),'policy':policy,'used':0,'diagonals':0}))
            M.shared_movement(e,donor,value['movement']['mode'])
            import capability_actions as LOAD
            LOAD.load(donor)
        operations=e.__dict__.setdefault(V.FIELD,V._state(e))
        operations['policies'].setdefault(body_id,V._sign({'body':V._body(value),'machine_id':body_id}))
        _current(e,actual);validate_world(e,index)
        e.gm._rec('equipment transport',None,{'body_id':body_id,'pokemon_ids':contract['pokemon_ids'],'rider_ids':contract['rider_ids'],'controller_id':c.entity_id},reason,c)
        return {'body_id':body_id,'pokemon_ids':contract['pokemon_ids'],'rider_ids':contract['rider_ids'],'controller_id':c.entity_id,'physical_mass_kg':mass}
    return G.transition(engine,controller,apply,participants=tuple(x for x in actors if x is not controller),include_rulings=True)


def release(engine,controller,body_id,*,reason):
    Q._text(reason);W.require_actors(engine,controller)
    body=getattr(engine,'_physical_objects',{}).get(body_id)
    if body is None:raise ValueError('actual transport body required')
    row,contract=_state(body)
    if row['controller'] is not controller:raise ValueError('actual transport controller required')
    def apply(e,c):
        actual=e._physical_objects[body_id];state,_=_state(actual)
        for member in (*state['pokemon'],*state['riders']):
            if getattr(member,LINK,None) is actual:delattr(member,LINK)
        state['active']=False
        e.gm._rec('equipment transport release',body_id,None,reason,c)
        return {'body_id':body_id,'released':True}
    return G.transition(engine,controller,apply,include_rulings=True)


def validate_world(engine,index):
    objects=getattr(engine,'_physical_objects',{})
    for body in objects.values():
        if STATE not in body:continue
        row=body[STATE];contract=row['contract'];_verify(contract)
        if contract['body_id']!=body['id'] or contract['selection']!=source(engine.r,TRANSPORT):raise ValueError('actual transport body/source changed')
        if [x.entity_id for x in row['pokemon']]!=contract['pokemon_ids'] or [x.entity_id for x in row['riders']]!=contract['rider_ids'] or row['controller'].entity_id!=contract['controller_id']:raise ValueError('actual transport actor identities changed')
        if [x['id'] for x in row['equipment']]!=contract['equipment_ids'] or any(objects.get(x['id']) is not x for x in row['equipment']):raise ValueError('actual connecting equipment aliases changed')
        for actor in (*row['pokemon'],*row['riders']):
            if index.get(actor.entity_id) is not actor:raise ValueError('actual transport participant is missing')
            if row['active'] and getattr(actor,LINK,None) is not body:raise ValueError('actual transport participant/body link changed')
        V.declaration(dict(contract['operation'],id='stored-transport'))
    for actor in index.values():
        body=getattr(actor,LINK,None)
        if body is not None and (objects.get(body.get('id')) is not body or not is_body(body) or actor not in (*body[STATE]['pokemon'],*body[STATE]['riders'])):raise ValueError('orphaned actual transport participant link')
    return True
