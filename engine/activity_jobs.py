"""Sourced jobs over actual participants, elapsed intervals and native rolls.

Eligibility and rewards stay with each native consumer. This module owns job
continuity, explicit resumption, finite attempts, daily use and shared time.
"""
from copy import deepcopy
from dataclasses import replace
import common_checks as C
import resolution_transaction as TX
import root_resolution as R
import world_entities as W

CREDITS='_activity_job_credits'


def _text(value,label):
    if type(value) is not str or not value.strip():raise ValueError(label+' identity required')
    return value


def _data(value):
    return R.plain(R.freeze(value))


def _source(engine,source):
    _text(source,'job source')
    if source in engine.r.selection.units and engine.r._selected_rule(source)!=source:
        raise ValueError('job source selection changed')
    return source


def definition(value):
    if type(value) is not dict:raise ValueError('explicit job definition required')
    allowed={'required_seconds','target','attempt_limit','interval_seconds','continuity','resume',
             'required_pause_seconds','daily_limits','daily_key','credit'}
    if set(value)-allowed:raise ValueError('unknown job policy')
    result={'required_seconds':0,'target':None,'attempt_limit':None,'interval_seconds':None,
            'continuity':'continuous','resume':'forbid','required_pause_seconds':0,
            'daily_limits':{},'daily_key':None,'credit':None,**_data(value)}
    C.integer(result['required_seconds'],'job required seconds',0)
    C.integer(result['required_pause_seconds'],'job required pause',0)
    for key,minimum in (('target',None),('attempt_limit',0),('interval_seconds',1)):
        if result[key] is not None:C.integer(result[key],'job '+key,minimum)
    if result['target'] is None and (result['attempt_limit'] is not None or result['interval_seconds'] is not None):
        raise ValueError('attempt policies require an accumulated target')
    if result['target'] is not None and result['interval_seconds'] is None:
        raise ValueError('attempts require an actual interval duration')
    if result['continuity'] not in ('continuous','resumable') or result['resume'] not in ('forbid','retain','reset'):
        raise ValueError('explicit continuity and resume policy required')
    limits=result['daily_limits']
    if type(limits) is not dict or set(limits)-{'sessions','attempts','seconds'}:
        raise ValueError('known daily job limits required')
    for key,amount in limits.items():C.integer(amount,'daily job '+key,0)
    if result['daily_key'] is not None:_text(result['daily_key'],'daily job bucket')
    credit=result['credit']
    if credit is not None:
        if type(credit) is not dict or set(credit)!={'family','applications','same_day'}:
            raise ValueError('exact shared credit policy required')
        _text(credit['family'],'shared credit family')
        apps=credit['applications']
        if type(apps) is not list or not apps:raise ValueError('distinct compatible applications required')
        for app in apps:
            _text(app,'compatible application')
            if '*' in app and (not app.endswith('*') or '*' in app[:-1]):raise ValueError('only a trailing application wildcard is supported')
        if len(set(apps))!=len(apps):raise ValueError('distinct compatible applications required')
        if type(credit['same_day']) is not bool:raise ValueError('explicit credit calendar policy required')
        if result['required_seconds']<1:raise ValueError('time credit requires a positive completed duration')
    return result


def plan_interval(record,*,interval_id,now_seconds,duration,usable,block,context,unit_seconds=1):
    """Pure adjacent-time arithmetic, also used by the existing rest planner."""
    if interval_id is not None:_text(interval_id,'interval')
    for key,value,minimum in (('now',now_seconds,0),('duration',duration,0),('usable',usable,0),('block',block,1),('unit seconds',unit_seconds,1)):
        C.integer(value,key,minimum)
    if usable>duration:raise ValueError('usable time exceeds actual duration')
    context=_data(context)
    continuing=record is not None and interval_id is not None and record['id']==interval_id
    if continuing:
        if record['end_seconds']!=now_seconds or record['context']!=context:
            raise ValueError('same interval requires adjacent time and unchanged context')
        carry,total=record['carry'],record['total']
    else:carry=total=0
    C.integer(carry,'interval carry',0);C.integer(total,'interval total',0)
    if carry>=block or carry>total:raise ValueError('invalid interval carry')
    earned,remainder=divmod(carry+usable,block)
    return {'id':interval_id,'end_seconds':now_seconds+duration*unit_seconds,'carry':remainder,
            'total':total+duration,'context':context},earned


def _state(engine):
    state=getattr(engine,'_activity_jobs',None)
    if state is None:
        state={'version':1,'sequence':0,'jobs':{}};engine._activity_jobs=state
    if type(state) is not dict or state.get('version')!=1 or type(state.get('jobs')) is not dict:
        raise ValueError('actual job state required')
    C.integer(state.get('sequence'),'job sequence',0)
    return state


