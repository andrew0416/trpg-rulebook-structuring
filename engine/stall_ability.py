"""Stall's native queue and Interrupt exceptions (abilities.csv:262, PTU 1.05)."""
from hashlib import sha256
from pathlib import Path

SOURCE = 'ability/시간벌기'
NAME = '시간벌기'
SOURCE_SHA = '87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'


def registration(rules, source):
    if source != SOURCE:
        return False
    if rules._selected_rule(SOURCE) != SOURCE:
        raise ValueError('selected Stall source required')
    if sha256((Path(rules.root) / 'input/db/abilities.csv').read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError('Stall ability source changed')
    return True


def active(actor):
    import ability_transitions as ABILITIES
    if actor.kind != 'pokemon' or not any(ABILITIES.ability_id(actor.r,value)==SOURCE for value in actor.abilities):
        return False
    return registration(actor.r, SOURCE) and ABILITIES.active(actor, SOURCE)


def order(engine, actors):
    """Keep existing ties/Trick Room order; Stall goes after every other entry."""
    last = {id(actor) for actor in actors if not isinstance(actor, dict) and active(actor)}
    return [actor for actor in actors if id(actor) not in last] + [actor for actor in actors if id(actor) in last]


def protected(engine, actor):
    # An Interrupt/borrowed frame is not the holder's own Initiative Count.
    import initiative_interrupts as INTERRUPTS
    return (actor is not None and engine._active_turn_actor is actor
            and INTERRUPTS.frame(engine) is None and active(actor))


def require_interruptible(engine, evidence):
    if evidence['kind'] not in ('between', 'reaction') and protected(engine, evidence.get('owner')):
        raise ValueError('Stall actions on their own Initiative Count cannot be Interrupted')
