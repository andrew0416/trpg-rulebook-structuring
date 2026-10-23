"""Exact acquired Static Feature/Class/Gift state projections.

The table owns only the persistent result of an already acquired source.  It
does not acquire a Feature or waive prerequisites.  Every result is installed
through ``state_grants`` so removal, independent ownership and codec restore
share one reversible state contract.
"""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path

import acquired_features as ACQUIRED
import state_grants as GRANTS
from ruleset import ExcludedRuleSelection

POLICY_PATH = "data/static-feature-state-grants-policy.json"
KIND = "feature"
STAT_ALIASES = {"공격":"atk", "방어":"def", "특수공격":"spa", "특수방어":"spd", "스피드":"spe"}


import resolution_transaction as _FINGERPRINTS

def _path(rules):
    path = Path(rules.root) / POLICY_PATH
    if not path.is_file():
        staged = Path(__file__).resolve().parent.parent / POLICY_PATH
        if staged.is_file():
            path = staged
    return path


def _policy(rules):
    cached = getattr(rules, "_static_feature_state_policy", None)
    if cached is not None:
        return cached
    data = json.loads(_path(rules).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("contract") != "acquired_static_feature_state_projection":
        raise ValueError("unsupported Static Feature state policy")
    declared = data.get("rules")
    if not isinstance(declared, dict) or len(declared) != 47 or any(row.get("id") != cid for cid,row in declared.items()):
        raise ValueError("Static Feature policy must contain 47 exact rules")
    for relative, digest in data.get("source_files", {}).items():
        if hashlib.sha256((Path(rules.root) / relative).read_bytes()).hexdigest() != digest:
            raise ValueError("Static Feature source changed: " + relative)
    authority = data.get("stat_tag_authority", {})
    if (authority.get("source_file") != "input/ch03-skills-edges-feats.md"
            or authority.get("lines") != [605,607]):
        raise ValueError("exact ranked stat-tag authority required")
    lines = (Path(rules.root)/authority["source_file"]).read_text(encoding="utf-8-sig").splitlines()
    excerpt = "\n".join(lines[604:607])
    if (excerpt != authority.get("excerpt")
            or hashlib.sha256(excerpt.encode()).hexdigest() != authority.get("excerpt_sha256")):
        raise ValueError("ranked stat-tag source changed")
    csv_cache = {}
    for cid,row in declared.items():
        if "csv_record" in row:
            relative = row["source_file"]
            if relative not in csv_cache:
                with (Path(rules.root)/relative).open(encoding="utf-8-sig", newline="") as handle:
                    csv_cache[relative] = list(csv.reader(handle))
            record = row["csv_record"]
            columns = row["columns"]
            actual = [csv_cache[relative][record-1][column-1] for column in columns]
            digest = _FINGERPRINTS.json_fingerprint(actual, sort_keys=False, compact=True, allow_nan=True)
            if actual != row["cells"] or digest != row["cell_sha256"]:
                raise ValueError("Static Feature source cells changed: " + cid)
        else:
            bounds = row.get("lines")
            lines = (Path(rules.root)/row["source_file"]).read_text(encoding="utf-8").splitlines()
            actual = "\n".join(lines[bounds[0]-1:bounds[1]])
            if actual != row.get("excerpt") or hashlib.sha256(actual.encode()).hexdigest() != row.get("excerpt_sha256"):
                raise ValueError("Static Feature source excerpt changed: " + cid)
        owner = row.get("owner_id")
        if owner is not None and owner not in rules.selection.units:
            raise ValueError("Static Feature owner binding changed: " + cid)
        if row.get("mode") == "ranked_stat":
            unit = rules.selection.units.get(owner, {})
            tag = row.get("tag")
            stat = {"+HP":"hp", "+공격":"atk", "+방어":"def", "+특수공격":"spa",
                    "+특수방어":"spd", "+스피드":"spe"}.get(tag)
            if (not isinstance(owner,str) or not owner.startswith("feat/")
                    or stat is None or row.get("stat") != stat or tag not in unit.get("tags", ())
                    or not any(str(value).startswith("랭크") for value in unit.get("tags", ()))):
                raise ValueError("ranked stat projection requires its exact printed Feature tags")
        for binding in row.get("equivalent_sources", {}).values():
            unit = rules.selection.units.get(binding["owner_id"], {})
            source = unit.get("source", {})
            relative = binding["source_file"]
            bounds = binding["lines"]
            span = source.get("lines", ())
            if ("input/" + str(source.get("file", "")) != relative
                    or source.get("sha256") != data["source_files"].get(relative)
                    or len(span) != 2 or not span[0] <= bounds[0] <= bounds[1] <= span[1]):
                raise ValueError("equivalent Static Feature owner changed: " + cid)
            lines = (Path(rules.root) / relative).read_text(encoding="utf-8").splitlines()
            excerpt = "\n".join(lines[bounds[0]-1:bounds[1]])
            if hashlib.sha256(excerpt.encode()).hexdigest() != binding["excerpt_sha256"]:
                raise ValueError("equivalent Static Feature source changed: " + cid)
        for move_id in list(row.get("moves", ())) + list(row.get("move_immune", ())):
            unit = rules.selection.units.get(move_id)
            if unit is None or not move_id.startswith("move/"):
                raise ValueError("Static Feature move binding changed: " + cid)
        ability_rows = list(row.get("abilities", ()))
        for branch in row.get("branches", {}).values():
            ability_rows.extend(branch.get("abilities", ()))
        for ability in ability_rows:
            uid,title = ability.get("id"),ability.get("title")
            unit = rules.selection.units.get(uid, {})
            if unit.get("title") != title or not uid.startswith("ability/") or title not in rules.ability_effects:
                raise ValueError("Static Feature Ability binding changed: " + cid)
    rules._static_feature_state_policy = data
    return data


def rules(rules):
    return _policy(rules)["rules"]


def _row_enabled(rules, row):
    """Return whether every exact source identity is active in this profile.

    The hash-pinned table spans core, fantasy, and playtest records.  Loading
    the table validates the whole catalog, while an actor may consume only the
    exact identities admitted by its current ruleset.  An excluded dependency
    disables that row; unresolved/conflicting selection still fails loudly.
    """
    identities = []
    owner = row.get("owner_id")
    if owner is not None:
        identities.append(owner)
    identities.extend(row.get("moves", ()))
    identities.extend(row.get("move_immune", ()))
    abilities = list(row.get("abilities", ()))
    for branch in row.get("branches", {}).values():
        abilities.extend(branch.get("abilities", ()))
    identities.extend(ability["id"] for ability in abilities)
    for uid in identities:
        try:
            if rules._selected_rule(uid) != uid:
                return False
        except ExcludedRuleSelection:
            return False
    return True


def _owner_aliases(rules, row):
    # A conflicting CSV recipe cannot borrow the Markdown Feature identity.
    # The source record itself is the existing explicit acquisition identity.
    if row.get("explicit_source"):
        return {row["id"]}
    owner = row.get("owner_id")
    if owner is None:
        aliases = {row["id"], row["name"]}
    else:
        unit = rules.selection.units[owner]
        aliases = {owner, unit.get("title"), unit.get("eng")}
        if owner.startswith("gift/"):
            aliases.update(uid for uid in rules.selection.names.get(unit.get("title"), ()) if uid.startswith(("gift/","feat/")))
    for binding in row.get("equivalent_sources", {}).values():
        uid = binding["owner_id"]
        unit = rules.selection.units[uid]
        aliases.update((uid, unit.get("title"), unit.get("eng")))
    return {value for value in aliases if value}


def identity(rules, value):
    if not isinstance(value, str):
        return None
    matches = [cid for cid,row in _policy(rules)["rules"].items() if value in _owner_aliases(rules,row)]
    if len(matches) > 1:
        raise ValueError("ambiguous Static Feature identity: " + value)
    return matches[0] if matches else None


def _owned_values(actor):
    values = []
    for field in ("classes","feats","gifts"):
        raw = actor.spec.get(field, [])
        if not isinstance(raw, (list,tuple)):
            raise ValueError("acquired Static Feature identities must be lists")
        values.extend(raw)
    return values


def _owned(actor, cid, row):
    matches = [value for value in _owned_values(actor) if identity(actor.r,value) == cid]
    if len(matches) > 1:
        raise ValueError("duplicate aliases for acquired Static Feature: " + cid)
    if matches and str(row.get("owner_id", "")).startswith("gift/"):
        import blessing_skill_features as BLESSINGS
        if not BLESSINGS.approval(actor,row["owner_id"]):
            raise ValueError("Static Gift requires actual acquired gifts and GM permission")
    for binding in row.get("equivalent_sources", {}).values():
        uid = binding["owner_id"]
        unit = actor.r.selection.units[uid]
        if matches and matches[0] in (uid, unit.get("title"), unit.get("eng")):
            if actor.r._selected_rule(uid) != uid:
                raise ValueError("equivalent Static Feature needs its own selected-source policy")
    return bool(matches)


def _raw_choice(actor, cid, row):
    # These selections describe the persistent result of this exact printed
    # row (for example its stat tag), not a move choice or an acquisition
    # branch.  Keeping a dedicated namespace prevents a fixed-move Feature
    # with a stat choice from being misread as a selectable move Feature.
    choices = actor.spec.get("static_feature_choices", {})
    if not isinstance(choices, dict):
        raise ValueError("Static Feature state choices must be a mapping")
    aliases = _owner_aliases(actor.r,row)
    matches = [value for key,value in choices.items() if key in aliases or key == cid]
    if len(matches) > 1:
        raise ValueError("duplicate aliases for Static Feature choice: " + cid)
    if not matches:
        return None
    value = matches[0]
    if isinstance(value,(list,tuple)) and len(value) == 1:
        value = value[0]
    return value


def _stat_choice(actor,cid,row):
    value = _raw_choice(actor,cid,row)
    value = STAT_ALIASES.get(value,value)
    if value not in row["stat_choice"]:
        raise ValueError("one explicit Static Feature stat choice required: " + cid)
    return value


def _class_feature_count(actor, marker):
    count = 1
    seen = set()
    for value in actor.spec.get("feats", []):
        candidates = ([value] if value in actor.r.selection.units and value.startswith("feat/") else
                      [uid for uid in actor.r.selection.names.get(value, ()) if uid.startswith("feat/")])
        if not candidates:
            continue
        if len(candidates) != 1 or candidates[0] in seen:
            raise ValueError("unambiguous distinct class Feature sources required")
        uid = candidates[0]; seen.add(uid)
        path = actor.r.selection.units[uid].get("source",{}).get("path",())
        if any(str(part).split("(",1)[0].strip() == marker for part in path):
            count += ACQUIRED.feature_rank(actor,uid)
    return count


def _plan_one(actor,cid,row):
    if row.get("mode") == "martial":
        import trainer_feature_acquisition as MARTIAL
        try:
            selected = MARTIAL.martial_ability(actor)
        except ValueError:
            if any(value in _owner_aliases(actor.r,row) for value in _owned_values(actor)):
                raise
            return None
        if selected not in row["stat_by_ability"]:
            raise ValueError("unreviewed Martial Artist Ability")
        count = ACQUIRED.count_for_class(actor,row["owner_id"])
        return dict(stat=row["stat_by_ability"][selected],count=count,selection=selected)
    if not _owned(actor,cid,row):
        return None
    if row.get("mode") == "signature_stat":
        import signature_moves as SIGNATURE
        stat = SIGNATURE.stat_choice(actor)
        return dict(stat=stat, count=1, selection=stat)
    if row.get("mode") == "ranked_stat":
        return dict(stat=row["stat"], count=ACQUIRED.feature_rank(actor,row["owner_id"]))
    if row.get("mode") == "class_branch":
        branch = _raw_choice(actor,cid,row)
        if branch not in row["branches"]:
            raise ValueError("one explicit Static class branch required: " + cid)
        result = deepcopy(row["branches"][branch])
        result.update(count=_class_feature_count(actor,row["class_marker"]),selection=branch)
        return result
    result = {key:deepcopy(row[key]) for key in ("moves","abilities","capabilities","status_immune","weather_immune","keyword_immune","move_immune","stat") if key in row}
    if "stat_choice" in row:
        result["stat"] = _stat_choice(actor,cid,row)
        result["selection"] = result["stat"]
    result["count"] = 1
    return result


def plan(actor):
    if actor.kind != "trainer":
        return {}
    ACQUIRED.validate_class_slots(actor)
    result = {}
    for cid,row in _policy(actor.r)["rules"].items():
        if not _row_enabled(actor.r, row):
            continue
        declaration = _plan_one(actor,cid,row)
        if declaration is not None:
            result[cid] = declaration
    return result


def class_branch(actor, owner):
    """Read the same owned branch used by ability and class-stat projection.

    A descendant may query either the reviewed owner or the original CSV
    contract. This does not grant ownership or create a second choice store.
    """
    cid = identity(actor.r, owner)
    if cid is None:
        return None
    row = _policy(actor.r)["rules"][cid]
    if row.get("mode") != "class_branch" or not _row_enabled(actor.r, row):
        return None
    declaration = _plan_one(actor, cid, row)
    if declaration is None:
        return None
    prior = actor.spec.get(GRANTS.KEY, {}).get("sources", {}).get(_source(actor, cid))
    if prior is not None and prior.get("selection") != declaration["selection"]:
        raise ValueError("Static class branch cannot be silently replaced")
    return declaration["selection"]


def _source(actor,cid):
    row = _policy(actor.r)["rules"][cid]
    owner = row.get("owner_id")
    # Keep the established feature source identity so saved state and existing
    # regression consumers migrate in place to this reviewed table.
    if isinstance(owner,str) and owner.startswith("feat/") and not row.get("explicit_source"):
        return "feature:" + actor.entity_id + ":" + owner
    return "static-feature:" + actor.entity_id + ":" + cid


def _install(engine,actor,cid,declaration):
    row = _policy(actor.r)["rules"][cid]
    source = _source(actor,cid)
    rule_id = row.get("owner_id") or cid
    metadata = dict(owner_id=actor.entity_id,lifetime="while_owned",rule_id=rule_id,tutor_points=0,
                    clause_id=cid,source_contract="acquired_static_feature_state_projection")
    if "selection" in declaration:
        metadata["selection"] = declaration["selection"]
    previous = actor.spec.get(GRANTS.KEY,{}).get("sources",{}).get(source)
    existed = previous is not None
    changed = not existed or previous.get("source_contract") != "acquired_static_feature_state_projection"
    GRANTS._source(actor,source,KIND,**metadata)
    grant_args = dict(owner_id=actor.entity_id,lifetime="while_owned",rule_id=rule_id,tutor_points=0)
    if declaration.get("moves"):
        # One batch preserves all-or-nothing move-slot validation.
        changed = GRANTS.grant_moves(actor,declaration["moves"],source,KIND,**grant_args) or changed
    for ability in declaration.get("abilities",()):
        changed = GRANTS.grant(actor,"abilities",ability["title"],source,KIND,**grant_args) or changed
        GRANTS.ensure_ability(engine,actor,ability["title"])
    for capability in declaration.get("capabilities",()):
        changed = GRANTS.grant(actor,"capabilities",capability,source,KIND,**grant_args) or changed
    for field in ("status_immune","weather_immune","keyword_immune","move_immune"):
        for value in declaration.get(field,()):
            before = value in getattr(actor,field,set())
            GRANTS.set_member(actor,field,value,source)
            changed = changed or not before
    if declaration.get("stat"):
        changed = GRANTS.reconcile_stat(actor,declaration["stat"],declaration.get("count",1),source,operation_id="feature_count") or changed
    return changed


def register_all(engine,actor):
    """Atomically reconcile all reviewed while-owned projections."""
    desired = plan(actor)
    current = {key for key,row in actor.spec.get(GRANTS.KEY,{}).get("sources",{}).items()
               if row.get("source_contract") == "acquired_static_feature_state_projection"}
    desired_sources = {_source(actor,cid) for cid in desired}
    if not desired and not current:
        return 0
    def apply(staged_engine,staged_actor):
        changed = 0
        for source in sorted(current-desired_sources):
            changed += bool(GRANTS.revoke(staged_actor,source,engine=staged_engine))
        for cid,declaration in desired.items():
            changed += _install(staged_engine,staged_actor,cid,declaration)
        return changed
    return GRANTS.transition(engine,actor,apply)


def validate(actor):
    """Validate only receipts owned by this adapter; codec callers stay pure."""
    expected = plan(actor)
    state = actor.spec.get(GRANTS.KEY,{})
    actual = {row.get("clause_id"):row for row in state.get("sources",{}).values()
              if row.get("source_contract") == "acquired_static_feature_state_projection"}
    if set(actual) != set(expected):
        raise ValueError("Static Feature state is stale; reconcile owned sources")
    for cid,declaration in expected.items():
        row = actual[cid]
        source = _source(actor,cid)
        if row.get("owner_id") != actor.entity_id or row.get("lifetime") != "while_owned" or row.get("source_contract") != "acquired_static_feature_state_projection":
            raise ValueError("Static Feature provenance changed: " + cid)
        if row.get("selection") != declaration.get("selection"):
            raise ValueError("Static Feature immutable choice changed: " + cid)
        for field in ("moves","abilities","capabilities"):
            desired = ([value["title"] for value in declaration[field]]
                       if field == "abilities" and field in declaration else declaration.get(field,()))
            if field in declaration and set(row.get("grants",{}).get(field,())) != set(desired):
                raise ValueError("Static Feature grant receipt changed: " + cid + ":" + field)
        for field in ("status_immune","weather_immune","keyword_immune","move_immune"):
            if field not in declaration:
                continue
            receipt = state.get("sets",{}).get(field,{}).get("sources",{}).get(source,())
            if set(receipt) != set(declaration[field]):
                raise ValueError("Static Feature immunity receipt changed: " + cid + ":" + field)
        if declaration.get("stat"):
            receipt = state.get("stat_sources",{}).get(declaration["stat"],{}).get("sources",{}).get(source,{})
            if receipt.get("feature_count") != {"delta":declaration.get("count",1),"minimum":None}:
                raise ValueError("Static Feature stat receipt changed: " + cid)
    return True

