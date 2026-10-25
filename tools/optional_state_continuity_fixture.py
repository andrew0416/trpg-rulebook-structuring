"""Two real blessing worlds, published only after a whole native case succeeds."""
from functools import wraps
from chained_case_lifecycle import bind_case_lifecycle, defer_case_commit

STAGES = (
    'test_white_yang_native_accuracy_and_stages_obey_shared_caps',
    'test_black_yin_extra_evasion_uses_shared_six_and_final_nine_caps',
    'test_yang_yin_breather_clears_combat_components_but_keeps_movement_clock',
    'test_yang_yin_recall_resets_combat_components_without_ending_movement',
)


def prepare(cases):
    selected = {case._testMethodName: case for case in cases if case._testMethodName in STAGES}
    if not selected:
        return None
    if len(selected) != sum(case._testMethodName in STAGES for case in cases):
        raise ValueError('duplicate optional-state stage')
    context = {'worlds': {}, 'blocked': None, 'prefix_builds': 0, 'events': []}
    def poison(reason):
        if context['blocked'] is None:
            context['blocked'] = reason
    for case in selected.values():
        if hasattr(case, '_optional_continuity'):
            raise ValueError('optional-state case already prepared')
        case._optional_continuity = context
        bind_case_lifecycle(case, poison)
    return [selected[name] for name in STAGES if name in selected] + [
        case for case in cases if case._testMethodName not in STAGES]


def stage(operation):
    @wraps(operation)
    def execute(case):
        context = getattr(case, '_optional_continuity', None)
        if context is not None and context['blocked'] is not None:
            raise AssertionError('optional-state predecessor unverified: ' + context['blocked'])
        case._optional_outputs = {}
        value = operation(case)
        if context is not None:
            outputs = dict(case._optional_outputs)
            if not outputs:
                raise AssertionError('optional-state stage produced no actual world')
            def commit():
                context['worlds'].update(outputs)
                context['events'].append({'id': case.id(), 'published': sorted(outputs),
                                          'prefix_builds': context['prefix_builds']})
            defer_case_commit(case, commit)
        return value
    return execute


def publish(case, clause, actors, phase):
    engine, owner, first, second, foe = actors
    assert all(any(actor is actual for actual in engine.everyone)
               for actor in (owner, first, second, foe))
    case._optional_outputs[clause] = {'actors': actors, 'phase': phase}


def active_world(case, clause, feature, *, consumer):
    context = getattr(case, '_optional_continuity', None)
    if context is not None and clause in context['worlds']:
        world = context['worlds'][clause]
        expected = {'active'} if consumer == 'breather' else {'active', 'breather'}
        if world['phase'] not in expected:
            raise AssertionError('optional-state predecessor has incompatible phase')
        return world
    # A sparse consumer needs only its actual active blessing, never earlier tests.
    actors = case.fixture(feature)
    engine, owner, first, second, _ = actors
    result = engine.activate_optional_state_effect(owner, clause, targets=(first, second))
    case.assertEqual(set(result['targets']), {first.entity_id, second.entity_id})
    if context is not None:
        context['prefix_builds'] += 1
    return {'actors': actors, 'phase': 'active'}
