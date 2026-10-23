"""Triggered trainer-feature reactions to one native attack-damage application.

The damage resolver records immutable hit facts.  A trainer then explicitly
accepts or declines the offered Free Action before another top-level action can
begin.  Feature frequency and each printed per-target Scene limit stay in the
shared frequency ledger, while timed Frozen state uses the common lifetime
consumer.
"""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import re

import csv_item_physical_contracts as CSV_ITEMS
import frequency as FREQUENCY


POLICY_PATH = "data/class-actor-state-reactions-policy.json"
NATIVE_POLICY_PATH = "data/native-class-reaction-policy.json"
STATE = "_class_actor_state_reactions"

THIS_WILL_NOT_STAND = "feat/이건-버티지-못할걸"
ENDURING_BLOOM = "feat/인내의-개화"
DEEP_COLD = "feat/극심한-추위"

ALL_RULES = frozenset((THIS_WILL_NOT_STAND, ENDURING_BLOOM, DEEP_COLD))
CLAUSE_BY_RULE = {
    THIS_WILL_NOT_STAND: "C2CSV/input/db/feats.csv:R240:main",
    ENDURING_BLOOM: "C2CSV/input/db/feats.csv:R267:main",
    DEEP_COLD: "C2CSV/input/db/feats.csv:R276:main",
}
NATIVE_CLAUSE_BY_RULE = {
    THIS_WILL_NOT_STAND: "input/ch04-trainer-classes.md:1454-1458",
    DEEP_COLD: "input/ch04-trainer-classes.md:1701-1705",
}
ALIASES = {
    THIS_WILL_NOT_STAND: ("이건 버티지 못할걸", "This Will Not Stand"),
    ENDURING_BLOOM: ("인내의 개화", "Enduring Bloom"),
    DEEP_COLD: ("극심한 추위", "Deep Cold"),
}
COMBAT_STATS = frozenset(("atk", "def", "spa", "spd", "spe"))
ENDURING_TYPES = frozenset(("벌레", "불꽃", "비행", "얼음", "독", "Bug", "Fire", "Flying", "Ice", "Poison"))
ICE_TYPES = frozenset(("얼음", "Ice"))


def _key(value):
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value).casefold())


def identity(value):
    if not isinstance(value, str):
        return None
    normalized = _key(value)
    for rule_id, aliases in ALIASES.items():
        candidates = {_key(rule_id), _key(CLAUSE_BY_RULE[rule_id])}
        candidates.update(_key(alias) for alias in aliases)
        if normalized in candidates:
            return rule_id
    return None


def _policy_path(rules):
    canonical = Path(rules.root) / POLICY_PATH
    staged = Path(__file__).resolve().parent.parent / POLICY_PATH
    return canonical if canonical.is_file() else staged


def policy(rules):
    cached = getattr(rules, "_class_actor_state_reaction_policy", None)
    if cached is not None:
        return cached
    path = _policy_path(rules)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("contract") != "native attack damage trainer feature reactions":
        raise ValueError("unsupported class actor-state reaction policy")
    source_path = Path(rules.root) / data.get("source_file", "")
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != data.get("source_file_sha256"):
        raise ValueError("class actor-state reaction source changed")
    with source_path.open(encoding="utf-8-sig", newline="") as source_file:
        source_rows = list(csv.reader(source_file))
    clauses = data.get("clauses")
    if not isinstance(clauses, dict) or set(clauses) != set(CLAUSE_BY_RULE.values()):
        raise ValueError("class actor-state reaction policy needs the exact reviewed clauses")
    for rule_id, clause_id in CLAUSE_BY_RULE.items():
        row = clauses[clause_id]
        if row.get("id") != clause_id or row.get("rule_id") != rule_id:
            raise ValueError("class actor-state reaction identity changed: " + clause_id)
        record = row.get("source_record")
        if type(record) is not int or record < 1 or source_rows[record - 1] != row.get("source_cells"):
            raise ValueError("class actor-state reaction source row changed: " + clause_id)
    rules._class_actor_state_reaction_policy = data
    return data


