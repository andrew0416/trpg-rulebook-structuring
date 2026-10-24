"""Paid trainer recall/send/switch actions, distinct from GM placement changes."""
from copy import deepcopy
import common_checks as C
import world_entities as W
import resolution_transaction as TX
import action_resources as RESOURCES

KEY='party_action_receipts'
POLICY='party_combat_policy'
SOURCE='input/ch07-combat.md:92-102'
GYM='gym_command_profile'
GYM_SOURCE='input/ch11-running-the-game.md:97'
NICOLETTE_SOURCE='input/ch11-running-the-game.md:2145-2146'
COMMAND_SOURCE='input/ch07-combat.md:86-88'
FORMAT_SOURCE='input/ch07-combat.md:12-16,27-30'
FORMAT_PREFIX='gm/battle-format/'

def _combat_source(engine):
    from source_context import verified_source
    verified_source(engine.r,{'file':'input/ch07-combat.md',
        'sha256':'57abb79c4f70c64246cd7927bffe2377e951bdc32dfa4c9a5c14b4ad97618c18'},label='battle and command policy')

def _gym_source(engine):
    from source_context import verified_source
    verified_source(engine.r,{'file':'input/ch11-running-the-game.md',
        'sha256':'5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad'},label='gym command profile')

def gym_profile(engine,*,entering=False):
    epoch=getattr(engine,'_party_encounter_epoch',0)+(1 if entering and not engine.encounter_active else 0)
    rows=[a.spec[GYM] for a in W.actors(engine) if GYM in a.spec and a.spec[GYM]['encounter_epoch']==epoch]
    if len(rows)>1:raise ValueError('only one actual gym challenge may own an encounter')
    if not rows:return None
    _gym_source(engine)
    return rows[0]

def configure_gym(engine,leader,*,pc_trainers,gym_trainers,pokemon,leader_turn_limit,gm_id,reason,sample=None):
    """GM group adoption for the next encounter; pools never grant turns.

    Only the leader's ordinary Pokemon-turn cap changes. PC/helper caps,
    voluntary switch locks and authoritative borrowed turns keep their owners.
    """
    pcs,helpers,pool=tuple(pc_trainers),tuple(gym_trainers),tuple(pokemon)
    actors=(leader,*pcs,*helpers,*pool)
    W.require_actors(engine,*actors)
    if engine.encounter_active or engine.round_start_seconds is not None or engine._active_turn_actor is not None:
        raise ValueError('gym profile requires a closed encounter')
    if len({a.entity_id for a in actors})!=len(actors) or not pcs or not pool:
        raise ValueError('distinct actual gym trainers and Pokemon required')
    if any(type(x)is not str or not x.strip() for x in (gm_id,reason)):
        raise ValueError('explicit GM identity and adoption reason required')
    C.integer(leader_turn_limit,'GM leader Pokemon turns per round',1)
    if sample not in (None,'nicolette'):raise ValueError('reviewed gym sample required')
    gym_count=sum(p.spec.get('trainer_id')==leader.entity_id for p in pool)
    if sample=='nicolette' and (helpers or leader_turn_limit!=gym_count):
        raise ValueError('Nicolette sample commands exactly its declared whole team')
    trainers=(leader,*pcs,*helpers);ids={a.entity_id for a in trainers}
    if any(a.kind!='trainer' or a.spec.get(POLICY,{}).get('battle_mode')!='league' for a in trainers):
        raise ValueError('actual trainers with explicit League battle policies required')
    if any(p.kind!='pokemon' or p.spec.get('trainer_id') not in ids for p in pool):
        raise ValueError('gym pool requires actual Pokemon of the admitted trainers')
    if any(not any(p.spec['trainer_id']==a.entity_id for p in pool) for a in trainers):
        raise ValueError('each admitted trainer needs an actual Pokemon pool')
    if gym_profile(engine,entering=True) is not None:
        raise ValueError('next encounter already has an adopted gym profile')
    _gym_source(engine)
    import state_grants as G
    def apply(e,a,*subjects):
        a.spec[GYM]={'source':GYM_SOURCE,'gm_id':gm_id,'reason':reason,
            'encounter_epoch':getattr(e,'_party_encounter_epoch',0)+1,
            'leader_id':a.entity_id,'pc_trainer_ids':[p.entity_id for p in pcs],
            'gym_trainer_ids':[p.entity_id for p in helpers],
            'pokemon_owners':{p.entity_id:p.spec['trainer_id'] for p in pool},
            'leader_turn_limit':leader_turn_limit}
        if sample=='nicolette':
            a.spec[GYM].update(sample_source=NICOLETTE_SOURCE,
                pool_guidance={'pc_pokemon':len(pool)-gym_count,'gym_pokemon':gym_count,
                               'recommended_pc_total':gym_count*1.5,'enforced_cap':False})
        return deepcopy(a.spec[GYM])
    return G.transition(engine,leader,apply,participants=actors[1:])

