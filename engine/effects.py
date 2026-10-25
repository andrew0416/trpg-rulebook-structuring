"""
effect-vocabulary 실행기. data/moves-mech·moves-llm·abilities-llm 의 effect 레코드를 엔진 동작으로 바꾼다.
  - HANDLERS: 기술 사용 시점에 실행되는 effect 유형 (명중 후, 혹은 조건부)
  - PASSIVES: 특성처럼 전투 내내 걸려 있는 수정자. Combatant.modifiers 에 쌓이고 engine 이 판정 때 조회한다.
  - SUPPORTED: 엔진이 아는 유형 전체. tools/effect_support.py 가 DB 전체 effect 중 실행 가능 비율을 잰다.
조건 키(on_natural_roll_min / on_miss / if_weather / on_ko / if / duration …)는 공통으로 검사하고,
자연어 조건('if': "...")은 아는 몇 가지만 해석하며 나머지는 '보류'로 로그에 남긴다.
"""
import combat_modifiers as COMBAT_MODS
import heavy_injury_adapter as HEAVY
import temporary_hp as TEMP_HP
import action_lifecycle as ACTION
import frequency as FREQ
import action_points as AP
import action_metadata as ACTION_META
import math
import life as LIFE
import arithmetic_policy as M
import arithmetic as ARITH
import re

STAT_KO = {"공격": "atk", "방어": "def", "특수공격": "spa", "특수방어": "spd", "스피드": "spe", "특공": "spa", "특방": "spd", "명중": "acc", "회피": "eva"}

def weather_effect_active(ctx):
    import weather_state as WEATHER
    return bool(WEATHER.effective_weathers(ctx["engine"], ctx["attacker"]))


KNOWN_IF = {
    "weather effect active": weather_effect_active,
    "super_effective": lambda ctx: ctx.get("multiplier", 1) > 1,
    "hp > half": lambda ctx: ctx["attacker"].hp > ctx["attacker"].base_max_hp / 2,
    "hp <= half": lambda ctx: ctx["attacker"].hp <= ctx["attacker"].base_max_hp / 2,
    "hp <= 1/3": lambda ctx: ctx["attacker"].hp <= ctx["attacker"].base_max_hp / 3,
    "crit": lambda ctx: ctx.get("crit", False),
    "target has damage reduction": lambda ctx: getattr(ctx["target"], "damage_reduction", 0) > 0,
    "target initiative lower and has not acted": lambda ctx: False if ACTION.already_acted_evidence(ctx) else None,
    "target already acted this round": ACTION.already_acted_evidence,
}


def tgt_of(e, attacker, target, ctx=None):
    import effect_contracts as CONTRACTS
    if ctx is not None:
        import native_area_hit_effects as AREA_HIT
        engine=ctx['engine']
        if AREA_HIT.owns(engine,ctx.get('source_id'),e):
            return AREA_HIT.recipients(engine,attacker,target,e,ctx)
        return CONTRACTS.hit_recipients(engine,attacker,target,e,ctx.get('source_id'))
    return CONTRACTS.recipients(attacker,target,e)


def effective_weather(engine, actor=None):
    """Read the existing sourced local field, then the actor's item projection."""
    if actor is None:return getattr(engine,'weather',None)
    import weather_state as WEATHER
    active=WEATHER.effective_state(engine,actor).get('active')
    return active.get('weather') if isinstance(active,dict) else None


def weather_matches(engine, condition, actor=None):
    """Weather alternatives are exact tokens, not substring or first-token matches."""
    import homebrew_weather as HOME
    import weather_state as WEATHER
    current = WEATHER.effective_weathers(engine,actor)
    canonical = getattr(HOME, 'canonical_weather', lambda rules, value: value)
    return bool({canonical(engine.r,w) for w in current} & {canonical(engine.r,w.strip()) for w in condition.split("|")})


def cond_ok(engine, e, ctx):
    """공통 조건 검사. (ok, reason)"""
    nat = ctx.get("nat")
    if e.get("on_miss") and ctx.get("hit", True):
        return False, "on_miss"
    if not e.get("on_miss") and not ctx.get("hit", True):
        return False, "miss"
    if any(key in e for key in ("on_natural_roll_min","on_natural_roll")) and __import__("provocateur").blocked(ctx["attacker"],"no_effect_range"):
        return False, "effect range forbidden"
    if "on_natural_roll_min" in e:
        m = __import__("combat_modifiers").incoming_status_threshold(ctx["target"],e.get("status"),e["on_natural_roll_min"])
        import combat_precision_features as CPF
        effect_face = CPF.effect_natural(engine, ctx["attacker"], ctx.get("move"), nat, actual_damage_type=ctx.get("actual_damage_type"))
        if not isinstance(m, int) or effect_face is None or effect_face < m:
            return False, f"natural<{m}"
    if e.get("on_natural_roll") == "even" and (nat is None or nat % 2):
        return False, "odd"
    if e.get("if_weather") and not weather_matches(engine, e["if_weather"],ctx.get('attacker')):
        return False, "weather"
    if e.get("on_ko") and not ctx.get("ko", False):
        return False, "no_ko"
    if "if_target_status_any" in e:
        statuses=e["if_target_status_any"]
        if not isinstance(statuses,list) or not statuses or any(not isinstance(s,str) or not s.strip() for s in statuses):
            return False, "invalid target status alternatives"
        import status_sets as STATUS_SETS
        if not any(STATUS_SETS.normalize(s) in ctx["target"].conditions for s in statuses):
            return False, "target status"
    cond = e.get("if")
    if isinstance(cond, str):
        if cond in ("user holds no item","user holds nothing"):
            import equipment_protection as PROTECTION
            return (True, "") if PROTECTION.itemless_for_move(engine,ctx["attacker"],ctx.get("move")) else (False,"condition: held item")
        f = KNOWN_IF.get(cond)
        if f is None:
            return False, f"조건 미해석: {cond}"
        result = f(dict(ctx, engine=engine)) if cond == "weather effect active" else f(ctx)
        if result is None:
            return False, f"조건 미해석: {cond}"
        if not result:
            return False, f"조건 불충족: {cond}"
    return True, ""


# ---------- 기술 효과 핸들러 ----------
def apply_stage_changes(engine, source_actor, target, changes, *, source_id, context=None):
    """Apply one effect for one actor, target and source/context identity.

    changes maps selected stage names to the same integer delta. Mixed deltas,
    including raises and losses, are unsupported and rejected before reaction
    consumption or stage mutation. Multi-stat losses share one reaction; this
    does not batch distinct effects or source/context identities.
    """
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError('actual stage effect source identity required')
    if source_actor is None or target is None:
        raise ValueError('actual stage effect source actor and target required')
    if not isinstance(changes, dict) or not changes or any(
            stat not in {'atk', 'def', 'spa', 'spd', 'spe', 'acc', 'eva'}
            or type(delta) is not int for stat, delta in changes.items()):
        raise ValueError('explicit stage names and integer deltas required')
    if len(set(changes.values())) != 1:
        raise ValueError('one stage effect must share its delta across selected stats')
    ctx = dict(context or {})
    if ctx.get('source_id', source_id) != source_id:
        raise ValueError('stage effect and context source identities disagree')
    ctx['source_id'] = source_id
    import dancer as DANCER
    target = DANCER.stage_recipient(engine, source_actor, target, changes, source_id, ctx)
    import hazard_state as HAZARDS
    origin_source_id, source_side = HAZARDS.stage_provenance(engine, source_actor, target, ctx)
    import fashion_items as FASHION
    if any(delta < 0 for delta in changes.values()) and FASHION.blocks_stage_loss(engine, target, source_actor, ctx, source_side=source_side):
        engine.log(f"    {target.name} 전투단계 하락 차단 (아름다운 패션)", "item/아름다운-패션-1")
        return
    for st, delta in changes.items():
        import static_equipment_contracts as STATIC_EQUIPMENT
        if delta < 0 and STATIC_EQUIPMENT.blocks_stage_loss(engine, target, source_actor, ctx, origin_source_id=origin_source_id, source_side=source_side):
            engine.log(f"    {target.name} {st} 단계 하락 차단 (클리어참)", "item/클리어참")
            continue
        if delta < 0 and target is not source_actor and any(__import__('trickster').set_contains(engine,target,'stage_loss_immune',key) for key in (st,'all')):
            engine.log(f"    {target.name} {st} 단계 하락 면역 (특성)", "ability/immune_stage_loss")
            continue
        if st in target.stages:
            engine.change_stage(target, st, delta)
        elif st == "acc":
            import restorative_items as RESTORATIVE
            if RESTORATIVE.blocks_stage_loss(engine, target, delta):continue
            lo, hi = engine.r.mech("combat/combat-stages")["range"]
            import state_grants as GRANTS
            if not GRANTS.adjust_numeric(target, "accuracy_stage", delta):target.accuracy_stage = max(lo, min(hi, target.accuracy_stage + delta))
            engine.log(f"    {target.name} 명중 단계 {delta:+d} → {target.accuracy_stage:+d}", "combat/combat-stages")
        elif st == "eva":
            lo, hi = engine.r.mech("combat/combat-stages")["range"]
            import state_grants as GRANTS
            if not GRANTS.adjust_numeric(target, "evasion_mod", delta):target.evasion_mod = max(lo, min(hi, target.evasion_mod + delta))
            engine.log(f"    {target.name} 회피 보너스 {delta:+d} → {target.evasion_mod:+d}", "combat/combat-stages")


