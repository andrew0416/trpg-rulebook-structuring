"""
전투 밖 진행(다운타임): 경험치 → 레벨업(스탯 포인트·레벨업 기술·특성 슬롯) → 진화, 인카운터 경험치 산정, 트레이너 경험치 뱅크, 휴식·포켓몬 센터·부상 치유, 볼 종류 목록.
A층 단위 data/progression-rules.json (pokemon/experience-table, pokemon/level-up, pokemon/evolution, pokemon/experience-award, trainer/experience) 과 combat/resting 을 읽는다.
spec(빌더가 만든 전투원 spec)을 직접 고치므로 전투 밖에서 쓰고, 전투 중에는 engine.use_item(이상한사탕) 경로로 들어온다.
  python -X utf8 -I engine/downtime.py <root>        # 데모: 이상해씨 5 → 경험치 → 15 진화 → 휴식
"""
import copy
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arithmetic_policy as M
from rulings import calc
import frequency as FREQ
import injury_recovery as INJURY
import bandages as BANDAGES
from rest_intervals import plan_rest
from builder import allocate_stats, species_lookup, _evolutions_left, add_stat_points, record_allocation  # noqa: E402


# ---------- 경험치 표 ----------
def exp_table(rules):
    return {int(k): v for k, v in rules.mech("pokemon/experience-table")["exp_to_reach"].items()}


def level_for_exp(rules, exp):
    tbl = exp_table(rules)
    lv = 1
    for k in sorted(tbl):
        if exp >= tbl[k]:
            lv = k
    return min(lv, rules.mech("pokemon/experience-table")["max_level"])


def exp_for_level(rules, level):
    return exp_table(rules)[max(1, min(100, M.floor(level)))]


# ---------- 경험치 산정 ----------
def award_exp(rules, defeated, players, significance=2.0, challenge=1.0, trainers_fought=()):
    """(적 레벨 합, 참전 트레이너 ×2) × 중요도 × 난이도 ÷ 플레이어 수.

    Return (integer XP, detail). Display factors/total retain finite floats for
    compatibility; values outside that representation use an exact integer or
    numerator/denominator string. This encoding policy adds no game-rule bound
    and does not establish that an arbitrarily large input is source-authorized.
    """
    M.validate_source(rules)
    rule = rules.mech("pokemon/experience-award")
    from fractions import Fraction
    from numbers import Number
    def factor(value, name):
        if isinstance(value, bool) or not isinstance(value, Number):
            raise ValueError(name + " must be a finite numeric factor")
        try:
            return Fraction(str(value))
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            raise ValueError(name + " must be a finite numeric factor") from exc
    significance = factor(significance, "significance")
    challenge = factor(challenge, "challenge")
    lo = factor(rule["significance"]["trivial"][0], "configured minimum significance")
    challenge_lo, challenge_hi = [factor(x, "configured challenge bound") for x in rule["challenge_adjust"]]
    # ch11 explicitly allows x5 or higher. The listed major range is guidance,
    # not an upper clamp. Outside this reader's other configured input bounds,
    # require a deliberate ruling rather than silently changing the chosen value.
    if significance < lo:
        raise ValueError("significance below configured guidance; an explicit ruling is required")
    if not challenge_lo <= challenge <= challenge_hi:
        raise ValueError("challenge outside configured adjustment range; an explicit ruling is required")
    if type(players) is not int or players < 1:
        raise ValueError("players must be a positive integer count")
    defeated, trainers_fought = list(defeated), list(trainers_fought)
    if any(type(level) is not int or level < 1 for level in defeated + trainers_fought):
        raise ValueError("defeated combatant levels must be positive integers")
    base = sum(defeated) + 2 * sum(trainers_fought)
    exact_total = base * significance * challenge
    per = M.ratio(exact_total, players)
    def display_number(value):
        # Display conversion must not invalidate the exact result or emit Infinity
        # (which strict JSON forbids). A string preserves overflowed rational data.
        try:
            displayed = float(value)
        except OverflowError:
            return str(value)
        return displayed if math.isfinite(displayed) else str(value)
    return per, {"base": base, "significance": display_number(significance), "challenge": display_number(challenge),
                 "players": players, "total": display_number(exact_total), "per_player": per}



# ---------- 레벨업 ----------
def _learnset_moves_upto(rules, species_name, level, lo=0, *, spec=None):
    import type_sync as TYPE_SYNC
    import example_species as EXAMPLES
    species=species_lookup(rules,spec['species'] if spec is not None else species_name)
    def allowed(moves):return [mid for mid in moves if EXAMPLES.learning_allowed(rules,species,mid)]
    adapted=TYPE_SYNC.level_up_rows(rules,spec) if spec is not None else None
    if adapted is not None:return allowed([row["move_id"] for row in adapted if lo < row["level"] <= level])
    links = rules.learnset_links.get(species_name, {})
    out = []
    for m in links.get("moves", []):
        if m.get("source") == "level_up" and m.get("to") and lo < m.get("level", 0) <= level and m["to"] in rules.moves:
            out.append((m["level"], m["to"]))
    return allowed([mid for _, mid in sorted(out)])


def gain_exp(rules, spec, amount, log=None, auto_evolve=False, strategy=None, stat_choices=None, *, source_kind="experience", growth_context=None):
    """spec['exp'] 에 더하고 레벨이 오르면 level_up 을 레벨마다 적용. 반환: 적용된 변화 목록."""
    log = log if log is not None else []
    if source_kind not in ('experience','level_grant'):raise ValueError('actual XP award or explicit level grant source required')
    import state_fields as F
    import pokemon_progression as PROGRESSION
    amount=M.floor(amount)
    F.integer(amount,'awarded Pokemon XP',0)
    PROGRESSION.validate(spec)
    if 'exp' not in spec:raise ValueError('actual cumulative Pokemon XP is unknown; observe it before growth')
    if source_kind=='experience':
        import food_effects as FOOD
        amount=FOOD.baby_xp(rules,spec,M.floor(amount))
    original, spec = spec, copy.deepcopy(spec)
    pending_log = []
    output_log, log = log, pending_log
    spec["exp"] = spec.get("exp", exp_for_level(rules, spec["level"])) + M.floor(amount)
    new_level = level_for_exp(rules, spec["exp"])
    log.append(f"{spec['name']}: 경험치 +{amount} → {spec['exp']} (레벨 {spec['level']} → {new_level})")
    while spec["level"] < new_level:
        choices = stat_choices or {}
        choice = choices.get(spec["level"] + 1, choices.get(str(spec["level"] + 1)))
        level_up(rules, spec, log, auto_evolve=auto_evolve, strategy=strategy, stat_choice=choice, growth_context=growth_context)
    original.clear()
    original.update(spec)
    output_log.extend(log)
    return output_log


