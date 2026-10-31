"""Exact book/CSV teaching over immutable selection and learning owners."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import common_checks as C
import trainer_feature_acquisition as A


SOURCE = 'C03-127'
CSV_SOURCE = 'C2CSV/input/db/feats.csv:R8:main'
FEATURE = A.PERSONAL_TUTOR
LEGALITY = 'definition/전문가-가르침'
LEGALITY_FILE = 'input/ch11-running-the-game.md'
LEGALITY_SHA = '5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad'
MARKER = 'personal_tutor_source_clause'
CSV_COST_SOURCE = {'file': 'output/source-audit/2026-10-10/ptu-core-1.05.pdf',
    'sha256': 'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907',
    'pages': [59, 59], 'point_cost': 2}


def _source(rules, source_clause_id=SOURCE):
    A._source(rules, source_clause_id)
    import pokemon_teaching as T
    T.source(rules, T.MOVES, T.POINTS)
    if source_clause_id == CSV_SOURCE:
        if FEATURE in rules.ruleset.unit_versions:
            raise ValueError('changed Personal Tutor version needs its own source adapter')
        if sha256((Path(rules.root) / CSV_COST_SOURCE['file']).read_bytes()).hexdigest() != CSV_COST_SOURCE['sha256']:
            raise ValueError('Personal Tutor English cost supplement changed; review required')
        return
    if FEATURE in rules.ruleset.unit_versions or LEGALITY in rules.ruleset.unit_versions:
        raise ValueError('changed Personal Tutor version needs its own source adapter')
    if LEGALITY in rules.selection.units and rules._selected_rule(LEGALITY) != LEGALITY:
        raise ValueError('selected Personal Tutor legality requires its reviewed source')
    if sha256((Path(rules.root) / LEGALITY_FILE).read_bytes()).hexdigest() != LEGALITY_SHA:
        raise ValueError('Personal Tutor legality source changed; review required')
    rules.ruleset.require({'id': LEGALITY,
        'source': {'file': LEGALITY_FILE.removeprefix('input/'), 'lines': [1406, 1406]}})


def _receipt(actor, feature_instance_id, source_clause_id=SOURCE):
    rows = [row for row in A.receipts(actor)
            if row['feature_id'] == FEATURE and row['feature_instance_id'] == feature_instance_id
            and row.get('state') != 'withdrawn']
    if len(rows) != 1 or rows[0]['source']['clause_id'] != source_clause_id:
        raise ValueError('actual acquired source-matching Personal Tutor selection required')
    A.selected_values(actor, FEATURE, feature_instance_id)
    return rows[0]


def _candidate(rules, spec, mid, *, type_sync_id='current', catalog=None):
    """Ch11:1406 names these four real species lists, including future levels."""
    from builder import species_lookup
    import mentor_csv as LISTS
    import type_sync as SYNC
    if catalog is None:
        catalog = LISTS._catalog(rules)
    species = species_lookup(rules, spec['species'])
    row, provenance = LISTS._learnset(rules, species['name'], catalog)
    options = LISTS._memberships(rules, row, mid)
    view = deepcopy(spec)
    if type_sync_id == 'current':
        current = SYNC.active(rules, view)
        type_sync_id = current['id'] if current else None
    if type_sync_id is None:
        view.pop(SYNC.KEY, None)
    else:
        SYNC.validate_spec(rules, view, consistent=False)
        history = view.get(SYNC.KEY, {}).get('history', [])
        matches = [i for i, value in enumerate(history) if value['id'] == type_sync_id]
        if len(matches) != 1:
            raise ValueError('Personal Tutor historical Type Sync source required')
        view[SYNC.KEY]['history'] = history[:matches[0] + 1]
        view['types'] = list(history[matches[0]]['after']['types'])
        options = [value for value in options if value['kind'] != 'level_up']
        options += [{'kind': 'level_up', 'required_level': value['required_level'], 'raw': value}
                    for value in SYNC.historical_evidence(rules, view, type_sync_id, mid, 100)]
        for method, kinds in (('tm', ('tm',)), ('tutor', ('tutor', 'n_tutor'))):
            permission = SYNC.learning_permission(rules, view, mid, method)
            if permission is False:
                options = [value for value in options if value['kind'] not in kinds]
            elif permission is True and not any(value['kind'] in kinds for value in options):
                # TM permission still needs an actual machine-table Move; the
                # existing Tutor permission already checks the global Tutor list.
                codes = []
                if method == 'tm':
                    import pokemon_teaching as T
                    codes = sorted(code for code, machine in T.catalog(rules)['machines'].items()
                                   if rules.move_id(machine['move_name']) == mid)
                if method == 'tutor' or codes:
                    options.append({'kind': method, 'required_level': None,
                        'raw': {'source': SYNC.SOURCE, 'type_sync_id': type_sync_id, 'machines': codes}})
    if not options:
        raise ValueError('Personal Tutor Move is not legal for the actual species learning lists')
    return {'source': LEGALITY, 'source_sha256': LEGALITY_SHA,
            'species_id': species['id'], 'learnset': provenance, 'move_id': mid,
            'type_sync_id': type_sync_id, 'memberships': options}


def _validate_learning(rules, spec, mid, record, catalog):
    import pokemon_teaching as T
    source_clause_id = record.get(MARKER)
    if (record.get('source') != FEATURE or source_clause_id not in (SOURCE, CSV_SOURCE) or
            record.get('method') != 'feature' or type(record.get('paid_tp')) is not int or
            record['paid_tp'] != 2 or record.get('lifetime') != 'permanent' or
            type(record.get('learning_contract')) is not int or record['learning_contract'] != 1):
        raise ValueError('exact Personal Tutor learning source and 2 TP required')
    C.integer(record.get('seconds'), 'Personal Tutor completed Extended duration', 1)
    teacher = record.get('teacher_id')
    if (type(teacher) is not str or not teacher or record.get('personal_tutor_owner_id') != teacher or
            record.get('personal_tutor_recipient_id') != spec.get('id')):
        raise ValueError('Personal Tutor actual teacher and original owned recipient required')
    acquisition = record.get('personal_tutor_acquisition_receipt')
    if type(acquisition) is not dict:
        raise ValueError('Personal Tutor original acquisition receipt required')
    # The actual teacher may since have left. Revalidate the sealed historical
    # acquisition through its owner; do not require current ownership or moves.
    historical = SimpleNamespace(r=rules, kind='trainer', entity_id=teacher, spec={})
    A._validate_receipt(historical, acquisition.get('acquisition_request_id'), acquisition)
    if (acquisition['feature_id'] != FEATURE or acquisition['source']['clause_id'] != source_clause_id or
            mid not in acquisition['selection']['values']):
        raise ValueError('Personal Tutor Move must be one of the original source-matching selections')
    if record.get('tutoring_admission') != T.tutor_admission(rules, mid, record.get('learned_at_level')):
        raise ValueError('Personal Tutor historical tutoring admission changed')
    if source_clause_id == CSV_SOURCE:
        cost_source = record.get('personal_tutor_cost_source')
        if (type(cost_source) is not dict or cost_source != CSV_COST_SOURCE or type(cost_source.get('point_cost')) is not int or
                any(type(page) is not int for page in cost_source.get('pages', [])) or
                type(record.get('personal_tutor_application_id')) is not str or
                not record['personal_tutor_application_id'] or 'personal_tutor_legality' in record or
                'personal_tutor_type_sync_id' not in record):
            raise ValueError('exact CSV Personal Tutor cost source and completed application required')
        _csv_permission(rules, spec, mid, type_sync_id=record['personal_tutor_type_sync_id'])
        return
    proof = record.get('personal_tutor_legality')
    if type(proof) is not dict:
        raise ValueError('Personal Tutor actual species legality proof required')
    previous = dict(spec, species=record.get('species_id'), level=record.get('learned_at_level'))
    expected = _candidate(rules, previous, mid, type_sync_id=proof.get('type_sync_id'), catalog=catalog)
    if proof != expected:
        raise ValueError('Personal Tutor historical species legality proof changed')


def _csv_permission(rules, spec, mid, *, type_sync_id='current'):
    """Compatibility waiver does not waive an independent GM learning exception."""
    import type_sync as SYNC
    if type_sync_id == 'current':
        active = SYNC.active(rules, spec)
        type_sync_id = active['id'] if active else None
    if type_sync_id is None:
        return None
    view = deepcopy(spec)
    SYNC.validate_spec(rules, view, consistent=False)
    history = view.get(SYNC.KEY, {}).get('history', [])
    matches = [i for i, row in enumerate(history) if row['id'] == type_sync_id]
    if len(matches) != 1:
        raise ValueError('CSV Personal Tutor historical Type Sync source required')
    view[SYNC.KEY]['history'] = history[:matches[0] + 1]
    view['types'] = list(history[matches[0]]['after']['types'])
    if SYNC.learning_permission(rules, view, mid, 'tutor') is False:
        raise ValueError('actual Type Sync learning exception forbids this teaching')
    return type_sync_id


def validate_spec(rules, spec):
    """Validate current and forgotten teaching through the existing learning log."""
    pairs = list(spec.get('move_learning', {}).items())
    pairs += [(row.get('move_id'), row) for row in spec.get('move_learning_log', [])
              if isinstance(row, dict)]
    records = [(mid, row) for mid, row in pairs if isinstance(row, dict) and
               (row.get('source') == FEATURE or MARKER in row or 'personal_tutor_legality' in row)]
    if records:
        import mentor_csv as LISTS
        catalog = LISTS._catalog(rules) if any(row.get(MARKER) == SOURCE for _, row in records) else None
        sources = []
        for _, row in records:
            source_clause_id = row.get(MARKER)
            if source_clause_id not in sources:
                _source(rules, source_clause_id)
                sources.append(source_clause_id)
        for mid, row in records:
            _validate_learning(rules, spec, mid, row, catalog)
    return True


def current_moves(rules, spec):
    """A CSV-taught Move reserves slots only while actually permanently owned."""
    import move_state as M
    owned = list(dict.fromkeys(list(spec.get('moves', [])) +
        list(spec.get('state_grants', {}).get('legacy', {}).get('moves', []))))
    result = []
    for mid in M.known(rules, {'moves': owned}):
        row = spec.get('move_learning', {}).get(mid)
        if not isinstance(row, dict) or row.get(MARKER) != CSV_SOURCE:
            continue
        _source(rules, CSV_SOURCE)
        _validate_learning(rules, spec, mid, row, None)
        result.append(mid)
    if len(result) > 1:
        raise ValueError('a Pokemon may have only one current Personal Tutor Move')
    return result


def teach(engine, actor, *, target, move_id, seconds, reason, replace=None,
          feature_instance_id='feat/개인-지도:1', source_clause_id=SOURCE):
    import state_grants as G
    C.integer(seconds, 'GM-established Extended activity duration seconds', 1)
    A._text(reason, 'teaching duration and application reason')
    return G.transition(engine, target,
        lambda e, pupil, teacher: _teach(e, teacher, target=pupil, move_id=move_id,
            seconds=seconds, reason=reason, replace=replace, feature_instance_id=feature_instance_id,
            source_clause_id=source_clause_id),
        participants=(actor,))


def _teach(engine, actor, *, target, move_id, seconds, reason, replace, feature_instance_id, source_clause_id):
    import activity_jobs as JOBS
    import learning_grant as LEARNING
    import move_state as M
    import pokemon_teaching as T
    import state_grants as G
    import trainer_retraining as RETRAINING
    import turn as TURN
    T._pokemon(engine, actor, target)
    _source(engine.r, source_clause_id)
    acquisition = _receipt(actor, feature_instance_id, source_clause_id)
    mid = engine.r.move_id(move_id)
    if mid is None or mid in engine.r.excluded_moves or mid not in acquisition['selection']['values']:
        raise ValueError('Personal Tutor requires an original selected available Move')
    if source_clause_id == CSV_SOURCE:
        proof = _csv_permission(engine.r, target.spec, mid)
    else:
        proof = _candidate(engine.r, target.spec, mid)
    admission = T.tutor_admission(engine.r, mid, target.level)
    if T._balance(target.spec) < 2:
        raise ValueError('insufficient actual Tutor Points')
    baseline = M.known(engine.r, target.spec)
    if mid in baseline:
        raise ValueError('Pokemon already learned that move')
    old = engine.r.move_id(replace) if replace is not None else None
    if replace is not None and old not in baseline:
        raise ValueError('explicit replacement must name an actually learned permanent move')
    candidate = __import__('world_entities').spec_copy(target)
    if old is not None:
        import move_type_sync as MOVE_SYNC
        MOVE_SYNC.forget_spec(engine.r, candidate, old, at=engine.elapsed_seconds, reason=reason)
        if source_clause_id == CSV_SOURCE:
            __import__('ace_trainer').forget_spec(engine.r, candidate, old, at=engine.elapsed_seconds, reason=reason)
    candidate['moves'] = [value for value in candidate.get('moves', []) if engine.r.move_id(value) != old]
    details = {MARKER: source_clause_id, 'seconds': seconds,
        'personal_tutor_acquisition_receipt': acquisition,
        'personal_tutor_recipient_id': target.entity_id, 'personal_tutor_owner_id': actor.entity_id,
        'tutoring_admission': admission}
    if source_clause_id == CSV_SOURCE:
        details.update(personal_tutor_cost_source=CSV_COST_SOURCE,
            personal_tutor_type_sync_id=proof,
            personal_tutor_application_id=':'.join((actor.entity_id, target.entity_id, mid,
                str(engine.elapsed_seconds + seconds), str(len(candidate.get('move_learning_log', [])) + 1))))
    else:
        details['personal_tutor_legality'] = proof
    LEARNING.learn_moves(engine.r, candidate, candidates=[mid], selected=[mid],
        method='feature', source=FEATURE, reason=reason, provider=actor.entity_id, paid_tp=2,
        replaced=old, details=details)
    if source_clause_id == CSV_SOURCE:
        import vitamin_capacity as CAPACITY
        if M.vitamin_state(engine.r, candidate)['occupied'] > CAPACITY.current(engine.r, candidate)['capacity']:
            raise ValueError('Personal Tutor requires an available current Vitamin slot')
        CAPACITY.record(engine.r, candidate, 'personal_tutor', details['personal_tutor_application_id'], move_id=mid)
    M.record_natural_opportunities(engine.r, candidate, reason=(
        'completed book Personal Tutor teaching' if source_clause_id == SOURCE
        else 'completed CSV Personal Tutor teaching'))
    M.validate_spec(engine.r, candidate, require_routes=True)
    if not TURN.spend(engine, actor, 'extended', FEATURE):
        raise ValueError('teaching requires the actual Extended action permission')
    JOBS.run_fixed(engine, actor, (target,), seconds=seconds, source=FEATURE,
                   context={'move_id': mid, 'source_clause_id': source_clause_id})
    fields = ('move_learning', 'move_learning_log', M.HISTORY, 'move_type_sync')
    if source_clause_id == CSV_SOURCE:
        fields += ('signature_techniques', 'vitamin_capacity_history')
    for field in fields:
        if field in candidate:
            target.spec[field] = candidate[field]
    if source_clause_id == CSV_SOURCE and 'signature_techniques' in candidate:
        target.spec['tutor_points'] = candidate['tutor_points']
    G.set_baseline(target, 'moves', candidate['moves'])
    T._debit_points(target.spec, 2)
    RETRAINING.irreversible(engine, actor, FEATURE,
        event_id='teaching:' + actor.entity_id + ':' + target.entity_id + ':' + source_clause_id + ':' + mid + ':' + str(engine.elapsed_seconds),
        reason='completed permanent Personal Tutor teaching to ' + target.entity_id + ': ' + mid)
    return {'activity': 'personal_tutoring', 'move': mid, 'replaced': old, 'point_cost': 2,
            'source': FEATURE, 'source_clause_id': source_clause_id, 'seconds': seconds,
            'classification': M.describe(engine.r, target.spec)['classifications'][mid]}
