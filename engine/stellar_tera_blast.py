"""Exact Stellar Blast radiation and the three CSV Tera Blast consumers."""
from copy import deepcopy
import json
from pathlib import Path

STATE = "stellar_blast_radiation"
POLICY = "data/stellar-tera-blast-policy.json"


def _policy(rules):
    cached = getattr(rules, "_stellar_tera_blast_policy", None)
    if cached is None:
        cached = json.loads((Path(rules.root) / POLICY).read_text(encoding="utf-8"))
        if cached.get("schema") != "ptk.csv-stellar-tera-blast.v1":
            raise ValueError("unsupported Stellar/Tera Blast policy schema")
        ability = cached.get("ability")
        moves = cached.get("moves")
        if not isinstance(ability, dict) or ability.get("source_id") != "ability/스텔라버스트":
            raise ValueError("exact Stellar Blast source policy required")
        expected = {
            "move/테라버스트",
            "move/테라버스트-물리",
            "move/테라버스트-특수",
        }
        if not isinstance(moves, list) or len(moves) != 3 or {row.get("move_id") for row in moves} != expected:
            raise ValueError("exact three Tera Blast consumers required")
        if len({row.get("clause_id") for row in moves}) != 3:
            raise ValueError("distinct Tera Blast clause identities required")
        rules._stellar_tera_blast_policy = cached
    return cached


def rows(rules):
    return {row["move_id"]: row for row in _policy(rules)["moves"]}


def owns_move(rules, move):
    return isinstance(move, dict) and move.get("id") in rows(rules)


def owns_effect(rules, move, effect):
    return owns_move(rules, move) and effect.get("type") in {
        "alternate_type", "type_effectiveness_override"
    }


def registration(rules, selected_id):
    return selected_id == _policy(rules)["ability"]["source_id"]


def _ability_owned(rules, actor):
    source = _policy(rules)["ability"]["source_id"]
    name = _policy(rules)["ability"]["name"]
    import move_state as MOVE_STATE
    for value in actor.abilities:
        if value in (source, name):
            return True
        try:
            registration = MOVE_STATE.ability_registration(rules, value)
        except (KeyError, ValueError):
            registration = None
        if registration and registration.get("source_id") == source:
            return True
    return False


def _blank(engine, actor):
    return {
        "version": 1,
        "source": _policy(engine.r)["ability"]["source_id"],
        "owner_id": actor.entity_id,
        "encounter_epoch": getattr(engine, "_party_encounter_epoch", 0),
        "sequence": 0,
        "opportunities": [],
        "active": None,
        "history": [],
    }


def _record(engine, actor, create=False):
    record = actor.spec.get(STATE)
    if record is None and create:
        record = _blank(engine, actor)
        actor.spec[STATE] = record
    if record is not None:
        validate_actor(engine, actor)
    return record


