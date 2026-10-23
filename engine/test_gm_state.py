"""GM 상태 개입 테스트: 체력·단계·상태(면역 무시)·부상·위치·도구·날씨·소생·기절·참가자·스냅샷/되돌리기·문자열 명령·기록·턴 훅 스크립트.
  python -X utf8 -I engine/test_gm_state.py <root>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Combatant, Engine, Rules, scenario  # noqa: E402
from gm_console import make_hook  # noqa: E402
from grid import Grid  # noqa: E402


def make(r, cid, **over):
    spec = dict(r.creatures[cid])
    spec.update(over)
    return Combatant(r, spec)


def run(root):
    res = []

    def check(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    r = Rules(root)
    e = Engine(r)
    e.grid = Grid(10, 10)
    a, t = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    a.pos, t.pos = (2, 2), (6, 2)
    gm = e.gm
    gm.everyone = [a, t]
    # 1. 체력·임시·부상
    gm.set_hp(a, 30, reason="낙석")
    check("set_hp: 60 → 30, 이유가 로그에", a.hp == 30 and any("[GM 상태] 아치 체력: 60 → 30 (낙석)" in l for l in e.log_lines))
    gm.set_hp(a, delta=-40, reason="추락")
    check("set_hp delta: 0 이하 → 기절 표시", a.hp == -10 and "기절" in a.conditions)
    gm.revive(a, 15, reason="GM 자비")
    check("revive: 기절 해제, 체력 15", a.hp == 15 and "기절" not in a.conditions)
    gm.set_injuries(a, 3, reason="누적 피로")
    check("set_injuries: 부상 3 → 최대 체력 42, 체력은 최대 이하로", a.injuries == 3 and a.max_hp == 42 and a.hp <= 42)
    gm.set_temp_hp(a, 9)
    check("set_temp_hp: 9", a.temp_hp == 9)
    # 2. 단계·스탯·레벨
    gm.set_stage(a, "공격", delta=8, reason="격려")
    check("set_stage: 한글 스탯명, +8 은 +6 으로 클램프", a.stages["atk"] == 6)
    gm.set_stage(a, "명중", value=2)
    check("set_stage acc: 명중 단계 2", a.accuracy_stage == 2)
    gm.set_stat(a, "spe", delta=5)
    gm.set_level(a, 30, reason="성장")
    check("set_stat/set_level: 스피드 +5, 레벨 30 → 최대 체력 (30+30+10)-3×7 = 49", a.stats["spe"] == 17 and a.level == 30 and a.max_hp == 49, f"{a.max_hp}")
    # 3. 상태: 면역 무시 강제 부여 / 제거
    gm.add_condition(t, "독", reason="GM 권한: 특수한 독", force=True)
    check("add_condition force: 독 타입 뚜벅초에게 독을 강제 부여 (룰로는 면역)", "독" in t.conditions)
    gm.add_condition(t, "마비", force=False)
    gm.remove_condition(t, "독", reason="해독제")
    check("remove_condition: 독만 제거, 마비 유지", "독" not in t.conditions and "마비" in t.conditions)
    gm.remove_condition(t, "전부")
    check("remove_condition 전부", not t.conditions)
    # 4. 위치·도구·버프·기술·특성·타입·카운터·고유 상태
    gm.set_position(t, (4, 4), reason="밀려남")
    gm.set_item(t, "오랭열매")
    gm.add_buff(t, "만복버프")
    gm.set_move(t, "move/불꽃세례", add=True, reason="GM 선물")
    gm.set_ability(t, "맹화", add=True)
    gm.set_types(t, ["풀"])
    gm.set_counter(t, "stockpile", 2)
    gm.set_custom(t, "표식", "GM 표식")
    check("위치·도구·버프·기술·특성·타입·카운터·고유 상태 설정", t.pos == (4, 4) and t.item == "오랭열매" and t.buffs == ["만복버프"] and "move/불꽃세례" in t.moves and "맹화" in t.abilities and t.types == ["풀"] and t.counters["stockpile"] == 2 and "표식" in t.custom_conditions)
    check("set_ability 는 특성 효과를 등록한다 (맹화 → 불꽃 +5 패시브)", any(m.get("type") == "damage_roll_mod" for m in t.modifiers))
    # 5. 전장: 날씨·필드·함정·지형
    gm.set_weather("비", reason="소나기")
    gm.set_field("그래스")
    gm.place_hazard((5, 5), "압정")
    gm.set_terrain((3, 3), "둔화")
    check("날씨(한글→코드)·필드·함정·지형", e.weather == "rain" and e.field["name"] == "그래스" and (5, 5) in e.hazards and (3, 3) in e.grid.slow)
    # 6. 스냅샷 / 되돌리기
    gm.snapshot("before")
    gm.set_hp(a, 1); gm.add_condition(a, "화상"); gm.set_weather("쾌청"); gm.set_position(a, (9, 9)); gm.clear_hazards()
    gm.restore("before", reason="전투 다시")
    check("restore: 체력·상태·위치·날씨·함정이 스냅샷 시점으로", a.hp == 15 and "화상" not in a.conditions and a.pos == (2, 2) and e.weather == "rain" and (5, 5) in e.hazards, f"{a.hp} {a.conditions} {a.pos} {e.weather}")
    # 7. 참가자 추가/제거, 퇴장/등장
    m = make(r, "trainer/maya")
    gm.add_combatant(m, pos=(1, 1), side="party", reason="마야 합류")
    check("add_combatant: 목록에 추가, 위치·진영", m in gm.everyone and m.pos == (1, 1) and m.side == "party")
    gm.recall(a, reason="볼로")
    check("recall: on_field False → 대상 선택에서 빠짐", not a.on_field and not e.targets_in_range(t, r.move("move/흡수"), [a, t, m], a))
    gm.send_out(a, (2, 3))
    gm.remove_combatant(m)
    check("send_out / remove_combatant", a.on_field and a.pos == (2, 3) and m not in gm.everyone)
    # 8. 문자열 명령
    check("command: '아치 hp 30 -- 낙석'", gm.command("아치 hp 30 -- 낙석") == "ok" and a.hp == 30)
    check("command: '뚜벅초 B +독' (이름에 공백 포함, 강제 부여)", gm.command("뚜벅초 B +독") == "ok" and "독" in t.conditions)
    check("command: '뚜벅초 B 상태 -독'", gm.command("뚜벅초 B 상태 -독") == "ok" and "독" not in t.conditions)
    check("command: '아치 atk -3' (현재 +6 → +3)", gm.command("아치 atk -3") == "ok" and a.stages["atk"] == 3)
    check("command: '전원 회피 +1'", gm.command("전원 회피 +1 -- 안개") == "ok" and a.evasion_mod == 1 and t.evasion_mod == 1)
    check("command: '날씨 모래바람' / '아치 위치 7,7' / '아치 도구 없음'", gm.command("날씨 모래바람") == "ok" and e.weather == "sandstorm" and gm.command("아치 위치 7,7") == "ok" and a.pos == (7, 7) and gm.command("아치 도구 없음") == "ok" and a.item is None)
    check("command: '스냅샷 x' → '아치 기절' → '되돌리기 x'", gm.command("스냅샷 x") == "x" and gm.command("아치 기절") == "ok" and a.fainted and gm.command("되돌리기 x -- 취소") == "ok" and not a.fainted and a.hp == 30)
    try:
        gm.command("없는이름 hp 1")
        missing = False
    except KeyError:
        missing = True
    check("command: 없는 이름은 KeyError 로 알려 줌", missing)
    # 9. 기록: 모든 개입이 rulings.log 에 kind=state 로, 이유 포함
    states = [x for x in e.rulings.log if x["kind"] == "state"]
    check("기록: state 항목 30건 이상, 이유('낙석') 포함, 보고서에 표로", len(states) >= 30 and any(x["reason"] == "낙석" for x in states) and "낙석" in e.rulings.report(), len(states))
    # 10. 턴 훅 스크립트: 3번째 턴 직전에 아치 체력 5 → 같은 seed 의 결과가 달라진다
    # The simulation explicitly chooses a GM tie policy; no engine default is assumed.
    tie_policy = os.path.join(root, "tools/fixtures/initiative-gm-policy.json")
    base = scenario(root, 5, rulings_path=tie_policy)
    hooked = scenario(root, 5, rulings_path=tie_policy, hook=make_hook(None, {3: ["아치 hp 5 -- 낙석", "날씨 비 -- 소나기"]}, interactive=False))
    check("턴 훅: 명령이 로그에 남고 같은 seed 의 전투 결과가 달라짐", any("[GM 명령 @턴 3]" in l for l in hooked.log_lines) and base.log_lines[-1] != hooked.log_lines[-1], hooked.log_lines[-1][:80])
    check("턴 훅 없는 scenario: GM 상태 명령 없음 (명시 동률 재정은 별도)", not any("[GM 명령" in l for l in base.log_lines) and not any(row["kind"] == "state" for row in base.rulings.log))

    passed = sum(1 for _, ok, _ in res if ok)
    lines = ["# GM 상태 개입 테스트 (자동 생성)", "", f"**{passed}/{len(res)} 통과**", "", "| # | 규칙 | 결과 | 비고 |", "|---|---|---|---|"]
    for i, (n, ok, d) in enumerate(res, 1):
        lines.append(f"| {i} | {n} | {'PASS' if ok else 'FAIL'} | {str(d)[:80]} |")
    open(os.path.join(root, "output/gm-state-tests.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return passed == len(res)


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
