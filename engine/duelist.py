"""Book Duelist: one tagged foe, native Momentum producers and its consumers."""
import arithmetic_policy as NUMERIC
from copy import deepcopy
import acquired_features as A
import common_checks as C
import counter_effects as COUNTERS
import frequency as F
import state_grants as G
import combat_timing as TIME

CLASS='class/듀얼리스트'
EXPEND='feat/탄력-확장'
METHODS='feat/효과적인-방법'
DIRECTED='feat/다이렉트-포커스'
TYPE='feat/타입-방법론'
MANUAL='feat/듀얼리스트-메뉴얼'
SEIZE='feat/기회-포착'
FOCUSED='feat/집중성-훈련'
TOLERANCE='ability/강내성'
EXPLOIT='ability/착취'
FEATURES={CLASS:(720,732),EXPEND:(735,743),DIRECTED:(751,754),TYPE:(756,762),MANUAL:(764,772),SEIZE:(774,779)}
KEY='duelist_state'
COUNTER='duelist_momentum'
USES='duelist_uses'
PARENTS={CLASS:(FOCUSED,),EXPEND:(CLASS,),DIRECTED:(METHODS,),TYPE:(METHODS,),MANUAL:(EXPEND,METHODS),SEIZE:(CLASS,)}
RANKS={CLASS:3,TYPE:4,MANUAL:5,SEIZE:6}


def acquired(actor,feature=CLASS):
    if not A.owned_rule_count(actor,feature):return False
    import trainer_feature_acquisition as TFA
    TFA.validate_actor(actor)
    receipts=[row['static_acquisition'] for _,row,live in TFA._static_records(actor)
              if live and row['static_acquisition']['feature_id']==feature]
    if not receipts:return False
    if len(receipts)!=1 or A.owned_rule_count(actor,feature)!=1:
        raise ValueError('Duelist requires its actual Book acquisition receipt')
    return receipts[0]


def acquisition_snapshot(actor,feature):
    import skill_modifiers as SK
    if any(A.owned_rule_count(actor,parent)!=1 for parent in PARENTS[feature]):
        raise ValueError('actual acquired Duelist prerequisites required')
    return {'parents':list(PARENTS[feature]),'focus':SK.rank(actor.r,actor,'집중')[2]}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or set(snapshot)!={'parents','focus'} or snapshot['parents']!=list(PARENTS[feature]):
        raise ValueError('exact Book Duelist acquisition observations required')
    C.integer(snapshot['focus'],'acquisition Focus rank',0)
    return Q.require(feature,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual trainer required'),
        Q.check('focus','prerequisite',snapshot['focus']>=RANKS.get(feature,0),'printed Focus prerequisite required')])


def owner(engine,pokemon):
    import world_entities as W
    if pokemon.kind!='pokemon':return None
    uid=W.identity_field(engine,pokemon,'owner_id')
    return W.actor_index(engine).get(uid)


def _owner(engine,pokemon,feature=CLASS):
    trainer=owner(engine,pokemon)
    return trainer if trainer is not None and acquired(trainer,feature) and acquired(trainer) else None


def momentum(pokemon):return C.integer(pokemon.counters.get(COUNTER,0),'actual Momentum',0,6)


def _state(actor):return actor.spec.setdefault(KEY,{'tag':None,'gains':[]})


def tagged(engine,pokemon,foe):
    trainer=_owner(engine,pokemon)
    return bool(trainer and trainer.spec.get(KEY,{}).get('tag')==foe.entity_id)


def focused(pokemon,trainer):
    import training_features as TRAIN
    return any(row['rule_id']==FOCUSED and row['owner'] is trainer for row in TRAIN.active(pokemon))


def accuracy(engine,pokemon,foe):
    trainer=_owner(engine,pokemon)
    if trainer is None or not focused(pokemon,trainer):return 0
    tag=trainer.spec.get(KEY,{}).get('tag')
    if tag is None:return 0
    if tag==foe.entity_id:return NUMERIC.ceil_ratio(momentum(pokemon),2)
    import training_features as TRAIN
    return -sum(TRAIN.bonuses(row).get('accuracy',0) for row in TRAIN.active(pokemon)
                if row['rule_id']==FOCUSED and row['owner'] is trainer)