def h_stage_change(engine, a, t, e, ctx):
    if e.get('linked_to'):
        import counter_effects as COUNTERS
        if COUNTERS.linked(a,e['linked_to'],ctx.get('source_id')):return None
    if not isinstance(e.get("delta"), int):
        return "delta 비정수(보류)"
    if not isinstance(e.get("stat"), str) or e.get("stat") not in {"atk", "def", "spa", "spd", "spe", "acc", "eva", "all"}:
        return "스탯 선택/해석 필요: " + str(e.get("stat"))
    targets=tgt_of(e,a,t,ctx)
    changes = dict.fromkeys(
        ["atk", "def", "spa", "spd", "spe"] if e["stat"] == "all" else [e["stat"]], e["delta"])
    for c in targets:
        apply_stage_changes(engine, a, c, changes, source_id=ctx.get('source_id'), context=ctx)
    return None


def h_stat_mod(engine, a, t, e, ctx):
    """기본 스탯/체급 직접 보정 (가드셰어 -5, 바디퍼지 체급 -1, 라이트메탈 체급 -2). multiplier(슬로스타트 x0.5)는 보류."""
    if "multiplier" in e or not isinstance(e.get("value"), int):
        return "stat_mod 배수/비정수(보류)"
    stats = e["stat"] if isinstance(e["stat"], list) else [e["stat"]]
    for c in tgt_of(e, a, t):
        for st in stats:
            if st == "weight_class":
                import state_grants as GRANTS
                source=getattr(c,"_state_registration_source",None) or GRANTS.effect_source(c,ctx,"weight-change")
                if source not in GRANTS.state(c)["sources"]:
                    GRANTS._source(c,source,"effect",owner_id=a.spec.get("id"),lifetime=e.get("duration") or e.get("until") or "legacy_unspecified",rule_id=ctx.get("source_id"))
                GRANTS.weight(c,e["value"],source,mode="add",minimum=int(e.get("min",1)))
                engine.log(f"    {c.name} 체급 {e['value']:+d} → {c.weight_class}")
            elif st in c.stats:
                import state_grants as GRANTS
                source=getattr(c,"_state_registration_source",None) or GRANTS.effect_source(c,ctx,"stat-change")
                if source not in GRANTS.state(c)["sources"]:
                    GRANTS._source(c,source,"effect",owner_id=a.spec.get("id"),lifetime=e.get("duration") or e.get("until") or "legacy_unspecified",rule_id=ctx.get("source_id"))
                GRANTS.stat(c,st,e["value"],source,minimum=1,operation_id=e.get("_state_effect_index",0))
                engine.log(f"    {c.name} {st} 기본 스탯 {e['value']:+d} → {c.stats[st]}")
    return None


def h_apply_status(engine, a, t, e, ctx):
    for c in tgt_of(e, a, t, ctx):
        engine.apply_status(c, e["status"],source=ctx.get("source_id"),applied_by=a,parameters=e.get("parameters"))


def h_apply_status_random(engine, a, t, e, ctx):
    st = engine.rng.choice(e["options"])
    engine.log(f"    무작위 상태 {e['options']} → {st}")
    for c in tgt_of(e, a, t):
        engine.apply_status(c, st)


def h_cure_status(engine, a, t, e, ctx):
    sts = e["status"] if isinstance(e["status"], list) else [e["status"]]
    known = {u["mech"]["data"]["name"] for u in engine.r.units.values()
             if (u.get("mech") or {}).get("schema") == "condition"}
    import linked_move_conditions as LINKED
    if any(s not in known | {"all", "all persistent", "독", "맹독", "기절"}
           and not LINKED.explicit_cure_name(engine.r,s) for s in sts):
        return "상태 선택/해석 필요: " + str(e["status"])
    for c in tgt_of(e, a, t, ctx):
        for s in sts:
            import status_sets as STATUS_SETS
            s=STATUS_SETS.normalize(s)
            import boss_transitions as BOSS
            if BOSS.condition_variant(c,s) in c.conditions:
                engine.cure_status(c, s)
            elif s in ("all persistent", "all"):
                import status_sets as STATUS_SETS
                STATUS_SETS.cure_group(engine,c,'persistent' if s=='all persistent' else None)


def h_cure_all_status(engine, a, t, e, ctx):
    import status_sets as STATUS_SETS
    for c in tgt_of(e, a, t):STATUS_SETS.cure_group(engine,c)


def _amount(expr, who, engine, ctx):
    if isinstance(expr, (int, float)):
        return M.floor(expr)
    s = str(expr)
    if m := re.match(r"tick\*(\d+)", s):
        return engine.tick(who) * int(m.group(1))
    table = {"tick": engine.tick(who), "user.level": ctx["attacker"].level, "current_hp/2": M.ratio(max(0, who.hp),2),
             "max_hp/2": M.ratio(who.base_max_hp,2), "max_hp/4": M.ratio(who.base_max_hp,4), "max_hp/3": M.ratio(who.base_max_hp,3),
             "current_max_hp/2": M.ratio(who.max_hp,2), "-50% max": None}
    if s in table:
        return table[s]
    return evaluate(s, {**ctx, "who": who, "engine": engine})


def h_heal(engine, a, t, e, ctx):
    for c in tgt_of(e, a, t):
        if "fraction_of_max" in e:
            num, den = e["fraction_of_max"]
            engine.heal(c, M.ratio(c.base_max_hp*num,den), source_kind=ctx.get("healing_source_kind","unspecified"))
        elif "amount" in e:
            v = _amount(e["amount"], c, engine, ctx)
            if v is None:
                return f"amount 미해석: {e['amount']}"
            engine.heal(c, v, source_kind=ctx.get("healing_source_kind","unspecified"))


def h_hp_loss(engine, a, t, e, ctx):
    if __import__('hex_maniac').skip_additional_self_cost(engine,a,e,ctx):return
    for c in tgt_of(e, a, t):
        v = _amount(e.get("value"), c, engine, ctx)
        if v is None:
            return f"value 미해석: {e.get('value')}"
        tick_match=re.fullmatch(r'tick(?:\s*\*\s*([0-9]+))?',str(e.get('value')))
        if tick_match:v=engine.tick_loss(c,int(tick_match.group(1) or 1))
        import attack_damage_history as DAMAGE_HISTORY
        if not __import__('coordinator').prevent_effect_loss(engine,a,c,e,ctx):DAMAGE_HISTORY.effect_loss(engine,a,t,c,e,ctx,v)


def h_self_hp_set(engine, a, t, e, ctx):
    v = e.get("self_hp")
    if v == 0:
        engine.lose_hp(a, max(0, a.hp), source="체력 0", unpreventable=e.get("unpreventable") is True, loss_kind="hp_setting")
    elif isinstance(v, str) and "-50%" in v:
        engine.lose_hp(a, a.hp + M.ratio(a.base_max_hp,2), source="체력 -50%", unpreventable=e.get("unpreventable") is True, loss_kind="hp_setting")
    else:
        return f"self_hp 미해석: {v}"


def h_temp_hp(engine, a, t, e, ctx):
    for c in tgt_of(e, a, t):
        v = _amount(e["value"], c, engine, ctx) if not isinstance(e["value"], int) else e["value"]
        if v is None:
            return "temp_hp 미해석"
        TEMP_HP.grant(engine, c, v, round_offset_seconds=ctx.get("round_offset_seconds"))


def h_set_weather(engine, a, t, e, ctx):
    import weather_state as WEATHER
    WEATHER.set_weather(engine,e['weather'],rounds=e.get('rounds',5),source_id=ctx.get('source_id') or 'combat/weather',origin='move',actor=a,policy=e.get('_weather_policy'))


def h_field_effect(engine, a, t, e, ctx):
    import field_effects as FIELD
    FIELD.install(engine, a, e, ctx.get("source_id"))


def h_swap_stages(engine, a, t, e, ctx):
    stats = ["atk", "def", "spa", "spd", "spe"] if e.get("swap_stages") == "all" else e["swap_stages"]
    import combat_stage_sources as STAGES
    if not isinstance(stats,(list,tuple)) or not stats or not set(stats)<=set(STAGES.STATS):raise ValueError("invalid swapped combat stages")
    import csv_item_food_contracts as CSV_FOOD
    CSV_FOOD.assign_stages(engine, ((a, {st: t.stages[st] for st in stats}),
                                   (t, {st: a.stages[st] for st in stats})))
    engine.log(f"    전투단계 교환 {stats}: {a.name} {a.stages} / {t.name} {t.stages}")


def h_swap_stats(engine, a, t, e, ctx):
    import state_fields as STATE_FIELDS
    if e.get("swap") == "initiative":
        before_a, before_t = {"spe": a.stats["spe"]}, {"spe": t.stats["spe"]}
        a.stats["spe"], t.stats["spe"] = t.stats["spe"], a.stats["spe"]
        STATE_FIELDS.record_stat_exchange(a, channels=["spe"], effect=e, before=before_a)
        STATE_FIELDS.record_stat_exchange(t, channels=["spe"], effect=e, before=before_t)
        engine.log(f"    이니셔티브(스피드) 교환: {a.name} {a.stats['spe']} / {t.name} {t.stats['spe']}")
        return None
    who = a if e.get("on") == "self" else t
    channels = list(dict.fromkeys(x for pair in e.get("swap_stats", []) for x in pair))
    before = {key: who.stats[key] for key in channels}
    for x, y in e.get("swap_stats", []):
        who.stats[x], who.stats[y] = who.stats[y], who.stats[x]
    if channels:
        STATE_FIELDS.record_stat_exchange(who, channels=channels, effect=e, before=before)
    engine.log(f"    {who.name} 스탯 교환 {e.get('swap_stats')}")


