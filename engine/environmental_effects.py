"""Source-backed environmental harm with explicit world facts and unresolved timing.

The engine clock owns duration. A breathing observation never restarts the same
ongoing deprivation. Protected suffocation injuries are removed only by breathing.
"""
import life as LIFE
import arithmetic_policy as M
from copy import deepcopy
import common_checks as C
import roll_pools as POOLS

SUFFOCATION="ch07-combat/여러가지-규칙/질식"
FALL="ch07-combat/여러가지-규칙/낙하-데미지"
TIMINGS={"grace_boundary":60,"completed_round_after_grace":70}


def selected(e,source):
    if e.r._selected_rule(source)!=source:
        raise ValueError("selected environmental rule variant requires its own source policy")


class EnvironmentalPending(RuntimeError):
    def __init__(self,actor,action_id):
        self.actor=actor;self.action_id=action_id
        super().__init__("unresolved environmental fall "+action_id)


def observe(c):
    return {"hp":c.hp,"temp_hp":c.temp_hp,"injuries":c.injuries,"dead":c.dead,"conditions":tuple(sorted(c.conditions))}


def ensure_clear(e):
    actors=[*getattr(e,"_time_actors",[]),*getattr(e,"everyone",[]),*getattr(getattr(e,"gm",None),"everyone",[])]
    for c in {id(c):c for c in actors}.values():
        for action_id,event in c.spec.get("_fall_events",{}).items():
            if event.get("status","").startswith("pending_heavy_composition"):
                raise EnvironmentalPending(c,action_id)


def resolve_fall_ruling(e,c,*,action_id,expected_current_state,disposition,hp_loss_applied,temp_hp_loss_applied,injury_delta_applied,reason,continuation_reason):
    """Receipt for externally applied GM consequences; never rerolls the fall."""
    event=c.spec.get("_fall_events",{}).get(action_id)
    if not event or not event.get("status","").startswith("pending_heavy_composition"):
        raise ValueError("no unresolved fall with this actual identity")
    if disposition not in ("resolved_externally","cancelled_by_ruling"):
        raise ValueError("explicit environmental continuation disposition required")
    for value,label in ((reason,"source/order ruling"),(continuation_reason,"remaining fall consequences")):
        if not isinstance(value,str) or not value.strip():raise ValueError(label+" required")
    C.integer(hp_loss_applied,"externally applied HP loss",0)
    C.integer(temp_hp_loss_applied,"externally applied temporary HP loss",0)
    C.integer(injury_delta_applied,"externally applied injury delta")
    current=observe(c);before=event["pending_observed"]
    if expected_current_state!=current:raise ValueError("adjudicated environmental state drift")
    if (before["hp"]-current["hp"],before["temp_hp"]-current["temp_hp"],current["injuries"]-before["injuries"])!=(hp_loss_applied,temp_hp_loss_applied,injury_delta_applied):
        raise ValueError("declared environmental consequences do not match actual applied state")
    receipt={"action_id":action_id,"disposition":disposition,"reason":reason,"continuation_reason":continuation_reason,
        "hp_loss_applied":hp_loss_applied,"temp_hp_loss_applied":temp_hp_loss_applied,"injury_delta_applied":injury_delta_applied,
        "before":deepcopy(before),"after":deepcopy(current),"pending_stage":event["status"],"source_conformance_proven":False}
    event["status"]="resolved_by_external_ruling";event["resolution"]=receipt
    e.gm._rec("낙하 후속 판정",before,current,reason+" / "+continuation_reason,c)
    return deepcopy(receipt)


def boundary(e):
    import passive_events as PASSIVE
    import heavy_injury_adapter as HEAVY
    PASSIVE.ensure_clear(e);HEAVY.ensure_clear(e)


def protected_injuries(c):
    state=c.spec.get("_respiration") or {}
    n=state.get("protected_injuries",0)
    C.integer(n,"protected suffocation injuries",0)
    if n>c.injuries:raise ValueError("suffocation injury provenance needs explicit GM reconciliation")
    return n


def _gilled(e,c):
    import state_grants as GRANTS
    names={str(x).removeprefix("capability/") for x in GRANTS.effective_capabilities(c)}
    if not names.intersection({"아가미","Gilled","gilled"}):return False
    selected(e,"capability/아가미")
    return True


