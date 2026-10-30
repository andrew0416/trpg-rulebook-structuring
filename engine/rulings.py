"""
GM 재정(개변) 층. 룰북 데이터(core-rules / lookup / moves-* / abilities-*)는 손대지 않고, 엔진이 값을 읽는 순간 덮어쓴다.
모든 재정은 이유와 함께 기록되고(engine.rulings.log) 보고서로 남는다. 다섯 가지 손잡이:
  1. formula   : 공식 치환 — tick="max_hp / 8", max_hp.pokemon="level + hp*4 + 10", crit_range=18, massive_damage=0.4, stab=3 …
  2. mech      : 단위 mech 필드 치환 — ("combat/critical-hit", "default_range", 18), ("combat/damage-chart", "by_damage_base.4.set.mid", 12) …
  3. effect    : 기술/특성 effect 패치 — add / remove / replace / set (평탄화 키 포함)
  4. situational: 상황 수정치 — 명중/회피/피해/DC 에 ±N (1회 또는 장면 동안, 전투원 지정 가능)
  5. answer·hook: GM 프롬프트에 대한 답(스크립트/대화형), effect 실행 전·피해 확정 전 가로채기 함수
scope: "campaign"(해제 안 됨) / "scene"(end_scene 에서 해제) / "once"(한 번 쓰면 소진).
"""
import copy
import json
import math
import os
import re

FORMULA_DEFAULTS = {        # 이름 → (출처 단위, 경로) 또는 기본 식. 엔진은 engine.formula(name, **vars) 로 읽는다.
    "tick": ("combat/tick-of-hit-points", "tick"),                   # "max_hp / 10"
    "max_hp.pokemon": ("combat/hit-points", "pokemon"),              # "level + hp*3 + 10"
    "max_hp.trainer": ("combat/hit-points", "trainer"),              # "level*2 + hp*3 + 10"
    "injury_penalty": ("combat/injuries", "max_hp_penalty_per_injury"),   # "max_hp / 10"
    "crit_range": ("combat/critical-hit", "default_range"),          # 20
    "massive_damage": ("combat/injuries", "massive_damage_fraction"),      # 0.5
    "stab": ("combat/stab", "damage_base_bonus"),                    # 2
}
SAFE = re.compile(r"^[0-9+\-*/(). ,a-z_]*$")


def calc(expr, variables):
    """Evaluate exact intermediates; each native consumer owns its rounding boundary."""
    import arithmetic as A
    return A.evaluate(expr, variables)


def _validate_read_adjudication(reason, scope):
    if type(reason) is not str or not reason.strip():
        raise ValueError('explicit adjudication reason required')
    if type(scope) is not str or scope not in ('scene', 'campaign'):
        raise ValueError('supported adjudication scope required: scene or campaign')


