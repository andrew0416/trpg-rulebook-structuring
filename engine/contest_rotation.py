"""Rotation-contest team, performer, and shared dice-budget state.

The host contest engine owns rolls and effects.  This module owns the parts
that are unique to the source format: one roster per competitor, one
performer per round, an optional order fixed before the contest, one shared
introduction representative, and the 2 * competitor-count spend ceiling.
All returned state is composed of the engine's ordinary contestants and JSON
codec containers so it remains saveable with the contest occurrence.
"""


SCHEMA = 2
_FIELDS = frozenset((
    "schema", "teams", "representatives", "mode", "orders", "round_types",
    "pool_cap", "performed", "spent", "last_moves", "current", "charged",
    "shared", "intro_dice",
))


def _tuple_rows(value, label):
    if not isinstance(value, (list, tuple)):
        raise ValueError(label + " must be an ordered sequence")
    rows = tuple(tuple(row) if isinstance(row, (list, tuple)) else () for row in value)
    if any(not row for row in rows):
        raise ValueError(label + " rows must be nonempty ordered sequences")
    return rows


def create(teams, representatives, *, orders=None, contest_type=None,
           round_types=None, valid_types=()):
    """Create the occurrence-owned rotation contract without callbacks."""
    teams = _tuple_rows(teams, "rotation teams")
    count = len(teams)
    if not 3 <= count <= 5 or any(len(team) != count for team in teams):
        raise ValueError("rotation needs 3..5 teams and one Pokemon per round on every team")
    members = [member for team in teams for member in team]
    if len({id(member) for member in members}) != len(members):
        raise ValueError("a Pokemon can belong to only one rotation roster slot")
    if not isinstance(representatives, (list, tuple)) or len(representatives) != count:
        raise ValueError("each rotation team needs one introduction representative")
    representatives = tuple(representatives)
    if any(rep not in team for rep, team in zip(representatives, teams)):
        raise ValueError("an introduction representative must belong to its team")

    if orders is None:
        mode, normalized_orders = "round-choice", None
    else:
        normalized_orders = _tuple_rows(orders, "predetermined rotation orders")
        if len(normalized_orders) != count or any(
                len(row) != count or len(set(row)) != count or set(row) != set(team)
                for row, team in zip(normalized_orders, teams)):
            raise ValueError("each predetermined order must be an exact team permutation")
        mode = "predetermined"

    valid_types = tuple(valid_types)
    if len(set(valid_types)) != len(valid_types) or any(type(x) is not str for x in valid_types):
        raise ValueError("contest type authority is malformed")
    if round_types is None:
        if contest_type not in valid_types:
            raise ValueError("a fixed rotation contest needs one valid contest type")
        normalized_types = (contest_type,) * count
    else:
        if contest_type is not None or not isinstance(round_types, (list, tuple)):
            raise ValueError("per-round contest types replace, rather than supplement, a fixed type")
        normalized_types = tuple(round_types)
        if len(normalized_types) != count or any(value not in valid_types for value in normalized_types):
            raise ValueError("declare one valid contest type for every rotation round")

    shared = {
        rep: {"excitement": 0, "double_next": False, "immune_fumble": False}
        for rep in representatives
    }
    return {
        "schema": SCHEMA,
        "teams": teams,
        "representatives": representatives,
        "mode": mode,
        "orders": normalized_orders,
        "round_types": normalized_types,
        "pool_cap": 2 * count,
        "performed": {rep: set() for rep in representatives},
        "spent": {rep: 0 for rep in representatives},
        "last_moves": {rep: None for rep in representatives},
        "current": {},
        "charged": {},
        "shared": shared,
        "intro_dice": {rep: {} for rep in representatives},
    }


def declaration(rotation):
    """Immutable portion used to reject a changed roster/order on resume."""
    return tuple(rotation[key] for key in (
        "teams", "representatives", "mode", "orders", "round_types", "pool_cap"))


