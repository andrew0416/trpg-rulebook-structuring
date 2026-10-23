"""Dancer Dance Moves in actual use: fixed self stages without an accuracy check, EOT frequency, the Beguiling
Dance range/AC/target, and Choreographer teaching an own Dance Move to an owned Pokemon (ch04:2277-2306)."""
from copy import deepcopy
from unittest.mock import patch
import json
import unittest

import test_book_dancer_acquisition as fixture
from engine import Engine
import dancer as D
import action_points as AP
import move_state as M
import pokemon_teaching as TEACH
import state_codec as CODEC
import world_entities as WORLD


class DancerMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not hasattr(fixture.DancerAcquisitionTests, 'rules'):
            fixture.DancerAcquisitionTests.setUpClass()
        cls.rules = fixture.DancerAcquisitionTests.rules

    add = fixture.DancerAcquisitionTests.add
    acquire = fixture.DancerAcquisitionTests.acquire
    dancer = fixture.DancerAcquisitionTests.dancer
    create = fixture.DancerAcquisitionTests.create
    rejected = fixture.DancerAcquisitionTests.rejected
    valid = fixture.DancerAcquisitionTests.valid
    invalid = fixture.DancerAcquisitionTests.invalid
    restore = fixture.DancerAcquisitionTests.restore
    combat = fixture.DancerAcquisitionTests.combat
    next_turn = fixture.DancerAcquisitionTests.next_turn
    use = fixture.DancerAcquisitionTests.use
    answer = fixture.DancerAcquisitionTests.answer

    def setUp(self):
        fixture.DancerAcquisitionTests.setUp(self)

    def scene(self, *features, ability='회전춤'):
        self.dancer(*features, ability=ability)
        self.p = self.add('partner', 'pokemon', (2, 1), trainer_id=self.t.entity_id, abilities=['마이페이스'], speed=25, tutor_points=5, moves=['move/용의춤'])
        self.b = self.add('enemy', 'pokemon', (4, 1), side='enemy', speed=20)

    def test_created_dance_move_applies_its_fixed_stages_without_accuracy_check_and_keeps_every_other_turn_frequency(self):
        self.scene()
        waltz = self.create('불꽃왈츠', {'atk': 1, 'spe': 1}, '근사함')
        self.combat(self.t)
        before = len(self.e.log_lines)
        self.use(self.t, self.t, waltz['id'])
        self.assertEqual(self.t.stages, {'atk': 1, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 1})
        self.assertTrue(any('명중 체크 없음' in line for line in self.e.log_lines[before:]))
        self.assertFalse(any('명중 d20' in line for line in self.e.log_lines[before:]))
        last = self.t.spec[D.KEY]['last_dance']
        self.assertEqual((last['move_id'], last['raised'], last['round'], last['encounter'], last['pirouette']), (waltz['id'], ['atk', 'spe'], 1, True, None))
        self.assertEqual(self.t.move_uses[waltz['id']], 1)
        self.next_turn(self.t)
        before = len(self.e.log_lines)
        self.assertEqual(self.use(self.t, self.t, waltz['id']), 0)   # 턴1회 = every other turn
        self.assertEqual(self.t.stages, {'atk': 1, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 1})
        self.assertTrue(any('매 다른 턴 기술 재사용 대기' in line for line in self.e.log_lines[before:]))
        self.next_turn(self.t)
        self.use(self.t, self.t, waltz['id'])
        self.assertEqual(self.t.stages, {'atk': 2, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 2})
        self.valid()
        self.restore('t', 'p', 'b')
        self.assertEqual(self.t.stages, {'atk': 2, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 2})
        self.assertEqual(self.t.spec[D.KEY]['last_dance']['move_id'], waltz['id'])

    def test_printed_dragon_quiver_and_swords_dance_count_as_dance_moves_for_the_dancer(self):
        self.scene()
        self.combat(self.t)
        self.use(self.t, self.t, 'move/칼춤')
        last = self.t.spec[D.KEY]['last_dance']
        self.assertEqual((last['move_id'], last['raised'], self.t.stages['atk']), ('move/칼춤', ['atk'], 2))
        other = self.add('non dancer', 'trainer', (6, 6), classes=[], feats=[], edges=[], items={}, money=100, moves=[], speed=29)
        self.next_turn(other)
        self.use(other, other, 'move/칼춤')
        self.assertEqual((other.stages['atk'], other.spec.get(D.KEY)), (2, None))   # no Dancer state for a non-Dancer
        self.valid()

    def test_beguiling_dance_move_targets_one_within_four_meters_with_ac_three_and_lowers_the_chosen_stat(self):
        self.scene(D.BEGUILING)
        tango = self.create('기만의탱고', template='beguiling', lowered='def', contest_type='강인함')
        self.combat(self.t)
        self.b.pos = (5, 1)   # distance 4: the printed range
        before = len(self.e.log_lines)
        self.use(self.t, self.b, tango['id'], face=1)   # AC 3 against evasion: natural 1 misses
        self.assertEqual(self.b.stages['def'], 0)
        self.assertTrue(any('AC 3' in line and '빗나감' in line for line in self.e.log_lines[before:]), self.e.log_lines[before:])
        self.assertEqual(self.t.spec[D.KEY]['last_dance']['move_id'], tango['id'])   # performed even when it misses
        self.next_turn(self.t)
        self.next_turn(self.t)
        self.use(self.t, self.b, tango['id'], face=10)
        self.assertEqual((self.b.stages['def'], self.t.stages['def']), (-2, 0))
        self.assertEqual(self.t.spec[D.KEY]['last_dance']['raised'], [])
        self.valid()

    def test_choreographer_teaches_own_dance_moves_for_two_tutor_points_outside_combat_and_repeats_per_move(self):
        self.scene(D.CHOREOGRAPHER)
        waltz = self.create('불꽃왈츠', {'atk': 1, 'spe': 1}, '근사함')
        tango = self.create('달빛탱고', {'spa': 2}, '아름다움')
        other = self.add('other trainer', 'trainer', (8, 8), classes=[], feats=[], edges=[], items={}, money=100, moves=[], speed=29)
        self.dancer(trainer=other, ability='마이페이스')
        foreign = D.create_dance_move(self.e, other, name='남의왈츠', stages={'def': 2}, contest_type='강인함', reason='other trainer')
        q = self.add('stranger', 'pokemon', (9, 8), trainer_id=other.entity_id, speed=21, tutor_points=5)
        teach = lambda target=None, move=None, **kw: D.choreograph(self.e, self.t, target or self.p, move or '불꽃왈츠', seconds=3600,
                                                                    reason='actual completed choreography', **kw)
        self.combat(self.t)
        self.rejected(teach, 'outside an active encounter')
        self.e.end_of_turn(self.t)
        self.e.end_round()
        self.e.end_encounter()
        self.rejected(lambda: teach(q), 'actual owned Pokemon required')
        self.rejected(lambda: teach(move='move/칼춤'), 'created by this trainer')
        self.rejected(lambda: teach(move=foreign['id']), 'created by this trainer')
        self.rejected(lambda: teach(move='남의왈츠'), 'created by this trainer')
        self.p.spec['tutor_points'] = 1
        self.rejected(teach, 'two actual Tutor Points')
        self.p.spec['tutor_points'] = 5
        self.t.spec['skills'].update({'곡예': 3, '육상': 3, '매력': 3})
        self.rejected(teach, 'printed skill rank')
        self.t.spec['skills']['육상'] = 4
        elapsed = self.e.elapsed_seconds
        out = teach()
        self.assertEqual((out['move'], out['point_cost'], out['classification'], self.p.spec['tutor_points'], self.e.elapsed_seconds - elapsed),
                         (waltz['id'], 2, 'taught', 3, 3600))
        self.assertEqual(self.p.moves, ['move/용의춤', waltz['id']])
        receipt = self.p.spec['move_learning'][waltz['id']]
        self.assertEqual((receipt['source'], receipt['method'], receipt['paid_tp'], receipt['teacher_id']), (D.CHOREOGRAPHER, 'feature', 2, self.t.entity_id))
        self.rejected(teach, 'already learned that Dance Move')
        out = teach(move=tango['id'])   # Choreographer targets the same Pokemon again with another Dance Move
        self.assertEqual((out['move'], self.p.spec['tutor_points'], len(self.p.moves)), (tango['id'], 1, 3))
        self.rejected(lambda: teach(move='둘째'), 'created by this trainer')
        self.valid()
        self.restore('t', 'p')
        self.assertEqual([self.e.r.move(mid)['name'] for mid in self.p.moves], ['용의춤', '불꽃왈츠', '달빛탱고'])
        self.combat(self.p)
        self.use(self.p, self.p, waltz['id'])
        self.assertEqual(self.p.stages, {'atk': 1, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 1})
        self.assertIsNone(self.t.spec[D.KEY]['last_dance'])   # a Pokemon's dance is not the trainer performing one
        forged = self.p.spec['move_learning'][waltz['id']]
        forged['teacher_id'] = 'trainer/instance/forged'
        self.invalid('Choreographer teaching receipt')


if __name__ == '__main__':
    unittest.main()
