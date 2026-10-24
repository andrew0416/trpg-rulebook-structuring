"""C09-088: native ball-like item attacks and recipient-owned family immunity.

Status presence, status immunity, stock and attack resolution retain their native
owners. Only the chemical family's one-hour immunity lives here. A blocked
follow-up does not start a new exposure or extend the original hour.
"""
from copy import copy
from dataclasses import replace
import common_checks as C
import elapsed_time as TIME
import equipment_item_contracts as ITEMS
import resolution_transaction as TX

VARIANTS={
    'item/오물탄-격노':'난동', 'item/오물탄-혼란':'혼란',
    'item/오물탄-화상':'화상', 'item/오물탄-독':'독',
    'item/오물탄-마비':'마비', 'item/오물탄-잠듦':'잠듦',
}
GENERIC=('item/오물탄','item/오물탄-1')
SOURCES=(*GENERIC,*VARIANTS)
KEY='pester_ball_immunity'
DURATION=3600
SOURCE_SHA256='b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'


def definition(rules, source):
    if source not in SOURCES:raise ValueError('exact Pester Ball source required')
    effects,header=rules.item_effects(source)
    chapter=rules.selection.units[ITEMS.BATTLE_TOOL_SOURCE]['source']
    status=VARIANTS.get(source,'chosen (난동/혼란/화상/독/마비/잠듦)')
    expected=[{'type':'item_attack','throw':'like poke ball',
               'effects':[{'type':'apply_status','status':status,'target':'target'}],
               'consumable':True},
              {'type':'rule','note':'적중당한 대상은 1시간 오물탄 면역'}]
    if (header.get('id')!=source or rules._selected_rule(source)!=source
            or effects!=expected or chapter.get('sha256')!=SOURCE_SHA256
            or chapter.get('file')!='ch09-equipment.md'
            or header.get('battle_tool',{}).get('stock_policy')!='single_use'
            or source!='item/오물탄' and header.get('price')!=350):
        raise ValueError('selected Pester Ball definition needs its reviewed adapter')
    return header


def throw_policy(rules):
    # Reuse just the throw declaration. Capture eligibility and capture-rate
    # arithmetic are unrelated to throwing a chemical ball at an actual actor.
    value=rules.mech('pokemon/capture-rate').get('throw')
    if (type(value) is not dict or value.get('action')!='standard'
            or value.get('class')!='변화' or value.get('range')!='4 + athletics_rank'):
        raise ValueError('selected ball throw requires a reviewed Pester Ball adapter')
    C.integer(value.get('ac'),'ball throw accuracy',0)
    return value


def attack(rules, source):
    value=throw_policy(rules)
    # Chemicals have no printed elemental type. Ball-like supplies the native
    # throwing action, accuracy and range; it does not assign an elemental type.
    return {'id':source,'name':'오물탄','class':value['class'],'type':None,
            'ac':value['ac'],'range':'원거리, 대상1','keywords':[]}


def _cannon(engine, r):
    if r.held_selection is None:return None
    import item_stock as STOCK,csv_item_physical_contracts as PHYSICAL
    stock=STOCK.prepare(engine,r.user,r.source_id,held_selection=r.held_selection)
    loaded=[obj['id'] for obj in getattr(engine,'_physical_objects',{}).values()
            if obj.get(PHYSICAL.OBJECT_STATE,{}).get('loaded_ball_instance_id')==stock['instance_id']]
    if not loaded:return None
    if len(loaded)!=1:raise ValueError('Pester Ball needs one actual loading Cannon')
    profile=PHYSICAL.cannon_profile(engine,r.user,loaded[0],projectile='pester_ball')
    return dict(profile,instance_id=loaded[0])


def _signed(value):
    return dict(value,sha256=TX.request_fingerprint(value))


def _auth(value,fields,label):
    if (type(value) is not dict or set(value)!=set(fields)|{'sha256'}
            or value['sha256']!=TX.request_fingerprint({k:v for k,v in value.items() if k!='sha256'})):
        raise ValueError(label+' changed')


def validate_actor(actor):
    state=actor.spec.get(KEY)
    if state is None:return []
    if type(state) is not dict or set(state)!={'episodes'} or type(state['episodes']) is not list or not state['episodes']:
        raise ValueError('actual Pester Ball exposure history required')
    for serial,row in enumerate(state['episodes'],1):
        if type(row) is not dict or set(row)!={'id','origin','observations'} or row['id']!=actor.entity_id+':pester:'+str(serial):
            raise ValueError('Pester Ball exposure identity changed')
        origin=row['origin']
        _auth(origin,('source','status','user_id','target_id','payment_id','natural','at','unknown_index'),'Pester Ball hit origin')
        if (origin['source'] not in VARIANTS or origin['status']!=VARIANTS[origin['source']]
                or origin['target_id']!=actor.entity_id or origin['user_id']==actor.entity_id
                or not isinstance(origin['user_id'],str) or not origin['user_id']
                or not isinstance(origin['payment_id'],str) or not origin['payment_id']):
            raise ValueError('actual Pester Ball variant, target and payer required')
        C.integer(origin['natural'],'actual Pester Ball hit d20',2,20)
        C.integer(origin['at'],'Pester Ball hit time',0)
        C.integer(origin['unknown_index'],'Pester Ball original interval index',0)
        definition(actor.r,origin['source'])
        if type(row['observations']) is not list:raise ValueError('Pester Ball elapsed observations must be a list')
        for observation in row['observations']:
            _auth(observation,('at','unknown_index','seconds','reason'),'Pester Ball elapsed observation')
            for field in ('at','unknown_index','seconds'):C.integer(observation[field],'Pester Ball observation '+field,0)
            if not isinstance(observation['reason'],str) or not observation['reason'].strip():raise ValueError('actual Pester Ball elapsed observation reason required')
    return state['episodes']


