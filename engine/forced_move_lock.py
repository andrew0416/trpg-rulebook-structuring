"""Source-owned repeat-Move choice lock for Ice Ball and Rollout.

The lock is created by an actual hit, consumed at the next ordinary Move choice,
and released only by an actual miss or by observing that no active encounter
target remains.  Damage escalation stays in ``conditional_damage_base`` so
preview queries never advance the chain.
"""
from __future__ import annotations


STATE = "_forced_move_lock"


def _repeat_effect(engine, move_id):
    effects = engine.r.move_mech(move_id)[0].get("effects_exec", [])
    return next((row for row in effects if row.get("type") == "repeat_each_turn"), None)


def manages(engine, move_id):
    row = _repeat_effect(engine, move_id)
    if not isinstance(row, dict):
        return False
    until = str(row.get("until", "")).lower()
    return "miss" in until and "no target" in until


def _record(actor):
    value = actor.custom_conditions.get(STATE)
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("move_id"), str):
        raise ValueError("forced Move lock requires a source-owned record")
    if actor.locked_move != value["move_id"]:
        raise ValueError("forced Move lock projection disagrees with its owner")
    return value


def current(engine, actor):
    record = _record(actor)
    if record is not None:
        if not manages(engine, record["move_id"]):
            raise ValueError("forced Move lock source no longer has a repeat contract")
        return record["move_id"]
    # Older saves already persisted the public ``locked_move`` projection.
    # Read it without mutating during a rejected preflight; the next admitted
    # hit writes the richer source record.
    move_id = getattr(actor, "locked_move", None)
    if isinstance(move_id, str) and manages(engine, move_id):
        return move_id
    return None


def _active_targets(engine, actor, candidates):
    import combat_state_lifecycle as COMBAT_STATE

    roster = COMBAT_STATE.members(engine, tuple(candidates))
    return [
        target for target in roster
        if target is not actor
        and not target.fainted
        and not target.captured
        and getattr(target, "on_field", True)
    ]


def clear(engine, actor, move_id, *, reason):
    record = _record(actor)
    if record is not None and record["move_id"] != move_id:
        raise ValueError("cannot clear a different forced Move lock")
    if getattr(actor, "locked_move", None) == move_id:
        actor.locked_move = None
    actor.custom_conditions.pop(STATE, None)
    import conditional_damage_base as CONDITIONAL_DB

    CONDITIONAL_DB.reset_streak(actor, move_id)
    engine.log(f"    {actor.name} 강제 연속 기술 종료 ({reason})", move_id)


def hit(engine, actor, move):
    move_id = move.get("id")
    if not isinstance(move_id, str) or not manages(engine, move_id):
        return False
    actor.locked_move = move_id
    actor.custom_conditions[STATE] = {
        "move_id": move_id,
        "source_id": move_id,
        "until": "miss_or_no_target",
    }
    engine.log(f"    {actor.name}은(는) 다음 턴에도 {move.get('name', move_id)} 사용", move_id)
    return True


def miss(engine, actor, move):
    move_id = move.get("id")
    if not isinstance(move_id, str) or current(engine, actor) != move_id:
        return False
    clear(engine, actor, move_id, reason="miss")
    return True


def preflight_choice(engine, actor, requested_move_id, candidates, *, ordinary):
    """Admit an ordinary choice before action, frequency, or RNG is consumed."""
    if type(ordinary) is not bool:
        raise ValueError("forced Move choice boundary requires an explicit ordinary flag")
    locked = current(engine, actor)
    if locked is None or not ordinary:
        return True
    targets = _active_targets(engine, actor, candidates)
    if not targets:
        clear(engine, actor, locked, reason="no_target")
        # Choosing a different Move is now legal.  A request for the locked
        # attack itself has no target and therefore ends without spending.
        return requested_move_id != locked
    if requested_move_id != locked:
        engine.log(
            f"  {actor.name}: {engine.r.move(locked)['name']} 연속 사용 중이라 다른 기술 선택 불가",
            locked,
        )
        return False
    return True
