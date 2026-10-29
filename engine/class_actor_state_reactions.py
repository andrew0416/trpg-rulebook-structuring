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
DEEP_QUOTA = "_deep_cold_target_scene_quota"

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
        metadata = {"acquisition_source", "native_clause_id", "native_source_sha256", "native_event_id", "completion_id", "native_origin_version"}
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
            actual = {key: event[key] for key in metadata - {"acquisition_source", "native_event_id", "completion_id", "native_origin_version"} if key in event}
            if actual != expected:
                raise ValueError("reaction native source identity changed")
        elif {"native_clause_id", "native_source_sha256"} & set(event):
            raise ValueError("native reaction requires its acquired source identity")
        native_fields={'native_event_id','completion_id'} & set(event)
        if native_fields and native_fields!={'native_event_id','completion_id'}:raise ValueError('paired native damage event/completion identity required')
        if native_fields and any(type(event[key]) is not str or not event[key] for key in native_fields):raise ValueError('actual native damage identity required')
        if 'native_origin_version' in event and (type(event['native_origin_version']) is not int or event['native_origin_version']!=1 or not native_fields):
            raise ValueError('issued native class reaction origin version required')
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
        result = event["result"] or {}
        if "target_scene_quota" in result:
            proof = result["target_scene_quota"]
            if (event["source"] != DEEP_COLD or event["status"] != "completed" or result.get("used") is not True
                    or not isinstance(proof, dict) or proof.get("source") != _deep_source(actor.r)
                    or proof.get("target_id") != event["target_id"]
                    or proof.get("feature_owner_id") != actor.entity_id or proof.get("event_id") != event["id"]):
                raise ValueError("Deep Cold completed result requires its actual target quota receipt")
    return value


def validate(actor):
    _state(actor)
    _deep_quota_state(actor)
    return True


def _validate_native_offer_links(engine, index=None):
    """Modern issuance cannot become a legacy offer by deleting its row metadata."""
    native_events=[native for native in getattr(engine,'_passive_events',{}).values()
                   if 'class_actor_reaction_offers' in native]
    if not native_events:return
    if index is None:index=_actor_index(engine)
    owners={}
    for native in native_events:
        offers=native['class_actor_reaction_offers']
        if type(offers) is not dict:raise ValueError('actual issued native occurrence mapping required')
        if native['phase']=='producer_return_boundary':
            if 'intent_fingerprint' not in native:raise ValueError('native class reaction occurrence seal missing')
            __import__('passive_events')._bind_intent(engine,native)
        for identity,facts in offers.items():
            if type(identity) is not str or type(facts) is not dict:
                raise ValueError('actual issued native occurrence facts required')
            owner_id=facts.get('owner_id');owner=index.get(owner_id)
            # Existing world traversal retains off-field referenced actors.
            # A fully detached historical owner cannot execute this offer and
            # is not recreated or rejected merely from the retained event.
            if owner is None:continue
            if owner_id not in owners:
                state=_state(owner)
                owners[owner_id]={row['id']:row for row in state['events']} if state is not None else {}
            row=owners[owner_id].get(identity)
            if (row is None or row.get('native_origin_version')!=1
                    or row.get('native_event_id')!=native['id']
                    or row.get('completion_id')!=native['completion_id']
                    or _native_offer_facts(row)!=facts):
                raise ValueError('actual issued native occurrence cannot lose its owner record or origin')



