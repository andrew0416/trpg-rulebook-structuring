"""Reviewed Move clauses whose declarations need native lifecycle consumers.

The JSON policy admits an exact source row and an exact declarative payload.
This module owns execution, durable provenance, and boundary cleanup.  It does
not infer new Moves from similar-looking declarations.
"""
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import json

import common_checks as C


KEY = "declarative_move_contracts"
POLICY = "data/declarative-move-contract-policy.json"
VERSION = 1
NATIVE = "native_lifecycle"


import resolution_transaction as _FINGERPRINTS

def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be nonempty text")
    return value.strip()


def _same(left, right):
    return json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _semantic(effect):
    return {key: deepcopy(value) for key, value in effect.items() if not key.startswith("_")}


def _policy_path(rules):
    staged = Path(__file__).resolve().parents[1] / POLICY
    return staged if staged.exists() else Path(rules.root) / POLICY


def policy(rules):
    cached = getattr(rules, "_declarative_move_contract_policy", None)
    if cached is not None:
        return cached
    data = json.loads(_policy_path(rules).read_text(encoding="utf-8"))
    if data.get("schema_version") != VERSION or data.get("contract") != "declarative_move_native_lifecycle":
        raise ValueError("declarative Move policy identity changed")
    for relative, digest in data.get("source_files", {}).items():
        path = Path(rules.root) / relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("declarative Move source anchor changed: " + relative)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            records = list(csv.reader(stream))
        for source, row in data.get("moves", {}).items():
            number = row.get("record")
            if type(number) is not int or number < 1 or number > len(records):
                raise ValueError("declarative Move source record is invalid: " + source)
            actual = _FINGERPRINTS.json_fingerprint(records[number - 1], sort_keys=False, compact=True, allow_nan=True)
            if actual != row.get("source_row_sha256"):
                raise ValueError("declarative Move source row changed: " + source)
    expected_operations = {
        "statuses_until_switch", "delayed_status", "next_normal_attack_type",
        "encounter_weight_and_stage", "last_resort_gate", "focus_until_switch",
        "rest_sleep", "scene_stat_choice", "explicit_scene_alternate_type",
        "scene_type_replacement",
    }
    operations = {row.get("operation") for row in data.get("moves", {}).values()}
    if operations != expected_operations or len(data.get("moves", {})) != 11:
        raise ValueError("declarative Move policy boundary changed")
    rules._declarative_move_contract_policy = data
    return data


def definition(rules, source):
    row = policy(rules)["moves"].get(source)
    if row is not None and (source=='move/3연화살' or row.get('after_all')):
        frequency=row.get('frequency')
        if (source!='move/3연화살' or row.get('after_all') is not True or
                row.get('operation')!='focus_until_switch' or row.get('executor')!=NATIVE or
                frequency!={'kind':'daily','uses':1} or type(frequency.get('uses')) is not int):
            raise ValueError('reviewed after-all daily-once focus policy required')
    if row is not None and rules._selected_rule(source) != source:
        raise ValueError("selected declarative Move source changed")
    return row


def _declared(mm):
    effects = []
    if isinstance(mm.get("apply_status"), str):
        effects.append({"type": "apply_status", "status": mm["apply_status"], "target": "target"})
    effects.extend(_semantic(effect) for effect in mm.get("effects_exec", []))
    if mm.get("never_miss") is True:
        effects.append({"type": "never_miss"})
    return effects


def marker(source, row):
    result = {
        "type": "declarative_move_contract",
        "source": source,
        "operation": row["operation"],
        "clause_id": row["clause_id"],
        "source_row_sha256": row["source_row_sha256"],
    }
    if row.get('after_all'):result.update(target='self')
    return result


def after_all(rules,effect):
    if effect.get('type')!='declarative_move_contract':return False
    row=definition(rules,effect.get('source'))
    return bool(row and row.get('after_all') and effect==marker(effect['source'],row))


def prepare_mechanics(rules, source, mechanics):
    """Replace only exact reviewed native-lifecycle declarations."""
    row = definition(rules, source)
    if row is None:
        return mechanics
    if not _same(_declared(mechanics), row["expected_effects"]):
        raise ValueError("declarative Move mechanics changed from reviewed source: " + source)
    if row["executor"] != NATIVE:
        return mechanics
    result = deepcopy(mechanics)
    if row.get("after_all"):
        result["effects_exec"] = [effect for effect in result.get("effects_exec", [])
                                  if effect.get("type") not in ("custom_condition", "rule")]
        result["effects_exec"].append(marker(source,row))
        return result
    result.pop("apply_status", None)
    result.pop("effects_exec", None)
    if source != "move/하품":
        result.pop("never_miss", None)
    result["effects_exec"] = [marker(source, row)]
    return result


