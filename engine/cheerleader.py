"""Cheerleader's source-owned instances and actual native trigger consumers."""
from copy import deepcopy
from contextvars import ContextVar
import acquired_features as A
import common_checks as C
import effect_instances as E
import moment_of_action as M
import trainer_feature_acquisition as TFA

CLASS=M.CLASS
BRIGADE='feat/응원-단체'
SUPPORT='feat/영감을-주는-지원'
GO_FIGHT_WIN='feat/응원-문구'
KIND='cheerleader'
KEY='cheerleader_instances'
USES='cheerleader_uses'
CONDITIONS=('Cheered','Excited','Motivated')
_TRANSACTION=ContextVar('cheerleader_native_transaction',default=False)


def acquired(actor,feature=CLASS):
    rows=M.receipts(actor,feature,active=True)
    if not A.owned_rule_count(actor,feature):return None
    TFA.validate_actor(actor)
    if len(rows)!=1 or A.owned_rule_count(actor,feature)!=1:
        raise ValueError('Cheerleader requires its actual acquisition source')
    return rows[0]


def acquisition_snapshot(actor,feature):
    import skill_modifiers as SKILLS
    parent=M.FEATURE if feature==GO_FIGHT_WIN else CLASS if feature==BRIGADE else BRIGADE
    receipt=acquired(actor,parent)
    if receipt is None:raise ValueError('actual acquired Cheerleader prerequisite required')
    return {'parent_request':receipt['request_id'],'charm':SKILLS.rank(actor.r,actor,'매력')[2] if feature!=BRIGADE else 0}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    parent=M.FEATURE if feature==GO_FIGHT_WIN else CLASS if feature==BRIGADE else BRIGADE
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!={'parent_request','charm'}:
        raise ValueError('exact Cheerleader child acquisition observations required')
    C.integer(snapshot['charm'],'acquisition Charm rank',0)
    if len([row for row in M.receipts(actor,parent) if row['request_id']==snapshot['parent_request']])!=1:
        raise ValueError('actual historical Cheerleader parent receipt required')
    if feature==BRIGADE and snapshot['charm']!=0:raise ValueError('Cheer Brigade has no separate Charm prerequisite')
    return Q.require(feature,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual trainer required'),
        Q.check('charm','prerequisite',feature==BRIGADE or snapshot['charm']>=(5 if feature==GO_FIGHT_WIN else 4),'Expert Charm required' if feature==GO_FIGHT_WIN else 'Adept Charm required')])


def live(actor,condition=None):
    rows=actor.spec.get(KEY,[])
    if type(rows) is not list:raise ValueError('Cheerleader instances must be a list')
    return [row for row in rows if condition is None or row.get('effect',{}).get('condition')==condition]


def history(actor):
    return [row for row in actor.spec.get('effect_instance_history',[]) if row.get(E.KEY,{}).get('kind')==KIND]


def _uses(actor):
    rows=actor.spec.get(USES,[])
    if type(rows) is not list:raise ValueError('Cheerleader producer history must be a list')
    return rows


def _seal(row):return TFA._digest('cheerleader/producer/v1',{key:value for key,value in row.items() if key!='integrity'})


def _allies(actor,targets):
    if any(target.kind not in ('trainer','pokemon') for target in targets):raise ValueError('actual allied Trainer or Pokemon required')
    # Existing native Orders ownership and support actor-side observations establish allies.
    return [target for target in targets if target is not actor and actor.side is not None and target.side==actor.side]


def issue(engine,actor,targets,origin):
    """Called at a successful native producer boundary, once per activation."""
    receipt=acquired(actor)
    if receipt is None:return None
    targets=list(dict.fromkeys(targets))
    if not targets:return None
    import state_grants as G,turn as TURN,action_points as AP
    def apply(e,owner,*recipients):
        choice=e.rulings.decide({'type':'cheerleader','unit':CLASS,'actor':owner.name,
            'text':'Choose one Cheerleader condition, or decline.','targets':[target.entity_id for target in recipients],
            'conditions':list(CONDITIONS),'trigger':deepcopy(origin)})
        if choice is None or choice is False:return None
        if type(choice) is not str or choice not in CONDITIONS:raise ValueError('choose exactly one Cheerleader condition')
        if acquired(owner) is None:raise ValueError('current acquired Cheerleader required')
        cost=int(len(recipients)>=2)
        if AP.available(owner)<cost:raise ValueError('Cheerleader needs one AP for multiple allies')
        import action_lifecycle as ACTION,body_modes as BODY
        if not BODY.permits(owner,'free'):raise ValueError('actual triggered Free action body permission required')
        ACTION.triggered_free_action(e,owner,CLASS)
        if cost:owner.ap_account.charge(cost,mode='spend')
        use_id='cheerleader:'+owner.entity_id+':'+str(len(_uses(owner))+1)
        row={'id':use_id,'issuer_id':owner.entity_id,'acquisition_request_id':receipt['request_id'],
             'source':deepcopy(receipt['source']),'at':e.elapsed_seconds,'round':e.round_no,
             'condition':choice,'cost':cost,'origin':deepcopy(origin),'targets':{}}
        for target in recipients:
            effect=E.create(e,target,kind=KIND,source=CLASS,payload={'kind':KIND,'condition':choice},
                capacity={'bucket':'independent_instances','source':CLASS},
                lifetime={'boundary':'until_consumed'},applied_by=owner)
            effect['origin']={'issuer_id':owner.entity_id,'use_id':use_id}
            target.spec.setdefault(KEY,[]).append(effect)
            row['targets'][target.entity_id]=effect['id']
        row['integrity']=_seal(row);owner.spec.setdefault(USES,[]).append(row)
        e.time_actors([owner,*recipients])
        return deepcopy(row)
    return G.transition(engine,actor,apply,participants=targets,include_rulings=True)


