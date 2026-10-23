"""Optional Baby Template as one source-owned Pokemon growth contract.

The source fixes the stat/Skill/Capability changes and the fifth-level recovery
boundary, but does not fix how much height or weight is regained at a boundary.
Those physical changes therefore stay as explicit GM observations instead of
being replaced by an invented percentage.
"""
from copy import deepcopy
from math import isfinite

import state_fields as F

KEY = "baby_template"
SOURCE = "optional/baby-template"
SOURCE_LINES = ("input/ch05-pokemon.md:674-680",
                "input/ch11-running-the-game.md:2515-2522")
CLAUSES = ("C05-151", "C05-152", "C05-153", "C05-154",
           "C11-148", "C11-149", "C11-150")
STAT_SOURCE = SOURCE + "/base-stat-reduction"


def _fraction(value, name):
    if isinstance(value, bool) or type(value) not in (int, float) or not isfinite(value):
        raise ValueError(name + " must be a finite reduction fraction")
    value = float(value)
    if not 0 <= value <= .5:
        raise ValueError(name + " must be between 0 and 0.5")
    return value


def _measurement(value, name):
    if value is None:
        return None
    if isinstance(value, bool) or type(value) not in (int, float) or not isfinite(value) or value <= 0:
        raise ValueError("actual positive " + name + " required")
    return float(value)


