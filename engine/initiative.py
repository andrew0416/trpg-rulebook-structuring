"""Source-owned common initiative calculation, with explicit unresolved decisions.

PTK ch07:25-32,584 and ch06:7 support descending initiative and isolated
paralysis floor(I/2). Tie direction/re-ties and modifier composition are not
invented here. Explicit GM answers are logged as adjudications, not source rules.
"""
import initiative_derivation as DERIVE
from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class InitiativeValue:
    value: object
    expression: str
    unresolved: tuple = ()
    derivation: object = None
    adjudicable: bool = False


def _int(value):
    return type(value) is int


def value(rules, actor, *, engine=None, procedure=None):
    """Read actual native inputs; an explicit procedure supplies order/basis."""
    try:
        authority = rules if hasattr(rules, 'selection') else actor.r
        if procedure is not None:
            DERIVE.selected(authority, procedure['source'])
        actual = DERIVE.subject(engine, actor, procedure)
        if actual.r is not authority:
            raise ValueError('initiative subject belongs to another rules selection')
        speed = actual.staged("spe")
        rows = DERIVE.contributions_for(rules, actor, actual, procedure, engine)
        calculated = DERIVE.derive(speed, rows, procedure)
    except DERIVE.InitiativePending as exc:
        detail = {'base':speed, 'initiative_contributions':rows} if 'rows' in locals() else None
        return InitiativeValue(None, "", (str(exc),), detail, True)
    except DERIVE.InitiativeStateError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return InitiativeValue(None, "", (str(exc),))
    calculated['speed_actor_id'] = actual.entity_id
    calculated['participant_id'] = actor['id'] if type(actor) is dict else actor.entity_id
    expression = str(speed)
    by_id = {row['id']:row for row in rows}
    for step in calculated['steps']:
        if step['law'] == 'add':
            expression += f"{sum(by_id[i]['value'] for i in step['contributors']):+d}"
        elif step['law'] == 'replace':
            expression = 'fixed='+str(by_id[step['selected'][0]]['value'])
        elif step['law'] == 'multiply':
            for identity in step['contributors']:
                ratio = DERIVE.COMPOSITION.R._number(by_id[identity]['value'])
                expression = f"({expression})*{ratio}" if ratio != DERIVE.Fraction(1,2) else f"({expression})/2"
            expression = calculated['rounding']+'('+expression+')'
    return InitiativeValue(calculated['value'], expression, derivation=calculated)


def _name(participant):
    return participant.get('name', participant['id']) if type(participant) is dict else participant.name


def _hold(engine, message):
    engine.log("[보류] 이니셔티브: " + message, "combat/initiative")
    return None


def _decision(engine, prompt):
    answer = engine.rulings.decide(prompt)
    if not isinstance(answer, dict) or not isinstance(answer.get("reason"), str) or not answer["reason"].strip():
        return None
    return answer


def _record(engine, prompt, answer):
    # This logs one use; Rulings.decide does not consume stored answers.
    engine.rulings.record("initiative_adjudication", prompt["type"], prompt,
                          answer, answer["reason"], "once")
    engine.log("[GM 이니셔티브 재정] " + answer["reason"], "gm/initiative")


def _tie_plan(engine, group, initiative_value, *, rolls=None):
    prompt = {"type": "initiative_tie_order", "unit": "combat/initiative",
              "text": "동률 순서의 고저/재동률 처리는 미확정입니다. 이전 결과를 재사용하지 않는 이 호출의 명시 순서 또는 주사위 정책과 이유를 정하세요.",
              "request_id": uuid4().hex,
              "initiative": initiative_value,
              "actors": [{"key": row[0], "name": _name(row[1])} for row in group],
              "rolls": rolls,
              "accepted": {"order": "exact permutation of actor keys, echo this request_id",
                           "policy": "highest_d20 or lowest_d20 (explicit GM policy)",
                           "same_face": "reroll or decide; reroll needs positive max_rounds"}}
    answer = _decision(engine, prompt)
    if answer is None:
        return None
    keys = [row[0] for row in group]
    if "order" in answer:
        # Index keys are call-local; a stored fixed order cannot bind a later roster.
        if answer.get("request_id") != prompt["request_id"]:
            return None
        chosen = answer["order"]
        if (not isinstance(chosen, list) or len(chosen) != len(keys)
                or any(not isinstance(key, str) for key in chosen)
                or len(set(chosen)) != len(chosen) or set(chosen) != set(keys)):
            return None
        _record(engine, prompt, answer)
        return ("order", chosen)
    if (rolls is None and answer.get("policy") in ("highest_d20", "lowest_d20")
            and answer.get("same_face") in ("reroll", "decide")):
        limit = answer.get("max_rounds")
        if answer["same_face"] == "reroll" and (not _int(limit) or limit < 1):
            return None
        _record(engine, prompt, answer)
        return ("policy", answer)
    return None


