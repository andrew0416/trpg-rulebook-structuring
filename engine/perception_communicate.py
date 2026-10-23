"""Source-owned communication, actual consent, links and retry histories."""
from copy import deepcopy
import common_checks as C,crafting_recipes as Q,frequency as F
import perception_observe as O,state_grants as G,skill_modifiers as S
import world_entities as W,resolution_transaction as TX,effect_lifetime_policy as L

KEY='_communication_state'
ISOLATION=('완전한 고독','Utter Isolation','feat/완전한 고독','gift/완전한 고독')
PERIODS=('lifetime','scene','day','turn')


def declaration(value):
    Q._fields(value,('id','source','capabilities','requirements','mode','range','path','medium','consent','blockers',
                     'connection','frequency','retry','distance_exceptions'))
    Q._text(value['id']);Q._text(value['source']);O._names(value['capabilities'],empty=True)
    route=O.native(value['source'],value['capabilities'],mode=value['mode'])
    route.update({k:deepcopy(value[k]) for k in ('range','path','medium')});O.declaration(route)
    if type(value['requirements']) is not list:raise ValueError('explicit communication qualifications required')
    for requirement in value['requirements']:Q._condition(requirement)
    consent=value['consent']
    if type(consent) is not dict:raise ValueError('explicit communication consent policy required')
    if consent.get('kind') in ('none','willing'):Q._fields(consent,('kind',))
    elif consent.get('kind')=='opposed':
        Q._fields(consent,('kind','sender_skill','recipient_skill','purpose'))
        for field in ('sender_skill','recipient_skill','purpose'):Q._text(consent[field])
    else:raise ValueError('unsupported communication consent policy')
    if type(value['blockers']) is not list:raise ValueError('explicit receiver blockers required')
    for block in value['blockers']:
        Q._fields(block,('field','names','source'));O._names(block['names']);Q._text(block['source'])
        if block['field'] not in ('capabilities','feats','edges','blessings'):raise ValueError('unsupported actual receiver blocker')
    link=value['connection']
    if link is not None:
        Q._fields(link,('maximum','lifetime'));C.integer(link['maximum'],'connection maximum',1)
        if type(link['lifetime']) is not dict or set(link['lifetime'])-{'duration','until','while'}:raise ValueError('connection uses existing non-repeating lifetime controls')
    frequency=value['frequency']
    if type(frequency) is not dict or frequency.get('kind') not in ('at_will','one_time','daily','scene','turn'):raise ValueError('explicit supported communication frequency required')
    fields=('kind','uses','turn_owner_id') if frequency['kind']=='turn' else ('kind','uses')
    Q._fields(frequency,fields);F.parse(frequency)
    if frequency['kind']=='turn':Q._text(frequency['turn_owner_id'])
    retry=value['retry']
    if retry is not None:
        Q._fields(retry,('period','scope','maximum_failures','delay_seconds',*(('failure_reasons',) if 'failure_reasons' in retry else ()),*(('penalty',) if 'penalty' in retry else ())))
        if retry['period'] not in PERIODS or retry['scope'] not in ('pair','sender','recipient'):raise ValueError('explicit retry unit required')
        if retry['maximum_failures'] is not None:C.integer(retry['maximum_failures'],'failure maximum',1)
        C.integer(retry['delay_seconds'],'retry delay',0)
        if 'failure_reasons' in retry:O._names(retry['failure_reasons'])
        if 'penalty' in retry:
            Q._fields(retry['penalty'],('modifier','seconds'))
            C.integer(retry['penalty']['modifier'],'retry check penalty',maximum=-1);C.integer(retry['penalty']['seconds'],'retry penalty window',1)
    if type(value['distance_exceptions']) is not list:raise ValueError('explicit relationship distance exceptions required')
    for relation in value['distance_exceptions']:
        if type(relation) is not dict:raise ValueError('actual distance relationship declaration required')
        if relation.get('kind')=='owned_pokemon':Q._fields(relation,('kind',))
        elif relation.get('kind')=='observed_pair':
            Q._fields(relation,('kind','name','source'));Q._text(relation['name']);Q._text(relation['source'])
        else:raise ValueError('unsupported relationship distance exception')
    return deepcopy(value)


def _body(value):return {k:deepcopy(v) for k,v in value.items() if k!='id'}
def _native(value):
    if value['source']=='capability/텔레파시':
        import telepathy
        return telepathy
    return None
