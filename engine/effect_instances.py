"""Common instance identity and ownership for source-owned runtime effects.

Metadata lives on the existing authoritative effect record, never in a second
mutable registry. Family adapters own payloads, admission, capacity and expiry.
Legacy opaque state remains unverified instead of acquiring invented origins.
"""
from copy import deepcopy
import common_checks as C

KEY='effect_instance'
SEQUENCE='effect_instance_sequence'


def text(value,label):
    if not isinstance(value,str) or not value.strip():raise ValueError(label+' required')
    return value


def create(engine,actor,*,kind,source,payload,capacity,lifetime,applied_by=None):
    import world_entities as W
    W.require_actors(engine,actor,*(() if applied_by is None else (applied_by,)))
    text(kind,'effect family');text(source,'effect source')
    if not isinstance(payload,dict):raise ValueError('typed effect payload required')
    sequence=C.integer(actor.spec.get(SEQUENCE,0),'effect instance sequence',0)+1
    uid=actor.entity_id+':effect:'+str(sequence)
    record={'id':uid,'source':source,'effect':deepcopy(payload),'at':engine.elapsed_seconds,
        KEY:{'version':1,'kind':kind,'origin_actor_id':actor.entity_id,'holder_id':actor.entity_id,
             'sequence':sequence,'state':'active','capacity':deepcopy(capacity),'lifetime':deepcopy(lifetime),
             'ownership':[{'kind':'created','holder_id':actor.entity_id,'at':engine.elapsed_seconds,'source':source}]}}
    if applied_by is not None:record[KEY]['applied_by_actor_id']=applied_by.entity_id
    validate(record,actor=actor)
    actor.spec[SEQUENCE]=sequence
    return record


def validate(record,*,actor=None,spent=False,terminal=False):
    if not isinstance(record,dict) or KEY not in record:return False
    m=record[KEY]
    if not isinstance(m,dict):raise ValueError('typed effect-instance metadata required')
    C.integer(m.get('version'),'effect instance version',1,1)
    if 'applied_by_actor_id' in m:text(m['applied_by_actor_id'],'actual effect applying actor')
    text(m.get('kind'),'effect family');origin=text(m.get('origin_actor_id'),'effect origin actor')
    sequence=C.integer(m.get('sequence'),'effect identity sequence',1)
    uid=record.get('buff_id') if spent else record.get('id')
    if uid!=origin+':effect:'+str(sequence):raise ValueError('effect instance identity and immutable origin disagree')
    text(record.get('source'),'effect source');holder=text(m.get('holder_id'),'current effect holder')
    if actor is not None and holder!=actor.entity_id:raise ValueError('effect is stored under a different holder')
    if spent and terminal:raise ValueError('one effect ending representation required')
    allowed=('consumed','expired') if terminal else ('consumed',) if spent else ('active',)
    if m.get('state') not in allowed:raise ValueError('effect activation/consumption state mismatch')
    if not isinstance(record.get('effect'),dict) or not isinstance(record['effect'].get('kind'),str):raise ValueError('typed family effect payload required')
    cap=m.get('capacity');life=m.get('lifetime')
    if not isinstance(cap,dict) or not isinstance(life,dict):raise ValueError('explicit effect capacity and lifetime required')
    text(cap.get('bucket'),'effect capacity bucket');text(cap.get('source'),'capacity authority');text(life.get('boundary'),'effect lifetime boundary')
    history=m.get('ownership')
    if not isinstance(history,list) or not history:raise ValueError('effect ownership origin/history required')
    previous=None
    for i,row in enumerate(history):
        if not isinstance(row,dict):raise ValueError('typed effect ownership event required')
        C.integer(row.get('at'),'effect ownership event time',0 if previous is None else previous)
        text(row.get('source'),'effect ownership event source');text(row.get('holder_id'),'effect ownership event holder')
        if i==0:
            if row.get('kind')!='created' or row['holder_id']!=origin or row['source']!=record['source']:raise ValueError('effect first event disagrees with its immutable origin')
        elif row.get('kind')!='transfer' or row.get('from_holder_id')!=history[i-1]['holder_id']:raise ValueError('effect transfer must continue actual ownership history')
        previous=row['at']
    if history[-1]['holder_id']!=holder:raise ValueError('current effect holder and history disagree')
    if spent:
        C.integer(m.get('consumed_at'),'effect consumption time',previous)
        if record.get('at')!=m['consumed_at']:raise ValueError('effect consumption receipt time mismatch')
    else:
        if record.get('at')!=history[0]['at']:raise ValueError('effect creation timestamp changed')
        if 'consumed_at' in m:raise ValueError('active/terminal canonical effect cannot use a food-receipt timestamp')
        if terminal:
            C.integer(m.get('ended_at'),'effect ending time',previous)
            if not isinstance(m.get('end_event'),dict):raise ValueError('actual effect ending event required')
            text(m['end_event'].get('kind'),'effect ending event kind')
        elif any(k in m for k in ('ended_at','end_event')):raise ValueError('active effect cannot already have ended')
    return True


