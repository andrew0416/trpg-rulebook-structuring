"""Actual mounted bodies, loads, source-owned movement and retention events."""
from copy import deepcopy
from dataclasses import asdict,is_dataclass
import common_checks as C,crafting_recipes as Q,state_grants as G,world_entities as W
import skill_modifiers as S,turn as TURN,movement_actions as MOVE,capability_actions as LOAD
import resolution_transaction as TX,roll_context as R
from physical_limits import number

CONTRACT='mount_contract'
RIDERS='_mounted_riders'
POOL='_mount_movement'
SOURCE='ch03-skills-edges-feats/재주'
RIDER='class/라이더'
RIDE_AS_ONE='feat/인마일체'
FEATURES={RIDER:(902,904),RIDE_AS_ONE:(920,924)}


def _acquisitions(actor,feature,*,active=False):
    import trainer_feature_acquisition as TFA
    return [row['static_acquisition'] for _,row,live in TFA._static_records(actor)
            if row['static_acquisition']['feature_id']==feature and (live or not active)]


def acquisition_snapshot(actor,feature):
    import acquired_features as A,training_features as TRAINING
    parent=None
    if feature==RIDE_AS_ONE:
        parent=acquired(actor,RIDER)
        if parent is None:raise ValueError('Ride as One requires its actual acquired Rider source')
    return {'acrobatics':S.rank(actor.r,actor,'곡예')[2] if feature==RIDER else 0,
            'athletics':S.rank(actor.r,actor,'육상')[2] if feature==RIDER else 0,
            'mounted_prowess':A.owned_rule_count(actor,'edge/탑승-기량') if feature==RIDER else 0,
            'agility_training':A.owned_rule_count(actor,TRAINING.AGILITY) if feature==RIDER else 0,
            'class_slots':len(A.class_instances(actor)) if feature==RIDER else 0,
            'parent_request':None if parent is None else parent['request_id']}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    fields={'acrobatics','athletics','mounted_prowess','agility_training','class_slots','parent_request'}
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields:
        raise ValueError('exact acquisition-time Rider observations required')
    for field in fields-{'parent_request'}:C.integer(snapshot[field],'Rider '+field,0)
    checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required')]
    if feature==RIDER:
        if snapshot['parent_request'] is not None:raise ValueError('Rider has no parent class acquisition')
        checks.extend([Q.check('mounted_prowess','prerequisite',snapshot['mounted_prowess']==1,'actual Mounted Prowess required'),
            Q.check('agility_training','prerequisite',snapshot['agility_training']==1,'actual Agility Training required'),
            Q.check('skill','prerequisite',max(snapshot['acrobatics'],snapshot['athletics'])>=3,'Novice Acrobatics or Athletics required'),
            Q.check('class_slots','capacity',snapshot['class_slots']<4,'one of four class slots required')])
    elif feature==RIDE_AS_ONE:
        if any(snapshot[field] for field in fields-{'parent_request'}):raise ValueError('Ride as One adds no independent skill prerequisite')
        parents=[row for row in _acquisitions(actor,RIDER) if row['request_id']==snapshot['parent_request']]
        if len(parents)!=1:raise ValueError('actual historical Rider acquisition required')
    else:raise ValueError('reviewed Rider feature required')
    return Q.require(feature,'native','acquire',checks)


def acquired(actor,feature):
    import acquired_features as A,trainer_feature_acquisition as TFA
    if not A.owned_rule_count(actor,feature):return None
    TFA.validate_actor(actor)
    rows=_acquisitions(actor,feature,active=True)
    if actor.kind!='trainer' or A.owned_rule_count(actor,feature)!=1 or len(rows)!=1:
        raise ValueError('one source-specific Rider acquisition required')
    if feature==RIDE_AS_ONE and acquired(actor,RIDER) is None:
        raise ValueError('Ride as One requires its current actual Rider source')
    return rows[0]


