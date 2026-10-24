"""Book Stat Ace branches on native acquisition, action and effect owners.

The template advertises choices; only acquire_static commits a branch. English
PTU 1.05 pp112-113 controls the duplicated Korean choice and Bound omission.
"""
from copy import deepcopy
import common_checks as C
import state_grants as G

CLASS='class/스탯-에이스'
LINK='feat/스탯-링크'
TRAINING='feat/스탯-훈련'
MANEUVER='feat/스탯-메뉴버'
MASTERY='feat/스탯-마스터리'
EMBODIMENT='feat/스탯-전형'
STRATAGEM='feat/스탯-책략'
STATS=('atk','def','spa','spd','spe')
STYLE={'아름다움':'spa','근사함':'atk','귀여움':'spe','슬기로움':'spd','강인함':'def'}
DEFINITIONS={
 CLASS:{'span':(1097,1099),'parents':[],'rank':3,'action':'static','choices':STATS},
 LINK:{'span':(1101,1106),'parents':[CLASS],'rank':0,'action':'free','ap':1},
 TRAINING:{'span':(1108,1118),'parents':[CLASS],'rank':0,'action':'extended','tp':1},
 MANEUVER:{'span':(1120,1129),'parents':[CLASS],'rank':4,'action':'free','frequency':{'kind':'scene','uses':1}},
 MASTERY:{'span':(1131,1140),'parents':[MANEUVER],'rank':0,'action':'static'},
 EMBODIMENT:{'span':(1142,1152),'parents':[CLASS],'rank':5,'action':'swift','class_features':4,'ap':1},
 STRATAGEM:{'span':(1154,1164),'parents':[LINK,TRAINING],'rank':6,'action':'standard','bound_ap':2},
}
FEATURES={uid:row['span'] for uid,row in DEFINITIONS.items()}
MOVES={'atk':('move/칼춤','move/분노'),'def':('move/철벽','move/리플렉터'),
       'spa':('move/나쁜음모','move/잠재파워'),'spd':('move/망각술','move/빛의장막'),
       'spe':('move/고속이동','move/당신먼저')}


def records(actor,feature=None,active=False):
    import trainer_feature_acquisition as T
    return [row['static_acquisition'] for _,row,live in T._static_records(actor)
            if row['static_acquisition']['feature_id'] in FEATURES
            and (feature is None or row['static_acquisition']['feature_id']==feature)
            and (not active or live)]


def acquired(actor,feature,branch):
    if branch not in STATS:raise ValueError('exact Stat Ace branch required')
    rows=[row for row in records(actor,feature,True) if row['snapshot']['branch']==branch]
    if len(rows)>1:raise ValueError('one acquired Stat Ace branch instance required')
    return rows[0] if rows else None


def acquisition_snapshot(engine,actor,feature,branch):
    import acquired_features as A,skill_modifiers as S,world_entities as W
    if branch not in STATS:raise ValueError('exact Stat Ace branch required')
    rank=max(S.rank(engine.r,actor,key)[2] for key in ('명령','집중'))
    parents={uid:(acquired(actor,uid,branch) or {}).get('request_id') for uid in DEFINITIONS[feature]['parents']}
    result={'branch':branch,'rank':rank,'parents':parents}
    if feature==CLASS:
        pokemon=[p for p in W.actor_index(engine).values() if p.kind=='pokemon' and p.spec.get('trainer_id')==actor.entity_id]
        result['pokemon']=[{'id':p.entity_id,'stat':p.stats[branch]} for p in sorted(pokemon,key=lambda p:p.entity_id)]
        instances=A.class_instances(actor)
        result['ace_trainer']=any(row['source_id']=='class/에이스-트레이너' for row in instances)
        result['style']=[row['branch'] for row in instances if row['source_id']=='class/스타일-전문가']
    if feature==EMBODIMENT:result['features']=[row['request_id'] for row in records(actor,active=True) if row['feature_id']!=EMBODIMENT]
    return result


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    fields={'branch','rank','parents'}|({'pokemon','ace_trainer','style'} if feature==CLASS else set())|({'features'} if feature==EMBODIMENT else set())
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields:
        raise ValueError('exact Stat Ace acquisition observations required')
    branch=snapshot['branch'];C.integer(snapshot['rank'],'Stat Ace skill rank',0)
    if branch not in STATS or set(snapshot['parents'])!=set(DEFINITIONS[feature]['parents']):raise ValueError('Stat Ace branch prerequisites changed')
    for uid,request in snapshot['parents'].items():
        if not any(row['request_id']==request and row['snapshot']['branch']==branch for row in records(actor,uid)):
            raise ValueError('actual acquired prerequisite branch required: '+uid)
    if feature==CLASS:
        p=snapshot['pokemon']
        if type(p) is not list or len({row['id'] for row in p})!=len(p):raise ValueError('distinct actual owned Pokemon observations required')
        for row in p:C.integer(row['stat'],'observed chosen stat',0)
        route=(snapshot['ace_trainer'] or any(STYLE.get(value)==branch for value in snapshot['style'])) and any(row['stat']>=15 for row in p)
        if not route and sum(row['stat']>=20 for row in p)<3:raise ValueError('Stat Ace requires matching Ace/Style and stat15 or three stat20 Pokemon')
    if feature==EMBODIMENT:
        known={row['request_id'] for row in records(actor) if row['feature_id']!=EMBODIMENT}
        if len(set(snapshot['features']))<4 or not set(snapshot['features'])<=known:raise ValueError('four actual Stat Ace Features required')
    return Q.require(feature,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('skill','prerequisite',snapshot['rank']>=DEFINITIONS[feature]['rank'],'printed Command or Focus rank required')])