def _empty():
    return {"version": VERSION, "sequence": 0, "live": [], "history": [], "uses": [], "choices": []}


def state(actor, create=False):
    value = actor.spec.get(KEY)
    if value is None and create:
        value = _empty()
        actor.spec[KEY] = value
    return value


def live(actor, operation=None):
    value = state(actor)
    rows = [] if value is None else value["live"]
    return [row for row in rows if operation is None or row["operation"] == operation]


def history(actor):
    value = state(actor)
    return [] if value is None else value["history"]


def _scene(actor):
    import frequency as FREQ
    return FREQ.state(actor)["scene"]


def _turn(actor):
    return C.integer(actor.custom_conditions.get("combat_turn_serial", 0), "actual owner turn serial", 0)


def _new_record(engine, issuer, holder, source, context, lifetime, payload, *, active=True):
    row = definition(engine.r, source)
    if row is None or row["executor"] != NATIVE:
        raise ValueError("exact native declarative Move source required")
    value = state(holder, True)
    value["sequence"] += 1
    record = {
        "id": "declarative:%s:%d" % (holder.entity_id, value["sequence"]),
        "operation": row["operation"], "source": source,
        "clause_id": row["clause_id"], "source_row_sha256": row["source_row_sha256"],
        "issuer_id": issuer.entity_id, "holder_id": holder.entity_id,
        "issued_at": engine.elapsed_seconds, "receipt": context["effect_receipt"],
        "occurrence": context["effect_occurrence"], "lifetime": deepcopy(lifetime),
        "payload": deepcopy(payload), "end": None,
    }
    value["live" if active else "history"].append(record)
    if not active:
        record["end"] = {"kind": "applied", "at": engine.elapsed_seconds}
    return record


def _archive(engine, holder, record, kind, **facts):
    value = state(holder)
    if value is None or record not in value["live"]:
        return False
    value["live"].remove(record)
    record["end"] = {"kind": kind, "at": engine.elapsed_seconds, **deepcopy(facts)}
    value["history"].append(record)
    return True


def _choice(actor, source, target=None):
    value = state(actor)
    if value is None:
        return None
    target_id = None if target is None else target.entity_id
    return next((row for row in value["choices"] if row["source"] == source and row["scene"] == _scene(actor)
                 and row["status"] == "pending" and (target is None or row["target_id"] == target_id)), None)


def choose(engine, actor, target, source, *, stat=None, own_type=None, target_type=None, reason):
    """Record only a source-required player choice; activation still pays and rolls normally."""
    import state_grants as GRANTS
    import world_entities as WORLD
    WORLD.require_actors(engine, actor, target)
    source = engine.r.move_id(source)
    row = definition(engine.r, source)
    if row is None or row["operation"] not in ("scene_stat_choice", "scene_type_replacement"):
        raise ValueError("Move has no reviewed declarative choice")
    if source not in [engine.r.move_id(mid) for mid in actor.moves]:
        raise ValueError("actor must currently know the selected Move")
    reason = _text(reason, "declarative Move choice reason")

    def apply(staged, user, chosen_target):
        current = state(user, True)
        scene = _scene(user)
        if any(item["source"] == source and item["scene"] == scene and item["status"] == "pending"
               for item in current["choices"]):
            raise ValueError("one pending choice already exists for this Move")
        if row["operation"] == "scene_stat_choice":
            if stat not in ("atk", "spa") or own_type is not None or target_type is not None:
                raise ValueError("Spicy Extract requires exactly atk or spa")
            if chosen_target is not user and (user.side is None or chosen_target.side != user.side):
                raise ValueError("Spicy Extract target must be self or an actual ally")
            if staged.grid is not None:
                from grid import cheb
                if cheb(user.pos, chosen_target.pos) > 4:
                    raise ValueError("Spicy Extract ally is outside range 4")
            if any(item["source"] == source and item["scene"] == scene and item["payload"].get("stat") == stat
                   and item["status"] in ("pending", "used") for item in current["choices"]):
                raise ValueError("the same Spicy Extract stat choice cannot be used twice in one scene")
            payload = {"stat": stat}
        else:
            if stat is not None or own_type not in user.types or target_type not in chosen_target.types:
                raise ValueError("Reflect Type requires one current user type and one current target type")
            import homebrew_state as HOME
            if HOME.type_change_blocked(user):
                raise ValueError("current type-change state blocks Reflect Type")
            payload = {"own_type": own_type, "target_type": target_type}
        current["sequence"] += 1
        choice = {
            "id": "declarative-choice:%s:%d" % (user.entity_id, current["sequence"]),
            "source": source, "operation": row["operation"], "clause_id": row["clause_id"],
            "source_row_sha256": row["source_row_sha256"], "actor_id": user.entity_id,
            "target_id": chosen_target.entity_id, "scene": scene, "selected_at": staged.elapsed_seconds,
            "payload": payload, "reason": reason, "status": "pending", "consumed_record_id": None,
        }
        current["choices"].append(choice)
        staged.log("    %s: %s 선택 기록" % (user.name, row["name"]), source)
        return deepcopy(choice)

    if actor is target:
        return GRANTS.transition(engine, actor, lambda staged, user: apply(staged, user, user), include_rulings=True)
    return GRANTS.transition(engine, actor, apply, participants=(target,), include_rulings=True)


