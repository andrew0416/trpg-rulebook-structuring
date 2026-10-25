"""Actual object repair with existing material, elapsed-job and recovery owners."""
import arithmetic_policy as NUMERIC
from copy import deepcopy
from dataclasses import asdict
import common_checks as C,crafting_recipes as Q,state_grants as G,world_entities as W
import special_entities as S,recovery_resolution as REC,activity_jobs as JOBS
import resolution_transaction as TX,roll_context as R,turn as TURN,arithmetic_policy as M
import environmental_item_state as ENVIRONMENTAL_ITEMS

FIELD='_object_repairs'
KINDS=('pokebot','vehicle','item_instance')


def declaration(value):
    Q._fields(value,('id','source','target_kinds','method','access','requirements','materials','action','seconds','check','effects','module','trigger','daily_limit'))
    Q._text(value['id']);Q._text(value['source']);Q._names(value['target_kinds'])
    if not set(value['target_kinds'])<=set(KINDS):raise ValueError('actual mechanical/item repair kinds required')
    if value['method'] not in ('repair','organic','module') or value['access'] not in ('owner','adjacent','observed'):raise ValueError('explicit repair method/access required')
    if type(value['requirements']) is not list:raise ValueError('actual repair qualifications required')
    for node in value['requirements']:Q._condition(node)
    Q.material_groups(value['materials']);C.integer(value['seconds'],'actual repair seconds',0)
    if value['action'] not in ('extended','standard','shift','swift','free'):raise ValueError('finite actual repair action required')
    if value['seconds'] and value['action']!='extended':raise ValueError('elapsed repair requires its extended action')
    if value['action']=='extended' and not value['seconds']:raise ValueError('extended repair needs an explicit positive duration')
    if value['check'] is not None:
        Q._fields(value['check'],('skill','dc'));Q._text(value['check']['skill'])
        if value['check']['dc'] is not None:C.integer(value['check']['dc'],'actual repair DC')
    if type(value['effects']) is not list or not value['effects']:raise ValueError('finite actual restoration effects required')
    resources=set()
    for effect in value['effects']:
        Q._fields(effect,('resource','provider','amount','ratio','maximum','subset') if effect.get('resource')=='breaches' else ('resource','provider','amount','ratio','maximum'))
        if effect['resource'] not in ('hp','injuries','disabled','patches','breaches') or effect['resource'] in resources:raise ValueError('distinct repair resources required')
        if effect['resource']=='breaches':
            if effect['subset'] not in ('patched_first','unpatched_first') or not value['seconds'] or value['method']!='repair':raise ValueError('actual structural repair needs its subset and positive repair period')
        resources.add(effect['resource'])
        if effect['provider'] not in ('declared','check','cost','fraction'):raise ValueError('explicit repair formula provider required')
        if effect['provider']=='declared':C.integer(effect['amount'],'authored repair quantity',0)
        elif effect['amount'] is not None:raise ValueError('calculated repair has no invented supplied amount')
        if effect['provider']=='fraction' and effect['resource']!='hp':raise ValueError('fraction repair requires actual maximum HP')
        if effect['provider']=='check' and value['check'] is None:raise ValueError('repair formula needs its actual skill check')
        if type(effect['ratio']) is not list or len(effect['ratio'])!=2:raise ValueError('explicit repair formula ratio required')
        C.integer(effect['ratio'][0],'repair numerator',0);C.integer(effect['ratio'][1],'repair denominator',1)
        if effect['maximum'] is not None:C.integer(effect['maximum'],'repair period quantity limit',0)
        if effect['resource']=='disabled' and (effect['provider']!='declared' or effect['amount']!=1 or effect['ratio']!=[1,1]):raise ValueError('item repair restores an existing disabled state once')
        if effect['resource']=='injuries' and value['method']=='repair' and not value['seconds']:raise ValueError('injury repair needs an actual positive repair period')
    module=value['module']
    if module is not None:
        Q._fields(module,('module_id','instance_id'));Q._text(module['module_id'])
        if module['instance_id'] is not None:Q._text(module['instance_id'])
    if (module is not None)!=(value['method']=='module'):raise ValueError('module repair needs its actual installed provider')
    if value['trigger'] is not None:
        Q._text(value['trigger'])
        if module is None:raise ValueError('module trigger requires an installed module')
    if value['daily_limit'] is not None:C.integer(value['daily_limit'],'actual target daily repair uses',1)
    return deepcopy(value)


