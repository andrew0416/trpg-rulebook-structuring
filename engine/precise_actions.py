"""Precision tasks (ch07:560-568): native combat evidence, separate Focus roll.

Only an explicit delicate ordinary task opts in. No blanket modifier is attached
 to SkillRoll or feature/maneuver checks. HP loss is not evidence of an attack.
"""
import arithmetic_policy as M
from copy import deepcopy
from dataclasses import replace
import common_checks as C
import common_action_checks as COMMON

SOURCE="ch07-combat/전투의-다른-행동/정밀-스킬-체크"

def initialize(e):
    e._precision_events=[]
    e._precision_sequence=0

def _record(e,c,kind,source,**values):
    if not e.encounter_active or e.round_start_seconds is None:return None
    e.time_actors([c])
    e._precision_events[:]=[x for x in e._precision_events if x["round"]>=e.round_no-1]
    e._precision_sequence+=1
    row=dict(id=e._precision_sequence,round=e.round_no,target=c,kind=kind,source=source,**values)
    e._precision_events.append(row)
    return row

def attacked(e,actor,target,move,*,producer="Engine.use_move"):
    # Self-only buffs are not attacks against the actor. Direct self-damage
    # producers can still register an actual damaging hit below.
    if actor is target and move.get("class")=="변화":return None
    return _record(e,target,"attack",move["id"],actor=actor,producer=producer,
                   move_class=move["class"],result="activated")

def accuracy(event,hit):
    if event is not None:event["result"]="accuracy_hit" if hit else "miss"

def damage_hit(e,actor,target,move,event,facts,damage):
    if event is None:event=attacked(e,actor,target,move,producer="Engine.resolve_attack_damage")
    if event is None:return
    # PTU p236/238 and immunity/absorption hit triggers (p316-335) separate
    # successful hit from dealt damage. Wonder Guard p336 explicitly cannot hit.
    event.update(result="hit_prevented" if facts.get("hit_prevented") else "damaging_hit",
                 hit_prevented=facts.get("hit_prevented"),nullification=facts.get("nullification"),resolved_damage=damage)

def injury(e,c,amount,source):
    import campaign_injury_policy as CAMPAIGN
    import injury_recovery as INJURY
    retained=CAMPAIGN.injury_added(e,c,amount,source)
    INJURY.note_change(e,c,retained,source)
    if retained>0:
        _record(e,c,"injury",source,amount=retained)
        __import__('type_ace').gravel(e,c,'actual_injury')

def clear(e):e._precision_events.clear()

def evidence(e,c):
    rows=[x for x in e._precision_events if x["target"] is c and e.round_no-1<=x["round"]<=e.round_no]
    attacks=[x for x in rows if x["kind"]=="attack"]
    hit=any(x["result"]=="damaging_hit" for x in attacks)
    return dict(attacked=bool(attacks),damaging_hit=hit,
                injuries=sum(x["amount"] for x in rows if x["kind"]=="injury"),
                event_ids=tuple(x["id"] for x in rows),round=e.round_no)

def _prepared(e,c,skill,options,*,featured=False):
    if not isinstance(options,dict):raise ValueError("roll options must be a mapping")
    opts=COMMON.assisted_options(e,c,skill,dict(options))
    if featured:
        import skill_feature_actions as SF
        prepared=SF.prepared_for_sequence(e,c,skill,opts)
    else:prepared=e._prepare_skill_roll(c,skill,**opts)
    if prepared[3] is not None:opts["fixed"]=prepared[3]
    if prepared[4] is not None:opts["fixed_penalties"]=prepared[4]
    return opts

def perform(e,actor,skill,dc,options,adjudication):
    import passive_events as PASSIVE
    import heavy_injury_adapter as HEAVY
    PASSIVE.ensure_clear(e);HEAVY.ensure_clear(e)
    options=dict(options)
    context=options.pop("context",None)
    task=options.pop("task_options",{})
    focus=options.pop("focus_options",{})
    if options:raise ValueError("unknown precision task options: "+str(sorted(options)))
    if actor is None or skill is None or dc is None:return C.PendingDecision("GM precision task actor / skill / DC")
    if not isinstance(context,dict) or context.get("delicate") is not True or context.get("activity")!="ordinary_task" or not isinstance(context.get("purpose"),str) or not context["purpose"].strip():
        return C.PendingDecision("GM explicit delicate ordinary task and concrete purpose; no blanket combat skill modifier")
    if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError("selected Precision Skill Checks variant requires its own procedure")
    C.integer(dc,"task DC")
    if not e.encounter_active or e.round_start_seconds is None:return C.PendingDecision("precision combat procedure requires an open combat round; use ordinary skill outside combat")
    observed=evidence(e,actor)
    if not isinstance(task,dict) or not isinstance(focus,dict):raise ValueError("roll options must be mappings")
    featured=task.get("feature") is not None or (observed["attacked"] and focus.get("feature") is not None)
    if featured:
        ids=[task.get("roll_id")]+([focus.get("roll_id")] if observed["attacked"] else [])
        if any(not isinstance(uid,str) or not uid.strip() for uid in ids) or len(set(ids))!=len(ids):
            raise ValueError("featured precision rolls require distinct actual roll IDs")
    task=_prepared(e,actor,skill,task,featured=featured)
    if observed["attacked"]:focus=_prepared(e,actor,"집중",focus,featured=featured)
    elif focus:raise ValueError("no additional Focus roll is required without a recent attack")
    if observed["attacked"] and task.get("roll_id") is not None and task.get("roll_id")==focus.get("roll_id"):
        raise ValueError("ordinary task and additional Focus need distinct roll identities")
    C.validate_adjudication(**adjudication)
    def resolve(staged,rolls=None):
        ordinary=rolls[0] if rolls is not None else staged.skill_roll(actor,skill,**task)
        concentration=(rolls[1] if rolls is not None else staged.skill_roll(actor,"집중",**focus)) if observed["attacked"] else None
        failure=0 if concentration is None or concentration.total>=16 else -(1+M.ratio(16-concentration.total,4))
        hit_penalty=-2 if observed["damaging_hit"] else 0
        injury_penalty=-2*observed["injuries"]
        penalty=failure+hit_penalty+injury_penalty
        adjusted=replace(ordinary,modifier=ordinary.modifier+penalty)
        check=C.against_dc(adjusted,dc)
        import skill_feature_actions as SF
        SF.finish(staged,actor,task.get("roll_id"))
        if concentration is not None:SF.finish(staged,actor,focus.get("roll_id"))
        basis={"source":SOURCE,"context":deepcopy(context),"evidence":observed,
               "ordinary_roll":ordinary,"focus_roll":concentration,"focus_dc":16 if concentration else None,
               "focus_penalty":failure,"hit_penalty":hit_penalty,"injury_penalty":injury_penalty,
               "adjusted_roll":adjusted,"penalty":penalty}
        staged.log(f"  정밀작업: 원작업 {ordinary.total}, 집중 {concentration.total if concentration else '-'}, 페널티 {penalty} → {check.total} vs DC {dc}",SOURCE)
        return replace(C.adjudicate(check,**adjudication),basis=basis)
    if featured:
        import skill_feature_actions as SF
        plans=[(actor,skill,task)]+([(actor,"집중",focus)] if observed["attacked"] else [])
        basis={"source":SOURCE,"context":deepcopy(context),"dc":dc,"evidence":observed}
        return SF.sequence(e,"precise:"+task["roll_id"],basis,plans,lambda rolls:resolve(e,rolls))
    return COMMON._staged_rolls(e,resolve)
