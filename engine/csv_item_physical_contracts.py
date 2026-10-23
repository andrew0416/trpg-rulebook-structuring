"""Actual physical-owner, activation-receipt and lifetime contracts for CSV items."""
from copy import deepcopy

import common_checks as C
import csv_item_contract_policy as POLICY
import roll_pools as POOLS


OBJECT_STATE = "csv_remaining_item_state"
ACTOR_STATE = "csv_remaining_item_actor_state"
PLAN = "_csv_remaining_item_contract"
PENDING = "csv_remaining_item_pending"

ITEM_KINDS = {
    "item/몬스터볼-캐논": "pokeball_cannon",
    "item/타입-공부-메뉴얼-1": "type_study_manual",
    "item/부스트에너지": "booster_energy",
    "item/다이맥스벤드": "dynamax_band",
    "item/돌격조끼": "assault_vest",
    "item/풍선": "air_balloon",
    "item/약점보험": "weakness_policy",
    "item/탈출버튼": "eject_button",
    "item/탈출팩": "eject_pack",
    "item/레드카드": "red_card",
    "item/만능우산": "utility_umbrella",
    "item/속임수주사위": "loaded_dice",
}
POKEMON_ONLY = {"assault_vest", "air_balloon", "weakness_policy", "eject_button", "eject_pack", "red_card", "loaded_dice"}
TRAINER_ONLY = {"pokeball_cannon", "type_study_manual", "booster_energy", "dynamax_band"}
REACTIONS = {"weakness_policy", "eject_button", "eject_pack", "red_card"}


def definition(rules, item_id):
    row = POLICY.definition(rules, item_id=item_id)
    return row if row and row["kind"] == ITEM_KINDS.get(item_id) else None


def _objects(engine):
    return getattr(engine, "_physical_objects", {})


def _object(engine, actor, instance_id, item_id):
    obj = _objects(engine).get(instance_id)
    if (not isinstance(obj, dict) or obj.get("kind") != "item_instance" or obj.get("item_rule_id") != item_id
            or actor.entity_id not in (obj.get("owner_id"), obj.get("carrier_id"), obj.get("equipped_by"))):
        raise ValueError("remaining CSV equipment requires its actual owned physical item")
    import world_entities as WORLD
    WORLD.require_physical_access(obj)
    return obj


def _new_state(row, now):
    state = {"schema_version": 1, "clause_id": row["clause_id"], "item_id": row["item_id"],
             "kind": row["kind"], "created_at": now, "history": []}
    if row["kind"] == "pokeball_cannon":
        state["loaded_ball_instance_id"] = None
    elif row["kind"] == "type_study_manual":
        state.update(chosen_type=None, study_rank=0)
    elif row["kind"] in REACTIONS:
        state["scene_uses"] = []
    return state


def _state(engine, actor, row, obj, *, create=False):
    state = obj.get(OBJECT_STATE)
    if state is None and create:
        state = obj[OBJECT_STATE] = _new_state(row, engine.elapsed_seconds)
    if state is None:
        raise ValueError("remaining CSV equipment physical state is missing")
    _validate_object_state(engine, obj, row=row)
    return state


def prepare_register(engine, actor, item_id, source_instance_id=None):
    if item_id not in ITEM_KINDS:
        return None
    row = definition(engine.r, item_id)
    if row is None:
        raise ValueError("remaining CSV equipment policy is missing")
    if row["kind"] in POKEMON_ONLY and actor.kind != "pokemon":
        raise ValueError("this remaining CSV held item is Pokemon-only")
    if row["kind"] in TRAINER_ONLY and actor.kind != "trainer":
        raise ValueError("this remaining CSV equipment is Trainer-only")
    if source_instance_id is None:
        raise ValueError("remaining CSV equipment requires an actual physical instance")
    _object(engine, actor, source_instance_id, item_id)
    return dict(row, **{PLAN: True})


def consumes_effect(plan, effect):
    return bool(plan and plan.get(PLAN) is True and isinstance(effect, dict))


