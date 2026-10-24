"""Initiative-count expiry (ch07:34), distinct from actor-turn expiry."""
import common_checks as CHECKS

KEY="combat_timed_effects"

def records(c):return c.custom_conditions.get(KEY,[])
def active(engine):return any(records(c) for c in getattr(engine,"_time_actors",[]))

def current(engine):
    cursor=getattr(engine,"_initiative_cursor",None)
    if not cursor or cursor["round"]!=engine.round_no:
        raise ValueError("combat effect requires the current explicit initiative count")
    return cursor["count"]

def at_count(engine,count,*,_turn_start=False):
    CHECKS.integer(count,"initiative count")
    if engine.round_start_seconds is None:raise ValueError("initiative count requires an open combat round")
    old=getattr(engine,"_initiative_cursor",None)
    if old and old["round"]==engine.round_no:
        if count>old["count"]:raise ValueError("initiative count cannot move backward within a round")
        if not _turn_start and getattr(engine,"_active_turn_actor",None) is not None and count!=old["count"]:
            raise ValueError("initiative count cannot advance while a turn is open")
    engine._initiative_cursor={"round":engine.round_no,"count":count,"available_for_turn":True}
    import weather_state as WEATHER
    WEATHER.boundary(engine,count=count)
    for c in getattr(engine,"_time_actors",[]):
        for record in list(records(c)):
            deadline=record.get("count_deadline")
            if deadline and (engine.round_no>deadline[0] or engine.round_no==deadline[0] and count<=deadline[1]):
                expire(engine,c,record)
    import condition_instances as CONDITIONS
    CONDITIONS.boundary(engine,count=count)
    import environmental_item_state as ENVIRONMENTAL_ITEMS
    ENVIRONMENTAL_ITEMS.boundary(engine,count=count)
    engine.log(f"  이니셔티브 카운트: R{engine.round_no} / {count}","combat/initiative")
    return count

def preflight_turn(engine,count=None):
    import weather_state as WEATHER
    WEATHER.validate(engine)
    weather=getattr(engine,WEATHER.KEY,{}).get('active')
    timed_weather=weather is not None and weather.get('deadline_count') is not None
    if count is not None:
        CHECKS.integer(count,"initiative count")
        if engine.round_start_seconds is None:raise ValueError("initiative count requires an open combat round")
        old=getattr(engine,"_initiative_cursor",None)
        if old and old["round"]==engine.round_no and count>old["count"]:
            raise ValueError("initiative count cannot move backward within a round")
    elif timed_weather or any(x.get("count_deadline") for c in getattr(engine,"_time_actors",[]) for x in records(c)) or any(r.get("effect",{}).get("condition")=="억압" for c in getattr(engine,"_time_actors",[]) for r in c.custom_conditions.get("condition_instances",[])):
        cursor=getattr(engine,"_initiative_cursor",None)
        if not cursor or cursor["round"]!=engine.round_no or not cursor["available_for_turn"]:
            raise ValueError("active timed effects require an explicit initiative count before this turn")

def begin_turn(engine,c,count=None):
    if count is not None:at_count(engine,count,_turn_start=True)
    cursor=getattr(engine,"_initiative_cursor",None)
    if cursor and cursor["round"]==engine.round_no:cursor["available_for_turn"]=False
    # Actual owner turns advance even when no timed-list effect is installed.
    # Coats and other storage families consume the same clock.
    c.custom_conditions["combat_turn_serial"]=CHECKS.integer(c.custom_conditions.get("combat_turn_serial",0),"actual owner turn serial",0)+1
    c.custom_conditions['blessing_ignore_turn_open']=True
    import effect_lifetime_policy as LIFETIMES
    LIFETIMES.boundary(engine,'turn_start',c)
    serial=c.custom_conditions.get("combat_turn_serial",0)
    for target in getattr(engine,"_time_actors",[]):
        for record in list(records(target)):
            if record.get("turn_owner") is c and record.get("turn_start_deadline") is not None and serial>=record["turn_start_deadline"]:
                expire(engine,target,record)

def end_turn(engine,c):
    __import__('telekinetic').end_turn(engine,c)
    import effect_lifetime_policy as LIFETIMES
    LIFETIMES.boundary(engine,'turn_end',c)
    serial=c.custom_conditions.get("combat_turn_serial",0)
    for target in getattr(engine,"_time_actors",[]):
        for record in list(records(target)):
            if record.get("turn_owner") is c and record.get("turn_deadline") is not None and serial>=record["turn_deadline"]:
                expire(engine,target,record)
    import exhaust_moves as EXHAUST
    EXHAUST.end_turn(engine,c)
    c.custom_conditions.pop('blessing_ignore_turn_open',None)

