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


def _prepare(engine, actor, target, held_selection, destination_slot):
    import held_equipment as HELD
    import items as ITEMS
    import partial_entities as PARTIAL
    import world_entities as WORLD

    reg = registration(engine.r, SOURCE)
    PARTIAL.require_complete(actor, "Pickup source")
    PARTIAL.require_complete(target, "Pickup target")
    index = WORLD.require_actors(engine, actor, target)
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
        "source": reg["source_id"],
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


def apply_effect(engine, actor, target, effect, ctx):
    """The registered ``copy_item`` handler's sole executable path."""
    if _semantic(effect) != COPY_EFFECT or ctx.get("source_id") != SOURCE or not ctx.get("pickup_item_copy_commit"):
        raise ValueError("copy_item requires the reviewed Pickup physical-instance adapter")
    plan = _prepare(engine, actor, target, ctx.get("held_selection"), ctx.get("destination_slot"))
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


def activate(engine, actor, ability, target, *, held_selection=None, destination_slot=None):
    """Pay Pickup once, then create and equip one linked physical copy."""
    reg = registration(engine.r, ability)
    if reg is None:
        raise ValueError("reviewed Pickup source required")
    # Pure preflight catches source/identity/slot failures before staging or cost.
    validate_world(engine)
    _prepare(engine, actor, target, held_selection, destination_slot)

    import frequency as FREQ
    import state_grants as GRANTS
    import turn as TURN

    def commit(staged, user, holder):
        key = "ability:" + NAME
        frequency = staged.r.ability_freq.get(NAME)
        if not FREQ.activation_allowed(user, key, frequency, engine=staged):
            raise ValueError("Pickup Scene frequency exhausted")
        if not TURN.spend(staged, user, "swift", NAME):
            raise ValueError("Pickup Swift action unavailable")
        FREQ.consume_activation(user, key, frequency, engine=staged)
        # Route the authored copy_item payload through its registered handler.
        import effects_ext as EXT
        result = EXT.h_copy_item(staged, user, holder, COPY_EFFECT, {
            "source_id": SOURCE,
            "pickup_item_copy_commit": True,
            "held_selection": held_selection,
            "destination_slot": destination_slot,
        })
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

    index = WORLD.actor_index(engine, () if actors is None else actors)
    validate_world(engine, index)
    plans = []
    for user in index.values():
        for record in _records(user, ACTIVE):
            copy = engine._physical_objects[record["copy_instance_id"]]
            copy_lifecycle = WORLD.physical_lifecycle(copy)
            original = engine._physical_objects[record["original_instance_id"]]
            original_lifecycle = WORLD.physical_lifecycle(original)
            if not copy_lifecycle["consumed"] and not copy_lifecycle["destroyed"]:
                _preflight_terminal(engine, index, copy["id"], record["user_id"])
            if (record["consumable"] and not copy_lifecycle["consumed"]
                    and not original_lifecycle["consumed"] and not original_lifecycle["destroyed"]):
                _preflight_terminal(engine, index, original["id"], record["target_id"])
            plans.append((user, record, copy_lifecycle))
    for user, record, copy_lifecycle in plans:
        copy_status = _destroy_present(
            engine,
            index,
            record["copy_instance_id"],
            source=SOURCE + "/encounter-end",
            fallback_holder_id=record["user_id"],
        )
        original_status = "retained"
        if record["consumable"] and not copy_lifecycle["consumed"]:
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
    validate_world(engine, index)
    return [deepcopy(record) for _, record, _ in plans]


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
