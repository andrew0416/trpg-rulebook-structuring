"""Source-pinned contracts for ten physical trainer equipment variants.

The physical item instance owns mutable state.  An equipped actor keeps only a
validated projection for read-only consumers which do not receive an Engine.
"""
from copy import deepcopy
import csv
import json
import os


POLICY_FILE = "equipment-variant-contract-policy.json"
OBJECT_STATE = "equipment_variant_state"
CHOICE_STATE = "equipment_variant_choices"
COVERT_BLOCK = "_equipment_variant_covert_block"
KINDS = {
    "item/잽-블래스터": "one_shot_cannon",
    "item/인페르노-캐논": "one_shot_cannon",
    "item/분리중갑": "ablative_armor",
    "item/타입-방어복": "type_armor",
    "item/보강된-트렌치코트": "physical_trenchcoat",
    "item/보강된-특수-트렌치코트": "special_trenchcoat",
    "item/마찰저하복": "physical_slipstream",
    "item/특수마찰저하복": "special_slipstream",
    "item/펀치글러브": "punching_glove",
    "item/은밀망토": "covert_cloak",
}
DR_KINDS = {
    "ablative_armor", "type_armor", "physical_trenchcoat",
    "special_trenchcoat", "physical_slipstream", "special_slipstream",
}
TRENCH_KINDS = {"physical_trenchcoat", "special_trenchcoat"}
SLIPSTREAM_KINDS = {"physical_slipstream", "special_slipstream"}


def _path(rules):
    staged = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", POLICY_FILE))
    canonical = os.path.join(rules.root, "data", POLICY_FILE)
    return staged if os.path.exists(staged) else canonical


def policy(rules):
    # Cache the reviewed declaration, never an earlier freshness/selection
    # decision. Warm native reads retain the same provenance boundary.
    value = getattr(rules, "_equipment_variant_contract_policy", None)
    if value is None:
        with open(_path(rules), encoding="utf-8") as handle:
            value = json.load(handle)
    rows = value.get("rows")
    if value.get("schema_version") != 1 or value.get("contract") != "physical trainer equipment variants":
        raise ValueError("equipment variant policy schema changed")
    if not isinstance(rows, dict) or set(rows) != set(KINDS):
        raise ValueError("equipment variant policy must contain the exact ten reviewed rows")
    from source_context import verified_source
    verified_source(rules, {"file": "input/db/inventory.csv",
        "sha256": value.get("inventory_file_sha256")}, label="equipment variant")
    from csv_item_contract_policy import registered_item_rows
    indexed = registered_item_rows(rules, (row.get("clause_id") for row in rows.values()
                                         if isinstance(row.get("clause_id"), str)))
    clauses = set()
    for item_id, row in rows.items():
        if item_id != row.get("item_id") or row.get("kind") != KINDS[item_id] or row.get("wearer_kind") != "trainer":
            raise ValueError("equipment variant identity, kind, or wearer changed")
        clause = row.get("clause_id")
        if not isinstance(clause, str) or clause in clauses:
            raise ValueError("equipment variant clause identity changed")
        clauses.add(clause)
        registered = indexed.get(clause)
        if registered is None or len(registered.get("source", ())) != 1:
            raise ValueError("equipment variant source row is missing")
        source = registered["source"][0]
        expected = (row.get("source_file"), row.get("source_row"), row.get("source_columns"), row.get("source_row_sha256"))
        actual = (source.get("file"), source.get("row"), source.get("columns"), source.get("raw_cells_sha256"))
        if expected != actual:
            raise ValueError("equipment variant source provenance changed: " + clause)
        header = rules.item_effects(item_id)[1]
        if header.get("id") != item_id or rules._selected_rule(item_id) != item_id:
            raise ValueError("selected equipment variant changed: " + item_id)
    classifier = value.get("punch_classifier")
    if (not isinstance(classifier, dict) or classifier.get("header_row") != 2
            or classifier.get("column") != 16 or classifier.get("header") != "철주먹"):
        raise ValueError("Punching Glove move classifier source changed")
    verified_source(rules, {"file": classifier.get("source_file"),
        "sha256": classifier.get("source_file_sha256")}, label="Punching Glove move classifier")
    rules._equipment_variant_contract_policy = value
    return deepcopy(value)


def definition(rules, item_id):
    return deepcopy(policy(rules)["rows"].get(item_id))


