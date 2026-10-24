"""Actual repair/tool consumers and native recovery boundaries for electronics."""
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT/'engine') not in sys.path:
    sys.path[:0] = [str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_repair_restore as FIX
import environmental_item_state as ENV
import world_entities as W
import repair_restore as REPAIR
import crafting_recipes as Q
from state_codec import load_engine


class ElectronicTests(unittest.TestCase):
    setUpClass = classmethod(FIX.RepairTests.setUpClass.__func__)
    setUp = FIX.RepairTests.setUp
    trainer = FIX.RepairTests.trainer
    bot = FIX.RepairTests.bot
    policy = FIX.RepairTests.policy
    snap = FIX.RepairTests.snap
    restore = FIX.RepairTests.restore

    def tool(self, uid='camera', rule='item/카메라-키트'):
        W.register_object(self.e,uid,kind='item_instance',item_rule_id=rule,
                          owner_id=self.a.entity_id,location={'kind':'unknown'},reason='actual electronic tool')
        self.a.spec.setdefault('accessible_equipment',[]).append(uid)
        return dict(kind='tool',item_id=rule,names=[rule],instance_id=uid)

    def observe(self, uid='camera', material='ordinary_electronics', **options):
        args=dict(event_id='water:'+uid,move_id='move/하이드로펌프',material=material,
                  actual_type='물',reason='GM observed water reaching actual unprotected electronics',exposed=True)
        args.update(options)
        return self.e.gm.observe_environmental_attack(self.a,uid,**args)

    def test_actual_tool_rejects_before_payment_until_real_scene_end(self):
        node=self.tool(); policy=self.policy(); policy['requirements'].append(node)
        self.observe(); before=self.snap()
        with self.assertRaisesRegex(ValueError,'qualification'):
            self.restore(policy)
        self.assertEqual(self.snap(),before)
        self.e.end_encounter()  # A combat boundary is not a narrative scene end.
        self.assertTrue(ENV.active(self.e._physical_objects['camera']))
        self.e.end_scene()
        self.assertFalse(ENV.active(self.e._physical_objects['camera']))
        self.assertTrue(self.restore(policy)['passed'])
        self.assertEqual(self.e.elapsed_seconds,60)

    def test_native_paid_repair_ends_electrical_sources_but_not_frozen_state(self):
        self.tool(); self.observe()
        self.observe(event_id='electric',move_id='move/전기쇼크',actual_type='전기')
        self.e.gm.observe_environmental_item(self.a,'camera',event_id='other-cold',condition='frozen',
            source='GM cold exposure',reason='independent observed freeze',exposed=True)
        result=self.restore(self.policy(1),target='camera')
        self.assertTrue(result['passed']); self.assertEqual(self.e.elapsed_seconds,60)
        obj=self.e._physical_objects['camera']
        self.assertFalse(ENV.active(obj,'electrical_failure')); self.assertTrue(ENV.active(obj,'frozen'))
        before=self.snap(); self.assertEqual(self.restore(self.policy(1),target='camera'),result)
        self.assertEqual(self.snap(),before)
        self.e.gm.recover_environmental_item(self.a,'camera',event_id='other-cold',end='thaw',reason='actual thaw')
        ENV.require_usable(self.e,obj)

    def test_three_rounds_expire_at_same_initiative_count_and_survive_restoration(self):
        node=self.tool('styler','item/캡쳐-스타일러')
        self.e.start_round([self.a]); self.e.at_initiative_count(12)
        first=self.observe('styler','shielded_class_tool')
        for count in range(2):
            self.e.start_round([self.a]); self.e.at_initiative_count(12)
            self.assertFalse(Q._observe(self.e,self.a,node,set()))
        saved=self.e.gm.snapshot()
        loaded=load_engine(self.poly,json.loads(json.dumps(self.snap(),ensure_ascii=False)))
        actor=next(x for x in loaded.gm.everyone if x.entity_id==self.a.entity_id)
        loaded.start_round([actor]); loaded.at_initiative_count(13)
        self.assertFalse(Q._observe(loaded,actor,node,set()))
        loaded.at_initiative_count(12)
        self.assertTrue(Q._observe(loaded,actor,node,set()))
        self.e.start_round([self.a]); self.e.at_initiative_count(12)
        self.assertEqual(first,self.observe('styler','shielded_class_tool'))
        self.assertTrue(Q._observe(self.e,self.a,node,set()))
        self.e.gm.restore(saved)
        self.assertFalse(Q._observe(self.e,self.a,node,set()))

    def test_round_end_fallback_and_missing_clock_or_wrong_material_are_atomic(self):
        node=self.tool('snag','item/고장기')
        self.e.begin_encounter([self.a]); before=self.snap()
        with self.assertRaisesRegex(ValueError,'clock'):
            self.observe('snag','shielded_class_tool')
        self.assertEqual(self.snap(),before)
        with self.assertRaisesRegex(ValueError,'shielded'):
            self.observe('snag','ordinary_electronics')
        self.assertEqual(self.snap(),before)
        protected=self.observe('snag','shielded_class_tool',event_id='protected',exposed=False)
        self.assertEqual(protected,self.observe('snag','shielded_class_tool',event_id='protected',exposed=False))
        self.e.start_round([self.a]); self.e.at_initiative_count(10)
        self.observe('snag','shielded_class_tool')
        for n in range(3):self.e.start_round([self.a])
        self.assertFalse(Q._observe(self.e,self.a,node,set()))
        self.e.end_round()
        self.assertTrue(Q._observe(self.e,self.a,node,set()))

    def test_late_scene_or_repair_failure_preserves_original_block_and_costs(self):
        self.tool(); self.observe(); before=self.snap()
        import scene_lighting as LIGHT
        with patch.object(LIGHT,'end_scene',side_effect=ValueError('late scene failure')):
            with self.assertRaises(ValueError):self.e.end_scene()
        self.assertEqual(self.snap(),before)
        original=REPAIR.restore_item
        def fail_after_repair(engine,uid):
            original(engine,uid)
            raise ValueError('late repair failure')
        with patch.object(REPAIR,'restore_item',side_effect=fail_after_repair):
            with self.assertRaises(ValueError):self.restore(self.policy(1),target='camera')
        self.assertEqual(self.snap(),before)

    def test_initiative_recovery_failure_rolls_back_clock_and_all_prior_expirations(self):
        self.tool('styler','item/캡쳐-스타일러')
        self.e.start_round([self.a]); self.e.at_initiative_count(12)
        self.observe('styler','shielded_class_tool')
        for n in range(3):self.e.start_round([self.a])
        self.e.at_initiative_count(13)
        before=self.snap(); original=ENV._release
        def fail_after_release(*args,**kwargs):
            original(*args,**kwargs)
            raise ValueError('late initiative recovery failure')
        with patch.object(ENV,'_release',side_effect=fail_after_release):
            with self.assertRaises(ValueError):self.e.at_initiative_count(12)
        self.assertEqual(self.snap(),before)
        self.e.at_initiative_count(12)
        self.assertFalse(ENV.active(self.e._physical_objects['styler']))

    def test_noncombat_actual_tools_recover_at_thirty_seconds_before_paid_consumer(self):
        nodes=[self.tool('styler','item/캡쳐-스타일러'), self.tool('snag','item/고장기')]
        first=[self.observe(node['instance_id'],'shielded_class_tool') for node in nodes]
        self.tool();self.observe()  # Ordinary electronics retain scene/repair lifetime.
        policy=self.policy();policy['requirements'].extend(nodes)
        self.e.advance_time(29);before=self.snap()
        with self.assertRaisesRegex(ValueError,'qualification'):self.restore(policy)
        self.assertEqual(self.snap(),before)
        self.e.advance_time(1)
        for node,receipt in zip(nodes,first):
            self.assertTrue(Q._observe(self.e,self.a,node,set()))
            self.assertEqual(self.observe(node['instance_id'],'shielded_class_tool'),receipt)
        self.assertTrue(ENV.active(self.e._physical_objects['camera']))
        self.assertTrue(self.restore(policy)['passed'])
        self.assertEqual(self.e.elapsed_seconds,90)

    def test_actual_combat_exit_retains_remaining_time_and_both_restores(self):
        node=self.tool('styler','item/캡쳐-스타일러')
        self.e.start_round([self.a]);self.e.at_initiative_count(12)
        self.observe('styler','shielded_class_tool',round_offset_seconds=4)
        self.e.end_scene(round_elapsed_seconds=7)
        self.assertEqual(self.e.elapsed_seconds,7)
        self.assertFalse(Q._observe(self.e,self.a,node,set()))
        saved=self.e.gm.snapshot()
        loaded=load_engine(self.poly,json.loads(json.dumps(self.snap(),ensure_ascii=False)))
        for e in (self.e,loaded):
            a=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id)
            e.advance_time(26)
            self.assertFalse(Q._observe(e,a,node,set()))
            e.advance_time(1)
            self.assertTrue(Q._observe(e,a,node,set()))
            self.assertEqual(e.elapsed_seconds,34)
        self.e.gm.restore(saved)
        self.assertFalse(Q._observe(self.e,self.a,node,set()))
        self.e.advance_time(27)
        self.assertTrue(Q._observe(self.e,self.a,node,set()))

    def test_unknown_partial_exit_and_new_encounter_do_not_reset_or_invent_time(self):
        node=self.tool('snag','item/고장기')
        self.e.start_round([self.a]);self.e.at_initiative_count(12)
        self.observe('snag','shielded_class_tool')
        self.e.end_encounter()
        self.assertEqual(self.e.elapsed_seconds,0)
        self.assertEqual(len(self.e.unresolved_time_intervals),1)
        self.e.advance_time(19)
        self.e.start_round([self.a]);self.e.at_initiative_count(12);self.e.end_round()
        self.assertEqual(self.e.elapsed_seconds,29)
        self.assertFalse(Q._observe(self.e,self.a,node,set()))
        self.e.end_encounter();self.e.advance_time(1)
        self.assertTrue(Q._observe(self.e,self.a,node,set()))
        self.assertEqual(len(self.e.unresolved_time_intervals),1)

    def test_elapsed_deadline_splits_resumable_clock_and_late_failure_rolls_back(self):
        self.tool('styler','item/캡쳐-스타일러');self.observe('styler','shielded_class_tool')
        before=self.snap();original=ENV._release
        def fail_after_release(*args,**kwargs):
            original(*args,**kwargs)
            raise ValueError('late elapsed recovery failure')
        with patch.object(ENV,'_release',side_effect=fail_after_release):
            with self.assertRaisesRegex(ValueError,'late elapsed'):
                self.e.advance_time(40)
        self.assertEqual(self.snap(),before)
        result=self.e.advance_time(40,request_id='tool-clock',source='gm/elapsed',resumable=True)
        self.assertEqual(result['status'],'complete')
        block=next(iter(self.e._physical_objects['styler'][ENV.FIELD].values()))
        self.assertEqual(block['released']['at'],30)
        self.assertEqual(self.e.elapsed_seconds,40)
        self.assertEqual([(r['start'],r['end']) for r in result['segments']],[(0,30),(30,40)])
        before=self.snap()
        self.e.advance_time(40,request_id='tool-clock',source='gm/elapsed',resumable=True)
        self.assertEqual(self.snap(),before)


    def test_unknown_birth_round_is_not_credited_as_ten_elapsed_seconds(self):
        node=self.tool('styler','item/캡쳐-스타일러')
        self.e.start_round([self.a]);self.e.at_initiative_count(12)
        self.observe('styler','shielded_class_tool')
        self.e.end_round();self.e.end_encounter()
        self.e.advance_time(29)
        self.assertEqual(self.e.elapsed_seconds,39)
        self.assertFalse(Q._observe(self.e,self.a,node,set()))
        self.e.advance_time(1)
        self.assertTrue(Q._observe(self.e,self.a,node,set()))


if __name__=='__main__':unittest.main()
