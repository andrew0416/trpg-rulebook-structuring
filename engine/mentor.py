"""Source-bound Mentor acquisitions and lessons over native permanent owners."""
from copy import deepcopy
from pathlib import Path
from hashlib import sha256
import json

CLASS='class/멘토'
LESSONS='feat/수업'
EXPAND='feat/시야-넓히기'
EXPAND_CSV='poke_edge/시야-넓히기'
GUIDANCE='feat/지침'
MOVE_TUTOR='feat/기술-가르침'
EGG_TUTOR='feat/교배-가르침'
LIFELONG='feat/평생학습'
SKILLS=('매력','직감','협박','포켓몬학')
FEATURES={CLASS:(618,620),LESSONS:(622,625),EXPAND:(627,631),GUIDANCE:(633,636),
          MOVE_TUTOR:(638,642),EGG_TUTOR:(644,648),LIFELONG:(650,653)}
CSV={uid:'C2CSV/input/db/feats.csv:R'+str(n)+':main' for uid,n in zip(FEATURES,range(104,111))}
TECHNIQUES={name:'C2CSV/input/db/class-data.csv:R'+str(n)+':technique' for name,n in
            zip(('changing','empowered','corrective','versatile'),range(16,20))}
LESSON_SKILLS=dict(zip(('changing','empowered','corrective','versatile'),('직감','매력','협박','포켓몬학')))
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'


def bind_expand_csv_source(rules,catalog):
    """Review only CSV64's extracted identity; do not admit miscellaneous edges."""
    path=Path(rules.root)/'data/mentor-source-contract.json'
    if EXPAND_CSV not in catalog or EXPAND not in catalog or not path.exists():return False
    data=json.loads(path.read_text(encoding='utf-8'))
    expected={'id':EXPAND_CSV,'file':'db/poke-edges.csv','record_span':[64,64],
        'sha256':'8e4bbb735033db781ca011f98885c1b5fe1b900da75a196b9e6f8734ceff946d',
        'feature':EXPAND,'feature_file':'ch04-trainer-classes.md','feature_lines':[627,631],
        'point_cost':0,'points':3,'action':'extended'}
    # The authenticated older contract omits only this published CSV64 link.
    link=data.get('expand_csv',expected)
    if (type(link)is not dict or set(link)-{'review'}!=set(expected) or
            json.dumps({key:link[key] for key in expected},sort_keys=True,allow_nan=False)!=
            json.dumps(expected,sort_keys=True,allow_nan=False) or
            data['source_hashes'].get('input/ch04-trainer-classes.md')!=SOURCE_SHA256):
        raise ValueError('reviewed Expand Horizons CSV/Book identity changed')
    unit=catalog[EXPAND_CSV];feature=catalog[EXPAND]
    if (link['id']!=EXPAND_CSV or link['feature']!=EXPAND or
            link['file']!='db/poke-edges.csv' or link['record_span']!=[64,64] or
            link['feature_file']!='ch04-trainer-classes.md' or link['feature_lines']!=[627,631] or
            unit['source'].get('file')!=link['file'] or unit['source'].get('record_span')!=link['record_span'] or
            unit['source'].get('sha256',link['sha256'])!=link['sha256'] or
            feature['source'].get('file')!=link['feature_file'] or feature['source'].get('lines')!=link['feature_lines']):
        raise ValueError('reviewed Expand Horizons CSV/Book identity changed')
    unit['source_group']=None
    unit['source'].update(sha256=link['sha256'],additional_files=[link['feature_file']],
        additional_snapshots={link['feature_file']:data['source_hashes']['input/'+link['feature_file']]})
    return True


def contract(rules):
    value=json.loads((Path(rules.root)/'data/mentor-source-contract.json').read_text(encoding='utf-8'))
    for file,digest in value['source_hashes'].items():
        if sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:
            raise ValueError('Mentor reviewed source changed: '+file)
    return value


def source(rules,feature,variant):
    if feature not in FEATURES or variant not in ('core','local_translation','local_csv'):
        raise ValueError('exact Mentor feature and source variant required')
    rules._selected_rule(feature);data=contract(rules)
    if variant=='core':
        reference=data['core']
        if sha256((Path(rules.root)/reference['file']).read_bytes()).hexdigest()!=reference['sha256']:
            raise ValueError('actual Core Mentor source changed')
        return {'variant':variant,'feature':feature,**deepcopy(reference),'pages':[88,89]}
    file='input/db/feats.csv' if variant=='local_csv' else 'input/ch04-trainer-classes.md'
    return {'variant':variant,'feature':feature,'clause_id':CSV[feature] if variant=='local_csv' else feature,
            'file':file,'sha256':data['source_hashes'][file]}


