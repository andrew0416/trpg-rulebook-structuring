"""Shared bounded recovery arithmetic; native owners supply authority and costs.

Healing, barrier grants, repair and injury removal keep separate resource and
operation declarations. No operation here grants resurrection or reconnects a
digital entity merely because its numeric balance became positive.
"""
import common_checks as C

RESOURCES = {'hp', 'temp_hp', 'integrity', 'injuries'}


def resolve(current, requested, *, resource, mode='add', ceiling=None, floor=0,
            allowance=None, eligible=True, blocked_reason=None):
    if type(resource) is not str or resource not in RESOURCES or type(mode) is not str or mode not in ('add', 'at_least', 'remove'):
        raise ValueError('explicit recovery resource and operation required')
    C.integer(current,'current recovery balance',0 if resource in ('temp_hp','injuries') else None)
    C.integer(requested,'requested recovery',0)
    C.integer(floor,'recovery floor',0)
    if ceiling is not None:C.integer(ceiling,'recovery ceiling',0)
    if allowance is not None:C.integer(allowance,'remaining recovery allowance',0)
    if type(eligible) is not bool:
        raise ValueError('recovery eligibility must be an observed boolean')
    if not eligible and (type(blocked_reason) is not str or not blocked_reason.strip()):
        raise ValueError('ineligible recovery needs its actual reason')
    if mode == 'remove':
        if current < floor:raise ValueError('protected balance exceeds the actual resource')
        desired = max(floor,current-requested)
        applied = current-desired
    else:
        desired = current+requested if mode=='add' else requested
        if ceiling is not None:desired=min(ceiling,desired)
        applied = max(0,desired-current)
    if allowance is not None:applied=min(applied,allowance)
    if not eligible:applied=0
    return {'resource':resource,'mode':mode,'requested':requested,'before':current,
            'after':current-applied if mode=='remove' else current+applied,
            'applied':applied,'ceiling':ceiling,'floor':floor,'allowance':allowance,
            'eligible':eligible,'blocked_reason':blocked_reason}


def physical_causes(actor, condition):
    import combat_timing as TIME
    return [row for row in TIME.records(actor)
            if row.get('manual_end') and condition in row.get('statuses',())]


def repair_integrity(engine, entity_id, amount, *, source, eligible, reason):
    """Apply an explicitly authorized repair to a real separate Integrity pool."""
    import world_entities as W
    import special_entities as SPECIAL
    import state_grants as G
    W._text(entity_id,'Integrity entity');W._text(source,'repair source')
    W._text(reason,'repair authority reason')
    if source in engine.r.selection.units and engine.r._selected_rule(source)!=source:
        raise ValueError('repair source selection changed')
    row=getattr(engine,'_physical_objects',{}).get(entity_id)
    if not row or row.get('kind') not in ('digital_avatar','digital_node'):
        raise ValueError('repair requires an actual separate Integrity resource')
    SPECIAL.validate_record(engine,row)
    plan=resolve(row['integrity'],amount,resource='integrity',ceiling=row['max_integrity'],
                 eligible=eligible,blocked_reason=None if eligible else reason)
    def apply(staged, primary):
        target=staged._physical_objects[entity_id]
        target['integrity']=plan['after']
        SPECIAL.validate_record(staged,target)
        receipt=dict(plan,entity_id=entity_id,source=source,reason=reason,
                     at=staged.elapsed_seconds,kind='integrity_repair')
        import event_trace as TRACE
        TRACE.calculation(staged,recovery=receipt)
        staged.log('  '+entity_id+': Integrity '+str(plan['before'])+' → '+str(plan['after']),source)
        return receipt
    return G.transition(engine,None,apply)
