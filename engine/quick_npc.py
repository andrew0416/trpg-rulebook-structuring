"""Source-adopted quick NPC sheets; no general PC acquisition certification.

The GM authors each selected source's prerequisite interpretation through the
existing source_policy boundary. Native skill/ownership facts are read here;
missing interpretations and decisions remain pending. Feature effects and
selection receipts still belong to the existing native feature consumers.
"""
from copy import deepcopy
from types import SimpleNamespace
import re

import acquired_features as ACQUIRED
import skill_modifiers as SKILLS
import source_policy as POLICY
import source_policy_state as INPUTS
import state_fields as F
from source_context import verified_source

SOURCE = "ch11-running-the-game/빠른-npc-제작"
REFERENCE = {"file": "input/ch11-running-the-game.md",
             "sha256": "5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad"}
KEY = "quick_npc"
NATIVE_SELECTIONS = {"class/무술가": "selected_ability", "feat/개인-지도": "selected_values"}


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(label + " requires nonempty text")
    return value


def _source(rules):
    if rules._selected_rule(SOURCE) != SOURCE or SOURCE in rules.ruleset.unit_versions:
        raise ValueError("quick NPC source replacement/version needs its own policy")
    selected = rules.selection.units[SOURCE]["source"]
    if selected.get("file") != REFERENCE["file"].removeprefix("input/") or selected.get("sha256") != REFERENCE["sha256"]:
        raise ValueError("quick NPC selected source provenance changed")
    if rules.rulings.mech.get(SOURCE) or rules.rulings.effects.get(SOURCE):
        raise ValueError("quick NPC override needs its own policy")
    verified_source(rules, REFERENCE, label="quick NPC")


def requirement_source(rules, uid):
    """Expose exact printed pre-effect text for an authored prerequisite policy.

    This is a source reader, not a natural-language prerequisite compiler.
    Class catalog ranges identify headings; introductory tables precede some
    actual class tables. Other sources retain their catalogued full span.
    """
    if type(uid) is not str or not uid.startswith(("class/", "feat/", "edge/")):
        raise ValueError("exact class, Feature or Edge source required")
    selected = rules.select_source_definition(uid)
    if selected["selected_id"] != uid or uid in rules.ruleset.unit_versions:
        raise ValueError("quick NPC selected feature variant needs its own policy")
    source = selected["source"]
    reference = {"file": "input/" + source["file"].removeprefix("input/"), "sha256": source["sha256"]}
    lines = verified_source(rules, reference, label="quick NPC requirement").decode("utf-8").splitlines()
    first, last = source["lines"]
    if uid.startswith("class/"):
        block = []
        for line in lines[first:]:
            if line.startswith("### "):
                break
            block.append(line)
            if line.strip() == "</table>":
                if "[클래스]" in "\n".join(block):
                    break
                block = []
        text = "\n".join(block)
        if "[클래스]" not in text:
            raise ValueError("class prerequisite table needs explicit authored source support")
    else:
        text = "\n".join(lines[first - 1:last])
    text = re.split(r"\*\*효과\s*:\s*\*\*", text, maxsplit=1)[0].strip()
    if not text:
        raise ValueError("printed requirement source is empty")
    return {"rule_id": uid, "source": reference, "source_text": text}


def _refs(value):
    if type(value) is dict:
        if set(value) == {"$input"}:
            return {value["$input"]}
        return set().union(*(_refs(child) for child in value.values()))
    if type(value) is list:
        return set().union(*(_refs(child) for child in value))
    return set()


def _native(actor, specs):
    values = {}
    for key, spec in specs.items():
        if spec["authority"] != "state":
            continue
        INPUTS.validate(spec)
        binding = spec["binding"]
        if binding["subject"] != "actor":
            raise ValueError("quick NPC prerequisites read the proposed actor only")
        field = binding["field"]
        if field == "skill_rank":
            SKILLS.skill_id(actor.r.skill_policy, binding["skill"], required=True)
            values[key] = SKILLS.rank(actor.r, actor, binding["skill"])[2]
        elif field == "owned_rule_count":
            values[key] = ACQUIRED.owned_rule_count(actor, binding["rule_id"])
        elif field in ("level", "kind"):
            values[key] = getattr(actor, field)
        else:
            raise ValueError("quick NPC prerequisite needs an existing native source adapter")
    return values


