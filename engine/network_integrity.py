"""Separate digital pools, sourced damage/programs and real recovery clocks."""
from copy import deepcopy
from fractions import Fraction
from dataclasses import asdict
import common_checks as C,crafting_recipes as Q,world_entities as W,state_grants as G
import special_entities as S,network_connection as N,combat_damage as DAMAGE
import recovery_resolution as REC,roll_context as R,skill_modifiers as SK
import resolution_transaction as TX,turn as TURN

FIELD='_digital_integrity'
KINDS=('digital_avatar','digital_node')


def _fraction(value,label):
    if type(value) is not list or len(value)!=2:raise ValueError('explicit '+label+' ratio required')
    C.integer(value[0],label+' numerator',0);C.integer(value[1],label+' denominator',1)
    return Fraction(*value)


def declaration(value):
    Q._fields(value,('id','source','requirements','action','range','check','effect','program'));Q._text(value['id']);Q._text(value['source'])
    if value['action'] not in ('standard','shift','swift'):raise ValueError('finite actual digital action required')
    if type(value['requirements']) is not list:raise ValueError('actual digital qualification declarations required')
    for node in value['requirements']:Q._condition(node)
    if value['range'] is not None:C.integer(value['range'],'digital mapped range',0)
    check=value['check']
    if check is not None:
        Q._fields(check,('skill','purpose'));Q._text(check['skill']);Q._text(check['purpose'])
    effect=value['effect']
    if type(effect) is not dict:raise ValueError('finite digital consequence declaration required')
    kind=effect.get('kind')
    if kind=='damage':
        Q._fields(effect,('kind','damage_kind','amount','damage_class','reduction','minimum','multiplier','defensive_feature','data_outcome','recovery'))
        if effect['damage_kind'] not in ('technology','ordinary','physical_hp'):raise ValueError('separate digital/physical damage basis required')
        Q._fields(effect['amount'],('provider','value'))
        if effect['amount']['provider']=='check':
            if check is None or effect['amount']['value'] is not None:raise ValueError('actual check total has no invented supplied value')
        elif effect['amount']['provider']=='declared':C.integer(effect['amount']['value'],'authored incoming damage',0)
        else:raise ValueError('explicit actual damage value provider required')
        if effect['damage_kind']=='technology' and (check is None or SK.key(check['skill'])!=SK.key('기술학') or effect['amount']['provider']!='check'):raise ValueError('Technology code damage requires its actual native Technology roll')
        if effect['damage_class'] not in ('physical','special'):raise ValueError('explicit ordinary damage class required')
        C.integer(effect['reduction'],'authored digital reduction',0);C.integer(effect['minimum'],'digital damage minimum',0);_fraction(effect['multiplier'],'digital damage multiplier')
        if effect['defensive_feature'] is not None:
            feature=effect['defensive_feature'];Q._fields(feature,('source','names','skill'));Q._text(feature['source']);Q._names(feature['names']);Q._text(feature['skill'])
        if effect['data_outcome'] not in (None,'extracted','modified'):raise ValueError('explicit distinct safe data outcome required')
        if effect['data_outcome'] is not None and effect['damage_kind']!='technology':raise ValueError('ordinary damage cannot be safe data extraction')
        recovery=effect['recovery'];Q._fields(recovery,('seconds','amount'));C.integer(recovery['seconds'],'authored digital recovery interval',0)
        if recovery['amount'] is not None:C.integer(recovery['amount'],'authored timed Integrity recovery',1)
    elif kind=='restore':Q._fields(effect,('kind','amount'));C.integer(effect['amount'],'digital Integrity repair',0)
    elif kind=='temporary':
        Q._fields(effect,('kind','amount','maximum','seconds'));C.integer(effect['amount'],'temporary Integrity grant',0);C.integer(effect['maximum'],'temporary Integrity ceiling',0)
        if effect['seconds'] is not None:C.integer(effect['seconds'],'temporary Integrity duration',1)
    elif kind=='data':
        Q._fields(effect,('kind','outcome'))
        if effect['outcome'] not in ('extracted','modified'):raise ValueError('explicit safe server data operation required')
    else:raise ValueError('unsupported digital operation')
    program=value['program']
    if program is not None:
        Q._fields(program,('instance_id','item_rule_id','consume'));Q._text(program['instance_id']);Q._text(program['item_rule_id'])
        if type(program['consume']) is not bool:raise ValueError('explicit actual program consumption policy required')
    return deepcopy(value)


