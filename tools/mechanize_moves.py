"""
C층 기계화 실험: 기술(moves) 효과 텍스트를 패턴 매칭으로 '실행 가능한 mech' 로 바꾸고, 기술별 coverage 를 매긴다.
(SRD 실험의 다음 단계 3 "스펠 본문 → mech 초안 → 검수 큐" 의 규칙 기반 버전)

입력: output/entities/moves.json   (시트 자동 추출: 헤더 + 효과 텍스트 + mech_auto 식별 플래그)
출력: data/moves-mech.json         (id -> {header, effects[], narrative[], coverage})
      output/moves-mech-coverage.md

coverage
  full    : 효과 문장 전부가 실행 가능한 effect 로 바뀜 (효과 없음 포함)
  partial : 일부 문장만
  none    : 효과는 있는데 아무 문장도 못 바꿈
"""
import json
import os
import re
import sys
from collections import Counter

STAT_KO = {"공격": "atk", "방어": "def", "특수공격": "spa", "특수방어": "spd", "스피드": "spe", "특공": "spa", "특방": "spd", "명중": "acc", "회피": "eva"}
STATUS_NORM = {"중독": "독", "맹독": "맹독", "풀죽": "풀죽음", "마비": "마비", "화상": "화상", "얼음": "얼음", "잠듦": "잠듦", "혼란": "혼란",
               "헤롱헤롱": "헤롱헤롱", "저주": "저주", "난동": "난동", "억압": "억압", "사슬묶기": "사슬묶기", "취약": "취약", "넘어짐": "넘어짐",
               "둔화": "둔화", "구속": "구속", "수렁": "수렁", "실명": "실명", "악몽": "악몽", "넘어": "넘어짐", "둔화됩": "둔화", "얼어붙": "얼음", "조이기": "조이기", "독": "독"}
STATUS_ALT = "중독|맹독|풀죽|마비|화상|얼어붙|얼음|잠듦|혼란|헤롱헤롱|저주|난동|억압|사슬묶기|취약|넘어짐|둔화|구속|수렁|실명|악몽|조이기|독"
SENT = re.compile(r"(?<=[.。])\s+|\n+")
WEATHER = {"쾌청": "sunny", "비바라기": "rain", "싸라기눈": "hail", "모래바람": "sandstorm"}

