"""Shared sourced recovery methods; unknown durations remain explicit GM input."""
import common_checks as C
KEY='condition_recovery_available'
RECEIPTS='condition_recovery_receipts'
SUPPORTED=('둔화','구속','얼음','잠듦')
# ch07:578 supplies recovery methods omitted from the individual definitions.
METHODS={'얼음':'extended_action_after_combat','잠듦':'natural_sleep'}
_THAW_PERMISSION=object()


def _stored_condition(actor,condition):
    import boss_transitions as BOSS
    return BOSS.condition_variant(actor,condition)


def _source_condition(actor,condition):
    import boss_transitions as BOSS
    return BOSS.condition_source(condition) if BOSS.state(actor) is not None else condition

def save_preflight(engine,actor,condition):
    import food_effects as FOOD,enduring_awareness as AWARENESS
    import eldritch_magic as ELDRITCH
    ELDRITCH.save_modifier(actor)
    C.integer(actor.save_mod,'actual saving modifier')
    AWARENESS.bonus(engine,actor)
    FOOD.save_preflight(engine,actor,condition)

def saving_check(engine,actor,condition,dc,*,fixed=None):
    """The actual native save calculation; curing belongs to its producer."""
    import food_effects as FOOD
    import cheerleader as CHEER
    if FOOD.save_preflight(engine,actor,condition) is not None or 'fashion_next_save' in actor.spec or CHEER.live(actor,'Cheered') or actor.spec.get('capture_next_save') or actor.custom_conditions.get('_trickster_first_save') or actor.custom_conditions.get('_trickster_stacked'):
        import state_grants as GRANTS
        return GRANTS.transition(engine,actor,
            lambda staged,subject:_saving_check(staged,subject,condition,dc,fixed=fixed),
            include_rulings=True)
    return _saving_check(engine,actor,condition,dc,fixed=fixed)


def _saving_check(engine,actor,condition,dc,*,fixed=None):
    import effects_ext as EXT,food_effects as FOOD,turn as TURN,status_sets as STATUSES
    C.integer(dc,'actual saving DC')
    if fixed is not None:C.integer(fixed,'actual saving d20',1,20)
    save_preflight(engine,actor,condition)
    import fashion_items as FASHION
    fashion_bonus=FASHION.consume_save_bonus(engine,actor)
    all_roll_modifier=(FASHION.all_roll_modifier(actor)+__import__('type_ace').all_rolls(actor))
    import duelist as DUELIST
    natural=11 if DUELIST.choose_eleven(engine,actor,'saving') else engine.d20() if fixed is None else fixed
    natural=__import__('oracle').replace_d20(engine,actor,natural,'saving')
    import cheerleader as CHEER
    natural,cheered=CHEER.save_roll(engine,actor,condition,natural)
    bonus=FOOD.save_bonus(engine,actor,condition)
    import optional_physical_equipment as OPTIONAL_EQUIPMENT
    optional_bonus=OPTIONAL_EQUIPMENT.save_bonus(actor,condition)
    import stat_ace as STAT
    optional_bonus+=STAT.stratagem_bonus(engine,actor,'save',condition=condition)
    capture_penalty=__import__('capture_specialist').save_penalty(engine,actor)
    adjusted=EXT.save_dc(engine,actor,condition,dc)+engine.rulings.consume('dc',actor.name,engine)-TURN.weather_save_mod(engine,condition,actor)-bonus-optional_bonus-fashion_bonus-all_roll_modifier-capture_penalty
    adjusted-=__import__('trickster').save_penalty(actor,condition)
    passed=natural>=adjusted
    label=condition or '숨돌리기'
    engine.log(f"    {actor.name} {label} 내성 체크 d20={natural} vs DC {adjusted} → {'성공' if passed else '실패'}",
               'condition/'+condition if condition else 'ch07-combat/전투의-다른-행동/숨돌리기')
    if condition is not None:STATUSES.on_save(engine,actor,condition,natural)
    __import__('trickster').saved(engine,actor,condition,passed)
    return {'natural':natural,'dc':adjusted,'base_dc':dc,'food_bonus':bonus,'optional_equipment_bonus':optional_bonus,'fashion_bonus':fashion_bonus,'all_roll_modifier':all_roll_modifier,'passed':passed,**({'capture_penalty':capture_penalty} if capture_penalty else {}),**({'cheered':cheered} if cheered else {})}


def method_for(condition):
    return METHODS.get(condition,'extended_action_end_of_scene')


def permits_action(engine,actor,kind,permission):
    return (permission is _THAW_PERMISSION and kind=='extended' and not engine.encounter_active
            and _stored_condition(actor,'얼음') in actor.conditions and actor.kind=='pokemon'
            and actor.custom_conditions.get(KEY,{}).get('얼음',{}).get('method')=='extended_action_after_combat')



def allowed_method(rules,condition,method):
    if condition not in SUPPORTED:return False
    if condition in METHODS:return method==METHODS[condition]
    return any(e.get('type')=='cured_by' and method in e.get('any_of',[]) for e in rules.condition_effects(condition))


