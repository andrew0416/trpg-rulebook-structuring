"""Book Moment of Action: acquired Orders source and atomic temporary AP producer."""
from copy import deepcopy
import acquired_features as A
import common_checks as C
import effect_instances as E
import trainer_feature_acquisition as TFA

FEATURE='feat/행동의-순간'
CLASS='class/치어리더'
TRAINING='feat/영감성-훈련'
CLAUSE='input/ch04-trainer-classes.md:698-703'
KEY='moment_of_action_uses'


def receipts(actor,feature,*,active=False):
    return [row['static_acquisition'] for _,row,live in TFA._static_records(actor)
            if row['static_acquisition']['feature_id']==feature and (live or not active)]


def acquisition_snapshot(actor,feature):
    import skill_modifiers as SKILLS
    parent={CLASS:TRAINING,FEATURE:CLASS}.get(feature)
    parents=receipts(actor,parent,active=True) if parent else []
    if parent and (len(parents)!=1 or A.owned_rule_count(actor,parent)!=1):
        raise ValueError('actual acquired prerequisite receipt required')
    return {'charm':SKILLS.rank(actor.r,actor,'매력')[2] if feature!=FEATURE else 0,
            'command':SKILLS.rank(actor.r,actor,'명령')[2] if feature==TRAINING else 0,
            'class_slots':len(A.class_instances(actor)) if feature==CLASS else 0,
            'parent_request':parents[0]['request_id'] if parent else None}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!={'charm','command','class_slots','parent_request'}:
        raise ValueError('exact acquisition-time Cheerleader prerequisite observations required')
    for field in ('charm','command','class_slots'):C.integer(snapshot[field],field,0)
    parent={CLASS:TRAINING,FEATURE:CLASS}.get(feature)
    if parent:
        rows=[row for row in receipts(actor,parent) if row['request_id']==snapshot['parent_request']]
        if len(rows)!=1:raise ValueError('historical prerequisite acquisition receipt required')
    elif snapshot['parent_request'] is not None:raise ValueError('Inspired Training has no prerequisite Feature')
    checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual trainer required')]
    if feature in (TRAINING,CLASS):checks.append(Q.check('charm','prerequisite',snapshot['charm']>=3,'Novice Charm required'))
    elif snapshot['charm']!=0:raise ValueError('Moment of Action has no independent Charm prerequisite')
    if feature==TRAINING:checks.append(Q.check('command','prerequisite',snapshot['command']>=2,'Untrained Command required'))
    elif snapshot['command']!=0:raise ValueError('this Feature has no independent Command prerequisite')
    if feature==CLASS:checks.append(Q.check('class_slots','capacity',snapshot['class_slots']<4,'one of four class slots required'))
    elif snapshot['class_slots']!=0:raise ValueError('only the class acquisition consumes a class slot')
    return Q.require(feature,'native','acquire',checks)


def acquired(actor):
    TFA.validate_actor(actor)
    rows=receipts(actor,FEATURE,active=True)
    if len(rows)!=1 or A.owned_rule_count(actor,FEATURE)!=1:
        raise ValueError('Moment of Action requires its actual acquisition source')
    parents=receipts(actor,CLASS,active=True)
    if len(parents)!=1 or A.owned_rule_count(actor,CLASS)!=1:
        raise ValueError('Moment of Action requires its current acquired Cheerleader source')
    return rows[0]


def _uses(actor):
    value=actor.spec.get(KEY,[])
    if type(value) is not list:raise ValueError('actual Moment of Action producer ledger required')
    return value


