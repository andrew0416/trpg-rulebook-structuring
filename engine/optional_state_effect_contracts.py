"""Source-owned optional state effects sharing one timed actor-state contract.

Only the eight clauses in the reviewed policy are executable here.  Global
condition clauses validate their existing native consumers; five activated
features store JSON-safe source records on the affected actors.  Consumers
read those records at stat, evasion, accuracy, critical, and movement queries.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import action_points as AP
import frequency as FREQUENCY
import skill_modifiers as SKILL
import turn as TURN


POLICY_PATH = "data/optional-state-effect-contract-policy.json"
STATE = "_optional_state_effect_contracts"
VERSION = 1
COLOSSUS_ROUND_COUNTING = "following_rounds_v1"

GLOBAL = frozenset(("ERRATA-090", "ERRATA-094", "ERRATA-095"))
ACTIVATED = frozenset(("ERRATA-056", "SB-099", "SB-107", "SB-110", "FAN-104"))
COMPLETION_IDS = GLOBAL | ACTIVATED


def _policy(rules):
    cached = getattr(rules, "_optional_state_effect_contract_policy", None)
    if cached is not None:
        return cached
    path = Path(rules.root) / POLICY_PATH
    if not path.is_file():
        staged = Path(__file__).resolve().parent.parent / POLICY_PATH
        if staged.is_file():
            path = staged
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or set(data.get("completion_ids", ())) != COMPLETION_IDS:
        raise ValueError("optional state-effect policy needs the exact eight reviewed clauses")
    clauses = data.get("clauses")
    if not isinstance(clauses, dict) or set(clauses) != COMPLETION_IDS:
        raise ValueError("optional state-effect clause table changed")
    for relative, digest in data.get("source_files", {}).items():
        actual = hashlib.sha256((Path(rules.root) / relative).read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError("optional state-effect source changed: " + relative)
    for clause_id, row in clauses.items():
        if row.get("id") != clause_id or not isinstance(row.get("sources"), list) or not row["sources"]:
            raise ValueError("optional state-effect source identity changed: " + clause_id)
    rules._optional_state_effect_contract_policy = data
    return data


def clause(rules, clause_id):
    if clause_id not in COMPLETION_IDS:
        raise ValueError("unreviewed optional state-effect clause")
    return _policy(rules)["clauses"][clause_id]


def validate_global_conditions(rules):
    """Prove the three errata rows against native condition definitions."""
    policy = _policy(rules)
    for clause_id in GLOBAL:
        row = policy["clauses"][clause_id]
        actual = rules.condition_effects(row["condition"])
        for expected in row["required_effects"]:
            if not any(all(candidate.get(key) == value for key, value in expected.items()) for candidate in actual):
                raise ValueError("native condition contract changed: " + clause_id)
    return True


def _state(actor, create=False):
    value = actor.spec.get(STATE)
    if value is None and create:
        value = {"version": VERSION, "serial": 0, "effects": []}
        actor.spec[STATE] = value
    if value is None:
        return None
    if (not isinstance(value, dict) or value.get("version") != VERSION
            or type(value.get("serial")) is not int or value["serial"] < 0
            or not isinstance(value.get("effects"), list)):
        raise ValueError("invalid optional state-effect state")
    for record in value["effects"]:
        required = {"id", "clause_id", "rule_id", "owner_id", "target_id", "created_round", "payload"}
        if not isinstance(record, dict) or not required <= set(record):
            raise ValueError("invalid optional state-effect record")
        if record["clause_id"] not in ACTIVATED or not isinstance(record["payload"], dict):
            raise ValueError("unknown optional state-effect record")
        if record["target_id"] != actor.entity_id:
            raise ValueError("optional state-effect target identity changed")
    return value


def records(actor, rule_id=None):
    state = _state(actor)
    rows = [] if state is None else state["effects"]
    import combat_timing as CLOCK
    rows = rows + [record for record in CLOCK.records(actor)
                   if record.get("optional_clause_id") in ("SB-107", "SB-110")]
    return [row for row in rows if rule_id is None or row["rule_id"] == rule_id]


def black_yin_source_options(rules, *, decision=None):
    """Resolve the explicit Korean/English movement conflict through source policy."""
    import source_policy as SOURCE_POLICY
    from source_context import verified_source
    verified_source(rules, {"file": "source-audit/blessed-and-damned-black-yin.txt",
        "sha256": "9f4602c800dc49a421a3625b40384df7e404582f3c9a9694306216914ef32e93"},
        label="English Black Yin movement", source_root="source-audit")
    document = {"schema": 1, "id": "optional/black-yin-movement", "variants": [{
        "rule_id": clause(rules, "SB-110")["rule_id"],
        "source": {"file": "input/supp-blessings.md",
            "sha256": "de4cdcd5c632b18bb2bbc600693362aa3347b4f66c89c724991b944102aa73b6"},
        "values": {"variant": {"$input": "source_text"},
            "english_excerpt_sha256": "9f4602c800dc49a421a3625b40384df7e404582f3c9a9694306216914ef32e93"},
        "inputs": {"source_text": {"type": "string", "authority": "gm",
            "decision_kind": "source_conflict", "choices": ["korean_to_one", "english_decrease_one"],
            "question": "Black Yin: Korean sets movement to 1; English decreases it by 1. Which source applies?"}}}]}
    return SOURCE_POLICY.resolve(rules, document,
        decisions=None if decision is None else {"source_text": decision})


def _blessing_payload(rules, clause_id, source_choice):
    payload = deepcopy(clause(rules, clause_id)["effects"])
    if clause_id == "SB-110" and source_choice is not None:
        receipt = black_yin_source_options(rules, decision=source_choice["decision"])
        if receipt != source_choice["receipt"] or receipt["status"] != "PolicyValuesReady":
            raise ValueError("Black Yin movement needs its original scoped source choice")
        if receipt["values"]["variant"] == "english_decrease_one":
            payload.pop("movement_set")
            payload["movement_add"] = -1
    return payload


def _feature_values(actor):
    values = []
    for field in ("feats", "gifts", "techniques"):
        raw = actor.spec.get(field, [])
        if not isinstance(raw, (list, tuple)):
            raise ValueError(field + " ownership must be a list")
        values.extend(raw)
    return values


def acquired_source(actor, clause_id):
    row = clause(actor.r, clause_id)
    uid = row.get("rule_id")
    if not isinstance(uid, str):
        return None
    matches = [value for value in _feature_values(actor) if value == uid]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("optional feature requires one exact acquired source")
    if actor.r._selected_rule(matches[0]) != uid:
        raise ValueError("selected optional feature variant requires its own policy")
    return matches[0]


def _require_owner(engine, actor, clause_id):
    import world_entities as WORLD
    if WORLD.actor_index(engine).get(actor.entity_id) is not actor:
        raise ValueError("actual registered feature owner required")
    source = acquired_source(actor, clause_id)
    if source is None:
        raise ValueError("actual acquired optional feature required: " + clause_id)
    if not engine.encounter_active or engine.round_start_seconds is None:
        raise ValueError("optional combat feature requires an open round")
    if not getattr(actor, "on_field", True) or actor.captured or actor.fainted:
        raise ValueError("optional feature owner must be present and able to act")
    return source


def _allies(engine, actor, *, range_m=None):
    import world_entities as WORLD
    index = WORLD.actor_index(engine)
    if getattr(actor, "side", None) is None:
        raise ValueError("allied effect requires an actual side")
    result = []
    for target in index.values():
        if target is actor or getattr(target, "side", None) != actor.side:
            continue
        if not getattr(target, "on_field", True) or target.captured:
            continue
        if range_m is not None:
            distance = WORLD.distance_known(actor, target)
            if distance is None:
                raise ValueError("ranged allied effect requires observed grid locations")
            if distance > range_m:
                continue
        result.append(target)
    return result


def activation_participants(engine, actor, clause_id, *, target=None, targets=()):
    """Read-only participant selection used before the atomic state transition."""
    row = clause(engine.r, clause_id)
    if clause_id in GLOBAL:
        raise ValueError("global condition clauses have no feature activation")
    if clause_id == "SB-099":
        if target is None or targets:
            raise ValueError("Colossus March requires exactly one target")
        if target.kind not in row["target_kinds"]:
            raise ValueError("Colossus March target must be a trainer or Pokemon")
        return (target,)
    if target is not None:
        raise ValueError("this optional feature does not take one target")
    if clause_id == "ERRATA-056":
        if targets:
            raise ValueError("Go, Fight, Win! affects every present ally")
        return tuple(_allies(engine, actor))
    if clause_id in ("SB-107", "SB-110"):
        eligible = _allies(engine, actor, range_m=row["range_m"])
        if not targets:
            return tuple(eligible)
        chosen = list(targets)
        if len({id(x) for x in chosen}) != len(chosen) or any(x not in eligible for x in chosen):
            raise ValueError("chosen allies must be distinct present allies within five metres")
        return tuple(chosen)
    if clause_id == "FAN-104":
        if targets:
            raise ValueError("Aiming Down the Sights targets only its owner")
        return ()
    raise ValueError("unknown optional activation")


def _spend(engine, actor, row, key, *, order=None):
    ap = row.get("ap", 0)
    if type(ap) is not int or ap < 0:
        raise ValueError("optional feature AP cost changed")
    if AP.available(actor) < ap:
        raise ValueError("optional feature lacks available AP")
    frequency = row.get("frequency", {"kind": "at_will"})
    kind, cap = FREQUENCY.parse({"kind": frequency.get("kind"), "uses": frequency.get("cap", 1)})
    if kind in ("scene", "daily") and not FREQUENCY.activation_allowed(
            actor, key, {"kind": kind, "uses": cap}, engine=engine, action_actor=actor):
        raise ValueError("optional feature frequency exhausted")
    if row["id"]=="ERRATA-056":
        import order_actions as ORDERS
        ORDERS.spend(engine,actor,row["rule_id"],action=row["action"],
                     subject=key,communication=order)
    elif not TURN.spend(engine, actor, row["action"], row["id"]):
        raise ValueError("optional feature action is unavailable")
    if ap:
        AP.charge(actor, ap, mode="spend")
    if kind in ("scene", "daily"):
        FREQUENCY.consume_activation(actor, key, {"kind": kind, "uses": cap}, engine=engine, action_actor=actor)


def _install(target, owner, clause_id, row, payload, *, expires_round=None,
             owner_turn_start=None):
    state = _state(target, create=True)
    state["serial"] += 1
    record = {
        "id": "optional-state:" + target.entity_id + ":" + str(state["serial"]),
        "clause_id": clause_id,
        "rule_id": row["rule_id"],
        "owner_id": owner.entity_id,
        "target_id": target.entity_id,
        "created_round": row.get("created_round", 0),
        "payload": deepcopy(payload),
    }
    if expires_round is not None:
        record["expires_round"] = expires_round
    if owner_turn_start is not None:
        record["owner_turn_start"] = owner_turn_start
    state["effects"].append(record)
    return record


def activate(engine, actor, clause_id, participants=(), *, choice=None, communication=None):
    """Activate one reviewed feature inside ``state_grants.transition``."""
    row = clause(engine.r, clause_id)
    source = _require_owner(engine, actor, clause_id)
    participants = tuple(participants)
    expected = activation_participants(
        engine, actor, clause_id,
        target=participants[0] if clause_id == "SB-099" and participants else None,
        targets=participants if clause_id in ("SB-107", "SB-110") else (),
    )
    if tuple(expected) != participants:
        raise ValueError("staged optional feature participants changed")

    if communication is not None and (clause_id!="ERRATA-056" or type(communication) is not dict
            or set(communication)!={target.entity_id for target in participants}):
        raise ValueError("exact per-ally established Order communication requests required")
    key = clause_id
    if clause_id == "ERRATA-056":
        if choice not in row["choices"]:
            raise ValueError("Go, Fight, Win! needs one reviewed cheer choice")
        key += ":" + choice
    if clause_id in ("SB-107", "SB-110") or clause_id == "ERRATA-056" and choice == "evasion":
        import combat_timing as CLOCK
        CLOCK.current(engine)
    source_choice = None
    if clause_id == "SB-110" and choice is not None:
        receipt = black_yin_source_options(engine.r, decision=choice)
        if receipt["status"] != "PolicyValuesReady":
            raise ValueError("complete scoped Black Yin source choice required")
        source_choice = {"decision": deepcopy(choice), "receipt": receipt}
    order=None
    if clause_id=="ERRATA-056":
        import order_actions as ORDERS
        order={"status":"delivered","recipients":{target.entity_id:ORDERS.delivery(engine,actor,target,row["rule_id"],communication=None if communication is None else communication[target.entity_id]) for target in participants}}
    _spend(engine, actor, row, key, order=order)

    if clause_id == "ERRATA-056":
        effect = row["choices"][choice]
        if "stage" in effect:
            stat = actor.spec.get("optional_state_choices", {}).get(clause_id)
            if stat not in effect["stage"]["one_of"]:
                raise ValueError("defense cheer needs an explicit Defense or Special Defense choice")
            for target in participants:
                engine.change_stage(target, stat, effect["stage"]["delta"])
        elif choice == "temp_hp":
            amount = SKILL.effective_rank(engine.r, actor, effect["skill"])
            import temporary_hp as TEMP_HP
            for target in participants:
                TEMP_HP.grant(engine, target, amount, provenance={"source": row["rule_id"], "owner_id": actor.entity_id})
        else:
            # One round ends at the original initiative count, independently
            # of when a faster/slower owner takes their next turn.
            import effect_lifetimes as LIFETIMES
            import combat_timing as CLOCK
            effect_plan = {"type": "evasion_mod", "value": effect["evasion"], "duration": "1라운드"}
            for target in participants:
                record = LIFETIMES.prepare(engine, actor, target, effect_plan, row["rule_id"])
                record.update(optional_clause_id=clause_id, optional_owner_id=actor.entity_id,
                              optional_created_round=engine.round_no, optional_created_count=CLOCK.current(engine))
                CLOCK.install(engine, target, record)
    elif clause_id == "SB-099":
        # Same-source interpretation: the next three rounds finish at R+3 EOR.
        # An absent basis reconstructs the actual former R+2 producer only;
        # completed/active legacy records never acquire a new deadline on read.
        basis = COLOSSUS_ROUND_COUNTING
        record = _install(participants[0], actor, clause_id, dict(row, created_round=engine.round_no),
                 row["effects"], expires_round=engine.round_no + row["rounds"] - int(basis is None))
        if basis is not None:
            record["round_counting"] = basis
    elif clause_id in ("SB-107", "SB-110"):
        import effect_lifetimes as LIFETIMES
        import combat_timing as CLOCK
        field = "accuracy" if clause_id == "SB-107" else "evasion"
        for target in participants:
            payload = _blessing_payload(engine.r, clause_id, source_choice)
            record = LIFETIMES.prepare(engine, actor, target,
                {"type": field + "_mod", "value": payload.pop(field),
                 "duration": str(row["rounds"]) + "라운드"}, row["rule_id"])
            record.update(optional_clause_id=clause_id, clause_id=clause_id,
                          rule_id=row["rule_id"], owner_id=actor.entity_id,
                          target_id=target.entity_id, created_round=engine.round_no,
                          created_count=CLOCK.current(engine), payload=payload,
                          stages_reset=False)
            if clause_id == "SB-110":
                record["source_choice"] = deepcopy(source_choice)
            CLOCK.install(engine, target, record)
    elif clause_id == "FAN-104":
        deadline = actor.custom_conditions.get("combat_turn_serial", 0) + 1
        _install(actor, actor, clause_id, dict(row, created_round=engine.round_no),
                 row["effects"], owner_turn_start=deadline)
    engine.time_actors((actor, *participants))
    engine.log("    " + actor.name + ": " + clause_id + " activated", row["rule_id"])
    return {"clause_id": clause_id, "targets": [x.entity_id for x in participants], "source": source}


def combat_stage_delta(actor, stat):
    result = 0
    for record in records(actor):
        stages = record["payload"].get("combat_stage", {})
        value = stages.get(stat, 0)
        if type(value) is not int:
            raise ValueError("optional combat-stage contribution must be an integer")
        result += value
    return result


def staged_value(actor, stat, value):
    if stat in ("atk", "spe") and any(r["clause_id"] == "SB-099" for r in records(actor)):
        return value // 2
    return value


def evasion_bonus(actor):
    return sum(record["payload"].get("evasion", 0) for record in records(actor))


def movement_addition(actor):
    return sum(record["payload"].get("movement_add", 0) for record in records(actor))


def movement_limit(actor, value):
    replacements = [record["payload"]["movement_set"] for record in records(actor)
                    if "movement_set" in record["payload"]]
    return min([value, *replacements]) if replacements else value


def _ranged_weapon(actor, move):
    attack = move.get("_weapon_attack") if isinstance(move, dict) else None
    entry = actor.custom_conditions.get("equipped_weapons", {}).get(attack.get("key")) if isinstance(attack, dict) else None
    return (move.get("class") in ("물리", "특수") and isinstance(entry, dict)
            and entry.get("weapon", {}).get("kind") == clause(actor.r, "FAN-104")["weapon_kind"])


def begin_move(engine, actor, target, move, completion_id):
    """Consume one pending aim into the actual native Move's existing receipt."""
    import move_activation as ACTIVATION
    current = ACTIVATION._require_started_event_use(engine, actor, actor if target is None else target, move["id"],
        scope_error="aiming needs the actual started native Move")
    row = getattr(engine, "_move_completions", {}).get(completion_id)
    if row is None or row["actor"] is not actor or row["move_id"] != move["id"]:
        raise ValueError("aiming needs its actual Move completion")
    if target is None:
        scopes = getattr(engine, "_empty_field_activation_scopes", ())
        if not scopes:
            raise ValueError("aiming needs the actual empty area activation")
        scope = ACTIVATION.require_empty_field_scope(engine, actor, move["id"], scopes[-1]["token"])
        if (row.get("activation") != "empty_area_field" or row["phase"] != "applying"
                or not row["sealed"] or row["targets"] or row["started"] or row["results"]
                or row["post_effects"] != scope["effects"] or row["field_cells"] != scope["cells"]
                or row["profile"] != scope["profile"]):
            raise ValueError("aiming needs its actual empty area completion")
    elif (target not in row["targets"] or target.entity_id not in row["started"]
            or row["phase"] != "targets"):
        raise ValueError("aiming needs its actual Move completion")
    if "optional_aiming" not in row:
        chosen = [record for record in records(actor)
                  if record["clause_id"] == "FAN-104" and _ranged_weapon(actor, move)]
        row["optional_aiming"] = deepcopy(chosen)
        state = _state(actor)
        if chosen:
            state["effects"] = [record for record in state["effects"] if record not in chosen]
            if not state["effects"]:
                actor.spec.pop(STATE, None)
    current["optional_state_completion"] = completion_id