def evasion(engine,pokemon,foe):
    trainer=_owner(engine,pokemon)
    return NUMERIC.ceil_ratio(momentum(pokemon),2) if trainer and focused(pokemon,trainer) and tagged(engine,pokemon,foe) else 0


def tag(engine,trainer,foe):
    import world_entities as W,turn as TURN
    W.require_actors(engine,trainer,foe)
    if not acquired(trainer) or foe.kind not in ('trainer','pokemon') or foe is trainer:
        raise ValueError('actual Duelist and opposing Trainer or Pokemon required')
    own_side=getattr(trainer,'side',None);foe_side=getattr(foe,'side',None)
    if own_side is None or foe_side is None or own_side==foe_side:raise ValueError('Duelist tags an observed opposing foe')
    def apply(e,a,t):
        if not TURN.spend(e,a,'swift',CLASS):raise ValueError('Duelist requires its Swift action')
        state=_state(a);state['tag']=None if state['tag']==t.entity_id else t.entity_id
        return {'tagged_id':state['tag']}
    return G.transition(engine,trainer,apply,participants=(foe,))


def _change(engine,pokemon,value):
    COUNTERS.change(engine,pokemon,{'type':'counter','name':COUNTER,'set':value,'max':6},CLASS)


def gain(engine,pokemon,origin):
    trainer=_owner(engine,pokemon)
    if trainer is None or not pokemon.on_field or pokemon.fainted:return
    state=_state(pokemon)
    if any(row['origin']==origin for row in state['gains']):return
    before=momentum(pokemon)
    row={'id':'momentum:'+pokemon.entity_id+':'+str(len(state['gains'])+1),'origin':deepcopy(origin),
         'before':before,'round':engine.round_no,'scene':F.state(pokemon)['scene'],'status':'gained'}
    row['integrity']=_gain_seal(row)
    state['gains'].append(row)
    _change(engine,pokemon,min(6,before+1))
    if before==6 and acquired(trainer,SEIZE):_offer_seize(engine,trainer,pokemon,row)


def round_end(engine):
    for pokemon in list(engine.time_actors()):
        if pokemon.kind=='pokemon':gain(engine,pokemon,{'kind':'round_end','round':engine.round_no})


def clear(engine,pokemon,reason):
    if COUNTER in pokemon.counters:_change(engine,pokemon,0)
    if KEY in pokemon.spec:
        for row in pokemon.spec[KEY]['gains']:
            if row['status']=='pending':row['status']='expired'


def end_encounter(engine,actors):
    for actor in actors:
        clear(engine,actor,'combat_end')
        if actor.kind=='trainer' and KEY in actor.spec:actor.spec[KEY]['tag']=None


def _has_method(pokemon):
    import ability_transitions as AB
    return AB.active(pokemon,TOLERANCE) or AB.active(pokemon,EXPLOIT)


def after_order(engine,trainer,targets,origin):
    if not acquired(trainer,DIRECTED):return
    for pokemon in dict.fromkeys(targets):
        if owner(engine,pokemon) is trainer and _has_method(pokemon):gain(engine,pokemon,{'kind':'order','activation':deepcopy(origin)})


def observe_damage(engine,attacker,target,move,event,receipt):
    if event.get('damage_formula',{}).get('multiplier',0)<=1 or receipt.get('requested',0)<=0:return
    token=getattr(engine,'_defense_recipient_scope',None)
    for row in getattr(engine,'_move_completions',{}).values():
        if row['actor'] is attacker and row['move_id']==move['id'] and row['phase']=='targets':
            if token is None:
                if target not in row['targets']:continue
            else:
                import move_defense_reactions as DEFENSE
                if engine._passive_events[token[0]]['completion_id']!=row['id']:continue
                DEFENSE.require_recipient(engine,token,attacker,target,move,row['id'])
            ids=row.setdefault('duelist_super_effective',[])
            for pokemon in (attacker,target):
                if _owner(engine,pokemon,DIRECTED) and _has_method(pokemon) and pokemon.entity_id not in ids:ids.append(pokemon.entity_id)
            return


