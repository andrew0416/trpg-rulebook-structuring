"""PTK training regimes and their source-owned Priority (Limited) Orders.

ch03:620,693,696-718 uses thirty minutes in the selected Korean rules.
Orders use actual communication and expire at the issuer's next turn start.
Training never silently awards experience, tutor points, or a new movement mode.
"""
from copy import deepcopy
import common_checks as C
import skill_modifiers as SKILL
import state_grants as GRANTS
import turn as TURN

TYPE = 'training_regime'
AGILITY = 'feat/민첩성-훈련'
BRUTAL = 'feat/잔혹성-훈련'
FOCUSED = 'feat/집중성-훈련'
INSPIRED = 'feat/영감성-훈련'
ELITE = 'feat/엘리트-트레이너'
ACE = 'class/에이스-트레이너'
TRAINED_STAT = 'ace_trained_stat'
ACE_SOURCES = {
    'C03-123': {'file': 'input/ch03-skills-edges-feats.md',
                'sha256': 'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23',
                'lines': [568, 570], 'requires_training_feat': True},
    'C04-009': {'file': 'input/ch04-trainer-classes.md',
                'sha256': 'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4',
                'lines': [312, 314], 'requires_training_feat': False},
}
RULES = {
    AGILITY: {'aliases': ('민첩성 훈련', 'Agility Training'), 'skills': {'육상': 3, '명령': 2}, 'bonuses': {'movement': 1, 'initiative': 4}},
    BRUTAL: {'aliases': ('잔혹성 훈련', 'Brutal Training'), 'skills': {'협박': 3, '명령': 2}, 'bonuses': {'critical': 1, 'effect': 1}},
    FOCUSED: {'aliases': ('집중성 훈련', 'Focused Training'), 'skills': {'명령': 3}, 'bonuses': {'accuracy': 1, 'skill': 2}},
    INSPIRED: {'aliases': ('영감성 훈련', 'Inspired Training'), 'skills': {'매력': 3, '명령': 2}, 'bonuses': {'evasion': 1, 'save': 2}},
}
CSV_CLAUSES = {
    AGILITY: 'C2CSV/input/db/feats.csv:R14:main',
    BRUTAL: 'C2CSV/input/db/feats.csv:R15:main',
    FOCUSED: 'C2CSV/input/db/feats.csv:R16:main',
    INSPIRED: 'C2CSV/input/db/feats.csv:R17:main',
}

def identity(name):
    if not isinstance(name, str): return None
    return next((uid for uid, policy in RULES.items() if SKILL.key(name) in {SKILL.key(x) for x in (uid, *policy['aliases'])}), None)

def _count(actor, names):
    aliases = {SKILL.key(x) for x in names}
    values = actor.spec.get('feats', [])
    if not isinstance(values, (list, tuple)): raise ValueError('actual acquired features must be a list')
    return sum(SKILL.key(x) in aliases for x in values)

def elite(actor):
    count = _count(actor, (ELITE, '엘리트 트레이너', 'Elite Trainer'))
    if not count: return False
    if count != 1 or actor.kind != 'trainer': raise ValueError('one actual Elite Trainer acquisition required')
    if actor.r._selected_rule(ELITE) != ELITE: raise ValueError('selected Elite Trainer variant needs its own policy')
    if sum(SKILL.key(x) in {SKILL.key(n) for n in ('class/에이스-트레이너', '에이스 트레이너', 'Ace Trainer')} for x in [*actor.spec.get('classes', []), *actor.spec.get('feats', [])]) != 1 or SKILL.rank(actor.r, actor, '명령')[2] < 3:
        raise ValueError('Elite Trainer requires acquired Ace Trainer with Novice Command')
    return True

