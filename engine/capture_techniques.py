"""Book Capture Specialist selections, owned by the common acquisition receipts.

The technique table defines selectable rights. Its separate active actions are
not implemented here; wild_equipment consumes only Tools and modern Snare.
"""
from collections import Counter
from copy import deepcopy

import acquisition_qualification as Q
import skill_modifiers as SKILL_RANKS
import acquired_features as ACQUIRED
import source_context as SOURCES
import trainer_feature_acquisition as TFA

CLASS = "class/포획전문가"
ADVANCED = "feat/고급-포획-테크닉"
ADAPTER = "trainer-feature/capture-techniques/v1"
SKILLS = ("곡예", "육상", "은신", "생존", "교활", "통찰")
TECHNIQUES = {
    "포획 스킬": "Capture Skills", "커브볼": "Curve Ball",
    "약화 투척": "Devitalizing Throw", "빠른 투구": "Fast Pitch",
    "덫": "Snare", "작업 도구": "Tools of the Trade", "캐치 콤보": "Catch Combo",
    "거짓 타격": "False Strike", "끝없는 추격": "Relentless Pursuit",
}
EXPERT = ("캐치 콤보", "거짓 타격", "끝없는 추격")
SOURCE = {"file": "input/ch04-trainer-classes.md",
          "sha256": "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4", "version": 1}
DEFINITIONS = {
    CLASS: {"span": [375, 377], "catalog_span": [362, 362],
            "excerpt_sha256": "895a72c2b036f3843bb47776e1cc3e53c025665137a8a7d1bf8d5506fc382433"},
    ADVANCED: {"span": [379, 386], "catalog_span": [379, 386],
               "excerpt_sha256": "e2c4dbaedb72d6d427ce05c41cda38025f0062f296b67bef78b88d8a491b9681"},
}
TABLE_SHA = "b5423faf61f63f10b306fed313658cd451eb72c9feb8a38c1e5fa612df4b3819"
SKILL_EDGES = {
    "edge/기본-스킬": {"span": [300, 302], "level": 1, "from": (1, 2)},
    "edge/숙련-스킬": {"span": [304, 306], "level": 2, "from": (3,)},
    "edge/전문-스킬": {"span": [308, 310], "level": 6, "from": (4,)},
    "edge/달인-스킬": {"span": [312, 314], "level": 12, "from": (5,)},
}


def _skill_edge(rules, choice, level, before):
    edge = choice["edge"]
    definition = SKILL_EDGES[edge]
    authority = dict(TFA.STATIC_SOURCE, span=definition["span"])
    SOURCES.verified_source(rules, authority, label="Capture Skill Edge")
    unit = rules.selection.units[edge]
    if (rules._selected_rule(edge) != edge or unit["source"]["file"] != "ch03-skills-edges-feats.md" or
            unit["source"]["lines"] != definition["span"]):
        raise ValueError("exact Book Skill Edge source required")
    if type(level) is not int or level < definition["level"] or before not in definition["from"]:
        raise ValueError("Capture Skills requires the Skill Edge's exact rank transition and level")
    return {"edge": edge, "skill": choice["skill"], "source": authority, "level": level,
            "before": before, "after": before + 1}


def _child_id(actor, receipt, index):
    return _source_id(actor, receipt) + ":skill:" + str(index)


def grant_skill_edge(engine, actor, edge, sid, **metadata):
    """One observed rank transition, reused by actual printed grant providers."""
    import skill_modifiers as SKILL, state_fields as FIELDS, state_grants as GRANTS
    expected = _skill_edge(engine.r, {"edge": edge["edge"], "skill": edge["skill"]},
                           actor.level, SKILL.rank(engine.r, actor, edge["skill"])[2])
    if edge != expected:
        raise ValueError("Skill Edge transition no longer matches its observed source and rank")
    skills = deepcopy(actor.spec.get("skills", {}))
    canonical = SKILL.skill_id(engine.r.skill_policy, edge["skill"], required=True)
    skills = {key: value for key, value in skills.items() if SKILL.skill_id(engine.r.skill_policy, key) != canonical}
    skills[edge["skill"]] = edge["after"]
    change = FIELDS.base_patch(actor, {"skills": skills}, reason="acquired eligible Capture Skill Edge",
                               source=edge["edge"], request_id=sid)
    native = GRANTS._source(actor, sid, "feature", owner_id=actor.entity_id, lifetime="permanent",
                           rule_id=edge["edge"], tutor_points=0, skill_edge=deepcopy(edge),
                           state_change=deepcopy(change), **metadata)
    native["grants"]["edges"] = [edge["edge"]]
    return native


