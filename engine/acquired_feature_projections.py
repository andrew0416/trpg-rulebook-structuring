"""Reviewed Ability/Move projections from already acquired Features.

The character sheet remains the acquisition authority.  This module turns an
owned Feature plus its immutable printed choice into native ability/move state,
then reconciles that state with a single staged transaction.  It deliberately
does not infer choices, prerequisites, or similarly named catalog versions.
"""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json

import acquired_features as ACQUIRED
import state_grants as GRANTS


POLICY = "data/acquired-feature-projection-policy.json"
TAG = "acquired_feature_projection"


@lru_cache(maxsize=None)
def _load(root):
    base = Path(root)
    data = json.loads((base / POLICY).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("contract") != "acquired feature ability and move projection":
        raise ValueError("reviewed acquired-Feature projection policy required")
    if len(data.get("rules", {})) != 17:
        raise ValueError("the reviewed acquired-Feature denominator must contain seventeen sources")
    for name, digest in data.get("source_files", {}).items():
        path = base / name
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("acquired-Feature projection evidence changed: " + name)
    return data


def sources(rules):
    return tuple(_load(str(rules.root))["rules"])


def clause_ids(rules):
    data = _load(str(rules.root))
    # Validate every catalog binding before exposing completion identities.
    for printed in data["abilities"]:
        _ability(rules, printed)
    for printed in data["moves"]:
        _move(rules, printed)
    for uid in data["rules"]:
        _rule(rules, uid)
    return tuple(row["clause_id"] for row in data["rules"].values())


def identity(rules, value):
    """Resolve only one of the seventeen reviewed owning Features."""
    if not isinstance(value, str):
        raise ValueError("acquired Feature source must be a text identity")
    found = []
    for uid in sources(rules):
        unit = rules.selection.units[uid]
        if value in tuple(x for x in (uid, unit.get("title"), unit.get("eng")) if x):
            found.append(uid)
    if len(found) > 1:
        raise ValueError("ambiguous acquired Feature projection source")
    return found[0] if found else None


def _owned(actor, uid):
    values = actor.spec.get("feats", [])
    if not isinstance(values, (list, tuple)):
        raise ValueError("acquired Feature list required")
    matches = [value for value in values if identity(actor.r, value) == uid]
    if len(matches) > 1:
        raise ValueError("duplicate acquired Feature projection source")
    return bool(matches)


def _rule(rules, uid):
    data = _load(str(rules.root))
    row = data["rules"][uid]
    if rules._selected_rule(uid) != uid:
        raise ValueError("selected acquired Feature source requires its own policy: " + uid)
    unit = rules.selection.units.get(uid)
    if not isinstance(unit, dict):
        raise ValueError("acquired Feature source identity is absent: " + uid)
    source = unit.get("source", {})
    actual_file = "input/" + str(source.get("file", ""))
    if (
        actual_file != row["source_file"]
        or source.get("lines") != row["source_lines"]
        or source.get("sha256") != row["source_sha256"]
        or source.get("sha256") != data["source_files"].get(actual_file)
    ):
        raise ValueError("acquired Feature source provenance changed: " + uid)
    effects, header = rules.feat_effects(uid)
    if effects != row["expected_effects"] or header.get("frequency") != row["expected_frequency"]:
        raise ValueError("acquired Feature extracted contract changed: " + uid)
    frequency = header.get("frequency") or {}
    if frequency.get("kind") != "static" or frequency.get("action") != "static":
        raise ValueError("acquired Feature projection is no longer static: " + uid)
    return row


def _ability(rules, printed):
    data = _load(str(rules.root))
    row = data["abilities"].get(printed)
    if row is None:
        raise ValueError("unreviewed acquired-Feature Ability: " + str(printed))
    candidates = []
    for definition in row["candidate_definitions"]:
        uid = definition["id"]
        unit = rules.selection.units.get(uid)
        if not isinstance(unit, dict):
            raise ValueError("reviewed Ability catalog identity is absent: " + uid)
        source = unit.get("source", {})
        actual = {
            "id": uid,
            "title": unit.get("title"),
            "eng": unit.get("eng"),
            "frequency": rules.ability_freq.get(unit.get("title")),
        }
        # Keep one fresh first-match snapshot for this candidate's catalog fields.
        catalog = next((item for item in json.loads((Path(rules.root) / "output/entities/abilities.json").read_text(encoding="utf-8")) if item.get("id") == uid), {})
        actual.update({
            "effect": catalog.get("effect"),
            "trigger": catalog.get("trigger"),
            "target": catalog.get("target"),
            "keyword": unit.get("keyword"),
            "source_file": "input/" + str(source.get("file", "")),
            "source_record_span": source.get("record_span"),
        })
        if actual != definition:
            raise ValueError("reviewed Ability catalog definition changed: " + uid)
        if rules._selected_rule(uid) != uid or unit["title"] not in rules.ability_effects or unit["title"] in getattr(rules, "excluded_abilities", {}):
            raise ValueError("reviewed Ability catalog identity is not executable: " + uid)
        candidates.append(uid)
    if candidates != row["candidate_ids"] or row["ability_id"] not in candidates:
        raise ValueError("reviewed Ability candidate set changed: " + printed)
    fields = row.get("equivalence_fields", [])
    if fields:
        by_id = {candidate["id"]: candidate for candidate in row["candidate_definitions"]}
        first = by_id[row["equivalent_ids"][0]]
        if any(any(by_id[uid].get(field) != first.get(field) for field in fields)
               for uid in row["equivalent_ids"][1:]):
            raise ValueError("duplicate Ability definitions are no longer semantically equivalent: " + printed)
    resolution = row.get("resolution")
    if resolution == "only_catalog_definition" and row["candidate_ids"] != [row["ability_id"]]:
        raise ValueError("single-definition Ability became ambiguous: " + printed)
    if resolution == "identical_catalog_definitions" and len(row.get("equivalent_ids", [])) < 2:
        raise ValueError("reviewed identical Ability family is no longer duplicated: " + printed)
    if resolution == "ptu_1_05_definition_excludes_later_named_variant":
        chosen = next(candidate for candidate in row["candidate_definitions"] if candidate["id"] == row["ability_id"])
        if "[" in chosen["title"] or any("썬문" not in candidate["title"] and "SuMo" not in str(candidate.get("eng"))
                                         for candidate in row["candidate_definitions"] if candidate["id"] != row["ability_id"]):
            raise ValueError("PTU 1.05 Ability version evidence changed: " + printed)
    if resolution not in {"only_catalog_definition", "identical_catalog_definitions", "ptu_1_05_definition_excludes_later_named_variant"}:
        raise ValueError("unsupported acquired-Feature Ability resolution")
    return row["ability_id"], row["ability_title"]


def registration(rules, name):
    """Exact ability registration used by move_state for these projections."""
    data = _load(str(rules.root))
    matches = []
    for printed, row in data["abilities"].items():
        aliases = {printed, row["ability_id"], row["ability_title"]}
        if name in aliases or name in row["candidate_ids"]:
            matches.append((printed, row))
    # Several Features legitimately share one catalog Ability; collapse only
    # identical selected identities.
    selected = {(row["ability_id"], row["ability_title"]) for _, row in matches}
    if len(selected) > 1:
        raise ValueError("ambiguous acquired-Feature Ability registration")
    if not matches:
        return None
    printed, row = matches[0]
    ability_id, title = _ability(rules, printed)
    return {"name": title, "source_id": ability_id, "equivalent_source_ids": list(row["equivalent_ids"])}


def _move(rules, printed):
    data = _load(str(rules.root))
    row = data["moves"].get(printed)
    if row is None:
        raise ValueError("unreviewed acquired-Feature move: " + str(printed))
    uid = row["move_id"]
    move = rules.moves.get(uid)
    if not isinstance(move, dict) or rules.move_id(row["catalog_name"]) != uid or rules._selected_rule(uid) != uid:
        raise ValueError("reviewed acquired-Feature move is not selected: " + printed)
    source = move.get("_source", {})
    if (
        move.get("eng") != row["eng"]
        or "input/" + str(source.get("file", "")) != row["source_file"]
        or source.get("record_span") != row["source_record_span"]
        or uid in getattr(rules, "excluded_moves", {})
    ):
        raise ValueError("reviewed acquired-Feature move provenance changed: " + printed)
    return uid


def _choice_map(actor):
    choices = actor.spec.get("feature_choices", {})
    if not isinstance(choices, dict):
        raise ValueError("acquired Feature choices must be a mapping")
    return choices


def _source_choice(actor, uid):
    matches = [value for key, value in _choice_map(actor).items() if identity(actor.r, key) == uid]
    if len(matches) > 1:
        raise ValueError("duplicate aliases for acquired Feature choice")
    return matches[0] if matches else None


def _ability_choice(actor, uid, row, rank):
    raw = _source_choice(actor, uid)
    if not isinstance(raw, (list, tuple)) or len(raw) != rank or any(not isinstance(value, str) for value in raw):
        raise ValueError("one explicit Ability choice required per acquired Feature rank: " + uid)
    allowed = row["abilities"]
    result = []
    for value in raw:
        candidates = [printed for printed in allowed if value in {
            printed,
            _load(str(actor.r.root))["abilities"][printed]["ability_id"],
            _load(str(actor.r.root))["abilities"][printed]["ability_title"],
        }]
        if len(candidates) != 1:
            raise ValueError("Ability choice outside its printed domain: " + uid)
        result.append(_ability(actor.r, candidates[0]))
    if len({ability_id for ability_id, _ in result}) != len(result):
        raise ValueError("ranked Ability choices must be distinct: " + uid)
    return result, list(raw)


def _derived_choice(actor, uid, row):
    import static_feature_state_grants as STATIC
    value = STATIC.class_branch(actor, row["derived_from"])
    if value is None:
        aliases = {row["derived_from"], "무리군주", "Swarmlord"}
        matches = [value for key, value in _choice_map(actor).items() if key in aliases]
        if len(matches) != 1:
            raise ValueError("one actual prior embrace choice required: " + uid)
        value = matches[0]
    else:
        aliases = {row["derived_from"], "무리군주", "Swarmlord"}
        legacy = [choice for key, choice in _choice_map(actor).items() if key in aliases]
        if any(choice not in (value, [value], (value,)) for choice in legacy):
            raise ValueError("descendant choice disagrees with its owned class branch: " + uid)
    if isinstance(value, (list, tuple)) and len(value) == 1:
        value = value[0]
    if value not in row["ability_by_choice"]:
        raise ValueError("prior embrace choice outside its printed domain: " + uid)
    printed = row["ability_by_choice"][value]
    return [_ability(actor.r, printed)], [value]


def _move_choice(actor, uid, row):
    raw = _source_choice(actor, uid)
    if not isinstance(raw, (list, tuple)) or len(raw) != row["choose"] or any(not isinstance(value, str) for value in raw):
        raise ValueError("exact printed move selection required: " + uid)
    allowed = row["moves"]
    ids = []
    for value in raw:
        candidates = [printed for printed in allowed if value in {
            printed,
            _load(str(actor.r.root))["moves"][printed]["catalog_name"],
            _load(str(actor.r.root))["moves"][printed]["move_id"],
        }]
        if len(candidates) != 1:
            raise ValueError("move choice outside its printed domain: " + uid)
        ids.append(_move(actor.r, candidates[0]))
    if len(set(ids)) != len(ids):
        raise ValueError("selected acquired Feature moves must be distinct: " + uid)
    return ids, list(raw)


def plan(engine, actor, uid):
    if actor.kind != "trainer" or not _owned(actor, uid):
        raise ValueError("actual trainer Feature acquisition required")
    row = _rule(engine.r, uid)
    rank = ACQUIRED.feature_rank(actor, uid)
    if rank > row["rank_max"]:
        raise ValueError("acquired Feature rank exceeds reviewed projection")
    abilities = []
    moves = []
    selection = []
    if row["mode"] == "ability_choice":
        abilities, selection = _ability_choice(actor, uid, row, rank)
    elif row["mode"] == "derived_ability":
        abilities, selection = _derived_choice(actor, uid, row)
    elif row["mode"] == "move_choice":
        moves, selection = _move_choice(actor, uid, row)
    elif row["mode"] == "fixed":
        if _source_choice(actor, uid) is not None:
            raise ValueError("fixed acquired Feature projection has no selectable output: " + uid)
        abilities = [_ability(engine.r, name) for name in row.get("abilities", [])]
        moves = [_move(engine.r, name) for name in row.get("moves", [])]
    else:
        raise ValueError("unsupported acquired Feature projection mode")
    return {
        "rule_id": uid,
        "clause_id": row["clause_id"],
        "rank": rank,
        "selection": selection,
        "ability_ids": [ability_id for ability_id, _ in abilities],
        "ability_names": [name for _, name in abilities],
        "move_ids": moves,
    }


def _source_key(actor, uid):
    return "feature:" + actor.entity_id + ":" + uid


def _managed(actor):
    current = actor.spec.get(GRANTS.KEY)
    if current is None:
        return {}, {}
    if not isinstance(current, dict) or current.get("version") != 1 or not isinstance(current.get("sources"), dict):
        raise ValueError("unsupported source-grant state")
    all_sources = current["sources"]
    managed = {key: row for key, row in all_sources.items() if isinstance(row, dict) and row.get(TAG) == 1}
    prefix = "feature:" + actor.entity_id + ":"
    policy_sources = set(sources(actor.r))
    for key, row in managed.items():
        uid = row.get("rule_id")
        if (
            uid not in policy_sources
            or key != prefix + uid
            or row.get("kind") != "feature"
            or row.get("owner_id") != actor.entity_id
            or row.get("lifetime") != "while_owned"
            or row.get("tutor_points") != 0
            or row.get("projection_clause_id") != _load(str(actor.r.root))["rules"][uid]["clause_id"]
        ):
            raise ValueError("acquired Feature projection provenance is invalid")
        grants = row.get("grants", {})
        if grants.get("abilities", []) != row.get("projection_ability_names", []) or grants.get("moves", []) != row.get("projection_move_ids", []):
            raise ValueError("acquired Feature projection receipt disagrees with its grants")
    return all_sources, managed


def register_all(engine, actor):
    """Plan and reconcile all seventeen sources as one atomic transition."""
    if actor.kind != "trainer":
        return 0
    desired_rows = [plan(engine, actor, uid) for uid in sources(actor.r) if _owned(actor, uid)]
    all_sources, managed = _managed(actor)
    desired = {_source_key(actor, row["rule_id"]): row for row in desired_rows}
    for key in desired:
        if key in all_sources and key not in managed:
            raise ValueError("acquired Feature source collides with another projection")
    for key, value in desired.items():
        prior = managed.get(key, {}).get("projection_selection")
        current = value["selection"]
        if prior is not None and prior[:min(len(prior), len(current))] != current[:min(len(prior), len(current))]:
            raise ValueError("acquired Feature projection choice cannot be silently replaced")
    def signature(row):
        return (
            row.get("projection_rank"), row.get("projection_selection"),
            row.get("projection_ability_ids"), row.get("projection_move_ids"),
        )
    changed = set(managed) != set(desired) or any(
        signature(managed.get(key, {})) != (
            value["rank"], value["selection"], value["ability_ids"], value["move_ids"]
        ) for key, value in desired.items()
    )
    if not changed:
        return 0

    def apply(staged_engine, staged_actor):
        for key in managed:
            if key not in desired or signature(managed[key]) != (
                desired[key]["rank"], desired[key]["selection"],
                desired[key]["ability_ids"], desired[key]["move_ids"],
            ):
                GRANTS.revoke(staged_actor, key, engine=staged_engine)
        for key, value in desired.items():
            uid = value["rule_id"]
            for name in value["ability_names"]:
                GRANTS.grant(staged_actor, "abilities", name, key, "feature",
                             owner_id=staged_actor.entity_id, lifetime="while_owned",
                             rule_id=uid, tutor_points=0)
                staged_engine.register_abilities_one(staged_actor, name)
            if value["move_ids"]:
                GRANTS.grant_moves(staged_actor, value["move_ids"], key, "feature",
                                   owner_id=staged_actor.entity_id, lifetime="while_owned",
                                   rule_id=uid, tutor_points=0)
            row = GRANTS.state(staged_actor)["sources"][key]
            row.update({
                TAG: 1,
                "projection_clause_id": value["clause_id"],
                "projection_rank": value["rank"],
                "projection_selection": value["selection"],
                "projection_ability_ids": value["ability_ids"],
                "projection_ability_names": value["ability_names"],
                "projection_move_ids": value["move_ids"],
            })
        return len(desired)

    return GRANTS.transition(engine, actor, apply)
