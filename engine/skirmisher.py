"""Skirmisher source adapters over native acquisitions, attacks and maneuvers."""
from copy import deepcopy
from functools import wraps
from hashlib import sha256
from pathlib import Path
import csv
import json
import state_grants as G
import world_entities as W

CLASS='supp-fantasy/척후'
NIMBLE='feat/날렵한-움직임'; COUNTER='feat/반격-자세'; HARRIER='feat/해리어'
FINESSE='feat/무기-수완'; OUT='feat/허찌르기'; SWIFT='feat/신속-공격'
FLUTTER='ability/파닥파닥'; VANGUARD='ability/선봉'
BOOK_SHA='a51f5d6592bc1ff12b380f47398db93426b53c58c210810f5041b29eb64b2266'
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
FEATURES={CLASS:(847,849),NIMBLE:(851,855),COUNTER:(857,862),HARRIER:(864,869),FINESSE:(871,876),OUT:(878,883),SWIFT:(885,889)}
CSV_ROWS={u:580+i for i,u in enumerate(FEATURES)}
CLAUSES={u:'FAN-'+str(110+i) for i,u in enumerate(FEATURES)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[838,890] if u==CLASS else list(s),
    'clause_id':CLAUSES[u],'class_template':CLASS,'minimum_level':0,'skill':None,
    'source':{'file':'input/supp-fantasy.md','sha256':BOOK_SHA}} for u,s in FEATURES.items()}
ARM='skirmisher_attack_choice'; FINESSE_STATE='skirmisher_finesse'; COUNTER_STATE='skirmisher_counter'


def records(actor,feature=None,active=False):
    return [r for _,r in __import__('trainer_feature_acquisition').static_family_acquisitions(actor,FEATURES,feature,active=active)]


def acquired(actor,feature):
    rows=records(actor,feature,True)
    return rows[-1] if rows else None


