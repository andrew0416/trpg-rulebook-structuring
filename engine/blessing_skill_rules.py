"""Exact CSV Blessing projections for the native skill-check consumer.

The ten source rows share acquisition and GM approval, but keep their own
configuration, action, lifetime, target, and roll transformation contracts.
This module prepares those transformations without drawing dice.  The engine
applies the prepared plan only after the ordinary request has been validated.
"""

from copy import deepcopy
import json
from pathlib import Path

import arithmetic_policy as M
import common_checks as C
import frequency as FREQ
import roll_pools as POOLS
import skill_modifiers as S
import state_grants as GRANTS
import turn as TURN


POLICY_PATH = Path(__file__).resolve().parents[1] / "data/blessing-skill-rules-policy.json"
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
if POLICY.get("schema_version") != 1:
    raise ValueError("unsupported Blessing skill-rule policy")

REQUIRED_RULE_FIELDS = {
    "clause_id",
    "record",
    "cell_sha256",
    "gift",
    "operation",
    "configuration",
    "action",
    "lifetime",
    "uses",
    "target_scope",
}
OPERATIONS = {
    "ancient_wisdom",
    "paragon",
    "watchful_sleep",
    "fount_of_knowledge",
    "plant_intuition",
    "spirit_of_justice",
    "dazzling_stage",
    "royal_privilege",
    "hero_of_balance",
    "alien_face",
}

RULES = {}
for _row in POLICY.get("rules", []):
    if set(_row) != REQUIRED_RULE_FIELDS:
        raise ValueError("exact Blessing skill-rule policy fields required")
    if _row["operation"] not in OPERATIONS:
        raise ValueError("unsupported Blessing skill-rule operation")
    if not isinstance(_row["clause_id"], str) or not _row["clause_id"].startswith(
        "C2CSV/input/db/class-data.csv:R"
    ):
        raise ValueError("source-bound Blessing CSV clause required")
    if type(_row["record"]) is not int or _row["record"] < 1:
        raise ValueError("positive Blessing CSV record required")
    if not isinstance(_row["cell_sha256"], str) or len(_row["cell_sha256"]) != 64:
        raise ValueError("Blessing source cell digest required")
    if not isinstance(_row["gift"], str) or not _row["gift"].startswith("gift/"):
        raise ValueError("canonical Blessing gift identity required")
    if not isinstance(_row["configuration"], list):
        raise ValueError("Blessing configuration field list required")
    if _row["gift"] in RULES:
        raise ValueError("duplicate Blessing skill-rule gift")
    RULES[_row["gift"]] = _row

if len(RULES) != 10 or {row["operation"] for row in RULES.values()} != OPERATIONS:
    raise ValueError("the exact ten-operation Blessing skill policy is required")

GIFTS = tuple(RULES)
BY_OPERATION = {row["operation"]: row["gift"] for row in RULES.values()}

ANCIENT_WISDOM = BY_OPERATION["ancient_wisdom"]
PARAGON = BY_OPERATION["paragon"]
WATCHFUL_SLEEP = BY_OPERATION["watchful_sleep"]
FOUNT_OF_KNOWLEDGE = BY_OPERATION["fount_of_knowledge"]
PLANT_INTUITION = BY_OPERATION["plant_intuition"]
SPIRIT_OF_JUSTICE = BY_OPERATION["spirit_of_justice"]
DAZZLING_STAGE = BY_OPERATION["dazzling_stage"]
ROYAL_PRIVILEGE = BY_OPERATION["royal_privilege"]
HERO_OF_BALANCE = BY_OPERATION["hero_of_balance"]
ALIEN_FACE = BY_OPERATION["alien_face"]

STATE = "_blessing_skill_rule_state"
CONFIGURATION = "_blessing_skill_rules"
ROLES = {"messiah", "contractor"}
SOCIAL_SKILLS = ("협박", "교활", "매력")
SHARDS = {
    "빨강": "협박",
    "주황": "명령",
    "노랑": "매력",
    "초록": "직감",
    "파랑": "협박",
    "보라": "집중",
}
CONTEXT_PURPOSES = {
    "occult_topic",
    "plant_related",
    "disarm",
    "resist_disarm",
    "singing",
    "dancing",
    "detect_lies",
    "discern_beliefs",
}


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonempty " + label + " required")
    return value


