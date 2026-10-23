"""Completed ordinary training hours shared by native reward consumers."""
from copy import deepcopy
import common_checks as C
import world_entities as W
import pokemon_progression as P
import resolution_transaction as TX

KEY='completed_training_hour'
SESSIONS='_completed_training_hours'


def require_safety(safe):
    import training_eligibility as E
    E.require_safety(safe)


def complete(engine,trainer,targets,*,safe,reason,request_id):
    import state_grants as G
    require_safety(safe)
    if type(reason) is not str or not reason.strip():raise ValueError('training safety and completion reason required')
    if type(targets) not in (list,tuple) or not 1<=len(targets)<=6 or len({id(t) for t in targets})!=len(targets):
        raise ValueError('one to six distinct training participants required')
    W.require_actors(engine,trainer,*targets);P.source(engine.r,P.TRAINING)
    request={'trainer_id':trainer.entity_id,'target_ids':[t.entity_id for t in targets],'safe':safe,'reason':reason}
    prior=TX.replay_result(trainer.custom_conditions.get(SESSIONS,{}),request_id,request,fingerprint_field='intent')
    if prior is not None:return deepcopy(prior['result'])
    import training_eligibility as E
    eligibility=E.prepare(engine,trainer,targets,E.native('training_hour'),safe=safe)
    import training_rewards as R,activity_jobs as JOBS
    value=R.policy(eligibility,3600,[{'id':'completed-hour','source':P.TRAINING,'kind':'credit',
        'publication':'ordinary','policy':JOBS.training_policy()}],identity='native:completed-training-hour')
    result=R.execute(engine,trainer,targets,value,request_id='hour:'+request_id,safe=safe,reason=reason,
                     _eligibility=eligibility,_session_id=request_id)
    return deepcopy(result['awards'][0]['result'])


def publish(engine,trainer,targets,job,*,request_id,reason,eligibility,started_at,reward_record_id):
    """Expose a completed actual job to existing ordinary teaching consumers."""
    import activity_jobs as JOBS
    actual=JOBS._row(engine,job['job_id'])
    if actual['owner'] is not trainer or tuple(actual['participants'])!=tuple(targets) or actual['status']!='complete' or actual['source']!=P.TRAINING or actual['progress_seconds']!=3600:
        raise ValueError('actual ordinary training job required for publication')
    request={'trainer_id':trainer.entity_id,'target_ids':[t.entity_id for t in targets],'safe':True,'reason':reason}
    facts={}
    for target in targets:
        row={'source':P.TRAINING,'trainer_id':trainer.entity_id,'session_id':request_id,'day':eligibility['day'],'hours':1,
             'started_at':started_at,'completed_at':engine.elapsed_seconds,'safe':True,'reason':reason,
             'job_id':job['job_id'],'credit_id':job['credit_ids'][target.entity_id],'reward_record_id':reward_record_id}
        facts[target.entity_id]=deepcopy(row);target.spec[KEY]=dict(row,applications=[])
    result={'request_id':request_id,'trainer_id':trainer.entity_id,'target_ids':request['target_ids'],
            'started_at':started_at,'completed_at':engine.elapsed_seconds,'source':P.TRAINING,'safe':True,'reason':reason,
            'eligibility':deepcopy(eligibility),'reward_record_id':reward_record_id}
    trainer.custom_conditions.setdefault(SESSIONS,{})[request_id]={'intent':TX.request_fingerprint(request),'request':deepcopy(request),'credits':facts,'result':deepcopy(result)}
    return result


def credit(engine,trainer,target,application):
    W.require_actors(engine,trainer,target);P.source(engine.r,P.TRAINING)
    if type(application) is not str or not application.strip():raise ValueError('training application identity required')
    row=target.spec.get(KEY)
    if type(row) is not dict:raise ValueError('actual completed ordinary training hour required')
    session=trainer.custom_conditions.get(SESSIONS,{}).get(row.get('session_id'))
    if type(session) is not dict or TX.request_fingerprint(session.get('request'))!=session.get('intent'):
        raise ValueError('original completed training session required')
    facts=session.get('credits',{}).get(target.entity_id)
    if facts!={k:v for k,v in row.items() if k!='applications'}:
        raise ValueError('completed training participant receipt changed')
    if row.get('source')!=P.TRAINING or row.get('trainer_id')!=trainer.entity_id or row.get('safe') is not True:
        raise ValueError('training source, provider or safety mismatch')
    day=trainer.spec.get('frequency_state',{}).get('day',0)
    C.integer(day,'current training day',0);C.integer(row.get('day'),'completed training day',0)
    C.integer(row.get('hours'),'completed training hours',1)
    if row['hours']!=1:raise ValueError('one completed training hour required')
    if row.get('day')!=day or target.spec.get('frequency_state',{}).get('day',0)!=day or target.spec.get('trainer_id')!=trainer.entity_id:
        raise ValueError('completed training ownership/calendar mismatch')
    C.integer(row.get('started_at'),'training start',0);C.integer(row.get('completed_at'),'training completion',0)
    if row['completed_at']-row['started_at']!=3600 or row['completed_at']>engine.elapsed_seconds:
        raise ValueError('training hour has not actually completed')
    apps=row.get('applications')
    if type(apps) is not list or any(type(a) is not str or not a.strip() for a in apps) or len(set(apps))!=len(apps):
        raise ValueError('distinct training applications required')
    if application in apps:raise ValueError('training application already consumed its completed hour')
    import activity_jobs as JOBS
    JOBS.credit(engine,trainer,target,credit_id=row.get('credit_id'),application=application,
                family='training_hour',minimum_seconds=3600)
    return row


def consume(target,application):
    import activity_jobs as JOBS
    JOBS.consume(target,target.spec[KEY]['credit_id'],application)
    target.spec[KEY]['applications'].append(application)