def level_up(rules, spec, log=None, auto_evolve=False, strategy=None, stat_choice=None, *, growth_context=None):
    """Stage growth; never discard an existing move without an explicit choice."""
    import move_state as MOVES_STATE
    candidate = copy.deepcopy(spec)
    pending_log = []
    _level_up(rules, candidate, pending_log, auto_evolve, strategy, stat_choice, growth_context=growth_context)
    MOVES_STATE.validate_spec(rules, candidate)
    spec.clear()
    spec.update(candidate)
    if log is not None:
        log.extend(pending_log)
        return log
    return pending_log


def _level_up(rules, spec, log=None, auto_evolve=False, strategy=None, stat_choice=None, *, growth_context=None):
    """레벨 +1: 스탯 포인트 +1(기존 배분 보존, 새 포인트만 추가), 새 레벨업 기술 학습(슬롯 부족이면 명시적 잊기 선택 필요), 특성 슬롯, 진화 가능 여부."""
    log = log if log is not None else []
    rule = rules.mech("pokemon/level-up")
    if spec["level"] >= rule["max_level"]:
        log.append(f"{spec['name']}: 최대 레벨")
        return log
    import pokemon_teaching as TEACHING
    TEACHING.preflight_level(rules, spec)
    sp = species_lookup(rules, spec["species"])
    old = dict(spec["stats"])
    from builder import stat_increment_plan
    growth_plan = stat_increment_plan(rules, spec, rule["stat_points_per_level"], strategy, stat_choice, growth_context=growth_context)
    new_stats = growth_plan['stats']
    if not spec.get("stat_history"):
        record_allocation(rules, spec, "import")
    elif spec["stat_history"][-1]["stats"] != old:
        record_allocation(rules, spec, "external_adjustment")
    spec["level"] += 1
    spec["stats"] = new_stats
    if 'form_plans' in growth_plan:
        record=spec['form_growth_allocations']
        spec.setdefault('form_growth_history',[]).append({'kind':'level_up','previous':copy.deepcopy(record),'level':spec['level']})
        record['plans']=copy.deepcopy(growth_plan['form_plans'])
        record['budget']+=growth_plan['points'];record['level']=spec['level']
        spec['form_allocations']['forms']=copy.deepcopy(growth_plan['form_stats'])
    spec.setdefault('growth_investment_events',[]).append({**copy.deepcopy(growth_plan),'level':spec['level'],'species':spec['species']})
    if strategy is not None:
        spec["strategy"] = strategy
    changed = {k: new_stats[k] - old[k] for k in new_stats if new_stats[k] != old[k]}
    import pokemon_stat_edges as STAT_EDGES
    provider=STAT_EDGES.levelup_provider(rules,spec,growth_context) if changed.get("hp",0)>0 else None
    record_allocation(rules, spec, "level_up", delta=changed, choice=stat_choice, **({"provider":provider} if provider else {}))
    import baby_templates as BABY
    BABY.on_level(rules,spec,log)
    import marsupial_state as MARSUPIAL
    MARSUPIAL.on_level(rules,spec,log)
    new_stats=spec['stats']
    changed = {k: new_stats[k] - old[k] for k in new_stats if new_stats[k] != old[k]}
    log.append(f"  레벨 {spec['level']}: 스탯 포인트 +{rule['stat_points_per_level']} (기존 배분 보존) → " + ", ".join(f"{k}{v:+d}" for k, v in changed.items()))
    # 레벨업 기술
    new_moves = [m for m in _learnset_moves_upto(rules, sp["name"], spec["level"], spec["level"] - 1, spec=spec) if m not in spec["moves"] and m not in rules.excluded_moves]
    # All earlier moves remain present. The outer candidate validator rejects
    # insufficient sourced capacity atomically; the GM can choose a forgotten
    # move explicitly before retrying the observed growth event.
    import learning_grant as LEARNING
    LEARNING.learn_moves(rules,spec,candidates=new_moves,selected=new_moves,method='level_up',
        source='pokemon/level-up',reason='native attained level learning')
    for mid in new_moves:
        log.append(f"  기술 {rules.move(mid)['name']} 습득")
    import pokemon_teaching as TEACHING
    TEACHING.on_level(rules, spec)
    import growth_milestones as MILESTONES
    MILESTONES.offer_inheritance(rules,spec)
    # 특성 슬롯
    ls = rules.learnsets.get(sp["name"], {})
    for slot in rule["ability_slots"]:
        if slot["level"] == spec["level"]:
            import growth_milestones as MILESTONES
            pool=MILESTONES.ability_options(rules,spec,spec['level'])
            MILESTONES.offer(spec,'ability:'+str(spec['level']),source='pokemon/level-up',
                stage={'kind':'level','level':spec['level'],'species':spec['species']},options=pool)
            log.append(f"  레벨 {spec['level']} 특성 슬롯 선택 대기: {', '.join(pool)}")
    # 진화
    ev = evolution_options(rules, spec)
    if ev:
        log.append("  진화 가능: " + ", ".join(f"{n} (레벨 {lv}+)" for n, lv in ev))
        import growth_milestones as MILESTONES
        identity='evolution:'+spec['species']
        if identity not in spec.get(MILESTONES.KEY,{}):
            MILESTONES.offer(spec,identity,source='pokemon/level-up',
                stage={'kind':'evolution','level':spec['level'],'species':spec['species']},options=[name for name,_ in ev])
        if auto_evolve:log.append('  진화 대상의 명시적 선택 대기')
    return log


