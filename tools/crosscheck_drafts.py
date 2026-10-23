"""
초안 교차검증: effect 레코드가 말하는 토큰(상태이상·스탯·숫자·타입·키워드)이 그 단위의 원문에 실제로 있는지 대조한다.
LLM 초안의 환각(원문에 없는 상태/스탯/수치)과 규칙 기반 오매칭을 같은 잣대로 잡는다.
  입력: output/ruleunits.jsonl (entity:move / entity:ability 의 mech.data.effects + text.body/summary)
  출력: output/draft-crosscheck.md (confidence 별 건수, 플래그 목록) + output/draft-crosscheck.jsonl
"""
import json
import hashlib
from pathlib import Path
import os
import re
import sys
from collections import Counter, defaultdict

STAT_KO = {"atk": ["공격"], "def": ["방어"], "spa": ["특수공격", "특수 공격", "특공"], "spd": ["특수방어", "특수 방어", "특방"], "spe": ["스피드", "속도"],
           "acc": ["명중"], "eva": ["회피"], "all": ["모든", "전부", "전투단계", "모두", "각 능력치", "능력치", "각 기본 스탯", "각각", "전투 단계"], "hp": ["HP", "체력"], "weight_class": ["체급", "무게"]}
TYPE_ALT = {"불꽃": ["불꽃", "불타입", "불 타입"], "물": ["물"], "풀": ["풀"], "전기": ["전기"], "얼음": ["얼음", "얼"], "악": ["악"], "땅": ["땅"]}
# 영문 코드로 적힌 날씨/지형 → 원문 표기
WEATHER_KO = {"sunny": ["쾌청", "햇살", "햇빛", "맑"], "rain": ["비"], "sandstorm": ["모래"], "hail": ["싸라기눈", "우박", "눈"], "snow": ["눈", "설경"], "fog": ["안개"], "none": ["날씨"], "any": ["날씨"]}
TERRAIN_KO = {"blocking": ["차단", "벽", "막"], "slow": ["험한", "느린", "둔화", "진흙", "수렁"], "snow": ["설경", "눈"], "rough": ["험한"], "water": ["물"], "ice": ["얼음"]}
# 상태 이름 → 원문에서 찾을 어간(번역 표기 흔들림 흡수)
STATUS_STEM = {"독": ["독"], "맹독": ["맹독", "독"], "화상": ["화상"], "마비": ["마비"], "잠듦": ["잠"], "얼음": ["얼"], "혼란": ["혼란"], "풀죽음": ["풀죽"],
               "격노": ["격노", "분노"], "헤롱헤롱": ["헤롱"], "저주": ["저주"], "조이기": ["조이", "조임"], "구속": ["구속", "붙잡"], "둔화": ["둔화", "느려", "스피드"],
               "취약": ["취약"], "억제": ["억제", "억눌"], "눈멂": ["눈멂", "눈이 멀", "실명", "눈멀"], "완전눈멂": ["눈멂", "눈멀", "완전"], "기절": ["기절"],
               "격려됨": ["격려"], "넘어짐": ["넘어"], "비틀거림": ["비틀"], "수렁": ["수렁"], "씨뿌리기": ["씨뿌리기", "씨"], "멍듦": ["멍"], "도발": ["도발"],
               "고통받음": ["고통"], "탈진": ["탈진"], "쇠약": ["쇠약"], "병듦": ["병"], "출혈": ["출혈"]}
TYPES = ["노말", "격투", "비행", "독", "땅", "바위", "벌레", "고스트", "강철", "불꽃", "물", "풀", "전기", "에스퍼", "얼음", "드래곤", "악", "페어리"]
NUM_KO = {1: ["1", "한", "하나", "일"], 2: ["2", "두", "둘", "이"], 3: ["3", "세", "셋", "삼"], 4: ["4", "네", "넷", "사"], 5: ["5", "다섯", "오"], 6: ["6", "여섯"], 10: ["10", "열"]}
SKIP_TYPES = {"trigger", "reaction", "rule", "gm", "connection", "usage_restriction", "note", "reveal", "random", "execute", "forbid", "limit", "cost", "craft", "tag", "restriction", "trainer_slot",
              "weapon", "vehicle", "z_crystal", "evolution_item", "contest_dice", "frequency_rule", "skill_rank_up", "counter", "custom_condition", "item_attack", "food_buff", "capture_mod", "summon", "zone"}


