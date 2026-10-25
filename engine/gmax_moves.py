"""Source-bound Gigantamax activation and its completed field consumers."""
import arithmetic_policy as NUMERIC
from copy import deepcopy
import json
import os
import hashlib
import roll_pools as POOLS

STATE = "gmax_state"
EFFECTS = "gmax_effects"
SOURCE = "data/gmax-move-policy.json"


def _policy(rules):
    cached = getattr(rules, "_gmax_move_policy", None)
    if cached is None:
        path = os.path.join(rules.root, SOURCE)
        with open(path, encoding="utf-8") as stream:
            cached = json.load(stream)
        if cached.get("schema") != "ptk.gmax-derived-moves.v1":
            raise ValueError("unsupported G-Max policy schema")
        rows = cached.get("moves")
        if not isinstance(rows, list) or len(rows) != 12:
            raise ValueError("G-Max policy must bind the exact twelve completed consumers")
        rules._gmax_move_policy = cached
    return cached


def _catalog(rules):
    policy = _policy(rules)
    moves_by_eng = {row.get("eng"): row for row in rules.moves.values()}
    species_by_eng = {row.get("eng"): row for row in rules.species.values()}
    result = {}
    for declaration in policy["moves"]:
        move = moves_by_eng.get(declaration["move_eng"])
        species = species_by_eng.get(declaration["species_eng"])
        if move is None or species is None:
            raise ValueError("selected G-Max move/species source is unavailable")
        if move.get("_source", {}).get("record_span") != [declaration["record"], declaration["record"]]:
            raise ValueError("G-Max record identity changed")
        if not {"강타", "정신급증"}.issubset(move.get("keywords", ())):
            raise ValueError("selected G-Max Smite/Spirit Surge source keywords changed")
        result[move["id"]] = dict(declaration, move_id=move["id"], species_id=species["id"])
    return result


def declarations(rules):
    return deepcopy(list(_catalog(rules).values()))


def is_gmax_move(rules, move_id):
    return move_id in _catalog(rules)


def prepare_mechanics(rules, move_id, mechanics):
    """Remove heuristic per-target projections owned by the native G-Max payload."""
    if move_id not in _catalog(rules):
        return mechanics
    result = deepcopy(mechanics)
    declaration = _catalog(rules)[move_id]
    if declaration["effect"] in ("area_hazard", "gravity"):
        for name, digest in _policy(rules)["source_files"].items():
            with open(os.path.join(rules.root, name), "rb") as stream:
                if hashlib.sha256(stream.read()).hexdigest() != digest:
                    raise ValueError("reviewed G-Max field source changed")
    if declaration["effect"] == "gravity":
        if result or rules.move(move_id)["effect"] != declaration["source_effect"]:
            raise ValueError("G-Max Gravity source differs from reviewed declaration")
    if declaration["effect"] == "area_hazard":
        import hazard_state as HAZARDS
        row = HAZARDS._definition(rules, move_id)
        if result != row["source_mechanics"] or rules.move(move_id)["effect"] != row["source_effect"]:
            raise ValueError("derived Hazard source differs from reviewed declaration")
        result.pop("hazard_terrain", None)
    for key in ("status", "tick_hp"):
        result.pop(key, None)
    result["_gmax_payload_owned"] = True
    return result


def _actor_index(engine):
    import world_entities
    return world_entities.actor_index(engine)


def _actual_species(rules, actor):
    from builder import species_lookup
    if actor.kind != "pokemon" or not actor.spec.get("species"):
        raise ValueError("Gigantamax requires an actual Pokemon species")
    return species_lookup(rules, actor.spec["species"])