def after_moment(engine,actor,targets,row):
    if __import__('commander').scope(engine,actor) is not None:return None
    return issue(engine,actor,targets,{'kind':'moment_of_action','source':M.FEATURE,'use_id':row['id']})


def after_training(engine,actor,target,result):
    if target is actor:return None  # Training permits self Orders; the user is not an ally.
    if actor.side and target.side and actor.side!=target.side:return None
    if 'core_standard_payment' in result:
        return issue(engine,actor,[target],{'kind':'training_core_order','source':result['rule_id'],
            'payment_id':result['core_standard_payment']['id'],'target_id':target.entity_id})
    return issue(engine,actor,[target],{'kind':'training_order','source':result['rule_id'],
        'priority_id':result['priority_receipt']['id'],'grant_source':result['source'],'target_id':target.entity_id})


def complete_native_order(engine,actor,targets,source,*,origin=None):
    targets=list(dict.fromkeys(targets))
    serial=actor.custom_conditions.get('duelist_order_sequence',0)+1
    actor.custom_conditions['duelist_order_sequence']=serial
    origin=deepcopy(origin) if origin is not None else {'kind':'native','source':source,'sequence':serial}
    if origin.get('source')!=source:raise ValueError('native Order completion source changed')
    __import__('duelist').after_order(engine,actor,targets,origin)
    allies=_allies(actor,targets)
    if allies:issue(engine,actor,allies,origin)


def order_activation(source):
    """Join existing native one-target Orders to the one triggered producer."""
    from functools import wraps
    def decorate(fn):
        @wraps(fn)
        def run(engine,actor,target,*args,**kwargs):
            if __import__('commander').scope(engine,actor) is not None:return fn(engine,actor,target,*args,**kwargs)
            import duelist as DUELIST
            if acquired(actor) is None and not DUELIST.acquired(actor,DUELIST.DIRECTED):return fn(engine,actor,target,*args,**kwargs)
            import state_grants as G
            uid=source or args[0]
            def apply(e,owner,recipient):
                result=fn(e,owner,recipient,*args,**kwargs)
                successful=result is True or type(result) is dict or isinstance(result,(tuple,list)) and tuple(result)==(1,0)
                if successful:
                    serial=owner.custom_conditions.get('duelist_order_sequence',0)+1
                    owner.custom_conditions['duelist_order_sequence']=serial
                    DUELIST.after_order(e,owner,[recipient],{'kind':'native','source':uid,'sequence':serial})
                if successful and recipient is not owner:
                    # These native sources either require the owner's Pokemon or
                    # permit an arbitrary Pokemon. Only actual allies receive cheer.
                    owned=recipient.spec.get('trainer_id')==owner.entity_id or recipient.spec.get('trainer')==owner.name
                    opposing=owner.side and recipient.side and owner.side!=recipient.side
                    if not opposing and (owned or owner.side is not None and recipient.side==owner.side):
                        issue(e,owner,[recipient],{'kind':'native_order','source':uid,
                            'target_id':recipient.entity_id,'at':e.elapsed_seconds,
                            'native_module':fn.__module__})
                return result
            return G.transition(engine,actor,apply,participants=(target,),include_rulings=True)
        return run
    return decorate


def owned_friend_guard(engine,pokemon,feature):
    import world_entities as W,ability_transitions as ABILITIES
    if pokemon.kind!='pokemon' or not ABILITIES.active(pokemon,'ability/프렌드가드'):return None
    owner_id=W.identity_field(engine,pokemon,'owner_id')
    owner=W.actor_index(engine).get(owner_id)
    if owner is None or acquired(owner,feature) is None:return None
    if acquired(owner,BRIGADE) is None or acquired(owner) is None:raise ValueError('current acquired Cheerleader family required')
    return {'pokemon_id':pokemon.entity_id,'owner_id':owner.entity_id,'side':owner.side,
        'source':deepcopy(acquired(owner,feature)['source']),
        'acquisition_request_id':acquired(owner,feature)['request_id'],
        'friend_guard':'ability/프렌드가드','at':engine.elapsed_seconds}


