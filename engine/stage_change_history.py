"""Actual combat-stage events bounded by each actor's ordinary turns.

The source rows for Lash Out, Alluring Voice, and Burning Jealousy ask whether
stages changed after a particular turn boundary.  A current-stage snapshot is
not sufficient: a rise followed by a loss is still a rise.  This module keeps
the committed events and exposes narrow source predicates; declarations never
create evidence.
"""
from copy import deepcopy

import common_checks as C


KEY = "stage_change_history"
VERSION = 1
STATS = ("atk", "def", "spa", "spd", "spe")


def _scene(actor):
    import frequency as FREQ
    return FREQ.state(actor)["scene"]


def _blank():
    return {"version": VERSION, "sequence": 0, "rise_window": None,
            "loss_window": None}


def _state(actor, *, create=False):
    value = actor.spec.get(KEY)
    if value is None and create:
        value = _blank()
        actor.spec[KEY] = value
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " required")
    return value.strip()


def _window(value, direction, actor, engine=None):
    if value is None:
        return None
    required = {"id", "actor_id", "boundary", "round", "at", "scene",
                "stages", "events"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("stage history turn window shape changed")
    if value["actor_id"] != actor.entity_id or value["boundary"] != direction:
        raise ValueError("stage history turn window owner changed")
    _text(value["id"], "stage history window id")
    C.integer(value["round"], "stage history round", 0)
    C.integer(value["at"], "stage history time", 0)
    C.integer(value["scene"], "stage history scene", 0, _scene(actor))
    if engine is not None and (value["round"] > engine.round_no or
                               value["at"] > engine.elapsed_seconds):
        raise ValueError("stage history window is from the future")
    stages = value["stages"]
    if not isinstance(stages, dict) or set(stages) != set(STATS):
        raise ValueError("stage history requires five boundary stage values")
    for amount in stages.values():
        C.integer(amount, "stage history boundary value", -6, 6)
    if not isinstance(value["events"], list):
        raise ValueError("stage history events must be a list")
    previous = 0
    for event in value["events"]:
        expected = {"id", "window_id", "direction", "stat", "before", "after",
                    "requested_delta", "actual_delta", "round", "at",
                    "source_actor_id", "source_id"}
        if not isinstance(event, dict) or set(event) != expected:
            raise ValueError("stage history event shape changed")
        if event["window_id"] != value["id"] or event["direction"] != direction:
            raise ValueError("stage history event belongs to another window")
        number = C.integer(event["id"], "stage history event sequence", 1)
        if number <= previous:
            raise ValueError("stage history event sequence must increase")
        previous = number
        if event["stat"] not in STATS:
            raise ValueError("stage history event stat changed")
        before = C.integer(event["before"], "stage history before", -6, 6)
        after = C.integer(event["after"], "stage history after", -6, 6)
        requested = C.integer(event["requested_delta"], "requested stage delta")
        actual = C.integer(event["actual_delta"], "actual stage delta")
        if actual != after - before or actual == 0:
            raise ValueError("stage history actual delta changed")
        if direction == "rise" and actual <= 0 or direction == "loss" and actual >= 0:
            raise ValueError("stage history event direction changed")
        if requested == 0 or requested * actual <= 0:
            raise ValueError("stage history requested and committed directions disagree")
        C.integer(event["round"], "stage history event round", value["round"])
        C.integer(event["at"], "stage history event time", value["at"])
        if engine is not None and (event["round"] > engine.round_no or
                                   event["at"] > engine.elapsed_seconds):
            raise ValueError("stage history event is from the future")
        if event["source_actor_id"] is not None:
            _text(event["source_actor_id"], "stage source actor id")
        if event["source_id"] is not None:
            _text(event["source_id"], "stage source id")
    return value


def validate_actor(actor, engine=None):
    state = _state(actor)
    if state is None:
        return True
    if (not isinstance(state, dict) or set(state) !=
            {"version", "sequence", "rise_window", "loss_window"} or
            state["version"] != VERSION):
        raise ValueError("versioned stage change history required")
    C.integer(state["sequence"], "stage history sequence", 0)
    rise = _window(state["rise_window"], "rise", actor, engine)
    loss = _window(state["loss_window"], "loss", actor, engine)
    maximum = max((event["id"] for window in (rise, loss) if window
                   for event in window["events"]), default=0)
    if maximum > state["sequence"]:
        raise ValueError("stage history sequence trails an event")
    return True


def validate_world(engine, index):
    for actor in index.values():
        validate_actor(actor, engine)
        state = _state(actor)
        if state is None:
            continue
        for window in (state["rise_window"], state["loss_window"]):
            if window is None:
                continue
            for event in window["events"]:
                source = event["source_actor_id"]
                if source is not None and source not in index:
                    raise ValueError("stage history source actor is missing")
    return True


def _new_window(engine, actor, direction, sequence):
    return {"id": f"stage-window:{actor.entity_id}:{direction}:{sequence}",
            "actor_id": actor.entity_id, "boundary": direction,
            "round": engine.round_no, "at": engine.elapsed_seconds,
            "scene": _scene(actor),
            "stages": dict(actor.stages), "events": []}


def begin_turn(engine, actor):
    """Open the exact 'since this actor's last turn began' boundary."""
    validate_actor(actor, engine)
    state = deepcopy(_state(actor) or _blank())
    state["sequence"] += 1
    state["rise_window"] = _new_window(engine, actor, "rise", state["sequence"])
    actor.spec[KEY] = state
    validate_actor(actor, engine)
    return deepcopy(state["rise_window"])


def end_turn(engine, actor):
    """Open the exact 'since this actor's last turn ended' boundary."""
    validate_actor(actor, engine)
    state = deepcopy(_state(actor) or _blank())
    state["sequence"] += 1
    state["loss_window"] = _new_window(engine, actor, "loss", state["sequence"])
    actor.spec[KEY] = state
    validate_actor(actor, engine)
    return deepcopy(state["loss_window"])


def _source(engine):
    scopes = getattr(engine, "_event_use_scopes", ())
    if scopes:
        row = scopes[-1]
        actor = row.get("actor")
        return getattr(actor, "entity_id", None), row.get("move_id")
    stack = getattr(engine, "_native_action_stack", ())
    if stack:
        row = stack[-1]
        actor = row.get("actor")
        return getattr(actor, "entity_id", None), row.get("source")
    actor = getattr(engine, "_inflictor", None)
    if actor is not None and getattr(engine, "_active_turn_actor", None) is actor:
        return getattr(actor, "entity_id", None), None
    return None, None


def record(engine, actor, stat, before, after, *, requested_delta):
    """Record only an actual committed, non-zero stage change."""
    if stat not in STATS:
        raise ValueError("only five non-HP combat stages have history")
    C.integer(before, "stage history before", -6, 6)
    C.integer(after, "stage history after", -6, 6)
    C.integer(requested_delta, "requested stage delta")
    actual = after - before
    if actual == 0:
        return None
    validate_actor(actor, engine)
    state = deepcopy(_state(actor) or _blank())
    direction = "rise" if actual > 0 else "loss"
    window = state[direction + "_window"]
    if window is None:
        return None
    state["sequence"] += 1
    source_actor_id, source_id = _source(engine)
    event = {"id": state["sequence"], "window_id": window["id"],
             "direction": direction, "stat": stat, "before": before,
             "after": after, "requested_delta": requested_delta,
             "actual_delta": actual, "round": engine.round_no,
             "at": engine.elapsed_seconds, "source_actor_id": source_actor_id,
             "source_id": source_id}
    window["events"].append(event)
    actor.spec[KEY] = state
    validate_actor(actor, engine)
    return deepcopy(event)


def rises_since_turn_start(actor):
    validate_actor(actor)
    state = _state(actor)
    if (state is None or state["rise_window"] is None or
            state["rise_window"]["scene"] != _scene(actor)):
        return []
    return deepcopy(state["rise_window"]["events"])


def losses_since_turn_end(actor, *, external_only=False):
    validate_actor(actor)
    state = _state(actor)
    rows = ([] if state is None or state["loss_window"] is None or
            state["loss_window"]["scene"] != _scene(actor)
            else state["loss_window"]["events"])
    if external_only:
        rows = [event for event in rows
                if event["source_actor_id"] is not None and
                event["source_actor_id"] != actor.entity_id]
    return deepcopy(rows)

