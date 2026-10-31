"""Data-authored recipe admission and execution, shared by native crafting.

Declarations carry conditions and permitted input alternatives. Facts come
from actual actors/inventory; source metadata retains action and frequency.
The existing transformation adapter commits time, payment and output together.
"""
from copy import deepcopy, copy
from collections import Counter
import common_checks as C
import acquisition_qualification as Q
import crafting_resources as R
import skill_modifiers as SKILL
import world_entities as W

CRAFTING_SOURCE='ch03-skills-edges-feats/재주'


def _text(value):
    return Q.text(value)


def _fields(row, keys):
    if type(row) is not dict or set(row)!=set(keys):
        raise ValueError('exact recipe declaration fields required')


def _names(values):
    if type(values) is not list or not values or len(set(map(str,values)))!=len(values):
        raise ValueError('distinct recipe names required')
    for value in values:_text(value)


def _condition(node, depth=0):
    if depth>12 or type(node) is not dict:raise ValueError('bounded recipe condition required')
    kind=node.get('kind')
    if kind in ('all','any'):
        _fields(node,('kind','conditions'))
        if type(node['conditions']) is not list or not node['conditions']:raise ValueError('recipe alternatives required')
        for child in node['conditions']:_condition(child,depth+1)
    elif kind=='owned':
        _fields(node,('kind','fields','names'));_names(node['fields']);_names(node['names'])
        if any(f not in ('edges','feats','classes') for f in node['fields']):raise ValueError('actual acquisition fields required')
    elif kind=='skill':
        _fields(node,('kind','skill','rank','effective'));_text(node['skill']);C.integer(node['rank'],'recipe skill rank',1)
        if type(node['effective']) is not bool:raise ValueError('explicit recipe rank policy required')
    elif kind=='tool':
        _fields(node,('kind','item_id','names','instance_id'));_text(node['item_id']);_names(node['names'])
        if not node['item_id'].startswith('item/'):raise ValueError('actual tool rule identity required')
        if node['instance_id'] is not None:_text(node['instance_id'])
    elif kind=='region':
        _fields(node,('kind','names'));_names(node['names'])
    else:raise ValueError('unsupported recipe condition')


def declaration(recipe):
    _fields(recipe,('id','source','output','requirements','materials','seconds'))
    _text(recipe['id']);_text(recipe['source']);C.integer(recipe['seconds'],'recipe seconds',0)
    _fields(recipe['output'],('item_id','key'));_text(recipe['output']['item_id']);_text(recipe['output']['key'])
    if not recipe['output']['item_id'].startswith('item/'):raise ValueError('actual recipe output identity required')
    if type(recipe['requirements']) is not list or not recipe['requirements']:raise ValueError('recipe permission requirements required')
    identities=set()
    for row in recipe['requirements']:
        _fields(row,('id','condition','reason'));_text(row['id']);_text(row['reason']);_condition(row['condition'])
        if row['id'] in identities:raise ValueError('duplicate recipe requirement')
        identities.add(row['id'])
    material_groups(recipe['materials'])
    return deepcopy(recipe)


def material_groups(groups, *, allow_zero_value=False):
    """Shared declared material units for item and non-item production."""
    recipe={'materials':groups}
    if type(recipe['materials']) is not list:raise ValueError('recipe material groups required')
    identities=set()
    for row in recipe['materials']:
        _fields(row,('id','options'));_text(row['id'])
        if row['id'] in identities:raise ValueError('duplicate recipe material group')
        identities.add(row['id'])
        if type(row['options']) is not list or not row['options']:raise ValueError('explicit material alternatives required')
        units=set()
        for option in row['options']:
            kind=option.get('kind') if type(option) is dict else None
            if kind=='value':
                _fields(option,('kind','category','amount','scrap','money'));_text(option['category']);units.add('value')
                if any(type(option[k]) is not bool for k in ('scrap','money')) or not (option['scrap'] or option['money']):
                    raise ValueError('explicit craft-only value substitution required')
            elif kind=='shard':
                _fields(option,('kind','color','amount'));units.add('count')
                if type(option['color']) is not str or option['color'] not in R.SHARDS:raise ValueError('actual shard color required')
            elif kind=='item':
                _fields(option,('kind','item_id','key','amount'));units.add('count')
                _text(option['item_id']);_text(option['key'])
                if not option['item_id'].startswith('item/'):raise ValueError('actual material item rule required')
            else:raise ValueError('unsupported recipe material kind')
            C.integer(option['amount'],'recipe material amount',0 if allow_zero_value and kind=='value' else 1)
        if len(units)!=1:raise ValueError('monetary scrap value cannot substitute for counted shards or items')
    return deepcopy(groups)