def require_gym_participants(engine,actors,*,entering=False):
    row=gym_profile(engine,entering=entering)
    if row is None:return
    allowed={row['leader_id'],*row['pc_trainer_ids'],*row['gym_trainer_ids'],*row['pokemon_owners']}
    for actor in actors:
        W.require_actors(engine,actor)
        if actor.entity_id not in allowed:raise ValueError('actor is not an admitted gym participant')
        if actor.kind=='pokemon' and actor.spec.get('trainer_id')!=row['pokemon_owners'].get(actor.entity_id):
            raise ValueError('admitted gym Pokemon ownership changed')

def end_gym(engine):
    for actor in W.actors(engine):actor.spec.pop(GYM,None)

def scope(engine):return (getattr(engine,'_party_encounter_epoch',0),engine.round_no)

def configure(engine,trainer,*,battle_mode,reason,command_limit=1,gm_id=None):
    W.require_actors(engine,trainer)
    if trainer.kind!='trainer' or engine.encounter_active:raise ValueError('party combat policy requires an actual trainer outside combat')
    if battle_mode not in ('league','full_contact') or type(reason) is not str or not reason.strip():raise ValueError('explicit battle mode and GM reason required')
    C.integer(command_limit,'GM Pokemon ordinary turns per round',1)
    if (gm_id is not None and (type(gm_id)is not str or not gm_id.strip())) or (command_limit!=1 and gm_id is None):
        raise ValueError('explicit GM identity required for additional Pokemon commands')
    if trainer.spec.get(KEY):raise ValueError('existing party action history requires a new encounter policy adapter before changing mode')
    _combat_source(engine)
    import state_grants as G
    def apply(e,a):
        a.spec[POLICY]={'battle_mode':battle_mode,'reason':reason,'source':SOURCE}
        if command_limit!=1:
            a.spec[POLICY].update(command_limit=command_limit,gm_id=gm_id,command_source=COMMAND_SOURCE)
        return deepcopy(a.spec[POLICY])
    return G.transition(engine,trainer,apply)

def current(engine,trainer):
    return [row['result'] for row in trainer.spec.get(KEY,{}).values() if not row.get('pending') and tuple(row['result']['scope'])==scope(engine)]


def format_layout(battle_mode):
    if battle_mode=='full_contact':
        return [{'id':'ordinary','roles':['*'],'reverse':False,'declaration':False}]
    if battle_mode!='league':raise ValueError('actual League or full contact battle mode required')
    return [{'id':'declare','roles':['trainer'],'reverse':True,'declaration':True},
            {'id':'trainers','roles':['trainer'],'reverse':False,'declaration':False},
            {'id':'pokemon','roles':['pokemon'],'reverse':False,'declaration':False}]


def prepare_initiative(engine,participants,*,battle_mode,bindings=None,procedures=None):
    """Adopt the printed format through the existing native schedule owner."""
    import initiative_schedule as SCHEDULE
    actors=tuple(participants);W.require_actors(engine,*actors)
    layout=format_layout(battle_mode);_combat_source(engine)
    if not actors or any(a.kind not in ('trainer','pokemon') for a in actors):
        raise ValueError('battle format requires actual trainer/Pokemon participants')
    for actor in actors:
        trainer=actor if actor.kind=='trainer' else owner(engine,actor)
        if trainer is not None and trainer.spec.get(POLICY,{}).get('battle_mode')!=battle_mode:
            raise ValueError('participant owner must adopt the actual battle mode')
    if bindings is not None:
        index={a.entity_id:a for a in actors}
        if any(row.get('actor_id') not in index or row.get('role')!=index[row['actor_id']].kind for row in bindings):
            raise ValueError('battle format roles must match actual participants')
    roles={a.kind for a in actors}
    # Empty role phases are harmless; order groups must partition nonempty sets.
    groups=[[role] for role in ('trainer','pokemon') if role in roles] if battle_mode=='league' else [['*']]
    return SCHEDULE.prepare(engine,actors,source=FORMAT_PREFIX+battle_mode,
        bindings=bindings,layout=layout,procedures=procedures,order_groups=groups)