def evolution_options(rules, spec):
    """learnset.evolution 목록에서 현재 종의 다음 단계 가운데 레벨 조건을 만족하는 것 [(종 이름, 최소 레벨)]. 도구·친밀도 조건은 (이름, None) 으로 GM 확인."""
    import underdog_edges as UNDERDOG
    if UNDERDOG.blocks_evolution(rules,spec):return []
    sp = species_lookup(rules, spec["species"])
    ls = rules.learnsets.get(sp["name"], {})
    from builder import evolution_stages
    stages = evolution_stages(ls)
    mine = next((st for st, n, _ in stages if n == sp["name"]), None)
    if mine is None:
        return []
    out = []
    for st, n, cond in stages:
        if st != mine + 1:
            continue
        lv = re.search(r"(\d+)\s*이상", cond)
        if lv:
            if spec["level"] >= int(lv.group(1)):
                out.append((n, int(lv.group(1))))
        else:
            out.append((n, None))
    return out


def evolve(rules, spec, target_species, log=None, *, form_declarations=None, underdog_decision=None):
    """Stage evolution; reject capacity conflicts without forgetting moves."""
    import move_state as MOVES_STATE
    candidate = copy.deepcopy(spec)
    pending_log = []
    result = _evolve(rules, candidate, target_species, pending_log, form_declarations=form_declarations,underdog_decision=underdog_decision)
    if result:
        MOVES_STATE.validate_spec(rules, candidate)
        spec.clear()
        spec.update(candidate)
    if log is not None:
        log.extend(pending_log)
    return result


def evolved_abilities(rules,abilities,old_species,new_species,log):
    order=('기본 특성','숨겨진 특성','대단한 특성')
    old_pools=rules.learnsets.get(old_species['name'],{}).get('abilities') or {}
    new_pools=rules.learnsets.get(new_species['name'],{}).get('abilities') or {}
    old_flat=[a for pool in order for a in old_pools.get(pool,[])]
    flat=[a for pool in order for a in new_pools.get(pool,[])]
    result=[]
    for ability in abilities:
        if ability in flat:result.append(ability)
        elif ability in old_flat and old_flat.index(ability)<len(flat):
            result.append(flat[old_flat.index(ability)])
            log.append(f"  특성 {ability} → {result[-1]} (진화 후 같은 슬롯)")
        else:result.append(ability)
    return result


def _evolve(rules, spec, target_species, log=None, *, form_declarations=None, underdog_decision=None):
    """진화: 새 종의 기본 스탯으로 재분배(성격·전략 유지), 타입·재능·이동·체급 갱신, 특성 재확인, 새 형태의 최소 진화 레벨 미만 기술 중 이전 형태에 없던 것 습득."""
    if 'type_sync' in spec:raise ValueError('Type Synced evolution requires an explicit adapted-species review')
    log = log if log is not None else []
    old_sp = species_lookup(rules, spec["species"])
    new_sp = species_lookup(rules, target_species)
    opts = dict((n, lv) for n, lv in evolution_options(rules, spec))
    import ability_state_projection as ABILITY_STATE_PROJECTION
    option_name=ABILITY_STATE_PROJECTION.evolution_option(rules,spec,target_species,opts)
    if option_name not in opts:
        log.append(f"{spec['name']}: {new_sp['name']} 로 진화 불가 (조건 미충족 또는 다음 단계 아님)")
        return False
    if not spec.get("stat_history"):
        record_allocation(rules, spec, "import")
    elif spec["stat_history"][-1]["stats"] != spec["stats"]:
        record_allocation(rules, spec, "external_adjustment")
    import move_state as MOVES_STATE
    MOVES_STATE.record_natural_opportunities(rules, spec, reason="known natural opportunities before evolution")
    previous_species = spec["species"]
    previous_stats = dict(spec["stats"])
    min_lv = opts[option_name] or spec["level"]
    points = M.floor(calc(rules.mech("pokemon/stat-build")["stat_points"], {"level":spec["level"]}))
    import pokemon_stat_edges as STAT_EDGES
    from builder import allocation_plan
    import underdog_edges as UNDERDOG
    underdog_evolution=UNDERDOG.evolution_points(rules,spec,new_sp,underdog_decision)
    import mixed_sweeper as MIXED
    active_form=spec.get('form_allocations',{}).get('active','base')
    evolution_plan = allocation_plan(new_sp["base_stats"], points, spec.get("strategy", "balanced"), spec.get("nature"), rules, relation_exempt=STAT_EDGES.exemptions(rules,spec),point_budgets=underdog_evolution['budgets'],fixed_point_sources=MIXED.point_sources(rules,spec,form=active_form))
    if 'form_allocations' in spec:
        import growth_stats as GROWTH
        if 'form_growth_allocations' not in spec:
            raise ValueError('explicit existing form investment evidence required')
        migration=GROWTH.evolution_forms(rules,spec,form_declarations,points=points,point_budgets=underdog_evolution['budgets'])
        migration['record']['plans']=MIXED.evolution_plans(rules,spec,migration['record']['plans'])
        migration['forms']={name:{st:plan['stats'][st]+spec.get('vitamin_bonus',{}).get(st,0) for st in plan['stats']} for name,plan in migration['record']['plans'].items()}
        spec.setdefault('form_growth_history',[]).append({'kind':'evolution',
            'previous':copy.deepcopy(spec['form_growth_allocations']),
            'previous_species':previous_species,'species':new_sp['id'],'level':spec['level']})
        spec['form_growth_allocations']=migration['record']
        spec['form_allocations']['forms']=migration['forms']
        evolution_plan=migration['record']['plans'][migration['active']]
    elif form_declarations is not None:
        raise ValueError('evolution form declarations require configured forms')
    else:
        evolution_plan=MIXED.evolution_plans(rules,spec,{'base':evolution_plan})['base']
    spec["stats"] = copy.deepcopy(evolution_plan['stats'])
    for st, dv in spec.get("vitamin_bonus", {}).items():
        spec["stats"][st] = spec["stats"].get(st, 0) + dv
    old_name = spec["name"]
    spec["species"] = new_sp["id"]
    if spec["name"] == old_sp["name"]:
        spec["name"] = new_sp["name"]
    # Evolution changes the species, never the individual identity.
    spec["types"] = list(new_sp["types"])
    spec["capabilities"] = list(new_sp.get("capabilities") or [])
    UNDERDOG.commit_evolution(rules,spec,new_sp,evolution_plan,underdog_evolution)
    from copy import deepcopy
    spec["naturewalk"] = deepcopy(new_sp.get("naturewalk"))
    spec["movement"] = dict(new_sp.get("movement") or {"land": 4})
    spec["size"], spec["weight_class"] = new_sp.get("size"), new_sp.get("weight_class", 1)
    ls_new = rules.learnsets.get(new_sp["name"], {})
    spec["evolutions_remaining"] = _evolutions_left(ls_new, new_sp["name"])
    # 특성: 새 형태의 같은 슬롯 풀로 치환 (이전 특성이 새 풀에 없으면 같은 순번의 특성)
    spec['abilities']=evolved_abilities(rules,spec['abilities'],old_sp,new_sp,log)
    import ability_mastery as ABILITY_MASTERY
    ABILITY_MASTERY.evolve_spec(rules,spec,old_sp,new_sp,log)
    # 기술: 새 형태가 min_lv 미만에서 배우는 것 중 이전 형태 학습표에 없던 것
    old_moves = set(_learnset_moves_upto(rules, old_sp["name"], 100))
    bonus = [m for m in _learnset_moves_upto(rules, new_sp["name"], min_lv - 1) if m not in old_moves and m not in spec["moves"]]
    import learning_grant as LEARNING
    LEARNING.learn_moves(rules,spec,candidates=bonus,selected=bonus,method='evolution',
        source='pokemon/level-up',reason='native explicit evolution learning',position='front')
    for mid in bonus:
        log.append(f"  진화 보너스 기술 {rules.move(mid)['name']} 습득 (새 형태 레벨 {min_lv} 미만 기술)")
    # Keep every known move; the outer validator requires an explicit choice
    # before a capacity-conflicting evolution can commit.
    MOVES_STATE.record_natural_opportunities(rules, spec, reason="known natural opportunities after evolution")
    import pokemon_skill_edges as POKE_EDGES
    POKE_EDGES.species_change(rules,spec,old_sp,new_sp)
    spec.setdefault('allocation_migrations',[]).append({
        'kind':'evolution','species':spec['species'],'previous_species':previous_species,
        'level':spec['level'],'previous_stats':previous_stats,'plan':copy.deepcopy(evolution_plan),
        'growth_event_offset':len(spec.get('growth_investment_events',[]))})
    import growth_milestones as MILESTONES
    identity='evolution:'+previous_species
    if identity in spec.get(MILESTONES.KEY,{}):
        MILESTONES.select(spec,identity,option_name,available=list(opts),reason='explicit evolution target')
    record_allocation(rules, spec, "evolution", previous_species=previous_species, previous_stats=previous_stats)
    log.append(f"{old_name} → {new_sp['name']} 진화 (레벨 {spec['level']}, 타입 {'/'.join(spec['types'])}, 스탯 {spec['stats']})")
    return True