def _record(spec):
    row = spec.get(KEY)
    if row is None:
        return None
    fields = {
        "source", "source_lines", "clauses", "selection_reason", "applied_level", "applied_species",
        "selected_stat_reduction", "stat_penalty_remaining", "permanent_stat_reduction",
        "species_base_total", "high_base_total", "height_base_m", "weight_base_kg",
        "selected_height_reduction", "selected_weight_reduction",
        "height_reduction", "weight_reduction", "permanent_height_reduction",
        "permanent_weight_reduction", "level_recoveries", "pending_growth_levels",
        "physical_growth"
    }
    if type(row) is not dict or set(row) != fields:
        raise ValueError("exact Baby Template state required")
    if row["source"] != SOURCE or tuple(row["source_lines"]) != SOURCE_LINES or tuple(row["clauses"]) != CLAUSES:
        raise ValueError("Baby Template source identity mismatch")
    if type(row["selection_reason"]) is not str or not row["selection_reason"].strip():
        raise ValueError("explicit Baby Template selection reason required")
    F.integer(row["applied_level"], "Baby Template application level", 1, 100)
    reduction = F.integer(row["selected_stat_reduction"], "Baby Template stat reduction", 2, 4)
    if reduction not in (2, 3, 4):
        raise ValueError("Baby Template stat reduction must be 2, 3, or 4")
    remaining = F.integer(row["stat_penalty_remaining"], "remaining Baby Template stat reduction", 0, reduction)
    floor = F.integer(row["permanent_stat_reduction"], "permanent Baby Template stat reduction", 0, reduction)
    if remaining < floor:
        raise ValueError("Baby Template recovered past its selected permanent reduction")
    F.integer(row["species_base_total"], "Baby Template species base total", 0)
    if type(row["high_base_total"]) is not bool or row["high_base_total"] != (row["species_base_total"] > 60):
        raise ValueError("Baby Template high-base-total evidence mismatch")
    for field, label in (("height_base_m", "height"), ("weight_base_kg", "weight")):
        _measurement(row[field], label)
    for field in ("selected_height_reduction", "selected_weight_reduction", "height_reduction", "weight_reduction", "permanent_height_reduction", "permanent_weight_reduction"):
        _fraction(row[field], field.replace("_", " "))
    if row["height_reduction"] > row["selected_height_reduction"] or row["weight_reduction"] > row["selected_weight_reduction"]:
        raise ValueError("Baby Template physical reduction exceeded its selected value")
    if row["height_reduction"] < row["permanent_height_reduction"] or row["weight_reduction"] < row["permanent_weight_reduction"]:
        raise ValueError("Baby Template physical growth passed its permanent floor")
    if row["height_reduction"] and row["height_base_m"] is None:
        raise ValueError("height reduction requires an actual height")
    if row["weight_reduction"] and row["weight_base_kg"] is None:
        raise ValueError("weight reduction requires an actual weight")
    if type(row["level_recoveries"]) is not list or any(type(x) is not int or x % 5 or x <= row["applied_level"] for x in row["level_recoveries"]):
        raise ValueError("Baby Template recovery levels must be later fifth levels")
    if row["level_recoveries"] != sorted(set(row["level_recoveries"])) or any(x > spec.get("level", 0) for x in row["level_recoveries"]):
        raise ValueError("Baby Template recovery levels must be distinct and ordered")
    expected_remaining=max(floor,reduction-len(row["level_recoveries"]))
    if remaining != expected_remaining:
        raise ValueError("Baby Template stat recovery count disagrees with its fifth-level receipts")
    pending = row["pending_growth_levels"]
    if type(pending) is not list or any(type(x) is not int or x % 5 or x not in row["level_recoveries"] for x in pending):
        raise ValueError("pending Baby Template growth must belong to a recovery level")
    if pending != sorted(set(pending)):
        raise ValueError("pending Baby Template growth levels must be distinct and ordered")
    history = row["physical_growth"]
    if type(history) is not list:
        raise ValueError("Baby Template physical growth history required")
    seen = set(); prior_height=row["selected_height_reduction"];prior_weight=row["selected_weight_reduction"]
    for receipt in history:
        if type(receipt) is not dict or set(receipt) != {"level", "height_reduction", "weight_reduction", "reason"}:
            raise ValueError("exact Baby Template physical growth receipt required")
        level = F.integer(receipt["level"], "Baby Template physical growth level", 5, 100)
        if level % 5 or level in seen or level in pending or level not in row["level_recoveries"]:
            raise ValueError("physical growth must consume one pending fifth-level boundary")
        seen.add(level)
        _fraction(receipt["height_reduction"], "historical height reduction")
        _fraction(receipt["weight_reduction"], "historical weight reduction")
        if not row["permanent_height_reduction"] <= receipt["height_reduction"] <= prior_height or not row["permanent_weight_reduction"] <= receipt["weight_reduction"] <= prior_weight:
            raise ValueError("Baby Template physical history must move toward its permanent floor")
        if receipt["height_reduction"] == prior_height and receipt["weight_reduction"] == prior_weight:
            raise ValueError("Baby Template physical history must record actual growth")
        prior_height=receipt["height_reduction"];prior_weight=receipt["weight_reduction"]
        if type(receipt["reason"]) is not str or not receipt["reason"].strip():
            raise ValueError("physical growth observation reason required")
    if history and [x["level"] for x in history] != sorted(x["level"] for x in history):
        raise ValueError("Baby Template physical growth receipts must be ordered")
    if (row["height_reduction"],row["weight_reduction"]) != (prior_height,prior_weight):
        raise ValueError("Baby Template physical projection differs from its receipt history")
    return row


def validate(rules, spec):
    row = _record(spec)
    if row is None:
        return None
    if spec.get("kind") != "pokemon":
        raise ValueError("Baby Template requires an actual Pokemon")
    from builder import species_lookup, STATS
    if type(row["applied_species"]) is not str or not row["applied_species"]:
        raise ValueError("Baby Template application species identity required")
    base = species_lookup(rules, row["applied_species"])["base_stats"]
    if sum(base.values()) != row["species_base_total"]:
        raise ValueError("Baby Template species base-total evidence changed")
    if any(base[stat] - row["selected_stat_reduction"] < 1 for stat in STATS):
        raise ValueError("selected Baby Template reduction would make a Base Stat lower than 1")
    return row


