"""Source-bound child actions emitted by a committed native effect occurrence.

The source separately owns action cost, accuracy, opposed check and success.
Only Push/Trip currently have a complete child consumer here. Known missing
consumers are Blocked/missing_runtime, never a request for a GM to invent law.
Receipts retain actor references through GM snapshots; causal IDs reuse the root
child contract. The pure root model is not used as a certificate for live code.
"""
from dataclasses import dataclass, replace
from copy import deepcopy
import common_checks as C
from root_children import child_id

RECORDS='_maneuver_grants'

@dataclass(frozen=True)
class Policy:
    maneuver: str
    cost: str
    accuracy: str='ordinary'
    opposed: str='required'
    success: str='check'
    optional: bool=True
    source_ref: str=''

POLICIES={
 'move/괴력':Policy('밀기','free','automatic',source_ref='input/db/moves.csv:괴력; input/ch07-combat.md:454-459'),
 'move/돌진':Policy('걸기','free',source_ref='input/db/moves.csv:돌진; input/ch07-combat.md:466-471'),
 'move/물고버티기':Policy('붙잡기','free',source_ref='input/db/moves.csv:물고버티기; input/ch07-combat.md:495-516'),
 'move/문어굳히기':Policy('붙잡기','included','automatic',optional=False,source_ref='input/db/moves.csv:문어굳히기; input/ch07-combat.md:495-516'),
 'ability/호박잡기-playtest':Policy('붙잡기','included','automatic','waived','automatic',False,'input/db/abilities.csv:호박잡기-playtest'),
 'move/휩쓸기-일격':Policy('걸기','free',source_ref='input/db/moves.csv:휩쓸기-일격'),
 'ability/스크루지느러미':Policy('질주','free','none','none','no_check',source_ref='input/db/abilities.csv:스크루지느러미'),
 'ability/일렉트로대시-playtest':Policy('질주','free','none','none','no_check',source_ref='input/db/abilities.csv:일렉트로대시-playtest'),
 'move/튀어오르기':Policy('뛰기','included',opposed='none',optional=False,source_ref='input/db/moves.csv:튀어오르기'),
}

@dataclass(frozen=True)
class ManeuverPending(C.PendingDecision):
    category: str='player_choice'
    grant_id: str=''
    tag: str='AwaitingInput'
    reason: str='source_choice'

@dataclass(frozen=True)
class ManeuverResult:
    grant_id: str
    accepted: bool
    result: object=None
    tag: str='Completed'
    following_effects: tuple=()

def _pending(row,detail,category='player_choice',reason='source_choice'):
    blocked=category!='player_choice'
    row['status']='blocked' if blocked else 'awaiting_input'
    value=ManeuverPending(detail,basis={'source':row['source'],'authority':dict(row['authority']),'parent_occurrence':row['occurrence'],'source_refs':[row['policy'].source_ref] if row.get('policy') else []},category=category,grant_id=row['id'],tag='Blocked' if blocked else 'AwaitingInput',reason=reason)
    row['pending']=value
    return value

def _plain(value):
    if isinstance(value,dict):return {k:_plain(v) for k,v in value.items() if k!='decision'}
    if isinstance(value,(tuple,list)):return tuple(_plain(v) for v in value)
    return value

def _authority(policy):
    if policy is None:return {}
    return dict(action_cost=policy.cost,accuracy=policy.accuracy,opposed=policy.opposed,success=policy.success)