def owner(engine,pokemon,feature,branch):
    import world_entities as W
    if pokemon.kind!='pokemon':return None
    trainer=W.actor_index(engine).get(pokemon.spec.get('trainer_id'))
    if trainer is None or trainer.kind!='trainer':return None
    return trainer if acquired(trainer,CLASS,branch) and acquired(trainer,feature,branch) else None


def has(engine,pokemon,feature,branch):return owner(engine,pokemon,feature,branch) is not None


def end_turn(engine,pokemon):
    """Called only by the native checked actual end-of-turn producer."""
    import action_lifecycle as A,action_points as AP,combat_stage_sources as CS
    import combat_timing as LIFE
    if has(engine,pokemon,MASTERY,'def') and not getattr(pokemon,'_regular_shift_movement_used',False):
        for effect in list(LIFE.records(pokemon)):
            if effect.get('stat_mastery_defense'):LIFE.expire(engine,pokemon,effect,ending='replaced')
        LIFE.install(engine,pokemon,{'source':MASTERY,'stat_mastery_defense':True,
            'count_deadline':(engine.round_no+1,LIFE.current(engine)),'encounter_end':True})
    for branch in STATS:
        trainer=owner(engine,pokemon,LINK,branch)
        state=CS.validate(pokemon)
        default=CS.total(state,branch) if state is not None else 0
        if trainer is None or pokemon.stages[branch]>default or AP.available(trainer)<1:continue
        choice=engine.rulings.decide({'type':'stat_link','unit':LINK,'actor':trainer.name,
            'target':pokemon.name,'branch':branch,'text':'Use Stat Link for 1 AP? true or false.'})
        if choice is None or choice is False:continue
        if choice is not True:raise ValueError('Stat Link requires explicit boolean choice')
        A.triggered_free_action(engine,trainer,LINK)
        trainer.ap_account.charge(1)
        engine.change_stage(pokemon,branch,1)


def damage_reduction(engine,pokemon):
    import combat_timing as TIME
    return 5 if has(engine,pokemon,MASTERY,'def') and any(row.get('stat_mastery_defense') for row in TIME.records(pokemon)) else 0


def tick_loss(engine,pokemon,amount):
    return max(1,amount-5) if amount>0 and has(engine,pokemon,MASTERY,'spd') else amount


