"""A late save error must not spend a selected one-shot bonus without a result."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from engine import Rules
import condition_recovery as RECOVERY
import csv_item_food_contracts as CSV
import effects_ext as EXT
import net_capsule as NET
import state_codec as CODEC
import test_category2_csv_remaining_item_contracts as ITEM_FIXTURE
import test_category2_fashion_item_contracts as FASHION_FIXTURE
import test_category3_net_capsule as NET_FIXTURE

ROOT = Path(__file__).resolve().parents[1]


class SaveConsumptionAtomicityTests(TestCase):
    def herb(self, engine, actor, condition):
        actor.spec['items']['item/회복허브'] = 1
        clause = CSV.definition(engine.r, 'item/회복허브')['clause_id']
        intake = engine.use_item(actor, 'item/회복허브', food_policy=clause,
                                 duration_minutes=1, duration_reason='save atomicity regression')
        engine.consume_food_buff(actor, buff_id=intake['buff_id'], save_condition=condition)
        return intake['buff_id']

    def test_recovery_herb_late_save_error_preserves_choice_and_retries_once(self):
        fixture = ITEM_FIXTURE.RemainingCsvItemContractTests()
        fixture.r = Rules(str(ROOT), ruleset='core')
        actor = fixture.pokemon('atomic-herb-holder')
        engine = fixture.fixture(actor, fixture.pokemon('atomic-herb-other'))
        buff_id = self.herb(engine, actor, '혼란')
        before = CODEC.dump_engine(engine)
        with patch.object(EXT, 'save_dc', side_effect=ValueError('late save fault')):
            with self.assertRaisesRegex(ValueError, 'late save fault'):
                RECOVERY.saving_check(engine, actor, '혼란', 10, fixed=9)
        self.assertEqual(CODEC.dump_engine(engine), before)
        self.assertTrue(any(buff['id'] == buff_id for buff in actor.buffs))
        self.assertEqual(RECOVERY.saving_check(engine, actor, '혼란', 10, fixed=9)['food_bonus'], 2)
        self.assertEqual(RECOVERY.saving_check(engine, actor, '혼란', 10, fixed=9)['food_bonus'], 0)

    def test_joint_food_and_fashion_late_error_preserves_both(self):
        FASHION_FIXTURE.FashionItemContractTests.setUpClass()
        fixture = FASHION_FIXTURE.FashionItemContractTests()
        fixture.setUp()
        item = 'item/근사한-패션-1'
        fixture.make(item)
        buff_id = self.herb(fixture.e, fixture.p, '혼란')
        fixture.combat(fixture.p, fixture.a, fixture.q)
        fixture.e.activate_fashion_item(fixture.p, item)
        before = CODEC.dump_engine(fixture.e)
        with patch.object(EXT, 'save_dc', side_effect=ValueError('late joint fault')):
            with self.assertRaisesRegex(ValueError, 'late joint fault'):
                RECOVERY.saving_check(fixture.e, fixture.p, '혼란', 10, fixed=5)
        self.assertEqual(CODEC.dump_engine(fixture.e), before)
        self.assertTrue(any(buff['id'] == buff_id for buff in fixture.p.buffs))
        first = RECOVERY.saving_check(fixture.e, fixture.p, '혼란', 10, fixed=5)
        second = RECOVERY.saving_check(fixture.e, fixture.p, '혼란', 10, fixed=5)
        self.assertEqual((first['food_bonus'], first['fashion_bonus']), (2, 4))
        self.assertEqual((second['food_bonus'], second['fashion_bonus']), (0, 0))

    def test_net_standard_late_error_preserves_herb_and_net(self):
        NET_FIXTURE.NetTests.setUpClass()
        fixture = NET_FIXTURE.NetTests()
        fixture.setUp()
        buff_id = self.herb(fixture.e, fixture.p, '네트')
        fixture.fire()
        fixture.p.budget = {'standard': 1, 'shift': 1, 'swift': 1}
        before = CODEC.dump_engine(fixture.e)
        with patch.object(EXT, 'save_dc', side_effect=ValueError('late net fault')):
            with self.assertRaisesRegex(ValueError, 'late net fault'):
                fixture.e.remove_net(fixture.p, fixed=10)
        self.assertEqual(CODEC.dump_engine(fixture.e), before)
        self.assertIsNotNone(NET.active(fixture.p))
        self.assertTrue(any(buff['id'] == buff_id for buff in fixture.p.buffs))
        outcome = fixture.e.remove_net(fixture.p, fixed=8)
        self.assertTrue(outcome['removed'])
        self.assertEqual(outcome['check']['food_bonus'], 2)
