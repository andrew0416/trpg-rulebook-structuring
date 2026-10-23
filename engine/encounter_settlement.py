"""One observed encounter result consumed by Pokemon XP and ordinary wagers.

The result owns who was rewarded, which owned Pokemon actually participated,
and who won.  XP calculation, per-Trainer allocation, and escrow payout remain
separate consumers of that one fact.
"""
from copy import deepcopy

import common_checks as C
import state_grants as GRANTS
import world_entities as WORLD


SOURCE = "input/ch11-running-the-game.md:1251-1271,1322"
KEY = "_campaign_reward_events"
PREFIX = "encounter-settlement:"
OUTCOME_PREFIX = "encounter-outcome:"
CLOSE_PREFIX = "encounter-close:"


def close_encounter(engine, actors):
    if not engine.encounter_active or engine._party_encounter_epoch < 1:
        return
    epoch = engine._party_encounter_epoch
    if not hasattr(engine, KEY):
        setattr(engine, KEY, {})
    getattr(engine, KEY)[CLOSE_PREFIX + str(epoch)] = {
        "kind": "encounter_close", "source": SOURCE, "encounter_epoch": epoch,
        "participant_ids": [actor.entity_id for actor in actors], "at": engine.elapsed_seconds}


def observe_outcome(engine, *, encounter_id, participants, winner, trainer_battle, reason):
    """Observe a real completed battle independently of XP eligibility."""
    _text(encounter_id, "encounter identity")
    _text(reason, "actual outcome observation reason")
    actors = tuple(participants)
    _actual(engine, *actors)
    if (engine.encounter_active or engine._active_turn_actor is not None or
            engine._party_encounter_epoch < 1):
        raise ValueError("outcome requires an actual completed encounter")
    if winner not in actors or type(trainer_battle) is not bool:
        raise ValueError("explicit participant winner and battle kind required")
    if trainer_battle and winner.kind != "trainer":
        raise ValueError("Trainer battle requires its actual winning Trainer")
    closed = _rows(engine).get(CLOSE_PREFIX + str(engine._party_encounter_epoch))
    if not closed or any(actor.entity_id not in closed["participant_ids"] for actor in actors):
        raise ValueError("outcome participant was not in the actual encounter")
    epoch = engine._party_encounter_epoch
    if any(key == OUTCOME_PREFIX + encounter_id or
           isinstance(row, dict) and row.get("kind") == "encounter_outcome" and row.get("encounter_epoch") == epoch
           for key, row in _rows(engine).items()):
        raise ValueError("encounter outcome already observed")

    def apply(staged, _primary, *subjects):
        row = {"id": encounter_id, "kind": "encounter_outcome", "source": SOURCE,
               "encounter_epoch": epoch, "participant_ids": [actor.entity_id for actor in subjects],
               "winner_id": winner.entity_id, "trainer_battle": trainer_battle,
               "reason": reason, "at": staged.elapsed_seconds}
        if not hasattr(staged, KEY):
            setattr(staged, KEY, {})
        getattr(staged, KEY)[OUTCOME_PREFIX + encounter_id] = row
        return deepcopy(row)

    return GRANTS.transition(engine, None, apply, participants=actors)


def outcome(engine, encounter_id):
    _text(encounter_id, "encounter identity")
    row = _rows(engine).get(OUTCOME_PREFIX + encounter_id)
    if not isinstance(row, dict) or row.get("kind") != "encounter_outcome" or row.get("source") != SOURCE:
        raise ValueError("actual observed encounter outcome required")
    return row


def validate_outcomes(engine, index):
    epochs = set()
    for key, row in _rows(engine).items():
        if not key.startswith(OUTCOME_PREFIX):
            continue
        required = {"id", "kind", "source", "encounter_epoch", "participant_ids", "winner_id", "trainer_battle", "reason", "at"}
        if not isinstance(row, dict) or set(row) != required or key != OUTCOME_PREFIX + row["id"]:
            raise ValueError("encounter outcome receipt shape changed")
        outcome(engine, row["id"])
        ids = row["participant_ids"]
        if (not isinstance(ids, list) or len(set(ids)) != len(ids) or not set(ids) <= set(index) or
                row["winner_id"] not in ids or type(row["trainer_battle"]) is not bool or
                row["trainer_battle"] and index[row["winner_id"]].kind != "trainer"):
            raise ValueError("encounter outcome participant graph changed")
        C.integer(row["encounter_epoch"], "outcome encounter", 1, engine._party_encounter_epoch)
        C.integer(row["at"], "outcome time", 0, engine.elapsed_seconds)
        closed = _rows(engine).get(CLOSE_PREFIX + str(row["encounter_epoch"]))
        if (not closed or closed.get("source") != SOURCE or closed.get("kind") != "encounter_close" or
                not set(ids) <= set(closed.get("participant_ids", ())) or closed["at"] > row["at"]):
            raise ValueError("outcome has no matching completed encounter")
        _text(row["reason"], "outcome reason")
        if row["encounter_epoch"] in epochs:
            raise ValueError("duplicate outcome for actual encounter")
        epochs.add(row["encounter_epoch"])


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " required")
    return value


