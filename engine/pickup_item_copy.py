"""Pickup's physical held-item copy and encounter-end cleanup contract.

This adapter is deliberately source-specific.  It reuses the physical object,
held equipment, item effect, frequency and transaction owners instead of
introducing another inventory abstraction.
"""
from copy import deepcopy
import json
from pathlib import Path

import common_checks as C


SOURCE = "ability/픽업"
NAME = "픽업"
ACTIVE = "pickup_item_copies"
HISTORY = "pickup_item_copy_history"
SEQUENCE = "pickup_item_copy_sequence"
CHOICE = "pickup_item_copy_choice"
CHOICE_SEQUENCE = "pickup_item_choice_sequence"
EXPIRY_SOURCE = {"file": "input/db/abilities.csv", "sha256": "87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae"}
EXPIRY_INTERPRETATIONS = ("copy_unconsumed", "original_unconsumed")
COPY_EFFECT = {
    "type": "copy_item",
    "target": "target",
    "until": "encounter_end",
    "note": "소모품이면 원본도 소멸",
}
CAPABILITY_EFFECT = {"type": "grant_capability", "capability": "청소부"}


def _semantic(effect):
    return {key: value for key, value in effect.items() if not key.startswith("_")}


def registration(rules, name):
    """Bind only the selected CSV R0455 Pickup source and reviewed payload."""
    if name not in (NAME, SOURCE):
        return None
    if rules._selected_rule(SOURCE) != SOURCE:
        raise ValueError("Pickup selected source changed")
    rules.selection.require_supported_version(SOURCE)
    rows = json.loads((Path(rules.root) / "output/entities/abilities.json").read_text(encoding="utf-8"))
    row = next((entry for entry in rows if entry.get("id") == SOURCE), None)
    source = None if row is None else row.get("_source")
    if (row is None or row.get("name") != NAME or row.get("eng") != "Pickup"
            or row.get("frequency") != "장면 - 신속 행동"
            or row.get("action") != "신속 행동"
            or not isinstance(source, dict) or source.get("file") != "db/abilities.csv"
            or source.get("record_span") != [455, 455]):
        raise ValueError("Pickup exact CSV R0455 source changed; review required")
    effects = rules.ability_effects.get(NAME)
    if effects != [COPY_EFFECT, CAPABILITY_EFFECT]:
        raise ValueError("Pickup reviewed copy/capability payload changed")
    return {"name": NAME, "source_id": SOURCE, "row": row}


def deferred_registration(rules, effect):
    return effect.get("_rule_id") == SOURCE and _semantic(effect) in (COPY_EFFECT, CAPABILITY_EFFECT)


def _is_consumable(rules, item_id):
    effects, header = rules.item_effects(item_id)
    if effects is None or header.get("id") != item_id:
        raise ValueError("Pickup needs the selected actual item rule")
    return header.get("use") == "consumable" or header.get("category") in ("약", "음식")


def _records(actor, key):
    rows = actor.spec.get(key, [])
    if not isinstance(rows, list):
        raise ValueError("Pickup copy ledger must be a list")
    return rows


def _next_slot(actor, requested):
    import held_equipment as HELD
    if requested is not None and requested not in ("held:1", "held:2"):
        raise ValueError("Pickup destination must select held:1 or held:2")
    occupied = {row["slot_id"] for row in HELD.entries(actor)}
    slot = requested or next((value for value in ("held:1", "held:2") if value not in occupied), None)
    if slot is None or slot in occupied:
        raise ValueError("Pickup user has no available actual held-item slot")
    return slot


def _ability_owned(actor):
    if actor.abilities_suppressed:
        return False
    return any(registration(actor.r, value) is not None for value in actor.abilities)


