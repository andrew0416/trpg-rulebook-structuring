"""Native Fling intake acceptance candidates. SOURCE ONLY; never locally run."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
import test_fling_native as BASE
import book_survivalist_fixture as FIX
import fling_consumables as CONSUMERS
import consumption_execution as EXECUTION
import event_effects as EVENTS
import food_effects as FOOD
import herb_mushroom_rules as HERB
import lifetime_consumables as LIFE
import vitamin_moves as VITAMINS


class FlingConsumableTests(unittest.TestCase):
    setUp = BASE.FlingNativeTests.setUp
    hand = BASE.FlingNativeTests.hand
    cast = BASE.FlingNativeTests.cast
    launch = BASE.FlingNativeTests.launch

    @classmethod
    def setUpClass(cls):cls.rules = Rules(ROOT, ruleset='core')

    def restore(self):
        self.e, index = FIX.restore(self.rules, self.e)
        self.a, self.t = index[self.a.entity_id], index[self.t.entity_id]

    def target_actions(self):
        return deepcopy((self.t.budget, self.t._action_history, self.t.pending_action_loss))

    def paid(self):
        return EXECUTION.validate(self.a)[self.launch()['consumer_result']['stock_receipt_id']]

    def test_herbal_native_history_and_actual_stock_survive_restore_without_debt(self):
        uid = self.hand(rule='item/힘의가루')
        self.e.lose_hp(self.t, 30, source='gm/actual-fixture-injury')
        before, actions = self.t.hp, self.target_actions()
        self.cast(uid)
        self.assertGreater(self.t.hp, before)
        self.assertEqual(FOOD.herbal_state(self.t)['count'], 1)
        self.assertEqual(self.target_actions(), actions)
        self.assertEqual(self.paid()['outcome'], 'applied')
        self.restore()
        self.assertEqual(self.e._physical_objects[uid]['consumed']['by_actor_id'], self.t.entity_id)
        self.assertEqual(self.paid()['item_stock']['instance_id'], uid)

    def test_x_item_changes_recipient_stage_without_recipient_action(self):
        uid = self.hand(rule='item/플러스파워')
        stage, hp, actions = self.t.stages['atk'], self.t.hp, self.target_actions()
        self.cast(uid)
        self.assertEqual(self.t.hp, hp)
        self.assertEqual(self.t.stages['atk'], min(6, stage + 2))
        self.assertEqual(self.target_actions(), actions)
        self.restore()

    def test_gem_binds_consumed_body_to_recipient_native_future_effect(self):
        uid = self.hand(rule='item/물주얼')
        hp, actions = self.t.hp, self.target_actions()
        self.cast(uid)
        records = [r for r in EVENTS.live(self.t) if r['source'] == 'item/물주얼']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['item_stock']['instance_id'], uid)
        self.assertEqual(self.t.hp, hp)
        self.assertEqual(self.target_actions(), actions)
        self.restore()  # Native Gem validator checks exact body consumer/time.
        self.assertEqual(len([r for r in EVENTS.live(self.t) if r['source'] == 'item/물주얼']), 1)

    def test_mushroom_keeps_its_actual_body_random_plan(self):
        uid = self.hand(rule='item/작은버섯')
        before = deepcopy(self.t.stages)
        hp, actions = self.t.hp, self.target_actions()
        self.cast(uid)
        obj = self.e._physical_objects[uid]
        plan = HERB.validate_object(self.rules, obj)
        self.assertEqual(plan['instance_id'], uid)
        self.assertEqual(self.t.hp, hp - 5)  # Only Mushroom loss; Fling DB is zero.
        self.assertEqual(sum(self.t.stages[k] - before[k] for k in before), 1)
        self.assertEqual(self.target_actions(), actions)
        self.restore()
        self.assertEqual(self.e._physical_objects[uid][HERB.PLAN], plan)

    def test_vitamin_and_pp_up_use_the_native_dose_ledger(self):
        for item in ('item/타우린', VITAMINS.PP):
            with self.subTest(item=item):
                self.setUp()
                mid = 'move/모래뿌리기'
                if item == VITAMINS.PP:self.e.gm.set_move(self.t, mid, reason='actual learned Move for PP Up')
                uid = self.hand(rule=item)
                before = len(self.t.spec.get('vitamins', []))
                actions = self.target_actions()
                options = {'selected_move': mid} if item == VITAMINS.PP else {}
                self.cast(uid, consumer_options=options)
                self.assertEqual(len(self.t.spec['vitamins']), before + 1)
                self.assertEqual(self.t.spec['vitamins'][-1], item)
                self.assertEqual(self.paid()['outcome'], 'applied')
                if item == VITAMINS.PP:
                    self.assertEqual(self.t.spec['vitamin_special_uses'][item]['move_id'], mid)
                self.assertEqual(self.target_actions(), actions)
                self.restore()

    def test_lifetime_candy_keeps_actual_growth_and_lifetime_receipt(self):
        item = 'item/이상한사탕'
        key, _ = LIFE.definition(self.rules, item)
        if key not in self.t.spec.get(LIFE.KEY, {}).get('quotas', {}):
            LIFE.observe(self.e, self.t, item=item, count=0, reason='actual known zero prior Candy consumption')
        uid = self.hand(rule=item)
        level, actions = self.t.level, self.target_actions()
        self.cast(uid)
        self.assertEqual(self.t.level, level + 1)
        self.assertEqual(self.t.spec[LIFE.KEY]['quotas'][key]['receipts'][-1]['item_stock']['instance_id'], uid)
        self.assertEqual(self.target_actions(), actions)
        self.restore()

    def test_extended_food_is_not_forced_into_a_digestion_buff(self):
        for item in ('item/오랭열매', 'item/멘탈허브', 'item/맛있는물', 'item/붕대', 'item/파스'):
            self.assertIsNone(CONSUMERS.profile(self.e, self.a, self.t, item))
        self.assertEqual(self.a.move_uses.get('move/내던지기', 0), 0)

    def test_unissued_consumption_cannot_consume_or_apply_effects(self):
        uid = self.hand(rule='item/상처약')
        plan = CONSUMERS.profile(self.e, self.a, self.t, 'item/상처약', instance_id=uid)
        before = deepcopy((self.a.spec, self.t.spec, self.t.hp, self.e._physical_objects, self.e.rng.getstate()))
        with self.assertRaisesRegex(ValueError, 'unused Fling effect admission'):
            CONSUMERS.consume(self.e, self.a, self.t, 'unissued', plan)
        self.assertEqual(before, (self.a.spec, self.t.spec, self.t.hp, self.e._physical_objects, self.e.rng.getstate()))

    def test_saved_consumer_receipt_cannot_be_rebound_to_another_recipient(self):
        uid = self.hand(rule='item/상처약')
        self.cast(uid)
        self.restore()
        self.paid()['item_stock']['fling']['target_id'] = self.a.entity_id
        with self.assertRaisesRegex(ValueError, 'stock receipt disagree'):
            self.restore()


if __name__ == '__main__':unittest.main()
