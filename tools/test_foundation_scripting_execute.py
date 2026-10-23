"""Original foundation57: external JSON programs execute existing native owners."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,unittest
from engine import Rules,Engine,Combatant
from builder import build_trainer
from rulings import Rulings
from ruleset import RuleFilter,RuleSelection
from grid import Grid
from state_codec import dump_engine,load_engine
from source_policy import PolicyExecutionPending
import effects as FX,forced_movement as FORCED

ROOT=Path(__file__).resolve().parents[1]

class ExecuteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=Rules(ROOT,ruleset='core')
    def setUp(self):
        self.r=copy(self.base);self.r.ruleset=RuleFilter({'sources':['core','custom'],'variants':[]})
        self.r.selection=RuleSelection(self.r.ruleset,list(self.base.selection.units.values()))
        self.r.rulings=Rulings()
        for name in ('repulse','recovery'):
            self.r.load_source_policy_package((ROOT/('data/examples/scripting-'+name+'.json')).read_text(encoding='utf8'))
        self.e=Engine(self.r,31);self.e.grid=Grid(12,8)
        self.a,self.b=(Combatant(self.r,build_trainer(self.r,name,10,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),abilities=[])) for name in ('author','recipient'))
        self.a.pos=(1,1);self.b.pos=(2,1)
        self.e.everyone=self.e.gm.everyone=[self.a,self.b]
        self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a)
        self.repulse=self.r.source_policy_document('external/repulse')
        self.recovery=self.r.source_policy_document('external/recovery')
    def run_program(self,doc=None,request='external/one',**options):
        return self.e.execute_source_policy_operations(self.a,self.b,doc or self.repulse,request_id=request,**options)
    def repulse_run(self,**options):return self.run_program(context={'distance':2},**options)
    def recovery_run(self,**options):
        return self.run_program(self.recovery,context={'seconds':3},
            decisions={'healing':{'value':4,'reason':'explicit authored recovery value'}},**options)
    def step(self,identity,operation,**arguments):return dict(id=identity,operation=operation,arguments=arguments)
    def program(self,steps,identity='external/test'):
        doc=deepcopy(self.repulse);doc['id']=identity
        row=doc['variants'][0];row['inputs']={};row['values']={'operations':steps}
        return doc
    def test_two_external_files_execute_different_native_owners_without_engine_edits(self):
        first=self.repulse_run()
        self.assertEqual(first['status'],'PolicyOperationsCompleted')
        self.assertEqual(self.a.budget['swift'],0);self.assertEqual(self.a.spec['ap_spent'],1)
        self.assertIn('취약',self.b.conditions);self.assertEqual(self.b.pos,(4,1))
        self.assertEqual(first['selected_id'],'authored/example-repulse')
        self.assertEqual(first['operation_results'][1]['result']['moved'],2)
        self.b.hp-=6;before=self.b.hp;clock=self.e.elapsed_seconds
        second=self.recovery_run(request='external/two')
        self.assertEqual(self.b.hp,before+4);self.assertEqual(self.e.elapsed_seconds,clock+3)
        self.assertEqual(second['selected_id'],'authored/example-recovery')
        self.assertNotEqual(first['definition_hash'],second['definition_hash'])
        self.assertTrue(first['operations_executed']);self.assertFalse(first['operation_plan']['source_ready'])
        self.assertTrue(first['trace']['source_reads'])
        self.assertTrue(any(row['resource']=='budget' for row in first['trace']['resource_changes']))
    def test_unknown_required_gm_input_and_false_condition_do_not_mutate_or_reserve(self):
        before=dump_engine(self.e)
        pending=self.run_program(self.recovery,context={'seconds':3})
        self.assertEqual(pending['status'],'PolicyInputsRequired');self.assertEqual(dump_engine(self.e),before)
        self.recovery_run()
        doc=deepcopy(self.repulse);doc['variants'][0]['when']={'op':'eq','left':1,'right':2}
        before=dump_engine(self.e);result=self.run_program(doc,request='false',context={'distance':2})
        self.assertEqual(result['status'],'PolicyNotApplicable');self.assertEqual(dump_engine(self.e),before)
    def test_request_redelivery_has_no_new_cost_rng_displacement_or_live_token(self):
        first=self.repulse_run();before=dump_engine(self.e);second=self.repulse_run()
        self.assertTrue(second['replayed']);self.assertEqual(second['execution_id'],first['execution_id'])
        self.assertEqual(dump_engine(self.e),before);self.assertNotIn('receipt',second['operation_results'][0]['result'])
        second['operation_results'].clear();self.assertTrue(self.repulse_run()['operation_results'])
        with self.assertRaises(ValueError):self.run_program(context={'distance':3})
        self.assertEqual(dump_engine(self.e),before)
    def test_late_failure_rolls_back_native_action_lifetime_rng_position_and_records(self):
        before=dump_engine(self.e);original=FORCED.displace
        def fail(engine,actor,target,**args):
            result=original(engine,actor,target,**args);engine.rng.random()
            raise RuntimeError('late native failure')
        with patch.object(FORCED,'displace',fail):
            with self.assertRaisesRegex(RuntimeError,'late native'):self.repulse_run()
        self.assertEqual(dump_engine(self.e),before);self.repulse_run()
    def test_native_pending_result_rolls_back_prior_costs_and_effects(self):
        steps=deepcopy(self.repulse['variants'][0]['values']['operations'])
        steps.append(self.step('later','effects.heal',c={'$actor':'target'},amount=1))
        doc=deepcopy(self.repulse);doc['variants'][0]['values']['operations']=steps
        before=dump_engine(self.e)
        with patch.object(Engine,'heal',return_value={'status':'PolicyQualificationPending','obligations':['unknown native input']}):
            with self.assertRaises(PolicyExecutionPending):self.run_program(doc,context={'distance':2})
        self.assertEqual(dump_engine(self.e),before)
    def test_prior_actual_result_drives_later_operation(self):
        self.b.hp-=5;before=self.b.hp
        doc=deepcopy(self.repulse)
        doc['variants'][0]['values']['operations'].append(self.step('heal-distance','effects.heal',
            c={'$actor':'target'},amount={'$result':'push','path':['moved']}))
        result=self.run_program(doc,context={'distance':2})
        self.assertEqual(self.b.hp,before+2);self.assertEqual(len(result['operation_results']),3)
    def test_invalid_result_path_and_actor_reference_rollback_previous_steps(self):
        for extra in (self.step('bad','effects.heal',c={'$actor':'invented'},amount=1),
                      self.step('bad','effects.heal',c={'$actor':'target'},amount={'$result':'push','path':['imaginary']})):
            doc=deepcopy(self.repulse);doc['variants'][0]['values']['operations'].append(extra)
            before=dump_engine(self.e)
            with self.assertRaises((ValueError,KeyError)):self.run_program(doc,context={'distance':2})
            self.assertEqual(dump_engine(self.e),before)
    def test_prior_native_result_can_supply_an_effect_value(self):
        doc=deepcopy(self.repulse)
        doc['variants'][0]['values']['operations'].append(self.step('effect-from-distance','effects.apply',
            actor={'$actor':'actor'},target={'$actor':'target'},effects=[{'type':'stage_change','stat':'atk',
            'delta':{'$result':'push','path':['moved']},'target':'self'}]))
        result=self.run_program(doc,context={'distance':2})
        self.assertEqual(self.a.stages['atk'],2)
        self.assertEqual(result['operation_results'][-1]['result'][0]['status'],'completed')
    def test_caller_sheet_copy_is_not_actual_target_and_id_binding_selects_live_actor(self):
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'actual'):
            self.e.execute_source_policy_operations(self.a,deepcopy(self.b),self.repulse,context={'distance':2})
        self.assertEqual(dump_engine(self.e),before)
        self.b.hp-=3;before=self.b.hp
        doc=self.program([self.step('heal','effects.heal',c={'$actor':self.b.entity_id},amount=2)])
        self.run_program(doc);self.assertEqual(self.b.hp,before+2)
    def test_producing_source_cannot_be_replaced_independently_of_selected_policy(self):
        self.repulse['variants'][0]['values']['operations'][1]['arguments']['source']='combat/struggle'
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'producing source'):self.repulse_run()
        self.assertEqual(dump_engine(self.e),before)
    def test_native_attack_miss_keeps_real_observations_without_fabricating_hit(self):
        self.e.enable_execution_trace()
        listener=deepcopy(self.repulse);listener['id']='external/observe-actual-hit'
        row=listener['variants'][0]
        row['inputs']={'hit':{'type':'boolean','authority':'context','question':'actual native hit'}}
        row['when']={'$input':'hit'}
        row['values']={'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}
        self.e.subscribe_source_policy(self.a,'actual-hit-listener',listener,inputs={'hit':'hit'})
        doc=self.program([self.step('attack','combat.hit',attacker={'$actor':'actor'},target={'$actor':'target'},move_id='struggle',set_damage=True)])
        before=self.b.hp;result=self.run_program(doc)
        self.assertEqual(self.b.hp,before);self.assertEqual(self.a.budget['standard'],0)
        event=list(self.e._passive_events.values())[-1]
        observations=self.e.event_trace(event['id'])['observations']
        self.assertTrue(any(row['stage']=='accuracy' for row in observations))
        self.assertFalse(any(row['stage']=='hp_loss' for row in observations))
        self.assertEqual(result['operation_results'][0]['state'],'returned')
        self.assertTrue(self.e.execution_traces())
    def test_callback_is_rejected_before_first_native_mutation(self):
        before=dump_engine(self.e)
        self.e.rulings.provider=lambda *args,**kwargs:None
        try:
            with self.assertRaisesRegex(ValueError,'callbacks'):self.repulse_run()
        finally:self.e.rulings.provider=None
        self.assertEqual(dump_engine(self.e),before)
    def test_json_and_gm_restore_preserve_remaining_lifetime_and_request_history(self):
        first=self.repulse_run();saved=json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False))
        loaded=load_engine(self.r,saved);a,b=loaded.everyone
        before=dump_engine(loaded)
        replay=loaded.execute_source_policy_operations(a,b,self.repulse,request_id='external/one',context={'distance':2})
        self.assertTrue(replay['replayed']);self.assertEqual(dump_engine(loaded),before)
        loaded.end_of_turn(a);loaded.start_of_turn(b);loaded.end_of_turn(b);self.assertNotIn('취약',b.conditions)
        self.e.gm.snapshot('program');self.e.end_of_turn(self.a);self.e.start_of_turn(self.b);self.e.end_of_turn(self.b)
        self.assertNotIn('취약',self.b.conditions)
        self.e.gm.restore('program',reason='restore actual external program')
        a,b=self.e.everyone
        self.assertIn('취약',b.conditions)
        self.assertEqual(self.e.source_policy_execution(first['execution_id'])['operation_results'],first['operation_results'])
    def test_no_request_legacy_call_returns_only_durable_observations(self):
        result=self.run_program(request=None,context={'distance':2})
        json.dumps(result,ensure_ascii=False)
        self.assertEqual(result['status'],'PolicyOperationsCompleted')
        self.assertNotIn('receipt',result['operation_results'][0]['result'])

if __name__=='__main__':unittest.main()

