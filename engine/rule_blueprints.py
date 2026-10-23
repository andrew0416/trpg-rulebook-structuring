"""Serializable rule specifications, including explicit unresolved obligations.

This is an authoring boundary, not a second actor store or effect dispatcher.
A resolved specification still needs a verified native adapter. Never eval text.
"""
from copy import deepcopy
import json

AXES = ('trigger', 'target', 'effect', 'composition', 'duration',
        'consumption', 'release', 'exception', 'source_policy')
KINDS = ('contract_review', 'source_decision', 'context_input', 'implementation')


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be nonempty text')


def validate(spec):
    """Validate authoring structure without declaring mechanics implemented."""
    if not isinstance(spec, dict) or spec.get('schema') != 'rule-blueprint-v1':
        raise ValueError('unsupported rule blueprint')
    for key in ('id', 'family', 'source_text', 'qualitative_reason'):
        _text(spec.get(key), key)
    if not isinstance(spec.get('contract'), dict) or set(spec['contract']) != set(AXES):
        raise ValueError('all contract axes must be explicit')
    requirements = spec.get('requirements')
    if not isinstance(requirements, dict):
        raise ValueError('requirements must be keyed by stable ID')
    for key, req in requirements.items():
        _text(key, 'requirement ID')
        if not isinstance(req, dict) or req.get('kind') not in KINDS:
            raise ValueError('unknown requirement kind')
        for field in ('question', 'resume_when'):
            _text(req.get(field), field)
    used = set()
    for axis, cell in spec['contract'].items():
        if not isinstance(cell, dict):
            raise ValueError('typed contract cell required')
        state = cell.get('state')
        if state in ('bound', 'not_applicable'):
            if set(cell) != ({'state', 'value', 'evidence'} if state == 'bound' else {'state', 'evidence'}):
                raise ValueError('resolved cell fields disagree')
            _text(cell.get('evidence'), 'resolution evidence')
            if state == 'bound' and cell['value'] is None:
                raise ValueError('unknown is not a bound value')
        elif state == 'deferred':
            if set(cell) != {'state', 'requires'} or not isinstance(cell['requires'], list) or not cell['requires']:
                raise ValueError('deferred cell requires explicit dependency IDs')
            for key in cell['requires']:
                if key not in requirements:
                    raise ValueError('dangling requirement: ' + str(key))
                used.add(key)
        else:
            raise ValueError('unknown contract state: ' + str(state))
    if used != set(requirements):
        raise ValueError('unused requirements must be removed when resolved')
    json.dumps(spec, ensure_ascii=False, allow_nan=False)
    return spec


def pending(spec):
    validate(spec)
    return deepcopy(spec['requirements'])


def resolve(spec, requirement_id, replacements):
    """Pure update; every dependent axis must be resolved explicitly together."""
    validate(spec)
    if requirement_id not in spec['requirements']:
        raise ValueError('unknown requirement')
    affected = {a for a, cell in spec['contract'].items()
                if requirement_id in cell.get('requires', [])}
    if set(replacements) != affected:
        raise ValueError('resolve every dependent axis, and no unrelated axes')
    result = deepcopy(spec)
    result['contract'].update(deepcopy(replacements))
    still_used = {key for cell in result['contract'].values() for key in cell.get('requires', [])}
    if set(spec['requirements']) - still_used != {requirement_id}:
        raise ValueError('resolution cannot silently remove another requirement')
    result['requirements'] = {key: req for key, req in result['requirements'].items() if key in still_used}
    if requirement_id in still_used:
        raise ValueError('resolution left the same requirement pending')
    return validate(result)


def resolved_contract(spec):
    """Return data for adapter review, never an execution authorization."""
    validate(spec)
    if spec['requirements']:
        raise ValueError('unresolved contract: ' + ', '.join(spec['requirements']))
    return deepcopy(spec['contract'])


def dependency_index(specs):
    result = {}
    seen = set()
    for spec in specs:
        validate(spec)
        if spec['id'] in seen:
            raise ValueError('duplicate blueprint ID')
        seen.add(spec['id'])
        for key, requirement in spec['requirements'].items():
            row = result.setdefault(key, {'requirement': deepcopy(requirement), 'clauses': []})
            if row['requirement'] != requirement:
                raise ValueError('inconsistent shared requirement: ' + key)
            row['clauses'].append(spec['id'])
    return result
