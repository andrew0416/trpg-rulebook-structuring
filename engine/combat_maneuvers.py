"""Concrete combat maneuvers; source durations and explicit GM overrides stay distinct."""
import arithmetic_policy as M
import common_checks as CHECKS
import turn as TURN
import combat_timing as TIMING
import temporary_hp as TEMP_HP
import maneuver_edges as EDGES
import action_lifecycle as ACTION

SOURCE="maneuver/치사한-짓"
TRICKS={"hinder":("육상","둔화"),"blind":("은신","실명"),"low_blow":("곡예","취약")}
ALIASES={"저지하기":"hinder","눈 멀게하기":"blind","로우 블로":"low_blow"}

@ACTION.continued_maneuver(SOURCE)
def dirty_trick(engine,actor,target,trick,*,fixed_accuracy=None,challenger_options=None,
                defender_options=None,duration_policy=None,policy_reason=None):
    from grid import cheb
    import skill_maneuver_actions as SM
    trick=ALIASES.get(trick,trick)
    rogue=__import__('rogue').dirty_context(engine,actor,target)
    trickster=__import__('trickster').maneuver_context(engine,actor,target)
    if trick not in TRICKS:raise ValueError("unknown Dirty Trick selection")
    if engine.r._selected_rule(SOURCE)!=SOURCE:raise ValueError("selected Dirty Trick variant requires its own policy")
    if actor is target or actor.kind not in ("trainer","pokemon") or target.kind not in ("trainer","pokemon"):
        raise ValueError("Dirty Trick needs two distinct trainer/Pokemon actors")
    if not engine.encounter_active or engine.round_start_seconds is None:
        raise ValueError("Dirty Trick requires an active combat round")
    if not SM.native_reaction_resume(engine,actor,target,SOURCE) and (engine.grid is None or not engine.adjacent(actor,target) or not actor.on_field or not target.on_field or target.captured):
        raise ValueError("Dirty Trick requires one adjacent on-field target")
    if rogue is None and trickster is None and (actor.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(actor)):raise ValueError("heavy Standard Dirty Trick needs its event ordering adapter")
    if not SM.resuming(actor,SOURCE,challenger_options or {}) and any(t==trick and victim is target for t,victim in actor.custom_conditions.get("dirty_trick_uses",[])):
        raise ValueError("this Dirty Trick has already been used on this target this scene")
    if trick in ("hinder","low_blow"):
        # Both PTK437/439 and PTU241 attach one duration to the joined effects.
        # A split lifetime is an explicit GM alternative, never the source default.
        if duration_policy is None:duration_policy="combined"
        if duration_policy not in ("combined","split"):
            raise ValueError("Dirty Trick duration policy must be combined or explicit GM split")
        if duration_policy=="split" and (not isinstance(policy_reason,str) or not policy_reason.strip()):
            raise ValueError("Dirty Trick split duration requires an explicit GM reason")
    elif duration_policy not in (None,"combined"):
        raise ValueError("Blind has one explicit one-round duration")
    if trick in ("hinder","blind"):count=TIMING.current(engine)
    if trick=="hinder" and any(x.get("skill_modifier") for x in TIMING.records(target)):
        raise ValueError("overlapping Hinder penalties need an explicit stacking policy")
    TEMP_HP.ensure_certain(engine,actor);TEMP_HP.ensure_certain(engine,target)
    if fixed_accuracy is not None:CHECKS.integer(fixed_accuracy,"Dirty Trick d20",1,20)
    skill,status=TRICKS[trick]
    success_only=EDGES.success_only(engine,actor,target,SOURCE)
    opts_a=EDGES.options(engine,actor,SOURCE,challenger_options)
    opts_a=__import__('survivalist_class').maneuver_skill_options(engine,actor,SOURCE,opts_a)
    opts_b=EDGES.options(engine,target,SOURCE,defender_options)
    if opts_a.get("roll_id") is not None and opts_a.get("roll_id")==opts_b.get("roll_id"):
        raise ValueError("opposed rolls require distinct identities")
    plans=[(actor,skill,opts_a),(target,skill,opts_b)]
    featured=any(o.get('feature') is not None for o in (opts_a,opts_b))
    if not featured:
        for c,opts in ((actor,opts_a),(target,opts_b)):
            prepared=engine._prepare_skill_roll(c,skill,**opts)
            if prepared[3] is not None:opts['fixed']=prepared[3]
            if prepared[4] is not None:opts['fixed_penalties']=prepared[4]
    prepared=SM.prepare(engine,actor,target,SOURCE,{'trick':trick,'duration_policy':duration_policy,'policy_reason':policy_reason,'fixed_accuracy':fixed_accuracy,'count':count if trick in ('hinder','blind') else None,'rogue_completion':rogue['completion'] if rogue else None},plans)
    def outcome(won):
        result=_dirty_trick_outcome(engine,actor,target,trick,status,duration_policy,policy_reason,count if trick in ('hinder','blind') else None) if won else False
        if success_only:EDGES.charge_on_success(actor,target,SOURCE,trick,'dirty_trick_uses',result)
        if result and not isinstance(result,CHECKS.PendingDecision):
            import stat_ace as STAT
            STAT.maneuver_success(engine,actor,target,SOURCE)
        return result
    def spend():
        if trickster is not None:__import__('trickster').maneuver_spend(engine,actor,target)
        elif not __import__('rogue').dirty_spend(engine,actor,target,trick):return False
        if not success_only:actor.custom_conditions.setdefault('dirty_trick_uses',[]).append((trick,target))
        return True
    move={'id':SOURCE,'name':'치사한 짓: '+trick,'type':'노말','class':'변화','ac':2,'range':'근접, 대상1','keywords':[]}
    def accuracy():
        import precise_actions as PRECISE
        event=PRECISE.attacked(engine,actor,target,move,producer='combat_maneuver')
        if rogue is not None or trickster is not None:hit,natural=True,None
        else:hit,natural,_=engine.accuracy_check(actor,target,move,fixed_roll=fixed_accuracy)
        PRECISE.accuracy(event,hit,natural=natural)
        return hit
    return SM.run(engine,actor,prepared,attack=move,spend=spend,
        aoo=lambda:TURN.trigger_aoo(engine,actor,'치사한 짓',[x for x in TURN.adjacent_enemies(engine,actor) if x is not target]),
        can_continue=lambda:TURN.can_act(engine,actor),accuracy=accuracy,outcome=outcome,
        opposed=lambda:engine.opposed_check(actor,skill,target,skill,challenger_options=opts_a,defender_options=opts_b))


