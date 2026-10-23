"""Exact requested clock intervals, native timer results and activity bindings.

Clock completion does not certify the calling activity. Native consumers bind
their own committed step separately. Unrequested ordinary clock ticks stay lean.
"""
from copy import deepcopy
import common_checks as C
import resolution_transaction as REQUESTS

KEY='_clock_invocations'
ACTIVE='_active_clock_invocation'


def intent(seconds, actors, source):
    C.integer(seconds,'clock invocation seconds',0)
    if type(source) is not str or not source:raise ValueError('actual clock source required')
    return {'seconds':seconds,'actors':list(dict.fromkeys(c.entity_id for c in actors)),'source':source}


def validate(engine):
    rows=getattr(engine,KEY,{})
    if type(rows) is not dict:raise ValueError('native clock invocation mapping required')
    if not rows:return rows
    import world_entities as W
    actors=W.actor_index(engine)
    for identity,row in rows.items():
        if type(row) is not dict or row.get('id')!=identity or type(identity) is not str or not identity:
            raise ValueError('actual clock invocation identity required')
        if row.get('intent_fingerprint')!=REQUESTS.request_fingerprint(row.get('intent')):
            raise ValueError('clock invocation intent changed')
        declared=row['intent']
        if (type(declared) is not dict or type(declared.get('actors')) is not list
                or intent(declared.get('seconds'),[actors[a] for a in declared['actors']],declared.get('source'))!=declared):
            raise ValueError('actual clock declaration required')
        participants=row.get('participants')
        if (type(participants) is not list or len(set(participants))!=len(participants)
                or any(a not in actors for a in participants) or set(declared['actors'])-set(participants)):
            raise ValueError('actual clock participants required')
        if row.get('status') not in ('running','waiting','complete') or type(row.get('bindings')) is not list or type(row.get('children')) is not list:
            raise ValueError('explicit clock completion state required')
        C.integer(row.get('start'),'clock start',0)
        if row.get('mode')=='resumable':
            _validate_progress(engine,row)
        if 'activity' in row:_validate_activity(engine,row,actors)
        for child in row['children']:
            _validate_child(engine,row,child,actors,completed=row['status']=='complete')
        if row['status']=='complete':
            if row.get('end')!=row['start']+row['intent']['seconds']:
                raise ValueError('clock completion does not match its actual interval')
            for binding in row['bindings']:
                _native_binding(engine,row,binding,actors)
                if binding['record'].get('clock_invocation_id')!=identity:
                    raise ValueError('native step lost its clock original')
    return rows


def _delivery(engine, owner, delivery):
    import combat_timing as LIFE
    from effect_lifetime_policy import KEY as POLICY
    matches=[]
    for record in LIFE.records(owner):
        if POLICY in record and any(delivery is r for r in record['lifetime_deliveries']):
            matches.append((record['source'],record['effect_receipt'],record[POLICY]['repeat_effect']))
    for record in owner.custom_conditions.get('effect_lifetime_history',[]):
        if any(delivery is r for r in record['deliveries']):
            matches.append((record['source'],record['receipt'],record['policy']['repeat_effect']))
    if len(matches)!=1:raise ValueError('actual native lifetime delivery original required')
    source,parent,effect=matches[0]
    rows=getattr(engine,'_effect_dispatch_receipts',{})
    try:producer=rows[parent];child=rows[delivery['receipt']]
    except (KeyError,TypeError):raise ValueError('actual lifetime producer and child receipts required')
    import effect_contracts as CONTRACTS
    CONTRACTS.validate_receipt(engine,delivery['receipt'],source,child['occurrence'],producer['actor'],owner,effect)
    if child['status']=='condition_unknown' or 'condition_request' in child:
        CONTRACTS.validate_condition_request(engine,child,completed=child['status']=='completed')
    return child


