"""Source-selected food and medicine buffs for the remaining CSV rows."""
from copy import deepcopy

import csv_item_contract_policy as POLICY


STATE = "csv_remaining_food_state"
ITEM_KINDS = {
    "item/다이버섯": "dynamax_mushroom",
    "item/흉내허브": "mirror_herb",
    "item/회복허브": "recovery_herb_playtest",
    "item/단맛-과자": "sweet_confection_homebrew",
}


def definition(rules, item_id):
    row = POLICY.definition(rules, item_id=item_id)
    return row if row and row["kind"] == ITEM_KINDS.get(item_id) else None


def _state(actor):
    value = actor.spec.setdefault(STATE, {"version": 1, "next": 1, "buffs": [], "receipts": []})
    validate_actor(actor)
    return value


def _buff(actor, buff_id):
    matches = [row for row in _state(actor)["buffs"] if row["id"] == buff_id]
    if len(matches) != 1:
        raise ValueError("one actual remaining CSV food buff is required")
    return matches[0]


def _prepare_stock(engine, actor, item_id, held_selection):
    if held_selection is not None:
        import item_stock as STOCK
        return STOCK.prepare(engine, actor, item_id, held_selection=held_selection)
    inventory = actor.spec.get("items")
    available = inventory.get(item_id) if isinstance(inventory, dict) else None
    if type(available) is not int or available < 1:
        raise ValueError("actual owned selected CSV food inventory required")
    return {"kind": "csv_quantity", "item_id": item_id, "key": item_id, "count": 1}


def _debit_stock(engine, actor, prepared):
    if prepared.get("kind") != "csv_quantity":
        import item_stock as STOCK
        return STOCK.debit(engine, actor, prepared)
    checked = _prepare_stock(engine, actor, prepared["item_id"], None)
    if checked != prepared:
        raise ValueError("selected CSV food stock changed before payment")
    actor.spec["items"][prepared["key"]] -= 1
    paid = {"kind": "quantity", "item_id": prepared["item_id"], "count": 1,
            "selected_variant": True}
    import consumption_execution as EXECUTION
    return EXECUTION.issue(engine, actor, paid)


def consume(engine, user, target, item_id, *, held_selection=None):
    row = definition(engine.r, item_id)
    if row is None:
        raise ValueError("selected item is not a remaining CSV food contract")
    if target.dead or target.fainted or target.hp <= 0:
        raise ValueError("remaining CSV food requires a conscious actual consumer")
    prepared = _prepare_stock(engine, user, item_id, held_selection)
    import state_grants as GRANTS
    participants = () if target is user else (target,)
    def apply(staged, actual_user, *others):
        actual_target = actual_user if not others else others[0]
        actual_stock = _prepare_stock(staged, actual_user, item_id, held_selection)
        payment = _debit_stock(staged, actual_user, actual_stock)
        state = _state(actual_target)
        buff_id = actual_target.entity_id + ":csv-food:" + str(state["next"])
        state["next"] += 1
        buff = {"id": buff_id, "clause_id": row["clause_id"], "item_id": item_id, "kind": row["kind"],
                "created_at": staged.elapsed_seconds, "payment": payment, "protected": row["kind"] == "dynamax_mushroom"}
        state["buffs"].append(buff)
        state["receipts"].append({"event": "consumed_item", "buff_id": buff_id, "item_id": item_id,
                                  "at": staged.elapsed_seconds, "user_id": actual_user.entity_id})
        return deepcopy(buff)
    return GRANTS.transition(engine, user, apply, participants=participants)


def _spend(engine, actor, buff, consumer, result):
    state = _state(actor)
    if buff not in state["buffs"]:
        raise ValueError("remaining CSV food buff was already consumed")
    state["buffs"].remove(buff)
    receipt = {"event": "buff_spent", "buff_id": buff["id"], "consumer": consumer,
               "at": engine.elapsed_seconds, "result": deepcopy(result)}
    state["receipts"].append(receipt)
    return receipt


def consume_dynamax(engine, actor, buff_id, *, form_source):
    buff = _buff(actor, buff_id)
    if buff["kind"] != "dynamax_mushroom" or form_source not in ("dynamax", "gigantamax"):
        raise ValueError("Dynamax Mushroom can only be consumed by its designated Dynamax form")
    return _spend(engine, actor, buff, "designated_dynamax_form", {"form_source": form_source})


def forbid_external_operation(actor, buff_id, operation):
    buff = _buff(actor, buff_id)
    if buff["kind"] == "dynamax_mushroom" and operation in ("steal", "consume", "deny", "reuse", "transfer"):
        raise ValueError("Dynamax Mushroom buff excludes theft, ordinary consumption, denial and reuse")
    return False


def mirror_holders(engine, *, exclude=None):
    import world_entities as WORLD
    return [(actor, buff) for actor in WORLD.actor_index(engine).values() if actor is not exclude
            for buff in actor.spec.get(STATE, {}).get("buffs", ()) if buff.get("kind") == "mirror_herb"]


def change_stage(engine, actor, stat, delta):
    """Keep the actual gain and all selected Herb exchanges in one transition."""
    import state_grants as GRANTS
    def apply(staged, subject):
        staged._csv_food_stage_transaction = True
        try:
            return staged.change_stage(subject, stat, delta)
        finally:
            del staged._csv_food_stage_transaction
    return GRANTS.transition(engine, actor, apply)


