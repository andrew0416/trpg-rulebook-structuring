"""Exact source-owned combat projections for a CSV trainer-feature cluster.

The common contract is deliberately small: an acquired trainer source owns a
declaration on either that trainer or one of their Pokemon.  Consumers read
that declaration and the exact clause policy.  Sustained Stratagems add a
two-AP reservation and an encounter lifetime; static features do not invent a
runtime activation.
"""
from copy import copy, deepcopy
import hashlib
import json
from pathlib import Path
import re

import action_points as AP
import combat_precision_features as PRECISION
import skill_modifiers as SKILL
import state_grants as GRANTS
import turn as TURN


POLICY_PATH = "data/class-passive-combat-policy.json"
KIND = "class_passive_combat"
STATE = "_class_passive_combat"
STAT_STRATAGEM='feat/스탯-책략'

SPECIES_SAVANT = "feat/종의-학자"
SPECIES_SAVANT_ADAPTER = "trainer-feature/species-savant-family/v1"
RECKLESS = "feat/난폭한-진격"
TRICK_SHOT = "feat/트릭-샷"
CAPRICIOUS = "feat/변덕스러운-회전"
ADAPTIVE = "feat/반복진화"
SHINING_FLAME = "feat/빛나는-화염"
GLACIAL_ICE = "feat/빙하-얼음"
PERFECT = "feat/확실한-완벽"
BURNING_BRAND = "feat/불타는-낙인"
BLESSED_RESILIENCE = "gift/축복받은-회복력"
HAT_TRICK = "technique/해트트릭"
REINFORCED_CLOTHING = "technique/강화옷"

STRATAGEMS = frozenset((RECKLESS, TRICK_SHOT, CAPRICIOUS, ADAPTIVE, PERFECT))
POKEMON_STATIC = frozenset((SPECIES_SAVANT, SHINING_FLAME, GLACIAL_ICE))
TRAINER_STATIC = frozenset((BURNING_BRAND, BLESSED_RESILIENCE, HAT_TRICK, REINFORCED_CLOTHING))
ALL_RULES = STRATAGEMS | POKEMON_STATIC | TRAINER_STATIC

CLAUSE_BY_RULE = {
    SPECIES_SAVANT: "C2CSV/input/db/feats.csv:R7:main",
    RECKLESS: "C2CSV/input/db/feats.csv:R21:main",
    TRICK_SHOT: "C2CSV/input/db/feats.csv:R24:main",
    CAPRICIOUS: "C2CSV/input/db/feats.csv:R27:main",
    ADAPTIVE: "C2CSV/input/db/feats.csv:R230:main",
    SHINING_FLAME: "C2CSV/input/db/feats.csv:R253:main",
    GLACIAL_ICE: "C2CSV/input/db/feats.csv:R273:main",
    PERFECT: "C2CSV/input/db/feats.csv:R278:main",
    BURNING_BRAND: "C2CSV/input/db/feats.csv:R624:main",
    BLESSED_RESILIENCE: "C2CSV/input/db/class-data.csv:R10:blessing",
    HAT_TRICK: "C2CSV/input/db/class-data.csv:R51:technique",
    REINFORCED_CLOTHING: "C2CSV/input/db/class-data.csv:R57:technique",
}

NATIVE_CLAUSE_BY_RULE = {
    TRICK_SHOT: "C03-132",
    CAPRICIOUS: "input/ch03-skills-edges-feats.md:776-780",
    SHINING_FLAME: "input/ch04-trainer-classes.md:1541-1544",
    GLACIAL_ICE: "input/ch04-trainer-classes.md:1677-1680",
}

ALIASES = {
    SPECIES_SAVANT: ("종의 학자", "Species Savant"),
    RECKLESS: ("난폭한 진격", "Reckless Advance"),
    TRICK_SHOT: ("트릭 샷", "Trick Shot"),
    CAPRICIOUS: ("변덕스러운 회전", "Capricious Whirl"),
    ADAPTIVE: ("반복진화", "Adaptive Evolution"),
    SHINING_FLAME: ("빛나는 화염", "Shining Flame"),
    GLACIAL_ICE: ("빙하 얼음", "Glacial Ice"),
    PERFECT: ("확실한 완벽", "Perfectly Ordinary"),
    BURNING_BRAND: ("불타는 낙인", "Burning Brand"),
    BLESSED_RESILIENCE: ("축복받은 회복력", "Blessed Resilience"),
    HAT_TRICK: ("해트트릭", "Hat Trick"),
    REINFORCED_CLOTHING: ("강화옷", "Reinforced Clothing"),
}


def _key(value):
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value).lower())


def identity(value):
    if not isinstance(value, str):
        return None
    if value==STAT_STRATAGEM:return value
    import type_ace as TA
    if value in TA.STRATAGEMS:return value
    for uid, aliases in ALIASES.items():
        if _key(value) in {_key(uid), _key(CLAUSE_BY_RULE[uid]), *(_key(x) for x in aliases)}:
            return uid
    return None