def _check_marker(engine, source, effect):
    row = definition(engine.r, source)
    if row is None or row["executor"] != NATIVE or effect != marker(source, row):
        raise ValueError("declarative Move marker differs from reviewed policy")
    return row


def _normal_attack(engine, actor, move):
    if move.get('class') not in ('물리', '특수'):
        return False
    import effects_ext as EXT
    registered = EXT.revelation_dance_type(engine, actor, move)
    return (registered if registered is not None else move.get('type')) == '노말'


def _plasma_conflict(engine, actor, source):
    move = engine.r.move(source)
    if not _normal_attack(engine, actor, move):
        return False
    if actor.type_override_next is not None:
        return True
    if any(effect.get("type") == "type_override_moves" for effect in actor.registry):
        return True
    if any(rule.get("rule", {}).get("normal_moves_become") for rule in engine.zone_rules):
        return True
    return False


def preflight(engine, actor, target, effects, source):
    """All deterministic gates run before cost, frequency, or accuracy RNG."""
    row = definition(engine.r, source)
    markers = [effect for effect in effects if effect.get("type") == "declarative_move_contract"]
    if markers:
        if len(markers) != 1 or row is None or row["executor"] != NATIVE:
            raise ValueError("one exact native declarative Move marker required")
        _check_marker(engine, source, markers[0])
        operation = row["operation"]
        if operation == "last_resort_gate":
            if not engine.encounter_active:
                raise ValueError("Last Resort requires an active encounter")
            # Struggle is an intrinsic fallback in Combatant.moves, not one of
            # the six learned Move slots named by Last Resort.
            known = [mid for mid in dict.fromkeys(engine.r.move_id(mid) for mid in actor.moves) if mid != "struggle"]
            others = [mid for mid in known if mid != source]
            if len(known) != 6 or len(others) != 5:
                raise ValueError("Last Resort requires exactly five other currently known Moves")
            used = {item["move_id"] for item in (state(actor) or _empty())["uses"]}
            missing = [mid for mid in others if mid not in used]
            if missing:
                raise ValueError("Last Resort other Moves not yet used without switching: " + ", ".join(missing))
        elif operation == "rest_sleep":
            reason = engine.immune_to(actor, "잠듦", cause=source)
            if reason:
                raise ValueError("Rest cannot produce its required Sleep: " + str(reason))
        elif operation in ("scene_stat_choice", "scene_type_replacement"):
            if _choice(actor, source, target) is None:
                raise ValueError("this Move requires its explicit pending source choice")
        elif operation == "encounter_weight_and_stage" and type(actor.weight_class) is not int:
            raise ValueError("Autotomize requires a known current weight class")
    # A pending Plasma Fists contract is consumed by the next actual activation.
    if live(actor, "next_normal_attack_type") and _plasma_conflict(engine, actor, source):
        raise ValueError("pending Plasma Fists conflicts with another type override")
    return True