def _communication(engine,actor,target,use_id,request,*,source=FEATURE,label='Moment of Action'):
    import perception_communicate as COMM
    if request is None:
        request=use_id+':communication:'+target.entity_id
        declaration={'id':source,'source':source,'capabilities':[],'requirements':[],
            'mode':'auditory','range':None,'path':'auditory','medium':[],'consent':{'kind':'none'},
            'blockers':[],'connection':None,'frequency':{'kind':'at_will','uses':1},'retry':None,'distance_exceptions':[]}
        result=COMM.send(engine,actor,target,declaration,label,request_id=request)
    else:
        E.text(request,'actual established communication request')
        stored=COMM._state(engine)['requests'].get(request)
        if stored is None:raise ValueError('actual established communication delivery required')
        prior=_delivery(engine,actor.entity_id,target.entity_id,request,engine.elapsed_seconds)
        declaration=dict(COMM._state(engine)['policies'][prior['source']]['declaration'],id=use_id)
        request=use_id+':communication:'+target.entity_id
        result=COMM.send(engine,actor,target,declaration,label,request_id=request)
    _delivery(engine,actor.entity_id,target.entity_id,request,engine.elapsed_seconds)
    return request,deepcopy(result)


def _delivery(engine,issuer,target,request,at):
    import perception_communicate as COMM
    state=COMM._state(engine);stored=state['requests'].get(request)
    result=stored['result'] if stored else {}
    attempts=[r for r in state['attempts'] if r['request_id']==request]
    if (result.get('status')!='delivered' or result.get('sender_id')!=issuer or result.get('recipient_id')!=target
            or len(attempts)!=1 or attempts[0]['at']!=at):
        raise ValueError('actual contemporaneous order communication was not delivered')
    return result


def use(engine,actor,targets,*,funding,allies,communication=None):
    import world_entities as W,state_grants as G,temporary_ap as AP,priority_limited as P,combat_timing as T
    import passive_events as PASSIVE,heavy_injury_adapter as HEAVY
    PASSIVE.ensure_clear(engine);HEAVY.ensure_clear(engine)
    W.require_actors(engine,actor)
    import commander as COMMANDER
    commander=COMMANDER.scope(engine,actor,FEATURE)
    expanded=bool(commander is not None and commander['activation']['modifier'] in (COMMANDER.BATTLE,COMMANDER.TIP)
        and [c['target'] for c in commander['assignments'] if c['feature']==FEATURE]==list(targets))
    if type(targets) not in (list,tuple) or len(targets)>2 and not expanded:
        raise ValueError('explicit zero, one or two allied Trainers required')
    W.require_actors(engine,*targets)
    ids=[target.entity_id for target in targets]
    if len(set(ids))!=len(ids):raise ValueError('distinct allied Trainers required')
    if type(funding) is not dict or set(funding)!=set(ids) or type(allies) is not dict or set(allies)!=set(ids):
        raise ValueError('exact per-target funding and allied observations required')
    if communication is not None and (type(communication) is not dict or set(communication)!=set(ids)):
        raise ValueError('exact per-target established communication requests required')
    receipt=acquired(actor)
    for target in targets:
        fact=allies[target.entity_id]
        if target is actor or target.kind!='trainer':raise ValueError('Orders require other allied Trainers')
        if type(fact) is not dict or set(fact)!={'allied','reason'} or fact['allied'] is not True:
            raise ValueError('actual allied relationship observation required')
        E.text(fact['reason'],'allied relationship reason')
        if actor.side and target.side and actor.side!=target.side:raise ValueError('actual opposing sides are not allies')
        AP.policy(funding[target.entity_id])
    import order_actions as ORDERS
    if engine.encounter_active:
        ORDERS.preflight(engine,actor,FEATURE,action=COMMANDER.priority_action(engine,actor,FEATURE));T.current(engine)
    def apply(e,owner,*recipients):
        import turn as TURN,action_lifecycle as ACTION,body_modes as BODY,effect_lifetimes as LIFE
        if ORDERS.priority(e,owner,FEATURE):
            ACTION.ensure_resolutions_clear(e)
            if not TURN.can_act(e,owner) or not ACTION.status_permission(e,owner,'standard') or not BODY.permits(owner,'standard') or LIFE.forbids(owner,'priority'):
                raise ValueError('actual Standard Priority action permission required')
        e.time_actors([owner,*recipients])
        use_id='moment-of-action:'+owner.entity_id+':'+str(len(_uses(owner))+1)
        deliveries={}
        for target in recipients:
            request,result=_communication(e,owner,target,use_id,None if communication is None else communication[target.entity_id])
            deliveries[target.entity_id]={'request_id':request,'result':result}
        group={'status':'delivered','recipients':deepcopy(deliveries)}
        if ORDERS.priority(e,owner,FEATURE):
            payment={'kind':'priority_limited','receipt_id':P.reserve(e,owner,action=COMMANDER.priority_action(e,owner,FEATURE),source=FEATURE,subject=use_id,communication=group)['id']}
        else:
            if not TURN.spend(e,owner,'standard','Moment of Action'):raise ValueError('actual Standard action permission required')
            payment={'kind':'standard','action':'standard'}
        row={'id':use_id,'issuer_id':owner.entity_id,'source':deepcopy(receipt['source']),
             'acquisition_request_id':receipt['request_id'],'round':e.round_no,'at':e.elapsed_seconds,
             'targets':{},'payment':payment,'communication':deliveries}
        if expanded:row['commander_activation']=commander['activation']['id']
        for target in recipients:
            origin={'issuer_id':owner.entity_id,'use_id':use_id,'acquisition_request_id':receipt['request_id']}
            effect=AP.grant(e,target,source=FEATURE,amount=1,origin=origin,funding=funding[target.entity_id],issuer=owner)
            row['targets'][target.entity_id]={'effect_id':effect['id'],'funding':deepcopy(funding[target.entity_id]),
                'allied':deepcopy(allies[target.entity_id]),'issuer_side':owner.side,'recipient_side':target.side}
        row['integrity']=TFA._digest('moment-of-action/producer/v1',row)
        owner.spec.setdefault(KEY,[]).append(row)
        validate_world(e,W.actor_index(e))
        import cheerleader as CHEER
        CHEER.after_moment(e,owner,recipients,row)
        return deepcopy(row)
    return G.transition(engine,actor,apply,participants=targets,include_rulings=True)