def mounted_pairs(actor):
    """Use the existing carried-body references, never an owned-Pokemon guess."""
    for rider in _riders(actor):
        contract=rider.spec.get(CONTRACT,{})
        if rider.spec.get('mount_id')!=actor.entity_id or contract.get('mount_id')!=actor.entity_id:
            raise ValueError('actual managed Rider mount relation required')
        yield rider,actor


def agility_multiplier(actor):
    return 2 if any(acquired(rider,RIDER) is not None for rider,_ in mounted_pairs(actor)) else 1


def ride_pairs(engine,actor):
    if not managed_subject(actor):return []
    W.require_actors(engine,actor)
    mount=_relation(engine,actor) if CONTRACT in actor.spec else actor
    if mount is None:return []
    pairs=[]
    for rider,actual in mounted_pairs(mount):
        W.require_actors(engine,rider,actual)
        if actor in (rider,actual) and acquired(rider,RIDE_AS_ONE) is not None:pairs.append((rider,actual))
    return pairs


def ride_pair(engine,actor,other):
    return next((pair for pair in ride_pairs(engine,actor) if other in pair),None)


def speed_evasion(engine,actor,value):
    ev=actor.r.mech('combat/evasion')
    import arithmetic_policy as M,combat_timing as TIMING
    results=[value]
    for pair in ride_pairs(engine,actor):
        other=next(c for c in pair if c is not actor)
        disabled=(other.fainted or other.custom_conditions.get('_grapple_relation') or TIMING.evasion_zero(other)
            or any(e['type']=='evasion_disabled' and (not e.get('only') or e.get('only')=='speed') for condition in other.conditions for e in other.r.condition_effects(condition))
            or any(e.get('type')=='implied_by' and other.conditions.intersection(e.get('conditions',())) for e in other.r.condition_effects('취약')))
        theirs=0 if disabled else min(ev['cap'],M.ratio(other.staged(ev['sources']['speed']),ev['per_points']))
        results.append(value+1 if value==theirs else max(value,theirs))
    return max(results)


def declaration(value):
    Q._fields(value,('id','source','authority','requirements','target_capabilities','seats','load','boarding','retention','movement'))
    Q._text(value['id']);Q._text(value['source'])
    if value['authority'] not in ('owned','controlled','gm'):raise ValueError('actual mounting authority required')
    if type(value['requirements']) is not list:raise ValueError('explicit mount qualification list required')
    for node in value['requirements']:Q._condition(node)
    if type(value['target_capabilities']) is not list:raise ValueError('explicit mount capabilities required')
    Q._names(value['target_capabilities']) if value['target_capabilities'] else None
    if value['seats'] is not None:C.integer(value['seats'],'mount seats',1)
    load=value['load']
    if type(load) is not dict or load.get('kind') not in ('gm','power'):raise ValueError('explicit known load or GM admission policy required')
    if load['kind']=='gm':Q._fields(load,('kind',))
    else:
        Q._fields(load,('kind','average_exception','boundary_band'))
        if load['boundary_band'] not in (None,'normal','heavy','staggering'):raise ValueError('explicit load endpoint policy required')
        exception=load['average_exception']
        if exception is not None:
            Q._fields(exception,('capabilities','maximum_riders','average_weight_kg'));Q._names(exception['capabilities'])
            C.integer(exception['maximum_riders'],'average rider seats',1);number(exception['average_weight_kg'],'observed average weight',minimum=0)
    boarding=value['boarding'];Q._fields(boarding,('skill','dc','action','automatic','adjacent'))
    Q._text(boarding['skill']);C.integer(boarding['dc'],'boarding DC',0)
    if boarding['action'] not in ('standard','shift','free') or type(boarding['adjacent']) is not bool:raise ValueError('explicit boarding action and distance policy required')
    if boarding['automatic'] is not None:Q._condition(boarding['automatic'])
    retain=value['retention'];Q._fields(retain,('skill','dc','bonus','feature_bonus','damage_fraction','forced_move','confusion'))
    Q._text(retain['skill']);C.integer(retain['dc'],'retention DC',0);C.integer(retain['bonus'],'retention bonus')
    if retain['feature_bonus'] is not None:
        Q._fields(retain['feature_bonus'],('condition','value'));Q._condition(retain['feature_bonus']['condition']);C.integer(retain['feature_bonus']['value'],'owned retention bonus')
    Q._fields(retain['damage_fraction'],('numerator','denominator'));C.integer(retain['damage_fraction']['numerator'],'damage numerator',1);C.integer(retain['damage_fraction']['denominator'],'damage denominator',1)
    if type(retain['forced_move']) is not bool or type(retain['confusion']) is not bool:raise ValueError('explicit retention trigger policy required')
    movement=value['movement'];Q._fields(movement,('scope','action_owner','maximum_distance'))
    if movement['scope'] not in ('round','mount_turn') or movement['action_owner'] not in ('mover','mount'):raise ValueError('actual shared movement owner and reset boundary required')
    if movement['maximum_distance'] is not None:C.integer(movement['maximum_distance'],'mount movement cap',0)
    return deepcopy(value)