def evolve_combatant(engine,c,target_species,*,form_declarations=None,underdog_decision=None):
    """Apply existing spec evolution to the same live actor, preserving sources."""
    import state_grants as GRANTS
    from copy import deepcopy
    def apply(e,actor):
        if actor.kind!='pokemon':raise ValueError('actual Pokemon evolution target required')
        if getattr(actor,'_nonadditive_stats',None):raise ValueError('evolution during a stat exchange needs its source-specific policy')
        import ability_state_projection as ABILITY_STATE_PROJECTION
        ABILITY_STATE_PROJECTION.preflight_evolution(e.r,actor.spec,target_species)
        candidate=deepcopy(actor.spec);log=[]
        changed=evolve(e.r,candidate,target_species,log,form_declarations=form_declarations,underdog_decision=underdog_decision)
        if not changed:return {'evolved':False,'log':log}
        import world_entities as WORLD
        trainer=WORLD.actor_index(e).get(actor.spec.get('trainer_id'))
        acquisition=None if trainer is None else prepare_first_owned_species(e,trainer,candidate['species'],producer='evolve')
        old_max=max(1,actor.base_max_hp);hp_before=actor.hp
        stats=GRANTS.prepare_stat_baseline(actor,candidate['stats'],new_spec=candidate)
        types=GRANTS.prepare_type_baseline(actor,candidate.get('types',[]))
        weight=GRANTS.prepare_weight_baseline(actor,candidate.get('weight_class'))
        movement=actor.movement+candidate.get('movement',{}).get('land',4)-actor.spec.get('movement',{}).get('land',4)
        if type(movement)is not int or movement<0:raise ValueError('evolution would invalidate effective movement')
        actor.spec.clear();actor.spec.update(candidate);actor.stats=stats;actor._types=types;actor._weight_class=weight;actor.movement=movement
        GRANTS.commit_stat_baseline(actor);GRANTS.commit_type_baseline(actor);GRANTS.commit_weight_baseline(actor)
        movement_row=actor.spec.get('state_grants',{}).get('numbers',{}).get('movement')
        if movement_row is not None:GRANTS._sync_number(actor,'movement',movement_row)
        actor._state_revision=getattr(actor,'_state_revision',0)+1
        proposed=M.ratio(hp_before*actor.base_max_hp,old_max)
        import keep_fighting as KEEP
        actor.hp=KEEP.replace_hp(e,actor,hp_before,proposed,source='pokemon/evolution',loss_kind='evolution',amount=max(0,hp_before-proposed))
        BANDAGES.on_hp_change(e,actor,hp_before,actor.hp)
        ABILITY_STATE_PROJECTION.after_evolution(e,actor)
        GRANTS.reconcile(e,actor,activate_existing=False)
        if acquisition is not None:commit_first_owned_species(e,trainer,acquisition)
        for line in log:e.log('    '+line,'pokemon/evolution')
        return {'evolved':True,'log':log,'entity_id':actor.entity_id,'species_id':actor.spec['species']}
    import keep_fighting as KEEP
    interested=KEEP.interested(engine,c)
    return GRANTS.transition(engine,c,apply,include_rulings=interested,include_grid=interested and engine.grid is not None)