def transfer(engine,source_actor,target,record,*,source,capacity=None):
    import world_entities as W
    W.require_actors(engine,source_actor,target)
    if not validate(record,actor=source_actor):raise ValueError('legacy effect needs an explicit origin observation before transfer')
    text(source,'effect transfer source')
    if source_actor is target:raise ValueError('effect transfer needs distinct actual holders')
    # Validate the proposed metadata before changing this authoritative record.
    candidate=dict(record);candidate[KEY]=deepcopy(record[KEY])
    m=candidate[KEY];m['ownership'].append({'kind':'transfer','from_holder_id':source_actor.entity_id,'holder_id':target.entity_id,'at':engine.elapsed_seconds,'source':source})
    m['holder_id']=target.entity_id
    if capacity is not None:m['capacity']=deepcopy(capacity)
    validate(candidate,actor=target)
    record[KEY]=candidate[KEY]
    return record


def consumed(record,actor,at):
    if not validate(record,actor=actor):return None
    result=deepcopy(record[KEY]);result.update(state='consumed',consumed_at=at)
    return result


def archive(engine,actor,record,*,state,event):
    if not validate(record,actor=actor):raise ValueError('canonical effect required before archive')
    if state not in ('consumed','expired'):raise ValueError('supported explicit effect ending required')
    history=actor.spec.get('effect_instance_history',[])
    if not isinstance(history,list):raise ValueError('effect instance history must be a list')
    if any(row.get('id')==record['id'] for row in history):raise ValueError('effect instance already archived')
    actors=getattr(engine,'_time_actors',[])
    memo={id(c):c for c in actors};memo[id(actor)]=actor
    closed=deepcopy(record,memo)
    closed[KEY].update(state=state,ended_at=engine.elapsed_seconds,end_event=deepcopy(event))
    validate(closed,actor=actor,terminal=True)
    if closed[KEY]['kind']=='event_effect':
        import event_effects as EVENTS
        EVENTS.validate_record(actor,closed,terminal=True)
    if closed[KEY]['kind']=='coat':
        import coat_effects as COATS
        COATS.validate_record(actor,closed,terminal=True)
    if closed[KEY]['kind']=='team_blessing':
        import blessing_effects as BLESSINGS
        BLESSINGS.validate_record(actor,closed,terminal=True)
    if closed[KEY]['kind']=='roll_components':
        import roll_effects as ROLLS
        ROLLS.validate_record(actor,closed,terminal=True)
    if closed[KEY]['kind']=='captured_momentum':
        import captured_momentum as MOMENTUM
        MOMENTUM.validate_record(actor,closed,terminal=True)
    if closed[KEY]['kind']=='temporary_ap':
        import temporary_ap as TEMP_AP
        TEMP_AP.validate_record(actor,closed,terminal=True)
    if closed[KEY]['kind']=='cheerleader':
        import cheerleader as CHEER
        CHEER.validate_record(actor,closed,terminal=True)
    if closed[KEY]['kind']=='condition':
        import condition_instances as CONDITIONS
        CONDITIONS.validate_record(actor,closed,terminal=True)
    if closed[KEY]['kind']=='sage_dr':__import__('sage').validate_effect(actor,closed,terminal=True)
    history=actor.spec.setdefault('effect_instance_history',[])
    if not isinstance(history,list):raise ValueError('effect instance history must be a list')
    history.append(closed)
    return closed


