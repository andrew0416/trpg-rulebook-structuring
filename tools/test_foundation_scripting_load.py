"""External operation loading: real source selection, typed contracts and no execution."""
from pathlib import Path
from copy import copy,deepcopy
from hashlib import sha256
import json,unittest
from unittest.mock import patch
from engine import Rules,Engine
from ruleset import RuleFilter,RuleSelection
import foundation_operations as OPS

ROOT=Path(__file__).resolve().parents[1]

class LoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=Rules(ROOT,ruleset='core')
    def setUp(self):
        self.r=copy(self.base);self.r.ruleset=deepcopy(self.base.ruleset)
        self.r.selection=copy(self.base.selection);self.r.selection.filter=self.r.ruleset
        source=self.r.selection.units['combat/struggle']['source']['file']
        self.document=dict(schema=1,id='external-operation-test',variants=[dict(rule_id='combat/struggle',
            source=dict(file='input/'+source,sha256=sha256((ROOT/'input'/source).read_bytes()).hexdigest()),
            inputs={},values=dict(operations=[self.step()]))])
    def step(self,**changes):
        result=dict(id='stage',operation='effects.apply',arguments=dict(actor={'$actor':'actor'},target={'$actor':'target'},
            effects=[dict(type='apply_status',status='취약',until={'event':'turn_end','owner':'target'})]))
        result.update(changes);return result
    @property
    def row(self):return self.document['variants'][0]
    def package(self):return dict(schema=1,sources=[],policies=[deepcopy(self.document)])
    def load(self,package=None):return self.r.load_source_policy_package(json.dumps(package or self.package(),ensure_ascii=False))
    def test_every_advertised_contract_names_a_real_public_native_consumer(self):
        items=OPS.catalog();self.assertEqual(len({item['operation'] for item in items}),len(items))
        for item in items:
            self.assertFalse(item['execution_certified'])
            if item['operation'] in OPS.BINDINGS:self.assertTrue(callable(getattr(Engine,OPS.BINDINGS[item['operation']][1])))
            self.assertEqual(self.r.catalog_definition(item['id']),item)
        self.assertIn('movement.forced',{item['operation'] for item in items})
        self.assertNotIn('_grant',OPS.describe('maneuvers.grapple')['arguments'])
    def test_loading_json_accepts_contracts_without_executing_and_returns_pure_plan(self):
        with patch.object(Engine,'apply_effect',side_effect=AssertionError('load executed state')):
            result=self.load()
        self.assertEqual(result[0]['status'],'PolicyValuesReady');self.assertFalse(result[0]['execution_certified'])
        self.assertFalse(result[0]['operation_plan']['source_ready'])
        self.assertEqual(self.r.source_policy_document(self.document['id']),self.document)
    def test_unknown_late_operation_rejects_whole_package_without_partial_install(self):
        package=self.package();second=deepcopy(self.document);second['id']='bad-late';second['variants'][0]['values']['operations'][0]['operation']='python.exec'
        package['policies'].append(second)
        with self.assertRaisesRegex(ValueError,'unsupported'):self.load(package)
        self.assertNotIn(self.document['id'],getattr(self.r,'_source_policy_documents',{}))
    def test_exact_argument_types_reject_bool_integer_and_unknown_arguments(self):
        for args in (dict(seconds=True),dict(seconds=1,magic=True),dict(seconds={'$input':'missing'})):
            self.row['values']['operations']=[self.step(operation='activity.clock',arguments=args)]
            with self.assertRaises(ValueError):self.load()
    def test_required_unknown_input_is_pending_then_exact_typed_value_resolves(self):
        self.row['inputs']={'seconds':dict(type='integer',authority='context',question='actual elapsed seconds',minimum=1)}
        self.row['values']['operations']=[self.step(operation='activity.clock',arguments={'seconds':{'$input':'seconds'}})]
        result=self.load();self.assertEqual(result[0]['status'],'PolicyInputsRequired');self.assertNotIn('operation_plan',result[0])
        ready=self.r.resolve_source_policy(self.document,context={'seconds':2})
        self.assertEqual(ready['status'],'PolicyValuesReady');self.assertEqual(ready['values']['operations'][0]['arguments']['seconds'],2)
        with self.assertRaises(ValueError):self.r.resolve_source_policy(self.document,context={'seconds':True})
    def test_declared_input_type_must_match_operation_argument(self):
        self.row['inputs']={'seconds':dict(type='string',authority='context',question='wrong clock type')}
        self.row['values']['operations']=[self.step(operation='activity.clock',arguments={'seconds':{'$input':'seconds'}})]
        with self.assertRaisesRegex(ValueError,'type'):self.load()
    def test_actor_bindings_are_explicit_and_actual_ids_are_not_literal_objects(self):
        self.row['values']['operations'][0]['arguments']['actor']='actor'
        with self.assertRaisesRegex(ValueError,'actor'):self.load()
        self.row['values']['operations'][0]['arguments']['actor']={'$actor':'actor'}
        self.load()
    def test_private_tokens_and_executable_objects_never_enter_declarations(self):
        for field in ('_grant','_activation','free_action'):
            self.setUp();step=self.step(operation='maneuvers.grapple',arguments=dict(actor={'$actor':'actor'},target={'$actor':'target'},**{field:True}))
            self.row['values']['operations']=[step]
            with self.assertRaises(ValueError):self.load()
        self.setUp();self.row['values']['operations'][0]['arguments']['effects'][0]['callback']=lambda:None
        with self.assertRaises((ValueError,TypeError)):self.r.load_source_policy_package(self.package())
    def test_result_references_require_prior_public_steps_and_unique_ids(self):
        for extra in (self.step(),self.step(id='second',operation='effects.heal',arguments=dict(c={'$result':'future'},amount=1)),self.step(id='second',operation='effects.heal',arguments=dict(c={'$result':'stage','path':['_secret']},amount=1))):
            self.setUp();self.row['values']['operations'].append(extra)
            with self.assertRaises(ValueError):self.load()
        self.setUp();self.row['values']['operations'].append(self.step(id='second',operation='objects.identity',arguments={'identity':{'$result':'stage','path':['entity_id']}}))
        self.load()
    def test_unsupported_lifetime_owner_kind_and_multiple_endings_fail_before_execution(self):
        for update in (dict(until={'event':'turn_end'}),dict(until={'event':'imaginary'}),dict(duration={'seconds':0}),dict(duration={'seconds':2}),dict(repeat={'event':'scene_end','times':2})):
            self.setUp();self.row['values']['operations'][0]['arguments']['effects'][0].update(update)
            with self.assertRaises(ValueError):self.load()
    def test_source_hash_version_and_typed_condition_reuse_existing_admission(self):
        self.row['inputs']={'enabled':dict(type='boolean',authority='context',question='actual rule condition')}
        self.row['when']={'$input':'enabled'}
        self.assertEqual(self.load()[0]['status'],'PolicyInputsRequired')
        self.assertEqual(self.r.resolve_source_policy(self.document,context={'enabled':False})['status'],'PolicyNotApplicable')
        self.row['source']['sha256']='0'*64
        with self.assertRaises(ValueError):self.load()
        self.setUp();self.r.ruleset=RuleFilter({'unit_versions':{'combat/struggle':'v2'}})
        self.r.selection=RuleSelection(self.r.ruleset,list(self.base.selection.units.values()))
        self.row['version']='v2'
        self.assertEqual(self.r.resolve_source_policy(self.document)['selected_version'],'v2')
        self.row['version']='v1'
        with self.assertRaises(ValueError):self.load()
    def test_operation_model_preserves_declared_order_and_selected_variant(self):
        alternate=deepcopy(self.row);alternate['version']='v2'
        alternate['values']['operations'].append(self.step(id='later',operation='activity.clock',arguments={'seconds':2}))
        self.row['values']={'description':'non-executable catalog value'}
        self.document['variants'].append(alternate)
        self.r.ruleset=RuleFilter({'unit_versions':{'combat/struggle':'v2'}})
        self.r.selection=RuleSelection(self.r.ruleset,list(self.base.selection.units.values()))
        result=self.load()[0]
        self.assertIn('operation_plan',result)
        plan=result['operation_plan']['aspects'][0]['value']
        self.assertEqual([step['id'] for step in plan],['stage','later'])
    def test_unknown_json_keys_duplicate_keys_and_catalog_mutation_do_not_install(self):
        text=json.dumps(self.package()).replace('"schema": 1','"schema": 1, "schema": 1',1)
        with self.assertRaises(ValueError):self.r.load_source_policy_package(text)
        self.assertFalse(getattr(self.r,'_source_policy_documents',{}))
        first=self.r.catalog_definition('operation/maneuvers.grapple');first['arguments'].clear()
        self.assertTrue(self.r.catalog_definition('operation/maneuvers.grapple')['arguments'])

if __name__=='__main__':unittest.main()
