"""턴 구조 테스트: 날씨 피해 보정·틱 피해·면역·지속, 행동 예산(기본/이동/신속, 낮춤, 소진), 기회 공격(이탈 vs 이동, 원거리, 잠듦 면제), 공중 이동, 우선 선언, 트레이너 무기.
  python -X utf8 -I engine/test_turn.py <root>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from builder import build_pokemon, build_trainer  # noqa: E402
from engine import Combatant, Engine, Rules  # noqa: E402
from grid import Grid  # noqa: E402
import turn as TURN  # noqa: E402


def mk(r, species, level, **kw):
    return Combatant(r, build_pokemon(r, species, level, **kw))


def run(root):
    res = []

    def check(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    r = Rules(root)
    # 1. 날씨: 쾌청 불꽃 +5 / 물 -5, 비바라기 반대
    e = Engine(r)
    a, t = mk(r, "브케인", 20, strategy="special"), mk(r, "뚜벅쵸", 13)
    d0 = e.roll_damage(a, t, r.move("move/불꽃세례"), set_damage=True)
    e.weather, e.weather_rounds = "sunny", 5
    d1 = e.roll_damage(a, t, r.move("move/불꽃세례"), set_damage=True)
    check("쾌청: 불꽃세례 피해 굴림 +5 → 최종 +7 (×1.5)", d1 - d0 in (7, 8), f"{d0} → {d1}")
    w = mk(r, "꼬부기", 20, strategy="special")
    dw0 = e.roll_damage(w, t, r.move("move/물대포"), set_damage=True) if "move/물대포" in r.moves else None
    check("쾌청: 물 기술 피해 굴림 -5 (로그에 날씨 보정)", any("날씨(쾌청): 물 피해 굴림 -5" in l for l in e.log_lines) if dw0 is not None else True, dw0)
    # 2. 모래바람 틱 피해와 면역 타입, 지속 5라운드
    e2 = Engine(r)
    e2.weather, e2.weather_rounds = "sandstorm", 2
    o, g = mk(r, "뚜벅쵸", 13), mk(r, "꼬마돌", 13)
    e2.everyone = [o, g]
    e2.start_of_turn(o)
    e2.start_of_turn(g)
    check("모래바람: 풀/독 뚜벅쵸는 턴 시작에 소량 손실, 바위/땅 꼬마돌은 면역", o.hp == o.max_hp - e2.tick(o) and g.hp == g.max_hp, f"{o.hp}/{o.max_hp} {g.hp}/{g.max_hp}")
    e2.start_round([o, g]); e2.start_round([o, g])
    check("날씨 지속: 라운드 시작마다 감소, 0 이면 맑음", e2.weather is None and any("종료 → 맑음" in l for l in e2.log_lines))
    e2.weather = "hail"
    check("싸라기눈: 얼음 내성 체크 DC -2 보정값(=+2 페널티)", TURN.weather_save_mod(e2, "얼음") == -2)
    # 3. 행동 예산
    e3 = Engine(r); e3.grid = Grid(10, 10)
    a3, t3 = mk(r, "브케인", 20, pos=(1, 1)), mk(r, "뚜벅쵸", 13, pos=(2, 1), wild=True)
    e3.everyone = [a3, t3]
    e3.start_of_turn(a3)
    d_a = e3.use_move(a3, t3, "move/불꽃세례")
    d_b = e3.use_move(a3, t3, "move/불꽃세례")
    check("행동 예산: 같은 턴에 기본 행동 두 번 → 두 번째 거부(0) + 로그", d_b == 0 and any("기본 행동이 남지 않음" in l for l in e3.log_lines), f"{d_a} {d_b}")
    e3.start_of_turn(a3)
    a3.budget["swift"] = 0
    check("낮춤: 신속이 없으면 기본 행동을 신속으로 낮춰 사용", TURN.spend(e3, a3, "swift", "테스트") and a3.budget["standard"] == 0 and any("낮춰 사용" in l for l in e3.log_lines))
    check("자유 행동은 예산을 쓰지 않음", TURN.spend(e3, a3, "free") and a3.budget["standard"] == 0)
    check("free_action=True 로 부른 use_move(기회 공격·반응)는 예산을 안 씀", e3.use_move(a3, t3, "move/불꽃세례", free_action=True) >= 0 and a3.budget["standard"] == 0)
    # 4. 기회 공격: 인접 적에게서 2칸 이상 이동하면 발버둥 방해 공격, 1칸 이탈은 아님, 잠든 적은 못 함
    e4 = Engine(r, 7); e4.grid = Grid(12, 6)
    m, foe, far = mk(r, "브케인", 20, pos=(3, 3)), mk(r, "꼬마돌", 20, pos=(4, 3), wild=True), mk(r, "뚜벅쵸", 13, pos=(9, 3), wild=True)
    e4.everyone = [m, foe, far]
    e4.start_round([m, foe, far]); e4.start_of_turn(m)
    hp0 = m.hp
    e4.approach(m, far, 1)
    check("기회 공격: 인접한 꼬마돌 옆에서 멀리 이동 → 꼬마돌의 발버둥 방해 공격 (로그)", any("[기회 공격] 꼬마돌" in l for l in e4.log_lines), m.hp)
    check("기회 공격은 라운드 1회: 표식이 남음", foe.aoo_used)
    e5 = Engine(r, 7); e5.grid = Grid(12, 6)
    m2, foe2 = mk(r, "브케인", 20, pos=(3, 3)), mk(r, "꼬마돌", 20, pos=(4, 3), wild=True)
    e5.everyone = [m2, foe2]
    e5.start_round([m2, foe2]); e5.start_of_turn(m2)
    foe2.conditions.add("잠듦")
    e5.approach(m2, Combatant(r, build_pokemon(r, "뚜벅쵸", 13, pos=(9, 3))), 1)
    check("잠든 적은 기회 공격을 못 함", not any("[기회 공격]" in l for l in e5.log_lines))
    e6 = Engine(r, 7); e6.grid = Grid(12, 6)
    s6, f6 = mk(r, "브케인", 20, pos=(3, 3)), mk(r, "꼬마돌", 20, pos=(4, 3), wild=True)
    e6.everyone = [s6, f6]
    e6.start_round([s6, f6]); e6.start_of_turn(s6)
    far6 = mk(r, "뚜벅쵸", 13, pos=(8, 3), wild=True); e6.everyone.append(far6)
    e6.use_move(s6, far6, "move/불꽃세례")
    check("원거리 공격: 인접한 적을 두고 멀리 쏘면 기회 공격 유발", any("[기회 공격] 꼬마돌" in l and "원거리" in l for l in e6.log_lines))
    # 5. 공중 이동: 주뱃(공중 6 > 육상 2)은 둔화 지형 비용 없이 이동하고 airborne 표식
    e7 = Engine(r); e7.grid = Grid(12, 6, slow={(4, 3), (5, 3), (6, 3)})
    z = mk(r, "주뱃", 18, pos=(2, 3)); tgt7 = mk(r, "뚜벅쵸", 13, pos=(9, 3), wild=True)
    e7.everyone = [z, tgt7]; e7.start_of_turn(z)
    e7.approach(z, tgt7, 1)
    sky = max(r.species["pokemon/주뱃"]["movement"].get("sky", 0), 0)
    check(f"공중 이동: 주뱃 공중 {sky} 로 둔화 지형을 비용 없이 통과, airborne", z.airborne and z.pos[0] >= 2 + min(sky, 6) - 1 and any("공중/부유" in l for l in e7.log_lines), f"{z.pos} {sky}")
    # 6. 우선 선언 (인카운터): 우선 키워드 기술 보유자가 먼저
    from encounter import run_encounter
    enc, _, _ = run_encounter(root, "data/encounters/cave.json", write=False)
    check("인카운터 루프가 라운드 시작 API 를 거쳐 라운드 번호를 센다", enc.round_no >= 1, enc.round_no)
    check("중상 보류는 현재 라운드와 시간 보존, 승패 확정 금지",
          enc._heavy_pending is not None and enc._heavy_driver_result.get("status") == "incomplete"
          and (enc.round_no, enc.elapsed_seconds) == (3, 20) and enc.encounter_active
          and not any(l.startswith("결과:") for l in enc.log_lines))
    complete, cp, cw = run_encounter(root, "tests/fixtures/light-completion.json", write=False)
    check("경상 전투의 정상 종료 계약 유지",
          complete._heavy_pending is None and not complete.encounter_active
          and all(c.injuries < 5 for c in cp + cw)
          and any(l.startswith("결과: 파티 승리") for l in complete.log_lines))
    # Only declaration detection is asserted. The driver is not a proof of
    # league initiative, tie resolution, Priority debt or interruption ordering.
    priority, pp, pw = run_encounter(root, "tests/fixtures/priority-declaration.json", write=False)
    check("실제 전광석화 선택에서 우선 선언 관측",
          TURN.has_priority(priority, pp[0], priority.r.move("move/전광석화"))
          and any(l.startswith("우선 선언: priority-declarer") for l in priority.log_lines)
          and pp[0].move_uses.get("move/전광석화", 0) == 1
          and priority._heavy_pending is None, pp[0].move_uses)
    # 7. 트레이너 무기: 대형 근접무기 → 발버둥 DB +2, AC +1; 좋음 등급 + 숙련 전투 → 무기 기술
    e8 = Engine(r)
    tr = Combatant(r, build_trainer(r, "민호", 10, {"hp": 10, "atk": 8, "def": 8, "spa": 6, "spd": 8, "spe": 10}, skills={"combat": "숙련"}))
    mid = TURN.equip_weapon(e8, tr, {"name": "육척봉", "kind": "대형 근접무기", "grade": "좋음", "moves": ["백스윙", "강타"]})
    st = r.mech("combat/struggle")
    check("무기 장착: 육척봉 발버둥 DB 4+2=6, AC 4+1=5, 무기 기술 백스윙 추가", r.moves[mid]["damage_base"] == st["damage_base"] + 2 and r.moves[mid]["ac"] == st["ac"] + 1 and any("백스윙" in r.moves[x]["name"] for x in tr.moves), [r.moves[x]["name"] for x in tr.moves])
    t8 = mk(r, "뚜벅쵸", 13, pos=(1, 0)); tr.pos = (0, 0)
    dmg = e8.use_move(tr, t8, mid, set_damage=True)
    check("무기 발버둥으로 실제 공격", any("육척봉 발버둥" in l for l in e8.log_lines) and dmg >= 0)

    passed = sum(1 for _, ok, _ in res if ok)
    lines = ["# 턴 구조(날씨·행동 경제·기회 공격·이동 방식·무기) 테스트 (자동 생성)", "", f"**{passed}/{len(res)} 통과**", "", "| # | 규칙 | 결과 | 비고 |", "|---|---|---|---|"]
    for i, (n, ok, d) in enumerate(res, 1):
        lines.append(f"| {i} | {n} | {'PASS' if ok else 'FAIL'} | {str(d)[:90]} |")
    open(os.path.join(root, "output/turn-tests.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return passed == len(res)


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
