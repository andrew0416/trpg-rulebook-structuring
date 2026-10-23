"""Exact catalog Move states that reuse the native combat timer.

The declarations here are deliberately closed: a selected Move must carry the
reviewed effect verbatim before it can create a timed state.  The shared state
stores only the differences needed by its consumers (locked keywords or
grounding); turn ownership and expiry stay in :mod:`combat_timing`.
"""
from copy import deepcopy

import combat_timing as TIMING
import common_checks as CHECKS


MOVE_LOCKS = {
    "move/지옥찌르기": {
        "clause": "C2CSV-MOVE-R0076",
        "effect": {"type": "move_lock", "keyword": "소리", "target": "target", "duration": "2턴"},
        "turns": 2,
    },
}

GROUNDING = {
    "move/사우전드애로": {
        "clause": "C2CSV-MOVE-R0407",
        "effect": {"type": "grounding", "turns": 3},
        "turns": 3,
    },
    "move/떨어뜨리기": {
        "clause": "C2CSV-MOVE-R0750",
        "effect": {"type": "grounding", "turns": 3, "target": "target"},
        "turns": 3,
    },
}


def _semantic(effect):
    return {key: deepcopy(value) for key, value in effect.items() if not key.startswith("_")}


def _selected_declaration(engine, source, effect, policies):
    policy = policies.get(source)
    if policy is None:
        raise ValueError("catalog Move state has no reviewed source policy: " + str(source))
    if engine.r._selected_rule(source) != source:
        raise ValueError("selected catalog Move variant needs its own state policy")
    actual = _semantic(effect)
    if actual != policy["effect"]:
        raise ValueError("catalog Move state differs from its reviewed declaration")
    mechanics, _ = engine.r.move_mech(source)
    matches = [row for row in mechanics.get("effects_exec", [])
               if isinstance(row, dict) and _semantic(row) == actual]
    if len(matches) != 1:
        raise ValueError("selected Move must contain exactly one reviewed state declaration")
    return policy


def prepare_move_lock(engine, actor, target, effect, source):
    policy = _selected_declaration(engine, source, effect, MOVE_LOCKS)
    if not engine.encounter_active:
        raise ValueError("two target turns require an active encounter")
    if target is actor or effect.get("target") != "target":
        raise ValueError("Throat Chop lock requires its actual hit target")
    serial = CHECKS.integer(target.custom_conditions.get("combat_turn_serial", 0),
                            "target turn serial", 0)
    return {
        "source": source,
        "effect_contract": True,
        "timing_text": effect["duration"],
        "turn_owner": target,
        "turn_deadline": serial + policy["turns"],
        "encounter_end": True,
        "catalog_move_lock": {
            "clause": policy["clause"],
            "keyword": effect["keyword"],
            "start_serial": serial,
            "turns": policy["turns"],
        },
    }


def locked_keywords(actor):
    return {record["catalog_move_lock"]["keyword"]
            for record in TIMING.records(actor)
            if isinstance(record.get("catalog_move_lock"), dict)}


def _keyword_in_range(engine, move, keyword):
    import weapon_actions as WEAPONS
    raw = str(WEAPONS.range_spec(engine, move).get("raw", move.get("range", "")))
    aliases = {keyword.casefold()}
    if keyword == "소리":
        aliases.add("sound")
    folded = raw.casefold()
    return any(alias in folded for alias in aliases)


def move_locked(engine, actor, move):
    return next((keyword for keyword in locked_keywords(actor)
                 if _keyword_in_range(engine, move, keyword)), None)


def _landing_available(engine, target):
    if engine.grid is None:
        return True
    import body_state as BODY
    return BODY.can_place(engine, target, target.pos, altitude=0)


