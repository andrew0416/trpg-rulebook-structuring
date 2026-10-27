"""룰셋 필터 테스트: 분류, 프로필별 제외/치환, 엔진의 거부·치환 로그, 단위 버전 선택, DB 필터 도구.
  python -X utf8 -I engine/test_ruleset.py <root>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from engine import Combatant, Engine, Rules  # noqa: E402
from grid import Grid  # noqa: E402
from native_scenario_fixture import prepare_body  # noqa: E402
from ruleset import RuleFilter, classify, base_id, base_name, UnresolvedRuleSelection  # noqa: E402
from filter_ruleunits import filter_db  # noqa: E402


def make(r, cid, **over):
    spec = dict(r.creatures[cid])
    spec.update(over)
    return Combatant(r, spec)


def run(root):
    res = []

    def check(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    # 1. 분류
    check("classify: 시트 홈브류 구역 기술 → (core, 홈브류)", classify({"title": "눈보라 [홈브류]", "tags": ["move", "homebrew"], "source": {"file": "db/moves.csv"}}) == ("core", "홈브류"))
    check("classify: [Playtest] 특성 → (core, playtest)", classify({"title": "옹골참 [Playtest]", "tags": [], "source": {"file": "db/abilities.csv"}}) == ("core", "playtest"))
    check("classify: 폴리곤 서플리먼트 단위 → (polygon, None)", classify({"title": "폴리곤 쇼크", "tags": [], "source": {"file": "supp-polygon.md"}}) == ("polygon", None))
    check("base_id/base_name: 접미사·표식 제거", base_id("ability/옹골참-playtest") == "ability/옹골참" and base_name("옹골참 [Playtest]") == "옹골참")
    # 2. core 프로필: 홈브류 기술 125개·플레이테스트 특성 제외, 코어판 유지
    rc = Rules(root, ruleset="core")
    check("core: 홈브류 기술 125개 전부 제외, 눈보라 코어판은 유지", len(rc.excluded_moves) == 125 and "move/눈보라-홈브류" in rc.excluded_moves and "move/눈보라" not in rc.excluded_moves, len(rc.excluded_moves))
    import json as _json
    pt_names = {a["name"] for a in _json.load(open(os.path.join(root, "output/entities/abilities.json"), encoding="utf-8")) if "Playtest" in a["name"]}
    n_pt = sum(1 for k in rc.excluded_abilities if "Playtest" in k)
    check(f"core: 플레이테스트 특성 전부 제외 (이름 {len(pt_names)}종)", n_pt == len(pt_names) and len(pt_names) >= 130, n_pt)
    e = Engine(rc)
    a, t = make(rc, "pokemon/archie"), make(rc, "pokemon/oddish-2")
    d = e.use_move(a, t, "move/폴리곤-쇼크")
    check("core: 제외된 기술 사용 시 거부(0) + 로그", d == 0 and any("제외된 기술" in l for l in e.log_lines))
    # 3. homebrew 프로필: 눈보라 → 눈보라 [홈브류] 치환
    rh = Rules(root, ruleset="homebrew")
    check("homebrew: 눈보라 코어판 → 홈브류판 치환표", rh.resolve_move("move/눈보라") == "move/눈보라-홈브류" and rh.resolve_move("move/버티기") == "move/버티기-홈브류", rh.move_alias)
    eh = Engine(rh, 2)
    eh.grid = Grid(12, 8)
    ah, th = make(rh, "pokemon/archie", pos=(1, 1)), make(rh, "pokemon/oddish-2", pos=(4, 1))
    # Preserve the original example sheets. Observe their actual one-cell bodies
    # and supply the complete on-field group to the native ranged Blast path.
    for actor in (ah, th):
        eh.gm.add_combatant(actor)
        prepare_body(eh, actor, size="소형", offsets=[(0, 0)],
                     reason="ruleset fixture observes the two small example Pokemon on its grid")
    eh.gm.set_move(ah, "move/눈보라", reason="ruleset fixture explicitly grants its selected test move")
    eh.use_move_on(ah, th, "move/눈보라", [ah, th], aim=th.pos)
    check("homebrew: use_move 가 치환을 로그에 남기고 홈브류판(17+ 얼음)으로 판정", any("변형판 대체" in l and "눈보라 [홈브류]" in l for l in eh.log_lines))
    # 4. playtest 프로필: 특성 이름 치환 (옹골참 → 옹골참 [Playtest]: 일격 면역 + 피해 상한)
    rp = Rules(root, ruleset="playtest")
    check("playtest: 특성 치환표에 옹골참 → 옹골참 [Playtest]", rp.ability_alias.get("옹골참") == "옹골참 [Playtest]", rp.ability_alias.get("옹골참"))
    ep = Engine(rp)
    cp = make(rp, "pokemon/oddish-2", abilities=["옹골참"])
    ep.register_abilities(cp)
    check("playtest: 등록 시 플레이테스트판 효과(피해 상한 max_hp/2) 적용 + 로그", cp.damage_cap is not None and any("변형판 대체" in l for l in ep.log_lines), cp.damage_cap)
    rc2 = Rules(root, ruleset="core")
    cc = make(rc2, "pokemon/oddish-2", abilities=["옹골참"])
    Engine(rc2).register_abilities(cc)
    check("core: 같은 전투원은 코어판 옹골참(피해 상한 없음)", cc.damage_cap is None)
    # 5. 단위 버전 선택: 포획률 구판
    rl = Rules(root, ruleset="legacy-capture")
    m_new, m_old = Rules(root).mech("pokemon/capture-rate"), rl.mech("pokemon/capture-rate")
    sup = Rules(root).mech("pokemon/capture-rate")["_superseded_version"]
    check("legacy-capture: mech 가 _superseded_version 필드로 덮인 버전을 돌려줌", m_old.get("_version") == "_superseded_version" and all(m_old.get(k) == v for k, v in sup.items()) and m_new.get("_version") is None)
    # 6. exclude_units (no-ohko) / 기본값 all
    rn = Rules(root, ruleset="no-ohko")
    check("no-ohko: 일격 기술 4종 + 자폭 2종 제외", all(x in rn.excluded_moves for x in ("move/절대영도", "move/가위자르기", "move/뿔드릴", "move/땅가르기", "move/자폭", "move/대폭발")))
    ra = Rules(root)
    # Source anchors: abilities.csv record492 has conflicting Korean/English
    # markers; poke-edges.csv records64/65 lack a marker under 기타/홈브류.
    expected_holds = {
        "ability/옹골참-홈브류-2": "conflicting_variant_markers:playtest,홈브류",
        "poke_edge/시야-넓히기": "unknown_variant_lineage:기타/홈브류",
        "poke_edge/쌍두스위퍼": "unknown_variant_lineage:기타/홈브류",
    }
    held = {}
    for uid in expected_holds:
        try:
            ra.selection.resolve(uid)
        except UnresolvedRuleSelection as exc:
            held[uid] = exc.candidates
    ordinary_allowed = ["move/눈보라", "move/눈보라-홈브류", "ability/가시", "ability/터보블레이즈-playtest"]
    # Same mixed section, but these rows explicitly identify their edition.
    explicit_homebrew = ["poke_edge/언어-학습", "poke_edge/탑승-훈련", "poke_edge/잠재력-발견-1", "poke_edge/타임캡슐"]
    allowed_ids = ordinary_allowed + explicit_homebrew
    check("기본값(all): 실제 출처 충돌만 보류하고 명시된 정상 판본은 허용",
          set(held) == set(expected_holds)
          and all(any(expected_holds[uid] in reason for reason in held[uid]) for uid in expected_holds)
          and all(ra.selection.resolve(uid) == uid for uid in allowed_ids)
          and not ra.move_alias and not ra.ability_alias, held)
    # 7. 직접 만든 프로필 / 도구
    rf = RuleFilter({"sources": "*", "variants": "*", "exclude_tags": ["homebrew"]}, "custom")
    ok, why = rf.allows({"id": "move/x", "title": "x", "tags": ["move", "homebrew"], "source": {"file": "db/moves.csv"}})
    check("custom 프로필: exclude_tags 로 거부", not ok and why == "exclude_tags")
    st = filter_db(root, "core")
    check("filter_ruleunits core: 유지+제외 = 전체, 파일 생성", st["kept"] + st["excluded"] == st["total"] and os.path.exists(os.path.join(root, "output/ruleunits.core.jsonl")), st)
    st2 = filter_db(root, "all", write=False)
    with open(os.path.join(root, "output/ruleunits.jsonl"), encoding="utf-8") as handle:
        source_units = [_json.loads(line) for line in handle if line.strip()]
    kept_all, excluded_all, aliases_all = RuleFilter.load(root, "all").split(source_units)
    held_reasons = {unit["id"]: reason for unit, reason in excluded_all}
    expected_reasons = {uid: "unresolved:" + reason for uid, reason in expected_holds.items()}
    kept_ids = {unit["id"] for unit in kept_all}
    expected_dangling = sum(1 for unit in kept_all for ref in unit.get("refs") or []
                            if ref.get("to") in expected_holds)
    check("filter_ruleunits all: 원문 근거의 보류 ID·사유 및 허용 단위·참조 집계",
          held_reasons == expected_reasons
          and set(allowed_ids) <= kept_ids and not aliases_all
          and st2["kept"] + st2["excluded"] == st2["total"]
          and st2["excluded"] == len(expected_holds)
          and st2["dangling"] == expected_dangling, held_reasons)
    check("filter_ruleunits core: 끊어진 refs 를 센다(학습 데이터 → 홈브류 기술 등)", isinstance(st["dangling"], int) and st["dangling"] >= 0, st["dangling"])

    passed = sum(1 for _, ok, _ in res if ok)
    lines = ["# 룰셋 필터 테스트 (자동 생성)", "", f"**{passed}/{len(res)} 통과**", "", "| # | 규칙 | 결과 | 비고 |", "|---|---|---|---|"]
    for i, (n, ok, d) in enumerate(res, 1):
        lines.append(f"| {i} | {n} | {'PASS' if ok else 'FAIL'} | {str(d)[:80]} |")
    open(os.path.join(root, "output/ruleset-tests.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return passed == len(res)


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
