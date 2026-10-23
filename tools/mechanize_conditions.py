"""
PTK 상태이상(Status Afflictions) 22개를 패턴 매칭으로 자동 기계화한다 (B층 실험, SRD의 mechanize_conditions.py 대응).

입력: output/entities/condition.json  (ptk_structure.py entities 가 뽑은 한 줄 정의 + 이어지는 줄)
출력: data/conditions.json            (RuleUnit 형식: text + mech{coverage, effects, narrative})

SRD는 상태 하나가 `_소항목._` 여러 개로 쪼개져 있었지만, PTK는 상태 하나가 문단 하나라서
문장 단위로 쪼개서 패턴을 건다. 매핑 안 된 문장은 narrative 로 남긴다.
"""
import json
import os
import re
import sys

SENT_SPLIT = re.compile(r"(?<=[.。])\s+|\n+")
STAT_KO = {"방어": "def", "특수방어": "spd", "공격": "atk", "특수공격": "spa", "스피드": "spe"}
TYPES = "노말|격투|비행|독|땅|바위|벌레|고스트|강철|불꽃|물|풀|전기|에스퍼|얼음|드래곤|악|페어리"

def save_effect(match):
    # The optional timing group can be skipped when the sentence starts with
    # e.g. "대상의". Inspect the full matched sentence, not that optional group.
    timing = "start_of_turn" if re.search(r"턴이\s*시작될\s*때", match.string) else "end_of_turn"
    return {"type": "save", "dc": int(match.group(2) or match.group(3)),
            "timing": timing, "on_success": "cure"}