def _statuses_until_switch(engine, actor, target, source, context):
    statuses = {}
    for condition in ("저주", "취약"):
        present = condition in target.conditions
        applied = engine.apply_status(target, condition, source=source, applied_by=actor)
        statuses[condition] = bool(applied and not present)
    return _new_record(engine, actor, target, source, context, {"boundary": "switch_or_encounter_end"},
                       {"owned_statuses": statuses})


def _delayed_status(engine, actor, target, source, context):
    return _new_record(engine, actor, target, source, context,
                       {"boundary": "target_next_turn_end", "turn": _turn(target) + 1},
                       {"status": "잠듦", "due_turn": _turn(target) + 1})


def _next_normal_attack(engine, actor, target, source, context):
    return _new_record(engine, actor, target, source, context,
                       {"boundary": "next_normal_attack_activation_or_encounter_end"},
                       {"as_type": "전기", "consumed_by": None})


def _autotomize(engine, actor, target, source, context):
    import state_grants as GRANTS
    before = actor.weight_class
    record = _new_record(engine, actor, actor, source, context, {"boundary": "encounter_end"}, {})
    grant = "declarative-grant:" + record["id"]
    GRANTS._source(actor, grant, "effect", owner_id=actor.entity_id, lifetime="encounter_end", rule_id=source)
    GRANTS.weight(actor, -1, grant, mode="add", minimum=1)
    lowered = actor.weight_class < before
    if lowered:
        engine.change_stage(actor, "spe", 2)
    record["payload"] = {"grant_source": grant, "before_weight": before,
                         "after_weight": actor.weight_class, "speed_raised": lowered}
    return record


def _last_resort(engine, actor, target, source, context):
    return _new_record(engine, actor, actor, source, context, {"boundary": "activation"},
                       {"used_move_ids": sorted({item["move_id"] for item in state(actor)["uses"]})}, active=False)


def _focus(engine, actor, target, source, context):
    row=definition(engine.r,source)
    if row.get("after_all"):
        import move_completion as COMPLETE, frequency as FREQ
        if not context.get("after_all_targets") or not COMPLETE.authorized(engine,context):
            raise ValueError("Pumped requires its whole completed native Move")
        if not FREQ.activation_allowed(actor,source+"/pumped",row["frequency"],engine=engine):return None
        FREQ.consume_activation(actor,source+"/pumped",row["frequency"],engine=engine)
    existing = live(actor, "focus_until_switch")
    if existing:
        return existing[0]
    return _new_record(engine, actor, actor, source, context, {"boundary": "switch_or_encounter_end"},
                       {"critical_delta": 2, "fallback_min": 18})


def _rest(engine, actor, target, source, context):
    import status_sets as STATUS_SETS
    STATUS_SETS.cure_group(engine, actor)
    engine.heal(actor, actor.max_hp, source_kind="move")
    if not engine.apply_status(actor, "잠듦", source=source, applied_by=actor):
        raise ValueError("Rest failed to install its required Sleep after preflight")
    due = _turn(actor) + 2
    return _new_record(engine, actor, actor, source, context,
                       {"boundary": "owner_second_turn_end", "turn": due},
                       {"status": "잠듦", "due_turn": due, "blocks_start_save": True})


def _spicy(engine, actor, target, source, context):
    choice = _choice(actor, source, target)
    if choice is None:
        raise ValueError("Spicy Extract pending choice disappeared before dispatch")
    before = target.stages[choice["payload"]["stat"]]
    engine.change_stage(target, choice["payload"]["stat"], 3)
    record = _new_record(engine, actor, target, source, context, {"boundary": "ordinary_combat_stage_reset"},
                         {"stat": choice["payload"]["stat"], "before": before,
                          "after": target.stages[choice["payload"]["stat"]], "choice_id": choice["id"]}, active=False)
    choice["status"] = "used"
    choice["consumed_record_id"] = record["id"]
    return record