def _validate_child(engine, row, child, actors, *, completed):
    owner=actors.get(child.get('owner_id'));record=child.get('record')
    if owner is None or owner.entity_id not in row['participants'] or type(record) is not dict:
        raise ValueError('actual clock child owner required')
    end=row.get('cursor',row.get('end'))
    if end is None:end=engine.elapsed_seconds
    if child.get('kind')=='bandage':
        if (not any(record is r for r in owner.spec.get('bandages',[]))
                or record.get('status')!='expired' or not row['start']<=record['ended_at']<=end):
            raise ValueError('clock child has no completed native bandage result')
    elif child.get('kind')=='lifetime_delivery':
        actual=_delivery(engine,owner,record)
        if (record.get('clock_invocation_id')!=row['id'] or record.get('event')!='time_advanced'
                or type(record.get('token')) is not int or not row['start']<=record['token']<=end):
            raise ValueError('lifetime result belongs to another clock interval')
        if completed and actual['status']!='completed':raise ValueError('clock still has a required native child')
    else:raise ValueError('unsupported native clock child')


def _validate_progress(engine, row):
    if row.get('profile')!=_source_profile(engine,row):
        raise ValueError('clock source policy changed')
    target=row['start']+row['intent']['seconds']
    if row.get('target')!=target:raise ValueError('clock original target changed')
    C.integer(row.get('cursor'),'clock committed cursor',row['start'],target)
    if row.get('phase') not in ('slice','boundary','complete'):
        raise ValueError('actual clock continuation phase required')
    at=row['start']
    for segment in row.get('segments',()):
        if type(segment) is not dict or segment.get('start')!=at:
            raise ValueError('clock committed prefix is not adjacent')
        at=C.integer(segment.get('end'),'clock segment end',at,target)
    if at!=row['cursor']:raise ValueError('clock cursor differs from its committed prefix')
    if row['status']=='complete':
        if row['phase']!='complete' or row['cursor']!=target:raise ValueError('clock boundary has not completed')
    elif engine.elapsed_seconds!=row['cursor'] or row['phase']=='complete':
        raise ValueError('pending clock cannot move past its committed boundary')
    elif row.get('context')!=_context(engine,row['participants']):
        raise ValueError('pending clock boundary context changed')
    if row['status']=='waiting' and row['phase']!='boundary':raise ValueError('waiting clock needs its actual boundary')


def _source_profile(engine, row):
    """A native explicit choice belongs only to its actual intake declaration.

    Generic clock sources retain the ordinary automatic selection contract.
    The food owner revalidates its exact CSV source on every save and resume;
    neither a saved profile nor an arbitrary catalog identifier grants access.
    """
    import effect_contracts as CONTRACTS
    source=row['intent']['source'];activity=row.get('activity',{})
    plan=activity.get('plan',{});choice=plan.get('csv_food_source')
    if choice is None:return CONTRACTS.source_profile(engine,source)
    import csv_item_food_contracts as CSV
    checked=CSV.validate_choice(engine.r,choice,source)
    request=activity.get('request',{});stock=plan.get('stock',{})
    if (activity.get('kind')!='food_intake' or request.get('item')!=source
            or plan.get('item')!=source or request.get('target_id')!=plan.get('target_id')
            or CSV.intake_choice(engine.r,source,request.get('policy'))!=checked
            or stock.get('item_id')!=source or stock.get('source_selection')!=checked
            or plan.get('effect')!=CSV.effect(checked)):
        raise ValueError('clock exact source differs from its native food declaration')
    payment=activity.get('payment')
    if payment is not None and (payment.get('item_id')!=source or payment.get('source_selection')!=checked):
        raise ValueError('clock exact source differs from its original stock payment')
    return REQUESTS.request_fingerprint({'csv_food_source':checked,
        'payload':engine.r.items_mech[source],'effect':CSV.effect(checked)})


def _context(engine, participants):
    import world_entities as W
    index=W.actor_index(engine)
    return {'round':engine.round_no,'round_start':engine.round_start_seconds,'encounter':engine.encounter_active,
            'gaps':len(engine.unresolved_time_intervals),
            'calendars':{uid:{k:index[uid].spec.get('frequency_state',{}).get(k,0) for k in ('day','scene','turn')}
                         for uid in participants}}


def executing_resumable(engine):
    row=getattr(engine,KEY,{}).get(getattr(engine,ACTIVE,None),{})
    return row.get('mode')=='resumable' and row.get('status') in ('running','waiting')


def owns_delivery(engine, owner, delivery):
    return any(row.get('mode')=='resumable' and row['status']!='complete'
               and any(child['kind']=='lifetime_delivery' and child['owner_id']==owner.entity_id
                       and child['record'] is delivery for child in row['children'])
               for row in getattr(engine,KEY,{}).values())


