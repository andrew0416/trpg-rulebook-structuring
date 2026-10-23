"""Native grapple relations and all-participant contests over existing check owners."""
from copy import deepcopy
import common_checks as C,world_entities as W,state_grants as G
import maneuver_opposed as OP,crafting_recipes as Q,body_state as BODY
import combat_timing as TIME,turn as TURN,resolution_transaction as TX
import skill_maneuver_actions as SM

FIELD='_grapple_state'
MARK='_grapple_relation'
SOURCE='maneuver/붙잡기'
BIND='move/조이기'


def _bind_bonuses(e,actor):
    """Current owned Static learning, never an activation or display permission."""
    import move_capabilities as MOVES,move_state as MOVE_STATE
    if BIND not in MOVES.learned_ids(actor):
        # A selected replacement cannot silently inherit the original passive.
        if any(mid in (BIND,'조이기') for mid in MOVE_STATE.owned_list(actor.spec,'moves',actor.moves)):
            raise ValueError('Static Bind needs its exact selected original source')
        return 0,0
    move=e.r.move(BIND)
    if (move.get('id'),move.get('eng'),move.get('frequency'),move.get('class'))!=(BIND,'Bind','항상','항상') or move.get('_source',{}).get('record_span')!=[447,447]:
        raise ValueError('Static Bind needs its exact selected original source')
    return 1,2


def _state(e):return getattr(e,FIELD,{'version':1,'sequence':0,'relations':{},'requests':{}})
def has_pending(e):return any(row['status']=='active' for row in _state(e)['relations'].values())
def _sign(row):return dict(row,sha256=TX.request_fingerprint(row))
def _verify(row):
    if type(row) is not dict or row.get('sha256')!=TX.request_fingerprint({key:value for key,value in row.items() if key!='sha256'}):raise ValueError('grapple relation or request changed')
def _save(row):row.update(_sign({key:value for key,value in row.items() if key!='sha256'}))
def relation(e,c):
    uid=c.custom_conditions.get(MARK)
    row=_state(e)['relations'].get(uid)
    if row is not None:
        _verify(row)
        if row['status']=='active' and c.entity_id in row['participants']:return row
    if uid is not None:raise ValueError('grapple participant binding has no active relation')
    return None


def native_policy():
    return dict(id='native-grapple',source=SOURCE,initiation=dict(
        id='native-grapple-entry',source=SOURCE,requirements=[],challenger_skills=['전투','육상'],defender_skills=['전투','육상'],
        resistance_purpose='resist_grapple',geometry=dict(range=1,remote=False,vertical=False),
        action_cost='standard',accuracy='ordinary',accuracy_class='변화',ac=4,opposed='required',success='check',
        opportunity='other_adjacent',effects=[]),secure_bonus=3,secure_stacking=None,drag_penalties=None)


def policy(value):
    Q._fields(value,('id','source','initiation','secure_bonus','secure_stacking','drag_penalties'))
    Q._text(value['id']);Q._text(value['source']);decl=OP.declaration(value['initiation'])
    if decl['source']!=value['source'] or decl['effects']:raise ValueError('grapple entry owns its relation result and source')
    C.integer(value['secure_bonus'],'secure next-check bonus',0)
    if value['secure_stacking'] not in (None,'replace','add'):raise ValueError('explicit repeated secure stacking policy required')
    table=value['drag_penalties']
    if table is not None:
        if type(table) is not dict or not table:raise ValueError('explicit weight-class drag penalties required')
        for key,amount in table.items():
            if key not in {str(x) for x in range(1,7)}:raise ValueError('actual weight classes 1..6 required')
            C.integer(amount,'drag movement penalty',0)
    return deepcopy(value)


def _actors(e,row):
    index=W.actor_index(e)
    return tuple(index[uid] for uid in row['participants'])