def _state(actor):
    value = actor.spec.get(STATE)
    if value is None:
        value = {"version": 1, "activations": {}, "history": []}
        actor.spec[STATE] = value
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("unsupported Blessing skill-rule state")
    if set(value) != {"version", "activations", "history"}:
        raise ValueError("exact Blessing skill-rule state fields required")
    if not isinstance(value["activations"], dict) or not isinstance(value["history"], list):
        raise ValueError("Blessing activation mappings and history required")
    return value


def _education_skills(rules):
    return {
        skill_id
        for skill_id in rules.skill_policy["skills"]
        if skill_id.endswith(" education")
    }


def _category(rules, value):
    matches = [
        category
        for category, aliases in rules.skill_policy["categories"].items()
        if S.key(value) in {S.key(category), *(S.key(alias) for alias in aliases)}
    ]
    if len(matches) != 1:
        raise ValueError("one physical, mental, or spirit Paragon category required")
    return matches[0]


def prepare_configuration(engine, actor, gift, requested):
    """Validate source-specific permanent choices before approval is written."""
    if gift not in RULES:
        if requested is not None:
            raise ValueError("this Blessing has no skill-rule configuration")
        return None
    rule = RULES[gift]
    fields = set(rule["configuration"])
    if not fields:
        if requested not in (None, {}):
            raise ValueError("this Blessing has no acquisition choices")
        values = {}
    else:
        if not isinstance(requested, dict) or set(requested) != fields:
            raise ValueError("exact Blessing acquisition configuration required")
        values = deepcopy(requested)

    if gift in (ANCIENT_WISDOM, PARAGON):
        if values["role"] not in ROLES:
            raise ValueError("Messiah or Contractor Blessing role required")
    if gift == PARAGON:
        values["category"] = _category(engine.r, values["category"])
    if gift == FOUNT_OF_KNOWLEDGE:
        selected = values["education_skills"]
        if not isinstance(selected, (list, tuple)) or len(selected) != 2:
            raise ValueError("Fount of Knowledge requires two Education skills")
        canonical = [S.skill_id(engine.r.skill_policy, skill, required=True) for skill in selected]
        if len(set(canonical)) != 2 or not set(canonical) <= _education_skills(engine.r):
            raise ValueError("two distinct Education skills required")
        values["education_skills"] = canonical

    return {
        "gift": gift,
        "clause_id": rule["clause_id"],
        "operation": rule["operation"],
        "values": values,
    }


def store_configuration(actor, record):
    if record is None:
        return
    rows = actor.spec.get(CONFIGURATION)
    if rows is None:
        rows = {}
        actor.spec[CONFIGURATION] = rows
    if not isinstance(rows, dict):
        raise ValueError("Blessing skill-rule configurations must be a mapping")
    gift = record["gift"]
    if gift in rows:
        raise ValueError("Blessing acquisition choices were already recorded")
    rows[gift] = deepcopy(record)


def _record(engine, actor, gift):
    import blessing_skill_features as BLESSINGS

    if gift not in RULES:
        raise ValueError("supported exact Blessing skill rule required")
    if not BLESSINGS.require(engine, actor, gift):
        return None
    rows = actor.spec.get(CONFIGURATION)
    if not isinstance(rows, dict) or gift not in rows:
        raise ValueError("approved Blessing is missing its acquisition configuration")
    stored = rows[gift]
    values = stored.get("values") if isinstance(stored, dict) else None
    refreshed = prepare_configuration(engine, actor, gift, values)
    if stored != refreshed:
        raise ValueError("Blessing acquisition configuration changed")
    return stored


def _owned_record(engine, actor, gift):
    import blessing_skill_features as BLESSINGS

    return _record(engine, actor, gift) if BLESSINGS.acquired(actor, gift) else None


def _scene(actor):
    return FREQ.state(actor)["scene"]


