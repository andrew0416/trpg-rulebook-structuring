"""Exact physical-item contracts for one optional weapon/equipment batch.

The physical object and the ordinary item registration own the lifetime.  This
module only projects source-reviewed weapon grants, conditional saves and the
two explicit activations into existing native consumers.
"""
from copy import deepcopy
import json
import os

import skill_modifiers as SKILL
import roll_pools as POOLS


POLICY_FILE = "optional-physical-equipment-policy.json"
STATE = "optional_physical_equipment_state"
KINDS = {
    "crafted_item/스톰-글러브": "crafted_weapon",
    "crafted_item/명금의-로브": "songbird_robes",
    "crafted_item/따스한-플루트": "heartwarming_flute",
    "crafted_item/경쟁-부츠": "stampede_boots",
    "crafted_item/뇌수-창": "crafted_weapon",
    "crafted_item/엑스칼리버": "excalibur",
    "item/우주복": "space_suit",
    "item/정신방패": "mental_shield",
    "crafted_item/스프레드-니들": "spread_needle",
    "crafted_item/나인플레임의-스태프": "nine_flames_staff",
    "crafted_item/피의-낫": "blood_scythe",
    "crafted_item/섀도우-워커": "shadow_walkers",
    "crafted_item/요정의-엉덩이-차는-거친-불검": "fairy_fire_sword",
    "crafted_item/캔디-해머": "candy_hammer",
    "crafted_item/카라단다": "kaladanda",
    "crafted_item/스-발린": "svalinn",
    "crafted_item/야타의-거울": "yata_mirror",
    "crafted_item/여의금고봉": "ruyi_staff",
    "crafted_item/카오스-던커": "chaos_dunker",
}

CATALOG_CLAUSES = {
    "FAN-035", "FAN-036", "FAN-042", "FAN-043", "FAN-044",
    "FAN-045", "FAN-046", "FAN-047", "FAN-049",
}
NO_AWAKENING = "optional_equipment_kaladanda_no_awakening"


def _path(rules):
    staged = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", POLICY_FILE))
    canonical = os.path.join(rules.root, "data", POLICY_FILE)
    return staged if os.path.exists(staged) else canonical


def policy(rules):
    value = getattr(rules, "_optional_physical_equipment_policy", None)
    if value is None:
        with open(_path(rules), encoding="utf-8") as handle:
            value = json.load(handle)
    rows = value.get("rows")
    if value.get("schema_version") != 1 or value.get("contract") != "optional physical weapon and equipment projections":
        raise ValueError("optional physical equipment policy schema changed")
    if not isinstance(rows, dict) or set(rows) != set(KINDS):
        raise ValueError("optional physical equipment policy must contain the exact reviewed items")
    optional_path = os.path.join(rules.root, "data", "verification", "category2-optional-clause-status.json")
    with open(optional_path, encoding="utf-8") as handle:
        indexed = {row["clause_id"]: row for row in json.load(handle).get("rows", ())}
    clauses = set()
    verified_files = set()
    for item_id, row in rows.items():
        if row.get("item_id") != item_id or row.get("kind") != KINDS[item_id]:
            raise ValueError("optional equipment item identity or kind changed")
        clause = row.get("clause_id")
        if not isinstance(clause, str):
            raise ValueError("optional equipment clause identity changed")
        clauses.add(clause)
        from source_context import verified_source
        for source in row.get("source", ()):
            reference = (source["file"], source["file_sha256"])
            if reference not in verified_files:
                verified_source(rules, {"file": reference[0], "sha256": reference[1]}, label="optional physical equipment")
                verified_files.add(reference)
        actual = indexed.get(clause)
        if actual is None:
            raise ValueError("optional equipment source clause is missing: " + clause)
        expected = [(x["file"], x["start"], x["end"], x["excerpt_sha256"]) for x in row.get("source", ())]
        observed = [(x["file"], x["start"], x["end"], x["excerpt_sha256"]) for x in actual.get("source", ())]
        if expected != observed:
            raise ValueError("optional equipment source provenance changed: " + clause)
    rules._optional_physical_equipment_policy = value
    return deepcopy(value)


def _require_selected(rules, item_id):
    if rules._selected_rule(item_id) != item_id:
        raise ValueError("selected optional equipment item changed: " + item_id)


def definition(rules, item_id):
    row = policy(rules)["rows"].get(item_id)
    if row is not None:
        _require_selected(rules, item_id)
    return deepcopy(row)


def _object(engine, actor, instance_id, item_id):
    obj = getattr(engine, "_physical_objects", {}).get(instance_id)
    if (not isinstance(obj, dict) or obj.get("kind") != "item_instance"
            or obj.get("item_rule_id") != item_id
            or actor.entity_id not in (obj.get("owner_id"), obj.get("carrier_id"), obj.get("equipped_by"))):
        raise ValueError("optional equipment requires its actual owned physical item")
    return obj


def _edge(actor, *names):
    owned = actor.spec.get("edges", ())
    return any(SKILL.key(value) in {SKILL.key(name) for name in names} for value in owned)


def _feature(actor, *names):
    wanted = {SKILL.key(name) for name in names}
    values = [*actor.spec.get("features", ()), *actor.spec.get("feats", ())]
    return any(SKILL.key(value) in wanted for value in values)