def validate_format(engine,state):
    if not state['source'].startswith(FORMAT_PREFIX):return
    mode=state['source'][len(FORMAT_PREFIX):]
    _combat_source(engine)
    if state['layout']!=format_layout(mode):raise ValueError('battle format lost its printed native phase layout')
    for row in state['slots'].values():
        if row['role']!=row['actor'].kind:raise ValueError('battle format role differs from actual participant')
        trainer=row['actor'] if row['actor'].kind=='trainer' else owner(engine,row['actor'])
        if trainer is not None and trainer.spec.get(POLICY,{}).get('battle_mode')!=mode:
            raise ValueError('battle format lost its actual owner mode adoption')
    if mode=='league':
        roles=[state['slots'][key]['role'] for key in state['order']]
        if roles!=sorted(roles,key=lambda role:0 if role=='trainer' else 1):
            raise ValueError('League resolves trainers before Pokemon')


def switch_lock(engine,pokemon):
    trainer=owner(engine,pokemon)
    if trainer is None or trainer.spec.get(POLICY,{}).get('battle_mode')!='league':return None
    for request,row in trainer.spec.get(KEY,{}).items():
        if tuple(row['result']['scope'])==scope(engine) and pokemon.entity_id in row['result']['blocked_command_ids']:
            return {'trainer':trainer,'request_id':request,'scope':list(scope(engine))}
    return None


def validate_switch_lock(engine,pokemon,proof):
    _combat_source(engine)
    trainer=proof['trainer'];W.require_actors(engine,pokemon,trainer)
    row=trainer.spec.get(KEY,{}).get(proof['request_id'])
    result=None if row is None else row['result']
    if (trainer.kind!='trainer' or result is None or result['source']!=SOURCE
            or result['actor_id']!=trainer.entity_id or result['request_id']!=proof['request_id']
            or result['scope']!=proof['scope'] or pokemon.entity_id not in result['blocked_command_ids']
            or row['intent']['policy']['battle_mode']!='league'
            or not result['counts_as_switch'] or not any(not r['fainted'] for r in result['recall_events']+
                [event for prior in trainer.spec.get(KEY,{}).values()
                 if prior['result']['scope']==result['scope'] for event in prior['result']['recall_events']])):
        raise ValueError('switch lock requires its actual voluntary League party receipt')
    return result

def owner(engine,pokemon):
    uid=pokemon.spec.get('trainer_id')
    return next((a for a in W.actors(engine) if a.kind=='trainer' and a.spec.get('id')==uid),None)

def require_command(engine,pokemon,move_id=None):
    require_gym_participants(engine,(pokemon,))
    if pokemon.kind!='pokemon':return
    import marsupial_state as MARSUPIAL
    MARSUPIAL.require_independent(engine,pokemon)
    import special_entities as SPECIAL
    SPECIAL.require_prime_independent(engine,pokemon)
    import csv_item_form_contracts as CSV_FORMS
    CSV_FORMS.require_independent(engine,pokemon)
    if not engine.encounter_active:return
    import initiative_interrupts as INTERRUPTS
    frame=INTERRUPTS.frame(engine)
    INTERRUPTS.require_selected_move(engine,pokemon,move_id)
    trainer=owner(engine,pokemon)
    if trainer is None or POLICY not in trainer.spec:return
    _combat_source(engine)
    if not pokemon.on_field:raise ValueError('recalled Pokemon cannot take a combat action')
    if switch_lock(engine,pokemon) is not None:
        if frame and frame['mode']=='switch_interrupt' and frame['status']=='open' and frame['actor'] is pokemon:return
        raise ValueError('voluntary League switch prevents an ordinary command for the rest of this round')

