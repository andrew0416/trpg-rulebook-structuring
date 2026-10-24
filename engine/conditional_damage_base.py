"""Source-scoped conditional DB receipts and round-end setup moves.

The reviewed move rows use two facts that the generic expression evaluator cannot
infer: who dealt actual attack damage during the open round, and whether Assurance
already spent its per-target scene trigger.  This module owns those facts and the
shared Revenge/Avalanche round-end reservation.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path


STATE = "_conditional_damage_base"
ASSURANCE_CONDITION = "target already took damage this round"
RETALIATION_CONDITION = "target damaged user this round"
POLICY_FILE = Path(__file__).resolve().parents[1] / "data" / "conditional-damage-base-policy.json"


@lru_cache(maxsize=1)
def _policies():
    data = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    rows = data.get("moves")
    if not isinstance(rows, dict):
        raise ValueError("conditional damage-base policy needs a moves mapping")
    return rows


def policy(move):
    row = _policies().get(move.get("id"))
    return row if isinstance(row, dict) else None


def manages(move):
    return policy(move) is not None


def execution_mechanics(move, mechanics):
    """Remove a reviewed static DB declaration from generic effect dispatch."""
    if move.get('_type_ace_new_normal'):
        return dict(mechanics,effects_exec=[e for e in mechanics.get('effects_exec',[]) if e.get('type') not in ('conditional_damage_base','damage_base_formula','escalating_damage_base')])
    if not manages(move):
        return mechanics
    row = policy(move)
    repairs = row.get("effect_repairs", {})
    effects = []
    contract = row.get("contract")
    for effect in mechanics.get("effects_exec", []):
        if effect.get("type") == "conditional_damage_base":
            continue
        if (contract == "forced_move_damage_streak"
                and effect.get("type") == "escalating_damage_base"):
            continue
        effect = dict(effect)
        if effect.get("type") == "apply_status" and repairs:
            effect["status"] = repairs.get(effect.get("status"), effect.get("status"))
            if "target" in repairs:
                effect["target"] = repairs["target"]
            if "duration" in repairs:
                effect["duration"] = repairs["duration"]
        effects.append(effect)
    result = dict(mechanics)
    result["effects_exec"] = effects
    return result


def _identity(actor):
    value = getattr(actor, "entity_id", None)
    return value if isinstance(value, str) and value else f"object:{id(actor)}"


def _state(actor, *, create=False):
    if create:
        return actor.custom_conditions.setdefault(
            STATE, {"damage_round": None, "damaged_by": {}, "streaks": {}})
    value = actor.custom_conditions.get(STATE, {})
    return value if isinstance(value, dict) else {}


def _effects(engine, move):
    return engine.r.move_mech(move["id"])[0].get("effects_exec", [])


def _limit_key(move, target):
    return f"lim:conditional-db:{move['id']}:{_identity(target)}"


def _scene_key(move):
    return f"lim:conditional-db:{move['id']}:scene"


def _streak(actor, move):
    return _state(actor).get("streaks", {}).get(move["id"], {})


def _pass_scope(engine, actor, move):
    scope = getattr(engine, "_pass_move_scope", None)
    if scope is None or scope["actor"] is not actor or scope["move_id"] != move["id"]:
        return None
    import pass_moves as PASS
    PASS.require_scope(engine, actor, scope)
    return scope


def begin_pass(engine, actor, move, scope):
    """Freeze the existing streak for every recipient of this paid use."""
    row = policy(move)
    if row is not None and row.get("contract") == "forced_move_damage_streak":
        if _pass_scope(engine, actor, move) is not scope or not scope.get("paid"):
            raise ValueError("forced streak requires its actual paid Pass")
        scope["repeat_successes"] = _streak(actor, move).get("successes", 0)


def finish_pass(engine, actor, move, scope, completion_id):
    """Commit once from the real whole-Pass native completion."""
    if "repeat_successes" not in scope:
        return
    if _pass_scope(engine, actor, move) is not scope:
        raise ValueError("forced streak requires its actual Pass completion")
    completion = getattr(engine, "_move_completions", {}).get(completion_id)
    if (completion is None or completion["phase"] != "complete" or not completion["sealed"]
            or completion["actor"] is not actor or completion["move_id"] != move["id"]
            or tuple(completion["targets"]) != scope["creatures"]):
        raise ValueError("forced streak requires the complete actual native recipient set")
    results = list(completion["results"].values())
    if any(not row["hit"] or row["cancelled"] for row in results):
        import forced_move_lock as FORCED
        FORCED.clear(engine, actor, move["id"], reason="miss")
        return
    streaks = _state(actor, create=True).setdefault("streaks", {})
    if (any(row["dealt"] > 0 for row in results)
            or "no_damage" not in policy(move).get("reset", ())):
        streaks[move["id"]] = {"successes": scope["repeat_successes"] + 1}
    else:
        streaks.pop(move["id"], None)


def begin_activation(actor, move_id):
    """Break source-declared consecutive chains when another Move is activated."""
    state = _state(actor)
    streaks = state.get("streaks")
    if not isinstance(streaks, dict):
        return
    for stored in tuple(streaks):
        stored_policy = _policies().get(stored, {})
        if (stored != move_id
                and stored_policy.get("contract") != "forced_move_damage_streak"):
            streaks.pop(stored, None)


def miss(attacker, move):
    """A real miss resets only a policy whose source explicitly says so."""
    row = policy(move)
    if row and row.get("contract") in {
            "same_target_damage_streak", "forced_move_damage_streak"}:
        _state(attacker, create=True).setdefault("streaks", {}).pop(move["id"], None)


def reset_streak(attacker, move_id):
    """End one reviewed damage chain at its source-declared boundary."""
    row = _policies().get(move_id)
    if row and row.get("contract") in {
            "same_target_damage_streak", "forced_move_damage_streak"}:
        _state(attacker, create=True).setdefault("streaks", {}).pop(move_id, None)


def _afflicted(target):
    import status_sets as STATUS_SETS
    return bool(STATUS_SETS.afflictions(target))


def override_base(engine, attacker, target, move, base):
    """Read a reviewed CSV contract without mutating preview state."""
    row = policy(move)
    if row is None or target is None:
        return base
    contract = row.get("contract")
    if contract == "same_target_damage_streak":
        current = _streak(attacker, move)
        successes = current.get("successes", 0) if current.get("target_id") == _identity(target) else 0
        return min(row["cap"], row["base"] + row["increment"] * successes)
    if contract == "forced_move_damage_streak":
        scope = _pass_scope(engine, attacker, move)
        successes = (scope["repeat_successes"] if scope is not None and "repeat_successes" in scope
                     else _streak(attacker, move).get("successes", 0))
        return min(row["cap"], row["base"] + row["increment"] * successes)
    if contract == "scene_once_afflicted_target":
        if row.get("optional"):
            return base
        if not attacker.counters.get(_scene_key(move), 0) and _afflicted(target):
            return row["replacement"]
        return base
    if contract == "external_stage_loss_since_turn_end_per_target_scene":
        import stage_change_history as STAGE_HISTORY
        if (not attacker.counters.get(_limit_key(move, target), 0)
                and STAGE_HISTORY.losses_since_turn_end(attacker, external_only=True)):
            return row["replacement"]
        return base
    raise ValueError("unsupported conditional damage-base contract: " + str(contract))


def record_attack_damage(engine, attacker, target, receipt):
    """Record only observed HP or temporary-HP loss from the native damage receipt."""
    loss = receipt.get("net_hp_loss", 0) + receipt.get("net_temporary_hp_loss", 0)
    if loss <= 0:
        return False
    state = _state(target, create=True)
    state["damage_round"] = engine.round_no
    state.setdefault("damaged_by", {})[_identity(attacker)] = engine.round_no
    return True


def predicate(engine, attacker, target, move, effect):
    condition = effect.get("if")
    if target is None:
        return False
    if condition == ASSURANCE_CONDITION:
        state = _state(target)
        return (state.get("damage_round") == engine.round_no
                and not attacker.counters.get(_limit_key(move, target), 0))
    if condition == RETALIATION_CONDITION:
        state = _state(attacker)
        return state.get("damaged_by", {}).get(_identity(target)) == engine.round_no
    return None


def prepare(engine, attacker, target, move):
    """Capture eligibility before the current hit can become its own evidence."""
    applied = []
    row = policy(move)
    if row is not None:
        contract = row.get("contract")
        if contract in {"same_target_damage_streak", "forced_move_damage_streak"}:
            applied.append({"contract": contract})
        elif contract == "scene_once_afflicted_target" and target is not None and not row.get("optional"):
            if not attacker.counters.get(_scene_key(move), 0) and _afflicted(target):
                applied.append({"contract": contract})
        elif contract == "external_stage_loss_since_turn_end_per_target_scene" and target is not None:
            import stage_change_history as STAGE_HISTORY
            events=STAGE_HISTORY.losses_since_turn_end(attacker, external_only=True)
            if not attacker.counters.get(_limit_key(move, target), 0) and events:
                applied.append({"contract": contract,
                                "stage_event_ids": [event["id"] for event in events]})
        else:
            if contract != "scene_once_afflicted_target":
                raise ValueError("unsupported conditional damage-base contract: " + str(contract))
    for effect in _effects(engine, move):
        if effect.get("type") != "conditional_damage_base":
            continue
        result = predicate(engine, attacker, target, move, effect)
        if result:
            applied.append({"condition": effect.get("if"), "damage_base": effect["damage_base"]})
    plan = {"move_id": move["id"], "target_id": _identity(target), "applied": applied}
    if row is not None and row.get("contract") == "forced_move_damage_streak":
        scope = _pass_scope(engine, attacker, move)
        if scope is not None and "repeat_successes" in scope:
            plan["defer_forced_streak"] = True
    return plan


def override(engine, attacker, target, move, effect):
    result = predicate(engine, attacker, target, move, effect)
    return effect.get("damage_base") if result is True else None


def commit(attacker, target, move, plan, receipt=None):
    if (not plan or plan.get("move_id") != move["id"]
            or plan.get("target_id") != _identity(target)):
        raise ValueError("conditional damage-base plan does not match the applied hit")
    if any(row.get("condition") == ASSURANCE_CONDITION for row in plan.get("applied", [])):
        attacker.counters[_limit_key(move, target)] = 1
    contracts = {row.get("contract") for row in plan.get("applied", [])}
    if "scene_once_afflicted_target" in contracts:
        attacker.counters[_scene_key(move)] = 1
    if "external_stage_loss_since_turn_end_per_target_scene" in contracts:
        attacker.counters[_limit_key(move, target)] = 1
    if "same_target_damage_streak" in contracts:
        if not isinstance(receipt, dict):
            raise ValueError("same-target streak commit requires the actual damage receipt")
        loss = receipt.get("net_hp_loss", 0) + receipt.get("net_temporary_hp_loss", 0)
        streaks = _state(attacker, create=True).setdefault("streaks", {})
        if loss <= 0:
            streaks.pop(move["id"], None)
        else:
            previous = streaks.get(move["id"], {})
            successes = previous.get("successes", 0) if previous.get("target_id") == _identity(target) else 0
            streaks[move["id"]] = {
                "target_id": _identity(target),
                "successes": successes + 1,
            }
    if "forced_move_damage_streak" in contracts:
        if plan.get("defer_forced_streak"):
            return
        if not isinstance(receipt, dict):
            raise ValueError("forced Move streak commit requires the actual damage receipt")
        loss = receipt.get("net_hp_loss", 0) + receipt.get("net_temporary_hp_loss", 0)
        streaks = _state(attacker, create=True).setdefault("streaks", {})
        if loss <= 0 and "no_damage" in policy(move).get("reset", ()):
            streaks.pop(move["id"], None)
        else:
            previous = streaks.get(move["id"], {})
            streaks[move["id"]] = {"successes": previous.get("successes", 0) + 1}


def round_end_setup(effect):
    return (isinstance(effect, dict)
            and effect.get("type") == "set_up_move"
            and effect.get("declare") == "no actions this round"
            and effect.get("resolve") == "at round end: shift and use")


def action_locked(actor):
    row = _state(actor).get("pending_setup")
    return isinstance(row, dict) and not row.get("resolving", False)


def pending_move(actor, move_id):
    row = _state(actor).get("pending_setup")
    return isinstance(row, dict) and row.get("move_id") == move_id


def resolving(actor, move_id):
    row = _state(actor).get("pending_setup")
    return isinstance(row, dict) and row.get("move_id") == move_id and row.get("resolving") is True


def round_end_authorized(actor, target, move_id):
    row = _state(actor).get("pending_setup")
    return (isinstance(row, dict) and row.get("resolving") is True
              and row.get("move_id") == move_id and (row.get("target") is target or move_id=='move/울부짖기'))


def declare(engine, actor, target, move):
    state = _state(actor, create=True)
    if state.get("pending_setup") is not None:
        raise ValueError("an unresolved round-end setup move already exists")
    state["pending_setup"] = {
        "move_id": move["id"], "target": target, "round": engine.round_no,
        "saved_budget": deepcopy(getattr(actor, "budget", {})), "resolving": False,
    }
    actor.setup_move = move["id"]
    if move['id']=='move/울부짖기':
        import style_expert as STYLE
        value=STYLE.scope(engine,actor,move)
        if value is not None:state['pending_setup']['style_expert']=dict(value)
    if isinstance(getattr(actor, "budget", None), dict):
        for key in actor.budget:
            actor.budget[key] = 0
    import frequency as FREQ
    FREQ.consume_move(engine, actor, move["id"])
    engine.log(f"  {actor.name} {move['name']}: 라운드말 공격 예약; 그때까지 행동·이동 잠금",
               f"{move['id']} conditional_damage_base/round_end_setup")


def finish_round(engine):
    """Resolve source-declared setup moves before the shared round closes."""
    for actor in list(engine.time_actors()):
        row = _state(actor).get("pending_setup")
        if not isinstance(row, dict) or row.get("round") != engine.round_no:
            continue
        target = row.get("target")
        move_id = row.get("move_id")
        if (move_id not in engine.r.moves or actor.fainted
                or (move_id != 'move/울부짖기' and (target is None or target.fainted))):
            actor.setup_move = None
            _state(actor).pop("pending_setup", None)
            continue
        if isinstance(getattr(actor, "budget", None), dict):
            actor.budget.clear()
            actor.budget.update(deepcopy(row.get("saved_budget", {})))
        row["resolving"] = True
        try:
            if move_id=='move/울부짖기':
                import roar as ROAR
                ROAR.shift(engine,actor)
                value=row.get('style_expert')
                if value:engine._style_move_scope=value
                before=set(getattr(engine,'_move_completions',{}))
                try:
                    # Roar selects a new self-centred Burst after its Shift.
                    engine.use_move_on(actor,actor,move_id,engine.everyone)
                    if not any(key not in before and item['actor'] is actor and item['move_id']==move_id and item['phase']=='complete' for key,item in engine._move_completions.items()):
                        raise ValueError('Roar release requires actual completed native activation')
                finally:
                    if value:del engine._style_move_scope
                continue
            if engine.grid is not None and not engine.adjacent(actor, target):
                engine.approach(actor, target, 1)
            engine.use_move(actor, target, move_id, count_use=False)
        finally:
            actor.setup_move = None
            _state(actor).pop("pending_setup", None)


def clear_scene(actor):
    state = _state(actor)
    state.pop("pending_setup", None)
    if not state.get("damaged_by") and state.get("damage_round") is None:
        actor.custom_conditions.pop(STATE, None)
