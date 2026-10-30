"""Fling intake: an authenticated thrown body pays the existing native effect.

Extended food is excluded by Core 1.05 p339. This adapter does not call the
ordinary item action producer or grant a cost waiver to arbitrary callers.
"""
from copy import deepcopy


def profile(engine, actor, target, uid, options=None, *, instance_id=None):
    import world_entities as W
    import restorative_items as REST, food_effects as FOOD
    import vitamin_moves as V, lifetime_consumables as LIFE
    import herb_mushroom_rules as HERB, gem_effects as GEM
    import common_checks as C
    W.require_actors(engine, actor, target)
    options = {} if options is None else options
    if type(options) is not dict or set(options) - {'selected_move', 'selected_stat', 'owner_consent_id'}:
        raise ValueError('plain sourced Fling consumer choices required')
    if any(type(value) is not str or not value for value in options.values()):
        raise ValueError('Fling consumer choices use named source or actor identities')
    blend = __import__('researcher_blend_contents').profile(engine, actor, target, instance_id, options)
    if blend is not None:return blend
    if options and uid not in V.ALL_ITEMS | {V.SUPPRESSANT}:
        raise ValueError('these Fling consumer choices require a Vitamin')
    if FOOD.handles(uid) or uid in ('item/붕대', 'item/파스'):
        return None  # Extended intake/application is not the consumables row.
    kind = ('medicine' if uid in REST.HELD_CONSUMABLES else
            'vitamin' if uid in V.ALL_ITEMS | {V.SUPPRESSANT} else
            'lifetime' if uid in LIFE.ITEMS else
            'mushroom' if uid in HERB.MUSHROOMS else
            'gem' if GEM.definition(engine.r, uid) is not None else None)
    if kind is None:
        # A known separately administered consumable is not generic Fling trash.
        import consumable_use as USE
        adapter = USE.adapter_for(uid)
        if adapter.family in (USE.UseFamily.IMMEDIATE, USE.UseFamily.STORED_EFFECT, USE.UseFamily.DEPLOYED):
            raise ValueError('Fling consumption needs this item family native application: ' + uid)
        return None
    effects, header = engine.r.item_effects(uid)
    if effects is None or header.get('id') != uid or engine.r._selected_rule(uid) != uid:
        raise ValueError('actual selected Fling consumable source required')
    plan = dict(kind=kind, item_rule_id=uid, item_name=header.get('name', uid.split('/', 1)[1]),
                effects=deepcopy(effects), header=deepcopy(header), options=deepcopy(options),
                instance_id=instance_id, no_effect=False)
    if kind == 'medicine':
        REST.selected(engine, uid)
        plan['no_effect'] = uid in REST.X_ITEMS and target.kind != 'pokemon'
        if not plan['no_effect']:
            pending = REST.preflight(engine, target, uid)
            if pending is not None:raise ValueError('Fling medicine needs its native timing decision: ' + str(pending))
            if uid in FOOD.HERBS:FOOD.herbal_preflight(engine, target, uid)
            if uid == 'item/만능가루':
                plan['effects'] = [{'type': 'cure_status', 'status': 'persistent all', 'target': 'target'}]
            __import__('effects').preflight_effects(engine, actor, target, plan['effects'], uid, consumer='items.use_item')
    elif kind == 'vitamin':
        plan['no_effect'] = target.kind != 'pokemon'
        if not plan['no_effect']:
            owner_id = options.get('owner_consent_id')
            owner = W.actor_index(engine).get(owner_id) if owner_id is not None else None
            if owner_id is not None and owner is None:raise ValueError('actual Vitamin consent owner required')
            plan['native'] = V.prepare_effect(engine, actor, target, uid,
                selected_move=options.get('selected_move'), selected_stat=options.get('selected_stat'), owner_consent_by=owner)
    elif kind == 'lifetime':
        plan['no_effect'] = target.kind != 'pokemon'
        if not plan['no_effect']:
            native = LIFE.prepare_effect(engine, actor, target, uid)
            if isinstance(native, C.PendingDecision):raise ValueError('Fling growth needs its native history/level decision: ' + str(native))
            plan['native'] = native
    elif kind == 'mushroom':
        HERB.selected(engine.r, uid)
        obj = getattr(engine, '_physical_objects', {}).get(instance_id)
        if obj is None or obj.get('item_rule_id') != uid:raise ValueError('Fling Mushroom requires its actual selected body')
        HERB.validate_object(engine.r, obj, W.actor_index(engine))
        __import__('combat_stage_sources').validate(target)
    else:
        import event_effects as EVENTS
        definition = GEM.definition(engine.r, uid)
        if len(effects) != 1 or not EVENTS.same_payload(EVENTS.semantic(effects[0]), definition['raw']):
            raise ValueError('Fling Gem needs its selected native effect')
        EVENTS.preflight(engine, target, definition['raw'], uid)
        plan['native'] = deepcopy(definition['raw'])
    return plan