def _dirty_trick_outcome(engine,actor,target,trick,status,duration_policy,policy_reason,count):
    record={"source":SOURCE,"trick":trick,"duration_policy":duration_policy or "combined","policy_reason":policy_reason}
    if trick in ("hinder","low_blow"):
        record["duration_origin"]="gm_override" if duration_policy=="split" else "source_comparison_ptk_ptu241"
        if duration_policy=="split":
            engine.rulings.record("duration_adjudication",SOURCE,"combined",duration_policy,policy_reason,"once")
            engine.log(f"  GM 기간 대체재정 split: {policy_reason}",SOURCE)
        else:engine.log("  원문 기간: 상태와 부가효과에 같은 종료점 적용 (PTK / PTU241)",SOURCE)
    if duration_policy=="split":
        engine.apply_status(target,status);record["statuses"]=[]
    else:record["statuses"]=[status]
    if trick in ("hinder","blind"):record["count_deadline"]=(engine.round_no+1,count)
    if trick=="hinder":record["skill_modifier"]=-2
    if trick=="low_blow":
        record.update(initiative_zero=True,turn_owner=actor,turn_deadline=actor.custom_conditions.get("combat_turn_serial",0)+1)
    _install_from_actor(engine,actor,target,record)
    if trick=="blind" and not record["owned_statuses"]:
        TIMING.expire(engine,target,record)
        return False
    return True


MANIPULATE="maneuver/술수"
MANIPULATIONS={'bon_mot':('교활','난동'),'flirt':('매력','헤롱헤롱'),'terrorize':('협박',None)}
MANIP_ALIASES={'재담':'bon_mot','추파 던지기':'flirt','위협하기':'terrorize'}

def flirt_existing(engine,actor,target):
    """A repeated Flirt may extend the same beloved; another beloved remains unresolved."""
    if '헤롱헤롱' not in target.conditions:return False
    import condition_instances as CONDITIONS
    if not CONDITIONS.beloved(target):raise ValueError('existing Infatuation requires its actual beloved source')
    CONDITIONS.prepare(engine,target,'헤롱헤롱',applied_by=actor)
    return True


