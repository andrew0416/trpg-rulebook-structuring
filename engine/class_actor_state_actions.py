"""Exact trainer-feature actions fed by committed recovery/resource events.

The feature owner keeps optional triggered decisions.  Native food, medicine,
growth, healing, injury, frequency, action, and temporary-HP modules remain the
authorities for the resources they own.
"""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import re

import frequency as FREQUENCY


POLICY_PATH = "data/class-actor-state-actions-policy.json"
STATE = "_class_actor_state_actions"
KIND = "class_actor_state_action"

EMERGENCY_CARE = "feat/응급-처치-전문지식"
TOP_PERCENTAGE = "feat/탑-퍼센티지"
THATS_THE_TASTE = "feat/이-맛이야"
MEDICAL_TECHNIQUE = "feat/의료-테크닉"
COMPLEX_AFTERTASTE = "feat/복잡한-뒷맛"

ALL_RULES = frozenset((EMERGENCY_CARE, TOP_PERCENTAGE, THATS_THE_TASTE, MEDICAL_TECHNIQUE, COMPLEX_AFTERTASTE))
TRIGGERED_RULES = frozenset((TOP_PERCENTAGE, THATS_THE_TASTE, MEDICAL_TECHNIQUE, COMPLEX_AFTERTASTE))
# Book-bound rule: the Chef definitions (chef_cooking) verify its ch04 excerpt; the CSV policy keeps its four rows.
BOOK_CLAUSE_BY_RULE = {COMPLEX_AFTERTASTE: "input/ch04-trainer-classes.md:1910-1914"}
CLAUSE_BY_RULE = {
    EMERGENCY_CARE: "C2CSV/input/db/feats.csv:R45:main",
    TOP_PERCENTAGE: "C2CSV/input/db/feats.csv:R59:main",
    THATS_THE_TASTE: "C2CSV/input/db/feats.csv:R302:main",
    MEDICAL_TECHNIQUE: "C2CSV/input/db/feats.csv:R434:main",
}
ALIASES = {
    EMERGENCY_CARE: ("응급 처치 전문지식", "Emergency Care Expertise"),
    TOP_PERCENTAGE: ("탑 퍼센티지", "Top Percentage"),
    THATS_THE_TASTE: ("이 맛이야", "That's the Taste"),
    MEDICAL_TECHNIQUE: ("의료 테크닉", "Medical Techniques"),
    COMPLEX_AFTERTASTE: ("복잡한 뒷맛", "Complex Aftertaste"),
}


def _clause(rule_id):
    return CLAUSE_BY_RULE.get(rule_id, BOOK_CLAUSE_BY_RULE.get(rule_id))


def _name(rules, rule_id):
    if rule_id in CLAUSE_BY_RULE:
        return policy(rules)["clauses"][CLAUSE_BY_RULE[rule_id]]["name"]
    return rules.selection.units[rule_id]["title"]


def _key(value):
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value).casefold())


def identity(value):
    if not isinstance(value, str):
        return None
    normalized = _key(value)
    for rule_id, aliases in ALIASES.items():
        candidates = {_key(rule_id), _key(_clause(rule_id))}
        candidates.update(_key(alias) for alias in aliases)
        if normalized in candidates:
            return rule_id
    return None


def _policy_path(rules):
    canonical = Path(rules.root) / POLICY_PATH
    staged = Path(__file__).resolve().parent.parent / POLICY_PATH
    return canonical if canonical.is_file() else staged