def teach(engine,trainer,pokemon,branch,move_id,*,seconds,reason,replace=None,safe=None):
    import pokemon_teaching as T,learning_grant as L,move_state as M
    import turn as TURN,activity_jobs as JOBS,acquisition_withdrawal as WITHDRAWAL
    T._pokemon(engine,trainer,pokemon)
    if owner(engine,pokemon,TRAINING,branch) is not trainer:raise ValueError('actual Stat Training branch required')
    C.integer(seconds,'observed Extended Stat Training seconds',1)
    if type(reason) is not str or not reason.strip():raise ValueError('actual Stat Training reason required')
    mid=engine.r.move_id(move_id)
    pool=list(MOVES[branch])
    if mid not in pool:raise ValueError('Move outside selected Stat Training branch')
    def apply(e,a,p):
        if T._balance(p.spec)<1:raise ValueError('Stat Training requires one actual Tutor Point')
        candidate=deepcopy(p.spec);old=e.r.move_id(replace) if replace is not None else None
        if replace is not None:
            if old not in M.known(e.r,p.spec):raise ValueError('actual learned replacement required')
            import move_type_sync as SYNC
            SYNC.forget_spec(e.r,candidate,old,at=e.elapsed_seconds,reason=reason)
            candidate['moves']=[uid for uid in candidate['moves'] if e.r.move_id(uid)!=old]
        L.learn_moves(e.r,candidate,candidates=pool,selected=[mid],method='feature',source=TRAINING,
            reason=reason,provider=a.entity_id,paid_tp=1,details={'branch':branch,'seconds':seconds},replaced=old)
        M.record_natural_opportunities(e.r,candidate,reason='completed Stat Training')
        M.validate_spec(e.r,candidate,require_routes=True)
        if not TURN.spend(e,a,'extended',TRAINING):raise ValueError('actual Stat Training Extended permission required')
        JOBS.run_fixed(e,a,(p,),seconds=seconds,source=TRAINING,context={'move_id':mid})
        for field in ('move_learning','move_learning_log',M.HISTORY,'move_type_sync'):
            if field in candidate:p.spec[field]=candidate[field]
        G.set_baseline(p,'moves',candidate['moves']);T._debit_points(p.spec,1)
        sid='feature:'+a.entity_id+':'+TRAINING+':'+branch
        WITHDRAWAL.irreversible(e,a,sid,event_id='stat-training:'+p.entity_id+':'+mid+':'+str(e.elapsed_seconds),reason=reason)
        return {'activity':'stat_training','move':mid,'point_cost':1,'branch':branch,'seconds':seconds}
    return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def maneuver_success(engine,pokemon,target,source):
    if source in ('maneuver/밀기','maneuver/무장해제','maneuver/치사한-짓') and has(engine,pokemon,MASTERY,'atk'):
        engine.lose_tick_hp(target,1,source=MASTERY)


def special_range(engine,pokemon,move,spec):
    if pokemon is None or move.get('class')!='특수' or not has(engine,pokemon,MASTERY,'spa') or spec.get('origin')=='melee':return spec
    result=deepcopy(spec)
    # Existing CSV Static materialization already contributes this same benefit.
    if not result.get('static_origin_bonus') and type(result.get('origin')) is int:result['origin']+=2
    return result


def _stratagem(engine,pokemon):
    import class_passive_combat as P
    active=P._active(engine,pokemon,STRATAGEM)
    return None if active is None else active[1]['branch']


def stratagem_bonus(engine,pokemon,kind,move=None,condition=None):
    branch=_stratagem(engine,pokemon)
    if branch is None:return 0
    steps=max(0,min(3,pokemon.stages[branch]))
    damaging=move and move.get('class') in ('물리','특수')
    melee=move and '근접' in move.get('range','')
    if kind=='critical' and branch=='atk' and damaging and melee:return steps
    if kind=='effect' and branch=='spa' and damaging and not melee:return steps
    if kind=='save' and ((branch=='def' and condition in ('마비','잠듦','얼음')) or (branch=='spd' and condition in ('혼란','난동','헤롱헤롱'))):return steps*2
    if kind=='movement' and branch=='spe':return steps
    return 0


def activate(engine,trainer,pokemon,branch,*,communication=None):
    """Use the existing single-Stratagem, typed Bound-AP and Order owner."""
    import class_passive_combat as P,cheerleader as CHEER,turn as TURN,action_points as AP
    import world_entities as W,temporary_ap as TEMP
    W.require_actors(engine,trainer,pokemon)
    if owner(engine,pokemon,STRATAGEM,branch) is not trainer:raise ValueError('actual acquired owned Stat Stratagem branch required')
    @CHEER.order_activation(STRATAGEM)
    def apply(e,a,p):
        if not e.encounter_active or not p.on_field or p.fainted or p.captured:raise ValueError('available encounter Stratagem target required')
        P._require_stratagem_slot(p)
        if AP.available(a)<2:raise ValueError('Stat Stratagem requires two available AP')
        TEMP.preflight_binding(a,2,'class_passive_combat')
        import order_actions as ORDERS
        delivery=ORDERS.delivery(e,a,p,STRATAGEM,communication=communication)
        ORDERS.spend(e,a,STRATAGEM,subject=p.entity_id,communication=delivery)
        state=P._state(p,create=True);state['serial']+=1
        instance='class-passive:'+a.entity_id+':'+str(state['serial'])
        while instance in a.ap_account.identified_bindings(allow_missing=True):
            state['serial']+=1;instance='class-passive:'+a.entity_id+':'+str(state['serial'])
        a.ap_account.charge(2,mode='bind',instance_id=instance,temporary_binding_owner='class_passive_combat')
        receipt=acquired(a,STRATAGEM,branch)
        row={'owner_id':a.entity_id,'target_id':p.entity_id,'instance':instance,'rule_id':STRATAGEM,
            'clause_id':'input/ch04-trainer-classes.md:1154-1164','acquisition_source':receipt['request_id'],
            'branch':branch,'lifetime':'sustained_2_ap_encounter'}
        state['sustains'][STRATAGEM]=row
        G._source(p,instance,P.KIND,owner_id=a.entity_id,lifetime=row['lifetime'],rule_id=STRATAGEM,
            clause_id=row['clause_id'],acquisition_source=row['acquisition_source'],sustain=True,tutor_points=0,branch=branch)
        return (1,0)
    return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def withdraw(engine,trainer,feature):
    if feature!=STRATAGEM:return
    import class_passive_combat as P,world_entities as W
    for pokemon in W.actor_index(engine).values():
        state=P._state(pokemon)
        row=None if state is None else state['sustains'].get(STRATAGEM)
        if row and row['owner_id']==trainer.entity_id:P._unbind(engine,pokemon,STRATAGEM,trainer,row)