def h_type_change(engine, a, t, e, ctx):
    c = t if e.get("target") == "target" else a
    if "add_type" in e:mode,value="add",e["add_type"]
    elif "lose_type" in e:mode,value="remove",e["lose_type"]
    elif isinstance(e.get("set_type"), str) and e["set_type"] in ("노말", "격투", "비행", "독", "땅", "바위", "벌레", "고스트", "강철", "불꽃", "물", "풀", "전기", "에스퍼", "얼음", "드래곤", "악", "페어리"):
        mode,value="set",e["set_type"]
    else:return "set_type 규칙형(보류)"
    import homebrew_state as HOME
    if HOME.type_change_blocked(c):return False
    import type_state as TYPES
    TYPES.validate_types(c.r,[value],label="type-changing effect")
    if e.get("fallback") is not None:TYPES.validate_types(c.r,[e["fallback"]],label="type-changing fallback")
    import personal_type_settings as PERSONAL
    personal_loss=PERSONAL.neutral_burn_up(c.r,ctx.get('source_id'),mode,[value])
    fallback=None if personal_loss else e.get('fallback')
    import state_grants as GRANTS
    source=getattr(c,"_state_registration_source",None) or GRANTS.effect_source(c,ctx,"type-change")
    if source not in GRANTS.state(c)["sources"]:
        GRANTS._source(c,source,"effect",owner_id=a.spec.get("id"),lifetime=e.get("duration") or e.get("until") or "legacy_unspecified",rule_id=ctx.get("source_id"))
    if personal_loss:
        GRANTS.state(c)['sources'][source]['personal_type_setting']={
            'source':PERSONAL.NEUTRAL_SOURCE,'identity':PERSONAL.TYPELESS,'fallback':None}
    GRANTS.type_operation(c,mode,[value],source,fallback=fallback)
    import csv_item_capability_contracts as CSV_CAP
    CSV_CAP.sync_essence(engine,c)
    engine.log(f"    {c.name} 타입 → {c.types}")


def h_grant_ability(engine, a, t, e, ctx):
    c = t if e.get("on") == "target" else a
    import static_equipment_contracts as STATIC_EQUIPMENT
    if STATIC_EQUIPMENT.blocks_ability_change(engine,c,a):
        engine.log(f"    {c.name} 특성 변경 차단 (특성가드)", "item/특성가드")
        return None
    name = e.get("grant_ability")
    if not isinstance(name, str) or " " in name:
        return "특성 지정 불명(보류)"
    import state_grants as GRANTS
    source=GRANTS.effect_source(c,ctx,"grant-ability")
    GRANTS.grant(c,"abilities",name,source,"effect",owner_id=a.spec.get("id"),lifetime=e.get("duration") or e.get("until") or "legacy_unspecified",rule_id=ctx.get("source_id"))
    engine.register_abilities_one(c,name)
    engine.log(f"    {c.name} 특성 획득: {name}")


def h_ability_transition(engine, a, t, e, ctx):
    import static_equipment_contracts as STATIC_EQUIPMENT
    if STATIC_EQUIPMENT.blocks_ability_change(engine,t,a):
        engine.log(f"    {t.name} 특성 변경 차단 (특성가드)", "item/특성가드")
        return None
    import ability_transitions as ABILITY_TRANSITIONS
    return ABILITY_TRANSITIONS.apply(engine,a,t,e,ctx)


def h_ability_change(engine, a, t, e, ctx):
    c = t if e.get("on") == "target" else a
    import static_equipment_contracts as STATIC_EQUIPMENT
    if STATIC_EQUIPMENT.blocks_ability_change(engine,c,a):
        engine.log(f"    {c.name} 특성 변경 차단 (특성가드)", "item/특성가드")
        return None
    if "set_ability" in e:
        import state_grants as GRANTS
        source=GRANTS.effect_source(c,ctx,"ability-replacement")
        GRANTS._source(c,source,"effect",owner_id=a.spec.get("id"),lifetime=e.get("duration") or e.get("until") or "legacy_unspecified",rule_id=ctx.get("source_id"))
        GRANTS.overlay(c,source,abilities=[e["set_ability"]])
        GRANTS.reconcile(engine,c)
        engine.log(f"    {c.name} 특성 → {e['set_ability']}")
    else:
        return "복사/교환 규칙(보류)"


def h_suppress_ability(engine, a, t, e, ctx):
    import static_equipment_contracts as STATIC_EQUIPMENT
    if STATIC_EQUIPMENT.blocks_ability_change(engine,t,a):
        engine.log(f"    {t.name} 특성 무효화 차단 (특성가드)", "item/특성가드")
        return None
    t.abilities_suppressed = True
    import items as ITEMS
    ITEMS.synchronize_equipment_suppression(engine,(t,))
    engine.log(f"    {t.name} 특성 무효화")


def h_custom_condition(engine, a, t, e, ctx):
    import custom_condition_effects as CUSTOM
    if CUSTOM.definition(engine.r,ctx.get('source_id')) is not None:
        CUSTOM.grant(engine,a,t,e,ctx['source_id'])
        return
    c = t if e.get("on") in ("target", None) else a
    name = e.get("name", "custom")
    c.custom_conditions[name] = e
    engine.log(f"    {c.name} 고유 상태 '{name}' ({e.get('effect', '')[:40]})")


def h_reaction_shield(engine, a, t, e, ctx):
    import move_defense_reactions as DEFENSE
    DEFENSE.hold_shield(engine,a,e,ctx)
    engine.log(f"    {a.name} 방패 준비: 다음 공격 무효 ({e.get('trigger', '')[:30]})")


def h_next_attack_modifier(engine, a, t, e, ctx):
    import event_effects as EVENTS
    if EVENTS.grant(engine,a,e,ctx.get('source_id')):return
    a.next_attack = e
    engine.log(f"    {a.name} 다음 공격 수정: {e}")


def h_forced_target(engine, a, t, e, ctx):
    engine.taunt = {"by": a, "until": "next turn end"}
    engine.log(f"    도발: 적은 {a.name}을(를) 대상으로 해야 함")


def h_create_terrain(engine, a, t, e, ctx):
    if engine.grid is None:
        return "격자 없음"
    kind = e.get("terrain", "")
    cells = engine.grid.burst(a.pos, 1) if "burst" in str(e.get("cells", "")) or e.get("shape") == "burst 1" else set()
    if not cells:
        return "셀 규칙 미해석"
    store = engine.grid.slow if "slow" in kind else engine.grid.rough if "rough" in kind else engine.grid.blocking if "blocking" in kind else None
    if store is None:
        return f"지형 종류 미해석: {kind}"
    store |= cells
    engine.log(f"    지형 생성 {kind}: {len(cells)}칸")


def h_push(engine, a, t, e, ctx):
    import coat_effects as COATS
    if COATS.blocks_displacement(engine,t) or __import__('type_ace').push_immunity(engine,t,attacker=a,move=ctx.get('move')):return None
    m = e.get("meters")
    if m == "to outside blast range":m=__import__("native_area_hit_effects").push_outside(engine,a,t,e,ctx)
    if not isinstance(m, int):
        m = evaluate(m, {**ctx, "attacker": a, "target": t, "engine": engine})
    if not isinstance(m, int):
        return f"밀기 거리 미해석: {e.get('meters')}"
    if type(m) is not int or m<0:return 'explicit nonnegative forced movement distance required'
    if engine.grid is None:return 'mapped displacement requires an actual grid'
    dx = (t.pos[0] > a.pos[0]) - (t.pos[0] < a.pos[0])
    dy = (t.pos[1] > a.pos[1]) - (t.pos[1] < a.pos[1])
    import forced_movement as FORCED
    if dx==dy==0:return 'forced movement direction is unresolved'
    result=FORCED.displace(engine,a,t,direction=(dx,dy),distance=m,
        source=ctx.get('source_id') or 'effect/push')
    engine.log(f"    {t.name} {result['moved']}m 밀려남 → {t.pos}")



def h_damage_reduction(engine, a, t, e, ctx):
    c = a if e.get("target", "self") == "self" else t
    c.damage_reduction += e["value"]
    engine.log(f"    {c.name} 피해 감소 +{e['value']} ({e.get('duration', '')})")


def h_evasion_mod(engine, a, t, e, ctx):
    for c in tgt_of(e, a, t):
        if isinstance(e.get("value"), int):
            import state_grants as GRANTS
            if not GRANTS.adjust_numeric(c,"evasion_mod",e["value"]):c.evasion_mod = max(-6, min(6, c.evasion_mod + e["value"]))
            engine.log(f"    {c.name} 회피 {e['value']:+d}")
        else:
            return "회피 수치 미해석"


def h_accuracy_mod(engine, a, t, e, ctx):
    for c in tgt_of(e, a, t):
        if isinstance(e.get("value"), int):
            import restorative_items as RESTORATIVE
            if RESTORATIVE.blocks_stage_loss(engine,c,e['value']):continue
            import state_grants as GRANTS
            if not GRANTS.adjust_numeric(c,"accuracy_stage",e["value"]):c.accuracy_stage = max(-6, min(6, c.accuracy_stage + e["value"]))
            engine.log(f"    {c.name} 명중 {e['value']:+d}")


def h_initiative(engine, a, t, e, ctx):
    import blessing_effects as BLESSINGS
    if BLESSINGS.grant(engine,a,e,ctx.get('source_id')):return
    import initiative_derivation as INITIATIVE
    import state_grants as GRANTS
    INITIATIVE.operation(e)
    if ctx.get('source_id'):INITIATIVE.selected(engine.r,ctx['source_id'])
    def apply(staged, actor, target):
        return _initiative_commit(staged, actor, target, e, ctx)
    return GRANTS.transition(engine,a,apply,participants=(t,))