def after_move(engine,row):
    if row['phase']!='complete' or row.get('duelist_done'):return
    row['duelist_done']=True
    import world_entities as W,move_completion as COMPLETE
    pokemon=row['actor'];index=W.actor_index(engine)
    hits=[]
    for target in COMPLETE.actual_recipients(row):
        outcome=COMPLETE.recipient_result(row,target)
        if not outcome['hit'] or outcome['cancelled'] or outcome.get('hit_prevented'):continue
        hits.append(target)
        if tagged(engine,pokemon,target):
            gain(engine,pokemon,{'kind':'tag_hit','completion':row['id'],'target':target.entity_id})
    for uid in row.get('duelist_super_effective',[]):
        gain(engine,index[uid],{'kind':'super_effective','completion':row['id']})
    manual=row.get('duelist_manual')
    if manual is not None:
        for target in hits:
            count=TIME.current(engine)
            TIME.install(engine,target,{'source':MANUAL,'statuses':['취약'],'count_deadline':[engine.round_no+1,count]})
            TIME.install(engine,target,{'source':MANUAL,'initiative_zero':True,'turn_owner':target,
                'turn_deadline':target.custom_conditions.get('combat_turn_serial',0)+1})
        record=next((r for r in TIME.records(pokemon) if r.get('duelist_use')==manual),None)
        if record:TIME.expire(engine,pokemon,record,ending='consumed')
    interrupt=row.get('duelist_interrupt')
    if interrupt is not None:
        _,overflow=overflow_trigger(engine,interrupt)
        if hits and row.get('duelist_already_critical') and not overflow.get('heal_applied'):
            import life
            overflow['heal_applied']=True
            overflow['healed']=life.heal(engine,pokemon,NUMERIC.ratio(pokemon.base_max_hp,2),source_kind='feature')
        if overflow.get('suspended'):
            # The native continuation has now completed the already paid Move.
            import initiative_interrupts as I
            I.finish(engine)
            overflow_trigger(engine,interrupt)[1]['status']='completed'


def ability_hit(engine,pokemon,target,source,receipt):
    if tagged(engine,pokemon,target):gain(engine,pokemon,{'kind':'ability_hit','source':source,'receipt':receipt})


def _quota(engine,actor,source,uses):
    frequency={'kind':'scene','uses':uses}
    if not F.activation_allowed(actor,source,frequency,engine=engine):raise ValueError('printed per-Scene quota exhausted')
    return frequency


def _target(engine,trainer,pokemon,feature):
    import world_entities as W
    W.require_actors(engine,trainer,pokemon)
    if not acquired(trainer,feature) or _owner(engine,pokemon) is not trainer or not focused(pokemon,trainer):
        raise ValueError('actual owned Pokemon under this Duelist Focused Training required')
    if pokemon.fainted or not pokemon.on_field:raise ValueError('conscious present Pokemon required')


def _use(engine,trainer,pokemon,feature,mode):
    row={'id':feature+':'+trainer.entity_id+':'+str(len(trainer.spec.get(USES,[]))+1),
         'source':feature,'trainer_id':trainer.entity_id,'pokemon_id':pokemon.entity_id,
         'mode':mode,'scene':F.state(pokemon)['scene'],'round':engine.round_no,
         'momentum':momentum(pokemon),'acquisition':acquired(trainer,feature)['request_id']}
    trainer.spec.setdefault(USES,[]).append(row)
    return row


def _pay_order(e,a,p,feature,communication=None):
    import moment_of_action as MOMENT,order_actions as ORDERS
    use_id=feature+':'+a.entity_id+':'+str(len(a.spec.get(USES,[]))+1)
    request,delivery=MOMENT._communication(e,a,p,use_id,communication,source=feature,label='Duelist Order')
    payment=ORDERS.spend(e,a,feature,subject=use_id,communication=delivery)
    return request,delivery,payment


