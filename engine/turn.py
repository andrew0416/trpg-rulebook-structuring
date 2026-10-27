"""
턴 구조 확장: 날씨 효과 · 행동 경제(행동 예산) · 기회 공격 · 이동 방식(공중/부유) · 트레이너 무기.
  - 날씨(combat/weather, A층 수작업 단위): 쾌청 불꽃 +5/물 -5, 비바라기 물 +5/불꽃 -5, 모래바람·싸라기눈은 면역 타입이 아니면 턴 시작에 소량 손실, 5라운드 지속, 얼음 내성 체크 보정.
  - 행동 경제(combat/action-economy): 턴마다 기본 1·이동 1·신속 1·자유 무제한. 기본 행동은 신속/이동으로 낮춰 쓸 수 있다. 우선/방해/반응은 턴 밖.
  - 기회 공격(maneuver/기회-공격): 인접한 적이 (1) 인접 칸 밖으로 이동, (2) 인접하지 않은 대상에게 원거리 공격 → 라운드 1회 방해로 발버둥. 잠듦·풀죽음·마비 상태면 못 한다. 이탈(1칸)·통과·ignore_aoo 이동 규칙은 유발하지 않는다.
  - 무기(ch09 장비/무기): 트레이너의 발버둥을 강화(무기 DB·AC), 무기 기술(weapon_move)은 전투 랭크에 따라.
"""
import heavy_injury_adapter as HEAVY
import re
import action_lifecycle as ACTION
from action_metadata import ActionCost

WEATHER_KO = {"sunny": "쾌청", "rain": "비바라기", "sandstorm": "모래바람", "hail": "싸라기눈", "snow": "싸라기눈"}


# ---------- 날씨 ----------
import resolution_transaction as _FINGERPRINTS

def weather_rule(engine):
    try:
        return engine.r.mech("combat/weather")
    except Exception:
        return None


def weather_damage_mod(engine, attacker, move, target=None):
    import homebrew_weather as HOME_WEATHER
    if HOME_WEATHER.enabled(engine.r):return 0
    import csv_item_physical_contracts as CSV_ITEMS
    import weather_state as WEATHER
    active = WEATHER.effective_state(engine,attacker,include_virtual=False).get('active')
    w = active.get('weather') if isinstance(active,dict) else None
    if target is not None and w in ('rain','sunny') and CSV_ITEMS._active(engine,target,'utility_umbrella'):
        return 0
    rule = weather_rule(engine)
    if not w or not rule or w not in rule["weathers"]:
        return 0
    move_effects = engine.r.move_mech(move["id"])[0].get("effects_exec", [])
    if any(e.get("type") == "ignore_weather_penalty" and e.get("weather") in (w, None) for e in attacker.registry + move_effects):
        return max(0, rule["weathers"][w].get("damage_roll_mod", {}).get(move["type"], 0))
    return rule["weathers"][w].get("damage_roll_mod", {}).get(move["type"], 0)


def weather_turn_start(engine, c, *, _boss_round=False):
    """모래바람·싸라기눈: 면역 타입/특성이 아니면 턴 시작에 소량 손실."""
    import boss_transitions as BOSS
    if BOSS.state(c) is not None and not _boss_round:
        return
    import homebrew_weather as HOME_WEATHER
    if HOME_WEATHER.enabled(engine.r):return
    import weather_state as WEATHER
    __import__('researcher_fields').weather_turn_start(engine,c)
    for w in WEATHER.effective_weathers(engine):
        _weather_turn_start_one(engine,c,w,_boss_round=_boss_round)


def _weather_turn_start_one(engine,c,w,*,_boss_round=False):
    if __import__('study_books').natural_weather_immune(engine,c):return
    if __import__('type_ace')._buff(c,'ace_zephyr'):return
    rule = weather_rule(engine)
    if not w or not rule or w not in rule["weathers"]:
        return
    spec = rule["weathers"][w]
    if not spec.get("tick_damage"):
        return
    if any(t in spec.get("immune_types", []) for t in c.types):
        return
    if WEATHER_KO.get(w, w) in getattr(c, "weather_immune", ()) or w in getattr(c, "weather_immune", ()):
        engine.log(f"    {c.name}: {WEATHER_KO.get(w, w)} 피해 면역 (도구)", "combat/weather")
        return
    if any(e.get("type") == "immunity" and ("weather" in str(e.get("to", "")) or WEATHER_KO.get(w, w) in str(e.get("to", "")) or w in str(e.get("to", "")))
           and ((not e.get('_ability') and not str(e.get('_rule_id','')).startswith('ability/'))
                or __import__('ability_transitions').effect_active(c,e)) for e in c.modifiers + c.registry):
        engine.log(f"    {c.name}: {WEATHER_KO.get(w, w)} 피해 면역 (특성)", "combat/weather")
        return
    if c.fainted or not c.on_field:
        return
    survival = __import__('survivalist_class').weather_hp_immune(engine, c, w)
    if survival:
        engine.log(f"    {c.name}: {WEATHER_KO.get(w, w)} 피해 면역 (생존가)", survival)
        return
    engine.log(f"    {WEATHER_KO.get(w, w)}: {c.name} 소량의 체력 손실", "combat/weather")
    engine.lose_hp(c, engine.tick_loss(c), source=WEATHER_KO.get(w, w),
                   loss_kind="percentage" if _boss_round else "loss")
    __import__('researcher_fields').weather_damaged(engine,c,w)


def weather_round_tick(engine):
    """라운드 시작마다 지속 라운드를 줄이고 끝나면 맑음으로."""
    import weather_state as WEATHER
    if WEATHER.boundary(engine):return
    if not engine.weather:
        return
    if getattr(engine, "weather_rounds", None) is None:
        rule = weather_rule(engine)
        engine.weather_rounds = (rule or {}).get("duration_rounds", 5)
    engine.weather_rounds -= 1
    if engine.weather_rounds <= 0:
        engine.log(f"  날씨 {WEATHER_KO.get(engine.weather, engine.weather)} 종료 → 맑음", "combat/weather")
        engine.weather = None
        engine.weather_rounds = None


