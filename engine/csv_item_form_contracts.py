"""Reversible partner/item/form relations for the remaining CSV form rows."""
from copy import deepcopy

import csv_item_contract_policy as POLICY


STATE = "csv_remaining_form_state"
MERGE_PARTNER = "_csv_form_merge_partner"
MERGE_WORLD = "_csv_form_world"


def _capabilities(actor):
    import state_grants as GRANTS
    return set(GRANTS.effective(actor, "capabilities"))


def _require(actor, name):
    if name not in _capabilities(actor):
        raise ValueError(name + " actual capability required")


def _state(actor):
    value = actor.spec.setdefault(STATE, {"version": 1, "history": []})
    validate_actor(actor)
    return value


def _actor(engine, uid):
    import world_entities as WORLD
    actor = WORLD.actor_index(engine).get(uid)
    if actor is None or actor.r is not engine.r:
        raise ValueError("form relation actor is missing")
    return actor


def _species(actor):
    from builder import species_lookup
    return species_lookup(actor.r, actor.spec["species"])


def _stock_species(actor, name):
    row = _species(actor)
    return row.get("id") == "pokemon/" + name and row.get("_source", {}).get("file") == "db/pokemon.csv"


def _relation(actor, name):
    state = actor.spec.get(STATE, {})
    return state.get(name) if isinstance(state, dict) else None


def require_independent(engine, actor):
    """A removed partner is not an independent command, target or ball subject."""
    marker = actor.spec.get("off_field_reason", {})
    if not isinstance(marker, dict) or marker.get("kind") not in ("as_one_mount", "virus_merge"):
        return
    owner = _actor(engine, marker.get("owner_id"))
    key, field = ("as_one", "mount_id") if marker["kind"] == "as_one_mount" else ("necrozma_merge", "partner_id")
    row = _relation(owner, key)
    if not isinstance(row, dict) or row.get(field) != actor.entity_id:
        raise ValueError("removed form partner has no actual owning relation")
    raise ValueError("removed form partner cannot act or be targeted independently")


def movement_projection(engine, actor, values):
    """Use the shared movement consumer; no second movement state is installed."""
    row = _relation(actor, "necrozma_merge")
    if row is None:
        return values
    import movement_actions as MOVE
    partner = _actor(engine, row["partner_id"])
    other = MOVE.capabilities(engine, partner, environment=False)
    result = dict(values)
    for field in MOVE.MODES:
        if field in other:
            result[field] = max(result.get(field, 0), other[field])
    return result


def naturewalk_provider(engine, actor):
    row = _relation(actor, "as_one")
    return _actor(engine, row["mount_id"]) if row else actor


def skill_pool_projection(actor, skill):
    """Read the actual partner's current pool, retaining the permanent sheet."""
    if skill not in ("athletics", "acrobatics", "combat", "stealth", "perception"):
        return None
    partner = _merge_partner(actor)
    if partner is None:
        return None
    import skill_modifiers as SKILLS
    from pokemon_skill_profiles import pool
    dice = SKILLS.rank(actor.r, partner, skill)[2]
    supplied = [value for key, value in partner.spec.get("skills", {}).items()
                if SKILLS.skill_id(actor.r.skill_policy, key) == skill]
    # rank() authenticates ordinary names and aliases; the Pokemon pool's
    # constant is consumed once by researcher_features' existing native plan.
    try:
        modifier = pool(supplied[0])[1] if supplied else 0
    except ValueError:
        modifier = 0
    return min(6, dice + 1), modifier


def _merge_partner(actor):
    row = _relation(actor, "necrozma_merge")
    if row is None:
        return None
    # This is an actual actor alias, like control_mount's runtime rider list.
    # STATE.partner_id remains authoritative; validate_world rebinds on load.
    partner = getattr(actor, MERGE_PARTNER, None)
    engine = getattr(actor, MERGE_WORLD, None)
    if (engine is None or partner is None or partner.entity_id != row["partner_id"] or partner.r is not actor.r
            or partner.spec.get("off_field_reason") != {"kind": "virus_merge", "owner_id": actor.entity_id}):
        raise ValueError("Virus Merge physical reader requires its actual bound partner")
    import world_entities as WORLD
    index = WORLD.require_actors(engine, partner)
    owner = index.get(actor.entity_id)
    if owner is None or _relation(owner, "necrozma_merge") != row or index[row["partner_id"]] is not partner:
        raise ValueError("Virus Merge physical reader disagrees with the actual world relation")
    return partner


