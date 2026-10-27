"""Two observed native NameErrors; retain real payment, identity and restore paths."""
from copy import copy, deepcopy
import json
import unittest

import test_book_focused_command_full as _focused_fixture
import test_category2_csv_remaining_item_contracts as _capability_fixture
from engine import Engine
from native_scenario_fixture import assert_rejected_unchanged
import commander as COMMANDER
import csv_item_capability_contracts as CAP
import focused_command as FOCUSED
import priority_limited as PRIORITY
import training_features as TRAINING
import world_entities as WORLD


class VoiceTrainingNameErrorTests(_focused_fixture.CommanderFixture, unittest.TestCase):
    world = _focused_fixture.FocusedCommandFullTests.world
    battle = _focused_fixture.FocusedCommandFullTests.battle
    close = _focused_fixture.FocusedCommandFullTests.close
    voice = _focused_fixture.FocusedCommandFullTests.voice
    cold = _focused_fixture.FocusedCommandFullTests.cold

    def test_native_voice_training_authorizes_only_its_paid_targets_and_survives_restore(self):
        for edition in ('core', 'local_csv'):
            with self.subTest(edition=edition):
                self.world()
                self.acquire(TRAINING.FOCUSED)
                self.acquire(FOCUSED.VOICE)
                self.battle()
                self.voice(TRAINING.FOCUSED, options={'edition': edition})
                self.assertEqual((self.a.budget['standard'], self.a.budget['swift']), (0, 0))
                self.assertFalse(PRIORITY.records(self.a))
                for restored in (False, True):
                    if restored:
                        self.cold()
                    self.valid()
                    self.assertEqual([TRAINING.bonus(p, 'accuracy') for p in (self.p, self.p2)], [1, 1])
                    self.assertEqual(TRAINING.bonus(self.third, 'accuracy'), 0)
                    before = self.e.export_state()
                    for partner in (self.p, self.p2):
                        payment = TRAINING.active(partner)[0]['order_id']
                        self.assertTrue(COMMANDER.training_authority(self.a, partner, TRAINING.FOCUSED, payment))
                        self.assertTrue(COMMANDER.training_authority_id(self.a, partner.entity_id, TRAINING.FOCUSED, payment))
                        self.assertFalse(COMMANDER.training_authority(self.a, self.third, TRAINING.FOCUSED, payment))
                        self.assertFalse(COMMANDER.training_authority_id(self.a, partner.entity_id, TRAINING.INSPIRED, payment))
                        self.assertFalse(COMMANDER.training_authority(self.a, partner, TRAINING.FOCUSED, 'unpaid/voice'))
                        self.assertFalse(COMMANDER.training_authority(self.b, partner, TRAINING.FOCUSED, payment))
                    self.assertEqual(self.e.export_state(), before)
                self.close()
                self.e.end_round()
                self.e.start_round(self.e.everyone)
                self.e.start_of_turn(self.a)
                self.assertEqual([TRAINING.bonus(p, 'accuracy') for p in (self.p, self.p2)], [0, 0])

    def test_failed_native_voice_delivery_rolls_back_training_authority_and_both_actions(self):
        self.world()
        self.acquire(TRAINING.FOCUSED)
        self.acquire(FOCUSED.VOICE)
        self.hears(self.p2, False)
        self.battle()
        self.rejected(lambda: self.voice(TRAINING.FOCUSED, options={'edition': 'local_csv'}),
                      'communication was not delivered')
        self.assertNotIn(COMMANDER.ACTIVATIONS, self.a.spec)
        self.assertFalse(PRIORITY.records(self.a))
        self.assertEqual((self.a.budget['standard'], self.a.budget['swift']), (1, 1))
        self.assertEqual([TRAINING.bonus(p, 'accuracy') for p in (self.p, self.p2)], [0, 0])
        self.assertFalse(COMMANDER.training_authority(self.a, self.p, TRAINING.FOCUSED, 'unpaid/voice'))

    def test_voice_authority_rejects_changed_activation_without_resealing_it(self):
        self.world()
        self.acquire(TRAINING.FOCUSED)
        self.acquire(FOCUSED.VOICE)
        self.battle()
        self.voice(TRAINING.FOCUSED, options={'edition': 'local_csv'})
        payment = TRAINING.active(self.p)[0]['order_id']
        before = self.e.export_state()
        row = self.a.spec[COMMANDER.ACTIVATIONS][-1]
        original = deepcopy(row['orders'])
        try:
            row['orders'][1]['target_id'] = self.third.entity_id
            with self.assertRaisesRegex(ValueError, 'Commander training activation changed'):
                COMMANDER.training_authority(self.a, self.third, TRAINING.FOCUSED, payment)
        finally:
            row['orders'] = original
        self.assertEqual(self.e.export_state(), before)