def _grant_skill_edges(engine, actor, receipt):
    import skill_modifiers as SKILL
    import state_fields as FIELDS
    import state_grants as GRANTS
    for index, proof in enumerate(receipt["selection"]["proofs"]):
        edge = proof["skill_edge"]
        if edge is None:
            continue
        sid = _child_id(actor, receipt, index)
        grant_skill_edge(engine, actor, edge, sid, capture_skill_receipt=receipt["receipt_id"],
                         capture_parent_source=_source_id(actor, receipt))
        import acquisition_withdrawal as WITHDRAWAL
        dependencies = [identity for identity, row in skill_edges(actor) if identity != sid and
                        row["skill_edge"]["skill"] == edge["skill"] and row["skill_edge"]["after"] <= edge["before"]]
        WITHDRAWAL.dependencies(engine, actor, sid, dependencies)


def skill_edges(actor):
    """Actual granted Edge instances, separate from baseline imported references."""
    return [(sid, row) for sid, row in actor.spec.get("state_grants", {}).get("sources", {}).items()
            if "capture_skill_receipt" in row]


def preflight_revoke(actor, source_ids):
    for sid, row in skill_edges(actor):
        if sid in source_ids and not row.get("capture_skill_withdrawal"):
            raise ValueError("Capture Skill Edge removal requires its own reviewed rank withdrawal policy")
        if row["capture_parent_source"] in source_ids and not row.get("parent_end_policy"):
            raise ValueError("Capture Skill Edge retention after parent removal requires explicit GM policy")


def prepare_retraining(engine, actor, feature_id, policy):
    """The book does not define removal of an already granted permanent Edge."""
    active = {row["receipt_id"] for row in _rows(actor) if row["feature_id"] == feature_id}
    children = [(sid, row) for sid, row in skill_edges(actor) if row["capture_skill_receipt"] in active]
    if not children:
        if policy is not None:
            raise ValueError("no granted Capture Skill Edge for this GM retention policy")
        return
    if type(policy) is not dict or policy.get("mode") not in ("retain", "withdraw"):
        raise ValueError("explicit GM retain or withdraw policy required for granted Capture Skill Edges")
    TFA._text(policy["reason"], "GM granted-Edge retention reason")
    expected = {"mode", "reason"} if policy["mode"] == "retain" else {"mode", "reason", "skills_before", "skills_after"}
    if set(policy) != expected:
        raise ValueError("exact GM granted-Edge policy inputs required")
    if policy["mode"] == "withdraw":
        import acquisition_withdrawal as WITHDRAWAL
        import skill_modifiers as SKILL
        import state_fields as FIELDS
        import state_grants as GRANTS
        affected = {row["skill_edge"]["skill"] for _, row in children}
        before, after = policy["skills_before"], policy["skills_after"]
        if (type(before) is not dict or type(after) is not dict or set(before) != affected or set(after) != affected or
                any(type(before[s]) is not int or type(after[s]) is not int or
                    not 1 <= after[s] <= before[s] or SKILL.rank(engine.r, actor, s)[2] != before[s] for s in affected)):
            raise ValueError("GM withdrawal requires exact current ranks and explicit resulting ranks")
        for skill in affected:
            SKILL_RANKS.validate_rank_value(engine.r,before[skill],label="Capture withdrawal prior rank")
            SKILL_RANKS.validate_rank_value(engine.r,after[skill],label="Capture withdrawal resulting rank")
        WITHDRAWAL.preflight(actor, {sid for sid, _ in children})
        skills = deepcopy(actor.spec.get("skills", {}))
        canonical = {SKILL.skill_id(engine.r.skill_policy, skill) for skill in affected}
        skills = {key: value for key, value in skills.items() if SKILL.skill_id(engine.r.skill_policy, key) not in canonical}
        skills.update(after)
        change = FIELDS.base_patch(actor, {"skills": skills}, reason=policy["reason"], source="gm/capture-skill-withdrawal")
        root = "feature:" + actor.entity_id + ":" + feature_id
        for sid, row in children:
            row["capture_skill_withdrawal"] = {"policy": deepcopy(policy), "state_change": deepcopy(change)}
            GRANTS.state(actor)["sources"][root].setdefault("effect_sources", []).append(sid)
    for _, row in children:
        row["parent_end_policy"] = deepcopy(policy)