def acquired(actor,feature):
    import trainer_feature_acquisition as A,acquired_features as OWN
    if not OWN.owned_rule_count(actor,feature):return None
    if feature==CLASS:
        import mentor_csv as CSV_MENTOR
        if CSV_MENTOR.has_receipt(actor):
            row=CSV_MENTOR.receipt(actor);skills=list(row['selection']['values'])
            return {'request_id':row['acquisition_request_id'],'snapshot':{'skills':skills,
                'ranks':list(row['selection']['acquisition_snapshot']['ranks']),'parents':{},
                'source':source(actor.r,CLASS,'local_csv'),
                'selection':{'source':'local_csv','skills':skills,'tutoring_policy':'kr_errata'}},
                'sealed_csv_receipt':deepcopy(row)}
    rows=[r['static_acquisition'] for _,r,active in A._static_records(actor)
          if active and r['static_acquisition']['feature_id']==feature]
    if not rows:return None
    if len(rows)!=1:raise ValueError('one actual Mentor acquisition receipt required: '+feature)
    return rows[0]


def acquisition_snapshot(engine,actor,feature,selection=None):
    import skill_modifiers as S
    selection={'source':'core'} if selection is None else deepcopy(selection)
    allowed={'source','skills','tutoring_policy'} if feature==CLASS else {'source'}
    if type(selection)is not dict or set(selection)!=allowed:
        raise ValueError('exact source-specific Mentor acquisition selection required')
    proof=source(engine.r,feature,selection['source'])
    base=None if feature==CLASS else acquired(actor,CLASS)
    skills=selection.get('skills',None if base is None else base['snapshot']['skills'])
    if type(skills)is not list or len(skills)!=2 or len(set(skills))!=2 or any(x not in SKILLS for x in skills):
        raise ValueError('two distinct fixed Mentor skills required')
    ranks=[S.rank(engine.r,actor,x)[2] for x in skills]
    parents=[] if feature==CLASS else [MOVE_TUTOR if feature in (EGG_TUTOR,LIFELONG) else CLASS]
    parent_rows={uid:(acquired(actor,uid) or {}).get('request_id') for uid in parents}
    if feature==CLASS and selection['tutoring_policy'] not in ('core','official_sep2015','kr_errata'):
        raise ValueError('selected Core, actual official Sep2015 or KR tutoring policy required')
    result={'skills':list(skills),'ranks':ranks,'parents':parent_rows,'source':proof,'selection':selection}
    return result


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or set(snapshot)!={'skills','ranks','parents','source','selection'}:
        raise ValueError('exact Mentor acquisition evidence required')
    if snapshot['source']!=source(actor.r,feature,snapshot['source']['variant']):
        raise ValueError('Mentor acquisition source changed')
    ranks=snapshot['ranks'];skills=snapshot['skills']
    if len(skills)!=2 or len(set(skills))!=2 or any(x not in SKILLS for x in skills) or len(ranks)!=2:
        raise ValueError('fixed two-skill Mentor acquisition evidence required')
    parents=[] if feature==CLASS else [MOVE_TUTOR if feature in (EGG_TUTOR,LIFELONG) else CLASS]
    if set(snapshot['parents'])!=set(parents):raise ValueError('exact Mentor parent acquisition evidence required')
    selection=snapshot['selection']
    expected={'source','skills','tutoring_policy'} if feature==CLASS else {'source'}
    if type(selection)is not dict or set(selection)!=expected or selection['source']!=snapshot['source']['variant']:
        raise ValueError('Mentor source and immutable selection differ')
    if any(type(x)is not int or not 1<=x<=6 for x in ranks):raise ValueError('ordinary acquisition skill ranks required')
    if feature==CLASS:
        if selection['skills']!=skills or selection['tutoring_policy'] not in ('core','official_sep2015','kr_errata'):
            raise ValueError('exact fixed Mentor skills and tutoring source required')
    else:
        import trainer_feature_acquisition as A,mentor_csv as CSV_MENTOR
        records=[row['static_acquisition'] for _,row,_ in A._static_records(actor)]
        for parent,request in snapshot['parents'].items():
            found=[row for row in records if row['feature_id']==parent and row['request_id']==request]
            if parent==CLASS and CSV_MENTOR.has_receipt(actor):
                found.append(acquired(actor,CLASS))
            if not any(row['snapshot']['skills']==skills for row in found):
                raise ValueError('Mentor parent receipt and fixed skills differ')
    threshold=5 if feature==MOVE_TUTOR else 6 if feature==LIFELONG else 0
    checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','Mentor features require an actual Trainer'),
            Q.check('two_novice','prerequisite',feature!=CLASS or all(type(x)is int and 3<=x<=6 for x in ranks),'both fixed Mentor skills must be ordinary Novice when acquiring the Class'),
            Q.check('parents','prerequisite',all(snapshot['parents'].values()),'actual acquired parent Mentor feature required'),
            Q.check('selected_rank','prerequisite',max(ranks)>=threshold,'one selected Mentor skill must meet the printed ordinary rank')]
    return Q.require(feature,actor.entity_id,'acquisition',checks)


