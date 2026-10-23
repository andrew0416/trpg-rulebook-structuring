"""Trainer ordinary and drained AP spending (ch06:78-85).
Typed bound charges require a native effect owner; legacy text-only bound and
selectable costs remain holds until their activation lifetime is known.
"""
from action_point_account import ActionPointAccount, SOURCE
import re


def has_accounting(c):
    return ActionPointAccount(c).has_accounting()


def validate(c, *, source_required=True):
    return ActionPointAccount(c).validate(source_required=source_required)


def scene_actors(engine,actors=()):
    """Read-only known participant union; time_actors would bind session state."""
    rows=list(getattr(engine,'_time_actors',[]) or [])+list(getattr(engine,'everyone',[]) or [])+list(getattr(engine.gm,'everyone',[]) or [])+list(actors or [])
    return list({id(c):c for c in rows}.values())


def validate_scene(engine,actors=()):
    targets=scene_actors(engine,actors)
    for c in targets:validate(c,source_required=has_accounting(c))
    return targets


def finish_scene(engine,actors=()):
    for c in validate_scene(engine,actors):end_scene(c)


def extended_rest(c, *, request_id=None):
    return ActionPointAccount(c).extended_rest(request_id=request_id)


def maximum(c):
    return ActionPointAccount(c).maximum()

def cost_mode(header, effects):
    freq=header.get("frequency") or {}
    raw=freq.get("raw", "") if isinstance(freq,dict) else str(freq)
    text=(raw+" "+" ".join(str(e.get("ap", ""))+" "+str(e.get("note", "")) for e in effects if isinstance(e,dict) and e.get("type")=="cost")).lower()
    bound=any(x in text for x in ("지속", "bind"))
    drained=any(x in text for x in ("제거", "drain"))
    return "mixed" if bound and drained else "bind" if bound else "drain" if drained else "spend"


def quote(header, effects):
    freq=header.get("frequency") or {}
    raw=freq.get("raw","") if isinstance(freq,dict) else str(freq)
    ap=freq.get("ap") if isinstance(freq,dict) else None
    costs=[e for e in effects if isinstance(e,dict) and e.get("type")=="cost" and "ap" in e]
    if ap is None and not costs and not re.search(r"\d+\s*AP",raw,re.I):
        return 0,""
    text=raw+" "+" ".join(str(e.get("ap"))+" "+str(e.get("note","")) for e in costs)
    mode=cost_mode(header,effects)
    if mode in ("bind","mixed"):
        return None,"AP 지속 효과 수명 검증 필요"
    normalized=[]
    for effect in costs:
        cost=dict(effect)
        if mode=="drain" and isinstance(cost.get("ap"),str):
            match=re.fullmatch(r"(\d+)\s*\(제거\)",cost["ap"].strip())
            if match:cost["ap"]=int(match.group(1))
        normalized.append(cost)
    costs=normalized
    if any(e.get("optional") or type(e.get("ap")) is not int for e in costs):
        return None,"AP 선택/가변 비용 검증 필요"
    effect_amount=sum(e["ap"] for e in costs)
    if ap is None:
        if costs:ap=effect_amount
        else:
            m=re.search(r"(\d+)\s*AP",raw,re.I)
            ap=int(m.group(1)) if m else None
    if type(ap) is not int or ap<0 or any(e["ap"]<0 for e in costs):
        return None,"AP 비용 형식 검증 필요"
    if costs and effect_amount!=ap:
        return None,"AP 헤더/효과 비용 불일치"
    return ap,""

def available(c):
    return ActionPointAccount(c).available()

def check(engine,c,header,effects):
    amount,reason=quote(header,effects)
    if amount is None:
        engine.log("    [보류] "+reason,"trainer/action-points")
        return None
    if amount>available(c):
        engine.log(f"    AP 부족: 필요 {amount}, 잔여 {available(c)} → 실행 거부","trainer/action-points")
        return None
    return amount

def charge(c,amount,*,mode='spend',instance_id=None):
    return ActionPointAccount(c).charge(amount, mode=mode, instance_id=instance_id)


def release_binding(c,instance_id,*,expected_amount):
    return ActionPointAccount(c).release_binding(instance_id, expected_amount=expected_amount)


def spend(c,amount,header=None,effects=None):
    mode=cost_mode(header or {},effects or [])
    if mode in ('bind','mixed'):
        raise ValueError('binding needs an actual source-owned effect lifetime producer')
    charge(c,amount,mode=mode)


def end_scene(c, *, request_id=None):
    return ActionPointAccount(c).end_scene(request_id=request_id)
