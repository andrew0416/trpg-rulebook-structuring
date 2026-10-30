"""Reusable physical bodies and separately identified, sourced contents.

The initial empty state is an observation, never inferred from an item name.
Native loading moves existing stock, and intake spends contents only. Each
portion retains its origin after use so body reuse cannot erase provenance.
"""
from pathlib import Path
from copy import deepcopy
import json
import common_checks as C

KEY='item_contents'


def policy(rules,uid):
    data=getattr(rules,'_item_container_policy',None)
    if data is None:
        data=json.loads((Path(rules.root)/'data/item-container-policy.json').read_text(encoding='utf-8'))
        rules._item_container_policy=data
    row=data['containers'].get(uid)
    if row is None or rules._selected_rule(row['source'])!=row['source']:
        raise ValueError('selected physical container needs its own source contract')
    return row


def text(value,label):
    if not isinstance(value,str) or not value.strip():raise ValueError(label+' required')
    return value


def body(engine,actor,selection):
    import items as I,item_stock as S
    held=I.selected_equipment(actor,selection,('held',))
    policy(engine.r,held['item_id'])
    return S.inspect_held(engine,actor,held['item_id'],selection)


def validate_object(engine,obj,index):
    if KEY not in obj:return
    policy(engine.r,obj.get('item_rule_id'))
    state=obj[KEY]
    if not isinstance(state,dict) or type(state.get('version')) is not int or state['version']!=1 or state.get('container_id')!=obj['id']:
        raise ValueError('container contents identity/version mismatch')
    origin=state.get('origin')
    if not isinstance(origin,dict) or origin.get('kind')!='observed_empty':raise ValueError('known empty container origin required')
    text(origin.get('reason'),'empty-container evidence')
    if origin.get('actor_id') not in index:raise ValueError('empty-container observer actor missing')
    C.integer(origin.get('at'),'empty-container observation time',0,engine.elapsed_seconds)
    if state.get('current') is not None:text(state['current'],'current content identity')
    rows=state.get('portions')
    if not isinstance(rows,dict):raise ValueError('identified container portions required')
    stored=[]
    for key,row in rows.items():
        if not isinstance(row,dict) or row.get('id')!=key:raise ValueError('portion identity mismatch')
        text(key,'portion identity');uid=row.get('item_id')
        crafted=isinstance(row.get('input_stock'),dict) and row['input_stock'].get('kind')=='researcher_blend'
        if crafted:
            __import__('researcher_blend_contents').validate_portion(engine,obj,row,index)
        elif not isinstance(uid,str) or engine.r.item_effects(uid)[1].get('id')!=uid or engine.r._selected_rule(uid)!=uid:raise ValueError('actual selected content item required')
        C.integer(row.get('count'),'whole content portion',1,1)
        C.integer(row.get('loaded_at'),'content loading time',origin['at'],engine.elapsed_seconds)
        if row.get('loaded_by') not in index:raise ValueError('actual content loader missing')
        text(row.get('reason'),'content transfer reason')
        stock=row.get('input_stock')
        if not isinstance(stock,dict) or stock.get('item_id')!=uid or type(stock.get('count')) is not int or stock['count']!=1:raise ValueError('content input stock receipt required')
        if crafted:
            pass  # Exact native Blend producer/quantity/creation was joined above.
        elif stock.get('kind')=='quantity':
            if row.get('source')!=obj['item_rule_id']:raise ValueError('container load source changed')
        elif stock.get('kind')=='held_instance':
            if row.get('source')!=obj['item_rule_id']:raise ValueError('container load source changed')
            material=getattr(engine,'_physical_objects',{}).get(stock.get('instance_id'),{})
            if material.get('item_rule_id')!=uid or material.get('consumed',{}).get('by_actor_id')!=row['loaded_by'] or material['consumed'].get('at')!=row['loaded_at']:raise ValueError('container input physical payment missing')
        elif stock.get('kind')=='capability_product':
            import capability_products as PRODUCTS
            producer=index.get(stock.get('producer_id'))
            product=PRODUCTS.validate(producer).get(stock.get('product_id'),{}) if producer else {}
            if stock.get('product_id')!=key or product.get('container_id')!=obj['id'] or product.get('item_id')!=uid or product.get('source')!=row.get('source') or product.get('at')!=row['loaded_at'] or product.get('collector_id')!=row['loaded_by']:raise ValueError('actual capability-produced portion receipt required')
        elif stock.get('kind')=='shell_product':
            import item_maturation as M
            actor=index.get(stock.get('actor_id'))
            batch=actor.spec.get(M.KEY,{}).get(stock.get('batch_id'),{}) if actor else {}
            removal=batch.get('removal',{})
            if row.get('source')!=M.SOURCE or stock.get('product_id')!=key or batch.get('stage')!='bottled' or removal.get('container_id')!=obj['id'] or removal.get('content_id')!=key or removal.get('at')!=row['loaded_at'] or removal.get('by_actor_id')!=row['loaded_by']:raise ValueError('bottled contents lack actual shell transfer')
        else:raise ValueError('unsupported content origin')
        if row.get('status')=='stored':
            if 'consumed_at' in row or 'consumed_by' in row:raise ValueError('stored contents cannot also be consumed')
            stored.append(key)
        elif row.get('status')=='consumed':
            C.integer(row.get('consumed_at'),'content consumption time',row['loaded_at'],engine.elapsed_seconds)
            if row.get('consumed_by') not in index:raise ValueError('actual content payer missing')
        else:raise ValueError('unknown content state')
    if len(stored)>1 or state.get('current')!=(stored[0] if stored else None):raise ValueError('container active contents disagree with portion history')


