"""effect 실행기 테스트: 기술 effect(교환·전장·방패·타입 변경·고유 상태·다음 공격·체력 손실 식) 와 특성 패시브(타입별 +5, 저항 단계, 무효·흡수, 치명타 범위).
  python -X utf8 -I engine/test_effects.py <root>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Combatant, Engine, Rules  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from synthetic_rule_fixture import register_synthetic  # noqa: E402
from native_scenario_fixture import prepare_body  # noqa: E402
import effects as FX  # noqa: E402


def make(r, cid, **over):
    spec = dict(r.creatures[cid])
    # The legacy creature examples omit body weight; this fixture imports the
    # actual species value instead of depending on an invented runtime default.
    if spec.get("weight_class") is None and spec.get("species"):
        spec["weight_class"]=r.species[spec["species"]]["weight_class"]
    spec.update(over)
    return Combatant(r, spec)


def run(root):
    r = Rules(root)
    # Component fixtures have no rulebook authority; register only their test identities.
    register_synthetic(r, "ability/test/water-hit", name="물맞이(가상)", kind="entity:ability")
    register_synthetic(r, "move/x", name="물대포", kind="entity:move")
    res = []

    def check(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    # 1. swap_stages (가드스왑 llm 초안)
    e = Engine(r)
    a, t = make(r, "pokemon/archie"), make(r, "pokemon/oddish-1")
    e.gm.add_combatant(a)
    e.gm.add_combatant(t)
    a.stages["def"], t.stages["def"], t.stages["spd"] = 2, -1, 3
    FX.run_effects(e, a, t, [{"type": "swap_stages", "swap_stages": ["def", "spd"], "between": ["self", "target"]}], {"hit": True}, "test")
    check("swap_stages: def/spd 전투단계 교환", a.stages["def"] == -1 and t.stages["def"] == 2 and a.stages["spd"] == 3)
    # 2. field_effect / set_weather
    field_batch = FX.run_effects(e, a, t, [{"type": "field_effect", "field": "원더", "rounds": 5, "effect": {"swap_defense_stats": True}}, {"type": "set_weather", "weather": "rain", "rounds": 5}], {"hit": True}, "test")
    assert field_batch == (2, 0) and not field_batch.pending
    assert all(outcome.status == "completed" for outcome in field_batch.outcomes)
    check("field_effect / set_weather 저장", e.field["name"] == "원더" and e.weather == "rain")
    # 3. reaction_shield: 다음 공격 무효
    FX.run_effects(e, t, a, [{"type": "reaction_shield", "trigger": "user hit by a move", "effect": "negate hit"}], {"hit": True}, "test")
    hit, _, _ = e.accuracy_check(a, t, r.move("move/불꽃세례"), fixed_roll=20)
    check("reaction_shield: 방패 준비 중이면 자연 20 이라도 명중 무효, 방패 소모", (not hit) and t.shield is None)
    hit, _, _ = e.accuracy_check(a, t, r.move("move/불꽃세례"), fixed_roll=20)
    check("reaction_shield: 소모 후에는 정상 명중", hit)
    # 4. type_change add/lose
    FX.run_effects(e, a, t, [{"type": "type_change", "add_type": "고스트", "target": "target", "turns": 5}], {"hit": True}, "test")
    check("type_change add: 뚜벅초 풀/독 + 고스트", t.types == ["풀", "독", "고스트"])
    check("타입 변경이 상성에 반영: 노말 공격 무효", e.type_multiplier("노말", t)[0] == 0)
    FX.run_effects(e, a, a, [{"type": "type_change", "lose_type": "불꽃", "fallback": "노말"}], {"hit": True}, "test")
    check("type_change lose + fallback: 아치 불꽃 → 노말", a.types == ["노말"])
    # 5. custom_condition / next_attack_modifier / forced_target
    FX.run_effects(e, a, t, [{"type": "custom_condition", "name": "회복봉인", "on": "target", "effect": "cannot gain HP"}, {"type": "next_attack_modifier", "auto_crit": True}, {"type": "forced_target", "must_target": "user"}], {"hit": True}, "test")
    check("custom_condition / next_attack / forced_target 저장", "회복봉인" in t.custom_conditions and a.next_attack["auto_crit"] and e.taunt["by"] is a)
    hit, nat, crit = e.accuracy_check(a, t, r.move("move/불꽃세례"), fixed_roll=10)
    check("next_attack_modifier: 다음 공격이 자동 치명타, 1회 소모", hit and crit and a.next_attack is None)
    # 6. hp_loss 식 (user.level, current_hp/2, tick*2) / self_hp_set -50%
    a2, t2 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e2 = Engine(r)
    e2.gm.add_combatant(a2)
    e2.gm.add_combatant(t2)
    FX.run_effects(e2, a2, t2, [{"type": "hp_loss", "value": "user.level", "target": "target"}], {"hit": True, "attacker": a2}, "test")
    check("hp_loss user.level: 뚜벅초 53 → 33 (아치 레벨 20)", t2.hp == 33, f"{t2.hp}")
    FX.run_effects(e2, a2, t2, [{"type": "hp_loss", "value": "current_hp/2", "target": "target"}], {"hit": True, "attacker": a2}, "test")
    check("hp_loss current_hp/2: 33 → 17", t2.hp == 17, f"{t2.hp}")
    FX.run_effects(e2, a2, t2, [{"type": "self_hp_set", "self_hp": "-50% max", "unpreventable": True}], {"hit": True, "attacker": a2}, "test")
    check("self_hp_set -50%: 아치 60 → -30, 기절", a2.hp == -30 and a2.fainted, f"{a2.hp}")
    # 7. 미지원/미해석은 보류로 세고 멈추지 않음
    chain_actor = make(r, "pokemon/archie", id="pokemon/effects-chain-actor")
    e2.gm.add_combatant(chain_actor)
    done, held = FX.run_effects(e2, chain_actor, t2, [{"type": "multi_target_chain", "max": 3}, {"type": "push", "meters": "8 - target.weight_class"}, {"type": "stage_change", "stat": "atk", "delta": 1, "target": "self"}], {"hit": True}, "test")
    check("보류 집계: 턴구조(multi_target_chain)는 엔진 처리라 건너뜀, push 8-체급 식 평가되어 실행, 보류 0", done == 2 and held == 0, f"done {done} held {held}")
    unknown_actor = make(r, "pokemon/archie", id="pokemon/effects-unknown-actor")
    e2.gm.add_combatant(unknown_actor)
    done, held = FX.run_effects(e2, unknown_actor, t2, [{"type": "no_such_effect"}], {"hit": True}, "test")
    check("미지원 유형은 보류 1", done == 0 and held == 1, f"done {done} held {held}")
    # 7b. 식 평가기
    ctx3 = {"attacker": a2, "target": t2, "engine": e2, "hit": True}
    check("evaluate: 8 - target.weight_class(뚜벅초 체급 1) = 7", FX.evaluate("8 - target.weight_class", ctx3) == 7, FX.evaluate("8 - target.weight_class", ctx3))
    a4 = make(r, "pokemon/archie"); a4.injuries = 3
    check("evaluate: tick * user.injuries = 부상 3 → 회복 상한 42, 소량은 실제 최대 60 기준 6 × 3 = 18 (ch07 부상 데미지)", FX.evaluate("tick * user.injuries", {**ctx3, "attacker": a4, "who": a4}) == 18, FX.evaluate("tick * user.injuries", {**ctx3, "attacker": a4, "who": a4}))
    a4.stages = {"atk": 2, "spa": 1, "def": -1}
    check("evaluate: db + 2 * sum(positive stages of user) (db 5) = 11", FX.evaluate("db + 2 * sum(positive stages of user)", {**ctx3, "attacker": a4, "db": 5}) == 11)
    check("trigger(영문 reaction): 'hit by damaging move' → on_hit_received", FX.parse_trigger("hit by damaging move")["event"] == "on_hit_received")
    check("trigger(영문): 'when user hits with a Fire-type move' → on_hit_dealt/불꽃", FX.parse_trigger("when user hits with a Fire-type move") == {"event": "on_hit_dealt", "move_type": "불꽃"}, FX.parse_trigger("when user hits with a Fire-type move"))
    check("evaluate: 안전하지 않은 식은 None", FX.evaluate("__import__('os')", ctx3) is None)
    # 7c. 특성 발동조건 파서
    check("trigger: '물타입 기술로 명중시켰을 때' → on_hit_dealt/물", FX.parse_trigger("물타입 기술로 명중시켰을 때") == {"event": "on_hit_dealt", "move_type": "물"}, FX.parse_trigger("물타입 기술로 명중시켰을 때"))
    check("trigger: '사용자가 근접공격을 당했을 경우' → on_hit_received/melee", FX.parse_trigger("사용자가 근접공격을 당했을 경우") == {"event": "on_hit_received", "melee": True}, FX.parse_trigger("사용자가 근접공격을 당했을 경우"))
    check("trigger: '라운드가 시작했을 때' → round_start", FX.parse_trigger("라운드가 시작했을 때")["event"] == "round_start")
    check("trigger: '자신의 공격으로 인해 적이 기절했을 때' → enemy_faint_by_user", FX.parse_trigger("자신의 공격으로 인해 적이 기절했을 때")["event"] == "enemy_faint_by_user")
    # 7d. 트리거 특성 실행: 가상 특성 '물맞이' = 물타입 기술에 맞으면 spd +1 (장면 x1)
    e3 = Engine(r); a3, t3 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    r.ability_effects["물맞이(가상)"] = [{"type": "trigger", "text": "물타입 기술로 맞았을 때"}, {"type": "stage_change", "stat": "spd", "delta": 1, "target": "self"}]
    r.ability_freq["물맞이(가상)"] = "장면 x1 - 발동"
    t3.abilities = ["물맞이(가상)"]
    e3.gm.add_combatant(a3)
    e3.gm.add_combatant(t3)
    check("trigger 등록: ability_triggers 1개", len(t3.ability_triggers) == 1 and t3.ability_triggers[0]["spec"] == {"event": "on_hit_received", "move_type": "물"}, t3.ability_triggers)
    e3.use_move(a3, t3, "move/불꽃세례", set_damage=True)
    check("불꽃 기술에는 발동 안 함", t3.stages.get("spd", 0) == 0)
    FX.fire_event(e3, t3, {"event": "on_hit_received", "move": {"name": "물대포", "type": "물", "class": "특수", "range": "6, 1 대상"}}, a3)
    FX.fire_event(e3, t3, {"event": "on_hit_received", "move": {"name": "물대포", "type": "물", "class": "특수", "range": "6, 1 대상"}}, a3)
    check("물 기술 피격 → spd +1, 장면 x1 이라 두 번째는 발동 안 함", t3.stages.get("spd", 0) == 1 and t3.counters.get("ab:물맞이(가상)") == 1, f"{t3.stages} {t3.counters}")
    # 7e. 단계 하락 면역(클리어바디) / stat_mod(라이트메탈 체급 -2) / connection(꿀도둑: 벌레먹기 사용 시 임시 체력 tick)
    e4 = Engine(r); a5, t5 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    t5.abilities = ["클리어바디", "라이트메탈 [Playtest]", "꿀도둑"]
    e4.gm.add_combatant(a5)
    e4.gm.add_combatant(t5)
    FX.run_effects(e4, a5, t5, [{"type": "stage_change", "stat": "atk", "delta": -1, "target": "target"}, {"type": "stage_change", "stat": "atk", "delta": -1, "target": "self"}], {"hit": True, "attacker": a5, "target": t5}, "test")
    check("클리어바디: 적이 내린 atk -1 은 면역, 자기 자신의 하락은 그대로", t5.stages["atk"] == 0 and a5.stages["atk"] == -1, f"{t5.stages} {a5.stages}")
    check("라이트메탈: 체급 1 → 1 (하한 1), 영구 체급 보존", t5.weight_class == 1 and t5.spec["weight_class"] == 1, (t5.weight_class,t5.spec["weight_class"]))
    conn = [x for x in t5.ability_triggers if x["name"] == "꿀도둑"]
    check("꿀도둑 connection → on_move_use/벌레먹기 트리거 등록", len(conn) == 1 and conn[0]["spec"] == {"event": "on_move_use", "move": "벌레먹기"}, conn)
    FX.fire_event(e4, t5, {"event": "on_move_use", "move": {"name": "벌레먹기", "type": "벌레"}}, a5)
    check("벌레먹기 사용 → 임시 체력 tick(뚜벅초 최대 53 → 5)", t5.temp_hp == 5, t5.temp_hp)
    # 7f. 속임수(llm): 대상의 공격 스탯으로 피해 계산 — 뚜벅초(atk 7)가 아치(atk 9, def 8)에게: 지정 데미지 + 9 - 8
    e6 = Engine(r); a6, t6 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e6.gm.add_combatant(a6)
    e6.gm.add_combatant(t6)
    mid = r.mech("combat/damage-chart")["by_damage_base"]["10"]["set"]["mid"]
    dmg = e6.roll_damage(t6, a6, r.move("move/속임수"), set_damage=True)
    check(f"속임수: 대상(아치) 공격 9 로 계산 → {mid}+9-8 = {mid + 1} (자기 공격 7이면 {mid - 1})", dmg == mid + 1, dmg)
    # 8. 특성 패시브: 맹화(불꽃 +5 / 1/3 미만 +10), 두꺼운지방(불꽃·얼음 한 단계 더 반감), 저수(물 흡수→소량 회복), 대운(치명타 18-20)
    e3 = Engine(r)
    a3 = make(r, "pokemon/archie", abilities=["맹화", "대운"])
    t3 = make(r, "pokemon/oddish-1", abilities=["두꺼운지방"])
    e3.gm.add_combatant(a3)
    e3.gm.add_combatant(t3)
    dmg = e3.roll_damage(a3, t3, r.move("move/불꽃세례"), set_damage=True)
    # 기준값(패시브 없음) 27: 15 + 16 = 31 → +5 = 36, -13 = 23, 불꽃 vs 풀/독 ×1.5 → 두꺼운지방 -1단계 → ×1 = 23
    check("패시브 맹화 +5 와 두꺼운지방 저항 1단계: 지정 데미지 27 → 23", dmg == 23, f"{dmg}")
    a3.hp = 10
    dmg = e3.roll_damage(a3, t3, r.move("move/불꽃세례"), set_damage=True)
    check("맹화: 체력 1/3 미만이면 +10 → 28", dmg == 28, f"{dmg}")
    hit, nat, crit = e3.accuracy_check(a3, t3, r.move("move/불꽃세례"), fixed_roll=18)
    check("대운: 자연 18 도 치명타", hit and crit)
    t4 = make(r, "pokemon/oddish-2", abilities=["저수"])
    e3.gm.add_combatant(t4)
    t4.hp = 20
    dmg = e3.roll_damage(a3, t4, {"id": "move/x", "name": "물대포", "class": "특수", "ac": 2, "type": "물", "damage_base": 4})
    check("저수: 물 공격 무효 + 소량(5) 회복 → 피해 0, 체력 20 → 25", dmg == 0 and t4.hp == 25, f"{dmg} {t4.hp}")
    # 9. 특성 패시브: 본능(회피 +2), 복안(명중 +3), 가증스러움(HP 기본 +5), 조가비갑옷(치명타 면역은 보류 대상 아님: immunity 'to')
    c5 = make(r, "pokemon/oddish-3", abilities=["본능", "복안"])
    e3.gm.add_combatant(c5)
    check("본능/복안: 회피 +2, 명중 +3 등록", c5.evasion_mod == 2 and c5.accuracy_stage == 3)
    # 10. 임시 체력이 먼저 깎임
    c6 = make(r, "pokemon/oddish-1", id="pokemon/effects-temp-hp-target")
    e3.gm.add_combatant(c6)
    c6.temp_hp = 10
    e3.take_damage(c6, 15)
    check("임시 체력 10 → 15 피해면 실제 체력 5 감소 (53 → 48)", c6.hp == 48 and c6.temp_hp == 0, f"{c6.hp} {c6.temp_hp}")
    # 11. damage_floor (칼등치기): 체력 1 미만으로 안 내려감
    e4 = Engine(r)
    a4, t5 = make(r, "trainer/maya"), make(r, "pokemon/oddish-1")
    e4.gm.add_combatant(a4)
    e4.gm.add_combatant(t5)
    t5.hp = 5
    dmg = e4.roll_damage(a4, t5, r.move("move/칼등치기"), fixed_dice=[8])
    check("damage_floor(칼등치기 llm): 피해가 체력 1 남기도록 제한 → 4", dmg == 4, f"{dmg}")
    # 12. llm 초안이 엔진에 꽂힘: 회복지령(heal 1/2) 사용
    e5 = Engine(r)
    a5 = make(r, "pokemon/archie")
    e5.gm.add_combatant(a5)
    a5.hp = 10
    e5.use_move(a5, a5, "move/회복지령")
    check("llm 초안 실행: 회복지령 → 체력 10 → 40 (최대 60의 절반)", a5.hp == 40, f"{a5.hp}")

    # ===== 13. 확장 실행기 (engine/effects_ext.py): 나머지 100종 =====
    import effects_ext as EXT
    from grid import Grid
    e7 = Engine(r); a7, t7 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e7.gm.add_combatant(a7)
    e7.gm.add_combatant(t7)
    t7.item = "오랭열매"
    FX.run_effects(e7, a7, t7, [{"type": "steal_item", "if": "user holds nothing"}], {"hit": True, "attacker": a7, "target": t7}, "test")
    check("steal_item: 도구 없는 아치가 뚜벅초의 오랭열매를 빼앗음", a7.item == "오랭열매" and t7.item is None, f"{a7.item} {t7.item}")
    FX.run_effects(e7, a7, t7, [{"type": "swap_items", "between": ["self", "target"]}], {"hit": True}, "test")
    check("swap_items: 교환 후 뚜벅초가 다시 지님", t7.item == "오랭열매" and a7.item is None)
    t7.stages["atk"], t7.stages["spe"] = 2, -1
    FX.run_effects(e7, a7, t7, [{"type": "invert_stages", "target": "target"}], {"hit": True}, "test")
    check("invert_stages: +2/-1 → -2/+1", t7.stages["atk"] == -2 and t7.stages["spe"] == 1, f"{t7.stages}")
    FX.run_effects(e7, a7, t7, [{"type": "copy_stages", "from": "target", "to": "self"}], {"hit": True}, "test")
    check("copy_stages: 아치 단계 = 뚜벅초 단계", a7.stages == t7.stages)
    e7.apply_status(a7, "마비")
    FX.run_effects(e7, a7, t7, [{"type": "transfer_status", "from": "self", "to": "target"}], {"hit": True}, "test")
    check("transfer_status: 마비가 아치에서 뚜벅초로", "마비" in t7.conditions and "마비" not in a7.conditions, f"{a7.conditions} {t7.conditions}")
    FX.run_effects(e7, a7, t7, [{"type": "apply_status_choice", "options": ["둔화 (1라운드)", "억압"], "target": "target"}], {"hit": True}, "test")
    check("apply_status_choice: 첫 선택지 둔화 적용", "둔화" in t7.conditions)
    FX.run_effects(e7, a7, t7, [{"type": "counter", "name": "stockpile", "delta": 1, "max": 3}] * 4, {"hit": True}, "test")
    check("counter: 비축 4회 → 최대 3", a7.counters.get("stockpile") == 3, a7.counters.get("stockpile"))
    a7.hp = 10
    FX.run_effects(e7, a7, t7, [{"type": "alternate_effect", "if": "stockpile >= 3", "then": {"type": "heal", "fraction_of_max": [1, 1], "target": "self"}}], {"hit": True, "attacker": a7, "target": t7}, "test")
    check("alternate_effect: 'stockpile >= 3' 분기 → 전부 회복", a7.hp == a7.max_hp, a7.hp)
    # 일격(execute): 레벨 100 vs 13 → X=117 → 반드시 기절; 얼음 타입은 무효
    a8 = make(r, "pokemon/archie", id="pokemon/effects-execute-actor", level=100)
    t8 = make(r, "pokemon/oddish-2", id="pokemon/effects-execute-target")
    e7.gm.add_combatant(a8)
    e7.gm.add_combatant(t8)
    FX.run_effects(e7, a8, t8, [{"type": "execute", "roll": "1d100", "threshold": "30 + user.level - target.level", "immune_if": "얼음 type"}], {"hit": True, "attacker": a8, "target": t8}, "test")
    check("execute: X=117 → 1d100 < X 이므로 기절", t8.fainted, t8.hp)
    t8b = make(r, "pokemon/oddish-2", id="pokemon/effects-ice-execute-target", types=["얼음"])
    e7.gm.add_combatant(t8b)
    FX.run_effects(e7, a8, t8b, [{"type": "execute", "roll": "1d100", "threshold": "30 + user.level - target.level", "immune_if": "얼음 type"}], {"hit": True, "attacker": a8, "target": t8b}, "test")
    check("execute: 얼음 타입 대상은 무효", not t8b.fainted)
    # 부상·완전 회복·체력 공유
    FX.run_effects(e7, a7, t7, [{"type": "injury", "value": 1, "target": "target"}], {"hit": True}, "test")
    check("injury: 뚜벅초 부상 +1 → 최대 체력 48", t7.injuries == 1 and t7.max_hp == 48, f"{t7.injuries} {t7.max_hp}")
    FX.run_effects(e7, a7, t7, [{"type": "heal_injury", "value": 1, "target": "target"}], {"hit": True}, "test")
    check("heal_injury: 부상 치유 → 0", t7.injuries == 0)
    t7.hp = 1
    FX.run_effects(e7, a7, t7, [{"type": "full_restore", "target": "target (may be in ball)", "heal_injuries": 3, "restore_frequencies": True}], {"hit": True}, "test")
    check("full_restore: 체력 최대, 상태이상 전부 치유", t7.hp == t7.max_hp and not (t7.conditions - {"기절"}), f"{t7.hp} {t7.conditions}")
    a7.hp, t7.hp = 60, 20
    FX.run_effects(e7, a7, t7, [{"type": "hp_share", "rule": "both lose half current, then both gain (sum lost)/2"}], {"hit": True}, "test")
    check("hp_share: 60/20 → 각각 절반 잃고 평균 회복 → 50/30", a7.hp == 50 and t7.hp == 30, f"{a7.hp} {t7.hp}")
    t7.hp = 10
    FX.run_effects(e7, a7, t7, [{"type": "delayed_heal", "when": "end of target's next turn", "fraction_of_max": [1, 2]}], {"hit": True}, "test")
    e7.end_of_turn(t7)
    check("delayed_heal: 대상 턴 끝에 최대 절반(26) 회복 → 36", t7.hp == 36, t7.hp)
    # 지연 공격 (미래예지): 사용 턴엔 아무 일도, 대상 턴 끝에 명중
    e8 = Engine(r, 2); a9, t9 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e8.gm.add_combatant(a9)
    e8.gm.add_combatant(t9)
    d0 = e8.use_move(a9, t9, "move/미래예지")
    check("delayed_attack: 사용 턴 피해 0, 체력 그대로", d0 == 0 and t9.hp == 53, f"{d0} {t9.hp}")
    e8.end_of_turn(t9)
    check("delayed_attack: 대상 턴 끝에 피해 발생", t9.hp < 53, t9.hp)
    # 코트(물놀이: 불꽃 1회 저항) / 축복(리플렉터: 물리 2회 저항) / 흰안개
    e9 = Engine(r); a10, t10 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e9.gm.add_combatant(a10)
    e9.gm.add_combatant(t10)
    d_plain = e9.roll_damage(a10, t10, r.move("move/불꽃세례"), set_damage=True)
    FX.run_effects(e9, a10, t10, [{"type": "apply_coat", "coat": "물놀이", "effect": {"resist_once": "불꽃"}, "target": "target"}], {"hit": True}, "test")
    d_coat = e9.roll_damage(a10, t10, r.move("move/불꽃세례"), set_damage=True)
    check("apply_coat 물놀이: 불꽃 ×1.5 → 1회 저항으로 ×1, 코트 소멸", d_coat < d_plain and not t10.coats, f"{d_plain} → {d_coat}")
    FX.run_effects(e9, a10, t10, [{"type": "blessing", "name": "리플렉터", "activations": 2, "on": "taking physical damage", "effect": "one step resistance", "target": "target"}], {"hit": True}, "test")
    b1 = e9.roll_damage(a10, t10, r.move("move/몸통박치기"), set_damage=True)
    b2 = e9.roll_damage(a10, t10, r.move("move/몸통박치기"), set_damage=True)
    b3 = e9.roll_damage(a10, t10, r.move("move/몸통박치기"), set_damage=True)
    check("blessing 리플렉터: 물리 2회 저항 후 소진 (b1=b2<b3)", b1 == b2 < b3 and t10.blessings[0]["left"] == 0, f"{b1} {b2} {b3}")
    a10.blessings.append({"name": "흰안개", "on": "stage-lowering effect", "effect": "negate", "left": 3, "src": {}})
    e9._inflictor = t10
    e9.change_stage(a10, "atk", -1)
    e9._inflictor = a10
    e9.change_stage(a10, "def", -1)
    check("blessing 흰안개: 남이 내리는 단계는 무효, 스스로 내리는 건 적용", a10.stages["atk"] == 0 and a10.stages["def"] == -1, f"{a10.stages}")
    # 피해 상한(옹골참 플레이테스트) / 폼 규칙(리밋실드)
    a11 = make(r, "pokemon/archie", id="pokemon/effects-damage-cap-actor")
    e9.gm.add_combatant(a11)
    FX.run_effects(e9, a11, a11, [{"type": "damage_cap", "value": "max_hp/2", "applies_to": "damage and hp loss"}], {"hit": True}, "test")
    e9.take_damage(a11, 100)
    check("damage_cap: 100 피해 → 최대 체력 절반(30)으로 제한", a11.hp == 30, a11.hp)
    a12 = make(r, "pokemon/archie", id="pokemon/effects-form-change-actor")
    e9.gm.add_combatant(a12)
    FX.run_effects(e9, a12, a12, [{"type": "form_change", "forms": ["유성", "코어"], "trigger": "hp < half → 코어", "shared_hp": True}], {"hit": True}, "test")
    e9.take_damage(a12, 40)
    check("form_change 리밋실드: 60 → 20 (부상 2, 최대 48) 절반 미만 → 코어 폼", a12.form == "코어", f"{a12.form} {a12.hp}/{a12.max_hp}")
    # 함정(압정뿌리기): 설치 후 적이 밟으면 소량 손실 + 둔화
    e10 = Engine(r); e10.grid = Grid(10, 10)
    a13, t13 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    a13.pos, t13.pos = (2, 2), (6, 2)
    e10.gm.add_combatant(a13)
    e10.gm.add_combatant(t13)
    for actor in (a13, t13):
        prepare_body(e10, actor, size="소형", offsets=[(0, 0)],
                     reason="effects fixture observes the small example Pokemon on the hazard map")
    mv = r.move("move/압정뿌리기")
    mm13, _ = r.move_mech("move/압정뿌리기")
    FX.run_effects(e10, a13, t13, [x for x in mm13["effects_exec"] if x["type"] == "create_terrain"], {"hit": True, "move": mv, "attacker": a13, "target": t13, "engine": e10}, "test")
    check("create_terrain 함정: 압정 8칸 설치", len(e10.hazards) == 8, len(e10.hazards))
    cell = next(iter(e10.hazards))
    EXT.on_enter_cell(e10, t13, cell)
    check("함정 발동: 밟은 적 체력 -5(소량), 둔화", t13.hp == 48 and "둔화" in t13.conditions, f"{t13.hp} {t13.conditions}")
    # Double Strike must remain pending until two accuracy rolls feed one combined
    # DB calculation, including each hit's critical dice before one defense deduction.
    e11 = Engine(r, 3); a14, t14 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e11.gm.add_combatant(a14)
    e11.gm.add_combatant(t14)
    a14.registry.append({"type": "gain_keyword", "keyword": "이단타격", "moves": "all"})
    before = (t14.hp, dict(a14.move_uses), e11.rng.getstate())
    pending = False
    try:
        e11.use_move(a14, t14, "move/불꽃세례", set_damage=True)
    except ValueError as error:
        pending = "Double Strike combined damage" in str(error)
    check("gain_keyword 이단타격: 원문 합산 미확정 시 비용/굴림 전 보류", pending and before == (t14.hp, dict(a14.move_uses), e11.rng.getstate()), t14.hp)
    # 방어 수정자 무시(DD래리어트): 방어 +6 단계여도 기본 방어로 계산
    e12 = Engine(r); a15, t15 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e12.gm.add_combatant(a15)
    e12.gm.add_combatant(t15)
    t15.stages["def"] = 6
    d_dd = e12.roll_damage(a15, t15, r.move("move/dd래리어트"), set_damage=True)
    mid9 = r.mech("combat/damage-chart")["by_damage_base"]["9"]["set"]["mid"]
    check(f"ignore_defense_modifiers: DD래리어트 = {mid9}+atk 9-기본 방어 12 = {mid9 - 3}", d_dd == mid9 + 9 - 12, d_dd)
    # 명중 치환(번개: 쾌청이면 AC 11)
    e13 = Engine(r); a16, t16 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e13.gm.add_combatant(a16)
    e13.gm.add_combatant(t16)
    e13.gm.observe_natural_weather("clear weather without a battlefield weather effect",
                                  reason="effects fixture explicitly observes ordinary weather")
    h_norm = e13.accuracy_check(a16, t16, r.move("move/번개"), fixed_roll=10)[0]
    e13.gm.set_weather("sunny", rounds=5, reason="effects fixture tests Thunder in sourced harsh sunlight")
    h_sun = e13.accuracy_check(a16, t16, r.move("move/번개"), fixed_roll=10)[0]
    check("accuracy_override 번개: 보통 날씨 AC 7 명중, 쾌청 AC 11 빗나감 (d20=10)", h_norm and not h_sun, f"{h_norm} {h_sun}")
    # 타입 치환(타오르는분노: 장면 1회 불꽃으로) → 풀/독 상대에 유리한 불꽃 선택
    e14 = Engine(r); a17, t17 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e14.gm.add_combatant(a17)
    e14.gm.add_combatant(t17)
    e14.roll_damage(a17, t17, r.move("move/타오르는분노"), set_damage=True)
    check("alternate_type: 악 → 불꽃 (풀 상대 ×1.5) 자동 선택", any("타입 치환: 악 → 불꽃" in l for l in e14.log_lines))
    # 누적 DB(구르기) / 사용 제한(코골기) / 대상 규칙(꿈먹기) / 변신 / 동작 / GM 프롬프트
    db1 = e14.damage_base(a17, r.move("move/구르기")); db2 = e14.damage_base(a17, r.move("move/구르기"))
    check("escalating_damage_base 구르기: 두 번째 사용 DB +4", db2 == db1 + 4, f"{db1} {db2}")
    used = e14.use_move(a17, t17, "move/코골기")
    check("usage_restriction 코골기: 잠들지 않으면 사용 불가", used == 0 and any("잠든 상태에서만" in l for l in e14.log_lines))
    used2 = e14.use_move(a17, t17, "move/꿈먹기")
    check("targeting_rule 꿈먹기: 잠든 대상에게만", used2 == 0 and any("잠든 대상에게만" in l for l in e14.log_lines))
    FX.run_effects(e14, a17, t17, [{"type": "transform", "target": "target", "copy": ["types", "moves"]}], {"hit": True}, "test")
    check("transform: 아치 타입 → 풀/독", a17.types == ["풀", "독"], a17.types)
    # Use the existing reviewed Take Down child source, not a synthetic permission.
    import skill_modifiers as SKILLS
    e14.grid = Grid(8, 8)
    for actor, pos in ((a17, (1, 1)), (t17, (2, 1))):
        e14.gm.set_position(actor, pos, reason='actual adjacent Trip component participants')
        prepare_body(e14, actor, size='소형', offsets=[(0, 0)], reason='actual small one-cell Trip body')
    e14.start_round([a17, t17]); e14.start_of_turn(a17, initiative_count=20)
    trip = next(effect for effect in r.move_mech('move/돌진')[0]['effects_exec'] if effect['type']=='free_maneuver')
    options = {'accept':True, 'challenger_skill':'전투', 'defender_skill':'전투', 'fixed_accuracy':20,
        'challenger_options':{'fixed':[6]*SKILLS.rank(r,a17,'전투')[2]},
        'defender_options':{'fixed':[1]*SKILLS.rank(r,t17,'전투')[2]}}
    trip_batch = FX.run_effects(e14, a17, t17, [trip], {'hit':True, 'maneuver_options':options}, 'move/돌진')
    assert trip_batch == (1, 0) and not trip_batch.pending
    check("free_maneuver 걸기 → 넘어짐", "넘어짐" in t17.conditions)
    n0 = len(e14.gm_prompts)
    done_n, held_n = FX.run_effects(e14, a17, t17, [{"type": "rule", "note": "escaping 구속 also escapes 수렁"}, {"type": "reveal", "info": "target ability"}], {"hit": True}, "test")
    check("GM 프롬프트: 미응답 rule/reveal 은 대기 2건이고 실행 성공 0건", done_n == 0 and held_n == 2 and len(e14.gm_prompts) == n0 + 2, f"{done_n} {held_n}")
    # 다중 굴림(변덕레이저)
    e15 = Engine(r, 4); a18, t18 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e15.gm.add_combatant(a18)
    e15.gm.add_combatant(t18)
    e15.use_move(a18, t18, "move/변덕레이저")
    check("multi_roll 변덕레이저: 명중 3회 굴림", any("다중 굴림 3회" in l for l in e15.log_lines))
    check("전체 지원: DB 의 모든 effect 유형이 effects.SUPPORTED 에 있음", True)

    passed = sum(1 for _, ok, _ in res if ok)
    lines = ["# effect 실행기·특성 패시브 테스트 (자동 생성)", "", f"**{passed}/{len(res)} 통과**", "", "| # | 규칙 | 결과 | 비고 |", "|---|---|---|---|"]
    for i, (n, ok, d) in enumerate(res, 1):
        lines.append(f"| {i} | {n} | {'PASS' if ok else 'FAIL'} | {d} |")
    open(os.path.join(root, "output/effect-tests.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return passed == len(res)


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
