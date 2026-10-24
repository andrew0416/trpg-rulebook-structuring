"""Source-declared capability parameters with shared native TP acquisition and loss."""
import state_fields as F,state_grants as G,skill_modifiers as S
import acquisition_qualification as Q,acquisition_withdrawal as W

SOURCES=('poke_edge/꼼꼼한-실','poke_edge/지진계','poke_edge/장거리-판독',
         'poke_edge/파동술','poke_edge/유혹적인-미끼','poke_edge/흔적-탐지')


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


def _provider_owned(engine,actor,spec):
    if not spec.get('trainer_capabilities'):return True
    import world_entities as W
    provider=W.actor_index(engine).get(actor.spec.get('trainer_id'))
    return provider is not None and provider.kind=='trainer' and owned(provider,{'capabilities':spec['trainer_capabilities']})


def _lost(actor,spec,engine=None):
    return actor.level<spec['minimum_level'] or not owned(actor,spec) or (engine is not None and not _provider_owned(engine,actor,spec))


def _grant_source(source):return 'native-poke-edge:'+source


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
                if spec.get('grant_capability'):
                    grant=actor.spec.get('state_grants',{}).get('sources',{}).get(_grant_source(uid),{})
                    if grant.get('rule_id')!=uid or grant.get('grants',{}).get('capabilities')!=[spec['grant_capability']]:raise ValueError('actual native Edge capability grant required')
            elif row.get('status')=='refunded':
                refund=row.get('refund',{})
                F.integer(refund.get('points'),'actual parameter Edge refund TP',spec['tutor_cost'],spec['tutor_cost'])
                if refund.get('source')!='input/ch05-pokemon.md:274' or not refund.get('reason'):raise ValueError('actual prerequisite loss refund required')
            else:raise ValueError('explicit capability parameter Edge lifetime required')
        if active>1:raise ValueError('one active receipt per capability parameter Edge permitted')


def parameters(actor,source):
    validate(actor,source)
    return definition(actor.r,source)['parameters'].copy() if any(row['status']=='active' for row in records(actor,source)) else {}


def reconcile(actor,*,reason,source=None,engine=None):
    validate(actor,source,allow_lost=True)
    ending=[]
    for uid in SOURCES if source is None else (source,):
        rows=records(actor,uid)
        if rows:
            spec=definition(actor.r,uid)
            ending.extend(row for row in rows if row['status']=='active' and _lost(actor,spec,engine))
    if not ending:return
    policy=W.policy({'cause':'prerequisite_loss','policies':{'prerequisite_loss':{'allowed':True,'refund_mode':'actual'}}})
    if policy['status']!='allowed' or policy['refund_mode']!='actual':raise ValueError('actual prerequisite-loss refund policy required')
    for row in ending:
        spec=definition(actor.r,row['source']);lost={}
        if actor.level<spec['minimum_level']:lost.update(minimum_level=spec['minimum_level'],actual_level=actor.level)
        if not owned(actor,spec):lost.update(capabilities=spec['capabilities'],owned=False)
        if engine is not None and not _provider_owned(engine,actor,spec):lost.update(trainer_capabilities=spec['trainer_capabilities'],owned=False)
        if spec.get('grant_capability'):G.revoke(actor,_grant_source(row['source']),engine=engine)
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
            Q.check('trainer_capability','prerequisite',_provider_owned(engine,target,spec),'actual trainer capability required'),
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
    if spec.get('grant_capability'):
        G.grant(target,'capabilities',spec['grant_capability'],_grant_source(uid),'poke_edge',
                owner_id=owner.entity_id,rule_id=uid,tutor_points=0)
    if credit:T.consume_credit(target,uid,from_training=from_training)
    validate(target)
    return {'activity':'teach_edge','edge':uid,'point_cost':cost,**spec['parameters'],'seconds':0 if credit else 3600}


def enticing_bonus(actor):
    source='poke_edge/유혹적인-미끼'
    if not parameters(actor,source):return 0
    return max(S.effective_rank(actor.r,actor,'육상'),S.effective_rank(actor.r,actor,'집중'))


def tracker_modifiers(rules,actor,skill,context):
    source='poke_edge/흔적-탐지'
    if not isinstance(context,dict) or context.get('purpose')!='capability/추적자':return ()
    if S.skill_id(rules.skill_policy,skill)!=S.skill_id(rules.skill_policy,'통찰'):raise ValueError('Tracker requires its actual Perception check')
    spec=definition(rules,source)
    if not owned(actor,spec):raise ValueError('actual Tracker capability required')
    if not parameters(actor,source):return ()
    return ((source,S.effective_rank(rules,actor,'집중'),'actual Tracker Perception check'),)
