"""Native declarations for Chef's pre-damage-RNG composition validation."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
from native_scenario_fixture import assert_rejected_unchanged
import test_temporary_hp_composition as BASE
import book_chef_fixture as FIX
import chef_cooking as CHEF
import food_effects as FOOD
import temporary_hp as TEMP
import custom_condition_effects as CUSTOM


class TemporaryHPPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    setUp = BASE.TemporaryHPCompositionTests.setUp
    world = BASE.TemporaryHPCompositionTests.world
    choice = BASE.TemporaryHPCompositionTests.choice
    buy = BASE.TemporaryHPCompositionTests.buy
    chocolate = BASE.TemporaryHPCompositionTests.chocolate
    lunch = BASE.TemporaryHPCompositionTests.lunch
    rows = BASE.TemporaryHPCompositionTests.rows
    unset_lifetime_default = BASE.TemporaryHPCompositionTests.unset_lifetime_default

    def ready_pair(self, *, cooked=False):
        engine, chef, actor, foe = self.world(stored_foods=True)
        batch = FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')
        first = FIX.serve(engine, chef, batch['batch_id'], actor)['buff_id']
        if cooked:
            batch = FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')
            second = FIX.serve(engine, chef, batch['batch_id'], actor)['buff_id']
        else:
            second = self.buy(engine, actor, 'item/짠맛-서프라이즈')
        engine.consume_food_buff(actor, buff_id=first)
        engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'), set_damage=True)
        engine.consume_food_buff(actor, buff_id=second)
        return engine, chef, actor, foe

    def reject_before_damage(self, engine, actor, foe):
        before = deepcopy((engine.log_lines, actor.hp, actor.temp_hp, actor.spec,
                           actor.buffs, actor.custom_conditions))
        with patch.object(Engine, 'roll_expr', autospec=True, side_effect=Engine.roll_expr) as dice, \
                patch.object(TEMP, 'food_source', side_effect=AssertionError('preflight minted source rights')):
            assert_rejected_unchanged(engine,
                lambda: engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기')),
                reason_pattern='temporary HP additive_lifetime')
        dice.assert_not_called()
        self.assertEqual((engine.log_lines, actor.hp, actor.temp_hp, actor.spec,
                          actor.buffs, actor.custom_conditions), before)

    def test_standalone_food_missing_and_invalid_policy_reject_before_rng_and_all_mutation(self):
        self.unset_lifetime_default()
        for mode in (None, 'invalid'):
            with self.subTest(mode=mode):
                engine, chef, actor, foe = self.ready_pair()
                TEMP.absorb(engine, actor, 10)  # actual surviving assigned Salty contribution
                engine.advance_time(40)
                if mode is not None:
                    self.choice(engine, 'additive_lifetime', mode)
                self.reject_before_damage(engine, actor, foe)

    def test_standalone_assigned_salty_missing_and_invalid_policy_reject_before_rng(self):
        self.unset_lifetime_default()
        for mode in (None, 'invalid'):
            with self.subTest(mode=mode):
                engine, chef, actor, foe = self.ready_pair(cooked=True)
                self.choice(engine, 'allocation', 'lifo')
                TEMP.absorb(engine, actor, 5)  # Food 10 remains; next Food 10 is an equal no-op.
                engine.advance_time(40)
                engine.rulings.answers = [r for r in engine.rulings.answers if r['key'] != 'temporary_hp_additive_lifetime']
                if mode is not None:
                    self.choice(engine, 'additive_lifetime', mode)
                self.reject_before_damage(engine, actor, foe)

    def test_standalone_explicit_lifetime_alternatives_keep_outcomes_and_json_gm_restore(self):
        for mode, expected in ((None, 10), ('per_grant', 10), ('refresh_pool', 15)):
            with self.subTest(mode=mode):
                engine, chef, actor, foe = self.ready_pair()
                TEMP.absorb(engine, actor, 10)
                engine.advance_time(40)
                if mode is not None:
                    self.choice(engine, 'additive_lifetime', mode)
                engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'))
                self.assertEqual(actor.temp_hp, 15)
                engine.gm.snapshot('accepted-chef-composition')
                loaded, actors = FIX.restore(self.rules, engine)
                engine.lose_hp(actor, 15)
                engine.gm.restore('accepted-chef-composition', reason='restore actual accepted Chef receipt')
                for current, target in ((engine, actor), (loaded, actors[actor.entity_id])):
                    current.advance_time(260)
                    self.assertEqual(target.temp_hp, expected)
                    self.assertEqual([r['source']['kind'] for r in self.rows(target)],
                                     ['chef_taste', 'food'] if mode == 'refresh_pool' else ['food'])
                    self.assertTrue(current.validate_state()['valid'])

    def test_null_policy_does_not_reject_ordinary_max_lower_equal_or_equal_age(self):
        self.unset_lifetime_default()
        for before in (10, 20):
            with self.subTest(ordinary=before):
                engine, chef, actor, foe = self.world(feats=())
                buff = self.buy(engine, actor, 'item/짠맛-서프라이즈')
                engine.consume_food_buff(actor, buff_id=buff)
                TEMP.grant(engine, actor, before)
                engine.advance_time(40)
                old = deepcopy(actor.custom_conditions[TEMP.STATE])
                engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'))
                self.assertEqual((actor.temp_hp, FIX.receipt(actor)['benefit']['gained']), (before, 0))
                self.assertEqual(actor.custom_conditions[TEMP.STATE], old)
        engine, chef, actor, foe = self.ready_pair()
        TEMP.absorb(engine, actor, 10)
        engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'))
        self.assertEqual(actor.temp_hp, 15)  # compatible, equal-age increase

    def test_null_policy_keeps_aged_compatible_equal_noop_and_actual_block(self):
        self.unset_lifetime_default()
        for blocked in (False, True):
            with self.subTest(blocked=blocked):
                engine, chef, actor, foe = self.ready_pair()
                if blocked:
                    TEMP.absorb(engine, actor, 10)
                    definition = CUSTOM.definition(self.rules, 'move/회복봉인')
                    engine.apply_effect(foe, actor, definition['raw'], nat=10, hit=True, dealt=0, src='move/회복봉인')
                engine.advance_time(40)
                old = deepcopy(actor.custom_conditions[TEMP.STATE])
                engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'))
                self.assertEqual(FIX.receipt(actor)['benefit']['gained'], 0)
                self.assertEqual(actor.custom_conditions[TEMP.STATE], old)
                self.assertEqual(FIX.receipt(actor)['benefit']['blocked_reason'], 'healing_block' if blocked else None)

    def test_food_replacement_precedes_assigned_salty_and_drops_incompatible_aged_lunchbox(self):
        self.unset_lifetime_default()
        engine, chef, actor, foe = self.world(stored_foods=True)
        batch = FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')
        buff = FIX.serve(engine, chef, batch['batch_id'], actor)['buff_id']
        receipt = self.chocolate(engine, actor)
        self.lunch(engine, actor, receipt)
        self.assertLess(actor.temp_hp, 10)
        engine.consume_food_buff(actor, buff_id=buff)
        engine.advance_time(40)
        engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'))
        actual = FIX.receipt(actor)
        self.assertEqual(actor.temp_hp, 15)
        self.assertEqual([r['source']['kind'] for r in self.rows(actor)], ['food', 'chef_taste'])
        self.assertTrue(all(r['source']['receipt_sequence'] == actual['sequence'] for r in self.rows(actor)))
        self.assertTrue(engine.validate_state()['valid'])

    def test_actual_berry_receipt_shift_preserves_food_taste_and_lunchbox_receipt_identity(self):
        for use_food in (False, True):
            with self.subTest(use_food=use_food):
                engine, chef, actor, foe = self.world(stored_foods=True)
                batch = FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')
                salty = FIX.serve(engine, chef, batch['batch_id'], actor)['buff_id']
                berry = self.buy(engine, actor, 'item/카리열매')
                engine.consume_food_buff(actor, buff_id=salty)
                engine.consume_food_buff(actor, buff_id=berry)
                old = len(actor.spec.get('food_consumption_receipts', []))
                engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'))
                receipts = actor.spec['food_consumption_receipts']
                berry_receipt, food_receipt = receipts[-2:]
                self.assertEqual((berry_receipt['sequence'], food_receipt['sequence']), (old + 1, old + 2))
                self.assertEqual((berry_receipt['buff_id'], food_receipt['buff_id']), (berry, salty))
                self.assertTrue(all(r['source']['receipt_sequence'] == food_receipt['sequence'] for r in self.rows(actor)))
                self.lunch(engine, actor, food_receipt if use_food else berry_receipt)
                self.assertEqual(actor.temp_hp, 15 + engine.tick(actor) if use_food else 15)
                self.assertTrue(engine.validate_state()['valid'])

    def test_outgoing_salty_dumplings_healing_block_still_checks_legacy_clock_before_rng(self):
        engine, chef, actor, foe = self.world(feats=FIX.ALL_FEATURES)
        spicy = FIX.cook(engine, chef, recipe='tasty_snack', snack='매운맛 랩')
        mixed = FIX.cook(engine, chef, recipe='dumplings',
                         ingredient_1={'batch_id': spicy['batch_id']},
                         ingredient_2={'item': 'item/먹다남은음식'}, taste='짠맛')
        served = FIX.serve(engine, chef, mixed['batch_id'], actor)
        buff = FOOD.get_buff(actor, served['buff_id'])
        self.assertEqual((FOOD._chef_payload(buff)['trigger'], FOOD._chef_payload(buff)['benefit']['type']),
                         ('attack', 'bonus_damage'))
        self.assertEqual(CHEF.bonus_plan(engine, actor, buff)['kind'], 'temporary_hp')
        FIX.battle(engine, actor)
        engine.consume_food_buff(actor, buff_id=served['buff_id'])
        TEMP.grant(engine, actor, 20)
        definition = CUSTOM.definition(self.rules, 'move/회복봉인')
        engine.apply_effect(foe, actor, definition['raw'], nat=10, hit=True, dealt=0, src='move/회복봉인')
        # An imported old clock is representable, but cannot be used as an observed outside clock.
        state = actor.custom_conditions[TEMP.STATE]
        state.pop('contributions')
        state.pop('clock_basis')
        state.update(minimum_seconds=100, maximum_seconds=200)
        loaded, actors = FIX.restore(self.rules, engine)
        target, opponent = actors[actor.entity_id], actors[foe.entity_id]
        self.assertEqual(TEMP.blocked_reason(target), 'healing_block')
        before = deepcopy((loaded.log_lines, target.spec, target.buffs, target.custom_conditions))
        with patch.object(Engine, 'roll_expr', autospec=True, side_effect=Engine.roll_expr) as dice, \
                patch.object(TEMP, 'food_source', side_effect=AssertionError('preflight minted source rights')):
            assert_rejected_unchanged(loaded,
                lambda: loaded.roll_damage(target, opponent, self.rules.move('move/몸통박치기')),
                reason_pattern='temporary HP expiry needs legacy clock-basis reconciliation')
        dice.assert_not_called()
        self.assertEqual((loaded.log_lines, target.spec, target.buffs, target.custom_conditions), before)


if __name__ == '__main__':
    unittest.main()
