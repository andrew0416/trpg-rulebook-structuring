"""C10-105: one innate cultivation space on the actual Planter Pokemon.

Capability is an admission requirement. An already planted physical organism
retains its growth/source policy; losing the capability does not delete it.
"""
from copy import deepcopy
import re
import crafting_recipes as Q
import cultivation_state as P
from source_context import verified_source

SOURCE='capability/플랜터'
REFERENCE={'file':'input/ch10-index-reference.md','sha256':'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}
KIND='capability_planter'


def restriction(name):
    if type(name) is not str:return False
    match=re.fullmatch(r'(?:capability/)?(?:플랜터|Planter)\s*(?:\(([^()]+)\))?',name.strip(),re.I)
    if not match:return False
    return match.group(1).strip() if match.group(1) else None


def permits(qualifier,species,kind):
    if qualifier is None:return True
    aliases={'나무열매':'berry','나무열매 종류':'berry','열매':'berry','berries':'berry','berry':'berry',
             '허브':'herb','herbs':'herb','herb':'herb','규토리':'apricorn','apricorns':'apricorn','apricorn':'apricorn'}
    return aliases.get(qualifier.casefold(),qualifier)==kind or qualifier==species


def site_id(actor):return actor.entity_id+':capability:planter'


def _holder(actor):
    import partial_entities as PARTIAL
    PARTIAL.require_complete(actor,'Planter planting')
    if actor.kind!='pokemon':raise ValueError('actual Pokemon Planter holder required')


def select(engine,actor,species,crop):
    _holder(actor)
    if actor.dead or actor.fainted:raise ValueError('conscious Planter holder required for planting')
    Q._selected(engine,SOURCE);verified_source(engine.r,REFERENCE,label='Planter')
    import state_grants as GRANTS
    choices=[(name,restriction(name)) for name in GRANTS.effective_capabilities(actor) if restriction(name) is not False]
    for name,qualifier in choices:
        if permits(qualifier,species,crop['kind']):return name,qualifier
    raise ValueError('current Planter capability does not permit this plant kind')


def definition(rules,actor,species,key,capability,planter_policy,plant_identity=None):
    qualifier=restriction(capability)
    if qualifier is False:raise ValueError('exact sourced Planter capability required')
    selected,common=P.variant(rules,planter_policy)
    binding={'source':SOURCE,'holder_id':actor.entity_id,'capability':capability,
             'restriction':qualifier,'planter_policy':planter_policy}
    from cultivation_growth import native_fertilizer
    crop=P.plant_crop(rules,species,plant_identity)
    value={'id':'native:planter:'+species,'source':SOURCE,'species':species,
        'seed':{'item_id':P.item_source(rules,species,plant_identity),'key':key,'count':1},'requirements':[],
        'site':{'kind':KIND,'capacity':1,'tool':None,'max_owned':None,'soil_bonus':common['soil_quality_bonus'],
                'protected':common['protected_from_environment'],'require_soft_soil':False,'capability':binding},
        'maturity':{'clock':'sessions' if selected['maturity_sessions'] is not None else 'seconds',
                    'amount':selected['maturity_sessions'] or selected['maturity_seconds']},
        'fertilizer':native_fertilizer(),'native_variant':'capability-planter'}
    if plant_identity is not None:value['plant_identity']=deepcopy(plant_identity)
    if crop.get('harvest_policy')=='pending':value['maturity']={'clock':'pending','amount':None}
    return value


def validate(actor,value,*,engine=None):
    _holder(actor)
    binding=value['site'].get('capability')
    Q._fields(binding,('source','holder_id','capability','restriction','planter_policy'))
    if binding['source']!=SOURCE or binding['holder_id']!=actor.entity_id:raise ValueError('Planter site must belong to its actual Pokemon holder')
    expected=definition(actor.r,actor,value['species'],value['seed']['key'],binding['capability'],binding['planter_policy'],value.get('plant_identity'))
    if value!=expected:raise ValueError('Planter restriction or inherited source policy changed')
    crop=P.plant_crop(actor.r,value['species'],value.get('plant_identity'))
    if not permits(binding['restriction'],value['species'],crop['kind']):raise ValueError('retained Planter qualifier rejects its plant')
    if actor.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Planter source changed')
    verified_source(actor.r,REFERENCE,label='Planter')
    if engine is not None:
        import state_grants as GRANTS
        select(engine,actor,value['species'],crop)
        if binding['capability'] not in GRANTS.effective_capabilities(actor):raise ValueError('actual current Planter qualifier required')
    return binding


def native(engine,actor,*,species,plant_id,planter_policy):
    """Use the existing staged plant producer; no trainer, Green Thumb or tool."""
    import cultivation_growth as GROWTH,state_grants as GRANTS,world_entities as WORLD
    WORLD.require_actors(engine,actor)
    def commit(e,c):
        crop=P.plant_crop(e.r,species);name,_=select(e,c,species,crop)
        import crafting_activities as A
        key=A._inventory(c,species,1)
        value=definition(e.r,c,species,key,name,planter_policy)
        return GROWTH._plant_staged(e,c,value,plant_id=plant_id,site_id=site_id(c),reason='actual Planter capability planting')
    return GRANTS.transition(engine,actor,commit)


def ensure_site(engine,actor,value,sid):
    import world_entities as WORLD
    validate(actor,value,engine=engine)
    if sid!=site_id(actor):raise ValueError('one actor-bound Planter site; changing site IDs cannot add spaces')
    existing=getattr(engine,'_physical_objects',{}).get(sid)
    binding=value['site']['capability']
    if existing is None:
        WORLD.register_object(engine,sid,location={'kind':'unknown'},reason='actual Pokemon innate Planter space',owner_id=actor.entity_id,source=SOURCE)
        engine._physical_objects[sid]['growth_site']={'owner_id':actor.entity_id,'capacity':1,'soil_quality':0,
            'soft_soil':False,'allows_growth':None,'reason':'actual Pokemon innate Planter space','capability':deepcopy(binding)}
    elif existing.get('growth_site',{}).get('capability')!=binding:
        raise ValueError('occupied innate Planter space retains its admitted source qualifier')
