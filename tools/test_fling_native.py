"""Source-only Fling native acceptance candidates; deliberately not executed."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
import book_survivalist_fixture as FIX
import fling_move as FLING
import physical_hands as HANDS
import world_entities as W
import capability_actions as CAP
import optional_weapon_framework as WEAPONS
import state_codec as CODEC


class FlingNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        old = self.rules.rulings
        self.rules.rulings = deepcopy(old)
        self.addCleanup(setattr, self.rules, 'rulings', old)
        world = FIX.scene(self.rules, feats=())
        self.e, self.a, self.t = [world[k] for k in ('engine', 'trainer', 'foe')]
        self.e.gm.set_move(self.a, FLING.SOURCE, reason='actual acquired Fling fixture')
        self.e.gm.set_position(self.t, (3, 3), reason='actual Fling target')
        self.e.gm.set_types(self.t, ['물'], reason='nonimmune actual target')
        FIX.battle(self.e, self.a)

    def hand(self, uid='fixture/object', rule=None, hand='주요손'):
        W.register_object(self.e, uid, location=W.location_of(self.a), reason='actual existing fixture object',
            weight_kg=.1, kind='item_instance' if rule else 'physical_object', item_rule_id=rule, owner_id=self.a.entity_id)
        CAP.set_carried(self.e, self.a, [*self.a.spec.get('_carried_load', {}).get('objects', []),
            {'id': uid, 'weight_kg': .1}], 'actual fixture physical possession')
        HANDS.observe(self.e, self.a, uid, hand=hand, reason='actual object gripped')
        return uid

    def cast(self, uid, *, face=20, **options):
        FLING.declare(self.e, self.a, self.t, uid, **options)
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.use_move_on(self.a, self.t, FLING.SOURCE, self.e.everyone, set_damage=True)

    def launch(self):
        return next(row['fling_launch'] for row in self.e._move_completions.values() if 'fling_launch' in row)

    def test_other_real_object_uses_db6_native_cost_and_moves_actual_body(self):
        uid = self.hand()
        hp = self.t.hp
        self.cast(uid)
        self.assertLess(self.t.hp, hp)
        self.assertEqual(self.a.move_uses[FLING.SOURCE], 1)
        self.assertEqual(self.a.budget['standard'], 0)
        self.assertEqual(self.launch()['plan']['damage_base'], 6)
        self.assertEqual(HANDS.occupied(self.a), set())
        self.assertNotIn('carrier_id', self.e._physical_objects[uid])
        self.assertEqual(W.location_of(self.e._physical_objects[uid]), {'kind': 'unknown'})
        self.assertEqual(self.e._physical_objects[uid]['owner_id'], self.a.entity_id)

    def test_miss_still_throws_without_consuming_medicine_or_healing(self):
        uid = self.hand(rule='item/상처약')
        before = self.t.hp
        self.cast(uid, face=1)
        self.assertEqual(self.t.hp, before)
        self.assertNotIn('consumed', self.e._physical_objects[uid])
        self.assertEqual(self.launch()['status'], 'miss')
        self.assertEqual(self.a.move_uses[FLING.SOURCE], 1)
        self.assertFalse(HANDS.occupied(self.a))

    def test_medicine_hit_consumes_actual_body_without_damage_or_target_debt(self):
        uid = self.hand(rule='item/상처약')
        self.e.lose_hp(self.t, 20, source='gm/fixture-injury')
        before = self.t.hp
        target_budget = deepcopy(self.t.budget)
        target_history = deepcopy(self.t._action_history)
        self.cast(uid)
        self.assertGreater(self.t.hp, before)
        self.assertIn('consumed', self.e._physical_objects[uid])
        self.assertEqual(self.t.budget, target_budget)
        self.assertEqual(self.t._action_history, target_history)
        receipts = self.a.spec['stock_consumption_receipts']
        self.assertEqual(len(receipts), 1)
        self.assertEqual(next(iter(receipts.values()))['item_stock']['instance_id'], uid)
        self.assertEqual(self.launch()['plan']['category'], 'consumable')
        self.assertIn('consumer_result', self.launch())

    def test_poison_and_fire_native_status_after_damage(self):
        for rule, status in (('item/맹독구슬', '독'), ('item/화염구슬', '화상')):
            with self.subTest(rule=rule):
                self.setUp()
                uid = self.hand(rule=rule)
                before = self.t.hp
                self.cast(uid)
                self.assertLess(self.t.hp, before)
                self.assertIn(status, self.t.conditions)
                self.assertEqual(self.launch()['plan']['damage_base'], 3)
                self.assertNotIn('consumed', self.e._physical_objects[uid])

    def test_ball_capture_variants_share_one_native_move_launch(self):
        for edition, requested, expected in (('core_105', False, 0), ('core_105', True, 1), ('korean', False, 1)):
            with self.subTest(edition=edition, requested=requested):
                self.setUp()
                uid = self.hand(rule='item/몬스터볼')
                before = self.t.hp
                stock = deepcopy(self.a.spec.get('items', {}))
                self.cast(uid, edition=edition, capture=requested,
                          capture_options={'capture_source': 'core_105', 'fixed_capture': 100})
                attempts = self.a.spec.get('capture_attempts', {})
                self.assertEqual(len(attempts), expected)
                self.assertLess(self.t.hp, before)
                self.assertEqual(self.a.spec.get('items', {}), stock)
                self.assertEqual(self.a.budget['standard'], 0)
                self.assertEqual(self.a.move_uses[FLING.SOURCE], 1)
                self.assertEqual(self.launch()['plan']['damage_base'], 3)
                if expected:
                    attempt = next(iter(attempts.values()))
                    self.assertEqual(attempt['physical_instance_id'], uid)
                    self.assertEqual(attempt['accuracy_natural'], 20)
                    self.assertEqual(attempt['move_origin']['move_id'], FLING.SOURCE)
                    self.assertEqual(self.launch()['capture_result'], attempt['captured'])

    def test_table_held_rare_lagging_uses_source_classification(self):
        for rule, category, db in (('item/불꽃의돌', 'held', 7), ('item/분홍진주', 'rare', 10),
                ('item/검은철구', 'lagging', 12), ('item/느림보꼬리', 'lagging', 12)):
            with self.subTest(rule=rule):
                self.setUp()
                uid = self.hand(rule=rule)
                FLING.declare(self.e, self.a, self.t, uid)
                move = FLING.prepare_move(self.e, self.a, self.t, self.rules.move(FLING.SOURCE))
                self.assertEqual((move['_fling']['category'], move['damage_base']), (category, db))

    def test_rare_ineligible_texts_stay_selectable(self):
        uid = self.hand(rule='item/금속파우더')
        FLING.declare(self.e, self.a, self.t, uid, edition='core_105')
        move = FLING.prepare_move(self.e, self.a, self.t, self.rules.move(FLING.SOURCE))
        self.assertEqual(move['damage_base'], 7)
        before = deepcopy((CODEC.dump_engine(self.e), self.e.rng.getstate()))
        with self.assertRaisesRegex(ValueError, 'suitable user'):
            FLING.declare(self.e, self.a, self.t, uid, edition='korean')
        self.assertEqual(before, (CODEC.dump_engine(self.e), self.e.rng.getstate()))

    def test_unobserved_typed_item_refuses_before_cost_then_uses_actual_type(self):
        uid = self.hand(rule='item/타입부스터')
        with self.assertRaisesRegex(ValueError, 'actual generic item type'):
            FLING.declare(self.e, self.a, self.t, uid)
        self.assertNotIn(FLING.SOURCE, self.a.move_uses)
        FLING.observe_type(self.e, self.a, uid, '독', reason='actual Poison Booster')
        self.cast(uid)
        self.assertIn('독', self.t.conditions)

    def test_missing_or_inventory_only_item_cannot_pay_fling(self):
        before = deepcopy((self.a.budget, self.a.spec, self.e.rng.getstate()))
        with self.assertRaisesRegex(ValueError, 'existing physical object'):
            FLING.declare(self.e, self.a, self.t, 'fictional trash')
        self.assertEqual(before, (self.a.budget, self.a.spec, self.e.rng.getstate()))
        uid = self.hand()
        CAP.set_carried(self.e, self.a, [], 'actual object released')
        self.assertFalse(HANDS.occupied(self.a))
        with self.assertRaisesRegex(ValueError, 'actual hand or held'):
            FLING.declare(self.e, self.a, self.t, uid)

    def test_occupied_hand_cannot_be_double_booked(self):
        self.hand()
        uid = 'fixture/weapon'
        W.register_object(self.e, uid, location=W.location_of(self.a), reason='actual weapon',
            weight_kg=1, owner_id=self.a.entity_id)
        WEAPONS.observe_weapon(self.e, self.a, uid, name='test knife', kind='소형 근접무기',
            grade='조잡', arcane=False, metal=True, reason='actual weapon profile')
        with self.assertRaisesRegex(ValueError, 'occupied'):
            WEAPONS.equip(self.e, self.a, uid)

    def test_native_weapon_throws_once_preserves_weapon_damage_and_fling_ac(self):
        uid = 'fixture/weapon'
        W.register_object(self.e, uid, location=W.location_of(self.a), reason='actual weapon',
            weight_kg=1, owner_id=self.a.entity_id)
        WEAPONS.observe_weapon(self.e, self.a, uid, name='test knife', kind='소형 근접무기',
            grade='조잡', arcane=False, metal=True, reason='actual weapon profile')
        key = WEAPONS.equip(self.e, self.a, uid)
        FLING.declare(self.e, self.a, self.t, uid)
        move = FLING.prepare_move(self.e, self.a, self.t, self.rules.move(FLING.SOURCE))
        self.assertEqual(move['ac'], 2)
        self.assertEqual(move['_weapon_attack']['accuracy_bonus'], 0)
        self.assertEqual(move['_weapon_attack']['range']['origin'], 6)
        with patch.object(Engine, 'd20', return_value=20):
            self.e.use_move_on(self.a, self.t, FLING.SOURCE, self.e.everyone, set_damage=True)
        self.assertNotIn(key, self.a.custom_conditions.get('equipped_weapons', {}))
        self.assertEqual(self.launch()['plan']['category'], 'weapon')
        self.assertFalse(self.e._physical_objects[uid].get('equipped_by'))

    def test_manual_effect_cannot_borrow_fling_status_or_consume_an_object(self):
        uid = self.hand(rule='item/맹독구슬')
        FLING.declare(self.e, self.a, self.t, uid)
        before = deepcopy((self.a.spec, self.t.conditions, self.e._physical_objects))
        result = self.e.apply_effect(self.a, self.t, FLING.RESULT, 20, True, 0, FLING.SOURCE)
        self.assertEqual(tuple(result), (0, 1))
        self.assertEqual(before, (self.a.spec, self.t.conditions, self.e._physical_objects))

    def test_unissued_capture_or_consumer_admission_rejected(self):
        for consumer in (FLING.consume_capture_admission, FLING.consume_item_admission):
            with self.assertRaisesRegex(ValueError, 'unused Fling effect admission'):
                consumer(self.e, self.a, self.t, 'forged', {})

    def test_downstream_consumer_failure_rolls_back_native_cost_and_projectile(self):
        import fling_consumables as CONSUMER
        uid = self.hand(rule='item/상처약')
        FLING.declare(self.e, self.a, self.t, uid)
        before = deepcopy((CODEC.dump_engine(self.e), self.e.rng.getstate()))
        with patch.object(CONSUMER, 'consume', side_effect=ValueError('actual downstream failure')):
            with patch.object(Engine, 'd20', return_value=20):
                with self.assertRaisesRegex(ValueError, 'native Fling effect failed'):
                    self.e.use_move_on(self.a, self.t, FLING.SOURCE, self.e.everyone, set_damage=True)
        self.assertEqual(before, (CODEC.dump_engine(self.e), self.e.rng.getstate()))

    def test_hand_observation_survives_native_save_restore(self):
        uid = self.hand()
        self.e, index = FIX.restore(self.rules, self.e)
        self.a, self.t = index[self.a.entity_id], index[self.t.entity_id]
        self.assertEqual(HANDS.inspect(self.e, self.a, uid)['hand'], '주요손')
        self.cast(uid)
        self.assertEqual(self.launch()['status'], 'hit')


if __name__ == '__main__':unittest.main()



