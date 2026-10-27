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
            if rules is not None:self.rulings=rules.rulings
            self.rng=random.Random(19);self.elapsed_seconds=0
            self._heavy_native_types=(Engine,Rules,Actor)
            self.items={'plate':1};self.events=[];self._scene_observer=None
        @_traced
        def action(self,target,amount=1):return target.hp-amount
        @staticmethod
        def source(options={'selected':True}):return options
        @classmethod
        def restore(cls,options={'accepted':True}):return options
        def end_scene(self,combatants):
            self.events.append('native scene end')
            self.rulings.log.append(dict(kind='end_scene',what='scene',before=None,after=None,reason='',scope='scene'))
            if self._scene_observer:self._scene_observer()
            return len(combatants)
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
    rules.rulings.log=[{'kind':'existing campaign observation'}]
    return rules


def _Case(name,rules):
    case=unittest.FunctionTestCase(lambda:None)
    case._testMethodName=name;case.rules=rules;case.calls=0
    case.id=lambda:'synthetic.reference.'+case._testMethodName
    def fixture(item=None,feat=False):
        case.calls+=1
        engine,actor=_environment(case.rules);target=type(actor)();engine.everyone.append(target)
        return engine,actor,target
    case.fixture=fixture
    return case


def _execute(chain,case,body):
    """Keep the original guard assertions inside a real complete TestCase."""
    errors=[];values=[]
    def run_body():
        try:values.append(chain.execute(case,body))
        except BaseException as error:errors.append(error);raise
    setattr(case,case._testMethodName,run_body)
    if not hasattr(case,'_chain_case_lifecycle'):
        C.bind_case_lifecycle(case,lambda reason:setattr(chain,'failed',chain.failed or case.id()))
    result=getattr(getattr(case,'_outcome',None),'result',None) or unittest.TestResult()
    case.run(result)
    if errors:raise errors[0]
    return values[0] if values else None


def _gift_chain():
    rules=_rules()
    cases=[_Case(name,rules) for name in C.GIFT_STEPS]
    cases=list(C.prepare_reference_cases(type(cases[0]),cases,(),'gift'))
    chain=cases[0]._reference_lifecycle
    for case in cases[:2]:_execute(chain,case,lambda test:C.initial_gift_state(test,'gift'))
    return chain,cases


