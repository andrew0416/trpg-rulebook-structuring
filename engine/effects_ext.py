import arithmetic_policy as M
"""
effects.py 확장: DB 의 나머지 effect 유형 100종을 엔진이 소비하게 한다. 세 층으로 나눈다.
  1. 실행(EXEC): 전투 상태를 바로 바꾸는 것 — 아이템·버프·카운터·부상·완전 회복·체력 공유·지연 효과·OHKO·변신·동작·강제 이동·무작위 표·분기(alternate_effect)…
  2. 레지스트리(REGISTRY): 전투원/엔진에 수정자로 올려 두고 판정 훅(명중·데미지·대상 선택·이동·턴 시작/끝)이 조회하는 것 —
     키워드 부여·사거리 치환·명중 치환·회피 무시·방어 수정자 무시·상성 치환·타입 치환·코트·축복·함정·구역·지연 공격·반응(반사/방해/가로채기)·폼 변경·사용 제한·대상 규칙…
  3. GM 프롬프트(PROMPT): 룰북 자체가 GM/플레이어 판단에 맡긴 것 — 엔진은 발동 시점에 "[GM 판단]" 으로 띄우고 engine.gm_prompts 에 쌓는다 (rule, gm, reveal, craft, custom_token, attach, pledge, …).
엔진 훅은 engine.py 가 EXT.* 로 호출한다. 핸들러 등록은 조건·대상·지속시간 구현의 증거가 아니다.
미응답 GM 프롬프트는 보류이며, 실행 완료로 집계하지 않는다.
"""
import heavy_injury_adapter as HEAVY
import temporary_hp as TEMP_HP
import frequency as FREQ
import injury_recovery as INJURY
import re
import held_equipment as HELD
import vortex_state as VORTEX
import roll_pools as POOLS

import effects as FX

TYPES = ["노말", "격투", "비행", "독", "땅", "바위", "벌레", "고스트", "강철", "불꽃", "물", "풀", "전기", "에스퍼", "얼음", "드래곤", "악", "페어리"]
STATUS_WORDS = ["맹독", "독", "화상", "마비", "얼음", "잠듦", "혼란", "풀죽음", "둔화", "구속", "수렁", "넘어짐", "취약", "억압", "난동", "헤롱헤롱", "저주", "사슬묶기", "조이기", "실명", "악몽"]
STAGE_RE = re.compile(r"([+\-]?\d+)\s*(atk|def|spa|spd|spe|acc|eva)|(atk|def|spa|spd|spe|acc|eva)\s*([+\-]\d+)")


def _who(engine, a, t, e, default="target"):
    tg = e.get("target", e.get("on", default))
    if tg in ("self", "user") or (isinstance(tg, str) and tg.startswith("self")):
        return [a]
    if tg in ("self and target", "both"):
        return [a, t]
    if isinstance(tg, str) and (tg.startswith("all") or tg.startswith("enemies") or tg.startswith("allies")):
        every = getattr(engine, "everyone", None) or [a, t]
        if tg.startswith("allies"):
            return [c for c in every if c is not a and getattr(c, "side", None) == getattr(a, "side", None)] or []
        if tg.startswith("enemies"):
            return [c for c in every if getattr(c, "side", None) != getattr(a, "side", None) and not c.fainted] or [t]
        return [c for c in every if not c.fainted]
    return [t]


def _prompt(engine, e, text, src=None, attacker=None, target=None):
    msg = f"    [GM 판단] {e.get('type')}: {text}"
    prompt = {"type": e.get("type"), "text": text, "effect": e, "attacker": attacker, "target": target}
    engine.gm_prompts.append(prompt)
    engine.log(msg, src)
    if hasattr(engine, "decide"):
        ans = engine.decide(prompt)
        if ans is not None:
            prompt["answer"] = ans
    return prompt.get("answer")


def _register(engine, c, e, label=None):
    c.registry.append(e)
    engine.log(f"    {c.name} 수정자 등록: {label or e.get('type')} {_short(e)}")


def _short(e):
    return "{" + ", ".join(f"{k}={str(v)[:28]}" for k, v in e.items() if k not in ("type", "_ability", "_frequency"))[:90] + "}"


def _parse_stage(text):
    m = STAGE_RE.search(str(text))
    if not m:
        return None
    if m.group(1):
        return m.group(2), int(m.group(1))
    return m.group(3), int(m.group(4))


def _parse_status(text):
    for s in STATUS_WORDS:
        if s in str(text):
            return s
    return None


def _run_nested(engine, a, t, then, ctx, src):
    if isinstance(then, dict):
        then = [then]
    if isinstance(then, list):
        return FX.run_effects(engine, a, t, then, ctx, src)
    if isinstance(then, str):
        st = _parse_status(then)
        sg = _parse_stage(then)
        if st:
            engine.apply_status(t, st)
            return 1, 0
        if sg:
            engine.change_stage(a if "self" in then or "user" in then else t, sg[0], sg[1])
            return 1, 0
        _prompt(engine, {"type": "alternate_effect"}, then, src)
        return 1, 0
    return 0, 0


# ============================ 1. 실행 핸들러 ============================
def h_incinerate_equipment(engine,a,t,e,ctx):
    import equipment_actions as EQUIPMENT
    return EQUIPMENT.dispatch(engine,a,t,e,ctx)

def h_item_swap(engine, a, t, e, ctx):
    if ctx.get("source_id")=="move/트릭":
        import equipment_actions as EQUIPMENT
        return EQUIPMENT.dispatch(engine,a,t,e,ctx)
    import equipment_actions as EQUIPMENT
    note=EQUIPMENT.exchange_dispatch(engine,a,a,t,e,ctx,swap=True)
    engine.log(f"    도구 교환: {a.name}={[x['name'] for x in HELD.entries(a)]}, {t.name}={[x['name'] for x in HELD.entries(t)]}")
    return note


def h_steal_item(engine, a, t, e, ctx):
    if ctx.get("source_id") in ("move/도둑질","move/쪼아대기","move/탐내기"):
        import equipment_actions as EQUIPMENT
        return EQUIPMENT.dispatch(engine,a,t,e,ctx)
    if "user holds nothing" in str(e.get("if", "")) and HELD.any_held(a):
        engine.log(f"    {a.name}은(는) 이미 도구를 지녀 훔치지 못함")
        return None
    if not HELD.any_held(t):
        engine.log(f"    {t.name}은(는) 도구가 없음")
        return None
    import items as ITEMS
    held=ITEMS.equipment_options(t,("held",))
    if len(held)!=1:raise ValueError("steal requires one actual selected held instance")
    ITEMS.transfer_equipment(engine,t,a,held[0]["key"],slots=("held",))
    engine.log(f"    {a.name}이(가) {t.name}의 도구 {[x['name'] for x in HELD.entries(a)]} 을(를) 빼앗음")


def h_item_drop(engine, a, t, e, ctx):
    if ctx.get("source_id")=="move/탁쳐서떨구기":
        import equipment_actions as EQUIPMENT
        return EQUIPMENT.dispatch(engine,a,t,e,ctx)
    if HELD.any_held(t):
        import items as ITEMS
        name=t.item
        ITEMS.drop_item(engine,t)
        engine.log(f"    {t.name}의 도구 {name} 이(가) 땅에 떨어짐")
    else:
        engine.log(f"    {t.name}은(는) 떨굴 도구가 없음")


def h_give_item(engine, a, t, e, ctx):
    if HELD.any_held(t) and "holds nothing" in str(e.get("if", "")):
        engine.log(f"    {t.name}은(는) 이미 도구를 지님 → 실패")
        return None
    import equipment_actions as EQUIPMENT
    note=EQUIPMENT.exchange_dispatch(engine,a,a,t,e,ctx,swap=False)
    engine.log(f"    {a.name}이(가) {t.name}에게 도구 {[x['name'] for x in HELD.entries(t)]} 을(를) 줌")
    return note


def h_copy_item(engine, a, t, e, ctx):
    import pickup_item_copy as PICKUP
    return PICKUP.apply_effect(engine, a, t, e, ctx)


def h_item_restore(engine, a, t, e, ctx):
    if ctx.get('source_id')=='move/리사이클':
        __import__('recycle_move').apply(engine,a,t,e,ctx)
        return None
    a.counters["item_restore"] = a.counters.get("item_restore", 0) + 1
    engine.log(f"    {a.name}: 소모한 도구 효과 1회 재사용 가능")


def h_consume_buff(engine, a, t, e, ctx):
    import food_effects as FOOD
    source=ctx.get('food_move_source')
    if source!=FOOD.STUFF_CHEEKS or e.get('ignore_conditions') is not True:
        return 'source-specific native food consumption producer required'
    result=FOOD.move_consumption_commit(engine,a,source)
    if result is None:return 'no actual acquired food buff to exchange'
    ctx['food_consumption_receipt']=result['receipt']
    engine.log(f"    {a.name} 음식 버프 소비: {result['buff_id']}",source)


def h_steal_buff(engine, a, t, e, ctx):
    import food_effects as FOOD
    FOOD.transfer_live(engine,a,t,ctx.get('source_id'))
    return None  # successful transfer identity is not an unsupported-execution note


def h_copy_stages(engine, a, t, e, ctx):
    src, dst = (t, a) if e.get("from", "target") == "target" else (a, t)
    import combat_stage_sources as STAGES
    STAGES.validate(src)
    import csv_item_food_contracts as CSV_FOOD
    CSV_FOOD.assign_stages(engine, ((dst, dict(src.stages)),))
    engine.log(f"    {dst.name} 전투단계 ← {src.name} {dst.stages}")


def h_invert_stages(engine, a, t, e, ctx):
    import combat_stage_sources as STAGES
    import csv_item_food_contracts as CSV_FOOD
    assignments = [(c, {k: -v for k, v in c.stages.items()}) for c in _who(engine, a, t, e)]
    CSV_FOOD.assign_stages(engine, assignments)
    for c, _ in assignments:
        engine.log(f"    {c.name} 전투단계 반전 {c.stages}")


def h_transfer_status(engine, a, t, e, ctx):
    src, dst = (a, t) if e.get("from", "self") == "self" else (t, a)
    movable = [s for s in src.conditions if s not in ("기절",)]
    if not movable:
        engine.log(f"    {src.name}에게 옮길 상태이상이 없음")
        return None
    s = sorted(movable)[0]
    if s in dst.conditions:
        engine.log(f"    {dst.name}은(는) 이미 {s} 상태 → 실패")
        return None
    engine.cure_status(src, s)
    engine.apply_status(dst, s)


def h_apply_status_choice(engine, a, t, e, ctx):
    return __import__('earned_status_choices').apply(engine,a,t,e,ctx)


def h_move_lock(engine, a, t, e, ctx):
    for c in _who(engine, a, t, e):
        c.custom_conditions["move_lock"] = e
        engine.log(f"    {c.name}: [{e.get('keyword')}] 기술 봉인 ({e.get('duration', '')})")


def h_condition_param(engine, a, t, e, ctx):
    engine.condition_params.setdefault(e.get("condition"), {}).update({k: v for k, v in e.items() if k not in ("type", "condition")})
    engine.log(f"    상태 매개변수: {e.get('condition')} {_short(e)}")


def h_bind(engine, a, t, e, ctx):
    for c in _who(engine, a, t, dict(e, target=e.get("targets", "target"))):
        c.custom_conditions["속박"] = dict(e, by=a.name)
        engine.log(f"    {c.name} 속박됨 (by {a.name}, {e.get('until', '')})")


def h_grounding(engine, a, t, e, ctx):
    import catalog_move_states as CATALOG
    return CATALOG.install_grounding(engine, a, t, e, ctx)


def h_size_change(engine, a, t, e, ctx):
    c = a if e.get("target", "self") == "self" else t
    c.spec["size"] = e.get("to")
    engine.log(f"    {c.name} 크기 → {e.get('to')} ({e.get('until', '')})")


def h_save_mod(engine, a, t, e, ctx):
    for c in _who(engine, a, t, dict(e, target=e.get("target", "self"))):
        if isinstance(e.get("value"), int):
            c.save_mod += e["value"]
            engine.log(f"    {c.name} 내성 체크 {e['value']:+d} ({e.get('vs', '전부')})")


def h_injury(engine, a, t, e, ctx):
    import actor_templates as TEMPLATES
    for c in _who(engine, a, t, e):
        if TEMPLATES.injuries_immune(c):
            continue
        import ice_lake as ICE_LAKE
        ice_observation = ICE_LAKE.injury_effect(engine,a,c,ctx)
        n = int(e.get("value", 1))
        import precise_actions as PRECISE
        retained=PRECISE.gain_injury(engine,c,n,"effect/injury")
        if ice_observation is not None:
            event_id, before, contact = ice_observation
            ICE_LAKE.note_injury(engine,event_id,c.injuries-before,contact=contact)
        engine.check_fainted(c)
        engine.log(f"    {c.name} 부상 +{retained} (총 {c.injuries}) → 최대 체력 {c.max_hp}")