@ACTION.continued_maneuver(MANIPULATE)
def manipulate(engine,actor,target,kind,*,defender_skill,fixed_accuracy=None,challenger_options=None,defender_options=None,_provocateur_quick=False):
    import body_state as BODY
    import skill_modifiers as SKILL
    import skill_maneuver_actions as SM
    trickster=__import__('trickster').maneuver_context(engine,actor,target)
    if _provocateur_quick:__import__('provocateur')._live(engine,actor,__import__('provocateur').QUICK)
    kind=MANIP_ALIASES.get(kind,kind)
    if kind not in MANIPULATIONS:raise ValueError('unknown Manipulate selection')
    if engine.r._selected_rule(MANIPULATE)!=MANIPULATE:raise ValueError('selected Manipulate variant requires its own policy')
    if (actor.kind!='trainer' and trickster is None) or actor is target or target.kind not in ('trainer','pokemon'):
        raise ValueError('Manipulate requires a trainer and distinct trainer/Pokemon target')
    if not engine.encounter_active or engine.round_start_seconds is None:raise ValueError('Manipulate requires an active combat round')
    if not SM.native_reaction_resume(engine,actor,target,MANIPULATE) and (engine.grid is None or not actor.on_field or not target.on_field or target.captured or not BODY.in_range(engine,actor,target,6)):
        raise ValueError('Manipulate requires one visible on-field target within six metres')
    if not _provocateur_quick and trickster is None and (actor.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(actor)):raise ValueError('heavy Standard Manipulate needs its event ordering adapter')
    if not SM.resuming(actor,MANIPULATE,challenger_options or {}) and any(k==kind and victim is target for k,victim in actor.custom_conditions.get('manipulate_uses',[])):
        raise ValueError('this Manipulation has already been used on this target this scene')
    existing_flirt=kind=='flirt' and flirt_existing(engine,actor,target)
    if not existing_flirt and any(record.get('source')==MANIPULATE and record.get('manipulation')==kind for record in TIMING.records(target)):
        raise ValueError('overlapping same Manipulation needs an explicit composition policy')
    skill,status=MANIPULATIONS[kind]
    if SKILL.skill_id(engine.r.skill_policy,defender_skill) not in {SKILL.skill_id(engine.r.skill_policy,x) for x in (skill,'집중')}:
        raise ValueError('Manipulate defender must choose the named skill or Focus')
    count=TIMING.current(engine)
    TEMP_HP.ensure_certain(engine,actor);TEMP_HP.ensure_certain(engine,target)
    if fixed_accuracy is not None:CHECKS.integer(fixed_accuracy,'Manipulate d20',1,20)
    success_only=EDGES.success_only(engine,actor,target,MANIPULATE)
    opts_a=EDGES.options(engine,actor,MANIPULATE,challenger_options)
    opts_a=__import__('survivalist_class').maneuver_skill_options(engine,actor,MANIPULATE,opts_a)
    opts_b=EDGES.options(engine,target,MANIPULATE,defender_options)
    if opts_a.get('roll_id') is not None and opts_a.get('roll_id')==opts_b.get('roll_id'):
        raise ValueError('opposed rolls require distinct identities')
    challenger=trickster['trainer'] if trickster else actor
    challenger_skill='교활' if trickster else skill
    plans=[(challenger,challenger_skill,opts_a),(target,defender_skill,opts_b)]
    if not any(o.get('feature') is not None for o in (opts_a,opts_b)):
        for c,sk,opts in plans:
            prepared=engine._prepare_skill_roll(c,sk,**opts)
            if prepared[3] is not None:opts['fixed']=prepared[3]
            if prepared[4] is not None:opts['fixed_penalties']=prepared[4]
    prepared=SM.prepare(engine,actor,target,MANIPULATE,{'kind':kind,'defender_skill':SKILL.skill_id(engine.r.skill_policy,defender_skill),'fixed_accuracy':fixed_accuracy,'count':count,'quick_wit':_provocateur_quick},plans,challenger=challenger)
    def spend():
        if trickster is not None:__import__('trickster').maneuver_spend(engine,actor,target)
        elif _provocateur_quick:__import__('provocateur')._spend(engine,actor,__import__('provocateur').QUICK,'swift')
        elif not TURN.spend(engine,actor,'standard','술수: '+kind):return False
        if not success_only:actor.custom_conditions.setdefault('manipulate_uses',[]).append((kind,target))
        return True
    def aoo():
        if not engine.adjacent(actor,target):TURN.trigger_aoo(engine,actor,'인접하지 않은 대상에게 원거리 공격')
    move={'id':MANIPULATE,'name':'술수: '+kind,'type':'노말','class':'변화','ac':2,'range':'6, 대상1','keywords':[]}
    def accuracy():
        import precise_actions as PRECISE
        event=PRECISE.attacked(engine,actor,target,move,producer='combat_maneuver')
        if event is not None:event['manipulation']=kind
        if trickster is not None:hit,natural=True,None
        else:hit,natural,_=engine.accuracy_check(actor,target,move,fixed_roll=fixed_accuracy)
        PRECISE.accuracy(event,hit,natural=natural)
        return hit
    def outcome(won):
        result=_manipulate_outcome(engine,actor,target,kind,status,count) if won else False
        if success_only:EDGES.charge_on_success(actor,target,MANIPULATE,kind,'manipulate_uses',result)
        return result
    return SM.run(engine,actor,prepared,attack=move,spend=spend,aoo=aoo,can_continue=lambda:TURN.can_act(engine,actor),accuracy=accuracy,outcome=outcome,
        opposed=lambda:engine.opposed_check(challenger,challenger_skill,target,defender_skill,challenger_options=opts_a,defender_options=opts_b))

