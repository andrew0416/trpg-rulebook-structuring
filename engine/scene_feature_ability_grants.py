"""Scene-lived one-of ability grants from acquired branch Features.

The policy owns source/branch differences.  This module owns the single
activation transaction, source-scoped replacement, scene expiry, and native
ability registration.  It does not infer acquisition from a requested branch.
"""
from copy import deepcopy
from pathlib import Path
import csv
import json

import acquired_features as ACQUIRED
import action_points as AP
import state_grants as GRANTS
import source_selection as SELECTION


POLICY = "data/scene-feature-ability-grant-policy.json"
TAG = "scene_ability_grant"
STAT_FEATURE = "feat/스탯-전형"
STYLE_FEATURE = "feat/스타일-엔트레인먼트"
SOURCES = (STAT_FEATURE, STYLE_FEATURE)
CLASS_CLAUSE_IDS = ("C04-048", "C04-051")
STAT_ALIASES = {
    "공격": "atk", "방어": "def", "특수공격": "spa", "특수방어": "spd", "스피드": "spe",
    "공격 전형": "atk", "방어 전형": "def", "특수공격 전형": "spa",
    "특수방어 전형": "spd", "스피드 전형": "spe",
}


def _policy(rules):
    cached = getattr(rules, "_scene_feature_ability_grant_policy", None)
    if cached is not None:
        return cached
    path = Path(rules.root) / POLICY
    if not path.is_file():
        staged = Path(__file__).resolve().parent.parent / POLICY
        if staged.is_file():
            path = staged
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 2 or set(data.get("features", {})) != set(SOURCES):
        raise ValueError("unsupported scene Feature ability-grant policy")
    sources = data.get("source_files", {})
    if (set(sources) != {"input/db/feats.csv", "input/ch04-trainer-classes.md"}
            or any(not isinstance(digest, str) or not digest for digest in sources.values())):
        raise ValueError("scene ability source snapshots required")
    seen = set()
    for source_id, definitions in data["features"].items():
        if (not isinstance(definitions, list) or not definitions
                or any(row.get("rule_id") != source_id for row in definitions)):
            raise ValueError("complete scene ability source definitions required")
        for definition in definitions:
            source = definition.get("source", {})
            if (set(source) != {"file", "sha256"} or source["file"] not in sources
                    or source["sha256"] != sources[source["file"]]):
                raise ValueError("scene ability definition source snapshot changed")
            values = definition.get("values", {})
            if (values.get("family") not in ("stat_embodiment", "style_entrainment")
                    or values.get("action") != "swift" or values.get("ap") != 1
                    or type(values.get("priority_limited")) is not bool
                    or not isinstance(values.get("branches"), dict) or not values["branches"]):
                raise ValueError("complete scene ability semantic contract required")
            for declaration in values["branches"].values():
                abilities = declaration.get("abilities")
                if (not isinstance(declaration.get("clause_id"), str)
                        or not isinstance(declaration.get("name"), str)
                        or not isinstance(abilities, dict) or len(abilities) != 2
                        or any(not isinstance(printed, str) or not isinstance(uid, str)
                               or not uid.startswith("ability/") for printed, uid in abilities.items())):
                    raise ValueError("invalid scene ability branch declaration")
        # Legacy grant receipts used this exact CSV policy. Keep that producer
        # interpretation available without pretending they were Book grants.
        csv_definitions = [row for row in definitions if row["source"]["file"] == "input/db/feats.csv"]
        if len(csv_definitions) != 1:
            raise ValueError("one retained CSV scene ability definition required")
        feature = csv_definitions[0]["values"]
        branches = feature.get("branches")
        if not isinstance(branches, dict) or not branches:
            raise ValueError("scene ability branches must be declared")
        for branch, declaration in branches.items():
            clause = declaration.get("clause_id")
            physical = declaration.get("physical_row")
            if type(physical) is not int or physical < 2:
                raise ValueError("invalid scene ability branch declaration")
            seen.add(clause)
        aggregate=feature.get("aggregate_clause")
        if aggregate is not None:
            physical=aggregate.get("physical_row");clause=aggregate.get("clause_id")
            if (type(physical) is not int or physical<2
                    or not isinstance(aggregate.get("name"), str) or not isinstance(clause,str)):
                raise ValueError("invalid scene ability aggregate CSV declaration")
            seen.add(clause)
    if len(seen) != 7:
        raise ValueError("scene ability policy must cover seven exact CSV clauses after fan-out")
    rules._scene_feature_ability_grant_policy = data
    return data