def _object(engine, actor, instance_id, item_id):
    obj = getattr(engine, "_physical_objects", {}).get(instance_id)
    if (not isinstance(obj, dict) or obj.get("kind") != "item_instance"
            or obj.get("item_rule_id") != item_id
            or actor.entity_id not in (obj.get("owner_id"), obj.get("carrier_id"), obj.get("equipped_by"))):
        raise ValueError("equipment variant requires its actual owned physical item")
    return obj


def _new_state(row, now):
    result = {"schema_version": 1, "item_id": row["item_id"], "kind": row["kind"], "created_at": now}
    if row["kind"] == "one_shot_cannon":
        result.update(remaining_uses=1, use_history=[])
    elif row["kind"] == "ablative_armor":
        result.update(current_dr=row["maximum_dr"], last_repair_at=now, damage_history=[], repair_history=[])
    elif row["kind"] in SLIPSTREAM_KINDS:
        result.update(encounter_uses=[], encounter_scope_version=2)
    elif row["kind"] == "covert_cloak":
        result["scene_uses"] = []
    return result


def _state(engine, actor, row, obj, *, create=False):
    state = obj.get(OBJECT_STATE)
    if state is None and create:
        state = _new_state(row, engine.elapsed_seconds)
        obj[OBJECT_STATE] = state
    if state is None:
        raise ValueError("physical equipment variant state is missing")
    _validate_object_state(engine, obj, row=row)
    return state


def configure_type_armor(engine, owner, instance_id, chosen_type):
    """Bind the immutable purchase-time type to one observed armor instance."""
    if chosen_type not in __import__("items").TYPES:
        raise ValueError("Type Armor requires one canonical damage type")
    obj = _object(engine, owner, instance_id, "item/타입-방어복")
    old = obj.get(OBJECT_STATE)
    if old is not None:
        if old.get("chosen_type") == chosen_type:
            return deepcopy(old)
        raise ValueError("Type Armor purchase choice is immutable")
    if obj.get("equipped_by") is not None:
        raise ValueError("Type Armor must be configured before it is equipped")
    import state_grants as GRANTS
    def apply(staged, staged_owner):
        actual = _object(staged, staged_owner, instance_id, "item/타입-방어복")
        if actual.get(OBJECT_STATE) is not None:
            raise ValueError("Type Armor purchase choice already exists")
        row = definition(staged.r, "item/타입-방어복")
        state = _new_state(row, staged.elapsed_seconds)
        state.update(chosen_type=chosen_type, configured_by=staged_owner.entity_id,
                     configured_at=staged.elapsed_seconds)
        actual[OBJECT_STATE] = state
        _validate_object_state(staged, actual, row=row)
        return deepcopy(state)
    return GRANTS.transition(engine, owner, apply)


def prepare_register(engine, actor, item_id, source_instance_id=None):
    if item_id not in KINDS:
        import csv_item_physical_contracts as CSV_ITEMS
        return CSV_ITEMS.prepare_register(engine, actor, item_id, source_instance_id)
    row = definition(engine.r, item_id)
    if actor.kind != row["wearer_kind"]:
        raise ValueError(row["name"] + " requires a trainer wearer")
    if source_instance_id is None:
        raise ValueError(row["name"] + " requires an actual physical item instance")
    obj = _object(engine, actor, source_instance_id, item_id)
    if row["kind"] == "one_shot_cannon":
        import capability_actions as CAPABILITIES
        if CAPABILITIES.power(actor) <= row["minimum_power_exclusive"]:
            raise ValueError(row["name"] + " requires Power greater than 6")
    if row["kind"] == "type_armor":
        state = obj.get(OBJECT_STATE)
        if not isinstance(state, dict) or state.get("chosen_type") not in __import__("items").TYPES:
            raise ValueError("Type Armor requires its immutable purchase-time type before equip")
        _validate_object_state(engine, obj, row=row)
    return row


def consumes_effect(plan, effect):
    # Every selected row is executed by this exact contract.  Leaving a parsed
    # fragment live would double-apply DR or turn a limited action into a passive.
    if plan and plan.get("_csv_remaining_item_contract") is True:
        import csv_item_physical_contracts as CSV_ITEMS
        return CSV_ITEMS.consumes_effect(plan, effect)
    return bool(plan and isinstance(effect, dict))