def activate(engine, actor, gift, *, reason):
    """Pay the exact Contractor action and commit its bounded activation."""
    _text(reason, "Blessing activation reason")
    if gift not in (ANCIENT_WISDOM, PARAGON):
        raise ValueError("only Contractor Blessings in this batch have activations")

    def apply(staged_engine, staged_actor):
        record = _record(staged_engine, staged_actor, gift)
        if record is None or record["values"].get("role") != "contractor":
            raise ValueError("actual acquired Contractor Blessing required")
        state = _state(staged_actor)
        previous = state["activations"].get(gift)
        if gift == ANCIENT_WISDOM:
            if isinstance(previous, dict) and previous.get("status") == "pending":
                raise ValueError("Ancient Wisdom already has a pending check activation")
            action = "free"
            lifetime = "next_bound_check"
        else:
            scene = _scene(staged_actor)
            if isinstance(previous, dict) and previous.get("scene") == scene:
                raise ValueError("Contractor Paragon is already active this scene")
            action = "swift"
            lifetime = "scene"
        if not TURN.spend(staged_engine, staged_actor, action, gift):
            raise ValueError("required Blessing action is unavailable")
        activation = {
            "id": gift + ":" + str(len(state["history"]) + 1),
            "gift": gift,
            "source": RULES[gift]["clause_id"],
            "action": action,
            "lifetime": lifetime,
            "at": staged_engine.elapsed_seconds,
            "reason": reason,
            "status": "pending" if gift == ANCIENT_WISDOM else "active",
        }
        if gift == PARAGON:
            activation["scene"] = _scene(staged_actor)
        state["activations"][gift] = activation
        state["history"].append(deepcopy(activation))
        staged_engine.log("  " + staged_actor.name + ": 축복 스킬 규칙 활성화", gift)
        return deepcopy(activation)

    return GRANTS.transition(engine, actor, apply)


def validate_sleep_check(engine, actor, skill, context):
    """Return the exact CSV source when Watchful Sleep permits this check."""
    record = _owned_record(engine, actor, WATCHFUL_SLEEP)
    if record is None:
        return None
    canonical = S.skill_id(engine.r.skill_policy, skill, required=True)
    eligible = (
        isinstance(context, dict)
        and set(context) == {"purpose", "reason"}
        and context.get("purpose") == "imminent_danger"
    )
    if canonical != "perception" or not eligible:
        raise ValueError("CSV Watchful Sleep permits only an imminent-danger Perception check")
    _text(context["reason"], "GM imminent danger reason")
    return record["clause_id"]


def _purpose(context):
    return context.get("purpose") if isinstance(context, dict) else None


def shared_context(context):
    """Remove only this adapter's modifier declaration for older consumers."""
    if not isinstance(context, dict) or "modifier_basis" not in context:
        return context
    remaining = {key: value for key, value in context.items() if key != "modifier_basis"}
    return remaining or None


def _require_reason(context, label):
    if not isinstance(context, dict):
        raise ValueError("explicit " + label + " check context required")
    return _text(context.get("reason"), "GM " + label + " reason")


def _add_modifier(plan, gift, value, detail):
    if type(value) is not int:
        raise ValueError("whole-number Blessing skill modifier required")
    plan["modifier"] += value
    plan["modifier_sources"].append((gift, value, detail))


def _add_dice(plan, gift, count, detail):
    C.integer(count, "Blessing bonus dice", 1)
    plan["bonus_dice"] += count
    plan["effects"].append({"source": gift, "kind": "bonus_dice", "value": count, "detail": detail})


def _replace_body_with_mind(plan, gift, resolved, context):
    if not isinstance(context, dict) or "modifier_basis" not in context:
        return
    basis = context["modifier_basis"]
    if not isinstance(basis, dict) or set(basis) != {"body", "mind", "selected"}:
        raise ValueError("exact body/mind modifier basis required")
    if any(type(basis[name]) is not int for name in ("body", "mind")):
        raise ValueError("whole-number body and mind modifiers required")
    if basis["selected"] != "mind":
        raise ValueError("Blessing modifier replacement must explicitly select mind")
    if resolved.get("additional") != basis["body"]:
        raise ValueError("ordinary skill modifier must equal the declared body modifier")
    delta = basis["mind"] - basis["body"]
    _add_modifier(plan, gift, delta, "mind replaces body")