def _context(engine,owner,participants,observations):
    days=[c.spec.get('frequency_state',{}).get('day',0) for c in (owner,*participants)]
    for day in days:C.integer(day,'job calendar day',0)
    if len(set(days))!=1:raise ValueError('job participant calendars must agree')
    return {'day':days[0],'round':engine.round_no,'gaps':len(engine.unresolved_time_intervals),
            'observations':_data({} if observations is None else observations)}


def _actors(engine,owner,participants):
    if type(participants) not in (list,tuple) or len({id(c) for c in (owner,*participants)})!=len(participants)+1:
        raise ValueError('distinct actual job participants required')
    W.require_actors(engine,owner,*participants)
    if engine.encounter_active:raise ValueError('elapsed activity jobs require noncombat time')
    if any(getattr(c,'dead',False) or getattr(c,'fainted',False) for c in (owner,*participants)):
        raise ValueError('conscious job participants required')


def _intent(row):
    return {'id':row['id'],'source':row['source'],'owner_id':row['owner'].entity_id,
            'participant_ids':[c.entity_id for c in row['participants']],
            'definition':row['definition'],'context':row['events'][0]['context']}


def _daily(state,row,day,addition):
    policy=row['definition'];used={'sessions':0,'attempts':0,'seconds':0}
    key=policy['daily_key'] or row['source']
    for previous in state['jobs'].values():
        old=previous['definition']
        if previous['owner'] is not row['owner'] or previous['source']!=row['source'] or (old['daily_key'] or previous['source'])!=key:continue
        if old['daily_limits']!=policy['daily_limits']:raise ValueError('daily job bucket cannot change its limits')
        for event in previous['events']:
            if event.get('day')!=day:continue
            if event['kind']=='start':used['sessions']+=1
            elif event['kind']=='work':
                used['seconds']+=event['seconds'];used['attempts']+=int(event['roll'] is not None)
    for name,limit in policy['daily_limits'].items():
        if used[name]+addition.get(name,0)>limit:raise ValueError('daily job '+name+' limit exhausted')


def _terminal(row):
    policy=row['definition']
    if row['progress_seconds']>=policy['required_seconds'] and (policy['target'] is None or row['total']>=policy['target']):return 'complete'
    if policy['attempt_limit'] is not None and row['attempts']>=policy['attempt_limit']:return 'failed'
    return 'active'


def _start(engine,owner,participants,*,job_id,source,policy,context):
    import clock_invocations as CLOCK
    CLOCK.ensure_clear(engine)
    _actors(engine,owner,participants);_text(job_id,'job');_source(engine,source)
    validate_world(engine,W.actor_index(engine))
    policy=definition(policy);state=_state(engine)
    if job_id in state['jobs']:raise ValueError('job identity already used; explicit new job required')
    observed=_context(engine,owner,participants,context)
    row={'id':job_id,'source':source,'owner':owner,'participants':list(participants),'definition':policy,
         'status':'active','attempts':0,'total':0,'worked_seconds':0,'progress_seconds':0,
         'context':observed,'end_seconds':engine.elapsed_seconds,'credits':{},
         'events':[{'kind':'start','at':engine.elapsed_seconds,'day':observed['day'],'context':deepcopy(observed)}]}
    row['intent']=TX.request_fingerprint(_intent(row));row['status']=_terminal(row)
    _daily(state,row,observed['day'],{'sessions':1});state['jobs'][job_id]=row
    return row


def _row(engine,job_id):
    _text(job_id,'job')
    row=getattr(engine,'_activity_jobs',{}).get('jobs',{}).get(job_id)
    if type(row) is not dict:raise ValueError('actual activity job required')
    if row.get('intent')!=TX.request_fingerprint(_intent(row)):raise ValueError('job definition or participants changed')
    _source(engine,row['source'])
    return row


def status(engine,job_id):
    row=_row(engine,job_id)
    return {'job_id':row['id'],'source':row['source'],'owner_id':row['owner'].entity_id,
            'participant_ids':[c.entity_id for c in row['participants']],
            **{key:deepcopy(row[key]) for key in ('status','attempts','total','worked_seconds','progress_seconds','end_seconds')},
            'credit_ids':{key:value['id'] for key,value in row['credits'].items()}}


def _checked_row(engine,job_id):
    row=_row(engine,job_id)
    validate_world(engine,W.actor_index(engine))
    return row


def start(engine,owner,participants=(),*,job_id,source,definition,context=None):
    import state_grants as G
    _actors(engine,owner,participants)
    def apply(e,a,*ps):
        _start(e,a,ps,job_id=job_id,source=source,policy=definition,context=context)
        return status(e,job_id)
    return G.transition(engine,owner,apply,participants=participants)


def _compatible(credit,application):
    return any(application==pattern or (pattern.endswith('*') and application.startswith(pattern[:-1])) for pattern in credit['applications'])