def _roll_group(engine, group, initiative_value, policy):
    """Reroll only unresolved face subgroups, under the recorded GM policy.

    max_rounds is a caller-selected computation bound, not a rulebook cap.
    Reaching it leaves the order pending, never falls back to insertion order.
    """
    pending = [group]
    rounds = 0
    while any(len(part) > 1 for part in pending):
        rounds += 1
        next_parts = []
        for part in pending:
            if len(part) == 1:
                next_parts.append(part)
                continue
            rolls = [(row, engine.d20()) for row in part]
            if any(not _int(face) or not 1 <= face <= 20 for _, face in rolls):
                return None
            faces = sorted({face for _, face in rolls}, reverse=policy["policy"] == "highest_d20")
            engine.log("이니셔티브 GM 동률 굴림: " + ", ".join(f"{row[0]}={face}" for row, face in rolls), "gm/initiative")
            for face in faces:
                subgroup = [row for row, result in rolls if result == face]
                if len(subgroup) > 1 and policy["same_face"] == "decide":
                    plan = _tie_plan(engine, subgroup, initiative_value,
                                     rolls=[{"key": row[0], "face": face} for row in subgroup])
                    if plan is None:
                        return None
                    by_key = {row[0]: row for row in subgroup}
                    next_parts.extend([[by_key[key]] for key in plan[1]])
                else:
                    next_parts.append(subgroup)
        pending = next_parts
        if policy["same_face"] == "reroll" and rounds >= policy["max_rounds"] and any(len(part) > 1 for part in pending):
            return None
    return [part[0] for part in pending]


def order(engine, combatants, *, procedures=None, round_no=None):
    """Return an ordinary resolved roster, or None to hold before round start.

    No actor/clock state is mutated. Missing/invalid decisions do not fabricate
    an order. Randomness is consumed only by an explicitly accepted tie policy.
    Decision and diagnostic logs are observable even when a request is held.
    """
    actors = list(combatants)
    if len({id(actor) for actor in actors}) != len(actors):
        return _hold(engine, "중복 전투원 입력")
    identities = [actor['id'] if type(actor) is dict else actor.entity_id for actor in actors]
    if len(set(identities)) != len(identities):
        return _hold(engine, "중복 참가자 ID")
    if procedures is None:
        procedures = {}
    if type(procedures) is not dict or set(procedures)-set(identities):
        return _hold(engine, "우선권 절차는 실제 참가자 ID로 지정해야 합니다")
    rule = engine.r.mech("combat/initiative")
    if rule.get("order_by") != "staged_stat.spe desc" or rule.get("tie_break") != "1d20":
        return _hold(engine, "수정된 기본 순서/동률 규칙은 별도 해석 필요")
    rows = []
    for index, actor in enumerate(actors):
        key = f"actor:{index}"
        result = value(engine.r, actor, engine=engine, procedure=procedures.get(identities[index]))
        if result.unresolved:
            if not result.adjudicable:
                return _hold(engine, _name(actor) + ": " + "; ".join(result.unresolved))
            prompt = {"type": "initiative_value", "unit": "combat/initiative",
                      "text": "이 전투원의 이니셔티브 합성이 미정입니다. 최종 정수값과 이유를 정하세요.",
                      "actor": {"key": key, "name": _name(actor), "entity_id": identities[index]},
                      "unresolved": list(result.unresolved),
                      "derivation": result.derivation}
            answer = _decision(engine, prompt)
            if answer is None or not _int(answer.get("value")):
                return _hold(engine, _name(actor) + ": " + "; ".join(result.unresolved))
            _record(engine, prompt, answer)
            result = InitiativeValue(answer["value"], "GM=" + str(answer["value"]))
        rows.append((key, actor, result))
    import field_effects as FIELD
    ascending = FIELD.initiative_ascending(engine, round_no=round_no)
    groups = [[row for row in rows if row[2].value == n]
              for n in sorted({row[2].value for row in rows}, reverse=not ascending)]
    # Obtain all first-stage decisions before consuming random faces.
    plans = []
    for group in groups:
        plan = _tie_plan(engine, group, group[0][2].value) if len(group) > 1 else ("order", [group[0][0]])
        if plan is None:
            return _hold(engine, "동률 순서는 명시적인 GM 결정이 필요합니다")
        plans.append(plan)
    resolved = []
    for group, plan in zip(groups, plans):
        if plan[0] == "order":
            by_key = {row[0]: row for row in group}
            part = [by_key[key] for key in plan[1]]
        else:
            part = _roll_group(engine, group, group[0][2].value, plan[1])
            if part is None:
                return _hold(engine, "동률 굴림의 재동률/입력/계산 한계가 미해결")
        resolved.extend(part)
    engine.log("이니셔티브" + ("(트릭룸)" if ascending else "") + ": " + ", ".join(f"{_name(actor)}({result.expression}={result.value})" for _, actor, result in resolved), "combat/initiative")
    return [actor for _, actor, _ in resolved]
