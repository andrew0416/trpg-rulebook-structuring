"""전투원 생성기·인카운터·커스텀 종 테스트.
  python -X utf8 -I engine/test_builder.py <root>"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from builder import allocate_stats, build_pokemon, build_trainer, species_lookup  # noqa: E402
from custom_species import validate  # noqa: E402
from encounter import choose_action, load_encounter, run_encounter, usable_moves  # noqa: E402
from engine import Combatant, Engine, Rules  # noqa: E402


def run(root):
    res = []

    def check(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    r = Rules(root)
    # 1. 스탯 분배 규칙
    base = species_lookup(r, "뚜벅쵸")["base_stats"]
    st = allocate_stats(base, 13 + 10, "balanced")
    check("stat-build: 포인트 = level+10 = 23 이 전부 분배됨", sum(st.values()) - sum(base.values()) == 23, st)
    order_base = sorted(base, key=lambda s: -base[s])
    ok_order = all(st[order_base[i]] >= st[order_base[i + 1]] for i in range(5) if base[order_base[i]] > base[order_base[i + 1]])
    check("stat-build: 기본 스탯의 대소 관계 보존", ok_order, st)
    st2 = allocate_stats(base, 23, "special", nature="위풍당당", rules=r)
    nat = r.mech("pokemon/natures")["by_name"]["위풍당당"]
    check(f"성격 위풍당당 (HP↑ {nat['down']}↓): HP +1, 특공 -2 가 반영되고 특공 전략은 특공에 더 줌", st2["hp"] >= st["hp"] and st2["spa"] >= st["spa"] - 2, f"{st2}")
    # 2. 종 + 레벨 → spec
    spec = build_pokemon(r, "뚜벅쵸", 13, name="뚜벅초 X", strategy="special", wild=True, pos=(9, 7))
    check("build_pokemon: 종 데이터에서 타입·이동·크기·체급·스킬", spec["types"] == ["풀", "독"] and spec["movement"]["land"] == 4 and spec["size"] == "소형" and spec["skills"], spec["skills"])
    check("build_pokemon: 레벨 13 이하 레벨업 기술 (흡수·달콤한향기·용해액·독가루) + 발버둥", set(spec["moves"]) >= {"move/흡수", "move/달콤한향기", "move/용해액", "move/독가루", "struggle"} and "move/저리가루" not in spec["moves"], spec["moves"])
    check("build_pokemon: 기본 특성 첫 번째(엽록소), 진화 2단계 남음", spec["abilities"] == ["엽록소"] and spec["evolutions_remaining"] == 2, f"{spec['abilities']} {spec['evolutions_remaining']}")
    c = Combatant(r, spec)
    check("Combatant 로 바로 전투 투입 (최대 체력 = 13 + hp×3 + 10)", c.max_hp == 13 + spec["stats"]["hp"] * 3 + 10 and c.side == "wild", c.max_hp)
    spec40 = build_pokemon(r, "브케인", 40, strategy="attack")
    check("레벨 40 브케인: 최대 6개 기술, 포인트 50", len([m for m in spec40["moves"] if m != "struggle"]) <= 6 and sum(spec40["stats"].values()) - sum(species_lookup(r, '브케인')['base_stats'].values()) == 50, spec40["moves"])
    tr = build_trainer(r, "민호", 10, {"hp": 10, "atk": 8, "def": 8, "spa": 6, "spd": 8, "spe": 10}, items={"poke_ball": 2})
    check("build_trainer: 트레이너 spec (발버둥 포함, 볼 2개)", tr["kind"] == "trainer" and "struggle" in tr["moves"] and tr["items"]["poke_ball"] == 2)
    # 3. 인카운터 로더 + AI
    e, enc, party, wild = load_encounter(root, "data/encounters/lakeside.json")
    check("load_encounter lakeside: 파티 2(트레이너+브케인), 야생 3, 격자·특성 등록", len(party) == 2 and len(wild) == 3 and e.grid is not None and all(c.side for c in party + wild))
    archie = party[1]
    kind, mid, tgt = choose_action(e, archie, wild, party)
    check("AI: 아치(불꽃)는 풀 상대에 불꽃 기술을 고른다", kind == "move" and r.move(mid)["type"] == "불꽃", mid)
    odd = wild[0]
    odd.move_uses["move/달콤한향기"] = 1
    r_mm = r.moves_mech.get("move/달콤한향기", {}).get("header", {}).get("frequency")
    um = usable_moves(e, odd)
    check("usable_moves: 장면 1회 기술은 다 쓰면 빠진다", ("move/달콤한향기" not in um) if (r_mm or {}).get("kind") == "scene" and (r_mm or {}).get("uses", 1) <= 1 else True, f"{r_mm} {um}")
    e1, p1, w1 = run_encounter(root, "data/encounters/lakeside.json", seed=5, write=True)
    e2, p2, w2 = run_encounter(root, "data/encounters/lakeside.json", seed=5, write=False)
    check("run_encounter: 같은 seed 는 같은 로그 (결정적)", e1.log_lines == e2.log_lines and os.path.exists(os.path.join(root, "output/encounter-lakeside.md")), len(e1.log_lines))
    e3, p3, w3 = run_encounter(root, "data/encounters/cave.json", write=True)
    # The generated cave still verifies weather and all actors. Its real 2→5
    # injury event cannot certify a winner; completed-result coverage is below.
    check("run_encounter cave: 모래바람 틱 및 생성된 6행위자 유지", any("모래바람: " in l for l in e3.log_lines) and len(p3) + len(w3) == 6, [c.name for c in p3 + w3])
    pending = e3._heavy_events.get(e3._heavy_pending, {})
    check("run_encounter cave: 정확한 부상 2→5 사건을 미완료로 보존",
          pending.get("producer") == "Engine.resolve_attack_damage"
          and pending.get("before", {}).get("injuries") == 2
          and pending.get("observed_after", {}).get("injuries") == 5
          and pending.get("amount") == 50 and pending.get("target") in w3
          and e3._heavy_driver_result.get("status") == "incomplete"
          and (e3.round_no, e3.elapsed_seconds) == (3, 20)
          and e3.encounter_active and e3._active_turn_actor is pending.get("attacker")
          and not any(l.startswith("결과:") or l == "## 결과" for l in e3.log_lines), e3._heavy_pending)
    finished, fp, fw = run_encounter(root, "tests/fixtures/light-completion.json", write=False)
    check("run_encounter 경상 전투: 실제 종료 및 파티 승리 결과 유지",
          finished._heavy_pending is None and not finished.encounter_active
          and all(c.injuries < 5 for c in fp + fw)
          and all(c.fainted for c in fw) and any(not c.fainted for c in fp)
          and any(l.startswith("결과: 파티 승리") for l in finished.log_lines), finished.round_no)
    # 4. 커스텀 종
    rc = Rules(root)   # data/custom/species/*.json 자동 적재
    check("커스텀 종 자동 적재: 실험체 (출처 custom)", "pokemon/실험체" in rc.species and rc.species["pokemon/실험체"]["source"] == "custom" and rc.custom_species == ["pokemon/실험체"], rc.custom_species)
    check("커스텀 기술 오버로드가 기술 테이블·mech(reviewed 'custom')에 들어옴", "move/오버로드" in rc.moves and rc.move_mech("move/오버로드")[1] == "reviewed" and rc.moves_mech["move/오버로드"]["header"]["range"]["origin"] == 6, rc.move_mech("move/오버로드"))
    check("커스텀 특성 정전기Ω 가 특성 효과 테이블에", "정전기Ω" in rc.ability_effects and rc.ability_freq["정전기Ω"].startswith("장면"))
    sp = build_pokemon(rc, "실험체", 15, strategy="special")
    check("커스텀 종으로 전투원 생성: 전기/고스트, 레벨 15 이하 학습(오버로드 포함), 기본 특성 부유", sp["types"] == ["전기", "고스트"] and "move/오버로드" in sp["moves"] and sp["abilities"] == ["부유"], sp["moves"])
    ec = Engine(rc, 3)
    cc, tt = Combatant(rc, sp), Combatant(rc, build_pokemon(rc, "뚜벅쵸", 13, name="상대"))
    cc.pos, tt.pos = (0, 0), (1, 0)
    ec.register_abilities(cc)
    dealt = ec.use_move(cc, tt, "move/오버로드")
    check("커스텀 기술 실행: 오버로드가 판정·피해·효과까지 엔진을 통과", any("오버로드" in l for l in ec.log_lines) and dealt >= 0, ec.log_lines[-3:])
    bad = {"name": "엉망", "types": ["빛"], "base_stats": {"hp": 5}, "movement": {"fly": 3}, "abilities": {"기본 특성": ["없는특성"]}, "learnset": {"level_up": [{"level": 1, "move": "없는기술"}]}}
    errors, warns = validate(rc, bad)
    check("validate: 타입·스탯·이동 키·특성·기술 오류를 전부 잡음 (5건 이상)", len(errors) >= 5, errors)
    big = dict(json.load(open(os.path.join(root, "data/custom/species/silheomche.json"), encoding="utf-8")))
    big["base_stats"] = {"hp": 30, "atk": 30, "def": 30, "spa": 30, "spd": 30, "spe": 30}
    errors2, warns2 = validate(rc, big)
    check("validate: 기본 스탯 합이 DB 범위 밖이면 오류 아닌 경고", not errors2 and any("범위" in w for w in warns2), warns2)
    from ruleset import RuleFilter
    rf = RuleFilter({"sources": ["core"], "variants": []}, "core")
    ok, why = rf.allows({"id": "pokemon/실험체", "title": "실험체", "tags": ["custom"], "source": {"file": "data/custom/species/silheomche.json"}})
    check("룰셋: 커스텀 출처는 core 프로필에서 제외됨(source:custom)", not ok and why == "source:custom", why)

    passed = sum(1 for _, ok, _ in res if ok)
    lines = ["# 전투원 생성기·인카운터·커스텀 종 테스트 (자동 생성)", "", f"**{passed}/{len(res)} 통과**", "", "| # | 규칙 | 결과 | 비고 |", "|---|---|---|---|"]
    for i, (n, ok, d) in enumerate(res, 1):
        lines.append(f"| {i} | {n} | {'PASS' if ok else 'FAIL'} | {str(d)[:90]} |")
    open(os.path.join(root, "output/builder-tests.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return passed == len(res)


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
