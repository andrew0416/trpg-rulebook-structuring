"""Exact CSV definitions using the native digestion owner and consumers.

The clause is an explicit source choice, not an automatic profile replacement.
Old separate-state saves remain observations until explicit GM reconciliation
verifies their original payment. New intake never writes that active store.
"""
from copy import deepcopy

import csv_item_contract_policy as POLICY


STATE = "csv_remaining_food_state"
SELECTION = "csv_food_source"
SOURCE_KEYS = ("clause_id", "item_id", "kind", "source_file", "source_row",
               "source_columns", "source_row_sha256")
ITEM_KINDS = {
    "item/다이버섯": "dynamax_mushroom",
    "item/흉내허브": "mirror_herb",
    "item/회복허브": "recovery_herb_playtest",
    "item/단맛-과자": "sweet_confection_homebrew",
}


def definition(rules, item_id):
    row = POLICY.definition(rules, item_id=item_id)
    return row if row and row["kind"] == ITEM_KINDS.get(item_id) and row['domain'] == 'food' else None


def source_choice(rules, item_id, clause_id):
    row = definition(rules, item_id)
    if row is None or clause_id != row['clause_id']:
        raise ValueError('exact reviewed CSV food clause selection required')
    return {key: deepcopy(row[key]) for key in SOURCE_KEYS}


def validate_choice(rules, choice, item_id=None):
    if not isinstance(choice, dict):
        raise ValueError('typed exact CSV food source choice required')
    expected = source_choice(rules, choice.get('item_id'), choice.get('clause_id'))
    if choice != expected or (item_id is not None and expected['item_id'] != item_id):
        raise ValueError('CSV food source choice changed')
    return expected


def intake_choice(rules, item_id, policy):
    if policy is not None and item_id != 'item/이유식':
        return source_choice(rules, item_id, policy)
    # Preserve the Chef default and explicit homebrew/playtest choices.
    if item_id == 'item/흉내허브':
        if rules._selected_rule(item_id) != item_id:
            raise ValueError('selected Mirror Herb source changed')
        return source_choice(rules, item_id, definition(rules, item_id)['clause_id'])
    return None


def selected_names(rules, choice):
    choice = validate_choice(rules, choice)
    uid = choice['item_id']
    return (uid, uid.split('/', 1)[1], rules.items_mech[uid]['name'])


def selected_header(rules, choice, requested=None):
    choice = validate_choice(rules, choice)
    if requested is not None and requested not in selected_names(rules, choice):
        raise ValueError('requested item differs from exact CSV food choice')
    raw = rules.items_mech[choice['item_id']]
    return dict(raw.get('header', {}), id=choice['item_id'], name=raw['name'],
                desc=raw.get('desc', ''), confidence='source_pinned_csv_food')


def effect(choice):
    if choice['kind'] == 'recovery_herb_playtest':
        return {'kind': 'save_bonus', 'amount': 2}
    return {'kind': 'csv_food', 'contract_kind': choice['kind']}


def validate_native(actor, buff):
    choice = validate_choice(actor.r, buff.get(SELECTION), buff.get('item'))
    if buff.get('effect') != effect(choice) or buff.get('effect_source') != choice['item_id']:
        raise ValueError('CSV digestion payload differs from its exact source')
    return choice


def _buff(actor, buff_id):
    import food_effects as FOOD
    buff = FOOD.get_buff(actor, buff_id)
    validate_native(actor, buff)
    return buff


def buffs(actor, kind=None):
    result = []
    for buff in actor.buffs:
        if isinstance(buff, dict) and SELECTION in buff:
            row = validate_native(actor, buff)
            if kind is None or row['kind'] == kind:
                result.append(buff)
    return result


def consume(engine, user, target, item_id, **options):
    """Compatibility entry uses the same public Extended intake, with no waiver."""
    row = definition(engine.r, item_id)
    if row is None:
        raise ValueError("selected item is not a remaining CSV food contract")
    return engine.use_item(user, item_id, target, food_policy=row['clause_id'], **options)


def _spend(engine, actor, buff, consumer, result):
    import food_effects as FOOD
    receipt = FOOD.remove_buff(engine, actor, buff, producer=consumer)
    receipt['benefit'] = deepcopy(result)
    return receipt


