"""Shared selection contract; existing RuleSelection retains admission authority.

A selection identifies the entire definition, never a merge of its fields.
Optional source bytes are verified on every call. A returned record is evidence,
not an authorization token; validate() reselects before it can be reused.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
from types import MethodType
from root_resolution import fingerprint

_VERIFICATION_SCOPE = ContextVar('source_verification_scope', default=None)


def operation_memo():
    """The current verification scope's memo (None outside a scope); other owners may
    memoize per-operation derived indexes in it under their own keys."""
    return _VERIFICATION_SCOPE.get()


@contextmanager
def verification_scope():
    """Within one native state transition each selected definition's source bytes are
    verified once; outside a transition every call verifies. Nested scopes share the outer one."""
    if _VERIFICATION_SCOPE.get() is not None:
        yield
        return
    token = _VERIFICATION_SCOPE.set({})
    try:
        yield
    finally:
        _VERIFICATION_SCOPE.reset(token)


class SourceChangedError(ValueError):
    """A selected native definition no longer has its reviewed source bytes."""


def require_current_source(rules, selected):
    from source_context import verified_source
    scope=_VERIFICATION_SCOPE.get();rid=id(rules)
    seen=set();verified=set()
    def check(uid):
        # Inside a verification scope each definition (with its dependency subtree) is
        # verified once per Rules object; the memo holds the subtree's verified pairs.
        uid=rules.selection.resolve(uid)
        if uid in seen:return frozenset()
        seen.add(uid)
        if scope is not None:
            memo=scope.get((rid,uid))
            if memo is not None:verified.update(memo);return memo
        subtree=set();origin=rules.selection.units[uid]['source']
        references=dict(origin.get('additional_snapshots',{}))
        if origin.get('sha256') is not None:references[origin['file']]=origin['sha256']
        for file,digest in references.items():
            source_root='source-audit' if file.startswith('source-audit/') else 'input'
            if source_root=='source-audit' and getattr(rules.selection,'source_audit_snapshots',{}).get(uid,{}).get(file)!=digest:
                raise SourceChangedError('unregistered source-audit snapshot for '+uid)
            reference={'file':file if source_root=='source-audit' else 'input/'+file.removeprefix('input/'),'sha256':digest}
            if (reference['file'],digest) in verified:continue
            try:verified_source(rules,reference,source_root=source_root)
            except (ValueError,OSError) as exc:raise SourceChangedError('selected source changed: '+uid) from exc
            verified.add((reference['file'],digest));subtree.add((reference['file'],digest))
        for dependency in rules.selection.dependencies.get(uid,()):subtree.update(check(dependency))
        memo=frozenset(subtree)
        if scope is not None:scope[(rid,uid)]=memo
        return memo
    check(selected)
    return verified


def _native_selection(rules, uid, supports_versions=False):
    """Select and verify once; evidence exists only within this native call."""
    if not hasattr(rules,'selection'):return uid,set()
    rules.selection.require_current_filter(rules.ruleset)
    if getattr(rules,'moves',{}).get(uid,{}).get('source')=='weapon':
        from ruleset import require_runtime_weapon
        selected=require_runtime_weapon(rules,uid)
    else:selected=rules.selection.require_supported_version(uid,supports_versions or __import__('glitch_moves').supports_version(rules,uid) or __import__('stockpile_moves').supports_version(rules,uid))
    return selected,require_current_source(rules,selected)


def native_selected_rule(rules, uid, supports_versions=False):
    """Existing native reader, also identifiable without trusting duck hooks."""
    import special_entities as SPECIAL
    if SPECIAL.prime_instance(rules,uid) is not None:return uid
    import coordinator as COORDINATOR
    if COORDINATOR.innovation_instance(rules,uid) is not None:return uid
    import dancer as DANCER
    if DANCER.dance_instance(rules,uid) is not None:return uid
    return _native_selection(rules,uid,supports_versions)[0]


def _policy(value):
    if isinstance(value,dict):return {key:_policy(item) for key,item in value.items()}
    if isinstance(value,(set,frozenset)):return sorted(_policy(item) for item in value)
    if isinstance(value,(list,tuple)):return [_policy(item) for item in value]
    return value


def select(rules, requested_id, *, source=None, supports_versions=False):
    if type(requested_id) is not str or not requested_id.strip():
        raise ValueError('actual requested source identity required')
    if type(supports_versions) is not bool:raise ValueError('explicit reader version support required')
    if not hasattr(rules,'selection'):raise ValueError('actual rule selection index required')
    reader=rules._selected_rule
    # A proxy can forward method metadata, including __class__; only an actual
    # bound native method can share this call's freshness evidence.
    if type(reader) is MethodType and reader.__func__ is native_selected_rule and reader.__self__ is rules:
        selected,verified=_native_selection(rules,requested_id,supports_versions)
    else:
        # An override can perform arbitrary work. It receives its original call,
        # and cannot lend native freshness evidence to the following boundary.
        selected=reader(requested_id,supports_versions=True) if supports_versions else reader(requested_id)
        verified=set()
    if selected not in rules.selection.units:raise ValueError('selected replacement lacks registered definition')
    origin=rules.selection.units[selected]['source']
    if source is not None:
        if type(source) is not dict or set(source)!={'file','sha256'}:
            raise ValueError('source file and sha256 required')
        if type(source['file']) is not str or origin.get('file')!=source['file'].removeprefix('input/'):
            raise ValueError('source does not match selected rule')
    registered=getattr(rules,'_authored_policy_sources',{}).get(selected)
    if source is not None and registered is not None and registered['source']!=source:
        raise ValueError('authored policy source differs from registered provenance')
    pinned=origin.get('sha256')
    if pinned is not None:
        pinned_reference={'file':'input/'+origin['file'].removeprefix('input/'),'sha256':pinned}
        if source is not None and source!=pinned_reference:
            raise ValueError('source changed or supplied hash differs from registered source snapshot')
        source=pinned_reference
    if source is not None:
        registered=getattr(rules,'_authored_policy_sources',{}).get(selected)
        if registered is not None and registered['source']!=source:
            raise ValueError('authored policy source differs from registered provenance')
        from source_context import verified_source
        if (source['file'],source['sha256']) not in verified:verified_source(rules,source)
    return deepcopy({'schema':1,'requested_id':requested_id,'selected_id':selected,
        'version':rules.ruleset.unit_versions.get(selected),'source':origin,
        'verified_reference':source,'supports_versions':supports_versions,
        'profile':rules.ruleset.name,'selection_policy_hash':fingerprint(_policy(rules.ruleset.selection_policy())),
        'root':str(Path(rules.root).resolve())})


def validate(rules, record):
    if type(record) is not dict or type(record.get('schema')) is not int or record.get('schema')!=1:
        raise ValueError('source selection record required')
    current=select(rules,record.get('requested_id'),source=record.get('verified_reference'),
                   supports_versions=record.get('supports_versions'))
    if current!=record:raise ValueError('source selection changed; select the complete definition again')
    return current


def _policy_definitions(definitions):
    rows = [definitions] if type(definitions) is dict else definitions
    if type(rows) is not list or not rows:
        raise ValueError('complete policy definitions required')
    for row in rows:
        if (type(row) is not dict or not {'rule_id', 'source', 'values'} <= set(row)
                or type(row['rule_id']) is not str or not row['rule_id'].strip()
                or type(row['values']) is not dict):
            raise ValueError('policy rule_id, source and complete values required')
        source = row['source']
        if (type(source) is not dict or set(source) != {'file', 'sha256'}
                or any(type(source[k]) is not str or not source[k] for k in source)):
            raise ValueError('policy source file and sha256 required')
        if 'version' in row and (type(row['version']) is not str or not row['version']):
            raise ValueError('explicit policy version required')
        locator = row.get('locator')
        if locator is not None:
            if type(locator) is not dict or len(locator) != 1:
                raise ValueError('one actual policy source locator required')
            key, value = next(iter(locator.items()))
            if key == 'record':
                valid = type(value) is int and value >= 1
            else:
                valid = (key in ('lines', 'record_span', 'pages') and type(value) is list
                         and len(value) == 2 and all(type(v) is int for v in value)
                         and 1 <= value[0] <= value[1])
            if not valid:raise ValueError('invalid policy source locator')
    return rows


def _policy_matches(selection, definition):
    if (selection.get('selected_id') != definition['rule_id']
            or selection.get('version') != definition.get('version')):
        return False
    source = selection.get('source', {})
    reference = definition['source']
    if (type(source) is not dict or type(source.get('file')) is not str
            or source['file'].removeprefix('input/') != reference['file'].removeprefix('input/')
            or source.get('sha256', reference['sha256']) != reference['sha256']):
        return False
    for key, value in definition.get('locator', {}).items():
        if key == 'record':
            actual = source.get('record', source.get('record_span'))
            if not ((type(actual) is int and actual == value)
                    or (type(actual) is list and len(actual) == 2
                        and all(type(v) is int for v in actual) and actual == [value, value])):
                return False
        else:
            bounds = source.get(key)
            if (type(bounds) is not list or len(bounds) != 2
                    or any(type(v) is not int for v in bounds)
                    or not bounds[0] <= value[0] <= value[1] <= bounds[1]):
                return False
    return True


def bind_policy(rules, requested_id, definitions, *, supports_versions=False):
    """Bind one complete semantic declaration to the actual selected definition.

    No field inheritance or edition precedence is inferred. Existing authored
    declarations may omit locator: the selected registration retains its actual
    locator. This record is evidence for a producer, never reusable authority.
    """
    rows = deepcopy(_policy_definitions(definitions))
    reference = rows[0]['source'] if len(rows) == 1 else None
    selection = rules.select_source_definition(requested_id, source=reference,
                                               supports_versions=supports_versions)
    matches = [row for row in rows if _policy_matches(selection, row)]
    if len(matches) != 1:
        raise ValueError('selected definition requires exactly one complete source policy')
    definition = matches[0]
    reference = definition['source']
    registered = getattr(rules, '_authored_policy_sources', {}).get(selection['selected_id'])
    if registered is not None and registered['source'] != reference:
        raise ValueError('authored policy source differs from registered provenance')
    if selection['verified_reference'] != reference:
        from source_context import verified_source
        verified_source(rules, reference)
    return deepcopy({'schema': 1, 'selection': selection, 'definition': definition,
                     'definition_hash': fingerprint(definition)})


def policy_values(binding, definitions):
    """Read a producer's known declaration without authorizing a new use.

    Historical consumers supply their retained reviewed definitions. A hash of
    caller-editable JSON is not evidence that its values came from a producer.
    Current selection/freshness belongs to bind_policy at the next activation.
    """
    rows = _policy_definitions(definitions)
    if (type(binding) is not dict or set(binding) != {'schema', 'selection', 'definition', 'definition_hash'}
            or type(binding['schema']) is not int or binding['schema'] != 1
            or type(binding['selection']) is not dict
            or type(binding['definition']) is not dict
            or binding['definition_hash'] != fingerprint(binding['definition'])
            or binding['definition_hash'] not in {fingerprint(row) for row in rows}
            or not _policy_matches(binding['selection'], binding['definition'])):
        raise ValueError('known producing source policy required')
    return deepcopy(binding['definition']['values'])
