"""C09-012: actual spray use, wild admission and native attempted retreat.

Nearby and a fastest feasible route are observed world facts. They are never a
new radius, encounter probability, extra action or automatic escape success.
"""
from copy import deepcopy
import common_checks as C
import consumption_execution as PAID
import elapsed_time as ELAPSED
import item_stock as STOCK
import state_grants as G
import turn as TURN
import world_entities as WORLD
import root_resolution as ROOT

SOURCE_REF={'file':'input/ch09-equipment.md','sha256':'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'}
SOURCES={'item/벌레회피스프레이':(3600,15,200),'item/실버스프레이':(7200,25,300),'item/골드스프레이':(18000,35,400)}
KEY='repel_uses'
FLEE='_repel_flee_declaration'


def _seal(row):
    row['fingerprint']=ROOT.fingerprint({k:v for k,v in row.items() if k!='fingerprint'})
    return row


def _verify(row):
    if row.get('fingerprint')!=ROOT.fingerprint({k:v for k,v in row.items() if k!='fingerprint'}):
        raise ValueError('actual Repel observation changed')


def _text(value,label):
    if type(value) is not str or not value.strip():raise ValueError(label+' required')
    return value


def definition(rules,source):
    from source_context import verified_source
    if source not in SOURCES:raise ValueError('reviewed Repel source required')
    if 'C09-012' in rules.ruleset.unit_versions:raise ValueError('selected Repel prose version requires review')
    rules.ruleset.require({'id':'C09-012','source':{'file':'ch09-equipment.md','lines':[100,108]}})
    selected=rules.select_source_definition(source)
    if selected['selected_id']!=source:raise ValueError('selected Repel source needs its own policy')
    verified_source(rules,SOURCE_REF,label='Repels')
    duration,level,price=SOURCES[source]
    effects,header=rules.item_effects(source)
    if header.get('id')!=source or header.get('price')!=price:
        raise ValueError('selected Repel price/source changed')
    expected={'type':'rule','note':f'{duration//3600}시간, {level}레벨 이하 야생 포켓몬 퇴치'}
    if effects!=[expected]:raise ValueError('selected Repel effect needs review against its full prose')
    return {'duration':duration,'maximum_level':level,'price':price}


def _present(e,actor):
    WORLD.require_actors(e,actor)
    if not actor.on_field or actor.captured or actor.dead or actor.fainted:
        raise ValueError('actual conscious on-field spray participant required')


def attack(r):
    # The prose specifies AC6/Status, but no elemental type or metric range.
    return {'id':r.source_id,'name':r.item_name,'class':'변화','type':None,'ac':6,'keywords':[]}


def prepare(e,r):
    definition(e.r,r.source_id);_present(e,r.user);_present(e,r.target)
    if r.free or r.count!=1 or r.resumable or any(x is not None for x in
            (r.duration_minutes,r.duration_reason,r.food_policy,r.selected_move,
             r.container_selection,r.shell_batch_id,r.request_id,r.source_selection)):
        raise ValueError('one actual Repel application without a timing override required')
    direct=r.target is not r.user
    if direct and r.target.kind!='pokemon':raise ValueError('direct Repel target must be a Pokemon')
    if not direct and r.fixed_accuracy is not None:raise ValueError('self spray has no attack roll')
    if r.fixed_accuracy is not None:C.integer(r.fixed_accuracy,'Repel accuracy d20',1,20)
    STOCK.prepare(e,r.user,r.source_id,held_selection=r.held_selection)
    if r.aim is None:
        return C.PendingDecision('Observe the actual spray application/reach; source prints no metric range',basis={'source':r.source_id,'direct':direct})
    expected={'reason','reachable'} if direct else {'reason'}
    if type(r.aim) is not dict or set(r.aim)!=expected:
        raise ValueError('actual spray application reason and direct reach observation required')
    _text(r.aim['reason'],'actual spray application reason')
    if direct:
        if r.aim['reachable'] is not True:raise ValueError('actual reachable direct spray target required')
        import body_modes as BODY,confusion_attacks as CONFUSION
        BODY.require_targetable(r.target)
        if e.encounter_active and (r.user.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(r.user)):raise ValueError('heavy-injury Repel attack needs native action composition')
        CONFUSION.preflight(e,r.user,attack(r))
        import invisibility_state as INV,blender_state as BLEND,effects_ext as EXT
        INV.accuracy_penalty(e,r.target);BLEND.evasion(e,r.target,attack(r));EXT.validate_combat_edges(e,r.user)


