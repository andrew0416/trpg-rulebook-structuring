"""Real old paid saves are reconciled once, then use native consumers.

Only the fixture executes the frozen D14 producer to create an authentic old
save/payment alias graph. Production intake is always the common owner.
"""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import csv_item_food_contracts as CSV
import food_effects as FOOD
import state_codec as CODEC
import consumption_execution as PAYMENTS
import world_entities as WORLD
import condition_recovery as RECOVERY
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts
import test_csv_food_common_intake as _fixture_test_csv_food_common_intake

OLD_PATH=Path(__file__).resolve().parent/'fixtures/csv_food_d14_legacy.py'
assert sha256(OLD_PATH.read_bytes()).hexdigest()=='96ad23da39f80e36f7b4191026f2b364211c6f1d60b513c8699f97670fb00879'
spec=importlib.util.spec_from_file_location('legacy_csv_food_D14_fixture',OLD_PATH)
OLD=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=OLD
spec.loader.exec_module(OLD)


class CsvFoodLegacyReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass()

    fixture=_fixture_test_csv_food_common_intake.CsvFoodCommonIntake.fixture
    restored=_fixture_test_csv_food_common_intake.CsvFoodCommonIntake.restored

    def setUp(self):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.answers.clear()
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.provider=None

    def test_original_paid_legacy_save_is_adopted_once_and_native_consumption_frees_slot(self):
        for item,other_payer in [('item/흉내허브',False),('item/회복허브',True)]:
            with self.subTest(item=item,other_payer=other_payer):
                e,payer,other=self.fixture(item)
                actor=other if other_payer else payer
                old=OLD.consume(e,payer,actor,item)
                self.assertEqual(payer.spec['items'][item],1)
                e.advance_time(90,[payer,other])
                e.gm.snapshot('original-legacy-payment')
                e=self.restored(e)
                payer,actor=WORLD.actor_index(e)[payer.entity_id],WORLD.actor_index(e)[actor.entity_id]
                current=e.elapsed_seconds
                result=e.consume_food_buff(actor,buff_id=old['id'],legacy_reason='GM verified exact original paid legacy source')
                self.assertEqual((result['observed_creation_at'],result['adopted_at']),(0,90))
                self.assertEqual((e.elapsed_seconds,payer.spec['items'][item]),(current,1))
                self.assertFalse(actor.spec[CSV.STATE]['buffs'])
                self.assertEqual(FOOD.slots(actor),1)
                self.assertEqual(len(PAYMENTS.validate(payer)),1)
                self.assertEqual(next(iter(PAYMENTS.validate(payer).values()))['outcome'],'applied')
                e=self.restored(e)
                actor=WORLD.actor_index(e)[actor.entity_id]
                if item=='item/흉내허브':
                    source=WORLD.actor_index(e)[other.entity_id]
                    e.rulings.add_answer('mirror_herb',True,reason='actual native event after legacy reconciliation')
                    e.change_stage(source,'atk',2)
                    self.assertEqual(actor.stages['atk'],2)
                else:
                    e.consume_food_buff(actor,buff_id=result['buff_id'],save_condition='마비')
                    self.assertEqual(RECOVERY.saving_check(e,actor,'마비',11,fixed=9)['food_bonus'],2)
                self.assertFalse(actor.buffs)
                self.assertEqual(FOOD.slots(actor),0)
                self.assertEqual(len(actor.spec['food_consumption_receipts']),1)
                self.restored(e)
                before=CODEC.dump_engine(e)
                with self.assertRaisesRegex(ValueError,'one actual legacy'):
                    e.consume_food_buff(actor,buff_id=old['id'],legacy_reason='cannot adopt twice')
                self.assertEqual(before,CODEC.dump_engine(e))

    def test_late_adoption_fault_rolls_back_original_payment_history_and_slot(self):
        e,actor,other=self.fixture('item/흉내허브')
        old=OLD.consume(e,actor,actor,'item/흉내허브')
        e.gm.snapshot('before-legacy-reconciliation')
        before=CODEC.dump_engine(e)
        original=FOOD.grant_buff
        observed=[]
        def fail(engine,target,*args,**options):
            buff=original(engine,target,*args,**options)
            observed.append((len(target.buffs),len(target.spec[CSV.STATE]['buffs'])))
            raise ValueError('bounded fault after actual legacy common grant')
        with patch.object(FOOD,'grant_buff',fail):
            with self.assertRaisesRegex(ValueError,'bounded fault'):
                e.consume_food_buff(actor,buff_id=old['id'],legacy_reason='verified original payment')
        self.assertEqual(observed,[(1,0)])
        self.assertEqual(before,CODEC.dump_engine(e))
        e.consume_food_buff(actor,buff_id=old['id'],legacy_reason='successful retry of original unpaid application')
        self.assertEqual(actor.spec['items']['item/흉내허브'],1)
        e.gm.restore('before-legacy-reconciliation',reason='bounded history restore')
        self.assertEqual(actor.spec[CSV.STATE]['buffs'][0]['id'],old['id'])
        self.assertFalse(actor.buffs)
        e.consume_food_buff(actor,buff_id=old['id'],legacy_reason='same observed past restored')
        self.assertEqual(len(actor.spec[CSV.STATE]['receipts']),2)
        self.assertEqual(len(PAYMENTS.validate(actor)),1)

    def test_forged_payment_alias_and_overcapacity_legacy_require_explicit_gm_reconciliation(self):
        for broken in ('alias','overcapacity'):
            with self.subTest(broken=broken):
                e,actor,other=self.fixture('item/흉내허브')
                old=OLD.consume(e,actor,actor,'item/흉내허브')
                if broken=='alias':
                    row=actor.spec[CSV.STATE]['buffs'][0]
                    row['payment']=deepcopy(row['payment'])
                else:
                    OLD.consume(e,actor,actor,'item/흉내허브')
                e=self.restored(e);actor=WORLD.actor_index(e)[actor.entity_id]
                before=CODEC.dump_engine(e)
                with self.assertRaisesRegex(ValueError,'GM.*reconcil'):
                    e.consume_food_buff(actor,buff_id=old['id'],legacy_reason='must not invent paid provenance or capacity')
                self.assertEqual(before,CODEC.dump_engine(e))

    def test_history_only_legacy_stays_history_and_adopted_source_cannot_be_rewritten(self):
        e,actor,other=self.fixture('item/회복허브')
        old=OLD.consume(e,actor,actor,'item/회복허브')
        OLD.prepare_save(e,actor,old['id'],'마비')
        self.assertEqual(OLD.saving_bonus(e,actor,'마비'),2)
        history=deepcopy(actor.spec[CSV.STATE])
        e=self.restored(e);actor=WORLD.actor_index(e)[actor.entity_id]
        self.assertEqual(actor.spec[CSV.STATE],history)
        self.assertEqual((FOOD.slots(actor),actor.buffs),(0,[]))
        with self.assertRaisesRegex(ValueError,'one actual legacy'):
            e.consume_food_buff(actor,buff_id=old['id'],legacy_reason='history does not create a second effect')
        e,actor,other=self.fixture('item/흉내허브')
        old=OLD.consume(e,actor,actor,'item/흉내허브')
        e.consume_food_buff(actor,buff_id=old['id'],legacy_reason='verified source observation')
        actor.spec[CSV.STATE]['receipts'][-1]['observation']['clause_id']='C2CSV/inventory:91:7'
        with self.assertRaisesRegex(ValueError,'original source observation'):
            CSV.validate_world(e,WORLD.actor_index(e))
        with self.assertRaises(CODEC.StateCodecError):
            self.restored(e)


if __name__=='__main__':
    unittest.main()
