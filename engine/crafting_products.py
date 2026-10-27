"""Actual transformation products, maker contributions and physical identities.

Ordinary quantities retain their native transformation proof. A declared
physical output replaces the newly produced quantity; it never adds a copy.
Maker attachments use native owned effects and actual clock/holder lifetimes.
"""
from copy import deepcopy
import resolution_transaction as REQUESTS
import common_checks as C
import crafting_recipes as RECIPES,crafting_resources as R,world_entities as W

KEY='crafting_products'


def _hash(value):
    try:return REQUESTS.json_fingerprint(value,compact=True,allow_nan=False)
    except (TypeError,ValueError) as exc:raise ValueError('serializable crafting declaration required') from exc


def _item_output(operation,options,result=None):
    if operation in ('craft_item','craft_gem'):return True
    if operation!='cook_chef_food':return False
    import chef_cooking as CHEF
    recipe={'vitamin':CHEF.VITAMINS,'meal_planner':CHEF.MEAL_PLANNER}.get(options.get('recipe'))
    return recipe is not None and (result is None or (result.get('chef_recipe')==recipe
        and result.get('recipe_id')=='native:chef:'+recipe.split('/',1)[1] and 'batch_id' not in result))


def policy(value):
    if value is None:return None
    RECIPES._fields(value,('mode','instance_ids','owner_id','state','attachments'))
    if value['mode'] not in ('create','repair') or value['state'] not in ('intact','disabled'):raise ValueError('explicit physical product mode/state required')
    RECIPES._names(value['instance_ids']);RECIPES._text(value['owner_id'])
    if type(value['attachments']) is not list:raise ValueError('maker attachment declarations required')
    import items as I,effects as FX
    identities=set()
    for row in value['attachments']:
        RECIPES._fields(row,('id','source','requirement','effects','seconds','ownership'))
        RECIPES._text(row['id']);RECIPES._text(row['source']);RECIPES._condition(row['requirement'])
        if row['id'] in identities:raise ValueError('distinct maker attachments required')
        identities.add(row['id'])
        if row['seconds'] is not None:C.integer(row['seconds'],'maker contribution lifetime',1)
        if row['ownership'] not in ('any_holder','creator_only','original_owner'):raise ValueError('explicit maker contribution ownership required')
        if type(row['effects']) is not list or not row['effects']:raise ValueError('actual maker effects required')
        for effect in row['effects']:
            if type(effect) is not dict:raise ValueError('typed maker effect required')
            normalized=I.normalize(effect)
            if normalized.get('type') not in FX.PASSIVE_TYPES|{'save_mod','initiative_mod','speed_mod'}:
                raise ValueError('maker attachment needs an existing passive consumer')
            if any(k in effect for k in ('duration','lifetime','while','target','on')):raise ValueError('maker lifetime/recipient uses the attachment declaration')
            for key in ('value','delta'):
                if key in effect:C.integer(effect[key],'maker effect amount')
    if value['mode']=='repair' and (value['attachments'] or value['state']!='intact'):raise ValueError('repair preserves existing maker attachments and restores intact state')
    _hash(value)
    return deepcopy(value)