def power_projection(actor, value):
    union = _relation(actor, "weapon_union")
    if union is not None:
        stock, _, crowned = _weapon_union_profile(actor, union)
        value += crowned["movement"]["power"] - stock["movement"]["power"]
    partner = _merge_partner(actor)
    if partner is None:
        return value
    import capability_actions as CAPABILITIES
    return max(value, CAPABILITIES.power(partner))


def jump_projection(actor, values):
    partner = _merge_partner(actor)
    if partner is None:
        return values
    import jump_actions as JUMP
    other = JUMP.limits(partner)
    return {key: max(value, other[key]) for key, value in values.items()}


def merge_necrozma(engine, necrozma, partner, *, willing=False, helpless=False, signature_move=None):
    import state_grants as GRANTS
    return GRANTS.transition(
        engine, necrozma,
        lambda staged, actual, other: _merge_necrozma(
            staged, actual, other, willing=willing, helpless=helpless,
            signature_move=signature_move),
        participants=(partner,),
    )


def _merge_necrozma(engine, necrozma, partner, *, willing=False, helpless=False, signature_move=None):
    _require(necrozma, "바이러스 합체")
    require_independent(engine, necrozma)
    require_independent(engine, partner)
    if necrozma is partner or necrozma.kind != "pokemon" or partner.kind != "pokemon" or not (willing or helpless or partner.fainted):
        raise ValueError("Virus Merge needs one distinct willing or helpless actual Pokemon")
    state = _state(necrozma)
    if ("necrozma_merge" in state or "as_one" in state or not partner.on_field
            or _relation(partner, "necrozma_merge") or _relation(partner, "as_one")):
        raise ValueError("Virus Merge participants are not independently available")
    second = partner.types[1] if partner.types and partner.types[0] == "에스퍼" and len(partner.types) > 1 else partner.types[0] if partner.types else None
    fixed = "move/메테오드라이브" if _stock_species(partner, "솔가레오") else "move/섀도레이" if _stock_species(partner, "루나아라") else None
    if fixed is not None and signature_move not in (None, fixed):
        raise ValueError("this actual species has its fixed Virus Merge signature")
    if fixed is None:
        fixed = signature_move
        if fixed is not None:
            species = _species(partner)
            available = [row for row in engine.r.learnset_links.get(species["name"], {}).get("moves", [])
                         if row.get("source") == "level_up" and row.get("to") == fixed]
            if not available or not any(row.get("level", 0) <= necrozma.level for row in available):
                raise ValueError("signature needs the actual partner species level-up and Necrozma level")
    if fixed is not None and fixed not in engine.r.moves:
        raise ValueError("Virus Merge signature Move must be selected")
    source = "csv-form:necrozma:" + partner.entity_id
    before = {"types": list(necrozma.types), "movement": necrozma.movement,
              "skills": deepcopy(necrozma.spec.get("skills", {})), "partner_on_field": partner.on_field,
              "form": getattr(necrozma, "form", None)}
    partner.on_field = False
    partner.spec["off_field_reason"] = {"kind": "virus_merge", "owner_id": necrozma.entity_id}
    import state_grants as GRANTS
    if second is not None:
        GRANTS.type_operation(necrozma, "set", list(dict.fromkeys(([necrozma.types[0]] if necrozma.types else []) + [second])), source)
    if fixed:
        import state_grants as GRANTS
        GRANTS.grant_moves(necrozma, [fixed], source, "form", owner_id=necrozma.entity_id,
                          lifetime="merged", rule_id="C2CSV/item-data:77:5", mode="learned")
    if _stock_species(partner, "솔가레오"):
        necrozma.form = "네크로즈마 황혼의 갈기"
    elif _stock_species(partner, "루나아라"):
        necrozma.form = "네크로즈마 새벽의 날개"
    state["necrozma_merge"] = {"partner_id": partner.entity_id, "source": source, "before": before,
                                "second_type": second,
                                "signature_move": fixed, "started_at": engine.elapsed_seconds}
    setattr(necrozma, MERGE_PARTNER, partner)
    setattr(necrozma, MERGE_WORLD, engine)
    state["history"].append({"event": "merge", "partner_id": partner.entity_id, "at": engine.elapsed_seconds})
    return deepcopy(state["necrozma_merge"])


