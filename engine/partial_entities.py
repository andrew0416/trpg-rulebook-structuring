"""Observed incomplete NPCs and HP-only weak parts, without fabricated stats.

Core ch11:1622-1637 permits minimal NPC sheets; ch11:2371-2375 permits
weak parts with HP alone. Observations do not certify creation rights or
supply a damage/action algorithm for an incomplete sheet.
"""
from copy import deepcopy
from functools import wraps
from types import SimpleNamespace
from uuid import uuid4
import state_fields as F
import world_entities as W

FIELDS = {"level", "stats", "skills", "hp", "max_hp", "species", "description",
          "features", "edges", "moves", "abilities", "types"}
KINDS = {"partial_npc", "weak_part"}

def _registry(e):
    value = getattr(e, "_partial_entities", {})
    if not isinstance(value, dict):
        raise ValueError("partial entity registry must be a mapping")
    return value

def _other_entities(e):
    """Read every other native store through the shared identity owner."""
    partials = _registry(e)
    return {uid: row for uid, row in W.entity_index(e).items() if uid not in partials}

def validate_row(e, row):
    if not isinstance(row, dict) or row.get("kind") not in KINDS:
        raise ValueError("explicit partial entity record required")
    W._text(row.get("entity_id"), "partial entity identity")
    W._text(row.get("name"), "partial entity name")
    W._text(row.get("provenance", {}).get("reason"), "partial entity observation reason")
    F.location(row.get("location"))
    if row.get("actor_kind") not in ("trainer", "pokemon", "object"):
        raise ValueError("observed actor kind required")
    known = row.get("known")
    if not isinstance(known, dict) or not set(known) <= FIELDS:
        raise ValueError("unsupported partial entity facts")
    if any(value is None for value in known.values()):
        raise ValueError("omit unknown facts instead of inventing a value")
    if "level" in known:
        if row["actor_kind"] == "object":
            raise ValueError("an object does not have an inferred character level")
        F.integer(known["level"], "observed level", 1, 50 if row["actor_kind"] == "trainer" else 100)
    if "stats" in known:
        if not isinstance(known["stats"], dict) or not set(known["stats"]) <= set(F.STATS):
            raise ValueError("known stats must be an explicit subset of the six stats")
        for key, value in known["stats"].items():
            F.integer(value, "known stat " + key, 0 if key == "hp" else 1)
    if "skills" in known:
        import skill_modifiers as SKILL
        if not isinstance(known["skills"], dict):
            raise ValueError("known skills must be a mapping")
        for key in known["skills"]:
            SKILL.skill_id(e.r.skill_policy, key, required=True)
            SKILL.rank(e.r, SimpleNamespace(kind=row["actor_kind"], spec={"skills":known["skills"]}), key)
    if "hp" in known:F.integer(known["hp"], "observed HP")
    if "max_hp" in known:
        F.integer(known["max_hp"], "observed maximum HP", 1)
        if known.get("hp", known["max_hp"]) > known["max_hp"]:
            raise ValueError("observed HP exceeds observed maximum")
    for key in ("species", "description"):
        if key in known:W._text(known[key], key)
    for key in ("features", "edges", "moves", "abilities", "types"):
        if key in known:
            if not isinstance(known[key], list):raise ValueError(key + " must be observed names")
            for value in known[key]:W._text(value, key)
    if row["kind"] == "weak_part":
        if "hp" not in known:raise ValueError("an HP-only weak part needs observed HP")
        W._text(row.get("parent_id"), "weak part parent")
        if row["parent_id"] == row["entity_id"]:raise ValueError("a part cannot be its own parent")
    elif row.get("parent_id") is not None:
        raise ValueError("partial NPC membership is not an inferred weak-part relationship")
    return True

