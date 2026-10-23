"""Exact CSV104 Mentor choice and learning proofs over existing native owners."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import csv
import json
import re

import trainer_feature_acquisition as A

SOURCE = 'C2CSV/input/db/feats.csv:R104:main'
FEATURE = 'class/멘토'
ADAPTER = 'trainer-feature/mentor-csv-skills/v1'
SKILLS = ('매력', '직감', '협박', '포켓몬학')
CSV_SHA = '4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
CELL_SHA = '3b423664059a5c2ad597d650b2d5ae3670708a7db3d6f9c9c42099d451e83cb4'
LEARNSET_SHA = '9b2be5bac7189567b97ad957379124f1a001bf016a0ce45ed03f63065a10ea6a'
EXTRACT_SHA = 'a359d6649cc5207eebd588ef9c4053bfc09f9c77f926a00c99e33bb586b20c44'


import resolution_transaction as _FINGERPRINTS

def source(rules, clause_id=SOURCE):
    if clause_id != SOURCE or rules._selected_rule(FEATURE) != FEATURE:
        raise ValueError('exact CSV Mentor source must be selected')
    if SOURCE in rules.ruleset.unit_versions or FEATURE in rules.ruleset.unit_versions:
        raise ValueError('changed Mentor version needs its own source adapter')
    path = Path(rules.root) / 'input/db/feats.csv'
    if sha256(path.read_bytes()).hexdigest() != CSV_SHA:
        raise ValueError('Mentor CSV source changed; review required')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        cells = list(csv.reader(stream))[103]
    if _FINGERPRINTS.json_fingerprint(cells, sort_keys=False, compact=True, allow_nan=True) != CELL_SHA:
        raise ValueError('Mentor exact CSV record changed')
    unit = rules.selection.units.get(FEATURE, {})
    if unit.get('title') != '멘토':
        raise ValueError('actual selected Mentor catalog identity changed')
    rules.ruleset.require({'id': SOURCE, 'source': {'file': 'db/feats.csv', 'record_span': [104, 104]}})
    return {'clause_id': SOURCE, 'file': 'input/db/feats.csv', 'sha256': CSV_SHA, 'version': 1}


def has_receipt(actor):
    return any(row.get('adapter_id') == ADAPTER for row in A._active_rows(actor))


def _qualification(actor, skills, ranks):
    return {'schema': 1, 'status': 'qualified', 'waivers': [], 'checks': [
        {'id': 'trainer', 'kind': 'prerequisite', 'state': 'passed', 'observed': 'trainer',
         'reason': 'Mentor is an actual trainer Class'},
        {'id': 'two_novice', 'kind': 'prerequisite', 'state': 'passed',
         'observed': {'skills': list(skills), 'ranks': list(ranks)},
         'reason': 'Two distinct printed Mentor skills must be Novice at acquisition'}]}


def validate_receipt(actor, payload):
    src = source(actor.r)
    if (actor.kind != 'trainer' or payload['adapter_id'] != ADAPTER or payload['feature_id'] != FEATURE or
            payload['source'] != src or payload['provider'] != {'actor_id': actor.entity_id, 'mode': 'self_acquisition'}):
        raise ValueError('CSV Mentor actual acquisition source/provider mismatch')
    selection = payload['selection']; skills = selection['values']; snap = selection['acquisition_snapshot']
    if (selection['kind'] != 'mentor_skill' or selection['required_count'] != 2 or
            len(skills) != 2 or len(set(skills)) != 2 or any(v not in SKILLS for v in skills) or
            set(snap) != {'skills', 'ranks'} or snap['skills'] != skills or
            type(snap['ranks']) is not list or len(snap['ranks']) != 2 or
            any(type(v) is not int or not 3 <= v <= 6 for v in snap['ranks'])):
        raise ValueError('CSV Mentor immutable acquisition skill evidence mismatch')
    if (selection['proofs'] != [{'value': skill, 'rank_at_acquisition': rank} for skill, rank in zip(skills, snap['ranks'])] or
            payload['qualification'] != _qualification(actor, skills, snap['ranks']) or
            actor.spec.get('mentor_skills') != skills or
            actor.spec.get('mentor_skill_selection') != {'source': SOURCE, 'request_id': payload['acquisition_request_id']}):
        raise ValueError('CSV Mentor acquisition choice/projection/qualification changed')
    return src


def receipt(actor):
    rows = [row for row in A.receipts(actor) if row['adapter_id'] == ADAPTER and row.get('state') != 'withdrawn']
    if len(rows) != 1:
        raise ValueError('actual committed CSV Mentor acquisition required')
    return rows[0]


def acquire(engine, actor, *, acquisition_request_id, skills, source_clause_id=SOURCE,
            feature_instance_id=FEATURE + ':csv104', provider=None, waivers=(), lifecycle_policy=None):
    import world_entities as W
    import state_grants as G
    import skill_modifiers as S
    provider = actor if provider is None else provider
    W.require_actors(engine, actor, provider)
    src = source(engine.r, source_clause_id)
    lifecycle = A._lifecycle(lifecycle_policy)
    A._text(acquisition_request_id, 'acquisition request identity'); A._text(feature_instance_id, 'feature instance')
    if actor.kind != 'trainer' or provider is not actor or waivers not in ((), []):
        raise ValueError('CSV Mentor requires actual self-acquiring trainer without waiver')
    if (not isinstance(skills, (list, tuple)) or len(skills) != 2 or len(set(skills)) != 2 or
            any(v not in SKILLS for v in skills)):
        raise ValueError('select two distinct printed Mentor skills')
    skills = list(skills)
    intent = A._intent(actor_id=actor.entity_id, feature_id=FEATURE, feature_instance_id=feature_instance_id,
        source=src, request_id=acquisition_request_id, provider_id=actor.entity_id, adapter_id=ADAPTER,
        selection_kind='mentor_skill', selected_values=skills, required_count=2, lifecycle_policy=lifecycle)
    signature = A._digest('trainer-feature/acquisition-request/v1', intent)
    A.validate_actor(actor)
    ledger = actor.spec.get(A.LEDGER_KEY, {})
    if acquisition_request_id in ledger:
        row = ledger[acquisition_request_id]
        if row['request_integrity'] != signature:
            raise ValueError('CSV Mentor replay cannot change acquisition choices')
        return deepcopy(row)
    import pokemon_teaching as T
    if T._acquired_feature(actor, FEATURE) or 'mentor_skills' in actor.spec:
        raise ValueError('CSV Mentor cannot replace an existing Class/skill acquisition')
    ranks = [S.rank(engine.r, actor, skill)[2] for skill in skills]
    if any(rank < 3 for rank in ranks):
        raise ValueError('both selected Mentor skills must be Novice at acquisition')
    row = A._seal({'schema': 1, 'basis': 'trainer_feature_selection',
        'receipt_id': 'trainer-feature-selection/' + acquisition_request_id, 'actor_id': actor.entity_id,
        'feature_id': FEATURE, 'feature_instance_id': feature_instance_id, 'source': src,
        'acquisition_request_id': acquisition_request_id,
        'provider': {'actor_id': actor.entity_id, 'mode': 'self_acquisition'}, 'adapter_id': ADAPTER,
        'qualification': _qualification(actor, skills, ranks),
        'selection': {'kind': 'mentor_skill', 'required_count': 2, 'values': skills,
            'proofs': [{'value': skill, 'rank_at_acquisition': rank} for skill, rank in zip(skills, ranks)],
            'acquisition_snapshot': {'skills': skills, 'ranks': ranks}},
        'lifecycle_policy': lifecycle, 'request_integrity': signature, 'committed': True})
    def apply(e, c):
        c.spec.setdefault('classes', []).append(FEATURE)
        c.spec['mentor_skills'] = list(skills)
        c.spec['mentor_skill_selection'] = {'source': SOURCE, 'request_id': acquisition_request_id}
        c.spec.setdefault(A.LEDGER_KEY, {})[acquisition_request_id] = deepcopy(row)
        c.spec[A.PROJECTION_KEY] = A._projection_from_rows(A._active_rows(c))
        import acquired_features as ACQUIRED
        ACQUIRED.validate_class_slots(c)
        return deepcopy(row)
    return G.transition(engine, actor, apply)


def _catalog(rules):
    root = Path(rules.root)
    if sha256((root / 'input/db/learnsets.csv').read_bytes()).hexdigest() != LEARNSET_SHA:
        raise ValueError('Mentor learnset original source changed; review required')
    path = root / 'output/entities/learnsets.json'
    if sha256(path.read_bytes()).hexdigest() != EXTRACT_SHA:
        raise ValueError('Mentor selected learnset extraction changed; review required')
    records = json.loads(path.read_text(encoding='utf-8'))
    with (root / 'input/db/learnsets.csv').open(encoding='utf-8-sig', newline='') as stream:
        raw = list(csv.reader(stream))
    return {row['species']: row for row in records}, raw


def _learnset(rules, name, catalog):
    rows, raw = catalog
    row = rows.get(name)
    if row is None or rules.learnsets.get(name) != row:
        raise ValueError('actual selected species learnset/source required')
    if row['id'] in rules.selection.units and rules._selected_rule(row['id']) != row['id']:
        raise ValueError('actual selected species learnset/source required')
    if row['id'] in rules.ruleset.unit_versions:
        raise ValueError('changed learnset source version needs review')
    src = row['_source']; span = src.get('record_span')
    if src.get('file') != 'db/learnsets.csv' or type(span) is not list or len(span) != 2 or span[0] != span[1]:
        raise ValueError('actual source learnset record required')
    cells = raw[span[0] - 1]
    if cells[0] != name:
        raise ValueError('learnset species source identity differs')
    rules.ruleset.require({'id': row['id'], 'source': {'file': 'db/learnsets.csv', 'record_span': span}})
    proof = {'species': name, 'record': span[0], 'file_sha256': LEARNSET_SHA,
             'row_sha256': _FINGERPRINTS.json_fingerprint(cells, sort_keys=False, compact=True, allow_nan=True),
             'extract_sha256': EXTRACT_SHA}
    return row, proof


def _memberships(rules, row, mid):
    found = []
    for value in row.get('level_up', []):
        if rules.move_id(value['move']) == mid:
            found.append({'kind': 'level_up', 'required_level': value['level'], 'raw': deepcopy(value)})
    for kind in ('tm', 'egg', 'tutor'):
        for raw in row.get(kind, []):
            name = re.sub(r'^\s*[A-Za-z]?\d+\s+', '', raw) if kind == 'tm' else raw
            name = re.sub(r'\s*\(N\)', '', name, flags=re.I).strip()
            if rules.move_id(name) == mid:
                found.append({'kind': 'n_tutor' if kind == 'tutor' and re.search(r'\(N\)', raw, re.I) else kind,
                              'required_level': None, 'raw': raw})
    return found


def _ancestors(rules, target_row, catalog):
    from builder import evolution_stages
    chain = evolution_stages(target_row)
    positions = [i for i, row in enumerate(chain) if row[1] == target_row['species']]
    if len(positions) != 1:
        raise ValueError('unresolved exact target-specific evolution lineage')
    prefix = chain[:positions[0] + 1]
    if [v[0] for v in prefix] != list(range(1, prefix[-1][0] + 1)) or len({v[1] for v in prefix}) != len(prefix):
        raise ValueError('unresolved branched target-specific lineage; no family-stage inference')
    result = []
    for i, (_, name, _) in enumerate(prefix[:-1]):
        row, proof = _learnset(rules, name, catalog)
        corroboration = [(v[0], v[1]) for v in evolution_stages(row)]
        pair = [(prefix[i][0], name), (prefix[i + 1][0], prefix[i + 1][1])]
        if not any(corroboration[j:j + 2] == pair for j in range(len(corroboration) - 1)):
            raise ValueError('unresolved target/predecessor source chain conflict')
        result.append((row, proof))
    return prefix, result


def candidate(rules, spec, mid, ranks, *, ancestor=None, type_sync_id='current', rank_record=None):
    """Produce deterministic historical eligibility, never a caller hit/permission flag."""
    source(rules)
    from builder import species_lookup
    import type_sync as SYNC
    name = species_lookup(rules, spec['species'])['name']; level = spec['level']
    if type(level) is not int or not 1 <= level <= 100 or len(ranks) != 2 or any(type(v) is not int or v not in (3, 4, 5, 6, 8) for v in ranks):
        raise ValueError('actual Mentor pupil level and selected skill ranks required')
    if any(v > 6 for v in ranks):
        import pokemon_teaching as T
        if rank_record is None or T.validate_mentor_ranks(rules, rank_record) != list(ranks):
            raise ValueError('actual historical Mentor rank-effect evidence required')
    catalog = _catalog(rules); current, current_source = _learnset(rules, name, catalog)
    own = _memberships(rules, current, mid)
    if type_sync_id == 'current':
        active = SYNC.active(rules, spec)
        type_sync_id = active['id'] if active else None
    if type_sync_id:
        own = [v for v in own if v['kind'] != 'level_up']
        sync = SYNC.historical_evidence(rules, spec, type_sync_id, mid, 100)
        own += [{'kind': 'level_up', 'required_level': v['required_level'], 'raw': v} for v in sync if v['kind'] == 'level_up']
    options = [v for v in own if v['kind'] == 'n_tutor' or (v['kind'] == 'level_up' and v['required_level'] <= min(100, level + sum(ranks)))]
    proof = {'target_species': current['species'], 'target_source': current_source,
             'move_id': mid, 'level': level, 'ranks': list(ranks), 'type_sync_id': type_sync_id}
    if options and ancestor is None:
        chosen = sorted(options, key=lambda v: (v['required_level'] is None, v['required_level'] or 0))[0]
        return {**proof, 'route': 'current', 'membership': chosen, 'ancestor': None,
                'point_cost': 0 if chosen['required_level'] is not None and chosen['required_level'] <= level else 1}
    if own:
        raise ValueError('Mentor Move exceeds current allowance; currently available Move is not a lost pre-evolution exception')
    chain, earlier = _ancestors(rules, current, catalog)
    requested = species_lookup(rules, ancestor)['name'] if ancestor is not None else None
    matches = []
    for row, earlier_source in reversed(earlier):
        if requested is not None and row['species'] != requested:
            continue
        for membership in _memberships(rules, row, mid):
            matches.append((row, earlier_source, membership))
    if not matches:
        raise ValueError('Move has no actual available current or true pre-evolution Mentor source')
    row, earlier_source, chosen = min(matches, key=lambda v: (v[2]['required_level'] is None or v[2]['required_level'] > level))
    return {**proof, 'route': 'pre_evolution_n', 'membership': chosen, 'ancestor': row['species'],
            'ancestor_source': earlier_source, 'lineage': [list(v) for v in chain],
            'corroborating_sources': [p for _, p in earlier], 'unavailable_current': [],
            'point_cost': 0 if chosen['required_level'] is not None and chosen['required_level'] <= level else 1}


def prepare(engine, teacher, target, mid, *, ancestor=None):
    import pokemon_teaching as T
    row = receipt(teacher)
    skills = row['selection']['values']; ranks, witness = T.mentor_effect_ranks(engine.r, teacher, skills)
    details = {'mentor_skills': list(skills), 'mentor_skill_ranks': ranks}
    if witness is not None:
        details['mentor_rank_evidence'] = witness
    proof = candidate(engine.r, target.spec, mid, ranks, ancestor=ancestor,
                      rank_record=dict(details, teacher_id=teacher.entity_id))
    return dict(details, mentor_csv_proof=proof, mentor_acquisition_receipt=deepcopy(row))


def validate_learning(rules, spec, mid, record):
    source(rules)
    if (record.get('source') != FEATURE or record.get('mentor_source_clause') != SOURCE or
            record.get('method') != 'mentor_csv'):
        raise ValueError('exact CSV Mentor learning source required')
    proof = record.get('mentor_csv_proof')
    if type(proof) is not dict or proof.get('move_id') != mid or proof.get('level') != record.get('learned_at_level'):
        raise ValueError('CSV Mentor historical Move/level proof changed')
    from builder import species_lookup
    if species_lookup(rules, record.get('species_id'))['name'] != proof['target_species']:
        raise ValueError('CSV Mentor historical species identity changed')
    ranks = record.get('mentor_skill_ranks'); skills = record.get('mentor_skills')
    acquisition = record.get('mentor_acquisition_receipt')
    if type(acquisition) is not dict:
        raise ValueError('CSV Mentor original acquisition receipt required')
    payload = A._receipt_payload(acquisition)
    # Historical teacher evidence uses the original sealed acquisition, not its
    # current ownership/skill ranks; teacher may since have left the encounter.
    from types import SimpleNamespace
    historical = SimpleNamespace(r=rules, kind='trainer', entity_id=record.get('teacher_id'),
        spec={'mentor_skills': skills, 'mentor_skill_selection': {'source': SOURCE,
              'request_id': payload['acquisition_request_id']}})
    A._validate_receipt(historical, payload['acquisition_request_id'], acquisition)
    if payload['selection']['values'] != skills:
        raise ValueError('CSV Mentor original selected skills changed')
    import pokemon_teaching as T
    T.validate_mentor_ranks(rules, record)
    historical_spec = dict(spec, species=record['species_id'], level=record['learned_at_level'])
    expected = candidate(rules, historical_spec, mid, ranks, ancestor=proof.get('ancestor'), type_sync_id=proof.get('type_sync_id'), rank_record=record)
    if proof != expected or record.get('paid_tp') != expected['point_cost']:
        raise ValueError('CSV Mentor historical source/eligibility/payment proof changed')
    return True


def teach(engine, teacher, *, target, move_id, seconds, reason, replace=None, ancestor=None):
    import pokemon_teaching as T
    return T.teach_feature(engine, teacher, target=target, move_id=move_id, feature=SOURCE,
                          seconds=seconds, reason=reason, replace=replace, mentor_ancestor=ancestor)