def release_necrozma(engine, necrozma):
    state = necrozma.spec.get(STATE)
    row = state.get("necrozma_merge") if isinstance(state, dict) else None
    if not isinstance(row, dict):
        raise ValueError("actual Virus Merge relation required")
    partner = _actor(engine, row["partner_id"])
    import state_grants as GRANTS
    return GRANTS.transition(engine, necrozma,
        lambda staged, actual, other: _release_necrozma(staged, actual),
        participants=(partner,))


def _release_necrozma(engine, necrozma):
    state = _state(necrozma)
    row = state.get("necrozma_merge")
    if not isinstance(row, dict):
        raise ValueError("actual Virus Merge relation required")
    partner = _actor(engine, row["partner_id"])
    import state_grants as GRANTS
    GRANTS.revoke(necrozma, row["source"], engine=engine)
    necrozma.form = row["before"].get("form")
    partner.on_field = row["before"]["partner_on_field"]
    partner.spec.pop("off_field_reason", None)
    state.pop("necrozma_merge")
    necrozma.__dict__.pop(MERGE_PARTNER, None)
    necrozma.__dict__.pop(MERGE_WORLD, None)
    state["history"].append({"event": "release", "partner_id": partner.entity_id, "at": engine.elapsed_seconds})
    return {"released": partner.entity_id}


def _weapon_union_profile(actor, union=None):
    """Read only the actual stock form identities; capability queries stay pure."""
    from builder import species_lookup
    stock = _species(actor)
    identity = stock.get("id")
    if identity in ("pokemon/자시안", "pokemon/자시안-검왕", "pokemon/자시안-역전의-용사"):
        ids, spans, form, item, move = (
            ("pokemon/자시안", "pokemon/자시안-검왕", "pokemon/자시안-역전의-용사"),
            (940, 941, 942), "검왕", "item/녹슨검", "move/거수참")
    elif identity in ("pokemon/자마젠타", "pokemon/자마젠타-방패왕", "pokemon/자마젠타-역전의-용사"):
        ids, spans, form, item, move = (
            ("pokemon/자마젠타", "pokemon/자마젠타-방패왕", "pokemon/자마젠타-역전의-용사"),
            (943, 944, 945), "방패왕", "item/녹슨방패", "move/거수탄")
    else:
        raise ValueError("Weapon Union is limited to actual stock Zacian or Zamazenta")
    hero, crowned = (species_lookup(actor.r, key) for key in ids[:2])
    for value in (stock, hero, crowned):
        source = value.get("_source", {})
        expected = spans[ids.index(value.get("id"))]
        if source.get("file") != "db/pokemon.csv" or source.get("record_span") != [expected, expected]:
            raise ValueError("Weapon Union needs its source-bound stock form rows")
    if union is not None:
        if (union.get("hero_species_id") != hero["id"] or union.get("crowned_species_id") != crowned["id"]
                or union.get("form") != form or union.get("item_id") != item or union.get("move") != move
                or actor.form != form or actor.spec.get("form_allocations", {}).get("active") != form):
            raise ValueError("Weapon Union current form disagrees with its actual source relation")
    return stock, hero, crowned


def capability_baseline(actor, values):
    """Replace only stock Hero contributions, before unrelated grants are added."""
    union = _relation(actor, "weapon_union")
    if union is None:
        return values
    stock, _, crowned = _weapon_union_profile(actor, union)
    removed = set(stock.get("capabilities", ())) - set(crowned.get("capabilities", ()))
    return [value for value in values if value not in removed]


def _weapon_union_allocations(actor, hero, crowned):
    import form_allocations as FORMS
    import growth_stats as GROWTH
    if "form_allocations" not in actor.spec or "form_growth_allocations" not in actor.spec:
        raise ValueError("Weapon Union requires explicit native Hero and Crowned form investments")
    FORMS.project(actor)
    GROWTH.form_projection(actor.r, actor.spec)
    plans = actor.spec["form_growth_allocations"]["plans"]
    form = "검왕" if crowned["id"] == "pokemon/자시안-검왕" else "방패왕"
    normal = [name for name, plan in plans.items() if plan["species_base"] == hero["base_stats"]]
    if (len(normal) != 1 or set(plans) != {normal[0], form}
            or plans[form]["species_base"] != crowned["base_stats"]):
        raise ValueError("Weapon Union allocations must bind exactly the printed Hero and Crowned bases")
    return actor.spec["form_allocations"]