def _common(engine, actor, target):
    import held_equipment as HELD
    import csv_item_form_contracts as CSV_FORMS
    import partial_entities as PARTIAL
    import world_entities as WORLD

    registration(engine.r, SOURCE)
    PARTIAL.require_complete(actor, "Pickup source")
    PARTIAL.require_complete(target, "Pickup target")
    index = WORLD.require_actors(engine, actor, target)
    CSV_FORMS.require_independent(engine, actor)
    if target is not actor:
        CSV_FORMS.require_independent(engine, target)
    if not engine.encounter_active:
        raise ValueError("Pickup requires an active encounter")
    if not _ability_owned(actor):
        raise ValueError("actual unsuppressed acquired Pickup ability required")
    if not getattr(actor, "on_field", False) or not getattr(target, "on_field", False):
        raise ValueError("Pickup requires on-field combatants")
    distance = WORLD.distance_known(actor, target)
    if distance is None or distance > 5:
        raise ValueError("Pickup target must be at a known distance within 5 meters")
    HELD.require_resolved(actor)
    if target is not actor:
        HELD.require_resolved(target)
    return index


def _prepare(engine, actor, target, held_selection, destination_slot):
    import held_equipment as HELD
    import items as ITEMS
    import world_entities as WORLD

    index = _common(engine, actor, target)
    selected = ITEMS.selected_equipment(target, held_selection, ("held",))
    original_id = selected.get("instance_id")
    original = getattr(engine, "_physical_objects", {}).get(original_id)
    if not isinstance(original_id, str) or not isinstance(original, dict):
        raise ValueError("Pickup must select an actual physical held item")
    WORLD.require_usable_object(original)
    if (original.get("kind") != "item_instance"
            or original.get("equipped_by") != target.entity_id
            or original.get("item_rule_id") != selected.get("item_id")):
        raise ValueError("Pickup selected item and actual holder disagree")
    item_id = original["item_rule_id"]
    effects, header = engine.r.item_effects(item_id)
    if effects is None or header.get("id") != item_id or selected.get("name") is None:
        raise ValueError("Pickup selected item has no complete runtime definition")
    sequence = C.integer(actor.spec.get(SEQUENCE, 0), "Pickup copy sequence", 0) + 1
    copy_id = "pickup-copy:" + actor.entity_id + ":" + str(sequence)
    if copy_id in WORLD.entity_index(engine):
        raise ValueError("Pickup copy physical identity already exists")
    slot = _next_slot(actor, destination_slot)
    # Pure destination validation.  Giving an explicit unused slot prevents a
    # new physical copy from being folded into a legacy same-name row.
    HELD.prepare(actor, selected["name"], item_id, copy_id, slot)
    return {
        "source": SOURCE,
        "sequence": sequence,
        "copy_instance_id": copy_id,
        "original_instance_id": original_id,
        "item_id": item_id,
        "item_name": selected["name"],
        "consumable": _is_consumable(engine.r, item_id),
        "destination_slot": slot,
        "target_id": target.entity_id,
        "user_id": actor.entity_id,
        "index": index,
    }


def _expiry_basis(plan):
    return {key: deepcopy(plan[key]) for key in (
        "source", "sequence", "user_id", "target_id", "original_instance_id",
        "copy_instance_id", "item_id", "destination_slot")}


def _expiry_document(basis):
    return {"schema": 1, "id": "native/pickup-copy-expiry", "variants": [{
        "rule_id": SOURCE, "source": EXPIRY_SOURCE,
        "values": {"interpretation": {"$input": "interpretation"}, "basis": deepcopy(basis)},
        "inputs": {"interpretation": {"type": "string", "authority": "gm",
            "decision_kind": "source_conflict", "choices": list(EXPIRY_INTERPRETATIONS),
            "question": "Choose the unstated consumption subject in the same Korean R455 text: copy or original. These are GM interpretations, not different English editions."}}}]}


def _expiry_resolution(engine, basis, choice=None):
    from source_context import verified_source
    import source_policy as POLICY

    verified_source(engine.r, EXPIRY_SOURCE, label="Pickup actual R455 expiry interpretation")
    return POLICY.resolve(engine.r, _expiry_document(basis), decisions={} if choice is None else {"interpretation": choice})


def source_choices(engine, actor, target, *, held_selection=None, destination_slot=None):
    """Pure scoped query; choosing an expiry reading never authorizes a held selection."""
    plan = _prepare(engine, actor, target, held_selection, destination_slot)
    return _expiry_resolution(engine, _expiry_basis(plan))