def _policy(rules):
    cached = getattr(rules, "_class_passive_combat_policy", None)
    if cached is not None:
        return cached
    path = Path(rules.root) / POLICY_PATH
    if not path.is_file():
        staged = Path(__file__).resolve().parent.parent / POLICY_PATH
        if staged.is_file():
            path = staged
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported class passive combat policy")
    for relative, digest in data.get("source_files", {}).items():
        actual = hashlib.sha256((Path(rules.root) / relative).read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError("class passive combat source changed: " + relative)
    clauses = data.get("clauses")
    if not isinstance(clauses, dict) or set(clauses) != set(CLAUSE_BY_RULE.values()):
        raise ValueError("class passive combat policy needs the exact reviewed clauses")
    for uid, clause_id in CLAUSE_BY_RULE.items():
        row = clauses[clause_id]
        if row.get("id") != clause_id or row.get("rule_id") != uid:
            raise ValueError("class passive combat clause identity changed: " + clause_id)
    native = data.get("native_sources", {})
    if set(native) != set(NATIVE_CLAUSE_BY_RULE):
        raise ValueError("exact reviewed native class passive sources required")
    for uid, clause_id in NATIVE_CLAUSE_BY_RULE.items():
        row = native[uid]
        if (row.get("rule_id") != uid or row.get("clause_id") != clause_id
                or row.get("behavior_clause_id") != CLAUSE_BY_RULE[uid]):
            raise ValueError("native class passive source binding changed")
        lines = (Path(rules.root) / row["file"]).read_text(encoding="utf-8").splitlines()
        excerpt = "\n".join(lines[row["start"] - 1:row["end"]])
        if hashlib.sha256(excerpt.encode("utf-8")).hexdigest() != row["excerpt_sha256"]:
            raise ValueError("native class passive source excerpt changed")
    rules._class_passive_combat_policy = data
    return data


def _field(uid):
    if uid == BLESSED_RESILIENCE:
        return "gifts"
    if uid in (HAT_TRICK, REINFORCED_CLOTHING):
        return "techniques"
    return "feats"


def acquired_source(trainer, uid):
    if trainer.kind != "trainer" or uid not in ALL_RULES:
        return None
    values = trainer.spec.get(_field(uid), [])
    if not isinstance(values, (list, tuple)):
        raise ValueError(_field(uid) + " ownership must be a list")
    matches = [value for value in values if identity(value) == uid]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("feature requires exactly one acquired source: " + uid)
    source = matches[0]
    if trainer.r._selected_rule(source) != source:
        raise ValueError("selected feature variant requires its own source policy")
    _policy(trainer.r)
    if uid == BLESSED_RESILIENCE:
        import blessing_skill_features as BLESSINGS
        if not BLESSINGS.approval(trainer,uid):
            raise ValueError("Blessed Resilience requires actual acquired Gift permission")
    return source


def owns(trainer, uid):
    return acquired_source(trainer, uid) is not None


def _native_metadata(rules, uid, source):
    if source != uid or uid not in NATIVE_CLAUSE_BY_RULE:
        return {}
    row = _policy(rules)["native_sources"][uid]
    return {"native_clause_id": row["clause_id"]}


def _choices(trainer):
    choices = trainer.spec.get("class_passive_choices", {})
    if not isinstance(choices, dict):
        raise ValueError("class passive choices must be a mapping")
    return choices


def _choice(trainer, uid):
    row = _choices(trainer).get(uid)
    if not isinstance(row, dict):
        raise ValueError("explicit class passive choice required: " + uid)
    return row


def _trainer_index(engine):
    import world_entities as WORLD
    return WORLD.actor_index(engine)


def _owner(engine, pokemon):
    if pokemon.kind != "pokemon":
        raise ValueError("trainer feature target must be a Pokemon")
    index = _trainer_index(engine)
    owner_id = pokemon.spec.get("trainer_id")
    owner = index.get(owner_id)
    if not isinstance(owner_id, str) or not owner_id or owner is None or owner.kind != "trainer":
        raise ValueError("Pokemon needs an actual trainer owner identity")
    if pokemon.spec.get("trainer") not in (None, owner.name):
        raise ValueError("Pokemon trainer name conflicts with its owner identity")
    return owner


def _owned_pokemon(engine, trainer):
    index = _trainer_index(engine)
    if index.get(trainer.entity_id) is not trainer:
        raise ValueError("actual registered trainer required")
    return [actor for actor in index.values()
            if actor.kind == "pokemon" and actor.spec.get("trainer_id") == trainer.entity_id]


def _source_id(owner, target, uid):
    return "class-passive:" + owner.entity_id + ":" + target.entity_id + ":" + uid


def _declare(target, owner, uid, source):
    clause_id = CLAUSE_BY_RULE[uid]
    sid = _source_id(owner, target, uid)
    metadata = _native_metadata(owner.r, uid, source)
    if uid == SPECIES_SAVANT:
        receipt = _species_book_receipt(owner)
        if receipt is not None:
            metadata.update(source_variant="C03-126", acquisition_receipt_id=receipt["receipt_id"],
                            species_savant_family=receipt["selection"]["acquisition_snapshot"]["family"])
    GRANTS._source(target, sid, KIND, owner_id=owner.entity_id,
                   lifetime="acquired" if target is owner else "your_pokemon",
                   rule_id=uid, clause_id=clause_id, acquisition_source=source,
                   tutor_points=0, **metadata)
    return sid


def _species_group(trainer):
    value = _choice(trainer, SPECIES_SAVANT).get("evolution_group")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Species Savant needs one explicit evolution group")
    return value


def _eligible_species(trainer, pokemon):
    receipt = _species_book_receipt(trainer)
    if receipt is not None:
        family = _species_family(pokemon, pokemon.spec.get("species"))
        if family is None:
            raise ValueError("Species Savant target evolution family is unresolved")
        return family == receipt["selection"]["acquisition_snapshot"]["family"]
    selected = _species_family(trainer, _species_group(trainer))
    if selected is None:
        raise ValueError("Species Savant needs one explicit resolved evolution family")
    family = _species_family(pokemon, pokemon.spec.get("species"))
    if family is None:
        raise ValueError("Species Savant target evolution family is unresolved")
    return family == selected


def _species_book_source(rules):
    row = _policy(rules)["species_savant_book"]
    if (rules._selected_rule(SPECIES_SAVANT) != SPECIES_SAVANT or
            any(key in rules.ruleset.unit_versions for key in (SPECIES_SAVANT, "C03-126"))):
        raise ValueError("selected Species Savant source requires its own acquisition adapter")
    if row["clause_id"] != "C03-126" or row["span"] != [655, 659]:
        raise ValueError("exact book Species Savant clause required")
    selected_source = rules.selection.units[SPECIES_SAVANT].get("source", {})
    if (selected_source.get("file") != row["file"].removeprefix("input/") or
            selected_source.get("lines") != row["span"] or
            selected_source.get("sha256") != _policy(rules)["source_files"][row["file"]]):
        raise ValueError("book Species Savant catalog source differs from its reviewed clause")
    path = Path(rules.root) / row["file"]
    excerpt = "\n".join(path.read_text(encoding="utf-8").splitlines()[654:659])
    if hashlib.sha256(excerpt.encode("utf-8")).hexdigest() != row["excerpt_sha256"]:
        raise ValueError("book Species Savant source changed")
    _species_family_sources(rules)
    rules.ruleset.require({"id": "C03-126", "source": {"file": row["file"].removeprefix("input/"), "lines": row["span"]}})
    return {"clause_id": "C03-126", "file": row["file"],
            "sha256": _policy(rules)["source_files"][row["file"]], "version": 1}


def _species_family_sources(rules):
    """Verify shared family facts independently of a Feature acquisition source."""
    for relative, digest in _policy(rules)["species_savant_book"]["family_sources"].items():
        if hashlib.sha256((Path(rules.root) / relative).read_bytes()).hexdigest() != digest:
            raise ValueError("Species Savant evolution source changed: " + relative)


def _species_family(actor, species):
    """Reuse the actual connected evolution owner; arbitrary group labels are not facts."""
    import pokemon_activities as ACTIVITIES
    from builder import species_lookup
    _species_family_sources(actor.r)
    try:
        selected = species_lookup(actor.r, species)
        if selected.get("_source", {}).get("file") != "db/pokemon.csv":
            return None
        names = ACTIVITIES._evolution_family(actor, selected["id"])
        catalog = {row["species"]: row for row in json.loads(
            (Path(actor.r.root) / "output/entities/learnsets.json").read_text(encoding="utf-8"))}
        if any(actor.r.learnsets.get(name) != catalog.get(name) or name not in catalog for name in names):
            return None
        return sorted(species_lookup(actor.r, name)["id"] for name in names)
    except (KeyError, ValueError):
        return None


def _species_book_receipt(trainer):
    import trainer_feature_acquisition as ACQUISITION
    if not any(row.get("adapter_id") == SPECIES_SAVANT_ADAPTER for row in ACQUISITION._active_rows(trainer)):
        return None
    rows = [row for row in ACQUISITION.receipts(trainer)
            if row["adapter_id"] == SPECIES_SAVANT_ADAPTER and row.get("state") != "withdrawn"]
    if len(rows) != 1:
        raise ValueError("one immutable Species Savant family acquisition required")
    return rows[0]


def _species_qualification(actor, snapshot):
    import acquisition_qualification as QUALIFICATION
    rows = snapshot["prerequisites"]
    families = [_species_family(actor, row["species"]) for row in rows]
    checks = [
        QUALIFICATION.check("trainer", "prerequisite", actor.kind == "trainer", "Species Savant requires an actual trainer"),
        QUALIFICATION.check("three_individuals", "prerequisite",
            len(rows) == 3 and len({row["entity_id"] for row in rows}) == 3 and
            all(row["owner_id"] == actor.entity_id for row in rows), "Species Savant requires three distinct actual owned Pokemon"),
        QUALIFICATION.check("same_evolution_family", "prerequisite",
            None if None in families else len(families) == 3 and all(family == families[0] for family in families),
            "Species Savant requires one established shared evolution family; the same species is allowed"),
    ]
    result = QUALIFICATION.evaluate(source_id="C03-126", provider=actor.entity_id, stage="acquisition", checks=checks)
    return {"schema": 1, "status": result["status"], "checks": result["checks"], "waivers": []}


def validate_species_savant_receipt(actor, payload):
    source = _species_book_source(actor.r)
    selection = payload["selection"]; snapshot = selection["acquisition_snapshot"]
    family = snapshot.get("family")
    if (actor.kind != "trainer" or payload["feature_id"] != SPECIES_SAVANT or
            payload["adapter_id"] != SPECIES_SAVANT_ADAPTER or payload["source"] != source or
            payload["provider"] != {"actor_id": actor.entity_id, "mode": "self_acquisition"} or
            set(snapshot) != {"family", "prerequisites"} or type(family) is not list or not family or
            selection["kind"] != "evolution_family" or selection["required_count"] != 1 or
            selection["values"] != [family[0]] or _species_family(actor, family[0]) != family):
        raise ValueError("Species Savant immutable source/family acquisition mismatch")
    rows = snapshot["prerequisites"]
    if (type(rows) is not list or any(type(row) is not dict or
            set(row) != {"entity_id", "species", "owner_id", "basis"} or
            any(type(row[key]) is not str or not row[key] for key in row) or
            row["basis"] not in ("actual_actor", "registered_reserve") for row in rows) or
            selection["proofs"] != [{"value": family[0], "family": family}]):
        raise ValueError("Species Savant historical ownership evidence mismatch")
    qualification = _species_qualification(actor, snapshot)
    if qualification["status"] != "qualified" or payload["qualification"] != qualification:
        raise ValueError("Species Savant historical prerequisite evidence mismatch")
    return source


def acquire_species_savant(engine, trainer, *, acquisition_request_id, selected_species, prerequisite_ids):
    """Acquire book C03-126 once; its historical prerequisite is not a retention gate."""
    import trainer_feature_acquisition as ACQUISITION
    import world_entities as WORLD
    from builder import species_lookup
    index = WORLD.require_actors(engine, trainer)
    source = _species_book_source(engine.r)
    ACQUISITION._text(acquisition_request_id, "acquisition request")
    if (trainer.kind != "trainer" or type(prerequisite_ids) is not list or len(prerequisite_ids) != 3 or
            any(type(uid) is not str or not uid for uid in prerequisite_ids) or len(set(prerequisite_ids)) != 3):
        raise ValueError("Species Savant requires three distinct owned Pokemon identities")
    family = _species_family(trainer, selected_species)
    if family is None:
        return {"status": "pending", "acquired": False, "reason": "selected evolution family needs an established definition or source policy"}
    lifecycle = deepcopy(ACQUISITION.LIFECYCLE_WHILE_OWNED)
    intent = ACQUISITION._intent(actor_id=trainer.entity_id, feature_id=SPECIES_SAVANT,
        feature_instance_id=SPECIES_SAVANT + ":book", source=source, request_id=acquisition_request_id,
        provider_id=trainer.entity_id, adapter_id=SPECIES_SAVANT_ADAPTER, selection_kind="evolution_family",
        selected_values=[family[0]], required_count=1, lifecycle_policy=lifecycle)
    signature = ACQUISITION._digest("trainer-feature/acquisition-request/v1", intent)
    ACQUISITION.validate_actor(trainer)
    ledger = trainer.spec.get(ACQUISITION.LEDGER_KEY, {})
    if acquisition_request_id in ledger:
        if ledger[acquisition_request_id]["request_integrity"] != signature:
            raise ValueError("Species Savant replay cannot change its selected family")
        return deepcopy(ledger[acquisition_request_id])
    if acquired_source(trainer, SPECIES_SAVANT) or any(row["feature_id"] == SPECIES_SAVANT for row in ledger.values()):
        raise ValueError("Species Savant cannot reselect or claim an existing unreceipted acquisition")
    rows = []
    for uid in prerequisite_ids:
        ACQUISITION._text(uid, "prerequisite Pokemon identity")
        pokemon = index.get(uid)
        reserve = trainer.spec.get("pokemon_registry", {}).get(uid)
        if pokemon is not None and pokemon.kind == "pokemon" and pokemon.spec.get("trainer_id") == trainer.entity_id:
            species, basis = pokemon.spec["species"], "actual_actor"
        elif (pokemon is None and isinstance(reserve, dict) and reserve.get("sheet_pending") is True and
                reserve.get("owner_id") == trainer.entity_id and reserve.get("location") in ("storage", "sale_transport")):
            species, basis = reserve["species"], "registered_reserve"
        else:
            raise ValueError("Species Savant prerequisite must identify actual currently owned Pokemon")
        rows.append({"entity_id": uid, "species": species_lookup(engine.r, species)["id"],
                     "owner_id": trainer.entity_id, "basis": basis})
    snapshot = {"family": family, "prerequisites": rows}
    qualification = _species_qualification(trainer, snapshot)
    if qualification["status"] != "qualified":
        return {"status": qualification["status"], "acquired": False, "qualification": qualification}
    receipt = ACQUISITION._seal({"schema": 1, "basis": "trainer_feature_selection",
        "receipt_id": "trainer-feature-selection/" + acquisition_request_id, "actor_id": trainer.entity_id,
        "feature_id": SPECIES_SAVANT, "feature_instance_id": SPECIES_SAVANT + ":book", "source": source,
        "acquisition_request_id": acquisition_request_id,
        "provider": {"actor_id": trainer.entity_id, "mode": "self_acquisition"},
        "adapter_id": SPECIES_SAVANT_ADAPTER, "qualification": qualification,
        "selection": {"kind": "evolution_family", "required_count": 1, "values": [family[0]],
                      "proofs": [{"value": family[0], "family": family}], "acquisition_snapshot": snapshot},
        "lifecycle_policy": lifecycle, "request_integrity": signature, "committed": True})
    def apply(staged, owner):
        owner.spec.setdefault("feats", []).append(SPECIES_SAVANT)
        owner.spec.setdefault(ACQUISITION.LEDGER_KEY, {})[acquisition_request_id] = deepcopy(receipt)
        owner.spec[ACQUISITION.PROJECTION_KEY] = ACQUISITION._projection_from_rows(ACQUISITION._active_rows(owner))
        GRANTS._source(owner, "feature:" + owner.entity_id + ":" + SPECIES_SAVANT, "feature",
                       owner_id=owner.entity_id, rule_id=SPECIES_SAVANT, lifetime="while_owned", tutor_points=0)
        for pokemon in _owned_pokemon(staged, owner):
            register_all(staged, pokemon)
        ACQUISITION.validate_actor(owner)
        return deepcopy(receipt)
    return GRANTS.transition(engine, trainer, apply)


def _expected_for(engine, actor):
    expected = {}
    if actor.kind == "trainer":
        for uid in TRAINER_STATIC:
            source = acquired_source(actor, uid)
            if source is not None:
                expected[_source_id(actor, actor, uid)] = (actor, uid, source)
        return expected
    if actor.spec.get("trainer_id") is None:
        return expected
    owner = _owner(engine, actor)
    for uid in STRATAGEMS | POKEMON_STATIC:
        source = acquired_source(owner, uid)
        if source is None:
            continue
        if uid == SPECIES_SAVANT and not _eligible_species(owner, actor):
            continue
        expected[_source_id(owner, actor, uid)] = (owner, uid, source)
    return expected


def register_all(engine, actor):
    """Reconcile declarations for one actual actor without granting acquisition."""
    _policy(engine.r)
    expected = _expected_for(engine, actor)
    state = GRANTS.state(actor)
    stale = [sid for sid, row in state["sources"].items()
             if row.get("kind") == KIND and not row.get("sustain") and sid not in expected]
    for sid in stale:
        GRANTS.revoke(actor, sid, engine=engine)
    for sid, (owner, uid, source) in expected.items():
        _declare(actor, owner, uid, source)
        if uid == SPECIES_SAVANT:
            for stat in ("hp", "atk", "def", "spa", "spd", "spe"):
                GRANTS.stat(actor, stat, 1, sid, operation_id=stat)
    validate(actor)
    return len(expected)


def _declaration(engine, actor, uid):
    rows = []
    for sid, row in actor.spec.get(GRANTS.KEY, {}).get("sources", {}).items():
        if row.get("kind") == KIND and not row.get("sustain") and row.get("rule_id") == uid:
            rows.append((sid, row))
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError("class passive has ambiguous live owners")
    sid, row = rows[0]
    index = _trainer_index(engine)
    owner = index.get(row.get("owner_id"))
    if owner is None or acquired_source(owner,uid) != row.get("acquisition_source"):
        raise ValueError("class passive acquisition or owner changed")
    _validate_native(owner.r, uid, row)
    if actor is not owner and _owner(engine, actor) is not owner:
        raise ValueError("class passive target ownership changed")
    if uid == SPECIES_SAVANT and not _eligible_species(owner, actor):
        raise ValueError("Species Savant evolution group changed")
    return owner, row, sid


def _state(actor, create=False):
    value = actor.spec.get(STATE)
    if value is None and create:
        value = {"version": 1, "sustains": {}, "contractor": None, "serial": 0}
        actor.spec[STATE] = value
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("sustains"), dict):
        raise ValueError("unsupported class passive combat state")
    return value


