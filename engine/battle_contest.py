"""Battle Contest occurrence contract for C08-097 through C08-104.

The ordinary combat engine remains authoritative for initiative, attacks,
damage, turn costs, fainting and field membership.  This module owns only the
additional Battle Contest ledger: team Appeal, per-Pokemon Voltage and Contest
Stat Dice, the finite round clock and the replacement Center-of-Attention flag.

The occurrence is stored under its first Trainer's ``spec``.  Consequently the
whole ledger follows the native actor through GM snapshots and JSON engine
round trips without teaching the state codec another parallel object graph.
"""
from copy import copy, deepcopy

from contest import Contestant


KEY = "battle_contest_occurrences"
SCHEMA = 1
SOURCE = "input/ch08-contests.md:291-307"
RECALL_EXEMPT_MOVES = frozenset(("move/배턴터치", "move/유턴", "move/볼트체인지"))
RECALL_EXEMPT_FEATURES = frozenset(("feat/왕복-여행", "feat/태그-인"))


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be nonempty text")
    return value


def _world(engine, extra=()):
    import world_entities as WORLD
    return WORLD.actor_index(engine, extra=extra)


def _member_row(pokemon, stat_dice):
    learned = []
    for move in pokemon.moves:
        if move == "struggle":
            continue
        move_id = pokemon.r.move(move)["id"]
        if move_id != "move/발버둥":
            learned.append(move_id)
    return {
        "pokemon_id": pokemon.entity_id,
        "appeal": 0,
        "fumble": 0,
        "excitement": 0,
        "stat_dice": deepcopy(stat_dice),
        "moves": learned,
        "last_move": None,
        "double_next": False,
        "immune_fumble": False,
        "center_pending": False,
        "acted_rounds": [],
    }


def _find(engine, contest_id):
    contest_id = _text(contest_id, "battle contest identity")
    for actor in _world(engine).values():
        if actor.kind != "trainer":
            continue
        row = actor.spec.get(KEY, {}).get(contest_id)
        if row is not None:
            if row.get("host_trainer_id") != actor.entity_id:
                raise ValueError("battle contest host identity mismatch")
            return actor, row
    raise ValueError("unknown battle contest occurrence")


def _side_for(state, pokemon_id):
    found = [index for index, side in enumerate(state["sides"])
             if pokemon_id in side["roster"]]
    if len(found) != 1:
        raise ValueError("Pokemon must belong to exactly one Battle Contest side")
    return found[0]


def _contestant(row, name):
    c = Contestant(name, deepcopy(row["stat_dice"]), list(row["moves"]),
                   "매력", 1, "귀여움")
    c.appeal = row["appeal"]
    c.fumble = row["fumble"]
    c.excitement = row["excitement"]
    c.last_move = row["last_move"]
    c.double_next = row["double_next"]
    c.immune_fumble = row["immune_fumble"]
    c.intro_completed = True
    return c


def _sync(row, contestant):
    row.update(
        appeal=contestant.appeal,
        fumble=contestant.fumble,
        excitement=contestant.excitement,
        stat_dice=deepcopy(contestant.stat_dice),
        last_move=contestant.last_move,
        double_next=contestant.double_next,
        immune_fumble=contestant.immune_fumble,
    )


def _score(state, side):
    data = state["sides"][side]
    return data["intro_appeal"] + sum(
        state["pokemon"][uid]["appeal"] - state["pokemon"][uid]["fumble"]
        for uid in data["roster"])


def _complete(state, index, reason):
    if state["status"] == "complete":
        return
    scores = [_score(state, 0), _score(state, 1)]
    state["status"] = "complete"
    state["completion_reason"] = reason
    state["scores"] = scores
    state["winner_trainer_id"] = (None if scores[0] == scores[1]
                                   else state["sides"][0 if scores[0] > scores[1] else 1]["trainer_id"])


def _finish_if_defeated(state, index):
    defeated = []
    for number, side in enumerate(state["sides"]):
        if all(index[uid].fainted for uid in side["roster"]):
            defeated.append(number)
    if defeated:
        _complete(state, index, "all_pokemon_fainted")
    return defeated