def support_snapshot(engine,pokemon):return owned_friend_guard(engine,pokemon,SUPPORT)


def effect_targets(engine,tokens):
    """Use completed native receipts and each existing recipient resolver."""
    import effect_contracts as EC,blessing_effects as BLESS,coat_effects as COATS,world_entities as W
    affected=[];index=W.actor_index(engine);seen=set()
    def visit(token):
        if token in seen:return
        seen.add(token);row=engine._effect_dispatch_receipts[token]
        if row['status']=='condition_false':return
        if row['status']!='completed':raise ValueError('actual effects must complete before Inspirational Support')
        result=row.get('result')
        if isinstance(result,EC.BatchResult):
            for outcome in result.outcomes:
                if outcome.receipt is not None:visit(outcome.receipt)
            return
        actor,target,effect,source=row['actor'],row['target'],row['effect'],row['source_id']
        if type(result) is dict and isinstance(result.get('recipients'),list):
            affected.extend(index[uid] for uid in result['recipients']);return
        if BLESS.definition(engine.r,source) is not None:
            records=[r for r in BLESS.live(actor) if r['source']==source]
            if not records:raise ValueError('actual newly issued team Blessing required')
            team=BLESS.side(records[-1])
            affected.extend(a for a in index.values() if a.side==team);return
        coat=COATS.definition(engine.r,source)
        if coat is not None and effect.get('type')=='apply_coat':
            affected.append(target if coat['payload']['kind']=='damage_coat' else actor);return
        if effect.get('target')=='all_targets':
            # The existing area adapter emits one actual leaf receipt per target.
            affected.append(target);return
        if effect.get('type') in ('weather','terrain','field'):
            affected.extend(a for a in index.values() if a.on_field);return
        affected.extend(EC.recipients(actor,target,effect))
    for token in tokens:visit(token)
    return list(dict.fromkeys(affected))


def support(engine,snapshot,targets,origin):
    if snapshot is None or not targets:return None
    import world_entities as W
    index=W.actor_index(engine);owner=index[snapshot['owner_id']]
    # Ally is relative to the Cheerleader. A Pokemon's self Coat may affect
    # that Trainer's ally; this does not make an actor its own ally.
    if snapshot['side'] is None or any(target.side!=snapshot['side'] for target in targets):return None
    recipients=[target for target in targets if target is not owner]
    if not recipients:return None
    origin={'kind':'inspirational_support','activation':deepcopy(origin),'support':deepcopy(snapshot),
            'affected_ids':[target.entity_id for target in targets]}
    return issue(engine,owner,recipients,origin)


def after_move(engine,row):
    if row.get('cheerleader_support_done') or row.get('cheerleader_support') is None:return
    if row['phase']!='complete':return
    row['cheerleader_support_done']=True
    if row['move'].get('class')!='변화':return
    targets=effect_targets(engine,row['effects'])
    return support(engine,row['cheerleader_support'],targets,
        {'kind':'move','completion_id':row['id'],'source':row['move_id']})


def batch_activation(engine,actor,source,result,*,snapshot=None,orders=False):
    import effect_contracts as EC
    if not isinstance(result,EC.BatchResult):return
    if orders:
        import duelist as DUELIST
        if acquired(actor) is None and not DUELIST.acquired(actor,DUELIST.DIRECTED):return
        from ruleset import source_unit
        unit=engine.r.selection.units.get(source)
        if unit is None or '지시' not in source_unit(unit)['tags']:return
    elif snapshot is None:return
    tokens=tuple(outcome.receipt for outcome in result.outcomes if outcome.receipt is not None)
    if not tokens:return
    root=engine._effect_dispatch_receipts[tokens[0]]
    if 'cheerleader_activation' in root:raise ValueError('one Cheerleader observation per actual activation')
    root['cheerleader_activation']={'actor':actor,'source':source,'roots':tokens,
        'snapshot':deepcopy(snapshot),'orders':orders,'done':False}
    refresh_batches(engine)


def refresh_batches(engine):
    import action_lifecycle as ACTION
    for row in list(getattr(engine,'_effect_dispatch_receipts',{}).values()):
        meta=row.get('cheerleader_activation')
        if not meta or meta['done']:continue
        members=ACTION._turn_end_members(engine,{'effects':meta['roots']})
        if ACTION.pending_resolution_effects(engine,{'effects':members}):continue
        targets=effect_targets(engine,members)
        meta['done']=True
        origin={'kind':'effect_batch','source':meta['source'],'root_occurrence':row['occurrence']}
        if meta['orders']:
            import duelist as DUELIST
            DUELIST.after_order(engine,meta['actor'],targets,origin)
            allies=_allies(meta['actor'],targets)
            if allies:issue(engine,meta['actor'],allies,origin)
        else:support(engine,meta['snapshot'],targets,origin)


