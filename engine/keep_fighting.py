"""Book Keep Fighting replaces the native HP crossing before faint consequences."""
from copy import deepcopy
import acquired_features as A
import common_checks as C
import moment_of_action as M
import trainer_feature_acquisition as TFA

FEATURE='feat/끝까지-싸우자'
CLAUSE='input/ch04-trainer-classes.md:714-718'
KEY='keep_fighting_uses'
FAMILY=(M.CLASS,M.FEATURE,'feat/응원-단체','feat/영감을-주는-지원','feat/신나게-방해','feat/응원-문구')
QUOTA={'kind':'daily','uses':2}


def acquisition_snapshot(actor):
    import cheerleader as CH,skill_modifiers as SKILLS
    parents=[]
    for feature in FAMILY:
        row=CH.acquired(actor,feature)
        if row is not None:parents.append({'feature':feature,'request_id':row['request_id']})
    return {'features':parents,'charm':SKILLS.rank(actor.r,actor,'매력')[2]}


def qualification(actor,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!={'features','charm'}:
        raise ValueError('exact Keep Fighting acquisition observations required')
    C.integer(snapshot['charm'],'acquisition Charm rank',0)
    parents=snapshot['features']
    if type(parents) is not list or any(type(p) is not dict or set(p)!={'feature','request_id'} for p in parents):
        raise ValueError('actual Cheerleader acquisition identities required')
    ids=[p['feature'] for p in parents]
    if len(ids)!=len(set(ids)) or any(uid not in FAMILY for uid in ids):raise ValueError('distinct Cheerleader Features required')
    for parent in parents:
        if len([r for r in M.receipts(actor,parent['feature']) if r['request_id']==parent['request_id']])!=1:
            raise ValueError('historical actual Cheerleader acquisition required')
    return Q.require(FEATURE,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual trainer required'),
        Q.check('features','prerequisite',len(parents)>=5,'five actual Cheerleader Features required'),
        Q.check('charm','prerequisite',snapshot['charm']>=6,'Master Charm required')])


def _related(engine,owner,target):
    import world_entities as W
    if target.kind=='pokemon':return W.identity_field(engine,target,'owner_id')==owner.entity_id
    return target.kind=='trainer' and target is not owner and owner.side is not None and target.side==owner.side


def interested(engine,target):
    import taskmaster as TASK
    if TASK.press_interested(target):return True
    import world_entities as W,csv_item_form_contracts as FORMS
    index=W.actor_index(engine);targets=[target]
    relation=FORMS._relation(target,'as_one');marker=target.spec.get('off_field_reason',{})
    partner=relation['mount_id'] if relation else marker.get('owner_id') if marker.get('kind')=='as_one_mount' else None
    if partner in index:targets.append(index[partner])
    return any(owner.kind=='trainer' and A.owned_rule_count(owner,FEATURE) and any(_related(engine,owner,subject) for subject in targets)
               for owner in index.values())


def _uses(actor):
    rows=actor.spec.get(KEY,[])
    if type(rows) is not list:raise ValueError('Keep Fighting producer history must be a list')
    return rows


def _seal(row):return TFA._digest('keep-fighting/producer/v1',{k:v for k,v in row.items() if k!='integrity'})