def apply_medicine(engine, actor, target, plan, *, paid=None):
    """Native medicine effects after an admitted dose, without a second action.

    FLING-BLEND-CODE-1: an actual Object Not Found recipient still pays (stock
    or Blend contents) but receives no benefit now and no latent X-item timing
    record that would revive after Code expires. Herbal drawbacks still follow
    the intake, exactly as in the ordinary items._use_immediate_item path.
    """
    import restorative_items as REST, items as ITEMS, food_effects as FOOD
    if plan['no_effect']:return (0, 0)
    uid = plan['item_rule_id']
    if paid is not None:
        blocked = __import__('consumption_execution').suppress_benefit(engine, actor, target, paid)
    else:
        blocked = __import__('glitch_bender').benefits_blocked(target)
    if blocked:
        if uid in FOOD.HERBS:FOOD.herbal_consumed(engine, target, uid)
        return (0, 0)
    if uid in REST.X_ITEMS and REST.special_apply(engine, target, uid):return (1, 0)
    return ITEMS.apply_immediate_effects(engine, actor, target, plan['item_name'], plan['effects'], plan['header'])


def consume(engine, actor, target, admission, prepared_plan):
    # These native families already commit stock and effect in one transition.
    # Medicine keeps its existing observed-event tail outside blanket rollback.
    if prepared_plan['kind'] not in ('medicine', 'blend'):
        import state_grants as G
        return G.transition(engine, actor,
            lambda e, a, t: _consume(e, a, t, admission, prepared_plan), participants=(target,))
    return _consume(engine, actor, target, admission, prepared_plan)


def _consume(engine, actor, target, admission, prepared_plan):
    import world_entities as W, consumption_execution as EXECUTION
    import fling_move as FLING
    uid = prepared_plan['item_rule_id']
    current = profile(engine, actor, target, uid, prepared_plan['options'], instance_id=prepared_plan['instance_id'])
    if current != prepared_plan:raise ValueError('Fling consumer plan changed before actual intake')
    if prepared_plan['kind'] == 'blend':
        return __import__('researcher_blend_contents').consume(engine, actor, target, admission, prepared_plan)
    admitted = FLING.consume_item_admission(engine, actor, target, admission, prepared_plan)
    if (admitted['item_rule_id'] != uid or admitted['actor_id'] != actor.entity_id
            or admitted['target_id'] != target.entity_id or admitted['consumer_plan'] != prepared_plan):
        raise ValueError('Fling intake lost its actual producer')
    obj = engine._physical_objects[admitted['instance_id']]
    if prepared_plan['instance_id'] is not None and obj['id'] != prepared_plan['instance_id']:
        raise ValueError('Fling intake body changed')
    mushroom = None
    if prepared_plan['kind'] == 'mushroom':
        mushroom = __import__('herb_mushroom_rules')._ensure_plan(engine, obj)
    # The recipient actually consumes the detached body. The thrower paid it.
    # Keep this exact native evidence shape for Gem world-receipt validation.
    W.finish_physical_use(engine, obj, 'consumed',
        {'source': uid, 'by_actor_id': target.entity_id, 'at': engine.elapsed_seconds})
    paid = EXECUTION.issue(engine, actor, {'kind': 'held_instance', 'item_id': uid,
        'instance_id': obj['id'], 'count': 1,
        'fling': {'completion_id': admitted['completion_id'], 'move_id': admitted['move_id'],
                  'target_id': target.entity_id}})
    payment_id = EXECUTION.payment_id(actor, paid)
    if prepared_plan['no_effect']:
        EXECUTION.finish(actor, paid, target_id=target.entity_id, outcome='no_effect')
        result = (0, 0)
    elif prepared_plan['kind'] == 'medicine':
        result = apply_medicine(engine, actor, target, prepared_plan, paid=paid)
        EXECUTION.finish_immediate(engine, actor, target, payment_id, prepared_plan['header'], result)
    elif prepared_plan['kind'] == 'vitamin':
        result = __import__('vitamin_moves').apply_paid(engine, target, actor, prepared_plan['native'], paid)
    elif prepared_plan['kind'] == 'lifetime':
        result = __import__('lifetime_consumables').apply_paid(engine, target, actor, prepared_plan['native'], paid)
    elif prepared_plan['kind'] == 'mushroom':
        result = __import__('herb_mushroom_rules').apply_mushroom(engine, target, uid, mushroom)
        EXECUTION.finish(actor, paid, target_id=target.entity_id, outcome='applied',
                         results=[{'kind': 'mushroom', 'id': obj['id']}])
    else:
        import event_effects as EVENTS
        EVENTS.grant(engine, target, prepared_plan['native'], uid, item_stock=paid)
        result = {'effect_id': EVENTS.live(target)[-1]['id']}
        EXECUTION.finish(actor, paid, target_id=target.entity_id, outcome='applied',
                         results=[{'kind': 'event_effect', 'id': result['effect_id']}])
    return {'status': 'consumed', 'item_rule_id': uid, 'instance_id': obj['id'],
            'stock_receipt_id': payment_id, 'result': result}


