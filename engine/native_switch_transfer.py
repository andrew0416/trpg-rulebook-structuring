"""Actual native replacement and the two selected Juggler switch Features.

Transfer adapters move existing source-owned effects. Unknown Order families
hold before payment; a registry entry is never a substitute for a native grant.
"""
from copy import deepcopy
import common_checks as C
import root_resolution as ROOT
import world_entities as W

BATON='move/배턴터치'
ROUND_TRIP='feat/왕복-여행'
TAG_IN='feat/태그-인'
CLASS='class/저글러'
CHOICES='native_switch_choices'
RECALLS='native_recall_history'
TAG='pending_tag_in'
TAG_CHOICE='native_tag_in_selection'
USES='native_switch_feature_uses'
ROUND_EFFECT={'type':'switch_out','target':'that pokemon','ignore_trapped':True,
              'note':'즉시 다른 포켓몬과 교대'}
BATON_EFFECT={'type':'switch_out','pass':['stages','coats','orders'],'ignore_trapped':True}


def identity(name):
    return next((uid for uid,names in ((ROUND_TRIP,('왕복 여행','Round Trip')),
        (TAG_IN,('태그 인','Tag In'))) if name in (uid,*names)),None)


def selected(engine,source):
    from source_context import verified_source
    if source not in (BATON,ROUND_TRIP,TAG_IN) or engine.r._selected_rule(source)!=source:
        raise ValueError('exact reviewed native switch source required')
    ref=({'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'}
         if source==BATON else {'file':'input/ch04-trainer-classes.md','sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'})
    verified_source(engine.r,ref,label='native switch/transfer')


def _owner(engine,pokemon):
    import party_actions as PARTY
    owner=PARTY.owner(engine,pokemon)
    if owner is None:raise ValueError('actual Pokemon Trainer required')
    return owner


def pair(engine,outgoing,incoming,*,recalled=False):
    import pokemon_party as PARTY
    W.require_actors(engine,outgoing,incoming)
    owner=_owner(engine,outgoing)
    if (outgoing is incoming or outgoing.kind!='pokemon' or incoming.kind!='pokemon'
            or incoming.spec.get('trainer_id')!=owner.entity_id or outgoing.side!=incoming.side):
        raise ValueError('distinct actual Pokemon of the same Trainer required')
    PARTY.require_participation(engine,outgoing);PARTY.require_participation(engine,incoming)
    if outgoing.captured or outgoing.dead or (not recalled and (not outgoing.on_field or outgoing.fainted)):
        raise ValueError('actual eligible outgoing Pokemon required')
    if incoming.on_field or incoming.fainted or incoming.dead or incoming.captured:
        raise ValueError('actual available off-field replacement required')
    return owner


def select(engine,outgoing,incoming,*,source=BATON,reason):
    selected(engine,source);pair(engine,outgoing,incoming)
    if source==BATON:
        import coat_effects as COATS
        return COATS.select_transfer(engine,outgoing,incoming,reason=reason)
    if source!=ROUND_TRIP:raise ValueError('Tag In chooses the actual next send-out')
    if type(reason)is not str or not reason.strip():raise ValueError('actual replacement choice reason required')
    choice={'source':source,'outgoing_id':outgoing.entity_id,'incoming_id':incoming.entity_id,
            'at':engine.elapsed_seconds,'reason':reason}
    outgoing.spec.setdefault(CHOICES,{})[source]=choice
    return deepcopy(choice)


def _chosen(engine,outgoing,source):
    if source==BATON:
        import coat_effects as COATS
        return COATS.preflight_transfer(engine,outgoing,source)
    choice=outgoing.spec.get(CHOICES,{}).get(source)
    if not isinstance(choice,dict) or choice.get('source')!=source or choice.get('outgoing_id')!=outgoing.entity_id:
        raise ValueError('actual selected replacement required')
    C.integer(choice.get('at'),'replacement choice time',0,engine.elapsed_seconds)
    incoming=W.actor_index(engine).get(choice.get('incoming_id'))
    if incoming is None:raise ValueError('selected replacement is missing')
    pair(engine,outgoing,incoming)
    return incoming