def _pair(source,sender,recipient):return TX.request_fingerprint([source,sender,recipient])
def _signed(row):return dict(row,sha256=TX.request_fingerprint(row))


def _state(engine):
    return getattr(engine,KEY,{'version':1,'policies':{},'permissions':{},'relations':{},'connections':{},'attempts':[],'requests':{},'batches':{}})


def _actual(engine,sender,recipient):
    index=W.require_actors(engine,sender,recipient)
    if sender is recipient:raise ValueError('communication requires distinct actual participants')
    return index


def _current(actor,field):
    if field=='capabilities':return G.effective_capabilities(actor)
    values=actor.spec.get(field,[])
    if type(values) is not list:raise ValueError('actual communication acquisition list required')
    if field=='blessings':values=values+list(getattr(actor,'blessings',[]))
    return [x if type(x) is str else x.get('name',x.get('id',x.get('source',''))) if type(x) is dict else '' for x in values]


def _owns(actor,field,names):
    return bool({S.key(x) for x in _current(actor,field)} & {S.key(x) for x in names})


def receiver_block(engine,recipient,value):
    # Source-reviewed Isolation blocks receiving these mental messages. Mindlock
    # remains an explicit source policy; it is not blanket Aura Pulse immunity.
    if value['mode'] in ('mental','aura') and any(_owns(recipient,f,ISOLATION) for f in ('feats','blessings')):
        return 'utter_isolation'
    for block in value['blockers']:
        if _owns(recipient,block['field'],block['names']):
            Q._selected(engine,block['source']);return block['source']
    return None


def _qualify(engine,sender,value):
    Q._selected(engine,value['source'])
    if value['capabilities'] and not _owns(sender,'capabilities',value['capabilities']):raise ValueError('current communication capability required')
    sources=set()
    outcomes=[Q._observe(engine,sender,node,sources) for node in value['requirements']]
    if not all(outcomes):raise ValueError('actual communication qualification required')


def permission(engine,recipient,sender,source,allowed,*,reason):
    _actual(engine,sender,recipient);Q._text(source);Q._selected(engine,source);Q._text(reason)
    if type(allowed) is not bool:raise ValueError('explicit pair-specific consent required')
    def apply(e,c,other):
        validate_world(e,W.actor_index(e));state=_state(e);key=_pair(source,other.entity_id,c.entity_id);old=state['permissions'].get(key)
        row=_signed({'source':source,'sender_id':other.entity_id,'recipient_id':c.entity_id,'allowed':allowed,
                     'revision':1 if old is None else old['revision']+1,'reason':reason,'at':e.elapsed_seconds})
        state['permissions'][key]=row;setattr(e,KEY,state);boundary(e,'consent_changed')
        e.gm._rec('communication consent',old,row,reason,c);return deepcopy(row)
    return G.transition(engine,recipient,apply,participants=(sender,))


def observe_relation(engine,sender,recipient,name,source,allowed,*,reason):
    _actual(engine,sender,recipient)
    for text in (name,source,reason):Q._text(text)
    Q._selected(engine,source)
    if type(allowed) is not bool:raise ValueError('explicit observed pair relationship required')
    def apply(e,c,other):
        validate_world(e,W.actor_index(e));state=_state(e);key=_pair(name,c.entity_id,other.entity_id);old=state['relations'].get(key)
        row=_signed({'source':source,'name':name,'sender_id':c.entity_id,'recipient_id':other.entity_id,'allowed':allowed,
                     'revision':1 if old is None else old['revision']+1,'at':e.elapsed_seconds,'reason':reason})
        state['relations'][key]=row;setattr(e,KEY,state);e.gm._rec('communication relationship',old,row,reason,c)
        return deepcopy(row)
    return G.transition(engine,sender,apply,participants=(recipient,))


def _willing(engine,sender,recipient,source):
    row=_state(engine)['permissions'].get(_pair(source,sender.entity_id,recipient.entity_id))
    return row is not None and row['allowed']