def preflight(engine,actor,operation,options,product_policy,event_id):
    W.require_actors(engine,actor);validate_world(engine,W.actor_index(engine))
    declared=policy(product_policy)
    if event_id is not None:RECIPES._text(event_id)
    intent={'operation':operation,'options':deepcopy(options),'product_policy':declared}
    digest=_hash(intent)
    for row in actor.spec.get(KEY,{}).values():
        if event_id is not None and row['event_id']==event_id:
            if row['intent_sha256']!=digest:raise ValueError('crafting event cannot change its original request')
            return {'replay':deepcopy(row['transformation']['result'])}
    if declared is not None:
        if not _item_output(operation,options):raise ValueError('this product policy requires a native item output')
        if operation=='cook_chef_food' and declared['mode']!='create':raise ValueError('Chef item outputs require creation, not repair')
        count=C.integer(options.get('count',1),'physical output count',1)
        if len(declared['instance_ids'])!=count:raise ValueError('one physical identity per produced item required')
        index=W.actor_index(engine);owner=index.get(declared['owner_id'])
        if owner is None:raise ValueError('product owner must be an actual registered actor')
        entities=W.entity_index(engine)
        for uid in declared['instance_ids']:
            if declared['mode']=='create':
                if uid in entities:raise ValueError('product identity already exists')
            else:
                obj=getattr(engine,'_physical_objects',{}).get(uid)
                if not obj or obj.get('kind')!='item_instance' or 'crafting_origin' not in obj:raise ValueError('repair requires an actual crafted physical item')
                W.require_usable_object(obj)
                if obj.get('disabled') is not True:raise ValueError('repair requires an actual disabled product')
                if obj.get('owner_id')!=declared['owner_id'] or actor.entity_id not in (obj.get('owner_id'),obj.get('equipped_by'),obj.get('carrier_id')):
                    raise ValueError('repair cannot invent ownership or access')
        for row in declared['attachments']:
            RECIPES._selected(engine,row['source'])
            if not RECIPES._observe(engine,actor,row['requirement'],set()):raise ValueError('actual acquired maker contribution required')
            import effect_contracts as CONTRACTS
            ordinary=[effect for effect in row['effects'] if effect['type'] not in ('save_mod','initiative_mod','speed_mod')]
            if ordinary:CONTRACTS.require(engine,actor,actor,ordinary,row['source'])
    identity=actor.entity_id+':transform-'+str(len(actor.spec.get('resource_transformations',[]))+1)
    return {'id':identity,'event_id':event_id or identity,'intent':intent,'intent_sha256':digest,'policy':declared}


def materialize(engine,actor,result,plan):
    declared=plan['policy'];ids=[];now=engine.elapsed_seconds
    result.update(production_id=plan['id'],product_instance_ids=ids,product_policy=deepcopy(declared))
    if declared is None:return
    count=result['count'];uid=result['item_id'];key=result['item']
    if count!=len(declared['instance_ids']):raise ValueError('physical output quantity changed')
    C.integer(actor.spec['items'].get(key),'new physical output quantity',count)
    actor.spec['items'][key]-=count
    for identity in declared['instance_ids']:
        if declared['mode']=='repair':
            obj=engine._physical_objects[identity]
            if obj['item_rule_id']!=uid:raise ValueError('repair recipe cannot change the product item rule')
            import repair_restore as REPAIR
            REPAIR.restore_item(engine,identity);obj.setdefault('crafting_repairs',[]).append(plan['id'])
        else:
            W.register_object(engine,identity,location={'kind':'unknown'},reason='actual crafted output',kind='item_instance',item_rule_id=uid,owner_id=declared['owner_id'],source=result['recipe_source'])
            obj=engine._physical_objects[identity];obj['disabled']=declared['state']=='disabled'
            obj['crafting_origin']={'production_id':plan['id'],'maker_id':actor.entity_id,'owner_id':declared['owner_id'],'at':now,
                'attachments':[dict(deepcopy(row),ends_at=None if row['seconds'] is None else now+row['seconds']) for row in declared['attachments']]}
        ids.append(identity)


def publish(engine,actor,plan,record):
    rows=actor.spec.setdefault(KEY,{})
    if plan['id'] in rows:raise ValueError('duplicate transformation production identity')
    rows[plan['id']]={'id':plan['id'],'maker_id':actor.entity_id,'event_id':plan['event_id'],
        'intent':plan['intent'],'intent_sha256':plan['intent_sha256'],'transformation':record}
    __import__('study_books').product_created(engine,actor,rows[plan['id']])
    validate_world(engine,W.actor_index(engine))
    if record['operation'] in ('craft_item','craft_gem') or plan['policy'] is not None:
        lineage(engine,actor,plan['id'])
    return rows[plan['id']]


