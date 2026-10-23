"""Shared ordinary daily injury-healing allowance (ch07:748/758).
Explicit GM state replacement is outside this ordinary recovery operation.
"""
EXEMPT='injury_exempt_healing'


def healed_today(c):
    values=[c.spec.get('injuries_healed_today',0),c.spec.get('center_injuries_today',0)]
    if any(type(n) is not int or n<0 for n in values):
        raise ValueError('daily injury healing counters must be nonnegative integers')
    # Legacy saves only tracked Center healing; never drop that spent allowance.
    return max(values)


def heal(engine,c,count,*,source):
    if type(count) is not int or count<0:raise ValueError('injury healing count must be a nonnegative integer')
    if not isinstance(source,str) or not source:raise ValueError('injury healing source required')
    spent=healed_today(c)
    engine.check_fainted(c)
    if c.dead:return 0
    limit=engine.r.mech('combat/resting')['pokemon_center']['max_injuries_removed_per_day']
    import csv_item_capability_contracts as CSV_CAPABILITIES
    limit=CSV_CAPABILITIES.daily_injury_heal(c,limit)
    import campaign_injury_policy as CAMPAIGN
    limit=CAMPAIGN.healing_limit(engine,c,source=source,core_limit=limit,spent=spent)
    import environmental_effects as ENVIRONMENT
    import recovery_resolution as RECOVERY
    plan=RECOVERY.resolve(c.injuries,count,resource='injuries',mode='remove',
                          floor=ENVIRONMENT.protected_injuries(c),allowance=max(0,limit-spent))
    recovered=plan['applied']
    c.injuries=plan['after']
    CAMPAIGN.injuries_healed(engine,c,recovered,source)
    observe_actor(engine,c,recovered_change=True)
    c.spec['injuries_healed_today']=spent+recovered
    if source=='pokemon_center':
        c.spec['center_injuries_today']=c.spec.get('center_injuries_today',0)+recovered
    if recovered:
        c.spec.setdefault('injury_healing_history',[]).append(dict(source=source,count=recovered,
            day=c.spec.get('frequency_state',{}).get('day',0),known_elapsed_seconds=engine.elapsed_seconds))
    return recovered


def exempt_remaining(c,source,daily_cap):
    if not isinstance(source,str) or not source:raise ValueError('exempt injury healing source required')
    if type(daily_cap) is not int or daily_cap<1:raise ValueError('positive exempt injury daily cap required')
    day=c.spec.get('frequency_state',{}).get('day',0)
    if type(day) is not int or day<0:raise ValueError('invalid injury healing day')
    rows=c.spec.get(EXEMPT,[])
    if not isinstance(rows,list):raise ValueError('exempt injury healing ledger must be a list')
    spent=sum(row.get('count',0) for row in rows if isinstance(row,dict) and row.get('source')==source and row.get('day')==day)
    return max(0,daily_cap-spent)


def heal_exempt(engine,c,count,*,source,daily_cap):
    """Remove injuries under an explicit source-owned cap, outside the ordinary daily pool."""
    if type(count) is not int or count<0:raise ValueError('injury healing count must be a nonnegative integer')
    remaining=exempt_remaining(c,source,daily_cap)
    engine.check_fainted(c)
    if c.dead:return 0
    import environmental_effects as ENVIRONMENT
    import recovery_resolution as RECOVERY
    plan=RECOVERY.resolve(c.injuries,count,resource='injuries',mode='remove',
                          floor=ENVIRONMENT.protected_injuries(c),allowance=remaining)
    recovered=plan['applied'];c.injuries=plan['after']
    import campaign_injury_policy as CAMPAIGN
    CAMPAIGN.injuries_healed(engine,c,recovered,source)
    observe_actor(engine,c,recovered_change=True)
    if recovered:
        day=c.spec.get('frequency_state',{}).get('day',0)
        row={'source':source,'count':recovered,'day':day,'known_elapsed_seconds':engine.elapsed_seconds,
             'daily_exempt':True,'daily_cap':daily_cap}
        c.spec.setdefault('injury_healing_history',[]).append(dict(row))
        c.spec.setdefault(EXEMPT,[]).append({'source':source,'count':recovered,'day':day,
                                            'at':engine.elapsed_seconds,'daily_cap':daily_cap})
    return recovered



