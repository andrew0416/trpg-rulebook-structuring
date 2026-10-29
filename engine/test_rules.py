"""
규칙별 단위 테스트: 엔진이 data/*.json 의 mech 를 PTK 원문대로 해석하는지 확인.
원문에 예시 수치가 있는 규칙은 그 예시(챕터 5 포획률 예시 3건, 챕터 7 본문 예시, 챕터 7 전투 데모의 계산)를 그대로 쓴다.

  python -X utf8 -I engine/test_rules.py <experiment_root>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Combatant, Engine, Rules  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from synthetic_rule_fixture import register_synthetic  # noqa: E402


class FixedRng:
    def __init__(self, seq):
        self.seq = list(seq)

    def randint(self, a, b):
        v = self.seq.pop(0)
        assert a <= v <= b, f"fixed value {v} out of [{a},{b}]"
        return v


def make(rules, cid, **over):
    spec = dict(rules.creatures[cid])
    spec.update(over)
    return Combatant(rules, spec)


def run(root):
    r = Rules(root)
    # Component fixtures have no rulebook authority; register only their test identities.
    register_synthetic(r, "x", name="x", kind="entity:move")
    register_synthetic(r, "move/x", name="x", kind="entity:move")
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    # 1. 체력 공식 — 데모: 아치 60, 뚜벅초 53
    archie, odd, silv = make(r, "pokemon/archie"), make(r, "pokemon/oddish-1"), make(r, "trainer/silvana")
    check("체력 공식(포켓몬) 아치 = 20 + 10×3 + 10 = 60", archie.max_hp == 60, f"{archie.max_hp}")
    check("체력 공식(포켓몬) 뚜벅초 = 13 + 10×3 + 10 = 53", odd.max_hp == 53, f"{odd.max_hp}")
    check("체력 공식(트레이너) 실바나 = 4×2 + 5×3 + 10 = 33", silv.max_hp == 33, f"{silv.max_hp}")

    # 2. 회피 파생 — 데모: 방어 12 → 물리 회피 2, 특방 13 → 특수 회피 2, 스피드 8 → 속도 회피 1; 30이면 최대 6
    check("회피: 방어 12 → 물리 회피 2", odd.evasion("물리") == 2, f"{odd.evasion('물리')}")
    check("회피: 특수방어 13 → 특수 회피 2", odd.evasion("특수") == 2, f"{odd.evasion('특수')}")
    check("회피: 속도 회피 1 (스피드 8), 변화기엔 속도 회피만", odd.evasion("변화") == 1, f"{odd.evasion('변화')}")
    big = make(r, "pokemon/oddish-1", stats={"hp": 10, "atk": 7, "def": 45, "spa": 14, "spd": 13, "spe": 8})
    check("회피 상한 +6 (방어 45 → 9가 아니라 6)", big.evasion("물리") == 6, f"{big.evasion('물리')}")

    # 3. 전투단계 승수 — 원문: +6 → 220%, -6 → 40%; 데모: 특공 14, +1 → 16
    check("전투단계 +1: 특공 14 → 16 (데모)", archie.staged("spa") == 16, f"{archie.staged('spa')}")
    archie.stages["spa"] = 6
    check("전투단계 +6: 220% (14 → 30)", archie.staged("spa") == 30, f"{archie.staged('spa')}")
    archie.stages["spa"] = -6
    check("전투단계 -6: 40% (14 → 5)", archie.staged("spa") == 5, f"{archie.staged('spa')}")
    e = Engine(r)
    e.change_stage(archie, "spa", -3)
    check("전투단계 하한 -6 (클램프)", archie.stages["spa"] == -6)
    archie.stages["spa"] = 1

    # 4. 명중 체크 — 원문: AC 2 지진 vs 물리 회피 +4 → 6 이상 필요
    e = Engine(r)
    tank = make(r, "pokemon/oddish-2", stats={"hp": 10, "atk": 7, "def": 20, "spa": 14, "spd": 13, "spe": 8})
    quake = {"id": "move/지진", "name": "지진", "class": "물리", "ac": 2, "type": "땅", "damage_base": 10}
    hit5, _, _ = e.accuracy_check(archie, tank, quake, fixed_roll=5)
    hit6, _, _ = e.accuracy_check(archie, tank, quake, fixed_roll=6)
    check("명중 체크: AC 2 + 물리 회피 4 → 5는 빗나가고 6은 명중", (not hit5) and hit6)
    hit1, _, _ = e.accuracy_check(archie, odd, {"id": "x", "name": "x", "class": "물리", "ac": 0, "type": "노말"}, fixed_roll=1)
    hit20, _, crit = e.accuracy_check(archie, big, {"id": "x", "name": "x", "class": "물리", "ac": 10, "type": "노말"}, fixed_roll=20)
    check("자연 1은 항상 빗나감, 자연 20은 항상 명중 + 치명타", (not hit1) and hit20 and crit)

    # 5. 데미지 표 / 자속보정 / 치명타
    chart = r.mech("combat/damage-chart")["by_damage_base"]
    check("데미지 표: DB6 = 2d6+8, DB4 = 1d8+6, DB6 지정(중) = 15", chart["6"]["dice"] == "2d6+8" and chart["4"]["dice"] == "1d8+6" and chart["6"]["set"]["mid"] == 15)
    e = Engine(r)
    absorb = r.move("move/흡수")
    check("자속보정: 풀타입 뚜벅초의 흡수 DB2 → DB4", e.damage_base(odd, absorb) == 4)
    e = Engine(r)
    e.rng = FixedRng([5, 6, 5, 6])
    ember_like = {"id": "move/x", "name": "x", "class": "물리", "ac": 2, "type": "노말", "damage_base": 6}
    dmg = e.roll_damage(make(r, "trainer/maya"), make(r, "trainer/silvana", stats={"hp": 5, "atk": 6, "def": 0, "spa": 5, "spd": 5, "spe": 7}), ember_like, crit=True)
    check("치명타: DB6 2d6+8 → 주사위·고정치 두 번(11+8+11+8=38) + 공격 12 한 번 = 50", dmg == 50, f"{dmg}")

    # 6. 데모 계산 재현
    e = Engine(r)
    maya = make(r, "trainer/maya")
    odd = make(r, "pokemon/oddish-1")
    dmg = e.roll_damage(maya, odd, r.move("move/제비반환"), fixed_dice=[5, 6])
    check("데모 R3 제비반환: [5,6]+8=19, +공격 12=31, -방어 12=19, 비행 vs 풀/독 ×1.5 → 28", dmg == 28, f"{dmg}")
    inj = e.take_damage(odd, dmg)
    check("데모 R3: 28 데미지 → 53→25, 부상 2개(대규모 데미지 + 50% 표시점)", odd.hp == 25 and inj == 2 and odd.injuries == 2, f"hp {odd.hp} inj {inj}")
    e = Engine(r)
    archie = make(r, "pokemon/archie")
    odd = make(r, "pokemon/oddish-2")
    dmg = e.roll_damage(archie, odd, r.move("move/불꽃세례"), set_damage=True)
    check("데모 R4 불꽃세례 지정 데미지: DB4+2=6 → 15, +특공 16=31, -특방 13=18, 불꽃 vs 풀/독 ×1.5 → 27", dmg == 27, f"{dmg}")
    e = Engine(r)
    silv = make(r, "trainer/silvana")
    e.rng = FixedRng([3, 1])      # 1d8 눈: 용해액 DB4+2(자속)=6 → 2d6+8 … 데모는 총 30 이었음. 여기선 '특방 5 감산, 타입 없음' 부분만 확인
    acid_total_before_def = 30
    after = max(0, acid_total_before_def - silv.staged("spd"))
    mult, _ = e.type_multiplier("독", silv)
    check("데모 R3 용해액 vs 실바나: 30 - 특방 5 = 25, 트레이너는 타입 없음 ×1", after == 25 and mult == 1.0, f"{after} ×{mult}")
    e = Engine(r)
    maya = make(r, "trainer/maya")
    odd = make(r, "pokemon/oddish-3")
    dmg = e.roll_damage(maya, odd, r.move("struggle"), fixed_dice=[5])
    check("데모 R4 마야 발버둥: DB4 1d8+6 눈 5 = 11, +공격 12 = 23, -방어 12 = 11, 노말 vs 풀/독 ×1", dmg == 11, f"{dmg}")

    # 7. 소량의 체력 / 부상 / 사망
    archie = make(r, "pokemon/archie")
    e = Engine(r)
    check("소량의 체력: 최대 60 → 6 (데모)", e.tick(archie) == 6, f"{e.tick(archie)}")
    hundred = make(r, "pokemon/oddish-1", level=60, stats={"hp": 10, "atk": 7, "def": 12, "spa": 14, "spd": 13, "spe": 8})
    check("부상 예시 준비: 최대 체력 100", hundred.max_hp == 100, f"{hundred.max_hp}")
    e.take_damage(hundred, 250)
    check("부상 원문 예시: 한 번에 -150%까지 → 부상 6개 (대규모 1 + 표시점 5)", hundred.injuries == 6, f"{hundred.injuries}")
    fifty = make(r, "pokemon/oddish-1", level=10, stats={"hp": 10, "atk": 7, "def": 12, "spa": 14, "spd": 13, "spe": 8})
    fifty.injuries = 3
    check("부상 원문 예시: 최대 50, 부상 3개 → 최대 체력 35", fifty.max_hp == 35, f"{fifty.max_hp}")
    check("기절: 체력 0 이하", hundred.fainted)

    # 8. 타입 상성
    e = Engine(r)
    ghost = make(r, "pokemon/oddish-1", types=["고스트"])
    check("타입: 노말 → 고스트 = 무효 0", e.type_multiplier("노말", ghost)[0] == 0)
    normal = make(r, "pokemon/oddish-1", types=["노말"])
    check("타입: 격투 → 노말 = 굉장한 효과 ×1.5", e.type_multiplier("격투", normal)[0] == 1.5)
    gs = make(r, "pokemon/oddish-1", types=["풀", "강철"])
    check("타입: 불꽃 → 풀/강철 = 이중 굉장한 효과 ×2", e.type_multiplier("불꽃", gs)[0] == 2.0)
    wd = make(r, "pokemon/oddish-1", types=["풀", "드래곤"])
    check("타입: 물 → 풀/드래곤 = 이중 저항 ×0.25", e.type_multiplier("물", wd)[0] == 0.25)
    pf = make(r, "pokemon/oddish-1", types=["독", "비행"])
    check("타입: 땅 → 독/비행 = 약점+무효 → 0", e.type_multiplier("땅", pf)[0] == 0)
    check("타입: 트레이너는 타입 없음 → ×1", e.type_multiplier("불꽃", make(r, "trainer/maya"))[0] == 1.0)

    # 9. 타입 면역 / 상태이상 효과 (자동 기계화된 conditions.json 해석)
    e = Engine(r)
    odd = make(r, "pokemon/oddish-1")
    ok = e.apply_status(odd, "독")
    check("타입 면역: 독타입 뚜벅초는 독에 걸리지 않음", not ok)
    pika = make(r, "pokemon/oddish-1", types=["전기"])
    check("타입 면역: 전기타입은 마비 면역", not e.apply_status(pika, "마비"))
    archie = make(r, "pokemon/archie")
    e.apply_status(archie, "독")
    check("독(자동 기계화): 걸리면 특수방어 -2 전투단계 → 9 → 7", "독" in archie.conditions and archie.stages["spd"] == -2 and archie.staged("spd") == 7, f"{archie.stages} {archie.staged('spd')}")
    archie.took_standard = True
    e.end_of_turn(archie)
    check("독(자동 기계화): 기본 행동한 턴 끝에 소량의 체력 6 손실 → 54 (데모 44/60은 이미 흡수 피해 후)", archie.hp == 54, f"{archie.hp}")
    e.cure_status(archie, "독")
    check("독 치료 시 전투단계 복구", archie.stages["spd"] == 0)
    check("화상(자동 기계화): 불꽃타입 아치는 화상 면역", not e.apply_status(archie, "화상"))
    frozen = make(r, "pokemon/oddish-1")
    e.apply_status(frozen, "얼음")
    check("얼음(자동 기계화): 회피 보너스 없음 → 회피 0", frozen.evasion("물리") == 0)
    e.rng = FixedRng([16])
    e.end_of_turn(frozen)
    check("얼음(자동 기계화): 턴 끝 DC 16 내성 체크 성공 → 치료", "얼음" not in frozen.conditions)

    # 10. 포획률 — 챕터 5 예시 3건 (개정판 1d20)
    e = Engine(r)
    pika = make(r, "pokemon/oddish-1", name="피카츄", level=10, types=["전기"], evolutions_remaining=1)
    pika.hp = int(pika.max_hp * 0.7)
    pika.conditions.add("혼란")
    check("포획률 예시: 레벨10 피카츄 70% 혼란 진화1 → 7", e.capture_rate(pika)[0] == 7, f"{e.capture_rate(pika)}")
    cat = make(r, "pokemon/oddish-1", name="캐터피", level=30, types=["벌레"], evolutions_remaining=2)
    cat.hp = int(cat.max_hp * 0.4)
    check("포획률 예시: 레벨30 이로치(+5) 캐터피 40% 진화2 → 12", e.capture_rate(cat, rarity=5)[0] == 12, f"{e.capture_rate(cat, rarity=5)}")
    hyd = make(r, "pokemon/oddish-1", name="삼삼드레", level=80, types=["악", "드래곤"], evolutions_remaining=0)
    hyd.hp, hyd.injuries = 1, 5
    hyd.conditions.update({"화상", "독"})
    # 원문은 '포획율은 10입니다. 계산: 10 +8 -4 -2 -4 = 10' 이라고 적었지만 그 식의 합은 8이다. 엔진은 식(체크박스 규칙)을 따른다 → 원문 예시의 산수 오류 발견.
    check("포획률 예시: 레벨80 삼삼드레 체력1 화상·독 부상5 → 식대로 8 (원문은 '10'이라 적었으나 10+8-4-2-4=8, 원문 산수 오류)", e.capture_rate(hyd)[0] == 8, f"{e.capture_rate(hyd)}")
    # 구판(데모): 라운드 1 → 59 (100-26-25+10), 라운드 4 (부상 2) → 94
    odd = make(r, "pokemon/oddish-1")
    check("포획률 구판(데모 R1): 100 - 26 - 25 + 10 = 59", e.capture_rate_superseded(odd, 1.0) == 59)
    odd.injuries = 2
    check("포획률 구판(데모 R4): 100 - 26 + 10 + 2×5 = 94", e.capture_rate_superseded(odd, 0.4) == 94)

    # 11. 스킬 체크 / AP
    rank = r.mech("gameplay/skill-rank-dice")["by_rank_name"]
    check("스킬 랭크 표: 전문 = 5d6, 미숙 = 2d6 (원문 예: 전문 육상 5d6)", rank["전문"]["dice"] == "5d6" and rank["미숙"]["dice"] == "2d6")
    ap = r.mech("gameplay/action-points")["max"]
    check("AP 최대치: 레벨 15 → 8 (원문 예)", ap == "5 + floor(level / 5)" and 5 + 15 // 5 == 8)

    # 11b. 스킬 체크 — 원문 예: 전문 육상 5d6, 스킬 향상 엣지 +2 → 5d6+2; 팀/지원 체크
    e = Engine(r)
    ath = make(r, "trainer/maya", skills={"athletics": "전문"})
    ok, total = e.skill_check(ath, "athletics", 15, mods=2, fixed=[3, 4, 2, 5, 1])
    check("스킬 체크: 전문 육상 5d6+2 = [3,4,2,5,1]+2 = 17 ≥ DC 15 성공", ok and total == 17, f"{total}")
    ok, total = e.skill_check(make(r, "trainer/silvana"), "athletics", 10, fixed=[2, 3, 1], helper_rank=4)
    check("지원 체크: 초보 육상 3d6 [2,3,1] + 도우미 랭크 4의 절반 2 = 8 < DC 10 실패", (not ok) and total == 8, f"{total}")

    # 12. never_miss (hand mech)
    e = Engine(r)
    hit, _, _ = e.accuracy_check(make(r, "trainer/maya"), big, r.move("move/제비반환"), fixed_roll=1)
    check("제비반환: 자연 1이어도 빗나가지 않음 (데모: '제비반환는 놓치지 않습니다')", hit)

    passed = sum(1 for _, ok, _ in results if ok)
    lines = ["# PTK 규칙 단위 테스트 결과 (자동 생성)", "", f"**{passed}/{len(results)} 통과**", "", "| # | 규칙 (원문 예시) | 결과 | 비고 |", "|---|---|---|---|"]
    for i, (name, ok, detail) in enumerate(results, 1):
        lines.append(f"| {i} | {name} | {'PASS' if ok else 'FAIL'} | {detail} |")
    out = "\n".join(lines) + "\n"
    open(os.path.join(root, "output/rule-tests.md"), "w", encoding="utf-8").write(out)
    print(out)
    return passed == len(results)


if __name__ == "__main__":
    ok = run(sys.argv[1] if len(sys.argv) > 1 else ".")
    sys.exit(0 if ok else 1)