def _advance_ablative(engine, state, row):
    now = engine.elapsed_seconds
    if state["last_repair_at"] > now:
        raise ValueError("Ablative Armor repair clock is in the future")
    intervals = (now - state["last_repair_at"]) // row["repair_seconds"]
    if intervals <= 0:
        return False
    before = state["current_dr"]
    state["current_dr"] = min(row["maximum_dr"], before + intervals * row["repair_amount"])
    state["last_repair_at"] += intervals * row["repair_seconds"]
    if state["current_dr"] != before:
        state["repair_history"].append({"at": now, "before": before, "after": state["current_dr"], "intervals": intervals})
    return state["current_dr"] != before


def install(engine, actor, source_id, plan):
    if plan is None:
        return [], 0
    if plan.get("_csv_remaining_item_contract") is True:
        import csv_item_physical_contracts as CSV_ITEMS
        return CSV_ITEMS.install(engine, actor, source_id, plan)
    registration = next((row for row in getattr(actor, "_item_reg", {}).values()
                         if row.get("state_source") == source_id), None)
    if registration is not None:
        raise ValueError("equipment variant source is already registered")
    instance_id = source_id.split("equipment:", 1)[1] if source_id.startswith("equipment:") else None
    obj = _object(engine, actor, instance_id, plan["item_id"])
    state = _state(engine, actor, plan, obj, create=True)
    if plan["kind"] == "ablative_armor":
        _advance_ablative(engine, state, plan)
    effect_sources = []
    if plan["kind"] == "one_shot_cannon":
        import state_grants as GRANTS
        GRANTS.grant_moves(actor, [plan["move_id"]], source_id, "item",
            owner_id=actor.spec.get("id"), lifetime="equipped", rule_id=plan["item_id"],
            tutor_points=0, mode="permission")
    elif plan["kind"] == "ablative_armor":
        import combat_stage_sources as STAGES
        import state_grants as GRANTS
        key = source_id + ":variant:base-speed"
        STAGES.add_base(actor, key, "spe", plan["base_speed_stage"],
                        source=plan["item_id"], ends=key)
        GRANTS.state(actor)["effects"][key] = {"rows": [], "listeners": [], "stages": True}
        effect_sources.append(key)
    return effect_sources, 1


def bind_registration(engine, actor, registration, plan):
    if plan is None:
        return
    if plan.get("_csv_remaining_item_contract") is True:
        import csv_item_physical_contracts as CSV_ITEMS
        return CSV_ITEMS.bind_registration(engine, actor, registration, plan)
    obj = _object(engine, actor, registration.get("instance_id"), plan["item_id"])
    state = _state(engine, actor, plan, obj)
    _sync_projection(registration, state)


def uninstall(engine, actor, registration):
    item_id = registration.get("item_id")
    if item_id not in KINDS:
        import csv_item_physical_contracts as CSV_ITEMS
        return CSV_ITEMS.uninstall(engine, actor, registration)
    # Mutable charge/durability belongs to the item and deliberately survives.
    choice = actor.spec.get(CHOICE_STATE)
    if isinstance(choice, dict) and choice.get("instance_id") == registration.get("instance_id"):
        actor.spec.pop(CHOICE_STATE, None)


def _sync_projection(registration, state):
    projection = {"schema_version": 1, "instance_id": registration.get("instance_id"),
                  "item_id": state["item_id"], "kind": state["kind"]}
    if state["kind"] == "ablative_armor":
        projection["current_dr"] = state["current_dr"]
    elif state["kind"] == "type_armor":
        projection["chosen_type"] = state["chosen_type"]
    registration["variant_projection"] = projection


def _active(engine, actor, kinds):
    kinds = {kinds} if isinstance(kinds, str) else set(kinds)
    sources = actor.spec.get("state_grants", {}).get("sources", {})
    found = []
    for registration in getattr(actor, "_item_reg", {}).values():
        row = policy(engine.r)["rows"].get(registration.get("item_id"))
        if row is None or row["kind"] not in kinds or registration.get("state_source") not in sources:
            continue
        instance_id = registration.get("instance_id")
        obj = _object(engine, actor, instance_id, row["item_id"])
        if obj.get("equipped_by") != actor.entity_id:
            raise ValueError("equipment variant registration and physical holder disagree")
        state = _state(engine, actor, row, obj)
        expected = deepcopy(registration)
        _sync_projection(expected, state)
        if registration.get("variant_projection") != expected.get("variant_projection"):
            raise ValueError("equipment variant projection differs from its physical state")
        found.append((row, registration, obj, state))
    return found