def _weapon_union_source(actor):
    from source_context import verified_source
    verified_source(actor.r, {"file": "input/db/pokemon.csv",
        "sha256": "0b6f0fbe200a362b341322227f9d3885addd8dc0e54e2f7734a3c7a9a24b752c"},
        label="Weapon Union printed species forms")
    if POLICY.definition(actor.r, clause_id="C2CSV/item-data:78:5")["kind"] != "weapon_union":
        raise ValueError("Weapon Union selected source changed")


def _weapon_union_duration(minutes, reason):
    import common_checks as C
    C.integer(minutes, "actual Weapon Union Extended Action minutes", 1)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("actual Weapon Union Extended Action reason required")


def _validate_weapon_union(actor):
    union = _relation(actor, "weapon_union")
    if union is None:
        return
    _weapon_union_source(actor)
    stock, hero, crowned = _weapon_union_profile(actor, union)
    allocation = _weapon_union_allocations(actor, hero, crowned)
    if union.get("allocation_source") != allocation["source"] or union.get("before_form") not in allocation["forms"]:
        raise ValueError("Weapon Union original form allocation is missing")
    _weapon_union_duration(union.get("minutes"), union.get("reason"))
    source = union.get("source")
    if source != "csv-form:weapon-union:" + union.get("instance_id", ""):
        raise ValueError("Weapon Union actual item source identity changed")
    grants = actor.spec.get("state_grants", {})
    issued = grants.get("sources", {}).get(source, {})
    added = sorted(set(crowned["capabilities"]) - set(stock["capabilities"]))
    if (issued.get("rule_id") != "C2CSV/item-data:78:5" or issued.get("lifetime") != "faint_or_exit"
            or issued.get("owner_id") != actor.entity_id or issued.get("move_mode") != "permission"
            or issued.get("grants", {}).get("moves") != [union["move"]]
            or sorted(issued.get("grants", {}).get("capabilities", [])) != added):
        raise ValueError("Weapon Union actual form permission or capabilities changed")
    expected = {"mode": "set", "values": list(crowned["types"]), "fallback": None}
    if grants.get("type_sources", {}).get("sources", {}).get(source) != expected:
        raise ValueError("Weapon Union actual Crowned type source changed")


def weapon_union(engine, actor, item_instance_id, *, minutes, reason):
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor,
        lambda staged, actual: _weapon_union(staged, actual, item_instance_id, minutes=minutes, reason=reason))


def _weapon_union(engine, actor, item_instance_id, *, minutes, reason):
    _weapon_union_duration(minutes, reason)
    _weapon_union_source(actor)
    _require(actor, "무기합일")
    stock, hero, crowned = _weapon_union_profile(actor)
    if crowned["id"] == "pokemon/자시안-검왕":
        item_id, form, move = "item/녹슨검", "검왕", "move/거수참"
    else:
        item_id, form, move = "item/녹슨방패", "방패왕", "move/거수탄"
    allocation = _weapon_union_allocations(actor, hero, crowned)
    obj = getattr(engine, "_physical_objects", {}).get(item_instance_id)
    if (not isinstance(obj, dict) or obj.get("csv_form_item_id", obj.get("item_rule_id")) != item_id
            or actor.entity_id not in (obj.get("owner_id"), obj.get("carrier_id"), obj.get("equipped_by"))):
        raise ValueError("Weapon Union requires its actual Rusted item")
    import world_entities as WORLD
    WORLD.require_physical_access(obj)
    state = _state(actor)
    if "weapon_union" in state:
        raise ValueError("Weapon Union is already active")
    before = actor.form
    import turn as TURN
    if not TURN.spend(engine, actor, "extended", "무기합일"):
        raise ValueError("Weapon Union requires an available actual Extended Action")
    started_at = engine.elapsed_seconds
    engine.advance_time(minutes * 60, [actor])
    if not TURN.can_act(engine, actor):
        # A real clock consequence is retained, rather than rolled back as a declaration error.
        return {"completed": False, "reason": "actor cannot complete the observed Extended Action"}
    source = "csv-form:weapon-union:" + item_instance_id
    import state_grants as GRANTS
    GRANTS.grant_moves(actor, [move], source, "form", owner_id=actor.entity_id, lifetime="faint_or_exit",
                      rule_id="C2CSV/item-data:78:5", mode="permission")
    for capability in sorted(set(crowned["capabilities"]) - set(stock["capabilities"])):
        GRANTS.grant(actor, "capabilities", capability, source, "form", owner_id=actor.entity_id,
                     lifetime="faint_or_exit", rule_id="C2CSV/item-data:78:5")
    if GRANTS.type_operation(actor, "set", crowned["types"], source) is False:
        raise ValueError("Weapon Union Crowned typing is blocked by an actual source")
    import form_allocations as FORMS
    FORMS.switch(engine, actor, form)
    row = {"source": source, "instance_id": item_instance_id, "item_id": item_id,
           "before_form": before, "form": form, "move": move, "started_at": started_at,
           "completed_at": engine.elapsed_seconds,
           "minutes": minutes, "reason": reason, "allocation_source": allocation["source"],
           "hero_species_id": hero["id"], "crowned_species_id": crowned["id"]}
    # The nested native switch commits fresh spec containers; reacquire their owner.
    state = _state(actor)
    state["weapon_union"] = row
    state["history"].append({"event": "weapon_union_enter", **deepcopy(row)})
    return deepcopy(row)


