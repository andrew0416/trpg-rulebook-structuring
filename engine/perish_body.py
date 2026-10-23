"""R0141 source adapter; native completed-hit Reaction authority stays shared."""
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path

import ability_transitions as ABILITIES
import condition_instances as CONDITIONS
import effect_instances as EFFECTS
import linked_move_conditions as LINKED
import world_entities as WORLD

SOURCE = 'ability/멸망의바디'
CLAUSE = 'C2CSV-ABILITY-R0141'
POLICY = 'data/perish-body-policy.json'
NAME = '멸망 카운트'
KEY = 'perish_body_receipts'
TAG = 'perish_body_origin'
PLAN_FIELDS = {'source', 'clause_id', 'event_id', 'completion_id', 'owner_id',
               'attacker_id', 'move', 'targets'}


import resolution_transaction as _FINGERPRINTS

def definition(rules, source=SOURCE):
    if source != SOURCE:
        return None
    row = json.loads((Path(rules.root) / POLICY).read_text(encoding='utf-8'))
    raw = (Path(rules.root) / 'input/db/abilities.csv').read_bytes()
    cells = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))[140]
    digest = _FINGERPRINTS.json_fingerprint(cells, sort_keys=False, compact=True, allow_nan=True)
    if (row.get('schema_version') != 1 or row.get('source') != SOURCE or
            row.get('clause_id') != CLAUSE or row.get('csv_record') != 141 or
            row.get('source_file') != 'input/db/abilities.csv' or
            row.get('source_sha256') != hashlib.sha256(raw).hexdigest() or
            row.get('row_sha256') != digest or row.get('source_cells') != cells or
            rules._selected_rule(SOURCE) != SOURCE):
        raise ValueError('selected exact Perish Body source required')
    expected = {'action': 'standard', 'reaction': True, 'frequency': {'kind': 'daily', 'uses': 1},
                'defensive': True, 'zero_hp_loss_kind': 'hp_setting', 'massive_damage': False}
    condition = {'raw': {'type': 'custom_condition', 'name': NAME, 'on': 'target',
                        'value': 3, 'tick': '-1 at turn start', 'at_zero': 'hp = 0',
                        'cleared_by': ['recall', 'breather', 'faint']},
                 'payload': {'kind': 'custom_condition', 'operation': 'perish_count',
                             'condition': NAME, 'class': 'volatile'},
                 'source_record': {'file': 'input/db/abilities.csv', 'record': 141, 'sha256': digest},
                 'clause_id': CLAUSE}
    if any(row.get(k) != v for k, v in expected.items()) or row.get('condition') != condition:
        raise ValueError('reviewed Perish Body count semantics required')
    return row


def policy(rules):
    return definition(rules)


def condition_definition(rules):
    return deepcopy(definition(rules)['condition'])


def registration(rules, name):
    if name not in (SOURCE, '멸망의바디', 'Perish Body'):
        return None
    definition(rules)
    return {'name': '멸망의바디', 'source_id': SOURCE, 'equivalent_source_ids': [SOURCE]}


def handled(rules, selected_id):
    return selected_id == SOURCE and definition(rules) is not None


def _origin(plan):
    return {key: plan[key] for key in ('event_id', 'completion_id', 'owner_id', 'attacker_id')}


def _validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
        raise ValueError('exact Perish Body pair plan required')
    if plan['source'] != SOURCE or plan['clause_id'] != CLAUSE:
        raise ValueError('Perish Body source plan mismatch')
    for key in ('event_id', 'completion_id', 'owner_id', 'attacker_id'):
        EFFECTS.text(plan[key], 'actual Perish Body ' + key)
    expected = list(dict.fromkeys([plan['attacker_id'], plan['owner_id']]))
    if not isinstance(plan['targets'], list) or len(plan['targets']) != len(expected):
        raise ValueError('actual attacker and ability owner required')
    for identity, target in zip(expected, plan['targets']):
        if (not isinstance(target, dict) or set(target) != {'holder_id', 'existing_id', 'immune'} or
                target['holder_id'] != identity or type(target['immune']) is not bool or
                (target['existing_id'] is not None and
                 (not isinstance(target['existing_id'], str) or not target['existing_id']))):
            raise ValueError('exact Perish Body recipient admission required')
    import reactive_ability_events as REACTIVE
    if not isinstance(plan['move'], dict) or not REACTIVE._melee(plan['move']):
        raise ValueError('actual Melee Move required for Perish Body')
    json.dumps(plan, ensure_ascii=False, allow_nan=False)
    return plan


