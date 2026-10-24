"""Taskmaster's real training trigger and current injury-dependent benefits.

Hardened is a result of the Class trigger, not another Training regime.  The
printed Class gives it no rest deadline; its source is the actual owning Class.
"""
from copy import deepcopy
from functools import wraps
import common_checks as C
import state_grants as G

CLASS='class/감독관'
PAIN='feat/고통-저항'
PRESS='feat/밀고나가'
QUICK='feat/빠른-치유'
SAVAGE='feat/야만적-타격'
WHIP='feat/채찍질'
DESPERATE='feat/절망적-타격'
GAMBIT='feat/치명적인-장기말'
PRESS_ACTION='feat/압박'
CRUELTY='ability/잔인'
# Class definitions describe available choices. Acquisitions remain independent
# owned instances in trainer_feature_acquisition/acquired_features.
DEFINITIONS={
 CLASS:{'span':(961,963),'parents':['feat/잔혹성-훈련'],'rank':3,'action':'free','parameters':{'injuries':[0,3]}},
 QUICK:{'span':(965,971),'parents':[CLASS],'rank':0,'action':'extended','parameters':{'injuries':[0,3],'ticks_per_injury':2}},
 SAVAGE:{'span':(973,977),'parents':[CLASS],'rank':0,'action':'extended','parameters':{'tutor_points':2,'ability':CRUELTY}},
 WHIP:{'span':(979,986),'parents':[CLASS,PRESS_ACTION],'rank':0,'action':'swift','parameters':{'options':['injury','cure','order'],'cure_ap':1}},
 PAIN:{'span':(988,992),'parents':[CLASS],'rank':4,'action':'free','parameters':{'ap':1,'per_pokemon_scene':1}},
 PRESS:{'span':(994,1002),'parents':[CLASS],'rank':5,'action':'static','parameters':{'ap':1,'faint_percent':-30}},
 DESPERATE:{'span':(1004,1008),'parents':[SAVAGE],'rank':5,'action':'free','parameters':{'scene':2,'per_pokemon_scene':1}},
 GAMBIT:{'span':(1010,1017),'parents':[CLASS],'rank':6,'action':'free','parameters':{'class_features':5,'scene':1}},
}
FEATURES={uid:row['span'] for uid,row in DEFINITIONS.items()}
KIND='taskmaster_hardened'


def acquisitions(actor,feature,active=False):
    import trainer_feature_acquisition as T
    return [row['static_acquisition'] for _,row,live in T._static_records(actor)
            if row['static_acquisition']['feature_id']==feature and (live or not active)]


def acquired(actor,feature=CLASS):
    import acquired_features as A,trainer_feature_acquisition as T
    if not A.owned_rule_count(actor,feature):return None
    T.validate_actor(actor)
    rows=acquisitions(actor,feature,True)
    if actor.kind!='trainer' or A.owned_rule_count(actor,feature)!=1 or len(rows)!=1:
        raise ValueError('one actual source-specific Taskmaster acquisition required')
    if feature!=CLASS and acquired(actor) is None:raise ValueError('actual acquired Taskmaster prerequisite required')
    return rows[0]


def acquisition_snapshot(actor,feature):
    import training_features as F,skill_modifiers as S,acquired_features as A
    if feature==CLASS:
        if not F.owns(actor,F.BRUTAL):raise ValueError('actual Brutal Training prerequisite required')
        parent=F.BRUTAL
    else:
        row=acquired(actor)
        if row is None:raise ValueError('actual acquired Taskmaster prerequisite required')
        parent=row['request_id']
    result={'parent':parent,'intimidate':S.rank(actor.r,actor,'협박')[2]}
    if feature not in (CLASS,PAIN,PRESS):
        parents=DEFINITIONS[feature]['parents']
        result['parents']={uid:(acquired(actor,uid)['request_id'] if uid in FEATURES else uid)
                           for uid in parents if A.owned_rule_count(actor,uid)}
        if feature==GAMBIT:
            result['class_features']=[row['request_id'] for uid in FEATURES if uid!=GAMBIT
                                      for row in acquisitions(actor,uid,True)]
    return result


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q,training_features as F
    fields={'parent','intimidate'} | ({'parents'} if feature not in (CLASS,PAIN,PRESS) else set()) | ({'class_features'} if feature==GAMBIT else set())
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields:
        raise ValueError('exact Taskmaster acquisition observations required')
    C.integer(snapshot['intimidate'],'Taskmaster Intimidate',0)
    if feature==CLASS:
        if snapshot['parent']!=F.BRUTAL:raise ValueError('Brutal Training prerequisite identity changed')
    elif len([r for r in acquisitions(actor,CLASS) if r['request_id']==snapshot['parent']])!=1:
        raise ValueError('historical Taskmaster prerequisite required')
    if 'parents' in snapshot:
        if set(snapshot['parents'])!=set(DEFINITIONS[feature]['parents']):raise ValueError('printed Taskmaster prerequisites required')
        for uid,request in snapshot['parents'].items():
            if uid in FEATURES and not any(row['request_id']==request for row in acquisitions(actor,uid)):
                raise ValueError('actual historical prerequisite acquisition required')
            if uid not in FEATURES and request!=uid:raise ValueError('prerequisite identity changed')
    if feature==GAMBIT:
        actual={row['request_id'] for uid in FEATURES if uid!=GAMBIT for row in acquisitions(actor,uid)}
        if len(set(snapshot['class_features']))<DEFINITIONS[GAMBIT]['parameters']['class_features'] or not set(snapshot['class_features'])<=actual:
            raise ValueError('five actual acquired Taskmaster Features required')
    return Q.require(feature,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('intimidate','prerequisite',snapshot['intimidate']>=DEFINITIONS[feature]['rank'],
                'printed Intimidate rank required')])