def _fresh_move(engine,outgoing):
    rows=[row for row in getattr(engine,'_move_completions',{}).values() if row['actor'] is outgoing]
    row=rows[-1] if rows else None
    if (row is None or row['phase']!='complete' or row['round']!=engine.round_no
            or row['turn_serial']!=outgoing.custom_conditions.get('combat_turn_serial',0)
            or row['completed_at']!=engine.elapsed_seconds or not row.get('sealed')):
        raise ValueError('Round Trip requires the just-completed actual owned Pokemon Move')
    owner=_owner(engine,outgoing)
    used=[use for use in owner.spec.get(USES,[]) if use.get('move_id')==row['id']]
    if any(use.get('phase')!='dispatching' for use in used):raise ValueError('Round Trip already consumed this actual Move')
    expected=used[-1]['action_boundary'] if used else row.get('native_switch_window')
    if expected!=action_boundary(engine):raise ValueError('Round Trip Move is no longer the immediate native action boundary')
    return row


def _feature(engine,trainer,source):
    import contest_features as FEATURES
    import skill_modifiers as SKILL
    selected(engine,source);FEATURES.conscious_trainer(trainer)
    for uid in (CLASS,ROUND_TRIP,*((TAG_IN,) if source==TAG_IN else ())):FEATURES.require(engine,trainer,uid)
    minimum=5 if source==TAG_IN else 4
    if max(SKILL.effective_rank(engine.r,trainer,key) for key in ('곡예','교활'))<minimum:
        raise ValueError('actual Juggler switch Feature skill prerequisite required')


def _pay(engine,trainer,source):
    import action_lifecycle as ACTION
    import action_points as AP
    if AP.available(trainer)<1:raise ValueError('switch Feature requires one available AP')
    ACTION.triggered_free_action(engine,trainer,source)
    trainer.ap_account.charge(1)


def _orders(engine,outgoing,incoming,*,scope='orders'):
    import native_order_transfer as ORDERS
    return ORDERS.preflight(engine,outgoing,incoming,scope=scope)


def preflight_handoff(engine,outgoing,incoming,*,source=BATON,recalled=False,contract=None):
    selected(engine,source);selected(engine,BATON);pair(engine,outgoing,incoming,recalled=recalled)
    import coat_effects as COATS
    import combat_stage_sources as CS
    COATS.preflight_handoff(outgoing,incoming)
    CS.validate(outgoing);CS.validate(incoming)
    import native_switch_policy as POLICY
    contract=POLICY.contract(engine,outgoing) if contract is None else POLICY.validate(engine,contract)
    _orders(engine,outgoing,incoming,scope=contract['scope'])
    return contract


def handoff(engine,outgoing,incoming,*,source,stages,recall_id,contract):
    preflight_handoff(engine,outgoing,incoming,source=source,recalled=not outgoing.on_field,contract=contract)
    import combat_stage_sources as CS
    import coat_effects as COATS
    import native_order_transfer as ORDERS
    clocks=ORDERS.plan_clocks(engine,outgoing,incoming,scope=contract['scope'])
    orders=ORDERS.transfer(engine,outgoing,incoming,source=source,recall_id=recall_id,scope=contract['scope'])
    if stages is not None:CS.assign_combat(incoming,stages)
    coats=COATS.transfer_to(engine,outgoing,incoming,source=source,recall_id=recall_id)
    if not outgoing.on_field:
        import state_grants as G
        G.reconcile(engine,outgoing);G.reconcile(engine,incoming)
    return {'stages':None if stages is None else dict(stages),'coats':coats,'orders':orders,'clocks':clocks}


def inspect(engine,actor,target,effect,source):
    if source==ROUND_TRIP:
        if effect!=ROUND_EFFECT:raise ValueError('selected Round Trip payload changed')
        _feature(engine,actor,source)
        if _owner(engine,target) is not actor:raise ValueError('Round Trip belongs to the actual Pokemon Trainer')
        _fresh_move(engine,target);incoming=_chosen(engine,target,source)
    elif source==BATON:
        if effect!=BATON_EFFECT:raise ValueError('selected Baton Pass payload changed')
        incoming=_chosen(engine,actor,source)
        preflight_handoff(engine,actor,incoming)
    elif effect.get('pass'):
        raise ValueError('transfer needs a reviewed native source')
    else:return None
    import body_state as BODY
    outgoing=target if source==ROUND_TRIP else actor
    if engine.grid is not None and not BODY.can_place(engine,incoming,outgoing.pos,ignore_actors=(outgoing,)):
        raise ValueError('replacement does not fit the actual outgoing position')
    return incoming


