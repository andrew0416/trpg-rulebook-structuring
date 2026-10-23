"""Selected campaign variants for injury and death (ch07:706-708, 736-738).

The base rules remain the default.  A campaign may instead suppress injuries,
use the optional location injury stages, independently disable death, and let
Pokemon Center treatment remove every injury admitted that day.  The selected
policy is owned by the engine; per-injury location records are owned by the
injured actor and end only when an actual injury is removed.
"""
from copy import deepcopy

SOURCE_LOCALIZED = "ch07-combat/선택-규칙-부상-위치"
SOURCE_CAMPAIGN = "ch07-combat/부상과-죽음의-조정"
ACTIVE = "localized_injuries"
HISTORY = "localized_injury_history"

_STATS = ("atk", "def", "spa", "spd", "spe")
_LOCATIONS = {
    "atk": "팔/전지",
    "def": "몸통",
    "spa": "머리/감각기관",
    "spd": "내부기관",
    "spe": "다리/후지",
}
_INJURY_MODES = ("core", "disabled", "localized")
_RECOVERY_ORDERS = ("oldest_first", "newest_first")


def _selected(engine):
    row = getattr(engine, "_campaign_injury_policy", None)
    if row is None:
        return {
            "source": SOURCE_CAMPAIGN,
            "injury_mode": "core",
            "death_enabled": engine.death_enabled,
            "center_heals_all": False,
            "taskmaster_exempt": False,
            "recovery_order": "oldest_first",
            "revision": 0,
            "reason": "engine base policy",
        }
    validate_policy(row)
    return row


def policy(engine):
    """Return a defensive view of the selected campaign policy."""
    return deepcopy(_selected(engine))


def _actors(engine):
    rows = []
    seen = set()
    for actor in list(getattr(engine, "everyone", [])) + list(getattr(getattr(engine, "gm", None), "everyone", [])):
        if id(actor) not in seen:
            seen.add(id(actor)); rows.append(actor)
    return rows


def configure(engine, *, injury_mode, death_enabled, center_heals_all,
              taskmaster_exempt=False, recovery_order="oldest_first", reason):
    """Select all campaign switches explicitly and atomically.

    Changing injury models after actors already carry injuries would invent or
    discard location identity.  Such a conversion needs a separate GM ruling,
    so this selector rejects it rather than silently fabricating records.
    """
    if injury_mode not in _INJURY_MODES:
        raise ValueError("unknown campaign injury mode")
    if type(death_enabled) is not bool or type(center_heals_all) is not bool or type(taskmaster_exempt) is not bool:
        raise ValueError("campaign injury/death switches must be explicit booleans")
    if recovery_order not in _RECOVERY_ORDERS:
        raise ValueError("unknown localized injury recovery order")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("campaign injury/death policy reason required")
    previous = getattr(engine, "_campaign_injury_policy", None)
    if (previous is None and injury_mode != "core") or (previous is not None and previous["injury_mode"] != injury_mode):
        if any(getattr(actor, "injuries", 0) or actor.spec.get(ACTIVE) for actor in _actors(engine)):
            raise ValueError("changing injury models with existing injuries needs an explicit conversion ruling")
    revision = 1 if previous is None else previous["revision"] + 1
    row = {
        "source": SOURCE_CAMPAIGN,
        "injury_mode": injury_mode,
        "death_enabled": death_enabled,
        "center_heals_all": center_heals_all,
        "taskmaster_exempt": taskmaster_exempt,
        "recovery_order": recovery_order,
        "revision": revision,
        "reason": reason.strip(),
    }
    validate_policy(row)
    engine._campaign_injury_policy = row
    engine.death_enabled = death_enabled
    return policy(engine)


def validate_policy(row):
    if not isinstance(row, dict) or row.get("source") != SOURCE_CAMPAIGN:
        raise ValueError("campaign injury policy source required")
    if row.get("injury_mode") not in _INJURY_MODES:
        raise ValueError("unknown campaign injury mode")
    for key in ("death_enabled", "center_heals_all", "taskmaster_exempt"):
        if type(row.get(key)) is not bool:
            raise ValueError("campaign policy switch must be boolean: " + key)
    if row.get("recovery_order") not in _RECOVERY_ORDERS:
        raise ValueError("unknown localized injury recovery order")
    if type(row.get("revision")) is not int or row["revision"] < 1:
        raise ValueError("campaign injury policy revision required")
    if not isinstance(row.get("reason"), str) or not row["reason"].strip():
        raise ValueError("campaign injury policy reason required")