def _initiative_commit(engine, a, t, e, ctx):
    import initiative_derivation as INITIATIVE
    op = INITIATIVE.operation(e)
    c = t if e.get("target", "target") == "target" else a
    if __import__('martial_artist_ability_identities').blocks_zero(c,op):return
    if op['operation'] == 'replace':
        import combat_timing as TIMING
        TIMING.on_initiative_override(c)
        c.initiative_override = e["set_to"]
        if ctx.get('effect_receipt') is not None:
            c.custom_conditions['initiative_fixed'] = dict(operation=op,
                source=INITIATIVE.selected(engine.r,ctx['source_id']),
                receipt=ctx['effect_receipt'],occurrence=ctx['effect_occurrence'])
    elif op['operation'] == 'add':
        import state_grants as GRANTS
        if ctx.get('source_id'):
            source = INITIATIVE.selected(engine.r,ctx['source_id'])
            token = GRANTS.effect_source(c,ctx,"initiative-add")
            GRANTS._source(c,token,"effect",rule_id=source,owner_id=a.entity_id)
            GRANTS.numeric(c,"initiative_bonus",e["delta"],token)
        elif not GRANTS.adjust_numeric(c,"initiative_bonus",e["delta"]):
            c.initiative_bonus += e["delta"]
    else:
        from copy import deepcopy
        row = dict(type='initiative_multiplier',value=deepcopy(op['value']))
        row['_initiative_source'] = INITIATIVE.selected(engine.r,ctx.get('source_id'))
        if ctx.get('effect_receipt') is not None:
            row.update(_initiative_receipt=ctx['effect_receipt'],
                       _initiative_occurrence=ctx['effect_occurrence'])
        c.registry.append(row)
    engine.log(f"    {c.name} 이니셔티브 변경 {e}")


def h_drain(engine, a, t, e, ctx):
    d = ctx.get("dealt", 0)
    if d:
        engine.heal(a, M.product(d,e.get("fraction",0.5)), source_kind=ctx.get("healing_source_kind","unspecified"))


def h_reset_stages(engine, a, t, e, ctx):
    import combat_state_lifecycle as COMBAT_STATE
    if (ctx.get('source_id')=='move/흑안개' and e.get('target')=='all'):
        import weapon_actions as WEAPONS
        if e!={'type':'reset_stages','target':'all',
              '_src':'인카운터에 존재하는 모든 포켓몬과 트레이너의 전투단계를 기본상태로 되돌린다(보통 0).'}:
            raise ValueError('Haze all-target effect changed from its reviewed source')
        recipients=WEAPONS.field_members(engine)
    else:recipients=list(tgt_of(e,a,t))
    for c in recipients:COMBAT_STATE.preflight(c)
    for c in recipients:
        COMBAT_STATE.reset_actor(engine,c)
        engine.log(f"    {c.name} 전투단계·명중·회피 초기화")


def h_noop_static(engine, a, t, e, ctx):
    return None   # 정적 규칙(재능 부여·무기 제한·사용 제한 등)은 전투 중 실행할 것이 없음


def h_declarative_move_contract(engine, a, t, e, ctx):
    import declarative_move_contracts as DECLARATIVE_MOVES
    DECLARATIVE_MOVES.execute(engine,a,t,e,ctx)
    return None


HANDLERS = {
    'roar_retreat': __import__('roar').effect,
    "stage_change": h_stage_change, "apply_status": h_apply_status, "apply_status_random": h_apply_status_random,
    "cure_status": h_cure_status, "cure_all_status": h_cure_all_status, "heal": h_heal, "hp_loss": h_hp_loss, "self_hp_set": h_self_hp_set,
    "temp_hp": h_temp_hp, "set_weather": h_set_weather, "field_effect": h_field_effect, "swap_stages": h_swap_stages, "swap_stats": h_swap_stats,
    "ability_transition": h_ability_transition, "type_change": h_type_change, "grant_ability": h_grant_ability, "ability_change": h_ability_change, "suppress_ability": h_suppress_ability,
    "custom_condition": h_custom_condition, "reaction_shield": h_reaction_shield, "next_attack_modifier": h_next_attack_modifier,
    "forced_target": h_forced_target, "create_terrain": h_create_terrain, "push": h_push, "damage_reduction": h_damage_reduction,
    "evasion_mod": h_evasion_mod, "accuracy_mod": h_accuracy_mod, "stat_mod": h_stat_mod, "initiative": h_initiative, "initiative_multiplier": h_initiative, "drain": h_drain, "reset_stages": h_reset_stages,
    # 정적/판정 시점에 읽는 유형 (실행 시점에는 할 일 없음)
    "never_miss": h_noop_static, "crit_range": h_noop_static, "grant_capability": h_noop_static, "weapon_restriction": h_noop_static,
    "usage_restriction": h_noop_static, "bonus_damage": h_noop_static, "damage_base_formula": h_noop_static, "conditional_damage_base": h_noop_static,
    "skill_check_mod": h_noop_static,
    "oracle_mark": h_noop_static, "channel_imprint": h_noop_static, "damage_formula_override": h_noop_static, "damage_floor": h_noop_static, "damage_roll_mod": h_noop_static,
    "declarative_move_contract": h_declarative_move_contract,
}
# 판정 시점(명중/데미지)에 engine 이 직접 읽는 유형
JUDGEMENT_TYPES = {"never_miss", "crit_range", "bonus_damage", "damage_base_formula", "conditional_damage_base", "damage_formula_override", "damage_floor", "damage_roll_mod"}
# Move-local declarations consumed before post-hit dispatch.  Ability versions
# of these effect kinds still use the persistent passive registry.
MOVE_JUDGEMENT_TYPES = {"ignore_ability", "type_effectiveness_override"}
# 특성 패시브로 Combatant.modifiers 에 올라가는 유형
PASSIVE_TYPES = {"immune_stage_loss", "stat_mod", "damage_roll_mod", "resistance_step", "immunity", "absorb", "evasion_mod", "accuracy_mod", "stat_base_mod", "crit_range", "effect_range_mod",
                 "damage_reduction", "damage_base_mod", "bonus_damage", "initiative_multiplier", "immune_stage_loss", "stage_change", "temp_hp", "grant_capability"}
ENGINE_TYPES = {"zone", "set_up_move", "multi_target_chain"}     # 실행기가 아니라 엔진의 턴 구조(use_move / use_move_on / flatten_effects)가 처리
SUPPORTED = set(HANDLERS) | PASSIVE_TYPES | {"trigger", "reaction", "connection"} | ENGINE_TYPES


def passive_supported(effect):
    if not isinstance(effect, dict) or effect.get('type') not in PASSIVE_TYPES:
        return False
    return effect['type'] != 'effect_range_mod' or COMBAT_MODS.effect_range_supported(effect)


def preflight_effects(engine, attacker, target, effects, src, *, consumer=None):
    """Deterministic source-state checks before a producer pays or observes dice."""
    HEAVY.ensure_clear(engine)
    import combat_stage_sources as STAGES
    for actor in (attacker,target):
        STAGES.validate(actor)
    import effect_contracts as CONTRACTS
    import ability_transitions as ABILITY_TRANSITIONS
    if CONTRACTS.source_id(engine,src)=="move/잠자기" and ABILITY_TRANSITIONS.active(attacker,"ability/불면"):
        raise ValueError("Insomnia prevents using Rest")
    import mindlock as MINDLOCK
    # This exact Move fails against Mindlock before its unresolved positive
    # effect can matter. The native hit gate still records the paid miss.
    if MINDLOCK.move_block(engine,attacker,target,{'id':CONTRACTS.source_id(engine,src)}):return None
    identity=CONTRACTS.require(engine,attacker,target,effects,src,consumer=consumer)
    import move_coins as COINS
    COINS.preflight(engine,attacker,identity)
    import declarative_move_contracts as DECLARATIVE_MOVES
    DECLARATIVE_MOVES.preflight(engine,attacker,target,effects,identity)
    import hazard_state as HAZARDS
    HAZARDS.prepare_effects(engine,attacker,effects,identity)
    import counter_effects as COUNTERS
    COUNTERS.preflight(attacker,effects,identity)
    import weather_state as WEATHER
    for effect in effects:
        if effect.get('type')=='set_weather':
            WEATHER.prepare(engine,effect['weather'],effect.get('rounds',5),identity,'move',actor=attacker,policy=effect.get('_weather_policy'))
        if effect.get('type')=='field_effect':
            import field_effects as FIELD
            FIELD.prepare(engine,effect,identity)
    for effect in getattr(attacker,'registry',[]):
        if effect.get('type')=='never_miss':CONTRACTS.never_miss_allowed(engine,attacker,target,effect,dict(source_id=identity,attacker=attacker,target=target,engine=engine))
    import equipment_actions as EQUIPMENT
    import held_equipment as HELD
    for actor in (attacker,target):HELD.require_resolved(actor)
    if identity not in EQUIPMENT.MOVE_EFFECTS and any(len(HELD.entries(c))>1 for c in (attacker,target)) and any(x.get('type') in ('copy_item','item_restore','swap_items','steal_item','give_item','item_drop') for x in effects):
        raise ValueError('this source needs a reviewed two-held instance selection before action cost')
    if identity=='move/애크러뱃':
        import equipment_protection as PROTECTION
        PROTECTION.itemless_for_move(engine,attacker,engine.r.move(identity))
    if identity in EQUIPMENT.MOVE_EFFECTS:
        substantive=[effect for effect in effects if effect.get('type')!='action_type_change']
        if len(substantive)!=1:raise ValueError('equipment move needs its reviewed source effect')
        EQUIPMENT.require_source(engine,identity,substantive[0])
    if identity=='move/볼가득넣기':
        import food_effects as FOOD
        expected=[{'type':'stage_change','stat':'def','delta':2,'target':'self'},
                  {'type':'consume_buff','buff':'food','ignore_conditions':True}]
        semantic=[{k:v for k,v in effect.items() if k!='_src'} for effect in effects]
        if semantic!=expected:raise ValueError('selected Stuff Cheeks effect profile requires its own policy')
        return FOOD.move_consumption_plan(engine,attacker,identity)
    return None


