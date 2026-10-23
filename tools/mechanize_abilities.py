"""
특성(abilities) 680개에 기술과 같은 효과 패턴을 적용해 coverage 를 잰다.
입력: output/entities/abilities.json  출력: data/abilities-mech.json, output/abilities-mech-coverage.md
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mechanize_moves import mechanize_effect  # noqa: E402

TRIGGER_RE = re.compile(r"^(?:발동\s*조건|발동조건)\s*[:：]\s*(.+?)(?:\.|$)")
IMMUNE_RE = re.compile(r"(화상|독|마비|얼음|잠듦|혼란|헤롱헤롱|풀죽음|둔화|구속|수렁|실명|취약|상태이상|모든 상태이상)[^.]*?면역")
DMG_BONUS_RE = re.compile(r"(\S+)\s*타입\s*(?:기술|공격)[^.]*?(?:데미지|피해)(?:\s*굴림)?에\s*\+(\d+)")
WEATHER_RE = re.compile(r"(쾌청|비바라기|싸라기눈|모래바람)")


def main(src, dst, report):
    abil = json.load(open(src, encoding="utf-8"))
    out, cov, types = {}, Counter(), Counter()
    for a in abil:
        text = a["effect"] or ""
        eff, nar, c = mechanize_effect(a["name"], text)
        extra = []
        m = IMMUNE_RE.search(text)
        if m:
            extra.append({"type": "immunity", "status": m.group(1), "_src": m.group(0)})
        m = DMG_BONUS_RE.search(text)
        if m:
            extra.append({"type": "damage_bonus", "move_type": m.group(1), "value": int(m.group(2)), "_src": m.group(0)})
        # A form-gated passive bonus is independent of the ability's activation trigger.
        bonus = re.search(r"보너스:\s*(.+?폼)일 때,?\s*사용자는\s*(\S+)타입 기술에 자속 보정을 받습니다[.]", text)
        if bonus:
            extra.append({"type":"stab_grant", "form":bonus.group(1), "move_type":bonus.group(2), "_src":bonus.group(0)})
        if a.get("trigger"):
            extra.append({"type": "trigger", "text": a["trigger"]})
        eff += extra
        # 특성은 '항상' 패시브가 많아, 효과 문장을 하나라도 바꿨고 narrative 가 없으면 full
        srcs = {e.get("_src") for e in eff}
        nar = [n for n in nar if not any(n in s or s in n for s in srcs if s)]
        if not text:
            c = "none"
        elif not nar and eff:
            c = "full"
        elif eff:
            c = "partial"
        else:
            c = "none"
        cov[c] += 1
        for e in eff:
            types[e["type"]] += 1
        out[a["id"]] = {"name": a["name"], "eng": a["eng"], "confidence": "auto", "coverage": c,
                        "header": {"frequency": a.get("freq_kind"), "action": a.get("action"), "trigger": a.get("trigger"), "target": a.get("target"), "keyword": a.get("keyword")},
                        "effects": eff, "narrative": nar, "effect_text": text}
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = len(abil)
    lines = ["# 특성(abilities) 자동 기계화 커버리지", "", "| 항목 | 수 | 비율 |", "|---|---|---|", f"| 특성 수 | {n} | |",
             f"| 빈도 파싱 | {sum(1 for a in abil if a.get('freq_kind'))} | {sum(1 for a in abil if a.get('freq_kind'))/n:.0%} |",
             f"| coverage full | {cov['full']} | {cov['full']/n:.0%} |", f"| coverage partial | {cov['partial']} | {cov['partial']/n:.0%} |",
             f"| coverage none | {cov['none']} | {cov['none']/n:.0%} |", "", "## effect 유형", "", "| 유형 | 수 |", "|---|---|"]
    for k, v in types.most_common():
        lines.append(f"| {k} | {v} |")
    none = [a["name"] for a in abil if out[a["id"]]["coverage"] == "none"]
    lines += ["", f"## coverage none ({len(none)}개) 예", "", ", ".join(none[:50])]
    open(report, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