def _active(engine, pokemon, uid):
    state = _state(pokemon)
    row = None if state is None else state["sustains"].get(uid)
    if row is None:
        return None
    if not engine.encounter_active or row.get("target_id") != pokemon.entity_id:
        raise ValueError("sustained Stratagem needs its actual active encounter target")
    owner = _trainer_index(engine).get(row.get("owner_id"))
    if uid==STAT_STRATAGEM:
        import stat_ace as STAT
        receipt=None if owner is None else STAT.acquired(owner,uid,row.get('branch'))
        source=None if receipt is None else receipt['request_id']
    elif row.get('branch') in __import__('type_ace').TYPES:
        receipt=None if owner is None else __import__('type_ace').acquired(owner,uid)
        source=None if receipt is None else receipt['request_id']
    else:source=None if owner is None else acquired_source(owner,uid)
    if owner is None or source != row.get("acquisition_source"):
        raise ValueError("sustained Stratagem owner or acquisition changed")
    _validate_native(owner.r, uid, row)
    if _owner(engine, pokemon) is not owner:
        raise ValueError("sustained Stratagem target ownership changed")
    if AP.ActionPointAccount(owner).identified_bindings(allow_missing=True).get(row.get("instance")) != 2:
        raise ValueError("sustained Stratagem needs its matching two-AP reservation")
    return owner, row


