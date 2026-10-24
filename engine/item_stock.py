"""Whole-unit item stock across actor kinds and quantity/physical storage.

This adapter owns identity and payment only. The actual food/medicine source
continues to decide permission, duration, action cost and resulting effects.
"""
import common_checks as C


def prepare(engine, actor, rule_id, *, held_selection=None, quantity_key=None, count=1, allow_empty=False, container_selection=None, shell_batch_id=None, equipment_slots=('held',), source_selection=None, chef_batch_id=None):
    C.integer(count,'whole item count',1)
    if not isinstance(equipment_slots,(tuple,list)) or not equipment_slots or any(x not in ('held','반대손','장신구') for x in equipment_slots):raise ValueError('explicit eligible physical stock slots required')
    if not isinstance(rule_id,str) or not rule_id.startswith('item/'):
        raise ValueError('actual item rule identity required')
    if type(allow_empty) is not bool:raise ValueError('explicit empty-stock policy required')
    selected = None
    if source_selection is not None:
        import csv_item_food_contracts as CSV
        selected = CSV.validate_choice(engine.r,source_selection,rule_id)
        if container_selection is not None or shell_batch_id is not None:raise ValueError('exact CSV food uses its actual quantity or physical stock')
    if sum(x is not None for x in (held_selection,container_selection,shell_batch_id,chef_batch_id))>1:raise ValueError('select one actual stock location')
    if chef_batch_id is not None:
        C.integer(count,'chef-made serving',1,1)
        if quantity_key is not None or selected is not None:raise ValueError('a Chef batch unit cannot also select quantity or CSV stock')
        import chef_cooking as CHEF
        return CHEF.prepare_batch_stock(engine,actor,rule_id,chef_batch_id)
    if container_selection is not None or shell_batch_id is not None:
        C.integer(count,'identified content serving',1,1)
        if quantity_key is not None:raise ValueError('contents cannot also select quantity inventory')
        if container_selection is not None:
            import item_containers as J
            return J.prepare(engine,actor,rule_id,container_selection)
        import item_maturation as M
        return M.prepare_shell(engine,actor,rule_id,shell_batch_id)
    if held_selection is None:
        inventory=actor.spec.get('items')
        if not isinstance(inventory,dict):raise ValueError('actual item inventory mapping required')
        if selected is not None:
            names=CSV.selected_names(engine.r,selected)
            if quantity_key is not None and quantity_key not in names:raise ValueError('quantity key differs from exact CSV food source')
            keys=[quantity_key] if quantity_key is not None else [key for key in names if key in inventory]
        elif quantity_key is not None:keys=[quantity_key]
        else:
            keys=[key for key in (rule_id,rule_id.split('/',1)[1]) if key in inventory]
            from ruleset import UnresolvedRuleSelection,ExcludedRuleSelection
            for key in inventory:
                if key in keys:continue
                try:resolved=engine.r.item_effects(key)[1].get('id')
                except ExcludedRuleSelection as exc:
                    # Merely owning an explicitly selected CSV variant cannot
                    # prevent payment for an unrelated admitted core item.
                    if exc.identity==rule_id or exc.identity not in engine.r.selection.units:raise
                    continue
                except UnresolvedRuleSelection as exc:
                    # Unrelated ambiguous possessions cannot block this payment.
                    # A requested candidate or stale profile still needs review.
                    if exc.identity!=key or rule_id in exc.candidates or not all(uid in engine.r.selection.units for uid in exc.candidates):raise
                    continue
                if resolved==rule_id:keys.append(key)
        for key in keys:
            if selected is None and engine.r.item_effects(key)[1].get('id')!=rule_id:raise ValueError('quantity inventory key belongs to another item rule')
            available=C.integer(inventory.get(key,0),'actual owned item count',0)
            if available>=count:return {'kind':'quantity','item_id':rule_id,'key':key,'count':count,**({'source_selection':selected} if selected is not None else {})}
        if allow_empty:return None
        raise ValueError('actual owned item inventory required')
    if isinstance(held_selection,(list,tuple)):
        if len(held_selection)!=count:raise ValueError('one selected physical instance per consumed unit required')
        entries=[prepare(engine,actor,rule_id,held_selection=selection,equipment_slots=equipment_slots,source_selection=selected) for selection in held_selection]
        if len({entry['instance_id'] for entry in entries})!=count:raise ValueError('the same physical item cannot pay twice')
        return entries[0] if count==1 else {'kind':'held_batch','item_id':rule_id,'count':count,'entries':entries,**({'source_selection':selected} if selected is not None else {})}
    if count!=1:raise ValueError('one physical item pays exactly one unit; select each actual instance')
    obj=inspect_held(engine,actor,rule_id,held_selection,equipment_slots=equipment_slots)
    if obj.get('item_contents',{}).get('current') is not None:raise ValueError('loaded body cannot be spent as if its contents did not exist')
    return {'kind':'held_instance', 'item_id':rule_id, 'instance_id':obj['id'], 'count':1, **({'equipment_slots':list(equipment_slots)} if tuple(equipment_slots)!=('held',) else {}), **({'source_selection':selected} if selected is not None else {})}