def _finish_order(e,a,p,row,paid):
    import cheerleader as CHEER
    import trainer_feature_acquisition as TFA
    import moment_of_action as MOMENT
    import order_actions as ORDERS
    request,delivery,payment=paid
    if payment.get('kind')=='free_order':row['free_order_payment']=payment
    elif payment.get('kind')=='priority_limited':row['priority_receipt_id']=payment['id']
    row['communication']={'request_id':request,'result':delivery};row['at']=e.elapsed_seconds
    row['integrity']=TFA._digest('duelist/use/v1',row)
    CHEER.issue(e,a,[p],{'kind':'duelist_order','source':row['source'],'use_id':row['id']})
    after_order(e,a,[p],{'kind':'duelist','use_id':row['id']})
    return deepcopy(row)


def expend(engine,trainer,pokemon,*,amount,move=None,communication=None):
    C.integer(amount,'Momentum expense',1,3)
    move=engine.r.move_id(move) if move is not None else None
    def apply(e,a,p):
        import turn as TURN,move_state as MOVES
        _target(e,a,p,EXPEND)
        if momentum(p)<amount:raise ValueError('insufficient Momentum')
        quota=_quota(e,p,EXPEND,1) if amount==3 else None
        if amount!=2:
            if move not in MOVES.known(e.r,{'moves':MOVES.owned_list(p.spec,'moves',p.moves,rules=p.r)}) or F.move_frequency(e,move,p)[0]!=('every_other_turn' if amount==1 else 'scene'):
                raise ValueError('one known Move of the printed frequency required')
            if not p.move_uses.get(move):raise ValueError('selected Move has no spent use to restore')
        elif move is not None:raise ValueError('the d20 option does not restore a Move')
        paid=_pay_order(e,a,p,EXPEND,communication)
        row=_use(e,a,p,EXPEND,amount);_change(e,p,momentum(p)-amount)
        if quota:F.consume_activation(p,EXPEND,quota,engine=e)
        if amount==2:
            TIME.install(e,p,{'source':EXPEND,'duelist_eleven':True,'duelist_use':row['id'],
                'turn_owner':p,'turn_deadline':p.custom_conditions.get('combat_turn_serial',0)+1})
        else:
            p.move_uses[move]=max(0,p.move_uses[move]-1);p.spec['move_uses']=dict(p.move_uses)
            F.state(p)['moves'].pop(move,None)
            if p.last_move==move:p.last_move=None
            row['move_id']=move
        return _finish_order(e,a,p,row,paid)
    return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def choose_eleven(engine,pokemon,kind):
    if engine._active_turn_actor is not pokemon:return False
    serial=pokemon.custom_conditions.get('combat_turn_serial',0)
    records=[r for r in TIME.records(pokemon) if r.get('duelist_eleven') and __import__('native_order_transfer').on_eligible_turn(engine,pokemon,r,r['turn_deadline'])]
    if not records:return False
    choice=engine.rulings.decide({'type':'duelist_eleven','unit':EXPEND,'actor':pokemon.name,'roll':kind,
        'text':'Use one Expend Momentum automatic 11 on this actual d20 roll?'})
    if choice is not None and type(choice) is not bool:raise ValueError('choose whether to use the automatic 11')
    if choice is not True:return False
    TIME.expire(engine,pokemon,records[0],ending='consumed');return True