def owns(actor, uid):
    count = _count(actor, (uid, *RULES[uid]['aliases']))
    if not count: return False
    if count != 1 or actor.kind != 'trainer': raise ValueError('one actual trainer feature acquisition required')
    if actor.r._selected_rule(uid) != uid: raise ValueError('selected training variant needs its own policy')
    if uid == INSPIRED:
        import trainer_feature_acquisition as TFA
        if any(active and row['static_acquisition']['feature_id'] == uid for _,row,active in TFA._static_records(actor)):
            TFA.validate_actor(actor)
            return True
    # Imported acquisition is not new character creation. The precise Elite gift
    # must be identified to apply its printed prerequisite waiver.
    gift = actor.spec.get('elite_training_choice')
    waived = gift is not None and identity(gift) == uid and elite(actor)
    if not waived and any(SKILL.rank(actor.r, actor, skill)[2] < minimum for skill, minimum in RULES[uid]['skills'].items()):
        raise ValueError('training feature prerequisite is not established: ' + uid)
    return True

def register_owned(engine, actor, name):
    uid = identity(name)
    if uid is None: return False
    owns(actor, uid)
    # Registration alone does not execute either mode or award any bonus.
    return True

def records(actor):
    return [row for row in getattr(actor, 'registry', ()) if isinstance(row, dict) and row.get('type') == TYPE]

def active(actor):
    result = []
    sources = actor.spec.get(GRANTS.KEY, {}).get('sources', {})
    for row in records(actor):
        source = row.get(GRANTS.TAG)
        receipt = sources.get(source)
        if receipt is None: raise ValueError('training projection requires its live source receipt')
        uid = row.get('rule_id')
        definition=row.get('training_reward_definition')
        if definition is not None:
            import training_rewards as REWARDS
            REWARDS.bonus_definition(definition)
            if definition['source']!=uid:raise ValueError('declared training bonus source changed')
        elif uid not in RULES:raise ValueError('known training regime required')
        if actor.r._selected_rule(uid) != uid: raise ValueError('training source selection changed')
        owner = row.get('owner')
        if owner is None or owner.entity_id != receipt.get('owner_id'): raise ValueError('training owner receipt mismatch')
        if actor.spec.get('trainer_id', owner.entity_id) != owner.entity_id or actor.spec.get('trainer', owner.name) != owner.name:
            raise ValueError('training ownership changed without source cleanup')
        mode=row.get('mode')
        if mode not in ('training','orders'): raise ValueError('unsupported Training/Orders source mode')
        if mode=='orders':
            if uid not in CSV_CLAUSES or row.get('source_clause_id')!=CSV_CLAUSES[uid]:
                raise ValueError('Training Order requires its exact CSV source clause')
            import combat_timing as TIMING
            import priority_limited as PRIORITY
            PRIORITY.validate(owner)
            if row.get('free_order_payment') is not None:
                if receipt.get('free_order_payment')!=row['free_order_payment']:
                    raise ValueError('Training Order Free payment source changed')
            else:
                payments=[payment for payment in PRIORITY.records(owner)
                          if payment['id']==row.get('order_id') and payment['source']==uid
                          and payment['subject_id']==actor.entity_id]
                if len(payments)!=1:raise ValueError('Training Order requires its exact Priority Limited payment')
            lifetime=[effect for effect in TIMING.records(actor) if effect.get('grant_source')==source]
            if len(lifetime)!=1 or lifetime[0].get('turn_owner') is not owner:
                raise ValueError('Training Order requires its live next-owner-turn lifetime')
        result.append(row)
    trained=[row for row in result if row['mode']=='training']
    ordered=[row for row in result if row['mode']=='orders']
    if len(trained) > 1 and (len(trained) > 2 or len({r['rule_id'] for r in trained}) != len(trained) or any(not r.get('elite_authority') for r in trained)):
        raise ValueError('invalid simultaneous training regimes')
    if len(ordered)>1:
        raise ValueError('multiple simultaneous Training Orders need an explicit stacking rule')
    return result

def bonuses(row):
    """Read one validated native or declared training source contribution."""
    return (row['training_reward_definition'] if 'training_reward_definition' in row else RULES[row['rule_id']])['bonuses']


def bonus(actor, field):
    import control_mount as MOUNT
    return sum(bonuses(row).get(field,0)*(MOUNT.agility_multiplier(actor) if row['rule_id']==AGILITY else 1)
               for row in active(actor))

