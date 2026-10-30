"""Native Apothecary Blend quantities loaded into real reusable containers.

A Blend is a crafted portion, never a fabricated Rules item or a new owned body.
The existing researcher creation ledger and quantity pay the actual transfer.
"""
from copy import deepcopy
import common_checks as C


def native(engine, maker, blend):
    import researcher_fields as R
    row = (R.state(maker) or {}).get('blends', {}).get(blend)
    if (maker.kind != 'trainer' or not isinstance(row, dict) or row.get('feature') != R.BLEND
            or row.get('clause_id') != R.clause(R.BLEND) or type(row.get('extended_only')) is not bool):
        raise ValueError('actual native Medicinal Blend creation required')
    parts = row.get('components')
    if (type(parts) is not list or len(parts) != 2
            or blend != R.BLEND_PREFIX + '+'.join(parts)):
        raise ValueError('actual two-component Blend identity required')
    selected = [R._medicine(engine, uid) for uid in parts]
    kinds = sorted(part[3] for part in selected)
    if (kinds == ['restorative', 'restorative'] and R._signature(selected[0][2]) == R._signature(selected[1][2])
            or kinds not in (['restorative', 'restorative'], ['restorative', 'x'])):
        raise ValueError('native Blend recipe no longer matches its two components')
    made = row.get('made')
    if not isinstance(made, list) or not made:raise ValueError('native Blend creation receipt required')
    for creation in made:
        C.integer(creation.get('at'), 'actual Blend creation time', 0, engine.elapsed_seconds)
        R._text(creation.get('reason'), 'actual Blend creation reason')
        inputs = creation.get('inputs')
        if type(inputs) is not list or len(inputs) != 2:raise ValueError('actual Blend input identities required')
        actual = [R._component(engine, maker, key) for key in inputs]
        if [part['item_id'] for part in actual] != parts:
            raise ValueError('Blend components disagree with actual creation inputs')
        if any(part['extended_only'] for part in actual) and not row['extended_only']:
            raise ValueError('Patch-derived Blend must retain Extended-only application')
    bottled = row.get('bottled', {})
    if type(bottled) is not dict:raise ValueError('actual Blend transfers required')
    remaining = C.integer(maker.spec.get('items', {}).get(blend, 0), 'remaining native Blend quantity', 0)
    if remaining + len(bottled) > len(made):raise ValueError('Blend quantity and physical transfers exceed actual production')
    return row


def load(engine, maker, blend, *, container_selection, reason):
    """Transfer one actually crafted dose into an observed-empty held bottle."""
    import researcher_fields as R, item_containers as J, state_grants as G
    import world_entities as W, movement_actions as MOVEMENT, turn as TURN
    W.require_actors(engine, maker)
    MOVEMENT.boundary(engine, 'load_container');R._outside(engine)
    R._text(reason, 'actual Blend transfer reason')
    if not TURN.can_act(engine, maker):raise ValueError('acting Blend holder required')
    native(engine, maker, blend);R._owned_count(maker, blend)
    J.empty_body(engine, maker, container_selection)
    def apply(e, m):
        row = native(e, m, blend);R._owned_count(m, blend)
        jar = J.empty_body(e, m, container_selection)
        identity = jar['id'] + ':contents:' + str(len(jar[J.KEY]['portions']) + 1)
        before = m.spec['items'][blend]
        m.spec['items'][blend] -= 1
        row.setdefault('bottled', {})[identity] = {
            'id': identity, 'container_id': jar['id'], 'maker_id': m.entity_id,
            'blend_id': blend, 'at': e.elapsed_seconds, 'count': 1, 'reason': reason,
            'quantity_before': before, 'quantity_after': before - 1,
            'creation_count': len(row['made']), 'creation': deepcopy(row['made'][-1])}
        stock = {'kind': 'researcher_blend', 'item_id': blend, 'count': 1,
                 'maker_id': m.entity_id, 'product_id': identity}
        return J.deposit(e, m, container_selection, item_id=blend, stock=stock,
                         source=R.BLEND, reason=reason, product_id=identity)
    return G.transition(engine, maker, apply)