def ability_action(fn):
    """Observe an existing manual Ability producer, never a caller's hit flag."""
    from functools import wraps
    @wraps(fn)
    def run(engine,actor,source,*args,**kwargs):
        snapshot=support_snapshot(engine,actor)
        if snapshot is None:return fn(engine,actor,source,*args,**kwargs)
        import state_grants as G,world_entities as W,effect_contracts as EC
        def apply(e,user):
            before=set(getattr(e,'_effect_dispatch_receipts',{}))
            prior={a.entity_id:a.spec.get(E.SEQUENCE,0) for a in W.actor_index(e).values()}
            index=W.actor_index(e)
            memo={id(c):index[uid] for uid,c in W.actor_index(engine).items()}
            memo.update(G._transition_token_anchors(engine))
            result=fn(e,user,source,*deepcopy(args,memo),**deepcopy(kwargs,memo))
            if result is None or result is False or isinstance(result,C.PendingDecision):return result
            if isinstance(result,EC.BatchResult) and result.pending:return result
            tokens=[key for key in getattr(e,'_effect_dispatch_receipts',{}) if key not in before]
            targets=effect_targets(e,tokens) if tokens else []
            if not targets:
                for target in index.values():
                    for effect,spent in E.records(target):
                        if spent or effect[E.KEY]['sequence']<=prior[target.entity_id] or effect[E.KEY].get('applied_by_actor_id')!=user.entity_id:continue
                        if effect[E.KEY]['kind']=='team_blessing':
                            import blessing_effects as BLESS
                            targets.extend(a for a in index.values() if a.side==BLESS.side(effect))
                        else:targets.append(target)
            if not targets and type(result) is dict:
                ids=result.get('recipients') or ([result['target_id']] if result.get('target_id') in index else [])
                targets.extend(index[uid] for uid in ids)
                if not targets and result.get('grant_source'):
                    targets.extend(a for a in index.values() if result['grant_source'] in a.spec.get(G.KEY,{}).get('sources',{}))
            if targets:
                import ability_transitions as ABILITIES
                support(e,snapshot,list(dict.fromkeys(targets)),{'kind':'manual_ability','source':ABILITIES.ability_id(e.r,source),
                    'producer':fn.__name__,'receipt_id':result.get('id',result.get('effect_id')) if type(result) is dict else None,
                    'effects':[e._effect_dispatch_receipts[token]['occurrence'] for token in tokens]})
            return result
        return G.transition(engine,actor,apply,include_rulings=True,include_grid=engine.grid is not None)
    return run


def native_action(fn):
    """Keep new choices atomic while preserving genuine native pending events."""
    from functools import wraps
    @wraps(fn)
    def run(engine,actor,*args,**kwargs):
        import state_grants as G,world_entities as W
        subjects=list(W.actor_index(engine).values())
        interested=(acquired(actor) if actor.kind=='trainer' else support_snapshot(engine,actor))
        if actor.kind=='pokemon':
            import gleeful_interference as GLEEFUL
            interested=interested or owned_friend_guard(engine,actor,GLEEFUL.FEATURE)
        interested=interested or any(live(subject,'Excited') for subject in subjects)
        import keep_fighting as KEEP
        interested=interested or any(subject.kind=='trainer' and A.owned_rule_count(subject,KEEP.FEATURE) for subject in subjects)
        import duelist as DUELIST
        interested=interested or any(DUELIST.interested(engine,subject) for subject in subjects)
        import enduring_resilience as RESILIENCE
        interested=interested or any(RESILIENCE.interested(subject) for subject in subjects)
        import roughneck as ROUGHNECK,endure as ENDURE
        interested=interested or any(ROUGHNECK.owns(subject,ROUGHNECK.CLASS) or ENDURE.known(engine,subject) for subject in subjects)
        interested=interested or any(__import__('sage').acquired(subject) for subject in subjects)
        if _TRANSACTION.get() or not interested:return fn(engine,actor,*args,**kwargs)
        pending=[]
        def apply(e,user):
            copied_args,copied_kwargs=G._stage_transition_payload(engine,e,(args,kwargs))
            token=_TRANSACTION.set(True)
            try:return fn(e,user,*copied_args,**copied_kwargs)
            except Exception as error:
                import passive_events as PASSIVE,heavy_injury_adapter as HEAVY
                if type(error) is PASSIVE.PassiveEventPending and e._passive_pending==error.event_id and error.event_id in e._passive_events:
                    pending.append((PASSIVE.PassiveEventPending,error.event_id));return None
                if type(error) is HEAVY.HeavyPending and e._heavy_pending==error.event_id and error.event_id in e._heavy_events:
                    pending.append((HEAVY.HeavyPending,error.event_id));return None
                raise
            finally:_TRANSACTION.reset(token)
        try:result=G.transition(engine,actor,apply,include_rulings=True,include_grid=engine.grid is not None)
        except __import__('roughneck').OverlapPending as pending:return pending.decision
        if pending:
            exception,event_id=pending[0];raise exception(event_id)
        return result
    return run