def movement(actor, values):
    amount = bonus(actor, 'movement')
    return {key: value + amount if key in ('land', 'sky', 'levitate', 'swim', 'burrow', 'teleport') and value > 0 else value for key, value in values.items()}

def _declared_targets(engine, trainer, choices, *, allow_empty=False):
    import world_entities as WORLD
    if not isinstance(choices,(list,tuple)) or not 1<=len(choices)<=6:
        raise ValueError('one to six trained Pokemon required')
    plan=[]
    for pair in choices:
        if not isinstance(pair,(list,tuple)) or len(pair)!=2:
            raise ValueError('each target needs its selected training features')
        pokemon,names=pair
        if not isinstance(names,(list,tuple)) or (not names and not allow_empty):
            raise ValueError('selected training features required')
        uids=[identity(name) for name in names]
        if None in uids or len(set(uids))!=len(uids):
            raise ValueError('distinct known training features required')
        plan.append((pokemon,uids))
    if len({id(p) for p,_ in plan})!=len(plan):
        raise ValueError('distinct actual training targets required')
    WORLD.require_actors(engine,trainer,*[p for p,_ in plan])
    return plan


def _targets(engine, trainer, choices, *, allow_empty=False):
    import training_eligibility as E
    plan=_declared_targets(engine,trainer,choices,allow_empty=allow_empty)
    E.participants(engine,trainer,[p for p,_ in plan])
    limit=2 if elite(trainer) else 1
    for pokemon,uids in plan:
        if len(uids)>limit:raise ValueError('selected training count exceeds the actual regime limit')
        for uid in uids:
            if not owns(trainer,uid):raise ValueError('trainer does not own selected training feature')
        if uids:
            for old in active(pokemon):
                if old['mode']=='training':GRANTS.preflight_revoke(pokemon,old[GRANTS.TAG])
    return plan


def _ace_source(rules, clause_id):
    from source_context import verified_source
    if type(clause_id) is not str or clause_id not in ACE_SOURCES:raise ValueError('exact reviewed Ace Trainer book source required')
    if rules._selected_rule(ACE)!=ACE or any(uid in rules.ruleset.unit_versions for uid in (ACE,clause_id)):
        raise ValueError('selected Ace Trainer variant requires its own reviewed policy')
    source=ACE_SOURCES[clause_id]
    rules.ruleset.require({'id':clause_id,'source':{'file':source['file'].removeprefix('input/'),'lines':source['lines']}})
    verified_source(rules,source,label='Ace Trainer')
    return source


def stat_records(actor):
    return [row for row in getattr(actor,'registry',()) if isinstance(row,dict) and row.get('type')==TRAINED_STAT]


def validate_trained(actor, actors=None):
    import combat_stage_sources as CS
    rows=stat_records(actor)
    if len(rows)>1:raise ValueError('one trained non-HP stat per Pokemon required')
    sources=actor.spec.get(GRANTS.KEY,{}).get('sources',{})
    tags=[row.get(GRANTS.TAG) for row in rows]
    if (any(type(tag) is not str or not tag for tag in tags)
            or {key for key,receipt in sources.items() if receipt.get('kind')==TRAINED_STAT}!=set(tags)):
        raise ValueError('trained stat source and recipient row must correspond exactly')
    for row in rows:
        source=row.get(GRANTS.TAG);owner=row.get('owner');stat=row.get('stat')
        if type(source) is not str or not source:raise ValueError('trained stat requires its actual source identity')
        receipt=sources.get(source,{})
        _ace_source(actor.r,row.get('source_clause_id'))
        if (actor.kind!='pokemon' or stat not in CS.STATS or getattr(owner,'kind',None)!='trainer'
                or (actors is not None and actors.get(owner.entity_id) is not owner)
                or any(receipt.get(key)!=value for key,value in {'kind':TRAINED_STAT,'owner_id':owner.entity_id,
                    'rule_id':ACE,'source_clause_id':row['source_clause_id'],'stat':stat,'lifetime':'recipient_extended_rest'}.items())):
            raise ValueError('trained stat lost its actual source, recipient or training owner')
        session_id=row.get('session')
        session=owner.custom_conditions.get('_training_sessions',{}).get(session_id,{}) if type(session_id) is str else {}
        expected={'pokemon_id':actor.entity_id,'stat':stat,'source':source,'source_clause_id':row['source_clause_id']}
        if (session.get('request_id')!=session_id or session.get('trainer')!=owner.entity_id
                or session.get('trained_stat_sources',[]).count(expected)!=1):
            raise ValueError('trained stat requires its actual completed training session source')
        state=CS.validate(actor)
        if (state is None or state['base'].get(source)!={'source':ACE,'ends':source,'deltas':{stat:1}}
                or actor.spec[GRANTS.KEY]['effects'].get(source)!={'rows':['registry'],'listeners':[],'stages':True}):
            raise ValueError('trained stat requires its exact source-owned base stage')
    return rows