def execute(engine,actor,target,effect,ctx):
    import state_grants as G
    def apply(e,a,t):
        context=G._stage_transition_payload(engine,e,ctx)
        return _execute(e,a,t,effect,context)
    scopes=getattr(engine,'_native_switch_receipts',[])
    engine._native_switch_receipts=scopes;scopes.append(ctx['effect_receipt'])
    try:return G.transition(engine,actor,apply,participants=(target,),include_grid=engine.grid is not None)
    finally:
        scopes.pop()
        if not scopes:del engine._native_switch_receipts


def _execute(engine,actor,target,effect,ctx):
    import combat_state_lifecycle as COMBAT
    import condition_recovery as RECOVERY
    source=ctx['source_id'];incoming=inspect(engine,actor,target,effect,source)
    if source.startswith('move/'):
        completion=getattr(engine,'_move_completions',{}).get(ctx.get('move_completion'))
        if (completion is None or completion['actor'] is not actor or completion['move_id']!=source
                or completion['phase']=='complete' or ctx.get('move',{}).get('id')!=source
                or completion['round']!=engine.round_no or completion['turn_serial']!=actor.custom_conditions.get('combat_turn_serial',0)):
            raise ValueError('switch effect requires its actual native Move producer')
    elif source==ROUND_TRIP:
        move=_fresh_move(engine,target)
        paid=[use for use in actor.spec.get(USES,[]) if use.get('source')==source
              and use.get('move_id')==move['id'] and use.get('phase')=='dispatching' and use.get('paid_ap')==1]
        if len(paid)!=1:raise ValueError('Round Trip requires its actual paid Free activation')
    outgoing=target if source==ROUND_TRIP else actor
    W.require_actors(engine,outgoing)
    if outgoing.kind!='pokemon' or not outgoing.on_field:raise ValueError('actual field Pokemon must be recalled')
    if not effect.get('ignore_trapped') and not RECOVERY.permits_recall(outgoing):
        raise ValueError('Trapped prevents this native recall')
    stages=dict(outgoing.stages);position=outgoing.pos
    contract=__import__('native_switch_policy').contract(engine,outgoing) if source==BATON else None
    recall_id=outgoing.entity_id+':recall:'+str(len(outgoing.spec.get(RECALLS,[]))+1)
    result={'source':source,'outgoing_id':outgoing.entity_id,
            'incoming_id':None if incoming is None else incoming.entity_id,
            'recalled':False,'sent':False,'recall_id':recall_id,'transfer':None,'contract':contract,
            'move_completion':ctx.get('move_completion'),
            'at':engine.elapsed_seconds,'from_turn':outgoing.custom_conditions.get('combat_turn_serial',0),
            'to_turn':None if incoming is None else incoming.custom_conditions.get('combat_turn_serial',0)}
    engine._effect_dispatch_receipts[ctx['effect_receipt']]['native_switch']=result
    if source==BATON:
        import native_order_transfer as ORDERS,coat_effects as COATS
        result['transfer']={'stages':dict(stages),'coats':[row['id'] for row in COATS.live(outgoing)],
                            'orders':ORDERS.plan_ids(engine,outgoing,incoming,scope=contract['scope']),
                            'clocks':ORDERS.plan_clocks(engine,outgoing,incoming,scope=contract['scope'])}
        result['integrity']=seal(result)
        # Transfer before recall so recall-owned cleanup cannot delete the passed effect.
        transfer=handoff(engine,outgoing,incoming,source=source,stages=stages,
            recall_id=recall_id,contract=contract)
    else:transfer=None
    COMBAT.recall(engine,outgoing,ignore_trapped=effect.get('ignore_trapped',False))
    if source==BATON:
        import state_grants as G
        G.reconcile(engine,outgoing);G.reconcile(engine,incoming)
    recall=outgoing.spec.get(RECALLS,[])
    recall_id=recall[-1]['id'] if recall else None
    if incoming is not None:COMBAT.send_out(engine,incoming,pos=position)
    result.update(recalled=True,sent=incoming is not None,recall_id=recall_id,transfer=transfer)
    result['integrity']=seal(result)
    if source==BATON:
        import coat_effects as COATS
        outgoing.spec.get(COATS.TRANSFER_CHOICES,{}).pop(BATON,None)
        if not outgoing.spec.get(COATS.TRANSFER_CHOICES):outgoing.spec.pop(COATS.TRANSFER_CHOICES,None)
    elif source==ROUND_TRIP:
        outgoing.spec.get(CHOICES,{}).pop(source,None)
        if not outgoing.spec.get(CHOICES):outgoing.spec.pop(CHOICES,None)
    engine.log('  '+outgoing.name+': actual native recall/replacement',source)