def h_heal_injury(engine, a, t, e, ctx):
    c = a if e.get("target", "self") == "self" else t
    engine.check_fainted(c)
    if c.dead:return "사망 상태의 부활은 미정"
    v = e.get("value", 1)
    n = int(re.search(r"\d+", str(v)).group()) if re.search(r"\d+", str(v)) else 1
    healed = INJURY.heal(engine,c,n,source="effect_heal_injury")
    engine.log(f"    {c.name} 부상 {healed}개 치유 (남은 {c.injuries})")
    if e.get("heal_per_injury") == "tick" and healed:
        engine.heal(c, engine.tick(c) * healed, source_kind=ctx.get("healing_source_kind","unspecified"))


def h_full_restore(engine, a, t, e, ctx):
    c = t if "target" in str(e.get("target", "target")) else a
    engine.check_fainted(c)
    if c.dead:return "사망 상태의 부활은 미정"
    INJURY.heal(engine,c,int(e.get("heal_injuries", 0)),source="effect_full_restore")
    import status_sets as STATUS_SETS
    STATUS_SETS.cure_group(engine,c)
    engine.revive(c,max(1,c.max_hp))
    if e.get("restore_frequencies"):
        FREQ.restore_all_moves(c)
    engine.log(f"    {c.name} 완전 회복: 체력 {c.hp}, 부상 {c.injuries}, 빈도 복구")


def h_hp_share(engine, a, t, e, ctx):
    engine.check_fainted(a);engine.check_fainted(t)
    if a.dead or t.dead:return "사망 대상 HP 공유 미지원"
    import bandages as BANDAGES,state_grants as G
    import combat_damage as DAMAGE,attack_damage_history as HISTORY
    def apply(staged,actor,target):
        before=DAMAGE.observe(target)
        la, lt = M.ratio(max(0,actor.hp),2), M.ratio(max(0,target.hp),2)
        import temporary_hp as TEMP_HP
        ahp, thp = actor.hp, target.hp
        actor.hp -= TEMP_HP.loss_remainder(staged,actor,la,unpreventable=True)
        target.hp -= TEMP_HP.loss_remainder(staged,target,lt,unpreventable=True)
        BANDAGES.on_hp_change(staged,actor,ahp,actor.hp)
        BANDAGES.on_hp_change(staged,target,thp,target.hp)
        HISTORY.wake_effect_loss(staged,actor,target,ctx,before)
        gain = M.ratio(la+lt,2)
        # Keep the native redistribution policy; this is not new healing authority.
        staged.heal(actor,gain,source_kind="unspecified")
        staged.heal(target,gain,source_kind="unspecified")
        staged.log(f"    아픔나누기: {actor.name} -{la}, {target.name} -{lt}, 둘 다 +{gain} → {actor.name} {actor.hp}, {target.name} {target.hp} (부상·대규모 피해 없음)")
    return G.transition(engine,a,apply,participants=(t,))


def h_delayed_heal(engine, a, t, e, ctx):
    if ctx.get('source_id')=='move/희망사항':return __import__('wish_move').schedule(engine,a,t,e,ctx)
    engine.delayed.append({"kind": "heal", "who": t, "turns": 1, "effect": e, "src": "delayed_heal", "healing_source_kind": ctx.get("healing_source_kind","unspecified")})
    engine.log(f"    {t.name}: 다음 턴 끝에 회복 예약 ({e.get('fraction_of_max')})")


def h_counter(engine, a, t, e, ctx):
    import counter_effects as COUNTERS
    COUNTERS.change(engine,a,e,ctx.get('source_id'))


def h_execute(engine, a, t, e, ctx):
    thr = FX.evaluate(e.get("threshold"), {**ctx, "attacker": a, "target": t, "engine": engine})
    if thr is None:
        thr = FX.evaluate(re.sub(r"\(.*?\)", "", str(e.get("threshold"))), {**ctx, "attacker": a, "target": t, "engine": engine})
    if thr is None:
        return f"임계값 미해석: {e.get('threshold')}"
    imm = str(e.get("immune_if", ""))
    for ty in TYPES:
        if ty in imm and ty in t.types:
            engine.log(f"    {t.name}은(는) {ty} 타입 → 일격 무효")
            return None
    roll = POOLS.die(engine.rng, 100)
    ok = roll < thr
    engine.log(f"    일격 판정 1d100={roll} < X={thr} → {'기절!' if ok else '실패'}")
    if ok:
        import attack_damage_history as HISTORY
        HISTORY.received_loss(engine,t,max(0,t.hp),source="일격",move=ctx.get('move'),loss_kind="hp_setting")
        __import__("life").faint(engine,t)


def h_transform(engine, a, t, e, ctx):
    import state_grants as GRANTS
    def apply(staged,actor,donor):
        context=GRANTS._stage_transition_payload(engine,staged,ctx)
        source=GRANTS.effect_source(actor,context,"transform")
        row=GRANTS._source(actor,source,"effect",owner_id=actor.spec.get("id"),lifetime=e.get("duration") or e.get("until") or "legacy_unspecified",rule_id=context.get("source_id"))
        row["copied_actor_id"]=donor.spec.get("id")
        GRANTS.overlay(actor,source,moves=list(donor.moves),abilities=list(donor.abilities))
        GRANTS.scalar(actor,"_types",list(donor.types),source)
        GRANTS.scalar(actor,"_weight_class",donor.weight_class,source)
        actor.custom_conditions["transformed"]={"source":source,"copied_actor_id":donor.spec.get("id"),"lifetime":row["lifetime"]}
        GRANTS.reconcile(staged,actor)
        staged.log(f"    {actor.name} → {donor.name}으로 변신 (타입 {actor.types}, 기술 {len(actor.moves)}개, 스탯 불변)")
    return GRANTS.transition(engine,a,apply,participants=(t,),include_rulings=True)


def h_free_maneuver(engine, a, t, e, ctx):
    import maneuver_grants as GRANTS
    return GRANTS.dispatch(engine, a, t, e, ctx)


def h_forced_movement(engine, a, t, e, ctx):
    spec = e.get("on_hit", e)
    # Text such as "toward trainer" declares a different procedure from radial
    # pushing. Do not infer its direction or distance from a displayed speed.
    if 'distance' not in spec or 'direction' not in spec:
        return 'forced movement requires explicit source-resolved distance and direction'
    import forced_movement as FORCED
    result=FORCED.displace(engine,a,t,direction=spec['direction'],distance=spec['distance'],
        source=ctx.get('source_id') or 'effect/forced_movement',
        stop_cells=spec.get('stop_cells',()),allow_fainted=spec.get('allow_fainted',False))
    engine.log(f"    {t.name} 강제 이동 {result['moved']}m → {t.pos}")


def h_switch_out(engine, a, t, e, ctx):
    if e.get("if") == "hit" and not ctx.get("hit", True):
        return None
    if 'effect_receipt' not in ctx:
        # Existing low-level recall callers have no paid source occurrence.
        if e.get('pass') or ctx.get('source_id') in ('move/배턴터치','feat/왕복-여행'):
            raise ValueError('source transfer requires its native dispatcher occurrence')
        import condition_recovery as RECOVERY
        if not RECOVERY.permits_recall(a) and not e.get('ignore_trapped'):
            return '수렁 상태로 복귀 불가'
        engine.gm.recall(a,reason='explicit low-level recall')
        return None
    import native_switch_transfer as SWITCH
    SWITCH.execute(engine,a,t,e,ctx)


def h_ally_struggle(engine, a, t, e, ctx):
    every = getattr(engine, "everyone", None) or []
    allies = [c for c in every if c is not a and getattr(c, "side", None) == getattr(a, "side", None) and not c.fainted]
    if engine.grid is not None:
        from grid import cheb
        allies = [c for c in allies if engine.adjacent(c,t)]
    allies = allies[: int(e.get("allies", 2))]
    engine.log(f"    집단구타: {a.name} + 아군 {[c.name for c in allies]} 발버둥 ({e.get('struggle_type')} 타입)")
    for c in [a] + allies:
        c.type_override_next = e.get("struggle_type")
        engine.use_move(c, t, "struggle", count_use=False)


def h_copy_move(engine, a, t, e, ctx):
    src = t.last_move
    if not src or src == ctx.get("move", {}).get("id"):
        engine.log(f"    {t.name}이(가) 마지막에 쓴 기술이 없음 → 실패")
        return None
    engine.log(f"    {a.name}이(가) {t.name}의 마지막 기술 {src} 을(를) 사용")
    if e.get("permanent") or e.get("until"):
        a.moves.append(src)
    engine.use_move(a, t, src, count_use=False)


def h_random_move(engine, a, t, e, ctx):
    cur = ctx.get("move", {}).get("id")
    pool = [m for m in a.moves if m != cur]
    if not pool:
        _prompt(engine, e, f"무작위 기술 출처: {e.get('source')}")
        return None
    mv = engine.rng.choice(pool)
    engine.log(f"    무작위 기술 → {mv}")
    engine.use_move(a, t, mv, count_use=False)


def h_repeat_last_move(engine, a, t, e, ctx):
    if not t.last_move:
        engine.log(f"    {t.name}은(는) 반복할 기술이 없음")
        return None
    if t.last_move == ctx.get("move", {}).get("id"):
        engine.log(f"    지휘는 지휘를 반복할 수 없음")
        return None
    engine.log(f"    {t.name}이(가) {t.last_move} 을(를) 자유 행동으로 재사용 (빈도 무시)")
    foe = getattr(t, "last_target", None) or a
    engine.use_move(t, foe, t.last_move, count_use=False)


def h_attack(engine, a, t, e, ctx):
    __import__('condition_instances').require_target(a,t)
    from ruleset import UnresolvedRuleSelection
    origin = e.get("_rule_id")
    if not origin:
        raise UnresolvedRuleSelection("ability-attack", ["missing_effect_source_identity"])
    selection = engine.r.selection
    selected = selection.require_supported_version(origin)
    uid = "derived/ability-attack/" + selected
    if uid not in selection.units:
        source = selection.units[selected]["source"]
        selection.register_derived({"id": uid, "title": "특성 공격", "source": source},
                                   (selected, "combat/accuracy-roll"))
    selection.require_supported_version(uid)
    move = {"id": uid, "name": "특성 공격", "class": e.get("class", "변화"), "ac": e.get("ac", 2), "type": "노말", "damage_base": None}
    import action_lifecycle as ACTION,confusion_attacks as CONFUSION
    import eldritch_magic as ELDRITCH
    ELDRITCH.preflight(engine,a,move)
    CONFUSION.preflight(engine,a,move)
    with ACTION.resolution(engine,a,uid,kind='ability_attack'):
        CONFUSION.observe_action(engine,a,move)
        import precise_actions as PRECISE
        precision_event=PRECISE.attacked(engine,a,t,move,producer="effects_ext.ability_attack")
        hit, nat, crit = engine.accuracy_check(a, t, move)
        PRECISE.accuracy(precision_event,hit)
        if not hit:
            return None
        import duelist as DUELIST
        DUELIST.ability_hit(engine,a,t,uid,ctx.get('effect_occurrence',str(ctx.get('effect_receipt'))))
        __import__('channeler').hit(engine,a,t,'ability:'+uid+':'+str(ctx.get('effect_occurrence',ctx.get('effect_receipt'))))
        ELDRITCH.after_hit(engine,a,t,move,nat,effect_receipt=ctx.get('effect_receipt'))
        on = e.get("on_hit")
        if isinstance(on, dict):
            if "apply_status" in on:
                engine.apply_status(t, on["apply_status"])
            else:
                FX.run_effects(engine, a, t, [on], dict(ctx, hit=True, nat=nat), "attack")


def h_alternate_effect(engine, a, t, e, ctx):
    cond = e.get("if")
    ok = True
    if isinstance(cond, str):
        ok, why = FX.cond_ok(engine, {"if": cond}, ctx)
        if not ok and why.startswith("조건 미해석"):
            ok = _eval_cond(engine, a, t, cond, ctx)
            if ok is None:
                _prompt(engine, e, f"조건 '{cond}' 판단 → then: {str(e.get('then'))[:60]}")
                return None
    if not ok:
        engine.log(f"    분기 조건 불충족: {cond}")
        return None
    engine.log(f"    분기 조건 충족: {cond or '(무조건)'}")
    return _run_nested(engine, a, t, e.get("then"), ctx, ctx["source_id"])