def validate_actor(engine, actor):
    record = actor.spec.get(STATE)
    if record is None:
        return True
    required = {
        "version", "source", "owner_id", "encounter_epoch", "sequence",
        "opportunities", "active", "history",
    }
    ability = _policy(engine.r)["ability"]
    if (not isinstance(record, dict) or set(record) != required or record["version"] != 1
            or record["source"] != ability["source_id"] or record["owner_id"] != actor.entity_id
            or type(record["encounter_epoch"]) is not int or record["encounter_epoch"] < 0
            or type(record["sequence"]) is not int or record["sequence"] < 0
            or not isinstance(record["opportunities"], list) or not isinstance(record["history"], list)):
        raise ValueError("invalid Stellar Blast radiation state")
    if not _ability_owned(engine.r, actor):
        raise ValueError("Stellar Blast state requires the actual owned ability")
    seen = set()
    opportunity_by_id = {}
    for row in record["opportunities"]:
        keys = {"id", "sequence", "completion_id", "move_id", "target_id", "types", "round", "at", "consumed"}
        if (not isinstance(row, dict) or set(row) != keys or not isinstance(row["id"], str)
                or row["id"] in seen or type(row["sequence"]) is not int
                or not 1 <= row["sequence"] <= record["sequence"]
                or not isinstance(row["completion_id"], str) or not isinstance(row["move_id"], str)
                or not isinstance(row["target_id"], str) or not isinstance(row["types"], list)
                or not row["types"] or len(set(row["types"])) != len(row["types"])
                or any(not isinstance(value, str) or not value for value in row["types"])
                or type(row["round"]) is not int or row["round"] < 0
                or isinstance(row["at"], bool) or not isinstance(row["at"], (int, float)) or row["at"] < 0
                or type(row["consumed"]) is not bool):
            raise ValueError("invalid actual-hit radiation opportunity")
        seen.add(row["id"])
        opportunity_by_id[row["id"]] = row
    for row in record["history"]:
        keys = {"id", "opportunity_id", "radiated_type", "activated_at", "round", "reason", "action"}
        if (not isinstance(row, dict) or set(row) != keys or not isinstance(row["id"], str)
                or row["opportunity_id"] not in opportunity_by_id
                or row["radiated_type"] not in opportunity_by_id[row["opportunity_id"]]["types"]
                or isinstance(row["activated_at"], bool) or not isinstance(row["activated_at"], (int, float))
                or row["activated_at"] < 0 or type(row["round"]) is not int
                or not isinstance(row["reason"], str) or not row["reason"].strip()
                or row["action"] != ability["activation_action"]):
            raise ValueError("invalid Stellar Blast activation receipt")
    active = record["active"]
    if active is not None:
        if not isinstance(active, dict) or not record["history"] or active != record["history"][-1]:
            raise ValueError("active radiation must be the latest activation receipt")
        if not opportunity_by_id[active["opportunity_id"]]["consumed"]:
            raise ValueError("active radiation requires its consumed hit opportunity")
    return True


def validate_world(engine):
    import world_entities as WORLD
    for actor in WORLD.actor_index(engine).values():
        validate_actor(engine, actor)
    return True


def observe_completion(engine, completion):
    """Produce hit opportunities only after every completion effect succeeded."""
    actor = completion.get("actor")
    if (not engine.encounter_active or actor is None or not _ability_owned(engine.r, actor)
            or actor.fainted or actor.abilities_suppressed):
        return []
    import homebrew_state as HOME
    pending = []
    existing = {row["id"] for row in (_record(engine, actor) or {}).get("opportunities", [])}
    import move_completion as COMPLETE
    for target in COMPLETE.actual_recipients(completion):
        result = COMPLETE.recipient_result(completion,target)
        identity = "stellar-hit:%s:%s" % (completion["id"], target.entity_id)
        if (not result or not result["hit"] or result["cancelled"] or target.side == actor.side
                or identity in existing):
            continue
        types = HOME.actual_types(target, target.types)
        if not types:
            continue
        pending.append((identity, target, list(types)))
    if not pending:
        return []
    record = _record(engine, actor, True)
    additions = []
    for identity, target, types in pending:
        record["sequence"] += 1
        additions.append({
            "id": identity,
            "sequence": record["sequence"],
            "completion_id": completion["id"],
            "move_id": completion["move_id"],
            "target_id": target.entity_id,
            "types": types,
            "round": engine.round_no,
            "at": engine.elapsed_seconds,
            "consumed": False,
        })
    record["opportunities"].extend(additions)
    validate_actor(engine, actor)
    return deepcopy(additions)