def validate(engine, contest_id):
    host, state = _find(engine, contest_id)
    index = _world(engine)
    if state.get("schema") != SCHEMA or state.get("contest_id") != contest_id:
        raise ValueError("unsupported Battle Contest state")
    if state.get("source") != SOURCE or state.get("format_size") not in (1, 2, 3):
        raise ValueError("Battle Contest source or format is malformed")
    if len(state.get("sides", ())) != 2 or len(state.get("pokemon", {})) not in range(6, 13):
        raise ValueError("Battle Contest needs two three-to-six Pokemon rosters")
    roster_ids = []
    for side in state["sides"]:
        roster = side.get("roster", [])
        active = side.get("active", [])
        if not 3 <= len(roster) <= 6 or len(active) != state["format_size"]:
            raise ValueError("Battle Contest roster or active-slot count is malformed")
        trainer = index.get(side.get("trainer_id"))
        if trainer is None or trainer.kind != "trainer":
            raise ValueError("Battle Contest trainer must remain in the world")
        for uid in roster:
            pokemon = index.get(uid)
            if (pokemon is None or pokemon.kind != "pokemon"
                    or (state.get("status") != "complete" and pokemon.spec.get("trainer_id") != trainer.entity_id)):
                raise ValueError("Battle Contest roster ownership changed")
        if len(set(active)) != len(active) or not set(active) <= set(roster):
            raise ValueError("Battle Contest active slots must select distinct roster members")
        roster_ids.extend(roster)
    if len(set(roster_ids)) != len(roster_ids) or set(roster_ids) != set(state["pokemon"]):
        raise ValueError("Battle Contest rosters and Pokemon ledger disagree")
    if len(state["sides"][0]["roster"]) != len(state["sides"][1]["roster"]):
        raise ValueError("Battle Contest sides must declare the same roster size")
    if state.get("max_rounds") != 2 * len(state["sides"][0]["roster"]):
        raise ValueError("Battle Contest round limit must be twice the roster size")
    if type(state.get("rounds_completed")) is not int or not 0 <= state["rounds_completed"] <= state["max_rounds"]:
        raise ValueError("Battle Contest round lifetime is malformed")
    if state.get("status") not in ("ready", "round", "complete"):
        raise ValueError("Battle Contest phase is malformed")
    for uid, row in state["pokemon"].items():
        if row.get("pokemon_id") != uid:
            raise ValueError("Battle Contest Pokemon identity mismatch")
        if type(row.get("excitement")) is not int or not 0 <= row["excitement"] <= 5:
            raise ValueError("Battle Contest excitement must be from zero to five")
        if any(type(value) is not int or value < 0 for value in row.get("stat_dice", {}).values()):
            raise ValueError("Battle Contest stat dice must be nonnegative integers")
    return host, state, index