def consume(e,r):
    import action_lifecycle as ACTION
    direct=r.target is not r.user
    with ACTION.resolution(e,r.user,r.source_id,kind='item_attack' if direct else 'repel_use'):
        stock=STOCK.prepare(e,r.user,r.source_id,held_selection=r.held_selection)
        if not direct:
            return G.transition(e,r.user,lambda se,user:_record(se,user,user,r,
                STOCK.debit(se,user,stock),hit=True,natural=None))
        def pay(se,user):
            if not TURN.spend(se,user,'standard',r.source_id):return None
            return STOCK.debit(se,user,stock)
        payment=G.transition(e,r.user,pay)
        if payment is None:return (0,0)
        import confusion_attacks as CONFUSION,precise_actions as PRECISE
        move=attack(r);CONFUSION.observe_action(e,r.user,move)
        event=PRECISE.attacked(e,r.user,r.target,move,producer='item_attack')
        hit,natural,_=e.accuracy_check(r.user,r.target,move,fixed_roll=r.fixed_accuracy)
        PRECISE.accuracy(event,hit)
        # A known attack roll and its real payment remain observable on a miss.
        paid_id=next(uid for uid,row in PAID.validate(r.user).items() if row['item_stock'] is payment)
        return G.transition(e,r.user,lambda se,user,target:_record(se,user,target,r,
            PAID.validate(user)[paid_id]['item_stock'],hit=hit,natural=natural),participants=(r.target,))


def _record(e,user,target,r,payment,*,hit,natural):
    direct=target is not user
    rows=user.spec.setdefault(KEY,{})
    identity=user.entity_id+':repel:'+str(len(rows)+1)
    record={'id':identity,'source':r.source_id,'user_id':user.entity_id,
            'target_id':target.entity_id,'mode':'direct' if direct else 'self',
            'at':e.elapsed_seconds,'unknown_index':len(e.unresolved_time_intervals),
            'hit':bool(hit),'natural':natural,'target_level':target.level,
            'affected':bool(hit and (not direct or target.level<=SOURCES[r.source_id][1])),
            'reason':r.aim['reason'],'approaches':{}}
    rows[identity]=record
    __import__('researcher_fields').spray_exposure(e,user,target,r.source_id,hit=direct and bool(hit))
    receipt=PAID.finish(user,payment,target_id=target.entity_id,
        outcome='applied' if record['affected'] else 'no_effect',
        results=[{'kind':'repel_use','id':identity}])
    record['payment_id']=receipt['receipt_id']
    return deepcopy(_seal(record))


def _live(e,row):
    _verify(row)
    profile=definition(e.r,row['source'])
    if not row['affected']:return False
    low,high=ELAPSED.bounds(e,row['at'],row['unknown_index'],0,label='Repel elapsed time')
    if low>=profile['duration']:return False
    if high>=profile['duration']:
        return C.PendingDecision('Observe actual elapsed time at the Repel expiry boundary',basis={'application_id':row['id'],'elapsed_bounds':[low,high]})
    return bool(row['affected'])


def _applications(e):
    for user in WORLD.actor_index(e).values():
        for row in user.spec.get(KEY,{}).values():yield user,row


def _speeds(e,target):
    import movement_actions as MOVE
    return {mode:MOVE.distance_budget(e,target,mode) for mode,value in MOVE.capabilities(e,target).items() if mode in MOVE.MODES and value>0}


def _self_effect(e,wearer,target):
    pending=None
    for row in wearer.spec.get(KEY,{}).values():
        if row['mode']!='self' or target.level>SOURCES[row['source']][1]:continue
        live=_live(e,row)
        if live is True:return row
        if isinstance(live,C.PendingDecision):pending=live
    return pending


def admit(e,wearer,candidates,*,nearby,reason):
    """Consume an actual local encounter list; suppressed bodies stay off field."""
    WORLD.require_actors(e,wearer);_text(reason,'GM actual encounter neighborhood reason')
    candidates=list(candidates)
    if len({id(x) for x in candidates})!=len(candidates):raise ValueError('distinct actual wild candidates required')
    if type(nearby) is not dict or set(nearby)!={x.entity_id for x in candidates} or any(type(x) is not bool for x in nearby.values()):
        raise ValueError('actual nearby observation for every candidate required')
    import wild_equipment as WILD
    blocked=[];allowed=[]
    for target in candidates:
        WILD._wild(e,target)
        row=_self_effect(e,wearer,target) if nearby[target.entity_id] else None
        if isinstance(row,C.PendingDecision):return row
        (blocked if row else allowed).append(target)
    def apply(se,sw,*subjects):
        for target in subjects:
            target.on_field=target.entity_id not in {x.entity_id for x in blocked}
        se.gm._rec('Repel actual wild admission',[x.entity_id for x in subjects],[x.entity_id for x in allowed],reason,sw)
        return {'admitted':[x.entity_id for x in allowed],'suppressed':[x.entity_id for x in blocked]}
    return G.transition(e,wearer,apply,participants=candidates,include_rulings=True)


