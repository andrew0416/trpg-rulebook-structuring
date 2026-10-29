"""Captured Momentum: actual capture event, explicit choice, native consumers."""
from copy import deepcopy
from contextvars import ContextVar
import common_checks as C
import skill_modifiers as SKILL_RANKS
import trainer_feature_acquisition as TFA
import capture_techniques as CT
import acquired_features as A
import combat_timing as T
import effect_instances as E

FEATURE='feat/포획-추진력'
CLAUSE='input/ch04-trainer-classes.md:388-396'
KIND='captured_momentum'
_RESOLVING=ContextVar('captured_momentum_choice',default=None)
CONVERSION='구판 1d100 보정치의 부호를 뒤집고 5로 나눈다 (슈퍼볼 +2, 하이퍼볼 +3, 타이머볼 -1→+4, 포획전문가의 덫 +2)'

def acquisition_snapshot(actor):
    CT.validate_actor(actor)
    receipts=[r['receipt_id'] for r in CT._rows(actor) if r['feature_id']==CT.ADVANCED]
    return {'rank':A.owned_rule_count(actor,CT.ADVANCED),'parent_receipts':receipts}

def qualification(actor,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!={'rank','parent_receipts'}:
        raise ValueError('exact Captured Momentum acquisition observations required')
    rank=C.integer(snapshot['rank'],'Advanced Capture rank',0,4)
    receipts=snapshot['parent_receipts']
    actual={r['receipt_id']:r for r in actor.spec.get(TFA.LEDGER_KEY,{}).values() if r.get('adapter_id')==CT.ADAPTER and r.get('feature_id')==CT.ADVANCED}
    if type(receipts) is not list or len(receipts)!=rank or len(set(receipts))!=rank or any(uid not in actual for uid in receipts):
        raise ValueError('Captured Momentum requires actual acquired Advanced Capture receipts')
    if sorted(actual[uid]['selection']['acquisition_snapshot']['rank'] for uid in receipts)!=list(range(1,rank+1)):
        raise ValueError('Captured Momentum parent ranks changed')
    return Q.require(FEATURE,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual trainer required'),
        Q.check('advanced_capture_rank','prerequisite',rank>=2,'Advanced Capture Techniques rank 2 required')])

def acquired(actor):
    TFA.validate_actor(actor)
    rows=[row['static_acquisition'] for _,row,active in TFA._static_records(actor) if active and row['static_acquisition']['feature_id']==FEATURE]
    if A.owned_rule_count(actor,FEATURE) and not rows:raise ValueError('Captured Momentum requires its actual acquisition source')
    return rows[0] if rows else None

def live(actor):return [r for r in T.records(actor) if r.get(E.KEY,{}).get('kind')==KIND]
def history(actor):return [r for r in actor.spec.get('effect_instance_history',[]) if r.get(E.KEY,{}).get('kind')==KIND]

def pending(engine):
    import world_entities as W
    return [(a,attempt) for a in W.actor_index(engine).values() for attempt in a.spec.get('capture_attempts',{}).values() if attempt.get('momentum',{}).get('state')=='pending']

def ensure_clear(engine):
    if _RESOLVING.get() is not None:return
    if pending(engine):raise ValueError('Captured Momentum capture-success choice is pending')

def after_capture(engine,actor,target,attempt):
    receipt=acquired(actor)
    if receipt is None:return
    # Native caller has already consumed the actual ball and committed placement.
    attempt['momentum']={'state':'pending','actor_id':actor.entity_id,'target_id':target.entity_id,
        'source':deepcopy(receipt['source']),'acquisition_request_id':receipt['request_id'],
        'round':engine.round_no,'at':engine.elapsed_seconds,'choice':None,'effect_id':None}

