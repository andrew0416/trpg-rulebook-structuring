"""Permanent Pokemon Ability lessons compose the existing clock and payment."""
import hashlib
import json
from pathlib import Path

import ability_transitions as ABILITIES
import activity_jobs as JOBS
import common_checks as CHECKS
import grant_payments as PAYMENTS
import pokemon_teaching as TEACHING
import state_grants as GRANTS
import turn as TURN
import world_entities as WORLD

SOURCES = ("feat/효과적인-방법", "feat/댄스-연습", "feat/집단-전술", "feat/요리-음미")
POLICY = "data/feature-ability-lessons.json"


def identity(rules, value):
    if not isinstance(value, str):
        return None
    found = [uid for uid in SOURCES
             if value in (uid, rules.selection.units[uid]["title"], rules.selection.units[uid].get("eng"))]
    if len(found) > 1:
        raise ValueError("ambiguous Ability teaching source")
    return found[0] if found else None


def _policy(rules):
    cached = getattr(rules, "_feature_ability_lessons", None)
    if cached is not None:
        return cached
    path = Path(rules.root) / POLICY
    if not path.is_file():
        path = Path(__file__).resolve().parent.parent / POLICY
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("schema_version") != 1 or data.get("contract") != "permanent_tp_ability_lesson"
            or set(data.get("rules", {})) != set(SOURCES)):
        raise ValueError("unsupported Ability lesson policy")
    for relative, expected in data["source_files"].items():
        if hashlib.sha256((Path(rules.root) / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Ability lesson source changed: " + relative)
    for uid, row in data["rules"].items():
        source = rules.selection.units[uid]["source"]
        bounds = row["lines"]
        lines = (Path(rules.root) / row["source_file"]).read_text(encoding="utf-8").splitlines()
        excerpt = "\n".join(lines[bounds[0]-1:bounds[1]])
        if ("input/" + source["file"] != row["source_file"] or source["lines"] != bounds
                or source["sha256"] != data["source_files"][row["source_file"]]
                or hashlib.sha256(excerpt.encode()).hexdigest() != row["excerpt_sha256"]
                or row["parent"] not in rules.selection.units
                or row["point_cost"] != 2 or type(row["once_per_pokemon"]) is not bool):
            raise ValueError("Ability lesson declaration changed: " + uid)
        for choice in row["abilities"]:
            unit = rules.selection.units.get(choice["id"], {})
            if (unit.get("title") != choice["title"]
                    or "input/" + unit.get("source", {}).get("file", "") != choice["source_file"]
                    or unit.get("source", {}).get("sha256") != data["source_files"][choice["source_file"]]):
                raise ValueError("Ability lesson choice binding changed: " + uid)
    rules._feature_ability_lessons = data["rules"]
    return data["rules"]


def _qualify(engine, teacher, pupil, uid, ability):
    import pokemon_activities as ACTIVITIES
    WORLD.require_actors(engine, teacher, pupil)
    ACTIVITIES._trainer(teacher)
    ACTIVITIES._pokemon(pupil)
    ACTIVITIES._outside(engine)
    row = _policy(engine.r)[uid]
    TEACHING.source(engine.r, uid, row["parent"], TEACHING.POINTS)
    if not TEACHING._acquired_feature(teacher, uid) or not TEACHING._acquired_feature(teacher, row["parent"]):
        raise ValueError("actual acquired teaching Feature and parent class required")
    if row["own_pokemon"]:
        ACTIVITIES._owner(teacher, pupil)
    if teacher.spec.get("frequency_state", {}).get("day", 0) != pupil.spec.get("frequency_state", {}).get("day", 0):
        raise ValueError("teaching calendars must agree")
    effects, header = engine.r.feat_effects(uid)
    if effects != row["effects"] or header.get("frequency", {}).get("action") != "extended":
        raise ValueError("Ability lesson extracted declaration changed")
    selected = ABILITIES.ability_id(engine.r, ability)
    if selected not in {choice["id"] for choice in row["abilities"]}:
        raise ValueError("Ability is outside this Feature's explicit choices")
    TEACHING.source(engine.r, selected)
    engine.r.selection.require_supported_version(selected)
    PAYMENTS.validate(pupil)
    payments = pupil.spec.get(GRANTS.KEY, {}).get("payments", {})
    if row["once_per_pokemon"] and any(receipt["acquisition"]["rule_id"] == uid for receipt in payments.values()):
        raise ValueError("Ability teaching Feature may target this Pokemon only once")
    if not row["once_per_pokemon"] and selected in ABILITIES.known(pupil):
        # No printed once-per-Pokemon limit; a Pokemon that already has the Ability cannot gain it again.
        raise ValueError("the target already has the printed Ability")
    if TEACHING._balance(pupil.spec) < row["point_cost"]:
        raise ValueError("Ability teaching requires two actual Tutor Points")
    return row, selected


def teach(engine, teacher, *, target, feature, ability, seconds, reason):
    """Execute one explicit Extended lesson, paid once by its actual pupil."""
    uid = identity(engine.r, feature)
    if uid is None:
        raise ValueError("reviewed Ability teaching Feature required")
    CHECKS.integer(seconds, "GM-established Extended lesson duration", 1)
    TEACHING._text(reason, "Ability teaching duration and application reason")
    TEACHING._text(ability, "explicit Ability teaching choice")

    def apply(e, pupil, owner):
        row, selected = _qualify(e, owner, pupil, uid, ability)
        group_id = "ability-lesson:" + pupil.entity_id + ":" + uid
        source_id = group_id + ":ability"
        job_id = "training:" + group_id
        if not TURN.spend(e, owner, "extended", uid):
            raise ValueError("Ability teaching requires actual Extended action permission")
        JOBS.run_fixed(e, owner, (pupil,), seconds=seconds, source=uid, job_id=job_id,
                       context={"ability_id": selected, "payment_id": group_id, "reason": reason})
        # The clock can change a participant. Never pay or grant from stale
        # ownership, Feature, source, choice or balance observed before work.
        _, current = _qualify(e, owner, pupil, uid, ability)
        if current != selected:
            raise ValueError("Ability teaching choice changed during the lesson")
        receipt = PAYMENTS.acquire(
            e, pupil, group_id, [{"source_id": source_id, "field": "abilities", "value": selected}],
            row["point_cost"], rule_id=uid, reason=reason, lifetime=None,
        )
        GRANTS.state(pupil)["sources"][source_id]["ability_lesson"] = {
            "teacher_id": owner.entity_id, "ability_id": selected,
            "job_id": job_id, "seconds": seconds, "completed_at": e.elapsed_seconds,
        }
        import trainer_retraining as RETRAINING
        RETRAINING.irreversible(e, owner, uid, event_id=job_id,
                               reason="completed permanent Ability lesson to " + pupil.entity_id + ": " + selected)
        e.log(pupil.name + " learned " + ABILITIES.label(e.r, selected) + " for 2 TP", uid)
        return {"activity": "teach_feature_ability", "source": uid, "ability": selected,
                "point_cost": row["point_cost"], "seconds": seconds, "job_id": job_id,
                "payment": receipt}

    return GRANTS.transition(engine, target, apply, participants=(teacher,))