def observe_recall(engine,outgoing,stages):
    if outgoing.kind!='pokemon':return
    import party_actions as PARTY
    owner=PARTY.owner(engine,outgoing)
    if owner is None:return
    rows=outgoing.spec.setdefault(RECALLS,[])
    fact={'id':outgoing.entity_id+':recall:'+str(len(rows)+1),'outgoing_id':outgoing.entity_id,
          'trainer_id':owner.entity_id,'round':engine.round_no,'at':engine.elapsed_seconds,
          'turn_serial':outgoing.custom_conditions.get('combat_turn_serial',0),'stages':dict(stages),'fainted':outgoing.fainted,
          'send_serial':owner.spec.get('native_send_serial',0),'action_boundary':action_boundary(engine),
          'order_ids':__import__('native_order_transfer').live_ids(outgoing),
          'stratagem_ids':__import__('native_order_transfer').live_ids(outgoing,scope='stratagems')}
    rows.append({'fact':fact,'integrity':ROOT.fingerprint(fact),'id':fact['id']})


def select_tag_in(engine,trainer,outgoing,*,reason):
    """Choose the triggered Feature before a paid party or Move recall starts."""
    W.require_actors(engine,trainer,outgoing);_feature(engine,trainer,TAG_IN)
    if _owner(engine,outgoing) is not trainer or not outgoing.on_field:
        raise ValueError('Tag In selection requires the actual owned field Pokemon')
    if type(reason)is not str or not reason.strip():raise ValueError('actual Tag In choice reason required')
    if TAG in trainer.spec or TAG_CHOICE in trainer.spec:raise ValueError('a Tag In choice is already pending')
    import action_points as AP
    if AP.available(trainer)<1:raise ValueError('Tag In requires one available AP')
    __import__('native_switch_policy').contract(engine,outgoing)
    trainer.spec[TAG_CHOICE]={'outgoing_id':outgoing.entity_id,'reason':reason,
                             'action_boundary':action_boundary(engine)}


def _tag_activation(engine,trainer,outgoing,recall):
    if TAG in trainer.spec or any(x.get('recall_id')==recall['id'] for x in trainer.spec.get(USES,[])):
        raise ValueError('Tag In already selected for this recall')
    _pay(engine,trainer,TAG_IN)
    record={'source':TAG_IN,'recall_id':recall['id'],'outgoing_id':outgoing.entity_id,
            'trainer_id':trainer.entity_id,'at':engine.elapsed_seconds,'round':engine.round_no,
            'paid_ap':1,'phase':'pending','action_boundary':action_boundary(engine),
            'contract':__import__('native_switch_policy').contract(engine,outgoing),'stage_reset':None}
    record['fainted_stage_rule']=__import__('native_switch_policy').fainted_tag_rule(engine,fainted=recall['fact']['fainted'])
    if record['fainted_stage_rule'] is not None and record['fainted_stage_rule']['fainted_at_recall']:
        record['stage_reset']={'source':'hb-finance:36','actor_id':outgoing.entity_id,
                               'at':engine.elapsed_seconds,'round':engine.round_no}
    record['integrity']=seal(record)
    trainer.spec[TAG]=record;trainer.spec.setdefault(USES,[]).append(record)
    return record