def _issue(engine,row):
    policy=row['definition']['credit']
    if policy is None or row['status']!='complete':return
    events=row['events']
    if row['definition']['resume']=='reset':
        offset=max((i+1 for i,event in enumerate(events) if event['kind']=='resume'),default=0)
        events=events[offset:]
    start=next(event['start'] for event in events if event['kind']=='work')
    for actor in row['participants'] or [row['owner']]:
        credit={'id':TX.request_fingerprint({'job_id':row['id'],'recipient_id':actor.entity_id}),
                'job_id':row['id'],'recipient_id':actor.entity_id,'owner_id':row['owner'].entity_id,
                'source':row['source'],'start':start,'end':row['end_seconds'],
                'seconds':row['progress_seconds'],'day':row['context']['day'],**deepcopy(policy),'claims':[]}
        row['credits'][actor.entity_id]=credit
        actor.custom_conditions.setdefault(CREDITS,{})[credit['id']]=credit


def _native_roll(roll):
    from state_codec import native_data_types
    if not isinstance(roll,C.SkillRoll) or type(roll) not in native_data_types():
        raise ValueError('registered native job roll required')
    if replace(roll)!=roll:raise ValueError('native job roll shape changed')
    C.integer(roll.total,'native job roll total')
    return roll


def _preflight_work(engine,row,*,interval_id,seconds,context=None,attempt=False,contribution=None):
    if 'pending_work' in row:raise ValueError('resume the actual pending job interval first')
    _text(interval_id,'job interval');C.integer(seconds,'job interval seconds',1)
    _actors(engine,row['owner'],row['participants'])
    if row['status']!='active':raise ValueError('job is paused or terminal')
    if any(event.get('id')==interval_id for event in row['events']):raise ValueError('job interval already recorded')
    policy=row['definition']
    if (policy['target'] is not None)!=attempt:raise ValueError('target jobs require a native skill attempt')
    if attempt and seconds!=policy['interval_seconds']:raise ValueError('attempt requires its selected interval duration')
    if attempt:
        if type(contribution) is not dict or set(contribution)!={'actor_id','skill'} or contribution['actor_id'] not in [c.entity_id for c in (row['owner'],*row['participants'])]:
            raise ValueError('actual job roll contributor required')
        _text(contribution['skill'],'job contributor skill')
    observations=row['context']['observations'] if context is None else context
    observed=_context(engine,row['owner'],row['participants'],observations)
    if observed!=row['context']:raise ValueError('changed job context requires explicit permitted resumption')
    gap=engine.elapsed_seconds-row['end_seconds']
    last_work=next((event for event in reversed(row['events']) if event['kind']=='work'),None)
    pause=policy['required_pause_seconds'] if last_work is not None else 0
    if last_work is not None and engine.elapsed_seconds-last_work['end']<pause:raise ValueError('required job pause has not elapsed')
    adjacency=pause if row['events'][-1]['kind']=='work' else 0
    if policy['continuity']=='continuous' and gap!=adjacency:raise ValueError('continuous job requires adjacent time')
    _daily(_state(engine),row,observed['day'],{'seconds':seconds,'attempts':int(attempt)})
    engine.preflight_advance_time(seconds,[row['owner'],*row['participants']])
    return observed


def _work(engine,row,*,interval_id,seconds,context=None,roller=None,contribution=None):
    attempt=roller is not None
    observed=_preflight_work(engine,row,interval_id=interval_id,seconds=seconds,context=context,attempt=attempt,contribution=contribution)
    import clock_invocations as CLOCK
    clock_id='activity-job:'+TX.request_fingerprint({'job_id':row['id'],'interval_id':interval_id})
    start_at=engine.elapsed_seconds
    clock=engine.advance_time(seconds,[row['owner'],*row['participants']],request_id=clock_id,source=row['source'])
    roll=roller(engine) if attempt else None
    return _finish_work(engine,row,clock,interval_id,seconds,observed,start_at,roll,contribution)


def _finish_work(engine,row,clock,interval_id,seconds,observed,start_at,roll=None,contribution=None):
    import clock_invocations as CLOCK
    clock_id='activity-job:'+TX.request_fingerprint({'job_id':row['id'],'interval_id':interval_id})
    facts=_native_roll(roll) if roll is not None else None
    row['events'].append({'kind':'work','id':interval_id,'start':start_at,'end':clock['end'],
                          'seconds':seconds,'day':observed['day'],'context':observed,'roll':facts,'contribution':deepcopy(contribution)})
    CLOCK.bind(engine,clock,row['events'][-1],kind='activity_job',owner_id=row['owner'].entity_id,
               step_id=interval_id,request_id=clock_id)
    row['end_seconds']=clock['end'];row['worked_seconds']+=seconds;row['progress_seconds']+=seconds
    if roll is not None:row['attempts']+=1;row['total']+=roll.total
    row['status']=_terminal(row);_issue(engine,row)
    return status(engine,row['id'])