def prepare_register(engine, actor, item_id, source_instance_id=None):
    if item_id not in KINDS:
        return None
    row = definition(engine.r, item_id)
    if actor.kind != "trainer":
        raise ValueError(row["name"] + " requires a trainer wearer")
    if source_instance_id is None:
        raise ValueError(row["name"] + " requires an actual physical item instance")
    obj = _object(engine, actor, source_instance_id, item_id)
    if row["kind"] == "space_suit":
        variant, configuration = _space_suit_configuration(obj, row)
        row.update(configuration, space_suit_variant=variant)
        row["capabilities"] = list(definition(engine.r, item_id)["capabilities"]) + configuration["capabilities"]
        _validate_object_state(obj, row)
    if row.get("weapon_kind"):
        required = {"주요손", "반대손"} if row["weapon_kind"] == "대형 근접무기" else {"주요손"}
        occupied = {slot for record in getattr(actor, "_item_reg", {}).values() for slot in record.get("slots", ())}
        occupied.update(slot for record in actor.custom_conditions.get("equipped_weapons", {}).values() for slot in record.get("slots", ()))
        if occupied.intersection(required):
            raise ValueError(row["name"] + " requires its physical weapon slots")
    if row["kind"] == "shadow_walkers":
        bases = [(key, record) for key, record in getattr(actor, "_item_reg", {}).items()
                 if "발" in record.get("slots", ()) and record.get("instance_id") != source_instance_id
                 and not record.get("retained_by_shadow_walkers")]
        if len(bases) != 1:
            raise ValueError("Shadow Walkers require exactly one actual equipped feet-slot base")
        base_key, base = bases[0]
        base_obj = _object(engine, actor, base.get("instance_id"), base.get("item_id"))
        row["retained_base"] = {
            "registration_key": base_key, "instance_id": base["instance_id"],
            "item_id": base["item_id"], "source_id": base["state_source"],
        }
        row["retained_base_state"] = deepcopy(base_obj)
    if row["kind"] == "mental_shield":
        row["iron_mind"] = _edge(actor, "edge/강철의-정신", "강철의 정신", "Iron Mind")
    if row.get("arcane") and not _feature(actor, "feat/아케인-훈련", "아케인 훈련", "Arcane Training"):
        raise ValueError(row["name"] + " requires Arcane Training")
    row["instance_id"] = source_instance_id
    row["object_state"] = deepcopy(obj.get(STATE))
    return row


def ignored_registration_keys(plan):
    retained = (plan or {}).get("retained_base")
    return {retained["registration_key"]} if isinstance(retained, dict) else set()


def slot_options(plan):
    return deepcopy(plan.get("slots", [])) if plan else []


def consumes_effect(plan, effect):
    return bool(plan and isinstance(effect, dict))


def _grant_ability(engine, actor, source_id, item_id, name):
    import state_grants as GRANTS
    if name not in engine.r.ability_effects:
        raise ValueError("unknown optional equipment ability: " + name)
    GRANTS.grant(actor, "abilities", name, source_id, "item", owner_id=actor.entity_id,
                 lifetime="equipped", rule_id=item_id)
    engine.register_abilities_one(actor, name)


def _grant_move(actor, source_id, item_id, move_id):
    import state_grants as GRANTS
    GRANTS.grant(actor, "moves", move_id, source_id, "item", owner_id=actor.entity_id,
                 lifetime="equipped", rule_id=item_id)


def install(engine, actor, source_id, plan):
    if plan is None:
        return [], 0
    import state_grants as GRANTS
    effect_sources = []
    for name in plan.get("abilities", ()):
        _grant_ability(engine, actor, source_id, plan["item_id"], name)
    for capability in plan.get("capabilities", ()):
        GRANTS.grant(actor, "capabilities", capability, source_id, "item", owner_id=actor.entity_id,
                     lifetime="equipped", rule_id=plan["item_id"])
    if plan["kind"] == "mental_shield" and plan["iron_mind"]:
        GRANTS.grant(actor, "capabilities", "정신봉인", source_id, "item", owner_id=actor.entity_id,
                     lifetime="equipped", rule_id=plan["item_id"])
    weapon_key = None
    if plan.get("weapon_kind"):
        import turn as TURN
        import optional_weapon_framework as FRAMEWORK
        weapon_key = TURN.equip_weapon(engine, actor, FRAMEWORK.crafted_weapon(engine,plan,{
            "name": plan["name"], "kind": plan["weapon_kind"], "grade": "좋음", "moves": []}))
        ledger = actor.custom_conditions["equipped_weapons"][weapon_key]
        grants = []
        for move_id in plan.get("moves", ()):
            _grant_move(actor, source_id, plan["item_id"], move_id)
            if move_id not in ledger["available_moves"]:
                ledger["available_moves"].append(move_id)
            grants.append(move_id)
        ledger["crafted_grants"] = grants
        ledger["item_id"] = plan["item_id"]
        ledger["instance_id"] = plan["instance_id"]
        ledger["optional_kind"] = plan["kind"]
    row = {
        "type": "optional_physical_equipment", "item_id": plan["item_id"],
        "kind": plan["kind"], "clause_id": plan["clause_id"],
        "instance_id": plan["instance_id"], "weapon_key": weapon_key,
        "save_condition": plan.get("save_condition"), "save_bonus": plan.get("save_bonus", 0),
        "mental_bonus": plan.get("mental_bonus", 0), "iron_mind": plan.get("iron_mind", False),
        "free_float": plan.get("free_float", 0), "weight_lb": plan.get("weight_lb"),
        "retained_base": deepcopy(plan.get("retained_base")),
        **({"space_suit_variant": plan["space_suit_variant"], "additional_cost": plan["additional_cost"]}
           if plan["kind"] == "space_suit" else {}),
    }
    effect_source = source_id + ":optional-contract"
    GRANTS.apply_owned(engine, actor, effect_source, lambda: actor.registry.append(row))
    effect_sources.append(effect_source)
    return effect_sources, 1