def manual(engine,trainer,pokemon,*,mode,ability=None,communication=None):
    C.integer(mode,'Manual option',1,3)
    def apply(e,a,p):
        import turn as TURN,action_points as AP,ability_transitions as AB
        _target(e,a,p,MANUAL)
        if momentum(p)<mode:raise ValueError('Manual requires its Momentum threshold without spending it')
        if any(r.get('source')==MANUAL and r.get('duelist_mode')==mode for r in TIME.records(p)):
            raise ValueError('this Manual option is already active')
        quota=_quota(e,p,MANUAL,1) if mode==3 else None
        operation=None
        if mode==1:
            pool=[uid for uid in (TOLERANCE,EXPLOIT) if AB.active(p,uid)]
            if not pool:raise ValueError('actual Tolerance or Exploit required')
            if ability is not None:
                chosen=AB.ability_id(e.r,ability)
                if chosen not in (TOLERANCE,EXPLOIT):raise ValueError('Manual only exchanges Tolerance and Exploit')
                old=EXPLOIT if chosen==TOLERANCE else TOLERANCE
                if old not in pool:raise ValueError('actual exchanged Ability required')
                operation={'kind':'replace','remove':[old],'add':[chosen]}
        elif ability is not None:raise ValueError('only the first Manual option exchanges an Ability')
        if AP.available(a)<2:raise ValueError('Manual requires two AP')
        paid=_pay_order(e,a,p,MANUAL,communication)
        a.ap_account.charge(2,mode='spend');row=_use(e,a,p,MANUAL,mode)
        if quota:F.consume_activation(p,MANUAL,quota,engine=e)
        record={'source':MANUAL,'duelist_mode':mode,'duelist_use':row['id']}
        if mode in (1,3):record.update(turn_owner=p,turn_deadline=p.custom_conditions.get('combat_turn_serial',0)+1)
        if operation:
            source=row['id']+':ability'
            G._source(p,source,'effect',owner_id=a.entity_id,rule_id=MANUAL,duelist_manual=row['id'],ability_operation=operation)
            record['grant_source']=source
            row['ability_operation']=deepcopy(operation)
        TIME.install(e,p,record)
        if operation:G.materialize(p,'abilities');G.reconcile(e,p)
        return _finish_order(e,a,p,row,paid)
    return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def method_multiplier(pokemon):return 2 if any(r.get('duelist_mode')==1 for r in TIME.records(pokemon)) else 1


def operation_mode(actor,source):
    if source!=MANUAL:return None
    if not any(r.get('duelist_mode')==1 and r.get('grant_source') for r in TIME.records(actor)):
        raise ValueError('Manual exchange requires its actual timed producer')
    return 'replace'


def range_spec(engine,pokemon,move,result):
    if pokemon is None or move.get('class') not in ('물리','특수'):return result
    records=[r for r in TIME.records(pokemon) if r.get('duelist_mode')==2]
    if not records:return result
    shape=result.get('shape');raw=result.get('raw',move.get('range',''))
    if shape not in ('pass','cone','burst','blast','close_blast','line') and not any(x in raw for x in ('통과','Pass')):return result
    ranged=shape=='line' or shape=='blast' and result.get('origin') not in (None,'self','melee')
    origin=result.get('origin') if ranged else 'melee'
    if ranged and not isinstance(origin,int):origin=result.get('size')
    if ranged and (type(origin) is not int or origin<1):raise ValueError('Manual ranged conversion needs its actual printed range')
    return {'origin':origin,'targets':1,'parsed':True,'raw':str(origin)+', 대상 1','duelist_use':records[0]['duelist_use']}


def begin_move(engine,row):
    import weapon_actions as W
    rng=W.range_spec(engine,row['move'],row['actor'])
    if rng.get('duelist_use'):row['duelist_manual']=rng['duelist_use']
    interrupt=interrupt_attack(engine,row['actor'],row['targets'][0],row['move'])
    if interrupt is not None:row['duelist_interrupt']=interrupt['id']


def ignores(engine,pokemon,target=None):
    if engine._active_turn_actor is not pokemon:return False
    serial=pokemon.custom_conditions.get('combat_turn_serial',0)
    active=any(r.get('duelist_mode')==3 and __import__('native_order_transfer').on_eligible_turn(engine,pokemon,r,r.get('turn_deadline')) for r in TIME.records(pokemon))
    if not active:return False
    if target is not None:return tagged(engine,pokemon,target)
    return getattr(pokemon,'_duelist_ignoring',False)


def attack_scope(fn):
    from functools import wraps
    @wraps(fn)
    def run(engine,attacker,target,*args,**kwargs):
        move_id=args[0] if args else kwargs.get('move_id')
        if move_id is not None:interrupt_attack(engine,attacker,target,engine.r.move(move_id))
        previous=getattr(attacker,'_duelist_ignoring',False)
        attacker._duelist_ignoring=ignores(engine,attacker,target)
        try:return fn(engine,attacker,target,*args,**kwargs)
        finally:
            if previous:attacker._duelist_ignoring=previous
            elif hasattr(attacker,'_duelist_ignoring'):del attacker._duelist_ignoring
    return run