def advance(engine,job_id,*,interval_id,seconds,context=None,resumable=False):
    import state_grants as G
    row=_checked_row(engine,job_id)
    if type(resumable) is not bool:raise ValueError('explicit job clock mode required')
    if resumable:return _advance_resumable(engine,row,interval_id,seconds,context)
    return G.transition(engine,row['owner'],lambda e,a,*ps:_work(e,_row(e,job_id),interval_id=interval_id,seconds=seconds,context=context),participants=row['participants'])


def _advance_resumable(engine,row,interval_id,seconds,context):
    import state_grants as G
    if row['definition']['target'] is not None:raise ValueError('resumable time work does not declare a skill attempt')
    _text(interval_id,'job interval');C.integer(seconds,'job interval seconds',1)
    clock_id='activity-job:'+TX.request_fingerprint({'job_id':row['id'],'interval_id':interval_id})
    for event in row['events']:
        if event.get('id')==interval_id:
            if event['seconds']!=seconds or context is not None and context!=event['context']['observations']:
                raise ValueError('completed job interval input changed')
            return status(engine,row['id'])
    pending=row.get('pending_work')
    if pending is None:
        observed=_preflight_work(engine,row,interval_id=interval_id,seconds=seconds,context=context)
        def admit(e,a,*ps):
            current=_row(e,row['id'])
            current['pending_work']={'id':interval_id,'seconds':seconds,'start':e.elapsed_seconds,'context':observed,'clock_id':clock_id}
        G.transition(engine,row['owner'],admit,participants=row['participants'])
        pending=row['pending_work']
    if (pending['id']!=interval_id or pending['seconds']!=seconds
            or context is not None and context!=pending['context']['observations']):
        raise ValueError('pending job interval input changed')
    clock=engine.advance_time(seconds,[row['owner'],*row['participants']],request_id=clock_id,source=row['source'],resumable=True)
    if clock['status']!='complete':
        return dict(status(engine,row['id']),clock_status=clock['status'],clock_id=clock_id)
    def finish(e,a,*ps):
        current=_row(e,row['id']);original=current['pending_work']
        _actors(e,current['owner'],current['participants'])
        result=_finish_work(e,current,getattr(e,'_clock_invocations')[clock_id],interval_id,seconds,
                            original['context'],original['start'])
        del current['pending_work']
        return result
    return G.transition(engine,row['owner'],finish,participants=row['participants'])


def attempt(engine,job_id,actor,skill,*,interval_id,context=None,options=None,resumable=False):
    import state_grants as G
    row=_checked_row(engine,job_id);W.require_actors(engine,actor)
    if type(resumable) is not bool:raise ValueError('explicit job clock mode required')
    if resumable:return _attempt_resumable(engine,row,actor,skill,interval_id,context,options)
    if row['status']!='active':raise ValueError('job is paused or terminal')
    if actor not in (row['owner'],*row['participants']):raise ValueError('actual job contributor required')
    _text(skill,'job skill');options={} if options is None else deepcopy(options,{id(c):c for c in W.actors(engine)})
    # Validate the native procedure before changing time or drawing dice.
    actor_id=actor.entity_id
    contribution={'actor_id':actor_id,'skill':skill}
    def commit(observed=None):
        def apply(e,a,*ps):
            index=W.actor_index(e);actual=index[actor_id]
            native_options=deepcopy(options,{id(c):index[c.entity_id] for c in W.actors(engine)})
            if observed is None:e._prepare_skill_roll(actual,skill,**native_options)
            return _work(e,_row(e,job_id),interval_id=interval_id,seconds=row['definition']['interval_seconds'],context=context,
                         roller=lambda staged:observed[0] if observed is not None else staged.skill_roll(actual,skill,**native_options),contribution=contribution)
        return G.transition(engine,row['owner'],apply,participants=row['participants'])
    if options.get('feature') is not None:
        import skill_feature_actions as SF
        _preflight_work(engine,row,interval_id=interval_id,seconds=row['definition']['interval_seconds'],context=context,attempt=True,contribution=contribution)
        basis={'job_intent':row['intent'],'interval_id':interval_id,'contribution':contribution,'context':row['context']}
        key='activity-job:'+TX.request_fingerprint({'job_id':job_id,'interval_id':interval_id})
        return SF.sequence(engine,key,basis,[(actor,skill,options)],commit)
    return commit()


def _attempt_declaration(engine,actor,skill,options):
    import skill_feature_actions as SF
    native=list(SF._request(engine,actor,skill,options))
    if native[-1] is not None:
        W.require_actors(engine,native[-1]);native[-1]=native[-1].entity_id
    return {'actor_id':actor.entity_id,'skill':skill,'native':_data(native),
            'feature':options.get('feature'),'roll_id':options['roll_id']}


