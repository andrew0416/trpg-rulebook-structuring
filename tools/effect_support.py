"""DB effect 유형의 등록 여부 집계. 규칙 의미·실행 정확성 검증이 아니다.  → output/effect-support.md"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import effects_ext as EXT  # noqa: E402  (import 시 effects 테이블에 확장 핸들러를 설치)
from effects import SUPPORTED, PASSIVE_TYPES, JUDGEMENT_TYPES, ENGINE_TYPES  # noqa: E402
import items as ITEMS  # noqa: E402

TRAINER_NARRATIVE = {"rule", "gm", "craft", "limit", "cost", "tag", "restriction", "trainer_slot", "weapon", "vehicle", "z_crystal", "evolution_item", "contest_dice", "frequency_rule",
                     "skill_rank_up", "skill_mod", "skill_check", "food_buff", "item_attack", "custom_condition", "summon", "range_mod", "ac_mod", "reroll", "grant_capability", "next_roll_bonus"}


def main(root):
    rows = [json.loads(l) for l in open(os.path.join(root, "output/ruleunits.jsonl"), encoding="utf-8")]
    out = ["# 효과 유형 등록 현황 (정확성 미검증)", "", "유형 이름의 등록 여부만 집계한다. 최상위 effects만 대상으로 하며, 빈 목록도 단위 집계에 포함된다. GM 프롬프트·레지스트리 등록은 자동 실행이나 원문 정확성의 증거가 아니다. 완료 판정은 whole-rulebook-audit/completion-gate.json을 확인한다.", ""]
    for kind, label in (("entity:move", "기술"), ("entity:ability", "특성"), ("entity:feat", "재주(트레이너 계층)"), ("entity:item", "아이템"), ("entity:edge", "엣지"), ("entity:poke_edge", "포켓엣지")):
        c, sup = Counter(), Counter()
        units_all = units_ok = 0
        for u in rows:
            if u["kind"] != kind or not u.get("mech"):
                continue
            effs = [e for e in u["mech"]["data"].get("effects", []) if isinstance(e, dict) and e.get("type")]
            units_all += 1
            if all(e["type"] in SUPPORTED or (kind not in ("entity:move", "entity:ability") and (e["type"] in ITEMS.PASSIVE_ITEM_TYPES | ITEMS.CONSUMABLE_TYPES | TRAINER_NARRATIVE | {"capture_mod", "trigger"})) for e in effs):
                units_ok += 1
            for e in effs:
                c[e["type"]] += 1
                if e["type"] in SUPPORTED or (kind not in ("entity:move", "entity:ability") and e["type"] in ITEMS.PASSIVE_ITEM_TYPES | ITEMS.CONSUMABLE_TYPES | TRAINER_NARRATIVE | {"capture_mod", "trigger"}):
                    sup[e["type"]] += 1
        tot, ok = sum(c.values()), sum(sup.values())
        if not tot:
            continue
        out += [f"## {label}", "", f"- effect 레코드 {tot}개 중 등록 유형 {ok}개 ({ok/tot:.0%}); 단위 기준 {units_ok}/{units_all} ({units_ok/max(1, units_all):.0%})가 최상위 effect 유형 모두 등록", "",
                "| 유형 | 수 | 엔진 |", "|---|---|---|"]
        cat = Counter()
        rows_tbl = []
        for k, v in c.most_common():
            tag = ("GM 프롬프트" if k in EXT.PROMPT_TYPES else "레지스트리" if k in EXT.REGISTRY_TYPES else "턴 구조" if k in ENGINE_TYPES
                   else "판정 시 참조" if k in JUDGEMENT_TYPES else "패시브" if k in PASSIVE_TYPES else "실행" if k in SUPPORTED
                   else "아이템/재주 소비기" if k in ITEMS.PASSIVE_ITEM_TYPES | ITEMS.CONSUMABLE_TYPES | {"capture_mod", "trigger"} else "서술/제작(엔진 밖)" if k in TRAINER_NARRATIVE else "-")
            cat[tag] += v
            rows_tbl.append(f"| {k} | {v} | {tag} |")
        out.insert(len(out) - 2, "- 소비 방식: " + ", ".join(f"{t} {n}" for t, n in cat.most_common()))
        out += rows_tbl
        out.append("")
    out += ["등록 집합 = effects.py HANDLERS ∪ PASSIVE_TYPES ∪ JUDGEMENT_TYPES ∪ ENGINE_TYPES ∪ effects_ext 의 실행/레지스트리/GM 프롬프트 핸들러.",
            "실행: 전투 상태를 바꿈. 패시브/판정 시 참조/레지스트리: 명중·데미지·대상·이동·턴 훅이 조회. 턴 구조: use_move 가 처리(준비·연쇄·지연·다중 굴림). GM 프롬프트: 룰북이 GM 판단에 맡긴 효과를 발동 시점에 '[GM 판단]' 으로 띄우고 engine.gm_prompts 에 기록."]
    open(os.path.join(root, "output/effect-support.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    print("\n".join(out[:6]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