def _validate_receipt(engine, actor):
    receipt = actor.spec.get(STATE)
    if not isinstance(receipt, dict) or receipt.get("source") != SOURCE or receipt.get("active") is not True:
        raise ValueError("an active source-bound Gigantamax receipt is required")
    species = _actual_species(engine.r, actor)
    if receipt.get("actor_id") != actor.entity_id or receipt.get("species_id") != species["id"]:
        raise ValueError("Gigantamax receipt species identity changed")
    if receipt.get("encounter_epoch") != getattr(engine, "_party_encounter_epoch", 0):
        raise ValueError("Gigantamax receipt belongs to another encounter")
    if actor.form != receipt.get("form_id"):
        raise ValueError("current form disagrees with the Gigantamax receipt")
    if receipt.get('producer_source')=='item/다이버섯':
        event=getattr(engine,'_csv_food_form_event',None)
        in_entry=isinstance(event,dict) and event.get('actor') is actor and event.get('receipt') is receipt
        if not in_entry:
            food=receipt.get('food_consumption')
            matches=[r for r in actor.spec.get('food_consumption_receipts',[])
                if isinstance(food,dict) and r.get('buff_id')==food.get('buff_id') and r.get('sequence')==food.get('sequence')]
            if len(matches)!=1 or matches[0].get('producer')!='designated_dynamax_form' or matches[0].get('item')!='item/다이버섯':raise ValueError('Gigantamax lacks its actual designated Mushroom consumption')
            import food_effects as FOOD
            FOOD.validate_native(actor,matches[0],spent=True)
            benefit=matches[0].get('benefit',{})
            if benefit!={'form_source':'gigantamax','form_id':receipt['form_id'],'encounter_epoch':receipt['encounter_epoch']}:raise ValueError('Mushroom consumption belongs to another native form entry')
    return receipt


def enter(engine, actor, *, source_id, reason):
    """Produce a real encounter receipt; a raw form string grants no authority."""
    if not engine.encounter_active or actor.kind != "pokemon" or actor.fainted or not actor.on_field:
        raise ValueError("a conscious on-field Pokemon in an encounter is required")
    if not isinstance(source_id, str) or not source_id.strip() or not isinstance(reason, str) or not reason.strip():
        raise ValueError("explicit Gigantamax source and reason are required")
    species = _actual_species(engine.r, actor)
    eligible = [row for row in _catalog(engine.r).values() if row["species_id"] == species["id"]]
    if not eligible:
        raise ValueError("this exact species has no implemented Gigantamax move")
    if STATE in actor.spec:
        raise ValueError("Pokemon already has Gigantamax state")
    import csv_item_food_contracts as CSV
    food_buff_id = CSV.form_preflight(engine,actor,source_id)
    band = None
    if source_id == 'item/다이맥스벤드':
        import csv_item_physical_contracts as PHYSICAL
        owner = _actor_index(engine).get(actor.spec.get('trainer_id'))
        if owner is None or owner.kind != 'trainer' or not PHYSICAL.dynamax_authorized(engine, owner):
            raise ValueError('Dynamax Band requires the actual controller wearing its live accessory')
        active = PHYSICAL._active(engine, owner, 'dynamax_band')[0]
        band = {'owner_id': owner.entity_id, 'instance_id': active[2]['instance_id'], 'clause_id': active[1]['clause_id']}
    previous = getattr(actor, "form", None)
    form_id = "gmax:" + species["id"]
    actor.form = form_id
    actor.spec[STATE] = {
        "source": SOURCE, "producer_source": source_id, "reason": reason,
        "actor_id": actor.entity_id, "species_id": species["id"],
        "form_id": form_id, "previous_form": previous, "active": True,
        "encounter_epoch": getattr(engine, "_party_encounter_epoch", 0),
        "entered_round": engine.round_no, "entered_at": engine.elapsed_seconds,
    }
    if food_buff_id is not None:
        actor.spec[STATE]['food_consumption'] = CSV._form_entered(engine,actor,food_buff_id,actor.spec[STATE])
    if band is not None:
        actor.spec[STATE]['band_authorization'] = band
    engine.log("    %s: Gigantamax form entered" % actor.name, SOURCE)
    return deepcopy(actor.spec[STATE])


