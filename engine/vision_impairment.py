"""One projection for Blindness accuracy (ch07:637-639).

``Combatant.conditions`` and the observed battlefield light remain the state
owners. This module resolves the precedence between ordinary Blindness, Total
Blindness and sensory immunity, so consumers never add -6 and -10.
"""


BLIND = "실명"
TOTAL = "완전-실명"
ALIASES = {"완전 실명": TOTAL}
SOURCE_BLIND = "condition/실명"
SOURCE_TOTAL = "condition/완전-실명"


def _blindsense(actor):
    import capability_traits as TRAITS
    return "blindsense" in TRAITS.owned(actor)


def explicit_level(actor):
    """Return the selected affliction level after Blindsense immunity."""
    if _blindsense(actor):
        return "none"
    conditions = {ALIASES.get(name, name) for name in __import__('blessing_effects').effective_conditions(actor)}
    if TOTAL in conditions:
        if actor.r._selected_rule(SOURCE_TOTAL) != SOURCE_TOTAL:
            raise ValueError("selected Total Blindness needs its own policy")
        return "total"
    if BLIND in conditions and not __import__('keen_eye').active(None,actor):
        if actor.r._selected_rule(SOURCE_BLIND) != SOURCE_BLIND:
            raise ValueError("selected Blindness needs its own policy")
        return "ordinary"
    return "none"


def accuracy_level(engine, actor):
    """Resolve explicit conditions and observed light through one precedence."""
    explicit = explicit_level(actor)
    if explicit != "none":
        return explicit
    import survivalist_features as SURVIVALIST
    environmental, _ = SURVIVALIST.vision(engine, actor)
    return 'none' if environmental == 'ordinary' and __import__('keen_eye').active(engine,actor) else environmental


def accuracy_penalty(engine, actor, target=None):
    # Explicit afflictions retain the existing precedence. Only the
    # environmental branch replaces coarse darkness with mapped distance.
    explicit=explicit_level(actor)
    if explicit!='none':return {'ordinary':-6,'total':-10}[explicit]
    if target is not None:
        import scene_lighting as LIGHT
        result=LIGHT.projection(engine,actor,target)
        if result is not None:return result['penalty']
    return {"none": 0, "ordinary": -6, "total": -10}[accuracy_level(engine, actor)]


def require_move(engine, actor, move):
    """Reject selected Priority/Interrupt Moves before the producer spends.

    Optional conditional Priority belongs to its actual modifier producer;
    an unused option never makes an otherwise ordinary Move forbidden.
    """
    import turn as TURN
    if accuracy_level(engine,actor)!='total':return
    import effects_ext as EXT
    keywords=set(EXT.keywords_for(actor,move))|set(move.get('keywords') or ())
    keywords|=set(engine.r.moves_mech.get(move['id'],{}).get('header',{}).get('keywords') or ())
    if TURN.has_priority(engine,actor,move) or '방해' in keywords or '방해' in str(move.get('range','')):
        raise ValueError('Total Blindness prohibits Priority or Interrupt Moves')
