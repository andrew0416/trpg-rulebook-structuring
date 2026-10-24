"""Ace Trainer source adapters over existing acquisition, training and Move owners."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import re

import common_checks as C
import state_grants as G
import world_entities as W
import skill_modifiers as SK
import combat_timing as TIME

CLASS = 'class/에이스-트레이너'
PERSEVERANCE = 'feat/인내'
ELITE = 'feat/엘리트-트레이너'
CRITICAL = 'feat/결정적인-순간'
TOP = 'feat/탑-퍼센티지'
SIGNATURE = 'feat/시그니처-테크닉'
CHAMP = 'feat/미래의-챔피언'
SOURCE_SHA256 = 'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
FEATURES = {CLASS:(312,314), PERSEVERANCE:(316,320), ELITE:(322,325), CRITICAL:(327,332),
            TOP:(334,338), SIGNATURE:(340,348), CHAMP:(350,354)}
PARENTS = {CLASS:(), PERSEVERANCE:(CLASS,), ELITE:(CLASS,), CRITICAL:(ELITE,), TOP:(CLASS,),
           SIGNATURE:(ELITE,), CHAMP:()}
CLAUSES = {CLASS:'C04-009', ELITE:'C04-010', SIGNATURE:'C04-011', CHAMP:'C04-012'}
DEFINITIONS = {u:{'span':list(s), 'catalog_span':[296,296] if u==CLASS else [350,358] if u==CHAMP else list(s),
    'parents':list(PARENTS[u]), 'clause_id':CLAUSES.get(u, 'input/ch04-trainer-classes.md:'+str(s[0])+'-'+str(s[1])),
    'minimum_command':3 if u==CLASS else 4 if u==CRITICAL else 5 if u in (TOP,SIGNATURE) else 6 if u==CHAMP else 0}
    for u,s in FEATURES.items()}
TRAINING = {'feat/민첩성-훈련':(696,700), 'feat/잔혹성-훈련':(702,706),
            'feat/집중성-훈련':(708,712), 'feat/영감성-훈련':(714,718)}
POLICY = 'data/ace-trainer-source-contract.json'
KEY = 'signature_techniques'
MARKER = '_signature_technique'
MODIFICATIONS = {
    'scattershot':('area','feat/민첩성-훈련',3),
    'shock_and_awe':('area','feat/영감성-훈련',3),
    'vicious_storm':('area','feat/잔혹성-훈련',3),
    'guarding_strike':('single','feat/영감성-훈련',4),
    'unbalancing_blow':('single','feat/잔혹성-훈련',4),
    'reliable_attack':('single','feat/집중성-훈련',4),
    'alternative_energy':('damage','feat/집중성-훈련',5),
    'bloodied_speed':('damage','feat/민첩성-훈련',5),
    'double_down':('damage','feat/잔혹성-훈련',5),
    'burst_of_motivation':('status','feat/영감성-훈련',6),
    'supreme_concentration':('status','feat/집중성-훈련',6),
    'double_curse':('status','feat/민첩성-훈련',6),
}


def policy(rules):
    path=Path(__file__).resolve().parents[1]/POLICY
    document=json.loads(path.read_text(encoding='utf8'))
    if document.get('schema')!=1 or set(document['source_choices'])!={'core_1.05','dataninja_class_errata'}:
        raise ValueError('reviewed Ace Trainer source contract required')
    return document


def source(rules, contract='core_1.05', *, csv_source=False):
    """Explicit actual sources; adopted Class Errata is not an official Playtest."""
    from source_context import verified_source
    p=policy(rules)
    if contract not in p['source_choices']:raise ValueError('exact Core or adopted Dataninja Technique source required')
    for key in ('body','core', *(['feats_csv','class_data_csv'] if csv_source else []),
                *(['dataninja_class_errata'] if contract=='dataninja_class_errata' else [])):
        verified_source(rules,p[key],label='Ace Trainer '+key,
            source_root='source-audit' if key in ('core','dataninja_class_errata') else 'input')
    if rules._selected_rule(SIGNATURE)!=SIGNATURE:raise ValueError('selected Signature Technique requires its own source adapter')
    return deepcopy(p['source_choices'][contract])


def records(actor, feature=None, *, active=False):
    import trainer_feature_acquisition as T
    return [row['static_acquisition'] for _,row,live in T._static_records(actor)
            if row['static_acquisition']['feature_id'] in {*FEATURES,*TRAINING}
            and (feature is None or row['static_acquisition']['feature_id']==feature) and (not active or live)]


def acquired(actor, feature=CLASS):
    rows=records(actor,feature,active=True)
    return rows[-1] if rows else None


def acquisition_snapshot(engine, actor, uid, rank=None, selection=None):
    import trainer_feature_acquisition as T
    import training_features as TRAIN
    if rank is not None:raise ValueError('Ace Trainer Features are not Ranked')
    gift=None
    if uid==ELITE:
        if type(selection)is not dict or set(selection)!={'feature','options'} or type(selection['options'])is not dict:
            raise ValueError('choose one actual Elite gift Feature and its native acquisition options')
        feature=selection['feature']
        if feature not in T.STATIC_FEATURES:raise ValueError('Elite gift needs a supported actual Feature acquisition')
        if feature.startswith('class/'):raise ValueError('Elite Trainer grants one Feature, not a Class Feature')
        owned=[u for u in TRAIN.RULES if TRAIN.owns(actor,u)]
        if len(owned)<4 and (feature not in TRAIN.RULES or feature in owned):
            raise ValueError('choose one unowned basic Training Feature for the Elite gift')
        if len(owned)==4 and feature in TRAIN.RULES:raise ValueError('all four owned: choose another qualified Feature')
        gift={'feature':feature,'options':deepcopy(selection['options']),'waived_training_prerequisite':len(owned)<4}
    elif uid in TRAINING and selection is not None:
        if type(selection)is not dict or set(selection)!={'elite_parent'}:raise ValueError('exact actual Elite gift parent required')
        parents=[r for r in records(actor,ELITE,active=True) if r['request_id']==selection['elite_parent']]
        if len(parents)!=1 or parents[0]['snapshot']['gift']!={'feature':uid,'options':{},'waived_training_prerequisite':True}:
            raise ValueError('Training waiver requires its actual Elite chosen gift')
        gift={'elite_parent':selection['elite_parent']}
    elif selection is not None:raise ValueError('this Ace Trainer Feature has no optional selection')
    return {'skills':{s:SK.rank(engine.r,actor,s)[2] for s in ('명령','육상','협박','매력')},
            'parents':[r['request_id'] for r in records(actor,active=True) if r['feature_id'] in FEATURES],
            'gift':gift,'selection':deepcopy(selection)}


def qualification(actor, uid, snapshot, prerequisite_source):
    import acquisition_qualification as Q
    import training_features as TRAIN
    if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'skills','parents','gift','selection'}:
        raise ValueError('exact Ace Trainer acquisition observations required')
    if set(snapshot['skills'])!={'명령','육상','협박','매력'}:raise ValueError('exact acquired skill observations required')
    # Acquisition resolves declared ranks through SK.rank; history retains that observation.
    for value in snapshot['skills'].values():C.integer(value,'acquired skill rank',1)
    history={r['request_id']:r for r in records(actor)}
    if type(snapshot['parents'])is not list or len(set(snapshot['parents']))!=len(snapshot['parents']) or not set(snapshot['parents'])<=set(history):
        raise ValueError('actual Ace Trainer parent acquisition receipts required')
    parents={history[r]['feature_id'] for r in snapshot['parents']}
    if uid in TRAINING:
        waiver=snapshot['gift'] is not None
        if waiver:
            parent=history.get(snapshot['gift'].get('elite_parent'),{})
            if parent.get('feature_id')!=ELITE or parent['snapshot']['gift']!={'feature':uid,'options':{},'waived_training_prerequisite':True}:
                raise ValueError('actual chosen Elite gift required for Training waiver')
        passed=all(snapshot['skills'][s]>=n for s,n in TRAIN.RULES[uid]['skills'].items())
        checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
                Q.check('training_skills','prerequisite',passed,'printed basic Training prerequisite required')]
    else:
        checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
                Q.check('parents','prerequisite',set(PARENTS[uid])<=parents,'actual Ace Trainer parent required'),
                Q.check('command','prerequisite',snapshot['skills']['명령']>=DEFINITIONS[uid]['minimum_command'],'printed Command rank required'),
                Q.check('class_count','prerequisite',uid!=CHAMP or len(parents&set(FEATURES))>=4,'four actually acquired Ace Trainer Features required')]
        if uid==ELITE:checks.append(Q.check('gift','selection',type(snapshot['gift'])is dict,'one immutable Elite gift required'))
    if uid in TRAINING and snapshot['gift'] is not None:
        result=Q.evaluate(source_id=uid,provider='native',stage='acquire',checks=checks,waivers=[{
            'source_id':uid,'provider':'native','stage':'acquire','checks':['training_skills'],
            'reason':ELITE+' chosen actual gift '+snapshot['gift']['elite_parent']}])
        if result['status']!='qualified':raise ValueError('actual Elite Training gift qualification required')
        return result
    return Q.require(uid,'native','acquire',checks)


def after_acquire(engine, actor, uid, source_id):
    if uid!=ELITE:return
    import trainer_feature_acquisition as T
    parent=acquired(actor,ELITE);gift=parent['snapshot']['gift'];options=deepcopy(gift['options'])
    if gift['waived_training_prerequisite']:
        if options:raise ValueError('basic Training gift has no acquisition choices')
        options['selection']={'elite_parent':parent['request_id']}
    if set(options)-{'selection','branch','rank','prerequisite_source'}:raise ValueError('native gifted Feature acquisition options required')
    actor.spec['_ace_committing_gift']=parent['request_id']
    try:T.acquire_static(engine,actor,gift['feature'],acquisition_request_id=parent['request_id']+'/gift',**options)
    finally:actor.spec.pop('_ace_committing_gift',None)
    import trainer_retraining as RETRAIN
    import acquisition_withdrawal as WITHDRAWAL
    child=RETRAIN.owned_source(engine,actor,gift['feature'])
    native=RETRAIN._native_dependencies(engine,actor,RETRAIN._owned(actor)).get(gift['feature'],[])
    parents=list(dict.fromkeys([source_id,*[RETRAIN.owned_source(engine,actor,p) for p in native]]))
    WITHDRAWAL.dependencies(engine,actor,child,parents)


def validate_acquisition(actor, record, source_id, active):
    if not active:return
    if record['feature_id']==ELITE:
        gift=record['snapshot']['gift']
        import trainer_feature_acquisition as T
        rows=[r['static_acquisition'] for _,r,_ in T._static_records(actor)
              if r['static_acquisition']['request_id']==record['request_id']+'/gift']
        # The parent is validated once before its nested gifted acquisition.
        if not rows and actor.spec.get('_ace_committing_gift')!=record['request_id']:
            raise ValueError('Elite Trainer requires its actual gifted Feature acquisition')


def require(engine, actor, uid):
    W.require_actors(engine,actor)
    if actor.kind!='trainer' or not acquired(actor,uid):raise ValueError('actual acquired Ace Trainer Feature required: '+uid)
    if engine.r._selected_rule(uid)!=uid:raise ValueError('selected exact Ace Trainer Feature source required')
    if actor.dead or actor.fainted or actor.captured or not actor.on_field:raise ValueError('available actual Trainer required')


def _own(engine, trainer, pokemon):
    import pokemon_activities as P
    W.require_actors(engine,trainer,pokemon)
    P._trainer(trainer);P._pokemon(pokemon);P._owner(trainer,pokemon)


def critical_moment(engine, trainer, targets):
    import training_features as TRAIN
    import frequency as F
    import priority_limited as PRIORITY
    import perception_communicate as COMM
    import order_actions as ORDERS
    require(engine,trainer,CRITICAL)
    if type(targets)not in (list,tuple) or not targets or len({id(t) for t in targets})!=len(targets):raise ValueError('distinct actually trained own Pokemon required')
    for p in targets:
        import commander as COMMANDER
        if not (COMMANDER.transformed_target(engine,trainer,p) or COMMANDER.leadership_target(engine,trainer,p)):
            _own(engine,trainer,p)
        if not any(r['mode']=='training' for r in TRAIN.active(p)):raise ValueError('actual Training Feature applied to each target required')
    quota={'kind':'scene','uses':2}
    if not F.activation_allowed(trainer,CRITICAL,quota,engine=engine):raise ValueError('Critical Moment frequency exhausted')
    if ORDERS.current(engine,trainer,CRITICAL) is None:PRIORITY.preflight(engine,trainer,action=__import__('commander').priority_action(engine,trainer,CRITICAL),source=CRITICAL)
    def apply(e,t,*ps):
        for p in ps:
            declaration={'id':'ace-critical-order','source':CRITICAL,'capabilities':[],'requirements':[],
                'mode':'auditory','range':None,'path':'auditory','medium':[],'consent':{'kind':'none'},'blockers':[],
                'connection':None,'frequency':{'kind':'at_will','uses':1},'retry':None,'distance_exceptions':[]}
            sent=COMM.send(e,t,p,declaration,'Critical Moment',request_id='critical:'+str(len(getattr(e,COMM.KEY,{}).get('attempts',[]))+1))
            if sent['status']!='delivered':raise ValueError('Critical Moment Order communication not delivered')
        if ORDERS.current(e,t,CRITICAL) is not None:
            if len(ps)!=1 or ORDERS.current(e,t,CRITICAL)['target'] is not ps[0]:raise ValueError('targeted Free Critical Moment requires its actual recipient')
            import turn as TURN
            if not TURN.spend(e,t,'standard',CRITICAL):raise ValueError('actual Free Order action required')
            proof=ORDERS.payment(e,t,CRITICAL)
            paid={'id':'free-order:'+proof['parent'],'payment':proof}
        else:paid=PRIORITY.reserve(e,t,action=__import__('commander').priority_action(e,t,CRITICAL),source=CRITICAL,subject=ps[0].entity_id,communication=sent)
        F.consume_activation(t,CRITICAL,quota,engine=e)
        deadline=t.custom_conditions.get('combat_turn_serial',0)+1
        for p in ps:
            for old in list(TIME.records(p)):
                if old.get('ace_critical'):TIME.expire(e,p,old)
            TIME.install(e,p,{'source':CRITICAL,'ace_critical':True,'turn_owner':t,'turn_deadline':deadline,
                'acquisition':acquired(t,CRITICAL)['request_id'],'payment_id':paid['id']})
        return {'source':CRITICAL,'targets':[p.entity_id for p in ps],'turn_deadline':deadline,'payment':deepcopy(paid)}
    return G.transition(engine,trainer,apply,participants=tuple(targets),include_rulings=True)


def training_multiplier(actor, row):
    # Core p60: use has exactly one tag; separately used Orders still stack.
    if row['mode']!='training':return 1
    return 3 if any(r.get('ace_critical') for r in TIME.records(actor)) else 1


def arm_perseverance(engine, trainer, pokemon, *, source, ordinal=1, request_id):
    """Player selects one actual upcoming gain source and ordinal, or declines."""
    require(engine,trainer,PERSEVERANCE);_own(engine,trainer,pokemon)
    C.integer(ordinal,'selected one Injury ordinal',1)
    G._text(request_id,'Perseverance choice request')
    if source is not None:G._text(source,'actual Injury producer source')
    if source is not None:
        import frequency as F,action_points as AP
        if not F.activation_allowed(trainer,PERSEVERANCE+':'+pokemon.entity_id,{'kind':'scene','uses':1},engine=engine):
            raise ValueError('Perseverance once per Scene per target exhausted')
        if AP.available(trainer)<1:raise ValueError('Perseverance requires one available AP')
    def apply(e,t,p):
        p.spec['perseverance_choice']={'trainer_id':t.entity_id,'acquisition':acquired(t,PERSEVERANCE)['request_id'],
            'source':source,'ordinal':ordinal,'request_id':request_id}
        return deepcopy(p.spec['perseverance_choice'])
    return G.transition(engine,trainer,apply,participants=(pokemon,))


def prevent_injury(engine, pokemon, amount, source):
    """Called before adding count or invoking injury-dependent consumers."""
    C.integer(amount,'actual gained Injury count',0)
    choice=pokemon.spec.get('perseverance_choice')
    if not amount or not choice or choice['source']!=source:return amount
    trainer=W.actor_index(engine).get(choice['trainer_id'])
    actual=acquired(trainer,PERSEVERANCE) if trainer is not None else None
    if (actual is None or actual['request_id']!=choice['acquisition'] or pokemon.spec.get('trainer_id')!=choice['trainer_id']
            or trainer.dead or trainer.fainted or trainer.captured or not trainer.on_field):
        pokemon.spec.pop('perseverance_choice')
        return amount
    require(engine,trainer,PERSEVERANCE);_own(engine,trainer,pokemon)
    if choice['ordinal']>amount:raise ValueError('selected Injury ordinal is outside the actual simultaneous gain; select a real gain to resume')
    import action_points as AP
    import frequency as F
    import action_lifecycle as ACTION
    uid=PERSEVERANCE+':'+pokemon.entity_id;quota={'kind':'scene','uses':1}
    if not F.activation_allowed(trainer,uid,quota,engine=engine):raise ValueError('Perseverance once per Scene per target exhausted')
    if AP.available(trainer)<1:raise ValueError('Perseverance requires one available AP')
    ACTION.triggered_free_action(engine,trainer,PERSEVERANCE);AP.charge(trainer,1)
    F.consume_activation(trainer,uid,quota,engine=engine)
    trainer.spec.setdefault('perseverance_preventions',[]).append({**deepcopy(choice),'target_id':pokemon.entity_id,
        'gained':amount,'retained':amount-1,'scene':F.state(trainer)['scene']})
    pokemon.spec.pop('perseverance_choice')
    return amount-1


def _history(spec):return spec.get(KEY,[])


def _hash(row):
    from resolution_transaction import request_fingerprint
    return request_fingerprint({k:v for k,v in row.items() if k!='sha256'})


def _known(rules,spec):
    # Suppression/temporary display overlays do not forget a learned Move.
    state=spec.get('state_grants',{})
    moves=list(spec.get('moves',[]))+list(state.get('legacy',{}).get('moves',[]))
    for row in state.get('sources',{}).values():
        if row.get('move_mode')!='permission':moves.extend(row.get('grants',{}).get('moves',[]))
    return {rules.move_id(mid) for mid in moves}


def validate_spec(rules, spec, *, losing_move=None):
    rows=_history(spec)
    if type(rows)is not list:raise ValueError('Signature Technique history must be a list')
    ids=set();live=[]
    for row in rows:
        if row.get('id') in ids or not isinstance(row.get('id'),str) or row.get('sha256')!=_hash(row):raise ValueError('actual immutable Signature Technique investment required')
        ids.add(row['id'])
        if (row.get('actor_id')!=spec.get('id') or row.get('point_cost')!=2 or row.get('modification') not in MODIFICATIONS
                or row.get('source_clause_id') not in ('C04-011','C2CSV/input/db/feats.csv:R60:main')):
            raise ValueError('exact individual Technique source and two-point investment required')
        source(rules,row['source_contract'],csv_source=row['source_clause_id']!='C04-011')
        if row.get('status')=='active':
            if row['move_id']!=losing_move and row['move_id'] not in _known(rules,spec):raise ValueError('active Technique requires its actually known Move')
            if row.get('refund',0)!=0:raise ValueError('active Technique cannot be refunded')
            live.append(row)
        elif row.get('status') not in ('replaced','forgotten') or row.get('refund')!=1:raise ValueError('ended Technique requires exactly one Tutor Point refund')
    if len(live)>1:raise ValueError('one Signature Technique per Pokemon')
    return True


def active(rules, spec, move_id=None):
    validate_spec(rules,spec)
    return next((r for r in _history(spec) if r['status']=='active' and (move_id is None or r['move_id']==move_id)),None)


def _eligible(rules, move_id, modification, contract):
    import priority_actions as P
    move=P._move(rules,move_id);mm=rules.move_mech(move_id)[0]
    if modification not in MODIFICATIONS:raise ValueError('exact one known Technique modification required')
    group,training,record=MODIFICATIONS[modification];text=move['range'];damaging=move['class'] in ('물리','특수')
    area=any(token in text for token in ('원뿔','직선','파열','폭발','Cone','Line','Burst','Blast'))
    one=bool(re.search(r'(?:대상\s*1|1\s*대상|1\s*Target)',text,re.I))
    if group=='area' and not area or group=='single' and not one or group=='damage' and not damaging or group=='status' and move['class']!='변화':
        raise ValueError('Move does not meet the printed modification category')
    if modification=='vicious_storm' and not damaging:raise ValueError('Vicious Storm requires a Damaging Move')
    if modification=='reliable_attack' and ('강타' in text or 'Smite' in text):raise ValueError('Reliable Attack cannot modify Smite')
    if modification=='double_down':
        db=move.get('damage_base');effects=mm.get('effects_exec',[])
        if (type(db)is not int or not 1<=db<=4 or any(e.get('type') in ('conditional_damage_base','damage_fixed','fixed_damage','special_damage','multi_roll','escalating_damage_base','damage_base_formula') for e in effects)
                or '특수' in str(move.get('damage','')) or __import__('multi_strike').kind(move)
                or __import__('conditional_damage_base').manages(move)):
            raise ValueError('Double Down requires printed DB four or less without conditional DB or special-case damage')
    if modification=='double_curse':
        if not one:raise ValueError('Double Curse requires a one-Target Status Move')
        if source(rules,contract)['double_curse_non_status_enabling_forbidden']:
            if move.get('eng') in ('Copycat','Sketch','Transform') or any(e.get('type') in ('copy_move','copy_last_move','transform','sketch','use_move','move_copy','invoke_move','random_move','repeat_last_move','ally_struggle','attack') for e in mm.get('effects_exec',[])):
                raise ValueError('adopted Double Curse forbids Moves capable of non-Status Move use')
    return move,training,record


def teach_technique(engine, trainer, pokemon, *, move_id, modification, request_id,
                    source_contract='core_1.05', source_clause_id='C04-011'):
    import pokemon_teaching as TEACH
    TEACH._pokemon(engine,trainer,pokemon)
    import turn as TURN
    G._text(request_id,'Technique investment request')
    validate_spec(engine.r,pokemon.spec)
    mid=engine.r.move_id(move_id)
    intent={'trainer_id':trainer.entity_id,'move_id':mid,'modification':modification,
            'source_contract':source_contract,'source_clause_id':source_clause_id}
    old_request=next((r for r in _history(pokemon.spec) if r['id']==request_id),None)
    if old_request:
        if any(old_request.get(k)!=v for k,v in intent.items()):raise ValueError('Technique replay intent changed')
        return deepcopy(old_request)
    require(engine,trainer,SIGNATURE)
    if source_clause_id not in ('C04-011','C2CSV/input/db/feats.csv:R60:main'):raise ValueError('exact Technique body or CSV60 source required')
    source(engine.r,source_contract,csv_source=source_clause_id!='C04-011')
    if TEACH._balance(pokemon.spec)<2:raise ValueError('at least two Tutor Points required before Technique replacement refund')
    if mid not in _known(engine.r,pokemon.spec):raise ValueError('Technique must select an actual Move on its Move List')
    _,training,csv_record=_eligible(engine.r,mid,modification,source_contract)
    if not acquired(trainer,training):raise ValueError('actually acquired associated Training Feature required')
    if engine.encounter_active:raise ValueError('Signature Technique requires an Extended action outside combat')
    def apply(e,t,p):
        if not TURN.spend(e,t,'extended',SIGNATURE):raise ValueError('Technique Extended action unavailable')
        old=active(e.r,p.spec)
        TEACH._debit_points(p.spec,2)
        if old:_retire(p.spec,old,'replaced',at=e.elapsed_seconds,reason=request_id)
        row={'id':request_id,'actor_id':p.entity_id,**intent,'training_acquisition':acquired(t,training)['request_id'],
            'feature_acquisition':acquired(t,SIGNATURE)['request_id'],'point_cost':2,'status':'active','refund':0,
            'csv_reference':'C2CSV/input/db/class-data.csv:R'+str(csv_record)+':technique' if source_clause_id!='C04-011' else None,
            'at':e.elapsed_seconds}
        row['sha256']=_hash(row);p.spec.setdefault(KEY,[]).append(row);validate_spec(e.r,p.spec)
        import trainer_retraining as RETRAIN
        RETRAIN.irreversible(e,t,SIGNATURE,event_id='technique:'+p.entity_id+':'+request_id,
            reason='completed permanent Signature Technique investment in '+p.entity_id)
        return deepcopy(row)
    return G.transition(engine,trainer,apply,participants=(pokemon,))


def _retire(spec,row,status,*,at,reason):
    if row['status']!='active':return
    import pokemon_teaching as TEACH
    G._text(reason,'Technique loss reason')
    row.update(status=status,refund=1,ended_at=at,ending_reason=reason)
    spec['tutor_points']=TEACH._balance(spec)+1
    row['sha256']=_hash(row)


def forget_spec(rules,spec,move_id,*,at,reason):
    validate_spec(rules,spec,losing_move=move_id)
    row=next((r for r in _history(spec) if r['status']=='active' and r['move_id']==move_id),None)
    if row is not None:_retire(spec,row,'forgotten',at=at,reason=reason)
    return deepcopy(row)


def prepare(engine,actor,move):
    row=active(engine.r,actor.spec,move['id']);marker=move.get(MARKER)
    if row is None:
        if marker is not None:raise ValueError('stale Signature Technique projection')
        return move
    expected={'investment_id':row['id'],'actor_id':actor.entity_id,'modification':row['modification'],'source_contract':row['source_contract']}
    if marker is not None:
        if marker!=expected:raise ValueError('Technique projection source changed')
        return move
    out=deepcopy(move);mod=row['modification'];range_text=out['range'];values=source(engine.r,row['source_contract'])
    if mod=='scattershot':
        out['range']='4m, 대상'+str(values['scattershot_targets'])
        out['_class_move_range']={'raw':out['range'],'origin':4,'targets':values['scattershot_targets'],'parsed':True}
    elif mod=='vicious_storm':
        out['range']+=', 강타'
        out['keywords']=list(dict.fromkeys([*(out.get('keywords') or []),'강타']))
    elif mod=='alternative_energy':out['class']='특수' if out['class']=='물리' else '물리'
    elif mod=='double_down':out['range']+=', 이단타격'
    elif mod=='double_curse':
        out['range']=re.sub(r'대상\s*1|1\s*대상|1\s*Target','대상2',range_text,flags=re.I)
        out['_class_move_range']=dict(__import__('weapon_actions').range_spec(engine,move,actor),raw=out['range'],targets=2)
    out[MARKER]=expected
    return out


def selected_targets(engine,actor,move,candidates,primary):
    marker=move.get(MARKER)
    if not marker or marker['modification'] not in ('scattershot','double_curse'):return None
    if prepare(engine,actor,engine.r.move(move['id'])).get(MARKER)!=marker:
        raise ValueError('actual source-owned Technique target projection required')
    import weapon_actions as WEAPONS,body_state as BODY
    rng=WEAPONS.range_spec(engine,move,actor)
    if not candidates or candidates[0] is not primary or len(candidates)>rng['targets']:
        raise ValueError('select the actual primary and no more than the Technique target maximum')
    if len({id(p) for p in candidates})!=len(candidates):raise ValueError('distinct actual Technique recipients required')
    if marker['modification']=='double_curse' and any(p.side==actor.side for p in candidates):
        raise ValueError('Double Curse selects actual foes')
    reach=BODY.melee_reach(actor) if rng.get('origin')=='melee' else rng['origin']
    if any(not BODY.in_range(engine,actor,p,reach,move=move) for p in candidates):
        raise ValueError('all selected Technique recipients must be in the actual Move range')
    return list(candidates)


def vicious_storm(engine,actor,move):
    marker=move.get(MARKER)
    return bool(marker and marker['modification']=='vicious_storm' and move['class'] in ('물리','특수')
        and prepare(engine,actor,engine.r.move(move['id'])).get(MARKER)==marker)


def mechanics(engine, actor, move, mechanics):
    row=active(engine.r,actor.spec,move['id'])
    if row is None:return mechanics
    out=deepcopy(mechanics)
    if row['modification']=='double_down':
        strike_authority(engine,actor,move)
        out['effects_exec']=[x for x in out.get('effects_exec',[]) if x.get('type')!='multi_roll']
        out['effects_exec'].append({'type':'multi_roll','rolls':2,'crit_if_any_crit':True})
    return out


def strike_authority(engine,actor,move):
    row=active(engine.r,actor.spec,move['id'])
    if not row or row['modification']!='double_down':return False
    if prepare(engine,actor,engine.r.move(move['id'])).get(MARKER)!=move.get(MARKER):raise ValueError('Double Down requires actual source-owned Move projection')
    _eligible(engine.r,move['id'],'double_down',row['source_contract'])
    return {'source':SIGNATURE,'investment_id':row['id'],'actor_id':actor.entity_id,'source_contract':row['source_contract']}


def validate_strike_record(engine,actor,record):
    authority=record.get('technique_authority',{})
    rows=[r for r in _history(actor.spec) if r['id']==authority.get('investment_id')]
    if (len(rows)!=1 or rows[0]['modification']!='double_down' or rows[0]['move_id']!=record['move_id']
            or record['kind']!='double' or authority!={'source':SIGNATURE,'investment_id':rows[0]['id'],
                'actor_id':actor.entity_id,'source_contract':rows[0]['source_contract']}):
        raise ValueError('historical Double Down strike requires its actual source-authorized investment')
    validate_spec(engine.r,actor.spec)
    return True


def timed(actor,kind=None):
    return [r for r in TIME.records(actor) if r.get('ace_technique') and (kind is None or r['ace_technique']==kind)]


def _effect(engine,actor,target,row,kind,completion,*,next_user_turn=False,one_round=False,**fields):
    receipt={'source':SIGNATURE,'ace_technique':kind,'technique_id':row['id'],'completion_id':completion,
             'user_id':actor.entity_id,**fields}
    if next_user_turn:receipt.update(turn_owner=actor,turn_deadline=actor.custom_conditions.get('combat_turn_serial',0)+1)
    if one_round:receipt['count_deadline']=[engine.round_no+1,TIME.current(engine)]
    return TIME.install(engine,target,receipt)


def after_target(engine,completion,target):
    actor=completion['actor'];move=completion.get('target_moves',{}).get(target.entity_id,completion['move'])
    marker=move.get(MARKER)
    if not marker:return
    result=__import__('move_completion').recipient_result(completion,target)
    if not result or result.get('cancelled'):return
    row=next(r for r in _history(actor.spec) if r['id']==marker['investment_id']);mod=row['modification']
    token=target.entity_id+':'+mod
    if token in completion.setdefault('ace_target_effects',[]):return
    completion['ace_target_effects'].append(token)
    if mod=='shock_and_awe' and target.side!=actor.side:
        _effect(engine,actor,target,row,mod,completion['id'],next_user_turn=True,save_modifier=-2,evasion_modifier=-1)
    elif mod=='guarding_strike' and result['hit']:
        _effect(engine,actor,actor,row,mod,completion['id'],next_user_turn=True,against_id=target.entity_id,damage_reduction=5)
    elif mod=='unbalancing_blow':
        _effect(engine,actor,target,row,mod,completion['id'],one_round=True,evasion_zero=True)


def after_damaging_hit(engine,target,completion_id):
    for r in list(timed(target,'unbalancing_blow')):
        if r['completion_id']!=completion_id:TIME.expire(engine,target,r,event={'kind':'next_damaging_hit','completion_id':completion_id})


def evasion(actor):return sum(r.get('evasion_modifier',0) for r in timed(actor))
def save_bonus(actor):return sum(r.get('save_modifier',0) for r in timed(actor))
def damage_reduction(actor,attacker):return max([r.get('damage_reduction',0) for r in timed(actor,'guarding_strike') if r['against_id']==attacker.entity_id]+[0])


def validate_world(engine,index):
    for actor in index.values():
        validate_spec(engine.r,actor.spec)
        for investment in _history(actor.spec):
            owner=index.get(investment['trainer_id'])
            if owner is None:raise ValueError('Technique requires its actual investing Trainer history')
            history=records(owner)
            training=MODIFICATIONS[investment['modification']][1]
            if (not any(r['feature_id']==SIGNATURE and r['request_id']==investment['feature_acquisition'] for r in history)
                    or not any(r['feature_id']==training and r['request_id']==investment['training_acquisition'] for r in history)):
                raise ValueError('Technique requires its actual Feature and associated Training acquisition histories')
        for effect in TIME.records(actor):
            if effect.get('ace_critical'):
                owner=effect.get('turn_owner')
                if (index.get(getattr(owner,'entity_id',None)) is not owner or
                        not any(r['request_id']==effect.get('acquisition') for r in records(owner,CRITICAL))):
                    raise ValueError('Critical Moment needs its actual issuing acquisition and turn owner')
        for row in timed(actor):
            completion=getattr(engine,'_move_completions',{}).get(row.get('completion_id'))
            if completion is None or completion['actor'] is not index.get(row.get('user_id')):
                raise ValueError('Technique timed effect requires its actual Move completion')
    return True


def withdraw(engine,trainer,feature):
    """Withdraw live permissions; printed durable investments keep their history."""
    if feature not in FEATURES:return
    for target in W.actor_index(engine).values():
        if feature==CRITICAL:
            for row in list(TIME.records(target)):
                if row.get('ace_critical') and row.get('turn_owner') is trainer:TIME.expire(engine,target,row)
        if feature==PERSEVERANCE and target.spec.get('perseverance_choice',{}).get('trainer_id')==trainer.entity_id:
            target.spec.pop('perseverance_choice')


def trained_stat_choices(trainer, trained_stats, targets):
    import combat_stage_sources as CS
    if type(trained_stats)is not dict or set(trained_stats)!={p.entity_id for p in targets}:
        raise ValueError('each actual trained Pokemon needs its trained non-HP stats')
    sizes=[]
    for value in trained_stats.values():
        stats=[value] if type(value)is str else value
        if type(stats)not in (list,tuple) or not stats or len(stats)>2 or len(set(stats))!=len(stats) or any(s not in CS.STATS for s in stats):
            raise ValueError('one non-HP trained stat or two different non-HP Champ stats required')
        sizes.append(len(stats))
    if 2 in sizes:
        if set(sizes)!={2} or not acquired(trainer,CHAMP):raise ValueError('actual Champ in the Making grants exactly two different stats to each recipient')
        return acquired(trainer,CHAMP)['request_id']
    return None


def forget_missing(rules,spec,*,at,reason):
    for row in _history(spec):
        if row['status']=='active' and row['move_id'] not in _known(rules,spec):
            _retire(spec,row,'forgotten',at=at,reason=reason)


def top_source(actor):
    record=acquired(actor,TOP)
    return record['source']['clause_id'] if record else None


def before_frequency(engine,actor,move_id):
    """Capture the real frequency owner before native consumption, once."""
    row=active(engine.r,actor.spec,move_id)
    if not row or row['modification']!='reliable_attack':return
    import frequency as F
    import move_permissions as P
    owner=P.frequency_owner(engine,actor,move_id)
    state=F.state(owner)
    actor.custom_conditions['ace_reliable_frequency']={'move_id':move_id,'investment_id':row['id'],'owner_id':owner.entity_id,
        'uses':owner.move_uses.get(move_id),'occurrence':deepcopy(state['moves'].get(move_id)),
        'last_move':owner.last_move,'scene':state['scene'],'turn':state['turn'],'day':state['day']}


def begin_move(engine,completion):
    actor=completion['actor'];move=completion['move'];row=active(engine.r,actor.spec,move['id'])
    if not row:return
    completion['ace_technique_investment']=row['id']
    if row['modification']=='reliable_attack':
        # Native completion creation precedes this activation's consume_move.
        before_frequency(engine,actor,move['id'])
        snapshot=actor.custom_conditions.pop('ace_reliable_frequency',None)
        if snapshot is None or snapshot['investment_id']!=row['id']:raise ValueError('Reliable Attack requires its actual native frequency consumption boundary')
        completion['ace_reliable_frequency']=snapshot


def _completion(engine,actor,completion_id,modification):
    row=getattr(engine,'_move_completions',{}).get(completion_id)
    if row is None or row['actor'] is not actor or row['phase']!='complete' or not row['sealed']:
        raise ValueError('actual completed Signature Technique Move required')
    marker=row['move'].get(MARKER)
    if marker is None or marker['modification']!=modification or row.get('ace_technique_investment')!=marker['investment_id']:
        raise ValueError('actual source-owned Technique completion required')
    if (row['round']!=engine.round_no or row['turn_serial']!=actor.custom_conditions.get('combat_turn_serial',0)
            or row['completed_at']!=engine.elapsed_seconds):
        raise ValueError('immediate Signature Technique completion opportunity has ended')
    return row


def after_move(engine,completion):
    marker=completion['move'].get(MARKER)
    if marker is None or completion.get('ace_after_move'):return
    if completion['phase']!='complete':raise ValueError('Technique needs whole actual Move completion')
    completion['ace_after_move']=True
    if marker['modification']=='reliable_attack':
        results=[v for v in completion['results'].values() if not v['cancelled']]
        if results and all(not r['hit'] for r in results):
            fact=completion['ace_reliable_frequency'];owner=W.actor_index(engine)[fact['owner_id']]
            import frequency as F
            state=F.state(owner);mid=completion['move_id']
            if any(state[k]!=fact[k] for k in ('scene','day','turn')):raise ValueError('Reliable Attack cannot restore across a frequency boundary')
            if fact['uses'] is None:owner.move_uses.pop(mid,None)
            else:owner.move_uses[mid]=fact['uses']
            owner.spec['move_uses']=dict(owner.move_uses)
            if fact['occurrence'] is None:state['moves'].pop(mid,None)
            else:state['moves'][mid]=deepcopy(fact['occurrence'])
            completion['ace_reliable_offer']={'target_ids':[t.entity_id for t in completion['targets']],
                'used':False,'action_history':deepcopy(getattr(completion['actor'],'_action_history',[]))}
    elif marker['modification']=='burst_of_motivation':
        completion['ace_motivation_offer']={'used':False,'action_history':deepcopy(getattr(completion['actor'],'_action_history',[]))}


def reliable_struggle(engine,pokemon,target,completion_id):
    W.require_actors(engine,pokemon,target)
    row=_completion(engine,pokemon,completion_id,'reliable_attack');offer=row.get('ace_reliable_offer')
    if (not offer or offer['used'] or target.entity_id not in offer['target_ids']
            or offer['action_history']!=getattr(pokemon,'_action_history',[])):
        raise ValueError('one immediate actual Reliable Attack miss Struggle opportunity required')
    def apply(e,p,t):
        row=_completion(e,p,completion_id,'reliable_attack');row['ace_reliable_offer']['used']=True
        e._ace_reliable_scope={'actor':p,'target':t,'completion_id':completion_id}
        import action_lifecycle as ACTION
        try:
            with ACTION.move_grant(e,p,t,'struggle',source=SIGNATURE,kind='free') as grant:
                return e.use_move(p,t,'struggle',count_use=False,free_action=True,_action_grant=grant)
        finally:del e._ace_reliable_scope
    return G.transition(engine,pokemon,apply,participants=(target,),include_rulings=True,include_grid=engine.grid is not None)


def move_authority(engine,actor,target,move_id,source_id):
    if source_id!=SIGNATURE:return False
    scope=getattr(engine,'_ace_reliable_scope',None)
    if not scope or scope['actor'] is not actor or scope['target'] is not target or move_id!='struggle':return False
    row=_completion(engine,actor,scope['completion_id'],'reliable_attack')
    return bool(row.get('ace_reliable_offer',{}).get('used'))


def motivation(engine,pokemon,completion_id,choices):
    W.require_actors(engine,pokemon)
    row=_completion(engine,pokemon,completion_id,'burst_of_motivation');offer=row.get('ace_motivation_offer')
    if not offer or offer['used'] or offer['action_history']!=getattr(pokemon,'_action_history',[]):raise ValueError('one actual completed Move Burst of Motivation opportunity required')
    import combat_stage_sources as CS
    if type(choices)is not dict or set(choices)-set(CS.STATS):raise ValueError('actual non-HP stat motivation choices required')
    for stat,amount in choices.items():
        C.integer(amount,'optional Motivation stage increase',0,2)
        if pokemon.stages[stat]>=0 or pokemon.stages[stat]+amount>0:raise ValueError('Motivation raises only negative stages and never above zero')
    def apply(e,p):
        row=_completion(e,p,completion_id,'burst_of_motivation');row['ace_motivation_offer']['used']=True
        for stat,amount in choices.items():e.change_stage(p,stat,amount)
        return dict(choices)
    return G.transition(engine,pokemon,apply)


def supreme(engine,actor,move=None):
    """Exception for the selected actual Status Move, never condition immunity."""
    if move is None:
        frames=getattr(engine,'_native_action_stack',[])
        frame=frames[-1] if frames else None
        if frame is None or frame['actor'] is not actor or frame['kind']!='move':return False
        mid=frame['source']
    else:mid=move['id']
    row=active(engine.r,actor.spec,mid)
    return bool(row and row['modification']=='supreme_concentration')


def supreme_limit(engine,actor,limit,move=None):
    if not supreme(engine,actor,move):return False
    if limit.get('source')=='condition/혼란':
        mid=move['id'] if move else getattr(engine,'_native_action_stack',[])[-1]['source']
        chosen=actor.spec.get('supreme_concentration_choice',{})
        return (limit.get('signature_choice')==chosen.get('request_id') and chosen.get('move_id')==mid
                and chosen.get('status')=='failed_save' and chosen.get('turn')==actor.custom_conditions.get('combat_turn_serial',0))
    return '마비' in actor.conditions and limit in engine.r.condition_effects('마비')


def choose_supreme(engine,actor,*,move_id,request_id):
    W.require_actors(engine,actor);G._text(request_id,'actual Supreme Concentration choice')
    if getattr(engine,'_active_turn_actor',None) is actor:raise ValueError('choose Supreme Concentration before the actual turn starts')
    if move_id is not None:
        mid=engine.r.move_id(move_id)
        if not supreme(engine,actor,{'id':mid}):raise ValueError('choose the actually owned Supreme Concentration Technique')
    else:mid=None
    def apply(e,a):
        a.spec['supreme_concentration_choice']={'move_id':mid,'request_id':request_id,'status':'armed',
            'turn':a.custom_conditions.get('combat_turn_serial',0)+1}
        return deepcopy(a.spec['supreme_concentration_choice'])
    return G.transition(engine,actor,apply)


def replace_core_confusion(engine,actor,result):
    """Core p247/p76 interpretation: no extra Standard or Free activation."""
    choice=actor.spec.get('supreme_concentration_choice',{})
    if (choice.get('status')!='armed' or choice.get('move_id') is None
            or choice.get('turn')!=actor.custom_conditions.get('combat_turn_serial',0)):
        return False
    if not supreme(engine,actor,{'id':choice['move_id']}):raise ValueError('preselected Supreme Concentration investment changed')
    choice['status']='failed_save'
    actor._turn_action_limit={'source':'condition/혼란','choose_one_of':[],'signature_choice':choice['request_id']}
    result.update(outcome='selected_supreme_concentration',move_id=choice['move_id'],choice_request=choice['request_id'],
                  interpretation='Core p247 self-attack replaced by p76 selected-Move exception; normal action cost')
    return True


def bloodied_authority(engine,actor,move_id):
    row=active(engine.r,actor.spec,move_id)
    if not row or row['modification']!='bloodied_speed':return None
    if actor.hp*2>=actor.max_hp:raise ValueError('Bloodied Speed requires strictly below half maximum HP')
    return {'source':SIGNATURE,'investment_id':row['id'],'modification':'bloodied_speed'}


def priority_bloodied(engine,actor,target,move_id):
    """Native Priority Advanced turn loan, retaining all normal turn consumers."""
    import priority_actions as P
    return P.use(engine,actor,target,move_id,signature_technique=True)
