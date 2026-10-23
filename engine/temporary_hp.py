"""Source-backed temporary-HP lifetime, separate from ordinary healing.

Ordinary grants expire after five minutes outside combat, per the original
PTU1.05 text. Actual combat participation pauses that timer. Explicit GM wall-clock overrides remain
separate, and old rule records without a clock basis need reconciliation.
"""
import common_checks as CHECKS
from copy import deepcopy
from pathlib import Path
import hashlib,json

STATE = "temporary_hp_lifetime"
CLOCK = "out_of_combat_seconds"
LOSS_MODES = ('temp_first', 'bypass')


def loss_policy(engine):
    """Defensive view of the persistent GM interpretation for unpreventable loss."""
    from copy import deepcopy
    row = getattr(engine, '_hp_loss_policy', None)
    if row is None:
        return {'mode': 'temp_first', 'reason': 'user-adopted project default'}
    if (type(row) is not dict or set(row) != {'mode', 'reason'}
            or row['mode'] not in LOSS_MODES or type(row['mode']) is not str
            or type(row['reason']) is not str or not row['reason'].strip()):
        raise ValueError('HP loss policy requires temp_first/bypass and a reason')
    return deepcopy(row)


def configure_loss_policy(engine, mode, *, reason):
    if (type(mode) is not str or mode not in LOSS_MODES
            or type(reason) is not str or not reason.strip()):
        raise ValueError('HP loss policy requires temp_first/bypass and a reason')
    engine._hp_loss_policy = {'mode': mode, 'reason': reason.strip()}
    return loss_policy(engine)


def loss_remainder(engine, actor, amount, *, unpreventable=False):
    """Allocate a loss without changing its amount or granting damage reactions.

    Unpreventable always bypasses damage caps at the producer. Its temporary-HP
    allocation follows the persistent GM choice; HP-setting adapters do not call
    this function. Pain Split reuses it while retaining its no-injury contract.
    """
    CHECKS.integer(amount, 'HP loss', 0)
    if type(unpreventable) is not bool:
        raise ValueError('unpreventable must be an explicit boolean')
    choice = loss_policy(engine)
    if unpreventable and choice['mode'] == 'bypass':
        ensure_certain(engine, actor)
        return amount
    return absorb(engine, actor, amount)


def policy(rules):
    row=getattr(rules,"_temporary_hp_policy",None)
    if row is None:
        row=json.loads((Path(rules.root)/"data/temporary-hp-policy.json").read_text(encoding="utf-8"))
        for file,digest in row["source_files"].items():
            if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError("temporary HP source changed: "+file)
        if row["clock_basis"]!=CLOCK or row["duration_seconds"]!=300:raise ValueError("unsupported temporary HP timer policy")
        rules._temporary_hp_policy=row
    return row


def validate(actor):
    """Validate shared balance/lifetime without inventing an imported timestamp."""
    CHECKS.integer(actor.temp_hp, "temporary HP", 0)
    state = actor.custom_conditions.get(STATE)
    if state is None:
        return
    if not isinstance(state, dict):
        raise ValueError("temporary HP lifetime must be a mapping")
    kind = state.get("kind")
    expected = {"rule_grant": "condition/임시-체력", "gm_override": "gm/state"}
    if kind not in expected or state.get("source") != expected[kind]:
        raise ValueError("temporary HP lifetime source mismatch")
    events=state.get('grant_events',[])
    if not isinstance(events,list):raise ValueError('temporary HP grant events must be a list')
    for event in events:
        if not isinstance(event,dict) or set(event)!={'amount','stack','provenance','at','round'}:raise ValueError('invalid temporary HP grant provenance')
        CHECKS.integer(event['amount'],'temporary HP granted amount',1)
        if type(event['stack']) is not bool or not isinstance(event['provenance'],dict):raise ValueError('invalid temporary HP grant mode/provenance')
        CHECKS.integer(event['at'],'temporary HP grant time',0);CHECKS.integer(event['round'],'temporary HP grant round',0)
        try:json.dumps(event['provenance'],ensure_ascii=False)
        except (TypeError,ValueError) as exc:raise ValueError('temporary HP provenance must be JSON data') from exc
    if "expiry_policy" in state:
        if (kind != "gm_override" or state["expiry_policy"] != "explicit_unbounded"
                or "minimum_seconds" in state or "maximum_seconds" in state or "clock_basis" in state):
            raise ValueError("invalid temporary HP expiry policy")
        return
    low = CHECKS.integer(state.get("minimum_seconds"), "temporary HP earliest expiry")
    high = CHECKS.integer(state.get("maximum_seconds"), "temporary HP latest expiry", 0)
    if low > high:
        raise ValueError("temporary HP expiry bounds are reversed")
    basis=state.get("clock_basis")
    if basis is not None:
        if kind!="rule_grant" or basis!=policy(actor.r)["clock_basis"]:raise ValueError("temporary HP clock basis mismatch")
        if state.get("uncertain_birth",False) or state.get("out_of_combat_elapsed_unresolved",False):raise ValueError("outside-combat temporary HP clock cannot inherit a combat-time uncertainty")
        if low!=high and state.get("unknown_elapsed") is not True:raise ValueError("outside-combat temporary HP expiry bounds need an observed unknown interval")
    birth = state.get("birth_round")
    if birth is not None:
        CHECKS.integer(birth, "temporary HP birth round", 0)
    for key in ("uncertain_birth", "unknown_elapsed", "out_of_combat_elapsed_unresolved"):
        if key in state and type(state[key]) is not bool:
            raise ValueError("temporary HP timing flags must be boolean")


