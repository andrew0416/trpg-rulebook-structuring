"""Exact event consumers for reviewed held-item reactions.

The item registry owns equipment lifetime.  This module only consumes events
that the static registration path cannot represent without applying them at
the wrong time.
"""
from copy import deepcopy
import hashlib
import json
import os


POLICY_FILE = "held-item-reaction-policy.json"
ITEM_KINDS = {
    "item/허탕보험": "blunder_policy",
    "item/울퉁불퉁멧": "rocky_helmet",
}


def _path(rules):
    canonical = os.path.join(rules.root, "data", POLICY_FILE)
    staged = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", POLICY_FILE))
    return canonical if os.path.exists(canonical) else staged


def policy(rules):
    with open(_path(rules), encoding="utf-8") as handle:
        value = json.load(handle)
    rows = value.get("rows")
    if value.get("schema_version") != 1 or value.get("contract") != "physical held-item event reactions":
        raise ValueError("held-item reaction policy schema changed")
    if not isinstance(rows, dict) or set(rows) != set(ITEM_KINDS):
        raise ValueError("held-item reaction policy must contain the exact reviewed rows")
    source = os.path.join(rules.root, "input", "db", "inventory.csv")
    with open(source, "rb") as handle:
        source_sha = hashlib.sha256(handle.read()).hexdigest()
    if source_sha != value.get("source_file_sha256"):
        raise ValueError("held-item reaction inventory source changed")
    with open(os.path.join(rules.root, "data", "verification", "category2-item-table-status.json"), encoding="utf-8") as handle:
        status = json.load(handle)
    source_rows = {row["clause_id"]: row for row in status.get("new_clauses", ())}
    seen = set()
    for item_id, row in rows.items():
        if item_id != row.get("item_id") or row.get("kind") != ITEM_KINDS[item_id]:
            raise ValueError("held-item reaction identity or kind changed")
        clause = row.get("clause_id")
        if not isinstance(clause, str) or clause in seen:
            raise ValueError("held-item reaction clause identity changed")
        seen.add(clause)
        registered = source_rows.get(clause)
        if registered is None or len(registered.get("source", ())) != 1:
            raise ValueError("held-item reaction source row is missing")
        src = registered["source"][0]
        expected = (row.get("source_file"), row.get("source_row"), row.get("source_columns"), row.get("source_row_sha256"))
        actual = (src.get("file"), src.get("row"), src.get("columns"), src.get("raw_cells_sha256"))
        if expected != actual:
            raise ValueError("held-item reaction source provenance changed: " + clause)
        header = rules.item_effects(item_id)[1]
        if header.get("id") != item_id or rules._selected_rule(item_id) != item_id:
            raise ValueError("held-item reaction selected item changed: " + item_id)
    return value


def definition(rules, item_id):
    return deepcopy(policy(rules)["rows"].get(item_id))


def prepare_register(engine, actor, item_id):
    if item_id not in ITEM_KINDS:
        return None
    row = definition(engine.r, item_id)
    if actor.kind != "pokemon":
        raise ValueError(row["name"] + " requires a pokemon wearer")
    return row


def consumes_effect(plan, effect):
    if not plan or not isinstance(effect, dict):
        return False
    if plan["kind"] == "blunder_policy":
        return effect.get("type") == "initiative_mod" and effect.get("trigger") == "own attack misses"
    if plan["kind"] == "rocky_helmet":
        return effect.get("type") == "hp_loss" and effect.get("trigger") == "holder hit by damaging melee attack"
    return False


def _active(engine, actor, kind):
    """Return exact live physical registrations; legacy names are not evidence."""
    import held_equipment as HELD
    HELD.require_resolved(actor)
    rows = policy(engine.r)["rows"]
    sources = actor.spec.get("state_grants", {}).get("sources", {})
    held = {row.get("registration_key"): row for row in HELD.entries(actor)}
    found = []
    for key, record in getattr(actor, "_item_reg", {}).items():
        row = rows.get(record.get("item_id"))
        if row is None or row["kind"] != kind or record.get("state_source") not in sources:
            continue
        uid = record.get("instance_id")
        slot = held.get(key)
        if uid is None or slot is None or slot.get("instance_id") != uid:
            continue
        obj = getattr(engine, "_physical_objects", {}).get(uid)
        if not isinstance(obj, dict) or obj.get("item_rule_id") != row["item_id"] or obj.get("equipped_by") != actor.entity_id:
            raise ValueError("held-item reaction registration and physical instance disagree")
        found.append((row, record))
    return found


def after_accuracy(engine, actor, target, move, hit, natural):
    """Install Blunder Policy only after the holder's actual accuracy miss."""
    if hit:
        return None
    active = _active(engine, actor, "blunder_policy")
    if not active:
        return None
    if not engine.encounter_active:
        raise ValueError("Blunder Policy encounter lifetime requires an active encounter")
    row, record = active[0]
    import frequency as FREQUENCY
    frequency = deepcopy(row["frequency"])
    key = "held-item-reaction:" + row["clause_id"]
    if not FREQUENCY.activation_allowed(actor, key, frequency, engine=engine):
        return {"triggered": False, "reason": "scene_frequency_spent"}
    effect = {
        "type": "initiative",
        "delta": row["initiative_bonus"],
        "target": "self",
        "duration": row["duration"],
    }
    import state_grants as GRANTS
    def apply(staged, owner):
        current = _active(staged, owner, "blunder_policy")
        if not current:
            raise ValueError("Blunder Policy physical source ended before commit")
        current_row, current_record = current[0]
        if not FREQUENCY.activation_allowed(owner, key, frequency, engine=staged):
            return {"triggered": False, "reason": "scene_frequency_spent"}
        import effect_contracts as CONTRACTS
        import effect_lifetimes as LIFETIMES
        occurrence, receipt = CONTRACTS.issue_receipt(staged, current_row["item_id"], owner, owner, effect, 0)
        LIFETIMES.install(staged, owner, owner, effect, current_row["item_id"], receipt, occurrence)
        FREQUENCY.consume_activation(owner, key, frequency, engine=staged)
        result = {
            "triggered": True,
            "clause_id": current_row["clause_id"],
            "instance_id": current_record["instance_id"],
            "effect_occurrence": occurrence,
            "move_id": move.get("id"),
            "natural": natural,
        }
        CONTRACTS.finish(staged, receipt, "completed", deepcopy(result))
        owner.spec.setdefault("held_item_reaction_history", []).append(deepcopy(result))
        staged.log("    허탕보험: 빗나감 → 인카운터 동안 이니셔티브 +10", current_row["item_id"])
        return result
    return GRANTS.transition(engine, actor, apply)


def after_hit(engine, attacker, target, move, dealt):
    """Apply Rocky Helmet after a positive-damage melee hit resolves."""
    if type(dealt) is not int or dealt <= 0 or move.get("class") not in ("물리", "특수") or "근접" not in str(move.get("range", "")):
        return None
    active = _active(engine, target, "rocky_helmet")
    if not active:
        return None
    row, record = active[0]
    loss = engine.tick_loss(attacker)
    engine.lose_hp(attacker, loss, source=row["item_id"])
    result = {"triggered": True, "clause_id": row["clause_id"], "instance_id": record["instance_id"], "hp_loss": loss, "move_id": move.get("id")}
    target.spec.setdefault("held_item_reaction_history", []).append(deepcopy(result))
    return result