def install(engine, actor, source_id, plan):
    if not plan or plan.get(PLAN) is not True:
        return [], 0
    instance_id = source_id.split("equipment:", 1)[1] if source_id.startswith("equipment:") else None
    obj = _object(engine, actor, instance_id, plan["item_id"])
    state = _state(engine, actor, plan, obj, create=True)
    effect_sources = []
    if plan["kind"] == "pokeball_cannon":
        import optional_weapon_framework as FRAMEWORK
        import turn as TURN
        weapon = FRAMEWORK.crafted_weapon(engine, {"instance_id": instance_id}, {
            "name": engine.r.items_mech[plan["item_id"]]["name"],
            "kind": "장거리 사격무기", "grade": "좋음", "moves": []})
        key = TURN.equip_weapon(engine, actor, weapon)
        actor.custom_conditions["equipped_weapons"][key].update(
            item_id=plan["item_id"], instance_id=instance_id)
    if plan["kind"] == "assault_vest":
        import state_grants as GRANTS
        effect_source = source_id + ":csv:spdef"
        GRANTS.numeric(actor, "stats.spd", 5, effect_source)
        GRANTS.state(actor)["effects"][effect_source] = {"rows": [], "listeners": [], "numbers": True}
        effect_sources.append(effect_source)
        engine.apply_status(actor, "난동", source=plan["item_id"])
        actor.spec.setdefault(ACTOR_STATE, {})["assault_vest_rampage"] = {
            "instance_id": instance_id, "started_at": engine.elapsed_seconds,
            "encounter": _encounter_key(engine, actor), "active": True,
        }
    elif plan["kind"] == "air_balloon":
        import state_grants as GRANTS
        GRANTS.grant(actor, "abilities", "부유", source_id, "item", owner_id=actor.entity_id,
                     lifetime="equipped", rule_id=plan["item_id"])
    state["history"].append({"event": "equipped", "at": engine.elapsed_seconds, "actor_id": actor.entity_id})
    return effect_sources, 1


def bind_registration(engine, actor, registration, plan):
    if not plan or plan.get(PLAN) is not True:
        return
    obj = _object(engine, actor, registration.get("instance_id"), plan["item_id"])
    state = _state(engine, actor, plan, obj)
    registration["csv_item_projection"] = _projection(registration, state)
    if plan["kind"] == "pokeball_cannon":
        matches = [key for key, value in actor.custom_conditions.get("equipped_weapons", {}).items()
                   if value.get("instance_id") == registration["instance_id"]
                   and value.get("item_id") == plan["item_id"]]
        if len(matches) != 1:
            raise ValueError("Pokeball Cannon must own exactly one physical weapon grant")
        registration["cannon_weapon_key"] = matches[0]


def uninstall(engine, actor, registration):
    row = definition(engine.r, registration.get("item_id"))
    if row is None:
        return
    if row["kind"] == "pokeball_cannon":
        import turn as TURN
        TURN.unequip_weapon(engine, actor, registration["cannon_weapon_key"])
    obj = _objects(engine).get(registration.get("instance_id"))
    if isinstance(obj, dict) and OBJECT_STATE in obj:
        state = _state(engine, actor, row, obj)
        state["history"].append({"event": "unequipped", "at": engine.elapsed_seconds, "actor_id": actor.entity_id})
    # Assault Vest's +5 is source-owned and is revoked by items.unregister_item.
    # Its printed Rampage is encounter-owned and deliberately remains locked.


def _projection(registration, state):
    result = {"schema_version": 1, "instance_id": registration.get("instance_id"),
              "clause_id": state["clause_id"], "item_id": state["item_id"], "kind": state["kind"]}
    for field in ("loaded_ball_instance_id", "chosen_type", "study_rank", "scene_uses"):
        if field in state:
            result[field] = deepcopy(state[field])
    return result


def _active(engine, actor, kinds):
    kinds = {kinds} if isinstance(kinds, str) else set(kinds)
    sources = actor.spec.get("state_grants", {}).get("sources", {})
    found = []
    for key, registration in getattr(actor, "_item_reg", {}).items():
        row = definition(engine.r, registration.get("item_id"))
        if row is None or row["kind"] not in kinds or registration.get("state_source") not in sources:
            continue
        obj = _object(engine, actor, registration.get("instance_id"), row["item_id"])
        if obj.get("equipped_by") != actor.entity_id:
            raise ValueError("remaining CSV equipment registration and physical holder disagree")
        state = _state(engine, actor, row, obj)
        if registration.get("csv_item_projection") != _projection(registration, state):
            raise ValueError("remaining CSV equipment projection differs from physical state")
        found.append((key, row, registration, obj, state))
    return found