def validate_world(engine, index=None):
    """Validate preserved provenance and unresolved actual hit participants."""
    if index is None:
        index = _actor_index(engine)
    for actor in index.values():
        quota = _deep_quota_state(actor)
        if quota is not None and any(row["at"] > engine.elapsed_seconds
                                     for row in quota["adoptions"] + quota["uses"]):
            raise ValueError("Deep Cold target quota receipt cannot be in the future")
        if quota is not None and any(row["key"] != _target_key(engine, actor, actor, DEEP_COLD)
                                     for row in quota["uses"]):
            raise ValueError("Deep Cold use requires the existing exact target frequency key")
        state = _state(actor)
        if state is None:
            continue
        for event in state["events"]:
            native_completion(engine,event)
            if event["status"] == "pending" and any(
                    uid not in index for uid in (event["subject_id"], event["target_id"], event["attacker_id"])):
                raise ValueError("pending reaction requires actual world participants")
            proof = (event["result"] or {}).get("target_scene_quota")
            if proof is not None and event["target_id"] in index:
                target_quota = _deep_quota_state(index[event["target_id"]])
                if target_quota is None or proof not in target_quota["uses"]:
                    raise ValueError("completed Deep Cold target quota receipt is missing")
    _validate_native_offer_links(engine,index)
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


def _fingerprint(value):
    # Native damage evidence contains finite type multipliers (including 0.5).
    # Hash its existing JSON representation, not the integer-only request DSL.
    import resolution_transaction as TX
    return TX.json_fingerprint(value, allow_nan=False)


def _deep_source(rules):
    csv_source = policy(rules)
    native = native_policy(rules)["sources"][DEEP_COLD]
    return {"rule_id": DEEP_COLD, "clause_id": CLAUSE_BY_RULE[DEEP_COLD],
            "csv_sha256": csv_source["source_file_sha256"],
            "native_clause_id": native["clause_id"], "native_sha256": native["excerpt_sha256"]}


def _deep_quota_state(target, create=False):
    value = target.spec.get(DEEP_QUOTA)
    if value is None and create:
        value = {"version": 1, "adoptions": [], "uses": []}
        target.spec[DEEP_QUOTA] = value
    if value is None:
        return None
    FREQUENCY.validate(target)
    scene = target.spec.get("frequency_state", {}).get("scene", 0)
    if (not isinstance(value, dict) or set(value) != {"version", "adoptions", "uses"}
            or value["version"] != 1 or type(value["adoptions"]) is not list or type(value["uses"]) is not list):
        raise ValueError("invalid Deep Cold target quota receipts")
    scopes = set()
    events = set()
    used_scenes = set()
    for row in value["adoptions"] + value["uses"]:
        if (not isinstance(row, dict) or row.get("source") != _deep_source(target.r)
                or row.get("target_id") != target.entity_id
                or type(row.get("scene")) is not int or not 0 <= row["scene"] <= scene
                or type(row.get("at")) is not int or row["at"] < 0):
            raise ValueError("Deep Cold quota requires actual source, target, Scene and time")
    for row in value["adoptions"]:
        if (set(row) != {"source", "target_id", "scene", "at", "scope", "evidence", "used", "reason"}
                or type(row["used"]) is not int or row["used"] not in (0, 1)
                or type(row["reason"]) is not str or not row["reason"].strip()
                or type(row["evidence"]) is not list or not row["evidence"]
                or type(row["scope"]) is not dict
                or set(row["scope"]) != {"source", "target_id", "target_scene", "legacy_evidence_hash", "target_quota_hash"}
                or row["scope"].get("source") != row["source"]
                or row["scope"].get("target_id") != row["target_id"]
                or row["scope"].get("target_scene") != row["scene"]
                or row["scope"].get("legacy_evidence_hash") != _fingerprint(row["evidence"])
                or type(row["scope"].get("target_quota_hash")) is not str
                or re.fullmatch(r"[0-9a-f]{64}", row["scope"]["target_quota_hash"]) is None):
            raise ValueError("Deep Cold adoption needs its exact current observation")
        identity = _fingerprint(row["scope"])
        if identity in scopes:
            raise ValueError("duplicate Deep Cold quota observation")
        scopes.add(identity)
    for row in value["uses"]:
        if (set(row) != {"source", "target_id", "scene", "at", "feature_owner_id", "key", "event_id"}
                or any(type(row[key]) is not str or not row[key] for key in ("feature_owner_id", "key", "event_id"))
                or row["event_id"] in events or row["scene"] in used_scenes):
            raise ValueError("Deep Cold use needs its actual target quota receipt")
        events.add(row["event_id"])
        used_scenes.add(row["scene"])
    return value


