"""GM 재정(개변) 층 테스트: 공식·mech 필드·effect 패치·상황 수정치·프롬프트 답·훅·범위 해제·파일 로드·원본 불변.
  python -X utf8 -I engine/test_rulings.py <root>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Combatant, Engine, Rules  # noqa: E402
import effects as FX  # noqa: E402
from rulings import calc  # noqa: E402


def make(r, cid, **over):
    spec = dict(r.creatures[cid])
    spec.update(over)
    return Combatant(r, spec)


def run(root):
    res = []

    def check(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    # 0. 안전한 식 계산기
    check("calc: 'max_hp / 8' (60) = 7.5", calc("max_hp / 8", {"max_hp": 60}) == 7.5)
    try:
        calc("__import__('os')", {})
        bad = False
    except ValueError:
        bad = True
    check("calc: 허용되지 않은 토큰은 거부", bad)
    # 1. 공식 치환: 소량(tick) 1/10 → 1/8
    r = Rules(root)
    e = Engine(r)
    a, t = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e.gm.add_combatant(a)
    e.gm.add_combatant(t)
    check("룰북 기본: 아치(최대 60) 소량 = 6", e.tick(a) == 6, e.tick(a))
    e.rule_formula("tick", "max_hp / 8", reason="하우스룰")
    check("공식 치환 tick='max_hp / 8' → 7 (60/8 내림)", e.tick(a) == 7, e.tick(a))
    e.rule_formula("max_hp.pokemon", "level + hp*4 + 10", reason="체력 넉넉한 캠페인")
    check("공식 치환 max_hp.pokemon → 아치 20 + 10×4 + 10 = 70 (기존 전투원도 즉시 반영)", a.max_hp == 70, a.max_hp)
    e.rule_formula("max_hp.pokemon", "level + hp*3 + 10", reason="원복")
    # 2. mech 필드 치환: 치명타 범위 20 → 18 (장면 범위)
    _, _, c20 = e.accuracy_check(a, t, r.move("move/불꽃세례"), fixed_roll=18)
    e.rule_mech("combat/critical-hit", "default_range", 18, reason="축제 결투", scope="scene")
    _, _, c18 = e.accuracy_check(a, t, r.move("move/불꽃세례"), fixed_roll=18)
    check("mech 치환 crit 18: d20=18 이 치명타가 됨 (전: 아님)", (not c20) and c18, f"{c20} {c18}")
    e.end_scene()
    _, _, c_after = e.accuracy_check(a, t, r.move("move/불꽃세례"), fixed_roll=18)
    check("장면 종료 후 장면 범위 재정 해제 → 다시 치명타 아님", not c_after)
    check("캠페인 범위 재정(tick)은 장면 종료 후에도 유지", e.tick(a) == 7)
    # 3. effect 패치: 불꽃세례에 화상(17+) 추가, 연막의 구역 제거
    e.rule_effect("move/불꽃세례", "add", {"type": "apply_status", "status": "화상", "target": "target", "on_natural_roll_min": 17}, reason="세션 합의")
    mm, conf = r.move_mech("move/불꽃세례")
    check("effect add: move_mech 결과에 화상 effect, confidence 에 +gm 표식", any(x.get("status") == "화상" for x in mm["effects_exec"]) and conf.endswith("+gm"), conf)
    FX.run_effects(e, a, t, mm["effects_exec"], {"hit": True, "nat": 18, "attacker": a, "target": t, "engine": e}, "test")
    check("패치된 effect 가 실제로 실행됨: 뚜벅초 화상", "화상" in t.conditions, t.conditions)
    mm0, _ = r.move_mech("move/연막")
    e.rule_effect("move/연막", "remove", match="zone", reason="강풍", scope="scene")
    mm1, _ = r.move_mech("move/연막")
    check("effect remove(zone): 연막의 평탄화 키 zone 이 사라짐", "zone" in mm0 and "zone" not in mm1)
    # 4. 상황 수정치: 명중 +2 (1회)
    t2 = make(r, "pokemon/oddish-2", id="pokemon/rulings-situational-target")
    e.gm.add_combatant(t2)
    need_roll = 2   # 불꽃세례 AC 2 + 뚜벅초 특수 회피 2 = 4 → d20=2 는 빗나감
    h0 = e.accuracy_check(a, t2, r.move("move/불꽃세례"), fixed_roll=need_roll)[0]
    e.rule_situational("accuracy", 2, who="아치", uses=1, reason="높은 지형")
    h1 = e.accuracy_check(a, t2, r.move("move/불꽃세례"), fixed_roll=need_roll)[0]
    h2 = e.accuracy_check(a, t2, r.move("move/불꽃세례"), fixed_roll=need_roll)[0]
    check("상황 수정치 명중 +2 (1회): 빗나감 → 명중 → (소진) 빗나감", (not h0) and h1 and (not h2), f"{h0} {h1} {h2}")
    e.rule_situational("damage", -5, who="아치", uses=1, reason="젖은 장작: 불꽃이 약하다")
    d_full = e.roll_damage(a, t2, r.move("move/몸통박치기"), set_damage=True)
    d_again = e.roll_damage(a, t2, r.move("move/몸통박치기"), set_damage=True)
    check("상황 수정치 피해 -5 (1회) 후 소진", d_full == d_again - 5, f"{d_full} {d_again}")
    # 5. 훅: 피해 확정 전 절반 / effect 실행 전 delta 조정
    e.rule_hook("before_damage", lambda v, ctx: v // 2, reason="서사: 공격이 스쳤다", scope="scene")
    d_half = e.roll_damage(a, t2, r.move("move/몸통박치기"), set_damage=True)
    check("before_damage 훅: 피해 절반", d_half == d_again // 2, f"{d_half} vs {d_again}")
    e.end_scene()

    def soften(eff, ctx):
        if eff.get("type") == "stage_change" and eff.get("delta", 0) < -1:
            return dict(eff, delta=-1)
        return eff
    e.rule_hook("before_effect", soften, reason="GM: 단계 하락은 최대 -1", scope="scene")
    FX.run_effects(e, a, t2, [{"type": "stage_change", "stat": "def", "delta": -2, "target": "target"}], {"hit": True}, "test")
    check("before_effect 훅: -2 단계 하락을 -1 로 완화", t2.stages["def"] == -1, t2.stages)
    # 6. 프롬프트 답: 스크립트 답 → 프롬프트에 answer 기록, 효과 dict 면 실행
    e.rule_answer("reveal", "대상 특성: 엽록소", reason="GM 이 공개")
    FX.run_effects(e, a, t2, [{"type": "reveal", "info": "target ability"}], {"hit": True}, "test")
    check("프롬프트 답(문자열): gm_prompts 에 answer 기록", e.gm_prompts[-1].get("answer") == "대상 특성: 엽록소", e.gm_prompts[-1])
    e.rule_answer("rule", {"note": "GM 재정: 대신 스피드 +1", "effects": [{"type": "stage_change", "stat": "spe", "delta": 1, "target": "self"}]}, reason="프롬프트를 효과로 치환")
    before = a.stages["spe"]
    FX.run_effects(e, a, t2, [{"type": "rule", "note": "escaping 구속 also escapes 수렁"}], {"hit": True}, "test")
    check("프롬프트 답(효과): rule 프롬프트에 대한 답으로 스피드 +1 실행", a.stages["spe"] == before + 1, a.stages)
    e.rulings.provider = lambda prompt: "대화형 답" if prompt.get("type") == "gm" else None
    FX.run_effects(e, a, t2, [{"type": "gm", "choice": "pick one ability if target has 2+"}], {"hit": True}, "test")
    check("제공자(대화형 GM 대역): 스크립트 답이 없으면 제공자에게 묻는다", e.gm_prompts[-1].get("answer") == "대화형 답")
    # 7. 파일 로드 + 원본 불변
    r2 = Rules(root, ruleset="core", rulings_path=os.path.join(root, "data/gm-rulings.json"))
    e2 = Engine(r2)
    a2 = make(r2, "pokemon/archie")
    check("파일 로드: data/gm-rulings.json 의 재정 6건", len([x for x in r2.rulings.log if x['kind'] != 'end_scene']) == 6, len(r2.rulings.log))
    check("파일 로드: tick 1/8 → 7, 치명타 18, 불꽃세례 화상 추가, 연막 zone 제거", e2.tick(a2) == 7 and r2.mech("combat/critical-hit")["default_range"] == 18 and any(x.get("status") == "화상" for x in r2.move_mech("move/불꽃세례")[0]["effects_exec"]) and "zone" not in r2.move_mech("move/연막")[0])
    r3 = Rules(root, ruleset="core")
    check("원본 불변: 재정 없는 새 Rules 는 룰북 그대로 (치명타 20, zone 있음, tick 6)", r3.mech("combat/critical-hit")["default_range"] == 20 and "zone" in r3.move_mech("move/연막")[0] and Engine(r3).tick(make(r3, "pokemon/archie")) == 6)
    rep = e.rulings.report()
    check("재정 보고서: 모든 개변이 이유와 함께 표로 남음", rep.count("|") > 40 and "하우스룰" in rep and "축제 결투" in rep)

    passed = sum(1 for _, ok, _ in res if ok)
    lines = ["# GM 재정(개변) 층 테스트 (자동 생성)", "", f"**{passed}/{len(res)} 통과**", "", "| # | 규칙 | 결과 | 비고 |", "|---|---|---|---|"]
    for i, (n, ok, d) in enumerate(res, 1):
        lines.append(f"| {i} | {n} | {'PASS' if ok else 'FAIL'} | {d} |")
    open(os.path.join(root, "output/rulings-tests.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return passed == len(res)


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
