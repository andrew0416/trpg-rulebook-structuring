"""Permanent capability investments, derived contributions and refunds.

Raw capabilities remain separate from each learned edge's contribution. The
minimum-level prerequisite controls the investment lifetime; acquisition choice
eligibility is not silently promoted to a new ongoing prerequisite.
"""
from copy import deepcopy
import state_fields as F
import physical_limits as LIMITS

TRAINING='poke_edge/재능-훈련'
MOBILITY='poke_edge/고급-이동'
RULES={TRAINING:{'choices':('power','high_jump','long_jump'),'amount':1},
       MOBILITY:{'choices':('land','sky','levitate','swim','burrow','teleport'),'amount':2}}
ALIASES={TRAINING:TRAINING,'재능 훈련':TRAINING,'Capability Training':TRAINING,
         MOBILITY:MOBILITY,'고급 이동':MOBILITY,'Advanced Mobility':MOBILITY}
CHOICES={'파워':'power','Power':'power','높이뛰기':'high_jump','High Jump':'high_jump',
         '멀리뛰기':'long_jump','Long Jump':'long_jump','육상':'land','Overland':'land',
         '비행':'sky','Sky':'sky','부유':'levitate','Levitate':'levitate','수영':'swim','Swim':'swim',
         '굴파기':'burrow','Burrow':'burrow','순간이동':'teleport','Teleport':'teleport'}


def records(spec):
    rows=spec.get('learned_poke_edges',[])
    if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('Poke Edge investments must be records')
    return [r for r in rows if r.get('source') in RULES]


def validate(rules,spec,*,allow_lost_prerequisite=False):
    validate_named(rules,spec)
    seen=set()
    for row in records(spec):
        import poke_edge_variants as VARIANTS
        VARIANTS.validate_receipt(rules,row,history=True,minimum_level=20)
        if spec.get('kind')!='pokemon':raise ValueError('capability Poke Edge requires an actual Pokemon')
        source=row['source']
        if rules._selected_rule(source)!=source:raise ValueError('selected capability Poke Edge needs its own source policy')
        if row.get('choice') not in RULES[source]['choices'] or row.get('effect_storage')!='derived':raise ValueError('explicit derived capability choice required')
        lesson=bool(row.get('mentor_source_id'))
        if lesson:__import__('mentor').validate_edge_origin(rules,row)
        F.integer(row.get('point_cost'),'capability investment',0 if lesson else 1,0 if lesson else 1)
        status=row.get('status')
        if status=='active':
            key=(source,row['choice'])
            if key in seen:raise ValueError('one active investment per capability and source')
            seen.add(key)
            if spec['level']<20 and not lesson and not allow_lost_prerequisite:raise ValueError('lost level20 prerequisite needs capability-edge refund')
        elif status=='refunded':
            refund=row.get('refund')
            if not isinstance(refund,dict) or refund.get('source')!='input/ch05-pokemon.md:274' or not refund.get('reason'):raise ValueError('refunded capability edge needs an actual receipt')
            F.integer(refund.get('points'),'refunded capability points',0 if lesson else 1,1)
        else:raise ValueError('explicit capability edge lifetime required')


def projection(rules,spec,values=None):
    """Use the common composition owner without merging base and investment state."""
    validate(rules,spec)
    grouped={}
    base={} if values is None else values
    for row in records(spec):
        if row['status']!='active':continue
        choice=row['choice'];source=row['source']
        # input/ch05-pokemon.md:352-355: Advanced Mobility increases one existing Movement
        # Capability. A mode whose composite value without this Edge is 0 (e.g. lost by
        # evolution) stays dormant and is not refunded; Capability Training values may be 0.
        if values is not None and source==MOBILITY and not base.get(choice,0)>0:continue
        grouped.setdefault(choice,[]).append({
            'id':source+':'+choice,
            'source':row.get('definition_origin',{}).get('rule_id',source),
            'value':RULES[source]['amount']})
    return {choice:LIMITS.add_sources(base.get(choice,0),rows)
            for choice,rows in grouped.items()}


def amounts(rules,spec):
    return {choice:row['value'] for choice,row in projection(rules,spec).items()}


def apply(actor,values):
    result=dict(values)
    for key,row in projection(actor.r,actor.spec,values).items():result[key]=row['value']
    return result


