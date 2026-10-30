"""Glitch Bender source editions on existing native rule owners, not networking."""
from copy import deepcopy
from pathlib import Path
from hashlib import sha256
import state_grants as G
import world_entities as W

CLASS='feat/버그-타락자'; ERROR='feat/나는-에러다'; NULL='feat/널-에러'
REALITY='feat/타락한-현실'; CODE='feat/코드-투입'; SHUFFLE='feat/버그-셔플'; BURST='feat/버그-파열'
FEATURES={CLASS:(1871,1875),ERROR:(1877,1894),NULL:(1896,1900),REALITY:(1902,1907),CODE:(1909,1920),SHUFFLE:(1922,1926),BURST:(1928,1941)}
PARENTS={CLASS:(),ERROR:(CLASS,),NULL:(CLASS,),REALITY:(CLASS,),CODE:(REALITY,),SHUFFLE:(CLASS,),BURST:(SHUFFLE,)}
CSV_ROWS={CLASS:76,ERROR:77,REALITY:78,CODE:79,NULL:80,SHUFFLE:81,BURST:82}
HB_ROWS={CLASS:759,NULL:760,SHUFFLE:761,BURST:762,CODE:763}
BOOK_SHA='99c41c5de006f3cc0e5d57f1f3e498aa019c557d36f21e938f777b25be253f0e'
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
DEFINITIONS={u:{'span':list(s),'catalog_span':list(s),'clause_id':'input/supp-polygon.md:'+str(s[0])+'-'+str(s[1]),'class_template':CLASS,'minimum_level':0,'skill':None,'source':{'file':'input/supp-polygon.md','sha256':BOOK_SHA}} for u,s in FEATURES.items()}
SKILLS=('집중','오컬트학','통찰')
DISABLE='move/사슬묶기'; SNATCH='move/가로채기'; METRONOME='move/손가락흔들기'; TOPSY='move/뒤집어엎기'
CLASS_MOVES=(DISABLE,SNATCH,METRONOME,TOPSY)
TEACHING={NULL:('폴리곤 쇼크','액세스 거부','방해 웨이브'),SHUFFLE:('순간이동 충격','블루 스크린','고통 교환'),BURST:('버그 파동','버그 스트라이크'),CODE:('데이터 드레인','대규모 할퀴기')}
HB_AUTHORITY='C2CSV/input/db/feats.csv:R759:main'
CONDITIONS=('잠듦','화상','얼음','헤롱헤롱','독','혼란','마비','난동','사슬묶기','억압')
BUGS=('object_not_found','access_denied','blue_screen'); SCENE={'kind':'scene','uses':1}


def source(rules,feature,edition):
    from source_context import verified_source
    if feature not in FEATURES or edition not in ('supplement','local_csv','homebrew'):raise ValueError('exact Glitch Bender source edition required')
    if edition=='homebrew' and feature not in HB_ROWS:raise ValueError('Feature has no separate homebrew row')
    if rules._selected_rule(feature)!=feature or feature in rules.ruleset.unit_versions:raise ValueError('selected variant needs its exact adapter')
    verified_source(rules,{'file':'input/supp-polygon.md','sha256':BOOK_SHA},label='Glitch Bender supplement')
    result={'edition':edition,'file':'input/supp-polygon.md','sha256':BOOK_SHA,'span':list(FEATURES[feature])}
    if edition!='supplement':
        verified_source(rules,{'file':'input/db/feats.csv','sha256':CSV_SHA},label='Glitch Bender CSV')
        row=(HB_ROWS if edition=='homebrew' else CSV_ROWS)[feature];uid='C2CSV/input/db/feats.csv:R'+str(row)+':main'
        rules.ruleset.require({'id':uid,'source':{'file':'db/feats.csv','record_span':[row,row]}})
        result.update(file='input/db/feats.csv',sha256=CSV_SHA,row=row,clause_id=uid)
    return result


def static_source(rules,feature):
    source(rules,feature,'supplement');unit=rules.selection.units[feature]['source']
    if unit.get('file')!='supp-polygon.md' or unit.get('lines')!=list(FEATURES[feature]):raise ValueError('exact full Glitch Bender catalog body required')
    return {**DEFINITIONS[feature]['source'],'clause_id':DEFINITIONS[feature]['clause_id'],'span':list(FEATURES[feature])}


def records(actor,feature=None,active=False):
    return [r for _,r in __import__('trainer_feature_acquisition').static_family_acquisitions(actor,FEATURES,feature,active=active)]


def acquired(actor,feature=CLASS):
    rows=records(actor,feature,True)
    if len(rows)>1:raise ValueError('one exact Glitch Bender acquisition required')
    return rows[0] if rows else None


def selection(feature,rank,value):
    expected={'edition'}|({'gm_permission'} if feature==CLASS else set())|({'confusion_cure'} if feature==BURST else set())
    if rank is not None or type(value)is not dict or set(value)!=expected:raise ValueError('explicit Glitch Bender edition and printed choices required')
    if feature==CLASS:G._text(value['gm_permission'],'actual campaign GM class availability approval')
    if feature==BURST and value['confusion_cure'] not in ('korean_glitch_only','english_target'):raise ValueError('explicit S-001 Topsy-Turvy cure scope required')


def connection_choice(rules,value):
    """HB759-only non-basic type exception; never an automatic Edge grant."""
    if value!={'type':'에러','authority':HB_AUTHORITY}:return None
    source(rules,CLASS,'homebrew')
    if rules._selected_rule('supp-polygon/버그-타입')!='supp-polygon/버그-타입':raise ValueError('selected actual Glitch type source required')
    return '에러'


def acquisition_snapshot(e,actor,feature,rank,choice):
    import skill_modifiers as S,elemental_connection as E
    selection(feature,rank,choice);src=source(e.r,feature,choice['edition'])
    parent={CODE:REALITY,BURST:SHUFFLE}.get(feature,CLASS)
    glitch=[v for v in actor.spec.get('edges',[]) if S.key(v) in S.GLITCH_OWNERSHIP_SOURCES]
    elemental=('에러' in E.choices(e,actor) or '에러' in E.choices(e,actor,E.HOMEBREW)) if feature==CLASS and choice['edition']=='homebrew' else False
    return {'selection':deepcopy(choice),'source':src,'skills':{s:S.rank(e.r,actor,s)[2] for s in SKILLS},'parent_requests':[] if feature==CLASS else [r['request_id'] for r in records(actor,parent,True)],'glitched_existence':len(glitch)==1,'elemental_error':elemental}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q,common_checks as C,skill_modifiers as S
    if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'selection','source','skills','parent_requests','glitched_existence','elemental_error'}:raise ValueError('exact historical Glitch Bender prerequisites required')
    s=snapshot;selection(feature,None,s['selection'])
    if s['source']!=source(actor.r,feature,s['selection']['edition']):raise ValueError('Glitch Bender source changed')
    if type(s['skills'])is not dict or set(s['skills'])!=set(SKILLS):raise ValueError('all three actual skill observations required')
    for v in s['skills'].values():
        S.validate_rank_value(actor.r,v,label='actual class skill rank')
    for k in ('glitched_existence','elemental_error'):
        if type(s[k])is not bool:raise ValueError('actual source-specific prerequisite required')
    parent={CODE:REALITY,BURST:SHUFFLE}.get(feature,CLASS)
    if type(s['parent_requests'])is not list or len(set(s['parent_requests']))!=len(s['parent_requests']):raise ValueError('distinct prerequisite receipt identities required')
    if feature==CLASS:
        if s['parent_requests']:raise ValueError('class cannot invent a parent')
        prerequisite=s['elemental_error'] if s['selection']['edition']=='homebrew' else s['glitched_existence']
    else:prerequisite=bool(s['parent_requests']) and set(s['parent_requests'])<={r['request_id'] for r in records(actor,parent)}
    minimum={CLASS:3,ERROR:0,NULL:0,REALITY:4,CODE:0,SHUFFLE:5,BURST:6}[feature]
    if feature==SHUFFLE and s['selection']['edition']!='supplement':minimum=4
    return Q.require(feature,'native','acquire',[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),Q.check('parent','prerequisite',prerequisite,'printed actual class/Feature/Edge prerequisite required'),Q.check('skill','prerequisite',max(s['skills'].values())>=minimum,'printed class-linked skill rank required')])


def after_acquire(e,actor,feature,sid):
    G.stat(actor,'spd',1,sid,operation_id='acquisition_stat_tag')
    if feature==CLASS:
        G.grant(actor,'abilities','싱크로',sid,'feature',owner_id=actor.entity_id,lifetime='while_owned',rule_id=feature);e.register_abilities(actor)
    if feature in (NULL,SHUFFLE):
        for mid in CLASS_MOVES[:2] if feature==NULL else CLASS_MOVES[2:]:
            actual=e.r.move_id(mid)
            if actual is None:raise ValueError('actual printed Glitch Bender Move required')
            G.grant(actor,'moves',actual,sid,'feature',owner_id=actor.entity_id,lifetime='while_owned',rule_id=feature)