def _eval_cond(engine, a, t, cond, ctx):
    """자연어 조건 가운데 전투 상태로 판단 가능한 것. 모르면 None."""
    c = str(cond)
    if c in ('target in rain weather','target in sunny weather','target airborne (뛰어오르기/공중날기/프리폴)','target hit user super-effectively since last turn'):
        return __import__('effect_contracts').condition_text(engine,a,t,c,ctx)
    m = re.search(r"stockpile\s*(==|>=)\s*(\d+)", c)
    if m:
        v = a.counters.get("stockpile", 0)
        return v == int(m.group(2)) if m.group(1) == "==" else v >= int(m.group(2))
    if "user is 고스트" in c or "user is ghost" in c or "user not 고스트" in c:
        import class_move_grants as CLASS_MOVES
        ghost = "고스트" in a.types or CLASS_MOVES.uses_ghost_curse(a,ctx.get("move"))
        return not ghost if "user not 고스트" in c else ghost
    if "target is ally" in c:
        return getattr(t, "side", None) == getattr(a, "side", None)
    if "target was asleep" in c or "target paralyzed" in c or "target is poisoned" in c or "target has a status" in c or "target has status" in c:
        if "asleep" in c:
            return "잠듦" in t.conditions
        if "paralyzed" in c:
            return "마비" in t.conditions
        if "poisoned" in c:
            return "독" in t.conditions or "맹독" in t.conditions
        return bool(t.conditions - {"기절"})
    if "user holds no item" in c or "user holds nothing" in c:
        import equipment_protection as PROTECTION
        return PROTECTION.itemless_for_move(engine,a,ctx.get("move"))
    if "user has >= 1 injury" in c:
        return a.injuries >= 1
    if "user current HP <= half" in c:
        return a.hp <= a.base_max_hp / 2
    if "target HP above 50%" in c:
        return t.hp > t.base_max_hp / 2
    if "target HP below half" in c:
        return t.hp < t.base_max_hp / 2
    if "terastallized" in c:
        import homebrew_state as HOME
        return HOME.tera_active(a)
    if "weather effect active" in c:
        import csv_item_physical_contracts as CSV_ITEMS
        return bool(__import__('effects').effective_weather(engine,a))
    if "field" in c and "terrain" in c:
        return engine.field is not None
    if "single target" in c:
        return True
    if "sunny weather" in c or "in sunny" in c:
        return FX.weather_matches(engine,'sunny',a)
    if "rain weather" in c or "in rain" in c:
        return FX.weather_matches(engine,'rain',a)
    if "hail" in c and "weather" in c:
        return FX.weather_matches(engine,'hail|snow',a)
    if "airborne" in c:
        return bool(getattr(t, "airborne", False))
    if "immune to" in c:
        for ty in TYPES:
            if ty in c:
                return engine.type_multiplier(ty, t)[0] == 0
    if "target faster" in c or "target initiative lower" in c:
        return t.staged("spe") > a.staged("spe") if "faster" in c else t.staged("spe") < a.staged("spe")
    if "hit" == c.strip():
        return ctx.get("hit", True)
    return None


def h_random(engine, a, t, e, ctx):
    tbl = e.get("table")
    if isinstance(tbl, dict) and tbl:
        keys = list(tbl)
        match = re.search(r"d(\d+)", str(e.get("roll", "")))
        sides = max(2, int(match[1]) if match else len(keys))
        import duelist as DUELIST
        roll = 11 if sides==20 and DUELIST.choose_eleven(engine,a,'effect') else POOLS.die(engine.rng, sides)
        if sides==20:roll=__import__('oracle').replace_d20(engine,a,roll,'random_table')
        pick = None
        for k, v in tbl.items():
            m = re.match(r"(\d+)(?:-(\d+))?", str(k))
            if m and int(m.group(1)) <= roll <= int(m.group(2) or m.group(1)):
                pick = v
                break
        if pick is None:
            pick = tbl[keys[(roll - 1) % len(keys)]]
        engine.log(f"    {e.get('roll', '무작위')} = {roll} → {pick}")
        who = _who(engine, a, t, e)[0]
        st, sg = _parse_status(pick), _parse_stage(pick)
        if st:
            engine.apply_status(who, st)
        elif sg:
            engine.change_stage(who, sg[0], sg[1])
        else:
            _prompt(engine, e, f"표 결과 '{pick}' 적용")
        return None
    if isinstance(e.get("then"), (dict, list)):
        import duelist as DUELIST
        roll = 11 if DUELIST.choose_eleven(engine,a,'effect') else POOLS.die(engine.rng, 20)
        roll=__import__('oracle').replace_d20(engine,a,roll,'random_effect')
        cond = str(e.get("if", ""))
        m = re.search(r"<=\s*(\d+)", cond)
        if m and roll <= int(m.group(1)):
            engine.log(f"    1d20={roll} ≤ {m.group(1)} → 효과 발동")
            then = e["then"]
            if isinstance(then, dict) and "heal" in then:
                engine.heal(a, engine.tick(a))
                engine.log(f"    기본 행동 불가 (게으름)")
            else:
                _run_nested(engine, a, t, then, ctx, "random")
        else:
            engine.log(f"    1d20={roll} → 효과 없음")
        return None
    _prompt(engine, e, f"무작위 굴림 {e.get('roll')}: {e.get('note') or e.get('effect', '')}")


def h_escalating_effect(engine, a, t, e, ctx):
    every = getattr(engine, "everyone", None) or []
    n = sum(1 for c in every if c is not a and getattr(c, "side", None) == getattr(a, "side", None) and c.fainted)
    engine.log(f"    기절한 아군 {n}명 기준 누적 효과")
    for k, v in (e.get("table") or {}).items():
        if n >= int(k):
            st = _parse_status(v)
            m = re.search(r"(\d+)\+", str(v))
            if st and (m is None or (ctx.get("nat") or 0) >= int(m.group(1))):
                engine.apply_status(t, st)
            else:
                engine.log(f"    단계 {k}: {v}")


def h_conditional_area_status(engine, a, t, e, ctx):
    every = getattr(engine, "everyone", None) or [t]
    foes = [c for c in every if getattr(c, "side", None) != getattr(a, "side", None) and not c.fainted and any(v > 0 for v in c.stages.values())]
    if engine.grid is not None:
        from grid import cheb
        m = re.search(r"(\d+)m", str(e.get("targets", "")))
        if m:
            foes = [c for c in foes if cheb(a.pos, c.pos) <= int(m.group(1))]
    engine.log(f"    조건부 영역 상태 {e.get('status')}: 양수 전투단계를 가진 적 {[c.name for c in foes]} (근사: '최근 턴 이후 상승' 대신 현재 양수 단계)")
    for c in foes:
        engine.apply_status(c, e["status"])


def h_damage_cap(engine, a, t, e, ctx):
    c = a
    c.damage_cap = e
    engine.log(f"    {c.name} 피해 상한 등록: {e.get('value')}")


def h_apply_coat(engine, a, t, e, ctx):
    import coat_effects as COATS
    if COATS.grant(engine,a,e,ctx.get('source_id'),target=t):return None
    for c in _who(engine, a, t, e):
        c.coats.append(e)
        engine.log(f"    {c.name} 코트 획득: {e.get('coat')} {_short(e.get('effect') or {}) if isinstance(e.get('effect'), dict) else ''}")


def h_remove_coats(engine, a, t, e, ctx):
    for c in _who(engine, a, t, e):
        import coat_effects as COATS
        n = COATS.clear(engine,c,source=ctx.get('source_id'),applied_by=a)
        engine.log(f"    {c.name} 코트 {n}개 제거")


def h_blessing(engine, a, t, e, ctx):
    import blessing_effects as BLESSINGS
    if BLESSINGS.grant(engine,a,e,ctx.get('source_id')):return
    for c in _who(engine, a, t, dict(e, target=e.get("target", "self"))):
        c.blessings.append({"name": e.get("name"), "on": str(e.get("on", "")), "effect": str(e.get("effect", "")), "left": int(e.get("activations") or 2), "src": e})
        engine.log(f"    {c.name} 축복 {e.get('name')} ({e.get('activations', 2)}회): {e.get('on')} → {e.get('effect')}")


def h_create_terrain_ext(engine, a, t, e, ctx):
    import hazard_state as HAZARDS
    if HAZARDS.handles(engine,ctx.get('source_id'),e):
        HAZARDS.install(engine,a,e,ctx)
        return None
    import field_effects as FIELD
    if FIELD.handles_local_snow(engine,ctx.get('source_id'),e):
        FIELD.install_local_snow(engine,a,t,e,ctx.get('source_id'),ctx.get('effect_receipt'),ctx.get('effect_occurrence'))
        return None
    kind = str(e.get("terrain", ""))
    if engine.grid is None:
        engine.log(f"    지형 생성 {kind} (격자 없음: 기록만)")
        engine.hazards_nogrid.append(e)
        return None
    from grid import cheb
    n = e.get("cells") if isinstance(e.get("cells"), int) else e.get("segments") if isinstance(e.get("segments"), int) else None
    center = t.pos if t is not a else a.pos
    if "burst" in str(e.get("shape", "")) or "burst" in str(e.get("cells", "")):
        size = int(re.search(r"\d+", str(e.get("shape") or e.get("cells"))).group()) if re.search(r"\d+", str(e.get("shape") or e.get("cells"))) else 1
        cells = set(engine.grid.burst(a.pos, size))
    else:
        ring = sorted(engine.grid.burst(center, 1) | {center}, key=lambda p: (cheb(p, center), p))
        cells = set(ring[: (n or 4)])
    if kind.startswith("hazard:"):
        name = kind.split(":", 1)[1]
        move = ctx.get("move") or {}
        mm, _ = engine.r.move_mech(move["id"]) if move.get("id") in engine.r.moves else ({}, None)
        effs = [x for x in mm.get("effects_exec", []) if isinstance(x, dict) and re.search(r"hazard|passes|enters", str(x.get("if", "")))]
        for cell in cells:
            engine.hazards[cell] = {"name": name, "effects": effs, "owner": a.name, "slow": bool(e.get("slow_terrain"))}
            if e.get("slow_terrain"):
                engine.grid.slow.add(cell)
        engine.log(f"    함정 {name} {len(cells)}칸 설치 ({sorted(cells)[:4]}…), 밟으면 효과 {len(effs)}개")
    elif "blocking" in kind:
        engine.grid.blocking |= cells
        engine.log(f"    차단 지형(벽) {len(cells)}칸 생성 (체력 {e.get('hp', '?')}, DR {e.get('damage_reduction', '?')})")
    elif "slow" in kind or "snow" in kind:
        engine.grid.slow |= cells
        engine.log(f"    둔화 지형 {len(cells)}칸 생성 ({kind})")
    elif "rough" in kind or "바위" in kind:
        engine.grid.rough |= cells
        engine.log(f"    험한 지형 {len(cells)}칸 생성 ({kind})")
    else:
        engine.hazards_nogrid.append(e)
        _prompt(engine, e, f"지형 '{kind}' 배치")


def h_destroy_hazards(engine, a, t, e, ctx):
    if engine.grid is None:
        n = len(engine.hazards_nogrid)
        engine.hazards_nogrid = []
    else:
        from grid import cheb
        m = re.search(r"(\d+)m", str(e.get("area", "")))
        rad = int(m.group(1)) if m else 1 if "adjacent" in str(e.get("area", "")) else 99
        if e.get('area') == 'line':
            cells = ctx.get('move', {}).get('_effect_area_cells')
            if cells is None:
                return '직선 함정 제거에는 실제 기술 영역이 필요하다'
            gone = [c for c in engine.hazards if c in cells]
        else:
            gone = [c for c in engine.hazards if cheb(c, a.pos) <= rad]
        import hazard_state as HAZARDS
        n = HAZARDS.remove_cells(engine,gone)
        if e.get("also") == "smoke":
            import smoke_regions as SMOKE
            SMOKE.remove_cells(engine,[c for c in engine.zone_cells if cheb(c,a.pos)<=rad])
    engine.log(f"    함정 {n}개 파괴 ({e.get('area', '')})")


def h_clear_terrain(engine, a, t, e, ctx):
    if engine.grid is None:
        return None
    m = re.search(r"burst\s*(\d+)", str(e.get("area", "")))
    cells = set(engine.grid.burst(a.pos, int(m.group(1)) if m else 1)) | {a.pos}
    before = len(engine.grid.slow & cells) + len(engine.grid.rough & cells)
    engine.grid.slow -= cells
    engine.grid.rough -= cells
    import hazard_state as HAZARDS
    HAZARDS.remove_cells(engine,cells)
    engine.log(f"    지형 정리: 둔화/험한 지형 {before}칸 + 함정 제거 ({e.get('area')})")