def _deep_legacy_evidence(engine, target, key):
    evidence = []
    for owner in sorted(_actor_index(engine).values(), key=lambda actor: actor.entity_id):
        FREQUENCY.validate(owner)
        old = owner.spec.get("frequency_state", {}).get("activations", {}).get(key)
        if owner is not target and old is not None and old.get("kind") == "scene" and old["used"]:
            evidence.append({"kind": "owner_quota", "owner_id": owner.entity_id, "key": key, "row": deepcopy(old)})
        state = _state(owner)
        for event in state["events"] if state is not None else ():
            if (event["source"] == DEEP_COLD and event["target_id"] == target.entity_id
                    and event["status"] == "completed" and isinstance(event["result"], dict)
                    and event["result"].get("used") is True
                    and "target_scene_quota" not in event["result"]):
                evidence.append({"kind": "owner_event", "owner_id": owner.entity_id, "event": deepcopy(event)})
    return evidence


def deep_cold_target_quota(engine, target):
    """Read the actual target Scene; old owner counters cannot identify it."""
    if _actor_index(engine).get(target.entity_id) is not target:
        raise ValueError("actual registered Deep Cold target required")
    FREQUENCY.validate(target)
    key = _target_key(engine, target, target, DEEP_COLD)
    calendar = target.spec.get("frequency_state", {})
    scene = calendar.get("scene", 0)
    row = calendar.get("activations", {}).get(key)
    state = _deep_quota_state(target) or {"version": 1, "adoptions": [], "uses": []}
    spent = bool(row and row["kind"] == "scene" and row["period"] == scene and row["used"])
    spent = spent or any(receipt["scene"] == scene for receipt in state["uses"])
    spent = spent or any(receipt["scene"] == scene and receipt["used"] == 1 for receipt in state["adoptions"])
    evidence = _deep_legacy_evidence(engine, target, key)
    covered = {_fingerprint(item) for receipt in state["adoptions"] for item in receipt["evidence"]}
    unbound = any(_fingerprint(item) not in covered for item in evidence)
    status = "spent" if spent else "observation_required" if unbound else "available"
    scope = {"source": _deep_source(engine.r), "target_id": target.entity_id, "target_scene": scene,
             "legacy_evidence_hash": _fingerprint(evidence),
             "target_quota_hash": _fingerprint({"row": row, "receipts": state})}
    return {"status": status, "scope": scope, "evidence": evidence, "key": key}


def _close_deep_target(engine, target):
    for owner in _actor_index(engine).values():
        state = _state(owner)
        for event in state["events"] if state is not None else ():
            if event["status"] == "pending" and event["source"] == DEEP_COLD and event["target_id"] == target.entity_id:
                event["status"] = "superseded"
                event["result"] = {"used": False, "reason": "target_scene_limit_spent"}


def observe_deep_cold_target_quota(engine, target, *, used, scope, reason):
    """Adopt a GM observation of the current quota, preserving legacy history."""
    if type(used) is not int or used not in (0, 1):
        raise ValueError("Deep Cold current quota observation must be integer 0 or 1")
    if type(reason) is not str or not reason.strip():
        raise ValueError("Deep Cold current quota observation reason required")
    current = deep_cold_target_quota(engine, target)
    if current["status"] != "observation_required" or scope != current["scope"]:
        raise ValueError("fresh scoped Deep Cold current quota observation required")
    import state_grants as GRANTS

    def commit(e, actual):
        before = deep_cold_target_quota(e, actual)
        if before["status"] != "observation_required" or scope != before["scope"]:
            raise ValueError("fresh scoped Deep Cold current quota observation required")
        receipt = {"source": deepcopy(scope["source"]), "target_id": actual.entity_id,
                   "scene": scope["target_scene"], "at": e.elapsed_seconds,
                   "scope": deepcopy(scope), "evidence": before["evidence"], "used": used, "reason": reason}
        _deep_quota_state(actual, create=True)["adoptions"].append(receipt)
        FREQUENCY.state(actual)["activations"][before["key"]] = {
            "kind": "scene", "period": scope["target_scene"], "used": used}
        if used:
            _close_deep_target(e, actual)
        e.gm._rec("현재 극심한 추위 대상 장면 횟수 관측", before, receipt, reason, who=actual)
        return deepcopy(receipt)

    return GRANTS.transition(engine, target, commit, include_rulings=True)