def _attempt_resumable(engine,row,actor,skill,interval_id,context,options):
    """Commit elapsed time before the native observed-roll sequence.

    Choice callbacks are supplied again on resume, never serialized in a job.
    The native SkillEvent retains an observed first/final roll on later failure.
    """
    import clock_invocations as CLOCK,skill_feature_actions as SF,state_grants as G
    _text(interval_id,'job interval');_text(skill,'job skill')
    if actor not in (row['owner'],*row['participants']):raise ValueError('actual job contributor required')
    seconds=row['definition']['interval_seconds']
    if row['definition']['target'] is None:raise ValueError('skill attempt requires an accumulated job target')
    options={} if options is None else deepcopy(options,{id(c):c for c in W.actors(engine)})
    allowed={'mods','helper_rank','fixed','penalty_count','fixed_penalties','roll_id','helper_bonus',
             'feature','feature_options','skill_context','skill_stunt','skill_target'}
    if set(options)-allowed:raise ValueError('unsupported native job skill options')
    if options.get('feature') is None and options.get('feature_options') is not None:
        raise ValueError('feature options require a selected feature')
    clock_id='activity-job:'+TX.request_fingerprint({'job_id':row['id'],'interval_id':interval_id})
    options.setdefault('roll_id',clock_id+':roll')
    _text(options['roll_id'],'job skill roll')
    declared=_attempt_declaration(engine,actor,skill,options)
    for event in row['events']:
        if event.get('id')==interval_id:
            if (event.get('attempt_request')!=declared
                    or context is not None and context!=event['context']['observations']):
                raise ValueError('completed job attempt input changed')
            return status(engine,row['id'])
    contribution={'actor_id':actor.entity_id,'skill':skill}
    pending=row.get('pending_work')
    if pending is None:
        observed=_preflight_work(engine,row,interval_id=interval_id,seconds=seconds,context=context,attempt=True,contribution=contribution)
        engine._prepare_skill_roll(actor,skill,**options)
        if SF.event(engine,actor,options['roll_id']) is not None:raise ValueError('roll already belongs to another observed action')
        def admit(e,a,*ps):
            _row(e,row['id'])['pending_work']={'id':interval_id,'seconds':seconds,'start':e.elapsed_seconds,
                'context':observed,'clock_id':clock_id,'attempt':deepcopy(declared),
                'attempt_fingerprint':TX.request_fingerprint(declared)}
        G.transition(engine,row['owner'],admit,participants=row['participants'])
        pending=row['pending_work']
    if (pending['id']!=interval_id or pending.get('attempt')!=declared
            or context is not None and context!=pending['context']['observations']):
        raise ValueError('pending job attempt input changed')
    clock=engine.advance_time(seconds,[row['owner'],*row['participants']],request_id=clock_id,source=row['source'],resumable=True)
    if clock['status']!='complete':return dict(status(engine,row['id']),clock_status=clock['status'],clock_id=clock_id)
    _actors(engine,row['owner'],row['participants'])
    def finish(rolls):
        def apply(e,a,*ps):
            current=_row(e,row['id']);original=current['pending_work']
            actual=SF.event(e,W.actor_index(e)[actor.entity_id],options['roll_id'])
            if actual is None or actual.state!='final' or actual.final!=rolls[0]:raise ValueError('actual completed native skill roll required')
            result=_finish_work(e,current,e._clock_invocations[clock_id],interval_id,seconds,
                                original['context'],original['start'],actual.final,contribution)
            current['events'][-1].update(attempt_request=deepcopy(declared),attempt_fingerprint=TX.request_fingerprint(declared))
            del current['pending_work']
            return result
        return G.transition(engine,row['owner'],apply,participants=row['participants'])
    previous=getattr(engine,CLOCK.ACTIVE,None);setattr(engine,CLOCK.ACTIVE,clock_id)
    try:
        basis={'job_intent':row['intent'],'interval_id':interval_id,'attempt':declared,'context':pending['context']}
        return SF.sequence(engine,clock_id,basis,[(actor,skill,options)],finish)
    finally:setattr(engine,CLOCK.ACTIVE,previous)


def interrupt(engine,job_id,*,reason):
    import state_grants as G
    row=_checked_row(engine,job_id);_text(reason,'job interruption reason')
    if 'pending_work' in row:raise ValueError('resolve the actual pending job interval first')
    if row['status']!='active':raise ValueError('only an active job can be interrupted')
    def apply(e,a,*ps):
        current=_row(e,job_id);current['status']='paused'
        current['events'].append({'kind':'interrupt','at':e.elapsed_seconds,'reason':reason})
        return status(e,job_id)
    return G.transition(engine,row['owner'],apply,participants=row['participants'])


