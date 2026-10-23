"""Data-authored growth on actual sites, seeds and the existing world clocks.

Waiting for growth is world time, not active crafting work. Native crop yields
and acquisition policies remain in their existing adapters.
"""
from copy import deepcopy
import hashlib,json
import common_checks as C,crafting_recipes as Q,world_entities as W
import cultivation_state as P


import resolution_transaction as _FINGERPRINTS

def _digest(value):
    try:return _FINGERPRINTS.json_fingerprint(value, sort_keys=True, compact=True, allow_nan=False)
    except (TypeError,ValueError) as exc:raise ValueError('serializable growth declaration required') from exc


def fertilizer(value):
    Q._fields(value,('item_id','count','delta','soil_cap','clock','duration'))
    Q._text(value['item_id'])
    if not value['item_id'].startswith('item/'):raise ValueError('actual fertilizer item identity required')
    for key in ('count','delta','duration'):C.integer(value[key],'fertilizer '+key,1)
    C.integer(value['soil_cap'],'fertilizer soil cap')
    if value['clock'] not in ('day','seconds','sessions'):raise ValueError('explicit fertilizer lifetime clock required')
    return deepcopy(value)


def native_fertilizer():
    return {'item_id':P.MULCH,'count':1,'delta':1,'soil_cap':2,'clock':'day','duration':1}


def declaration(value):
    keys=('id','source','species','seed','requirements','site','maturity','fertilizer','native_variant')
    Q._fields(value,keys+('plant_identity',) if type(value) is dict and 'plant_identity' in value else keys)
    for key in ('id','source','species'):Q._text(value[key])
    Q._fields(value['seed'],('item_id','key','count'))
    Q._text(value['seed']['item_id']);Q._text(value['seed']['key']);C.integer(value['seed']['count'],'actual seed count',1,1)
    if type(value['requirements']) is not list or not value['requirements'] and value['site'].get('kind')!='capability_planter':raise ValueError('actual growth permission declarations required')
    seen=set()
    for row in value['requirements']:
        Q._fields(row,('id','condition','reason'));Q._text(row['id']);Q._text(row['reason']);Q._condition(row['condition'])
        if row['id'] in seen:raise ValueError('distinct growth requirements required')
        seen.add(row['id'])
    site=value['site'];site_keys=('kind','capacity','tool','max_owned','soil_bonus','protected','require_soft_soil')
    Q._fields(site,site_keys+('capability',) if site.get('kind')=='capability_planter' else site_keys)
    if site['kind'] not in ('outdoor','planter','capability_planter'):raise ValueError('explicit cultivation site kind required')
    C.integer(site['capacity'],'site plant capacity',1);C.integer(site['soil_bonus'],'site soil contribution')
    for key in ('protected','require_soft_soil'):
        if type(site[key]) is not bool:raise ValueError('explicit site condition required')
    if site['max_owned'] is not None:C.integer(site['max_owned'],'owned planter limit',1)
    if site['kind']=='planter':
        Q._fields(site['tool'],('item_id','key'));Q._text(site['tool']['item_id']);Q._text(site['tool']['key'])
        if not site['tool']['item_id'].startswith('item/'):raise ValueError('actual planter source required')
    elif site['tool'] is not None or site['max_owned'] is not None:raise ValueError('outdoor site cannot invent a planter')
    maturity=value['maturity'];Q._fields(maturity,('clock','amount'))
    if maturity['clock']=='pending':
        if maturity['amount'] is not None or 'plant_identity' not in value:raise ValueError('identified plant and explicit pending maturity policy required')
    else:
        if maturity['clock'] not in ('seconds','sessions'):raise ValueError('explicit growth maturity clock required')
        C.integer(maturity['amount'],'growth maturity interval',1)
    fertilizer(value['fertilizer'])
    if value['native_variant'] not in (None,'outdoor-native','book-literal','sheet-current','capability-planter'):raise ValueError('retained native planter variant required')
    if (value['native_variant']=='capability-planter')!=(site['kind']=='capability_planter'):raise ValueError('innate Planter source and typed site must agree')
    _digest(value)
    return deepcopy(value)