ROLL_RE = re.compile(r"(?:명중\s*굴림(?:의\s*값|값)?(?:이|은|가)?\s*)?(?<![dD0-9])(\d+)\s*(?:이상|\+)(?:이|일|의)?\s*(?:나왔을\s*때|나오면|나올\s*경우|일\s*때|에서)?")
STAGE_RE = re.compile(r"((?:(?:공격|방어|특수공격|특수방어|스피드|특공|특방|명중|회피)(?:과|와|,|\s|및|/)*)+)\s*(?:의\s*)?전투단계(?:와|과)?\s*((?:(?:공격|방어|특수공격|특수방어|스피드|특공|특방|명중|회피)(?:를|을|과|와|,|\s)*)*)(?:를|가|은|는|을)?\s*(?:각각\s*)?([+\-−]\s*\d+)")
SUBJ_SELF = re.compile(r"사용자|자신|시전자")
SUBJ_ALL = re.compile(r"모든 대상|대상 전체|범위 내")
STATUS_RE = re.compile(rf"({STATUS_ALT})\s*(?:상태|이|에|를|을|으로|가|로)?\s*(?:만듭니다|됩니다|시킵니다|시키고|시켜|입힙니다|입습니다|빠집니다|빠뜨립니다|걸립니다|겁니다|합니다|되게|상태가|상태로|해집니다|습니다|받은 상태|한 상태|고\s|니다)")
ROLL_ANY_RE = re.compile(r"(?<![dD0-9])(\d+)\s*(?:이상|\+)")   # 3d8+10 같은 주사위 표기는 제외
STATUS_LIST_RE = re.compile(rf"({STATUS_ALT})\s*(?:과|와|및|,|이나|또는)\s*(?={STATUS_ALT})")
COND_MISS_RE = re.compile(r"빗나가면|빗나갈 경우|빗맞으면|빗나갔을 때")
COND_WEATHER_RE = re.compile(r"날씨가\s*(쾌청|비바라기|싸라기눈|모래바람)")
COND_KO_RE = re.compile(r"기절시켰을 경우|기절시키면|쓰러뜨리면")
DURATION_RE = re.compile(r"(\d+)\s*(?:턴|라운드)\s*(?:간|동안)|다음 턴이? 끝날 때까지|장면 끝까지|인카운터(?:가)? 끝날\s*때까지")
STAGE_RE3 = re.compile(r"(공격|방어|특수공격|특수방어|스피드|특공|특방|명중|회피)(?:의\s*전투단계|\s*전투단계)?(?:이|가|를|은|는|을)?\s*(\d+)\s*(?:단계|만큼)?\s*(낮아|낮춥|하락|떨어|오르|상승|올라|증가)")
STAGE_RE2 = re.compile(r"(공격|방어|특수공격|특수방어|스피드|특공|특방|명중|회피)(?:이|가|를|은|는|을)?\s*(?:전투단계\s*)?([+\-−]\s*\d+)\s*(?:만큼)?\s*(?:감소|하락|상승|증가)")
ALL_STAGES_RE = re.compile(r"모든\s*(?:스탯|전투단계)[^.]*?([+\-−]\s*\d+)")
RESET_STAGES_RE = re.compile(r"전투단계를\s*기본\s*상태로|전투단계를\s*0으로")
CRIT_RANGE_RE = re.compile(r"(?<![dD0-9])(\d+)\s*(?:이상|\+)[^.]*?치명타가\s*됩니다")
GRANT_RE = re.compile(r"\*?\s*습득\s*시\s*(\S+?)\s*재능을\s*얻")
HP_LOSS_RE = re.compile(r"체력\s*(\d+)\s*점?을\s*잃|(\d+)\s*의\s*체력을\s*잃")
HP_LOSS_LEVEL_RE = re.compile(r"사용자의\s*레벨만큼\s*체력을\s*잃")
HEAL_HALF_MAX_RE = re.compile(r"최대\s*체력의\s*절반만큼\s*체력")
RESTRICTION_RE = re.compile(r"^제한\s*[:：]\s*(.+?)(?:만\s*가능)?$")
ABILITY_SUPPRESS_RE = re.compile(r"특성(?:을|이)[^.]*?(?:무효화|비활성)")
CURE_ALL_RE = re.compile(r"모든\s*(?:영구적|지속적)[^.]*?상태(?:이상)?(?:가|를|이)?\s*(?:치료|제거|회복)")
NEXT_ROLL_RE = re.compile(r"다음\s*명중\s*굴림에\s*\+?(\d+)[^.]*?다음\s*피해\s*굴림에\s*\+?(\d+)")
CURE_RE = re.compile(rf"({STATUS_ALT})[^.]*?(?:제거|치료|회복)")
PUSH_RE = re.compile(r"(\d+)\s*[mM]\s*밀려")
HEAL_FRAC_RE = re.compile(r"최대\s*체력의\s*(\d+)/(\d+)\s*(?:만큼)?[^.]*?회복")
HEAL_HALF_RE = re.compile(r"(?:피해|데미지)의\s*절반만큼\s*체력")
NEVER_MISS_RE = re.compile(r"빗나가지\s*않")
EVASION_RE = re.compile(r"회피에\s*([+\-]\d+)")
ACC_PEN_RE = re.compile(r"명중에\s*([+\-]\d+)")
WEATHER_RE = re.compile(r"(쾌청|비바라기|싸라기눈|모래바람)(?:이|으로|로)?\s*(?:됩니다|만듭니다|바뀝니다|변합니다)")
TEMP_HP_RE = re.compile(r"임시\s*체력\s*(\d+)")
TICK_RE = re.compile(r"소량의\s*체력")
DB_COND_RE = re.compile(r"기본\s*(?:데미지|피해량?)(?:는|은|가|이|을|를)?\s*(?:대신\s*)?(\d+)")
RANGE_RE = re.compile(r"^(?:(근접)|(자신)|(전체)|(\d+))?\s*,?\s*(?:대상\s*(\d+))?|(파열|원뿔|직선|인접 폭발)\s*(\d+)|(\d+)\s*,\s*원거리 폭발\s*(\d+)")


def parse_range(rng):
    r = rng.strip()
    out = {"raw": r}
    m = re.match(r"^(근접|자신|전체|\d+)\s*,?\s*(?:대상\s*(\d+))?", r)
    if m:
        out["origin"] = "melee" if m.group(1) == "근접" else "self" if m.group(1) == "자신" else "field" if m.group(1) == "전체" else int(m.group(1))
        if m.group(2):
            out["targets"] = int(m.group(2))
    m = re.search(r"(파열|원뿔|직선|인접 폭발|원거리 폭발)\s*(\d+)", r)
    if m:
        out["shape"] = {"파열": "burst", "원뿔": "cone", "직선": "line", "인접 폭발": "close_blast", "원거리 폭발": "blast"}[m.group(1)]
        out["size"] = int(m.group(2))
    out["parsed"] = "origin" in out or "shape" in out
    return out