def _reflect_type(engine, actor, target, source, context):
    import state_grants as GRANTS
    choice = _choice(actor, source, target)
    if choice is None:
        raise ValueError("Reflect Type pending choice disappeared before dispatch")
    own_type = choice["payload"]["own_type"]
    target_type = choice["payload"]["target_type"]
    if own_type not in actor.types or target_type not in target.types:
        raise ValueError("Reflect Type selected types changed before the hit")
    new_types = list(dict.fromkeys(target_type if value == own_type else value for value in actor.types))
    record = _new_record(engine, actor, actor, source, context, {"boundary": "scene_end"}, {})
    grant = "declarative-grant:" + record["id"]
    GRANTS._source(actor, grant, "effect", owner_id=actor.entity_id, lifetime="scene_end", rule_id=source)
    if GRANTS.type_operation(actor, "set", new_types, grant) is False:
        raise ValueError("Reflect Type was blocked after its preflight")
    record["payload"] = {"grant_source": grant, "own_type": own_type, "target_type": target_type,
                         "projected_types": new_types, "choice_id": choice["id"]}
    choice["status"] = "used"
    choice["consumed_record_id"] = record["id"]
    return record


EXECUTORS = {
    "statuses_until_switch": _statuses_until_switch,
    "delayed_status": _delayed_status,
    "next_normal_attack_type": _next_normal_attack,
    "encounter_weight_and_stage": _autotomize,
    "last_resort_gate": _last_resort,
    "focus_until_switch": _focus,
    "rest_sleep": _rest,
    "scene_stat_choice": _spicy,
    "scene_type_replacement": _reflect_type,
}


def execute(engine, actor, target, effect, context):
    """Run one admitted producer as an all-or-nothing world transition."""
    import state_grants as GRANTS
    source = context.get("source_id")
    row = _check_marker(engine, source, effect)
    operation = row["operation"]
    executor = EXECUTORS.get(operation)
    if executor is None:
        raise ValueError("declarative Move operation has no native executor")

    def apply(staged, user, recipient):
        staged_context=GRANTS._stage_transition_payload(engine,staged,
            {key:value for key,value in context.items() if key!='engine'})
        staged_context['engine']=staged
        return executor(staged, user, recipient, source, staged_context)

    if actor is target:
        return GRANTS.transition(engine, actor, lambda staged, user: apply(staged, user, user), include_rulings=True)
    return GRANTS.transition(engine, actor, apply, participants=(target,), include_rulings=True)


def begin_move_use(engine, actor, target, move, mechanics, *, targetless=False):
    """Observe one authenticated activation for Last Resort and Plasma Fists."""
    scopes = getattr(engine, "_event_use_scopes", ())
    if not scopes or scopes[-1].get("actor") is not actor or scopes[-1].get("target") is not target \
            or scopes[-1].get("move_id") != move.get("id"):
        raise ValueError("declarative Move observation requires an actual native activation")
    current = scopes[-1]
    group = __import__("move_activation").current_scope(engine, actor, target, move["id"])
    cache = group.setdefault("declarative_move_contracts", {}) if group is not None else {}
    if "activation" in cache:
        current["declarative_move_type"] = cache["activation"].get("move_type")
        return current["declarative_move_type"]

    actual_type = None
    pending = list(live(actor, "next_normal_attack_type"))
    if pending and _normal_attack(engine, actor, move):
        if _plasma_conflict(engine, actor, move["id"]):
            raise ValueError("pending Plasma Fists conflicts with another type override")
        actual_type = "전기"
        for record in pending:
            record["payload"]["consumed_by"] = {"move_id": move["id"], "at": engine.elapsed_seconds,
                                                  "target_id": None if targetless else target.entity_id}
            _archive(engine, actor, record, "matching_move_activation", move_id=move["id"])
        current["declarative_move_type"] = actual_type
        engine.log("    플라스마피스트: 다음 노말타입 공격을 전기타입으로 대체", "move/플라스마피스트")

    known = [engine.r.move_id(mid) for mid in actor.moves]
    if engine.encounter_active and "move/비장의무기" in known:
        value = state(actor, True)
        value["uses"].append({"move_id": move["id"], "at": engine.elapsed_seconds, "turn": _turn(actor)})
    cache["activation"] = {"move_type": actual_type}
    return actual_type


def effective_type(engine, actor, target, move, *, preview=False):
    scopes = getattr(engine, "_event_use_scopes", ())
    if scopes:
        current = scopes[-1]
        if current.get("actor") is actor and current.get("target") is target and current.get("move_id") == move.get("id"):
            if "declarative_move_type" in current:
                return current["declarative_move_type"]
    if (preview and _normal_attack(engine, actor, move)
            and live(actor, "next_normal_attack_type")):
        if _plasma_conflict(engine, actor, move["id"]):
            raise ValueError("pending Plasma Fists conflicts with another type override")
        return "전기"
    return None