def h_clear_field(engine, a, t, e, ctx):
    rm = [str(x) for x in (e.get("remove") or [])]
    done = []
    if any("weather" in x for x in rm):
        import weather_state as WEATHER
        WEATHER.clear(engine,source_id=ctx.get("source_id") or "combat/weather")
        done.append("날씨")
    if any("blessing" in x for x in rm):
        import blessing_effects as BLESSINGS
        BLESSINGS.clear(engine,ctx.get('source_id'),a)
        for c in getattr(engine, "everyone", None) or [a, t]:
            c.blessings = []
        done.append("축복")
    if any("coat" in x for x in rm):
        for c in getattr(engine, "everyone", None) or [a, t]:
            import coat_effects as COATS
            COATS.clear(engine,c,source=ctx.get('source_id'),applied_by=a)
        done.append("코트")
    if any("hazard" in x for x in rm):
        import hazard_state as HAZARDS
        HAZARDS.clear(engine)
        done.append("함정")
    if any("field" in x or "terrain" in x for x in rm):
        import field_effects as FIELD
        FIELD.clear(engine, terrain_only=any("terrain" in x for x in rm))
        done.append("필드")
    if any("연막" in x for x in rm) or ctx.get('source_id') == 'move/안개제거':
        if any('연막' in x and 'line' in x for x in rm):
            cells = ctx.get('move', {}).get('_effect_area_cells')
            if cells is None:
                return '직선 연막 제거에는 실제 기술 영역이 필요하다'
            import smoke_regions as SMOKE
            SMOKE.disperse_intersecting(engine,cells)
        else:
            import smoke_regions as SMOKE
            SMOKE.clear(engine)
        done.append("연막")
    engine.log(f"    필드 정리: {', '.join(done) or rm}")


def h_swap_field_sides(engine, a, t, e, ctx):
    import hazard_state as HAZARDS
    HAZARDS.swap_sides(engine,a)


def h_zone_rule(engine, a, t, e, ctx):
    center = t.pos if engine.grid is not None else None
    m = re.search(r"(\d+)", str(e.get("shape") or e.get("radius") or "1"))
    engine.zone_rules.append({"owner": a, "center": center, "radius": int(m.group(1)) if m else 1, "rule": e})
    engine.log(f"    구역 규칙 등록: {_short(e)}")


def h_form_change(engine, a, t, e, ctx):
    c = a
    if "form" in e:
        import form_allocations as FORMS
        FORMS.switch(engine,c,e["form"])
        engine.log(f"    {c.name} 폼 체인지 → {e['form']} ({e.get('until', '')})")
    elif e.get("forms"):
        if e.get("trigger") or e.get("at"):
            import form_allocations as FORMS
            FORMS.switch(engine,c,e["forms"][0])
            c.form_rule = e
            engine.log(f"    {c.name} 폼 규칙 등록 {e['forms']} ({e.get('trigger') or e.get('at')})")
        else:
            import form_allocations as FORMS
            FORMS.switch(engine,c,e["forms"][0])
            engine.log(f"    {c.name} 폼 선택 가능 {e['forms']} → 기본 {c.form}")
    else:
        _prompt(engine, e, f"폼 변경 {e.get('by', '')}")


def h_grant_move(engine, a, t, e, ctx):
    """An actual effect owns its entire grant batch; no silent partial append."""
    import state_grants as GRANTS
    if any(key in e for key in ('duration','until','while','repeat')):
        raise ValueError('timed move grant requires its explicit lifetime consumer')
    ids=GRANTS.move_grants(engine.r,e)
    recipients=list(dict.fromkeys(_who(engine,a,t,e,default='self')))
    source_rule=ctx.get('source_id')
    import move_permissions as PERMISSIONS
    permission=PERMISSIONS.preflight_grant(engine,a,e,source_rule,ctx)
    if not isinstance(source_rule,str) or engine.r._selected_rule(source_rule)!=source_rule:
        raise ValueError('actual selected move-grant source required')
    def apply(staged_e,staged_a,*targets):
        for c in targets:
            registration=getattr(c,'_state_registration_source',None)
            source=ctx.get('permission_source') if permission else registration or GRANTS.effect_source(staged_a,ctx,'move-grant')
            kind='passive' if registration else 'effect'
            lifetime='scene_end' if permission else 'while_registered' if registration else 'until_source_ends'
            GRANTS.grant_moves(c,ids,source,kind,owner_id=staged_a.entity_id,lifetime=lifetime,rule_id=source_rule,mode='permission' if permission else 'learned')
        staged_e.log(f"    {staged_a.name} 기술 부여 {ids} (출처 {source_rule})",source_rule)
    GRANTS.transition(engine,a,apply,participants=tuple(recipients))


def FX_slug(s):
    return re.sub(r"[^0-9A-Za-z가-힣]+", "-", re.sub(r"\[.*?\]|\(.*?\)", "", s)).strip("-").lower()


def h_delayed_attack(engine, a, t, e, ctx):
    return None     # use_move 의 실제 사용 커밋 뒤 전용 경로에서 예약한다


def h_multi_roll(engine, a, t, e, ctx):
    return None     # use_move 의 명중 훅에서 처리


def h_repeat_each_turn(engine, a, t, e, ctx):
    import forced_move_lock as FORCED_MOVE
    if ctx.get("hit", True):
        FORCED_MOVE.hit(engine, a, ctx.get("move", {}))
    else:
        FORCED_MOVE.miss(engine, a, ctx.get("move", {}))


def h_next_roll_bonus(engine, a, t, e, ctx):
    import roll_effects as ROLLS
    ROLLS.grant(engine,a,t,e,ctx.get('source_id'))


def h_type_override_moves(engine, a, t, e, ctx):
    for c in _who(engine, a, t, dict(e, target=e.get("target", "self"))):
        _register(engine, c, e, "기술 타입 치환")


def h_reaction_ext(engine, a, t, e, ctx):
    """기술이 부여하는 반응(reaction_attack / reaction_redirect / reaction_reflect / reaction / pledge): 트리거로 등록."""
    spec = FX.parse_trigger(str(e.get("trigger", ""))) or {"event": "on_hit_received"}
    if e.get("type") == "reaction_reflect":
        a.reflect = e
        if e.get("resist_one_step"):
            a.modifiers.append({"type": "resistance_step", "value": 1, "vs": "physical" if "physical" in str(e.get("trigger", "")) else "special" if "special" in str(e.get("trigger", "")) else None, "_reflect": True})
        engine.log(f"    {a.name} 반사 준비: {e.get('trigger')} → 공격자 체력 손실 {e.get('attacker_hp_loss') or e.get('adjacent_enemies_hp_loss')}")
        return None
    entry = {"name": f"기술 반응 ({ctx.get('move', {}).get('name', '?')})", "spec": spec, "frequency": "장면 x1", "effects": [], "reaction": e, "move_id": ctx.get("move", {}).get("id")}
    a.ability_triggers.append(entry)
    engine.log(f"    {a.name} 반응 등록: {e.get('type')} — {e.get('trigger', e.get('with', ''))}")


# ============================ 2. 레지스트리 / 3. 프롬프트 ============================
REGISTRY_TYPES = {
    "gain_keyword", "range_override", "alternate_range", "range_extension", "effect_range_mod", "extra_target", "accuracy_override", "ignore_evasion",
    "ignore_defense_modifiers", "ignore_effects", "ignore_immunity", "ignore_ability", "immunity_rule", "ignore_weather_penalty", "type_effectiveness_override",
    "alternate_type", "damage_multiplier", "damage_bonus", "escalating_damage_base", "random_db", "action_type_change", "priority", "frequency_rule",
    "usage_restriction", "targeting_rule", "forbid", "limit", "movement_rule", "no_wake", "weapon_restriction", "grant_capability",
    "stab_grant"}
PROMPT_TYPES = {"rule", "gm", "reveal", "craft", "custom_token", "attach", "pledge", "static", "note", "skill_mod", "random_type_on_learn", "share_item_effect",
                "revive_action", "environment_effect", "reroll"}


def _make_registry_handler(label):
    def h(engine, a, t, e, ctx):
        who = a
        if e.get("target") in ("target",) or e.get("on") == "target":
            who = t
        _register(engine, who, e, label)
    return h


def _make_prompt_handler():
    def h(engine, a, t, e, ctx):
        if e.get("type") == "gm":
            # GM decisions need the complete procedure, not a truncated review note.
            text = e.get("choice") or e.get("note") or e.get("info") or _short(e)
            answer = _prompt(engine, e, str(text), attacker=a, target=t)
        else:
            text = e.get("note") or e.get("info") or e.get("choice") or e.get("item") or e.get("name") or e.get("effect") or _short(e)
            answer = _prompt(engine, e, str(text)[:120], attacker=a, target=t)
        if answer is None:
            return "GM 결정 대기 (프롬프트 생성은 효과 실행이 아님)"
    return h


EXEC_HANDLERS = {
    "incinerate_equipment":h_incinerate_equipment, "equipment_reaction":h_incinerate_equipment, "swap_items": h_item_swap, "steal_item": h_steal_item, "item_drop": h_item_drop, "give_item": h_give_item, "copy_item": h_copy_item,
    "item_restore": h_item_restore, "consume_buff": h_consume_buff, "steal_buff": h_steal_buff, "copy_stages": h_copy_stages, "invert_stages": h_invert_stages,
    "transfer_status": h_transfer_status, "apply_status_choice": h_apply_status_choice, "move_lock": h_move_lock, "condition_param": h_condition_param,
    "bind": h_bind, "grounding": h_grounding, "size_change": h_size_change, "save_mod": h_save_mod, "injury": h_injury, "heal_injury": h_heal_injury,
    "full_restore": h_full_restore, "hp_share": h_hp_share, "delayed_heal": h_delayed_heal, "counter": h_counter, "execute": h_execute, "transform": h_transform,
    "free_maneuver": h_free_maneuver, "forced_movement": h_forced_movement, "switch_out": h_switch_out, "switch_out_after_damage": h_switch_out,
    "ally_struggle": h_ally_struggle, "copy_move": h_copy_move, "random_move": h_random_move, "repeat_last_move": h_repeat_last_move, "attack": h_attack,
    "alternate_effect": h_alternate_effect, "random": h_random, "escalating_effect": h_escalating_effect, "conditional_area_status": h_conditional_area_status,
    "damage_cap": h_damage_cap, "apply_coat": h_apply_coat, "remove_coats": h_remove_coats, "blessing": h_blessing, "create_terrain": h_create_terrain_ext,
    "destroy_hazards": h_destroy_hazards, "clear_terrain": h_clear_terrain, "clear_field": h_clear_field, "swap_field_sides": h_swap_field_sides,
    "zone_rule": h_zone_rule, "form_change": h_form_change, "grant_move": h_grant_move, "delayed_attack": h_delayed_attack, "multi_roll": h_multi_roll,
    "repeat_each_turn": h_repeat_each_turn, "next_roll_bonus": h_next_roll_bonus, "type_override_moves": h_type_override_moves,
    "reaction_attack": h_reaction_ext, "reaction_redirect": h_reaction_ext, "reaction_reflect": h_reaction_ext, "reaction": h_reaction_ext, "pledge": h_reaction_ext,
}
for _t in REGISTRY_TYPES:
    EXEC_HANDLERS.setdefault(_t, _make_registry_handler(_t))
for _t in PROMPT_TYPES:
    if _t != "pledge":
        EXEC_HANDLERS.setdefault(_t, _make_prompt_handler())

ABILITY_START_TYPES = REGISTRY_TYPES | PROMPT_TYPES | {"damage_cap", "blessing", "apply_coat", "form_change", "grant_move", "condition_param", "counter", "save_mod", "type_override_moves", "custom_condition", "zone_rule"}


def install():
    """effects.py 의 테이블에 합친다 (import 시 1회)."""
    for k, v in EXEC_HANDLERS.items():
        if k == "create_terrain":
            FX.HANDLERS[k] = v          # 격자 함정·벽·둔화 지형까지 다루는 확장판으로 교체
        else:
            FX.HANDLERS.setdefault(k, v)
    FX.SUPPORTED |= set(EXEC_HANDLERS) | REGISTRY_TYPES | PROMPT_TYPES
    # alternate_type is consumed by effective_type before accuracy; it is not a
    # post-hit registry modifier.  Exact limited choices are owned by
    # alternate_move_modes and validated by effect_contracts.
    FX.ENGINE_TYPES |= {"delayed_attack", "multi_roll", "alternate_type"}


install()


# ============================ 엔진 훅 ============================
def init_combatant(c):
    import held_equipment as HELD
    HELD.initialize(c)
    c.buffs = list(c.spec.get("buffs", []))
    c.coats, c.blessings, c.registry = [], [], []
    c.save_mod, c.grounded, c.form, c.form_rule = 0, 0, None, None
    c.locked_move, c.on_field, c.passed, c.reflect = None, True, None, None
    c.damage_cap, c.type_override_next, c.last_target, c.side = None, None, None, c.spec.get("side", "wild" if c.kind == "pokemon" and c.spec.get("wild") else "party")
    c.turns_taken = 0