def weather_save_mod(engine, cond, actor=None):
    import homebrew_weather as HOME_WEATHER
    if HOME_WEATHER.enabled(engine.r):return 0
    rule = weather_rule(engine)
    import weather_state as WEATHER
    weathers=WEATHER.effective_weathers(engine,actor,include_virtual=False)
    if not rule or not weathers:
        return 0
    effects=engine.r.condition_effects(cond) if cond and engine.r.condition_class(cond) else []
    modifiers=[effect['weather'] for effect in effects if effect.get('type')=='save_modifier' and 'weather' in effect]
    if modifiers:return sum(modifier.get(WEATHER_KO.get(weather,weather),0) for weather in weathers for modifier in modifiers)
    return sum(rule["weathers"].get(weather, {}).get("save_mod", {}).get(cond, 0) for weather in weathers)


# ---------- 행동 경제 ----------
def reset_budget(engine, c):
    rule = engine.r.mech("combat/action-economy")["per_round"]
    import action_resources as RESOURCES
    RESOURCES.reset(engine,c,{"standard":rule["standard"],"shift":rule["shift"],"swift":rule["swift"]})
    import party_actions as PARTY_ACTIONS
    PARTY_ACTIONS.settle_prepaid(engine,c)
    c._diagonal_steps = 0
    c._regular_shift_movement_used = False
    c.aoo_used = False if getattr(c, "_round_marker", None) != engine.round_no else getattr(c, "aoo_used", False)
    c._round_marker = engine.round_no


def can_act(engine, c):
    """Default conscious-actor requirement. Explicit fainted feature exceptions need their own reviewed path."""
    import special_entities as SPECIAL
    SPECIAL.require_prime_independent(engine,c)
    import marsupial_state as MARSUPIAL
    if MARSUPIAL.active(c):return False
    import action_resources as RESOURCES
    if RESOURCES.action_locked(c):return False
    import coup_de_grace as COUP
    if COUP.bound(engine,c):return False
    if c.fainted:
        engine.log(f"  {c.name}: 체력 {c.hp} 의식불명 → 동작 불가", "combat/hit-points")
        return False
    return True


def movement_permission(engine, c, *, equipment_transport=None):
    if not __import__('declarative_move_contracts').defensive_movement_allowed(c):return False
    import equipped_transport_saddle as EQUIPMENT
    if not EQUIPMENT.independent(engine,c):
        body=getattr(c,EQUIPMENT.LINK)
        if body is not equipment_transport or getattr(engine,'_physical_objects',{}).get(body.get('id')) is not body or not EQUIPMENT.is_body(body):return False
    import body_modes as BODY_MODES
    if not BODY_MODES.movement_permission(c):return False
    import setup_move_state as SETUP_MOVE
    if not SETUP_MOVE.movement_permission(engine,c):
        engine.log(f"    {c.name}: 준비 중인 기술의 이동 단계만 사용할 수 있음",
                   "setup_move_state/movement")
        return False
    import grapple_state as GRAPPLE
    if not GRAPPLE.movement_permission(engine,c):return False
    for status in c.conditions:
        if __import__('blessing_effects').ignored(c,status):continue
        effects = engine.r.condition_effects(status)
        if any(e.get("type") in ("no_shift_movement", "must_stand_up") for e in effects):
            engine.log(f"    {c.name}: {status} 상태로 현재 이동할 수 없음", "condition/" + status)
            return False
    return True


def disengage(engine, c, destination, *, movement_mode=None, _telepathy_source=None, _trickster_escape=False):
    """ch07 Disengage: one Shift, one metre, no opportunity attack.

    The existing grid and action ledger carry the actual move. This grants no
    additional movement action and does not issue an attack/reaction token.
    """
    import passive_events as PASSIVE_EVENTS
    import league_runtime as LEAGUE
    import effects_ext as EXT
    from grid import cheb
    PASSIVE_EVENTS.ensure_clear(engine)
    LEAGUE.check_boundary(engine, "disengage")
    HEAVY.ensure_clear(engine)
    engine.r._selected_rule("maneuver/이탈")
    if "혼란" in c.conditions and __import__("provocateur").blocked(c,"confusion_opportunities"):
        raise ValueError("Fiddle forbids Disengage while Confused")
    if not isinstance(destination, (list, tuple)) or len(destination) != 2 or any(type(v) is not int for v in destination):
        raise ValueError("Disengage destination needs two integer grid coordinates")
    destination = tuple(destination)
    if engine.grid is None:
        raise ValueError("Disengage needs an explicit mapped destination")
    if cheb(c.pos, destination) != 1:
        raise ValueError("ordinary Disengage moves exactly one metre")
    if not engine.grid.inside(destination) or destination in engine.occupied(c):
        raise ValueError("Disengage destination is blocked or occupied")
    import body_state as BODY
    if not BODY.can_place(engine, c, destination, origin=c.pos):
        raise ValueError("Disengage destination body is blocked or outside its movement region")
    distance, mode = engine.move_profile(c, movement_mode=movement_mode)
    import movement_actions as MOVEMENT
    if not MOVEMENT.free_float_destination(engine,c,destination,movement_mode or mode):
        raise ValueError('Free Floating destination requires observed zero gravity')
    if movement_mode == "teleport":
        raise ValueError("Teleport has its own movement conditions")
    if distance <= 0:
        raise ValueError("no usable movement capability")
    diagonal = c.pos[0] != destination[0] and c.pos[1] != destination[1]
    parity = getattr(c, "_diagonal_steps", 0) % 2
    cost = (2 if diagonal and parity else 1) + MOVEMENT.slow_terrain_penalty(engine,c,destination,'land' if mode=='육상' else movement_mode or 'sky')
    if cost > 1:
        raise ValueError("selected Disengage step exceeds its one-metre movement allowance")
    import stat_ace as STAT
    swift=STAT.has(engine,c,STAT.MASTERY,'spe') or __import__('skirmisher').nimble(engine,c)
    if swift and not movement_permission(engine,c):return False
    if _trickster_escape:
        proof=getattr(engine,'_trickster_escape',None)
        if not proof or proof['pokemon'] is not c or proof['source']!=__import__('trickster').ESCAPE:raise ValueError('actual Escape Artist Free Disengage boundary required')
        if not movement_permission(engine,c):return False
        __import__('action_lifecycle').triggered_free_action(engine,c,__import__('trickster').ESCAPE)
    elif _telepathy_source is not None:
        proof=getattr(engine,'_telepath_disengage_boundary',None)
        if not proof or proof['actor_id']!=c.entity_id or proof['source']!=_telepathy_source or _telepathy_source!=__import__('telepath').FEB or engine._move_completions[proof['completion']]['phase']=='complete':raise ValueError('actual Telepathy Free Disengage boundary required')
        if not movement_permission(engine,c):return False
        __import__('action_lifecycle').triggered_free_action(engine,c,_telepathy_source)
    elif not getattr(c, "on_field", True) or c.captured or not spend(engine, c, "swift" if swift else "shift", "이탈", movement=not swift):return False
    import type_ace as TA
    TA.mark_departure(engine,c,destination)
    import field_effects as FIELD
    origin=c.pos;origin_altitude=c.spec.get('_movement_altitude',0);origin_contact=FIELD.touches_ground(c)
    c.pos = destination
    import living_weapon as LIVING
    LIVING.sync(engine,c)
    c.airborne = mode == "공중/부유"
    if diagonal:
        c._diagonal_steps = getattr(c, "_diagonal_steps", 0) + 1
    __import__('ability_exchange_contracts').refresh(engine)
    __import__('ability_control_contracts').refresh(engine)
    EXT.on_enter_cell(engine, c, destination,previous_position=origin if origin_altitude==c.spec.get('_movement_altitude',0) and origin_contact==FIELD.touches_ground(c) else None)
    engine.log(f"    {c.name}: 이탈 1m → {destination} (기회공격 유발 없음)", "maneuver/이탈")
    return True