def _state(e):return getattr(e,FIELD,{'version':1,'policies':{},'requests':{},'events':{}})
def _sign(row):return dict(row,sha256=TX.request_fingerprint(row))
def _verify(row):
    if type(row) is not dict or row.get('sha256')!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('actual repair evidence changed')


def _target(e,uid):
    target=getattr(e,'_physical_objects',{}).get(uid)
    if not target or target.get('kind') not in KINDS:raise ValueError('actual registered mechanical or item repair target required')
    W.require_usable_object(target)
    if target['kind'] in ('pokebot','vehicle'):S.validate_record(e,target)
    else:W.require_physical_access(target);Q._selected(e,target['item_rule_id'])
    return target


def restore_item(e,uid):
    target=_target(e,uid)
    if target['kind']!='item_instance' or not _disabled(target):raise ValueError('actual disabled item required')
    target['disabled']=False
    ENVIRONMENTAL_ITEMS.repaired(e,target)
    return {'resource':'disabled','before':True,'after':False,'applied':1}


def _disabled(target):
    return W.physical_lifecycle(target)['disabled'] or ENVIRONMENTAL_ITEMS.active(target,'electrical_failure')


def observe_module_event(e,actor,target_id,source,event,*,event_id,reason):
    W.require_actors(e,actor);Q._text(source);Q._text(event);Q._text(event_id);Q._text(reason);Q._selected(e,source);_target(e,target_id)
    def apply(staged,c):
        state=_state(staged);setattr(staged,FIELD,state)
        if event_id in state['events']:raise ValueError('actual module event identity already recorded')
        state['events'][event_id]=_sign({'actor_id':c.entity_id,'target_id':target_id,'source':source,'event':event,'at':staged.elapsed_seconds,'reason':reason,'used_by':None})
        return deepcopy(state['events'][event_id])
    return G.transition(e,actor,apply)


def _key(target,value):return TX.request_fingerprint([target['id'],value['source'],value['method'],None if value['module'] is None else value['module']['module_id']])
def _limit(value):return {'daily_limit':value['daily_limit']}
def _day(e,target,actor,limited):
    if not limited:return actor.spec.get('frequency_state',{}).get('day',0)
    owner=W.actor_index(e).get(target.get('owner_id'))
    if owner is None:raise ValueError('target daily repair quota requires its actual owner calendar')
    day=owner.spec.get('frequency_state',{}).get('day',0);C.integer(day,'actual repair owner day',0);return day