def type_steps(engine,attacker,target,move,mult):
    import ability_transitions as AB,action_lifecycle as ACTION
    choices=[]
    for pokemon,foe,uid,condition,step in ((target,attacker,TOLERANCE,mult>1,1),(attacker,target,EXPLOIT,0<mult<1,-1)):
        trainer=_owner(engine,pokemon,TYPE)
        if not condition or trainer is None or momentum(pokemon)<2 or not tagged(engine,pokemon,foe) or not AB.active(pokemon,uid):continue
        if not F.activation_allowed(trainer,TYPE,{'kind':'scene','uses':2},engine=engine):continue
        choice=engine.rulings.decide({'type':'type_methodology','unit':TYPE,'actor':trainer.name,
            'pokemon':pokemon.name,'move':move['id'],'text':'Spend two Momentum to shift this actual attack one effectiveness step?'})
        if choice is not None and type(choice) is not bool:raise ValueError('choose whether to use Type Methodology')
        if choice is True:
            ACTION.triggered_free_action(engine,trainer,TYPE)
            F.consume_activation(trainer,TYPE,{'kind':'scene','uses':2},engine=engine)
            _change(engine,pokemon,momentum(pokemon)-2);choices.append(step)
    return sum(choices)


def _offer_seize(engine,trainer,pokemon,row):
    if not F.activation_allowed(trainer,SEIZE,{'kind':'scene','uses':2},engine=engine) or not F.activation_allowed(pokemon,SEIZE,{'kind':'scene','uses':1},engine=engine):return
    if trainer.spec.get(KEY,{}).get('tag') is None:return
    row['status']='pending'


def pending(engine,trainer):
    import world_entities as W
    return [deepcopy(row) for p in W.actor_index(engine).values() if owner(engine,p) is trainer
            for row in p.spec.get(KEY,{}).get('gains',[]) if row['status']=='pending']


def overflow_trigger(engine,identity,*,allow_completed=False):
    import world_entities as W
    found=[(p,row) for p in W.actor_index(engine).values() for row in p.spec.get(KEY,{}).get('gains',[]) if row['id']==identity]
    if len(found)!=1:raise ValueError('actual Momentum overflow event required')
    pokemon,row=found[0]
    historical=allow_completed and row['status']=='completed' and row['round']<=engine.round_no
    if row.get('integrity')!=_gain_seal(row) or row['before']!=6 or (row['round']!=engine.round_no and not historical) or row['status'] not in (('pending','interrupt','completed') if allow_completed else ('interrupt',)):
        raise ValueError('current actual overflow Interrupt authority required')
    return pokemon,row


def validate_interrupt(engine,trigger,request):
    pokemon,row=overflow_trigger(engine,trigger['overflow_id'],allow_completed=True)
    if request['actor'] is not pokemon or request['source']!=SEIZE or request['move_id']!=row.get('move_id') or request['mode']!='duelist_interrupt':
        raise ValueError('Seize Interrupt must retain its actual Pokemon and selected Move')