def consume_dynamax(engine, actor, buff_id, *, form_source):
    buff = _buff(actor, buff_id)
    if (validate_native(actor, buff)['kind'] != 'dynamax_mushroom'
            or form_source != 'gigantamax' or not designated_form_authorized(engine, actor, buff)):
        raise ValueError('Dynamax Mushroom consumption requires its actual designated native form entry')
    event = engine._csv_food_form_event
    receipt = _spend(engine, actor, buff, 'designated_dynamax_form',
        {'form_source': form_source, 'form_id': event['receipt']['form_id'],
         'encounter_epoch': event['receipt']['encounter_epoch']})
    return {'buff_id': buff_id, 'sequence': receipt['sequence']}


def designated_form_authorized(engine, actor, buff):
    event = getattr(engine, '_csv_food_form_event', None)
    if not isinstance(event, dict) or event.get('actor') is not actor or event.get('buff_id') != buff['id']:
        return False
    import gmax_moves as GMAX
    receipt = GMAX._validate_receipt(engine, actor)
    return (receipt is event.get('receipt') and receipt.get('producer_source') == 'item/다이버섯'
            and receipt.get('food_consumption') is None)


def form_preflight(engine, actor, source_id):
    if source_id != 'item/다이버섯':
        return None
    candidates = buffs(actor, 'dynamax_mushroom')
    if len(candidates) != 1:
        raise ValueError('one actual Dynamax Mushroom Digestion Buff required for selected form source')
    return candidates[0]['id']


def _form_entered(engine, actor, buff_id, receipt):
    if buff_id is None:
        return None
    engine._csv_food_form_event = {'actor': actor, 'buff_id': buff_id, 'receipt': receipt}
    try:
        return consume_dynamax(engine, actor, buff_id, form_source='gigantamax')
    finally:
        del engine._csv_food_form_event


def forbid_external_operation(actor, buff_id, operation):
    buff = _buff(actor, buff_id)
    if validate_native(actor, buff)['kind'] == 'dynamax_mushroom' and operation in ("steal", "consume", "deny", "reuse", "transfer"):
        raise ValueError("Dynamax Mushroom buff excludes theft, ordinary consumption, denial and reuse")
    return False


def transferable(actor, buff):
    return SELECTION not in buff or validate_native(actor, buff)['kind'] != 'dynamax_mushroom'


def mirror_holders(engine, *, exclude=None):
    import world_entities as WORLD
    return [(actor, buff) for actor in WORLD.actor_index(engine).values() if actor is not exclude
            for buff in buffs(actor, 'mirror_herb')]


def change_stage(engine, actor, stat, delta):
    """Keep the actual gain and all selected Herb exchanges in one transition."""
    import state_grants as GRANTS
    def apply(staged, subject):
        staged._csv_food_stage_transaction = True
        try:
            return staged.change_stage(subject, stat, delta)
        finally:
            del staged._csv_food_stage_transaction
    return GRANTS.transition(engine, actor, apply)


def assign_stages(engine, changes):
    """Observe actual gains from copy/swap/inversion without changing assignment semantics."""
    import combat_stage_sources as STAGES
    changes = tuple((actor, dict(values)) for actor, values in changes)
    prepared = tuple((actor, STAGES.prepare_assignment(actor, values)) for actor, values in changes)
    before = tuple(dict(actor.stages) for actor, _ in changes)
    gains = any(after > prior[stat] and mirror_holders(engine, exclude=actor)
                for (actor, values), prior in zip(changes, before)
                for stat, after in values.items())
    if not gains:
        for actor, assignment in prepared:
            STAGES.commit_assignment(actor, assignment)
        return

    import state_grants as GRANTS
    def apply(staged, first, *rest):
        staged_changes = tuple(zip((first, *rest), (values for _, values in changes)))
        staged_prepared = tuple((actor, STAGES.prepare_assignment(actor, values))
                                for actor, values in staged_changes)
        staged_before = tuple(dict(actor.stages) for actor, _ in staged_changes)
        staged._csv_food_stage_transaction = True
        try:
            for actor, assignment in staged_prepared:
                STAGES.commit_assignment(actor, assignment)
            assigned_after = tuple(dict(actor.stages) for actor, _ in staged_changes)
            for (actor, _), prior, after in zip(staged_changes, staged_before, assigned_after):
                for stat in STAGES.STATS:
                    if after[stat] > prior[stat]:
                        _stage_changed(staged, actor, stat, prior[stat], after[stat])
        finally:
            del staged._csv_food_stage_transaction
    GRANTS.transition(engine, changes[0][0], apply,
                      participants=tuple(actor for actor, _ in changes[1:]))