def run_effects(engine, attacker, target, effects, ctx, src, *, _resume_receipt=None):
    """Dispatch without losing declared controls or confusing false with unknown.

    The tuple-compatible result retains per-occurrence typed outcomes. Source
    preflight belongs before cost; a blocked post-observation continuation does
    not replay or refund the producer that has already happened.
    """
    HEAVY.ensure_clear(engine)
    import common_checks as C
    import effect_contracts as CONTRACTS
    import effect_lifetimes as LIFE
    import clock_invocations as CLOCK
    CLOCK.ensure_clear(engine)
    ctx=dict(ctx);identity=CONTRACTS.source_id(engine,src)
    import move_completion as COMPLETE
    effects=COMPLETE.defer(effects,ctx)
    if _resume_receipt is not None:
        row=engine._effect_dispatch_receipts.get(_resume_receipt)
        if row is None or row['status']!='condition_unknown' or len(effects)!=1:
            raise ValueError('one actual suspended condition occurrence required')
    if not effects:
        return CONTRACTS.BatchResult(0,0)
    if identity=='move/기프트패스':
        preflight_effects(engine,attacker,target,effects,src)
        # This is metadata consumed by TURN before dispatch, not an ongoing
        # actor modifier that changes the cost of unrelated later moves.
        effects=[effect for effect in effects if effect.get('type')!='action_type_change']
    if identity=='move/볼가득넣기':
        buff=preflight_effects(engine,attacker,target,effects,src)
        if buff is None:
            engine.log('    볼가득넣기: 실제 음식 버프가 없어 소비와 방어 상승 없음',identity)
            return CONTRACTS.BatchResult(0,0)
        effects=sorted(effects,key=lambda effect:effect.get('type')!='consume_buff')
        ctx['food_move_source']=identity
    ctx.setdefault('healing_source_kind','ordinary_item' if identity.startswith('item/') else 'move' if identity.startswith('move/') else 'feature' if identity.startswith(('feat/','edge/')) else 'unspecified')
    ctx.update(attacker=attacker,target=target,engine=engine)
    done=held=0;outcomes=[]
    effects=list(effects)
    def halt(index,effect,status,reason,receipt=None,occurrence=None):
        if receipt is None:occurrence,receipt=CONTRACTS.issue_receipt(engine,identity,attacker,target,effect,index)
        CONTRACTS.finish(engine,receipt,status,reason)
        if status=='condition_unknown':
            engine._effect_dispatch_receipts[receipt]['condition_request']={
                'context':CONTRACTS.freeze_context(engine,ctx),
                'profile':CONTRACTS.source_profile(engine,identity),
                'boundary':CONTRACTS.boundary(engine,attacker,target)}
        outcomes.append(CONTRACTS.Outcome(identity,occurrence,status,reason,receipt))
        suffix=CONTRACTS.retain_suffix(engine,receipt,identity,attacker,target,effects[index+1:],ctx)
        if suffix:outcomes.append(suffix)

    replacements={e.get('target','target') for e in effects if isinstance(e,dict) and e.get('type')=='heal' and e.get('replaces') and CONTRACTS.condition(engine,e,ctx).truth is CONTRACTS.ROOT.Truth.TRUE}
    status_limits={x.get('status'):x for x in effects if isinstance(x,dict) and x.get('type')=='limit' and x.get('status')}
    for index,original in enumerate(effects):
        if not isinstance(original,dict) or 'type' not in original:
            held+=1;halt(index,{'type':'_invalid','payload':original},'unsupported_execution','typed effect required');break
        e=dict(original);kind=e['type']
        if identity=='move/볼가득넣기' and kind=='stage_change' and not ctx.get('food_consumption_receipt'):continue
        if kind=='heal' and not e.get('replaces') and e.get('target','target') in replacements:continue
        issue=CONTRACTS.inspect(engine,attacker,target,e,identity,index)
        if issue:
            held+=1;halt(index,e,issue.category,issue);engine.log('    [계약 보류] '+issue.field+': '+issue.detail,identity);break
        predicate=CONTRACTS.condition(engine,e,ctx,source=identity)
        if predicate.truth is not CONTRACTS.ROOT.Truth.TRUE:
            status='condition_false' if predicate.truth is CONTRACTS.ROOT.Truth.FALSE else 'condition_unknown'
            if status=='condition_unknown':
                held+=1;halt(index,e,status,predicate);engine.log('    [조건 미확정] '+predicate.obligation,identity);break
            if _resume_receipt is not None:
                row=engine._effect_dispatch_receipts[_resume_receipt]
                CONTRACTS.validate_receipt(engine,_resume_receipt,identity,row['occurrence'],attacker,target,e)
                CONTRACTS.finish(engine,_resume_receipt,'completed',{'condition':False,'applied':False})
                outcomes.append(CONTRACTS.Outcome(identity,row['occurrence'],'completed',{'condition':False,'applied':False},_resume_receipt))
                done+=1
                continue
            outcomes.append(CONTRACTS.Outcome(identity,'',status,predicate));continue
        if (kind in JUDGEMENT_TYPES|ENGINE_TYPES and not (kind=='damage_roll_mod' and LIFE.declared(e))) or identity.startswith("move/") and kind in MOVE_JUDGEMENT_TYPES:
            outcomes.append(CONTRACTS.Outcome(identity,'','deferred_consumer',kind));continue
        handler=HANDLERS.get(kind)
        if handler is None:
            held+=1;halt(index,e,'unsupported_execution',kind);break
        limit=e.get('limit','')
        if kind=='apply_status' and e.get('status') in status_limits:limit='once_per_scene_per_target'
        # Pounce limits how often the actual target is Slowed this scene,
        # independently of the user. Its existing counter is scene-reset/save-owned.
        target_limit=(identity,kind,e.get('status'),limit)==('move/달려들기','apply_status','둔화','once_per_scene_per_target')
        limit_owner=target if target_limit else attacker
        key=f"lim:{identity}:{kind}:{e.get('status','')}:{target.spec.get('id') if 'target' in limit and not target_limit else ''}"
        if limit and limit_owner.counters.get(key,0)>=1:
            outcomes.append(CONTRACTS.Outcome(identity,'','condition_false','source frequency exhausted'));continue
        if getattr(engine,'rulings',None) is not None and engine.rulings.hooks.get('before_effect'):
            e=engine.rulings.run_hooks('before_effect',e,dict(ctx,src=src),engine)
            if e is None:
                outcomes.append(CONTRACTS.Outcome(identity,'','condition_false','GM cancelled this effect'));continue
            issue=CONTRACTS.inspect(engine,attacker,target,e,identity,index)
            if issue:
                held+=1;halt(index,e,issue.category,issue);break
            predicate=CONTRACTS.condition(engine,e,ctx,source=identity)
            if predicate.truth is not CONTRACTS.ROOT.Truth.TRUE:
                if predicate.truth is CONTRACTS.ROOT.Truth.UNKNOWN:
                    held+=1;halt(index,e,'condition_unknown',predicate);break
                outcomes.append(CONTRACTS.Outcome(identity,'','condition_false',predicate));continue
            handler=HANDLERS.get(e['type'])
            if handler is None:
                held+=1;halt(index,e,'unsupported_execution','GM replacement has no handler');break
        if _resume_receipt is None:
            occurrence,receipt=CONTRACTS.issue_receipt(engine,identity,attacker,target,e,index)
        else:
            receipt=_resume_receipt
            row=engine._effect_dispatch_receipts[receipt]
            if index!=0 or row['status']!='condition_unknown':raise ValueError('actual suspended condition occurrence required')
            occurrence=row['occurrence']
            CONTRACTS.validate_receipt(engine,receipt,identity,occurrence,attacker,target,e)
        ctx.update(source_id=identity,effect_occurrence=occurrence,effect_receipt=receipt)
        native_children=False
        before=set(engine._effect_dispatch_receipts)
        try:
            import blessing_effects as BLESSINGS
            import weather_state as WEATHER
            weather_owner=WEATHER.native_sandstorm_rule_owner(engine,attacker,identity,e)
            if weather_owner is not None:
                # Final post-hook declaration, actual producer and occurrence
                # delegate this exact ongoing rule to the existing turn owner.
                engine.log('    Sandstorm rule consumed by native turn-start weather occurrence '+str(weather_owner['id']),identity)
                note=None
            elif (LIFE.declared(e) and kind != 'repeat_each_turn'
                    and not BLESSINGS.owns_timing(engine.r,e,identity)):
                if kind in ('initiative','initiative_multiplier'):
                    import initiative_derivation as INITIATIVE
                    INITIATIVE.install_temporary(engine,attacker,target,e,identity,receipt,occurrence)
                else:
                    for recipient in tgt_of(e,attacker,target,ctx):LIFE.install(engine,attacker,recipient,e,identity,receipt,occurrence)
                note=None
            else:
                note=handler(engine,attacker,target,e,ctx)
            # A successful handler or lifetime installation may emit native
            # callbacks without returning their batch. Publish those actual
            # receipts once at their common handoff; an existing BatchResult
            # already owns its child edges and keeps its original semantics.
            if note is None:
                children=[CONTRACTS.Outcome(row['source_id'],row['occurrence'],row['status'],row.get('result'),token)
                          for token,row in engine._effect_dispatch_receipts.items() if token not in before]
                if children:
                    completed=sum(child.status=='completed' for child in children)
                    note=CONTRACTS.BatchResult(completed,len(children)-completed,children);note.engine=engine
                    native_children=True
            if kind=="ability_transition" and isinstance(note,dict):status="completed"
            elif native_children:status='completed'
            elif kind=="alternate_effect" and isinstance(note,CONTRACTS.BatchResult):
                pending=note.pending
                status=engine._effect_dispatch_receipts[pending[0].receipt]['status'] if pending else 'completed'
            elif isinstance(note,C.PendingDecision):
                category=getattr(note,'category',None)
                status='awaiting_input' if category=='player_choice' or category is None else 'unresolved_source' if category=='unresolved_source' else 'unsupported_execution'
            elif getattr(note,'tag',None)=='Completed':status='completed'
            else:status='unsupported_execution' if note else 'completed'
        except HEAVY.HeavyPending:
            CONTRACTS.finish(engine,receipt,'awaiting_input');raise
        except Exception as ex:
            note=ex;status='execution_failed'
        CONTRACTS.finish(engine,receipt,status,note)
        # A resumed condition can itself emit a native child. Its actual batch
        # edge is now published, so retain newly reachable source profiles before
        # continuation validation or the final native close examines that graph.
        ACTION.retain_turn_end_children(engine,receipt,set(engine._effect_dispatch_receipts)-before)
        outcomes.append(CONTRACTS.Outcome(identity,occurrence,status,note,receipt))
        if status=='completed':
            done+=1
            if limit:limit_owner.counters[key]=limit_owner.counters.get(key,0)+1
        else:
            held+=1;engine.log('    [효과 '+status+'] '+str(note),identity)
            suffix=CONTRACTS.retain_suffix(engine,receipt,identity,attacker,target,effects[index+1:],ctx)
            if suffix:outcomes.append(suffix)
            break
    result=CONTRACTS.BatchResult(done,held,outcomes);result.engine=engine
    return result