def _available(engine, owner, target, rule_id):
    row = policy(engine.r)["clauses"][CLAUSE_BY_RULE[rule_id]]
    if rule_id == DEEP_COLD:
        if not FREQUENCY.activation_allowed(owner, rule_id, row["frequency"], engine=engine):
            return False
        status = deep_cold_target_quota(engine, target)["status"]
        return None if status == "observation_required" else status == "available"
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
    if acquisition_source is None or _available(engine, owner, target, rule_id) is False:
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
        "sunny": "sunny" in __import__("weather_state").effective_weathers(engine, subject, include_virtual=False),
        "damage_receipt": deepcopy(receipt),
        "round": engine.round_no,
        "status": "pending",
        "result": None,
        "acquisition_source": acquisition_source,
        **_native_metadata(engine.r, rule_id, acquisition_source),
    }
    native=getattr(engine,'_passive_events',{}).get(event.get('passive_event'))
    if native is not None:
        row.update(native_event_id=native['id'],completion_id=native['completion_id'])
        native_completion(engine,row)
        offers=native.setdefault('class_actor_reaction_offers',{})
        if type(offers) is not dict or row['id'] in offers:
            raise ValueError('one actual native occurrence per class reaction offer required')
        row['native_origin_version']=1
        offers[row['id']]=_native_offer_facts(row)
        native_completion(engine,row)
    state["events"].append(row)
    engine.log("    선택 대기: " + policy(engine.r)["clauses"][CLAUSE_BY_RULE[rule_id]]["name"], rule_id)
    return event_id


def interested(engine, attacker, target, move):
    """Retain the real activation before a class-owned damage reaction can occur."""
    if move.get('class') not in ('물리','특수'):
        return False
    defender = _owner(engine, target) if target is not None and target.kind=='pokemon' else None
    if defender is not None and acquired_source(defender, ENDURING_BLOOM) is not None:
        return True
    owner = _owner(engine, attacker) if attacker.kind=='pokemon' else None
    return owner is not None and acquired_source(owner, DEEP_COLD) is not None


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
    # User-adopted This Will Not Stand is owned by the actual HP-crossing leaf in
    # type_ace for both receipted and source-authenticated imported feat owners.
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
    result = []
    for event in state["events"]:
        if event["status"] != "pending":
            continue
        copy = deepcopy(event)
        if event["source"] == DEEP_COLD:
            copy["target_scene_quota"] = deep_cold_target_quota(engine, index[event["target_id"]])
        result.append(copy)
    return tuple(result)