def bind_shared_state(rotation):
    """Bind team-wide excitement and next-performance effects once."""
    for rep, team in zip(rotation["representatives"], rotation["teams"]):
        shared = rotation["shared"][rep]
        for member in team:
            existing = vars(member).get("_paired_state")
            if existing is not None and existing is not shared:
                raise ValueError("a rotation Pokemon is already bound to another shared contest state")
    for rep, team in zip(rotation["representatives"], rotation["teams"]):
        shared = rotation["shared"][rep]
        for member in team:
            member._paired_state = shared
            member._intro_stat_dice = rotation["intro_dice"][rep]


def share_introduction(rotation, before):
    """Move only the representative's new dice into the team's single pool."""
    for rep in rotation["representatives"]:
        pool = rotation["intro_dice"][rep]
        pool.update({stat: value - before[rep].get(stat, 0)
                     for stat, value in rep.stat_dice.items()})
        rep.stat_dice.clear()
        rep.stat_dice.update(before[rep])


def select_round(rotation, round_index, selector=None):
    """Choose every team's performer atomically and lock the round."""
    count = len(rotation["teams"])
    if type(round_index) is not int or not 0 <= round_index < count:
        raise ValueError("rotation round index is outside the occurrence")
    if rotation["current"]:
        if set(rotation["current"]) != set(rotation["representatives"]):
            raise ValueError("saved rotation performer selection is incomplete")
        return dict(rotation["current"])
    if rotation["mode"] == "round-choice" and not callable(selector):
        raise ValueError("round-choice rotation needs an explicit performer selector")
    if rotation["mode"] == "predetermined" and selector is not None:
        raise ValueError("predetermined rotation order cannot be replaced by a selector")

    planned = {}
    for index, (rep, team) in enumerate(zip(rotation["representatives"], rotation["teams"])):
        used = rotation["performed"][rep]
        available = tuple(member for member in team if member not in used)
        member = (rotation["orders"][index][round_index]
                  if rotation["mode"] == "predetermined"
                  else selector(rep, round_index + 1, available))
        if member not in available:
            raise ValueError("the chosen Pokemon must be unused and belong to that rotation team")
        planned[rep] = member
    rotation["current"].update(planned)
    return dict(planned)


def charge(rotation, representative, performer, attempt_id, spend):
    """Commit a stat-die cost once, including a paused observed reroll."""
    if type(attempt_id) is not str or not attempt_id or type(spend) is not int or spend < 0:
        raise ValueError("rotation spend receipt is malformed")
    expected = {"team": representative, "performer": performer, "spend": spend}
    previous = rotation["charged"].get(attempt_id)
    if previous is not None:
        if previous != expected:
            raise ValueError("rotation spend receipt changed during resume")
        return False
    total = rotation["spent"][representative] + spend
    if total > rotation["pool_cap"]:
        raise ValueError("rotation team exceeded its shared contest-die limit")
    rotation["charged"][attempt_id] = expected
    rotation["spent"][representative] = total
    return True


def ensure_budget(rotation, representative, attempt_id, spend):
    previous = rotation["charged"].get(attempt_id)
    if previous is not None:
        if previous.get("team") is not representative or previous.get("spend") != spend:
            raise ValueError("rotation spend receipt changed during resume")
        return
    if type(spend) is not int or spend < 0 or rotation["spent"][representative] + spend > rotation["pool_cap"]:
        raise ValueError("rotation team exceeded its shared contest-die limit")


def complete_performance(rotation, representative, performer, move_id):
    if rotation["current"].get(representative) is not performer:
        raise ValueError("completed performer differs from the locked rotation choice")
    if performer in rotation["performed"][representative]:
        raise ValueError("a rotation Pokemon cannot perform twice")
    rotation["performed"][representative].add(performer)
    rotation["last_moves"][representative] = move_id


