"""Identity-preserving held-item and contained-product maturation.

Known elapsed time drives data-defined phases. Shell contents are actual owned
products, distinct from inventory and held slots. Uncertain continuity remains
pending; a deterministic conversion may be retried without rerolling time.
"""
from pathlib import Path
from copy import deepcopy
import json
import common_checks as C

KEY='item_maturations'
SOURCE='capability/과즙기'
SESSION_SOURCE='C2CSV/item-data:83:5'


def row_policy(rules,row):
    p=policy(rules)
    if row.get('source')==SESSION_SOURCE:
        import csv_item_contract_policy as CSV
        CSV.definition(rules,clause_id=SESSION_SOURCE)
        return dict(p,held_seconds=1,shell_seconds=4,clock='sessions')
    return dict(p,clock='seconds')


def clock(engine,row):
    return engine.session_epoch if row.get('source')==SESSION_SOURCE else engine.elapsed_seconds


def policy(rules):
    data=getattr(rules,'_item_maturation_policy',None)
    if data is None:
        data=json.loads((Path(rules.root)/'data/item-maturation-policy.json').read_text(encoding='utf-8'))['juicer']
        rules._item_maturation_policy=data
    if rules._selected_rule(data['source'])!=data['source']:raise ValueError('selected maturation source requires its own policy')
    return data


def eligible(actor):
    if actor.kind!='pokemon':return False
    p=policy(actor.r)
    import state_grants as G
    return actor.spec.get('species')==p['species'] and p['capability'] in G.effective(actor,'capabilities')


def capability_changed(actor,capabilities):
    """Source loss invalidates continuity; reacquiring it never rewrites the past."""
    if '과즙기' in capabilities:return
    for row in actor.spec.get(KEY,{}).values():
        if row.get('stage') in ('held','juice'):
            row['pending']='capability_continuity_unknown'


def berry_ids(rules):
    import cultivation_state as PLANTS
    return {rules.item_effects(name)[1]['id'] for name in PLANTS.policy(rules,'cultivation')['berries']}