def _require_stratagem_slot(pokemon):
    """Read both native sustain owners and the existing legacy occupancy marks."""
    state = _state(pokemon)
    if ((state is not None and state["sustains"])
            or PRECISION.KEY in pokemon.custom_conditions
            or pokemon.custom_conditions.get("stratagem") or pokemon.spec.get("stratagem")):
        raise ValueError("only one Stratagem may be sustained on a Pokemon")
    if any(row.get("stratagem") or row.get("_stratagem") for row in pokemon.registry + pokemon.modifiers):
        raise ValueError("existing Stratagem must be released first")


import cheerleader as CHEER

@CHEER.order_activation(None)
def activate(engine, trainer, pokemon, uid, *, communication=None):
    if uid not in STRATAGEMS or acquired_source(trainer, uid) is None:
        raise ValueError("actual acquired Stratagem required")
    if not engine.encounter_active:
        raise ValueError("Stratagem may only be sustained in an encounter")
    if _trainer_index(engine).get(trainer.entity_id) is not trainer or _owner(engine, pokemon) is not trainer:
        raise ValueError("Stratagem requires your actual registered Pokemon")
    if not pokemon.on_field or pokemon.fainted or pokemon.captured:
        raise ValueError("Stratagem target must be available")
    register_all(engine, pokemon)
    if _declaration(engine, pokemon, uid) is None:
        raise ValueError("Stratagem target declaration is missing")
    _require_stratagem_slot(pokemon)
    state = _state(pokemon, create=True)
    if AP.available(trainer) < 2:
        raise ValueError("Stratagem requires two available AP")
    import temporary_ap as TEMP_AP
    TEMP_AP.preflight_binding(trainer,2,"class_passive_combat")
    import order_actions as ORDERS
    delivery=ORDERS.delivery(engine,trainer,pokemon,uid,communication=communication)
    ORDERS.spend(engine,trainer,uid,subject=pokemon.entity_id,communication=delivery)
    state["serial"] += 1
    instance = "class-passive:" + trainer.entity_id + ":" + str(state["serial"])
    while instance in AP.ActionPointAccount(trainer).identified_bindings(allow_missing=True):
        state["serial"] += 1
        instance = "class-passive:" + trainer.entity_id + ":" + str(state["serial"])
    trainer.ap_account.charge(2, mode="bind", instance_id=instance, temporary_binding_owner="class_passive_combat")
    source = acquired_source(trainer, uid)
    row = {"owner_id": trainer.entity_id, "target_id": pokemon.entity_id,
           "instance": instance, "rule_id": uid, "clause_id": CLAUSE_BY_RULE[uid],
           "acquisition_source": source, "lifetime": "sustained_2_ap_encounter"}
    row.update(_native_metadata(engine.r, uid, source))
    state["sustains"][uid] = row
    GRANTS._source(pokemon, instance, KIND, owner_id=trainer.entity_id,
                   lifetime=row["lifetime"], rule_id=uid, clause_id=row["clause_id"],
                   acquisition_source=source, sustain=True, tutor_points=0,
                   **_native_metadata(engine.r, uid, source))
    engine.time_actors([trainer, pokemon])
    engine.log("    " + trainer.name + ": " + pokemon.name + " Stratagem, bind 2 AP", uid)
    return (1, 0)