def invalidate(actor,condition=None):
    if condition is None:actor.custom_conditions.pop(KEY,None)
    else:
        condition=_source_condition(actor,condition)
        rows=actor.custom_conditions.get(KEY,{})
        rows.pop(condition,None)
        if not rows:actor.custom_conditions.pop(KEY,None)


def validate(actor):
    rows=actor.custom_conditions.get(KEY,{})
    if not isinstance(rows,dict):raise ValueError('condition recovery availability must be a mapping')
    for condition,row in rows.items():
        if _stored_condition(actor,condition) not in actor.conditions or condition=='잠듦' or not allowed_method(actor.r,condition,row.get('method','extended_action_end_of_scene') if isinstance(row,dict) else ''):
            raise ValueError('recovery needs an actual afflicted condition with the source permission')
        if not isinstance(row,dict) or row.get('source')!='condition/'+condition:raise ValueError('condition recovery source mismatch')
        C.integer(row.get('scene'),'condition recovery scene',0 if condition=='얼음' else 1)
        C.integer(row.get('at'),'condition recovery availability time',0)
        if row['scene']!=actor.spec.get('frequency_state',{}).get('scene'):raise ValueError('condition recovery belongs to another scene boundary')
    receipts=actor.spec.get(RECEIPTS,[])
    if not isinstance(receipts,list):raise ValueError('condition recovery receipts must be a list')
    for row in receipts:
        if not isinstance(row,dict) or row.get('condition') not in SUPPORTED or row.get('source')!='condition/'+row['condition']:
            raise ValueError('condition recovery receipt source mismatch')
        if row.get('method',method_for(row['condition']))!=method_for(row['condition']):raise ValueError('recovery receipt method mismatch')
        for key,minimum in [('scene',0 if row['condition'] in METHODS else 1),('start',0),('end',0),('duration_minutes',1)]:C.integer(row.get(key),'recovery '+key,minimum)
        if row['end']-row['start']!=row['duration_minutes']*60:raise ValueError('recovery receipt duration mismatch')
        if not isinstance(row.get('reason'),str) or not row['reason'].strip():raise ValueError('recovery duration requires its GM reason')


def prepare_scene(actor):
    # A real post-combat opportunity survives a later narrative boundary.
    for condition in list(actor.custom_conditions.get(KEY,{})):
        if condition!='얼음':invalidate(actor,condition)


def end_combat(engine,actor):
    import frequency as F
    if _stored_condition(actor,'얼음') in actor.conditions:
        actor.custom_conditions.setdefault(KEY,{})['얼음']={
            'source':'condition/얼음','method':METHODS['얼음'],
            'scene':F.state(actor)['scene'],'at':engine.elapsed_seconds}


def end_scene(engine,actor):
    import frequency as F
    frozen=actor.custom_conditions.get(KEY,{}).get('얼음')
    invalidate(actor)
    rows={condition:{'source':'condition/'+condition,'scene':F.state(actor)['scene'],'at':engine.elapsed_seconds}
          for condition in sorted({_source_condition(actor,name) for name in actor.conditions}) if allowed_method(engine.r,condition,'extended_action_end_of_scene')}
    if frozen and _stored_condition(actor,'얼음') in actor.conditions:rows['얼음']={**frozen,'scene':F.state(actor)['scene']}
    if rows:actor.custom_conditions[KEY]=rows


def switch_out(engine,actor):
    for condition in sorted(actor.conditions):
        if allowed_method(engine.r,condition,'switch_out'):engine.cure_status(actor,condition)
    invalidate(actor)


def recover(engine,actor,condition,*,duration_minutes=None,reason=None):
    import movement_actions as MOVEMENT,world_entities as W,combat_timing as TIMING
    MOVEMENT.boundary(engine,'condition_recovery')
    if W.actor_index(engine).get(actor.entity_id) is not actor:raise ValueError('actual participating actor required')
    validate(actor)
    condition=_source_condition(actor,condition)
    stored=_stored_condition(actor,condition)
    method=method_for(condition)
    if not allowed_method(engine.r,condition,method):raise ValueError('condition has no supported recovery rule')
    if condition in METHODS and actor.kind!='pokemon':return C.PendingDecision('source ch07:578 specifies Pokemon; Trainer natural recovery needs a source ruling')
    if stored not in actor.conditions:raise ValueError('actual afflicted condition required')
    if engine.encounter_active:return C.PendingDecision('timed condition recovery requires being outside combat')
    row=actor.custom_conditions.get(KEY,{}).get(condition)
    if row is None and method!='natural_sleep':return C.PendingDecision('condition requires its actual scene/combat recovery boundary')
    import recovery_resolution as RECOVERY
    if RECOVERY.physical_causes(actor,condition):
        return C.PendingDecision('remove the actual physical condition source through its own removal action')
    if duration_minutes is None or reason is None:return C.PendingDecision('GM Extended condition recovery duration and reason')
    C.integer(duration_minutes,'Extended recovery minutes',1)
    if not isinstance(reason,str) or not reason.strip():raise ValueError('GM recovery duration reason required')
    engine.preflight_advance_time(duration_minutes*60,[actor])
    import state_grants as G
    def apply(e,c):
        import turn as TURN
        if method!='natural_sleep' and not TURN.spend(e,c,'extended','상태 회복: '+condition,
                _condition_recovery=_THAW_PERMISSION if condition=='얼음' else None):return False
        start=e.elapsed_seconds
        e.advance_time(duration_minutes*60,[c]);e.cure_status(c,condition)
        if stored in c.conditions:raise ValueError('condition source still active; recovery not completed')
        import frequency as F
        receipt={'source':'condition/'+condition,'condition':condition,'method':method,
                 'scene':F.state(c)['scene'],'start':start,
                 'end':e.elapsed_seconds,'duration_minutes':duration_minutes,'reason':reason}
        c.spec.setdefault(RECEIPTS,[]).append(receipt)
        e.log('  '+c.name+': '+method+'으로 '+condition+' 회복',receipt['source'])
        return receipt
    return G.transition(engine,actor,apply)