def _selected_evidence(rules, definition):
    """Check only the bound edition's rows/catalog after current-source binding.

    Parsing/caching known declarations does not make the other edition a live
    dependency. The binder verifies this source's bytes on every activation.
    """
    feature = definition["values"]
    declarations = list(feature["branches"].values())
    for declaration in declarations:
        for ability_id in declaration["abilities"].values():
            unit = rules.selection.units.get(ability_id, {})
            if not unit:
                raise ValueError("scene ability catalog identity changed: " + str(ability_id))
            if not isinstance(unit.get("title"), str) or not unit["title"]:
                raise ValueError("scene ability lacks its catalog title")
    if definition["source"]["file"] == "input/db/feats.csv":
        with (Path(rules.root) / "input/db/feats.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        if feature.get("aggregate_clause") is not None:
            declarations.append(feature["aggregate_clause"])
        for declaration in declarations:
            physical = declaration["physical_row"]
            if (physical > len(rows) or len(rows[physical - 1]) != 5
                    or rows[physical - 1][0] != declaration["name"]):
                raise ValueError("scene ability CSV row changed: " + declaration["clause_id"])


def clause_ids(rules):
    result=[]
    for definitions in _policy(rules)["features"].values():
        feature = next(row["values"] for row in definitions if row["source"]["file"] == "input/db/feats.csv")
        if feature.get("aggregate_clause"):result.append(feature["aggregate_clause"]["clause_id"])
        result.extend(row["clause_id"] for row in feature["branches"].values())
    return tuple(dict.fromkeys(result))


def completion_clause_ids(rules):
    """Return the seven CSV obligations and their two source-entry obligations."""
    return clause_ids(rules) + CLASS_CLAUSE_IDS


def identity(rules, name):
    if not isinstance(name, str):
        return None
    found = []
    for uid in SOURCES:
        unit = rules.selection.units[uid]
        if name in tuple(value for value in (uid, unit.get("title"), unit.get("eng")) if value):
            found.append(uid)
    if len(found) > 1:
        raise ValueError("ambiguous scene ability Feature source")
    return found[0] if found else None


def _branch(source_id, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("scene ability grant requires an explicit acquired branch")
    value = STAT_ALIASES.get(value.strip(), value.strip()) if source_id == STAT_FEATURE else value.strip()
    return value


def _instances(trainer, source_id):
    return tuple(row for row in ACQUIRED.feature_instances(trainer) if row["source_id"] == source_id)


def _require_instance(trainer, source_id, branch):
    matches = [row for row in _instances(trainer, source_id) if _branch(source_id, row["branch"]) == branch]
    if len(matches) != 1:
        raise ValueError("actual acquired scene ability Feature branch required")


def _requirements(engine, trainer, source_id, branch, feature):
    _require_instance(trainer, source_id, branch)
    minimum = feature.get("minimum_prior_class_features")
    if source_id == STAT_FEATURE:
        import skill_modifiers as SKILL
        count = ACQUIRED.count_for_class(trainer, feature["parent_class"], exclude=(source_id,))
        if count < minimum:
            raise ValueError("Stat Embodiment requires four prior Stat Ace features")
        if max(SKILL.rank(engine.r, trainer, name)[2] for name in feature["qualifying_skills"]) < feature["minimum_skill_rank"]:
            raise ValueError("Stat Embodiment requires Expert Command or Focus")
    else:
        import contest_features as CONTEST
        choices = CONTEST.style_expert(engine, trainer)
        if branch not in choices:
            raise ValueError("Style Entrainment branch requires its acquired Style Expert branch")
        if CONTEST.style_feature_count(engine, trainer, choices, exclude=(source_id,)) < minimum:
            raise ValueError("Style Entrainment requires four prior Style Expert features")


def _ability(rules, declaration, choice):
    if not isinstance(choice, str) or not choice.strip():
        raise ValueError("exactly one scene ability choice is required")
    raw = choice.strip()
    candidates = []
    for printed, ability_id in declaration["abilities"].items():
        unit = rules.selection.units[ability_id]
        if raw in (printed, ability_id, unit.get("title"), unit.get("eng")):
            candidates.append((printed, ability_id, unit.get("title")))
    if len(candidates) != 1:
        raise ValueError("scene ability choice is outside its printed branch domain")
    printed, ability_id, name = candidates[0]
    if rules._selected_rule(ability_id) != ability_id:
        raise ValueError("selected scene ability variant requires its own policy")
    if name not in rules.ability_effects or not rules.ability_effects[name]:
        raise ValueError("selected scene ability lacks an exact executable definition")
    if name in getattr(rules, "excluded_abilities", {}):
        raise ValueError("selected scene ability belongs to an excluded source")
    return printed, ability_id, name


def _source_key(owner, target, family):
    return "scene-feature-ability:" + owner.entity_id + ":" + target.entity_id + ":" + family


def _managed(target):
    state = target.spec.get(GRANTS.KEY, {})
    sources = state.get("sources", {}) if isinstance(state, dict) else {}
    return {key: row for key, row in sources.items()
            if isinstance(row, dict) and row.get(TAG) == 1}


def records(target):
    result = []
    for key, row in _managed(target).items():
        required = ("scene", "your_pokemon", 1)
        if (row.get("lifetime"), row.get("target_contract"), row.get(TAG)) != required:
            raise ValueError("scene ability grant lifetime provenance changed")
        source_id = row.get("rule_id")
        definitions = _policy(target.r)["features"].get(source_id)
        if definitions is None:
            raise ValueError("scene ability grant family provenance changed")
        producer = row.get("source_policy_binding")
        if producer is None:
            feature = next(d["values"] for d in definitions if d["source"]["file"] == "input/db/feats.csv")
        else:
            feature = SELECTION.policy_values(producer, definitions)
        if row.get("family") != feature["family"]:
            raise ValueError("scene ability grant family provenance changed")
        branch = row.get("branch")
        declaration = feature["branches"].get(branch)
        if declaration is None or row.get("clause_id") != declaration["clause_id"]:
            raise ValueError("scene ability grant branch provenance changed")
        ability_id = row.get("ability_id")
        if ability_id not in declaration["abilities"].values():
            raise ValueError("scene ability grant choice provenance changed")
        name = target.r.selection.units[ability_id].get("title")
        if row.get("grants", {}).get("abilities") != [name] or row.get("ability_name") != name:
            raise ValueError("scene ability grant disagrees with its native ability")
        owner_id = row.get("owner_id")
        if key != "scene-feature-ability:" + owner_id + ":" + target.entity_id + ":" + feature["family"]:
            raise ValueError("scene ability grant source identity changed")
        result.append(dict(row, source=key))
    return tuple(result)


def plan(engine, trainer, pokemon, source, branch, ability):
    import world_entities as WORLD
    import priority_limited as PRIORITY
    WORLD.require_actors(engine, trainer, pokemon)
    source_id = identity(engine.r, source)
    if source_id is None:
        raise ValueError("known scene ability Feature required")
    binding = engine.r.bind_source_policy(source_id, _policy(engine.r)["features"][source_id])
    _selected_evidence(engine.r, binding["definition"])
    if trainer.kind != "trainer" or trainer.dead or trainer.fainted or trainer.hp <= 0:
        raise ValueError("conscious trainer required for scene ability grant")
    if pokemon.kind != "pokemon" or pokemon.spec.get("trainer_id") != trainer.entity_id:
        raise ValueError("scene ability target must be the actual trainer-owned Pokemon")
    feature = binding["definition"]["values"]
    branch = _branch(source_id, branch)
    declaration = feature["branches"].get(branch)
    if declaration is None:
        raise ValueError("scene ability branch is outside its source domain")
    _requirements(engine, trainer, source_id, branch, feature)
    printed, ability_id, ability_name = _ability(engine.r, declaration, ability)
    if AP.available(trainer) < feature["ap"]:
        raise ValueError("scene ability grant requires 1 available AP")
    import order_actions as ORDERS
    if feature["priority_limited"]:
        ORDERS.preflight(engine, trainer, source_id, action=feature["action"])
    key = _source_key(trainer, pokemon, feature["family"])
    current = _managed(pokemon).get(key)
    if current is not None:
        records(pokemon)
        GRANTS.preflight_revoke(pokemon, [key])
    return {
        "source_id": source_id, "family": feature["family"], "branch": branch,
        "clause_id": declaration["clause_id"], "ability_printed": printed,
        "ability_id": ability_id, "ability_name": ability_name, "source": key,
        "action": feature["action"], "ap": feature["ap"],
        "priority_limited": feature["priority_limited"],
        "source_policy_binding": binding,
    }


def activate(engine, trainer, pokemon, source, branch, ability):
    """Pay and replace one family-owned grant as one staged transaction."""
    def apply(staged, owner, target):
        import priority_limited as PRIORITY
        import turn as TURN
        value = plan(staged, owner, target, source, branch, ability)
        # The planned producer is evidence, not authority for this later commit.
        current = staged.r.bind_source_policy(value["source_id"], _policy(staged.r)["features"][value["source_id"]])
        if current != value["source_policy_binding"]:
            raise ValueError("scene ability source policy changed before commit")
        _selected_evidence(staged.r, current["definition"])
        communication = None
        import order_actions as ORDERS
        if value["priority_limited"] and ORDERS.priority(staged, owner, value["source_id"]):
            priority = PRIORITY.reserve(
                staged, owner, action=value["action"], source=value["source_id"],
                subject=target.entity_id, communication=communication,
            )
        else:
            if not TURN.spend(staged, owner, value["action"], value["source_id"]):
                raise ValueError("scene ability Swift action is unavailable")
            priority = None
        AP.charge(owner, value["ap"], mode="spend")
        if value["source"] in _managed(target):
            GRANTS.revoke(target, value["source"], engine=staged)
        GRANTS.grant(
            target, "abilities", value["ability_name"], value["source"], "scene_feature_ability",
            owner_id=owner.entity_id, lifetime="scene", rule_id=value["source_id"], tutor_points=0,
        )
        staged.register_abilities_one(target, value["ability_name"])
        row = GRANTS.state(target)["sources"][value["source"]]
        row.update({
            TAG: 1, "family": value["family"], "branch": value["branch"],
            "clause_id": value["clause_id"], "ability_id": value["ability_id"],
            "ability_name": value["ability_name"], "target_contract": "your_pokemon",
            "switch_persists": True, "replacement_scope": "same_family_same_target",
            "source_policy_binding": deepcopy(value["source_policy_binding"]),
        })
        result = dict(value, owner_id=owner.entity_id, target_id=target.entity_id,
                      priority_receipt=deepcopy(priority), communication=deepcopy(communication))
        staged.gm._rec("Scene Feature ability grant", None, deepcopy(result),
                       "actual acquired Feature activation", owner)
        return result

    return GRANTS.transition(engine, trainer, apply, participants=(pokemon,))


def reconcile_owner(engine, trainer):
    """Withdraw only live grants whose producing acquired Feature vanished."""
    if trainer.kind != "trainer":
        return 0
    import world_entities as WORLD
    actors = tuple(WORLD.actor_index(engine).values())
    owned = {source_id: {_branch(source_id, row["branch"]) for row in _instances(trainer, source_id)}
             for source_id in SOURCES}
    removals = []
    for target in actors:
        for key, row in _managed(target).items():
            if row.get("owner_id") == trainer.entity_id and row.get("branch") not in owned.get(row.get("rule_id"), set()):
                removals.append((target, key))
    if not removals:
        return 0
    targets = tuple(dict.fromkeys(target for target, _ in removals))

    def apply(staged, owner, *participants):
        by_id = {target.entity_id: target for target in participants}
        for original, key in removals:
            GRANTS.revoke(by_id[original.entity_id], key, engine=staged)
        return len(removals)

    return GRANTS.transition(engine, trainer, apply, participants=targets)


def end_scene(engine, actors):
    count = 0
    for actor in actors:
        for key in tuple(_managed(actor)):
            GRANTS.revoke(actor, key, engine=engine)
            count += 1
    return count


def validate(actor):
    records(actor)
    return True