def choose(engine,actor,condition,**facts):
    rows=live(actor,condition)
    if not rows:return None
    for row in rows:validate_record(actor,row)
    choice=engine.rulings.decide({'type':'cheerleader_'+condition.lower(),'unit':CLASS,
        'actor':actor.name,'text':'Consume one '+condition+' instance for this actual event?',
        'instances':[row['id'] for row in rows],**facts})
    if choice is None or choice is False:return None
    if choice is True:return rows[0]
    if type(choice) is not str or sum(row['id']==choice for row in rows)!=1:
        raise ValueError('one actual '+condition+' instance required')
    return next(row for row in rows if row['id']==choice)


def consume(engine,actor,row,event):
    closed=E.archive(engine,actor,row,state='consumed',event=event)
    actor.spec[KEY].remove(row)
    return closed


def save_roll(engine,actor,condition,natural):
    row=choose(engine,actor,'Cheered',save_condition=condition)
    if row is None:return natural,None
    import duelist as DUELIST
    second=11 if DUELIST.choose_eleven(engine,actor,'saving_reroll') else engine.d20()
    second=__import__('oracle').replace_d20(engine,actor,second,'saving_reroll')
    C.integer(second,'Cheered second saving d20',1,20)
    event={'kind':'saving_check','condition':condition,'rolls':[natural,second],'natural':max(natural,second)}
    consume(engine,actor,row,event)
    return event['natural'],{'instance_id':row['id'],**event}


def damage_reduction(engine,actor,attacker,move,event):
    if event is None or move.get('class') not in ('물리','특수'):return 0
    row=choose(engine,actor,'Excited',attacker_id=attacker.entity_id,move_id=move['id'])
    if row is None:return 0
    event['cheerleader_excited']=row['id']
    return 5


def finish_damage(engine,event,receipt):
    uid=event.get('cheerleader_excited')
    if uid is None:return
    actor=event['target'];rows=[row for row in live(actor,'Excited') if row['id']==uid]
    if len(rows)!=1:raise ValueError('selected Excited instance changed during the actual hit')
    consume(engine,actor,rows[0],{'kind':'damaging_hit','attacker_id':event['attacker'].entity_id,
        'move_id':event['move']['id'],'reduction':5,'damage_receipt':deepcopy(receipt)})


def motivate(engine,actor,instance_id,stat):
    import state_grants as G,combat_stage_sources as STAGES,turn as TURN
    def apply(e,holder):
        rows=[row for row in live(holder,'Motivated') if row['id']==instance_id]
        if len(rows)!=1:raise ValueError('one actual Motivated instance required')
        if stat not in STAGES.STATS:raise ValueError('one ordinary combat stat required')
        state=STAGES.validate(holder)
        lo,hi=STAGES.limits(holder)
        baseline=max(lo,min(hi,STAGES.total(state,stat))) if state is not None else 0
        before=holder.stages[stat]
        if before>=baseline:raise ValueError('Motivated requires a combat stage below its actual baseline')
        if not TURN.spend(e,holder,'free','Motivated'):raise ValueError('Motivated requires its own Free action')
        e.change_stage(holder,stat,1)
        after=holder.stages[stat]
        consume(e,holder,rows[0],{'kind':'motivated_free','stat':stat,'before':before,'after':after,'requested_delta':1,'baseline':baseline})
        return {'instance_id':instance_id,'stat':stat,'before':before,'after':after,'baseline':baseline}
    return G.transition(engine,actor,apply)


