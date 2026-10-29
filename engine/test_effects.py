"""effect 실행기 테스트: 기술 effect(교환·전장·방패·타입 변경·고유 상태·다음 공격·체력 손실 식) 와 특성 패시브(타입별 +5, 저항 단계, 무효·흡수, 치명타 범위).
  python -X utf8 -I engine/test_effects.py <root>"""
import os
import sys
from copy import deepcopy
from unittest.mock import patch

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
    # 4. Selected five-target-turn type addition, with actual native costs.
    from unittest.mock import patch as front_patch
    from grid import Grid as FrontGrid
    import event_effects as FRONT_EVENTS
    import healing_blocks as FRONT_BLOCKS
    import temporary_hp as FRONT_TEMP

    def front_world(label, moves):
        world = Engine(r, seed=41)
        world.grid = FrontGrid(20, 12)
        user = make(r, "pokemon/archie", id="pokemon/front-"+label+"-user",
                    moves=list(moves), abilities=[], side="party", pos=(1, 1))
        target = make(r, "pokemon/oddish-1", id="pokemon/front-"+label+"-target",
                      abilities=[], side="wild", pos=(2, 1))
        for actor in (user, target):
            world.gm.add_combatant(actor, reason="actual independent effect fixture participant")
            prepare_body(world, actor, size="소형", offsets=[(0, 0)],
                         reason="observed small one-cell effect fixture body")
        return world, user, target

    def front_next_turn(world, user):
        world.end_of_turn(user); world.end_round()
        world.start_round(world.everyone); world.start_of_turn(user, initiative_count=20)

    typed, typed_user, typed_target = front_world("type", ["move/핼러윈"])
    typed.start_round(typed.everyone); typed.start_of_turn(typed_user, initiative_count=20)
    with front_patch.object(typed, "d20", return_value=10):
        typed.use_move(typed_user, typed_target, "move/핼러윈")
    check("type_change add: 뚜벅초 풀/독 + 고스트", typed_target.types == ["풀", "독", "고스트"])
    check("타입 변경이 상성에 반영: 노말 공격 무효", typed.type_multiplier("노말", typed_target)[0] == 0)
    assert typed_user.budget["standard"] == 0 and typed_user.move_uses["move/핼러윈"] == 1
    typed.end_of_turn(typed_user)
    for turn_index in range(5):
        if turn_index:
            typed.end_round(); typed.start_round(typed.everyone)
        typed.start_of_turn(typed_target, initiative_count=10); typed.end_of_turn(typed_target)
        assert ("고스트" in typed_target.types) is (turn_index < 4)
    check("type_change: 정확히 다섯 대상 턴 후 원래 타입 복귀", typed_target.types == ["풀", "독"])
    FX.run_effects(e, a, a, [{"type": "type_change", "lose_type": "불꽃", "fallback": "노말"}], {"hit": True}, "test")
    check("type_change lose + fallback: 아치 불꽃 → 노말", a.types == ["노말"])
    # 5. Real Heal Block and Laser Focus producers; forced_target remains the
    # original storage-adapter smoke scope, not a native Follow Me certificate.
    control, control_user, control_target = front_world("control", ["move/회복봉인", "move/예민해지기", "move/불꽃세례"])
    control.gm.set_stat(control_target, "hp", value=100, reason="durable target for successive native attacks")
    control.gm.set_hp(control_target, value=control_target.base_max_hp-5, reason="actual prior damage for healing-block consumer")
    control.start_round(control.everyone); control.start_of_turn(control_user, initiative_count=20)
    with front_patch.object(control, "d20", return_value=10):
        control.use_move(control_user, control_target, "move/회복봉인")
    hp_before = control_target.hp
    assert control.heal(control_target, 5, source_kind="move") == 0 and control_target.hp == hp_before
    assert control_user.move_uses["move/회복봉인"] == 1 and control_user.budget["standard"] == 0
    choice = FRONT_EVENTS.laser_focus_source_choices(r)
    FRONT_EVENTS.choose_laser_focus_source(control, control_user,
        {"value":"english_next_successful_attack", "reason":"explicit successful-hit contract for this Laser Focus fixture", "scope":choice["decision_scope"]})
    front_next_turn(control, control_user)
    control.use_move(control_user, control_user, "move/예민해지기")
    focused = [row for row in FRONT_EVENTS.live(control_user) if row["source"] == "move/예민해지기"]
    assert len(focused) == 1 and control_user.move_uses["move/예민해지기"] == 1 and control_user.budget["standard"] == 0
    forced = FX.run_effects(control, control_user, control_target,
        [{"type":"forced_target", "must_target":"user"}], {"hit":True}, "test")
    assert forced == (1, 0) and not forced.pending
    check("custom_condition / next_attack / forced_target 저장",
          bool(FRONT_BLOCKS.records(control_target)) and bool(focused) and control.taunt["by"] is control_user)
    front_next_turn(control, control_user); control.enable_execution_trace()
    with front_patch.object(control, "d20", return_value=10):
        damage = control.use_move(control_user, control_target, "move/불꽃세례", set_damage=True)
    attacks = [row for row in control.execution_traces() if row["producer"] == "resolve_attack_damage"]
    check("next_attack_modifier: 다음 공격이 자동 치명타, 1회 소모",
          damage > 0 and bool(attacks) and attacks[-1]["inputs"]["crit"] and not FRONT_EVENTS.live(control_user))
    assert control_user.move_uses["move/불꽃세례"] == 1 and control_user.budget["standard"] == 0
    front_next_turn(control, control_user)
    with front_patch.object(control, "d20", return_value=10):
        second_damage = control.use_move(control_user, control_target, "move/불꽃세례", set_damage=True)
    attacks = [row for row in control.execution_traces() if row["producer"] == "resolve_attack_damage"]
    check("next_attack_modifier: 소모 후 다음 실제 공격은 자동 치명타 아님",
          second_damage > 0 and not attacks[-1]["inputs"]["crit"] and control_user.move_uses["move/불꽃세례"] == 2)
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
    push_world, chain_actor, push_target = front_world("push", [])
    original_position = tuple(push_target.pos)
    batch = FX.run_effects(push_world, chain_actor, push_target,
        [{"type":"multi_target_chain", "max":3}, {"type":"push", "meters":"8 - target.weight_class"},
         {"type":"stage_change", "stat":"atk", "delta":1, "target":"self"}],
        {"hit":True, "attacker":chain_actor, "target":push_target, "engine":push_world}, "test")
    done, held = batch
    check("보류 집계: mapped push와 실제 stage 실행, chain은 native 소비자 위임",
          done == 2 and held == 0 and push_target.pos == (original_position[0]+7, original_position[1])
          and chain_actor.stages["atk"] == 1 and batch.outcomes[0].status == "deferred_consumer",
          f"done {done} held {held}, position {push_target.pos}")
    # The deferred marker above is not chain completion. Exercise its real
    # selected native producer with an explicit first target/forgone suffix.
    chain_world, chain_user, chain_target = front_world("chain", ["move/트리플다이브"])
    chain_world.start_round(chain_world.everyone); chain_world.start_of_turn(chain_user, initiative_count=20)
    with front_patch.object(chain_world, "d20", return_value=16):
        chain_damage = chain_world.use_move_on(chain_user, chain_target, "move/트리플다이브", chain_world.everyone,
            chain_steps=[{"target":chain_target, "path":[], "forgo_remaining":True}], set_damage=True)
    chain_row = next(row for row in chain_world._move_completions.values() if row["move_id"] == "move/트리플다이브")
    check("multi_target_chain: 실제 선택한 첫 명중과 잔여 포기, 비용 1회",
          chain_damage > 0 and chain_row["phase"] == "complete" and len(chain_row["started"]) == 1
          and chain_user.move_uses["move/트리플다이브"] == 1 and chain_user.budget["standard"] == 0)
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
    # 7e. 단계 하락 면역(클리어바디) / stat_mod(라이트메탈 체급 -2) / connection(꿀도둑: 실제 벌레먹기 음식 절도 후 임시 체력 tick)
    e4 = Engine(r); a5, t5 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    t5.abilities = ["클리어바디", "라이트메탈 [Playtest]", "꿀도둑"]
    e4.gm.add_combatant(a5, side="party", reason="actual opposing effect participant")
    e4.gm.add_combatant(t5, side="wild", reason="actual hostile recipient and later Bug Bite user")
    FX.run_effects(e4, a5, t5, [{"type": "stage_change", "stat": "atk", "delta": -1, "target": "target"}, {"type": "stage_change", "stat": "atk", "delta": -1, "target": "self"}], {"hit": True, "attacker": a5, "target": t5}, "test")
    check("클리어바디: 적이 내린 atk -1 은 면역, 자기 자신의 하락은 그대로", t5.stages["atk"] == 0 and a5.stages["atk"] == -1, f"{t5.stages} {a5.stages}")
    check("라이트메탈: 체급 1 → 1 (하한 1), 영구 체급 보존", t5.weight_class == 1 and t5.spec["weight_class"] == 1, (t5.weight_class,t5.spec["weight_class"]))
    bug_bite = r.move_id("벌레먹기")
    check("꿀도둑 connection: 벌레먹기 학습, 실제 절도 전 임시 HP 없음", bug_bite in t5.moves and t5.temp_hp == 0)
    a5.spec.setdefault("items", {})["초코바"] = 1
    e4.use_item(a5, "초코바", a5, duration_minutes=1, duration_reason="actual food intake before Bug Bite")
    food_id = a5.buffs[-1]["id"]
    e4.grid = FrontGrid(8, 8)
    for actor, position in ((t5, (1, 1)), (a5, (2, 1))):
        e4.gm.set_position(actor, position, reason="actual adjacent hostile Bug Bite participants")
        prepare_body(e4, actor, size="소형", offsets=[(0, 0)], reason="observed Bug Bite participants")
    assert t5.side != a5.side
    e4.gm.choose_food_transfer(t5, a5, food_id, reason="select actual live food effect for Bug Bite theft")
    e4.start_round(e4.everyone); e4.start_of_turn(t5, initiative_count=20)
    before_hp = a5.hp
    with front_patch.object(e4, "d20", return_value=10):
        bite_damage = e4.use_move(t5, a5, bug_bite, set_damage=True)
    event = t5.custom_conditions[FRONT_TEMP.STATE]["grant_event"]
    check("벌레먹기 실제 명중·음식 절도 → 임시 체력 tick(뚜벅초 최대 53 → 5)",
          bite_damage > 0 and a5.hp < before_hp and t5.temp_hp == e4.tick(t5) == 5
          and event == {"kind":"food_effect_transfer", "effect_id":food_id, "from_actor_id":a5.entity_id, "move_source":bug_bite}
          and any(row["id"] == food_id for row in t5.buffs) and not any(row["id"] == food_id for row in a5.buffs)
          and t5.move_uses[bug_bite] == 1 and t5.budget["standard"] == 0, t5.temp_hp)
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
    FX.run_effects(e3, c6, c6, [{"type": "temp_hp", "value": 10}], {"hit": True, "attacker": c6, "target": c6, "engine": e3}, "temporary HP component")
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
    e7 = Engine(r); e7.grid = Grid(8, 8)
    a7, t7 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    e7.gm.add_combatant(a7, pos=(1, 1), side="party", reason="actual equipment exchange user")
    e7.gm.add_combatant(t7, pos=(2, 1), side="foe", reason="actual opposed equipment exchange recipient")
    for actor in (a7, t7):
        prepare_body(e7, actor, size="소형", offsets=[(0, 0)], reason="actual adjacent equipment exchange body")
    t7.item = "오랭열매"
    FX.run_effects(e7, a7, t7, [{"type": "steal_item", "if": "user holds nothing"}], {"hit": True, "attacker": a7, "target": t7}, "test")
    check("steal_item: 도구 없는 아치가 뚜벅초의 오랭열매를 빼앗음", a7.item == "오랭열매" and t7.item is None, f"{a7.item} {t7.item}")
    # Switcheroo's equipment exchange requires its real selected Move source.
    e7.gm.set_move(a7, "move/바꿔치기", reason="actual learned Switcheroo fixture")
    e7.start_round([a7, t7]); e7.start_of_turn(a7, initiative_count=20)
    with patch.object(e7, "d20", return_value=18):
        e7.use_move(a7, t7, "move/바꿔치기")
    check("swap_items: 실제 바꿔치기 지불 후 뚜벅초가 다시 지님",
          t7.item == "오랭열매" and a7.item is None
          and a7.budget["standard"] == 0 and a7.move_uses["move/바꿔치기"] == 1)
    e7.end_of_turn(a7); e7.end_encounter(e7.everyone)
    t7.stages["atk"], t7.stages["spe"] = 2, -1
    FX.run_effects(e7, a7, t7, [{"type": "invert_stages", "target": "target"}], {"hit": True}, "test")
    check("invert_stages: +2/-1 → -2/+1", t7.stages["atk"] == -2 and t7.stages["spe"] == 1, f"{t7.stages}")
    FX.run_effects(e7, a7, t7, [{"type": "copy_stages", "from": "target", "to": "self"}], {"hit": True}, "test")
    check("copy_stages: 아치 단계 = 뚜벅초 단계", a7.stages == t7.stages)
    e7.apply_status(a7, "마비")
    FX.run_effects(e7, a7, t7, [{"type": "transfer_status", "from": "self", "to": "target"}], {"hit": True}, "test")
    check("transfer_status: 마비가 아치에서 뚜벅초로", "마비" in t7.conditions and "마비" not in a7.conditions, f"{a7.conditions} {t7.conditions}")
    choice_before=set(t7.conditions)
    choice_result=FX.run_effects(e7, a7, t7, [{"type": "apply_status_choice", "options": ["둔화 (1라운드)", "억압"], "target": "target"}], {"hit": True}, "test")
    check("apply_status_choice: 실제 획득 선택권 없는 기본 선택 거부", choice_result[0]==0 and choice_result[1]==1 and t7.conditions==choice_before)
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
    # Apply the full 10% injury proportion before rounding the recovery ceiling.
    check("injury: 실제 최대 53, 부상 +1 → 회복 상한 floor(53×0.9)=47",
          t7.injuries == 1 and t7.base_max_hp == 53 and t7.max_hp == 47,
          f"{t7.injuries} {t7.max_hp}")
    FX.run_effects(e7, a7, t7, [{"type": "heal_injury", "value": 1, "target": "target"}], {"hit": True}, "test")
    check("heal_injury: 부상 치유 → 0", t7.injuries == 0)
    t7.hp = 1
    # This component targets the actual present recipient; an annotation is not a target selector.
    restored_batch = FX.run_effects(e7, a7, t7, [{"type": "full_restore", "target": "target", "heal_injuries": 3, "restore_frequencies": True}], {"hit": True}, "test")
    check("full_restore: 실제 대상의 체력 최대, 상태이상 전부 치유",
          restored_batch == (1, 0) and t7.hp == t7.max_hp and not (t7.conditions - {"기절"}),
          f"{t7.hp} {t7.conditions}")
    a7.hp, t7.hp = 60, 20
    FX.run_effects(e7, a7, t7, [{"type": "hp_share", "rule": "both lose half current, then both gain (sum lost)/2"}], {"hit": True}, "test")
    check("hp_share: 60/20 → 각각 절반 잃고 평균 회복 → 50/30", a7.hp == 50 and t7.hp == 30, f"{a7.hp} {t7.hp}")
    # The CSV Wish edition owns this exact target-next-turn clock.
    wish_e = Engine(r); wish_e.grid = Grid(8, 8)
    wish_a = make(r, "pokemon/archie", id="pokemon/effects-wish-actor")
    wish_t = make(r, "pokemon/oddish-2", id="pokemon/effects-wish-target")
    for actor, pos in ((wish_a, (1, 1)), (wish_t, (2, 1))):
        wish_e.gm.add_combatant(actor, pos=pos, side="party", reason="actual allied Wish participants")
        prepare_body(wish_e, actor, size="소형", offsets=[(0, 0)], reason="actual Wish recipient body")
    wish_e.gm.set_move(wish_a, "move/희망사항", reason="actual learned Wish fixture")
    wish_e.gm.set_hp(wish_t, 10, reason="actual damaged Wish recipient")
    wish_e.start_round([wish_a, wish_t]); wish_e.start_of_turn(wish_a, initiative_count=20)
    wish_e.use_move(wish_a, wish_t, "move/희망사항", wish_edition="csv-row623")
    wish_paid = wish_a.budget["standard"] == 0 and wish_a.move_uses["move/희망사항"] == 1
    wish_e.end_of_turn(wish_a)
    wish_waited = wish_t.hp == 10 and len(wish_e.delayed) == 1
    wish_e.start_of_turn(wish_t, initiative_count=10); wish_e.end_of_turn(wish_t)
    check("delayed_heal: 지불된 CSV 희망사항은 실제 대상의 다음 턴 끝에 10→36",
          wish_paid and wish_waited and wish_t.hp == 36 and not wish_e.delayed, wish_t.hp)
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
    # Blessing previews do not spend a source-owned team pool; actual chosen hits do.
    import blessing_effects as BLESSINGS
    reflect_e = Engine(r); reflect_e.grid = Grid(8, 8)
    reflect_a = make(r, "pokemon/archie", id="pokemon/effects-reflector-attacker")
    reflect_t = make(r, "pokemon/oddish-2", id="pokemon/effects-reflector-owner")
    for actor, pos, side in ((reflect_a, (1, 1), "foe"), (reflect_t, (2, 1), "party")):
        reflect_e.gm.add_combatant(actor, pos=pos, side=side, reason="actual Reflector participants")
        prepare_body(reflect_e, actor, size="소형", offsets=[(0, 0)], reason="actual Reflector hit body")
    reflect_e.gm.set_move(reflect_t, "move/리플렉터", reason="actual learned Reflector")
    reflect_e.gm.set_move(reflect_a, "move/몸통박치기", reason="actual learned physical attack")
    reflect_e.start_round([reflect_a, reflect_t]); reflect_e.start_of_turn(reflect_t, initiative_count=20)
    reflect_e.use_move(reflect_t, reflect_t, "move/리플렉터")
    reflect_pool = next(row for row in BLESSINGS.live(reflect_t) if row["source"] == "move/리플렉터")
    reflect_paid = reflect_t.budget["standard"] == 0 and reflect_t.move_uses["move/리플렉터"] == 1
    reflect_e.roll_damage(reflect_a, reflect_t, reflect_e.r.move("move/몸통박치기"), set_damage=True)
    preview_kept_pool = BLESSINGS.remaining(reflect_pool) == 2 and not reflect_pool["decisions"]
    reflect_e.rulings.add_answer("team_blessing", True, reason="actual beneficiary chooses resistance")
    reflect_damage = []
    for _ in range(3):
        if reflect_e._active_turn_actor is not None:
            reflect_e.end_of_turn(reflect_e._active_turn_actor)
        reflect_e.start_round([reflect_a, reflect_t]); reflect_e.start_of_turn(reflect_a, initiative_count=20)
        with patch.object(reflect_e, "d20", return_value=18):
            reflect_damage.append(reflect_e.use_move(reflect_a, reflect_t, "move/몸통박치기", set_damage=True))
    b1, b2, b3 = reflect_damage
    check("blessing 리플렉터: 미리보기는 보존, 선택한 실제 물리 2회 저항 후 소진",
          reflect_paid and preview_kept_pool and b1 == b2 < b3
          and BLESSINGS.remaining(reflect_pool) == 0 and not BLESSINGS.live(reflect_t),
          f"{b1} {b2} {b3}")
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
    # An explicitly acquired real ability and authored forms, not an anonymous trigger dictionary.
    forms_e = Engine(r)
    a12 = make(r, "pokemon/archie", id="pokemon/effects-form-change-actor", abilities=["ability/리밋실드"])
    forms_e.gm.add_combatant(a12, reason="actual acquired Shields Down fixture; no natural-species acquisition claim")
    meteor_stats = dict(a12.spec["stats"]); core_stats = dict(meteor_stats)
    core_stats["def"] -= 1; core_stats["atk"] += 1
    forms_e.configure_form_allocations(a12, {"유성": meteor_stats, "코어": core_stats},
                                      active="유성", source="ability/리밋실드")
    forms_e.start_round([a12]); forms_e.start_of_turn(a12, initiative_count=20)
    forms_e.take_damage(a12, 40)
    check("form_change 리밋실드: 실제 획득/폼 배분 뒤 60→20, 코어 폼과 배분 유지",
          a12.base_max_hp == 60 and a12.hp == 20 and a12.max_hp == 48
          and a12.form == "코어" and a12.spec["stats"] == core_stats,
          f"{a12.form} {a12.hp}/{a12.max_hp}")
    # Native Spikes: one paid placement and one actual entered body cell.
    e10 = Engine(r); e10.grid = Grid(10, 10)
    a13, t13 = make(r, "pokemon/archie"), make(r, "pokemon/oddish-2")
    a13.pos, t13.pos = (2, 2), (6, 2)
    e10.gm.add_combatant(a13, side="party", reason="actual native Hazard creator")
    e10.gm.add_combatant(t13, side="foe", reason="actual hostile Hazard entrant")
    for actor in (a13, t13):
        prepare_body(e10, actor, size="소형", offsets=[(0, 0)],
                     reason="effects fixture observes the small example Pokemon on the hazard map")
    spike_move = "move/압정뿌리기"
    e10.gm.set_move(a13, spike_move, reason="actual learned printed Spikes fixture")
    spike_cells = ((3, 1), (3, 2), (3, 3), (4, 1), (4, 2), (4, 3), (5, 1), (5, 2))
    e10.start_round(e10.everyone); e10.start_of_turn(a13, initiative_count=20)
    e10.use_move_on(a13, a13, spike_move, e10.everyone, aim=spike_cells)
    check("create_terrain 함정: 실제 압정 8칸과 1회 Standard/기술 지불",
          set(e10.hazards) == set(spike_cells) and a13.budget['standard'] == 0
          and a13.move_uses[spike_move] == 1
          and all(instance['kind'] == 'spikes' and instance['source_id'] == spike_move
                  and instance['owner_actor_id'] == a13.entity_id
                  for envelope in e10.hazards.values() for instance in envelope['instances']),
          len(e10.hazards))
    e10.end_of_turn(a13); e10.start_of_turn(t13, initiative_count=10)
    hp_before_entry = t13.hp
    # Spikes are Slow Terrain: this entry costs2m, beyond Disengage's1m cap.
    # Use the same paid-path owner as ordinary Engine.approach movement.
    import turn as TURN
    import movement_actions as MOVEMENT
    movement_budget = e10.move_profile(t13, movement_mode='land')[0]
    assert TURN.spend(e10, t13, 'shift', 'actual entry onto Spikes', movement=True)
    moved = MOVEMENT.follow_paid_path(e10, t13, [(5, 2)], mode='land',
                                      maximum_distance=movement_budget)
    check("함정 발동: 실제 진입한 적 체력 -5(소량), 둔화와 Shift 지불",
          moved['steps'] == 1 and moved['distance'] == 2
          and t13.pos == (5, 2) and t13.budget['shift'] == 0
          and hp_before_entry - t13.hp == t13.base_max_hp // 10
          and t13.hp == 48 and "둔화" in t13.conditions,
          f"{t13.hp} {t13.conditions}")
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
    # Printed Dark stays the default; Fire needs the actual scene-limited choice.
    import alternate_move_modes as ALTERNATE
    e14 = Engine(r); e14.grid = Grid(8, 8)
    a17 = make(r, "pokemon/archie", moves=["move/타오르는분노", "move/코골기", "move/꿈먹기", "move/돌진"])
    t17 = make(r, "pokemon/oddish-2", stats=dict(r.creatures["pokemon/oddish-2"]["stats"], hp=300))
    for actor, pos, side in ((a17, (1, 1), 'party'), (t17, (2, 1), 'foe')):
        e14.gm.add_combatant(actor, pos=pos, side=side, reason='actual alternate-type Move participants')
        prepare_body(e14, actor, size='소형', offsets=[(0, 0)], reason='actual small alternate-type Move body')
    e14.start_round(e14.everyone); e14.start_of_turn(a17, initiative_count=20)
    alternate_mid = 'move/타오르는분노'
    alternate_move = r.move(alternate_mid)
    alternate_mechanics = r.move_mech(alternate_mid)[0]
    default_type = EXT.effective_type(e14, a17, t17, alternate_move, alternate_mechanics, consume=False)
    selected = e14.gm.choose_alternate_move_type(a17, alternate_mid, '불꽃',
                                               reason='actual player selects printed once-per-scene Fire mode')
    with patch.object(Engine, 'd20', return_value=10):
        selected_damage = e14.use_move(a17, t17, alternate_mid, set_damage=True)
    alternate_record = ALTERNATE.status(a17, alternate_mid)[0]
    check("alternate_type: 기본 악 유지, 명시 불꽃 선택을 실제 기술에서 1회 사용",
          default_type == '악' and selected_damage > 0
          and alternate_record['id'] == selected['id'] and alternate_record['status'] == 'used'
          and alternate_record['use']['actual_type'] == '불꽃'
          and a17.move_uses[alternate_mid] == 1 and a17.budget['standard'] == 0)
    e14.end_of_turn(a17); e14.end_round()
    # Queries cannot invent consecutive hits. A real independent Rollout Pass
    # advances its existing forced chain without locking unrelated later cases.
    e_roll = Engine(r, 404); e_roll.grid = Grid(8, 8)
    a_roll = make(r, "pokemon/archie", id='pokemon/effects-rollout-user', moves=['move/구르기'])
    t_roll = make(r, "pokemon/oddish-2", id='pokemon/effects-rollout-target',
                  stats=dict(r.creatures["pokemon/oddish-2"]["stats"], hp=300))
    for actor, pos, side in ((a_roll, (2, 2), 'party'), (t_roll, (3, 2), 'foe')):
        e_roll.gm.add_combatant(actor, pos=pos, side=side, reason='actual Rollout Pass participant')
        prepare_body(e_roll, actor, size='소형', offsets=[(0, 0)], reason='actual one-cell Pass body')
    e_roll.start_round(e_roll.everyone); e_roll.start_of_turn(a_roll, initiative_count=20)
    roll_move = r.move('move/구르기')
    query_state = deepcopy((a_roll.counters, a_roll.move_uses, a_roll.spec.get('_conditional_damage_base'), e_roll.rng.getstate()))
    db1 = e_roll.damage_base(a_roll, roll_move, target=t_roll)
    db_repeat = e_roll.damage_base(a_roll, roll_move, target=t_roll)
    assert (a_roll.counters, a_roll.move_uses, a_roll.spec.get('_conditional_damage_base'), e_roll.rng.getstate()) == query_state
    roll_hp = t_roll.hp
    with patch.object(Engine, 'd20', return_value=10):
        roll_receipt = e_roll.use_pass_move(a_roll, 'move/구르기', (4, 2),
            event_id='effects/actual-rollout-pass', object_adjudications={},
            source='gm/observed-object-hits', reason='actual complete Rollout path through the target')
    db2 = e_roll.damage_base(a_roll, roll_move, target=t_roll)
    check("escalating_damage_base 구르기: 조회 불변, 실제 Pass 성공 뒤 다음 DB +4",
          db1 == db_repeat == 3 and db2 == db1 + 4 and t_roll.hp < roll_hp
          and a_roll.move_uses['move/구르기'] == 1
          and (a_roll.budget['standard'], a_roll.budget['shift']) == (0, 0)
          and roll_receipt['phase'] == 'complete', f"{db1} {db_repeat} {db2}")
    e14.start_round(e14.everyone); e14.start_of_turn(a17, initiative_count=20)
    snore_before = deepcopy((a17.budget, a17.move_uses, a17.hp, t17.hp,
                             a17.conditions, t17.conditions, e14.rng.getstate()))
    snore_log_start = len(e14.log_lines)
    used = e14.use_move_on(a17, t17, "move/코골기", e14.everyone, aim=a17.pos)
    snore_after = deepcopy((a17.budget, a17.move_uses, a17.hp, t17.hp,
                            a17.conditions, t17.conditions, e14.rng.getstate()))
    snore_refusal = e14.log_lines[snore_log_start:]
    snore_source_refused = any("코골기는 실제 잠든 사용자의 학습된 native 기술로만 사용 가능" in line
                              for line in snore_refusal)
    check("usage_restriction 코골기: 깨어 있으면 실제 파열 시도도 비용/굴림 전 거부",
          used == 0 and snore_source_refused and snore_after == snore_before,
          {"return": used, "source_refused": snore_source_refused, "logs": snore_refusal,
           "budget_before": snore_before[0], "budget_after": snore_after[0],
           "uses_before": snore_before[1], "uses_after": snore_after[1],
           "hp_before": snore_before[2:4], "hp_after": snore_after[2:4],
           "conditions_before": [sorted(value) for value in snore_before[4:6]],
           "conditions_after": [sorted(value) for value in snore_after[4:6]],
           "rng_unchanged": snore_after[6] == snore_before[6]})
    e14.end_of_turn(a17); e14.end_round()
    e14.start_round(e14.everyone); e14.start_of_turn(a17, initiative_count=20)
    dream_before = deepcopy((a17.budget, a17.move_uses, a17.hp, t17.hp,
                             a17.conditions, t17.conditions, e14.rng.getstate()))
    dream_log_start = len(e14.log_lines)
    used2 = e14.use_move(a17, t17, "move/꿈먹기")
    dream_after = deepcopy((a17.budget, a17.move_uses, a17.hp, t17.hp,
                            a17.conditions, t17.conditions, e14.rng.getstate()))
    dream_refusal = e14.log_lines[dream_log_start:]
    dream_source_refused = any("잠든 대상에게만" in line for line in dream_refusal)
    check("targeting_rule 꿈먹기: 깨어 있는 실제 대상은 비용/굴림 전 거부",
          used2 == 0 and dream_source_refused and dream_after == dream_before,
          {"return": used2, "source_refused": dream_source_refused, "logs": dream_refusal,
           "budget_before": dream_before[0], "budget_after": dream_after[0],
           "uses_before": dream_before[1], "uses_after": dream_after[1],
           "hp_before": dream_before[2:4], "hp_after": dream_after[2:4],
           "conditions_before": [sorted(value) for value in dream_before[4:6]],
           "conditions_after": [sorted(value) for value in dream_after[4:6]],
           "rng_unchanged": dream_after[6] == dream_before[6]})
    e14.end_of_turn(a17); e14.end_round()
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
    waiting_batch = FX.run_effects(e14, a17, t17,
        [{"type": "rule", "note": "escaping 구속 also escapes 수렁"},
         {"type": "reveal", "info": "target ability"}], {"hit": True}, "test")
    pending_effects = waiting_batch.pending
    first = e14._effect_dispatch_receipts[pending_effects[0].receipt] if pending_effects else {}
    suffix = e14._effect_dispatch_receipts[pending_effects[1].receipt] if len(pending_effects) > 1 else {}
    check("GM 프롬프트: 첫 미응답과 실제 연결된 reveal 후속 보류, 실행 성공 0건",
          waiting_batch[0] == 0 and waiting_batch[1] == 1 and len(pending_effects) == 2
          and len(e14.gm_prompts) == n0 + 1 and first.get('effect', {}).get('type') == 'rule'
          and suffix.get('status') == 'deferred_suffix'
          and suffix.get('blocked_on') is pending_effects[0].receipt
          and suffix.get('effects') == [{"type": "reveal", "info": "target ability"}]
          and suffix.get('resumed') is False)
    # Full Fickle Beam, including U-011's previous own-turn-start window.
    # Actual Water Gun damage supplies the earlier super-effective observation.
    import passive_events as PASSIVE
    import earned_status_choices as EARNED
    e15 = Engine(r, 4); e15.grid = Grid(10, 8)
    a18 = make(r, "pokemon/archie", moves=['move/변덕레이저'],
               stats=dict(r.creatures["pokemon/archie"]["stats"], hp=300))
    t18 = make(r, "pokemon/oddish-2", moves=['move/물대포'],
               stats=dict(r.creatures["pokemon/oddish-2"]["stats"], hp=300))
    for actor, pos, side in ((a18, (2, 2), 'party'), (t18, (3, 2), 'foe')):
        e15.gm.add_combatant(actor, pos=pos, side=side, reason='actual complete Fickle history participant')
        prepare_body(e15, actor, size='소형', offsets=[(0, 0)], reason='actual Fickle line body')
    assert '불꽃' in a18.types and t18.types == ['풀', '독']
    e15.start_round(e15.everyone); e15.start_of_turn(a18, initiative_count=20)
    e15.end_of_turn(a18); e15.start_of_turn(t18, initiative_count=10)
    history_hp = a18.hp
    with patch.object(Engine, 'd20', return_value=10):
        history_damage = e15.use_move(t18, a18, 'move/물대포', set_damage=True)
    assert history_damage > 0 and a18.hp < history_hp
    e15.end_of_turn(t18); e15.end_round()
    e15.start_round(e15.everyone); e15.start_of_turn(a18, initiative_count=20)
    native_roll_damage = Engine.roll_damage
    fickle_damage_facts = []
    def observe_fickle_damage(engine, attacker, target, move, *args, **kwargs):
        value = native_roll_damage(engine, attacker, target, move, *args, **kwargs)
        if move['id'] == 'move/변덕레이저':
            event = kwargs.get('_reaction_event')
            if event is not None:
                fickle_damage_facts.append(deepcopy(event.get('damage_formula', {})))
        return value
    choice_required = False
    fickle_target_hp = t18.hp
    with patch.object(Engine, 'd20', side_effect=[10, 10, 10]) as accuracy_faces, \
         patch.object(Engine, 'roll_damage', autospec=True, side_effect=observe_fickle_damage):
        try:
            e15.use_move_on(a18, t18, 'move/변덕레이저', e15.everyone, aim=(5, 2), set_damage=True)
        except PASSIVE.PassiveEventPending as waiting:
            event = e15._passive_events[waiting.event_id]
            assert event['actor'] is a18 and event['target'] is t18
            assert event['move_id'] == 'move/변덕레이저' and event['reason'] == 'earned_status_choice'
            facts = event[EARNED.KEY]['facts']
            assert len(facts['results']) == 3 and facts['budget'] == 2
            choice_required = True
            e15.choose_move_status(a18, waiting.event_id, [1, 2])
    check("multi_roll 변덕레이저: 실제 3회 명중·획득 선택·직전 턴 이후 상성 1단계",
          accuracy_faces.call_count == 3 and choice_required and e15._passive_pending is None
          and a18.move_uses['move/변덕레이저'] == 1 and a18.budget['standard'] == 0
          and t18.hp < fickle_target_hp and {'둔화', '억압'} <= t18.conditions
          and len(fickle_damage_facts) == 1 and fickle_damage_facts[0]['multiplier'] == 1.5
          and any("다중 굴림 3회" in line for line in e15.log_lines))
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
