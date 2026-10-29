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
LEAN = 'feat/기대기'
REPRISAL = 'feat/카발리어의-보복'
OVERRUN = 'feat/침략'
FEATURES = {RAMMING:(906,911), FEATURE:(913,918), LEAN:(926,931), REPRISAL:(933,938), OVERRUN:(940,945)}
PARENTS = {RAMMING:MOUNT.RIDER, FEATURE:RAMMING, LEAN:MOUNT.RIDE_AS_ONE, REPRISAL:MOUNT.RIDE_AS_ONE, OVERRUN:FEATURE}
KEY = 'conquerors_march_uses'
FLAG = 'conquerors_march'
FAMILIES = ('대시','파열','폭발','원뿔','직선')
CSV = 'C2CSV/input/db/feats.csv:R141:main'
CSV_SOURCE = {'file':'input/db/feats.csv','sha256':'4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd','record_span':[141,141]}


def _edition(rules, value):
    """An explicit CSV extra Dash keyword; the common acquired Feature is unchanged."""
    if value is None:return None
    if value != CSV:raise ValueError('exact reviewed Conqueror source edition required')
    from source_context import verified_source
    rules.ruleset.require({'id':CSV,'source':{'file':'db/feats.csv','record_span':[141,141]}})
    verified_source(rules,CSV_SOURCE,label='Conqueror CSV')
    return value


def records(actor, feature, *, active=False):
    import trainer_feature_acquisition as TFA
    return [record for _, record in TFA.static_acquisitions(actor, feature, active=active)]


def acquired(actor, feature=FEATURE):
    import acquired_features as A
    import trainer_feature_acquisition as TFA
    if not A.owned_rule_count(actor,feature):return None
    TFA.validate_actor(actor)
    found=records(actor,feature,active=True)
    if actor.kind!='trainer' or A.owned_rule_count(actor,feature)!=1 or len(found)!=1:
        raise ValueError('one actual source-specific Rider Feature acquisition required')
    parent=_parent(actor,feature)
    if parent is None:raise ValueError('actual current acquired Rider prerequisite required')
    return found[0]


def _parent(actor,feature):
    parent=PARENTS[feature]
    return MOUNT.acquired(actor,parent) if parent in MOUNT.FEATURES else acquired(actor,parent)


def acquisition_snapshot(actor,feature):
    import skill_modifiers as S
    parent=_parent(actor,feature)
    if parent is None:raise ValueError('actual acquired Rider prerequisite required')
    return {'parent_request':parent['request_id'],
            'acrobatics':S.rank(actor.r,actor,'곡예')[2] if feature not in (RAMMING,LEAN) else 0,
            'athletics':S.rank(actor.r,actor,'육상')[2] if feature not in (RAMMING,LEAN) else 0}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if feature not in FEATURES or prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!={'parent_request','acrobatics','athletics'}:
        raise ValueError('exact acquisition-time Conqueror observations required')
    for field in ('acrobatics','athletics'):C.integer(snapshot[field],'Conqueror '+field,0)
    parent=PARENTS[feature]
    parents=MOUNT._acquisitions(actor,parent) if parent in MOUNT.FEATURES else records(actor,parent)
    if len([row for row in parents if row['request_id']==snapshot['parent_request']])!=1:
        raise ValueError('actual historical Rider Feature prerequisite required')
    if feature in (RAMMING,LEAN) and (snapshot['acrobatics'] or snapshot['athletics']):
        raise ValueError('this Rider Feature adds no skill prerequisite')
    minimum=0 if feature in (RAMMING,LEAN) else 4 if feature==FEATURE else 5
    return Q.require(feature,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('skill','prerequisite',max(snapshot['acrobatics'],snapshot['athletics'])>=minimum,
                'printed Acrobatics or Athletics rank required')])


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


def use(engine,trainer,pokemon,*,event_id,edition=None):
    """One paid native Order; mounting is checked when the Move is used."""
    import trainer_feature_acquisition as TFA
    import moment_of_action as ORDER
    import priority_limited as PRIORITY
    import turn as TURN
    import action_lifecycle as ACTION
    import passive_events as PASSIVE,heavy_injury_adapter as HEAVY
    PASSIVE.ensure_clear(engine);HEAVY.ensure_clear(engine)
    TFA._text(event_id,'Conqueror Order event identity')
    selected_edition=_edition(engine.r,edition)
    W.require_actors(engine,trainer,pokemon)
    intent={'issuer_id':trainer.entity_id,'target_id':pokemon.entity_id}
    if selected_edition is not None:intent['edition']=selected_edition
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
    return _conversion_proof(engine,pokemon,row)