def finish_round(rotation):
    if set(rotation["current"]) != set(rotation["representatives"]):
        raise ValueError("cannot finish a rotation round without every team choice")
    if any(rotation["current"][rep] not in rotation["performed"][rep]
           for rep in rotation["representatives"]):
        raise ValueError("cannot finish a rotation round before every performance commits")
    rotation["current"].clear()


def scores(rotation):
    return {
        rep: (sum(member.appeal for member in team),
              sum(member.fumble for member in team))
        for rep, team in zip(rotation["representatives"], rotation["teams"])
    }


def validate_native_roster(teams, bindings):
    """A native competitor is one owner or N owners with one Pokemon each."""
    members = [member for team in teams for member in team]
    if not any(member in bindings for member in members):
        return
    if any(member not in bindings for member in members):
        raise ValueError("native rotation rosters require an actual binding for every Pokemon")
    import contest_features as FEATURES
    import world_entities as WORLD
    engines = {bindings[member][0] for member in members}
    if len(engines) != 1:
        raise ValueError("native rotation rosters require one actual world")
    engine = next(iter(engines))
    index = WORLD.actor_index(engine)
    pokemon_seen, trainers_seen = set(), set()
    for team in teams:
        owners = set()
        for member in team:
            _, pokemon, trainer, _, _ = bindings[member]
            FEATURES.owner(trainer, pokemon)
            for actor in (pokemon, trainer):
                if actor.r is not engine.r or index.get(actor.entity_id) is not actor:
                    raise ValueError("native rotation needs actual registered Pokemon and Trainers")
            if pokemon in pokemon_seen:
                raise ValueError("a native Pokemon can occupy only one rotation roster slot")
            pokemon_seen.add(pokemon)
            owners.add(trainer)
        if len(owners) not in (1, len(teams)):
            raise ValueError("rotation needs one solo Trainer or one Trainer per team Pokemon")
        if owners & trainers_seen:
            raise ValueError("a native Trainer can belong to only one rotation competitor")
        trainers_seen.update(owners)