def _body(value):return {k:deepcopy(v) for k,v in value.items() if k!='id'}
def _sign(row):return dict(row,sha256=TX.request_fingerprint(row))
def _verify(row):
    if type(row) is not dict or row.get('sha256')!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('digital consequence evidence changed')
def _state(e):return getattr(e,FIELD,{'version':1,'policies':{},'requests':{},'temporary':{},'recovery':{},'data_permissions':{}})


def _target(e,uid):
    row=getattr(e,'_physical_objects',{}).get(uid)
    if row is None or row.get('kind') not in KINDS:raise ValueError('actual registered digital target required')
    S.validate_record(e,row);return row


def _program(e,actor,avatar,value):
    program=value['program']
    if program is None:return None
    uid=program['instance_id'];row=getattr(e,'_physical_objects',{}).get(uid)
    if uid not in avatar['program_ids'] or row is None or row.get('kind')!='item_instance' or row.get('item_rule_id')!=program['item_rule_id']:raise ValueError('actual avatar-bound program instance/rule required; physical equipment is not a digital program')
    Q._selected(e,program['item_rule_id']);W.require_usable_object(row)
    if any(W.physical_lifecycle(row)[x] for x in ('disabled','suppressed')) or row.get('owner_id') not in (None,actor.entity_id):raise ValueError('actual program unavailable to this user')
    if program['consume'] and (row.get('carrier_id') or row.get('equipped_by') or row.get('telekinetic_holder_id') or row.get('item_contents',{}).get('current') is not None):raise ValueError('program instance must be independently consumable, not physically equipped/held/loaded')
    return row


def _range(e,avatar,target,maximum):
    if avatar['network_id']!=target['network_id']:raise ValueError('digital operation requires the same actual network')
    if maximum is not None:
        distance=W.distance_known(avatar,target)
        if distance is None or distance>maximum:raise ValueError('actual mapped digital operation range unavailable')


def _recognized_snares(e,actor_id):
    return {row['intent']['target_id']:request for request,row in _state(e)['requests'].items()
            if row['intent']['actor_id']==actor_id and row['result'].get('false_core_revealed') is True}


def _preflight(e,actor,avatar_id,target_id,value):
    W.require_actors(e,actor);Q._selected(e,value['source']);avatar=N._connected(e,actor,avatar_id);target=_target(e,target_id);_range(e,avatar,target,value['range'])
    if value['source']=='digital-program/net-shield':
        import digital_programs
        digital_programs.validate_operation(e,value,avatar_id,target_id)
    if not all([Q._observe(e,actor,node,set()) for node in value['requirements']]):raise ValueError('actual digital action qualification required')
    _program(e,actor,avatar,value);kind=value['effect']['kind']
    if kind=='damage':
        if target['status']!='connected':raise ValueError('actual digital damage target must be connected')
        if target.get('node_type')=='wall_of_thorns' and value['effect']['damage_kind']!='technology':raise ValueError('actual Wall of Thorns accepts only Technology targeting')
        if value['effect']['damage_kind']=='physical_hp' and target['kind']!='digital_avatar':raise ValueError('physical HP redirection requires an actual digital actor body')
        if value['effect']['data_outcome'] is not None:
            if target.get('node_type')=='data_snare':
                import digital_programs
                digital_programs.definition(e,'data_snare')
                if target_id in _recognized_snares(e,actor.entity_id):raise ValueError('recognized false core cannot be mistaken for extractable server data')
            elif target.get('node_type')!='server_core' or target['data_state']=='corrupted':raise ValueError('damaged or non-core data cannot be certified safely extracted/modified')
    if kind=='temporary' and target_id in _state(e)['temporary']:raise ValueError('existing temporary Integrity provider must end before replacing its source')
    if kind=='data':
        permit=_state(e)['data_permissions'].get(target_id)
        if target.get('node_type')!='server_core' or target['integrity']!=0 or target['data_state']!='intact' or not permit or not permit['available'] or permit['actor_id']!=actor.entity_id or permit['avatar_id']!=avatar_id:raise ValueError('actual intact server needs this users completed Technology finishing receipt')
    return avatar,target


