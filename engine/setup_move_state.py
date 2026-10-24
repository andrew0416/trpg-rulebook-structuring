"""Source-owned Set-Up Move state for completed terrain and transit clauses.

The native Move path still owns action, frequency, accuracy, damage and area
selection.  This module owns only the preparation record and the exceptional
movement that the printed Set-Up effect grants before that native path resumes.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json


SOURCE = "data/setup-move-state-policy.json"
STATE = "_setup_move_state"
SCHEMA = "ptk.setup-move-state.v1"
TURN_STATE = "_setup_following_turn"
EXIT_STATE = "_setup_move_exit"
TURN_SOURCE = "ch10-index-reference/준비"


def _policy(rules):
    cached = getattr(rules, "_setup_move_state_policy", None)
    if cached is None:
        path = Path(rules.root) / SOURCE
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("schema") != SCHEMA:
            raise ValueError("unsupported setup Move policy schema")
        rows = cached.get("moves")
        if not isinstance(rows, list) or len(rows) != 4:
            raise ValueError("setup Move policy must bind the exact four completed clauses")
        for file, digest in cached.get("source_files", {}).items():
            if hashlib.sha256((Path(rules.root) / file).read_bytes()).hexdigest() != digest:
                raise ValueError("setup Move source changed: " + file)
        rules._setup_move_state_policy = cached
    return cached


def _catalog(rules):
    by_eng = {row.get("eng"): row for row in rules.moves.values()}
    result = {}
    for declaration in _policy(rules)["moves"]:
        move = by_eng.get(declaration["move_eng"])
        if move is None or move.get("_source", {}).get("record_span") != [declaration["record"], declaration["record"]]:
            raise ValueError("setup Move record identity changed")
        move_id = move["id"]
        if rules._selected_rule(move_id) != move_id:
            raise ValueError("setup Move requires its selected source")
        mechanics, _ = rules.move_mech(move_id)
        effects = [{k: v for k, v in row.items() if not k.startswith("_")}
                   for row in mechanics.get("effects_exec", [])]
        if effects != declaration["expected_effects"]:
            raise ValueError("setup Move extraction changed: " + move_id)
        result[move_id] = dict(declaration, move_id=move_id)
    return result


def declarations(rules):
    return deepcopy(list(_catalog(rules).values()))


def deferred(rules):
    _policy(rules)
    return deepcopy(_policy(rules)["deferred"])


def owns(rules, move_id):
    move = rules.moves.get(move_id)
    if move is None:
        return False
    span = move.get("_source", {}).get("record_span")
    return any(row["move_eng"] == move.get("eng") and span == [row["record"], row["record"]]
               for row in _policy(rules)["moves"])


def pending(actor):
    row = actor.custom_conditions.get(STATE)
    return row if isinstance(row, dict) else None


def _serial(actor):
    import common_checks as C
    return C.integer(actor.custom_conditions.get("combat_turn_serial", 0), "actual owner turn serial", 0)


def require_physical_exit(actor):
    if actor.custom_conditions.get(EXIT_STATE) is not None:
        raise ValueError("actual GM Dive physical exit observation required; targetability is unresolved")


def prepare_turn(engine, actor, move_id):
    if not engine.encounter_active or engine._active_turn_actor is not actor:
        raise ValueError("Set-Up preparation requires an actual own turn")
    require_physical_exit(actor)
    actor.custom_conditions[TURN_STATE] = {
        "source": TURN_SOURCE, "actor_id": actor.entity_id, "move_id": move_id,
        "selected_source": engine.r._selected_rule(move_id),
        "prepared_turn": _serial(actor), "prepared_round": engine.round_no,
        "prepared_at": engine.elapsed_seconds,
    }
    actor.setup_move = move_id


def _following_turn(engine, actor, move_id):
    row = actor.custom_conditions.get(TURN_STATE)
    if row is None:
        raise ValueError("prepared Set-Up Move has no actual own-turn receipt; explicit reconciliation required")
    if (row["move_id"] != move_id or row["selected_source"] != engine.r._selected_rule(move_id)):
        raise ValueError("Set-Up preparation source changed")
    return (engine.encounter_active and engine._active_turn_actor is actor
            and _serial(actor) == row["prepared_turn"] + 1)


def generic_ready(engine, actor, move_id):
    if actor.setup_move is None or actor.setup_move != move_id or owns(engine.r, move_id):
        return True
    import conditional_damage_base as CONDITIONAL
    if CONDITIONAL.pending_move(actor, move_id):
        return True
    if not _following_turn(engine, actor, move_id):
        engine.log("  %s: Set-Up resolves on the following actual own turn" % actor.name, TURN_SOURCE)
        return False
    return True


def consume_turn(actor):
    actor.custom_conditions.pop(TURN_STATE, None)
    actor.setup_move = None


def cancel(engine, actor, reason):
    row = pending(actor)
    turn = actor.custom_conditions.get(TURN_STATE)
    import conditional_damage_base as CONDITIONAL
    if (row is None and turn is None and not (reason == "recall" and actor.custom_conditions.get(EXIT_STATE))
            and (actor.setup_move is None or CONDITIONAL.pending_move(actor, actor.setup_move))):
        return
    if row is not None and row["kind"] == "dive" and reason != "recall":
        actor.custom_conditions[EXIT_STATE] = {
            "source": SOURCE, "actor_id": actor.entity_id, "move_id": row["move_id"],
            "clause_id": row["clause_id"], "source_row_sha256": row["source_row_sha256"],
            "position": list(actor.pos), "water_depth_m": row["water_depth_m"],
            "submerged_observation": True, "cancelled_at": engine.elapsed_seconds,
            "cancelled_turn": _serial(actor), "reason": reason,
        }
    if reason == "recall":
        actor.custom_conditions.pop(EXIT_STATE, None)
    if row is not None:
        scope = _scope(engine, actor, row["move_id"])
        if scope is not None and scope.get("phase") == "prepare" and scope.get("prepared"):
            scope["cancelled"] = reason
    # Readiness ends. Actual altitude, burrow state and rough terrain belong to
    # their existing physical owners; cancellation does not manufacture an exit.
    actor.custom_conditions.pop(STATE, None)
    consume_turn(actor)
    engine.log("  %s: Set-Up readiness cancelled (%s)" % (actor.name, reason), TURN_SOURCE)


def start_turn(engine, actor):
    row = actor.custom_conditions.get(TURN_STATE)
    if row is not None and _serial(actor) > row["prepared_turn"] + 1:
        cancel(engine, actor, "following own turn already passed")
    elif row is None and actor.setup_move is not None:
        import conditional_damage_base as CONDITIONAL
        if not CONDITIONAL.pending_move(actor, actor.setup_move):
            cancel(engine, actor, "legacy preparation has no own-turn receipt")


def end_turn(engine, actor):
    row = actor.custom_conditions.get(TURN_STATE)
    if row is not None and _serial(actor) >= row["prepared_turn"] + 1:
        cancel(engine, actor, "following own turn ended unused")


def observe_exit(engine, actor, *, expected_state, submerged, reason):
    """Record an actual GM-observed Dive exit; no travel or damage is executed."""
    _text(reason, "actual Dive physical exit reason")
    if submerged is not False:
        raise ValueError("explicit observed Dive exit required; continued protection is not inferred")
    import state_grants as GRANTS
    def apply(staged, subject):
        row = subject.custom_conditions.get(EXIT_STATE)
        if row is None or expected_state != row or list(subject.pos) != row["position"]:
            raise ValueError("actual pending Dive physical observation changed")
        declaration = _catalog(staged.r).get(row["move_id"])
        if declaration is None or declaration["source_row_sha256"] != row["source_row_sha256"]:
            raise ValueError("Dive physical observation source changed")
        receipt = dict(deepcopy(row), submerged=False, observed_at=staged.elapsed_seconds,
                       observation_reason=reason)
        subject.custom_conditions.pop(EXIT_STATE)
        subject.custom_conditions.setdefault("setup_move_exit_history", []).append(receipt)
        staged.gm._rec("observed Dive exit", row, receipt, reason, subject)
        return deepcopy(receipt)
    return GRANTS.transition(engine, actor, apply)


def _scopes(engine):
    scopes = getattr(engine, "_setup_move_scopes", None)
    if scopes is None:
        engine._setup_move_scopes = scopes = []
    return scopes


def _scope(engine, actor, move_id):
    matches = [row for row in getattr(engine, "_setup_move_scopes", ())
               if row["actor_id"] == actor.entity_id and row["move_id"] == move_id]
    if len(matches) == 1:
        return matches[0]
    if not matches and getattr(engine, "_resuming_move_activation", False):
        # The existing saved activation owns only the remaining paid targets.
        native = [row for row in getattr(engine, "_move_activation_scopes", ())
                  if row["actor"] is actor and row["move_id"] == move_id
                  and row["activation"].get("started")]
        if len(native) == 1 and pending(actor) is None:
            completion = getattr(engine, "_move_completions", {}).get(native[0].get("completion_id"))
            if (completion is not None and completion["actor"] is actor
                    and completion["move_id"] == move_id):
                return {"phase": "resolve", "native_started": True}
    return None


def require_move_choice(engine, actor, move_id):
    """A prepared actor resumes that exact Move instead of replacing its state."""
    require_physical_exit(actor)
    row = pending(actor) or actor.custom_conditions.get(TURN_STATE)
    if row is not None and row["move_id"] != move_id:
        raise ValueError("prepared setup Move must resolve before another Move is used")


def require_native_scope(engine, actor, move_id):
    require_move_choice(engine, actor, move_id)
    if owns(engine.r, move_id) and _scope(engine, actor, move_id) is None:
        raise ValueError("source-owned setup Move requires Engine.use_setup_move_on")


def targetable(target, *, engine=None, attacker=None, move=None):
    require_physical_exit(target)
    import marsupial_state as MARSUPIAL
    blocked = (MARSUPIAL.attack_blocked(attacker,target,move,engine=engine)
               if move is not None else MARSUPIAL.protected_from_attacks(target,engine=engine))
    if blocked:return False
    row = pending(target)
    return not (row and row.get("kind") == "dive" and row.get("submerged") is True)


def require_targetable(engine, attacker, target, move_id):
    import partial_entities as PARTIAL
    PARTIAL.require_complete(attacker, "setup Move attacker")
    PARTIAL.require_complete(target, "setup Move target")
    require_physical_exit(target)
    import marsupial_state as MARSUPIAL
    if MARSUPIAL.attack_blocked(attacker,target,engine.r.move(move_id),engine=engine):
        raise ValueError('native Marsupial baby is protected in its actual mother pouch')
    row = pending(target)
    if target is not attacker and row and row.get('kind') == 'dive' and row.get('submerged') is True:
        raise ValueError("a submerged Dive user cannot be targeted")


def movement_permission(engine, actor):
    require_physical_exit(actor)
    row = pending(actor)
    if row is None:
        return True
    scope = _scope(engine, actor, row["move_id"])
    if scope is not None and scope["phase"] == "resolve":
        return True
    if row["kind"] == "geomancy":
        return engine.round_no != row["prepared_round"]
    return False


def _options(value):
    if value is None:
        return {}
    if type(value) is not dict:
        raise ValueError("setup Move options must be a mapping")
    return deepcopy(value)


def _keys(options, required=(), optional=()):
    required, allowed = set(required), set(required) | set(optional)
    if set(options) != required and (not optional or not required <= set(options) <= allowed):
        missing = required - set(options)
        unknown = set(options) - allowed
        raise ValueError("setup Move options mismatch; missing=%s unknown=%s" %
                         (sorted(missing), sorted(unknown)))


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " requires explicit text")
    return value


def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or any(type(v) is not int for v in value):
        raise ValueError("mapped setup Move coordinate required")
    return tuple(value)


def _base_state(engine, actor, declaration):
    return {
        "source": SOURCE,
        "schema": SCHEMA,
        "clause_id": declaration["clause_id"],
        "source_row_sha256": declaration["source_row_sha256"],
        "move_id": declaration["move_id"],
        "kind": declaration["kind"],
        "actor_id": actor.entity_id,
        "prepared_round": engine.round_no,
        "prepared_turn": _serial(actor),
        "prepared_at": engine.elapsed_seconds,
        "origin": list(actor.pos),
    }


def _prepare_geomancy(engine, actor, declaration, options):
    _keys(options, ("terrain_cells",))
    if engine.grid is None:
        raise ValueError("Geomancy requires an actual mapped Burst 3")
    cells = [_point(value) for value in options["terrain_cells"]]
    if not cells or len(cells) != len(set(cells)):
        raise ValueError("Geomancy requires distinct selected rough cells")
    allowed = engine.grid.burst(actor.pos, 3)
    if any(cell not in allowed for cell in cells):
        raise ValueError("Geomancy rough cell lies outside the actual Burst 3")
    engine.grid.rough.update(cells)
    row = _base_state(engine, actor, declaration)
    row.update(rough_cells=[list(cell) for cell in cells])
    engine.log("  %s: Geomancy preparation creates %d selected rough cells" %
               (actor.name, len(cells)), declaration["clause_id"])
    return row


def _prepare_fly(engine, actor, declaration, options):
    _keys(options)
    if engine.grid is None or actor.spec.get("_movement_altitude", 0) != 0:
        raise ValueError("Fly preparation requires a mapped surface origin")
    if actor.spec.get("_burrow", {}).get("underground"):
        raise ValueError("an underground actor cannot prepare Fly")
    import body_state as BODY
    if not BODY.can_place(engine, actor, actor.pos, altitude=25):
        raise ValueError("Fly preparation altitude is occupied or outside the map body")
    actor.spec["_movement_altitude"] = 25
    actor.airborne = True
    row = _base_state(engine, actor, declaration)
    row.update(altitude_m=25)
    engine.log("  %s: Fly preparation shifts to altitude 25m" % actor.name,
               declaration["clause_id"])
    return row


def _prepare_dig(engine, actor, declaration, options):
    _keys(options, ("diggable", "reason"))
    if options["diggable"] is not True:
        raise ValueError("Dig preparation requires an observed diggable origin")
    reason = _text(options["reason"], "Dig terrain observation")
    if engine.grid is None:
        raise ValueError("Dig preparation requires an actual map")
    import map_terrain as TERRAIN
    if not TERRAIN.can_travel(engine, actor, actor.pos, "burrow", altitude=0, underground=True):
        raise ValueError("Dig preparation conflicts with the actual base terrain")
    actor.spec["_movement_altitude"] = 0
    actor.airborne = False
    actor.spec.setdefault("_burrow", {}).update(
        underground=True, depth_m=25, setup_move=declaration["move_id"], reason=reason,
        upkeep_round=engine.round_no)
    row = _base_state(engine, actor, declaration)
    row.update(depth_m=25, diggable_reason=reason)
    if getattr(actor, "budget", None) is not None:
        actor.budget["swift"] = 0
    engine.log("  %s: Dig preparation descends 25m underground" % actor.name,
               declaration["clause_id"])
    return row


def _dive_origin(engine, actor, options):
    from physical_limits import number
    depth = number(options["water_depth_m"], "observed water depth", minimum=10)
    reason = _text(options["reason"], "Dive water observation")
    if engine.grid is None:
        raise ValueError("Dive requires an actual water map")
    import body_state as BODY
    import map_terrain as TERRAIN
    if any(TERRAIN.base_at(engine.grid, cell) != "underwater"
           for cell in BODY.cells(actor, require_complete=True)):
        raise ValueError("Dive requires mapped underwater body cells")
    return depth, reason


def _prepare_dive(engine, actor, declaration, options):
    _keys(options, ("water_depth_m", "reason"))
    depth, reason = _dive_origin(engine, actor, options)
    actor.airborne = False
    actor.spec["_movement_altitude"] = 0
    row = _base_state(engine, actor, declaration)
    row.update(submerged=True, water_depth_m=depth, water_reason=reason)
    if getattr(actor, "budget", None) is not None:
        actor.budget["swift"] = 0
    engine.log("  %s: Dive preparation submerges in %.3gm water" % (actor.name, depth),
               declaration["clause_id"])
    return row


PREPARE = {
    "geomancy": _prepare_geomancy,
    "fly": _prepare_fly,
    "dig": _prepare_dig,
    "dive": _prepare_dive,
}


def native_phase(engine, actor, target, move_id):
    """Called inside the paid native use, at the existing generic Set-Up seam."""
    declaration = _catalog(engine.r).get(move_id)
    if declaration is None:
        return None
    scope = _scope(engine, actor, move_id)
    if scope is None:
        raise ValueError("source-owned setup Move activation scope is missing")
    if scope["phase"] == "prepare":
        if pending(actor) is not None:
            raise ValueError("actor already has a prepared setup Move")
        row = PREPARE[declaration["kind"]](engine, actor, declaration, scope["setup_options"])
        prepare_turn(engine, actor, move_id)
        actor.custom_conditions[STATE] = row
        scope["prepared"] = True
        if declaration["kind"] in ("dig", "dive"):
            engine.end_of_turn(actor)
        return "prepared"
    row = pending(actor)
    if scope.get("native_started"):
        return "resolve"
    if scope["phase"] != "skip" and (row is None or row["move_id"] != move_id or row["clause_id"] != declaration["clause_id"]):
        raise ValueError("setup Move resolution state changed")
    if declaration["kind"] == "geomancy":
        for stat in ("spa", "spd", "spe"):
            engine.change_stage(actor, stat, 2)
    actor.custom_conditions.pop(STATE, None)
    consume_turn(actor)
    scope["native_started"] = True
    engine.log("  %s: %s prepared state resolves" % (actor.name, declaration["move_eng"]),
               declaration["clause_id"])
    return "resolve"


def _capabilities(engine, actor):
    import movement_actions as MOVEMENT
    return {mode: engine.move_profile(actor, movement_mode=mode)[0]
            for mode, value in MOVEMENT.capabilities(engine, actor).items()
            if mode in MOVEMENT.MODES and value > 0}


def _complete_path(result, path, label):
    if result["steps"] != len(path):
        raise ValueError(label + " path did not complete")


def _primary_in_burst(engine, actor, primary):
    import body_state as BODY
    return bool(BODY.cells(primary, require_complete=True).intersection(engine.grid.burst(actor.pos, 1)))


def _resolve_fly(engine, actor, primary, options, *, skip_setup=False):
    _keys(options, ("path",))
    path = deepcopy(options["path"])
    if not isinstance(path, (list, tuple)):
        raise ValueError("Fly resolution path must be ordered")
    altitude = actor.spec.get("_movement_altitude", 0) if skip_setup else 25
    if skip_setup and (actor.spec.get("_burrow", {}).get("underground") or (path and altitude <= 0)):
        raise ValueError("Fly's airborne resolution shift requires actual airborne position")
    for node in path:
        if type(node) is not dict or node.get("altitude") != altitude:
            raise ValueError("Fly horizontal path remains at its actual resolution altitude")
    caps = _capabilities(engine, actor)
    allowance = 2 * max(caps.get("land", 0), caps.get("sky", 0))
    import movement_actions as MOVEMENT
    result = MOVEMENT.follow_paid_path(engine, actor, path, mode="sky", maximum_distance=allowance)
    _complete_path(result, path, "Fly")
    import body_state as BODY
    if not BODY.can_place(engine, actor, actor.pos, altitude=0):
        raise ValueError("Fly descent destination is blocked")
    actor.spec["_movement_altitude"] = 0
    actor.airborne = False
    if not BODY.adjacent(actor, primary):
        raise ValueError("Fly must descend adjacent to its declared target")


def _resolve_dig(engine, actor, primary, options, *, skip_setup=False):
    _keys(options, ("path", "diggable", "reason"))
    if options["diggable"] is not True:
        raise ValueError("Dig resolution requires an observed diggable path")
    reason = _text(options["reason"], "Dig path observation")
    path = [_point(node) for node in options["path"]]
    caps = _capabilities(engine, actor)
    allowance = max(caps.get("land", 0), caps.get("burrow", 0))
    import movement_actions as MOVEMENT
    underground = bool(actor.spec.get("_burrow", {}).get("underground"))
    mode = "land" if skip_setup and not underground else "burrow"
    result = MOVEMENT.follow_paid_path(engine, actor, path, mode=mode, maximum_distance=allowance)
    _complete_path(result, path, "Dig")
    import body_state as BODY
    if not BODY.can_place(engine, actor, actor.pos, altitude=0, underground=False):
        raise ValueError("Dig surface destination is blocked")
    if not skip_setup or underground:
        actor.spec.setdefault("_burrow", {}).update(
            underground=False, depth_m=0, last_path=[list(row) for row in path], reason=reason)
        if not hasattr(engine, "_burrow_tunnels"):
            engine._burrow_tunnels = []
        engine._burrow_tunnels.append({"actor": actor.entity_id,
                                    "path": [list(row) for row in path],
                                    "body_size": actor.spec.get("size"),
                                    "round": engine.round_no,
                                    "source": "move/구멍파기"})
    if not _primary_in_burst(engine, actor, primary):
        raise ValueError("Dig must surface with its declared target in Burst 1")


def _resolve_dive(engine, actor, primary, options, *, skip_setup=False):
    _keys(options, ("path", "water_depth_m", "reason") if skip_setup else ("path",))
    if skip_setup:
        _dive_origin(engine, actor, options)
    path = [_point(node) for node in options["path"]]
    caps = _capabilities(engine, actor)
    import movement_actions as MOVEMENT
    result = MOVEMENT.follow_paid_path(engine, actor, path, mode="swim",
                                       maximum_distance=caps.get("swim", 0))
    _complete_path(result, path, "Dive")
    if not _primary_in_burst(engine, actor, primary):
        raise ValueError("Dive must rise with its declared target in Burst 1")


RESOLVE = {"fly": _resolve_fly, "dig": _resolve_dig, "dive": _resolve_dive}


def _prepare_resolution(engine, actor, primary, declaration, options):
    row = pending(actor)
    if row is None or row["move_id"] != declaration["move_id"]:
        raise ValueError("matching prepared setup Move state required")
    if not _following_turn(engine, actor, declaration["move_id"]):
        raise ValueError("a setup Move resolves on the following actual own turn, not an arbitrary later turn")
    if declaration["kind"] == "geomancy":
        _keys(options)
    else:
        RESOLVE[declaration["kind"]](engine, actor, primary, options)


def activate(engine, actor, primary, move_id, everyone, *, setup_options=None, native_options=None):
    """Atomically prepare or resume one of the four completed Set-Up Moves."""
    declaration = _catalog(engine.r).get(move_id)
    if declaration is None:
        raise ValueError("selected Move is outside the completed setup Move package")
    if engine.grid is None:
        raise ValueError("completed setup Move package requires an actual map")
    import state_grants as GRANTS
    supplied = list(everyone) + [actor, primary]
    members = list({row.entity_id: row for row in engine.time_actors(supplied)}.values())
    participants = tuple(row for row in members if row is not actor)
    member_ids = [row.entity_id for row in members]
    primary_id = primary.entity_id
    options = _options(setup_options)
    native_options = _options(native_options)
    native_pending = []

    def apply(staged, staged_actor, *staged_participants):
        index = {row.entity_id: row for row in (staged_actor, *staged_participants)}
        staged_primary = index[primary_id]
        staged_everyone = [index[uid] for uid in member_ids]
        previous = getattr(staged, "_reactive_move_transaction", None)
        staged._reactive_move_transaction = True
        try:
            return _activate(staged, staged_actor, staged_primary, declaration,
                             staged_everyone, options, native_options, native_pending)
        finally:
            if previous is None:
                del staged._reactive_move_transaction
            else:
                staged._reactive_move_transaction = previous

    result = GRANTS.transition(engine, actor, apply, participants=participants,
                               include_grid=True, include_rulings=True)
    if native_pending:
        exception, event_id = native_pending[0]
        raise exception(event_id)
    return result


def _activate(engine, actor, primary, declaration, everyone, setup_options, native_options, native_pending):
    move_id = declaration["move_id"]
    row = pending(actor)
    import herb_mushroom_rules as HERB
    skip_setup = HERB.power_herb_plan(engine, actor, move_id) is not None or __import__('type_ace').setup_skip(engine,actor,engine.r.move(move_id))
    phase = "skip" if skip_setup else "resolve" if row is not None else "prepare"
    if row is not None and row["move_id"] != move_id:
        raise ValueError("another setup Move is already prepared")
    scope = {"source": SOURCE, "actor_id": actor.entity_id, "move_id": move_id,
             "phase": phase, "setup_options": setup_options,
             "prepared": False, "native_started": False}
    scopes = _scopes(engine)
    scopes.append(scope)
    try:
        if phase == "prepare":
            # Preparation has no attack target.  The user is the native
            # lifecycle anchor, which prevents ordinary melee/range pre-use
            # checks from fabricating an approach before the Set-Up effect.
            result = engine.use_move(actor, actor, move_id, **native_options)
        else:
            if phase == "skip":
                if declaration["kind"] == "geomancy":
                    _keys(setup_options)
                else:
                    RESOLVE[declaration["kind"]](engine, actor, primary, setup_options, skip_setup=True)
            else:
                _prepare_resolution(engine, actor, primary, declaration, setup_options)
            result = engine.use_move_on(actor, primary, move_id, everyone, **native_options)
    except Exception as error:
        import passive_events as PASSIVE
        import heavy_injury_adapter as HEAVY
        if (type(error) is PASSIVE.PassiveEventPending and
                engine._passive_pending == error.event_id and error.event_id in engine._passive_events):
            native_pending.append((PASSIVE.PassiveEventPending, error.event_id))
        elif (type(error) is HEAVY.HeavyPending and
                engine._heavy_pending == error.event_id and error.event_id in engine._heavy_events):
            native_pending.append((HEAVY.HeavyPending, error.event_id))
        else:
            raise
        result = None
    finally:
        if scope in scopes:
            scopes.remove(scope)
        if not scopes:
            vars(engine).pop("_setup_move_scopes", None)
    if native_pending and __import__('combat_move_reactions').pending_setup(engine,actor,scope):return result
    if scope.get('interrupted_by_sky_uppercut'):return result
    if phase == "prepare":
        if not scope["prepared"] or (pending(actor) is None and not scope.get("cancelled")):
            raise ValueError("native setup Move did not establish its preparation state")
    elif not scope["native_started"] or pending(actor) is not None:
        raise ValueError("native setup Move did not consume its prepared state")
    return result


def end_encounter(engine, actors):
    for actor in actors:
        cancel(engine, actor, "encounter end")


def validate_actor(actor):
    turn = actor.custom_conditions.get(TURN_STATE)
    if turn is not None:
        required = {"source", "actor_id", "move_id", "selected_source", "prepared_turn", "prepared_round", "prepared_at"}
        if (type(turn) is not dict or set(turn) != required or turn["source"] != TURN_SOURCE
                or turn["actor_id"] != actor.entity_id or turn["move_id"] != actor.setup_move
                or actor.r._selected_rule(turn["move_id"]) != turn["selected_source"]):
            raise ValueError("Set-Up actual own-turn receipt changed")
        import common_checks as C
        C.integer(turn["prepared_turn"], "Set-Up preparation own turn", 1, _serial(actor))
        C.integer(turn["prepared_round"], "Set-Up preparation round", 1)
        C.integer(turn["prepared_at"], "Set-Up preparation time", 0)
    exit_row = actor.custom_conditions.get(EXIT_STATE)
    if exit_row is not None:
        required = {"source", "actor_id", "move_id", "clause_id", "source_row_sha256", "position",
                    "water_depth_m", "submerged_observation", "cancelled_at", "cancelled_turn", "reason"}
        if type(exit_row) is not dict or set(exit_row) != required:
            raise ValueError("exact pending Dive physical observation required")
        declaration = _catalog(actor.r).get(exit_row["move_id"])
        if (declaration is None or declaration["kind"] != "dive" or exit_row["source"] != SOURCE
                or exit_row["actor_id"] != actor.entity_id or exit_row["clause_id"] != declaration["clause_id"]
                or exit_row["source_row_sha256"] != declaration["source_row_sha256"]
                or exit_row["submerged_observation"] is not True or exit_row["water_depth_m"] < 10
                or actor.setup_move is not None or pending(actor) is not None or turn is not None):
            raise ValueError("pending Dive physical observation source changed")
        _point(exit_row["position"])
        _text(exit_row["reason"], "Dive cancellation reason")
        import common_checks as C
        C.integer(exit_row["cancelled_at"], "Dive cancellation time", 0)
        C.integer(exit_row["cancelled_turn"], "Dive cancellation own turn", 1, _serial(actor))
    row = actor.custom_conditions.get(STATE)
    if row is None:
        return True
    required = {"source", "schema", "clause_id", "source_row_sha256", "move_id", "kind", "actor_id",
                "prepared_round", "prepared_at", "origin"}
    if not isinstance(row, dict) or not required <= set(row):
        raise ValueError("invalid setup Move state")
    declaration = _catalog(actor.r).get(row.get("move_id"))
    if (row.get("source") != SOURCE or row.get("schema") != SCHEMA or declaration is None or
            row.get("clause_id") != declaration["clause_id"] or
            row.get("source_row_sha256") != declaration["source_row_sha256"] or
            row.get("kind") != declaration["kind"] or row.get("actor_id") != actor.entity_id):
        raise ValueError("setup Move state source identity changed")
    if type(row.get("prepared_round")) is not int or row["prepared_round"] < 0:
        raise ValueError("invalid setup Move preparation round")
    if turn is not None and (row.get("prepared_turn") != turn["prepared_turn"]
                             or row["prepared_round"] != turn["prepared_round"]):
        raise ValueError("source-owned Set-Up preparation disagrees with its actual own turn")
    _point(row.get("origin"))
    if actor.setup_move != row["move_id"]:
        raise ValueError("legacy setup Move marker disagrees with source-owned state")
    if row["kind"] == "fly" and (row.get("altitude_m") != 25 or
                                   actor.spec.get("_movement_altitude") != 25 or not actor.airborne):
        raise ValueError("Fly prepared altitude state changed")
    if row["kind"] == "dig" and (row.get("depth_m") != 25 or
                                   not actor.spec.get("_burrow", {}).get("underground")):
        raise ValueError("Dig prepared underground state changed")
    if row["kind"] == "dive" and (row.get("submerged") is not True or
                                    row.get("water_depth_m", 0) < 10):
        raise ValueError("Dive submerged state changed")
    if row["kind"] == "geomancy":
        cells = row.get("rough_cells")
        if not isinstance(cells, list) or not cells or len({_point(cell) for cell in cells}) != len(cells):
            raise ValueError("Geomancy rough-cell receipt changed")
    return True