def validate_record(actor,row,*,terminal=False):
    E.validate(row,actor=actor,terminal=terminal)
    meta=row[E.KEY];condition=row['effect'].get('condition')
    if (row['source'] not in (CLASS,GO_FIGHT_WIN) or row['effect']!={'kind':KIND,'condition':condition} or condition not in CONDITIONS
            or meta['kind']!=KIND or meta['capacity']!={'bucket':'independent_instances','source':row['source']}
            or meta['lifetime']!={'boundary':'until_consumed'}
            or (len(meta['ownership'])!=1 and row['source']!=GO_FIGHT_WIN)):
        raise ValueError('Cheerleader effect definition changed')
    if row['source']==GO_FIGHT_WIN and len(meta['ownership'])>1:
        import native_order_transfer as TRANSFER
        if TRANSFER.KEY not in row or TRANSFER.origin_id(row,actor)!=meta['origin_actor_id']:
            raise ValueError('fixed Order condition requires its actual transfer origin')
        if any(event['source'] not in TRANSFER.SOURCES for event in meta['ownership'][1:]):
            raise ValueError('only native Baton Pass/Tag In passes fixed Order conditions')
    origin=row.get('origin')
    if type(origin) is not dict or set(origin)!={'issuer_id','use_id'} or meta.get('applied_by_actor_id')!=origin['issuer_id']:
        raise ValueError('actual Cheerleader issuer and use required')
    for value in origin.values():E.text(value,'Cheerleader origin')
    if terminal:
        event=meta['end_event'];kind={'Cheered':'saving_check','Excited':'damaging_hit','Motivated':'motivated_free'}[condition]
        if meta['state']!='consumed' or event.get('kind')!=kind:raise ValueError('Cheerleader instances end only on their printed consumption')
        if condition=='Cheered':
            rolls=event.get('rolls')
            if type(rolls) is not list or len(rolls)!=2:raise ValueError('exactly two Cheered saving dice required')
            for die in rolls:C.integer(die,'Cheered saving d20',1,20)
            if event.get('natural')!=max(rolls):raise ValueError('Cheered must use the better Save')
        elif condition=='Excited':
            if event.get('reduction')!=5:raise ValueError('one Excited instance contributes exactly five DR')
            E.text(event.get('move_id'),'actual Excited attack');E.text(event.get('attacker_id'),'actual Excited attacker')
        elif event.get('stat') not in ('atk','def','spa','spd','spe') or event.get('requested_delta')!=1 or event['before']>=event.get('baseline',-7):
            raise ValueError('Motivated must request one stage below actual baseline')
        elif condition=='Motivated':
            for field in ('before','after','baseline'):C.integer(event.get(field),'actual Motivated '+field,-6,6)
    return True


def validate_world(engine,index):
    import keep_fighting as KEEP
    KEEP.validate_world(engine,index)
    import gleeful_interference as GLEEFUL
    GLEEFUL.validate_world(engine,index)
    import go_fight_win as GO
    linked=GO.validate_world(engine,index)
    for issuer in index.values():
        for serial,use in enumerate(_uses(issuer),1):
            fields={'id','issuer_id','acquisition_request_id','source','at','round','condition','cost','origin','targets','integrity'}
            if type(use) is not dict or set(use)!=fields or use['integrity']!=_seal(use):raise ValueError('Cheerleader producer evidence changed')
            if use['id']!='cheerleader:'+issuer.entity_id+':'+str(serial) or use['issuer_id']!=issuer.entity_id or use['source']!=TFA._static_source(issuer.r,CLASS):
                raise ValueError('Cheerleader source or issuer changed')
            if len([row for row in M.receipts(issuer,CLASS) if row['request_id']==use['acquisition_request_id']])!=1:raise ValueError('actual historical Cheerleader acquisition missing')
            C.integer(use['at'],'Cheerleader issue time',0,engine.elapsed_seconds);C.integer(use['round'],'Cheerleader issue round',0,engine.round_no)
            if type(use['targets']) is not dict or not use['targets'] or use['cost']!=int(len(use['targets'])>=2) or use['condition'] not in CONDITIONS:
                raise ValueError('Cheerleader selected condition, actual targets or AP count changed')
            validate_origin(engine,issuer,use)
            for target_id,effect_id in use['targets'].items():
                target=index.get(target_id)
                if target is None or target is issuer:raise ValueError('actual Cheerleader ally is missing')
                rows=[row for row in live(target)+history(target) if row['id']==effect_id]
                if len(rows)!=1:raise ValueError('Cheerleader issuance needs its actual target instance')
                row=rows[0]
                if row['source']!=CLASS or row['origin']!={'issuer_id':issuer.entity_id,'use_id':use['id']} or row['effect']['condition']!=use['condition'] or row['at']!=use['at']:
                    raise ValueError('Cheerleader producer and condition instance disagree')
                linked.add(effect_id)
    for target in index.values():
        for row in live(target)+history(target):
            if row['id'] not in linked:raise ValueError('Cheerleader instance lacks its actual producer')
    return True


