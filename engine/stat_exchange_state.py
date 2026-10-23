"""Source-owned non-HP statistic exchanges with reversible lifetimes.

An exchange is a permutation, not an additive modifier.  The first live source
owns one baseline and every live source is replayed in installation order.  A
source can therefore expire while later exchanges remain without guessing an
inverse operation from the currently visible values.
"""
from copy import deepcopy


KEY = "stat_exchange_state"
HISTORY = "stat_exchange_history"
STATS = ("atk", "def", "spa", "spd", "spe")
BOUNDARIES = {
    "scene_end or switch or faint": ("scene_end", "switch", "faint"),
    "encounter_end or faint or switch": ("encounter_end", "faint", "switch"),
}


def _integer(value, label):
    if type(value) is not int or value < 1:
        raise ValueError(label + " must be a positive whole statistic")
    return value


def pairs(value):
    if not isinstance(value, list) or not value:
        raise ValueError("stat exchange requires at least one explicit pair")
    result = []
    used = set()
    for pair in value:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("each stat exchange pair requires exactly two statistics")
        left, right = pair
        if left not in STATS or right not in STATS or left == right:
            raise ValueError("stat exchange pairs require two distinct non-HP statistics")
        if left in used or right in used:
            raise ValueError("one exchange cannot reuse a statistic in multiple pairs")
        used.update((left, right))
        result.append([left, right])
    return result


def _declared_effect(engine, source, effect):
    """Bind an executable exchange to the selected Move declaration."""
    if source not in engine.r.moves:
        raise ValueError("timed statistic exchange requires an actual selected Move source")
    mechanics, _ = engine.r.move_mech(source)
    declarations = mechanics.get("effects_exec", [])
    semantic = {key: deepcopy(value) for key, value in effect.items() if not key.startswith("_")}
    matches = [row for row in declarations
               if isinstance(row, dict)
               and {key: value for key, value in row.items() if not key.startswith("_")} == semantic]
    if len(matches) != 1:
        raise ValueError("timed statistic exchange differs from its selected Move declaration")
    return semantic


def prepare(engine, actor, target, effect, source):
    if target is not actor or effect.get("on") != "self":
        raise ValueError("timed statistic exchange requires its actual self recipient")
    raw = effect.get("until")
    if raw not in BOUNDARIES:
        raise ValueError("statistic exchange requires a reviewed restoration boundary")
    operation = pairs(effect.get("swap_stats"))
    _declared_effect(engine, source, effect)
    record = {
        "source": source,
        "effect_contract": True,
        "timing_text": raw,
        "stat_exchange": {
            "pairs": operation,
            "boundaries": list(BOUNDARIES[raw]),
        },
    }
    record["scene_end" if "scene_end" in BOUNDARIES[raw] else "encounter_end"] = True
    return record


def _exchange_records(actor, *, excluding=None):
    import combat_timing as TIMING
    return [record for record in TIMING.records(actor)
            if record is not excluding and "stat_exchange" in record]


def _operation(record):
    operation = record.get("stat_exchange")
    raw = record.get("timing_text")
    if (record.get("effect_contract") is not True or raw not in BOUNDARIES
            or not isinstance(record.get("source"), str) or not record["source"]):
        raise ValueError("active stat exchange lost its source-owned lifetime")
    if not isinstance(operation, dict) or set(operation) != {"pairs", "boundaries"}:
        raise ValueError("active stat exchange needs one typed operation and boundary set")
    if tuple(operation["boundaries"]) != BOUNDARIES[raw]:
        raise ValueError("active stat exchange boundary differs from its declaration")
    end_key = "scene_end" if "scene_end" in BOUNDARIES[raw] else "encounter_end"
    other_key = "encounter_end" if end_key == "scene_end" else "scene_end"
    if record.get(end_key) is not True or record.get(other_key):
        raise ValueError("active stat exchange has the wrong shared timer boundary")
    return pairs(operation["pairs"])


def _projection(baseline, records):
    if set(baseline) != set(STATS):
        raise ValueError("stat exchange baseline must contain all five non-HP statistics")
    visible = {stat: _integer(baseline[stat], "stat exchange baseline " + stat) for stat in STATS}
    for record in records:
        for left, right in _operation(record):
            visible[left], visible[right] = visible[right], visible[left]
    return visible


def active(actor):
    return KEY in actor.custom_conditions or bool(_exchange_records(actor))


def prepare_install(actor, record):
    current = {stat: _integer(actor.stats[stat], "current " + stat) for stat in STATS}
    live = _exchange_records(actor)
    state = actor.custom_conditions.get(KEY)
    if state is None:
        if live:
            raise ValueError("live statistic exchange has no common baseline")
        baseline = current
    else:
        _validate_state(actor, state, live)
        baseline = deepcopy(state["baseline"])
    visible = _projection(baseline, [*live, record])
    return {"baseline": baseline, "visible": visible}


def commit_install(actor, plan):
    actor.custom_conditions[KEY] = {
        "version": 1,
        "baseline": deepcopy(plan["baseline"]),
        "visible": deepcopy(plan["visible"]),
    }
    actor.stats.update(plan["visible"])