def _bounds(engine,row):
    origin=row['origin'];anchor=origin['at'];index=origin['unknown_index'];base=0
    for observation in row['observations']:
        if observation['at']>engine.elapsed_seconds or observation['unknown_index']>len(engine.unresolved_time_intervals):
            raise ValueError('Pester Ball elapsed observation is in the future')
        historical=copy(engine);historical.elapsed_seconds=observation['at']
        historical.unresolved_time_intervals=engine.unresolved_time_intervals[:observation['unknown_index']]
        low,high=TIME.bounds(historical,anchor,index,base,label='Pester Ball observation clock')
        if not low<=observation['seconds']<=high:raise ValueError('Pester Ball observation exceeds its actual elapsed bounds')
        anchor,index,base=observation['at'],observation['unknown_index'],observation['seconds']
    return TIME.bounds(engine,anchor,index,base,label='Pester Ball immunity clock')


def projection(engine,target):
    rows=validate_actor(target)
    if not rows:return {'immune':False,'elapsed_bounds':None,'episode_id':None}
    row=rows[-1];low,high=_bounds(engine,row)
    return {'immune':False if low>=DURATION else True if high<DURATION else None,
            'elapsed_bounds':[low,high],'episode_id':row['id']}


def validate_world(engine,index):
    import consumption_execution as PAID
    for target in index.values():
        previous=None
        for row in validate_actor(target):
            origin=row['origin'];_bounds(engine,row)
            payer=index.get(origin['user_id'])
            if payer is None:raise ValueError('actual Pester Ball payer is missing')
            receipt=PAID.validate(payer).get(origin['payment_id'])
            if (receipt is None or receipt['at']!=origin['at'] or receipt['target_id']!=target.entity_id
                    or receipt['outcome']!='applied' or receipt['item_stock'].get('item_id')!=origin['source']
                    or receipt['item_stock'].get('count')!=1
                    or {'kind':KEY,'id':row['id']} not in receipt['results']):
                raise ValueError('Pester Ball immunity needs its original actual paid hit')
            if previous is not None:
                historical=copy(engine);historical.elapsed_seconds=origin['at']
                historical.unresolved_time_intervals=engine.unresolved_time_intervals[:origin['unknown_index']]
                # Previous observations after this exposure are impossible.
                if _bounds(historical,previous)[0]<DURATION:raise ValueError('Pester Ball immunity cannot overlap or refresh')
            previous=row
    return True


def observe_elapsed(engine,target,seconds,*,reason):
    """Explicit GM observation resolves bounded partial-round uncertainty."""
    import world_entities as W,state_grants as G
    W.require_actors(engine,target)
    view=projection(engine,target)
    if view['elapsed_bounds'] is None:raise ValueError('actual Pester Ball exposure required')
    C.integer(seconds,'observed Pester Ball elapsed seconds',0)
    if not view['elapsed_bounds'][0]<=seconds<=view['elapsed_bounds'][1]:raise ValueError('observed Pester Ball time is outside its elapsed bounds')
    W._text(reason,'Pester Ball elapsed observation reason')
    def apply(e,c):
        row=validate_actor(c)[-1]
        row['observations'].append(_signed({'at':e.elapsed_seconds,'unknown_index':len(e.unresolved_time_intervals),'seconds':seconds,'reason':reason}))
        validate_world(e,W.actor_index(e))
        e.gm._rec('Pester Ball elapsed observation',view,projection(e,c),reason,c)
        return projection(e,c)
    return G.transition(engine,target,apply)