def _consume(engine,trainer,pokemon,branch,move_id):
    import frequency as F,action_lifecycle as A
    if owner(engine,pokemon,MANEUVER,branch) is not trainer:raise ValueError('actual acquired Stat Maneuver branch required')
    key=MANEUVER+':'+branch;frequency=DEFINITIONS[MANEUVER]['frequency']
    if not F.activation_allowed(trainer,key,frequency,engine=engine):raise ValueError('Stat Maneuver branch Scene frequency exhausted')
    A.triggered_free_action(engine,trainer,MANEUVER)
    F.consume_activation(trainer,key,frequency,engine=engine)
    receipt={'source':MANEUVER,'issuer_id':trainer.entity_id,'target_id':pokemon.entity_id,
        'acquisition_request':acquired(trainer,MANEUVER,branch)['request_id'],'branch':branch,
        'move_id':move_id,'round':engine.round_no,'scene':F.state(trainer)['scene']}
    trainer.spec.setdefault('stat_maneuver_uses',[]).append(deepcopy(receipt))
    return receipt


def conversion_proof(engine,actor_id,proof,round_no):
    import world_entities as W
    trainer=W.actor_index(engine).get(proof.get('issuer_id'))
    if (trainer is None or proof.get('source')!=MANEUVER or proof.get('branch')!='atk'
            or proof.get('target_id')!=actor_id or proof.get('round')!=round_no
            or proof not in trainer.spec.get('stat_maneuver_uses',[])):
        raise ValueError('actual paid Stat Maneuver Pass proof required')
    return proof


def scope(engine,pokemon,move):
    row=getattr(engine,'_stat_maneuver_scope',None)
    if row is None:
        matches=[scope['stat_maneuver'] for scope in getattr(engine,'_move_activation_scopes',())
            if scope['actor'] is pokemon and scope['move_id']==move['id'] and 'stat_maneuver' in scope]
        if len(matches)>1:raise ValueError('one actual Stat Maneuver activation required')
        row=matches[0] if matches else None
    if row is None or row['pokemon'] is not pokemon or row['move_id']!=move['id']:return None
    if row['proof'] not in row['trainer'].spec.get('stat_maneuver_uses',[]):raise ValueError('actual paid Stat Maneuver scope required')
    return row


def range_spec(engine,pokemon,move,spec):
    row=scope(engine,pokemon,move)
    return deepcopy(row['range']) if row is not None else spec


def bind(engine,pokemon,move):
    row=scope(engine,pokemon,move)
    return dict(move,range=row['range']['raw'],_class_move_range=deepcopy(row['range'])) if row is not None else move


