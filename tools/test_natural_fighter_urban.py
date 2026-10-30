"""Unexecuted Natural Fighter urban joins to the complete native Fling path."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_natural_fighter_native as BASE
from engine import Engine, Rules
import action_points as AP
import book_survivalist_fixture as FIX
import capability_actions as CAP
import fling_move as FLING
import items as ITEMS
import natural_fighter as NF
import passive_events as PASSIVE
import physical_hands as HANDS
import state_grants as G
import survivalist_class as SC
import turn as TURN
import world_entities as W


class NaturalFighterUrbanTests(unittest.TestCase):
    scene = BASE.NaturalFighterTests.scene
    next_round = BASE.NaturalFighterTests.next_round
    snap = BASE.NaturalFighterTests.snap
    reject_unchanged = BASE.NaturalFighterTests.reject_unchanged

    @classmethod
    def setUpClass(cls):cls.rules = Rules(str(ROOT), ruleset='all')

    def setUp(self):
        old = self.rules.rulings
        self.rules.rulings = deepcopy(old)
        self.addCleanup(setattr, self.rules, 'rulings', old)

    def restore(self):
        self.e, index = FIX.restore(self.rules, self.e)
        self.t, self.p, self.foe, self.actor = [index[a.entity_id] for a in (self.t, self.p, self.foe, self.actor)]

    def object(self, uid='urban/projectile', rule=None, *, holder=None, held=True):
        holder = holder or self.actor
        W.register_object(self.e, uid, location=W.location_of(holder), reason='actual urban projectile fixture',
            weight_kg=.1, owner_id=self.t.entity_id, kind='item_instance' if rule else 'physical_object', item_rule_id=rule)
        CAP.set_carried(self.e, holder, [*holder.spec.get('_carried_load', {}).get('objects', []),
            {'id': uid, 'weight_kg': .1}], 'actual carried urban projectile')
        if held:
            if holder.kind == 'trainer':
                HANDS.observe(self.e, holder, uid, hand='주요손', reason='actual gripped urban projectile')
            else:
                ITEMS.equip_held(self.e, holder, rule, source_instance_id=uid)
        return {'instance_id': uid}

    def cast(self, *, choice=None, subject=None, target=None, terrain='urban'):
        return self.e.survivalist_activity(self.t, 'natural_fighter', subject=subject or self.actor,
            terrain_name=terrain, target=target or self.foe, set_damage=True, fling=choice)

    def test_actual_trainer_or_owned_pokemon_projectile_pays_once_and_releases_permission(self):
        for role in ('trainer', 'partner'):
            with self.subTest(role=role):
                self.scene(role, 'urban')
                self.e.gm.set_types(self.foe, ['물'], reason='actual nonimmune recipient')
                choice = self.object(rule='item/맹독구슬' if role == 'partner' else None)
                ap = AP.available(self.t)
                owner_budget = deepcopy(getattr(self.t, 'budget', None))
                learned = deepcopy(self.actor.spec.get('moves', []))
                hp = self.foe.hp
                with patch.object(Engine, 'd20', return_value=18):result = self.cast(choice=choice)
                record = self.actor.spec[NF.KEY][result['activation_id']]
                completion = self.e._move_completions[result['completion_id']]
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(AP.available(self.t), ap - 1)
                self.assertEqual(self.actor.budget['standard'], 0)
                self.assertEqual(self.actor.move_uses[FLING.SOURCE], 1)
                self.assertLess(self.foe.hp, hp)
                self.assertEqual(record['payment']['actor_id'], self.t.entity_id)
                self.assertEqual(record['fling_choice']['actor_id'], self.actor.entity_id)
                self.assertEqual(record['fling_choice']['target_id'], self.foe.entity_id)
                self.assertEqual(completion['fling_launch']['plan']['instance_id'], choice['instance_id'])
                self.assertEqual(record['fling_choice']['instance_id'], choice['instance_id'])
                self.assertEqual(self.actor.spec.get('moves', []), learned)
                self.assertNotIn(FLING.SOURCE, self.actor.moves)
                self.assertNotIn(result['activation_id'], self.actor.spec[G.KEY]['sources'])
                self.assertNotIn(FLING.CHOICE, self.actor.spec)
                self.assertIsNone(NF.current(self.actor))
                obj = self.e._physical_objects[choice['instance_id']]
                self.assertFalse(obj.get('equipped_by') or obj.get('carrier_id'))
                self.assertEqual(W.location_of(obj), {'kind': 'unknown'})
                if role == 'partner':
                    self.assertEqual(getattr(self.t, 'budget', None), owner_budget)
                    self.assertNotIn(FLING.SOURCE, self.t.move_uses)
                    self.assertIn('독', self.foe.conditions)
                self.restore()
                self.assertEqual(AP.available(self.t), ap - 1)
                self.assertEqual(self.actor.move_uses[FLING.SOURCE], 1)

    def test_missing_fictional_and_ungripped_projectiles_reject_without_any_payment(self):
        self.scene(terrain='urban')
        self.reject_unchanged('explicit actual Fling projectile choice', lambda: self.cast())
        self.reject_unchanged('existing physical object', lambda: self.cast(choice={'instance_id': 'fictional-trash'}))
        choice = self.object(held=False)
        self.reject_unchanged('actual hand or held', lambda: self.cast(choice=choice))
        self.assertNotIn(FLING.SOURCE, self.actor.moves)
        self.assertIsNone(NF.current(self.actor))
        self.assertNotIn(FLING.CHOICE, self.actor.spec)

    def test_choice_must_belong_to_actual_subject_and_only_urban_accepts_it(self):
        self.scene('partner', 'urban')
        choice = self.object(holder=self.t)
        self.reject_unchanged('actual hand or held', lambda: self.cast(choice=choice))
        self.scene(terrain='tundra')
        choice = self.object()
        self.reject_unchanged('choices require the urban', lambda: self.cast(choice=choice, terrain='tundra', target=self.t))

    def test_feature_ownership_subject_terrain_and_real_target_boundaries_remain(self):
        self.scene(terrain='urban', feats=(SC.CLASS,))
        choice = self.object()
        self.reject_unchanged('acquired source', lambda: self.cast(choice=choice))
        self.scene(terrain='urban')
        choice = self.object()
        self.reject_unchanged('trainer-owned Pokemon', lambda: self.cast(choice=choice, subject=self.foe, target=self.p))
        self.reject_unchanged('actual encounter turn', lambda: self.cast(choice=choice, subject=self.p))
        self.scene('partner', 'tundra')
        FIX.env(self.e, self.t, 'urban')
        choice = self.object(rule='item/맹독구슬')
        self.reject_unchanged('observed current terrain', lambda: self.cast(choice=choice))
        self.scene(terrain='urban')
        choice = self.object()
        self.e.gm.recall(self.foe, reason='actual target recalled before urban Fling')
        self.reject_unchanged('.', lambda: self.cast(choice=choice))

    def test_urban_still_requires_owner_ap_and_subject_standard(self):
        self.scene(terrain='urban')
        choice = self.object()
        AP.spend(self.t, AP.available(self.t))
        self.reject_unchanged('1 available trainer AP', lambda: self.cast(choice=choice))
        self.scene('partner', 'urban')
        choice = self.object(rule='item/맹독구슬')
        self.assertTrue(TURN.spend(self.e, self.p, 'standard', 'actual earlier Standard'))
        self.reject_unchanged('available Standard', lambda: self.cast(choice=choice))

    def test_native_miss_pays_once_and_releases_the_actual_projectile(self):
        self.scene(terrain='urban')
        choice = self.object(rule='item/상처약')
        before, ap = self.foe.hp, AP.available(self.t)
        with patch.object(Engine, 'd20', return_value=1):result = self.cast(choice=choice)
        completion = self.e._move_completions[result['completion_id']]
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(completion['fling_launch']['status'], 'miss')
        self.assertEqual(self.foe.hp, before)
        self.assertNotIn('consumed', self.e._physical_objects[choice['instance_id']])
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.actor.budget['standard'], 0)
        self.assertFalse(HANDS.occupied(self.actor))
        self.assertIsNone(NF.current(self.actor))

    def test_learned_fling_and_class_route_share_scene_twice_through_restore(self):
        self.scene(terrain='urban')
        self.e.gm.set_move(self.t, FLING.SOURCE, reason='previously acquired Fling')
        choice = self.object('urban/first')
        FLING.declare(self.e, self.t, self.foe, **choice)
        with patch.object(Engine, 'd20', return_value=1):
            self.e.use_move_on(self.t, self.foe, FLING.SOURCE, self.e.everyone, set_damage=True)
        self.next_round()
        choice = self.object('urban/second')
        ap = AP.available(self.t)
        with patch.object(Engine, 'd20', return_value=1):self.cast(choice=choice)
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.t.move_uses[FLING.SOURCE], 2)
        self.assertIn(FLING.SOURCE, self.t.moves)
        self.restore()
        self.next_round()
        choice = self.object('urban/third')
        self.reject_unchanged('.', lambda: self.cast(choice=choice))
        self.assertEqual(self.t.move_uses[FLING.SOURCE], 2)
        self.assertEqual(self.t.budget['standard'], 1)
        self.assertEqual(HANDS.inspect(self.e, self.t, choice['instance_id'])['hand'], '주요손')

    def test_actual_defense_wait_restores_projectile_permission_and_paid_prefix_once(self):
        self.scene('partner', 'urban')
        self.e.gm.set_types(self.foe, ['물'], reason='actual nonimmune recipient')
        choice = self.object(rule='item/맹독구슬')
        self.e.gm.set_ability(self.foe, '회피', reason='actual optional Dodge')
        self.e.watch_move_defense(self.foe, [{'actor_id': self.foe.entity_id, 'source': 'ability/회피'}],
                                 reason='actual defense of class Fling')
        ap = AP.available(self.t)
        with patch.object(Engine, 'd20', return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending):self.cast(choice=choice)
        event = self.e._passive_pending
        identity = NF.current(self.p)['id']
        completion_id = NF.current(self.p)['completion_id']
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.e._move_completions[completion_id]['fling_launch']['plan']['instance_id'], choice['instance_id'])
        self.assertFalse(self.e._physical_objects[choice['instance_id']].get('equipped_by'))
        self.restore()
        prefix = deepcopy((AP.available(self.t), self.p.budget, self.p.move_uses))
        self.e.choose_move_defense(event, self.foe, use=False, reason='decline the saved actual Fling defense')
        self.assertEqual(prefix, (AP.available(self.t), self.p.budget, self.p.move_uses))
        self.assertIn('독', self.foe.conditions)
        self.assertNotIn(identity, self.p.spec[G.KEY]['sources'])
        self.assertIsNone(NF.current(self.p))
        self.assertEqual(self.p.spec[NF.KEY][identity]['fling_choice']['instance_id'], choice['instance_id'])
        self.restore()

    def test_class_medicine_consumes_real_body_without_recipient_action_or_damage(self):
        self.scene(terrain='urban')
        choice = self.object(rule='item/상처약')
        self.e.lose_hp(self.foe, 20, source='gm/actual-injury')
        before = self.foe.hp
        target_actions = deepcopy((self.foe.budget, self.foe._action_history))
        ap = AP.available(self.t)
        with patch.object(Engine, 'd20', return_value=18):result = self.cast(choice=choice)
        completion = self.e._move_completions[result['completion_id']]
        self.assertGreater(self.foe.hp, before)
        self.assertEqual((self.foe.budget, self.foe._action_history), target_actions)
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertIn('consumed', self.e._physical_objects[choice['instance_id']])
        consumed = completion['fling_launch']['consumer_result']
        payment = self.t.spec['stock_consumption_receipts'][consumed['stock_receipt_id']]
        self.assertEqual(payment['item_stock']['instance_id'], choice['instance_id'])
        self.assertEqual(payment['item_stock']['fling']['completion_id'], result['completion_id'])
        self.restore()

    def test_class_ball_uses_existing_capture_without_second_standard_or_accuracy(self):
        self.scene(terrain='urban')
        choice = self.object(rule='item/몬스터볼')
        choice.update(capture=True, capture_options={'capture_source': 'core_105', 'fixed_capture': 100})
        ap = AP.available(self.t)
        with patch.object(Engine, 'd20', return_value=18):result = self.cast(choice=choice)
        attempts = list(self.t.spec['capture_attempts'].values())
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]['physical_instance_id'], choice['instance_id'])
        self.assertEqual(attempts[0]['accuracy_natural'], 18)
        self.assertEqual(attempts[0]['move_origin']['completion_id'], result['completion_id'])
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.t.budget['standard'], 0)
        self.assertEqual(self.t.move_uses[FLING.SOURCE], 1)
        self.assertIsNone(NF.current(self.t))
        self.restore()

    def test_saved_class_projectile_choice_cannot_be_rebound_to_another_body(self):
        self.scene(terrain='urban')
        choice = self.object()
        with patch.object(Engine, 'd20', return_value=1):result = self.cast(choice=choice)
        record = self.t.spec[NF.KEY][result['activation_id']]
        record['fling_choice']['instance_id'] = 'different-projectile'
        with self.assertRaisesRegex(ValueError, 'Natural Fighter native activation identity changed'):
            FIX.restore(self.rules, self.e)


if __name__ == '__main__':unittest.main()
