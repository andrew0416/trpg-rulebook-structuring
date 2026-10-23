"""Native linked condition producers, holder clocks, consumers and restoration."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import tools.test_category2_native_move_batches as FIX
import condition_instances as CONDITIONS
import linked_move_conditions as LINKED


class LinkedMoveConditionTests(unittest.TestCase):
    initial_moves = ['move/몸통박치기', 'move/씨뿌리기', 'move/멸망의노래', 'move/봉인']
    setUpClass = classmethod(FIX.NativeMoveBatchTests.setUpClass.__func__)
    turn = FIX.NativeMoveBatchTests.turn
    restore = FIX.NativeMoveBatchTests.restore

    def setUp(self):
        FIX.NativeMoveBatchTests.setUp(self)

    def saved(self):
        self.e.__dict__.pop('d20', None)
        self.e.gm.snapshot('linked')
        self.e.gm.restore('linked', reason='verify actual linked ownership')
        self.e = self.restore()
        self.p = next(c for c in self.e.everyone if c.entity_id == self.p.entity_id)
        self.t = next(c for c in self.e.everyone if c.entity_id == self.t.entity_id)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_seed_native_current_maximum_actual_loss_heals_caster_after_both_restores(self):
        self.p.hp -= 25
        self.e.use_move(self.p, self.t, 'move/씨뿌리기')
        self.assertIn('씨뿌리기', self.t.conditions)
        row = CONDITIONS.records(self.t, '씨뿌리기')[0]
        self.assertEqual(row['effect_instance']['applied_by_actor_id'], self.p.entity_id)
        self.saved()
        before = self.p.hp, self.t.hp
        expected = self.t.max_hp // 10
        self.turn(self.t)
        self.assertEqual((self.p.hp-before[0], before[1]-self.t.hp), (expected, expected))
        event = CONDITIONS.records(self.t, '씨뿌리기')[0]['applications'][0]
        self.assertEqual(event['lost'], expected)
        self.e.gm.recall(self.t, reason='seed target recalled')
        self.assertNotIn('씨뿌리기', self.t.conditions)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_seed_grass_immunity_miss_and_faint_end_actual_instances(self):
        self.e.use_move(self.p, self.p, 'move/씨뿌리기')
        self.assertNotIn('씨뿌리기', self.p.conditions)
        self.setUp(); self.e.d20 = lambda: 1
        self.e.use_move(self.p, self.t, 'move/씨뿌리기')
        self.assertNotIn('씨뿌리기', self.t.conditions)
        self.setUp(); self.p.hp -= 25
        self.e.use_move(self.p, self.t, 'move/씨뿌리기')
        self.t.hp = 1; before = self.p.hp
        expected = self.t.max_hp // 10
        self.turn(self.t)
        self.assertNotIn('씨뿌리기', self.t.conditions)
        self.assertEqual(self.p.hp-before, expected)
        closed = next(r for r in self.t.spec['effect_instance_history'] if r['source'] == 'move/씨뿌리기')
        self.assertEqual(closed['applications'][-1]['lost'], expected)
        self.assertTrue(self.restore().validate_state()['valid'])

    def test_perish_actual_area_includes_user_counts_three_starts_and_sets_hp_without_massive_damage(self):
        before = deepcopy((self.p.budget, self.e.rng.getstate()))
        with self.assertRaises(ValueError): self.e.use_move(self.p, self.t, LINKED.PERISH)
        self.assertEqual(before, (self.p.budget, self.e.rng.getstate()))
        self.e.d20 = lambda: 1
        self.e.use_move_on(self.p, self.t, LINKED.PERISH, self.e.everyone)
        for actor in (self.p, self.t): self.assertIn('멸망 카운트', actor.conditions)
        self.saved()
        self.turn(self.t)
        self.assertEqual(CONDITIONS.records(self.t, '멸망 카운트')[0]['applications'][-1]['remaining'], 2)
        self.turn(self.p, new_round=True)
        self.turn(self.t)
        self.assertEqual(CONDITIONS.records(self.t, '멸망 카운트')[0]['applications'][-1]['remaining'], 1)
        self.turn(self.p, new_round=True)
        # A real HP setting crosses marker thresholds but is not attack/massive damage.
        with patch.object(self.e, 'take_damage', side_effect=AssertionError('Perish is not attack damage')):
            self.turn(self.t)
        self.assertEqual(self.t.hp, 0)
        self.assertNotIn('멸망 카운트', self.t.conditions)
        self.assertTrue(self.restore().validate_state()['valid'])

    def test_perish_recall_and_breather_clear_counter(self):
        self.e.use_move_on(self.p, self.t, LINKED.PERISH, self.e.everyone)
        self.e.gm.recall(self.t, reason='counter target recalled')
        self.assertNotIn('멸망 카운트', self.t.conditions)
        self.turn(self.p, new_round=True)
        result = self.e.take_breather(self.p, request_id='clear-perish', path=[(10,10),(9,10)],
            retreat_reason='observed safe retreat', save_dc=1, save_reason='table DC for this test',
            save_cost='full', fixed_save=20)
        self.assertTrue(result['completed'])
        self.assertNotIn('멸망 카운트', self.p.conditions)
        self.assertTrue(self.restore().validate_state()['valid'])

    def test_seed_grass_absorption_and_healing_block_share_current_consumers(self):
        self.r = FIX.Rules(str(FIX.ROOT),ruleset='playtest')
        self.initial_target_abilities = ['초식 [Playtest]'];self.setUp()
        self.e.use_move(self.p,self.t,'move/씨뿌리기')
        self.assertNotIn('씨뿌리기',self.t.conditions)
        del self.r;del self.initial_target_abilities
        self.setUp();self.p.hp-=25
        self.p.spec['moves'].append('move/회복봉인');self.p.moves.append('move/회복봉인')
        self.e.use_move(self.p,self.t,'move/씨뿌리기')
        self.turn(self.p,new_round=True)
        self.e.use_move(self.p,self.p,'move/회복봉인')
        before=self.p.hp,self.t.hp
        self.turn(self.t)
        self.assertLess(self.t.hp,before[1]);self.assertEqual(self.p.hp,before[0])
        self.assertTrue(self.restore().validate_state()['valid'])

    def test_imprison_consumes_current_caster_moves_before_cost_and_expires_at_scene_end(self):
        self.e.d20 = lambda: 1
        self.e.use_move(self.p, self.t, 'move/봉인')
        self.assertIn('봉인', self.t.conditions)
        self.saved()
        self.turn(self.t)
        before = deepcopy((self.t.budget, self.t.move_uses, self.e.rng.getstate()))
        with self.assertRaises(ValueError): self.e.use_move(self.t, self.p, 'move/몸통박치기')
        self.assertEqual(before, (self.t.budget, self.t.move_uses, self.e.rng.getstate()))
        self.p.moves.remove('move/몸통박치기')
        with patch.object(self.e, 'd20', return_value=17):
            self.e.use_move(self.t, self.p, 'move/몸통박치기', set_damage=True)
        self.e.end_of_turn(self.t); self.e.end_encounter()
        self.assertIn('봉인', self.t.conditions)
        self.e.end_scene()
        self.assertNotIn('봉인', self.t.conditions)
        self.assertTrue(self.e.validate_state()['valid'])


if __name__ == '__main__': unittest.main()