def validate(rotation, *, state=None, valid_types=(), move_validator=None,
             native_bindings=None):
    """Validate saved ledgers and their relation to the standard run cursor."""
    if type(rotation) is not dict or set(rotation) != _FIELDS or rotation["schema"] != SCHEMA:
        raise ValueError("invalid rotation contest state fields")
    teams = rotation["teams"]
    reps = rotation["representatives"]
    count = len(teams) if type(teams) is tuple else 0
    if not 3 <= count <= 5 or type(reps) is not tuple or len(reps) != count:
        raise ValueError("invalid saved rotation roster")
    if any(type(team) is not tuple or len(team) != count for team in teams):
        raise ValueError("saved rotation roster size changed")
    members = [member for team in teams for member in team]
    if len(set(members)) != len(members) or any(rep not in team for rep, team in zip(reps, teams)):
        raise ValueError("saved rotation membership changed")
    if native_bindings is not None:
        validate_native_roster(teams, native_bindings)
    if rotation["mode"] not in ("round-choice", "predetermined"):
        raise ValueError("invalid saved rotation selection mode")
    orders = rotation["orders"]
    if rotation["mode"] == "round-choice" and orders is not None:
        raise ValueError("round-choice rotation unexpectedly contains fixed orders")
    if rotation["mode"] == "predetermined" and (
            type(orders) is not tuple or len(orders) != count or
            any(type(row) is not tuple or set(row) != set(team) or len(row) != count
                for row, team in zip(orders, teams))):
        raise ValueError("saved predetermined order changed")
    valid_types = set(valid_types)
    if (type(rotation["round_types"]) is not tuple or len(rotation["round_types"]) != count
            or any(value not in valid_types for value in rotation["round_types"])):
        raise ValueError("saved rotation round types changed")
    if rotation["pool_cap"] != 2 * count:
        raise ValueError("saved rotation dice limit changed")

    keyed = ("performed", "spent", "last_moves", "shared", "intro_dice")
    if any(type(rotation[name]) is not dict or set(rotation[name]) != set(reps) for name in keyed):
        raise ValueError("saved rotation team ledger keys changed")
    seen_shared = set()
    for rep, team in zip(reps, teams):
        performed = rotation["performed"][rep]
        spent = rotation["spent"][rep]
        shared = rotation["shared"][rep]
        if type(performed) is not set or not performed <= set(team):
            raise ValueError("saved rotation performed set is invalid")
        if type(spent) is not int or not 0 <= spent <= rotation["pool_cap"]:
            raise ValueError("saved rotation spent balance is invalid")
        if type(shared) is not dict or set(shared) != {"excitement", "double_next", "immune_fumble"}:
            raise ValueError("saved rotation shared effect state is invalid")
        if (type(shared["excitement"]) is not int or not 0 <= shared["excitement"] <= 5
                or type(shared["double_next"]) is not bool
                or type(shared["immune_fumble"]) is not bool
                or id(shared) in seen_shared):
            raise ValueError("saved rotation shared effect values are invalid")
        seen_shared.add(id(shared))
        if any(vars(member).get("_paired_state") is not shared for member in team):
            raise ValueError("rotation team no longer shares one effect state")
        pool = rotation["intro_dice"][rep]
        if (type(pool) is not dict or set(pool) - valid_types
                or any(type(n) is not int or n < 0 for n in pool.values())
                or any(vars(member).get("_intro_stat_dice") is not pool for member in team)):
            raise ValueError("rotation team no longer shares one introduction pool")
        move = rotation["last_moves"][rep]
        if move is not None:
            if type(move) is not str:
                raise ValueError("saved rotation last Move is invalid")
            if move_validator is not None:
                move_validator(move)

    current = rotation["current"]
    if type(current) is not dict or set(current) not in (set(), set(reps)):
        raise ValueError("saved rotation current choices are incomplete")
    if any(current[rep] not in teams[index]
           for index, rep in enumerate(reps) if rep in current):
        raise ValueError("saved current rotation choice is invalid")
    charged = rotation["charged"]
    if type(charged) is not dict:
        raise ValueError("saved rotation cost receipts are invalid")
    totals = {rep: 0 for rep in reps}
    for attempt, receipt in charged.items():
        if (type(attempt) is not str or not attempt or type(receipt) is not dict
                or set(receipt) != {"team", "performer", "spend"}):
            raise ValueError("saved rotation cost receipt is malformed")
        rep, performer, spend = receipt["team"], receipt["performer"], receipt["spend"]
        if rep not in totals or performer not in teams[reps.index(rep)] or type(spend) is not int or spend < 0:
            raise ValueError("saved rotation cost receipt authority changed")
        totals[rep] += spend
    if totals != rotation["spent"]:
        raise ValueError("saved rotation spend total differs from its receipts")

    if state is not None:
        phase, completed = state.get("phase"), state.get("round")
        if type(completed) is not int or not 0 <= completed <= count:
            raise ValueError("saved rotation progress is invalid")
        if phase in ("intro", "round", "complete") and current:
            raise ValueError("saved rotation choices outlived their performance round")
        if phase == "perform" and set(current) != set(reps):
            raise ValueError("performing rotation lacks locked team choices")
        expected = {rep: completed for rep in reps}
        if phase == "perform":
            table = state["table"]
            row = table["rounds"][completed]
            columns = sorted(range(count), key=lambda i: table["turn_order_by_column"][i])
            by_letter = {rep.letter: rep for rep in reps}
            for position in columns[:state["slot"]]:
                expected[by_letter[row[position]]] += 1
        if any(len(rotation["performed"][rep]) != expected[rep] for rep in reps):
            raise ValueError("saved performed sets disagree with the contest cursor")
        if phase == "complete" and any(set(team) != rotation["performed"][rep]
                                        for rep, team in zip(reps, teams)):
            raise ValueError("completed rotation did not use every declared Pokemon exactly once")
    return True