def source(rules, feature_id):
    from hashlib import sha256
    if feature_id not in DEFINITIONS:
        raise ValueError("exact Capture Specialist or Advanced Capture Techniques source required")
    SOURCES.verified_source(rules, SOURCE, label="Capture Techniques")
    definition = DEFINITIONS[feature_id]
    if rules._selected_rule(feature_id) != feature_id:
        raise ValueError("selected Capture source requires its own acquisition contract")
    unit = rules.selection.units[feature_id]
    catalog = unit.get("source", {})
    if catalog.get("file") != SOURCE["file"].removeprefix("input/") or catalog.get("lines") != definition["catalog_span"]:
        raise ValueError("Capture catalog identity differs from the reviewed source")
    from pathlib import Path
    lines = (Path(rules.root) / SOURCE["file"]).read_text(encoding="utf-8").splitlines()
    for bounds, digest in ((definition["span"], definition["excerpt_sha256"]), ([405, 407], TABLE_SHA)):
        if sha256("\n".join(lines[bounds[0]-1:bounds[1]]).encode()).hexdigest() != digest:
            raise ValueError("Capture source excerpt changed")
    clause = SOURCE["file"] + ":" + "-".join(map(str, definition["span"]))
    rules.ruleset.require({"id": clause, "source": {"file": catalog["file"], "lines": definition["span"]}})
    return dict(SOURCE, clause_id=clause)


def _choices(rules, choices):
    import skill_modifiers as SKILL
    if type(choices) is not list or len(choices) != 2:
        raise ValueError("each Capture acquisition requires exactly two choices")
    result = []
    for choice in choices:
        if type(choice) is not dict:
            raise ValueError("typed Capture technique choice required")
        name = next((name for name, alias in TECHNIQUES.items() if choice.get("technique") in (name, alias)), None)
        expected = {"technique", "edge", "skill"} if name == "포획 스킬" else {"technique"}
        if name is None or set(choice) - {"source_variant"} != expected:
            raise ValueError("Capture technique choice differs from its printed domain")
        row = {"technique": name}
        if "source_variant" in choice:
            import capture_specialist as ACTIVE
            ACTIVE.technique_source(rules, name, choice["source_variant"])
            row["source_variant"] = choice["source_variant"]
        if name == "포획 스킬":
            canonical = SKILL.skill_id(rules.skill_policy, choice["skill"], required=True)
            matched = next((skill for skill in SKILLS if SKILL.skill_id(rules.skill_policy, skill) == canonical), None)
            if matched is None or choice["edge"] not in SKILL_EDGES:
                raise ValueError("Capture Skills requires an exact Skill Edge and one of its six skills")
            row.update(edge=choice["edge"], skill=matched)
        result.append(row)
    return result


def _qualification(actor, feature_id, snapshot):
    fields = {"rank", "level", "skills", "parent_count", "prior_rank", "prior_values"}
    if type(snapshot) is not dict or set(snapshot) != fields:
        raise ValueError("exact Capture acquisition-time observations required")
    ranks = snapshot["skills"]
    if (type(ranks) is not dict or set(ranks) != set(SKILLS) or
            any(type(snapshot[key]) is not int for key in ("rank", "level", "parent_count", "prior_rank")) or
            type(snapshot["prior_values"]) is not list or any(type(v) is not str for v in snapshot["prior_values"])):
        raise ValueError("whole ordinary Capture skill ranks and acquisition history required")
    for value in ranks.values():
        SKILL_RANKS.validate_rank_value(actor.r,value,label="Capture acquisition skill rank")
    rank = snapshot["rank"]
    checks = [Q.check("trainer", "prerequisite", actor.kind == "trainer", "actual trainer required")]
    if feature_id == CLASS:
        checks.extend([
            Q.check("physical", "prerequisite", max(ranks[s] for s in SKILLS[:4]) >= 3, "Novice physical Capture skill required"),
            Q.check("social", "prerequisite", max(ranks[s] for s in SKILLS[4:]) >= 3, "Novice Guile or Perception required"),
            Q.check("class_once", "repeat", rank == 0 and snapshot["parent_count"] == 0 and snapshot["prior_rank"] == 0 and not snapshot["prior_values"], "one new Capture Specialist class required"),
        ])
    else:
        checks.extend([
            Q.check("parent", "prerequisite", snapshot["parent_count"] == 1, "actual Capture Specialist parent required"),
            Q.check("next_rank", "repeat", 1 <= rank <= 4 and snapshot["prior_rank"] == rank - 1, "next Advanced Capture rank from one to four required"),
            Q.check("skill_count", "prerequisite", rank == 1 or sum(r >= (4 if rank == 2 else 5) for r in ranks.values()) >= (3 if rank == 4 else 2), "Advanced Capture rank requires distinct qualifying skills in its six-skill domain"),
        ])
    result = Q.require(feature_id, "native", "acquire", checks)
    return {"schema": 1, "status": result["status"], "checks": result["checks"], "waivers": []}


