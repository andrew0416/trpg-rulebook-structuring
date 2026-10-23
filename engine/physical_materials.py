"""Sourced physical material facts and damage exceptions over the existing HP owner."""
from copy import deepcopy
from pathlib import Path
import json
import physical_object_attacks as ATTACKS
import world_entities as WORLD
import state_grants as GRANTS

FIELD='physical_material'
ROPE_IDS=('item/기본-밧줄','item/다용도-밧줄','item/단단한-로프')


def _catalog(engine, rule_id):
    policy=json.loads((Path(engine.r.root)/ATTACKS.POLICY).read_text(encoding='utf-8'))
    row=policy.get('materials',{}).get(rule_id)
    if row is None or engine.r._selected_rule(rule_id)!=rule_id:
        raise ValueError('reviewed selected material rule required')
    effects,definition=engine.r.item_effects(rule_id)
    if definition!=row['definition'] or effects!=row['effects']:
        raise ValueError('selected material definition/effects changed; review required')
    return row


def quote(engine, rule_id, *, length_feet):
    """Lengths are feet from the chapter source; prices are per 25 feet."""
    row=_catalog(engine,rule_id)
    ATTACKS._integer(length_feet,'rope length in feet',row['min_length_feet'])
    if length_feet>row['max_length_feet']:raise ValueError('rope length exceeds sourced maximum')
    price=length_feet*row['price_per_25_feet']//25
    return dict(item_rule_id=rule_id,length_feet=length_feet,price=price,
                max_hp=row['max_hp'],reduction=row['reduction'],minimum_damage=row['minimum_damage'],tension_kg=row['tension_kg'],
                source=row['source'],policy_hash=ATTACKS._hash(row))


def configure(engine, actor, object_id, *, length_feet, reason):
    WORLD.require_actors(engine,actor);ATTACKS._text(reason,'material observation reason')
    obj=getattr(engine,'_physical_objects',{}).get(object_id)
    if not isinstance(obj,dict) or obj.get('kind')!='item_instance' or obj.get('item_rule_id') not in ROPE_IDS:
        raise ValueError('actual registered sourced rope instance required')
    WORLD.require_usable_object(obj)
    if any(key in obj for key in ('hp','max_hp','breaches','integrity')):
        raise ValueError('material cannot replace a separate damage owner')
    facts=quote(engine,obj['item_rule_id'],length_feet=length_feet)
    if FIELD in obj:
        validate(engine,obj)
        if obj[FIELD]['facts']!=facts:raise ValueError('material facts cannot reset damage or change rope length')
        return deepcopy(obj[FIELD])
    if ATTACKS.FIELD in obj:raise ValueError('existing durability cannot be replaced by material facts')
    def apply(e,c):
        target=e._physical_objects[object_id]
        profile=dict(max_hp=facts['max_hp'],reduction=facts['reduction'],minimum_damage=facts['minimum_damage'],
            source=facts['source'],reason=reason,observed_by=c.entity_id)
        target[FIELD]=dict(facts=deepcopy(facts),observed_by=c.entity_id,reason=reason)
        target[ATTACKS.FIELD]=dict(profile=profile,profile_hash=ATTACKS._hash(profile),hp=profile['max_hp'],attacks=[])
        return deepcopy(target[FIELD])
    return GRANTS.transition(engine,actor,apply)


def validate(engine, obj):
    if FIELD not in obj:return None
    material=obj[FIELD]
    if type(material) is not dict or set(material)!={'facts','observed_by','reason'}:
        raise ValueError('invalid physical material record')
    if obj.get('kind')!='item_instance' or obj.get('item_rule_id') not in ROPE_IDS:
        raise ValueError('material record belongs to another physical identity')
    expected=quote(engine,obj['item_rule_id'],length_feet=material['facts']['length_feet'])
    if material['facts']!=expected:raise ValueError('physical material source/length/price projection mismatch')
    ATTACKS._text(material['reason'],'material observation reason')
    if material['observed_by'] not in WORLD.actor_index(engine):raise ValueError('unknown material observer')
    profile=dict(max_hp=expected['max_hp'],reduction=expected['reduction'],minimum_damage=expected['minimum_damage'],
        source=expected['source'],reason=material['reason'],observed_by=material['observed_by'])
    if obj.get(ATTACKS.FIELD,{}).get('profile')!=profile:
        raise ValueError('material durability cannot diverge from sourced HP/DR')
    return material


def damage_policy(engine, obj, move, reviewed_move):
    """Derive tags from the exact selected Move, never a caller's sharp flag."""
    material=validate(engine,obj)
    if material is None:return None
    row=_catalog(engine,obj['item_rule_id'])
    tags=[]
    if move['type']=='불꽃':tags.append('fire')
    if reviewed_move.get('sharp') is True and '베기' in move.get('keywords',[]):tags.append('sharp')
    return contact_damage_policy(engine,obj,tags,cut_move=move['id'])


def contact_damage_policy(engine,obj,tags,*,cut_move=None):
    """Shared material tail; callers own the actual source of contact tags."""
    material=validate(engine,obj)
    if material is None:return None
    row=_catalog(engine,obj['item_rule_id'])
    allowed=bool(set(tags).intersection(row['allowed_attack_tags']))
    ignore_all=allowed and cut_move==row['ignore_all_dr_move']
    return dict(material_policy_hash=material['facts']['policy_hash'],tags=tags,allowed=allowed,
        reduction=0 if ignore_all else material['facts']['reduction'],ignore_all_dr=ignore_all,
        reason='source Cut exception ignores all rope DR' if ignore_all else
               ('source material accepts this attack' if allowed else 'rope resists attacks without sharp/fire source'))


def capacity(engine, object_id, *, load_ids):
    """Use current real object masses; over-capacity does not invent break damage."""
    obj=getattr(engine,'_physical_objects',{}).get(object_id)
    if not isinstance(obj,dict):raise ValueError('actual material object required')
    WORLD.require_usable_object(obj);material=validate(engine,obj)
    if material is None:raise ValueError('sourced material required')
    if type(load_ids) is not list or not load_ids or len(set(load_ids))!=len(load_ids) or object_id in load_ids:
        raise ValueError('distinct actual load object identities required')
    objects=getattr(engine,'_physical_objects',{});total=0
    for uid in load_ids:
        load=objects.get(uid)
        if not isinstance(load,dict):raise ValueError('actual registered load object required')
        WORLD.require_usable_object(load)
        weight=load.get('weight_kg')
        from math import isfinite
        if type(weight) not in (int,float) or not isfinite(weight) or weight<0:
            raise ValueError('observed actual load mass required')
        total+=weight
    limit=material['facts']['tension_kg']
    return dict(object_id=object_id,load_ids=list(load_ids),load_kg=total,tension_kg=limit,within_capacity=total<=limit)