def ensure_clear(engine):
    import effect_contracts as CONTRACTS
    return CONTRACTS.ensure_clear(engine)


def resolve_condition(engine, actor, receipt, *, target_was_asleep, reason):
    """Observe one missing historical fact, then execute its original effect.

    This is not a completion override: the source, boundary and actual effect
    remain fixed, and the normal dispatcher must produce the result.
    """
    import effect_contracts as CONTRACTS
    import state_grants as G
    try:row=engine._effect_dispatch_receipts[receipt]
    except (KeyError,TypeError,AttributeError):raise ValueError('actual dispatcher receipt required')
    if row.get('receipt') is not receipt or row.get('actor') is not actor:
        raise ValueError('actual condition observation owner required')
    if type(target_was_asleep) is not bool or type(reason) is not str or not reason.strip():
        raise ValueError('explicit historical sleep observation and reason required')
    ACTION.validate_turn_end_closures(engine)
    reply={'target_was_asleep':target_was_asleep,'reason':reason}
    if 'condition_reply' in row:
        if row['condition_reply']!=reply:raise ValueError('accepted condition observation cannot change')
        return row['condition_result']
    request=row.get('condition_request')
    if (row.get('status')!='condition_unknown' or type(request) is not dict
            or row['effect'].get('if')!='target was asleep'
            or 'target_was_asleep' in request['context']):
        raise ValueError('this occurrence has no missing historical sleep observation')
    CONTRACTS.validate_condition_request(engine,row)
    if (request['boundary']!=CONTRACTS.boundary(engine,actor,row['target'])
            or request['profile']!=CONTRACTS.source_profile(engine,row['source_id'])):
        raise ValueError('condition observation source or boundary changed')
    def apply(staged, owner):
        actual=staged._effect_dispatch_receipts[receipt]
        ctx=dict(actual['condition_request']['context'],target_was_asleep=target_was_asleep)
        with CONTRACTS.resuming(staged,receipt):
            result=run_effects(staged,owner,actual['target'],[actual['effect']],ctx,actual['source_id'],_resume_receipt=receipt)
            if actual['status'] not in ('completed','awaiting_input'):
                raise ValueError('observation did not resolve the actual consequence')
            actual.update(condition_reply=reply,condition_result={'receipt':receipt,'status':actual['status']})
        if actual['status']=='completed':resume_effects(staged,receipt)
        return actual['condition_result']
    return G.transition(engine,actor,apply,include_rulings=True)


def resume_effects(engine, completed_receipt):
    """Resume only a receipt-bound suffix after its actual predecessor completed."""
    import effect_contracts as CONTRACTS
    rows=getattr(engine,'_effect_dispatch_receipts',{})
    try:preceding=rows[completed_receipt]
    except (KeyError,TypeError):raise ValueError('actual dispatcher receipt required for continuation')
    def finish_nested():
        # A branch already owns its child's real batch. Reuse those receipts to
        # join a completed child suffix back to the original parent, never to
        # issue a new activation or reconstruct a native producer.
        def contains(batch,token,seen):
            if id(batch) in seen:return False
            seen.add(id(batch))
            for outcome in batch.outcomes:
                if outcome.receipt is token:return True
                child=rows.get(outcome.receipt,{}).get('result')
                if isinstance(child,CONTRACTS.BatchResult) and contains(child,token,seen):return True
            return False
        def settled(batch,ancestors=frozenset()):
            # A staged BatchResult can still point at the live engine through
            # its deepcopy contract. Read this invocation's actual registry.
            if id(batch) in ancestors:return False
            ancestors=ancestors|{id(batch)}
            for outcome in batch.outcomes:
                actual=rows.get(outcome.receipt,{})
                child=actual.get('result')
                if isinstance(child,CONTRACTS.BatchResult):
                    if not settled(child,ancestors):return False
                elif actual.get('status',outcome.status) in ('condition_unknown','awaiting_input','unsupported_execution','unresolved_source','execution_failed','deferred_suffix','dispatching'):return False
            return True
        for parent_token,parent in tuple(rows.items()):
            child=parent.get('result')
            if (parent.get('effect',{}).get('type')!='alternate_effect'
                    or parent.get('status') in ('completed','dispatching')
                    or not isinstance(child,CONTRACTS.BatchResult)
                    or not settled(child) or not contains(child,completed_receipt,set())):continue
            CONTRACTS.validate_continuation(engine,parent_token)
            CONTRACTS.finish(engine,parent_token,'completed',child)
            resume_effects(engine,parent_token)
    token=preceding.get('continuation')
    if token is None:
        import move_completion as COMPLETE,confusion_attacks as CONFUSION
        finish_nested()
        CONFUSION.refresh_actions(engine)
        COMPLETE.refresh(engine)
        ACTION.refresh_turn_end(engine)
        import cheerleader as CHEER
        CHEER.refresh_batches(engine)
        return CONTRACTS.BatchResult(0,0)
    row=rows[token]
    if row['resumed']:raise ValueError('effect continuation already resumed')
    if preceding['status']!='completed':raise ValueError('actual preceding effect completion required')
    CONTRACTS.validate_continuation(engine,completed_receipt)
    row['resumed']=True;row['status']='dispatching'
    before=set(rows)
    with CONTRACTS.resuming(engine,completed_receipt):
        result=run_effects(engine,row['actor'],row['target'],row['effects'],row['context'],row['source_id'])
    row['result']=result;row['status']='awaiting_input' if result.pending else 'completed'
    ACTION.retain_turn_end_children(engine,completed_receipt,set(rows)-before)
    finish_nested()
    import move_completion as COMPLETE,confusion_attacks as CONFUSION
    CONFUSION.refresh_actions(engine)
    COMPLETE.refresh(engine)
    ACTION.refresh_turn_end(engine)
    import cheerleader as CHEER
    CHEER.refresh_batches(engine)
    return result


def apply_passives(engine, c, ability_effects):
    """특성 effect 목록을 Combatant.modifiers 로 등록 (전투 시작 시 한 번)."""
    name = next((e.get("_ability") for e in ability_effects if isinstance(e, dict) and e.get("_ability")), "?")
    if __import__('hex_maniac').ability_registration(engine.r,name):return
    if name in ('매복','매복 [Playtest]','ability/매복','ability/매복-playtest'):
        # Ambush is an explicit native Priority activation, never an always-on Flinch.
        return
    if name in ('잔인','ability/잔인'):
        # The extracted optional-purchase list is not an automatic on-hit Slow.
        # Actual damaging hits are offered once by Taskmaster's Cruelty adapter.
        import taskmaster as TASK
        TASK.cruelty_definition(engine.r)
        return
    for e in ability_effects:   # 연결(connection): 특정 기술을 쓸 때 발동 → on_move_use 트리거로 등록 (effect 가 dict 면 실행, 문장이면 로그만)
        if isinstance(e, dict) and e.get("type") == "connection" and e.get("move"):
            import food_effects as FOOD
            if FOOD.honey_thief_connection(engine.r,name,e):continue
            eff = e.get("effect")
            c.ability_triggers.append({"name": name, "spec": {"event": "on_move_use", "move": e["move"]}, "frequency": e.get("frequency") or e.get("_frequency"),
                                       "effects": [dict(eff, target=eff.get("target", "self"))] if isinstance(eff, dict) else [], "note": eff if isinstance(eff, str) else None})
    trig = next((e for e in ability_effects if isinstance(e, dict) and e.get("type") in ("trigger", "reaction")), None)
    if trig is not None:
        spec = parse_trigger(trig.get("text") or trig.get("trigger") or "")
        if spec:
            c.ability_triggers.append({"name": trig.get("_ability", "?"), "spec": spec, "frequency": trig.get("_frequency"),
                                       "effects": [x for x in ability_effects if isinstance(x, dict) and x.get("type") not in ("trigger", "reaction", "connection")]})
        return
    for effect_index, e in enumerate(ability_effects):
        if not isinstance(e, dict):
            continue
        t = e.get("type")
        if not passive_supported(e):
            continue
        if t == "grant_capability" and not any(e.get(k) for k in ("if","duration","while")):
            import state_grants as GRANTS
            values=GRANTS.capability_values(e.get("capability"))
            source=getattr(c,"_state_registration_source",None)
            if source is None:raise ValueError("passive capability needs an owned registration source")
            for value in values:GRANTS.grant(c,"capabilities",value,source,"passive",rule_id=source)
        elif t == "immune_stage_loss":
            c.stage_loss_immune.add(e.get("stat") or "all")
        elif t == "stat_mod":
            h_stat_mod(engine, c, c, dict(e, target="self",_state_effect_index=effect_index), {"attacker": c, "target": c, "hit": True})
        elif t == "stat_base_mod" and isinstance(e.get("value"), int) and e.get("stat") in c.stats:
            import state_grants as GRANTS
            source=getattr(c,"_state_registration_source",None) or GRANTS.effect_source(c,{"source_id":e.get("_ability")},"passive-stat")
            GRANTS.stat(c,e["stat"],e["value"],source,operation_id=effect_index)
        elif t == "stage_change" and e.get("base") and isinstance(e.get("delta"), int):
            c.stages[e["stat"]] += e["delta"]
        elif COMBAT_MODS.passive_field(e) == "evasion_mod":
            c.evasion_mod = max(-6, min(6, c.evasion_mod + e["value"]))
        elif COMBAT_MODS.passive_field(e) == "accuracy_stage":
            c.accuracy_stage = max(-6, min(6, c.accuracy_stage + e["value"]))
        elif t == "damage_reduction" and isinstance(e.get("value"), int) and not any(e.get(k) for k in ("if", "if_weather", "vs", "duration")):
            c.damage_reduction += e["value"]
        elif t == "temp_hp" and e.get("at") == "encounter start":
            v = _amount(e["value"], c, engine, {"attacker": c})
            TEMP_HP.grant(engine, c, v or 0)
        else:
            c.modifiers.append(e)


