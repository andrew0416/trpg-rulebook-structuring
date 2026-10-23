"""Dancer encounter Features: Power Pirouette (scene x2 Swift after the trainer's own Dance Move) and
Passing Waltz (triggered 1 AP Free Action moving a Dance Move's stages to one ally within 3 m) (ch04:2308-2323)."""
from copy import deepcopy
from unittest.mock import patch
import json
import unittest

import test_book_dancer_acquisition as fixture
from engine import Engine
import dancer as D
import action_points as AP
import frequency as FREQ
import hazard_state as HAZARDS
import state_codec as CODEC
import world_entities as WORLD


class DancerCombatTests(unittest.TestCase):
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
        self.waltz = self.create('불꽃왈츠', {'atk': 1, 'spe': 1}, '근사함')
        self.p = self.add('partner', 'pokemon', (2, 1), trainer_id=self.t.entity_id, abilities=['마이페이스'], speed=25, tutor_points=5, moves=['move/용의춤'])
        self.q = self.add('plain', 'pokemon', (1, 2), trainer_id=self.t.entity_id, abilities=[], speed=22, tutor_points=5, moves=['move/칼춤'])
        self.b = self.add('enemy', 'pokemon', (2, 2), side='enemy', speed=20)
        self.far = self.add('far enemy', 'pokemon', (8, 8), side='enemy', speed=18)
        self.answer(D.WALTZ_PROMPT, None)   # decline Passing Waltz unless a test chooses

    def pirouette(self, option, **options):
        return D.power_pirouette(self.e, self.t, option, **options)

    # ------------------------------------------------------------ Power Pirouette
    def test_power_pirouette_stage_option_raises_only_a_stat_the_dance_did_not_as_a_scene_twice_swift_action(self):
        self.scene(D.PIROUETTE)
        self.combat(self.t)
        self.rejected(lambda: self.pirouette('stage', stat='def'), 'just performed a Dance Move')
        self.use(self.t, self.t, self.waltz['id'])
        self.rejected(lambda: self.pirouette('stage', stat='atk'), 'cannot raise a stat the triggering Dance Move raised')
        self.rejected(lambda: self.pirouette('stage', stat='spe'), 'cannot raise a stat')
        self.rejected(lambda: self.pirouette('stage', stat='hp'), 'needs one combat stat')
        self.rejected(lambda: self.pirouette('stage'), 'needs one combat stat')
        self.rejected(lambda: self.pirouette('confuse_adjacent', stat='def'), 'only the stage option takes a stat')
        self.rejected(lambda: self.pirouette('spin'), 'option must be one of')
        swift_before = self.t.budget['swift'] if isinstance(getattr(self.t, 'budget', None), dict) and 'swift' in self.t.budget else None
        record = self.pirouette('stage', stat='def')
        self.assertEqual((record['option'], record['stat'], record['move_id'], record['clause_id']), ('stage', 'def', self.waltz['id'], 'input/ch04-trainer-classes.md:2308-2316'))
        self.assertEqual(self.t.stages, {'atk': 1, 'def': 1, 'spa': 0, 'spd': 0, 'spe': 1})
        if swift_before is not None:
            self.assertEqual(self.t.budget['swift'], swift_before - 1)
        self.assertEqual(self.t.spec[D.KEY]['last_dance']['pirouette'], 'stage')
        self.rejected(lambda: self.pirouette('stage', stat='spa'), 'already used for this Dance Move')
        self.assertEqual(FREQ.activation_allowed(self.t, D.PIROUETTE, {'kind': 'scene', 'uses': 2}, engine=self.e), True)
        self.next_turn(self.t)
        self.rejected(lambda: self.pirouette('stage', stat='spa'), 'just performed a Dance Move')   # the trigger is the same turn
        self.next_turn(self.t)
        self.use(self.t, self.t, self.waltz['id'])
        self.pirouette('stage', stat='spa')
        self.assertEqual(self.t.stages, {'atk': 2, 'def': 1, 'spa': 1, 'spd': 0, 'spe': 2})
        self.next_turn(self.t)
        self.next_turn(self.t)
        self.use(self.t, self.t, self.waltz['id'])
        self.rejected(lambda: self.pirouette('stage', stat='spd'), 'scene uses exhausted')
        self.assertEqual(len(self.t.spec[D.KEY]['pirouettes']), 2)
        self.valid()
        self.restore('t', 'p', 'b')
        self.assertEqual([row['option'] for row in self.t.spec[D.KEY]['pirouettes']], ['stage', 'stage'])

    def test_power_pirouette_follows_only_the_trainers_own_dance_and_a_pokemon_dance_is_not_its_trigger(self):
        self.scene(D.PIROUETTE)
        self.combat(self.p, count=25)
        self.use(self.p, self.p, 'move/용의춤')
        self.assertIsNone(self.t.spec[D.KEY]['last_dance'])
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.t, initiative_count=20)
        self.rejected(lambda: self.pirouette('confuse_adjacent'), 'just performed a Dance Move')
        self.use(self.t, self.t, 'move/칼춤')   # printed Swords Dance counts
        record = self.pirouette('stage', stat='def')
        self.assertEqual((record['move_id'], self.t.stages['atk'], self.t.stages['def']), ('move/칼춤', 2, 1))
        other = self.add('other dancer', 'trainer', (10, 10), classes=[], feats=[], edges=[], items={}, money=100, moves=[], speed=28)
        self.dancer(trainer=other, ability='마이페이스')
        self.rejected(lambda: D.power_pirouette(self.e, other, 'stage', stat='def'), 'Power Pirouette required')
        self.valid()

    def test_power_pirouette_confuses_every_adjacent_target_and_own_tempo_keeps_its_immunity(self):
        self.scene(D.PIROUETTE)
        self.combat(self.t)
        self.use(self.t, self.t, self.waltz['id'])
        record = self.pirouette('confuse_adjacent')
        self.assertEqual(record['targets'], {self.p.entity_id: False, self.q.entity_id: True, self.b.entity_id: True})
        self.assertEqual((self.p.conditions, '혼란' in self.q.conditions, '혼란' in self.b.conditions, self.far.conditions), (set(), True, True, set()))
        self.valid()
        self.restore('t', 'p', 'q', 'b')
        self.assertIn('혼란', self.b.conditions)

    def test_power_pirouette_clears_traps_within_five_meters_and_its_own_leech_seed_stuck_and_trapped(self):
        self.scene(D.PIROUETTE)
        self.e.gm.place_hazard((3, 3), '압정', reason='near trap')
        self.e.gm.place_hazard((6, 1), '압정', reason='edge trap at 5 m')
        self.e.gm.place_hazard((7, 7), '압정', reason='far trap at 6 m')
        self.combat(self.t)
        self.e.apply_status(self.t, '수렁', source='gm')
        self.e.apply_status(self.t, '구속', source='gm')
        self.t.custom_conditions['씨뿌리기'] = {'type': 'custom_condition', 'name': '씨뿌리기', 'effect': 'lose max_hp/10 at turn start; user gains same'}
        self.e.apply_status(self.b, '수렁', source='gm')
        self.use(self.t, self.t, self.waltz['id'])
        record = self.pirouette('clear')
        self.assertEqual((record['traps_removed'], sorted(record['cured'])), (2, ['구속', '수렁', '씨뿌리기']))
        self.assertEqual(sorted(HAZARDS.ensure(self.e)), [(7, 7)])
        self.assertEqual((self.t.conditions & {'수렁', '구속'}, '씨뿌리기' in self.t.custom_conditions, '수렁' in self.b.conditions), (set(), False, True))
        self.assertEqual(len(self.t.spec[D.KEY]['pirouettes']), 1)
        self.valid()
        self.restore('t', 'b')
        self.assertEqual(sorted(HAZARDS.ensure(self.e)), [(7, 7)])

    # ------------------------------------------------------------ Passing Waltz
    def test_passing_waltz_moves_the_trainers_dance_stages_to_one_chosen_ally_within_three_meters_for_one_ap(self):
        self.scene(D.WALTZ)
        self.combat(self.t)
        ap = AP.available(self.t)
        self.answer(D.WALTZ_PROMPT, self.far.entity_id)   # not an ally: the Waltz does not activate, the dance stands
        self.use(self.t, self.t, self.waltz['id'])
        self.assertEqual((self.t.stages['atk'], self.far.stages['atk'], AP.available(self.t)), (1, 0, ap))
        self.assertIn('invalid choice', self.t.spec[D.KEY]['waltzes'][-1]['declined'])
        self.next_turn(self.t)
        self.next_turn(self.t)
        self.q.pos = (5, 1)   # 4 m from the dancer: not a candidate
        self.answer(D.WALTZ_PROMPT, self.q.entity_id)
        self.use(self.t, self.t, self.waltz['id'])
        self.assertEqual((self.t.stages['atk'], self.q.stages['atk'], AP.available(self.t)), (2, 0, ap))
        self.assertEqual(self.t.spec[D.KEY]['waltzes'][-1]['candidates'], [self.p.entity_id])
        self.next_turn(self.t)
        self.next_turn(self.t)
        self.q.pos = (4, 1)   # 3 m: a candidate
        self.use(self.t, self.t, self.waltz['id'])
        self.assertEqual((self.t.stages, self.q.stages['atk'], self.q.stages['spe'], self.p.stages['atk']), ({'atk': 2, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 2}, 1, 1, 0))
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(getattr(self.t, '_action_history', []).count('free'), 1)
        record = self.t.spec[D.KEY]['waltzes'][-1]
        self.assertEqual((record['ally_id'], record['ap'], record['use']['move_id'], record['use']['user_id'], record['clause_id']),
                         (self.q.entity_id, 1, self.waltz['id'], self.t.entity_id, 'input/ch04-trainer-classes.md:2318-2323'))
        self.assertEqual(sorted(record['candidates']), sorted([self.p.entity_id, self.q.entity_id]))
        self.assertEqual(self.t.spec[D.KEY]['last_dance']['raised'], ['atk', 'spe'])   # the trainer still performed the dance
        self.next_turn(self.t)
        self.next_turn(self.t)
        self.answer(D.WALTZ_PROMPT, None)
        self.use(self.t, self.t, self.waltz['id'])
        self.assertEqual((self.t.stages['atk'], self.q.stages['atk'], AP.available(self.t), self.t.spec[D.KEY]['waltzes'][-1]['declined']), (3, 1, ap - 1, 'player declined'))
        self.valid()
        self.restore('t', 'p', 'q')
        self.assertEqual(self.q.stages['atk'], 1)
        forged = self.t.spec[D.KEY]['waltzes'][0]
        forged['ally_id'] = self.b.entity_id
        self.invalid('one of its observed candidates')

    def test_passing_waltz_triggers_only_for_own_pokemon_with_own_tempo_or_spinning_dance_and_needs_ap_and_the_feature(self):
        self.scene(D.WALTZ)
        self.answer(D.WALTZ_PROMPT, self.q.entity_id)
        self.combat(self.p, count=25)
        ap = AP.available(self.t)
        self.use(self.p, self.p, 'move/용의춤')   # Own Tempo Pokemon: the trainer may pass the stages
        self.assertEqual((self.p.stages['atk'], self.p.stages['spe'], self.q.stages['atk'], self.q.stages['spe'], AP.available(self.t)), (0, 0, 1, 1, ap - 1))
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.q, initiative_count=22)
        self.answer(D.WALTZ_PROMPT, self.p.entity_id)
        self.use(self.q, self.q, 'move/칼춤')   # a Pokemon without either Ability never triggers it
        self.assertEqual((self.q.stages['atk'], self.p.stages['atk'], AP.available(self.t), len(self.t.spec[D.KEY]['waltzes'])), (3, 0, ap - 1, 1))
        # Without AP the trigger lapses: the user keeps its stages and nothing is charged.
        AP.charge(self.t, AP.available(self.t), mode='spend')
        for _ in range(2):   # Dragon Dance is EOT: skip the Pokemon's next turn
            self.e.end_of_turn(self.e._active_turn_actor)
            self.e.end_round()
            self.e.start_round(self.e.everyone)
            self.e.start_of_turn(self.p, initiative_count=25)
        self.answer(D.WALTZ_PROMPT, self.q.entity_id)
        self.use(self.p, self.p, 'move/용의춤')
        self.assertEqual((self.p.stages['atk'], self.q.stages['atk'], AP.available(self.t)), (1, 3, 0))
        self.assertIn('no AP', self.t.spec[D.KEY]['waltzes'][-1]['declined'])
        self.valid()
        # Another trainer's Pokemon and a Dancer without Passing Waltz do not trigger it.
        other = self.add('other dancer', 'trainer', (10, 10), classes=[], feats=[], edges=[], items={}, money=100, moves=[], speed=28)
        self.dancer(trainer=other, ability='마이페이스')
        r = self.add('other partner', 'pokemon', (10, 9), trainer_id=other.entity_id, abilities=['회전춤'], speed=19, tutor_points=5, moves=['move/용의춤'])
        s = self.add('other second', 'pokemon', (11, 10), trainer_id=other.entity_id, abilities=[], speed=17, tutor_points=5)
        self.answer(D.WALTZ_PROMPT, s.entity_id)
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(r, initiative_count=19)
        ap_other = AP.available(other)
        self.use(r, r, 'move/용의춤')
        self.assertEqual((r.stages['atk'], s.stages['atk'], AP.available(other), other.spec.get(D.KEY, {}).get('waltzes', [])), (1, 0, ap_other, []))
        self.valid()

    def test_passing_waltz_and_pirouette_combine_on_one_dance_and_survive_restore(self):
        self.scene(D.PIROUETTE, D.WALTZ)
        self.answer(D.WALTZ_PROMPT, self.p.entity_id)
        self.combat(self.t)
        self.use(self.t, self.t, self.waltz['id'])
        self.assertEqual((self.t.stages['atk'], self.p.stages['atk'], self.p.stages['spe']), (0, 1, 1))
        self.rejected(lambda: self.pirouette('stage', stat='atk'), 'cannot raise a stat the triggering Dance Move raised')
        record = self.pirouette('stage', stat='def')
        self.assertEqual((record['stat'], self.t.stages['def']), ('def', 1))
        self.valid()
        self.restore('t', 'p', 'q', 'b')
        st = self.t.spec[D.KEY]
        self.assertEqual((st['last_dance']['pirouette'], st['waltzes'][-1]['ally_id'], len(st['pirouettes'])), ('stage', self.p.entity_id, 1))
        self.assertEqual((self.p.stages['atk'], self.t.stages['def']), (1, 1))


if __name__ == '__main__':
    unittest.main()