def absorb(engine, actor, amount):
    """Spend the shared barrier once and return only the real-HP remainder.

    Callers resolve damage caps and source-specific bypasses before this step.
    Consuming the last point removes its lifetime as part of the same change.
    """
    CHECKS.integer(amount, "HP loss", 0)
    ensure_certain(engine, actor)
    used = min(actor.temp_hp, amount)
    if used:
        actor.temp_hp -= used
        if actor.temp_hp == 0:
            actor.custom_conditions.pop(STATE, None)
        engine.log(f"    임시 체력이 {used} 흡수 (남은 임시 {actor.temp_hp})", "condition/임시-체력")
    return amount - used


def _policy(engine):
    if engine.r._selected_rule("condition/임시-체력") != "condition/임시-체력":
        raise ValueError("selected temporary HP variant requires its own lifetime policy")
    effects = engine.r.condition_effects("임시-체력")
    rule = next((e for e in effects if e.get("type") == "temp_hp_rules"), None)
    if not rule or set(rule.get("lost_on", [])) != {"recall", "5min"}:
        raise ValueError("unsupported temporary HP lifetime policy")
    return policy(engine.r)["duration_seconds"]


def clear(engine, actor, reason):
    before = actor.temp_hp
    actor.temp_hp = 0
    actor.custom_conditions.pop(STATE, None)
    if before:
        engine.log(f"    {actor.name} 임시 체력 {before} 소멸 ({reason})", "condition/임시-체력")


def grant(engine, actor, value, *, round_offset_seconds=None, stack=False, provenance=None):
    CHECKS.integer(value, "temporary HP", 0)
    if type(stack) is not bool:raise ValueError('temporary HP stack mode must be boolean')
    if provenance is not None and not isinstance(provenance,dict):raise ValueError('temporary HP provenance must be a mapping')
    duration = _policy(engine)
    import actor_templates as TEMPLATES
    if TEMPLATES.soulless(actor):
        return 0
    import food_effects as FOOD
    if not FOOD.temp_hp_allowed(actor):
        return 0
    if round_offset_seconds is not None:
        engine.at_round_offset(round_offset_seconds)
    ensure_certain(engine, actor)
    import healing_blocks as HEALING_BLOCKS
    if HEALING_BLOCKS.blocked(actor):
        return 0
    import recovery_resolution as RECOVERY
    recovery=RECOVERY.resolve(actor.temp_hp,value,resource='temp_hp',mode='add' if stack else 'at_least')
    if not recovery['applied']:
        return 0
    before = actor.temp_hp
    upper = duration
    actor.temp_hp = recovery['after']
    prior=actor.custom_conditions.get(STATE,{}).get('grant_events',[])
    lifetime={
        "kind": "rule_grant", "source": "condition/임시-체력", "clock_basis": CLOCK,
        "minimum_seconds": duration, "maximum_seconds": upper,
        "birth_round": engine.round_no if engine.round_start_seconds is not None else None,
        "uncertain_birth": upper != duration,
    }
    if prior or provenance is not None:
        lifetime['grant_events']=list(prior)
        if provenance is not None:lifetime['grant_events'].append({'amount':recovery['applied'],'stack':stack,
            'provenance':deepcopy(provenance),'at':engine.elapsed_seconds,'round':engine.round_no})
    actor.custom_conditions[STATE] = lifetime
    engine.time_actors([actor])
    engine.log(f"    {actor.name} 임시 체력 {actor.temp_hp}", "condition/임시-체력")
    return recovery['applied']