def _stat_choices(trainer, plan, clause_id):
    import acquired_features as ACQUIRED
    import action_points as AP
    source=_ace_source(trainer.r,clause_id)
    if (trainer.kind!='trainer' or not any(row['source_id']==ACE for row in ACQUIRED.class_instances(trainer))
            or SKILL.rank(trainer.r,trainer,'명령')[2]<3):
        raise ValueError('Ace Trainer requires actual class acquisition and Novice Command')
    if source['requires_training_feat'] and not any('훈련' in trainer.r.selection.units[row['source_id']].get('tags',[])
            for row in ACQUIRED.feature_instances(trainer)):
        raise ValueError('C03-123 requires an actual acquired Training feature')
    if AP.available(trainer)<1:raise ValueError('Ace Trainer requires one available AP to drain')
    for target,_ in plan:
        for old in validate_trained(target):GRANTS.preflight_revoke(target,old[GRANTS.TAG])


def _grant_stats(engine, trainer, targets, trained_stats, clause_id, request_id):
    import combat_stage_sources as CS
    applied=[]
    for target in targets:
        for old in list(stat_records(target)):GRANTS.revoke(target,old[GRANTS.TAG],engine=engine)
        source='trained-stat:'+trainer.entity_id+':'+request_id+':'+target.entity_id
        stat=trained_stats[target.entity_id]
        GRANTS._source(target,source,TRAINED_STAT,owner_id=trainer.entity_id,rule_id=ACE,
            source_clause_id=clause_id,stat=stat,lifetime='recipient_extended_rest',tutor_points=0)
        row={'type':TRAINED_STAT,'owner':trainer,'stat':stat,'source_clause_id':clause_id,'session':request_id}
        GRANTS.apply_owned(engine,target,source,lambda target=target,row=row:target.registry.append(row))
        CS.add_base(target,source,stat,1,source=ACE,ends=source)
        target.spec[GRANTS.KEY]['effects'][source]['stages']=True
        applied.append({'pokemon_id':target.entity_id,'stat':stat,'source':source,'source_clause_id':clause_id})
    return applied


