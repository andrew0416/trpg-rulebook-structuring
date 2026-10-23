"""
재주(feat) 규칙 기반 기계화 → data/feats-mech.json, output/feats-mech-coverage.md
헤더: frequency(kind/uses/ap)·action·trigger·target·prereq 는 블록 라벨에서. effects 는 효과문의 정형 패턴에서:
  재능 부여, 기술 습득, 면역, 명중/데미지/회피/피해감소/스킬 보너스, 전투단계, 소량 회복/임시 체력, 체력 N 회복, 기본 스탯 +N, 이니셔티브, 상태 부여, 리롤, 함정 생성, 기술 목록 제한, 리롤, 엣지/재주 부여.
남은 문장은 narrative 로 두고 coverage 를 full/partial/none 으로 표시한다 (기술 기계화와 같은 규약, LLM 초안은 data/feats-llm.json 이 보충).
  python -X utf8 -I tools/mechanize_feats.py <root>
"""
import json
import os
import re
import sys
from collections import Counter

STAT = r"(공격|방어|특수공격|특공|특수방어|특방|스피드|명중|회피|HP|체력)"
STAT_KO = {"공격": "atk", "방어": "def", "특수공격": "spa", "특공": "spa", "특수방어": "spd", "특방": "spd", "스피드": "spe", "명중": "acc", "회피": "eva", "HP": "hp", "체력": "hp"}
STATUS = r"(화상|얼음|마비|독|맹독|잠듦|혼란|풀죽음|둔화|구속|수렁|넘어짐|취약|억압|난동|헤롱헤롱|저주|사슬묶기|조이기|실명|악몽)"
SKILLS = r"(곡예|육상|전투|협박|매력|명령|교활|집중|직감|은신|지각|생존|일반 ?지식|의학|오컬트학|포켓몬학|기술학|교육학)"
NUM = r"([+\-]?\d+)"


def parse_frequency(raw):
    raw = (raw or "").strip()
    out = {"raw": raw}
    m = re.search(r"(\d+)\s*AP", raw)
    if m:
        out["ap"] = int(m.group(1))
    if raw.startswith("항상"):
        out["kind"] = "static"
    elif raw.startswith("임의") or ("AP" in raw and "장면" not in raw and "하루" not in raw):
        out["kind"] = "at_will"
    elif m2 := re.match(r"(장면|하루|일일)\s*x?\s*(\d+)?", raw):
        out["kind"] = "scene" if m2.group(1) == "장면" else "daily"
        out["uses"] = int(m2.group(2) or 1)
    elif raw:
        out["kind"] = "unknown"
    else:
        out["kind"] = "static"
    a = re.search(r"-\s*(.+)$", raw)
    act = a.group(1).strip() if a else ("항상" if out["kind"] == "static" else "")
    out["action"] = {"기본 행동": "standard", "신속 행동": "swift", "자유 행동": "free", "연장 행동": "extended", "이동 행동": "shift", "완전 행동": "full", "특수": "special", "항상": "static"}.get(act.split("+")[0].strip(), act or "static")
    return out


def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.다요])\s+(?=[^\s])|\n", text or "") if s.strip()]


