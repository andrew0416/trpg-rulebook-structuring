"""Scene-limited post-resolution effects driven by actual stage-rise history."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json


KEY = "post_resolution_stage_effects"
POLICY_FILE = "data/post-resolution-stage-effect-policy.json"


def _path(rules):
    staged = Path(__file__).resolve().parents[1] / POLICY_FILE
    return staged if staged.exists() else Path(rules.root) / POLICY_FILE


def policy(rules):
    data = json.loads(_path(rules).read_text(encoding="utf-8"))
    if (data.get("schema_version") != 1 or
            data.get("contract") != "post_resolution_stage_rise_area_status"):
        raise ValueError("post-resolution stage effect policy identity changed")
    for name, digest in data.get("source_files", {}).items():
        if hashlib.sha256((Path(rules.root) / name).read_bytes()).hexdigest() != digest:
            raise ValueError("post-resolution stage effect source changed: " + name)
    rows = data.get("moves")
    if not isinstance(rows, dict) or set(rows) != {"move/매혹의보이스", "move/질투의불꽃"}:
        raise ValueError("post-resolution stage effect boundary changed")
    return data


def definition(rules, move_id):
    row = policy(rules)["moves"].get(move_id)
    if row is None:
        return None
    if rules._selected_rule(move_id) != move_id:
        raise ValueError("selected post-resolution Move source changed")
    move = rules.move(move_id)
    mechanics = rules.move_mech(move_id)[0]
    actual = [{key: value for key, value in effect.items() if key != "_src"}
              for effect in mechanics.get("effects_exec", [])]
    expected = [{"type": "conditional_area_status", "status": row["status"],
                 "targets": row["targets"], "limit": "scene x1"}]
    if move.get("effect") != row["source_effect"] or actual != expected:
        raise ValueError("post-resolution Move definition changed from reviewed source")
    return row


def owns(rules, move, effect):
    if not isinstance(move, dict) or not isinstance(effect, dict):
        return False
    row = definition(rules, move.get("id")) if move.get("id") in policy(rules)["moves"] else None
    return bool(row and effect == {"type": "conditional_area_status",
        "status": row["status"], "targets": row["targets"], "limit": "scene x1"})


def _scene(actor):
    import frequency as FREQ
    return FREQ.state(actor)["scene"]


def _history(actor):
    state = actor.spec.get(KEY)
    return [] if state is None else state.get("history", [])


def validate_actor(actor):
    state = actor.spec.get(KEY)
    if state is None:
        return True
    if (not isinstance(state, dict) or set(state) != {"version", "history"}
            or state["version"] != 1 or not isinstance(state["history"], list)):
        raise ValueError("versioned post-resolution stage effect history required")
    seen = set()
    for record in state["history"]:
        required = {"id", "actor_id", "move_id", "clause_id", "source_row_sha256",
                    "scene", "selected_at", "reason", "use"}
        if not isinstance(record, dict) or set(record) != required:
            raise ValueError("post-resolution stage effect record shape changed")
        row = definition(actor.r, record.get("move_id"))
        if (row is None or record["actor_id"] != actor.entity_id or
                record["clause_id"] != row["clause_id"] or
                record["source_row_sha256"] != row["source_row_sha256"]):
            raise ValueError("post-resolution stage effect provenance changed")
        if type(record["scene"]) is not int or not 0 <= record["scene"] <= _scene(actor):
            raise ValueError("post-resolution stage effect scene changed")
        if type(record["selected_at"]) is not int or record["selected_at"] < 0:
            raise ValueError("post-resolution stage effect selection time changed")
        if not isinstance(record["reason"], str) or not record["reason"].strip():
            raise ValueError("post-resolution stage effect selection reason required")
        identity = (record["move_id"], record["scene"])
        if identity in seen:
            raise ValueError("post-resolution stage effect can be selected once per Move per scene")
        seen.add(identity)
        use = record["use"]
        if use is None:
            continue
        needed = {"completion_id", "move_id", "scene", "at", "eligible_target_ids",
                  "applied_target_ids", "status", "stage_event_ids"}
        if not isinstance(use, dict) or set(use) != needed:
            raise ValueError("post-resolution stage effect use receipt changed")
        if use["move_id"] != record["move_id"] or use["scene"] != record["scene"]:
            raise ValueError("post-resolution stage effect was used by another activation")
        if type(use["at"]) is not int or use["at"] < record["selected_at"]:
            raise ValueError("post-resolution stage effect use time changed")
        if (not isinstance(use["eligible_target_ids"], list) or
                not use["eligible_target_ids"] or
                len(set(use["eligible_target_ids"])) != len(use["eligible_target_ids"]) or
                not set(use["applied_target_ids"]) <= set(use["eligible_target_ids"])):
            raise ValueError("post-resolution stage effect target evidence changed")
        if not isinstance(use["stage_event_ids"], dict) or set(use["stage_event_ids"]) != set(use["eligible_target_ids"]):
            raise ValueError("post-resolution stage effect history evidence changed")
        for target_id, event_ids in use["stage_event_ids"].items():
            if not isinstance(target_id, str) or not isinstance(event_ids, list) or not event_ids:
                raise ValueError("post-resolution stage effect needs actual rise events")
        if use["status"] != row["status"]:
            raise ValueError("post-resolution stage effect status changed")
    return True


def validate_world(engine, index):
    import stage_change_history as STAGES
    STAGES.validate_world(engine, index)
    completions = getattr(engine, "_move_completions", {})
    for actor in index.values():
        validate_actor(actor)
        for record in _history(actor):
            use = record["use"]
            if use is None:
                continue
            if use["at"] > engine.elapsed_seconds:
                raise ValueError("post-resolution stage effect use is from the future")
            if use["completion_id"] not in completions:
                raise ValueError("post-resolution stage effect completion is missing")
            if any(target_id not in index for target_id in use["eligible_target_ids"]):
                raise ValueError("post-resolution stage effect target is missing")
    return True


def choose(engine, actor, move_id, *, reason):
    import world_entities as WORLD
    WORLD.require_actors(engine, actor)
    validate_actor(actor)
    mid = engine.r.move_id(move_id)
    row = definition(engine.r, mid)
    if row is None:
        raise ValueError("Move has no reviewed post-resolution stage effect")
    if mid not in actor.moves:
        raise ValueError("actor must currently know the selected Move")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("selection reason required")
    scene = _scene(actor)
    if any(record["move_id"] == mid and record["scene"] == scene
           for record in _history(actor)):
        raise ValueError("post-resolution stage effect already selected or used this scene")
    state = deepcopy(actor.spec.get(KEY, {"version": 1, "history": []}))
    record = {"id": f"post-stage:{actor.entity_id}:{mid}:{scene}",
              "actor_id": actor.entity_id, "move_id": mid,
              "clause_id": row["clause_id"],
              "source_row_sha256": row["source_row_sha256"], "scene": scene,
              "selected_at": engine.elapsed_seconds, "reason": reason.strip(),
              "use": None}
    state["history"].append(record)
    actor.spec[KEY] = state
    validate_actor(actor)
    engine.log(f"    {engine.r.move(mid)['name']}: 전투단계 상승 적 후처리 선택", mid)
    return deepcopy(record)


def _pending(actor, move_id):
    scene = _scene(actor)
    return next((record for record in _history(actor)
                 if record["move_id"] == move_id and record["scene"] == scene
                 and record["use"] is None), None)


def apply_completion(engine, completion, effects):
    """Consume one choice at the authenticated all-target completion boundary."""
    move = completion["move"]
    owned = [effect for effect in effects if owns(engine.r, move, effect)]
    if not owned:
        return []
    if len(owned) != 1:
        raise ValueError("one reviewed post-resolution stage effect required")
    actor = completion["actor"]
    validate_actor(actor)
    record = _pending(actor, move["id"])
    if record is None:
        return []
    if (not completion.get("sealed") or completion.get("phase") != "applying" or
            any(target.entity_id not in completion["results"] for target in completion["targets"]) or
            all(result["cancelled"] for result in completion["results"].values())):
        raise ValueError("actual completed Move activation required")
    import stage_change_history as STAGES
    import world_entities as WORLD
    from grid import cheb
    index = WORLD.actor_index(engine)
    row = definition(engine.r, move["id"])
    eligible = []
    evidence = {}
    for target in index.values():
        if (target is actor or target.fainted or not target.on_field or target.captured or
                getattr(target, "side", None) is None or getattr(actor, "side", None) is None or
                target.side == actor.side):
            continue
        if engine.grid is None or cheb(actor.pos, target.pos) > row["radius"]:
            continue
        events = STAGES.rises_since_turn_start(target)
        if not events:
            continue
        eligible.append(target)
        evidence[target.entity_id] = [event["id"] for event in events]
    if not eligible:
        return []
    effect = owned[0]
    # Every target and condition is checked before the first mutation.
    import condition_instances as CONDITIONS
    for target in eligible:
        if effect["status"] in CONDITIONS.SUPPORTED:
            CONDITIONS.prepare(engine, target, effect["status"], applied_by=actor)
    applied = []
    for target in eligible:
        if engine.apply_status(target, effect["status"], source=move["id"], applied_by=actor):
            applied.append(target.entity_id)
    record["use"] = {"completion_id": completion["id"], "move_id": move["id"],
                     "scene": _scene(actor), "at": engine.elapsed_seconds,
                     "eligible_target_ids": [target.entity_id for target in eligible],
                     "applied_target_ids": applied, "status": effect["status"],
                     "stage_event_ids": evidence}
    validate_actor(actor)
    engine.log(f"    {move['name']} 후처리: {effect['status']} → " +
               ", ".join(target.name for target in eligible), move["id"])
    return deepcopy(record["use"])

