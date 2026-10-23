"""Explicit synthetic identities for component tests, never production sources.

This harness-only insertion isolates effect/state tests from source selection.
It does not prove admission under the named ruleset; real IDs still use the
unchanged production index. Production modules must never import this module.
"""
from ruleset import ExcludedRuleSelection


def register_synthetic(rules, uid, name='', kind='test_fixture'):
    selection = rules.selection
    if uid in selection.units:
        raise ValueError('A synthetic fixture cannot replace a real identity: ' + uid)
    if uid in rules.ruleset.exclude_units:
        raise ExcludedRuleSelection(uid, 'exclude_units')
    unit = {'id': uid, 'title': name or uid, 'kind': kind,
            'source': {'file': 'test-only/synthetic', 'meaning': 'component fixture, not source admission evidence'},
            'tags': ['test-only-synthetic']}
    selection.units[uid] = unit
    selection.names.setdefault(unit['title'], []).append(uid)
    return uid