def create(engine, contest_engine, trainers, rosters, active, contest_type,
           introductions, *, contest_id, format_size=1):
    """Create one finite occurrence after two real Introduction checks.

    ``introductions`` maps each Trainer identity to the native-bound Contestant
    made by ``ContestEngine.contestant_from_combatants``.  Each Trainer rolls
    once; that side's resulting pool is copied as a separate balance for every
    declared Pokemon, so spending never leaks between team members.
    """
    contest_id = _text(contest_id, "battle contest identity")
    trainers, rosters, active = tuple(trainers), tuple(map(tuple, rosters)), tuple(map(tuple, active))
    if len(trainers) != 2 or len(rosters) != 2 or len(active) != 2:
        raise ValueError("Battle Contest requires exactly two Trainers and two rosters")
    if type(format_size) is not int or format_size not in (1, 2, 3):
        raise ValueError("Battle Contest format must be single, double or triple")
    if any(len(team) < format_size for team in rosters) or any(len(team) != len(rosters[0]) for team in rosters):
        raise ValueError("Battle Contest sides need equal rosters large enough for the format")
    if not 3 <= len(rosters[0]) <= 6:
        raise ValueError("Battle Contest roster size must be from three through six")
    if any(len(team) != format_size for team in active):
        raise ValueError("Battle Contest active slots must match its format")
    subjects = [*trainers, *(p for team in rosters for p in team)]
    index = _world(engine, extra=subjects)
    if len({id(actor) for actor in subjects}) != len(subjects):
        raise ValueError("Battle Contest declarations need distinct actual actors")
    if any(t.kind != "trainer" for t in trainers):
        raise ValueError("Battle Contest sides require actual Trainers")
    for trainer, roster, fielded in zip(trainers, rosters, active):
        if any(p.kind != "pokemon" or p.spec.get("trainer_id") != trainer.entity_id for p in roster):
            raise ValueError("Battle Contest roster needs actually owned Pokemon")
        if len(set(map(id, fielded))) != len(fielded) or not set(fielded) <= set(roster):
            raise ValueError("Battle Contest active slots need distinct roster Pokemon")
        if any(not p.on_field or p.fainted for p in fielded):
            raise ValueError("initial Battle Contest active Pokemon must be conscious and on field")
        if any(p.on_field for p in roster if p not in fielded):
            raise ValueError("Battle Contest bench Pokemon must start recalled")
    host = trainers[0]
    if contest_id in host.spec.get(KEY, {}):
        raise ValueError("Battle Contest identity was already used")
    intro = []
    bindings = getattr(contest_engine, "_native_intro_bindings", {})
    for trainer, roster in zip(trainers, rosters):
        candidate = introductions.get(trainer.entity_id)
        binding = bindings.get(candidate)
        if candidate is None or binding is None or binding[0] is not engine or binding[2] is not trainer or binding[1] not in roster:
            raise ValueError("Battle Contest introduction needs the actual Trainer and one declared Pokemon")
        intro.append(candidate)
    before = [(deepcopy(c.stat_dice), c.appeal, c.intro_completed) for c in intro]
    import contest_halls as HALLS
    HALLS._source(engine.r, contest_engine.r)
    HALLS.WORLD.require_actors(engine, *subjects)
    contest_engine.intro_stage(intro, contest_type)
    if not all(c.intro_completed for c in intro):
        raise ValueError("Battle Contest introduction did not complete")
    sides, members = [], {}
    for trainer, roster, fielded, contestant in zip(trainers, rosters, active, intro):
        sides.append({
            "trainer_id": trainer.entity_id,
            "roster": [p.entity_id for p in roster],
            "active": [p.entity_id for p in fielded],
            "intro_appeal": contestant.appeal - before[len(sides)][1],
            "replacement_center_due": False,
        })
        for pokemon in roster:
            members[pokemon.entity_id] = _member_row(pokemon, contestant.stat_dice)
    state = {
        "schema": SCHEMA,
        "contest_id": contest_id,
        "host_trainer_id": host.entity_id,
        "contest_type": contest_type,
        "format_size": format_size,
        "max_rounds": 2 * len(rosters[0]),
        "rounds_completed": 0,
        "current_round": None,
        "initiative_order": [],
        "status": "ready",
        "sides": sides,
        "pokemon": members,
        "source": SOURCE,
    }
    host.spec.setdefault(KEY, {})[contest_id] = state
    validate(engine, contest_id)
    return deepcopy(state)


def begin_round(engine, contest_id):
    """Start one native combat round and record its unmodified initiative."""
    host, state, index = validate(engine, contest_id)
    if state["status"] == "complete":
        raise ValueError("completed Battle Contest has no further rounds")
    if state["status"] == "round":
        raise ValueError("current Battle Contest round must finish first")
    if state["rounds_completed"] >= state["max_rounds"]:
        raise ValueError("Battle Contest round limit was reached")
    active = [index[uid] for side in state["sides"] for uid in side["active"] if not index[uid].fainted]
    if not active:
        raise ValueError("Battle Contest round needs conscious active Pokemon")
    order = engine.initiative(active)
    if order is None:
        raise ValueError("Battle Contest cannot hide a pending ordinary initiative decision")
    # Ordinary initiative can expose a required GM decision. Hold that boundary
    # before native round effects so resolving/retrying cannot start twice.
    engine.start_round(active)
    state["current_round"] = state["rounds_completed"] + 1
    state["initiative_order"] = [actor.entity_id for actor in order]
    state["status"] = "round"
    return tuple(order)