def _evidence(rules, choices, snapshot):
    prior = snapshot["prior_values"]
    counts = Counter(value.split(":", 1)[0] for value in prior)
    proofs = []
    ranks = dict(snapshot["skills"])
    for choice in choices:
        name = choice["technique"]
        counts[name] += 1
        if counts[name] > (2 if name == "포획 스킬" else 1):
            raise ValueError("only Capture Skills can repeat, at most twice")
        if name in EXPERT and sum(value >= 5 for value in ranks.values()) < 3:
            raise ValueError("this Capture technique requires three Expert skills in its six-skill domain")
        value = name + (":" + str(counts[name]) if name == "포획 스킬" else "")
        proof = {"value": value, "choice": deepcopy(choice), "skill_edge": None}
        if name == "포획 스킬":
            proof["skill_edge"] = _skill_edge(rules, choice, snapshot["level"], ranks[choice["skill"]])
            ranks[choice["skill"]] = proof["skill_edge"]["after"]
        proofs.append(proof)
    return proofs


def validate_receipt(actor, payload):
    if payload["adapter_id"] != ADAPTER or payload["feature_id"] not in DEFINITIONS:
        raise ValueError("exact Capture acquisition adapter and feature required")
    expected = source(actor.r, payload["feature_id"])
    if payload["source"] != expected or payload["provider"] != {"actor_id": actor.entity_id, "mode": "self_acquisition"}:
        raise ValueError("Capture source or provider provenance changed")
    selection = payload["selection"]
    snapshot = selection["acquisition_snapshot"]
    if payload["qualification"] != _qualification(actor, payload["feature_id"], snapshot):
        raise ValueError("Capture historical qualification changed")
    choices = _choices(actor.r, [proof.get("choice") for proof in selection["proofs"]])
    proofs = _evidence(actor.r, choices, snapshot)
    if (selection["kind"] != "capture_technique_instances" or selection["required_count"] != 2 or
            selection["proofs"] != proofs or selection["values"] != [row["value"] for row in proofs]):
        raise ValueError("Capture choice proof differs from its acquisition-time constraints")
    TFA._martial_lifecycle(payload["lifecycle_policy"])
    return expected


def _rows(actor):
    return sorted((row for row in TFA._active_rows(actor) if row["adapter_id"] == ADAPTER),
                  key=lambda row: row["selection"]["acquisition_snapshot"]["rank"])


