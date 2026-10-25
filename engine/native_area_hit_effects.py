"""Bind selected area effects to each actual paid native hit, exactly once."""
from pathlib import Path
import json

_POLICY=json.loads((Path(__file__).resolve().parents[1]/'data/native-area-hit-effects.json').read_text(encoding='utf-8'))['moves']

def manages(e,mid):
    return mid in _POLICY

def selected(e,mid):
    row=_POLICY[mid]
    mechanics=e.r.move_mech(mid)[0]
    if mid=='move/소란피기':
        import area_targets as AREA
        if not AREA.empty_field_effects(mechanics):raise ValueError('actual Uproar field adapter required')
        mechanics={'effects_exec':[{k:v for k,v in x.items() if k!='_activation_scope'} for x in mechanics['effects_exec']]}
    if e.r.move(mid)!=row['definition'] or mechanics!=row['mechanics']:
        raise ValueError('area-hit effect requires its unchanged reviewed selected source')
    return row

def owns(e,mid,effect):
    if mid=='move/소란피기':effect={k:v for k,v in effect.items() if k!='_activation_scope'}
    return effect.get('target')=='all_targets' and manages(e,mid) and effect in selected(e,mid)['mechanics'].get('effects_exec',[])

def range_spec(e,move,result):
    mid=move['id']
    if not manages(e,mid):return result
    row=selected(e,mid)
    if row['mapless_observed_area']:
        import mapless_space as SPACE
        if e.grid is None and SPACE.active(e):
            # The selected source has no numeric range. The GM's complete
            # observed set supplies the area; do not invent a grid radius.
            return dict(result,origin='self',shape='observed_area')
    return result

def preflight(e,actor,target,effect,mid):
    if not owns(e,mid,effect):raise ValueError('selected area-hit source/effect required')
    import weapon_actions as WEAPONS
    import pass_moves as PASS
    if PASS.is_pass(e.r.move(mid)) or PASS.converted_scope(e,actor,mid):
        scope=getattr(e,'_pass_move_scope',None)
        if scope is None:raise ValueError('area-hit Pass needs its actual path producer')
        PASS.require_scope(e,actor,scope)
        if scope['move_id']!=mid or target not in scope['creatures']:raise ValueError('actual planned Pass recipient required')
        return (target,)
    if not WEAPONS.range_spec(e,e.r.move(mid),actor).get('shape'):
        raise ValueError('this selected area needs an actual GM mapless target ruling')
    return (target,)

def require_activation(e,actor,target,mid,activation,accuracy):
    if manages(e,mid):
        selected(e,mid)
        if mid=='move/소란피기':return
        if activation is None:
            raise ValueError('area-hit effects require the complete native target activation')

def require_targets(e,actor,move,targets,primary):
    if not manages(e,move['id']):return
    selected(e,move['id'])
    # Do not let a caller omit a real member of the current area observation.
    import world_entities as WORLD
    actual=e.targets_in_range(actor,move,list(WORLD.actor_index(e).values()),primary)
    actual=__import__('musician').friendly_targets(actor,move,actual)
    if {c.entity_id for c in targets}!={c.entity_id for c in actual}:
        raise ValueError('complete actual area targets required; a member was omitted')

def require_candidates(e,actor,move,candidates,primary):
    if manages(e,move['id']):
        targets=__import__('musician').friendly_targets(actor,move,e.targets_in_range(actor,move,candidates,primary))
        require_targets(e,actor,move,targets,primary)

def recipients(e,actor,target,effect,ctx):
    mid=ctx.get('source_id');preflight(e,actor,target,effect,mid)
    if mid=='move/소란피기' and effect.get('_activation_scope')=='field':
        import move_completion as COMPLETE,body_state as BODY,world_entities as W
        if not COMPLETE.authorized_field(e,ctx,effect):raise ValueError('actual Uproar completion required')
        if e.grid is None:raise ValueError('actual Uproar five-meter geometry required')
        area=set().union(*(e.grid.burst(cell,5)|{cell} for cell in BODY.cells(actor,require_complete=True)))
        return tuple(c for c in W.actor_index(e).values() if c.on_field and not c.captured and BODY.cells(c,require_complete=True).intersection(area)
                     and __import__('effects_ext').keyword_block_reason(e,actor,c,ctx['move']) is None)
    import attack_damage_history as HISTORY
    frame=HISTORY.native_recipient(e,actor,target,ctx,error='area effect does not belong to the actual native hit')
    if frame is None:raise ValueError('area effect needs its live native hit recipient')
    import effect_contracts as CONTRACTS
    CONTRACTS.validate_receipt(e,ctx.get('effect_receipt'),mid,
        ctx.get('effect_occurrence'),actor,target,effect)
    import pass_moves as PASS
    if PASS.is_pass(e.r.move(mid)):PASS.require_native_target(e,actor,target,mid)
    # The activation dispatches the effect once for each hit member. Returning
    # the full group here would apply every effect N times to every member.
    return (target,)



def bind(e,actor,primary,move):
    import area_targets as AREA,weapon_actions as WEAPONS
    if not manages(e,move['id']) or e.grid is None or '_area_aim' in move:return move
    shape=WEAPONS.range_spec(e,move,actor).get('shape')
    if shape in ('burst','close_blast','cone','line'):
        return AREA.bind(e,actor,move,actor.pos if shape=='burst' else primary.pos)
    return move


def push_outside(e,actor,target,effect,ctx):
    if ctx.get('source_id')!='move/하이퍼보이스' or not owns(e,'move/하이퍼보이스',effect):
        raise ValueError('exact native Hyper Voice displacement required')
    import area_targets as AREA,body_state as BODY
    completion=getattr(e,'_move_completions',{}).get(ctx.get('move_completion'))
    if completion is None:raise ValueError('actual Hyper Voice area completion required')
    move=completion['move'];area=AREA.cells(e,actor,move)
    direction=((target.pos[0]>actor.pos[0])-(target.pos[0]<actor.pos[0]),(target.pos[1]>actor.pos[1])-(target.pos[1]<actor.pos[1]))
    if direction==(0,0):raise ValueError('Hyper Voice needs a resolved outward direction')
    count=0;body=BODY.cells(target,require_complete=True)
    while any((c[0]+direction[0]*count,c[1]+direction[1]*count) in area for c in body):count+=1
    return count