def validate_world(engine,index):
    seen=set()
    for obj in getattr(engine,'_physical_objects',{}).values():
        validate_object(engine,obj,index)
        for key in obj.get(KEY,{}).get('portions',{}):
            if key in seen:raise ValueError('one portion cannot be copied into two containers')
            seen.add(key)
    __import__('researcher_blend_contents').validate_world(engine,index)
    return True


def observe_empty(engine,actor,*,container_selection,reason):
    import state_grants as G
    text(reason,'actual empty-container observation')
    obj=body(engine,actor,container_selection)
    if KEY in obj:raise ValueError('known container history cannot be reset by an empty observation')
    def apply(e,c):
        jar=body(e,c,container_selection)
        jar[KEY]={'version':1,'container_id':jar['id'],'origin':{'kind':'observed_empty','actor_id':c.entity_id,'at':e.elapsed_seconds,'reason':reason},'current':None,'portions':{}}
        e.gm._rec('empty container '+jar['id'],None,jar[KEY],reason,c)
        return deepcopy(jar[KEY])
    return G.transition(engine,actor,apply)


def empty_body(engine,actor,selection):
    import world_entities as W
    obj=body(engine,actor,selection)
    if KEY not in obj:raise ValueError('container emptiness must be observed before native loading')
    validate_object(engine,obj,W.actor_index(engine))
    if obj[KEY]['current'] is not None:raise ValueError('occupied container: mixing or multiple portions requires an explicit source contract')
    return obj


def deposit(engine,actor,selection,*,item_id,stock,source,reason,product_id=None):
    # Called only inside the producer's admitted material transaction.
    jar=empty_body(engine,actor,selection);state=jar[KEY]
    text(reason,'actual content loading reason')
    key=product_id or jar['id']+':contents:'+str(len(state['portions'])+1)
    if key in state['portions']:raise ValueError('contents identity already used')
    state['portions'][key]={'id':key,'item_id':item_id,'count':1,'source':source,'status':'stored','loaded_at':engine.elapsed_seconds,'loaded_by':actor.entity_id,'reason':reason,'input_stock':deepcopy(stock)}
    state['current']=key
    return {'container_id':jar['id'],'content_id':key}


def load(engine,actor,*,container_selection,item_name,reason,held_selection=None):
    import item_stock as S,state_grants as G,pokemon_activities as P,movement_actions as MOVEMENT
    MOVEMENT.boundary(engine,'load_container');P._outside(engine);text(reason,'actual content transfer reason')
    import turn as TURN
    if not TURN.can_act(engine,actor):raise ValueError('acting container holder required')
    jar=empty_body(engine,actor,container_selection)
    uid=engine.r.item_effects(item_name)[1].get('id')
    stock=S.prepare(engine,actor,uid,held_selection=held_selection)
    if stock.get('instance_id')==jar['id']:raise ValueError('container cannot contain itself')
    def apply(e,c):
        receipt=S.debit(e,c,stock)
        result=deposit(e,c,container_selection,item_id=uid,stock=receipt,source=jar['item_rule_id'],reason=reason)
        import consumption_execution as EXECUTION
        EXECUTION.finish(c,receipt,target_id=c.entity_id,outcome='loaded',
                         results=[{'kind':'container_contents','id':result['content_id'],'container_id':result['container_id']}])
        e.log(f'    {c.name}: loaded {uid} into {jar["id"]}',jar['item_rule_id'])
        return result
    return G.transition(engine,actor,apply)


def prepare(engine,actor,rule_id,selection):
    import world_entities as W
    jar=body(engine,actor,selection)
    validate_object(engine,jar,W.actor_index(engine))
    state=jar.get(KEY,{})
    row=state.get('portions',{}).get(state.get('current'))
    if not row or row.get('item_id')!=rule_id or row.get('status')!='stored':raise ValueError('actual selected contents of this item required')
    return {'kind':'container_contents','container_id':jar['id'],'content_id':row['id'],'item_id':rule_id,'count':1}


def debit(engine,actor,stock):
    checked=prepare(engine,actor,stock['item_id'],stock['container_id'])
    if checked!=stock:raise ValueError('prepared contents identity changed')
    state=engine._physical_objects[checked['container_id']][KEY]
    row=state['portions'][checked['content_id']]
    row.update(status='consumed',consumed_at=engine.elapsed_seconds,consumed_by=actor.entity_id)
    state['current']=None
    return checked