def observe_site(engine,actor,site_id,*,capacity,soil_quality,soft_soil,allows_growth,reason,location=None,tool=None):
    W.require_actors(engine,actor);Q._text(site_id);Q._text(reason)
    C.integer(capacity,'observed site capacity',1);C.integer(soil_quality,'observed soil quality')
    if type(soft_soil) is not bool or type(allows_growth) is not bool:raise ValueError('explicit actual site environment required')
    if tool is not None:
        Q._fields(tool,('item_id','key','slot'));Q._text(tool['item_id']);Q._text(tool['key']);C.integer(tool['slot'],'actual planter observation slot',0)
        Q._selected(engine,tool['item_id']);Q._item_key(engine,tool['key'],tool['item_id'])
        C.integer(actor.spec.get('items',{}).get(tool['key']),'actual observed planter count',tool['slot']+1)
    import state_grants as G
    def commit(e,c):
        old=getattr(e,'_physical_objects',{}).get(site_id)
        if old and old.get('growth_site',{}).get('capability') is not None:raise ValueError('innate Planter space cannot be replaced by a GM outdoor/tool site')
        if old and (old.get('growth_site',{}).get('owner_id')!=c.entity_id or 'growth' in old):raise ValueError('existing site identity/ownership cannot change')
        occupied=[p for a in W.actor_index(e).values() for p in a.spec.get('plants',{}).values() if p.get('growth',{}).get('site_id')==site_id]
        if len(occupied)>capacity:raise ValueError('observed site capacity cannot discard existing plants')
        if old:
            W.require_usable_object(old)
            if location is not None:W.observe_location(e,site_id,location,reason=reason)
        else:
            W.register_object(e,site_id,location=location or {'kind':'unknown'},reason=reason,owner_id=c.entity_id)
            old=e._physical_objects[site_id]
        retained=old.get('growth_site',{}).get('tool')
        if retained is not None and tool is not None and retained!=tool:raise ValueError('actual planter identity cannot change')
        old['growth_site']={'owner_id':c.entity_id,'capacity':capacity,'soil_quality':soil_quality,'soft_soil':soft_soil,'allows_growth':allows_growth,'reason':reason}
        if tool is not None or retained is not None:old['growth_site']['tool']=deepcopy(tool or retained)
        validate_world(e,W.actor_index(e))
        return deepcopy(old)
    return G.transition(engine,actor,commit)


def _site(engine,actor,value,site_id,slot):
    import physical_planter as PHYSICAL
    if value['site']['kind']=='capability_planter':
        import planter_capability as PLANTER
        PLANTER.ensure_site(engine,actor,value,site_id)
    obj=getattr(engine,'_physical_objects',{}).get(site_id,{})
    W.require_usable_object(obj)
    observed=obj.get('growth_site')
    if type(observed) is not dict or observed.get('owner_id')!=actor.entity_id:raise ValueError('actual owned cultivation site required')
    PHYSICAL.admit(engine,actor,value,site_id)
    site=value['site']
    if observed['capacity']<site['capacity']:raise ValueError('declared capacity exceeds actual site')
    if site['require_soft_soil'] and not observed['soft_soil']:raise ValueError('actual suitable soft soil required')
    if site['kind']=='planter':
        C.integer(slot,'actual planter unit',0)
        tool=site['tool'];Q._selected(engine,tool['item_id']);Q._item_key(engine,tool['key'],tool['item_id'])
        count=C.integer(actor.spec.get('items',{}).get(tool['key']),'actual owned planters',slot+1)
        if site['max_owned'] is not None and count>site['max_owned']:raise ValueError('declared planter ownership limit exceeded')
        identity={'item_id':tool['item_id'],'key':tool['key'],'slot':slot}
        if observed.get('tool')!=identity:raise ValueError('actual site is not the selected owned planter unit')
    elif slot is not None:raise ValueError('outdoor site has no planter slot')
    occupants=[p for a in W.actor_index(engine).values() for p in a.spec.get('plants',{}).values() if p.get('growth',{}).get('site_id')==site_id and PHYSICAL.RELEASE not in p]
    if any(p['growth']['definition']['site']!=site for p in occupants):raise ValueError('occupied cultivation site cannot change its source policy')
    if len(occupants)>=site['capacity']:raise ValueError('actual cultivation site is full')
    return obj,observed