def passive_status_immunity(engine, actor, condition):
    """Read the existing owned passive records; suppression never rewrites them."""
    if actor.abilities_suppressed:
        return None
    for effect in actor.modifiers:
        source = effect.get("_rule_id")
        if effect.get("type") != "immunity" or not __import__('ability_transitions').effect_active(actor,effect):
            continue
        if not isinstance(source, str) or not source.startswith("ability/"):
            continue
        if __import__('trickster').ignores_defensive(engine,actor,source):continue
        statuses = effect.get("status")
        if statuses == condition or isinstance(statuses, list) and condition in statuses:
            return source
    return None


def passive_damage_mods(engine, attacker, target, move, ctx):
    """패시브 수정자 → (DB 보정, 굴림 보정, 저항 단계, 무효 여부, 흡수 effect)."""
    db_mod = roll_mod = 0
    resist_steps = 0
    immune = None
    absorb = None
    import stellar_tera_blast as STELLAR_TERA
    actual_type=ctx.get('actual_damage_type')
    if actual_type is not None:
        stellar_bonus,stellar_sources=STELLAR_TERA.damage_roll_bonus(engine,attacker,actual_type)
        if stellar_bonus:
            roll_mod += stellar_bonus
            ctx['stellar_radiation_sources']=stellar_sources
    import items as ITEMS
    for e in attacker.modifiers:
        if not ITEMS.passive_effect_allowed(engine,attacker,e):
            continue
        t = e["type"]
        if t == "damage_roll_mod" and e.get('if')=='super_effective' and ctx.get('multiplier',0)>1 and not (attacker.abilities_suppressed and e.get('_ability')):
            import duelist as DUELIST
            roll_mod+=e['value']*(DUELIST.method_multiplier(attacker) if e.get('_rule_id')==DUELIST.EXPLOIT else 1)
        elif t == "damage_roll_mod" and (e.get("move_type") in (None, move["type"])) and e.get("moves") in (None, "STAB") and not e.get("if") and not e.get("vs") and not e.get("while_status") and "if_target_status_any" not in e:
            import homebrew_state as HOME
            if e.get("moves") == "STAB" and move["type"] not in HOME.effect_stab_types(attacker, e):
                continue
            v = e["value"]
            if e.get("if_hp_below_third") and attacker.hp < attacker.base_max_hp / 3:
                v = e["if_hp_below_third"]
            if isinstance(v, int):
                roll_mod += v
        elif t == "damage_base_mod" and isinstance(e.get("value"), int) and (e.get("move_type") in (None, move["type"])) and e.get("moves") in (None, "melee"):
            db_mod += e["value"]
        elif t == "bonus_damage" and isinstance(e.get("value"), int):
            ok, _ = cond_ok(engine, e, ctx)
            if ok and e.get("move_type") in (None, move["type"]) and (not e.get("damaging_only") or move.get("class") in ("물리", "특수")):
                roll_mod += e["value"]
    for e in target.modifiers:
        if not ITEMS.passive_effect_allowed(engine,target,e):
            continue
        t = e["type"]
        if t=='resistance_step' and (target.abilities_suppressed or __import__('chronicler').defensive_ignored(engine,attacker,target)) and e.get('_ability') and str(e.get('_rule_id','')).startswith('ability/'):
            continue
        if e.get("if_weather") and not weather_matches(engine, e["if_weather"],target):
            continue
        if t == "resistance_step" and isinstance(e.get("value"), int):
            if e.get('if')=='already resisted type' and 0<ctx.get('multiplier',0)<1:
                import duelist as DUELIST
                resist_steps+=e['value']*(DUELIST.method_multiplier(target) if e.get('_rule_id')==DUELIST.TOLERANCE else 1)
                continue
            if (e.get("types") and move["type"] in e["types"]) or (e.get("vs") == "physical" and move["class"] == "물리") or (e.get("vs") == "special" and move["class"] == "특수") or (e.get("if") == "hp full" and LIFE.at_full_hp(target)) or (not e.get("types") and not e.get("vs") and not e.get("if")):
                resist_steps += e["value"]
        elif t == "immunity":
            to = e.get("to")
            immune_type = ctx.get('actual_damage_type', move['type']) if e.get('_ability') in ('부유', 'Levitate') else move['type']
            if isinstance(to, str) and immune_type in to or (isinstance(to, list) and any(immune_type in str(x) for x in to)):
                immune = e
        elif t == "absorb" and e.get("move_type") == move["type"]:
            absorb = e
    return db_mod, roll_mod, resist_steps, immune, absorb


# ---------- 식 평가기 ----------
EXPR_VARS = {
    "user.level": lambda c: c["attacker"].level, "target.level": lambda c: c["target"].level,
    "user.weight_class": lambda c: c["attacker"].weight_class,
    "target.weight_class": lambda c: c["target"].weight_class,
    "user.injuries": lambda c: c["attacker"].injuries, "target.injuries": lambda c: c["target"].injuries,
    "user.loyalty": lambda c: __import__("pokemon_entities").effective_loyalty_value(c["attacker"],engine=c.get("engine"), required=True),
    "max_hp": lambda c: c["who"].base_max_hp, "current_hp": lambda c: max(0, c["who"].hp), "tick": lambda c: c["engine"].tick(c["who"]),
    "sum(positive stages of user)": lambda c: sum(v for v in c["attacker"].stages.values() if v > 0),
    "sum(positive stages of target)": lambda c: sum(v for v in c["target"].stages.values() if v > 0),
    "sum(|stages of target|)": lambda c: sum(abs(v) for v in c["target"].stages.values()),
    "lost_hp_percent": lambda c: M.ratio(100*(c["attacker"].base_max_hp-c["attacker"].hp),max(1,c["attacker"].base_max_hp)),
    "user.stockpile": lambda c: c["attacker"].counters.get("stockpile", 0), "last_resort_count": lambda c: c["attacker"].counters.get("last_resort", 0),
    "spe": lambda c: c["attacker"].staged("spe"), "atk": lambda c: c["attacker"].staged("atk"), "spa": lambda c: c["attacker"].staged("spa"),
    "def": lambda c: c["attacker"].staged("def"), "spd": lambda c: c["attacker"].staged("spd"), "db": lambda c: c.get("db", 0),
    "hp lost by user": lambda c: c.get("hp_lost", 0), "damage taken since declaration": lambda c: c.get("damage_taken", 0),
    "direct damage user took this round": lambda c: c.get("damage_taken", 0),
}


def evaluate(expr, ctx):
    """'8 - target.weight_class', 'tick*2', 'db + 2 * sum(positive stages of user)' 같은 식을 정수로. 못 풀면 None."""
    if isinstance(expr, (int, float)):
        return M.floor(expr)
    s = str(expr).strip()
    s = s.replace("floor(lost_hp_percent/10)", "(lost_hp_percent//10)").replace("−", "-").replace("×", "*").replace("x ", "* ")
    c = dict(ctx)
    c.setdefault("who", c.get("target") or c.get("attacker"))
    for name in sorted(EXPR_VARS, key=len, reverse=True):
        if name in s:
            try:
                s = s.replace(name, str(int(EXPR_VARS[name](c))))
            except Exception:
                return None
    s = s.replace("max(0, ", "max(0,")
    if not re.fullmatch(r"[0-9+\-*/(),.% maxin]+", s):
        return None
    try:
        return M.floor(ARITH.evaluate(s,{}))
    except Exception:
        return None


