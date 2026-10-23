"""Actual equipped weapon contact surfaces and paid object-target Struggle.

GM observations describe the real contact surface and pre-DR result; existing
weapon grants, action costs, material damage and physical HP retain ownership.
"""
from contextlib import contextmanager
from copy import deepcopy
import physical_object_attacks as ATTACKS
import physical_materials as MATERIALS
import optional_weapon_framework as WEAPONS
import weapon_actions as ACTIONS
import world_entities as WORLD
import state_grants as GRANTS
import turn as TURN

FIELD='physical_weapon_contact_surface'
SURFACES=('cutting_edge','sharp_point','blunt')


def _policy(e,uid):
    obj,profile=WEAPONS.object_profile(e,uid,usable=False)
    if profile['arcane']:raise ValueError('Arcane weapon contact needs its own material adapter')
    return dict(weapon_profile_hash=ATTACKS._hash(profile),weapon_rules=WEAPONS.policy(e.r),
                struggle=e.r.mech('combat/struggle'),weapon_kind=TURN.WEAPON_KIND[profile['kind']])


def surface(e,uid):
    obj=getattr(e,'_physical_objects',{}).get(uid)
    if obj is None or FIELD not in obj:raise ValueError('actual sourced weapon contact surface required')
    row=obj[FIELD]
    if (type(row) is not dict or set(row)!={'facts','facts_hash'}
            or row['facts_hash']!=ATTACKS._hash(row['facts'])):
        raise ValueError('weapon contact surface observation changed')
    facts=row['facts']
    if (set(facts)!={'tool_id','contact_surface','source','reason','observed_by','policy_hash'}
            or facts['tool_id']!=uid or facts['contact_surface'] not in SURFACES
            or facts['observed_by'] not in WORLD.actor_index(e)
            or facts['policy_hash']!=ATTACKS._hash(_policy(e,uid))):
        raise ValueError('weapon contact surface lost its actual source/profile')
    for key in ('source','reason'):ATTACKS._text(facts[key],'weapon surface '+key)
    return row


def observe(e,c,uid,*,contact_surface,source,reason):
    WORLD.require_actors(e,c)
    ATTACKS._text(source,'GM contact-surface source');ATTACKS._text(reason,'GM contact-surface reason')
    obj,profile=WEAPONS.object_profile(e,uid)
    if c.entity_id not in (obj.get('owner_id'),obj.get('carrier_id'),obj.get('equipped_by')):
        raise ValueError('actual accessible owned weapon required')
    if contact_surface not in SURFACES:raise ValueError('explicit actual cutting edge, sharp point or blunt contact required')
    facts=dict(tool_id=uid,contact_surface=contact_surface,source=source,reason=reason,
               observed_by=c.entity_id,policy_hash=ATTACKS._hash(_policy(e,uid)))
    if FIELD in obj:
        prior=surface(e,uid)
        if prior['facts']!=facts:raise ValueError('weapon contact surface observation is immutable')
        return deepcopy(prior)
    def apply(staged,actor):
        row=dict(facts=deepcopy(facts),facts_hash=ATTACKS._hash(facts))
        staged._physical_objects[uid][FIELD]=row
        surface(staged,uid)
        return deepcopy(row)
    return GRANTS.transition(e,c,apply)


def _prepare(e,c,uid):
    obj,profile=WEAPONS.object_profile(e,uid);observed=surface(e,uid)
    if obj.get('equipped_by')!=c.entity_id:raise ValueError('actual weapon must be equipped by the attacker')
    entries=[entry for entry in c.custom_conditions.get('equipped_weapons',{}).values()
             if entry.get('instance_id')==uid and entry['weapon'].get('framework_instance')==uid]
    if len(entries)!=1:raise ValueError('actual physical weapon grant required')
    mid=entries[0]['struggle_id']
    if mid not in c.moves:raise ValueError('actual equipped weapon Struggle grant required')
    move=ACTIONS.prepare(e,c,e.r.move(mid),uid);mm,_=e.r.move_mech(mid)
    if move['class']!='물리' or move.get('source')!='weapon' or mm.get('effects_exec'):
        raise ValueError('ordinary physical weapon Struggle required')
    policy=dict(definition=deepcopy(move),mechanics=deepcopy(mm),tool_id=uid,
                surface_hash=observed['facts_hash'],source_policy_hash=ATTACKS._hash(_policy(e,uid)))
    return move,mm,policy


@contextmanager
def _scope(e,c,uid,move):
    if hasattr(e,'_physical_tool_scope'):raise ValueError('nested tool attack requires an actual producer')
    token=dict(actor=c,tool_id=uid,move_id=move['id'])
    e._physical_tool_scope=token
    try:yield token
    finally:del e._physical_tool_scope


def require_scope(e,c,move,token):
    if (getattr(e,'_physical_tool_scope',None) is not token or token['actor'] is not c
            or token['move_id']!=move['id']):raise ValueError('tool attack requires its actual equipped-weapon producer')
    actual,_,_=_prepare(e,c,token['tool_id'])
    if actual!=move:raise ValueError('tool attack changed its prepared weapon')