def dispatch(engine,actor,target,effect,ctx):
    import effect_contracts as EFFECTS
    source=ctx.get('source_id');occurrence=ctx.get('effect_occurrence')
    EFFECTS.validate_receipt(engine,ctx.get('effect_receipt'),source,occurrence,actor,target,effect)
    if not isinstance(source,str) or not isinstance(occurrence,str):raise ValueError('canonical source and actual effect occurrence required')
    identity=child_id(occurrence,'free_maneuver','native-maneuver')
    records=actor.custom_conditions.setdefault(RECORDS,{})
    row=records.get(identity)
    if row is not None:
        if row['actor'] is not actor or row['target'] is not target or row['effect']!=effect:raise ValueError('cannot retarget or replace a granted maneuver')
        return row.get('result') or row.get('pending') or _pending(row,'Continue the existing child action')
    policy=POLICIES.get(source)
    row=dict(receipt=ctx['effect_receipt'],id=identity,actor=actor,target=target,source=source,occurrence=occurrence,effect=deepcopy(effect),policy=policy,authority=_authority(policy),round=engine.round_no,scene=actor.spec.get('frequency_state',{}).get('scene',0),turn_owner=getattr(engine,'_active_turn_actor',None),closures=len(engine._turn_closures),status='outstanding',accepted=None,declaration=None,actor_position=tuple(actor.pos),target_position=tuple(target.pos),action_history=tuple(getattr(actor,'_action_history',[])),elapsed_seconds=engine.elapsed_seconds)
    records[identity]=row
    if policy is None:return _pending(row,'This source has no reviewed maneuver-grant refinement','unsupported_maneuver','missing_refinement')
    if engine.r._selected_rule(source)!=source:return _pending(row,'Selected source variant needs its own maneuver refinement','unresolved_source','source_ambiguity')
    if effect.get('maneuver')!=policy.maneuver:return _pending(row,'Effect maneuver disagrees with its reviewed source','unsupported_maneuver','missing_refinement')
    controls={'on_miss','on_natural_roll_min','on_natural_roll','if_weather','on_ko','if'}
    allowed={'type','maneuver','target','note'}|controls
    hints={}
    if source=='move/괴력':hints={'auto_hit':True,'still_opposed_check':True}
    elif source=='move/문어굳히기':hints={'auto_hit':True}
    elif source=='ability/호박잡기-playtest':hints={'auto_hit':True,'advantage':True,'auto_success':True}
    elif source=='ability/일렉트로대시-playtest':hints={'no_aoo':True}
    unknown={k for k in effect if not k.startswith('_')}-allowed-set(hints)
    wrong={k for k,v in hints.items() if k in effect and effect[k] is not v}
    if unknown or wrong:return _pending(row,'Source refinement has no consumer for fields: '+', '.join(sorted(unknown|wrong)),'unsupported_maneuver','missing_refinement')
    if policy.maneuver in ('밀기','걸기','붙잡기') and effect.get('target','target')!='target':return _pending(row,'Source requires its actual parent target','unsupported_maneuver','missing_refinement')
    # Parser hints cannot expand source authority. They may omit a proven rule.
    if effect.get('auto_hit') and policy.accuracy!='automatic' or effect.get('auto_success') and policy.success!='automatic' or effect.get('advantage') and policy.success!='automatic':
        return _pending(row,'Effect requests an exemption its source does not grant','unsupported_maneuver','missing_refinement')
    if policy.maneuver not in ('밀기','걸기','붙잡기') or source=='move/휩쓸기-일격':
        return _pending(row,'Known source authority retained; actual '+policy.maneuver+' child runtime/refinement is not implemented','unsupported_maneuver','missing_runtime')
    if not engine.encounter_active or engine.round_start_seconds is None or row['turn_owner'] is not actor:
        return _pending(row,'Immediate child requires its actual open parent turn','unsupported_maneuver','invalid_state')
    pending=_pending(row,'Choose whether to take the granted maneuver, then each participant chooses an allowed skill')
    options=ctx.get('maneuver_options')
    if options is not None:
        if not isinstance(options,dict):raise ValueError('maneuver choices must be a mapping')
        return resolve(engine,actor,identity,**options)
    return pending

def authority(engine,actor,target,row):
    if actor.custom_conditions.get(RECORDS,{}).get(row['id']) is not row or row['actor'] is not actor or row['target'] is not target or row['status']!='running':raise ValueError('live running child receipt required')
    if row['policy'] is None or POLICIES.get(row['source'])!=row['policy'] or row['authority']!=_authority(row['policy']):raise ValueError('source authority changed')
    if row['policy'].maneuver not in ('밀기','걸기','붙잡기') or row['source']=='move/휩쓸기-일격':raise ValueError('child consumer is not supported')
    return dict(row['authority'],source=row['source'],child_id=row['id'],maneuver='maneuver/'+row['policy'].maneuver)

def resolve(engine,actor,grant_id,*,accept=None,**choices):
    import effect_contracts as EFFECTS
    row=actor.custom_conditions.get(RECORDS,{}).get(grant_id)
    if row is None or row['actor'] is not actor:raise ValueError('actual actor does not own this child obligation')
    if row['status']=='completed':return _resolve(engine,actor,grant_id,accept=accept,**choices)
    with EFFECTS.resuming(engine,row['receipt']):
        EFFECTS.ensure_clear(engine)
        EFFECTS.validate_continuation(engine,row['receipt'])
        return _resolve(engine,actor,grant_id,accept=accept,**choices)