def bind_registration(engine, actor, registration, plan):
    if plan is None:
        return
    registration["optional_equipment"] = {
        "kind": plan["kind"], "clause_id": plan["clause_id"],
        "weapon_key": next((row.get("weapon_key") for row in actor.registry
                            if row.get("type") == "optional_physical_equipment"
                            and row.get("instance_id") == plan["instance_id"]), None),
    }
    obj = _object(engine, actor, plan["instance_id"], plan["item_id"])
    if plan["kind"] == "space_suit":
        obj.setdefault(STATE, {"schema_version": 1, "space_suit_variant": plan["space_suit_variant"]})
        obj["weight_kg"] = plan["weight_lb"] * 0.45359237
        _validate_object_state(obj, definition(engine.r, plan["item_id"]))
    if plan["kind"] == "shadow_walkers":
        retained = plan["retained_base"]
        base = getattr(actor, "_item_reg", {}).get(retained["registration_key"])
        if base is None or base.get("instance_id") != retained["instance_id"]:
            raise ValueError("Shadow Walkers retained base disappeared before binding")
        base["retained_by_shadow_walkers"] = plan["instance_id"]
        registration["optional_equipment"]["retained_base"] = deepcopy(retained)
        obj[STATE] = {"schema_version": 1, "retained_base": deepcopy(retained)}
    if plan["kind"] == "excalibur":
        state = obj.setdefault(STATE, {"schema_version": 1, "sacred_sword_type": "격투", "changes": []})
        _validate_object_state(obj, plan)
        registration["optional_equipment"]["sacred_sword_type"] = state["sacred_sword_type"]


def uninstall(engine, actor, registration):
    row = registration.get("optional_equipment")
    if not isinstance(row, dict):
        return
    key = row.get("weapon_key")
    if key is not None and key in actor.custom_conditions.get("equipped_weapons", {}):
        import turn as TURN
        TURN.unequip_weapon(engine, actor, key)
    retained = row.get("retained_base")
    if isinstance(retained, dict):
        base_key = retained.get("registration_key")
        base = getattr(actor, "_item_reg", {}).get(base_key)
        if base is not None:
            base.pop("retained_by_shadow_walkers", None)
            import items as ITEMS
            ITEMS.unregister_item(engine, actor, registration_key=base_key)
    instance_id = registration.get("instance_id")
    pending = actor.custom_conditions.get("blood_scythe_healing")
    if isinstance(pending, dict) and pending.get("instance_id") == instance_id:
        actor.custom_conditions.pop("blood_scythe_healing", None)


def _active(actor, kind=None):
    rows = [row for row in actor.registry if isinstance(row, dict)
            and row.get("type") == "optional_physical_equipment"
            and (kind is None or row.get("kind") == kind)]
    return rows


def save_bonus(actor, condition):
    return sum(row["save_bonus"] for row in _active(actor)
               if row.get("save_condition") == condition and isinstance(row.get("save_bonus"), int))


def mental_resistance_bonus(actor):
    return sum(row["mental_bonus"] for row in _active(actor, "mental_shield")
               if not row.get("iron_mind"))


def movement(actor, values):
    result = dict(values)
    bonus = max((row.get("free_float", 0) for row in _active(actor, "space_suit")), default=0)
    if bonus:
        result["levitate"] = max(result.get("levitate", 0), bonus)
    return result