def parse_frequency(freq):
    f = freq.replace(" ", "")
    if f.startswith("임의"):
        return {"kind": "at_will"}
    if f.startswith("턴1회") or f == "EOT":
        return {"kind": "every_other_turn"}
    m = re.match(r"장면x?(\d+)?", f)
    if m:
        return {"kind": "scene", "uses": int(m.group(1) or 1)}
    m = re.match(r"(일일|하루)x?(\d+)?", f)
    if m:
        return {"kind": "daily", "uses": int(m.group(2) or 1)}
    if f.startswith("항상"):
        return {"kind": "static"}
    return {"kind": "unknown", "raw": freq}


def who(sent, pos=None):
    """효과 단어 위치(pos) 바로 앞에서 가장 가까운 주어가 사용자/자신이면 self, 대상이면 target."""
    head = sent if pos is None else sent[:pos]
    if re.match(r"^피해를 입힌 (?:후|이후)", sent) and "대상" not in head[9:]:
        return "self"                     # '피해를 입힌 후 … 상태가 됩니다' 의 생략된 주어는 사용자
    last_self = max(head.rfind("사용자"), head.rfind("자신"))
    last_tgt = max(head.rfind("대상"), head.rfind("적"))
    if last_self > last_tgt:
        return "self"
    if last_tgt > last_self:
        return "target"
    return "self" if SUBJ_SELF.search(sent) else "target"