def has(body, needles):
    return any(n and n in body for n in needles)


def check_effect(e, body):
    """플래그 목록 반환: (종류, 토큰)"""
    flags = []
    t = e.get("type")
    if t in SKIP_TYPES:
        return flags
    # 상태 이름
    for key in ("status",):
        v = e.get(key)
        if isinstance(v, str) and v in STATUS_STEM and not has(body, STATUS_STEM[v]):
            flags.append(("상태 없음", v))
    # 스탯
    st = e.get("stat")
    stats = st if isinstance(st, list) else [st]
    for s in stats:
        if isinstance(s, str) and s in STAT_KO:
            b = body
            if s == "atk":
                b = b.replace("특수공격", "").replace("특공", "")
            if s == "def":
                b = b.replace("특수방어", "").replace("특방", "")
            if not has(b, STAT_KO[s]) and not (s in ("atk", "def", "spa", "spd", "spe") and has(body, STAT_KO["all"])):
                flags.append(("스탯 없음", s))
    # 숫자 (delta/value/meters/dc/bonus/steps/turns)
    for key in ("delta", "value", "meters", "dc", "bonus", "steps", "turns", "rounds", "amount"):
        v = e.get(key)
        if isinstance(v, bool) or not isinstance(v, int):
            continue
        n = abs(v)
        if n == 0:
            continue
        needles = NUM_KO.get(n, [str(n)])
        if not has(body, needles) and not (key == "delta" and n == 1):     # '한 단계' 가 생략되는 번역이 많아 ±1 은 봐준다
            flags.append(("수치 없음", f"{key}={v}"))
    # 타입
    for key in ("move_type", "add_type", "set_type", "lose_type", "immune_type", "absorb_type", "vs_type", "of_type"):
        v = e.get(key)
        if isinstance(v, str) and v in TYPES and not has(body, TYPE_ALT.get(v, [v])):
            flags.append(("타입 없음", v))
    v = e.get("type_name") or (e.get("types") if isinstance(e.get("types"), list) else None)
    if isinstance(v, list):
        for x in v:
            if x in TYPES and not has(body, TYPE_ALT.get(x, [x])):
                flags.append(("타입 없음", x))
    # 날씨/지형: 영문 코드 → 원문 표기
    for key, table in (("weather", WEATHER_KO), ("terrain", TERRAIN_KO)):
        v = e.get(key)
        if isinstance(v, str):
            code = re.sub(r"^hazard:", "", v)
            head = re.split(r"[ ,:/(+]", code)[0]
            needles = table.get(head, [head[:2] if re.match(r"[가-힣]", head) else head])
            if not has(body, needles):
                flags.append((f"{key} 없음", v))
    # 키워드/능력/동작 문자열 (앞 두 글자 어간으로 대조: 붙잡기 ↔ 붙잡고)
    for key in ("keyword", "capability", "maneuver", "ability"):
        v = e.get(key)
        if isinstance(v, str):
            head = re.split(r"[ ,:/(+]", v)[0]
            aliases = {"파워": ["Power Capability"], "높이뛰기": ["High Jump"], "멀리뛰기": ["Long Jump"]}
            if len(head) >= 2 and not has(body, [head, head[:2]] + aliases.get(head, [])):
                flags.append((f"{key} 없음", v))
    return flags



def load_resolutions(root):
    """Only explicit per-effect reviews are accepted; reviewed confidence alone is not evidence."""
    path = Path(root) / "data/source-verification-2026-10-10.json"
    if not path.exists():
        return {}
    return {c["id"]: c for c in json.loads(path.read_text(encoding="utf-8"))["cases"]
            if c.get("applied_to_rules") and c.get("crosscheck_resolution")}


def evidence_matches(root, unit, case):
    """Invalidate a review if its source body, effects, or any local reference changed."""
    if not case or case.get("id") != unit.get("id"):
        return False
    resolution = case.get("crosscheck_resolution", {})
    body = (unit.get("text", {}).get("body") or "") + " " + (unit.get("text", {}).get("summary") or "")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != resolution.get("body_sha256"):
        return False
    if (unit.get("mech") or {}).get("data", {}).get("effects") != resolution.get("effects"):
        return False
    evidence = case.get("evidence", [])
    if not evidence:
        return False
    root = Path(root).resolve()
    for ref in evidence:
        if "file" in ref:
            path = (root / ref["file"]).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                return False
            if hashlib.sha256(path.read_bytes()).hexdigest() != ref.get("file_sha256"):
                return False
        elif not ref.get("url"):
            return False
    return True