def _expiry_decision(engine, plan, choice):
    basis = _expiry_basis(plan)
    if choice is None:
        return {"interpretation": "copy_unconsumed", "authority": "authored_default",
                "source": deepcopy(EXPIRY_SOURCE), "basis": basis}
    resolved = _expiry_resolution(engine, basis, choice)
    if resolved["status"] != "PolicyValuesReady":
        raise ValueError("complete scoped Pickup expiry decision required")
    return {"interpretation": resolved["values"]["interpretation"], "authority": "gm",
            "source": deepcopy(EXPIRY_SOURCE), "basis": basis,
            "choice": deepcopy(choice), "policy": resolved}


def _expiry_name(engine, record):
    # An unmarked record is an actual old producer receipt, not a new GM choice.
    if "expiry_decision" not in record:
        return "copy_unconsumed"
    decision = record["expiry_decision"]
    if (not isinstance(decision, dict) or decision.get("source") != EXPIRY_SOURCE
            or decision.get("basis") != _expiry_basis(record)):
        raise ValueError("Pickup expiry decision needs its actual producing identities")
    if decision.get("authority") == "authored_default":
        if set(decision) != {"interpretation", "authority", "source", "basis"} or decision["interpretation"] != "copy_unconsumed":
            raise ValueError("Pickup authored expiry default changed")
    elif decision.get("authority") == "gm":
        if set(decision) != {"interpretation", "authority", "source", "basis", "choice", "policy"}:
            raise ValueError("Pickup GM expiry decision changed")
        from source_context import verified_source
        import root_resolution as RESOLUTION
        verified_source(engine.r, EXPIRY_SOURCE, label="Pickup original R455 expiry interpretation")
        document = _expiry_document(decision["basis"])
        fixed = {"policy_id": document["id"], "selected_id": SOURCE, "selected_version": None,
                 "definition_hash": RESOLUTION.fingerprint(document)}
        choice, policy = decision["choice"], decision["policy"]
        if (type(choice) is not dict or set(choice) != {"value", "reason", "scope"}
                or choice["value"] not in EXPIRY_INTERPRETATIONS
                or choice["value"] != decision["interpretation"]
                or type(choice["scope"]) is not dict or set(choice["scope"]) != set(fixed) | {"profile_hash"}
                or any(choice["scope"][key] != value for key, value in fixed.items())
                or any(not isinstance(text, str) or not text.strip()
                       for text in (choice["reason"], choice["scope"]["profile_hash"]))):
            raise ValueError("Pickup original scoped expiry decision required")
        # This is a producing receipt, not authority to make another copy under today's profile.
        if (type(policy) is not dict or any(policy.get(key) != value for key, value in fixed.items())
                or policy.get("status") != "PolicyValuesReady" or policy.get("source") != EXPIRY_SOURCE
                or policy.get("profile_hash") != choice["scope"]["profile_hash"]
                or policy.get("decision_scope") != choice["scope"]
                or policy.get("values") != {"interpretation": choice["value"], "basis": decision["basis"]}
                or policy.get("input_values") != {"interpretation": choice["value"]}
                or policy.get("decision_evidence") != [{"input": "interpretation", "reason": choice["reason"],
                    "decision_kind": "source_conflict", "scope": choice["scope"]}]
                or policy.get("obligations") != []
                or policy.get("inputs_hash") != RESOLUTION.fingerprint({"context": {}, "decisions": {"interpretation": choice}, "state": {}})):
            raise ValueError("Pickup producing expiry source scope changed")
    else:
        raise ValueError("Pickup expiry authority required")
    return decision["interpretation"]


def _choice_basis(engine, actor, target, destination_slot):
    import held_equipment as HELD
    _common(engine, actor, target)
    return {"source": deepcopy(EXPIRY_SOURCE), "user_id": actor.entity_id,
        "target_id": target.entity_id, "user_held": deepcopy(HELD.entries(actor)),
        "target_held": deepcopy(HELD.entries(target)),
        "user_capacity": HELD.capacity(actor), "target_capacity": HELD.capacity(target),
        "sequence": actor.spec.get(SEQUENCE, 0), "destination_slot": destination_slot,
        "round": engine.round_no, "elapsed_seconds": engine.elapsed_seconds,
        "owner_turn": actor.custom_conditions.get("combat_turn_serial", 0),
        "active_turn_actor": getattr(getattr(engine, "_active_turn_actor", None), "entity_id", None)}


