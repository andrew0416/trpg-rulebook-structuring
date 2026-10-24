"""Scoped skill-roll preparation using the native, non-consuming planner."""
from copy import deepcopy
import skill_modifiers as S
import world_entities as W
import ap_roll_bonus as AP_ROLL

def plan(engine,actor,skill,*,purpose,target=None,provider=None,replacement=None,**options):
    target=actor if target is None else target
    provider=actor if provider is None else provider
    W.require_actors(engine,actor,target);W.require_actors(engine,actor,provider)
    if type(purpose) is not str or not purpose.strip():raise ValueError('explicit roll purpose required')
    requested=S.skill_id(engine.r.skill_policy,skill,required=True);selected=skill
    evidence=None
    if replacement is not None:
        fields={'source','purpose','actor_id','target_id','provider_id','from_skill','to_skill','allowed'}
        if type(replacement) is not dict or set(replacement)!=fields:raise ValueError('exact scoped replacement declaration required')
        if replacement['allowed'] is not True:raise ValueError('replacement is not explicitly allowed')
        if (replacement['purpose'],replacement['actor_id'],replacement['target_id'],replacement['provider_id'])!=(purpose,actor.entity_id,target.entity_id,provider.entity_id):
            raise ValueError('replacement scope differs from actual roll participants or purpose')
        if S.skill_id(engine.r.skill_policy,replacement['from_skill'],required=True)!=requested:raise ValueError('replacement original skill mismatch')
        if engine.r._selected_rule(replacement['source'])!=replacement['source']:raise ValueError('selected replacement source required')
        selected=replacement['to_skill'];S.skill_id(engine.r.skill_policy,selected,required=True);evidence=deepcopy(replacement)
    if 'skill_target' in options:raise ValueError('use the bound target instead of a second skill target')
    prepared=engine._prepare_skill_roll(actor,selected,skill_target=target,**options)
    rank_name,expression,ordinary,faces,penalties,resolved=prepared
    stunt=resolved.get('skill_stunt')
    if stunt is not None:
        if provider is not actor:raise ValueError('Skill Stunt acquisition provider must be its actual actor')
        if purpose!=stunt['choice']['use']:raise ValueError('roll purpose differs from approved narrow stunt use')
    return {'purpose':purpose,'actor_id':actor.entity_id,'target_id':target.entity_id,'provider_id':provider.entity_id,
            'requested_skill':requested,'selected_skill':S.skill_id(engine.r.skill_policy,selected,required=True),
            'requested_rank':S.rank(engine.r,actor,skill)[2],'ordinary_rank':ordinary,
            'effective_rank':S.effective_rank(engine.r,actor,selected),'rank_name':rank_name,'expression':expression,
            'dice_count':resolved['dice_count'],'modifier':resolved['modifier'],
            'ap_bonus':AP_ROLL.bonus(engine,actor,options.get('roll_id'),'skill'),
            'fixed_faces':deepcopy(faces),'fixed_penalties':deepcopy(penalties),
            'request_options':{k:deepcopy(v) for k,v in options.items() if k not in ('fixed','fixed_penalties')},
            'sources':deepcopy(resolved['sources']),'replacement':evidence,
            'skill_stunt':deepcopy(stunt),'consumed':False}


