"""Book Resilience consumes actual critical-damage and affliction boundaries.

The native attack scope owns one decision for each actual recipient. Critical
damage is calculated normally without rewriting the attack's critical fact.
"""
from copy import deepcopy
import acquired_features as A
import common_checks as C
import enduring_awareness as AWARE
import frequency as F
import moment_of_action as M
import trainer_feature_acquisition as TFA

FEATURE='feat/복원력'
CLAUSE='input/ch04-trainer-classes.md:812-816'
KEY='resilience_uses'
QUOTA={'kind':'scene','uses':1,'scope':['target']}


def acquisition_snapshot(actor):
    import skill_modifiers as S
    if AWARE.awareness_source(actor)!=AWARE.AWARENESS:
        raise ValueError('Book Resilience requires its actual Book Awareness prerequisite')
    if not AWARE.acquired(actor,AWARE.ENDURING,('Enduring Soul',)):
        raise ValueError('actual Enduring Soul prerequisite required')
    if actor.r._selected_rule(AWARE.AWARENESS)!=AWARE.AWARENESS:
        raise ValueError('selected Awareness prerequisite needs its own source contract')
    return {'awareness':deepcopy(AWARE.acquisition_record(actor,AWARE.AWARENESS)),
            'athletics':S.rank(actor.r,actor,'육상')[2],'focus':S.rank(actor.r,actor,'집중')[2]}


def qualification(actor,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!={'awareness','athletics','focus'}:
        raise ValueError('exact Book Resilience acquisition observations required')
    for field in ('athletics','focus'):C.integer(snapshot[field],'Resilience '+field,0)
    parent=snapshot['awareness']
    if (type(parent) is not dict or parent.get('trainer_id')!=actor.entity_id
            or parent.get('source')!=AWARE.AWARENESS or parent.get('prerequisite_source')!=AWARE.ENDURING
            or len(parent.get('defenders',[]))!=3):
        raise ValueError('actual historical Book Awareness acquisition required')
    return Q.require(FEATURE,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('skill','prerequisite',max(snapshot['athletics'],snapshot['focus'])>=5,
                'Expert Athletics or Focus required')])


def interested(actor):return bool(A.owned_rule_count(actor,FEATURE))


def acquired(actor):
    if not interested(actor):return None
    TFA.validate_actor(actor)
    rows=M.receipts(actor,FEATURE,active=True)
    if actor.kind!='trainer' or A.owned_rule_count(actor,FEATURE)!=1 or len(rows)!=1:
        raise ValueError('Resilience requires one actual source-specific acquisition')
    return rows[0]


def _owner(engine,target):
    import world_entities as W
    W.require_actors(engine,target)
    if target.kind!='pokemon':return None
    owner=W.actor_index(engine).get(target.spec.get('trainer_id'))
    if owner is None or not interested(owner):return None
    return owner if acquired(owner) is not None else None


def _scope(engine):
    # These are issued by native producers, never accepted from a script payload.
    scopes=getattr(engine,'_event_use_scopes',())
    if scopes and scopes[-1].get('move_id') is not None:return scopes[-1]
    frames=getattr(engine,'_native_action_stack',())
    return frames[-1] if frames else None


def _uses(actor):
    rows=actor.spec.get(KEY,[])
    if type(rows) is not list:raise ValueError('Resilience uses must be a list')
    return rows


def _seal(row):return TFA._digest('enduring-resilience/use/v1',{k:v for k,v in row.items() if k!='integrity'})