def _body(value):return {k:deepcopy(v) for k,v in value.items() if k!='id'}
def _signed(row):return dict(row,sha256=TX.request_fingerprint(row))
def _riders(mount):return list(getattr(mount,RIDERS,[]))


def managed_subject(actor):return hasattr(actor,'spec') and (CONTRACT in actor.spec or bool(_riders(actor)))


def _relation(engine,rider):
    W.require_actors(engine,rider);return W.mount_relation(W.actor_index(engine),rider)


def travel_group(engine,actor):
    if actor is None:return set()
    # Only managed actual boarding joins body footprints. Legacy mount IDs still
    # retain their identity validation without inventing movement/load rights.
    mount=_relation(engine,actor) if CONTRACT in actor.spec else actor
    if mount is None:return {actor}
    return {mount,*_riders(mount)}


def sync(engine,mount):
    for rider in _riders(mount):
        if rider.spec.get('mount_id')!=mount.entity_id:raise ValueError('actual mounted body link required')
        location=W.location_of(mount)
        if location['kind']=='grid':rider.pos=mount.pos
        elif W.location_of(rider)!=location:
            W.observe_location(engine,rider,location,reason='actual carried body follows its mount',source=SOURCE)
        rider.spec['_movement_altitude']=mount.spec.get('_movement_altitude',0);rider.airborne=getattr(mount,'airborne',False)


def _owned_condition(rider):
    return {'kind':'all','conditions':[
        {'kind':'owned','fields':['edges'],'names':['edge/탑승-기량','탑승 기량','Mounted Prowess']},
        {'kind':'any','conditions':[{'kind':'skill','skill':s,'rank':3,'effective':False} for s in ('곡예','육상')]}]}


def native_declaration(skill):
    return {'id':'native/mounting','source':SOURCE,'authority':'gm','requirements':[],'target_capabilities':[],
        'seats':None,'load':{'kind':'gm'},'boarding':{'skill':skill,'dc':10,'action':'standard','automatic':_owned_condition(None),'adjacent':False},
        'retention':{'skill':skill,'dc':10,'bonus':0,'feature_bonus':{'condition':_owned_condition(None),'value':3},
            'damage_fraction':{'numerator':1,'denominator':4},'forced_move':True,'confusion':True},
        'movement':{'scope':'round','action_owner':'mover','maximum_distance':None}}


