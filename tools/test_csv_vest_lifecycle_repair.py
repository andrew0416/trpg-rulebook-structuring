from copy import deepcopy
import json
import unittest

from engine import Engine
import combat_state_lifecycle as COMBAT
import items as ITEMS
import csv_item_physical_contracts as CSV
import world_entities as WORLD
import test_completed_csv_native_remaining as _fixture_test_completed_csv_native_remaining


class VestLifecycleRepair(unittest.TestCase):
    setUpClass = classmethod(_fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.setUpClass.__func__)
    pokemon = _fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.pokemon
    trainer = _fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.trainer
    fixture = _fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.fixture
    equip = _fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.equip
    physical = _fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.physical
    test_actual_end = _fixture_test_completed_csv_native_remaining.CompletedCsvNativeRemaining.test_vest_native_cure_rejection_after_unequip_and_actual_encounter_end

    def equipped(self, *, battle=True):
        actor = self.pokemon('actual-vest-lifetime')
        other = self.pokemon('actual-vest-opponent')
        e = self.fixture(actor,other)
        if battle:
            e.start_round([actor,other])
        self.equip(e,actor,'csv/vest-lifetime','item/돌격조끼')
        return e,actor,other

    def test_recall_preserves_only_the_locked_condition_then_actual_end_cures_it(self):
        e,actor,other=self.equipped()
        e.apply_status(actor,'혼란',source='move/이상한빛')
        ITEMS.unregister_item(e,actor,'item/돌격조끼')
        COMBAT.recall(e,actor)
        self.assertIn('난동',actor.conditions)
        self.assertNotIn('혼란',actor.conditions)
        restored=Engine.import_state(self.r,json.loads(json.dumps(e.export_state())))
        actual=WORLD.actor_index(restored)[actor.entity_id]
        self.assertTrue(actual.spec[CSV.ACTOR_STATE]['assault_vest_rampage']['active'])
        restored.end_encounter([actual])
        self.assertNotIn('난동',actual.conditions)
        self.assertFalse(actual.spec[CSV.ACTOR_STATE]['assault_vest_rampage']['active'])
        restored.end_encounter([actual])
        restored.export_state()

    def test_generic_reset_without_round_clock_does_not_invent_encounter_end(self):
        e,actor,other=self.equipped(battle=False)
        COMBAT.reset_actor(e,actor)
        self.assertIn('난동',actor.conditions)
        self.assertTrue(actor.spec[CSV.ACTOR_STATE]['assault_vest_rampage']['active'])
        with self.assertRaisesRegex(ValueError,'cannot be cured'):
            e.cure_status(actor,'난동')

    def test_ordinary_cure_rejection_does_not_mutate_condition_receipts(self):
        e,actor,other=self.equipped()
        before=deepcopy(e.export_state())
        with self.assertRaisesRegex(ValueError,'cannot be cured'):
            e.cure_status(actor,'난동')
        self.assertEqual(e.export_state(),before)

    def test_unlocked_rampage_and_other_volatile_still_clear_on_recall(self):
        actor=self.pokemon('ordinary-rampage')
        e=self.fixture(actor)
        e.start_round([actor])
        e.apply_status(actor,'난동',source='move/난동부리기')
        e.apply_status(actor,'혼란',source='move/이상한빛')
        COMBAT.recall(e,actor)
        self.assertNotIn('난동',actor.conditions)
        self.assertNotIn('혼란',actor.conditions)