def _preflight(e,actor,uid,value,inputs,accessible,event_id,started_at=None):
    W.require_actors(e,actor);Q._selected(e,value['source']);target=_target(e,uid)
    if target['kind'] not in value['target_kinds']:raise ValueError('repair target kind does not match its policy')
    if value['access']=='owner' and target.get('owner_id')!=actor.entity_id:raise ValueError('actual repair owner authority required')
    if value['access']=='adjacent':
        distance=W.distance_known(actor,target)
        if distance is None or distance>1:raise ValueError('actual adjacent repair access required')
    if value['access']=='observed' and accessible is not True:raise ValueError('actual observed repair access required')
    if not all([Q._observe(e,actor,node,set()) for node in value['requirements']]):raise ValueError('actual repair qualification/tool unavailable')
    view=S.validate_record(e,target) if target['kind']!='item_instance' else None
    if value['method']=='organic' and (target['kind']!='pokebot' or not view['component_projection']['organic_healing_allowed']):raise ValueError('actual target does not permit organic healing')
    if value['module'] is not None:
        if target['kind']!='pokebot':raise ValueError('actual installed Pokebot module required')
        module=value['module'];matches=[c for c in target['components'] if c.get('module_id')==module['module_id'] and (module['instance_id'] is None or c['instance_id']==module['instance_id'])]
        if len(matches)!=1:raise ValueError('one actual installed repair module provider required')
        provider=e._physical_objects[matches[0]['instance_id']];W.require_usable_object(provider)
        if any(W.physical_lifecycle(provider)[x] for x in ('disabled','suppressed')):raise ValueError('actual repair module provider is disabled/suppressed')
        ENVIRONMENTAL_ITEMS.require_usable(e,provider)
    event=None
    if value['trigger'] is not None:
        event=_state(e)['events'].get(event_id)
        if not event or event['target_id']!=uid or event['actor_id']!=actor.entity_id or event['source']!=value['source'] or event['event']!=value['trigger'] or event['at']!=(e.elapsed_seconds if started_at is None else started_at) or event['used_by'] is not None:raise ValueError('current actual module trigger observation required')
        _verify(event)
    elif event_id is not None:raise ValueError('trigger-free repair has no module event')
    for effect in value['effects']:
        resource=effect['resource']
        if resource=='disabled' and target['kind']!='item_instance' or resource=='hp' and target['kind']=='item_instance' or resource=='injuries' and target['kind']!='pokebot' or resource in ('patches','breaches') and target['kind']!='vehicle':raise ValueError('repair resource does not exist on the actual target')
    if not any(_disabled(target) if x['resource']=='disabled' else target['hp']<target['max_hp'] if x['resource']=='hp' else target['breaches']>target['patched_breaches'] if x['resource']=='patches' else target['breaches']>0 if x['resource']=='breaches' else target['injuries']>0 for x in value['effects']):raise ValueError('repair requires actual damage or disabled state')
    if value['seconds']:JOBS._actors(e,actor,())
    payment=Q.prepare_materials(e,actor,value['materials'],inputs=inputs)
    if any(x['provider']=='cost' for x in value['effects']) and (not payment['payments'] or any(x['kind']!='value' for x in payment['payments'])):raise ValueError('cost-based repair requires actual monetary/scrap-value payment')
    day=_day(e,target,actor,value['daily_limit'] is not None);key=_key(target,value);state=_state(e);policy=state['policies'].get(key)
    if policy is not None and policy['limits']!=_limit(value):raise ValueError('actual target/source repair quota cannot change by renaming')
    used=sum(row['result']['policy_key']==key and row['result']['day']==day for row in state['requests'].values())
    if value['daily_limit'] is not None and used>=value['daily_limit']:raise ValueError('actual target daily repair quota exhausted')
    return target,payment,day,key,event


def _amount(target,effect,payments,check):
    provider=effect['provider']
    if provider=='declared':amount=effect['amount']
    elif provider=='check':amount=check.total
    elif provider=='cost':amount=sum(x['amount'] for x in payments)
    else:
        if target['kind']=='item_instance':raise ValueError('item repair has no maximum HP fraction')
        amount=target['max_hp']
    return NUMERIC.ratio(max(0,amount)*effect['ratio'][0],effect['ratio'][1])