DEFENSIVE_HACKING='C2CSV/input/db/edges.csv:R72:main'


def _defensive_hacking(e,actor):
    owned=actor.spec.get('edges',[])
    if DEFENSIVE_HACKING not in owned:return 0
    if actor.kind!='trainer' or owned.count(DEFENSIVE_HACKING)!=1:raise ValueError('one actual trainer Defensive Hacking acquisition required')
    if e.r._selected_rule(DEFENSIVE_HACKING)!=DEFENSIVE_HACKING:raise ValueError('selected Defensive Hacking source required')
    if SK.rank(e.r,actor,'기술학')[2]<4 or SK.rank(e.r,actor,'집중')[2]<3:raise ValueError('Defensive Hacking actual skill prerequisites required')
    for row in getattr(e,'_physical_objects',{}).values():
        if row.get('kind')=='augmentation_set' and row.get('actor_id')==actor.entity_id:
            S.validate_record(e,row)
            if any(x['augmentation_id']=='datajack' for x in row['installations']):return SK.effective_rank(e.r,actor,'집중')
    raise ValueError('Defensive Hacking requires an actually installed Datajack')


def _extra_defense(e,target,feature):
    if target['kind']!='digital_avatar':return 0
    actor=W.actor_index(e)[target['actor_id']];native=_defensive_hacking(e,actor)
    if feature is None:return native
    Q._selected(e,feature['source']);actor=W.actor_index(e)[target['actor_id']]
    owned=[*actor.spec.get('edges',[]),*actor.spec.get('poke_edges',[]),*actor.spec.get('feats',[])]
    names={SK.key(x) for x in feature['names']}
    if native and names & {SK.key(DEFENSIVE_HACKING),SK.key('방어적 해킹'),SK.key('Defensive Hacking')}:return native
    if {SK.key(x) for x in owned} & names:return native+SK.rank(e.r,actor,feature['skill'])[2]
    return native


def _damage_amount(e,target,effect,amount):
    view=S.validate_record(e,target);technology=effect['damage_kind']=='technology'
    defense=0 if technology else view['digital_stats']['def' if effect['damage_class']=='physical' else 'spd'] if target['kind']=='digital_avatar' else target['defense']
    reduction=0 if target.get('node_type')=='data_snare' else _extra_defense(e,target,effect['defensive_feature']) if technology else effect['reduction']+_extra_defense(e,target,effect['defensive_feature'])
    stages=DAMAGE.defend(dice=amount,attack=0,modifiers=0,defense=defense,reduction=reduction,minimum=effect['minimum'])
    result=DAMAGE.scale(after_defense=stages['after_defense'],type_multiplier=_fraction(effect['multiplier'],'digital damage multiplier'))
    return result,dict(stages,defense=defense,reduction=reduction,multiplier=effect['multiplier'])


def _recovery(e,row,value,cause):
    state=_state(e);state['recovery'][row['id']]=_sign({'entity_id':row['id'],'source':cause,'started_at':e.elapsed_seconds,'ready_at':e.elapsed_seconds+value['seconds'],'amount':value['amount'],'completed':False});setattr(e,FIELD,state)


def _node_end(e,row):
    affected=[row];seen=set();proposed=[]
    for node in affected:
        if node['id'] in seen:raise ValueError('digital node dependency cycle forbidden')
        seen.add(node['id']);updated=deepcopy(node);updated['status']='disabled';proposed.append(updated)
        affected.extend(x for x in e._physical_objects.values() if x.get('kind')=='digital_node' and x.get('status')=='connected' and x.get('anchor_id')==node['id'])
    S.observe_batch(e,proposed,reason='actual digital anchor/node Integrity zero');return [x['id'] for x in affected]