def _scene_key(engine, actor):
    import frequency as FREQUENCY
    return [getattr(engine, "session_epoch", 0), FREQUENCY.state(actor)["scene"]]


def _encounter_key(engine, actor):
    return [getattr(engine, "session_epoch", 0), getattr(engine, "_party_encounter_epoch", 0)]


def _sync(entry):
    _, _, registration, _, state = entry
    registration["csv_item_projection"] = _projection(registration, state)


def configure_type_manual(engine, owner, instance_id, chosen_type, rank):
    if chosen_type not in __import__("items").TYPES or rank not in (1, 2):
        raise ValueError("Type Study Manual needs one canonical type and rank one or two")
    _manual_skill(engine,owner,rank)
    obj = _object(engine, owner, instance_id, "item/타입-공부-메뉴얼-1")
    active = [entry for entry in _active(engine, owner, "type_study_manual")
              if entry[2]["instance_id"] == instance_id]
    row = definition(engine.r, "item/타입-공부-메뉴얼-1")
    state = _state(engine, owner, row, obj, create=True)
    if state["chosen_type"] not in (None, chosen_type):
        raise ValueError("Type Study Manual's studied type is immutable")
    if rank < state["study_rank"]:
        raise ValueError("Type Study Manual rank cannot decrease")
    state.update(chosen_type=chosen_type, study_rank=rank)
    state["history"].append({"event": "studied", "at": engine.elapsed_seconds, "rank": rank, "type": chosen_type})
    for entry in active:
        _sync(entry)
    return deepcopy(state)


def manual_capture_modifier(engine, trainer, target, instance_id):
    obj = _object(engine, trainer, instance_id, "item/타입-공부-메뉴얼-1")
    row = definition(engine.r, "item/타입-공부-메뉴얼-1")
    state = _state(engine, trainer, row, obj)
    _manual_skill(engine,trainer,1)
    return -5 if state["study_rank"] >= 1 and state["chosen_type"] in target.types else 0


def manual_training_level(engine, trainer, pokemon, instance_id, *, baby_food=False, champion_trainer=False):
    obj = _object(engine, trainer, instance_id, "item/타입-공부-메뉴얼-1")
    state = _state(engine, trainer, definition(engine.r, "item/타입-공부-메뉴얼-1"), obj)
    _manual_skill(engine,trainer,2)
    eligible = state["study_rank"] >= 2 and state["chosen_type"] in pokemon.types
    return 1 if eligible and not baby_food and not champion_trainer else 0


def _manual_skill(engine, owner, rank):
    import skill_modifiers as SKILL
    if owner.kind != 'trainer' or SKILL.rank(engine.r,owner,'포켓몬학')[2] < (3 if rank == 1 else 5):
        raise ValueError('Type Study Manual requires Novice/Expert Pokemon Education for its actual rank')


def load_cannon(engine, trainer, cannon_instance_id, ball_instance_id):
    matches = [entry for entry in _active(engine, trainer, "pokeball_cannon") if entry[2]["instance_id"] == cannon_instance_id]
    if len(matches) != 1:
        raise ValueError("one actual equipped Pokeball Cannon is required")
    entry = matches[0]
    ball = _objects(engine).get(ball_instance_id)
    if (not isinstance(ball, dict) or ball.get("kind") != "item_instance" or trainer.entity_id not in
            (ball.get("owner_id"), ball.get("carrier_id")) or "볼" not in str(ball.get("item_rule_id", ""))):
        raise ValueError("Pokeball Cannon requires one actual possessed ball instance")
    _object(engine,trainer,ball_instance_id,ball['item_rule_id'])
    for attempt in trainer.spec.get('capture_attempts',{}).values():
        if attempt.get('physical_instance_id',attempt.get('cannon',{}).get('ball_instance_id'))==ball_instance_id and attempt.get('status') not in ('recovered_intact','repaired'):
            raise ValueError('Cannon projectile must be actually recovered before reloading')
    if entry[4]["loaded_ball_instance_id"] is not None:
        raise ValueError("Pokeball Cannon already contains a ball")
    import turn as TURN
    if not TURN.spend(engine, trainer, "shift", "몬스터볼 캐논 장전"):
        return {"loaded": False, "reason": "no_shift_action"}
    entry[4]["loaded_ball_instance_id"] = ball_instance_id
    entry[4]["history"].append({"event": "loaded", "at": engine.elapsed_seconds, "ball_instance_id": ball_instance_id})
    _sync(entry)
    return {"loaded": True, "ball_instance_id": ball_instance_id}


