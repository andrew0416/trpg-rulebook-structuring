"""
초안 검증기: DB 의 모든 effect 레코드(hand/auto/llm)를 어휘·필드·이름 기준으로 점검한다.
  - type 이 effect-vocabulary 에 없는가 (→ 어휘 확장 후보)
  - stat 이 atk/def/spa/spd/spe/acc/eva/all 이 아닌가, status 가 conditions.json 에 없는가
  - target 값이 허용 집합 밖인가, delta/value 가 정수도 아는 식도 아닌가
출력: output/draft-validation.md (유형별 건수 + 예시), 종료 코드 0
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

STATS = {"atk", "def", "spa", "spd", "spe", "acc", "eva", "all"}
TARGETS = {"self", "target", "all_targets", "allies", "self_and_allies", "enemies", "self and target", "self_or_ally", "attacker", "all", "all in burst",
           "allies in burst", "enemies within 3m", "allies within 5m", "allies within 2m", "all in burst 2", "cardinally adjacent to target",
           "enemies within burst 2", "attacks against user", "allies' melee vs enemy adjacent to user", "self_and_allies within 3m", "cured targets", "ally",
           "enemies within 6m", "풀 types within 5m", "chosen", "all_targets with filter", "holder", "wearer", "user", "ally", "own pokemon", "enemy", "attacker", "mount",
           "telepathic pokemon", "adjacent allies", "self and mount", "self and own pokemon", "that pokemon", "pokemon", "경화된 포켓몬"}
EXPR_OK = re.compile(r"^(tick(\*\d+)?|user\.level|current_hp/2|max_hp/[234]|-50% max|hp lost by user|damage taken since declaration|direct damage user took this round|\d+ - target\.weight_class|8 - target\.weight_class|to outside blast range|spe/2|[+\-]?\d+)$")


def main(root):
    vocab = json.load(open(os.path.join(root, "data/effect-vocabulary.json"), encoding="utf-8"))["effects"]
    known = set(vocab)
    sys.path.insert(0, os.path.join(root, "engine"))
    import effects_ext  # noqa  (확장 핸들러 설치)
    from effects import SUPPORTED, evaluate  # noqa
    known |= SUPPORTED

    class _D:  # 식 평가용 더미 전투원
        level, injuries, base_max_hp, max_hp, hp = 20, 1, 60, 54, 30
        spec = {"weight_class": 2, "loyalty": 2}
        stages, counters = {"atk": 1}, {}
        staged = lambda self, s: 10

    class _E:
        tick = lambda self, w: 6
    dummy = {"attacker": _D(), "target": _D(), "who": _D(), "engine": _E(), "db": 5}

    def expr_ok(v):
        return isinstance(v, int) or EXPR_OK.match(str(v)) or evaluate(v, dummy) is not None
    conds = {u["mech"]["data"]["name"] for u in json.load(open(os.path.join(root, "data/conditions.json"), encoding="utf-8"))} | {"독", "맹독", "조이기", "격려됨", "넘어짐"}
    rows = [json.loads(l) for l in open(os.path.join(root, "output/ruleunits.jsonl"), encoding="utf-8")]
    issues = defaultdict(list)
    counts = Counter()
    total = 0
    for u in rows:
        m = u.get("mech")
        if not m or u["kind"] not in ("entity:move", "entity:ability", "entity:feat", "entity:item", "entity:edge", "entity:poke_edge"):
            continue
        for e in m["data"].get("effects", []):
            if not isinstance(e, dict):
                issues["effect가 dict 아님"].append(u["id"]); continue
            total += 1
            t = e.get("type")
            if t not in known:
                issues[f"미등록 type: {t}"].append(u["id"]); counts["unknown_type"] += 1
            if t == "stage_change" and e.get("stat") not in STATS and not str(e.get("stat")).startswith(("highest", "two", "by_form", "atk|spa", "higher", "all", "chosen", "random", "each", "attack stat", "negative", "another")):
                issues[f"stat 이상: {e.get('stat')}"].append(u["id"]); counts["bad_stat"] += 1
            if t == "stage_change" and not isinstance(e.get("delta"), int) and not re.match(r"^[+\-]?\d+( \(choose\))?$|^±1", str(e.get("delta"))) and u["kind"] in ("entity:move", "entity:ability"):
                issues[f"delta 비정수: {e.get('delta')}"].append(u["id"]); counts["bad_delta"] += 1
            if t in ("apply_status", "cure_status") and isinstance(e.get("status"), str) and e["status"] not in conds and e["status"] not in ("all", "all persistent", "one", "one of 마비/얼음/화상/독/잠듦", "all volatile", "all persistent, volatile", "one chosen by each ally", "씨뿌리기", "persistent all", "volatile all", "any one", "up to 2", "persistent (선택)", "둔화/구속", "화상/마비/독", "독/맹독", "chosen (난동/혼란/화상/독/마비/잠듦)", "fixed at creation", "persistent"):
                issues[f"상태 이름 이상: {e.get('status')}"].append(u["id"]); counts["bad_status"] += 1
            if "target" in e and isinstance(e["target"], str) and e["target"] not in TARGETS and not e["target"].startswith(("enemies", "allies", "all", "self", "target", "own", "아군", "targets", "attacks")) and u["kind"] in ("entity:move", "entity:ability"):
                issues[f"target 이상: {e['target']}"].append(u["id"]); counts["bad_target"] += 1
            if t in ("hp_loss", "push", "heal", "temp_hp") and "value" in e and not expr_ok(e["value"]) and u["kind"] in ("entity:move", "entity:ability"):
                issues[f"value 식 미등록: {e['value']}"].append(u["id"]); counts["expr"] += 1
            if t == "push" and "meters" in e and not expr_ok(e["meters"]):
                issues[f"push 식 미등록: {e['meters']}"].append(u["id"]); counts["expr"] += 1
    lines = ["# 초안 검증 결과 (자동 생성)", "", f"effect 레코드 {total}개 검사. 문제 종류 {len(issues)}개, 건수 {sum(len(v) for v in issues.values())}개.", "",
             "| 문제 | 건수 | 예 |", "|---|---|---|"]
    for k, v in sorted(issues.items(), key=lambda x: -len(x[1])):
        lines.append(f"| {k} | {len(v)} | {', '.join(v[:4])} |")
    open(os.path.join(root, "output/draft-validation.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