def _selected(engine, uid):
    # Communication and restored communication facts reuse this identity reader.
    # Only this source already has an explicit, source-verified version owner.
    if uid=='feat/작열':
        __import__('pokemon_move_edges').incandescence_source(engine.r)
        return
    if engine.r._selected_rule(uid)!=uid:raise ValueError('selected recipe source needs its own declaration')


def _item_key(engine, key, uid):
    from ruleset import UnresolvedRuleSelection
    try:actual=engine.r.item_effects(key)[1].get('id')
    except UnresolvedRuleSelection as exc:
        # A reviewed declaration explicitly binds this legacy display alias.
        # Never resolve another identity or silently choose an output variant.
        if exc.identity!=key or uid not in exc.candidates:raise
        actual=uid
    if actual!=uid:raise ValueError('owned recipe tool belongs to another item rule')


def require_tool(engine, actor, instance_id):
    """Admit a real functional tool through existing recipe qualification.

    Ownership alone does not establish access. Carrying/equipment or an actual
    shared-access observation is required. The result is detached evidence,
    never reusable permission to operate the tool.
    """
    W.require_actors(engine, actor)
    identity = W.entity_identity(engine, instance_id, kind='item_instance')
    obj = engine._physical_objects[instance_id]
    held_by = obj.get('equipped_by') or obj.get('carrier_id')
    if held_by is not None and held_by != actor.entity_id:
        raise ValueError('tool is physically held by another actor')
    uid = obj['item_rule_id']
    node = dict(kind='tool', item_id=uid, names=[uid], instance_id=instance_id)
    if not _observe(engine, actor, node, set()):
        raise ValueError('actual tool is inaccessible or functionally unusable')
    return dict(instance_id=instance_id, item_rule_id=uid, owner_id=identity['owner_id'],
                user_id=actor.entity_id)


def _observe(engine, actor, node, sources, *, provider_source=None):
    kind=node['kind']
    if kind in ('all','any'):
        # Evaluate every authored branch so an unresolved source never hides.
        values=[_observe(engine,actor,x,sources,provider_source=provider_source) for x in node['conditions']]
        return all(values) if kind=='all' else any(values)
    if kind=='owned':
        for field in node['fields']:
            if type(actor.spec.get(field,[])) is not list:raise ValueError('actual acquired recipe features must be lists')
        for name in node['names']:
            if name.startswith(('edge/','feat/','class/')):_selected(engine,name);sources.add(name)
        return any(name in actor.spec.get(field,[]) for field in node['fields'] for name in node['names'])
    if kind=='skill':
        if provider_source is not None and __import__('hobbyist').waives_printed_skill(actor,provider_source,node['skill'],node['rank']):return True
        rank=SKILL.effective_rank(engine.r,actor,node['skill']) if node['effective'] else SKILL.rank(engine.r,actor,node['skill'])[2]
        return rank>=node['rank']
    if kind=='region':
        fact=actor.spec.get('crafting_location')
        if fact is None:return False
        _fields(fact,('region','source','reason'))
        for value in fact.values():_text(value)
        return fact['region'] in node['names']
    uid=node['item_id'];_selected(engine,uid)
    if engine.r.item_effects(uid)[1].get('id')!=uid:raise ValueError('selected recipe tool identity changed')
    sources.add(uid)
    instance=node['instance_id']
    if instance is not None:
        identity=W.entity_identity(engine,instance,kind='item_instance')
        obj=engine._physical_objects[instance];W.require_physical_access(obj)
        if obj.get('item_rule_id')!=uid:raise ValueError('recipe tool instance belongs to another item')
        if any(W.physical_lifecycle(obj)[x] for x in ('disabled','suppressed')):return False
        import environmental_item_state as ENVIRONMENTAL_ITEMS
        if ENVIRONMENTAL_ITEMS.active(obj):return False
        attached=obj.get('equipped_by')==actor.entity_id or obj.get('carrier_id')==actor.entity_id
        shared=instance in actor.spec.get('accessible_equipment',[])
        return attached or shared and identity['owner_id'] is not None
    if any(x in actor.spec.get('damaged_items',[]) for x in [uid,*node['names']]):return False
    inventory=actor.spec.get('items',{})
    for name in [uid,*node['names']]:
        available=C.integer(inventory.get(name,0),'actual recipe tool count',0)
        if available:
            _item_key(engine,name,uid)
            return True
    for name in [uid,*node['names']]:
        if name in actor.spec.get('accessible_equipment',[]):
            _item_key(engine,name,uid);return True
    return False