def require_turn(engine,pokemon):
    require_gym_participants(engine,(pokemon,))
    if pokemon.kind!='pokemon':return
    import csv_item_form_contracts as CSV_FORMS
    CSV_FORMS.require_independent(engine,pokemon)
    if not engine.encounter_active:return
    import initiative_interrupts as INTERRUPTS
    require_command(engine,pokemon)
    if INTERRUPTS.is_borrow_start(engine,pokemon):return
    trainer=owner(engine,pokemon)
    if trainer is None or POLICY not in trainer.spec:return
    limit=command_limit(engine,trainer)
    used=sum(tuple(row['scope'])==scope(engine) for row in trainer.spec.get('party_command_turns',[]))
    if used+INTERRUPTS.command_debts(engine,trainer)>=limit:
        raise ValueError('this trainer already used the Pokemon ordinary turn for this round')


def command_limit(engine,trainer):
    profile=gym_profile(engine)
    return profile['leader_turn_limit'] if profile is not None and trainer.entity_id==profile['leader_id'] else trainer.spec[POLICY].get('command_limit',1)

def record_turn(engine,pokemon):
    if pokemon.kind!='pokemon' or not engine.encounter_active:return
    import initiative_interrupts as INTERRUPTS
    if INTERRUPTS.is_borrow_start(engine,pokemon):return
    trainer=owner(engine,pokemon)
    if trainer is not None and POLICY in trainer.spec:
        trainer.spec.setdefault('party_command_turns',[]).append({'scope':list(scope(engine)),'pokemon_id':pokemon.entity_id})

def settle_prepaid(engine,trainer):
    """Starting the trainer turn cannot replenish an already funded switch."""
    rows=[r['payment'] for r in current(engine,trainer) if r['payment']['phase']=='reserved']
    loss={}
    for row in rows:
        for kind,value in row['funded'].items():loss[kind]=loss.get(kind,0)+value
    if any(value>trainer.budget.get(kind,0) for kind,value in loss.items()):raise ValueError('prepaid party action overlaps another action loss')
    if loss:trainer.budget=RESOURCES.subtract(trainer.budget,loss)
    for row in rows:row.update(phase='paid',paid_turn=trainer.custom_conditions.get('combat_turn_serial',0))

def _pay(engine,trainer,kind,*,full_switch):
    import turn as TURN
    active=engine._active_turn_actor
    if active is trainer:
        before=deepcopy(trainer.budget)
        if not TURN.spend(engine,trainer,kind,'포켓몬 교대/복귀/방출'):raise ValueError('trainer cannot pay the party action')
        after=deepcopy(trainer.budget);phase='paid'
    else:
        if not full_switch or active is None or active.kind!='pokemon' or active.spec.get('trainer_id')!=trainer.spec['id']:
            raise ValueError('party action requires the trainer turn or owned Pokemon initiative for a full switch')
        if RESOURCES.pending(trainer):raise ValueError('switch at Pokemon initiative overlaps an existing next-action loss')
        pending=engine._ordinary_turn_rounds.get(trainer)!=engine.round_no
        old_budget=getattr(trainer,'budget',None)
        if pending:
            fresh=engine.r.mech('combat/action-economy')['per_round']
            loss={}
            for row in current(engine,trainer):
                if row['payment']['phase']=='reserved':
                    for token,value in row['payment']['funded'].items():loss[token]=loss.get(token,0)+value
            trainer.budget=RESOURCES.subtract({k:fresh[k] for k in RESOURCES.KINDS},loss)
        before=deepcopy(trainer.budget)
        engine._active_turn_actor=trainer
        try:
            if not TURN.spend(engine,trainer,kind,'포켓몬 이니셔티브에서 교대'):raise ValueError('trainer cannot fund the switch at Pokemon initiative')
            after=deepcopy(trainer.budget)
        finally:
            engine._active_turn_actor=active
            if pending:trainer.budget=old_budget
        phase='reserved' if pending else 'paid'
    funded={k:before[k]-after[k] for k in RESOURCES.KINDS if before[k]!=after[k]}
    return {'kind':kind,'budget_before':before,'budget_after':after,'funded':funded,'phase':phase}