def prepare_weapon_move(engine, actor, move, weapon_id=None):
    candidates = []
    for key, entry in actor.custom_conditions.get("equipped_weapons", {}).items():
        if entry.get("item_id") in KINDS and move.get("id") in entry.get("available_moves", ()):
            if weapon_id is None or weapon_id in (key, entry.get("item_id"), entry.get("instance_id"), entry["weapon"]["name"]):
                candidates.append((key, entry))
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValueError("crafted equipment move requires one explicit physical weapon")
    key, entry = candidates[0]
    out = deepcopy(move)
    import turn as TURN
    spec = TURN.WEAPON_KIND[entry["weapon"]["kind"]]
    raw = out.get("range", "")
    origin = "melee" if "근접" in spec["range"] else int(spec["range"].split(",")[0])
    out["_weapon_attack"] = {
        "key": key, "range": {"raw": raw, "origin": origin, "targets": 1, "parsed": True},
        "db_bonus": spec["db"], "accuracy_bonus": 0,
        "minimum_distance": spec.get("min_range", 0), "source": entry["item_id"],
    }
    out["_optional_crafted_equipment"] = {
        "item_id": entry["item_id"], "instance_id": entry["instance_id"],
        "kind": entry.get("optional_kind", KINDS[entry["item_id"]]), "weapon_key": key,
    }
    if entry.get("optional_kind") == "nine_flames_staff":
        out["class"] = "특수"
        out["_optional_crafted_equipment"]["arcane"] = True
    if entry.get("optional_kind") == "fairy_fire_sword" and move.get("id") == "move/베어가르기":
        out["type"] = "불꽃"
        out["name"] = "플레임턴지"
    if entry.get("optional_kind") == "candy_hammer":
        out["_optional_crafted_equipment"]["candy_type"] = True
    if entry.get("optional_kind") == "chaos_dunker":
        out["_optional_crafted_equipment"]["friendly"] = True
        out["_optional_crafted_equipment"]["ground_immunity_bypass"] = True
    if entry.get("optional_kind") == "ruyi_staff":
        out["_weapon_attack"]["range"].update(raw="5, 대상 1", origin=5, targets=1, parsed=True)
        pending = actor.custom_conditions.get("ruyi_smite_pending")
        if isinstance(pending, dict) and pending.get("instance_id") == entry["instance_id"]:
            shape = pending["mode"]
            out["_weapon_attack"]["range"] = {
                "raw": ("파열 " if shape == "burst" else "근접 폭발 ") + str(pending["size"]),
                "origin": "melee", "shape": shape, "size": pending["size"],
                "targets": None, "parsed": True,
            }
            out["_optional_crafted_equipment"]["smite"] = True
    if entry["item_id"] == "crafted_item/엑스칼리버" and move.get("id") == "move/성스러운칼":
        obj = _object(engine, actor, entry["instance_id"], entry["item_id"])
        state = obj.get(STATE)
        if not isinstance(state, dict):
            raise ValueError("Excalibur physical type state is missing")
        out["type"] = state["sacred_sword_type"]
    return out


def marker(move):
    row = move.get("_optional_crafted_equipment") if isinstance(move, dict) else None
    return row if isinstance(row, dict) and row.get("item_id") in KINDS else None


def effectiveness(engine, target, move, current):
    row = marker(move)
    if row is None:
        return current
    if row["kind"] == "candy_hammer":
        return 1.0
    if row["kind"] == "fairy_fire_sword" and any(t in ("페어리", "Fairy") for t in target.types):
        return max(1.5, current)
    if row["kind"] == "chaos_dunker" and move.get("type") in ("땅", "Ground"):
        import type_state as TYPES
        steps = 0
        for defender_type in target.types:
            value = TYPES.matchup(engine.r, move["type"], defender_type)
            if value == 0:
                value = 1
            steps += 1 if value > 1 else -1 if value < 1 else 0
        table = engine.r.mech("combat/type-effectiveness")["multiplier_by_net_steps"]
        return table[str(max(-3, min(3, steps)))]
    return current


def bypass_ability_immunity(move, move_type):
    row = marker(move)
    return bool(row and row.get("ground_immunity_bypass") and move_type in ("땅", "Ground"))


def filter_targets(attacker, move, targets):
    row = marker(move)
    if not (row and row.get("friendly")) and '친화' not in move.get('keywords',()):
        return targets
    return [target for target in targets if target.side != attacker.side]


def damage_roll_bonus(engine, attacker, target, move):
    row = marker(move)
    if not row or row["kind"] != "blood_scythe":
        return 0
    return 5 if engine.type_multiplier("악", target)[0] > 1 else 0


def resistance_steps(engine, target, move_type):
    if move_type not in ("불꽃", "Fire") or engine.grid is None:
        return 0
    from grid import cheb
    return 1 if any(wearer is not target and wearer.side == target.side
                    and cheb(wearer.pos, target.pos) <= 2 and _active(wearer, "svalinn")
                    for wearer in engine.time_actors()) else 0


def blocks_status(engine, target, condition, source):
    if condition not in ("화상", "Burn") or not _active(target, "svalinn"):
        return False
    move = source if isinstance(source, dict) else engine.r.moves.get(source) if isinstance(source, str) else None
    return isinstance(move, dict) and move.get("type") in ("불꽃", "Fire")


def observe_attack_damage(engine, attacker, target, move, receipt):
    row = marker(move)
    if row is None or receipt.get("net_hp_loss", 0) <= 0:
        return
    if row["kind"] == "blood_scythe":
        attacker.custom_conditions["blood_scythe_healing"] = {
            "instance_id": row["instance_id"], "damage": receipt["net_hp_loss"],
            "target_id": target.entity_id, "at": engine.elapsed_seconds,
            "scene": __import__("frequency").state(attacker)["scene"],
        }
    if row["kind"] == "kaladanda" and "기절" in target.conditions:
        target.custom_conditions[NO_AWAKENING] = {
            "schema_version": 1, "until": engine.elapsed_seconds + 24 * 60 * 60,
            "attacker_id": attacker.entity_id, "item_id": row["item_id"],
            "instance_id": row["instance_id"], "move_id": move["id"],
        }