def validate_actor(actor):
    # A later independent skill edit does not rewrite the original Edge transition.
    import trainer_retraining as RETRAINING
    retired = RETRAINING.retired_receipts(actor)
    expected_children = {}
    for receipt in actor.spec.get(TFA.LEDGER_KEY, {}).values():
        if receipt["adapter_id"] != ADAPTER:
            continue
        for index, proof in enumerate(receipt["selection"]["proofs"]):
            if proof["skill_edge"] is not None:
                expected_children[_child_id(actor, receipt, index)] = (receipt, proof["skill_edge"])
    state = actor.spec.get("state_grants", {})
    actual = {sid: (row, False) for sid, row in skill_edges(actor)}
    actual.update({entry["source_id"]: (entry["record"], True) for entry in state.get("ended_sources", [])
                   if "capture_skill_receipt" in entry["record"]})
    if set(actual) != set(expected_children):
        raise ValueError("Capture Skills must have their actual acquired Edge sources")
    for sid, (receipt, edge) in expected_children.items():
        native, ended = actual[sid]
        change = native.get("state_change", {})
        if (native.get("skill_edge") != edge or native.get("capture_skill_receipt") != receipt["receipt_id"] or
                native.get("rule_id") != edge["edge"] or native.get("owner_id") != actor.entity_id or
                native.get("lifetime") != "permanent" or native.get("capture_parent_source") != _source_id(actor, receipt) or
                native.get("grants") != {"edges": [edge["edge"]]} or
                change.get("source") != edge["edge"] or change.get("request_id") != sid or
                change.get("after", {}).get("skills", {}).get(edge["skill"]) != edge["after"]):
            raise ValueError("Capture Skill Edge source or actual transition evidence changed")
        if receipt["receipt_id"] in retired and "parent_end_policy" not in native:
            raise ValueError("retired Capture parent requires its explicit child policy")
        if ended:
            withdrawal = native.get("capture_skill_withdrawal", {})
            policy = native.get("parent_end_policy", {})
            after = withdrawal.get("state_change", {}).get("after", {}).get("skills", {})
            if (policy.get("mode") != "withdraw" or withdrawal.get("policy") != policy or
                    after.get(edge["skill"]) != policy.get("skills_after", {}).get(edge["skill"])):
                raise ValueError("Capture Skill Edge ended without its explicit GM withdrawal result")
        if "parent_end_policy" in native:
            archives = [entry["record"]["retraining"] for entry in state.get("ended_sources", [])
                        if receipt["receipt_id"] in entry["record"].get("retraining", {}).get("acquisition_receipt_ids", [])]
            if len(archives) != 1 or archives[0].get("granted_skill_edge_policy") != native["parent_end_policy"]:
                raise ValueError("Capture child policy requires the actual parent retraining decision")
    rows = _rows(actor)
    if not rows:
        return True
    parents = [row for row in rows if row["feature_id"] == CLASS]
    advances = [row for row in rows if row["feature_id"] == ADVANCED]
    if len(parents) != 1 or ACQUIRED.owned_rule_count(actor, CLASS) != 1:
        raise ValueError("Capture choices require their actual parent acquisition")
    rank = ACQUIRED.owned_rule_count(actor, ADVANCED)
    if sorted(row["selection"]["acquisition_snapshot"]["rank"] for row in advances) != list(range(1, rank + 1)):
        raise ValueError("current Capture ranks must match their actual acquisition receipts")
    ordered = parents + sorted(advances, key=lambda row: row["selection"]["acquisition_snapshot"]["rank"])
    prior = []
    for row in ordered:
        if row["selection"]["acquisition_snapshot"]["prior_values"] != prior:
            raise ValueError("Capture acquisition history does not match earlier owned selections")
        prior.extend(row["selection"]["values"])
        native = actor.spec.get("state_grants", {}).get("sources", {}).get(_source_id(actor, row))
        if (native is None or native.get("capture_receipt") != row["receipt_id"] or
                native.get("owner_id") != actor.entity_id or native.get("rule_id") != row["feature_id"] or
                native.get("lifetime") != "while_owned"):
            raise ValueError("Capture selections require their actual while-owned source")
    if actor.spec.get("capture_techniques"):
        raise ValueError("receipted Capture choices cannot mix an unverified imported choice list")
    return True


def selected(actor):
    """Return owned technique instances without rechecking later live skills."""
    TFA.validate_actor(actor)
    return tuple(proof["choice"]["technique"] for row in _rows(actor) for proof in row["selection"]["proofs"])


def _source_id(actor, receipt):
    return "feature:" + actor.entity_id + ":" + receipt["feature_id"] + ":" + receipt["acquisition_request_id"]