def init_engine(engine):
    engine.gm_prompts, engine.delayed, engine.hazards, engine.hazards_nogrid, engine.zone_rules, engine.condition_params = [], [], {}, [], [], {}
    engine.everyone = None
    import hazard_state as HAZARDS
    HAZARDS.init_engine(engine)


def _native_massive_damage_rule(effect):
    return (effect.get("_rule_id") == "ability/옹골참"
            and {key for key in effect if not key.startswith("_")}
            == {"type", "no_injury_from_massive_damage"}
            and effect.get("type") == "rule"
            and effect.get("no_injury_from_massive_damage") is True)


def massive_damage_injury_immune(actor):
    import ability_transitions as ABILITIES
    return ("ability/옹골참" in ABILITIES.project_components(actor)
            and ABILITIES.active(actor, "ability/옹골참"))


def register_ability_extras(engine, c, effs):
    """특성 effect 가운데 패시브 테이블 밖의 유형(레지스트리·프롬프트·코트·축복·폼·카운터…)을 전투 시작 시 한 번 실행."""
    import move_permissions as PERMISSIONS
    import equipment_protection as PROTECTION
    import held_equipment as HELD
    import food_effects as FOOD
    import manual_effects as MANUAL
    extra = [e for e in effs if isinstance(e, dict) and e.get("type") in ABILITY_START_TYPES and e.get("type") not in FX.PASSIVE_TYPES and not _native_massive_damage_rule(e) and not PERMISSIONS.deferred_registration(engine.r,e) and not PROTECTION.deferred_registration(engine.r,e) and not HELD.deferred_registration(engine.r,e) and not FOOD.deferred_registration(engine.r,e) and not MANUAL.deferred_registration(engine.r,e)]
    if not extra:
        return
    FX.run_effects(engine, c, c, extra, {"attacker": c, "target": c, "hit": True, "nat": None, "engine": engine}, f"ability/{extra[0].get('_ability', '?')}")


def _move_matches(e, move, actor=None):
    if e.get('ability_native') == 'ability/예지몽':
        revealed = e.get('moves')
        return move.get('id') in revealed if isinstance(revealed, list) else move.get('id') == revealed
    f = str(e.get("moves", "all"))
    if f in ("all", "None"):
        return True
    if f == "water moves and melee attacks":
        return move["class"] in ("물리", "특수") and (move["type"] == "물" or "근접" in str(move.get("range", "")))
    if "STAB" in f:
        import homebrew_state as HOME
        return actor is not None and move["type"] in HOME.effect_stab_types(actor, e) and ("damaging" not in f or move["class"] in ("물리", "특수"))
    if move["type"] in f and ("damaging" not in f or move["class"] in ("물리", "특수")):
        return True
    if "melee" in f and "근접" in str(move.get("range", "")):
        return True
    if "status" in f and move["class"] == "변화":
        return True
    if "damaging" in f and move["class"] in ("물리", "특수") and not any(ty in f for ty in TYPES):
        return True
    if move.get("name", "") in f or move.get("id", "") in f:
        return True
    return False


def keywords_for(c, move):
    kws = set(move.get("keywords") or [])
    kws.update(c.r.moves_mech.get(move.get('id'),{}).get('header',{}).get('keywords') or [])
    for e in c.registry:
        if e.get("type") == "gain_keyword" and _move_matches(e, move, c) and not e.get("if"):
            kws.add(e.get("keyword"))
        elif e.get("type") == "gain_keyword" and e.get("if") == "single target":
            kws.add(e.get("keyword"))
    import optional_physical_equipment as OPTIONAL_EQUIPMENT
    crafted = OPTIONAL_EQUIPMENT.marker(move)
    if crafted and crafted["kind"] == "spread_needle" and move["id"] == "move/구슬던지기":
        kws.difference_update(("오단타격", "Five Strike"))
    return kws


def owns_demoralize(engine, actor):
    """ch03:430-432; shared ownership is also the registration policy."""
    import combat_precision_features as CPF
    return CPF.owns(engine, actor, CPF.DEMORALIZE)


def validate_combat_edges(engine, actor):
    owns_demoralize(engine, actor)


def validate_combat_move(engine, actor, move):
    """Do not execute an unsupported combined-damage producer as two attacks."""
    revelation_dance_type(engine, actor, move)
    import eldritch_magic as ELDRITCH
    ELDRITCH.preflight(engine,actor,move)
    import csv_item_capability_contracts as CSV_CAP
    if 'csv_essence_projection' in actor.spec and not CSV_CAP.essence_move_allowed(actor,move):
        raise ValueError('CSV Essence forbids learning or using Ghost/Aura Moves at Essence four or below')
    if "이단타격" in keywords_for(actor, move):
        if __import__('multi_strike').kind(move)!='double':raise ValueError('Double Strike combined damage requires its printed source or a reviewed keyword-grant adapter')
        __import__('multi_strike').preflight(engine,actor,move)


def entry_move_allowed(engine, actor, move, mm, *, target=None, targetless=False):
    """Read-only admission; paid pre_use still rechecks the actual target."""
    if type(targetless) is not bool:raise ValueError('explicit targetless admission policy required')
    __import__('declarative_move_contracts').require_defensive_move(actor,move)
    effects=mm.get('effects_exec',[])+actor.registry
    if not targetless and any(e.get('type')=='targeting_rule' and 'asleep' in str(e.get('valid_targets','')) for e in effects):
        if target is None:raise ValueError('sleep-target admission requires the actual recipient')
        if '잠듦' not in target.conditions:
            engine.log(f"  {actor.name} {move['name']}: 잠든 대상에게만 → {target.name}은(는) 대상 불가", 'effect/targeting_rule')
            return False
    if not any(e.get('type')=='usage_restriction' and 'first turn after entering' in str(e.get('only_if','')) for e in effects):
        return True
    import common_checks as CHECKS
    turns=CHECKS.integer(actor.turns_taken,'actual turns since field entry',0)
    if engine.encounter_active and actor.on_field and turns<=1:
        return True
    engine.log(f"  {actor.name} {move['name']}: 실제 진입 후 첫 턴에만 사용 가능",'effect/usage_restriction')
    return False


def delayed_attack_spec(mm):
    """Return the one declared delayed attack without producing queue state."""
    rows = [e for e in mm.get("effects_exec", []) if e.get("type") == "delayed_attack"]
    if len(rows) > 1:
        raise ValueError("one delayed attack declaration per move required")
    return rows[0] if rows else None


def schedule_delayed_attack(engine, a, t, move, mm, completion_id):
    """Persist a delayed hit only after the native move-use producer commits."""
    effect = delayed_attack_spec(mm)
    if effect is None:
        return False
    if not isinstance(completion_id, str) or completion_id not in getattr(engine, "_move_completions", {}):
        raise ValueError("delayed attack requires its actual move completion")
    engine.delayed.append({"kind": "attack", "who": t,
        "turns": int(effect.get("turns", 1)), "attacker": a,
        "move_id": move["id"], "src": "delayed_attack",
        "completion_id": completion_id})
    engine.log(f"  {a.name} {move['name']}: 지연 공격 예약 — {t.name}의 다음 턴 끝에 명중 (사용자가 없어도)", "effect/delayed_attack")
    return True


def pre_use(engine, a, t, move, mm, *, targetless=False):
    """use_move 앞: 사용 제한·대상 규칙·기술 봉인. False 면 행동이 무효."""
    if type(targetless) is not bool:raise ValueError('explicit targetless pre-use policy required')
    validate_combat_edges(engine, a)
    if not entry_move_allowed(engine,a,move,mm,target=t,targetless=targetless):return False
    effs = mm.get("effects_exec", [])
    import catalog_move_states as CATALOG
    keyword = CATALOG.move_locked(engine,a,move)
    if keyword:
        engine.log(f"  {a.name} {move['name']}: [{keyword}] 기술 봉인 중 → 사용 불가", "effect/move_lock")
        return False
    lock = a.custom_conditions.get("move_lock")
    if lock and lock.get("keyword") and lock["keyword"] in str(move.get("range", "")) + str(move.get("effect", "")):
        engine.log(f"  {a.name} {move['name']}: [{lock['keyword']}] 기술 봉인 중 → 사용 불가", "effect/move_lock")
        return False
    for e in effs + [x for x in a.registry if x.get("type") in ("usage_restriction", "targeting_rule", "forbid")]:
        ty = e.get("type")
        if ty == "usage_restriction":
            cond = str(e.get("only_if", "")) + str(e.get("not_under", ""))
            if "asleep" in cond and "잠듦" not in a.conditions:
                engine.log(f"  {a.name} {move['name']}: 잠든 상태에서만 사용 가능 → 실패", "effect/usage_restriction")
                return False
            if "food buff" in cond:
                import food_effects as FOOD
                if not FOOD.consumed_this_scene(engine,a):
                    engine.log(f"  {a.name} {move['name']}: 이번 장면에 음식 버프를 소비하지 않음 → 실패", "effect/usage_restriction")
                    return False
            if "중력" in cond and __import__('field_effects').airborne_move_fields(engine, a):
                engine.log(f"  {a.name} {move['name']}: 중력(왜곡) 중 사용 불가", "effect/usage_restriction")
                return False
            if "stockpile" in cond and a.counters.get("stockpile", 0) <= 0:
                engine.log(f"  {a.name} {move['name']}: 비축 카운트 없음 → 실패", "effect/usage_restriction")
                return False
        elif ty == "targeting_rule":
            if targetless:
                continue
            vt = str(e.get("valid_targets", ""))
            if "not self" in vt and t is a:
                engine.log(f"  {a.name} {move['name']}: 자신은 대상 불가", "effect/targeting_rule")
                return False
            if "share a type" in vt and not set(a.types) & set(t.types):
                engine.log(f"  {a.name} {move['name']}: 타입을 공유하는 대상에게만 → 실패", "effect/targeting_rule")
                return False
            if "gender" in str(e.get("fails_if", "")):
                ga, gt = a.spec.get("gender"), t.spec.get("gender")
                if ga is None or gt is None:
                    _prompt(engine, e, f"성별 확인 필요 ({a.name}/{t.name}) — 같거나 무성이면 실패", "effect/targeting_rule")
                elif ga == gt or "무성" in (ga, gt):
                    engine.log(f"  {a.name} {move['name']}: 성별이 같거나 무성 → 실패", "effect/targeting_rule")
                    return False
    return True


def accuracy_hook(engine, a, t, move, mm, ctx):
    """(AC 치환, 회피 무시 여부, 추가 명중 보정)."""
    import combat_timing as TIMING
    import status_sets as STATUS
    import vision_impairment as VISION
    import living_weapon as LIVING
    from keen_eye import modifier
    acc = lambda value: modifier(engine,a,value)
    timed = sum(acc(row.get('accuracy_modifier',0)) for row in TIMING.records(a) if not row.get('effect_contract'))
    ac_override, waive, bonus, never = None, False, timed, False
    bonus += acc(__import__('defense_curl').accuracy(a,move))
    for status in a.conditions:
        if __import__('blessing_effects').ignored(a,status):continue
        # Use one derived contribution: Total Blindness replaces ordinary
        # Blindness and observed darkness enters the same accuracy consumer.
        if STATUS.normalize(status) in (VISION.BLIND, VISION.TOTAL):
            continue
        for effect in engine.r.condition_effects(status):
            if effect.get("type")=="accuracy_mod" and type(effect.get("value")) is int:
                bonus += acc(effect["value"])
    bonus += acc(VISION.accuracy_penalty(engine, a, t))
    for e in mm.get("effects_exec", []) + a.registry:
        ty = e.get("type")
        if LIVING.ignore_no_guard(engine,a,t,e,effect_owner=a):continue
        if ty == "accuracy_override" and (FX.cond_ok(engine, e, ctx)[0] or _eval_cond(engine, a, t, e.get("if", ""), ctx)):
            ac_override = e.get("ac")
        elif ty == "never_miss":
            import effect_contracts as CONTRACTS
            if CONTRACTS.never_miss_allowed(engine,a,t,e,ctx):never=True
        elif ty == "ignore_evasion":
            ok = FX.cond_ok(engine, e, ctx)[0] if not e.get("if") else _eval_cond(engine, a, t, e.get("if"), ctx)
            if ok is None:
                _prompt(engine, e, f"회피 무시 조건 '{e.get('if')}' 판단")
            elif ok:
                waive = True
        elif ty == "accuracy_mod" and e.get("moves") and _move_matches(e, move, a) and isinstance(e.get("value"), int):
            bonus += acc(e["value"])
    # The native passive producer keeps No Guard's enemy contribution in
    # modifiers; other existing target effects continue to use registry.
    no_guard_modifiers = [e for e in t.modifiers if LIVING.no_guard(e)
                          and e.get("target") == "enemies vs user"]
    for e in t.registry + no_guard_modifiers:
        no_guard_enemy = (LIVING.no_guard(e) and e.get("target") == "enemies vs user"
                          and getattr(a,"side",None) != getattr(t,"side",None))
        if e.get("type") == "accuracy_mod" and (str(e.get("target", "")).startswith("attacks against") or no_guard_enemy) and isinstance(e.get("value"), int):
            if LIVING.ignore_no_guard(engine,a,t,e,effect_owner=t):continue
            bonus += acc(e["value"])
    waive = waive or __import__("roughneck").vulnerable(engine,a,t,move)
    never = never or __import__('juggler').lock_on(engine,a,t)
    return ac_override, waive, bonus, never