def cannon_profile(engine, trainer, cannon_instance_id, *, projectile):
    if projectile not in ("ball", "sludge_bomb"):
        raise ValueError("Pokeball Cannon supports a ball or Sludge Bomb projectile")
    matches = [entry for entry in _active(engine, trainer, "pokeball_cannon") if entry[2]["instance_id"] == cannon_instance_id]
    if len(matches) != 1:
        raise ValueError("one actual equipped Pokeball Cannon is required")
    entry = matches[0]
    if projectile == "ball" and entry[4]["loaded_ball_instance_id"] is None:
        raise ValueError("Pokeball Cannon has no loaded physical ball")
    if projectile == "ball":
        ball = _objects(engine).get(entry[4]['loaded_ball_instance_id'], {})
        _object(engine,trainer,entry[4]['loaded_ball_instance_id'],ball.get('item_rule_id'))
    result = {"quality": "good", "weapon_class": "ranged", "accuracy_bonus": 1, "range_m": 15,
              "fixed_damage": "2d6" if projectile == "ball" else None,
              "ball_instance_id": entry[4].get("loaded_ball_instance_id")}
    return result


def fire_cannon(engine, trainer, cannon_instance_id, *, ball_instance_id):
    profile = cannon_profile(engine, trainer, cannon_instance_id, projectile="ball")
    if profile["ball_instance_id"] != ball_instance_id:
        raise ValueError("Cannon's actual loaded projectile changed")
    entry = next(row for row in _active(engine, trainer, "pokeball_cannon")
                 if row[2]["instance_id"] == cannon_instance_id)
    ball = _object(engine, trainer, ball_instance_id, _objects(engine)[ball_instance_id]["item_rule_id"])
    entry[4]["loaded_ball_instance_id"] = None
    entry[4]["history"].append({"event": "fired", "at": engine.elapsed_seconds,
                               "ball_instance_id": ball_instance_id})
    _sync(entry)
    # A thrown ball remains an actual recoverable projectile, rather than an
    # inventory counter or a consumed object whose miss could not be recovered.
    ball.pop("carrier_id", None)
    import world_entities as WORLD
    WORLD._set_object_location(ball, {"kind": "grid", "cell": list(trainer.pos)})
    return profile


def cannon_attempt_ball(engine, actor, attempt):
    """Resolve the same physical projectile for the existing capture recovery owner."""
    if attempt.get('physical_instance_id') is not None:
        import missed_ball_body as BALL_BODY
        return BALL_BODY.attempt_ball(engine,actor,attempt)
    source=attempt.get('cannon')
    if source is None:return None
    uid=source.get('ball_instance_id');obj=_objects(engine).get(uid)
    if (not isinstance(obj,dict) or obj.get('kind')!='item_instance'
            or obj.get('item_rule_id')!=attempt.get('item') or obj.get('owner_id')!=actor.entity_id):
        raise ValueError('actual fired Cannon ball identity required')
    import world_entities as WORLD
    WORLD.require_present_object(obj)
    return obj


def recover_cannon_ball(engine,actor,attempt):
    if attempt.get('physical_instance_id') is not None:
        import missed_ball_body as BALL_BODY
        return BALL_BODY.recover(engine,actor,attempt)
    obj=cannon_attempt_ball(engine,actor,attempt)
    if obj is None:return False
    obj.pop('disabled',None)
    import world_entities as WORLD
    WORLD._set_object_location(obj,{'kind':'grid','cell':list(actor.pos)})
    return True


