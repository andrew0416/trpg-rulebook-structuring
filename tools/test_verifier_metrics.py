"""Stdlib dummy checks for additive process-CPU/environment verifier fields."""
from pathlib import Path
from unittest.mock import patch
import importlib.util,io,json,subprocess,sys,tempfile,unittest
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
RUNNER=ROOT/'work/reuse-partials/verify_overlay_tests.py'


class VerifierMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='verifier-metrics-',dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.stage=self.root/'stage';self.canonical=self.root/'canonical'
        self.stage.mkdir();(self.canonical/'tools').mkdir(parents=True)
        (self.canonical/'tools/__init__.py').write_text('',encoding='utf-8')

    def write(self,source):
        path=self.stage/'tools/test_metrics_dummy.py';path.parent.mkdir(exist_ok=True)
        path.write_text(source,encoding='utf-8')

    def run_cli(self,*args):
        report=self.root/'report.json'
        result=subprocess.run([sys.executable,'-B','-X','utf8',str(RUNNER),
            '--stage',str(self.stage),'--canonical',str(self.canonical),'--report',str(report),
            *map(str,args)],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertTrue(report.exists(),result.stdout+result.stderr)
        return result,json.loads(report.read_text(encoding='utf-8'))

    def load_runner(self):
        spec=importlib.util.spec_from_file_location('_verifier_metrics_owner',RUNNER)
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        return runner

    def test_process_cpu_addition_preserves_exact_wall_difference(self):
        runner=self.load_runner()
        result=runner.ReportingResult(unittest.runner._WritelnDecorator(io.StringIO()),True,0)
        case=unittest.FunctionTestCase(lambda:None)
        with patch.object(runner.time,'perf_counter',side_effect=[10.0,12.5]), \
             patch.object(runner.time,'process_time',side_effect=[20.0,20.75]):
            result.startTest(case);result.addSuccess(case);result.stopTest(case)
        self.assertEqual(result.test_durations,[{'id':case.id(),'seconds':2.5,'process_cpu_seconds':.75}])
        self.assertEqual(result.testsRun,1);self.assertTrue(result.wasSuccessful())

    def test_runtime_fields_keep_failure_retry_and_exact_selection(self):
        self.write('import unittest\nclass Tests(unittest.TestCase):\n'
                   ' def test_pass(self):pass\n def test_fail(self):self.fail("original failure")\n')
        result,data=self.run_cli('tools.test_metrics_dummy')
        self.assertEqual(result.returncode,1,result.stdout+result.stderr)
        expected=['tools.test_metrics_dummy.Tests.test_fail','tools.test_metrics_dummy.Tests.test_pass']
        self.assertEqual(data['selected_case_ids'],expected);self.assertEqual(data['collected'],expected)
        self.assertEqual(data['chained_cases'],[]);self.assertEqual(data['retry_ids'],expected[:1])
        self.assertFalse(data['successful'])
        environment=data['runtime_environment']
        self.assertEqual(set(environment),{'python_version','python_executable','platform','cpu_clock'})
        self.assertEqual(environment['python_version'],sys.version)
        self.assertEqual(environment['python_executable'],sys.executable)
        self.assertTrue(environment['platform']);self.assertEqual(environment['cpu_clock'],'time.process_time')
        self.assertEqual([row['id'] for row in data['test_durations']],expected)
        self.assertTrue(all(row['process_cpu_seconds']>=0 for row in data['test_durations']))
        self.assertGreaterEqual(data['suite_process_cpu_seconds']+1e-9,sum(row['process_cpu_seconds'] for row in data['test_durations']))

    def test_collection_has_environment_but_no_fabricated_execution_cpu(self):
        self.write('import unittest\nclass Tests(unittest.TestCase):\n'
                   ' def test_a(self):raise AssertionError("must not run")\n')
        result,data=self.run_cli('tools.test_metrics_dummy','--collect-only')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(data['kind'],'collection');self.assertEqual(data['tests_run'],0)
        self.assertTrue(data['runtime_environment']['python_version'])
        self.assertNotIn('suite_process_cpu_seconds',data);self.assertNotIn('test_durations',data)

    def test_class_fixture_failure_has_suite_cpu_but_no_fake_method_timings(self):
        self.write('import unittest\nclass Tests(unittest.TestCase):\n'
                   ' @classmethod\n def setUpClass(cls):raise RuntimeError("original fixture error")\n'
                   ' def test_a(self):pass\n def test_b(self):pass\n')
        result,data=self.run_cli('tools.test_metrics_dummy')
        self.assertEqual(result.returncode,1,result.stdout+result.stderr)
        self.assertEqual(data['tests_run'],0);self.assertEqual(data['test_durations'],[])
        self.assertGreaterEqual(data['suite_process_cpu_seconds'],0)
        self.assertEqual(data['retry_ids'],data['collected'])
        self.assertIn('original fixture error',data['errors'][0]['traceback'])

    def test_required_skip_remains_unverified_and_retryable(self):
        self.write('import unittest\nclass Tests(unittest.TestCase):\n'
                   ' @unittest.skip("original skip")\n def test_a(self):pass\n')
        packet=self.stage/'packet.json'
        packet.write_text(json.dumps({'completed':{'dummy':{'tests':['tools.test_metrics_dummy.Tests.test_a']}}}),encoding='utf-8')
        result,data=self.run_cli('--candidate',packet)
        self.assertEqual(result.returncode,1,result.stdout+result.stderr)
        self.assertFalse(data['successful']);self.assertEqual(data['retry_ids'],data['collected'])
        self.assertEqual(data['skipped'][0]['reason'],'original skip')
        self.assertGreaterEqual(data['test_durations'][0]['process_cpu_seconds'],0)

    def test_c89_chaining_keeps_selected_ids_and_execution_order(self):
        self.write('import unittest\nclass Tests(unittest.TestCase):\n'
                   ' @classmethod\n def prepare_chained_cases(cls,cases):return reversed(cases)\n'
                   ' def test_a(self):pass\n def test_b(self):pass\n')
        result,data=self.run_cli('tools.test_metrics_dummy')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        expected=['tools.test_metrics_dummy.Tests.test_a','tools.test_metrics_dummy.Tests.test_b']
        self.assertEqual(data['selected_case_ids'],expected)
        self.assertEqual(data['collected'],list(reversed(expected)))
        self.assertEqual([row['id'] for row in data['test_durations']],data['collected'])
        self.assertEqual(data['chained_cases'][0]['selected_test_ids'],expected)
        self.assertEqual(data['chained_cases'][0]['execution_test_ids'],data['collected'])

    def test_subtest_failure_and_cleanup_still_use_original_result_contract(self):
        events=[]
        class Dummy(unittest.TestCase):
            def setUp(self):self.addCleanup(events.append,'cleanup')
            def runTest(self):
                events.append('body')
                with self.subTest(value=1):self.assertEqual(1,2)
        runner=self.load_runner();case=Dummy()
        result=unittest.TextTestRunner(stream=io.StringIO(),resultclass=runner.ReportingResult).run(unittest.TestSuite([case]))
        self.assertFalse(result.wasSuccessful());self.assertEqual(result.testsRun,1)
        self.assertEqual(events,['body','cleanup']);self.assertEqual(len(result.failures),1)
        self.assertEqual(runner.retry_ids(result,[case.id()]),[case.id()])
        self.assertEqual(result.test_durations[0]['id'],case.id())
        self.assertGreaterEqual(result.test_durations[0]['process_cpu_seconds'],0)


    def run_physical_cli(self, *extra_inputs):
        (self.stage/'tools/__init__.py').write_text('',encoding='utf-8')
        inputs=self.stage/'physical-inputs.json'
        inputs.write_text(json.dumps({'version':1,'inputs':['tools',*map(str,extra_inputs)]}),encoding='utf-8')
        records=self.stage/'records'
        result=subprocess.run([sys.executable,'-B','-X','utf8',str(RUNNER),
            '--stage',str(self.stage),'--canonical',str(self.stage),'tools.test_metrics_dummy',
            '--physical',str(inputs),'--record',str(records)],
            capture_output=True,text=True,encoding='utf-8',timeout=30)
        metadata=list(records.glob('physical-*/physical.json'))
        self.assertEqual(len(metadata),1,result.stdout+result.stderr)
        physical=json.loads(metadata[0].read_text(encoding='utf-8'))
        native=json.loads((self.stage/physical['current_cli_report']).read_text(encoding='utf-8'))
        return result,physical,native

    def test_native_platform_covers_windows_unix_and_absent_api_fallback(self):
        runner=self.load_runner()
        scenarios=(
            (SimpleNamespace(getwindowsversion=lambda:(10,0,19045),platform='win32'),SimpleNamespace(),'Windows-10.0.19045'),
            (SimpleNamespace(platform='linux'),SimpleNamespace(uname=lambda:SimpleNamespace(sysname='Linux',release='6.1',machine='aarch64')),'Linux-6.1-aarch64'),
            (SimpleNamespace(platform='fallback-os'),SimpleNamespace(),'fallback-os'),
        )
        for system,os_api,expected in scenarios:
            with self.subTest(expected=expected),patch.object(runner,'sys',system),patch.object(runner,'os',os_api):
                self.assertEqual(runner.native_platform(),expected)

    def test_native_platform_does_not_launch_subprocess(self):
        runner=self.load_runner()
        with patch('subprocess.Popen',side_effect=AssertionError('metadata launched a subprocess')):
            self.assertTrue(runner.native_platform())

    def test_physical_metadata_capture_preserves_native_pass(self):
        self.write('import unittest\nclass Tests(unittest.TestCase):\n def test_pass(self):self.assertEqual(2+2,4)\n')
        result,physical,native=self.run_physical_cli()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(native['successful']);self.assertEqual(native['tests_run'],1)
        self.assertTrue(physical['successful']);self.assertTrue(physical['stable_hashes'])
        self.assertTrue(physical['complete_pre_input_capture']);self.assertTrue(physical['complete_loaded_input_capture'])
        self.assertEqual(physical['capture_errors'],[]);self.assertEqual(physical['changed_origin_errors'],[])
        self.assertEqual(set(native['runtime_environment']),{'python_version','python_executable','platform','cpu_clock'})
        self.assertTrue(native['runtime_environment']['platform'])

    def test_actual_unresolved_descriptor_read_still_fails_physical_capture(self):
        fixture=self.stage/'declared-input.txt';fixture.write_text('observed input',encoding='utf-8')
        self.write('import unittest,os\nclass Tests(unittest.TestCase):\n def test_fd(self):\n'
            '  with os.fdopen(os.open('+repr(str(fixture))+',os.O_RDONLY),"r",encoding="utf-8") as stream:\n'
            '   self.assertEqual(stream.read(),"observed input")\n')
        result,physical,native=self.run_physical_cli(fixture)
        self.assertEqual(result.returncode,1,result.stdout+result.stderr)
        self.assertTrue(native['successful']);self.assertEqual(native['tests_run'],1)
        self.assertFalse(physical['successful']);self.assertTrue(physical['stable_hashes'])
        self.assertTrue(physical['complete_pre_input_capture']);self.assertTrue(physical['complete_loaded_input_capture'])
        self.assertEqual(physical['changed_origin_errors'],[])
        self.assertTrue(physical['capture_errors'])
        self.assertTrue(all(error.startswith('unresolved file-descriptor read: ') for error in physical['capture_errors']))


if __name__=='__main__':unittest.main()