def crit_hook(engine, a, t, move, hit, crit, *, natural=None, crit_min=20):
    """Owned Demoralize permits status criticals; existing blessings follow."""
    if __import__('declarative_move_contracts').defensive_critical_immunity(t):return False
    import ability_transitions as ABILITIES,taskmaster as TASK
    if (hit and TASK.gambit_side(engine,a,t,move)!='incoming'
            and ABILITIES.active(t,'ability/조가비갑옷-전투무장')
            and not __import__('trickster').ignores_defensive(engine,t,'ability/조가비갑옷-전투무장')
            and not __import__('chronicler').defensive_ignored(engine,a,t,move)):
        return False
    import combat_precision_features as CPF
    if hit and move["class"] == "변화" and natural is not None and CPF.status_can_critical(engine, a, t, move):
        threshold = __import__("provocateur").demoralize_threshold(a,crit_min) if CPF.owns(engine,a,CPF.DEMORALIZE) else crit_min
        crit = natural >= threshold
    import blessing_effects as BLESSINGS
    crit,handled = BLESSINGS.critical(engine,a,t,move,hit,crit)
    if handled:return crit
    if hit and crit:
        for b in t.blessings:
            if 'effect_instance' in b:continue
            if b["left"] > 0 and "crit" in b["on"]:
                b["left"] -= 1
                engine.log(f"    축복 {b['name']} 발동: 치명타를 보통 피해로 (남은 {b['left']})", "effect/blessing")
                return False
    if hit and not crit and move["class"] in ("물리", "특수"):
        for b in a.blessings:
            if 'effect_instance' in b:continue
            if b["left"] > 0 and "crit" in b["effect"] and "attack" in b["on"]:
                b["left"] -= 1
                engine.log(f"    축복 {b['name']} 발동: 명중을 치명타로 (남은 {b['left']})", "effect/blessing")
                return True
    return crit


def prepare_versatile_move(engine, move, selected=None):
    """ch10:440: explicit attack-stat choice; only Variable class changes class."""
    selected = move.get('_versatile_attack_stat') if selected is None else selected
    if '가변' not in (move.get('keywords') or []):
        if selected is not None:raise ValueError('attack-stat choice requires the Versatile keyword')
        return move
    if selected is None:
        if move.get('class') == '가변':raise ValueError('Versatile Move requires an explicit atk or spa choice')
        return move
    if selected not in ('atk','spa'):raise ValueError('Versatile attack stat must be atk or spa')
    if move.get('prime_unown_instance') or move.get('_unown_use'):
        raise ValueError('existing Unown instance owns its damage-class selection')
    from source_context import verified_source
    verified_source(engine.r,{'file':'input/ch10-index-reference.md',
        'sha256':'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'},label='Versatile keyword')
    result=dict(move,_versatile_attack_stat=selected)
    if move.get('class') == '가변':result['class']='물리' if selected=='atk' else '특수'
    return result


def grants_stab(engine, a, move):
    if __import__('type_expertise').grants_stab(engine, a, move):
        return True
    import stellar_tera_blast as STELLAR_TERA
    if STELLAR_TERA.grants_stab(engine,a,move):
        return True
    return any(e.get("type") == "stab_grant" and e.get("move_type") == move["type"]
               and e.get("form") == a.form and __import__('ability_transitions').effect_active(a,e)
               for e in a.registry)


def db_hook(engine, a, move, mm):
    """DB 보정: 레지스트리의 damage_base_mod/damage_bonus, 누적 DB, 무작위 DB."""
    mod = 0
    for e in a.registry + a.modifiers:
        ty = e.get("type")
        if ty in ("damage_base_mod", "damage_bonus") and isinstance(e.get("value"), int) and e.get("move_type") in (None, move["type"]) and (e.get("moves") is None or _move_matches(e, move, a)):
            if ty == "damage_base_mod" and e in a.modifiers:
                continue    # passive_damage_mods 가 이미 처리
            mod += e["value"]
    for e in mm.get("effects_exec", []):
        ty = e.get("type")
        if ty == "escalating_damage_base":
            key = f"esc:{move['id']}"
            n = a.counters.get(key, 0)
            step = int(e.get("step", 0))
            cap = e.get("max")
            add = step * n
            base = e.get("base")
            if base is not None:
                mod += int(base) - int(move.get("damage_base") or 0)
            mod += add
            a.counters[key] = n + 1
            if isinstance(cap, int):
                mod = min(mod, cap - int(move.get("damage_base") or 0))
            engine.log(f"    누적 DB: {n}회 성공 후 +{add} (최대 {cap})", "effect/escalating_damage_base")
        elif ty == "random_db":
            m = re.search(r"d(\d+)", str(e.get("roll", "1d6")))
            roll = POOLS.die(engine.rng, int(m.group(1)) if m else 6)
            expr = str(e.get("damage_base", "roll")).replace("x", "*")
            val = FX.evaluate(expr.replace("roll", str(roll)), {})
            if val is not None:
                mod += val - int(move.get("damage_base") or 0)
            engine.log(f"    무작위 DB: {e.get('roll')}={roll} → DB {val}", "effect/random_db")
            if roll == 1 and isinstance(e.get("if_1"), dict):
                engine.random_db_flag = e["if_1"]
    return mod


def keyword_block_reason(engine,a,t,move):
    """Only selected keyword immunity, shared by hit and non-hit field recipients."""
    if '풀' in t.types and keywords_for(a,move).intersection(('가루','Powder')):
        return 'type/풀:Powder immunity'
    blocked_keywords = {k for k in keywords_for(a,move) if __import__('trickster').set_contains(engine,t,'keyword_immune',k)}
    if blocked_keywords:
        return "state/keyword_immunity:" + ",".join(sorted(blocked_keywords))
    if not t.abilities_suppressed:
        for effect in t.modifiers:
            if (effect.get('type')=='immunity' and effect.get('keyword') in keywords_for(a,move)
                    and __import__('ability_transitions').effect_active(t,effect)):
                source=effect.get('_rule_id')
                if not isinstance(source,str) or engine.r._selected_rule(source)!=source:raise ValueError('selected keyword immunity source required')
                if __import__('trickster').ignores_defensive(engine,t,source):continue
                return source
    return None


def blocks_hit(engine,a,t,move,mm):
    if __import__('oracle').sight(t) and set(keywords_for(a,move)).intersection(('Illusion','환영')):return __import__('oracle').SIGHT
    ace=__import__('type_ace').blocks_hit(engine,a,t,move)
    if ace:return ace
    """PTU p336 Wonder Guard prevents hitting, unlike ordinary damage immunity.

    Type substitution/effectiveness hooks consume coats, blessings and one-shot
    choices during damage resolution. Preview only on isolated mutable state;
    the real producer consumes those resources once if an attack can hit.
    """
    import newground_flight_option as GROUND_FLIGHT
    ground_flight_block = GROUND_FLIGHT.block_reason(engine, a, t, move, mm)
    if ground_flight_block:return ground_flight_block
    import body_modes as BODY_MODES
    import marsupial_state as MARSUPIAL
    if MARSUPIAL.attack_blocked(a,t,move,engine=engine):return MARSUPIAL.SOURCE
    if not BODY_MODES.targetable(t,attack=False):return BODY_MODES.DEFINITIONS['phasing']['source']
    import mindlock as MINDLOCK
    mindlock_block=MINDLOCK.move_block(engine,a,t,move)
    if mindlock_block:return mindlock_block
    move_id=move.get("id")
    if move_id=='move/카운터' and engine.type_multiplier('격투',t)[0]==0:return 'move/카운터:Fighting immunity'
    blocked_moves=[]
    for value in getattr(t,"move_immune",()):
        if not __import__('trickster').set_contains(engine,t,'move_immune',value):continue
        if value==move_id:
            blocked_moves.append(value);continue
        try:resolved=engine.r.move_id(value)
        except (KeyError,ValueError):resolved=None
        if resolved==move_id:blocked_moves.append(value)
    if blocked_moves:
        return "state/move_immunity:"+str(move_id)
    keyword_reason=keyword_block_reason(engine,a,t,move)
    if keyword_reason:return keyword_reason
    if move.get("class") not in ("물리","특수") or t.abilities_suppressed:return None
    import commander_orders as COMMANDER
    if COMMANDER.perfect(engine,a,move) is not None:return None
    guards=[x for x in t.modifiers if x.get("type")=="immunity" and x.get("to")=="non-super-effective damage"
            and __import__('ability_transitions').effect_active(t,x)]
    if not guards:return None
    import blessing_effects as BLESSINGS
    shared_offense=[record for _,record in BLESSINGS.beneficiaries(engine,a,'team_damage_effectiveness')
                    if move['class'] in record['effect']['classes']]
    uid="ability/불가사의부적"
    if engine.r._selected_rule(uid)!=uid or any(x.get("_rule_id",uid)!=uid or x.get("unless")!="no weaknesses" for x in guards):
        raise ValueError("selected Wonder Guard variant requires its own hit policy")
    import type_state as TYPE_STATE
    if not any(engine.type_multiplier(ty,t)[0]>1 for ty in TYPE_STATE.attack_types(engine.r)):return None
    from copy import copy,deepcopy
    preview=copy(engine);preview.log_lines=[];preview.gm_prompts=[];preview.decide=lambda prompt:None
    user=copy(a);target=copy(t)
    user.counters=deepcopy(a.counters);user.blessings=deepcopy(a.blessings)
    target.coats=deepcopy(t.coats);target.blessings=deepcopy(t.blessings)
    mtype=effective_type(preview,user,target,move,mm)
    mult=preview.type_multiplier(mtype,target)[0]
    context={"attacker":user,"target":target,"multiplier":mult,"crit":False,"hit":True,"move":move,"engine":preview}
    mult=effectiveness_hook(preview,user,target,move,mm,mult,context)
    if preview.gm_prompts:raise ValueError("Wonder Guard effectiveness needs the unresolved conditional type ruling before attack cost")
    # Defender resistance steps are part of the existing actual damage pipeline.
    context["multiplier"]=mult
    _,_,resist,_,_=FX.passive_damage_mods(preview,user,target,move,context)
    if resist:
        steps={1.0:0,1.5:1,2.0:2,3.0:3,0.5:-1,0.25:-2,0.125:-3}.get(mult,0)-resist
        mult=preview.r.mech("combat/type-effectiveness")["multiplier_by_net_steps"][str(max(-3,min(3,steps)))] if mult else 0
    if mult<=1 and (target.coats!=t.coats or target.blessings!=t.blessings):
        raise ValueError("Wonder Guard versus consumed defensive resistance needs an explicit activation-order ruling before attack cost")
    potential=mult
    if mult and mult<=1 and not BLESSINGS.reaction_blocked(engine,a,move):
        for record in shared_offense:potential=BLESSINGS._damage_multiplier(engine.r,record,potential)
        if potential>1:
            raise ValueError('Wonder Guard versus optional shared Blessing offense needs an explicit activation-order ruling before attack cost')
    return uid if mult<=1 else None


def revelation_dance_type(engine, actor, move):
    """R559 uses the selected species registration, never mutable actor typing."""
    if move.get('id') != 'move/잠재댄스':
        return None
    if engine.r._selected_rule(move['id']) != move['id']:
        raise ValueError('selected Revelation Dance source required')
    species = engine.r.species.get(actor.spec.get('species'))
    if actor.kind != 'pokemon' or species is None:
        raise ValueError('Revelation Dance requires a registered Pokemon species')
    if engine.r._selected_rule(species['id']) != species['id']:
        raise ValueError('Revelation Dance requires the selected registered species')
    types = species.get('types')
    if not isinstance(types, list) or not types:
        raise ValueError('Revelation Dance requires an ordered registered first type')
    import type_state as TYPE_STATE
    TYPE_STATE.validate_attack(engine.r, types[0])
    return types[0]


