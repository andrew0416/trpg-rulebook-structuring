"""The six named upgrades consume the existing physical vehicle contract."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
from state_codec import dump_engine, load_engine, StateCodecError
import test_category2_vehicle_native as FIX
import vehicle_native as N
import special_entities as S
import control_vehicle as CONTROL
import crafting_recipes as Q
import world_entities as W
import repair_breach as B


DEFINITIONS = {
    'structural_integrity': ('C2ADD/supp-polygon:1110', 'd6f5d8d4549e3b9c5ed37984bc925632f43738358b37173b5f25f7a8c83f4b58'),
    'armored_plating': ('C2ADD/supp-polygon:1117', '85fec26a6489333043a81076a2985d790333f524c77ef50bdedfcae08b2aa164'),
    'breach_resistance': ('C2ADD/supp-polygon:1124', 'e692f4dc2bb4751a802d7d2845e53edd31f66052195e1c22bb61dd380b7525f1'),
    'reinforced_alloys': ('C2ADD/supp-polygon:1130', '62be175afb4f99c44cd075724fec12a082b26ecf03547127999db72851fcc048'),
    'vehicle_speed': ('C2ADD/supp-polygon:1136', '76e02b0ed1fcf85854525dddad6338222718b50fac9ee94c52f1f5615bc00007'),
    'shield_generator': ('C2ADD/supp-polygon:1142', 'b93119128484a9c04824c5d72f0f8c01e954be5520ab6adc1d62399eb4f65c4d'),
}


class UpgradeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.poly = Rules(str(ROOT), ruleset='polygon')

    trainer = FIX.NativeVehicleTests.trainer
    setUp = FIX.NativeVehicleTests.setUp
    register = FIX.NativeVehicleTests.register
    snap = FIX.NativeVehicleTests.snap
    policy = FIX.NativeVehicleTests.policy
    breach = FIX.NativeVehicleTests.breach
    hit = FIX.NativeVehicleTests.hit
    start = FIX.NativeVehicleTests.start
    move = FIX.NativeVehicleTests.move

    def purchase(self, upgrade, identity='car'):
        return N.acquire_upgrade(self.e, self.a, identity, upgrade,
            request_id='installed/' + upgrade, reason='actual named source installation')

    def test_six_actual_sources_survive_json_gm_restore_and_feed_both_defenses(self):
        row = self.register(template='personal', occupied=False)
        for uid, (clause, excerpt) in DEFINITIONS.items():
            result = self.purchase(uid)
            self.assertEqual((result['definition_clause_id'], result['definition_excerpt_sha256']), (clause, excerpt))
            self.assertEqual(result, self.purchase(uid))
        self.a.custom_conditions['installed_vehicle'] = row
        self.assertEqual((row['max_hp'], row['stats']['def'], row['stats']['spd']), (100, 9, 9))
        physical = N.defend(self.e, 'car', damage_class='물리', total=40)
        self.assertEqual(self.hit(physical, event='physical-source')['shield_absorbed'], 15)
        special = N.defend(self.e, 'car', damage_class='특수', total=40)
        self.hit(special, kind='불꽃', event='special-source')
        self.assertEqual(row['hp'], 59)
        saved = self.snap(); self.e.gm.snapshot('upgrade-sources')
        self.e.gm.set_hp(self.a, value=1, reason='later actor mutation'); self.e.gm.restore('upgrade-sources')
        for engine in (self.e, load_engine(self.poly, json.loads(json.dumps(saved, ensure_ascii=False)))):
            car = engine._physical_objects['car']; actor = W.actor_index(engine)[self.a.entity_id]
            self.assertIs(actor.custom_conditions['installed_vehicle'], car)
            self.assertTrue(W.validate_world(engine)['valid']); self.assertEqual(car['hp'], 59)
            for uid, (clause, excerpt) in DEFINITIONS.items():
                result = car['native_vehicle']['upgrades']['installed/' + uid]['result']
                self.assertEqual((result['definition_clause_id'], result['definition_excerpt_sha256']), (clause, excerpt))

    def test_size_columns_and_alloy_exceptions_feed_real_damage_and_scene_shields(self):
        for template, prices, shield_hp in (
            ('personal', (1500, 5000, 3000), 20),
            ('basic', (2250, 7500, 4000), 40),
            ('large', (3000, 10000, 5000), 60),
        ):
            row = self.register(template, template, occupied=False)
            for uid, price in zip(('breach_resistance', 'reinforced_alloys', 'shield_generator'), prices):
                self.assertEqual(self.purchase(uid, template)['cost'], price)
            self.assertEqual(N.begin_scene(self.e, self.a, template)['temporary_hp'], shield_hp)
            for move_type, expected in (
                ('노말', [1, 2]), ('격투', [1, 2]), ('얼음', [1, 2]),
                ('바위', [1, 2]), ('땅', [1, 1]), ('독', [0, 1]),
                ('불꽃', [3, 2]), ('물', [1, 1]),
            ):
                result = self.hit(8, identity=template, kind=move_type, event='typed/' + move_type)
                self.assertEqual(result['type_multiplier'], expected)
            self.assertEqual(row['hp'], row['max_hp'] - max(0, 44 - shield_hp))
            remaining = N.begin_scene(self.e, self.a, template)['temporary_hp']
            self.assertEqual(remaining, max(0, shield_hp - 44))
        self.e.end_scene()
        for template, shield_hp in (('personal', 20), ('basic', 40), ('large', 60)):
            self.assertEqual(N.begin_scene(self.e, self.a, template)['temporary_hp'], shield_hp)

    def test_breach_armor_changes_real_protection_disable_and_destruction_boundaries(self):
        row = self.register(template='personal'); self.purchase('breach_resistance')
        self.assertEqual((row['breach_security'], row['breach_capacity']), (2, 5))
        breach = self.breach(); breach['single_hit_fraction'] = None
        def actual_hit(amount, event, exposed):
            return N.hit(self.e, self.a, 'car', move_type='노말', after_defense=amount,
                passenger_after_defense={self.a.entity_id: 0} if exposed else {},
                event_id=event, reason='actual armor boundary damage', breach_policy=breach)
        actual_hit(20, 'one-breach', False)
        self.assertEqual(row['breaches'], 1); self.assertTrue(B.exposure(self.e, 'car')['protected'])
        actual_hit(20, 'two-breaches', True)
        self.assertEqual(row['breaches'], 2); self.assertFalse(B.exposure(self.e, 'car')['protected'])
        actual_hit(60, 'capacity-five', True)
        self.assertEqual(row['breaches'], 5); self.assertFalse(row['destroyed'])
        self.start(); before = self.snap()
        with self.assertRaisesRegex(ValueError, 'cannot act'): self.move()
        self.assertEqual(before, self.snap())
        result = actual_hit(100, 'double-capacity-ten', True)
        self.assertEqual((row['breaches'], row['hp'], row['destroyed']), (10, -120, True))
        self.assertGreater(row['hp'], -2 * row['max_hp'])
        salvage = self.e._physical_objects[result['salvage_id']]['vehicle_salvage']
        self.assertEqual(salvage['value_fraction'], [9000, 3])

    def test_speed_installation_updates_all_existing_modes_and_actual_levitate_command(self):
        modifications = [dict(id='actual/' + mode, kind='movement', operation='add', mode=mode,
                              cost=1000, reason='explicit GM customization quote')
                         for mode in ('swim', 'levitate', 'sky')]
        row = self.register(modifications=modifications)
        self.purchase('vehicle_speed')
        view = CONTROL.body_view(row)
        self.assertEqual(view['machine_movement'], {'land': 8, 'swim': 8, 'levitate': 8, 'sky': 8})
        value = self.policy(); value['movement']['mode'] = 'levitate'
        self.start(); result = self.move(value=value)
        self.assertEqual((result['distance'], result['remaining'], self.a.pos, row['location']['cell']),
                         (2, 6, (3, 1), (3, 1)))
        self.assertEqual(self.a.budget['standard'], 0)

    def test_late_payment_failure_and_forged_price_source_or_shield_never_commit(self):
        self.register(template='personal', occupied=False); before = self.snap()
        original = Q.pay_materials
        def late_failure(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('late named installation payment')
        with patch.object(Q, 'pay_materials', side_effect=late_failure):
            with self.assertRaisesRegex(RuntimeError, 'late named'): self.purchase('structural_integrity')
        self.assertEqual(before, self.snap())
        self.purchase('shield_generator'); N.begin_scene(self.e, self.a, 'car'); saved = self.snap()
        for changed in ('cost', 'source', 'shield'):
            engine = load_engine(self.poly, deepcopy(saved)); native = engine._physical_objects['car']['native_vehicle']
            if changed == 'shield':
                native['shield']['temporary_hp'] = 21
            else:
                key = 'installed/shield_generator'; receipt = native['upgrades'][key]
                if changed == 'cost': receipt['result']['cost'] = 1
                else: receipt['result']['definition_clause_id'] = 'C2ADD/supp-polygon:1110'
                native['upgrades'][key] = N._sign({k: v for k, v in receipt.items() if k != 'sha256'})
            self.assertFalse(W.validate_world(engine)['valid'], changed)
            with self.assertRaises(StateCodecError): dump_engine(engine)
        legacy = load_engine(self.poly, deepcopy(saved)); native = legacy._physical_objects['car']['native_vehicle']
        receipt = native['upgrades']['installed/shield_generator']
        receipt['result'].pop('definition_clause_id'); receipt['result'].pop('definition_excerpt_sha256')
        native['upgrades']['installed/shield_generator'] = N._sign({k: v for k, v in receipt.items() if k != 'sha256'})
        self.assertTrue(W.validate_world(legacy)['valid']); dump_engine(legacy)


if __name__ == '__main__':
    unittest.main()
