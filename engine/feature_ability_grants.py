"""Exact one-of ability choices projected from already-acquired features.

Acquisition and prerequisite approval remain with the character sheet.  This
module owns only the selected ability projection, its source lifetime, and the
native ability registration.  Every owned source is planned before a staged
transition so one invalid choice cannot leave another source half-registered.
"""
import acquired_features as ACQUIRED
import state_grants as GRANTS


DECLARATIONS = {
    "feat/분노의-힘": ("불굴의격노", "화이트플레임"),
    "feat/다크-소울": ("그림자밟기", "대운"),
    "feat/번개의-몸": ("축전", "전기엔진"),
    "feat/빙하-방어": ("아이스실드", "겨울의입맞춤"),
    "feat/불쾌한-몸": ("힘흡수", "독가시", "독수"),
}
SOURCES = tuple(DECLARATIONS)

# The translated feature prose separates two names whose ability catalog
# identities are closed compounds.  These are reviewed spellings, not fuzzy
# aliases.
PRINTED_ALIASES = {
    "아이스 실드": "아이스실드",
    "겨울의 입맞춤": "겨울의입맞춤",
}

def identity(rules, name):
    """Resolve only one of the five reviewed feature sources."""
    if not isinstance(name, str):
        raise ValueError("feature ability source must be a text identity")
    found = []
    for uid in SOURCES:
        unit = rules.selection.units[uid]
        if name in tuple(value for value in (uid, unit.get("title"), unit.get("eng")) if value):
            found.append(uid)
    if len(found) > 1:
        raise ValueError("ambiguous feature ability source")
    return found[0] if found else None


def _owned(actor, uid):
    values = actor.spec.get("feats", [])
    if not isinstance(values, (list, tuple)):
        raise ValueError("acquired feature list required")
    if any(not isinstance(value, str) for value in values):
        raise ValueError("acquired feature identity must be text")
    matches = [value for value in values if identity(actor.r, value) == uid]
    if len(matches) > 1:
        raise ValueError("duplicate acquired feature ability source")
    return bool(matches)


def _choice(actor, uid):
    choices = actor.spec.get("feature_choices", {})
    if not isinstance(choices, dict):
        raise ValueError("feature choices must be a mapping")
    matches = [value for key, value in choices.items() if identity(actor.r, key) == uid]
    if len(matches) > 1:
        raise ValueError("duplicate aliases for feature ability choice")
    return matches[0] if matches else None