def _breathes(e,c,state):
    import environment_derive as ED
    state=ED.respiration(e,c,state)
    import environmental_capabilities as CAPABILITIES
    return (CAPABILITIES.breathless(e,c) or state["air_available"]
            or (state["medium"]=="water" and _gilled(e,c)))


def _target_count(state,at):
    elapsed=at-state["deprivation_started_at"]-(state.get("grace_seconds",60)-60)
    if state["timing_policy"] is None:
        if elapsed>=60:raise ValueError("suffocation first-injury phase at 60/70 seconds needs an explicit timing policy")
        return 0
    first=TIMINGS[state["timing_policy"]]
    return max(0,M.ratio(elapsed-first,10)+1)


def preflight_advance(e,c,seconds):
    import environmental_capabilities as CAPABILITIES
    CAPABILITIES.preflight_advance(e,c,seconds)
    import environment_derive as ED
    if ED.bound(e,c) and not c.spec.get("_respiration"):
        actual=ED.context(e,c)
        if actual['air_available'] is not True:raise ValueError('current region requires actual timed breathing observation')
    validate_respiration(c)
    state=c.spec.get("_respiration")
    if not state:return
    selected(e,SUFFOCATION);protected_injuries(c)
    if _breathes(e,c,state)!=state["breathing"]:
        raise ValueError("changed breathing capability needs a new timed world observation")
    if state["breathing"]:return
    import trainer_capabilities as TRAINER
    if state.get("grace_seconds",60)!=TRAINER.breath_grace(c,state["medium"],engine=e):
        raise ValueError("changed breath-holding capability needs a new timed world observation")
    if len(e.unresolved_time_intervals)>state["unknown_interval_index"]:
        raise ValueError("unknown elapsed deprivation needs explicit GM time reconciliation")
    _target_count(state,e.elapsed_seconds+seconds)


def _add_injuries(e,c,amount):
    if not amount:return 0
    import actor_templates as TEMPLATES
    if TEMPLATES.injuries_immune(c):
        e.log(f"  {c.name}: 질식 부상 {amount} 면역",SUFFOCATION)
        return 0
    import precise_actions as PRECISE
    retained=PRECISE.gain_injury(e,c,amount,SUFFOCATION)
    e.log(f"  {c.name}: 질식 부상 +{retained} (호흡 외 치유 불가)",SUFFOCATION)
    e.check_fainted(c)
    return retained


def advance(e,c):
    import environmental_capabilities as CAPABILITIES
    CAPABILITIES.advance(e,c)
    state=c.spec.get("_respiration")
    if not state or state["breathing"]:return
    total=_target_count(state,e.elapsed_seconds)
    gained=total-state["applied_injuries"]
    state["applied_injuries"]=total
    retained=_add_injuries(e,c,gained)
    state["protected_injuries"]+=retained
    prevented=gained-retained
    if prevented:state['prevented_injuries']=state.get('prevented_injuries',0)+prevented