def _pending(row):
    return C.PendingDecision("The actual held-item owner chooses which item Pickup copies before any payment",
        basis={"choice_id": row["id"], "source": SOURCE, "chooser_id": row["target_id"],
               "options": deepcopy(row["basis"]["target_held"])})


def pending(engine):
    import world_entities as WORLD
    return [_pending(row) for actor in WORLD.actor_index(engine).values()
            if isinstance((row := actor.spec.get(CHOICE)), dict) and row.get("status") == "awaiting_input"]


def cancel_choice(engine, actor, choice_id):
    """The activator may withdraw their own still-unpaid request, including a stale one."""
    import state_grants as GRANTS
    import world_entities as WORLD
    WORLD.require_actors(engine, actor)
    def cancel(staged, actual):
        row = actual.spec.get(CHOICE)
        if not isinstance(row, dict) or row.get("id") != choice_id or row.get("status") != "awaiting_input":
            raise ValueError("actual unpaid Pickup request required")
        row["status"] = "cancelled"
        return deepcopy(row)
    return GRANTS.transition(engine, actor, cancel)


def resolve_choice(engine, chooser, choice_id, *, selection, expiry_choice=None):
    import world_entities as WORLD
    index = WORLD.require_actors(engine, chooser)
    matches = [(actor, actor.spec[CHOICE]) for actor in index.values()
               if isinstance(actor.spec.get(CHOICE), dict) and actor.spec[CHOICE].get("id") == choice_id]
    if len(matches) != 1:
        raise ValueError("actual Pickup held-item request required")
    actor, row = matches[0]
    target = index.get(row["target_id"])
    if chooser is not target:
        raise ValueError("actual Pickup held-item owner must choose")
    choice = row["expiry_choice"] if expiry_choice is None else expiry_choice
    if row["status"] == "completed":
        if selection != row["selection"] or choice != row["settled_expiry_choice"]:
            raise ValueError("completed Pickup decision cannot change")
        return deepcopy(row["result"])
    if row["status"] != "awaiting_input" or row["basis"] != _choice_basis(engine, actor, target, row["destination_slot"]):
        raise ValueError("Pickup held-item request is stale; withdraw it before a new activation")
    return _settle(engine, actor, target, selection, row["destination_slot"], choice, request_id=choice_id)


def apply_effect(engine, actor, target, effect, ctx):
    """The registered ``copy_item`` handler's sole executable path."""
    if _semantic(effect) != COPY_EFFECT or ctx.get("source_id") != SOURCE or not ctx.get("pickup_item_copy_commit"):
        raise ValueError("copy_item requires the reviewed Pickup physical-instance adapter")
    plan = _prepare(engine, actor, target, ctx.get("held_selection"), ctx.get("destination_slot"))
    expiry = _expiry_decision(engine, plan, ctx.get("pickup_expiry_choice"))
    import items as ITEMS
    import world_entities as WORLD

    WORLD.register_object(
        engine,
        plan["copy_instance_id"],
        location=WORLD.location_of(actor),
        reason="Pickup fake physical copy issued from selected held instance",
        kind="item_instance",
        item_rule_id=plan["item_id"],
        owner_id=actor.entity_id,
        source=SOURCE,
    )
    obj = engine._physical_objects[plan["copy_instance_id"]]
    link = {
        "source": SOURCE,
        "sequence": plan["sequence"],
        "user_id": actor.entity_id,
        "target_id": target.entity_id,
        "original_instance_id": plan["original_instance_id"],
        "item_id": plan["item_id"],
        "consumable": plan["consumable"],
        "expires": "encounter_end",
        "status": "active",
        "expiry_decision": expiry,
    }
    obj["pickup_copy"] = deepcopy(link)
    ITEMS.register_item(
        engine,
        actor,
        plan["item_name"],
        source_instance_id=plan["copy_instance_id"],
        as_held=True,
        held_slot=plan["destination_slot"],
    )
    equipped = ITEMS.selected_equipment(actor, plan["copy_instance_id"], ("held",))
    if equipped.get("item_id") != plan["item_id"] or equipped.get("held_slot") != plan["destination_slot"]:
        raise ValueError("Pickup copy did not acquire its actual destination held slot")
    record = {
        **link,
        "copy_instance_id": plan["copy_instance_id"],
        "item_name": plan["item_name"],
        "destination_slot": plan["destination_slot"],
        "issued_at": engine.elapsed_seconds,
    }
    actor.spec[SEQUENCE] = plan["sequence"]
    actor.spec.setdefault(ACTIVE, []).append(record)
    engine.log(
        "    " + actor.name + ": " + plan["item_name"] + " 실물 복사본 "
        + plan["copy_instance_id"] + " 생성 (원본 " + plan["original_instance_id"] + ")",
        SOURCE,
    )
    return deepcopy(record)