def acquire(engine, actor, feature_id, *, acquisition_request_id, selected_techniques,
            rank=0, provider=None, lifecycle_policy=None):
    import skill_modifiers as SKILL
    import state_grants as GRANTS
    import world_entities as WORLD
    provider = actor if provider is None else provider
    WORLD.require_actors(engine, actor, provider)
    if provider is not actor:
        raise ValueError("Capture acquisition provider must be the acquiring trainer")
    TFA._text(acquisition_request_id, "Capture acquisition request")
    if type(rank) is not int:
        raise ValueError("whole Capture acquisition rank required")
    lifecycle = TFA._martial_lifecycle(lifecycle_policy)
    authority = source(engine.r, feature_id)
    choices = _choices(engine.r, selected_techniques)
    TFA.validate_actor(actor)
    previous = actor.spec.get(TFA.LEDGER_KEY, {}).get(acquisition_request_id)
    if previous is not None:
        if (previous["adapter_id"] != ADAPTER or previous["feature_id"] != feature_id or
                previous["selection"]["acquisition_snapshot"]["rank"] != rank or
                [proof["choice"] for proof in previous["selection"]["proofs"]] != choices or
                previous["lifecycle_policy"] != lifecycle):
            raise ValueError("Capture acquisition request replay cannot change its intent")
        return deepcopy(previous)
    current = _rows(actor)
    parent_count = ACQUIRED.owned_rule_count(actor, CLASS)
    prior_rank = ACQUIRED.owned_rule_count(actor, ADVANCED)
    if (parent_count or prior_rank) and not current:
        raise ValueError("unreceipted Capture ownership cannot invent historical selections")
    snapshot = {"rank": rank, "level": actor.spec.get("level"),
                "skills": {skill: SKILL.rank(engine.r, actor, skill)[2] for skill in SKILLS},
                "parent_count": parent_count, "prior_rank": prior_rank,
                "prior_values": [value for row in current for value in row["selection"]["values"]]}
    qualification = _qualification(actor, feature_id, snapshot)
    proofs = _evidence(engine.r, choices, snapshot)
    values = [proof["value"] for proof in proofs]
    instance = feature_id + ":" + acquisition_request_id
    intent = TFA._intent(actor_id=actor.entity_id, feature_id=feature_id, feature_instance_id=instance,
        source=authority, request_id=acquisition_request_id, provider_id=provider.entity_id, adapter_id=ADAPTER,
        selection_kind="capture_technique_instances", selected_values=values, required_count=2, lifecycle_policy=lifecycle)
    intent["capture_choices"] = choices
    receipt = TFA._seal({"schema": TFA.SCHEMA, "basis": "trainer_feature_selection",
        "receipt_id": "trainer-feature-selection/" + acquisition_request_id, "actor_id": actor.entity_id,
        "feature_id": feature_id, "feature_instance_id": instance, "source": authority,
        "acquisition_request_id": acquisition_request_id,
        "provider": {"actor_id": provider.entity_id, "mode": "self_acquisition"}, "adapter_id": ADAPTER,
        "qualification": qualification, "selection": {"kind": "capture_technique_instances", "required_count": 2,
            "values": values, "proofs": proofs, "acquisition_snapshot": snapshot},
        "lifecycle_policy": lifecycle, "request_integrity": TFA._digest("trainer-feature/acquisition-request/v1", intent),
        "committed": True})

    def apply(staged, trainer):
        field = "classes" if feature_id == CLASS else "feats"
        if feature_id not in trainer.spec.setdefault(field, []):
            trainer.spec[field].append(feature_id)
        if feature_id == ADVANCED:
            trainer.spec.setdefault("feat_ranks", {})[feature_id] = rank
        trainer.spec.setdefault(TFA.LEDGER_KEY, {})[acquisition_request_id] = deepcopy(receipt)
        trainer.spec[TFA.PROJECTION_KEY] = TFA._projection_from_rows(TFA._active_rows(trainer))
        sid = _source_id(trainer, receipt)
        GRANTS._source(trainer, sid, "feature", owner_id=trainer.entity_id, rule_id=feature_id,
                       lifetime="while_owned", tutor_points=0, capture_receipt=receipt["receipt_id"])
        import trainer_retraining as RETRAINING
        parent = RETRAINING.owned_source(staged, trainer, feature_id)
        GRANTS.state(trainer)["sources"][parent].setdefault("effect_sources", []).append(sid)
        _grant_skill_edges(staged, trainer, receipt)
        import items
        items.register_feats(staged, trainer)
        TFA.validate_actor(trainer)
        return deepcopy(receipt)
    return GRANTS.transition(engine, actor, apply)
