"""Source-owned Breathless and vacuum exposure capability contracts.

The observed region remains the environment producer. This module projects
live capability sources onto that region, owns the vacuum injury-check clock,
and records explicit GM check outcomes without inventing a check DC. Vacuum
immunity never grants breathing; Breathless never grants vacuum immunity.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

import common_checks as C
import resolution_transaction as TX
import state_grants as GRANTS
import world_entities as WORLD


KEY = "environmental_capability_state"
POLICY_PATH = Path(__file__).resolve().parents[1] / "data" / "environmental-capability-policy.json"


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " required")
    return value


@lru_cache(maxsize=1)
def policy():
    value = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if type(value) is not dict or set(value) != {
        "schema_version", "source_file", "source_file_sha256", "capabilities",
        "vacuum_check_seconds",
    } or value["schema_version"] != 1:
        raise ValueError("exact environmental capability policy required")
    expected = {"vacuum_immunity", "vacuum_resistance", "breathless"}
    rows = value["capabilities"]
    if type(rows) is not list or {row.get("key") for row in rows} != expected:
        raise ValueError("three distinct respiration/vacuum capability rows required")
    clauses = set()
    for row in rows:
        if type(row) is not dict or set(row) != {"key", "names", "clause_id", "row", "columns", "raw_cells_sha256"}:
            raise ValueError("exact environmental capability row required")
        if (type(row["names"]) is not list or len(row["names"]) != 2 or
                any(not isinstance(name, str) or not name for name in row["names"])):
            raise ValueError("Korean and English capability names required")
        _text(row["clause_id"], "capability clause identity")
        C.integer(row["row"], "capability source row", 1)
        if row["columns"] != [5, 6] or len(row["raw_cells_sha256"]) != 64:
            raise ValueError("exact item-data source span required")
        clauses.add(row["clause_id"])
    if len(clauses) != 3 or value["vacuum_check_seconds"] != {"ordinary": 10, "vacuum_resistance": 300}:
        raise ValueError("vacuum capability source policy changed")
    return value


def _row(key):
    return next(row for row in policy()["capabilities"] if row["key"] == key)


def _matching_sources(actor, key):
    row = _row(key); names = set(row["names"])
    matched = sorted(set(GRANTS.effective_capabilities(actor)) & names)
    if not matched:
        return None
    sources = []
    baseline = actor.spec.get("capabilities", [])
    for name in matched:
        if name in baseline:
            sources.append({"kind": "sheet", "name": name, "species": actor.spec.get("species")})
    state = actor.spec.get(GRANTS.KEY, {})
    for source_id, source in sorted(state.get("sources", {}).items()):
        for name in matched:
            if name in source.get("grants", {}).get("capabilities", []):
                sources.append({
                    "kind": "state_grant", "name": name, "source_id": source_id,
                    "source_kind": source.get("kind"), "rule_id": source.get("rule_id"),
                    "owner_id": source.get("owner_id"), "lifetime": source.get("lifetime"),
                })
    for name in matched:
        if name in state.get("legacy", {}).get("capabilities", []):
            sources.append({"kind": "legacy_runtime", "name": name})
    if not sources:
        sources = [{"kind": "effective_projection", "name": name} for name in matched]
    result = {"key": key, "clause_id": row["clause_id"], "names": matched, "sources": sources}
    result["sha256"] = TX.request_fingerprint(result)
    return result


def breathless(engine, actor):
    """Breathless satisfies respiration only for its actual Pokemon owner."""
    return actor.kind == "pokemon" and _matching_sources(actor, "breathless") is not None


def _vacuum_snapshot(actor):
    return {key: value for key in ("vacuum_immunity", "vacuum_resistance")
            if (value := _matching_sources(actor, key)) is not None}


def _environment(engine, actor):
    import environment_derive as ENVIRONMENT
    WORLD.require_actors(engine, actor)
    actual = ENVIRONMENT.context(engine, actor)
    region = ENVIRONMENT._state(engine)["regions"][actual["region_id"]]
    ENVIRONMENT._verify(region)
    evidence = {"region_id": region["id"], "source": region["source"],
                "observed_at": region["seconds"], "sha256": region["sha256"]}
    return actual, evidence


def _state(actor, create=False):
    value = actor.spec.get(KEY)
    if value is None and create:
        value = {"version": 1, "vacuum_exposures": {}, "active_vacuum": None}
        actor.spec[KEY] = value
    return value


def observe_vacuum(engine, actor, *, exposure_id, exposed, reason):
    """Open or close one actual, region-backed vacuum exposure."""
    _text(exposure_id, "vacuum exposure identity"); _text(reason, "vacuum observation reason")
    if type(exposed) is not bool:
        raise ValueError("vacuum exposure must be explicit boolean")
    if exposed:
        actual, environment = _environment(engine, actor)
        if actual["pressure"] != 0 or actual["air_available"] is not False or actual["medium"] != "airless":
            raise ValueError("vacuum exposure requires an actual zero-pressure airless region")
        capabilities = _vacuum_snapshot(actor)
        interval = None if "vacuum_immunity" in capabilities else policy()["vacuum_check_seconds"][
            "vacuum_resistance" if "vacuum_resistance" in capabilities else "ordinary"]
        intent = {"exposure_id": exposure_id, "actor_id": actor.entity_id, "environment": environment,
                  "capabilities": capabilities, "interval_seconds": interval, "reason": reason}
        digest = TX.request_fingerprint(intent)

        def begin(staged, subject):
            state = _state(subject, True); old = state["vacuum_exposures"].get(exposure_id)
            if old is not None:
                if old["intent_sha256"] != digest or old["ended_at"] is not None:
                    raise ValueError("vacuum exposure identity cannot be reused")
                return deepcopy(old)
            if state["active_vacuum"] is not None:
                raise ValueError("close the actual active vacuum exposure first")
            row = {"id": exposure_id, "actor_id": subject.entity_id, "intent": intent,
                   "intent_sha256": digest, "started_at": staged.elapsed_seconds, "ended_at": None,
                   "interval_seconds": interval, "next_due_at": None if interval is None else staged.elapsed_seconds + interval,
                   "sequence": 0, "pending": {}, "resolved": []}
            state["vacuum_exposures"][exposure_id] = row; state["active_vacuum"] = exposure_id
            validate(subject, staged)
            return deepcopy(row)
        return GRANTS.transition(engine, actor, begin)

    def end(staged, subject):
        state = _state(subject)
        if state is None or state["active_vacuum"] != exposure_id:
            raise ValueError("actual active vacuum exposure required")
        row = state["vacuum_exposures"][exposure_id]
        if row["pending"]:
            raise ValueError("resolve due vacuum injury checks before ending exposure")
        row["ended_at"] = staged.elapsed_seconds; state["active_vacuum"] = None
        validate(subject, staged)
        return deepcopy(row)
    return GRANTS.transition(engine, actor, end)


def preflight_advance(engine, actor, seconds):
    state = _state(actor)
    if state is None or state["active_vacuum"] is None:
        return
    validate(actor, engine)
    row = state["vacuum_exposures"][state["active_vacuum"]]
    if row["pending"]:
        raise ValueError("resolve the due vacuum injury check before advancing time")
    actual, environment = _environment(engine, actor)
    if (actual["pressure"], actual["air_available"], actual["medium"]) != (0, False, "airless"):
        raise ValueError("changed vacuum region needs an explicit exposure-end observation")
    if environment != row["intent"]["environment"] or _vacuum_snapshot(actor) != row["intent"]["capabilities"]:
        raise ValueError("changed vacuum region or capability source needs a new exposure observation")
    due = row["next_due_at"]
    if due is not None and engine.elapsed_seconds + seconds > due:
        raise ValueError("advance only to the next actual vacuum injury-check boundary")


def advance(engine, actor):
    state = _state(actor)
    if state is None or state["active_vacuum"] is None:
        return
    row = state["vacuum_exposures"][state["active_vacuum"]]
    due = row["next_due_at"]
    if due is None or engine.elapsed_seconds < due:
        return
    if engine.elapsed_seconds != due or row["pending"]:
        raise ValueError("vacuum check boundary was crossed without its actual consumer")
    row["sequence"] += 1
    check_id = row["id"] + ":check:" + str(row["sequence"])
    row["pending"][check_id] = {"id": check_id, "exposure_id": row["id"], "due_at": due,
                                   "interval_seconds": row["interval_seconds"]}
    row["next_due_at"] = due + row["interval_seconds"]
    validate(actor, engine)


def resolve_vacuum_check(engine, actor, *, check_id, injury_delta, reason):
    _text(check_id, "vacuum check identity"); _text(reason, "vacuum check result reason")
    C.integer(injury_delta, "vacuum exposure injury result", 0, 1)

    def apply(staged, subject):
        state = _state(subject)
        if state is None or state["active_vacuum"] is None:
            raise ValueError("actual active vacuum exposure required")
        row = state["vacuum_exposures"][state["active_vacuum"]]
        check = row["pending"].pop(check_id, None)
        if check is None:
            raise ValueError("actual due vacuum injury check required")
        before = subject.injuries
        import actor_templates as TEMPLATES
        applied = 0 if TEMPLATES.injuries_immune(subject) else injury_delta
        if applied:
            import precise_actions as PRECISE
            injury_source = row["intent"]["environment"]["source"] + "#vacuum-exposure"
            applied=PRECISE.gain_injury(staged, subject, applied, injury_source)
            staged.check_fainted(subject)
        receipt = dict(check, injury_delta=applied, injury_delta_requested=injury_delta,
                       injury_delta_prevented=injury_delta-applied, injuries_before=before,
                       injuries_after=subject.injuries, resolved_at=staged.elapsed_seconds, reason=reason)
        row["resolved"].append(receipt)
        validate(subject, staged)
        return deepcopy(receipt)
    return GRANTS.transition(engine, actor, apply)


def validate(actor, engine=None):
    state = _state(actor)
    if state is None:
        return
    if type(state) is not dict or set(state) != {"version", "vacuum_exposures", "active_vacuum"} or state["version"] != 1:
        raise ValueError("exact vacuum capability state required")
    if type(state["vacuum_exposures"]) is not dict:
        raise ValueError("identified vacuum exposure ledger required")
    active = state["active_vacuum"]
    if active is not None and active not in state["vacuum_exposures"]:
        raise ValueError("active vacuum exposure identity missing")
    for exposure_id, row in state["vacuum_exposures"].items():
        required = {"id", "actor_id", "intent", "intent_sha256", "started_at", "ended_at", "interval_seconds", "next_due_at", "sequence", "pending", "resolved"}
        if type(row) is not dict or set(row) != required or row["id"] != exposure_id or row["actor_id"] != actor.entity_id:
            raise ValueError("exact vacuum exposure receipt required")
        if row["intent_sha256"] != TX.request_fingerprint(row["intent"]):
            raise ValueError("vacuum exposure intent changed")
        C.integer(row["started_at"], "vacuum exposure start", 0); C.integer(row["sequence"], "vacuum check sequence", 0)
        if row["interval_seconds"] not in (None, 10, 300):
            raise ValueError("vacuum check interval changed")
        if row["ended_at"] is not None:
            C.integer(row["ended_at"], "vacuum exposure end", row["started_at"])
            if active == exposure_id:
                raise ValueError("ended vacuum exposure cannot remain active")
        elif active != exposure_id:
            raise ValueError("one open vacuum exposure must be active")
        if type(row["pending"]) is not dict or type(row["resolved"]) is not list:
            raise ValueError("vacuum check ledgers required")
        for check_id, check in row["pending"].items():
            if (type(check) is not dict or set(check) != {"id", "exposure_id", "due_at", "interval_seconds"}
                    or check["id"] != check_id or check["exposure_id"] != exposure_id
                    or check["interval_seconds"] != row["interval_seconds"]):
                raise ValueError("vacuum pending check changed")
        if engine is not None and (row["started_at"] > engine.elapsed_seconds or
                                   row["ended_at"] is not None and row["ended_at"] > engine.elapsed_seconds):
            raise ValueError("vacuum receipt claims future world time")


def validate_world(engine, actors):
    for actor in actors.values():
        validate(actor, engine)