def _distance_exception(engine,sender,recipient,value):
    for relation in value['distance_exceptions']:
        if relation['kind']=='owned_pokemon':
            if sender.kind=='trainer' and recipient.kind=='pokemon' and W.identity_field(engine,recipient,'owner_id')==sender.entity_id:return 'owned_pokemon'
        else:
            row=_state(engine)['relations'].get(_pair(relation['name'],sender.entity_id,recipient.entity_id))
            if row is not None and row['allowed'] and row['source']==relation['source']:
                Q._selected(engine,row['source']);return relation['name']
    return None


def _route(engine,sender,recipient,value):
    route=O.native(value['source'],value['capabilities'],mode=value['mode'])
    route.update({k:deepcopy(value[k]) for k in ('range','path','medium')})
    exemption=_distance_exception(engine,sender,recipient,value)
    if exemption is not None:route['range']=None
    _,_,blocked=O.route(engine,sender,recipient,route)
    return blocked,exemption


def _period(engine,sender,recipient,retry):
    if retry['period']=='lifetime':return 'lifetime'
    owner=recipient if retry['scope']=='recipient' else sender
    F.bind_session(engine,owner);state=F.state(owner)
    if retry['period']=='turn':return {'owner':owner.entity_id,'turn':state['turn']}
    return F.activation_period(state,'daily' if retry['period']=='day' else 'scene')


def _failures(state,sender,recipient,value,period):
    retry=value['retry'];result=[]
    for row in state['attempts']:
        if row['source']!=value['source'] or row['status']!='failed' or row['period']!=period:continue
        if 'failure_reasons' in retry and row['reason'] not in retry['failure_reasons']:continue
        if retry['scope']!='recipient' and row['sender_id']!=sender.entity_id:continue
        if retry['scope']!='sender' and row['recipient_id']!=recipient.entity_id:continue
        result.append(row)
    return result


def _record(engine,row):
    index=W.actor_index(engine)
    return {L.KEY:row['lifetime'],'lifetime_actor':index[row['sender_id']],'lifetime_target':index[row['recipient_id']]}


def has_connections(engine):return any(row['status']=='live' for row in _state(engine)['connections'].values())


def next_interval(engine,end_at):
    next_at=end_at
    for row in _state(engine)['connections'].values():
        deadline=row['lifetime'].get('end_at')
        if row['status']=='live' and deadline is not None and engine.elapsed_seconds<deadline<next_at:next_at=deadline
    return next_at-engine.elapsed_seconds


def _close(engine,row,reason):
    row.pop('sha256',None);row.update(status='closed',ended_at=engine.elapsed_seconds,ending=reason)
    row['sha256']=TX.request_fingerprint(row)


def boundary(engine,event,actor=None):
    state=_state(engine)
    if not state['connections']:return
    index=W.actor_index(engine)
    for row in state['connections'].values():
        if row['status']!='live':continue
        value=state['policies'][row['source']]['declaration'];sender=index[row['sender_id']];recipient=index[row['recipient_id']]
        record=_record(engine,row);reason=None
        if not L.holds(engine,record):reason='condition_ended'
        elif L._ended(engine,record,event,actor):reason=event
        elif value['capabilities'] and not _owns(sender,'capabilities',value['capabilities']):reason='source_lost'
        elif value['consent']['kind']=='willing' and not _willing(engine,sender,recipient,row['source']):reason='consent_revoked'
        if reason is not None:_close(engine,row,reason)


def _opposed(engine,sender,recipient,value,options,modifier=0):
    import roll_context as R
    consent=value['consent'];requests=[]
    for label,actor,target in (('sender',sender,recipient),('recipient',recipient,sender)):
        skill=consent[label+'_skill'];roll_options=deepcopy(options.get(label,{}))
        if label=='sender' and modifier:roll_options['mods']=C.integer(roll_options.get('mods',0),'ordinary skill modifier')+modifier
        if label=='recipient' and skill in ('집중','Focus'):
            import optional_physical_equipment as OPTIONAL_EQUIPMENT
            equipment_bonus=OPTIONAL_EQUIPMENT.mental_resistance_bonus(actor)
            if equipment_bonus:roll_options['mods']=C.integer(roll_options.get('mods',0),'ordinary skill modifier')+equipment_bonus
        plan=R.plan(engine,actor,skill,purpose=consent['purpose'],target=target,**roll_options)
        requests.append({'actor':actor,'target':target,'provider':actor,'skill':skill,'purpose':consent['purpose'],
                         'replacement':None,'options':roll_options,'expected_plan':plan})
    return R.resolve(engine,requests,{'kind':'opposed','status_quo_defender_id':recipient.entity_id})