def _end(e,row,reason):
    if row['status']=='ended':return
    row.update(status='ended',ended_at=e.elapsed_seconds,end_reason=reason)
    row['history'].append(dict(action='end',reason=reason,seconds=e.elapsed_seconds));_save(row)
    for actor in _actors(e,row):
        if actor.custom_conditions.get(MARK)==row['id']:actor.custom_conditions.pop(MARK)
        for record in list(TIME.records(actor)):
            if record.get('effect_occurrence') in row['vulnerability'].get(actor.entity_id,[]):
                TIME.expire(e,actor,record,ending='ended',event={'kind':'grapple_ended','relation_id':row['id']})


def boundary(e,event='reconcile',actor=None):
    for row in list(_state(e)['relations'].values()):
        _verify(row)
        if row['status']!='active':continue
        actors=_actors(e,row);geo=row['policy']['initiation']['geometry']
        reason=None
        if event in ('scene_end','encounter_end'):reason=event
        elif any(c.fainted or c.captured or not c.on_field or c not in e.everyone for c in actors):reason='participant_unavailable'
        elif len(actors)==2:
            a,b=actors
            if e.grid is None or not BODY.in_range(e,a,b,geo['range']):reason='separated'
            elif not geo['vertical'] and a.spec.get('_movement_altitude',0)!=b.spec.get('_movement_altitude',0):reason='separated'
        elif row['observation']['geometry']!=_observed_geometry(actors):reason='observed_geometry_changed'
        if reason:_end(e,row,reason);continue
        if event=='turn_start' and actor in actors:
            row['eligible'][actor.entity_id]=dict(serial=actor.custom_conditions['combat_turn_serial'],dominant=row['dominant']==actor.entity_id)
            _save(row)


def movement_permission(e,c):
    if relation(e,c) is None:return True
    return getattr(e,'_grapple_motion_actor',None) is c


def accuracy_penalty(e,a,t):
    row=relation(e,a);relation(e,t)
    return -6 if row is not None and t.entity_id not in row['participants'] else 0


def _create(e,a,t,value,*,participants=None,observation=None):
    actors=(a,t) if participants is None else tuple(participants)
    state=deepcopy(_state(e));state['sequence']+=1;uid='grapple:'+str(state['sequence'])
    row=dict(id=uid,source=value['source'],policy=deepcopy(value),participants=[c.entity_id for c in actors],dominant=a.entity_id,
             status='active',started_at=e.elapsed_seconds,eligible={},secure={},vulnerability={},history=[])
    if observation is not None:row['observation']=deepcopy(observation)
    state['relations'][uid]=row;_save(row);setattr(e,FIELD,state)
    for actor in actors:
        actor.custom_conditions[MARK]=uid
        before={x.get('effect_occurrence') for x in TIME.records(actor)}
        result=e.apply_effect(a,actor,{'type':'apply_status','status':'취약','until':'scene_end'},None,True,0,value['source'])
        row['vulnerability'][actor.entity_id]=[x['effect_occurrence'] for x in TIME.records(actor) if x.get('effect_occurrence') not in before]
        _save(row)
    row['history'].append(dict(action='observe' if observation is not None else 'initiate',actor=a.entity_id,seconds=e.elapsed_seconds));_save(row)
    return deepcopy(row)


def _observed_geometry(actors):
    return {c.entity_id:dict(position=list(c.pos),altitude=c.spec.get('_movement_altitude',0)) for c in actors}