def plant(engine,actor,value,*,plant_id,site_id,slot=None,reason):
    W.require_actors(engine,actor)
    import state_grants as G
    return G.transition(engine,actor,lambda e,c:_plant_staged(e,c,value,plant_id=plant_id,site_id=site_id,slot=slot,reason=reason))


def _plant_staged(e,c,value,*,plant_id,site_id,slot=None,reason):
    """Plant in the caller's staged graph, including the actual seed payment."""
    W.require_actors(e,c)
    Q._text(plant_id);Q._text(site_id);Q._text(reason);value=declaration(value)
    validate_world(e,W.actor_index(e));P.validate(c)
    if e.encounter_active:raise ValueError('growth planting requires its outside-combat procedure')
    if plant_id in W.entity_index(e) or any(plant_id in a.spec.get('plants',{}) for a in W.actor_index(e).values()):raise ValueError('plant identity already exists')
    Q._selected(e,value['source']);Q._selected(e,value['seed']['item_id'])
    for row in value['requirements']:
        if not Q._observe(e,c,row['condition'],set()):raise ValueError(row['reason'])
    obj,observed=_site(e,c,value,site_id,slot)
    if value['maturity']['clock']=='sessions' and not e.session_frequency:raise ValueError('growth requires an enabled actual session clock')
    identity=value.get('plant_identity')
    expected=P.plant_crop(e.r,value['species'],identity);uid=P.item_source(e.r,value['species'],identity)
    seed=value['seed']
    alias=P.policy(e.r,'cultivation')['herbs'].get(value['species'],{}).get('source_name')
    if seed['item_id']!=uid:raise ValueError('seed does not identify the selected plant species')
    if uid!=P.SOURCE:
        if seed['key']!=alias:Q._item_key(e,seed['key'],uid)
    elif seed['key']!=value['species']:raise ValueError('actual named plant seed identity required')
    before=C.integer(c.spec.get('items',{}).get(seed['key']),'actual owned seed count',1)
    c.spec['items'][seed['key']]=before-1
    native=value['native_variant'];protected=value['site']['kind']=='planter'
    row={'id':plant_id,'berry':value['species'],'crop':expected,'planter_slot':slot if protected and native else None,
         'planter_policy':native if protected and native else None,'soft_soil':observed['soft_soil'],
         'planted_at':e.elapsed_seconds,'planted_session':e.session_epoch,'last_harvest_day':None,'history_start_day':None,'harvest_history':[],
         'provenance':{'origin':'planted','source':P.SOURCE,'item_source':uid,'inventory_key':seed['key'],'seed_count':1},
         'growth':{'owner_id':c.entity_id,'site_id':site_id,'slot':slot,'definition':value,'definition_sha256':_digest(value),'reason':reason,
                   'seed_payment':dict(item_id=seed['item_id'],key=seed['key'],count=1,before=before,after=before-1)}}
    W.register_object(e,plant_id,location={'kind':'unknown'},reason=reason,owner_id=c.entity_id,source=value['source'])
    body=e._physical_objects[plant_id];body.update(row);c.spec.setdefault('plants',{})[plant_id]=body
    import physical_planter as PHYSICAL
    PHYSICAL.attach(e,body,obj)
    P.validate(c);validate_world(e,W.actor_index(e))
    return {'activity':'plant_berry','plant':deepcopy(body)}