def validate(actor):
    if KEY not in actor.spec:return True
    rows=actor.spec[KEY]
    if not isinstance(rows,dict):raise ValueError('identified item maturation records required')
    active=set()
    if actor.kind!='pokemon':raise ValueError('maturation container must be a Pokemon')
    for key,row in rows.items():
        p=row_policy(actor.r,row);sessions=p['clock']=='sessions'
        if not isinstance(row,dict) or row.get('id')!=key or not isinstance(key,str) or not key:raise ValueError('maturation identity mismatch')
        if row.get('source') not in (SOURCE,SESSION_SOURCE) or row.get('actor_id')!=actor.entity_id:raise ValueError('maturation source and containing actor required')
        if sessions:
            C.integer(row.get('started_session'),'actual held start session',0)
            C.integer(row.get('last_session'),'last observed maturation session',row['started_session'])
        if not key.startswith(actor.entity_id+':maturation:'):raise ValueError('maturation identity belongs to another actor')
        C.integer(row.get('started_at'),'known held start',0);C.integer(row.get('gap_count'),'known clock-gap baseline',0)
        uid=row.get('instance_id')
        if not isinstance(uid,str) or not uid or row.get('input_item') not in berry_ids(actor.r):raise ValueError('actual source berry instance required')
        if row.get('origin') not in ('native_equipped','observed_holding'):raise ValueError('holding origin required')
        if row['origin']=='observed_holding' and (not isinstance(row.get('reason'),str) or not row['reason'].strip()):raise ValueError('observed holding needs its reason')
        stage=row.get('stage')
        if stage not in ('held','juice','candy','collected','cancelled','consumed','bottled'):raise ValueError('unknown maturation phase')
        if stage in ('held','juice','candy'):
            if uid in active:raise ValueError('one input instance cannot have two active maturations')
            active.add(uid)
        if 'pending' in row and row['pending'] not in ('unknown_elapsed_interval','capability_continuity_unknown'):raise ValueError('unknown maturation obligation')
        if stage in ('juice','candy','collected','consumed','bottled'):
            C.integer(row.get('juice_at'),'juice formation time',row['started_at'] if sessions else row['started_at']+p['held_seconds'],None if sessions else row['started_at']+p['held_seconds'])
            if sessions:C.integer(row.get('juice_session'),'juice formation session',row['started_session']+1,row['started_session']+1)
            stock=row.get('input_stock')
            if stock!={'kind':'held_instance','item_id':row['input_item'],'instance_id':uid,'count':1} or type(stock['count']) is not int:raise ValueError('maturation input must retain its actual one-unit stock receipt')
            product=row.get('product')
            if not isinstance(product,dict) or product.get('id')!=key+':product' or type(product.get('count'))is not int or product['count']!=p['output_count']:raise ValueError('actual produced item identity and quantity required')
            expected=p['intermediate_item'] if stage in ('juice','consumed','bottled') else p['output_item']
            if product.get('item_id')!=expected or product.get('location')!={'collected':'collected','consumed':'consumed','bottled':'container'}.get(stage,'shell'):raise ValueError('maturation product phase/location mismatch')
            if actor.r._selected_rule(expected)!=expected:raise ValueError('selected product source changed')
        elif any(k in row for k in ('product','input_stock','juice_at','candy_at','collection')):raise ValueError('unconverted berry cannot claim a produced item')
        if stage in ('candy','collected'):
            C.integer(row.get('candy_at'),'candy formation time',row['juice_at'] if sessions else row['juice_at']+p['shell_seconds'],None if sessions else row['juice_at']+p['shell_seconds'])
            if sessions:C.integer(row.get('candy_session'),'candy formation session',row['juice_session']+4,row['juice_session']+4)
        elif 'candy_at' in row:raise ValueError('juice cannot claim completed candy formation')
        if stage in ('consumed','bottled'):
            removal=row.get('removal')
            if not isinstance(removal,dict):raise ValueError('actual shell product removal required')
            C.integer(removal.get('at'),'shell removal time',row['juice_at'],None if sessions else row['juice_at']+p['shell_seconds']-1)
            if stage=='consumed':
                if removal.get('kind')!='snack' or removal.get('by_actor_id')!=actor.entity_id:raise ValueError('shell Snack belongs to its actual containing Shuckle')
            elif removal.get('kind')!='bottled' or not all(isinstance(removal.get(k),str) and removal[k].strip() for k in ('by_actor_id','container_id','content_id','reason')) or removal['content_id']!=product['id']:
                raise ValueError('actual bottle destination and loading evidence required')
        elif 'removal' in row:raise ValueError('unremoved product cannot claim removal')
        if stage=='cancelled':
            C.integer(row.get('cancelled_at'),'holding interruption time',row['started_at'])
            if row.get('cancel_reason') not in ('input_no_longer_held','intake_started'):raise ValueError('actual input interruption reason required')
        if stage=='collected':
            receipt=row.get('collection')
            if not isinstance(receipt,dict) or not isinstance(receipt.get('recipient_id'),str) or not receipt['recipient_id']:raise ValueError('actual collected product destination required')
            C.integer(receipt.get('at'),'product collection time',row['candy_at'])
            C.integer(receipt.get('before'),'inventory before collection',0);C.integer(receipt.get('after'),'inventory after collection',0)
            if receipt['after']-receipt['before']!=p['output_count'] or not isinstance(receipt.get('reason'),str) or not receipt['reason'].strip():raise ValueError('collection needs actual inventory change and reason')
    return True