def _admit(engine,rider,mount,value,gm_mountable):
    import equipped_transport_saddle as EQUIPMENT
    if not EQUIPMENT.independent(engine,rider) or not EQUIPMENT.independent(engine,mount):raise ValueError('release actual equipment transport before separate mounting')
    W.require_actors(engine,rider,mount);W.require_mount_target(engine,rider,mount);Q._selected(engine,value['source'])
    if not rider.on_field or rider.captured or not mount.on_field or mount.captured or rider.fainted or mount.fainted:raise ValueError('available actual rider and mount required')
    if value['authority']=='owned' and W.identity_field(engine,mount,'owner_id')!=rider.entity_id:raise ValueError('actual owned mount required')
    if value['authority']=='controlled':
        control=mount.spec.get('controller')
        if type(control) is not dict or control.get('kind')!='actor' or control.get('id')!=rider.entity_id:raise ValueError('actual mount controller required')
    if gm_mountable is not True:raise ValueError('GM must establish actual size, strength and equipment admission')
    if not all([Q._observe(engine,rider,node,set()) for node in value['requirements']]):raise ValueError('actual rider qualification required')
    if value['target_capabilities'] and not {S.key(x) for x in value['target_capabilities']} & {S.key(x) for x in G.effective_capabilities(mount)}:raise ValueError('current declared mount capability required')
    if rider.spec.get('mount_id'):raise ValueError('rider is already mounted')
    if value['boarding']['adjacent']:
        import body_state as BODY
        if not BODY.adjacent(rider,mount):raise ValueError('boarding requires actual adjacent bodies')
    riders=_riders(mount)
    if value['seats'] is not None and len(riders)>=value['seats']:raise ValueError('actual mounting seat capacity exceeded')
    for other in riders:
        if any(other.spec[CONTRACT]['policy'][field]!=value[field] for field in ('source','load','movement','seats')):raise ValueError('mount occupants must share the declared load and movement policy')
    if value['load']['kind']=='power':
        import body_state as BODY
        for actual in (*riders,rider):number(BODY.weight_kg(actual),'actual rider weight',minimum=0)
        from copy import copy
        probe=copy(mount);setattr(probe,RIDERS,[*riders,rider]);probe.spec=dict(mount.spec)
        fake=copy(rider);fake.spec=dict(rider.spec,mount_id=mount.entity_id,**{CONTRACT:{'policy':_body(value)}})
        setattr(probe,RIDERS,[*riders,fake]);LOAD.load(probe)


def _attach(engine,rider,mount,value):
    rider.spec['mount_id']=mount.entity_id
    rider.spec[CONTRACT]=_signed({'source':value['source'],'mount_id':mount.entity_id,'policy':_body(value),'boarded_at':engine.elapsed_seconds})
    setattr(mount,RIDERS,[*_riders(mount),rider]);sync(engine,mount)


def _detach(engine,rider,mount,reason):
    # A failed retention keeps the current actual position; no unobserved fall
    # distance, destination or damage is invented.
    rider.spec.pop('mount_id',None);contract=rider.spec.pop(CONTRACT,None)
    setattr(mount,RIDERS,[x for x in _riders(mount) if x is not rider])
    location=W.location_of(rider)
    rider.custom_conditions.setdefault('mount_history',[]).append({'mount_id':mount.entity_id,'source':None if contract is None else contract['source'],
        'at':engine.elapsed_seconds,'reason':reason,**({'position':list(rider.pos)} if location['kind']=='grid' else {'location':location})})


def native(engine,rider,*,target,phase,skill='곡예',gm_mountable=None,dc=10,**options):
    import pokemon_activities as A
    W.require_actors(engine,rider,target);validate_world(engine,W.actor_index(engine))
    value=declaration(native_declaration(skill))
    if phase=='mount':_admit(engine,rider,target,value,gm_mountable)
    def apply(e,c,mount):
        import equipped_transport_saddle as EQUIPMENT
        bonus=EQUIPMENT.saddle_bonus(e,c,mount,'boarding') if phase=='mount' and not Q._observe(e,c,value['boarding']['automatic'],set()) else 0
        actual=dict(options)
        if bonus:actual['mods']=actual.get('mods',0)+bonus
        out=A._mounting_native(e,c,target=mount,phase=phase,skill=skill,gm_mountable=gm_mountable,dc=dc,**actual)
        if isinstance(out,C.PendingDecision):return out
        if phase=='mount' and out['passed']:_attach(e,c,mount,value)
        elif phase=='retain' and not out['passed'] and CONTRACT in c.spec:_detach(e,c,mount,'retention_failed')
        validate_world(e,W.actor_index(e));return out
    return G.transition(engine,rider,apply,participants=(target,))