def native_plant(engine,actor,*,berry,plant_id,planter_slot=None,planter_policy=None,soft_soil=False):
    if actor.kind=='pokemon':
        if planter_slot is not None or soft_soil is not False:raise ValueError('innate Planter does not use a physical planter slot or outdoor soil')
        import planter_capability as PLANTER
        return PLANTER.native(engine,actor,species=berry,plant_id=plant_id,planter_policy=planter_policy)
    import crafting_activities as A,state_grants as G
    def commit(e,c):
        helper=A._p();helper._trainer(c);helper._outside(e);helper._feature(e,c,'green_thumb')
        berry_name='힘의뿌리' if berry=='힘의 뿌리' else berry
        crop=A._crop(e,c,berry_name);key=A._inventory(c,berry_name,1)
        if type(soft_soil) is not bool:raise ValueError('explicit soft-soil site condition required')
        source,aliases,skills=helper.FEATURES['green_thumb']
        requirements=[{'id':'gardener','condition':{'kind':'owned','fields':['edges'],'names':[source,*aliases]},'reason':'actual acquired Green Thumb required'},
                      {'id':'rank','condition':{'kind':'any','conditions':[{'kind':'skill','skill':s,'rank':r,'effective':False} for s,r in skills]},'reason':'actual Green Thumb skill rank required'}]
        if planter_slot is not None:
            C.integer(planter_slot,'actual planter slot',0);selected,common=P.variant(e.r,planter_policy)
            import physical_planter as PHYSICAL
            site_id=PHYSICAL.native_site(e,c,planter_slot,planter_policy);native=planter_policy
            actual=getattr(e,'_physical_objects',{}).get(site_id,{})
            tool=actual[PHYSICAL.KEY]['key'] if PHYSICAL.KEY in actual else helper._tool(c,'나무열매플랜터')
            site={'kind':'planter','capacity':selected['capacity_per_planter'],'tool':{'item_id':P.PLANTER,'key':tool},'max_owned':selected['max_owned'],'soil_bonus':common['soil_quality_bonus'],'protected':common['protected_from_environment'],'require_soft_soil':False}
            maturity={'clock':'sessions' if selected['maturity_sessions'] is not None else 'seconds','amount':selected['maturity_sessions'] or selected['maturity_seconds']}
        else:
            if not soft_soil:raise ValueError('Green Thumb requires a planter or suitable soft soil')
            site={'kind':'outdoor','capacity':1,'tool':None,'max_owned':None,'soil_bonus':1,'protected':False,'require_soft_soil':True}
            maturity={'clock':'seconds','amount':P.policy(e.r,'cultivation')['maturity_seconds']}
            site_id=c.entity_id+':growth-site:'+plant_id;native='outdoor-native'
        seed_id=P.item_source(e.r,berry_name)
        value={'id':'native:growth:'+berry_name,'source':P.SOURCE,'species':berry_name,'seed':{'item_id':seed_id,'key':key,'count':1},
               'requirements':requirements,'site':site,'maturity':maturity,'fertilizer':native_fertilizer(),'native_variant':native}
        if site_id not in getattr(e,'_physical_objects',{}):
            W.register_object(e,site_id,location={'kind':'unknown'},reason='native explicit planter or soft-soil observation',owner_id=c.entity_id,source=P.SOURCE)
            e._physical_objects[site_id]['growth_site']={'owner_id':c.entity_id,'capacity':site['capacity'],'soil_quality':0,'soft_soil':soft_soil,'allows_growth':None,'reason':'native explicit planter or soft-soil observation'}
            if site['tool']:e._physical_objects[site_id]['growth_site']['tool']={'item_id':P.PLANTER,'key':tool,'slot':planter_slot}
        return _plant_staged(e,c,value,plant_id=plant_id,site_id=site_id,slot=planter_slot,reason='actual native planting')
    return G.transition(engine,actor,commit)