def end_weapon_union(engine, actor, *, minutes, reason):
    import state_grants as GRANTS
    def apply(staged, actual):
        if _relation(actual, "weapon_union") is None:
            return False
        _weapon_union_duration(minutes, reason)
        _validate_weapon_union(actual)
        import turn as TURN
        if not TURN.spend(staged, actual, "extended", "무기합일 종료"):
            raise ValueError("Weapon Union exit requires an available actual Extended Action")
        staged.advance_time(minutes * 60, [actual])
        # An actual faint during the interval has already used the free lifecycle exit.
        if _relation(actual, "weapon_union") is None:
            return True
        return _end_weapon_union(staged, actual, cause="extended", minutes=minutes, reason=reason)
    return GRANTS.transition(engine, actor, apply)


def _end_weapon_union(engine, actor, *, cause="faint", minutes=None, reason=None):
    _validate_weapon_union(actor)
    state = actor.spec.get(STATE)
    row = state.pop("weapon_union", None) if isinstance(state, dict) else None
    if not isinstance(row, dict):
        return False
    import state_grants as GRANTS
    if row["source"] in actor.spec.get("state_grants", {}).get("sources", {}):
        GRANTS.revoke(actor, row["source"], engine=engine)
    import form_allocations as FORMS
    FORMS.switch(engine, actor, row["before_form"])
    _state(actor)["history"].append({"event": "weapon_union_exit", "source": row["source"],
        "instance_id": row["instance_id"], "cause": cause, "minutes": minutes,
        "reason": reason, "ended_at": engine.elapsed_seconds})
    return True


def configure_zygarde(engine, actor, cube_instance_id, *, cells, form_percent, power_construct=False, decompose=False):
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor,
        lambda staged, actual: _configure_zygarde(
            staged, actual, cube_instance_id, cells=cells, form_percent=form_percent,
            power_construct=power_construct, decompose=decompose))