def base_sources(rules, spec):
    row = validate(rules, spec)
    if row is None or not row["stat_penalty_remaining"]:
        return []
    from builder import STATS
    return [{"source": STAT_SOURCE, "signed": True,
             "values": dict.fromkeys(STATS, -row["stat_penalty_remaining"])}]


def _penalties_active(actor):
    row = validate(actor.r, actor.spec)
    return bool(row and row["stat_penalty_remaining"])


def skill_rank_penalty(actor):
    """All skills are one rank lower until every Base Stat is restored."""
    return int(_penalties_active(actor))


def limit_power(actor, value):
    """Printed core213/496 reduce numeric Capabilities BY two, not TO two.

    Preserve the existing Power domain (the published table starts at one).
    Invalid incoming values still reach the native Power validator unchanged.
    """
    if type(value) is not int or value < 1:
        return value
    return max(1, value - 2) if _penalties_active(actor) else value


def capability_values(actor, values, fields):
    """Project the same temporary -2 on existing numeric movement/jump values.

    A missing capability is never granted. Existing nonnegative distance domains
    remain nonnegative; malformed incoming values remain native-validation errors.
    """
    result = dict(values)
    if _penalties_active(actor):
        for field in fields:
            value = result.get(field)
            if type(value) in (int, float) and value >= 0:
                result[field] = max(0, value - 2)
    return result


def body_projection(actor):
    row = validate(actor.r, actor.spec)
    if row is None:
        return None
    return {
        "source": SOURCE, "active": bool(row["stat_penalty_remaining"] or
            row["height_reduction"] or row["weight_reduction"]),
        "stat_penalty_remaining": row["stat_penalty_remaining"],
        "skill_rank_penalty": skill_rank_penalty(actor),
        "capability_penalty": 2 if _penalties_active(actor) else 0,
        "height_reduction": row["height_reduction"],
        "weight_reduction": row["weight_reduction"],
        "pending_growth_levels": list(row["pending_growth_levels"]),
        "permanence": "permanent" if row["permanent_stat_reduction"] == row["selected_stat_reduction"]
            else "partial_permanent" if any((row["permanent_stat_reduction"],
                row["permanent_height_reduction"], row["permanent_weight_reduction"]))
            else "recovering"
    }


def _physical_value(base, reduction):
    return None if base is None else base * (1 - reduction)


def apply(engine, actor, *, stat_reduction, height_reduction=0, weight_reduction=0,
          permanent_stat_reduction=0, permanent_height_reduction=0,
          permanent_weight_reduction=0, reason):
    """Apply only after an explicit GM choice; species never auto-select it."""
    import state_grants as G
    return G.transition(engine, actor, lambda e, c: _apply(e, c,
        stat_reduction=stat_reduction, height_reduction=height_reduction,
        weight_reduction=weight_reduction,
        permanent_stat_reduction=permanent_stat_reduction,
        permanent_height_reduction=permanent_height_reduction,
        permanent_weight_reduction=permanent_weight_reduction, reason=reason))