def observe(e,participants,*,dominant,reason,source='gm/observation',declaration=None):
    """GM observes an existing group; this grants no maneuver success, roll or action."""
    if type(participants) not in (list,tuple) or len(participants)<3:raise ValueError('actual multi-participant grapple observation required')
    W.require_actors(e,*participants)
    if len({c.entity_id for c in participants})!=len(participants) or not any(c is dominant for c in participants):raise ValueError('distinct actual participants and their actual dominant required')
    if any(c.fainted or c.captured or not c.on_field or c not in e.everyone for c in participants):raise ValueError('observed grapple needs available field participants')
    fact=W._fact(reason,source);value=policy(native_policy() if declaration is None else declaration)
    Q._selected(e,value['source'])
    observation=dict(fact,participants=[c.entity_id for c in participants],dominant=dominant.entity_id,geometry=_observed_geometry(participants))
    existing=[relation(e,c) for c in participants]
    if any(row is not None for row in existing):
        row=existing[0]
        if row is not None and all(other is row for other in existing) and row['participants']==observation['participants'] and row['dominant']==dominant.entity_id and row.get('observation')==observation and row['policy']==value:return deepcopy(row)
        raise ValueError('observation cannot replace an active grapple')
    others=tuple(c for c in participants if c is not dominant)
    def apply(staged,actor,*members):
        by_id={c.entity_id:c for c in (actor,*members)}
        actual=tuple(by_id[c.entity_id] for c in participants)
        result=_create(staged,actor,members[0],value,participants=actual,observation=observation)
        staged.gm._rec('observed actual grapple',None,dict(observation,relation_id=result['id']),reason)
        return result
    return G.transition(e,dominant,apply,participants=others,include_rulings=True)


def initiate(e,a,t,*,declaration=None,challenger_skill=None,defender_skill=None,fixed_accuracy=None,
             challenger_options=None,defender_options=None,_grant=None):
    value=policy(native_policy() if declaration is None else declaration);W.require_actors(e,a,t)
    if relation(e,a) is not None or relation(e,t) is not None:raise ValueError('participant already belongs to an active two-sided grapple')
    if e.grid is None or value['initiation']['geometry']['range'] is None:return C.PendingDecision('actual grapple geometry is unknown')
    def apply(staged,actor,target):
        decl=value['initiation'];accuracy_bonus,skill_bonus=_bind_bonuses(staged,actor)
        options=challenger_options;basis={'grapple_policy':value}
        if skill_bonus:
            options=dict(challenger_options or {});options['mods']=options.get('mods',0)+skill_bonus
            basis['static_bind_source']=BIND
        plans,prepared=OP._prepare(staged,actor,target,SOURCE if _grant is not None else value['source'],(),
            challenger_skill,defender_skill,fixed_accuracy,options,defender_options,
            basis,_grant,config=decl)
        def outcome(won):
            if not won:return False
            if prepared is None:return _create(staged,actor,target,value)
            return G.transition(staged,actor,lambda se,x,y:_create(se,x,y,value),participants=(target,))
        return OP._run(staged,actor,target,SOURCE if _grant is not None else value['source'],decl['ac'],plans,prepared,
            outcome,fixed_accuracy,_grant,config=decl,_accuracy_bonus=accuracy_bonus)
    # Skill features use their existing observed continuation receipt.
    if any((option or {}).get('feature') is not None for option in (challenger_options,defender_options)):return apply(e,a,t)
    return G.transition(e,a,apply,participants=(t,))


def _turn(e,actor,row):
    eligibility=row['eligible'].get(actor.entity_id)
    if getattr(e,'_active_turn_actor',None) is not actor or eligibility is None or eligibility['serial']!=actor.custom_conditions.get('combat_turn_serial'):
        raise ValueError('grapple action requires an actual own turn that started in this relation')
    return eligibility['dominant'] and row['dominant']==actor.entity_id


def _skills(e,actor,other,row,skill,other_skill,ao,do):
    import skill_modifiers as SKILLS
    allowed={SKILLS.skill_id(e.r.skill_policy,x,required=True) for x in ('전투','육상')}
    for value in (skill,other_skill):
        if SKILLS.skill_id(e.r.skill_policy,value,required=True) not in allowed:raise ValueError('Combat or Athletics grapple check required')
    ao=dict(ao or {});do=dict(do or {})
    if ao.get('roll_id') is not None and ao.get('roll_id')==do.get('roll_id'):raise ValueError('distinct grapple roll identities required')
    for owner,chosen,options in ((actor,skill,ao),(other,other_skill,do)):
        _,skill_bonus=_bind_bonuses(e,owner)
        options['mods']=options.get('mods',0)+row['secure'].get(owner.entity_id,0)+skill_bonus
        e._prepare_skill_roll(owner,chosen,**options)
    return ao,do


