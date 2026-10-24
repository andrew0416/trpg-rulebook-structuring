"""Paid, GM-adjudicated attacks on real unheld physical instances.

The GM supplies hit and damage *before this object's DR*, with provenance.
This is not an automatic accuracy/DB calculator or a Combatant impersonator.
Specialized vehicle, bot and network owners are deliberately not overwritten.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import world_entities as WORLD
import state_grants as GRANTS
import frequency as FREQ
import turn as TURN
import combat_damage as DAMAGE

FIELD='physical_attack_integrity'
POLICY='data/physical-object-attack-policy.json'


import resolution_transaction as _FINGERPRINTS

def _text(value, name):
    if type(value) is not str or not value.strip():raise ValueError(name+' required')
    return value


def _integer(value, name, minimum=0):
    if type(value) is not int or value<minimum:raise ValueError(name+' must be an integer >= '+str(minimum))
    return value


def _hash(value):
    return _FINGERPRINTS.json_fingerprint(value, sort_keys=True, compact=True, allow_nan=True)


def _object(engine, uid):
    obj=getattr(engine,'_physical_objects',{}).get(uid)
    if not isinstance(obj,dict) or obj.get('kind') not in ('physical_object','item_instance'):
        raise ValueError('actual ordinary physical object required; specialized bodies keep their own damage owner')
    if any(key in obj for key in ('hp','max_hp','breaches','integrity')):
        raise ValueError('object already has a separate damage owner')
    import physical_materials as MATERIALS
    if obj.get('item_rule_id') in MATERIALS.ROPE_IDS and MATERIALS.validate(engine,obj) is None:
        raise ValueError('rope requires its sourced material and Cut exception adapter')
    return obj


def configure(engine, actor, object_id, *, max_hp, reduction, minimum_damage, source, reason):
    """GM/source-established object facts, not a universal door/forest stat block."""
    WORLD.require_actors(engine,actor)
    _integer(max_hp,'object maximum HP',1);_integer(reduction,'object DR')
    _integer(minimum_damage,'object minimum damage')
    _text(source,'object durability source');_text(reason,'GM durability reason')
    profile=dict(max_hp=max_hp,reduction=reduction,minimum_damage=minimum_damage,
                 source=source,reason=reason,observed_by=actor.entity_id)
    obj=_object(engine,object_id);WORLD.require_usable_object(obj)
    if FIELD in obj:
        validate_world(engine)
        if obj[FIELD]['profile']!=profile:raise ValueError('existing durability profile cannot reset damage or change policy')
        return deepcopy(obj[FIELD])
    def apply(e,c):
        target=_object(e,object_id)
        target[FIELD]=dict(profile=deepcopy(profile),profile_hash=_hash(profile),hp=max_hp,attacks=[])
        return deepcopy(target[FIELD])
    return GRANTS.transition(engine,actor,apply)


def _move(engine, actor, move_id):
    import move_state as MOVES
    requested=engine.r.move_id(move_id)
    if requested is None:raise ValueError('actual selected Move required')
    known=MOVES.known(engine.r,{'moves':MOVES.owned_list(actor.spec,'moves',actor.moves)})
    if requested not in known:raise ValueError('physical attack requires an actual learned or granted Move')
    mid=engine._ruleset_move(actor,requested)
    if mid is None:raise ValueError('selected Move unavailable')
    move=engine.r.move(mid);mm,_=engine.r.move_mech(mid)
    policies=json.loads((Path(engine.r.root)/POLICY).read_text(encoding='utf-8'))['moves']
    policy=policies.get(mid)
    if policy is None or move!=policy['definition'] or mm!=policy['mechanics']:
        raise ValueError('physical attack needs a reviewed selected Move effect/range policy')
    return requested,move,mm,policy


def _permission(engine, actor, obj, move, mm, *, pass_scope=None, tool_scope=None):
    import move_activation as ACTIVATION
    kind=ACTIVATION.paid_move_permission(engine,actor,obj,move,mm)
    # Every ordinary turn installs this window flag; actual status/ability
    # compositions remain guarded below.
    allowed_conditions={'combat_turn_serial','temporary_hp_lifetime','blessing_ignore_turn_open'}
    if pass_scope is not None:
        import forced_move_lock as FORCED
        import conditional_damage_base as CONDITIONAL
        if FORCED.manages(engine,move['id']):
            FORCED.current(engine,actor)
            allowed_conditions.update((FORCED.STATE,CONDITIONAL.STATE))
    if tool_scope is not None:
        import physical_tool_attacks as TOOLS
        TOOLS.require_scope(engine,actor,move,tool_scope)
        allowed_conditions.add('equipped_weapons')
    converted=pass_scope is not None and pass_scope.get('conversion') is not None
    if converted:
        import pass_moves as PASS
        import conquerors_march as MARCH
        PASS.require_scope(engine,actor,pass_scope)
        MARCH.require_conversion(engine,actor,pass_scope['conversion'])
        if any(MARCH.FLAG not in row for row in MARCH.TIME.records(actor)):
            raise ValueError('other timed physical-attack compositions require their native adapter')
        allowed_conditions.add('combat_timed_effects')
    def unsupported_reactions(c):
        if not converted or c is not actor:return bool(c.registry or c.abilities)
        import ability_transitions as AB
        return bool(c.registry or any(AB.ability_id(engine.r,name)!=MARCH.RUN_UP for name in c.abilities))
    if (any(unsupported_reactions(c) for c in WORLD.actors(engine)) or actor.spec.get('mount_id') or (actor.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(actor))
            or set(actor.custom_conditions)-allowed_conditions or getattr(engine,'_league_runtime',None) is not None):
        raise ValueError('physical attack with reactive effects, body modes, mounted/League or heavy-injury activation needs its native adapter')
    if actor.conditions-{'혼란'}:
        raise ValueError('physical attack with conditions needs its native condition/activation adapter')
    if obj is not None and (obj.get('carrier_id') or obj.get('equipped_by') or obj.get('telekinetic_holder_id')):
        raise ValueError('held/collateral physical target needs its holder and exposure adapter')
    import weapon_actions as WEAPONS
    if '통과' in move.get('keywords',[]) or converted:
        if pass_scope is None:raise ValueError('Pass Move requires its actual movement/complete target-set activation adapter')
        import pass_moves as PASS
        PASS.require_scope(engine,actor,pass_scope)
        return kind
    rng=WEAPONS.range_spec(engine,move,actor)
    distance=WORLD.distance_known(actor,obj)
    limit=1 if rng.get('origin')=='melee' else rng.get('origin')
    if rng.get('shape') or type(limit) is not int or distance is None or distance>limit:
        raise ValueError('physical attack requires a resolved single-target range and actual distance')
    # Opportunity attacks still need their real Combatant/reactive producer.
    if limit>1 and distance>1 and TURN.adjacent_enemies(engine,actor):
        raise ValueError('physical ranged attack under threat needs its opportunity-attack adapter')
    return kind


def attack(engine, actor, object_id, move_id, *, event_id, hit, damage_before_dr, source, reason):
    """Resolve one actual paid Move using an explicit GM attack adjudication."""
    WORLD.require_actors(engine,actor)
    _text(event_id,'physical attack event identity');_text(source,'GM attack adjudication source')
    _text(reason,'GM attack adjudication reason');_integer(damage_before_dr,'adjudicated pre-DR damage')
    if type(hit) is not bool or (not hit and damage_before_dr):raise ValueError('a miss must have zero adjudicated damage')
    obj=_object(engine,object_id)
    intent=dict(actor_id=actor.entity_id,object_id=object_id,requested_move_id=move_id,
                hit=hit,damage_before_dr=damage_before_dr,source=source,reason=reason)
    validate_world(engine)
    for other in getattr(engine,'_physical_objects',{}).values():
        for row in other.get(FIELD,{}).get('attacks',[]):
            if row['event_id']==event_id:
                if row['intent']!=intent:raise ValueError('physical attack event identity conflicts with previous intent')
                return deepcopy(row)
    WORLD.require_usable_object(obj)
    if FIELD not in obj:raise ValueError('GM/source object durability profile required before HP damage')
    requested,move,mm,policy=_move(engine,actor,move_id)

    def apply(e,c):
        target=_object(e,object_id);state=target[FIELD]
        kind=_permission(e,c,target,move,mm)
        _pay_move(e,c,move,kind)
        import confusion_attacks as CONFUSION
        confusion=CONFUSION.begin_native(e,c,move,producer='physical',event_id=event_id)
        row=_apply_damage(e,c,target,move,policy,kind,event_id,intent)
        if policy.get('self_effects'):
            import effects as FX
            effects=FX.run_effects(e,c,c,policy['self_effects'],
                {'attacker':c,'target':c,'hit':hit,'engine':e},move['id'])
            if effects[1] or effects.pending:raise ValueError('physical attack self effects must complete')
        if confusion is not None:
            row['confusion']=CONFUSION.finish_native(e,c,move,confusion,producer='physical',event_id=event_id)
            row['receipt_hash']=_hash({k:v for k,v in row.items() if k!='receipt_hash'})
        return deepcopy(row)
    return GRANTS.transition(engine,actor,apply,include_grid=bool(obj.get('telekinetic_barrier')) and engine.grid is not None)


def _pay_move(e,c,move,kind,*,unavailable_message='physical attack action unavailable'):
    """One native payment for HP damage or a non-HP environmental outcome."""
    if not TURN.spend(e,c,kind,move['name'],_native_move=move):raise ValueError(unavailable_message)
    FREQ.consume_move(e,c,move['id'],outside_combat=False)
    c.last_move=move['id'];c.last_target=None


def _apply_damage(e,c,target,move,policy,kind,event_id,intent,*,pass_event=None,tool_attack=None):
    """Internal recipient tail; the paid ordinary/Pass producers own authority."""
    import physical_combustion as COMBUSTION
    COMBUSTION.require_unused_event(e,event_id)
    state=target[FIELD];profile=state['profile'];before=state['hp']
    import physical_materials as MATERIALS
    if tool_attack is not None:
        import physical_tool_attacks as TOOLS
        material=TOOLS.material_policy(e,target,tool_attack)
    else:material=MATERIALS.damage_policy(e,target,move,policy)
    effects=policy['mechanics'].get('effects_exec',[])
    calculation=_calculation(profile,intent['hit'],intent['damage_before_dr'],material,effects=effects,multiplier=__import__('telekinetic').barrier_multiplier(e,target,move))
    after=_hp_after(before,calculation,effects)
    row=dict(event_id=event_id,intent=deepcopy(intent),move_id=move['id'],move_type=move['type'],
             damage_class=move['class'],action_kind=kind,at=e.elapsed_seconds,
             profile_hash=state['profile_hash'],definition_hash=_hash(policy),
             hp_before=before,hp_after=after,applied_damage=before-after,calculation=calculation)
    if material is not None:row['material_policy']=material
    if pass_event is not None:row['pass_event']=pass_event
    if tool_attack is not None:row['tool_attack']=deepcopy(tool_attack)
    state['hp']=after
    if after==0:
        WORLD.finish_physical_use(e,target,'destroyed',dict(source=intent['source'],reason=intent['reason'],
            by_actor_id=c.entity_id,event_id=event_id,move_id=move['id'],at=e.elapsed_seconds))
    row['receipt_hash']=_hash(row);state['attacks'].append(row)
    return row


def pass_recipient(e,c,uid,move,policy,*,scope,event_id,intent,kind):
    import pass_moves as PASS
    PASS.object_authority(e,c,uid,move['id'],scope)
    target=_object(e,uid);WORLD.require_usable_object(target)
    if FIELD not in target:raise ValueError('GM/source object durability required')
    return deepcopy(_apply_damage(e,c,target,move,policy,kind,event_id,intent,pass_event=scope['event_id']))


def _calculation(profile, hit, damage, material=None, *, effects=(),multiplier=1):
    if not hit or not damage or material is not None and not material['allowed']:return None
    import effects_ext as EXT
    reduction=material['reduction'] if material is not None else profile['reduction']
    damage=__import__('arithmetic_policy').product(damage,multiplier)
    return DAMAGE.defend(dice=damage,attack=0,modifiers=0,defense=0,
        reduction=EXT.reduction_after_ignore(reduction,list(effects)),minimum=profile['minimum_damage'])


def _hp_after(before, calculation, effects):
    """Apply the selected floor after DR without healing an already lower HP."""
    amount=calculation['after_defense'] if calculation else 0
    for effect in effects:
        if effect.get('type')=='damage_floor':
            minimum=_integer(effect.get('min_target_hp_after'),'minimum target HP after damage',1)
            amount=min(amount,max(0,before-minimum))
    return max(0,before-amount)


def validate_world(engine, index=None):
    index=WORLD.actor_index(engine) if index is None else index
    seen=set()
    for uid,obj in getattr(engine,'_physical_objects',{}).items():
        import physical_materials as MATERIALS
        material=MATERIALS.validate(engine,obj)
        if FIELD not in obj:continue
        _object(engine,uid);state=obj[FIELD]
        if type(state) is not dict or set(state)!={'profile','profile_hash','hp','attacks'}:
            raise ValueError('invalid physical attack integrity state')
        profile=state['profile']
        if type(profile) is not dict or set(profile)!={'max_hp','reduction','minimum_damage','source','reason','observed_by'}:
            raise ValueError('invalid physical object durability profile')
        _integer(profile['max_hp'],'object maximum HP',1);_integer(profile['reduction'],'object DR')
        _integer(profile['minimum_damage'],'object minimum damage')
        _text(profile['source'],'object durability source');_text(profile['reason'],'GM durability reason')
        if profile['observed_by'] not in index or state['profile_hash']!=_hash(profile):
            raise ValueError('physical durability identity/provenance mismatch')
        if type(state['attacks']) is not list:raise ValueError('physical attack history must be a list')
        hp=profile['max_hp']
        for row in state['attacks']:
            if type(row) is not dict or row.get('receipt_hash')!=_hash({k:v for k,v in row.items() if k!='receipt_hash'}):
                raise ValueError('physical attack receipt changed')
            event=_text(row['event_id'],'physical attack event identity')
            if event in seen:raise ValueError('duplicate physical attack event identity')
            seen.add(event);intent=row['intent']
            tool_policy=None
            if 'tool_attack' in row:
                import physical_tool_attacks as TOOLS
                tool_move,tool_mm,tool_policy=TOOLS.validate_receipt(engine,row)
            if tool_policy is None and ('pass_event' in row or '통과' in engine.r.move(row['move_id']).get('keywords',[])):
                import pass_moves as PASS
                PASS.validate_object_receipt(engine,uid,row)
            if intent['actor_id'] not in index or intent['object_id']!=uid or row['profile_hash']!=state['profile_hash']:
                raise ValueError('physical attack source/target/profile mismatch')
            _text(intent['source'],'GM attack adjudication source');_text(intent['reason'],'GM attack adjudication reason')
            _integer(intent['damage_before_dr'],'adjudicated pre-DR damage')
            if type(intent['hit']) is not bool or (not intent['hit'] and intent['damage_before_dr']):
                raise ValueError('physical miss damage mismatch')
            expected_material=None
            pass_policy=None
            if 'pass_event' in row:
                import pass_moves as PASS
                parent=getattr(engine,PASS.KEY,{}).get(row['pass_event'])
                if parent is None:raise ValueError('physical recipient lost its actual paid Pass')
                pass_policy=PASS.receipt_policy(engine,parent)
            if tool_policy is not None:
                expected_material=TOOLS.material_policy(engine,obj,tool_policy)
                if row.get('material_policy')!=expected_material:raise ValueError('tool material attack exception changed')
            elif material is not None:
                move=engine.r.move(row['move_id'])
                reviewed=pass_policy or json.loads((Path(engine.r.root)/POLICY).read_text(encoding='utf-8'))['moves'].get(row['move_id'])
                if reviewed is None or move!=reviewed['definition'] or engine.r.move_mech(row['move_id'])[0]!=reviewed['mechanics']:
                    raise ValueError('material attack requires unchanged reviewed Move')
                expected_material=MATERIALS.damage_policy(engine,obj,move,reviewed)
                if row.get('material_policy')!=expected_material:raise ValueError('material attack exception changed')
            elif 'material_policy' in row:raise ValueError('material attack exception without material')
            reviewed=tool_policy or pass_policy or json.loads((Path(engine.r.root)/POLICY).read_text(encoding='utf-8'))['moves'].get(row['move_id'])
            if pass_policy is not None and row['definition_hash']!=_hash(pass_policy):raise ValueError('physical Pass selected Move policy changed')
            if 'confusion' in row:
                if 'pass_event' in row:raise ValueError('Pass recipients cannot duplicate parent Confusion')
                import confusion_attacks as CONFUSION
                CONFUSION.validate_native(index[intent['actor_id']],reviewed['definition'],row['confusion'],
                    producer='tool' if tool_policy is not None else 'physical',event_id=event)
            effects=reviewed['mechanics'].get('effects_exec',[]) if reviewed else []
            calculation=_calculation(profile,intent['hit'],intent['damage_before_dr'],expected_material,effects=effects,multiplier=__import__('telekinetic').barrier_multiplier(engine,obj,engine.r.move(row['move_id'])))
            if row['calculation']!=calculation or row['hp_after']!=_hp_after(hp,calculation,effects):
                raise ValueError('physical attack damage calculation mismatch')
            _integer(row['hp_after'],'physical HP');_integer(row['applied_damage'],'physical damage')
            if hp<=0 or row['hp_before']!=hp or row['hp_after']!=hp-row['applied_damage']:
                raise ValueError('physical attack HP history mismatch')
            hp=row['hp_after']
        if type(state['hp']) is not int or state['hp']!=hp:raise ValueError('physical object HP projection mismatch')
        if hp==0:
            terminal=obj.get('destroyed')
            if type(terminal) is not dict or not state['attacks'] or terminal.get('event_id')!=state['attacks'][-1]['event_id']:
                raise ValueError('physical HP exhaustion requires the matching destruction event')