def _unbind(engine, pokemon, uid, owner, row):
    owner.ap_account.release_binding(row["instance"], expected_amount=2)
    _state(pokemon)["sustains"].pop(uid)
    GRANTS.revoke(pokemon, row["instance"], engine=engine)
    engine.log("    " + pokemon.name + ": Stratagem ends; release 2 AP", uid)


def release(engine, trainer, pokemon, uid):
    active = _active(engine, pokemon, uid)
    if active is None or active[0] is not trainer:
        raise ValueError("actual owner of the live Stratagem required")
    owner, row = active
    if not TURN.spend(engine, trainer, "free", uid + " release"):
        return (0, 1)
    _unbind(engine, pokemon, uid, owner, row)
    return (1, 0)


def end_encounter(engine, actors):
    for pokemon in list(actors):
        state = _state(pokemon)
        if state is None:
            continue
        for uid in list(state["sustains"]):
            active = _active(engine, pokemon, uid)
            if active is not None:
                _unbind(engine, pokemon, uid, *active)


def _damaging(move):
    return PRECISION.damaging(move)


def _melee(move):
    return _damaging(move) and "근접" in str(move.get("range", ""))


def _ranged(move):
    return _damaging(move) and bool(move.get("range")) and not _melee(move)


def type_link_rank(engine, owner, type_name):
    """Resolve the trainer's explicit reviewed Type Link skill and rank."""
    policy = _policy(engine.r)["type_link_skills"]
    allowed = policy.get(type_name)
    if allowed is None:
        # Core119 Type Ace table covers every printed type; the reviewed five rows stay authoritative.
        allowed = __import__('type_ace').SKILLS.get(type_name)
        if allowed is None:
            raise ValueError("unknown Type Link type: " + str(type_name))
    choices = owner.spec.get("type_link_skills", {})
    if not isinstance(choices, dict) or choices.get(type_name) not in allowed:
        raise ValueError("explicit reviewed Type Link skill required for " + type_name)
    return SKILL.effective_rank(engine.r, owner, choices[type_name])


def _effectiveness_preview(engine, attacker, target, move, mm, *, before_resistance=False):
    import effects as FX
    import effects_ext as EXT
    preview = copy(engine)
    preview.log_lines = []
    preview.gm_prompts = []
    preview.decide = lambda prompt: None
    user = copy(attacker)
    defender = copy(target)
    user.counters = deepcopy(attacker.counters)
    user.blessings = deepcopy(attacker.blessings)
    defender.coats = deepcopy(target.coats)
    defender.blessings = deepcopy(target.blessings)
    move_type = EXT.effective_type(preview, user, defender, move, mm)
    mult = preview.type_multiplier(move_type, defender)[0]
    context = {"attacker": user, "target": defender, "multiplier": mult,
               "crit": False, "hit": True, "move": move, "engine": preview}
    mult = EXT.effectiveness_hook(preview, user, defender, move, mm, mult, context)
    context["multiplier"] = mult
    if not before_resistance:
        _, _, resist, _, _ = FX.passive_damage_mods(preview, user, defender, move, context)
        resist += resistance_steps(engine, target, move_type)
        if resist:
            mult = _step_multiplier(preview, mult, -resist)
    if preview.gm_prompts:
        raise ValueError("Adaptive Evolution needs resolved pre-accuracy effectiveness")
    # Both native consumers below only ask whether effectiveness is above one.
    # A pending optional shared response cannot silently become a fixed answer.
    import blessing_effects as BLESSINGS
    potential=mult
    if mult and mult<=1 and not BLESSINGS.reaction_blocked(engine,attacker,move):
        for _,record in BLESSINGS.beneficiaries(engine,attacker,'team_damage_effectiveness'):
            if move['class'] in record['effect']['classes']:
                potential=BLESSINGS._damage_multiplier(engine.r,record,potential)
        if potential>1:
            raise ValueError('optional shared Blessing offense needs resolved pre-accuracy effectiveness')
    return mult