def _requirements(actor, uid, declaration):
    printed = requirement_source(actor.r, uid)
    if type(declaration) is not dict or set(declaration) - {"policy", "decisions"} or "policy" not in declaration:
        raise ValueError("source prerequisite policy and explicit decisions required")
    document = declaration["policy"]
    if type(document) is not dict or len(document.get("variants", [])) != 1:
        raise ValueError("one exact source prerequisite policy required")
    row = document["variants"][0]
    if (row.get("rule_id") != uid or row.get("source") != printed["source"] or
            row.get("values") != {"source_text": printed["source_text"], "requirements_reviewed": True}):
        raise ValueError("prerequisite policy must bind the complete printed source text")
    specs = row.get("inputs", {})
    review = specs.get("requirements_reviewed", {})
    if (review.get("authority"), review.get("type")) != ("gm", "boolean"):
        raise ValueError("explicit GM prerequisite coverage review required")
    references = _refs(row.get("when"))
    if "requirements_reviewed" not in references or set(specs) != references:
        raise ValueError("all prerequisite inputs and GM coverage must constrain the condition")
    if re.search(r"전제\s*조건", printed["source_text"]) and len(specs) < 2:
        raise ValueError("printed prerequisites cannot be replaced by an unchecked empty condition")
    if any(spec["authority"] == "context" for spec in specs.values()):
        raise ValueError("prerequisite facts require native state or an explicit GM decision")
    result = POLICY.resolve(actor.r, document, decisions=declaration.get("decisions"),
                            _state_reader=lambda inputs: _native(actor, inputs))
    # The host's coverage review is mandatory even if an authored OR would
    # otherwise make the policy applicable. False is not permission to proceed.
    if result["status"] == "PolicyValuesReady" and result["input_values"].get("requirements_reviewed") is not True:
        result.update(status="PolicyNotApplicable", values=None)
    return result


def combat_stats(level, declaration):
    """Explicit allocations, with the printed combat focus already in budget.

    The worked example's level-5 label contradicts its level-15/14–28 arithmetic;
    the main rule determines the range. No further automatic stat-tag award.
    """
    F.integer(level, "NPC level", 1, 50)
    if type(declaration) is not dict or set(declaration) != {"focus", "growth_points", "initial", "growth", "reason"}:
        raise ValueError("explicit combat focus and both stat allocations required")
    _text(declaration["reason"], "GM combat allocation reason")
    lower, upper = level - 1, 2 * (level - 1)
    focus = declaration["focus"]
    points = F.integer(declaration["growth_points"], "quick NPC growth points", lower, upper)
    if focus not in ("noncombat", "mixed", "combat"):
        raise ValueError("explicit GM combat focus required")
    if focus == "noncombat" and points != lower or focus == "combat" and points != upper:
        raise ValueError("combat focus disagrees with its printed growth budget")
    for key, budget in (("initial", 10), ("growth", points)):
        allocation = declaration[key]
        if type(allocation) is not dict or set(allocation) != set(F.STATS):
            raise ValueError("all six quick NPC stat allocations must be explicit")
        for value in allocation.values():
            F.integer(value, "quick NPC allocated stat", 0)
        if sum(allocation.values()) != budget:
            raise ValueError("quick NPC stat allocation disagrees with its budget")
    return {stat: (10 if stat == "hp" else 5) + declaration["initial"][stat] + declaration["growth"][stat]
            for stat in F.STATS}