def _damage(e,actor,avatar,target,value,amount,request):
    effect=value['effect'];total,derivation=_damage_amount(e,target,effect,amount);before={'integrity':target['integrity'],'temporary_integrity':target.get('temp_integrity',0)}
    if effect['damage_kind']=='physical_hp':
        body=W.actor_index(e)[target['actor_id']];old=body.hp;e.lose_hp(body,total,source=value['source'])
        return {'kind':'damage','damage_kind':'physical_hp','requested':total,'physical_before':old,'physical_after':body.hp,'before':before,'after':before,'derivation':derivation,'ejected':[]}
    temporary=min(total,target.get('temp_integrity',0));target['temp_integrity']=target.get('temp_integrity',0)-temporary;target['integrity']=max(0,target['integrity']-(total-temporary))
    state=_state(e);barrier=state['temporary'].get(target['id'])
    if barrier is not None:
        barrier.pop('sha256');barrier['remaining']=max(0,barrier['remaining']-temporary);barrier['current']=target['temp_integrity'];barrier['sha256']=TX.request_fingerprint(barrier)
        if barrier['remaining']==0:del state['temporary'][target['id']]
    if target.get('node_type')=='server_core' and total>temporary and effect['damage_kind']!='technology':target['data_state']='corrupted'
    ended=[]
    if target['integrity']==0:
        if target['kind']=='digital_avatar':
            changes=N._end(e,target,forced=True,value=N._policy(e,target['id']),reason='actual digital Integrity zero');ended=[x['avatar_id'] for x in changes]
            for change in changes:
                if change['after']==0:_recovery(e,e._physical_objects[change['avatar_id']],effect['recovery'],value['source'])
        else:
            ended=_node_end(e,target)
            if target.get('node_type')=='server_core' and effect['damage_kind']=='technology' and target['data_state']=='intact':
                permit={'entity_id':target['id'],'actor_id':actor.entity_id,'avatar_id':avatar['id'],'request_id':request,'at':e.elapsed_seconds,'available':effect['data_outcome'] is None}
                state['data_permissions'][target['id']]=_sign(permit)
                if effect['data_outcome'] is not None:target['data_state']=effect['data_outcome']
    S.validate_record(e,target)
    result={'kind':'damage','damage_kind':effect['damage_kind'],'requested':total,'before':before,'after':{'integrity':target['integrity'],'temporary_integrity':target.get('temp_integrity',0)},'derivation':derivation,'ejected':ended,'data_state':target.get('data_state')}
    if target.get('node_type')=='data_snare' and effect['data_outcome'] is not None:
        result.update(false_core_revealed=True,attempted_data_outcome=effect['data_outcome'])
    return result


