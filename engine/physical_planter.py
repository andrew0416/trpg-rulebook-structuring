"""C09-047: one actual Portable Grower, its plant and current benefits.

Growth clocks, seed payment, yields, fertilizer and item acquisition retain
their existing owners. Removal records an observation, never a new planting.
"""
from copy import deepcopy
import common_checks as C
import cultivation_state as P
import crafting_recipes as Q
import resolution_transaction as TX
import state_grants as GRANTS
import world_entities as W
from source_context import verified_source

ITEM=P.PLANTER
KEY='physical_planter'
RELEASE='physical_planter_release'
REFERENCE={'file':'input/ch09-equipment.md','sha256':'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'}
SHEET={'file':'input/db/inventory.csv','sha256':'e3e6d81649d8d12ae1e610db838e6ea615c077cd634c682429042c545b3bd3f4'}


def _signature(row):return TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'})


def _source(engine,policy):
    Q._selected(engine,ITEM);verified_source(engine.r,REFERENCE,label='physical Portable Grower')
    if policy=='sheet-current':verified_source(engine.r,SHEET,label='selected Portable Grower sheet')
    return P.variant(engine.r,policy)


def site_definition(engine,key,policy):
    selected,common=_source(engine,policy)
    return {'kind':'planter','capacity':selected['capacity_per_planter'],'tool':{'item_id':ITEM,'key':key},
        'max_owned':selected['max_owned'],'soil_bonus':common['soil_quality_bonus'],
        'protected':common['protected_from_environment'],'require_soft_soil':False}


def _configured(engine,identity):
    obj=getattr(engine,'_physical_objects',{}).get(identity,{})
    if obj.get('id')!=identity or obj.get('kind')!='item_instance' or obj.get('item_rule_id')!=ITEM:
        raise ValueError('actual registered Portable Grower item body required')
    binding=obj.get(KEY)
    if type(binding) is not dict or set(binding)!={'source','owner_id','key','slot','policy','at','reason','sha256'} or binding.get('source')!=ITEM or binding.get('sha256')!=_signature(binding):
        raise ValueError('actual Portable Grower source/body binding required')
    selected,_=_source(engine,binding['policy']);owner=W.actor_index(engine).get(binding['owner_id'])
    if owner is None or obj.get('owner_id')!=owner.entity_id:raise ValueError('actual owned Portable Grower body required')
    Q._item_key(engine,binding['key'],ITEM);C.integer(binding['slot'],'actual Portable Grower slot',0)
    if not terminal(obj):
        count=C.integer(owner.spec.get('items',{}).get(binding['key']),'actual owned Portable Grower count',binding['slot']+1)
        if selected['max_owned'] is not None and count>selected['max_owned']:raise ValueError('selected Portable Grower ownership limit exceeded')
    C.integer(binding['at'],'actual Portable Grower binding time',0,engine.elapsed_seconds);Q._text(binding['reason'])
    expected={'owner_id':owner.entity_id,'capacity':selected['capacity_per_planter'],'soil_quality':0,
        'soft_soil':False,'allows_growth':None,'reason':binding['reason'],
        'tool':{'item_id':ITEM,'key':binding['key'],'slot':binding['slot']}}
    if obj.get('growth_site')!=expected:raise ValueError('actual Portable Grower site/source changed')
    return obj


def _access(engine,actor,obj):
    W.require_actors(engine,actor);W.require_physical_access(obj)
    holder=obj.get('carrier_id') or obj.get('equipped_by')
    if holder is not None:
        if holder!=actor.entity_id:raise ValueError('actual Portable Grower must be physically accessible')
    else:
        distance=W.distance_known(actor,obj)
        if distance is None or distance>1:raise ValueError('actor must physically reach the actual Portable Grower')


def bind(engine,actor,body_id,*,slot,planter_policy,reason):
    """Associate the existing counted tool with its observed individual body."""
    W.require_actors(engine,actor);C.integer(slot,'actual Portable Grower slot',0);Q._text(reason)
    def apply(e,a):
        import item_stock as STOCK,cultivation_growth as G
        selected,_=_source(e,planter_policy)
        stock=STOCK.prepare(e,a,ITEM,count=slot+1)
        if stock['kind']!='quantity':raise ValueError('actual counted Portable Grower unit required')
        key=stock['key'];obj=getattr(e,'_physical_objects',{}).get(body_id,{})
        if obj.get('kind')!='item_instance' or obj.get('item_rule_id')!=ITEM or obj.get('owner_id')!=a.entity_id:
            raise ValueError('actual owned registered Portable Grower item body required')
        _access(e,a,obj)
        if KEY in obj or 'growth_site' in obj:raise ValueError('existing Portable Grower/site binding cannot be replaced')
        if selected['max_owned'] is not None and a.spec['items'][key]>selected['max_owned']:raise ValueError('selected Portable Grower ownership limit exceeded')
        binding={'source':ITEM,'owner_id':a.entity_id,'key':key,'slot':slot,'policy':planter_policy,'at':e.elapsed_seconds,'reason':reason}
        binding['sha256']=_signature(binding);obj[KEY]=binding
        obj['growth_site']={'owner_id':a.entity_id,'capacity':selected['capacity_per_planter'],'soil_quality':0,
            'soft_soil':False,'allows_growth':None,'reason':reason,'tool':{'item_id':ITEM,'key':key,'slot':slot}}
        G.validate_world(e,W.actor_index(e));e.gm._rec('actual Portable Grower '+body_id,None,binding,reason,a)
        return deepcopy(binding)
    return GRANTS.transition(engine,actor,apply,include_rulings=True)


