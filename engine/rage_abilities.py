"""Native dynamic contract for the two exact Rage-dependent abilities.

The ability receipt remains owned by ``state_grants``. This module validates
the selected source definitions and answers pure questions for the condition
save and damage consumers; it owns no duplicate actor state.
"""
import ability_transitions as ABILITIES


ENDURING_RAGE = "ability/불굴의격노"
WHITE_FLAME = "ability/화이트플레임"
SOURCES = (ENDURING_RAGE, WHITE_FLAME)

DEFINITIONS = {
    ENDURING_RAGE: {
        "name": "불굴의격노",
        "effects": [
            {"type": "rule", "no_rage_save": True},
            {"type": "damage_reduction", "value": 5, "while_status": "난동"},
        ],
    },
    WHITE_FLAME: {
        "name": "화이트플레임",
        "effects": [
            {"type": "rule", "no_rage_save": True},
            {"type": "bonus_damage", "value": 5, "while_status": "난동"},
        ],
    },
}


def registration(rules, source):
    """Claim only an exact selected source with the reviewed native shape."""
    if source not in DEFINITIONS:
        return False
    if rules._selected_rule(source) != source:
        raise ValueError("selected Rage ability requires its own native policy")
    expected = DEFINITIONS[source]
    unit = rules.selection.units.get(source)
    if not isinstance(unit, dict) or unit.get("title") != expected["name"]:
        raise ValueError("Rage ability identity changed")
    if rules.ability_effects.get(expected["name"]) != expected["effects"]:
        raise ValueError("Rage ability definition changed; native contract review required")
    return True


def active(actor, source):
    if source not in DEFINITIONS:
        raise ValueError("unknown native Rage ability")
    return not actor.abilities_suppressed and source in ABILITIES.known(actor)


def raging(actor):
    return "난동" in actor.conditions


def end_save_forbidden(actor, condition):
    """Both abilities forbid only the native end-of-turn Rage save."""
    return condition == "난동" and raging(actor) and any(active(actor, source) for source in SOURCES)


def outgoing_damage_bonus(actor):
    """White Flame contributes +5 only while its owner is actively raging."""
    return 5 if raging(actor) and active(actor, WHITE_FLAME) else 0


def incoming_damage_reduction(actor):
    """Enduring Rage contributes DR 5 only while its owner is actively raging."""
    return 5 if raging(actor) and active(actor, ENDURING_RAGE) else 0
