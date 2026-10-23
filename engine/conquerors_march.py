"""Book Conqueror's March joins actual Orders, mounted movement and Pass.

The selected Move keeps its native effects and frequency. Only its geometry
changes, and only inside the existing live paid Pass producer.
"""
from copy import deepcopy
import common_checks as C
import combat_timing as TIME
import control_mount as MOUNT
import state_grants as G
import world_entities as W

RAMMING = 'feat/래밍-스피드'
FEATURE = 'feat/정복자의-행진'
RUN_UP = 'ability/도움닫기'
FEATURES = {RAMMING:(906,911), FEATURE:(913,918)}
PARENTS = {RAMMING:MOUNT.RIDER, FEATURE:RAMMING}
KEY = 'conquerors_march_uses'
FLAG = 'conquerors_march'
FAMILIES = ('대시','파열','폭발','원뿔','직선')


def records(actor, feature, *, active=False):
    import trainer_feature_acquisition as TFA
    return [row['static_acquisition'] for _,row,live in TFA._static_records(actor)
            if row['static_acquisition']['feature_id']==feature and (live or not active)]


def acquired(actor, feature=FEATURE):
    import acquired_features as A
    import trainer_feature_acquisition as TFA
    if not A.owned_rule_count(actor,feature):return None
    TFA.validate_actor(actor)
    found=records(actor,feature,active=True)
    if actor.kind!='trainer' or A.owned_rule_count(actor,feature)!=1 or len(found)!=1:
        raise ValueError('one actual source-specific Rider Feature acquisition required')
    parent=(MOUNT.acquired(actor,MOUNT.RIDER) if feature==RAMMING else acquired(actor,RAMMING))
    if parent is None:raise ValueError('actual current acquired Rider prerequisite required')
    return found[0]


def acquisition_snapshot(actor,feature):
    import skill_modifiers as S
    parent=(MOUNT.acquired(actor,MOUNT.RIDER) if feature==RAMMING else acquired(actor,RAMMING))
    if parent is None:raise ValueError('actual acquired Rider prerequisite required')
    return {'parent_request':parent['request_id'],
            'acrobatics':S.rank(actor.r,actor,'곡예')[2] if feature==FEATURE else 0,
            'athletics':S.rank(actor.r,actor,'육상')[2] if feature==FEATURE else 0}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if feature not in FEATURES or prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!={'parent_request','acrobatics','athletics'}:
        raise ValueError('exact acquisition-time Conqueror observations required')
    for field in ('acrobatics','athletics'):C.integer(snapshot[field],'Conqueror '+field,0)
    parents=(MOUNT._acquisitions(actor,MOUNT.RIDER) if feature==RAMMING else records(actor,RAMMING))
    if len([row for row in parents if row['request_id']==snapshot['parent_request']])!=1:
        raise ValueError('actual historical Rider Feature prerequisite required')
    if feature==RAMMING and (snapshot['acrobatics'] or snapshot['athletics']):
        raise ValueError('Ramming Speed adds no skill prerequisite')
    return Q.require(feature,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('skill','prerequisite',feature==RAMMING or max(snapshot['acrobatics'],snapshot['athletics'])>=4,
                'Adept Acrobatics or Athletics required')])


def _uses(actor):
    rows=actor.spec.get(KEY,[])
    if type(rows) is not list:raise ValueError('Conqueror Order history must be a list')
    return rows


def _seal(row):
    import trainer_feature_acquisition as TFA
    return TFA._digest('conquerors-march/order/v1',{k:v for k,v in row.items() if k!='integrity'})


def _target(engine,trainer,pokemon):
    import ability_transitions as AB
    W.require_actors(engine,trainer,pokemon)
    receipt=acquired(trainer)
    if receipt is None:raise ValueError('actual acquired Conqueror\'s March required')
    if pokemon.kind!='pokemon' or W.identity_field(engine,pokemon,'owner_id')!=trainer.entity_id:
        raise ValueError('Conqueror\'s March targets your actual Pokemon')
    if not AB.active(pokemon,RUN_UP):raise ValueError('actual active Run Up Ability required')
    if not pokemon.on_field or pokemon.captured or pokemon.fainted:
        raise ValueError('present available Pokemon required')
    if not engine.encounter_active or engine.round_start_seconds is None:
        raise ValueError('this-round Order requires an open combat round')
    return receipt


def live(pokemon):
    return [row for row in TIME.records(pokemon) if FLAG in row]


