"""Damage stages and scoped native HP-application facts."""
import arithmetic as A
import arithmetic_policy as M
from contextlib import contextmanager


@contextmanager
def native_hit(target):
    """Carry the actual HP leaf's facts through native actor transactions.

    Actor state graphs are copied and reconciled by those transactions. A
    scoped actor mapping follows that commit; a global reference would observe
    the original actor instead of the staged damage application.
    """
    missing = object()
    previous = getattr(target, '_native_damage_observation', missing)
    facts = {}
    target._native_damage_observation = facts
    try:
        yield facts
    finally:
        if previous is missing:
            del target._native_damage_observation
        else:
            target._native_damage_observation = previous


def observe_native_hit(target, *, amount, maximum_hp, massive):
    facts = getattr(target, '_native_damage_observation', None)
    if facts is not None and not facts:
        facts.update(amount_after_temporary_hp=amount, maximum_hp=maximum_hp, massive=massive)


def validate_native_hit(facts):
    if (not isinstance(facts, dict)
            or set(facts) != {'amount_after_temporary_hp', 'maximum_hp', 'massive'}
            or type(facts['amount_after_temporary_hp']) is not int
            or facts['amount_after_temporary_hp'] < 0
            or type(facts['maximum_hp']) is not int or facts['maximum_hp'] <= 0
            or type(facts['massive']) is not bool):
        raise ValueError('actual native damage boundary facts required')
    return facts


def defend(*, dice, attack, modifiers, defense, reduction, minimum=1):
    values = [A.exact(x) for x in (dice, attack, modifiers, defense, reduction, minimum)]
    if values[-1] < 0:
        raise ValueError("damage minimum must be nonnegative")
    dice, attack, modifiers, defense, reduction, minimum = values
    total = dice + attack + modifiers
    after_defense = max(minimum, total-defense-reduction)
    return {"total": int(total) if total.denominator == 1 else total,
            "after_defense": int(after_defense) if after_defense.denominator == 1 else after_defense}


def scale(*, after_defense, type_multiplier, other_multiplier=1, adjustment=0):
    base, typing, other, adjust = map(A.exact,
        (after_defense, type_multiplier, other_multiplier, adjustment))
    if min(base, typing, other) < 0:
        raise ValueError("damage base and multipliers must be nonnegative")
    if adjust.denominator != 1:
        raise ValueError("post-rounding damage adjustment must be integral")
    return max(0, M.product(base, typing, other) + int(adjust))


def observe(target):
    return {"hp": target.hp, "temporary_hp": target.temp_hp}


def application(*, requested, before, after, source, damage_class):
    if type(requested) is not int or requested < 0:
        raise ValueError("requested damage must be a nonnegative integer")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("actual damage source required")
    if damage_class not in ("물리", "특수"):
        raise ValueError("actual attack damage class required")
    for state in (before, after):
        if set(state) != {"hp", "temporary_hp"} or any(type(v) is not int for v in state.values()):
            raise ValueError("observed integral HP and temporary HP required")
        if state["temporary_hp"] < 0:
            raise ValueError("temporary HP cannot be negative")
    return {"source": source, "damage_class": damage_class, "requested": requested,
            "before": dict(before), "after": dict(after),
            "net_hp_loss": before["hp"]-after["hp"],
            "net_temporary_hp_loss": before["temporary_hp"]-after["temporary_hp"],
            "observation_boundary": "native_attack_application_including_its_hooks"}