def policy(rules):
    cached = getattr(rules, "_class_actor_state_action_policy", None)
    if cached is not None:
        return cached
    path = _policy_path(rules)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("contract") != "trainer recovery and resource state actions":
        raise ValueError("unsupported class actor-state action policy")
    source_path = Path(rules.root) / data.get("source_file", "")
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != data.get("source_file_sha256"):
        raise ValueError("class actor-state action source changed")
    with source_path.open(encoding="utf-8-sig", newline="") as source_file:
        source_rows = list(csv.reader(source_file))
    clauses = data.get("clauses")
    if not isinstance(clauses, dict) or set(clauses) != set(CLAUSE_BY_RULE.values()):
        raise ValueError("class actor-state action policy needs the exact reviewed clauses")
    for rule_id, clause_id in CLAUSE_BY_RULE.items():
        row = clauses[clause_id]
        record = row.get("source_record")
        if row.get("id") != clause_id or row.get("rule_id") != rule_id:
            raise ValueError("class actor-state action identity changed: " + clause_id)
        if type(record) is not int or record < 1 or source_rows[record - 1] != row.get("source_cells"):
            raise ValueError("class actor-state action source row changed: " + clause_id)
    rules._class_actor_state_action_policy = data
    return data


def acquired_source(trainer, rule_id):
    if trainer.kind != "trainer" or rule_id not in ALL_RULES:
        return None
    values = trainer.spec.get("feats", [])
    if not isinstance(values, (list, tuple)):
        raise ValueError("trainer feature ownership must be a list")
    matches = [value for value in values if identity(value) == rule_id]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("class state action requires exactly one acquired source: " + rule_id)
    source = matches[0]
    if trainer.r._selected_rule(source) != source:
        raise ValueError("selected feature variant requires its own state-action policy")
    if rule_id==TOP_PERCENTAGE and __import__('ace_trainer').acquired(trainer,TOP_PERCENTAGE):
        from source_context import verified_source
        verified_source(trainer.r,__import__('ace_trainer').policy(trainer.r)['body'],label='actual Top Percentage body')
    elif rule_id in BOOK_CLAUSE_BY_RULE:
        import chef_cooking as CHEF
        CHEF.definitions(trainer.r)
    else:
        policy(trainer.r)
    return source


