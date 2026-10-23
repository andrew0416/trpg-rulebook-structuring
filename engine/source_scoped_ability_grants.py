"""Resolve a bare granted Ability only from an exact owning rule and version.

The source rules in this policy print an unversioned Ability name while the
catalog keeps its executable definition under a versioned identity.  A global
alias would silently affect unrelated rules, so resolution is restricted to
the reviewed Feature, its exact extracted effect, and its recorded source.
"""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json


POLICY = "data/fixed-feature-ability-grant-policy.json"


@lru_cache(maxsize=None)
def _load(root):
    base = Path(root)
    path = base / POLICY
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("contract") != "fixed owned feature ability projection":
        raise ValueError("reviewed source-scoped Ability grant policy required")
    rules = data.get("rules")
    if not isinstance(rules, dict) or not rules:
        raise ValueError("nonempty source-scoped Ability grant policy required")
    for source_file, digest in data.get("source_files", {}).items():
        candidate = base / source_file
        if not candidate.is_file() or sha256(candidate.read_bytes()).hexdigest() != digest:
            raise ValueError("source-scoped Ability grant evidence changed: " + source_file)
    return data


def _candidate_ids(rules, printed):
    """Exact display-family inventory; no fuzzy aliases or English matching."""
    return sorted(
        uid for uid, unit in rules.selection.units.items()
        if uid.startswith("ability/")
        and (unit.get("title") == printed or str(unit.get("title", "")).startswith(printed + " ["))
    )


def _validate_rule(rules, source_rule_id, row):
    if rules._selected_rule(source_rule_id) != source_rule_id:
        raise ValueError("owning Feature version is not selected: " + source_rule_id)
    unit = rules.selection.units.get(source_rule_id)
    if not isinstance(unit, dict):
        raise ValueError("owning Feature identity is absent: " + source_rule_id)
    source = unit.get("source", {})
    actual_file = "input/" + str(source.get("file", ""))
    if actual_file != row["source_file"] or source.get("lines") != row["source_lines"]:
        raise ValueError("owning Feature source span changed: " + source_rule_id)
    policy = _load(str(rules.root))
    if source.get("sha256") != policy["source_files"].get(actual_file):
        raise ValueError("owning Feature source version changed: " + source_rule_id)
    effects, header = rules.feat_effects(source_rule_id)
    if effects != row["expected_effects"]:
        raise ValueError("owning Feature Ability extraction changed: " + source_rule_id)
    frequency = header.get("frequency") or {}
    if frequency.get("kind") != "static" or frequency.get("action") != "static":
        raise ValueError("source-scoped Ability grant is no longer static: " + source_rule_id)
    return unit


def _validate_ability(rules, row):
    printed = row["printed_ability"]
    candidates = _candidate_ids(rules, printed)
    if candidates != row["candidate_ability_ids"]:
        raise ValueError("Ability version candidates changed for: " + printed)
    ability_id = row["ability_id"]
    if ability_id not in candidates or rules._selected_rule(ability_id) != ability_id:
        raise ValueError("reviewed Ability version is not selected: " + ability_id)
    unit = rules.selection.units.get(ability_id)
    if not isinstance(unit, dict):
        raise ValueError("reviewed Ability identity is absent: " + ability_id)
    source = unit.get("source", {})
    actual_file = "input/" + str(source.get("file", ""))
    policy = _load(str(rules.root))
    if (
        unit.get("title") != row["ability_title"]
        or unit.get("eng") != row["ability_eng"]
        or unit.get("keyword") != row["ability_keyword"]
        or actual_file != row["ability_source_file"]
        or source.get("record_span") != row["ability_source_record_span"]
        or source.get("sha256") != policy["source_files"].get(actual_file)
    ):
        raise ValueError("reviewed Ability definition provenance changed: " + ability_id)
    title = unit["title"]
    if title not in rules.ability_effects or title in getattr(rules, "excluded_abilities", {}):
        raise ValueError("reviewed Ability version lacks an executable definition: " + ability_id)
    return title


def resolve(rules, effect, source_rule_id=None):
    """Return the exact executable title for one reviewed source, else None."""
    if source_rule_id is None:
        return None
    data = _load(str(rules.root))
    row = data["rules"].get(source_rule_id)
    if row is None:
        return None
    # register_feature_effect adds only execution bookkeeping after the exact
    # extracted effect has passed _validate_rule.  Ignore those two fields,
    # but reject every other mutation so a reviewed binding cannot widen.
    runtime_only = {"target", "_ability"}
    unexpected = set(effect) - set(row["expected_effects"][0]) - runtime_only
    semantic = {key: value for key, value in effect.items() if key not in runtime_only}
    if unexpected or semantic not in row["expected_effects"] or effect.get("type") != "grant_ability":
        raise ValueError("source-scoped Ability grant must match its exact extracted effect")
    if "target" in effect and effect["target"] != "self":
        raise ValueError("source-scoped Ability grant runtime target changed")
    if effect.get("grant_ability") != row["printed_ability"] or effect.get("on") != "self":
        raise ValueError("source-scoped Ability grant text or target changed")
    feature = _validate_rule(rules, source_rule_id, row)
    resolution = row["resolution"]
    if resolution.get("kind") == "only_catalog_definition":
        if row["candidate_ability_ids"] != [row["ability_id"]]:
            raise ValueError("single-definition source became ambiguous: " + source_rule_id)
    elif resolution.get("kind") == "source_marker":
        marker = resolution.get("feature_source_path_marker")
        if not isinstance(marker, str) or not any(marker in str(value) for value in feature["source"].get("path", [])):
            raise ValueError("owning source no longer proves the reviewed Ability version")
        ability = rules.selection.units[row["ability_id"]]
        if ability.get("keyword") != resolution.get("ability_keyword"):
            raise ValueError("Ability keyword no longer matches the owning source version")
    else:
        raise ValueError("unsupported source-scoped Ability resolution")
    return _validate_ability(rules, row)


def clause_ids(rules):
    """Reviewed denominator identities, after validating every live binding."""
    data = _load(str(rules.root))
    for source_rule_id, row in data["rules"].items():
        resolve(rules, row["expected_effects"][0], source_rule_id)
    return tuple(row["clause_id"] for row in data["rules"].values())