def activate(engine, actor, opportunity_id, radiated_type, *, reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Stellar Blast activation reason required")
    if not engine.encounter_active or engine._active_turn_actor is not actor:
        raise ValueError("Stellar Blast is an immediate Swift action on its owner's active turn")
    record = _record(engine, actor)
    if record is None or record["encounter_epoch"] != getattr(engine, "_party_encounter_epoch", 0):
        raise ValueError("current-encounter Stellar Blast hit required")
    choices = [row for row in record["opportunities"] if row["id"] == opportunity_id]
    if len(choices) != 1 or choices[0]["consumed"]:
        raise ValueError("one unconsumed actual-hit opportunity required")
    opportunity = choices[0]
    if opportunity["round"] != engine.round_no or radiated_type not in opportunity["types"]:
        raise ValueError("choose a type of the enemy hit during this trigger window")
    import state_grants as GRANTS
    import turn as TURN
    def apply(staged, staged_actor):
        staged_record = _record(staged, staged_actor)
        staged_opportunity = next(row for row in staged_record["opportunities"] if row["id"] == opportunity_id)
        if not TURN.spend(staged, staged_actor, "swift", "Stellar Blast"):
            raise ValueError("Stellar Blast Swift action unavailable")
        staged_opportunity["consumed"] = True
        receipt = {
            "id": "stellar-radiation:%d" % (len(staged_record["history"]) + 1),
            "opportunity_id": opportunity_id,
            "radiated_type": radiated_type,
            "activated_at": staged.elapsed_seconds,
            "round": staged.round_no,
            "reason": reason,
            "action": "swift",
        }
        staged_record["history"].append(receipt)
        staged_record["active"] = receipt
        validate_actor(staged, staged_actor)
        staged.log("    %s: %s 타입 방사" % (staged_actor.name, radiated_type), _policy(staged.r)["ability"]["source_id"])
        return deepcopy(receipt)
    return GRANTS.transition(engine, actor, apply)


def active_radiation(engine, actor):
    record = _record(engine, actor)
    if (record is None or not engine.encounter_active
            or record["encounter_epoch"] != getattr(engine, "_party_encounter_epoch", 0)
            or actor.fainted or actor.abilities_suppressed or not actor.on_field):
        return None
    return record["active"]


def effective_type(engine, actor, target, move):
    if not owns_move(engine.r, move):
        return None
    active = active_radiation(engine, actor)
    if active is not None:
        return active["radiated_type"]
    import homebrew_state as HOME
    if HOME.tera_active(actor):
        return HOME.tera_type(actor)
    return None


def grants_stab(engine, actor, move):
    row = rows(engine.r).get(move.get("id"))
    return bool(row and row["force_stab_when_type_projected"]
                and effective_type(engine, actor, actor, move) is not None)


def _within_aura(owner, attacker):
    if owner is attacker:
        return True
    if owner.pos is None or attacker.pos is None:
        return False
    from grid import cheb
    return cheb(owner.pos, attacker.pos) <= 2


def damage_roll_bonus(engine, attacker, actual_type):
    import world_entities as WORLD
    sources = []
    for owner in WORLD.actor_index(engine).values():
        active = active_radiation(engine, owner)
        if (active is not None and owner.side == attacker.side and _within_aura(owner, attacker)
                and active["radiated_type"] == actual_type):
            sources.append(owner.entity_id)
    return (_policy(engine.r)["ability"]["matching_type_damage_bonus"] if sources else 0, sources)


def _form_changed(engine, target):
    import homebrew_state as HOME
    if HOME.tera_active(target):
        return True
    if target.spec.get("mega_form") or target.spec.get("gmax_state"):
        return True
    if getattr(target, "form", None):
        return True
    return bool(getattr(target, "custom_conditions", {}).get("transformed"))


def effectiveness(engine, actor, target, move, multiplier, ctx):
    if not owns_move(engine.r, move) or multiplier == 0:
        return multiplier
    import homebrew_state as HOME
    active = active_radiation(engine, actor)
    stellar_move = HOME.tera_type(actor) == "스텔라" and HOME.tera_active(target)
    stellar_ability = active is not None and _form_changed(engine, target)
    if not (stellar_move or stellar_ability):
        return multiplier
    steps = {0.125: -3, 0.25: -2, 0.5: -1, 1.0: 0, 1.5: 1, 2.0: 2, 3.0: 3}
    current = steps.get(multiplier)
    if current is None:
        raise ValueError("Stellar effectiveness needs a canonical multiplier")
    desired = min(2, current + _policy(engine.r)["ability"]["tera_blast_effectiveness_steps"])
    result = engine.r.mech("combat/type-effectiveness")["multiplier_by_net_steps"][str(desired)]
    ctx["stellar_tera_blast"] = {
        "source": _policy(engine.r)["ability"]["source_id"] if stellar_ability else rows(engine.r)[move["id"]]["clause_id"],
        "before": multiplier,
        "after": result,
        "cap": _policy(engine.r)["ability"]["effectiveness_cap"],
    }
    return result
