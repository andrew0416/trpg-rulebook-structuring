"""Authenticated continuing equipment-benefit suppression; never stock permission."""
from hashlib import sha256
from pathlib import Path

KEY='equipment_suspension'
KLUTZ='ability/서투름-소실'
KLUTZ_NAME='서투름 [소실]'
CSV_SHA='87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'


def _klutz(engine,actor):
    import ability_transitions as ABILITIES
    if actor.kind!='pokemon' or actor.abilities_suppressed:return False
    # project_components resolves actual owned names through source selection;
    # passing a slug to the name-only ability_id fallback loses the CSV marker.
    if not ABILITIES.project_components(actor).get(KLUTZ):return False
    if engine.r._selected_rule(KLUTZ)!=KLUTZ:
        raise ValueError('exact selected Klutz SwSh source required')
    rulings=engine.r.rulings
    if any(getattr(rulings,key,{}).get(KLUTZ) for key in ('mech','effects')):
        raise ValueError('overridden Klutz requires its own equipment policy')
    if sha256((Path(engine.r.root)/'input/db/abilities.csv').read_bytes()).hexdigest()!=CSV_SHA:
        raise ValueError('Klutz equipment source changed')
    return True


def reasons(engine,actor,registration_key,record):
    import items as ITEMS,field_effects as FIELD
    result=[]
    if ITEMS._passive_registration(engine,actor,record) and FIELD.passive_equipment_suppressed(engine,actor,record):
        result.append({'kind':'field','source':FIELD.active(engine,'신비')['source_id'],
                       'holder_id':actor.entity_id,'registration_key':registration_key})
    # Consuming stock is a separate producer. Suppress continuing held benefits,
    # including their active registration eligibility, without banning item use.
    if record.get('held_slot') is not None and _klutz(engine,actor):
        result.append({'kind':'ability','source':KLUTZ,
                       'holder_id':actor.entity_id,'registration_key':registration_key})
    return result


def benefit_active(actor,record):
    import items as ITEMS,state_grants as G
    return (not record.get(KEY) and not record.get(ITEMS.MAGIC_ROOM_KEY)
            and record.get('state_source') in actor.spec.get(G.KEY,{}).get('sources',{}))


def upgrade_legacy(engine,index):
    """Upgrade marker-only field saves on candidate restore, never on save."""
    import items as ITEMS
    changed=[]
    try:
        for actor in index.values():
            for key,record in getattr(actor,'_item_reg',{}).items():
                if KEY in record or ITEMS.MAGIC_ROOM_KEY not in record:continue
                expected=reasons(engine,actor,key,record)
                field=next((r for r in expected if r['kind']=='field'),None)
                if field is None or record[ITEMS.MAGIC_ROOM_KEY]!={'field_source':field['source'],'registration_key':key}:
                    raise ValueError('legacy equipment marker lacks its actual field/item source')
                record[KEY]={'reasons':expected};changed.append(record)
        validate(engine,index)
    except Exception:
        for record in changed:record.pop(KEY,None)
        raise
    return True


def validate(engine,index):
    import items as ITEMS,state_grants as G,held_equipment as HELD
    for actor in index.values():
        registrations=getattr(actor,'_item_reg',{})
        for key,record in registrations.items():
            expected=reasons(engine,actor,key,record)
            stored=record.get(KEY)
            if stored is not None and stored!={'reasons':expected}:
                raise ValueError('equipment suppression differs from its actual source/holder')
            if bool(expected)!=(stored is not None):
                raise ValueError('equipment suppression needs its actual retained reasons')
            field=next((r for r in expected if r['kind']=='field'),None)
            legacy=None if field is None else {'field_source':field['source'],'registration_key':key}
            if record.get(ITEMS.MAGIC_ROOM_KEY)!=legacy:
                raise ValueError('field equipment suspension evidence changed')
            source=record.get('state_source')
            live=source in actor.spec.get(G.KEY,{}).get('sources',{})
            if source is not None and live==bool(expected):
                raise ValueError('equipment benefit source disagrees with suspension')
            if expected:
                uid=record.get('instance_id')
                if uid is not None:
                    obj=getattr(engine,'_physical_objects',{}).get(uid,{})
                    if obj.get('equipped_by')!=actor.entity_id or obj.get('item_rule_id')!=record.get('item_id'):
                        raise ValueError('suppressed equipment lost its actual physical holder')
                if record.get('held_slot') is not None and not any(
                        r.get('registration_key')==key and r.get('instance_id')==uid for r in HELD.entries(actor)):
                    raise ValueError('suppressed equipment lost its actual held slot')
    return True