def _configure_zygarde(engine, actor, cube_instance_id, *, cells, form_percent, power_construct=False, decompose=False):
    _require(actor, "지가르데 세포")
    if type(cells) is not int or type(form_percent) is not int or cells not in (10, 50, 100) or form_percent not in (10, 50):
        raise ValueError("Zygarde Cube uses 10, 50 or 100 actual cells and a 10/50 form")
    if (type(power_construct) is not bool or type(decompose) is not bool
            or power_construct != (cells == 100) or (not power_construct and cells != form_percent)):
        raise ValueError("Zygarde cell count/form/Power Construct relation changed")
    cube = _zygarde_cube(engine, actor, cube_instance_id)
    cube_state = cube.get("zygarde_cells")
    if (not isinstance(cube_state, dict) or type(cube_state.get("available")) is not int
            or cube_state["available"] < 0 or not isinstance(cube_state.get("assemblies"), list)):
        raise ValueError("Zygarde Cube requires an observed nonnegative cell stock")
    current = _state(actor).get("zygarde")
    if current and current.get("cube_instance_id") != cube_instance_id:
        raise ValueError("the assembly belongs to a different actual Cube")
    if decompose:
        if not current or current.get("power_construct"):
            raise ValueError("100-cell Power Construct Zygarde cannot be decomposed")
        cube_state["available"] += current["cells"]
        _state(actor).pop("zygarde")
        cube_state["assemblies"] = [row for row in cube_state["assemblies"]
                                    if row.get("actor_id") != actor.entity_id]
        import form_allocations as FORMS
        FORMS.switch(engine, actor, current["before_form"])
        return {"decomposed": True, "returned_cells": current["cells"]}
    if current and current.get("power_construct"):
        current["form_percent"] = form_percent
        for assembly in cube_state["assemblies"]:
            if assembly.get("actor_id") == actor.entity_id:
                assembly["form_percent"] = form_percent
        import form_allocations as FORMS
        FORMS.switch(engine, actor, str(form_percent) + "%폼")
        return deepcopy(current)
    if current:
        raise ValueError("decompose the current reversible Zygarde form before assembling another")
    if cube_state["available"] < cells:
        raise ValueError("Zygarde Cube lacks the actual cells")
    source = "csv-form:zygarde:" + cube_instance_id + ":" + actor.entity_id
    row = {"cube_instance_id": cube_instance_id, "cells": cells, "form_percent": form_percent,
           "power_construct": power_construct, "decomposable": not power_construct,
           "before_form": getattr(actor, "form", None), "source": source, "started_at": engine.elapsed_seconds}
    if power_construct:
        if engine.r._selected_rule("ability/스웜체인지") != "ability/스웜체인지":
            raise ValueError("selected Power Construct source requires its own ability adapter")
        import state_grants as GRANTS
        GRANTS.grant(actor, "abilities", "스웜체인지", source, "form", owner_id=actor.entity_id,
                     lifetime="irreversible_assembly", rule_id="C2CSV/item-data:79:5")
        GRANTS.overlay(actor, source, abilities=[name for name in GRANTS.effective(actor, "abilities")
                       if name not in ("오라브레이크", "ability/오라브레이크")])
        row["source_correction"] = {
            "kind": "spelling_error", "original": "스윔페인지", "effective": "스웜체인지",
            "source": "input/db/item-data.csv:79:6", "corroboration": "input/db/learnsets.csv:791:7",
            "selected_ability": "ability/스웜체인지",
            "reason": "same Zygarde 100-cell ability replacing Aura Break; named by the actual Perfect Form source"}
    import form_allocations as FORMS
    FORMS.switch(engine, actor, str(form_percent) + "%폼")
    cube_state = _zygarde_cube(engine, actor, cube_instance_id)["zygarde_cells"]
    cube_state["available"] -= cells
    _state(actor)["zygarde"] = row
    cube_state["assemblies"].append({"actor_id": actor.entity_id, **deepcopy(row)})
    return deepcopy(row)


def _zygarde_cube(engine, actor, instance_id):
    cube = getattr(engine, "_physical_objects", {}).get(instance_id)
    if (not isinstance(cube, dict) or cube.get("csv_form_item_id", cube.get("item_rule_id")) != "item/지가르데큐브"
            or actor.entity_id not in (cube.get("owner_id"), cube.get("carrier_id"), cube.get("equipped_by"))):
        raise ValueError("actual owned Zygarde Cube required")
    import world_entities as WORLD
    WORLD.require_physical_access(cube)
    return cube


def _cube_moves(engine, actor):
    """The actual species' selected Cube list is separate from ordinary tutors."""
    import re
    species = _species(actor)
    note = engine.r.learnsets.get(species["name"], {}).get("note", "")
    match = re.fullmatch(r"지가르데큐브 기술 목록\s+(.+)", note, re.DOTALL)
    if not match:
        raise ValueError("actual species has no selected Zygarde Cube move list")
    names = [name.strip() for name in match.group(1).replace("\n", " ").split(",") if name.strip()]
    moves = [engine.r.move_id(name) for name in names]
    if not moves or any(mid is None or mid in engine.r.excluded_moves for mid in moves):
        raise ValueError("selected Cube move source is unresolved")
    return list(dict.fromkeys(moves))


def teach_zygarde_move(engine, actor, move_id, *, tutor_points):
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor,
        lambda staged, actual: _teach_zygarde_move(staged, actual, move_id, tutor_points=tutor_points))