def validate_portion(engine, obj, portion, index):
    import researcher_fields as R
    stock = portion.get('input_stock', {})
    maker = index.get(stock.get('maker_id'))
    if maker is None:raise ValueError('actual Blend maker missing')
    blend = portion.get('item_id');row = native(engine, maker, blend)
    record = row.get('bottled', {}).get(portion['id'])
    expected = {'kind': 'researcher_blend', 'item_id': blend, 'count': 1,
                'maker_id': maker.entity_id, 'product_id': portion['id']}
    if (stock != expected or not isinstance(record, dict) or portion.get('source') != R.BLEND
            or record.get('id') != portion['id'] or record.get('container_id') != obj['id']
            or record.get('maker_id') != maker.entity_id or record.get('blend_id') != blend
            or record.get('at') != portion.get('loaded_at') or record.get('reason') != portion.get('reason')
            or portion.get('loaded_by') != maker.entity_id):
        raise ValueError('Blend contents lost their actual native quantity transfer')
    C.integer(record.get('count'), 'one transferred Blend', 1, 1)
    before = C.integer(record.get('quantity_before'), 'native pre-transfer Blend quantity', 1)
    if type(record.get('quantity_after')) is not int or record['quantity_after'] != before - 1:
        raise ValueError('Blend loading must pay exactly one actual quantity')
    count = C.integer(record.get('creation_count'), 'actual creation receipt count', 1, len(row['made']))
    if record.get('creation') != row['made'][count - 1] or record['creation']['at'] > record['at']:
        raise ValueError('Blend loading lost its preceding actual creation receipt')
    if portion.get('status') == 'stored':
        if 'fling' in portion or 'fling_results' in portion or 'benefit_suppression' in portion:
            raise ValueError('stored Blend cannot claim a Fling consumption')
    elif portion.get('status') == 'consumed':
        facts = portion.get('fling', {})
        completion = getattr(engine, '_move_completions', {}).get(facts.get('completion_id'), {})
        launch = completion.get('fling_launch', {})
        admitted = launch.get('admissions', {}).get(str(completion.get('id')) + '|consumer', {})
        dispatch = getattr(engine, '_effect_dispatch_receipts', {}).get(admitted.get('effect_receipt'), {})
        actor = completion.get('actor');target = index.get(facts.get('target_id'))
        if (actor is None or target is None or completion.get('move_id') != 'move/내던지기'
                or facts != {'completion_id': completion.get('id'), 'move_id': completion.get('move_id'),
                             'actor_id': actor.entity_id, 'target_id': target.entity_id}
                or portion.get('consumed_by') != target.entity_id or admitted.get('consumed') is not True
                or admitted.get('actor_id') != actor.entity_id or admitted.get('target_id') != target.entity_id
                or admitted.get('instance_id') != obj['id'] or admitted.get('plan', {}).get('kind') != 'blend'
                or admitted.get('plan', {}).get('content_id') != portion['id']
                or admitted.get('plan', {}).get('blend_id') != blend
                or dispatch.get('actor') is not actor or dispatch.get('target') is not target
                or dispatch.get('source_id') != completion.get('move_id') or not dispatch.get('fling_applied')):
            raise ValueError('consumed Blend needs its actual native Fling admission')
        if (completion.get('phase') == 'complete'
                and launch.get('consumer_result', {}).get('content_id') != portion['id']):
            raise ValueError('completed Blend intake lost its native consumer result')
        suppression = portion.get('benefit_suppression')
        if suppression is not None:
            import glitch_bender as GLITCH
            if (type(suppression) is not dict or set(suppression) != {'source', 'target_id', 'at'}
                    or suppression['source'] != GLITCH.CODE or suppression['target_id'] != portion.get('consumed_by')
                    or suppression['target_id'] not in index or suppression['at'] != portion.get('consumed_at')):
                raise ValueError('suppressed Blend intake needs its actual Object Not Found recipient')
            if any(list(result) != [0, 0] for result in portion.get('fling_results', [])):
                raise ValueError('suppressed Blend intake cannot retain a native component benefit')
    return row


def validate_world(engine, index):
    import researcher_fields as R, item_containers as J
    for maker in index.values():
        for blend, row in (R.state(maker) or {}).get('blends', {}).items():
            if not row.get('bottled'):continue
            native(engine, maker, blend)
            for identity, record in row['bottled'].items():
                obj = getattr(engine, '_physical_objects', {}).get(record.get('container_id'), {})
                portion = obj.get(J.KEY, {}).get('portions', {}).get(identity)
                if not portion:raise ValueError('native Blend transfer lost its physical contents')
                validate_portion(engine, obj, portion, index)
    return True