def validate_stored(actor,plant):
    import physical_planter as PHYSICAL
    PHYSICAL.validate_retained(plant)
    row=plant.get('growth')
    if row is None:return
    value=declaration(row.get('definition'))
    if row.get('definition_sha256')!=_digest(value) or row.get('owner_id')!=actor.entity_id:raise ValueError('growth declaration and actual owner disagree')
    if value['species']!=plant['berry'] or value['seed']['key']!=plant['provenance']['inventory_key']:raise ValueError('actual seed and plant declaration disagree')
    native=value['native_variant']
    if native=='capability-planter':
        import planter_capability as PLANTER
        PLANTER.validate(actor,value)
        if row.get('site_id')!=PLANTER.site_id(actor) or row.get('slot') is not None:raise ValueError('retained innate Planter holder/site changed')
    if native in ('book-literal','sheet-current'):
        if plant.get('planter_slot')!=row.get('slot') or plant.get('planter_policy')!=native:raise ValueError('native planter fields disagree with the actual growth site')
    elif plant.get('planter_slot') is not None or plant.get('planter_policy') is not None:raise ValueError('declared growth cannot invent a legacy planter policy')
    Q._text(row.get('site_id'));Q._text(row.get('reason'))
    if actor.r._selected_rule(value['source'])!=value['source']:raise ValueError('selected growth source changed')
    paid=row.get('seed_payment',{})
    before=C.integer(paid.get('before'),'seed balance before',1)
    if paid!=dict(item_id=value['seed']['item_id'],key=value['seed']['key'],count=1,before=before,after=before-1):raise ValueError('actual one-unit seed payment required')


def validate_world(engine,index):
    import physical_planter as PHYSICAL
    PHYSICAL.validate_world(engine)
    objects=getattr(engine,'_physical_objects',{});seen=set();sites={};units=set();holders=set()
    for obj in objects.values():
        observed=obj.get('growth_site')
        if observed is None:continue
        if type(observed) is not dict or observed.get('owner_id') not in index:raise ValueError('actual cultivation site owner required')
        if obj.get('owner_id')!=observed['owner_id']:raise ValueError('cultivation site body and owner observation disagree')
        C.integer(observed.get('capacity'),'actual cultivation site capacity',1);C.integer(observed.get('soil_quality'),'actual cultivation soil')
        if type(observed.get('soft_soil')) is not bool or observed.get('allows_growth') is not None and type(observed['allows_growth']) is not bool:raise ValueError('actual site condition observations required')
        Q._text(observed.get('reason'))
        if 'capability' in observed:
            import planter_capability as PLANTER
            holder=index[observed['owner_id']]
            binding=observed['capability']
            Q._fields(binding,('source','holder_id','capability','restriction','planter_policy'))
            if holder.kind!='pokemon' or binding['holder_id']!=holder.entity_id or binding['source']!=PLANTER.SOURCE or PLANTER.restriction(binding['capability']) is False or binding['restriction']!=PLANTER.restriction(binding['capability']):raise ValueError('actual Pokemon innate Planter binding required')
            if engine.r._selected_rule(PLANTER.SOURCE)!=PLANTER.SOURCE:raise ValueError('selected innate Planter source changed')
            PLANTER.verified_source(engine.r,PLANTER.REFERENCE,label='Planter')
            if obj.get('id')!=PLANTER.site_id(holder) or holder.entity_id in holders or observed['capacity']!=1 or observed.get('tool') is not None:raise ValueError('one innate Planter space per actual Pokemon')
            holders.add(holder.entity_id)
        tool=observed.get('tool')
        if tool is not None:
            if PHYSICAL.KEY in obj and PHYSICAL.terminal(obj):continue
            Q._fields(tool,('item_id','key','slot'));C.integer(tool['slot'],'actual planter unit',0)
            owner=index[observed['owner_id']]
            Q._selected(engine,tool['item_id']);Q._item_key(engine,tool['key'],tool['item_id'])
            C.integer(owner.spec.get('items',{}).get(tool['key']),'actual observed planter ownership',tool['slot']+1)
            identity=(observed['owner_id'],tool['item_id'],tool['slot'])
            if identity in units:raise ValueError('one actual planter unit cannot create two cultivation sites')
            units.add(identity)
    for actor in index.values():
        for pid,plant in actor.spec.get('plants',{}).items():
            if 'growth' not in plant:continue
            validate_stored(actor,plant)
            if pid in seen or objects.get(pid) is not plant:raise ValueError('one actual plant body per identity required')
            if plant.get('owner_id')!=actor.entity_id or plant.get('kind')!='physical_object':raise ValueError('actual plant body and owner disagree')
            seen.add(pid);W.require_present_object(plant)
            row=plant['growth'];value=row['definition'];sid=row['site_id']
            site=objects.get(sid,{}).get('growth_site',{})
            if site.get('owner_id')!=actor.entity_id:raise ValueError('actual growth site owner missing')
            C.integer(site.get('capacity'),'actual cultivation site capacity',1)
            if value['site']['capacity']>site['capacity']:raise ValueError('growth capacity exceeds its actual site')
            if value['site']['kind']=='capability_planter' and site.get('capability')!=value['site']['capability']:raise ValueError('actual Planter site and retained plant qualifier disagree')
            if value['site']['kind']!='capability_planter' and site.get('capability') is not None:raise ValueError('innate Planter space requires its actual capability admission')
            if plant['planted_at']>engine.elapsed_seconds or plant['planted_session']>engine.session_epoch:raise ValueError('planting cannot precede an invented world clock')
            if value['site']['kind']=='planter' and PHYSICAL.RELEASE not in plant and not (PHYSICAL.KEY in objects.get(sid,{}) and PHYSICAL.terminal(objects[sid])):
                slot=C.integer(row['slot'],'actual retained planter unit',0);tool=value['site']['tool']
                if site.get('tool')!=dict(item_id=tool['item_id'],key=tool['key'],slot=slot):raise ValueError('growth site lost its actual planter unit')
                count=C.integer(actor.spec.get('items',{}).get(tool['key']),'actual retained planter count',slot+1)
                if value['site']['max_owned'] is not None and count>value['site']['max_owned']:raise ValueError('retained planter ownership limit exceeded')
            for application in plant.get('mulch_applications',[]):
                paid=application.get('payment',{})
                if paid.get('kind')=='held_instance':
                    used=objects.get(paid.get('instance_id'),{}).get('consumed',{})
                    if used.get('by_actor_id')!=actor.entity_id or used.get('at')!=application.get('applied_at'):raise ValueError('actual physical fertilizer payment missing')
            if PHYSICAL.RELEASE not in plant:sites.setdefault(sid,[]).append(plant)
    for sid,plants in sites.items():
        basis=plants[0]['growth']['definition']['site']
        if len(plants)>basis['capacity'] or any(p['growth']['definition']['site']!=basis for p in plants):raise ValueError('shared site capacity or retained source policy changed')
    for pid,obj in objects.items():
        if 'growth' in obj and pid not in seen:raise ValueError('unowned or copied actual plant body')
    return True