def execute(e,actor,target_id,value,*,request_id,reason,inputs=None,accessible=None,event_id=None,roll_options=None):
    value=declaration(value);Q._text(request_id);Q._text(reason);W.require_actors(e,actor);validate_world(e,W.actor_index(e))
    options={} if roll_options is None else deepcopy(roll_options);inputs={} if inputs is None else deepcopy(inputs)
    if type(options) is not dict:raise ValueError('actual native repair roll options required')
    intent={'actor_id':actor.entity_id,'target_id':target_id,'declaration':value,'inputs':inputs,'accessible':accessible,'event_id':event_id,'reason':reason,'roll_options':options}
    saved=_state(e)['requests'].get(request_id)
    if saved is not None:
        if saved['fingerprint']!=TX.request_fingerprint(intent):raise ValueError('actual repair request changed intent')
        return deepcopy(saved['result'])
    _preflight(e,actor,target_id,value,inputs,accessible,event_id)
    def apply(staged,c):
        state=_state(staged);setattr(staged,FIELD,state);started_at=staged.elapsed_seconds;target,payment,day,key,event=_preflight(staged,c,target_id,value,inputs,accessible,event_id);check=value['check']
        if check is None and options:raise ValueError('check-free repair has no roll inputs')
        if check is not None:R.plan(staged,c,check['skill'],purpose='repair:'+value['id'],**options)
        if not TURN.spend(staged,c,value['action'],value['source']):return C.PendingDecision('actual repair action unavailable')
        rolled=None if check is None else staged.skill_roll(c,check['skill'],**options)
        if rolled is not None and check['dc'] is not None:
            import skill_feature_actions as SF
            identity=SF._observed(staged,c,rolled,options)[0] if c.entity_id in getattr(staged,'_let_me_help_offers',{}) else options.get('roll_id')
            SF.resolve_check(staged,c,check['skill'],check['dc'],rolled,options)
            if identity is not None:
                observed=SF.event(staged,c,identity)
                if observed is not None and observed.final is not None:rolled=observed.final
        job=None
        if value['seconds']:job=JOBS.run_fixed(staged,c,(),seconds=value['seconds'],source=value['source'],context={'target_id':target_id,'repair':value['id'],'reason':reason})['job_id']
        state=_state(staged);target,payment,_,_,event=_preflight(staged,c,target_id,value,inputs,accessible,event_id,started_at=started_at)
        payments=Q.pay_materials(staged,c,payment['payments']);passed=rolled is None or check['dc'] is None or rolled.total>=check['dc'];restored=[]
        if passed:
            for effect in value['effects']:
                amount=_amount(target,effect,payments,rolled);resource=effect['resource']
                if resource=='disabled':restored.append(restore_item(staged,target_id))
                elif resource in ('patches','breaches'):
                    import repair_breach as BREACH
                    restored.append(BREACH.restoration(target,resource,amount,maximum=effect['maximum'],subset=effect.get('subset')))
                else:
                    before=target[resource];maximum=effect['maximum']
                    if resource=='injuries' and value['method']=='repair':
                        at_center=Q._observe(staged,c,{'kind':'region','names':['pokemon_center']},set())
                        native=3 if at_center else 1;maximum=native if maximum is None else min(native,maximum)
                    result=REC.resolve(before,amount,resource=resource,mode='remove' if resource=='injuries' else 'add',ceiling=target.get('max_hp') if resource=='hp' else None,allowance=maximum)
                    target[resource]=result['after'];restored.append(result)
        if target['kind'] in ('pokebot','vehicle'):S.validate_record(staged,target)
        if event is not None:
            event.pop('sha256');event['used_by']=request_id;event['sha256']=TX.request_fingerprint(event)
        result={'actor_id':c.entity_id,'target_id':target_id,'source':value['source'],'method':value['method'],'policy_key':key,'day':day,'at':staged.elapsed_seconds,'action':value['action'],'seconds':value['seconds'],'job_id':job,'passed':passed,'check':None if rolled is None else dict(asdict(rolled),total=rolled.total),'materials':payments,'restored':restored,'event_id':event_id}
        state['policies'].setdefault(key,_sign({'target_id':target_id,'source':value['source'],'method':value['method'],'module_id':None if value['module'] is None else value['module']['module_id'],'limits':_limit(value)}));state['requests'][request_id]=_sign({'intent':deepcopy(intent),'fingerprint':TX.request_fingerprint(intent),'result':deepcopy(result)})
        validate_world(staged,W.actor_index(staged));return result
    return G.transition(e,actor,apply)


def vehicle_policy(cost,seconds):
    C.integer(cost,'actual vehicle repair cost',1);C.integer(seconds,'observed extended repair seconds',1)
    return {'id':'native-vehicle-value-repair','source':'supp-polygon/차량-제작-가이드라인','target_kinds':['vehicle'],'method':'repair','access':'observed','requirements':[],'materials':[{'id':'repair','options':[{'kind':'value','category':'차량','amount':cost,'scrap':True,'money':True}]}],'action':'extended','seconds':seconds,'check':None,'effects':[{'resource':'hp','provider':'cost','amount':None,'ratio':[2,1],'maximum':None}],'module':None,'trigger':None,'daily_limit':None}


def regeneration_policy(component_id,event):
    if event not in ('breather','return_ball'):raise ValueError('actual Regenerator trigger required')
    return {'id':'native-repair-nanites-regenerator','source':'ability/재생력','target_kinds':['pokebot'],'method':'module','access':'owner','requirements':[],'materials':[],'action':'free','seconds':0,'check':None,'effects':[{'resource':'hp','provider':'fraction','amount':None,'ratio':[1,3],'maximum':None}],'module':{'module_id':'repair_nanites','instance_id':component_id},'trigger':event,'daily_limit':2}