def ensure_clear(engine):
    allowed=getattr(engine,'_effect_resuming_receipt',None)
    for row in getattr(engine,KEY,{}).values():
        if row.get('mode')!='resumable':continue
        native_pending=row.get('activity',{}).get('status')=='pending' or any(
            job.get('pending_work',{}).get('clock_id')==row['id']
            for job in getattr(engine,'_activity_jobs',{}).get('jobs',{}).values())
        if row['status']=='complete' and not native_pending:continue
        if getattr(engine,ACTIVE,None)==row['id']:continue
        if allowed is not None and any(child['kind']=='lifetime_delivery' and child['record']['receipt'] is allowed
                                       for child in row['children']):continue
        raise ValueError('resume the actual clock invocation before another action or time boundary')


def _native_binding(engine, row, binding, actors):
    owner=actors.get(binding.get('owner_id'))
    record=binding.get('record');step=binding.get('step_id');kind=binding.get('kind')
    if owner is None or owner.entity_id not in row['participants'] or type(record) is not dict or record.get('id')!=step:
        raise ValueError('actual native clock consumer required')
    if kind=='activity_job':
        jobs=getattr(engine,'_activity_jobs',{}).get('jobs',{})
        matches=[job for job in jobs.values() if job['owner'] is owner and any(record is event for event in job['events'])]
        if len(matches)!=1:raise ValueError('actual native activity work step required')
        job=matches[0]
        expected='activity-job:'+REQUESTS.request_fingerprint({'job_id':job['id'],'interval_id':step})
        if (row['id']!=expected or row['intent']['source']!=job['source'] or record.get('kind')!='work'
                or (record.get('start'),record.get('end'),record.get('seconds'))!=(row['start'],row['end'],row['intent']['seconds'])):
            raise ValueError('clock result belongs to another activity invocation')
    elif kind=='bandage_application':
        if (not any(record is r for r in owner.spec.get('bandages',[])) or record.get('started_at')!=row['end']
                or record.get('source_id')!=row['intent']['source']):
            raise ValueError('actual native bandage application required')
    else:raise ValueError('unsupported native clock consumer')


def replay(engine, request_id, declared):
    rows=validate(engine)
    if request_id is None:return None
    prior=REQUESTS.replay_result(rows,request_id,declared)
    if prior is not None and prior['status']!='complete':raise ValueError('clock invocation is not complete')
    return prior


def begin(engine, declared, request_id, participants):
    rows=validate(engine)
    if request_id is None:
        sequence=len(rows)+1
        while 'clock:'+str(sequence) in rows:sequence+=1
        request_id='clock:'+str(sequence)
    if type(request_id) is not str or not request_id or request_id in rows:raise ValueError('distinct clock request identity required')
    row={'id':request_id,'intent':deepcopy(declared),'intent_fingerprint':REQUESTS.request_fingerprint(declared),
         'participants':[c.entity_id for c in participants],'start':engine.elapsed_seconds,'end':None,
         'status':'running','children':[],'bindings':[]}
    if not hasattr(engine,KEY):setattr(engine,KEY,{})
    getattr(engine,KEY)[request_id]=row
    return row


def child(engine, actor, record, *, kind):
    identity=getattr(engine,ACTIVE,None)
    if identity is None:return
    row=getattr(engine,KEY)[identity]
    if row['status'] not in ('running','waiting') or actor.entity_id not in row['participants']:
        raise ValueError('timer result belongs to another clock invocation')
    if kind=='lifetime_delivery':
        _delivery(engine,actor,record)
        if record.get('clock_invocation_id',row['id'])!=row['id']:raise ValueError('lifetime delivery already belongs to another clock')
        record['clock_invocation_id']=row['id']
    elif kind!='bandage' or not any(record is r for r in actor.spec.get('bandages',[])) or record.get('status')!='expired':
        raise ValueError('actual native timer result required')
    if any(c['kind']==kind and c['owner_id']==actor.entity_id and c['record'] is record for c in row['children']):return
    row['children'].append({'kind':kind,'owner_id':actor.entity_id,'record':record})


