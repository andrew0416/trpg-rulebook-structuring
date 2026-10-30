"""C09-082: one manufactured condition, one actual reusable daily instrument."""
from copy import deepcopy

import common_checks as C
import equipment_item_contracts as CONTRACTS
import frequency as FREQ
import resolution_transaction as TX
import state_grants as G
import world_entities as W

SOURCES=('item/마법피리','item/마법피리-1')
PROFILE='magic_flute_profile'
FREQUENCY={'kind':'daily','uses':1}
SOURCE_FILE='input/ch09-equipment.md'
SOURCE_SHA256='b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'


def definition(rules,item_id):
    if item_id not in SOURCES:raise ValueError('exact Magic Flute source required')
    # The native reader authenticates item selection and the battle-tool chapter
    # through source_selection.require_current_source/verified_source. Pin that
    # already checked chapter interpretation without reading its bytes twice.
    effects,header=rules.item_effects(item_id)
    chapter=rules.selection.units[CONTRACTS.BATTLE_TOOL_SOURCE]['source']
    if (header.get('id')!=item_id or chapter.get('file')!=SOURCE_FILE.removeprefix('input/')
            or chapter.get('sha256')!=SOURCE_SHA256):
        raise ValueError('selected Magic Flute source changed')
    expected=[{'type':'cure_status','status':'fixed at creation',
               'target':'all within 20m','limit':'하루 1회'}]
    if effects!=expected or header['battle_tool']['stock_policy']!='daily_reusable':
        raise ValueError('selected Magic Flute effect requires its own adapter')
    return header


def _condition(rules,condition):
    # ch07:574 and the Other Conditions introduction exclude those states
    # from Status Afflictions and ordinary status cures (PTU core pp246/248).
    if (type(condition) is not str or rules.condition_class(condition) not in ('persistent','volatile')
            or condition in ('기절','사망','임시 체력','임시-체력')):
        raise ValueError('manufactured flute requires one sourced ordinary curable condition')
    source='condition/'+condition
    if rules._selected_rule(source)!=source:raise ValueError('selected flute condition source changed')
    return condition


def _object(engine,instance_id):
    obj=getattr(engine,'_physical_objects',{}).get(instance_id)
    if not isinstance(obj,dict) or obj.get('kind')!='item_instance' or obj.get('item_rule_id') not in SOURCES:
        raise ValueError('actual registered Magic Flute physical identity required')
    definition(engine.r,obj['item_rule_id'])
    return obj


def validate_object(engine,obj):
    profile=obj.get(PROFILE)
    if profile is None:
        if 'frequency_state' in obj:raise ValueError('Magic Flute manufacture profile is missing')
        return None
    fields={'source','instance_id','condition','calendar_owner_id','observed_day','initial_used','reason','sha256'}
    if (type(profile) is not dict or set(profile)!=fields
            or profile['sha256']!=TX.request_fingerprint({k:v for k,v in profile.items() if k!='sha256'})
            or profile['instance_id']!=obj.get('id') or profile['source']!=obj.get('item_rule_id')):
        raise ValueError('Magic Flute manufacture identity or fixed choice changed')
    definition(engine.r,profile['source']);_condition(engine.r,profile['condition'])
    W._text(profile['reason'],'manufactured flute observation reason')
    C.integer(profile['observed_day'],'observed flute day',0)
    C.integer(profile['initial_used'],'observed flute daily usage',0,1)
    owner=FREQ.physical_owner(engine,obj)
    state=obj['frequency_state'];rows=state['activations']
    if state['calendar_owner_id']!=profile['calendar_owner_id'] or set(rows)!={profile['source']}:
        raise ValueError('Magic Flute physical quota identity changed')
    row=rows[profile['source']]
    C.integer(row['used'],'physical flute daily usage',0,1)
    if (profile['observed_day']>owner.spec['frequency_state']['day']
            or type(row['period']) is int and row['period']<profile['observed_day']):
        raise ValueError('Magic Flute quota is outside its observed calendar')
    if (row['period']==profile['observed_day'] and row['used']<profile['initial_used']):
        raise ValueError('Magic Flute initial daily usage was erased')
    return profile


def observe(engine,instance_id,*,manufactured_condition,calendar_owner,day,available,reason):
    """GM imports an existing manufacture choice and observed current charge.

    This is neither a recipe nor permission to choose a new condition at use.
    A stable observed actor calendar supplies the existing narrative day reset.
    """
    W.require_actors(engine,calendar_owner)
    obj=_object(engine,instance_id);W.require_usable_object(obj)
    _condition(engine.r,manufactured_condition);W._text(reason,'manufactured flute observation reason')
    C.integer(day,'explicit observed flute day',0)
    if type(available) is not bool:raise ValueError('explicit observed flute availability required')
    FREQ.validate(calendar_owner)
    if day!=calendar_owner.spec.get('frequency_state',{}).get('day',0):
        raise ValueError('observed flute day must match its actual calendar')
    profile={'source':obj['item_rule_id'],'instance_id':instance_id,'condition':manufactured_condition,
             'calendar_owner_id':calendar_owner.entity_id,'observed_day':day,
             'initial_used':int(not available),'reason':reason}
    profile['sha256']=TX.request_fingerprint(profile)
    old=validate_object(engine,obj)
    if old is not None:
        if old==profile:return deepcopy(old)
        raise ValueError('Magic Flute manufacture choice and original availability are immutable')
    def apply(e,c):
        actual=_object(e,instance_id)
        FREQ.bind_physical(e,actual,c,actual['item_rule_id'],FREQUENCY,used=int(not available))
        actual[PROFILE]=deepcopy(profile);validate_object(e,actual)
        e.gm._rec('Magic Flute manufacture observation',None,profile,reason,c)
        return deepcopy(profile)
    return G.transition(engine,calendar_owner,apply,include_rulings=True)


