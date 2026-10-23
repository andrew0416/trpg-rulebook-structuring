import state_fields as STATE_FIELDS
"""
전투원 생성기: 종 + 레벨 → 전투원 spec (룰북 '포켓몬 스탯 분배' pokemon/stat-build 를 따른다).
  - 스탯 포인트 = level + 10 (A층 단위에서 읽음), 성격(up +2 / down -2, HP 는 ±1), 기본 스탯의 대소 관계를 보존하며 분배
  - 기술: 학습 데이터(learnset_links)의 레벨업 기술 가운데 level 이하, 가장 늦게 배운 6개 (지정하면 그대로)
  - 특성: 학습 데이터의 '기본 특성' 첫 번째 (지정 가능), 재능·이동·크기·체급·스킬은 종 데이터에서
  - 커스텀 종(data/custom/species/*.json)도 같은 경로로 들어온다 (Rules.species 에 합쳐짐, 출처 'custom')
사용: build_pokemon(rules, "뚜벅쵸", 13, name="뚜벅초 A", nature="끈기", strategy="special", wild=True, pos=(9, 7))
"""
import arithmetic_policy as M
from rulings import calc
import copy
import math

STATS = ["hp", "atk", "def", "spa", "spd", "spe"]
STAT_KO = {"HP": "hp", "공격": "atk", "방어": "def", "특공": "spa", "특수공격": "spa", "특방": "spd", "특수방어": "spd", "스피드": "spe"}
STRATEGY = {   # 분배 가중치 (기본 스탯 비례 × 가중치) — 대소 관계 보존 규칙 때문에 가중치는 '우선순위' 역할만 한다
    "balanced": {}, "attack": {"atk": 2.0, "spe": 1.3}, "special": {"spa": 2.0, "spe": 1.3}, "defense": {"def": 1.7, "spd": 1.7, "hp": 1.5}, "fast": {"spe": 2.5}, "bulky": {"hp": 2.5},
}


def species_lookup(rules, key):
    sp = rules.species
    if key in sp:
        return sp[key]
    if "pokemon/" + key in sp:
        return sp["pokemon/" + key]
    for s in sp.values():
        if s["name"] == key or s.get("eng", "").lower() == str(key).lower():
            return s
    raise KeyError(f"종 없음: {key}")


def nature_base(base, nature=None, rules=None):
    """Species stats after Nature, before allocated points and vitamins."""
    stats = dict(base)
    if nature is not None:
        if rules is None:
            raise ValueError("mechanical Nature requires its selected rules")
        import nature_state as NATURE
        nat = NATURE.describe(rules, nature)
        rule = rules.mech("pokemon/stat-build")["nature"]
        if not nat["neutral"]:
            up, down = nat["up_stat"], nat["down_stat"]
            stats[up] += rule["hp_delta"] if up == "hp" else rule["up"]
            stats[down] = max(1, stats[down] - (rule["hp_delta"] if down == "hp" else rule["down"]))
    return stats


def allocation_plan(base, points, strategy="balanced", nature=None, rules=None, *, excluded=(), relation_exempt=(), base_sources=(), point_budgets=(), fixed_point_sources=()):
    import growth_stats as GROWTH
    return GROWTH.allocate(base,points,strategy,nature,rules,excluded=excluded,relation_exempt=relation_exempt,base_sources=base_sources,point_budgets=point_budgets,fixed_point_sources=fixed_point_sources)


def allocate_stats(base, points, strategy="balanced", nature=None, rules=None, *, excluded=(), relation_exempt=()):
    return allocation_plan(base,points,strategy,nature,rules,excluded=excluded,relation_exempt=relation_exempt)['stats']


def allocation_base(rules, spec, *, base_stats=None):
    """Nature, template and vitamin adjustments, optionally over a temporary form base."""
    import growth_stats as GROWTH,pokemon_stat_edges as EDGES
    raw=species_lookup(rules, spec["species"])["base_stats"] if base_stats is None else base_stats
    base = nature_base(GROWTH.sourced_base(raw,EDGES.base_sources(rules,spec)), spec.get("nature"), rules)
    from actor_templates import has_soulless
    if has_soulless(spec):
        base["hp"] = 0
    for stat, value in spec.get("vitamin_bonus", {}).items():
        base[stat] += value
    return base