def advance(engine, seconds, actors, *, request_id, source):
    """Commit each prefix and each boundary before moving to the next one."""
    import state_grants as G
    import effect_lifetime_policy as LIFETIMES
    import crafting_products as PRODUCTS
    declared=intent(seconds,actors,source)
    if type(request_id) is not str or not request_id:raise ValueError('resumable clock request identity required')
    rows=validate(engine);row=rows.get(request_id)
    if row is not None:
        if row['intent_fingerprint']!=REQUESTS.request_fingerprint(declared):raise ValueError('clock identity reused with changed input')
        if row['status']=='complete':return deepcopy(row)
        if row.get('mode')!='resumable':raise ValueError('clock was not admitted as resumable')
    else:
        participants=engine.preflight_advance_time(seconds,actors)
        def start(staged, primary, *others):
            return _begin_resumable(staged,declared,request_id,others)
        row=G.transition(engine,None,start,participants=participants)
    import world_entities as W
    index=W.actor_index(engine)
    participants=[index[uid] for uid in row['participants']]
    while True:
        def step(staged, primary, *others):
            actual=getattr(staged,KEY)[request_id]
            previous=getattr(staged,ACTIVE,None);setattr(staged,ACTIVE,request_id)
            try:
                if actual['phase']=='slice':
                    remaining=actual['target']-staged.elapsed_seconds
                    staged.preflight_advance_time(remaining,others)
                    LIFETIMES.reconcile(staged);PRODUCTS.reconcile(staged)
                    interval=min(LIFETIMES.next_interval(staged,actual['target']),PRODUCTS.next_interval(staged,actual['target']))
                    start_at=staged.elapsed_seconds
                    staged._advance_time_slice(interval,others)
                    actual['segments'].append({'start':start_at,'end':staged.elapsed_seconds})
                    actual.update(cursor=staged.elapsed_seconds,phase='boundary',status='running')
                else:
                    result=LIFETIMES.boundary(staged,'time_advanced')
                    if result is False:actual['status']='waiting'
                    elif result=='progress':actual['status']='running'
                    elif actual['cursor']==actual['target']:
                        actual.update(status='complete',phase='complete',end=actual['target'])
                    else:actual.update(status='running',phase='slice')
                validate(staged)
                return actual
            finally:setattr(staged,ACTIVE,previous)
        row=G.transition(engine,None,step,participants=participants)
        if row['status'] in ('waiting','complete'):return row


def _begin_resumable(engine, declared, request_id, participants):
    row=begin(engine,declared,request_id,participants)
    return _admit_progress(engine,row)


def _admit_progress(engine, row):
    row.update(mode='resumable',target=engine.elapsed_seconds+row['intent']['seconds'],cursor=engine.elapsed_seconds,
               phase='slice',segments=[],profile=_source_profile(engine,row),
               context=_context(engine,row['participants']))
    return row


def activity_request(engine, request_id, kind, actor, actors, seconds, source, request):
    """Read an admitted native intake/application before repeating stock checks."""
    import world_entities as W
    W.require_actors(engine,actor,*actors)
    if type(request_id) is not str or not request_id.strip():raise ValueError('identified timed activity required')
    row=validate(engine).get(request_id)
    if row is None:return None
    activity=row.get('activity',{})
    if (row['intent']!=intent(seconds,actors,source) or activity.get('kind')!=kind
            or activity.get('owner_id')!=actor.entity_id
            or activity.get('request_fingerprint')!=REQUESTS.request_fingerprint(request)):
        raise ValueError('timed activity identity reused with changed input')
    return row