def validate(c):
    healed_today(c)
    validate_clock(c)
    rows=c.spec.get('injury_healing_history',[])
    if not isinstance(rows,list):raise ValueError('injury healing history must be a list')
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('source'),str) or not row['source']:
            raise ValueError('injury healing source required')
        if type(row.get('count')) is not int or row['count']<=0:raise ValueError('actual healed injury count required')
        if type(row.get('known_elapsed_seconds')) is not int or row['known_elapsed_seconds']<0:
            raise ValueError('injury recovery needs known elapsed seconds')
        if 'day' in row and (type(row['day']) is not int or row['day']<0):raise ValueError('invalid injury recovery day')
        if 'daily_exempt' in row:
            if row['daily_exempt'] is not True:raise ValueError('invalid exempt injury marker')
            if type(row.get('daily_cap')) is not int or row['daily_cap']<row['count']:raise ValueError('invalid exempt injury cap')
    exempt=c.spec.get(EXEMPT,[])
    if not isinstance(exempt,list):raise ValueError('exempt injury healing ledger must be a list')
    totals={}
    for row in exempt:
        if not isinstance(row,dict) or not isinstance(row.get('source'),str) or not row['source']:raise ValueError('exempt injury source required')
        for key,minimum in (('count',1),('day',0),('at',0),('daily_cap',1)):
            if type(row.get(key)) is not int or row[key]<minimum:raise ValueError('invalid exempt injury '+key)
        key=(row['source'],row['day']);totals[key]=totals.get(key,0)+row['count']
        if totals[key]>row['daily_cap']:raise ValueError('exempt injury daily cap exceeded')
        if not any(history.get('daily_exempt') is True and history.get('source')==row['source'] and history.get('day')==row['day'] and history.get('known_elapsed_seconds')==row['at'] and history.get('count')==row['count'] for history in rows):
            raise ValueError('exempt injury ledger lacks healing history')


CLOCK='injury_recovery_clock'


def observe_actor(engine,c,*,recovered_change=False):
    """A first observation supplies a safe lower bound, never an invented past onset."""
    validate_clock(c)
    row=c.spec.get(CLOCK)
    if row is None or (row['observed_injuries']!=c.injuries and not recovered_change):
        row={'source':'combat/resting','observed_at':engine.elapsed_seconds,'known_seconds':0,'accelerated_seconds':0,
             'observed_injuries':c.injuries,'birth_round':engine.round_no if engine.round_start_seconds is not None else None,
             'last_injury_source':None,'last_injury_count':None,'last_recovery_at':None}
        c.spec[CLOCK]=row
    row['observed_injuries']=c.injuries
    return row


def note_change(engine,c,amount,source):
    """Called by the already shared actual-injury producer observation."""
    if type(amount) is not int:raise ValueError('integral injury change required')
    if amount<=0:
        observe_actor(engine,c,recovered_change=True);return
    row=observe_actor(engine,c)
    row.update(observed_at=engine.elapsed_seconds,known_seconds=0,accelerated_seconds=0,
               birth_round=engine.round_no if engine.round_start_seconds is not None else None,
               last_injury_source=source,last_injury_count=amount)


def advance(engine,c,seconds):
    row=observe_actor(engine,c)
    if c.dead or c.injuries==0:return
    # A round has no exact occurrence timestamp unless individually observed.
    # Do not credit the injury's entire birth round. Subsequent known intervals
    # establish a lower bound, even when other elapsed intervals are unknown.
    if engine.round_start_seconds is not None and row['birth_round']==engine.round_no:return
    import csv_item_capability_contracts as CSV_CAPABILITIES
    # Keep the observed clock in real seconds. Recovery-only credit records
    # intervals actually spent under the effective twice-fast capability, so
    # gaining/losing that capability never rewrites earlier progress. Probe a
    # two-second interval: ceil(1 / 2) must not lose one-second slices.
    bonus=seconds if CSV_CAPABILITIES.injury_recovery_seconds(c,2)<2 else 0
    row['known_seconds']+=seconds
    row['accelerated_seconds']=row.get('accelerated_seconds',0)+bonus


def recover_naturally(engine,c):
    """Consume one observed no-new-injury interval; no retroactive multi-day schedule."""
    import movement_actions as MOVEMENT
    MOVEMENT.boundary(engine,'natural_injury_recovery')
    import common_checks as C
    rule=engine.r.mech('combat/resting')['injury_natural_heal']
    C.integer(rule['per_hours'],'natural recovery hours',1)
    if rule.get('if')!='no new injury':raise ValueError('selected natural recovery condition needs its own policy')
    engine.check_fainted(c);row=observe_actor(engine,c)
    if c.dead or row['known_seconds']+row.get('accelerated_seconds',0)<rule['per_hours']*3600:return 0
    evidence={k:row[k] for k in ('observed_at','known_seconds','last_injury_source','last_injury_count')}
    evidence['accelerated_seconds']=row.get('accelerated_seconds',0)
    recovered=heal(engine,c,rule['count'],source='natural')
    if recovered:
        c.spec['injury_healing_history'][-1]['eligibility']=evidence
        row.update(observed_at=engine.elapsed_seconds,known_seconds=0,accelerated_seconds=0,last_recovery_at=engine.elapsed_seconds,birth_round=None)
    return recovered