def source(rules,feature,edition):
    from source_context import verified_source
    if feature not in FEATURES or edition not in ('supplement','local_csv'):raise ValueError('exact Skirmisher source edition required')
    if rules._selected_rule(feature)!=feature or feature in rules.ruleset.unit_versions:raise ValueError('selected Skirmisher source needs its own adapter')
    verified_source(rules,{'file':'input/supp-fantasy.md','sha256':BOOK_SHA},label='Skirmisher supplement')
    result={'edition':edition,'file':'input/supp-fantasy.md','sha256':BOOK_SHA,'span':list(FEATURES[feature])}
    if edition=='local_csv':
        verified_source(rules,{'file':'input/db/feats.csv','sha256':CSV_SHA},label='Skirmisher CSV')
        row=CSV_ROWS[feature]
        with (Path(rules.root)/'input/db/feats.csv').open(encoding='utf-8-sig',newline='') as stream:cells=list(csv.reader(stream))[row-1]
        rules.ruleset.require({'id':'C2CSV/input/db/feats.csv:R'+str(row)+':main','source':{'file':'db/feats.csv','record_span':[row,row]}})
        result.update(file='input/db/feats.csv',sha256=CSV_SHA,row=row,cells_sha256=sha256(json.dumps(cells,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
    return result


def static_source(rules,feature):
    source(rules,feature,'supplement')
    unit=rules.selection.units[feature]['source']
    if unit.get('file')!='supp-fantasy.md' or unit.get('lines')!=DEFINITIONS[feature]['catalog_span']:raise ValueError('exact Skirmisher catalog span required')
    return {'file':'input/supp-fantasy.md','sha256':BOOK_SHA,'clause_id':CLAUSES[feature],'span':list(FEATURES[feature])}


def validate_selection(feature,rank,selection):
    extra={CLASS:'ability',COUNTER:'counter_cost',FINESSE:'trigger_scope'}.get(feature)
    if rank is not None or type(selection)is not dict or set(selection)!=({'edition',extra} if extra else {'edition'}):raise ValueError('explicit Skirmisher edition and printed source choice required')
    if feature==CLASS and selection['ability'] not in (FLUTTER,VANGUARD):raise ValueError('choose Flutter or Vanguard explicitly')
    if feature==COUNTER and selection['counter_cost'] not in ('korean_full','english_free'):raise ValueError('select the S-001 Counter Stance action cost')
    if feature==FINESSE and selection['trigger_scope'] not in ('korean_damaging','english_weapon'):raise ValueError('select the S-001 Weapon Finesse trigger scope')


def acquisition_snapshot(e,actor,feature,rank,selection):
    import skill_modifiers as S,acquired_features as A
    validate_selection(feature,rank,selection)
    parent={CLASS:None,NIMBLE:CLASS,COUNTER:CLASS,HARRIER:CLASS,FINESSE:COUNTER,OUT:HARRIER,SWIFT:CLASS}[feature]
    return {'selection':deepcopy(selection),'source':source(e.r,feature,selection['edition']),
        'combat':S.rank(e.r,actor,'전투')[2],'acrobatics':S.rank(e.r,actor,'곡예')[2],
        'parent_owned':parent is None or bool(A.owned_rule_count(actor,parent)),
        'feature_count':sum(bool(A.owned_rule_count(actor,u)) for u in FEATURES)}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q,common_checks as C
    s=snapshot
    if prerequisite_source is not None or type(s)is not dict or set(s)!={'selection','source','combat','acrobatics','parent_owned','feature_count'}:raise ValueError('exact Skirmisher acquisition observations required')
    validate_selection(feature,None,s['selection'])
    if s['source']!=source(actor.r,feature,s['selection']['edition']):raise ValueError('Skirmisher acquisition source changed')
    for key in ('combat','acrobatics','feature_count'):C.integer(s[key],'actual acquired '+key,0)
    if type(s['parent_owned'])is not bool:raise ValueError('actual Skirmisher parent observation required')
    skill=(s['combat']>=3 and s['acrobatics']>=3) if feature==CLASS else max(s['combat'],s['acrobatics'])>={NIMBLE:0,COUNTER:0,HARRIER:0,FINESSE:4,OUT:4,SWIFT:6}[feature]
    return Q.require(feature,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('parent','prerequisite',s['parent_owned'],'actual Skirmisher prerequisite required'),
        Q.check('skills','prerequisite',skill,'printed Skirmisher skill ranks required'),
        Q.check('features','prerequisite',feature!=SWIFT or s['feature_count']>=4,'Swift Strikes requires four actual Skirmisher Features')])


def after_acquire(e,actor,feature,sid):
    G.stat(actor,'spe',1,sid,operation_id='acquisition_stat_tag')
    if feature==CLASS:
        uid=acquired(actor,CLASS)['snapshot']['selection']['ability'];name={FLUTTER:'파닥파닥',VANGUARD:'선봉'}[uid]
        if e.r.selection.resolve_name(name,('ability/',))!=uid:raise ValueError('actual Skirmisher Ability identity required')
        G.grant(actor,'abilities',name,sid,'feature',owner_id=actor.entity_id,lifetime='while_owned',rule_id=feature)
        e.register_abilities_one(actor,name)


def validate_acquisition(actor,record,sid,active):
    if active and actor.spec.get(G.KEY,{}).get('stat_sources',{}).get('spe',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:raise ValueError('actual Skirmisher Speed tag required')


def require(e,actor,feature):
    W.require_actors(e,actor)
    row=acquired(actor,feature)
    if row is None or not __import__('acquired_features').owned_rule_count(actor,feature):raise ValueError('actual acquired Skirmisher Feature required: '+feature)
    source(e.r,feature,row['snapshot']['selection']['edition'])
    __import__('trainer_feature_acquisition').validate_actor(actor)
    if actor.fainted or actor.dead or actor.captured or not actor.on_field:raise ValueError('available actual Skirmisher required')
    return row


def nimble(e,actor):
    choice=getattr(e,'_skirmisher_disengage',None)
    if choice and choice[0] is actor and not choice[1]:return False
    return bool(acquired(actor,NIMBLE) and require(e,actor,NIMBLE))


def disengage(e,actor,destination,*,as_swift):
    if type(as_swift)is not bool:raise ValueError('explicit Nimble Steps action selection required')
    if as_swift:require(e,actor,NIMBLE)
    e._skirmisher_disengage=(actor,as_swift)
    try:return e.disengage(actor,destination)
    finally:del e._skirmisher_disengage


def _ability(e,actor,uid):
    import ability_transitions as A
    name={FLUTTER:'파닥파닥',VANGUARD:'선봉'}[uid]
    return uid in A.known(actor) and A.active(actor,name)


def flutter(e,actor,target=None):
    if target is not None and target is not actor:raise ValueError('Flutter targets only its actual user')
    W.require_actors(e,actor)
    if not _ability(e,actor,FLUTTER):raise ValueError('actual active Flutter Ability required')
    def apply(se,a):
        import turn as T,combat_timing as TIME
        if not T.spend(se,a,'shift',FLUTTER):raise ValueError('Flutter requires an available Shift Action')
        for row in list(TIME.records(a)):
            if row.get('source')==FLUTTER:TIME.expire(se,a,row,ending='replaced')
        result=se.apply_effect(a,a,{'type':'evasion_mod','value':3,'target':'self',
            'until':"end of user's next turn"},None,True,0,FLUTTER)
        if result.pending:raise ValueError('actual Flutter Evasion producer must resolve')
        row=next(r for r in reversed(TIME.records(a)) if r.get('source')==FLUTTER)
        row['skirmisher_unflanked']=True
        return row
    return G.transition(e,actor,apply,include_rulings=True)


def flanking(actor):
    import combat_timing as TIME
    if any(r.get('skirmisher_unflanked') for r in TIME.records(actor)):return False
    if any(r.get('skirmisher_flanked') for r in TIME.records(actor)):return True
    return None


def require_keyword(actor,kind):
    if any(kind in r.get('skirmisher_forbidden',[]) for r in __import__('combat_timing').records(actor)):
        raise ValueError('Harrier forbids Priority and Interrupt actions')


def vanguard_bonus(e,actor,target):
    if not _ability(e,actor,VANGUARD) or e._ordinary_turn_rounds.get(target)==e.round_no:return 0
    import initiative as I
    left=I.value(e.r,actor,engine=e);right=I.value(e.r,target,engine=e)
    if left.value is None or right.value is None:raise ValueError('Vanguard requires actual resolved Initiative values')
    return 5 if right.value<left.value else 0


def after_move(e,row):
    import frequency as F,move_completion as MC,combat_timing as TIME
    a=row['actor']
    row['skirmisher_boundary']={'round':e.round_no,'seconds':e.elapsed_seconds,
        'serial':a.custom_conditions.get('combat_turn_serial',0),'scene':F.state(a)['scene'],
        'history':list(getattr(a,'_action_history',[]))}
    selected=row.get('skirmisher_attack')
    if not selected or not selected['outmaneuver'] or row.get('skirmisher_out_applied'):return
    row['skirmisher_out_applied']=True
    for target in MC.actual_recipients(row):
        result=MC.recipient_result(row,target)
        if target.side==a.side or not result['hit'] or result.get('cancelled') or result.get('hit_prevented'):continue
        result=e.apply_effect(a,target,{'type':'initiative','delta':-selected['evasion'],
            'target':'target','until':'scene_end'},None,True,0,OUT)
        if result.pending:raise ValueError('actual Outmaneuver Initiative producer must resolve')


def completed(e,actor,target,completion_id,*,miss=False,resuming=False):
    import move_completion as MC,frequency as F
    W.require_actors(e,actor,target)
    row=getattr(e,MC.KEY,{}).get(completion_id)
    if row is None or row['phase']!='complete' or not row['sealed'] or row['actor'] is not actor:raise ValueError('actual completed Skirmisher trigger attack required')
    result=MC.recipient_result(row,target)
    if target not in MC.actual_recipients(row) or result is None or result.get('cancelled') or result.get('hit_prevented') or result['hit'] is miss:raise ValueError('actual nonprevented miss' if miss else 'actual nonprevented hit required')
    b=row.get('skirmisher_boundary',{})
    if b.get('round')!=e.round_no or b.get('seconds')!=e.elapsed_seconds or b.get('serial')!=actor.custom_conditions.get('combat_turn_serial',0) or b.get('scene')!=F.state(actor)['scene']:raise ValueError('immediate current attack completion required')
    if not resuming and b.get('history')!=list(getattr(actor,'_action_history',[])):raise ValueError('immediate attack follow-up cannot follow another action')
    if actor.side==target.side:raise ValueError('actual enemy trigger required')
    routed=row.get('received',{}).get(target.entity_id)
    move=MC.event_move(e,e._passive_events[routed['child_event']]) if routed else row.get('target_moves',{}).get(target.entity_id,row['move'])
    return row,move


def harrier(e,actor,target,completion_id):
    require(e,actor,HARRIER)
    def apply(se,a,t):
        import combat_timing as TIME,frequency as F,action_lifecycle as A
        row,move=completed(se,a,t,completion_id)
        if move.get('class') not in ('물리','특수'):raise ValueError('Harrier requires a damaging Attack hit')
        quota={'kind':'scene','uses':1};key=HARRIER+':'+t.entity_id
        if not F.activation_allowed(a,key,quota,engine=se):raise ValueError('Harrier once per foe per Scene exhausted')
        A.triggered_free_action(se,a,HARRIER);F.consume_activation(a,key,quota,engine=se)
        record={'source':HARRIER,'origin_completion':row['id'],'turn_owner':a,
            'turn_deadline':a.custom_conditions.get('combat_turn_serial',0)+1,'encounter_end':True,
            'statuses':['둔화'],'skirmisher_flanked':True,'skirmisher_forbidden':['priority','interrupt']}
        return __import__('combat_maneuvers')._install_from_actor(se,a,t,record)
    return G.transition(e,actor,apply,participants=(target,),include_rulings=True)


def arm_attack(e,actor,move_id,*,weapon_id=None,outmaneuver=False,swift=False,evasion_class='물리'):
    if type(outmaneuver)is not bool or type(swift)is not bool or not (outmaneuver or swift):raise ValueError('explicit Skirmisher attack selection required')
    if evasion_class not in ('물리','특수','변화'):raise ValueError('select an actual Physical, Special or Speed Evasion')
    W.require_actors(e,actor)
    mid=e.r.move_id(move_id);move=__import__('weapon_actions').prepare(e,actor,e.r.move(mid),weapon_id)
    if move.get('class') not in ('물리','특수'):raise ValueError('Skirmisher attack choice requires a damaging Attack')
    if outmaneuver:require(e,actor,OUT)
    if swift:
        require(e,actor,SWIFT)
        if not move.get('_weapon_attack'):raise ValueError('Swift Strikes requires an actual equipped Weapon Attack')
    data={'move_id':mid,'weapon_id':move.get('_weapon_attack',{}).get('key'),
        'outmaneuver':outmaneuver,'swift':swift,'evasion_class':evasion_class}
    return G.transition(e,actor,lambda se,a:a.spec.update({ARM:deepcopy(data)}))


def prepare_move(e,actor,move):
    if any('priority' in r.get('skirmisher_forbidden',[]) for r in __import__('combat_timing').records(actor)):
        __import__('turn').has_priority(e,actor,move)
    selected=actor.spec.get(ARM)
    if not selected or selected['move_id']!=move['id'] or selected['weapon_id']!=move.get('_weapon_attack',{}).get('key'):return move
    out=deepcopy(move);out['_skirmisher_attack']=deepcopy(selected)
    if selected['swift']:
        require(e,actor,SWIFT)
        if not move.get('_weapon_attack'):raise ValueError('actual Swift Strikes weapon source lost')
        import effects_ext as EXT
        keywords=list(EXT.keywords_for(actor,move));priority=any('우선' in str(word) or 'Priority' in str(word) for word in [*keywords,move.get('range','')])
        out['keywords']=[word for word in keywords if '우선' not in str(word) and 'Priority' not in str(word)]+['우선(고급)' if priority else '우선']
        out['range']=move.get('range','')+', '+out['keywords'][-1]
    return out


def begin_move(e,row):
    selected=row['move'].get('_skirmisher_attack')
    if selected is None:return
    a=row['actor'];saved=a.spec.get(ARM)
    if saved!=selected:raise ValueError('actual armed Skirmisher attack choice required')
    import action_lifecycle as A,action_points as AP,frequency as F
    if selected['swift']:
        require(e,a,SWIFT);require_keyword(a,'priority')
        if AP.available(a)<1:raise ValueError('Swift Strikes requires one AP')
        AP.charge(a,1,mode='spend')
    selected=deepcopy(selected)
    if selected['outmaneuver']:
        require(e,a,OUT);quota={'kind':'scene','uses':3}
        if not F.activation_allowed(a,OUT,quota,engine=e):raise ValueError('Outmaneuver Scene frequency exhausted')
        selected['evasion']=a.evasion(selected['evasion_class'],engine=e)
        A.triggered_free_action(e,a,OUT);F.consume_activation(a,OUT,quota,engine=e)
    row['skirmisher_attack']=selected;a.spec.pop(ARM)


def accuracy_bonus(e,actor,move):
    selected=move.get('_skirmisher_attack')
    if not selected or not selected['outmaneuver']:return 0
    import move_completion as MC,arithmetic_policy as M
    rows=[r for r in getattr(e,MC.KEY,{}).values() if r['actor'] is actor and r['move_id']==move['id'] and r['phase']!='complete' and r.get('skirmisher_attack')]
    return M.ratio(rows[-1]['skirmisher_attack']['evasion'],2) if rows else 0


def atomic_move(fn):
    @wraps(fn)
    def run(e,actor,*args,**kwargs):
        interested=actor.spec.get(ARM) or any(r.get('skirmisher_forbidden') for r in __import__('combat_timing').records(actor))
        if not interested or getattr(e,'_skirmisher_atomic',False):return fn(e,actor,*args,**kwargs)
        pending=[]
        def apply(se,a):
            args2,kwargs2=G._stage_transition_payload(e,se,(args,kwargs));se._skirmisher_atomic=True
            try:return fn(se,a,*args2,**kwargs2)
            except Exception as error:
                if G.record_native_pending(se,error,pending):return None
                raise
            finally:del se._skirmisher_atomic
        result=G.transition(e,actor,apply,include_grid=e.grid is not None,include_rulings=True)
        if pending:
            exception,event_id=pending[0];raise exception(event_id)
        return result
    return run


def counter_stance(e,actor,enemy,completion_id,*,request_id):
    acquisition=require(e,actor,COUNTER)
    pending=[]
    def apply(se,a,t):
        import turn as T,initiative_interrupts as I,action_lifecycle as A
        old=a.spec.get(COUNTER_STATE)
        completed(se,t,a,completion_id,miss=True,resuming=old is not None)
        require_keyword(a,'interrupt')
        cost=acquisition['snapshot']['selection']['counter_cost'];full=cost=='korean_full'
        state={'source':COUNTER,'request_id':request_id,'completion_id':completion_id,'enemy_id':t.entity_id,'cost':cost}
        if old is not None:
            if {k:old[k] for k in state}!=state or 'continuation' not in old:raise ValueError('resume the same actual paid Counter Stance')
            current=I.frame(se);continuation=old['continuation']
            if current is None or current['actor']is not a or current['window_id']!=continuation['window_id'] or current['request_id']!=request_id:raise ValueError('actual paid Counter Stance reaction frame required')
            rows=[r for key,r in getattr(se,'_move_completions',{}).items() if key not in continuation['completion_ids_before'] and r['actor']is a]
            if len(rows)!=1 or rows[0]['move_id']!='struggle' or rows[0]['phase']!='complete' or not rows[0]['sealed'] or not a.aoo_used:raise ValueError('resume after the actual Counter Attack of Opportunity completes')
            I.finish(se);a.spec.pop(COUNTER_STATE);return True
        if not se.adjacent(a,t) or not T.can_aoo(se,a):raise ValueError('Counter Stance requires an eligible adjacent Attack of Opportunity')
        row=getattr(se,'_move_completions')[completion_id]
        if a.entity_id in row.get('skirmisher_counters',[]):raise ValueError('Counter Stance already used for this miss')
        a.spec[COUNTER_STATE]=state
        owner=se._active_turn_actor
        if owner is None:raise ValueError('Counter Stance requires the actual suspended attacker turn')
        declaration={'id':request_id,'actor_id':a.entity_id,'source':COUNTER,'priority':0,'mode':'reaction',
            'payment':'current' if getattr(a,'budget',None)is not None else 'next',
            'budget':{'standard':1,'shift':1} if full else {},'clock':'none'}
        trigger={'kind':'turn','actor_id':owner.entity_id,'serial':owner.custom_conditions.get('combat_turn_serial',0),'round':se.round_no}
        window=I.queue(se,[declaration],trigger=trigger)['window_id'];I.begin(se,window,request_id)
        if full:
            if not T.spend(se,a,'full',COUNTER):raise ValueError('Counter Stance requires a Full Action')
        else:A.triggered_free_action(se,a,COUNTER)
        row=getattr(se,'_move_completions')[completion_id]
        row['skirmisher_counters']=list(row.get('skirmisher_counters',[]))+[a.entity_id]
        a.spec[COUNTER_STATE]['continuation']={'window_id':window,'completion_ids_before':list(getattr(se,'_move_completions',{}))}
        try:T.trigger_aoo(se,t,COUNTER,[a])
        except Exception as error:
            if G.record_native_pending(se,error,pending):return None
            raise
        I.finish(se);a.spec.pop(COUNTER_STATE)
        return True
    result=G.transition(e,actor,apply,participants=(enemy,),include_grid=e.grid is not None,include_rulings=True)
    if pending:
        exception,event_id=pending[0];raise exception(event_id)
    return result


def free_reaction(e,actor,row):
    state=actor.spec.get(COUNTER_STATE)
    if row['source']!=COUNTER or state is None or state['request_id']!=row['id'] or state['cost']!='english_free':raise ValueError('actual Counter Stance Free Interrupt required')
    enemy=W.actor_index(e).get(state['enemy_id']);completed(e,enemy,actor,state['completion_id'],miss=True)
    require(e,actor,COUNTER);require_keyword(actor,'interrupt')


def finesse_context(e,actor,target,source=None):
    state=actor.spec.get(FINESSE_STATE)
    if state is None or target is None or state['target_id']!=target.entity_id or source not in (None,state['maneuver']):return None
    require(e,actor,FINESSE)
    completed(e,actor,target,state['completion_id'],resuming=state['paid'])
    return state


def maneuver_permission(e,actor,target,source):
    if finesse_context(e,actor,target,source):return {'action_cost':'free','accuracy':'automatic','opposed':'required','success':'check'}
    return None


def maneuver_spend(e,actor,target,source,ordinary='standard'):
    if finesse_context(e,actor,target,source):
        __import__('action_lifecycle').triggered_free_action(e,actor,FINESSE);return True
    return __import__('martial_artist').spend_maneuver(e,actor,target,source,ordinary)


def weapon_finesse(e,actor,target,completion_id,maneuver,**options):
    acquisition=require(e,actor,FINESSE)
    aliases={'trip':'maneuver/걸기','push':'maneuver/밀기','disarm':'maneuver/무장해제'}
    source_id=aliases.get(maneuver,maneuver)
    if source_id not in aliases.values():raise ValueError('Weapon Finesse chooses Disarm, Trip or Push')
    def apply(se,a,t):
        import turn as T,action_points as AP,common_checks as C
        old=a.spec.get(FINESSE_STATE)
        receipt=getattr(se,'_move_completions',{}).get(completion_id,{})
        if old is None and a.entity_id in receipt.get('skirmisher_finesse_used',[]):raise ValueError('Weapon Finesse already used for this attack')
        row,move=completed(se,a,t,completion_id,resuming=old is not None)
        scope=acquisition['snapshot']['selection']['trigger_scope']
        if scope=='english_weapon' and not move.get('_weapon_attack'):raise ValueError('English Weapon Finesse requires a Weapon Attack hit')
        if scope=='korean_damaging' and move.get('class') not in ('물리','특수'):raise ValueError('Korean Weapon Finesse requires a damaging Attack hit')
        intent={'completion_id':completion_id,'target_id':t.entity_id,'maneuver':source_id,'options':deepcopy(options),'paid':True}
        if old is not None:
            if old!=intent:raise ValueError('resume the same actual Weapon Finesse maneuver and choices')
        else:
            if a.entity_id in row.get('skirmisher_finesse_used',[]):raise ValueError('Weapon Finesse already used for this attack')
            if AP.available(a)<2:raise ValueError('Weapon Finesse requires two AP')
            if not T.spend(se,a,'swift',FINESSE):raise ValueError('Weapon Finesse requires its Swift Action')
            AP.charge(a,2,mode='spend');a.spec[FINESSE_STATE]=intent
            row.setdefault('skirmisher_finesse_used',[]).append(a.entity_id)
        fn={'maneuver/걸기':se.trip,'maneuver/밀기':se.push,'maneuver/무장해제':se.disarm}[source_id]
        result=fn(a,t,**options)
        if isinstance(result,C.PendingDecision):return result
        a.spec.pop(FINESSE_STATE);return result
    return G.transition(e,actor,apply,participants=(target,),include_grid=e.grid is not None,include_rulings=True)


def authorize_request(e,actor,row,evidence):
    require(e,actor,SWIFT);require_keyword(actor,'priority')
    selected=actor.spec.get(ARM)
    if row['source']!=SWIFT or selected is None or not selected['swift'] or row.get('move_id')!=selected['move_id'] or row['mode']!='reaction' or row['budget']!={'standard':1} or row['clock']!='none':raise ValueError('actual selected Swift Strikes Priority request required')
    move=__import__('weapon_actions').prepare(e,actor,e.r.move(selected['move_id']),selected['weapon_id'])
    if not move.get('_weapon_attack'):raise ValueError('actual equipped Swift Strikes weapon required')
    return prepare_move(e,actor,move)


def validate_request(e,window,row):
    """Validate Swift's own native reaction, not a defensive Move source."""
    actor=row['actor']
    if row['source']!=SWIFT or row['mode']!='reaction' or row['budget']!={'standard':1} or row['clock']!='none' or not records(actor,SWIFT):raise ValueError('actual acquired Swift Strikes Standard reaction required')
    if row['status']=='ready':
        authorize_request(e,actor,row,window['trigger']);return
    if row['status']=='skipped':return  # I validates its unpaid, actionless receipt.
    import initiative_interrupts as I,move_completion as MC
    if row['status']=='open':
        frames=[f for f in getattr(e,I.KEY)['frames'] if f['window_id']==window['id'] and f['request_id']==row['id'] and f['actor']is actor]
        if len(frames)!=1:raise ValueError('actual open Swift Strikes frame required')
        completions=[r for key,r in getattr(e,MC.KEY,{}).items() if key not in frames[0]['completion_ids_before'] and r['actor']is actor]
        if not completions:
            authorize_request(e,actor,row,window['trigger']);return
    elif row['status']=='completed':
        completion=getattr(e,MC.KEY,{}).get(row['receipt'].get('move_completion'))
        completions=[] if completion is None else [completion]
    else:raise ValueError('actual Swift Strikes reaction progress required')
    if len(completions)!=1:raise ValueError('one actual Swift Strikes native Move required')
    completion=completions[0];selected=completion.get('skirmisher_attack',{})
    move=completion['move'];prepared=move.get('_skirmisher_attack',{})
    if (completion['actor']is not actor or completion['move_id']!=row['move_id'] or not selected.get('swift')
            or not prepared.get('swift') or any(selected.get(k)!=prepared.get(k) for k in prepared)
            or selected.get('move_id')!=row['move_id'] or not move.get('_weapon_attack')
            or selected.get('weapon_id')!=move['_weapon_attack'].get('key')):
        raise ValueError('Swift Strikes receipt lost its actual armed Weapon Attack')
    if row['status']=='completed' and (completion['phase']!='complete' or not completion['sealed']):raise ValueError('completed Swift Strikes needs its actual sealed native Move')


def validate_actor(actor):
    selected=actor.spec.get(ARM)
    if selected is not None:
        if type(selected)is not dict or set(selected)!={'move_id','weapon_id','outmaneuver','swift','evasion_class'}:raise ValueError('exact armed Skirmisher attack required')
        if any(type(selected[k])is not bool for k in ('outmaneuver','swift')) or not (selected['outmaneuver'] or selected['swift']) or selected['evasion_class'] not in ('물리','특수','변화'):raise ValueError('actual Skirmisher attack selections required')
        if actor.r.move_id(selected['move_id'])!=selected['move_id']:raise ValueError('exact actual Skirmisher Move required')
        for feature,active in ((OUT,selected['outmaneuver']),(SWIFT,selected['swift'])):
            if active and not acquired(actor,feature):raise ValueError('actual acquired Skirmisher attack source required')
    state=actor.spec.get(FINESSE_STATE)
    if state is not None:
        if type(state)is not dict or set(state)!={'completion_id','target_id','maneuver','options','paid'} or state['paid'] is not True or state['maneuver'] not in ('maneuver/걸기','maneuver/밀기','maneuver/무장해제') or type(state['options'])is not dict or not acquired(actor,FINESSE):raise ValueError('actual paid Weapon Finesse continuation required')
        if any(type(state[k])is not str or not state[k].strip() for k in ('completion_id','target_id')):raise ValueError('actual Finesse trigger identities required')
    state=actor.spec.get(COUNTER_STATE)
    if state is not None:
        keys={'source','request_id','completion_id','enemy_id','cost'}
        if type(state)is not dict or set(state) not in (keys,keys|{'continuation'}) or state['source']!=COUNTER or state['cost'] not in ('korean_full','english_free') or not acquired(actor,COUNTER):raise ValueError('actual Counter Stance continuation required')
        if any(type(state[k])is not str or not state[k].strip() for k in ('request_id','completion_id','enemy_id')):raise ValueError('actual Counter trigger identities required')
        if 'continuation' in state:
            c=state['continuation']
            if type(c)is not dict or set(c)!={'window_id','completion_ids_before'} or type(c['window_id'])is not str or not c['window_id'] or type(c['completion_ids_before'])is not list or any(type(k)is not str for k in c['completion_ids_before']) or len(c['completion_ids_before'])!=len(set(c['completion_ids_before'])):raise ValueError('actual Counter Stance native continuation required')


def validate_world(e,index):
    """Tie restored Skirmisher effects and paid continuations to native receipts."""
    import combat_timing as TIME,move_completion as MC,effect_contracts as EFFECTS
    def completion(owner,target,key,hit=True,damaging=True):
        row=getattr(e,MC.KEY,{}).get(key);result=None if row is None else MC.recipient_result(row,target)
        if (row is None or row['actor']is not owner or row['phase']!='complete' or not row['sealed']
                or target not in MC.actual_recipients(row) or result is None or result['hit']is not hit
                or result.get('cancelled') or result.get('hit_prevented')):
            raise ValueError('Skirmisher state lost its actual native Attack completion')
        routed=row.get('received',{}).get(target.entity_id)
        move=MC.event_move(e,e._passive_events[routed['child_event']]) if routed else row.get('target_moves',{}).get(target.entity_id,row['move'])
        if damaging and move.get('class') not in ('물리','특수'):raise ValueError('Skirmisher state requires an actual damaging Attack')
        return row
    for target in index.values():
        for state_key,feature in ((FINESSE_STATE,FINESSE),(COUNTER_STATE,COUNTER)):
            state=target.spec.get(state_key)
            if state is None:continue
            other=index.get(state['target_id'] if feature==FINESSE else state['enemy_id'])
            if other is None:raise ValueError('actual Skirmisher continuation target required')
            row=completion(target,other,state['completion_id']) if feature==FINESSE else completion(other,target,state['completion_id'],False,False)
            if feature==FINESSE and target.entity_id not in row.get('skirmisher_finesse_used',[]):raise ValueError('actual paid Weapon Finesse receipt required')
            if feature==FINESSE and acquired(target,FINESSE)['snapshot']['selection']['trigger_scope']=='english_weapon' and not row['move'].get('_weapon_attack'):raise ValueError('actual English Weapon Finesse Weapon Attack required')
            if feature==COUNTER and state['cost']!=acquired(target,COUNTER)['snapshot']['selection']['counter_cost']:raise ValueError('actual selected Counter Stance cost required')
            if feature==COUNTER and 'continuation' in state:
                windows=getattr(e,__import__('initiative_interrupts').KEY,{}).get('windows',{})
                window=windows.get(state['continuation']['window_id'])
                requests=[] if window is None else [r for r in window['requests'] if r['id']==state['request_id'] and r['actor']is target and r['source']==COUNTER]
                if len(requests)!=1 or requests[0]['status'] not in ('open','completed') or target.entity_id not in row.get('skirmisher_counters',[]):raise ValueError('actual paid Counter Stance request and miss receipt required')
        for record in TIME.records(target):
            flags={k for k in record if k.startswith('skirmisher_')}
            if record.get('source')==HARRIER:
                owner=record.get('turn_owner')
                if owner is None or index.get(owner.entity_id)is not owner or not records(owner,HARRIER):raise ValueError('actual acquired Harrier effect owner required')
                row=completion(owner,target,record.get('origin_completion'))
                if (flags!={'skirmisher_flanked','skirmisher_forbidden'} or record['skirmisher_flanked']is not True
                        or record['skirmisher_forbidden']!=['priority','interrupt'] or record.get('statuses')!=['둔화']
                        or record.get('encounter_end')is not True or record.get('turn_deadline')!=row.get('skirmisher_boundary',{}).get('serial',-2)+1):
                    raise ValueError('Harrier receipt lost its exact effects or original next-turn deadline')
            elif flags:
                if flags!={'skirmisher_unflanked'} or record['skirmisher_unflanked']is not True or record.get('source')!=FLUTTER:raise ValueError('exact native Flutter unflanked effect required')
                expected={'type':'evasion_mod','value':3,'target':'self','until':"end of user's next turn"}
                if (record.get('effect_contract')is not True or record.get('evasion_modifier')!=3 or record.get('turn_owner')is not target
                        or record.get('encounter_end')is not True or type(record.get('turn_deadline'))is not int
                        or not 1<=record['turn_deadline']<=target.custom_conditions.get('combat_turn_serial',0)+1):raise ValueError('actual timed Flutter Evasion and next-turn deadline required')
                EFFECTS.validate_receipt(e,record.get('effect_receipt'),FLUTTER,record.get('effect_occurrence'),target,target,expected)
    return True


def before_revoke(e,actor,sources):
    lost={G.state(actor)['sources'].get(s,{}).get('static_acquisition',{}).get('feature_id') for s in sources}
    if FINESSE in lost and actor.spec.get(FINESSE_STATE):raise ValueError('finish the actual paid Weapon Finesse continuation before source withdrawal')
    if COUNTER in lost and actor.spec.get(COUNTER_STATE):raise ValueError('finish the actual paid Counter Stance continuation before source withdrawal')
    selected=actor.spec.get(ARM)
    if selected and ((OUT in lost and selected['outmaneuver']) or (SWIFT in lost and selected['swift'])):actor.spec.pop(ARM)