class _AwaitContestDecision(Exception):
    def __init__(self,pending):self.pending=pending


def _multipart_contest(e,actor,row,checks,choices,tie_winner,request_id,intent):
    import skill_modifiers as SKILLS
    if request_id is None:raise ValueError('identified all-participant grapple contest required')
    if type(checks) is not dict or set(checks)!=set(row['participants']):raise ValueError('each actual grapple participant must choose a check')
    if choices is not None and (type(choices) is not dict or set(choices)-set(row['participants']) or any(x not in ('keep','end') for x in choices.values())):raise ValueError('actual participant winner choices must be keep or end')
    if tie_winner is not None:
        Q._fields(tie_winner,('actor_id','reason'));Q._text(tie_winner['reason'])
        if tie_winner['actor_id'] not in row['participants']:raise ValueError('GM tie decision needs an actual participant')
    allowed={SKILLS.skill_id(e.r.skill_policy,x,required=True) for x in ('전투','육상')}
    actors=_actors(e,row);plans=[]
    for owner in (actor,*(c for c in actors if c is not actor)):
        check=checks[owner.entity_id];Q._fields(check,('skill','options'))
        if SKILLS.skill_id(e.r.skill_policy,check['skill'],required=True) not in allowed:raise ValueError('Combat or Athletics grapple check required')
        if type(check['options']) is not dict:raise ValueError('actual participant skill options required')
        options=dict(check['options']);_,bind_bonus=_bind_bonuses(e,owner)
        options['mods']=options.get('mods',0)+row['secure'].get(owner.entity_id,0)+bind_bonus
        plans.append((owner,check['skill'],options))
    anchor=next(c for c in actors if c.entity_id==row['dominant'])
    signature=row['sha256'];uid=row['id']
    prepared=SM.prepare(e,actor,anchor,SOURCE+'/contest',dict(relation_id=uid,relation_sha256=signature,request_id=request_id),plans,observe=True)
    def resolve(rolls):
        totals={owner.entity_id:roll.total for (owner,_,_),roll in zip(plans,rolls)}
        highest=max(totals.values());leaders=[identity for identity,total in totals.items() if total==highest]
        # The existing defender keeps a tied highest check (ch06:33-34).
        winner=row['dominant'] if row['dominant'] in leaders else leaders[0] if len(leaders)==1 else None
        if tie_winner is not None:
            if winner is not None or tie_winner['actor_id'] not in leaders:raise ValueError('GM may choose only among unresolved actual highest participants')
            winner=tie_winner['actor_id']
        basis=dict(relation_id=uid,request_id=request_id,check_totals=totals,highest_ids=leaders)
        if winner is None:raise _AwaitContestDecision(C.PendingDecision('GM resolves the observed highest grapple tie',basis=basis))
        choice=(choices or {}).get(winner)
        if choice is None:raise _AwaitContestDecision(C.PendingDecision('actual grapple winner chooses keep or end',basis=dict(basis,winner_id=winner)))
        return winner,choice,totals
    def outcome(resolved):
        winner,choice,totals=resolved
        def apply(staged,a,*members):
            current=_state(staged)['relations'][uid];_verify(current)
            if current['status']!='active' or current['sha256']!=signature:raise ValueError('observed grapple contest relation changed')
            current['secure'].clear();current['dominant']=winner;_save(current)
            result=dict(success=True,relation_id=uid,action='contest',winner_id=winner,check_totals=totals)
            if tie_winner is not None:result['gm_tie_decision']=deepcopy(tie_winner)
            if choice=='end':_end(staged,current,'contest_winner_release')
            current['history'].append(dict(action='contest',actor=a.entity_id,winner_id=winner,seconds=staged.elapsed_seconds));_save(current)
            boundary(staged)
            _state(staged)['requests'][request_id]=_sign(dict(intent=intent,result=deepcopy(result)))
            return result
        return G.transition(e,actor,apply,participants=tuple(c for c in actors if c is not actor))
    try:
        result=SM.run(e,actor,prepared,spend=lambda:TURN.spend(e,actor,'full',SOURCE+'/contest'),
            aoo=lambda:None,can_continue=lambda:TURN.can_act(e,actor),accuracy=lambda:True,outcome=outcome,resolve_rolls=resolve)
    except _AwaitContestDecision as decision:return decision.pending
    if result is False:_state(e)['requests'][request_id]=_sign(dict(intent=intent,result=False))
    return result


