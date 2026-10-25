"""Whole-TestCase publication boundaries, stdlib only; no game fixtures."""
import unittest

from chained_case_lifecycle import bind_case_lifecycle, defer_case_commit


class ChainedCaseLifecycleTests(unittest.TestCase):
    def probe(self, mode, *, result=None, direct=False, debug=False):
        world={'value':0};published=[];poison=[];cleanups=[]
        class Case(unittest.TestCase):
            def setUp(case):
                if mode=='setup':raise RuntimeError('original setup error')
                if mode=='setup-skip':raise unittest.SkipTest('original setup skip')
            def runTest(case):
                world['value']+=1
                if mode=='body':raise AssertionError('original body failure')
                if mode=='unverified':return
                defer_case_commit(case,lambda:published.append(world['value']))
                case.addCleanup(lambda:cleanups.append(list(published)))
                if mode=='late-body':raise AssertionError('original late body failure')
                if mode=='skip':raise unittest.SkipTest('original body skip')
                if mode=='xfail':raise AssertionError('original expected failure')
                if mode.startswith('subtest-'):
                    with case.subTest(boundary=mode):
                        if mode=='subtest-skip':raise unittest.SkipTest('original subtest skip')
                        if mode=='subtest-error':raise RuntimeError('original subtest error')
                        raise AssertionError('original subtest failure')
                if mode.startswith('cleanup'):
                    def cleanup():
                        if mode=='cleanup-skip':raise unittest.SkipTest('original cleanup skip')
                        raise RuntimeError('original cleanup error')
                    case.addCleanup(cleanup)
                if mode=='fatal':raise KeyboardInterrupt('original fatal exception')
                if mode=='system-exit':raise SystemExit('original SystemExit')
            def tearDown(case):
                if mode=='teardown':raise RuntimeError('original teardown error')
        if mode in ('xfail','xpass'):Case.runTest=unittest.expectedFailure(Case.runTest)
        case=Case();bind_case_lifecycle(case,poison.append)
        original_id=case.id();original_type=type(case)
        if direct:case.runTest()
        elif debug:case.debug()
        else:
            result=unittest.TestResult() if result is None else result
            self.assertIs(case.run(result),result)
        self.assertEqual(case.id(),original_id);self.assertIs(type(case),original_type)
        return world,published,poison,cleanups,result,case

    def test_success_publishes_only_after_all_cleanups_and_keeps_identity(self):
        world,published,poison,cleanups,result,_=self.probe('pass')
        self.assertEqual(world,{'value':1});self.assertEqual(published,[1])
        self.assertEqual(cleanups,[[]]);self.assertEqual(poison,[])
        self.assertTrue(result.wasSuccessful());self.assertEqual(result.testsRun,1)

    def test_unverified_outcomes_keep_actual_state_and_never_publish(self):
        modes=('setup','setup-skip','body','late-body','skip','subtest-failure','subtest-error',
               'subtest-skip','cleanup','cleanup-skip','teardown','xfail','xpass','unverified','system-exit')
        for mode in modes:
            with self.subTest(mode=mode):
                world,published,poison,_,result,_=self.probe(mode)
                self.assertEqual(published,[]);self.assertEqual(len(poison),1)
                self.assertEqual(world['value'],0 if mode.startswith('setup') else 1)
                self.assertEqual(result.testsRun,1)
                if mode=='xfail':self.assertEqual(len(result.expectedFailures),1)
                elif mode=='xpass':self.assertEqual(len(result.unexpectedSuccesses),1)
                elif mode=='unverified':self.assertTrue(result.wasSuccessful())
                else:
                    texts=[text for _,text in result.failures+result.errors+result.skipped]
                    self.assertTrue(any('original' in text for text in texts))

    def test_unrelated_prior_failure_does_not_poison_current_case(self):
        result=unittest.TestResult()
        class Prior(unittest.TestCase):
            def runTest(self):self.fail('unrelated prior failure')
        prior=Prior();prior.run(result)
        _,published,poison,_,returned,_=self.probe('pass',result=result)
        self.assertIs(returned,result);self.assertEqual(published,[1]);self.assertEqual(poison,[])
        self.assertIs(result.failures[0][0],prior);self.assertEqual(len(result.failures),1)

    def test_debug_success_commits_after_cleanup_without_result_events(self):
        world,published,poison,cleanups,_,_=self.probe('pass',debug=True)
        self.assertEqual(world['value'],1);self.assertEqual(published,[1])
        self.assertFalse(poison);self.assertEqual(cleanups,[[]])

    def test_direct_body_has_no_verified_result_and_cannot_publish(self):
        world,published,poison,_,_,_=self.probe('pass',direct=True)
        self.assertEqual(world['value'],1);self.assertEqual(published,[]);self.assertTrue(poison)

    def test_debug_failure_and_fatal_exception_are_not_hidden(self):
        for debug,mode,kind,message in ((True,'late-body',AssertionError,'original late body failure'),
                                       (False,'fatal',KeyboardInterrupt,'original fatal exception')):
            with self.subTest(mode=mode):
                poison=[];published=[];world=[]
                class Case(unittest.TestCase):
                    def runTest(case):
                        world.append('actual mutation');defer_case_commit(case,lambda:published.append(True))
                        raise kind(message)
                case=Case();bind_case_lifecycle(case,poison.append)
                with self.assertRaisesRegex(kind,message):
                    case.debug() if debug else case.run()
                self.assertEqual(world,['actual mutation']);self.assertEqual(published,[]);self.assertTrue(poison)

    def test_fatal_cleanup_does_not_publish_or_hide_the_original_exception(self):
        poison=[];published=[]
        class Case(unittest.TestCase):
            def runTest(case):
                defer_case_commit(case,lambda:published.append(True))
                def cleanup():raise KeyboardInterrupt('original cleanup interrupt')
                case.addCleanup(cleanup)
        case=Case();bind_case_lifecycle(case,poison.append)
        with self.assertRaisesRegex(KeyboardInterrupt,'original cleanup interrupt'):case.run()
        self.assertEqual(published,[]);self.assertEqual(len(poison),1)

    def test_default_result_and_reused_case_do_not_reuse_a_pending_commit(self):
        poison=[];published=[];first=[True]
        class Case(unittest.TestCase):
            def runTest(case):
                if first[0]:defer_case_commit(case,lambda:published.append(True))
        case=Case();bind_case_lifecycle(case,poison.append)
        self.assertTrue(case.run().wasSuccessful());self.assertEqual(published,[True])
        first[0]=False
        self.assertTrue(case.run().wasSuccessful());self.assertEqual(published,[True]);self.assertEqual(len(poison),1)

    def test_duplicate_binding_and_multiple_commits_fail_explicitly(self):
        case=unittest.FunctionTestCase(lambda:None);bind_case_lifecycle(case,lambda reason:None)
        with self.assertRaisesRegex(ValueError,'already has'):bind_case_lifecycle(case,lambda reason:None)
        poison=[]
        class Duplicate(unittest.TestCase):
            def runTest(case):
                defer_case_commit(case,lambda:None);defer_case_commit(case,lambda:None)
        case=Duplicate();bind_case_lifecycle(case,poison.append);result=case.run()
        self.assertEqual(len(result.failures),1);self.assertIn('multiple commits',result.failures[0][1])
        self.assertEqual(len(poison),1)

    def test_poison_callback_cannot_hide_an_active_original_exception(self):
        for phase in ('commit','stopTest','debug'):
            with self.subTest(phase=phase):
                original=RuntimeError('original '+phase);secondary=ValueError('secondary poison')
                calls=[]
                def poison(reason):calls.append(reason);raise secondary
                class Case(unittest.TestCase):
                    def runTest(case):
                        if phase=='debug':raise original
                        def commit():
                            if phase=='commit':raise original
                        defer_case_commit(case,commit)
                class Result(unittest.TestResult):
                    def stopTest(self,test):
                        super().stopTest(test)
                        if phase=='stopTest':raise original
                case=Case();bind_case_lifecycle(case,poison)
                with self.assertRaises(RuntimeError) as caught:
                    case.debug() if phase=='debug' else case.run(Result())
                self.assertIs(caught.exception,original);self.assertEqual(len(calls),1)
                self.assertIs(case._chain_case_lifecycle['poison_error'],secondary)

    def test_standalone_poison_exception_propagates_unchanged_only_once(self):
        for debug in (False,True):
            with self.subTest(debug=debug):
                errors=[]
                def poison(reason):
                    error=ValueError('poison '+str(len(errors)));errors.append(error);raise error
                case=unittest.FunctionTestCase(lambda:None);bind_case_lifecycle(case,poison)
                with self.assertRaises(ValueError) as caught:
                    case.debug() if debug else case.run()
                self.assertEqual(len(errors),1);self.assertIs(caught.exception,errors[0])

    def test_poisoned_case_cannot_later_publish_a_new_success(self):
        published=[];poison=[];mark=[False]
        class Case(unittest.TestCase):
            def runTest(case):
                if mark[0]:defer_case_commit(case,lambda:published.append(True))
        case=Case();bind_case_lifecycle(case,poison.append)
        case.run();mark[0]=True;case.run()
        self.assertEqual(published,[]);self.assertEqual(len(poison),1)

    def test_existing_59_body_meta_comparison_keeps_debug_contract_and_one_start(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from test_reference_connection_equivalence import _compare_reference_modes
        from reference_rule_connections import GIFT_STEPS,initial_gift_state,prepare_reference_cases,reference_step,registered_plate_state
        plates=tuple(('plate/'+str(index),None,None) for index in range(1,19))
        class Rules:
            ruleset=None;rulings=None
            def item_effects(self,name):return {'plate':name}
            def feat_effects(self,name):return {'gift':name}
        class Case(unittest.TestCase):
            @classmethod
            def setUpClass(cls):cls.rules=Rules()
            @classmethod
            def prepare_chained_cases(cls,cases):return prepare_reference_cases(cls,cases,plates,'gift')
            def fixture(self,item=None,feat=False):
                return SimpleNamespace(r=self.rules),SimpleNamespace(hp=20),SimpleNamespace(hp=20)
        names=[]
        for index,(plate,_,_) in enumerate(plates,1):
            for mode in ('matching','nonmatching','lifecycle'):
                name=f'test_plate_{index:02d}_{mode}';names.append(name)
                def body(case,plate=plate,mode=mode):
                    registered_plate_state(case,plate)
                    if mode!='lifecycle':case.fixture()
                    case.assertEqual(1,1)
                setattr(Case,name,reference_step(body))
        for name in GIFT_STEPS:
            names.append(name)
            def body(case):initial_gift_state(case,'gift');case.assertEqual(1,1)
            setattr(Case,name,reference_step(body))
        class Meta(unittest.TestCase):
            def runTest(case):
                self.assertEqual(_compare_reference_modes(Case,names),{
                    'cold':{'main':59,'original_plain_comparator':36},
                    'connected':{'main':19,'original_plain_comparator':36}})
        result=unittest.TestResult()
        original_start=unittest.TestResult.startTest
        with patch.object(unittest.TestResult,'startTest',autospec=True,side_effect=original_start) as starts:
            Meta().run(result)
        self.assertTrue(result.wasSuccessful(),result.errors+result.failures)
        self.assertEqual(result.testsRun,1);self.assertEqual(starts.call_count,1)


if __name__=='__main__':unittest.main()