def activate_booster(engine, actor, environment):
    allowed = {"비", "쾌청", "모래바람", "싸라기눈", "전기지형", "그래스필드", "미스트필드", "사이코필드"}
    if environment not in allowed:
        raise ValueError("Booster Energy needs one supported weather or terrain")
    matches = _active(engine, actor, "booster_energy")
    if len(matches) != 1:
        raise ValueError("one actual equipped Booster Energy is required")
    key = _scene_key(engine, actor)
    state = actor.spec.setdefault(ACTOR_STATE, {})
    uses = state.setdefault("booster_scene_uses", [])
    if key in uses:
        raise ValueError("Booster Energy scene activation is spent")
    uses.append(key)
    state["booster_environment"] = {"value": environment, "instance_id": matches[0][2]["instance_id"],
                                    "started_at": engine.elapsed_seconds, "ends": "faint_or_switch"}
    return deepcopy(state["booster_environment"])


def effective_environment(engine, actor, actual, *, include_virtual=True):
    weather_names = {"비": "rain", "쾌청": "sunny", "모래바람": "sandstorm", "싸라기눈": "hail"}
    actual = weather_names.get(actual, actual)
    local = actor.spec.get(ACTOR_STATE, {}).get("booster_environment") if include_virtual else None
    value = local["value"] if isinstance(local, dict) and local.get("value") in weather_names else actual
    value = weather_names.get(value, value)
    return None if value in ('rain','sunny') and _active(engine, actor, 'utility_umbrella') else value


def effective_terrain(engine, actor):
    local = actor.spec.get(ACTOR_STATE, {}).get("booster_environment")
    names = {"전기지형": "일렉트릭", "그래스필드": "그래스", "미스트필드": "미스트", "사이코필드": "사이코"}
    return names.get(local.get("value")) if isinstance(local, dict) else None


def dynamax_authorized(engine, actor):
    return len(_active(engine, actor, "dynamax_band")) == 1


def ground_immunity(engine, actor, move):
    return bool(move.get("type") == "땅" and _active(engine, actor, "air_balloon"))


def loaded_dice_hits(engine, actor, *, fixed=None, optional=False):
    active = _active(engine, actor, "loaded_dice")
    if not active and optional:
        return None
    if len(active) != 1:
        raise ValueError("one actual held Loaded Dice is required")
    if fixed is None:
        rolls = POOLS.pool(engine.rng, 2, sides=8)["faces"]
    else:
        if not isinstance(fixed, (list, tuple)) or len(fixed) != 2 or any(type(v) is not int or v < 1 or v > 8 for v in fixed):
            raise ValueError("Loaded Dice fixed evidence requires two d8 faces")
        rolls = list(fixed)
    def hits(face):
        return 1 if face == 1 else 2 if face <= 3 else 3 if face <= 6 else 4 if face == 7 else 5
    return {"rolls": rolls, "hits": max(map(hits, rolls)),
            "item_id": "item/속임수주사위", "instance_id": active[0][2]["instance_id"]}


def _actual_hit(move, receipt):
    return (isinstance(receipt, dict)
            and receipt.get("observation_boundary") == "native_attack_application_including_its_hooks"
            and receipt.get("source") == move.get("id") and move.get("class") in ("물리", "특수"))


def after_attack_damage(engine, attacker, target, move, receipt, *, type_multiplier=None):
    if not _actual_hit(move, receipt):
        return None
    balloon = _active(engine, target, "air_balloon")
    if balloon:
        _finish_instance(engine, target, balloon[0], "destroyed", "item/풍선:attack-hit")
    multiplier = type_multiplier if type_multiplier is not None else receipt.get("type_multiplier")
    if multiplier is None:
        multiplier = engine.type_multiplier(move.get("type"), target)[0]
    if multiplier > 1:
        _issue_pending(engine, target, "weakness_policy", attacker=attacker, move=move)
    _issue_pending(engine, target, "eject_button", attacker=attacker, move=move)
    red = _active(engine, target, "red_card")
    if red and _scene_available(engine, red[0]):
        pending = _issue_pending(engine, target, "red_card", attacker=attacker, move=move, automatic=True)
        if pending:
            _spend_scene(engine, red[0], "triggered", attacker.entity_id)
            _finish_instance(engine, target, red[0], "consumed", "item/레드카드:attack-hit")
            if attacker.kind == "pokemon" and attacker.on_field:
                _resolve_pending(engine, target, "red_card")
    return True