def policy(engine,actor,target,document,*,purpose,context=None,decisions=None):
    """Selected-source declarations use actual provider acquisition records."""
    import source_policy as P,source_policy_state as STATE,acquired_features as A
    index=W.require_actors(engine,actor,target)
    prepared=P.resolve(engine.r,document,context=context,decisions=decisions,
        _state_reader=lambda specs:STATE.read(engine,actor,target,specs))
    if prepared['status']!='PolicyValuesReady':return prepared
    values=prepared['values']
    if set(values)!={'roll_plan'} or type(values['roll_plan']) is not dict:raise ValueError('exact roll plan declaration required')
    declaration=deepcopy(values['roll_plan'])
    required={'skill','purpose','provider_id','provider_requirement','options'}
    if not required<=set(declaration) or set(declaration)-(required|{'replacement'}):raise ValueError('exact scoped roll plan fields required')
    if declaration['purpose']!=purpose:raise ValueError('roll purpose differs from selected declaration')
    provider_id=declaration['provider_id']
    if type(provider_id) is not str or provider_id not in index:raise ValueError('actual roll provider required')
    provider=index[provider_id];requirement=declaration['provider_requirement']
    if type(requirement) is not dict or set(requirement)!={'source_id','minimum_count'}:raise ValueError('explicit provider acquisition requirement required')
    minimum=requirement['minimum_count']
    if type(minimum) is not int or minimum<1:raise ValueError('positive acquisition count required')
    count=A.owned_rule_count(provider,requirement['source_id'])
    evidence=dict(requirement,provider_id=provider_id,actual_count=count)
    if count<minimum:return dict(prepared,status='PolicyRollPlanDenied',provider_acquisition=evidence)
    options=declaration['options']
    if type(options) is not dict or set(options)-{'mods','helper_rank','fixed','penalty_count','fixed_penalties','roll_id','helper_bonus','skill_context','skill_stunt'}:
        raise ValueError('explicit supported native roll options required')
    replacement=declaration.get('replacement')
    if replacement is not None and (type(replacement) is not dict or replacement.get('source')!=prepared['selected_id']):
        raise ValueError('replacement must belong to selected policy source')
    if replacement is not None and replacement.get('allowed') is None:
        return dict(prepared,status='PolicyRollPlanPending',provider_acquisition=evidence,reason='replacement permission unresolved')
    result=plan(engine,actor,declaration['skill'],purpose=purpose,target=target,provider=provider,replacement=replacement,**options)
    return dict(prepared,status='PolicyRollPlanPrepared',roll_plan=result,provider_acquisition=evidence,consumed=False)


def rank_plan(engine,actor,skill,*,purpose,targets,source,provider=None):
    """Rank-only activity formula: never prepares dice, rerolls or Skill Stunts."""
    provider=actor if provider is None else provider
    if type(purpose) is not str or not purpose.strip():raise ValueError('explicit rank purpose required')
    if type(targets) not in (list,tuple) or not targets or len({id(t) for t in targets})!=len(targets):raise ValueError('distinct actual rank-plan targets required')
    W.require_actors(engine,actor,provider,*targets)
    if engine.r._selected_rule(source)!=source:raise ValueError('selected rank formula source required')
    identity=S.skill_id(engine.r.skill_policy,skill,required=True)
    ordinary=S.rank(engine.r,actor,skill)[2];effective=S.effective_rank(engine.r,actor,skill)
    return {'kind':'rank_formula','purpose':purpose,'actor_id':actor.entity_id,'provider_id':provider.entity_id,
            'target_ids':[t.entity_id for t in targets],'source':source,'skill':identity,
            'ordinary_rank':ordinary,'effective_rank':effective,'dice_count':None,'modifier':None,'consumed':False}


def accuracy(engine,actor,target,move,*,situational=0,waive=False,roll_id=None):
    W.require_actors(engine,actor,target)
    if type(situational) is not int or type(waive) is not bool:raise ValueError('typed accuracy context required')
    prepared=engine._prepare_accuracy_context(actor,target,move,situational,waive,roll_id=roll_id)
    return {'purpose':'accuracy','actor_id':actor.entity_id,'target_id':target.entity_id,'provider_id':actor.entity_id,
            'source':prepared['move']['id'],'situational':situational,'waive_evasion':waive,
            'preparation':deepcopy(prepared),'requires_roll':not prepared['no_accuracy'],
            'final_outcome':None,'post_roll_effects_pending':not prepared['no_accuracy'],'consumed':False}


