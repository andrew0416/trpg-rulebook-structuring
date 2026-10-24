"""Native source composition, user-selected allocation, expiry and restoration boundaries."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Combatant
from builder import build_pokemon
from native_scenario_fixture import assert_rejected_unchanged
import book_chef_fixture as FIX
import chef_cooking as CHEF
import food_effects as FOOD
import temporary_hp as TEMP
import state_codec as CODEC
import custom_condition_effects as CUSTOM
import test_category2_ability_state_projection as FORM_FIX
import test_manual_equipment as EQUIPMENT_FIX


class TemporaryHPCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.r = self.rules

    def choice(self, engine, name, mode):
        key = 'temporary_hp_' + name
        engine.rulings.answers = [row for row in engine.rulings.answers if row['key'] != key]
        engine.rulings.add_answer(key, {'mode': mode, 'reason': 'explicit test campaign rule', 'scope': 'campaign'},
                                 reason='explicit test campaign rule', scope='campaign')

    def unset_lifetime_default(self):
        configured = deepcopy(TEMP.policy(self.rules))
        configured['composition']['additive_lifetime'] = None
        self.enterContext(patch.object(self.rules, '_temporary_hp_policy', configured))

    def world(self, *, feats=(CHEF.CLASS, CHEF.ACCENTUATED), lunch=True, liked=True, stored_foods=False):
        abilities = ['도시락통 [Playtest]'] if lunch else []
        if stored_foods:
            abilities.append(FOOD.CORE_GLUTTONY)
        world = FIX.scene(self.rules, feats=feats,
            pokemon_nature=FIX.nature_for(self.rules, '짠맛', 'liked') if liked else None,
            abilities=abilities)
        return world['engine'], world['chef'], world['partner'], world['foe']

    def buy(self, engine, actor, item):
        actor.spec.setdefault('items', {})[item] = actor.spec.get('items', {}).get(item, 0) + 1
        return engine.use_item(actor, item, actor, duration_minutes=1,
                               duration_reason='actual food intake')['buff_id']

    def chocolate(self, engine, actor):
        buff = self.buy(engine, actor, '초코바')
        engine.consume_food_buff(actor, buff_id=buff, action_kind='free', action_reason='actual Food Buff trade-in')
        return FIX.receipt(actor)

    def salty(self, engine, chef, actor, foe, *, cooked=True):
        if cooked:
            batch = FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')
            buff = FIX.serve(engine, chef, batch['batch_id'], actor)['buff_id']
        else:
            buff = self.buy(engine, actor, 'item/짠맛-서프라이즈')
        engine.consume_food_buff(actor, buff_id=buff)
        engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'), set_damage=True)
        return FIX.receipt(actor)

    def lunch(self, engine, actor, receipt):
        return engine.activate_ability(actor, '도시락통 [Playtest]',
                                       (actor, {'receipt_sequence': receipt['sequence']}))

    def rows(self, actor):
        return actor.custom_conditions[TEMP.STATE]['contributions']

    def test_hits_foreign_max_zero_and_partial_delta_pay_once(self):
        for foreign in (20, 3):
            with self.subTest(foreign=foreign):
                engine, chef, actor, foe = self.world(feats=(CHEF.CLASS, CHEF.HITS))
                receipt = self.chocolate(engine, actor)
                TEMP.grant(engine, actor, foreign)
                event = FIX.pending(engine, chef, CHEF.HITS)[0]
                before = deepcopy(actor.custom_conditions[TEMP.STATE])
                result = engine.resolve_class_actor_state_action(chef, event['id'], use=True)
                self.assertEqual((actor.temp_hp, result['temporary_hp_granted'], chef.spec['ap_spent']),
                                 (max(foreign, 12), max(0, 12 - foreign), 1))
                self.assertNotIn('temporary_hp_blocked_reason', result)
                if foreign == 20:
                    self.assertEqual(actor.custom_conditions[TEMP.STATE], before)
                else:
                    self.assertEqual(self.rows(actor)[0]['source']['receipt_sequence'], receipt['sequence'])
                assert_rejected_unchanged(engine,
                    lambda: engine.resolve_class_actor_state_action(chef, event['id'], use=True), reason_pattern='pending class')

    def test_salty_taste_cannot_add_to_foreign_hp_and_lower_grant_has_no_source_right(self):
        engine, chef, actor, foe = self.world()
        batch = FIX.cook(engine, chef, recipe='leftovers', taste='짠맛')
        buff = FIX.serve(engine, chef, batch['batch_id'], actor)['buff_id']
        FIX.battle(engine, actor)
        TEMP.grant(engine, actor, 20)
        before = deepcopy(actor.custom_conditions[TEMP.STATE])
        engine.consume_food_buff(actor, buff_id=buff, action_kind='free', action_reason='actual Leftovers trade-in')
        self.assertEqual((actor.temp_hp, FIX.receipt(actor)['taste_bonus']['gained']), (20, 0))
        self.assertEqual(actor.custom_conditions[TEMP.STATE], before)
        TEMP.absorb(engine, actor, 18)
        result = self.lunch(engine, actor, FIX.receipt(actor))
        self.assertEqual(actor.temp_hp, engine.tick(actor))
        self.assertEqual(result['details']['temporary_hp'], engine.tick(actor) - 2)
        self.assertEqual(len(self.rows(actor)), 1)

    def test_native_food_taste_hits_and_lunchbox_keep_exact_sources(self):
        engine, chef, actor, foe = self.world(feats=(CHEF.CLASS, CHEF.HITS, CHEF.ACCENTUATED))
        receipt = self.salty(engine, chef, actor, foe)
        self.assertEqual(actor.temp_hp, 15)
        event = FIX.pending(engine, chef, CHEF.HITS)[0]
        engine.resolve_class_actor_state_action(chef, event['id'], use=True)
        self.assertEqual(actor.temp_hp, 27)
        result = self.lunch(engine, actor, receipt)
        self.assertEqual((actor.temp_hp, result['details']['temporary_hp']), (27 + engine.tick(actor), engine.tick(actor)))
        self.assertEqual([row['source']['kind'] for row in self.rows(actor)], ['food', 'chef_taste', 'chef_hits', 'lunchbox'])
        self.assertTrue(engine.validate_state()['valid'])

    def test_new_food_after_chef_and_hits_preserves_reverse_stack_exception(self):
        engine, chef, actor, foe = self.world(feats=(CHEF.CLASS, CHEF.HITS, CHEF.ACCENTUATED, CHEF.AFTERTASTE))
        left = FIX.cook(engine, chef, recipe='leftovers', taste='짠맛')
        served = FIX.serve(engine, chef, left['batch_id'], actor)
        FIX.battle(engine, actor)
        engine.consume_food_buff(actor, buff_id=served['buff_id'], action_kind='free', action_reason='actual Leftovers trade-in')
        engine.resolve_class_actor_state_action(chef, FIX.pending(engine, chef, CHEF.HITS)[0]['id'], use=True)
        engine.resolve_class_actor_state_action(chef, FIX.pending(engine, chef, CHEF.AFTERTASTE)[0]['id'], use=True)
        self.assertEqual(actor.temp_hp, 17)
        buff = actor.buffs[0]
        engine.consume_food_buff(actor, buff_id=buff['id'])
        engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'), set_damage=True)
        receipt = FIX.receipt(actor)
        self.assertEqual((receipt['benefit']['gained'], receipt['taste_bonus']['gained'], actor.temp_hp), (10, 5, 32))
        self.assertNotIn(FOOD.CHEF_RECEIVED_CHOICE, actor.spec)
        self.assertEqual(len(actor.spec['food_consumption_receipts']), 2)
        FIX.decline_all(engine, chef)
        self.assertTrue(engine.validate_state()['valid'])

    def test_lunchbox_foreign_zero_partial_and_empty_are_successes(self):
        for foreign in (20, 3, 0):
            with self.subTest(foreign=foreign):
                engine, chef, actor, foe = self.world(feats=())
                receipt = self.chocolate(engine, actor)
                TEMP.grant(engine, actor, foreign)
                result = self.lunch(engine, actor, receipt)
                self.assertEqual((actor.temp_hp, result['details']['temporary_hp']),
                                 (max(foreign, engine.tick(actor)), max(0, engine.tick(actor) - foreign)))
                self.assertEqual(FIX.receipt(actor)['ability_native_claims'], ['ability/도시락통-playtest'])
                assert_rejected_unchanged(engine, lambda: self.lunch(engine, actor, receipt), reason_pattern='already used|frequency')

    def test_lunchbox_only_adds_the_triggering_food_receipt_remaining_balance(self):
        for spent, different in ((0, False), (4, False), (10, False), (12, False), (0, True)):
            with self.subTest(spent=spent, different=different):
                engine, chef, actor, foe = self.world(feats=())
                receipt = self.salty(engine, chef, actor, foe, cooked=False)
                self.assertEqual(actor.temp_hp, 10)
                hp = actor.hp
                engine.take_damage(actor, spent)
                if different:
                    receipt = self.chocolate(engine, actor)
                self.lunch(engine, actor, receipt)
                expected = max(10, engine.tick(actor)) if different else max(0, 10 - spent) + engine.tick(actor)
                self.assertEqual((actor.temp_hp, actor.hp), (expected, hp - max(0, spent - 10)))
                self.assertTrue(engine.validate_state()['valid'])

    def test_fifo_default_and_explicit_lifo_change_only_surviving_sources(self):
        for mode, expected_kinds in (('fifo', ['food', 'chef_taste']), ('lifo', ['food'])):
            with self.subTest(mode=mode):
                engine, chef, actor, foe = self.world()
                self.choice(engine, 'additive_lifetime', 'per_grant')
                self.choice(engine, 'allocation', mode)
                self.salty(engine, chef, actor, foe)
                hp = actor.hp
                engine.take_damage(actor, 5)
                self.assertEqual((actor.temp_hp, actor.hp), (10, hp))
                self.assertEqual([row['source']['kind'] for row in self.rows(actor)], expected_kinds)
                receipt = self.chocolate(engine, actor)
                self.lunch(engine, actor, receipt)
                self.assertEqual(actor.temp_hp, 5 + engine.tick(actor) if mode == 'fifo' else 10)
                self.assertTrue(engine.validate_state()['valid'])
        self.assertEqual(TEMP.policy(self.rules)['composition']['allocation']['mode'], 'fifo')
        self.assertIn('not specified', TEMP.policy(self.rules)['composition']['allocation']['reason'])

    def test_distinct_additive_lifetimes_follow_explicit_policy_and_restore(self):
        for mode, expected in (('per_grant', 10), ('refresh_pool', 15)):
            with self.subTest(mode=mode):
                engine, chef, actor, foe = self.world()
                self.choice(engine, 'additive_lifetime', mode)
                self.salty(engine, chef, actor, foe)
                # FIFO removes the Food contribution, leaving the five-point Chef contribution.
                engine.take_damage(actor, 10)
                self.assertEqual(actor.temp_hp, 5)
                buff = self.buy(engine, actor, 'item/짠맛-서프라이즈')
                engine.advance_time(140)
                engine.consume_food_buff(actor, buff_id=buff)
                engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'), set_damage=True)
                self.assertEqual(actor.temp_hp, 15)
                loaded, actors = FIX.restore(self.rules, engine)
                for current, target in ((engine, actor), (loaded, actors[actor.entity_id])):
                    current.advance_time(100)
                    self.assertEqual(target.temp_hp, expected)
                    self.assertEqual([row['source']['kind'] for row in self.rows(target)],
                                     ['food'] if mode == 'per_grant' else ['chef_taste', 'food'])
                    self.assertEqual(TEMP.absorb(current, target, 12), max(0, 12 - expected))
                    self.assertEqual(target.temp_hp, max(0, expected - 12))

    def test_selected_default_keeps_native_lunchbox_and_chef_ages_fifo_and_restored_expiry(self):
        for override in (None, 'refresh_pool'):
            with self.subTest(override=override):
                engine, chef, actor, foe = self.world(stored_foods=True)
                if override is not None:
                    self.choice(engine, 'additive_lifetime', override)
                batch = FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')
                salty = FIX.serve(engine, chef, batch['batch_id'], actor)['buff_id']
                chocolate = self.buy(engine, actor, '초코바')
                engine.consume_food_buff(actor, buff_id=salty)
                engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'), set_damage=True)
                first = FIX.receipt(actor)
                self.assertEqual(actor.temp_hp, 15)
                hp = actor.hp
                engine.take_damage(actor, 12)
                self.assertEqual([(r['source']['kind'], r['amount']) for r in self.rows(actor)],
                                 [('chef_taste', 3)])
                engine.advance_time(40)
                engine.consume_food_buff(actor, buff_id=chocolate, action_kind='free',
                                         action_reason='actual Food Buff trade-in')
                second = FIX.receipt(actor)
                self.lunch(engine, actor, second)
                tick = engine.tick(actor)
                engine.take_damage(actor, 1)
                self.assertEqual((actor.hp, actor.temp_hp), (hp, 2 + tick))
                self.assertEqual([(r['source']['kind'], r['source']['receipt_sequence'], r['amount'])
                                  for r in self.rows(actor)],
                                 [('chef_taste', first['sequence'], 2), ('lunchbox', second['sequence'], tick)])
                expected_clock = [260, 300] if override is None else [300, 300]
                self.assertEqual([r['minimum_seconds'] for r in self.rows(actor)], expected_clock)
                selected = actor.custom_conditions[TEMP.STATE]['composition_policies']['additive_lifetime']
                self.assertEqual(selected['mode'], override or 'per_grant')
                engine.gm.snapshot('differently-aged-food-sources')
                loaded, actors = FIX.restore(self.rules, engine)
                engine.take_damage(actor, actor.temp_hp)
                engine.gm.restore('differently-aged-food-sources', reason='restore actual source balances and ages')
                for current, target in ((engine, actor), (loaded, actors[actor.entity_id])):
                    current.begin_encounter(current.everyone)
                    current.advance_time(900)
                    self.assertEqual([r['minimum_seconds'] for r in self.rows(target)], expected_clock)
                    current.end_encounter()
                    current.advance_time(259)
                    self.assertEqual(target.temp_hp, 2 + tick)
                    current.advance_time(1)
                    self.assertEqual(target.temp_hp, tick if override is None else 2 + tick)
                    if override is None:
                        self.assertEqual([r['source']['kind'] for r in self.rows(target)], ['lunchbox'])
                    current.advance_time(39)
                    self.assertEqual(target.temp_hp, tick if override is None else 2 + tick)
                    current.advance_time(1)
                    self.assertEqual(target.temp_hp, 0)
                    self.assertNotIn(TEMP.STATE, target.custom_conditions)
                    self.assertTrue(current.validate_state()['valid'])

    def test_consumption_clear_recall_and_gm_restore_cannot_resurrect_source_rights(self):
        engine, chef, actor, foe = self.world()
        receipt = self.salty(engine, chef, actor, foe)
        engine.take_damage(actor, 4)
        self.assertEqual([row['amount'] for row in self.rows(actor)], [6, 5])
        engine.gm.snapshot('partial')
        loaded, actors = FIX.restore(self.rules, engine)
        self.assertEqual(self.rows(actors[actor.entity_id]), self.rows(actor))
        engine.lose_hp(actor, 12)
        self.assertEqual(actor.temp_hp, 0)
        self.assertNotIn(TEMP.STATE, actor.custom_conditions)
        engine.gm.restore('partial', reason='restore known remaining contributions')
        self.assertEqual([row['amount'] for row in self.rows(actor)], [6, 5])
        engine.gm.set_temp_hp(actor, 20, reason='explicit replacement')
        self.lunch(engine, actor, FIX.receipt(actor))
        self.assertEqual(actor.temp_hp, 20)
        engine.gm.set_temp_hp(actor, 0, reason='explicit clear')
        self.assertNotIn(TEMP.STATE, actor.custom_conditions)
        TEMP.grant(engine, actor, 8)
        engine.gm.recall(actor, reason='actual return to owner ball')
        self.assertEqual(actor.temp_hp, 0)
        self.assertNotIn(TEMP.STATE, actor.custom_conditions)

    def test_legacy_event_history_does_not_invent_remaining_food_or_chef_sources(self):
        engine, chef, actor, foe = self.world()
        self.salty(engine, chef, actor, foe)
        actor.custom_conditions[TEMP.STATE].pop('contributions')
        loaded, actors = FIX.restore(self.rules, engine)
        saved = actors[actor.entity_id]
        self.lunch(loaded, saved, FIX.receipt(saved))
        self.assertEqual(saved.temp_hp, 15)
        self.assertNotIn('contributions', saved.custom_conditions[TEMP.STATE])
        TEMP.grant(loaded, saved, 20)
        self.assertEqual(self.rows(saved)[0]['source'], None)
        self.assertEqual(self.rows(saved)[0]['amount'], 20)

    def test_armed_salty_noop_never_blocks_the_actual_foe_attack(self):
        engine, chef, actor, foe = self.world(feats=())
        buff = self.buy(engine, actor, 'item/짠맛-서프라이즈')
        engine.consume_food_buff(actor, buff_id=buff)
        TEMP.grant(engine, actor, 20)
        FIX.battle(engine, foe)
        before = actor.hp + actor.temp_hp
        with patch.object(engine, 'd20', return_value=10):
            engine.use_move(foe, actor, 'move/몸통박치기', set_damage=True)
        self.assertLess(actor.hp + actor.temp_hp, before)
        self.assertEqual(foe.move_uses['move/몸통박치기'], 1)
        self.assertEqual(FIX.receipt(actor)['benefit']['gained'], 0)
        self.assertIsNone(FIX.receipt(actor)['benefit']['blocked_reason'])
        self.assertFalse(actor.buffs)
        self.assertNotIn(FOOD.CHEF_RECEIVED_CHOICE, actor.spec)

    def test_actual_heal_block_consumes_selected_salty_with_no_gain_and_lunchbox_rejects_atomically(self):
        engine, chef, actor, foe = self.world(feats=(CHEF.CLASS, CHEF.HITS))
        buff = self.buy(engine, actor, 'item/짠맛-서프라이즈')
        engine.consume_food_buff(actor, buff_id=buff)
        definition = CUSTOM.definition(self.rules, 'move/회복봉인')
        engine.apply_effect(foe, actor, definition['raw'], nat=10, hit=True, dealt=0, src='move/회복봉인')
        FIX.battle(engine, foe)
        with patch.object(engine, 'd20', return_value=10):
            engine.use_move(foe, actor, 'move/몸통박치기', set_damage=True)
        self.assertEqual(foe.move_uses['move/몸통박치기'], 1)
        receipt = FIX.receipt(actor)
        self.assertEqual((receipt['benefit']['gained'], receipt['benefit']['blocked_reason']), (0, 'healing_block'))
        self.assertFalse(actor.buffs)
        event = FIX.pending(engine, chef, CHEF.HITS)[0]
        hits = engine.resolve_class_actor_state_action(chef, event['id'], use=True)
        self.assertEqual((hits['temporary_hp_granted'], hits['temporary_hp_blocked_reason'], chef.spec['ap_spent']),
                         (0, 'healing_block', 1))
        assert_rejected_unchanged(engine, lambda: self.lunch(engine, actor, receipt), reason_pattern='blocked')
        self.assertNotIn('ability_native_claims', receipt)

    def test_form_lock_after_arming_preserves_attack_and_records_actual_block(self):
        engine, chef, actor, foe = self.world(feats=())
        buff = self.buy(engine, actor, 'item/짠맛-서프라이즈')
        engine.consume_food_buff(actor, buff_id=buff)
        engine.gm.set_ability(actor, '어군', True, reason='actual owned ability')
        FORM_FIX.AbilityStateProjectionTests.forms(self, engine, actor, ('단독의모습', '군집의모습'), 'ability/어군')
        FIX.battle(engine, actor)
        engine.activate_ability_state(actor, 'ability/어군', choice='군집의모습', reason='actual daily form')
        before = actor.hp + actor.temp_hp
        engine.end_of_turn(actor)
        engine.start_of_turn(foe, initiative_count=19)
        with patch.object(engine, 'd20', return_value=10):
            engine.use_move(foe, actor, 'move/몸통박치기', set_damage=True)
        self.assertLess(actor.hp + actor.temp_hp, before)
        self.assertEqual(foe.move_uses['move/몸통박치기'], 1)
        self.assertEqual(FIX.receipt(actor)['benefit']['blocked_reason'], 'temporary_hp_restriction')
        self.assertFalse(actor.buffs)
        self.assertTrue(engine.validate_state()['valid'])

    def test_soulless_is_actual_block_not_successful_max_noop(self):
        engine, chef, actor, foe = self.world(feats=())
        shell = Combatant(self.rules, build_pokemon(self.rules, '껍질몬', 20,
            abilities=['불가사의부적', '도시락통 [Playtest]'], moves=[]))
        engine.gm.add_combatant(shell, reason='actual Soulless Pokemon')
        receipt = self.chocolate(engine, shell)
        self.assertEqual(TEMP.blocked_reason(shell), 'soulless')
        self.assertEqual(TEMP.grant(engine, shell, 30), 0)
        assert_rejected_unchanged(engine, lambda: self.lunch(engine, shell, receipt), reason_pattern='blocked')
        self.assertNotIn('ability_native_claims', receipt)

    def test_mixed_unknown_outside_interval_survives_restore_without_inventing_time(self):
        engine, chef, actor, foe = self.world()
        self.salty(engine, chef, actor, foe)
        TEMP.unknown_interval(actor, 200, outside_combat=True)
        engine.advance_time(150)
        self.assertEqual([(row['minimum_seconds'], row['maximum_seconds']) for row in self.rows(actor)],
                         [(-50, 150), (-50, 150)])
        loaded, actors = FIX.restore(self.rules, engine)
        restored = actors[actor.entity_id]
        self.assertEqual(self.rows(restored), self.rows(actor))
        assert_rejected_unchanged(loaded, lambda: loaded.take_damage(restored, 1),
                                  reason_pattern='temporary HP expiry')
        loaded.gm.set_temp_hp(restored, 15, duration_seconds=10, reason='observed remaining clock')
        loaded.advance_time(10)
        self.assertEqual(restored.temp_hp, 0)

    def test_actual_heavy_equipment_loss_consumes_common_contribution_balance(self):
        EQUIPMENT_FIX.Tests.setUpClass()
        fixture = EQUIPMENT_FIX.Tests()
        engine, actor, other, item = fixture.fixture()
        actor.injuries = 5
        TEMP.grant(engine, actor, 9)
        hp = actor.hp
        result = engine.equip_equipment(actor, item)
        self.assertEqual((actor.hp, actor.temp_hp), (hp, 4))
        self.assertEqual(self.rows(actor)[0]['amount'], 4)
        self.assertEqual(engine._heavy_events[result['heavy_event']]['status'], 'applied')
        self.assertTrue(engine.validate_state()['valid'])

    def test_malformed_balance_source_receipt_and_policy_reject_before_persistence(self):
        engine, chef, actor, foe = self.world()
        self.salty(engine, chef, actor, foe)
        state = deepcopy(actor.custom_conditions[TEMP.STATE])
        for mutate in (lambda rows: rows[0].update(amount=99),
                       lambda rows: rows[0]['source'].update(receipt_sequence=99),
                       lambda rows: rows[0]['source'].update(rule_id=CHEF.HITS)):
            actor.custom_conditions[TEMP.STATE] = deepcopy(state)
            mutate(self.rows(actor))
            with self.assertRaises(ValueError):
                CODEC.dump_engine(engine)
        actor.custom_conditions[TEMP.STATE] = deepcopy(state)
        self.choice(engine, 'allocation', 'invalid')
        before = deepcopy((actor.temp_hp, actor.custom_conditions))
        with self.assertRaisesRegex(ValueError, 'requires mode'):
            TEMP.absorb(engine, actor, 1)
        self.assertEqual((actor.temp_hp, actor.custom_conditions), before)


if __name__ == '__main__':
    unittest.main()