def _teach_zygarde_move(engine, actor, move_id, *, tutor_points):
    current = _state(actor).get("zygarde")
    if not current or type(tutor_points) is not int or tutor_points != 1 or move_id not in _cube_moves(engine, actor):
        raise ValueError("actual assembled Zygarde, selected Cube Move and exactly one TP required")
    _zygarde_cube(engine, actor, current["cube_instance_id"])
    import state_grants as GRANTS
    if move_id in GRANTS.effective(actor, "moves"):
        raise ValueError("Cube Move is already known")
    import pokemon_teaching as TEACHING
    TEACHING._debit_points(actor.spec, 1)
    GRANTS.grant_moves(actor, [move_id], "csv-zygarde-cube:" + current["cube_instance_id"] + ":" + move_id, "item", owner_id=actor.entity_id,
                      lifetime="permanent", rule_id="C2CSV/item-data:79:5", tutor_points=tutor_points)
    return {"move_id": move_id, "tutor_points": tutor_points}


def mount_as_one(engine, rider, mount, *, ability, gm_mount_reason=None):
    import state_grants as GRANTS
    return GRANTS.transition(engine, rider,
        lambda staged, actual, other: _mount_as_one(staged, actual, other, ability=ability, gm_mount_reason=gm_mount_reason),
        participants=(mount,))


def _mount_as_one(engine, rider, mount, *, ability, gm_mount_reason=None):
    _require(rider, "혼연일체")
    require_independent(engine, rider)
    require_independent(engine, mount)
    if rider is mount or rider.kind != "pokemon" or mount.kind != "pokemon" or not mount.on_field:
        raise ValueError("As One needs one actual available Pokemon mount")
    import re
    mountable = any(re.fullmatch(r"(?:탑승|Mountable)\s*\d+", value, re.IGNORECASE) for value in _capabilities(mount))
    if not mountable and (not isinstance(gm_mount_reason, str) or not gm_mount_reason.strip()):
        raise ValueError("As One needs an actual Mountable capability or explicit GM suitable-mount decision")
    import move_state as MOVES
    registration = MOVES.ability_registration(engine.r, ability)
    selected = registration["name"] if registration else ability
    base = engine.r.learnsets.get(_species(mount)["name"], {}).get("abilities", {}).get("기본 특성", [])
    basic = [(MOVES.ability_registration(engine.r, name) or {}).get("name", name) for name in base]
    owned = [(MOVES.ability_registration(engine.r, name) or {}).get("name", name) for name in mount.abilities]
    if selected == "불가사의부적" or selected not in basic or selected not in owned:
        raise ValueError("As One needs one non-Wonder-Guard basic mount ability")
    state = _state(rider)
    if ("as_one" in state or "necrozma_merge" in state
            or _relation(mount, "as_one") or _relation(mount, "necrozma_merge")):
        raise ValueError("As One relation already exists")
    before = {"types": list(rider.types), "movement": rider.movement, "mount_on_field": mount.on_field,
              "size": rider.spec.get("size"), "weight_class": rider.spec.get("weight_class")}
    combined_weight = max(filter(lambda x: x is not None, (rider.weight_class, mount.weight_class)), default=None)
    mount.on_field = False
    mount.spec["off_field_reason"] = {"kind": "as_one_mount", "owner_id": rider.entity_id}
    source = "csv-form:as-one:" + mount.entity_id
    import state_grants as GRANTS
    if mount.types:
        GRANTS.type_operation(rider, "set", list(dict.fromkeys(([rider.types[0]] if rider.types else []) + [mount.types[0]])), source)
    chosen = registration["source_id"] if registration and ability == registration["source_id"] else selected
    GRANTS.grant(rider, "abilities", chosen, source, "form", owner_id=rider.entity_id,
                 lifetime="mounted", rule_id="C2CSV/item-data:80:5")
    GRANTS.scalar(rider, "spec.size", mount.spec.get("size", rider.spec.get("size")), source)
    if combined_weight is not None:GRANTS.weight(rider,combined_weight,source)
    mount_source = "csv-form:as-one-mount:" + rider.entity_id
    GRANTS.overlay(mount, mount_source, abilities=[])
    move = "move/아스트랄비트" if _stock_species(mount, "레이스포스") else "move/블리자드랜스" if _stock_species(mount, "블리자포스") else None
    if move:
        GRANTS.grant_moves(rider, [move], source, "form", owner_id=rider.entity_id, lifetime="mounted",
                          rule_id="C2CSV/item-data:80:5", mode="permission")
    state["as_one"] = {"mount_id": mount.entity_id, "source": source, "mount_source": mount_source,
                       "ability": chosen, "ability_source_id": registration["source_id"] if registration else None,
                       "move": move, "gm_mount_reason": gm_mount_reason,
                       "ball_owner_id": rider.entity_id, "before": before, "started_at": engine.elapsed_seconds}
    return deepcopy(state["as_one"])


