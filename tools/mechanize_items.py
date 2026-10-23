"""
아이템 규칙 기반 기계화 → data/items-mech.json, output/items-mech-coverage.md
시트 아이템(items_sheet.json 677) + ch09 블록(item.json) 을 분류별 패턴으로:
  약: 체력 N 회복 / 상태 해소 / 부상 치유 / 소생     음식: 회피·전투단계·임시 체력·버프·포핀 재료(등급)     몬스터볼: 포획 보정(mod) + 조건
  포켓몬 도구: 타입별 피해감소 N / 다음 타입 기술 DB +N(주얼) / 자속 DB +1 / 메가스톤 / 진화의 돌 / 트레이너 슬롯     장비품: 슬롯 + 스킬·회피·피해감소 보너스
  python -X utf8 -I tools/mechanize_items.py <root>
"""
import json
import os
import re
import sys
from collections import Counter

TYPES = "(노말|격투|비행|독|땅|바위|벌레|고스트|강철|불꽃|물|풀|전기|에스퍼|얼음|드래곤|악|페어리)"
STAT = r"(공격|방어|특수공격|특공|특수방어|특방|스피드|명중|회피|HP|체력)"
STAT_KO = {"공격": "atk", "방어": "def", "특수공격": "spa", "특공": "spa", "특수방어": "spd", "특방": "spd", "스피드": "spe", "명중": "acc", "회피": "eva", "HP": "hp", "체력": "hp"}
STATUS = r"(화상|얼음|마비|독|맹독|잠듦|혼란|풀죽음|둔화|구속|수렁|넘어짐|취약|억압|난동|헤롱헤롱|저주|사슬묶기|조이기|실명)"