def finish_round(engine, contest_id):
    """Close the native round and consume one of the finite 2N rounds."""
    host, state, index = validate(engine, contest_id)
    if state["status"] != "round":
        raise ValueError("Battle Contest has no open round")
    if engine._active_turn_actor is not None:
        raise ValueError("Battle Contest round cannot finish during an actor turn")
    engine.end_round()
    state["rounds_completed"] += 1
    state["current_round"] = None
    state["initiative_order"] = []
    state["status"] = "ready"
    if not _finish_if_defeated(state, index) and state["rounds_completed"] == state["max_rounds"]:
        _complete(state, index, "round_limit")
    import contest_halls as HALLS
    HALLS.award_battle(engine, contest_id)
    return result(engine, contest_id)


def perform_move(engine, contest_engine, contest_id, attacker, target, move_id, *,
                 spend_stat_dice=0, fixed_rolls=None, combat_options=None):
    """Resolve one native Move and its Appeal roll under one declaration.

    The Appeal calculation is staged first.  It commits only if ``use_move``
    records the native Move activation.  Struggle still resolves in combat but
    never enters the Appeal consumer.
    """
    host, state, index = validate(engine, contest_id)
    if state["status"] != "round":
        raise ValueError("Battle Contest Move requires an open round")
    side = _side_for(state, attacker.entity_id)
    other = 1 - side
    if attacker.entity_id not in state["sides"][side]["active"] or target.entity_id not in state["sides"][other]["active"]:
        raise ValueError("Battle Contest Move requires active opposing Pokemon")
    if attacker.fainted or target.fainted:
        raise ValueError("fainted Pokemon cannot perform or receive this Battle Contest Move")
    canonical = engine.r.move(move_id)["id"]
    struggle = canonical in ("struggle", "move/발버둥")
    staged_engine, staged_rows = None, None
    if not struggle:
        staged_engine = copy(contest_engine)
        staged_engine.rng = deepcopy(contest_engine.rng)
        staged_engine.log_lines = []
        staged_rows = deepcopy(state["pokemon"])
        actors = {uid: _contestant(staged_rows[uid], index[uid].name)
                  for uid in (attacker.entity_id, *state["sides"][other]["active"])}
        staged_engine.perform(
            actors[attacker.entity_id], canonical, state["contest_type"],
            [actors[uid] for uid in state["sides"][other]["active"]],
            staged_rows[attacker.entity_id]["center_pending"],
            spend_stat_dice=spend_stat_dice, fixed_rolls=fixed_rolls)
        for uid, contestant in actors.items():
            _sync(staged_rows[uid], contestant)
        staged_rows[attacker.entity_id]["center_pending"] = False
    uses_before = deepcopy(attacker.move_uses)
    history_before = len(getattr(attacker, "_action_history", ()))
    last_before = attacker.last_move
    target_was_fainted = target.fainted
    combat = engine.use_move(attacker, target, canonical, **dict(combat_options or {}))
    activated = (attacker.move_uses != uses_before or
                 len(getattr(attacker, "_action_history", ())) != history_before or
                 attacker.last_move != last_before)
    if not activated:
        return {"combat": combat, "appeal_committed": False, "knockout": False}
    if not struggle:
        state["pokemon"].update(staged_rows)
        contest_engine.rng.setstate(staged_engine.rng.getstate())
        contest_engine.log_lines.extend(staged_engine.log_lines)
        state["pokemon"][attacker.entity_id]["acted_rounds"].append(state["current_round"])
    else:
        # The replacement is Center on its first acting turn, including a
        # native Struggle that has no Appeal roll (ch08:301).
        state["pokemon"][attacker.entity_id]["center_pending"] = False
    knockout = not target_was_fainted and target.fainted
    if knockout:
        row = state["pokemon"][attacker.entity_id]
        row["excitement"] = min(5, row["excitement"] + 2)
        state["sides"][other]["replacement_center_due"] = True
        _finish_if_defeated(state, index)
    import contest_halls as HALLS
    HALLS.award_battle(engine, contest_id)
    return {"combat": combat, "appeal_committed": not struggle, "knockout": knockout,
            "result": result(engine, contest_id)}