def partition_flags(root, unit, flags, resolutions):
    case = resolutions.get(unit["id"])
    if not evidence_matches(root, unit, case):
        return flags, []
    approved = case["crosscheck_resolution"]["flags"]
    return ([flag for flag in flags if flag not in approved],
            [flag for flag in flags if flag in approved])


def main(root):
    rows = [json.loads(l) for l in open(os.path.join(root, "output/ruleunits.jsonl"), encoding="utf-8")]
    resolutions = load_resolutions(root)
    resolved = []
    counts = Counter()
    flagged = Counter()
    out = []
    by_kind = defaultdict(Counter)
    for u in rows:
        m = u.get("mech")
        if not m or u["kind"] not in ("entity:move", "entity:ability", "entity:feat", "entity:item", "entity:edge", "entity:poke_edge"):
            continue
        body = (u.get("text", {}).get("body") or "") + " " + (u.get("text", {}).get("summary") or "")
        conf = m["confidence"] + ("" if u["kind"] in ("entity:move", "entity:ability") else "/" + u["kind"].split(":")[1])
        counts[conf] += 1
        fl = []
        for e in m["data"].get("effects", []):
            if isinstance(e, dict):
                for kind, tok in check_effect(e, body):
                    fl.append({"effect": e, "flag": kind, "token": tok})
        fl, accepted = partition_flags(root, u, fl, resolutions)
        if accepted:
            case = resolutions[u["id"]]
            resolved.append({"id": u["id"], "confidence": conf, "flags": accepted,
                             "finding": case["finding"], "evidence": case["evidence"]})
        if fl:
            flagged[conf] += 1
            for f in fl:
                by_kind[conf][f["flag"]] += 1
            out.append({"id": u["id"], "confidence": conf, "body": body.strip()[:300], "flags": fl})
    lines = ["# 초안 교차검증 (effect 토큰 ↔ 원문 대조, 자동 생성)", "",
             "| confidence | 단위 | 플래그 단위 | 비율 | 플래그 종류 |", "|---|---|---|---|---|"]
    for conf in sorted(counts):
        kinds = ", ".join(f"{k} {n}" for k, n in by_kind[conf].most_common())
        lines.append(f"| {conf} | {counts[conf]} | {flagged[conf]} | {100 * flagged[conf] // max(1, counts[conf])}% | {kinds} |")
    lines += ["", "플래그는 '원문에 그 토큰이 없다'는 뜻이지 곧 오류는 아니다(번역 표기 차이, 요약된 수치). 아래 목록을 사람이 보고 data/*-llm*.json 또는 패턴을 고친다.", ""]
    lines += [f"미해결 {len(out)}건 / 원전·참조 근거 확인 {len(resolved)}건 ({sum(len(r['flags']) for r in resolved)} 플래그).",
              "근거 확인은 해당 본문·효과·로컬 참조 파일 지문이 일치할 때만 유효하다. 수동 실행의 자동화를 뜻하지 않는다.", ""]
    for r in out:
        lines.append(f"## {r['id']} ({r['confidence']})")
        lines.append(f"- 원문: {r['body']}")
        for f in r["flags"]:
            lines.append(f"- [{f['flag']}: {f['token']}] `{json.dumps(f['effect'], ensure_ascii=False)[:160]}`")
        lines.append("")
    lines += ["## 원전·참조 근거로 확인된 경고", ""]
    for r in resolved:
        lines += [f"- **{r['id']}**: {r['finding']}"]
        for ref in r["evidence"]:
            lines.append("  - " + (ref.get("url") or ref.get("file", "")) + " " + str(ref.get("lines") or ref.get("section", "")))
    with open(os.path.join(root, "output/draft-crosscheck-resolved.jsonl"), "w", encoding="utf-8") as f:
        for r in resolved:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    open(os.path.join(root, "output/draft-crosscheck.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    with open(os.path.join(root, "output/draft-crosscheck.jsonl"), "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("\n".join(lines[:8]))
    print(f"플래그 단위 {len(out)}개")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