def _actual(engine, *actors):
    index = WORLD.actor_index(engine, extra=actors)
    if any(index.get(actor.entity_id) is not actor for actor in actors):
        raise ValueError("actual registered encounter actors required")
    if len({actor.entity_id for actor in actors}) != len(actors):
        raise ValueError("distinct encounter actor identities required")
    return index


def _rows(engine):
    return getattr(engine, KEY, {})


def _event_key(encounter_id):
    return PREFIX + encounter_id


def observe(engine, *, encounter_id, rewarded_trainers, participating_pokemon,
            winner, defeated_levels, defeated_trainer_levels=(),
            significance=2.0, challenge=1.0, reason):
    """Commit a completed encounter's participants before any reward consumer.

    ``participating_pokemon`` maps each rewarded Trainer identity to the actual
    Pokemon that took part.  A fainted Pokemon is deliberately still eligible.
    """
    _text(encounter_id, "encounter identity")
    _text(reason, "actual completed encounter observation reason")
    trainers = tuple(rewarded_trainers)
    if not trainers or any(actor.kind != "trainer" for actor in trainers):
        raise ValueError("one or more actual rewarded Trainers required")
    if not isinstance(participating_pokemon, dict) or set(participating_pokemon) != {t.entity_id for t in trainers}:
        raise ValueError("each rewarded Trainer needs an explicit participant list")
    pokemon = []
    by_trainer = {}
    for trainer in trainers:
        values = tuple(participating_pokemon[trainer.entity_id])
        if not values or len({id(actor) for actor in values}) != len(values):
            raise ValueError("distinct actually participating Pokemon required for every rewarded Trainer")
        for actor in values:
            if actor.kind != "pokemon" or actor.spec.get("trainer_id") != trainer.entity_id:
                raise ValueError("participating Pokemon must be owned by its rewarded Trainer")
            if actor.captured or actor.dead:
                raise ValueError("captured or dead Pokemon cannot be declared an encounter participant")
        pokemon.extend(values)
        by_trainer[trainer.entity_id] = [actor.entity_id for actor in values]
    if len({id(actor) for actor in pokemon}) != len(pokemon):
        raise ValueError("one Pokemon cannot be credited to multiple Trainers")
    if winner not in trainers:
        raise ValueError("winner must be one of the actual rewarded Trainers")
    if engine.encounter_active or engine._active_turn_actor is not None:
        raise ValueError("encounter settlement requires a completed encounter and action")
    _actual(engine, *trainers, *pokemon)
    if _event_key(encounter_id) in _rows(engine):
        raise ValueError("encounter result identity already observed")
    import downtime as DOWNTIME
    share, detail = DOWNTIME.award_exp(
        engine.r, defeated_levels, len(trainers), significance, challenge,
        trainers_fought=defeated_trainer_levels)
    wager_ids = sorted(key for key, value in getattr(engine, "_campaign_reward_events", {}).items()
                       if isinstance(value, dict) and value.get("kind") == "wager" and value.get("status") == "escrowed")

    def apply(staged, _primary, *subjects):
        count = len(trainers)
        staged_trainers = subjects[:count]
        staged_pokemon = subjects[count:]
        trainer_ids = [actor.entity_id for actor in staged_trainers]
        pokemon_ids = {actor.entity_id for actor in staged_pokemon}
        if set().union(*(set(by_trainer[tid]) for tid in trainer_ids)) != pokemon_ids:
            raise ValueError("staged encounter participant graph changed")
        if not hasattr(staged, KEY):
            setattr(staged, KEY, {})
        row = {
            "id": encounter_id,
            "source": SOURCE,
            "reason": reason,
            "trainer_ids": trainer_ids,
            "participating_pokemon": deepcopy(by_trainer),
            "winner_id": winner.entity_id,
            "defeated_levels": list(defeated_levels),
            "defeated_trainer_levels": list(defeated_trainer_levels),
            "xp_share": share,
            "xp_detail": deepcopy(detail),
            "xp_allocations": {},
            "wager_ids_at_observation": wager_ids,
            "settled_wagers": [],
            "status": "observed",
        }
        getattr(staged, KEY)[_event_key(encounter_id)] = row
        staged.log("  encounter settlement observed: " + encounter_id, SOURCE)
        return deepcopy(row)

    return GRANTS.transition(engine, None, apply, participants=(*trainers, *pokemon))