def validate_effect_origin(actor,row):
    origin=row.get('origin')
    if type(origin) is not dict or set(origin)!={'issuer_id','use_id','acquisition_request_id'}:
        raise ValueError('Moment of Action requires its exact actual producer origin')
    for value in origin.values():E.text(value,'Moment of Action producer identity')
    if (row['source']!=FEATURE or actor.kind!='trainer' or actor.entity_id==origin['issuer_id']
            or row[E.KEY].get('applied_by_actor_id')!=origin['issuer_id'] or row['effect']['amount']!=1):
        raise ValueError('Moment of Action issuer, recipient or one-AP amount changed')
    issuer=row.get('issuer_actor')
    if issuer is None or issuer.entity_id!=origin['issuer_id'] or issuer.kind!='trainer':raise ValueError('actual Moment of Action issuer reference required')
    uses=[r for r in _uses(issuer) if r['id']==origin['use_id']]
    if len(uses)!=1 or uses[0]['acquisition_request_id']!=origin['acquisition_request_id'] or uses[0]['targets'].get(actor.entity_id,{}).get('effect_id')!=row['id']:
        raise ValueError('Moment of Action AP lacks its actual issuer ledger link')
    issued=uses[0]
    if (issued['integrity']!=TFA._digest('moment-of-action/producer/v1',{k:v for k,v in issued.items() if k!='integrity'})
            or issued['source']!=TFA._static_source(issuer.r,FEATURE)
            or len([r for r in receipts(issuer,FEATURE) if r['request_id']==origin['acquisition_request_id']])!=1):
        raise ValueError('Moment of Action actual issuance authority changed')