def board(engine,rider,mount,value,*,gm_mountable,roll_options=None):
    value=declaration(value);_admit(engine,rider,mount,value,gm_mountable);options={} if roll_options is None else deepcopy(roll_options)
    if type(options) is not dict:raise ValueError('native boarding roll options required')
    def apply(e,c,target):
        _admit(e,c,target,value,gm_mountable);boarding=value['boarding'];automatic=boarding['automatic'] is not None and Q._observe(e,c,boarding['automatic'],set())
        check=None
        if automatic and options:raise ValueError('automatic boarding does not consume dice or roll resources')
        import equipped_transport_saddle as EQUIPMENT
        bonus=0 if automatic else EQUIPMENT.saddle_bonus(e,c,target,'boarding')
        actual=dict(options)
        if bonus:actual['mods']=actual.get('mods',0)+bonus
        if not automatic:R.plan(e,c,boarding['skill'],purpose='declared mounting',target=target,**actual)
        if not TURN.spend(e,c,boarding['action'],'declared mounting'):return C.PendingDecision('required boarding action unavailable')
        if not automatic:check=C.against_dc(e.skill_roll(c,boarding['skill'],skill_target=target,**actual),boarding['dc'])
        passed=automatic or check.passed
        if passed:_attach(e,c,target,value)
        validate_world(e,W.actor_index(e));return {'passed':passed,'automatic':automatic,'check':check,'rider_id':c.entity_id,'mount_id':target.entity_id}
    return G.transition(engine,rider,apply,participants=(mount,))


def rider_load(mount):
    riders=_riders(mount)
    if not riders:return 0,None
    value=riders[0].spec[CONTRACT]['policy'];policy=value['load']
    if policy['kind']=='gm':return 0,None # Explicit GM physical admission, not a fabricated numeric mass.
    import body_state as BODY
    weights=[number(BODY.weight_kg(c),'actual rider weight',minimum=0) for c in riders]
    exception=policy['average_exception'];exempt=False
    if exception is not None:
        names={S.key(x) for x in G.effective_capabilities(mount)}
        exempt=bool(names & {S.key(x) for x in exception['capabilities']}) and len(riders)<=exception['maximum_riders'] and all(x<=exception['average_weight_kg'] for x in weights)
        # Additional ordinary loads withdraw the average-rider exemption.
        exempt=exempt and not (mount.spec.get('_carried_load') or {}).get('objects')
    return 0 if exempt else sum(weights),policy['boundary_band']


def _movement_policy(engine,actor):
    mount=_relation(engine,actor) if CONTRACT in actor.spec else actor
    if mount is None:raise ValueError('actual managed mount relation required')
    riders=_riders(mount)
    policy=riders[0].spec[CONTRACT]['policy'] if riders else getattr(mount,POOL)['policy']
    return mount,policy


def manages(engine,actor):
    if CONTRACT in actor.spec or _riders(actor):return True
    pool=getattr(actor,POOL,None)
    return type(pool) is dict and pool['period']==_period(engine,actor,pool['policy'])


def _period(engine,mount,value):
    return {'round':engine.round_no,'turn':mount.custom_conditions.get('combat_turn_serial',0) if value['movement']['scope']=='mount_turn' else None}


def shared_movement(engine,actor,mode='land'):
    """Read the actual donor and remaining pool without spending or refreshing it."""
    validate_world(engine,W.actor_index(engine));mount,value=_movement_policy(engine,actor)
    Q._selected(engine,value['source']);pool=getattr(mount,POOL,None);period=_period(engine,mount,value)
    if pool is not None and pool['period']==period:
        if any(pool['policy'][field]!=value[field] for field in ('source','load','movement')):
            raise ValueError('shared mount movement policy cannot reset mid-period')
        used,diagonals=pool['used'],pool['diagonals']
    else:used,diagonals=0,0
    allowance=MOVE.distance_budget(engine,mount,mode);maximum=value['movement']['maximum_distance']
    if maximum is not None:allowance=min(allowance,maximum)
    return mount,value,dict(period=period,allowance=allowance,remaining=max(0,allowance-used),used=used,diagonals=diagonals)


