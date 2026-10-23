"""Own the existing Vortex record, its derived restrictions and escape progress.

Engine and effect hooks supply actual events. This module neither imports their
dispatch adapters nor creates a second condition or timing ledger.
"""
KEY = "vortex"
SOURCE = "keyword/조이기"


def escape_bonus(parameters):
    if parameters is None:
        return 0
    if not isinstance(parameters, dict) or set(parameters) - {"escape_dc_bonus"}:
        raise ValueError("Vortex parameters support only escape_dc_bonus")
    bonus = parameters.get("escape_dc_bonus", 0)
    if type(bonus) is not int or bonus < 0:
        raise ValueError("Vortex escape bonus must be a nonnegative integer")
    return bonus


def configure(actor, parameters):
    bonus = escape_bonus(parameters)
    state = actor.custom_conditions.get(KEY)
    if state is None:
        raise ValueError("Vortex parameters need the actual applied condition")
    current = escape_bonus({"escape_dc_bonus": state.get("escape_dc_bonus", 0)})
    if bonus > current:
        state["escape_dc_bonus"] = bonus


def before_apply(engine, actor, condition):
    if condition == "조이기":
        engine.r._selected_rule(SOURCE)
    state = actor.custom_conditions.get(KEY)
    if state and not state.get("installing") and condition in ("둔화", "수렁"):
        state["owned"].discard(condition)


def applied(engine, actor, condition):
    if condition != "조이기":
        return
    state = {"ends": 0, "owned": set(), "installing": True}
    actor.custom_conditions[KEY] = state
    for child in ("둔화", "수렁"):
        if child not in actor.conditions and engine.apply_status(actor, child):
            state["owned"].add(child)
    state["installing"] = False


def before_cure(engine, actor, condition):
    state = actor.custom_conditions.get(KEY)
    if condition == "조이기":
        state = actor.custom_conditions.pop(KEY, None)
        if state:
            for child in sorted(state["owned"]):
                engine.cure_status(actor, child)
    elif state:
        state["owned"].discard(condition)


def turn_start(engine, actor):
    if "조이기" in actor.conditions:
        engine.r._selected_rule(SOURCE)
        engine.lose_tick_hp(actor,1,source=SOURCE)


def turn_end(engine, actor):
    if "조이기" not in actor.conditions:
        return
    engine.r._selected_rule(SOURCE)
    state = actor.custom_conditions.get(KEY)
    if state is None:
        raise ValueError("Vortex needs an applied condition record; use Engine.apply_status")
    bonus = escape_bonus({"escape_dc_bonus": state.get("escape_dc_bonus", 0)})
    state["ends"] += 1
    if state["ends"] >= 5:
        engine.cure_status(actor, "조이기")
        engine.log(f"    {actor.name}: 조이기 다섯 번째 턴 종료, 자동 탈출", SOURCE)
    else:
        threshold = 20 - 6 * (state["ends"] - 1) + bonus
        import duelist as DUELIST
        roll = 11 if DUELIST.choose_eleven(engine,actor,'vortex_escape') else engine.d20()
        import fashion_items as FASHION
        modifier = FASHION.all_roll_modifier(actor)
        total = roll + modifier
        escaped = total > threshold
        engine.log(f"    {actor.name}: 조이기 탈출 d20={roll}{modifier:+d}={total} > {threshold}: {escaped}", SOURCE)
        if escaped:
            engine.cure_status(actor, "조이기")
