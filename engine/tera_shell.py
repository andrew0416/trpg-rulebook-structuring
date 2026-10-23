"""R0670 Tera Shell: authenticated accuracy choice and encounter type grant."""
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path

import ability_transitions as ABILITIES
import combat_timing as TIME
import state_grants as GRANTS
import type_state as TYPES

SOURCE = 'ability/테라셸'
CLAUSE = 'C2CSV-ABILITY-R0670'
POLICY = 'data/tera-shell-policy.json'
KEY = 'tera_shell_receipts'
PLAN_FIELDS = {'source', 'clause_id', 'event_id', 'completion_id', 'owner_id',
               'attacker_id', 'move', 'chosen_type', 'original_stab_types', 'grant_key'}


import resolution_transaction as _FINGERPRINTS

def policy(rules):
    row = json.loads((Path(rules.root) / POLICY).read_text(encoding='utf-8'))
    raw = (Path(rules.root) / row['source_file']).read_bytes()
    if row['schema_version'] != 1 or row['source'] != SOURCE or row['clause_id'] != CLAUSE:
        raise ValueError('reviewed Tera Shell policy required')
    if hashlib.sha256(raw).hexdigest() != row['source_sha256']:
        raise ValueError('Tera Shell source changed')
    cells = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))[row['csv_record'] - 1]
    digest = _FINGERPRINTS.json_fingerprint(cells, sort_keys=False, compact=True, allow_nan=True)
    if digest != row['row_sha256'] or rules._selected_rule(SOURCE) != SOURCE:
        raise ValueError('selected exact Tera Shell source required')
    expected = {'action': 'free', 'interrupt': True, 'frequency': {'kind': 'scene', 'uses': 1},
                'lifetime': 'encounter_end', 'resistance_multiplier': .5,
                'new_only_damage_bonus': 10,
                'damage_phase': 'roll_modifier_before_defense_and_type_scaling'}
    if any(row.get(k) != v for k, v in expected.items()):
        raise ValueError('Tera Shell source semantics changed')
    return row


def definition(rules, source=SOURCE):
    return policy(rules) if source == SOURCE else None


def registration(rules, name):
    if name not in (SOURCE, '테라셸', 'Tera Shell'):
        return None
    policy(rules)
    return {'name': '테라셸', 'source_id': SOURCE, 'equivalent_source_ids': [SOURCE]}


def handled(rules, selected_id):
    return selected_id == SOURCE and definition(rules) is not None


def _live(owner):
    sources = owner.spec.get(GRANTS.KEY, {}).get('sources', {})
    rows = [p for key, p in owner.spec.get(KEY, {}).items() if key in sources]
    if len(rows) > 1:
        raise ValueError('only one live Tera Shell transformation allowed')
    return rows[0] if rows else None


def stab_types(owner, ordinary):
    row = _live(owner)
    return list(row['original_stab_types']) if row else list(ordinary)


def bonus_eligible(owner, move, *, other_stab=False):
    row = _live(owner)
    return bool(row and move.get('type') == row['chosen_type'] and
                move.get('type') in owner.types and
                move.get('type') not in row['original_stab_types'] and not other_stab and
                move.get('class') in ('물리', '특수') and move.get('id') != 'struggle')


def damage_bonus(owner, move, *, engine=None):
    if not bonus_eligible(owner, move):
        return 0
    if engine is None:
        raise ValueError('actual damage engine required to preserve other STAB grants')
    import effects_ext as EXT
    return 10 if not EXT.grants_stab(engine, owner, move) else 0


def _validate_plan(rules, plan):
    if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
        raise ValueError('exact Tera Shell activation plan required')
    if plan['source'] != SOURCE or plan['clause_id'] != CLAUSE:
        raise ValueError('Tera Shell plan source mismatch')
    for key in ('event_id', 'completion_id', 'owner_id', 'attacker_id', 'grant_key'):
        if not isinstance(plan[key], str) or not plan[key]:
            raise ValueError('Tera Shell plan identity required')
    if plan['grant_key'] != 'tera_shell:' + plan['event_id'] + ':' + plan['owner_id']:
        raise ValueError('Tera Shell grant identity mismatch')
    TYPES.validate_types(rules, [plan['chosen_type']], label='chosen resisting type')
    TYPES.validate_types(rules, plan['original_stab_types'], label='original Tera Shell STAB')
    move = plan['move']
    if not isinstance(move, dict) or not isinstance(move.get('id'), str):
        raise ValueError('actual native Tera Shell trigger Move required')
    if TYPES.matchup(rules, move.get('type'), plan['chosen_type']) != .5:
        raise ValueError('chosen type must resist the actual triggering Move type')
    json.dumps(plan, ensure_ascii=False, allow_nan=False)
    return plan