def critical_threshold(actor, current):
    if live(actor, "focus_until_switch"):
        return min(current - 2, 18)
    return current


def blocks_sleep_save(actor):
    return any(record["payload"].get("blocks_start_save") for record in live(actor, "rest_sleep"))


def end_turn(engine, actor):
    now = _turn(actor)
    for record in list(live(actor)):
        if record["operation"] == "delayed_status" and now >= record["payload"]["due_turn"]:
            applied = engine.apply_status(actor, record["payload"]["status"], source=record["source"])
            _archive(engine, actor, record, "target_turn_end", turn=now, applied=bool(applied))
        elif record["operation"] == "rest_sleep" and now >= record["payload"]["due_turn"]:
            _archive(engine, actor, record, "owner_second_turn_end", turn=now)
            engine.cure_status(actor, "잠듦")


def before_cure(engine, actor, condition):
    for record in list(live(actor)):
        if record["operation"] == "statuses_until_switch" and condition in record["payload"]["owned_statuses"]:
            record["payload"]["owned_statuses"][condition] = False
            if not any(record["payload"]["owned_statuses"].values()):
                _archive(engine, actor, record, "status_cure", status=condition)
        elif record["operation"] == "rest_sleep" and condition == "잠듦":
            _archive(engine, actor, record, "status_cure", status=condition)


def recall(engine, actor):
    for record in list(live(actor)):
        if record["operation"] not in ("statuses_until_switch", "focus_until_switch", "rest_sleep"):
            continue
        _archive(engine, actor, record, "switch")
        if record["operation"] == "statuses_until_switch":
            for condition, owned in record["payload"]["owned_statuses"].items():
                if owned and condition in actor.conditions:
                    engine.cure_status(actor, condition)
        elif record["operation"] == "rest_sleep" and "잠듦" in actor.conditions:
            engine.cure_status(actor, "잠듦")
    value = state(actor)
    if value is not None:
        value["uses"].clear()


def end_encounter(engine, actors):
    import state_grants as GRANTS
    for actor in actors:
        for record in list(live(actor)):
            if record["operation"] == "scene_type_replacement":
                continue
            _archive(engine, actor, record, "encounter_end")
            grant = record["payload"].get("grant_source")
            if grant:
                GRANTS.revoke(actor, grant, engine=engine)
            if record["operation"] == "statuses_until_switch":
                for condition, owned in record["payload"]["owned_statuses"].items():
                    if owned and condition in actor.conditions:
                        engine.cure_status(actor, condition)
            elif record["operation"] == "rest_sleep" and "잠듦" in actor.conditions:
                engine.cure_status(actor, "잠듦")
        value = state(actor)
        if value is not None:
            value["uses"].clear()


def end_scene(engine, actors):
    import state_grants as GRANTS
    for actor in actors:
        for record in list(live(actor, "scene_type_replacement")):
            grant = record["payload"]["grant_source"]
            GRANTS.revoke(actor, grant, engine=engine)
            _archive(engine, actor, record, "scene_end")
        value = state(actor)
        if value is not None:
            for choice in value["choices"]:
                if choice["status"] == "pending" and choice["scene"] == _scene(actor):
                    choice["status"] = "expired"