# ---------- 특성 발동조건(트리거) 파서 ----------
TYPES_RE = r"(노말|격투|비행|독|땅|바위|벌레|고스트|강철|불꽃|물|풀|전기|에스퍼|얼음|드래곤|악|페어리)"
TRIGGER_RULES = [
    (re.compile(r"라운드가 시작"), "round_start"),
    (re.compile(r"이니셔티브를 얻을 때|인카운터에 (?:등장|나왔)|필드에 참가"), "enter"),
    (re.compile(r"턴이 시작|턴 시작"), "turn_start"),
    (re.compile(r"턴이 끝|턴 종료|턴이 종료"), "turn_end"),
    (re.compile(r"적(?:이|을|들이) .*?기절|적을 기절|(?:knocks? out|faints? an enemy|KOs?)"), "enemy_faint_by_user"),
    (re.compile(r"(?:자신이|사용자가)?\s*기절했을 때|(?:user|when) faint"), "self_faint"),
    (re.compile(r"중독시켰|(?:화상|마비|잠듦|혼란|얼음)(?:을|에) (?:입혔|걸리게|시켰)"), "on_inflict_status"),
    (re.compile(r"붙잡았을|붙잡기"), "on_grapple"),
    (re.compile(r"몬스터볼로 되돌아가거나|숨돌리기"), "on_recall"),
    (re.compile(r"피해굴림을 굴릴 때|피해 굴림을 굴릴"), "on_damage_roll"),
    (re.compile(r"질주"), "on_charge"),
    (re.compile(r"순간이동"), "on_teleport"),
    (re.compile(r"풀죽었을 때|풀죽음"), "on_flinched"),
    (re.compile(r"(?:근접|물리|특수|변화|공격)?\s*(?:공격|기술|기)(?:으로|로|에|을|를)?\s*(?:맞았|당했|명중당|받았)"), "on_hit_received"),
    (re.compile(r"피해를 (?:받았|입었)|(?:when |after )?(?:user is )?hit by|takes? damage|damaged by|is hit|receives? damage"), "on_hit_received"),
    (re.compile(r"명중시켰|명중했|적중시켰|적중했|명중한|맞혔|피해를 (?:주었|입혔)|(?:user )?hits? (?:a |an |the )?(?:target|foe|enemy|with)|deals? damage|on hit"), "on_hit_dealt"),
    (re.compile(r"기술(?:을|로)?\s*(?:사용했|사용할|쓸)|공격(?:을|기로)?\s*(?:할 때|했을)|(?:user )?uses? (?:a |an |the )?(?:move|attack)|when using"), "on_move_use"),
    (re.compile(r"(?:start|beginning) of (?:user's |its |each |the )?turn"), "turn_start"),
    (re.compile(r"end of (?:user's |its |each |the )?turn"), "turn_end"),
    (re.compile(r"(?:start|beginning) of (?:each |the |a )?round"), "round_start"),
    (re.compile(r"enters? (?:the )?(?:battle|encounter|field)|sent out|switch(?:ed|es)? in"), "enter"),
    (re.compile(r"recalled|takes? a breather"), "on_recall"),
    (re.compile(r"inflicts? (?:a )?(?:status|poison|burn|paralysis|sleep|confus)"), "on_inflict_status"),
]
EN_TYPES = {"normal": "노말", "fighting": "격투", "flying": "비행", "poison": "독", "ground": "땅", "rock": "바위", "bug": "벌레", "ghost": "고스트", "steel": "강철", "fire": "불꽃", "water": "물", "grass": "풀", "electric": "전기", "psychic": "에스퍼", "ice": "얼음", "dragon": "드래곤", "dark": "악", "fairy": "페어리"}


def parse_trigger(text):
    """발동조건 문장 → {"event", "move_type"?, "move_class"?, "keyword"?, "move"?}. 못 풀면 None."""
    if not text:
        return None
    t = text.replace("\n", " ")
    spec = None
    for rx, ev in TRIGGER_RULES:
        if rx.search(t):
            spec = {"event": ev}
            break
    if not spec:
        return None
    m = re.search(TYPES_RE + r"\s*타입", t) or re.search(TYPES_RE + r"[- ]?type", t)
    if m:
        spec["move_type"] = m.group(1)
    else:
        m = re.search(r"\b(" + "|".join(EN_TYPES) + r")[- ]type", t, re.I)
        if m:
            spec["move_type"] = EN_TYPES[m.group(1).lower()]
    if "근접" in t or re.search(r"\bmelee\b", t, re.I):
        spec["melee"] = True
    if "물리" in t or re.search(r"\bphysical\b", t, re.I):
        spec["move_class"] = "물리"
    elif "특수" in t or re.search(r"\bspecial\b", t, re.I):
        spec["move_class"] = "특수"
    elif "변화" in t or re.search(r"\bstatus move\b", t, re.I):
        spec["move_class"] = "변화"
    m = re.search(r"\[([^\]]+)\]\s*키워드|(\S+)\s*키워드", t)
    if m:
        spec["keyword"] = m.group(1) or m.group(2)
    m = re.search(r"(?:기술\s*)?([가-힣A-Za-z]+?)(?:으로|로|를|을)\s*(?:명중|적중|사용)", t)
    if m and m.group(1) not in ("기술", "공격", "공격기", "적을", "대상을", "적", "대상", "피해", "근접공격", "물리공격", "반응", "상대", "사용자가", "사용자를"):
        spec["move"] = m.group(1)
    return spec


def event_matches(spec, ev):
    if spec["event"] != ev.get("event"):
        return False
    mv = ev.get("move")
    if spec.get("move_type") and (not mv or mv.get("type") != spec["move_type"]):
        return False
    if spec.get("move_class") and (not mv or mv.get("class") != spec["move_class"]):
        return False
    if spec.get("melee") and (not mv or "근접" not in str(mv.get("range", ""))):
        return False
    if spec.get("keyword") and (not mv or spec["keyword"] not in str(mv.get("range", "")) + str(mv.get("effect", ""))):
        return False
    if spec.get("move") and (not mv or spec["move"] not in mv.get("name", "")):
        return False
    return True


@__import__("cheerleader").native_action
def fire_event(engine, c, ev, other=None):
    """Combatant 의 특성 중 발동조건이 ev 와 맞는 것의 나머지 effect 를 실행. 빈도(장면 x N / 하루) 는 counters 로 센다."""
    HEAVY.ensure_clear(engine)
    for ab in c.ability_triggers:
        if not event_matches(ab["spec"], ev):
            continue
        if getattr(c,'dead',False):
            continue
        if c.fainted and ab['spec'].get('event')!='self_faint':
            engine.log(f"    {c.name}: 기절 중 기본 특성 발동 불가", "condition/기절")
            continue
        if ab.get("_feat"):
            header = ab.get("activation_header", {"frequency": ab.get("frequency")})
            action, action_problem = ACTION_META.resolve_feature_action(header)
            if action_problem or not ACTION_META.supported_combat_action(action):
                engine.log("    [보류] " + (action_problem or "재주 행동 종류 실행 미지원: " + str(action)), "trainer/action-points")
                continue
        key = ab.get("usage_key") or ("feat/" if ab.get("_feat") else "ability/") + ab["name"]
        freq = ab.get("frequency") or ""
        import equipment_actions as EQUIPMENT
        if key in EQUIPMENT.REACTIONS:
            EQUIPMENT.offer_reaction(engine,c,ev,other,key)
            continue
        if not FREQ.activation_allowed(c, key, freq,engine=engine,action_actor=c if ab.get('_feat') else None):
            continue
        # Trigger admission precedes frequency/AP/action consumption. Unknown
        # source controls cannot consume an activation merely by being logged.
        try:preflight_effects(engine,c,other or c,ab['effects'],key)
        except (ValueError,TypeError) as ex:
            engine.log('    [발동 계약 보류] '+str(ex),key)
            continue
        ap_cost = 0
        budget_before = None
        action_before = None
        if ab.get("_feat"):
            import turn as TURN
            if not TURN.can_act(engine, c):
                continue
            ap_cost = AP.check(engine, c, header, ab.get("cost_effects", ab["effects"]))
            if ap_cost is None:
                continue
            budget_before = dict(c.budget) if getattr(c, "budget", None) is not None else None
            action_before = (c.took_standard, list(getattr(c, "_action_history", [])), getattr(c, "_restricted_action_taken", False), getattr(c, "_standard_action_round", None))
            if not ACTION_META.supported_combat_action(action) or not TURN.spend(engine, c, action, ab["name"], sleep_cure=ACTION.self_cures_sleep(c, other or c, ab["effects"])):
                continue
        if not ab.get("_feat"):
            FREQ.consume_activation(c, key, freq,engine=engine)
        tgt = other or c
        engine.log(f"    특성 {ab['name']} 발동 ({ev['event']})" + (f": {ab['note']}" if ab.get("note") else ""), key)
        ctx = {"attacker": c, "target": tgt, "hit": True, "nat": None, "dealt": ev.get("dealt", 0), "crit": False, "engine": engine}
        if ab.get("_feat"):ctx["healing_source_kind"]="feature"
        import cheerleader as CHEER
        cheer_snapshot=CHEER.support_snapshot(engine,c) if not ab.get("_feat") else None
        result = run_effects(engine, c, tgt, ab["effects"], ctx, key)
        done, held = result
        # A real suspended occurrence has already accepted this activation.
        # Retain its original action/AP/frequency once while its fact is pending.
        accepted = bool(done or any(outcome.status == 'condition_unknown' for outcome in result.outcomes))
        if ab.get("_feat"):
            if accepted:
                AP.spend(c, ap_cost, header, ab.get("cost_effects", ab["effects"]))
                FREQ.consume_activation(c, key, freq,engine=engine,action_actor=c)
            else:
                c.budget = budget_before
                c.took_standard, c._action_history, c._restricted_action_taken, c._standard_action_round = action_before
        if not ab.get("_feat"):
            CHEER.batch_activation(engine,c,key,result,snapshot=cheer_snapshot)
        elif accepted:
            CHEER.batch_activation(engine,c,header.get("id",key),result,orders=True)
        if not ab.get("_feat") or accepted:
            c.counters["ab:" + ab["name"]] = FREQ.state(c)["activations"].get(key, {}).get("used", c.counters.get("ab:" + ab["name"], 0) + 1)