def mature_at(plant,at,session):
    value=plant['growth']['definition']['maturity']
    if value['clock']=='pending':return False
    current=at if value['clock']=='seconds' else session
    start=plant['planted_at'] if value['clock']=='seconds' else plant['planted_session']
    return current-start>=value['amount']


def status(engine,actor,plant_id,*,environment_allows_growth=None,soil_quality=None):
    W.require_actors(engine,actor);P.validate(actor);validate_world(engine,W.actor_index(engine))
    plant=actor.spec.get('plants',{}).get(plant_id)
    if not plant or 'growth' not in plant:raise ValueError('actual declared growth plant required')
    W.require_usable_object(plant)
    if any(W.physical_lifecycle(plant).values()):raise ValueError('actual plant is unavailable for growth')
    row=plant['growth'];value=row['definition'];site=engine._physical_objects[row['site_id']]
    import physical_planter as PHYSICAL
    released=PHYSICAL.released_context(plant,environment_allows_growth,soil_quality)
    if released is None:
        W.require_usable_object(site)
        if any(W.physical_lifecycle(site).values()):raise ValueError('actual site is unavailable for growth')
    observed=site['growth_site'];environment=released['environment'] if released is not None else observed['allows_growth'] if environment_allows_growth is None else environment_allows_growth
    protected=False if released is not None else value['site']['protected']
    if not protected and type(environment) is not bool:raise ValueError('actual growing environment observation required')
    if soil_quality is not None:C.integer(soil_quality,'observed growing soil')
    base=released['soil'] if released is not None else 0 if value['site']['kind'] in ('planter','capability_planter') else observed['soil_quality'] if soil_quality is None else soil_quality
    site_bonus=int(released['soft_soil']) if released is not None else value['site']['soil_bonus']
    removal={} if released is None else {'physical_planter_release':released['release']}
    import crafting_activities as A
    day=A._day(actor);bonus,applications=soil_bonus(plant,base+site_bonus,day,engine.elapsed_seconds,engine.session_epoch)
    if value['maturity']['clock']=='pending':
        return {'plant_id':plant_id,'site_id':row['site_id'],'mature':None,'clock':'pending','remaining':None,
            'environment_allows_growth':environment,'protected':protected,'ready':False,
            'soil_base':base,'site_bonus':site_bonus,'fertilizer_bonus':bonus,'fertilizer_applications':applications,
            'soil_quality':base+site_bonus+bonus,
            'pending':'species maturity duration and harvest yield/period require an explicit reviewed source policy'} | removal
    clock=value['maturity']['clock'];now=engine.elapsed_seconds if clock=='seconds' else engine.session_epoch
    start=plant['planted_at'] if clock=='seconds' else plant['planted_session']
    mature=mature_at(plant,engine.elapsed_seconds,engine.session_epoch)
    soil_allows=True if released is not None else not value['site']['require_soft_soil'] or observed['soft_soil']
    return {'plant_id':plant_id,'site_id':row['site_id'],'mature':mature,'clock':clock,'remaining':max(0,start+value['maturity']['amount']-now),
            'environment_allows_growth':environment,'protected':protected,'ready':mature and soil_allows and (protected or environment),
            'soil_base':base,'site_bonus':site_bonus,'fertilizer_bonus':bonus,'fertilizer_applications':applications,
            'soil_quality':base+site_bonus+bonus} | removal