def after_stage_change(engine, actor, stat, before, after):
    if stat not in ("atk", "def", "spa", "spd", "spe") or type(before) is not int or type(after) is not int:
        raise ValueError("actual combat-stage observation required")
    if after < before:
        return _issue_pending(engine, actor, "eject_pack", stage={"stat": stat, "before": before, "after": after})
    return None


def _scene_available(engine, entry):
    actor = _actor_for(engine, entry[3]["equipped_by"])
    return not any(row["scene"] == _scene_key(engine, actor)
                   for row in entry[4].get("scene_uses", []))


def _actor_for(engine, uid):
    for actor in engine.time_actors():
        if actor.entity_id == uid:
            return actor
    raise ValueError("equipment holder actor is missing")


def _spend_scene(engine, entry, event, target_id=None):
    actor = _actor_for(engine, entry[3]["equipped_by"])
    key = _scene_key(engine, actor)
    if any(row["scene"] == key for row in entry[4].get("scene_uses", [])):
        raise ValueError("remaining CSV held-item scene use is spent")
    entry[4].setdefault("scene_uses", []).append({"scene": key, "event": event, "at": engine.elapsed_seconds,
                                                  "target_id": target_id})
    _sync(entry)


def _issue_pending(engine, actor, kind, **event):
    matches = _active(engine, actor, kind)
    if not matches or not _scene_available(engine, matches[0]):
        return None
    pending = actor.spec.setdefault(PENDING, {})
    if kind in pending:
        return deepcopy(pending[kind])
    row = {"kind": kind, "instance_id": matches[0][2]["instance_id"], "at": engine.elapsed_seconds,
           "scene": _scene_key(engine, actor), "event": _json_event(event), "automatic": bool(event.get("automatic"))}
    pending[kind] = row
    return deepcopy(row)


def _json_event(event):
    result = {}
    for key, value in event.items():
        if key == "attacker": result["attacker_id"] = value.entity_id
        elif key == "move": result["move_id"] = value.get("id")
        elif key != "automatic": result[key] = deepcopy(value)
    return result


def resolve_pending(engine, actor, kind, *, accept=True, send=None):
    import state_grants as GRANTS
    participants = tuple(x for x in (send,) if x is not None and x is not actor)
    return GRANTS.transition(
        engine, actor,
        lambda staged_engine, staged_actor, *staged_send: _resolve_pending(
            staged_engine, staged_actor, kind, accept=accept,
            send=staged_send[0] if staged_send else None),
        participants=participants,
    )


def _resolve_pending(engine, actor, kind, *, accept=True, send=None):
    row = actor.spec.get(PENDING, {}).get(kind)
    if not isinstance(row, dict) or row.get("scene") != _scene_key(engine, actor):
        raise ValueError("actual live remaining-item reaction is required")
    if kind == "red_card" and accept is not True:
        raise ValueError("Red Card reaction is automatic")
    if type(accept) is not bool:
        raise ValueError("optional held-item Free action must be accepted or declined")
    matches = _active(engine, actor, kind)
    if kind != "red_card" and len(matches) != 1:
        raise ValueError("reaction's actual held item changed")
    actor.spec[PENDING].pop(kind)
    if not accept:
        return {"accepted": False, "kind": kind}
    if kind == "weakness_policy":
        _spend_scene(engine, matches[0], "accepted")
        actor.spec.setdefault(ACTOR_STATE, {})["weakness_policy_damage"] = {
            "amount": 10, "encounter": _encounter_key(engine, actor), "instance_id": row["instance_id"]}
        return {"accepted": True, "damage_bonus": 10}
    if kind in ("eject_button", "eject_pack"):
        _spend_scene(engine, matches[0], "accepted")
        _finish_instance(engine, actor, matches[0], "consumed", "item/" + kind + ":free-switch")
        _immediate_switch(engine, actor, send)
        return {"accepted": True, "switched": True, "sent_id": getattr(send, "entity_id", None)}
    if kind == "red_card":
        attacker_id = row["event"]["attacker_id"]
        attacker = _actor_for(engine, attacker_id)
        reserves = _reserves(engine, attacker)
        if send is not None:
            raise ValueError("Red Card replacement is selected randomly from the actual controller's reserves")
        if reserves:
            send = engine.rng.choice(reserves)
            _immediate_switch(engine, attacker, send)
        return {"accepted": True, "forced": True, "attacker_id": attacker_id,
                "sent_id": getattr(send, "entity_id", None)}
    raise ValueError("unknown remaining-item reaction")