def begin_recall(engine,outgoing):
    """Called by the actual recall after its eligibility guards, before reset."""
    import party_actions as PARTY
    trainer=PARTY.owner(engine,outgoing)
    choice=None if trainer is None else trainer.spec.get(TAG_CHOICE)
    if choice is None or choice['outgoing_id']!=outgoing.entity_id:return
    _feature(engine,trainer,TAG_IN)
    recall=outgoing.spec[RECALLS][-1]
    _tag_activation(engine,trainer,outgoing,recall)
    trainer.spec.pop(TAG_CHOICE)


def preserve_order_on_recall(engine,actor,record):
    import party_actions as PARTY,native_order_transfer as ORDERS
    owner=PARTY.owner(engine,actor);pending=None if owner is None else owner.spec.get(TAG)
    return (pending is not None and pending.get('outgoing_id')==actor.entity_id
            and pending.get('phase')=='pending' and pending['contract']['scope']=='orders' and record in ORDERS._timed(actor))


def clear_pending_stages(engine,actor):
    """The existing later reset ends only the untransferred stage contribution."""
    import party_actions as PARTY
    owner=PARTY.owner(engine,actor)
    pending=None if owner is None else owner.spec.get(TAG)
    if pending is None or pending['outgoing_id']!=actor.entity_id or pending['stage_reset'] is not None:return
    pending['stage_reset']={'source':'combat_state_lifecycle.reset_actor','actor_id':actor.entity_id,
                            'at':engine.elapsed_seconds,'round':engine.round_no}
    pending['integrity']=seal(pending)


def _recall(engine,trainer,outgoing):
    rows=outgoing.spec.get(RECALLS,[]);row=rows[-1] if rows else None
    fact=None if row is None else row['fact']
    if (row is None or row['integrity']!=ROOT.fingerprint(fact) or outgoing.on_field
            or fact['trainer_id']!=trainer.entity_id or fact['round']!=engine.round_no
            or fact['at']!=engine.elapsed_seconds or fact['send_serial']!=trainer.spec.get('native_send_serial',0)
            or fact['action_boundary']!=action_boundary(engine)):
        raise ValueError('Tag In requires the actual just-completed recall before any send-out')
    return row


def activate(engine,trainer,source,outgoing):
    import state_grants as G
    W.require_actors(engine,trainer,outgoing)
    source=identity(source)
    def apply(e,user,pokemon):
        _feature(e,user,source)
        if _owner(e,pokemon) is not user:raise ValueError('actual owned Pokemon required')
        if source==TAG_IN:
            recall=_recall(e,user,pokemon)
            contract=__import__('native_switch_policy').contract(e,pokemon)
            live=__import__('native_order_transfer').live_ids(pokemon,scope=contract['scope'])
            field='order_ids' if contract['scope']=='orders' else 'stratagem_ids'
            if not set(recall['fact'][field])<=set(live):
                raise ValueError('select Tag In at the actual recall boundary before its live Orders expire')
            return deepcopy(_tag_activation(e,user,pokemon,recall))
        move=_fresh_move(e,pokemon);inspect(e,user,pokemon,ROUND_EFFECT,source)
        _pay(e,user,source)
        use={'source':source,'move_id':move['id'],'paid_ap':1,'at':e.elapsed_seconds,
             'round':e.round_no,'phase':'dispatching','action_boundary':action_boundary(e)}
        user.spec.setdefault(USES,[]).append(use)
        import effects as FX
        batch=FX.run_effects(e,user,pokemon,[ROUND_EFFECT],{'hit':True},source)
        if tuple(batch)!=(1,0):raise ValueError('native Round Trip did not complete')
        outcome=batch.outcomes[0];row=e._effect_dispatch_receipts[outcome.receipt]
        use.update(receipt=outcome.receipt,phase='completed')
        return dict(row['native_switch'],receipt=outcome.receipt,occurrence=outcome.occurrence)
    return G.transition(engine,trainer,apply,participants=(outgoing,),include_grid=engine.grid is not None)


def round_trip(engine,trainer,outgoing,incoming):
    import state_grants as G
    def apply(e,user,pokemon,replacement):
        select(e,pokemon,replacement,source=ROUND_TRIP,reason='actual Round Trip replacement')
        return activate(e,user,ROUND_TRIP,pokemon)
    return G.transition(engine,trainer,apply,participants=(outgoing,incoming),include_grid=engine.grid is not None)


