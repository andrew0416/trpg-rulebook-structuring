"""Exact CSV91 Decisive Director over native action, initiative and lifetime owners."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import csv
import json

SOURCE = "C2CSV/input/db/feats.csv:R91:main"
FEATURE = "feat/결단력-있는-감독자"
CLASS = "class/코디네이터"
NAME = "결단력 있는 감독자"
KEY = "directive_activation"
CSV_SHA = "4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd"
CELL_SHA = "9ed8a1bd7a2007e279afc845c6464d44bd9c6d648706bcf3a642f34a731d2c27"
UNTIL = {"event": "turn_end", "owner": "target", "after": 1}


if __package__:
    from . import resolution_transaction as _FINGERPRINTS
else:
    import resolution_transaction as _FINGERPRINTS

def _digest(value):
    return _FINGERPRINTS.json_fingerprint(value, sort_keys=True, compact=True, allow_nan=True)


def definition(rules):
    # No Rules-instance cache: a warm parse is not a source certificate.
    data = json.loads((Path(rules.root) / "data/directive-features-policy.json").read_text(encoding="utf-8"))
    expected = {"schema": "directive-features-v1", "source_id": SOURCE,
                "feature_id": FEATURE, "name": NAME, "required_class": CLASS,
                "frequency": {"kind": "at_will", "action": "standard"},
                "target": "one_pokemon",
                "formula": {"skill": "매력", "factor": 2,
                            "adjustments": ["increase", "decrease"]}, "until": UNTIL}
    if set(data) != set(expected) | {"source"} or any(data.get(k) != v for k, v in expected.items()):
        raise ValueError("reviewed Decisive Director definition changed")
    ref = data["source"]
    if (set(ref) != {"file", "sha256", "record", "cells_sha256", "cells"} or
            (ref["file"], ref["sha256"], ref["record"], ref["cells_sha256"]) !=
            ("input/db/feats.csv", CSV_SHA, 91, CELL_SHA)):
        raise ValueError("exact CSV91 source reference required")
    path = Path(rules.root) / ref["file"]
    if sha256(path.read_bytes()).hexdigest() != CSV_SHA:
        raise ValueError("CSV91 source bytes changed")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        cells = list(csv.reader(stream))[90]
    cell_hash = _FINGERPRINTS.json_fingerprint(cells, sort_keys=False, compact=True, allow_nan=True)
    if cell_hash != CELL_SHA or cells != ref["cells"]:
        raise ValueError("exact CSV91 cells changed")
    for uid in (SOURCE, FEATURE):
        if rules._selected_rule(uid) != uid or uid in rules.ruleset.unit_versions:
            raise ValueError("CSV91 requires its exact selected source")
        unit = rules.selection.units[uid]
        origin = unit["source"]
        if (unit["title"] != NAME or origin.get("file") != "db/feats.csv" or
                origin.get("record_span") != [91, 91] or origin.get("sha256") != CSV_SHA):
            raise ValueError("CSV91 selected catalog identity changed")
    if rules._selected_rule(CLASS) != CLASS:
        raise ValueError("selected Coordinator Class required")
    return deepcopy(data)


def identity(name):
    return FEATURE if name in (FEATURE, SOURCE, NAME) else None


def _owned(engine, actor):
    import contest_features as FEATURES
    FEATURES.conscious_trainer(actor)
    FEATURES.require(engine, actor, FEATURE)
    FEATURES.require(engine, actor, CLASS)


def register_owned(engine, actor, name):
    if identity(name) is None:
        return False
    definition(engine.r)
    # Registration projects acquired references; it does not execute the action.
    import contest_features as FEATURES
    FEATURES.require(engine, actor, FEATURE)
    FEATURES.require(engine, actor, CLASS)
    return True


def _effect(rank, adjustment):
    if type(rank) is not int or rank < 1:
        raise ValueError("actual effective Charm rank required")
    if type(adjustment) is not str or adjustment not in ("increase", "decrease"):
        raise ValueError("explicit increase or decrease adjustment required")
    return {"type": "initiative", "delta": 2 * rank * (1 if adjustment == "increase" else -1),
            "target": "target", "until": deepcopy(UNTIL)}


import cheerleader as CHEER

@CHEER.order_activation('C2CSV/input/db/feats.csv:R91:main')
def activate(engine, actor, target, *, adjustment, communication=None):
    import world_entities as W
    import state_grants as G
    W.require_actors(engine, actor, target)

    def apply(e, user, recipient):
        import skill_modifiers as SKILL
        import frequency as FREQ
        import turn as TURN
        import effects as FX
        definition(e.r)
        _owned(e, user)
        if recipient.kind != "pokemon":
            raise ValueError("Decisive Director requires one actual Pokemon")
        rank = SKILL.effective_rank(e.r, user, "매력")
        effect = _effect(rank, adjustment)
        if not e.encounter_active:
            raise ValueError("target next-turn lifetime requires an active encounter")
        if not FREQ.activation_allowed(user, SOURCE, {"kind": "at_will"}, engine=e):
            raise ValueError("Decisive Director frequency unavailable")
        import order_actions as ORDERS
        delivery=ORDERS.delivery(e,user,recipient,FEATURE,communication=communication)
        paid=ORDERS.spend(e,user,FEATURE,subject=recipient.entity_id,communication=delivery)
        order_payment=ORDERS.payment(e,user,FEATURE)
        priority=paid if paid.get("kind")=="priority_limited" else None
        plan = {"source_id": SOURCE, "feature_id": FEATURE, "class_id": CLASS,
                "actor_id": user.entity_id, "target_id": recipient.entity_id,
                "charm_rank": rank, "adjustment": adjustment,
                "round": e.round_no, "at": e.elapsed_seconds,
                "actor_turn": user.custom_conditions.get("combat_turn_serial", 0),
                "target_turn": recipient.custom_conditions.get("combat_turn_serial", 0),
                "action": "priority_limited" if priority else "free" if order_payment else "standard",
                 "history_index": None if priority else len(user._action_history) - 1,
                "acquired": [FEATURE, CLASS]}
        if order_payment:plan['free_order_payment']=order_payment
        if priority:plan['priority_receipt_id']=priority['id']
        # This unconditional feature applies no accuracy roll and accepts no hit
        # input. True is only the existing nonattack dispatcher application context.
        result = FX.run_effects(e, user, recipient, [effect],
                               {"attacker": user, "target": recipient, "hit": True,
                                "nat": None, "engine": e}, SOURCE)
        if tuple(result) != (1, 0) or len(result.outcomes) != 1:
            raise ValueError("Decisive Director native effect did not complete")
        outcome = result.outcomes[0]
        if outcome.status != "completed":
            raise ValueError("completed native directive receipt required")
        row = e._effect_dispatch_receipts[outcome.receipt]
        row[KEY] = {"plan": plan, "integrity": _digest(plan)}
        FREQ.consume_activation(user, SOURCE, {"kind": "at_will"}, engine=e)
        validate_world(e, W.actor_index(e))
        return {"source": SOURCE, "occurrence": outcome.occurrence,
                "receipt": outcome.receipt, "delta": effect["delta"],
                "actor_id": user.entity_id, "target_id": recipient.entity_id}
    return G.transition(engine, actor, apply, participants=(target,))


def validate_world(engine, index):
    """Historical paid declarations, not live reacquisition/rank evaluation."""
    rows = [(token, row) for token, row in getattr(engine, "_effect_dispatch_receipts", {}).items()
            if row.get("source_id") == SOURCE or KEY in row]
    if not rows:
        return True
    import effect_contracts as CONTRACTS
    import combat_timing as TIME
    definition(engine.r)
    for token, row in rows:
        meta = row.get(KEY)
        if type(meta) is not dict or set(meta) != {"plan", "integrity"}:
            raise ValueError("CSV91 requires its source-owned paid activation")
        plan = meta["plan"]
        fields = {"source_id", "feature_id", "class_id", "actor_id", "target_id",
                  "charm_rank", "adjustment", "round", "at", "actor_turn",
                  "target_turn", "action", "history_index", "acquired"}
        if 'free_order_payment' in plan:fields.add('free_order_payment')
        if 'priority_receipt_id' in plan:fields.add('priority_receipt_id')
        if type(plan) is not dict or set(plan) != fields or meta["integrity"] != _digest(plan):
            raise ValueError("CSV91 historical activation changed")
        actor, target = row.get("actor"), row.get("target")
        if (actor is None or target is None or index.get(actor.entity_id) is not actor or
                index.get(target.entity_id) is not target or actor.kind != "trainer" or
                target.kind != "pokemon" or plan["actor_id"] != actor.entity_id or
                plan["target_id"] != target.entity_id):
            raise ValueError("CSV91 activation actor/recipient identity changed")
        priority='priority_receipt_id' in plan
        if (plan["source_id"], plan["feature_id"], plan["class_id"], plan["action"],
                plan["acquired"]) != (SOURCE, FEATURE, CLASS, "priority_limited" if priority else "free" if 'free_order_payment' in plan else "standard", [FEATURE, CLASS]):
            raise ValueError("CSV91 acquisition/source/action proof changed")
        if 'free_order_payment' in plan:
            import order_actions as ORDERS
            ORDERS.validate(engine,actor,target,FEATURE,plan['free_order_payment'])
        if priority:
            import priority_limited as PRIORITY
            paid=[p for p in PRIORITY.records(actor) if p["id"]==plan["priority_receipt_id"]]
            if (len(paid)!=1 or paid[0]["source"]!=FEATURE or paid[0]["subject_id"]!=target.entity_id
                    or paid[0]["payment"]["funded"]!={"standard":1} or plan["history_index"] is not None):
                raise ValueError("CSV91 native Standard reservation changed")
        for key in ("round", "at", "actor_turn", "target_turn") + (() if priority else ("history_index",)):
            if type(plan[key]) is not int or plan[key] < (1 if key=="round" or key=="actor_turn" and not priority else 0):
                raise ValueError("CSV91 actual action boundary required")
        if (plan["round"] > engine.round_no or plan["at"] > engine.elapsed_seconds or
                plan["actor_turn"] > actor.custom_conditions.get("combat_turn_serial", 0) or
                plan["target_turn"] > target.custom_conditions.get("combat_turn_serial", 0)):
            raise ValueError("CSV91 action boundary is in the future")
        effect = _effect(plan["charm_rank"], plan["adjustment"])
        if row.get("source_id") != SOURCE or row.get("effect") != effect or row.get("status") != "completed":
            raise ValueError("CSV91 actual effect differs from its admitted declaration")
        CONTRACTS.validate_receipt(engine, token, SOURCE, row["occurrence"], actor, target, effect)
        contract = row.get("lifetime_contracts", {}).get(target.entity_id)
        expected_turns = {"user": plan["actor_turn"], "target": plan["target_turn"]}
        if (type(contract) is not dict or contract.get("contribution") !=
                {"initiative_operation": {"operation": "add", "value": effect["delta"]}}):
            raise ValueError("CSV91 lifetime contribution changed")
        life = contract["policy"]
        if (life["declaration"] != {"until": UNTIL} or life["until"] != UNTIL or
                life["started_at"] != plan["at"] or life["started_round"] != plan["round"] or
                life["started_turns"] != expected_turns):
            raise ValueError("CSV91 lifetime differs from its paid target-turn declaration")
        current_turn = actor.custom_conditions.get("combat_turn_serial", 0)
        if not priority and current_turn == plan["actor_turn"] and engine.round_no == plan["round"]:
            history = getattr(actor, "_action_history", [])
            at = plan["history_index"]
            if at >= len(history) or history[at] != plan['action']:
                raise ValueError("CSV91 native Standard payment history changed")
        live = [record for holder in index.values() for record in TIME.records(holder) if record.get("effect_receipt") is token]
        ended = [record for holder in index.values() for record in holder.custom_conditions.get("effect_lifetime_history", [])
                 if record.get("receipt") is token]
        if len(live) + len(ended) != 1:
            raise ValueError("CSV91 effect occurrence lost or duplicated its lifetime")
        import native_order_transfer as TRANSFER
        actual = TRANSFER.original_policy(live[0] if live else ended[0])
        if actual != life:
            raise ValueError("CSV91 lifetime record differs from its original producer")
    return True