PATTERNS = [
    (re.compile(r"[‘'\"]?([가-힣A-Za-z0-9·, ]+?)[’'\"]?\s*재능(?:을|를)?\s*(?:얻|가집니다|획득|가지)"), lambda m: [{"type": "grant_capability", "capability": x.strip()} for x in re.split(r"[,·]|와|과|및", m.group(1)) if x.strip()]),
    (re.compile(r"[‘'\"]?([가-힣A-Za-z0-9!·, ]+?)[’'\"]?\s*기술(?:을|를)?\s*(?:배웁니다|배운다|습득|얻습니다)"), lambda m: [{"type": "grant_move", "moves": [x.strip() for x in re.split(r"[,·]|와|과|및", m.group(1)) if x.strip()]}]),
    (re.compile(STATUS + r"(?:에|에 대한|에 대해)?\s*면역"), lambda m: [{"type": "immunity", "status": [m.group(1)]}]),
    (re.compile(r"명중\s*(?:굴림|체크)?에?\s*\+?" + NUM + r"\s*(?:의\s*)?보너스"), lambda m: [{"type": "accuracy_mod", "value": int(m.group(1)), "target": "self"}]),
    (re.compile(r"(?:데미지|피해)\s*굴림에?\s*\+?" + NUM + r"\s*(?:의\s*)?보너스"), lambda m: [{"type": "damage_roll_mod", "value": int(m.group(1))}]),
    (re.compile(r"(?:데미지|피해)\s*굴림(?:에|의)\s*" + NUM + r"\s*(?:의\s*)?(?:패널티|페널티)"), lambda m: [{"type": "damage_roll_mod", "value": -abs(int(m.group(1)))}]),
    (re.compile(r"회피(?:에|를)?\s*\+" + NUM), lambda m: [{"type": "evasion_mod", "value": int(m.group(1)), "target": "self"}]),
    (re.compile(r"\+" + NUM + r"\s*(?:의\s*)?회피"), lambda m: [{"type": "evasion_mod", "value": int(m.group(1)), "target": "self"}]),
    (re.compile(r"피해\s*감소\s*\+?" + NUM), lambda m: [{"type": "damage_reduction", "value": int(m.group(1)), "target": "self"}]),
    (re.compile(STAT + r"\s*(?:스탯)?(?:의|을|를)?\s*전투단계(?:를|가|은|는)?\s*" + NUM + r"\s*(?:만큼|단계)?\s*(상승|증가|하락|감소|올|내)"), lambda m: [{"type": "stage_change", "stat": STAT_KO[m.group(1)], "delta": (1 if m.group(3) in ("상승", "증가", "올") else -1) * abs(int(m.group(2))), "target": "target"}]),
    (re.compile(r"전투단계(?:를|에)?\s*\+" + NUM), lambda m: [{"type": "stage_change", "stat": "chosen", "delta": int(m.group(1)), "target": "self"}]),
    (re.compile(r"소량의\s*(?:임시\s*)?체력(?:을|를)?\s*(?:회복|얻|치유|되찾)"), lambda m: [{"type": "heal", "amount": "tick", "target": "target"}]),
    (re.compile(r"소량의\s*임시\s*체력"), lambda m: [{"type": "temp_hp", "value": "tick", "target": "target"}]),
    (re.compile(r"체력(?:을|를)?\s*" + NUM + r"\s*(?:만큼\s*)?(?:회복|얻|치유)"), lambda m: [{"type": "heal", "amount": abs(int(m.group(1))), "target": "target"}]),
    (re.compile(r"(?:기본|기초)\s*" + STAT + r"\s*(?:스탯)?(?:에|이|가|을|를)?\s*\+?" + NUM + r"\s*(?:증가|상승|보너스)?"), lambda m: [{"type": "stat_base_mod", "stat": STAT_KO[m.group(1)], "value": int(m.group(2))}]),
    (re.compile(SKILLS + r"(?:\s*(?:체크|굴림|스킬))?(?:에|의)?\s*\+" + NUM), lambda m: [{"type": "skill_mod", "skill": m.group(1).replace(" ", ""), "value": int(m.group(2))}]),
    (re.compile(r"이니셔티브(?:를|가|는)?\s*0"), lambda m: [{"type": "initiative", "set_to": 0, "target": "target"}]),
    (re.compile(r"이니셔티브(?:에|를)?\s*\+" + NUM), lambda m: [{"type": "initiative", "delta": int(m.group(1)), "target": "self"}]),
    (re.compile(r"(?:대상|적|상대)(?:은|는|이|가)?\s*" + STATUS + r"\s*(?:상태|이)?\s*(?:가\s*)?(?:됩니다|된다|에 걸|상태로)"), lambda m: [{"type": "apply_status", "status": m.group(1), "target": "target"}]),
    (re.compile(r"다시\s*굴|리롤"), lambda m: [{"type": "reroll", "roll": "specified"}]),
    (re.compile(r"[‘'\"]?([가-힣]+)[’'\"]?\s*함정(?:을|를)?\s*(?:생성|설치)"), lambda m: [{"type": "create_terrain", "terrain": "hazard:" + m.group(1), "cells": "adjacent"}]),
    (re.compile(r"기본 기술 목록 제한이\s*\+" + NUM), lambda m: [{"type": "rule", "move_slots": f"+{m.group(1)}"}]),
    (re.compile(r"(?:자격을 갖춘|조건을 충족하는)\s*(?:아무\s*)?[‘'\"]?([가-힣 ]+?)[’'\"]?\s*(?:레시피|엣지)(?:를|을)?\s*(?:얻|제작|배)"), lambda m: [{"type": "rule", "grants": m.group(1).strip()}]),
    (re.compile(r"(\d+)\s*AP(?:를|을)?\s*(?:지불|소모|사용)"), lambda m: [{"type": "cost", "ap": int(m.group(1))}]),
    (re.compile(r"(?:두 번|2번|두번)\s*굴리고\s*(?:더\s*)?(?:나은|좋은|높은)"), lambda m: [{"type": "reroll", "roll": "take better of two"}]),
]


