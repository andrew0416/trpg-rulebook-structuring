"""
인카운터 로더 + 범용 전투 루프 + 간단한 AI. 파일럿 시나리오(engine.scenario)가 챕터 7 데모에 고정돼 있던 것을 임의 구성으로 푼다.
  python -X utf8 -I engine/encounter.py <root> data/encounters/lakeside.json [seed] [--ruleset=NAME] [--rulings] → output/encounter-<name>.md
인카운터 파일: {"name", "seed", "rounds", "grid": {"w","h","blocking":[[x,y]…],"slow":[…],"rough":[…]}, "weather",
              "party": [ {"species":"브케인","level":20,"name":"아치","nature":"…","strategy":"special","pos":[3,5],"moves":[…]} | {"trainer":{"name","level","stats",…}} ],
              "wild":  [ … 같은 꼴, "wild": true 기본 … ], "custom_species": ["data/custom/species/foo.json"] }
AI(choose_action): 사거리/빈도를 만족하는 기술 가운데 (타입 배수 × DB) 가 가장 큰 공격기, 없으면 변화기, 없으면 발버둥. 트레이너는 약해진 야생에 볼을 던진다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frequency as FREQ
from builder import build_pokemon, build_trainer, describe  # noqa: E402
import heavy_injury_adapter as HEAVY
import passive_events as PASSIVE_EVENTS
from engine import Combatant, Engine, Rules  # noqa: E402
from grid import Grid, cheb  # noqa: E402
import effects as FX  # noqa: E402
import turn as TURN  # noqa: E402
import priority_actions as PRIORITY  # noqa: E402
import initiative_interrupts as INTERRUPTS  # noqa: E402
import initiative_schedule as SCHEDULE  # noqa: E402


def usable_moves(engine, c):
    """빈도(턴1회·장면 xN·하루 xN)와 봉인을 지킨 사용 가능 기술."""
    out = []
    for mid in c.moves:
        if mid in engine.r.excluded_moves:
            continue
        mid = engine.r.resolve_move(mid)
        outside=not engine.encounter_active and engine._active_turn_actor is None
        if not FREQ.move_allowed(engine, c, mid,outside_combat=outside)[0]:
            continue
        if c.locked_move and mid != c.locked_move:
            continue
        out.append(mid)
    return out or ["struggle"]


def score_move(engine, c, mid, target):
    mv = engine.r.move(mid)
    if mv["class"] in ("물리", "특수") and isinstance(mv.get("damage_base"), int):
        mult = engine.type_multiplier(mv["type"], target)[0]
        stab = 2 if mv["type"] in c.types else 0
        return (mv["damage_base"] + stab) * mult * (1.0 if mv.get("ac") is None else max(0.5, 1 - 0.03 * mv["ac"]))
    if mv["class"] == "변화":
        return 1.5 if not target.conditions else 0.5
    return 1.0


def choose_action(engine, c, enemies, allies):
    """(행동 종류, 기술 id, 대상). 트레이너: 포획 기회 → 볼, 아니면 가장 좋은 기술."""
    import repels as REPELS
    repelled=REPELS.continuation(c) or REPELS.intent(engine,c)
    if repelled is not None:return 'repel',None,None
    alive = [x for x in enemies if not x.fainted and not x.captured and x.on_field]
    if not alive:
        return None, None, None
    target = min(alive, key=lambda x: (x.hp / max(1, x.base_max_hp), cheb(c.pos, x.pos)))
    if c.kind == "trainer":
        import items as ITEMS
        ball_key = ITEMS.ball_inventory_key(c)
        weak = [x for x in alive if x.kind == "pokemon" and x.spec.get("wild") and x.hp <= 0.5 * x.base_max_hp]
        if ball_key is not None and weak:
            return "ball", None, min(weak, key=lambda x: x.hp)
    moves = usable_moves(engine, c)
    best = max(moves, key=lambda m: (score_move(engine, c, m, target), -moves.index(m)))
    return "move", best, target


def load_encounter(root, path, ruleset=None, rulings_path=None, seed=None):
    enc = json.load(open(os.path.join(root, path) if not os.path.isabs(path) else path, encoding="utf-8"))
    r = Rules(root, ruleset=ruleset, rulings_path=rulings_path, custom_species=enc.get("custom_species"))
    e = Engine(r, seed if seed is not None else enc.get("seed", 1))
    g = enc.get("grid") or {"w": 14, "h": 10}
    e.grid = Grid(g.get("w", 14), g.get("h", 10), blocking={tuple(x) for x in g.get("blocking", [])}, slow={tuple(x) for x in g.get("slow", [])}, rough={tuple(x) for x in g.get("rough", [])}, walls=g.get("walls", []))
    if enc.get("weather"):
        import weather_state as WEATHER
        WEATHER.set_weather(e,enc["weather"],source_id="encounter/weather",origin="encounter")
    party, wild = [], []
    for side_name, lst, default_wild in (("party", enc.get("party", []), False), ("wild", enc.get("wild", []), True)):
        for ent in lst:
            if "trainer" in ent:
                t = ent["trainer"]
                spec = build_trainer(r, t["name"], t.get("level", 5), t["stats"], t.get("moves"), t.get("skills"), t.get("items"), tuple(ent.get("pos", t.get("pos", (0, 0)))), side_name)
            else:
                spec = build_pokemon(r, ent["species"], ent["level"], ent.get("name"), ent.get("nature"), ent.get("strategy", "balanced"), ent.get("moves"), ent.get("abilities"),
                                     wild=ent.get("wild", default_wild), side=side_name, pos=tuple(ent.get("pos", (0, 0))), item=ent.get("item"))
            c = Combatant(r, spec)
            c.side = side_name
            (party if side_name == "party" else wild).append(c)
    everyone = party + wild
    # Native passives can read other actors and local weather during admission.
    e.gm.everyone = everyone
    e.everyone = everyone
    import world_entities as WORLD
    WORLD.actor_index(e)
    for c in everyone:
        e.register_abilities(c)
    for ent, c in zip([x for x in enc.get("party", [])] + [x for x in enc.get("wild", [])], everyone):
        w = (ent.get("trainer") or {}).get("weapon") or ent.get("weapon")
        if w:
            TURN.equip_weapon(e, c, w)
    return e, enc, party, wild


def run_encounter(root, path, seed=None, ruleset=None, rulings_path=None, hook=None, write=True):
    e, enc, party, wild = load_encounter(root, path, ruleset, rulings_path, seed)
    r = e.r
    e.log(f"# 인카운터 '{enc.get('name', path)}' (seed {e.seed}, 룰셋 {r.ruleset.name})")
    e.log("참가자: " + "; ".join(describe(c.spec) for c in party + wild))
    e.log("")
    rounds = int(enc.get("rounds", 10))
    turn_no = 0

    def encounter_active():
        return all(any(not c.fainted and not c.captured and c.on_field for c in side)
                   for side in (party, wild))

    try:
        for rnd in range(1, rounds + 1):
            alive_w = [c for c in wild if not c.fainted and not c.captured and c.on_field]
            alive_p = [c for c in party if not c.fainted and not c.captured and c.on_field]
            if not alive_w or not alive_p:
                break
            e.log(f"## 라운드 {rnd}")
            prepared = e.prepare_initiative_schedule(alive_p + alive_w, source="combat/initiative")
            if prepared['status'] == 'pending':
                e.log("전투 보류: 이니셔티브 결정 필요 — 라운드/시간 진행 없음", "combat/initiative")
                break
            schedule = e._initiative_schedule
            order = [schedule['slots'][key]['actor'] for key in schedule['order']]
            e.start_round(order)
            # Declare source-authenticated ordinary Priority at the actual
            # between-turn boundary. Each native borrowed turn consumes its
            # original schedule slot below, without a second owner clock.
            hooked = set()
            for c in order:
                if not encounter_active():
                    break
                if c.fainted or c.captured or not c.on_field:
                    continue
                enemies_c = wild if c in party else party
                k, m, _ = choose_action(e, c, enemies_c, party if c in party else wild)
                if k == "move" and m and e.r.move(m).get('_source',{}).get('file')=='db/moves.csv':
                    priority = PRIORITY.classify(e.r,m)
                    if priority and priority['variant']=='plain':
                        if hook is not None:
                            hook(e, c, rnd)
                            hooked.add(c.entity_id)
                        if c.fainted or c.captured or not c.on_field:
                            continue
                        k, m, target = choose_action(e, c, enemies_c, party if c in party else wild)
                        current = PRIORITY.classify(e.r,m) if k == 'move' and m != 'struggle' else None
                        if current and current['variant'] == 'plain':
                            turn_no += 1
                            e.log("우선 선언: " + c.name, "action_type/우선-행동")
                            e.use_priority_move(c, target, m)
                            e.finish_initiative_reaction()
            for c in order:
                if not encounter_active():
                    break
                slot = e.initiative_schedule_status()['next']['slot']
                if INTERRUPTS._due(e, slot) is not None:
                    e.settle_borrowed_turn()
                    continue
                if hook is not None and c.entity_id not in hooked:
                    hook(e, c, rnd)
                if c.fainted or c.captured or not c.on_field:
                    SCHEDULE.skip_unavailable(e, c)
                    continue
                turn_no += 1
                e.start_of_turn(c, initiative_count=schedule['initiative_values'][slot])
                enemies = wild if c in party else party
                allies = party if c in party else wild
                kind, mid, target = choose_action(e, c, enemies, allies)
                if kind == "repel":
                    from common_checks import PendingDecision
                    result=e.resolve_repel_flee(c)
                    if isinstance(result,PendingDecision) or isinstance(result,dict) and result.get('status')=='pending':
                        e.log('Repel retreat awaits an actual GM route/time observation; turn remains open','C09-012')
                        return e,party,wild
                elif kind == "ball":
                    e.approach(c, target, 4 + 3)
                    e.log(f"  {c.name}이(가) {target.name}에게 몬스터볼을 던진다 (거리 {cheb(c.pos, target.pos)})")
                    e.throw_ball(c, target)
                elif kind == "move":
                    e.use_move_on(c, target, mid, party + wild)
                e.end_of_turn(c)
                if not encounter_active():
                    break
            # Exhausting initiative while both sides remain active completes a round.
            # A decisive action has no inferred within-round timestamp, even when it
            # belongs to the last initiative entry.
            if encounter_active():
                e.end_round()
            e.log("상태: " + "; ".join(map(repr, party + wild)))
            e.log("")
    except (HEAVY.HeavyPending, PASSIVE_EVENTS.PassiveEventPending) as pending:
        if isinstance(pending, PASSIVE_EVENTS.PassiveEventPending):
            PASSIVE_EVENTS.report_driver_pending(e,pending)
        else:
            HEAVY.report_driver_pending(e,pending)
        if write:
            name=enc.get("name",os.path.basename(path).split(".")[0])
            with open(os.path.join(root,f"output/encounter-{name}.md"),"w",encoding="utf-8") as pending_log:
                pending_log.write("\n".join(e.log_lines)+"\n")
        return e, party, wild
    # A round limit pauses a still-active encounter: preserve combat state.
    # Actual defeat/capture/withdrawal ends the encounter, not the narrative scene.
    if not encounter_active():
        e.end_encounter(party + wild)
    e.log("## 결과")
    e.log("; ".join(map(repr, party + wild)))
    won = all(c.fainted or c.captured or not c.on_field for c in wild)
    e.log(f"결과: {'파티 승리' if won else '미결/야생 승리'} — 포획 {sum(1 for c in wild if c.captured)}, 기절 {sum(1 for c in party + wild if c.fainted)}")
    if write:
        name = enc.get("name", os.path.basename(path).split(".")[0])
        open(os.path.join(root, f"output/encounter-{name}.md"), "w", encoding="utf-8").write("\n".join(e.log_lines) + "\n")
    return e, party, wild


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "."
    path = next((a for a in sys.argv[2:] if a.endswith(".json")), "data/encounters/lakeside.json")
    seed = next((int(a) for a in sys.argv[2:] if a.isdigit()), None)
    ruleset = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--ruleset=")), None)
    rp = os.path.join(root, "data/gm-rulings.json") if "--rulings" in sys.argv else None
    eng, _, _ = run_encounter(root, path, seed, ruleset, rp)
    print("\n".join(eng.log_lines[-4:]))