def mech_item(it):
    name, cat, desc = it["name"], it.get("category") or "", (it.get("desc") or it.get("effect") or it.get("text") or "")
    effects = []
    header = {"category": cat, "price": it.get("price_num"), "slot": it.get("slot"), "mod": it.get("mod")}
    use = "held"
    if cat == "약":
        use = "consumable"
        if m := re.search(r"체력(?:을|를)?\s*(\d+)\s*회복", desc):
            effects.append({"type": "heal", "amount": int(m.group(1)), "target": "target"})
        if re.search(r"모든 상태이상(?:을|를)?\s*(?:해소|치료|회복)", desc):
            effects.append({"type": "cure_all_status", "target": "target"})
        for m in re.finditer(STATUS + r"(?:을|를|상태를)?\s*(?:해소|치료|회복)", desc):
            effects.append({"type": "cure_status", "status": m.group(1), "target": "target"})
        if m := re.search(r"부상(?:을|를)?\s*(\d+)?\s*(?:개\s*)?(?:치유|치료|제거)", desc):
            effects.append({"type": "heal_injury", "value": int(m.group(1) or 1), "target": "target"})
        if re.search(r"기절(?:한|에서)?.*?(?:회복|소생|깨어)", desc) or "소생" in desc:
            effects.append({"type": "revive", "target": "target", "hp": "half" if "절반" in desc else "full" if "전부" in desc or "모두" in desc else "some"})
        if re.search(r"최대 체력(?:까지|만큼)?\s*(?:전부\s*)?회복|체력을 전부", desc):
            effects.append({"type": "heal", "fraction_of_max": [1, 1], "target": "target"})
        for m in re.finditer(r"상태이상\s*[“\"']?" + STATUS + r"[”\"']?(?:을|를)?\s*해소", desc):
            effects.append({"type": "cure_status", "status": m.group(1), "target": "target"})
    elif cat == "음식":
        use = "consumable"
        if m := re.search(r"(?:회피|회피 효과)(?:를|에)?\s*\+(\d+)|\+(\d+)의? 회피", desc):
            effects.append({"type": "evasion_mod", "value": int(m.group(1) or m.group(2)), "target": "self", "duration": "다음 턴 끝까지" if "다음 턴" in desc else None})
        for m in re.finditer(STAT + r"\s*(?:스탯)?(?:의|을|를)?\s*(?:전투단계|CS)?(?:를|가)?\s*\+(\d+)", desc):
            effects.append({"type": "stage_change", "stat": STAT_KO[m.group(1)], "delta": int(m.group(2)), "target": "self"})
        if m := re.search(r"체력(?:을|를)?\s*(\d+)\s*회복", desc):
            effects.append({"type": "heal", "amount": int(m.group(1)), "target": "self"})
        if re.search(r"소량의\s*임시\s*체력", desc):
            effects.append({"type": "temp_hp", "value": "tick", "target": "self"})
        if m := re.search(r"([가-힣]+)\s*포핀\s*재료.*?등급\s*(\d+)", desc):
            effects.append({"type": "ingredient", "dish": m.group(1) + " 포핀", "grade": int(m.group(2))})
        if "만복" in desc or "음식버프" in desc or "음식 버프" in desc:
            effects.append({"type": "food_buff", "note": desc[:80]})
        if m := re.search(STAT + r"\s*스탯(?:을|를)?\s*(\d+)\s*(?:낮|내)", desc):
            effects.append({"type": "stat_base_mod", "stat": STAT_KO[m.group(1)], "value": -int(m.group(2)), "note": "영양제 역(트레이너 허가)"})
    elif cat == "몬스터볼":
        use = "ball"
        mod = it.get("mod")
        try:
            mod_v = int(str(mod).replace("+", "")) if mod not in (None, "") else 0
        except ValueError:
            mod_v = 0
        effects.append({"type": "capture_mod", "value": mod_v, "condition": desc[:100] if re.search(r"경우|때|조건|이면", desc) else None})
    elif cat in ("포켓몬 도구", "소지 도구"):
        if m := re.search(STAT + r"\s*스탯\s*기본\s*단계가\s*\+(\d+)단계가\s*되지만,?\s*억압", desc):
            effects.append({"type": "stage_change", "stat": STAT_KO[m.group(1)], "delta": int(m.group(2)), "target": "self", "base": True})
            effects.append({"type": "apply_status", "status": "억압", "target": "self", "duration": "scene", "uncurable": True})
            effects[0]["if"] = "can receive 억압"
        if re.search(r"흡수하는 기술로 회복하는 체력이 2배", desc):
            effects.append({"type": "rule", "drain_heal_multiplier": 2})
        if m := re.search(r"([가-힣]+)\s*재능을\s*(?:부여|얻)", desc):
            effects.append({"type": "grant_capability", "capability": m.group(1)})
        if m := re.search(TYPES + r"타입\s*(?:기술|공격)에\s*대해\s*피해\s*감소\s*(\d+)", desc):
            effects.append({"type": "damage_reduction", "value": int(m.group(2)), "vs_type": m.group(1), "target": "self"})
        if m := re.search(TYPES + r"타입\s*(?:한\s*)?기술의\s*기본\s*피해량\s*\+(\d+)", desc):
            effects.append({"type": "next_attack_modifier", "damage_base_mod": int(m.group(2)), "move_type": m.group(1), "consume": "free action"})
        if (m := re.search(TYPES + r"\s*타입\s*기술(?:의|에)?\s*(?:기본\s*)?(?:피해|데미지)(?:량)?\s*\+(\d+)", desc)) and not any(e["type"] == "next_attack_modifier" for e in effects):
            effects.append({"type": "damage_base_mod", "value": int(m.group(2)), "move_type": m.group(1)})
        if m := re.search(r"메가링과 함께 사용하면\s*([가-힣]+)(?:을|를)\s*메가진화", desc):
            effects.append({"type": "mega_stone", "species": m.group(1)})
        if m := re.search(r"([가-힣, ]+?)(?:을|를)\s*진화시킬\s*수\s*있는\s*돌", desc):
            effects.append({"type": "evolution_item", "species": [x.strip() for x in m.group(1).split(",")]})
        if m := re.search(r"자속.*?(?:기본\s*)?(?:피해|데미지)(?:량)?\s*\+(\d+)", desc):
            effects.append({"type": "damage_base_mod", "value": int(m.group(1)), "moves": "STAB"})
        if (m := re.search(r"피해\s*감소\s*(\d+)", desc)) and not effects:
            effect = {"type": "damage_reduction", "value": int(m.group(1)), "target": "self"}
            if "특정 타입" in desc or "해당하는 타입" in desc:
                effect["vs_type"] = "chosen"
            effects.append(effect)
        for m in re.finditer(STAT + r"\s*(?:스탯)?(?:에|이|가)?\s*\+(\d+)", desc):
            effects.append({"type": "stat_base_mod", "stat": STAT_KO[m.group(1)], "value": int(m.group(2))})
        if m := re.search(r"트레이너 장착시\s*([가-힣 ]+?)(?:\s|$|\.)", desc):
            header["trainer_slot"] = m.group(1).strip()
    elif cat == "장비품":
        use = "equipment"
        if m := re.search(r"(물리|특수|모든)\s*피해에\s*대해\s*\+(\d+)\s*피해\s*감소", desc):
            effects.append({"type": "damage_reduction", "value": int(m.group(2)), "vs": {"물리": "physical", "특수": "special", "모든": None}[m.group(1)], "target": "self"})
        if m := re.search(r"([가-힣]+)\s*재능을\s*부여", desc):
            effects.append({"type": "grant_capability", "capability": m.group(1)})
        for m in re.finditer(r"(곡예|육상|전투|협박|매력|명령|교활|집중|직감|은신|지각|생존|일반 ?지식|의학|오컬트학|포켓몬학|기술학|교육학)(?:\s*(?:체크|굴림))?(?:에|의)?\s*\+(\d+)", desc):
            effects.append({"type": "skill_mod", "skill": m.group(1).replace(" ", ""), "value": int(m.group(2))})
        if (m := re.search(r"(?:매력|교활|협박|곡예|육상|전투|집중|직감|은신|지각|생존)[가-힣, ]*?굴림에\s*\+(\d+)", desc)) and not effects:
            effects.append({"type": "skill_mod", "skill": "listed", "value": int(m.group(1))})
        if m := re.search(r"\+(\d+)\s*회피", desc):
            effects.append({"type": "evasion_mod", "value": int(m.group(1)), "target": "self"})
        if m := re.search(r"피해\s*감소\s*(\d+)", desc):
            effects.append({"type": "damage_reduction", "value": int(m.group(1)), "target": "self"})
        if m := re.search(r"(?:근접|소형|대형|단거리|원거리|사격)\s*(?:근접)?\s*무기", desc):
            header["weapon_kind"] = m.group(0)
    elif cat == "증강(사이버네틱)":
        use = "augment"
        for m in re.finditer(STAT + r"\s*(?:스탯)?(?:에|이|가)?\s*\+(\d+)", desc):
            effects.append({"type": "stat_base_mod", "stat": STAT_KO[m.group(1)], "value": int(m.group(2))})
    else:
        use = "misc"
    header["use"] = use
    cov = "none" if not effects else "full" if (cat in ("몬스터볼",) or len(desc) < 60) else "partial"
    if cat in ("중요한 도구",) and not effects:
        cov = "n/a"
    if any(e.get("vs_type") == "chosen" for e in effects):
        cov = "partial"
    return {"name": name, "confidence": "auto", "coverage": cov, "header": header, "effects": effects, "narrative": [desc] if cov in ("partial", "none") else [], "desc": desc}


