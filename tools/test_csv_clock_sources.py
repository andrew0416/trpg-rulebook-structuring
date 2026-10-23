"""Exact native CSV intake clock admission, persistence and selection scope."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

import clock_invocations as CLOCK
import csv_item_food_contracts as CSV
import effects as FX
import food_effects as FOOD
import consumption_execution as STOCK
import effect_contracts as CONTRACTS
import resolution_transaction as REQUESTS
import state_codec as CODEC
import world_entities as WORLD
from ruleset import ExcludedRuleSelection
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts
from test_csv_food_common_intake import CLAUSES
import test_csv_food_common_intake as _fixture_test_csv_food_common_intake


class CsvClockSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass()

    fixture = _fixture_test_csv_food_common_intake.CsvFoodCommonIntake.fixture
    intake = _fixture_test_csv_food_common_intake.CsvFoodCommonIntake.intake
    restored = _fixture_test_csv_food_common_intake.CsvFoodCommonIntake.restored

    def setUp(self):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.answers.clear()
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.provider = None

    def waiting(self, item='item/회복허브'):
        e, actor, other = self.fixture(item)
        effect = {'type':'stage_change','stat':'atk','delta':1,
                  'repeat':{'seconds':5,'times':1},'if':'target was asleep'}
        self.assertEqual(FX.run_effects(e, actor, actor, [effect],
            {'hit':True,'target_was_asleep':True}, 'external/csv-intake-boundary'), (1,0))
        result = self.intake(e, actor, item, resumable=True, request_id='csv-clock')
        self.assertEqual(result['status'], 'waiting')
        self.assertEqual((e.elapsed_seconds, actor.spec['items'][item], actor.buffs), (5,2,[]))
        self.assertIsNone(e._clock_invocations['csv-clock']['activity']['payment'])
        return e, actor, other

    def answer(self, e, actor):
        child = e._clock_invocations['csv-clock']['children'][-1]
        e.resolve_effect_condition(actor, child['record']['receipt'], target_was_asleep=True,
                                   reason='GM observed the actual five-second intake boundary')

    def test_four_exact_public_resumable_intakes_keep_payment_original_and_json_query(self):
        for item in CLAUSES:
            with self.subTest(item=item):
                e, actor, other = self.fixture(item)
                result = self.intake(e, actor, item, resumable=True, request_id='csv-clock')
                self.assertEqual((result['status'], e.elapsed_seconds, actor.spec['items'][item], FOOD.slots(actor)),
                                 ('digestion_buff_gained',60,1,1))
                row = e._clock_invocations['csv-clock']; activity = row['activity']
                choice = CSV.source_choice(e.r, item, CLAUSES[item])
                self.assertEqual(activity['plan']['csv_food_source'], choice)
                self.assertEqual(activity['plan']['stock']['source_selection'], choice)
                self.assertEqual(activity['payment']['source_selection'], choice)
                self.assertIs(activity['native'], actor.buffs[0])
                self.assertIs(activity['payment'], actor.buffs[0]['item_stock'])
                self.assertIs(next(iter(STOCK.validate(actor).values()))['item_stock'], activity['payment'])
                e = self.restored(e); actor = WORLD.actor_index(e)[actor.entity_id]
                before = CODEC.dump_engine(e)
                self.assertEqual(self.intake(e, actor, item, resumable=True, request_id='csv-clock'), result)
                self.assertEqual(before, CODEC.dump_engine(e))

    def test_waiting_json_and_gm_restore_resume_the_actual_boundary_without_double_payment(self):
        e, actor, other = self.waiting()
        e = self.restored(e); actor = WORLD.actor_index(e)[actor.entity_id]
        e.gm.snapshot('actual-csv-boundary')
        self.answer(e, actor)
        result = self.intake(e, actor, 'item/회복허브', resumable=True, request_id='csv-clock')
        self.assertEqual((e.elapsed_seconds, actor.stages['atk'], actor.spec['items']['item/회복허브']), (60,1,1))
        self.assertEqual(len(STOCK.validate(actor)), 1)
        e.gm.restore('actual-csv-boundary', reason='revisit the observed unpaid intake boundary')
        self.assertEqual((e.elapsed_seconds, actor.stages['atk'], actor.spec['items']['item/회복허브']), (5,0,2))
        self.assertFalse(STOCK.validate(actor))
        self.answer(e, actor)
        self.assertEqual(self.intake(e, actor, 'item/회복허브', resumable=True, request_id='csv-clock'), result)
        self.assertEqual((e.elapsed_seconds, actor.stages['atk'], len(STOCK.validate(actor))), (60,1,1))
        self.restored(e)

    def test_changed_source_bytes_registry_payload_and_pin_reject_save_resume_and_gm_restore(self):
        e, actor, other = self.waiting()
        e.gm.snapshot('pinned-csv-boundary')
        source = Path(e.r.root) / 'input/db/item-data.csv'
        original_read = Path.read_bytes
        def changed_bytes(path):
            value = original_read(path)
            return value + b'\nchanged source observation' if path.resolve() == source.resolve() else value
        with patch.object(Path, 'read_bytes', changed_bytes):
            for operation in (lambda:CLOCK.validate(e), lambda:CODEC.dump_engine(e),
                              lambda:self.intake(e,actor,'item/회복허브',resumable=True,request_id='csv-clock'),
                              lambda:e.gm.restore('pinned-csv-boundary', reason='changed source rejected')):
                with self.assertRaises(ValueError): operation()
        raw = e.r.items_mech['item/회복허브']
        with patch.dict(raw, {'name': raw['name'] + ' changed'}):
            for operation in (lambda:CLOCK.validate(e), lambda:CODEC.dump_engine(e),
                              lambda:e.gm.restore('pinned-csv-boundary', reason='changed catalog rejected')):
                with self.assertRaisesRegex(ValueError, 'source policy changed'): operation()
        policy = e.r._csv_remaining_item_contract_policy['rows'][CLAUSES['item/회복허브']]
        with patch.dict(policy, {'source_row_sha256':'0'*64}):
            with self.assertRaisesRegex(ValueError, 'source provenance changed'): CLOCK.validate(e)
        self.assertEqual((e.elapsed_seconds, actor.spec['items']['item/회복허브'], actor.buffs), (5,2,[]))
        self.assertEqual(self.intake(e, actor, 'item/회복허브', resumable=True, request_id='csv-clock')['status'], 'waiting')

    def test_exact_selection_is_bound_to_request_plan_stock_and_actual_payment(self):
        e, actor, other = self.waiting()
        activity = e._clock_invocations['csv-clock']['activity']
        request = activity['request']; plan = activity['plan']
        with patch.dict(request, {'policy':CLAUSES['item/흉내허브']}):
            activity['request_fingerprint'] = REQUESTS.request_fingerprint(request)
            with self.assertRaises(ValueError): CLOCK.validate(e)
        activity['request_fingerprint'] = REQUESTS.request_fingerprint(request)
        for target, update in ((plan['stock'], {'source_selection':None}),
                               (plan, {'effect':{'kind':'save_bonus','amount':99}}),
                               (plan, {'item':'item/흉내허브'})):
            with patch.dict(target, update):
                activity['plan_fingerprint'] = REQUESTS.request_fingerprint(plan)
                with self.assertRaises(ValueError): CLOCK.validate(e)
        activity['plan_fingerprint'] = REQUESTS.request_fingerprint(plan)
        self.answer(e, actor)
        self.intake(e, actor, 'item/회복허브', resumable=True, request_id='csv-clock')
        activity = e._clock_invocations['csv-clock']['activity']; payment = activity['payment']
        with patch.dict(payment, {'source_selection':CSV.source_choice(e.r,'item/흉내허브',CLAUSES['item/흉내허브'])}):
            with self.assertRaisesRegex(ValueError, 'original stock payment'): CLOCK.validate(e)
        activity['payment'] = deepcopy(payment)
        with self.assertRaisesRegex(ValueError, 'original stock payment'): CLOCK.validate(e)
        activity['payment'] = payment
        self.restored(e)

    def test_explicit_csv_intake_does_not_admit_generic_automatic_selection(self):
        e, actor, other = self.fixture('item/회복허브')
        before = CODEC.dump_engine(e)
        for operation in (lambda:CONTRACTS.source_profile(e, 'item/회복허브'),
                          lambda:e.advance_time(1,[actor],resumable=True,request_id='generic',source='item/회복허브'),
                          lambda:e.r.item_effects('item/회복허브')):
            with self.assertRaises(ExcludedRuleSelection): operation()
        self.assertEqual(before, CODEC.dump_engine(e))
        self.intake(e,actor,'item/회복허브',resumable=True,request_id='csv-clock')
        with self.assertRaises(ExcludedRuleSelection): CONTRACTS.source_profile(e,'item/회복허브')
        with self.assertRaises(ValueError):
            e.use_item(actor,'item/회복허브',food_policy='C2CSV/item-data:999:1',
                       duration_minutes=1,duration_reason='unreviewed clause',resumable=True,request_id='bad')


if __name__ == '__main__':
    unittest.main()