def _immediate_switch(engine, outgoing, incoming):
    if outgoing.kind != "pokemon" or not outgoing.on_field:
        raise ValueError("switch reaction requires the actual on-field Pokemon")
    if incoming is None:
        raise ValueError("switch replacement Pokemon is required")
    if incoming is not None and (incoming.kind != "pokemon" or incoming.on_field or incoming.fainted or incoming.dead):
        raise ValueError("switch replacement must be a conscious actual off-field Pokemon")
    if incoming is not None and incoming not in _reserves(engine, outgoing):
        raise ValueError("switch replacement must belong to the actual same controller")
    import combat_state_lifecycle as COMBAT
    COMBAT.recall(engine, outgoing)
    if incoming is not None:
        COMBAT.join(engine, [incoming])
        incoming.on_field = True
        incoming.pos = outgoing.pos


def _reserves(engine, outgoing):
    import world_entities as WORLD
    actors = WORLD.actor_index(engine)
    owner = outgoing.spec.get("trainer_id")
    if owner is None or owner not in actors or actors[owner].kind != "trainer":
        return []
    return [actor for actor in actors.values() if actor.kind == "pokemon" and actor is not outgoing
            and actor.spec.get("trainer_id") == owner and not actor.on_field
            and not actor.fainted and not actor.dead]


def damage_roll_bonus(engine, actor, move):
    state = actor.spec.get(ACTOR_STATE, {}).get("weakness_policy_damage")
    return 10 if isinstance(state, dict) and state.get("encounter") == _encounter_key(engine, actor) and move.get("class") in ("물리", "특수") else 0


def _finish_instance(engine, actor, entry, outcome, source):
    key, _, registration, obj, state = entry
    state["history"].append({"event": outcome, "at": engine.elapsed_seconds, "source": source})
    if outcome == "consumed":
        import item_stock as STOCK
        stock = STOCK.prepare(engine, actor, obj["item_rule_id"], held_selection=obj["id"])
        payment = STOCK.debit(engine, actor, stock)
        obj["consumed"]["trigger"] = source
        import consumption_execution as EXECUTION
        EXECUTION.finish(actor, payment, target_id=actor.entity_id, outcome="applied",
                         results=[{"kind": "physical_consumption", "id": obj["id"]}])
        return
    import items as ITEMS
    ITEMS.unregister_item(engine, actor, registration_key=key)
    import world_entities as WORLD
    WORLD.finish_physical_use(engine, obj, outcome,
                              {"source": source, "former_holder_id": actor.entity_id})


def retain_encounter_condition(actor, condition):
    return condition == "난동" and bool(actor.spec.get(ACTOR_STATE, {}).get("assault_vest_rampage", {}).get("active"))


def before_cure_status(engine, actor, condition):
    if retain_encounter_condition(actor, condition):
        raise ValueError("Assault Vest Rampage cannot be cured before encounter end")


def switched_or_fainted(actor):
    actor.spec.get(ACTOR_STATE, {}).pop("booster_environment", None)


def end_encounter(actor, *, engine=None):
    state = actor.spec.get(ACTOR_STATE, {})
    lock = state.get("assault_vest_rampage")
    if isinstance(lock, dict):
        lock["active"] = False
        if engine is None:  # legacy direct compatibility; native boundary cures the instance
            actor.conditions.discard("난동")
        else:
            engine.cure_status(actor,"난동")
    state.pop("weakness_policy_damage", None)
    actor.spec.pop(PENDING, None)