def record_movement(engine,mount,value,*,distance,diagonals):
    """Commit actual travelled distance to the same mapped/unmapped shared pool."""
    C.integer(distance,'actual shared movement distance',0);C.integer(diagonals,'shared diagonal steps',0)
    actual,policy,context=shared_movement(engine,mount)
    if actual is not mount or policy!=value:raise ValueError('actual shared movement policy changed during travel')
    setattr(mount,POOL,_signed(dict(period=context['period'],policy=deepcopy(value),
        used=context['used']+distance,diagonals=diagonals)))


def approach(engine,actor,target,reach=1,*,movement_mode=None,blindness_options=None):
    W.require_actors(engine,actor,target);validate_world(engine,W.actor_index(engine));mount,value=_movement_policy(engine,actor)
    def apply(e,c,other,donor):
        _,_,context=shared_movement(e,c,movement_mode or 'land')
        allowance,remaining=context['allowance'],context['remaining']
        if not remaining:return {'distance':0,'remaining':0,'position':donor.pos}
        if not TURN.can_act(e,c) or not TURN.can_act(e,donor) or not TURN.movement_permission(e,c) or not TURN.movement_permission(e,donor):return False
        action_owner=donor if value['movement']['action_owner']=='mount' else c
        donor._diagonal_steps=context['diagonals']
        record_movement(e,donor,value,distance=0,diagonals=context['diagonals'])
        out=e._approach(donor,other,reach,movement_mode=movement_mode,blindness_options=blindness_options,
                        action_owner=action_owner,maximum_distance=remaining)
        moved=0 if out is None else out['distance']
        record_movement(e,donor,value,distance=moved,diagonals=getattr(donor,'_diagonal_steps',0))
        sync(e,donor);validate_world(e,W.actor_index(e));return {'distance':moved,'remaining':max(0,remaining-moved),'position':donor.pos}
    return G.transition(engine,actor,apply,participants=(target,mount))


def retain(engine,rider,*,event='manual',roll_options=None):
    mount=_relation(engine,rider)
    if mount is None or CONTRACT not in rider.spec:raise ValueError('actual managed mounted relation required')
    options={} if roll_options is None else deepcopy(roll_options)
    def apply(e,c,target):
        value=c.spec[CONTRACT]['policy'];Q._selected(e,value['source']);policy=value['retention']
        bonus=policy['bonus'];feature=policy['feature_bonus']
        import equipped_transport_saddle as EQUIPMENT
        bonus+=EQUIPMENT.saddle_bonus(e,c,target,event)
        if feature is not None and Q._observe(e,c,feature['condition'],set()):bonus+=feature['value']
        passed=False;check=None
        if not c.fainted and not target.fainted:
            actual=dict(options);actual['mods']=actual.get('mods',0)+bonus
            R.plan(e,c,policy['skill'],purpose='mount retention:'+event,target=target,**actual)
            check=C.against_dc(e.skill_roll(c,policy['skill'],skill_target=target,**actual),policy['dc']);passed=check.passed
        if not passed:_detach(e,c,target,'retention:'+event)
        else:sync(e,target)
        result={'event':event,'rider_id':c.entity_id,'mount_id':target.entity_id,'passed':passed,'bonus':bonus,
                'check':None if check is None else asdict(check),'at':e.elapsed_seconds}
        c.custom_conditions.setdefault('mount_retention_history',[]).append(deepcopy(result));validate_world(e,W.actor_index(e));return result
    return G.transition(engine,rider,apply,participants=(mount,))


def notify(engine,subject,event,*,amount=None,max_hp=None):
    W.require_actors(engine,subject)
    if event not in ('damage','forced_move','confusion'):raise ValueError('known actual retention event required')
    if event=='damage':C.integer(amount,'actual attack damage',0);C.integer(max_hp,'actual pre-hit maximum HP',1)
    index=W.actor_index(engine);selected=[]
    for rider in index.values():
        if CONTRACT not in rider.spec:continue
        mount=index.get(rider.spec.get('mount_id'))
        if subject not in (rider,mount):continue
        policy=rider.spec[CONTRACT]['policy']['retention']
        if event=='damage':
            ratio=policy['damage_fraction']
            if amount is None or amount<=0 or amount*ratio['denominator']<max_hp*ratio['numerator']:continue
        elif event not in ('forced_move','confusion') or not policy[event]:continue
        selected.append(rider)
    return [retain(engine,c,event=event) for c in selected if CONTRACT in c.spec]