def spend(engine, c, kind, what="", *, movement=False, sleep_cure=False, _native_move=None, _standing_up=False, _condition_recovery=None, _body_mode_return=False, _assisted_breather=None):
    """행동 소비. 기본 행동이 없으면 신속/이동으로 낮출 수 없고(상위→하위만 가능), 신속이 없으면 기본 행동을 낮춰 쓴다. 성공 여부 반환."""
    from arithmetic_policy import validate_source
    validate_source(engine.r)
    import initiative_interrupts as INTERRUPTS
    INTERRUPTS.require_move_cost(engine,c,kind,_native_move,movement=movement)
    HEAVY.ensure_clear(engine)
    import type_ace as TA
    if not TA.action_permission(engine,c,kind,_native_move,what):return False
    import boss_transitions as BOSS
    if not BOSS.action_permission(c):
        engine.log(f"    {c.name}: 이 보스 행동 슬롯은 상실됨", "C11-127/C11-133")
        return False
    import breather_assistance as ASSISTANCE
    assisted=ASSISTANCE.permission(engine,c,kind,_assisted_breather)
    if type(kind) is ActionCost:
        return spend_compound(engine, c, kind, what, movement=movement, sleep_cure=sleep_cure)
    if type(movement) is not bool or (movement and kind != "shift"):
        raise ValueError("movement purpose requires a shift action and a boolean flag")
    if not can_act(engine, c):
        return False
    if kind == "shift":
        import grapple_state as GRAPPLE
        if not GRAPPLE.movement_permission(engine, c):return False
    if movement:
        import vision_impairment as VISION
        if VISION.accuracy_level(engine,c)=='total' and getattr(engine,'_relative_mover',None)!=c.entity_id:
            raise ValueError('Total Blindness Shift movement requires its relative declaration')
    if movement and not movement_permission(engine, c):
        return False
    if __import__('capture_specialist').shift_grant(engine,c,kind,movement=movement):return True
    if not ACTION.ordinary_permission(engine, c):
        return False
    import order_actions as ORDERS
    kind=ORDERS.pay(engine,c,what,kind)
    status_allowed=ACTION.status_permission(engine, c, kind, sleep_cure=sleep_cure,
        _standing_up=_standing_up, _condition_recovery=_condition_recovery,_native_move=_native_move)
    if not status_allowed:
        return False
    b = getattr(c, "budget", None)
    import combat_maneuvers as MANEUVERS
    import body_modes as BODY_MODES
    if not BODY_MODES.permits(c,kind,returning=_body_mode_return):return False
    if not assisted and not MANEUVERS.standard_allowed(c,kind,_native_move,engine=engine):
        engine.log(f"    {c.name}: 재담 난동 중 기본 행동은 데미지 공격에 사용", "maneuver/술수")
        return False
    import wild_equipment as WILD
    if WILD.pending(c):
        if kind=="standard" and (b is None or b.get("standard",0)>0):
            if WILD.replace_standard(engine,c):return False
        elif kind=="full" or (kind in ("shift","swift") and b is not None and b.get(kind,0)<=0 and b.get("standard",0)>0):
            raise ValueError("bait distraction with Full or downgraded Standard needs an explicit composition policy")
    import swarm_transitions as SWARM
    swarm_spend=SWARM.spend(engine,c,kind,_native_move)
    if swarm_spend is not None:
        if swarm_spend:ACTION.record_action(engine,c,kind)
        return swarm_spend
    if not engine.encounter_active:
        # Ended encounters may leave a budget record; it does not constrain a
        # later outside action once the normal permissions above pass.
        ACTION.record_action(engine, c, kind)
        return True
    if b is None:          # Outside-encounter component execution only.
        ACTION.record_action(engine, c, kind)
        return True
    if kind == "full":
        if b.get("standard", 0) > 0 and b.get("shift", 0) > 0:
            if assisted:ASSISTANCE.consume(engine,_assisted_breather)
            b["standard"] -= 1
            b["shift"] -= 1
            ACTION.record_action(engine, c, kind)
            return True
        engine.log(f"    {c.name}: 완전 행동에는 기본·이동 행동 모두 필요 → {what} 불가", "combat/action-economy")
        return False
    if kind == "free":
        ACTION.record_action(engine, c, kind)
        return True
    if __import__('trickster').extra_standard(engine,c,kind,_native_move):return True
    if b.get(kind, 0) > 0:
        b[kind] -= 1
        if movement:c._regular_shift_movement_used = True
        ACTION.record_action(engine, c, kind)
        return True
    if kind in ("swift", "shift") and b.get("standard", 0) > 0:      # 기본 행동을 낮춰서 사용 (downgrade)
        # ch07:50 and :79 (PTU pp227-228): distinguish movement from
        # activating a Shift-cost effect. Pokemon cannot use the downgrade to
        # move; a Trainer cannot repeat movement after the regular Shift moved.
        if movement and (c.kind != "trainer" or getattr(c, "_regular_shift_movement_used", False)):
            reason = "포켓몬의 기본 행동 전환은 이동에 사용 불가" if c.kind == "pokemon" else "이미 정규 이동 행동으로 이동함" if c.kind == "trainer" else "행위자 종류의 이동 전환 권한 미해석"
            engine.log(f"    {c.name}: {reason} → {what} 불가", "combat/action-economy")
            return False
        b["standard"] -= 1
        ACTION.record_action(engine, c, kind)
        engine.log(f"    {c.name}: 기본 행동을 {'신속' if kind == 'swift' else '이동'} 행동으로 낮춰 사용 ({what})", "combat/action-economy")
        return True
    engine.log(f"    {c.name}: {'기본' if kind == 'standard' else '이동' if kind == 'shift' else '신속'} 행동이 남지 않음 → {what} 불가", "combat/action-economy")
    return False