def material_policy(e,target,policy):
    observed=surface(e,policy['tool_id'])
    if observed['facts_hash']!=policy['surface_hash']:
        raise ValueError('tool attack contact surface changed')
    tags=['sharp'] if observed['facts']['contact_surface'] in ('cutting_edge','sharp_point') else []
    return MATERIALS.contact_damage_policy(e,target,tags)


def validate_receipt(e,row):
    policy=row['tool_attack'];uid=policy['tool_id'];facts=surface(e,uid)
    move=policy['definition'];mm=policy['mechanics']
    if (policy['source_policy_hash']!=ATTACKS._hash(_policy(e,uid))
            or policy['surface_hash']!=facts['facts_hash'] or row['definition_hash']!=ATTACKS._hash(policy)
            or row['intent'].get('tool_id')!=uid or row['move_id']!=move['id']
            or row['intent']['requested_move_id']!=move['id']
            or move.get('source')!='weapon' or move.get('class')!='물리'
            or move.get('_weapon_attack',{}).get('source')!=WEAPONS.SOURCE
            or move.get(WEAPONS.MARK,{}).get('instance_id')!=uid
            or row['move_type']!=move['type'] or row['damage_class']!=move['class']):
        raise ValueError('tool attack lost its physical weapon source')
    return move,mm,policy


def _line(e,c,target,move):
    import body_state as BODY,body_modes as MODES
    location=WORLD.effective_location(e,target);actor_location=WORLD.location_of(c)
    if (e.grid is None or location['kind']!='grid' or location.get('map_id')!=actor_location.get('map_id')):
        raise ValueError('weapon object attack needs an actual mapped target')
    cell=tuple(location['cell'])
    if not any(not e.grid.blocked(q,cell) and not MODES.blocks_line(e,q,cell,ignored=(c,))
               for q in BODY.cells(c,require_complete=True)):
        raise ValueError('weapon object attack line is blocked')
    distance=WORLD.distance_known(c,target)
    if distance is None or distance<move['_weapon_attack']['minimum_distance']:
        raise ValueError('weapon object attack is within its minimum range')


def attack(e,c,object_id,tool_id,*,event_id,hit,damage_before_dr,source,reason):
    WORLD.require_actors(e,c)
    for value,name in ((event_id,'event identity'),(source,'GM attack source'),(reason,'GM attack reason')):
        ATTACKS._text(value,name)
    ATTACKS._integer(damage_before_dr,'adjudicated pre-DR damage')
    if type(hit) is not bool or not hit and damage_before_dr:raise ValueError('a miss must have zero damage')
    ATTACKS.validate_world(e)
    # Durable replay precedes current equipment: the original weapon can since
    # have been unequipped, transferred or destroyed without paying again.
    for obj in getattr(e,'_physical_objects',{}).values():
        for row in obj.get(ATTACKS.FIELD,{}).get('attacks',[]):
            if row['event_id']==event_id:
                intent=row['intent']
                expected=dict(actor_id=c.entity_id,object_id=object_id,tool_id=tool_id,
                    requested_move_id=row['move_id'],hit=hit,damage_before_dr=damage_before_dr,source=source,reason=reason)
                if 'tool_attack' not in row or intent!=expected:raise ValueError('tool attack event conflicts with previous intent')
                return deepcopy(row)
    def apply(staged,actor):
        target=ATTACKS._object(staged,object_id);WORLD.require_usable_object(target)
        if ATTACKS.FIELD not in target:raise ValueError('actual object durability required')
        if object_id==tool_id:raise ValueError('tool cannot be its own object target')
        move,mm,policy=_prepare(staged,actor,tool_id);_line(staged,actor,target,move)
        intent=dict(actor_id=actor.entity_id,object_id=object_id,tool_id=tool_id,
                    requested_move_id=move['id'],hit=hit,damage_before_dr=damage_before_dr,source=source,reason=reason)
        with _scope(staged,actor,tool_id,move) as token:
            kind=ATTACKS._permission(staged,actor,target,move,mm,tool_scope=token)
            ATTACKS._pay_move(staged,actor,move,kind,unavailable_message='weapon attack action unavailable')
            import confusion_attacks as CONFUSION
            confusion=CONFUSION.begin_native(staged,actor,move,producer='tool',event_id=event_id)
            row=ATTACKS._apply_damage(staged,actor,target,move,policy,kind,event_id,intent,tool_attack=policy)
            if confusion is not None:
                row['confusion']=CONFUSION.finish_native(staged,actor,move,confusion,producer='tool',event_id=event_id)
                row['receipt_hash']=ATTACKS._hash({k:v for k,v in row.items() if k!='receipt_hash'})
            ATTACKS.validate_world(staged)
            import improvised_weapons as IMPROVISED
            IMPROVISED.observe_tool_attack(staged,actor,row)
            return deepcopy(row)
    return GRANTS.transition(e,c,apply)


def validate_world(e):
    for uid,obj in getattr(e,'_physical_objects',{}).items():
        if FIELD in obj:surface(e,uid)
    return True