def bonus(actor,choice):return amounts(actor.r,actor.spec).get(choice,0)


def reconcile_spec(rules,spec,*,reason):
    """Pure candidate transition, called before a permanent level edit commits."""
    validate(rules,spec,allow_lost_prerequisite=True)
    ending=[row for row in records(spec) if row['status']=='active' and spec['level']<20 and not row.get('mentor_source_id')]
    if not ending:return []
    import acquisition_withdrawal as WITHDRAWAL
    WITHDRAWAL.refund_native_investments(spec,ending,source='input/ch05-pokemon.md:274',
        reason=reason,lost_prerequisite={'minimum_level':20,'actual_level':spec['level']})
    validate(rules,spec)
    return [{'source':r['source'],'choice':r['choice'],'points':1} for r in ending]


def decompose_current(actor,values):
    """GM current totals include active investments; stored values exclude them.

    An observed 0 (or absent) Movement Capability holds no dormant Advanced Mobility
    contribution; a positive observed mode must exceed it (its own value stays above 0).
    """
    result=deepcopy(values)
    for key,amount in amounts(actor.r,actor.spec).items():
        mobility=key in RULES[MOBILITY]['choices']
        if mobility and not result.get(key,0):continue
        if key not in result:raise ValueError('current capability observation must include its active investment: '+key)
        F.integer(result[key],key+' observed capability',amount+1 if mobility else amount)
        result[key]-=amount
    return result


def teach(e,owner,*,target,edge,capability,from_grooming=False,from_training=False,safe=None):
    import state_grants as G
    return G.transition(e,target,lambda se,st,so:_teach(se,so,st,edge,capability,from_grooming,from_training,safe),participants=(owner,))


def lesson_acquire(engine,teacher,pupil,edge,capability,source_id):
    """Native derived contribution with the printed lesson prerequisite waiver."""
    validate(engine.r,pupil.spec)
    source=ALIASES.get(edge);choice=CHOICES.get(capability,capability)
    if source not in RULES or choice not in RULES[source]['choices']:
        raise ValueError('choose one explicit eligible capability')
    if any(row['status']=='active' and row['source']==source and row['choice']==choice for row in records(pupil.spec)):
        raise ValueError('this capability already has that investment')
    if choice=='power':__import__('capability_actions').power(pupil)
    elif choice in ('high_jump','long_jump'):__import__('jump_actions').limits(pupil)
    elif __import__('movement_actions').capabilities(engine,pupil).get(choice,0)<=0:
        raise ValueError('actual existing selected movement capability required')
    row={'source':source,'status':'active','choice':choice,'point_cost':0,'effect_storage':'derived',
         'trainer_id':teacher.entity_id,'acquired_level':pupil.level,'training_source':'feat/수업',
         'completed_at':engine.elapsed_seconds,'mentor_source_id':source_id}
    pupil.spec.setdefault('learned_poke_edges',[]).append(row)
    return row


def _teach(e,owner,target,edge,capability,from_grooming,from_training,safe=None):
    import pokemon_teaching as T
    T._pokemon(e,owner,target)
    source=ALIASES.get(edge)
    if source is None:raise ValueError('reviewed capability Poke Edge required')
    T.source(e.r,source,T.POINTS);validate(e.r,target.spec)
    if target.level<20:raise ValueError('capability Poke Edge requires level20')
    choice=CHOICES.get(capability,capability) if isinstance(capability,str) else None
    if choice not in RULES[source]['choices']:raise ValueError('choose one explicit eligible capability')
    if any(r['status']=='active' and r['source']==source and r['choice']==choice for r in records(target.spec)):raise ValueError('this capability already has that investment')
    if T._balance(target.spec)<1:raise ValueError('capability Poke Edge costs one Tutor Point')
    if choice=='power':
        import capability_actions as C
        C.power(target)
    elif choice in ('high_jump','long_jump'):
        import jump_actions as J
        J.limits(target)
    else:
        import movement_actions as M
        values=M.capabilities(e,target)
        if values.get(choice,0)<=0:raise ValueError('actual existing selected movement capability required')
    application=source+':'+choice
    if T.credit_mode(from_grooming,from_training):T.training_credit(e,owner,target,application,from_training=from_training)
    else:T.edge_training_hour(e,owner,target,source,application,safe=safe)
    T._debit_points(target.spec,1)
    target.spec.setdefault('learned_poke_edges',[]).append({'source':source,'status':'active','choice':choice,
        'point_cost':1,'effect_storage':'derived','trainer_id':owner.entity_id,'acquired_level':target.level,
        'training_source':'edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274','completed_at':e.elapsed_seconds})
    if T.credit_mode(from_grooming,from_training):T.consume_credit(target,application,from_training=from_training)
    projection(e.r,target.spec)
    return {'activity':'teach_edge','edge':source,'capability':choice,'bonus':RULES[source]['amount'],
            'point_cost':1,'seconds':0 if (from_grooming or from_training) else 3600}