def resume(engine,job_id,*,reason,context=None):
    import state_grants as G
    row=_checked_row(engine,job_id);_text(reason,'job resumption reason')
    if row['status']!='paused' or row['definition']['resume']=='forbid':raise ValueError('selected job policy forbids resumption')
    _actors(engine,row['owner'],row['participants'])
    def apply(e,a,*ps):
        current=_row(e,job_id);observed=_context(e,a,ps,current['context']['observations'] if context is None else context)
        if current['definition']['resume']=='reset':current['progress_seconds']=current['total']=0
        current['context']=observed;current['end_seconds']=e.elapsed_seconds;current['status']=_terminal(current)
        current['events'].append({'kind':'resume','at':e.elapsed_seconds,'day':observed['day'],'context':observed,'reason':reason})
        return status(e,job_id)
    return G.transition(engine,row['owner'],apply,participants=row['participants'])


def run_fixed(engine,owner,participants,*,seconds,source,context=None,job_id=None,credit=None):
    """Native adapters call this after their source eligibility checks."""
    import state_grants as G
    _actors(engine,owner,participants);C.integer(seconds,'fixed job seconds',1)
    def apply(e,a,*ps):
        state=_state(e)
        identity=job_id
        if identity is None:
            state['sequence']+=1;identity='native-job:'+str(state['sequence'])
        _start(e,a,ps,job_id=identity,source=source,policy={'required_seconds':seconds,'credit':credit},context=context)
        return _work(e,_row(e,identity),interval_id='complete',seconds=seconds)
    return G.transition(engine,owner,apply,participants=participants)


def training_policy():
    # Existing native teaching consumers perform their own sourced eligibility.
    return {'family':'training_hour','applications':['*'],'same_day':True}


def credit(engine,owner,target,*,credit_id,application,family,minimum_seconds):
    W.require_actors(engine,owner,target);_text(credit_id,'completed job credit');_text(application,'credit application')
    _text(family,'credit family');C.integer(minimum_seconds,'credit minimum duration',1)
    validate_world(engine,W.actor_index(engine))
    receipt=target.custom_conditions.get(CREDITS,{}).get(credit_id)
    if type(receipt) is not dict:raise ValueError('actual completed job credit required')
    row=_row(engine,receipt.get('job_id'))
    if row['status']!='complete' or row['owner'] is not owner or row['credits'].get(target.entity_id) is not receipt:
        raise ValueError('actual completed job provider and participant credit required')
    if receipt['family']!=family or receipt['seconds']<minimum_seconds or not _compatible(receipt,application):
        raise ValueError('incompatible job credit application or duration')
    if receipt['end']>engine.elapsed_seconds:raise ValueError('job credit claims future time')
    if receipt['same_day'] and (owner.spec.get('frequency_state',{}).get('day',0)!=receipt['day'] or target.spec.get('frequency_state',{}).get('day',0)!=receipt['day']):
        raise ValueError('shared job credit calendar changed')
    if application in receipt['claims']:raise ValueError('job credit application already consumed')
    return receipt


def consume(target,credit_id,application):
    receipt=target.custom_conditions.get(CREDITS,{}).get(credit_id)
    if type(receipt) is not dict or not _compatible(receipt,application) or application in receipt['claims']:
        raise ValueError('actual unused compatible job credit required')
    receipt['claims'].append(application)


def apply_credit(engine,owner,target,**application):
    """Public transactional use for external, source-validated consumers."""
    import state_grants as G
    W.require_actors(engine,owner,target)
    def apply(e,a,t):
        receipt=credit(e,a,t,**application)
        consume(t,receipt['id'],application['application'])
        return deepcopy(receipt)
    return G.transition(engine,owner,apply,participants=(target,))


def _validate_context(engine,actors,row,context):
    if type(context) is not dict or set(context)!={'day','round','gaps','observations'}:raise ValueError('actual job context required')
    for key in ('day','round','gaps'):C.integer(context[key],'job context '+key,0)
    if context['day']>min(c.spec.get('frequency_state',{}).get('day',0) for c in (row['owner'],*row['participants'])) or context['round']>engine.round_no or context['gaps']>len(engine.unresolved_time_intervals):
        raise ValueError('job context claims future world state')
    if context['observations']!=_data(context['observations']):raise ValueError('plain job context required')