class NavigationNameErrorTests(unittest.TestCase):
    setUpClass = classmethod(_capability_fixture.RemainingCsvItemContractTests.setUpClass.__func__)
    pokemon = _capability_fixture.RemainingCsvItemContractTests.pokemon
    trainer = _capability_fixture.RemainingCsvItemContractTests.trainer
    fixture = _capability_fixture.RemainingCsvItemContractTests.fixture

    def test_native_fractional_navigation_keeps_ceiling_cooperative_clock_and_cold_restore(self):
        actor = self.pokemon('nameerror/navigator', capabilities=('에스퍼 네비게이터',))
        partner = self.pokemon('nameerror/partner', capabilities=('에스퍼 네비게이터',))
        engine = self.fixture(actor, partner)
        row = CAP.start_navigation(engine, actor, 'route/fractional', lightyears=1.1)
        self.assertEqual((row['dc'], row['total'], row['completed']), (17, 0, False))
        before = engine.export_state()
        self.assertEqual(CAP.start_navigation(engine, actor, 'route/fractional', lightyears=1.1), row)
        self.assertEqual(engine.export_state(), before)
        row['dc'] = 999
        self.assertEqual(actor.spec[CAP.STATE]['navigation_routes']['route/fractional']['dc'], 17)
        CAP.navigation_check(engine, actor, 'route/fractional', skill='지각', total=8, check_id='first')
        self.assertEqual(engine.elapsed_seconds, 300)
        self.assertEqual(CAP.navigation_jump(actor, 'route/fractional'),
                         {'safe': False, 'total': 8, 'dc': 17, 'gm_consequence_required': True})
        CAP.navigation_contribute(engine, actor, partner, 'route/fractional', skill='집중', total=9, check_id='second')
        self.assertEqual(engine.elapsed_seconds, 600)
        saved = json.loads(json.dumps(engine.export_state(), ensure_ascii=False))
        engine = Engine.import_state(self.r, saved)
        actor, partner = [WORLD.actor_index(engine)[p.entity_id] for p in (actor, partner)]
        self.assertEqual(CAP.navigation_jump(actor, 'route/fractional'),
                         {'safe': True, 'total': 17, 'dc': 17, 'gm_consequence_required': False})
        before = engine.export_state()
        CAP.navigation_contribute(engine, actor, partner, 'route/fractional', skill='집중', total=9, check_id='second')
        self.assertEqual(engine.export_state(), before)
        self.assertTrue(engine.validate_state()['valid'])

    def test_native_navigation_rejects_invalid_input_and_route_rebinding_without_mutation(self):
        actor = self.pokemon('nameerror/guarded', capabilities=('에스퍼 네비게이터',))
        ordinary = self.pokemon('nameerror/ordinary')
        trainer = self.trainer('nameerror/trainer', capabilities=('에스퍼 네비게이터',))
        engine = self.fixture(trainer, actor, ordinary)
        for distance in (0, -1, float('nan'), float('inf'), True, '1'):
            with self.subTest(distance=distance):
                assert_rejected_unchanged(engine,
                    lambda: CAP.start_navigation(engine, actor, 'route/invalid', lightyears=distance),
                    reason_pattern='positive distance')
        assert_rejected_unchanged(engine,
            lambda: CAP.start_navigation(engine, ordinary, 'route/ordinary', lightyears=1),
            reason_pattern='actual capability required')
        assert_rejected_unchanged(engine,
            lambda: CAP.start_navigation(engine, trainer, 'route/trainer', lightyears=1),
            reason_pattern='actual Pokemon')
        assert_rejected_unchanged(engine,
            lambda: CAP.start_navigation(engine, copy(actor), 'route/copied', lightyears=1),
            reason_pattern='registered')
        CAP.start_navigation(engine, actor, 'route/fixed', lightyears=1.1)
        assert_rejected_unchanged(engine,
            lambda: CAP.start_navigation(engine, actor, 'route/fixed', lightyears=2),
            reason_pattern='cannot change distance')
        before = engine.export_state()
        route = actor.spec[CAP.STATE]['navigation_routes']['route/fixed']
        try:
            route['dc'] = 16
            with self.assertRaisesRegex(ValueError, 'navigation distance or DC changed'):
                CAP.validate_actor(actor)
        finally:
            route['dc'] = 17
        self.assertEqual(engine.export_state(), before)


if __name__ == '__main__':
    unittest.main()
