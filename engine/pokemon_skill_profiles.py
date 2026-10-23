"""Explicit GM Pokemon skill templates and named individual backgrounds.

Catalog species pools, narrative personality and campaign permission remain
separate. A template is chosen by the GM; examples never select one implicitly.
Evolution bonuses consume actual individual evolution observations once.
"""
from copy import deepcopy
import hashlib
import json
import re
import skill_modifiers as S
import pokemon_intelligence as I

SOURCE = I.SKILLS
FIELD = "pokemon_skill_profile"
BACKGROUND = "pokemon_skill_background"
TEMPLATES = {
    "cutesy": {"name": "심장을 녹이는 귀여움", "primary": "charm", "pools": {
        "intimidate": "1d6", "guile": "3d6+2", "intuition": "2d6+2", "charm": "4d6+3", "command": "2d6"}},
    "taskmaster": {"name": "무섭게 호통치는 감독님", "primary": "intimidate", "pools": {
        "intimidate": "4d6+3", "guile": "2d6+2", "intuition": "2d6", "charm": "1d6", "command": "3d6+2"}},
    "trickster": {"name": "장난 가득 트릭스터", "primary": "guile", "pools": {
        "intimidate": "1d6", "guile": "4d6+3", "intuition": "3d6+2", "charm": "2d6+2", "command": "2d6"}},
    "scholar": {"name": "포켓몬 학자", "primary": None, "pools": {}}
}
# Core printed201 identifies Guile; Korean177 repeats the preceding template's
# Intimidate. Preserve the local original and expose the correction in state.
TRICKSTER_CORRECTION = {"kind": "translation_copy_error", "local": "input/ch05-pokemon.md:177",
    "original_label": "협박", "effective_skill": "guile", "authority": "PTU1.05 Core printed201 Playful Trickster"}


import resolution_transaction as _FINGERPRINTS

def _require(e, c, reason):
    if c.kind != "pokemon":
        raise ValueError("Pokemon skill state requires an actual Pokemon")
    if e.r._selected_rule(SOURCE) != SOURCE:
        raise ValueError("selected Pokemon skill source needs its own policy")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("explicit GM skill decision reason required")


def pool(value):
    if type(value) is int and 1 <= value <= 6:
        return value, 0
    match = re.fullmatch(r"([1-9][0-9]*)d6(?:([+-][0-9]+))?", value) if isinstance(value, str) else None
    if not match:
        raise ValueError("explicit positive Pokemon dice pool required")
    return int(match[1]), int(match[2] or 0)


def expression(dice, modifier):
    if type(dice) is not int or dice < 1:
        raise ValueError("Pokemon skill background cannot lower a pool below one die")
    return str(dice) + "d6" + (format(modifier, "+d") if modifier else "")


def _normalize(e, c, values, *, additional_only=False):
    if not isinstance(values, dict) or not values:
        raise ValueError("explicit skill pools required")
    result = {}
    for name, value in values.items():
        sid = S.skill_id(e.r.skill_policy, name, required=True)
        if sid in result:
            raise ValueError("duplicate aliases for one skill")
        if additional_only and sid not in I.SOCIAL | I.EDUCATION:
            raise ValueError("template adjustments require social or education skills")
        if sid in I.SOCIAL | I.EDUCATION and I.eligibility(e, c, sid) is not True:
            raise ValueError("explicit campaign skill permission required")
        result[sid] = expression(*pool(value))
    return result


def _replace(e, current, values):
    result = deepcopy(current)
    for sid, value in values.items():
        for old in list(result):
            if S.skill_id(e.r.skill_policy, old) == sid:
                del result[old]
        result[sid] = value
    return result


def _commit(e, c, skills, field, record, reason):
    import state_grants as G
    import state_fields as F
    def apply(staged_e, staged_c):
        receipt = F.base_patch(staged_c, {"skills": skills}, reason=reason, source=SOURCE)
        staged_c.spec[field] = deepcopy(record)
        validate_actor(staged_c)
        return {"record": deepcopy(record), "receipt": receipt}
    return G.transition(e, c, apply)


