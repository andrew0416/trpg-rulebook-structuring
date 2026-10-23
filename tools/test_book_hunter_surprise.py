"""Hunter Surprise!: armed X AP Swift action paid at the Trainer's actual accuracy roll; two dice, the better result, Flinch on a double hit.

Reuses the acquisition scene helpers without inheriting any test method.
"""
from unittest.mock import patch
import unittest

import test_book_hunter_acquisition as fixture
from engine import Rules, Engine
import action_points as AP
import hunter as HU
import turn as TURN


class HunterSurpriseTests(fixture.HunterScene, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    def ready(self, *, position=(3, 1)):
        """Whole class; the Hunter stands beside the foe (p with Teamwork is adjacent to q as well)."""
        self.whole()
        self.e.gm.set_position(self.t, position, reason='actual Hunter beside the foe')
        self.combat(self.t, count=30)
        return AP.available(self.t)

    def attack(self, move='struggle', faces=(4, 16), target=None):
        target = target or self.q
        if move not in self.t.moves and move != 'struggle':
            self.e.gm.set_move(self.t, move, reason='actual complete known Move list')
        with patch.object(Engine, 'd20', side_effect=list(faces) + [10] * 8):
            return self.e.use_move_on(self.t, target, move, self.e.everyone, set_damage=True)

    def receipt(self, index=-1):
        return self.t.spec[HU.SURPRISE_HISTORY][index]

    # ---------------------------------------------------------------- arming
    def test_arming_needs_the_feature_and_an_actual_foe_and_can_be_disarmed(self):
        self.acquire()
        self.rejected(lambda:HU.arm_surprise(self.e, self.t, self.q), 'actual acquired Hunter Feature')
        self.acquire(HU.SURPRISE)
        self.rejected(lambda:HU.arm_surprise(self.e, self.t, self.t), 'actual foe')
        self.rejected(lambda:HU.arm_surprise(self.e, self.t, self.p), 'actual foe')
        self.rejected(lambda:HU.arm_surprise(self.e, self.p, self.q), 'actual acquired Hunter Feature')
        row = HU.arm_surprise(self.e, self.t, self.q)
        self.assertEqual((row['target_id'], row['clause_id']), (self.q.entity_id, 'input/ch04-trainer-classes.md:2347-2352'))
        self.assertEqual(HU.armed_surprise(self.t), row)
        self.restore()
        self.valid()
        self.assertEqual(HU.armed_surprise(self.t)['target_id'], self.q.entity_id)
        HU.disarm_surprise(self.e, self.t)
        self.assertIsNone(HU.armed_surprise(self.t))
        self.rejected(lambda:HU.disarm_surprise(self.e, self.t), 'actual armed Surprise!')
        # An arming that outlives its acquisition is detected, and retraining discards it.
        HU.arm_surprise(self.e, self.t, self.q)
        self.retrain(HU.SURPRISE)
        self.assertIsNone(HU.armed_surprise(self.t))
        self.valid()

    # ---------------------------------------------------------------- the paid trigger
    def test_pack_adjacent_trigger_pays_swift_one_ap_for_struggle_rolls_twice_uses_the_better_and_flinches_on_a_double_hit(self):
        ap = self.ready()
        HU.arm_surprise(self.e, self.t, self.q)
        self.assertIsNotNone(HU.surprise_ready(self.e, self.t, self.q, self.e.r.move('struggle')))
        self.attack('struggle', faces=(4, 16))
        row = self.receipt()
        self.assertEqual((row['faces'], row['results'], row['chosen'], row['both_hit'], row['cost'], row['move_id']), ([4, 16], [True, True], 16, True, 1, 'struggle'))
        self.assertEqual(row['trigger'], {'basis':'pack_adjacent', 'pokemon_id':self.p.entity_id})
        self.assertIn('d20=16+2=18', self.accuracy_log(self.t)[-1])      # the better die finalizes the attack (+2 Teamwork from p)
        self.assertIn('풀죽음', self.q.conditions)
        self.assertEqual((AP.available(self.t), self.t.budget['swift'], self.t._action_history[-2:]), (ap - 1, 0, ['standard', 'swift']))
        self.assertIsNone(HU.armed_surprise(self.t))
        self.assertEqual(self.activations(self.t)[HU.SURPRISE + ':' + self.q.entity_id]['used'], 1)
        self.restore()
        self.valid()
        self.assertEqual(len(self.t.spec[HU.SURPRISE_HISTORY]), 1)
        # Once per target per Scene: the same foe cannot be surprised again until the Scene ends; another foe can.
        other = self.add('actual second foe', 'pokemon', (4, 0), side='foe', species='피카츄', types=['전기'],
            moves=['move/막치기'], speed=12)
        HU.arm_surprise(self.e, self.t, self.q)
        self.next_round(self.t, count=30)
        self.assertIsNone(HU.surprise_ready(self.e, self.t, self.q, self.e.r.move('struggle')))
        self.attack('struggle', faces=(4, 16))
        self.assertEqual((len(self.t.spec[HU.SURPRISE_HISTORY]), AP.available(self.t)), (1, ap - 1))
        self.assertIn('d20=4+', self.accuracy_log(self.t)[-1])
        self.assertIsNotNone(HU.armed_surprise(self.t))
        HU.arm_surprise(self.e, self.t, other)
        self.e.gm.set_position(self.p, (3, 0), reason='actual pack beside the second foe')
        self.next_round(self.t, count=30)
        self.attack('struggle', faces=(4, 16), target=other)
        self.assertEqual((len(self.t.spec[HU.SURPRISE_HISTORY]), self.receipt()['target_id']), (2, other.entity_id))
        self.e.end_scene()
        self.e.gm.set_position(self.p, (3, 2), reason='actual pack beside the foe')
        HU.arm_surprise(self.e, self.t, self.q)
        self.combat(self.t, count=30)
        self.assertIsNotNone(HU.surprise_ready(self.e, self.t, self.q, self.e.r.move('struggle')))
        self.attack('struggle', faces=(4, 16))
        self.assertEqual(len(self.t.spec[HU.SURPRISE_HISTORY]), 3)
        self.valid()

    def test_the_better_result_is_the_hitting_die_or_the_higher_face_and_no_flinch_without_a_double_hit(self):
        self.ready()
        HU.arm_surprise(self.e, self.t, self.q)
        self.attack('struggle', faces=(2, 15))                             # 2+2=4 misses AC 4+evasion 2; 15 hits
        self.assertEqual((self.receipt()['results'], self.receipt()['chosen']), ([False, True], 15))
        self.assertNotIn('풀죽음', self.q.conditions)
        self.assertIn('d20=15+2=17', self.accuracy_log(self.t)[-1])
        self.e.end_scene()
        self.e.gm.set_position(self.t, (3, 1), reason='actual Hunter beside the foe')
        HU.arm_surprise(self.e, self.t, self.q)
        self.combat(self.t, count=30)
        self.attack('struggle', faces=(15, 2))
        self.assertEqual((self.receipt()['results'], self.receipt()['chosen']), ([True, False], 15))
        self.e.end_scene()
        self.e.gm.set_position(self.t, (3, 1), reason='actual Hunter beside the foe')
        HU.arm_surprise(self.e, self.t, self.q)
        self.combat(self.t, count=30)
        self.attack('struggle', faces=(2, 3))
        self.assertEqual((self.receipt()['results'], self.receipt()['chosen']), ([False, False], 3))
        self.assertIn('빗나감', self.accuracy_log(self.t)[-1])
        self.assertNotIn('풀죽음', self.q.conditions)
        self.valid()

    def test_unaware_observation_triggers_without_pack_adjacency_and_an_ordinary_move_costs_two_ap(self):
        ap = self.ready()
        self.e.gm.set_position(self.p, (8, 8), reason='actual pack away')
        self.e.gm.set_position(self.u, (8, 9), reason='actual pack away')
        HU.arm_surprise(self.e, self.t, self.q)
        self.assertIsNone(HU.surprise_ready(self.e, self.t, self.q, self.e.r.move('struggle')))
        self.attack('move/몸통박치기', faces=(4, 16))                        # no trigger: ordinary single roll, arming stays
        self.assertEqual((AP.available(self.t), HU.armed_surprise(self.t)['target_id']), (ap, self.q.entity_id))
        self.assertNotIn(HU.SURPRISE_HISTORY, self.t.spec)
        self.answer(HU.SURPRISE_PROMPT, True)
        self.next_round(self.t, count=30)
        self.attack('move/몸통박치기', faces=(8, 16))
        self.assertEqual((self.receipt()['cost'], self.receipt()['trigger'], self.receipt()['move_id']), (2, {'basis':'unaware'}, 'move/몸통박치기'))
        self.assertEqual(AP.available(self.t), ap - 2)
        self.assertIn('풀죽음', self.q.conditions)
        # The printed discount set by attack identity (nets have no attack producer yet; identity is kept for them).
        self.assertEqual(HU.surprise_cost({'id':'ball'}), 1)
        self.assertEqual(HU.surprise_cost({'id':'move/몸통박치기', '_weapon_attack':{'source':'item/수제-그물'}}), 1)
        self.assertEqual(HU.surprise_cost({'id':'move/몸통박치기'}), 2)
        self.valid()

    def test_a_poke_ball_throw_is_a_one_ap_trigger_with_its_own_second_die(self):
        ap = self.ready()
        self.t.spec['items'] = {'몬스터볼':2}
        HU.arm_surprise(self.e, self.t, self.q)
        with patch.object(Engine, 'd20', return_value=16):
            self.e.throw_ball(self.t, self.q, fixed_accuracy=12, fixed_capture=1)
        self.assertEqual((self.receipt()['faces'], self.receipt()['cost'], self.receipt()['move_id']), ([12, 16], 1, 'ball'))
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertTrue(self.receipt()['both_hit'])
        self.assertIn('풀죽음', self.q.conditions)
        self.valid()

    def test_unpayable_or_unavailable_swift_action_leaves_the_attack_ordinary_and_the_arming_in_place(self):
        ap = self.ready()
        HU.arm_surprise(self.e, self.t, self.q)
        AP.charge(self.t, ap)
        self.assertIsNone(HU.surprise_ready(self.e, self.t, self.q, self.e.r.move('struggle')))
        self.attack('struggle', faces=(4, 16))
        self.assertIn('d20=4+', self.accuracy_log(self.t)[-1])
        self.assertIsNotNone(HU.armed_surprise(self.t))
        self.assertNotIn(HU.SURPRISE_HISTORY, self.t.spec)
        # A spent Swift action: the trigger is ready on paper but the Swift action cannot be paid, so nothing is paid.
        self.next_round(self.t, count=30)
        self.assertTrue(TURN.spend(self.e, self.t, 'swift', 'actual earlier Swift action'))
        self.attack('struggle', faces=(4, 16))
        self.assertIn('d20=4+', self.accuracy_log(self.t)[-1])
        self.assertNotIn(HU.SURPRISE_HISTORY, self.t.spec)
        self.assertIsNotNone(HU.armed_surprise(self.t))
        self.assertEqual(AP.available(self.t), 0)
        # The Pokemon's attack never answers the Trainer's arming.
        self.turn(self.p, count=20)
        self.use(self.p, self.q, 'move/몸통박치기', face=10)
        self.assertIsNotNone(HU.armed_surprise(self.t))
        self.valid()


if __name__ == '__main__':
    unittest.main()