def _drag_plan(e,actor,other,row,path):
    import movement_actions as MOVE
    penalties=row['policy']['drag_penalties']
    weight=other.weight_class
    if penalties is None or str(weight) not in penalties:return C.PendingDecision('declare actual partner weight class and sourced drag penalty table')
    if type(path) is not list or not path:raise ValueError('explicit joint actor/partner path required')
    if any(c.spec.get('_movement_altitude',0)!=0 or c.spec.get('_burrow',{}).get('underground') for c in (actor,other)):raise ValueError('drag requires a ground movement adapter')
    limit=max(0,e.move_profile(actor,movement_mode='land')[0]-penalties[str(weight)]);cost=0;diagonals=0
    old_a,old_b=actor.pos,other.pos;plan=[]
    for step in path:
        Q._fields(step,('actor','partner'))
        pa,pb=(tuple(step[key]) for key in ('actor','partner'))
        if any(len(p)!=2 or any(type(x) is not int for x in p) for p in (pa,pb)):raise ValueError('concrete joint path cells required')
        da=(pa[0]-old_a[0],pa[1]-old_a[1]);db=(pb[0]-old_b[0],pb[1]-old_b[1])
        if da!=db or max(map(abs,da))!=1:raise ValueError('drag translates both actual bodies by one adjacent step')
        if not BODY.can_place(e,actor,pa,origin=old_a,altitude=0,ignore_actors=(other,)) or not BODY.can_place(e,other,pb,origin=old_b,altitude=0,ignore_actors=(actor,)):raise ValueError('joint grapple path is obstructed')
        if BODY.at_position(actor,pa)&BODY.at_position(other,pb):raise ValueError('dragged bodies cannot overlap')
        step_cost,diagonals=MOVE.step_cost(old_a,pa,diagonals)
        import map_terrain as TERRAIN
        if not all(TERRAIN.can_travel(e,c,p,'육상') for c,p in ((actor,pa),(other,pb))):raise ValueError('joint drag lacks actual terrain movement capability')
        cost+=step_cost+MOVE.slow_terrain_penalty(e,actor,pa,'육상',step=step_cost)
        if cost>limit:raise ValueError('joint drag path exceeds reduced native movement')
        plan.append((pa,pb));old_a,old_b=pa,pb
    return plan