def observe_breathing(e,c,*,air_available,medium,reason,timing_policy=None,round_offset_seconds=None):
    boundary(e);selected(e,SUFFOCATION)
    if type(air_available)is not bool:raise ValueError("air availability must be explicit boolean")
    if medium not in ("water","airless","air"):raise ValueError("explicit breathing medium required")
    if not isinstance(reason,str) or not reason.strip():raise ValueError("GM breathing observation reason required")
    if timing_policy not in (None,*TIMINGS):raise ValueError("unknown suffocation timing policy")
    if e.round_start_seconds is not None and round_offset_seconds is None:
        return C.PendingDecision("within-round breathing observation needs an explicit round timestamp")
    if round_offset_seconds is not None:
        C.integer(round_offset_seconds,"round offset",0,10)
        if e.round_start_seconds is None:raise ValueError("round timestamp requires an open round")
        if e.round_start_seconds+round_offset_seconds<e.elapsed_seconds:raise ValueError("breathing timestamp cannot go backwards")
    old=c.spec.get("_respiration")
    if old:
        protected_injuries(c)
        if not old["breathing"] and len(e.unresolved_time_intervals)>old["unknown_interval_index"]:
            return C.PendingDecision("GM unknown deprivation interval; exact elapsed time must be reconciled before breathing recovery")
        if timing_policy is not None and old["applied_injuries"]+old.get("prevented_injuries",0) and timing_policy!=old["timing_policy"]:
            raise ValueError("cannot change suffocation timing after injuries have been applied")
    import trainer_capabilities as TRAINER
    grace=TRAINER.breath_grace(c,medium,engine=e)
    grace_source="edge/수영-선수" if medium=="water" and TRAINER.has_edge(c,"edge/수영-선수") else SUFFOCATION
    import environment_derive as ED
    ED.respiration(e,c,dict(air_available=air_available,medium=medium))
    effective=_breathes(e,c,dict(air_available=air_available,medium=medium))
    if effective:grace-=old.get('style_extension',0) if old else 0
    # Choosing a previously unresolved phase is an explicit policy input, not a
    # new breath. Advance preflight must see it before crossing the boundary.
    previous_policy=old["timing_policy"] if old else None
    if old and timing_policy is not None:old["timing_policy"]=timing_policy
    try:
        if round_offset_seconds is not None and e.round_start_seconds+round_offset_seconds!=e.elapsed_seconds:
            e.at_round_offset(round_offset_seconds)
    except BaseException:
        if old:old["timing_policy"]=previous_policy
        raise
    e.time_actors([c])
    continuous=bool(old and not old["breathing"] and not effective)
    state=deepcopy(old) if continuous else {
        "source":SUFFOCATION,"deprivation_started_at":None if effective else e.elapsed_seconds,
        "protected_injuries":0,"applied_injuries":0,"prevented_injuries":0,"timing_policy":timing_policy,
        "unknown_interval_index":len(e.unresolved_time_intervals)}
    if effective and old and old["protected_injuries"]:
        recovered=old["protected_injuries"]
        c.injuries-=recovered
        import injury_recovery as INJURY
        INJURY.observe_actor(e,c,recovered_change=True)
        e.log(f"  {c.name}: 호흡 재개, 질식 부상 {recovered} 치료",SUFFOCATION)
        c.spec.setdefault("injury_healing_history",[]).append({"source":SUFFOCATION,"count":recovered,"known_elapsed_seconds":e.elapsed_seconds})
    state.update(air_available=air_available,medium=medium,breathing=effective,reason=reason,observed_at=e.elapsed_seconds,
                 grace_seconds=grace,grace_source=grace_source)
    if timing_policy is not None:state["timing_policy"]=timing_policy
    c.spec["_respiration"]=state
    e.check_fainted(c)
    return deepcopy(state)


def _natural_sky(e,c,world_fact=None,reason=None):
    if c.kind=="trainer":
        if world_fact not in (None,False):raise ValueError("natural Sky injury exception applies only to Pokemon")
        return False,{"kind":"trainer"}
    species=e.r.species.get(c.spec.get("species"))
    if species is not None and species.get("_source"):
        natural=species.get("movement",{}).get("sky",0)>0
        if world_fact is not None and world_fact!=natural:raise ValueError("natural Sky assertion conflicts with selected species evidence")
        return natural,{"species":species["id"],"source":deepcopy(species["_source"]),"base_sky":species.get("movement",{}).get("sky",0)}
    if type(world_fact)is not bool or not isinstance(reason,str) or not reason.strip():
        raise ValueError("Pokemon natural Sky requires selected species/base evidence or explicit GM natural-capability fact")
    return world_fact,{"kind":"GM natural-capability fact","reason":reason}


def _dice(e,expr,fixed):
    result=POOLS.expression(e.rng,expr,fixed=fixed)
    return result['total'],result['faces']


