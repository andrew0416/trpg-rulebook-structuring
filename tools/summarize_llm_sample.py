"""data/moves-llm-sample.json (LLM 보조 구조화 샘플) 통계 -> output/moves-llm-sample.md"""
import json
import os
import sys
from collections import Counter


def main(root):
    d = json.load(open(os.path.join(root, "data/moves-llm-sample.json"), encoding="utf-8"))
    items = d["items"]
    cat = Counter()
    new_types = Counter()
    for it in items:
        v = it["vocab"]
        if v == "existing":
            cat["existing (기존 어휘, 패턴 보강으로 자동화 가능)"] += 1
        elif v.startswith("existing+"):
            cat["existing + 조건/새 스키마 일부"] += 1
        elif v == "gm":
            cat["gm (플레이어/GM 선택 필요)"] += 1
        else:
            cat["new (새 effect 스키마 필요)"] += 1
        for part in v.split("+"):
            if part.startswith("new:"):
                new_types[part[4:]] += 1
    lines = ["# LLM 보조 구조화 샘플 (coverage none 50개, seed %d)" % d["sample_seed"], "",
             "규칙 기반 기계화가 전부 narrative 로 남긴 기술 50개를 LLM 이 읽고 mech 초안을 작성한 결과. 검수 전(confidence=llm).", "",
             "| 분류 | 수 |", "|---|---|"]
    for k, v in cat.most_common():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## 필요한 새 effect 스키마 (빈도순)", "", "| 스키마 | 수 | 뜻 |", "|---|---|---|"]
    desc = {"swap_stages": "전투단계 교환", "swap_stats": "스탯/이니셔티브 교환", "field_effect": "N라운드 전장 효과(원더룸·매직룸)", "reaction_shield": "방해/반응으로 명중 무효",
            "grant_ability": "특성 부여", "ability_change": "특성 변경", "type_effectiveness_override": "상성 계산 예외", "type_change": "타입 변경",
            "set_up_move": "2턴 준비 기술", "movement_rule": "공격 전후 이동/지형 무시", "forced_movement": "강제 이동/복귀", "forced_target": "도발",
            "damage_formula_override": "데미지 공식 치환", "create_terrain": "지형 생성", "next_attack_modifier": "다음 공격 수정", "bind": "길동무",
            "custom_condition": "고유 상태이상 정의", "ignore_effects": "특정 반응/특성 무시", "reaction_reflect": "반사", "self_hp_set": "자신 체력 설정(자폭)",
            "destroy_hazards": "함정 제거", "condition_param": "상태이상 매개변수", "multi_target_chain": "연쇄 다중 대상", "targeting_rule": "대상 제한",
            "damage_floor": "체력 1 미만 불가", "random_move": "무작위 기술", "random_db": "무작위 DB", "conditional_area_status": "조건부 광역 상태",
            "grounding": "지상 강제"}
    for k, v in new_types.most_common():
        lines.append(f"| {k} | {v} | {desc.get(k, '')} |")
    lines += ["", f"새 스키마 종류 {len(new_types)}개로 {sum(new_types.values())}건을 덮는다. 상위 6개(swap, field_effect, reaction_shield, grant/ability_change, type override, movement_rule)가 절반 이상."]
    open(os.path.join(root, "output/moves-llm-sample.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