def _attempt(actor,attempt_id):
    attempt=actor.spec.get('capture_attempts',{}).get(attempt_id)
    if not isinstance(attempt,dict) or not attempt.get('momentum'):raise ValueError('actual capture-success trigger required')
    event=attempt['momentum']
    if type(event) is not dict or set(event)!={'state','actor_id','target_id','source','acquisition_request_id','round','at','choice','effect_id'}:
        raise ValueError('exact actual capture-success event required')
    C.integer(event['round'],'capture trigger round',0);C.integer(event['at'],'capture trigger time',0)
    if attempt.get('id')!=attempt_id or attempt.get('status')!='captured' or attempt.get('captured') is not True or attempt.get('hit') is not True:
        raise ValueError('Captured Momentum cannot use a failed or fabricated capture')
    if event['actor_id']!=actor.entity_id or event['source']!=TFA._static_source(actor.r,FEATURE):raise ValueError('capture trigger actor/source changed')
    rows=[r['static_acquisition'] for _,r,_ in TFA._static_records(actor) if r['static_acquisition']['feature_id']==FEATURE and r['static_acquisition']['request_id']==event['acquisition_request_id']]
    if len(rows)!=1:raise ValueError('capture event requires its actual acquired source')
    resolution=attempt.get('resolution',{})
    if resolution.get('captured') is not True or resolution.get('total')!=attempt.get('capture_total') or not attempt.get('placement'):
        raise ValueError('capture trigger needs actual successful resolution and placement')
    return attempt,event

def _owner(actor,target):
    if target is actor:return
    if target.kind!='pokemon' or target.spec.get('trainer_id')!=actor.entity_id:raise ValueError('accuracy beneficiary must be this trainer or their actual Pokemon')

def conversion_plan(engine,actor,conversion,capture_source=None):
    import arithmetic_policy as M
    import capture_resolution as RESOLUTION
    import skill_modifiers as SKILLS
    procedure,selected=RESOLUTION.bind_native(engine.r,capture_source)
    ordinary={skill:SKILLS.rank(engine.r,actor,skill)[2] for skill in CT.SKILLS}
    ranks={skill:SKILLS.effective_rank(engine.r,actor,skill) for skill in CT.SKILLS}
    maximum=max(ranks.values())
    import capture_specialist as CS
    variant=CS.feature_variant(actor,FEATURE)
    if variant==CS.CSV:
        if conversion is not None or procedure.sides!=20:raise ValueError('CSV Captured Momentum is fixed +2 on its d20 capture procedure')
        value=2;basis={'kind':'csv_fixed','modifier':2,'source':CS._file(engine.r,'input/db/feats.csv'),'record':74}
    elif procedure.sides==100:
        if conversion is not None:raise ValueError('Core Captured Momentum uses its original six-skill modifier')
        value=-maximum;basis={'kind':'core_original'}
    elif conversion is None:
        if selected.get('ball_modifier_conversion')!=CONVERSION:raise ValueError('Book capture modifier needs selected errata conversion or explicit GM conversion')
        import source_context as SOURCE
        authority={'file':'input/supp-errata.md','sha256':'90e533bde766c6ffe8fb480dd8e2478e5fddf3ed1fef9a7a1032070245622a3e'}
        SOURCE.verified_source(engine.r,authority,label="Captured Momentum errata conversion")
        # Rules.mech validates the selected errata patch; the exact field is retained.
        value=M.ratio(maximum,5);basis={'kind':'selected_errata','field':CONVERSION,'lines':[765,769],'rounding':'gameplay/general-rounding','source':authority}
    else:
        if type(conversion) is not dict or set(conversion)!={'modifier','reason','scope'} or conversion['scope']!='next_capture_roll':
            raise ValueError('explicit GM capture modifier, reason and next_capture_roll scope required')
        value=C.integer(conversion['modifier'],'GM capture modifier');E.text(conversion['reason'],'GM capture conversion reason')
        basis={'kind':'gm_ruling',**deepcopy(conversion)}
    return {'skills':ranks,'ordinary_skills':ordinary,'book_modifier':-maximum,'modifier':value,'procedure':{'source':procedure.source,'sides':procedure.sides,'comparison':procedure.comparison},'basis':basis}