def confusion_loss(engine,subject,amount,*,_completion_id=None):
    """Consume an actual confusion self-hit; its sourced amount stays upstream."""
    W.require_actors(engine,subject);C.integer(amount,'actual confusion self-hit loss',1)
    if '잠듦' in subject.conditions:raise ValueError('sleep prevents Confusion self-hit')
    if _completion_id is None:
        if '혼란' not in subject.conditions:raise ValueError('actual current confusion required for a self-hit')
    else:
        import confusion_attacks as CONFUSION
        CONFUSION.require_loss(engine,subject,_completion_id,amount)
    engine.r.condition_effects('혼란')
    def apply(e,c):
        before=c.hp;e.lose_hp(c,amount,source='혼란 자해')
        checks=notify(e,c,'confusion')
        return {'subject_id':c.entity_id,'before':before,'after':c.hp,'retention':checks}
    return G.transition(engine,subject,apply)


def dismount(engine,rider,*,destination=None,reason):
    Q._text(reason);mount=_relation(engine,rider)
    if mount is None or CONTRACT not in rider.spec:raise ValueError('actual managed mounted relation required')
    def apply(e,c,target):
        _detach(e,c,target,reason)
        if destination is not None:
            import body_state as BODY
            if not BODY.can_place(e,c,tuple(destination)):raise ValueError('actual dismount destination is blocked')
            c.pos=tuple(destination)
        validate_world(e,W.actor_index(e));location=W.location_of(c)
        return {'rider_id':c.entity_id,'mount_id':target.entity_id,**({'position':c.pos} if location['kind']=='grid' else {'location':location})}
    return G.transition(engine,rider,apply,participants=(mount,))


def validate_world(engine,index):
    for actor in index.values():
        riders=_riders(actor)
        if len({id(c) for c in riders})!=len(riders):raise ValueError('distinct actual mounted riders required')
        for rider in riders:
            if index.get(rider.entity_id) is not rider or rider.spec.get('mount_id')!=actor.entity_id or CONTRACT not in rider.spec:raise ValueError('actual mounted body reference required')
        contract=actor.spec.get(CONTRACT)
        if contract is not None:
            Q._fields(contract,('source','mount_id','policy','boarded_at','sha256'))
            if contract['sha256']!=TX.request_fingerprint({k:v for k,v in contract.items() if k!='sha256'}):raise ValueError('mount admission contract changed')
            value=declaration(dict(contract['policy'],id='restored'));Q._selected(engine,contract['source'])
            if value['source']!=contract['source'] or actor.spec.get('mount_id')!=contract['mount_id']:raise ValueError('mount source and actual relation disagree')
            mount=W.mount_relation(index,actor)
            if actor not in _riders(mount):raise ValueError('mount lacks actual rider body')
            C.integer(contract['boarded_at'],'mount boarding time',0,engine.elapsed_seconds)
        pool=getattr(actor,POOL,None)
        if pool is not None:
            Q._fields(pool,('period','policy','used','diagonals','sha256'));value=declaration(dict(pool['policy'],id='restored'));Q._selected(engine,value['source'])
            if pool['sha256']!=TX.request_fingerprint({k:v for k,v in pool.items() if k!='sha256'}):raise ValueError('shared mount movement record changed')
            Q._fields(pool['period'],('round','turn'));C.integer(pool['period']['round'],'shared movement round',0,engine.round_no)
            if value['movement']['scope']=='round':
                if pool['period']['turn'] is not None:raise ValueError('round movement has no rider turn reset')
            else:C.integer(pool['period']['turn'],'actual mount movement turn',0,actor.custom_conditions.get('combat_turn_serial',0))
            C.integer(pool['used'],'spent shared movement',0);C.integer(pool['diagonals'],'shared diagonal steps',0)
        if riders:LOAD.load(actor)
    return True