def on_acquired(engine,actor,feature,record):
    if feature==CLASS:
        if 'mentor_skills' in actor.spec:raise ValueError('Mentor acquisition cannot replace fixed skills')
        actor.spec['mentor_skills']=list(record['snapshot']['skills'])
        actor.spec['mentor_skill_selection']={'source':CLASS,'request_id':record['request_id']}
    if feature in (GUIDANCE,LIFELONG):
        __import__('move_state').register_passive_feature(engine,actor,feature)


def acquire(engine,actor,feature=CLASS,*,request_id,skills=None,variant='core',tutoring_policy='core'):
    import trainer_feature_acquisition as A
    if feature not in FEATURES:raise ValueError('reviewed Mentor feature required')
    if feature==CLASS and variant=='local_csv':
        if tutoring_policy!='kr_errata':raise ValueError('existing CSV104 acquisition retains its exact selected teaching policy')
        import mentor_csv as CSV_MENTOR
        return CSV_MENTOR.acquire(engine,actor,acquisition_request_id=request_id,skills=skills,
                                 lifecycle_policy=deepcopy(A.LIFECYCLE_UNRESOLVED))
    selection={'source':variant}
    if feature==CLASS:selection.update(skills=list(skills) if type(skills)in (list,tuple) else skills,tutoring_policy=tutoring_policy)
    return A.acquire_static(engine,actor,feature,acquisition_request_id=request_id,selection=selection)


def _require(actor,feature):
    row=acquired(actor,feature)
    if row is None:raise ValueError('actual acquired Mentor feature required: '+feature)
    return row


def _participants(engine,actor,target):
    import pokemon_activities as P,world_entities as W
    W.require_actors(engine,actor,target);P._trainer(actor);P._pokemon(target);P._outside(engine)
    if actor.spec.get('frequency_state',{}).get('day',0)!=target.spec.get('frequency_state',{}).get('day',0):
        raise ValueError('Mentor calendars must agree')


def _extended(engine,actor,target,source_id,seconds,context):
    import common_checks as C,turn,activity_jobs as JOBS
    C.integer(seconds,'GM-established Extended duration',1)
    if not turn.spend(engine,actor,'extended',source_id):raise ValueError('actual Extended action permission required')
    JOBS.run_fixed(engine,actor,(target,),seconds=seconds,source=source_id,context=context)


def expand(engine,actor,target,*,request_id,seconds,reason,source_id=EXPAND):
    import state_grants as G,resolution_transaction as TX
    if source_id not in (EXPAND,EXPAND_CSV):raise ValueError('exact Expand Horizons input source required')
    intent={'teacher':actor.entity_id,'target':target.entity_id,'seconds':seconds,'reason':reason}
    if source_id==EXPAND_CSV:intent['input_source']=source_id
    def apply(e,a,p):
        _participants(e,a,p);_require(a,EXPAND)
        admission=None
        if source_id==EXPAND_CSV:
            _require(a,CLASS)
            admission=e.r.select_source_definition(EXPAND_CSV)
        prior=TX.replay_result(p.spec.get('mentor_expansion_requests',{}),request_id,intent)
        if prior is not None:return prior['result']
        if p.spec.get('trainer_id')!=a.entity_id:raise ValueError('Expand Horizons requires your own Pokemon')
        if p.spec.get('mentor_expansion_history'):raise ValueError('Expand Horizons is once per Pokemon lifetime')
        import pokemon_teaching as T
        balance=T._balance(p.spec)
        if type(reason)is not str or not reason.strip():raise ValueError('actual Mentor application reason required')
        _extended(e,a,p,EXPAND,seconds,{'request_id':request_id})
        result={'source':EXPAND,'teacher_id':a.entity_id,'target_id':p.entity_id,'points':3,'before':balance,'after':T._balance(p.spec)+3}
        if admission is not None:result.update(input_source=admission,point_cost=0)
        p.spec['tutor_points']=result['after']
        p.spec.setdefault('mentor_expansion_history',[]).append(dict(result,request_id=request_id,at=e.elapsed_seconds))
        p.spec.setdefault('mentor_expansion_requests',{})[request_id]={'intent':deepcopy(intent),'result':deepcopy(result)}
        return result
    return G.transition(engine,actor,apply,participants=(target,))


def _changing(e,a,p,request,admission,reason,*,nature,investment=None,hp_policy='preserve_fraction'):
    import nature_state as N,growth_stats as G,pokemon_teaching as T
    old=N.describe(e.r,p.spec.get('nature'));new=N.describe(e.r,nature)
    if old is None or new is None:raise ValueError('actual current and new mechanical nature required')
    if old['catalog_name']==new['catalog_name']:raise ValueError('Changing Viewpoints requires a different nature')
    if admission['variant']!='class_data' and old['up_stat']!=new['up_stat'] and old['down_stat']!=new['down_stat']:
        raise ValueError('Changing Viewpoints requires the same raised or lowered stat')
    cost=0 if admission['variant']=='class_data' else 1
    T._debit_points(p.spec,cost)
    result=G.commit_nature(e,a,p,nature,investment=investment,source=LESSONS,reason=reason,
                          request_id='mentor-nature/'+request,ap_cost=0,hp_policy=hp_policy)
    return {'point_cost':cost,'nature_change':result}