def choose(engine,actor,*,attempt_id,choice,target=None,conversion=None,composition=None,ap_policy=None,capture_source=None):
    import world_entities as W,state_grants as G,turn as TURN,temporary_ap as AP
    W.require_actors(engine,actor,*(() if target is None else (target,)))
    attempt,event=_attempt(actor,attempt_id)
    if event['state']!='pending':raise ValueError('capture-success trigger already resolved')
    if choice not in ('decline','accuracy','capture','temporary_ap'):raise ValueError('choose exactly one Captured Momentum benefit or decline')
    if choice!='accuracy' and target is not None:raise ValueError('only accuracy chooses a beneficiary')
    if choice!='capture' and conversion is not None:raise ValueError('capture conversion belongs only to capture choice')
    if choice!='capture' and capture_source is not None:raise ValueError('capture procedure belongs only to capture choice')
    if choice!='temporary_ap' and ap_policy is not None:raise ValueError('temporary AP funding belongs only to AP choice')
    if choice=='decline':
        if composition is not None:raise ValueError('decline has no composition')
        def decline(se,sa):sa.spec['capture_attempts'][attempt_id]['momentum']['state']='declined';return {'status':'declined'}
        return G.transition(engine,actor,decline)
    if acquired(actor) is None:raise ValueError('capture feature is no longer acquired')
    if choice!='temporary_ap' and (not engine.encounter_active or engine.round_start_seconds is None):raise ValueError('next-roll benefit requires the actual encounter context')
    if engine.round_no!=event['round'] or engine.elapsed_seconds!=event['at']:raise ValueError('capture-success choice window has passed')
    target=actor if target is None else target
    _owner(actor,target)
    plan=conversion_plan(engine,actor,conversion,capture_source) if choice=='capture' else None
    if choice=='temporary_ap':
        AP.policy(ap_policy)
        if engine.encounter_active:T.current(engine)
    overlaps=[r for r in live(target) if r['effect']['choice']==choice and r[E.KEY]['applied_by_actor_id']==actor.entity_id]
    if overlaps:
        if type(composition) is not dict or set(composition)!={'mode','reason'} or composition['mode'] not in ('add','replace'):
            raise ValueError('same-source next-roll composition requires explicit GM add/replace and reason')
        E.text(composition['reason'],'GM next-roll composition reason')
    elif composition is not None:raise ValueError('no existing benefit for this composition ruling')
    def apply(se,sa,st):
        row,event=_attempt(sa,attempt_id)
        token=_RESOLVING.set((sa.entity_id,attempt_id))
        try:
            if not TURN.spend(se,sa,'free','Captured Momentum'):raise ValueError('actual Free action permission required')
        finally:_RESOLVING.reset(token)
        origin={'actor_id':sa.entity_id,'attempt_id':attempt_id,'acquisition_request_id':event['acquisition_request_id']}
        if choice=='temporary_ap':effect=AP.grant(se,sa,source=FEATURE,amount=1,origin=origin,funding=ap_policy)
        else:
            if composition and composition['mode']=='replace':
                for old in list(live(st)):
                    if old['effect']['choice']==choice and old[E.KEY]['applied_by_actor_id']==sa.entity_id:T.expire(se,st,old,event={'kind':'gm_replace','reason':composition['reason']})
            effect=E.create(se,st,kind=KIND,source=FEATURE,payload={'kind':KIND,'choice':choice,'amount':2 if choice=='accuracy' else plan['modifier'],'capture_plan':plan},
                capacity={'bucket':'explicit_composition','source':FEATURE},lifetime={'boundary':'encounter_end'},applied_by=sa)
            effect.update(origin=origin,issued_round=se.round_no,manual_end=False,encounter_end=True,applications=[],composition=deepcopy(composition))
            T.install(se,st,effect)
        event.update(state='issued',choice=choice,effect_id=effect['id'])
        return {'status':'issued','choice':choice,'effect_id':effect['id']}
    return G.transition(engine,actor,apply,participants=(target,))