def _conversion_proof(engine,pokemon,row):
    result={'issuer_id':row['intent']['issuer_id'],'order_id':row['id'],'integrity':row['integrity'],
            'mounted_riders':sorted(rider.entity_id for rider,_ in MOUNT.mounted_pairs(pokemon))}
    selected=_edition(engine.r,row['intent'].get('edition'))
    if selected is not None:result['edition']=selected
    import native_order_transfer as TRANSFER
    effect=next(effect for effect in live(pokemon) if effect[FLAG]['order_id']==row['id'])
    if TRANSFER.KEY in effect:result[TRANSFER.KEY]=deepcopy(effect[TRANSFER.KEY])
    return result


def require_conversion(engine,pokemon,proof):
    row=current(engine,pokemon)
    expected=None if row is None else _conversion_proof(engine,pokemon,row)
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
    import native_order_transfer as TRANSFER
    if TRANSFER.KEY in proof:actor_id=TRANSFER.origin_id(proof,index[actor_id])
    if (len(matches)!=1 or matches[0]['integrity']!=proof.get('integrity')
            or matches[0]['intent']['target_id']!=actor_id or matches[0]['round']!=round_no):
        raise ValueError('converted Pass requires its actual historical Conqueror Order')
    return matches[0]


def validate_conversion(engine,actor_id,proof,round_no):
    """Historical paid Pass proof survives expiry, dismount and retraining."""
    row=_order_origin(engine,actor_id,proof,round_no)
    index=W.actor_index(engine)
    riders=proof.get('mounted_riders')
    selected=_edition(engine.r,row['intent'].get('edition'))
    fields={'issuer_id','order_id','integrity','mounted_riders'}|({'edition'} if selected is not None else set())
    if 'native_order_handoff' in proof:fields.add('native_order_handoff')
    if (set(proof)!=fields or proof.get('edition')!=selected or type(riders) is not list
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
            expected_intent={'issuer_id':owner.entity_id,'target_id':target.entity_id} if target is not None else {}
            selected=_edition(engine.r,row['intent'].get('edition'))
            if selected is not None:expected_intent['edition']=selected
            if (owner.kind!='trainer' or target is None or target.kind!='pokemon'
                    or row['intent']!=expected_intent
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
            row=_order_origin(engine,__import__('native_order_transfer').origin_id(effect,target),proof,effect['round_end_deadline'])
            if (set(proof)!={'issuer_id','order_id','integrity'} or effect['source']!=FEATURE or effect.get('encounter_end') is not True
                    or not engine.encounter_active or effect['round_end_deadline']!=engine.round_no
                    or proof['issuer_id'] in issuers):
                raise ValueError('Conqueror live effect lost its native current-round source')
            issuers.add(proof['issuer_id'])
            owner=index[proof['issuer_id']]
            if not any(r['request_id']==row['acquisition_request'] for r in records(owner,FEATURE,active=True)):
                raise ValueError('Conqueror live effect survived its actual source withdrawal')
    validate_native(engine,index)
    return True


def interested(engine):
    import acquired_features as A
    return any(A.owned_rule_count(actor,uid) for actor in W.actor_index(engine).values()
               for uid in (LEAN,REPRISAL,OVERRUN))


def lean_interested(engine,target):
    return any(acquired(owner,LEAN) is not None for owner,_ in MOUNT.ride_pairs(engine,target))


def event_interested(engine,attacker,target):
    return (lean_interested(engine,target) or
        any(acquired(owner,REPRISAL) is not None for owner,_ in MOUNT.mounted_pairs(target)) or
        any(acquired(owner,OVERRUN) is not None for owner,_ in MOUNT.mounted_pairs(attacker)))


def damage_selection(engine,event,precision_facts,damage=None):
    """Retain an actual selected calculation, not a second speculative roll."""
    import coordinator as OBS
    native=engine._passive_events.get(event['passive_event'])
    if native is None:return None
    row=native.get('rider_damage_selection')
    if damage is None:
        if row is None:return None
        if (row['sha256']!=OBS._damage_seal(row) or row['event_id']!=native['id'] or
            row['actor_id']!=event['attacker'].entity_id or row['target_id']!=event['target'].entity_id or
            row['move_id']!=event['move']['id']):raise ValueError('actual Rider damage selection changed')
        memo={id(a):a for a in W.actor_index(engine).values()};memo[id(engine)]=engine
        event.update(deepcopy(row['event'],memo));precision_facts.update(deepcopy(row['precision_facts']))
        return row['damage']
    if not lean_interested(engine,event['target']):return None
    memo={id(a):a for a in W.actor_index(engine).values()};memo[id(engine)]=engine
    row={'event_id':native['id'],'actor_id':event['attacker'].entity_id,
         'target_id':event['target'].entity_id,'move_id':event['move']['id'],
         'event':deepcopy(event,memo),'precision_facts':deepcopy(precision_facts),'damage':damage}
    row['sha256']=OBS._damage_seal(row);native['rider_damage_selection']=row


def _positive_damage(engine,event,damage):
    import effects_ext as EXT
    if event.get('damage_floor'):damage=min(damage,max(0,event['target'].hp-1))
    return EXT.cap_damage(engine,event['target'],damage)>0


def damage_scope(method):
    from functools import wraps
    @wraps(method)
    def run(engine,attacker,target,*args,**kwargs):
        try:return method(engine,attacker,target,*args,**kwargs)
        finally:
            row=getattr(engine,'_rider_lean_pair',None)
            if row and row['event']['attacker'] is attacker and row['event']['target'] is target:
                del engine._rider_lean_pair
    return run


def _free_ready(engine,owner,feature):
    import turn as TURN, action_lifecycle as ACTION, body_modes as BODY, frequency as F
    return (not owner.dead and owner.on_field and not owner.captured and TURN.can_act(engine,owner)
            and ACTION.status_permission(engine,owner,'free',new_action=True) and BODY.permits(owner,'free')
            and F.activation_allowed(owner,feature,{'kind':'scene','uses':2},engine=engine,action_actor=owner))


def overrun(engine,attacker,target,move,event):
    """The actual native Damage Roll, not a passive speculative damage preview."""
    if event is None or move.get('class') not in ('물리','특수'):return {'bonus':0,'reduction':0}
    if 'rider_overrun' in event:return event['rider_overrun']
    import ability_transitions as AB,action_lifecycle as ACTION,frequency as F
    if not AB.active(attacker,RUN_UP) or not any(k in move.get('range','') for k in ('대시','통과')):
        return {'bonus':0,'reduction':0}
    choices=[rider for rider,_ in MOUNT.mounted_pairs(attacker)
             if acquired(rider,OVERRUN) is not None and _free_ready(engine,rider,OVERRUN)]
    for owner in choices:
        answer=engine.rulings.decide({'type':'rider_overrun','unit':OVERRUN,'actor':owner.name,
            'target':target.name,'pokemon':attacker.name,'move':move['id'],
            'text':'Use Overrun on this actual Damage Roll?',
            'bonus':attacker.staged('spe'),'damage_reduction':target.staged('spe')})
        if answer is not None and type(answer) is not bool:raise ValueError('explicit Overrun use or decline required')
        if answer is not True:continue
        ACTION.triggered_free_action(engine,owner,OVERRUN)
        F.consume_activation(owner,OVERRUN,{'kind':'scene','uses':2},engine=engine,action_actor=owner)
        result={'bonus':attacker.staged('spe'),'reduction':target.staged('spe'),
                'owner_id':owner.entity_id,'acquisition':acquired(owner,OVERRUN)['request_id']}
        event['rider_overrun']=result
        return result
    event['rider_overrun']={'bonus':0,'reduction':0}
    return event['rider_overrun']


def observe_hit(engine,attacker,target,move,completion_id,event_id):
    """Capture the actual mounted relation before faint/dismount consequences."""
    attacker_side,target_side=getattr(attacker,'side',None),getattr(target,'side',None)
    if (completion_id is None or event_id is None or attacker is target
            or attacker_side is None or target_side is None or attacker_side==target_side):return
    import action_points as AP,root_resolution as R
    completion=engine._move_completions[completion_id]
    for owner,mount in MOUNT.mounted_pairs(target):
        if acquired(owner,REPRISAL) is None or not engine.adjacent(owner,attacker):continue
        facts={'owner_id':owner.entity_id,'mount_id':mount.entity_id,'foe_id':attacker.entity_id,
               'completion_id':completion_id,'event_id':event_id,'move_id':move['id'],
               'acquisition':acquired(owner,REPRISAL)['request_id'],'round':engine.round_no}
        completion.setdefault('rider_reprisal',{}).setdefault(event_id+':'+owner.entity_id,
            {'facts':facts,'fingerprint':R.fingerprint(facts),'status':'offered'})


def reprisal_authority(engine,actor,target,move_id,source):
    if source!=REPRISAL:return False
    row=getattr(engine,'_rider_reprisal',None)
    if row is None or row['owner'] is not actor or row['foe'] is not target or move_id!='struggle':
        raise ValueError('Cavalier requires its live actual mounted-hit reaction')
    import move_completion as COMPLETE
    COMPLETE.require_recipient_hit_return(engine,row['event_id'],row['mount'])
    if acquired(actor,REPRISAL) is None:raise ValueError('actual current Cavalier acquisition required')
    return True


def after_move(engine,completion,*,event_id=None):
    import move_completion as COMPLETE,root_resolution as R,action_points as AP,action_lifecycle as ACTION
    import turn as TURN,body_modes as BODY
    index=W.actor_index(engine)
    for row in completion.get('rider_reprisal',{}).values():
        if row['status']!='offered':continue
        facts=row['facts']
        if event_id is not None and facts['event_id']!=event_id:continue
        if row['fingerprint']!=R.fingerprint(facts):raise ValueError('actual Cavalier trigger changed')
        event_id=facts['event_id']
        if event_id not in completion.get('native_returns',{}):continue
        owner=index[facts['owner_id']];mount=index[facts['mount_id']];foe=index[facts['foe_id']]
        receipt=COMPLETE.require_recipient_hit_return(engine,event_id,mount)
        if (facts['completion_id']!=completion['id'] or facts['foe_id']!=receipt['attacker_id'] or
                facts['mount_id']!=receipt['recipient_id'] or facts['move_id']!=receipt['move']['id'] or
                facts['round']!=completion['round']):raise ValueError('Cavalier actual hit source changed')
        if (acquired(owner,REPRISAL) is None or owner.fainted or owner.dead or not owner.on_field
                or owner.captured or foe.fainted or not foe.on_field or foe.captured
                or not engine.adjacent(owner,foe) or AP.available(owner)<1 or not TURN.can_act(engine,owner)
                or not ACTION.status_permission(engine,owner,'free',new_action=True) or not BODY.permits(owner,'free')):
            row['status']='unavailable';continue
        answer=engine.rulings.decide({'type':'rider_reprisal','unit':REPRISAL,'actor':owner.name,
            'target':foe.name,'mount':mount.name,'move':facts['move_id'],'text':'Pay 1 AP for a Free Struggle Attack?'})
        options={}
        if type(answer) is dict:
            if set(answer)!={'use','options'} or type(answer['use']) is not bool or type(answer['options']) is not dict:
                raise ValueError('explicit Cavalier use and native Struggle options required')
            options=answer['options'];answer=answer['use']
            if set(options)-{'weapon_id','struggle_choice','appendage_id','origin_part','set_damage'}:
                raise ValueError('native Struggle options only')
        if answer is not None and type(answer) is not bool:raise ValueError('explicit Cavalier use or decline required')
        row['status']='declined' if answer is not True else 'used'
        if answer is not True:continue
        AP.charge(owner,1)
        if hasattr(engine,'_rider_reprisal'):raise ValueError('nested Cavalier needs its own completed trigger')
        engine._rider_reprisal={'owner':owner,'foe':foe,'mount':mount,'event_id':event_id}
        try:
            with ACTION.move_grant(engine,owner,foe,'struggle',source=REPRISAL,kind='free') as grant:
                engine.use_move(owner,foe,'struggle',count_use=False,free_action=True,_action_grant=grant,**options)
        except __import__('passive_events').PassiveEventPending as pending:
            child=engine._passive_events[pending.event_id]
            child_completion=engine._move_completions[child['completion_id']]
            if child_completion['actor'] is not owner or child_completion['move_id']!='struggle':raise
            row['counter_wait']={'event_id':pending.event_id,'completion_id':child_completion['id']}
            raise
        finally:del engine._rider_reprisal


def _lean_resist(engine,event):
    import damage_reactions as R,combat_damage as D
    formula=event['damage_formula'];mult=formula['multiplier']
    if event.get('mettle_selected'):mult=R.resistance_multiplier(engine,mult,event=event)
    mult=R.resistance_multiplier(engine,mult,event=event)
    if mult is None:raise ValueError('native resistance-step multiplier required')
    formula['multiplier']=mult;event['context']['multiplier']=mult
    event['effective_type_multiplier']=mult
    return D.scale(after_defense=formula['after_defense'],type_multiplier=mult,
        other_multiplier=formula['other_multiplier'],adjustment=formula['adjustment'])


def prepare_lean(engine,event,damage,context,precision_event,precision_facts):
    """Rendezvous actual group hits; never presume the other body was hit."""
    import move_activation as ACTIVATION,substitute as SUBSTITUTE
    import action_lifecycle as ACTION,frequency as F
    attacker=event['attacker'];target=event['target'];move=event['move']
    current=getattr(engine,'_rider_lean_pair',None)
    if current is not None:
        if current['phase']!='seeking' or target.entity_id!=current['partner_id'] or attacker is not current['event']['attacker']:
            return False,damage
        owner=W.actor_index(engine)[current['owner_id']]
        pair=MOUNT.ride_pair(engine,current['event']['target'],target)
        if (_positive_damage(engine,event,damage) and _positive_damage(engine,current['event'],current['damage']) and pair is not None and pair[0] is owner
                and acquired(owner,LEAN) is not None and _free_ready(engine,owner,LEAN)):
            answer=engine.rulings.decide({'type':'rider_lean_in','unit':LEAN,'actor':owner.name,
                'attacker':attacker.name,'move':move['id'],'text':'Use Lean In on these two actual damaging hits?',
                'targets':[current['event']['target'].name,target.name]})
            if answer is not None and type(answer) is not bool:raise ValueError('explicit Lean In use or decline required')
            if answer is True:
                ACTION.triggered_free_action(engine,owner,LEAN)
                F.consume_activation(owner,LEAN,{'kind':'scene','uses':2},engine=engine,action_actor=owner)
                current['damage']=_lean_resist(engine,current['event']);damage=_lean_resist(engine,event)
                current['selected']=True
        current['partner_context']=context
        return False,damage
    if (not _positive_damage(engine,event,damage) or context is None or not any(k in move.get('range','') for k in ('파열','폭발','원뿔','직선'))
            or SUBSTITUTE.live(target)):
        return False,damage
    scope=ACTIVATION.current_scope(engine,attacker,target,move['id'])
    resumed=getattr(engine,'_rider_resuming_partner',None)
    if resumed is not None and resumed['first_id']==event['passive_event']:
        native=engine._passive_events[resumed['first_id']]
        source=native['rider_pair_source']
        scope=next(s for s in engine._move_activation_scopes if s['completion_id']==source['completion_id'])
        engine._rider_lean_pair={'event':event,'damage':damage,'context':context,
            'precision_event':precision_event,'precision_facts':precision_facts,'scope':scope,
            'owner_id':source['owner_id'],'partner_id':source['partner_id'],'phase':'prepared',
            'batch':False,'selected':False,'applied':False}
        return True,damage
    if scope is None or 'prepaid_pass' in scope:return False,damage
    for owner,mount in MOUNT.ride_pairs(engine,target):
        partner=mount if target is owner else owner
        if (partner not in scope['targets'][scope['index']:] or acquired(owner,LEAN) is None
                or not _free_ready(engine,owner,LEAN) or SUBSTITUTE.live(partner)):
            continue
        engine._rider_lean_pair={'event':event,'damage':damage,'context':context,
            'precision_event':precision_event,'precision_facts':precision_facts,'scope':scope,
            'owner_id':owner.entity_id,'partner_id':partner.entity_id,'phase':'prepared',
            'batch':False,'selected':False,'applied':False}
        source={'owner_id':owner.entity_id,'partner_id':partner.entity_id,'acquisition':acquired(owner,LEAN)['request_id'],
                'completion_id':scope['completion_id']}
        source['fingerprint']=__import__('root_resolution').fingerprint(source)
        engine._passive_events[event['passive_event']]['rider_pair_source']=source
        return True,damage
    return False,damage


def _finish_lean_first(engine,row):
    import damage_reactions as R,precise_actions as P,passive_events as EVENTS
    event=row['event'];damage=R.finalize_choice(engine,event,row['damage'])
    P.damage_hit(engine,event['attacker'],event['target'],event['move'],row['precision_event'],row['precision_facts'],damage)
    EVENTS.note_damage_request(engine,event['passive_event'],damage)
    row['damage']=damage
    return damage


def apply_lean_pair(engine,event,damage,context,before):
    """Same native recipient group, two calculated hits, then both HP leaves.

    Like Deadly Gambit's existing rendezvous, an actual nested native recipient
    supplies the second hit. A miss/shield has no second damage to pair.
    """
    import action_lifecycle as ACTION,heavy_injury_adapter as H,combat_damage as D
    row=getattr(engine,'_rider_lean_pair',None)
    if row is None:return None,damage
    if event is row['event']:
        row['before']=before;row['phase']='seeking';scope=row['scope']
        partner=W.actor_index(engine)[row['partner_id']]
        try:
            resumed=getattr(engine,'_rider_resuming_partner',None)
            if resumed is not None:
                dealt=__import__('passive_events')._deliver_accuracy(engine,resumed['event_id'])
                row['completed_epoch']=engine._heavy_activation_sequence
                scope.setdefault('rider_paired_returns',{})[partner.entity_id]=dealt
                scope['total']+=dealt
            while scope['index']<=scope['targets'].index(partner):
                if event['attacker'].fainted or event['attacker'].dead:break
                target=scope['targets'][scope['index']]
                with ACTION.move_grant(engine,event['attacker'],target,event['move']['id'],source='same_move_activation') as grant:
                    dealt=engine.use_move(event['attacker'],target,event['move']['id'],count_use=False,
                        _activation=scope['activation'],_shared_accuracy=scope['accuracy'],_action_grant=grant,**scope['options'])
                scope.setdefault('rider_paired_returns',{})[target.entity_id]=dealt
                scope['total']+=dealt
                row['completed_epoch']=engine._heavy_activation_sequence
            if row['applied']:return row['receipt'],row['damage']
            return None,_finish_lean_first(engine,row)
        except __import__('passive_events').PassiveEventPending as pending:
            native=engine._passive_events[pending.event_id]
            if not native.get('continuation'):raise
            if native.get('completion_id')!=scope['completion_id'] and (not row['applied'] or
                    counter_parent(engine,native,scope['completion_id']) is None):raise
            completion=engine._move_completions[scope['completion_id']]
            completion['rider_pair_wait']={'first_id':event['passive_event'],'pending_id':pending.event_id,
                'phase':'after_damage' if row['applied'] else 'before_damage'}
            if not row['applied']:raise
            row['completed_epoch']=engine._heavy_activation_sequence
            engine._passive_pending=None
            return row['receipt'],row['damage']
        finally:
            row['phase']='returned'
    if (row['phase']!='seeking' or event['target'].entity_id!=row['partner_id']
            or row.get('partner_context') is not context):return None,damage
    first=row['event'];first_damage=_finish_lean_first(engine,row)
    row['batch']=True
    try:
        first_result=H.apply_attack_damage(engine,first['attacker'],first['target'],first_damage,first['move'],
            producer=H.Producer.RESOLVED_HIT,remainder='paired Rider hit native continuations remain',
            native_context=row['context'],actual_damage_type=first.get('actual_damage_type'))
        row['receipt']=D.application(requested=first_damage,before=row['before'],after=D.observe(first['target']),
            source=first['move']['id'],damage_class=first['move']['class'])
        result=H.apply_attack_damage(engine,event['attacker'],event['target'],damage,event['move'],
            producer=H.Producer.RESOLVED_HIT,remainder='paired Rider hit native continuations remain',
            native_context=context,actual_damage_type=event.get('actual_damage_type'))
        receipt=D.application(requested=damage,before=before,after=D.observe(event['target']),
            source=event['move']['id'],damage_class=event['move']['class'])
        if isinstance(first_result,dict) and first_result.get('source')==__import__('channeler').PAIN:row['receipt']['channeler_pain']=first_result
        if isinstance(result,dict) and result.get('source')==__import__('channeler').PAIN:receipt['channeler_pain']=result
        row['applied']=True
    finally:row['batch']=False
    for actor in (first['target'],event['target']):engine.check_fainted(actor)
    return receipt,damage


def paired_receipt_current(engine,token):
    row=getattr(engine,'_rider_lean_pair',None)
    if not row or row['context'] is not token:return False
    if row.get('completed_epoch')==engine._heavy_activation_sequence:return True
    if not row['batch']:return False
    other=row.get('partner_context')
    if other is None or other is token:return False
    import heavy_injury_adapter as H
    return H.validate_native_receipt(engine,other,row['event']['attacker'],
        W.actor_index(engine)[row['partner_id']],row['event']['move']) is not None


def defer_faint(engine,actor):
    row=getattr(engine,'_rider_lean_pair',None)
    return bool(row and row['batch'] and (actor is row['event']['target'] or actor.entity_id==row['partner_id']))


def paired_return(engine,activation,target):
    scope=next((s for s in getattr(engine,'_move_activation_scopes',()) if s['activation'] is activation),None)
    if scope is None:return None
    return scope.get('rider_paired_returns',{}).pop(target.entity_id,None)


def pair_checkpoint(engine,first_id,pending_id):
    event=engine._passive_events[first_id]
    row=engine._move_completions[event['completion_id']].get('rider_pair_wait')
    return bool(row and row=={'first_id':first_id,'pending_id':pending_id,'phase':'before_damage'})


def counter_parent(engine,pending,completion_id):
    completion=engine._move_completions[completion_id]
    for row in completion.get('rider_reprisal',{}).values():
        wait=row.get('counter_wait')
        if wait and wait['event_id']==pending['id'] and wait['completion_id']==pending['completion_id']:
            event=engine._passive_events[row['facts']['event_id']]
            __import__('move_completion').require_recipient_hit_return(engine,event['id'],event['target'])
            return event
    return None


def resume_counter(engine,event,result):
    import move_activation as ACT,action_lifecycle as ACTION
    child=engine._move_completions[event['completion_id']]
    if child['phase']!='complete':return result
    for completion in engine._move_completions.values():
        for row in completion.get('rider_reprisal',{}).values():
            wait=row.get('counter_wait')
            if not wait or wait['completion_id']!=child['id']:continue
            parent=engine._passive_events[row['facts']['event_id']]
            __import__('move_completion').require_recipient_hit_return(engine,parent['id'],parent['target'])
            row.pop('counter_wait')
            with ACTION.resolution(engine,completion['actor'],completion['move_id'],kind='move',_move_completion=completion['id']):
                flush_pair_wait(engine,parent['id'],completion['results'][parent['target'].entity_id]['dealt'])
                result=ACT.resume_after_event(engine,parent,completion['results'][parent['target'].entity_id]['dealt'])
    return result


def pair_wait_index(engine,completion,event,scope):
    wait=completion.get('rider_pair_wait')
    if not wait or wait['phase']!='after_damage' or wait['first_id']!=event['id']:
        source=event.get('rider_pair_source')
        if not source:return False
        target=scope['targets'][scope['index']-1]
        actual=completion['results'].get(target.entity_id)
        returned=[r for r in completion.get('native_returns',{}).values() if r['facts']['recipient_id']==target.entity_id]
        return bool(source['partner_id']==target.entity_id and actual and returned and
            scope.get('rider_paired_returns',{}).get(target.entity_id)==actual['dealt'])
    second=engine._passive_events.get(wait['pending_id'])
    if second and second['completion_id']!=completion['id']:second=counter_parent(engine,second,completion['id'])
    return bool(second and second['completion_id']==completion['id'] and
        (second.get('continuation',{}).get('kind')=='recipient_return' or second['id'] in completion.get('native_returns',{})) and
        scope['targets'][scope['index']-1] is second['target'])


def flush_pair_wait(engine,event_id,dealt):
    import move_activation as ACT,passive_events as P
    event=engine._passive_events[event_id];completion=engine._move_completions[event['completion_id']]
    wait=completion.get('rider_pair_wait')
    if not wait or wait['phase']!='after_damage' or wait['first_id']!=event_id:return
    second=engine._passive_events[wait['pending_id']]
    pending=second
    if second['completion_id']!=completion['id']:second=counter_parent(engine,second,completion['id'])
    if second is None or (second.get('continuation',{}).get('kind')!='recipient_return' and
            second['id'] not in completion.get('native_returns',{})):raise ValueError('actual paired recipient return required')
    saved=completion.get('activation_continuation')
    scopes=[saved['scope']] if saved else [s for s in getattr(engine,'_move_activation_scopes',()) if s.get('completion_id')==completion['id']]
    if len(scopes)!=1:raise ValueError('actual paired native group required')
    scope=scopes[0];scope['total']+=dealt
    if saved:
        saved['event_id']=second['id'];saved['fingerprint']=__import__('root_resolution').fingerprint(ACT._continuation_facts(scope,second['id']))
    completion.pop('rider_pair_wait')
    engine._passive_pending=pending['id']
    raise P.PassiveEventPending(pending['id'])


def resume_pair_wait(engine,event):
    import move_activation as ACT,passive_events as P,root_resolution as R
    completion=engine._move_completions[event['completion_id']]
    wait=completion.get('rider_pair_wait');saved=completion.get('activation_continuation')
    if not wait or wait['phase']!='before_damage' or wait['pending_id']!=event['id']:return None
    if not saved or saved['event_id']!=event['id']:raise ValueError('actual paid paired group continuation required')
    scope=saved['scope'];first=engine._passive_events[wait['first_id']]
    if (first.get('phase')!='accuracy_boundary' or not first.get('continuation') or
            event.get('phase')!='accuracy_boundary' or not event.get('continuation') or
            saved['fingerprint']!=R.fingerprint(ACT._continuation_facts(scope,event['id'])) or
            scope['profile']!=ACT._profile(engine) or scope['lifetime'][1:]!=ACT._lifetime(engine)[1:]):
        raise ValueError('actual paired accuracy continuation changed')
    previous=getattr(engine,'_move_activation_scopes',None)
    scope['lifetime']=ACT._lifetime(engine);engine._move_activation_scopes=[scope]
    engine._rider_resuming_partner={'event_id':event['id'],'first_id':first['id']}
    try:
        completion.pop('rider_pair_wait')
        result=P._deliver_accuracy(engine,first['id'])
        saved['event_id']=first['id'];saved['fingerprint']=R.fingerprint(ACT._continuation_facts(scope,first['id']))
        return {'result':ACT.resume_after_event(engine,first,result)}
    except P.PassiveEventPending as pending:
        ACT.suspend(engine,scope,pending)
        raise
    finally:
        vars(engine).pop('_rider_resuming_partner',None)
        if previous is None:vars(engine).pop('_move_activation_scopes',None)
        else:engine._move_activation_scopes=previous


def validate_native(engine,index):
    import coordinator as OBS,passive_events as P
    for event in engine._passive_events.values():
        row=event.get('rider_damage_selection')
        if row is not None and (row['sha256']!=OBS._damage_seal(row) or
                row['event_id']!=event['id'] or row['actor_id']!=event['actor'].entity_id or
                row['target_id']!=event['target'].entity_id or row['move_id']!=event['move_id'] or
                row['event']['attacker'] is not event['actor'] or row['event']['target'] is not event['target']):
            raise ValueError('actual Rider selected damage observation changed')
        source=event.get('rider_pair_source')
        if source is not None:
            facts={k:v for k,v in source.items() if k!='fingerprint'}
            completion=engine._move_completions[event['completion_id']]
            if (source['fingerprint']!=__import__('root_resolution').fingerprint(facts) or
                    source['completion_id']!=completion['id'] or source['owner_id'] not in index or
                    source['partner_id'] not in {t.entity_id for t in completion['targets']} or
                    not any(r['request_id']==source['acquisition'] for r in records(index[source['owner_id']],LEAN))):
                raise ValueError('actual Rider pair source observation changed')
    for completion in getattr(engine,'_move_completions',{}).values():
        wait=completion.get('rider_pair_wait')
        if wait is not None:
            if set(wait)!={'first_id','pending_id','phase'} or wait['phase'] not in ('before_damage','after_damage'):
                raise ValueError('actual paired native wait required')
            first=engine._passive_events.get(wait['first_id']);pending=engine._passive_events.get(wait['pending_id'])
            if (first is None or pending is None or first['completion_id']!=completion['id'] or
                    not first.get('rider_damage_selection') or not first.get('rider_pair_source') or
                    not pending.get('continuation')):
                raise ValueError('paired wait lost an actual native producer')
            second=pending if pending['completion_id']==completion['id'] else counter_parent(engine,pending,completion['id'])
            if second is None or first['target'] is second['target'] or first['actor'] is not second['actor']:
                raise ValueError('paired wait lost its actual second recipient')
            if wait['phase']=='before_damage' and (first['phase']!='accuracy_boundary' or
                    second['phase']!='accuracy_boundary' or not first.get('continuation')):
                raise ValueError('paired pre-damage native checkpoint required')
            if wait['phase']=='after_damage' and not any(r['stage']=='hp_loss' for r in P.observations(engine,second['id'])):
                raise ValueError('paired post-damage native observation required')
        for row in completion.get('rider_reprisal',{}).values():
            facts=row['facts'];event=engine._passive_events.get(facts['event_id'])
            if (row['fingerprint']!=__import__('root_resolution').fingerprint(facts) or event is None or
                    facts['completion_id']!=completion['id'] or event['completion_id']!=completion['id'] or
                    facts['foe_id']!=event['actor'].entity_id or facts['mount_id']!=event['target'].entity_id or
                    facts['owner_id'] not in index or facts['move_id']!=event['move_id'] or facts['round']!=event['round'] or
                    not any(r['request_id']==facts['acquisition'] for r in records(index[facts['owner_id']],REPRISAL))):
                raise ValueError('actual Cavalier hit observation changed')
            child=row.get('counter_wait')
            if child is not None:
                native=engine._passive_events.get(child['event_id']);result=engine._move_completions.get(child['completion_id'])
                if (row['status']!='used' or native is None or result is None or native['completion_id']!=result['id'] or
                        result['actor'] is not index[facts['owner_id']] or result['move_id']!='struggle' or
                        result['targets']!=[index[facts['foe_id']]]):raise ValueError('actual paid Cavalier Struggle continuation required')