def attack_modifiers(actor, move, *, engine=None, target=None):
    """Preview pending aim, or read this native Move's already consumed aim."""
    accuracy = 0
    critical = 0
    selected = [record for record in records(actor)
                if record["clause_id"] == "FAN-104" and _ranged_weapon(actor, move)]
    scopes = () if engine is None else getattr(engine, "_event_use_scopes", ())
    if (scopes and scopes[-1]["actor"] is actor and scopes[-1]["target"] is target
            and scopes[-1].get("move_id") == move.get("id")):
        completion_id = scopes[-1].get("optional_state_completion")
        row = getattr(engine, "_move_completions", {}).get(completion_id)
        if (row is None or row["actor"] is not actor or row["move_id"] != move["id"]
                or target not in row["targets"] or target.entity_id not in row["started"]
                or "optional_aiming" not in row):
            raise ValueError("aiming accuracy needs its bound native Move completion")
        selected = row["optional_aiming"]
    for record in selected:
        payload = record["payload"]
        accuracy += payload["accuracy"]
        critical += payload["critical_range"]
    return accuracy, critical


def reset_stages(actor):
    """Clear bounded combat components, retaining each movement deadline."""
    for record in records(actor):
        if record["clause_id"] in ("SB-107", "SB-110"):
            record["payload"].pop("combat_stage", None)
            record.pop("accuracy_modifier", None)
            record.pop("evasion_modifier", None)
            record["stages_reset"] = True