def _stage_changed(engine, source_actor, stat, before, after):
    """Private Engine callback receives its actual clamped values, not declarations."""
    if stat not in ("atk", "def", "spa", "spd", "spe") or after <= before:
        return None
    candidates = mirror_holders(engine, exclude=source_actor)
    previous = getattr(engine, '_csv_food_stage_event', None)
    event = dict(source_actor=source_actor, stat=stat, before=before, after=after, selected=None)
    engine._csv_food_stage_event = event
    try:
        for holder, buff in candidates:
            if buff not in holder.buffs:
                continue
            # Optional forbidden consumption must not invalidate the source gain.
            import food_effects as FOOD, ability_target_limits as LIMITS
            if LIMITS.blocked(engine, holder, 'food_buff'):
                continue
            limits = FOOD.food_limits(engine, holder)
            if limits and holder.counters.get('lim:food_buff_consumed', 0) >= limits['per_scene']:
                continue
            answer = engine.rulings.decide(dict(type='mirror_herb', unit=buff['item'],
                actor_id=holder.entity_id, buff_id=buff['id'], source_actor_id=source_actor.entity_id,
                stat=stat, before=before, after=after, text='이 실제 전투단계 상승에 흉내허브 버프를 교환합니까?'))
            if answer is not True:
                continue
            event['selected'] = (holder, buff['id'])
            observe_positive_stage(engine, source_actor, stat, before, after, recipient=holder)
    finally:
        if previous is None:
            del engine._csv_food_stage_event
        else:
            engine._csv_food_stage_event = previous


def observe_positive_stage(engine, source_actor, stat, before, after, *, recipient=None):
    event = getattr(engine, '_csv_food_stage_event', None)
    if (not isinstance(event, dict) or event.get('source_actor') is not source_actor
            or (event.get('stat'), event.get('before'), event.get('after')) != (stat, before, after)
            or not event.get('selected') or event['selected'][0] is not recipient):
        raise ValueError('Mirror Herb consumption requires its selected actual native stage event')
    holder, buff_id = event['selected']
    event['selected'] = None
    buff = _buff(holder, buff_id)
    if validate_native(holder, buff)['kind'] != 'mirror_herb':
        raise ValueError('selected native stage reaction needs its actual Mirror Herb buff')
    delta = after - before
    _spend(engine, holder, buff, 'mirror_positive_stage',
           {'source_actor_id': source_actor.entity_id, 'stat': stat, 'before': before, 'after': after, 'delta': delta})
    engine.change_stage(holder, stat, delta)
    return {'holder_id': holder.entity_id, 'stat': stat, 'delta': delta, 'buff_id': buff_id}


def prepare_save(engine, actor, buff_id, condition):
    buff = _buff(actor, buff_id)
    if validate_native(actor, buff)['kind'] != 'recovery_herb_playtest':
        raise ValueError('actual selected Playtest Recovery Herb required')
    return engine.consume_food_buff(actor, buff_id=buff_id, save_condition=condition)


def saving_bonus(engine, actor, condition):
    import food_effects as FOOD
    return FOOD.save_bonus(engine, actor, condition)


def activate_sweet(engine, actor, buff_id, *, disposition=None):
    if not engine.encounter_active:
        raise ValueError("Sweet Confection next-turn lifetime requires an active encounter")
    buff = _buff(actor, buff_id)
    if validate_native(actor, buff)['kind'] != 'sweet_confection_homebrew':
        raise ValueError("selected buff is not the homebrew Sweet Confection")
    import food_effects as FOOD
    actual = FOOD._flavor_disposition(actor, '단맛')
    if disposition is not None and disposition != actual:
        raise ValueError('Sweet disposition must match the actual source-backed Nature')
    import state_grants as GRANTS
    return GRANTS.transition(engine, actor,
        lambda staged, subject: _activate_sweet(staged, subject, buff_id, actual))