def spend_compound(engine, c, cost, what="", *, movement=False, sleep_cure=False):
    """Plan every resource before committing one compound activation record.

    Components are declared costs. A Standard token funding a Shift/Swift is
    not an extra declared Standard action. Full is not routed through this API.
    """
    import initiative_interrupts as INTERRUPTS
    INTERRUPTS.require_move_cost(engine,c,cost,None,movement=movement)
    HEAVY.ensure_clear(engine)
    if type(cost) is not ActionCost:
        raise ValueError("typed compound action cost required")
    if type(movement) is not bool or movement:
        raise ValueError("compound movement purpose is not implemented")
    if not can_act(engine, c) or not ACTION.ordinary_permission(engine, c):
        return False
    if "shift" in cost.components:
        import grapple_state as GRAPPLE
        if not GRAPPLE.movement_permission(engine, c):return False
    if not ACTION.status_permission(engine, c, cost, sleep_cure=sleep_cure):
        return False
    import combat_maneuvers as MANEUVERS
    if MANEUVERS.force_attack(c) and "standard" in cost.components:
        raise ValueError("Bon Mot with compound Standard needs its damaging attack producer")
    import body_modes as BODY_MODES
    if 'standard' in cost.components and not BODY_MODES.permits(c,'standard'):return False
    if "standard" in cost.components and c.injuries >= 5 and engine.encounter_active and not __import__('taskmaster').ignores_acting_loss(c):
        # Existing reviewed Standard consequence is only native use_move.
        # Feature activation cannot silently inherit that confluence proof.
        engine.log(f"    {c.name}: 복합 재주 Standard 중상 적용 시점 미확정 → 보류", "common/heavy-injury")
        return False
    budget = getattr(c, "budget", None)
    planned = None if budget is None else dict(budget)
    if planned is not None:
        import action_resources as RESOURCES
        planned=RESOURCES.plan_cost(budget,cost.components)
        if planned is None:
            engine.log(c.name+': 복합 행동 예산이 남지 않음 (insufficient compound action budget)','combat/action-economy')
            return False
        import wild_equipment as WILD
        if WILD.pending(c) and ("standard" in cost.components or planned.get("standard",0)<budget.get("standard",0)):
            raise ValueError("bait distraction with compound Standard needs an explicit composition policy")
        if planned.get('standard',0)<budget.get('standard',0) and not BODY_MODES.permits(c,'standard'):return False
        budget.update(planned)
    elif "standard" in cost.components:
        import wild_equipment as WILD
        if WILD.pending(c):raise ValueError("bait distraction with compound Standard needs an explicit composition policy")
    ACTION.record_action(engine, c, cost)
    return True


def action_kind_of_move(engine, c, move, mm):
    if __import__('enduring_soul').move_scope(engine,c):return 'standard'
    if __import__('trickster').impromptu_scope(engine,c,move):return 'free'
    if __import__('trickster').sleight_scope(engine,c,move):return 'standard'
    if move['id']==__import__('tumbler').SPLASH:return 'shift'
    if __import__('provocateur').quick_scope(engine,c,move):return 'swift'
    """기술의 행동 종류: 레지스트리의 action_type_change / 헤더 키워드 / 기본값 standard."""
    ace=__import__('type_ace').scope(engine,c,move)
    if ace and ace.get('pokemon_action'):return ace['pokemon_action']
    for e in mm.get("effects_exec", []) + c.registry:
        if e.get("type") == "action_type_change" and (not e.get("moves") or move["name"] in str(e.get("moves")) or move["type"] in str(e.get("moves"))):
            to = str(e.get("to", "standard"))
            import effects as FX
            if e.get("if_weather") and not FX.weather_matches(engine,e["if_weather"],c):
                continue
            return {"swift": "swift", "free": "free", "shift": "shift"}.get(to, "standard")
    rng = str(move.get("range", ""))
    if "완전 행동" in rng or "완전행동" in rng:
        return "full"
    if "자유 행동" in rng:
        return "free"
    if "신속 행동" in rng or "신속" in rng:
        return "swift"
    return "standard"