def effective_type(engine, a, t, move, mm, *, consume=True):
    """타입 치환: 집단구타 등 1회 치환, 레지스트리 type_override_moves, alternate_type(사용자 선택 → 유리한 쪽)."""
    registered_type = revelation_dance_type(engine, a, move)
    if registered_type is not None:
        move = dict(move, type=registered_type)
    move = __import__('weather_state').prepare_weather_ball(engine,a,move)
    import declarative_move_contracts as DECLARATIVE_MOVES
    declarative=DECLARATIVE_MOVES.effective_type(engine,a,t,move,preview=not consume)
    if declarative is not None:
        return declarative
    import stellar_tera_blast as STELLAR_TERA
    stellar_type=STELLAR_TERA.effective_type(engine,a,t,move)
    if stellar_type is not None:
        return stellar_type
    if a.type_override_next:
        ty=a.type_override_next
        if consume:a.type_override_next=None
        return ty
    for e in a.registry:
        if e.get("type") == "type_override_moves" and _move_matches(e, move, a) and e.get("as_type") in TYPES:
            return e["as_type"]
    for zr in engine.zone_rules:
        r = zr["rule"]
        if r.get("normal_moves_become") in TYPES and move["type"] == "노말" and engine.grid is not None and zr["center"] is not None:
            from grid import cheb
            if cheb(a.pos, zr["center"]) <= zr["radius"]:
                return r["normal_moves_become"]
    import alternate_move_modes as ALTERNATE
    explicit=ALTERNATE.effective_type(engine,a,t,move,preview=not consume)
    if explicit is not None:
        return explicit
    # Fistful's paid shard choice owns Judgment's otherwise optional 'any' type.
    if move.get('_researcher_fistful') is not None:
        return move['_researcher_fistful']['type']
    if registered_type is not None:
        return registered_type
    counters=a.counters if consume else dict(a.counters)
    best = move["type"]
    best_mult = engine.type_multiplier(move["type"], t)[0]
    for e in mm.get("effects_exec", []):
        if e.get("type") == "alternate_type":
            if ALTERNATE.owns(engine.r,move,e):
                continue
            cand = e.get("move_type")
            if cand == "user's tera type":
                cand = a.spec.get("tera_type")
            elif cand == "user's first type":
                cand = a.types[0] if a.types else None
            elif cand == "any":
                cand = max(TYPES, key=lambda x: engine.type_multiplier(x, t)[0])
            elif cand == "any of user's types":
                cand = max(a.types, key=lambda x: engine.type_multiplier(x, t)[0]) if a.types else None
            if cand not in TYPES:
                continue
            if e.get("if") and _eval_cond(engine, a, t, e["if"], {}) is False:
                continue
            lim = str(e.get("limit", ""))
            key = f"alt:{move['id']}"
            if "scene" in lim and counters.get(key, 0) >= 1:
                continue
            m2 = engine.type_multiplier(cand, t)[0]
            if m2 > best_mult:
                best, best_mult = cand, m2
                if "scene" in lim:
                    counters[key] = counters.get(key, 0) + 1
    if consume and best != move["type"]:
        engine.log(f"    타입 치환: {move['type']} → {best} (유리한 쪽 선택)", "effect/alternate_type")
    return best


def effectiveness_hook(engine, a, t, move, mm, mult, ctx):
    """상성 치환·단계 보정·축복(공격 측)·코트(타르샷)·부유 면역."""
    import cleanse_tags as CLEANSE
    if 'actual_damage_type' not in ctx:
        ctx['actual_damage_type']=effective_type(engine,a,t,move,mm,consume=False)
    import catalog_move_states as CATALOG
    actual_move = dict(move, type=ctx['actual_damage_type'])
    arrows_policy = CATALOG.thousand_arrows_policy(engine, move, mm)
    mult = CATALOG.thousand_arrows_base(engine, t, actual_move, arrows_policy, mult)
    mult = CLEANSE.weapon_effectiveness(engine,a,t,move,ctx['actual_damage_type'],mult,ctx)
    import optional_physical_equipment as OPTIONAL_EQUIPMENT
    crafted_ground = OPTIONAL_EQUIPMENT.bypass_ability_immunity(actual_move, actual_move["type"])
    if crafted_ground:
        mult = OPTIONAL_EQUIPMENT.effectiveness(engine, t, actual_move, mult)
    te = engine.r.mech("combat/type-effectiveness")["multiplier_by_net_steps"]
    step_of = {1.0: 0, 1.5: 1, 2.0: 2, 3.0: 3, 0.5: -1, 0.25: -2, 0.125: -3}
    steps = step_of.get(mult, 0)
    immune = mult == 0
    changed = False
    import stellar_tera_blast as STELLAR_TERA
    for e in mm.get("effects_exec", []) + a.registry:
        if e.get("type") != "type_effectiveness_override":
            continue
        if (arrows_policy is not None and any(e is own for own in mm.get("effects_exec", []))
                and CATALOG._semantic(e) == arrows_policy["legacy_effect"]):
            continue
        if STELLAR_TERA.owns_effect(engine.r,move,e):
            continue
        if e.get("if_target_type") and e.get("as_if_attack_type"):
            if e["if_target_type"] in t.types:
                m2 = engine.type_multiplier(e["as_if_attack_type"], t)[0]
                if m2:
                    steps = step_of[m2] if immune else max(steps, step_of[m2])
                    immune = False
                    changed = True
        elif e.get("steps"):
            ok = _eval_cond(engine, a, t, e.get("if", ""), ctx) if e.get("if") else True
            if ok is None:
                _prompt(engine, e, f"상성 조건 '{e.get('if')}' 판단")
            elif ok:
                steps += int(str(e["steps"]).replace("+", "").split()[0]) if re.match(r"[+\-]?\d", str(e["steps"])) else 1
                changed = True
        elif e.get("resisted_moves"):
            if steps < 0:
                steps += 1
                changed = True
    for b in a.blessings:
        if 'effect_instance' in b:continue
        if b["left"] > 0 and "effectiveness" in b["effect"] and (("physical" in b["on"] and move["class"] == "물리") or ("special" in b["on"] and move["class"] == "특수")):
            b["left"] -= 1
            steps += 1
            changed = True
            engine.log(f"    축복 {b['name']} 발동: 한 단계 더 효과적 (남은 {b['left']})", "effect/blessing")
    import damage_coats as DAMAGE_COATS
    coat_steps=DAMAGE_COATS.steps(engine,t,dict(move,type=ctx["actual_damage_type"]))
    if coat_steps:steps+=coat_steps;changed=True
    for c in list(t.coats):
        if 'effect_instance' in c:continue
        eff = c.get("effect") if isinstance(c.get("effect"), dict) else {}
        if eff.get("extra_weakness_step") == ctx["actual_damage_type"]:
            steps += 1
            changed = True
            t.coats.remove(c)
            engine.log(f"    코트 {c.get('coat')} 발동: {ctx['actual_damage_type']}에 한 단계 더 취약 후 소멸", "effect/apply_coat")
        elif eff.get("resist_once") == ctx["actual_damage_type"]:
            steps -= 1
            changed = True
            t.coats.remove(c)
            engine.log(f"    코트 {c.get('coat')} 발동: {ctx['actual_damage_type']} 1회 저항 후 소멸", "effect/apply_coat")
    for b in t.blessings:
        if 'effect_instance' in b:continue
        if b["left"] > 0 and "resistance" in b["effect"] and (("physical" in b["on"] and move["class"] == "물리") or ("special" in b["on"] and move["class"] == "특수") or ("damage" in b["on"] and "physical" not in b["on"] and "special" not in b["on"])):
            b["left"] -= 1
            steps -= 1
            changed = True
            engine.log(f"    축복 {b['name']} 발동: 한 단계 저항 (남은 {b['left']})", "effect/blessing")
    import field_effects as FIELD
    import csv_item_physical_contracts as CSV_ITEMS
    if not crafted_ground and CSV_ITEMS.ground_immunity(engine,t,actual_move):
        engine.log(f"    {t.name} 풍선으로 땅 기술 무효", "item/풍선")
        return 0.0
    if (not crafted_ground and CATALOG.levitate_blocks(engine,t,actual_move,mm,attacker=a)
            and not FIELD.suppresses_ground_immunity(engine,t,{"_ability":"부유"})):
        engine.log(f"    {t.name} 부유 특성으로 땅 기술 무효", "ability/부유")
        return 0.0
    # Resistance/weakness steps cannot turn immunity into a damaging matchup.
    resolved = te[str(max(-3, min(3, steps)))] if changed and not immune else mult
    resolved = STELLAR_TERA.effectiveness(engine,a,t,move,resolved,ctx)
    resolved = __import__('typed_defensive_bypass').effectiveness(engine,a,t,move,resolved,actual_type=ctx['actual_damage_type'])
    import optional_physical_equipment as OPTIONAL_EQUIPMENT
    return resolved if crafted_ground else OPTIONAL_EQUIPMENT.effectiveness(engine, t, actual_move, resolved)


def reduction_after_ignore(reduction, effects):
    """Preserve a sourced numeric DR bypass instead of treating it as all DR."""
    import re
    ignore=next((effect for effect in reversed(effects) if effect.get('type')=='ignore_defense_modifiers'),None)
    if ignore is None:return reduction
    spec=str(ignore.get('ignore',''))
    amount=re.search(r'(?<!\d)(\d+)\s+damage reduction\b',spec)
    if amount:return max(0,reduction-int(amount[1]))
    return 0 if 'damage reduction' in spec or 'armor' in spec else reduction


def defense_hook(engine, a, t, move, mm, def_stat, *, stage_override=None):
    """방어 수정자 무시(DD래리어트·야금야금·천진 썬문): (방어값, 피해감소)."""
    ignore = None
    for e in mm.get("effects_exec", []) + a.registry:
        if e.get("type") == "ignore_defense_modifiers":
            ignore = e
    import effect_lifetimes as LIFETIMES
    staged=t.staged(def_stat)
    stage=t.stages[def_stat]
    if stage_override is not None:
        import arithmetic_policy as M,optional_state_effect_contracts as OPTIONAL,state_fields as FIELDS
        if type(stage_override) is not int or not -6<=stage_override<=6:raise ValueError('actual assumed defense Combat Stage required')
        stage=stage_override
        staged=max(FIELDS.stat_minimum(t.spec,def_stat),OPTIONAL.staged_value(t,def_stat,
            M.stage_stat(t.stats[def_stat],stage,engine.r.mech('combat/combat-stage-multipliers')['multiplier_by_stage'])))
    dr = t.damage_reduction + LIFETIMES.numeric(t,"damage_reduction") + __import__('sage').reduction(t) + __import__('ace_trainer').damage_reduction(t,a) + __import__('defense_curl').reduction(t) + __import__('declarative_move_contracts').defensive_reduction(t)
    if not t.abilities_suppressed:
        for e in t.modifiers:
            if e.get("type") == "damage_reduction" and e.get("if_weather") and isinstance(e.get("value"), int) and not any(e.get(k) for k in ("if", "vs", "duration")) and FX.weather_matches(engine, e["if_weather"],t) and not __import__("survivalist_class").weather_ability_suppressed(engine,t,e.get("_rule_id")):
                dr += e["value"]
    if ignore is None:
        return staged, dr
    spec = str(ignore.get("ignore", ""))
    val = t.stats[def_stat] if ("positive" in spec and stage > 0) or "stage" in spec else staged
    dr = reduction_after_ignore(dr, mm.get('effects_exec', []) + a.registry)
    engine.log(f"    방어 수정자 무시: {spec} → {def_stat} {val}, DR {dr}", "effect/ignore_defense_modifiers")
    return val, dr


def multiplier_hook(engine, a, move, mm, ctx):
    for e in mm.get("effects_exec", []):
        if e.get("type") == "damage_multiplier" and FX.cond_ok(engine, e, ctx)[0]:
            engine.log(f"    피해 배수 ×{e.get('value')} ({e.get('if_weather', '')})", "effect/damage_multiplier")
            return float(e.get("value", 1))
    return 1.0


def cap_damage(engine, c, amount, *, loss_kind='damage'):
    cap = c.damage_cap
    if not cap:
        return amount
    if loss_kind not in ('damage', 'loss', 'percentage', 'hp_setting'):
        raise ValueError('known damage or HP-loss kind required')
    scope = cap.get('applies_to')
    if scope not in (None, 'damage', 'damage and hp loss'):
        raise ValueError('unsupported damage-cap scope')
    if loss_kind != 'damage' and scope == 'damage':
        return amount
    if not __import__('hp_setting_moves').cap_active(engine, c, cap):
        return amount
    v = FX._amount(cap.get('value'), c, engine, {'attacker': c})
    if v is None:
        return amount
    if cap.get('round') == 'up' and str(cap.get('value', '')).endswith('/2'):
        v = M.ceil_ratio(c.base_max_hp, 2)
    if amount > v:
        engine.log(f"    피해 상한 {v} 적용 ({amount} → {v})", 'effect/damage_cap')
        return v
    return amount


