"""One native regression; direct debug calls below do not claim 59 unittest starts."""
import math
import unittest


def _assertion_value(value):
    kind=type(value)
    if value is None or kind in (bool,int,str):return (kind.__name__,value)
    if kind is float and math.isfinite(value):return ('float',value)
    if kind in (list,tuple):return (kind.__name__,tuple(_assertion_value(v) for v in value))
    if kind is dict:return ('dict',tuple((_assertion_value(k),_assertion_value(v)) for k,v in value.items()))
    if isinstance(value,tuple):
        from effect_contracts import BatchResult
        # Original assertions compare its tuple counts; lifecycle guards check the world separately.
        if kind is BatchResult:return ('tuple',tuple(_assertion_value(v) for v in value))
    raise AssertionError('unsupported reference assertion value: '+kind.__qualname__)


def _compare_reference_modes(Case,names):
    if len(names)!=59 or len(set(names))!=59:raise AssertionError('exact 59 original reference bodies required')
    original_fixture=Case.fixture;original_assert=Case.assertEqual
    missing=object();prior={name:Case.__dict__.get(name,missing) for name in ('fixture','assertEqual','rules')}
    observations={};counts={};owners=[];active=None
    def fixture(self,item=None,feat=False):
        key='main' if item or feat else 'original_plain_comparator'
        counts[active][key]=counts[active].get(key,0)+1
        return original_fixture(self,item,feat)
    def assertion(self,a,b,*args,**kwargs):
        observations[active][self.id()].append(_assertion_value((a,b,args,kwargs)))
        return original_assert(self,a,b,*args,**kwargs)
    Case.fixture=fixture;Case.assertEqual=assertion
    try:
        for active in ('cold','connected'):
            observations[active]={};counts[active]={}
            try:
                Case.setUpClass()
                try:
                    owners.append(Case.rules)
                    if len(owners)==2 and owners[0] is owners[1]:raise AssertionError('fresh Rules owner required for each mode')
                    cases=[Case(name) for name in sorted(names)];expected={case.id() for case in cases}
                    if active=='connected':
                        original=tuple(cases);cases=list(Case.prepare_chained_cases(cases))
                        if len(cases)!=59 or {id(case) for case in cases}!={id(case) for case in original}:
                            raise AssertionError('prepared reference selection changed original instances')
                    if {case.id() for case in cases}!=expected:raise AssertionError('reference original IDs changed')
                    for case in cases:
                        observations[active][case.id()]=[]
                        # debug retains each original setUp/body/tearDown/cleanup and raises failures.
                        case.debug()
                        if not observations[active][case.id()]:raise AssertionError('original reference body had no assertion events')
                finally:Case.tearDownClass()
            finally:
                Case.doClassCleanups()
                if Case.tearDown_exceptions:
                    _,error,traceback=Case.tearDown_exceptions[0];raise error.with_traceback(traceback)
        if observations['cold']!=observations['connected']:raise AssertionError('original reference assertion sequences differ')
        if counts!={'cold':{'main':59,'original_plain_comparator':36},'connected':{'main':19,'original_plain_comparator':36}}:
            raise AssertionError('original cold/connected/comparator factory counts differ: '+repr(counts))
        return counts
    except unittest.SkipTest as error:
        raise AssertionError('reference equivalence cannot accept skipped/blocked bodies: '+str(error)) from error
    finally:
        for name,value in prior.items():
            if value is missing:
                if name in Case.__dict__:delattr(Case,name)
            else:setattr(Case,name,value)


class ReferenceConnectionEquivalenceTests(unittest.TestCase):
    def test_original_59_bodies_cold_and_connected_equivalent(self):
        from tools import test_reference_rules as reference
        from reference_rule_connections import GIFT_STEPS
        names=[f'test_plate_{index:02d}_{mode}' for index in range(1,19) for mode in ('matching','nonmatching','lifecycle')]+list(GIFT_STEPS)
        _compare_reference_modes(reference.ReferenceRuleTests,names)