def _empowered(e,a,p,request,admission,reason,*,edges,allocation=None):
    import pokemon_teaching as T,pokemon_skill_edges as SK,pokemon_capability_edges as CAP
    import grant_payments as PAY
    if p.spec.get('mentor_empowered_history'):raise ValueError('Empowered Development is once per Pokemon lifetime')
    if type(edges)is not list or len(edges)!=3:raise ValueError('three explicit Poke Edge choices required')
    if T._balance(p.spec)<1:raise ValueError('Empowered Development costs one total Tutor Point')
    children=[];grants=[]
    for index,choice in enumerate(edges):
        if type(choice)is not dict or set(choice)!={'edge','choice'}:raise ValueError('exact selected edge and choice required')
        source_id='mentor-empowered/'+request+'/'+str(index)
        edge=choice['edge'];value=choice['choice']
        if edge in (SK.SOURCE,'Skill Improvement','스킬 향상'):
            row=SK.lesson_acquire(e,a,p,value,source_id)
        elif edge in CAP.ALIASES:
            row=CAP.lesson_acquire(e,a,p,edge,value,source_id)
        else:raise ValueError('Empowered Development allows only the three printed Poke Edges')
        children.append(row)
        grants.append({'source_id':source_id,'field':'native_poke_edge','value':source_id})
    payment_id='mentor-empowered/'+request
    for row in children:row['payment_id']=payment_id
    p.spec.setdefault('mentor_empowered_history',[]).append({'request_id':request,'teacher_id':a.entity_id,
        'children':[r['mentor_source_id'] for r in children],'payment_id':payment_id,'source':admission['source'],'paid':1})
    payment=PAY.acquire(e,p,payment_id,grants,1,rule_id=LESSONS,reason=reason,allocation=allocation)
    SK.validate(e.r,p.spec);CAP.validate(e.r,p.spec)
    return {'point_cost':1,'edges':deepcopy(children),'payment':payment}


def native_effect_id(row):
    import resolution_transaction as TX
    return row.get('mentor_source_id') or 'native-poke-edge/'+TX.request_fingerprint({k:v for k,v in row.items() if k not in ('status','refund')})


def _corrective(e,a,p,request,admission,reason,*,effect_id,allocations=None):
    import grant_payments as PAY,pokemon_skill_edges as SK,pokemon_capability_edges as CAP
    whole=[row for row in p.spec.get('mentor_empowered_history',[]) if row['payment_id']==effect_id]
    if whole:
        ids=whole[0]['children'];rows=[row for row in p.spec.get('learned_poke_edges',[]) if row.get('mentor_source_id') in ids and row['status']=='active']
        if len(rows)!=3:raise ValueError('whole Empowered effect must still contain all three actual contributions')
        plans=PAY.quote(p,ids,allocations);amount=PAY.settle_sources(e,p,ids,plans,reason)
        for row in rows:
            if row['source']==SK.SOURCE:
                rank,flat=SK.skill_pool(e.r,p.spec,row['skill']);SK.set_pool(e.r,p.spec,row['skill'],rank-1,flat)
            row.update(status='refunded',refund={'source':SK.SOURCE if row['source']==SK.SOURCE else 'input/ch05-pokemon.md:274',
                       'points':0,'reason':reason,'corrective_learning':admission['source'],'group_refund':effect_id})
        return {'point_cost':0,'effect_id':effect_id,'refunded_points':amount,'removed_children':list(ids)}
    chosen=[row for row in p.spec.get('learned_poke_edges',[]) if row.get('status','active')=='active' and native_effect_id(row)==effect_id]
    if chosen:
        if len(chosen)!=1:raise ValueError('one actual invested Poke Edge effect required')
        row=chosen[0]
        import growth_stats as GS,pokemon_stat_edges as ST,underdog_edges as U,mixed_sweeper as MIXED,state_grants as G
        source_id=row['source']
        if source_id!=MIXED.SOURCE and e.r._selected_rule(source_id)!=source_id:raise ValueError('selected native Poke Edge source must be resolved')
        stat_effect=source_id in (ST.ATTACK_CONFLICT,*U.SOURCES,MIXED.SOURCE)
        current=GS.source_permanent(p) if stat_effect else None
        original=deepcopy(row)
        if row.get('payment_id'):
            plans=PAY.quote(p,[effect_id],allocations)
            amount=PAY.settle_sources(e,p,[effect_id],plans,reason)
        else:
            amount=row.get('point_cost')
            if type(amount)is not int or amount<1:raise ValueError('actual positive Tutor Point payment required')
            p.spec['tutor_points']+=amount
        if row['source']==SK.SOURCE:
            rank,flat=SK.skill_pool(e.r,p.spec,row['skill']);SK.set_pool(e.r,p.spec,row['skill'],rank-1,flat)
        if row.get('grant_source'):G._revoke_sources(p,[row['grant_source']],e)
        row.update(status='refunded',refund={'source':SK.SOURCE if row['source']==SK.SOURCE else source_id if source_id=='poke_edge/약골의-수업' else 'input/ch05-pokemon.md:274',
                    'points':amount,'reason':reason,'corrective_learning':admission['source']})
        if source_id==ST.ATTACK_CONFLICT:p.spec['learned_poke_edges'].remove(row)
        if stat_effect:GS.migrate_sources(p,current,source=admission['source'],reason=reason,kind='corrective_learning')
        p.spec.setdefault('mentor_corrective_history',[]).append({'request_id':request,'effect_id':effect_id,
            'removed_native_record':original,'refunded_points':amount,'teacher_id':a.entity_id,'source':admission['source']})
        return {'point_cost':0,'effect_id':effect_id,'refunded_points':amount}
    owned=p.spec.get('state_grants',{}).get('sources',{}).get(effect_id)
    if owned is None:raise ValueError('actual active TP-paid effect identity required')
    if not owned.get('payment_id'):raise ValueError('effect has no actual group payment receipt')
    if admission['variant']!='class_data' and owned.get('kind')!='feature':raise ValueError('Core Corrective Learning removes a Poke Edge or Feature effect')
    plans=PAY.quote(p,[effect_id],allocations)
    if not plans or sum(x['amount'] for x in plans)<1:raise ValueError('effect has no actual positive refundable Tutor Point payment')
    amount=PAY.settle_sources(e,p,[effect_id],plans,reason)
    return {'point_cost':0,'effect_id':effect_id,'refunded_points':amount}


