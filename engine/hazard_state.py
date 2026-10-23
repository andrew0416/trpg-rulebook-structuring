"""Reviewed battlefield Hazard instances, placement, triggers, and lifetime.

The generic terrain opcode used to collapse one cell to one anonymous mapping.
This module keeps each trap as a physical instance, groups one Move's instances
into a stable region, and projects the instances back through ``engine.hazards``
so existing movement, GM, snapshot, and field-clearing paths share one state.
"""
from copy import deepcopy
import hashlib
import json
import os

import arithmetic_policy as M


NATIVE_MOVES = frozenset((
    "move/끈적끈적네트", "move/압정뿌리기", "move/독압정", "move/스텔스록",
))
COURT_CHANGE = "move/코트체인지"
DERIVED_MOVES = frozenset(("move/거다이암진", "move/거다이강철진"))
REENTRY = "_hazard_reentry_immunity"


class _HazardAuthority:
    def __deepcopy__(self, memo):
        return self


_AUTHORITY = _HazardAuthority()


def _policy_path(rules):
    canonical = os.path.join(rules.root, "data", "hazard-state-policy.json")
    staged = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "hazard-state-policy.json"))
    return canonical if os.path.exists(canonical) else staged


def _sha256(path):
    value = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def policy(rules):
    with open(_policy_path(rules), encoding="utf-8") as handle:
        value = json.load(handle)
    if value.get("schema_version") != 1 or set(value.get("moves", {})) != NATIVE_MOVES | {COURT_CHANGE}:
        raise ValueError("Hazard policy schema changed")
    if set(value.get("derived_moves", {})) != DERIVED_MOVES:
        raise ValueError("derived Hazard policy identity changed")
    for relative, digest in value.get("source_files", {}).items():
        source = os.path.join(rules.root, *relative.split("/"))
        if not os.path.exists(source) or _sha256(source) != digest:
            raise ValueError("Hazard reviewed source file changed: " + relative)
    return value


def _definition(rules, source_id):
    data = policy(rules)
    return (__import__('type_ace').hazard_definition(rules,source_id,data) or __import__('survivalist_class').hazard_definition(rules,source_id,data)
            or data["moves"].get(source_id) or data["derived_moves"].get(source_id))


