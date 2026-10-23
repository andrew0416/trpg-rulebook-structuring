"""Festival progression over the actual standard/super contest occurrence.

The source fixes score carry, one elimination and a final three-person contest.
Resource defaults/presets are user-adopted project policy, not source claims.
Tied elimination/winning still requires an explicit scoped GM decision.
"""
from copy import deepcopy
from native_rule_policy import PolicyPending


POLICY_CHOICES = {'introduction': ('repeat', 'retain'),
                  'stat_dice': ('reset', 'carry'),
                  'excitement': ('reset', 'carry'),
                  'last_move': ('reset', 'carry')}
_PRESETS = {
    'restart': dict(introduction='repeat', stat_dice='reset', excitement='reset', last_move='reset'),
    'retain_introduction': dict(introduction='retain', stat_dice='reset', excitement='reset', last_move='reset'),
    'carry_all': dict(introduction='retain', stat_dice='carry', excitement='carry', last_move='carry')}


def presets():
    """Return independent public preset definitions; fields can be overridden."""
    return deepcopy(_PRESETS)


def policy(value, occurrence, *, resolved=False):
    """Resolve None -> restart, then preset -> individual field overrides.

    Explicit sparse/complete dictionaries require scope=contest_id and reason.
    The resolved four-field policy is frozen for the entire Festival occurrence.
    `reset` pools mean pre-introduction pools; repeat adds a fresh introduction.
    """
    if value is None:
        if resolved:
            raise ValueError('resolved Festival policy required')
        return dict(scope=occurrence, reason='user-adopted project default: restart', **_PRESETS['restart'])
    if (type(value) is not dict
            or not {'scope', 'reason'} <= set(value)
            or set(value) - {*POLICY_CHOICES, 'scope', 'reason', 'preset'}
            or value['scope'] != occurrence or type(value['reason']) is not str
            or not value['reason'].strip()):
        raise ValueError('explicit scoped Festival resource interpretation required')
    if resolved and set(value) != {*POLICY_CHOICES, 'scope', 'reason'}:
        raise ValueError('resolved Festival policy must contain all four fields')
    name = value.get('preset', 'restart')
    if type(name) is not str or name not in _PRESETS:
        raise ValueError('unknown Festival preset')
    result = dict(scope=occurrence, reason=value['reason'], **_PRESETS[name])
    for key, choices in POLICY_CHOICES.items():
        if key in value:
            if type(value[key]) is not str or value[key] not in choices:
                raise ValueError('invalid Festival resource field: ' + key)
            result[key] = value[key]
    return result


def _scope(state, kind, candidates, scores):
    return {'festival': state['id'], 'subcontest': len(state['history']) + 1,
            'kind': kind, 'candidates': [c.entity_id for c in candidates],
            'scores': [[c.entity_id, scores[c]] for c in state['survivors']]}


def _decision(state, kind, candidates, scores, decisions):
    if len(candidates) == 1:
        return candidates[0], None
    scope = _scope(state, kind, candidates, scores)
    key = str(scope['subcontest']) + ':' + kind
    record = decisions.get(key)
    if record is None:
        raise PolicyPending('festival_tie_decision_required',
                            ({'key': key, 'scope': scope, 'choices': scope['candidates']},))
    if (type(record) is not dict or set(record) != {'value', 'reason', 'scope'}
            or record['scope'] != scope or type(record['value']) is not str
            or record['value'] not in scope['candidates']
            or type(record['reason']) is not str or not record['reason'].strip()):
        raise ValueError('Festival tie decision must select a current tied contestant with scope/reason')
    return next(c for c in candidates if c.entity_id == record['value']), deepcopy(record)


def _next(host, state):
    """Prepare only the next child; cumulative appeal/fumble are never erased."""
    choice = state['policy']
    actors = state['survivors']
    letters = sorted(actors, key=lambda c: c.letter)
    for c in actors:
        c.been_center = c.double_next = c.immune_fumble = False
        if choice['excitement'] == 'reset':
            c.excitement = 0
        if choice['last_move'] == 'reset':
            c.last_move = None
        if choice['stat_dice'] == 'reset':
            c.stat_dice = deepcopy(state['initial_pools'][c])
            if state['initial_style'][c] is not None:
                c._native_style_dice = deepcopy(state['initial_style'][c])
        c.intro_completed = choice['introduction'] == 'retain'
        c.letter = 'ABCDE'[letters.index(c)] if c.intro_completed else None
    host._coordinator_used.clear()
    host._flourish_used.clear()
    host._fashion_used.clear()
    host.__dict__.pop('last_standings', None)
    host._standard_run = None
    if choice['introduction'] == 'retain':
        host._standard_run = {
            'id': _child_id(state), 'contract': (actors, state['type'], state['variant']),
            'phase': 'round', 'table': host.r.mech('contest/position-tables')[str(len(actors))],
            'round': 0, 'slot': 0, 'round_type': None, 'pending': None}