def _validate_object_state(engine, obj, *, row=None):
    state = obj.get(OBJECT_STATE)
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("remaining CSV physical item state schema changed")
    row = row or definition(engine.r, obj.get("item_rule_id"))
    if row is None or state.get("clause_id") != row["clause_id"] or state.get("item_id") != row["item_id"] or state.get("kind") != row["kind"]:
        raise ValueError("remaining CSV physical item identity changed")
    C.integer(state.get("created_at"), "remaining CSV item creation clock", 0, engine.elapsed_seconds)
    if not isinstance(state.get("history"), list):
        raise ValueError("remaining CSV item history must be a list")
    if state["kind"] == "type_study_manual" and (state.get("chosen_type") is not None and state["chosen_type"] not in __import__("items").TYPES or state.get("study_rank") not in (0, 1, 2)):
        raise ValueError("Type Study Manual state is invalid")
    if state["kind"] in REACTIONS and not isinstance(state.get("scene_uses"), list):
        raise ValueError("remaining CSV reaction receipts must be a list")
    return True


def validate_actor(actor):
    pending = actor.spec.get(PENDING, {})
    if not isinstance(pending, dict) or any(k not in REACTIONS or not isinstance(v, dict) or v.get("kind") != k for k, v in pending.items()):
        raise ValueError("remaining CSV pending reaction state is invalid")
    state = actor.spec.get(ACTOR_STATE, {})
    if not isinstance(state, dict):
        raise ValueError("remaining CSV actor state must be a mapping")
    return True


def upgrade_legacy_cannon(engine, index):
    """Restore the ordinary weapon ledger for pre-repair, genuinely equipped Cannon saves."""
    import optional_weapon_framework as FRAMEWORK
    import turn as TURN
    for actor in index.values():
        for registration in getattr(actor, "_item_reg", {}).values():
            if registration.get("item_id") != "item/몬스터볼-캐논" or "cannon_weapon_key" in registration:
                continue
            uid = registration.get("instance_id")
            obj = _objects(engine).get(uid)
            if (actor.kind != "trainer" or registration.get("slots") != ["주요손", "반대손"]
                    or not isinstance(obj, dict) or obj.get("kind") != "item_instance"
                    or obj.get("item_rule_id") != registration["item_id"]
                    or obj.get("equipped_by") != actor.entity_id
                    or registration.get("state_source") not in actor.spec.get("state_grants", {}).get("sources", {})
                    or any(entry.get("item_id") == registration["item_id"]
                           and entry.get("instance_id") == uid
                           for entry in actor.custom_conditions.get("equipped_weapons", {}).values())):
                raise ValueError("legacy Pokeball Cannon needs its original equipped item and live source")
            row = definition(engine.r, registration["item_id"])
            _state(engine, actor, row, obj)
            weapon = FRAMEWORK.crafted_weapon(engine, {"instance_id": uid}, {
                "name": engine.r.items_mech[registration["item_id"]]["name"],
                "kind": "장거리 사격무기", "grade": "좋음", "moves": []})
            slots = registration.pop("slots")
            try:
                key = TURN.equip_weapon(engine, actor, weapon)
            finally:
                registration["slots"] = slots
            actor.custom_conditions["equipped_weapons"][key].update(
                item_id=registration["item_id"], instance_id=uid)
            registration["cannon_weapon_key"] = key
    return True


def validate_world(engine, index):
    POLICY.policy(engine.r)
    for obj in _objects(engine).values():
        if OBJECT_STATE in obj:
            _validate_object_state(engine, obj)
    for actor in index.values():
        validate_actor(actor)
        for registration in getattr(actor, "_item_reg", {}).values():
            row = definition(engine.r, registration.get("item_id"))
            if row is None:
                continue
            obj = _objects(engine).get(registration.get("instance_id"))
            if not isinstance(obj, dict) or obj.get("equipped_by") != actor.entity_id:
                raise ValueError("remaining CSV registration lacks its physical holder")
            state = _state(engine, actor, row, obj)
            if registration.get("csv_item_projection") != _projection(registration, state):
                raise ValueError("restored remaining CSV projection differs from physical state")
            if row["kind"] == "pokeball_cannon":
                key = registration.get("cannon_weapon_key")
                weapon = actor.custom_conditions.get("equipped_weapons", {}).get(key)
                if (not isinstance(weapon, dict) or weapon.get("item_id") != row["item_id"]
                        or weapon.get("instance_id") != registration["instance_id"]):
                    raise ValueError("Pokeball Cannon physical weapon permission changed")
    return True