def act(engine,trainer,*,recall=(),send=(),request_id,reason,release_throw=None,tag_in=False,feature=None):
    """send is an ordered list of (actual Pokemon, explicit map position) pairs."""
    if trainer.kind!='trainer':raise ValueError('actual trainer required')
    recall=tuple(recall);send=tuple((p,tuple(pos)) for p,pos in send)
    if type(tag_in)is not bool or tag_in and (len(recall)!=1 or len(send)>1):
        raise ValueError('Tag In selection requires one actual recall')
    subjects=[*recall,*(p for p,_ in send)]
    W.require_actors(engine,trainer,*subjects)
    if type(reason) is not str or not reason.strip():raise ValueError('actual party action reason required')
    policy=trainer.spec.get(POLICY)
    if policy is None:raise ValueError('explicit party combat policy required')
    intent={'actor_id':trainer.entity_id,'recall':[p.entity_id for p in recall],
            'send':[[p.entity_id,list(pos)] for p,pos in send],'reason':reason,'policy':deepcopy(policy)}
    if feature is not None:intent['feature']=deepcopy(feature)
    if release_throw is not None:
        if recall or len(send)!=1:raise ValueError('release throw belongs to one actual send')
        intent['release_throw']=deepcopy(release_throw)
    if tag_in:intent['tag_in']=True
    prior=TX.replay_result(trainer.spec.get(KEY,{}),request_id,intent)
    if prior is not None:
        if prior.get('pending'):
            event_id=prior['pending'].get('event_id')
            if event_id and engine._passive_pending==event_id:raise __import__('passive_events').PassiveEventPending(event_id)
            raise ValueError('finish the actual retained party-action reaction')
        return prior['result']
    feature_plan=None if feature is None else __import__('juggler').party_plan(engine,trainer,recall,send,feature)
    if tag_in and feature_plan and feature_plan['tag_in']:
        raise ValueError('select Tag In once for the actual recall')
    if release_throw is not None:
        __import__('capture_specialist').release_plan(engine,trainer,send[0][0],release_throw)
        bounce=release_throw.get('bounce')
        if bounce is not None:
            target=W.actor_index(engine).get(release_throw['target_id'])
            plan=__import__('juggler').bounce_plan(engine,trainer,target,bounce,function='release')
            expected=plan['landing'] if plan['timing']=='before' else plan['endpoint']
            if tuple(send[0][1])!=tuple(expected):raise ValueError('released Pokemon must occupy the actual ball function position')
    require_gym_participants(engine,(trainer,*subjects))
    if not engine.encounter_active or engine.round_start_seconds is None:raise ValueError('paid party action requires an actual open combat round')
    if not subjects or len(set(map(id,subjects)))!=len(subjects) or len(recall)>2 or len(send)>2 or (recall and send and (len(recall)!=1 or len(send)!=1)):
        raise ValueError('one actual switch, one recall/send, or a same-kind pair required')
    import movement_actions as MOVE
    MOVE.boundary(engine,'party_action')
    import action_lifecycle as ACTION
    ACTION.ensure_resolutions_clear(engine)
    import pokemon_activities as P
    import pokemon_party as PARTY
    import body_state as BODY
    from grid import cheb
    P._trainer(trainer)
    for p in subjects:P._pokemon(p);P._owner(trainer,p);PARTY.require_participation(engine,p)
    recalled={p.entity_id for p in recall};sent={p.entity_id for p,_ in send}
    history=current(engine,trainer)
    if any(recalled.intersection(row['sent']) or sent.intersection(row['recalled']) for row in history):
        raise ValueError('same Pokemon cannot be recalled and sent in one round')
    for p in recall:
        if not p.on_field:raise ValueError('recall requires an actual field Pokemon')
        import condition_recovery as RECOVERY
        if not RECOVERY.permits_recall(p) and not (feature_plan and feature_plan['ignore_trapped']):raise ValueError('Trapped prevents ordinary recall')
        if policy['battle_mode']!='league':
            if engine.grid is None:raise ValueError('actual recall beam distance requires a map')
            if min(cheb(a,b) for a in BODY.cells(trainer,require_complete=True) for b in BODY.cells(p,require_complete=True))>8:
                raise ValueError('actual Pokemon is beyond the eight metre recall beam')
    placements=[]
    for p,pos in send:
        if p.on_field or p.fainted or p.dead:raise ValueError('send requires a conscious actual off-field Pokemon')
        if len(pos)!=2 or any(type(v)is not int for v in pos) or engine.grid is None or not BODY.can_place(engine,p,pos,ignore_actors=recall):
            raise ValueError('actual send destination is outside, blocked or occupied')
        cells=BODY.at_position(p,pos)
        if any(cells&other for other in placements):raise ValueError('sent Pokemon bodies cannot overlap')
        placements.append(cells)
    if tag_in:
        import native_switch_transfer as SWITCH
        SWITCH._feature(engine,trainer,SWITCH.TAG_IN)
        if send:SWITCH.preflight_handoff(engine,recall[0],send[0][0],source=SWITCH.TAG_IN,recalled=True)
    cost='shift' if not(recall and send) or recall[0].fainted else 'standard'
    if release_throw is not None:cost='standard'
    if len(subjects)==2 and not(recall and send):cost='standard'
    prior_recall=[x for row in history for x in row['recall_events']]
    recall_events=[{'pokemon_id':p.entity_id,'fainted':p.fainted} for p in recall]
    is_switch=bool(send and (recall or prior_recall)) or bool(recall and any(row['sent'] for row in history))
    voluntary=any(not x['fainted'] for x in prior_recall+recall_events)
    blocked=sorted(sent | {uid for row in history for uid in row['sent']}) if policy['battle_mode']=='league' and is_switch and voluntary else []
    if feature_plan and feature_plan['preserve_turn']:blocked=[]
    import state_grants as G
    waiting=[]
    def apply(e,a,*participants):
        import action_lifecycle as ACTION,passive_events as P
        from_index={p.entity_id:p for p in participants}
        if tag_in:
            import native_switch_transfer as SWITCH
            SWITCH.select_tag_in(e,a,from_index[recall[0].entity_id],reason=reason)
        before_ap=__import__('action_points').available(a);before_budget=deepcopy(a.budget)
        if feature_plan:
            __import__('juggler').party_payment(e,a,feature_plan)
        if feature_plan and feature_plan['action']:
            payment={'kind':feature_plan['action'],'phase':'paid','source':feature_plan['source'],'ap':feature_plan['ap'],
                     'budget_before':before_budget,'budget_after':deepcopy(a.budget),'funded':{},
                     'ap_before':before_ap,'ap_after':__import__('action_points').available(a)}
        else:payment=_pay(e,a,cost,full_switch=bool(recall and send))
        result={'request_id':request_id,'actor_id':a.entity_id,'scope':list(scope(e)),
                'recalled':sorted(recalled),'sent':sorted(sent),'recall_events':deepcopy(recall_events),
                'counts_as_switch':is_switch,'blocked_command_ids':blocked,'payment':payment,'source':SOURCE}
        if feature_plan:result['feature_plan']=deepcopy(feature_plan)
        if feature_plan and feature_plan['tag_in']:
            result['tag_payment']={'source':'feat/태그-인','request_id':request_id,
                'outgoing_id':recall[0].entity_id,'paid_ap':1,
                'before_ap':before_ap-feature_plan['ap'],'after_ap':__import__('action_points').available(a),
                'consumed_recall':None}
        a.spec.setdefault(KEY,{})[request_id]={'intent':deepcopy(intent),'result':result,
            'pending':{'recall_cursor':0,'send_cursor':0,'event_id':None}}
        try:
            with ACTION.resolution(e,a,SOURCE,kind='escape'):
                return _continue_party(e,a,request_id)
        except P.PassiveEventPending as pending:
            if e._passive_pending!=pending.event_id:raise
            a.spec[KEY][request_id]['pending']['event_id']=pending.event_id
            waiting.append(pending.event_id)
            return None
    result=G.transition(engine,trainer,apply,participants=subjects,include_rulings=True,include_grid=engine.grid is not None)
    if waiting:raise __import__('passive_events').PassiveEventPending(waiting[0])
    return result