def lineage(engine,actor,production_id):
    import materialization_origins as ORIGIN
    row=actor.spec.get(KEY,{}).get(production_id)
    if row is None or row.get('maker_id')!=actor.entity_id:raise ValueError('actual production owner required')
    native=row['transformation']
    if not any(native is value for value in actor.spec.get('resource_transformations',[])):
        raise ValueError('actual native transformation original required')
    if not _item_output(native['operation'],row['intent']['options'],native['result']):
        raise ValueError('origin view requires an actual crafted or repaired item')
    result=native['result'];declared=result.get('product_policy')
    outputs=list(result.get('product_instance_ids',[]))
    retained=outputs if declared and declared['mode']=='repair' else []
    inputs=list(dict.fromkeys([*retained,*[identity for payment in result.get('materials',[])
                  if payment['kind']=='physical_item' for identity in payment['instances']]]))
    return ORIGIN.describe(kind='repair' if retained else 'craft',source=result['recipe_source'],owner_id=actor.entity_id,
        inputs=inputs,outputs=outputs,retained=list(retained),
        quantities=[{'item_id':result['item_id'],'count':result['count']}],
        native_ref={'kind':'resource_transformation','owner_id':actor.entity_id,'production_id':production_id,'event_id':row['event_id']})


def validate_world(engine,index):
    objects=getattr(engine,'_physical_objects',{});origins={};events=set()
    for actor in index.values():
        R.validate(actor);rows=actor.spec.get(KEY,{})
        if type(rows) is not dict:raise ValueError('identified product ledger required')
        for uid,row in rows.items():
            if type(row) is not dict or row.get('id')!=uid or row.get('maker_id')!=actor.entity_id:raise ValueError('actual product maker identity required')
            RECIPES._text(row.get('event_id'))
            key=(actor.entity_id,row['event_id'])
            if key in events:raise ValueError('one crafting event cannot create two productions')
            events.add(key)
            if row.get('intent_sha256')!=_hash(row.get('intent')):raise ValueError('product intent evidence changed')
            record=row.get('transformation')
            if type(record) is not dict or not any(record is r for r in actor.spec.get('resource_transformations',[])):raise ValueError('product must retain its actual shared transformation receipt')
            result=record['result']
            if result.get('production_id')!=uid:raise ValueError('product and native transformation disagree')
            declared=policy(result.get('product_policy'))
            if declared!=row['intent'].get('product_policy') or row['intent'].get('operation')!=record['operation']:raise ValueError('product declaration does not match paid transformation')
            job_id=result.get('job_id')
            if job_id is not None:
                job=getattr(engine,'_activity_jobs',{}).get('jobs',{}).get(job_id,{})
                if job.get('owner') is not actor or job.get('status')!='complete' or job.get('worked_seconds')!=record['completed_at']-record['started_at']:raise ValueError('product lacks actual completed work')
            ids=result.get('product_instance_ids')
            if type(ids) is not list:raise ValueError('actual physical output identities required')
            stock=result.get('input_stock')
            stocks=[stock] if stock else []
            stocks.extend(x.get('stock') for x in result.get('materials',[]) if x.get('kind')=='physical_item')
            for stock in stocks:
                entries=stock.get('entries',[stock]) if stock else []
                for entry in entries:
                    if entry.get('kind')=='held_instance':
                        paid=objects.get(entry.get('instance_id'),{}).get('consumed',{})
                        if paid.get('by_actor_id')!=actor.entity_id or paid.get('at')!=record['completed_at']:raise ValueError('physical ingredient payment is missing')
            if declared is None:
                if ids:raise ValueError('plain quantity product cannot claim physical copies')
                continue
            if not _item_output(record['operation'],row['intent']['options'],result):raise ValueError('physical product requires its actual native item output')
            if record['operation']=='cook_chef_food' and declared['mode']!='create':raise ValueError('Chef item outputs require creation, not repair')
            if ids!=declared['instance_ids'] or len(ids)!=result['count']:raise ValueError('physical output identity/quantity mismatch')
            for identity in ids:
                obj=objects.get(identity,{})
                if obj.get('item_rule_id')!=result['item_id']:raise ValueError('product physical item rule changed')
                origin=obj.get('crafting_origin',{})
                if declared['mode']=='repair':
                    if uid not in obj.get('crafting_repairs',[]):raise ValueError('actual physical repair evidence missing')
                else:
                    if identity in origins:raise ValueError('one physical output cannot be produced twice')
                    origins[identity]=uid
                    expected={'production_id':uid,'maker_id':actor.entity_id,'owner_id':declared['owner_id'],'at':record['completed_at'],
                        'attachments':[dict(deepcopy(r),ends_at=None if r['seconds'] is None else record['completed_at']+r['seconds']) for r in declared['attachments']]}
                    if origin!=expected:raise ValueError('maker contribution and physical product origin disagree')
                    if origin['owner_id'] not in index:raise ValueError('original product owner is missing')
    for identity,obj in objects.items():
        if 'crafting_origin' in obj and origins.get(identity)!=obj['crafting_origin'].get('production_id'):raise ValueError('physical maker origin was copied or lacks its producer')
    import cleanse_tags as CLEANSE
    CLEANSE.validate_world(engine,index)
    return True