def _owned_shard_item(engine, actor, name):
    """Source-neutral physical shard contract after the adapter's Gift gate."""
    canonical = name.removeprefix("item/") if isinstance(name, str) else name
    if canonical not in {colour + "조각" for colour in SHARDS}:
        return None
    inventory = actor.spec.get("items", {})
    if not isinstance(inventory, dict):
        raise ValueError("actual shard inventory required")
    C.integer(inventory.get(canonical, 0), "owned shard count", 1)
    uid = "item/" + canonical
    if engine.r._selected_rule(uid) != uid:
        raise ValueError("selected shard item requires its own source policy")
    return ([{"type": "trainer_slot", "slot": "장신구"}], {
        "id": uid,
        "name": canonical,
        "category": "장신구",
        "trainer_slot": "장신구",
    })


def _royal_modifier(engine, actor, canonical):
    """Project the one current actual Accessory; adapters label their own source."""
    equipped = [
        row
        for row in getattr(actor, "_item_reg", {}).values()
        if "장신구" in row.get("slots", [])
        and row.get("item_id", "").removeprefix("item/") in {colour + "조각" for colour in SHARDS}
    ]
    if len(equipped) > 1:
        raise ValueError("one native Accessory slot cannot contain several shards")
    if not equipped:
        return None
    name = equipped[0]["item_id"].removeprefix("item/")
    _owned_shard_item(engine, actor, name)
    colour = name.removesuffix("조각")
    expected = S.skill_id(engine.r.skill_policy, SHARDS[colour], required=True)
    return (2, colour) if canonical == expected else None


def shard_item(engine, actor, name):
    """Expose an owned shard as an Accessory for the exact CSV Gift variant."""
    record = _owned_record(engine, actor, ROYAL_PRIVILEGE)
    if record is None:
        return None
    return _owned_shard_item(engine, actor, name)


def prepare(engine, actor, skill, resolved, context=None, target=None):
    """Build one non-consuming plan for the native skill-roll path."""
    canonical = S.skill_id(engine.r.skill_policy, skill, required=True)
    category = engine.r.skill_policy["skills"][canonical]["category"]
    purpose = _purpose(context)
    plan = {
        "modifier": 0,
        "modifier_sources": [],
        "bonus_dice": 0,
        "reroll_ones": [],
        "consume_activation": None,
        "effects": [],
    }

    ancient = _owned_record(engine, actor, ANCIENT_WISDOM)
    if ancient is not None:
        role = ancient["values"]["role"]
        education = canonical in _education_skills(engine.r)
        occult_check = canonical == "occult education" or (
            education and purpose == "occult_topic"
        )
        if role == "messiah" and occult_check:
            if education and canonical != "occult education":
                _require_reason(context, "occult topic")
            _add_dice(plan, ANCIENT_WISDOM, 1, "Messiah occult knowledge")
        elif role == "contractor" and canonical == "occult education":
            activation = _state(actor)["activations"].get(ANCIENT_WISDOM)
            if isinstance(activation, dict) and activation.get("status") == "pending":
                _add_dice(plan, ANCIENT_WISDOM, 2, "Contractor occult activation")
                plan["consume_activation"] = activation["id"]

    paragon = _owned_record(engine, actor, PARAGON)
    if paragon is not None and category == paragon["values"]["category"]:
        if paragon["values"]["role"] == "messiah":
            _add_modifier(plan, PARAGON, 2, category)
        else:
            activation = _state(actor)["activations"].get(PARAGON)
            if isinstance(activation, dict) and activation.get("scene") == _scene(actor):
                _add_modifier(plan, PARAGON, 1, category + " scene activation")

    fount = _owned_record(engine, actor, FOUNT_OF_KNOWLEDGE)
    if fount is not None and canonical in fount["values"]["education_skills"]:
        plan["reroll_ones"].append(FOUNT_OF_KNOWLEDGE)

    plant = _owned_record(engine, actor, PLANT_INTUITION)
    if plant is not None and canonical == "survival" and purpose == "plant_related":
        _require_reason(context, "plant-related")
        plan["reroll_ones"].append(PLANT_INTUITION)

    justice = _owned_record(engine, actor, SPIRIT_OF_JUSTICE)
    if justice is not None:
        if canonical == "combat":
            _replace_body_with_mind(plan, SPIRIT_OF_JUSTICE, resolved, context)
        if (purpose in {"disarm", "resist_disarm"} or
                purpose == "telekinetic_maneuver" and context.get("maneuver") == "maneuver/무장해제"):
            _require_reason(context, "disarm")
            _add_modifier(plan, SPIRIT_OF_JUSTICE, 2, purpose)

    stage = _owned_record(engine, actor, DAZZLING_STAGE)
    social = {S.skill_id(engine.r.skill_policy, value, required=True) for value in SOCIAL_SKILLS}
    if stage is not None and canonical in social and purpose in {"singing", "dancing"}:
        _require_reason(context, purpose)
        highest = max(S.effective_rank(engine.r, actor, value) for value in SOCIAL_SKILLS)
        _add_modifier(plan, DAZZLING_STAGE, M.ratio(highest, 2), purpose)

    royal = _owned_record(engine, actor, ROYAL_PRIVILEGE)
    if royal is not None:
        shard = _royal_modifier(engine, actor, canonical)
        if shard is not None:
            value, colour = shard
            _add_modifier(plan, ROYAL_PRIVILEGE, value, colour)

    if target is not None and target is not actor and canonical == "intuition" and purpose in {
        "detect_lies",
        "discern_beliefs",
    }:
        balance = _owned_record(engine, target, HERO_OF_BALANCE)
        if balance is not None:
            _require_reason(context, purpose)
            _add_modifier(plan, HERO_OF_BALANCE, -3, target.entity_id + ":" + purpose)

    alien = _owned_record(engine, actor, ALIEN_FACE)
    if alien is not None and canonical == "intimidate":
        _replace_body_with_mind(plan, ALIEN_FACE, resolved, context)
        if target is not None and getattr(target, "kind", None) == "pokemon":
            _add_modifier(plan, ALIEN_FACE, 2, target.entity_id)

    return plan