def _deliver(engine,sender,recipient,value,thought):
    import aura_pulse as P
    if value['source']==P.SOURCE:
        row=P.state(recipient);message={'source':P.SOURCE,'sender_id':sender.entity_id,'recipient_id':recipient.entity_id,
                                      'sequence':len(row['received'])+1,'text':thought}
        row['received'].append(message);P.validate(recipient);return message
    return {'source':value['source'],'sender_id':sender.entity_id,'recipient_id':recipient.entity_id,'text':thought}


def send(engine,sender,recipient,value,thought,*,request_id,roll_options=None,operation='send'):
    _actual(engine,sender,recipient);value=declaration(value);Q._text(request_id);Q._selected(engine,value['source'])
    native=_native(value)
    if native is None and operation!='send':raise ValueError('this source has no native reading or receiving operation')
    if operation!='read':Q._text(thought)
    options={} if roll_options is None else deepcopy(roll_options)
    if type(options) is not dict or set(options)-{'sender','recipient'} or any(type(v) is not dict for v in options.values()):raise ValueError('actual endpoint roll options required')
    ordinary={'mods','helper_rank','fixed','penalty_count','fixed_penalties','roll_id','helper_bonus','skill_context','skill_stunt'}
    if any(set(v)-ordinary for v in options.values()):raise ValueError('ordinary native roll options required')
    if options and value['consent']['kind']!='opposed':raise ValueError('this communication policy has no opposed check')
    validate_world(engine,W.actor_index(engine));body=_body(value)
    intent={'sender_id':sender.entity_id,'recipient_id':recipient.entity_id,'policy':body,'text':thought,'roll_options':options}
    if native is not None:intent['operation']=operation
    prior=TX.replay_result(_state(engine)['requests'],request_id,intent,fingerprint_field='intent')
    if prior is not None:return dict(deepcopy(prior['result']),replayed=True)
    if native is not None:native.prepare(engine,sender,recipient,value,operation,thought)
    _qualify(engine,sender,value)
    if value['connection'] is not None:L.prepare(engine,sender,recipient,value['connection']['lifetime'],value['source'])
    def apply(e,c,other):
        validate_world(e,W.actor_index(e));_qualify(e,c,value);state=_state(e);source=value['source'];policy=state['policies'].get(source)
        signature=TX.request_fingerprint(body)
        if policy is not None and policy['sha256']!=signature:raise ValueError('communication source policy cannot change with declaration or request identity')
        state['policies'].setdefault(source,{'declaration':body,'sha256':signature});setattr(e,KEY,state);boundary(e,'reconcile')
        period=None if value['retry'] is None else _period(e,c,other,value['retry'])
        failures=[] if value['retry'] is None else _failures(state,c,other,value,period)
        retry=value['retry'];reason=None;consumed=False;check=None;exemption=None;message=None;event=None;modifier=0
        penalty=None if retry is None else retry.get('penalty')
        if penalty is not None and any(e.elapsed_seconds<row['at']+penalty['seconds'] for row in failures):modifier=penalty['modifier']
        if retry is not None and retry['maximum_failures'] is not None and len(failures)>=retry['maximum_failures']:reason='retry_exhausted'
        elif failures and e.elapsed_seconds<failures[-1]['at']+retry['delay_seconds']:reason='retry_wait'
        elif not F.activation_allowed(c,'communication:'+source,value['frequency'],engine=e):reason='frequency_exhausted'
        else:
            consumed=True;F.consume_activation(c,'communication:'+source,value['frequency'],engine=e)
            if native is not None:
                route,exemption=_route(e,c,other,value)
                if route is not None:reason=route['reason']
                if reason is None:
                    willing=operation=='offer' or _willing(e,c,other,source)
                    event=native.attempt(e,c,other,operation,not willing)
                    actual_receiver=c if operation=='offer' else other
                    if receiver_block(e,actual_receiver,value) is not None or native.read_block(e,other,operation) is not None:reason='receiver_blocked'
            else:
                block=receiver_block(e,other,value)
                if block is not None:reason='receiver_blocked'
            if native is None and reason is None:
                route,exemption=_route(e,c,other,value)
                if route is not None:reason=route['reason']
            key=_pair(source,c.entity_id,other.entity_id);link=state['connections'].get(key)
            live=link is not None and link['status']=='live'
            if reason is None and value['consent']['kind']=='willing' and not _willing(e,c,other,source):reason='mind_not_open'
            if reason is None and value['connection'] is not None and not live:
                active=sum(x['status']=='live' and x['source']==source and x['sender_id']==c.entity_id for x in state['connections'].values())
                if active>=value['connection']['maximum']:reason='connection_limit'
                else:
                    prepared=L.prepare(e,c,other,value['connection']['lifetime'],source)
                    if not L.holds(e,prepared):reason='connection_condition_unavailable'
            if reason is None and value['consent']['kind']=='opposed' and not live and operation!='offer' and not _willing(e,c,other,source):
                check=_opposed(e,c,other,value,options,modifier)
                if check['result']['winner_id']!=c.entity_id:reason='opposed_failed'
            if reason is None:
                if value['connection'] is not None and not live:
                    lifetime=prepared[L.KEY]
                    state['connections'][key]=_signed({'source':source,'sender_id':c.entity_id,'recipient_id':other.entity_id,
                        'lifetime':lifetime,'status':'live','opened_at':e.elapsed_seconds,'ended_at':None,'ending':None})
                message=_deliver(e,c,other,value,thought) if native is None else native.deliver(e,c,other,thought,operation)
        result={'source':source,'sender_id':c.entity_id,'recipient_id':other.entity_id,'status':'delivered' if reason is None else 'failed' if consumed else 'denied',
                'reason':reason,'consumed':consumed,'check':check,'distance_exemption':exemption,'message':deepcopy(message),'replayed':False}
        if native is not None:result.update(operation=operation,event=event,retry_modifier=modifier)
        if consumed:
            state['attempts'].append(_signed({'source':source,'sender_id':c.entity_id,'recipient_id':other.entity_id,
                'at':e.elapsed_seconds,'period':deepcopy(period),'status':result['status'],'reason':reason,'request_id':request_id}))
        state['requests'][request_id]={'intent':TX.request_fingerprint(intent),'result':deepcopy(result),
                                      'result_sha256':TX.request_fingerprint(result)}
        validate_world(e,W.actor_index(e));return result
    return G.transition(engine,sender,apply,participants=(recipient,))