def execute(e,actor,avatar_id,target_id,value,*,request_id,reason,roll_options=None):
    value=declaration(value);Q._text(request_id);Q._text(reason);W.require_actors(e,actor);options={} if roll_options is None else deepcopy(roll_options)
    if type(options) is not dict:raise ValueError('native digital check options required')
    intent={'actor_id':actor.entity_id,'avatar_id':avatar_id,'target_id':target_id,'policy':_body(value),'reason':reason,'roll_options':options};validate_world(e,W.actor_index(e));saved=_state(e)['requests'].get(request_id)
    if saved is not None:
        if saved['fingerprint']!=TX.request_fingerprint(intent):raise ValueError('digital request identity changed intent')
        return deepcopy(saved['result'])
    _preflight(e,actor,avatar_id,target_id,value)
    def apply(staged,c):
        state=_state(staged);setattr(staged,FIELD,state);key=TX.request_fingerprint([c.entity_id,value['source'],value['id']]);policy=state['policies'].get(key)
        if policy is not None and policy['body']!=_body(value):raise ValueError('digital source operation policy changed')
        avatar,target=_preflight(staged,c,avatar_id,target_id,value);check=value['check'];actual_target=W.actor_index(staged).get(target.get('actor_id'))
        if check is None and options:raise ValueError('check-free digital action has no roll resource input')
        if check is not None:R.plan(staged,c,check['skill'],purpose=check['purpose'],target=actual_target,**options)
        if not TURN.spend(staged,c,value['action'],'digital '+value['effect']['kind']):return C.PendingDecision('actual digital action unavailable')
        roll=None if check is None else staged.skill_roll(c,check['skill'],skill_target=actual_target,**options)
        effect=value['effect'];kind=effect['kind']
        if kind=='damage':
            amount=roll.total if effect['amount']['provider']=='check' else effect['amount']['value'];result=_damage(staged,c,avatar,target,value,max(0,amount),request_id)
        elif kind=='restore':
            result=REC.repair_integrity(staged,target_id,effect['amount'],source=value['source'],eligible=True,reason=reason)
            result['kind']='restore'
        elif kind=='temporary':
            before=target.get('temp_integrity',0);plan=REC.resolve(before,effect['amount'],resource='integrity',mode='at_least',ceiling=effect['maximum']);target['temp_integrity']=plan['after']
            if plan['applied']:
                state['temporary'][target_id]=_sign({'entity_id':target_id,'source':value['source'],'request_id':request_id,'at':staged.elapsed_seconds,'expires_at':None if effect['seconds'] is None else staged.elapsed_seconds+effect['seconds'],'remaining':plan['applied'],'current':target['temp_integrity']})
            result=dict(plan,kind='temporary')
        else:
            permit=state['data_permissions'][target_id];permit.pop('sha256');permit['available']=False;permit['sha256']=TX.request_fingerprint(permit);target['data_state']=effect['outcome'];result={'kind':'data','outcome':effect['outcome'],'finishing_request_id':permit['request_id']}
        program=_program(staged,c,avatar,value)
        if program is not None and value['program']['consume']:
            W.finish_physical_use(staged,program,'consumed',{'source':program['item_rule_id'],'by_actor_id':c.entity_id,'at':staged.elapsed_seconds,'request_id':request_id,'consumer':'digital_program'})
        result.update(actor_id=c.entity_id,avatar_id=avatar_id,target_id=target_id,source=value['source'],at=staged.elapsed_seconds,action=value['action'],check=None if roll is None else asdict(roll),program_id=None if program is None else program['id'])
        state['policies'].setdefault(key,_sign({'actor_id':c.entity_id,'source':value['source'],'operation_id':value['id'],'body':_body(value)}));state['requests'][request_id]=_sign({'intent':deepcopy(intent),'fingerprint':TX.request_fingerprint(intent),'result':deepcopy(result)});setattr(staged,FIELD,state)
        validate_world(staged,W.actor_index(staged));return result
    return G.transition(e,actor,apply)


def require_reentry(e,avatar_id):
    row=_state(e)['recovery'].get(avatar_id)
    if row is not None:
        _verify(row)
        if e.elapsed_seconds<row['ready_at']:raise ValueError('actual digital recovery interval must finish before reentry')


def boundary(e,event,actor=None):
    state=_state(e)
    for uid,row in list(state['temporary'].items()):
        _verify(row)
        if row['expires_at'] is not None and e.elapsed_seconds>=row['expires_at']:
            target=e._physical_objects[uid];target['temp_integrity']=max(0,target.get('temp_integrity',0)-row['remaining']);del state['temporary'][uid]
    for uid,row in state['recovery'].items():
        _verify(row)
        if not row['completed'] and e.elapsed_seconds>=row['ready_at']:
            target=e._physical_objects[uid]
            if row['amount'] is not None:target['integrity']=REC.resolve(target['integrity'],row['amount'],resource='integrity',ceiling=target['max_integrity'])['after']
            row.pop('sha256');row['completed']=True;row['sha256']=TX.request_fingerprint(row)


def has_pending(e):return bool(_state(e)['temporary']) or any(not x['completed'] for x in _state(e)['recovery'].values())
def next_interval(e,end_at):
    deadlines=[x['expires_at'] for x in _state(e)['temporary'].values() if x['expires_at'] is not None]+[x['ready_at'] for x in _state(e)['recovery'].values() if not x['completed']]
    return min([end_at-e.elapsed_seconds]+[x-e.elapsed_seconds for x in deadlines if e.elapsed_seconds<x<end_at])