def _step_multiplier(engine, multiplier, delta):
    steps = {1.0: 0, 1.5: 1, 2.0: 2, 3.0: 3, 0.5: -1, 0.25: -2, 0.125: -3}
    if multiplier == 0:
        return 0
    value = max(-3, min(3, steps.get(multiplier, 0) + delta))
    return engine.r.mech("combat/type-effectiveness")["multiplier_by_net_steps"][str(value)]


def preflight(engine, attacker, target, move, mm):
    preflight_glacial(engine, attacker, target, move, mm)
    for uid in STRATAGEMS:
        _active(engine, attacker, uid)
    for uid in (SHINING_FLAME, GLACIAL_ICE, BURNING_BRAND, BLESSED_RESILIENCE,
                HAT_TRICK, REINFORCED_CLOTHING):
        _declaration(engine, attacker if uid != GLACIAL_ICE else target, uid)
    if _active(engine, attacker, ADAPTIVE) and move.get("type") == "벌레":
        _effectiveness_preview(engine, attacker, target, move, mm)


def preflight_glacial(engine, attacker, target, move, mm):
    """Validate the live DR owner before native costs, accuracy or damage RNG."""
    glacial = _declaration(engine, target, GLACIAL_ICE)
    if (glacial and _damaging(move) and "얼음" in target.types
            and move.get("type") in ("격투", "불꽃", "바위", "강철")
            # The native DR consumer receives the multiplier after type and
            # effectiveness overrides, before passive resistance is scaled.
            and _effectiveness_preview(engine, attacker, target, move, mm,
                                       before_resistance=True) > 1):
        type_link_rank(engine, glacial[0], "얼음")


def accuracy_bonus(engine, attacker, target, move, mm):
    extreme = __import__('researcher_fields').accuracy_modifier(engine, attacker)
    if _active(engine, attacker, ADAPTIVE) and move.get("type") == "벌레":
        return extreme + (2 if _effectiveness_preview(engine, attacker, target, move, mm) > 1 else 0)
    return extreme


def accuracy_target(engine, attacker, move, ac):
    if ac is not None and move.get("ac") is not None and _active(engine, attacker, TRICK_SHOT) and _ranged(move):
        return ac + 2
    return ac


def critical_bonus(engine, attacker, move):
    return 3 if _active(engine, attacker, TRICK_SHOT) and _ranged(move) and move.get("ac") is not None else 0


def evasion_bonus(engine, target):
    return 3 if _active(engine, target, CAPRICIOUS) else 0


def effectiveness_modifier(engine, attacker, move, multiplier):
    if _active(engine, attacker, ADAPTIVE) and move.get("type") == "벌레" and 0 < multiplier < 1:
        return _step_multiplier(engine, multiplier, 1)
    return multiplier


def damage_roll_modifier(engine, attacker, target, move, multiplier):
    result = __import__('researcher_fields').damage_roll_modifier(engine, attacker)
    reckless = _active(engine, attacker, RECKLESS)
    if reckless and _melee(move):
        result += 8
    if _active(engine, attacker, CAPRICIOUS) and _damaging(move):
        result -= 5
    adaptive = _active(engine, attacker, ADAPTIVE)
    if adaptive and move.get("type") == "벌레" and multiplier == 1:
        result += type_link_rank(engine, adaptive[0], "벌레")
    shining = _declaration(engine, attacker, SHINING_FLAME)
    if shining and _damaging(move) and move.get("type") == "불꽃" and "화상" in target.conditions:
        result += type_link_rank(engine, shining[0], "불꽃")
    return result


def _parse_dice(expression):
    match = re.fullmatch(r"\s*(\d+)d(\d+)\s*([+\-]\s*\d+)?\s*", expression)
    if not match:
        raise ValueError("Perfectly Ordinary needs the native damage dice expression")
    count, sides = int(match.group(1)), int(match.group(2))
    bonus = int((match.group(3) or "0").replace(" ", ""))
    return count, sides, bonus


def perfect_damage(engine, attacker, move, expression, times, fixed=None):
    if not (_active(engine, attacker, PERFECT) and _damaging(move) and move.get("type") == "노말"):
        return None
    count, sides, bonus = _parse_dice(expression)
    first = count * sides + bonus
    if times == 1:
        return first, [sides] * count
    remaining_fixed = fixed
    if isinstance(fixed, (list, tuple)) and len(fixed) >= count * times:
        remaining_fixed = list(fixed)[count:]
    rest, faces = engine.roll_expr(expression, times - 1, fixed=remaining_fixed)
    return first + rest, [sides] * count + list(faces)


def _burn_move(mm):
    values = [mm.get("apply_status")]
    natural = mm.get("on_natural_roll")
    if isinstance(natural, dict):
        values.append(natural.get("apply_status"))
    for effect in mm.get("effects_exec", []):
        if effect.get("type") == "apply_status":
            values.append(effect.get("status"))
    return "화상" in values or "Burned" in values


def effect_range_bonus(engine, attacker, move, mm, *, actual_damage_type=None):
    rainbow = __import__('researcher_fields').effect_range_bonus(engine, attacker, move)
    if (actual_damage_type or move.get("type")) != "불꽃" or not _burn_move(mm):
        return rainbow
    result = rainbow
    if _damaging(move) and _declaration(engine, attacker, SHINING_FLAME):
        result += 3
    if _declaration(engine, attacker, BURNING_BRAND):
        result += 2
    return result