def finish_ball(e,actor,*,ball_id,roll):
    """Existing capture identity and one irreversible attempt, shared repair owner."""
    import pokemon_activities as P
    record=actor.spec.get('broken_balls',{}).get(ball_id)
    if not isinstance(record,dict) or record.get('cause')!='failed_capture' or record.get('status')!='broken':raise ValueError('repairable failed-capture ball instance required')
    attempt=actor.spec.get('capture_attempts',{}).get(record.get('capture_attempt_id'))
    if not attempt or attempt.get('status')!='broken' or attempt.get('captured') or not attempt.get('hit'):raise ValueError('actual failed capture and observed breakage required')
    name=P._text(record.get('item'),'ball item')
    if record.get('ball_kind') not in ('poke_ball','apricorn_ball'):raise ValueError('Poke Ball or Apricorn Ball prerequisite not established')
    check=P._check(e,actor,'기술학',15,roll,context=('repair_ball',ball_id))
    return G.transition(e,actor,lambda se,sa:_finish_ball_result(se,sa,ball_id,check,name),include_rulings=True)


def _finish_ball_result(e,actor,ball_id,check,name):
    record=actor.spec['broken_balls'][ball_id];attempt=actor.spec['capture_attempts'][record['capture_attempt_id']]
    record['status']='repaired' if check.passed else 'permanently_broken';attempt['status']=record['status']
    import csv_item_physical_contracts as CSV_ITEMS
    if check.passed:
        if not CSV_ITEMS.recover_cannon_ball(e,actor,attempt):
            inv=actor.spec.setdefault('items',{});inv[name]=inv.get(name,0)+1
    elif record.get('physical_instance_id'):
        ball=CSV_ITEMS.cannon_attempt_ball(e,actor,attempt)
        W.finish_physical_use(e,ball,'destroyed',{'source':name,'former_holder_id':actor.entity_id,'at':e.elapsed_seconds})
    return {'activity':'repair_ball','check':check,'ball_id':ball_id,'status':record['status']}


def validate_world(e,index):
    state=_state(e);Q._fields(state,('version','policies','requests','events'))
    if state['version']!=1 or any(type(state[x]) is not dict for x in ('policies','requests','events')):raise ValueError('known actual repair state required')
    registry=getattr(e,'_physical_objects',{})
    for key,row in state['policies'].items():
        _verify(row);Q._fields(row,('target_id','source','method','module_id','limits','sha256'))
        if row['target_id'] not in registry or key!=TX.request_fingerprint([row['target_id'],row['source'],row['method'],row['module_id']]):raise ValueError('actual repair quota owner required')
        Q._fields(row['limits'],('daily_limit',))
        if row['limits']['daily_limit'] is not None:C.integer(row['limits']['daily_limit'],'actual saved repair daily limit',1)
    counts={}
    for uid,row in state['requests'].items():
        Q._text(uid);_verify(row);Q._fields(row,('intent','fingerprint','result','sha256'));intent=row['intent'];result=row['result'];value=declaration(intent['declaration'])
        if row['fingerprint']!=TX.request_fingerprint(intent) or intent['actor_id'] not in index or intent['target_id'] not in registry or any(result[x]!=intent[x] for x in ('actor_id','target_id')):raise ValueError('actual repair request identities changed')
        C.integer(result['at'],'actual repair completion time',0,e.elapsed_seconds);C.integer(result['day'],'actual repair day',0)
        policy=state['policies'].get(result['policy_key'])
        if not policy or policy['target_id']!=intent['target_id'] or policy['source']!=value['source'] or policy['limits']!=_limit(value):raise ValueError('actual repair result source/quota changed')
        if value['seconds']:
            job=JOBS.status(e,result['job_id'])
            if job['status']!='complete' or job['owner_id']!=intent['actor_id'] or job['source']!=value['source'] or job['progress_seconds']!=value['seconds']:raise ValueError('actual completed repair time required')
        bucket=(result['policy_key'],result['day']);counts[bucket]=counts.get(bucket,0)+1
        if value['daily_limit'] is not None and counts[bucket]>value['daily_limit']:raise ValueError('actual saved repair quota exceeded')
    for uid,row in state['events'].items():
        Q._text(uid);_verify(row);Q._fields(row,('actor_id','target_id','source','event','at','reason','used_by','sha256'))
        if row['actor_id'] not in index or row['target_id'] not in registry:raise ValueError('actual module event participants required')
        C.integer(row['at'],'actual module trigger time',0,e.elapsed_seconds)
        if row['used_by'] is not None and (row['used_by'] not in state['requests'] or state['requests'][row['used_by']]['result']['event_id']!=uid):raise ValueError('module event needs its actual consuming repair')
    return True
