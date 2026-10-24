"""C09-089: one observed actual Smoke Ball use creates native Smokescreen.

The original supplies Blast 3 and the Smokescreen effect, but no action cost or
placement range. A GM identifies an actual use and its actual center; this does
not declare a Free Action or borrow the Move's range/frequency/knowledge cost.
"""
from copy import deepcopy
from dataclasses import replace

import common_checks as C
import consumption_execution as EXECUTION
import equipment_item_contracts as ITEMS
import resolution_transaction as TX

SOURCES = ('item/연막탄', 'item/연막탄-1')
MOVE = 'move/연막'
KEY = 'smoke_ball_uses'
SOURCE_SHA256 = 'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'
ZONE = {'accuracy_penalty': -3, 'until': 'encounter_end or 안개제거/날려버리기'}
AUTHORITY = {'source': 'input/ch09-equipment.md:989',
             'original': 'PTU Core 1.05 p302', 'geometry': 'blast 3',
             'declaration_cells': 'burst 3', 'move_id': MOVE,
             'accuracy_penalty': -3, 'action_cost': None, 'range_limit': None}


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be nonempty text')
    return value


def definition(rules, source):
    """Reauthenticate both current selected declarations on every public entry."""
    if source not in SOURCES:
        raise ValueError('exact reviewed Smoke Ball source required')
    effects, header = rules.item_effects(source)
    chapter = rules.selection.units[ITEMS.BATTLE_TOOL_SOURCE]['source']
    expected = [{'type': 'create_terrain', 'terrain': '연막',
                 'cells': 'burst 3', 'consumable': True}]
    if (header.get('id') != source or rules._selected_rule(source) != source
            or effects != expected or chapter.get('sha256') != SOURCE_SHA256
            or chapter.get('file') != 'ch09-equipment.md'
            or header.get('battle_tool', {}).get('stock_policy') != 'single_use'
            or source.endswith('-1') and header.get('price') != 500):
        raise ValueError('selected Smoke Ball definition needs its reviewed adapter')
    move = rules.move(MOVE)
    mechanics, _ = rules.move_mech(MOVE)
    if (rules._selected_rule(MOVE) != MOVE or move.get('id') != MOVE
            or mechanics != {'zone': ZONE}):
        raise ValueError('selected Smokescreen definition needs its reviewed adapter')
    return header


def _signed(row):
    return dict(row, sha256=TX.request_fingerprint(row))


def validate_actor(actor):
    rows = actor.spec.get(KEY, {})
    if type(rows) is not dict:
        raise ValueError('actual Smoke Ball use mapping required')
    fields = {'id', 'event_id', 'user_id', 'source_id', 'at', 'center', 'cells',
              'grid_size', 'reason', 'authority', 'payment_id', 'stock_selection'}
    for event_id, row in rows.items():
        _text(event_id, 'Smoke Ball use identity')
        if (type(row) is not dict or set(row) != fields | {'sha256'}
                or row['sha256'] != TX.request_fingerprint(
                    {k: v for k, v in row.items() if k != 'sha256'})):
            raise ValueError('actual Smoke Ball use evidence changed')
        identity = actor.entity_id + ':smoke-ball:' + event_id
        if (row['event_id'] != event_id or row['id'] != identity
                or row['user_id'] != actor.entity_id or row['authority'] != AUTHORITY):
            raise ValueError('Smoke Ball use identity or reviewed authority changed')
        definition(actor.r, row['source_id'])
        C.integer(row['at'], 'Smoke Ball use time', 0)
        _text(row['reason'], 'actual Smoke Ball use observation reason')
        _text(row['payment_id'], 'original Smoke Ball payment identity')
        if row['stock_selection'] is not None:
            _text(row['stock_selection'], 'Smoke Ball physical stock identity')
        size = row['grid_size']
        if type(size) is not list or len(size) != 2:
            raise ValueError('original Smoke Ball map size required')
        width, height = (C.integer(x, 'original Smoke Ball map dimension', 1) for x in size)
        from area_targets import point
        center = point(row['center'])
        if type(row['center']) is not list or not (0 <= center[0] < width and 0 <= center[1] < height):
            raise ValueError('actual Smoke Ball center outside original map')
        cells = row['cells']
        if type(cells) is not list or not cells or any(type(x) is not list for x in cells):
            raise ValueError('actual Smoke Ball cells required')
        points = [point(x) for x in cells]
        if (len(set(points)) != len(points) or points != sorted(points) or center not in points
                or any(not (0 <= x < width and 0 <= y < height
                            and abs(x-center[0]) <= 1 and abs(y-center[1]) <= 1)
                       for x, y in points)):
            raise ValueError('Smoke Ball cells differ from original clipped Blast 3')
    return rows