def seize(engine,trainer,pokemon,*,event_id,move,target,**options):
    import initiative_interrupts as I,action_lifecycle as ACTION,world_entities as W,move_state as MOVES
    W.require_actors(engine,trainer,pokemon,target)
    move=engine.r.move_id(move)
    pending=[]
    def apply(e,a,p,t):
        if _owner(e,p,SEIZE) is not a or not tagged(e,p,t):raise ValueError('Seize attacks only this Duelist tagged foe')
        actual,row=overflow_trigger(e,event_id,allow_completed=True)
        if actual is not p or row['status']!='pending' or momentum(p)!=6:raise ValueError('unspent actual overflow required')
        if move not in MOVES.known(e.r,{'moves':MOVES.owned_list(p.spec,'moves',p.moves,rules=p.r)}):raise ValueError('actual known attack required')
        import exhaust_moves as EXHAUST
        if not EXHAUST.preflight(e,p,e.r.move(move),count_use=True):raise ValueError('selected Exhaust Move requires its actual unspent action eligibility')
        q=_quota(e,a,SEIZE,2);pq=_quota(e,p,SEIZE,1)
        ACTION.triggered_free_action(e,a,SEIZE)
        F.consume_activation(a,SEIZE,q,engine=e);F.consume_activation(p,SEIZE,pq,engine=e)
        row.update(status='interrupt',move_id=move,target_id=t.entity_id)
        _change(e,p,1)
        request={'id':event_id,'actor_id':p.entity_id,'source':SEIZE,'priority':0,'mode':'duelist_interrupt',
                 'payment':'none','budget':{'standard':1},'clock':'none','move_id':move}
        queued=I.queue(e,[request],trigger={'kind':'duelist_overflow','overflow_id':event_id})
        I.begin(e,queued['window_id'],event_id)
        try:result=e.use_move(p,t,move,**options)
        except Exception as error:
            if not G.record_native_pending(e,error,pending):raise
            overflow_trigger(e,event_id)[1]['suspended']=True
            return None
        I.finish(e)
        overflow_trigger(e,event_id,allow_completed=True)[1]['status']='completed'
        return result
    def scoped(e,a,p,t):
        _,receipt=overflow_trigger(e,event_id,allow_completed=True)
        parent=getattr(e,'_move_completions',{}).get(receipt.get('origin',{}).get('completion'))
        with ACTION.completion_reaction(e,a,SEIZE,parent,receipt=receipt):
            return apply(e,a,p,t)
    result=G.transition(engine,trainer,scoped,participants=(pokemon,target),include_rulings=True,include_grid=engine.grid is not None)
    if pending:raise pending[0][0](pending[0][1])
    return result


def interrupt_attack(engine,pokemon,target,move):
    import initiative_interrupts as I
    selected=I.selected_move_frame(engine,pokemon)
    if selected is None or selected[1]['source']!=SEIZE:return None
    window=getattr(engine,I.KEY)['windows'][selected[0]['window_id']]
    _,row=overflow_trigger(engine,window['trigger']['overflow_id'],allow_completed=True)
    if target.entity_id!=row['target_id'] or move['id']!=row['move_id']:raise ValueError('Seize is a single tagged-foe attack')
    return row


def interested(engine,actor):
    return bool(acquired(actor) if actor.kind=='trainer' else _owner(engine,actor))


def decline(engine,trainer,pokemon,event_id):
    if owner(engine,pokemon) is not trainer:raise ValueError('actual overflow Pokemon owner required')
    def apply(e,a,p):
        actual,row=overflow_trigger(e,event_id,allow_completed=True)
        if actual is not p or row['status']!='pending':raise ValueError('unresolved actual overflow required')
        row['status']='declined'
        return {'event_id':event_id,'status':'declined'}
    return G.transition(engine,trainer,apply,participants=(pokemon,))


def critical(engine,pokemon,target,move,hit,crit):
    row=interrupt_attack(engine,pokemon,target,move)
    if row is None or not hit:return crit
    if crit:
        # Original accuracy alone cannot prove the eventual recipient was hit.
        for completion in getattr(engine,'_move_completions',{}).values():
            if completion.get('duelist_interrupt')==row['id'] and completion['phase']=='targets':
                completion['duelist_already_critical']=True
    return True


def smite(engine,pokemon,target,move,set_damage):
    if interrupt_attack(engine,pokemon,target,move) is None or move.get('class') not in ('물리','특수'):return 0
    import attack_damage_history as HISTORY,arithmetic_policy as M
    event={'attacker':pokemon,'target':target,'move':move}
    amount=M.ratio(engine.roll_damage(pokemon,target,move,False,set_damage,_reaction_event=event),2)
    receipt=HISTORY.apply_smite(engine,pokemon,target,move,amount,event.get('actual_damage_type',move['type']))
    observe_damage(engine,pokemon,target,move,event,receipt)
    return amount


