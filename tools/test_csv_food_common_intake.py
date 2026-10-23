"""Public exact-source intake and real form/save consumers, no direct producer."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from engine import Engine
import csv_item_food_contracts as CSV
import food_effects as FOOD
import state_codec as CODEC
import world_entities as WORLD
import effect_instances as INSTANCES
import consumption_execution as STOCK_RECEIPTS
import condition_recovery as RECOVERY
import gmax_moves as GMAX
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts

CLAUSES = {'item/다이버섯': 'C2CSV/inventory:92:7', 'item/흉내허브': 'C2CSV/inventory:232:10',
           'item/회복허브': 'C2CSV/item-data:66:1', 'item/단맛-과자': 'C2CSV/inventory:91:7'}


class CsvFoodCommonIntake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass()

    def setUp(self):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.answers.clear()
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.provider = None

    def fixture(self, item, *, trainer=False, abilities=(), count=2):
        fixture = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests()
        maker = fixture.trainer if trainer else fixture.pokemon
        opts = {} if trainer else {'abilities': abilities, 'species': 'Venusaur' if item=='item/다이버섯' else '피카츄'}
        actor = maker('native-food-holder', items={item: count, 'item/초코바': 1}, **opts)
        other = fixture.pokemon('native-food-other')
        return fixture.fixture(actor, other), actor, other

    def intake(self, e, actor, item, **options):
        return e.use_item(actor, item, food_policy=CLAUSES[item],
                          duration_minutes=1, duration_reason='explicit GM intake minute', **options)

    def buff(self, actor, item):
        return next(row for row in actor.buffs if row.get('item') == item)

    def restored(self, e):
        return CODEC.load_engine(e.r, json.loads(json.dumps(CODEC.dump_engine(e))))

    def test_four_exact_sources_use_common_time_stock_slot_receipt_and_json(self):
        for item in CLAUSES:
            for trainer in ((False,True) if item=='item/흉내허브' else (False,)):
                with self.subTest(item=item, trainer=trainer):
                    e, actor, other = self.fixture(item, trainer=trainer)
                    before = e.elapsed_seconds
                    result = self.intake(e, actor, item)
                    self.assertEqual(result['status'], 'digestion_buff_gained')
                    buff = self.buff(actor, item)
                    self.assertEqual(e.elapsed_seconds-before, 60)
                    self.assertEqual(FOOD.slots(actor), 1)
                    self.assertEqual(actor.spec['items'][item], 1)
                    self.assertEqual(buff['csv_food_source']['clause_id'], CLAUSES[item])
                    self.assertEqual(buff[INSTANCES.KEY]['kind'], 'digestion')
                    self.assertEqual(buff[INSTANCES.KEY]['capacity'], FOOD.ordinary_capacity())
                    paid = next(iter(STOCK_RECEIPTS.validate(actor).values()))
                    self.assertEqual(paid['outcome'], 'applied')
                    self.assertEqual(paid['results'], [{'kind': 'digestion_buff', 'id': buff['id']}])
                    self.assertNotIn(CSV.STATE, actor.spec)
                    restored = self.restored(e)
                    holder = WORLD.actor_index(restored)[actor.entity_id]
                    self.assertEqual(holder.buffs, actor.buffs)
                    self.assertEqual(FOOD.slots(holder), 1)
                    before = CODEC.dump_engine(restored)
                    with self.assertRaisesRegex(ValueError, 'another Digestion Buff'):
                        restored.use_item(holder, 'item/초코바', duration_minutes=1, duration_reason='full slot')
                    self.assertEqual(before, CODEC.dump_engine(restored))

    def test_missing_duration_refusal_combat_and_ordinary_action_permission_have_no_cost(self):
        for item in CLAUSES:
            e, actor, other = self.fixture(item)
            before = CODEC.dump_engine(e)
            pending = e.use_item(actor, item, food_policy=CLAUSES[item])
            self.assertTrue(getattr(pending, 'pending', False) or type(pending).__name__ == 'PendingDecision')
            self.assertEqual(before, CODEC.dump_engine(e))
            self.intake(e, actor, item, accepted=False)
            self.assertEqual((e.elapsed_seconds,actor.spec['items'][item],actor.buffs),(0,2,[]))
            e.start_round([actor, other]); e.start_of_turn(actor, initiative_count=20)
            before = CODEC.dump_engine(e)
            with self.assertRaises(ValueError):
                self.intake(e, actor, item)
            self.assertEqual(before, CODEC.dump_engine(e))

    def test_intake_late_native_grant_fault_rolls_back_time_stock_action_and_slot(self):
        e, actor, other = self.fixture('item/흉내허브')
        before = CODEC.dump_engine(e)
        original = FOOD.grant_buff
        attempted = []
        def fail(engine, target, *args, **options):
            result = original(engine, target, *args, **options)
            attempted.append({'elapsed': engine.elapsed_seconds, 'slots': FOOD.slots(target),
                              'stock': target.spec['items']['item/흉내허브']})
            raise ValueError('bounded fault after native grant')
        with patch.object(FOOD, 'grant_buff', fail):
            with self.assertRaisesRegex(ValueError, 'bounded fault'):
                self.intake(e, actor, 'item/흉내허브')
        self.assertEqual(attempted, [{'elapsed': 60, 'slots': 1, 'stock': 1}])
        self.assertEqual(before, CODEC.dump_engine(e))

    def test_exact_csv_selection_cannot_change_chef_default_or_admit_arbitrary_variant(self):
        e, actor, other = self.fixture('item/단맛-과자')
        result = e.use_item(actor, 'item/단맛-과자', duration_minutes=1, duration_reason='Chef source')
        self.assertEqual(actor.buffs[0]['effect'], FOOD.chef_effect(e.r, 'item/단맛-과자'))
        self.assertNotIn('csv_food_source', actor.buffs[0])
        before = CODEC.dump_engine(e)
        for requested, clause in [('item/초코바', CLAUSES['item/단맛-과자']),
                                   ('item/단맛-과자', 'C2CSV/inventory:999:7')]:
            with self.assertRaises(ValueError):
                e.use_item(actor, requested, food_policy=clause, duration_minutes=1, duration_reason='wrong source')
            self.assertEqual(before, CODEC.dump_engine(e))

    def test_recovery_actual_native_save_choice_survives_json_and_spends_once(self):
        e, actor, other = self.fixture('item/회복허브')
        self.intake(e, actor, 'item/회복허브')
        buff = self.buff(actor, 'item/회복허브')
        e.consume_food_buff(actor, buff_id=buff['id'], save_condition='혼란')
        e = self.restored(e); actor = WORLD.actor_index(e)[actor.entity_id]
        self.assertNotIn(CSV.STATE, actor.spec)
        wrong = RECOVERY.saving_check(e, actor, '독', 10, fixed=9)
        self.assertEqual(wrong['food_bonus'], 0)
        check = RECOVERY.saving_check(e, actor, '혼란', 10, fixed=9)
        self.assertEqual((check['food_bonus'], check['passed']), (2, True))
        self.assertFalse(actor.buffs)
        receipt = actor.spec['food_consumption_receipts'][0]
        self.assertEqual((receipt['producer'], receipt['benefit']),
                         ('saving_check', {'save_condition': '혼란', 'bonus': 2}))
        self.assertEqual(RECOVERY.saving_check(e, actor, '혼란', 10, fixed=9)['food_bonus'], 0)
        self.assertEqual(len(actor.spec['food_consumption_receipts']), 1)
        self.restored(e)

    def test_dynamax_actual_public_form_entry_spends_protected_buff_and_no_string_forgery(self):
        e, actor, other = self.fixture('item/다이버섯')
        self.intake(e, actor, 'item/다이버섯')
        buff = self.buff(actor, 'item/다이버섯')
        before = CODEC.dump_engine(e)
        with self.assertRaisesRegex(ValueError, 'native form entry'):
            CSV.consume_dynamax(e, actor, buff['id'], form_source='dynamax')
        self.assertEqual(before, CODEC.dump_engine(e))
        self.assertIsNone(FOOD.transfer_live_preflight(e, other, actor, 'move/벌레먹기'))
        e.start_round([actor, other]); e.start_of_turn(actor, initiative_count=20)
        result = e.enter_gigantamax(actor, source_id='item/다이버섯', reason='actual designated form')
        self.assertEqual(result['food_consumption']['buff_id'], buff['id'])
        self.assertFalse(actor.buffs)
        self.assertEqual(actor.spec['food_consumption_receipts'][0]['producer'], 'designated_dynamax_form')
        e = self.restored(e); actor = WORLD.actor_index(e)[actor.entity_id]
        e.exit_gigantamax(actor, reason='bounded form end')
        before = CODEC.dump_engine(e)
        with self.assertRaisesRegex(ValueError, 'one actual Dynamax'):
            e.enter_gigantamax(actor, source_id='item/다이버섯', reason='cannot reuse spent buff')
        self.assertEqual(before, CODEC.dump_engine(e))

    def test_native_dynamax_late_consumer_fault_rolls_back_form_and_common_receipt(self):
        e, actor, other = self.fixture('item/다이버섯')
        self.intake(e, actor, 'item/다이버섯')
        e.start_round([actor, other]); e.start_of_turn(actor, initiative_count=20)
        before = CODEC.dump_engine(e)
        original = CSV._spend
        attempted = []
        def fail(engine, target, *args):
            result = original(engine, target, *args)
            attempted.append((target.form, len(target.buffs), result['sequence']))
            raise ValueError('bounded native form consumer fault')
        with patch.object(CSV, '_spend', fail):
            with self.assertRaisesRegex(ValueError, 'bounded native form'):
                e.enter_gigantamax(actor, source_id='item/다이버섯', reason='late failure')
        self.assertTrue(attempted)
        self.assertEqual(before, CODEC.dump_engine(e))


if __name__ == '__main__':
    unittest.main()