# Named capabilities share the existing investment receipt and withdrawal owner.
LANGUAGE='poke_edge/언어-학습'
MOUNT='poke_edge/탑승-훈련'
NAMED=(LANGUAGE,MOUNT)


def named_records(spec):
    rows=spec.get('learned_poke_edges',[])
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ValueError('Poke Edge investments must be records')
    return [row for row in rows if row.get('source') in NAMED]


def validate_named(rules,spec):
    seen=set()
    for row in named_records(spec):
        import poke_edge_variants as V
        V.validate_receipt(rules,row,history=row.get('source')==MOUNT)
        source=row['source']
        if spec.get('kind')!='pokemon' or rules._selected_rule(source)!=source:
            raise ValueError('selected named-capability Pokemon Edge required')
        cost=2 if source==LANGUAGE else 1
        F.integer(row.get('point_cost'),'named capability payment',cost,cost)
        if row.get('effect_storage')!='derived':raise ValueError('source-owned named capability contribution required')
        snapshot=row.get('qualification')
        if type(snapshot)is not dict or set(snapshot)!={'shiny','size','power'} or type(snapshot['shiny'])is not bool:
            raise ValueError('actual acquisition-time shiny/size/Power observations required')
        if source==LANGUAGE:
            F.integer(row.get('slot_cost'),'Language reserved Move slots',1,1)
            if not snapshot['shiny'] or row.get('training_source')!='pokemon/creation':
                raise ValueError('Language Edge requires actual shiny creation and one reserved Move slot')
        elif not mount_qualified(snapshot['size'],snapshot['power'],snapshot['shiny']):
            raise ValueError('Mount Training acquisition prerequisites were not met')
        if row.get('status')=='active':
            if source in seen:raise ValueError('one active named-capability Edge investment required')
            seen.add(source)
        elif row.get('status')=='refunded':
            refund=row.get('refund')
            if type(refund)is not dict or refund.get('source')!='input/ch05-pokemon.md:274' or not refund.get('reason') or refund.get('points')!=cost:
                raise ValueError('actual named capability prerequisite refund required')
        else:raise ValueError('explicit named capability investment lifetime required')


def mount_qualified(size,power,shiny):
    sizes={'소형':0,'Small':0,'중형':1,'Medium':1,'대형':2,'Large':2,'거대':3,'거대형':3,'Huge':3,
           '초거대':4,'초거대형':4,'Gigantic':4}
    tier=sizes.get(size)
    if tier is None:raise ValueError('actual sourced Pokemon size required for Mount Training')
    if type(shiny)is not bool:raise ValueError('actual shiny status must be boolean')
    if tier>3 or (shiny and tier>=2):return True
    F.integer(power,'actual Mount Training Power',1)
    return (tier==1 and shiny and power>=8) or (tier==2 and power>=8) or (tier==3 and power>=6)


def named_capabilities(actor,values):
    rows=named_records(actor.spec)
    if not rows:return values
    validate_named(actor.r,actor.spec)
    result=list(values)
    if any(row['source']==LANGUAGE and row['status']=='active' for row in rows):result.append('언어')
    if any(row['source']==MOUNT and row['status']=='active' for row in rows):
        import re
        mounted=[(value,re.fullmatch(r'(?:탑승|Mountable)\s*(\d+)',value,re.I)) for value in result]
        base=max((int(match.group(1)) for _,match in mounted if match),default=0)
        result=[value for value,match in mounted if not match]+['탑승 '+str(base+1)]
    return result