def approach(e,wearer,target,*,nearby,reason):
    """Actual near approach event creates a live flee obligation, not a query flag."""
    WORLD.require_actors(e,wearer);_present(e,target);_text(reason,'GM actual close approach reason')
    import wild_equipment as WILD
    WILD._wild(e,target)
    if type(nearby) is not bool:raise ValueError('actual near approach observation required')
    row=_self_effect(e,wearer,target) if nearby else None
    if isinstance(row,C.PendingDecision):return row
    def apply(se,sw,st):
        if row is None:
            for application in sw.spec.get(KEY,{}).values():
                if application['mode']=='self':
                    application['approaches'].pop(st.entity_id,None);_seal(application)
            return {'status':'unaffected'}
        sw.spec[KEY][row['id']]['approaches'][st.entity_id]={'at':se.elapsed_seconds,'reason':reason}
        _seal(sw.spec[KEY][row['id']])
        return {'status':'must_flee','application_id':row['id'],'target_id':st.entity_id}
    return G.transition(e,wearer,apply,participants=(target,))


def intent(e,target):
    if target.kind!='pokemon' or not target.on_field or target.captured or target.dead or target.fainted:return None
    pending=None
    for user,row in _applications(e):
        if (row['mode']=='direct' and row['target_id']==target.entity_id or
                row['mode']=='self' and target.entity_id in row['approaches']):
            if target.level>SOURCES[row['source']][1]:continue
            if row['mode']=='self':
                import wild_equipment as WILD
                try:WILD._wild(e,target)
                except ValueError:continue
            live=_live(e,row)
            if isinstance(live,C.PendingDecision):pending=live
            elif live:return {'application_id':row['id'],'repeller_id':user.entity_id,'source':row['source']}
    return pending


def continuation(target):
    """A paid native Shift must finish even after the odor obligation ends."""
    import relative_movement as RELATIVE
    observed=target.spec.get(FLEE)
    if observed is None:return None
    _verify(observed)
    paid=target.spec.get(RELATIVE.KEY,{}).get(observed['movement'].get('movement_id'))
    return observed if paid is not None and paid['state']=='pending' else None


def observe_flee(e,target,*,movement,reason,limited_reason=None,departed=False,departure_reason=None,departure_position=None):
    """GM supplies its fastest feasible retreat; native movement owns feasibility."""
    _present(e,target);_text(reason,'GM fastest feasible retreat observation')
    current=intent(e,target)
    if isinstance(current,C.PendingDecision):return current
    if current is None:raise ValueError('actual live Repel flee obligation required')
    if type(movement) is not dict or set(movement)-{'direction','distance','pace','movement_id','movement_mode','blindness_options','native_options','resumed_blindness_options'}:
        raise ValueError('actual native relative retreat declaration required')
    C.integer(movement.get('distance'),'actual positive attempted flee distance',1)
    if limited_reason is not None:_text(limited_reason,'GM limiting terrain/condition reason')
    if type(departed) is not bool:raise ValueError('explicit actual departure observation required')
    if departed:
        _text(departure_reason,'actual encounter departure reason')
        from movement_actions import _point
        departure_position=_point(departure_position)
    elif departure_reason is not None or departure_position is not None:raise ValueError('departure evidence requires actual departure')
    import relative_movement as RELATIVE,movement_actions as MOVE
    old=target.spec.get(FLEE)
    if old is not None and old['movement'].get('movement_id') in target.spec.get(RELATIVE.KEY,{}):
        raise ValueError('finish the already paid Repel retreat before replacing its declaration')
    if movement.get('movement_id') in target.spec.get(RELATIVE.KEY,{}):raise ValueError('fresh actual Repel retreat movement identity required')
    frame=target.spec.get(RELATIVE.FRAME,{})
    vector=frame.get('directions',{}).get(movement.get('direction'))
    if vector is None:raise ValueError('actual understood flee direction frame required')
    repeller=WORLD.actor_index(e)[current['repeller_id']]
    toward=sum(vector[i]*(target.pos[i]-repeller.pos[i]) for i in (0,1))<0
    speeds=_speeds(e,target)
    chosen=speeds.get(movement.get('movement_mode','land'),0)
    if not chosen:raise ValueError('actual available native flee capability required')
    if (toward or movement.get('pace')!='quickly' or chosen<max(speeds.values()) or movement['distance']<chosen) and limited_reason is None:
        raise ValueError('shorter/slower/detoured flee needs actual fastest-feasible limitation evidence')
    target.spec[FLEE]=_seal({'intent':current,'movement':deepcopy(movement),'origin':target.pos,
        'repeller_position':repeller.pos,'speeds':speeds,'direction_vector':vector,'reason':reason,'limited_reason':limited_reason,
        'departed':departed,'departure_reason':departure_reason,'departure_position':departure_position})
    return deepcopy(target.spec[FLEE])