def train(engine, trainer, choices, *, minutes, reason, request_id, from_grooming=False, from_training=False, safe=None,
          trained_stats=None, source_clause_id=None):
    """Perform a real Extended training session with exact per-Pokemon choices.

    The caller supplies the GM's observation of the actual training activity,
    while the engine advances its elapsed clock and records its participants.
    """
    from resolution_transaction import request_fingerprint, replay_result
    import movement_actions as MOVEMENT
    import downtime as DT
    if not isinstance(reason, str) or not reason.strip(): raise ValueError('actual training observation reason required')
    if not isinstance(request_id, str) or not request_id.strip(): raise ValueError('training request identity required')
    C.integer(minutes, 'training minutes', 30)
    import pokemon_teaching as TEACHING
    TEACHING.credit_mode(from_grooming,from_training)
    has_stats=trained_stats is not None
    plan = _declared_targets(engine, trainer, choices,allow_empty=has_stats)
    if has_stats:
        import combat_stage_sources as CS
        if (type(trained_stats) is not dict or set(trained_stats)!={p.entity_id for p,_ in plan}
                or any(type(stat) is not str or stat not in CS.STATS for stat in trained_stats.values())):
            raise ValueError('each actual trained Pokemon needs exactly one non-HP trained stat')
    elif source_clause_id is not None:raise ValueError('Ace Trainer source requires selected trained stats')
    payload = {'trainer': trainer.entity_id, 'targets': [(p.entity_id, uids) for p, uids in plan], 'minutes': minutes, 'reason': reason}
    if has_stats:payload.update(trained_stats=dict(trained_stats),source_clause_id=source_clause_id)
    if from_grooming:payload['from_grooming']=True
    if from_training:payload['from_training']=True
    if safe is not None:payload['safe']=safe
    signature = request_fingerprint(payload)
    prior = replay_result(trainer.custom_conditions.get('_training_sessions', {}),request_id,payload,fingerprint_field='payload_sha256')
    if prior is not None:return prior
    if engine.encounter_active: raise ValueError('Extended training must occur outside combat')
    MOVEMENT.boundary(engine, 'training_feature')
    plan = _targets(engine, trainer, choices,allow_empty=has_stats)
    if has_stats:_stat_choices(trainer,plan,source_clause_id)
    import training_eligibility as E
    eligibility=E.prepare(engine,trainer,[p for p,_ in plan],E.native('training_regime',seconds=minutes*60),
                          safe=safe,from_grooming=from_grooming,from_training=from_training)
    credits=eligibility['completed_training_credits']
    if not (from_grooming or from_training):
        engine.preflight_advance_time(minutes * 60, [trainer, *[p for p, _ in plan]])
    def apply(e, owner, *targets):
        if not TURN.spend(e, owner, 'extended', 'training features'): raise ValueError('Extended training action is unavailable')
        if has_stats:
            import action_points as AP
            AP.charge(owner,1,mode='drain')
        started = e.elapsed_seconds
        for actor in (owner, *targets): DT.interrupt_rest(actor)
        if not (from_grooming or from_training):
            import activity_jobs as JOBS
            JOBS.run_fixed(e,owner,targets,seconds=minutes*60,source='training/features',
                context={'safe':True,'reason':reason},job_id='training-regime:'+owner.entity_id+':'+request_id)
        import training_rewards as REWARDS
        applied=REWARDS.grant_regimes(e,owner,targets,plan,request_id=request_id,started_at=started)
        receipt = {**payload, 'request_id': request_id, 'payload_sha256': signature, 'started_at': started,
                   'completed_at': e.elapsed_seconds, 'target_ids': [p.entity_id for p in targets], 'sources': applied,'eligibility':deepcopy(eligibility)}
        if has_stats:
            receipt['trained_stat_sources']=_grant_stats(e,owner,targets,trained_stats,source_clause_id,request_id)
            receipt['ap_removed']=1
        if from_grooming or from_training:
            for target in targets:TEACHING.consume_credit(target,'training_regime',**({'from_training':True} if from_training else {}))
            receipt.update(time_cost_seconds=0,completed_training_credits=deepcopy(credits))
        owner.custom_conditions.setdefault('_training_sessions', {})[request_id] = receipt
        e.gm._rec('Training session', None, deepcopy(receipt), reason, owner)
        return deepcopy(receipt)
    return GRANTS.transition(engine, trainer, apply, participants=[p for p, _ in plan])

def extended_rest(engine, trainer):
    # Ace training belongs to the recipient's rest, independently of trainer AP recovery.
    for row in list(stat_records(trainer)):
        GRANTS.revoke(trainer,row[GRANTS.TAG],engine=engine)
    # Target rest alone does not end a trainer-owned training session.
    for target in engine.time_actors():
        for row in list(records(target)):
            if row.get('owner') is trainer and row.get('mode')=='training':
                GRANTS.revoke(target, row[GRANTS.TAG], engine=engine)