def native_site(engine,actor,slot,policy):
    matches=[obj['id'] for obj in getattr(engine,'_physical_objects',{}).values()
        if obj.get(KEY,{}).get('owner_id')==actor.entity_id and obj[KEY]['slot']==slot and not terminal(obj)]
    if not matches:return actor.entity_id+':planter:'+str(slot)
    if len(matches)!=1:raise ValueError('one actual Portable Grower body per counted unit required')
    obj=_configured(engine,matches[0])
    if obj[KEY]['policy']!=policy:raise ValueError('actual Portable Grower retains its selected source policy')
    return obj['id']


def admit(engine,actor,value,site_id):
    obj=getattr(engine,'_physical_objects',{}).get(site_id,{})
    if KEY not in obj:return
    obj=_configured(engine,site_id);binding=obj[KEY];_access(engine,actor,obj)
    if value['site']!=site_definition(engine,binding['key'],binding['policy']) or value['native_variant']!=binding['policy']:
        raise ValueError('actual Portable Grower declaration must retain selected source policy')
    crop=P.plant_crop(engine.r,value['species'],value.get('plant_identity'))
    if crop['kind'] not in ('berry','herb'):raise ValueError('physical Portable Grower supports Berries or herbs only')
    selected,_=_source(engine,binding['policy'])
    expected={'clock':'pending','amount':None} if crop.get('harvest_policy')=='pending' else {
        'clock':'sessions' if selected['maturity_sessions'] is not None else 'seconds',
        'amount':selected['maturity_sessions'] or selected['maturity_seconds']}
    if value['maturity']!=expected:raise ValueError('actual Portable Grower retains selected species maturity policy')


def attach(engine,plant,site):
    if KEY not in site:return
    plant[KEY]={'source':ITEM,'body_id':site['id'],'policy':site[KEY]['policy'],'at':engine.elapsed_seconds}


def contained(plant):return type(plant) is dict and plant.get('kind')=='physical_object' and type(plant.get('growth')) is dict and KEY in plant and RELEASE not in plant


def terminal(obj):return any(W.physical_lifecycle(obj)[key] for key in ('consumed','destroyed'))


def validate_retained(plant):
    if KEY not in plant:
        if RELEASE in plant:raise ValueError('released plant requires its actual Portable Grower origin')
        return
    link=plant[KEY];growth=plant.get('growth',{})
    if type(link) is not dict or set(link)!={'source','body_id','policy','at'} or link.get('source')!=ITEM or link.get('policy') not in ('book-literal','sheet-current') or link.get('body_id')!=growth.get('site_id') or link.get('policy')!=growth.get('definition',{}).get('native_variant') or link.get('at')!=plant.get('planted_at'):
        raise ValueError('actual Portable Grower source, plant and original growth binding required')
    Q._text(link['body_id']);C.integer(link['at'],'actual Portable Grower planting time',0)
    if RELEASE not in plant:return
    row=plant[RELEASE]
    if type(row) is not dict or set(row)!={'source','body_id','actor_id','at','reason','location','soil_quality','soft_soil','allows_growth','sha256'} or row.get('sha256')!=_signature(row) or row.get('source')!=ITEM or row.get('body_id')!=link.get('body_id'):
        raise ValueError('actual plant removal must retain its Portable Grower source/body evidence')


