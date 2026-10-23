"""Book Go, Fight, Win!: compound Orders and its three fixed cheers."""
from copy import deepcopy
import common_checks as C
import effect_instances as E
import moment_of_action as M
import trainer_feature_acquisition as TFA
from action_metadata import ActionCost

FEATURE='feat/응원-문구'
CLAUSE='input/ch04-trainer-classes.md:705-712'
KEY='go_fight_win_uses'
COST=ActionCost(('standard','swift'))
CONDITIONS={'defense':'Motivated','temp_hp':'Excited','evasion':'Cheered'}
QUOTA={'kind':'scene','uses':1}


def _uses(actor):
    rows=actor.spec.get(KEY,[])
    if type(rows) is not list:raise ValueError('Book cheer producer history must be a list')
    return rows


def _seal(row):return TFA._digest('go-fight-win/producer/v1',{k:v for k,v in row.items() if k!='integrity'})


def use(engine,actor,*,cheer,stat=None,communication=None):
    import cheerleader as CH,optional_state_effect_contracts as OPTIONAL,state_grants as G
    import world_entities as W,passive_events as PASSIVE,heavy_injury_adapter as HEAVY
    PASSIVE.ensure_clear(engine);HEAVY.ensure_clear(engine);W.require_actors(engine,actor)
    if cheer not in CONDITIONS or (stat not in ('def','spd') if cheer=='defense' else stat is not None):
        raise ValueError('one Book cheer and its exact Defense or Special Defense choice required')
    receipt=CH.acquired(actor,FEATURE)
    if receipt is None:raise ValueError('actual acquired Book Go Fight Win required')
    if not actor.on_field or actor.captured:raise ValueError('actual present Orders performer required')
    targets=OPTIONAL._allies(engine,actor)
    ids={target.entity_id for target in targets}
    if communication is not None and (type(communication) is not dict or set(communication)!=ids):
        raise ValueError('exact per-ally established communication requests required')
    def apply(e,owner,*recipients):
        import priority_limited as P,turn as TURN,action_lifecycle as ACTION,body_modes as BODY
        import effect_lifetimes as LIFE,combat_timing as CLOCK,frequency as F,skill_modifiers as SKILLS
        import temporary_hp as HP
        if tuple(OPTIONAL._allies(e,owner))!=recipients:raise ValueError('actual complete battlefield ally roster changed')
        if not F.activation_allowed(owner,FEATURE+':'+cheer,QUOTA,engine=e):raise ValueError('this cheer was already performed this Scene')
        if cheer=='evasion':CLOCK.current(e)
        if e.encounter_active:
            P.preflight(e,owner,action=COST,source=FEATURE)
            ACTION.ensure_resolutions_clear(e)
            if (not TURN.can_act(e,owner) or not ACTION.status_permission(e,owner,COST)
                    or any(not BODY.permits(owner,kind) for kind in COST.components) or LIFE.forbids(owner,'priority')):
                raise ValueError('actual compound Priority action permission required')
        e.time_actors([owner,*recipients])
        use_id='go-fight-win:'+owner.entity_id+':'+str(len(_uses(owner))+1)
        deliveries={}
        for target in recipients:
            request,result=M._communication(e,owner,target,use_id,None if communication is None else communication[target.entity_id],source=FEATURE,label='Go, Fight, Win!')
            deliveries[target.entity_id]={'request_id':request,'result':result}
        if e.encounter_active:
            priority=P.reserve(e,owner,action=COST,source=FEATURE,subject=use_id,
                communication={'status':'delivered','recipients':deepcopy(deliveries)})
            payment={'kind':'priority_limited','receipt_id':priority['id']}
        else:
            if not TURN.spend_compound(e,owner,COST,'Go, Fight, Win!'):raise ValueError('actual Standard and Swift action costs required')
            payment={'kind':'compound','components':list(COST.components)}
        row={'id':use_id,'issuer_id':owner.entity_id,'source':deepcopy(receipt['source']),
            'acquisition_request_id':receipt['request_id'],'at':e.elapsed_seconds,'round':e.round_no,
            'scene':F.state(owner)['scene'],'cheer':cheer,'stat':stat,'charm':SKILLS.effective_rank(e.r,owner,'매력'),
            'count':CLOCK.current(e) if cheer=='evasion' else None,
            'payment':payment,'communication':deliveries,'targets':{}}
        for target in recipients:
            if cheer=='defense':e.change_stage(target,stat,1)
            elif cheer=='temp_hp':HP.grant(e,target,row['charm'],provenance={'source':FEATURE,'owner_id':owner.entity_id,'use_id':use_id})
            else:
                effect=LIFE.prepare(e,owner,target,{'type':'evasion_mod','value':2,'duration':'1라운드'},FEATURE)
                effect.update(go_fight_win_use=use_id,go_fight_win_owner=owner.entity_id,go_fight_win_target=target.entity_id)
                CLOCK.install(e,target,effect)
            effect=E.create(e,target,kind=CH.KIND,source=FEATURE,payload={'kind':CH.KIND,'condition':CONDITIONS[cheer]},
                capacity={'bucket':'independent_instances','source':FEATURE},lifetime={'boundary':'until_consumed'},applied_by=owner)
            effect['origin']={'issuer_id':owner.entity_id,'use_id':use_id}
            target.spec.setdefault(CH.KEY,[]).append(effect)
            row['targets'][target.entity_id]={'effect_id':effect['id'],'issuer_side':owner.side,'recipient_side':target.side}
        F.consume_activation(owner,FEATURE+':'+cheer,QUOTA,engine=e)
        row['integrity']=_seal(row);owner.spec.setdefault(KEY,[]).append(row)
        validate_world(e,W.actor_index(e))
        CH.issue(e,owner,recipients,{'kind':'go_fight_win','source':FEATURE,'use_id':use_id})
        return deepcopy(row)
    return G.transition(engine,actor,apply,participants=targets,include_rulings=True)