def _versatile(e,a,p,request,admission,reason,*,old_ability,new_ability):
    import ability_transitions as A,state_grants as G,pokemon_teaching as T
    from builder import species_lookup
    old=A.ability_id(e.r,old_ability);new=A.ability_id(e.r,new_ability)
    baseline=[A.ability_id(e.r,x) for x in p.spec.get('abilities',[])]
    if old not in baseline or old==new or new in baseline:raise ValueError('two different actual permanent ability identities required')
    forbidden={uid for uid,unit in e.r.selection.units.items() if uid.startswith('ability/') and
               (unit.get('name') in ("Serpent's Mark",'Color Theory','뱀무늬','색채이론') or uid.split('/',1)[1] in ('뱀무늬','색채이론'))}
    if old in forbidden or new in forbidden:raise ValueError('Versatile Teachings cannot reroll ability properties')
    sp=species_lookup(e.r,p.spec['species'])
    import growth_milestones as GM
    basic={A.ability_id(e.r,x) for x in GM.natural_abilities(e.r,p.spec,pools=('기본 특성',))}
    advanced={A.ability_id(e.r,x) for x in GM.natural_abilities(e.r,p.spec,pools=('숨겨진 특성',))}
    hidden={A.ability_id(e.r,x) for x in GM.natural_abilities(e.r,p.spec,pools=('대단한 특성',))}
    if admission['variant']=='class_data':
        pools_allowed={'기본 특성'}
        for slot in e.r.mech('pokemon/level-up')['ability_slots']:
            if slot['level']<=p.level:pools_allowed.update(slot['pool'])
        allowed=basic|(advanced if '숨겨진 특성' in pools_allowed else set())|(hidden if '대단한 특성' in pools_allowed else set())
        if new not in allowed or not (set(baseline)-{old}|{new})&basic:raise ValueError('CSV Versatile needs an eligible species ability and retains a Basic ability')
    elif old in basic:
        if new not in basic:raise ValueError('Basic ability may change only to another species Basic ability')
    elif old in advanced:
        if new not in basic|advanced:raise ValueError('Advanced ability may change only to species Basic or Advanced')
    else:raise ValueError('Core Versatile does not exchange Hidden or external abilities')
    free=admission['variant']=='class_data' or admission['variant']=='local_csv' and p.spec.get('trainer_id')==a.entity_id
    cost=0 if free else 1;T._debit_points(p.spec,cost)
    permanent=[A.label(e.r,new) if A.ability_id(e.r,x)==old else x for x in p.spec.get('abilities',[])]
    G.set_baseline(p,'abilities',permanent);G.reconcile(e,p)
    result={'point_cost':cost,'old_ability':old,'new_ability':new,'source':admission['source'],'teacher_id':a.entity_id}
    p.spec.setdefault('mentor_ability_history',[]).append(dict(deepcopy(result),request_id=request,species=sp['id'],level=p.level))
    return result


def validate_edge_origin(rules,row):
    if (row.get('training_source')!=LESSONS or row.get('point_cost')!=0 or
            type(row.get('mentor_source_id'))is not str or not row['mentor_source_id'].startswith('mentor-empowered/') or
            type(row.get('trainer_id'))is not str or type(row.get('acquired_level'))is not int or row['acquired_level']<1):
        raise ValueError('actual lesson-owned native Poke Edge origin required')
    contract(rules)