def _active_actor(rules, actor, kinds):
    kinds = {kinds} if isinstance(kinds, str) else set(kinds)
    sources = actor.spec.get("state_grants", {}).get("sources", {})
    found = []
    for registration in getattr(actor, "_item_reg", {}).values():
        row = policy(rules)["rows"].get(registration.get("item_id"))
        if row is None or row["kind"] not in kinds or registration.get("state_source") not in sources:
            continue
        projection = registration.get("variant_projection")
        if (not isinstance(projection, dict) or projection.get("schema_version") != 1
                or projection.get("instance_id") != registration.get("instance_id")
                or projection.get("item_id") != row["item_id"] or projection.get("kind") != row["kind"]):
            raise ValueError("equipment variant projection is invalid")
        found.append((row, registration))
    return found


def damage_reduction(actor, move):
    if move.get("class") not in ("물리", "특수"):
        return 0
    total = 0
    for row, registration in _active_actor(actor.r, actor, DR_KINDS):
        projection = registration["variant_projection"]
        kind = row["kind"]
        if kind == "ablative_armor":
            total += projection["current_dr"]
        elif kind == "type_armor" and projection["chosen_type"] == move.get("type"):
            total += row["damage_reduction"]
        elif kind in ("physical_trenchcoat", "physical_slipstream") and move["class"] == "물리":
            total += row["damage_reduction"]
        elif kind in ("special_trenchcoat", "special_slipstream") and move["class"] == "특수":
            total += row["damage_reduction"]
    return total


def preflight_move(engine, actor, move_id, *, count_use=True):
    if not count_use:
        return
    matches = [entry for entry in _active(engine, actor, "one_shot_cannon") if entry[0]["move_id"] == move_id]
    if not matches:
        return
    import move_state as MOVES
    if move_id in MOVES.owned_list(actor.spec, "moves", actor.moves):
        return
    if len(matches) != 1:
        raise ValueError("one actual cannon must own this Move permission")
    row, _, _, state = matches[0]
    if state["remaining_uses"] != 1:
        raise ValueError(row["name"] + " one-shot Move permission is spent")


def begin_move_use(engine, actor, target, move_id):
    matches = [entry for entry in _active(engine, actor, "one_shot_cannon") if entry[0]["move_id"] == move_id]
    if not matches:
        return None
    import move_state as MOVES
    if move_id in MOVES.owned_list(actor.spec, "moves", actor.moves):
        return None
    if len(matches) != 1:
        raise ValueError("one actual cannon must own this Move permission")
    row, registration, _, state = matches[0]
    if state["remaining_uses"] != 1:
        raise ValueError(row["name"] + " one-shot Move permission is spent")
    state["remaining_uses"] = 0
    receipt = {"at": engine.elapsed_seconds, "round": engine.round_no,
               "actor_id": actor.entity_id, "target_id": target.entity_id, "move_id": move_id}
    state["use_history"].append(receipt)
    _sync_projection(registration, state)
    return deepcopy(receipt)


def _punch_moves(rules):
    cached = getattr(rules, "_equipment_variant_punch_moves", None)
    if cached is not None:
        return cached
    classifier = policy(rules)["punch_classifier"]
    path = os.path.join(rules.root, classifier["source_file"])
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    header = rows[classifier["header_row"] - 1]
    index = classifier["column"] - 1
    if len(header) <= index or header[index] != classifier["header"]:
        raise ValueError("Punching Glove classifier column changed")
    by_name = {}
    for move_id, move in rules.moves.items():
        by_name.setdefault(move.get("name"), []).append(move_id)
    result = set()
    for source in rows[classifier["header_row"]:]:
        if len(source) <= index or not source[index].strip():
            continue
        candidates = by_name.get(source[0], ())
        if len(candidates) != 1:
            raise ValueError("Punching Glove classifier Move name is ambiguous: " + source[0])
        result.add(candidates[0])
    rules._equipment_variant_punch_moves = frozenset(result)
    return rules._equipment_variant_punch_moves


def damage_roll_bonus(engine, actor, move):
    result = 0
    if _active(engine, actor, "punching_glove"):
        result += policy(engine.r)["rows"]["item/펀치글러브"]["damage_roll_bonus"] if move.get("id") in _punch_moves(engine.r) else 0
    import csv_item_physical_contracts as CSV_ITEMS
    return result + CSV_ITEMS.damage_roll_bonus(engine, actor, move)