def _child_id(state):
    return state['id'] + ':subcontest:' + str(len(state['history']) + 1)


def run(host, contestants, contest_type, chooser, *, contest_id,
        base_variant, resource_policy, decisions):
    if getattr(host, '_festival_busy', False) or host._standard_busy or host._paired_busy:
        raise ValueError('contest callback cannot reenter its own contest')
    if type(contest_id) is not str or not contest_id.strip():
        raise ValueError('Festival occurrence identity required')
    state = getattr(host, '_festival_run', None)
    choice = (policy(state['contract'][3], contest_id, resolved=True)
              if resource_policy is None and state is not None else policy(resource_policy, contest_id))
    if (base_variant not in ('standard', 'super')
            or (base_variant == 'super' and contest_type is not None)
            or (base_variant == 'standard' and contest_type not in host.r.mech('contest/type-match')['ring'])):
        raise ValueError('Festival requires a valid standard or super child format')
    if not callable(chooser) or not 3 <= len(contestants) <= 5 or len(set(contestants)) != len(contestants):
        raise ValueError('three to five distinct Pokemon contestants and chooser required')
    if type(decisions) is not dict or any(type(k) is not str for k in decisions):
        raise ValueError('explicit Festival decisions dictionary required')
    contract = (tuple(contestants), contest_type, base_variant, deepcopy(choice))
    import contest_halls as HALLS
    HALLS.native_context(host, contestants, historical=state is not None and state['phase'] == 'complete')
    if state is None:
        if host._standard_run is not None or host._paired_run is not None:
            raise ValueError('finish the existing contest before creating a Festival')
        for c in contestants:
            if c.intro_completed or hasattr(c, '_paired_state') or c in host._trainer_partners.values():
                raise ValueError('Festival starts with fresh Pokemon contestants')
            for move in c.moves:
                host.r.move_contest(move)
        state = {'id': contest_id, 'contract': contract, 'type': contest_type,
                 'variant': base_variant, 'policy': choice, 'phase': 'playing',
                 'survivors': tuple(contestants), 'eliminated': (), 'history': [],
                 'initial_pools': {c: deepcopy(c.stat_dice) for c in contestants},
                 'initial_style': {c: deepcopy(getattr(c, '_native_style_dice', None)) for c in contestants}}
        host._festival_run = state
    elif state['contract'] != contract or state['id'] != contest_id or state['policy'] != choice:
        raise ValueError('resume the original Festival participants, type and resource interpretation')
    elif state['phase'] == 'complete':
        HALLS.award_contest(host)
        return list(state['result'])  # Stable result receipt; no introductions/costs repeated.
    host._festival_busy = True
    try:
        while state['phase'] != 'complete':
            if state['phase'] == 'next':
                _next(host, state)
                state['phase'] = 'playing'
            if state['phase'] == 'playing':
                host._run_standard(state['survivors'], contest_type, chooser,
                                   variant=base_variant, contest_id=_child_id(state))
                state['phase'] = 'adjudication'
            actors = state['survivors']
            scores = {c: c.appeal - c.fumble for c in actors}
            kind = 'winner' if len(actors) == 3 else 'eliminate'
            extreme = (max if kind == 'winner' else min)(scores.values())
            candidates = tuple(c for c in actors if scores[c] == extreme)
            selected, evidence = _decision(state, kind, candidates, scores, decisions)
            # No mutation between detecting a tie and validating its exact response.
            row = {'participants': actors, 'scores': scores, kind: selected, 'decision': evidence,
                   'child_id': _child_id(state)}
            state['history'].append(row)
            if kind == 'winner':
                result = tuple(sorted(actors, key=lambda c: (c is not selected, -scores[c])))
                state.update(phase='complete', winner=selected, result=result)
                host.log('페스티벌 우승: ' + selected.name, 'contest/performance-stage')
                HALLS.award_contest(host)
                return list(result)
            state['eliminated'] += (selected,)
            state['survivors'] = tuple(c for c in actors if c is not selected)
            state['phase'] = 'next'
            host.log('페스티벌 탈락: ' + selected.name, 'contest/performance-stage')
    finally:
        host._festival_busy = False