def action(e,actor,kind,*,challenger_skill=None,defender_skill=None,challenger_options=None,defender_options=None,
           winner_choice=None,path=None,escape=None,request_id=None,participant_checks=None,winner_choices=None,tie_winner=None,target=None):
    W.require_actors(e,actor)
    if target is not None:W.require_actors(e,target)
    if request_id is not None:Q._text(request_id)
    intent=dict(actor_id=actor.entity_id,kind=kind,challenger_skill=challenger_skill,defender_skill=defender_skill,
                challenger_options=deepcopy(challenger_options),defender_options=deepcopy(defender_options),
                winner_choice=winner_choice,path=deepcopy(path),escape=deepcopy(escape))
    for key,value in (('participant_checks',participant_checks),('winner_choices',winner_choices),('tie_winner',tie_winner)):
        if value is not None:intent[key]=deepcopy(value)
    if target is not None:intent['target_id']=target.entity_id
    if type(intent.get('participant_checks')) is dict:
        for check in intent['participant_checks'].values():
            if type(check) is dict and type(check.get('options')) is dict:check['options'].pop('feature_options',None)
    if type(intent['escape']) is dict and type(intent['escape'].get('cleanse_checks')) is dict:
        # A UI callback may change while resuming the same observed Focus.
        # It is not serializable intent or a fresh permission token.
        for check in intent['escape']['cleanse_checks'].values():
            if type(check) is dict and type(check.get('skill_options')) is dict:
                check['skill_options'].pop('feature_options',None)
    previous=_state(e)['requests'].get(request_id) if request_id is not None else None
    if previous is not None:
        _verify(previous)
        if previous['intent']!=intent:raise ValueError('grapple request changed intent')
        return deepcopy(previous['result'])
    boundary(e);row=relation(e,actor)
    if row is None:raise ValueError('actual active grapple participant required')
    if kind not in ('contest','end','secure','attack','drag','escape'):raise ValueError('unknown grapple action')
    if kind=='escape':
        if getattr(e,'_active_turn_actor',None) is not actor:raise ValueError('capability escape requires the actual own turn')
        dominant=False
    else:dominant=_turn(e,actor,row)
    actors=_actors(e,row);multipart=len(actors)>2
    if target is not None:
        if target is actor or not any(c is target for c in actors):raise ValueError('attack target must be another actual grapple participant')
        if kind!='attack':raise ValueError('explicit grapple target is only an attack choice')
    if kind!='contest' and any(x is not None for x in (participant_checks,winner_choices,tie_winner)):raise ValueError('participant check and winner choices require a contest')
    other=target if target is not None else next(c for c in actors if c is not actor)
    if kind in ('end','secure','attack','drag') and not dominant:raise ValueError('dominant role at turn start and action is required')
    if kind=='contest' and dominant:raise ValueError('nondominant participant contests dominance')
    if kind=='contest':
        if multipart:
            if any(x is not None for x in (challenger_skill,defender_skill,challenger_options,defender_options,winner_choice)):raise ValueError('multi-participant contest requires each actual participant declaration')
            return _multipart_contest(e,actor,row,participant_checks,winner_choices,tie_winner,request_id,intent)
        if any(x is not None for x in (participant_checks,winner_choices,tie_winner)):raise ValueError('paired contest uses its original challenger and defender declaration')
        if winner_choice not in ('keep','end'):raise ValueError('winner must choose to keep/dominance or end')
        _skills(e,actor,other,row,challenger_skill,defender_skill,challenger_options,defender_options)
    if multipart and kind=='attack' and target is None:raise ValueError('multi-participant grapple attack needs its actual target')
    if kind=='secure' and row['secure'].get(actor.entity_id) and row['policy']['secure_stacking'] is None:return C.PendingDecision('declare repeated Secure stacking policy')
    if kind=='drag':
        if multipart:return C.PendingDecision('GM multi-participant drag weight and joint path policy is not declared')
        plan=_drag_plan(e,actor,other,row,path)
        if isinstance(plan,C.PendingDecision):return plan
    if kind=='escape':
        Q._fields({k:v for k,v in escape.items() if k!='cleanse_checks'} if type(escape) is dict else escape,
                  ('capability','cost','destination'))
        choice=escape['capability'];teleporter=choice in ('Teleporter','텔레포터','순간이동')
        family=('Teleporter','텔레포터','순간이동') if teleporter else ('Phasing','통과','페이징')
        names={str(x).removeprefix('capability/') for x in G.effective_capabilities(actor,only=family)}
        import movement_actions as MOVE
        acquired=choice in names or teleporter and MOVE.capabilities(e,actor).get('teleport',0)>0
        if not acquired or choice not in ('Phasing','통과','페이징','Teleporter','텔레포터','순간이동'):raise ValueError('actual Phasing or Teleporter capability required')
        if escape['cost'] not in ('shift','standard','swift','free'):raise ValueError('explicit sourced escape cost required')
        if escape['destination'] is None:raise ValueError('escape needs an actual legal destination')
        if not teleporter:
            # Resolve observed source checks before the movement transaction:
            # failure and destruction remain real even if later movement fails.
            destination=MOVE._point(escape['destination'])
            if not BODY.can_place(e,actor,destination,altitude=actor.spec.get('_movement_altitude',0)):
                raise ValueError('actual escape destination is obstructed')
            if max(abs(destination[i]-actor.pos[i]) for i in range(2))>e.move_profile(actor,movement_mode='land')[0]:
                raise ValueError('Phasing escape exceeds native movement')
            import cleanse_tags as CLEANSE
            allowed=CLEANSE.phasing_passage(e,actor,destination,checks=escape.get('cleanse_checks'))
            if isinstance(allowed,C.PendingDecision) or allowed is False:return allowed
        elif escape.get('cleanse_checks'):
            raise ValueError('Cleanse Tags restrict Phasing, not Teleporter')
    uid=row['id']
    def apply(staged,a,b,*members):
        current=_state(staged)['relations'][uid]
        if kind=='escape':
            destination=tuple(escape['destination'])
            if len(destination)!=2 or not BODY.can_place(staged,a,destination,altitude=a.spec.get('_movement_altitude',0)):raise ValueError('actual escape destination is obstructed')
            if escape['capability'] in ('Teleporter','텔레포터','순간이동'):
                if escape['cost']!='shift':raise ValueError('native Teleporter escape uses its native Shift cost')
                import movement_actions as MOVE
                staged._grapple_motion_actor=a
                try:result=MOVE.teleport(staged,a,destination,surface_contact=True,reason_text='actual grapple capability escape')
                finally:vars(staged).pop('_grapple_motion_actor',None)
                if isinstance(result,C.PendingDecision) or result is False:return result
            else:
                if max(abs(destination[i]-a.pos[i]) for i in range(2))>staged.move_profile(a,movement_mode='land')[0]:raise ValueError('Phasing escape exceeds native movement')
                if not TURN.spend(staged,a,escape['cost'],SOURCE+'/escape'):return False
                a.pos=destination
                import effects_ext as EXT
                EXT.on_enter_cell(staged,a,destination)
            _end(staged,current,'capability_escape');result=dict(success=True,ended=True)
        else:
            if not TURN.spend(staged,a,__import__('martial_artist').grapple_action_cost(staged,a),SOURCE+'/'+kind):return False
            result=dict(success=True,relation_id=uid,action=kind)
            if kind=='end':_end(staged,current,'dominant_release')
            elif kind=='secure':
                old=current['secure'].get(a.entity_id,0)
                current['secure'][a.entity_id]=current['policy']['secure_bonus']+(old if current['policy']['secure_stacking']=='add' else 0);_save(current)
            elif kind=='contest':
                ao,do=_skills(staged,a,b,current,challenger_skill,defender_skill,challenger_options,defender_options)
                won=staged.opposed_check(a,challenger_skill,b,defender_skill,challenger_options=ao,defender_options=do)
                winner=a if won else b
                current['secure'].clear();current['dominant']=winner.entity_id;_save(current);result['winner_id']=winner.entity_id
                if winner_choice=='end':_end(staged,current,'contest_winner_release')
            elif kind=='attack':
                import precise_actions as PRECISE
                move=staged.r.move('struggle');event=PRECISE.attacked(staged,a,b,move,producer='combat_maneuver')
                PRECISE.accuracy(event,True)
                import gleeful_interference as GLEEFUL
                gleeful=GLEEFUL.snapshot(staged,a,b,move)
                observation={}
                result['damage']=staged.resolve_attack_damage(a,b,move,crit=False,_precision_event=event,_damage_observation=observation)
                # An actual atomic damage delivery can replace relation dictionaries.
                current=_state(staged)['relations'][uid]
                if not observation.get('hit_prevented'):
                    result['roughneck']=__import__('roughneck').attack_hit(staged,a,b,origin={'kind':'grapple','relation_id':uid,'history_index':len(current['history']),'event_id':event['id']})
                if gleeful is not None and not observation.get('hit_prevented'):
                    origin={'kind':'grapple','relation_id':uid,'history_index':len(current['history'])}
                    result['gleeful']=GLEEFUL.issue(staged,gleeful,origin)
                staged.check_fainted(b)
            elif kind=='drag':
                import effects_ext as EXT
                for pa,pb in plan:
                    a.pos=pa;b.pos=pb
                    EXT.on_enter_cell(staged,a,pa);EXT.on_enter_cell(staged,b,pb)
                    if current['status']!='active' or a.pos!=pa or b.pos!=pb:break
                result.update(actor_position=a.pos,partner_position=b.pos)
            entry=dict(action=kind,actor=a.entity_id,seconds=staged.elapsed_seconds)
            if 'roughneck' in result:entry['roughneck']=deepcopy(result['roughneck'])
            if 'gleeful' in result:entry['gleeful']=deepcopy(result['gleeful'])
            current['history'].append(entry);_save(current)
        boundary(staged)
        if request_id is not None:_state(staged)['requests'][request_id]=_sign(dict(intent=intent,result=deepcopy(result)))
        return result
    return G.transition(e,actor,apply,participants=(other,*(c for c in actors if c is not actor and c is not other)),include_rulings=True)


