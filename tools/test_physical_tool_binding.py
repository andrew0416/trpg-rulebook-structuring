"""Real tool admission for authored native programs, not class-rule certification."""
from pathlib import Path
from copy import deepcopy
import json,unittest
from unittest.mock import patch
import test_foundation_scripting_execute as FIX
from engine import Engine
from state_codec import dump_engine,load_engine
import world_entities as W
import combat_timing as TIMING


class ToolBindingTests(unittest.TestCase):
    setUpClass=classmethod(FIX.ExecuteTests.setUpClass.__func__)
    setUp=FIX.ExecuteTests.setUp

    def tool(self,uid='tool',rule='item/카메라-키트'):
        W.register_object(self.e,uid,kind='item_instance',item_rule_id=rule,
                          owner_id=self.a.entity_id,location={'kind':'unknown'},reason='actual test tool')
        self.a.spec.setdefault('accessible_equipment',[]).append(uid)
        return self.e._physical_objects[uid]

    def run_tool(self,uid='tool',request='tool/one',doc=None,**options):
        return self.e.execute_source_policy_operations(self.a,self.b,doc or self.repulse,
            context=options.pop('context',{'distance':2}),request_id=request,tool_instance_id=uid,**options)

    def block(self,uid='tool',material='ordinary_electronics',event='water'):
        return self.e.gm.observe_environmental_attack(self.a,uid,event_id=event,
            move_id='move/하이드로펌프',material=material,exposed=True,reason='actual unprotected tool failure')

    def test_failed_tool_blocks_all_native_costs_effects_and_execution_until_scene(self):
        self.tool();self.block();before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'functionally unusable'):self.run_tool()
        self.assertEqual(dump_engine(self.e),before)
        self.e.end_of_turn(self.a);self.e.end_scene();self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a)
        result=self.run_tool()
        self.assertEqual(result['tool_use']['instance_id'],'tool')
        self.assertEqual(self.a.budget['swift'],0);self.assertEqual(self.a.spec['ap_spent'],1)
        self.assertEqual(self.b.pos,(4,1));self.assertIn('취약',self.b.conditions)

    def test_two_shielded_instances_use_actual_three_round_recovery_for_programs(self):
        for index,rule in enumerate(('item/캡쳐-스타일러','item/고장기')):
            with self.subTest(rule=rule):
                self.setUp();self.e.at_initiative_count(10)
                self.tool(rule=rule);self.block(material='shielded_class_tool')
                count=TIMING.current(self.e);self.e.end_of_turn(self.a)
                for n in range(2):
                    self.e.start_round([self.a,self.b]);self.e.at_initiative_count(count)
                    before=dump_engine(self.e)
                    with self.assertRaisesRegex(ValueError,'functionally unusable'):self.run_tool()
                    self.assertEqual(dump_engine(self.e),before)
                self.e.start_round([self.a,self.b]);self.e.at_initiative_count(count);self.e.start_of_turn(self.a)
                result=self.run_tool()
                self.assertEqual(result['tool_use']['item_rule_id'],rule)
                self.assertEqual(self.b.pos,(4,1))

    def test_replay_binds_exact_instance_and_survives_both_restores_even_after_failure(self):
        self.tool();self.tool('other');first=self.run_tool()
        self.block();before=dump_engine(self.e)
        self.assertTrue(self.run_tool()['replayed']);self.assertEqual(dump_engine(self.e),before)
        with self.assertRaises(ValueError):self.run_tool('other')
        self.assertEqual(dump_engine(self.e),before)
        saved=self.e.gm.snapshot()
        loaded=load_engine(self.r,json.loads(json.dumps(before,ensure_ascii=False)))
        a,b=loaded.everyone;state=dump_engine(loaded)
        replay=loaded.execute_source_policy_operations(a,b,self.repulse,context={'distance':2},
            request_id='tool/one',tool_instance_id='tool')
        self.assertTrue(replay['replayed']);self.assertEqual(replay['tool_use'],first['tool_use'])
        self.assertEqual(dump_engine(loaded),state)
        self.e.end_of_turn(self.a);self.e.end_scene();self.e.gm.restore(saved)
        self.a,self.b=self.e.everyone;before=dump_engine(self.e)
        self.assertTrue(self.run_tool()['replayed']);self.assertEqual(dump_engine(self.e),before)
        with self.assertRaisesRegex(ValueError,'functionally unusable'):self.run_tool(request='tool/new')
        self.assertEqual(dump_engine(self.e),before)

    def test_actual_access_and_tool_lifecycle_are_required_without_copying_state(self):
        obj=self.tool()
        for field in ('disabled','suppressed'):
            obj[field]=True;before=dump_engine(self.e)
            with self.assertRaisesRegex(ValueError,'functionally unusable'):self.run_tool()
            self.assertEqual(dump_engine(self.e),before);obj.pop(field)
        self.a.spec['accessible_equipment']=[];before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'inaccessible'):self.run_tool()
        self.assertEqual(dump_engine(self.e),before)
        with self.assertRaisesRegex(ValueError,'unknown entity'):self.run_tool('missing')
        self.a.spec['accessible_equipment']=['tool']
        # An explicitly observed loan is allowed; fabricated ownership is unnecessary.
        obj['owner_id']=self.b.entity_id
        result=self.run_tool();self.assertEqual(result['tool_use']['owner_id'],self.b.entity_id)

    def test_tool_failure_between_steps_rolls_back_prior_action_and_effects(self):
        self.tool();before=dump_engine(self.e);original=Engine.execute_source_policy_action
        def disable_after_action(e,*args,**options):
            result=original(e,*args,**options)
            e._physical_objects['tool']['disabled']=True
            return result
        with patch.object(Engine,'execute_source_policy_action',disable_after_action):
            with self.assertRaisesRegex(ValueError,'functionally unusable'):self.run_tool()
        self.assertEqual(dump_engine(self.e),before)
        self.assertEqual(self.run_tool()['status'],'PolicyOperationsCompleted')

    def test_noncombat_elapsed_recovery_gates_second_distinct_native_program(self):
        self.tool(rule='item/고장기');self.e.end_of_turn(self.a);self.e.end_encounter()
        self.block(material='shielded_class_tool');self.b.hp-=6;before=dump_engine(self.e)
        opts=dict(doc=self.recovery,context={'seconds':3},decisions={'healing':{'value':4,'reason':'authored test procedure'}})
        with self.assertRaisesRegex(ValueError,'functionally unusable'):self.run_tool(**opts)
        self.assertEqual(dump_engine(self.e),before)
        self.e.advance_time(30);hp=self.b.hp;result=self.run_tool(**opts)
        self.assertEqual(self.b.hp,hp+4);self.assertEqual(self.e.elapsed_seconds,33)
        self.assertEqual(result['tool_use']['item_rule_id'],'item/고장기')


if __name__=='__main__':unittest.main()