def choose_template(e, c, template, *, reason, education_skill=None, adjustments=None):
    _require(e, c, reason)
    if template not in TEMPLATES:
        raise ValueError("unknown source skill template")
    definition = deepcopy(TEMPLATES[template])
    if template == "scholar":
        sid = S.skill_id(e.r.skill_policy, education_skill, required=True)
        if sid not in I.EDUCATION:
            raise ValueError("Scholar requires one explicit Education skill")
        definition.update(primary=sid, pools={sid: "4d6"})
    elif education_skill is not None:
        raise ValueError("only Scholar selects an Education skill")
    values = _normalize(e, c, definition["pools"], additional_only=True)
    changes = {} if adjustments is None else _normalize(e, c, adjustments, additional_only=True)
    values.update(changes)
    if c.spec.get(FIELD) is not None:
        raise ValueError("a skill template is already assigned; use an explicit adjustment instead of stacking")
    history = c.spec.get("stat_history", [])
    if not isinstance(history, list):
        raise ValueError("individual evolution history must be a list")
    record = {"source": SOURCE, "template": template, "name": definition["name"],
        "primary": definition["primary"], "assigned_pools": values, "adjustments": changes,
        "reason": reason, "assigned_history_length": len(history), "evolutions": [], "adjustment_history": []}
    if template == "trickster":
        record["source_correction"] = deepcopy(TRICKSTER_CORRECTION)
    return _commit(e, c, _replace(e, c.spec.get("skills", {}), values), FIELD, record, reason)


def adjust(e, c, skills, *, reason):
    _require(e, c, reason)
    row = deepcopy(c.spec.get(FIELD))
    if not isinstance(row, dict):
        raise ValueError("an assigned template is required")
    validate_actor(c)
    values = _normalize(e, c, skills, additional_only=True)
    row["adjustment_history"].append({"source": SOURCE, "reason": reason, "skills": values})
    return _commit(e, c, _replace(e, c.spec.get("skills", {}), values), FIELD, row, reason)


def _current_pool(e, c, sid):
    values = [pool(v) for k, v in c.spec.get("skills", {}).items() if S.skill_id(e.r.skill_policy, k) == sid]
    if not values or len(set(values)) != 1:
        raise ValueError("selected skill must have one actual unambiguous assigned pool")
    return values[0]


def _event_digest(event):
    return _FINGERPRINTS.json_fingerprint(event, sort_keys=True, compact=False, allow_nan=True)


def evolve_template(e, c, *, history_index, primary_increase, other_skill=None, reason):
    _require(e, c, reason)
    row = deepcopy(c.spec.get(FIELD))
    if not isinstance(row, dict):
        raise ValueError("an assigned template is required")
    validate_actor(c)
    history = c.spec.get("stat_history", [])
    if type(history_index) is not int or not row["assigned_history_length"] <= history_index < len(history):
        raise ValueError("an actual evolution after template assignment is required")
    event = history[history_index]
    if event.get("event") != "evolution" or not event.get("previous_species") or event.get("species") == event["previous_species"]:
        raise ValueError("selected history entry is not an actual evolution")
    if primary_increase not in ("die", "modifier"):
        raise ValueError("choose one die or a +2 modifier explicitly")
    primary = row["primary"]
    secondary = None if other_skill is None else S.skill_id(e.r.skill_policy, other_skill, required=True)
    if row["template"] == "scholar":
        if secondary is not None:
            raise ValueError("Scholar evolution raises only its chosen Education skill")
    elif secondary is None or secondary == primary or secondary not in row["assigned_pools"]:
        raise ValueError("choose a different assigned template skill for the other increase")
    decision = {"history_index": history_index, "event_sha256": _event_digest(event),
        "primary": primary, "primary_increase": primary_increase, "other_skill": secondary}
    prior = next((r for r in row["evolutions"] if r["history_index"] == history_index), None)
    if prior is not None:
        if any(prior[k] != v for k, v in decision.items()):
            raise ValueError("this evolution already has a different recorded skill choice")
        return {"record": row, "already_applied": True}
    changes = {}; before_pools = {}
    for sid, mode in [(primary, primary_increase)] + ([] if secondary is None else [(secondary, "modifier" if primary_increase == "die" else "die")]):
        dice, modifier = _current_pool(e, c, sid)
        before_pools[sid] = expression(dice, modifier)
        changes[sid] = expression(dice + int(mode == "die"), modifier + 2 * int(mode == "modifier"))
    changes = _normalize(e, c, changes, additional_only=True)
    row["evolutions"].append({**decision, "reason": reason, "before_pools": before_pools, "applied_pools": changes})
    return _commit(e, c, _replace(e, c.spec["skills"], changes), FIELD, row, reason)


def background(e, c, name, *, raised, lowered, reason):
    _require(e, c, reason)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("named Pokemon skill background required")
    if not isinstance(raised, (list, tuple)) or not isinstance(lowered, (list, tuple)) or not 1 <= len(raised) <= 3 or len(raised) != len(lowered):
        raise ValueError("raise one to three skills and lower equally many other skills")
    ups = [S.skill_id(e.r.skill_policy, x, required=True) for x in raised]
    downs = [S.skill_id(e.r.skill_policy, x, required=True) for x in lowered]
    if len(set(ups + downs)) != len(ups + downs):
        raise ValueError("background skills must be distinct and disjoint")
    if c.spec.get(BACKGROUND) is not None:
        raise ValueError("one individual background is already recorded; no automatic stacking")
    changes = {}; before = {}
    for sid, delta in [(x, 1) for x in ups] + [(x, -1) for x in downs]:
        dice, modifier = _current_pool(e, c, sid)
        before[sid] = expression(dice, modifier)
        changes[sid] = expression(dice + delta, modifier)
    changes = _normalize(e, c, changes)
    record = {"source": SOURCE, "name": name, "raised": ups, "lowered": downs,
        "before": before, "after": changes, "reason": reason}
    return _commit(e, c, _replace(e, c.spec["skills"], changes), BACKGROUND, record, reason)