def has_priority(engine, c, move):
    kws = set(engine.r.moves_mech.get(move["id"], {}).get("header", {}).get("keywords") or []) | set(move.get("keywords") or [])
    if "우선" in kws or "우선" in str(move.get("range", "")):
        __import__('skirmisher').require_keyword(c,'priority')
        return True
    try:
        import effects_ext as EXT
        priority = "우선" in EXT.keywords_for(c, move)
    except Exception:
        return False
    if priority:__import__('skirmisher').require_keyword(c,'priority')
    return priority


# ---------- 기회 공격 ----------
def can_aoo(engine, c):
    import effect_lifetimes as LIFETIMES
    import action_resources as RESOURCES
    if RESOURCES.action_locked(c):return False
    import coup_de_grace as COUP
    if COUP.bound(engine,c):return False
    # Hunter's Reflexes raises the single per-round Attack of Opportunity to three for the Hunter and their Pokemon.
    return c.on_field and not c.fainted and not c.captured and not __import__("hunter").opportunity_exhausted(engine, c) and not (__import__('blessing_effects').effective_conditions(c) & {"잠듦", "풀죽음", "마비", "넘어짐"}) and __import__('confusion_attacks').permits_opportunity(engine,c) and not LIFETIMES.forbids(c,"attack_of_opportunity")


def adjacent_enemies(engine, c):
    side = getattr(c, "side", None)
    if side is None:
        return []
    return [x for x in (engine.everyone or []) if x is not c and getattr(x, "side", None) is not None and x.side != side and x.on_field and not x.fainted and not x.captured and engine.adjacent(x,c)]


def trigger_aoo(engine, mover, why, enemies=None):
    import trickster as T,state_grants as G
    candidates=enemies if enemies is not None else adjacent_enemies(engine,mover)
    if not getattr(engine,'_trickster_aoo_transaction',False) and any(T.owner(engine,p,tech=T.IMPROMPTU) for p in candidates):
        def apply(staged,subject,*actual):
            staged._trickster_aoo_transaction=True
            try:return _trigger_aoo(staged,subject,why,list(actual))
            finally:del staged._trickster_aoo_transaction
        return G.transition(engine,mover,apply,participants=tuple(candidates),include_rulings=True,include_grid=engine.grid is not None)
    return _trigger_aoo(engine,mover,why,enemies)


def _trigger_aoo(engine, mover, why, enemies=None):
    if __import__('trickster').prevents_aoo(engine,mover):return
    if __import__('commander').no_opportunity(engine, mover):
        return
    """이동/원거리 공격으로 기회 공격 조건이 걸린 (이동 전) 인접 적들이 발버둥으로 방해 공격."""
    if engine.grid is None:
        import mapless_space as MAPLESS
        if not MAPLESS.active(engine):return
    if any(e.get("type") == "movement_rule" and (e.get("ignore_aoo") or e.get("no_aoo")) for e in mover.registry):
        return
    if __import__("tumbler").immune(mover) or why=="인접 칸 밖으로 이동" and __import__("tumbler").run_away(mover):return
    enemies = enemies if enemies is not None else adjacent_enemies(engine, mover)
    import fashion_items as FASHION
    if FASHION.prevents_opportunity(engine,mover,why,enemies):
        return
    for enemy in enemies:
        if __import__('warper').prevents_aoo(enemy,mover,why):continue
        if not can_aoo(engine, enemy):
            continue
        enemy.aoo_used = True
        enemy._round_marker = engine.round_no
        __import__("hunter").note_opportunity(engine, enemy)
        previous=getattr(engine,'_opportunity_attack',None)
        engine._opportunity_attack={'attacker_id':enemy.entity_id,'target_id':mover.entity_id,'source':'maneuver/기회-공격'}
        try:
            if __import__('trickster').impromptu(engine,enemy,mover,why):continue
        finally:
            if previous is None:del engine._opportunity_attack
            else:engine._opportunity_attack=previous
        engine.log(f"  [기회 공격] {enemy.name} → {mover.name} ({why}): 방해로 발버둥", "maneuver/기회-공격")
        with ACTION.move_grant(engine, enemy, mover, "struggle", source="maneuver/기회-공격", kind="free") as grant:
            # An armed Athlete Coaching answers the Pokemon's actual Attack of Opportunity with an automatic hit.
            # The Hunter scope records this actual Attack of Opportunity hit for Don't Look Away.
            # The grant is consumed before accuracy; keep the opportunity-attack pair readable by evasion consumers.
            previous = getattr(engine, "_opportunity_attack", None)
            engine._opportunity_attack = {"attacker_id": enemy.entity_id, "target_id": mover.entity_id, "source": "maneuver/기회-공격"}
            try:
                __import__("hunter").opportunity(engine,enemy,mover,lambda:__import__("athlete").opportunity(engine,enemy,mover,lambda:__import__('martial_artist').opportunity(engine,enemy,mover,lambda:__import__("type_ace").aoo(engine,enemy,mover,grant))))
            finally:
                if previous is None:
                    del engine._opportunity_attack
                else:
                    engine._opportunity_attack = previous


# ---------- 트레이너 무기 ----------
WEAPON_KIND = {   # ch09 장비/무기: 소형 근접 DB+1 / 대형 근접 AC+1 DB+2 (양손) / 단거리 사격 4m / 장거리 사격 12m AC+1 DB+1 (4m 이내 공격 불가)
    "소형 근접무기": {"range": "근접, 대상 1", "db": 1, "ac": 0}, "대형 근접무기": {"range": "근접, 대상 1", "db": 2, "ac": 1},
    "단거리 사격무기": {"range": "4, 대상 1", "db": 0, "ac": 0}, "장거리 사격무기": {"range": "12, 대상 1", "db": 1, "ac": 1, "min_range": 5},
    "발 무기": {"range": "근접, 대상 1", "db": 1, "ac": 1}}


