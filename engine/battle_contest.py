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
SCHEMA = 2
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


def _member_row(pokemon, stat_dice, contest_id):
    learned = []
    for move in pokemon.moves:
        if move == "struggle":
            continue
        move_id = pokemon.r.move(move)["id"]
        if move_id != "move/발버둥":
            learned.append(move_id)
    return {
        "pokemon_id": pokemon.entity_id,
        "contestant_id": "battle-contest/" + contest_id + "/" + pokemon.entity_id,
        "appeal": 0,
        "fumble": 0,
        "excitement": 0,
        "stat_dice": deepcopy(stat_dice),
        "moves": learned,
        "last_move": None,
        "double_next": False,
        "double_round": None,
        "immune_fumble": False,
        "faint_observed": pokemon.fainted,
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


def _contestant(row, name, intro_pool):
    c = Contestant(name, deepcopy(row["stat_dice"]), list(row["moves"]),
                   "매력", 1, "귀여움")
    c._contestant_id = row["contestant_id"]
    c.appeal = row["appeal"]
    c.fumble = row["fumble"]
    c.excitement = row["excitement"]
    c.last_move = row["last_move"]
    c.double_next = row["double_next"]
    c.immune_fumble = row["immune_fumble"]
    c.intro_completed = True
    c._intro_stat_dice = intro_pool
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
    for row in state["pokemon"].values():
        row["double_next"], row["double_round"], row["immune_fumble"] = False, None, False
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


def _observe_knockouts(state, index, *, attacker=None, attack_recipients=(), damage_over_time=()):
    """Observe native faint transitions once; every lost slot earns a replacement."""
    knocked_out = []
    for side_number, side in enumerate(state["sides"]):
        for uid in side["active"]:
            row = state["pokemon"][uid]
            fainted = index[uid].fainted
            if fainted and not row["faint_observed"]:
                knocked_out.append(uid)
                side["replacement_center_due"].append(uid)
                recipients = ([attacker.entity_id] if uid in attack_recipients
                              and _side_for(state, attacker.entity_id) != side_number
                              else state["sides"][1 - side_number]["active"] if uid in damage_over_time else [])
                for recipient in recipients:
                    if uid in damage_over_time and (index[recipient].fainted or not index[recipient].on_field):
                        continue
                    bonus = state["pokemon"][recipient]
                    bonus["excitement"] = min(5, bonus["excitement"] + 2)
            row["faint_observed"] = fainted
    _finish_if_defeated(state, index)
    return knocked_out


def _require_actor(index, actor):
    if index.get(actor.entity_id) is not actor:
        raise ValueError("Battle Contest requires the actual registered actor")


def validate(engine, contest_id):
    from contest_features import STATS
    host, state = _find(engine, contest_id)
    index = _world(engine)
    if state.get("schema") != SCHEMA or state.get("contest_id") != contest_id:
        raise ValueError("unsupported Battle Contest state")
    if state.get("source") != SOURCE or state.get("format_size") not in (1, 2, 3):
        raise ValueError("Battle Contest source or format is malformed")
    if state.get("smart_stat_policy") not in ("ptk-literal-defense", "ptu-original-special-defense"):
        raise ValueError("Battle Contest must preserve its explicit Smart-stat source policy")
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
        pool = side.get("intro_dice")
        if type(pool) is not dict or set(pool) - set(STATS) or any(type(n) is not int or n < 0 for n in pool.values()):
            raise ValueError("Battle Contest introduction dice must be one nonnegative side pool")
        due = side.get("replacement_center_due")
        if type(due) is not list or len(set(due)) != len(due) or not set(due) <= set(active):
            raise ValueError("Battle Contest replacement rights must identify lost active slots")
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
    consumed = state.get("consumed_recalls", [])
    if (type(consumed) is not list or any(type(uid) is not str or not uid for uid in consumed)
            or len(set(consumed)) != len(consumed)):
        raise ValueError("Battle Contest recall receipts are malformed")
    for uid, row in state["pokemon"].items():
        if row.get("pokemon_id") != uid:
            raise ValueError("Battle Contest Pokemon identity mismatch")
        if row.get("contestant_id") != "battle-contest/" + contest_id + "/" + uid:
            raise ValueError("Battle Contest participant identity mismatch")
        if type(row.get("excitement")) is not int or not 0 <= row["excitement"] <= 5:
            raise ValueError("Battle Contest excitement must be from zero to five")
        if any(type(value) is not int or value < 0 for value in row.get("stat_dice", {}).values()):
            raise ValueError("Battle Contest stat dice must be nonnegative integers")
        if type(row.get("faint_observed")) is not bool:
            raise ValueError("Battle Contest faint observation is malformed")
        expiry = row.get("double_round")
        if any(type(row.get(flag)) is not bool for flag in ("double_next", "immune_fumble", "center_pending")):
            raise ValueError("Battle Contest effect flags are malformed")
        if row.get("double_next") and (type(expiry) is not int or expiry <= state["rounds_completed"]):
            raise ValueError("Battle Contest next-round boost has expired")
        if not row["double_next"] and expiry is not None:
            raise ValueError("Battle Contest spent boost retains a lifetime")
    return host, state, index


def create(engine, contest_engine, trainers, rosters, active, contest_type,
           introductions, *, contest_id, format_size=1, smart_stat_policy=None):
    """Create one finite occurrence after two real Introduction checks.

    ``introductions`` maps each Trainer identity to the native-bound Contestant
    made by ``ContestEngine.contestant_from_combatants``.  Each Trainer rolls
    once for a shared introduction pool. Each Pokemon separately retains its
    own combat-stat and consumed-Poffin dice under the selected stat policy.
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
    pools = {pokemon.entity_id: contest_engine.stat_pool_from_combatant(
        pokemon, smart_stat_policy=smart_stat_policy, trainer=trainer, engine=engine)
        for trainer, roster in zip(trainers, rosters) for pokemon in roster}
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
            "intro_dice": {stat: value - before[len(sides)][0].get(stat, 0)
                           for stat, value in contestant.stat_dice.items()},
            "replacement_center_due": [],
        })
        for pokemon in roster:
            members[pokemon.entity_id] = _member_row(pokemon, pools[pokemon.entity_id], contest_id)
    state = {
        "schema": SCHEMA,
        "contest_id": contest_id,
        "host_trainer_id": host.entity_id,
        "contest_type": contest_type,
        "smart_stat_policy": smart_stat_policy,
        "format_size": format_size,
        "max_rounds": 2 * len(rosters[0]),
        "rounds_completed": 0,
        "current_round": None,
        "initiative_order": [],
        "status": "ready",
        "sides": sides,
        "pokemon": members,
        "consumed_recalls": [],
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
    _observe_knockouts(state, index, damage_over_time={actor.entity_id for actor in active})
    return tuple(order)


def finish_round(engine, contest_id):
    """Close the native round and consume one of the finite 2N rounds."""
    host, state, index = validate(engine, contest_id)
    if state["status"] != "round":
        raise ValueError("Battle Contest has no open round")
    if engine._active_turn_actor is not None:
        raise ValueError("Battle Contest round cannot finish during an actor turn")
    living = {uid for side in state["sides"] for uid in side["active"] if not index[uid].fainted}
    engine.end_round()
    _observe_knockouts(state, index, damage_over_time=living)
    state["rounds_completed"] += 1
    for row in state["pokemon"].values():
        row["immune_fumble"] = False
        if row["double_round"] is not None and row["double_round"] <= state["rounds_completed"]:
            row["double_next"], row["double_round"] = False, None
    state["current_round"] = None
    state["initiative_order"] = []
    state["status"] = "ready"
    if not _finish_if_defeated(state, index) and state["rounds_completed"] == state["max_rounds"]:
        _complete(state, index, "round_limit")
    import contest_halls as HALLS
    HALLS.award_battle(engine, contest_id)
    return result(engine, contest_id)


def bind_move(engine, completion):
    """Called only by the actual native Move activation, never by a hit claim."""
    import root_resolution as ROOT
    if getattr(engine, "_move_completions", {}).get(completion.get("id")) is not completion:
        raise ValueError("actual native Move completion required")
    matches = []
    for host in _world(engine).values():
        for state in host.spec.get(KEY, {}).values():
            request = state.get("performance_declaration")
            if request is None:
                continue
            plan = request["plan"]
            if (plan["attacker_id"] == completion["actor"].entity_id
                    and plan["move_id"] == completion["move_id"]
                    and plan["target_id"] in {target.entity_id for target in completion["targets"]}
                    and request["native_depth"] == getattr(engine, "_native_move_resolution_depth", 0)):
                matches.append((host, state, request))
    if not matches:
        return
    if len(matches) != 1:
        raise ValueError("native Move must bind exactly one Battle Contest declaration")
    host, state, request = matches[0]
    plan = request["plan"]
    if request["fingerprint"] != ROOT.fingerprint(plan) or plan["round"] != state["current_round"]:
        raise ValueError("Battle Contest performance declaration changed before activation")
    identity = completion["id"]
    record = {"plan": plan, "fingerprint": request["fingerprint"],
              "appeal_committed": False, "native_complete": False}
    state.setdefault("performances", {})[identity] = record
    state["performance_rng_state"] = plan["rng_after"]
    state["performance_log_lines"] = request["log_owner"]
    completion["battle_contest"] = {"host_trainer_id": host.entity_id,
        "contest_id": state["contest_id"], "fingerprint": record["fingerprint"]}
    state.pop("performance_declaration")


def _bound_performance(engine, completion):
    import root_resolution as ROOT
    if getattr(engine, "_move_completions", {}).get(completion.get("id")) is not completion:
        raise ValueError("actual native Move completion required")
    link = completion.get("battle_contest")
    if link is None:
        return None
    host, state = _find(engine, link["contest_id"])
    record = state.get("performances", {}).get(completion["id"])
    if (host.entity_id != link["host_trainer_id"] or record is None
            or link["fingerprint"] != record["fingerprint"]
            or record["fingerprint"] != ROOT.fingerprint(record["plan"])):
        raise ValueError("Battle Contest performance lost its actual Move binding")
    plan = record["plan"]
    if (plan["attacker_id"] != completion["actor"].entity_id
            or plan["move_id"] != completion["move_id"]
            or plan["target_id"] not in {actor.entity_id for actor in completion["targets"]}):
        raise ValueError("Battle Contest performance native actor or Move changed")
    return state, record


def _commit_performance(state, record):
    if record["appeal_committed"]:
        return
    plan = record["plan"]
    if (any(state["pokemon"][uid] != before for uid, before in plan["rows_before"].items())
            or [side["intro_dice"] for side in state["sides"]] != plan["pools_before"]):
        raise ValueError("pending Battle Contest performance sources changed")
    for uid, after in plan["rows_after"].items():
        state["pokemon"][uid].update(deepcopy(after))
    for side, pool in zip(state["sides"], plan["pools_after"]):
        side["intro_dice"].clear()
        side["intro_dice"].update(pool)
    if not plan["struggle"]:
        state["pokemon"][plan["attacker_id"]]["acted_rounds"].append(plan["round"])
    state["performance_log_lines"].extend(plan["logs"])
    record["appeal_committed"] = True


def _cancelled_native_return(engine, completion, event):
    """The native attacker-ineligible terminal has no recipient-return tail."""
    if event.get("continuation_cancelled") != "actor_no_longer_eligible":
        return False
    target = event.get("target")
    result = completion["results"].get(target.entity_id) if target is not None else None
    after = event.get("owner_after", {})
    if (getattr(engine, "_passive_events", {}).get(event.get("id")) is not event
            or event.get("producer") != "Engine.use_move"
            or event.get("completion_id") != completion["id"]
            or event.get("actor") is not completion["actor"]
            or not any(target is actor for actor in completion["targets"])
            or event.get("move_id") != completion["move_id"]
            or event.get("round") != completion["round"]
            or event.get("elapsed_seconds") != completion["seconds"]
            or completion["phase"] != "complete" or completion["sealed"] is not True
            or event.get("phase") != "producer_return_boundary"
            or event.get("status") not in ("applied", "inapplicable")
            or event.get("continuation") is not None
            or not (after.get("fainted") is True or after.get("dead") is True)
            or result is None or result.get("cancelled") is not True or result.get("dealt") != 0
            or result.get("hit") is not event.get("hit") or event.get("dealt") != 0
            or type(event.get("intent_fingerprint")) is not str):
        raise ValueError("actual attacker-ineligible native cancellation required")
    defense = completion.get("defense", {}).get(target.entity_id)
    if defense is not None and (defense.get("event_id") != event["id"]
            or defense.get("phase") != "cancelled" or defense.get("recipients")
            or defense.get("children") or defense.get("total") or defense.get("active_attempt")):
        raise ValueError("native cancelled defense must have no unresolved recipient or paid attempt")
    import passive_events as PASSIVE
    PASSIVE._bind_intent(engine, event)
    return True


def complete_move(engine, completion):
    """Consume only the existing completed Move and its actual recipient returns."""
    bound = _bound_performance(engine, completion)
    if bound is None:
        return
    state, record = bound
    if record["native_complete"] or completion["phase"] != "complete":
        return
    import action_lifecycle as ACTION
    import move_completion as COMPLETE
    if ACTION.pending_resolution_effects(engine, completion):
        return
    events = [event for event in getattr(engine, "_passive_events", {}).values()
              if event.get("completion_id") == completion["id"]]
    for event in events:
        if event["id"] not in completion.get("native_returns", {}):
            if not _cancelled_native_return(engine, completion, event):
                return
        else:
            COMPLETE.require_returned_event(engine, event["id"])
    recipients = COMPLETE.actual_recipients(completion)
    knocked_out = []
    for actor in recipients:
        result = COMPLETE.recipient_result(completion, actor)
        if result is None or not result["hit"] or result.get("cancelled") or result.get("hit_prevented"):
            continue
        actual = next((event for event in events if event["target"] is actor
                       and event.get("producer") == "Engine.use_move/defense-recipient"), None)
        if actual is None:
            actual = next((event for event in events if event["target"] is actor), None)
        if actual is not None:
            if completion["native_returns"][actual["id"]]["facts"]["hit_prevented"]:
                continue
            COMPLETE.require_hit_return(engine, actual["id"], actor)
        before = (actual["target_before"]["fainted"] if actual is not None
                  else record["plan"]["fainted_before"].get(actor.entity_id, True))
        after = actual["target_after"]["fainted"] if actual is not None else actor.fainted
        if not before and after:
            knocked_out.append(actor.entity_id)
    _commit_performance(state, record)
    if state["status"] != "complete":
        _observe_knockouts(state, _world(engine), attacker=completion["actor"], attack_recipients=knocked_out)
    record["native_complete"] = True
    record["result"] = {"completion_id": completion["id"],
        "recipient_ids": [actor.entity_id for actor in recipients], "knockout_ids": knocked_out,
        "appeal_committed": not record["plan"]["struggle"]}
    import contest_halls as HALLS
    HALLS.award_battle(engine, state["contest_id"])
    return record["result"]


def validate_world(engine, index):
    """Validate persisted performance choices against their native Move owner."""
    completions = getattr(engine, "_move_completions", {})
    for host in index.values():
        for state in host.spec.get(KEY, {}).values():
            if "performance_declaration" in state:
                raise ValueError("unactivated Battle Contest declaration cannot be saved")
            for identity, record in state.get("performances", {}).items():
                completion = completions.get(identity)
                if completion is None or _bound_performance(engine, completion) != (state, record):
                    raise ValueError("Battle Contest performance lacks its actual Move completion")
                if any(type(record.get(key)) is not bool for key in ("appeal_committed", "native_complete")):
                    raise ValueError("Battle Contest performance completion flags are malformed")
                if record["native_complete"] and (not record["appeal_committed"] or completion["phase"] != "complete"):
                    raise ValueError("Battle Contest completion predates its native Move")
                if record["native_complete"]:
                    import move_completion as COMPLETE
                    result = record.get("result")
                    recipients = [actor.entity_id for actor in COMPLETE.actual_recipients(completion)]
                    if (type(result) is not dict or result.get("completion_id") != identity
                            or result.get("recipient_ids") != recipients
                            or result.get("appeal_committed") is not (not record["plan"]["struggle"])
                            or type(result.get("knockout_ids")) is not list
                            or not set(result["knockout_ids"]) <= set(recipients)):
                        raise ValueError("Battle Contest result lost its actual native recipients")
                if not record["appeal_committed"]:
                    plan = record["plan"]
                    if (any(state["pokemon"][uid] != before for uid, before in plan["rows_before"].items())
                            or [side["intro_dice"] for side in state["sides"]] != plan["pools_before"]
                            or state.get("performance_rng_state") != plan["rng_after"]):
                        raise ValueError("pending Battle Contest choice, spend or RNG changed")
    for completion in completions.values():
        if "battle_contest" in completion:
            _bound_performance(engine, completion)


def perform_move(engine, contest_engine, contest_id, attacker, target, move_id, *,
                 spend_stat_dice=0, spend_intro_dice=0, fixed_rolls=None, combat_options=None):
    """Resolve one native Move and its Appeal roll under one declaration.

    The existing native activation binds the frozen Appeal declaration. Its
    actual completion commits the performance once, including a defense resume.
    """
    host, state, index = validate(engine, contest_id)
    _require_actor(index, attacker)
    _require_actor(index, target)
    if state["status"] != "round":
        raise ValueError("Battle Contest Move requires an open round")
    side = _side_for(state, attacker.entity_id)
    other = 1 - side
    if (attacker.entity_id not in state["sides"][side]["active"]
            or target.entity_id not in state["sides"][_side_for(state, target.entity_id)]["active"]):
        raise ValueError("Battle Contest Move requires active Pokemon; the native Move owns targeting")
    if attacker.fainted or target.fainted:
        raise ValueError("fainted Pokemon cannot perform or receive this Battle Contest Move")
    canonical = engine.r.move(move_id)["id"]
    struggle = canonical in ("struggle", "move/발버둥")
    if "performance_declaration" in state or any(not row["appeal_committed"] for row in state.get("performances", {}).values()):
        raise ValueError("resume the actual pending Battle Contest Move")
    rng_before = (contest_engine.rng.getstate() if contest_engine.log_lines is state.get("performance_log_lines")
                  else state.get("performance_rng_state", contest_engine.rng.getstate()))
    rows_before = deepcopy(state["pokemon"])
    pools_before = [deepcopy(side["intro_dice"]) for side in state["sides"]]
    staged_engine, staged_rows = None, None
    if not struggle:
        staged_engine = copy(contest_engine)
        staged_engine.rng = deepcopy(contest_engine.rng)
        staged_engine.rng.setstate(rng_before)
        staged_engine.log_lines = []
        staged_rows = deepcopy(state["pokemon"])
        staged_pools = [deepcopy(side["intro_dice"]) for side in state["sides"]]
        opponents = [uid for uid in state["sides"][other]["active"]
                     if index[uid].on_field and not index[uid].fainted]
        actors = {uid: _contestant(staged_rows[uid], index[uid].name,
                                  staged_pools[_side_for(state, uid)])
                  for uid in (attacker.entity_id, *opponents)}
        attacker_row = staged_rows[attacker.entity_id]
        actors[attacker.entity_id].double_next = (attacker_row["double_next"] and
                                                attacker_row["double_round"] == state["current_round"])
        staged_engine.perform(
            actors[attacker.entity_id], canonical, state["contest_type"],
            [actors[uid] for uid in opponents],
            staged_rows[attacker.entity_id]["center_pending"],
            spend_stat_dice=spend_stat_dice, spend_intro_dice=spend_intro_dice, fixed_rolls=fixed_rolls)
        for uid, contestant in actors.items():
            _sync(staged_rows[uid], contestant)
        if contest_engine.r.move_contest(canonical)[1] == "준비하기":
            attacker_row["double_round"] = state["current_round"] + 1
        elif attacker_row["double_round"] is not None and attacker_row["double_round"] > state["current_round"]:
            attacker_row["double_next"] = True
        else:
            attacker_row["double_round"] = None
        staged_rows[attacker.entity_id]["center_pending"] = False
    if struggle:
        staged_rows, staged_pools = deepcopy(rows_before), deepcopy(pools_before)
        staged_rows[attacker.entity_id]["center_pending"] = False
    import root_resolution as ROOT
    plan = {"attacker_id": attacker.entity_id, "target_id": target.entity_id,
        "move_id": canonical, "round": state["current_round"], "struggle": struggle,
        "spend_stat_dice": spend_stat_dice, "spend_intro_dice": spend_intro_dice,
        "rows_before": rows_before, "rows_after": staged_rows,
        "pools_before": pools_before, "pools_after": staged_pools,
        "fainted_before": {uid: actor.fainted for uid, actor in index.items() if uid in state["pokemon"]},
        "rng_before": rng_before, "rng_after": rng_before if struggle else staged_engine.rng.getstate(),
        "logs": [] if struggle else staged_engine.log_lines}
    before_completions = set(getattr(engine, "_move_completions", {}))
    state["performance_declaration"] = {"plan": plan, "fingerprint": ROOT.fingerprint(plan),
        "native_depth": getattr(engine, "_native_move_resolution_depth", 0) + 1,
        "log_owner": state.get("performance_log_lines", contest_engine.log_lines)}
    try:
        combat = engine.use_move(attacker, target, canonical, **dict(combat_options or {}))
    finally:
        _, state = _find(engine, contest_id)
        state.pop("performance_declaration", None)
        activated = [row for identity, row in getattr(engine, "_move_completions", {}).items()
                     if identity not in before_completions and row.get("battle_contest", {}).get("contest_id") == contest_id]
        if activated:
            contest_engine.rng.setstate(state["performance_rng_state"])
            contest_engine.log_lines = state["performance_log_lines"]
    if not activated:
        return {"combat": combat, "appeal_committed": False, "knockout": False}
    if len(activated) != 1:
        raise ValueError("one Battle performance must bind one actual Move")
    completion = activated[0]
    record = state["performances"][completion["id"]]
    # A returned delayed Move has performed now; its native completion still
    # owns any eventual hit/KO. A suspended defense never reaches this tail.
    _commit_performance(state, record)
    complete_move(engine, completion)
    knocked_out = record.get("result", {}).get("knockout_ids", [])
    return {"combat": combat, "appeal_committed": not struggle, "knockout": bool(knocked_out),
            "completion_id": completion["id"], "result": result(engine, contest_id)}


def start_turn(engine, contest_id, actor, *, initiative_count=None):
    """Start the actual combat turn, observing weather and other start-tick KOs."""
    host, state, index = validate(engine, contest_id)
    _require_actor(index, actor)
    side = _side_for(state, actor.entity_id)
    if state["status"] != "round" or actor.entity_id not in state["sides"][side]["active"]:
        raise ValueError("Battle Contest turn starter needs an open round and active Pokemon")
    living = {actor.entity_id} if not actor.fainted else set()
    engine.start_of_turn(actor, initiative_count=initiative_count)
    knocked_out = _observe_knockouts(state, index, damage_over_time=living)
    import contest_halls as HALLS
    HALLS.award_battle(engine, contest_id)
    return {"knockout": actor.entity_id in knocked_out, "result": result(engine, contest_id)}


def finish_turn(engine, contest_id, actor):
    """Consume native end-of-turn damage and route an ensuing KO bonus."""
    host, state, index = validate(engine, contest_id)
    _require_actor(index, actor)
    side = _side_for(state, actor.entity_id)
    if actor.entity_id not in state["sides"][side]["active"]:
        raise ValueError("Battle Contest turn finisher must be active")
    living = {actor.entity_id} if not actor.fainted else set()
    engine.end_of_turn(actor)
    state["pokemon"][actor.entity_id]["center_pending"] = False
    knocked_out = _observe_knockouts(state, index, damage_over_time=living)
    knockout = actor.entity_id in knocked_out
    import contest_halls as HALLS
    HALLS.award_battle(engine, contest_id)
    return {"knockout": knockout, "result": result(engine, contest_id)}






def _latest_move(engine, state, outgoing):
    rows = [row for row in getattr(engine, "_move_completions", {}).values()
            if row["actor"] is outgoing]
    if not rows:
        raise ValueError("recall exception requires the actual completed Move")
    row = rows[-1]
    if (row["phase"] != "complete"
            or row["round"] != engine.round_no
            or row["turn_serial"] != outgoing.custom_conditions.get("combat_turn_serial", 0)
            or row["id"] in state.get("consumed_recalls", [])):
        raise ValueError("recall exception requires a fresh completed native Move")
    bound = _bound_performance(engine, row)
    if bound is None or bound[0] is not state or not bound[1]["native_complete"]:
        raise ValueError("recall exception requires its completed Battle Contest performance")
    import native_switch_transfer as SWITCH
    current=SWITCH.action_boundary(engine)
    recorded=row.get("native_switch_window")
    if recorded != current:
        prior=recorded if isinstance(recorded,dict) else {}
        changed={key:{'recorded':prior.get(key),'current':current.get(key)}
                 for key in prior.keys() | current.keys() if prior.get(key)!=current.get(key)}
        raise ValueError("recall exception lost its immediate native action boundary: " + repr(changed))
    return row



def _recall_receipt(engine, state, outgoing, source):
    """A source label authorizes nothing without its completed native effect."""
    row = _latest_move(engine, state, outgoing)
    if row["move_id"] != source or outgoing.on_field:
        raise ValueError("recall exception requires a fresh completed native recall")
    import effect_contracts as CONTRACTS
    for token in row["effects"]:
        proof = engine._effect_dispatch_receipts[token]
        if (proof["source_id"] == source and proof["actor"] is outgoing
                and proof["status"] == "completed"
                and proof["effect"].get("type") in ("switch_out", "switch_out_after_damage")):
            CONTRACTS.validate_receipt(engine, token, source, proof["occurrence"],
                                      outgoing, proof["target"], proof["effect"])
            native = proof.get("native_switch")
            import native_switch_transfer as SWITCH
            if (not isinstance(native, dict) or native.get("source") != source
                    or native.get("outgoing_id") != outgoing.entity_id or native.get("recalled") is not True
                    or native.get("integrity") != SWITCH.seal(native)
                    or native.get("move_completion") != row["id"]):
                raise ValueError("recall effect lacks its actual native switch observation")
            return row["id"], native
    raise ValueError("recall exception requires a completed switch-out effect")



def switch(engine, contest_id, trainer, outgoing, incoming, *, position=None,
           source=None, reason="Battle Contest switch"):
    """Replace one active slot, spending its Pokemon turn unless it fainted."""
    host, state, index = validate(engine, contest_id)
    for actor in (trainer, outgoing, incoming):
        _require_actor(index, actor)
    side = _side_for(state, outgoing.entity_id)
    if trainer.entity_id != state["sides"][side]["trainer_id"] or incoming.entity_id not in state["sides"][side]["roster"]:
        raise ValueError("Battle Contest switch requires the owning Trainer and roster")
    slots = state["sides"][side]["active"]
    if outgoing.entity_id not in slots or incoming.entity_id in slots:
        raise ValueError("Battle Contest switch requires active outgoing and benched incoming Pokemon")
    if incoming.fainted or incoming.dead:
        raise ValueError("Battle Contest replacement must be conscious")
    forced = outgoing.fainted
    if not forced and source is None and engine._active_turn_actor is not outgoing:
        raise ValueError("voluntary Battle Contest switch uses the outgoing Pokemon turn")
    source_id = None
    if source is not None:
        source_id = engine.r.move(source)["id"] if str(source).startswith("move/") or source in ("배턴터치", "유턴", "볼트체인지") else source
        if source_id not in RECALL_EXEMPT_MOVES | RECALL_EXEMPT_FEATURES:
            raise ValueError("unknown Battle Contest recall-loss exception")
    round_trip, tag_in = source_id == "feat/왕복-여행", source_id == "feat/태그-인"
    recall_id, native_switch = None, None
    if source_id in RECALL_EXEMPT_MOVES:
        recall_id, native_switch = _recall_receipt(engine, state, outgoing, source_id)
    elif tag_in and not outgoing.on_field:
        previous = _latest_move(engine, state, outgoing)["move_id"]
        if previous not in RECALL_EXEMPT_MOVES:
            raise ValueError("already-recalled Tag In requires the actual source Move")
        recall_id, native_switch = _recall_receipt(engine, state, outgoing, previous)
    already_sent = native_switch is not None and native_switch.get("sent") is True
    if already_sent:
        if tag_in or native_switch.get("incoming_id") != incoming.entity_id or not incoming.on_field:
            raise ValueError("Battle Contest replacement differs from the actual native send-out")
    elif incoming.on_field:
        raise ValueError("Battle Contest replacement must be recalled before its native send-out")
    if tag_in and recall_id is None and not forced and engine._active_turn_actor is not outgoing:
        raise ValueError("voluntary Battle Contest switch uses the outgoing Pokemon turn")
    if position is None:
        position = incoming.pos if already_sent else outgoing.pos
    position = tuple(position)
    if (already_sent and position != tuple(incoming.pos)) or (round_trip and position != tuple(outgoing.pos)):
        raise ValueError("source-specific replacement must keep its actual native position")
    import state_grants as GRANTS
    participants = tuple({id(actor): actor for actor in (outgoing, incoming, trainer)}.values())
    def apply(e, staged_host, *staged_participants):
        staged = {actor.entity_id: actor for actor in staged_participants}
        old, new, owner = staged[outgoing.entity_id], staged[incoming.entity_id], staged[trainer.entity_id]
        turn_spent = not forced and recall_id is None and not round_trip
        if turn_spent:
            import turn as TURN
            if not TURN.spend(e, old, "standard", reason):
                raise ValueError("outgoing Pokemon cannot spend its Battle Contest turn")
        import body_state as BODY
        if not already_sent and e.grid is not None and not BODY.can_place(e, new, position, ignore_actors=(old,)):
            raise ValueError("Battle Contest replacement position is unavailable")
        import combat_state_lifecycle as COMBAT
        import native_switch_transfer as SWITCH
        feature_id = None
        if round_trip:
            produced = SWITCH.round_trip(e, owner, old, new)
            feature_id = produced["occurrence"]
        else:
            if tag_in and recall_id is None:
                SWITCH.select_tag_in(e, owner, old, reason=reason)
            if recall_id is None:
                COMBAT.recall(e, old)
            if tag_in:
                pending = owner.spec.get(SWITCH.TAG)
                if pending is not None:
                    if pending["outgoing_id"] != old.entity_id or pending["phase"] != "pending":
                        raise ValueError("Tag In must use the actual pending outgoing recall")
                    produced = pending
                else:
                    produced = SWITCH.activate(e, owner, SWITCH.TAG_IN, old)
                feature_id = "tag-in:" + produced["recall_id"]
            if not already_sent:
                COMBAT.send_out(e, new, pos=position)
        occurrence = staged_host.spec[KEY][contest_id]
        staged_side = occurrence["sides"][side]
        slot = staged_side["active"].index(old.entity_id)
        staged_side["active"][slot] = new.entity_id
        occurrence["pokemon"][new.entity_id]["faint_observed"] = new.fainted
        if source_id is None:
            row = occurrence["pokemon"][old.entity_id]
            row["excitement"] = max(0, row["excitement"] - 2)
        if old.entity_id in staged_side["replacement_center_due"]:
            occurrence["pokemon"][new.entity_id]["center_pending"] = True
            staged_side["replacement_center_due"].remove(old.entity_id)
        if recall_id is not None:
            occurrence.setdefault("consumed_recalls", []).append(recall_id)
        if feature_id is not None:
            occurrence.setdefault("consumed_recalls", []).append(feature_id)
        return {"outgoing": old.entity_id, "incoming": new.entity_id,
                "turn_spent": turn_spent, "loss_exempt": source_id is not None,
                "source": source_id, "position": list(position)}
    receipt = GRANTS.transition(engine, host, apply, participants=participants, include_grid=engine.grid is not None)
    validate(engine, contest_id)
    return receipt


def party_switched(engine,trainer,receipt):
    """The paid native party producer also updates its actual Contest slot."""
    if len(receipt['recalled'])!=1 or len(receipt['sent'])!=1:return
    old,new=receipt['recalled'][0],receipt['sent'][0]
    plan=receipt.get('feature_plan',{})
    exempt=plan.get('source')=='feat/왕복-여행' or plan.get('tag_in') is True
    for host in _world(engine).values():
        for occurrence in host.spec.get(KEY,{}).values():
            if occurrence['status']!='round':continue
            for side in occurrence['sides']:
                if side['trainer_id']!=trainer.entity_id or old not in side['active']:continue
                if new not in side['roster'] or new in side['active']:raise ValueError('actual Battle Contest party replacement required')
                side['active'][side['active'].index(old)]=new
                if not exempt:occurrence['pokemon'][old]['excitement']=max(0,occurrence['pokemon'][old]['excitement']-2)
                if side['replacement_center_due']:
                    occurrence['pokemon'][new]['center_pending']=True;side['replacement_center_due']=False
                occurrence.setdefault('party_switches',[]).append({'request_id':receipt['request_id'],'source':plan.get('source'),'tag_in':plan.get('tag_in',False),'loss_exempt':exempt,'outgoing':old,'incoming':new})


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