def validate_effect_origin(actor,row):
    origin=row.get('origin')
    if type(origin) is not dict or set(origin)!={'actor_id','attempt_id','acquisition_request_id'} or row[E.KEY].get('applied_by_actor_id')!=origin['actor_id']:
        raise ValueError('Momentum effect needs exact actual capture origin')
    if row[E.KEY]['kind']=='temporary_ap' and row['effect']['amount']!=1:raise ValueError('Captured Momentum grants exactly one temporary AP')
    if actor.entity_id==origin['actor_id']:
        _,event=_attempt(actor,origin['attempt_id'])
        if event['state']!='issued' or event['effect_id']!=row['id'] or event['acquisition_request_id']!=origin['acquisition_request_id']:
            raise ValueError('Momentum effect and consumed capture-success choice disagree')

def _validate_skill_observations(actor,plan):
    ranks=plan['skills']
    if type(ranks)is not dict or set(ranks)!=set(CT.SKILLS):
        raise ValueError('exact six skill rank evidence required')
    for value in ranks.values():
        SKILL_RANKS.validate_rank_value(actor.r,value,kind='effective',label='captured skill rank')
    if 'ordinary_skills' in plan:
        ordinary=plan['ordinary_skills']
        if type(ordinary)is not dict or set(ordinary)!=set(CT.SKILLS):
            raise ValueError('exact six ordinary skill observations required')
        for value in ordinary.values():
            SKILL_RANKS.validate_rank_value(actor.r,value,label='captured ordinary skill rank')
    if plan['book_modifier']!=-max(ranks.values()):
        raise ValueError('actual capture roll skill observation changed')


def validate_record(actor,row,*,terminal=False,consuming=False):
    E.validate(row,actor=actor,terminal=terminal);validate_effect_origin(actor,row)
    payload=row['effect'];choice=payload.get('choice')
    if row['source']!=FEATURE or payload.get('kind')!=KIND or choice not in ('accuracy','capture') or set(payload)!={'kind','choice','amount','capture_plan'}:
        raise ValueError('Captured Momentum payload changed')
    if row[E.KEY]['lifetime']!={'boundary':'encounter_end'} or row.get('manual_end') is not False or any(k in row for k in ('count_deadline','round_end_deadline','turn_owner')):
        raise ValueError('next roll is limited to this encounter')
    if choice=='accuracy' and (payload['amount']!=2 or payload['capture_plan'] is not None):raise ValueError('Momentum accuracy must be +2')
    if choice=='capture':
        plan=payload['capture_plan']
        _validate_skill_observations(actor,plan)
        if plan['procedure'] not in ({'source':'pokemon/capture-rate','sides':20,'comparison':'>='},{'source':'core_105/capture-p214','sides':100,'comparison':'<='}):raise ValueError('Momentum selected capture procedure changed')
        basis=plan['basis']
        expected=__import__('arithmetic_policy').ratio(-plan['book_modifier'],5) if basis['kind']=='selected_errata' else plan['book_modifier'] if basis['kind']=='core_original' else basis['modifier']
        if basis['kind']=='selected_errata' and basis['field']!=CONVERSION:raise ValueError('selected errata conversion changed')
        if basis['kind']=='gm_ruling' and (basis.get('scope')!='next_capture_roll' or not basis.get('reason')):raise ValueError('GM conversion scope changed')
        if basis['kind']=='csv_fixed' and (basis.get('record')!=74 or basis.get('modifier')!=2 or plan['procedure']['sides']!=20):raise ValueError('CSV Momentum fixed +2 source changed')
        if basis['kind']=='core_original' and (set(basis)!={'kind'} or plan['procedure']['sides']!=100):raise ValueError('Core Momentum original modifier changed')
        if basis['kind'] not in ('gm_ruling','selected_errata','csv_fixed','core_original'):raise ValueError('unknown Momentum source policy')
        if plan['modifier']!=expected or payload['amount']!=expected:raise ValueError('Momentum capture conversion changed')
    if row[E.KEY]['capacity']!={'bucket':'explicit_composition','source':FEATURE}:raise ValueError('Momentum capacity changed')
    C.integer(row.get('issued_round'),'Momentum issuing round',1)
    applications=row.get('applications')
    if type(applications) is not list or len(applications)>1:raise ValueError('next roll may be consumed once')
    for application in applications:
        keys={'kind','move_id','target_id','natural'} if choice=='accuracy' else {'kind','attempt_id','target_id','capture_plan'}
        if type(application) is not dict or set(application)!=keys or application['kind']!=choice+'_roll':raise ValueError('exact actual next-roll consumption required')
        E.text(application['target_id'],'actual roll target')
        if choice=='accuracy':C.integer(application['natural'],'actual accuracy face',1,20);E.text(application['move_id'],'actual accuracy Move')
        else:
            observed=application['capture_plan']
            _validate_skill_observations(actor,observed)
            if observed['basis']!=payload['capture_plan']['basis'] or observed['procedure']!=payload['capture_plan']['procedure']:raise ValueError('actual capture procedure differs from granted policy')
            expected=__import__('arithmetic_policy').ratio(-observed['book_modifier'],5) if observed['basis']['kind']=='selected_errata' else observed['book_modifier'] if observed['basis']['kind']=='core_original' else observed['basis']['modifier']
            if observed['modifier']!=expected:raise ValueError('actual capture modifier changed')
    expected_count=1 if (terminal and row[E.KEY]['state']=='consumed') or (not terminal and consuming) else 0
    if len(applications)!=expected_count:raise ValueError('Momentum active/consumed state must match its actual one-shot application count')
    return True

