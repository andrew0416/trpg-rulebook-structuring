"""Stdlib-only lifecycle guards; no game imports or original rule-body substitutes."""
from copy import deepcopy
from functools import wraps
import inspect
import random
import types
import unittest

import reference_rule_connections as C


def _traced(function):
    signature=inspect.signature(function)
    @wraps(function)
    def run(*args,**kwargs):
        signature.bind(*args,**kwargs)
        return function(*args,**kwargs)
    return run


def _environment(rules=None):
    class Rules:
        pass
    class Actor:
        __slots__=('hp','budget')
        def __init__(self):self.hp=20;self.budget={'standard':1}
        @property
        def health(self):raise AssertionError('a property must not be invoked by snapshotting')
    class Engine:
        policy={'enabled':True}
        def __init__(self):
            self.r=rules if rules is not None else Rules()
            self.rng=random.Random(19);self.elapsed_seconds=0
            self._heavy_native_types=(Engine,Rules,Actor)
            self.items={'plate':1};self.events=[]
        @_traced
        def action(self,target,amount=1):return target.hp-amount
        @staticmethod
        def source(options={'selected':True}):return options
        @classmethod
        def restore(cls,options={'accepted':True}):return options
    engine=Engine();actor=Actor();engine.everyone=[actor]
    return engine,actor


def _rules():
    class Owner:
        pass
    class Rules:
        def item_effects(self,name):return self.declaration
        def feat_effects(self,name):return self.declaration
    rules=Rules();rules.declaration={'source':'reviewed','effect':{'bonus':5}}
    rules.ruleset=Owner();rules.ruleset.profile={'enabled':True};rules.ruleset.alias_conflicts={}
    rules.rulings=Owner();rules.rulings.answers=[];rules.rulings.hooks={'before_damage':[]}
    return rules


class _Case:
    def __init__(self,name,rules):self._testMethodName=name;self.rules=rules;self.calls=0
    def id(self):return 'synthetic.reference.'+self._testMethodName
    def fixture(self,item=None,feat=False):
        self.calls+=1
        engine,actor=_environment(self.rules);target=type(actor)();engine.everyone.append(target)
        return engine,actor,target