def validate_escape(engine,trainer,request_id):
    row=trainer.spec.get(KEY,{}).get(request_id)
    if row is None or not row.get('pending') or row['intent']['actor_id']!=trainer.entity_id or tuple(row['result']['scope'])!=scope(engine):
        raise ValueError('actual paid native party continuation required')
    progress=row['pending'];intent=row['intent']
    C.integer(progress['recall_cursor'],'actual recall progress',0,len(intent['recall']))
    C.integer(progress['send_cursor'],'actual send progress',0,len(intent['send']))
    if row['result']['payment']['phase'] not in ('paid','reserved'):raise ValueError('actual party payment prefix required')
    return row


def _continue_party(e,a,request_id):
    import combat_state_lifecycle as COMBAT,combat_move_reactions as REACTIONS
    row=validate_escape(e,a,request_id);intent=row['intent'];progress=row['pending'];index=W.actor_index(e)
    while progress['recall_cursor']<len(intent['recall']):
        target=index[intent['recall'][progress['recall_cursor']]]
        REACTIONS.before_escape(e,a,target,SOURCE,kind='party',request_id=request_id)
        row=a.spec[KEY][request_id];progress=row['pending']
        previous=getattr(e,'_native_party_recall',None)
        e._native_party_recall={'trainer':a,'outgoing':target,'request_id':request_id,'result':row['result']}
        try:
            __import__('juggler').before_recall(e,a,target,row['result'])
            COMBAT.recall(e,target,ignore_trapped=bool(row['result'].get('feature_plan',{}).get('ignore_trapped')))
        finally:
            if previous is None:del e._native_party_recall
            else:e._native_party_recall=previous
        progress['recall_cursor']+=1
    while progress['send_cursor']<len(intent['send']):
        uid,pos=intent['send'][progress['send_cursor']];target=index[uid]
        if 'release_throw' in intent:
            row['result']['release_throw']=__import__('capture_specialist').release_hit(e,a,target,intent['release_throw'])
        COMBAT.send_out(e,target,pos=pos,request_id=request_id,source_id=row['result'].get('feature_plan',{}).get('source') or SOURCE)
        progress['send_cursor']+=1
        if intent['recall']:
            __import__('initiative_schedule').replace_party(e,index[intent['recall'][0]],target,source=row['result'].get('feature_plan',{}).get('source') or SOURCE,request_id=request_id)
    import marsupial_state as MARSUPIAL
    MARSUPIAL.sync(e)
    row=a.spec[KEY][request_id];row.pop('pending');result=row['result']
    __import__('battle_contest').party_switched(e,a,result)
    e.log('  '+a.name+': '+result['payment']['kind']+' 포켓몬 복귀/방출 '+str(result['recalled'])+' → '+str(result['sent']),SOURCE)
    validate_world(e,W.actor_index(e))
    return deepcopy(result)