def begin_sessions(engine,actor,selection):
    """Select the CSV clock on the existing physical maturation owner."""
    import world_entities as W,items as I,item_stock as STOCK,state_grants as G
    W.require_actors(engine,actor)
    if not eligible(actor):raise ValueError('homebrew Juicer requires actual Shuckle and live Juicer')
    held=I.selected_equipment(actor,selection,('held',))
    if held.get('item_id') not in berry_ids(engine.r):raise ValueError('homebrew Juicer requires an actual held Berry')
    STOCK.prepare(engine,actor,held['item_id'],held_selection=selection)
    validate(actor)
    active=[r for r in actor.spec.get(KEY,{}).values() if r['stage'] in ('held','juice','candy')]
    if any(r['instance_id']!=selection or r['stage']!='held' or r['source']==SESSION_SOURCE for r in active):
        raise ValueError('homebrew Juicer already contains an actual product')
    def apply(e,c):
        key=active[0]['id'] if active else on_held(e,c,held)
        row=c.spec[KEY][key]
        row.update(source=SESSION_SOURCE,started_at=e.elapsed_seconds,started_session=e.session_epoch,last_session=e.session_epoch)
        validate(c)
        return dict(deepcopy(row),phase='berry',sessions=0)
    return G.transition(engine,actor,apply)


def session_step(engine,actor,*,berry_consumed=False,bottled=False,container_selection=None,recipient=None,reason=None):
    import world_entities as W
    W.require_actors(engine,actor)
    validate(actor)
    rows=[r for r in actor.spec.get(KEY,{}).values() if r.get('source')==SESSION_SOURCE and r['stage'] in ('held','juice','candy','cancelled')]
    if not rows:raise ValueError('homebrew Juicer has no actual product')
    row=rows[-1]
    if row.get('pending'):raise ValueError('homebrew Juicer needs known actual capability continuity')
    if berry_consumed:
        obj=engine._physical_objects.get(row['instance_id'],{})
        if not W.physical_lifecycle(obj)['consumed']:raise ValueError('Berry consumption needs its actual physical event')
    if row['stage']=='cancelled':return dict(deepcopy(row),cancelled=True,reason=row['cancel_reason'])
    if not bottled and engine.session_epoch<=row['last_session']:
        raise ValueError('homebrew Juicer needs an actual distinct session boundary')
    plans=preflight(engine,actor,0)
    advance(engine,actor,plans)
    row=actor.spec[KEY][row['id']]
    row['last_session']=engine.session_epoch
    if row['stage']=='cancelled':return dict(deepcopy(row),cancelled=True,reason=row['cancel_reason'])
    if bottled:
        if container_selection is None:raise ValueError('bottling Juice requires an actual empty bottle')
        recipient=recipient or actor
        W.require_actors(engine,recipient)
        return bottle(engine,recipient,actor,row['id'],container_selection,reason)
    return dict(deepcopy(row),phase={'held':'berry'}.get(row['stage'],row['stage']),
                sessions=engine.session_epoch-row.get('juice_session',row['started_session']))


def on_held(engine,actor,held,*,started_at=None,reason=None):
    if not eligible(actor) or not held.get('instance_id') or held.get('item_id') not in berry_ids(engine.r):return None
    validate(actor)
    uid=held['instance_id']
    if any(r['instance_id']==uid and r['stage'] in ('held','juice','candy') for r in actor.spec.get(KEY,{}).values()):return None
    import item_stock as STOCK
    STOCK.prepare(engine,actor,held['item_id'],held_selection=uid)
    when=engine.elapsed_seconds if started_at is None else C.integer(started_at,'observed held start',0,engine.elapsed_seconds)
    if started_at is not None and (not isinstance(reason,str) or not reason.strip()):raise ValueError('holding observation needs its evidence')
    rows=actor.spec.setdefault(KEY,{})
    key=actor.entity_id+':maturation:'+str(len(rows)+1)
    rows[key]={'id':key,'source':SOURCE,'actor_id':actor.entity_id,'instance_id':uid,'input_item':held['item_id'],
        'started_at':when,'gap_count':len(engine.unresolved_time_intervals),'stage':'held',
        'origin':'native_equipped' if started_at is None else 'observed_holding'}
    if reason is not None:rows[key]['reason']=reason
    validate(actor)
    return key