def mechanize_effect(name, text):
    text = re.sub(r"\n(?!- )", " ", text)
    sents = [s.strip() for s in SENT.split(text) if s.strip() and s.strip() != "."]
    effects, narrative = [], []
    for s in sents:
        found = []
        cond = {}
        m = ROLL_RE.search(s) if ("명중" in s or "나오" in s or "나왔" in s or re.search(r"(?<![dD0-9])\d+\s*(?:이상|\+)", s)) else None
        if m and ("이상" in s or "+" in s):
            cond = {"on_natural_roll_min": int(m.group(1))}
        if "짝수" in s:
            cond = {"on_natural_roll": "even"}
        if COND_MISS_RE.search(s):
            cond["on_miss"] = True
        wm0 = COND_WEATHER_RE.search(s)
        if wm0:
            cond["if_weather"] = WEATHER[wm0.group(1)]
        if COND_KO_RE.search(s):
            cond["on_ko"] = True
        dm0 = DURATION_RE.search(s)
        if dm0:
            cond["duration"] = dm0.group(0)
        for m0 in STAGE_RE.finditer(s):
            stats, delta = m0.group(1) + " " + (m0.group(2) or ""), m0.group(3)
            d = int(delta.replace("−", "-").replace(" ", ""))
            tgt = who(s, m0.start())
            if "아군" in s[:m0.start()]:
                tgt = "self_and_allies" if "사용자와" in s or "자신과" in s else "allies"
            tf = re.search(r"(노말|격투|비행|독|땅|바위|벌레|고스트|강철|불꽃|물|풀|전기|에스퍼|얼음|드래곤|악|페어리)\s*타입(?:인)?\s*(?:포켓몬|대상)", s[:m0.start()])
            extra = {"target_filter": {"type": tf.group(1)}} if tf else {}
            for st in re.findall(r"공격|방어|특수공격|특수방어|스피드|특공|특방|명중|회피", stats):
                found.append({"type": "stage_change", "stat": STAT_KO[st], "delta": d, "target": tgt, **extra, **cond})
        if not any(f["type"] == "stage_change" for f in found):
            for m0 in STAGE_RE2.finditer(s):
                d = int(m0.group(2).replace("−", "-").replace(" ", ""))
                found.append({"type": "stage_change", "stat": STAT_KO[m0.group(1)], "delta": d, "target": who(s, m0.start()), **cond})
        if not any(f["type"] == "stage_change" for f in found):
            for m0 in STAGE_RE3.finditer(s):
                d = int(m0.group(2)) * (-1 if m0.group(3) in ("낮아", "낮춥", "하락", "떨어") else 1)
                found.append({"type": "stage_change", "stat": STAT_KO[m0.group(1)], "delta": d, "target": who(s, m0.start()), **cond})
        am_ = ALL_STAGES_RE.search(s)
        if am_ and not any(f["type"] == "stage_change" for f in found):
            d = int(am_.group(1).replace("−", "-").replace(" ", ""))
            found.append({"type": "stage_change", "stat": "all", "delta": d, "target": who(s), **cond})
        if re.search(r"모든\s*전투단계를\s*상승", s) and not any(f["type"] == "stage_change" for f in found):
            found.append({"type": "stage_change", "stat": "all", "delta": 1, "target": who(s, s.find("모든")), **cond})
        if re.search(r"현재\s*체력의\s*절반(?:을|만큼)?\s*(?:체력을\s*)?잃", s):
            found.append({"type": "hp_loss", "value": "current_hp/2", "target": who(s, s.find("현재")), **cond})
        if re.search(r"소량의\s*체력(?:을|만큼)?\s*잃", s) and not any(f["type"] == "hp_loss" for f in found):
            n_t = re.search(r"소량의\s*체력\s*(\d+)|(\d+)\s*소량", s)
            found.append({"type": "hp_loss", "value": f"tick*{(n_t.group(1) or n_t.group(2)) if n_t else 1}", "target": who(s, s.find("소량")), **cond})
        if RESET_STAGES_RE.search(s):
            found.append({"type": "reset_stages", "target": "all" if "모든" in s else who(s)})
        cm = CRIT_RANGE_RE.search(s)
        if cm:
            found.append({"type": "crit_range", "min": int(cm.group(1))})
        gm = GRANT_RE.search(s)
        if gm:
            found.append({"type": "grant_capability", "capability": gm.group(1)})
        hl = HP_LOSS_RE.search(s)
        if hl:
            found.append({"type": "hp_loss", "value": int(hl.group(1) or hl.group(2)), "target": "target"})
        if HP_LOSS_LEVEL_RE.search(s):
            found.append({"type": "hp_loss", "value": "user.level", "target": "target"})
        if HEAL_HALF_MAX_RE.search(s):
            found.append({"type": "heal", "fraction_of_max": [1, 2], "target": who(s)})
        rm = RESTRICTION_RE.match(s)
        if rm:
            found.append({"type": "weapon_restriction", "text": rm.group(1)})
        if ABILITY_SUPPRESS_RE.search(s):
            found.append({"type": "suppress_ability", "target": "target", "until": "encounter_end"})
        if CURE_ALL_RE.search(s):
            found.append({"type": "cure_all_status", "target": who(s)})
        nr = NEXT_ROLL_RE.search(s)
        if nr:
            found.append({"type": "next_roll_bonus", "accuracy": int(nr.group(1)), "damage": int(nr.group(2)), "target": "target"})
        for m0 in STATUS_RE.finditer(s):
            st = m0.group(1)
            c2 = dict(cond)
            prev = [r for r in ROLL_ANY_RE.finditer(s) if r.start() < m0.start()]
            if prev and "on_natural_roll_min" in c2:
                c2["on_natural_roll_min"] = int(prev[-1].group(1))
            tgt = who(s, m0.start())
            if "아군" in s[:m0.start()]:
                tgt = "allies"
            found.append({"type": "apply_status", "status": STATUS_NORM.get(st, st), "target": tgt, **c2})
        sts = [f for f in found if f["type"] == "apply_status"]
        if len(sts) >= 2 and re.search(r"1d[23]을?\s*굴", s):      # '1d3을 굴립니다; 1이면 마비, 2면 화상 …' → 하나만 무작위
            for f in sts:
                found.remove(f)
            found.append({"type": "apply_status_random", "options": [f["status"] for f in sts], "target": sts[0]["target"], **{k: v for k, v in sts[0].items() if k not in ("type", "status", "target")}})
        if any(f["type"] == "apply_status" for f in found):
            tgt0 = next(f["target"] for f in found if f["type"] == "apply_status")
            for st in STATUS_LIST_RE.findall(s):           # '난동과 혼란', '둔화 및 취약' 의 앞쪽 상태
                nm = STATUS_NORM.get(st, st)
                if not any(f["type"] == "apply_status" and f["status"] == nm for f in found):
                    found.append({"type": "apply_status", "status": nm, "target": tgt0, **cond})
        if "풀죽게" in s:
            found.append({"type": "apply_status", "status": "풀죽음", "target": "target", **cond})
        for st in CURE_RE.findall(s):
            if not any(f["type"] == "apply_status" and f["status"] == STATUS_NORM.get(st, st) for f in found):
                found.append({"type": "cure_status", "status": STATUS_NORM.get(st, st), "target": who(s)})
        if NEVER_MISS_RE.search(s):
            found.append({"type": "never_miss", **({"if_weather": cond["if_weather"]} if "if_weather" in cond else {})})
        pm = PUSH_RE.search(s)
        if pm:
            found.append({"type": "push", "meters": int(pm.group(1)), "target": "target"})
        hm = HEAL_FRAC_RE.search(s)
        if hm:
            found.append({"type": "heal", "fraction_of_max": [int(hm.group(1)), int(hm.group(2))], "target": who(s)})
        if HEAL_HALF_RE.search(s):
            found.append({"type": "drain", "fraction": 0.5})
        em = EVASION_RE.search(s)
        if em:
            found.append({"type": "evasion_mod", "value": int(em.group(1)), "target": who(s)})
        am = ACC_PEN_RE.search(s)
        if am:
            found.append({"type": "accuracy_mod", "value": int(am.group(1)), "target": who(s)})
        wm = WEATHER_RE.search(s)
        if wm:
            found.append({"type": "set_weather", "weather": WEATHER[wm.group(1)]})
        tm = TEMP_HP_RE.search(s)
        if tm:
            found.append({"type": "temp_hp", "value": int(tm.group(1)), "target": who(s)})
        dm = DB_COND_RE.search(s)
        if dm and ("경우" in s or "면" in s or "때" in s):
            found.append({"type": "conditional_damage_base", "damage_base": int(dm.group(1)), "condition_text": s})
        if found:
            for f in found:
                for k, v in cond.items():
                    f.setdefault(k, v)
                f["_src"] = s
            effects += found
        else:
            narrative.append(s)
    # 조건부 DB 는 조건이 자연어라 partial 로 취급
    exec_ok = [e for e in effects if e["type"] != "conditional_damage_base"]
    if not sents:
        cov = "full"
    elif not narrative and not any(e["type"] == "conditional_damage_base" for e in effects):
        cov = "full"
    elif effects:
        cov = "partial"
    else:
        cov = "none"
    return effects, narrative, cov