def awakening_blocked(engine, actor, *, at_time=None):
    row = actor.custom_conditions.get(NO_AWAKENING)
    if row is None:
        return False
    _validate_no_awakening(engine, actor, row)
    now = engine.elapsed_seconds if at_time is None else at_time
    if type(now) is not int or now < engine.elapsed_seconds:
        raise ValueError("awakening observation time must be a present or future whole second")
    if now >= row["until"]:
        actor.custom_conditions.pop(NO_AWAKENING, None)
        return False
    return True


def _equipped(actor, kind):
    rows = _active(actor, kind)
    if len(rows) != 1:
        raise ValueError("exactly one live " + kind + " physical registration required")
    return rows[0]


def claim_blood_scythe_healing(engine, actor):
    row = _equipped(actor, "blood_scythe")
    pending = actor.custom_conditions.get("blood_scythe_healing")
    if not isinstance(pending, dict) or pending.get("instance_id") != row["instance_id"]:
        raise ValueError("Blood Scythe needs actual unclaimed weapon damage")
    import frequency as FREQ
    frequency = {"kind": "scene", "uses": 1}
    key = "optional-equipment:blood-scythe:" + row["instance_id"]
    if pending.get("scene") != FREQ.state(actor)["scene"]:
        raise ValueError("Blood Scythe damage belongs to an expired scene")
    if not FREQ.activation_allowed(actor, key, frequency, engine=engine):
        raise ValueError("Blood Scythe scene healing spent")
    def apply(staged, staged_actor):
        current = staged_actor.custom_conditions.pop("blood_scythe_healing")
        FREQ.consume_activation(staged_actor, key, frequency, engine=staged)
        amount = current["damage"] // 2
        gained = staged.heal(staged_actor, amount, source_kind="feature")
        return {"healed": gained, "eligible_damage": current["damage"], "instance_id": row["instance_id"]}
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor, apply)


def lick_candy_hammer(engine, actor):
    row = _equipped(actor, "candy_hammer")
    import frequency as FREQ
    import turn as TURN
    frequency = {"kind": "daily", "uses": 1}
    key = "optional-equipment:candy-hammer-lick:" + row["instance_id"]
    if not FREQ.activation_allowed(actor, key, frequency, engine=engine):
        raise ValueError("Candy Hammer daily lick spent")
    def apply(staged, staged_actor):
        if not TURN.spend(staged, staged_actor, "standard", "캔디 해머 핥기"):
            return {"activated": False, "healed": 0}
        FREQ.consume_activation(staged_actor, key, frequency, engine=staged)
        return {"activated": True, "healed": staged.heal(staged_actor, staged.tick(staged_actor) * 2,
                                                           source_kind="feature")}
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor, apply)


def ask_yata_truth(engine, actor, target, *, question, truthful_answer, looking):
    row = _equipped(actor, "yata_mirror")
    if not isinstance(question, str) or not question.strip() or not isinstance(truthful_answer, str):
        raise ValueError("Yata Mirror requires one explicit question and adjudicated truthful answer")
    if looking is not True:
        raise ValueError("Yata Mirror target must actually be looking at the mirror")
    import world_entities as WORLD
    WORLD.require_actors(engine, actor, target)
    import frequency as FREQ
    import turn as TURN
    frequency = {"kind": "daily", "uses": 1}
    key = "optional-equipment:yata-truth:" + row["instance_id"]
    if not FREQ.activation_allowed(actor, key, frequency, engine=engine):
        raise ValueError("Yata Mirror daily truth spent")
    def apply(staged, staged_actor, staged_target):
        if not TURN.spend(staged, staged_actor, "standard", "야타의 거울 진실 질문"):
            return {"activated": False}
        FREQ.consume_activation(staged_actor, key, frequency, engine=staged)
        receipt = {"schema_version": 1, "instance_id": row["instance_id"],
                   "target_id": staged_target.entity_id, "question": question.strip(),
                   "truthful_answer": truthful_answer, "at": staged.elapsed_seconds}
        staged_actor.custom_conditions.setdefault("yata_truth_receipts", []).append(receipt)
        return {"activated": True, **receipt}
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor, apply, participants=(target,))


def reveal_observation(engine, observer, target, result):
    if not _active(observer, "yata_mirror"):
        return result
    out = deepcopy(result)
    if isinstance(target, dict) and target.get("kind") == "illusion":
        out.update(status="observed", reason="yata_mirror_true_reflection")
        out.setdefault("values", {})["illusion_detected"] = True
    elif hasattr(target, "entity_id"):
        transformed = target.custom_conditions.get("transformed")
        disguise = target.spec.get("disguise") or target.custom_conditions.get("disguise")
        out["yata_reflection"] = {
            "target_id": target.entity_id, "disguised": disguise is not None,
            "transformed": transformed is not None or getattr(target, "form", None) == "transformed",
        }
    out["illusion_immunity"] = True
    return out