def inspect_held(engine,actor,rule_id,selection,*,equipment_slots=('held',)):
    """Read actual held possession/access, without admitting body consumption.

    Container contents need this same access check even while their reusable
    body is loaded. Only prepare() creates an empty-body stock payment plan.
    """
    import items as I, world_entities as W
    remote=getattr(engine,'_physical_objects',{}).get(selection) if isinstance(selection,str) else None
    if remote and remote.get('telekinetic_holder_id')==actor.entity_id:
        __import__('telekinetic').remote(engine,actor,remote)
        W.require_usable_object(remote)
        __import__('environmental_item_state').require_usable(engine,remote)
        if remote.get('kind')!='item_instance' or remote.get('item_rule_id')!=rule_id:raise ValueError('remote item requires its actual selected source')
        return remote
    held = I.selected_equipment(actor, selection, equipment_slots)
    uid = held.get('instance_id')
    obj = getattr(engine, '_physical_objects', {}).get(uid)
    if not isinstance(uid, str) or not isinstance(obj, dict):
        raise ValueError('consumption requires an actual registered physical item')
    W.require_physical_access(obj)
    import environmental_item_state as ENVIRONMENTAL_ITEMS
    ENVIRONMENTAL_ITEMS.require_usable(engine, obj)
    if obj.get('kind') != 'item_instance' or obj.get('item_rule_id') != rule_id:
        raise ValueError('selected physical item belongs to another rule')
    if obj.get('equipped_by') != actor.entity_id or held.get('item_id') != rule_id:
        raise ValueError('selected physical item and actual holder disagree')
    if obj.get('carrier_id'):
        load = actor.spec.get('_carried_load', {})
        if obj['carrier_id'] != actor.entity_id or not any(x.get('id') == uid for x in load.get('objects', [])):
            raise ValueError('selected physical item has inconsistent carried-load state')
        if load.get('blocked_actions') or load.get('failure_pending'):
            raise ValueError('consumption needs the unresolved carrying decision')
    return obj


def debit(engine, actor, stock):
    import consumption_execution as EXECUTION
    EXECUTION.validate(actor)
    return EXECUTION.issue(engine,actor,_debit(engine,actor,stock))


