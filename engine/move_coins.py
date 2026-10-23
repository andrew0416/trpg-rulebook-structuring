"""Coins from one completed Move, paid once to an observed encounter winner."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json

import common_checks as C
import roll_pools as POOLS

KEY = "move_coin_history"
MOVES = frozenset(("move/고양이돈받기", "move/골드러시"))
POLICY = "data/move-coin-policy.json"


def policy(rules):
    data = json.loads((Path(rules.root) / POLICY).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or set(data.get("moves", {})) != MOVES:
        raise ValueError("Move coin policy identity changed")
    for name, digest in data["source_files"].items():
        if hashlib.sha256((Path(rules.root) / name).read_bytes()).hexdigest() != digest:
            raise ValueError("reviewed Move coin source changed")
    return data["moves"]


def mechanics(rules, move_id, declaration):
    if move_id not in MOVES:
        return declaration
    row = policy(rules)[move_id]
    effects = [{k: v for k, v in effect.items() if k != "_src"}
               for effect in declaration.get("effects_exec", [])]
    if (effects != row["source_effects"] or
            rules.move(move_id)["effect"] != row["source_effect"]):
        raise ValueError("selected Move coin definition differs from reviewed source")
    # The generic GM text has no per-target execution. Its real producer is
    # observe_completion; the separate self-stage consequence uses dispatch.
    return dict(declaration, effects_exec=deepcopy(row["runtime_effects"]))


def records(actor):
    return actor.spec.get(KEY, [])


def preflight(engine, actor, move_id):
    if move_id not in MOVES:
        return
    import world_entities as WORLD
    WORLD.require_actors(engine, actor)
    if not engine.encounter_active:
        raise ValueError("coin scattering needs an actual encounter")
    validate_world(engine, WORLD.actor_index(engine))
    C.integer(actor.level, "coin-producing user level", 1)


def begin(engine, completion):
    if completion["move_id"] not in MOVES:
        return
    import frequency as FREQ
    actor = completion["actor"]
    completion["coin_basis"] = {"level": actor.level, "day": FREQ.state(actor)["day"],
        "encounter_epoch": engine._party_encounter_epoch}


def observe_completion(engine, completion):
    mid = completion["move_id"]
    if mid not in MOVES:
        return
    if (getattr(engine, "_move_completions", {}).get(completion["id"]) is not completion or
            completion["phase"] != "completion_effects" or not completion["sealed"] or
            set(completion["results"]) != {t.entity_id for t in completion["targets"]}):
        raise ValueError("coin scattering requires actual all-target completion")
    if all(result["cancelled"] for result in completion["results"].values()):
        return
    actor = completion["actor"]
    if any(row["completion_id"] == completion["id"] for row in records(actor)):
        return
    definition = policy(engine.r)[mid]
    basis = completion["coin_basis"]
    exhausted = definition["daily_once"] and any(
        row["move_id"] == mid and row["day"] == basis["day"] and row["face"] is not None
        for row in records(actor))
    face = None if exhausted else POOLS.die(engine.rng, 8)
    row = {"completion_id": completion["id"], "actor_id": actor.entity_id,
        "move_id": mid, "clause_id": definition["clause_id"],
        "source_row_sha256": definition["source_row_sha256"], **basis,
        "face": face, "amount": 0 if face is None else basis["level"] * face,
        "created_at": engine.elapsed_seconds, "payment": None}
    actor.spec.setdefault(KEY, []).append(row)
    engine.log("    동전 생성: %d%s" % (row["amount"], " (하루 생성 소진)" if exhausted else ""), mid)


def settle(engine, *, encounter_id):
    """Consume physical coin occurrences using the common observed outcome."""
    import encounter_settlement as SETTLEMENT
    import state_grants as GRANTS
    import world_entities as WORLD
    import campaign_rewards as REWARDS
    outcome = SETTLEMENT.outcome(engine, encounter_id)
    if engine.encounter_active or engine._active_turn_actor is not None:
        raise ValueError("coin collection requires completed encounter and action")
    index = WORLD.actor_index(engine)
    validate_world(engine, index)
    winner = index[outcome["winner_id"]]
    definitions = policy(engine.r)
    eligible = [(actor, row) for actor in index.values() for row in records(actor)
        if row["encounter_epoch"] == outcome["encounter_epoch"] and row["face"] is not None
        and row["payment"] is None and (outcome["trainer_battle"] or
                                        not definitions[row["move_id"]]["trainer_battle_only"])]
    if not eligible:
        raise ValueError("no uncollected coins eligible for this observed outcome")
    if any(actor.entity_id not in outcome["participant_ids"] for actor, _ in eligible):
        raise ValueError("coin producer missing from actual encounter participants")
    REWARDS.balances(winner)
    owners = tuple(dict.fromkeys(actor for actor, _ in eligible if actor is not winner))
    ids = {row["completion_id"] for _, row in eligible}

    def apply(staged, recipient, *participants):
        rows = [row for actor in (recipient, *participants) for row in records(actor)
                if row["completion_id"] in ids]
        amount = sum(row["amount"] for row in rows)
        before = recipient.spec.get("money", 0)
        REWARDS.pay(recipient, money=amount)
        payment = {"encounter_id": encounter_id, "winner_id": recipient.entity_id,
                   "amount": amount, "money_before": before, "money_after": recipient.spec["money"],
                   "completion_ids": sorted(ids)}
        for row in rows:
            row["payment"] = deepcopy(payment)
        return payment

    return GRANTS.transition(engine, winner, apply, participants=owners)


def validate_world(engine, index):
    import frequency as FREQ
    import encounter_settlement as SETTLEMENT
    SETTLEMENT.validate_outcomes(engine, index)
    completions = getattr(engine, "_move_completions", {})
    seen = set()
    for actor in index.values():
        rows = records(actor)
        if not isinstance(rows, list):
            raise ValueError("Move coin history must be a list")
        generated_days = set()
        for row in rows:
            required = {"completion_id", "actor_id", "move_id", "clause_id", "source_row_sha256",
                        "level", "day", "encounter_epoch", "face", "amount", "created_at", "payment"}
            if not isinstance(row, dict) or set(row) != required:
                raise ValueError("Move coin occurrence shape changed")
            definition = policy(engine.r).get(row["move_id"])
            completion = completions.get(row["completion_id"])
            if (definition is None or row["actor_id"] != actor.entity_id or row["completion_id"] in seen or
                    (row["clause_id"], row["source_row_sha256"]) !=
                    (definition["clause_id"], definition["source_row_sha256"]) or
                    not completion or completion["actor"] is not actor or
                    completion["move_id"] != row["move_id"] or completion["phase"] != "complete" or
                    all(result["cancelled"] for result in completion["results"].values())):
                raise ValueError("Move coins lack their actual completed source")
            seen.add(row["completion_id"])
            basis = {key: row[key] for key in ("level", "day", "encounter_epoch")}
            if completion.get("coin_basis") != basis:
                raise ValueError("coin generation inputs differ from actual activation")
            C.integer(row["level"], "coin level", 1)
            C.integer(row["day"], "coin day", 0, FREQ.state(actor)["day"])
            C.integer(row["encounter_epoch"], "coin encounter", 1, engine._party_encounter_epoch)
            C.integer(row["created_at"], "coin creation time", completion["seconds"], engine.elapsed_seconds)
            identity = (row["move_id"], row["day"])
            if row["face"] is None:
                if not definition["daily_once"] or identity not in generated_days or row["amount"] != 0 or row["payment"] is not None:
                    raise ValueError("coin exhaustion requires an earlier actual daily generation")
            else:
                C.integer(row["face"], "coin die face", 1, 8)
                if type(row["amount"]) is not int or row["amount"] != row["face"] * row["level"]:
                    raise ValueError("coin value differs from actual level and die")
                if definition["daily_once"] and identity in generated_days:
                    raise ValueError("duplicate daily Move coin generation")
                generated_days.add(identity)
            payment = row["payment"]
            if payment is not None:
                outcome = SETTLEMENT.outcome(engine, payment.get("encounter_id"))
                if (outcome["encounter_epoch"] != row["encounter_epoch"] or
                        outcome["winner_id"] != payment.get("winner_id") or
                        actor.entity_id not in outcome["participant_ids"] or
                        definition["trainer_battle_only"] and not outcome["trainer_battle"]):
                    raise ValueError("coin payment differs from observed encounter winner")
                if (row["completion_id"] not in payment.get("completion_ids", []) or
                        payment.get("money_after") != payment.get("money_before", 0) + payment.get("amount", 0)):
                    raise ValueError("coin payment receipt changed")
    # Cross-check each whole payout against all its consumed coin occurrences.
    all_rows = [row for actor in index.values() for row in records(actor)]
    for row in all_rows:
        payment = row["payment"]
        if payment is None:
            continue
        paid = [candidate for candidate in all_rows if candidate["payment"] == payment]
        if (sorted(candidate["completion_id"] for candidate in paid) != payment["completion_ids"] or
                sum(candidate["amount"] for candidate in paid) != payment["amount"]):
            raise ValueError("coin payout does not match consumed occurrences")