def _validate_activity(engine, row, actors):
    import consumption_execution as STOCK
    activity=row['activity'];owner=actors.get(activity.get('owner_id'))
    if (activity.get('kind') not in ('food_intake','bandage_application') or owner is None
            or owner.entity_id not in row['participants'] or row.get('mode')!='resumable'
            or activity.get('status') not in ('pending','complete')
            or activity.get('request_fingerprint')!=REQUESTS.request_fingerprint(activity.get('request'))
            or activity.get('plan_fingerprint')!=REQUESTS.request_fingerprint(activity.get('plan'))):
        raise ValueError('actual source-owned timed activity required')
    payment=activity.get('payment')
    if payment is not None:
        matches=[r for r in STOCK.validate(owner).values() if r['item_stock'] is payment]
        if len(matches)!=1 or payment.get('item_id')!=row['intent']['source']:
            raise ValueError('timed activity lost its original stock payment')
    if activity['status']=='complete':
        native=activity.get('native')
        if (row['status']!='complete' or payment is None or type(native) is not dict
                or native.get('item_stock') is not payment or type(activity.get('result')) is not dict
                or activity.get('result_fingerprint')!=REQUESTS.request_fingerprint(activity['result'])):
            raise ValueError('timed activity lacks its committed native outcome')
    elif activity.get('result') is not None or row['context']!=_context(engine,row['participants']) or row['cursor']!=engine.elapsed_seconds:
        raise ValueError('pending timed activity cannot leave its original boundary')


def run_activity(engine, actor, actors, *, request_id, kind, seconds, source, request,
                 prepare, finish):
    """Share only admission/clock/resumption; native adapters own payment/effects.

    Callbacks are provided by the native consumer on every call and never saved.
    The clock row stores plain declarations and actual payment/result references.
    """
    import state_grants as G
    row=activity_request(engine,request_id,kind,actor,actors,seconds,source,request)
    if row is not None and row['activity']['status']=='complete':return deepcopy(row['activity']['result'])
    participants=[c for c in actors if c is not actor]
    if row is None:
        clock_actors=engine.preflight_advance_time(seconds,actors)
        def admit(e,a,*ps):
            import world_entities as W
            current=begin(e,intent(seconds,[a,*ps],source),request_id,
                          [W.actor_index(e)[c.entity_id] for c in clock_actors])
            previous=getattr(e,ACTIVE,None);setattr(e,ACTIVE,request_id)
            try:plan,payment=prepare(e,a,*ps)
            finally:setattr(e,ACTIVE,previous)
            current['activity']={'kind':kind,'owner_id':a.entity_id,'request':deepcopy(request),
                'request_fingerprint':REQUESTS.request_fingerprint(request),
                'plan':plan,'plan_fingerprint':REQUESTS.request_fingerprint(plan),
                'status':'pending','payment':payment,'result':None}
            return _admit_progress(e,current)
        row=G.transition(engine,actor,admit,participants=participants)
    clock=advance(engine,seconds,actors,request_id=request_id,source=source)
    if clock['status']!='complete':return {'status':'waiting','activity':kind,'request_id':request_id,'clock_id':request_id}
    def commit(e,a,*ps):
        current=getattr(e,KEY)[request_id];activity=current['activity']
        previous=getattr(e,ACTIVE,None);setattr(e,ACTIVE,request_id)
        try:
            result,payment,native=finish(e,a,*ps,plan=activity['plan'],payment=activity['payment'],clock=current)
            activity.update(status='complete',payment=payment,native=native,result=result,
                            result_fingerprint=REQUESTS.request_fingerprint(result))
            validate(e)
            return deepcopy(result)
        finally:setattr(e,ACTIVE,previous)
    return G.transition(engine,actor,commit,participants=participants)


def bind(engine, receipt, record, *, kind, owner_id, step_id, request_id=None):
    row=validate(engine).get(receipt.get('id'))
    if row is None or row['status']!='complete' or receipt.get('intent_fingerprint')!=row['intent_fingerprint']:
        raise ValueError('actual completed clock original required')
    if request_id is not None and row['id']!=request_id:raise ValueError('clock result belongs to another activity invocation')
    if type(record) is not dict or any(type(v) is not str or not v for v in (kind,owner_id,step_id)):
        raise ValueError('actual identified activity step required')
    if owner_id not in row['participants']:raise ValueError('clock and activity participants differ')
    import world_entities as W
    binding={'kind':kind,'owner_id':owner_id,'step_id':step_id,'record':record}
    _native_binding(engine,row,binding,W.actor_index(engine))
    for previous in row['bindings']:
        if (previous['kind'],previous['owner_id'],previous['step_id'])==(kind,owner_id,step_id):
            if previous['record'] is not record:raise ValueError('activity step original replaced')
            return row['id']
    row['bindings'].append(binding)
    record['clock_invocation_id']=row['id']
    return row['id']