def gain_exp_combatant(engine, c, amount, *, stat_choices=None):
    """Apply the existing growth policy atomically to the actual state graph."""
    import state_grants as GRANTS
    return GRANTS.transition(engine, c, lambda staged_engine, staged_c:
                             _gain_exp_combatant(staged_engine, staged_c, amount,stat_choices=stat_choices))


def _gain_exp_combatant(engine, c, amount, *, stat_choices=None):
    split=__import__('csv_item_form_contracts').experience_split(engine,c,amount,stat_choices=stat_choices)
    if split is not None:return split
    return _gain_exp_unsplit_combatant(engine,c,amount,stat_choices=stat_choices)


def _gain_exp_unsplit_combatant(engine, c, amount, *, stat_choices=None):
    """전투 중 경험치(이상한사탕 등): 'to next level' 이면 다음 레벨 경험치까지. Combatant 의 spec·level·stats 를 갱신한다."""
    r = engine.r
    M.validate_source(r)
    if getattr(c, "_nonadditive_stats", None):
        raise ValueError("growth during a stat exchange needs the exchange-specific policy")
    old_max_hp = max(1, c.base_max_hp)
    old_level = c.level
    hp_before = c.hp
    import state_grants as GRANTS
    from copy import deepcopy
    candidate = deepcopy(c.spec)
    source_kind='level_grant' if amount=='to next level' else 'experience'
    if amount == "to next level":
        cur = c.spec.get("exp", exp_for_level(r, c.level))
        amount = max(0, exp_for_level(r, c.level + 1) - cur)
    log = gain_exp(r, candidate, amount,source_kind=source_kind,stat_choices=stat_choices,growth_context=(engine,c))
    runtime_stats = GRANTS.prepare_stat_baseline(c, candidate["stats"])
    runtime_types = GRANTS.prepare_type_baseline(c, candidate.get("types", []))
    runtime_weight = GRANTS.prepare_weight_baseline(c, candidate.get("weight_class"))
    c.spec.clear()
    c.spec.update(candidate)
    c.stats = runtime_stats
    c._types = runtime_types
    c._weight_class = runtime_weight
    GRANTS.commit_stat_baseline(c)
    GRANTS.commit_type_baseline(c)
    GRANTS.commit_weight_baseline(c)
    c._state_revision = getattr(c, "_state_revision", 0) + 1
    # Preserve the existing proportional-HP model without inventing a rounding
    # exception: exact ratio, then the selected common floor policy.
    c.hp = M.ratio(hp_before * c.base_max_hp, old_max_hp)
    BANDAGES.on_hp_change(engine,c,hp_before,c.hp)
    import state_grants as GRANTS
    GRANTS.reconcile(engine, c, activate_existing=False)
    import ability_state_projection as ABILITY_PROJECTION
    ABILITY_PROJECTION.level_changed(engine,c,old_level)
    import class_actor_state_actions as CLASS_STATE_ACTIONS
    CLASS_STATE_ACTIONS.observe_level_up(engine, c, old_level, c.level)
    import marsupial_state as MARSUPIAL
    MARSUPIAL.sync(engine)
    for line in log:
        engine.log("    " + line, "pokemon/level-up")
    return log


# ---------- 트레이너 경험치 ----------
def trainer_gain_exp(rules, spec, amount, log=None, reason=""):
    rule = rules.mech("trainer/experience")
    log = log if log is not None else []
    spec["exp_bank"] = spec.get("exp_bank", 0) + M.floor(amount)
    log.append(f"{spec['name']}: 트레이너 경험치 +{amount}" + (f" ({reason})" if reason else "") + f" → 뱅크 {spec['exp_bank']}")
    while spec["exp_bank"] >= rule["exp_per_level"]:
        spec["exp_bank"] -= rule["exp_per_level"]
        spec["level"] += 1
        log.append(f"  트레이너 레벨 {spec['level']} (뱅크 {spec['exp_bank']})")
    return log


def trainer_milestone(rules, spec, log=None, what="이정표"):
    log = log if log is not None else []
    spec["level"] += 1
    log.append(f"{spec['name']}: {what} → 트레이너 레벨 {spec['level']} (경험치 뱅크 무관)")
    return log


def award_trainer_progression(engine,actor,*,kind,request_id,reason,amount=None):
    """Commit an observed trainer experience/milestone event exactly once.

    This advances the existing level/bank consumer. attained_levels identifies
    milestones for downstream entitlement consumers; it is not proof that their
    Edge/Feature/stat choices have been granted or resolved.
    """
    import world_entities as WORLD
    import state_grants as GRANTS
    import resolution_transaction as TX
    import state_fields as FIELDS
    if WORLD.actor_index(engine).get(actor.entity_id) is not actor or actor.r is not engine.r or actor.kind!='trainer':
        raise ValueError('actual registered trainer required')
    if type(reason) is not str or not reason.strip():raise ValueError('trainer progression reason required')
    if kind not in ('experience','milestone'):raise ValueError('explicit trainer progression kind required')
    if kind=='experience':FIELDS.integer(amount,'trainer experience',0)
    elif amount is not None:raise ValueError('milestone has no experience amount')
    rule=engine.r.mech('trainer/experience')
    FIELDS.integer(rule.get('exp_per_level'),'experience per trainer level',1)
    if kind=='milestone' and rule.get('milestone_levels_bypass_bank') is not True:
        raise ValueError('selected milestone policy requires its own progression consumer')
    import trainer_entitlements as ENTITLEMENTS
    ENTITLEMENTS.validate(actor)
    import trainer_milestone_rewards as REWARDS
    REWARDS.validate(actor)
    intent={'kind':kind,'amount':amount,'reason':reason,'entity_id':actor.entity_id,'policy':rule}
    prior=TX.replay_result(actor.spec.get('trainer_progression_events',{}),request_id,intent,fingerprint_field='intent')
    if prior is not None:return prior['result']
    FIELDS.integer(actor.level,'actual trainer level',1)
    FIELDS.integer(actor.spec.get('exp_bank',0),'trainer experience bank',0)
    def apply(e,c):
        before_level=c.level;before_bank=c.spec.get('exp_bank',0)
        if kind=='experience':lines=trainer_gain_exp(e.r,c.spec,amount,reason=reason)
        else:lines=trainer_milestone(e.r,c.spec,what=reason)
        FIELDS.validate_actor(c)
        result={'request_id':request_id,'entity_id':c.entity_id,'kind':kind,
                'level_before':before_level,'level_after':c.level,
                'bank_before':before_bank,'bank_after':c.spec.get('exp_bank',0),
                'attained_levels':list(range(before_level+1,c.level+1)),
                'reason':reason,'source':'trainer/experience','log':list(lines)}
        import trainer_entitlements as ENTITLEMENTS
        result['entitlement_ids']=ENTITLEMENTS.issue(e.r,c,request_id,result['attained_levels'])
        result['special_reward_levels']=[level for level in result['attained_levels'] if level in REWARDS.OPTIONS]
        result['skill_reward_levels']=[level for level in result['attained_levels'] if level in ENTITLEMENTS.SKILL_REWARDS]
        result['stat_reward_levels']=list(result['attained_levels'])
        c.spec.setdefault('trainer_progression_events',{})[request_id]={
            'intent':TX.request_fingerprint(intent),'request':copy.deepcopy(intent),'result':copy.deepcopy(result)}
        ENTITLEMENTS.validate(c)
        REWARDS.validate(c)
        for line in lines:e.log('    '+line,'trainer/experience')
        return copy.deepcopy(result)
    return GRANTS.transition(engine,actor,apply)