def _activate_sweet(engine, actor, buff_id, disposition):
    buff = _buff(actor, buff_id)
    amount = 2 if disposition == "liked" else 1
    import combat_timing as TIMING
    serial = actor.custom_conditions.get("combat_turn_serial", 0)
    effect_id = "csv-sweet:" + buff_id
    receipt = _spend(engine, actor, buff, 'sweet_self_activation',
        {'kind': 'timed_modifiers', 'effect_id': effect_id, 'evasion': amount,
         'disposition': disposition, 'until': 'end_of_next_turn'})
    TIMING.install(engine, actor, {"source": buff["item"], "effect_contract": True, "effect_id": effect_id,
        'csv_sweet': True, 'buff_id': buff_id,
        "turn_owner": actor, "turn_deadline": serial + 1, "encounter_end": True, "evasion_modifier": amount})
    if disposition == "disliked":
        engine.apply_status(actor, "난동", source=buff["item"], applied_by=actor)
    return {'status': 'consumed', 'buff_id': buff_id, 'receipt': receipt['sequence'], **receipt['benefit']}


def legacy_occupancy(actor):
    state = actor.spec.get(STATE)
    if state is None:
        return 0
    validate_actor(actor)
    return len(state['buffs'])


def _legacy_plan(engine, actor, buff_id):
    import world_entities as WORLD, consumption_execution as EXECUTION
    import common_checks as C, food_effects as FOOD
    validate_actor(actor)
    state=actor.spec.get(STATE,{})
    matches=[b for b in state.get('buffs',[]) if b['id']==buff_id]
    if len(matches)!=1:raise ValueError('one actual legacy CSV food observation required')
    old=matches[0]
    choice=source_choice(engine.r,old['item_id'],old['clause_id'])
    C.integer(old.get('created_at'),'observed legacy food creation time',0,engine.elapsed_seconds)
    if FOOD.slots(actor)>FOOD.buff_capacity(engine,actor):
        raise ValueError('legacy food exceeds the actual current slot capacity; GM must reconcile the conflicting observations')
    events=[r for r in state['receipts'] if r.get('event')=='consumed_item' and r.get('buff_id')==buff_id]
    if (len(events)!=1 or events[0].get('item_id')!=old['item_id']
            or events[0].get('at')!=old['created_at']):
        raise ValueError('legacy food lacks its exact original item event; GM source reconciliation required')
    index=WORLD.actor_index(engine)
    payer=index.get(events[0].get('user_id'))
    payment=old.get('payment')
    if payer is None or not isinstance(payment,dict) or payment.get('item_id')!=old['item_id'] or payment.get('count')!=1:
        raise ValueError('legacy food lacks its actual source payer/payment; GM source reconciliation required')
    originals=[r for r in EXECUTION.validate(payer).values() if r['item_stock'] is payment]
    if (len(originals)!=1 or originals[0]['outcome']!='paid' or originals[0]['results']
            or originals[0]['target_id'] is not None or originals[0]['at']!=old['created_at']):
        raise ValueError('legacy food needs one unapplied actual original stock payment; GM source reconciliation required')
    if payment.get('kind') not in ('quantity','held_instance') or (payment['kind']=='quantity' and payment.get('selected_variant') is not True):
        raise ValueError('legacy food payment does not match the old source adapter')
    uses=[b for holder in index.values() for b in holder.spec.get(STATE,{}).get('buffs',[]) if b.get('payment') is payment]
    if len(uses)!=1:raise ValueError('legacy food payment is duplicated; GM source reconciliation required')
    return old,choice,payer,originals[0]


def adopt_legacy(engine,actor,buff_id,*,reason):
    """Explicit GM source reconciliation, without new intake, time or payment."""
    if not isinstance(reason,str) or not reason.strip():raise ValueError('GM legacy food reconciliation reason required')
    old,choice,payer,original=_legacy_plan(engine,actor,buff_id)
    import state_grants as GRANTS,food_effects as FOOD,consumption_execution as EXECUTION
    def apply(staged,subject,*others):
        old,choice,payer,original=_legacy_plan(staged,subject,buff_id)
        state=subject.spec[STATE]
        state['buffs'].remove(old)
        buff=FOOD.grant_buff(staged,subject,old['item_id'],effect(choice),source=FOOD.FOOD,source_selection=choice)
        if buff is None:raise ValueError('legacy food cannot currently gain its common slot; GM reconciliation required')
        origin={'actor_id':subject.entity_id,'legacy_buff_id':buff_id,'stock_receipt_id':original['receipt_id'],
                'payer_id':payer.entity_id,'adopted_at':staged.elapsed_seconds,'reason':reason}
        buff.update(item_stock=old['payment'],csv_legacy_origin=deepcopy(origin))
        state['receipts'].append({'event':'legacy_adopted','buff_id':buff_id,'common_buff_id':buff['id'],
                                  'origin':deepcopy(origin),'observation':old})
        EXECUTION.finish(payer,old['payment'],target_id=subject.entity_id,outcome='applied',
                         results=[{'kind':'digestion_buff','id':buff['id']}])
        return {'status':'legacy_adopted','buff_id':buff['id'],'legacy_buff_id':buff_id,
                'observed_creation_at':old['created_at'],'adopted_at':staged.elapsed_seconds}
    return GRANTS.transition(engine,actor,apply,participants=() if payer is actor else (payer,))