def _resolve(engine,actor,grant_id,*,accept=None,**choices):
    import action_lifecycle as ACTION
    import physics_maneuvers as PHYSICS
    row=actor.custom_conditions.get(RECORDS,{}).get(grant_id)
    if row is None or row['actor'] is not actor:raise ValueError('actual actor does not own this child obligation')
    if accept is not None and type(accept) is not bool:raise ValueError('accept choice must be boolean')
    allowed={'challenger_skill','defender_skill','fixed_accuracy','challenger_options','defender_options','follow_steps'}
    if set(choices)-allowed:raise ValueError('unknown maneuver choice; exemption flags are source-owned')
    declaration=_plain(choices)
    if row['status']=='completed':
        if accept is not None and accept!=row['result'].accepted or choices and declaration!=row['declaration']:raise ValueError('completed child declaration cannot change')
        return row['result']
    if row['status']=='running':raise ValueError('child action cannot reenter itself')
    policy=row['policy']
    target=row['target']
    import effect_contracts as EFFECTS
    EFFECTS.validate_receipt(engine,row['receipt'],row['source'],row['occurrence'],actor,target,row['effect'])
    if not engine.encounter_active or engine.round_no!=row['round'] or len(engine._turn_closures)!=row['closures'] or getattr(engine,'_active_turn_actor',None)is not row['turn_owner'] or actor.spec.get('frequency_state',{}).get('scene',0)!=row['scene'] or engine.elapsed_seconds!=row['elapsed_seconds']:
        return _pending(row,'Immediate child outlived its source occurrence','unsupported_maneuver','invalid_state')
    if engine.r._selected_rule(row['source'])!=row['source']:return _pending(row,'Source selection changed after the parent occurrence','unresolved_source','source_ambiguity')
    if row['accepted'] is not True and (tuple(actor.pos)!=row['actor_position'] or tuple(target.pos)!=row['target_position'] or tuple(getattr(actor,'_action_history',[]))!=row['action_history'] or engine.elapsed_seconds!=row['elapsed_seconds']):
        return _pending(row,'Immediate child cannot be saved across another action or changed world geometry','unsupported_maneuver','invalid_state')
    if accept is False:
        if policy is None or not policy.optional:raise ValueError('source does not grant a choice to decline this child')
        if row['accepted'] is True:raise ValueError('an accepted observed action cannot be retroactively declined')
        result=ManeuverResult(grant_id,False);row.update(status='completed',result=result,accepted=False,declaration={});return _finish(engine,row,result)
    if row['pending'].reason in ('missing_runtime','missing_refinement','source_ambiguity'):return row['pending']
    if accept is None and row['accepted'] is not True:return _pending(row,'Player chooses whether to use the granted maneuver')
    if policy.opposed!='waived' and (not choices.get('challenger_skill') or not choices.get('defender_skill')):return _pending(row,'Each participant must choose a skill permitted by this maneuver')
    if row['declaration'] is not None and row['declaration']!=declaration:raise ValueError('cannot change an already observed child declaration')
    old_history=len(getattr(actor,'_action_history',[]));old_declaration=row['declaration']
    row.update(status='running',declaration=deepcopy(declaration,{id(x):x for x in engine.everyone}),accepted=True)
    try:
        with ACTION.maneuver_grant(engine,actor,target,row) as token:
            import grapple_state as GRAPPLE
            method=GRAPPLE.initiate if policy.maneuver=='붙잡기' else PHYSICS.push if policy.maneuver=='밀기' else PHYSICS.trip
            value=method(engine,actor,target,_grant=token,**choices)
    except Exception:
        # A feature callback may already have observed the skill result. The
        # native skill maneuver receipt retains cost, AoO and accuracy exactly.
        observed=len(getattr(actor,'_action_history',[]))!=old_history or actor.custom_conditions.get('_skill_maneuver_active') is not None
        row.update(status='awaiting_input',declaration=row['declaration'] if observed else old_declaration,accepted=True if observed else None)
        raise
    if isinstance(value,C.PendingDecision):
        observed=len(getattr(actor,'_action_history',[]))!=old_history
        if not observed:row.update(declaration=old_declaration,accepted=None)
        return _pending(row,value.required,'unresolved_source','source_ambiguity')
    result=ManeuverResult(grant_id,True,value)
    row.update(status='completed',result=result)
    return _finish(engine,row,result)

def _finish(engine,row,result):
    import effect_contracts as EFFECTS
    EFFECTS.finish(engine,row['receipt'],'completed',result)
    import effects as FX
    following=FX.resume_effects(engine,row['receipt'])
    if getattr(following,'outcomes',()):
        result=replace(result,following_effects=following.outcomes)
        row['result']=result
        EFFECTS.finish(engine,row['receipt'],'completed',result)
    return result

def check_end(engine,actor):
    for row in actor.custom_conditions.get(RECORDS,{}).values():
        if _blocks_boundary(row):
            raise ValueError('finish the required or accepted child maneuver before closing its parent turn')
    # Choosing to end the turn declines unused optional opportunities before
    # end-of-turn ticks; their following effects still belong to the parent.
    close_turn(engine,actor)

def close_turn(engine,actor):
    while True:
        row=next((x for x in actor.custom_conditions.get(RECORDS,{}).values() if x['status']!='completed' and x.get('policy') and x['policy'].optional and x.get('accepted') is None),None)
        if row is None:return
        result=resolve(engine,actor,row['id'],accept=False)
        if isinstance(result,C.PendingDecision):raise ValueError('stale or unresolved child cannot be declined by ending its turn')


def _blocks_boundary(row):
    policy=row.get('policy')
    return row['status'] not in ('completed','running') and (row.get('accepted') is True or policy is None or not policy.optional)

def ensure_clear(engine):
    """A world boundary cannot discard an observed or source-required child."""
    for actor in getattr(engine,'everyone',[]):
        for row in actor.custom_conditions.get(RECORDS,{}).values():
            if _blocks_boundary(row):
                raise ValueError('finish the required or observed child maneuver before a new action or encounter boundary')