def install_grounding(engine, actor, target, effect, context):
    source = context.get("source_id")
    policy = _selected_declaration(engine, source, effect, GROUNDING)
    if not engine.encounter_active:
        raise ValueError("three target turns require an active encounter")
    if target is actor or effect.get("target", "target") != "target":
        raise ValueError("grounding requires its actual hit target")
    if not target.on_field or target.captured or target.fainted:
        raise ValueError("grounding requires a current field target")
    altitude = target.spec.get("_movement_altitude", 0)
    if isinstance(altitude, bool) or not isinstance(altitude, (int, float)) or altitude < 0:
        raise ValueError("grounding requires a known nonnegative altitude")
    if altitude and not _landing_available(engine, target):
        return CHECKS.PendingDecision(
            "forced landing cell is occupied; GM world response required",
            basis={"source": source, "location": deepcopy(target.location), "altitude": altitude},
        )
    serial = CHECKS.integer(target.custom_conditions.get("combat_turn_serial", 0),
                            "target turn serial", 0)
    record = {
        "source": source,
        "effect_contract": True,
        "timing_text": "3 target turns",
        "turn_owner": target,
        "turn_deadline": serial + policy["turns"],
        "encounter_end": True,
        "blocked_movement_modes": ["sky", "levitate"],
        "catalog_grounding": {
            "clause": policy["clause"],
            "start_serial": serial,
            "turns": policy["turns"],
            "from_altitude": altitude,
            "location": deepcopy(target.location),
        },
        "effect_occurrence": context.get("effect_occurrence"),
        "effect_receipt": context.get("effect_receipt"),
    }
    target.spec["_movement_altitude"] = 0
    target.airborne = False
    TIMING.install(engine, target, record)
    engine.log(
        f"    {target.name} 땅으로 떨어짐: 대상의 다음 {policy['turns']}턴 동안 공중/부유 이동 상실, 땅 기술 명중",
        source,
    )
    return None


def grounded(actor):
    return bool(getattr(actor, "grounded", 0)) or any(
        isinstance(record.get("catalog_grounding"), dict)
        for record in TIMING.records(actor)
    )


def _ability_names(engine, actor):
    result = set()
    for name in actor.abilities:
        result.add(str(name).casefold())
        result.add(str(engine.r.ability_alias.get(name, name)).casefold())
    return result


def ignores_levitate(mechanics):
    aliases = {"부유", "levitate", "ability/부유"}
    return any(effect.get("type") == "ignore_ability"
               and str(effect.get("ability", "")).casefold() in aliases
               for effect in mechanics.get("effects_exec", []))


def levitate_blocks(engine, target, move, mechanics, attacker=None):
    if move.get("type") != "땅" or target.abilities_suppressed or grounded(target):
        return False
    if attacker is not None and __import__('chronicler').defensive_ignored(engine, attacker, target):
        return False
    if ignores_levitate(mechanics):
        return False
    return bool(_ability_names(engine, target) & {"부유", "levitate", "ability/부유"})


def _validate_receipt(engine, actor, record, policies, marker):
    import effect_contracts as CONTRACTS
    receipt = record.get("effect_receipt")
    row = getattr(engine, "_effect_dispatch_receipts", {}).get(receipt)
    if not row or row.get("status") != "completed":
        raise ValueError("catalog Move state needs a completed native effect receipt")
    source = record.get("source")
    CONTRACTS.validate_receipt(engine, receipt, source, record.get("effect_occurrence"),
                               row["actor"], row["target"], row["effect"])
    if row["target"] is not actor or _semantic(row["effect"]) != policies[source]["effect"]:
        raise ValueError("catalog Move state recipient or declaration differs from its receipt")
    if record.get("turn_owner") is not actor:
        raise ValueError("catalog Move state lost its actual target turn owner")
    state = record[marker]
    if record.get("turn_deadline") != state.get("start_serial") + state.get("turns", 0):
        raise ValueError("catalog Move state turn boundary changed")


def validate_world(engine, index):
    for actor in index.values():
        for record in TIMING.records(actor):
            if "catalog_move_lock" in record:
                source = record.get("source")
                if source not in MOVE_LOCKS or record["catalog_move_lock"].get("clause") != MOVE_LOCKS[source]["clause"]:
                    raise ValueError("unknown catalog Move lock source")
                _validate_receipt(engine, actor, record, MOVE_LOCKS, "catalog_move_lock")
            if "catalog_grounding" in record:
                source = record.get("source")
                if source not in GROUNDING or record["catalog_grounding"].get("clause") != GROUNDING[source]["clause"]:
                    raise ValueError("unknown catalog grounding source")
                if record.get("blocked_movement_modes") != ["sky", "levitate"]:
                    raise ValueError("catalog grounding movement loss changed")
                if actor.spec.get("_movement_altitude", 0) != 0 or actor.airborne:
                    raise ValueError("grounded target is no longer on the ground")
                _validate_receipt(engine, actor, record, GROUNDING, "catalog_grounding")
    return True