def records(actor):
    return [r for r in getattr(actor,'registry',()) if r.get('type')==KIND]


def active(actor):
    rows=records(actor)
    if len(rows)>1:raise ValueError('one actual Hardened source per Pokemon required')
    if not rows:return None
    row=rows[0];owner=row.get('owner');source=row.get(G.TAG)
    receipt=actor.spec.get(G.KEY,{}).get('sources',{}).get(source,{})
    if (actor.kind!='pokemon' or getattr(owner,'kind',None)!='trainer'
            or receipt.get('kind')!=KIND or receipt.get('owner_id')!=owner.entity_id
            or receipt.get('rule_id')!=CLASS or acquired(owner) is None
            or actor.spec.get('trainer_id')!=owner.entity_id):
        raise ValueError('Hardened requires its actual owned Class and recipient source')
    return row


def _injury(engine,target,amount,source):
    import actor_templates as TEMPLATES,precise_actions as PRECISE
    if TEMPLATES.injuries_immune(target):return 0
    before=target.injuries
    if amount:PRECISE.gain_injury(engine,target,amount,source)
    return target.injuries-before


def training(engine,owner,target,*,session,training_source):
    """Only grant_regimes calls this after actually applying Brutal Training."""
    import action_lifecycle as ACTION
    receipt=acquired(owner)
    if receipt is None:return None
    choice=engine.rulings.decide({'type':'taskmaster','unit':CLASS,'actor':owner.name,
        'target':target.name,'text':'Use Taskmaster? Choose 0 to 3 injuries, or decline with false.',
        'session':session,'injuries':target.injuries})
    if choice is None or choice is False:return None
    C.integer(choice,'Taskmaster injury grant',*DEFINITIONS[CLASS]['parameters']['injuries'])
    ACTION.triggered_free_action(engine,owner,CLASS)
    before=target.injuries
    granted=_injury(engine,target,choice,CLASS)
    after=target.injuries
    result={'injuries_granted':granted,'before':before,'after':after,'hardened':after>=1}
    if after>=1:
        for old in list(records(target)):G.revoke(target,old[G.TAG],engine=engine)
        source='hardened:'+owner.entity_id+':'+target.entity_id
        G._source(target,source,KIND,owner_id=owner.entity_id,rule_id=CLASS,
            acquisition_request=receipt['request_id'],session=session,training_source=training_source,
            lifetime='your_pokemon',tutor_points=0)
        row={'type':KIND,'owner':owner,'session':session,'training_source':training_source,
             'training_result':deepcopy(result),'press_on':False}
        G.apply_owned(engine,target,source,lambda:target.registry.append(row))
        # A completed, durationless Pokemon effect is a used permanent-effect
        # Feature under Core's retraining prohibition, even after transfer ends
        # this particular owner's contribution.
        import trainer_retraining as RETRAIN
        RETRAIN.irreversible(engine,owner,CLASS,event_id='hardened:'+session+':'+target.entity_id,
            reason='applied permanent Hardened result to own Pokemon')
    # We are already inside the completed training transaction; its receipt is
    # written by the caller before the world validation at commit.
    import life as LIFE
    LIFE.sync(engine,target)
    return result


def bonus(actor,field):
    row=active(actor)
    if row is None:return 0
    minimum,amount={'critical':(1,1),'effect':(1,1),'evasion':(3,1),'initiative':(3,5),
                    'dr':(5,5),'resistance':(9,1)}[field]
    if actor.injuries<minimum:return 0
    import skill_modifiers as S
    doubled=(conscious(actor) and actor.hp<=0 and acquired(row['owner'],PRESS) is not None
             and S.rank(actor.r,row['owner'],'협박')[2]>=6)
    return amount*(2 if doubled else 1)