def start_turn(engine, owner):
    """Expire owner-next-turn effects after the actual turn serial advances."""
    import world_entities as WORLD
    index = WORLD.actor_index(engine)
    serial = owner.custom_conditions.get("combat_turn_serial", 0)
    for target in index.values():
        state = _state(target)
        if state is None:
            continue
        state["effects"] = [record for record in state["effects"]
                            if not (record.get("owner_id") == owner.entity_id
                                    and record.get("owner_turn_start") is not None
                                    and serial >= record["owner_turn_start"])]
        if not state["effects"]:
            target.spec.pop(STATE, None)
    return True


def finish_round(engine):
    """Commit third-round Colossus stages, then expire round-owned records."""
    import world_entities as WORLD
    index = WORLD.actor_index(engine)
    for target in index.values():
        state = _state(target)
        if state is None:
            continue
        expired = [record for record in state["effects"]
                   if record.get("expires_round") is not None
                   and record["expires_round"] <= engine.round_no]
        for record in expired:
            if record["clause_id"] == "SB-099":
                for stat, delta in record["payload"]["expiry_stage"].items():
                    engine.change_stage(target, stat, delta)
        state["effects"] = [record for record in state["effects"] if record not in expired]
        if not state["effects"]:
            target.spec.pop(STATE, None)
    return True


