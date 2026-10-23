"""C09-080: one real tool pays for the selected native Hazard placement.

The item supplies one use without learning the Move. The native Move producer
keeps its action, frequency, restrictions and completion; hazard_state owns its
geometry, field instances, entry triggers and lifetime.
"""
from dataclasses import replace

import common_checks as C

SOURCES = {
    'item/마름쇠': ('move/압정뿌리기',),
    'item/독-마름쇠': ('move/독압정',),
    'item/마름쇠-독-마름쇠': ('move/압정뿌리기', 'move/독압정'),
}
SOURCE_NAMES = {'move/압정뿌리기': '압정', 'move/독압정': '독압정'}


def _plan(engine, r):
    import equipment_item_contracts as CONTRACTS
    import world_entities as WORLD
    import hazard_state as HAZARDS
    import effects as FX
    import item_stock as STOCK

    options = SOURCES.get(r.source_id)
    if options is None:
        raise ValueError('reviewed Caltrops item source required')
    CONTRACTS.selected_item(engine.r, r.source_id)
    if (r.free or r.count != 1 or r.resumable or any(x is not None for x in
            (r.duration_minutes, r.duration_reason, r.food_policy,
             r.container_selection, r.shell_batch_id, r.fixed_accuracy))):
        raise ValueError('Caltrops require one Standard Action item application')
    if r.target is not r.user:
        raise ValueError('Caltrops use explicit field cells, not a creature target')
    if WORLD.actor_index(engine).get(r.user.entity_id) is not r.user:
        raise ValueError('actual Caltrops user required')
    if not r.user.on_field or r.user.captured or r.user.dead:
        raise ValueError('actual on-field Caltrops user required')
    expected = {'type': 'grant_move', 'moves': [SOURCE_NAMES[x] for x in options],
                'target': 'user', 'consumable': True}
    if len(options) == 2:
        expected['note'] = '둘 중 하나'
    if engine.r.item_effects(r.source_id)[0] != [expected]:
        raise ValueError('selected Caltrops effect differs from its reviewed source')
    move_id = r.selected_move or (options[0] if len(options) == 1 else None)
    if move_id is None:
        return C.PendingDecision('Select Spikes or Toxic Spikes for the actual Caltrops item')
    if move_id not in options or engine.r._selected_rule(move_id) != move_id:
        raise ValueError('selected Caltrops Move differs from the item source')
    # Rules.move_mech authenticates and adapts the reviewed native declaration;
    # bind validates its real range and contiguous eight-cell placement.
    move = HAZARDS.bind(engine, r.user, engine.r.move(move_id), r.aim)
    mechanics = engine.r.move_mech(move_id)[0]
    effects = HAZARDS.field_effects(mechanics)
    if not effects:
        raise ValueError('selected Caltrops Move lacks its native field producer')
    FX.preflight_effects(engine, r.user, r.user, effects, move_id)
    stock = STOCK.prepare(engine, r.user, r.source_id, held_selection=r.held_selection)
    return {'move': move, 'effects': effects, 'stock': stock}


def prepare(engine, request):
    plan = _plan(engine, request)
    return plan if isinstance(plan, C.PendingDecision) else None


def consume(engine, request):
    import state_grants as G
    import item_stock as STOCK
    import consumption_execution as EXECUTION
    import heavy_injury_adapter as HEAVY

    def commit(e, actor):
        r = replace(request, user=actor, target=actor)
        plan = _plan(e, r)
        if isinstance(plan, C.PendingDecision):
            return plan
        previous = set(getattr(e, '_move_completions', {}))
        regions = {row['region_id'] for env in e.hazards.values() for row in env['instances']}
        pending = None
        try:
            native_result = e.use_move_on(actor, actor, plan['move']['id'], e.everyone, aim=r.aim)
        except HEAVY.HeavyPending as error:
            # Native empty-field activation commits its actual Standard/frequency
            # prefix before raising. Keep that packet and its consumed tool;
            # the existing GM decision owns the still-unexecuted consequences.
            event = e._heavy_events.get(error.event_id)
            if (event is None or event.get('attacker') is not actor or
                    event.get('move', {}).get('id') != plan['move']['id'] or
                    event.get('producer') != 'Engine.use_move.native_standard'):
                raise
            pending = error.event_id
        completed = [row for identity, row in getattr(e, '_move_completions', {}).items()
            if identity not in previous and row['actor'] is actor and
            row['move_id'] == plan['move']['id'] and row.get('activation') == 'empty_area_field'
            and row['phase'] == 'complete' and row['sealed']]
        if not completed and pending is None:
            return native_result if isinstance(native_result, C.PendingDecision) else (0, 0)
        if len(completed) > 1:
            raise ValueError('one actual Caltrops Move activation required')
        payment = STOCK.debit(e, actor, plan['stock'])
        new_regions = sorted({row['region_id'] for env in e.hazards.values()
            for row in env['instances']} - regions)
        results = [{'kind': 'hazard_region', 'id': identity} for identity in new_regions]
        if completed:
            results.append({'kind': 'move_completion', 'id': completed[0]['id']})
        if pending:
            results.append({'kind': 'heavy_event', 'id': pending})
        if completed:
            EXECUTION.finish(actor, payment, target_id=actor.entity_id, outcome='applied', results=results)
        else:
            # The native activation exists but its field consequences still
            # await the original heavy decision. Link the real pending event
            # while retaining the stock owner's explicitly uncompleted state.
            receipts = [row for row in EXECUTION.validate(actor).values() if row['item_stock'] is payment]
            if len(receipts) != 1:
                raise ValueError('actual original Caltrops stock payment required')
            receipts[0].update(target_id=actor.entity_id, results=results)
        return {'source': r.source_id, 'clause_id': 'C09-080',
                'move_id': plan['move']['id'], 'payment': payment,
                'move_completion': completed[0]['id'] if completed else None,
                'hazard_regions': new_regions, 'heavy_pending': pending}

    result = G.transition(engine, request.user, commit, include_grid=True)
    if isinstance(result, dict) and result.get('heavy_pending'):
        raise HEAVY.HeavyPending(result['heavy_pending'])
    return result