def validate_world(e):
    registry = _registry(e)
    others = _other_entities(e)
    for uid, row in registry.items():
        validate_row(e, row)
        if uid != row["entity_id"] or uid in others:
            raise ValueError("partial entity identity collides with another actual entity")
        if row["kind"] == "weak_part":
            parent = others.get(row["parent_id"], registry.get(row["parent_id"]))
            if parent is None or isinstance(parent, dict) and parent.get("kind") == "weak_part":
                raise ValueError("weak part must resolve to an actual parent body")
    return True

def observe(e, *, name, actor_kind, known=None, location=None, reason, entity_id=None, parent_id=None):
    """Create a minimal observed sheet. Missing facts stay unknown."""
    validate_world(e)
    uid = entity_id or "entity/" + str(uuid4())
    if uid in _registry(e) or uid in _other_entities(e):
        raise ValueError("entity identity already exists")
    row = {"entity_id":uid, "kind":"weak_part" if parent_id is not None else "partial_npc",
           "name":name, "actor_kind":actor_kind, "known":deepcopy({} if known is None else known),
           "location":F.location({"kind":"unknown"} if location is None else location), "parent_id":parent_id,
           "provenance":{"kind":"gm_observation", "reason":reason,
                         "source":"C2CORE-HP-ONLY-WEAK-PART" if parent_id is not None else "C2CORE-PARTIAL-NPC-SHEET"},
           "revision":0}
    validate_row(e, row)
    if parent_id is not None:
        parent = _other_entities(e).get(parent_id, _registry(e).get(parent_id))
        if parent is None or isinstance(parent, dict) and parent.get("kind") == "weak_part":
            raise ValueError("weak part requires an actual parent body")
    e.__dict__.setdefault("_partial_entities", {})[uid] = row
    e.gm._rec("partial entity", None, row, reason)
    return project(e, uid)

def project(e, uid):
    validate_world(e)
    row = deepcopy(_registry(e)[uid])
    row["combatant"] = False
    row["unknown_fields"] = sorted(FIELDS - set(row["known"]))
    row["ordinary_combat_eligible"] = False
    if row["kind"] == "weak_part":row["destroyed"] = row["known"]["hp"] <= 0
    return row

def skill(e, uid, name):
    """Return an observed rank; never default a missing skill to Untrained."""
    import skill_modifiers as SKILL
    row = project(e, uid)
    values = row["known"].get("skills", {})
    key = SKILL.skill_id(e.r.skill_policy, name, required=True)
    if not any(SKILL.skill_id(e.r.skill_policy, value) == key for value in values):return None
    return SKILL.rank(e.r, SimpleNamespace(kind=row["actor_kind"], spec={"skills":values}), name)

def update(e, uid, *, facts, reason):
    W._text(reason, "partial fact update reason")
    validate_world(e)
    row = _registry(e)[uid]
    candidate = deepcopy(row)
    if not isinstance(facts, dict) or not facts:raise ValueError("explicit observed facts required")
    candidate["known"].update(deepcopy(facts))
    validate_row(e, candidate)
    before = deepcopy(row)
    row["known"].update(deepcopy(facts))
    row["revision"] += 1
    row["provenance"]["reason"] = reason
    e.gm._rec("partial entity facts", before, row, reason)
    return project(e, uid)

def require_complete(value, operation):
    if isinstance(value, dict) and value.get("kind") in KINDS:
        raise ValueError(operation + " needs a complete combat actor or an explicit HP-only-part adapter; missing stats are unknown")


def complete_move(fn):
    """Reject incomplete sheets before feature decorators inspect or stage them."""
    @wraps(fn)
    def run(engine, actor, target, *args, **kwargs):
        require_complete(actor, fn.__name__)
        if isinstance(target, dict) and target.get("kind") in KINDS:
            from inspect import signature
            field = signature(fn).bind(engine, actor, target, *args, **kwargs).arguments.get("_field_activation")
            if field is None:
                require_complete(target, fn.__name__ + " target")
        return fn(engine, actor, target, *args, **kwargs)
    return run

