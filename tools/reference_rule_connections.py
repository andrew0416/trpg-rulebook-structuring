"""Explicit plate and Gift lifecycles; unrelated and partial selections stay cold."""
from copy import deepcopy
from functools import wraps
import random
import types
import unittest

GIFT_STEPS=(
    'test_gift_one_additional_injury_per_acknowledged_trigger',
    'test_gift_fourth_use_rejected_without_target_mutation',
    'test_gift_scene_end_does_not_refresh_daily_limit',
    'test_gift_usage_survives_serialized_spec_and_reregistration',
    'test_gift_explicit_new_day_refreshes_only_daily_uses',
)


def _world(environment):
    """Exact handoff graph, including identity, aliases, clock, RNG and resources."""
    rules=environment[0].r;seen=set()
    def freeze(value):
        if value is rules:return ('rules',id(rules))
        if value is None or type(value) in (str,int,float,bool,bytes):return value
        identity=id(value)
        if identity in seen:return ('alias',identity)
        seen.add(identity)
        if isinstance(value,random.Random):return ('rng',value.getstate())
        if isinstance(value,dict):return ('dict',tuple((freeze(k),freeze(v)) for k,v in value.items()))
        if isinstance(value,(list,tuple)):return (type(value).__name__,tuple(freeze(v) for v in value))
        if isinstance(value,(set,frozenset)):return (type(value).__name__,tuple(sorted((freeze(v) for v in value),key=repr)))
        if isinstance(value,types.FunctionType):
            return ('function',identity,freeze(value.__defaults__),freeze(value.__kwdefaults__),
                    tuple(freeze(c.cell_contents) for c in (value.__closure__ or ())))
        if isinstance(value,types.MethodType):return ('method',freeze(value.__self__),freeze(value.__func__))
        slots=tuple(name for cls in type(value).__mro__
                    for name in ((cls.__dict__.get('__slots__'),) if isinstance(cls.__dict__.get('__slots__'),str) else cls.__dict__.get('__slots__',()))
                    if name not in ('__dict__','__weakref__') and hasattr(value,name))
        if hasattr(value,'__dict__'):
            return (type(value).__module__,type(value).__qualname__,identity,
                    tuple((k,freeze(v)) for k,v in vars(value).items()),tuple((k,freeze(getattr(value,k))) for k in slots))
        if slots:return ('slots',identity,tuple((k,freeze(getattr(value,k))) for k in slots))
        if type(value) is object:return ('identity_token',identity)
        raise AssertionError('unreviewed reference lifecycle state: '+type(value).__qualname__)
    return tuple(freeze(value) for value in environment)


class ReferenceLifecycle:
    def __init__(self,key,steps):
        self.key,self.steps=key,tuple(steps)
        self.cursor=0;self.environment=None;self.failed=None;self.snapshot=None;self.profile=None

    def source_profile(self,test):
        owner=test.rules
        declaration=owner.item_effects(self.key[1]) if self.key[0]=='plate' else owner.feat_effects(self.key[1])
        rulings=getattr(owner,'rulings',None)
        ruleset=getattr(owner,'ruleset',None)
        # Native RuleFilter/Rulings use identity equality, not value equality.
        # Retain the actual owner and class identities, copying every value field
        # (including RuleFilter.alias_conflicts), never the owner object itself.
        def owner_state(value):
            if hasattr(value,'__dict__'):return (type(value),id(value),deepcopy(vars(value)))
            return deepcopy(value)
        return (owner_state(ruleset),owner_state(rulings),deepcopy(declaration))

    def acquire(self,test,key,builder):
        if key!=self.key:raise AssertionError('reference lifecycle source mismatch')
        if self.environment is None:
            if self.cursor!=0:raise AssertionError('missing predecessor environment; no cold fallback')
            self.environment=builder()
            if self.environment[0].r is not test.rules:raise AssertionError('reference lifecycle Rules identity differs')
            self.profile=self.source_profile(test)
        return self.environment

    def execute(self,test,body):
        if self.failed:raise unittest.SkipTest('blocked connected predecessor: '+self.failed)
        try:
            if self.cursor>=len(self.steps) or test._testMethodName!=self.steps[self.cursor]:
                raise AssertionError('reference lifecycle order differs')
            if self.environment is not None:
                if self.environment[0].r is not test.rules or self.source_profile(test)!=self.profile:
                    raise AssertionError('reference lifecycle Rules/source profile changed')
                if _world(self.environment)!=self.snapshot:raise AssertionError('reference lifecycle handoff changed')
            result=getattr(getattr(test,'_outcome',None),'result',None)
            before=(len(result.failures),len(result.errors)) if result is not None else None
            value=body(test)
            if before is not None and before!=(len(result.failures),len(result.errors)):
                self.failed=test.id();return value
            if self.environment is None:raise AssertionError('reference lifecycle did not construct its first environment')
            if self.source_profile(test)!=self.profile:raise AssertionError('reference lifecycle source mutated')
            self.snapshot=_world(self.environment);self.cursor+=1
            return value
        except BaseException:
            self.failed=test.id();raise