def eligible(engine,actor,choice):
    import world_entities as W
    index=W.actor_index(engine);rows=[]
    for row in live(actor):
        validate_record(actor,row)
        owner=index.get(row['origin']['actor_id'])
        if owner is None:raise ValueError('Momentum issuing trainer is missing')
        if row['effect']['choice']==choice and (actor is owner or actor.kind=='pokemon' and actor.spec.get('trainer_id')==owner.entity_id):rows.append(row)
    return rows

def preflight_accuracy(engine,actor,target,move,shared_roll):
    ensure_clear(engine)
    if eligible(engine,actor,'accuracy') and shared_roll is not None:
        import roll_effects as R
        scope,index=R.accuracy_scope(engine,actor,target,move,shared_roll)
        if scope is None:raise ValueError('Momentum shared accuracy needs actual native roll authority')

def accuracy(engine,actor,target,move,natural,shared_roll):
    import roll_effects as R
    scope,index=R.accuracy_scope(engine,actor,target,move,shared_roll)
    cache=scope.setdefault('momentum_uses',{}) if scope is not None else None
    if cache is not None and index in cache:return cache[index]
    rows=eligible(engine,actor,'accuracy');total=0
    for row in rows:
        row['applications'].append({'kind':'accuracy_roll','move_id':move['id'],'target_id':target.entity_id,'natural':natural})
        total+=row['effect']['amount'];T.expire(engine,actor,row,ending='consumed',event={'kind':'accuracy_roll'})
    if cache is not None:cache[index]=total
    return total