def send_many(engine,sender,recipients,value,thought,*,request_id,maximum,roll_options=None):
    """One immutable roster, atomic delivery, and durable replay of native groups."""
    W.require_actors(engine,sender);value=declaration(value);Q._text(thought);Q._text(request_id)
    if type(recipients) not in (list,tuple) or not recipients:raise ValueError('explicit nonempty actual communication roster required')
    ids=[]
    for other in recipients:_actual(engine,sender,other);ids.append(other.entity_id)
    if len(ids)!=len(set(ids)):raise ValueError('distinct actual communication recipients required')
    validate_world(engine,W.actor_index(engine))
    options={} if roll_options is None else deepcopy(roll_options)
    intent={'source':_body(value),'sender_id':sender.entity_id,'recipient_ids':ids,'text':thought,'roll_options':options}
    prior=TX.replay_result(_state(engine).get('batches',{}),request_id,intent,fingerprint_field='intent')
    if prior is not None:return dict(deepcopy(prior['result']),replayed=True)
    C.integer(maximum,'actual communication recipient maximum',0)
    if len(ids)>maximum:raise ValueError('actual communication recipient count exceeds the source maximum')
    native=_native(value)
    if native is not None:
        for other in recipients:native.prepare(engine,sender,other,value,'send',thought)
    def apply(e,c,*others):
        results=[];members=[]
        for other in others:
            key='communication-group:'+request_id+':'+other.entity_id
            result=send(e,c,other,value,thought,request_id=key,roll_options=options)
            result['replayed']=False;results.append(result);members.append(key)
        result={'source':value['source'],'sender_id':c.entity_id,'recipient_ids':ids,'results':results,'replayed':False}
        state=_state(e);state.setdefault('batches',{})[request_id]={'intent':TX.request_fingerprint(intent),'result':deepcopy(result),
            'members':members,'result_sha256':TX.request_fingerprint(result)}
        setattr(e,KEY,state);validate_world(e,W.actor_index(e));return result
    return G.transition(engine,sender,apply,participants=tuple(recipients))