def advance(engine, actor, seconds):
    CHECKS.integer(seconds,"temporary HP elapsed seconds",0)
    validate(actor)
    state = actor.custom_conditions.get(STATE)
    if state is None or state.get("expiry_policy") == "explicit_unbounded":
        return
    if actor.temp_hp <= 0:
        actor.custom_conditions.pop(STATE, None)
        return
    if state.get("kind")=="rule_grant":
        if state.get("clock_basis")!=CLOCK:return  # preserve unreconciled legacy timing
        if engine.encounter_active:
            import combat_state_lifecycle as COMBAT
            if any(c is actor for c in COMBAT.members(engine)):return
    state["minimum_seconds"] -= seconds
    state["maximum_seconds"] -= seconds
    if state["maximum_seconds"] <= 0:
        clear(engine, actor, "5분 경과")


def unknown_interval(actor, maximum_seconds, *, outside_combat=False):
    CHECKS.integer(maximum_seconds,"unknown combat interval",0)
    validate(actor)
    state = actor.custom_conditions.get(STATE)
    if state and state.get("expiry_policy") != "explicit_unbounded" and actor.temp_hp > 0:
        if state.get("kind")=="rule_grant":
            # Preserve legacy records; actual outsiders still experienced this interval.
            if state.get("clock_basis")!=CLOCK or not outside_combat:return
        state["minimum_seconds"] -= maximum_seconds
        state["unknown_elapsed"] = True


def ensure_certain(engine, actor):
    validate(actor)
    state = actor.custom_conditions.get(STATE)
    if state is None and actor.temp_hp>0:
        raise ValueError("temporary HP expiry needs an origin/clock observation")
    if state is None or state.get("expiry_policy") == "explicit_unbounded" or actor.temp_hp <= 0:
        return
    if state.get("kind")=="rule_grant" and state.get("clock_basis")!=CLOCK:
        raise ValueError("temporary HP expiry needs legacy clock-basis reconciliation")
    if state["maximum_seconds"] <= 0:
        clear(engine, actor, "5분 경과")
    elif state["minimum_seconds"] <= 0:
        raise ValueError("temporary HP expiry needs the unresolved grant/elapsed timestamp")


def gm_set(engine, actor, value, *, duration_seconds=None, round_offset_seconds=None):
    """Explicit state override; never masquerades as a sourced ordinary grant."""
    CHECKS.integer(value, "GM temporary HP", 0)
    import actor_templates as TEMPLATES
    if value and TEMPLATES.soulless(actor):
        raise ValueError("Soulless requires a rule override before adding temporary HP")
    if duration_seconds is not None:
        CHECKS.integer(duration_seconds, "GM temporary HP duration", 0)
    if round_offset_seconds is not None:
        engine.at_round_offset(round_offset_seconds)
    if value == 0:
        clear(engine, actor, "GM 지정")
        return
    actor.temp_hp = value
    state = {"kind": "gm_override", "source": "gm/state"}
    if duration_seconds is None:
        state["expiry_policy"] = "explicit_unbounded"
    else:
        upper = duration_seconds
        if engine.round_start_seconds is not None and round_offset_seconds is None:
            upper += max(0, 10 - (engine.elapsed_seconds - engine.round_start_seconds))
        state.update(minimum_seconds=duration_seconds, maximum_seconds=upper)
    actor.custom_conditions[STATE] = state
    engine.time_actors([actor])
    if duration_seconds == 0:
        clear(engine, actor, "GM 만료 지정")