def validate_actor(actor):
    rows = actor.spec.get(ACTIVE, [])
    history = actor.spec.get(HISTORY, [])
    if not isinstance(rows, list) or not isinstance(history, list):
        raise ValueError("localized injury records must be lists")
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("source") != SOURCE_LOCALIZED:
            raise ValueError("localized injury source required")
        if row.get("stat") not in _STATS or row.get("location") != _LOCATIONS[row["stat"]]:
            raise ValueError("localized injury stat/location mismatch")
        if type(row.get("sequence")) is not int or row["sequence"] < 1 or row["sequence"] in ids:
            raise ValueError("localized injury sequence must be unique")
        ids.add(row["sequence"])
        if not isinstance(row.get("injury_source"), str) or not row["injury_source"]:
            raise ValueError("localized injury producer required")
    for row in history:
        if not isinstance(row, dict):
            raise ValueError("localized injury history receipt invalid")
        if row.get("source") == SOURCE_LOCALIZED and row.get("status") in ("healed", "taskmaster_exempt"):
            continue
        if row.get("source") == SOURCE_CAMPAIGN and row.get("status") == "campaign_injury_disabled":
            continue
        raise ValueError("localized injury history receipt invalid")
    return rows


def _taskmaster(source):
    value = source.casefold()
    return "taskmaster" in value or "감독관" in value


def injury_added(engine, actor, amount, source):
    """Observe injuries after their producer incremented ``actor.injuries``.

    Returns the injury count retained by the selected campaign rules.
    """
    if type(amount) is not int or not isinstance(source, str) or not source:
        raise ValueError("actual integral injury change and source required")
    selected = _selected(engine)
    validate_actor(actor)
    if amount <= 0:
        if amount < 0:
            injuries_healed(engine, actor, -amount, source)
        return amount
    if selected["injury_mode"] == "disabled":
        actor.injuries = max(0, actor.injuries - amount)
        actor.spec.setdefault(HISTORY, []).append({
            "source": SOURCE_CAMPAIGN, "status": "campaign_injury_disabled",
            "injury_source": source, "count": amount,
            "at": engine.elapsed_seconds,
        })
        return 0
    if selected["injury_mode"] != "localized":
        return amount
    active = actor.spec.setdefault(ACTIVE, [])
    history = actor.spec.setdefault(HISTORY, [])
    next_sequence = max((row["sequence"] for row in active), default=0)
    next_sequence = max(next_sequence, max((row.get("sequence", 0) for row in history), default=0))
    for _ in range(amount):
        next_sequence += 1
        if selected["taskmaster_exempt"] and _taskmaster(source):
            history.append({
                "source": SOURCE_LOCALIZED, "status": "taskmaster_exempt",
                "sequence": next_sequence, "injury_source": source,
                "at": engine.elapsed_seconds,
            })
            continue
        stat = engine.rng.choice(_STATS)
        active.append({
            "source": SOURCE_LOCALIZED, "sequence": next_sequence,
            "injury_source": source, "stat": stat,
            "location": _LOCATIONS[stat], "started_at": engine.elapsed_seconds,
        })
    validate_actor(actor)
    return amount


def injuries_healed(engine, actor, count, source):
    if type(count) is not int or count < 0 or not isinstance(source, str) or not source:
        raise ValueError("actual healed injury count and source required")
    selected = _selected(engine)
    active = validate_actor(actor)
    if not count or not active:
        return ()
    ordered = active if selected["recovery_order"] == "oldest_first" else list(reversed(active))
    removed = ordered[:count]
    removed_ids = {row["sequence"] for row in removed}
    actor.spec[ACTIVE] = [row for row in active if row["sequence"] not in removed_ids]
    for row in removed:
        receipt = dict(row)
        receipt.update(status="healed", healed_by=source, ended_at=engine.elapsed_seconds)
        actor.spec.setdefault(HISTORY, []).append(receipt)
    validate_actor(actor)
    return tuple(sorted(removed_ids))


def stage_penalty(actor, stat):
    if stat not in _STATS:
        return 0
    return -sum(1 for row in validate_actor(actor) if row["stat"] == stat)


def enforce(engine, actor):
    """Catch injury producers that reach a life boundary without the notifier."""
    selected = _selected(engine)
    if selected["injury_mode"] == "disabled" and actor.injuries:
        count = actor.injuries
        actor.injuries = 0
        actor.spec.pop(ACTIVE, None)
        actor.spec.setdefault(HISTORY, []).append({
            "source": SOURCE_CAMPAIGN, "status": "campaign_injury_disabled",
            "injury_source": "life-boundary", "count": count,
            "at": engine.elapsed_seconds,
        })
    validate_actor(actor)


def healing_limit(engine, actor, *, source, core_limit, spent):
    if type(core_limit) is not int or type(spent) is not int:
        raise ValueError("integral injury healing allowance required")
    selected = _selected(engine)
    if source == "pokemon_center" and selected["center_heals_all"]:
        return spent + actor.injuries
    return core_limit