def recover_with_ap(engine,c,*,duration_minutes=None,reason=None):
    import common_checks as C,movement_actions as MOVEMENT,world_entities as W
    import action_points as AP,state_grants as G,environmental_effects as ENVIRONMENT
    MOVEMENT.boundary(engine,'trainer_injury_recovery')
    if W.actor_index(engine).get(c.entity_id) is not c:raise ValueError('actual world actor required')
    if c.kind!='trainer':raise ValueError('Drained AP injury recovery is a Trainer rule')
    if engine.encounter_active:return C.PendingDecision('Extended injury recovery needs an actual noncombat interval')
    if duration_minutes is None or reason is None:return C.PendingDecision('GM Extended injury recovery duration and reason')
    C.integer(duration_minutes,'Extended injury recovery minutes',1)
    if not isinstance(reason,str) or not reason.strip():raise ValueError('GM injury recovery duration reason required')
    validate(c);AP.validate(c)
    limit=engine.r.mech('combat/resting')['pokemon_center']['max_injuries_removed_per_day']
    if c.dead or c.injuries<=ENVIRONMENT.protected_injuries(c) or healed_today(c)>=limit or AP.available(c)<2:return False
    engine.preflight_advance_time(duration_minutes*60,[c])
    def apply(e,actor):
        import turn as TURN
        if not TURN.spend(e,actor,'extended','2 AP 제거로 부상 회복'):return False
        start=e.elapsed_seconds
        AP.spend(actor,2,{'frequency':{'raw':'2 AP 제거'}})
        e.advance_time(duration_minutes*60,[actor]);recovered=heal(e,actor,1,source='trainer_drained_ap')
        receipt={'source':'combat/resting','ap_drained':2,'recovered':recovered,'start':start,
                 'end':e.elapsed_seconds,'duration_minutes':duration_minutes,'reason':reason}
        actor.spec.setdefault('injury_ap_recovery_history',[]).append(receipt)
        e.log('  '+actor.name+': AP 2 제거, 부상 '+str(recovered)+'개 회복','combat/resting')
        return receipt
    return G.transition(engine,c,apply)


def validate_clock(c):
    import common_checks as C
    row=c.spec.get(CLOCK)
    if row is not None:
        if not isinstance(row,dict) or row.get('source')!='combat/resting':raise ValueError('injury recovery clock source required')
        for key in ('observed_at','known_seconds','observed_injuries'):C.integer(row.get(key),'injury clock '+key,0)
        C.integer(row.get('accelerated_seconds',0),'injury acceleration credit',0,row['known_seconds'])
        if row.get('birth_round') is not None:C.integer(row['birth_round'],'injury birth round',0)
        if row.get('last_recovery_at') is not None:C.integer(row['last_recovery_at'],'natural recovery time',0)
        if row.get('last_injury_source') is not None:
            if not isinstance(row['last_injury_source'],str) or not row['last_injury_source']:raise ValueError('actual injury source required')
            C.integer(row.get('last_injury_count'),'last actual injury count',1)
    rows=c.spec.get('injury_ap_recovery_history',[])
    if not isinstance(rows,list):raise ValueError('AP recovery history must be a list')
    for receipt in rows:
        if not isinstance(receipt,dict) or receipt.get('source')!='combat/resting' or type(receipt.get('ap_drained')) is not int or receipt['ap_drained']!=2:
            raise ValueError('AP recovery source/cost mismatch')
        C.integer(receipt.get('recovered'),'AP recovered injury count',0,1)
        for key in ('start','end'):C.integer(receipt.get(key),'AP recovery '+key,0)
        C.integer(receipt.get('duration_minutes'),'AP recovery duration',1)
        if receipt['end']-receipt['start']!=receipt['duration_minutes']*60:raise ValueError('AP recovery duration mismatch')
        if not isinstance(receipt.get('reason'),str) or not receipt['reason'].strip():raise ValueError('AP recovery reason required')


def validate_world(engine,actors):
    for c in actors.values():
        validate_clock(c);row=c.spec.get(CLOCK)
        if row is not None and (row['observed_at']>engine.elapsed_seconds or row['known_seconds']>engine.elapsed_seconds-row['observed_at']):
            raise ValueError('injury clock claims unobserved future time')
        if row is not None:
            if row['birth_round'] is not None and row['birth_round']>engine.round_no:raise ValueError('injury clock claims a future round')
            if row['last_recovery_at'] is not None and row['last_recovery_at']>engine.elapsed_seconds:raise ValueError('natural recovery claims future time')
        for receipt in c.spec.get('injury_ap_recovery_history',[]):
            if receipt['end']>engine.elapsed_seconds:raise ValueError('AP recovery claims future time')