def ensure_clear(engine):
    if getattr(engine, "_native_move_resolution_depth", 0):
        return
    index=_actor_index(engine)
    _validate_native_offer_links(engine,index)
    for actor in index.values():
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
        if target is None or _available(engine, owner, target, event["source"]) is False:
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
        available = _available(staged_engine, staged_owner, target, event["source"])
        if available is None:
            raise ValueError("Deep Cold target Scene quota requires a current scoped GM observation")
        if not available:
            raise ValueError("reaction frequency or target Scene limit is spent")
        import action_lifecycle as ACTION
        ACTION.triggered_free_action(staged_engine, staged_owner, event["source"])
        result = _apply_effect(staged_engine, staged_owner, event, actors, selected_stats)
        clause = policy(staged_engine.r)["clauses"][event["clause_id"]]
        FREQUENCY.consume_activation(staged_owner, event["source"], clause["frequency"], engine=staged_engine)
        target_key = _target_key(staged_engine, staged_owner, target, event["source"])
        quota_owner = target if event["source"] == DEEP_COLD else staged_owner
        FREQUENCY.consume_activation(
            quota_owner,
            target_key,
            {"kind": "scene", "uses": 1},
            engine=staged_engine,
        )
        if event["source"] == DEEP_COLD:
            receipt = {"source": _deep_source(staged_engine.r), "target_id": target.entity_id,
                       "scene": FREQUENCY.state(target)["scene"], "at": staged_engine.elapsed_seconds,
                       "feature_owner_id": staged_owner.entity_id, "key": target_key, "event_id": event["id"]}
            _deep_quota_state(target, create=True)["uses"].append(deepcopy(receipt))
            result["target_scene_quota"] = receipt
        event["status"] = "completed"
        event["result"] = dict(result, used=True)
        if event["source"] == DEEP_COLD:
            _close_deep_target(staged_engine, target)
        _close_unavailable(staged_engine, staged_owner, actors)
        return deepcopy(event["result"])

    def scoped(staged_engine,staged_owner):
        _validate_native_offer_links(staged_engine)
        event=_find_event(staged_owner,event_id)
        parent=native_completion(staged_engine,event,returned=True) if use else None
        with __import__('action_lifecycle').completion_reaction(staged_engine,staged_owner,event['source'],parent,receipt=event):
            return apply(staged_engine,staged_owner)
    return GRANTS.transition(engine, trainer, scoped)


def _native_offer_facts(event):
    """Detached issued trigger/effect facts; only its lifecycle may progress."""
    return deepcopy({key:value for key,value in event.items() if key not in ('status','result')})


def native_completion(engine, event, *, returned=False):
    """Exact native producer link; component/legacy observations stay unlinked."""
    fields={'native_event_id','completion_id'} & set(event)
    if not fields:
        _validate_native_offer_links(engine)
        return None
    if fields!={'native_event_id','completion_id'}:raise ValueError('paired native reaction origin required')
    import move_completion as MC
    native=getattr(engine,'_passive_events',{}).get(event['native_event_id'])
    row=getattr(engine,MC.KEY,{}).get(event['completion_id'])
    if (native is None or row is None or native.get('completion_id')!=row['id'] or
            native.get('move_id')!=event['move_id'] or native['actor'].entity_id!=event['attacker_id'] or
            native['target'].entity_id!=event['target_id'] or row['actor'] is not native['actor']):
        raise ValueError('class reaction must retain its actual native hit participants')
    # Older records may retain participant IDs without an issued reciprocal
    # witness. Preserve their effects, but do not invent same-hit authority.
    if event.get('native_origin_version') is None:
        _validate_native_offer_links(engine)
        return None
    offers=native.get('class_actor_reaction_offers')
    if (event['native_origin_version']!=1 or type(offers) is not dict
            or offers.get(event['id'])!=_native_offer_facts(event)):
        raise ValueError('class reaction must retain its actual issued native occurrence')
    if native['phase']=='producer_return_boundary':
        if 'intent_fingerprint' not in native:raise ValueError('native class reaction occurrence seal missing')
        __import__('passive_events')._bind_intent(engine,native)
    if returned:MC.require_hit_return(engine,native['id'],native['target'],_recipient_only=True)
    return row


def completion_reaction_origin(engine,actor,source,row,receipt):
    if source not in ALL_RULES:return False
    if not isinstance(receipt,dict) or not any(saved is receipt for saved in (_state(actor) or {}).get('events',())):
        raise ValueError('actual acquired class reaction receipt required')
    if receipt['source']!=source or receipt['owner_id']!=actor.entity_id or acquired_source(actor,source) is None:
        raise ValueError('actual class reaction owner/source required')
    if native_completion(engine,receipt,returned=True) is not row:
        raise ValueError('actual class reaction completion required')
    return True