def trainer_new_species(rules, spec, species, log=None):
    seen = spec.setdefault("caught_species", [])
    if species in seen:
        return log if log is not None else []
    seen.append(species)
    return trainer_gain_exp(rules, spec, rules.mech("trainer/experience")["new_species_exp"], log, reason=f"처음 보는 종 {species}")


# Native acquisition reuses the actual progression owner, including its source,
# attained levels and entitlement records. No second XP calculation or ledger.
_FIRST_SPECIES_SOURCE={'file':'input/ch11-running-the-game.md',
    'sha256':'5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad'}
_PROGRESSION_FIELDS=('level','exp_bank','trainer_progression_events','trainer_entitlements')


def owned_species(engine,trainer,*,extra=(),species=()):
    """Canonical lifetime history plus observed current ownership; no XP grant."""
    import world_entities as WORLD
    from builder import species_lookup
    WORLD.require_actors(engine,trainer)
    if trainer.kind!='trainer':raise ValueError('actual trainer required for owned species')
    history=trainer.spec.get('caught_species',[])
    if type(history) is not list:raise ValueError('owned species history must be a list')
    values=list(history)
    for pokemon in WORLD.actors(engine,extra=extra):
        if pokemon.kind=='pokemon' and pokemon.spec.get('trainer_id')==trainer.entity_id and pokemon.spec.get('species'):
            values.append(pokemon.spec['species'])
    registry=trainer.spec.get('pokemon_registry',{})
    if type(registry) is not dict:raise ValueError('owned Pokemon registry must be a mapping')
    values.extend(row['species'] for row in registry.values() if isinstance(row,dict) and row.get('species'))
    values.extend(species)
    result=[]
    for value in values:
        if type(value) is not str or not value.strip():raise ValueError('actual species identity required in ownership history')
        identity=species_lookup(engine.r,value)['id']
        if identity not in result:result.append(identity)
    return result


def _progression_state(trainer):
    return {field:copy.deepcopy(trainer.spec[field]) for field in _PROGRESSION_FIELDS if field in trainer.spec}


def prepare_first_owned_species(engine,trainer,species,*,producer):
    """Prepare the existing owner's output before native acquisition costs.

    Capture has no enclosing growth transaction. Run progression on an isolated
    graph now, then commit only its explicit fields together with ownership.
    """
    from builder import species_lookup
    from source_context import verified_source
    import world_entities as WORLD
    if producer not in ('capture','hatch','evolve'):raise ValueError('actual capture, hatch or evolution producer required')
    history=owned_species(engine,trainer)
    identity=species_lookup(engine.r,species)['id']
    if engine.r._selected_rule('trainer/experience')!='trainer/experience':
        raise ValueError('selected first-owned species experience needs its own policy')
    verified_source(engine.r,_FIRST_SPECIES_SOURCE,label='first-owned species experience')
    rule=engine.r.mech('trainer/experience')
    if rule.get('new_species_exp')!=1 or type(rule.get('new_species_exp')) is not int or rule.get('exp_per_level')!=10:
        raise ValueError('selected automatic species experience needs its own policy')
    before=_progression_state(trainer)
    plan={'species':identity,'producer':producer,'trainer_id':trainer.entity_id,'history':history,
          'history_before':copy.deepcopy(trainer.spec.get('caught_species',[])),
          'progression_before':before,'progression_after':None,'result':None}
    if identity in history:return plan
    staged=copy.deepcopy(engine,{id(engine.r):engine.r})
    subject=WORLD.actor_index(staged)[trainer.entity_id]
    result=award_trainer_progression(staged,subject,kind='experience',amount=rule['new_species_exp'],
        request_id='trainer/new-species/'+identity,reason='처음 소유한 종 '+identity)
    plan['progression_after']=_progression_state(subject);plan['result']=copy.deepcopy(result)
    return plan


def commit_first_owned_species(engine,trainer,plan):
    """Only inside the acquisition's existing native state transaction."""
    if trainer.entity_id!=plan['trainer_id'] or _progression_state(trainer)!=plan['progression_before']:
        raise ValueError('trainer progression changed after species acquisition preflight')
    if trainer.spec.get('caught_species',[])!=plan['history_before']:
        raise ValueError('ownership history changed after species acquisition preflight')
    prepared=plan['progression_after']
    if prepared is not None:
        for field in _PROGRESSION_FIELDS:
            if field in prepared:trainer.spec[field]=copy.deepcopy(prepared[field])
            else:trainer.spec.pop(field,None)
        for line in plan['result']['log']:engine.log('    '+line,'trainer/experience')
    history=list(plan['history'])
    if plan['species'] not in history:history.append(plan['species'])
    trainer.spec['caught_species']=history


