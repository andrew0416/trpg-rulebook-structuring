"""The selected CSV session clock does not inherit elapsed-time uncertainty."""
from copy import deepcopy
import unittest
import test_completed_item_capability_repairs6 as _fixture_test_completed_item_capability_repairs6
from engine import Engine
import csv_item_capability_contracts as CAP
import item_maturation as M
import item_containers as J
import world_entities as W


class JuicerSessionGapTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_completed_item_capability_repairs6.ItemCapabilityRepairs6.setUpClass.__func__)
    pokemon=_fixture_test_completed_item_capability_repairs6.ItemCapabilityRepairs6.pokemon
    trainer=_fixture_test_completed_item_capability_repairs6.ItemCapabilityRepairs6.trainer
    equip=_fixture_test_completed_item_capability_repairs6.ItemCapabilityRepairs6.equip
    physical=_fixture_test_completed_item_capability_repairs6.ItemCapabilityRepairs6.physical
    sessions=_fixture_test_completed_item_capability_repairs6.ItemCapabilityRepairs6.sessions

    def produce_with_gap(self):
        actor=self.pokemon('gap-shuckle',species='단단지',capabilities=('과즙기',))
        owner=self.trainer('gap-owner');actor.spec['trainer_id']=owner.entity_id
        engine=self.sessions(actor,owner)
        self.equip(engine,actor,'berry/gap','item/오랭열매')
        batch=CAP.juicer_begin(engine,actor,'berry/gap')['id']
        engine.start_round([actor,owner]);engine.end_encounter()
        self.assertTrue(engine.unresolved_time_intervals)
        engine.begin_session('session/1',[actor,owner])
        self.assertEqual(CAP.juicer_session(engine,actor)['phase'],'juice')
        return engine,actor,owner,batch

    def test_csv_known_session_shell_snack_succeeds_despite_actual_elapsed_gap(self):
        engine,actor,owner,batch=self.produce_with_gap()
        loaded=Engine.import_state(self.r,engine.export_state())
        actor=W.actor_index(loaded)[actor.entity_id];engine=loaded
        result=engine.use_item(actor,'item/나무열매쥬스',shell_batch_id=batch,
            duration_minutes=1,duration_reason='actual session shell Snack')
        self.assertEqual(result['status'],'digestion_buff_gained')
        self.assertEqual(actor.spec[M.KEY][batch]['stage'],'consumed')
        self.assertEqual(len(actor.buffs),1)
        self.assertEqual(actor.buffs[0]['effect'],{'kind':'heal','amount':30})
        self.assertNotIn('drink_history',actor.spec)
        before=engine.export_state()
        with self.assertRaises(ValueError):
            engine.use_item(actor,'item/나무열매쥬스',shell_batch_id=batch,duration_minutes=1,duration_reason='duplicate shell Snack')
        self.assertEqual(engine.export_state(),before)
        self.assertTrue(engine.validate_state()['valid'])

    def test_csv_known_session_bottles_and_drinks_despite_actual_elapsed_gap(self):
        engine,actor,owner,batch=self.produce_with_gap()
        self.equip(engine,owner,'bottle/gap','item/빈병')
        engine.gm.observe_empty_container(owner,container_selection='bottle/gap',reason='actual empty gap bottle')
        result=CAP.juicer_session(engine,actor,bottled=True,container_selection='bottle/gap',recipient=owner,reason='actual session shell Juice bottled')
        self.assertEqual(result['stage'],'bottled')
        self.assertEqual(J.body(engine,owner,'bottle/gap')['id'],'bottle/gap')
        saved=engine.gm.snapshot();engine.gm.restore(saved)
        actor,owner=W.actor_index(engine)[actor.entity_id],W.actor_index(engine)[owner.entity_id]
        owner.hp=1
        result=engine.use_item(owner,'item/나무열매쥬스',container_selection='bottle/gap',duration_minutes=1,duration_reason='actual bottled session Juice drink')
        self.assertEqual(result['status'],'consumed');self.assertGreater(owner.hp,1)
        self.assertIsNone(engine._physical_objects['bottle/gap'][J.KEY]['current'])
        self.assertEqual(actor.spec[M.KEY][batch]['stage'],'bottled')
        self.assertTrue(engine.validate_state()['valid'])

    def test_core_elapsed_juice_still_rejects_gap_before_snack_or_bottling(self):
        actor=self.pokemon('seconds-shuckle',species='단단지',capabilities=('과즙기',))
        owner=self.trainer('seconds-owner');actor.spec['trainer_id']=owner.entity_id
        engine=self.sessions(actor,owner)
        self.equip(engine,actor,'berry/seconds','item/오랭열매')
        batch=next(iter(actor.spec[M.KEY]))
        self.assertEqual(actor.spec[M.KEY][batch]['source'],M.SOURCE)
        engine.advance_time(M.policy(self.r)['held_seconds'],[actor])
        self.assertEqual(actor.spec[M.KEY][batch]['stage'],'juice')
        self.equip(engine,owner,'bottle/seconds','item/빈병')
        engine.gm.observe_empty_container(owner,container_selection='bottle/seconds',reason='actual empty seconds bottle')
        engine.start_round([actor,owner]);engine.end_encounter()
        self.assertTrue(engine.unresolved_time_intervals)
        before=engine.export_state()
        with self.assertRaisesRegex(ValueError,'continuity'):
            engine.use_item(actor,'item/나무열매쥬스',shell_batch_id=batch,duration_minutes=1,duration_reason='unresolved seconds Snack')
        self.assertEqual(engine.export_state(),before)
        with self.assertRaisesRegex(ValueError,'continuity'):
            engine.pokemon_activity(owner,'collect_matured_item',target=actor,batch_id=batch,container_selection='bottle/seconds',reason='unresolved seconds bottling')
        self.assertEqual(engine.export_state(),before)
        self.assertEqual(actor.spec[M.KEY][batch]['stage'],'juice')