def _apply(engine, actor, **choice):
    import world_entities as W
    import growth_stats as GS
    from builder import species_lookup, STATS
    W.require_actors(engine, actor)
    if actor.kind != "pokemon":
        raise ValueError("Baby Template requires an actual Pokemon")
    if KEY in actor.spec:
        raise ValueError("Baby Template is already applied")
    if type(choice["reason"]) is not str or not choice["reason"].strip():
        raise ValueError("explicit Baby Template selection reason required")
    reduction = choice["stat_reduction"]
    if type(reduction) is not int or reduction not in (2, 3, 4):
        raise ValueError("Baby Template stat reduction must be 2, 3, or 4")
    floor = F.integer(choice["permanent_stat_reduction"], "permanent stat reduction", 0, reduction)
    height = _fraction(choice["height_reduction"], "height reduction")
    weight = _fraction(choice["weight_reduction"], "weight reduction")
    height_floor = _fraction(choice["permanent_height_reduction"], "permanent height reduction")
    weight_floor = _fraction(choice["permanent_weight_reduction"], "permanent weight reduction")
    if height_floor > height or weight_floor > weight:
        raise ValueError("permanent physical reduction cannot exceed the selected reduction")
    species = species_lookup(engine.r, actor.spec["species"])
    if any(species["base_stats"][stat] - reduction < 1 for stat in STATS):
        raise ValueError("selected Baby Template reduction would make a Base Stat lower than 1")
    current = GS.source_permanent(actor)
    height_base = _measurement(actor.spec.get("height_m", species.get("height_m")), "height")
    weight_base = _measurement(actor.spec.get("weight_kg", species.get("weight_kg")), "weight")
    if height and height_base is None:
        raise ValueError("height reduction requires an actual height")
    if weight and weight_base is None:
        raise ValueError("weight reduction requires an actual weight")
    actor.spec[KEY] = {
        "source": SOURCE, "source_lines": list(SOURCE_LINES), "clauses": list(CLAUSES),
        "selection_reason": choice["reason"], "applied_level": actor.level,
        "applied_species": actor.spec["species"],
        "selected_stat_reduction": reduction, "stat_penalty_remaining": reduction,
        "permanent_stat_reduction": floor, "species_base_total": sum(species["base_stats"].values()),
        "high_base_total": sum(species["base_stats"].values()) > 60,
        "height_base_m": height_base, "weight_base_kg": weight_base,
        "selected_height_reduction": height, "selected_weight_reduction": weight,
        "height_reduction": height, "weight_reduction": weight,
        "permanent_height_reduction": height_floor, "permanent_weight_reduction": weight_floor,
        "level_recoveries": [], "pending_growth_levels": [], "physical_growth": []
    }
    validate(engine.r, actor.spec)
    GS.migrate_sources(actor, current, source=SOURCE, reason=choice["reason"], kind="baby_template_apply")
    changes = {}
    if height_base is not None:
        changes["height_m"] = _physical_value(height_base, height)
    if weight_base is not None:
        changes["weight_kg"] = _physical_value(weight_base, weight)
    if changes:
        F.base_patch(actor, changes, source=SOURCE, reason=choice["reason"])
    validate(engine.r, actor.spec)
    actor._state_revision = getattr(actor, "_state_revision", 0) + 1
    return projection(engine.r, actor.spec)


def on_level(rules, spec, log=None):
    """Reconcile the template after the ordinary level investment is recorded."""
    row = validate(rules, spec)
    if row is None or spec["level"] % 5 or spec["level"] <= row["applied_level"]:
        return False
    level = spec["level"]
    if level in row["level_recoveries"]:
        raise ValueError("Baby Template fifth-level recovery was already recorded")
    import growth_stats as GS
    current = GS.project(rules, spec)
    row["level_recoveries"].append(level)
    recovered = row["stat_penalty_remaining"] > row["permanent_stat_reduction"]
    if recovered:
        row["stat_penalty_remaining"] -= 1
        prepared = GS.source_plans(rules, spec, current)
        if "form_growth_allocations" in spec:
            growth = spec["form_growth_allocations"]
            spec.setdefault("form_growth_history", []).append({"kind": "baby_template_recovery",
                "previous": deepcopy(growth), "source": SOURCE, "level": level})
            growth["plans"] = {name: value["plan"] for name, value in prepared.items()}
            growth["level"] = level
            spec["form_allocations"]["forms"] = {name: value["stats"] for name, value in prepared.items()}
            active = spec["form_allocations"]["active"]
        else:
            active = "base"
        chosen = prepared[active]
        spec.setdefault("allocation_migrations", []).append({"kind": "baby_template_recovery",
            "species": spec["species"], "level": level, "source": SOURCE,
            "reason": "Baby Template fifth-level Base Stat recovery", "plan": deepcopy(chosen["plan"]),
            "growth_event_offset": len(spec.get("growth_investment_events", []))})
        spec["stats"] = deepcopy(chosen["stats"])
        from builder import record_allocation, STATS
        record_allocation(rules, spec, "baby_template_recovery",
            delta=dict.fromkeys(STATS, 1), source=SOURCE)
    if (row["height_reduction"] > row["permanent_height_reduction"] or
            row["weight_reduction"] > row["permanent_weight_reduction"]):
        row["pending_growth_levels"].append(level)
    if log is not None:
        suffix = "each Base Stat +1" if recovered else "permanent Base Stat reduction retained"
        if level in row["pending_growth_levels"]:
            suffix += "; physical growth observation pending"
        log.append("  Baby Template: " + suffix)
    validate(rules, spec)
    return True