def _active(row,day,at,session):
    value=row.get('growth_policy',native_fertilizer());clock=value['clock']
    if clock=='day':current,start=day,row['day']
    elif clock=='seconds':current,start=at,row['applied_at']
    else:current,start=session,row['applied_session']
    if current is None:raise ValueError('actual fertilizer lifetime clock required')
    return start<=current<start+value['duration']


def soil_bonus(plant,soil,day,at=None,session=None):
    rows=[r for r in plant.get('mulch_applications',[]) if _active(r,day,at,session)]
    value=plant.get('growth',{}).get('definition',{}).get('fertilizer',native_fertilizer())
    return min(sum(r.get('growth_policy',native_fertilizer())['delta'] for r in rows),max(0,value['soil_cap']-soil)),[r['sequence'] for r in rows]


def validate_fertilizers(actor,plant):
    rows=plant.get('mulch_applications',[])
    if type(rows) is not list:raise ValueError('identified fertilizer application records required')
    for seq,row in enumerate(rows,1):
        if type(row) is not dict:raise ValueError('actual fertilizer application record required')
        C.integer(row.get('sequence'),'actual fertilizer sequence',seq,seq)
        value=fertilizer(row.get('growth_policy',native_fertilizer()))
        ability=row.get('ability_application')
        if row.get('sequence')!=seq:raise ValueError('fertilizer source/sequence mismatch')
        if ability is None:
            if row.get('source')!=value['item_id']:raise ValueError('fertilizer source/sequence mismatch')
            if actor.r._selected_rule(value['item_id'])!=value['item_id']:raise ValueError('selected fertilizer source changed')
        else:
            if type(ability) is not dict or set(ability)!={'source','provider_id','activation_sequence'} or ability.get('source')!='ability/정원사' or row.get('source')!=ability['source']:
                raise ValueError('Gardener fertilizer provenance required')
            if not isinstance(ability.get('provider_id'),str) or not ability['provider_id'] or type(ability.get('activation_sequence')) is not int or ability['activation_sequence']<1:
                raise ValueError('Gardener provider/activation identity required')
            if actor.r._selected_rule(ability['source'])!=ability['source']:raise ValueError('selected Gardener source changed')
        for key in ('day','soil_base','site_bonus','before_soil','after_soil'):C.integer(row.get(key),'fertilizer '+key,0 if key=='day' else None)
        if 'growth_policy' in row:
            C.integer(row.get('applied_at'),'actual fertilizer application time',plant['planted_at'])
            C.integer(row.get('applied_session'),'actual fertilizer application session',plant['planted_session'])
            expected=plant.get('growth',{}).get('definition',{}).get('fertilizer',native_fertilizer())
            if value!=expected:raise ValueError('fertilizer cannot replace its retained plant policy')
        prior=dict(plant,mulch_applications=rows[:seq-1]);soil=row['soil_base']+row['site_bonus']
        bonus,_=soil_bonus(prior,soil,row['day'],row.get('applied_at'),row.get('applied_session'))
        if row['before_soil']!=soil+bonus or row['after_soil']!=row['before_soil']+value['delta'] or row['after_soil']>value['soil_cap']:raise ValueError('fertilizer must respect its actual source and soil cap')
        Q._text(row.get('reason'))
        expected_timing='ability-current-day' if ability is not None else ('selected-korean-current-day' if value==native_fertilizer() else 'declared-growth-clock')
        if row.get('timing_policy')!=expected_timing:raise ValueError('explicit fertilizer timing policy required')
        paid=row.get('payment',{})
        if ability is None:
            if paid.get('item_id')!=value['item_id'] or C.integer(paid.get('count'),'actual fertilizer count',1)!=value['count']:raise ValueError('actual fertilizer payment required')
        else:
            expected={'kind':'ability','source':ability['source'],'actor_id':ability['provider_id'],'count':0,'at':row.get('applied_at')}
            if paid!=expected:raise ValueError('actual Gardener payment required')
    return rows


