"""Real food/medicine admission, exact-instance recovery and both restorations."""
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'engine') not in sys.path:
    sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_item_stock as FIX
import environmental_item_state as ENV
import food_effects as FOOD
import state_codec as CODEC


class EnvironmentalItemTests(unittest.TestCase):
    setUpClass = classmethod(FIX.ItemStockTests.setUpClass.__func__)
    setUp = FIX.ItemStockTests.setUp
    add = FIX.ItemStockTests.add
    held = FIX.ItemStockTests.held
    eat = FIX.ItemStockTests.eat
    snap = FIX.ItemStockTests.snap
    restored = FIX.ItemStockTests.restored

    def observe(self, uid='berry', event='cold', **options):
        return self.e.gm.observe_environmental_item(
            self.p, uid, event_id=event, condition='frozen',
            source='move/눈보라', reason='GM observed this exposed physical item frozen', **options)

    def thaw(self, uid='berry', event='cold'):
        return self.e.gm.recover_environmental_item(
            self.p, uid, event_id=event, end='thaw', reason='GM observed actual thawing')

    def test_protected_default_and_exact_selected_instance(self):
        self.held(self.p, '오랭열매', 'berry')
        self.observe()  # No observed exposure is protected, not inferred from a hit.
        self.eat(self.p)
        self.assertIn('consumed', self.e._physical_objects['berry'])
        self.held(self.a, '맛있는물', 'water')
        before = self.snap()
        with self.assertRaises(ValueError):
            self.observe('water', exposed=True)  # Another holder cannot be selected.
        self.assertEqual(self.snap(), before)

    def test_actual_food_block_is_atomic_and_recovery_allows_consumption(self):
        self.held(self.p, '오랭열매', 'berry')
        self.observe(exposed=True)
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'environmentally unusable'):
            self.eat(self.p)
        self.assertEqual(self.snap(), before)
        self.thaw()
        self.eat(self.p)
        self.assertIn('consumed', self.e._physical_objects['berry'])

    def test_actual_medicine_blocks_before_payment_and_uses_only_thawed_instance(self):
        self.held(self.a, '상처약', 'potion')
        self.p.hp = 1
        self.e.gm.observe_environmental_item(
            self.a, 'potion', event_id='potion-cold', condition='frozen',
            source='move/눈보라', reason='GM observed exposed potion frozen', exposed=True)
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'environmentally unusable'):
            self.e.use_item(self.a, '상처약', self.p, held_selection='potion')
        self.assertEqual(self.snap(), before)
        self.e.gm.recover_environmental_item(
            self.a, 'potion', event_id='potion-cold', end='thaw', reason='actual potion thawed')
        self.e.use_item(self.a, '상처약', self.p, held_selection='potion')
        self.assertGreater(self.p.hp, 1)
        self.assertIn('consumed', self.e._physical_objects['potion'])

    def test_two_sources_recover_independently_and_replay_cannot_refresh(self):
        self.held(self.p, '오랭열매', 'berry')
        first = self.observe(exposed=True)
        self.assertEqual(first, self.observe(exposed=True))
        self.e.gm.observe_environmental_item(
            self.p, 'berry', event_id='water', condition='electrical_failure',
            source='GM observed environmental event', exposed=True,
            reason='independent source adapter observation')
        self.thaw()
        self.assertIsNotNone(self.observe(exposed=True)['released'])
        with self.assertRaisesRegex(ValueError, 'environmentally unusable'):
            self.eat(self.p)
        before = self.snap()
        with self.assertRaises(ValueError):
            self.e.gm.recover_environmental_item(
                self.p, 'berry', event_id='water', end='thaw', reason='wrong recovery')
        self.assertEqual(self.snap(), before)
        self.e.gm.recover_environmental_item(
            self.p, 'berry', event_id='water', end='repair', reason='actual source-approved repair')
        self.eat(self.p)

    def test_json_and_gm_rewind_preserve_block_and_recovery(self):
        self.held(self.p, '오랭열매', 'berry')
        self.observe(exposed=True)
        snapshot = self.e.gm.snapshot()
        loaded = self.restored()
        p = next(x for x in loaded.gm.everyone if x.entity_id == self.p.entity_id)
        with self.assertRaisesRegex(ValueError, 'environmentally unusable'):
            loaded.use_item(p, '오랭열매', held_selection='berry', duration_minutes=1,
                            duration_reason='actual food interval')
        self.thaw()
        self.assertTrue(self.e.validate_state()['valid'])
        self.e.gm.restore(snapshot)
        with self.assertRaisesRegex(ValueError, 'environmentally unusable'):
            self.eat(self.p)
        self.thaw()
        self.eat(self.p)

    def test_tampered_block_fails_validation_and_export(self):
        self.held(self.p, '오랭열매', 'berry')
        self.observe(exposed=True)
        state = CODEC.dump_engine(self.e)
        row = self.e._physical_objects['berry'][ENV.FIELD]['cold']
        row['exposed'] = False
        self.assertFalse(self.e.validate_state()['valid'])
        with self.assertRaises(ValueError):
            self.e.export_state()
        CODEC.load_engine(self.r, json.loads(json.dumps(state)))

    def test_changed_event_and_late_food_failure_leave_all_state_unchanged(self):
        self.held(self.p, '오랭열매', 'berry')
        self.observe(exposed=True)
        before = self.snap()
        with self.assertRaises(ValueError):
            self.observe(exposed=False)
        self.assertEqual(self.snap(), before)
        self.thaw()
        before = self.snap()
        with patch.object(FOOD, 'grant_buff', side_effect=ValueError('late native failure')):
            with self.assertRaises(ValueError):
                self.eat(self.p)
        self.assertEqual(self.snap(), before)


if __name__ == '__main__':
    unittest.main()