def _authority(engine, owner, event_id):
    import ability_reaction_choices as REACTIONS
    evidence = REACTIONS.require_post_return_reaction(engine, owner, SOURCE, event_id)
    if evidence['recipient'] is not owner or owner.fainted or not ABILITIES.active(owner, SOURCE):
        raise ValueError('actual surviving Perish Body recipient required')
    WORLD.require_actors(engine, owner, evidence['attacker'])
    return evidence


def prepare(engine, owner, event_id):
    evidence = _authority(engine, owner, event_id)
    row = condition_definition(engine.r)
    import move_defense_reactions as DEFENSE
    plan = {'source': SOURCE, 'clause_id': CLAUSE, 'event_id': evidence['event_id'],
            'completion_id': evidence['completion_id'], 'owner_id': owner.entity_id,
            'attacker_id': evidence['attacker'].entity_id,
            'move': DEFENSE._move_facts(evidence['move']), 'targets': []}
    for target in (evidence['attacker'], owner):
        if any(t['holder_id'] == target.entity_id for t in plan['targets']):
            continue
        LINKED.prepare(engine, owner, target, row['raw'], SOURCE, row)
        old = CONDITIONS.records(target, NAME)
        if len(old) > 1:
            raise ValueError('ambiguous existing Perish count requires explicit cure')
        plan['targets'].append({'holder_id': target.entity_id,
                                'existing_id': old[0]['id'] if old else None,
                                'immune': bool(engine.immune_to(target, NAME))})
    return deepcopy(_validate_plan(plan))


def prepare_condition(engine, owner, target, effect):
    scope = getattr(engine, '_perish_body_apply_scope', None)
    if (not isinstance(scope, dict) or scope.get('owner_id') != owner.entity_id or
            target.entity_id not in scope.get('target_ids', ())):
        raise ValueError('actual Perish Body pair application scope required')
    evidence = _authority(engine, owner, scope['event_id'])
    if {owner.entity_id, evidence['attacker'].entity_id} != set(scope['target_ids']):
        raise ValueError('Perish Body scope differs from actual native recipients')
    row = condition_definition(engine.r)
    return LINKED.prepare(engine, owner, target, effect, SOURCE, row)


def activate(engine, owner, plan):
    _validate_plan(plan)
    _authority(engine, owner, plan['event_id'])
    previous = owner.spec.get(KEY, {}).get(plan['event_id'])
    if previous is not None:
        if previous['plan'] != plan:
            raise ValueError('Perish Body activation identity cannot be reused')
        return deepcopy(previous['activation'])
    if prepare(engine, owner, plan['event_id']) != plan:
        raise ValueError('Perish Body pair admission changed after preflight')
    if hasattr(engine, '_perish_body_apply_scope'):
        raise ValueError('Perish Body pair application cannot nest')
    import custom_condition_effects as CUSTOM
    row = condition_definition(engine.r)
    index = WORLD.actor_index(engine)
    activation = {'event_id': plan['event_id'], 'conditions': []}
    engine._perish_body_apply_scope = {'owner_id': owner.entity_id, 'event_id': plan['event_id'],
                                      'target_ids': [t['holder_id'] for t in plan['targets']]}
    try:
        for admission in plan['targets']:
            target = index[admission['holder_id']]
            created = CUSTOM.grant(engine, owner, target, row['raw'], SOURCE)
            records = CONDITIONS.records(target, NAME)
            record = records[0] if records else None
            if created:
                record[TAG] = _origin(plan)
            activation['conditions'].append({'holder_id': target.entity_id,
                                             'record_id': record['id'] if record else None,
                                             'created': bool(created)})
    finally:
        del engine._perish_body_apply_scope
    owner.spec.setdefault(KEY, {})[plan['event_id']] = {'plan': deepcopy(plan),
                                                     'activation': deepcopy(activation)}
    return deepcopy(activation)


def validate_record(actor, record):
    origin = record.get(TAG)
    if (record.get('source') != SOURCE or not isinstance(origin, dict) or
            set(origin) != {'event_id', 'completion_id', 'owner_id', 'attacker_id'} or
            record[EFFECTS.KEY].get('applied_by_actor_id') != origin['owner_id'] or
            actor.entity_id not in (origin['owner_id'], origin['attacker_id'])):
        raise ValueError('source-owned actual Perish Body condition origin required')
    for key, value in origin.items():
        EFFECTS.text(value, 'Perish Body condition ' + key)
    return True