def _validate_record(engine, index, holder, record, terminal):
    required = {"id", "operation", "source", "clause_id", "source_row_sha256", "issuer_id", "holder_id",
                "issued_at", "receipt", "occurrence", "lifetime", "payload", "end"}
    if not isinstance(record, dict) or set(record) != required:
        raise ValueError("declarative Move record shape changed")
    row = definition(engine.r, record["source"])
    if row is None or row["executor"] != NATIVE or (record["operation"], record["clause_id"], record["source_row_sha256"]) != (
            row["operation"], row["clause_id"], row["source_row_sha256"]):
        raise ValueError("declarative Move record provenance changed")
    if record["holder_id"] != holder.entity_id or record["issuer_id"] not in index:
        raise ValueError("declarative Move actor reference changed")
    C.integer(record["issued_at"], "declarative Move issue time", 0, engine.elapsed_seconds)
    _text(record["id"], "declarative Move record identity")
    _text(record["occurrence"], "declarative Move occurrence")
    producer = getattr(engine, "_effect_dispatch_receipts", {}).get(record["receipt"])
    if not producer or producer.get("source_id") != record["source"] or producer.get("occurrence") != record["occurrence"] \
            or producer.get("status") != "completed" or producer.get("actor").entity_id != record["issuer_id"]:
        raise ValueError("declarative Move producer receipt is missing or incomplete")
    if terminal:
        if not isinstance(record["end"], dict) or record["end"].get("at", engine.elapsed_seconds + 1) > engine.elapsed_seconds:
            raise ValueError("declarative Move terminal event is invalid")
    elif record["end"] is not None:
        raise ValueError("live declarative Move record cannot be ended")
    operation = record["operation"]
    if not terminal and operation == "statuses_until_switch":
        owned = record["payload"].get("owned_statuses")
        if not isinstance(owned, dict) or set(owned) != {"저주", "취약"} or any(
                value and condition not in holder.conditions for condition, value in owned.items()):
            raise ValueError("Catastropika status projection changed")
    if not terminal and operation == "rest_sleep" and "잠듦" not in holder.conditions:
        raise ValueError("Rest live record requires its Sleep projection")
    if not terminal and operation == "encounter_weight_and_stage":
        source = record["payload"].get("grant_source")
        if source not in holder.spec.get("state_grants", {}).get("weight_sources", {}).get("sources", {}):
            raise ValueError("Autotomize weight grant is missing")
    if not terminal and operation == "scene_type_replacement":
        source = record["payload"].get("grant_source")
        if source not in holder.spec.get("state_grants", {}).get("type_sources", {}).get("sources", {}):
            raise ValueError("Reflect Type grant is missing")


def validate_actor(actor):
    value = state(actor)
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != {"version", "sequence", "live", "history", "uses", "choices"} \
            or value["version"] != VERSION:
        raise ValueError("declarative Move actor state shape changed")
    C.integer(value["sequence"], "declarative Move sequence", 0)
    if any(not isinstance(value[field], list) for field in ("live", "history", "uses", "choices")):
        raise ValueError("declarative Move ledgers must be lists")
    for use in value["uses"]:
        if not isinstance(use, dict) or set(use) != {"move_id", "at", "turn"}:
            raise ValueError("Last Resort use observation shape changed")
        actor.r.move(use["move_id"])
        C.integer(use["at"], "Move use time", 0); C.integer(use["turn"], "Move use turn", 0)
    for choice in value["choices"]:
        required = {"id", "source", "operation", "clause_id", "source_row_sha256", "actor_id", "target_id",
                    "scene", "selected_at", "payload", "reason", "status", "consumed_record_id"}
        if not isinstance(choice, dict) or set(choice) != required or choice["actor_id"] != actor.entity_id:
            raise ValueError("declarative Move choice shape changed")
        row = definition(actor.r, choice["source"])
        if row is None or (choice["operation"], choice["clause_id"], choice["source_row_sha256"]) != (
                row["operation"], row["clause_id"], row["source_row_sha256"]):
            raise ValueError("declarative Move choice provenance changed")
        if choice["status"] not in ("pending", "used", "expired"):
            raise ValueError("declarative Move choice status changed")
    return True


def validate_world(engine, index):
    identities = set()
    consumed = []
    for actor in index.values():
        validate_actor(actor)
        value = state(actor)
        if value is None:
            continue
        for record in value["live"]:
            _validate_record(engine, index, actor, record, False)
            if record["id"] in identities: raise ValueError("duplicate declarative Move record identity")
            identities.add(record["id"])
        for record in value["history"]:
            _validate_record(engine, index, actor, record, True)
            if record["id"] in identities: raise ValueError("duplicate declarative Move record identity")
            identities.add(record["id"])
        for use in value["uses"]:
            if use["at"] > engine.elapsed_seconds:
                raise ValueError("Last Resort use observation is in the future")
        for choice in value["choices"]:
            if choice["target_id"] not in index or choice["selected_at"] > engine.elapsed_seconds or choice["scene"] > _scene(actor):
                raise ValueError("declarative Move choice references missing or future state")
            if choice["status"] == "used": consumed.append(choice["consumed_record_id"])
            elif choice["consumed_record_id"] is not None: raise ValueError("unconsumed declarative choice has a record")
    if any(identity not in identities for identity in consumed):
        raise ValueError("declarative Move choice consumption record is missing")
    return True