def validate_world(engine,index):
    import trainer_feature_acquisition as TFA
    for actor in index.values():
        momentum(actor)
        for row in actor.spec.get(USES,[]):
            if row.get('integrity')!=TFA._digest('duelist/use/v1',{k:v for k,v in row.items() if k!='integrity'}):raise ValueError('Duelist Order producer receipt changed')
            if actor.kind!='trainer' or row['trainer_id']!=actor.entity_id or row['source'] not in (EXPEND,MANUAL) or row['pokemon_id'] not in index:raise ValueError('actual Duelist Order producer and recipient required')
            if len([r for _,r,_ in TFA._static_records(actor) if r['static_acquisition']['request_id']==row['acquisition'] and r['static_acquisition']['feature_id']==row['source']])!=1:raise ValueError('historical Duelist acquisition required')
            if row['momentum']<row['mode']:raise ValueError('actual Momentum threshold required')
            if row.get('free_order_payment') is not None:
                import order_actions as ORDERS
                ORDERS.validate(engine,actor,index[row['pokemon_id']],row['source'],row['free_order_payment'])
            if row.get('priority_receipt_id') is not None:
                import priority_limited as PRIORITY
                paid=[r for r in PRIORITY.records(actor) if r['id']==row['priority_receipt_id']]
                if (len(paid)!=1 or paid[0]['source']!=row['source'] or paid[0]['subject_id']!=row['id']
                        or paid[0]['payment']['funded']!={'standard':1} or paid[0]['communication']!=row['communication']['result']):
                    raise ValueError('Duelist Order lost its native Standard reservation')
            import moment_of_action as MOMENT
            delivered=row['communication']
            if MOMENT._delivery(engine,actor.entity_id,row['pokemon_id'],delivered['request_id'],row['at'])!=delivered['result']:
                raise ValueError('actual Duelist Order delivery required')
        for record in TIME.records(actor):
            use=record.get('duelist_use')
            if use is None:continue
            found=[(trainer,row) for trainer in index.values() for row in trainer.spec.get(USES,[]) if row['id']==use]
            if len(found)!=1 or found[0][1]['pokemon_id']!=__import__('native_order_transfer').origin_id(record,actor):raise ValueError('actual Duelist timed Order producer required')
            trainer,row=found[0]
            if record['source']!=row['source']:raise ValueError('Duelist effect source changed')
            if record.get('grant_source'):
                receipt=actor.spec.get(G.KEY,{}).get('sources',{}).get(record['grant_source'],{})
                if receipt.get('duelist_manual')!=use or receipt.get('ability_operation')!=row.get('ability_operation'):raise ValueError('Manual exchange must retain its actual source-owned Ability operation')
        state=actor.spec.get(KEY)
        if state is None:continue
        if type(state) is not dict or set(state)!={'tag','gains'} or type(state['gains']) is not list:raise ValueError('native Duelist state required')
        if state['tag'] is not None and (actor.kind!='trainer' or state['tag'] not in index):raise ValueError('actual single tagged foe required')
        for serial,row in enumerate(state['gains'],1):
            if row['id']!='momentum:'+actor.entity_id+':'+str(serial) or row['status'] not in ('gained','pending','interrupt','completed','expired','declined'):
                raise ValueError('native Momentum event identity required')
            C.integer(row['before'],'Momentum before actual gain',0,6)
            if row.get('integrity')!=_gain_seal(row):raise ValueError('actual Momentum producer observation changed')
    return True


def _gain_seal(row):
    import trainer_feature_acquisition as TFA
    return TFA._digest('duelist/gain/v1',{key:row[key] for key in ('id','origin','before','round','scene')})


def completion_reaction_origin(engine,actor,source,completion,receipt):
    if source!=SEIZE:return False
    if not isinstance(receipt,dict):raise ValueError('actual Seize overflow receipt required')
    pokemon,actual=overflow_trigger(engine,receipt['id'],allow_completed=True)
    if actual is not receipt or _owner(engine,pokemon,SEIZE) is not actor or receipt['origin'].get('completion')!=completion['id']:
        raise ValueError('Seize must retain its actual completed hit origin')
    return True
