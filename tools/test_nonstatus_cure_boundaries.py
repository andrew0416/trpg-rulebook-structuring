"""Selected-source status cures preserve Seed and Perish's distinct end events.

Prepared native regressions; importing or executing this module is deferred to
the final stable integration check. Sources: C07-140/162, CSV Moves 301/306/307/
355/539, and ch04:2240-2245. Perish Body is a directly coupled producer.
"""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
import athlete as ATHLETE
import condition_instances as CONDITIONS
import optional_move_modes as MODES
import status_sets as STATUSES
import test_book_athlete_acquisition as ATHLETE_FIX
import test_category2_native_move_batches as MOVE_FIX
import test_category2_perish_body as BODY_FIX
from native_scenario_fixture import assert_rejected_unchanged

SEED = 'move/씨뿌리기'
SONG = 'move/멸망의노래'
COUNT = '멸망 카운트'


class AdrenalineStatusBoundaryTests(ATHLETE_FIX.AthleteScene, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def triggered(self, *conditions):
        self.whole()
        self.exercise()
        for condition in conditions:
            self.e.apply_status(self.t, condition)
        maximum = self.t.base_max_hp
        self.e.gm.set_temp_hp(self.t, 0, reason='no temporary HP before actual crossing')
        self.e.gm.set_hp(self.t, value=maximum // 2 + 1, reason='actual current HP')
        self.e.lose_hp(self.t, 1, source='actual hazard')
        self.assertIsNotNone(ATHLETE.adrenaline_trigger(self.t))

    def test_other_afflictions_are_rejected_without_consuming_trigger_action_or_frequency(self):
        for condition in ('둔화', '구속', '넘어짐', '취약', '완전-실명'):
            with self.subTest(condition=condition):
                self.setup()
                self.triggered(condition)
                self.assertNotIn(condition, STATUSES.afflictions(self.t))
                self.rejected(lambda: ATHLETE.adrenaline_rush(self.e, self.t, cure=[condition]),
                              'up to two actual current status afflictions')
                self.assertIsNotNone(ATHLETE.adrenaline_trigger(self.t))
                self.assertIn(condition, self.t.conditions)

    def test_persistent_and_volatile_afflictions_can_be_cured_together(self):
        self.triggered('화상', '마비', '혼란')
        receipt = ATHLETE.adrenaline_rush(self.e, self.t, cure=['화상', '혼란'])
        self.assertEqual(receipt['cured'], ['화상', '혼란'])
        self.assertEqual(self.t.conditions & {'화상', '마비', '혼란'}, {'마비'})
        self.assertEqual(self.activations(self.t)[ATHLETE.ADRENALINE]['used'], 1)
        self.restore()
        self.valid()

    def test_actual_seed_and_count_are_rejected_as_adrenaline_cure_choices(self):
        self.whole()
        self.exercise()
        self.combat(self.p, count=25)
        self.use(self.p, self.t, SEED)
        self.next_turn(self.p, count=25)
        self.use(self.p, self.t, SONG)
        maximum = self.t.base_max_hp
        self.e.gm.set_temp_hp(self.t, 0, reason='no temporary HP before actual crossing')
        self.e.gm.set_hp(self.t, value=maximum // 2 + 1, reason='actual current HP')
        self.e.lose_hp(self.t, 1, source='actual hazard')
        for condition in ('씨뿌리기', COUNT):
            self.rejected(lambda: ATHLETE.adrenaline_rush(self.e, self.t, cure=[condition]),
                          'up to two actual current status afflictions')

    def test_native_mental_herb_and_all_status_cure_keep_nonstatus_states(self):
        self.combat(self.p, count=25)
        self.use(self.p, self.t, SEED)
        self.next_turn(self.p, count=25)
        self.use(self.p, self.t, SONG)
        self.e.end_of_turn(self.p)
        self.e.end_encounter()
        self.t.spec.setdefault('items', {})['멘탈허브'] = 1
        snack = self.e.use_item(self.t, '멘탈허브', self.t, duration_minutes=1,
                               duration_reason='actual Extended herb intake')
        self.e.apply_status(self.t, '혼란')
        self.e.apply_effect(self.t, self.t, {'type': 'cure_all_status', 'target': 'target'},
                            20, True, 0, 'gm/actual-all-status-cure')
        self.assertNotIn('혼란', self.t.conditions)
        self.assertTrue({'씨뿌리기', COUNT} <= self.t.conditions)
        self.e.apply_status(self.t, '혼란')
        self.combat(self.t, count=20)
        self.e.consume_food_buff(self.t, buff_id=snack['buff_id'], action_kind='swift',
                                 action_reason='actual Mental Herb activation')
        self.assertNotIn('혼란', self.t.conditions)
        self.assertTrue({'씨뿌리기', COUNT} <= self.t.conditions)
        self.restore()
        self.valid()


class NonstatusMoveBoundaryTests(unittest.TestCase):
    initial_moves = [SEED, SONG, 'move/병상첨병', 'move/천추지한', 'move/백귀야행', 'move/고속스핀']
    turn = MOVE_FIX.NativeMoveBatchTests.turn
    restore = MOVE_FIX.NativeMoveBatchTests.restore

    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        MOVE_FIX.NativeMoveBatchTests.setUp(self)

    def seed_and_count(self):
        self.e.use_move(self.p, self.t, SEED)
        self.turn(self.p, new_round=True)
        self.e.use_move_on(self.p, self.t, SONG, self.e.everyone)
        self.assertTrue({'씨뿌리기', COUNT} <= self.t.conditions)

    def test_seed_and_count_do_not_qualify_hex_or_bitter_malice_or_spend_scene_bonus(self):
        for move_id, base in (('move/병상첨병', 7), ('move/천추지한', 6)):
            with self.subTest(move=move_id):
                self.setUp()
                self.seed_and_count()
                self.turn(self.p, new_round=True)
                self.e.d20 = lambda: 10
                self.assertEqual(STATUSES.afflictions(self.t), ())
                self.assertEqual(self.e.damage_base(self.p, self.r.move(move_id), target=self.t), base)
                self.e.use_move(self.p, self.t, move_id, set_damage=True)
                self.assertNotIn('lim:conditional-db:' + move_id + ':scene', self.p.counters)

    def test_seed_and_count_do_not_qualify_infernal_parade_optional_mode(self):
        self.seed_and_count()
        self.turn(self.p, new_round=True)
        self.e.gm.choose_optional_move_effect(self.p, 'move/백귀야행', reason='actual optional mode choice')
        assert_rejected_unchanged(self.e,
            lambda: self.e.use_move_on(self.p, self.t, 'move/백귀야행', self.e.everyone),
            reason_pattern='previously afflicted')
        self.assertIsNone(MODES.history(self.p)[0]['use'])
        self.e.apply_status(self.t, '독')
        self.e.use_move_on(self.p, self.t, 'move/백귀야행', self.e.everyone, set_damage=True)
        self.assertIsNotNone(MODES.history(self.p)[0]['use'])

    def test_rest_cures_real_status_but_keeps_seed_and_perish_countdown(self):
        self.seed_and_count()
        self.e.gm.set_move(self.t, 'move/잠자기', reason='actual known Rest')
        self.e.apply_status(self.t, '화상')
        self.turn(self.t)
        self.e.use_move(self.t, self.t, 'move/잠자기')
        self.assertNotIn('화상', self.t.conditions)
        self.assertTrue({'씨뿌리기', COUNT, '잠듦'} <= self.t.conditions)
        self.assertEqual(CONDITIONS.records(self.t, COUNT)[0]['applications'][-1]['remaining'], 2)
        self.turn(self.t, new_round=True)
        self.assertEqual(CONDITIONS.records(self.t, COUNT)[0]['applications'][-1]['remaining'], 1)
        self.turn(self.t, new_round=True)
        self.assertEqual(self.t.hp, 0)
        self.assertFalse({'씨뿌리기', COUNT} & self.t.conditions)
        self.assertTrue(self.restore().validate_state()['valid'])

    def test_breather_removes_perish_but_preserves_seed(self):
        self.seed_and_count()
        self.turn(self.t)
        result = self.e.take_breather(self.t, request_id='source-specific-breather',
            path=[(11, 10), (12, 10)], retreat_reason='observed safe retreat from the enemy',
            save_dc=1, save_reason='table DC for this test', save_cost='full', fixed_save=20)
        self.assertTrue(result['completed'])
        self.assertIn('씨뿌리기', self.t.conditions)
        self.assertNotIn(COUNT, self.t.conditions)
        self.assertTrue(self.restore().validate_state()['valid'])

    def test_recall_and_faint_remove_both_states_only_from_that_holder(self):
        for event in ('recall', 'faint'):
            with self.subTest(event=event):
                self.setUp()
                self.seed_and_count()
                if event == 'recall':
                    self.e.gm.recall(self.t, reason='actual target recall')
                else:
                    self.e.lose_hp(self.t, self.t.hp, source='actual HP loss', unpreventable=True)
                self.assertFalse({'씨뿌리기', COUNT} & self.t.conditions)
                self.assertIn(COUNT, self.p.conditions)
                self.assertTrue(self.restore().validate_state()['valid'])

    def test_encounter_end_clears_volatile_but_preserves_explicit_seed_and_count_lifetimes(self):
        self.seed_and_count()
        self.e.apply_status(self.t, '혼란')
        identities = {name: CONDITIONS.records(self.t, name)[0]['id'] for name in ('씨뿌리기', COUNT)}
        self.e.end_of_turn(self.p)
        self.e.end_encounter()
        self.assertNotIn('혼란', self.t.conditions)
        for name, identity in identities.items():
            self.assertIn(name, self.t.conditions)
            self.assertEqual(CONDITIONS.records(self.t, name)[0]['id'], identity)
        restored = self.restore()
        self.assertTrue(restored.validate_state()['valid'])
        target = next(c for c in restored.everyone if c.entity_id == self.t.entity_id)
        self.assertTrue({'씨뿌리기', COUNT} <= target.conditions)

    def test_rapid_spin_still_removes_seed_by_its_explicit_source_effect(self):
        self.seed_and_count()
        self.e.gm.set_move(self.t, 'move/고속스핀', reason='actual known Rapid Spin')
        self.turn(self.t)
        self.e.use_move(self.t, self.p, 'move/고속스핀', set_damage=True)
        self.assertNotIn('씨뿌리기', self.t.conditions)
        self.assertIn(COUNT, self.t.conditions)
        self.assertTrue(self.restore().validate_state()['valid'])


class PerishBodyStatusBoundaryTests(unittest.TestCase):
    setUp = BODY_FIX.PerishBodyTests.setUp
    actor = BODY_FIX.PerishBodyTests.actor
    watch = BODY_FIX.PerishBodyTests.watch
    offer = BODY_FIX.PerishBodyTests.offer
    choose = BODY_FIX.PerishBodyTests.choose
    activate = BODY_FIX.PerishBodyTests.activate
    count = BODY_FIX.PerishBodyTests.count
    turn = BODY_FIX.PerishBodyTests.turn

    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def test_actual_ability_count_is_nonstatus_and_survives_generic_cure_and_encounter_end(self):
        self.activate()
        for actor in (self.a, self.t):
            self.assertEqual(self.count(actor)['effect']['class'], 'effect')
            self.assertNotIn(COUNT, STATUSES.afflictions(actor))
            self.e.apply_effect(actor, actor, {'type': 'cure_all_status', 'target': 'target'},
                                20, True, 0, 'gm/actual-all-status-cure')
            self.assertIn(COUNT, actor.conditions)
        self.e.end_of_turn(self.a)
        self.e.end_encounter()
        identities = self.a.entity_id, self.t.entity_id
        saved = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        self.e = Engine.import_state(Rules(ROOT, ruleset='core'), saved)
        index = {actor.entity_id: actor for actor in self.e.everyone}
        self.a, self.t = (index[identity] for identity in identities)
        self.assertTrue(self.e.validate_state()['valid'])
        for actor in (self.a, self.t):
            self.assertIn(COUNT, actor.conditions)


if __name__ == '__main__':
    unittest.main()