def stored_family(record,kind):
    metadata=record.get(KEY)
    if not isinstance(metadata,dict) or metadata.get('kind')!=kind:raise ValueError('native effect is stored outside its authoritative family container')


def records(actor):
    live=getattr(actor,'buffs',[])
    # Legacy snapshots can contain opaque GM annotations or reference graphs.
    # They are preserved, but never counted as certified native instances.
    if isinstance(live,list):
        for row in live:
            if isinstance(row,dict) and KEY in row:
                stored_family(row,'digestion');yield row,False
    ongoing=actor.spec.get('food_turn_healing',[])
    if not isinstance(ongoing,list):raise ValueError('ongoing food effects must be a list')
    if isinstance(ongoing,list):
        for row in ongoing:
            if isinstance(row,dict) and KEY in row:
                stored_family(row,'food_turn_healing');yield row,False
    receipts=actor.spec.get('food_consumption_receipts',[])
    if not isinstance(receipts,list):raise ValueError('food consumption receipts must be a list')
    if isinstance(receipts,list):
        for row in receipts:
            if isinstance(row,dict) and KEY in row:
                stored_family(row,'digestion');yield row,True

    coats=getattr(actor,'coats',[])
    if isinstance(coats,list):
        for row in coats:
            if isinstance(row,dict) and KEY in row:
                stored_family(row,'coat');yield row,False
    blessings=getattr(actor,'blessings',[])
    if isinstance(blessings,list):
        for row in blessings:
            if isinstance(row,dict) and KEY in row:
                stored_family(row,'team_blessing');yield row,False
    import combat_timing as TIMING
    timed=TIMING.records(actor)
    if not isinstance(timed,list):raise ValueError('timed effects must be a list')
    for row in timed:
        if isinstance(row,dict) and KEY in row:
            if not isinstance(row[KEY],dict) or row[KEY].get('kind') not in ('event_effect','roll_components','captured_momentum','temporary_ap','sage_dr','telepath'):raise ValueError('native effect is stored outside its authoritative timed family')
            yield row,False
    import cheerleader as CHEER
    for row in CHEER.live(actor):
        stored_family(row,'cheerleader');yield row,False
    import condition_instances as CONDITIONS
    for row in CONDITIONS.records(actor):
        stored_family(row,'condition');yield row,False
    history=actor.spec.get('effect_instance_history',[])
    if not isinstance(history,list):raise ValueError('effect history must be a list')
    for row in history:
        if not isinstance(row,dict) or KEY not in row:raise ValueError('typed ended effect instance required')
        if not isinstance(row[KEY],dict) or row[KEY].get('kind') not in ('event_effect','coat','team_blessing','roll_components','condition','captured_momentum','temporary_ap','cheerleader','sage_dr','telepath'):raise ValueError('unsupported canonical ended effect family')
        yield row,'terminal'