def after_attack_damage(engine, attacker, target, move, receipt, *, type_multiplier=None):
    actual_hit = (isinstance(receipt, dict)
                  and receipt.get("observation_boundary") == "native_attack_application_including_its_hooks"
                  and receipt.get("source") == move.get("id")
                  and receipt.get("damage_class") == move.get("class")
                  and move.get("class") in ("물리", "특수"))
    if not actual_hit:
        return None
    import csv_item_physical_contracts as CSV_ITEMS
    CSV_ITEMS.after_attack_damage(engine, attacker, target, move, receipt, type_multiplier=type_multiplier)
    _begin_covert_hit(engine,attacker,target,move)
    for row, registration, _, state in _active(engine, target, "ablative_armor"):
        _advance_ablative(engine, state, row)
        before = state["current_dr"]
        state["current_dr"] = max(0, before - row["loss_per_damaging_attack"])
        state["damage_history"].append({"at": engine.elapsed_seconds, "move_id": move["id"],
                                        "attacker_id": attacker.entity_id, "before": before,
                                        "after": state["current_dr"]})
        _sync_projection(registration, state)
    if ("근접" in str(move.get("range", ""))
            and _active(engine, attacker, "punching_glove")):
        move["_equipment_original_range"] = move.get("range")
        move["range"] = str(move.get("range", "")).replace("근접", "비접촉")
        move["_melee_hit_effects_suppressed"] = True
    return True


def advance_time(engine, actor):
    for row, registration, _, state in _active(engine, actor, "ablative_armor"):
        if _advance_ablative(engine, state, row):
            _sync_projection(registration, state)


def _encounter_key(engine, actor):
    if not engine.encounter_active:
        raise ValueError("Slipstream Armor requires an active encounter")
    return [getattr(engine, "session_epoch", 0), getattr(engine, "_party_encounter_epoch", 0)]


def upgrade_legacy_slipstream(engine, *, commit=True):
    """Bind ambiguous scene receipts once, before a restore or battle boundary."""
    changes = []
    for obj in getattr(engine, "_physical_objects", {}).values():
        state = obj.get(OBJECT_STATE)
        if not isinstance(state, dict) or state.get("kind") not in SLIPSTREAM_KINDS:
            continue
        _validate_object_state(engine, obj)
        if "encounter_scope_version" in state:
            continue
        upgraded = {"encounter_scope_version": 2}
        if state["encounter_uses"]:
            # shortcut: old scene keys cannot identify a battle; lock only the
            # restored epoch, until versioned saves replace this legacy format.
            upgraded["legacy_encounter_scope"] = {
                "encounter": [getattr(engine, "session_epoch", 0), getattr(engine, "_party_encounter_epoch", 0)],
                "receipt_count": len(state["encounter_uses"]),
            }
        changes.append((state, upgraded))
    if commit:
        for state, upgraded in changes:
            state.update(upgraded)


def _slipstream_spent(state, key):
    if state.get("encounter_scope_version") != 2:
        raise ValueError("Slipstream legacy receipts require a restore or battle boundary upgrade")
    legacy = state.get("legacy_encounter_scope")
    # Session/scene changes inside an active battle do not reset its quota.
    if legacy is not None and legacy["encounter"][1] == key[1]:
        return True
    return any(event.get("scope_version") == 2 and event["encounter"][1] == key[1]
               for event in state["encounter_uses"])


def activate_slipstream(engine, actor):
    matches = _active(engine, actor, SLIPSTREAM_KINDS)
    if len(matches) != 1:
        raise ValueError("one actual equipped Slipstream Armor is required")
    import status_sets as STATUS
    bound = STATUS.normalize("구속")
    if bound not in actor.conditions:
        return {"activated": False, "reason": "not_bound"}
    key = _encounter_key(engine, actor)
    if _slipstream_spent(matches[0][3], key):
        return {"activated": False, "reason": "encounter_frequency_spent"}
    import state_grants as GRANTS
    def apply(staged, staged_actor):
        current = _active(staged, staged_actor, SLIPSTREAM_KINDS)
        if len(current) != 1:
            raise ValueError("Slipstream Armor source ended before commit")
        row, registration, _, state = current[0]
        actual_key = _encounter_key(staged, staged_actor)
        if bound not in staged_actor.conditions:
            return {"activated": False, "reason": "not_bound"}
        if _slipstream_spent(state, actual_key):
            return {"activated": False, "reason": "encounter_frequency_spent"}
        import turn as TURN
        if not TURN.spend(staged, staged_actor, "swift", row["name"]):
            return {"activated": False, "reason": "no_swift_action"}
        # Engine.cure_status returns None for an ordinary successful cure; the
        # authoritative success signal is the projected condition set.
        staged.cure_status(staged_actor, bound)
        if bound in staged_actor.conditions:
            raise ValueError("Slipstream Armor paid but Bound was not cured")
        receipt = {"encounter": actual_key, "scope_version": 2, "at": staged.elapsed_seconds,
                   "round": staged.round_no, "actor_id": staged_actor.entity_id}
        state["encounter_uses"].append(receipt)
        _sync_projection(registration, state)
        return {"activated": True, **deepcopy(receipt)}
    return GRANTS.transition(engine, actor, apply)