def main(src, dst, report_path):
    moves = [m for m in json.load(open(src, encoding="utf-8")) if not m.get("homebrew")]
    out = {}
    cov = Counter()
    eff_types = Counter()
    rng_ok = freq_ok = 0
    for m in moves:
        eff, nar, c = mechanize_effect(m["name"], m["effect"] or "")
        rng = parse_range(m["range"] or "")
        frq = parse_frequency(m["frequency"] or "")
        header_ok = bool(m["type"]) and bool(m["class"]) and rng["parsed"] and frq["kind"] != "unknown" and (m["class"] == "변화" or isinstance(m["damage_base"], int))
        if not header_ok and c == "full":
            c = "partial"
        cov[c] += 1
        rng_ok += rng["parsed"]
        freq_ok += frq["kind"] != "unknown"
        for e in eff:
            eff_types[e["type"]] += 1
        out[m["id"]] = {"name": m["name"], "eng": m["eng"], "confidence": "auto", "coverage": c,
                        "header": {"type": m["type"], "class": m["class"], "damage_base": m["damage_base"], "ac": m["ac"],
                                   "frequency": frq, "range": rng, "contest": m["contest"], "keywords": m.get("keywords", [])},
                        "effects": eff, "narrative": nar, "effect_text": m["effect"]}
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = len(moves)
    with_eff = sum(1 for m in moves if m["effect"])
    lines = ["# 기술(moves) 자동 기계화 커버리지 (코어 기술, 홈브류 제외)", "",
             f"| 항목 | 수 | 비율 |", "|---|---|---|",
             f"| 기술 수 | {n} | |",
             f"| 범위 문자열 파싱 | {rng_ok} | {rng_ok/n:.0%} |",
             f"| 빈도 문자열 파싱 | {freq_ok} | {freq_ok/n:.0%} |",
             f"| coverage full (헤더 OK + 효과 전부 실행 가능 또는 효과 없음) | {cov['full']} | {cov['full']/n:.0%} |",
             f"| coverage partial | {cov['partial']} | {cov['partial']/n:.0%} |",
             f"| coverage none (효과 있음, 전부 narrative) | {cov['none']} | {cov['none']/n:.0%} |",
             "", f"효과 텍스트가 있는 기술 {with_eff}개 기준 full {sum(1 for m in moves if m['effect'] and out[m['id']]['coverage']=='full')}개.", "",
             "## 생성된 effect 유형", "", "| 유형 | 수 |", "|---|---|"]
    for k, v in eff_types.most_common():
        lines.append(f"| {k} | {v} |")
    none_names = [m["name"] for m in moves if out[m["id"]]["coverage"] == "none"]
    lines += ["", f"## coverage none ({len(none_names)}개) 예", "", ", ".join(none_names[:60])]
    open(report_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
