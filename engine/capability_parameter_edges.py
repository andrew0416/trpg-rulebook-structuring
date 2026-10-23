"""Source-declared capability parameters with shared native TP acquisition and loss."""
import state_fields as F,state_grants as G,skill_modifiers as S
import acquisition_qualification as Q,acquisition_withdrawal as W

SOURCES=('poke_edge/꼼꼼한-실','poke_edge/지진계','poke_edge/장거리-판독')


def records(actor,source):
    rows=actor.spec.get('learned_poke_edges',[])
    if type(rows)is not list or any(type(row)is not dict for row in rows):raise ValueError('actual Poke Edge receipts required')
    return [row for row in rows if row.get('source')==source]


def definition(rules,source):
    import poke_edge_variants as V
    row=V.resolve(rules,source)
    if source not in SOURCES or row is None or row['field']!='none' or row.get('native_kind')!='capability_parameters':
        raise ValueError('selected capability parameter Edge required')
    if type(row.get('parameters'))is not dict or not row['parameters'] or type(row.get('capabilities'))is not list or not row['capabilities']:
        raise ValueError('declared capability parameters and actual prerequisites required')
    return row


def owned(actor,spec):
    return bool({S.key(x) for x in spec['capabilities']} & {S.key(x) for x in G.effective_capabilities(actor)})


def _lost(actor,spec):return actor.level<spec['minimum_level'] or not owned(actor,spec)


def validate(actor,source=None,*,allow_lost=False):
    import poke_edge_variants as V
    for uid in SOURCES if source is None else (source,):
        rows=records(actor,uid)
        if not rows:continue
        spec=definition(actor.r,uid);active=0
        if actor.kind!='pokemon':raise ValueError('capability parameter Edge requires actual Pokemon')
        for row in rows:
            V.validate_receipt(actor.r,row)
            if row.get('definition_origin')!={k:spec[k] for k in ('clause_id','rule_id','record')}:raise ValueError('actual capability parameter Edge source receipt required')
            F.integer(row.get('point_cost'),'actual parameter Edge paid TP',spec['tutor_cost'],spec['tutor_cost'])
            F.integer(row.get('acquired_level'),'historical parameter Edge level',spec['minimum_level'],100)
            if type(row.get('trainer_id'))is not str or not row['trainer_id']:raise ValueError('actual historical teacher required')
            if row.get('status')=='active':
                active+=1
                if not allow_lost and _lost(actor,spec):raise ValueError('lost capability parameter Edge prerequisite requires refund')
            elif row.get('status')=='refunded':
                refund=row.get('refund',{})
                F.integer(refund.get('points'),'actual parameter Edge refund TP',spec['tutor_cost'],spec['tutor_cost'])
                if refund.get('source')!='input/ch05-pokemon.md:274' or not refund.get('reason'):raise ValueError('actual prerequisite loss refund required')
            else:raise ValueError('explicit capability parameter Edge lifetime required')
        if active>1:raise ValueError('one active receipt per capability parameter Edge permitted')


def parameters(actor,source):
    validate(actor,source)
    return definition(actor.r,source)['parameters'].copy() if any(row['status']=='active' for row in records(actor,source)) else {}


def reconcile(actor,*,reason,source=None):
    validate(actor,source,allow_lost=True)
    ending=[]
    for uid in SOURCES if source is None else (source,):
        rows=records(actor,uid)
        if rows:
            spec=definition(actor.r,uid)
            ending.extend(row for row in rows if row['status']=='active' and _lost(actor,spec))
    if not ending:return
    policy=W.policy({'cause':'prerequisite_loss','policies':{'prerequisite_loss':{'allowed':True,'refund_mode':'actual'}}})
    if policy['status']!='allowed' or policy['refund_mode']!='actual':raise ValueError('actual prerequisite-loss refund policy required')
    for row in ending:
        spec=definition(actor.r,row['source']);lost={}
        if actor.level<spec['minimum_level']:lost.update(minimum_level=spec['minimum_level'],actual_level=actor.level)
        if not owned(actor,spec):lost.update(capabilities=spec['capabilities'],owned=False)
        W.refund_native_investments(actor.spec,[row],source='input/ch05-pokemon.md:274',reason=reason,lost_prerequisite=lost)
    validate(actor,source)


def teach(engine,owner,target,spec,*,from_grooming=False,from_training=False,safe=None):
    import pokemon_teaching as T
    uid=spec['policy'];declared=definition(engine.r,uid)
    if spec!=declared:raise ValueError('actual source-selected parameter Edge declaration required')
    T._pokemon(engine,owner,target);T.source(engine.r,uid,T.POINTS);validate(target)
    cost=spec['tutor_cost']
    def qualify():
        return Q.require(uid,owner.entity_id,'acquisition',[
            Q.check('level','prerequisite',target.level>=spec['minimum_level'],'actual minimum level required'),
            Q.check('capability','prerequisite',owned(target,spec),'actual parameter Edge capability required'),
            Q.check('repeat','repeat',not any(row['status']=='active' for row in records(target,uid)),'parameter Edge already acquired'),
            Q.check('points','capacity',T._balance(target.spec)>=cost,'actual parameter Edge TP required')])
    qualify()
    credit=T.credit_mode(from_grooming,from_training)
    if credit:T.training_credit(engine,owner,target,uid,from_training=from_training)
    else:T.edge_training_hour(engine,owner,target,uid,uid,safe=safe)
    qualify()
    target.spec.setdefault('learned_poke_edges',[]).append({'source':uid,'status':'active','point_cost':cost,
        'trainer_id':owner.entity_id,'acquired_level':target.level,'completed_at':engine.elapsed_seconds,
        'training_source':'edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274',
        'definition_origin':{k:spec[k] for k in ('clause_id','rule_id','record')}})
    T._debit_points(target.spec,cost)
    if credit:T.consume_credit(target,uid,from_training=from_training)
    validate(target)
    return {'activity':'teach_edge','edge':uid,'point_cost':cost,**spec['parameters'],'seconds':0 if credit else 3600}