def native_policy(rules):
    """Bind the two reviewed Markdown clauses to existing executable contracts."""
    cached = getattr(rules, "_native_class_actor_state_reaction_policy", None)
    if cached is not None:
        return cached
    path = Path(rules.root) / NATIVE_POLICY_PATH
    if not path.is_file():
        path = Path(__file__).resolve().parent.parent / NATIVE_POLICY_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or set(data.get("sources", {})) != set(NATIVE_CLAUSE_BY_RULE):
        raise ValueError("exact reviewed native reaction sources required")
    for uid, clause_id in NATIVE_CLAUSE_BY_RULE.items():
        row = data["sources"][uid]
        if (row.get("rule_id") != uid or row.get("clause_id") != clause_id
                or row.get("behavior_clause_id") != CLAUSE_BY_RULE[uid]):
            raise ValueError("native reaction source binding changed")
        source = Path(rules.root) / row["file"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != row["file_sha256"]:
            raise ValueError("native reaction source file changed")
        lines = source.read_text(encoding="utf-8").splitlines()
        excerpt = "\n".join(lines[row["start"] - 1:row["end"]])
        if hashlib.sha256(excerpt.encode("utf-8")).hexdigest() != row["excerpt_sha256"]:
            raise ValueError("native reaction source excerpt changed")
    rules._native_class_actor_state_reaction_policy = data
    return data


def _native_metadata(rules, rule_id, acquisition_source):
    if rule_id not in NATIVE_CLAUSE_BY_RULE or acquisition_source != rule_id:
        return {}
    row = native_policy(rules)["sources"][rule_id]
    return {"native_clause_id": row["clause_id"], "native_source_sha256": row["excerpt_sha256"]}


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
        raise ValueError("reaction feature requires exactly one acquired source: " + rule_id)
    source = matches[0]
    if trainer.r._selected_rule(source) != source:
        raise ValueError("selected feature variant requires its own reaction policy")
    policy(trainer.r)
    _native_metadata(trainer.r, rule_id, source)
    return source


def _state(actor, create=False):
    value = actor.spec.get(STATE)
    if value is None and create:
        value = {"version": 2, "serial": 0, "events": []}
        actor.spec[STATE] = value
    if value is None:
        return None
    if actor.kind != "trainer" or not isinstance(value, dict) or value.get("version") not in (1, 2):
        raise ValueError("class actor-state reactions belong to one trainer")
    if type(value.get("serial")) is not int or value["serial"] < 0 or not isinstance(value.get("events"), list):
        raise ValueError("invalid class actor-state reaction ledger")
    identities = set()
    required = {
        "id", "source", "clause_id", "owner_id", "subject_id", "target_id",
        "attacker_id", "move_id", "actual_type", "type_multiplier", "critical",
        "massive", "sunny", "damage_receipt", "round", "status", "result",
    }
    for event in value["events"]:
        metadata = {"acquisition_source", "native_clause_id", "native_source_sha256"}
        if (not isinstance(event, dict) or not required <= set(event)
                or set(event) - required - metadata):
            raise ValueError("invalid class actor-state reaction event")
        if value["version"] == 2 and "acquisition_source" not in event:
            raise ValueError("reaction needs its actual acquired source")
        if event["id"] in identities or not isinstance(event["id"], str) or not event["id"]:
            raise ValueError("reaction event identities must be distinct nonempty text")
        identities.add(event["id"])
        if event["source"] not in ALL_RULES or event["clause_id"] != CLAUSE_BY_RULE[event["source"]]:
            raise ValueError("reaction event source identity changed")
        if event["owner_id"] != actor.entity_id:
            raise ValueError("reaction event owner identity changed")
        if "acquisition_source" in event:
            source = event["acquisition_source"]
            if identity(source) != event["source"] or actor.r._selected_rule(source) != source:
                raise ValueError("reaction acquired source identity changed")
            expected = _native_metadata(actor.r, event["source"], source)
            actual = {key: event[key] for key in metadata - {"acquisition_source"} if key in event}
            if actual != expected:
                raise ValueError("reaction native source identity changed")
        elif {"native_clause_id", "native_source_sha256"} & set(event):
            raise ValueError("native reaction requires its acquired source identity")
        for field in ("owner_id", "subject_id", "target_id", "attacker_id", "move_id", "actual_type"):
            if not isinstance(event[field], str) or not event[field]:
                raise ValueError("reaction event needs actual identity facts")
        if type(event["type_multiplier"]) not in (int, float) or type(event["critical"]) is not bool:
            raise ValueError("reaction event hit facts are invalid")
        if type(event["massive"]) is not bool or type(event["sunny"]) is not bool:
            raise ValueError("reaction event trigger flags are invalid")
        if type(event["round"]) is not int or event["round"] < 0:
            raise ValueError("reaction event round is invalid")
        if event["status"] not in ("pending", "completed", "declined", "superseded"):
            raise ValueError("reaction event status is invalid")
        receipt = event["damage_receipt"]
        if not isinstance(receipt, dict) or not {"requested", "net_hp_loss", "net_temporary_hp_loss"} <= set(receipt):
            raise ValueError("reaction event needs an actual damage receipt")
        if any(type(receipt[field]) is not int for field in ("requested", "net_hp_loss", "net_temporary_hp_loss")):
            raise ValueError("reaction damage receipt values must be whole numbers")
        if 'native_damage' in receipt:
            __import__('combat_damage').validate_native_hit(receipt['native_damage'])
        if event["result"] is not None and not isinstance(event["result"], dict):
            raise ValueError("reaction result must be a mapping or null")
    return value


def validate(actor):
    _state(actor)
    return True


def validate_world(engine, index=None):
    """Validate preserved provenance and unresolved actual hit participants."""
    if index is None:
        index = _actor_index(engine)
    for actor in index.values():
        state = _state(actor)
        if state is None:
            continue
        for event in state["events"]:
            if event["status"] == "pending" and any(
                    uid not in index for uid in (event["subject_id"], event["target_id"], event["attacker_id"])):
                raise ValueError("pending reaction requires actual world participants")
    return True


def _actor_index(engine):
    import world_entities as WORLD
    return WORLD.actor_index(engine)


def _owner(engine, pokemon):
    index = _actor_index(engine)
    owner_id = pokemon.spec.get("trainer_id") if pokemon.kind == "pokemon" else None
    owner = index.get(owner_id)
    if not isinstance(owner_id, str) or owner is None or owner.kind != "trainer":
        return None
    if pokemon.spec.get("trainer") not in (None, owner.name):
        raise ValueError("Pokemon trainer name conflicts with its owner identity")
    return owner


def _target_key(engine, owner, target, rule_id):
    declaration = {"kind": "scene", "uses": 1, "scope": ["target"]}
    return FREQUENCY.declaration_key(engine, owner, target, rule_id, "triggered_free", declaration)


def _available(engine, owner, target, rule_id):
    row = policy(engine.r)["clauses"][CLAUSE_BY_RULE[rule_id]]
    return (
        FREQUENCY.activation_allowed(owner, rule_id, row["frequency"], engine=engine)
        and FREQUENCY.activation_allowed(
            owner,
            _target_key(engine, owner, target, rule_id),
            {"kind": "scene", "uses": 1},
            engine=engine,
        )
    )


def _actual_type(engine, event):
    actual = event.get("actual_damage_type")
    if isinstance(actual, str) and actual:
        return actual
    move = event["move"]
    move_mech = engine.r.move_mech(move["id"])[0]
    import effects_ext as EXT
    return EXT.effective_type(engine, event["attacker"], event["target"], move, move_mech)


def _massive(engine, target, receipt):
    facts = receipt.get('native_damage')
    return False if facts is None else __import__('combat_damage').validate_native_hit(facts)['massive']


def _offer(engine, owner, subject, target, event, receipt, rule_id, *, critical, massive, actual_type, multiplier):
    acquisition_source = acquired_source(owner, rule_id)
    if acquisition_source is None or not _available(engine, owner, target, rule_id):
        return None
    state = _state(owner, create=True)
    state["serial"] += 1
    event_id = "class-actor-reaction:" + owner.entity_id + ":" + str(state["serial"])
    row = {
        "id": event_id,
        "source": rule_id,
        "clause_id": CLAUSE_BY_RULE[rule_id],
        "owner_id": owner.entity_id,
        "subject_id": subject.entity_id,
        "target_id": target.entity_id,
        "attacker_id": event["attacker"].entity_id,
        "move_id": event["move"]["id"],
        "actual_type": actual_type,
        "type_multiplier": multiplier,
        "critical": critical,
        "massive": massive,
        "sunny": __import__("effects").effective_weather(engine, subject) == "sunny",
        "damage_receipt": deepcopy(receipt),
        "round": engine.round_no,
        "status": "pending",
        "result": None,
        "acquisition_source": acquisition_source,
        **_native_metadata(engine.r, rule_id, acquisition_source),
    }
    state["events"].append(row)
    engine.log("    선택 대기: " + policy(engine.r)["clauses"][CLAUSE_BY_RULE[rule_id]]["name"], rule_id)
    return event_id


def observe_attack_damage(engine, event, receipt, *, critical):
    """Offer every exact eligible reaction from one committed attack hit."""
    if type(critical) is not bool or not event.get("damage_applied"):
        raise ValueError("committed native attack evidence required")
    if not isinstance(receipt, dict) or event.get("attacker") is None or event.get("target") is None:
        raise ValueError("actual attack participants and damage receipt required")
    attacker = event["attacker"]
    target = event["target"]
    move = event["move"]
    if move.get("class") not in ("물리", "특수"):
        return ()
    actual_type = _actual_type(engine, event)
    multiplier = event.get("damage_formula", {}).get("multiplier", 0)
    offered = []

    defending_owner = _owner(engine, target)
    massive = _massive(engine, target, receipt)
    if defending_owner is not None and any(kind in ("드래곤", "Dragon") for kind in target.types):
        # Adopted errata p8 replaces the printed critical/massive trigger with the actual
        # above-half HP crossing owned by type_ace.hp_changed for receipted Type Ace owners.
        # Legacy feats-list-only owners keep this pre-errata offer (documented limit).
        if (critical or massive) and not __import__('type_ace').hp_interested(engine, target):
            offered.append(_offer(
                engine,
                defending_owner,
                target,
                target,
                event,
                receipt,
                THIS_WILL_NOT_STAND,
                critical=critical,
                massive=massive,
                actual_type=actual_type,
                multiplier=multiplier,
            ))
    if defending_owner is not None and any(kind in ("풀", "Grass") for kind in target.types):
        if actual_type in ENDURING_TYPES and multiplier > 1:
            offered.append(_offer(
                engine,
                defending_owner,
                target,
                target,
                event,
                receipt,
                ENDURING_BLOOM,
                critical=critical,
                massive=massive,
                actual_type=actual_type,
                multiplier=multiplier,
            ))

    attacking_owner = _owner(engine, attacker)
    if attacking_owner is not None and actual_type in ICE_TYPES:
        offered.append(_offer(
            engine,
            attacking_owner,
            attacker,
            target,
            event,
            receipt,
            DEEP_COLD,
            critical=critical,
            massive=massive,
            actual_type=actual_type,
            multiplier=multiplier,
        ))
    return tuple(event_id for event_id in offered if event_id is not None)


def pending(engine, trainer):
    index = _actor_index(engine)
    if index.get(trainer.entity_id) is not trainer:
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
            raise ValueError("triggered class Free Action must be accepted or declined before another action")


def _find_event(owner, event_id):
    state = _state(owner)
    if state is None:
        raise ValueError("unknown class actor-state reaction")
    matches = [event for event in state["events"] if event["id"] == event_id]
    if len(matches) != 1 or matches[0]["status"] != "pending":
        raise ValueError("pending class actor-state reaction required")
    return matches[0]


def _stats_for(event, stats):
    if not isinstance(stats, (list, tuple)) or any(stat not in COMBAT_STATS for stat in stats):
        raise ValueError("reaction stats must be explicit combat-stat identifiers")
    stats = tuple(stats)
    if len(set(stats)) != len(stats):
        raise ValueError("reaction stat choices must be distinct")
    if event["source"] == ENDURING_BLOOM:
        maximum = 2 if event["sunny"] else 1
        if len(stats) < 1 or len(stats) > maximum:
            raise ValueError("Enduring Bloom needs one stat, with one optional different Sunny stat")
    elif stats:
        raise ValueError("this reaction has no selectable combat stat")
    return stats


def _apply_effect(engine, owner, event, actors, stats):
    source = event["source"]
    subject = actors[event["subject_id"]]
    target = actors[event["target_id"]]
    result = {"source": source, "clause_id": event["clause_id"], "event_id": event["id"]}
    result.update({key: event[key] for key in ("acquisition_source", "native_clause_id", "native_source_sha256")
                   if key in event})
    if source == THIS_WILL_NOT_STAND:
        before = {stat: subject.stages[stat] for stat in ("atk", "spa", "spe")}
        for stat in ("atk", "spa", "spe"):
            engine.change_stage(subject, stat, 1)
        result["stage_changes"] = {stat: subject.stages[stat] - before[stat] for stat in before}
    elif source == ENDURING_BLOOM:
        import class_passive_combat as CLASS_PASSIVE
        import temporary_hp as TEMP_HP
        rank = CLASS_PASSIVE.type_link_rank(engine, owner, "풀")
        granted = TEMP_HP.grant(
            engine,
            subject,
            2 * rank,
            provenance={"source": source, "event_id": event["id"], "owner_id": owner.entity_id},
        )
        before = {stat: subject.stages[stat] for stat in stats}
        for stat in stats:
            engine.change_stage(subject, stat, 1)
        result.update(
            type_link_rank=rank,
            temporary_hp_granted=granted,
            stage_changes={stat: subject.stages[stat] - before[stat] for stat in before},
        )
    elif source == DEEP_COLD:
        import effect_lifetimes as LIFETIMES
        before = {stat: target.stages[stat] for stat in ("atk", "spa", "spe")}
        effect = {"type": "apply_status", "status": "얼음", "target": "target", "duration": "1라운드"}
        LIFETIMES.install(engine, owner, target, effect, source, None, event["id"])
        import effects as FX
        FX.apply_stage_changes(engine, owner, target,
            dict.fromkeys(("atk", "spa", "spe"), -1), source_id=source)
        result.update(
            frozen="얼음" in target.conditions,
            frozen_duration="1라운드",
            stage_changes={stat: target.stages[stat] - before[stat] for stat in before},
        )
    else:
        raise ValueError("unsupported class actor-state reaction source")
    return result


def _close_unavailable(engine, owner, actors):
    state = _state(owner)
    for event in state["events"]:
        if event["status"] != "pending":
            continue
        target = actors.get(event["target_id"])
        if target is None or not _available(engine, owner, target, event["source"]):
            event["status"] = "superseded"
            event["result"] = {"used": False, "reason": "frequency_or_target_scene_limit_spent"}


def resolve(engine, trainer, event_id, *, use, stats=()):
    if type(use) is not bool:
        raise ValueError("reaction decision must be explicit")
    index = _actor_index(engine)
    if index.get(trainer.entity_id) is not trainer or trainer.kind != "trainer":
        raise ValueError("actual registered trainer required")

    import state_grants as GRANTS

    def apply(staged_engine, staged_owner):
        actors = _actor_index(staged_engine)
        event = _find_event(staged_owner, event_id)
        if not use:
            if stats:
                raise ValueError("declined reaction cannot include effect choices")
            event["status"] = "declined"
            event["result"] = {"used": False}
            return deepcopy(event["result"])
        selected_stats = _stats_for(event, stats)
        if acquired_source(staged_owner, event["source"]) is None:
            raise ValueError("reaction feature acquisition ended before use")
        subject = actors.get(event["subject_id"])
        target = actors.get(event["target_id"])
        attacker = actors.get(event["attacker_id"])
        if subject is None or target is None or attacker is None:
            raise ValueError("reaction participants must remain actual world actors")
        if _owner(staged_engine, subject) is not staged_owner:
            raise ValueError("reaction subject ownership changed")
        if not _available(staged_engine, staged_owner, target, event["source"]):
            raise ValueError("reaction frequency or target Scene limit is spent")
        import action_lifecycle as ACTION
        ACTION.triggered_free_action(staged_engine, staged_owner, event["source"])
        result = _apply_effect(staged_engine, staged_owner, event, actors, selected_stats)
        clause = policy(staged_engine.r)["clauses"][event["clause_id"]]
        FREQUENCY.consume_activation(staged_owner, event["source"], clause["frequency"], engine=staged_engine)
        target_key = _target_key(staged_engine, staged_owner, target, event["source"])
        FREQUENCY.consume_activation(
            staged_owner,
            target_key,
            {"kind": "scene", "uses": 1},
            engine=staged_engine,
        )
        event["status"] = "completed"
        event["result"] = dict(result, used=True)
        _close_unavailable(staged_engine, staged_owner, actors)
        return deepcopy(event["result"])

    return GRANTS.transition(engine, trainer, apply)