def orders(engine, trainer, name, target):
    """Issue one owned Training feature as a Standard Priority (Limited) order."""
    import world_entities as WORLD
    import pokemon_activities as ACTIVITIES
    import priority_limited as PRIORITY
    import perception_communicate as COMM
    import combat_timing as TIMING
    import order_actions as ORDERS
    uid=identity(name)
    if uid is None: raise ValueError('known training feature required')
    WORLD.require_actors(engine,trainer,target)
    ACTIVITIES._trainer(trainer);owns(trainer,uid)
    if target is not trainer:
        ACTIVITIES._pokemon(target);ACTIVITIES._owner(trainer,target)
        if target.dead or target.fainted:raise ValueError('conscious order recipient required')
    if ORDERS.current(engine,trainer,uid) is None:PRIORITY.preflight(engine,trainer,action='standard',source=uid)
    if any(row.get('mode')=='orders' for row in records(target)):
        raise ValueError('target already has a live Training Order')
    def apply(e,owner,recipient):
        if recipient is owner:
            communication={'status':'delivered','mode':'self_target_exception','source_clause_id':CSV_CLAUSES[uid],
                           'sender_id':owner.entity_id,'recipient_id':recipient.entity_id}
        else:
            policy={'id':'training-order:'+uid,'source':uid,'capabilities':[],'requirements':[],
                    'mode':'auditory','range':None,'path':'auditory','medium':[],
                    'consent':{'kind':'none'},'blockers':[],'connection':None,
                    'frequency':{'kind':'at_will','uses':1},'retry':None,'distance_exceptions':[]}
            state=getattr(e,COMM.KEY,{'attempts':[]})
            request='training-order:'+owner.entity_id+':'+str(len(state.get('attempts',[]))+1)
            communication=COMM.send(e,owner,recipient,policy,'Training Order: '+uid,request_id=request)
            if communication['status']!='delivered':
                raise ValueError('Training Order communication was not delivered: '+str(communication.get('reason')))
        if ORDERS.current(e,owner,uid) is not None:
            import turn as TURN
            if not TURN.spend(e,owner,'standard',uid):raise ValueError('Free Training Order permission required')
            free=ORDERS.payment(e,owner,uid)
            receipt={'id':'free-order:'+free['parent'],'payment':free}
        else:
            free=None
            receipt=PRIORITY.reserve(e,owner,action='standard',source=uid,subject=recipient.entity_id,
                                     communication=communication)
        serial=C.integer(owner.custom_conditions.get('_training_order_serial',0),'Training Order serial',0)+1
        owner.custom_conditions['_training_order_serial']=serial
        source='training-order:'+owner.entity_id+':'+str(serial)+':'+recipient.entity_id+':'+uid
        GRANTS._source(recipient,source,'training_order',owner_id=owner.entity_id,
                       lifetime='start_of_issuer_next_turn',rule_id=uid,tutor_points=0)
        if free is not None:GRANTS.state(recipient)['sources'][source]['free_order_payment']=deepcopy(free)
        row={'type':TYPE,'rule_id':uid,'source_clause_id':CSV_CLAUSES[uid],'mode':'orders','owner':owner,
             'order_id':receipt['id'],'elite_authority':False,'started_at':e.elapsed_seconds,
             'started_round':e.round_no}
        if free is not None:row['free_order_payment']=free
        GRANTS.apply_owned(e,recipient,source,lambda row=row,recipient=recipient:recipient.registry.append(row))
        deadline=C.integer(owner.custom_conditions.get('combat_turn_serial',0),'actual owner turn serial',0)+1
        TIMING.install(e,recipient,{'source':uid,'effect_contract':True,'grant_source':source,
                                    'turn_owner':owner,'turn_start_deadline':deadline})
        result={'status':'applied','rule_id':uid,'source_clause_id':CSV_CLAUSES[uid],
                'source':source,'trainer_id':owner.entity_id,'target_id':recipient.entity_id,
                'priority_receipt':deepcopy(receipt),'expires_at_owner_turn':deadline,
                'communication':deepcopy(communication)}
        e.gm._rec('Training Order',None,result,'actual delivered Priority (Limited) order',owner)
        import cheerleader as CHEER
        CHEER.after_training(e,owner,recipient,result)
        import duelist as DUELIST
        DUELIST.after_order(e,owner,[recipient],{'kind':'training','receipt_id':receipt['id']})
        return deepcopy(result)
    return GRANTS.transition(engine,trainer,apply,participants=(target,),include_rulings=True)