def validate_world(engine,index):
    import cheerleader as CH,priority_limited as P,combat_timing as CLOCK
    linked=set();issued={}
    for issuer in index.values():
        seen=set()
        for serial,row in enumerate(_uses(issuer),1):
            fields={'id','issuer_id','source','acquisition_request_id','at','round','scene','cheer','stat','charm','count','payment','communication','targets','integrity'}
            if type(row) is not dict or set(row)!=fields or row['integrity']!=_seal(row):raise ValueError('Book cheer producer evidence changed')
            if row['id']!='go-fight-win:'+issuer.entity_id+':'+str(serial) or row['issuer_id']!=issuer.entity_id or row['source']!=TFA._static_source(issuer.r,FEATURE):
                raise ValueError('Book cheer source or actual issuer changed')
            if len([r for r in M.receipts(issuer,FEATURE) if r['request_id']==row['acquisition_request_id']])!=1:raise ValueError('Book cheer historical acquisition missing')
            for field in ('at','round','scene','charm'):C.integer(row[field],'Book cheer '+field,0)
            if row['at']>engine.elapsed_seconds or row['round']>engine.round_no:raise ValueError('Book cheer producer is from the future')
            cheer=row['cheer'];key=(row['scene'],cheer)
            if cheer not in CONDITIONS or key in seen or (row['stat'] not in ('def','spd') if cheer=='defense' else row['stat'] is not None):
                raise ValueError('Book cheer choice or once-per-Scene identity changed')
            seen.add(key)
            if cheer=='evasion':C.integer(row['count'],'Book cheer initiative count')
            elif row['count'] is not None:raise ValueError('only the Evasion cheer has a full-round count')
            issued[(issuer.entity_id,row['id'])]=row
            if type(row['targets']) is not dict or set(row['communication'])!=set(row['targets']):raise ValueError('Book cheer complete target delivery evidence required')
            payment=row['payment']
            if payment.get('kind')=='priority_limited':
                paid=[r for r in P.records(issuer) if r['id']==payment.get('receipt_id')]
                if len(paid)!=1 or paid[0]['source']!=FEATURE or paid[0]['subject_id']!=row['id'] or paid[0]['payment']['funded']!={'standard':1,'swift':1} or paid[0]['communication']!={'status':'delivered','recipients':row['communication']}:
                    raise ValueError('Book cheer actual compound Priority reservation missing')
            elif payment!={'kind':'compound','components':list(COST.components)}:raise ValueError('Book cheer compound payment changed')
            for target_id,proof in row['targets'].items():
                target=index.get(target_id)
                if target is None or target is issuer or target.kind not in ('trainer','pokemon') or set(proof)!={'effect_id','issuer_side','recipient_side'} or proof['issuer_side'] is None or proof['issuer_side']!=proof['recipient_side']:
                    raise ValueError('Book cheer actual allied target evidence changed')
                delivered=row['communication'][target_id]
                if delivered['result']!=M._delivery(engine,issuer.entity_id,target_id,delivered['request_id'],row['at']):raise ValueError('actual Book cheer delivery changed')
                effects=[r for r in CH.live(target)+CH.history(target) if r['id']==proof['effect_id']]
                if len(effects)!=1:raise ValueError('Book cheer needs its actual fixed condition instance')
                effect=effects[0];CH.validate_record(target,effect,terminal=effect[E.KEY]['state']!='active')
                if effect['source']!=FEATURE or effect['origin']!={'issuer_id':issuer.entity_id,'use_id':row['id']} or effect['effect']['condition']!=CONDITIONS[cheer] or effect['at']!=row['at'] or effect['id'] in linked:
                    raise ValueError('Book cheer fixed condition and actual producer disagree')
                linked.add(effect['id'])
    timed=set()
    for target in index.values():
        for effect in CLOCK.records(target):
            if effect.get('source')!=FEATURE and 'go_fight_win_use' not in effect:continue
            key=(effect.get('go_fight_win_owner'),effect.get('go_fight_win_use'))
            row=issued.get(key);identity=(*key,target.entity_id)
            if row is None or row['cheer']!='evasion' or target.entity_id not in row['targets'] or identity in timed:
                raise ValueError('Book Evasion requires its actual unique producer and recipient')
            if (effect.get('source')!=FEATURE or effect.get('go_fight_win_target')!=target.entity_id
                    or effect.get('evasion_modifier')!=2 or tuple(effect.get('count_deadline',()))!=(row['round']+1,row['count'])
                    or effect.get('encounter_end') is not True):
                raise ValueError('Book Evasion source, recipient, bonus or full-round deadline changed')
            timed.add(identity)
    return linked