def profile(engine, actor, target, instance_id, options):
    import item_containers as J, world_entities as W, fling_consumables as F
    obj = getattr(engine, '_physical_objects', {}).get(instance_id, {})
    state = obj.get(J.KEY, {})
    portion = state.get('portions', {}).get(state.get('current'))
    if not portion or portion.get('input_stock', {}).get('kind') != 'researcher_blend':return None
    J.validate_object(engine, obj, W.actor_index(engine))
    row = validate_portion(engine, obj, portion, W.actor_index(engine))
    if row['extended_only']:return None
    if options:raise ValueError('Medicinal Blend has no Vitamin selection options')
    return {'kind': 'blend', 'item_rule_id': obj['item_rule_id'], 'instance_id': instance_id,
            'content_id': portion['id'], 'blend_id': portion['item_id'], 'options': {},
            'components': [F.profile(engine, actor, target, uid) for uid in row['components']]}


def consume(engine, actor, target, admission, plan):
    """Claim the actual native Fling admission; consume its contents once."""
    import item_containers as J, fling_consumables as F, fling_move as FLING
    if profile(engine, actor, target, plan['instance_id'], plan['options']) != plan:
        raise ValueError('Fling Blend plan changed before actual intake')
    admitted = FLING.consume_item_admission(engine, actor, target, admission, plan)
    obj = engine._physical_objects[plan['instance_id']]
    state = obj[J.KEY];portion = state['portions'][plan['content_id']]
    if (state['current'] != portion['id'] or portion['status'] != 'stored'
            or admitted['instance_id'] != obj['id'] or admitted['consumer_plan'] != plan):
        raise ValueError('Fling requires these actual unconsumed Blend contents')
    portion.update(status='consumed', consumed_at=engine.elapsed_seconds, consumed_by=target.entity_id,
        fling={'completion_id': admitted['completion_id'], 'move_id': admitted['move_id'],
               'actor_id': actor.entity_id, 'target_id': target.entity_id})
    state['current'] = None
    # Same native component intake as an unblended restorative/X item.
    import glitch_bender as GLITCH
    blocked = GLITCH.benefits_blocked(target)
    results = [F.apply_medicine(engine, actor, target, component) for component in plan['components']]
    portion = engine._physical_objects[plan['instance_id']][J.KEY]['portions'][plan['content_id']]
    portion['fling_results'] = deepcopy(results)
    if blocked:
        # FLING-BLEND-CODE-1: contents paid, no component benefit installed.
        portion['benefit_suppression'] = {'source': GLITCH.CODE, 'target_id': target.entity_id, 'at': portion['consumed_at']}
    return {'status': 'consumed_contents', 'item_rule_id': plan['item_rule_id'],
            'instance_id': plan['instance_id'], 'content_id': plan['content_id'],
            'blend_id': plan['blend_id'], 'result': results}


def validate_result(engine, completion, launch):
    import world_entities as W, item_containers as J
    result = launch['consumer_result'];plan = launch['plan'];actor = completion['actor']
    obj = engine._physical_objects.get(plan['instance_id'], {})
    index = W.actor_index(engine)
    J.validate_object(engine, obj, index)
    admitted = launch.get('admissions', {}).get(completion['id'] + '|consumer', {})
    native_plan = admitted.get('plan', {})
    portion = obj.get(J.KEY, {}).get('portions', {}).get(result.get('content_id'), {})
    expected = {'completion_id': completion['id'], 'move_id': completion['move_id'],
                'actor_id': actor.entity_id, 'target_id': admitted.get('target_id')}
    if (not portion or admitted.get('consumed') is not True or native_plan.get('kind') != 'blend'
            or native_plan.get('content_id') != portion.get('id') or native_plan.get('blend_id') != portion.get('item_id')
            or native_plan.get('instance_id') != obj.get('id')
            or portion.get('status') != 'consumed' or portion.get('fling') != expected
            or portion.get('consumed_by') != admitted.get('target_id')
            or admitted.get('target_id') not in index or admitted.get('actor_id') != actor.entity_id
            or result != {'status': 'consumed_contents', 'item_rule_id': obj.get('item_rule_id'),
                          'instance_id': obj.get('id'), 'content_id': portion.get('id'),
                          'blend_id': portion.get('item_id'), 'result': portion.get('fling_results')}):
        raise ValueError('Fling Blend result lost its actual carrier/contents/recipient')
    dispatch = getattr(engine, '_effect_dispatch_receipts', {}).get(admitted.get('effect_receipt'))
    if (not dispatch or dispatch['actor'] is not actor or dispatch['target'] is not index[admitted['target_id']]
            or dispatch['source_id'] != completion['move_id'] or not dispatch.get('fling_applied')):
        raise ValueError('Fling Blend lost its native final effect dispatch')