class ReferenceLifecycleStateTests(unittest.TestCase):
    def test_observed_gift_scene_end_preserves_exact_profile_and_world_handoff(self):
        chain,cases=_gift_chain();engine,actor,target=chain.environment;before=chain.profile
        result=_execute(chain,cases[2],lambda test:C.end_gift_scene(test,engine,[actor,target]))
        self.assertEqual(result,2);self.assertEqual(engine.events,['native scene end'])
        self.assertNotEqual(before,chain.profile);self.assertEqual(chain.profile,chain.source_profile(cases[2]))
        self.assertEqual(chain.cursor,3);self.assertIsNone(chain.failed)
        _execute(chain,cases[3],lambda test:C.exhausted_gift_state(test,lambda *args:None,'gift'))
        self.assertEqual([case.calls for case in cases],[1,0,0,0,0])

    def test_unobserved_scene_transition_and_log_edits_cannot_be_laundered(self):
        for mode in ('unobserved native','forged append','prefix edit'):
            with self.subTest(mode=mode):
                chain,cases=_gift_chain();engine,actor,target=chain.environment
                def body(test):
                    if mode=='unobserved native':engine.end_scene([actor,target])
                    elif mode=='forged append':
                        test.rules.rulings.log.append(dict(kind='end_scene',what='scene',before=None,after=None,reason='',scope='scene'))
                    else:test.rules.rulings.log[0]['kind']='forged prefix'
                    C.end_gift_scene(test,engine,[actor,target])
                with self.assertRaisesRegex(AssertionError,'Rules/source profile changed'):_execute(chain,cases[2],body)
                self.assertEqual(chain.cursor,2);self.assertEqual(chain.failed,cases[2].id())

    def test_observed_scene_end_rejects_every_other_source_profile_drift(self):
        mutations=(
            lambda rules:rules.rulings.log.append({'kind':'extra arbitrary observation'}),
            lambda rules:rules.rulings.log.append(deepcopy(rules.rulings.log[-1])),
            lambda rules:rules.rulings.log[0].update(kind='changed prefix'),
            lambda rules:rules.rulings.log[-1].update(reason='forged end reason'),
            lambda rules:rules.rulings.answers.append({'answer':True}),
            lambda rules:rules.rulings.hooks['before_damage'].append({'fn':lambda:None}),
            lambda rules:rules.ruleset.alias_conflicts.update(x=['a','b']),
            lambda rules:rules.declaration['effect'].update(bonus=6),
            lambda rules:setattr(rules,'rulings',deepcopy(rules.rulings)),
            lambda rules:setattr(rules,'ruleset',deepcopy(rules.ruleset)))
        for index,mutate in enumerate(mutations):
            with self.subTest(index=index):
                chain,cases=_gift_chain();engine,actor,target=chain.environment
                def body(test):
                    engine._scene_observer=lambda:mutate(test.rules)
                    try:C.end_gift_scene(test,engine,[actor,target])
                    finally:engine._scene_observer=None
                with self.assertRaisesRegex(AssertionError,'changed more than its native log entry'):
                    _execute(chain,cases[2],body)
                self.assertEqual(chain.cursor,2);self.assertEqual(chain.failed,cases[2].id())

    def test_gift_scene_observer_rejects_wrong_stage_engine_and_participants(self):
        chain,cases=_gift_chain();engine,actor,target=chain.environment
        for case,observed,actors in ((cases[1],engine,[actor,target]),
                                    (cases[2],_environment(cases[2].rules)[0],[actor,target]),
                                    (cases[2],engine,[target,actor])):
            with self.subTest(case=case.id(),foreign=observed is not engine):
                with self.assertRaisesRegex(AssertionError,'Gift scene transition differs'):
                    C.end_gift_scene(case,observed,actors)
        self.assertEqual(engine.events,[]);self.assertEqual(chain.cursor,2)

    def test_cold_gift_scene_end_keeps_original_public_entrypoint(self):
        case=_Case('independent O_A',_rules());engine,actor,target=case.fixture(feat=True)
        self.assertEqual(C.end_gift_scene(case,engine,[actor,target]),2)
        self.assertEqual(engine.events,['native scene end']);self.assertEqual(case.calls,1)

    def test_failed_cleanup_does_not_commit_observed_scene_transition(self):
        chain,cases=_gift_chain();engine,actor,target=chain.environment
        def body(test):
            def fail():raise RuntimeError('original cleanup failed')
            test.addCleanup(fail)
            C.end_gift_scene(test,engine,[actor,target])
        _execute(chain,cases[2],body)
        self.assertEqual(chain.cursor,2);self.assertEqual(chain.failed,cases[2].id())
        with self.assertRaisesRegex(unittest.SkipTest,'blocked connected predecessor'):
            _execute(chain,cases[3],lambda test:C.exhausted_gift_state(test,lambda *args:None,'gift'))
        self.assertEqual(cases[3].calls,0)

    def test_gift_scene_transition_is_once_only_even_inside_the_same_body(self):
        chain,cases=_gift_chain();engine,actor,target=chain.environment;before=len(engine.rulings.log)
        def body(test):
            C.end_gift_scene(test,engine,[actor,target])
            C.end_gift_scene(test,engine,[actor,target])
        with self.assertRaisesRegex(AssertionError,'Gift scene transition differs'):
            _execute(chain,cases[2],body)
        self.assertEqual(engine.events,['native scene end']);self.assertEqual(len(engine.rulings.log),before+1)
        self.assertEqual(chain.cursor,2);self.assertEqual(chain.failed,cases[2].id())
        with self.assertRaisesRegex(unittest.SkipTest,'blocked connected predecessor'):
            _execute(chain,cases[3],lambda test:self.fail('dependent body ran'))

    def test_gift_scene_rejects_temporary_native_entrypoint_substitution(self):
        for owner in ('instance','class'):
            with self.subTest(owner=owner):
                chain,cases=_gift_chain();engine,actor,target=chain.environment;before=deepcopy(engine.rulings.log)
                def body(test):
                    def fake(*args):
                        engine.rulings.log.append(dict(kind='end_scene',what='scene',before=None,after=None,reason='',scope='scene'))
                    target_owner=engine if owner=='instance' else type(engine)
                    original=vars(target_owner).get('end_scene')
                    setattr(target_owner,'end_scene',fake)
                    try:C.end_gift_scene(test,engine,[actor,target])
                    finally:
                        if original is None:delattr(target_owner,'end_scene')
                        else:setattr(target_owner,'end_scene',original)
                with self.assertRaisesRegex(AssertionError,'native scene entrypoint changed'):
                    _execute(chain,cases[2],body)
                self.assertEqual(engine.events,[]);self.assertEqual(engine.rulings.log,before)
                self.assertEqual(chain.cursor,2);self.assertEqual(chain.failed,cases[2].id())

    def test_gift_scene_rejects_foreign_case_even_with_same_rules_name_and_chain(self):
        for mode in ('observer','execute'):
            with self.subTest(mode=mode):
                chain,cases=_gift_chain();engine,actor,target=chain.environment
                foreign=_Case(C.GIFT_STEPS[2],cases[2].rules);foreign._reference_lifecycle=chain
                body=lambda test:C.end_gift_scene(foreign,engine,[actor,target])
                with self.assertRaisesRegex(AssertionError,'Gift scene transition differs' if mode=='observer' else 'order differs'):
                    _execute(chain,cases[2] if mode=='observer' else foreign,body)
                self.assertEqual(engine.events,[]);self.assertEqual(chain.cursor,2)

    def test_gift_scene_rejects_calls_outside_the_active_case_body(self):
        chain,cases=_gift_chain();engine,actor,target=chain.environment
        with self.assertRaisesRegex(AssertionError,'Gift scene transition differs'):
            C.end_gift_scene(cases[2],engine,[actor,target])
        self.assertEqual(engine.events,[]);self.assertEqual(chain.cursor,2)

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
        _execute(chain,first,body);_execute(chain,second,body)
        self.assertIs(seen[0],seen[1]);self.assertEqual((first.calls,second.calls),(1,0))
        self.assertEqual(chain.cursor,2);self.assertIsNone(chain.failed)

    def test_real_predecessor_failure_blocks_without_builder_fallback(self):
        rules=_rules();chain=C.ReferenceLifecycle(('plate','plate'),('one','two'))
        first,second=(_Case(name,rules) for name in chain.steps)
        def fail(case):raise AssertionError('original assertion failed')
        with self.assertRaisesRegex(AssertionError,'original assertion failed'):_execute(chain,first,fail)
        with self.assertRaisesRegex(unittest.SkipTest,'blocked connected predecessor'):
            _execute(chain,second,lambda case:case.fixture('plate'))
        self.assertEqual((first.calls,second.calls,chain.cursor),(0,0,0))

    def test_source_rules_identity_and_policy_mutation_block_descendants(self):
        for mutate in (lambda c:setattr(c.environment[0],'r',_rules()),
                       lambda c:c.environment[0].r.declaration['effect'].update(bonus=6),
                       lambda c:c.environment[0].r.ruleset.alias_conflicts.update(x=['a','b'])):
            rules=_rules();chain=C.ReferenceLifecycle(('plate','plate'),('one','two'))
            first,second=(_Case(name,rules) for name in chain.steps)
            first._reference_lifecycle=second._reference_lifecycle=chain
            _execute(chain,first,lambda case:C.registered_plate_state(case,'plate'));mutate(chain)
            with self.assertRaisesRegex(AssertionError,'Rules/source profile changed'):
                _execute(chain,second,lambda case:C.registered_plate_state(case,'plate'))
            self.assertEqual(second.calls,0)

    def test_between_step_state_mutation_is_rejected(self):
        rules=_rules();chain=C.ReferenceLifecycle(('plate','plate'),('one','two'))
        first,second=(_Case(name,rules) for name in chain.steps)
        first._reference_lifecycle=second._reference_lifecycle=chain
        _execute(chain,first,lambda case:C.registered_plate_state(case,'plate'))
        chain.environment[1].budget['standard']=0
        with self.assertRaisesRegex(AssertionError,'handoff changed'):
            _execute(chain,second,lambda case:C.registered_plate_state(case,'plate'))
        self.assertEqual(second.calls,0)

    def test_complete_partial_and_unrelated_selections_preserve_cold_factories(self):
        rules=_rules();names=[f'test_plate_01_{mode}' for mode in ('matching','nonmatching','lifecycle')]
        partial=[_Case(names[0],rules),_Case('unrelated',rules)]
        self.assertEqual(tuple(partial),C.prepare_reference_cases(type(partial[0]),partial,(('plate',None,None),),'gift'))
        self.assertTrue(all(not hasattr(c,'_reference_lifecycle') for c in partial))
        for case in partial:C.registered_plate_state(case,'plate');C.registered_plate_state(case,'plate')
        self.assertEqual([case.calls for case in partial],[2,2])
        full=[_Case(name,rules) for name in reversed(names)];original_ids={id(c) for c in full}
        ordered=C.prepare_reference_cases(type(full[0]),full,(('plate',None,None),),'gift')
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
        _execute(chain,first,failed_subtest)
        self.assertEqual(chain.failed,first.id())
        with self.assertRaisesRegex(unittest.SkipTest,'blocked connected predecessor'):
            _execute(chain,second,lambda case:case.fixture('plate'))
        self.assertEqual(second.calls,0)


if __name__=='__main__':unittest.main()