def record_growth(engine, actor, *, level, height_reduction, weight_reduction, reason):
    """Consume one fifth-level physical-growth choice without inventing its size."""
    import state_grants as G
    return G.transition(engine, actor, lambda e, c: _record_growth(e, c, level,
        height_reduction, weight_reduction, reason))


def _record_growth(engine, actor, level, height_reduction, weight_reduction, reason):
    import world_entities as W
    W.require_actors(engine, actor)
    row = validate(engine.r, actor.spec)
    if row is None or level not in row["pending_growth_levels"]:
        raise ValueError("an actual pending Baby Template growth boundary is required")
    if type(reason) is not str or not reason.strip():
        raise ValueError("physical growth observation reason required")
    height = _fraction(height_reduction, "height reduction")
    weight = _fraction(weight_reduction, "weight reduction")
    if not row["permanent_height_reduction"] <= height <= row["height_reduction"] or not row["permanent_weight_reduction"] <= weight <= row["weight_reduction"]:
        raise ValueError("physical growth must move toward the selected permanent floor")
    if height == row["height_reduction"] and weight == row["weight_reduction"]:
        raise ValueError("Baby Template physical growth must increase height or weight")
    row["height_reduction"] = height
    row["weight_reduction"] = weight
    row["pending_growth_levels"].remove(level)
    row["physical_growth"].append({"level": level, "height_reduction": height,
        "weight_reduction": weight, "reason": reason})
    changes = {}
    if row["height_base_m"] is not None:
        changes["height_m"] = _physical_value(row["height_base_m"], height)
    if row["weight_base_kg"] is not None:
        changes["weight_kg"] = _physical_value(row["weight_base_kg"], weight)
    if changes:
        F.base_patch(actor, changes, source=SOURCE, reason=reason)
    validate(engine.r, actor.spec)
    actor._state_revision = getattr(actor, "_state_revision", 0) + 1
    return projection(engine.r, actor.spec)


def projection(rules, spec):
    row = validate(rules, spec)
    if row is None:
        return None
    return deepcopy({**row,
        "skill_rank_penalty_active": bool(row["stat_penalty_remaining"]),
        "capability_penalty": 2 if row["stat_penalty_remaining"] else 0,
        "height_m": _physical_value(row["height_base_m"], row["height_reduction"]),
        "weight_kg": _physical_value(row["weight_base_kg"], row["weight_reduction"]),
        "fully_recovered": not any((row["stat_penalty_remaining"], row["height_reduction"], row["weight_reduction"]))})


def validate_actor(engine, actor):
    """Validate source state against its permanent-stat and body consumers."""
    row = validate(engine.r, actor.spec)
    if row is None:
        return True
    for field, base, reduction in (("height_m", row["height_base_m"], row["height_reduction"]),
                                   ("weight_kg", row["weight_base_kg"], row["weight_reduction"])):
        if base is not None and actor.spec.get(field) != _physical_value(base,reduction):
            raise ValueError("Baby Template " + field + " differs from its source-owned projection")
    import growth_stats as GS
    GS.project_actor(engine,actor)
    return True
