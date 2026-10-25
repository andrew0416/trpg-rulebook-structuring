"""Ranked Type Expertise choices; acquisition, stat ownership and damage stay native."""
from copy import deepcopy
from pathlib import Path
import json

import common_checks as C
import move_state as MOVES
import state_grants as GRANTS
import type_state as TYPES

FEATURE = 'feat/타입-전문지식'
BOOK = 'C03-142'
CSV = 'C2CSV/input/db/feats.csv:R42:main'
BOOK_FILE = 'input/ch03-skills-edges-feats.md'
BOOK_SHA256 = 'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'
STATS = ('hp', 'atk', 'def', 'spa', 'spd', 'spe')
DEFINITION = {'clause_id': BOOK, 'span': [863, 867], 'catalog_span': [863, 867],
              'ranked': True, 'max_rank': 2, 'stat_tags': ['any'],
              'selection': {'type': 'known_move_type', 'stat': list(STATS),
                            'local_translation_moves': 3}}


def contract(rules):
    path = Path(rules.root) / 'data/type-expertise-source-contract.json'
    return json.loads(path.read_text(encoding='utf-8'))


def source(rules, edition):
    from source_context import verified_source
    if edition not in ('core', 'local_translation', 'local_csv'):
        raise ValueError('reviewed Type Expertise source edition required')
    if rules._selected_rule(FEATURE) != FEATURE:
        raise ValueError('selected Type Expertise source requires its own adapter')
    if FEATURE in rules.ruleset.unit_versions or BOOK in rules.ruleset.unit_versions or CSV in rules.ruleset.unit_versions:
        raise ValueError('Type Expertise source version requires its own adapter')
    data = contract(rules)
    for file, digest in data['source_files'].items():
        verified_source(rules, {'file': file, 'sha256': digest}, label='Type Expertise')
    result = {'edition': edition, 'clause_id': CSV if edition == 'local_csv' else BOOK,
              'file': 'input/db/feats.csv' if edition == 'local_csv' else BOOK_FILE}
    result['sha256'] = data['source_files'][result['file']]
    if edition == 'local_csv':
        result['record'] = 42
        rules.ruleset.require({'id': CSV, 'source': {'file': 'db/feats.csv', 'record_span': [42, 42]}})
    else:
        result['span'] = [863, 867]
    if edition == 'core':
        original = data['core']
        verified_source(rules, original, label='original Core Type Expertise', source_root='source-audit')
        result['interpretation'] = deepcopy(original)
    return result


def _selection(rules, selection):
    if type(selection) is not dict:
        raise ValueError('Type Expertise requires an explicit Type and stat selection')
    edition = selection.get('edition', 'core')
    fields = {'type', 'stat'} | ({'edition'} if 'edition' in selection else set())
    if edition == 'local_translation':
        fields.add('moves')
    if set(selection) != fields or selection['stat'] not in STATS:
        raise ValueError('Type Expertise requires its exact source-specific Type, moves and stat choice')
    TYPES.validate_types(rules, [selection['type']], label='Type Expertise selected Type')
    moves = None
    if edition == 'local_translation':
        raw = selection['moves']
        if type(raw) is not list or len(raw) != 3:
            raise ValueError('translated Type Expertise selects exactly three known Moves')
        moves = MOVES.known(rules, {'moves': raw})
        if len(moves) != 3:
            raise ValueError('translated Type Expertise selects three distinct known Moves')
    return edition, moves


def acquisition_snapshot(engine, actor, rank, selection):
    edition, selected = _selection(engine.r, selection)
    # The source says Move List, unlike Signature Move's explicit permanent-only rule.
    # Display overlays and permission-only actions are not learned Move ownership.
    known = MOVES.known(engine.r, {'moves': MOVES.owned_list(actor.spec, 'moves')})
    types = {mid: engine.r.move(mid)['type'] for mid in known}
    if selected is not None and (not set(selected) <= set(known) or
            any(types[mid] != selection['type'] for mid in selected)):
        raise ValueError('translated Type Expertise selects three known Moves of the chosen Type')
    return {'level': actor.spec.get('level'), 'rank_number': rank,
            'selection': deepcopy(selection), 'source': source(engine.r, edition),
            'known_moves': known, 'move_types': types}