def end_encounter(engine, actors):
    for actor in actors:
        _state(actor)
        actor.spec.pop(STATE, None)


def validate_world(engine):
    import world_entities as WORLD
    index = WORLD.actor_index(engine)
    _policy(engine.r)
    for completion in getattr(engine, "_move_completions", {}).values():
        for record in completion.get("optional_aiming", ()):
            if (record.get("clause_id") != "FAN-104"
                    or record.get("rule_id") != clause(engine.r, "FAN-104")["rule_id"]
                    or record.get("owner_id") != completion["actor"].entity_id
                    or record.get("target_id") != completion["actor"].entity_id
                    or record.get("payload") != clause(engine.r, "FAN-104")["effects"]):
                raise ValueError("consumed aiming Move receipt changed")
    for target in index.values():
        import combat_timing as CLOCK
        for record in CLOCK.records(target):
            if "optional_clause_id" not in record:
                continue
            if record["optional_clause_id"] in ("SB-107", "SB-110"):
                clause_id = record["optional_clause_id"]
                row = clause(engine.r, clause_id)
                owner = index.get(record.get("owner_id"))
                born, count = record.get("created_round"), record.get("created_count")
                if (owner is None or acquired_source(owner, clause_id) != row["rule_id"]
                        or type(born) is not int or not 1 <= born <= engine.round_no
                        or type(count) is not int or type(record.get("stages_reset")) is not bool):
                    raise ValueError("optional three-round source or activation count changed")
                payload = _blessing_payload(engine.r, clause_id, record.get("source_choice"))
                field = "accuracy" if clause_id == "SB-107" else "evasion"
                value = payload.pop(field)
                if record["stages_reset"]:
                    payload.pop("combat_stage", None)
                expected = {"source": row["rule_id"], "effect_contract": True,
                    "timing_text": str(row["rounds"]) + "라운드",
                    "count_deadline": (born + row["rounds"], count), "encounter_end": True,
                    "optional_clause_id": clause_id, "clause_id": clause_id,
                    "rule_id": row["rule_id"], "owner_id": owner.entity_id,
                    "target_id": target.entity_id, "created_round": born, "created_count": count,
                    "payload": payload, "stages_reset": record["stages_reset"],
                    "owned_statuses": set(), "installing": False}
                if clause_id == "SB-110":
                    expected["source_choice"] = record.get("source_choice")
                if not record["stages_reset"]:
                    expected[field + "_modifier"] = value
                if (set(record) != set(expected)
                        or any((tuple(record[k]) if k == "count_deadline" else record[k]) != v
                               for k, v in expected.items())):
                    raise ValueError("optional three-round component or original deadline changed")
                continue
            if record.get("optional_clause_id") != "ERRATA-056":
                raise ValueError("unknown optional common-clock source")
            owner = index.get(record.get("optional_owner_id"))
            row = clause(engine.r, "ERRATA-056")
            born, count = record.get("optional_created_round"), record.get("optional_created_count")
            expected = {"source": row["rule_id"], "effect_contract": True, "timing_text": "1라운드",
                        "count_deadline": (born + 1, count) if type(born) is int else None,
                        "encounter_end": True, "evasion_modifier": row["choices"]["evasion"]["evasion"],
                        "optional_clause_id": "ERRATA-056", "optional_owner_id": getattr(owner,"entity_id",None),
                        "optional_created_round": born, "optional_created_count": count,
                        "owned_statuses": set(), "installing": False}
            if (owner is None or acquired_source(owner,"ERRATA-056") != row["rule_id"]
                    or type(born) is not int or not 0 <= born <= engine.round_no or type(count) is not int
                    or set(record) != (set(expected)|({'native_order_handoff'} if 'native_order_handoff' in record else set()))
                    or any((tuple(record[k]) if k == "count_deadline" else record[k]) != v for k,v in expected.items())):
                raise ValueError("optional one-round source, value or original count changed")
        for record in records(target):
            owner = index.get(record["owner_id"])
            if owner is None or acquired_source(owner, record["clause_id"]) != record["rule_id"]:
                raise ValueError("optional state-effect owner or acquired source changed")
            row = clause(engine.r, record["clause_id"])
            if record["clause_id"] == "ERRATA-056":
                raise ValueError("one-round cheer requires the shared exact-count clock")
            if record["clause_id"] in ("SB-107", "SB-110") and "optional_clause_id" not in record:
                raise ValueError("three-round blessings require the shared exact-count clock")
            if row["rule_id"] != record["rule_id"]:
                raise ValueError("optional state-effect policy identity changed")
            if record["clause_id"] == "SB-099":
                born = record["created_round"]
                current = "round_counting" in record
                if (current and record["round_counting"] != "following_rounds_v1"
                        or type(born) is not int or not 0 <= born <= engine.round_no
                        or type(record.get("expires_round")) is not int
                        or record["expires_round"] != born + row["rounds"] - int(not current)
                        or record["payload"] != row["effects"]):
                    raise ValueError("Colossus March original round-counting basis changed")
    return True