class Rulings:
    def __init__(self):
        self.formulas = {}          # name -> {"expr", "scope", "reason"}
        self.mech = {}              # uid -> {path: {"value", "scope", "reason"}}
        self.effects = {}           # move_id -> [ {"op", "match", "effect", "scope", "reason"} ]
        self.situational = []       # {"modifier", "who", "value", "uses", "scope", "reason"}
        self.answers = []           # {"key", "answer", "scope", "reason"}
        self.hooks = {"before_effect": [], "before_damage": [], "before_accuracy": []}
        self.provider = None        # callable(prompt: dict) -> answer | None  (대화형 GM 등)
        self.log = []
        self._mech_cache = {}

    # ---------- 기록 ----------
    def record(self, kind, what, before, after, reason, scope):
        entry = {"kind": kind, "what": what, "before": before, "after": after, "reason": reason, "scope": scope}
        self.log.append(entry)
        return entry

    # ---------- 1. 공식 ----------
    def set_formula(self, name, expr, reason="", scope="campaign"):
        _validate_read_adjudication(reason, scope)
        before = self.formulas.get(name, {}).get("expr")
        self.formulas[name] = {"expr": expr, "scope": scope, "reason": reason}
        return self.record("formula", name, before, expr, reason, scope)

    def formula_expr(self, name, rules):
        if name in self.formulas:
            return self.formulas[name]["expr"]
        src = FORMULA_DEFAULTS.get(name)
        if src is None:
            raise KeyError(name)
        uid, path = src
        return rules.mech(uid)[path]

    # ---------- 2. mech 필드 ----------
    def set_mech(self, uid, path, value, reason="", scope="campaign", rules=None):
        _validate_read_adjudication(reason, scope)
        before = None
        if rules is not None:
            try:
                before = _get_path(rules.mech(uid), path)
            except Exception:
                before = None
        self.mech.setdefault(uid, {})[path] = {"value": value, "scope": scope, "reason": reason}
        self._mech_cache.pop(uid, None)
        return self.record("mech", f"{uid}.{path}", before, value, reason, scope)

    def apply_mech(self, uid, data):
        ov = self.mech.get(uid)
        if not ov:
            return data
        # Reapply to the currently selected base; a UID alone does not identify a version.
        d = copy.deepcopy(data)
        for path, spec in ov.items():
            _set_path(d, path, spec["value"])
        return d

    # ---------- 3. effect 패치 ----------
    def patch_effect(self, move_id, op, effect=None, match=None, reason="", scope="campaign"):
        """op: add(effect 추가) / remove(match 와 맞는 effect 제거) / replace(match → effect) / set(평탄화 키 직접 설정: effect 가 dict of mm keys)."""
        self.effects.setdefault(move_id, []).append({"op": op, "match": match, "effect": effect, "scope": scope, "reason": reason})
        return self.record("effect", f"{move_id} {op} {match or ''}", None, effect, reason, scope)

    def apply_effects(self, move_id, mm):
        patches = self.effects.get(move_id)
        if not patches:
            return mm
        mm = copy.deepcopy(mm)
        ex = mm.setdefault("effects_exec", [])
        for p in patches:
            op, m, eff = p["op"], p["match"], p["effect"]
            if op == "add":
                ex.append(dict(eff))
            elif op == "remove":
                ex[:] = [e for e in ex if not _match(e, m)]
                for k in list(mm):          # 평탄화된 키(apply_status / zone / never_miss / push / drain / evasion_mod …)도 같은 이름이면 제거
                    if k != "effects_exec" and (k == m or (isinstance(m, dict) and m.get("type") == k)):
                        mm.pop(k)
            elif op == "replace":
                ex[:] = [dict(eff) if _match(e, m) else e for e in ex]
                if isinstance(m, dict) and m.get("type") in mm and m.get("type") != "effects_exec":
                    mm.pop(m["type"])
                    ex.append(dict(eff))
            elif op == "set" and isinstance(eff, dict):
                mm.update(eff)
        return mm

    # ---------- 4. 상황 수정치 ----------
    def add_situational(self, modifier, value, who=None, uses=1, reason="", scope="scene"):
        """modifier: accuracy / evasion / damage / dc / damage_mult. who: 전투원 이름(None 이면 모두). uses: 정수(소진) 또는 'scene'."""
        e = {"modifier": modifier, "who": who, "value": value, "uses": uses, "scope": scope, "reason": reason}
        self.situational.append(e)
        return self.record("situational", f"{modifier} {who or '*'}", None, value, reason, scope)

    def consume(self, modifier, who_name, engine=None, *, ignore_penalties=False):
        """해당 수정치의 합. 1회성은 소진한다."""
        total = 0
        for e in list(self.situational):
            if e["modifier"] != modifier or (e["who"] not in (None, who_name)):
                continue
            value = max(0, e['value']) if ignore_penalties else e['value']
            total += value
            if engine is not None:
                engine.log(f"    [GM 개변] {modifier} {value:+} ({e['reason']})", "gm/situational")
            if isinstance(e["uses"], int):
                e["uses"] -= 1
                if e["uses"] <= 0:
                    self.situational.remove(e)
        return total

    # ---------- 5. 답·훅 ----------
    def add_answer(self, key, answer, reason="", scope="scene"):
        self.answers.append({"key": key, "answer": answer, "scope": scope, "reason": reason})
        return self.record("answer", key, None, answer, reason, scope)

    def decide(self, prompt):
        """프롬프트(dict: type, text, unit…)에 대한 GM 의 답. 스크립트 답 → 제공자(대화형) → None."""
        for a in self.answers:
            k = a["key"]
            if k == prompt.get("type") or k == prompt.get("unit") or (isinstance(k, str) and k in str(prompt.get("text", ""))):
                return a["answer"]
        if self.provider is not None:
            return self.provider(prompt)
        return None

    def add_hook(self, when, fn, reason="", scope="scene"):
        self.hooks[when].append({"fn": fn, "reason": reason, "scope": scope})
        return self.record("hook", when, None, getattr(fn, "__name__", "fn"), reason, scope)

    def run_hooks(self, when, value, ctx, engine=None):
        for h in self.hooks.get(when, []):
            new = h["fn"](value, ctx)
            if new is not None and new != value:
                if engine is not None:
                    engine.log(f"    [GM 개변] {when}: {_brief(value)} → {_brief(new)} ({h['reason']})", "gm/hook")
                value = new
        return value

    # ---------- 범위 해제 ----------
    def end_scene(self, engine=None):
        n = 0
        for name in [k for k, v in self.formulas.items() if v["scope"] == "scene"]:
            self.formulas.pop(name); n += 1
        for uid in list(self.mech):
            for path in [p for p, v in self.mech[uid].items() if v["scope"] == "scene"]:
                self.mech[uid].pop(path); n += 1
            if not self.mech[uid]:
                self.mech.pop(uid)
            self._mech_cache.pop(uid, None)
        for mid in list(self.effects):
            self.effects[mid] = [p for p in self.effects[mid] if p["scope"] != "scene"]
            n += 1
            if not self.effects[mid]:
                self.effects.pop(mid)
        self.situational = [e for e in self.situational if e["scope"] != "scene"]
        self.answers = [a for a in self.answers if a["scope"] != "scene"]
        for k in self.hooks:
            self.hooks[k] = [h for h in self.hooks[k] if h["scope"] != "scene"]
        if engine is not None:
            engine.log(f"[GM 개변] 장면 종료: 장면 범위 재정 해제", "gm/end_scene")
        self.record("end_scene", "scene", None, None, "", "scene")
        return n

    # ---------- 파일 ----------
    def load(self, path, rules=None):
        if not os.path.exists(path):
            return 0
        data = json.load(open(path, encoding="utf-8"))
        n = 0
        for r in data.get("rulings", []):
            k = r.get("kind")
            scope, reason = r.get("scope", "campaign"), r.get("reason", "")
            if k == "formula":
                self.set_formula(r["name"], r["expr"], reason, scope)
            elif k == "mech":
                self.set_mech(r["unit"], r["path"], r["value"], reason, scope, rules)
            elif k == "effect":
                self.patch_effect(r["move"], r["op"], r.get("effect"), r.get("match"), reason, scope)
            elif k == "situational":
                self.add_situational(r["modifier"], r["value"], r.get("who"), r.get("uses", 1), reason, scope)
            elif k == "answer":
                self.add_answer(r["key"], r["answer"], reason, scope)
            else:
                continue
            n += 1
        return n

    def report(self):
        lines = ["# GM 재정 기록 (자동 생성)", "", "| # | 종류 | 대상 | 전 | 후 | 범위 | 이유 |", "|---|---|---|---|---|---|---|"]
        for i, e in enumerate(self.log, 1):
            lines.append(f"| {i} | {e['kind']} | {e['what']} | {_brief(e['before'])} | {_brief(e['after'])} | {e['scope']} | {e['reason']} |")
        return "\n".join(lines) + "\n"


def _brief(v):
    s = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
    return s[:60]


def _match(e, m):
    if m is None:
        return False
    if isinstance(m, str):
        return e.get("type") == m
    return all(e.get(k) == v for k, v in m.items())


def _get_path(d, path):
    cur = d
    for p in path.split("."):
        cur = cur[int(p)] if isinstance(cur, list) else cur[p]
    return cur


def _set_path(d, path, value):
    parts = path.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur[int(p)] if isinstance(cur, list) else cur.setdefault(p, {})
    last = parts[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


class InteractiveGM:
    """대화형 제공자: 터미널에서 GM 이 직접 답한다 (빈 입력이면 엔진 기본값)."""
    def __call__(self, prompt):
        try:
            ans = input(f"[GM] {prompt.get('type')}: {prompt.get('text')} > ").strip()
        except EOFError:
            return None
        return ans or None