def _semantic(value):
    if isinstance(value, dict):
        return {key: _semantic(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [_semantic(item) for item in value]
    return deepcopy(value)


def mechanics(rules, move_id, declaration):
    """Adapt only the five exact reviewed Move declarations."""
    if move_id not in NATIVE_MOVES | {COURT_CHANGE}:
        return declaration
    row = policy(rules)["moves"][move_id]
    effects = declaration.get("effects_exec", [])
    if _semantic(effects) != row["effects"]:
        raise ValueError("selected Hazard Move differs from reviewed source policy")
    if move_id == COURT_CHANGE:
        return declaration
    adapted = []
    for index, effect in enumerate(effects):
        if index == 0:
            runtime = dict(effect)
            if "trigger" in runtime:
                runtime["_hazard_source_trigger"] = runtime.pop("trigger")
            adapted.append(dict(runtime, _activation_scope="field", _hazard_native=True))
        else:
            adapted.append(effect)
    return dict(declaration, effects_exec=adapted, _native_hazard_activation=_AUTHORITY)


def field_effects(declaration):
    if declaration.get("_native_hazard_activation") is not _AUTHORITY:
        return []
    move_id = declaration.get("_hazard_move_id")
    # move_id is optional in the declaration; the exact adapted effect is
    # independently checked against every reviewed producer below.
    effects = declaration.get("effects_exec", [])
    selected = [effect for effect in effects if effect.get("_activation_scope") == "field"]
    if len(selected) != 1 or selected[0].get("type") != "create_terrain" or selected[0].get("_hazard_native") is not True:
        return []
    return selected


def target_free(declaration):
    return declaration.get("_native_hazard_activation") is _AUTHORITY and bool(field_effects(declaration))


def _placement(engine, move_id):
    row = policy(engine.r)["moves"].get(move_id)
    return None if row is None else row.get("placement")


def bind(engine, actor, move, aim):
    """Bind the exact selected physical cells before any action or frequency cost."""
    move_id = move.get("id")
    placement = _placement(engine, move_id)
    if move_id not in NATIVE_MOVES or placement is None:
        return None
    if engine.grid is None:
        raise ValueError("Hazard placement requires an actual map before action cost")
    if not isinstance(aim, (list, tuple)):
        raise ValueError("Hazard placement requires an explicit cell list")
    import common_checks as C
    cells = []
    for value in aim:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("Hazard placement requires explicit coordinate pairs")
        cell = tuple(C.integer(x, "Hazard aim coordinate") for x in value)
        if not engine.grid.inside(cell):
            raise ValueError("Hazard placement cell lies outside map")
        cells.append(cell)
    if len(cells) != placement["cells"] or len(set(cells)) != len(cells):
        raise ValueError("Hazard placement requires exactly %d distinct cells" % placement["cells"])
    import body_state as BODY
    from grid import cheb
    origins = BODY.cells(actor, require_complete=True)
    if any(min(cheb(origin, cell) for origin in origins) > placement["within"] for cell in cells):
        raise ValueError("Hazard placement cell is outside the reviewed range")
    if placement.get("contiguous"):
        remaining = set(cells)
        reached = {remaining.pop()}
        while remaining:
            adjacent = {cell for cell in remaining if any(cheb(cell, known) <= 1 for known in reached)}
            if not adjacent:
                raise ValueError("Hazard placement cells must form one contiguous region")
            reached |= adjacent
            remaining -= adjacent
    out = dict(move)
    out["_hazard_cells"] = tuple(sorted(cells))
    return out


def cells(move):
    values = move.get("_hazard_cells")
    if values is None:
        return None
    return set(values)


def init_engine(engine):
    engine._hazard_sequence = 0
    engine._hazard_region_sequence = 0


def _next(engine, field, prefix):
    value = getattr(engine, field, 0) + 1
    setattr(engine, field, value)
    return prefix + str(value)


def _project(engine, cell, envelope):
    instances = envelope["instances"]
    if not instances:
        engine.hazards.pop(cell, None)
        if engine.grid is not None and not envelope["slow_before"]:
            engine.grid.slow.discard(cell)
        return
    first = instances[0]
    envelope.update(name=first["name"], owner=first.get("owner_name") or first.get("owner_side"),
                    effects=deepcopy(first.get("legacy_effects", [])),
                    slow=any(row.get("slow", False) for row in instances))
    if engine.grid is not None:
        if envelope["slow_before"] or envelope["slow"]:
            engine.grid.slow.add(cell)
        else:
            engine.grid.slow.discard(cell)


def _new_envelope(engine, cell, *, slow=False):
    return {"instances": [], "slow_before": bool(engine.grid is not None and cell in engine.grid.slow and not slow),
            "name": "", "owner": "", "effects": [], "slow": False}


def _legacy_instance(engine, cell, raw):
    import world_entities as WORLD
    owner_name = raw.get("owner")
    matches = [actor for actor in WORLD.actor_index(engine).values() if actor.name == owner_name]
    owner = matches[0] if len(matches) == 1 else None
    return {
        "id": _next(engine, "_hazard_sequence", "hazard:"),
        "region_id": _next(engine, "_hazard_region_sequence", "hazard-region:"),
        "source_id": "legacy/hazard",
        "clause_id": None,
        "source_row_sha256": None,
        "name": str(raw.get("name", "hazard")),
        "kind": "legacy",
        "cell": cell,
        "owner_actor_id": getattr(owner, "entity_id", None),
        "owner_side": getattr(owner, "side", str(owner_name or "legacy")),
        "owner_name": owner_name,
        "created_at": engine.elapsed_seconds,
        "created_round": engine.round_no,
        "lifetime": "encounter_end",
        "trigger": "enter_cell",
        "trigger_range": 0,
        "slow": bool(raw.get("slow")),
        "legacy_effects": deepcopy(raw.get("effects", [])),
    }


def ensure(engine):
    if not hasattr(engine, "_hazard_sequence"):
        engine._hazard_sequence = 0
    if not hasattr(engine, "_hazard_region_sequence"):
        engine._hazard_region_sequence = 0
    if not isinstance(engine.hazards, dict):
        raise ValueError("Hazard cells must be a mapping")
    for raw_cell, raw in list(engine.hazards.items()):
        cell = tuple(raw_cell)
        if not isinstance(raw, dict):
            raise ValueError("Hazard cell state must be a mapping")
        if isinstance(raw.get("instances"), list):
            _project(engine, cell, raw)
            continue
        envelope = _new_envelope(engine, cell, slow=bool(raw.get("slow")))
        envelope["instances"].append(_legacy_instance(engine, cell, raw))
        engine.hazards.pop(raw_cell)
        engine.hazards[cell] = envelope
        _project(engine, cell, envelope)
    return engine.hazards


def handles(engine, source_id, effect):
    return source_id in NATIVE_MOVES and isinstance(effect, dict) and effect.get("type") == "create_terrain"


def prepare_effects(engine, actor, effects, source_id):
    if source_id not in NATIVE_MOVES | {COURT_CHANGE}:
        return None
    row = policy(engine.r)["moves"][source_id]
    if source_id == COURT_CHANGE:
        if _semantic(effects) != row["effects"]:
            raise ValueError("Court Change differs from reviewed source policy")
        return opponent(engine, actor, preflight=True)
    runtime = dict(row["effects"][0])
    if "trigger" in runtime:
        runtime["_hazard_source_trigger"] = runtime.pop("trigger")
    expected = [dict(runtime, _activation_scope="field", _hazard_native=True)]
    source_semantic = deepcopy(_semantic(effects))
    if source_id == "move/스텔스록" and source_semantic:
        source_semantic[0]["trigger"] = effects[0].get("_hazard_source_trigger")
    if source_semantic != [row["effects"][0]] or len(effects) != 1 or effects[0] != expected[0]:
        raise ValueError("Hazard installation differs from reviewed source policy")
    validate_world(engine)
    if not engine.encounter_active:
        raise ValueError("native Hazard lifetime requires an actual encounter")
    return True


def install(engine, actor, effect, ctx):
    source_id = ctx.get("source_id")
    if not handles(engine, source_id, effect):
        return False
    prepare_effects(engine, actor, [effect], source_id)
    move = ctx.get("move") or {}
    chosen = cells(move)
    if chosen is None:
        raise ValueError("Hazard installation requires the authenticated placement cells")
    placement = _placement(engine, source_id)
    if len(chosen) != placement["cells"]:
        raise ValueError("Hazard installation geometry changed after preflight")
    import world_entities as WORLD
    index = WORLD.actor_index(engine)
    if index.get(actor.entity_id) is not actor:
        raise ValueError("Hazard creator must be an actual world participant")
    row = policy(engine.r)["moves"][source_id]
    return _install_region(engine, actor, source_id, row, chosen, index)


def install_from_completion(engine, actor, source_id, completion_id):
    """Use the completed derived attack's real area, not an arbitrary cell list."""
    if source_id not in DERIVED_MOVES:
        raise ValueError("reviewed derived Hazard source required")
    completion = getattr(engine, "_move_completions", {}).get(completion_id)
    if (not completion or completion["actor"] is not actor or completion["move_id"] != source_id or
            completion["phase"] != "complete" or not completion["sealed"] or
            not completion["move"].get("_gmax_base_move_id") or
            not any(row["hit"] and not row["cancelled"] for row in completion["results"].values())):
        raise ValueError("derived Hazard requires actual successful native completion")
    if completion.get("hazard_region_id"):
        raise ValueError("derived Hazard completion already installed")
    import area_targets as AREA
    import world_entities as WORLD
    chosen = AREA.cells(engine, actor, completion["move"])
    row = _definition(engine.r, source_id)
    region_id = _install_region(engine, actor, source_id, row, chosen, WORLD.actor_index(engine))
    completion["hazard_region_id"] = region_id
    return region_id


def _install_region(engine, actor, source_id, row, chosen, index):
    if not engine.encounter_active or engine.grid is None or not chosen or any(not engine.grid.inside(cell) for cell in chosen):
        raise ValueError("native Hazard region requires an actual encounter map")
    if index.get(actor.entity_id) is not actor or not isinstance(actor.side, str) or not actor.side:
        raise ValueError("actual Hazard owner and side required")
    region_id = _next(engine, "_hazard_region_sequence", "hazard-region:")
    for cell in sorted(chosen):
        envelope = engine.hazards.get(cell)
        if envelope is None:
            envelope = engine.hazards[cell] = _new_envelope(engine, cell, slow=row["slow"])
        elif not isinstance(envelope.get("instances"), list):
            ensure(engine)
            envelope = engine.hazards[cell]
        instance = {
            "id": _next(engine, "_hazard_sequence", "hazard:"),
            "region_id": region_id,
            "source_id": source_id,
            "clause_id": row["clause_id"],
            "source_row_sha256": row["source_row_sha256"],
            "name": row["name"],
            "kind": row["kind"],
            "cell": cell,
            "owner_actor_id": actor.entity_id,
            "owner_side": actor.side,
            "owner_name": actor.name,
            "created_at": engine.elapsed_seconds,
            "created_round": engine.round_no,
            "lifetime": "encounter_end",
            "trigger": row["trigger"],
            "trigger_range": row["trigger_range"],
            "slow": row["slow"],
            "legacy_effects": [],
        }
        envelope["instances"].append(instance)
        _project(engine, cell, envelope)
    validate_world(engine, index)
    engine.log("    함정 %s %d칸 설치 (%s)" % (row["name"], len(chosen), region_id), source_id)
    return region_id


def _remove(engine, selected):
    selected = set(selected)
    removed = 0
    for cell, envelope in list(ensure(engine).items()):
        before = len(envelope["instances"])
        envelope["instances"][:] = [row for row in envelope["instances"] if row["id"] not in selected]
        removed += before - len(envelope["instances"])
        _project(engine, cell, envelope)
    return removed


def remove_cells(engine, cells_to_remove):
    cells_to_remove = set(cells_to_remove)
    selected = [row["id"] for cell, envelope in ensure(engine).items() if cell in cells_to_remove
                for row in envelope["instances"]]
    return _remove(engine, selected)


def clear(engine):
    count = sum(len(envelope["instances"]) for envelope in ensure(engine).values())
    for cell, envelope in list(engine.hazards.items()):
        envelope["instances"].clear()
        _project(engine, cell, envelope)
    engine.hazards_nogrid = []
    return count


def place_legacy(engine, cell, name, effects=None, owner="GM", slow=False):
    cell = tuple(cell)
    raw = {"name": name, "effects": list(effects or []), "owner": owner, "slow": bool(slow)}
    if cell in engine.hazards:
        ensure(engine)
        engine.hazards[cell]["instances"].append(_legacy_instance(engine, cell, raw))
        _project(engine, cell, engine.hazards[cell])
    else:
        engine.hazards[cell] = raw
        ensure(engine)
    return engine.hazards[cell]


def _hostile(instance, actor):
    if instance["kind"] == "legacy" and instance.get("owner_name") == actor.name:
        return False
    return instance.get("owner_side") != actor.side


def _owner(engine, instance):
    import world_entities as WORLD
    owner = WORLD.actor_index(engine).get(instance.get("owner_actor_id"))
    return owner


def _dispatch(engine, owner, target, instance, effects):
    if not effects:
        return
    import effects as FX
    source = "hazard-instance/" + instance["id"] + "/" + instance["source_id"]
    result = FX.run_effects(engine, owner or target, target, effects,
        {"attacker": owner or target, "target": target, "hit": True, "nat": None,
         "engine": engine, "hazard_instance_id": instance["id"],
         "_hazard_instance": instance, "_hazard_activation": _AUTHORITY}, source)
    if result[1] or result.pending:
        raise ValueError("Hazard trigger effect did not complete")


def stage_provenance(engine, source_actor, target, context):
    """Resolve the selected live trap, keeping tracking and rule sources distinct."""
    source = context["source_id"]
    if not any(key in context for key in ("hazard_instance_id", "_hazard_instance", "_hazard_activation")) and not source.startswith("hazard-instance/"):
        return source, None
    instance = context.get("_hazard_instance")
    if context.get("_hazard_activation") is not _AUTHORITY or not isinstance(instance, dict):
        raise ValueError("actual Hazard trigger context required")
    cell = instance.get("cell")
    envelope = engine.hazards.get(cell) if isinstance(cell, tuple) else None
    if not isinstance(envelope, dict) or not any(row is instance for row in envelope.get("instances", ())):
        raise ValueError("actual live Hazard instance required")
    import world_entities as WORLD
    index = WORLD.actor_index(engine)
    _validate_instance(engine, cell, instance, index)
    if (context.get("hazard_instance_id") != instance["id"] or
            source != "hazard-instance/" + instance["id"] + "/" + instance["source_id"] or
            index.get(target.entity_id) is not target or
            (index.get(instance["owner_actor_id"]) or target) is not source_actor):
        raise ValueError("Hazard trigger source or participant identity changed")
    if instance["kind"] == "legacy":
        return source, None
    return instance["source_id"], instance["owner_side"]


def _slow(engine, owner, target, instance):
    _dispatch(engine, owner, target, instance, [{"type": "apply_status", "status": "둔화",
        "target": "target", "duration": "end of target's next turn"}])


def _is_levitating(actor):
    import ability_transitions as ABILITIES
    return ABILITIES.active(actor, "ability/부유")


def _ordinary_entry(engine, actor, cell, instances):
    instances = __import__('survivalist_class').hazard_entry(engine, actor, cell, instances)
    by_kind = {}
    for instance in instances:
        if instance['kind']=='fire' and __import__('field_effects').touches_ground(actor):engine.lose_hp(actor,engine.tick(actor),source=instance['source_id'])
        if instance["trigger"] == "enter_cell" and _hostile(instance, actor):
            by_kind.setdefault(instance["kind"], []).append(instance)
    if by_kind.get("legacy"):
        instance = by_kind["legacy"][0]
        _dispatch(engine, _owner(engine, instance), actor, instance,
                  [dict(effect, target="self", **{"if": None}) for effect in instance["legacy_effects"]])
        _remove(engine, [instance["id"]])
    webs = by_kind.get("sticky_web", [])
    if webs:
        if actor.kind == "pokemon" and "벌레" in actor.types:
            _remove(engine, [row["id"] for row in webs])
            engine.log("    %s: 벌레 타입이 끈적끈적네트를 무해하게 파괴" % actor.name, webs[0]["source_id"])
        elif not (actor.kind == "pokemon" and "비행" in actor.types) and not _is_levitating(actor):
            for instance in webs:
                _dispatch(engine, _owner(engine, instance), actor, instance,
                          [{"type": "stage_change", "stat": "spe", "delta": -1, "target": "target"}])
                _slow(engine, _owner(engine, instance), actor, instance)
    spikes = by_kind.get("spikes", [])
    if spikes:
        import field_effects as FIELD
        if FIELD.touches_ground(actor):
            for instance in spikes:
                engine.lose_hp(actor, M.ratio(actor.max_hp, 10), source="hazard-instance/" + instance["id"])
                _slow(engine, _owner(engine, instance), actor, instance)
    toxic = by_kind.get("toxic_spikes", [])
    if toxic:
        if actor.kind == "pokemon" and "독" in actor.types:
            _remove(engine, [row["id"] for row in toxic])
            engine.log("    %s: 독 타입이 독압정을 무해하게 파괴" % actor.name, toxic[0]["source_id"])
        else:
            instance = toxic[0]
            _dispatch(engine, _owner(engine, instance), actor, instance,
                      [{"type": "apply_status", "status": "맹독" if len(toxic) >= 2 else "독", "target": "target"}])
            _slow(engine, _owner(engine, instance), actor, instance)


def _stealth_entry(engine, actor, cell):
    from grid import cheb
    for kind, attack_type in (("stealth_rock", "바위"), ("steelsurge", "강철")):
        candidates = [instance for hazard_cell, envelope in ensure(engine).items()
                  for instance in envelope["instances"]
                  if instance["kind"] == kind and _hostile(instance, actor)
                  and cheb(hazard_cell, cell) <= instance["trigger_range"]]
        if not candidates or kind in actor.spec.get(REENTRY, []):
            continue
        if kind == "stealth_rock" and __import__('survivalist_class').stealth_rock_immune(engine, actor):
            engine.log("    %s: 동굴 거주자로 스텔스록 함정 면역" % actor.name, "feat/지형-재능")
            continue
        instance = min(candidates, key=lambda row: (cheb(row["cell"], cell), row["cell"], row["id"]))
        multiplier, source = engine.type_multiplier(attack_type, actor)
        damage = M.product(engine.tick(actor), multiplier)
        engine.take_damage(actor, damage)
        if actor.kind == "pokemon":
            actor.spec.setdefault(REENTRY, []).append(kind)
        if not __import__('type_ace').preserve_rock(engine,instance):_remove(engine, [instance["id"]])
        engine.log("    %s: %s %s 피해 %d, 물리 함정 파괴" % (actor.name, instance["name"], source, damage), instance["source_id"])


def on_enter_cell(engine, actor, cell):
    ensure(engine)
    import effect_lifetime_policy as LIFETIMES
    LIFETIMES.reconcile(engine)
    import static_equipment_contracts as STATIC_EQUIPMENT
    has_any = any(envelope["instances"] for envelope in engine.hazards.values())
    if not has_any:
        return
    if STATIC_EQUIPMENT.ignores_entry_hazard(engine, actor):
        engine.log("    %s: 진입 함정 무시 (통굽부츠)" % actor.name, "item/통굽부츠")
        return
    guide = __import__('survivalist_class').ignores_hazards(engine, actor)
    if guide:
        envelope = engine.hazards.get(tuple(cell))
        if (envelope and envelope["instances"]) or any(row["kind"] in ("stealth_rock", "steelsurge") for env in engine.hazards.values() for row in env["instances"]):
            engine.log("    %s: 함정을 유발하지 않음 (야생 가이드)" % actor.name, guide)
        return
    envelope = engine.hazards.get(tuple(cell))
    if envelope:
        _ordinary_entry(engine, actor, tuple(cell), list(envelope["instances"]))
    _stealth_entry(engine, actor, tuple(cell))


def on_recall(actor):
    actor.spec.pop(REENTRY, None)


def opponent(engine, actor, *, preflight=False):
    import world_entities as WORLD
    index = WORLD.actor_index(engine)
    active = [candidate for candidate in index.values() if candidate.on_field]
    sides = {candidate.side for candidate in active}
    if len(sides) != 2 or actor.side not in sides:
        raise ValueError("Court Change requires exactly two actual battlefield sides")
    other = next(candidate for candidate in active if candidate.side != actor.side)
    if engine.hazards_nogrid:
        raise ValueError("Court Change cannot exchange opaque no-grid Hazards")
    import blessing_effects as BLESSINGS
    for candidate in index.values():
        native = BLESSINGS.live(candidate)
        if any(record not in native for record in candidate.blessings):
            raise ValueError("Court Change cannot exchange legacy Blessings without side identity")
    BLESSINGS.preflight_swap(engine, actor, other, COURT_CHANGE)
    validate_world(engine, index)
    return other


def swap_sides(engine, actor):
    other = opponent(engine, actor, preflight=True)
    import blessing_effects as BLESSINGS
    BLESSINGS.swap(engine, actor, other, COURT_CHANGE)
    sides = {actor.side: other.side, other.side: actor.side}
    changed = 0
    for cell, envelope in ensure(engine).items():
        for instance in envelope["instances"]:
            if instance["owner_side"] in sides:
                instance["owner_side"] = sides[instance["owner_side"]]
                changed += 1
        _project(engine, cell, envelope)
    validate_world(engine)
    engine.log("    양측 축복·함정 교환 (물리 함정 %d개 소유 진영 교환)" % changed, COURT_CHANGE)
    return changed


def end_encounter(engine, actors=()):
    count = clear(engine)
    for actor in actors:
        on_recall(actor)
    return count


def validate_actor(actor):
    value = actor.spec.get(REENTRY)
    if value is None:
        return
    if not isinstance(value, list) or value != list(dict.fromkeys(value)) or any(item not in ("stealth_rock", "steelsurge") for item in value):
        raise ValueError("Hazard re-entry immunity must be an exact unique marker list")


def _validate_instance(engine, cell, instance, index):
    import common_checks as C
    required = {"id", "region_id", "source_id", "clause_id", "source_row_sha256", "name", "kind", "cell",
                "owner_actor_id", "owner_side", "owner_name", "created_at", "created_round", "lifetime",
                "trigger", "trigger_range", "slow", "legacy_effects"}
    if set(instance) != required or instance["cell"] != cell:
        raise ValueError("Hazard physical instance shape or identity changed")
    try:
        seq = int(instance["id"].split(":", 1)[1]); rseq = int(instance["region_id"].split(":", 1)[1])
    except (ValueError, IndexError):
        raise ValueError("Hazard instance and region identities must be issued sequences")
    C.integer(instance["created_at"], "Hazard creation time", 0)
    C.integer(instance["created_round"], "Hazard creation round", 0)
    C.integer(instance["trigger_range"], "Hazard trigger range", 0)
    if instance["created_at"] > engine.elapsed_seconds or instance["created_round"] > engine.round_no:
        raise ValueError("Hazard creation receipt is in the future")
    if instance["lifetime"] != "encounter_end" or type(instance["slow"]) is not bool:
        raise ValueError("Hazard lifetime or terrain projection changed")
    if instance["kind"] != "legacy":
        row = _definition(engine.r, instance["source_id"])
        expected = (row and row["clause_id"], row and row["source_row_sha256"], row and row["name"], row and row["kind"],
                    row and row["trigger"], row and row["trigger_range"], row and row["slow"])
        actual = (instance["clause_id"], instance["source_row_sha256"], instance["name"], instance["kind"],
                  instance["trigger"], instance["trigger_range"], instance["slow"])
        if expected != actual or instance["owner_actor_id"] not in index:
            raise ValueError("Hazard source provenance or creator identity changed")
    if not isinstance(instance["owner_side"], str) or not instance["owner_side"]:
        raise ValueError("Hazard current owning side must be explicit")
    return seq, rseq


def validate_world(engine, index=None):
    import world_entities as WORLD
    import common_checks as C
    index = WORLD.actor_index(engine) if index is None else index
    ensure(engine)
    ids = set()
    region_sources = {}
    max_id = max_region = 0
    for cell, envelope in engine.hazards.items():
        if engine.grid is None or not engine.grid.inside(cell):
            raise ValueError("Hazard physical cell is outside the actual map")
        if set(envelope) != {"instances", "slow_before", "name", "owner", "effects", "slow"}:
            raise ValueError("Hazard cell projection shape changed")
        if type(envelope["slow_before"]) is not bool:
            raise ValueError("Hazard base terrain observation must be boolean")
        for instance in envelope["instances"]:
            seq, rseq = _validate_instance(engine, cell, instance, index)
            if instance["id"] in ids:
                raise ValueError("Hazard physical instance shape or identity changed")
            ids.add(instance["id"])
            max_id = max(max_id, seq); max_region = max(max_region, rseq)
            previous = region_sources.setdefault(instance["region_id"], instance["source_id"])
            if previous != instance["source_id"]:
                raise ValueError("Hazard region cannot merge physical sources")
        _project(engine, cell, envelope)
    if C.integer(engine._hazard_sequence, "Hazard issuance sequence", 0) < max_id or C.integer(engine._hazard_region_sequence, "Hazard region sequence", 0) < max_region:
        raise ValueError("Hazard issuance sequence is behind live identities")
    if engine.hazards and not engine.encounter_active and any(row["kind"] != "legacy" for env in engine.hazards.values() for row in env["instances"]):
        raise ValueError("native encounter Hazards survived encounter end")
    return True