def prepare(rules, name, level, *, role, level_treatment, classes=(), feats=(), edges=(), skills=None,
            feature_choices=None, edge_choices=None, feat_ranks=None, requirements=None, combat=None,
            native_acquisitions=None):
    """Prepare a role-selected sheet; pending results never create any entity.

    No numeric meaning of 'very low level' is invented. The GM supplies that
    source-delegated assessment. Its exception concerns PC acquisition order/
    progression, never source prerequisites, class capacity or feature choices.
    """
    _source(rules)
    _text(name, "NPC name"); _text(role, "NPC role")
    F.integer(level, "NPC level", 1, 50)
    if type(level_treatment) is not dict or set(level_treatment) != {"very_low_level", "reason"}:
        raise ValueError("explicit GM level treatment required")
    if type(level_treatment["very_low_level"]) is not bool:
        raise ValueError("very-low-level assessment must be boolean")
    _text(level_treatment["reason"], "GM level treatment reason")
    spec = {"name": name, "kind": "trainer", "level": level, "skills": deepcopy(skills or {}),
            "feature_choices": deepcopy(feature_choices or {}), "edge_choices": deepcopy(edge_choices or {}),
            "feat_ranks": deepcopy(feat_ranks or {})}
    actor = SimpleNamespace(r=rules, spec=spec, kind="trainer", level=level)
    for field, prefix, values in (("classes", "class/", classes), ("feats", "feat/", feats), ("edges", "edge/", edges)):
        if not isinstance(values, (list, tuple)):
            raise ValueError("NPC selected sources must be lists")
        spec[field] = [ACQUIRED._resolve(actor, value, prefix) for value in values]
    for skill in spec["skills"]:
        SKILLS.skill_id(rules.skill_policy, skill, required=True)
        SKILLS.rank(rules, actor, skill)
    ACQUIRED.validate_class_slots(actor)
    selected = set(spec["classes"] + spec["feats"] + spec["edges"])
    requirements = {} if requirements is None else requirements
    if type(requirements) is not dict or set(requirements) - selected:
        raise ValueError("requirements must name the actual selected NPC sources")
    pending, evidence = [], {}
    native_acquisitions = {} if native_acquisitions is None else deepcopy(native_acquisitions)
    if type(native_acquisitions) is not dict or set(native_acquisitions) - (selected & NATIVE_SELECTIONS.keys()):
        raise ValueError("native acquisition choices must name selected native receipt sources")
    for uid in sorted(selected & NATIVE_SELECTIONS.keys()):
        request = native_acquisitions.get(uid)
        if (type(request) is not dict or NATIVE_SELECTIONS[uid] not in request or
                "acquisition_request_id" not in request):
            pending.append({"kind": "native_acquisition_choice_required", "rule_id": uid})
        elif set(request) != {NATIVE_SELECTIONS[uid], "acquisition_request_id"}:
            raise ValueError("native acquisition uses its existing source adapter and lifecycle")
    if level_treatment["very_low_level"]:
        pending.append({"kind": "normal_pc_acquisition_required", "reason": "very low level NPC has no quick acquisition exception"})
    for uid in sorted(selected):
        if uid not in requirements:
            pending.append({"kind": "source_prerequisites_required", "rule_id": uid})
            continue
        result = _requirements(actor, uid, requirements[uid])
        evidence[uid] = result
        if result["status"] != "PolicyValuesReady":
            pending.append({"kind": "source_prerequisites_unresolved", "rule_id": uid, "result": result})
    metadata = {"source_id": SOURCE, "source": deepcopy(REFERENCE), "role": role,
                "level_treatment": deepcopy(level_treatment), "pc_acquisition_exception": not level_treatment["very_low_level"],
                "exception_scope": "full_pc_progression_budget_and_order_only",
                "creation_legality_certified": False, "requirements": evidence, "combat": deepcopy(combat)}
    if combat is not None:
        spec["stats"] = combat_stats(level, combat)
    spec[KEY] = metadata
    return {"status": "pending" if pending else "ready", "obligations": pending, "spec": spec,
            "native_acquisitions": native_acquisitions}


def build(rules, name, level, *, moves=None, items=None, pos=(0, 0), side="npc", **options):
    """Prepare a raw trainer import spec; create() performs native admission.

    As with build_trainer, this draft has no registered feature projections.
    Use create for a live actor with receipts, effects and the final budget.
    """
    prepared = prepare(rules, name, level, **options)
    if prepared["status"] != "ready":
        raise ValueError("quick NPC prerequisites are pending: " + str(prepared["obligations"]))
    spec = prepared["spec"]
    if "stats" not in spec:
        raise ValueError("ordinary NPC combat requires the optional complete stat allocation")
    if prepared["native_acquisitions"]:
        raise ValueError("selection-only native acquisitions require quick_npc.create")
    import builder
    return builder.build_trainer(rules, name, level, spec["stats"], moves=moves, skills=spec["skills"],
                                 items=items, pos=pos, side=side, extra=spec)


