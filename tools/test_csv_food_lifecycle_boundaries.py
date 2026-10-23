"""Distinct intake/stock/capacity/restore boundaries shared by the four rows."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from engine import Engine, Rules
import csv_item_food_contracts as CSV
import food_effects as FOOD
import item_stock as STOCK
import state_codec as CODEC
import world_entities as WORLD
import condition_recovery as RECOVERY
import cultivation_state as PLANTS
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts
from test_csv_food_common_intake import CLAUSES
import test_csv_food_common_intake as _fixture_test_csv_food_common_intake


class CsvFoodLifecycleBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass()
        cls.playtest = Rules(_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.root, ruleset='playtest')

    fixture = _fixture_test_csv_food_common_intake.CsvFoodCommonIntake.fixture
    intake = _fixture_test_csv_food_common_intake.CsvFoodCommonIntake.intake
    buff = _fixture_test_csv_food_common_intake.CsvFoodCommonIntake.buff
    restored = _fixture_test_csv_food_common_intake.CsvFoodCommonIntake.restored

    def setUp(self):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.answers.clear()
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.provider = None

    def test_recovery_real_start_turn_save_and_gm_restore_use_the_one_common_choice(self):
        e, actor, other = self.fixture('item/회복허브')
        self.intake(e, actor, 'item/회복허브')
        buff = self.buff(actor, 'item/회복허브')
        e.apply_status(actor, '마비')
        e.consume_food_buff(actor, buff_id=buff['id'], save_condition='마비')
        e.start_round([actor, other])
        e.gm.snapshot('armed-native-save')
        with patch.object(Engine, 'd20', return_value=9):
            e.start_of_turn(actor, initiative_count=20)
        self.assertFalse(actor.buffs)
        self.assertEqual(actor.spec['food_consumption_receipts'][0]['benefit'],
                         {'save_condition':'마비','bonus':2})
        self.assertEqual(actor._action_history, [])
        e.gm.restore('armed-native-save', reason='bounded native save replay from observed past')
        self.assertEqual(actor.buffs[0]['id'], buff['id'])
        self.assertNotIn('food_consumption_receipts', actor.spec)
        with patch.object(Engine, 'd20', return_value=9):
            e.start_of_turn(actor, initiative_count=20)
        self.assertEqual(len(actor.spec['food_consumption_receipts']), 1)
        self.restored(e)

    def test_gluttony_shared_three_slots_and_quota_include_csv_actual_consumers(self):
        fixture = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests(); fixture.r = self.playtest
        actor = fixture.pokemon('csv-glutton', abilities=('먹보 [Playtest]',),
            items={'item/흉내허브':4,'item/회복허브':1})
        other = fixture.pokemon('glutton-stage-source')
        e = fixture.fixture(actor, other)
        for _ in range(3):
            self.intake(e, actor, 'item/흉내허브')
        self.assertEqual(FOOD.slots(actor), 3)
        before = CODEC.dump_engine(e)
        with self.assertRaisesRegex(ValueError, 'another Digestion Buff'):
            self.intake(e, actor, 'item/회복허브')
        self.assertEqual(before, CODEC.dump_engine(e))
        e.rulings.add_answer('mirror_herb', True, reason='actual optional Herb exchanges')
        e.change_stage(other, 'atk', 1)
        self.assertEqual(actor.stages['atk'], 3)
        self.assertEqual(actor.counters['lim:food_buff_consumed'], 3)
        self.assertFalse(actor.buffs)
        self.intake(e, actor, 'item/회복허브')
        buff = self.buff(actor, 'item/회복허브')
        before = CODEC.dump_engine(e)
        with self.assertRaisesRegex(ValueError, 'Gluttony scene'):
            e.consume_food_buff(actor, buff_id=buff['id'], save_condition='마비')
        self.assertEqual(before, CODEC.dump_engine(e))
        e.end_scene([actor, other])
        e.consume_food_buff(actor, buff_id=buff['id'], save_condition='마비')
        self.assertEqual(RECOVERY.saving_check(e, actor, '마비', 11, fixed=9)['food_bonus'], 2)
        self.assertEqual(actor.counters['lim:food_buff_consumed'], 1)
        self.restored(e)

    def test_gluttony_three_actual_legacy_payments_adopt_without_new_charge_then_consume_natively(self):
        from test_csv_food_legacy_reconciliation import OLD
        fixture=_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests();fixture.r=self.playtest
        actor=fixture.pokemon('legacy-csv-glutton',abilities=('먹보 [Playtest]',),items={'item/흉내허브':3})
        source=fixture.pokemon('actual-legacy-stage-source')
        e=fixture.fixture(actor,source)
        old=[OLD.consume(e,actor,actor,'item/흉내허브') for _ in range(3)]
        e=self.restored(e);actor=WORLD.actor_index(e)[actor.entity_id]
        self.assertEqual(FOOD.slots(actor),3)
        for record in old:
            e.consume_food_buff(actor,buff_id=record['id'],legacy_reason='GM verified three distinct actual Gluttony payments')
        self.assertEqual((e.elapsed_seconds,actor.spec['items']['item/흉내허브'],FOOD.slots(actor)),(0,0,3))
        self.assertEqual(len(actor.spec['stock_consumption_receipts']),3)
        e=self.restored(e);actor=WORLD.actor_index(e)[actor.entity_id];source=WORLD.actor_index(e)[source.entity_id]
        e.rulings.add_answer('mirror_herb',True,reason='actual optional exchange of reconciled Herbs')
        e.change_stage(source,'atk',1)
        self.assertEqual((actor.stages['atk'],FOOD.slots(actor),actor.counters['lim:food_buff_consumed']),(3,0,3))
        self.assertEqual(len(actor.spec['food_consumption_receipts']),3)
        self.restored(e)

    def test_mushroom_designated_entry_cannot_be_denied_by_unnerve_or_ordinary_operation(self):
        e, actor, other = self.fixture('item/다이버섯')
        self.intake(e, actor, 'item/다이버섯')
        buff = self.buff(actor, 'item/다이버섯')
        other.abilities = ['긴장감']
        for operation in ('steal','consume','deny','reuse','transfer'):
            with self.assertRaisesRegex(ValueError, 'excludes'):
                CSV.forbid_external_operation(actor, buff['id'], operation)
        before = CODEC.dump_engine(e)
        with self.assertRaisesRegex(ValueError, 'native form entry'):
            e.consume_food_buff(actor, buff_id=buff['id'], action_kind='free', action_reason='ordinary consumption')
        self.assertEqual(before, CODEC.dump_engine(e))
        e.start_round([actor, other]); e.start_of_turn(actor, initiative_count=20)
        e.enter_gigantamax(actor, source_id='item/다이버섯', reason='source explicitly excludes denial')
        self.assertFalse(actor.buffs)
        self.assertEqual(len(actor.spec['food_consumption_receipts']), 1)
        self.restored(e)

    def test_exact_stock_choice_is_rechecked_at_debit_and_physical_intake_pays_once(self):
        e, actor, other = self.fixture('item/흉내허브')
        choice = CSV.source_choice(e.r,'item/흉내허브',CLAUSES['item/흉내허브'])
        prepared = STOCK.prepare(e, actor, 'item/흉내허브', source_selection=choice)
        broken = deepcopy(prepared); broken['source_selection']['source_columns'] = [1, 3]
        before = CODEC.dump_engine(e)
        with self.assertRaisesRegex(ValueError, 'choice changed'):
            STOCK.debit(e, actor, broken)
        self.assertEqual(before, CODEC.dump_engine(e))
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests().equip(e, actor, 'csv-native-held-herb', 'item/흉내허브')
        self.intake(e, actor, 'item/흉내허브', held_selection='csv-native-held-herb')
        self.assertEqual(actor.spec['items']['item/흉내허브'], 2)
        buff = self.buff(actor, 'item/흉내허브')
        self.assertEqual(buff['item_stock']['kind'], 'held_instance')
        self.assertEqual(buff['item_stock']['instance_id'], 'csv-native-held-herb')
        e = self.restored(e); actor = WORLD.actor_index(e)[actor.entity_id]
        before = CODEC.dump_engine(e)
        with self.assertRaises(ValueError):
            self.intake(e, actor, 'item/흉내허브', held_selection='csv-native-held-herb')
        self.assertEqual(before, CODEC.dump_engine(e))

    def test_legacy_csv_restore_preserves_observation_without_fabricating_paid_common_effect(self):
        e, actor, other = self.fixture('item/흉내허브')
        row = CSV.definition(e.r, 'item/흉내허브')
        legacy = {'version':1,'next':2,'buffs':[{'id':actor.entity_id+':csv-food:1',
            'clause_id':row['clause_id'],'item_id':row['item_id'],'kind':row['kind'],
            'created_at':0,'payment':{'kind':'quantity','item_id':row['item_id'],'count':1,'selected_variant':True},
            'protected':False}],'receipts':[]}
        actor.spec[CSV.STATE] = deepcopy(legacy)
        e.gm.snapshot('legacy-observation')
        e = self.restored(e); actor = WORLD.actor_index(e)[actor.entity_id]
        self.assertEqual(actor.spec[CSV.STATE], legacy)
        self.assertFalse(actor.buffs)
        self.assertEqual(FOOD.slots(actor), 1)
        before = CODEC.dump_engine(e)
        with self.assertRaisesRegex(ValueError, 'another Digestion Buff'):
            self.intake(e, actor, 'item/흉내허브')
        with self.assertRaisesRegex(ValueError, 'one actual'):
            e.consume_food_buff(actor, buff_id=legacy['buffs'][0]['id'])
        self.assertEqual(before, CODEC.dump_engine(e))

    def test_resumable_csv_intake_and_json_query_never_pay_or_advance_twice(self):
        e, actor, other = self.fixture('item/회복허브')
        self.intake(e, actor, 'item/회복허브', resumable=True, request_id='csv-public-intake')
        self.assertEqual((e.elapsed_seconds,actor.spec['items']['item/회복허브'],len(actor.buffs)),(60,1,1))
        e = self.restored(e); actor = WORLD.actor_index(e)[actor.entity_id]
        before = CODEC.dump_engine(e)
        self.intake(e, actor, 'item/회복허브', resumable=True, request_id='csv-public-intake')
        self.assertEqual(before, CODEC.dump_engine(e))

    def test_mirror_observed_growth_uses_tier_two_yield_period_and_common_harvest(self):
        e, actor, other = self.fixture('item/흉내허브', trainer=True, count=0)
        e.gm.observe_plant(actor,plant_id='native-mirror-patch',berry='흉내허브',
            planted_at=0,last_harvest_day=None,soft_soil=True,reason='GM inspected actual existing Herb patch')
        crop = actor.spec['plants']['native-mirror-patch']['crop']
        berry = PLANTS.crop(e.r,'자뭉열매')
        self.assertEqual(crop,dict(berry,kind='herb'))
        with self.assertRaisesRegex(ValueError,'matured'):
            e.pokemon_activity(actor,'harvest_berry',plant_id='native-mirror-patch',fixed=3)
        e.advance_time(172800,[actor,other])
        result = e.pokemon_activity(actor,'harvest_berry',plant_id='native-mirror-patch',fixed=3)
        self.assertEqual(result['amount'], 2)
        self.assertEqual(actor.spec['items']['흉내허브'],2)
        with self.assertRaises(ValueError):
            e.pokemon_activity(actor,'harvest_berry',plant_id='native-mirror-patch',fixed=3)
        self.restored(e)


if __name__ == '__main__':
    unittest.main()