@__import__('cheerleader').native_action
def prevent(engine,target,*,critical=False,condition=None,source=None,attacker=None,classification=None):
    if type(critical) is not bool:raise ValueError('actual critical fact required')
    if not critical:
        classification=classification or engine.r.condition_class(condition)
        if classification not in ('persistent','volatile'):return False
    owner=_owner(engine,target)
    if owner is None:return False
    frame=_scope(engine)
    choices=frame.setdefault('resilience_decisions',{}) if frame is not None else {}
    if target.entity_id in choices:return choices[target.entity_id]
    if owner.dead or owner.fainted or owner.hp<=0:return False
    import turn as TURN,action_lifecycle as ACTION,action_points as AP
    if not TURN.can_act(engine,owner) or not ACTION.status_permission(engine,owner,'free',new_action=True):return False
    key=F.declaration_key(engine,owner,target,FEATURE,'triggered_free',QUOTA)
    if not F.activation_allowed(owner,key,QUOTA,engine=engine) or AP.available(owner)<2:return False
    choice=engine.rulings.decide({'type':'resilience','unit':FEATURE,'actor_id':owner.entity_id,
        'target_id':target.entity_id,'critical':critical,'condition':condition,'source':source,
        'text':'Use Resilience once for this actual attack or affliction event? Its critical damage and afflictions are prevented together.'})
    if choice is not None and type(choice) is not bool:raise ValueError('explicit Resilience use or decline required')
    if choice is not True:
        choices[target.entity_id]=False
        return False
    receipt=acquired(owner)
    ACTION.triggered_free_action(engine,owner,FEATURE)
    AP.charge(owner,2)
    F.consume_activation(owner,key,QUOTA,engine=engine)
    row={'id':owner.entity_id+':resilience:'+str(len(_uses(owner))+1),'issuer_id':owner.entity_id,
        'target_id':target.entity_id,'owner_id':owner.entity_id,'source':deepcopy(receipt['source']),
        'acquisition_request_id':receipt['request_id'],'at':engine.elapsed_seconds,'round':engine.round_no,
        'scene':F.state(owner)['scene'],'quota_key':key,'ap':2,
        'trigger':{'critical':critical,'condition':condition,'classification':classification,
                   'source':source,'attacker_id':getattr(attacker,'entity_id',None)}}
    row['integrity']=_seal(row);owner.spec.setdefault(KEY,[]).append(row)
    choices[target.entity_id]=True
    engine.time_actors([owner,target])
    engine.log('    '+target.name+': 복원력, 상태 부여 방지 및 해당 치명타 피해 일반 계산',FEATURE)
    return True


def validate_world(engine,index):
    for owner in index.values():
        if interested(owner):acquired(owner)
        current={}
        for serial,row in enumerate(_uses(owner),1):
            if type(row) is not dict or row.get('integrity')!=_seal(row):raise ValueError('Resilience use evidence changed')
            if (owner.kind!='trainer' or row['id']!=owner.entity_id+':resilience:'+str(serial)
                    or row['issuer_id']!=owner.entity_id or row['owner_id']!=owner.entity_id or row['ap']!=2
                    or row['source']!=TFA._static_source(engine.r,FEATURE)):
                raise ValueError('Resilience source, payment or actual issuer changed')
            if len([r for r in M.receipts(owner,FEATURE) if r['request_id']==row['acquisition_request_id']])!=1:
                raise ValueError('historical Resilience acquisition missing')
            target=index.get(row['target_id'])
            if target is None or target.kind!='pokemon':raise ValueError('Resilience needs its actual Pokemon recipient')
            C.integer(row['at'],'Resilience time',0,engine.elapsed_seconds)
            C.integer(row['round'],'Resilience round',0,engine.round_no)
            C.integer(row['scene'],'Resilience scene',0,F.state(owner)['scene'])
            expected=F.declaration_key(engine,owner,target,FEATURE,'triggered_free',QUOTA)
            if row['quota_key']!=expected:raise ValueError('Resilience target quota changed')
            trigger=row['trigger']
            if type(trigger['critical']) is not bool or (not trigger['critical'] and trigger['classification'] not in ('persistent','volatile')):
                raise ValueError('actual critical hit or affliction required')
            if row['scene']==F.state(owner)['scene']:current[expected]=current.get(expected,0)+1
        for key,used in current.items():
            entry=F.state(owner)['activations'].get(key,{})
            if used!=1 or entry!={'kind':'scene','period':F.state(owner)['scene'],'used':1}:
                raise ValueError('Resilience must use each actual target once per Scene')
    return True