def equip_weapon(engine, c, weapon):
    """Publish physical equipment and its generated rule identity atomically."""
    import state_grants as GRANTS
    return GRANTS.transition(engine,c,lambda staged,actor:_equip_weapon(staged,actor,weapon))


def _equip_weapon(engine, c, weapon):
    """Record physical slots and move grants separately from independently learned moves."""
    import copy
    import skill_modifiers as SKILL
    import weapon_actions as WEAPONS
    import hashlib, json
    if c.kind not in ("trainer","pokemon"):
        raise ValueError("ordinary weapon equipment requires a trainer or Wielder Pokemon")
    source = "ch09-equipment/장비/무기"
    if engine.r._selected_rule(source) != source:
        raise ValueError("selected weapon variant requires its own equipment policy")
    weapon = copy.deepcopy(weapon)
    if not isinstance(weapon, dict) or not isinstance(weapon.get("name"), str) or not weapon["name"].strip():
        raise ValueError("weapon needs its physical identity/name")
    aliases = {"대형 근접 무기":"대형 근접무기", "근거리 사격무기":"단거리 사격무기", "원거리 사격무기":"장거리 사격무기", "발무기":"발 무기"}
    weapon["kind"] = aliases.get(weapon.get("kind"), weapon.get("kind"))
    if weapon["kind"] not in WEAPON_KIND or weapon.get("grade", "간단") not in ("조잡", "간단", "좋음"):
        raise ValueError("unsupported ordinary weapon kind/grade")
    import wielder_capability as WIELDER
    import living_weapon as LIVING
    living=LIVING.require_weapon(engine,c,weapon)
    if not living:WIELDER.require_weapon(engine,c,weapon)
    held=None
    if c.kind=='pokemon' and not living:
        import held_equipment as HELD
        held=HELD.prepare(c,weapon['name'],None,weapon['instance_id'])
        if any(x.get('instance_id')==weapon['instance_id'] for x in HELD.entries(c)):
            raise ValueError('external weapon already occupies a held slot')
    foot_weapon = weapon["kind"] == "발 무기"
    slot = weapon.get("slot", "발" if foot_weapon else "주요손").replace(" ", "")
    if foot_weapon:
        if slot != "발":
            raise ValueError("foot weapon requires the feet slot")
        weapon["slot"] = slot
    elif slot not in ("주요손", "반대손"):
        raise ValueError("ordinary hand weapon requires main/off hand")
    two_handed = weapon["kind"] in ("대형 근접무기", "장거리 사격무기")
    if two_handed and slot != "주요손":
        raise ValueError("two-handed weapon occupies both hands")
    slots = ["주요손", "반대손"] if two_handed else [slot]
    ledger = c.custom_conditions.get("equipped_weapons", {})
    occupied = {s for entry in ledger.values() for s in entry["slots"]}
    occupied.update(s for entry in getattr(c,"_item_reg",{}).values() for s in entry.get("slots",[]))
    if occupied.intersection(slots):
        raise ValueError("weapon hand slot already occupied")
    kind = WEAPON_KIND[weapon["kind"]]
    mid,generated_move,generated_mechanics = WEAPONS.derived_definition(engine.r,weapon)
    if any(mid == entry["struggle_id"] for entry in ledger.values()):
        raise ValueError("weapon already equipped")
    import optional_weapon_framework as FRAMEWORK
    rank = FRAMEWORK.skill_rank(engine,c,weapon)
    grade = weapon.get("grade", "간단")
    # Only the off-hand slot loses the Master grant; feet keep the grade/rank rule.
    allowed = 0 if grade == "조잡" or rank < 4 else 2 if grade == "좋음" and rank >= 6 and slot != "반대손" else 1
    framework_limit = FRAMEWORK.move_limit(engine,c,weapon)
    if framework_limit is not None:allowed=framework_limit
    if c.kind=='pokemon':allowed=min(allowed,1)
    supplied = weapon.get("moves", [])
    if not isinstance(supplied, list) or any(not isinstance(v,str) for v in supplied):
        raise ValueError("weapon moves must be an explicit list")
    available = []
    for name in supplied[:allowed]:
        wid = name if name in engine.r.moves else next((k for k,v in engine.r.moves.items() if v["name"].rstrip("!") == name.rstrip("!")),None)
        if wid is None:
            raise ValueError("unknown selected weapon move")
        if framework_limit is None:WEAPONS.validate_grant(engine,c,weapon,wid)
        available.append(wid)
    __import__('ruleset').capture_runtime_weapon(engine.r,mid,weapon['name']+' 발버둥')
    engine.r.moves[mid] = generated_move
    engine.r.moves_mech[mid] = generated_mechanics
    engine.r._runtime_weapon_declarations[mid] = copy.deepcopy(weapon)
    # The actual producer admits its derived source before publishing the grant.
    # A later read, including a failed staged attack, must not change Rules.
    __import__('ruleset').require_runtime_weapon(engine.r,mid)
    baseline = set(c.moves)
    prior_granted = {m for entry in ledger.values() for m in entry["available_moves"]}
    independent = set(c.spec.get("moves",[])) | set(c.custom_conditions.get("independently_acquired_moves",[]))
    independent.update(m for entry in ledger.values() for m in entry.get("independently_known",[]))
    independently_known = [m for m in [mid,*available] if m in baseline and (m not in prior_granted or m in independent)]
    granted = [m for m in [mid,*available] if m not in baseline]
    for m in granted:
        if m not in c.moves:c.moves.append(m)
    ledger[mid] = {"weapon":weapon,"slots":slots,"struggle_id":mid,"available_moves":[mid,*available],"introduced_moves":granted,"independently_known":independently_known,"source":source}
    c.custom_conditions["equipped_weapons"] = ledger
    c.weapon = weapon
    FRAMEWORK.on_equip(engine,c,mid)
    if held is not None:
        HELD.commit(c,held,item_id=None,instance_id=weapon['instance_id'],registration_key=None)
        held['weapon_key']=mid
    engine.log(f"  {c.name} 무기 장착: {weapon['name']} ({'/'.join(slots)}), 부여 기술 {available}",source)
    return mid