def validate_world(e,index=None):
    state=_state(e)
    if set(state)!={'version','sequence','relations','requests'} or state['version']!=1:raise ValueError('invalid grapple state')
    C.integer(state['sequence'],'grapple sequence',0);index=W.actor_index(e) if index is None else index
    active={}
    for uid,row in state['relations'].items():
        _verify(row);policy(row['policy'])
        if row['id']!=uid or row['source']!=row['policy']['source'] or type(row['participants']) is not list or len(row['participants'])<2 or len(set(row['participants']))!=len(row['participants']) or any(x not in index for x in row['participants']) or row['dominant'] not in row['participants']:raise ValueError('actual distinct grapple participants and dominant owner required')
        if len(row['participants'])>2:
            observation=row.get('observation');Q._fields(observation,('reason','source','participants','dominant','geometry'))
            W._fact(observation['reason'],observation['source'])
            if observation['participants']!=row['participants'] or observation['dominant'] not in row['participants'] or set(observation['geometry'])!=set(row['participants']):raise ValueError('actual GM-observed grapple membership and geometry required')
            for geometry in observation['geometry'].values():
                Q._fields(geometry,('position','altitude'))
                if type(geometry['position']) is not list or len(geometry['position'])!=2 or any(type(x) is not int for x in geometry['position']):raise ValueError('actual observed grapple positions required')
                from physical_limits import number
                number(geometry['altitude'],'observed grapple altitude',minimum=0)
        if row['status'] not in ('active','ended'):raise ValueError('invalid grapple lifecycle')
        if row['status']=='active':
            for identity in row['participants']:
                if identity in active:raise ValueError('participant belongs to multiple active grapples')
                active[identity]=uid
                if index[identity].custom_conditions.get(MARK)!=uid:raise ValueError('grapple restriction lost its relation')
    for identity,actor in index.items():
        if actor.custom_conditions.get(MARK)!=active.get(identity):raise ValueError('orphaned grapple restriction')
    for request in state['requests'].values():_verify(request)