def create(engine, name, level, *, moves=None, items=None, pos=(0, 0), side="npc", **options):
    """Commit one new actor and existing native acquisitions as one transition."""
    prepared = prepare(engine.r, name, level, **options)
    if prepared["status"] != "ready":
        raise ValueError("quick NPC prerequisites are pending: " + str(prepared["obligations"]))
    spec = deepcopy(prepared["spec"])
    if "stats" not in spec:
        raise ValueError("ordinary NPC combat requires the optional complete stat allocation")
    native = prepared["native_acquisitions"]
    for field in ("classes", "feats"):
        spec[field] = [uid for uid in spec[field] if uid not in native]
    import builder
    from engine import Combatant
    import state_grants as GRANTS
    import trainer_feature_acquisition as FEATURES
    import items as ITEMS
    import static_feature_state_grants as STATIC
    actor = Combatant(engine.r, builder.build_trainer(engine.r, name, level, spec["stats"],
                      moves=moves, items=items, pos=pos, side=side, extra=spec))

    def apply(staged, proposed):
        # Native producers require the actual actor in the staging graph.
        # Registration happens after their existing immutable receipts commit.
        for roster in (staged.everyone, staged.gm.everyone):
            if proposed not in roster:
                roster.append(proposed)
            __import__('world_entities').roster_changed(staged)
        for uid, request in sorted(native.items()):
            if uid == FEATURES.MARTIAL_ARTIST:
                FEATURES.acquire_martial_artist(staged, proposed, **request,
                    lifecycle_policy=deepcopy(FEATURES.LIFECYCLE_WHILE_OWNED))
            else:
                FEATURES.acquire_personal_tutor(staged, proposed, **request, source_clause_id="C03-127",
                    lifecycle_policy=deepcopy(FEATURES.LIFECYCLE_UNRESOLVED))
        # The printed quick budget already includes stat tags. Keep the
        # existing exact tag receipts while fitting only their declared
        # contributions into the GM's explicit allocation. Other effects are
        # not part of this adjustment and remain owned by their consumers.
        tags = dict.fromkeys(F.STATS, 0)
        for declaration in STATIC.plan(proposed).values():
            if declaration.get("stat"):
                tags[declaration["stat"]] += declaration.get("count", 1)
        allocation = prepared["spec"][KEY]["combat"]
        if any(tags[stat] > allocation["initial"][stat] + allocation["growth"][stat] for stat in F.STATS):
            raise ValueError("native stat tags exceed the explicit allocation; choose an allocation")
        if any(tags.values()):
            F.base_patch(proposed, {"stats": {stat: proposed.spec["stats"][stat] - tags[stat] for stat in F.STATS}},
                         source=SOURCE, reason="quick NPC explicit budget already includes native stat tags")
        # Existing construction registers projections before GM admission's
        # pure validation. Reuse the same items/Feature pipeline here.
        ITEMS.register_feats(staged, proposed)
        staged.gm.add_combatant(proposed, reason="source-adopted quick NPC: " + options["role"])
        return {"entity_id": proposed.entity_id}

    GRANTS.transition(engine, actor, apply, include_rulings=True)
    return actor


def observe(engine, name, level, *, location=None, **options):
    """Adopt the same role-selected construction as an existing partial NPC."""
    if options.get("combat") is not None:
        raise ValueError("complete combat sheets use build and native Combatant registration")
    prepared = prepare(engine.r, name, level, **options)
    if prepared["status"] != "ready":
        raise ValueError("quick NPC prerequisites are pending: " + str(prepared["obligations"]))
    import partial_entities as PARTIAL
    import state_grants as GRANTS
    spec = prepared["spec"]

    def apply(staged, _primary):
        result = PARTIAL.observe(staged, name=name, actor_kind="trainer", location=location,
                                 known={"level": level, "skills": spec["skills"], "features": spec["classes"] + spec["feats"],
                                        "edges": spec["edges"], "description": spec[KEY]["role"]},
                                 reason="source-adopted quick NPC: " + spec[KEY]["level_treatment"]["reason"])
        staged._partial_entities[result["entity_id"]]["provenance"][KEY] = deepcopy(spec[KEY])
        return PARTIAL.project(staged, result["entity_id"])

    return GRANTS.transition(engine, None, apply, include_rulings=True)