def validate_result(engine, completion, launch):
    """A saved thrown intake must still reference its original body and payment."""
    import world_entities as W, consumption_execution as EXECUTION
    result = launch.get('consumer_result')
    if result is None:return
    if result.get('status') == 'consumed_contents':
        return __import__('researcher_blend_contents').validate_result(engine, completion, launch)
    plan = launch['plan'];index = W.actor_index(engine)
    actor = completion['actor']
    admissions = [row for row in launch.get('admissions', {}).values()
        if row.get('completion_id') == completion['id'] and row.get('kind') == 'consumer'
        and row.get('consumed') is True and row.get('instance_id') == plan['instance_id']]
    if len(admissions) != 1:raise ValueError('Fling result needs its one consumed native admission')
    admitted = admissions[0];target = index.get(admitted['target_id'])
    payment = EXECUTION.validate(actor).get(result.get('stock_receipt_id'))
    obj = getattr(engine, '_physical_objects', {}).get(plan['instance_id'])
    if (target is None or admitted['actor_id'] != actor.entity_id or admitted['move_id'] != completion['move_id']
            or result.get('status') != 'consumed' or result.get('instance_id') != plan['instance_id']
            or result.get('item_rule_id') != plan['item_rule_id'] or payment is None
            or payment['outcome'] not in ('applied', 'no_effect') or payment['target_id'] != target.entity_id
            or obj is None or obj.get('item_rule_id') != plan['item_rule_id']):
        raise ValueError('Fling consumed result lost its native source/target/payment')
    expected = {'kind': 'held_instance', 'item_id': plan['item_rule_id'], 'instance_id': plan['instance_id'],
                'count': 1, 'fling': {'completion_id': completion['id'], 'move_id': completion['move_id'],
                                    'target_id': target.entity_id}}
    if (payment['item_stock'] != expected
            or obj.get('consumed') != {'source': plan['item_rule_id'], 'by_actor_id': target.entity_id, 'at': payment['at']}):
        raise ValueError('Fling consumed body and original stock receipt disagree')
    dispatch = getattr(engine, '_effect_dispatch_receipts', {}).get(admitted['effect_receipt'])
    if (dispatch is None or dispatch['actor'] is not actor or dispatch['target'] is not target
            or dispatch['source_id'] != completion['move_id'] or not dispatch.get('fling_applied')):
        raise ValueError('Fling intake lost its actual final effect dispatch')