def activate(engine, actor, ability, target, *, held_selection=None, destination_slot=None, expiry_choice=None):
    """Pay Pickup once, then create and equip one linked physical copy."""
    reg = registration(engine.r, ability)
    if reg is None:
        raise ValueError("reviewed Pickup source required")
    # Pure preflight catches source/identity/slot failures before staging or cost.
    validate_world(engine)
    _common(engine, actor, target)
    import held_equipment as HELD
    if len(HELD.entries(target)) > 1:
        if held_selection is not None:
            _prepare(engine, actor, target, held_selection, destination_slot)
        destination_slot = _next_slot(actor, destination_slot)
        if HELD.capacity(actor)["count"] >= HELD.capacity(actor)["maximum"]:
            raise ValueError("Pickup user has no available actual held-item slot")
        basis = _choice_basis(engine, actor, target, destination_slot)
        old = actor.spec.get(CHOICE)
        if isinstance(old, dict) and old.get("status") == "awaiting_input":
            if old["basis"] != basis or old["expiry_choice"] != expiry_choice:
                raise ValueError("resolve or withdraw the existing unpaid Pickup request")
            return _pending(old)
        import state_grants as GRANTS
        def request(staged, user, holder):
            actual = _choice_basis(staged, user, holder, destination_slot)
            if actual != basis:
                raise ValueError("Pickup held-item request changed before issue")
            sequence = C.integer(user.spec.get(CHOICE_SEQUENCE, 0), "Pickup held request sequence", 0) + 1
            row = {"id": "pickup-held-choice:" + user.entity_id + ":" + str(sequence),
                "request_sequence": sequence,
                "user_id": user.entity_id, "target_id": holder.entity_id,
                "basis": actual, "destination_slot": destination_slot,
                "expiry_choice": deepcopy(expiry_choice), "status": "awaiting_input"}
            user.spec[CHOICE] = row
            user.spec[CHOICE_SEQUENCE] = sequence
            return _pending(row)
        if target is actor:
            return GRANTS.transition(engine, actor, lambda staged, user: request(staged, user, user))
        return GRANTS.transition(engine, actor, request, participants=(target,))
    if isinstance(actor.spec.get(CHOICE), dict) and actor.spec[CHOICE].get("status") == "awaiting_input":
        raise ValueError("withdraw the existing unpaid Pickup request before a new activation")
    return _settle(engine, actor, target, held_selection, destination_slot, expiry_choice)


