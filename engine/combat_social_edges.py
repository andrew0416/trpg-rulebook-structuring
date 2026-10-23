"""Owned trainer social edges, with actual hit and initiative-count lifetime."""
import skill_modifiers as SKILL
import combat_timing as TIMING
import composition_derive as COMPOSITION

FLUSTER = "edge/번뜩이는-카리스마"
SMOOTH = "edge/원만함"
POLICIES = {
    FLUSTER: {"aliases": ("번뜩이는 카리스마", "Flustering Charisma"), "skills": ("매력", "교활"), "rank": 4},
    SMOOTH: {"aliases": ("원만함", "Smooth"), "skills": ("매력", "집중"), "rank": 5},
}

def identity(name):
    for uid, spec in POLICIES.items():
        if SKILL.key(name) in {SKILL.key(x) for x in (uid, *spec["aliases"])}:
            return uid
    return None

def owns(engine, actor, uid):
    edges, feats = actor.spec.get("edges", []), actor.spec.get("feats", [])
    if not isinstance(edges, (list, tuple)) or not isinstance(feats, (list, tuple)):
        raise ValueError("edge and feature ownership must be lists")
    names = [*edges, *feats]
    count = sum(identity(name) == uid for name in names)
    if not count:
        return False
    if actor.kind != "trainer" or count != 1:
        raise ValueError("social edge requires exactly one trainer acquisition")
    if engine.r._selected_rule(uid) != uid:
        raise ValueError("selected social edge variant requires its own policy")
    spec = POLICIES[uid]
    if not any(SKILL.rank(engine.r, actor, skill)[2] >= spec["rank"] for skill in spec["skills"]):
        raise ValueError("social edge prerequisite is not established")
    return True

def validate(engine, actor):
    for uid in POLICIES:
        owns(engine, actor, uid)

def register_owned(engine, actor, name):
    uid = identity(name)
    if uid is None:
        return False
    owns(engine, actor, uid)
    engine.log(f"    {actor.name}: {uid} 실제 사회적 명중/회피/내성 경로 등록", uid)
    return True

def social(attacker, move):
    import effects_ext as EXT
    keys = EXT.keywords_for(attacker, move)
    return "사회적" in keys or "Social" in keys

def penalty_records(actor):
    return [x for x in TIMING.records(actor) if x.get("source") == FLUSTER]

def preflight(engine, attacker, target, move, mm, *, applying=False):
    validate(engine, attacker)
    validate(engine, target)
    __import__("provocateur").preflight(engine,attacker,target,move)
    if applying and social(attacker, move) and owns(engine, attacker, FLUSTER):
        learned = {engine.r.resolve_move(uid) for uid in attacker.moves}
        if move["id"] not in learned:
            raise ValueError("Flustering Charisma social activation requires a learned move or separately sourced grant policy")
        TIMING.current(engine)
        if penalty_records(target):
            raise ValueError("overlapping Flustering Charisma penalties need an explicit stacking policy before attack cost")

def evasion_bonus(engine, actor, move, mm, attacker):
    if not social(attacker, move) or not owns(engine, actor, SMOOTH):
        return 0
    if actor.fainted:
        return 0
    if any(e.get("type") == "implied_by" and actor.conditions.intersection(e.get("conditions", ()))
           for e in engine.r.condition_effects("취약")):
        return 0
    if any(e.get("type") == "evasion_disabled" and not e.get("only")
           for cond in actor.conditions for e in engine.r.condition_effects(cond)):
        return 0
    return 4

def after_hit(engine, attacker, target, move, mm, hit):
    if not hit or not social(attacker, move) or not owns(engine, attacker, FLUSTER):
        return
    count = TIMING.current(engine)
    if penalty_records(target):
        raise ValueError("unresolved overlapping Flustering Charisma activation")
    TIMING.install(engine, target, {"source": FLUSTER, "count_deadline": (engine.round_no + 1, count),
                                  "volatile_save_modifier": -2, "attacker": attacker, "move_id": move["id"]})
    engine.log(f"    {target.name}: 다음 라운드 카운트 {count}까지 휘발성 상태 내성 -2", FLUSTER)

def save_bonus(engine, actor, condition):
    rows = [{'id':SMOOTH,'source':SMOOTH,'value':2}] if condition in ("난동", "헤롱헤롱") and owns(engine, actor, SMOOTH) else []
    if engine.r.condition_class(condition) == "volatile":
        rows += [{'id':FLUSTER+':'+str(i),'source':FLUSTER,'value':x.get('volatile_save_modifier',0)}
                 for i,x in enumerate(penalty_records(actor))]
    return COMPOSITION.derive(0,rows,[{'law':'add','contributors':[r['id'] for r in rows]}] if rows else [])['value']