def flee(e,target):
    import relative_movement as RELATIVE
    observed=target.spec.get(FLEE)
    if observed is not None:_verify(observed)
    paid=None if observed is None else target.spec.get(RELATIVE.KEY,{}).get(observed['movement'].get('movement_id'))
    current=observed['intent'] if paid is not None else intent(e,target)
    if isinstance(current,C.PendingDecision):return current
    if current is None:return {'status':'unaffected'}
    if paid is None and not TURN.movement_permission(e,target):return {'status':'blocked','reason':'native_movement_permission'}
    if observed is None:return C.PendingDecision('Observe fastest feasible native Repel retreat before acting',basis=current)
    repeller=WORLD.actor_index(e)[current['repeller_id']]
    if observed['intent']!=current or paid is None and (tuple(observed['origin'])!=target.pos or tuple(observed['repeller_position'])!=repeller.pos):
        raise ValueError('Repel retreat observation no longer matches actual participants/positions')
    if paid is None and (_speeds(e,target)!=observed['speeds'] or target.spec.get(RELATIVE.FRAME,{}).get('directions',{}).get(observed['movement']['direction'])!=observed['direction_vector']):
        return C.PendingDecision('Reobserve the actual fastest feasible retreat after movement capability/direction changed',basis=current)
    movement=e.move_relative(target,**observed['movement'])
    if isinstance(movement,C.PendingDecision) or movement is False:return movement
    complete=movement['state']=='complete'
    if complete:
        target.spec.pop(FLEE,None)
        if observed['departed'] and movement['distance']>0 and not movement['tripped'] and tuple(observed['departure_position'])==target.pos:
            # Departure is an actual GM event after traversal, never a spray hit.
            target.on_field=False
    return {'status':'departed' if not target.on_field else 'attempted' if complete else 'pending',
            'intent':current,'movement':movement}


def validate_world(e,index=None):
    index=WORLD.actor_index(e) if index is None else index
    for user in index.values():
        if FLEE in user.spec:_verify(user.spec[FLEE])
        rows=user.spec.get(KEY,{})
        if type(rows) is not dict:raise ValueError('actual Repel applications required')
        payments=PAID.validate(user)
        for n,(identity,row) in enumerate(rows.items(),1):
            fields={'id','source','user_id','target_id','mode','at','unknown_index','hit','natural','target_level','affected','reason','approaches','payment_id','fingerprint'}
            if type(row) is not dict or set(row)!=fields or identity!=user.entity_id+':repel:'+str(n) or row['id']!=identity or row['user_id']!=user.entity_id:
                raise ValueError('actual Repel application identity required')
            _verify(row);definition(e.r,row['source']);target=index.get(row['target_id'])
            if target is None or row['mode'] not in ('self','direct') or (row['mode']=='self')!=(target is user) or row['mode']=='direct' and target.kind!='pokemon':
                raise ValueError('actual sourced Repel target/mode required')
            if type(row['hit']) is not bool:raise ValueError('actual Repel hit result required')
            if row['mode']=='self':
                if not row['hit'] or row['natural'] is not None:raise ValueError('self spray has no attack result')
            else:C.integer(row['natural'],'actual direct Repel natural roll',1,20)
            C.integer(row['target_level'],'actual Pokemon level at spray application',1)
            expected=bool(row['hit'] and (row['mode']=='self' or row['target_level']<=SOURCES[row['source']][1]))
            if type(row['affected']) is not bool or row['affected']!=expected:raise ValueError('Repel application threshold changed')
            C.integer(row['at'],'Repel application time',0,e.elapsed_seconds)
            ELAPSED.bounds(e,row['at'],row['unknown_index'],0,label='Repel elapsed time')
            _text(row['reason'],'actual Repel use reason')
            payment=payments.get(row['payment_id'])
            if payment is None or payment['at']!=row['at'] or payment['target_id']!=target.entity_id or payment['item_stock'].get('item_id')!=row['source'] or payment['item_stock'].get('count')!=1 or payment['item_stock'].get('kind') not in ('quantity','held_instance') or payment['results']!=[{'kind':'repel_use','id':identity}] or payment['outcome']!=('applied' if row['affected'] else 'no_effect'):
                raise ValueError('Repel application requires its actual stock payment original')
            if type(row['approaches']) is not dict or row['mode']=='direct' and row['approaches']:
                raise ValueError('self-spray actual approach events required')
            for uid,event in row['approaches'].items():
                if uid not in index or type(event) is not dict or set(event)!={'at','reason'}:raise ValueError('actual approached Pokemon required')
                C.integer(event['at'],'actual approach time',row['at'],e.elapsed_seconds);_text(event['reason'],'actual approach reason')
        for payment in payments.values():
            for result in payment['results']:
                if result.get('kind')=='repel_use' and result.get('id') not in rows:raise ValueError('Repel stock payment lost its actual application')
    return True