def registered_plate_state(test,name):
    """Independent original O_A constructor, also used once by a full plate chain."""
    chain=getattr(test,'_reference_lifecycle',None)
    builder=lambda:test.fixture(name)
    return chain.acquire(test,('plate',name),builder) if chain else builder()


def exhausted_gift_state(test,manual_feat,gift):
    """Original cold O_A producer; full chains consume the prior three actual uses."""
    chain=getattr(test,'_reference_lifecycle',None)
    if chain:return chain.acquire(test,('gift',gift),lambda:None)
    e,a,b=test.fixture(feat=True)
    for _ in range(3):manual_feat(e,a,gift,b)
    return e,a,b


def initial_gift_state(test,gift):
    chain=getattr(test,'_reference_lifecycle',None)
    builder=lambda:test.fixture(feat=True)
    return chain.acquire(test,('gift',gift),builder) if chain else builder()


def reference_step(function):
    @wraps(function)
    def wrapped(test):
        chain=getattr(test,'_reference_lifecycle',None)
        return chain.execute(test,function) if chain else function(test)
    return wrapped


def prepare_reference_cases(cls,cases,plates,gift):
    cases=tuple(cases)
    if any(type(case) is not cls for case in cases):raise ValueError('reference connection requires exact case class')
    if len({case.id() for case in cases})!=len(cases):raise ValueError('duplicate reference selection')
    if any(hasattr(case,'_reference_lifecycle') for case in cases):raise ValueError('reference selection already prepared')
    by_name={case._testMethodName:case for case in cases};groups=[]
    for index,(name,_,_) in enumerate(plates,1):
        steps=tuple(f'test_plate_{index:02d}_{mode}' for mode in ('matching','nonmatching','lifecycle'))
        if all(step in by_name for step in steps):groups.append((('plate',name),steps))
    if all(step in by_name for step in GIFT_STEPS):groups.append((('gift',gift),GIFT_STEPS))
    replacements={}
    for key,steps in groups:
        chain=ReferenceLifecycle(key,steps)
        for step in steps:by_name[step]._reference_lifecycle=chain;replacements[step]=steps
    # shortcut: connect complete reviewed families only; review a new partial contract before widening.
    emitted=set();ordered=[]
    for case in cases:
        steps=replacements.get(case._testMethodName)
        if steps is None:ordered.append(case)
        elif steps not in emitted:ordered.extend(by_name[name] for name in steps);emitted.add(steps)
    return tuple(ordered)


def connected_reference_suite(suite,cls,plates,gift):
    def leaves(node):
        if type(node) is unittest.TestSuite:
            for child in node:yield from leaves(child)
        elif isinstance(node,unittest.TestSuite):raise ValueError('custom suite must retain its execution owner')
        else:yield node
    return unittest.TestSuite(prepare_reference_cases(cls,tuple(leaves(suite)),plates,gift))
