"""Bounded source-frequency chains; direct test selection remains a cold entry.
Only source-keyed low-level policy cases with unchanged actor/type context join.
A failed contract or unexpected world mutation blocks its remaining chain.
"""
from functools import wraps
from chained_case_lifecycle import bind_case_lifecycle, defer_case_commit
import ast
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import random
import types
import unittest

CHAIN_SIZE = 32
MUTABLE_SPEC = frozenset(('frequency_state', 'move_uses', 'resource_recovery_receipts'))


def eligible(case):
    variants = case.get('variants') or [{'types': [], 'expected': case.get('expected')}]
    if len(variants) != 1 or variants[0]['types'] != []:
        return False
    expected = variants[0]['expected']
    return (isinstance(case.get('id'), str) and case['id'].startswith('move/')
            and isinstance(expected, dict)
            and expected.get('kind') in ('at_will', 'scene', 'daily', 'every_other_turn')
            and type(expected.get('uses')) is int and expected['uses'] > 0)


def _stable(environment):
    engine, actor, target, synthetic = environment
    rules = engine.r
    seen = set()

    def freeze(value):
        if value is rules:
            return ('rules_identity', id(rules))
        if value is None or type(value) in (str, int, float, bool, bytes):
            return value
        identity = id(value)
        if identity in seen:
            return ('alias', identity)
        seen.add(identity)
        if isinstance(value, random.Random):
            return ('rng', value.getstate())
        if isinstance(value, dict):
            ignored = MUTABLE_SPEC if value is actor.spec else ()
            return ('dict', tuple((freeze(k), freeze(v)) for k, v in value.items() if k not in ignored))
        if isinstance(value, (list, tuple)):
            return (type(value).__name__, tuple(freeze(v) for v in value))
        if isinstance(value, (set, frozenset)):
            return (type(value).__name__, tuple(sorted((freeze(v) for v in value), key=repr)))
        if isinstance(value, types.FunctionType):
            cells = tuple(freeze(c.cell_contents) for c in (value.__closure__ or ()))
            return ('function', identity, freeze(value.__defaults__), freeze(value.__kwdefaults__), cells)
        if isinstance(value, types.MethodType):
            return ('method', freeze(value.__self__), freeze(value.__func__))
        # Native class references and decorated methods are authority metadata,
        # not actor instances. Preserve their namespaces and callable state;
        # never invoke a descriptor to inspect its class-owned definition.
        if isinstance(value, property):
            return ('property', identity, freeze(value.fget), freeze(value.fset),
                    freeze(value.fdel), freeze(value.__doc__))
        if isinstance(value, (staticmethod, classmethod)):
            return (type(value).__name__, identity, freeze(value.__func__), freeze(vars(value)))
        # event_trace.operation retains these exact stdlib objects in closures.
        # Project all signature slots without descending into enum/type internals.
        if type(value) is inspect.Signature:
            return ('signature', identity, tuple((name, freeze(parameter))
                    for name, parameter in value.parameters.items()), freeze(value.return_annotation))
        if type(value) is inspect.Parameter:
            return ('parameter', identity, value.name, id(value.kind), value.kind.name,
                    value.kind.value, freeze(value.default), freeze(value.annotation))
        if isinstance(value, type):
            return ('class', identity, type(value).__module__, type(value).__qualname__,
                    tuple((id(base), base.__module__, base.__qualname__) for base in value.__bases__),
                    tuple((name, freeze(member)) for name, member in vars(value).items()))
        if type(value) in (types.GetSetDescriptorType, types.MemberDescriptorType):
            return ('native_descriptor', identity, type(value).__name__,
                    id(value.__objclass__), value.__name__)
        declared_slots = tuple(name for cls in type(value).__mro__
                               for name in ((cls.__dict__.get('__slots__'),) if isinstance(cls.__dict__.get('__slots__'), str)
                                            else cls.__dict__.get('__slots__', ()))
                               if name not in ('__dict__', '__weakref__') and hasattr(value, name))
        if hasattr(value, '__dict__'):
            ignored = ('move_uses',) if value is actor else ()
            return (type(value).__module__, type(value).__qualname__, identity,
                    tuple((k, freeze(v)) for k, v in vars(value).items() if k not in ignored),
                    tuple((name, freeze(getattr(value, name))) for name in declared_slots))
        slots = tuple(name for cls in type(value).__mro__
                      for name in ((cls.__dict__.get('__slots__'),) if isinstance(cls.__dict__.get('__slots__'), str)
                                   else cls.__dict__.get('__slots__', ()))
                      if name not in ('__dict__', '__weakref__') and hasattr(value, name))
        if slots:
            return ('slots', identity, tuple((name, freeze(getattr(value, name))) for name in slots))
        if type(value) is object:
            return ('identity_token', identity)
        raise AssertionError('unreviewed opaque connection state: ' + type(value).__qualname__)

    # Rules data is class-shared in both cold and connected modes. Mutable
    # adjudications are separately guarded; native worlds remain exact objects.
    return (freeze(engine), freeze(actor), freeze(target), synthetic,
            freeze(getattr(rules, 'ruleset', None)), freeze(getattr(rules, 'rulings', None)))