def capture_plan(engine,actor,source_variant=None):
    ensure_clear(engine)
    rows=eligible(engine,actor,'capture')
    for row in rows:
        import capture_resolution as RESOLUTION
        procedure,_=RESOLUTION.bind_native(engine.r,source_variant)
        if row['effect']['capture_plan']['procedure']!={'source':procedure.source,'sides':procedure.sides,'comparison':procedure.comparison}:raise ValueError('next capture needs the granted matching procedure')
        if row['effect']['capture_plan']['basis']['kind']=='selected_errata' and engine.r.mech('pokemon/capture-rate').get('ball_modifier_conversion')!=CONVERSION:
            raise ValueError('Momentum capture conversion no longer selected')
    return {row['id']:conversion_plan(engine,actor,
        {k:v for k,v in row['effect']['capture_plan']['basis'].items() if k!='kind'} if row['effect']['capture_plan']['basis']['kind']=='gm_ruling' else None,
        source_variant) for row in rows}

def capture(engine,actor,target,attempt,plan):
    rows=eligible(engine,actor,'capture')
    if [row['id'] for row in rows]!=list(plan):raise ValueError('next capture effect changed after admission')
    total=0
    for row in rows:
        current=plan[row['id']]
        row['applications'].append({'kind':'capture_roll','attempt_id':attempt['id'],'target_id':target.entity_id,'capture_plan':deepcopy(current)})
        total+=current['modifier'];T.expire(engine,actor,row,ending='consumed',event={'kind':'capture_roll','attempt_id':attempt['id']})
    attempt['momentum_effects']=deepcopy(plan)
    return total

def validate_world(engine,index):
    import missed_ball_body as BALL,temporary_ap as AP
    __import__('capture_specialist').validate_world(engine,index)
    for actor in index.values():
        for attempt in actor.spec.get('capture_attempts',{}).values():
            if 'momentum' not in attempt:continue
            _,event=_attempt(actor,attempt['id']);obj=BALL.attempt_ball(engine,actor,attempt)
            if obj is None or obj.get('consumed',{}).get('by_actor_id')!=actor.entity_id or event['target_id'] not in index:
                raise ValueError('Momentum trigger needs its actual consumed ball and captured target')
            if event['at']>engine.elapsed_seconds or event['round']>engine.round_no:raise ValueError('capture trigger is from the future')
            if event['state'] in ('pending','declined') and (event['choice'] is not None or event['effect_id'] is not None):raise ValueError('unissued trigger has an invented benefit')
            if event['state'] not in ('pending','declined','issued'):raise ValueError('Momentum trigger state changed')
            if event['state']=='issued':
                effects=[r for holder in index.values() for r in live(holder)+history(holder)+AP.all_records(holder) if r['id']==event['effect_id']]
                if len(effects)!=1 or effects[0]['origin']['attempt_id']!=attempt['id'] or event['choice']!=(effects[0]['effect'].get('choice') or effects[0]['effect']['kind']):raise ValueError('Momentum choice must own one actual benefit')
        for row in live(actor)+history(actor):
            validate_record(actor,row,terminal=row in history(actor));owner=index.get(row['origin']['actor_id'])
            if owner is None:raise ValueError('Momentum actual issuer missing')
            _,event=_attempt(owner,row['origin']['attempt_id'])
            if event['effect_id']!=row['id'] or event['choice']!=row['effect']['choice']:raise ValueError('Momentum effect differs from actual choice')
            for application in row['applications']:
                if application['target_id'] not in index:raise ValueError('Momentum actual roll target missing')
                if application['kind']=='capture_roll':
                    attempt=actor.spec.get('capture_attempts',{}).get(application['attempt_id'],{})
                    if attempt.get('momentum_effects',{}).get(row['id'])!=application['capture_plan'] or not attempt.get('hit') or 'resolution' not in attempt:raise ValueError('Momentum capture consumption requires its actual completed capture roll')
            if row in live(actor) and not engine.encounter_active:raise ValueError('Momentum benefit survived encounter end')


def end_encounter(engine):
    import temporary_ap as AP
    for actor in engine.time_actors():
        for row in list(live(actor))+[r for r in AP.live(actor) if r[E.KEY]['lifetime']['boundary']=='initiative_count']:
            T.expire(engine,actor,row,event={'kind':'encounter_end','round':engine.round_no})