def activate_spread_needle(engine, actor, targets, *, fixed_strikes=None):
    row = _equipped(actor, "spread_needle")
    targets = tuple(targets)
    if not targets or len({id(x) for x in targets}) != len(targets):
        raise ValueError("Spread Needle requires distinct actual targets")
    import world_entities as WORLD
    WORLD.require_actors(engine, actor, *targets)
    if engine.grid is None:
        raise ValueError("Spread Needle split attack requires a map")
    from grid import cheb
    if any(t is actor or t.fainted or t.captured or cheb(actor.pos, t.pos) > 4 for t in targets):
        raise ValueError("Spread Needle target is not an active target within short range")
    if fixed_strikes is not None and (type(fixed_strikes) is not int or not 1 <= fixed_strikes <= 8):
        raise ValueError("Spread Needle fixed 1d8 result must be 1 through 8")
    def apply(staged, staged_actor, *staged_targets):
        strikes = fixed_strikes if fixed_strikes is not None else POOLS.die(staged.rng, 8)
        if len(staged_targets) > strikes:
            raise ValueError("Spread Needle selected more distinct targets than its 1d8 result")
        import move_activation as ACTIVATION
        import action_lifecycle as ACTION
        total = 0
        with ACTIVATION.open_scope(staged, staged_actor, "move/구슬던지기", staged_targets,
                                   shared=False, primary=staged_targets[0]) as (activation, accuracy):
            for index, staged_target in enumerate(staged_targets):
                if index == 0:
                    total += staged.use_move(staged_actor, staged_target, "move/구슬던지기",
                                             _activation=activation, _shared_accuracy=accuracy,
                                             weapon_id=row["instance_id"])
                else:
                    with ACTION.move_grant(staged, staged_actor, staged_target, "move/구슬던지기",
                                           source="same_move_activation") as grant:
                        total += staged.use_move(staged_actor, staged_target, "move/구슬던지기",
                                                 count_use=False, _activation=activation,
                                                 _shared_accuracy=accuracy, _action_grant=grant,
                                                 weapon_id=row["instance_id"])
        return {"activated": bool(activation.get("started")), "rolled_strikes": strikes,
                "targets": [x.entity_id for x in staged_targets], "damage": total, "damage_base": 2}
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor, apply,
                             participants=tuple(x for x in targets if x is not actor), include_grid=True)


def activate_ruyi_smite(engine, actor, primary, move_id, everyone, *, mode, size, aim=None):
    row = _equipped(actor, "ruyi_staff")
    if move_id not in definition(engine.r, row["item_id"])["moves"]:
        raise ValueError("Ruyi Smite requires one of its physical weapon moves")
    limits = {"burst": (1, 3), "close_blast": (2, 4)}
    if mode not in limits or type(size) is not int or not limits[mode][0] <= size <= limits[mode][1]:
        raise ValueError("Ruyi Smite requires Burst 1-3 or Close Blast 2-4")
    if aim is None:
        aim = actor.pos if mode == "burst" else primary.pos
    everyone = tuple(everyone)
    import world_entities as WORLD
    WORLD.require_actors(engine, actor, primary, *everyone)
    import frequency as FREQ
    frequency = {"kind": "scene", "uses": 2}
    key = "optional-equipment:ruyi-smite:" + row["instance_id"]
    if not FREQ.activation_allowed(actor, key, frequency, engine=engine):
        raise ValueError("Ruyi Smite scene frequency spent")
    participants = tuple(x for x in dict.fromkeys((primary, *everyone)) if x is not actor)
    def apply(staged, staged_actor, *staged_participants):
        index = {x.entity_id: x for x in staged_participants}
        staged_primary = index[primary.entity_id]
        staged_everyone = [staged_actor if x is actor else index[x.entity_id] for x in everyone]
        before = staged_actor.move_uses.get(move_id, 0)
        staged_actor.custom_conditions["ruyi_smite_pending"] = {
            "instance_id": row["instance_id"], "mode": mode, "size": size}
        try:
            damage = staged.use_move_on(staged_actor, staged_primary, move_id, staged_everyone,
                                        weapon_id=row["instance_id"], aim=aim)
        finally:
            staged_actor.custom_conditions.pop("ruyi_smite_pending", None)
        activated = staged_actor.move_uses.get(move_id, 0) > before
        if activated:
            FREQ.consume_activation(staged_actor, key, frequency, engine=staged)
        return {"activated": activated, "mode": mode, "size": size, "smite": True, "damage": damage}
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor, apply, participants=participants, include_grid=True)


def change_excalibur_type(engine, actor, instance_id, chosen_type):
    import items as ITEMS
    import turn as TURN
    if chosen_type not in ITEMS.TYPES:
        raise ValueError("Excalibur requires one canonical type")
    obj = _object(engine, actor, instance_id, "crafted_item/엑스칼리버")
    if obj.get("equipped_by") != actor.entity_id:
        raise ValueError("actual equipped Excalibur required")
    if not any(row.get("instance_id") == instance_id for row in _active(actor, "excalibur")):
        raise ValueError("live Excalibur registration required")
    def apply(staged, staged_actor):
        actual = _object(staged, staged_actor, instance_id, "crafted_item/엑스칼리버")
        state = actual.get(STATE)
        if not isinstance(state, dict):
            raise ValueError("Excalibur physical type state is missing")
        if not TURN.spend(staged, staged_actor, "swift", "엑스칼리버 성스러운칼 타입 변경"):
            return {"changed": False, "type": state["sacred_sword_type"]}
        before = state["sacred_sword_type"]
        state["sacred_sword_type"] = chosen_type
        state["changes"].append({"at": staged.elapsed_seconds, "from": before, "to": chosen_type})
        _validate_object_state(actual, definition(staged.r, "crafted_item/엑스칼리버"))
        return {"changed": True, "type": chosen_type}
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor, apply)