def _recipients(engine,actor):
    import body_state as BODY
    from grid import cheb
    if engine.grid is None:
        return C.PendingDecision('Magic Flute needs observed mapped radial body geometry',
            basis={'source':'C09-082','radius_metres':20,'needed':'actual map and body footprints; caller target lists cannot replace all radial recipients'})
    participants=[c for c in W.actor_index(engine).values()
                  if c.kind in ('trainer','pokemon') and c.on_field and not c.captured]
    shapes={};unknown=[]
    for c in participants:
        view=BODY.projection(c)
        if not view['geometry_complete']:unknown.append(c.entity_id)
        else:
            occupied=BODY.cells(c,require_complete=True)
            if any(not engine.grid.inside(cell) for cell in occupied):
                raise ValueError('Magic Flute recipient body is outside the actual map')
            shapes[c.entity_id]=occupied
    if unknown:
        return C.PendingDecision('Magic Flute needs complete observed recipient bodies',
            basis={'source':'C09-082','unknown_actor_ids':unknown,'radius_metres':20,
                   'needed':'GM observes actual size/footprint and location before any charge or action'})
    origin=shapes[actor.entity_id]
    return [c for c in participants if any(cheb(a,b)<=20 for a in origin for b in shapes[c.entity_id])]


def _plan(engine,r):
    import item_stock as STOCK
    W.require_actors(engine,r.user,r.target)
    definition(engine.r,r.source_id)
    if (r.target is not r.user or r.free or r.count!=1
            or any(getattr(r,key) is not None for key in (
                'duration_minutes','duration_reason','food_policy','selected_move','container_selection','shell_batch_id'))):
        raise ValueError('Magic Flute uses one ordinary Standard activation with automatic radial recipients')
    if not r.user.on_field or r.user.captured:raise ValueError('actual field flute user required')
    if engine.encounter_active and (r.user.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(r.user)):
        raise ValueError('Magic Flute Standard use requires reviewed heavy-injury action composition')
    if r.held_selection is None:
        return C.PendingDecision('Magic Flute needs one actual reusable physical instrument',
            basis={'source':r.source_id,'catalog':definition(engine.r,r.source_id)['battle_tool'],
                   'needed':'select an existing held physical tool; quantity inventory cannot identify its manufacture choice or daily charge'})
    stock=STOCK.prepare(engine,r.user,r.source_id,held_selection=r.held_selection)
    import crafting_recipes as RECIPES
    RECIPES.require_tool(engine,r.user,stock['instance_id'])
    obj=_object(engine,stock['instance_id']);profile=validate_object(engine,obj)
    if profile is None:
        return C.PendingDecision('GM must observe this flute\'s original manufacture condition and current daily availability',
            basis={'source':r.source_id,'catalog':definition(engine.r,r.source_id)['battle_tool'],
                   'instance_id':obj['id'],'needed':'GMState.observe_magic_flute(manufactured_condition, calendar_owner, day, available, reason); never choose condition during use'})
    if not __import__('glitch_bender').frequency_allowed(r.user,FREQ.parse(FREQUENCY)[0]):raise ValueError('Access Denied permits only At-Will actions this round')
    if not FREQ.physical_activation_allowed(engine,obj,r.source_id,FREQUENCY):
        raise ValueError('this physical Magic Flute was already used today')
    targets=_recipients(engine,r.user)
    if isinstance(targets,C.PendingDecision):return targets
    return obj,profile,targets


def prepare(engine,r):
    plan=_plan(engine,r)
    return plan if isinstance(plan,C.PendingDecision) else None


def consume(engine,r):
    plan=_plan(engine,r)
    if isinstance(plan,C.PendingDecision):return plan
    import turn as TURN
    def apply(e,actor):
        from dataclasses import replace
        request=replace(r,user=actor,target=actor)
        current=_plan(e,request)
        if isinstance(current,C.PendingDecision):raise ValueError('Magic Flute observations changed before commit')
        obj,profile,targets=current
        if not TURN.spend(e,actor,'standard','마법피리'):return (0,0)
        FREQ.consume_physical_activation(e,obj,r.source_id,FREQUENCY)
        cured=[];retained=[]
        for target in targets:
            afflicted=profile['condition'] in target.conditions
            if not __import__('glitch_bender').benefits_blocked(target):e.cure_status(target,profile['condition'])
            if afflicted:(retained if profile['condition'] in target.conditions else cured).append(target.entity_id)
        result={'source':r.source_id,'instance_id':obj['id'],'condition':profile['condition'],
                'recipients':[c.entity_id for c in targets],'cured':cured,'retained':retained,
                'frequency':deepcopy(obj['frequency_state']['activations'][r.source_id])}
        e.log(actor.name+'이(가) 마법피리로 반경20m 상태를 치료',r.source_id)
        validate_object(e,obj)
        return result
    return G.transition(engine,r.user,apply)


def validate_world(engine,index):
    for obj in getattr(engine,'_physical_objects',{}).values():
        if PROFILE in obj or obj.get('item_rule_id') in SOURCES and 'frequency_state' in obj:
            _object(engine,obj.get('id'));validate_object(engine,obj)