def stand_up(engine,actor):
    """One actual Shift action; interrupting AoO happens before recovery."""
    import movement_actions as MOVEMENT,world_entities as W,state_grants as G
    MOVEMENT.boundary(engine,'stand_up')
    if W.actor_index(engine).get(actor.entity_id) is not actor:raise ValueError('actual participating actor required')
    if '넘어짐' not in actor.conditions:raise ValueError('standing up requires an actual Tripped actor')
    if not any(e.get('type')=='must_stand_up' and e.get('cost')=='shift_action' for e in engine.r.condition_effects('넘어짐')):
        raise ValueError('selected Tripped source needs its own recovery action')
    def apply(e,c):
        import turn as TURN
        if not TURN.spend(e,c,'shift','일어나기',_standing_up=True):return False
        quick=__import__('tumbler').quick_offer(e,c,{'kind':'stand_up','round':e.round_no,'turn':c.custom_conditions.get('combat_turn_serial',0)})
        if e.encounter_active:TURN.trigger_aoo(e,c,'일어나기')
        if not TURN.can_act(e,c):return False
        e.cure_status(c,'넘어짐')
        if '넘어짐' in c.conditions:raise ValueError('Tripped source still requires its own removal')
        __import__('tumbler').quick_shift(e,c,quick)
        e.log('  '+c.name+': 이동 행동으로 일어나기','condition/넘어짐')
        return True
    return G.transition(engine,actor,apply)


def wake_ally(engine,actor,target,*,contact=None):
    """Sleep's adjacent ally Standard action, with native body and turn costs."""
    import movement_actions as MOVEMENT,world_entities as W,state_grants as G
    import body_state as BODY,turn as TURN
    MOVEMENT.boundary(engine,'wake_ally')
    index=W.actor_index(engine)
    for c in (actor,target):
        if index.get(c.entity_id) is not c or c.kind not in ('pokemon','trainer'):
            raise ValueError('wake requires actual participating trainer or Pokemon')
        if not c.on_field or c.captured:raise ValueError('wake requires field participants')
    if actor is target or actor.side!=target.side:
        raise ValueError('wake requires another actual ally')
    if _stored_condition(target,'잠듦') not in target.conditions:raise ValueError('wake requires an asleep ally')
    selected=engine.r._selected_rule('condition/잠듦')
    body=engine.r.units[selected]['text']['body']
    if '포켓몬과 트레이너는 기본 행동으로 인접 동료를 깨울 수 있습니다.' not in body:
        raise ValueError('selected Sleep source needs its ally wake policy')
    if contact is not None and not isinstance(contact,dict):raise ValueError('actual contact observation mapping required')
    import breather_assistance as ASSIST,mapless_space as MAPLESS
    touching=(MAPLESS.adjacent(engine,actor,target) if MAPLESS.active(engine) else
              ASSIST._contact(actor,target,ASSIST._state(actor),ASSIST._state(target),contact or {}))
    if isinstance(touching,C.PendingDecision):return touching
    if not touching:raise ValueError('wake requires adjacent actual bodies')
    if engine.grid is not None and not BODY.in_range(engine,actor,target,1):
        raise ValueError('wake contact is blocked')
    def apply(e,c,other):
        if not TURN.spend(e,c,'standard','인접 동료 깨우기'):return False
        e.cure_status(other,'잠듦')
        if _stored_condition(other,'잠듦') in other.conditions:
            raise ValueError('ally Sleep source prevented waking')
        e.log(c.name+'이(가) 인접 동료 '+other.name+'을(를) 깨움','condition/잠듦')
        return True
    return G.transition(engine,actor,apply,participants=(target,))


def permits_recall(actor):
    """Ordinary recall admission; source-specific bypass belongs to its effect."""
    return '수렁' not in __import__('blessing_effects').effective_conditions(actor)