def _settle(engine, actor, target, held_selection, destination_slot, expiry_choice, *, request_id=None):
    import held_equipment as HELD
    plan = _prepare(engine, actor, target, held_selection, destination_slot)
    _expiry_decision(engine, plan, expiry_choice)

    import frequency as FREQ
    import state_grants as GRANTS
    import turn as TURN

    def commit(staged, user, holder):
        if request_id is not None:
            row = user.spec.get(CHOICE)
            if (not isinstance(row, dict) or row.get("id") != request_id
                    or row.get("status") != "awaiting_input"
                    or row["basis"] != _choice_basis(staged, user, holder, destination_slot)):
                raise ValueError("Pickup actual holder decision changed before settlement")
        elif len(HELD.entries(holder)) > 1:
            raise ValueError("Pickup needs the actual holder's pending selection")
        key = "ability:" + NAME
        frequency = staged.r.ability_freq.get(NAME)
        if not FREQ.activation_allowed(user, key, frequency, engine=staged, action_actor=user):
            raise ValueError("Pickup Scene frequency exhausted")
        if not TURN.spend(staged, user, "swift", NAME):
            raise ValueError("Pickup Swift action unavailable")
        FREQ.consume_activation(user, key, frequency, engine=staged, action_actor=user)
        # Route the authored copy_item payload through its registered handler.
        import effects_ext as EXT
        result = EXT.h_copy_item(staged, user, holder, COPY_EFFECT, {
            "source_id": SOURCE,
            "pickup_item_copy_commit": True,
            "held_selection": held_selection,
            "destination_slot": destination_slot,
            "pickup_expiry_choice": expiry_choice,
        })
        if request_id is not None:
            row.update(status="completed", selection=held_selection,
                       settled_expiry_choice=deepcopy(expiry_choice), result=deepcopy(result))
        validate_world(staged)
        return result

    participants = () if target is actor else (target,)
    if participants:
        return GRANTS.transition(engine, actor, commit, participants=participants)
    return GRANTS.transition(engine, actor, lambda staged, user: commit(staged, user, user))


def _registered_holder(index, instance_id):
    import items as ITEMS
    found = []
    for actor in index.values():
        for row in ITEMS.equipment_options(actor, ("held",)):
            if row.get("instance_id") == instance_id:
                found.append((actor, row))
    if len(found) > 1:
        raise ValueError("Pickup physical instance has multiple equipment holders")
    return found[0] if found else (None, None)


def _preflight_terminal(engine, index, instance_id, fallback_holder_id):
    import state_grants as GRANTS
    obj = engine._physical_objects[instance_id]
    holder, equipment = _registered_holder(index, instance_id)
    if equipment is not None:
        registration_key = equipment.get("registration_key")
        record = getattr(holder, "_item_reg", {}).get(registration_key)
        if record is None or record.get("instance_id") != instance_id:
            raise ValueError("Pickup terminal equipment receipt disagrees")
        GRANTS.preflight_revoke(holder, record["state_source"])
    carrier_id = obj.get("carrier_id")
    if carrier_id is not None:
        carrier = index.get(carrier_id)
        load = None if carrier is None else carrier.spec.get("_carried_load", {})
        if (carrier is None or load.get("blocked_actions") or load.get("failure_pending")
                or not any(row.get("id") == instance_id for row in load.get("objects", []))):
            raise ValueError("Pickup terminal physical carrier state is unresolved")
    former = obj.get("equipped_by") or carrier_id or fallback_holder_id or obj.get("owner_id")
    if former not in index:
        raise ValueError("Pickup terminal event needs an actual former holder")
    return former


def _destroy_present(engine, index, instance_id, *, source, fallback_holder_id):
    import capability_actions as CAP
    import items as ITEMS
    import world_entities as WORLD

    obj = engine._physical_objects[instance_id]
    lifecycle = WORLD.physical_lifecycle(obj)
    if lifecycle["consumed"] or lifecycle["destroyed"]:
        return "consumed" if lifecycle["consumed"] else "destroyed"
    former = _preflight_terminal(engine, index, instance_id, fallback_holder_id)
    holder, equipment = _registered_holder(index, instance_id)
    carrier_id = obj.get("carrier_id")
    if carrier_id is not None:
        carrier = index[carrier_id]
        remaining = [row for row in carrier.spec["_carried_load"]["objects"] if row.get("id") != instance_id]
        CAP.set_carried(engine, carrier, remaining, "Pickup encounter-end physical expiration")
    if equipment is not None:
        ITEMS._unregister_selected(engine, holder, equipment)
        ITEMS._refresh_unresolved(engine, holder)
    WORLD.finish_physical_use(
        engine,
        obj,
        "destroyed",
        {"source": source, "former_holder_id": former},
    )
    return "destroyed"