def unequip_weapon(engine, c, key, *, _living_detach=False):
    """Remove only this physical weapon's grants; keep all independent/other grants."""
    ledger = c.custom_conditions.get("equipped_weapons", {})
    if key not in ledger:raise ValueError("missing weapon grant provenance")
    record = ledger[key]
    if record['weapon'].get('living_actor') and not _living_detach:
        raise ValueError('Living Weapon separation requires either participant Swift action')
    import optional_weapon_framework as FRAMEWORK
    FRAMEWORK.on_unequip(engine,c,record)
    if c.kind=='pokemon' and not record['weapon'].get('living_actor'):
        import held_equipment as HELD
        held=next((row for row in HELD.entries(c) if row.get('weapon_key')==key),None)
        if held is None:raise ValueError('Wielder weapon and actual held slot disagree')
        HELD.remove(c,held['slot_id'])
    ledger.pop(key)
    preserved = set(c.spec.get("moves",[])) | set(c.custom_conditions.get("independently_acquired_moves",[]))
    preserved.update(record.get("independently_known",[]))
    preserved.update(m for entry in ledger.values() for m in entry["available_moves"])
    preserved.update(m for entry in getattr(c,"_item_reg",{}).values() for m in entry.get("moves",[]))
    for move in record["available_moves"]:
        if move not in preserved and move in c.moves:c.moves.remove(move)
    c.weapon = next((entry["weapon"] for entry in ledger.values()),None)
    if not ledger:c.custom_conditions.pop("equipped_weapons",None)
    return record["weapon"]


@ACTION.continued_maneuver("maneuver/무장해제")
def disarm(engine, actor, target, *, attacker_skill, defender_skill, item_name=None,
           fixed_accuracy=None, challenger_options=None, defender_options=None, prevent_with_ap=None):
    """ch07:423-428: one adjacent target, one Standard, AC6, then opposed check."""
    import copy
    import skill_maneuver_actions as SM
    import items as ITEMS
    import skill_modifiers as SKILL
    import common_checks as CHECKS
    import temporary_hp as TEMP_HP
    import maneuver_opposed as OP
    from grid import cheb
    source="maneuver/무장해제"
    if engine.r._selected_rule(source)!=source:raise ValueError("selected Disarm variant requires its own policy")
    if actor is target or actor.kind not in ("trainer","pokemon") or target.kind not in ("trainer","pokemon"):
        raise ValueError("Disarm needs two distinct trainer/Pokemon actors")
    threaded=__import__('type_ace').threaded_scope(engine,actor)
    if not SM.native_reaction_resume(engine,actor,target,source) and (engine.grid is None or (not engine.adjacent(actor,target) and threaded is None) or not actor.on_field or not target.on_field or target.captured):
        raise ValueError("Disarm requires one adjacent on-field target")
    import optional_weapon_framework as FRAMEWORK
    for c,skill in ((actor,attacker_skill),(target,defender_skill)):
        allowed_skills=FRAMEWORK.disarm_skills(engine,c,item_name) if c is target else {"combat","stealth"}
        if SKILL.skill_id(engine.r.skill_policy,skill,required=True) not in allowed_skills:
            raise ValueError("Disarm permits Combat or Stealth only")
    import weapon_actions as WEAPONS
    # Heavy-event composition remains explicit until its event ordering is sourced.
    if engine.encounter_active and (actor.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(actor)):
        raise ValueError("heavy Standard Disarm event ordering requires its sourced adapter")
    TEMP_HP.ensure_certain(engine,actor);TEMP_HP.ensure_certain(engine,target)
    if fixed_accuracy is not None:CHECKS.integer(fixed_accuracy,"Disarm d20",1,20)
    import wielder_capability as WIELDER
    opts_a=WIELDER.disarm_options(engine,actor,challenger_options)
    opts_b,defense_bonus,prevention=WEAPONS.disarm_options(engine,target,defender_options,prevent_with_ap)
    for opts,purpose in ((opts_a,'disarm'),(opts_b,'resist_disarm')):
        context=opts.get('skill_context')
        if isinstance(context,dict) and 'purpose' not in context:
            opts['skill_context']=dict(OP._options(None,purpose)['skill_context'],**context)
        opts.update(OP._options(opts,purpose))
    featured=any(o.get('feature') is not None for o in (opts_a,opts_b))
    if not featured:
        for c,skill,opts in ((actor,attacker_skill,opts_a),(target,defender_skill,opts_b)):
            prepared=engine._prepare_skill_roll(c,skill,**opts)
            if prepared[3] is not None:opts['fixed']=prepared[3]
            if prepared[4] is not None:opts['fixed_penalties']=prepared[4]
    if opts_a.get("roll_id") is not None and opts_a.get("roll_id")==opts_b.get("roll_id"):
        raise ValueError("each Disarm opposed roll needs its own identity")
    chosen=disarm_equipment(engine,target,item_name)
    if chosen is None:return False
    plans=[(actor,attacker_skill,opts_a),(target,defender_skill,opts_b)]
    prepared=SM.prepare(engine,actor,target,source,{'chosen':chosen,'fixed_accuracy':fixed_accuracy,'defense_bonus':defense_bonus,'prevention':prevention},plans)
    move={'id':source,'name':'무장해제','type':'노말','class':'변화','ac':6,'range':'근접, 대상1','keywords':[]}
    def accuracy():
        import precise_actions as PRECISE
        event=PRECISE.attacked(engine,actor,target,move,producer='combat_maneuver')
        hit,natural=(True,None) if __import__('skirmisher').finesse_context(engine,actor,target,source) else engine.accuracy_check(actor,target,move,fixed_roll=fixed_accuracy)[:2]
        PRECISE.accuracy(event,hit,natural=natural)
        if not hit:__import__('martial_artist').maneuver_failed(engine,actor,target,source,opposed=False)
        return hit
    def outcome(won):
        result=_disarm_outcome(engine,target,prevention,chosen) if won else False
        if not won:__import__('martial_artist').maneuver_failed(engine,actor,target,source,opposed=True)
        if result and not isinstance(result,CHECKS.PendingDecision):
            import stat_ace as STAT
            STAT.maneuver_success(engine,actor,target,source)
        return result
    return SM.run(engine,actor,prepared,attack=move,
        spend=lambda:__import__('skirmisher').maneuver_spend(engine,actor,target,source,'shift' if threaded is not None else 'standard'),
        aoo=lambda:trigger_aoo(engine,actor,'무장해제',[c for c in adjacent_enemies(engine,actor) if c is not target]),
        can_continue=lambda:can_act(engine,actor),accuracy=accuracy,
        outcome=outcome,
        opposed=lambda:engine.opposed_check(actor,attacker_skill,target,defender_skill,challenger_options=opts_a,defender_options=opts_b))