def after_damage(engine, c):
    rule = c.form_rule
    if rule and "hp < half" in str(rule.get("trigger", "")) and c.hp < c.base_max_hp / 2 and c.form != rule["forms"][-1]:
        import form_allocations as FORMS
        FORMS.switch(engine,c,rule["forms"][-1])
        engine.log(f"    {c.name} 폼 체인지 → {c.form} (체력 절반 미만)", "effect/form_change")
    if c.reflect and getattr(engine, "_last_attacker", None) is not None and getattr(engine, "_last_dealt", 0) > 0:
        pass    # 반사는 fire_event 경로에서 처리
    if c.fainted:
        import csv_item_physical_contracts as CSV_ITEMS
        import csv_item_form_contracts as CSV_FORMS
        CSV_ITEMS.switched_or_fainted(c)
        CSV_FORMS.fainted(engine,c)


def stage_hook(engine, c, delta):
    """흰안개: 남이 내리는 전투단계 무효."""
    if delta >= 0:return False
    import blessing_effects as BLESSINGS
    if BLESSINGS.stage_guard(engine,c,delta):return True
    if getattr(engine, "_inflictor", None) is c:return False
    for b in c.blessings:
        if 'effect_instance' in b:continue
        if b["left"] > 0 and "stage" in b["on"]:
            b["left"] -= 1
            engine.log(f"    축복 {b['name']} 발동: 전투단계 하락 무효 (남은 {b['left']})", "effect/blessing")
            return True
    return False


def demoralize_hit(engine, attacker, target, *, hit, critical):
    if hit and critical and owns_demoralize(engine, attacker):
        if getattr(attacker, "side", None) is not None and getattr(target, "side", None) is not None and attacker.side != target.side:
            engine.apply_status(target, "취약")


def after_move(engine, a, t, move, mm, ctx):
    """명중 후: 사기저하, 반사(reaction_reflect), 반응 기술."""
    HEAVY.ensure_clear(engine)
    validate_combat_move(engine, a, move)
    demoralize_hit(engine, a, t, hit=ctx.get("hit"), critical=ctx.get("crit"))
    import combat_social_edges as SOCIAL
    SOCIAL.after_hit(engine,a,t,move,mm,ctx.get("hit"))
    __import__("provocateur").critical_tick(engine,a,t,move,ctx)
    rf = t.reflect
    if rf and ctx.get("dealt", 0) > 0 and not t.fainted and move["class"] in ("물리", "특수"):
        trig = str(rf.get("trigger", ""))
        if ("physical" in trig and move["class"] != "물리") or ("special" in trig and move["class"] != "특수"):
            return
        expr = str(rf.get("attacker_hp_loss") or rf.get("adjacent_enemies_hp_loss") or "hp user lost")
        mult = 2 if expr.startswith("2") else 1
        loss = ctx["dealt"] * mult
        engine.log(f"    반사({rf.get('type')}): {a.name}이(가) {loss} 체력 손실 ({expr})", "effect/reaction_reflect")
        import attack_damage_history as HISTORY
        HISTORY.received_loss(engine,a,loss,source="반사")
        t.reflect = None
        t.modifiers = [m for m in t.modifiers if not m.get("_reflect")]
    for tr in list(t.ability_triggers):
        rx = tr.get("reaction")
        if rx and tr.get("move_id") and FX.event_matches(tr["spec"], {"event": "on_hit_received", "move": move}) and not t.fainted:
            key = "rx:" + tr["move_id"]
            if t.counters.get(key, 0) >= 1:
                continue
            t.counters[key] = 1
            engine.log(f"    [반응] {t.name}: {rx.get('type')} — {rx.get('trigger', '')[:40]} → {tr['move_id']} 사용", "effect/reaction_attack")
            if rx.get("type") in ("reaction_attack",):
                engine.use_move(t, a, tr["move_id"], count_use=False)
            elif rx.get("type") == "reaction_redirect":
                engine.log(f"    가로채기: 효과 대상을 {t.name}으로 치환 (기록)", "effect/reaction_redirect")
            else:
                _prompt(engine, rx, f"반응 효과: {rx.get('effect', '')}")


def multi_roll_spec(mm):
    return next((e for e in mm.get("effects_exec", []) if e.get("type") == "multi_roll"), None)


# PTK ch10:379. Keep the condition's own children separate from independent
# Slowed/Trapped sources; curing Vortex must not remove unrelated afflictions.
def vortex_escape_bonus(parameters):
    return VORTEX.escape_bonus(parameters)


def configure_vortex(c, parameters):
    return VORTEX.configure(c, parameters)


def before_apply_status(engine, c, cond):
    import combat_timing as TIMING
    TIMING.on_status_apply(c,cond)
    VORTEX.before_apply(engine,c,cond)


def after_apply_status(engine, c, cond):
    VORTEX.applied(engine,c,cond)


def before_cure_status(engine, c, cond):
    import combat_timing as TIMING
    TIMING.on_status_cure(c,cond)
    VORTEX.before_cure(engine,c,cond)
    import declarative_move_contracts as DECLARATIVE_MOVES
    DECLARATIVE_MOVES.before_cure(engine,c,cond)
    import csv_item_physical_contracts as CSV_ITEMS
    CSV_ITEMS.before_cure_status(engine,c,cond)


def movement_profile(engine, c, land, sky, movement_mode=None, capabilities=None, *, as_slowed=False):
    """Apply Speed stages then Slowed to the actor's existing movement values.

    ch07:239: half the stage count, using ordinary rounding down; a negative
    stage cannot reduce an available movement capability below 2. Absent
    capabilities remain absent. No choice of path or movement mode is invented.
    """
    import combat_stage_sources as STAGE_SOURCES
    import optional_state_effect_contracts as OPTIONAL_STATE
    if type(as_slowed) is not bool:raise ValueError('as-Slowed movement projection must be boolean')
    delta = M.ratio(STAGE_SOURCES.effective_stage(c,'spe'),2)
    def adjusted(value):
        if value <= 0:
            return 0
        value = max(min(value, 2), value + delta) if delta < 0 else value + delta
        if "둔화" in __import__('blessing_effects').effective_conditions(c) or as_slowed or __import__('setup_move_state').liquefied(c):
            value = max(1, M.ratio(value,2))
        value += OPTIONAL_STATE.movement_addition(c)
        return OPTIONAL_STATE.movement_limit(c,value)
    if movement_mode is not None:
        names = {"land": "육상", "sky": "공중/부유", "levitate": "공중/부유",
                 "swim": "수중", "burrow": "지중", "teleport": "순간이동"}
        if movement_mode not in names:
            raise ValueError("unknown movement capability")
        movement = capabilities if capabilities is not None else (c.spec.get("movement") or {})
        value = movement.get(movement_mode, land if movement_mode == "land" else 0)
        if type(value) is not int or value <= 0:
            raise ValueError("selected movement capability is not possessed")
        return adjusted(value), names[movement_mode]
    land, sky = adjusted(land), adjusted(sky)
    return (sky, "공중/부유") if sky > land else (land, "육상")


def start_of_turn(engine, c):
    c.turns_taken += 1
    VORTEX.turn_start(engine,c)
    import coat_effects as COATS,effect_instances as INSTANCES
    COATS.turn_start(engine,c)
    import custom_condition_effects as CUSTOM
    CUSTOM.turn_start(engine,c)
    for coat in c.coats:
        if INSTANCES.KEY in coat:continue
        eff = coat.get("effect") if isinstance(coat.get("effect"), dict) else {}
        if eff.get("heal_per_turn"):
            v = FX._amount(eff["heal_per_turn"], c, engine, {"attacker": c})
            if v:
                engine.log(f"    코트 {coat.get('coat')}: 턴 시작 회복 {v}", "effect/apply_coat")
                engine.heal(c, v)
    if c.grounded:
        c.grounded -= 1
    if c.form_rule and c.form_rule.get("at") == "turn start":
        import form_allocations as FORMS
        FORMS.switch(engine,c,c.form_rule["forms"][0])
        engine.log(f"    {c.name} 폼 선택(턴 시작): {c.form}", "effect/form_change")


def end_of_turn(engine, c):
    __import__('weather_passive_benefits').end_turn(engine,c)
    __import__('type_ace').end_turn(engine,c)
    __import__('type_ace').fire_boundary(engine,c)
    HEAVY.ensure_clear(engine)
    __import__('wish_move').end_turn(engine,c)
    VORTEX.turn_end(engine,c)
    for d in list(engine.delayed):
        if d['kind']=='wish':continue
        if d["who"] is not c:
            continue
        d["turns"] -= 1
        if d["turns"] > 0:
            continue
        engine.delayed.remove(d)
        if d["kind"] == "heal":
            num, den = d["effect"].get("fraction_of_max", [1, 2])
            engine.log(f"    예약된 회복 발동 ({d['src']})", "effect/delayed_heal")
            engine.heal(c, M.ratio(c.base_max_hp*num,den), source_kind=d.get("healing_source_kind","unspecified"))
        elif d["kind"] == "attack":
            a = d["attacker"]
            engine.log(f"    지연 공격 발동: {a.name}의 {d['move_id']} → {c.name}" + ("" if a.on_field and not a.fainted else " (사용자 부재/기절이어도 명중)"), "effect/delayed_attack")
            move = engine.r.move(d["move_id"])
            import move_completion as COMPLETE
            completion_id=d.get("completion_id")
            if c.fainted:
                COMPLETE.finish_target(engine,completion_id,a,c,hit=False,dealt=0,cancelled=True)
                continue
            import precise_actions as PRECISE
            precision_event=PRECISE.attacked(engine,a,c,move,producer="effects_ext.delayed_attack")
            precision_facts={};damage_event={}
            dealt = engine.roll_damage(a, c, move, False, _precision_observation=precision_facts,_reaction_event=damage_event)
            PRECISE.damage_hit(engine,a,c,move,precision_event,precision_facts,dealt)
            if precision_facts.get("hit_prevented"):
                COMPLETE.finish_target(engine,completion_id,a,c,hit=False,dealt=0)
                continue
            history_before={'requested':dealt,'state':__import__('combat_damage').observe(c),
                            'heavy_sequence':engine._heavy_sequence}
            application=HEAVY.apply_attack_damage(engine, a, c, dealt, move,
                producer=HEAVY.Producer.DELAYED_HIT,
                remainder="remaining delayed queue and outer turn-end effects have not run; current delayed record already removed",
                actual_damage_type=precision_facts.get("actual_damage_type"))
            if isinstance(application,dict) and application.get('source')==__import__('channeler').PAIN:dealt=0
            else:
                __import__('attack_damage_history').record_delayed_hit(engine,a,c,move,completion_id,
                    history_before,precision_facts.get('actual_damage_type',move['type']),precision_facts.get('type_multiplier'))
            COMPLETE.finish_target(engine,completion_id,a,c,hit=True,dealt=dealt)
    import declarative_move_contracts as DECLARATIVE_MOVES
    DECLARATIVE_MOVES.end_turn(engine,c)


def on_enter_cell(engine, c, cell, *, previous_position=None):
    __import__('type_ace').enter_cell(engine,c,cell)
    import nicolette_gym as NICOLETTE
    NICOLETTE.enter_cell(engine, c, 'walk')
    import ice_lake as ICE_LAKE
    ICE_LAKE.enter(engine, c)
    import body_modes as BODY_MODES
    BODY_MODES.sync_shadows(engine)
    import marsupial_state as MARSUPIAL
    MARSUPIAL.sync(engine)
    import hazard_state as HAZARDS
    result=HAZARDS.on_enter_cell(engine,c,cell,previous_position=previous_position)
    pending=__import__('marksman').moved(engine,c)
    return pending if isinstance(pending,__import__('common_checks').PendingDecision) else result


def save_dc(engine, c, cond, dc):
    """Use cond=None for a declared general saving check without an affliction."""
    import persistent_conditions as PERSISTENT
    if cond is not None:dc=PERSISTENT.base_save_dc(engine,c,cond,dc)
    p = engine.condition_params.get(cond, {})
    import combat_social_edges as SOCIAL
    import enduring_awareness as AWARENESS
    import effect_lifetimes as LIFETIMES
    import training_features as TRAINING
    import eldritch_magic as ELDRITCH
    return dc + int(p.get("escape_dc_bonus", 0)) - c.save_mod - LIFETIMES.numeric(c,"save_modifier") - SOCIAL.save_bonus(engine,c,cond) - AWARENESS.bonus(engine,c) - TRAINING.bonus(c,"save") - ELDRITCH.save_modifier(c) - __import__('ace_trainer').save_bonus(c)