def resolve(engine, requests, procedure, *, request_id=None, observed_choices=None):
    """Execute ordinary scoped plans through native rolls and arithmetic.

    Requests bind live actors and a reviewed plan. All participants are
    re-prepared before consuming any dice. Observed choices use native durable
    sequences so later errors cannot erase a first observation or paid cost.
    """
    import common_checks as C, common_action_checks as ACTION, skill_feature_actions as SF
    from dataclasses import asdict
    if type(requests) not in (list,tuple) or not requests:raise ValueError('nonempty roll requests required')
    if type(procedure) is not dict:raise ValueError('explicit check procedure required')
    kind=procedure.get('kind')
    fields={'dc':{'kind','dc'},'opposed':{'kind','status_quo_defender_id'},
            'team':{'kind','dc','required_people'},'weighted_team':{'kind','dc','required_people','weights'}}
    if kind not in fields or set(procedure)!=fields[kind]:raise ValueError('unsupported or incomplete check procedure')
    if kind=='dc' and len(requests)!=1:raise ValueError('DC procedure requires one roll')
    if kind=='opposed' and len(requests)!=2:raise ValueError('opposed procedure requires challenger then defender')
    if kind!='opposed':C.integer(procedure['dc'],'DC')
    if kind in ('team','weighted_team'):C.integer(procedure['required_people'],'required people',1)
    if kind=='weighted_team':
        weights=procedure['weights']
        if type(weights) not in (list,tuple) or len(weights)!=len(requests):raise ValueError('one explicit weight per participant required')
        for weight in weights:C.integer(weight,'explicit contribution multiplier',1)
    import resolution_transaction as TX
    intent_requests=[]
    for request in requests:
        if type(request) is not dict or set(request)!={'actor','target','provider','skill','purpose','replacement','options','expected_plan'}:
            raise ValueError('exact scoped execution request required')
        actor=request['actor'];target=request['target'];provider=request['provider']
        target=actor if target is None else target;provider=actor if provider is None else provider
        W.require_actors(engine,actor,target,provider)
        intent_requests.append({**{k:v for k,v in request.items() if k not in ('actor','target','provider')},
                                'actor_id':actor.entity_id,'target_id':target.entity_id,'provider_id':provider.entity_id})
    choice_intent={}
    if observed_choices is not None:
        if type(observed_choices) is not dict or not observed_choices:raise ValueError('nonempty observed choices required')
        if type(request_id) is not str or not request_id.strip():raise ValueError('observed choices require durable request identity')
        for roll_id,choice in observed_choices.items():
            if type(roll_id) is not str or not roll_id.strip() or type(choice) is not dict or set(choice)!={'feature','options'}:
                raise ValueError('exact identified feature choice required')
            options=choice['options']
            if type(options) is not dict or not callable(options.get('decision')) or set(options)-{'decision','reroll_faces','reroll_penalties'}:
                raise ValueError('native observed choice callback and reroll observations required')
            choice_intent[roll_id]={'feature':choice['feature'],'options':{k:v for k,v in options.items() if k!='decision'}}
    intent={'requests':intent_requests,'procedure':procedure}
    if observed_choices is not None:intent['observed_choices']=choice_intent
    records=getattr(engine,'_roll_context_requests',{})
    if request_id is not None:
        prior=TX.replay_result(records,request_id,intent,fingerprint_field='intent')
        if prior is not None:return dict(prior['result'],replayed=True)
        signature=TX.request_fingerprint(intent)
    sequence_key='roll_context:'+request_id if observed_choices is not None else None
    prior_sequence=getattr(engine,'_skill_sequences',{}).get(sequence_key) if sequence_key else None
    if prior_sequence is not None and prior_sequence['basis']!={'intent':signature}:
        raise ValueError('cannot change an observed scoped request')
    prepared=[];actors=[];identities=[]
    for request in requests:
        if type(request) is not dict or set(request)!={'actor','target','provider','skill','purpose','replacement','options','expected_plan'}:
            raise ValueError('exact scoped execution request required')
        options=deepcopy(request['options'])
        if type(options) is not dict or set(options)-{'mods','helper_rank','fixed','penalty_count','fixed_penalties','roll_id','helper_bonus','skill_context','skill_stunt'}:
            raise ValueError('ordinary native roll options required')
        actor=request['actor'];target=request['target'];provider=request['provider']
        current=(deepcopy(request['expected_plan']) if prior_sequence is not None else
                 plan(engine,actor,request['skill'],purpose=request['purpose'],target=target,provider=provider,
                      replacement=request['replacement'],**options))
        if current!=request['expected_plan']:raise ValueError('stale or mismatched roll plan; prepare again')
        if kind in ('team','weighted_team') and (options.get('helper_rank',0)!=0 or options.get('helper_bonus') not in (None,0)):
            raise ValueError('team-plus-assistance requires a sourced extension')
        if options.get('roll_id') is not None:identities.append(options['roll_id'])
        actors.append(actor.entity_id)
        # Preserve validated fixed observations, including consumed iterables.
        options['fixed']=current['fixed_faces'];options['fixed_penalties']=current['fixed_penalties']
        options['skill_target']=actor if target is None else target
        if observed_choices is not None and options.get('roll_id') in observed_choices:
            choice=observed_choices[options['roll_id']]
            options.update(feature=choice['feature'],feature_options=choice['options'])
        prepared.append((actor,current['selected_skill'],options,current))
    if len(set(actors))!=len(actors):raise ValueError('distinct check participants required')
    if len(set(identities))!=len(identities):raise ValueError('each roll needs its own identity')
    if kind=='opposed' and procedure['status_quo_defender_id']!=actors[1]:raise ValueError('actual status-quo defender must be second participant')
    if observed_choices is not None and (len(identities)!=len(requests) or set(observed_choices)-set(identities)):
        raise ValueError('observed sequence requires distinct participant IDs and bound choices')
    def execute(staged,rolls=None):
        if rolls is None:rolls=[staged.skill_roll(actor,skill,**options) for actor,skill,options,_ in prepared]
        if kind=='dc':result=asdict(C.against_dc(rolls[0],procedure['dc']))
        elif kind=='opposed':
            winner=C.opposed(*rolls)
            result={'winner':winner,'winner_id':actors[0 if winner=='challenger' else 1]}
        elif kind=='team':result=asdict(C.team(rolls,procedure['dc'],procedure['required_people']))
        else:result=asdict(C.weighted_team(rolls,procedure['dc'],procedure['required_people'],procedure['weights']))
        for actor,_,options,_ in prepared:SF.finish(staged,actor,options.get('roll_id'))
        result={'procedure':deepcopy(procedure),'plans':[deepcopy(p[3]) for p in prepared],
                'rolls':[dict(asdict(roll),total=roll.total) for roll in rolls],'result':result,'consumed':True}
        if observed_choices is not None:
            result['observations']=[{'roll_id':options['roll_id'],'actor_id':actor.entity_id,
                'first':dict(asdict(SF.event(staged,actor,options['roll_id']).first),total=SF.event(staged,actor,options['roll_id']).first.total),
                'feature':SF.event(staged,actor,options['roll_id']).feature,
                'state':SF.event(staged,actor,options['roll_id']).state}
                for actor,_,options,_ in prepared]
        if request_id is None:return result,None
        # Allocate the durable receipt while RNG/logs/events are still staged.
        next_records=dict(records)
        next_records[request_id]={'intent':signature,'result':deepcopy(result)}
        return dict(result,replayed=False),next_records
    if observed_choices is None:
        result,next_records=ACTION._staged_rolls(engine,execute)
    else:
        result,next_records=SF.sequence(engine,sequence_key,{'intent':signature},
            [(actor,skill,options) for actor,skill,options,_ in prepared],lambda rolls:execute(engine,rolls))
    if next_records is not None:engine._roll_context_requests=next_records
    return result