PATTERNS = [
    # (id, regex, builder)  — builder(m) -> effect dict
    ("stage_down", re.compile(r"(방어|특수방어|공격|특수공격|스피드)\s*(?:스탯|값)?(?:은|는|이|가)?[^.]*?(\d+)\s*전투단계만큼\s*낮아"),
     lambda m: {"type": "combat_stage", "stat": STAT_KO[m.group(1)], "delta": -int(m.group(2)), "while": "afflicted"}),
    ("immune_types", re.compile(rf"((?:{TYPES})(?:\s*(?:과|와|,|및)\s*(?:{TYPES}))*)\s*타입(?:의)?\s*포켓몬은[^.]*?면역"),
     lambda m: {"type": "immunity", "types": re.findall(TYPES, m.group(1))}),
    ("tick_on_standard", re.compile(r"기본 행동을 취하거나[^.]*?해당 턴이 끝나면 소량의 체력을 손실"),
     lambda m: {"type": "tick_damage", "ticks": 1, "when": "end_of_turn", "if": "took_standard_action_or_unable_to"}),
    ("badly_poisoned", re.compile(r"맹독[^.]*?(\d+)의 체력을 잃[^.]*?두 배"),
     lambda m: {"type": "hp_loss_escalating", "variant": "맹독", "start": int(m.group(1)), "growth": "x2_per_round"}),
    ("two_ticks_on_standard", re.compile(r"기본 행동을 취하면, 그 턴이 끝날 때 둘의 소량의 체력"),
     lambda m: {"type": "tick_damage", "ticks": 2, "when": "end_of_turn", "if": "took_standard_action"}),
    ("two_ticks_on_save", re.compile(r"잠듦으로 인해 내성 체크를 수행 할 때마다 두 번의 소량의 체력"),
     lambda m: {"type": "tick_damage", "ticks": 2, "when": "on_sleep_save"}),
    ("no_actions", re.compile(r"자신의 턴에 행동하지 못하|행동을 취할 수 없습니다|행동, 특성 또는 재주를 사용할 수 없"),
     lambda m: {"type": "no_actions"}),
    ("evasion_disabled", re.compile(r"회피 보너스를 받지 않|어떤 종류의 회피도 적용 할 수 없"),
     lambda m: {"type": "evasion_disabled"}),
    ("speed_evasion_disabled", re.compile(r"속도 회피를 적용 할 수 없"),
     lambda m: {"type": "evasion_disabled", "only": "speed"}),
    ("save", re.compile(r"(턴이 시작될 때|턴이 끝날 때마다|턴이 끝날 때|턴이 끝나고)?[^.]*?(?:DC\s*(\d+)|(\d+)\+의?)\s*내성\s*체크"),
     save_effect),
    ("save_type_dc", re.compile(rf"DC는 ({TYPES})타입 포켓몬의 경우 (\d+)로"),
     lambda m: {"type": "save_modifier", "if_type": m.group(1), "dc": int(m.group(2))}),
    ("save_weather", re.compile(r"쾌청 때는 \+(\d+) 보너스를, 싸라기눈 때는 -(\d+) 페널티"),
     lambda m: {"type": "save_modifier", "weather": {"쾌청": int(m.group(1)), "싸라기눈": -int(m.group(2))}}),
    ("cure_on_hit_types", re.compile(rf"((?:{TYPES})(?:, (?:{TYPES}))*) 공격을 받으면[^.]*?치료"),
     lambda m: {"type": "cured_by_damage_of_types", "types": re.findall(TYPES, m.group(1))}),
    ("wake_on_damage", re.compile(r"데미지를 입거나 공격으로부터 생명력을 잃을 때마다, 그들은 깨어"),
     lambda m: {"type": "cured_by_damage", "excluding": "passive_hp_loss"}),
    ("initiative_half", re.compile(r"이니셔티브는 절반"),
     lambda m: {"type": "initiative", "multiplier": 0.5}),
    ("initiative_set", re.compile(r"이니셔티브를[^.]*?(\d+)까지 낮추"),
     lambda m: {"type": "initiative", "set_to": int(m.group(1)), "until": "cured"}),
    ("vulnerable_rounds", re.compile(r"(\d+)라운드 동안 취약상태"),
     lambda m: {"type": "apply_condition", "condition": "취약", "rounds": int(m.group(1))}),
    ("accuracy_penalty", re.compile(r"명중\s*(?:굴림|률)에 -(\d+)의 (?:총 )?페널티"),
     lambda m: {"type": "accuracy_mod", "value": -int(m.group(1))}),
    ("damage_roll_penalty", re.compile(r"데미지 롤에 대해 -(\d+) 패널티"),
     lambda m: {"type": "damage_roll_mod", "value": -int(m.group(1)), "unless": "target_is_infatuation_source"}),
    ("movement_half", re.compile(r"이동이 절반으로 감소합니다 \(최소 (\d+)\)"),
     lambda m: {"type": "movement", "multiplier": 0.5, "min": int(m.group(1))}),
    ("no_shift_move", re.compile(r"'이동 행동'으로 이동을 할 수 없"),
     lambda m: {"type": "no_shift_movement"}),
    ("no_recall", re.compile(r"복귀할 수 없"),
     lambda m: {"type": "no_recall"}),
    ("must_stand", re.compile(r"'이동 행동'으로 먼저 일어나야"),
     lambda m: {"type": "must_stand_up", "cost": "shift_action"}),
    ("freq_lock", re.compile(r"“임의” 이외의 빈도를 가진 기술을 사용할 수 없"),
     lambda m: {"type": "move_frequency_lock", "allowed": ["임의"]}),
    ("fixed_duration", re.compile(r"항상 (\d+)라운드 동안 지속"),
     lambda m: {"type": "duration", "rounds": int(m.group(1))}),
    ("cured_by_switch_or_rest", re.compile(r"교대하거나 연장 동작으로 장면 끝에서 제거"),
     lambda m: {"type": "cured_by", "any_of": ["switch_out", "extended_action_end_of_scene"]}),
    ("no_aoo", re.compile(r"기회공격을 할 수 없"),
     lambda m: {"type": "no_attack_of_opportunity"}),
    ("confusion_roll", re.compile(r"1d2를 굴리"),
     lambda m: {"type": "on_attack_roll", "die": "1d2", "fail_on": 1}),
    ("confusion_self_hit", re.compile(r"물리면 공격 스탯의 절반[^.]*?특수면 특수공격의 절반[^.]*?변화기라면 소량의 체력을 2번"),
     lambda m: {"type": "self_hp_loss", "by_move_class": {"물리": "atk/2", "특수": "spa/2", "변화": "2 ticks"}, "after": "attack_resolves"}),
    ("action_limit_on_fail", re.compile(r"기본행동 또는 이동행동 중 하나만"),
     lambda m: {"type": "action_limit", "choose_one_of": ["standard", "shift"], "if": "save_failed"}),
    ("must_attack", re.compile(r"데미지를 입히는 물리, 특수 기술 또는 발버둥을 사용해야만"),
     lambda m: {"type": "forced_action", "must": "damaging_move_or_struggle"}),
    ("move_locked", re.compile(r"특정 기술이 지정됩니다[^.]*"),
     lambda m: {"type": "move_lock", "param": "move_id", "stackable": True}),
    ("fainted_trigger", re.compile(r"체력이 0 이하인 포켓몬 또는 트레이너는 실신하거나 기절"),
     lambda m: {"type": "trigger", "when": "hp<=0"}),
    ("implies_vulnerable", re.compile(r"(실명, 잠듦, 기절, 얼음, 넘어진) 상태의 대상의 경우 항상 취약"),
     lambda m: {"type": "implied_by", "conditions": ["실명", "잠듦", "기절", "얼음", "넘어짐"]}),
    ("stacking", re.compile(r"중첩으로 쌓일 수 있"),
     lambda m: {"type": "stackable"}),
    ("cured_with_sleep", re.compile(r"잠듦이 치료되면 악몽도 치료"),
     lambda m: {"type": "cured_by", "any_of": ["cure:잠듦"]}),
    ("temp_hp_loss", re.compile(r"몬스터볼에 돌아오면 상실되며, 전투 중 (\d+)분 후에 스스로 사라"),
     lambda m: {"type": "temp_hp_rules", "lost_on": ["recall", f"{m.group(1)}min"]}),
    ("blind_terrain_check", re.compile(r"DC를 (\d+)으로하여 곡예 체크"),
     lambda m: {"type": "skill_check", "skill": "곡예", "dc": int(m.group(1)), "when": "moving_through_rough_or_slow_terrain"}),
    ("no_priority", re.compile(r"우선이 있는 기술이나 가로채기를 사용할 수 없"),
     lambda m: {"type": "forbid", "actions": ["priority_moves", "intercept"]}),
    ("requires_condition", re.compile(r"잠든 목표에만 영향"),
     lambda m: {"type": "requires", "condition": "잠듦"}),
    ("multi_instance", re.compile(r"여러 개의 사슬묶기 상태를 가질 수"),
     lambda m: {"type": "stackable", "distinct_param": True}),
    ("move_lock_effect", re.compile(r"해당 기술을 사용할 수 없"),
     lambda m: {"type": "forbid", "actions": ["locked_move"]}),
]
# 매핑 못 해도 '규칙이 아닌 설명' 또는 앞 문장의 패턴에 이미 포함된 문장 (narrative 로 세지 않음)
FLUFF = re.compile(r"^(실명은 대상의 시야가|실명은 여러 가지 효과로|완전 실명은 단순히|완전히 어두운 동굴|이 양은 매 라운드마다|\(또한, 이제|여기에는 독 또는 화상|일부 효과는 임시 체력을 부여"
                   r"|성공하면 .*치료됩니다|내성 체크에 성공했으면|1이 나왔다면|완전 실명에는 실명과 같은)")