def refund_edge_spec(rules,spec,row,reason):
    """Settle the same native group on a staged permanent skill change."""
    from types import SimpleNamespace
    import grant_payments as PAY
    from acquisition_ledger import AcquisitionLedger
    actor=SimpleNamespace(spec=spec);identity=row['mentor_source_id']
    plans=PAY.quote(actor,[identity])
    # A partial debit remains pending until the original explicit allocation is known.
    amount=sum(plan['amount'] for plan in plans)
    spec['state_grants']['sources'].pop(identity)
    AcquisitionLedger(actor).commit_refunds(plans,reason)
    spec['tutor_points']+=amount
    return amount


def teaching_policy(actor):
    row=acquired(actor,CLASS)
    return 'kr_errata' if row is None else row['snapshot']['selection']['tutoring_policy']


def teaching_variant(actor,feature):
    row=acquired(actor,feature)
    return None if row is None else row['snapshot']['source']['variant']


def validate_teaching_evidence(rules,record):
    import trainer_feature_acquisition as A
    row=record['mentor_acquisition_evidence'];payload={k:v for k,v in row.items() if k!='integrity'}
    feature=record['source']
    if (row.get('integrity')!=A._digest('trainer-feature/static-acquisition/v1',payload) or
            row.get('feature_id')!=feature or row.get('actor_id')!=record.get('teacher_id') or
            row.get('source')!=A._static_source(rules,feature) or
            row['snapshot']['source']!=source(rules,feature,row['snapshot']['source']['variant'])):
        raise ValueError('actual historical Mentor teaching acquisition changed')
    if feature==CLASS and row['snapshot']['skills']!=record.get('mentor_skills'):
        raise ValueError('taught Mentor move differs from fixed acquired skills')


def validate_actor(actor):
    """Validate feature state during native transitions, GM and data-only restore."""
    import trainer_feature_acquisition as A,grant_payments as PAY
    rows=[r['static_acquisition'] for _,r,active in A._static_records(actor)
          if r['static_acquisition']['feature_id']==CLASS]
    if rows:
        skills=rows[0]['snapshot']['skills']
        if actor.spec.get('mentor_skills')!=skills or actor.spec.get('mentor_skill_selection')!={'source':CLASS,'request_id':rows[0]['request_id']}:
            raise ValueError('Mentor immutable acquired skill projection changed')
    history=actor.spec.get('mentor_expansion_history',[])
    if type(history)is not list or len(history)>1:raise ValueError('Expand Horizons lifetime history changed')
    for row in history:
        if row.get('target_id')!=actor.entity_id or row.get('points')!=3 or row.get('after')!=row.get('before',-4)+3:
            raise ValueError('actual Expand Horizons +3 receipt required')
        receipt=actor.spec.get('mentor_expansion_requests',{}).get(row.get('request_id'),{})
        if receipt.get('result')!={k:v for k,v in row.items() if k not in ('request_id','at')}:
            raise ValueError('Expand Horizons request/history mismatch')
    empowered=actor.spec.get('mentor_empowered_history',[])
    if type(empowered)is not list or len(empowered)>1:raise ValueError('Empowered lifetime history changed')
    for row in empowered:
        payment=actor.spec.get('state_grants',{}).get('payments',{}).get(row.get('payment_id'))
        children=row.get('children')
        if payment is None or row.get('paid')!=1 or payment['paid']!=1 or payment['children']!=children or len(children)!=3:
            raise ValueError('Empowered requires one actual payment and three native children')
        edges=[r for r in actor.spec.get('learned_poke_edges',[]) if r.get('mentor_source_id') in children]
        if len(edges)!=3 or len({r['mentor_source_id'] for r in edges})!=3:
            raise ValueError('Empowered actual native contributions changed')
        for edge in edges:
            validate_edge_origin(actor.r,edge)
            if edge.get('payment_id')!=row['payment_id'] or edge.get('trainer_id')!=row.get('teacher_id'):
                raise ValueError('Empowered payment/provider provenance changed')
    if empowered:PAY.validate(actor)
    orphan=[row for row in actor.spec.get('learned_poke_edges',[]) if row.get('mentor_source_id') and
            not any(row['mentor_source_id'] in h['children'] for h in empowered)]
    if orphan:raise ValueError('native lesson Poke Edge has no whole-effect history')
    validate_egg_list(actor.r,actor.spec)


CSV_EGG_POLICY='authored/mentor/feats-R109-individual-list'


def egg_list_source(rules):
    definition={'id':CSV_EGG_POLICY,'title':'CSV109 individual EggList application policy',
        'source':{'file':'input/db/feats.csv','sha256':contract(rules)['source_hashes']['input/db/feats.csv']},
        'locator':{'record':109},'tags':[],
        'rationale':'Application-authored identity for the exact CSV109 row; candidate domain and individual list interpretation still require an explicit scoped source-conflict decision.'}
    if getattr(rules,'_authored_policy_sources',{}).get(CSV_EGG_POLICY)!=definition:
        rules.register_source_policy_definitions([definition])
    return definition