def record_allocation(rules, spec, event, **details):
    """Keep current allocation plus an append-only history (including legacy imports)."""
    base = allocation_base(rules, spec)
    allocation = {st: spec["stats"][st] - base[st] for st in STATS}
    spec["stat_allocation"] = allocation
    spec.setdefault("stat_history", []).append({"event": event, "level": spec["level"], "species": spec["species"],
        "base": base, "allocation": dict(allocation), "stats": dict(spec["stats"]), **details})


def stat_increment_plan(rules, spec, points=1, strategy=None, choice=None, *, growth_context=None):
    import growth_stats as GROWTH
    allocate = GROWTH.increment_forms if 'form_growth_allocations' in spec else GROWTH.increment
    return allocate(rules,spec,points,strategy,choice,growth_context=growth_context)


def add_stat_points(rules, spec, points=1, strategy=None, choice=None, *, growth_context=None):
    return stat_increment_plan(rules,spec,points,strategy,choice,growth_context=growth_context)['stats']


def build_pokemon(rules, species, level, name=None, nature=None, strategy="balanced", moves=None, abilities=None, wild=False, side=None, pos=(0, 0), item=None, extra=None):
    M.validate_source(rules)
    sp = species_lookup(rules, species)
    import example_species as EXAMPLES
    EXAMPLES.require(rules,sp)
    if sp.get("example_initial_moves"):
        if moves is not None and {rules.move_id(x) if x!="struggle" else x for x in moves}-{"struggle"}!=set(sp["example_initial_moves"]):raise ValueError("example requires its complete initial natural move list")
        moves=list(sp["example_initial_moves"])
    if sp.get("name") == "알":
        raise ValueError("an unhatched egg uses pokemon_entities state, not Combatant stat allocation")
    points = M.floor(calc(rules.mech("pokemon/stat-build")["stat_points"], {"level":level}))
    from actor_templates import has_soulless
    initial_plan = allocation_plan(sp["base_stats"], points, strategy, nature, rules,
                           excluded=("hp",) if has_soulless(sp) else ())
    stats = copy.deepcopy(initial_plan["stats"])
    ls = rules.learnsets.get(sp["name"], {})
    links = rules.learnset_links.get(sp["name"], {})
    if moves is None:
        learned = [(m.get("level", 0), m["to"]) for m in links.get("moves", []) if m.get("source") == "level_up" and m.get("to") and m.get("level", 0) <= level]
        learned = [mid for _, mid in sorted(learned, key=lambda x: x[0]) if mid in rules.moves and mid not in rules.excluded_moves]
        seen, uniq = set(), []
        for mid in learned:
            if mid not in seen:
                seen.add(mid)
                uniq.append(mid)
        moves = uniq[-6:] or ["struggle"]
    if "struggle" not in moves:
        moves = list(moves) + ["struggle"]
    pending_creation_ability=abilities is None and not (extra and "abilities" in extra)
    if abilities is None:
        ab = (ls.get("abilities") or {}).get("기본 특성") or []
        ab = EXAMPLES.resolved_basic_choices(rules,sp,ab)
        abilities = []
        # Soulless fixes the default ability in its own source contract.
        # Ordinary species still retain the explicit, unresolved birth choice.
        if pending_creation_ability and has_soulless(sp):
            abilities = ["불가사의부적"]
            pending_creation_ability = False
    spec = {"id": STATE_FIELDS.new_id("pokemon"), "name": name or sp["name"], "kind": "pokemon", "species": sp["id"], "level": level, "stats": stats,
            "types": list(sp["types"]), "capabilities": list(sp.get("capabilities") or []), "naturewalk": copy.deepcopy(sp.get("naturewalk")), "movement": dict(sp.get("movement") or {"land": 4}),
            "movement_basis": "base", "power_basis": "base",
            "size": sp.get("size"), "weight_class": sp.get("weight_class", 1), "moves": moves, "abilities": abilities, "nature": nature, "strategy": strategy,
            "skills": {k: str(v["rank"])+"d6"+format(int(v.get("mod", 0)), "+d") for k, v in (rules.species_skills.get(sp["name"]) or {}).items()} if rules.species_skills.get(sp["name"]) else {},
            "pos": tuple(pos), "wild": wild, "side": side or ("wild" if wild else "party"), "item": item,
            "evolutions_remaining": _evolutions_left(ls, sp["name"]), "source": sp.get("source", "db"), "_built": True}
    if sp.get("example_definition"):
        spec["example_definition"]=copy.deepcopy(sp["example_definition"])
    if extra:
        spec.update(extra)
        # Species values are bases; supplied sheet totals keep their import semantics.
        if "movement" in extra and "movement_basis" not in extra:
            spec["movement_basis"] = "current"
        if "power" in (extra.get("movement") or {}) and "power_basis" not in extra:
            spec["power_basis"] = "current"
    from actor_templates import validate_soulless_default
    validate_soulless_default(rules,spec)
    EXAMPLES.validate_spec(rules,spec)
    import species_classification as CLASSIFICATION
    CLASSIFICATION.produce(rules, spec)
    import lifetime_consumables as LIFETIME
    LIFETIME.fresh(rules,spec)
    import pokemon_progression as PROGRESSION
    PROGRESSION.fresh(rules, spec, explicit_balance=bool(extra and "tutor_points" in extra))
    if pending_creation_ability:
        import growth_milestones as MILESTONES
        MILESTONES.offer(spec,'ability:creation',source='pokemon/level-up',
            stage={'kind':'creation','level':spec['level'],'species':spec['species']},
            options=MILESTONES.ability_options(rules,spec,'creation'))
    import move_state as MOVES_STATE
    MOVES_STATE.record_natural_opportunities(rules, spec, reason="initial known-move state at observed species and level")
    MOVES_STATE.validate_spec(rules, spec)
    record_allocation(rules, spec, "initial")
    # Only the allocation actually produced here is evidence. Arbitrary extra
    # overrides require an explicit import instead of reverse-engineered points.
    if spec['stats']==initial_plan['stats'] and spec['species']==sp['id'] and spec.get('nature')==nature and spec['level']==level:
        spec['initial_allocation']=copy.deepcopy(initial_plan)
    return spec