def validate_world(engine, index=None):
    import world_entities as WORLD
    index = WORLD.actor_index(engine) if index is None else index
    for actor in index.values():
        rows = validate_actor(actor)
        payments = EXECUTION.validate(actor)
        used = set()
        for row in rows.values():
            payment = payments.get(row['payment_id'])
            if payment is None or row['payment_id'] in used:
                raise ValueError('one original payment per actual Smoke Ball use required')
            used.add(row['payment_id'])
            stock = payment['item_stock']
            if (payment['at'] != row['at'] or row['at'] > engine.elapsed_seconds
                    or payment['target_id'] != actor.entity_id or payment['outcome'] != 'applied'
                    or stock.get('item_id') != row['source_id'] or stock.get('count') != 1
                    or stock.get('kind') not in ('quantity', 'held_instance')
                    or stock.get('instance_id') != row['stock_selection']
                    or payment['results'] != [{'kind': 'smoke_ball_use', 'id': row['id']}]):
                raise ValueError('Smoke Ball application differs from its actual stock payment')
            if row['stock_selection'] is not None:
                obj = getattr(engine, '_physical_objects', {}).get(row['stock_selection'])
                expected = {'source': row['source_id'], 'by_actor_id': actor.entity_id, 'at': row['at']}
                if (type(obj) is not dict or obj.get('item_rule_id') != row['source_id']
                        or obj.get('consumed') != expected):
                    raise ValueError('Smoke Ball actual physical consumption changed')
        # A generic payment cannot claim this native result without the matching
        # use original, even after its smoke has been cleared or the map changed.
        identities = {row['id'] for row in rows.values()}
        for payment in payments.values():
            for result in payment['results']:
                if result.get('kind') == 'smoke_ball_use' and result.get('id') not in identities:
                    raise ValueError('Smoke Ball payment lacks its actual use original')