def action_policy(engine, actor, source, seconds):
    import action_metadata as META, action_lifecycle as ACTION, turn as TURN, frequency as FREQ
    _selected(engine,CRAFTING_SOURCE);_selected(engine,source)
    if getattr(engine.r.rulings,'mech',{}).get(CRAFTING_SOURCE) or getattr(engine.r.rulings,'effects',{}).get(CRAFTING_SOURCE):
        raise ValueError('overridden crafting defaults require their own policy')
    import cleanse_tags as CLEANSE
    if CLEANSE.handles(source):
        policy=CLEANSE.crafting_policy(engine,actor,source,seconds)
    elif source=='feat/몬스터볼-장인':
        import hobbyist as H,source_context as SOURCE
        SOURCE.verified_source(engine.r,{'file':'input/ch03-skills-edges-feats.md','sha256':H.GENERAL},label='Poké Ball Crafter permission')
        origin=engine.r.selection.units[source]['source']
        if (origin.get('file'),origin.get('lines'),origin.get('sha256'))!=('ch03-skills-edges-feats.md',[892,895],H.GENERAL):raise ValueError('exact Poké Ball Crafter permission source required')
        _,header=engine.r.feat_effects(source)
        if META.resolve_feature_action(header)!=('static','') or FREQ.parse(header.get('frequency')) not in (('static',1),('at_will',1)):raise ValueError('changed Poké Ball Crafter permission requires its own policy')
        policy=META.resolve_crafting_policy({'feature_kind':'crafting'})
    else:
        _,header=engine.r.feat_effects(source)
        policy=META.resolve_crafting_policy(dict(header,feature_kind='crafting'))
    action=policy['action']
    if action!='extended' and not META.supported_combat_action(action):raise ValueError('specific crafting action requires its own policy')
    if engine.encounter_active and (seconds or action=='extended'):raise ValueError('timed crafting requires an actual noncombat interval')
    if not TURN.can_act(engine,actor) or not ACTION.ordinary_permission(engine,actor) or not ACTION.status_permission(engine,actor,action):
        raise ValueError('crafter cannot perform the actual recipe action')
    probe=copy(actor);probe.spec=__import__('world_entities').spec_copy(actor)
    if not FREQ.activation_allowed(probe,source,policy['frequency'],engine=engine):raise ValueError('specific crafting frequency exhausted')
    if seconds:engine.preflight_advance_time(seconds,[actor])
    return policy