def _state(actor, create=False):
    value = actor.spec.get(STATE)
    if value is None and create:
        value = {"version": 1, "serial": 0, "events": []}
        actor.spec[STATE] = value
    if value is None:
        return None
    if actor.kind != "trainer" or not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("class actor-state actions belong to one trainer")
    if type(value.get("serial")) is not int or value["serial"] < 0 or not isinstance(value.get("events"), list):
        raise ValueError("invalid class actor-state action ledger")
    required = {
        "id", "source", "clause_id", "owner_id", "target_id", "trigger",
        "payload", "at", "round", "status", "result",
    }
    identities = set()
    for event in value["events"]:
        if not isinstance(event, dict) or set(event) != required:
            raise ValueError("invalid class actor-state action event")
        if event["id"] in identities or not isinstance(event["id"], str) or not event["id"]:
            raise ValueError("class state event identities must be distinct nonempty text")
        identities.add(event["id"])
        allowed_clause=event["clause_id"]==_clause(event["source"])
        if event['source']==TOP_PERCENTAGE and event['clause_id']=='input/ch04-trainer-classes.md:334-338':
            import ace_trainer as ACE
            allowed_clause=any(r['request_id']==event['payload'].get('acquisition_request') for r in ACE.records(actor,TOP_PERCENTAGE))
        if event["source"] not in TRIGGERED_RULES or not allowed_clause:
            raise ValueError("class state event source identity changed")
        for field in ("owner_id", "target_id", "trigger"):
            if not isinstance(event[field], str) or not event[field]:
                raise ValueError("class state event needs actual identity facts")
        if not isinstance(event["payload"], dict):
            raise ValueError("class state event payload must be a mapping")
        try:
            json.dumps(event["payload"], ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("class state event payload must be JSON data") from exc
        if type(event["at"]) is not int or event["at"] < 0 or type(event["round"]) is not int or event["round"] < 0:
            raise ValueError("class state event clock is invalid")
        if event["status"] not in ("pending", "completed", "declined", "superseded"):
            raise ValueError("class state event status is invalid")
        if event["result"] is not None and not isinstance(event["result"], dict):
            raise ValueError("class state event result must be a mapping or null")
    return value


def validate(actor):
    _state(actor)
    return True


def _actor_index(engine):
    import world_entities as WORLD
    return WORLD.actor_index(engine)


def _owner(engine, actor):
    index = _actor_index(engine)
    if actor.kind == "trainer":
        return actor if index.get(actor.entity_id) is actor else None
    if actor.kind != "pokemon":
        return None
    owner_id = actor.spec.get("trainer_id")
    owner = index.get(owner_id)
    if not isinstance(owner_id, str) or owner is None or owner.kind != "trainer":
        return None
    if actor.spec.get("trainer") not in (None, owner.name):
        raise ValueError("Pokemon trainer name conflicts with its owner identity")
    return owner


def _offer(engine, owner, target, source, trigger, payload):
    if acquired_source(owner, source) is None:
        return None
    state = _state(owner, create=True)
    state["serial"] += 1
    event_id = "class-state-action:" + owner.entity_id + ":" + str(state["serial"])
    clause=_clause(source)
    if source==TOP_PERCENTAGE:
        import ace_trainer as ACE
        actual=ACE.acquired(owner,TOP_PERCENTAGE)
        if actual:
            clause=ACE.top_source(owner)
            payload=dict(payload,acquisition_request=actual['request_id'])
    event = {
        "id": event_id,
        "source": source,
        "clause_id": clause,
        "owner_id": owner.entity_id,
        "target_id": target.entity_id,
        "trigger": trigger,
        "payload": deepcopy(payload),
        "at": engine.elapsed_seconds,
        "round": engine.round_no,
        "status": "pending",
        "result": None,
    }
    state["events"].append(event)
    engine.log("    선택 대기: " + _name(engine.r, source), source)
    return event_id


def observe_food_buff_consumed(engine, actor, receipt):
    """Offer That's the Taste only from the shared committed food receipt."""
    if not isinstance(receipt, dict) or any(key not in receipt for key in ("sequence", "buff_id", "item", "producer")):
        raise ValueError("actual Digestion Buff consumption receipt required")
    owner = _owner(engine, actor)
    offered = None
    if owner is not None:
        offered = _offer(engine, owner, actor, THATS_THE_TASTE, "digestion_buff_consumed", {
            "receipt_sequence": receipt["sequence"],
            "buff_id": receipt["buff_id"],
            "item": receipt["item"],
            "producer": receipt["producer"],
        })
    assignment = receipt.get("taste_assignment")
    if isinstance(assignment, dict) and assignment.get("taste") is not None:
        # Complex Aftertaste: "you or an ally trades in a Digestion Buff from an item with a Taste".
        import chef_cooking as CHEF
        for trainer in CHEF.aftertaste_owners(engine, actor):
            _offer(engine, trainer, actor, COMPLEX_AFTERTASTE, "tasted_digestion_buff_consumed", {
                "receipt_sequence": receipt["sequence"],
                "buff_id": receipt["buff_id"],
                "item": receipt["item"],
                "producer": receipt["producer"],
                "taste": assignment["taste"],
                "assigned_by": assignment.get("assigned_by"),
            })
    return offered


def observe_healing_item_used(engine, user, target, item_name, result):
    """Offer Medical Technique after one actual restorative medicine action."""
    if user.kind != "trainer" or _actor_index(engine).get(user.entity_id) is not user:
        return None
    effects, header = engine.r.item_effects(item_name)
    import restorative_items as RESTORATIVE
    item_id = header.get("id")
    restorative = header.get("category") == "약" and item_id not in RESTORATIVE.X_ITEMS
    if not restorative:
        return None
    if not isinstance(result, tuple) or len(result) != 2:
        raise ValueError("actual immediate medicine result required")
    return _offer(engine, user, target, MEDICAL_TECHNIQUE, "healing_item_used", {
        "item_id": item_id,
        "item_name": item_name,
        "native_result": list(result),
    })


def observe_level_up(engine, pokemon, old_level, new_level):
    """Offer each crossed fifth-level trigger from the native growth commit."""
    if pokemon.kind != "pokemon" or type(old_level) is not int or type(new_level) is not int or new_level < old_level:
        raise ValueError("actual Pokemon level transition required")
    owner = _owner(engine, pokemon)
    if owner is None or acquired_source(owner, TOP_PERCENTAGE) is None:
        return ()
    offered = []
    for level in range(old_level + 1, new_level + 1):
        if level % 5 == 0:
            offered.append(_offer(engine, owner, pokemon, TOP_PERCENTAGE, "level_multiple_of_five", {"level": level}))
    return tuple(event_id for event_id in offered if event_id is not None)


def offer_top_percentage_at_max_level(engine, trainer, pokemon):
    """Use the printed maximum-level exception without fabricating level history."""
    if pokemon.kind != "pokemon" or pokemon.level != 100:
        raise ValueError("Top Percentage trigger exception requires a maximum-level Pokemon")
    if _owner(engine, pokemon) is not trainer:
        raise ValueError("Top Percentage requires your actual Pokemon")
    if acquired_source(trainer, TOP_PERCENTAGE) is None:
        raise ValueError("Top Percentage acquisition required")
    if __import__('ace_trainer').acquired(trainer,TOP_PERCENTAGE):
        raise ValueError('Core body Top Percentage requires an actual fifth-level trigger; maximum-level exception belongs to CSV59')
    return _offer(engine, trainer, pokemon, TOP_PERCENTAGE, "maximum_level_exception", {"level": 100})


def pending(engine, trainer):
    index = _actor_index(engine)
    if index.get(trainer.entity_id) is not trainer or trainer.kind != "trainer":
        raise ValueError("actual registered trainer required")
    state = _state(trainer)
    if state is None:
        return ()
    return tuple(deepcopy(event) for event in state["events"] if event["status"] == "pending")


def ensure_clear(engine):
    if getattr(engine, "_native_move_resolution_depth", 0):
        return
    for actor in _actor_index(engine).values():
        state = _state(actor)
        if state is not None and any(event["status"] == "pending" for event in state["events"]):
            raise ValueError("triggered class state action must be accepted or declined before another action")


def _find_event(owner, event_id):
    state = _state(owner)
    if state is None:
        raise ValueError("unknown class actor-state action")
    matches = [event for event in state["events"] if event["id"] == event_id]
    if len(matches) != 1 or matches[0]["status"] != "pending":
        raise ValueError("pending class actor-state action required")
    return matches[0]


def _top_percentage_count(engine, target):
    source = target.spec.get('state_grants', {}).get('sources', {}).get('top-percentage:' + target.entity_id)
    if source is not None:
        # Older native sources were created only by the fourth use. New uses
        # keep the same permanent source on the Pokemon, across owner removal.
        used = source.get('top_percentage_uses', 4)
        if type(used) is not int or not 1 <= used <= 4:
            raise ValueError('invalid permanent Top Percentage use count')
        return used
    # Upgrade native pre-fourth-use history without inferring uses from TP.
    return sum(
        event["source"] == TOP_PERCENTAGE
        and event["target_id"] == target.entity_id
        and event["status"] == "completed"
        and event["result"].get("used") is True
        for owner in _actor_index(engine).values()
        for event in (_state(owner) or {}).get('events', [])
    )


def _apply_top_percentage(engine, owner, target, event):
    used = _top_percentage_count(engine, target)
    if used >= 4:
        raise ValueError("Top Percentage may affect one Pokemon at most four times")
    if target.kind != "pokemon" or _owner(engine, target) is not owner:
        raise ValueError("Top Percentage requires your actual Pokemon")
    balance = target.spec.get("tutor_points")
    if type(balance) is not int or balance < 0:
        raise ValueError("known current Tutor Point balance required")
    target.spec["tutor_points"] = balance + 1
    result = {"tutor_points_granted": 1, "target_uses": used + 1}
    import state_grants as GRANTS
    source_id = "top-percentage:" + target.entity_id
    prior=target.spec.get(GRANTS.KEY,{}).get('sources',{}).get(source_id,{})
    clause=prior.get('clause_id',event['clause_id'])
    source = GRANTS._source(target, source_id, KIND, lifetime="permanent_fourth_use",
        rule_id=TOP_PERCENTAGE, clause_id=clause, tutor_points=0)
    source['top_percentage_uses'] = used + 1
    if used + 1 == 4:
        GRANTS._source(
            target,
            source_id,
            KIND,
            owner_id=owner.entity_id,
            lifetime="permanent_fourth_use",
            rule_id=TOP_PERCENTAGE,
            clause_id=clause,
            tutor_points=0,
        )
        for stat in ("hp", "atk", "def", "spa", "spd", "spe"):
            GRANTS.stat(target, stat, 1, source_id, operation_id=stat)
        result["all_base_stats_granted"] = 1
    else:
        result["all_base_stats_granted"] = 0
    return result


def _apply_triggered(engine, owner, target, event):
    source = event["source"]
    if source == TOP_PERCENTAGE:
        return _apply_top_percentage(engine, owner, target, event)
    import action_points as AP
    AP.charge(owner, 1, mode="spend")
    if source == COMPLEX_AFTERTASTE:
        import chef_cooking as CHEF
        return CHEF.aftertaste_grant(engine, owner, target, event)
    if source == THATS_THE_TASTE:
        import skill_modifiers as SKILL
        import temporary_hp as TEMP_HP
        rank = SKILL.effective_rank(engine.r, owner, "직감")
        granted = TEMP_HP.grant(
            engine,
            target,
            rank * 2,
            stack=True,
            contribution_source=TEMP_HP.food_source(target, 'chef_hits',
                target.spec['food_consumption_receipts'][event['payload']['receipt_sequence'] - 1]),
            provenance={
                "source": source,
                "event_id": event["id"],
                "food_receipt_sequence": event["payload"]["receipt_sequence"],
            },
        )
        result = {"intuition_rank": rank, "temporary_hp_granted": granted, "ap_spent": 1}
        blocked = TEMP_HP.blocked_reason(target)
        if blocked is not None:
            result["temporary_hp_blocked_reason"] = blocked
        return result
    if source == MEDICAL_TECHNIQUE:
        import skill_modifiers as SKILL
        rank = SKILL.effective_rank(engine.r, owner, "의학")
        amount = engine.tick(target) + rank
        healed = engine.heal(target, amount, source_kind="feature")
        return {"medicine_rank": rank, "healing_requested": amount, "healed": healed, "ap_spent": 1}
    raise ValueError("unsupported class actor-state action source")


def resolve(engine, trainer, event_id, *, use):
    if type(use) is not bool:
        raise ValueError("class state action decision must be explicit")
    index = _actor_index(engine)
    if index.get(trainer.entity_id) is not trainer or trainer.kind != "trainer":
        raise ValueError("actual registered trainer required")
    import state_grants as GRANTS

    def apply(staged_engine, staged_owner):
        actors = _actor_index(staged_engine)
        event = _find_event(staged_owner, event_id)
        if not use:
            event["status"] = "declined"
            event["result"] = {"used": False}
            return deepcopy(event["result"])
        if acquired_source(staged_owner, event["source"]) is None:
            raise ValueError("class state feature acquisition ended before use")
        target = actors.get(event["target_id"])
        if target is None:
            raise ValueError("class state action target is no longer in the world")
        import action_lifecycle as ACTION
        ACTION.triggered_free_action(staged_engine, staged_owner, event["source"])
        result = _apply_triggered(staged_engine, staged_owner, target, event)
        event["status"] = "completed"
        event["result"] = {"used": True, **result}
        return deepcopy(event["result"])

    return GRANTS.transition(engine, trainer, apply)


def _target_daily_key(engine, owner, target):
    declaration = {"kind": "daily", "uses": 1, "scope": ["target"]}
    return FREQUENCY.declaration_key(
        engine, owner, target, EMERGENCY_CARE, "extended", declaration
    )


def emergency_care(engine, trainer, target):
    """Use the exact tool-backed Daily x3 Extended recovery atomically."""
    index = _actor_index(engine)
    if index.get(trainer.entity_id) is not trainer or index.get(target.entity_id) is not target:
        raise ValueError("actual registered trainer and target required")
    if acquired_source(trainer, EMERGENCY_CARE) is None:
        raise ValueError("Emergency Care Expertise acquisition required")
    if target.kind not in ("trainer", "pokemon") or target.dead:
        raise ValueError("Emergency Care Expertise requires a living trainer or Pokemon")
    import item_stock as STOCK
    STOCK.prepare(engine, trainer, "item/응급치료키트", allow_empty=False)
    frequency = {"kind": "daily", "uses": 3}
    target_frequency = {"kind": "daily", "uses": 1}
    if not FREQUENCY.activation_allowed(trainer, EMERGENCY_CARE, frequency, engine=engine):
        raise ValueError("Emergency Care Expertise Daily x3 exhausted")
    target_key = _target_daily_key(engine, trainer, target)
    medical = acquired_source(trainer, MEDICAL_TECHNIQUE) is not None
    if not medical and not FREQUENCY.activation_allowed(trainer, target_key, target_frequency, engine=engine):
        raise ValueError("Emergency Care Expertise target daily limit exhausted")
    import state_grants as GRANTS

    def apply(staged_engine, staged_trainer, staged_target):
        if acquired_source(staged_trainer, EMERGENCY_CARE) is None:
            raise ValueError("Emergency Care Expertise acquisition ended before use")
        STOCK.prepare(staged_engine, staged_trainer, "item/응급치료키트", allow_empty=False)
        if not FREQUENCY.activation_allowed(staged_trainer, EMERGENCY_CARE, frequency, engine=staged_engine):
            raise ValueError("Emergency Care Expertise Daily x3 exhausted")
        staged_target_key = _target_daily_key(staged_engine, staged_trainer, staged_target)
        medical_now = acquired_source(staged_trainer, MEDICAL_TECHNIQUE) is not None
        if not medical_now and not FREQUENCY.activation_allowed(
            staged_trainer, staged_target_key, target_frequency, engine=staged_engine
        ):
            raise ValueError("Emergency Care Expertise target daily limit exhausted")
        import turn as TURN
        if not TURN.spend(staged_engine, staged_trainer, "extended", EMERGENCY_CARE):
            raise ValueError("Emergency Care Expertise Extended Action unavailable")
        import injury_recovery as INJURY
        import status_sets as STATUS
        injury = INJURY.heal(staged_engine, staged_target, 1, source=EMERGENCY_CARE)
        healed = staged_engine.heal(staged_target, staged_target.base_max_hp, source_kind="feature")
        before = STATUS.afflictions(staged_target)
        STATUS.cure_group(staged_engine, staged_target)
        FREQUENCY.consume_activation(staged_trainer, EMERGENCY_CARE, frequency, engine=staged_engine)
        if not medical_now:
            FREQUENCY.consume_activation(staged_trainer, staged_target_key, target_frequency, engine=staged_engine)
        return {
            "source": EMERGENCY_CARE,
            "target_id": staged_target.entity_id,
            "injuries_removed": injury,
            "healed": healed,
            "statuses_cured": [name for name in before if name not in staged_target.conditions],
            "target_daily_limit_waived": medical_now,
            "tool_retained": True,
        }

    return GRANTS.transition(engine, trainer, apply, participants=(target,))
