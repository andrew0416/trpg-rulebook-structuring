"""Native regression for the exact Cannon identity and ordinary weapon permissions."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]

import csv_item_physical_contracts as CANNON
import optional_weapon_framework as WEAPON
import state_codec
import items as ITEMS
import turn as TURN
from engine import Engine, Rules
import weapon_actions as ACTIONS
import test_category2_csv_remaining_item_contracts as FIX


class CannonWeaponRepair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.RemainingCsvItemContractTests.setUpClass()
        cls.f = FIX.RemainingCsvItemContractTests()

    def fixture(self, *, profile):
        actor = self.f.trainer('weapon-cannon-' + str(profile))
        actor.spec['skills']['전투'] = '달인'
        target = self.f.pokemon('weapon-cannon-target')
        actor.pos = (0, 0)
        target.pos = (8, 0)
        engine = self.f.fixture(actor, target)
        uid = 'repair/cannon-' + str(profile)
        self.f.physical(engine, actor, uid, 'item/몬스터볼-캐논')
        if profile:
            WEAPON.observe_weapon(engine, actor, uid,
                name=engine.r.items_mech['item/몬스터볼-캐논']['name'],
                kind='장거리 사격무기', grade='좋음', arcane=False, metal=False,
                moves=('move/불스아이', 'move/치명적-일격'),
                reason='GM selected actual good ranged weapon form and legal moves')
        ITEMS.register_item(engine, actor, 'item/몬스터볼-캐논', source_instance_id=uid)
        return engine, actor, target, uid

    def test_actual_profile_grants_both_tiers_and_native_move_then_revokes(self):
        engine, actor, target, uid = self.fixture(profile=True)
        row = next(v for v in actor._item_reg.values() if v['instance_id'] == uid)
        key = row['cannon_weapon_key']
        self.assertEqual(row['slots'], ['주요손', '반대손'])
        self.assertEqual(actor.custom_conditions['equipped_weapons'][key]['available_moves'][1:],
                         ['move/불스아이', 'move/치명적-일격'])
        self.assertIn('move/치명적-일격', actor.moves)
        self.assertEqual(ACTIONS.prepare(engine, actor, engine.r.move('move/치명적-일격'), uid)
                         ['_weapon_attack']['key'], key)
        engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
        with patch.object(engine, 'd20', return_value=18):
            engine.use_move(actor, target, 'move/치명적-일격', weapon_id=uid, set_damage=True)
        self.assertLess(target.hp, target.base_max_hp)
        self.assertTrue(engine.validate_state()['valid'])
        restored = Engine.import_state(engine.r, json.loads(json.dumps(engine.export_state())))
        copy_actor = next(c for c in restored.everyone if c.entity_id == actor.entity_id)
        self.assertIn('move/치명적-일격', copy_actor.moves)
        ITEMS.unregister_item(engine, actor, 'item/몬스터볼-캐논')
        self.assertNotIn('move/치명적-일격', actor.moves)
        self.assertNotIn('move/불스아이', actor.moves)
        self.assertFalse(actor.custom_conditions.get('equipped_weapons'))
        self.assertTrue(engine.validate_state()['valid'])

    def test_unconfigured_item_keeps_native_cannon_and_one_weapon_identity(self):
        engine, actor, _, uid = self.fixture(profile=False)
        row = next(v for v in actor._item_reg.values() if v['instance_id'] == uid)
        self.assertIn(row['cannon_weapon_key'], actor.custom_conditions['equipped_weapons'])
        self.assertEqual(len(actor.custom_conditions['equipped_weapons']), 1)
        with self.assertRaisesRegex(ValueError, 'only Poke Ball and Pester Ball'):
            CANNON.cannon_profile(engine, actor, uid, projectile='sludge_bomb')
        self.assertTrue(engine.validate_state()['valid'])
        Engine.import_state(engine.r, json.loads(json.dumps(engine.export_state())))
        ITEMS.unregister_item(engine, actor, 'item/몬스터볼-캐논')
        self.assertFalse(actor.custom_conditions.get('equipped_weapons'))
        self.assertTrue(engine.validate_state()['valid'])

    def test_pre_repair_save_shape_migrates_once_and_remains_unregistrable_after_removal(self):
        payload = json.loads(subprocess.check_output(
            [sys.executable, '-B', '-X', 'utf8', str(HERE / 'legacy_cannon_snapshot.py')], text=True))
        restored = Engine.import_state(Rules(str(ROOT), ruleset='core'), payload)
        actor = next(c for c in restored.everyone if c.name == 'legacy-cannon-owner')
        row = next(v for v in actor._item_reg.values() if v['item_id'] == 'item/몬스터볼-캐논')
        self.assertIn(row['cannon_weapon_key'], actor.custom_conditions['equipped_weapons'])
        self.assertTrue(restored.validate_state()['valid'])
        second = Engine.import_state(restored.r, json.loads(json.dumps(restored.export_state())))
        copy_actor = next(c for c in second.everyone if c.entity_id == actor.entity_id)
        self.assertEqual(len(copy_actor.custom_conditions['equipped_weapons']), 1)
        ITEMS.unregister_item(second, copy_actor, 'item/몬스터볼-캐논')
        self.assertFalse(copy_actor.custom_conditions.get('equipped_weapons'))

    def test_disarm_and_drop_select_one_actual_item_and_revoke_both_grants(self):
        engine, actor, _, uid = self.fixture(profile=True)
        candidates = [row for row in ITEMS.equipment_options(actor, ('held', '주요손', '반대손'))
                      if row.get('instance_id') == uid]
        self.assertEqual(len(candidates), 1)
        self.assertNotIn('weapon_key', candidates[0])
        self.assertEqual(TURN.disarm_equipment(engine, actor),
                         (next(iter(actor._item_reg)), 'item', candidates[0]['name']))
        dropped = ITEMS.drop_equipment(engine, actor, [uid],
            slots=('held', '주요손', '반대손'), source='repair/regression')
        self.assertEqual(dropped['dropped'][0]['instance_id'], uid)
        self.assertFalse(actor.custom_conditions.get('equipped_weapons'))
        self.assertFalse(actor._item_reg)
        self.assertNotIn('move/치명적-일격', actor.moves)
        self.assertTrue(engine.validate_state()['valid'])

    def test_wrong_identity_unqualified_move_and_foreign_owner_cannot_observe_cannon(self):
        actor = self.f.trainer('cannon-low-rank')
        stranger = self.f.trainer('cannon-foreign-owner')
        engine = self.f.fixture(actor, stranger)
        uid = 'repair/cannon-rejection'
        self.f.physical(engine, actor, uid, 'item/몬스터볼-캐논')
        name = engine.r.items_mech['item/몬스터볼-캐논']['name']
        choice = dict(name=name, kind='장거리 사격무기', grade='좋음',
                      arcane=False, metal=False, moves=('move/치명적-일격',), reason='test')
        with self.assertRaises(ValueError):
            WEAPON.observe_weapon(engine, stranger, uid, **choice)
        with self.assertRaises(ValueError):
            WEAPON.observe_weapon(engine, actor, uid, **dict(choice, grade='간단'))
        with self.assertRaises(ValueError):
            WEAPON.observe_weapon(engine, actor, uid, **choice)
        self.assertNotIn(WEAPON.PROFILE, engine._physical_objects[uid])
        ITEMS.register_item(engine, actor, 'item/몬스터볼-캐논', source_instance_id=uid)
        self.assertNotIn('move/치명적-일격', actor.moves)
        self.assertTrue(engine.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
