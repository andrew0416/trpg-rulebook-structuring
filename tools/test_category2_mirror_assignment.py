"""F-22 cross-producer tests against native source data and staged engine modules."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if (HERE.parent / 'data').is_dir() else Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')
BASELINE = '--baseline' in sys.argv
if BASELINE:
    sys.argv.remove('--baseline')
sys.path[:0] = ([] if BASELINE else [str(HERE / 'engine')]) + [str(ROOT / 'engine'), str(ROOT / 'tools')]
import csv_item_food_contracts as CSV
import effects as FX
import effects_ext as EXT
import engine
import food_effects as FOOD
import test_category2_csv_remaining_item_contracts as FIXTURES


class MirrorAssignmentTests(unittest.TestCase):
    def fixture(self, holder_count=1):
        f = FIXTURES.RemainingCsvItemContractTests()
        f.r = engine.Rules(str(ROOT), ruleset='core')
        holders = [f.pokemon('mirror-holder-' + str(i), items={'item/흉내허브': 1})
                   for i in range(holder_count)]
        source = f.pokemon('source', moves=('move/자기암시',))
        model = f.pokemon('model')
        e = f.fixture(*holders, source, model)
        choice = CSV.definition(e.r, 'item/흉내허브')['clause_id']
        ids = [e.use_item(h, 'item/흉내허브', food_policy=choice,
                          duration_minutes=1, duration_reason='stage assignment audit')['buff_id']
               for h in holders]
        return e, holders, source, model, ids

    def assert_spent(self, holder, buff_id, stage):
        self.assertEqual(holder.stages['atk'], stage)
        self.assertNotIn(buff_id, [b['id'] for b in holder.buffs])
        receipts = holder.spec.get('food_consumption_receipts', [])
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]['producer'], 'mirror_positive_stage')

    def test_native_copy_observed(self):
        e, holders, source, model, ids = self.fixture()
        e.change_stage(model, 'atk', 2)
        e.rulings.add_answer('mirror_herb', True, reason='actual stage-copy gain')
        e.start_round([*holders, source, model])
        e.start_of_turn(source, initiative_count=20)
        e.use_move(source, model, 'move/자기암시')
        self.assertEqual(source.stages['atk'], 2)
        self.assert_spent(holders[0], ids[0], 2)
        self.assertTrue(e.validate_state()['valid'])

    def test_swap_observed_only_for_positive_actual_gain(self):
        e, holders, source, model, ids = self.fixture()
        e.change_stage(model, 'atk', 2)
        e.rulings.add_answer('mirror_herb', True, reason='actual swap gain')
        FX.h_swap_stages(e, source, model, {'swap_stages': ['atk']}, {})
        self.assertEqual((source.stages['atk'], model.stages['atk']), (2, 0))
        self.assert_spent(holders[0], ids[0], 2)
        self.assertTrue(e.validate_state()['valid'])

    def test_invert_observed_only_for_positive_actual_gain(self):
        e, holders, source, model, ids = self.fixture()
        e.change_stage(model, 'atk', -2)
        e.rulings.add_answer('mirror_herb', True, reason='actual inversion gain')
        EXT.h_invert_stages(e, source, model, {'target': 'target'}, {})
        self.assertEqual(model.stages['atk'], 2)
        self.assert_spent(holders[0], ids[0], 4)
        self.assertTrue(e.validate_state()['valid'])

    def test_decline_or_no_gain_retains_buff(self):
        e, holders, source, model, ids = self.fixture()
        e.change_stage(model, 'atk', 2)
        e.rulings.add_answer('mirror_herb', False, reason='optional reaction declined')
        EXT.h_copy_stages(e, source, model, {}, {})
        self.assertEqual(source.stages['atk'], 2)
        self.assertIsNotNone(FOOD.get_buff(holders[0], ids[0]))
        EXT.h_copy_stages(e, source, model, {}, {})
        self.assertIsNotNone(FOOD.get_buff(holders[0], ids[0]))

    def test_invalid_second_assignment_preflight_preserves_first(self):
        e, holders, source, model, ids = self.fixture()
        import combat_stage_sources as STAGES
        STAGES.add_base(model, 'fixture', 'atk', 1, source='fixture', ends='fixture')
        model.stages['atk'] = 2  # invalid source snapshot
        before = dict(source.stages)
        with self.assertRaisesRegex(ValueError, 'untracked'):
            FX.h_swap_stages(e, source, model, {'swap_stages': ['atk']}, {})
        self.assertEqual(source.stages, before)
        self.assertIsNotNone(FOOD.get_buff(holders[0], ids[0]))

    def test_two_holders_react_once_to_one_copied_gain(self):
        e, holders, source, model, ids = self.fixture(holder_count=2)
        e.change_stage(model, 'atk', 2)
        e.rulings.add_answer('mirror_herb', True, reason='each holder accepts')
        EXT.h_copy_stages(e, source, model, {}, {})
        self.assertEqual(source.stages['atk'], 2)
        for holder, buff_id in zip(holders, ids):
            self.assert_spent(holder, buff_id, 2)
        self.assertTrue(e.validate_state()['valid'])

    def test_late_reaction_failure_rolls_back_assignment_and_buff(self):
        e, holders, source, model, ids = self.fixture()
        e.change_stage(model, 'atk', 2)
        e.rulings.add_answer('mirror_herb', True, reason='accept before failed receipt')
        before = dict(source.stages)
        with patch.object(FOOD, 'remove_buff', side_effect=ValueError('failed receipt')):
            with self.assertRaisesRegex(ValueError, 'failed receipt'):
                EXT.h_copy_stages(e, source, model, {}, {})
        self.assertEqual(source.stages, before)
        self.assertIsNotNone(FOOD.get_buff(holders[0], ids[0]))
        self.assertTrue(e.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