def observe_holding(engine,actor,*,held_selection,started_at,reason):
    import items as I,state_grants as G
    def apply(e,c):
        row=I.selected_equipment(c,held_selection,('held',))
        key=on_held(e,c,row,started_at=started_at,reason=reason)
        if key is None:raise ValueError('eligible actual berry without an existing maturation required')
        e.gm._rec('held maturation start',None,started_at,reason,c)
        return key
    return G.transition(engine,actor,apply)


def on_release(engine,actor,instance_id):
    for row in actor.spec.get(KEY,{}).values():
        if row['stage']=='held' and row['instance_id']==instance_id:
            row.update(stage='cancelled',cancelled_at=engine.elapsed_seconds,cancel_reason='input_no_longer_held')


def validate_world(engine,index):
    objects=getattr(engine,'_physical_objects',{})
    for actor in index.values():
        validate(actor)
        for row in actor.spec.get(KEY,{}).values():
            if row.get('source')==SESSION_SOURCE:
                C.integer(row['last_session'],'last actual maturation session',0,engine.session_epoch)
                C.integer(row['started_session'],'start actual maturation session',0,engine.session_epoch)
                if row.get('candy_session',row.get('juice_session',0))>engine.session_epoch:raise ValueError('maturation session result is in the future')
            obj=objects.get(row['instance_id'])
            if not isinstance(obj,dict) or obj.get('item_rule_id')!=row['input_item']:raise ValueError('maturation input physical identity is missing or changed')
            if row['started_at']>engine.elapsed_seconds:raise ValueError('held start cannot be in the future')
            if row['stage']=='held' and (obj.get('equipped_by')!=actor.entity_id or 'consumed' in obj):raise ValueError('maturation input is no longer actually held')
            if row['stage'] in ('juice','candy','collected','consumed','bottled'):
                consumed=obj.get('consumed',{})
                if consumed.get('by_actor_id')!=actor.entity_id or consumed.get('at')!=row['juice_at']:raise ValueError('maturation product lacks the actual consumed input')
                if row.get('candy_at',row['juice_at'])>engine.elapsed_seconds:raise ValueError('maturation result is in the future')
            if row['stage']=='collected' and row['collection']['recipient_id'] not in index:raise ValueError('collected product recipient is missing')
            if row['stage'] in ('consumed','bottled'):
                removal=row['removal']
                if removal['at']>engine.elapsed_seconds or removal['by_actor_id'] not in index:raise ValueError('shell removal time/actor invalid')
                if row['stage']=='bottled':
                    import item_containers as J
                    portion=objects.get(removal['container_id'],{}).get(J.KEY,{}).get('portions',{}).get(removal['content_id'],{})
                    if portion.get('id')!=row['product']['id'] or portion.get('item_id')!=row['product']['item_id'] or portion.get('loaded_at')!=removal['at'] or portion.get('input_stock')!=shell_receipt(actor,row):raise ValueError('shell product and actual bottle contents disagree')
                else:
                    # A sourced transfer can move a Digestion Buff to another
                    # actor; the material origin remains this Shuckle's shell.
                    candidates=[x for holder in index.values() for x in (*holder.buffs,*holder.spec.get('food_consumption_receipts',[]))]
                    matches=[x for x in candidates if isinstance(x,dict) and not __import__('food_effects').retained_activation(x) and x.get('item_stock')==shell_receipt(actor,row)]
                    if not matches and _pending_shell_intake(engine,actor,row):continue
                    if len(matches)!=1 or matches[0].get('item')!=row['product']['item_id'] or matches[0].get('effect')!={'kind':'heal','amount':30}:raise ValueError('shell Snack must retain its actual acquired or consumed Digestion Buff')
    return True