def _scene_key(engine, actor):
    import frequency as FREQUENCY
    return [getattr(engine, "session_epoch", 0), FREQUENCY.state(actor)["scene"]]


def authorize_covert_cloak(engine, actor, *, expected_move_id=None, accept=True):
    if type(accept) is not bool:
        raise ValueError("Covert Cloak choice must be explicit")
    matches = _active(engine, actor, "covert_cloak")
    if len(matches) != 1:
        raise ValueError("one actual equipped Covert Cloak is required")
    if expected_move_id is not None:
        if expected_move_id not in engine.r.moves or engine.r._selected_rule(expected_move_id) != expected_move_id:
            raise ValueError("Covert Cloak expected Move must be selected")
    if not accept:
        actor.spec.pop(CHOICE_STATE, None)
        return {"authorized": False}
    row, registration, _, state = matches[0]
    key = _scene_key(engine, actor)
    if any(event["scene"] == key for event in state["scene_uses"]):
        return {"authorized": False, "reason": "scene_frequency_spent"}
    choice = {"kind": "covert_cloak", "item_id": row["item_id"],
              "instance_id": registration["instance_id"], "scene": key,
              "expected_move_id": expected_move_id}
    actor.spec[CHOICE_STATE] = choice
    return {"authorized": True, **deepcopy(choice)}


def filter_move_effects(ctx, effects):
    target = ctx.get("target")
    engine = ctx.get("engine")
    if engine is None or target is None:
        return effects
    block = getattr(target,COVERT_BLOCK,None)
    if block is None:
        return effects
    move = ctx.get("move") or {}
    if (ctx.get("hit") is not True or block.get("move_id") != move.get("id")
            or block.get("attacker_id") != ctx.get("attacker").entity_id):
        raise ValueError("Covert Cloak effect-filter boundary changed")
    # evasion_mod is one remaining legacy direct Move field.  Restore its
    # post-damage snapshot before independent after-hit reactions run.
    target.evasion_mod=block["evasion_mod"]
    delattr(target,COVERT_BLOCK)
    return [effect for effect in effects if isinstance(effect, dict) and effect.get("type") == "hp_loss"]


def _begin_covert_hit(engine,attacker,target,move):
    choice=target.spec.get(CHOICE_STATE)
    if not isinstance(choice,dict) or choice.get("kind")!="covert_cloak":return None
    if choice.get("expected_move_id") is not None and choice["expected_move_id"]!=move.get("id"):return None
    matches=_active(engine,target,"covert_cloak")
    if len(matches)!=1 or matches[0][1].get("instance_id")!=choice.get("instance_id"):
        raise ValueError("Covert Cloak choice source changed before the hit")
    row,_,_,state=matches[0];key=_scene_key(engine,target)
    if choice.get("scene")!=key:raise ValueError("Covert Cloak choice crossed a scene boundary")
    if any(event["scene"]==key for event in state["scene_uses"]):
        target.spec.pop(CHOICE_STATE,None);return None
    state["scene_uses"].append({"scene":key,"at":engine.elapsed_seconds,
        "move_id":move["id"],"attacker_id":attacker.entity_id})
    target.spec.pop(CHOICE_STATE,None)
    setattr(target,COVERT_BLOCK,{"move_id":move["id"],"attacker_id":attacker.entity_id,
        "evasion_mod":target.evasion_mod,"instance_id":matches[0][1]["instance_id"]})
    engine.log("    은밀망토: 피해/직접 HP 손실 외 기술 효과 무효",row["item_id"])
    return True


def skill_modifiers(rules, actor, target_skill, context):
    if target_skill != "stealth":
        return ()
    rows = []
    for row, registration in _active_actor(rules, actor, TRENCH_KINDS):
        rows.append((registration["state_source"], row["stealth_bonus"], row["clause_id"]))
    if isinstance(context, dict) and context.get("purpose") == "avoid_notice":
        for row, registration in _active_actor(rules, actor, "covert_cloak"):
            rows.append((registration["state_source"], row["stealth_bonus"], row["clause_id"]))
    cap = 4
    accepted = []
    remaining = cap
    for source, value, detail in rows:
        applied = min(value, max(0, remaining))
        if applied:
            accepted.append((source, applied, detail))
            remaining -= applied
    return tuple(accepted)