def _resolve_egg_policy(rules,document,context,decisions):
    definition=egg_list_source(rules)
    prepared=rules.resolve_source_policy(document,context=context,decisions=decisions)
    if prepared['selected_id']!=CSV_EGG_POLICY or prepared['source']!=definition['source'] or prepared.get('authored_source')!=definition:
        raise ValueError('exact registered CSV109 application source policy required')
    return prepared


def egg_list_policy(engine,actor,target,document,*,context=None,decisions=None):
    import world_entities as W
    W.require_actors(engine,actor,target)
    row=_require(actor,EGG_TUTOR)
    if row['snapshot']['source']['variant']!='local_csv':raise ValueError('CSV109 acquisition required for EggList edits')
    prepared=_resolve_egg_policy(engine.r,document,context,decisions)
    if prepared['status']!='PolicyValuesReady':return prepared
    values=prepared['values']
    if type(values)is not dict or set(values)!={'target_id','scope','allowed_egg_moves'} or values['target_id']!=target.entity_id:
        raise ValueError('EggList policy must bind the actual individual and exact candidate domain')
    if values['scope'] not in ('individual_egg_list','individual_inheritance_list'):
        raise ValueError('explicit individual EggList or individual inheritance scope required')
    if not any(row.get('decision_kind')=='source_conflict' and row.get('scope')==prepared['decision_scope'] for row in prepared['decision_evidence']):
        raise ValueError('unresolved CSV109 interpretation requires its explicit scoped source-conflict decision')
    allowed=values['allowed_egg_moves']
    if type(allowed)is not list or not allowed or len(set(allowed))!=len(allowed) or any(engine.r.move_id(mid)!=mid or mid in engine.r.excluded_moves for mid in allowed):
        raise ValueError('explicit distinct selected allowed Egg Move identities required')
    return prepared


def individual_egg_list(rules,spec):
    from builder import species_lookup
    validate_egg_list(rules,spec)
    if 'mentor_egg_list' in spec:return list(spec['mentor_egg_list'])
    species=species_lookup(rules,spec['species'])
    return list(dict.fromkeys(rules.move_id(x) for x in rules.learnsets.get(species['name'],{}).get('egg',[])))


def individual_egg_evidence(rules,spec,mid,request_id=None):
    validate_egg_list(rules,spec)
    rows=[row for row in spec.get('mentor_egg_list_history',[]) if row['scope']=='individual_egg_list' and
          mid in row['after'] and (request_id is None or row['request_id']==request_id)]
    if not rows:raise ValueError('actual individual EggList candidate receipt required')
    return rows[-1]


def validate_individual_egg_event(rules,spec,mid,event):
    from builder import species_lookup
    species_lookup(rules,event['species_id'])
    row=individual_egg_evidence(rules,spec,mid,event.get('egg_list_request_id'))
    if event.get('egg_list_request_id')!=row['request_id'] or event['kind']!='egg' or event.get('required_level') is not None:
        raise ValueError('historical individual natural Egg Move proof changed')


def edit_egg_list(engine,actor,target,move,*,document,request_id,seconds,reason,replace=None,context=None,decisions=None):
    import state_grants as G,resolution_transaction as TX,frequency as F
    intent={'teacher':actor.entity_id,'target':target.entity_id,'move':move,'replace':replace,
            'document':deepcopy(document),'context':deepcopy(context),'decisions':deepcopy(decisions),'seconds':seconds,'reason':reason}
    def apply(e,a,p):
        prior=TX.replay_result(p.spec.get('mentor_egg_list_requests',{}),request_id,intent)
        if prior is not None:return prior['result']
        _participants(e,a,p);prepared=egg_list_policy(e,a,p,document,context=context,decisions=decisions)
        if prepared['status']!='PolicyValuesReady':raise ValueError('CSV109 candidate/scope policy pending: explicit scoped decision required')
        if type(reason)is not str or not reason.strip():raise ValueError('actual EggList application reason required')
        values=prepared['values'];mid=e.r.move_id(move);old=None if replace is None else e.r.move_id(replace)
        if mid not in values['allowed_egg_moves']:raise ValueError('selected Egg Move is outside the resolved individual candidate policy')
        scope=values['scope'];field='mentor_egg_list' if scope=='individual_egg_list' else 'inheritance_moves'
        before=individual_egg_list(e.r,p.spec) if field=='mentor_egg_list' else list(p.spec.get(field,[]))
        if mid in before or replace is not None and old not in before:raise ValueError('add a new Egg Move or replace one actual individual list entry')
        if not F.activation_allowed(a,EGG_TUTOR,'하루x2',engine=e):raise ValueError('CSV109 daily frequency exhausted')
        after=[mid if x==old else x for x in before] if old is not None else [*before,mid]
        _extended(e,a,p,CSV[EGG_TUTOR],seconds,{'request_id':request_id,'scope':scope})
        F.consume_activation(a,EGG_TUTOR,'하루x2',engine=e)
        p.spec[field]=after
        result={'source':CSV[EGG_TUTOR],'target_id':p.entity_id,'scope':scope,'field':field,'before':before,'after':list(after),
                'move_id':mid,'replaced':old,'point_cost':0,'policy':deepcopy(prepared),'teacher_id':a.entity_id}
        p.spec.setdefault('mentor_egg_list_history',[]).append(dict(deepcopy(result),request_id=request_id,
            document=deepcopy(document),context=deepcopy(context),decisions=deepcopy(decisions)))
        p.spec.setdefault('mentor_egg_list_requests',{})[request_id]={'intent':deepcopy(intent),'result':deepcopy(result)}
        return result
    return G.transition(engine,actor,apply,participants=(target,))