def _debit(engine, actor, stock):
    """Pay exact whole units within the caller's admitted transition.

    Physical batches must be inside a staged caller transaction, as are native
    food, medicine payment, Vitamins and bandage application.
    """
    count=C.integer(stock.get('count',1),'prepared whole item count',1)
    source_selection=stock.get('source_selection')
    if source_selection is not None:
        import csv_item_food_contracts as CSV
        CSV.validate_choice(engine.r,source_selection,stock.get('item_id'))
    if stock.get('kind')=='container_contents':
        import item_containers as J
        return J.debit(engine,actor,stock)
    if stock.get('kind')=='shell_product':
        import item_maturation as M
        return M.consume_shell(engine,actor,stock)
    if stock.get('kind')=='chef_batch':
        import chef_cooking as CHEF
        return CHEF.consume_batch_unit(engine,actor,stock)
    if stock.get('kind')=='held_batch':
        entries=stock.get('entries')
        if not isinstance(entries,list) or len(entries)!=count:raise ValueError('invalid prepared physical batch')
        # Preserve each admitted slot policy and validate the whole batch first.
        checked=[]
        for entry in entries:
            if not isinstance(entry,dict) or entry.get('kind')!='held_instance' or entry.get('item_id')!=stock['item_id'] or not isinstance(entry.get('instance_id'),str):
                raise ValueError('invalid prepared physical batch member')
            C.integer(entry.get('count',1),'prepared physical batch unit',1,1)
            checked.append(prepare(engine,actor,stock['item_id'],held_selection=entry.get('instance_id'),
                                   equipment_slots=entry.get('equipment_slots',('held',)),source_selection=source_selection))
        if len({entry['instance_id'] for entry in checked})!=count:
            raise ValueError('the same physical item cannot pay twice')
        receipts=[_debit(engine,actor,entry) for entry in checked]
        return {'kind':'held_batch','item_id':stock['item_id'],'count':count,'items':receipts}
    if stock.get('kind') == 'quantity':
        inv = actor.spec.get('items')
        key = stock['key']
        if not isinstance(inv, dict): raise ValueError('actual item inventory mapping required')
        C.integer(inv.get(key), 'actual remaining item count', count)
        if source_selection is not None:
            checked=prepare(engine,actor,stock['item_id'],quantity_key=key,count=count,source_selection=source_selection)
            if checked!=stock:raise ValueError('prepared exact CSV food stock changed')
        elif engine.r.item_effects(key)[1].get('id') != stock['item_id']:
            raise ValueError('prepared quantity source changed')
        inv[key] -= count
        return {'kind':'quantity', 'item_id':stock['item_id'], 'count':count, **({'source_selection':source_selection} if source_selection is not None else {})}
    if stock.get('kind') != 'held_instance' or count!=1: raise ValueError('unknown item storage or invalid physical unit count')
    import items as I, world_entities as W, capability_actions as CAP
    checked = prepare(engine, actor, stock['item_id'], held_selection=stock['instance_id'],equipment_slots=stock.get('equipment_slots',('held',)),source_selection=source_selection)
    obj = engine._physical_objects[checked['instance_id']]
    if obj.get('telekinetic_holder_id')==actor.entity_id:
        actor.spec['_carried_load']['objects'][:]=[x for x in actor.spec['_carried_load']['objects'] if x['id']!=obj['id']]
        obj.pop('telekinetic_holder_id')
        W.finish_physical_use(engine,obj,'consumed',{'source':stock['item_id'],'by_actor_id':actor.entity_id,'at':engine.elapsed_seconds})
        return {'kind':'held_instance','item_id':stock['item_id'],'instance_id':obj['id'],'count':1,**({'source_selection':source_selection} if source_selection is not None else {})}
    row = I.selected_equipment(actor, checked['instance_id'], stock.get('equipment_slots',('held',)))
    obj = engine._physical_objects[checked['instance_id']]
    if obj.get('carrier_id'):
        remaining = [x for x in actor.spec['_carried_load']['objects'] if x['id'] != obj['id']]
        CAP.set_carried(engine, actor, remaining, 'actual held item consumed')
    I._unregister_selected(engine, actor, row)
    W.finish_physical_use(engine, obj, 'consumed',
                          {'source':stock['item_id'], 'by_actor_id':actor.entity_id,
                           'at':engine.elapsed_seconds})
    I._refresh_unresolved(engine, actor)
    return {'kind':'held_instance', 'item_id':stock['item_id'], 'instance_id':obj['id'], 'count':1, **({'source_selection':source_selection} if source_selection is not None else {})}