def prepare(engine,r):
    import world_entities as W,body_state as B,capability_actions as CAP
    import confusion_attacks as CONFUSION,item_stock as STOCK,dream_state as DREAM
    definition(engine.r,r.source_id);throw_policy(engine.r)
    if r.source_id in GENERIC:
        return C.PendingDecision('Select the actual manufactured Pester Ball variant',basis={'source':r.source_id,'variants':dict(VARIANTS)})
    if (r.free or r.count!=1 or any(x is not None for x in
            (r.duration_minutes,r.duration_reason,r.food_policy,r.selected_move,r.container_selection,r.shell_batch_id))):
        raise ValueError('Pester Ball needs one actual ball-like Standard throw')
    if r.fixed_accuracy is not None:C.integer(r.fixed_accuracy,'Pester Ball accuracy d20',1,20)
    W.require_actors(engine,r.user,r.target)
    if (r.user is r.target or r.user.kind!='trainer' or not r.user.on_field or not r.target.on_field
            or r.target.captured or r.target.dead):raise ValueError('actual trainer thrower and distinct on-field target required')
    if engine.grid is None:return C.PendingDecision('Pester Ball throwing needs actual mapped range and path')
    cannon=_cannon(engine,r)
    maximum=cannon['range_m'] if cannon is not None else CAP.throwing_range(engine,r.user,category='poke_ball')
    if not B.in_range(engine,r.user,r.target,maximum):
        raise ValueError('Pester Ball target exceeds actual ball throwing range or path')
    if engine.encounter_active and (r.user.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(r.user)):raise ValueError('heavy-injury Standard item attack needs reviewed action composition')
    validate_world(engine,W.actor_index(engine))
    if projection(engine,r.target)['immune'] is None:
        return C.PendingDecision('Observe actual elapsed Pester Ball immunity time before another throw',basis=projection(engine,r.target))
    DREAM.validate(r.target)
    move=attack(engine.r,r.source_id);CONFUSION.preflight(engine,r.user,move)
    # Validate every native accuracy dependency before payment or RNG. This is
    # preparation only; native accuracy_check still owns the actual observation.
    engine._prepare_accuracy_context(r.user,r.target,move,fixed_roll=r.fixed_accuracy,
                                     situational=cannon['accuracy_bonus'] if cannon is not None else 0)
    STOCK.prepare(engine,r.user,r.source_id,held_selection=r.held_selection)


def consume(engine,r):
    import state_grants as G,action_lifecycle as ACTION
    def apply(e,user,target):
        request=replace(r,user=user,target=target)
        with ACTION.resolution(e,user,r.source_id,kind='item_attack'):
            return _consume(e,request)
    # No roll/decision escapes before commit; failures restore the whole graph,
    # including exact physical stock, status callbacks, RNG, trace and rulings.
    return G.transition(engine,r.user,apply,participants=(r.target,),include_rulings=True)


def _consume(engine,r):
    import item_stock as STOCK,consumption_execution as PAID,turn as TURN
    import confusion_attacks as CONFUSION,precise_actions as PRECISE,world_entities as W
    stock=STOCK.prepare(engine,r.user,r.source_id,held_selection=r.held_selection)
    cannon=_cannon(engine,r)
    if not TURN.spend(engine,r.user,'standard','오물탄'):return (0,0)
    if cannon is not None:
        import csv_item_physical_contracts as PHYSICAL
        PHYSICAL.fire_cannon(engine,r.user,cannon['instance_id'],
                             ball_instance_id=cannon['ball_instance_id'],projectile='pester_ball')
    payment=STOCK.debit(engine,r.user,stock)
    move=attack(engine.r,r.source_id);CONFUSION.observe_action(engine,r.user,move)
    event=PRECISE.attacked(engine,r.user,r.target,move,producer='item_attack')
    hit,natural,_=engine.accuracy_check(r.user,r.target,move,fixed_roll=r.fixed_accuracy,
                                      situational=cannon['accuracy_bonus'] if cannon is not None else 0)
    PRECISE.accuracy(event,hit)
    if hit and cannon is not None:
        damage,faces=engine.roll_expr(cannon['fixed_damage'])
        engine.take_damage(r.target,damage)
        cannon['damage']={'expression':'2d6','faces':faces,'requested':damage}
    prior=projection(engine,r.target)['immune'];applied=False;row=None
    if hit and not prior:
        if cannon is None or not (r.target.fainted or r.target.dead):
            applied=bool(engine.apply_status(r.target,VARIANTS[r.source_id],source=r.source_id,applied_by=r.user))
        receipt=next(value for value in PAID.validate(r.user).values() if value['item_stock'] is payment)
        rows=r.target.spec.setdefault(KEY,{'episodes':[]})['episodes']
        row={'id':r.target.entity_id+':pester:'+str(len(rows)+1),
             'origin':_signed({'source':r.source_id,'status':VARIANTS[r.source_id],
                 'user_id':r.user.entity_id,'target_id':r.target.entity_id,'payment_id':receipt['receipt_id'],
                 'natural':natural,'at':engine.elapsed_seconds,'unknown_index':len(engine.unresolved_time_intervals)}),
             'observations':[]}
        rows.append(row)
    PAID.finish(r.user,payment,target_id=r.target.entity_id,outcome='applied' if row else 'no_effect',
                results=[{'kind':KEY,'id':row['id']}] if row else [])
    burst=__import__('researcher_fields').pester_hit(engine,r.user,r.target,r.source_id,hit=hit,status_applied=applied)
    validate_world(engine,W.actor_index(engine))
    result={'source':r.source_id,'target_id':r.target.entity_id,'hit':hit,'natural':natural,
            'status_applied':applied,'family_immune_before':prior,'immunity_started':row is not None,'payment':payment,'chemical_warfare':burst}
    if cannon is not None:result['cannon']=cannon
    engine.log('    Pester Ball: '+('miss' if not hit else 'family immune' if prior else 'status applied' if applied else 'hit without new status'),r.source_id)
    return result