def end_encounter(engine, actors=None):
    """Expire every live copy and apply the unconsumed-consumable exception."""
    import world_entities as WORLD
    import equipment_protection as PROTECTION

    index = WORLD.actor_index(engine, () if actors is None else actors)
    validate_world(engine, index)
    plans = []
    for user in index.values():
        for record in _records(user, ACTIVE):
            copy = engine._physical_objects[record["copy_instance_id"]]
            copy_lifecycle = WORLD.physical_lifecycle(copy)
            original = engine._physical_objects[record["original_instance_id"]]
            original_lifecycle = WORLD.physical_lifecycle(original)
            original_protection = None
            if not copy_lifecycle["consumed"] and not copy_lifecycle["destroyed"]:
                _preflight_terminal(engine, index, copy["id"], record["user_id"])
            original_due = record["consumable"] and (
                _expiry_name(engine, record) == "original_unconsumed" or not copy_lifecycle["consumed"])
            if (original_due
                    and not original_lifecycle["consumed"] and not original_lifecycle["destroyed"]):
                holder, equipment = _registered_holder(index, original["id"])
                if equipment is not None:
                    original_protection = PROTECTION.status(engine, holder, equipment, 'destroy')
                if original_protection is None or original_protection['status']=='allowed':
                    _preflight_terminal(engine, index, original["id"], record["target_id"])
            plans.append((user, record, copy_lifecycle, original_protection, original_due))
    for user, record, copy_lifecycle, original_protection, original_due in plans:
        copy_status = _destroy_present(
            engine,
            index,
            record["copy_instance_id"],
            source=SOURCE + "/encounter-end",
            fallback_holder_id=record["user_id"],
        )
        original_status = "retained"
        if original_protection is not None and original_protection['status']!='allowed':
            original_status = "retained_protected"
        elif original_due:
            original_status = _destroy_present(
                engine,
                index,
                record["original_instance_id"],
                source=SOURCE + "/unconsumed-consumable",
                fallback_holder_id=record["target_id"],
            )
        elif record["consumable"]:
            original_status = "retained_copy_consumed"
        completed = deepcopy(record)
        completed.update(ended_at=engine.elapsed_seconds, copy_terminal=copy_status,
                         original_terminal=original_status, status="expired")
        copy = engine._physical_objects[record["copy_instance_id"]]
        copy["pickup_copy"].update(status="expired", ended_at=engine.elapsed_seconds,
                                   copy_terminal=copy_status, original_terminal=original_status)
        user.spec.setdefault(HISTORY, []).append(completed)
    for user in index.values():
        if ACTIVE in user.spec:
            user.spec[ACTIVE] = []
        choice = user.spec.get(CHOICE)
        if isinstance(choice, dict) and choice.get("status") == "awaiting_input":
            choice.update(status="cancelled", cancellation="encounter_end_before_activation")
    validate_world(engine, index)
    return [deepcopy(record) for _, record, _, _, _ in plans]