# ---------- 휴식 ----------
def _extended_rest_benefits(engine,c,log):
    """Apply the sourced four-hour milestone, once per declared rest bout."""
    if c.dead:return
    import effect_lifetime_policy as LIFETIMES
    LIFETIMES.boundary(engine,'extended_rest',c)
    import researcher_features as RF
    RF.extended_rest(c)
    import food_effects as FOOD
    FOOD.extended_rest(engine,c)
    import chef_cooking as CHEF
    CHEF.extended_rest(engine,c)
    import training_features as TRAINING
    TRAINING.extended_rest(engine,c)
    cured=[x for x in sorted(c.conditions) if engine.r.condition_class(x)=='persistent']
    for status in cured:engine.cure_status(c,status)
    import action_points as AP
    import resolution_transaction as REQUESTS
    parent='rest:'+REQUESTS.request_fingerprint({'owner':c.entity_id,'interval':c.spec.get('rest_interval')})
    AP.extended_rest(c,request_id=parent)
    __import__('study_books').after_extended_rest(engine,c)
    FREQ.restore_daily_moves(engine,c,request_id=parent)
    log.append(f'{c.name}: 연속4시간 휴식 → 지속 상태 {len(cured)}개 치료, 제거된 AP 및 조건을 충족한 하루 기술 복원')


def rest(engine,c,minutes,log=None,*,rest_id=None):
    """One qualified uninterrupted rest segment. Same explicit ID declares continuity.
    Without an ID each call is a new bout; temporal adjacency alone proves nothing.
    There is no public option to grant rest credit without elapsed time.
    """
    return rest_many(engine,[c],minutes,log,rest_id=rest_id)[0]


def interrupt_rest(c):
    """Explicit activity/GM declaration ends continuity without resetting daily use."""
    c.spec.pop('rest_interval',None)


def observe_activity(engine,combatants,minutes,*,qualifies_as_rest,reason,rest_id=None):
    """An explicit GM activity classification, using the common group clock/rest plan."""
    import common_checks as C,world_entities as W,state_grants as G,rest_intervals as INTERVALS
    C.integer(minutes,'activity minutes',1)
    if type(qualifies_as_rest) is not bool:raise ValueError('GM must explicitly classify rest')
    if not isinstance(reason,str) or not reason.strip():raise ValueError('GM activity classification reason required')
    if not qualifies_as_rest and rest_id is not None:raise ValueError('non-rest cannot declare rest continuity')
    actors=list({id(c):c for c in combatants}.values());index=W.actor_index(engine)
    if not actors or any(index.get(c.entity_id) is not c for c in actors):raise ValueError('actual world actors required')
    INTERVALS.validate_world(engine,{c.entity_id:c for c in actors})
    engine.preflight_advance_time(minutes*60,actors)
    def apply(e,first,*others):
        group=[first,*others];start=e.elapsed_seconds
        if qualifies_as_rest:rest_many(e,group,minutes,rest_id=rest_id)
        else:
            e.advance_time(minutes*60,group)
            for c in group:interrupt_rest(c)
        rows=[]
        for c in group:
            row={'source':'combat/resting','qualifies_as_rest':qualifies_as_rest,'reason':reason,
                 'start':start,'end':e.elapsed_seconds,'minutes':minutes,
                 'day':c.spec.get('frequency_state',{}).get('day',0),'rest_id':rest_id}
            c.spec.setdefault(INTERVALS.ACTIVITIES,[]).append(row);rows.append(row)
            e.log('  '+c.name+': GM 활동 분류 '+('휴식' if qualifies_as_rest else '휴식 아님')+' — '+reason,'combat/resting')
        return rows
    return G.transition(engine,actors[0],apply,participants=actors[1:])


def rest_many(engine,combatants,minutes,log=None,*,rest_id=None):
    """Commit one shared rest interval and every participant's benefits together."""
    import state_grants as GRANTS
    actors=list({id(c):c for c in combatants}.values())
    def apply(staged,primary,*participants):
        messages=[]
        gains=_rest_many(staged,participants,minutes,messages,rest_id=rest_id)
        return gains,messages
    gains,messages=GRANTS.transition(engine,None,apply,participants=actors)
    if log is not None:log.extend(messages)
    return gains


def _rest_many(engine,combatants,minutes,log=None,*,rest_id=None):
    """Plan all actors, advance one shared interval, then grant each actor once."""
    if type(minutes) is not int or minutes<0:raise ValueError('rest minutes must be a nonnegative integer')
    if rest_id is not None and (not isinstance(rest_id,str) or not rest_id.strip()):raise ValueError('invalid rest id')
    actors=list({id(c):c for c in combatants}.values())
    if not actors:return []
    log=log if log is not None else []
    rule=engine.r.mech('combat/resting');heal_rule=rule['rest_heal']
    heavy=engine.r.mech('combat/injuries')['heavily_injured_at']
    plans=[]
    for c in actors:
        import action_points as AP
        AP.validate(c,source_required=bool(c.spec.get('ap_removed',0)))
        import combat_stage_sources as STAGE_SOURCES
        STAGE_SOURCES.validate(c)
        import food_effects as FOOD
        FOOD.validate_herbal(c)
        previous=c.spec.get('rest_interval')
        spent=c.spec.get('rested_minutes_today',0)
        record,blocks=plan_rest(previous,rest_id=rest_id,now_seconds=engine.elapsed_seconds,
            gap_count=len(engine.unresolved_time_intervals),round_no=engine.round_no,
            day=c.spec.get('frequency_state',{}).get('day',0),injuries=c.injuries,
            base_max_hp=c.base_max_hp,minutes=minutes,rested_minutes_today=spent,
            cap_minutes=heal_rule['max_hours_per_day']*60,block_minutes=heal_rule['per_minutes'])
        before_total=previous['total_minutes'] if previous and rest_id is not None and previous['id']==rest_id else 0
        healing=BANDAGES.rest_healing(engine,c,previous=previous,rest_id=rest_id,blocks=blocks,
            block_minutes=heal_rule['per_minutes'],fraction=heal_rule['fraction'],heavy_threshold=heavy)
        plans.append((c,record,blocks,spent,before_total,healing))
    import study_books as BOOKS
    with BOOKS.rest_scope(engine,plans,minutes,rest_id):
        plans=[(c,record,blocks,spent,before,BANDAGES.rest_healing(engine,c,previous=c.spec.get('rest_interval'),rest_id=rest_id,
            blocks=blocks,block_minutes=heal_rule['per_minutes'],fraction=heal_rule['fraction'],heavy_threshold=heavy,
            caretaker=BOOKS.care_owner(engine,c,rest_id) is not None)) for c,record,blocks,spent,before,healing in plans]
        return _commit_rest_many(engine,actors,plans,minutes,log)


