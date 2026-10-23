"""Read native creation/transformation lineage without a parallel origin ledger."""
from copy import deepcopy


def describe(*, kind, source, owner_id, inputs, outputs, retained, native_ref, quantities=()):
    for value in (kind,source,owner_id):
        if type(value) is not str or not value:raise ValueError('actual origin kind/source/owner required')
    for values in (inputs,outputs,retained):
        if type(values) is not list or any(type(v) is not str or not v for v in values) or len(set(values))!=len(values):
            raise ValueError('distinct actual materialization identities required')
    if set(retained)-set(outputs):raise ValueError('retained identity must be an actual output')
    if type(native_ref) is not dict or not native_ref:raise ValueError('native origin address required')
    return {'kind':kind,'source':source,'owner_id':owner_id,'inputs':list(inputs),'outputs':list(outputs),
            'retained':list(retained),'new_outputs':[v for v in outputs if v not in retained],
            'native_ref':deepcopy(native_ref),'quantities':deepcopy(list(quantities))}


def read(engine, entity_id, *, production_id=None):
    import world_entities as W
    entities=W.entity_index(engine)
    entity=entities.get(entity_id)
    if entity is None:raise ValueError('actual materialized entity required')
    actors=W.actor_index(engine)
    actor=actors.get(entity_id)
    if actor is not None and actor.spec.get('egg_entity_id'):
        if production_id is not None:raise ValueError('hatch origin is not a crafting production')
        import creation_egg as EGGS
        return EGGS.lineage(engine,actor)
    obj=getattr(engine,'_physical_objects',{}).get(entity_id)
    if not obj or 'crafting_origin' not in obj:return None
    import crafting_products as PRODUCTS
    maker=actors.get(obj['crafting_origin']['maker_id'])
    if maker is None:raise ValueError('actual product maker origin required')
    view=PRODUCTS.lineage(engine,maker,production_id or obj['crafting_origin']['production_id'])
    if entity_id not in view['outputs']:raise ValueError('production is not the origin of this object')
    return view


def validate_world(engine):
    import world_entities as W
    for actor in W.actor_index(engine).values():
        if actor.spec.get('egg_entity_id'):read(engine,actor.entity_id)
    for identity,row in getattr(engine,'_physical_objects',{}).items():
        if 'crafting_origin' in row:read(engine,identity)
    return True