def resolve_pool(engine,actor,subject,*,purpose,source,count,sides,offset=0,fixed=None):
    """Observe a declared non-skill pool; its caller owns eligibility and commit."""
    import common_checks as C,roll_pools as POOLS
    W.require_actors(engine,actor)
    if type(purpose) is not str or not purpose.strip() or type(source) is not str or not source.strip():raise ValueError('explicit pool purpose and source required')
    if engine.r._selected_rule(source)!=source:raise ValueError('selected pool source changed')
    C.integer(count,'declared pool count',0);C.integer(sides,'declared pool sides',1);C.integer(offset,'declared pool offset')
    if type(subject) is not dict or type(subject.get('id')) is not str:raise ValueError('actual identified pool subject required')
    registered=W.entity_index(engine).get(subject['id'])
    if registered is not subject and (registered is not None or actor.spec.get('plants',{}).get(subject['id']) is not subject):raise ValueError('actual scoped pool subject required')
    result = observe_native(engine,actor,purpose,POOLS.pool(engine.rng,count,sides=sides,offset=offset,fixed=fixed),lambda faces:POOLS.pool(engine.rng,count,sides=sides,offset=offset,fixed=faces))
    return dict(result, purpose=purpose, source=source,
                actor_id=actor.entity_id, subject_id=subject['id'])


def observe_native(engine,actor,purpose,first,roll_again):
    """The final native consumer uses this result, after its observed reroll."""
    W.require_actors(engine,actor)
    return __import__('warper').reroll(engine,actor,purpose,first,roll_again)