def injury_ceiling(actor):return min(actor.injuries,5) if active(actor) else actor.injuries
def ignores_acting_loss(actor):
    import style_expert as STYLE
    return active(actor) is not None or STYLE.endurance_active(actor)
def immune_loss(actor):return actor.injuries>=7 and active(actor) is not None


def conscious(actor, *, hp=None):
    """An actual paid Press On changes the native faint threshold, never death."""
    if actor.dead or '기절' in actor.conditions:return False
    current_hp=actor.hp if hp is None else hp
    if current_hp>0:return True
    rows=records(actor)
    if not rows or rows[0].get('press_on') is not True or 100*current_hp<=DEFINITIONS[PRESS]['parameters']['faint_percent']*actor.base_max_hp:return False
    import actor_templates as T
    return not T.soulless(actor) and active(actor) is not None and acquired(rows[0]['owner'],PRESS) is not None


def press_interested(actor):
    row=active(actor)
    return row is not None and acquired(row['owner'],PRESS) is not None


def move_interested(engine,attacker,target):
    if active(attacker) is not None or active(target) is not None:return True
    import world_entities as W,ability_transitions as AB
    if AB.active(attacker,CRUELTY):return True
    index=W.actor_index(engine)
    for pokemon in (attacker,target):
        owner=index.get(pokemon.spec.get('trainer_id'))
        if owner is not None and any(acquired(owner,uid) is not None for uid in (PAIN,DESPERATE,GAMBIT)):return True
    return False


def faint_boundary(engine,actor):
    """Called by life.sync before faint's irreversible status consequences."""
    row=active(actor)
    if row is None:return False
    if actor.hp>0:
        row['press_on']=False
        return False
    if conscious(actor):return True
    import actor_templates as T,action_points as AP
    if (actor.dead or '기절' in actor.conditions or T.soulless(actor)
            or 100*actor.hp<=DEFINITIONS[PRESS]['parameters']['faint_percent']*actor.base_max_hp or acquired(row['owner'],PRESS) is None):
        row['press_on']=False
        return False
    owner=row['owner']
    if AP.available(owner)<DEFINITIONS[PRESS]['parameters']['ap']:return False
    choice=engine.rulings.decide({'type':'press_on','unit':PRESS,'actor':owner.name,'target':actor.name,
        'text':'Pay 1 AP to faint at -30% HP instead?', 'hp':actor.hp,'maximum_hp':actor.base_max_hp})
    if choice is not None and type(choice) is not bool:raise ValueError('explicit Press On use or decline required')
    if choice is not True:return False
    AP.charge(owner,DEFINITIONS[PRESS]['parameters']['ap'])
    row['press_on']=True
    return True


def move_permission(actor,move_id):
    if actor.hp<=0 and move_id in {'move/대폭발','move/버티기','move/아픔나누기','move/자폭'}:
        raise ValueError('Explosion, Endure, Pain Split and Self-Destruct cannot be used at nonpositive HP')


def pain_reduction(engine,attacker,target,move,event):
    """Read the real attack before defense/DR subtraction; no post-hit refund."""
    if event is None or target.kind!='pokemon' or target.injuries<1:return 0
    import world_entities as W,frequency as F,action_points as AP,action_lifecycle as ACTION
    import turn as TURN,body_modes as BODY
    owner=W.actor_index(engine).get(target.spec.get('trainer_id'))
    if owner is None or acquired(owner,PAIN) is None:return 0
    quota={'kind':'scene','uses':DEFINITIONS[PAIN]['parameters']['per_pokemon_scene']};key=PAIN+':'+target.entity_id
    if (AP.available(owner)<DEFINITIONS[PAIN]['parameters']['ap'] or not F.activation_allowed(owner,key,quota,engine=engine)
            or not TURN.can_act(engine,owner) or not ACTION.status_permission(engine,owner,'free',new_action=True)
            or not BODY.permits(owner,'free')):return 0
    amount=engine.tick(target)*target.injuries
    choice=engine.rulings.decide({'type':'pain_resistance','unit':PAIN,'actor':owner.name,'target':target.name,
        'attacker':attacker.name,'move':move['id'],'text':'Pay 1 AP for Pain Resistance against this attack?',
        'injuries':target.injuries,'damage_reduction':amount})
    if choice is not None and type(choice) is not bool:raise ValueError('explicit Pain Resistance use or decline required')
    if choice is not True:return 0
    ACTION.triggered_free_action(engine,owner,PAIN);AP.charge(owner,DEFINITIONS[PAIN]['parameters']['ap'])
    F.consume_activation(owner,key,quota,engine=engine)
    event['pain_resistance']={'owner':owner.entity_id,'reduction':amount,'injuries':target.injuries}
    return amount