def _validate(engine,actors):
    state=getattr(engine,'_activity_jobs',None)
    if state is None:
        if any(c.custom_conditions.get(CREDITS) for c in actors.values()):raise ValueError('orphan job time credits')
        if any('job_id' in row for row in getattr(engine,'_extended_checks',{}).values()):raise ValueError('orphan native extended jobs')
        return
    _state(engine)
    occupied={}
    for identity,row in state['jobs'].items():
        if identity!=row['id'] or _row(engine,identity) is not row:raise ValueError('job identity mismatch')
        owner=row['owner'];participants=row['participants'];policy=definition(row['definition'])
        if policy!=row['definition']:raise ValueError('job policy must be normalized')
        if type(participants) is not list or len({id(c) for c in (owner,*participants)})!=len(participants)+1:
            raise ValueError('distinct job participants required')
        if any(actors.get(c.entity_id) is not c for c in (owner,*participants)):raise ValueError('actual world job participants required')
        events=row['events']
        pending=row.get('pending_work')
        if pending is not None:
            expected={'id','seconds','start','context','clock_id'}
            if policy['target'] is not None:expected|={'attempt','attempt_fingerprint'}
            if (type(pending) is not dict or set(pending)!=expected
                    or row['status']!='active'
                    or pending['context']!=row['context']
                    or pending['clock_id']!='activity-job:'+TX.request_fingerprint({'job_id':identity,'interval_id':pending['id']})):
                raise ValueError('actual pending job time interval required')
            _text(pending['id'],'pending work');C.integer(pending['seconds'],'pending work seconds',1)
            if policy['target'] is not None:
                declaration=pending['attempt']
                if (pending['seconds']!=policy['interval_seconds'] or type(declaration) is not dict
                        or declaration.get('actor_id') not in [c.entity_id for c in (owner,*participants)]
                        or pending['attempt_fingerprint']!=TX.request_fingerprint(declaration)):
                    raise ValueError('actual pending native skill attempt required')
            C.integer(pending['start'],'pending work start',row['end_seconds'],engine.elapsed_seconds)
            clock=getattr(engine,'_clock_invocations',{}).get(pending['clock_id'])
            if clock is None:
                if engine.elapsed_seconds!=pending['start']:raise ValueError('pending work lost its actual clock')
            elif (clock['start']!=pending['start'] or clock['intent']!={'seconds':pending['seconds'],
                    'actors':[c.entity_id for c in (owner,*participants)],'source':row['source']}):
                raise ValueError('pending work belongs to another clock invocation')
        if type(events) is not list or not events or events[0]['kind']!='start':raise ValueError('job start evidence required')
        worked=progress=total=attempts=0;disposition='active';end=events[0]['at'];context=events[0]['context'];seen=set();last_work_end=None
        _validate_context(engine,actors,row,context)
        last_event_at=end
        initial=dict(row,progress_seconds=0,total=0,attempts=0);disposition=_terminal(initial)
        for index,event in enumerate(events):
            if index==0:
                C.integer(end,'job start time',0)
                C.integer(event['day'],'job start day',0)
                if event['day']!=context['day']:raise ValueError('job start calendar mismatch')
                continue
            event_start=event.get('start',event.get('at'))
            C.integer(event_start,'job event time',0)
            if event_start<last_event_at:raise ValueError('job event chronology changed')
            if event['kind']=='work':
                if disposition!='active':raise ValueError('work after a paused or terminal job')
                _text(event['id'],'work interval');C.integer(event['seconds'],'work seconds',1)
                if event['id'] in seen:raise ValueError('duplicate job interval')
                seen.add(event['id'])
                C.integer(event['start'],'work start',0);C.integer(event['end'],'work end',0)
                pause=policy['required_pause_seconds'] if last_work_end is not None else 0
                gap=event['start']-end
                adjacency=pause if events[index-1]['kind']=='work' else 0
                if event['end']-event['start']!=event['seconds'] or gap<0 or (last_work_end is not None and event['start']-last_work_end<pause) or (policy['continuity']=='continuous' and gap!=adjacency):
                    raise ValueError('job interval has no adjacent elapsed-time proof')
                if event['context']!=context or event['day']!=context['day']:raise ValueError('job interval context changed')
                C.integer(event['day'],'work calendar day',0)
                roll=event['roll']
                if (roll is not None)!=(policy['target'] is not None):raise ValueError('native job attempt evidence required')
                if roll is not None:
                    if event['seconds']!=policy['interval_seconds']:raise ValueError('job attempt interval mismatch')
                    _native_roll(roll)
                    contribution=event['contribution']
                    if type(contribution) is not dict or set(contribution)!={'actor_id','skill'} or contribution['actor_id'] not in [c.entity_id for c in (owner,*participants)]:raise ValueError('actual job contributor evidence required')
                    _text(contribution['skill'],'job contributor skill')
                    if 'attempt_request' in event:
                        import skill_feature_actions as SF
                        request=event['attempt_request'];native=SF.event(engine,actors[contribution['actor_id']],request['roll_id'])
                        if (event.get('attempt_fingerprint')!=TX.request_fingerprint(request)
                                or (request['actor_id'],request['skill'])!=(contribution['actor_id'],contribution['skill'])
                                or native is None or native.state!='final' or native.final is not roll):
                            raise ValueError('job attempt lost its actual native skill observation')
                    attempts+=1;total+=roll.total
                worked+=event['seconds'];progress+=event['seconds'];end=event['end']
                last_work_end=end
                for actor in (owner,*participants):occupied.setdefault(actor.entity_id,[]).append((event['start'],end,identity))
                disposition=_terminal(dict(row,progress_seconds=progress,total=total,attempts=attempts))
            elif event['kind']=='interrupt':
                C.integer(event['at'],'job interruption time',0)
                if disposition!='active' or event['at']<end:raise ValueError('invalid job interruption')
                _text(event['reason'],'interruption reason');disposition='paused'
            elif event['kind']=='resume':
                C.integer(event['at'],'job resume time',0);C.integer(event['day'],'job resume day',0)
                if disposition!='paused' or policy['resume']=='forbid' or event['at']<end:raise ValueError('invalid job resumption')
                _text(event['reason'],'resumption reason')
                if policy['resume']=='reset':progress=total=0
                end=event['at'];context=event['context']
                _validate_context(engine,actors,row,context)
                if event['day']!=context['day']:raise ValueError('resume calendar mismatch')
                disposition=_terminal(dict(row,progress_seconds=progress,total=total,attempts=attempts))
            else:raise ValueError('unknown job event')
            last_event_at=event.get('end',event.get('at'))
            if event.get('end',event.get('at',0))>engine.elapsed_seconds:raise ValueError('job claims future elapsed time')
        if end>engine.elapsed_seconds or (row['worked_seconds'],row['progress_seconds'],row['total'],row['attempts'],row['end_seconds'],row['context'],row['status'])!=(worked,progress,total,attempts,end,context,disposition):
            raise ValueError('job progress does not match actual recorded intervals')
        for key in ('worked_seconds','progress_seconds','attempts','end_seconds'):C.integer(row[key],'job '+key,0)
        C.integer(row['total'],'job total')
        for day in {event['day'] for event in events if 'day' in event}:_daily(state,row,day,{})
        recipients={c.entity_id:c for c in participants or [owner]}
        expected=set(recipients) if disposition=='complete' and policy['credit'] is not None else set()
        if set(row['credits'])!=expected:raise ValueError('job credit completion evidence mismatch')
        for actor_id,receipt in row['credits'].items():
            recipient=recipients[actor_id]
            for key in ('start','end','day','seconds'):C.integer(receipt[key],'job credit '+key,1 if key=='seconds' else 0)
            if receipt['id']!=TX.request_fingerprint({'job_id':identity,'recipient_id':actor_id}):raise ValueError('job credit identity changed')
            if recipient.custom_conditions.get(CREDITS,{}).get(receipt['id']) is not receipt:raise ValueError('job credit graph binding changed')
            if (receipt['job_id'],receipt['recipient_id'],receipt['owner_id'],receipt['source'],receipt['seconds'],receipt['day'],receipt['end'])!=(identity,actor_id,owner.entity_id,row['source'],progress,context['day'],end):
                raise ValueError('job credit producer evidence changed')
            if any(receipt[key]!=value for key,value in policy['credit'].items()):raise ValueError('job credit policy changed')
            eligible=events
            if policy['resume']=='reset':eligible=events[max((i+1 for i,event in enumerate(events) if event['kind']=='resume'),default=0):]
            if receipt['start']!=next(event['start'] for event in eligible if event['kind']=='work'):raise ValueError('job credit start changed')
            claims=receipt['claims']
            if type(claims) is not list or any(type(x) is not str or not x.strip() or not _compatible(receipt,x) for x in claims) or len(set(claims))!=len(claims):
                raise ValueError('distinct compatible job credit applications required')
    for actor in actors.values():
        for identity,receipt in actor.custom_conditions.get(CREDITS,{}).items():
            row=state['jobs'].get(receipt.get('job_id'))
            if type(row) is not dict or row['credits'].get(actor.entity_id) is not receipt or receipt['id']!=identity:
                raise ValueError('orphan or copied job time credit')
    for legacy in getattr(engine,'_extended_checks',{}).values():
        if 'job_id' not in legacy:continue
        job=state['jobs'].get(legacy['job_id'])
        if job is None or legacy['actor'] is not job['owner']:raise ValueError('native extended job binding changed')
        work=[event for event in job['events'] if event['kind']=='work']
        expected_status={'active':'in_progress','complete':'complete','failed':'exhausted'}.get(job['status'])
        if (tuple(legacy['interval_ids']),tuple(legacy['rolls']),legacy['result'].total,legacy['result'].attempts_used,legacy['result'].attempt_limit)!=(tuple(event['id'] for event in work),tuple(event['roll'] for event in work),job['total'],job['attempts'],job['definition']['attempt_limit']):
            raise ValueError('native extended result diverges from its activity job')
        if expected_status is not None and legacy['result'].status!=expected_status:raise ValueError('native extended job disposition mismatch')
    for intervals in occupied.values():
        ordered=sorted(intervals)
        if any(first[1]>second[0] for first,second in zip(ordered,ordered[1:])):raise ValueError('participant job time overlaps')


def validate_world(engine,actors):
    try:_validate(engine,actors)
    except (KeyError,TypeError,AttributeError,IndexError) as exc:raise ValueError('malformed activity job state') from exc
