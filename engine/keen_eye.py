"""Keen Eye (abilities.csv R61 / Core 1.05 p321), including virtual grants.

The Guide owns its one-round lifetime; this owner never installs an Ability or
rewrites saved modifiers. Total Blindness remains a condition and action limit.
"""
SOURCE = 'ability/날카로운눈'


def active(engine, actor):
    import ability_transitions as ABILITIES
    if actor.abilities_suppressed:
        return False
    actual = ABILITIES.active(actor, SOURCE)
    virtual = __import__('survivalist_class').keen_eye(engine, actor)
    if not (actual or virtual):
        return False
    if actor.r._selected_rule(SOURCE) != SOURCE:
        raise ValueError('Keen Eye requires its selected source')
    return True


def modifier(engine, actor, value):
    """Remove each Accuracy penalty before it can cancel a separate bonus."""
    return max(0, value) if active(engine, actor) else value