def _commit_rest_many(engine,actors,plans,minutes,log):
    """The admitted shared interval remains one atomic native rest operation."""
    rule=engine.r.mech('combat/resting')
    engine.advance_time(minutes*60,actors)
    gains=[]
    for c,record,blocks,spent,before_total,healing in plans:
        if c.dead:
            log.append(f'{c.name}: 사망 상태는 휴식으로 복구되지 않음');gains.append(0);continue
        c.spec['rest_interval']=record
        c.spec['rested_minutes_today']=spent+minutes
        before=c.hp
        import actor_templates as TEMPLATES
        milestone=rule['extended_rest']['min_hours']*60
        if TEMPLATES.soulless(c):
            import life as LIFE
            if TEMPLATES.soulless_rest_recovery(engine,c,record,before_total,milestone):
                if LIFE.revive(engine,c,1):
                    engine.log(f"    {c.name}: 선택한 영혼없음 휴식 완료로 HP 1 회복", "capability/영혼없음")
        else:
            engine.heal(c,healing,source_kind='rest')
        record['context']['injuries']=c.injuries
        gains.append(c.hp-before)
        log.append(f'{c.name}: 휴식 {minutes}분 (오늘 {spent+minutes}분) → 체력 {before} → {c.hp}')
        if before_total<milestone<=record['total_minutes']:
            _extended_rest_benefits(engine,c,log)
    return gains


def extended_rest(engine,c,hours,log=None,*,rest_id=None):
    """Rest with the same common continuity model; four-hour benefits are shared.
    Natural injury recovery consumes the shared observed no-new-injury interval.
    """
    if type(hours) not in (int,float) or not math.isfinite(hours) or hours<0:raise ValueError('rest hours must be finite and nonnegative')
    rule=engine.r.mech('combat/resting')
    log=log if log is not None else []
    rest(engine,c,M.product(hours,60),log,rest_id=rest_id)
    if c.dead:return log
    if c.spec['rest_interval']['total_minutes']<rule['extended_rest']['min_hours']*60:
        log.append(f'{c.name}: 연장 휴식 최소4시간 미충족')
    healed=INJURY.recover_naturally(engine,c)
    if healed:log.append(f'{c.name}: 관측된 새 부상 없는24시간 → 부상 {healed}개 자연 치유 ({c.injuries}개 남음)')
    return log


def pokemon_center(engine, c, log=None):
    """Complete one uninterrupted treatment interval (ch07:754–758).
    Duration uses injuries present at admission. No within-treatment removal
    schedule is inferred. Other concurrent procedures need separate scheduling.
    """
    log = log if log is not None else []
    INJURY.healed_today(c)
    engine.check_fainted(c)
    if c.dead:
        log.append(f'{c.name}: 사망 상태의 부활은 포켓몬센터 기본 규칙에 없음')
        return log
    rule = engine.r.mech("combat/resting")["pokemon_center"]
    admission_injuries = c.injuries
    per_injury = rule['heavy_per_injury_minutes'] if admission_injuries >= rule['heavily_injured_at'] else rule['per_injury_minutes']
    minutes = rule['base_hours'] * 60 + admission_injuries * per_injury
    engine.advance_time(minutes * 60, [c])
    n = INJURY.heal(engine,c,admission_injuries,source='pokemon_center')
    for status in sorted(c.conditions):
        if status not in ('기절','임시 체력') and engine.r.condition_class(status) in ('persistent','volatile'):
            engine.cure_status(c,status)
    engine.revive(c,max(1,c.max_hp))
    FREQ.restore_daily_moves(engine,c,center=True)
    log.append(f"{c.name}: 포켓몬 센터 {minutes}분 → 체력 회복, 상태이상 치료, 부상 {n}개 제거 ({c.injuries}개 남음)")
    return log


def new_day(c):
    FREQ.new_day(c)
    for k in ("rested_minutes_today", "injuries_healed_today", "center_injuries_today", "injured_today", "daily_feat_uses"):
        c.spec.pop(k, None)


# ---------- 데모 ----------
if __name__ == "__main__":
    from builder import build_pokemon
    from engine import Combatant, Engine, Rules
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    r = Rules(root)
    spec = build_pokemon(r, "이상해씨", 5, strategy="special")
    log = ["# 다운타임 데모: 이상해씨 레벨 5 → 경험치 → 진화 → 휴식", ""]
    per, detail = award_exp(r, defeated=[12, 14, 10], players=2, significance=3, trainers_fought=[8])
    log.append(f"인카운터 경험치: {detail}")
    gain_exp(r, spec, per + 150, log, auto_evolve=True)
    e = Engine(r, 1)
    c = Combatant(r, spec)
    c.hp -= c.max_hp // 2
    c.injuries = 1
    rest(e, c, 120, log)
    extended_rest(e, c, 24, log)
    pokemon_center(e, c, log)
    tr = {"name": "실바나", "level": 5}
    trainer_new_species(r, tr, "이상해씨", log)
    trainer_gain_exp(r, tr, 9, log, "체육관전")
    trainer_milestone(r, tr, log, "배지 획득")
    open(os.path.join(root, "output/downtime-demo.md"), "w", encoding="utf-8").write("\n".join(log) + "\n")
    print("\n".join(log))