def validate_actor(actor):
    state = actor.spec.get(STATE)
    if state is None:
        return True
    if (not isinstance(state, dict) or state.get("version") != 1 or type(state.get("next")) is not int
            or state["next"] < 1 or not isinstance(state.get("buffs"), list) or not isinstance(state.get("receipts"), list)):
        raise ValueError("remaining CSV food state is invalid")
    seen = set()
    if any(not isinstance(row,dict) for row in state['receipts']):raise ValueError('typed legacy CSV food history required')
    for buff in state["buffs"]:
        if not isinstance(buff, dict):
            raise ValueError('legacy CSV food observation must be a record')
        row = definition(actor.r, buff.get("item_id"))
        if (not isinstance(buff, dict) or not isinstance(buff.get("id"), str) or buff["id"] in seen or row is None
                or buff.get("clause_id") != row["clause_id"] or buff.get("kind") != row["kind"]):
            raise ValueError("remaining CSV food buff identity is invalid")
        seen.add(buff["id"])
    return True


def validate_world(engine, index):
    import common_checks as C, effect_instances as INSTANCES
    POLICY.policy(engine.r)
    for actor in index.values():
        validate_actor(actor)
        records=list(actor.buffs)+actor.spec.get('food_consumption_receipts',[])
        for record in records:
            origin=record.get('csv_legacy_origin') if isinstance(record,dict) else None
            if origin is None:continue
            if (not isinstance(origin,dict) or set(origin)!={'actor_id','legacy_buff_id','stock_receipt_id','payer_id','adopted_at','reason'}
                    or not isinstance(origin.get('reason'),str) or not origin['reason'].strip()):
                raise ValueError('typed legacy food reconciliation origin required')
            C.integer(origin['adopted_at'],'actual legacy reconciliation time',0,engine.elapsed_seconds)
            holder=index.get(origin.get('actor_id'));payer=index.get(origin.get('payer_id'))
            if holder is None or payer is None:raise ValueError('actual legacy food source actors required')
            events=[r for r in holder.spec.get(STATE,{}).get('receipts',[]) if r.get('event')=='legacy_adopted' and r.get('origin')==origin]
            common_id=record.get('buff_id',record.get('id'))
            if len(events)!=1 or events[0].get('common_buff_id')!=common_id:raise ValueError('legacy food lacks its actual one-time reconciliation event')
            old=events[0].get('observation')
            choice=validate_native(actor,record)
            if (not isinstance(old,dict) or old.get('id')!=origin['legacy_buff_id']
                    or old.get('item_id')!=choice['item_id'] or old.get('clause_id')!=choice['clause_id']
                    or old.get('kind')!=choice['kind']):
                raise ValueError('legacy food reconciliation changed its actual original source observation')
            C.integer(old.get('created_at'),'observed original legacy food time',0,origin['adopted_at'])
            creation=record[INSTANCES.KEY]['ownership'][0]
            if creation['holder_id']!=holder.entity_id or creation['at']!=origin['adopted_at']:
                raise ValueError('legacy reconciliation must retain its actual new instance creation boundary')
            payment=payer.spec.get('stock_consumption_receipts',{}).get(origin.get('stock_receipt_id'))
            if (not isinstance(payment,dict) or payment.get('outcome')!='applied'
                    or payment.get('target_id')!=holder.entity_id or payment.get('at')!=old['created_at']
                    or payment.get('results')!=[{'kind':'digestion_buff','id':common_id}]
                    or payment.get('item_stock')!=record.get('item_stock')
                    or payment.get('item_stock') is not old.get('payment')
                    or payment['item_stock'].get('item_id')!=choice['item_id']):
                raise ValueError('legacy food lost its actual original applied stock payment')
    return True