def fertilize(engine,actor,plant_id,*,soil_quality=0,reason,held_selection=None):
    W.require_actors(engine,actor);Q._text(reason);C.integer(soil_quality,'observed growing soil')
    import state_grants as G,item_stock as STOCK,crafting_activities as A
    def commit(e,c):
        plants=P.validate(c);validate_world(e,W.actor_index(e))
        if plant_id not in plants:raise ValueError('actual identified plant required')
        plant=plants[plant_id];value=plant.get('growth',{}).get('definition',{}).get('fertilizer',native_fertilizer())
        import physical_planter as PHYSICAL
        PHYSICAL.require_access(e,c,plant)
        Q._selected(e,value['item_id'])
        if 'growth' in plant:
            observed=status(e,c,plant_id,environment_allows_growth=True,soil_quality=soil_quality)
            base,site,bonus=observed['soil_base'],observed['site_bonus'],observed['fertilizer_bonus']
        else:
            site=P.variant(c.r,plant['planter_policy'])[1]['soil_quality_bonus'] if plant['planter_slot'] is not None else int(plant['soft_soil'])
            base=0 if plant['planter_slot'] is not None else soil_quality
            bonus,_=soil_bonus(plant,base+site,A._day(c),e.elapsed_seconds,e.session_epoch)
        before=base+site+bonus
        if before+value['delta']>value['soil_cap']:raise ValueError('fertilizer cannot exceed its declared soil quality cap')
        stock=STOCK.prepare(e,c,value['item_id'],count=value['count'],held_selection=held_selection);paid=STOCK.debit(e,c,stock)
        rows=plant.setdefault('mulch_applications',[])
        row={'source':value['item_id'],'sequence':len(rows)+1,'day':A._day(c),'soil_base':base,'site_bonus':site,'before_soil':before,'after_soil':before+value['delta'],
             'timing_policy':'selected-korean-current-day' if value==native_fertilizer() else 'declared-growth-clock','reason':reason,'payment':deepcopy(paid),
             'growth_policy':deepcopy(value),'applied_at':e.elapsed_seconds,'applied_session':e.session_epoch}
        rows.append(row);P.validate(c);validate_world(e,W.actor_index(e));e.gm._rec('fertilizer application',before,row['after_soil'],reason,c)
        return deepcopy(row)
    return G.transition(engine,actor,commit)