def _source(identity,attachment):
    return 'crafted:'+identity+':'+attachment['id']


def _active(engine,actor,obj,row):
    import items as ITEMS
    registrations=[record for record in getattr(actor,'_item_reg',{}).values()
                   if record.get('instance_id')==obj['id']]
    if not any(ITEMS.equipment_benefit_active(actor,record) for record in registrations):return False
    life=W.physical_lifecycle(obj)
    return (obj.get('equipped_by')==actor.entity_id and not any(life.values())
        and (row['ends_at'] is None or engine.elapsed_seconds<row['ends_at'])
        and (row['ownership']=='any_holder' or actor.entity_id==obj['crafting_origin']['maker_id' if row['ownership']=='creator_only' else 'owner_id']))


def register(engine,actor,obj):
    import state_grants as G,items as I,effects as FX
    for row in obj.get('crafting_origin',{}).get('attachments',[]):
        source=_source(obj['id'],row)
        if not _active(engine,actor,obj,row) or source in actor.spec.get(G.KEY,{}).get('sources',{}):continue
        G._source(actor,source,'item',owner_id=obj['crafting_origin']['maker_id'],rule_id=row['source'],lifetime='equipped',
            product_id=obj['id'],maker_attachment=row['id'],ends_at=row['ends_at'],tutor_points=0)
        for n,raw in enumerate(row['effects']):
            effect=I.normalize(raw);token=source+':'+str(n)
            if effect['type'] in ('save_mod','initiative_mod','speed_mod'):
                G.numeric(actor,{'save_mod':'save_mod','initiative_mod':'initiative_bonus','speed_mod':'movement'}[effect['type']],effect['value'],token)
            else:
                owned=dict(effect,_ability=obj['item_rule_id'])
                G.apply_owned(engine,actor,token,lambda owned=owned:FX.apply_passives(engine,actor,[owned]),effects=[owned])
        G.state(actor)['sources'][source]['effect_sources']=[source+':'+str(n) for n in range(len(row['effects']))]


def unregister(engine,actor,obj):
    import state_grants as G
    if obj is None:return
    for row in obj.get('crafting_origin',{}).get('attachments',[]):
        source=_source(obj['id'],row)
        if source in actor.spec.get(G.KEY,{}).get('sources',{}):G.revoke(actor,source,engine=engine)


def reconcile(engine):
    import state_grants as G
    index=W.actor_index(engine)
    for obj in getattr(engine,'_physical_objects',{}).values():
        if 'crafting_origin' not in obj:continue
        for actor in index.values():
            for row in obj['crafting_origin']['attachments']:
                source=_source(obj['id'],row)
                if source in actor.spec.get(G.KEY,{}).get('sources',{}) and not _active(engine,actor,obj,row):G.revoke(actor,source,engine=engine)
        holder=index.get(obj.get('equipped_by'))
        if holder:register(engine,holder,obj)


def next_interval(engine,end_at):
    deadlines=[row['ends_at'] for obj in getattr(engine,'_physical_objects',{}).values()
        for row in obj.get('crafting_origin',{}).get('attachments',[]) if row['ends_at'] is not None and engine.elapsed_seconds<row['ends_at']<=end_at]
    return min([end_at,*deadlines])-engine.elapsed_seconds


def receipts(engine,actor):
    validate_world(engine,W.actor_index(engine))
    return [{'schema':1,'receipt_id':row['id'],'basis':'native_crafting_product','source_id':row['transformation']['result'].get('recipe_source',R.SOURCE),
        'provider_id':actor.entity_id,'recipient_id':(row['intent']['product_policy'] or {}).get('owner_id',actor.entity_id),
        'completed_at':row['transformation']['completed_at'],'debit':deepcopy(row['transformation']['resources']),
        'native_record':deepcopy(row['transformation'])} for row in actor.spec.get(KEY,{}).values()]