def evolution_stages(ls):
    """Preserve sourced stage, species name and conditions for native consumers."""
    import re
    result=[]
    for raw in ls.get('evolution') or []:
        match=re.match(r"\s*(\d+)\s*-\s*([^\s,]+)\s*(.*)",str(raw))
        if match:result.append((int(match[1]),match[2],match[3].strip()))
    return result


def _evolutions_left(ls, name):
    """진화 목록 '1 - 뚜벅쵸', '2 - 냄새꼬 20이상', '3 - 라플레시아 …', '3 - 아르코 …' → 최대 단계 - 내 단계 (분기는 같은 단계)."""
    rows=evolution_stages(ls)
    if not rows:
        return 0
    stages = []
    mine = None
    for st,label,_ in rows:
        stages.append(st)
        if label == name or name in label:
            mine = st if mine is None else min(mine, st)
    if not stages:
        return 0
    return max(0, max(stages) - (mine if mine is not None else min(stages)))


def build_trainer(rules, name, level, stats, moves=None, skills=None, items=None, pos=(0, 0), side="party", abilities=None, extra=None):
    from trainer_capabilities import CORE_POWER_POLICY
    spec = {"id": STATE_FIELDS.new_id("trainer"), "name": name, "kind": "trainer", "level": level, "stats": dict(stats), "types": [], "moves": list(dict.fromkeys([*(moves or []), "struggle"])),
            "skills": dict(skills or {}), "items": dict(items or {"poke_ball": 0}), "pos": tuple(pos), "side": side, "abilities": list(abilities or []), "movement": {}, "size": "중형", "movement_basis": "trainer_base", "power_basis": "derived", "power_policy": CORE_POWER_POLICY, "_built": True}
    if extra:
        spec.update(extra)
        if "movement" in extra and "movement_basis" not in extra:
            spec["movement_basis"] = "current"
        if "power" in (extra.get("movement") or {}) and "power_basis" not in extra:
            spec["power_basis"] = "current"
        if spec["power_basis"] != "derived" and "power_policy" not in extra:
            spec.pop("power_policy", None)
    return spec


def build_quick_npc(rules, name, level, **options):
    """Source-adopted quick NPC with explicit prerequisites and combat budget."""
    import quick_npc
    return quick_npc.build(rules, name, level, **options)


def describe(spec):
    st = spec["stats"]
    return f"{spec['name']} (Lv{spec['level']} {spec.get('species', spec['kind'])}, {'/'.join(spec.get('types') or ['-'])}) HP{st['hp']} A{st['atk']} D{st['def']} SA{st['spa']} SD{st['spd']} S{st['spe']} | 기술 {[m.split('/')[-1] for m in spec['moves']]} | 특성 {spec.get('abilities')}"