def exit(engine, actor, *, reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Gigantamax exit reason is required")
    receipt = _validate_receipt(engine, actor)
    actor.form = receipt.get("previous_form")
    actor.spec.pop(STATE, None)
    engine.log("    %s: Gigantamax form ended (%s)" % (actor.name, reason), SOURCE)
    return True


def _known_base_move(rules, actor, base_move_id):
    import move_state
    move = rules.move(base_move_id)
    if base_move_id not in move_state.owned_list(actor.spec, "moves", actor.moves):
        raise ValueError("G-Max derivation requires an actually learned base Move")
    if move.get("class") not in ("물리", "특수", "Physical", "Special"):
        raise ValueError("G-Max base Move must have a physical or special class")
    return move


def plan(engine, actor, base_move_id, gmax_move_id):
    declaration = _catalog(engine.r).get(gmax_move_id)
    if declaration is None:
        raise ValueError("selected Move is not in the implemented G-Max package")
    receipt = _validate_receipt(engine, actor)
    if receipt["species_id"] != declaration["species_id"]:
        raise ValueError("G-Max Move requires its exact species form")
    base = _known_base_move(engine.r, actor, base_move_id)
    derived = engine.r.move(gmax_move_id)
    if base.get("type") != derived.get("type"):
        raise ValueError("learned base Move type must match the derived G-Max Move")
    return {"source": SOURCE, "actor_id": actor.entity_id, "base_move_id": base_move_id,
            "gmax_move_id": gmax_move_id, "class": base["class"],
            "clause_id": declaration["clause_id"], "effect": declaration["effect"]}


def _scopes(engine):
    scopes = getattr(engine, "_gmax_activation_scopes", None)
    if scopes is None:
        engine._gmax_activation_scopes = scopes = []
    return scopes


def prepare_native_move(engine, actor, move):
    declaration = _catalog(engine.r).get(move.get("id"))
    if declaration is None:
        return move
    scopes = _scopes(engine)
    matches = [row for row in scopes if row["actor_id"] == actor.entity_id and row["gmax_move_id"] == move["id"]]
    if len(matches) != 1:
        raise ValueError("direct G-Max use is forbidden; use the derived activation producer")
    current = plan(engine, actor, matches[0]["base_move_id"], move["id"])
    if current != matches[0]:
        raise ValueError("G-Max activation inputs changed after preflight")
    return dict(move, **{"class": current["class"], "_gmax_clause_id": current["clause_id"],
                        "_gmax_base_move_id": current["base_move_id"]})


def _members(engine, actor, *, allies):
    if actor.side is None:
        raise ValueError("G-Max side scope requires an actual side")
    return [row for row in engine.time_actors() if row.on_field and not row.captured and
            ((row.side == actor.side) if allies else (row.side is not None and row.side != actor.side))]


def activate(engine, actor, primary, base_move_id, gmax_move_id, everyone, **options):
    """Atomically execute the native Move and its all-target payload."""
    import state_grants as GRANTS
    # Stage every registered actor, including field recipients and coin owners
    # omitted from the native caller's local view.
    supplied = list(everyone) + [actor, primary]
    members = list({row.entity_id: row for row in engine.time_actors(supplied)}.values())
    participants = tuple(row for row in members if row is not actor)
    member_ids = [row.entity_id for row in members]
    primary_id = primary.entity_id
    def apply(staged, staged_actor, *staged_participants):
        index = {row.entity_id: row for row in (staged_actor, *staged_participants)}
        return _activate(staged, staged_actor, index[primary_id], base_move_id,
                         gmax_move_id, [index[uid] for uid in member_ids], options)
    return GRANTS.transition(engine, actor, apply, participants=participants,
                             include_grid=engine.grid is not None)


def _completed_move(engine, actor, move_id, before):
    rows = getattr(engine, "_move_completions", {})
    created = [row for token, row in rows.items() if token not in before and
               row.get("actor") is actor and row.get("move_id") == move_id]
    if len(created) != 1:
        raise ValueError("G-Max payload requires one native move-completion receipt")
    receipt = created[0]
    if (receipt.get("phase") != "complete" or not receipt.get("sealed") or
            set(receipt.get("results", {})) != {target.entity_id for target in receipt["targets"]}):
        raise ValueError("G-Max native activation did not complete")
    return receipt


def _activate(engine, actor, primary, base_move_id, gmax_move_id, everyone, options):
    activation = plan(engine, actor, base_move_id, gmax_move_id)
    payload = payload_plan(engine, actor, activation, primary, everyone, options)
    if payload["kind"] == "area_hazard":
        import area_targets as AREA
        if options.get("aim") is None:
            raise ValueError("derived Hazard requires explicit attack area aim before cost")
        AREA.cells(engine, actor, AREA.bind(engine, actor, engine.r.move(gmax_move_id), options["aim"]))
        import hazard_state as HAZARDS
        HAZARDS.validate_world(engine)
    before = set(getattr(engine, "_move_completions", {}))
    scopes = _scopes(engine)
    scopes.append(activation)
    try:
        result = engine.use_move_on(actor, primary, gmax_move_id, everyone, **options)
    finally:
        if activation in scopes:
            scopes.remove(activation)
    # A native pre-activation ruling is not a completed attack or its payload.
    from common_checks import PendingDecision
    if isinstance(result, PendingDecision):
        return result
    receipt = _completed_move(engine, actor, gmax_move_id, before)
    # All twelve selected rows print Spirit Surge. Cancellation is not a miss.
    if any(not outcome.get("cancelled") for outcome in receipt["results"].values()):
        apply_payload(engine, actor, activation, payload, receipt["id"])
    return result


def _new_effect(engine, actor, target, activation, kind, **values):
    sequence = getattr(engine, "_gmax_effect_sequence", 0) + 1
    engine._gmax_effect_sequence = sequence
    row = {"id": "gmax:%d" % sequence, "source": SOURCE, "clause_id": activation["clause_id"],
           "move_id": activation["gmax_move_id"], "owner_id": actor.entity_id,
           "target_id": target.entity_id, "kind": kind, "created_round": engine.round_no}
    row.update(values)
    target.spec.setdefault(EFFECTS, []).append(row)
    return row


def _apply_status(engine, target, status, activation, actor, *, parameters=None):
    engine.apply_status(target, status, source=activation["gmax_move_id"],
                        parameters=parameters, applied_by=actor)


def payload_plan(engine, actor, activation, primary, everyone, options):
    declaration = _catalog(engine.r)[activation["gmax_move_id"]]
    foes = _members(engine, actor, allies=False)
    kind = declaration["effect"]
    if kind == "confuse_and_coins":
        import area_targets as AREA
        move = AREA.bind(engine, actor, engine.r.move(activation["gmax_move_id"]), options.get("aim"))
        selected = engine.targets_in_range(actor, move, everyone, primary)
        foes = [target for target in selected if target.side is not None and target.side != actor.side]
    # Preflight the complete target set before the native Move can spend its
    # action/frequency or any payload consumer can mutate an earlier target.
    for target in foes:
        if target.dead or target.captured:
            raise ValueError("G-Max all-target payload requires live field participants")
    if kind == "disable_and_suppress_last_move":
        # A foe without a last Move is unaffected; identities that exist must
        # still resolve through the selected rules before any target mutates.
        for target in foes:
            if target.last_move is not None:
                engine.r.move(target.last_move)
    payload = {"kind": kind, "foes": foes}
    if kind == "confuse_and_coins":
        import campaign_rewards as REWARDS
        import common_checks as CHECKS
        CHECKS.integer(actor.level, "G-Max coin-producing level", 1)
        index = _actor_index(engine)
        trainer_id = actor.spec.get("trainer_id")
        recipient = index.get(trainer_id) if trainer_id is not None else actor
        if (recipient is None or recipient.side != actor.side or
                trainer_id is not None and recipient.kind != "trainer"):
            raise ValueError("G-Max coins require the actual user-side recipient")
        REWARDS.balances(recipient)
        payload.update(recipient_id=recipient.entity_id, level=actor.level,
                       encounter_epoch=engine._party_encounter_epoch)
    return payload


def _payload_foes(actor, payload, completion):
    import move_completion as COMPLETE
    recipients = COMPLETE.actual_recipients(completion)
    outcomes = {target.entity_id: COMPLETE.recipient_result(completion, target)
                for target in recipients}
    foes = (recipients if payload["kind"] == "confuse_and_coins" else payload["foes"])
    # Smite excludes the secondary effect only for its actual damaged recipient;
    # Spirit Surge still reaches other field foes, including those outside the blast.
    return [target for target in foes if target.side is not None and target.side != actor.side
            and not ((outcome := outcomes.get(target.entity_id)) is not None and
                     (outcome.get("cancelled") or not outcome.get("hit") and outcome.get("dealt", 0) > 0))]


def apply_payload(engine, actor, activation, payload, completion_id):
    declaration = _catalog(engine.r)[activation["gmax_move_id"]]
    completion = getattr(engine, "_move_completions", {}).get(completion_id)
    if (not completion or completion.get("actor") is not actor or
            completion.get("move_id") != activation["gmax_move_id"] or
            completion.get("phase") != "complete" or not completion.get("sealed") or
            not completion["move"].get("_gmax_base_move_id") or
            not any(not row.get("cancelled") for row in completion["results"].values())):
        raise ValueError("G-Max payload requires its actual noncancelled native completion")
    if any(row["completion_id"] == completion_id for row in engine._gmax_payload_receipts):
        raise ValueError("G-Max completion payload already applied")
    foes = _payload_foes(actor, payload, completion)
    kind = payload["kind"]
    if kind == "gravity":
        import field_effects as FIELD
        row = FIELD.policy(engine.r)["moves"][activation["gmax_move_id"]]
        FIELD.install(engine, actor, {"type":"field_effect", "field":row["field"],
            "rounds":row["rounds"], "effect":row["effect"]}, activation["gmax_move_id"])
    elif kind == "area_hazard":
        import hazard_state as HAZARDS
        HAZARDS.install_from_completion(engine, actor, activation["gmax_move_id"], completion_id)
    elif kind == "typed_residual":
        attack_type = engine.r.move(activation["gmax_move_id"])["type"]
        for target in foes:
            if attack_type not in target.types:
                _new_effect(engine, actor, target, activation, kind, turns=declaration["turns"], type=attack_type)
    elif kind == "sandblast":
        import combat_timing as TIMING
        for target in foes:
            row = _new_effect(engine, actor, target, activation, kind, turns=declaration["turns"])
            # Reuse timed status ownership: a pre-existing or later independent
            # Trapped source must survive expiry of this G-Max occurrence.
            TIMING.install(engine, target, {"source": activation["gmax_move_id"],
                "gmax_parent_id": row["id"], "statuses": ["수렁"], "manual_end": True})
    elif kind == "confuse_and_coins":
        for target in foes:
            _apply_status(engine, target, "혼란", activation, actor)
        rolls = POOLS.pool(engine.rng, declaration["dice"], sides=8)["faces"]
        event = {"source": SOURCE, "clause_id": activation["clause_id"], "owner_side": actor.side,
                 "owner_id": actor.entity_id, "completion_id": completion_id,
                 "recipient_id": payload["recipient_id"], "level": payload["level"],
                 "encounter_epoch": payload["encounter_epoch"], "rolls": rolls,
                 "amount": payload["level"] * sum(rolls), "payment": None,
                 "status": "pending_encounter_end"}
        completion["gmax_coin_basis"] = {key: event[key] for key in
            ("owner_id", "owner_side", "recipient_id", "level", "encounter_epoch")}
        engine._gmax_coin_rewards = getattr(engine, "_gmax_coin_rewards", []) + [event]
    elif kind == "bind":
        for target in foes:
            _new_effect(engine, actor, target, activation, kind, persists_if_owner_leaves=True)
            _apply_status(engine, target, "조이기", activation, actor)
    elif kind == "delayed_sleep":
        for target in foes:
            face = POOLS.die(engine.rng, declaration["die"])
            _new_effect(engine, actor, target, activation, kind, face=face, pending=face in declaration["success"])
    elif kind == "disable_and_suppress_last_move":
        for target in foes:
            if target.last_move:
                suppressed = not bool(engine.immune_to(target, "억압"))
                _new_effect(engine, actor, target, activation, kind,
                            disabled_move_id=target.last_move, suppressed=suppressed)
                _apply_status(engine, target, "사슬묶기", activation, actor,
                              parameters={"move_id": target.last_move})
                if suppressed:
                    target.conditions.add("억압")
                    engine.log("    %s: encounter-long G-Max Suppressed" % target.name,
                               activation["gmax_move_id"])
    else:
        raise ValueError("unsupported G-Max payload")
    engine._gmax_payload_receipts.append({"source": SOURCE, "clause_id": activation["clause_id"],
        "completion_id": completion_id, "actor_id": actor.entity_id,
        "target_ids": [row.entity_id for row in foes], "round": engine.round_no})
    return {"clause_id": activation["clause_id"], "targets": [row.entity_id for row in foes]}


def start_turn(engine, actor):
    effects = actor.spec.get(EFFECTS, [])
    if not isinstance(effects, list) or any(not isinstance(row, dict) for row in effects):
        raise ValueError("typed G-Max effect state required")
    keep = []
    for row in effects:
        kind = row.get("kind")
        if kind in ("typed_residual", "sandblast"):
            if kind == "sandblast":
                serial = actor.custom_conditions.get("combat_turn_serial", 0)
                if type(serial) is not int or serial < 1:
                    raise ValueError("Sandblast requires an actual target turn")
                if row["turns"] == 0:
                    keep.append(row)
                    continue
            damage = NUMERIC.ratio(actor.base_max_hp,6)
            if damage:
                engine.lose_hp(actor, damage, source=row["move_id"], unpreventable=True)
            row["turns"] -= 1
            if row["turns"] > 0:
                keep.append(row)
            elif kind == "sandblast":
                # The fourth tick starts the fourth protected target turn.
                # Keep its existing manual status owner until that real EOT.
                row["expires_after_target_turn"] = serial
                keep.append(row)
        elif kind == "delayed_sleep":
            if row.get("pending"):
                engine.apply_status(actor, "잠듦", source=row["move_id"])
            # Whether it proc'd or not, the single observation is consumed.
        elif kind == "bind":
            # G-Max Centiferno uses the ordinary Vortex consumer and ordinary
            # escape/cure lifetime; it explicitly persists if its user leaves.
            if "조이기" in actor.conditions:
                keep.append(row)
        elif kind == "disable_and_suppress_last_move":
            keep.append(row)
        else:
            raise ValueError("unknown saved G-Max effect")
    if keep:
        actor.spec[EFFECTS] = keep
    else:
        actor.spec.pop(EFFECTS, None)


def end_turn(engine, actor):
    """End Sandblast after the real target turn that delivered its fourth tick."""
    effects = actor.spec.get(EFFECTS, [])
    keep = []
    for row in effects:
        if row.get("kind") == "sandblast" and row.get("turns") == 0:
            if row.get("expires_after_target_turn") != actor.custom_conditions.get("combat_turn_serial"):
                raise ValueError("Sandblast expiry must match the actual closing target turn")
            _end_sandblast(engine, actor, row)
        else:
            keep.append(row)
    if keep:
        actor.spec[EFFECTS] = keep
    else:
        actor.spec.pop(EFFECTS, None)


def _end_sandblast(engine, actor, row):
    import combat_timing as TIMING
    import vortex_state as VORTEX
    for timed in list(TIMING.records(actor)):
        if timed.get("gmax_parent_id") == row["id"]:
            vortex = actor.custom_conditions.get(VORTEX.KEY)
            if "수렁" in timed.get("owned_statuses", ()) and "조이기" in actor.conditions and vortex:
                # A later Vortex could not install its already-present child.
                # Transfer that child to its surviving ordinary condition owner.
                timed["owned_statuses"].discard("수렁")
                vortex["owned"].add("수렁")
            TIMING.expire(engine, actor, timed)


def move_allowed(engine, actor, move):
    """Encounter-long Suppressed; Disabled uses its ordinary condition owner."""
    for row in actor.spec.get(EFFECTS, []):
        if row.get("kind") != "disable_and_suppress_last_move":
            continue
        import frequency as FREQ
        if row.get("suppressed") and FREQ.move_frequency(engine, move["id"], actor)[0] != "at_will":
            return False, "G-Max Depletion suppresses non-At-Will Moves for the encounter"
    return True, ""


def encounter_suppressed(actor):
    return any(row.get("kind") == "disable_and_suppress_last_move" and row.get("suppressed")
               for row in actor.spec.get(EFFECTS, []))


def retain_condition(engine, actor, condition):
    return condition == "억압" and engine.encounter_active and encounter_suppressed(actor)


def end_encounter(engine, actors):
    if getattr(engine, "_gmax_coin_rewards", []):
        validate_world(engine)
    for actor in actors:
        receipt = actor.spec.get(STATE)
        if isinstance(receipt, dict) and receipt.get("source") == SOURCE:
            actor.form = receipt.get("previous_form")
            actor.spec.pop(STATE, None)
        effects = actor.spec.pop(EFFECTS, [])
        for effect in effects:
            if effect.get("kind") == "sandblast":
                _end_sandblast(engine, actor, effect)
        if (any(row.get("kind") == "disable_and_suppress_last_move" and row.get("suppressed")
                for row in effects)):
            import condition_instances as CONDITIONS
            if not CONDITIONS.records(actor, "억압"):
                actor.conditions.discard("억압")
    rewards = getattr(engine, "_gmax_coin_rewards", [])
    index = _actor_index(engine)
    import campaign_rewards as REWARDS
    for reward in rewards:
        if reward.get("status") == "pending_encounter_end":
            recipient = index.get(reward.get("recipient_id"))
            if recipient is None or reward.get("encounter_epoch") != engine._party_encounter_epoch:
                raise ValueError("G-Max coin recipient or encounter changed")
            REWARDS.balances(recipient)
    for reward in rewards:
        if reward.get("status") == "pending_encounter_end":
            recipient = index[reward["recipient_id"]]
            before = recipient.spec.get("money", 0)
            REWARDS.pay(recipient, money=reward["amount"])
            reward["payment"] = {"recipient_id": recipient.entity_id,
                "completion_id": reward["completion_id"], "encounter_epoch": reward["encounter_epoch"],
                "amount": reward["amount"], "money_before": before, "money_after": recipient.spec["money"]}
            reward["status"] = "collected"
    engine._gmax_activation_scopes = []


def validate_world(engine):
    index = _actor_index(engine)
    for actor in index.values():
        if STATE in actor.spec:
            _validate_receipt(engine, actor)
        effects = actor.spec.get(EFFECTS, [])
        if not isinstance(effects, list):
            raise ValueError("G-Max effects must be a list")
        for row in effects:
            if not isinstance(row, dict) or row.get("source") != SOURCE or row.get("target_id") != actor.entity_id:
                raise ValueError("invalid G-Max effect receipt")
            if row.get("owner_id") not in index:
                raise ValueError("G-Max effect owner is missing")
    receipts = getattr(engine, "_gmax_payload_receipts", [])
    if not isinstance(receipts, list) or any(not isinstance(row, dict) or row.get("source") != SOURCE
                                             or row.get("actor_id") not in index for row in receipts):
        raise ValueError("invalid G-Max payload receipt ledger")
    completions = getattr(engine, "_move_completions", {})
    declarations_by_clause = {row["clause_id"]: row for row in _catalog(engine.r).values()}
    payload_ids = set()
    for row in receipts:
        completion = completions.get(row.get("completion_id"))
        declaration = declarations_by_clause.get(row.get("clause_id"))
        if (declaration is None or not completion or completion.get("phase") != "complete" or
                completion.get("move_id") != declaration["move_id"] or
                completion.get("actor").entity_id != row["actor_id"] or row.get("completion_id") in payload_ids or
                not completion.get("sealed") or
                not completion.get("move", {}).get("_gmax_base_move_id") or
                not any(not result.get("cancelled")
                        for result in completion.get("results", {}).values())):
            raise ValueError("G-Max payload lacks its completed noncancelled native Move receipt")
        payload_ids.add(row["completion_id"])
        if not isinstance(row.get("target_ids"), list) or any(uid not in index for uid in row["target_ids"]):
            raise ValueError("G-Max payload target identity is missing")
    rewards = getattr(engine, "_gmax_coin_rewards", [])
    if not isinstance(rewards, list):
        raise ValueError("G-Max coin rewards must be a list")
    seen = set()
    for row in rewards:
        if (not isinstance(row, dict) or row.get("source") != SOURCE or row.get("owner_id") not in index or
                row.get("status") not in ("pending_encounter_end", "collected") or
                not isinstance(row.get("rolls"), list) or len(row["rolls"]) != 10 or
                any(type(face) is not int or not 1 <= face <= 8 for face in row["rolls"]) or
                type(row.get("level")) is not int or row["level"] < 1 or
                type(row.get("amount")) is not int or row["amount"] != row["level"] * sum(row["rolls"]) or
                row.get("recipient_id") not in index or not row.get("owner_side") or
                type(row.get("encounter_epoch")) is not int or
                not 1 <= row["encounter_epoch"] <= engine._party_encounter_epoch or
                row.get("completion_id") in seen):
            raise ValueError("invalid G-Max Gold Rush reward receipt")
        seen.add(row.get("completion_id"))
        completion = completions.get(row.get("completion_id"))
        declaration = declarations_by_clause.get(row.get("clause_id"))
        if (not completion or declaration is None or declaration["effect"] != "confuse_and_coins" or
                completion["move_id"] != declaration["move_id"] or
                completion["actor"].entity_id != row["owner_id"] or
                not any(receipt["completion_id"] == row["completion_id"] and
                        receipt["clause_id"] == row["clause_id"] for receipt in receipts)):
            raise ValueError("G-Max coins lack their actual payload completion")
        if completion.get("gmax_coin_basis") != {key: row[key] for key in
                ("owner_id", "owner_side", "recipient_id", "level", "encounter_epoch")}:
            raise ValueError("G-Max coin generation inputs changed after activation")
        payment = row.get("payment")
        if row["status"] == "pending_encounter_end":
            if payment is not None:
                raise ValueError("uncollected G-Max coins cannot already have a payment")
        elif (not isinstance(payment, dict) or
                any(payment.get(key) != row[key] for key in
                    ("recipient_id", "completion_id", "encounter_epoch", "amount")) or
                type(payment.get("money_before")) is not int or payment["money_before"] < 0 or
                payment.get("money_after") != payment["money_before"] + row["amount"]):
            raise ValueError("G-Max coins lack their exact native payment receipt")
    if getattr(engine, "_gmax_activation_scopes", []):
        raise ValueError("cannot validate or save during a G-Max activation")
    return True


def validate_actor(actor):
    effects = actor.spec.get(EFFECTS, [])
    if not isinstance(effects, list):
        raise ValueError("G-Max effects must be a list")
    allowed = {"typed_residual", "sandblast", "bind", "delayed_sleep",
               "disable_and_suppress_last_move"}
    for row in effects:
        if not isinstance(row, dict) or row.get("source") != SOURCE or row.get("kind") not in allowed:
            raise ValueError("unsupported G-Max actor effect receipt")
        if row.get("target_id") != actor.entity_id:
            raise ValueError("G-Max effect target identity changed")
        if row["kind"] in ("typed_residual", "sandblast"):
            minimum = 0 if row["kind"] == "sandblast" else 1
            if type(row.get("turns")) is not int or not minimum <= row["turns"] <= 4:
                raise ValueError("G-Max residual turn count is invalid")
            final = row.get("expires_after_target_turn")
            if row["kind"] == "sandblast" and row["turns"] == 0:
                if (type(final) is not int or final < 1
                        or final != actor.custom_conditions.get("combat_turn_serial")):
                    raise ValueError("Sandblast needs its actual fourth target turn end")
            elif final is not None:
                raise ValueError("only the final Sandblast turn has a pending turn end")
        if row["kind"] == "bind" and row.get("persists_if_owner_leaves") is not True:
            raise ValueError("G-Max bind must preserve its printed owner-leaves exception")
        if row["kind"] == "disable_and_suppress_last_move":
            if actor.r.move(row.get("disabled_move_id"))["id"] != row["disabled_move_id"]:
                raise ValueError("G-Max depletion requires a selected disabled Move")
            if type(row.get("suppressed")) is not bool:
                raise ValueError("G-Max depletion needs an explicit Suppressed outcome")
            if row["suppressed"] and "억압" not in actor.conditions:
                raise ValueError("G-Max encounter Suppressed projection disagrees with its receipt")
    return True
