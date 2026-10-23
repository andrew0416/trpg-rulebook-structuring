from copy import deepcopy
import json
import unittest

from engine import Engine
import csv_item_physical_contracts as CSV
import items as ITEMS
import world_entities as WORLD
import test_completed_csv_native_remaining as _fixture_test_completed_csv_native_remaining


class VestFaintBoundary(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.setUpClass.__func__)
    pokemon=_fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.pokemon
    trainer=_fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.trainer
    fixture=_fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.fixture
    equip=_fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.equip
    physical=_fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.physical

    def test_actual_faint_preserves_locked_rampage_and_cures_other_afflictions(self):
        actor=self.pokemon('vest-faint-boundary')
        e=self.fixture(actor)
        e.start_round([actor])
        self.equip(e,actor,'csv/vest-faint','item/돌격조끼')
        lock_before=deepcopy(actor.spec[CSV.ACTOR_STATE]['assault_vest_rampage'])
        self.assertEqual(lock_before['instance_id'],'csv/vest-faint')
        e.apply_status(actor,'혼란',source='move/이상한빛')
        e.apply_status(actor,'마비',source='move/전기자석파')
        ITEMS.unregister_item(e,actor,'item/돌격조끼')
        e.lose_hp(actor,actor.hp,source='condition/vest-faint-test',unpreventable=True)
        self.assertIn('기절',actor.conditions)
        self.assertIn('난동',actor.conditions)
        self.assertNotIn('혼란',actor.conditions)
        self.assertNotIn('마비',actor.conditions)
        self.assertTrue(actor.spec[CSV.ACTOR_STATE]['assault_vest_rampage']['active'])
        self.assertEqual(actor.spec[CSV.ACTOR_STATE]['assault_vest_rampage'],lock_before)
        e.gm.snapshot('fainted-vest')
        e.end_encounter([actor])
        self.assertNotIn('난동',actor.conditions)
        e.gm.restore('fainted-vest')
        actor=WORLD.actor_index(e)[actor.entity_id]
        self.assertEqual(actor.spec[CSV.ACTOR_STATE]['assault_vest_rampage'],lock_before)
        self.assertIn('난동',actor.conditions)
        self.assertIn('기절',actor.conditions)
        restored=Engine.import_state(self.r,json.loads(json.dumps(e.export_state())))
        actual=WORLD.actor_index(restored)[actor.entity_id]
        self.assertEqual(actual.spec[CSV.ACTOR_STATE]['assault_vest_rampage'],lock_before)
        before=deepcopy(restored.export_state())
        with self.assertRaisesRegex(ValueError,'cannot be cured'):
            restored.cure_status(actual,'난동')
        self.assertEqual(restored.export_state(),before)
        restored.end_encounter([actual])
        self.assertNotIn('난동',actual.conditions)
        self.assertIn('기절',actual.conditions)
        self.assertFalse(actual.spec[CSV.ACTOR_STATE]['assault_vest_rampage']['active'])
        ended=actual.spec[CSV.ACTOR_STATE]['assault_vest_rampage']
        self.assertEqual(ended['instance_id'],lock_before['instance_id'])
        self.assertEqual(ended['encounter'],lock_before['encounter'])

    def test_ordinary_faint_still_cures_all_ordinary_afflictions(self):
        actor=self.pokemon('ordinary-faint-boundary')
        e=self.fixture(actor)
        e.start_round([actor])
        for condition in ('난동','혼란','마비'):
            e.apply_status(actor,condition,source='move/actual-test-source')
        e.lose_hp(actor,actor.hp,source='condition/ordinary-faint-test',unpreventable=True)
        self.assertEqual(actor.conditions,{'기절'})
