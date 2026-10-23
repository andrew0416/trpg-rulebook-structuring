"""Observed cold/fire effects consume actual physical states and default protection."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'engine') not in sys.path:
    sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_item_stock as FIX
import environmental_attacks as A
import items as I
import world_entities as W
import held_equipment as H


class EnvironmentalAttackTests(unittest.TestCase):
    setUpClass = classmethod(FIX.ItemStockTests.setUpClass.__func__)
    setUp = FIX.ItemStockTests.setUp
    add = FIX.ItemStockTests.add
    held = FIX.ItemStockTests.held
    snap = FIX.ItemStockTests.snap
    restored = FIX.ItemStockTests.restored

    def observe(self, uid, material, **options):
        defaults = dict(event_id='attack:' + uid, material=material,
                        move_id='move/눈보라' if material == 'liquid_medicine' else 'move/화염방사',
                        reason='GM observed actual attack, material and storage exposure')
        defaults.update(options)
        return self.e.gm.observe_environmental_attack(self.a, uid, **defaults)

    def test_default_holster_protects_medicine_and_herb_and_changed_replay_is_atomic(self):
        for name, uid, material in [('상처약', 'potion', 'liquid_medicine'),
                                    ('힘의가루', 'herb', 'herb')]:
            self.held(self.a, name, uid)
            row = self.observe(uid, material)
            self.assertEqual(row['outcome'], 'protected')
            before = self.snap()
            with self.assertRaises(ValueError):
                self.observe(uid, material, exposed=True)
            self.assertEqual(self.snap(), before)
            self.p.hp = 1
            self.e.use_item(self.a, name, self.p, held_selection=uid)
            self.assertGreater(self.p.hp, 1)
            self.assertEqual(row, self.observe(uid, material))

    def test_frozen_potion_blocks_native_medicine_until_thaw_across_both_restorations(self):
        self.held(self.a, '상처약', 'potion')
        self.p.hp = 1
        row = self.observe('potion', 'liquid_medicine', exposed=True)
        saved = self.e.gm.snapshot()
        loaded = self.restored()
        trainer = next(x for x in loaded.gm.everyone if x.entity_id == self.a.entity_id)
        target = next(x for x in loaded.gm.everyone if x.entity_id == self.p.entity_id)
        with self.assertRaisesRegex(ValueError, 'environmentally unusable'):
            loaded.use_item(trainer, '상처약', target, held_selection='potion')
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'environmentally unusable'):
            self.e.use_item(self.a, '상처약', self.p, held_selection='potion')
        self.assertEqual(self.snap(), before)
        self.e.gm.recover_environmental_item(self.a, 'potion', event_id='environmental-attack:attack:potion',
                                           end='thaw', reason='liquid actually thawed')
        self.e.use_item(self.a, '상처약', self.p, held_selection='potion')
        self.assertGreater(self.p.hp, 1)
        self.assertEqual(row, self.observe('potion', 'liquid_medicine', exposed=True))
        self.e.gm.restore(saved)
        with self.assertRaisesRegex(ValueError, 'environmentally unusable'):
            self.e.use_item(self.a, '상처약', self.p, held_selection='potion')

    def test_burning_herb_releases_equipment_and_apricorn_keeps_real_remnant(self):
        self.held(self.a, '힘의가루', 'herb')
        row = self.observe('herb', 'herb', exposed=True)
        self.assertEqual(row['outcome'], 'destroyed')
        self.assertFalse(H.entries(self.a))
        with self.assertRaises(ValueError):
            self.e.use_item(self.a, '힘의가루', self.p, held_selection='herb')
        with self.assertRaises(ValueError):
            I.equip_held(self.e, self.a, '힘의가루', source_instance_id='herb')
        W.register_object(self.e, 'apricorn', location={'kind': 'unknown'},
                          owner_id=self.a.entity_id, weight_kg=0.1,
                          reason='actual uncatalogued raw apricorn, not quantity inventory')
        self.e.gm.set_carried_objects(self.a, [{'id': 'apricorn', 'weight_kg': 0.1}],
                                     'GM observed actual raw apricorn in pocket')
        protected = self.observe('apricorn', 'apricorn')
        self.assertEqual(protected['outcome'], 'protected')
        self.observe('apricorn', 'apricorn', event_id='exposed-fire', exposed=True)
        obj = self.e._physical_objects['apricorn']
        self.assertTrue(W.physical_lifecycle(obj)['destroyed'])
        self.assertEqual(obj['carrier_id'], self.a.entity_id)
        with self.assertRaises(ValueError):
            W.require_usable_object(obj)
        loaded = self.restored()
        trainer = next(x for x in loaded.gm.everyone if x.entity_id == self.a.entity_id)
        self.assertEqual(row, loaded.gm.observe_environmental_attack(
            trainer, 'herb', event_id='attack:herb', move_id='move/화염방사', material='herb',
            reason=row['reason'], exposed=True))
        self.assertTrue(loaded.validate_state()['valid'])

    def test_invalid_move_holder_and_late_destruction_failure_do_not_change_state(self):
        self.held(self.a, '힘의가루', 'herb')
        before = self.snap()
        with self.assertRaises(ValueError):
            self.observe('herb', 'herb', move_id='move/몸통박치기', exposed=True)
        self.assertEqual(self.snap(), before)
        with self.assertRaises(ValueError):
            self.e.gm.observe_environmental_attack(self.p, 'herb', event_id='wrong-holder',
                move_id='move/화염방사', material='herb', reason='wrong holder', exposed=True)
        self.assertEqual(self.snap(), before)
        with patch.object(W, 'finish_physical_use', side_effect=ValueError('late destruction failure')):
            with self.assertRaises(ValueError):
                self.observe('herb', 'herb', exposed=True)
        self.assertEqual(self.snap(), before)

    def test_tampered_environmental_evidence_is_rejected_by_world_and_export(self):
        self.held(self.a, '힘의가루', 'herb')
        self.observe('herb', 'herb', exposed=True)
        obj = self.e._physical_objects['herb']
        original = deepcopy(obj)
        obj['destroyed']['environmental_event_id'] = 'different'
        self.assertFalse(self.e.validate_state()['valid'])
        with self.assertRaises(ValueError):
            self.e.export_state()
        obj.clear(); obj.update(original)
        obj[A.FIELD]['attack:herb']['exposed'] = False
        self.assertFalse(self.e.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