def prepare(engine, actor, recipe, *, count=1, inputs=None):
    W.require_actors(engine,actor);R.validate(actor)
    if actor.kind!='trainer':raise ValueError('actual trainer recipe producer required')
    recipe=declaration(recipe);C.integer(count,'crafted count',1)
    charged=__import__('study_books').recipe(engine,actor,recipe)
    _selected(engine,R.SOURCE);_selected(engine,CRAFTING_SOURCE);_selected(engine,recipe['source'])
    output=recipe['output'];_selected(engine,output['item_id'])
    if engine.r.item_effects(output['key'])[1].get('id')!=output['item_id']:raise ValueError('recipe output key belongs to another selected rule')
    C.integer(actor.spec.get('items',{}).get(output['key'],0),'existing crafted inventory',0)
    sources={R.SOURCE,recipe['source'],output['item_id']}
    checks=[Q.check(row['id'],'prerequisite',_observe(engine,actor,row['condition'],sources,provider_source=recipe['source']),row['reason']) for row in recipe['requirements']]
    qualification=Q.require(recipe['source'],actor.entity_id,'recipe:'+recipe['id'],checks)
    policy=action_policy(engine,actor,recipe['source'],recipe['seconds'])
    material_plan=prepare_materials(engine,actor,charged['materials'],count=count,inputs=inputs,allow_zero_value=True)
    sources.update(material_plan['sources'])
    return {'recipe':recipe,'count':count,'policy':policy,'qualification':qualification,'payments':material_plan['payments'],'sources':sorted(sources)}


def prepare_materials(engine,actor,groups,*,count=1,inputs=None,allow_zero_value=False):
    """Pure aggregate payment plan; the caller owns action, time and output."""
    W.require_actors(engine,actor);R.validate(actor);C.integer(count,'produced count',1)
    recipe={'materials':material_groups(groups,allow_zero_value=allow_zero_value)};_selected(engine,R.SOURCE);sources={R.SOURCE}
    csv_materials=R.csv_materials(engine.r)
    if csv_materials:sources.add(R.CSV_SOURCE)
    inputs={} if inputs is None else inputs
    if type(inputs) is not dict or any(k not in {x['id'] for x in recipe['materials']} for k in inputs):raise ValueError('only declared recipe input groups may be selected')
    payments=[];debits=Counter()
    for group in recipe['materials']:
        selection=inputs.get(group['id'],{'option':0,'scrap_value':0})
        if type(selection) is not dict or set(selection) not in ({'option','scrap_value'},{'option','scrap_value','instances'},{'option','scrap_value','shop'}):raise ValueError('exact recipe material selection required')
        C.integer(selection['option'],'recipe material alternative',0,len(group['options'])-1)
        C.integer(selection['scrap_value'],'scrap cost',0)
        option=group['options'][selection['option']];amount=option['amount']*count
        if 'shop' in selection and (not csv_materials or option['kind']!='value'):raise ValueError('shop only purchases CSV monetary recipe materials')
        payment={'group':group['id'],'option':selection['option'],'kind':option['kind'],'amount':amount}
        if 'instances' in selection:
            if option['kind']!='item' or selection['scrap_value']:raise ValueError('physical inputs require the declared counted item')
            _names(selection['instances'])
            import item_stock as STOCK
            stock=STOCK.prepare(engine,actor,option['item_id'],held_selection=selection['instances'],count=amount)
            prior={uid for p in payments if p['kind']=='physical_item' for uid in p['instances']}
            if prior.intersection(selection['instances']):raise ValueError('one real ingredient cannot pay two material groups')
            payments.append(dict(payment,kind='physical_item',instances=deepcopy(selection['instances']),stock=stock))
            continue
        if option['kind']=='value':
            scrap=selection['scrap_value']
            category=R.material_kind(option['category']) if csv_materials else option['category']
            if csv_materials and group['id'] not in inputs:
                scrap=min(amount,actor.spec.get('crafting_scrap',{}).get(category,0)-debits['crafting_scrap',category])
            if not csv_materials and ((scrap and not option['scrap']) or (scrap!=amount and not option['money'])):raise ValueError('recipe does not permit that money/scrap substitution')
            cost=R.prepare_cost(actor,category,amount,scrap,shop=selection.get('shop'))
            payment.update(category=cost.kind,scrap=cost.scrap,money=cost.money)
            if csv_materials:payment.update(materials_edition='csv-homebrew',purchased_material_value=cost.money,shop=cost.shop)
            debits['crafting_scrap',cost.kind]+=cost.scrap;debits['money',None]+=cost.money
        else:
            if selection['scrap_value']:raise ValueError('monetary scrap cannot pay counted recipe ingredients')
            if option['kind']=='shard':
                field,key='shards',option['color'];_selected(engine,'item/조각');sources.add('item/조각')
            else:
                field,key='items',option['key'];_selected(engine,option['item_id']);sources.add(option['item_id'])
                if engine.r.item_effects(key)[1].get('id')!=option['item_id']:raise ValueError('material belongs to another item rule')
                if key in actor.spec.get('damaged_items',[]) or option['item_id'] in actor.spec.get('damaged_items',[]):raise ValueError('intact recipe material required')
            payment.update(field=field,key=key);debits[field,key]+=amount
        payments.append(payment)
    for (field,key),amount in debits.items():
        available=actor.spec.get(field,0) if key is None else actor.spec.get(field,{}).get(key,0)
        if C.integer(available,'actual recipe material balance',0)<amount:raise ValueError('insufficient aggregate recipe ingredients')
    return {'payments':payments,'sources':sorted(sources)}


