"""Consumed Poffin history and current-owner availability (ch03:383-384)."""
import arithmetic_policy as M

STATS=("아름다움","근사함","귀여움","슬기로움","강인함")
GRACE="edge/우아함"


def history(pokemon):
    if pokemon.kind!="pokemon" or type(pokemon.level)is not int or not 1<=pokemon.level<=100:
        raise ValueError("Poffin state requires a Pokemon with an established level")
    values=pokemon.spec.get("poffins",[])
    if not isinstance(values,list) or any(s not in STATS for s in values):
        raise ValueError("ordered consumed Poffin stat history required")
    # Imported history is state evidence, not proof of its acquisition legality.
    if len(values)>8:raise ValueError("Poffin benefit history exceeds the Grace maximum")
    return tuple(values)


def current_owner(engine,pokemon,trainer=None):
    owner_id=pokemon.spec.get("trainer_id")
    if trainer is not None:
        if trainer.kind!="trainer" or not owner_id or trainer.spec.get("id")!=owner_id:
            raise ValueError("Poffin availability needs the current actual owner")
        if engine is not None:
            from world_entities import actor_index
            if actor_index(engine,extra=(pokemon,trainer)).get(owner_id) is not trainer:
                raise ValueError("Poffin owner identity is ambiguous")
        return trainer
    if engine is None or not owner_id:return None
    from world_entities import actor_index
    actual=actor_index(engine,extra=(pokemon,)).get(owner_id)
    if actual is None or actual.kind!="trainer":
        raise ValueError("current Poffin owner must be present for availability evaluation")
    return actual


def grace(pokemon,trainer=None,*,engine=None):
    actual=current_owner(engine,pokemon,trainer)
    if actual is None:return False
    edges=actual.spec.get("edges",[])
    if not isinstance(edges,(list,tuple)):raise ValueError("acquired edges must be a list")
    count=sum(value in (GRACE,"우아함","Grace") for value in edges)
    if count>1:raise ValueError("Grace requires one actual acquisition, not repeated aliases")
    if count and pokemon.r._selected_rule(GRACE)!=GRACE:
        raise ValueError("Grace variant requires its own Poffin availability contract")
    if count:
        from skill_modifiers import rank
        if max(rank(pokemon.r,actual,skill)[2] for skill in ("매력","명령","교활","협박","직감"))<3:
            raise ValueError("Grace requires a Novice eligible social skill")
    return bool(count)


def available(pokemon,trainer=None,*,engine=None):
    values=history(pokemon)
    has_grace=grace(pokemon,trainer,engine=engine)
    ordinary_cap=min(6,1+M.ratio(pokemon.level,5))
    witnessed=any(isinstance(row,dict) and row.get("benefit_source")==GRACE and row.get("effective") is True
                  for row in pokemon.spec.get("poffin_consumption",[]))
    if ordinary_cap<6 and len(values)>ordinary_cap and not (has_grace or witnessed):
        raise ValueError("Poffin history exceeds level allowance without a Grace source")
    if len(values)>ordinary_cap+2 and not witnessed:
        raise ValueError("Poffin history exceeds the level plus Grace allowance")
    # Grace's transfer rule limits use to six, preserving every consumed benefit.
    usable=values[:8 if has_grace else 6]
    return __import__('coordinator').flexible_projection(pokemon,usable,engine=engine)


def consumption_limit(pokemon,trainer=None,*,engine=None):
    history(pokemon)
    return min(6,1+M.ratio(pokemon.level,5))+(2 if grace(pokemon,trainer,engine=engine) else 0)


def projection(pokemon,trainer=None,*,engine=None):
    values=history(pokemon);usable=available(pokemon,trainer,engine=engine)
    return {"source":"ch03:383-384","history":list(values),"available":list(usable),
            "unavailable_count":len(values)-len(usable),"current_owner_id":pokemon.spec.get("trainer_id"),
            "consumption_limit":consumption_limit(pokemon,trainer,engine=engine)}