def resume_escape(engine,trainer,request_id):
    validate_escape(engine,trainer,request_id)
    result=_continue_party(engine,trainer,request_id)
    __import__('juggler').finish_party_reaction(engine,trainer,request_id)
    return result


def validate_world(engine,index):
    for actor in index.values():
        policy=actor.spec.get(POLICY)
        if policy is None:continue
        if (actor.kind!='trainer' or policy.get('battle_mode') not in ('league','full_contact')
                or policy.get('source')!=SOURCE or type(policy.get('reason'))is not str or not policy['reason'].strip()):
            raise ValueError('actual trainer and sourced battle policy required')
        C.integer(policy.get('command_limit',1),'GM Pokemon ordinary turn cap',1)
        if 'command_limit' in policy and (policy.get('command_source')!=COMMAND_SOURCE
                or type(policy.get('gm_id'))is not str or not policy['gm_id'].strip()):
            raise ValueError('additional commands require the actual sourced GM adoption')
        if 'command_limit' in policy:_combat_source(engine)
    for actor in index.values():
        row=actor.spec.get(GYM)
        if row is None:continue
        if (actor.kind!='trainer' or row.get('leader_id')!=actor.entity_id or row.get('source')!=GYM_SOURCE
                or type(row.get('gm_id'))is not str or not row['gm_id'].strip()
                or type(row.get('reason'))is not str or not row['reason'].strip()):
            raise ValueError('actual sourced GM gym adoption required')
        C.integer(row.get('encounter_epoch'),'gym encounter epoch',1)
        C.integer(row.get('leader_turn_limit'),'gym leader turn cap',1)
        epoch=getattr(engine,'_party_encounter_epoch',0)
        if row['encounter_epoch']!=epoch+(0 if engine.encounter_active else 1):
            raise ValueError('gym profile has an expired or future encounter scope')
        ids=[row['leader_id'],*row['pc_trainer_ids'],*row['gym_trainer_ids']]
        pool=row['pokemon_owners']
        if (not row['pc_trainer_ids'] or len(ids)!=len(set(ids)) or not pool
                or not set(ids)<=index.keys() or not set(pool)<=index.keys()
                or any(index[uid].kind!='trainer' or index[uid].spec.get(POLICY,{}).get('battle_mode')!='league' for uid in ids)
                or any(index[uid].kind!='pokemon' or index[uid].spec.get('trainer_id')!=owner or owner not in ids for uid,owner in pool.items())
                or set(pool.values())!=set(ids)):
            raise ValueError('gym profile must preserve actual trainer/pool identities and ownership')
        _gym_source(engine)
        if 'sample_source' in row:
            count=sum(uid==row['leader_id'] for uid in pool.values())
            if (row['sample_source']!=NICOLETTE_SOURCE or row['gym_trainer_ids'] or row['leader_turn_limit']!=count
                    or row.get('pool_guidance')!={'pc_pokemon':len(pool)-count,'gym_pokemon':count,
                        'recommended_pc_total':count*1.5,'enforced_cap':False}):
                raise ValueError('Nicolette entire-team exception or advisory pool changed')
    gym_profile(engine,entering=not engine.encounter_active)
    for actor in index.values():
        for row in actor.spec.get('party_command_turns',[]):
            if actor.kind!='trainer' or len(row['scope'])!=2 or tuple(row['scope'])>scope(engine) or row['pokemon_id'] not in index:
                raise ValueError('actual owner Pokemon turn history required')
        rows=actor.spec.get(KEY,{})
        if type(rows)is not dict:raise ValueError('identified party action ledger required')
        if not rows:continue
        if actor.kind!='trainer' or actor.spec.get(POLICY,{}).get('battle_mode') not in ('league','full_contact'):raise ValueError('party action owner and battle policy required')
        for request,row in rows.items():
            if row.get('pending'):validate_escape(engine,actor,request)
            result=row['result'];payment=result['payment']
            if result['request_id']!=request or result['actor_id']!=actor.entity_id or result['source']!=SOURCE:raise ValueError('party action receipt identity mismatch')
            if not set(result['recalled']+result['sent'])<=index.keys():raise ValueError('party receipt requires actual world Pokemon')
            if len(result['scope'])!=2 or any(type(v)is not int or v<0 for v in result['scope']) or tuple(result['scope'])>scope(engine):raise ValueError('party action scope cannot be in the future')
            if 'tag_payment' in result:
                import native_switch_transfer as SWITCH
                outgoing=index.get(result['tag_payment'].get('outgoing_id'))
                if outgoing is None:raise ValueError('prepaid Tag In lost its actual outgoing Pokemon')
                tag,_=SWITCH._prepaid_tag(engine,actor,outgoing,request)
                if tag['consumed_recall'] is None:
                    if not row.get('pending'):raise ValueError('completed party recall lost its paid Tag In occurrence')
                elif len([use for use in actor.spec.get(SWITCH.USES,[]) if use.get('recall_id')==tag['consumed_recall']
                        and use.get('prepaid_party_request')==request])!=1:
                    raise ValueError('prepaid Tag In must bind one actual recall')
            if 'source' in payment:
                plan=result.get('feature_plan')
                if plan is None or plan['source']!=payment['source'] or plan['action']!=payment['kind'] or plan['ap']!=payment['ap']:raise ValueError('actual source party action receipt required')
                if payment['ap_before']-payment['ap_after']!=plan['ap']+int(plan['tag_in']):raise ValueError('source party AP evidence disagrees with actual charges')
                if payment['phase']!='paid' or payment['kind'] not in ('free','shift'):raise ValueError('actual Juggler Free/Shift payment required')
                if not set(result['blocked_command_ids'])<=index.keys():raise ValueError('party command lock requires actual Pokemon')
                continue
            if payment['phase'] not in ('paid','reserved') or payment['kind'] not in ('standard','shift'):raise ValueError('actual paid or reserved trainer action required')
            funded={k:payment['budget_before'][k]-payment['budget_after'][k] for k in RESOURCES.KINDS if payment['budget_before'][k]!=payment['budget_after'][k]}
            if funded!=payment['funded'] or sum(funded.values())!=1 or any(v!=1 for v in funded.values()):raise ValueError('party cost evidence disagrees with actual budget')
            if not set(result['blocked_command_ids'])<=index.keys():raise ValueError('party command lock requires actual Pokemon')
    __import__('juggler').validate_world(engine,index)
    return True