def validate_egg_list(rules,spec):
    rows=spec.get('mentor_egg_list_history',[])
    if type(rows)is not list:raise ValueError('individual EggList history required')
    latest={}
    for row in rows:
        prepared=_resolve_egg_policy(rules,row['document'],row['context'],row['decisions'])
        if prepared!=row['policy'] or prepared['status']!='PolicyValuesReady':
            raise ValueError('historical EggList source policy changed')
        values=prepared['values'];field=row['field']
        if values['target_id']!=spec['id'] or row['target_id']!=spec['id'] or row['move_id'] not in values['allowed_egg_moves'] or row['point_cost']!=0 or row['scope']!=values['scope']:
            raise ValueError('historical EggList target, candidate or cost changed')
        if field!=('mentor_egg_list' if row['scope']=='individual_egg_list' else 'inheritance_moves'):
            raise ValueError('EggList scope and actual field differ')
        if field in latest and row['before']!=latest[field]:raise ValueError('EggList individual edit history is discontinuous')
        old=row['replaced'];mid=row['move_id'];before=row['before']
        expected=[mid if x==old else x for x in before] if old is not None else [*before,mid]
        if mid in before or old is not None and old not in before or row['after']!=expected:raise ValueError('actual EggList add/replace receipt changed')
        receipt=spec.get('mentor_egg_list_requests',{}).get(row['request_id'])
        if receipt is None or receipt['result']!={k:v for k,v in row.items() if k not in ('request_id','document','context','decisions')}:
            raise ValueError('EggList request and permanent history differ')
        latest[field]=row['after']
    for field,values in latest.items():
        if spec.get(field)!=values:raise ValueError('individual EggList projection changed')
    if 'mentor_egg_list' in spec and 'mentor_egg_list' not in latest:raise ValueError('individual EggList has no actual scoped edit receipt')


def _lesson_admission(engine,actor,target,lesson,variant):
    import skill_modifiers as S,frequency as F
    _participants(engine,actor,target);base=_require(actor,CLASS)
    if lesson not in LESSON_SKILLS:raise ValueError('one of the four actual Mentor lessons required')
    if variant=='class_data':
        contract(engine.r);source_id=TECHNIQUES[lesson];frequency='하루x3'
    else:
        row=_require(actor,LESSONS);actual=row['snapshot']['source']['variant']
        if variant is not None and variant!=actual:raise ValueError('lesson source differs from actual acquisition')
        variant=actual;source_id=LESSONS;frequency='하루x2' if variant=='local_translation' else '하루x3'
    skill=LESSON_SKILLS[lesson];widened=False;expand_row=acquired(actor,EXPAND)
    if expand_row and expand_row['snapshot']['source']['variant']=='local_csv' and acquired(actor,LESSONS):
        widened=all(S.rank(engine.r,actor,x)[2]>=3 for x in SKILLS)
    if skill not in base['snapshot']['skills'] and not widened:raise ValueError('lesson requires its actually selected Mentor skill')
    if not F.activation_allowed(actor,source_id,frequency,engine=engine):raise ValueError('Mentor lesson daily frequency exhausted')
    return {'source':source_id,'variant':variant,'frequency':frequency,'all_lesson_permission':widened}


def lesson(engine,actor,target,name,*,request_id,seconds,reason,variant=None,**choices):
    import state_grants as G,resolution_transaction as TX,frequency as F
    intent={'teacher':actor.entity_id,'target':target.entity_id,'lesson':name,'seconds':seconds,
            'reason':reason,'variant':variant,'choices':deepcopy(choices)}
    def apply(e,a,p):
        prior=TX.replay_result(p.spec.get('mentor_lesson_requests',{}),request_id,intent)
        if prior is not None:return prior['result']
        admission=_lesson_admission(e,a,p,name,variant)
        if type(reason)is not str or not reason.strip():raise ValueError('actual Mentor lesson reason required')
        effect={'changing':_changing,'empowered':_empowered,'corrective':_corrective,'versatile':_versatile}[name]
        result=effect(e,a,p,request_id,admission,reason,**choices)
        _extended(e,a,p,admission['source'],seconds,{'lesson':name,'request_id':request_id})
        F.consume_activation(a,admission['source'],admission['frequency'],engine=e)
        result.update(lesson=name,admission=deepcopy(admission),seconds=seconds)
        p.spec.setdefault('mentor_lesson_requests',{})[request_id]={'intent':deepcopy(intent),'result':deepcopy(result)}
        return result
    return G.transition(engine,actor,apply,participants=(target,))