def before_send(engine,incoming):
    import party_actions as PARTY
    owner=PARTY.owner(engine,incoming)
    if owner is None:return None
    pending=owner.spec.get(TAG)
    result=None
    if pending is not None:
        outgoing=W.actor_index(engine).get(pending['outgoing_id'])
        if outgoing is None:raise ValueError('pending Tag In outgoing Pokemon missing')
        recall=next((r for r in outgoing.spec.get(RECALLS,[]) if r['id']==pending['recall_id']),None)
        if recall is None:raise ValueError('pending Tag In lost its actual recall')
        import native_order_transfer as ORDERS,coat_effects as COATS
        preflight_handoff(engine,outgoing,incoming,source=TAG_IN,recalled=True,contract=pending['contract'])
        stages=recall['fact']['stages'] if pending['stage_reset'] is None else None
        pending.update(phase='sending',incoming_id=incoming.entity_id,sent_at=engine.elapsed_seconds,
            from_turn=outgoing.custom_conditions.get('combat_turn_serial',0),
            to_turn=incoming.custom_conditions.get('combat_turn_serial',0),
            transfer={'stages':None if stages is None else dict(stages),
                      'coats':[row['id'] for row in COATS.live(outgoing)],
                      'orders':ORDERS.plan_ids(engine,outgoing,incoming,scope=pending['contract']['scope']),
                      'clocks':ORDERS.plan_clocks(engine,outgoing,incoming,scope=pending['contract']['scope'])})
        pending['integrity']=seal(pending)
        engine._native_tag_in_use=pending
        try:result=handoff(engine,outgoing,incoming,source=TAG_IN,
                stages=stages,recall_id=recall['id'],contract=pending['contract'])
        finally:del engine._native_tag_in_use
        pending.update(phase='completed',transfer=deepcopy(result))
        pending['integrity']=seal(pending)
        owner.spec.pop(TAG)
    owner.spec['native_send_serial']=owner.spec.get('native_send_serial',0)+1
    return result