def _fall_defense(e,c):
    import effects as FX
    import effect_lifetimes as LIFETIMES,stat_ace as STAT
    dr=c.damage_reduction+LIFETIMES.numeric(c,'damage_reduction')+STAT.damage_reduction(e,c)+__import__('defense_curl').reduction(c)+__import__('declarative_move_contracts').defensive_reduction(c)
    for modifier in c.modifiers:
        if modifier.get("type")!="damage_reduction":continue
        scope=modifier.get("_scope")
        if scope:
            if scope.get("type"):continue # Typeless has no matching Pokemon type.
            if scope.get("class")=="원거리":raise ValueError("falling versus ranged-only reduction needs a sourced composition policy")
            if scope.get("class") in (None,"물리"):dr+=modifier["value"]
        elif not c.abilities_suppressed and modifier.get("if_weather") and isinstance(modifier.get("value"),int) and not any(modifier.get(k) for k in ("if","vs","duration")) and FX.weather_matches(e,modifier["if_weather"],c) and not __import__("survivalist_class").weather_ability_suppressed(e,c,modifier.get("_rule_id")):
            dr+=modifier["value"]
    return c.staged("def"),dr


def fall(e,c,*,action_id,meters,intentional,reason,acrobatics=False,acrobatics_options=None,
         surface_meters=0,surface_dice=None,surface_reason=None,fixed_damage=None,fixed_surface=None,
         high_jump_boost=False,boost_options=None,running_start=False,running_reason=None,running_bonus_included=None,
         natural_sky=None,natural_sky_reason=None,acrobatics_injury_policy=None,same_jump_id=None):
    """Resolve one actual GM-observed fall. No attack stat, STAB, AC or type chart.

    This environmental event does not grant movement or a new jump action. Each
    optional roll belongs to this same identified fall; past jump boosts cannot
    be reused. Fractional-meter DB rounding remains an explicit world decision.
    """
    boundary(e);selected(e,FALL)
    import temporary_hp as TEMP_HP
    import common_action_checks as COMMON
    import skill_feature_actions as SF
    TEMP_HP.ensure_certain(e,c)
    for value,label in ((action_id,"fall action identity"),(reason,"GM actual fall reason")):
        if not isinstance(value,str) or not value.strip():raise ValueError(label+" required")
    if action_id in c.spec.get("_fall_events",{}):raise ValueError("fall already resolved; identity cannot be replayed")
    C.integer(meters,"actual fall meters",0);C.integer(surface_meters,"GM surface distance adjustment")
    for value,label in ((intentional,"intentional jump"),(acrobatics,"optional falling Acrobatics"),(high_jump_boost,"same-jump High Jump increase")):
        if type(value)is not bool:raise ValueError(label+" must be explicit boolean")
    if acrobatics_injury_policy not in (None,"damage_only","distance"):
        raise ValueError("unknown falling Acrobatics injury-distance policy")
    if (surface_meters or surface_dice) and (not isinstance(surface_reason,str) or not surface_reason.strip()):
        raise ValueError("GM surface adjustment reason required")
    if surface_dice is not None:
        import re
        if not isinstance(surface_dice,str) or not re.fullmatch(r"[1-9]\d*d[1-9]\d*(?:\+\d+)?",surface_dice):raise ValueError("explicit GM surface damage dice required")
    elif fixed_surface is not None:raise ValueError("surface faces require an actual surface damage expression")
    weight=C.integer(c.weight_class,"actual Weight Class",1,7)
    natural,evidence=_natural_sky(e,c,natural_sky,natural_sky_reason)
    base_jump=0
    jump_record=None
    if same_jump_id is not None:
        jump_record=c.spec.get('_jump_attempts',{}).get(same_jump_id)
        if (not intentional or not isinstance(jump_record,dict) or jump_record.get('landed') is not True or
            'launch_altitude' not in jump_record or c.pos!=tuple(jump_record['destination']) or
            c.spec.get('_movement_altitude',0)!=jump_record['landing_altitude'] or
            action_id!='jump-fall:'+same_jump_id or meters!=jump_record['launch_altitude']+jump_record['apex_height']-jump_record['landing_altitude']):
            raise ValueError('same-jump falling requires the actual landed jump and its exact observed descent')
        if high_jump_boost or boost_options or running_start or running_reason is not None or running_bonus_included is not None:
            raise ValueError('actual jump already owns its High Jump increase and running allowance')
        base_jump=jump_record['effective_limits']['high_jump']
        C.integer(base_jump,'actual same-jump High Jump allowance',0)
    elif intentional:
        import trainer_capabilities as TRAINER
        from physical_limits import number
        mv=TRAINER.values(c) if c.spec.get("movement_basis")=="trainer_base" else c.spec.get("movement",{})
        if c.kind=="trainer" and c.spec.get("movement_basis")=="base":mv=TRAINER.jump_bonuses(c,mv)
        base_jump=number(mv.get("high_jump"),"current High Jump",minimum=0)
        base_jump=TRAINER.for_jump(c,{"high_jump":base_jump},running_start=running_start,running_reason=running_reason,running_bonus_included=running_bonus_included)["high_jump"]
        if type(base_jump)is not int:raise ValueError("fractional High Jump requires an explicit integral falling-distance adjudication")
    elif high_jump_boost or boost_options or running_start or running_reason is not None or running_bonus_included is not None:
        raise ValueError("jump allowances require this actual fall to be an intentional jump")
    acrobatics_options=dict(acrobatics_options or {});boost_options=dict(boost_options or {})
    if not acrobatics and acrobatics_options:raise ValueError("falling roll options require an actual optional check")
    if not high_jump_boost and boost_options:raise ValueError("boost options require this same jump increase attempt")
    plans=[]
    if high_jump_boost:plans.append(("jump_boost",16,boost_options))
    if acrobatics:plans.append(("falling_acrobatics",12 if intentional else 20,acrobatics_options))
    ids=[o.get("roll_id") for _,_,o in plans if o.get("roll_id") is not None]
    if len(ids)!=len(set(ids)):raise ValueError("High Jump increase and falling Acrobatics require distinct roll identities")
    featured=any(o.get('feature') is not None for _,_,o in plans)
    inflight=c.spec.get('_fall_skill_inflight')
    if inflight is not None and (not featured or inflight['action_id']!=action_id):raise ValueError('resume the actually observed fall before declaring another fall')
    if featured and (len(ids)!=len(plans) or any(not isinstance(uid,str) or not uid.strip() for uid in ids)):
        raise ValueError('falling feature requires actual distinct check roll identities')
    for _,_,opts in plans:
        prepared=SF.prepared_for_sequence(e,c,'곡예',opts) if featured else e._prepare_skill_roll(c,'곡예',**opts)
        if prepared[3] is not None:opts["fixed"]=prepared[3]
        if prepared[4] is not None:opts["fixed_penalties"]=prepared[4]
    defense,dr=_fall_defense(e,c)
    # The falling/physical-attack comparison does not settle all generic ability
    # resistance and reactive-attack compositions. Do not silently ignore them.
    def relevant_resistance(x):
        if x.get("type")=="resistance_step":
            return x.get("vs")=="physical" or x.get("if")=="hp full" and LIFE.at_full_hp(c) or not any(x.get(k) for k in ("types","vs","if"))
        if x.get("type")=="absorb":return x.get("move_type") in ("Typeless","무타입")
        if x.get("type")=="immunity":return x.get("to") in ("Typeless","무타입","physical","물리","all damage")
        return False
    if not c.abilities_suppressed and any(relevant_resistance(x) for x in c.modifiers):
        return C.PendingDecision("falling Typeless Physical damage versus applicable ability resistance/immunity needs source composition")
    def observe_prefix(staged,c,plans):
        return [staged.skill_roll(c,'곡예',**plans[0][2])] if plans else []
    def calculate(staged,c,plans,observed=None):
        checks={}
        for index,(key,dc,opts) in enumerate(plans):
            roll=observed[index] if observed is not None and index<len(observed) else staged.skill_roll(c,'곡예',**opts)
            checks[key]=SF.resolve_check(staged,c,'곡예',dc,roll,opts);SF.finish(staged,c,opts.get('roll_id'))
        jump=base_jump+int(bool(checks.get("jump_boost") and checks["jump_boost"].passed))
        distance=max(0,meters-__import__('martial_artist').fall_reduction(staged,c)-jump+surface_meters)
        acro=int(bool(checks.get("falling_acrobatics") and checks["falling_acrobatics"].passed))
        endurance=getattr(staged,'_style_endurance_fall',None)
        ignored=endurance[1] if endurance is not None and endurance[0] is c else 0
        damage_distance=max(0,distance-acro-ignored)
        unit=3 if natural else 2
        injuries_before=M.ratio(distance,unit) if distance>=4 else 0
        injuries_after=M.ratio(damage_distance,unit) if damage_distance>=4 else 0
        if (acro or ignored) and injuries_before!=injuries_after and acrobatics_injury_policy is None:
            raise ValueError("ignored falling distance changes height-injury boundary; explicit injury-distance policy required")
        height_injuries=injuries_after if acrobatics_injury_policy=="distance" else injuries_before
        import survivalist_features as SURVIVALIST
        damage_distance,height_injuries,terrain_distance_reduction,terrain_injury_reduction=\
            SURVIVALIST.fall_adjustment(staged,c,damage_distance,height_injuries)
        db=min(20 if weight<=2 else 28,damage_distance*(1 if weight<=2 else 2))
        damage_roll=0;faces=[];expr=None
        if db:
            expr=staged.r.mech("combat/damage-chart")["by_damage_base"][str(db)]["dice"]
            damage_roll,faces=_dice(staged,expr,fixed_damage)
        elif fixed_damage not in (None,[],()):raise ValueError("no base falling damage dice at zero effective distance")
        extra,extra_faces=_dice(staged,surface_dice,fixed_surface) if surface_dice else (0,[])
        damage=max(1,damage_roll+extra-defense-dr) if db or surface_dice else 0
        if __import__('setup_move_state').physical_immunity(c,'물리'):damage=0
        return dict(source=FALL,action_id=action_id,meters=meters,weight_class=weight,intentional=intentional,
            reason=reason,checks=checks,high_jump=jump,base_high_jump=base_jump,natural_sky=natural,
            natural_sky_evidence=evidence,surface_meters=surface_meters,surface_reason=surface_reason,
            damage_distance=damage_distance,injury_distance=damage_distance if acrobatics_injury_policy=="distance" else distance,
            acrobatics_injury_policy=acrobatics_injury_policy,damage_base=db,dice=expr,faces=faces,
            terrain_distance_reduction=terrain_distance_reduction,terrain_injury_reduction=terrain_injury_reduction,
            surface_dice=surface_dice,surface_faces=extra_faces,raw_damage=damage_roll+extra,
            defense=defense,damage_reduction=dr,damage=damage,height_injuries=height_injuries)
    if featured:
        basis=dict(source=FALL,action_id=action_id,meters=meters,intentional=intentional,reason=reason,
            surface_meters=surface_meters,surface_dice=surface_dice,surface_reason=surface_reason,
            natural_sky=natural,natural_sky_evidence=evidence,base_high_jump=base_jump,
            high_jump_boost=high_jump_boost,acrobatics=acrobatics,weight=weight,defense=defense,dr=dr,
            round=e.round_no,elapsed_seconds=e.elapsed_seconds)
        if inflight is not None:
            if inflight['basis']!=basis:raise ValueError('cannot change the actual observed fall')
            if inflight.get('injury_policy') is not None and inflight['injury_policy']!=acrobatics_injury_policy:
                raise ValueError('cannot replace the chosen injury-distance policy')
        else:
            inflight={'action_id':action_id,'basis':deepcopy(basis),'injury_policy':None}
            c.spec['_fall_skill_inflight']=inflight
        if acrobatics_injury_policy is not None:inflight['injury_policy']=acrobatics_injury_policy
        sequence_key='fall:'+c.spec.get('id',c.name)+':'+action_id
        def finish_observed(rolls):
            # SF.sequence already owns these actual durable observations.
            if COMMON._has_help_offers(e,(c,)):return calculate(e,c,plans,rolls)
            return COMMON._staged_rolls(e,calculate,actors=(c,),payload=(c,plans,rolls))
        try:
            result=SF.sequence(e,sequence_key,basis,[(c,'곡예',opts) for _,_,opts in plans],finish_observed)
        finally:
            if sequence_key not in getattr(e,'_skill_sequences',{}):c.spec.pop('_fall_skill_inflight',None)
        c.spec.pop('_fall_skill_inflight',None)
    else:result=COMMON._rolls_before_help(e,calculate,observe_prefix if plans else None,actors=(c,),payload=(c,plans))
    # Save the actual outcome before any potential adjudication boundary. A new
    # request cannot reroll this real fall merely because an exception is pending.
    result["status"]="calculated"
    if same_jump_id is not None:result['same_jump_id']=same_jump_id
    c.spec.setdefault("_fall_events",{})[action_id]=result
    e.time_actors([c])
    import nicolette_gym as NICOLETTE
    NICOLETTE.enter_cell(e,c,"fall")
    import ice_lake as ICE_LAKE
    ICE_LAKE.enter(e,c,actual_fall=True)
    # No fictitious attacker is introduced to satisfy the existing attack-only
    # producer certificate. Heavy-injury composition is explicitly separate.
    if c.injuries>=5:
        result["status"]="pending_heavy_composition"
        result["pending_observed"]=observe(c)
        return C.PendingDecision("falling versus existing heavy-injury attack trigger/order",basis=deepcopy(result))
    before=c.injuries
    e.take_damage(c,result["damage"])
    result["damage_injuries"]=c.injuries-before
    import actor_templates as TEMPLATES
    result["height_injuries_prevented"]=result["height_injuries"] if TEMPLATES.injuries_immune(c) else 0
    result["height_injuries"]-=result["height_injuries_prevented"]
    import precise_actions as PRECISE
    result['retained_height_injuries']=PRECISE.gain_injury(e,c,result["height_injuries"],FALL)
    e.check_fainted(c)
    result["status"]="resolved" if c.injuries<5 else "pending_heavy_composition_after_base_fall"
    e.log(f"  {c.name}: 낙하 DB{result['damage_base']} 피해 {result['damage']}, 높이 부상 +{result['height_injuries']}",FALL)
    if c.injuries>=5:
        result["pending_observed"]=observe(c)
        return C.PendingDecision("base fall applied; whether crossing heavy threshold changes this fall requires source ordering",basis=deepcopy(result))
    return deepcopy(result)