def slot_reservations(rules,spec):
    rows=named_records(spec)
    if not rows:return []
    validate_named(rules,spec)
    return [{'id':LANGUAGE,'source':LANGUAGE,'weights':{'total':1}} for row in rows
            if row['source']==LANGUAGE and row['status']=='active']


def creation_choices(rules,spec,choices):
    if choices is None:return
    if type(choices)is not list or any(type(choice)is not str for choice in choices) or len(choices)!=len(set(choices)):
        raise ValueError('distinct actual creation Poke Edge selections required')
    import poke_edge_variants as V,pokemon_teaching as T
    for choice in choices:
        definition=V.resolve(rules,choice)
        if definition is None or definition['policy']!=LANGUAGE:raise ValueError('only the shiny-creation Language Edge belongs to creation choices')
        if spec.get('shiny') is not True:raise ValueError('Language Edge can only be selected during shiny Pokemon creation')
        if named_records(spec):raise ValueError('fresh creation cannot replay existing named-capability investments')
        if T._balance(spec)<2:raise ValueError('Language Edge costs two actual Tutor Points')
        spec.setdefault('learned_poke_edges',[]).append({'source':LANGUAGE,'status':'active','point_cost':2,
            'effect_storage':'derived','slot_cost':1,'trainer_id':spec.get('trainer_id'),
            'acquired_level':spec['level'],'training_source':'pokemon/creation','completed_at':0,
            'qualification':{'shiny':True,'size':spec.get('size'),'power':None},
            'definition_origin':{'clause_id':definition['clause_id'],'rule_id':definition['rule_id'],'record':definition['record']}})
        T._debit_points(spec,2)
        __import__('move_state').validate_spec(rules,spec)


def _mount_power(actor):
    if actor.spec.get('size') in ('초거대','초거대형','Gigantic') or (actor.spec.get('shiny') is True and actor.spec.get('size') in ('대형','Large','거대','거대형','Huge')):
        return None
    return __import__('capability_actions').power(actor)


def teach_named(e,owner,target,definition,*,from_grooming=False,from_training=False,safe=None):
    import pokemon_teaching as T
    T._pokemon(e,owner,target);source=definition['policy']
    if source==LANGUAGE:raise ValueError('Language Edge can only be selected during actual shiny Pokemon creation')
    if source!=MOUNT:raise ValueError('reviewed named-capability Edge required')
    T.source(e.r,source,T.POINTS)
    validate_named(e.r,target.spec)
    if any(row['source']==source and row['status']=='active' for row in named_records(target.spec)):
        raise ValueError('Mount Training already acquired')
    shiny=target.spec.get('shiny',False);size=target.spec.get('size');power=_mount_power(target)
    if not mount_qualified(size,power,shiny):raise ValueError('Mount Training size/Power/shiny prerequisites are not met')
    if T._balance(target.spec)<1:raise ValueError('Mount Training costs one actual Tutor Point')
    if T.credit_mode(from_grooming,from_training):T.training_credit(e,owner,target,source,from_training=from_training)
    else:T.edge_training_hour(e,owner,target,source,source,safe=safe)
    T._debit_points(target.spec,1)
    target.spec.setdefault('learned_poke_edges',[]).append({'source':source,'status':'active','point_cost':1,
        'effect_storage':'derived','trainer_id':owner.entity_id,'acquired_level':target.level,
        'qualification':{'shiny':shiny,'size':size,'power':power},
        'training_source':'edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274','completed_at':e.elapsed_seconds})
    if T.credit_mode(from_grooming,from_training):T.consume_credit(target,source,from_training=from_training)
    return {'activity':'teach_edge','edge':source,'point_cost':1,'seconds':0 if (from_grooming or from_training) else 3600}


def reconcile_named(actor,*,reason):
    rows=[row for row in named_records(actor.spec) if row['source']==MOUNT and row['status']=='active']
    if not rows:return
    validate_named(actor.r,actor.spec);power=_mount_power(actor)
    if mount_qualified(actor.spec.get('size'),power,actor.spec.get('shiny',False)):return
    __import__('acquisition_withdrawal').refund_native_investments(actor.spec,rows,
        source='input/ch05-pokemon.md:274',reason=reason,
        lost_prerequisite={'size':actor.spec.get('size'),'power':power,'shiny':actor.spec.get('shiny',False)})