def native_pool(engine,actor,*,purpose,source,count,sides,offset=0,fixed=None):
    import roll_pools as POOLS
    W.require_actors(engine,actor)
    if not isinstance(purpose,str) or not purpose or engine.r._selected_rule(source)!=source:raise ValueError('actual selected native roll source and purpose required')
    def apply(staged,c):
        first=POOLS.pool(staged.rng,count,sides=sides,offset=offset,fixed=fixed)
        return observe_native(staged,c,purpose,first,lambda faces:POOLS.pool(staged.rng,count,sides=sides,offset=offset,fixed=faces))
    return __import__('state_grants').transition(engine,actor,apply)


def native_choices(fn):
    """Stage an actual ordinary roll together with its optional provider cost."""
    from functools import wraps
    @wraps(fn)
    def run(engine,actor,*args,**kwargs):
        if not any(c.spec.get('native_roll_offer') for c in W.actor_index(engine).values()):return fn(engine,actor,*args,**kwargs)
        def apply(staged,c):
            options=__import__('state_grants')._stage_transition_payload(engine,staged,{'args':args,'kwargs':kwargs})
            return fn(staged,c,*options['args'],**options['kwargs'])
        return __import__('state_grants').transition(engine,actor,apply)
    return run


def execute_policies(engine, submissions, procedure, *, request_id):
    """Resolve ordinary authored roll plans with fresh source/provider evidence."""
    import source_policy as P,source_policy_state as STATE
    import resolution_transaction as TX,common_action_checks as ACTION
    if type(submissions) not in (list,tuple) or not submissions:raise ValueError('nonempty roll policy submissions required')
    intents=[];selections=[]
    for submission in submissions:
        required={'actor','target','document','purpose'}
        if type(submission) is not dict or not required<=set(submission) or set(submission)-(required|{'context','decisions'}):
            raise ValueError('exact roll policy submission required')
        actor=submission['actor'];target=submission['target'];W.require_actors(engine,actor,target)
        selected=P.resolve(engine.r,submission['document'],context=submission.get('context'),decisions=submission.get('decisions'),
            _state_reader=lambda specs:STATE.read(engine,actor,target,specs))
        selections.append(selected)
        intents.append({'actor_id':actor.entity_id,'target_id':target.entity_id,'document':submission['document'],
            'purpose':submission['purpose'],'context':submission.get('context') or {},'decisions':submission.get('decisions') or {},
            'profile_hash':selected['profile_hash']})
    intent={'submissions':intents,'procedure':procedure}
    records=getattr(engine,'_roll_policy_requests',{})
    prior=TX.replay_result(records,request_id,intent,fingerprint_field='intent')
    if prior is not None:
        # Historical outcome is reusable even when a formerly owned provider
        # feature has ended. Its actual actor identity must still be present.
        for entry in prior['result']['policies']:
            provider_id=entry['provider_acquisition']['provider_id']
            if provider_id not in W.require_actors(engine,submissions[0]['actor']):raise ValueError('historical roll provider no longer present')
        return dict(prior['result'],replayed=True)
    signature=TX.request_fingerprint(intent)
    if any(selected['status']!='PolicyValuesReady' for selected in selections):
        return {'status':'PolicyRollsPending','policies':selections,'consumed':False}
    policies=[];requests=[]
    for submission in submissions:
        actor=submission['actor'];target=submission['target']
        prepared=policy(engine,actor,target,submission['document'],purpose=submission['purpose'],
            context=submission.get('context'),decisions=submission.get('decisions'))
        policies.append(prepared)
        if prepared['status']!='PolicyRollPlanPrepared':continue
        declaration=prepared['values']['roll_plan'];provider=W.require_actors(engine,actor,target)[declaration['provider_id']]
        requests.append({'actor':actor,'target':target,'provider':provider,'skill':declaration['skill'],
            'purpose':declaration['purpose'],'replacement':declaration.get('replacement'),
            'options':declaration['options'],'expected_plan':prepared['roll_plan']})
    if len(requests)!=len(submissions):
        return {'status':'PolicyRollsDenied' if any(p['status']=='PolicyRollPlanDenied' for p in policies) else 'PolicyRollsPending',
                'policies':policies,'consumed':False}
    def execute(staged):
        outcome=resolve(staged,requests,procedure)
        result={'status':'PolicyRollsCompleted','request_id':request_id,'policies':deepcopy(policies),'outcome':outcome,'consumed':True}
        next_records=dict(records);next_records[request_id]={'intent':signature,'result':deepcopy(result)}
        return result,next_records
    result,next_records=ACTION._staged_rolls(engine,execute)
    engine._roll_policy_requests=next_records
    return dict(result,replayed=False)