def validate_acquisition(actor,record,sid,active):
    if active and actor.spec.get(G.KEY,{}).get('stat_sources',{}).get('spd',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:raise ValueError('actual source-owned Special Defense tag required')


def require(e,actor,feature):
    W.require_actors(e,actor);row=acquired(actor,feature)
    if row is None or not __import__('acquired_features').owned_rule_count(actor,feature):raise ValueError('actual acquired Glitch Bender Feature required: '+feature)
    source(e.r,feature,row['snapshot']['selection']['edition']);__import__('trainer_feature_acquisition').validate_actor(actor)
    if actor.fainted or actor.dead or actor.captured or not actor.on_field:raise ValueError('available actual Glitch Bender required')
    return row


def homebrew(actor,feature=CLASS):
    row=acquired(actor,feature)
    return row is not None and row['snapshot']['selection']['edition']=='homebrew'


def type_ace_features(actor):
    """A count/view, never an invented Type Ace acquisition or child grant."""
    return records(actor,active=True) if homebrew(actor) else []


def type_ace_records(actor,feature=None,active=False):
    """Source-bound class-equivalence view, not another Type Ace acquisition."""
    import type_ace as T
    if feature not in (None,T.CLASS):return []
    rows=records(actor,CLASS if feature==T.CLASS else None,active)
    if not any(r['feature_id']==CLASS and r['snapshot']['selection']['edition']=='homebrew' for r in records(actor,CLASS,active)):return []
    return rows


def type_ace_skill(engine,actor,branch):
    if branch!='에러' or not homebrew(actor):return None
    skill=actor.spec.get('type_link_skills',{}).get(branch)
    if skill not in SKILLS:raise ValueError('explicit source-bound Glitch Type Ace linked skill required')
    return __import__('skill_modifiers').effective_rank(engine.r,actor,skill)


def _pay(e,actor,feature,kind,*,ap=0,quota=None,triggered=False,retain_receipt=False):
    import action_points as AP,frequency as F,turn as T
    if AP.available(actor)<ap:raise ValueError('insufficient actual Glitch Bender AP')
    if quota and not F.activation_allowed(actor,feature,quota,engine=e,action_actor=actor):raise ValueError('Glitch Bender frequency exhausted')
    if triggered:
        if kind!='free':raise ValueError('actual triggered Free action required')
        import heavy_injury_adapter as HEAVY,heavy_standard_adapter as STANDARD
        parents=[(token,row) for token,row in e._heavy_native_receipts.items() if row['attacker'] is actor]
        for token,row in parents:HEAVY.validate_native_receipt(e,token,actor,row['target'],{'id':row['move_id']})
        standards=[(token,row) for token,row in e._heavy_standard_receipts.items() if row['actor'] is actor]
        for token,row in standards:STANDARD.validate(e,token)
        history=list(getattr(actor,'_action_history',[]));epoch=e._heavy_activation_sequence;standard_epoch=e._heavy_standard_sequence
        __import__('action_lifecycle').triggered_free_action(e,actor,feature)
        if actor._action_history!=history+['free'] or e._heavy_activation_sequence!=epoch or e._heavy_standard_sequence!=standard_epoch:raise ValueError('triggered Glitch Feature must add exactly its actual Free action')
        for token,row in parents:
            if e._heavy_native_receipts.get(token)is not row or row['history_length']!=len(history):raise ValueError('triggered Glitch Feature parent receipt changed')
            row['history_length']=len(actor._action_history)
        for token,row in standards:
            if e._heavy_standard_receipts.get(token)is not row or row['history_length']!=len(history):raise ValueError('triggered Glitch Feature Standard receipt changed')
            row['history_length']=len(actor._action_history)
    elif not T.spend(e,actor,kind,feature):raise ValueError('Glitch Bender requires its actual '+kind+' action')
    receipt=__import__("action_point_account").ActionPointAccount(actor).charge(ap,retain_receipt=True) if retain_receipt else None
    if ap and not retain_receipt:AP.charge(actor,ap)
    if quota:F.consume_activation(actor,feature,quota,engine=e,action_actor=actor)
    return receipt


def teach(e,teacher,target,feature,choice,*,seconds,reason,replace=None):
    """HB Extended lessons compose shared permanent learning/payment and clock."""
    __import__('common_checks').integer(seconds,'GM-established Extended teaching seconds',1);G._text(reason,'actual lesson duration and reason')
    def apply(se,pupil,owner):
        import pokemon_activities as P,pokemon_teaching as T,turn as TURN,activity_jobs as JOBS
        import move_state as M,learning_grant as L,grant_payments as PAY,ability_transitions as A
        require(se,owner,feature);W.require_actors(se,pupil);P._trainer(owner);P._pokemon(pupil);P._outside(se)
        if not homebrew(owner,feature):raise ValueError('actual selected homebrew teaching Feature required')
        if T._balance(pupil.spec)<2:raise ValueError('lesson requires two actual target Tutor Points')
        if __import__('frequency').state(owner)['day']!=__import__('frequency').state(pupil)['day']:raise ValueError('actual teaching calendars must agree')
        acquisition=deepcopy(acquired(owner,feature));is_ability=feature==CLASS
        if is_ability:
            if choice not in ('last_chance','strategist'):raise ValueError('select printed Last Chance or Type Strategist')
            selected='ability/마지막기회' if choice=='last_chance' else 'ability/타입전략가';group='glitch-ability-lesson:'+pupil.entity_id
            if group in pupil.spec.get(G.KEY,{}).get('payments',{}):raise ValueError('Ability lesson may target each Pokemon only once')
            if selected in A.known(pupil):raise ValueError('target already has selected actual Ability')
            if replace is not None:raise ValueError('Ability lesson has no Move replacement')
        else:
            if feature not in TEACHING:raise ValueError('Feature has no printed Move lesson')
            pool=[se.r.move_id(v) for v in TEACHING[feature]];selected=se.r.move_id(choice)
            if None in pool or selected not in pool or selected in se.r.excluded_moves:raise ValueError('selected actual Move outside exact HB teaching pool')
            if selected in M.known(se.r,pupil.spec):raise ValueError('Pokemon already permanently learned this Move')
        if not TURN.spend(se,owner,'extended',feature):raise ValueError('lesson requires actual Extended action')
        JOBS.run_fixed(se,owner,(pupil,),seconds=seconds,source=feature,context={'glitch_bender_lesson':selected})
        require(se,owner,feature)
        if acquired(owner,feature)!=acquisition or not homebrew(owner,feature):raise ValueError('actual teaching source changed during activity')
        if T._balance(pupil.spec)<2:raise ValueError('target Tutor Points changed during lesson')
        proof={'feature':feature,'acquisition':acquisition,'teacher_id':owner.entity_id,'seconds':seconds,'completed_at':se.elapsed_seconds,'choice':choice}
        proof['integrity']=__import__('trainer_feature_acquisition')._digest('glitch-lesson/v1',proof)
        if is_ability:
            receipt=PAY.acquire(se,pupil,group,[{'source_id':group+':ability','field':'abilities','value':selected}],2,rule_id=feature,reason=reason)
            G.state(pupil)['sources'][group+':ability']['glitch_bender_lesson']=proof;se.register_abilities(pupil)
        else:
            candidate=deepcopy(pupil.spec);old=se.r.move_id(replace) if replace is not None else None
            if replace is not None and old not in M.known(se.r,candidate):raise ValueError('explicit actual permanent replacement Move required')
            if old is not None:
                __import__('move_type_sync').forget_spec(se.r,candidate,old,at=se.elapsed_seconds,reason=reason)
                __import__('ace_trainer').forget_spec(se.r,candidate,old,at=se.elapsed_seconds,reason=reason)
                candidate['moves']=[m for m in candidate['moves'] if se.r.move_id(m)!=old]
            receipt=L.learn_moves(se.r,candidate,candidates=pool,selected=[selected],method='feature',source=feature,reason=reason,provider=owner.entity_id,paid_tp=2,details={'glitch_bender_lesson':proof},replaced=old)
            M.record_natural_opportunities(se.r,candidate,reason='completed Glitch Bender HB teaching');M.validate_spec(se.r,candidate,require_routes=True)
            for field in ('move_learning','move_learning_log',M.HISTORY,'move_type_sync','signature_techniques'):
                if field in candidate:pupil.spec[field]=candidate[field]
            G.set_baseline(pupil,'moves',candidate['moves']);T._debit_points(pupil.spec,2)
        __import__('trainer_retraining').irreversible(se,owner,feature,event_id='glitch-lesson:'+owner.entity_id+':'+pupil.entity_id+':'+selected+':'+str(se.elapsed_seconds),reason=reason)
        return {'feature':feature,'learned':selected,'point_cost':2,'receipt':receipt}
    return G.transition(e,target,apply,participants=(teacher,))


def taught_branches(actor,kind):
    import ability_transitions as A,move_state as M
    identity='ability/마지막기회' if kind=='last_chance' else 'ability/타입전략가'
    if identity not in A.known(actor) or not A.active(actor,identity):return set()
    for row in actor.spec.get(G.KEY,{}).get('sources',{}).values():
        proof=row.get('glitch_bender_lesson')
        if proof and proof.get('feature')==CLASS and proof.get('choice')==kind and M.source_active(actor.spec,row):return {'에러'}
    return set()


def arm_error(e,actor,decision,*,fixed=None):
    """Live optional choice, consumed only at the actual status-gain boundary."""
    require(e,actor,ERROR)
    if not callable(decision):raise ValueError('fresh actual status observation callback required')
    if fixed is not None:
        if type(fixed)is not list or not fixed:raise ValueError('explicit observed d10 sequence required')
        for face in fixed:__import__('common_checks').integer(face,'observed I Am Error d10 face',1,10)
    G.transition(e,actor,lambda se,c:c.spec.update(glitch_error_offer={'fixed':deepcopy(fixed)}))
    authenticate_error(e,actor,decision)


def authenticate_error(e,actor,decision):
    require(e,actor,ERROR)
    if not callable(decision) or 'glitch_error_offer' not in actor.spec:raise ValueError('fresh decision for actual I Am Error offer required')
    validate_actor(actor)
    e._glitch_error_choices={**getattr(e,'_glitch_error_choices',{}),actor.entity_id:decision}


def status_interested(e,actor):
    return 'glitch_error_offer' in actor.spec


class ErrorChoiceRejected(ValueError):
    """A rejected I Am Error choice rolls back its enclosing native producer."""


def replace_status(e,actor,condition,*,source=None,parameters=None,applied_by=None,force=False):
    try:return _replace_status(e,actor,condition,source=source,parameters=parameters,applied_by=applied_by,force=force)
    except Exception as exc:
        if type(exc) in (__import__('passive_events').PassiveEventPending,__import__('heavy_injury_adapter').HeavyPending):raise
        raise ErrorChoiceRejected(str(exc)) from exc


def _replace_status(e,actor,condition,*,source=None,parameters=None,applied_by=None,force=False):
    """Called AFTER native duplicate, immunity, deferral and prevention checks.

    None delegates the unchanged gain. A boolean is the actual replacement's
    native result. No initial condition was installed or reflected yet.
    """
    if getattr(e,'_glitch_replacing_status',False) or not status_interested(e,actor):return None
    if condition in actor.conditions or e.r.condition_class(condition) not in __import__('status_sets').AFFLICTION_CLASSES:return None
    if acquired(actor,ERROR) is None or actor.fainted or actor.dead or actor.captured or not actor.on_field:return None
    require(e,actor,ERROR)
    callback=getattr(e,'_glitch_error_choices',{}).get(actor.entity_id)
    if not callable(callback):raise ValueError('I Am Error requires fresh live choice authentication after load')
    fixed=actor.spec['glitch_error_offer']['fixed']
    e._native_roll_deciding=True
    try:answer=callback({'condition':condition,'source':source,'actor_id':actor.entity_id})
    finally:e.__dict__.pop('_native_roll_deciding',None)
    if type(answer)is not bool:raise ValueError('explicit observed I Am Error use or decline required')
    require(e,actor,ERROR)
    if not answer:
        actor.spec.pop('glitch_error_offer');return None
    if all(v in actor.conditions for v in CONDITIONS):raise ValueError('no unheld I Am Error result remains')
    import roll_pools as POOLS
    faces=iter(fixed) if fixed is not None else None
    observations=[]
    while True:
        try:observed=None if faces is None else next(faces)
        except StopIteration as exc:raise ValueError('I Am Error observed d10 sequence exhausted before an unheld condition') from exc
        face=POOLS.die(e.rng,10,fixed=observed)
        observations.append(face);chosen=CONDITIONS[face-1]
        if chosen not in actor.conditions:break
    issuer=applied_by;params=None
    if chosen=='헤롱헤롱':
        enemies=[c for c in W.actor_index(e).values() if c is not actor and actor.side and c.side and c.side!=actor.side and c.on_field and not c.fainted and not c.dead and not c.captured]
        if not enemies:raise ValueError('I Am Error Infatuation requires an actual enemy to choose at random')
        issuer=e.rng.choice(enemies)
    elif chosen=='사슬묶기':
        known=__import__('move_state').known(e.r,{'moves':__import__('move_state').owned_list(actor.spec,'moves',actor.moves)})
        if not known:raise ValueError('I Am Error Disable requires an actually known Move')
        params={'move_id':e.rng.choice(known)}
    _pay(e,actor,ERROR,'free',ap=2,triggered=True)
    actor.spec.pop('glitch_error_offer')
    e._glitch_replacing_status=True
    try:result=e._apply_status(actor,chosen,source=ERROR,parameters=params,applied_by=issuer,force=force)
    finally:del e._glitch_replacing_status
    e.log('I Am Error: '+condition+' -> '+chosen+' '+str(observations),ERROR)
    return result


def arm_reality(e,actor,target,*,purpose,decision,reroll_fixed=None):
    require(e,actor,REALITY);W.require_actors(e,target);G._text(purpose,'actual native foe roll purpose')
    if target is actor or not actor.side or not target.side or actor.side==target.side:raise ValueError('Corrupt Reality observes only an actual foe roll')
    if not callable(decision):raise ValueError('fresh observed foe roll decision callback required')
    import frequency as F
    if not F.activation_allowed(actor,REALITY,SCENE,engine=e,action_actor=actor):raise ValueError('Corrupt Reality Scene use exhausted')
    if actor.spec.get('native_roll_offer'):raise ValueError('one actual native roll offer per provider required')
    result=G.transition(e,actor,lambda se,c:c.spec.update(native_roll_offer={'actor_id':target.entity_id,'purpose':purpose,'source':REALITY,'fixed':deepcopy(reroll_fixed)}))
    e._native_roll_decisions={**getattr(e,'_native_roll_decisions',{}),actor.entity_id:decision}
    return result


def reroll(e,owner,actor,purpose,first,roll_again):
    """Dispatch from the existing native-roll owner for this exact source only."""
    offer=owner.spec.get('native_roll_offer')
    if not offer or offer.get('source')!=REALITY:return None
    if acquired(owner,REALITY) is None or owner.fainted or owner.dead or owner.captured or not owner.on_field:return first
    if not owner.side or not actor.side or owner.side==actor.side:return first
    require(e,owner,REALITY);W.require_actors(e,actor)
    if offer.get('actor_id')!=actor.entity_id or offer.get('purpose')!=purpose:raise ValueError('actual foe roll offer mismatch')
    if not owner.side or not actor.side or owner.side==actor.side:raise ValueError('Corrupt Reality lost its actual foe')
    callback=getattr(e,'_native_roll_decisions',{}).get(owner.entity_id)
    if not callable(callback):raise ValueError('restored Corrupt Reality offer requires fresh live choice authentication')
    e._native_roll_deciding=True
    try:answer=callback(deepcopy(first))
    finally:e.__dict__.pop('_native_roll_deciding',None)
    if type(answer)is not bool:raise ValueError('observed Corrupt Reality choice must be explicit')
    require(e,owner,REALITY)
    if not owner.side or not actor.side or owner.side==actor.side:raise ValueError('Corrupt Reality lost its actual foe during choice')
    owner.spec.pop('native_roll_offer')
    if not answer:return first
    _pay(e,owner,REALITY,'free',quota=SCENE,triggered=True)
    return roll_again(offer['fixed'])


def authenticate_reality(e,actor,decision):
    require(e,actor,REALITY)
    if not callable(decision) or actor.spec.get('native_roll_offer',{}).get('source')!=REALITY:raise ValueError('fresh decision for the existing actual Corrupt Reality offer required')
    validate_world(e)
    e._native_roll_decisions={**getattr(e,'_native_roll_decisions',{}),actor.entity_id:decision}


def code_injection(e,actor,target,bug,*,fixed_accuracy=None):
    """The existing typed attack dispatcher owns actual AC2 status accuracy."""
    if bug not in BUGS:raise ValueError('choose exactly one printed Code Injection bug')
    def apply(se,a,t):
        require(se,a,CODE);W.require_actors(se,t)
        if t.kind not in ('trainer','pokemon'):raise ValueError('Code Injection needs an actual Trainer or Pokemon')
        import body_state as BODY,frequency as F,common_checks as C
        C.integer(fixed_accuracy,'observed Code Injection accuracy',1,20) if fixed_accuracy is not None else None
        move={'id':CODE,'name':'코드 투입','class':'변화','type':'노말','ac':2,'damage_base':None,'range':'5, 대상 1','_class_move_range':{'origin':5,'targets':1,'parsed':True}}
        __import__('body_modes').require_targetable(t,attacker=a)
        if se.grid is not None:
            if not BODY.in_range(se,a,t,5,move=move):raise ValueError('Code Injection actual target outside range/line of sight')
        else:
            __import__('mapless_space').require_target(se,a,t,move)
        if not F.activation_allowed(a,CODE+':'+bug,SCENE,engine=se,action_actor=a):raise ValueError('that Code Injection bug already used this Scene')
        if not F.activation_allowed(t,CODE+':recipient',SCENE,engine=se):raise ValueError('that recipient already affected this Scene')
        payment=_pay(se,a,CODE,'standard',ap=1,retain_receipt=True)
        F.consume_activation(a,CODE+':'+bug,SCENE,engine=se,action_actor=a)
        token=object();se._glitch_code_activation=(token,a,t,bug,deepcopy(acquired(a,CODE)),fixed_accuracy,payment)
        try:
            import effects as FX
            effect=code_declaration(bug)
            result=FX.run_effects(se,a,t,[effect],{'glitch_code_token':token,'source_id':CODE,'hit':True},CODE)
            return result
        finally:del se._glitch_code_activation
    return G.transition(e,actor,apply,participants=(target,),include_rulings=True)



def code_effect(e,actor,target,effect,ctx):
    import effect_contracts as CONTRACTS,combat_timing as CLOCK,frequency as F
    frame=getattr(e,'_glitch_code_activation',None)
    if (not frame or frame[1] is not actor or frame[2] is not target or frame[3]!=effect.get('bug') or ctx.get('hit') is not True):
        raise ValueError('Code Injection requires its actual paid native hit')
    parent=code_attack_record(e,ctx.get('code_attack_receipt'))
    if parent['actor'] is not actor or parent['target'] is not target or parent['code_injection'].get('accuracy',[False])[0] is not True or parent['code_injection']['phase']!='effect':
        raise ValueError('Code Injection effect lost its actual native attack hit')
    receipt=ctx.get('effect_receipt');occurrence=ctx.get('effect_occurrence')
    CONTRACTS.validate_receipt(e,receipt,CODE,occurrence,actor,target,effect)
    if not F.activation_allowed(target,CODE+':recipient',SCENE,engine=e):raise ValueError('actual recipient already affected this Scene')
    proof={'bug':frame[3],'issuer_id':actor.entity_id,'target_id':target.entity_id,'acquisition':deepcopy(frame[4]),'occurrence':occurrence,'receipt':receipt,'attack_receipt':parent['receipt'],'effect':deepcopy(effect),'round':e.round_no,'count':CLOCK.current(e)}
    proof['integrity']=__import__('trainer_feature_acquisition')._digest('glitch-code/v1',{k:v for k,v in proof.items() if k not in ('receipt','attack_receipt')})
    row={'source':CODE,'glitch_code':proof,'effect_contract':True,'encounter_end':True,'count_deadline':(e.round_no+1,CLOCK.current(e)),
         'statuses':{'object_not_found':[],'access_denied':['둔화'],'blue_screen':['실명','취약']}[frame[3]]}
    application={'round':e.round_no,'count':CLOCK.current(e),'occurrence':occurrence}
    parent['code_injection']['application']={**application,'receipt':receipt,
        'integrity':__import__('trainer_feature_acquisition')._digest('glitch-code-application/v1',application)}
    F.consume_activation(target,CODE+':recipient',SCENE,engine=e)
    CLOCK.install(e,target,row)
    if frame[3]=='object_not_found':__import__('items').synchronize_equipment_suppression(e,[target])
    return None


def code_rows(actor,bug=None):
    return [r for r in __import__('combat_timing').records(actor) if r.get('glitch_code') and (bug is None or r['glitch_code']['bug']==bug)]


def benefits_blocked(actor):return bool(code_rows(actor,'object_not_found'))


def frequency_allowed(actor,kind):return kind=='at_will' or not (code_rows(actor,'access_denied') or __import__('glitch_moves').access_rows(actor))


def equipment_reasons(actor,registration_key):
    return [{'kind':'glitch_code','source':CODE,'effect_occurrence':r['glitch_code']['occurrence'],'holder_id':actor.entity_id,'registration_key':registration_key} for r in code_rows(actor,'object_not_found')]


def _historical_acquisition(rules,row,feature,owner_id):
    """An applied permanent effect keeps its original, sealed acquisition proof."""
    import trainer_feature_acquisition as T
    fields={'actor_id','feature_id','source','request_id','prerequisite_source','snapshot','qualification','integrity'}
    if type(row)is not dict or set(row)!=fields or row['actor_id']!=owner_id or row['feature_id']!=feature:raise ValueError('exact original Glitch Bender acquisition required')
    if row['integrity']!=T._digest('trainer-feature/static-acquisition/v1',{k:v for k,v in row.items() if k!='integrity'}):raise ValueError('original Glitch Bender acquisition changed')
    if row['source']!=static_source(rules,feature) or row['prerequisite_source'] is not None:raise ValueError('Glitch Bender acquisition source changed')
    choice=row['snapshot'].get('selection');selection(feature,None,choice)
    if row['snapshot'].get('source')!=source(rules,feature,choice['edition']):raise ValueError('Glitch Bender acquired edition changed')
    return choice


def _lesson(rules,proof,feature):
    import common_checks as C,trainer_feature_acquisition as T
    if type(proof)is not dict or set(proof)!={'feature','acquisition','teacher_id','seconds','completed_at','choice','integrity'} or proof['feature']!=feature:raise ValueError('complete actual Glitch Bender lesson evidence required')
    if proof['integrity']!=T._digest('glitch-lesson/v1',{k:v for k,v in proof.items() if k!='integrity'}):raise ValueError('Glitch Bender teaching receipt changed')
    G._text(proof['teacher_id'],'actual historical Glitch Bender teacher')
    C.integer(proof['seconds'],'completed Extended teaching seconds',1);C.integer(proof['completed_at'],'completed teaching clock',proof['seconds'])
    if _historical_acquisition(rules,proof['acquisition'],feature,proof['teacher_id'])['edition']!='homebrew':raise ValueError('actual homebrew lesson acquisition required')


def validate_actor(actor):
    """Validate the shared payment/learning records, without a second lesson ledger."""
    import move_state as M
    offer=actor.spec.get('glitch_error_offer')
    if 'glitch_error_offer' in actor.spec:
        if type(offer)is not dict or set(offer)!={'fixed'}:raise ValueError('exact I Am Error offer required')
        fixed=offer['fixed']
        if fixed is not None:
            if type(fixed)is not list or not fixed:raise ValueError('explicit I Am Error observed d10 sequence required')
            for face in fixed:__import__('common_checks').integer(face,'observed I Am Error d10 face',1,10)
        if not records(actor,ERROR):raise ValueError('I Am Error offer lost its historical acquired source')
    payments=actor.spec.get(G.KEY,{}).get('payments',{})
    group='glitch-ability-lesson:'+actor.entity_id
    sources=actor.spec.get(G.KEY,{}).get('sources',{})
    sources={**sources,**{x['source_id']:x['record'] for x in actor.spec.get(G.KEY,{}).get('ended_sources',[])}}
    for sid,row in sources.items():
        proof=row.get('glitch_bender_lesson')
        if proof is None:continue
        _lesson(actor.r,proof,CLASS)
        choice=proof['choice'];ability={'last_chance':'ability/마지막기회','strategist':'ability/타입전략가'}.get(choice)
        payment=payments.get(group)
        if (actor.kind!='pokemon' or ability is None or sid!=group+':ability' or not payment or payment['paid']!=2 or payment['children']!=[sid]
                or payment['acquisition']['rule_id']!=CLASS or row.get('payment_id')!=group or row.get('lifetime') is not None
                or row.get('grants')!={'abilities':[actor.r.selection.units[ability]['title']]}):raise ValueError('Glitch Bender lesson disagrees with actual permanent Ability payment')
    for row in actor.spec.get('move_learning_log',[]):
        if not isinstance(row,dict) or 'glitch_bender_lesson' not in row:continue
        feature=row.get('source');proof=row['glitch_bender_lesson']
        if feature not in TEACHING:raise ValueError('actual Feature has no homebrew Move lesson')
        _lesson(actor.r,proof,feature);pool=[actor.r.move_id(v) for v in TEACHING[feature]]
        if (actor.kind!='pokemon' or row.get('method')!='feature' or row.get('paid_tp')!=2 or row.get('teacher_id')!=proof['teacher_id']
                or row.get('candidates')!=pool or actor.r.move_id(proof['choice'])!=row.get('move_id') or row.get('lifetime')!='permanent'):
            raise ValueError('Glitch Bender lesson disagrees with actual permanent Move learning route')
    # Shared owners still validate slot capacity, payment allocation and log projection.
    if any('glitch_bender_lesson' in x for x in actor.spec.get('move_learning_log',[]) if isinstance(x,dict)):M.validate_spec(actor.r,actor.spec,require_routes=True)
    return True


def preflight_code(e,actor,target,effect,source):
    frame=getattr(e,'_glitch_code_activation',None)
    if source!=CODE or not frame or frame[1] is not actor or frame[2] is not target:
        raise ValueError('exact paid source-bound Code Injection effect required')
    expected=code_declaration(frame[3]) if effect.get('type')=='attack' else {'type':'glitch_code','bug':frame[3]}
    if effect!=expected:raise ValueError('exact printed Code Injection declaration required')
    if getattr(e,'_glitch_code_resuming',None) is None:require(e,actor,CODE)
    return True


def code_ended(e,target,record):
    """Called after the shared timed owner removes the full-round cause."""
    if record.get('glitch_code',{}).get('bug')=='object_not_found':__import__('items').synchronize_equipment_suppression(e,[target])


def validate_world(e,index=None):
    __import__('glitch_moves').validate_world(e,index or W.actor_index(e))
    import common_checks as C,combat_timing as CLOCK,effect_contracts as CONTRACTS,trainer_feature_acquisition as T
    index=W.actor_index(e) if index is None else index
    for token,attack in getattr(e,'_effect_dispatch_receipts',{}).items():
        if 'code_injection' in attack:code_attack_record(e,token)
    for actor in index.values():
        validate_code_consumption(e,actor,index)
        validate_actor(actor)
        offer=actor.spec.get('native_roll_offer')
        if offer and offer.get('source')==REALITY:
            if set(offer)!={'actor_id','purpose','source','fixed'} or offer['actor_id'] not in index:raise ValueError('complete actual Corrupt Reality foe roll offer required')
            if not records(actor,REALITY):raise ValueError('Corrupt Reality offer lost its historical acquired source')
            target=index[offer['actor_id']]
            G._text(offer['purpose'],'actual Corrupt Reality native roll purpose')
            if target is actor:raise ValueError('Corrupt Reality offer cannot observe its own provider')
        for row in CLOCK.records(actor):
            burst=row.get('glitch_burst')
            if burst is not None:
                fields={'actor_id','target_id','event_id','acquisition','deadline','glitch_target','integrity'}
                if type(burst)is not dict or set(burst)!=fields or burst['target_id']!=actor.entity_id or burst['actor_id'] not in index:raise ValueError('exact original Topsy-Turvy Burst target required')
                if burst['integrity']!=T._digest('glitch-burst/v1',{k:v for k,v in burst.items() if k!='integrity'}):raise ValueError('Topsy-Turvy Burst source evidence changed')
                choice=_historical_acquisition(e.r,burst['acquisition'],BURST,burst['actor_id'])
                receipt=__import__('move_completion').require_hit_return(e,burst['event_id'],actor)
                if receipt['attacker_id']!=burst['actor_id'] or receipt['move']['id']!=TOPSY:raise ValueError('Topsy-Turvy Burst lost its actual native hit')
                if type(burst['glitch_target'])is not bool or choice['confusion_cure']=='korean_glitch_only' and not burst['glitch_target']:raise ValueError('Korean automatic Confusion cure needs its actual application-time Glitch Pokemon')
                if row.get('source')!=BURST or row.get('turn_owner') is not actor or row.get('turn_deadline')!=burst['deadline'] or row.get('statuses')!=['혼란']:raise ValueError('Topsy-Turvy Burst next actual target turn changed')
            proof=row.get('glitch_code')
            if proof is None:continue
            fields={'bug','issuer_id','target_id','acquisition','occurrence','receipt','attack_receipt','effect','round','count','integrity'}
            if type(proof)is not dict or set(proof)!=fields or proof['bug'] not in BUGS or proof['target_id']!=actor.entity_id or proof['issuer_id'] not in index:raise ValueError('exact original Code Injection recipient evidence required')
            if proof['integrity']!=T._digest('glitch-code/v1',{k:v for k,v in proof.items() if k not in ('integrity','receipt','attack_receipt')}):raise ValueError('Code Injection hit receipt changed')
            _historical_acquisition(e.r,proof['acquisition'],CODE,proof['issuer_id'])
            C.integer(proof['round'],'Code Injection application round',1);C.integer(proof['count'],'Code Injection application initiative')
            if (row.get('source')!=CODE or row.get('effect_contract') is not True or row.get('encounter_end') is not True or tuple(row.get('count_deadline',()))!=(proof['round']+1,proof['count'])
                    or row.get('statuses')!={'object_not_found':[],'access_denied':['둔화'],'blue_screen':['실명','취약']}[proof['bug']]):raise ValueError('Code Injection full-round actual effect lifetime changed')
            attack=code_attack_record(e,proof['attack_receipt'])
            if attack['actor'] is not index[proof['issuer_id']] or attack['target'] is not actor or attack['code_injection'].get('accuracy',[False])[0] is not True:
                raise ValueError('Code Injection effect lost its original actual hit')
            CONTRACTS.validate_receipt(e,proof['receipt'],CODE,proof['occurrence'],index[proof['issuer_id']],actor,proof['effect'])
            actual=e._effect_dispatch_receipts[proof['receipt']]
            if actual['status']!='completed' and not (actual['status']=='dispatching' and getattr(e,'_glitch_code_activation',None)):raise ValueError('Code Injection requires its actual completed effect dispatch')
    for token,receipt in getattr(e,'_effect_dispatch_receipts',{}).items():
        if 'metronome_parent' not in receipt:continue
        parent=getattr(e,'_move_completions',{}).get(receipt['metronome_parent'],{})
        if parent.get('metronome_child',{}).get('receipt') is not token:raise ValueError('Metronome dispatcher receipt lost its actual parent')
    for parent in getattr(e,'_move_completions',{}).values():
        if parent.get('metronome_child'):_metronome_state(e,parent,historical=parent['metronome_child']['phase']=='complete')
    return True


MOVE_ROWS={DISABLE:467,SNATCH:71,METRONOME:526,TOPSY:77}
METRONOME_EXCLUDED=('당신먼저','조수','기프트패스','흉내쟁이','카운터','탐내기','트릭가드','길동무','판별','버티기','속여때리기','힘껏펀치','날따름','도우미','킹실드','손가락흔들기','선취','흉내내기','미러코트','따라하기','방어','순서미루기','패스트가드','분노가루','스케치','잠꼬대','가로채기','코골기','니들가드','바꿔치기','도둑질','변신','트릭','와이드가드')


def selected_move(rules,mid):
    """Generic printed Move source, independent of Glitch class ownership."""
    if mid not in MOVE_ROWS:raise ValueError('exact referenced Glitch Bender Move required')
    move=rules.move(mid)
    if rules._selected_rule(mid)!=mid or move.get('_source',{}).get('record_span')!=[MOVE_ROWS[mid]]*2:raise ValueError('selected printed Move needs its own source adapter')
    return move


def _disable_trigger(e,actor,event_id):
    import move_completion as M,initiative_interrupts as I,action_lifecycle as A
    W.require_actors(e,actor);selected_move(e.r,DISABLE)
    __import__('priority_actions')._owned_move(e,actor,DISABLE)
    receipt=M.require_hit_return(e,event_id,actor);event=e._passive_events[event_id];row=e._move_completions[receipt['completion_id']]
    own=(e._active_turn_actor is actor and row.get('full_turn')==A.current_full_turn(e))
    if not own:I._trigger(e,{'kind':'move','event_id':event.get('defense_parent',event_id)})
    if row['round']!=e.round_no or event['phase']!='producer_return_boundary' or actor.fainted or actor.dead:raise ValueError('Disable requires its actual current surviving hit recipient')
    return row


def event_interested(e,actor,target,move):
    return move['id']==METRONOME or metronome_child_scope(e,actor) or (target is not None and DISABLE in target.moves) or (move['id'] in CLASS_MOVES and acquired(actor,BURST) is not None)


def use_disable(e,actor,event_id):
    """The printed Move's Free/no-Command producer; no Glitch-only combat path."""
    row=_disable_trigger(e,actor,event_id);target=row['actor']
    def apply(se,a,t):
        import action_lifecycle as A
        _disable_trigger(se,a,event_id);before=a.move_uses.get(DISABLE,0)
        if getattr(se,'_glitch_disable_trigger',None):raise ValueError('one actual Disable trigger at a time')
        se._glitch_disable_trigger=(a,event_id)
        try:
            with A.move_grant(se,a,t,DISABLE,source=DISABLE,kind='free') as grant:
                result=se.use_move(a,t,DISABLE,free_action=True,_action_grant=grant)
            if a.move_uses.get(DISABLE,0)!=before+1:raise ValueError('native Disable did not consume its printed Scene use')
            return result
        finally:vars(se).pop('_glitch_disable_trigger',None)
    # The existing native transaction retains legitimate suspended paid prefixes.
    if getattr(e,'_reactive_move_transaction',False):return apply(e,actor,target)
    return __import__('reactive_ability_events').atomic_move(e,actor,target,apply)


def move_authority(e,actor,target,mid,source):
    """AL admission and consumption both revalidate this exact native source."""
    if source==DISABLE:
        frame=getattr(e,'_glitch_disable_trigger',None)
        if not frame:return False
        if mid!=DISABLE or frame[0] is not actor or _disable_trigger(e,actor,frame[1])['actor'] is not target:raise ValueError('Disable grant changed its actual triggering attacker')
        return True
    if source==METRONOME:
        frame=getattr(e,'_glitch_metronome_child',None)
        if not frame:return False
        parent=e._move_completions[frame['parent_id']];_metronome_state(e,parent)
        if frame['phase']!='running' or frame['effect_user_id']!=actor.entity_id or frame['choice']['target_id']!=target.entity_id or frame['choice']['move_id']!=mid:raise ValueError('Metronome child grant changed its actual selection')
        return True
    return False


def grant_count(e,actor,target,mid,source):
    if not move_authority(e,actor,target,mid,source):raise ValueError('actual referenced Move authority required')
    return source==DISABLE


def move_interested(e,actor,target,mid):
    return mid in (DISABLE,METRONOME,SNATCH) or any(status_interested(e,c) or c.spec.get('native_roll_offer',{}).get('source')==REALITY for c in W.actor_index(e).values())


def native_move(fn):
    from functools import wraps
    @wraps(fn)
    def run(e,a,t,mid,*args,**kwargs):
        if mid not in (DISABLE,SNATCH,METRONOME) and not __import__('combat_move_reactions').snatch_interested(e,a,t) and not any(status_interested(e,c) for c in W.actor_index(e).values()):return fn(e,a,t,mid,*args,**kwargs)
        def apply(se,c,target):
            payload=G._stage_transition_payload(e,se,{'args':args,'kwargs':kwargs})
            before=set(getattr(se,'_effect_dispatch_receipts',{}))
            result=fn(se,c,target,mid,*payload['args'],**payload['kwargs'])
            for token,row in getattr(se,'_effect_dispatch_receipts',{}).items():
                if token not in before and row.get('status')=='execution_failed' and isinstance(row.get('result'),ErrorChoiceRejected):raise row['result']
            return result
        if getattr(e,'_reactive_move_transaction',False):return apply(e,a,t)
        return __import__('reactive_ability_events').atomic_move(e,a,t,apply)
    return run


def native_frame_required(e,actor,source):
    """Only actual printed referenced Moves need this native proof producer."""
    child=getattr(e,'_glitch_metronome_child',None)
    if child and child['effect_user_id']==actor.entity_id and child['choice']['move_id']==source:
        _metronome_state(e,e._move_completions[child['parent_id']])
        return True
    if source not in CLASS_MOVES:return False
    selected_move(e.r,source)
    return True


def arm_snatch(e,actor,*,target):
    """The shared actual Interrupt owner supplies payment, trigger and routing."""
    selected_move(e.r,SNATCH)
    return __import__('combat_move_reactions').arm(e,actor,SNATCH,target=target)


def project_move(e,actor,target,move,mechanics):
    if move['id']==DISABLE:
        if not move_authority(e,actor,target,DISABLE,DISABLE):raise ValueError('Disable needs its actual hit and Free/no-Command source')
        trigger=_disable_trigger(e,actor,e._glitch_disable_trigger[1])
        return move,dict(mechanics,effects_exec=[{'type':'apply_status','status':'사슬묶기','parameters':{'move_id':trigger['move_id']}}])
    if move['id']==METRONOME:
        selected_move(e.r,METRONOME)
        if actor is not target:raise ValueError('Metronome actual parent must use its printed Self range')
        if actor.entity_id not in getattr(e,'_glitch_metronome_choices',{}):raise ValueError('Metronome needs a fresh observed random Move selection callback')
        return move,dict(mechanics,effects_exec=[{'type':'random_move'}])
    return move,mechanics


def arm_metronome(e,actor,decision,*,burst=False):
    W.require_actors(e,actor);selected_move(e.r,METRONOME)
    import combat_move_reactions as REACTION
    snatch=actor.spec.get(REACTION.CHOICES,{}).get(SNATCH)
    retained=[row for row in actor.spec.get(REACTION.EVENTS,{}).values() if row['source']==SNATCH and row['trigger_move']==METRONOME and row['status'] in ('resolving','complete') and getattr(e,'_move_completions',{}).get(row['completion_id'],{}).get('phase')=='targets']
    if snatch is None and not retained:__import__('priority_actions')._owned_move(e,actor,METRONOME)
    elif retained:
        for row in retained:REACTION.validate_event(e,actor,row)
    else:__import__('priority_actions')._owned_move(e,actor,SNATCH)
    if not callable(decision) or type(burst)is not bool:raise ValueError('fresh actual Metronome selection and explicit Burst choice required')
    if burst:require(e,actor,BURST)
    e._glitch_metronome_choices={**getattr(e,'_glitch_metronome_choices',{}),actor.entity_id:(decision,burst)}


def metronome_pool(rules):
    selected_move(rules,METRONOME)
    excluded={rules.move_id(v) for v in METRONOME_EXCLUDED}
    if None in excluded:raise ValueError('all printed Metronome exclusions must resolve exactly')
    pool=sorted(mid for mid in rules.moves if mid not in excluded and mid not in rules.excluded_moves and rules._selected_rule(mid)==mid)
    if not pool:raise ValueError('selected actual Move pool is empty')
    return pool


def preflight_metronome(e,actor,target,effect,source,context=None):
    if source!=METRONOME or effect!={'type':'random_move'}:raise ValueError('random Move effect has no exact native Metronome owner')
    selected_move(e.r,METRONOME)
    if context and context.get('move_completion'):
        parent=e._move_completions.get(context['move_completion'])
        if parent is None or parent['actor'] is not actor or parent['move_id']!=METRONOME:raise ValueError('actual paid Metronome context required')
        actual=__import__('combat_move_reactions').snatch_recipient(e,actor,target,METRONOME,context) or actor
        if target is not actual:raise ValueError('Metronome effect user differs from its actual recipient')
    elif target is not actor:raise ValueError('Metronome parent must declare its printed Self target')
    __import__('priority_actions')._owned_move(e,actor,METRONOME)
    metronome_pool(e.r)
    return True


def _metronome_parent(e,actor,ctx,*,historical=False,mapping=True):
    import effect_contracts as C,action_lifecycle as A
    row=getattr(e,'_move_completions',{}).get(ctx.get('move_completion'))
    if not row or row['move_id']!=METRONOME or row['targets']!=[row['actor']]:raise ValueError('actual paid Metronome parent Move completion required')
    paid=row['actor'];receipt=ctx.get('effect_receipt');occurrence=ctx.get('effect_occurrence')
    actual=e._effect_dispatch_receipts.get(receipt)
    if actual is None:raise ValueError('actual Metronome dispatcher receipt required')
    C.validate_receipt(e,receipt,METRONOME,occurrence,paid,actor,{'type':'random_move'})
    if A.move_frame(e,row) is None or row['move'].get('range')!='자신':raise ValueError('actual native Metronome Self frame required')
    if not historical and (row['round']!=e.round_no or row['seconds']!=e.elapsed_seconds or row['phase']!='targets'):raise ValueError('Metronome parent continuation lifetime changed')
    # The mapping API admits only the live routed recipient or its own retained
    # receipt. In particular, actor need not be one of the declared Self targets.
    if mapping:
        with C.resuming(e,receipt):
            user=__import__('combat_move_reactions').snatch_recipient(e,paid,actor,METRONOME,ctx) or paid
        if actor is not user:raise ValueError('Metronome paid actor and actual effect user changed')
    else:
        # Read-only validation must not open a second dispatcher resume scope
        # while the actual generated child is itself resolving an effect.
        routes=[entry for entry in row.get('defense',{}).values() if entry.get('source_route',{}).get('source')==SNATCH]
        if routes:
            if len(routes)!=1 or routes[0]['source_route']['actor_id']!=actor.entity_id:raise ValueError('Metronome retained Snatch effect user changed')
            proof=routes[0]['source_route'];reaction=actor.spec.get(__import__('combat_move_reactions').EVENTS,{}).get(proof['reaction_id'])
            if reaction is None or reaction['completion_id']!=row['id'] or reaction['result_completion']!=proof['response_completion'] or reaction['status']!='complete':raise ValueError('Metronome retained Snatch response changed')
            __import__('combat_move_reactions').validate_event(e,actor,reaction)
        elif actor is not paid:raise ValueError('Metronome effect user lacks its actual Snatch route')
    return row


def _metronome_facts(state):
    return {key:state[key] for key in ('parent_id','paid_actor_id','effect_user_id','generated','choice','enhanced','occurrence','parent_profile','child_profile','round','seconds','history')}


def _metronome_state(e,parent,*,historical=False):
    import effect_contracts as C,root_resolution as R,action_lifecycle as A
    state=parent.get('metronome_child')
    if not state:return None
    if state.get('fingerprint')!=R.fingerprint(_metronome_facts(state)):raise ValueError('Metronome generated choice or payment prefix changed')
    index=W.actor_index(e);actor=index.get(state['effect_user_id']);paid=index.get(state['paid_actor_id'])
    if actor is None or paid is not parent['actor'] or state['parent_id']!=parent['id']:raise ValueError('Metronome actual parent or effect user changed')
    ctx={'move_completion':parent['id'],'effect_receipt':state['receipt'],'effect_occurrence':state['occurrence']}
    _metronome_parent(e,actor,ctx,historical=historical,mapping=False)
    if e._effect_dispatch_receipts[state['receipt']].get('metronome_parent')!=parent['id']:raise ValueError('Metronome dispatcher receipt parent changed')
    if state['parent_profile']!=C.source_profile(e,METRONOME) or state['child_profile']!=C.source_profile(e,state['choice']['move_id']):raise ValueError('Metronome selected source profile changed')
    if len(state['generated'])!=(3 if state['enhanced'] else 1) or state['choice']['move_id'] not in state['generated'] or any(mid not in metronome_pool(e.r) for mid in state['generated']):raise ValueError('Metronome selected child lost its actual generated pool')
    if state['choice']['target_id'] not in index or type(state['enhanced'])is not bool:raise ValueError('Metronome selected recipient or Burst declaration changed')
    if state['phase'] not in ('selected','running','waiting','complete'):raise ValueError('Metronome child phase changed')
    if state['phase']!='complete' and (state['round']!=e.round_no or state['seconds']!=e.elapsed_seconds or paid._action_history[:len(state['history'])]!=state['history']):raise ValueError('Metronome paid continuation boundary changed')
    event=e._passive_events.get(state.get('event_id'))
    if event is not None:
        if event['actor'] is not paid or event['target'] is not actor or event['completion_id']!=parent['id'] or event['move_id']!=METRONOME:raise ValueError('Metronome original recipient event changed')
        if actor is not paid or event.get('defense_parent'):
            received=parent.get('received',{}).get(actor.entity_id)
            if received is None or received['child_event']!=event['id'] or state['receipt'] not in received['effects'] or not received['hit'] or received['cancelled']:raise ValueError('Metronome child needs its actual parent received evidence')
        elif state['phase']!='complete':
            continuation=event.get('continuation',{})
            if continuation.get('kind')!='recipient_return' or state['receipt'] not in continuation['result']['effects']:raise ValueError('Metronome child needs its retained native recipient return')
    elif state['phase']!='selected':raise ValueError('Metronome child lost its actual recipient boundary')
    frame=state.get('frame')
    if frame is not None:
        __import__('move_completion').validate_trigger_frame(e,frame)
        if frame.get('metronome_parent')!=parent['id'] or frame.get('metronome_receipt') is not state['receipt'] or frame.get('metronome_selection')!=state['fingerprint'] or frame['actor'] is not actor or frame['source']!=state['choice']['move_id'] or frame['kind']!='move' or not frame.get('trigger_granted_payment'):raise ValueError('Metronome child native grant frame changed')
    child_id=state.get('child_completion')
    if child_id is not None:
        child=e._move_completions.get(child_id)
        if child is None or child['actor'] is not actor or child['move_id']!=state['choice']['move_id'] or child['targets']!=[index[state['choice']['target_id']]] or A.move_frame(e,child) is not frame:raise ValueError('Metronome child completion or native frame changed')
        if state['phase']=='complete' and child['phase']!='complete':raise ValueError('Metronome effect completed before its actual child')
    if event is not None and event['phase']=='activated' and 'checkpoint' in state:
        if state['checkpoint']!=_metronome_checkpoint(e,parent,state,event):raise ValueError('Metronome retained parent producer tail changed')
    if state['phase']=='complete':
        outcome={'child_completion':child_id,'cancelled':state.get('cancelled',False),'cancelled_by':state.get('cancelled_by')}
        if state.get('result_fingerprint')!=R.fingerprint(outcome):raise ValueError('Metronome completed child disposition changed')
        if child_id is None:
            import combat_move_reactions as REACTION
            response=next((r for owner in e.everyone for r in owner.spec.get(REACTION.EVENTS,{}).values() if r['id']==state.get('cancelled_by')),None)
            if frame is None or not state.get('cancelled') or response is None or response['source'] not in (REACTION.SUCKER,REACTION.UPPER) or response['status']!='complete' or response['native_action_id']!=frame['id']:raise ValueError('Metronome cancellation lacks its actual pre-initiation reaction')
            REACTION.validate_event(e,index[response['actor_id']],response)
            if response['attacker_id']!=actor.entity_id or response['trigger_move']!=state['choice']['move_id']:raise ValueError('Metronome cancellation response belongs to another generated Move')
            if response['source']==REACTION.UPPER:
                received=__import__('move_completion').recipient_result(e._move_completions[response['result_completion']],actor)
                if not received or not received['hit'] or received.get('cancelled'):raise ValueError('Metronome Upper cancellation requires its actual successful response')
        actual=e._effect_dispatch_receipts[state['receipt']]
        if actual['status']!='completed' or actual.get('result')!={'metronome_parent':parent['id'],'child_completion':child_id,'cancelled':state.get('cancelled',False)}:raise ValueError('Metronome effect lost its actual child result')
    return state


def metronome_effect(e,actor,target,effect,ctx):
    """Retain one actual generated selection; the native recipient owns dispatch."""
    import effect_contracts as C,root_resolution as R,common_checks as CHECKS
    preflight_metronome(e,actor,target,effect,METRONOME,ctx)
    parent=_metronome_parent(e,target,ctx)
    if parent.get('metronome_child'):raise ValueError('Metronome effect may generate only once')
    choices=getattr(e,'_glitch_metronome_choices',{})
    original=choices.get(actor.entity_id);selected=choices.get(target.entity_id)
    if original is None or selected is None:raise ErrorChoiceRejected('fresh Metronome callback required for its actual effect user')
    decision,receiver_burst=selected;enhanced=original[1]
    if target is not actor and receiver_burst:raise ErrorChoiceRejected('Snatch effect recipient did not use the paid Metronome Burst trigger')
    if enhanced:
        try:_burst_pay(e,actor,parent)
        except (ValueError,KeyError,TypeError) as error:raise ErrorChoiceRejected('Metronome Burst cannot pay its actual source cost') from error
    parent=e._move_completions[parent['id']]
    callback_boundary=C.boundary(e,actor,target);callback_history=list(actor._action_history)
    generated=[e.rng.choice(metronome_pool(e.r)) for _ in range(3 if enhanced else 1)]
    try:choice=decision(tuple(generated))
    except Exception as error:raise ErrorChoiceRejected('Metronome selection callback failed') from error
    if callback_boundary!=C.boundary(e,actor,target) or callback_history!=actor._action_history:raise ErrorChoiceRejected('Metronome selection callback changed the paid action boundary')
    parent=_metronome_parent(e,target,ctx)
    if type(choice)is not dict or set(choice)-{'move_id','target_id','aim','set_damage'} or not {'move_id','target_id'}<=set(choice):raise ErrorChoiceRejected('explicit generated Move and actual target choice required')
    mid=e.r.move_id(choice['move_id']);recipient=W.actor_index(e).get(choice['target_id'])
    if mid not in generated or recipient is None or type(choice.get('set_damage',False))is not bool:raise ErrorChoiceRejected('select one actual generated Metronome Move and actual recipient')
    choice=deepcopy(dict(choice,move_id=mid))
    state={'parent_id':parent['id'],'paid_actor_id':actor.entity_id,'effect_user_id':target.entity_id,'generated':generated,'choice':choice,'enhanced':enhanced,
           'receipt':ctx['effect_receipt'],'occurrence':ctx['effect_occurrence'],'parent_profile':C.source_profile(e,METRONOME),'child_profile':C.source_profile(e,mid),
           'round':e.round_no,'seconds':e.elapsed_seconds,'history':list(actor._action_history),'phase':'selected','child_completion':None}
    state['fingerprint']=R.fingerprint(_metronome_facts(state));parent['metronome_child']=state
    e._effect_dispatch_receipts[state['receipt']]['metronome_parent']=parent['id']
    choices.pop(actor.entity_id,None);choices.pop(target.entity_id,None)
    return CHECKS.PendingDecision('actual selected Metronome child must return')


def metronome_child_scope(e,actor):
    state=getattr(e,'_glitch_metronome_child',None)
    if state is None or state['effect_user_id']!=actor.entity_id:return False
    _metronome_state(e,e._move_completions[state['parent_id']])
    stack=getattr(e,'_native_action_stack',());uses=getattr(e,'_event_use_scopes',())
    event=e._passive_events[state['event_id']];parent=e._passive_events.get(event.get('defense_parent'),event)
    prefix=parent.get('continuation',{}).get('scopes')
    return bool(state['phase']=='running' and stack and stack[-1]['actor'] is actor and stack[-1]['source']==state['choice']['move_id'] and
                prefix is not None and list(uses[:-1])==prefix and len(uses)==len(prefix)+1 and uses[-1]['actor'] is actor and
                uses[-1]['target'].entity_id==state['choice']['target_id'] and uses[-1]['move_id'] in (None,state['choice']['move_id']))


def metronome_bind_grant(e,actor,mid):
    """Called only after the existing opaque source grant has been consumed."""
    state=getattr(e,'_glitch_metronome_child',None)
    if state is None:return
    frame=e._native_action_stack[-1]
    if actor.entity_id!=state['effect_user_id'] or mid!=state['choice']['move_id'] or frame['actor'] is not actor or frame['source']!=mid or not frame.get('trigger_granted_payment'):raise ValueError('Metronome actual native child payment required')
    if state.get('frame') is not None:raise ValueError('Metronome child grant already consumed')
    frame.update(metronome_parent=state['parent_id'],metronome_receipt=state['receipt'],metronome_selection=state['fingerprint'])
    state['frame']=frame


def _metronome_join(e,parent,state):
    """Find the real child without manufacturing a completion for pre-initiation."""
    frame=state.get('frame')
    children=[row for row in e._move_completions.values() if frame is not None and row.get('native_action_frame') is frame]
    if len(children)>1:raise ValueError('Metronome grant produced multiple child completions')
    if children:
        child=children[0]
        if state['child_completion'] not in (None,child['id']):raise ValueError('Metronome child completion changed')
        state['child_completion']=child['id']
        if child['phase']!='complete':return False
        state['cancelled']=all(result.get('cancelled') for result in child['results'].values())
        return True
    if frame is not None:
        import combat_move_reactions as REACTION
        for reactor in e.everyone:
            for response in reactor.spec.get(REACTION.EVENTS,{}).values():
                if response['source'] not in (REACTION.SUCKER,REACTION.UPPER) or response['native_action_id']!=frame['id'] or response['status']!='complete':continue
                REACTION.validate_event(e,reactor,response)
                actor=W.actor_index(e)[state['effect_user_id']]
                received=__import__('move_completion').recipient_result(e._move_completions[response['result_completion']],actor)
                cancelled=(response['source']==REACTION.SUCKER and actor.fainted) or (response['source']==REACTION.UPPER and received and received['hit'] and not received.get('cancelled'))
                if cancelled and response['attacker_id']==actor.entity_id and response['trigger_move']==state['choice']['move_id'] and frame['id'] in e._native_action_resolutions and e._native_action_resolutions[frame['id']]['phase']=='producer_returned':
                    state['cancelled']=True;state['cancelled_by']=response['id'];return True
    return False


def _metronome_finish(e,parent,state):
    import effect_contracts as C
    if not _metronome_join(e,parent,state):return False
    state['phase']='complete'
    state['result_fingerprint']=__import__('root_resolution').fingerprint({'child_completion':state['child_completion'],'cancelled':state.get('cancelled',False),'cancelled_by':state.get('cancelled_by')})
    C.finish(e,state['receipt'],'completed',{'metronome_parent':parent['id'],'child_completion':state['child_completion'],'cancelled':state.get('cancelled',False)})
    event=e._passive_events[state['event_id']]
    result=parent['received'][event['target'].entity_id] if event.get('defense_parent') else event['continuation']['result']
    if result['held']!=state['return_args']['held'] or result['held']<1:raise ValueError('Metronome native held effect count changed')
    result['held']-=1;e.effect_stats['held']-=1;e.effect_stats['done']+=1
    parent['metronome_result']={'generated':list(state['generated']),'chosen':state['choice']['move_id'],'child_completion':state['child_completion'],'enhanced':state['enhanced'],'effect_user_id':state['effect_user_id'],'cancelled':state.get('cancelled',False)}
    _metronome_state(e,parent)
    return True


def _metronome_checkpoint(e,parent,state,event):
    import passive_events as P,move_defense_reactions as D,root_resolution as R
    if event.get('defense_parent'):
        original=e._passive_events[event['defense_parent']]
        received=parent['received'][event['target'].entity_id]
        facts={'route':original['continuation']['fingerprint'],'recipient':{k:v for k,v in received.items() if k not in ('effects','held')}}
        facts=D._move_facts(facts)
    else:
        facts=P._continuation_facts(e,event,event['continuation'])
        facts['recipient_return'].pop('held',None)
    return R.fingerprint({'event_id':event['id'],'facts':facts,'return_args':state['return_args'],'selection':state['fingerprint']})


def metronome_begin_child(e,event,return_args):
    """Run after the native hit is retained, before the parent's listeners return."""
    import action_lifecycle as A,passive_events as P,effect_contracts as C
    parent=e._move_completions.get(event.get('completion_id'),{})
    state=parent.get('metronome_child')
    if not state or event['target'].entity_id!=state['effect_user_id'] or event['move_id']!=METRONOME:return
    if state['phase']=='complete':return
    if state['phase']!='selected':raise ValueError('Metronome selected child cannot restart')
    state['event_id']=event['id'];state['return_args']=dict(return_args)
    state['checkpoint']=_metronome_checkpoint(e,parent,state,event)
    _metronome_state(e,parent)
    if getattr(e,'_glitch_metronome_child',None):raise ValueError('one live Metronome child source grant at a time')
    actor=W.actor_index(e)[state['effect_user_id']];choice=state['choice'];target=W.actor_index(e)[choice['target_id']]
    ctx={'move_completion':parent['id'],'effect_receipt':state['receipt'],'effect_occurrence':state['occurrence']}
    _metronome_parent(e,actor,ctx)
    state['phase']='running';e._glitch_metronome_child=state
    previous=getattr(e,'_event_use_scopes',None)
    e._event_use_scopes=list(previous or ())
    try:
        with C.resuming(e,state['receipt']):
            with A.move_grant(e,actor,target,choice['move_id'],source=METRONOME,kind='free') as grant:
                e.use_move(actor,target,choice['move_id'],count_use=False,free_action=True,_action_grant=grant,aim=choice.get('aim'),set_damage=choice.get('set_damage',False))
        parent=e._move_completions[parent['id']];state=parent['metronome_child']
        if not _metronome_finish(e,parent,state):raise ValueError('Metronome native child did not return or register a native wait')
    except P.PassiveEventPending as pending:
        parent=e._move_completions[parent['id']];state=parent['metronome_child']
        if e._passive_pending!=pending.event_id or pending.event_id not in e._passive_events or state.get('frame') is None:raise
        state['phase']='waiting';state['pending_event']=pending.event_id
        _metronome_join(e,parent,state)
        raise
    except __import__('heavy_injury_adapter').HeavyPending as pending:
        parent=e._move_completions[parent['id']];state=parent['metronome_child']
        if e._heavy_pending!=pending.event_id:raise
        state['phase']='waiting';state['pending_heavy']=pending.event_id
        _metronome_join(e,parent,state)
        raise
    finally:
        vars(e).pop('_glitch_metronome_child',None)
        if previous is None:vars(e).pop('_event_use_scopes',None)
        else:e._event_use_scopes=previous


def resume_metronome(e,event,result):
    import passive_events as P,action_lifecycle as A
    for parent in list(getattr(e,'_move_completions',{}).values()):
        state=parent.get('metronome_child')
        if not state or state['phase']!='waiting':continue
        _metronome_state(e,parent)
        if not _metronome_finish(e,parent,state):continue
        original=e._passive_events[state['event_id']]
        outer=e._passive_events.get(original.get('defense_parent'),original)
        previous=getattr(e,'_event_use_scopes',None);e._event_use_scopes=list(outer['continuation']['scopes'])
        try:
            with A.resume_move(e,original):
                P.complete(e,original['id'],**dict(state['return_args'],held=state['return_args']['held']-1))
                if original.get('defense_parent'):return P.deliver(e,original['defense_parent'])
                return P._finish_recipient_return(e,original['continuation'])
        finally:
            if previous is None:vars(e).pop('_event_use_scopes',None)
            else:e._event_use_scopes=previous
    return result

def _burst_pay(e,actor,completion):
    require(e,actor,BURST)
    if completion['actor'] is not actor or completion['move_id'] not in CLASS_MOVES:raise ValueError('Burst requires an actual Glitch Bender Move')
    if completion.get('full_turn')!=__import__('action_lifecycle').current_full_turn(e):raise ValueError('Burst requires the same actual triggering full-turn witness')
    key=BURST+':activation:'+completion['id'];F=__import__('frequency')
    if not F.activation_allowed(actor,key,SCENE,engine=e,action_actor=actor):raise ValueError('that native Move already triggered Burst')
    _pay(e,actor,BURST,'swift',ap=2);F.consume_activation(actor,key,SCENE,engine=e,action_actor=actor)


def burst(e,actor,event_id,*,regain=None):
    import move_completion as M,frequency as F,combat_timing as TIME
    require(e,actor,BURST);receipt=M.require_returned_event(e,event_id);event=e._passive_events[event_id];row=e._move_completions[receipt['completion_id']]
    if row['actor'] is not actor or row['round']!=e.round_no or row['seconds']!=e.elapsed_seconds or row['move_id'] not in (DISABLE,SNATCH,TOPSY):raise ValueError('actual current triggering Glitch Bender Move required; Metronome is chosen during native generation')
    mid=row['move_id'];target=event['target']
    if mid==TOPSY:M.require_hit_return(e,event_id,target)
    if mid==SNATCH:
        selected=e.r.move_id(regain)
        if selected not in CLASS_MOVES:raise ValueError('regain one printed Glitch Bender Move use')
        key=BURST+':regain:'+selected
        if not F.activation_allowed(actor,key,SCENE,engine=e,action_actor=actor):raise ValueError('that Move already regained its use this Scene')
        kind=F.move_frequency(e,selected,actor)[0]
        if kind in ('scene','daily'):F.preflight_restore_move_use(e,actor,selected)
        elif kind=='every_other_turn':
            if not F.state(actor)['moves'].get(selected):raise ValueError('Move must have an actually spent use')
        else:raise ValueError('Move has no spent frequency use to restore')
    elif regain is not None:raise ValueError('only Snatch Burst regains a Move use')
    def apply(se,a,t):
        actual=M.require_returned_event(se,event_id);current=se._move_completions[actual['completion_id']]
        returned=actual['native_return']
        if (returned['action_history']!=list(getattr(a,'_action_history',[])) or returned['turn_serial']!=a.custom_conditions.get('combat_turn_serial',0)):
            raise ValueError('Burst requires the immediate actual Move return, before an unrelated action')
        _burst_pay(se,a,current)
        if mid==DISABLE:se.apply_status(t,'억압',source=BURST,applied_by=a)
        elif mid==SNATCH:
            if kind=='scene':F.restore_scene_use(se,a,selected)
            elif kind=='daily':F.restore_daily_use(se,a,selected)
            else:F.restore_eot(se,a,selected)
            F.consume_activation(a,key,SCENE,engine=se,action_actor=a)
        else:
            selection=acquired(a,BURST)['snapshot']['selection'];held='혼란' in t.conditions
            applied=se.apply_status(t,'혼란',source=BURST,applied_by=a)
            glitch=t.kind=='pokemon' and '에러' in t.types
            if not held and applied and '혼란' in t.conditions and (selection['confusion_cure']=='english_target' or glitch):
                deadline=t.custom_conditions.get('combat_turn_serial',0)+1
                proof={'actor_id':a.entity_id,'target_id':t.entity_id,'event_id':event_id,'acquisition':deepcopy(acquired(a,BURST)),'deadline':deadline,'glitch_target':glitch}
                proof['integrity']=__import__('trainer_feature_acquisition')._digest('glitch-burst/v1',proof)
                TIME.install(se,t,{'source':BURST,'turn_owner':t,'turn_deadline':deadline,'statuses':['혼란'],'glitch_burst':proof})['owned_statuses'].add('혼란')
        return {'source':BURST,'trigger':mid,'completion_id':current['id']}
    return G.transition(e,actor,apply,participants=(target,),include_rulings=True)

def code_declaration(bug):
    return {'type':'attack','class':'변화','ac':2,'_rule_id':CODE,'on_hit':{'type':'glitch_code','bug':bug}}


def install(rules):
    """The printed attack identity is stable before any world can be saved."""
    unit=rules.selection.units.get(CODE)
    if unit is None or CODE in rules.ruleset.unit_versions or not rules.ruleset.allows(unit)[0]:return
    uid='derived/ability-attack/'+CODE
    if uid not in rules.selection.units:
        rules.selection.register_derived({'id':uid,'title':'코드 투입','source':unit['source']},(CODE,'combat/accuracy-roll'))


def code_move(e):
    uid='derived/ability-attack/'+CODE
    selected=e.r.selection.require_supported_version(CODE)
    if selected!=CODE:raise ValueError('exact acquired Code Injection attack source required')
    e.r.selection.require_supported_version(uid)
    return {'id':uid,'name':'코드 투입','class':'변화','type':'노말','ac':2,'damage_base':None,
            'range':'5, 대상 1','_class_move_range':{'origin':5,'targets':1,'parsed':True}}


def code_attack_record(e,receipt):
    import effect_contracts as C,trainer_feature_acquisition as T
    row=getattr(e,'_effect_dispatch_receipts',{}).get(receipt)
    if not row or row.get('receipt') is not receipt:raise ValueError('actual Code Injection attack receipt required')
    state=row.get('code_injection');facts=None if state is None else state.get('facts')
    if not isinstance(facts,dict) or state.get('integrity')!=T._digest('glitch-code-attack/v1',facts):
        raise ValueError('Code Injection original paid attack facts changed')
    if row['effect']!=code_declaration(facts['bug']):raise ValueError('Code Injection attack payload changed')
    C.validate_receipt(e,receipt,CODE,row['occurrence'],row['actor'],row['target'],code_declaration(facts['bug']))
    _historical_acquisition(e.r,facts['acquisition'],CODE,row['actor'].entity_id)
    payment=facts['payment']
    if (facts['actor_id']!=row['actor'].entity_id or facts['target_id']!=row['target'].entity_id
            or facts['bug'] not in BUGS or payment.get('actor_id')!=facts['actor_id']
            or payment.get('amount')!=1 or payment.get('mode')!='spend' or payment.get('refunded') is not False
            or facts['action']!='standard' or state.get('phase') not in ('ready','defense','effect','complete')):
        raise ValueError('Code Injection actual actor/recipient/action/AP payment changed')
    if (type(payment)is not dict or set(payment)!={'actor_id','mode','amount','ordinary','temporary','refunded'}
            or type(payment['ordinary'])is not int or not 0<=payment['ordinary']<=1
            or type(payment['temporary'])is not list
            or sum(x['amount'] for x in payment['temporary'])+payment['ordinary']!=1):
        raise ValueError('Code Injection original AP funding receipt changed')
    if state['phase']!='complete':
        history=getattr(row['actor'],'_action_history',[])
        if (e.round_no!=facts['round'] or row['actor'].custom_conditions.get('combat_turn_serial',0)!=facts['turn']
                or len(history)!=facts['history_length'] or not history or history[-1]!='standard'):
            raise ValueError('Code Injection lost its original paid Standard action boundary')
    native=state.get('native_frame')
    if native is not None and native.get('id') is not None:
        action=getattr(e,'_native_action_resolutions',{}).get(native['id'])
        if (native.get('actor') is not row['actor'] or native.get('kind')!='ability_attack'
                or native.get('source')!='derived/ability-attack/'+CODE or action is None
                or any(action.get(k)!=native.get(k) for k in ('actor','kind','source'))):
            raise ValueError('Code Injection native action receipt changed')
    if state['phase']!='ready':
        if state.get('accuracy') is None or native is None or native.get('id') is None:
            raise ValueError('Code Injection phase lacks its original native accuracy/action')
        observed=[fact for trigger in action['triggers'] if trigger['actor'] is row['actor'] and trigger['source']==native['source']
                  for fact in trigger['observations'] if fact.get('event')=='native_accuracy']
        if observed!=[{'event':'native_accuracy','effect_occurrence':row['occurrence']}]:
            raise ValueError('Code Injection native frame belongs to another attack occurrence')
    if state.get('accuracy') is not None:
        hit,natural,critical=state['accuracy']
        if type(hit)is not bool or type(critical)is not bool or natural is not None and (type(natural)is not int or not 1<=natural<=20):
            raise ValueError('actual native Code Injection accuracy required')
        if state.get('accuracy_integrity')!=T._digest('glitch-code-accuracy/v1',{'occurrence':row['occurrence'],'accuracy':state['accuracy'],'facts':facts}):
            raise ValueError('Code Injection observed accuracy changed')
    application=state.get('application')
    if application is not None:
        facts_applied={k:application[k] for k in ('round','count','occurrence')}
        if application.get('integrity')!=T._digest('glitch-code-application/v1',facts_applied):
            raise ValueError('Code Injection application boundary changed')
        C.validate_receipt(e,application['receipt'],CODE,application['occurrence'],row['actor'],row['target'],{'type':'glitch_code','bug':facts['bug']})
    return row


def code_frame(e,actor,source,receipt):
    row=code_attack_record(e,receipt);state=row['code_injection'];frame=state.get('native_frame')
    if row['actor'] is not actor or source!='derived/ability-attack/'+CODE or state['phase']=='complete' or frame is None:
        raise ValueError('actual unfinished Code Injection action required')
    actual=e._native_action_resolutions.get(frame['id'])
    if actual is None or actual['actor'] is not actor or actual['source']!=source or actual['kind']!='ability_attack':
        raise ValueError('Code Injection lost original native action resolution')
    return frame


def code_event(e,event):
    row=code_attack_record(e,event.get('code_receipt'));state=row['code_injection']
    if (event.get('producer')!='glitch_bender.code_attack' or event['kind']!='attack'
            or event['source']!='derived/ability-attack/'+CODE or event['actor'] is not row['actor']
            or event['target'] is not row['target'] or state.get('precision_id')!=event['id']
            or state.get('accuracy') is None or event.get('natural')!=state['accuracy'][1]
            or event['result']!=('accuracy_hit' if state['accuracy'][0] else 'miss')):
        raise ValueError('Code Injection native Attack observation changed')
    return row


def ensure_code_clear(e):
    import initiative_interrupts as I
    for token,row in getattr(e,'_effect_dispatch_receipts',{}).items():
        state=row.get('code_injection')
        if state is None or state['phase']=='complete':continue
        code_attack_record(e,token)
        if getattr(e,'_glitch_code_resuming',None) is token:continue
        active=getattr(e,'_glitch_code_activation',None)
        if active and active[1] is row['actor'] and active[2] is row['target']:continue
        frame=I.frame(e)
        if frame:
            trigger=getattr(e,I.KEY)['windows'][frame['window_id']]['trigger']
            if trigger['kind']=='native_accuracy' and trigger['event_id']==state.get('precision_id'):continue
        raise ValueError('finish the original paid Code Injection attack before another action or clock boundary')


def code_attack(e,actor,target,effect,ctx):
    import effect_contracts as C,action_lifecycle as A,confusion_attacks as CONFUSION
    import precise_actions as P,move_defense_reactions as D,trainer_feature_acquisition as T
    receipt=ctx['effect_receipt'];row=e._effect_dispatch_receipts[receipt]
    C.validate_receipt(e,receipt,CODE,ctx['effect_occurrence'],actor,target,effect)
    if 'code_injection' not in row:
        frame=getattr(e,'_glitch_code_activation',None)
        if frame is None or ctx.get('glitch_code_token') is not frame[0]:raise ValueError('actual paid Code Injection dispatch required')
        preflight_code(e,actor,target,effect,CODE)
        facts={'actor_id':actor.entity_id,'target_id':target.entity_id,'bug':frame[3],
               'acquisition':deepcopy(frame[4]),'fixed_accuracy':frame[5],'payment':deepcopy(frame[6]),
               'action':'standard','round':e.round_no,'turn':actor.custom_conditions.get('combat_turn_serial',0),
               'history_length':len(actor._action_history)}
        row['code_injection']={'facts':facts,'integrity':T._digest('glitch-code-attack/v1',facts),'phase':'ready'}
    row=code_attack_record(e,receipt);state=row['code_injection'];move=code_move(e)
    if state['phase']=='complete':return None
    resumed=receipt if state.get('native_frame') is not None else None
    with A.resolution(e,actor,move['id'],kind='ability_attack',_ability_attack=resumed) as frame:
        state['native_frame']=frame
        if state['phase']=='ready':
            __import__('eldritch_magic').preflight(e,actor,move)
            CONFUSION.preflight(e,actor,move);CONFUSION.observe_action(e,actor,move)
            event=P.attacked(e,actor,target,move,producer='glitch_bender.code_attack')
            hit,natural,critical=e.accuracy_check(actor,target,move,fixed_roll=state['facts']['fixed_accuracy'])
            state['accuracy']=[hit,natural,critical]
            state['accuracy_integrity']=T._digest('glitch-code-accuracy/v1',{'occurrence':row['occurrence'],'accuracy':state['accuracy'],'facts':state['facts']})
            P.accuracy(event,hit,natural=natural)
            if event is not None:event['code_receipt']=receipt;state['precision_id']=event['id']
            A.observe_resolution(e,actor,move['id'],{'event':'native_accuracy','effect_occurrence':row['occurrence']})
            state['phase']='defense'
        hit,natural,critical=state['accuracy']
        if state['phase']=='defense':
            if hit and state.get('precision_id') is not None:
                event=D.native_event(e,state['precision_id'])
                try:result=D.native_splash(e,event,{'kind':'code_injection','occurrence':row['occurrence']})
                except __import__('passive_events').PassiveEventPending:
                    state=code_attack_record(e,receipt)['code_injection']
                    state['native_frame']['deferred']=True
                    return __import__('common_checks').PendingDecision('finish the original Splash passive response')
                row=code_attack_record(e,receipt);state=row['code_injection'];frame=state['native_frame']
                if isinstance(result,__import__('common_checks').PendingDecision):
                    frame['deferred']=True;return result
            state['phase']='effect'
        if state['phase']=='effect' and 'children' not in state:
            eligible=not (actor.fainted or actor.dead or actor.hp<=0 or actor.captured or not actor.on_field
                          or target.dead or target.captured or not target.on_field)
            if not eligible:state['cancelled']='participant_unavailable_after_defense'
            if eligible and hit and __import__('substitute').intercept(e,actor,target,move) is None:
                __import__('duelist').ability_hit(e,actor,target,move['id'],row['occurrence'])
                __import__('channeler').hit(e,actor,target,'ability:'+move['id']+':'+row['occurrence'])
                __import__('eldritch_magic').after_hit(e,actor,target,move,natural,effect_receipt=receipt)
                import effects as FX
                result=FX.run_effects(e,actor,target,[effect['on_hit']],
                    dict(ctx,hit=True,nat=natural,code_attack_receipt=receipt),CODE)
                state['children']=result
            else:state['children']=C.BatchResult(0,0)
        if state['children'].pending:
            frame['deferred']=True
            return __import__('common_checks').PendingDecision('finish the original Code Injection effect occurrence')
        state['phase']='complete'
        action=e._native_action_resolutions[frame['id']]
        next(t for t in action['triggers'] if t['actor'] is actor and t['source']==move['id'])['status']='completed'
    return None


def resume_code_injection(e,actor,receipt):
    """Resume the actual paid attack after its native child, never reroll or repay."""
    import effect_contracts as C
    row=code_attack_record(e,receipt)
    if row['actor'] is not actor:raise ValueError('actual Code Injection attack owner required')
    if row['code_injection']['phase']=='complete':return row.get('result')
    def apply(se,a,target):
        row=code_attack_record(se,receipt);state=row['code_injection'];facts=state['facts']
        token=object();se._glitch_code_activation=(token,a,target,facts['bug'],facts['acquisition'],facts['fixed_accuracy'],facts['payment'])
        se._glitch_code_resuming=receipt
        try:
            C.finish(se,receipt,'dispatching')
            note=code_attack(se,a,target,row['effect'],{'effect_receipt':receipt,'effect_occurrence':row['occurrence'],'source_id':CODE,'glitch_code_token':token,'hit':True})
            pending=isinstance(note,__import__('common_checks').PendingDecision)
            result=note if pending else code_attack_record(se,receipt)['code_injection']['children']
            C.finish(se,receipt,'awaiting_input' if pending else 'completed',result)
            return result
        finally:
            del se._glitch_code_activation;del se._glitch_code_resuming
    return G.transition(e,actor,apply,participants=(row['target'],),include_rulings=True)

def validate_code_consumption(e,actor,index):
    import consumption_execution as EXEC,common_checks as C
    for row in EXEC.validate(actor).values():
        proof=row.get('benefit_suppression')
        if proof is None:continue
        if (type(proof)is not dict or set(proof)!={'source','attack_receipt','effect_receipt','effect_occurrence','target_id','round','count'}
                or proof['source']!=CODE or row['outcome']!='no_effect' or row['target_id']!=proof['target_id']
                or proof['target_id'] not in index):
            raise ValueError('exact no-benefit consumable suppression receipt required')
        attack=code_attack_record(e,proof['attack_receipt']);state=attack['code_injection'];application=state.get('application')
        if (state['facts']['bug']!='object_not_found' or attack['target'] is not index[proof['target_id']]
                or application is None or application['receipt'] is not proof['effect_receipt']
                or application['occurrence']!=proof['effect_occurrence']):
            raise ValueError('consumable suppression lost its actual Object Not Found hit')
        C.integer(proof['round'],'suppressed consumption round',application['round'],application['round']+1)
        C.integer(proof['count'],'suppressed consumption initiative')
        if (proof['round']==application['round'] and proof['count']>application['count']
                or proof['round']==application['round']+1 and proof['count']<=application['count']):
            raise ValueError('consumable suppression outside the actual one-round lifetime')
    for quota in actor.spec.get('consumable_lifetime',{}).get('quotas',{}).values():
        for receipt in quota['receipts']:
            if receipt.get('benefit_suppressed') is not True:continue
            user=index.get(receipt['user_id'])
            matches=[] if user is None else [r for r in EXEC.validate(user).values()
                if r['item_stock'] is receipt['item_stock'] and r.get('benefit_suppression')
                and r['target_id']==actor.entity_id and r['outcome']=='no_effect']
            if len(matches)!=1:raise ValueError('suppressed lifetime dose requires its actual paid no-benefit receipt')
def action_allowed(e,actor,source,move=None):
    """At the native payment boundary, source metadata also covers unmetered actions."""
    if not (code_rows(actor,'access_denied') or __import__('glitch_moves').access_rows(actor)):return True
    import frequency as F
    if isinstance(move,dict) and move.get('id') in e.r.moves:
        return frequency_allowed(actor,F.move_frequency(e,move['id'],actor)[0])
    if not isinstance(source,str):return True
    selected=source
    if selected not in e.r.selection.units:
        candidates=[uid for uid in e.r.selection.names.get(source,()) if uid.startswith(('feat/','gift/','edge/','ability/'))]
        if len(candidates)==1:selected=candidates[0]
        elif candidates:raise ValueError('Access Denied requires the actual action source frequency')
    if selected.startswith(('feat/','gift/','edge/')) and selected in e.r.selection.units:
        effects,header=e.r.feat_effects(selected)
        if effects is None:raise ValueError('actual Feature action frequency unavailable')
        return frequency_allowed(actor,F.parse(header.get('frequency'))[0])
    if selected.startswith('ability/') and selected in e.r.selection.units:
        title=e.r.selection.units[selected]['title']
        return frequency_allowed(actor,F.parse(e.r.ability_freq.get(title))[0])
    return True


def order_snatch(e,target,responders,*,reason):
    return __import__('snatch_dispatch').order(e,target,responders,reason=reason)


def choose_snatch_recipient(e,event_id,recipient,*,reason):
    return __import__('snatch_dispatch').choose(e,event_id,recipient,reason=reason)