def validate(host, known):
    """Check the occurrence, elimination lineage, tie receipts and actual child."""
    state = getattr(host, '_festival_run', None)
    if state is None:
        return
    if type(state) is not dict or state.get('phase') not in ('playing', 'adjudication', 'next', 'complete'):
        raise ValueError('invalid Festival phase')
    original, topic, variant, choice = state['contract']
    if (type(original) is not tuple or not 3 <= len(original) <= 5
            or len(set(original)) != len(original) or not set(original) <= known
            or state['type'] != topic or state['variant'] != variant
            or state['policy'] != policy(choice, state['id'], resolved=True)):
        raise ValueError('invalid Festival contract')
    if variant not in ('standard', 'super') or (variant == 'super' and topic is not None) or (variant == 'standard' and topic not in host.r.mech('contest/type-match')['ring']):
        raise ValueError('invalid Festival child variant')
    if set(state['initial_pools']) != set(original) or set(state['initial_style']) != set(original):
        raise ValueError('Festival initial resources lost their original owners')
    for pool in state['initial_pools'].values():
        if type(pool) is not dict or set(pool) - set(host.r.mech('contest/type-match')['ring']) or any(type(n) is not int or n < 0 for n in pool.values()):
            raise ValueError('invalid Festival initial resource pool')
    survivors = original
    eliminated = ()
    if type(state['history']) is not list:
        raise ValueError('invalid Festival history')
    for index, row in enumerate(state['history']):
        final = len(survivors) == 3
        kind = 'winner' if final else 'eliminate'
        if (row['participants'] != survivors or set(row['scores']) != set(survivors)
                or any(type(n) is not int for n in row['scores'].values())
                or row['child_id'] != state['id'] + ':subcontest:' + str(index + 1)):
            raise ValueError('Festival history changed participants or child identity')
        extreme = (max if final else min)(row['scores'].values())
        candidates = tuple(c for c in survivors if row['scores'][c] == extreme)
        checkpoint = dict(state, survivors=survivors, history=state['history'][:index])
        decisions = {str(index + 1) + ':' + kind: row['decision']} if row['decision'] is not None else {}
        selected, _ = _decision(checkpoint, kind, candidates, row['scores'], decisions)
        if row[kind] is not selected or (final and index != len(state['history']) - 1):
            raise ValueError('Festival result is not the observed extreme score')
        if not final:
            eliminated += (selected,)
            survivors = tuple(c for c in survivors if c is not selected)
    if state['survivors'] != survivors or state['eliminated'] != eliminated:
        raise ValueError('Festival survivors disagree with elimination history')
    child = host._standard_run
    if child is not None:
        offset = len(state['history']) if state['phase'] in ('next', 'complete') else len(state['history']) + 1
        expected_actors = state['history'][-1]['participants'] if state['phase'] == 'next' else survivors
        if (child['contract'] != (expected_actors, topic, variant)
                or child['id'] != state['id'] + ':subcontest:' + str(offset)):
            raise ValueError('Festival progress does not match its actual child contest')
    if state['phase'] in ('adjudication', 'next', 'complete') and (child is None or child['phase'] != 'complete'):
        raise ValueError('Festival boundary requires the completed actual child')
    if state['phase'] in ('next', 'complete'):
        row = state['history'][-1]
        if any(row['scores'][c] != c.appeal - c.fumble for c in row['participants']):
            raise ValueError('Festival boundary scores disagree with actual contestants')
    if state['phase'] == 'complete':
        if (not state['history'] or 'winner' not in state['history'][-1]
                or state['winner'] is not state['history'][-1]['winner']
                or len(survivors) != 3 or type(state.get('result')) is not tuple
                or len(state['result']) != 3 or set(state['result']) != set(survivors)
                or state['result'][0] is not state['winner']):
            raise ValueError('invalid Festival final three result')
    elif state['history'] and 'winner' in state['history'][-1]:
        raise ValueError('Festival final receipt cannot be unfinished')