def validate_plant(engine,plant):
    validate_retained(plant)
    if KEY not in plant:
        if RELEASE in plant:raise ValueError('released plant requires its actual Portable Grower origin')
        return
    link=plant[KEY]
    if type(link) is not dict or set(link)!={'source','body_id','policy','at'} or link.get('source')!=ITEM:
        raise ValueError('actual Portable Grower plant binding required')
    obj=_configured(engine,link['body_id']);binding=obj[KEY];growth=plant['growth']
    if growth['site_id']!=obj['id'] or growth['owner_id']!=binding['owner_id'] or growth['slot']!=binding['slot'] or link['policy']!=binding['policy'] or growth['definition']['site']!=site_definition(engine,binding['key'],binding['policy']):
        raise ValueError('one actual plant, site and Portable Grower source required')
    C.integer(link['at'],'actual Portable Grower planting time',binding['at'],engine.elapsed_seconds)
    if link['at']!=plant['planted_at']:raise ValueError('Portable Grower binding cannot restart actual growth')
    crop=P.plant_crop(engine.r,plant['berry'],growth['definition'].get('plant_identity'))
    selected,_=_source(engine,link['policy'])
    maturity={'clock':'pending','amount':None} if crop.get('harvest_policy')=='pending' else {
        'clock':'sessions' if selected['maturity_sessions'] is not None else 'seconds',
        'amount':selected['maturity_sessions'] or selected['maturity_seconds']}
    if crop['kind'] not in ('berry','herb') or growth['definition']['maturity']!=maturity or growth['definition']['native_variant']!=link['policy']:
        raise ValueError('actual Portable Grower retains its supported plant and selected maturity policy')
    if contained(plant):
        if plant.get('carrier_id') or plant.get('equipped_by'):raise ValueError('contained plant follows its actual Portable Grower body')
        return
    row=plant[RELEASE]
    if type(row) is not dict or set(row)!={'source','body_id','actor_id','at','reason','location','soil_quality','soft_soil','allows_growth','sha256'} or row.get('sha256')!=_signature(row) or row.get('source')!=ITEM or row.get('body_id')!=obj['id'] or row.get('actor_id')!=growth['owner_id']:
        raise ValueError('actual plant removal observation required')
    C.integer(row['at'],'actual Portable Grower removal time',link['at'],engine.elapsed_seconds);Q._text(row['reason'])
    C.integer(row['soil_quality'],'actual released plant soil')
    if type(row['soft_soil']) is not bool or type(row['allows_growth']) is not bool:raise ValueError('actual released plant environment required')
    import state_fields as F
    if F.location(row['location'])!=row['location']:raise ValueError('actual released plant location required')


def validate_world(engine):
    for identity,obj in getattr(engine,'_physical_objects',{}).items():
        if KEY in obj and 'growth' not in obj:_configured(engine,identity)
    for actor in W.actor_index(engine).values():
        for plant in actor.spec.get('plants',{}).values():validate_plant(engine,plant)


def location(engine,plant):
    validate_plant(engine,plant)
    return W.effective_location(engine,_configured(engine,plant[KEY]['body_id']))


def require_access(engine,actor,plant):
    if KEY not in plant:return
    validate_plant(engine,plant)
    _access(engine,actor,_configured(engine,plant[KEY]['body_id']) if contained(plant) else plant)


def remove(engine,actor,plant_id,*,soil_quality,soft_soil,allows_growth,reason):
    """Remove the same organism at the actual body's currently known location."""
    W.require_actors(engine,actor);Q._text(reason);C.integer(soil_quality,'actual released plant soil')
    if type(soft_soil) is not bool or type(allows_growth) is not bool:raise ValueError('actual released plant environment required')
    def apply(e,a):
        import cultivation_growth as G
        plant=a.spec.get('plants',{}).get(plant_id)
        if not contained(plant):raise ValueError('actual owned plant still in a Portable Grower required')
        validate_plant(e,plant);obj=_configured(e,plant[KEY]['body_id']);_access(e,a,obj)
        row={'source':ITEM,'body_id':obj['id'],'actor_id':a.entity_id,'at':e.elapsed_seconds,'reason':reason,
            'location':W.effective_location(e,obj),'soil_quality':soil_quality,'soft_soil':soft_soil,'allows_growth':allows_growth}
        row['sha256']=_signature(row);plant[RELEASE]=row;W._set_object_location(plant,row['location'])
        P.validate(a);G.validate_world(e,W.actor_index(e));e.gm._rec('remove actual plant '+plant_id,obj['id'],row,reason,a)
        return deepcopy(row)
    return GRANTS.transition(engine,actor,apply,include_rulings=True)


def released_context(plant,environment,soil):
    row=plant.get(RELEASE)
    if row is None:return None
    return {'environment':row['allows_growth'] if environment is None else environment,
        'soil':row['soil_quality'] if soil is None else soil,'soft_soil':row['soft_soil'],'release':row['sha256']}


def receipt_site(plant,context,at):
    """Keep pre-removal harvest contexts; later removal cannot rewrite them."""
    row=plant.get(RELEASE);proof=context.get('physical_planter_release')
    if proof is not None:
        if row is None or proof!=row['sha256'] or at<row['at']:raise ValueError('actual removal must precede released-plant harvest')
        return False,int(row['soft_soil'])
    if row is not None and at>row['at']:raise ValueError('removed plant cannot retain old Portable Grower benefits')
    value=plant['growth']['definition']['site']
    return value['protected'],value['soil_bonus']