def main(root):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from item_records import sheet_items
    items = sheet_items(root)
    out, cov, kinds, bycat = {}, Counter(), Counter(), {}
    for it in items:
        m = mech_item(it)
        out[it["id"]] = m
        cov[m["coverage"]] += 1
        bycat.setdefault(it.get("category"), Counter())[m["coverage"]] += 1
        for e in m["effects"]:
            kinds[e["type"]] += 1
    json.dump(out, open(os.path.join(root, "data/items-mech.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lines = ["# 아이템 규칙 기반 기계화 커버리지 (자동 생성)", "", f"시트 아이템 {len(items)}개: " + ", ".join(f"{k} {v}" for k, v in cov.most_common()), "",
             "| 분류 | full | partial | none | n/a |", "|---|---|---|---|---|"]
    for cat, c in bycat.items():
        lines.append(f"| {cat} | {c['full']} | {c['partial']} | {c['none']} | {c['n/a']} |")
    lines += ["", "| effect 유형 | 수 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in kinds.most_common()]
    lines += ["", "## none 예 (앞 30개)", ""] + [f"- {m['name']} ({m['header']['category']}): {m['desc'][:120]}" for m in out.values() if m["coverage"] == "none"][:30]
    open(os.path.join(root, "output/items-mech-coverage.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