def use(engine,trainer,pokemon,*,event_id):
    """One paid native Order; mounting is checked when the Move is used."""
    import trainer_feature_acquisition as TFA
    import moment_of_action as ORDER
    import priority_limited as PRIORITY
    import turn as TURN
    import action_lifecycle as ACTION
    import passive_events as PASSIVE,heavy_injury_adapter as HEAVY
    PASSIVE.ensure_clear(engine);HEAVY.ensure_clear(engine)
    TFA._text(event_id,'Conqueror Order event identity')
    W.require_actors(engine,trainer,pokemon)
    intent={'issuer_id':trainer.entity_id,'target_id':pokemon.entity_id}
    validate_world(engine,W.actor_index(engine))
    old=next((row for row in _uses(trainer) if row['id']==event_id),None)
    if old is not None:
        if old['intent']!=intent:raise ValueError('Conqueror Order replay changed its target')
        return deepcopy(old)
    _target(engine,trainer,pokemon)
    def apply(e,a,p):
        receipt=_target(e,a,p)
        ACTION.ensure_resolutions_clear(e)
        request,delivery=ORDER._communication(e,a,p,event_id,None,source=FEATURE,label='Conqueror\'s March')
        if e._active_turn_actor is None:
            import body_modes as BODY,effect_lifetimes as LIFE
            if not TURN.can_act(e,a) or not ACTION.status_permission(e,a,'standard') or not BODY.permits(a,'standard') or LIFE.forbids(a,'priority'):
                raise ValueError('actual Standard Priority action permission required')
            paid=PRIORITY.reserve(e,a,action='standard',source=FEATURE,subject=event_id,communication=delivery)
            payment={'kind':'priority_limited','receipt_id':paid['id']}
        else:
            if e._active_turn_actor is not a or not TURN.spend(e,a,'standard',FEATURE):
                raise ValueError('Conqueror Order requires its actual Standard action')
            import order_actions as ORDERS
            payment=ORDERS.payment(e,a,FEATURE) or {'kind':'standard','turn':a.custom_conditions.get('combat_turn_serial',0)}
        for previous in list(live(p)):
            if previous[FLAG]['issuer_id']==a.entity_id:
                TIME.expire(e,p,previous,ending='replaced',event={'kind':'replacement','order_id':event_id})
        row={'id':event_id,'intent':intent,'source':deepcopy(receipt['source']),
             'acquisition_request':receipt['request_id'],'round':e.round_no,'at':e.elapsed_seconds,
             'communication':{'request_id':request,'result':delivery},'payment':payment,
             'qualification':{'owner_id':a.entity_id,'ability_id':RUN_UP}}
        row['integrity']=_seal(row);a.spec.setdefault(KEY,[]).append(row)
        TIME.install(e,p,{'source':FEATURE,'round_end_deadline':e.round_no,'encounter_end':True,
                         FLAG:{'issuer_id':a.entity_id,'order_id':event_id,'integrity':row['integrity']}})
        e.time_actors([a,p])
        import cheerleader as CHEER
        import duelist as DUELIST
        origin={'kind':'conquerors_march','source':FEATURE,'use_id':event_id}
        CHEER.issue(e,a,[p],origin);DUELIST.after_order(e,a,[p],origin)
        validate_world(e,W.actor_index(e))
        return deepcopy(row)
    return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def current(engine,pokemon):
    """Select only an owned, unexpired Order on a current actual mounted body."""
    import ability_transitions as AB
    W.require_actors(engine,pokemon)
    if pokemon.kind!='pokemon' or not AB.active(pokemon,RUN_UP):return None
    index=W.actor_index(engine)
    if not list(MOUNT.mounted_pairs(pokemon)):return None
    candidates=[]
    for effect in live(pokemon):
        origin=effect[FLAG];owner=index.get(origin['issuer_id'])
        if (effect['round_end_deadline']==engine.round_no and owner is not None
                and W.identity_field(engine,pokemon,'owner_id')==owner.entity_id
                and acquired(owner) is not None):
            row=next(row for row in _uses(owner) if row['id']==origin['order_id'])
            candidates.append(row)
    if len(candidates)>1:raise ValueError('one current Conqueror Order per actual owned Pokemon required')
    return candidates[0] if candidates else None


def eligible(move):
    return any(family in move.get('range','') for family in FAMILIES)


def conversion(engine,pokemon,move):
    if not eligible(move):raise ValueError('Conqueror converts only Dash, Burst, Blast, Cone or Line Moves')
    row=current(engine,pokemon)
    if row is None:raise ValueError('this-round Conqueror Order and actual current mounted Run Up Pokemon required')
    return {'issuer_id':row['intent']['issuer_id'],'order_id':row['id'],'integrity':row['integrity'],
            'mounted_riders':sorted(rider.entity_id for rider,_ in MOUNT.mounted_pairs(pokemon))}


def require_conversion(engine,pokemon,proof):
    row=current(engine,pokemon)
    expected=None if row is None else {'issuer_id':row['intent']['issuer_id'],'order_id':row['id'],'integrity':row['integrity'],
        'mounted_riders':sorted(rider.entity_id for rider,_ in MOUNT.mounted_pairs(pokemon))}
    if proof!=expected or expected is None:raise ValueError('Conqueror Pass lost its actual live mounted Order')
    return row


