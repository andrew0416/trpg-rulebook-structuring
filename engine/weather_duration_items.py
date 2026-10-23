"""Equipped rocks that extend one newly created finite weather occurrence.

The weather occurrence owns the resulting deadline.  The item only contributes
at creation time, so later unequipping cannot shorten an already established
weather and another holder cannot lend its equipment to the producer.
"""
from copy import deepcopy

import resolution_transaction as TX


ADDED_ROUNDS = 2
ITEM_WEATHER = {
    "item/차가운바위": "hail",
    "item/보송보송바위": "sandstorm",
    "item/뜨거운바위": "sunny",
    "item/축축한바위": "rain",
}


def _fingerprint(row):
    return TX.request_fingerprint({key: value for key, value in row.items() if key != "fingerprint"})


def _equipped_sources(actor, weather):
    # Magic Room leaves the physical registration in place while suspending
    # every passive equipment contribution.  Weather rocks are creation-time
    # passive contributors, so a suspended registration must not extend a new
    # weather occurrence.
    import items as ITEMS

    rows = []
    for registration_key, record in getattr(actor, "_item_reg", {}).items():
        if not ITEMS.equipment_benefit_active(actor,record):
            continue
        item_id = record.get("item_id")
        if ITEM_WEATHER.get(item_id) != weather:
            continue
        # _item_reg contains only live registrations.  Preserve the concrete
        # registration and physical identity (when one exists) in the receipt.
        rows.append({
            "registration_key": registration_key,
            "item_id": item_id,
            "item_name": record.get("name"),
            "instance_id": record.get("instance_id"),
            "state_source": record.get("state_source"),
        })
    return sorted(rows, key=lambda row: (row["item_id"], row["instance_id"] or "", row["registration_key"]))


def extend(actor, weather, rounds, origin):
    """Return adjusted rounds and an immutable, non-stacking source receipt."""
    if origin != "move" or actor is None or rounds is None:
        return rounds, None
    if type(rounds) is not int or rounds <= 0:
        raise ValueError("weather item extension requires a positive finite base duration")
    sources = _equipped_sources(actor, weather)
    if not sources:
        return rounds, None
    row = {
        "version": 1,
        "actor_id": actor.entity_id,
        "weather": weather,
        "base_rounds": rounds,
        "added_rounds": ADDED_ROUNDS,
        "sources": sources,
        "stacking": "same_effect_once",
    }
    row["fingerprint"] = _fingerprint(row)
    return rounds + ADDED_ROUNDS, row


def validate(receipt, *, actor_id, weather, duration):
    if type(receipt) is not dict or set(receipt) != {
        "version", "actor_id", "weather", "base_rounds", "added_rounds",
        "sources", "stacking", "fingerprint",
    }:
        raise ValueError("invalid weather duration item receipt")
    if receipt["version"] != 1 or receipt["actor_id"] != actor_id or receipt["weather"] != weather:
        raise ValueError("weather duration item receipt is attached to another occurrence")
    if (type(receipt["base_rounds"]) is not int or receipt["base_rounds"] <= 0 or
            receipt["added_rounds"] != ADDED_ROUNDS or
            duration != receipt["base_rounds"] + ADDED_ROUNDS or
            receipt["stacking"] != "same_effect_once"):
        raise ValueError("weather duration item receipt changed its sourced duration")
    sources = receipt["sources"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("weather duration item receipt needs an equipped source")
    identities = set()
    for row in sources:
        if type(row) is not dict or set(row) != {
            "registration_key", "item_id", "item_name", "instance_id", "state_source",
        }:
            raise ValueError("invalid weather duration equipment source")
        if ITEM_WEATHER.get(row["item_id"]) != weather:
            raise ValueError("weather duration equipment does not match the created weather")
        if not isinstance(row["registration_key"], str) or not row["registration_key"]:
            raise ValueError("weather duration equipment needs a registration identity")
        if not isinstance(row["item_name"], str) or not row["item_name"]:
            raise ValueError("weather duration equipment needs its rule name")
        if row["instance_id"] is not None and (not isinstance(row["instance_id"], str) or not row["instance_id"]):
            raise ValueError("invalid weather duration item instance")
        if not isinstance(row["state_source"], str) or not row["state_source"]:
            raise ValueError("weather duration equipment needs its live state source")
        identity = row["instance_id"] or row["state_source"]
        if identity in identities:
            raise ValueError("duplicate weather duration equipment identity")
        identities.add(identity)
    if receipt["fingerprint"] != _fingerprint(receipt):
        raise ValueError("weather duration item receipt was modified")
    return deepcopy(receipt)