def activate_heartwarming_flute(engine, actor, *, protected_allies=()):
    row = next((row for row in _active(actor, "heartwarming_flute")), None)
    if row is None:
        raise ValueError("actual equipped Heartwarming Flute required")
    import frequency as FREQ
    import skill_modifiers as SKILLS
    import turn as TURN
    import world_entities as WORLD
    participants = list(WORLD.actor_index(engine).values())
    protected_allies = tuple(protected_allies)
    if len(set(map(id, protected_allies))) != len(protected_allies):
        raise ValueError("Heartwarming Flute requires distinct protected allies")
    occult = SKILLS.effective_rank(engine.r, actor, "오컬트학")
    if len(protected_allies) > occult:
        raise ValueError("Heartwarming Flute exceeds the wielder's Occult rank")
    for ally in protected_allies:
        if ally not in participants or ally.side != actor.side:
            raise ValueError("Heartwarming Flute protection requires actual allies")
    if engine.grid is None:
        raise ValueError("Heartwarming Flute requires mapped 20 metre recipients")
    from grid import cheb
    in_range = [target for target in participants if cheb(actor.pos, target.pos) <= 20]
    if any(ally not in in_range for ally in protected_allies):
        raise ValueError("Heartwarming Flute protected ally outside 20 metres")
    frequency = {"kind": "scene", "uses": 1}
    frequency_id = "optional-equipment:heartwarming-flute:" + row["instance_id"]
    if not FREQ.activation_allowed(actor, frequency_id, frequency, engine=engine):
        raise ValueError("Heartwarming Flute scene frequency spent")
    def apply(staged, staged_actor, *staged_participants):
        staged_index = {target.entity_id: target for target in staged_participants}
        if not TURN.spend(staged, staged_actor, "standard", "따스한 플루트"):
            return {"activated": False, "cured": [], "protected": []}
        FREQ.consume_activation(staged_actor, frequency_id, frequency, engine=staged)
        cured = []
        for target in staged_participants:
            if target.entity_id in {x.entity_id for x in in_range} and "마비" in target.conditions:
                staged.cure_status(target, "마비")
                cured.append(target.entity_id)
        protected = []
        for original in protected_allies:
            target = staged_index[original.entity_id]
            source = frequency_id + ":scene:" + str(FREQ.state(staged_actor)["scene"]) + ":" + target.entity_id
            import state_grants as GRANTS
            GRANTS._source(target, source, "optional_equipment_scene", owner_id=staged_actor.entity_id,
                           lifetime="scene", rule_id="crafted_item/따스한-플루트",
                           instance_id=row["instance_id"], scene=FREQ.state(staged_actor)["scene"])
            effect = {"type": "damage_reduction", "value": 5, "_scope": {"type": "고스트"},
                      "source": "crafted_item/따스한-플루트"}
            GRANTS.apply_owned(staged, target, source + ":effect", lambda target=target, effect=effect: target.modifiers.append(effect))
            target.spec["state_grants"]["sources"][source]["effect_sources"] = [source + ":effect"]
            protected.append(target.entity_id)
        return {"activated": True, "cured": cured, "protected": protected}
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor, apply, participants=tuple(participants))


def boundary(engine, event):
    if event != "scene_end":
        return
    import state_grants as GRANTS
    for actor in engine.time_actors():
        sources = list(actor.spec.get("state_grants", {}).get("sources", {}).items())
        for source_id, row in sources:
            if row.get("kind") == "optional_equipment_scene" and row.get("lifetime") == "scene":
                for effect_source in row.get("effect_sources", ()):
                    GRANTS.revoke(actor, effect_source, engine=engine)
                GRANTS.revoke(actor, source_id, engine=engine)


def _space_suit_configuration(obj, row):
    state = obj.get(STATE)
    if state is None:
        variant = "ordinary"
    elif (not isinstance(state, dict) or set(state) != {"schema_version", "space_suit_variant"}
          or state.get("schema_version") != 1):
        raise ValueError("Space Suit requires its exact physical variant choice")
    else:
        variant = state["space_suit_variant"]
    if variant not in row["variants"]:
        raise ValueError("Space Suit variant must be ordinary or robotic")
    return variant, deepcopy(row["variants"][variant])


def configure_space_suit(engine, owner, instance_id, variant, *, reason):
    """Observe the selected existing suit version before physical equip.

    Additional cost is the sourced price difference, not a purchase receipt.
    """
    import world_entities as WORLD
    import state_grants as GRANTS
    WORLD.require_actors(engine, owner)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Space Suit variant observation needs its actual reason")
    row = definition(engine.r, "item/우주복")
    if variant not in row["variants"]:
        raise ValueError("Space Suit variant must be ordinary or robotic")
    obj = _object(engine, owner, instance_id, "item/우주복")
    if obj.get("owner_id") != owner.entity_id:
        raise ValueError("Space Suit variant requires its actual owner")
    if any(obj.get(key) for key in ("equipped_by", "carrier_id", "telekinetic_holder_id")):
        raise ValueError("observe Space Suit variant before carrying or equipping it")
    WORLD.require_usable_object(obj)
    def apply(staged, actor):
        actual = _object(staged, actor, instance_id, "item/우주복")
        actual[STATE] = {"schema_version": 1, "space_suit_variant": variant}
        actual["weight_kg"] = row["variants"][variant]["weight_lb"] * 0.45359237
        _validate_object_state(actual, row)
        return deepcopy(actual[STATE])
    return GRANTS.transition(engine, owner, apply)