def finish_round(engine):
    import environmental_item_state as ENVIRONMENTAL_ITEMS
    ENVIRONMENTAL_ITEMS.boundary(engine,round_end=True)
    import effect_lifetime_policy as LIFETIMES
    LIFETIMES.boundary(engine,'round_end')
    import weather_state as WEATHER
    WEATHER.boundary(engine,round_end=True)
    import condition_instances as CONDITIONS
    CONDITIONS.boundary(engine,round_end=True)
    # Ending the successor round necessarily passes every count. Never expire
    # a one-round effect at the end of the round in which it was created.
    for c in getattr(engine,"_time_actors",[]):
        for record in list(records(c)):
            deadline=record.get("count_deadline")
            if deadline and deadline[0]<=engine.round_no:expire(engine,c,record)
            elif record.get("round_end_deadline") is not None and record["round_end_deadline"]<=engine.round_no:expire(engine,c,record)

def end_scene(engine):
    import environmental_item_state as ENVIRONMENTAL_ITEMS
    ENVIRONMENTAL_ITEMS.boundary(engine,scene_end=True)
    import stat_exchange_state as STAT_EXCHANGE
    STAT_EXCHANGE.preflight_actors(getattr(engine,"_time_actors",[]),'scene_end')
    import effect_lifetime_policy as LIFETIMES
    LIFETIMES.boundary(engine,'scene_end')
    import optional_physical_equipment as OPTIONAL_EQUIPMENT
    OPTIONAL_EQUIPMENT.boundary(engine,'scene_end')
    for c in getattr(engine,"_time_actors",[]):
        for record in list(records(c)):
            if not record.get("manual_end") and LIFETIMES.KEY not in record:
                expire(engine,c,record,
                       event={'kind':'scene_end'} if 'stat_exchange' in record else None)
        c.custom_conditions.pop("dirty_trick_uses",None)
        c.custom_conditions.pop("manipulate_uses",None)
    if hasattr(engine,"_initiative_cursor"):delattr(engine,"_initiative_cursor")

def install(engine,c,record):
    engine.time_actors([c,*([record["turn_owner"]] if "turn_owner" in record else [])])
    zero=record.get('initiative_operation') or ({'operation':'replace','value':0} if record.get('initiative_zero') else {})
    if __import__('martial_artist_ability_identities').blocks_zero(c,zero):
        record.pop('initiative_zero',None);record.pop('initiative_operation',None);record['initiative_prevented_by']='ability/정신력'
    record["owned_statuses"]=set();record["installing"]=True
    c.custom_conditions.setdefault(KEY,[]).append(record)
    for status in record.get("statuses",[]):
        if status not in c.conditions and engine.apply_status(c,status):record["owned_statuses"].add(status)
    record["installing"]=False
    if record.get("initiative_zero"):
        if not any(x is not record and x.get("initiative_zero") for x in records(c)):
            c.custom_conditions["timed_initiative_baseline"]={"value":c.initiative_override}
        c.initiative_override=0
    return record