def validate_respiration(c):
    row=c.spec.get('_respiration')
    if row is None:return
    if not isinstance(row,dict) or row.get('source')!=SUFFOCATION:raise ValueError('respiration source required')
    for key in ('air_available','breathing'):
        if type(row.get(key)) is not bool:raise ValueError('explicit respiration '+key+' required')
    if row.get('medium') not in ('water','airless','air'):raise ValueError('respiration medium required')
    if row.get('timing_policy') not in (None,*TIMINGS):raise ValueError('unknown suffocation phase')
    for key in ('protected_injuries','applied_injuries','unknown_interval_index','observed_at'):
        C.integer(row.get(key),'respiration '+key,0)
    C.integer(row.get('prevented_injuries',0),'respiration prevented_injuries',0)
    C.integer(row.get('grace_seconds'),'respiration grace',60)
    if row.get('grace_source') not in (SUFFOCATION,'edge/수영-선수'):raise ValueError('unknown breath-holding source')
    if not isinstance(row.get('reason'),str) or not row['reason'].strip():raise ValueError('actual breathing observation reason required')
    if row['breathing']:
        if row.get('deprivation_started_at') is not None or row['protected_injuries'] or row['applied_injuries'] or row.get('prevented_injuries',0):
            raise ValueError('breathing state cannot retain deprivation injury debt')
    else:
        C.integer(row.get('deprivation_started_at'),'deprivation start',0)
        if row['deprivation_started_at']>row['observed_at']:raise ValueError('deprivation starts after its observation')
        C.integer(row.get('prevented_injuries',0),'prevented suffocation injuries',0)
        if row['protected_injuries']+row.get('prevented_injuries',0)!=row['applied_injuries']:raise ValueError('unrecovered suffocation provenance mismatch')
    protected_injuries(c)


def validate_world(engine,actors):
    import ice_lake as ICE_LAKE
    ICE_LAKE.validate_world(engine,actors)
    import environmental_capabilities as CAPABILITIES
    CAPABILITIES.validate_world(engine,actors)
    for c in actors.values():
        validate_respiration(c);row=c.spec.get('_respiration')
        if row is not None and (row['observed_at']>engine.elapsed_seconds or row['unknown_interval_index']>len(engine.unresolved_time_intervals)):
            raise ValueError('respiration claims unobserved world time')