def pay_materials(engine,actor,payments):
    """Internal payment consumer used only inside an admitted transaction."""
    payments=deepcopy(payments)
    for payment in payments:
        if payment['kind']=='value':
            R.pay_cost(actor,R.ValueCost(payment['category'],payment['amount'],payment['scrap'],payment['money'],payment.get('shop')))
        elif payment['kind']=='physical_item':
            import item_stock as STOCK
            payment['stock']=STOCK.debit(engine,actor,payment['stock'])
        else:actor.spec[payment['field']][payment['key']]-=payment['amount']
    return payments


def perform(engine, actor, recipe, *, count=1, inputs=None, reason, operation='craft_item'):
    """Internal staged executor; public calls use TransformationUse.execute."""
    _text(reason);plan=prepare(engine,actor,recipe,count=count,inputs=inputs)
    import turn as TURN, frequency as FREQ, activity_jobs as JOBS
    recipe=plan['recipe'];policy=plan['policy'];source=recipe['source']
    if not TURN.spend(engine,actor,policy['action'],source):raise ValueError('recipe action not admitted')
    job=None
    if recipe['seconds']:
        job=JOBS.run_fixed(engine,actor,(),seconds=recipe['seconds'],source=source,context={'recipe':recipe['id'],'reason':reason})['job_id']
    FREQ.consume_activation(actor,source,policy['frequency'],engine=engine)
    plan['payments']=pay_materials(engine,actor,plan['payments'])
    output=recipe['output'];inventory=actor.spec.setdefault('items',{});inventory[output['key']]=inventory.get(output['key'],0)+count
    values=[x for x in plan['payments'] if x['kind']=='value']
    return {'activity':operation,'item':output['key'],'item_id':output['item_id'],'recipe_source':source,'count':count,
            'category':values[0]['category'] if len(values)==1 else None,'scrap_spent':sum(x['scrap'] for x in values),
            'money_spent':sum(x['money'] for x in values),'recipe_id':recipe['id'],'recipe_definition':recipe,
            'qualification':plan['qualification'],'materials':plan['payments'],'recipe_sources':plan['sources'],'job_id':job}


def craft(engine, actor, recipe, *, count=1, inputs=None, reason, product_policy=None, event_id=None):
    import transformation_use as T
    return T.dispatch(engine,actor,'craft_item',recipe=recipe,count=count,inputs=inputs,reason=reason,product_policy=product_policy,event_id=event_id)