def _owner(engine,owner,target,feature):
    import world_entities as W,pokemon_activities as P
    W.require_actors(engine,owner,target);P._trainer(owner);P._pokemon(target);P._owner(owner,target)
    if acquired(owner,feature) is None:raise ValueError('actual acquired Taskmaster Feature required')


def extended(engine,owner,target,feature,*,seconds,reason,injuries=None,request_id):
    """Public typed actions; the existing job clock and recovery/payment owners execute them."""
    import turn as TURN,activity_jobs as JOBS,pokemon_activities as P
    C.integer(seconds,'GM-established Extended duration',1)
    for value in (reason,request_id):
        if type(value) is not str or not value.strip():raise ValueError('Extended reason and request identity required')
    if feature not in (QUICK,SAVAGE):raise ValueError('Quick Healing or Savage Strike required')
    if feature==QUICK:C.integer(injuries,'Quick Healing injury selection',*DEFINITIONS[QUICK]['parameters']['injuries'])
    elif injuries is not None:raise ValueError('Savage Strike has no injury selection')
    def apply(e,pupil,trainer):
        _owner(e,trainer,pupil,feature);P._outside(e)
        worker=pupil if feature==QUICK else trainer
        if feature==QUICK and active(pupil) is None:raise ValueError('your actual Hardened Pokemon required')
        if not TURN.spend(e,worker,'extended',feature):raise ValueError('actual Extended action permission required')
        job='taskmaster:'+trainer.entity_id+':'+request_id
        JOBS.run_fixed(e,worker,tuple(c for c in (trainer,pupil) if c is not worker),seconds=seconds,
            source=feature,job_id=job,context={'target_id':pupil.entity_id,'reason':reason})
        _owner(e,trainer,pupil,feature)
        if feature==QUICK:
            import injury_recovery as INJURY
            if active(pupil) is None:raise ValueError('Hardened source ended during Quick Healing')
            removed=INJURY.heal(e,pupil,injuries,source=QUICK)
            gained=e.heal(pupil,DEFINITIONS[QUICK]['parameters']['ticks_per_injury']*e.tick(pupil)*removed,source_kind='feature')
            return {'source':feature,'job_id':job,'injuries_removed':removed,'hp_result':gained}
        import grant_payments as PAYMENTS,pokemon_teaching as TEACH,trainer_retraining as RETRAIN
        cruelty_definition(e.r)
        price=DEFINITIONS[SAVAGE]['parameters']['tutor_points']
        if TEACH._balance(pupil.spec)<price:raise ValueError('Savage Strike requires two actual Tutor Points')
        group=job+':lesson';source=group+':ability'
        result=PAYMENTS.acquire(e,pupil,group,[{'source_id':source,'field':'abilities','value':DEFINITIONS[SAVAGE]['parameters']['ability']}],price,
            rule_id=SAVAGE,reason=reason,owner_id=trainer.entity_id,lifetime='your_pokemon')
        RETRAIN.irreversible(e,trainer,SAVAGE,event_id=job,reason='completed permanent Cruelty Ability lesson')
        return {'source':feature,'job_id':job,'ability':CRUELTY,'payment':result}
    return G.transition(engine,target,apply,participants=(owner,),include_rulings=True)