def _plan(engine, r):
    import ninja as NINJA
    if NINJA.utility_authority(engine,r):return NINJA.utility_item(engine,r)
    import world_entities as WORLD
    import item_stock as STOCK
    import area_targets as AREA
    import partial_entities as PARTIAL
    WORLD.require_actors(engine, r.user, r.target)
    PARTIAL.require_complete(r.user, 'Smoke Ball use')
    definition(engine.r, r.source_id)
    if (type(r.accepted) is not bool or type(r.free) is not bool
            or type(r.resumable) is not bool or r.free or r.resumable
            or type(r.count) is not int or r.count != 1
            or any(x is not None for x in (r.duration_minutes, r.duration_reason,
                r.food_policy, r.selected_move, r.container_selection, r.shell_batch_id,
                r.fixed_accuracy, r.request_id, r.source_selection))):
        raise ValueError('Smoke Balls require one actual observed use without invented timing')
    if r.target is not r.user:
        raise ValueError('Smoke Ball use identifies a field center, not a creature target')
    if not r.user.on_field or r.user.captured or r.user.dead or r.user.fainted:
        raise ValueError('actual conscious on-field Smoke Ball user required')
    if r.held_selection is not None:
        _text(r.held_selection, 'one actual Smoke Ball physical instance')
    rows = validate_actor(r.user)
    stock = STOCK.prepare(engine, r.user, r.source_id, held_selection=r.held_selection)
    if engine.grid is None:
        return C.PendingDecision('Actual Smoke Ball Blast 3 requires its mapped placement',
            basis={'source': r.source_id, 'status': 'actual_smoke_ball_placement',
                   'action_cost': None, 'range_limit': None})
    if r.aim is None:
        return C.PendingDecision('GM observes the actual Smoke Ball use and its center',
            basis={'source': r.source_id, 'status': 'actual_smoke_ball_use',
                   'action_cost': None, 'range_limit': None})
    observation = r.aim if type(r.aim) is dict else None
    if observation is not None and set(observation) != {'center', 'event_id', 'reason'}:
        raise ValueError('Smoke Ball placement requires center, event_id and actual-use reason')
    center = AREA.point(observation['center'] if observation is not None else r.aim)
    if not engine.grid.inside(center):
        raise ValueError('Smoke Ball center lies outside map')
    if observation is None:
        return C.PendingDecision('GM observes the actual Smoke Ball use at the selected center',
            basis={'source': r.source_id, 'center': list(center),
                   'status': 'actual_smoke_ball_use', 'action_cost': None, 'range_limit': None})
    event_id = _text(observation['event_id'], 'actual Smoke Ball use identity')
    _text(observation['reason'], 'actual Smoke Ball use observation reason')
    if event_id in rows:
        raise ValueError('actual Smoke Ball use already observed; do not consume or recreate it')
    cells = engine.grid.ranged_blast(center, 3)
    return {'stock': stock, 'center': center, 'cells': cells,
            'event_id': event_id, 'reason': observation['reason']}


def prepare(engine, request):
    plan = _plan(engine, request)
    return plan if isinstance(plan, C.PendingDecision) else None


def consume(engine, request):
    import ninja as NINJA
    if NINJA.utility_authority(engine,request):return NINJA.utility_item(engine,request,consume=True)
    import state_grants as G
    import item_stock as STOCK
    import smoke_regions as SMOKE
    # Admission also precedes construction of a candidate graph. Invalid
    # actors/options and missing actual observation cannot mutate live state.
    before = _plan(engine, request)
    if isinstance(before, C.PendingDecision):
        return before

    def commit(e, actor):
        r = replace(request, user=actor, target=actor)
        plan = _plan(e, r)
        payment = STOCK.debit(e, actor, plan['stock'])
        move = {'_area_aim': plan['center'], '_effect_area_cells': plan['cells']}
        result = SMOKE.apply(e, actor, move, ZONE, r.source_id, 'C09-089 original blast 3')
        receipts = [row for row in EXECUTION.validate(actor).values() if row['item_stock'] is payment]
        if len(receipts) != 1:
            raise ValueError('actual original Smoke Ball payment required')
        identity = actor.entity_id + ':smoke-ball:' + plan['event_id']
        row = _signed({'id': identity, 'event_id': plan['event_id'], 'user_id': actor.entity_id,
            'source_id': r.source_id, 'at': e.elapsed_seconds, 'center': list(plan['center']),
            'cells': [list(cell) for cell in result['cells']],
            'grid_size': [e.grid.w, e.grid.h], 'reason': plan['reason'],
            'authority': deepcopy(AUTHORITY), 'payment_id': receipts[0]['receipt_id'],
            'stock_selection': r.held_selection})
        actor.spec.setdefault(KEY, {})[plan['event_id']] = row
        EXECUTION.finish(actor, payment, target_id=actor.entity_id, outcome='applied',
                         results=[{'kind': 'smoke_ball_use', 'id': identity}])
        validate_world(e)
        return deepcopy(row)

    return G.transition(engine, request.user, commit, include_grid=True)


def observe_use(engine, actor, center, *, event_id, reason, item='item/연막탄', held_selection=None):
    """Public GM observation of an actual use, with no invented action/range."""
    return engine.use_item(actor, item, held_selection=held_selection,
        aim={'center': center, 'event_id': event_id, 'reason': reason})
