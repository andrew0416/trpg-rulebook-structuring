"""아이템·재주·엣지·몬스터볼 테스트: 지니는 도구 패시브(깁스·부스터·손톱·고글), 소모 아이템(상처약·해독제·기력의조각·플러스파워·타우린), 볼 보정(네트볼·힐볼·퀵볼), 재주 등록(상시·발동조건·수동), 엣지 기술 부여.
  python -X utf8 -I engine/test_items.py <root>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from builder import build_pokemon, build_trainer  # noqa: E402
from engine import Combatant, Engine, Rules  # noqa: E402
import items as ITEMS  # noqa: E402
import turn as TURN  # noqa: E402


def mk(r, species, level, **kw):
    # This suite explicitly uses the available Playtest identity under the all profile.
    # The bare learnset name has no corresponding core definition; do not add a fallback.
    if species == "뚜벅쵸" and "abilities" not in kw:
        kw["abilities"] = ["엽록소 [Playtest]"]
    return Combatant(r, build_pokemon(r, species, level, **kw))


def run(root):
    res = []

    def check(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    r = Rules(root)
    check("DB: 아이템 mech 표(규칙 기반+LLM) 로드", len(r.items_mech) > 600 and len(r.items_llm) > 300, f"{len(r.items_mech)}/{len(r.items_llm)}")
    check("DB: 재주·엣지 mech 표 로드", len(r.feats_mech) > 600 and len(r.feats_llm) > 500 and len(r.edges_llm) > 80, f"{len(r.feats_mech)}/{len(r.feats_llm)}/{len(r.edges_llm)}")
    effs, h = r.item_effects("불꽃깁스")
    check("item_effects: 규칙 기반 full 이 우선 (불꽃깁스 → damage_reduction 15 vs_type 불꽃)", effs and effs[0]["type"] == "damage_reduction" and effs[0].get("vs_type") == "불꽃" and h["confidence"] == "auto", effs)
    effs2, h2 = r.item_effects("선제공격손톱")
    check("item_effects: 규칙 기반 none 이면 LLM 초안 (선제공격손톱 → initiative_mod +10, llm)", effs2 and effs2[0]["type"] == "initiative_mod" and effs2[0]["value"] == 10 and h2["confidence"] == "llm", effs2)
    # 1. 깁스: 타입 한정 피해 감소
    e = Engine(r, 3)
    a = mk(r, "브케인", 20, strategy="special")
    t0, t1 = mk(r, "뚜벅쵸", 13), mk(r, "뚜벅쵸", 13, item="불꽃깁스")
    for actor in (a, t0, t1):
        e.gm.add_combatant(actor)
    d0 = e.roll_damage(a, t0, r.move("move/불꽃세례"), set_damage=True)
    d1 = e.roll_damage(a, t1, r.move("move/불꽃세례"), set_damage=True)
    check("불꽃깁스: 불꽃 피해에만 DR 15 (뚜벅쵸 약점 ×1.5 전 감산)", d0 - d1 >= 15 and any("도구 피해 감소 15" in l for l in e.log_lines), f"{d0} → {d1}")
    dn0 = e.roll_damage(a, t0, r.move("move/몸통박치기"), set_damage=True) if "move/몸통박치기" in r.moves else 0
    dn1 = e.roll_damage(a, t1, r.move("move/몸통박치기"), set_damage=True) if "move/몸통박치기" in r.moves else 0
    check("불꽃깁스: 노말 기술에는 감소 없음", dn0 == dn1, f"{dn0} {dn1}")
    # 2. 타입 부스터: 불꽃 +5
    a2 = mk(r, "브케인", 20, strategy="special", item="불꽃부스터")
    e.gm.add_combatant(a2)
    d2 = e.roll_damage(a2, t0, r.move("move/불꽃세례"), set_damage=True)
    check("불꽃부스터: 불꽃 기술 피해 굴림 +5 (×1.5 → +7)", d2 - d0 in (7, 8), f"{d0} → {d2}")
    d2n = e.roll_damage(a2, t0, r.move("move/몸통박치기"), set_damage=True) if "move/몸통박치기" in r.moves else dn0
    check("불꽃부스터: 다른 타입 기술엔 없음", d2n == dn0, f"{dn0} {d2n}")
    # 3. 선제공격손톱: 이니셔티브 +10, 예리한손톱: 치명타 범위 +1
    s = mk(r, "뚜벅쵸", 13, item="선제공격손톱")
    # Playtest Chlorophyll's actual weather reader requires real world actors.
    e.gm.add_combatant(s)
    # This oracle compares +10 with the same-speed unboosted actor only.
    # The unrelated third actor has initiative15, tying s and requiring a GM decision.
    order = e.initiative([s, t0])
    assert order is not None, e.log_lines
    check("선제공격손톱: 이니셔티브 +10 → 같은 스피드의 뚜벅쵸보다 먼저, 로그에 +10", order.index(s) < order.index(t0) and s.initiative_bonus == 10 and any("+10" in l for l in e.log_lines[-1:]), [c.name for c in order])
    k = mk(r, "브케인", 20, item="예리한손톱")
    e.gm.add_combatant(k)
    check("예리한손톱: 치명타 범위 +1 (crit_range delta 등록)", ITEMS.crit_delta(k, r.move("move/불꽃세례")) == 1)
    # 4. 고고고글: 모래바람 면역
    g = mk(r, "뚜벅쵸", 13, item="고고고글")
    e4 = Engine(r)
    e4.gm.add_combatant(g)
    e4.gm.set_weather("sandstorm", rounds=3, reason="item fixture observes a three-round sandstorm")
    e4.start_of_turn(g)
    check("고고고글: 모래바람 틱 피해 면역", g.hp == g.max_hp and any("피해 면역 (도구)" in l for l in e4.log_lines), f"{g.hp}/{g.max_hp}")
    # 5. 소모 아이템
    e5 = Engine(r, 1)
    tr = Combatant(r, build_trainer(r, "실바나", 5, {"hp": 10, "atk": 5, "def": 5, "spa": 5, "spd": 5, "spe": 5}, items={"상처약": 1, "해독제": 1, "기력의조각": 1, "플러스파워": 1, "타우린": 7}))
    p = mk(r, "뚜벅쵸", 13)
    e5.gm.add_combatant(tr)
    e5.gm.add_combatant(p)
    p.hp -= 30
    hp0 = p.hp
    e5.use_item(tr, "상처약", p)
    check("상처약: 체력 20 회복", p.hp == min(p.max_hp, hp0 + 20), f"{hp0} → {p.hp}")
    check("재고: 상처약 1개 소모 → 0", tr.spec["items"]["상처약"] == 0)
    e5.use_item(tr, "상처약", p)
    check("재고 없으면 사용 불가 (로그)", any("재고 없음" in l for l in e5.log_lines))
    p.conditions.add("독")
    e5.use_item(tr, "해독제", p)
    check("해독제: 독 치료", "독" not in p.conditions)
    p.hp = 0; p.conditions.add("기절")
    e5.use_item(tr, "기력의조각", p)
    check("기력의조각: 기절 해제, 체력 20", p.hp == 20 and "기절" not in p.conditions, p.hp)
    e5.use_item(tr, "플러스파워", p)
    check("플러스파워: 공격 +2 전투단계", p.stages["atk"] == 2)
    atk0 = p.stats["atk"]
    for _ in range(7):
        e5.use_item(tr, "타우린", p)
    check("타우린: 기본 공격 +1, 영양제 한도 6개 (7번째는 무효)", p.stats["atk"] == atk0 + 6 and any("한도" in l for l in e5.log_lines), f"{atk0} → {p.stats['atk']}")
    tr.spec["items"]["상처약"] = 1
    TURN.reset_budget(e5, tr)
    e5.use_item(tr, "상처약", p)
    check("재고 있는 아이템 사용은 기본 행동을 소비 (예산 켜졌을 때)", tr.budget["standard"] == 0)
    # 6. 몬스터볼 보정
    e6 = Engine(r, 5); e6.round_no = 1
    w = mk(r, "꼬부기", 10, wild=True)
    for actor in (tr, p, w):
        e6.gm.add_combatant(actor)
    mod, why = ITEMS.ball_modifier(e6, "네트볼", tr, w)
    check("네트볼: 물 타입에 +4", mod == 4, why)
    mod2, _ = ITEMS.ball_modifier(e6, "네트볼", tr, p)
    check("네트볼: 풀/독 뚜벅쵸에는 +0", mod2 == 0)
    e6.round_no = 4
    mod3, _ = ITEMS.ball_modifier(e6, "퀵볼", tr, w)
    mod4, _ = ITEMS.ball_modifier(e6, "타이머볼", tr, w)
    check("퀵볼 4라운드 +0 / 타이머볼 4라운드 +2", mod3 == 0 and mod4 == 2, f"{mod3} {mod4}")
    check("하이퍼볼 +3 (에라타 환산), 마스터볼 20", ITEMS.ball_modifier(e6, "하이퍼볼", tr, w)[0] == 3 and ITEMS.ball_modifier(e6, "마스터볼", tr, w)[0] == 20)
    w.hp = 1
    e6.start_of_turn(tr)  # A new turn: the earlier potion already spent the standard action.
    tr.spec.setdefault("items", {}).update({"마스터볼": 1, "힐볼": 1})  # Actual owned capture devices.
    ok = e6.throw_ball(tr, w, "마스터볼")
    check("throw_ball(볼 종류): 마스터볼로 포획, 잡은 종이 트레이너 기록에", ok and w.captured and w.spec["species"] in tr.spec["caught_species"], e6.log_lines[-2:])
    w2 = mk(r, "꼬부기", 10, wild=True); w2.hp = 1; w2.conditions.add("독")
    e6.gm.add_combatant(w2)
    e6.start_of_turn(tr)
    e6.throw_ball(tr, w2, "힐볼", fixed_accuracy=20, fixed_capture=20)
    check("힐볼: 원문대로 체력 회복, 상태이상은 유지", w2.captured and w2.hp == w2.max_hp and "독" in w2.conditions, f"{w2.captured} {w2.hp}/{w2.max_hp}")
    f = mk(r, "꼬부기", 10, wild=True); f.hp = 0; f.conditions.add("기절")
    e6.gm.add_combatant(f)
    check("기절한 포켓몬은 포획 불가", not e6.throw_ball(tr, f, "몬스터볼") and any("포획 불가" in l for l in e6.log_lines))
    cat = ITEMS.ball_catalog(r)
    check("볼 목록: DB 의 몬스터볼 50종 이상, 조건부 볼 표시", len(cat) >= 50 and any(b["conditional"] for b in cat), len(cat))
    # 7. 재주·엣지
    e7 = Engine(r, 2)
    tr2 = Combatant(r, build_trainer(r, "마야", 10, {"hp": 10, "atk": 6, "def": 5, "spa": 5, "spd": 5, "spe": 6}, extra={"feats": ["자각", "깡다구", "빠른 반사신경"], "edges": ["기본 무술", "호감인"]}))
    pk = mk(r, "뚜벅쵸", 13, extra={"trainer": "마야"})
    import enduring_awareness as AWARENESS
    import effects_ext as EXT
    tr2.spec.update(id="item-test-trainer", classes=[AWARENESS.ENDURING], skills={"육상":3,"집중":3})
    witnesses = [pk, mk(r,"꼬부기",10), mk(r,"꼬마돌",10)]
    for i, pokemon in enumerate(witnesses):
        pokemon.spec.update(id="item-test-pokemon-"+str(i),trainer_id=tr2.spec["id"])
        pokemon.abilities = ["두꺼운지방"]
    for actor in (tr2, *witnesses):
        e7.gm.add_combatant(actor)
    e7.gm.confirm_awareness(tr2,[{"pokemon":pokemon,"ability":"두꺼운지방","defensive_reason":"incoming elemental damage defense"} for pokemon in witnesses],reason="source-qualified item integration fixture")
    e7.register_abilities(pk)
    e7.register_abilities(tr2)
    check("재주 자각: 실제 소유 포켓몬 내성 +2 한 번", EXT.save_dc(e7,pk,"마비",11)==9 and pk.save_mod==0, EXT.save_dc(e7,pk,"마비",11))
    check("엣지 기본 무술·호감인: 트레이너가 바위깨기·초롱초롱눈동자 기술 획득", r.move_id("바위깨기") in tr2.moves and r.move_id("초롱초롱눈동자") in tr2.moves, tr2.moves[:3])
    manual = [x for x in tr2.registry if x.get("type") == "feat_manual"]
    check("재주 깡다구: 발동조건('대규모 데미지를 받거나…')은 파서 밖 → 수동 발동 레지스트리", any(x["name"] == "깡다구" for x in manual) or any(a.get("name") == "깡다구" for a in tr2.ability_triggers), [x["name"] for x in manual])
    foe = mk(r, "꼬마돌", 20, wild=True)
    e7.gm.add_combatant(foe)
    mettle_before = dict(foe.stages)
    mettle_actor_before = (tr2.hp, dict(tr2.stages), dict(tr2.budget) if getattr(tr2, "budget", None) is not None else None,
                           list(getattr(tr2, "_action_history", [])), e7.rng.getstate())
    mettle_result = e7.manual_feat(tr2, "깡다구", foe)
    # The first unsupported resistance consumer holds; its dependent suffix is
    # deferred instead of being dispatched and counted as a second failure.
    # Source acceptance remains open in data/test-oracle-findings.json.
    mettle_states = [outcome.status for outcome in mettle_result.outcomes]
    mettle_actor_after = (tr2.hp, dict(tr2.stages), dict(tr2.budget) if getattr(tr2, "budget", None) is not None else None,
                          list(getattr(tr2, "_action_history", [])), e7.rng.getstate())
    check("공격 문맥 없는 깡다구 수동 호출: 보류, 성공 실행·상태 변경 없음",
          mettle_result == (0, 1) and mettle_states == ["unsupported_execution", "deferred_suffix"]
          and foe.stages == mettle_before and mettle_actor_after == mettle_actor_before,
          {"result": mettle_result, "states": mettle_states, "stages": foe.stages})
    check("재주 빠른 반사신경: 특성 '회피' 부여 (DB 에 있으면)", ("회피" in tr2.abilities) or not any(n.startswith("회피") for n in r.ability_effects), tr2.abilities)
    effs_f, hf = r.feat_effects("feat/엘리트-트레이너")
    check("feat_effects: id 로도 찾고 confidence 표기", effs_f is not None and hf["confidence"] in ("llm", "auto", "auto:partial"), hf.get("confidence"))

    lines = ["# 아이템·재주·볼 테스트 (자동 생성)", "", f"{sum(1 for _, ok, _ in res if ok)}/{len(res)} 통과", "", "| # | 검사 | 결과 | 비고 |", "|---|---|---|---|"]
    for i, (name, ok, detail) in enumerate(res, 1):
        lines.append(f"| {i} | {name} | {'PASS' if ok else 'FAIL'} | {str(detail)[:100]} |")
    open(os.path.join(root, "output/item-tests.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return all(ok for _, ok, _ in res)


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