def _pending_shell_intake(engine,actor,row):
    """Removal is real at intake start; its buff exists only after clock end."""
    import clock_invocations as CLOCK
    expected=shell_receipt(actor,row);matches=[]
    for clock in getattr(engine,CLOCK.KEY,{}).values():
        activity=clock.get('activity',{});plan=activity.get('plan',{})
        if (activity.get('kind')=='food_intake' and activity.get('status')=='pending'
                and activity.get('owner_id')==actor.entity_id and activity.get('payment')==expected
                and plan.get('stock')==expected and plan.get('target_id')==actor.entity_id
                and plan.get('kind')=='snack' and plan.get('shell_snack') is True
                and plan.get('effect')=={'kind':'heal','amount':30} and clock.get('start')==row['removal']['at']):
            matches.append(clock)
    if not matches:return False
    CLOCK.validate(engine) # requires the actual payer's original payment alias
    if len(matches)!=1:raise ValueError('shell product belongs to more than one pending intake')
    return True


def intake_started(engine,actor,stock):
    if stock.get('kind')!='held_instance':return
    for row in actor.spec.get(KEY,{}).values():
        if row['stage']=='held' and row['instance_id']==stock['instance_id']:
            row.update(stage='cancelled',cancelled_at=engine.elapsed_seconds,cancel_reason='intake_started')


def preflight(engine,actor,seconds):
    validate(actor)
    plans=[]
    if not actor.spec.get(KEY):return plans
    import held_equipment as H,item_stock as STOCK
    for key,row in actor.spec[KEY].items():
        p=row_policy(engine.r,row);sessions=p['clock']=='sessions'
        end=clock(engine,row)+(0 if sessions else seconds)
        if row['stage'] not in ('held','juice') or row.get('pending'):continue
        if row['stage']=='held':
            current=next((x for x in H.entries(actor) if x.get('instance_id')==row['instance_id'] and x.get('item_id')==row['input_item']),None)
            if current is None:
                plans.append((key,'cancel'));continue
        if not sessions and row['gap_count']!=len(engine.unresolved_time_intervals):plans.append((key,'unknown_elapsed_interval'));continue
        if not eligible(actor):plans.append((key,'capability_continuity_unknown'));continue
        due=(row['started_session']+1 if row['stage']=='held' else row['juice_session']+4) if sessions else (row['started_at']+p['held_seconds'] if row['stage']=='held' else row['juice_at']+p['shell_seconds'])
        if end>=due:
            if row['stage']=='held':STOCK.prepare(engine,actor,row['input_item'],held_selection=row['instance_id'])
            plans.append((key,'mature'))
    return plans


def advance(engine,actor,plans):
    import equipment_variant_contracts as EQUIPMENT_VARIANTS
    EQUIPMENT_VARIANTS.advance_time(engine,actor)
    if not plans:return
    import state_grants as G,item_stock as STOCK
    def apply(e,c):
        for key,op in plans:
            row=c.spec[KEY][key]
            p=row_policy(e.r,row);sessions=p['clock']=='sessions'
            if op=='cancel':
                row.update(stage='cancelled',cancelled_at=e.elapsed_seconds,cancel_reason='input_no_longer_held');continue
            if op!='mature':row['pending']=op;continue
            if row['stage']=='held':
                stock=STOCK.prepare(e,c,row['input_item'],held_selection=row['instance_id'])
                row['stage']='juice' # this admitted conversion owns the release
                receipt=STOCK.debit(e,c,stock)
                row['juice_at']=e.elapsed_seconds if sessions else row['started_at']+p['held_seconds'];row['input_stock']=receipt
                if sessions:row['juice_session']=row['started_session']+1
                e._physical_objects[row['instance_id']]['consumed']['at']=row['juice_at']
                row['product']={'id':key+':product','item_id':p['intermediate_item'],'count':p['output_count'],'location':'shell'}
            due=row['juice_session']+4 if sessions else row['juice_at']+p['shell_seconds']
            if clock(e,row)>=due:
                row['stage']='candy';row['candy_at']=e.elapsed_seconds if sessions else due;row['product']['item_id']=p['output_item']
                if sessions:row['candy_session']=due
            e.log(f'    {c.name}: held item maturation -> {row["stage"]}',SOURCE)
        validate(c)
    # Only deterministic material conversion is staged. The already advanced
    # world interval and unrelated observed events are never rolled back here.
    return G.transition(engine,actor,apply)