def qualification(actor, snapshot, prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot) != {
            'level', 'rank_number', 'selection', 'source', 'known_moves', 'move_types'}:
        raise ValueError('exact Type Expertise acquisition observations required')
    C.integer(snapshot['level'], 'Type Expertise observed trainer level', 1, 50)
    C.integer(snapshot['rank_number'], 'Type Expertise rank', 1, 2)
    selection = snapshot['selection']
    edition, selected = _selection(actor.r, selection)
    if snapshot['source'] != source(actor.r, edition):
        raise ValueError('immutable actual Type Expertise source required')
    known, types = snapshot['known_moves'], snapshot['move_types']
    if (type(known) is not list or MOVES.known(actor.r, {'moves': known}) != known or
            type(types) is not dict or set(types) != set(known) or
            types != {mid: actor.r.move(mid)['type'] for mid in known}):
        raise ValueError('Type Expertise historical Move List or Types changed')
    enough = sum(value == selection['type'] for value in types.values()) >= 3
    if selected is not None:
        enough = enough and set(selected) <= set(known) and all(types[mid] == selection['type'] for mid in selected)
    return Q.require(FEATURE, 'native', 'acquire', [
        Q.check('trainer', 'prerequisite', actor.kind == 'trainer', 'actual Trainer required'),
        Q.check('level', 'prerequisite', snapshot['level'] >= 9, 'Type Expertise requires Level 9'),
        Q.check('same_type_moves', 'prerequisite', enough,
                'Type Expertise requires three known Moves of the chosen Type')])


def records(actor, *, active=True):
    import trainer_feature_acquisition as T
    return T.static_acquisitions(actor, FEATURE, active=active)


def after_acquire(engine, actor, source_id):
    row = actor.spec[GRANTS.KEY]['sources'][source_id]['static_acquisition']
    GRANTS.stat(actor, row['snapshot']['selection']['stat'], 1, source_id,
                operation_id='acquisition_stat_tag')
    import acquisition_withdrawal as WITHDRAWAL
    lower = [sid for sid, other in records(actor)
             if other['snapshot']['rank_number'] < row['snapshot']['rank_number']]
    WITHDRAWAL.dependencies(engine, actor, source_id, lower)


def source_for_rank(actor, rank=None):
    rows = records(actor)
    if not rows:
        raise ValueError('actual acquired Type Expertise rank required')
    rank = max(row['snapshot']['rank_number'] for _, row in rows) if rank is None else rank
    matches = [sid for sid, row in rows if row['snapshot']['rank_number'] == rank]
    if len(matches) != 1:
        raise ValueError('one actual acquired Type Expertise rank required')
    return matches[0]


def retraining_rank(actor, rule_id, rank):
    if rule_id != FEATURE:
        if rank is not None:
            raise ValueError('explicit per-rank retraining requires its reviewed Feature adapter')
        return None
    current = max(row['snapshot']['rank_number'] for _, row in records(actor))
    if rank is None and current == 1:
        rank = 1
    C.integer(rank, 'explicit Type Expertise retraining rank', 1, 2)
    if rank != current:
        raise ValueError('a retained higher rank requires the lower Type Expertise rank')
    return rank


def validate_actor(actor):
    import trainer_feature_acquisition as T
    rows = records(actor)
    aliases = {FEATURE, '타입 전문지식', 'Type Expertise'}
    owned = aliases.intersection(actor.spec.get('feats', []))
    if bool(owned) != bool(rows) or (owned and owned != {FEATURE}):
        raise ValueError('Type Expertise needs its actual ranked acquisition receipts')
    for sid, record in rows:
        payload = {key: value for key, value in record.items() if key != 'integrity'}
        if record['integrity'] != T._digest('trainer-feature/static-acquisition/v1', payload):
            raise ValueError('Type Expertise acquisition integrity changed')
        stat = record['snapshot']['selection']['stat']
        operation = actor.spec[GRANTS.KEY].get('stat_sources', {}).get(stat, {}).get('sources', {}).get(sid, {})
        if operation.get('acquisition_stat_tag') != {'delta': 1, 'minimum': None}:
            raise ValueError('actual source-owned Type Expertise stat tag required for each rank')
        lower = sorted(other_sid for other_sid, other in rows
                       if other['snapshot']['rank_number'] < record['snapshot']['rank_number'])
        if actor.spec[GRANTS.KEY]['sources'][sid].get('withdrawal_dependencies') != lower:
            raise ValueError('Type Expertise rank must retain its actual lower-rank dependencies')


def grants_stab(engine, actor, move):
    if actor is None:
        return False
    validate_actor(actor)
    # Engine owns one STAB application and the actual weapon/Struggle exclusions.
    return move.get('id') != 'struggle' and any(
        record['snapshot']['selection']['type'] == move.get('type')
        for _, record in records(actor))