def _stage_changed(engine, source_actor, stat, before, after):
    """Private Engine callback receives its actual clamped values, not declarations."""
    if stat not in ("atk", "def", "spa", "spd", "spe") or after <= before:
        return None
    candidates = mirror_holders(engine, exclude=source_actor)
    previous = getattr(engine, '_csv_food_stage_event', None)
    event = dict(source_actor=source_actor, stat=stat, before=before, after=after, selected=None)
    engine._csv_food_stage_event = event
    try:
        for holder, buff in candidates:
            if buff not in _state(holder)['buffs']:
                continue
            answer = engine.rulings.decide(dict(type='mirror_herb', unit=buff['item_id'],
                actor_id=holder.entity_id, buff_id=buff['id'], source_actor_id=source_actor.entity_id,
                stat=stat, before=before, after=after, text='이 실제 전투단계 상승에 흉내허브 버프를 교환합니까?'))
            if answer is not True:
                continue
            event['selected'] = (holder, buff['id'])
            observe_positive_stage(engine, source_actor, stat, before, after, recipient=holder)
    finally:
        if previous is None:
            del engine._csv_food_stage_event
        else:
            engine._csv_food_stage_event = previous


def observe_positive_stage(engine, source_actor, stat, before, after, *, recipient=None):
    event = getattr(engine, '_csv_food_stage_event', None)
    if (not isinstance(event, dict) or event.get('source_actor') is not source_actor
            or (event.get('stat'), event.get('before'), event.get('after')) != (stat, before, after)
            or not event.get('selected') or event['selected'][0] is not recipient):
        raise ValueError('Mirror Herb consumption requires its selected actual native stage event')
    holder, buff_id = event['selected']
    event['selected'] = None
    buff = _buff(holder, buff_id)
    if buff['kind'] != 'mirror_herb':
        raise ValueError('selected native stage reaction needs its actual Mirror Herb buff')
    delta = after - before
    _spend(engine, holder, buff, 'mirror_positive_stage',
           {'source_actor_id': source_actor.entity_id, 'stat': stat, 'before': before, 'after': after, 'delta': delta})
    engine.change_stage(holder, stat, delta)
    return {'holder_id': holder.entity_id, 'stat': stat, 'delta': delta, 'buff_id': buff_id}


def prepare_save(engine, actor, buff_id, condition):
    buff = _buff(actor, buff_id)
    if buff["kind"] != "recovery_herb_playtest" or not isinstance(condition, str) or not condition:
        raise ValueError("Recovery Herb needs one actual saving-check condition")
    actor.spec.setdefault(STATE, {})["pending_save"] = {"buff_id": buff_id, "condition": condition}
    return deepcopy(actor.spec[STATE]["pending_save"])


def saving_bonus(engine, actor, condition):
    pending = _state(actor).get("pending_save")
    if not isinstance(pending, dict) or pending.get("condition") != condition:
        return 0
    buff = _buff(actor, pending["buff_id"])
    if buff["kind"] != "recovery_herb_playtest":
        raise ValueError("Recovery Herb pending save source changed")
    _state(actor).pop("pending_save", None)
    _spend(engine, actor, buff, "saving_check", {"condition": condition, "bonus": 2})
    return 2


def activate_sweet(engine, actor, buff_id, *, disposition="neutral"):
    if not engine.encounter_active:
        raise ValueError("Sweet Confection next-turn lifetime requires an active encounter")
    if disposition not in ("neutral", "liked", "disliked"):
        raise ValueError("Sweet Confection flavor disposition is explicit")
    buff = _buff(actor, buff_id)
    if buff["kind"] != "sweet_confection_homebrew":
        raise ValueError("selected buff is not the homebrew Sweet Confection")
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor,
        lambda staged, actual: _activate_sweet(staged, actual, buff_id, disposition))


def _activate_sweet(engine, actor, buff_id, disposition):
    buff = _buff(actor, buff_id)
    amount = 2 if disposition == "liked" else 1
    import combat_timing as TIMING
    serial = actor.custom_conditions.get("combat_turn_serial", 0)
    effect_id = "csv-sweet:" + buff_id
    TIMING.install(engine, actor, {"source": buff["item_id"], "effect_contract": True, "effect_id": effect_id,
        "turn_owner": actor, "turn_deadline": serial + 1, "encounter_end": True, "evasion_modifier": amount})
    if disposition == "disliked":
        engine.apply_status(actor, "난동", source=buff["item_id"], applied_by=actor)
    _spend(engine, actor, buff, "sweet_self_activation", {"evasion": amount, "disposition": disposition,
                                                           "until": "end_of_next_turn"})
    return {"evasion": amount, "disposition": disposition, "effect_id": effect_id}


def validate_actor(actor):
    state = actor.spec.get(STATE)
    if state is None:
        return True
    if (not isinstance(state, dict) or state.get("version") != 1 or type(state.get("next")) is not int
            or state["next"] < 1 or not isinstance(state.get("buffs"), list) or not isinstance(state.get("receipts"), list)):
        raise ValueError("remaining CSV food state is invalid")
    seen = set()
    for buff in state["buffs"]:
        row = definition(actor.r, buff.get("item_id"))
        if (not isinstance(buff, dict) or not isinstance(buff.get("id"), str) or buff["id"] in seen or row is None
                or buff.get("clause_id") != row["clause_id"] or buff.get("kind") != row["kind"]):
            raise ValueError("remaining CSV food buff identity is invalid")
        seen.add(buff["id"])
    return True


def validate_world(engine, index):
    POLICY.policy(engine.r)
    for actor in index.values():
        validate_actor(actor)
    return True