def disarm_equipment(engine,target,item_name=None):
    """Select and admit the actual native held instance for either Disarm geometry."""
    import items as ITEMS
    source="maneuver/무장해제"
    candidates=[]
    for key,record in target.custom_conditions.get("equipped_weapons",{}).items():
        if (record.get('item_id') == 'item/몬스터볼-캐논'
                and any(row.get('instance_id') == record.get('instance_id')
                        and row.get('item_id') == record['item_id']
                        for row in getattr(target,'_item_reg',{}).values())):
            continue  # Disarm the one registered physical item, not its grant ledger.
        if {"주요손","반대손"}.intersection(record.get("slots",[])):
            candidates.append((key,"weapon",record["weapon"]["name"]))
    for key,record in getattr(target,"_item_reg",{}).items():
        if target.kind=="pokemon" or {"주요손","반대손"}.intersection(record.get("slots",[])):
            candidates.append((key,"item",record.get("name",key)))
    import held_equipment as HELD
    if target.kind=="pokemon":
        for held in HELD.entries(target):
            if held.get('weapon_key'):continue
            if any(x[0]==held.get('registration_key') for x in candidates):continue
            eff,header=engine.r.item_effects(held['name'])
            if eff is not None:candidates.append(('slot:'+held['slot_id'],'item',held['name']))
    import wielder_capability as WIELDER
    candidates.extend((row['key'],'natural',row['name']) for row in WIELDER.natural_rows(target))
    if item_name is None:
        if len(candidates)!=1:raise ValueError("Disarm needs one explicit held-item selection")
        chosen=candidates[0]
    else:
        matching=[x for x in candidates if item_name in (x[0],x[2])]
        if len(matching)!=1:raise ValueError("selected item is not uniquely held in an eligible hand")
        chosen=matching[0]
    import equipment_protection as PROTECTION
    equipment_key=("weapon:"+chosen[0] if chosen[1]=="weapon" else chosen[0] if chosen[1]=='natural' else next(x["key"] for x in ITEMS.equipment_options(target,("held","주요손","반대손")) if x.get('registration_key')==chosen[0] or 'slot:'+str(x.get('held_slot'))==chosen[0]))
    equipment=ITEMS.selected_equipment(target,equipment_key,("held","주요손","반대손"))
    protection=PROTECTION.status(engine,target,equipment,"disarm")
    import fashionista as FASHIONISTA
    if protection["status"]=="blocked":
        # An armed Style is Eternal answers the actual Disarm; the maneuver itself is still attempted.
        if protection.get("source")!=FASHIONISTA.STYLE:return None
    else:PROTECTION.require(engine,target,equipment,"disarm")
    return chosen


def _disarm_outcome(engine,target,prevention,chosen):
    import copy
    import items as ITEMS
    import weapon_actions as WEAPONS
    source='maneuver/무장해제'
    if WEAPONS.prevent_disarm(engine,target,prevention):return False
    key,kind,name=chosen
    equipment_key="weapon:"+key if kind=="weapon" else next(x["key"] for x in ITEMS.equipment_options(target,("held","주요손","반대손")) if x.get('registration_key')==key or 'slot:'+str(x.get('held_slot'))==key)
    import equipment_protection as PROTECTION
    equipment=ITEMS.selected_equipment(target,equipment_key,("held","주요손","반대손"))
    protection=PROTECTION.status(engine,target,equipment,"disarm")
    import fashionista as FASHIONISTA
    if protection["status"]=="blocked" and protection.get("source")==FASHIONISTA.STYLE:
        FASHIONISTA.keep(engine,target,protection,operation="disarm",source=source)
        engine.log(f"    {target.name}: 무장해제되었으나 스타일은 영원하다로 {name} 유지",FASHIONISTA.STYLE)
        return True
    PROTECTION.require(engine,target,equipment,"disarm")
    # Source/passive cleanup and physical location move with the real instance.
    result=ITEMS.drop_equipment(engine,target,[equipment_key],slots=("held","주요손","반대손"),source=source)
    if kind=="weapon":
        engine.log(f"    {target.name}: {name}을(를) {target.pos}에 떨어뜨림",source)
        return True
    dropped=result['dropped'][0]
    ground=getattr(engine,"ground_items",None)
    if ground is None:engine.ground_items=[];ground=engine.ground_items
    ground.append({"item":name,"instance_id":dropped.get("instance_id"),"former_equipment_key":equipment_key,"position":tuple(target.pos),"from_actor":target.spec.get("id",target.name),"source":source,"kind":kind})
    engine.log(f"    {target.name}: {name}을(를) {target.pos}에 떨어뜨림",source)
    return True