def _row(engine, encounter_id):
    _text(encounter_id, "encounter identity")
    row = _rows(engine).get(_event_key(encounter_id))
    if not isinstance(row, dict) or row.get("source") != SOURCE:
        raise ValueError("actual observed encounter settlement required")
    return row


def allocate_pokemon_xp(engine, *, encounter_id, trainer, allocations):
    """Give one Trainer's whole share in any ratio to actual participants."""
    row = _row(engine, encounter_id)
    _actual(engine, trainer)
    if trainer.entity_id not in row["trainer_ids"]:
        raise ValueError("Trainer did not receive a share from this encounter")
    if trainer.entity_id in row["xp_allocations"]:
        raise ValueError("Trainer encounter share already allocated")
    if not isinstance(allocations, dict) or not allocations:
        raise ValueError("one or more Pokemon XP allocations required")
    eligible = set(row["participating_pokemon"][trainer.entity_id])
    if not set(allocations) <= eligible:
        raise ValueError("XP may be allocated only to this Trainer's actual participating Pokemon")
    for identity, amount in allocations.items():
        _text(identity, "participating Pokemon identity")
        C.integer(amount, "Pokemon XP allocation", 0)
    if sum(allocations.values()) != row["xp_share"]:
        raise ValueError("Pokemon allocations must consume exactly the Trainer's whole share")
    index = WORLD.actor_index(engine)
    targets = tuple(index[identity] for identity, amount in allocations.items() if amount)
    _actual(engine, trainer, *targets)

    def apply(staged, owner, *pokemon):
        current = _row(staged, encounter_id)
        staged_index = WORLD.actor_index(staged, extra=(owner, *pokemon))
        import downtime as DOWNTIME
        receipts = []
        for identity, amount in allocations.items():
            if not amount:
                continue
            actor = staged_index[identity]
            before = actor.spec.get("exp")
            result = DOWNTIME._gain_exp_combatant(staged, actor, amount)
            receipts.append({"pokemon_id": identity, "amount": amount,
                             "exp_before": before, "exp_after": actor.spec.get("exp"),
                             "growth": deepcopy(result)})
        current["xp_allocations"][owner.entity_id] = {
            "allocations": deepcopy(allocations), "receipts": receipts}
        return deepcopy(current["xp_allocations"][owner.entity_id])

    return GRANTS.transition(engine, trainer, apply, participants=targets)


def settle_wager(engine, *, encounter_id, wager_id, actor):
    """Pay both escrowed stakes to the observed ordinary-battle winner."""
    row = _row(engine, encounter_id)
    _text(wager_id, "wager event identity")
    if wager_id not in row["wager_ids_at_observation"]:
        raise ValueError("wager was not escrowed before this encounter result")
    import campaign_rewards as REWARDS
    wager = REWARDS.owned(engine, actor, wager_id, "wager")
    parties = tuple(wager["parties"])
    if wager["status"] != "escrowed" or set(p.entity_id for p in parties) != set(row["trainer_ids"]):
        raise ValueError("unconsumed wager parties must match the actual encounter Trainers")
    winner = next((party for party in parties if party.entity_id == row["winner_id"]), None)
    if winner is None:
        raise ValueError("actual encounter winner is not a wager party")
    _actual(engine, *parties)

    def apply(staged, owner, *others):
        current = _row(staged, encounter_id)
        actual = REWARDS.owned(staged, owner, wager_id, "wager")
        staged_parties = tuple(actual["parties"])
        staged_winner = next(p for p in staged_parties if p.entity_id == current["winner_id"])
        value = sum(actual["stakes"].values())
        REWARDS.balances(staged_winner)
        REWARDS.pay(staged_winner, money=value)
        actual.update(status="paid", encounter_id=encounter_id,
                      winner=staged_winner.entity_id, payout=value)
        current["settled_wagers"].append(wager_id)
        return {"status": "paid", "winner": staged_winner.entity_id, "payout": value}

    ordered = tuple(party for party in parties if party is not actor)
    return GRANTS.transition(engine, actor, apply, participants=ordered)

