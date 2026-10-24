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