def _item_effect_applies(effect, move):
    if effect.get("type") != "damage_reduction":
        return False
    scope = effect.get("_scope", {})
    condition = effect.get("vs") or scope.get("class")
    if condition in ("physical", "물리") and move.get("class") != "물리":
        return False
    if condition in ("special", "특수") and move.get("class") != "특수":
        return False
    required_type = scope.get("type")
    return required_type in (None, move.get("type"))


def _qualifying_equipment(engine, target, slot, move):
    rows = []
    for record in getattr(target, "_item_reg", {}).values():
        if slot not in record.get("slots", ()):
            continue
        effects, header = engine.r.item_effects(record.get("item_id"))
        if effects is None or not isinstance(header.get("price"), int) or header["price"] < 1000:
            continue
        rows.append((record, effects))
    if not rows:
        return False, False
    equipment_dr = any(_item_effect_applies(effect, move)
                       for _, effects in rows for effect in effects if isinstance(effect, dict))
    return True, equipment_dr


def damage_reduction(engine, attacker, target, move, multiplier, crit):
    result = 0
    glacial = _declaration(engine, target, GLACIAL_ICE)
    if (glacial and "얼음" in target.types and move.get("type") in ("격투", "불꽃", "바위", "강철")
            and multiplier > 1):
        result += type_link_rank(engine, glacial[0], "얼음")
    if _declaration(engine, target, HAT_TRICK) and crit:
        equipped, item_dr = _qualifying_equipment(engine, target, "머리", move)
        if equipped and not item_dr:
            result += 15
    if _declaration(engine, target, REINFORCED_CLOTHING):
        equipped, item_dr = _qualifying_equipment(engine, target, "몸통", move)
        if equipped and not item_dr:
            result += 5
    return result


def _resilience_patron(engine, owner, choice):
    patron_id=choice.get("patron_id")
    patrons=owner.spec.get("gift_patrons",{})
    index=_trainer_index(engine)
    patron=index.get(patron_id) if isinstance(patron_id,str) else None
    if (patron is None or patron is owner or not isinstance(patrons,dict)
            or patrons.get(BLESSED_RESILIENCE)!=patron_id):
        raise ValueError("Blessed Resilience needs its actual bound patron identity")
    return patron


def _patron_resistance_domain(engine, owner, patron):
    """Read actual typing and unconditional typed passive resistance only."""
    import effects as FX
    domain=[]
    for type_name in engine.r.mech("combat/type-chart")["attack_vs_defense"]:
        if type_name in ("에러","None"):continue
        multiplier=engine.type_multiplier(type_name,patron)[0]
        preview=copy(patron)
        preview.modifiers=[row for row in patron.modifiers if
            ((row.get("type")=="resistance_step" and type_name in row.get("types",()))
             or row.get("type") in ("immunity","absorb"))
            and not any(value for key,value in row.items() if
                key.startswith("if") or key in ("vs","while","while_status","when","condition",
                    "on_miss","on_natural_roll_min","on_natural_roll","on_ko"))]
        move={"id":"state/patron-resistance-domain","type":type_name,"class":"물리"}
        _,_,steps,immune,absorb=FX.passive_damage_mods(engine,owner,preview,move,
            {"attacker":owner,"target":preview,"move":move,"engine":engine,"multiplier":multiplier})
        if not patron.abilities_suppressed and (immune is not None or absorb is not None):
            domain.append(type_name);continue
        if not patron.abilities_suppressed and steps and multiplier:
            multiplier=_step_multiplier(engine,multiplier,-steps)
        if multiplier<1:domain.append(type_name)
    return sorted(domain)


def prepare_resilience(engine, owner, requested=None):
    """Bind the permanent role/selection to a real patron at GM confirmation."""
    _choices(owner)
    choice=_choice(owner,BLESSED_RESILIENCE) if requested is None else requested
    if not isinstance(choice,dict) or choice.get("role") not in ("messiah","contractor"):
        raise ValueError("Blessed Resilience needs its exact role and patron choices")
    required={"role","patron_id","eligible_types"}
    if choice["role"]=="messiah":required.add("selected_types")
    if set(choice)!=required:
        raise ValueError("exact Blessed Resilience acquisition choices required")
    patron=_resilience_patron(engine,owner,choice)
    domain=_patron_resistance_domain(engine,owner,patron)
    eligible=choice["eligible_types"]
    if not isinstance(eligible,list) or len(eligible)!=len(set(eligible)) or sorted(eligible)!=domain:
        raise ValueError("eligible types must equal the actual patron resistance domain")
    result={"role":choice["role"],"patron_id":patron.entity_id,"eligible_types":domain}
    if choice["role"]=="messiah":
        selected=choice["selected_types"]
        if not isinstance(selected,list) or len(selected)!=2 or len(set(selected))!=2 or any(x not in domain for x in selected):
            raise ValueError("Messiah Blessed Resilience needs exactly two eligible patron types")
        result["selected_types"]=list(selected)
    return result


def _resilience_choice(engine,owner):
    choice=_choice(owner,BLESSED_RESILIENCE)
    record=owner.spec.get("_blessing_gift_approvals",{}).get(BLESSED_RESILIENCE,{})
    stored=record.get("configuration")
    canonical=deepcopy(choice)
    if isinstance(canonical.get("eligible_types"),list):canonical["eligible_types"]=sorted(canonical["eligible_types"])
    if not isinstance(stored,dict) or canonical!=stored:
        raise ValueError("Blessed Resilience acquisition choices changed after GM permission")
    _resilience_patron(engine,owner,stored)
    return stored


def resistance_steps(engine, target, move_type):
    declared = _declaration(engine, target, BLESSED_RESILIENCE)
    if declared is None:
        return 0
    owner = declared[0]
    choice = _resilience_choice(engine, owner)
    role = choice.get("role")
    eligible = choice.get("eligible_types")
    if role not in ("messiah", "contractor") or not isinstance(eligible, list) or not eligible or len(set(eligible)) != len(eligible):
        raise ValueError("Blessed Resilience needs its exact patron resistance domain")
    if role == "messiah":
        selected = choice.get("selected_types")
        if not isinstance(selected, list) or len(selected) != 2 or len(set(selected)) != 2 or any(x not in eligible for x in selected):
            raise ValueError("Messiah Blessed Resilience needs exactly two eligible types")
        return int(move_type in selected)
    import frequency as FREQ
    state = _state(owner)
    if state is None:
        return 0
    active = state.get("contractor")
    return int(isinstance(active, dict) and active.get("type") == move_type
               and active.get("scene") == FREQ.state(owner)["scene"])