def dismount_as_one(engine, rider):
    state = rider.spec.get(STATE)
    row = state.get("as_one") if isinstance(state, dict) else None
    if not isinstance(row, dict):
        raise ValueError("actual As One mount relation required")
    mount = _actor(engine, row["mount_id"])
    import state_grants as GRANTS
    return GRANTS.transition(engine, rider,
        lambda staged, actual, other: _dismount_as_one(staged, actual),
        participants=(mount,))


def _dismount_as_one(engine, rider):
    row = _state(rider).pop("as_one", None)
    if not isinstance(row, dict):
        raise ValueError("actual As One mount relation required")
    mount = _actor(engine, row["mount_id"])
    import state_grants as GRANTS
    GRANTS.revoke(rider, row["source"], engine=engine)
    GRANTS.revoke(mount, row["mount_source"], engine=engine)
    mount.on_field = row["before"]["mount_on_field"] and rider.on_field
    mount.spec.pop("off_field_reason", None)
    return {"dismounted": mount.entity_id}


def tera_exit(actor, *, engine=None):
    _require(actor, "테라체인지")
    if engine is None:
        raise ValueError("Tera Change outside combat requires its actual engine")
    import world_entities as WORLD
    import combat_state_lifecycle as COMBAT
    WORLD.require_actors(engine, actor)
    if engine.encounter_active and any(member is actor for member in COMBAT.members(engine)):
        raise ValueError("Tera Change can exit only outside combat")
    import state_grants as GRANTS
    def apply(staged, actual):
        _state(actual)["tera_change"] = {"active": False, "return_pending": True}
        actual.form = "일반"
        return {"active": False}
    return GRANTS.transition(engine, actor, apply)


def encounter_join(engine, actor):
    row = _state(actor).get("tera_change")
    import state_grants as GRANTS
    if "테라체인지" in GRANTS.effective(actor, "capabilities", only=("테라체인지",)) and (row is None or row.get("return_pending")):
        actor.form = "테라스탈"
        _state(actor)["tera_change"] = {"active": True, "return_pending": False,
                                         "returned_at": engine.elapsed_seconds, "action": "free"}
        return True
    return False


def fainted(engine, actor):
    _end_weapon_union(engine, actor)
    row = _relation(actor, "as_one")
    if row:
        other = _actor(engine, row["mount_id"])
    else:
        marker = actor.spec.get("off_field_reason", {})
        other = _actor(engine, marker["owner_id"]) if isinstance(marker, dict) and marker.get("kind") == "as_one_mount" else None
    if other is not None and not other.fainted:
        import keep_fighting as KEEP
        other.hp = KEEP.replace_hp(engine,other,other.hp,0,source='C2CSV/item-data:80:5',loss_kind='as_one',amount=other.hp)
        import life as LIFE
        if other.hp<=0:LIFE.faint(engine, other)


def validate_actor(actor):
    state = actor.spec.get(STATE)
    if state is None:
        return True
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("history"), list):
        raise ValueError("remaining CSV form state is invalid")
    return True


def validate_world(engine, index):
    POLICY.policy(engine.r)
    for actor in index.values():
        validate_actor(actor)
        _validate_weapon_union(actor)
        state = actor.spec.get(STATE, {})
        for key in ("necrozma_merge", "as_one"):
            row = state.get(key)
            if row is not None and row.get("partner_id", row.get("mount_id")) not in index:
                raise ValueError("remaining CSV form partner relation is dangling")
        merge = state.get("necrozma_merge")
        if merge:
            partner = index[merge["partner_id"]]
            if (partner is actor or _relation(partner, "necrozma_merge") or _relation(partner, "as_one")
                    or partner.spec.get("off_field_reason") != {"kind": "virus_merge", "owner_id": actor.entity_id}):
                raise ValueError("Virus Merge relation must bind its one actual removed partner")
            setattr(actor, MERGE_PARTNER, partner)
            setattr(actor, MERGE_WORLD, engine)
        else:
            actor.__dict__.pop(MERGE_PARTNER, None)
            actor.__dict__.pop(MERGE_WORLD, None)
    return True