def disconnect(engine,sender,recipient,source,*,reason):
    _actual(engine,sender,recipient);Q._text(source);Q._text(reason)
    def apply(e,c,other):
        validate_world(e,W.actor_index(e));row=_state(e)['connections'].get(_pair(source,c.entity_id,other.entity_id))
        if row is None or row['status']!='live':return False
        _close(e,row,'disconnected');e.gm._rec('communication disconnected',None,deepcopy(row),reason,c);return True
    return G.transition(engine,sender,apply,participants=(recipient,))


def received(engine,recipient,*,source=None):
    W.require_actors(engine,recipient);validate_world(engine,W.actor_index(engine))
    if source is not None:Q._text(source)
    return [deepcopy(row['result']['message']) for row in _state(engine)['requests'].values()
            if row['result']['status']=='delivered' and row['result'].get('operation')!='read' and row['result']['message']['recipient_id']==recipient.entity_id
            and (source is None or row['result']['source']==source)]


def native_pulse(engine,sender,recipient,thought):
    import aura_pulse as P
    value={'id':'native:'+P.SOURCE,'source':P.SOURCE,'capabilities':['파동술','Aura Pulse',P.SOURCE],'requirements':[],
        'mode':'mental','range':None,'path':None,'medium':[],'consent':{'kind':'none'},'blockers':[],
        'connection':None,'frequency':{'kind':'at_will','uses':1},'retry':None,'distance_exceptions':[]}
    sequence=len(_state(engine)['requests'])+1
    while 'native-pulse:'+str(sequence) in _state(engine)['requests']:sequence+=1
    result=send(engine,sender,recipient,value,thought,request_id='native-pulse:'+str(sequence))
    if result['status']!='delivered':raise ValueError('Aura Pulse receiving blocked: '+str(result['reason']))
    return result['message']