def _conditions(actor):
    return [*CONDITIONS.records(actor), *actor.spec.get('effect_instance_history', [])]


def _validate_activation(plan, activation, index):
    if (not isinstance(activation, dict) or set(activation) != {'event_id', 'conditions'} or
            activation['event_id'] != plan['event_id'] or
            not isinstance(activation['conditions'], list) or
            len(activation['conditions']) != len(plan['targets'])):
        raise ValueError('exact Perish Body pair activation required')
    for admission, result in zip(plan['targets'], activation['conditions']):
        if (not isinstance(result, dict) or set(result) != {'holder_id', 'record_id', 'created'} or
                result['holder_id'] != admission['holder_id'] or type(result['created']) is not bool):
            raise ValueError('Perish Body condition recipient changed')
        holder = index.get(result['holder_id'])
        if holder is None:
            raise ValueError('actual Perish Body holder missing')
        if admission['existing_id'] is not None:
            if result['created'] or result['record_id'] != admission['existing_id']:
                raise ValueError('Perish Body must not replace or refresh its existing count')
        elif admission['immune']:
            if result['created'] or result['record_id'] is not None:
                raise ValueError('immune Perish Body recipient cannot acquire a new count')
        elif not result['created'] or not isinstance(result['record_id'], str):
            raise ValueError('admitted Perish Body recipient requires its actual count')
        if result['record_id'] is not None:
            records = [r for r in _conditions(holder) if r.get('id') == result['record_id']]
            if len(records) != 1:
                raise ValueError('actual live or terminal Perish Body condition receipt required')
            validate_record(holder, records[0])
            if (records[0][EFFECTS.KEY]['applied_by_actor_id'] != plan['owner_id'] or
                    (result['created'] and records[0][TAG] != _origin(plan))):
                raise ValueError('Perish Body pair issuer or native origin changed')


def validate_world(engine, index=None):
    index = WORLD.actor_index(engine) if index is None else index
    for owner in index.values():
        receipts = owner.spec.get(KEY, {})
        if not isinstance(receipts, dict):
            raise ValueError('Perish Body source receipts required')
        for event_id, receipt in receipts.items():
            if not isinstance(receipt, dict) or set(receipt) != {'plan', 'activation'}:
                raise ValueError('exact Perish Body source receipt required')
            plan = _validate_plan(receipt['plan'])
            if event_id != plan['event_id'] or owner.entity_id != plan['owner_id']:
                raise ValueError('Perish Body receipt owner or event changed')
            completion = getattr(engine, '_move_completions', {}).get(plan['completion_id'], {})
            offer = completion.get('ability_reaction_choices', {}).get('offers', {}).get(event_id, {})
            attempt = offer.get('attempt') or {}
            if (offer.get('status') != 'activated' or attempt.get('source') != SOURCE or
                    attempt.get('owner_id') != owner.entity_id or attempt.get('paid') is not True or
                    attempt.get('plan') != plan or attempt.get('activation') != receipt['activation']):
                raise ValueError('Perish Body receipt lacks its actual paid native Reaction')
            _validate_activation(plan, receipt['activation'], index)
    for holder in index.values():
        for record in _conditions(holder):
            if record.get('source') != SOURCE:
                continue
            validate_record(holder, record)
            origin = record[TAG]
            owner = index.get(origin['owner_id'])
            receipt = owner.spec.get(KEY, {}).get(origin['event_id']) if owner is not None else None
            if (receipt is None or _origin(receipt['plan']) != origin or
                    not any(c['holder_id'] == holder.entity_id and c['record_id'] == record['id']
                            and c['created'] for c in receipt['activation']['conditions'])):
                raise ValueError('Perish Body condition lacks its actual native pair activation')
    for completion in getattr(engine, '_move_completions', {}).values():
        for event_id, offer in completion.get('ability_reaction_choices', {}).get('offers', {}).items():
            attempt = offer.get('attempt') or {}
            if offer.get('status') != 'activated' or attempt.get('source') != SOURCE:
                continue
            owner = index.get(attempt.get('owner_id'))
            receipt = owner.spec.get(KEY, {}).get(event_id) if owner is not None else None
            if receipt != {'plan': attempt.get('plan'), 'activation': attempt.get('activation')}:
                raise ValueError('native Perish Body Reaction lost its source receipt')
    return True