def _ability(rules, uid, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("feature ability choice must be a named ability")
    raw = PRINTED_ALIASES.get(value.strip(), value.strip())
    if raw.startswith("ability/") and raw in rules.selection.units:
        ability_id = raw
    else:
        ability_id = rules.selection.resolve_name(raw, ("ability/",))
    allowed = {rules.selection.resolve_name(name, ("ability/",)) for name in DECLARATIONS[uid]}
    if ability_id not in allowed:
        raise ValueError("feature ability choice outside its printed domain: " + uid)
    if rules._selected_rule(ability_id) != ability_id:
        raise ValueError("selected ability variant requires its own policy")
    name = rules.selection.units[ability_id].get("title")
    if not isinstance(name, str) or name not in rules.ability_effects:
        raise ValueError("selected feature ability lacks an exact executable definition")
    if name in getattr(rules, "excluded_abilities", {}):
        raise ValueError("selected feature ability belongs to an excluded source")
    return ability_id, name


def plan(engine, actor, uid):
    """Pure plan for one actual acquired source and its one explicit choice."""
    if actor.kind != "trainer" or not _owned(actor, uid):
        raise ValueError("actual trainer feature acquisition required")
    if engine.r._selected_rule(uid) != uid:
        raise ValueError("selected feature ability source requires its own policy")
    if ACQUIRED.feature_rank(actor, uid) != 1:
        raise ValueError("feature ability choice requires one acquired source rank")
    chosen = _choice(actor, uid)
    if not isinstance(chosen, (list, tuple)) or len(chosen) != 1:
        raise ValueError("exactly one explicit ability choice required per acquired feature")
    ability_id, ability_name = _ability(engine.r, uid, chosen[0])
    return {"rule_id": uid, "ability_id": ability_id, "ability_name": ability_name}


def _source_key(actor, uid):
    return "feature:" + actor.entity_id + ":" + uid


def _stored_ability(rules, uid, row):
    """Validate the narrow owned row without changing or selecting live state."""
    if not isinstance(row, dict):
        raise ValueError("feature ability projection must be a source record")
    ability_id = row.get("feature_ability_selection")
    allowed = {"ability/" + name for name in DECLARATIONS[uid]}
    if ability_id not in allowed or ability_id not in rules.selection.units:
        raise ValueError("feature ability projection has an invalid stored choice")
    name = rules.selection.units[ability_id].get("title")
    grants = row.get("grants")
    if not isinstance(grants, dict) or set(grants) != {"abilities"} or grants.get("abilities") != [name]:
        raise ValueError("feature ability projection disagrees with its owned ability")
    if row.get("feature_ability_name") != name:
        raise ValueError("feature ability projection name disagrees with its identity")
    return ability_id, name


def _managed(actor):
    current = actor.spec.get(GRANTS.KEY)
    if current is None:
        return {}, {}
    if not isinstance(current, dict) or current.get("version") != 1 or not isinstance(current.get("sources"), dict):
        raise ValueError("unsupported source-grant state")
    sources = current["sources"]
    managed = {key: row for key, row in sources.items() if isinstance(row, dict) and row.get("feature_ability_projection") == 1}
    prefix = "feature:" + actor.entity_id + ":"
    for key, row in managed.items():
        uid = row.get("rule_id")
        if (uid not in DECLARATIONS or key != prefix + uid or row.get("kind") != "feature"
                or row.get("owner_id") != actor.entity_id or row.get("lifetime") != "while_owned"
                or row.get("tutor_points") != 0):
            raise ValueError("feature ability projection provenance is invalid")
        _stored_ability(actor.r, uid, row)
    return sources, managed


def register_all(engine, actor):
    """Reconcile all five projections as one atomic owned-state change."""
    if actor.kind != "trainer":
        return 0
    selected = [plan(engine, actor, uid) for uid in SOURCES if _owned(actor, uid)]
    sources, managed = _managed(actor)
    desired = {_source_key(actor, value["rule_id"]): value for value in selected}

    # A different subsystem may not silently share these feature-owned keys.
    for key in desired:
        if key in sources and key not in managed:
            raise ValueError("feature ability source collides with an existing projection")
    for key, value in desired.items():
        previous = managed.get(key, {}).get("feature_ability_selection")
        if previous is not None and previous != value["ability_id"]:
            raise ValueError("acquired feature ability choice cannot be silently replaced")

    changed = set(managed) != set(desired) or any(
        managed.get(key, {}).get("feature_ability_selection") != value["ability_id"]
        for key, value in desired.items()
    )
    if not changed:
        return 0

    def apply(staged_engine, staged_actor):
        for key in managed:
            if key not in desired:
                GRANTS.revoke(staged_actor, key, engine=staged_engine)
        for key, value in desired.items():
            GRANTS.grant(
                staged_actor, "abilities", value["ability_name"], key, "feature",
                owner_id=staged_actor.entity_id, lifetime="while_owned",
                rule_id=value["rule_id"], tutor_points=0,
            )
            staged_engine.register_abilities_one(staged_actor, value["ability_name"])
            row = GRANTS.state(staged_actor)["sources"][key]
            row.update(
                feature_ability_projection=1,
                feature_ability_selection=value["ability_id"],
                feature_ability_name=value["ability_name"],
            )
        return len(desired)

    return GRANTS.transition(engine, actor, apply)