def conceal_weapon(engine, wearer, weapon_instance_id, *, method):
    if method not in ("visual", "metal_detector", "manual_search", "touch"):
        raise ValueError("explicit supported weapon detection method required")
    matches = _active(engine, wearer, TRENCH_KINDS)
    if len(matches) != 1:
        raise ValueError("one actual reinforced trenchcoat is required")
    weapon = getattr(engine, "_physical_objects", {}).get(weapon_instance_id)
    if not isinstance(weapon, dict):
        raise ValueError("actual carried weapon instance required")
    import optional_weapon_framework as WEAPONS
    import optional_physical_equipment as OPTIONAL
    equipped = [entry for entry in wearer.custom_conditions.get("equipped_weapons", {}).values()
                if entry.get("instance_id", entry.get("weapon", {}).get("instance_id")) == weapon_instance_id]
    if (any(weapon.get(field) not in (None, wearer.entity_id) for field in ("equipped_by", "carrier_id"))
            or not (equipped or wearer.entity_id in (weapon.get("equipped_by"), weapon.get("carrier_id")))):
        raise ValueError("actual carried weapon instance required")
    if WEAPONS.PROFILE in weapon:
        WEAPONS.object_profile(engine, weapon_instance_id)
    elif equipped:
        import turn as TURN
        if any(entry.get("weapon", {}).get("kind") not in TURN.WEAPON_KIND for entry in equipped):
            raise ValueError("actual identified weapon required")
    elif (weapon.get("item_rule_id") not in OPTIONAL.KINDS
          or not OPTIONAL.definition(engine.r, weapon["item_rule_id"]).get("weapon_kind")):
        raise ValueError("actual identified weapon required")
    hidden = method in ("visual", "metal_detector")
    return {"item_id": matches[0][0]["item_id"], "instance_id": matches[0][1]["instance_id"],
            "weapon_instance_id": weapon_instance_id, "method": method,
            "status": "concealed" if hidden else "detectable"}


def _validate_object_state(engine, obj, *, row=None):
    state = obj.get(OBJECT_STATE)
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("physical equipment variant state schema changed")
    row = row or policy(engine.r)["rows"].get(obj.get("item_rule_id"))
    if row is None or state.get("item_id") != row["item_id"] or state.get("kind") != row["kind"]:
        raise ValueError("physical equipment variant state identity changed")
    created = state.get("created_at")
    if type(created) is not int or created < 0 or created > engine.elapsed_seconds:
        raise ValueError("equipment variant creation clock is invalid")
    kind = row["kind"]
    if kind == "one_shot_cannon":
        if state.get("remaining_uses") not in (0, 1) or not isinstance(state.get("use_history"), list):
            raise ValueError("one-shot cannon charge state is invalid")
        if len(state["use_history"]) != 1 - state["remaining_uses"]:
            raise ValueError("one-shot cannon charge and history disagree")
    elif kind == "ablative_armor":
        current = state.get("current_dr")
        if (type(current) is not int or current < 0 or current > row["maximum_dr"]
                or current % row["repair_amount"] or type(state.get("last_repair_at")) is not int
                or state["last_repair_at"] < created or state["last_repair_at"] > engine.elapsed_seconds
                or not isinstance(state.get("damage_history"), list) or not isinstance(state.get("repair_history"), list)):
            raise ValueError("Ablative Armor durability or repair clock is invalid")
    elif kind == "type_armor":
        if (state.get("chosen_type") not in __import__("items").TYPES
                or state.get("configured_by") != obj.get("owner_id")
                or type(state.get("configured_at")) is not int):
            raise ValueError("Type Armor purchase choice state is invalid")
    elif kind in SLIPSTREAM_KINDS:
        if not isinstance(state.get("encounter_uses"), list):
            raise ValueError("Slipstream encounter receipts must be a list")
        _validate_slipstream_scope(engine, state)
    elif kind == "covert_cloak":
        if not isinstance(state.get("scene_uses"), list):
            raise ValueError("Covert Cloak scene receipts must be a list")
    return True