def press(engine,owner,target,*,stats,obedience=False,whip=None):
    """Press is a real Standard action; Whip observes this successful use only."""
    import acquired_features as A,skill_modifiers as S,turn as TURN
    import pokemon_activities as P,combat_timing as TIMING
    if type(stats) not in (tuple,list) or len(stats)!=2 or len(set(stats))!=2 or any(x not in ('atk','def','spa','spd','spe') for x in stats):
        raise ValueError('choose two distinct combat Stats for Press')
    if type(obedience) is not bool:raise ValueError('explicit Press obedience choice required')
    if whip is not None and (type(whip) is not dict or not whip or set(whip)-set(DEFINITIONS[WHIP]['parameters']['options'])):
        raise ValueError('one or more explicit Strike of the Whip effects required')
    def apply(e,trainer,pupil):
        import action_lifecycle as ACTION
        P._trainer(trainer);P._pokemon(pupil);P._owner(trainer,pupil)
        if not A.owned_rule_count(trainer,PRESS_ACTION) or S.rank(e.r,trainer,'협박')[2]<4:
            raise ValueError('actual Press and Adept Intimidate required')
        if pupil.fainted:raise ValueError('conscious Press target required')
        parent=None
        with ACTION.resolution(e,trainer,PRESS_ACTION,kind='feature'):
            if not TURN.spend(e,trainer,'standard',PRESS_ACTION):raise ValueError('Press requires Standard action permission')
            e.lose_hp(pupil,max(1,pupil.base_max_hp//6),PRESS_ACTION)
            if '잠듦' in pupil.conditions:e.cure_status(pupil,'잠듦')
            for stat in stats:e.change_stage(pupil,stat,1)
            if obedience:
                TIMING.install(e,trainer,{'source':PRESS_ACTION,'press_target':pupil.entity_id,
                    'press_obedience':S.effective_rank(e.r,trainer,'협박')//2,'round_end_deadline':e.round_no})
            if whip is not None and whip.get('order') is not None:
                order=whip['order'];feature=order if isinstance(order,str) else order['feature']
                if feature not in e.r.selection.units:feature=e.r.selection.resolve_name(feature,('feat/',))
                parent=ACTION.observe_resolution(e,trainer,PRESS_ACTION,{'press_target':pupil.entity_id,'whip_order':feature})
                # This fact observes the native Press just performed. Other
                # actual Stamina/Confusion triggers retain their own finishers.
                next(t for t in parent['triggers'] if t['actor'] is trainer and t['source']==PRESS_ACTION)['status']='completed'
        if whip is not None:
            _owner(e,trainer,pupil,WHIP)
            if any(type(whip.get(x,False)) is not bool for x in ('injury','cure')):raise ValueError('explicit Whip injury/cure choices required')
            if not any(whip.values()):raise ValueError('Whip must select at least one effect')
            if not TURN.spend(e,trainer,'swift',WHIP):raise ValueError('Whip requires an actual Swift action')
            if whip.get('injury'):
                import temporary_hp as TEMP
                _injury(e,pupil,1,WHIP);e.check_fainted(pupil)
                TEMP.grant(e,pupil,e.tick(pupil),provenance={'source':WHIP})
            if whip.get('cure'):
                import action_points as AP
                AP.charge(trainer,DEFINITIONS[WHIP]['parameters']['cure_ap'])
                for condition in ('혼란','헤롱헤롱','난동','억압'):
                    if condition in pupil.conditions:e.cure_status(pupil,condition)
            if whip.get('order') is not None:
                import order_actions as ORDERS
                ORDERS.execute(e,trainer,pupil,order,source=WHIP,parent=parent['id'])
        return {'source':PRESS_ACTION,'stats':list(stats),'obedience':obedience,'whip':deepcopy(whip)}
    return G.transition(engine,owner,apply,participants=(target,),include_rulings=True)


def is_obedience_context(context):
    """Recognize the native check purpose without granting a Press bonus."""
    if not isinstance(context,dict) or context.get('purpose')!='pokemon_obedience':return False
    if set(context) not in ({'purpose'},{'purpose','reason'}):
        raise ValueError('Press obedience context requires purpose and optional reason')
    if 'reason' in context:G._text(context['reason'],'Press obedience observation reason')
    return True


def obedience_bonus(engine,actor,context,target):
    import combat_timing as TIMING,world_entities as WORLD
    if not is_obedience_context(context) or target is None:return 0
    WORLD.require_actors(engine,actor,target)
    if target.kind!='pokemon':raise ValueError('Press obedience checks require an actual Pokemon target')
    return max([r['press_obedience'] for r in TIMING.records(actor)
        if r.get('source')==PRESS_ACTION and r.get('press_target')==target.entity_id]+[0])


def cruelty_definition(rules):
    import pokemon_teaching as TEACH
    TEACH.source(rules,CRUELTY)
    rules.selection.require_supported_version(CRUELTY)
    raw={'type':'custom_condition','condition':'잔인 회복 봉쇄'}
    return {'raw':raw,'payload':{'kind':'custom_condition','condition':'잔인 회복 봉쇄',
        'class':'healing_block','operation':'healing_gain_block'},'recipient':'effect_target',
        'lifetime':{'boundary':'explicit_healing_block_end','ends_on':['replacement','breather','encounter_end']}}


def _side(actor):return getattr(actor,'side',None)


def prepare_gambit(engine,attacker,target,move):
    """Native selected target occurrence, before its accuracy is resolved."""
    if getattr(engine,'_taskmaster_gambit',None) is not None:return
    import weapon_actions as WEAPONS,world_entities as W,frequency as F,action_lifecycle as ACTION
    if target.kind!='pokemon' or target.fainted or _side(attacker) is None or _side(target) is None or _side(attacker)==_side(target) or move['class'] not in ('물리','특수'):
        return
    if WEAPONS.range_spec(engine,move,attacker).get('origin')!='melee':return
    owner=W.actor_index(engine).get(target.spec.get('trainer_id'))
    quota={'kind':'scene','uses':DEFINITIONS[GAMBIT]['parameters']['scene']}
    if owner is None or acquired(owner,GAMBIT) is None or not F.activation_allowed(owner,GAMBIT,quota,engine=engine):return
    choice=engine.rulings.decide({'type':'deadly_gambit','unit':GAMBIT,'actor':owner.name,'target':target.name,
        'foe':attacker.name,'move':move['id'],'text':'Use Deadly Gambit? Choose counter Move (or null) and whether to roll for effects.'})
    if choice is None or choice is False:return
    if type(choice) is not dict or set(choice) not in ({'move','roll_effects'},{'move','roll_effects','options'}) or type(choice['roll_effects']) is not bool:
        raise ValueError('explicit Deadly Gambit counter and effect-roll choices required')
    counter=choice['move']
    options=choice.get('options',{})
    if type(options) is not dict or set(options)-{'weapon_id','struggle_choice','appendage_id','origin_part','set_damage','versatile_stat'}:
        raise ValueError('native Deadly Gambit attack options required')
    if counter is not None:
        import move_state as MOVES
        if counter!='struggle' and counter not in MOVES.known(engine.r,target.spec):raise ValueError('actual known Deadly Gambit counter Move required')
        import struggle_capabilities as STRUGGLE
        prepared=WEAPONS.prepare(engine,target,engine.r.move(counter),options.get('weapon_id'))
        prepared=STRUGGLE.prepare(engine,target,prepared,options.get('struggle_choice'))
        import effects_ext as EXT
        prepared=EXT.prepare_versatile_move(engine,prepared,options.get('versatile_stat'))
        if prepared['class'] not in ('물리','특수') or (counter!='struggle' and WEAPONS.range_spec(engine,prepared,target).get('targets')!=1):
            raise ValueError('Deadly Gambit requires a damaging 1 Target counterattack')
        allowed,reason=F.move_allowed(engine,target,counter,outside_combat=False)
        if not allowed:raise ValueError('Deadly Gambit counter frequency: '+reason)
    ACTION.triggered_free_action(engine,owner,GAMBIT);F.consume_activation(owner,GAMBIT,quota,engine=engine)
    engine._taskmaster_gambit={'incoming_attacker':attacker,'pokemon':target,'move_id':move['id'],
        'counter_id':counter,'counter_options':deepcopy(options),'roll_effects':choice['roll_effects'],'phase':'incoming','applied':False}


def native_move(fn):
    @wraps(fn)
    def run(engine,attacker,target,*args,**kwargs):
        existed=hasattr(engine,'_taskmaster_gambit')
        outer=getattr(engine,'_taskmaster_gambit',None) is None
        move_id=args[0] if args else kwargs.get('move_id')
        # This outer decorator runs before the Engine's native move preflight.
        import partial_entities as PARTIAL
        PARTIAL.require_complete(attacker,'native move attacker')
        PARTIAL.require_complete(target,'native move target')
        move_permission(attacker,engine.r.move_id(move_id) or move_id)
        try:
            if not getattr(engine,'_reactive_move_transaction',False) and move_interested(engine,attacker,target):
                import reactive_ability_events as REACTIONS
                def staged(e,a,t):
                    payload=G._stage_transition_payload(engine,e,{'args':args,'kwargs':kwargs})
                    return fn(e,a,t,*payload['args'],**payload['kwargs'])
                return REACTIONS.atomic_move(engine,attacker,target,staged)
            return fn(engine,attacker,target,*args,**kwargs)
        finally:
            if outer:
                if existed:engine._taskmaster_gambit=None
                elif hasattr(engine,'_taskmaster_gambit'):del engine._taskmaster_gambit
    return run


def gambit_side(engine,attacker,target,move):
    row=getattr(engine,'_taskmaster_gambit',None)
    if not row:return None
    if row['incoming_attacker'] is attacker and row['pokemon'] is target and row['move_id']==move['id']:return 'incoming'
    if row['pokemon'] is attacker and row['incoming_attacker'] is target and row['counter_id']==move['id']:return 'counter'
    return None


def critical_damage(engine,attacker,target,move,critical):
    """Existing critical prevention, with the printed own-Pokemon exception."""
    if not critical:return False
    if gambit_side(engine,attacker,target,move)=='incoming':return True
    import ability_transitions as AB,enduring_resilience as RESILIENCE
    if AB.active(target,'ability/조가비갑옷-전투무장'):return False
    return not RESILIENCE.prevent(engine,target,critical=True,source=move['id'],attacker=attacker)


def apply_gambit_damage(engine,attacker,target,move,damage,context,before,*,actual_damage_type=None):
    """Two pre-damage calculations, then both native HP applications before sync.

    The counter retains its actual Move activation and completion. Its damage
    leaf is the rendezvous; no post-damage effect runs until both HP changes.
    """
    import heavy_injury_adapter as HEAVY,action_lifecycle as ACTION,combat_damage as DAMAGE
    row=getattr(engine,'_taskmaster_gambit',None);side=gambit_side(engine,attacker,target,move)
    if row is None or side is None:return None
    if side=='counter':
        incoming=row.get('prepared')
        if incoming is None:raise ValueError('actual prepared incoming paired hit required')
        row['counter_context']=context
        row['batch']=True
        try:
            incoming_application=HEAVY.apply_attack_damage(engine,incoming['attacker'],incoming['target'],incoming['damage'],incoming['move'],
                producer=HEAVY.Producer.RESOLVED_HIT,remainder='paired hit native continuations remain',native_context=incoming['context'],actual_damage_type=incoming['actual_damage_type'])
            row['incoming_receipt']=DAMAGE.application(requested=incoming['damage'],before=incoming['before'],
                after=DAMAGE.observe(incoming['target']),source=incoming['move']['id'],damage_class=incoming['move']['class'])
            counter_application=HEAVY.apply_attack_damage(engine,attacker,target,damage,move,producer=HEAVY.Producer.RESOLVED_HIT,
                remainder='paired hit native continuations remain',native_context=context,actual_damage_type=actual_damage_type)
            counter_receipt=DAMAGE.application(requested=damage,before=before,after=DAMAGE.observe(target),
                source=move['id'],damage_class=move['class'])
            if isinstance(incoming_application,dict) and incoming_application.get('source')==__import__('channeler').PAIN:row['incoming_receipt']['channeler_pain']=incoming_application
            if isinstance(counter_application,dict) and counter_application.get('source')==__import__('channeler').PAIN:counter_receipt['channeler_pain']=counter_application
        finally:
            row['batch']=False
            row.pop('counter_context',None)
        # Both participants' HP and injuries now exist before faint/death and
        # post-damage listeners. The reverse damage was calculated before either.
        for participant in (row['pokemon'],row['incoming_attacker']):engine.check_fainted(participant)
        row['applied']=True
        return counter_receipt
    if row['counter_id'] is None:return None
    row['prepared']={'attacker':attacker,'target':target,'move':move,'damage':damage,'context':context,'before':before,'actual_damage_type':actual_damage_type}
    row['phase']='counter'
    with ACTION.move_grant(engine,target,attacker,row['counter_id'],source=GAMBIT,kind='free') as grant:
        engine.use_move(target,attacker,row['counter_id'],count_use=True,free_action=True,_action_grant=grant,**row['counter_options'])
    # A real shield/cannot-hit response may prevent the counter. It still used
    # its Move frequency; the incoming hit then has no second damage to pair.
    if not row['applied']:return None
    row['phase']='incoming_return'
    return row['incoming_receipt']


def paired_receipt_current(engine,token):
    """Only the live reverse native receipt can retain its paired parent epoch."""
    row=getattr(engine,'_taskmaster_gambit',None)
    if not row or not row.get('batch') or row.get('prepared',{}).get('context') is not token:return False
    counter=row.get('counter_context')
    if counter is None or counter is token:return False
    import heavy_injury_adapter as HEAVY
    return HEAVY.validate_native_receipt(engine,counter,row['pokemon'],row['incoming_attacker'],{'id':row['counter_id']}) is not None


def defer_faint(engine,actor):
    row=getattr(engine,'_taskmaster_gambit',None)
    return bool(row and row.get('batch') and actor in (row['pokemon'],row['incoming_attacker']))


def after_attack(engine,attacker,target,move,*,critical,damage):
    """Actual damaging hit only. Choices spend virtual injury budget, never injuries."""
    if move.get('class') not in ('물리','특수') or _side(attacker) is None or _side(target) is None or _side(attacker)==_side(target):return
    import frequency as F,world_entities as W,action_lifecycle as ACTION,turn as TURN
    import ability_transitions as ABILITIES
    owner=W.actor_index(engine).get(attacker.spec.get('trainer_id'))
    known=ABILITIES.active(attacker,CRUELTY)
    normal=known and F.activation_allowed(attacker,CRUELTY,{'kind':'scene','uses':1},engine=engine)
    desperate=(owner is not None and acquired(owner,DESPERATE) is not None
        and (critical or known) and F.activation_allowed(owner,DESPERATE,{'kind':'scene','uses':DEFINITIONS[DESPERATE]['parameters']['scene']},engine=engine)
        and F.activation_allowed(attacker,DESPERATE,{'kind':'scene','uses':DEFINITIONS[DESPERATE]['parameters']['per_pokemon_scene']},engine=engine))
    if not normal and not desperate:return
    cruelty_definition(engine.r)
    choice=engine.rulings.decide({'type':'cruelty','unit':CRUELTY,'actor':attacker.name,'target':target.name,
        'text':'Choose Cruelty purchases, optionally Desperate Strike, or decline.',
        'normal_available':normal,'desperate_available':desperate,'critical':critical,
        'target_injuries':target.injuries,'user_injuries':attacker.injuries})
    if choice is None or choice is False:return
    if type(choice) is not dict or set(choice)!={'desperate','normal_trigger','hp_loss','slowed','healing_block'}:
        raise ValueError('explicit Cruelty trigger and purchase choices required')
    for field in ('desperate','normal_trigger','slowed','healing_block'):
        if type(choice[field]) is not bool:raise ValueError('explicit Cruelty boolean choices required')
    C.integer(choice['hp_loss'],'Cruelty repeated two-HP-loss purchases',0)
    use_desperate=choice['desperate'];normal_trigger=choice['normal_trigger']
    if use_desperate:
        if not desperate or (not normal_trigger and not critical):raise ValueError('actual Desperate Strike trigger required')
        if normal_trigger and not known:raise ValueError('normal Cruelty trigger requires the Ability')
        ACTION.triggered_free_action(engine,owner,DESPERATE)
        F.consume_activation(owner,DESPERATE,{'kind':'scene','uses':DEFINITIONS[DESPERATE]['parameters']['scene']},engine=engine)
        F.consume_activation(attacker,DESPERATE,{'kind':'scene','uses':DEFINITIONS[DESPERATE]['parameters']['per_pokemon_scene']},engine=engine)
    elif not normal or not normal_trigger:raise ValueError('actual available Cruelty Ability required')
    if normal_trigger:
        if not TURN.spend(engine,attacker,'swift',CRUELTY):raise ValueError('Cruelty requires an actual Swift action')
        if not use_desperate:F.consume_activation(attacker,CRUELTY,{'kind':'scene','uses':1},engine=engine)
    _injury(engine,target,1,CRUELTY);engine.check_fainted(target)
    budget=target.injuries+(attacker.injuries if use_desperate else 0)
    cost=choice['hp_loss']+int(choice['slowed'])+2*int(choice['healing_block'])
    if cost>budget:raise ValueError('Cruelty purchases exceed disclosed current injury budget')
    engine.log(target.name+': current injuries '+str(target.injuries)+'; Cruelty purchase budget '+str(budget),CRUELTY)
    if choice['hp_loss']:engine.lose_hp(target,2*choice['hp_loss'],CRUELTY)
    if choice['slowed']:engine.apply_status(target,'둔화',applied_by=attacker,source=CRUELTY)
    if choice['healing_block']:
        import custom_condition_effects as CUSTOM
        CUSTOM.grant(engine,attacker,target,cruelty_definition(engine.r)['raw'],CRUELTY)


def validate_world(engine,index):
    for actor in index.values():
        import order_actions as ORDERS
        for order in actor.registry:
            if order.get('free_order_payment') is not None:
                ORDERS.validate(engine,order['owner'],actor,order['rule_id'],order['free_order_payment'])
        row=active(actor)
        if row is None:continue
        if index.get(row['owner'].entity_id) is not row['owner'] or type(row.get('press_on')) is not bool:
            raise ValueError('Hardened actual owner or Press On state changed')
        receipt=actor.spec[G.KEY]['sources'][row[G.TAG]]
        for field in ('session','training_source'):
            if receipt.get(field)!=row[field]:raise ValueError('Hardened training source changed')
        owner=row['owner'];session=owner.custom_conditions.get('_training_sessions',{}).get(row['session'])
        outputs=[] if session is None else session.get('sources',[])
        if session is None:
            import training_rewards as R
            for reward in owner.spec.get(R.KEY,{}).values():
                if reward.get('id')==row['session']:
                    outputs=[o for a in reward['result']['awards'] for o in a['outputs']]
        matches=[o for o in outputs if o.get('source')==row['training_source']
                 and o.get('pokemon_id')==actor.entity_id and o.get('rule_id')=='feat/잔혹성-훈련'
                 and o.get('taskmaster')==row['training_result']]
        if len(matches)!=1:raise ValueError('Hardened requires the actual completed Brutal Training trigger')
    return True