def withdraw(engine,trainer,feature):
    if feature!=FEATURE:return
    for target in W.actor_index(engine).values():
        for effect in list(live(target)):
            if effect[FLAG]['issuer_id']==trainer.entity_id:
                TIME.expire(engine,target,effect,ending='source_withdrawn',event={'kind':'source_withdrawal','source':FEATURE})


def _order_origin(engine,actor_id,proof,round_no):
    index=W.actor_index(engine);owner=index.get(proof.get('issuer_id'))
    matches=[] if owner is None else [row for row in _uses(owner) if row['id']==proof.get('order_id')]
    if (len(matches)!=1 or matches[0]['integrity']!=proof.get('integrity')
            or matches[0]['intent']['target_id']!=actor_id or matches[0]['round']!=round_no):
        raise ValueError('converted Pass requires its actual historical Conqueror Order')
    return matches[0]


def validate_conversion(engine,actor_id,proof,round_no):
    """Historical paid Pass proof survives expiry, dismount and retraining."""
    row=_order_origin(engine,actor_id,proof,round_no)
    index=W.actor_index(engine)
    riders=proof.get('mounted_riders')
    if (set(proof)!={'issuer_id','order_id','integrity','mounted_riders'} or type(riders) is not list
            or not riders or len(set(riders))!=len(riders) or any(uid not in index or uid==actor_id for uid in riders)):
        raise ValueError('converted Pass requires its actual mounted-body observation')
    return row


def validate_world(engine,index):
    import trainer_feature_acquisition as TFA
    import moment_of_action as ORDER
    import priority_limited as PRIORITY
    seen=set()
    for owner in index.values():
        for row in _uses(owner):
            fields={'id','intent','source','acquisition_request','round','at','communication','payment','qualification','integrity'}
            if type(row) is not dict or set(row)!=fields or row['integrity']!=_seal(row) or row['id'] in seen:
                raise ValueError('Conqueror Order identity or evidence changed')
            seen.add(row['id']);target=index.get(row['intent'].get('target_id'))
            if (owner.kind!='trainer' or target is None or target.kind!='pokemon'
                    or row['intent']!={'issuer_id':owner.entity_id,'target_id':target.entity_id}
                    or row['qualification']!={'owner_id':owner.entity_id,'ability_id':RUN_UP}
                    or row['source']!=TFA._static_source(engine.r,FEATURE)
                    or len([r for r in records(owner,FEATURE) if r['request_id']==row['acquisition_request']])!=1):
                raise ValueError('Conqueror Order actual source, acquired issuer or target changed')
            C.integer(row['round'],'Conqueror round',1,engine.round_no);C.integer(row['at'],'Conqueror time',0,engine.elapsed_seconds)
            communication=row['communication']
            delivered=ORDER._delivery(engine,owner.entity_id,target.entity_id,communication['request_id'],row['at'])
            if delivered!=communication['result']:raise ValueError('Conqueror delivered Order changed')
            payment=row['payment']
            if payment.get('kind')=='priority_limited':
                receipts=[r for r in PRIORITY.records(owner) if r['id']==payment.get('receipt_id')]
                if (len(receipts)!=1 or receipts[0]['source']!=FEATURE or receipts[0]['subject_id']!=row['id']
                        or receipts[0]['payment']['funded']!={'standard':1} or receipts[0]['communication']!=delivered):
                    raise ValueError('Conqueror Order lost its native reserved Standard action')
            elif payment.get('kind')=='free_order':
                import order_actions as ORDERS
                ORDERS.validate(engine,owner,target,FEATURE,payment)
            elif payment.get('kind')=='standard':
                if set(payment)!={'kind','turn'}:raise ValueError('Conqueror actual Standard payment required')
                C.integer(payment['turn'],'Conqueror actual paid turn',1,owner.custom_conditions.get('combat_turn_serial',0))
            else:raise ValueError('Conqueror native Standard payment required')
    for target in index.values():
        issuers=set()
        for effect in live(target):
            proof=effect[FLAG]
            row=_order_origin(engine,target.entity_id,proof,effect['round_end_deadline'])
            if (set(proof)!={'issuer_id','order_id','integrity'} or effect['source']!=FEATURE or effect.get('encounter_end') is not True
                    or not engine.encounter_active or effect['round_end_deadline']!=engine.round_no
                    or proof['issuer_id'] in issuers):
                raise ValueError('Conqueror live effect lost its native current-round source')
            issuers.add(proof['issuer_id'])
            owner=index[proof['issuer_id']]
            if not any(r['request_id']==row['acquisition_request'] for r in records(owner,FEATURE,active=True)):
                raise ValueError('Conqueror live effect survived its actual source withdrawal')
    return True