def _rule_digest(value):
    def plain(v):
        if v is None or type(v) in (str, int, float, bool):
            return v
        if isinstance(v, dict):
            return {k: plain(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [plain(x) for x in v]
        if isinstance(v, (set, frozenset)):
            return sorted((plain(x) for x in v), key=repr)
        raise AssertionError('unreviewed rule declaration value: ' + type(v).__qualname__)
    return hashlib.sha256(json.dumps(plain(value), ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode('utf-8')).hexdigest()


class RulesSourceGuard:
    """Capture selected declaration rows once; check only the current source.

    Independent fresh chunks share this read-only baseline, not failure status.
    A modified source is refused when it is read, without blocking other sources.
    """
    def __init__(self, source_ids):
        self.source_ids = tuple(dict.fromkeys((*source_ids, 'audit/frequency')))
        self.baselines = {}

    @staticmethod
    def global_policy(rules):
        rulings = rules.rulings
        return {'selection_policy': rules.ruleset.selection_policy(),
                'selection_snapshot': rules.selection._selection_policy,
                'use_hand': rules.use_hand,
                'rulings': {k: getattr(rulings, k) for k in
                            ('formulas', 'situational', 'answers', 'hooks', 'provider')}}

    @staticmethod
    def source_policy(rules, mid):
        selection = rules.selection
        visited = set()
        def source(uid):
            if uid in visited:
                return {'revisited': uid}
            visited.add(uid)
            alias = selection.aliases.get(uid)
            dependencies = selection.dependencies.get(uid, ())
            raw = rules.moves.get(uid, {})
            name = raw.get('name')
            return {'id': uid, 'move': raw,
                    'mechanics': {key: getattr(rules, key).get(uid) for key in
                                  ('moves_hand', 'moves_reviewed', 'moves_mech')},
                    'llm': rules.moves_llm.get(name),
                    'llm_partial': rules.moves_llm_partial.get(name),
                    'unit': selection.units.get(uid), 'excluded': selection.excluded.get(uid),
                    'conflict': selection.conflicts.get(uid),
                    'alias': None if alias is None else source(alias),
                    'dependencies': [source(dep) for dep in dependencies],
                    'rulings': {'mech': rules.rulings.mech.get(uid),
                                'effects': rules.rulings.effects.get(uid)}}
        return source(mid)

    def check(self, rules, mid):
        identity = id(rules)
        if identity not in self.baselines:
            self.baselines[identity] = (rules, _rule_digest(self.global_policy(rules)),
                {uid: _rule_digest(self.source_policy(rules, uid)) for uid in self.source_ids})
        original, global_digest, sources = self.baselines[identity]
        if original is not rules or _rule_digest(self.global_policy(rules)) != global_digest:
            raise AssertionError('frequency connection source profile/adjudication changed')
        for uid in (mid, 'audit/frequency'):
            if _rule_digest(self.source_policy(rules, uid)) != sources[uid]:
                raise AssertionError('frequency connection source declaration changed: ' + uid)


class SourceFrequencyChain:
    def __init__(self, source_guard):
        self.environment = None
        self.baseline = None
        self.seen = set()
        self.current = None
        self.blocked = None
        self.source_guard = source_guard
        self.entries = []

    def acquire(self, builder, case, variant):
        if self.current != case['id'] or not eligible(case) or variant['types']:
            raise AssertionError('incompatible source-frequency chain entry')
        if self.environment is None:
            self.environment = builder()
            self.baseline = _stable(self.environment)
        engine, actor, target, synthetic = self.environment
        if _stable(self.environment) != self.baseline:
            raise AssertionError('frequency chain changed non-quota world state')
        expected_rules = getattr(getattr(builder, '__self__', None), 'rules', engine.r)
        if expected_rules is not engine.r:
            raise AssertionError('frequency connection cannot cross a class Rules replacement')
        self.source_guard.check(engine.r, case['id'])
        ledger = actor.spec.get('frequency_state', {})
        mid = case['id']
        if mid in actor.move_uses or mid in ledger.get('moves', {}):
            raise AssertionError('source does not have its original unused quota entry')
        if getattr(engine, 'session_frequency', False):
            raise AssertionError('source-frequency fixture is not a session-policy test')
        return self.environment

    def execute(self, test, case, callback):
        if self.blocked is not None:
            raise unittest.SkipTest('blocked connected predecessor: ' + self.blocked)
        mid = case['id']
        if mid in self.seen or self.current is not None:
            raise AssertionError('duplicate or nested frequency source entry')
        self.current = mid
        try:
            result = callback()
            if self.environment is not None:
                self.source_guard.check(self.environment[0].r, mid)
            if self.environment is None or _stable(self.environment) != self.baseline:
                raise AssertionError('frequency chain changed non-quota world state')
        except BaseException as exc:
            self.blocked = mid + ': ' + type(exc).__name__ + ': ' + str(exc)
            raise
        else:
            state = self.environment[1].spec.get('frequency_state', {})
            entry = {'source_id': mid, 'day': state.get('day', 0),
                     'scene': state.get('scene', 0), 'turn': state.get('turn', 0)}
            def commit():
                self.seen.add(mid)
                self.entries.append(entry)
            defer_case_commit(test, commit)
            return result
        finally:
            self.current = None


def source_fixture(test, case, variant):
    chain = getattr(test, '_source_frequency_chain', None)
    return test.fixture() if chain is None else chain.acquire(test.fixture, case, variant)


def source_case_contract(case, function):
    @wraps(function)
    def wrapped(test):
        chain = getattr(test, '_source_frequency_chain', None)
        if chain is None:
            return function(test)
        return chain.execute(test, case, lambda: function(test))
    wrapped._source_frequency_case = case
    return wrapped


def _tests(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _tests(test)
        else:
            yield test


def prepare_source_frequency_cases(cls, cases, source_cases, root=None):
    """Wire only final selected instances, preserving their exact ID and order."""
    cases = tuple(cases)
    if any(type(case) is not cls for case in cases):
        raise ValueError('frequency connection requires this exact TestCase class')
    if len({id(case) for case in cases}) != len(cases) or len({case.id() for case in cases}) != len(cases):
        raise ValueError('frequency selection repeats a case instance or ID')
    if any(hasattr(case, '_source_frequency_chain') for case in cases):
        raise ValueError('frequency cases already have a connection context')
    expected = {case['id']: case for case in source_cases}
    if len(expected) != len(source_cases):
        raise ValueError('source-keyed connection requires distinct case IDs')
    chunks, pending = [], []
    for test in cases:
        function = getattr(cls, test._testMethodName)
        case = getattr(function, '_source_frequency_case', None)
        if case is not None and case != expected.get(case['id']):
            raise ValueError('generated case differs from declared source binding')
        if case is None or not eligible(case):
            if len(pending) > 1:
                chunks.append(pending)
            pending = []
            continue
        pending.append(test)
        if len(pending) == CHAIN_SIZE:
            chunks.append(pending)
            pending = []
    if len(pending) > 1:
        chunks.append(pending)
    if not chunks:
        return None
    if root is not None:
        verify_source_connection_inputs(root)
    sources = [getattr(cls, test._testMethodName)._source_frequency_case['id']
               for chunk in chunks for test in chunk]
    guard = RulesSourceGuard(sources)
    for chunk in chunks:
        chain = SourceFrequencyChain(guard)
        for test in chunk:
            test._source_frequency_chain = chain
            bind_case_lifecycle(test, lambda reason, chain=chain: setattr(chain, 'blocked', chain.blocked or reason))
    return cases


def connected_source_suite(suite, source_cases):
    tests = list(_tests(suite))
    grouped = {}
    for test in tests:
        grouped.setdefault(type(test), []).append(test)
    for cls, cases in grouped.items():
        prepare_source_frequency_cases(cls, cases, source_cases)
    return unittest.TestSuite(tests)


def verify_source_connection_inputs(root):
    contract = json.loads((Path(__file__).with_name('frequency_source_connection_contract.json')).read_text(encoding='utf-8'))
    for relative, expected in contract['input_hashes'].items():
        actual = hashlib.sha256((Path(root) / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('frequency source connection proof is stale: ' + relative)
    for entry in contract.get('function_contracts', []):
        tree = ast.parse((Path(root) / entry['file']).read_text(encoding='utf-8-sig'))
        definitions = {}
        def collect(nodes, prefix=''):
            for node in nodes:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    name = (prefix + '.' if prefix else '') + node.name
                    if not isinstance(node, ast.ClassDef):
                        definitions.setdefault(name, []).append(node)
                    collect(node.body, name)
        collect(tree.body)
        def digest(nodes):
            text = '\n'.join(ast.dump(node, include_attributes=False) for node in nodes)
            return hashlib.sha256(text.encode('utf-8')).hexdigest()
        for name, expected in entry['symbols'].items():
            if name not in definitions or digest(definitions[name]) != expected:
                raise ValueError('frequency connection function changed: ' + entry['file'] + ':' + name)
        def strip(nodes):
            result = []
            for node in nodes:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    node = deepcopy(node)
                    node.body = [ast.Pass()]
                    result.append(node)
                    continue
                if isinstance(node, ast.ClassDef):
                    node = deepcopy(node)
                    node.body = strip(node.body)
                result.append(node)
            return result
        tree.body = strip(tree.body)
        if digest([tree]) != entry['module_structure_sha256']:
            raise ValueError('frequency connection module declarations changed: ' + entry['file'])