def validate_actor(actor):
    if SEQUENCE in actor.spec:C.integer(actor.spec[SEQUENCE],'effect identity sequence',0)
    seen=set()
    for row,spent in records(actor):
        validate(row,actor=actor,spent=spent is True,terminal=spent=='terminal')
        if row[KEY]['kind'] in ('digestion','food_turn_healing'):
            import food_effects as FOOD
            FOOD.validate_native(actor,row,spent=spent is True)
        if row[KEY]['kind']=='event_effect':
            import event_effects as EVENTS
            EVENTS.validate_record(actor,row,terminal=spent=='terminal')
        if row[KEY]['kind']=='coat':
            import coat_effects as COATS
            COATS.validate_record(actor,row,terminal=spent=='terminal')
        if row[KEY]['kind']=='team_blessing':
            import blessing_effects as BLESSINGS
            BLESSINGS.validate_record(actor,row,terminal=spent=='terminal')
        if row[KEY]['kind']=='roll_components':
            import roll_effects as ROLLS
            ROLLS.validate_record(actor,row,terminal=spent=='terminal')
        if row[KEY]['kind']=='temporary_ap':
            import temporary_ap as TEMP_AP
            TEMP_AP.validate_record(actor,row,terminal=spent=='terminal')
        if row[KEY]['kind']=='captured_momentum':
            import captured_momentum as MOMENTUM
            MOMENTUM.validate_record(actor,row,terminal=spent=='terminal')
        if row[KEY]['kind']=='cheerleader':
            import cheerleader as CHEER
            CHEER.validate_record(actor,row,terminal=spent=='terminal')
        if row[KEY]['kind']=='condition':
            import condition_instances as CONDITIONS
            CONDITIONS.validate_record(actor,row,terminal=spent=='terminal')
        if row[KEY]['kind']=='sage_dr':__import__('sage').validate_effect(actor,row,terminal=spent=='terminal')
        if row[KEY]['kind']=='telepath':__import__('telepath').validate_effect(actor,row,terminal=spent=='terminal')
        uid=row['buff_id'] if spent is True else row['id']
        if uid in seen:raise ValueError('one effect instance appears more than once under an actor')
        seen.add(uid)
    import food_effects as FOOD
    FOOD.validate_actor_state(actor)
    return True


def validate_world(engine,index):
    seen=set()
    for actor in index.values():
        validate_actor(actor)
        for row,spent in records(actor):
            uid=row['buff_id'] if spent is True else row['id'];m=row[KEY]
            if uid in seen:raise ValueError('one effect instance cannot be held or consumed by multiple actors')
            seen.add(uid)
            if m.get('applied_by_actor_id') is not None and m['applied_by_actor_id'] not in index:raise ValueError('effect applying actor is missing')
            origin=index.get(m['origin_actor_id'])
            if origin is None or C.integer(origin.spec.get(SEQUENCE,0),'effect origin sequence',0)<m['sequence']:raise ValueError('actual effect origin/issued sequence missing')
            for event in m['ownership']:
                if event['holder_id'] not in index or event['at']>engine.elapsed_seconds:raise ValueError('effect ownership event references missing actor or future time')
            if spent=='terminal' and m['ended_at']>engine.elapsed_seconds:raise ValueError('effect ending is in the future')
            if spent is True and m['consumed_at']>engine.elapsed_seconds:raise ValueError('effect consumption is in the future')
    import cheerleader as CHEER
    CHEER.validate_world(engine,index)
    import captured_momentum as MOMENTUM
    MOMENTUM.validate_world(engine,index)
    import temporary_ap as TEMP_AP
    TEMP_AP.validate_world(engine,index)
    import event_effects as EVENTS
    EVENTS.validate_world(engine,index)
    import coat_effects as COATS
    COATS.validate_world(engine,index)
    import blessing_effects as BLESSINGS
    BLESSINGS.validate_world(engine,index)
    import roll_effects as ROLLS
    ROLLS.validate_world(engine,index)
    import condition_instances as CONDITIONS
    CONDITIONS.validate_world(engine,index)
    import food_effects as FOOD
    FOOD.validate_world(engine,index)
    FOOD.validate_transfer_world(engine,index)
    import declarative_move_contracts as DECLARATIVE_MOVES
    DECLARATIVE_MOVES.validate_world(engine,index)
    return True