def validate_actor(c):
    row = c.spec.get(FIELD)
    if row is not None:
        if c.kind != "pokemon" or not isinstance(row, dict) or row.get("source") != SOURCE or row.get("template") not in TEMPLATES:
            raise ValueError("invalid sourced Pokemon skill template")
        if type(row.get("assigned_history_length")) is not int or not 0 <= row["assigned_history_length"] <= len(c.spec.get("stat_history", [])):
            raise ValueError("invalid template evolution observation boundary")
        if c.r._selected_rule(SOURCE) != SOURCE:
            raise ValueError("saved skill template source is not selected")
        primary = row.get("primary")
        if (row["template"] == "scholar" and primary not in I.EDUCATION) or (row["template"] != "scholar" and primary != TEMPLATES[row["template"]]["primary"]):
            raise ValueError("skill template primary disagrees with its source")
        if not isinstance(row.get("evolutions"), list) or not isinstance(row.get("adjustment_history"), list):
            raise ValueError("skill template history must be explicit lists")
        if any(not isinstance(x, dict) for x in row["evolutions"] + row["adjustment_history"]):
            raise ValueError("skill histories require explicit records")
        if row["template"] == "trickster" and row.get("source_correction") != TRICKSTER_CORRECTION:
            raise ValueError("Trickster requires its recorded source correction")
        for values in [row.get("assigned_pools", {})] + [x.get("skills", {}) for x in row.get("adjustment_history", [])]:
            if not isinstance(values, dict) or not values:
                raise ValueError("explicit template skill pools required")
            if not set(values) <= I.SOCIAL | I.EDUCATION:
                raise ValueError("template uses unknown additional skill identities")
            for value in values.values(): pool(value)
        seen = set(); history = c.spec.get("stat_history", [])
        for entry in row.get("evolutions", []):
            index = entry.get("history_index")
            if type(index) is not int or index in seen or not row["assigned_history_length"] <= index < len(history) or history[index].get("event") != "evolution" or entry.get("event_sha256") != _event_digest(history[index]):
                raise ValueError("skill evolution must refer to one unchanged actual evolution")
            seen.add(index)
            mode, secondary = entry.get("primary_increase"), entry.get("other_skill")
            if entry.get("primary") != primary or mode not in ("die", "modifier"):
                raise ValueError("invalid recorded evolution choice")
            if row["template"] == "scholar":
                if secondary is not None: raise ValueError("Scholar evolution has no second skill")
            elif secondary == primary or secondary not in row["assigned_pools"]:
                raise ValueError("invalid second evolution skill")
            for sid, change in [(primary, mode)] + ([] if secondary is None else [(secondary, "modifier" if mode == "die" else "die")]):
                before = pool(entry.get("before_pools", {}).get(sid))
                after = pool(entry.get("applied_pools", {}).get(sid))
                if after != (before[0] + int(change == "die"), before[1] + 2 * int(change == "modifier")):
                    raise ValueError("recorded skill evolution increment disagrees with its source")
    bg = c.spec.get(BACKGROUND)
    if bg is not None:
        if c.kind != "pokemon" or not isinstance(bg, dict) or bg.get("source") != SOURCE or not isinstance(bg.get("name"), str) or not bg["name"].strip():
            raise ValueError("invalid named Pokemon skill background")
        if c.r._selected_rule(SOURCE) != SOURCE:
            raise ValueError("saved skill background source is not selected")
        ups, downs = bg.get("raised", []), bg.get("lowered", [])
        if not isinstance(ups, list) or not isinstance(downs, list) or any(not isinstance(x, str) or S.skill_id(c.r.skill_policy, x) != x for x in ups + downs):
            raise ValueError("background requires canonical known skill identities")
        if not 1 <= len(ups) <= 3 or len(ups) != len(downs) or len(set(ups + downs)) != len(ups + downs):
            raise ValueError("invalid background skill balance")
        for sid in ups + downs:
            before, after = pool(bg["before"][sid]), pool(bg["after"][sid])
            if after != (before[0] + (1 if sid in ups else -1), before[1]):
                raise ValueError("background must change dice rank once and preserve its fixed modifier")
    return True