def validate_origin(engine,issuer,use):
    origin=use['origin'];kind=origin.get('kind')
    if kind=='commander_order':
        import commander as COMMANDER
        rows=[row for row in issuer.spec.get(COMMANDER.ACTIVATIONS,[]) if row['id']==origin.get('activation_id')]
        if (len(rows)!=1 or rows[0]['phase']!='complete' or rows[0]['feature']!=origin.get('source')
                or rows[0]['at']!=use['at'] or set(use['targets'])!={r['target_id'] for r in rows[0]['orders']}):
            raise ValueError('Cheerleader requires the actual completed Commander Order activation')
    elif kind=='mobilize':
        import commander as COMMANDER
        n=origin.get('use_index');rows=COMMANDER.uses(issuer)
        if (type(n)is not int or not 1<=n<=len(rows) or origin.get('source')!=COMMANDER.MOBILIZE
                or set(use['targets'])!={rows[n-1]['target_id']} or rows[n-1]['at']!=use['at']):
            raise ValueError('Cheerleader requires actual completed Mobilize')
    elif kind=='general_order':
        import commander_orders as ORDERS
        row=ORDERS.find_use(issuer,origin.get('use_id'))
        if (row['phase']!='complete' or row['feature']!=origin.get('source') or row['at']!=use['at']
                or set(use['targets'])!={row['target_id']}):raise ValueError('Cheerleader requires actual completed general Order')
    elif kind=='duelist_order':
        import duelist as DUELIST
        rows=[row for row in issuer.spec.get(DUELIST.USES,[]) if row['id']==origin.get('use_id')]
        if len(rows)!=1 or rows[0]['source']!=origin.get('source') or set(use['targets'])!={rows[0]['pokemon_id']}:
            raise ValueError('Cheerleader requires the actual completed Duelist Order')
    elif kind=='go_fight_win':
        import go_fight_win as GO
        rows=[row for row in GO._uses(issuer) if row['id']==origin.get('use_id')]
        if origin.get('source')!=GO.FEATURE or len(rows)!=1 or set(rows[0]['targets'])!=set(use['targets']) or rows[0]['at']!=use['at']:
            raise ValueError('Cheerleader requires the actual completed Book Go Fight Win')
    elif kind=='conquerors_march':
        import conquerors_march as MARCH
        rows=[row for row in MARCH._uses(issuer) if row['id']==origin.get('use_id')]
        if (origin.get('source')!=MARCH.FEATURE or len(rows)!=1
                or set(use['targets'])!={rows[0]['intent']['target_id']} or rows[0]['at']!=use['at']):
            raise ValueError('Cheerleader requires the actual completed Conqueror Order')
    elif kind=='moment_of_action':
        rows=[row for row in M._uses(issuer) if row['id']==origin.get('use_id')]
        if origin.get('source')!=M.FEATURE or len(rows)!=1 or set(rows[0]['targets'])!=set(use['targets']) or rows[0]['at']!=use['at']:
            raise ValueError('Cheerleader requires the actual completed Moment of Action')
    elif kind=='training_core_order':
        import training_features as TRAINING
        payment=TRAINING.core_payment(issuer,origin.get('payment_id'))
        if (payment['feature']!=origin.get('source') or payment['target_id']!=origin.get('target_id')
                or payment['at']!=use['at'] or set(use['targets'])!={origin.get('target_id')}):
            raise ValueError('Cheerleader requires the actual completed Core Training Order')
    elif kind=='training_order':
        import priority_limited as P,training_features as TRAINING
        rows=[row for row in P.records(issuer) if row['id']==origin.get('priority_id')]
        ordinary=[record['result'] for record in issuer.spec.get('training_order_uses',[])
                  if record['integrity']==TFA._digest('training-order/use/v1',record['result'])
                  and record['result']['priority_receipt']['id']==origin.get('priority_id')
                  and record['result']['rule_id']==origin.get('source') and record['result']['target_id']==origin.get('target_id')
                  and record['result']['trainer_id']==issuer.entity_id and record['result']['source']==origin.get('grant_source')]
        reserved=(len(rows)==1 and rows[0]['source']==origin.get('source')
                  and rows[0]['subject_id']==origin.get('target_id'))
        if origin.get('source') not in TRAINING.RULES or not (reserved or len(ordinary)==1) or set(use['targets'])!={origin['target_id']}:
            raise ValueError('Cheerleader requires the actual completed Training Order')
    elif kind=='native_order':
        import class_passive_combat as CLASS_PASSIVE,combat_precision_features as PRECISION,directive_features as DIRECTIVES
        import stat_ace as STAT,chronicler as CHRONICLER,fashionista as FASHION
        sources={'class_passive_combat':CLASS_PASSIVE.STRATAGEMS,
                 'combat_precision_features':{PRECISION.PINPOINT},'directive_features':{DIRECTIVES.SOURCE},
                 'stat_ace':{STAT.STRATAGEM},'chronicler':{CHRONICLER.PROFILING},'fashionista':{FASHION.DRESS},
                 'type_ace':__import__('type_ace').STRATAGEMS|{__import__('type_ace').REFRESH}}
        if origin.get('source') not in sources.get(origin.get('native_module'),()) or set(use['targets'])!={origin.get('target_id')} or origin.get('at')!=use['at']:
            raise ValueError('actual known native Orders completion required')
    elif kind=='wilderness_guide':
        import survivalist_class as GUIDE
        rows=[row for row in issuer.spec.get(GUIDE.GUIDE_HISTORY,[]) if row['sequence']==origin.get('sequence')]
        if (origin.get('source')!=GUIDE.GUIDE or len(rows)!=1 or rows[0]['owner_id']!=issuer.entity_id
                or set(rows[0]['allies'])!=set(use['targets']) or rows[0]['seconds']!=use['at']):
            raise ValueError('Cheerleader requires the actual completed Wilderness Guide')
    elif kind=='inspirational_support':
        snapshot=origin.get('support',{});pokemon_id=snapshot.get('pokemon_id')
        import world_entities as W
        index=W.actor_index(engine)
        if snapshot.get('owner_id')!=issuer.entity_id or pokemon_id not in index or index[pokemon_id].kind!='pokemon' or snapshot.get('friend_guard')!='ability/프렌드가드':
            raise ValueError('Inspirational Support requires its actual owned Friend Guard Pokemon observation')
        if snapshot.get('source')!=TFA._static_source(issuer.r,SUPPORT) or len([r for r in M.receipts(issuer,SUPPORT) if r['request_id']==snapshot.get('acquisition_request_id')])!=1:
            raise ValueError('actual historical Inspirational Support acquisition required')
        if set(use['targets'])!=set(origin.get('affected_ids',[]))-{issuer.entity_id}:raise ValueError('Inspirational Support affected allies changed')
        activation=origin.get('activation',{})
        if activation.get('kind')=='move':
            import move_completion as COMPLETE
            row=getattr(engine,COMPLETE.KEY,{}).get(activation.get('completion_id'))
            if row is None or row['actor'].entity_id!=pokemon_id or row['phase']!='complete' or row['move_id']!=activation.get('source') or row['move'].get('class')!='변화':
                raise ValueError('actual completed Status Move required')
        elif activation.get('kind')=='effect_batch':
            rows=[r for r in getattr(engine,'_effect_dispatch_receipts',{}).values() if r['occurrence']==activation.get('root_occurrence')]
            if len(rows)!=1 or not rows[0].get('cheerleader_activation',{}).get('done') or rows[0]['actor'].entity_id!=pokemon_id:
                raise ValueError('actual completed triggered Ability batch required')
        elif activation.get('kind')=='reactive_ability':
            import move_completion as COMPLETE,reactive_ability_events as REACTIVE
            row=getattr(engine,COMPLETE.KEY,{}).get(activation.get('completion_id'))
            applications=[] if row is None else row.get(REACTIVE.TAG,{}).get('applications',[])
            if not any(a['id']==activation.get('application_id') and a['source']==activation.get('source') for a in applications):
                raise ValueError('actual reactive Ability application required')
        elif activation.get('kind')=='passive_ability':
            event=getattr(engine,'_passive_events',{}).get(activation.get('event_id'))
            if event is None or event['actor'].entity_id!=pokemon_id or event.get('outcomes',{}).get(activation.get('source'),{}).get('status')!='applied':
                raise ValueError('actual committed passive Ability consequence required')
        elif activation.get('kind')=='choice_ability':
            import ability_interrupt_choices as INTERRUPT,ability_reaction_choices as REACTION,move_completion as COMPLETE
            event=getattr(engine,'_passive_events',{}).get(activation.get('event_id'))
            if event is None:raise ValueError('actual native Ability choice event required')
            if activation.get('source')==INTERRUPT.SOURCE:
                attempts=event.get(INTERRUPT.KEY,{}).get('attempts',[])
                if not any(a['owner_id']==pokemon_id and a.get('outcome')=='activated' for a in attempts) or origin['affected_ids']!=[pokemon_id]:
                    raise ValueError('actual activated Tera Shell self recipient required')
            elif activation.get('source')==REACTION.SOURCE:
                completion=getattr(engine,COMPLETE.KEY,{})[event['completion_id']]
                offer=completion.get(REACTION.KEY,{}).get('offers',{}).get(event['id'],{})
                if offer.get('status')!='activated' or offer['attempt']['owner_id']!=pokemon_id:
                    raise ValueError('actual activated Perish Body Reaction required')
                ids=[entry['holder_id'] for entry in offer['attempt']['activation']['conditions'] if entry['record_id'] is not None]
                if origin['affected_ids']!=ids:raise ValueError('actual Perish Body recipients changed')
            else:raise ValueError('known native choice Ability source required')
        elif activation.get('kind')=='manual_ability':
            if activation.get('producer') not in ('activate_ability','activate_ability_state','activate_form_ability') or not activation.get('source','').startswith('ability/'):
                raise ValueError('known native manual Ability completion required')
        else:raise ValueError('actual native Ability or Status Move activation required')
    elif kind=='effect_batch':
        rows=[row for row in getattr(engine,'_effect_dispatch_receipts',{}).values() if row['occurrence']==origin.get('root_occurrence')]
        if len(rows)!=1 or not rows[0].get('cheerleader_activation',{}).get('done') or rows[0]['cheerleader_activation']['source']!=origin.get('source'):
            raise ValueError('actual completed Orders effect batch required')
    else:raise ValueError('unknown native Cheerleader trigger')