def _validate_object_state(obj, row):
    if row["kind"] == "space_suit":
        _, configuration = _space_suit_configuration(obj, row)
        weight = obj.get("weight_kg")
        if weight is not None and (type(weight) not in (int, float)
                or abs(weight - configuration["weight_lb"] * 0.45359237) > 1e-9):
            raise ValueError("Space Suit actual object weight differs from its selected variant")
        return True
    if row["kind"] == "shadow_walkers":
        state = obj.get(STATE)
        retained = state.get("retained_base") if isinstance(state, dict) else None
        if (not isinstance(state, dict) or state.get("schema_version") != 1
                or not isinstance(retained, dict)
                or set(retained) != {"registration_key", "instance_id", "item_id", "source_id"}
                or any(not isinstance(value, str) or not value for value in retained.values())):
            raise ValueError("Shadow Walkers retained feet-equipment relation changed")
        return True
    if row["kind"] != "excalibur":
        return True
    state = obj.get(STATE)
    if (not isinstance(state, dict) or state.get("schema_version") != 1
            or state.get("sacred_sword_type") not in __import__("items").TYPES
            or not isinstance(state.get("changes"), list)):
        raise ValueError("Excalibur physical type state changed")
    for change in state["changes"]:
        if (not isinstance(change, dict) or set(change) != {"at", "from", "to"}
                or change["from"] not in __import__("items").TYPES
                or change["to"] not in __import__("items").TYPES
                or type(change["at"]) is not int or change["at"] < 0):
            raise ValueError("Excalibur type change receipt changed")
    return True


def _validate_no_awakening(engine, actor, row):
    if (not isinstance(row, dict) or set(row) != {"schema_version", "until", "attacker_id", "item_id", "instance_id", "move_id"}
            or row.get("schema_version") != 1 or type(row.get("until")) is not int
            or row["until"] < engine.elapsed_seconds or row.get("item_id") != "crafted_item/카라단다"
            or row.get("move_id") not in definition(engine.r, "crafted_item/카라단다")["moves"]
            or any(not isinstance(row.get(key), str) or not row[key]
                   for key in ("attacker_id", "instance_id", "move_id"))):
        raise ValueError("Kaladanda no-awakening receipt changed")
    return True


def validate_world(engine, index):
    policy(engine.r)
    objects = getattr(engine, "_physical_objects", {})
    for actor in index.values():
        for row in _active(actor):
            item_id = row.get("item_id")
            registration = next((record for record in getattr(actor, "_item_reg", {}).values()
                                 if record.get("item_id") == item_id and record.get("instance_id") == row.get("instance_id")), None)
            obj = objects.get(row.get("instance_id"))
            if (registration is None or not isinstance(obj, dict) or obj.get("equipped_by") != actor.entity_id
                    or obj.get("item_rule_id") != item_id):
                raise ValueError("optional equipment projection lacks its live physical registration")
            definition_row = definition(engine.r, item_id)
            if definition_row["kind"] in ("excalibur", "shadow_walkers", "space_suit"):
                _validate_object_state(obj, definition_row)
            if definition_row["kind"] == "space_suit":
                variant, configuration = _space_suit_configuration(obj, definition_row)
                if (row.get("space_suit_variant") != variant
                        or any(row.get(key) != configuration[key] for key in ("weight_lb", "additional_cost"))):
                    raise ValueError("Space Suit projection differs from its actual physical variant")
            if definition_row["kind"] == "shadow_walkers":
                retained = row.get("retained_base")
                base = getattr(actor, "_item_reg", {}).get(retained.get("registration_key")) if isinstance(retained, dict) else None
                base_obj = objects.get(retained.get("instance_id")) if isinstance(retained, dict) else None
                if (base is None or base.get("retained_by_shadow_walkers") != row["instance_id"]
                        or not isinstance(base_obj, dict) or base_obj.get("equipped_by") != actor.entity_id):
                    raise ValueError("Shadow Walkers lost its live retained feet-equipment participant")
        no_awaken = actor.custom_conditions.get(NO_AWAKENING)
        if no_awaken is not None:
            _validate_no_awakening(engine, actor, no_awaken)
        receipts = actor.custom_conditions.get("yata_truth_receipts", [])
        if not isinstance(receipts, list):
            raise ValueError("Yata Mirror truth receipts must be a list")
        if receipts:
            _require_selected(engine.r, "crafted_item/야타의-거울")
        for receipt in receipts:
            if (not isinstance(receipt, dict)
                    or set(receipt) != {"schema_version", "instance_id", "target_id", "question", "truthful_answer", "at"}
                    or receipt.get("schema_version") != 1 or type(receipt.get("at")) is not int
                    or receipt["at"] < 0 or receipt["at"] > engine.elapsed_seconds
                    or any(not isinstance(receipt.get(key), str) for key in ("instance_id", "target_id", "question", "truthful_answer"))
                    or not receipt["instance_id"] or not receipt["target_id"] or not receipt["question"]):
                raise ValueError("Yata Mirror truth receipt changed")
    return True