def validate_world(e,index):
    state=_state(e);Q._fields(state,('version','policies','requests','temporary','recovery','data_permissions'))
    if state['version']!=1 or any(type(state[x]) is not dict for x in ('policies','requests','temporary','recovery','data_permissions')):raise ValueError('known actual digital consequence state required')
    registry=getattr(e,'_physical_objects',{})
    for key,row in state['policies'].items():
        _verify(row);Q._fields(row,('actor_id','source','operation_id','body','sha256'));declaration(dict(row['body'],id=row['operation_id']))
        if row['actor_id'] not in index or row['source']!=row['body']['source'] or key!=TX.request_fingerprint([row['actor_id'],row['source'],row['operation_id']]):raise ValueError('actual digital policy owner/source required')
        if row['source']=='digital-program/net-shield':
            import digital_programs
            digital_programs.validate_operation(e,dict(row['body'],id=row['operation_id']))
    for key,row in state['requests'].items():
        Q._text(key);_verify(row);Q._fields(row,('intent','fingerprint','result','sha256'))
        if row['fingerprint']!=TX.request_fingerprint(row['intent']):raise ValueError('digital command intent changed')
        intent=row['intent'];result=row['result']
        if intent['actor_id'] not in index or any(intent[x] not in registry for x in ('avatar_id','target_id')) or any(result[x]!=intent[x] for x in ('actor_id','avatar_id','target_id')):raise ValueError('actual digital consequence identities required')
        C.integer(result['at'],'digital consequence time',0,e.elapsed_seconds)
        if intent['policy']['source']=='digital-program/net-shield':
            import digital_programs
            digital_programs.validate_operation(e,intent['policy'],intent['avatar_id'],intent['target_id'])
            digital_programs.validate_receipt(e,intent,result,key)
        if 'false_core_revealed' in result:
            effect=intent['policy']['effect'];target=registry[intent['target_id']]
            if (result['false_core_revealed'] is not True or target.get('node_type')!='data_snare'
                    or result.get('kind')!='damage' or result.get('damage_kind')!='technology'
                    or effect.get('kind')!='damage' or effect.get('damage_kind')!='technology'
                    or effect.get('amount',{}).get('provider')!='check' or result.get('check') is None
                    or effect.get('data_outcome') not in ('extracted','modified')
                    or result.get('attempted_data_outcome')!=effect['data_outcome']
                    or result.get('data_state')!='not_applicable'):
                raise ValueError('false-core recognition needs its actual Technology intrusion producer')
    for field in ('temporary','recovery','data_permissions'):
        for uid,row in state[field].items():
            _verify(row)
            if uid!=row.get('entity_id') or uid not in registry or registry[uid].get('kind') not in KINDS:raise ValueError('actual digital pool/permission owner required')
            if field=='temporary':
                Q._fields(row,('entity_id','source','request_id','at','expires_at','remaining','current','sha256'));C.integer(row['remaining'],'remaining temporary provider',0,row['current']);C.integer(row['at'],'temporary Integrity grant time',0,e.elapsed_seconds)
                producer=state['requests'].get(row['request_id'])
                if not producer or producer['intent']['target_id']!=uid or producer['result'].get('kind')!='temporary' or producer['result']['source']!=row['source'] or producer['result']['at']!=row['at'] or row['remaining']>producer['result']['applied']:raise ValueError('temporary Integrity needs its actual completed provider')
                seconds=producer['intent']['policy']['effect']['seconds']
                if row['expires_at']!=(None if seconds is None else row['at']+seconds):raise ValueError('temporary Integrity deadline diverged from actual provider')
                if registry[uid].get('temp_integrity',0)!=row['current']:raise ValueError('actual temporary Integrity pool diverged from provider')
                if row['expires_at'] is not None:C.integer(row['expires_at'],'temporary Integrity expiration',row['at'])
            elif field=='recovery':
                Q._fields(row,('entity_id','source','started_at','ready_at','amount','completed','sha256'));C.integer(row['started_at'],'digital ejection time',0,e.elapsed_seconds);C.integer(row['ready_at'],'digital recovery deadline',row['started_at'])
                if row['amount'] is not None:C.integer(row['amount'],'digital timed recovery amount',1)
                if type(row['completed']) is not bool or row['completed'] and e.elapsed_seconds<row['ready_at']:raise ValueError('actual recovery clock completion required')
            else:
                Q._fields(row,('entity_id','actor_id','avatar_id','request_id','at','available','sha256'))
                producer=state['requests'].get(row['request_id'])
                if row['actor_id'] not in index or row['avatar_id'] not in registry or not producer or producer['result'].get('damage_kind')!='technology' or producer['intent']['target_id']!=uid or producer['result']['after']['integrity']!=0:raise ValueError('safe data permission needs its actual Technology finishing producer')
                if type(row['available']) is not bool:raise ValueError('explicit safe data permission state required')
    return True