def _validate_record(engine, index, user, record, *, active):
    import world_entities as WORLD

    if not isinstance(record, dict):
        raise ValueError("Pickup copy record must be a mapping")
    sequence = C.integer(record.get("sequence"), "Pickup copy record sequence", 1)
    required = ("copy_instance_id", "original_instance_id", "item_id", "item_name",
                "user_id", "target_id", "source", "expires", "status")
    if any(not isinstance(record.get(key), str) or not record[key] for key in required):
        raise ValueError("Pickup copy record needs complete stable identities")
    if (record["source"] != SOURCE or record["user_id"] != user.entity_id
            or record["target_id"] not in index or record["expires"] != "encounter_end"
            or record["copy_instance_id"] != "pickup-copy:" + user.entity_id + ":" + str(sequence)
            or type(record.get("consumable")) is not bool):
        raise ValueError("Pickup copy source/owner/lifetime identity mismatch")
    copy = getattr(engine, "_physical_objects", {}).get(record["copy_instance_id"])
    original = getattr(engine, "_physical_objects", {}).get(record["original_instance_id"])
    if not isinstance(copy, dict) or not isinstance(original, dict):
        raise ValueError("Pickup copy and original must remain actual physical records")
    if (copy.get("kind") != "item_instance" or original.get("kind") != "item_instance"
            or copy.get("item_rule_id") != record["item_id"]
            or original.get("item_rule_id") != record["item_id"]):
        raise ValueError("Pickup copy and original item rules disagree")
    link = copy.get("pickup_copy")
    expected = {
        "source": SOURCE,
        "sequence": sequence,
        "user_id": record["user_id"],
        "target_id": record["target_id"],
        "original_instance_id": record["original_instance_id"],
        "item_id": record["item_id"],
        "consumable": record["consumable"],
        "expires": "encounter_end",
    }
    if not isinstance(link, dict) or any(link.get(key) != value for key, value in expected.items()):
        raise ValueError("Pickup physical copy has a broken original-instance link")
    if (("expiry_decision" in link) != ("expiry_decision" in record)
            or link.get("expiry_decision") != record.get("expiry_decision")):
        raise ValueError("Pickup physical copy lost its producing expiry decision")
    _expiry_name(engine, record)
    if record["consumable"] != _is_consumable(engine.r, record["item_id"]):
        raise ValueError("Pickup consumable classification changed")
    WORLD.physical_lifecycle(copy)
    WORLD.physical_lifecycle(original)
    if active:
        if not engine.encounter_active or record["status"] != "active" or link.get("status") != "active":
            raise ValueError("active Pickup copy cannot outlive its encounter")
    else:
        if record["status"] != "expired" or link.get("status") != "expired":
            raise ValueError("Pickup history needs completed encounter-end evidence")
        C.integer(record.get("ended_at"), "Pickup copy end time", 0)
        if link.get("ended_at") != record["ended_at"]:
            raise ValueError("Pickup history and physical copy end times disagree")
    return sequence


def validate_world(engine, index=None):
    import world_entities as WORLD

    index = WORLD.actor_index(engine) if index is None else index
    copy_ids = set()
    for user in index.values():
        choice = user.spec.get(CHOICE)
        if choice is not None:
            if (not isinstance(choice, dict) or choice.get("user_id") != user.entity_id
                    or choice.get("target_id") not in index
                    or choice.get("status") not in ("awaiting_input", "completed", "cancelled")
                    or not isinstance(choice.get("basis"), dict)
                    or choice["basis"].get("source") != EXPIRY_SOURCE
                    or choice["basis"].get("user_id") != user.entity_id
                    or choice["basis"].get("target_id") != choice["target_id"]
                    or choice.get("request_sequence") != C.integer(user.spec.get(CHOICE_SEQUENCE), "Pickup held request sequence", 1)
                    or choice.get("id") != "pickup-held-choice:" + user.entity_id + ":" + str(choice["request_sequence"])):
                raise ValueError("Pickup unpaid request needs its actual owner/source/held basis")
            if choice["status"] == "completed" and (
                    not isinstance(choice.get("result"), dict)
                    or choice["result"].get("copy_instance_id") != "pickup-copy:" + user.entity_id + ":"
                       + str(C.integer(choice["basis"].get("sequence"), "Pickup request copy sequence", 0) + 1)):
                raise ValueError("Pickup completed holder decision needs its actual issued copy")
        active = _records(user, ACTIVE)
        history = _records(user, HISTORY)
        sequence = C.integer(user.spec.get(SEQUENCE, 0), "Pickup copy sequence", 0)
        seen = []
        for record in active:
            seen.append(_validate_record(engine, index, user, record, active=True))
            if record["copy_instance_id"] in copy_ids:
                raise ValueError("Pickup copy identity belongs to multiple records")
            copy_ids.add(record["copy_instance_id"])
        for record in history:
            seen.append(_validate_record(engine, index, user, record, active=False))
            if record["copy_instance_id"] in copy_ids:
                raise ValueError("Pickup copy identity belongs to multiple records")
            copy_ids.add(record["copy_instance_id"])
        if sorted(seen) != list(range(1, sequence + 1)):
            raise ValueError("Pickup copy sequence and ledger history disagree")
    for object_id, obj in getattr(engine, "_physical_objects", {}).items():
        if isinstance(obj, dict) and "pickup_copy" in obj and object_id not in copy_ids:
            raise ValueError("Pickup physical copy has no source ledger record")
    return True