def replace_hp(engine,target,before,proposed,*,source,loss_kind,amount,unpreventable=False):
    """The HP producer supplies the post-temporary-HP proposal, before writing it."""
    if source=='move/대타출동' and loss_kind=='hp_setting' and unpreventable:return proposed
    if before<1 or proposed>0:return proposed
    import world_entities as W,cheerleader as CH,frequency as F
    import action_lifecycle as ACTION,body_modes as BODY,turn as TURN
    import skill_modifiers as SKILLS,temporary_hp as HP
    for owner in W.actor_index(engine).values():
        if owner.kind!='trainer' or not A.owned_rule_count(owner,FEATURE) or not _related(engine,owner,target):continue
        receipt=CH.acquired(owner,FEATURE)
        if receipt is None:continue
        if not TURN.can_act(engine,owner) or not ACTION.status_permission(engine,owner,'free',new_action=True) or not BODY.permits(owner,'free'):continue
        if not F.activation_allowed(owner,FEATURE,QUOTA,engine=engine):continue
        origin={'target_id':target.entity_id,'before_hp':before,'proposed_hp':proposed,
                'amount':amount,'source':source,'loss_kind':loss_kind,'unpreventable':unpreventable}
        choice=engine.rulings.decide({'type':'keep_fighting','unit':FEATURE,'actor':owner.name,
            'text':'Use Keep Fighting: remain at 1 HP and gain twice current Charm temporary HP?',
            'trigger':deepcopy(origin)})
        if choice is not None and type(choice) is not bool:raise ValueError('explicit Keep Fighting use or decline required')
        if choice is not True:continue
        ACTION.triggered_free_action(engine,owner,FEATURE)
        F.consume_activation(owner,FEATURE,QUOTA,engine=engine)
        use_id='keep-fighting:'+owner.entity_id+':'+str(len(_uses(owner))+1)
        charm=SKILLS.effective_rank(engine.r,owner,'매력')
        previous=target.temp_hp
        gained=HP.grant(engine,target,charm*2,provenance={'source':FEATURE,'owner_id':owner.entity_id,'use_id':use_id})
        row={'id':use_id,'issuer_id':owner.entity_id,'source':deepcopy(receipt['source']),
             'acquisition_request_id':receipt['request_id'],'at':engine.elapsed_seconds,'round':engine.round_no,
             'period':deepcopy(F.activation_period(F.state(owner),'daily')),'origin':origin,
             'relationship':{'kind':target.kind,'owner_id':owner.entity_id if target.kind=='pokemon' else None,
                             'issuer_side':owner.side,'target_side':target.side},
             'after_hp':1,'charm':charm,'temp_before':previous,'temp_after':target.temp_hp,'temp_gained':gained}
        row['integrity']=_seal(row);owner.spec.setdefault(KEY,[]).append(row)
        engine.time_actors([owner,target])
        return 1
    return proposed


def validate_world(engine,index):
    for owner in index.values():
        for serial,row in enumerate(_uses(owner),1):
            fields={'id','issuer_id','source','acquisition_request_id','at','round','period','origin','relationship',
                    'after_hp','charm','temp_before','temp_after','temp_gained','integrity'}
            if type(row) is not dict or set(row)!=fields or row['integrity']!=_seal(row):raise ValueError('Keep Fighting producer evidence changed')
            if owner.kind!='trainer' or row['id']!='keep-fighting:'+owner.entity_id+':'+str(serial) or row['issuer_id']!=owner.entity_id or row['source']!=TFA._static_source(engine.r,FEATURE):
                raise ValueError('Keep Fighting actual source or issuer changed')
            if len([r for r in M.receipts(owner,FEATURE) if r['request_id']==row['acquisition_request_id']])!=1:
                raise ValueError('Keep Fighting actual historical acquisition missing')
            for key in ('charm','temp_before','temp_after','temp_gained'):C.integer(row[key],'Keep Fighting '+key,0)
            C.integer(row['at'],'Keep Fighting time',0,engine.elapsed_seconds);C.integer(row['round'],'Keep Fighting round',0,engine.round_no)
            origin=row['origin'];relation=row['relationship'];target=index.get(origin.get('target_id'))
            if target is None or target is owner or set(origin)!={'target_id','before_hp','proposed_hp','amount','source','loss_kind','unpreventable'}:
                raise ValueError('Keep Fighting actual HP producer target required')
            C.integer(origin['before_hp'],'Keep Fighting prior HP',1);C.integer(origin['proposed_hp'],'Keep Fighting proposed HP')
            C.integer(origin['amount'],'Keep Fighting producer loss',0)
            if origin['proposed_hp']>0 or origin['before_hp']-origin['amount']!=origin['proposed_hp'] or row['after_hp']!=1:
                raise ValueError('Keep Fighting must replace an actual positive-to-nonpositive HP crossing')
            if type(origin['source']) is not str or not origin['source'] or origin['loss_kind'] not in ('damage','loss','percentage','hp_setting','gm_set','gm_faint','as_one','nature_change','evolution') or type(origin['unpreventable']) is not bool:
                raise ValueError('Keep Fighting native HP producer changed')
            if set(relation)!={'kind','owner_id','issuer_side','target_side'} or relation['kind']!=target.kind:
                raise ValueError('Keep Fighting actual target relation changed')
            if target.kind=='pokemon':
                if relation['owner_id']!=owner.entity_id:raise ValueError('Keep Fighting requires its own Pokemon')
            elif target.kind!='trainer' or relation['owner_id'] is not None or relation['issuer_side'] is None or relation['issuer_side']!=relation['target_side']:
                raise ValueError('Keep Fighting requires an allied Trainer')
            if row['temp_gained'] not in (0,max(0,row['charm']*2-row['temp_before'])) or row['temp_after']!=row['temp_before']+row['temp_gained']:
                raise ValueError('Keep Fighting must use the shared nonstacking temporary HP grant')
    return True