def validate_world(engine,index):
    import temporary_ap as AP,priority_limited as P
    linked=set()
    for issuer in index.values():
        for serial,row in enumerate(_uses(issuer),1):
            fields={'id','issuer_id','source','acquisition_request_id','round','at','targets','payment','communication','integrity'}
            if type(row) is not dict or set(row) not in (fields,fields|{'commander_activation'}) or row['integrity']!=TFA._digest('moment-of-action/producer/v1',{k:v for k,v in row.items() if k!='integrity'}):
                raise ValueError('Moment of Action producer evidence changed')
            if row['id']!='moment-of-action:'+issuer.entity_id+':'+str(serial) or row['issuer_id']!=issuer.entity_id or row['source']!=TFA._static_source(issuer.r,FEATURE):
                raise ValueError('Moment of Action source or actual issuer changed')
            if len([r for r in receipts(issuer,FEATURE) if r['request_id']==row['acquisition_request_id']])!=1:
                raise ValueError('Moment of Action actual historical acquisition missing')
            C.integer(row['at'],'Moment of Action issue time',0,engine.elapsed_seconds)
            C.integer(row['round'],'Moment of Action issue round',0,engine.round_no)
            targets=row['targets']
            expanded=__import__('commander').group_authority(engine,issuer,FEATURE,targets,row.get('commander_activation'))
            if (type(targets) is not dict or len(targets)>2 and not expanded or set(row['communication'])!=set(targets)
                    or 'commander_activation' in row and not expanded):raise ValueError('exact Moment of Action target roster required')
            payment=row['payment']
            if payment.get('kind')=='priority_limited':
                paid=[r for r in P.records(issuer) if r['id']==payment.get('receipt_id')]
                if len(paid)!=1 or paid[0]['source']!=FEATURE or paid[0]['subject_id']!=row['id'] or paid[0]['payment']['funded']!=__import__('commander').priority_funded(issuer,FEATURE,paid[0]['id'],row.get('commander_activation')) or paid[0]['communication']!={'status':'delivered','recipients':row['communication']}:
                    raise ValueError('Moment of Action actual Standard reservation missing')
            elif payment!={'kind':'standard','action':'standard'}:raise ValueError('Moment of Action Standard payment changed')
            for target_id,proof in targets.items():
                target=index.get(target_id)
                if target is None or target is issuer or target.kind!='trainer':raise ValueError('Moment of Action actual Trainer recipient missing')
                if (set(proof)!={'effect_id','funding','allied','issuer_side','recipient_side'} or proof['allied'].get('allied') is not True
                        or proof['issuer_side'] and proof['recipient_side'] and proof['issuer_side']!=proof['recipient_side']):raise ValueError('Moment of Action allied target evidence changed')
                E.text(proof['allied'].get('reason'),'historical allied relationship reason')
                delivered=row['communication'][target_id]
                if delivered['result']!=_delivery(engine,issuer.entity_id,target_id,delivered['request_id'],row['at']):raise ValueError('actual order delivery differs from issuance')
                effects=[r for r in AP.all_records(target) if r['id']==proof['effect_id']]
                if len(effects)!=1:raise ValueError('Moment of Action issuance has no actual target AP grant')
                effect=effects[0];validate_effect_origin(target,effect)
                if effect['issuer_actor'] is not issuer:raise ValueError('Moment of Action issuer reference is not the actual world actor')
                expected={'issuer_id':issuer.entity_id,'use_id':row['id'],'acquisition_request_id':row['acquisition_request_id']}
                if effect['origin']!=expected or effect['at']!=row['at'] or effect['issued_round']!=row['round'] or effect['effect']['funding']!=proof['funding']:
                    raise ValueError('Moment of Action producer and target AP disagree')
                if effect['id'] in linked:raise ValueError('one AP grant cannot fulfill two order issuances')
                linked.add(effect['id'])
    actual={r['id'] for actor in index.values() for r in AP.all_records(actor) if r['source']==FEATURE}
    if actual!=linked:raise ValueError('Moment of Action AP requires its actual producer ledger')
    return True
