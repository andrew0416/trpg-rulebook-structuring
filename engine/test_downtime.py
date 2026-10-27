"""다운타임 테스트: 경험치 표·레벨 환산, 인카운터 경험치 산정, 레벨업(스탯 포인트·기술·특성 슬롯), 진화(조건·스탯·보너스 기술), 트레이너 경험치 뱅크·이정표·새 종, 휴식·연장 휴식·포켓몬 센터, 이상한사탕.
  python -X utf8 -I engine/test_downtime.py <root>"""
import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from builder import build_pokemon, build_trainer  # noqa: E402
from engine import Combatant, Engine, Rules  # noqa: E402
import downtime as DT  # noqa: E402


def run(root):
    res = []

    def check(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    r = Rules(root)
    check("경험치 표: 레벨 2=10, 20=400, 82=12320(원문 오탈자 보정), 100=20555", DT.exp_for_level(r, 2) == 10 and DT.exp_for_level(r, 20) == 400 and DT.exp_for_level(r, 82) == 12320 and DT.exp_for_level(r, 100) == 20555)
    check("경험치 → 레벨: 399 → 19, 400 → 20, 99999 → 100", DT.level_for_exp(r, 399) == 19 and DT.level_for_exp(r, 400) == 20 and DT.level_for_exp(r, 99999) == 100)
    per, d = DT.award_exp(r, defeated=[20], players=1, significance=1, trainers_fought=[10])
    check("경험치 산정: 레벨 10 트레이너(×2) + 레벨 20 포켓몬 = 40 (룰북 예시)", d["base"] == 40 and per == 40, d)
    per2, d2 = DT.award_exp(r, defeated=[12, 14, 10], players=2, significance=3, challenge=1.0)
    check("경험치 산정: 36 × 3 ÷ 2 = 54, 중요도 5 초과 명시 허용", per2 == 54 and DT.award_exp(r, [10], 1, significance=9)[0] == 90, per2)
    # 레벨업
    spec = build_pokemon(r, "이상해씨", 5, strategy="special")
    log = DT.gain_exp(r, spec, 50)
    check("레벨업: 경험치 40+50=90 → 레벨 10, 스탯 포인트 20 = 기본 합 + 20", spec["level"] == 10 and sum(spec["stats"].values()) == sum(r.species["pokemon/이상해씨"]["base_stats"].values()) + 20, (spec["level"], spec["stats"]))
    check("레벨업: 레벨 7·9 의 레벨업 기술(씨뿌리기·덩굴채찍) 습득", r.move_id("씨뿌리기") in spec["moves"] and r.move_id("덩굴채찍") in spec["moves"], spec["moves"])
    check("레벨업: 기본 관계 유지 (특공·특방 ≥ 나머지)", spec["stats"]["spa"] >= spec["stats"]["atk"] and spec["stats"]["spd"] >= spec["stats"]["def"], spec["stats"])
    check("진화 옵션: 레벨 10 은 아직 없음", DT.evolution_options(r, spec) == [])
    # Growth must not silently drop an old move when the sourced capacity fills.
    before_growth = deepcopy(spec)
    try:
        DT.gain_exp(r, spec, 130)
    except ValueError as exc:
        assert str(exc) == "known Pokemon moves exceed sourced capacity; explicit forgotten-move choice required"
    else:
        raise AssertionError("over-capacity growth must require an explicit forgotten move")
    assert spec == before_growth
    growth_engine = Engine(r, 1)
    growing = Combatant(r, spec)
    growth_engine.gm.add_combatant(growing)
    growth_engine.gm.set_move(growing, "move/울음소리", add=False,
                              reason="downtime fixture chooses Growl as the forgotten move before growth")
    spec = growing.spec
    DT.gain_exp(r, spec, 130)
    opts = DT.evolution_options(r, spec)
    check("진화 옵션: 레벨 15 → 이상해풀 (15이상)", spec["level"] == 15 and opts == [("이상해풀", 15)], (spec["level"], opts))
    # Choose the birth ability explicitly; level 20 offers, but does not choose,
    # the second ability from the actual basic/hidden learnset pools.
    spec20 = build_pokemon(r, "이상해씨", 19, strategy="special", abilities=["심록"])
    log20 = DT.level_up(r, spec20)
    growing20 = Combatant(r, spec20)
    growth_engine.gm.add_combatant(growing20)
    growth_engine.choose_growth_ability(growing20, 20, "자신감",
                                        reason="downtime fixture selects its offered hidden ability at level 20")
    spec20 = growing20.spec
    check("레벨 20 특성 슬롯: 두 번째 특성 획득 (기본/숨겨진 풀)", len(spec20["abilities"]) == 2 and any("특성 슬롯" in l for l in log20), spec20["abilities"])
    # 진화
    old_stats = dict(spec["stats"])
    ok = DT.evolve(r, spec, "이상해풀")
    check("진화: 종·타입·스탯 재분배(포인트 25 유지)", ok and spec["species"] == "pokemon/이상해풀" and sum(spec["stats"].values()) == sum(r.species["pokemon/이상해풀"]["base_stats"].values()) + 25, (spec["species"], spec["stats"]))
    check("진화: 남은 진화 단계 2 → 1", spec["evolutions_remaining"] == 1)
    check("진화 거부: 다음 단계가 아닌 종(이상해꽃)은 불가", not DT.evolve(r, build_pokemon(r, "이상해씨", 30), "이상해꽃"))
    # 트레이너
    tr = {"name": "실바나", "level": 5}
    DT.trainer_new_species(r, tr, "이상해씨"); DT.trainer_new_species(r, tr, "이상해씨")
    check("트레이너: 처음 보는 종 +1, 같은 종 두 번째는 0", tr["exp_bank"] == 1)
    DT.trainer_gain_exp(r, tr, 19)
    check("트레이너: 뱅크 20 → 레벨 +2, 뱅크 0", tr["level"] == 7 and tr["exp_bank"] == 0, tr)
    DT.trainer_milestone(r, tr)
    check("트레이너: 이정표는 뱅크 무관 +1", tr["level"] == 8 and tr["exp_bank"] == 0)
    # 휴식
    e = Engine(r, 1)
    c = Combatant(r, build_pokemon(r, "뚜벅쵸", 13))
    e.gm.add_combatant(c)
    c.hp = 10
    got = DT.rest(e, c, 60)
    check("휴식 60분: 30분마다 최대 체력 1/16 → 2블록", got == 2 * int(c.max_hp / 16), (got, c.max_hp))
    c.injuries = 5
    check("부상 5 이상이면 휴식 회복 불가", DT.rest(e, c, 60) == 0)
    c.injuries = 1
    c.spec["rested_minutes_today"] = 8 * 60
    check("하루 8시간 넘으면 회복 없음", DT.rest(e, c, 60) == 0)
    c.conditions.add("독"); c.conditions.add("혼란")
    DT.extended_rest(e, c, 24)
    check("연장 휴식 24h: 지속 상태(독) 제거, 휘발성(혼란)은 유지, 부상 1 자연 치유", "독" not in c.conditions and "혼란" in c.conditions and c.injuries == 0, c.conditions)
    c.hp = 1; c.injuries = 4; c.conditions.add("독")
    DT.pokemon_center(e, c)
    check("포켓몬 센터: 자연치유1개와 공유하는 하루3개한도, 센터에서는2개", c.hp == c.max_hp and not c.conditions and c.injuries == 2, c.injuries)
    # 이상한사탕 (전투 중 경험치)
    e2 = Engine(r, 1)
    trn = Combatant(r, build_trainer(r, "실바나", 5, {"hp": 10, "atk": 5, "def": 5, "spa": 5, "spd": 5, "spe": 5}, items={"이상한사탕": 1}))
    pc = Combatant(r, build_pokemon(r, "뚜벅쵸", 13))
    e2.gm.add_combatant(trn)
    e2.gm.add_combatant(pc)
    e2.use_item(trn, "이상한사탕", pc)
    check("이상한사탕: 다음 레벨까지 경험치 → 레벨 14, 전투원 스탯 갱신", pc.level == 14 and sum(pc.stats.values()) == sum(r.species["pokemon/뚜벅쵸"]["base_stats"].values()) + 24, (pc.level, pc.stats))
    lines = ["# 다운타임 테스트 (자동 생성)", "", f"{sum(1 for _, ok, _ in res if ok)}/{len(res)} 통과", "", "| # | 검사 | 결과 | 비고 |", "|---|---|---|---|"]
    for i, (name, ok, detail) in enumerate(res, 1):
        lines.append(f"| {i} | {name} | {'PASS' if ok else 'FAIL'} | {str(detail)[:100]} |")
    open(os.path.join(root, "output/downtime-tests.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return all(ok for _, ok, _ in res)


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