def mechanize(cond):
    # 번역본은 문장 중간에 줄바꿈이 있다. '- ' 소항목 줄만 별도 문장으로 두고 나머지 줄바꿈은 공백으로 잇는다.
    text = re.sub(r"\n(?!- )", " ", cond["text"])
    sents = [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]
    effects, narrative, mapped = [], [], 0
    for sentence_index, s in enumerate(sents):
        hit = False
        for pid, rx, build in PATTERNS:
            m = rx.search(s)
            if m:
                eff = build(m)
                # ch07:584: a successful paralysis save permits normal acting;
                # it does not cure the persistent condition. Keep the following
                # success clause as evidence instead of dropping it as fluff.
                if pid == "save" and sentence_index + 1 < len(sents):
                    success = sents[sentence_index + 1]
                    if re.match(r"내성\s*체크에\s*성공했으면\s*사용자는\s*정상적으로\s*행동할\s*수\s*있", success):
                        eff["on_success"] = "act_normally"
                        eff["_success_src"] = success
                eff["_pattern"] = pid
                eff["_src"] = s
                effects.append(eff)
                hit = True
        if hit:
            mapped += 1
        elif FLUFF.match(s):
            mapped += 1
        else:
            narrative.append(s)
    section = cond["section"].split(" / ")[-1]
    cls = "persistent" if "지속적" in section else "volatile" if "휘발성" in section else "other"
    if cond["name"] == "임시 체력":cls = "resource"  # ch07:619: not removed by status cures
    coverage = "full" if not narrative else ("partial" if effects else "none")
    return {
        "id": "condition/" + cond["name"].replace(" ", "-"),
        "kind": "definition:condition",
        "source": {"doc": "PTK 코어 룰북 (PTU 1.05 한국어 번역)", "chapter": cond["chapter"], "section": cond["section"], "line": cond["line"]},
        "text": {"summary": sents[0] if sents else "", "body": cond["text"]},
        "mech": {"schema": "condition", "confidence": "auto", "coverage": coverage,
                 "data": {"name": cond["name"], "eng": cond["eng"], "class": cls, "effects": effects, "narrative": narrative}},
        "_stats": {"sentences": len(sents), "mapped": mapped},
    }


def main(src, dst):
    conds = json.load(open(src, encoding="utf-8"))
    out = [mechanize(c) for c in conds]
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tot_s = sum(o["_stats"]["sentences"] for o in out)
    tot_m = sum(o["_stats"]["mapped"] for o in out)
    cov = {k: sum(1 for o in out if o["mech"]["coverage"] == k) for k in ("full", "partial", "none")}
    print(f"조건 {len(out)}개, 문장 {tot_s}개 중 {tot_m}개 매핑, 효과 레코드 {sum(len(o['mech']['data']['effects']) for o in out)}개, 패턴 {len(PATTERNS)}개")
    print("커버리지:", cov)
    for o in out:
        d = o["mech"]["data"]
        print(f"- {d['name']}({d['eng']}) [{d['class']}] {o['mech']['coverage']}: " + ", ".join(e["_pattern"] for e in d["effects"]) +
              (("  | 미매핑: " + " / ".join(n[:40] for n in d["narrative"])) if d["narrative"] else ""))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