def prepare(engine, owner, event_id, chosen_type):
    import ability_interrupt_choices as CHOICES
    import homebrew_state as HOME
    import move_defense_reactions as DEFENSE
    policy(engine.r)
    evidence = CHOICES.require_accuracy_interrupt(engine, owner, SOURCE, event_id)
    if owner.fainted or not ABILITIES.active(owner, SOURCE):
        raise ValueError('active owned Tera Shell required')
    if HOME.type_change_blocked(owner):
        raise ValueError('current transformation prevents Tera Shell type replacement')
    plan = {'source': SOURCE, 'clause_id': CLAUSE, 'event_id': evidence['event_id'],
            'completion_id': evidence['completion_id'], 'owner_id': owner.entity_id,
            'attacker_id': evidence['attacker'].entity_id, 'move': DEFENSE._move_facts(evidence['move']),
            'chosen_type': chosen_type, 'original_stab_types': list(HOME.stab_types(owner)),
            'grant_key': 'tera_shell:' + event_id + ':' + owner.entity_id}
    if evidence['recipient'] is not owner:
        raise ValueError('actual hit recipient must own Tera Shell')
    return deepcopy(_validate_plan(engine.r, plan))


def _timing(plan):
    return {'source': SOURCE, 'grant_source': plan['grant_key'], 'tera_shell': plan['event_id'],
            'effect_contract': True, 'encounter_end': True}


def _metadata(plan):
    return {'kind': 'effect', 'grants': {}, 'tera_shell': plan['event_id'],
            'rule_id': SOURCE, 'owner_id': plan['owner_id'],
            'completion_id': plan['completion_id'], 'lifetime': 'encounter'}


def activate(engine, owner, plan):
    _validate_plan(engine.r, plan)
    expected = prepare(engine, owner, plan['event_id'], plan['chosen_type'])
    if expected != plan:
        raise ValueError('Tera Shell plan differs from actual authorized hit or STAB state')
    key = plan['grant_key']
    previous = owner.spec.get(KEY, {}).get(key)
    if previous is not None:
        if previous != plan or key not in owner.spec.get(GRANTS.KEY, {}).get('sources', {}):
            raise ValueError('Tera Shell activation identity cannot be reused')
        return {'grant_key': key, 'chosen_type': plan['chosen_type']}
    for record in list(TIME.records(owner)):
        if 'tera_shell' in record:
            TIME.expire(engine, owner, record, ending='replaced')
    metadata = _metadata(plan)
    GRANTS._source(owner, key, metadata.pop('kind'), **{k: v for k, v in metadata.items() if k != 'grants'})
    GRANTS.type_operation(owner, 'set', [plan['chosen_type']], key)
    owner.spec.setdefault(KEY, {})[key] = deepcopy(plan)
    TIME.install(engine, owner, _timing(plan))
    return {'grant_key': key, 'chosen_type': plan['chosen_type']}


def validate_world(engine, index=None):
    import world_entities as WORLD
    actors = index if index is not None else WORLD.actor_index(engine)
    if not isinstance(actors, dict):
        actors = {a.entity_id: a for a in actors}
    for owner in actors.values():
        receipts = owner.spec.get(KEY, {})
        if not isinstance(receipts, dict):
            raise ValueError('Tera Shell receipt mapping required')
        for key, plan in receipts.items():
            _validate_plan(engine.r, plan)
            if key != plan['grant_key'] or owner.entity_id != plan['owner_id']:
                raise ValueError('Tera Shell receipt owner mismatch')
            event = getattr(engine, '_passive_events', {}).get(plan['event_id'], {})
            attempts = event.get('ability_interrupts', {}).get('attempts', [])
            matches = [a for a in attempts if a.get('owner_id') == owner.entity_id and
                       a.get('source') == SOURCE and a.get('outcome') == 'activated' and
                       a.get('paid') is True and a.get('plan') == plan]
            if len(matches) != 1:
                raise ValueError('Tera Shell receipt requires authenticated paid native activation')
            source = owner.spec.get(GRANTS.KEY, {}).get('sources', {}).get(key)
            timed = [r for r in TIME.records(owner) if r.get('grant_source') == key]
            operation = owner.spec.get(GRANTS.KEY, {}).get('type_sources', {}).get('sources', {}).get(key)
            if source is None:
                if timed or operation is not None:
                    raise ValueError('expired Tera Shell cannot retain a type or timing grant')
            else:
                expected_time = {**_timing(plan), 'owned_statuses': set(), 'installing': False}
                if source != _metadata(plan) or timed != [expected_time] or operation != {
                        'mode': 'set', 'values': [plan['chosen_type']], 'fallback': None}:
                    raise ValueError('Tera Shell exact type grant and encounter lifetime required')
        if any('tera_shell' in s and k not in receipts for k, s in
               owner.spec.get(GRANTS.KEY, {}).get('sources', {}).items()):
            raise ValueError('unreceipted Tera Shell source')
        if any('tera_shell' in r and r.get('grant_source') not in receipts for r in TIME.records(owner)):
            raise ValueError('unreceipted Tera Shell lifetime')
        _live(owner)
    for event in getattr(engine, '_passive_events', {}).values():
        for attempt in event.get('ability_interrupts', {}).get('attempts', []):
            if attempt.get('source') == SOURCE and attempt.get('outcome') == 'activated':
                plan = attempt.get('plan', {})
                owner = actors.get(attempt.get('owner_id'))
                if owner is None or owner.spec.get(KEY, {}).get(plan.get('grant_key')) != plan:
                    raise ValueError('native Tera Shell activation lost its owned receipt')
    return True