def apply_faces(engine, actor, faces, plan):
    """Reroll each current 1 once per applicable exact source."""
    current = list(faces)
    for source in plan.get("reroll_ones", []):
        positions = [index for index, face in enumerate(current) if face == 1]
        if not positions:
            continue
        selected = POOLS.select(current, operation="reroll", indices=positions, rng=engine.rng)
        current = list(selected["faces"])
        plan["effects"].append({
            "source": source,
            "kind": "reroll_ones",
            "value": len(positions),
            "detail": tuple(positions),
        })
    return tuple(current)


def finish(engine, actor, plan):
    """Consume a prepared one-check activation only after the roll exists."""
    activation_id = plan.get("consume_activation")
    if activation_id is not None:
        state = _state(actor)
        activation = state["activations"].get(ANCIENT_WISDOM)
        if not isinstance(activation, dict) or activation.get("id") != activation_id:
            raise ValueError("prepared Ancient Wisdom activation changed before consumption")
        activation["status"] = "consumed"
        activation["consumed_at"] = engine.elapsed_seconds
        state["history"].append(deepcopy(activation))
    for effect in plan.get("effects", []):
        engine.log(
            "  축복 스킬 효과 " + effect["source"] + ": " + effect["kind"] + " " + str(effect["value"]),
            effect["source"],
        )


def identify_visible_crop(engine, actor, item_name, *, visible, reason):
    """Return the sourced berry/apricorn identity from an explicit visual fact."""
    if type(visible) is not bool:
        raise ValueError("visible crop fact must be boolean")
    _text(reason, "visible crop observation reason")
    record = _owned_record(engine, actor, PLANT_INTUITION)
    if record is None:
        raise ValueError("actual acquired Plant Intuition required")
    if not visible:
        raise ValueError("Plant Intuition identifies only a visible berry or Apricorn")
    import cultivation_state as CULTIVATION

    crop = CULTIVATION.crop(engine.r, item_name)
    if crop["kind"] not in {"berry", "apricorn"}:
        raise ValueError("visible subject is not a sourced berry or Apricorn")
    return {
        "source": record["clause_id"],
        "gift": PLANT_INTUITION,
        "name": item_name,
        "kind": crop["kind"],
        "identified": True,
        "reason": reason,
    }