def collect(engine,trainer,*,target,batch_id,reason,container_selection=None):
    import pokemon_activities as P,state_grants as G
    P._trainer(trainer);P._outside(engine);P._owner(trainer,target);P._text(reason,'actual product collection reason')
    validate(target)
    row=target.spec.get(KEY,{}).get(batch_id)
    if not isinstance(row,dict):raise ValueError('actual source-produced batch required')
    if row['stage']=='juice':
        if container_selection is None:return C.PendingDecision('Select an actual observed-empty bottle for shell Juice')
        return bottle(engine,trainer,target,batch_id,container_selection,reason)
    if container_selection is not None:raise ValueError('bottle selection applies only to shell Juice')
    if row['stage']!='candy' or row.get('pending'):raise ValueError('uncollected matured Candy required')
    uid=row['product']['item_id'];inv=trainer.spec.get('items')
    if not isinstance(inv,dict):raise ValueError('actual recipient inventory required')
    before=C.integer(inv.get(uid,0),'actual existing output count',0)
    def apply(e,c,t):
        r=t.spec[KEY][batch_id]
        c.spec['items'][uid]=before+policy(e.r)['output_count']
        r.update(stage='collected',collection={'recipient_id':c.entity_id,'at':e.elapsed_seconds,'before':before,'after':c.spec['items'][uid],'reason':reason})
        r['product']['location']='collected';validate(t)
        return deepcopy(r)
    return G.transition(engine,trainer,apply,participants=(target,))


def shell_receipt(actor,row):
    return {'kind':'shell_product','actor_id':actor.entity_id,'batch_id':row['id'],'product_id':row['product']['id'],'item_id':row['product']['item_id'],'count':1}


def prepare_shell(engine,actor,rule_id,batch_id):
    validate(actor)
    row=actor.spec.get(KEY,{}).get(batch_id)
    if not row or row['stage']!='juice' or row.get('pending') or row['product']['item_id']!=rule_id:
        raise ValueError('actual available shell Juice batch required')
    if (row.get('source')!=SESSION_SOURCE and row['gap_count']!=len(engine.unresolved_time_intervals)) or not eligible(actor):
        raise ValueError('shell contents need known capability/time continuity')
    valid_clock=(row['juice_session']<=engine.session_epoch<row['juice_session']+4 if row.get('source')==SESSION_SOURCE else row['juice_at']<=engine.elapsed_seconds<row['juice_at']+policy(engine.r)['shell_seconds'])
    if not valid_clock:
        raise ValueError('shell Juice phase must be resolved against the actual clock')
    return shell_receipt(actor,row)


def consume_shell(engine,actor,stock):
    checked=prepare_shell(engine,actor,stock['item_id'],stock['batch_id'])
    if checked!=stock:raise ValueError('prepared shell product changed')
    row=actor.spec[KEY][stock['batch_id']]
    row.update(stage='consumed',removal={'kind':'snack','by_actor_id':actor.entity_id,'at':engine.elapsed_seconds})
    row['product']['location']='consumed'
    validate(actor)
    return checked


def bottle(engine,trainer,target,batch_id,selection,reason):
    import item_containers as J,state_grants as G
    stock=prepare_shell(engine,target,policy(engine.r)['intermediate_item'],batch_id)
    J.empty_body(engine,trainer,selection)
    def apply(e,c,t):
        row=t.spec[KEY][batch_id]
        destination=J.deposit(e,c,selection,item_id=stock['item_id'],stock=stock,source=SOURCE,reason=reason,product_id=stock['product_id'])
        row.update(stage='bottled',removal={'kind':'bottled','by_actor_id':c.entity_id,'at':e.elapsed_seconds,'reason':reason,**destination})
        row['product']['location']='container'
        validate(t)
        e.log(f'    {t.name}: shell Juice bottled in {destination["container_id"]}',SOURCE)
        return deepcopy(row)
    return G.transition(engine,trainer,apply,participants=(target,))