def expire(engine,c,record,*,ending='expired',event=None):
    current_records=records(c)
    if record not in current_records:return
    __import__('telekinetic').ending(engine,c,record)
    if record.get('effect_instance',{}).get('kind')=='temporary_ap':
        import temporary_ap as TEMP_AP
        TEMP_AP.before_expire(engine,c,record)
    import bound_ap as BOUND
    BOUND.preflight_expire(engine,c,record,event=event or {'kind':ending})
    stat_plan=None
    if "stat_exchange" in record:
        import stat_exchange_state as STAT_EXCHANGE
        stat_plan=STAT_EXCHANGE.prepare_expire(c,record)
    import effect_lifetime_policy as LIFETIMES
    if LIFETIMES.KEY in record:
        LIFETIMES.archive(engine,c,record,ending=ending,event=event or {'kind':'expired'})
    import effect_instances as INSTANCES
    if INSTANCES.KEY in record:
        if record[INSTANCES.KEY].get('kind')=='temporary_ap':
            import temporary_ap as TEMP_AP
            TEMP_AP.validate_record(c,record)
            event=event or {'kind':'lifetime_end','round':engine.round_no}
        elif record[INSTANCES.KEY].get('kind')=='captured_momentum':
            import captured_momentum as MOMENTUM
            MOMENTUM.validate_record(c,record,consuming=ending=='consumed')
            event=event or {'kind':'lifetime_end','round':engine.round_no}
        elif record[INSTANCES.KEY].get('kind')=='roll_components':
            import roll_effects as ROLLS
            ROLLS.validate_record(c,record)
            event=event or {'kind':'round_end','round':engine.round_no}
        elif record[INSTANCES.KEY].get('kind')=='sage_dr':
            __import__('sage').validate_effect(c,record)
            cursor=getattr(engine,'_initiative_cursor',None)
            event=event or ({'kind':'initiative_count','round':engine.round_no,'count':cursor['count']} if cursor and cursor['round']==engine.round_no else {'kind':'lifetime_end','round':engine.round_no})
        elif record[INSTANCES.KEY].get('kind')=='telepath':
            __import__('telepath').validate_effect(c,record)
            event=event or {'kind':'owner_turn_end','turn':c.custom_conditions.get('combat_turn_serial',0)}
        else:
            import event_effects as EVENTS
            EVENTS.validate_record(c,record)
            event=event or {'kind':'owner_turn_end','turn':c.custom_conditions.get('combat_turn_serial',0)}
        INSTANCES.archive(engine,c,record,state=ending,event=event)
    current_records.remove(record)
    if record.get("uncurable_infatuation"):engine.cure_status(c,"헤롱헤롱")
    if stat_plan is not None:
        STAT_EXCHANGE.commit_expire(c,record,stat_plan,ending=ending,
                                    event=event or {'kind':'expired'})
    if record.get("grant_source"):
        import state_grants as GRANTS
        GRANTS.revoke(c,record["grant_source"],engine=engine)
    if record.get("fashionista_dress"):
        import fashionista as FASHIONISTA
        FASHIONISTA.dress_expired(engine,c,record)
    for status in list(record.get("owned_statuses",[])):
        if any(status in x.get("statuses",[]) for x in current_records):
            next(x for x in current_records if status in x.get("statuses",[]))["owned_statuses"].add(status)
        else:engine.cure_status(c,status)
    if record.get("initiative_zero") and not any(x.get("initiative_zero") for x in current_records):
        baseline=c.custom_conditions.pop("timed_initiative_baseline",None)
        if baseline is not None and c.initiative_override==0:c.initiative_override=baseline["value"]
    if not current_records:c.custom_conditions.pop(KEY,None)
    BOUND.effect_ended(engine,c,record,event=event or {'kind':ending})
    if record.get('channel_imprint'):__import__('channeler').imprint_ended(engine,c,record)
    engine.log(f"    {c.name}: {record['source']} 기간 종료",record["source"])

def on_status_apply(c,status):
    for record in records(c):
        if not record.get("installing"):record.get("owned_statuses",set()).discard(status)

def on_status_cure(c,status):
    if status=='독':c.custom_conditions.pop('type_ace_poison',None)
    for record in records(c):
        record.get("owned_statuses",set()).discard(status)
        if record.get("source")=="maneuver/술수":
            if status=="헤롱헤롱" and record.get("manipulation")=="flirt":
                record.pop("infatuation_source",None)
                record["save_automatic_failure"]=[]
            elif status=="난동" and record.get("manipulation")=="bon_mot":
                record["save_forbidden"]=[]
                record["forced_attack"]=False

def on_initiative_override(c):
    c.custom_conditions.pop("timed_initiative_baseline",None)
    c.custom_conditions.pop("initiative_fixed",None)
def all_roll_modifier(c):return sum(x.get("all_roll_modifier",0)+x.get("fashion_all_roll_modifier",0) for x in records(c))

def skill_modifier(c):return sum(x.get("skill_modifier",0) for x in records(c))

def evasion_zero(c):return any(x.get('evasion_zero') is True for x in records(c))


def retain_manual_status(c,status):
    """Cure other causes while an unremoved physical source still imposes status."""
    import recovery_resolution as RECOVERY
    sources=RECOVERY.physical_causes(c,status)
    if not sources:return False
    on_status_cure(c,status)
    sources[0].setdefault("owned_statuses",set()).add(status)
    return True

def accuracy_modifier(c, *, include_effect_contract=True):
    return sum(x.get("accuracy_modifier",0) for x in records(c)
               if include_effect_contract or not x.get("effect_contract"))
def blocked_movement_modes(c):return {mode for x in records(c) for mode in x.get("blocked_movement_modes",[])}