class ReferenceLifecycleStateTests(unittest.TestCase):
    def test_real_class_descriptor_graph_is_stable_and_read_only(self):
        class NativeType:pass
        probe=types.SimpleNamespace(r=object(),_heavy_native_types=(NativeType,))
        self.assertEqual(C._world((probe,)),C._world((probe,)))
        environment=_environment();engine,actor=environment
        before=(engine.rng.getstate(),deepcopy(engine.items),deepcopy(actor.budget),actor.hp)
        self.assertIs(type(type(engine).__dict__['__dict__']),types.GetSetDescriptorType)
        self.assertIs(type(type(actor).__dict__['hp']),types.MemberDescriptorType)
        first=C._world(environment)
        self.assertEqual(first,C._world(environment))
        self.assertEqual(before,(engine.rng.getstate(),engine.items,actor.budget,actor.hp))

    def test_class_policy_and_class_replacement_change_world(self):
        environment=_environment();engine,actor=environment
        before=C._world(environment);type(engine).policy['enabled']=False
        self.assertNotEqual(before,C._world(environment))
        before=C._world(environment)
        replacement=type('Actor',(),{'__module__':type(actor).__module__})
        engine._heavy_native_types=(*engine._heavy_native_types[:-1],replacement)
        self.assertNotEqual(before,C._world(environment))

    def test_descriptor_binding_and_property_accessor_change_world(self):
        environment=_environment();engine,actor=environment;owner=type(actor)
        before=C._world(environment);owner.health=property(lambda self:20)
        self.assertNotEqual(before,C._world(environment))
        before=C._world(environment);owner.health.__doc__='changed contract'
        self.assertNotEqual(before,C._world(environment))
        before=C._world(environment);owner.other_slot=owner.hp
        self.assertNotEqual(before,C._world(environment))

    def test_static_and_class_method_callable_values_change_world(self):
        environment=_environment();engine,_=environment;owner=type(engine)
        for name in ('source','restore'):
            with self.subTest(name=name):
                method=vars(owner)[name];before=C._world(environment)
                method.__func__.__defaults__[0]['changed']=True
                self.assertNotEqual(before,C._world(environment))
                before=C._world(environment);method.contract={'new':1}
                self.assertNotEqual(before,C._world(environment))

    def test_signature_parameter_and_return_fields_change_world(self):
        environment=_environment();engine,_=environment
        signature=next(cell.cell_contents for cell in type(engine).action.__closure__
                       if type(cell.cell_contents) is inspect.Signature)
        parameter=signature.parameters['amount']
        for field,value in (('_default',2),('_annotation','reviewed-annotation'),
                            ('_kind',inspect.Parameter.KEYWORD_ONLY)):
            with self.subTest(field=field):
                before=C._world(environment);setattr(parameter,field,value)
                self.assertNotEqual(before,C._world(environment))
        before=C._world(environment);signature._return_annotation='changed-return'
        self.assertNotEqual(before,C._world(environment))

    def test_signature_unknown_fields_fail_closed(self):
        for field in ('_name','_default','_annotation','_kind'):
            with self.subTest(field=field):
                environment=_environment();engine,_=environment
                signature=next(cell.cell_contents for cell in type(engine).action.__closure__
                               if type(cell.cell_contents) is inspect.Signature)
                setattr(signature.parameters['amount'],field,memoryview(b'unreviewed'))
                with self.assertRaisesRegex(AssertionError,'unreviewed reference'):
                    C._world(environment)
        environment=_environment();engine,_=environment
        signature=next(cell.cell_contents for cell in type(engine).action.__closure__
                       if type(cell.cell_contents) is inspect.Signature)
        signature._return_annotation=memoryview(b'unreviewed')
        with self.assertRaisesRegex(AssertionError,'unreviewed reference lifecycle state'):
            C._world(environment)
        signature._return_annotation=inspect.Signature.empty
        signature._parameters={memoryview(b'unreviewed'):inspect.Parameter('known',inspect.Parameter.POSITIONAL_ONLY)}
        with self.assertRaisesRegex(AssertionError,'unreviewed reference lifecycle state'):
            C._world(environment)

    def test_unreviewed_opaque_types_fail_closed(self):
        for value in (memoryview(b'opaque'),complex(1,2),iter(())):
            with self.subTest(kind=type(value).__name__):
                environment=_environment();environment[0].unknown=value
                with self.assertRaisesRegex(AssertionError,'unreviewed reference lifecycle state'):
                    C._world(environment)

    def test_rng_clock_resources_and_aliases_change_world(self):
        for mutate in (lambda e,a:e.rng.random(),lambda e,a:setattr(e,'elapsed_seconds',1),
                       lambda e,a:e.items.update(plate=0),lambda e,a:a.budget.update(standard=0),
                       lambda e,a:setattr(e,'everyone',[deepcopy(a)])):
            environment=_environment();before=C._world(environment)
            mutate(*environment);self.assertNotEqual(before,C._world(environment))

    def test_source_profile_preserves_owner_class_identity_and_all_values(self):
        rules=_rules();case=_Case('one',rules);chain=C.ReferenceLifecycle(('plate','plate'),('one',))
        for mutate in (lambda:setattr(rules.ruleset,'alias_conflicts',{'x':['a','b']}),
                       lambda:rules.ruleset.profile.update(enabled=False),
                       lambda:rules.rulings.answers.append({'answer':True}),
                       lambda:rules.declaration['effect'].update(bonus=6),
                       lambda:setattr(rules,'ruleset',deepcopy(rules.ruleset))):
            before=chain.source_profile(case);mutate()
            self.assertNotEqual(before,chain.source_profile(case))

    def test_lifecycle_reuses_only_successful_exact_predecessor(self):
        rules=_rules();chain=C.ReferenceLifecycle(('plate','plate'),('one','two'))
        first,second=(_Case(name,rules) for name in chain.steps)
        first._reference_lifecycle=second._reference_lifecycle=chain
        seen=[]
        def body(case):
            environment=C.registered_plate_state(case,'plate');seen.append(environment)
            environment[0].events.append(case._testMethodName)
        chain.execute(first,body);chain.execute(second,body)
        self.assertIs(seen[0],seen[1]);self.assertEqual((first.calls,second.calls),(1,0))
        self.assertEqual(chain.cursor,2);self.assertIsNone(chain.failed)

    def test_real_predecessor_failure_blocks_without_builder_fallback(self):
        rules=_rules();chain=C.ReferenceLifecycle(('plate','plate'),('one','two'))
        first,second=(_Case(name,rules) for name in chain.steps)
        def fail(case):raise AssertionError('original assertion failed')
        with self.assertRaisesRegex(AssertionError,'original assertion failed'):chain.execute(first,fail)
        with self.assertRaisesRegex(unittest.SkipTest,'blocked connected predecessor'):
            chain.execute(second,lambda case:case.fixture('plate'))
        self.assertEqual((first.calls,second.calls,chain.cursor),(0,0,0))

    def test_source_rules_identity_and_policy_mutation_block_descendants(self):
        for mutate in (lambda c:setattr(c.environment[0],'r',_rules()),
                       lambda c:c.environment[0].r.declaration['effect'].update(bonus=6),
                       lambda c:c.environment[0].r.ruleset.alias_conflicts.update(x=['a','b'])):
            rules=_rules();chain=C.ReferenceLifecycle(('plate','plate'),('one','two'))
            first,second=(_Case(name,rules) for name in chain.steps)
            first._reference_lifecycle=second._reference_lifecycle=chain
            chain.execute(first,lambda case:C.registered_plate_state(case,'plate'));mutate(chain)
            with self.assertRaisesRegex(AssertionError,'Rules/source profile changed'):
                chain.execute(second,lambda case:C.registered_plate_state(case,'plate'))
            self.assertEqual(second.calls,0)

    def test_between_step_state_mutation_is_rejected(self):
        rules=_rules();chain=C.ReferenceLifecycle(('plate','plate'),('one','two'))
        first,second=(_Case(name,rules) for name in chain.steps)
        first._reference_lifecycle=second._reference_lifecycle=chain
        chain.execute(first,lambda case:C.registered_plate_state(case,'plate'))
        chain.environment[1].budget['standard']=0
        with self.assertRaisesRegex(AssertionError,'handoff changed'):
            chain.execute(second,lambda case:C.registered_plate_state(case,'plate'))
        self.assertEqual(second.calls,0)

    def test_complete_partial_and_unrelated_selections_preserve_cold_factories(self):
        rules=_rules();names=[f'test_plate_01_{mode}' for mode in ('matching','nonmatching','lifecycle')]
        partial=[_Case(names[0],rules),_Case('unrelated',rules)]
        self.assertEqual(tuple(partial),C.prepare_reference_cases(_Case,partial,(('plate',None,None),),'gift'))
        self.assertTrue(all(not hasattr(c,'_reference_lifecycle') for c in partial))
        for case in partial:C.registered_plate_state(case,'plate');C.registered_plate_state(case,'plate')
        self.assertEqual([case.calls for case in partial],[2,2])
        full=[_Case(name,rules) for name in reversed(names)];original_ids={id(c) for c in full}
        ordered=C.prepare_reference_cases(_Case,full,(('plate',None,None),),'gift')
        self.assertEqual([c._testMethodName for c in ordered],names)
        self.assertEqual({id(c) for c in ordered},original_ids)
        self.assertEqual(len({id(c._reference_lifecycle) for c in ordered}),1)

    def test_cold_gift_exhaustion_does_not_acquire_a_connected_fallback(self):
        case=_Case('unrelated',_rules());uses=[]
        C.exhausted_gift_state(case,lambda *args:uses.append(args),'gift')
        self.assertEqual((case.calls,len(uses)),(1,3))
        chain=C.ReferenceLifecycle(('gift','gift'),C.GIFT_STEPS);case._reference_lifecycle=chain
        chain.cursor=1
        with self.assertRaisesRegex(AssertionError,'missing predecessor environment'):
            C.exhausted_gift_state(case,lambda *args:uses.append(args),'gift')
        self.assertEqual((case.calls,len(uses)),(1,3))

    def test_reported_unittest_subtest_failure_blocks_descendant(self):
        rules=_rules();chain=C.ReferenceLifecycle(('plate','plate'),('one','two'))
        first,second=(_Case(name,rules) for name in chain.steps)
        result=unittest.TestResult();first._outcome=types.SimpleNamespace(result=result)
        def failed_subtest(case):result.failures.append((case,'original subtest assertion failed'))
        chain.execute(first,failed_subtest)
        self.assertEqual(chain.failed,first.id())
        with self.assertRaisesRegex(unittest.SkipTest,'blocked connected predecessor'):
            chain.execute(second,lambda case:case.fixture('plate'))
        self.assertEqual(second.calls,0)


if __name__=='__main__':unittest.main()