def finish_turn(engine, contest_id, actor):
    """Consume native end-of-turn damage and route an ensuing KO bonus."""
    host, state, index = validate(engine, contest_id)
    side = _side_for(state, actor.entity_id)
    if actor.entity_id not in state["sides"][side]["active"]:
        raise ValueError("Battle Contest turn finisher must be active")
    was_fainted = actor.fainted
    engine.end_of_turn(actor)
    state["pokemon"][actor.entity_id]["center_pending"] = False
    knockout = not was_fainted and actor.fainted
    if knockout:
        for uid in state["sides"][1 - side]["active"]:
            row = state["pokemon"][uid]
            row["excitement"] = min(5, row["excitement"] + 2)
        state["sides"][side]["replacement_center_due"] = True
        _finish_if_defeated(state, index)
    import contest_halls as HALLS
    HALLS.award_battle(engine, contest_id)
    return {"knockout": knockout, "result": result(engine, contest_id)}


def switch(engine, contest_id, trainer, outgoing, incoming, *, position=None,
           source=None, reason="Battle Contest switch"):
    """Replace one active slot, spending its Pokemon turn unless it fainted."""
    host, state, index = validate(engine, contest_id)
    side = _side_for(state, outgoing.entity_id)
    if trainer.entity_id != state["sides"][side]["trainer_id"] or incoming.entity_id not in state["sides"][side]["roster"]:
        raise ValueError("Battle Contest switch requires the owning Trainer and roster")
    slots = state["sides"][side]["active"]
    if outgoing.entity_id not in slots or incoming.entity_id in slots:
        raise ValueError("Battle Contest switch requires active outgoing and benched incoming Pokemon")
    if incoming.on_field or incoming.fainted or incoming.dead:
        raise ValueError("Battle Contest replacement must be a conscious recalled Pokemon")
    forced = outgoing.fainted
    if not forced and engine._active_turn_actor is not outgoing:
        raise ValueError("voluntary Battle Contest switch uses the outgoing Pokemon turn")
    source_id = None
    if source is not None:
        source_id = engine.r.move(source)["id"] if str(source).startswith("move/") or source in ("배턴터치", "유턴", "볼트체인지") else source
        if source_id not in RECALL_EXEMPT_MOVES | RECALL_EXEMPT_FEATURES:
            raise ValueError("unknown Battle Contest recall-loss exception")
    if position is None:
        position = outgoing.pos
    position = tuple(position)
    import state_grants as GRANTS
    participants = tuple({id(actor): actor for actor in (outgoing, incoming, trainer)}.values())
    def apply(e, staged_host, *staged_participants):
        staged = {actor.entity_id: actor for actor in staged_participants}
        old, new, owner = staged[outgoing.entity_id], staged[incoming.entity_id], staged[trainer.entity_id]
        occurrence = staged_host.spec[KEY][contest_id]
        if not forced:
            import turn as TURN
            if not TURN.spend(e, old, "standard", reason):
                raise ValueError("outgoing Pokemon cannot spend its Battle Contest turn")
        import body_state as BODY
        if e.grid is not None and not BODY.can_place(e, new, position, ignore_actors=(old,)):
            raise ValueError("Battle Contest replacement position is unavailable")
        import combat_state_lifecycle as COMBAT
        COMBAT.recall(e, old)
        COMBAT.join(e, [new])
        new.on_field = True
        new.pos = position
        staged_side = occurrence["sides"][side]
        slot = staged_side["active"].index(old.entity_id)
        staged_side["active"][slot] = new.entity_id
        if source_id is None:
            row = occurrence["pokemon"][old.entity_id]
            row["excitement"] = max(0, row["excitement"] - 2)
        if staged_side["replacement_center_due"]:
            occurrence["pokemon"][new.entity_id]["center_pending"] = True
            staged_side["replacement_center_due"] = False
        return {"outgoing": old.entity_id, "incoming": new.entity_id,
                "turn_spent": not forced, "loss_exempt": source_id is not None,
                "source": source_id, "position": list(position)}
    receipt = GRANTS.transition(engine, host, apply, participants=participants, include_grid=engine.grid is not None)
    validate(engine, contest_id)
    return receipt


def result(engine, contest_id):
    host, state, index = validate(engine, contest_id)
    scores = [_score(state, 0), _score(state, 1)]
    return {
        "contest_id": contest_id,
        "status": state["status"],
        "rounds_completed": state["rounds_completed"],
        "max_rounds": state["max_rounds"],
        "scores": scores,
        "winner_trainer_id": state.get("winner_trainer_id"),
        "completion_reason": state.get("completion_reason"),
        "source": SOURCE,
    }