def validate_world(engine,index):
    for actor in index.values():
        used_recalls=set()
        for use in actor.spec.get(USES,[]):
            if use.get('source')==TAG_IN:
                __import__('native_switch_policy').validate(engine,use['contract'])
                __import__('native_switch_policy').validate_fainted_tag_rule(engine,use['fainted_stage_rule'])
                if use.get('integrity')!=seal(use) or use.get('paid_ap')!=1 or use.get('trainer_id')!=actor.entity_id:
                    raise ValueError('Tag In actual paid source record changed')
                outgoing=index.get(use.get('outgoing_id'))
                recall=next((row['fact'] for row in outgoing.spec.get(RECALLS,[]) if row['id']==use.get('recall_id')),None) if outgoing is not None else None
                if (recall is None or recall['trainer_id']!=actor.entity_id or use['recall_id'] in used_recalls
                        or (use['at'],use['round'])!=(recall['at'],recall['round'])):
                    raise ValueError('Tag In must consume one actual contemporaneous owned recall')
                used_recalls.add(use['recall_id'])
                if use['fainted_stage_rule'] is not None and use['fainted_stage_rule']['fainted_at_recall']!=recall['fainted']:
                    raise ValueError('Tag In Q&A faint predicate differs from its actual recall')
                if use.get('phase') not in ('pending','sending','completed'):
                    raise ValueError('Tag In requires its actual native activation phase')
                reset=use.get('stage_reset')
                if reset is not None:
                    if (type(reset)is not dict or set(reset)!={'source','actor_id','at','round'}
                            or reset['source'] not in ('combat_state_lifecycle.reset_actor','hb-finance:36')
                            or reset['actor_id']!=use['outgoing_id']):
                        raise ValueError('queued Tag In stages require their actual original-owner reset')
                    C.integer(reset['at'],'queued stage reset time',use['at'],engine.elapsed_seconds)
                    C.integer(reset['round'],'queued stage reset round',use['round'],engine.round_no)
                    if reset['source']=='hb-finance:36' and not (use['fainted_stage_rule'] or {}).get('fainted_at_recall'):
                        raise ValueError('only the selected fainted-recall Q&A suppresses Tag In stages')
                if use.get('phase')=='sending' and getattr(engine,'_native_tag_in_use',None) is not use:
                    raise ValueError('unfinished Tag In send-out is not a persisted completed occurrence')
        for number,row in enumerate(actor.spec.get(RECALLS,[]),1):
            fact=row['fact']
            if (actor.kind!='pokemon' or row['integrity']!=ROOT.fingerprint(fact)
                    or row['id']!=actor.entity_id+':recall:'+str(number) or fact['id']!=row['id']
                    or fact['outgoing_id']!=actor.entity_id or fact['trainer_id'] not in index):
                raise ValueError('native recall identity or historical observation changed')
            C.integer(fact['at'],'native recall time',0,engine.elapsed_seconds)
            if type(fact['fainted'])is not bool:raise ValueError('actual recall faint observation required')
            if set(fact['stages'])!={'atk','def','spa','spd','spe'}:raise ValueError('actual recalled combat stages required')
            for value in fact['stages'].values():C.integer(value,'recalled combat stage',-6,6)
        pending=actor.spec.get(TAG)
        if pending is not None:
            if (actor.kind!='trainer' or not any(pending is use for use in actor.spec.get(USES,[]))
                    or pending.get('phase') not in ('pending','sending')):
                raise ValueError('pending Tag In requires its paid native activation')
            outgoing=index.get(pending.get('outgoing_id'))
            if (outgoing is None or outgoing.spec.get('trainer_id')!=actor.entity_id
                    or not any(r['id']==pending.get('recall_id') for r in outgoing.spec.get(RECALLS,[]))
                    or pending.get('paid_ap')!=1 or pending.get('source')!=TAG_IN):
                raise ValueError('pending Tag In recall/payment identity changed')
    import native_order_transfer as ORDERS
    ORDERS.validate_world(engine,index)
    import effect_instances as INSTANCES
    for holder in index.values():
        for record,_ in INSTANCES.records(holder):
            if record[INSTANCES.KEY]['kind']!='coat':continue
            for event in record[INSTANCES.KEY]['ownership'][1:]:
                # Only historical Baton transfers predate native recall proof.
                if event['source']==BATON and 'recall_id' not in event:continue
                if not {'recall_id','trainer_id','from_turn','to_turn'}<=set(event):
                    raise ValueError('Tag In Coat handoff requires complete native recall proof')
                facts={key:event[key] for key in ('source','at','recall_id','trainer_id','from_turn','to_turn')}
                facts.update(from_id=event['from_holder_id'],to_id=event['holder_id'])
                ORDERS.require_switch_proof(engine,facts,record['id'],kind='coats')
    return True


def action_boundary(engine):
    return {'round':engine.round_no,
        'active_actor_id':None if engine._active_turn_actor is None else engine._active_turn_actor.entity_id,
        'turn_closure_count':len(engine._turn_closures),
        'last_move':next(reversed(getattr(engine,'_move_completions',{})),None),
        'actors':{a.entity_id:{'turn':a.custom_conditions.get('combat_turn_serial',0),
                              'actions':deepcopy(getattr(a,'_action_history',[]))}
                  for a in W.actor_index(engine).values()}}


def observe_move(engine,row):
    if 'native_switch_window' in row:return
    events=getattr(engine,'_passive_events',{})
    returns=row.get('native_returns',{})
    for target in row['targets']:
        issued=[event_id for event_id,event in events.items() if event.get('completion_id')==row['id']
                and event.get('target') is target and event.get('producer')=='Engine.use_move']
        if any(event_id not in returns for event_id in issued) or target.entity_id not in row['results']:return
    import party_actions as PARTY
    owner=PARTY.owner(engine,row['actor'])
    native_recall=any(getattr(engine,'_effect_dispatch_receipts',{}).get(token,{}).get('native_switch')
                      for token in row['effects'])
    if native_recall or owner is not None and any(identity(name)==ROUND_TRIP for name in owner.spec.get('feats',[])):
        row['native_switch_window']=action_boundary(engine)


def seal(record):
    return ROOT.fingerprint({key:value for key,value in record.items() if key!='integrity'})