def maneuver(engine,trainer,pokemon,target,move_id,*,branch,option,aim=None,destination=None,event_id=None,targets=None,set_damage=False):
    """Commit the Free choice and the existing complete Move or Pass activation."""
    import weapon_actions as W,pass_moves as PASS,move_state as MOVES
    import world_entities as WORLD
    WORLD.require_actors(engine,trainer,pokemon,target)
    if targets is not None:
        if not isinstance(targets,(list,tuple)) or not 1<=len(targets)<=3 or len({p.entity_id for p in targets})!=len(targets):raise ValueError('one to three distinct selected Stat Maneuver targets required')
        WORLD.require_actors(engine,*targets)
        if targets[0] is not target:raise ValueError('first selected Stat Maneuver target must be the primary')
    if option=='three' and targets is None:raise ValueError('three-target Stat Maneuver requires explicit actual target selection')
    if option!='three' and targets is not None:raise ValueError('explicit selected targets belong to three-target Stat Maneuver')
    mid=engine.r.move_id(move_id)
    if mid is None or mid not in MOVES.known(engine.r,pokemon.spec):raise ValueError('actual learned Stat Maneuver Move required')
    move=engine.r.move(mid);original=W.range_spec(engine,move,pokemon)
    if branch=='spe':
        import priority_actions as PRIORITY
        if option!='priority':raise ValueError('Speed Stat Maneuver grants Priority')
        return PRIORITY.use(engine,pokemon,target,mid,stat_maneuver=trainer)
    if branch=='atk':
        if move.get('class')!='물리' or original.get('origin')!='melee' or original.get('targets')!=1 or original.get('shape'):
            raise ValueError('Attack Stat Maneuver needs Physical Melee 1-Target')
        if option not in ('pass','three'):raise ValueError('Attack Stat Maneuver chooses Pass or three targets')
        result={'raw':'근접, 통과' if option=='pass' else '근접, 대상3','origin':'melee','targets':1 if option=='pass' else 3,'parsed':True}
    elif branch=='spa':
        shapes={'burst':('파열 1',1),'cone':('원뿔 2',2),'close_blast':('인접 폭발 2',2),'line':('직선 4',4)}
        if move.get('class')!='특수' or original.get('shape') not in ('burst','cone','close_blast','blast','line') or option not in shapes:
            raise ValueError('Special Attack Stat Maneuver needs an actual Special area Move and one of four shapes')
        raw,size=shapes[option];result={'raw':raw,'origin':'self','shape':option,'size':size,'parsed':True}
    else:raise ValueError('Defense Stat Maneuver is chosen at the actual incoming hit')
    pending=[]
    def apply(e,a,p,t):
        if hasattr(e,'_stat_maneuver_scope'):raise ValueError('nested Stat Maneuver activation requires a native continuation')
        proof=_consume(e,a,p,branch,mid)
        e._stat_maneuver_scope={'trainer':a,'pokemon':p,'move_id':mid,'range':result,'proof':proof,
            'targets':[p.entity_id for p in targets] if targets is not None else None}
        try:
            if option=='pass':
                return PASS.use(e,p,mid,destination,event_id=event_id,object_adjudications={},source=MANEUVER,
                    reason='actual Stat Maneuver Pass declaration',range_source=MANEUVER)
            return e.use_move_on(p,t,mid,e.everyone,aim=aim,set_damage=set_damage)
        except Exception as error:
            import passive_events as PASSIVE,heavy_injury_adapter as HEAVY
            if (type(error) is PASSIVE.PassiveEventPending and e._passive_pending==error.event_id
                    and error.event_id in e._passive_events):pending.append((PASSIVE.PassiveEventPending,error.event_id));return None
            if (type(error) is HEAVY.HeavyPending and e._heavy_pending==error.event_id
                    and error.event_id in e._heavy_events):pending.append((HEAVY.HeavyPending,error.event_id));return None
            raise
        finally:del e._stat_maneuver_scope
    result=G.transition(engine,trainer,apply,participants=(pokemon,target),include_rulings=True,include_grid=engine.grid is not None)
    if pending:
        exception,event=pending[0];raise exception(event)
    return result


def selected_targets(engine,pokemon,move,eligible,primary):
    row=scope(engine,pokemon,move)
    if row is None or row['targets'] is None:return None
    import body_state as BODY
    indexed={p.entity_id:p for p in eligible}
    if any(uid not in indexed for uid in row['targets']):raise ValueError('all selected Stat Maneuver recipients must be actual eligible targets')
    selected=[indexed[uid] for uid in row['targets']]
    if not selected or selected[0] is not primary or len(selected)>3:raise ValueError('actual primary and at most three recipients required')
    if any(not BODY.in_range(engine,pokemon,p,BODY.melee_reach(pokemon),move=move) for p in selected):raise ValueError('all selected Stat Maneuver recipients must be in actual Melee range')
    return selected


def defense_maneuver(engine,pokemon,move,event):
    branch={'물리':'def','특수':'spd'}.get(move.get('class'))
    if branch is None or event is None:return None
    trainer=owner(engine,pokemon,MANEUVER,branch)
    if trainer is None:return None
    import frequency as F
    if not F.activation_allowed(trainer,MANEUVER+':'+branch,DEFINITIONS[MANEUVER]['frequency'],engine=engine):return None
    choice=engine.rulings.decide({'type':'stat_maneuver_defense','unit':MANEUVER,'actor':trainer.name,
        'target':pokemon.name,'branch':branch,'text':'Receive this hit as if the chosen defensive Combat Stage were +6?'})
    if choice is None or choice is False:return None
    if choice is not True:raise ValueError('Stat Maneuver requires an explicit boolean choice')
    _consume(engine,trainer,pokemon,branch,move['id'])
    return branch
