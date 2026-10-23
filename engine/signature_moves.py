"""Exact CSV R41/book C03-141 Signature Move acquisition and projection.

The existing trainer acquisition receipt owns the choice.  This adapter does
not consume a Vitamin, teach a move, or create a second usage/frequency ledger.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import csv

import trainer_feature_acquisition as ACQUISITION

SOURCE = "C2CSV/input/db/feats.csv:R41:main"
BOOK_SOURCE = "C03-141"
BOOK_FILE = "input/ch03-skills-edges-feats.md"
BOOK_SHA256 = "b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23"
BOOK_EXCERPT_SHA256 = "7a635758371335abd55e5328c97a401a2275f7b6c98ec2f0028f5b2c3fc7c9d3"
FEATURE = "feat/시그니처-기술"
ADAPTER = "trainer-feature/signature-move/v1"
STATS = ("hp", "atk", "def", "spa", "spd", "spe")
SOURCE_SHA256 = "4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd"
CELLS = ["시그니처 기술", "[+아무 스탯]", "4개의 기술을 배움", "항상",
         "알고 있는 기술을 선택하세요. PP업을 사용한 것처럼 기술의 빈도를 한 단계 높입니다. 이 선택은 한 번 만들면 바꿀 수 없습니다. 이 재주는 임시적인 수단을 통해 알게 된 기술을 선택할 수 없으며, 이러한 기술을 사용하여 이 재주를 사용할 수 없습니다."]


def source(rules, clause_id=SOURCE):
    if clause_id not in (SOURCE, BOOK_SOURCE) or rules._selected_rule(FEATURE) != FEATURE:
        raise ValueError("Signature Move requires its exact selected source")
    if clause_id in rules.ruleset.unit_versions or FEATURE in rules.ruleset.unit_versions:
        raise ValueError("Signature Move source version requires its own adapter")
    if clause_id == BOOK_SOURCE:
        path = Path(rules.root) / BOOK_FILE
        if sha256(path.read_bytes()).hexdigest() != BOOK_SHA256:
            raise ValueError("Signature Move book source changed; review required")
        excerpt = "\n".join(path.read_text(encoding="utf-8-sig").splitlines()[856:861])
        unit = rules.selection.units.get(FEATURE, {})
        binding = unit.get("source", {})
        if (sha256(excerpt.encode()).hexdigest() != BOOK_EXCERPT_SHA256 or
                binding.get("file") != BOOK_FILE.removeprefix("input/") or
                binding.get("lines") != [857, 861] or
                binding.get("sha256") != BOOK_SHA256):
            raise ValueError("Signature Move book catalog binding changed")
        rules.ruleset.require({"id": BOOK_SOURCE, "source": {
            "file": BOOK_FILE.removeprefix("input/"), "lines": [857, 861]}})
        return {"clause_id": BOOK_SOURCE, "file": BOOK_FILE,
                "sha256": BOOK_SHA256, "version": 1}
    path = Path(rules.root) / "input/db/feats.csv"
    if sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Signature Move source changed; review required")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        if list(csv.reader(handle))[40] != CELLS:
            raise ValueError("Signature Move exact CSV cells changed")
    unit = rules.selection.units.get(FEATURE, {})
    if unit.get("title") != CELLS[0] or "+아무 스탯" not in unit.get("tags", ()):
        raise ValueError("Signature Move catalog identity changed")
    rules.ruleset.require({"id": SOURCE, "source": {
        "file": "db/feats.csv", "record_span": [41, 41]}})
    return {"clause_id": SOURCE, "file": "input/db/feats.csv",
            "sha256": SOURCE_SHA256, "version": 1}


def _frequency(value):
    if (not isinstance(value, (tuple, list)) or len(value) != 2 or
            value[0] not in ("at_will", "every_other_turn", "daily", "scene") or
            type(value[1]) is not int or value[1] < 1 or
            (value[0] in ("at_will", "every_other_turn") and value[1] != 1)):
        raise ValueError("Signature Move needs the reviewed PP Up frequency policy")
    return tuple(value)


def _learned(engine, actor):
    """Current permanent baseline and authenticated typed learned sources.

    Never use actor.moves: it includes borrowed/temporary permissions and
    overlays.  Legacy live-only imports are deliberately not qualification.
    """
    import move_state as MOVES
    import class_move_grants as CLASSES
    import static_feature_state_grants as STATIC
    import acquired_feature_projections as PROJECTIONS
    known = MOVES.known(engine.r, actor.spec)
    origins = {mid: [{"kind": "baseline", "index": index}]
               for index, mid in enumerate(known)}
    rows = actor.spec.get("state_grants", {}).get("sources", {})
    for sid, row in rows.items():
        moves = row.get("grants", {}).get("moves", ())
        if (not moves or row.get("move_mode", "learned") != "learned" or
                row.get("lifetime") not in ("permanent", "while_owned")):
            continue
        uid = row.get("rule_id")
        if row.get("owner_id") != actor.entity_id or engine.r._selected_rule(uid) != uid:
            raise ValueError("permanent learned grant needs its actual owner/source")
        if row.get("class_move_projection") == 1:
            plan = CLASSES.plan(engine, actor, uid)
            if (sid != "feature:" + actor.entity_id + ":" + uid or
                    moves != plan["moves"] or row.get("class_move_selection") != plan["selections"]):
                raise ValueError("class learned qualification source changed")
        elif row.get("source_contract") == "acquired_static_feature_state_projection":
            STATIC.validate(actor)
        elif row.get(PROJECTIONS.TAG) == 1:
            plan = PROJECTIONS.plan(engine, actor, uid)
            if (sid != PROJECTIONS._source_key(actor, uid) or
                    moves != plan["move_ids"] or row.get("projection_move_ids") != plan["move_ids"]):
                raise ValueError("acquired Feature learned source changed")
        elif row.get("lifetime") != "permanent":
            # No permanent-learning assertion from an unreviewed while-owned
            # equipment/effect or arbitrary current display grant.
            continue
        evidence = {"kind": "learned_grant", "source_id": sid,
                    "rule_id": uid, "owner_id": actor.entity_id,
                    "lifetime": row["lifetime"], "move_mode": "learned"}
        for mid in MOVES.known(engine.r, {"moves": list(moves)}):
            if mid not in origins:
                known.append(mid)
                origins[mid] = []
            origins[mid].append(deepcopy(evidence))
    return known, origins


def _qualification(actor, snapshot):
    return {"schema": 1, "status": "qualified", "waivers": [], "checks": [
        {"id": "trainer", "kind": "prerequisite", "state": "passed",
         "observed": "trainer", "reason": "actual acquiring trainer"},
        {"id": "four_learned", "kind": "prerequisite", "state": "passed",
         "observed": {"count": len(snapshot["canonical_values"]),
                      "snapshot_integrity": snapshot["integrity"]},
         "reason": "four distinct learned moves, excluding temporary means"}]}


def validate_receipt(actor, payload):
    src = source(actor.r, payload.get("source", {}).get("clause_id"))
    if (actor.kind != "trainer" or payload["adapter_id"] != ADAPTER or
            payload["feature_id"] != FEATURE or payload["source"] != src):
        raise ValueError("Signature Move receipt requires its actual trainer/source")
    if payload["provider"] != {"actor_id": actor.entity_id, "mode": "self_acquisition"}:
        raise ValueError("Signature Move provider provenance changed")
    selection = payload["selection"]
    snapshot = selection["acquisition_snapshot"]
    if (selection["kind"] != "canonical_move_id" or selection["required_count"] != 1 or
            len(selection["values"]) != 1 or type(snapshot) is not dict or
            set(snapshot) != {"canonical_values", "origins", "stat", "base_frequency", "integrity"}):
        raise ValueError("Signature Move requires ONE immutable selected move")
    values, origins = snapshot["canonical_values"], snapshot["origins"]
    if (type(values) is not list or len(values) < 4 or len(set(values)) != len(values) or
            any(type(mid) is not str or actor.r.move_id(mid) != mid for mid in values) or
            type(origins) is not dict or set(origins) != set(values) or snapshot["stat"] not in STATS):
        raise ValueError("Signature Move four permanent learned snapshot changed")
    _frequency(snapshot["base_frequency"])
    for mid, proofs in origins.items():
        if type(proofs) is not list or not proofs:
            raise ValueError("permanent learned source evidence missing")
        for proof in proofs:
            if type(proof) is not dict:
                raise ValueError("permanent learned source evidence changed")
            if proof.get("kind") == "baseline":
                if (set(proof) != {"kind", "index"} or type(proof["index"]) is not int or
                        not 0 <= proof["index"] < len(values) or values[proof["index"]] != mid):
                    raise ValueError("permanent baseline evidence changed")
            elif (set(proof) != {"kind", "source_id", "rule_id", "owner_id", "lifetime", "move_mode"} or
                  proof.get("kind") != "learned_grant" or proof.get("move_mode") != "learned" or
                  proof.get("lifetime") not in ("permanent", "while_owned") or
                  proof.get("owner_id") != actor.entity_id or
                  any(type(proof.get(k)) is not str or not proof[k] for k in ("source_id", "rule_id"))):
                raise ValueError("temporary or unauthenticated learned snapshot")
    body = {k: v for k, v in snapshot.items() if k != "integrity"}
    if snapshot["integrity"] != ACQUISITION._digest("signature-move/learned-snapshot/v1", body):
        raise ValueError("Signature Move snapshot integrity changed")
    mid = selection["values"][0]
    if (mid not in origins or selection["proofs"] != [{"value": mid,
            "origins": origins[mid], "snapshot_integrity": snapshot["integrity"]}] or
            payload["qualification"] != _qualification(actor, snapshot)):
        raise ValueError("Signature Move acquisition qualification/selection changed")
    return src


def receipt(actor):
    rows = [row for row in ACQUISITION.receipts(actor) if row["feature_id"] == FEATURE and row.get('state') != 'withdrawn']
    if len(rows) != 1:
        raise ValueError("Signature Move requires one committed acquisition receipt")
    return rows[0]


def stat_choice(actor):
    return receipt(actor)["selection"]["acquisition_snapshot"]["stat"]


def acquire(engine, actor, *, acquisition_request_id, selected_move, stat,
            source_clause_id=SOURCE, feature_instance_id=FEATURE + ":1",
            provider=None, waivers=(), lifecycle_policy=None):
    import world_entities as WORLD
    import state_grants as GRANTS
    import frequency as FREQUENCY
    import static_feature_state_grants as STATIC
    provider = actor if provider is None else provider
    WORLD.require_actors(engine, actor, provider)
    src = source(engine.r, source_clause_id)
    lifecycle = ACQUISITION._lifecycle(lifecycle_policy)
    ACQUISITION._text(acquisition_request_id, "acquisition request identity")
    ACQUISITION._text(feature_instance_id, "feature instance identity")
    if actor.kind != "trainer" or provider is not actor or waivers not in ((), []):
        raise ValueError("Signature Move needs the actual trainer without a prerequisite waiver")
    mid = engine.r.move_id(selected_move) if type(selected_move) is str else None
    if mid is None or stat not in STATS:
        raise ValueError("Signature Move requires ONE canonical move and one actual stat")
    intent = ACQUISITION._intent(actor_id=actor.entity_id, feature_id=FEATURE,
        feature_instance_id=feature_instance_id, source=src, request_id=acquisition_request_id,
        provider_id=actor.entity_id, adapter_id=ADAPTER, selection_kind="canonical_move_id",
        selected_values=[mid], required_count=1, lifecycle_policy=lifecycle)
    intent["stat_choice"] = stat
    signature = ACQUISITION._digest("trainer-feature/acquisition-request/v1", intent)
    ACQUISITION.validate_actor(actor)
    ledger = actor.spec.get(ACQUISITION.LEDGER_KEY, {})
    existing = ledger.get(acquisition_request_id)
    if existing is not None:
        if existing["request_integrity"] != signature:
            raise ValueError("Signature Move request replay changed its choice")
        return deepcopy(existing)
    aliases = {FEATURE, "시그니처 기술", "Signature Move"}
    if (any(row["feature_id"] == FEATURE for row in ledger.values()) or
            aliases.intersection(actor.spec.get("feats", []))):
        raise ValueError("Signature Move is immutable; no reselection or retroactive receipt")
    known, origins = _learned(engine, actor)
    if len(known) < 4 or mid not in known:
        raise ValueError("Signature Move requires four permanent learned moves and a learned selection")
    base = _frequency(FREQUENCY.move_frequency(engine, mid, actor))
    body = {"canonical_values": known, "origins": origins, "stat": stat,
            "base_frequency": list(base)}
    snapshot = {**body, "integrity": ACQUISITION._digest("signature-move/learned-snapshot/v1", body)}
    row = ACQUISITION._seal({"schema": 1, "basis": "trainer_feature_selection",
        "receipt_id": "trainer-feature-selection/" + acquisition_request_id,
        "actor_id": actor.entity_id, "feature_id": FEATURE,
        "feature_instance_id": feature_instance_id, "source": src,
        "acquisition_request_id": acquisition_request_id,
        "provider": {"actor_id": actor.entity_id, "mode": "self_acquisition"},
        "adapter_id": ADAPTER, "qualification": _qualification(actor, snapshot),
        "selection": {"kind": "canonical_move_id", "required_count": 1, "values": [mid],
                      "proofs": [{"value": mid, "origins": origins[mid],
                                  "snapshot_integrity": snapshot["integrity"]}],
                      "acquisition_snapshot": snapshot},
        "lifecycle_policy": lifecycle, "request_integrity": signature, "committed": True})

    def apply(e, c):
        c.spec.setdefault("feats", []).append(FEATURE)
        c.spec.setdefault(ACQUISITION.LEDGER_KEY, {})[acquisition_request_id] = deepcopy(row)
        c.spec[ACQUISITION.PROJECTION_KEY] = ACQUISITION._projection_from_rows(
            ACQUISITION._active_rows(c))
        STATIC._install(e, c, SOURCE, {"stat": stat, "selection": stat, "count": 1})
        ACQUISITION.validate_actor(c)
        return deepcopy(row)
    return GRANTS.transition(engine, actor, apply)


def frequency(actor, mid, base):
    if actor is None:
        return base
    if not any(row.get("feature_id") == FEATURE for row in ACQUISITION._active_rows(actor)):
        if {FEATURE, "시그니처 기술", "Signature Move"}.intersection(actor.spec.get("feats", [])):
            raise ValueError("Signature Move needs its committed acquisition receipt")
        return base
    row = receipt(actor)
    if row["selection"]["values"] != [mid]:
        return base
    snapshot = row["selection"]["acquisition_snapshot"]
    kind, count = _frequency(base)
    if list(base) != snapshot["base_frequency"]:
        raise ValueError("Signature Move changed conditional frequency needs explicit source composition")
    if actor.spec.get("vitamin_special_uses", {}).get("item/pp업"):
        raise ValueError("Signature Move has no admitted same-owner PP Up composition")
    return base if kind == "at_will" else ("at_will", 1) if kind == "every_other_turn" else (kind, count + 1)