def prepare_expire(actor, record):
    state = actor.custom_conditions.get(KEY)
    if state is None:
        raise ValueError("expiring statistic exchange has no common baseline")
    history = actor.custom_conditions.get(HISTORY, [])
    if not isinstance(history, list):
        raise ValueError("statistic exchange history must be a list")
    validate_actor(actor)
    remaining = _exchange_records(actor, excluding=record)
    # Replay the actual timer order after removing this source.
    return {
        "baseline": deepcopy(state["baseline"]),
        "visible": _projection(state["baseline"], remaining),
        "remaining": remaining,
    }


def commit_expire(actor, record, plan, *, ending, event):
    actor.stats.update(plan["visible"])
    if plan["remaining"]:
        actor.custom_conditions[KEY] = {
            "version": 1,
            "baseline": deepcopy(plan["baseline"]),
            "visible": deepcopy(plan["visible"]),
        }
    else:
        actor.custom_conditions.pop(KEY, None)
    operation = record["stat_exchange"]
    actor.custom_conditions.setdefault(HISTORY, []).append({
        "source": record["source"],
        "effect_occurrence": record.get("effect_occurrence"),
        "effect_receipt": record.get("effect_receipt"),
        "pairs": deepcopy(operation["pairs"]),
        "until": record["timing_text"],
        "ending": ending,
        "event": deepcopy(event),
    })


def end_event(engine, actor, event):
    if event not in ("switch", "faint"):
        raise ValueError("stat exchange event must be switch or faint")
    preflight_boundary(actor, event)
    import combat_timing as TIMING
    for record in list(TIMING.records(actor)):
        operation = record.get("stat_exchange")
        if operation and event in operation.get("boundaries", ()):
            TIMING.expire(engine, actor, record, ending=event, event={"kind": event})


def preflight_boundary(actor, event):
    """Validate every live exchange before a boundary mutates any of them."""
    if event not in ("switch", "faint", "encounter_end", "scene_end"):
        raise ValueError("unknown statistic exchange boundary")
    validate_actor(actor)
    history = actor.custom_conditions.get(HISTORY, [])
    if not isinstance(history, list):
        raise ValueError("statistic exchange history must be a list")
    for record in _exchange_records(actor):
        operation = record["stat_exchange"]
        if event in operation["boundaries"]:
            _operation(record)
    return True


def preflight_actors(actors, event):
    for actor in actors:
        preflight_boundary(actor, event)
    return True


def _validate_state(actor, state, live):
    if not isinstance(state, dict) or set(state) != {"version", "baseline", "visible"} or state["version"] != 1:
        raise ValueError("invalid statistic exchange state")
    baseline = state["baseline"]
    visible = state["visible"]
    if not isinstance(baseline, dict) or not isinstance(visible, dict):
        raise ValueError("statistic exchange baseline and projection must be mappings")
    expected = _projection(baseline, live)
    if visible != expected or any(actor.stats[stat] != expected[stat] for stat in STATS):
        raise ValueError("visible statistics diverged from active exchange sources")
    return state


def validate_actor(actor):
    live = _exchange_records(actor)
    state = actor.custom_conditions.get(KEY)
    if not live:
        if state is not None:
            raise ValueError("statistic exchange state remains without an active source")
        return True
    if state is None:
        raise ValueError("active statistic exchange has no common baseline")
    _validate_state(actor, state, live)
    return True


def _validate_receipt(engine, actor, row, *, source, occurrence, receipt, pairs_value, until):
    import effect_contracts as CONTRACTS
    if not row or row.get("status") != "completed":
        raise ValueError("statistic exchange needs a completed native effect receipt")
    effect = row.get("effect")
    CONTRACTS.validate_receipt(engine, receipt, source, occurrence,
                               row["actor"], row["target"], effect)
    if actor is not row["actor"] or actor not in CONTRACTS.recipients(row["actor"], row["target"], effect):
        raise ValueError("statistic exchange recipient differs from its receipt")
    if (effect.get("type") != "swap_stats" or pairs(effect.get("swap_stats")) != pairs_value
            or effect.get("until") != until or effect.get("on") != "self"):
        raise ValueError("statistic exchange receipt carries a different operation")
    _declared_effect(engine, source, effect)


def validate_world(engine, index):
    receipts = getattr(engine, "_effect_dispatch_receipts", {})
    for actor in index.values():
        validate_actor(actor)
        for record in _exchange_records(actor):
            operation = record["stat_exchange"]
            _validate_receipt(engine, actor, receipts.get(record.get("effect_receipt")),
                              source=record.get("source"),
                              occurrence=record.get("effect_occurrence"),
                              receipt=record.get("effect_receipt"),
                              pairs_value=operation["pairs"], until=record.get("timing_text"))
        history = actor.custom_conditions.get(HISTORY, [])
        if not isinstance(history, list):
            raise ValueError("statistic exchange history must be a list")
        for entry in history:
            required = {"source", "effect_occurrence", "effect_receipt", "pairs", "until", "ending", "event"}
            if not isinstance(entry, dict) or set(entry) != required:
                raise ValueError("invalid statistic exchange history entry")
            if entry["ending"] not in ("switch", "faint", "expired"):
                raise ValueError("invalid statistic exchange ending")
            if not isinstance(entry["event"], dict) or not isinstance(entry["event"].get("kind"), str):
                raise ValueError("statistic exchange history needs its actual ending event")
            _validate_receipt(engine, actor, receipts.get(entry["effect_receipt"]),
                              source=entry["source"], occurrence=entry["effect_occurrence"],
                              receipt=entry["effect_receipt"], pairs_value=pairs(entry["pairs"]),
                              until=entry["until"])
    return True