def mechanize(feat):
    effects, matched = [], set()
    text = feat.get("effect") or ""
    sents = split_sentences(text)
    for i, s in enumerate(sents):
        for rx, fn in PATTERNS:
            for m in rx.finditer(s):
                for e in fn(m):
                    e["_src"] = s[:120]
                    effects.append(e)
                matched.add(i)
    narrative = [s for i, s in enumerate(sents) if i not in matched]
    header = {"frequency": parse_frequency(feat.get("frequency")), "trigger": feat.get("trigger") or None, "target": feat.get("target") or None, "prereq": feat.get("prereq") or None, "condition": feat.get("condition") or None}
    if header["trigger"]:
        effects.insert(0, {"type": "trigger", "text": header["trigger"]})
    cov = "none" if not effects or (len(effects) == 1 and effects[0]["type"] == "trigger") else ("full" if not narrative else "partial")
    if not text.strip():
        cov = "none"
    return {"name": feat["name"], "eng": feat.get("eng"), "confidence": "auto", "coverage": cov, "header": header, "effects": effects, "narrative": narrative, "effect_text": text}


def main(root):
    feats = json.load(open(os.path.join(root, "output/entities/feat.json"), encoding="utf-8"))
    out, cov, kinds = {}, Counter(), Counter()
    for f in feats:
        m = mechanize(f)
        # Match the exporter suffix scheme; duplicate names must not overwrite earlier source records.
        uid = f["id"]
        key = uid if uid not in out else uid + "-" + str(sum(k.startswith(uid) for k in out))
        out[key] = m
        cov[m["coverage"]] += 1
        for e in m["effects"]:
            kinds[e["type"]] += 1
    json.dump(out, open(os.path.join(root, "data/feats-mech.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lines = ["# 재주 규칙 기반 기계화 커버리지 (자동 생성)", "", f"재주 {len(feats)}개: full {cov['full']}, partial {cov['partial']}, none {cov['none']}.", "",
             "| effect 유형 | 수 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in kinds.most_common()]
    lines += ["", "## none 예 (앞 30개)", ""] + [f"- {m['name']}: {m['effect_text'][:120]}" for m in out.values() if m["coverage"] == "none" and m["effect_text"].strip()][:30]
    open(os.path.join(root, "output/feats-mech-coverage.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:4]))
    print(", ".join(f"{k} {v}" for k, v in kinds.most_common(12)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