def _validate_slipstream_scope(engine, state):
    receipts = state["encounter_uses"]
    version = state.get("encounter_scope_version")
    legacy = state.get("legacy_encounter_scope")
    if "encounter_scope_version" in state and (type(version) is not int or version != 2):
        raise ValueError("Slipstream encounter scope version is invalid")
    count = 0
    if "legacy_encounter_scope" in state:
        if (version != 2 or not isinstance(legacy, dict)
                or set(legacy) != {"encounter", "receipt_count"}
                or type(legacy["receipt_count"]) is not int
                or not 0 < legacy["receipt_count"] <= len(receipts)):
            raise ValueError("Slipstream legacy encounter scope is invalid")
        count = legacy["receipt_count"]
        _validate_battle_key(engine, legacy["encounter"], allow_zero=True)
    seen = set()
    for index, receipt in enumerate(receipts):
        modern = version == 2 and index >= count
        fields = {"encounter", "at", "round", "actor_id"} | ({"scope_version"} if modern else set())
        if (not isinstance(receipt, dict) or set(receipt) != fields
                or type(receipt["at"]) is not int or not state["created_at"] <= receipt["at"] <= engine.elapsed_seconds
                or type(receipt["round"]) is not int or not 0 <= receipt["round"] <= engine.round_no
                or not isinstance(receipt["actor_id"], str) or not receipt["actor_id"]):
            raise ValueError("Slipstream encounter receipt is invalid")
        key = receipt["encounter"]
        if modern:
            if type(receipt["scope_version"]) is not int or receipt["scope_version"] != 2:
                raise ValueError("Slipstream encounter receipt version is invalid")
            _validate_battle_key(engine, key)
            if key[1] in seen or legacy is not None and key[1] <= legacy["encounter"][1]:
                raise ValueError("Slipstream encounter receipt duplicates a spent battle")
            seen.add(key[1])
        elif (not isinstance(key, list) or len(key) != 2
              or any(type(value) is not int or value < 0 for value in key)
              or key[0] > getattr(engine, "session_epoch", 0)):
            raise ValueError("Slipstream legacy scene receipt is invalid")


def _validate_battle_key(engine, key, *, allow_zero=False):
    if (not isinstance(key, list) or len(key) != 2
            or any(type(value) is not int or value < 0 for value in key)
            or key[0] > getattr(engine, "session_epoch", 0)
            or key[1] > getattr(engine, "_party_encounter_epoch", 0)
            or not allow_zero and key[1] == 0):
        raise ValueError("Slipstream battle epoch is invalid")


def validate_actor(actor):
    import csv_item_physical_contracts as CSV_ITEMS
    CSV_ITEMS.validate_actor(actor)
    choice = actor.spec.get(CHOICE_STATE)
    if choice is None:
        return True
    required = {"kind", "item_id", "instance_id", "scene", "expected_move_id"}
    if (not isinstance(choice, dict) or set(choice) != required or choice["kind"] != "covert_cloak"
            or choice["item_id"] != "item/은밀망토" or not isinstance(choice["instance_id"], str)
            or not isinstance(choice["scene"], list) or len(choice["scene"]) != 2
            or choice["expected_move_id"] is not None and not isinstance(choice["expected_move_id"], str)):
        raise ValueError("Covert Cloak optional choice state is invalid")
    return True


def validate_world(engine, index):
    policy(engine.r)
    import csv_item_physical_contracts as CSV_ITEMS
    import csv_item_food_contracts as CSV_FOOD
    import csv_item_capability_contracts as CSV_CAPABILITIES
    import csv_item_form_contracts as CSV_FORMS
    CSV_ITEMS.validate_world(engine, index)
    CSV_FOOD.validate_world(engine, index)
    CSV_CAPABILITIES.validate_world(engine, index)
    CSV_FORMS.validate_world(engine, index)
    objects = getattr(engine, "_physical_objects", {})
    for obj in objects.values():
        if OBJECT_STATE in obj:
            _validate_object_state(engine, obj)
    for actor in index.values():
        validate_actor(actor)
        for registration in getattr(actor, "_item_reg", {}).values():
            if registration.get("item_id") not in KINDS:
                continue
            row = policy(engine.r)["rows"][registration["item_id"]]
            obj = objects.get(registration.get("instance_id"))
            if not isinstance(obj, dict) or obj.get("equipped_by") != actor.entity_id:
                raise ValueError("equipment variant registration lacks its physical holder")
            state = _state(engine, actor, row, obj)
            expected = deepcopy(registration)
            _sync_projection(expected, state)
            if registration.get("variant_projection") != expected.get("variant_projection"):
                raise ValueError("equipment variant restored projection differs from physical state")
    return True