def _manipulate_outcome(engine,actor,target,kind,status,count):
    existing_flirt=kind=='flirt' and flirt_existing(engine,actor,target)
    if existing_flirt and engine.immune_to(target,'헤롱헤롱'):return False
    record={'source':MANIPULATE,'manipulation':kind,'count_deadline':(engine.round_no+1,count),'attacker':actor,'statuses':[status] if status else []}
    if kind=='bon_mot':record.update(ap_forbidden=True,save_forbidden=['난동'],forced_attack=True)
    elif kind=='flirt':record.update(save_automatic_failure=['헤롱헤롱'],infatuation_source=actor)
    else:
        TEMP_HP.clear(engine,target,'술수 위협하기')
        record['at_will_moves_only']=True
    _install_from_actor(engine,actor,target,record)
    if kind=='flirt' and not record['owned_statuses'] and not existing_flirt:
        TIMING.expire(engine,target,record)
        return False
    engine.log(f'    {target.name}: 술수 {kind}, 다음 라운드 카운트 {count}까지',MANIPULATE)
    return True

def save_disposition(actor,condition):
    if any(condition in record.get('save_forbidden',()) for record in TIMING.records(actor)):return 'forbidden'
    if any(condition in record.get('save_automatic_failure',()) for record in TIMING.records(actor)):return 'automatic_failure'
    return None

def force_attack(actor):
    if getattr(actor,'_duelist_ignoring',False):return False
    import status_sets as STATUS_SETS
    return STATUS_SETS.forces_damaging_move(actor)

def move_allowed(engine,actor,move):
    import condition_instances as CONDITIONS
    allowed,reason=CONDITIONS.move_allowed(engine,actor,move)
    if not allowed:return allowed,reason
    import frequency as FREQ
    if any(record.get('at_will_moves_only') for record in TIMING.records(actor)) and FREQ.move_frequency(engine,move['id'],actor)[0]!='at_will':
        return False,'위협하기 동안 임의 빈도 기술만 사용 가능'
    if force_attack(actor) and move.get('class') not in ('물리','특수') and not __import__('ace_trainer').supreme(engine,actor,move):
        return False,'재담 난동 중 데미지 기술 또는 발버둥만 사용 가능'
    return True,''

def standard_allowed(actor,kind,native_move=None,engine=None):
    if engine is not None and __import__('breather').staying_permission(engine,actor,kind):return True
    if not force_attack(actor):return True
    budget=getattr(actor,'budget',None)
    standard=kind in ('standard','full') or (kind in ('shift','swift') and budget is not None and budget.get(kind,0)<=0 and budget.get('standard',0)>0)
    if not standard:return True
    return isinstance(native_move,dict) and (native_move.get('class') in ('물리','특수') or (engine is not None and __import__('ace_trainer').supreme(engine,actor,native_move)))

def infatuation_damage(actor,target,move,attack_source,attack_stat_value):
    if getattr(actor,'_duelist_ignoring',False):return attack_stat_value,0
    import condition_instances as CONDITIONS
    sources=CONDITIONS.beloved(actor)
    if '헤롱헤롱' in actor.conditions and not sources:raise ValueError('Infatuation needs its actual beloved before damage resolution')
    if '헤롱헤롱' not in actor.conditions or not sources:return attack_stat_value,0
    targets=move.get('_actual_targets',(target,))
    if any(source is victim for source in sources for victim in targets):
        return (M.ratio(attack_stat_value,2) if attack_source is actor else attack_stat_value),0
    return attack_stat_value,-5


def _install_from_actor(engine,actor,target,record):
    previous=getattr(engine,'_inflictor',None)
    engine._inflictor=actor
    try:return TIMING.install(engine,target,record)
    finally:engine._inflictor=previous