def validate_world(engine,index):
    state=_state(engine);Q._fields(state,('version','policies','permissions','relations','connections','attempts','requests',*(('batches',) if 'batches' in state else ())))
    if state['version']!=1 or type(state['attempts']) is not list:raise ValueError('supported communication state required')
    for field in ('policies','permissions','relations','connections','requests'):
        if type(state[field]) is not dict:raise ValueError('communication records must be mappings')
    for source,row in state['policies'].items():
        Q._fields(row,('declaration','sha256'));value=declaration(dict(row['declaration'],id='restored'))
        if value['source']!=source or row['sha256']!=TX.request_fingerprint(row['declaration']):raise ValueError('communication source policy changed')
        Q._selected(engine,source)
        native=_native(value)
        if native is not None and _body(native.policy(engine.r)['declaration'])!=row['declaration']:raise ValueError('native communication source contract changed')
    for field in ('permissions','relations','connections','attempts'):
        rows=state[field].items() if type(state[field]) is dict else enumerate(state[field])
        for key,row in rows:
            if type(row) is not dict or row.get('sha256')!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('communication evidence changed')
            a=row.get('sender_id');b=row.get('recipient_id')
            if a not in index or b not in index or a==b:raise ValueError('actual communication relationship required')
            Q._text(row.get('source'));Q._selected(engine,row['source'])
            if field in ('permissions','relations'):
                if type(row.get('allowed')) is not bool:raise ValueError('explicit communication consent fact required')
                C.integer(row.get('revision'),'communication fact revision',1);C.integer(row.get('at'),'communication fact time',0,engine.elapsed_seconds);Q._text(row.get('reason'))
                if key!=_pair(row['source'] if field=='permissions' else row.get('name'),a,b):raise ValueError('communication fact identity mismatch')
            else:
                if row['source'] not in state['policies']:raise ValueError('communication record lacks source policy')
                if field=='connections':
                    if key!=_pair(row['source'],a,b) or row.get('status') not in ('live','closed'):raise ValueError('actual connection identity required')
                    policy=state['policies'][row['source']]['declaration']['connection']
                    if policy is None or type(row.get('lifetime')) is not dict:raise ValueError('actual connection lifetime required')
                    C.integer(row.get('opened_at'),'connection opening time',0,engine.elapsed_seconds)
                    plan=row['lifetime'];expected=policy['lifetime']
                    if plan.get('declaration')!=expected or plan.get('started_at')!=row['opened_at']:raise ValueError('connection lifetime policy changed')
                    C.integer(plan.get('started_round'),'connection starting round',0,engine.round_no)
                    Q._fields(plan.get('started_turns'),('user','target'))
                    for label,uid in (('user',a),('target',b)):
                        C.integer(plan['started_turns'][label],'connection starting owner turn',0,index[uid].custom_conditions.get('combat_turn_serial',0))
                    if 'duration' in expected and plan.get('end_at')!=row['opened_at']+C.integer(expected['duration']['seconds'],'connection seconds',1):raise ValueError('connection clock changed')
                    if 'until' in expected:
                        event={'event':expected['until']} if type(expected['until']) is str else expected['until']
                        if plan.get('until')!=L._event(event):raise ValueError('connection boundary changed')
                    if 'while' in expected and plan.get('while')!=expected['while']:raise ValueError('connection condition changed')
                    if row['status']=='closed':C.integer(row.get('ended_at'),'connection ending time',row['opened_at'],engine.elapsed_seconds);Q._text(row.get('ending'))
                    elif row.get('ended_at') is not None or row.get('ending') is not None:raise ValueError('live connection cannot have an ending')
                else:
                    C.integer(row.get('at'),'attempt time',0,engine.elapsed_seconds)
                    if row.get('status') not in ('delivered','failed') or row.get('request_id') not in state['requests']:raise ValueError('actual communication attempt receipt required')
    for request,row in state['requests'].items():
        Q._text(request);Q._fields(row,('intent','result','result_sha256'));Q._text(row['intent']);result=row['result']
        if type(result) is not dict or row['result_sha256']!=TX.request_fingerprint(result):raise ValueError('communication receipt changed')
        if result.get('source') not in state['policies'] or result.get('sender_id') not in index or result.get('recipient_id') not in index:raise ValueError('communication receipt endpoints required')
        if result.get('status') not in ('delivered','failed','denied') or type(result.get('consumed')) is not bool or result.get('replayed') is not False:raise ValueError('actual communication outcome required')
        if result['consumed']!=(result['status']!='denied'):raise ValueError('communication consumption outcome mismatch')
        attempts=[x for x in state['attempts'] if x['request_id']==request]
        if len(attempts)!=int(result['consumed']):raise ValueError('communication attempt history mismatch')
        if attempts and any(attempts[0][field]!=result[field] for field in ('source','sender_id','recipient_id','status','reason')):raise ValueError('communication failure history differs from actual receipt')
        native=_native({'source':result['source']})
        if native is not None:native.validate_result(engine,result)
        if result['status']=='delivered' and native is None:
            message=result.get('message')
            if type(message) is not dict or any(message.get(field)!=result[field] for field in ('source','sender_id','recipient_id')):raise ValueError('actual delivered message endpoints required')
            Q._text(message.get('text'))
        elif result['status']!='delivered' and result.get('message') is not None:raise ValueError('failed communication cannot contain delivered information')
    batches=state.get('batches',{})
    if type(batches) is not dict:raise ValueError('actual communication batches must be a mapping')
    for key,row in batches.items():
        Q._text(key);Q._fields(row,('intent','result','members','result_sha256'));Q._text(row['intent']);result=row['result']
        if type(result) is not dict or row['result_sha256']!=TX.request_fingerprint(result):raise ValueError('communication group receipt changed')
        Q._fields(result,('source','sender_id','recipient_ids','results','replayed'));O._names(result['recipient_ids'])
        if result['replayed'] is not False or type(row['members']) is not list or type(result['results']) is not list or len(result['recipient_ids'])!=len(row['members']) or len(result['results'])!=len(row['members']):raise ValueError('actual immutable communication roster required')
        for uid,member,out in zip(result['recipient_ids'],row['members'],result['results']):
            actual=state['requests'].get(member,{}).get('result')
            if member!='communication-group:'+key+':'+uid or actual!=out or any(out.get(field)!=result[field] for field in ('source','sender_id')) or out.get('recipient_id')!=uid:raise ValueError('communication group lacks its actual individual receipts')
    for source,policy in state['policies'].items():
        link=policy['declaration']['connection']
        if link is not None:
            for uid in index:
                if sum(row['status']=='live' and row['source']==source and row['sender_id']==uid for row in state['connections'].values())>link['maximum']:raise ValueError('actual communication connection limit exceeded')
    return True