def activate_blessed_resilience(engine, actor, move_type):
    declared = _declaration(engine, actor, BLESSED_RESILIENCE)
    if declared is None or declared[0] is not actor:
        raise ValueError("actual acquired Blessed Resilience required")
    choice = _resilience_choice(engine, actor)
    eligible = _patron_resistance_domain(engine,actor,_resilience_patron(engine,actor,choice))
    if choice.get("role") != "contractor" or not isinstance(eligible, list) or move_type not in eligible:
        raise ValueError("Contractor must choose an eligible patron type")
    import blessing_skill_rules as BLESSINGS
    import frequency as FREQ
    cost_source = BLESSINGS.sign_cost_source(actor)
    frequency_key = "blessing-sign:" + BLESSED_RESILIENCE
    previous = (_state(actor) or {}).get("contractor")
    if isinstance(previous, dict) and previous.get("scene") == FREQ.state(actor)["scene"]:
        raise ValueError("Contractor Sign already used this scene")
    if not FREQ.activation_allowed(actor, frequency_key, "장면", engine=engine):
        raise ValueError("Contractor Sign already used this scene")
    if AP.available(actor) < 1:
        raise ValueError("Contractor Sign requires one available AP")
    if not TURN.spend(engine, actor, "standard", BLESSED_RESILIENCE):
        return (0, 1)
    AP.charge(actor, 1, mode="spend")
    FREQ.consume_activation(actor, frequency_key, "장면", engine=engine)
    _state(actor, create=True)["contractor"] = {
        "type": move_type,
        "scene": FREQ.state(actor)["scene"],
        "clause_id": CLAUSE_BY_RULE[BLESSED_RESILIENCE],
        "cost_source": cost_source,
        "ap": 1,
    }
    engine.time_actors([actor])
    return (1, 0)


def end_scene(engine, actors):
    for actor in actors:
        state = _state(actor)
        if state is not None:
            state["contractor"] = None


def after_move(engine, attacker, target, move, mm, natural, dealt, *, actual_damage_type=None):
    if not _damaging(move) or dealt <= 0:
        return
    reckless = _active(engine, attacker, RECKLESS)
    if reckless and _melee(move):
        if natural is not None and natural >= 18:
            engine.apply_status(target, "넘어짐", source=RECKLESS, applied_by=attacker)
        import effect_lifetimes as LIFETIMES
        effect = {"type": "apply_status", "status": "취약", "target": "self", "duration": "1라운드"}
        LIFETIMES.install(engine, attacker, attacker, effect, RECKLESS, None, None)
    if (actual_damage_type or move.get("type")) != "불꽃" or natural is None or _burn_move(mm):
        return
    if (_declaration(engine, attacker, SHINING_FLAME)
            and PRECISION.effect_natural(engine, attacker, move, natural, actual_damage_type=actual_damage_type) >= 18):
        engine.apply_status(target, "화상", source=SHINING_FLAME, applied_by=attacker)
    elif _declaration(engine, attacker, BURNING_BRAND) and natural >= 19:
        engine.apply_status(target, "화상", source=BURNING_BRAND, applied_by=attacker)


def _validate_native(rules, uid, row):
    import type_ace as TA
    if uid in TA.STRATAGEMS and row.get('branch') in TA.TYPES:
        __import__('trainer_feature_acquisition')._static_source(rules,uid)
        if row.get('branch')!=TA.DEFINITIONS[uid]['branch'] or row.get('clause_id')!=TA.clause(uid):raise ValueError('Type Ace sustained source changed')
        return
    if uid==STAT_STRATAGEM:
        import trainer_feature_acquisition as T,stat_ace as STAT
        T._static_source(rules,uid)
        if row.get('branch') not in STAT.STATS or row.get('clause_id')!='input/ch04-trainer-classes.md:1154-1164':raise ValueError('Stat Stratagem branch source changed')
        return
    expected = _native_metadata(rules, uid, row.get("acquisition_source"))
    # Older saves retain their behavior-clause identity; registration adds the
    # native binding without replacing the historical CSV behavior reference.
    if "native_clause_id" in row and row["native_clause_id"] != expected.get("native_clause_id"):
        raise ValueError("native class passive acquisition source changed")


def _sustain_clause(uid,row):
    import type_ace as TA
    if uid in TA.STRATAGEMS and row.get('branch') in TA.TYPES:return TA.clause(uid)
    return 'input/ch04-trainer-classes.md:1154-1164' if uid==STAT_STRATAGEM else CLAUSE_BY_RULE.get(uid)


def validate(actor):
    state = actor.spec.get(GRANTS.KEY, {})
    for sid, row in state.get("sources", {}).items():
        if row.get("kind") != KIND:
            continue
        uid = row.get("rule_id")
        if uid not in ALL_RULES|{STAT_STRATAGEM}|__import__('type_ace').STRATAGEMS or row.get("clause_id") != _sustain_clause(uid,row):
            raise ValueError("class passive source has an unreviewed clause")
        if row.get("source_variant") is not None:
            if (uid != SPECIES_SAVANT or row["source_variant"] != "C03-126" or
                    actor.kind != "pokemon" or actor.spec.get("trainer_id") != row.get("owner_id") or
                    not isinstance(row.get("acquisition_receipt_id"), str) or
                    not row["acquisition_receipt_id"].startswith("trainer-feature-selection/") or
                    row.get("species_savant_family") != _species_family(actor, actor.spec.get("species"))):
                raise ValueError("book Species Savant target owner/family evidence changed")
        _validate_native(actor.r, uid, row)
        if row.get("sustain"):
            local = _state(actor)
            if local is None or local["sustains"].get(uid, {}).get("instance") != sid:
                raise ValueError("orphaned sustained class passive source")
            if uid==STAT_STRATAGEM or row.get('branch') in __import__('type_ace').TYPES:
                current=local['sustains'][uid]
                for key in ('owner_id','rule_id','clause_id','branch','acquisition_source'):
                    if current.get(key)!=row.get(key):raise ValueError('Stat Stratagem sustained provenance changed')
    local = _state(actor)
    if local is not None:
        for uid, row in local["sustains"].items():
            if uid not in STRATAGEMS|{STAT_STRATAGEM}|__import__('type_ace').STRATAGEMS or row.get("rule_id") != uid or row.get("clause_id") != _sustain_clause(uid,row):
                raise ValueError("invalid sustained class passive record")
            _validate_native(actor.r, uid, row)
    return True

