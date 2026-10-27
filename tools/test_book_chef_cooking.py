"""Chef recipes: Tasty Snacks, Leftovers, Preserves, Hearty Meal and Dumplings through the shared recipe owners."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from native_scenario_fixture import assert_rejected_unchanged
import book_chef_fixture as FIX
import action_points as AP
import arithmetic_policy as M
import chef_cooking as CHEF
import common_checks as C
import crafting_resources as R
import downtime as DOWNTIME
import food_effects as FOOD
import state_codec as CODEC
import world_entities as W


class ChefCookingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ruleset import RuleFilter
        profile = deepcopy(RuleFilter.load(ROOT, 'all').profile)
        profile['exclude_units'] = list(profile.get('exclude_units', [])) + ['chef/dumplings-no-nesting-errata']
        selected = RuleFilter(profile, 'all-with-original-book-dumplings')
        with patch.object(RuleFilter, 'load', return_value=selected):
            cls.rules = Rules(ROOT, ruleset='all')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        FOOD.buff_policy(self.rules)
        CHEF.definitions(self.rules)

    def rejected(self, engine, operation, pattern):
        return assert_rejected_unchanged(engine, operation, reason_pattern=pattern)

    def batch(self, trainer, batch_id):
        return trainer.spec['chef_batches'][batch_id]

    def test_tasty_snacks_cost_100_extended_time_and_carry_the_corresponding_taste_only_with_accentuated_taste(self):
        world = FIX.scene(self.rules)
        engine, chef = world['engine'], world['chef']
        tasty = CHEF.definitions(self.rules)['tasty_snacks']
        for index, (item_id, taste) in enumerate(tasty.items(), 1):
            with self.subTest(item=item_id):
                money = chef.spec['money']
                result = FIX.cook(engine, chef, recipe='tasty_snack', snack=item_id)
                batch = self.batch(chef, result['batch_id'])
                self.assertEqual((batch['kind'], batch['item_id'], batch['count'], batch['units']), ('tasty_snack', item_id, 1, 1))
                self.assertEqual(batch['taste'], {'taste': taste, 'source': CHEF.ACCENTUATED, 'assigned_by': chef.entity_id, 'basis': 'cooking'})
                self.assertEqual(batch['payload'], FOOD.chef_effect(self.rules, item_id))
                self.assertEqual((result['money_spent'], chef.spec['money']), (100, money - 100))
                self.assertEqual(engine.activity_job_status(result['job_id'])['status'], 'complete')
                self.assertEqual(engine.elapsed_seconds, 300 * index)
                self.assertEqual(chef.spec['resource_transformations'][-1]['operation'], 'cook_chef_food')
                self.assertIn(CHEF.CLASS, result['recipe_sources'])
        self.assertEqual(FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈', taste='짠맛')['batch']['taste']['taste'], '짠맛')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈', taste='단맛'), 'corresponding Taste')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='tasty_snack', snack='item/초코바'), 'six printed basic snacks')
        plain = FIX.scene(self.rules, feats=(CHEF.CLASS,), seed=9)
        result = FIX.cook(plain['engine'], plain['chef'], recipe='tasty_snack', snack='매운맛 랩')
        self.assertIsNone(result['batch']['taste'])
        self.rejected(plain['engine'], lambda: FIX.cook(plain['engine'], plain['chef'], recipe='tasty_snack', snack='매운맛 랩', taste='매운맛'), 'Accentuated Taste')
        self.assertTrue(engine.validate_state()['valid'])

    def test_recipe_permission_feature_gates_tool_money_and_combat_fail_without_payment_or_time(self):
        world = FIX.scene(self.rules, feats=(CHEF.CLASS, CHEF.HITS))
        engine, chef = world['engine'], world['chef']
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='leftovers'), 'recipe provider')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='preserves', origin='item/오랭열매'), 'recipe provider')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'item': 'item/먹다남은음식'}, ingredient_2={'item': 'item/먹다남은음식'}), 'different items|Leftovers, Preserves')
        chef.spec['items']['요리 세트'] = 0
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='hearty_meal', ingredients='big_mushroom', units=1), 'required equipment')
        chef.spec['items']['요리 세트'] = 1
        chef.spec['money'] = 50
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='tasty_snack', snack='단맛 과자'), 'insufficient')
        chef.spec['money'] = 500
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='hearty_meal', ingredients='balm_mushroom', units=6), 'Hearty Meal count')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='hearty_meal', ingredients='truffle', units=1), 'printed option')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='sandwich'), 'Chef recipe must be one of')
        FIX.battle(engine, chef)
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='tasty_snack', snack='단맛 과자'), 'active encounter')
        engine.end_encounter()
        self.assertEqual(FIX.cook(engine, chef, recipe='hearty_meal', ingredients='big_mushroom', units=2)['count'], 2)
        self.assertTrue(engine.validate_state()['valid'])

    def test_leftovers_and_preserves_keep_their_source_effects_two_units_and_reject_unsupported_origins(self):
        world = FIX.scene(self.rules)
        engine, chef = world['engine'], world['chef']
        money = chef.spec['money']
        left = FIX.cook(engine, chef, recipe='leftovers', taste='단맛')
        self.assertEqual((left['batch']['item_id'], left['batch']['payload'], left['batch']['units'], chef.spec['money']), (CHEF.LEFTOVERS_ITEM, {'kind': 'turn_heal', 'denominator': 16}, 1, money - 100))
        self.assertEqual(left['batch']['taste']['taste'], '단맛')
        berries = chef.spec['items']['오랭열매']
        pres = FIX.cook(engine, chef, recipe='preserves', origin='item/오랭열매', taste='신맛')
        self.assertEqual((pres['batch']['origin_item'], pres['batch']['payload'], pres['batch']['count'], chef.spec['items']['오랭열매'], chef.spec['money']),
                         ('item/오랭열매', {'kind': 'heal', 'amount': 5, 'berry': True}, 2, berries - 1, money - 150))
        herb = FIX.cook(engine, chef, recipe='preserves', origin='item/파워풀허브')
        self.assertEqual(herb['batch']['payload'], {'kind': 'herb_skip_setup'})
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='preserves', origin='item/작은버섯'), 'actual held origin instance')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='preserves', origin='item/상처약'), 'Berry, Herb or Mushroom')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='preserves', origin='item/오카열매', taste='쓴맛'), 'assigned Taste must be one of')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='preserves', origin='item/라즈열매'), 'source-specific consumer')
        self.assertTrue(engine.validate_state()['valid'])

    def test_served_units_reach_actual_digestion_buffs_with_provenance_and_exhaust_the_batch(self):
        world = FIX.scene(self.rules)
        engine, chef, partner, foe = world['engine'], world['chef'], world['partner'], world['foe']
        pres = FIX.cook(engine, chef, recipe='preserves', origin='item/오랭열매', taste='신맛')
        batch_id = pres['batch_id']
        first = FIX.serve(engine, chef, batch_id, partner)
        buff = FOOD.get_buff(partner, first['buff_id'])
        self.assertEqual((buff['item'], buff['effect'], buff['effect_source']), ('item/오랭열매', {'kind': 'heal', 'amount': 5, 'berry': True}, 'item/오랭열매'))
        self.assertEqual(buff['taste_assignment']['taste'], '신맛')
        self.assertEqual(buff['chef_batch'], {'batch_id': batch_id, 'kind': 'preserves', 'recipe': CHEF.PRESERVES, 'cook_id': chef.entity_id, 'created_at': 300})
        self.assertEqual(first['item_stock'], {'kind': 'chef_batch', 'item_id': 'item/오랭열매', 'batch_id': batch_id, 'count': 1, 'unit': 1})
        self.assertEqual(self.batch(chef, batch_id)['count'], 1)
        self.rejected(engine, lambda: FIX.serve(engine, chef, batch_id, partner), 'cannot gain another Digestion Buff')
        second = FIX.serve(engine, chef, batch_id, foe)
        self.assertEqual(self.batch(chef, batch_id)['count'], 0)
        self.rejected(engine, lambda: FIX.serve(engine, chef, batch_id, chef), 'exhausted')
        self.rejected(engine, lambda: FIX.serve(engine, chef, 'chef-batch:nobody:1', chef), 'owned Chef batch')
        partner.hp = 1
        before = engine.export_state()
        self.assertIsInstance(engine.consume_food_buff(partner, buff_id=first['buff_id'], action_kind='free', action_reason='actual berry benefit'), C.PendingDecision)
        self.assertEqual(engine.export_state(), before)  # the sour taste bonus needs the GM lifetime ruling first
        FIX.ruling(engine, 'encounter_end')
        result = engine.consume_food_buff(partner, buff_id=first['buff_id'], action_kind='free', action_reason='actual berry benefit')
        self.assertEqual((result['healed'], partner.hp, FIX.receipt(partner)['taste_bonus']['kind']), (5, 6, 'evasion_damaging'))
        receipt = FIX.receipt(partner)
        self.assertEqual((receipt['buff_id'], receipt['taste_assignment']['taste'], receipt['chef_batch']['batch_id']), (first['buff_id'], '신맛', batch_id))
        loaded, actors = FIX.restore(self.rules, engine)
        self.assertEqual(actors[chef.entity_id].spec['chef_batches'][batch_id]['served'], self.batch(chef, batch_id)['served'])
        self.assertEqual(FOOD.get_buff(actors[foe.entity_id], second['buff_id'])['chef_batch']['batch_id'], batch_id)
        self.assertTrue(loaded.validate_state()['valid'])
        self.batch(chef, batch_id)['payload'] = {'kind': 'heal', 'amount': 50, 'berry': True}
        self.assertFalse(engine.validate_state()['valid'])

    def test_hearty_meal_options_units_trainer_only_two_max_ap_until_extended_rest_one_at_a_time_and_freshness(self):
        world = FIX.scene(self.rules)
        engine, chef, partner = world['engine'], world['chef'], world['partner']
        options = {row['id']: row for row in CHEF.definitions(self.rules)['recipes'][CHEF.HEARTY]['ingredients']}
        self.assertEqual(set(options), {'tiny_mushrooms', 'big_mushroom', 'balm_mushroom', 'power_herbs', 'white_herbs', 'mental_herbs'})
        mushrooms = chef.spec['items']['작은버섯']
        meal = FIX.cook(engine, chef, recipe='hearty_meal', ingredients='tiny_mushrooms', units=5, taste='짠맛')
        self.assertEqual((meal['batch']['count'], chef.spec['items']['작은버섯'], meal['batch']['item_id'], meal['batch']['taste']['taste']), (5, mushrooms - 2, CHEF.HEARTY_ITEM, '짠맛'))
        herbs = FIX.cook(engine, chef, recipe='hearty_meal', ingredients='power_herbs', units=1)
        self.assertEqual(chef.spec['items']['파워풀허브'], 0)
        self.rejected(engine, lambda: FIX.serve(engine, chef, meal['batch_id'], partner), 'consumed by Trainers')
        maximum = AP.maximum(chef)
        result = FIX.serve(engine, chef, meal['batch_id'])
        self.assertEqual((result['status'], result['ap_bonus'], result['until'], AP.maximum(chef)), ('hearty_meal', 2, 'extended_rest', maximum + 2))
        self.assertEqual(chef.spec[CHEF.MEAL]['batch_id'], meal['batch_id'])
        self.assertEqual(self.batch(chef, meal['batch_id'])['count'], 4)
        self.rejected(engine, lambda: FIX.serve(engine, chef, herbs['batch_id']), 'one Hearty Meal at a time')
        loaded, actors = FIX.restore(self.rules, engine)
        self.assertEqual(AP.maximum(actors[chef.entity_id]), maximum + 2)
        self.assertTrue(loaded.validate_state()['valid'])
        DOWNTIME.rest(engine, chef, 60)
        self.assertEqual(AP.maximum(chef), maximum + 2)
        DOWNTIME.extended_rest(engine, chef, 8)
        self.assertEqual((AP.maximum(chef), chef.spec.get(CHEF.MEAL)), (maximum, None))
        self.rejected(engine, lambda: FIX.serve(engine, chef, meal['batch_id']), '20 minutes')
        fresh = FIX.cook(engine, chef, recipe='hearty_meal', ingredients='big_mushroom', units=1)
        engine.unresolved_time_intervals.append({'round': 0, 'reason': 'unobserved interval'})
        before = engine.export_state()
        self.assertIsInstance(FIX.serve(engine, chef, fresh['batch_id']), C.PendingDecision)
        self.assertEqual(engine.export_state(), before)
        chef.spec[CHEF.MEAL] = {'source': CHEF.HEARTY_ITEM, 'recipe': CHEF.HEARTY, 'ap_bonus': 4, 'ends': 'extended_rest', 'eaten_at': 0, 'batch_id': 'x', 'cook_id': chef.entity_id, 'taste': None}
        self.assertFalse(engine.validate_state()['valid'])

    def test_dumplings_mix_two_different_ingredients_into_one_composite_snack_and_reject_undefined_mixes(self):
        world = FIX.scene(self.rules)
        engine, chef = world['engine'], world['chef']
        tasty = FIX.cook(engine, chef, recipe='tasty_snack', snack='매운맛 랩')
        pres = FIX.cook(engine, chef, recipe='preserves', origin='item/오랭열매')
        left = FIX.cook(engine, chef, recipe='leftovers')
        oka = FIX.cook(engine, chef, recipe='preserves', origin='item/오카열매')
        herb = FIX.cook(engine, chef, recipe='preserves', origin='item/파워풀허브')
        meal = FIX.cook(engine, chef, recipe='hearty_meal', ingredients='balm_mushroom', units=1)
        inventory = chef.spec['items']['먹다남은음식']
        mixed = FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'batch_id': tasty['batch_id']}, ingredient_2={'item': 'item/먹다남은음식'}, taste='매운맛')
        batch = self.batch(chef, mixed['batch_id'])
        self.assertEqual(batch['payload'], {'kind': 'chef_composite', 'components': [
            {'item': 'item/매운맛-랩', 'effect': FOOD.chef_effect(self.rules, 'item/매운맛-랩')},
            {'item': CHEF.LEFTOVERS_ITEM, 'effect': {'kind': 'turn_heal', 'denominator': 16}}]})
        self.assertEqual((batch['item_id'], batch['count'], self.batch(chef, tasty['batch_id'])['count'], chef.spec['items']['먹다남은음식']), ('item/매운맛-랩', 1, 0, inventory - 1))
        self.assertEqual(mixed['trigger_components'], ['chef_snack'])
        second = FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'batch_id': pres['batch_id']}, ingredient_2={'batch_id': left['batch_id']})
        self.assertEqual([part['item'] for part in second['batch']['components']], ['item/오랭열매', CHEF.LEFTOVERS_ITEM])
        self.assertEqual(second['trigger_components'], [])
        self.assertEqual((self.batch(chef, pres['batch_id'])['count'], self.batch(chef, left['batch_id'])['count']), (1, 0))
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'batch_id': pres['batch_id']}, ingredient_2={'batch_id': pres['batch_id']}), 'different items')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'item': 'item/먹다남은음식'}, ingredient_2={'item': 'item/먹다남은음식'}), 'different items')
        # The printed Book allows a Chef-made Dumplings as the first Snack;
        # the CSV/May errata prohibition has its own actual source selection.
        nested = FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'batch_id': mixed['batch_id']}, ingredient_2={'batch_id': pres['batch_id']})
        self.assertEqual(len(nested['batch']['payload']['components']), 3)
        self.assertEqual(self.batch(chef, mixed['batch_id'])['count'], 0)
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'batch_id': meal['batch_id']}, ingredient_2={'item': 'item/먹다남은음식'}), 'not a Snack ingredient')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'item': 'item/먹다남은음식'}, ingredient_2={'batch_id': tasty['batch_id']}), 'leftovers, preserves required|exhausted')
        herb_mix = FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'batch_id': herb['batch_id']}, ingredient_2={'item': 'item/먹다남은음식'})
        self.assertEqual(herb_mix['trigger_components'], ['herb_skip_setup'])
        spicy = FIX.cook(engine, chef, recipe='tasty_snack', snack='매운맛 랩')
        self.rejected(engine, lambda: FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'batch_id': spicy['batch_id']}, ingredient_2={'batch_id': oka['batch_id']}), 'two different trigger-bound')
        self.assertTrue(engine.validate_state()['valid'])
        batch['components'][0]['item'] = 'item/신맛-캔디'
        self.assertFalse(engine.validate_state()['valid'])

    def test_composite_trade_in_applies_every_ingredient_effect_through_its_actual_consumer(self):
        world = FIX.scene(self.rules)
        engine, chef, partner, foe = world['engine'], world['chef'], world['partner'], world['foe']
        FIX.ruling(engine, 'encounter_end')
        tasty = FIX.cook(engine, chef, recipe='tasty_snack', snack='매운맛 랩')
        attack = FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'batch_id': tasty['batch_id']}, ingredient_2={'item': 'item/먹다남은음식'}, taste='매운맛')
        kari = FIX.cook(engine, chef, recipe='preserves', origin='item/카리열매')
        hit = FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'batch_id': kari['batch_id']}, ingredient_2={'item': 'item/먹다남은음식'})
        pres = FIX.cook(engine, chef, recipe='preserves', origin='item/오랭열매')
        left = FIX.cook(engine, chef, recipe='leftovers')
        immediate = FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'batch_id': pres['batch_id']}, ingredient_2={'batch_id': left['batch_id']})
        served = FIX.serve(engine, chef, attack['batch_id'], partner)
        buff = FOOD.get_buff(partner, served['buff_id'])
        self.assertEqual((buff['effect']['kind'], buff['effect_source'], buff['taste_assignment']['taste']), ('chef_composite', CHEF.DUMPLINGS, '매운맛'))
        self.rejected(engine, lambda: engine.consume_food_buff(partner, buff_id=served['buff_id'], action_kind='free', action_reason='wrong path'), 'exact attack or self-activation consumer')
        prep = engine.consume_food_buff(partner, buff_id=served['buff_id'])
        self.assertEqual(prep['status'], 'prepared_for_actual_attack')
        FIX.battle(engine, partner)
        move = self.rules.move('move/몸통박치기')
        engine.roll_damage(partner, foe, move, set_damage=True)
        benefit = FIX.receipt(partner)['benefit']
        self.assertEqual((benefit['kind'], benefit['amount'], benefit['composite'][0]['kind'], benefit['composite'][0]['until']), ('bonus_damage', 5, 'turn_heal', 'encounter_end'))
        self.assertEqual(benefit['taste_bonus']['kind'], 'critical_range')
        self.assertEqual(len(partner.spec['food_turn_healing']), 1)
        self.assertEqual(partner.spec['food_turn_healing'][0]['buff_id'], served['buff_id'])
        self.assertFalse(partner.buffs)
        self.assertTrue(engine.validate_state()['valid'], engine.validate_state()['issues'])
        FIX.decline_all(engine, chef)
        partner.hp = max(1, partner.hp - 20)
        before_hp = partner.hp
        engine.end_of_turn(partner)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(partner, initiative_count=20)
        self.assertEqual(partner.hp, min(partner.max_hp, before_hp + M.ratio(partner.base_max_hp, 16)))
        engine.end_encounter()
        self.assertNotIn('food_turn_healing', partner.spec)
        # Hit-triggered type Berry Preserves plus Leftovers.
        served = FIX.serve(engine, chef, hit['batch_id'], partner)
        self.assertEqual(engine.consume_food_buff(partner, buff_id=served['buff_id'])['status'], 'prepared_for_actual_hit')
        FIX.battle(engine, foe)
        engine.roll_damage(foe, partner, move, set_damage=True)
        benefit = FIX.receipt(partner)['benefit']
        self.assertEqual((benefit['resistance_steps'], benefit['composite'][0]['kind']), (1, 'turn_heal'))
        self.assertEqual(len(partner.spec['food_turn_healing']), 1)
        FIX.decline_all(engine, chef)
        engine.end_encounter()
        # Immediate-only composite: both effects apply in one explicit trade-in during an encounter.
        served = FIX.serve(engine, chef, immediate['batch_id'], partner)
        partner.hp = 1
        before = engine.export_state()
        self.assertIsInstance(engine.consume_food_buff(partner, buff_id=served['buff_id'], action_kind='free', action_reason='out of combat'), C.PendingDecision)
        self.assertEqual(engine.export_state(), before)
        FIX.battle(engine, partner)
        result = engine.consume_food_buff(partner, buff_id=served['buff_id'], action_kind='free', action_reason='composite trade-in')
        self.assertEqual([row['kind'] for row in result['components']], ['heal', 'turn_heal'])
        self.assertEqual((partner.hp, len(partner.spec['food_turn_healing'])), (6, 1))
        self.assertTrue(engine.validate_state()['valid'], engine.validate_state()['issues'])
        loaded, actors = FIX.restore(self.rules, engine)
        self.assertEqual(len(actors[partner.entity_id].spec['food_turn_healing']), 1)
        self.assertTrue(loaded.validate_state()['valid'])
        FIX.decline_all(engine, chef)

    def test_late_cooking_failure_rolls_back_money_ingredients_time_jobs_and_batches(self):
        world = FIX.scene(self.rules)
        engine, chef = world['engine'], world['chef']
        tasty = FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')
        native = R.record

        def fail(*args, **kwargs):
            native(*args, **kwargs)
            raise ValueError('actual late transformation ledger failure')
        for options in ({'recipe': 'tasty_snack', 'snack': '신맛 캔디'}, {'recipe': 'preserves', 'origin': 'item/오랭열매'},
                        {'recipe': 'hearty_meal', 'ingredients': 'big_mushroom', 'units': 2},
                        {'recipe': 'dumplings', 'ingredient_1': {'batch_id': tasty['batch_id']}, 'ingredient_2': {'item': 'item/먹다남은음식'}}):
            with self.subTest(recipe=options['recipe']), patch.object(R, 'record', side_effect=fail):
                self.rejected(engine, lambda: FIX.cook(engine, chef, **options), 'late transformation ledger failure')
        self.assertEqual((len(chef.spec['chef_batches']), self.batch(chef, tasty['batch_id'])['count'], engine.elapsed_seconds), (1, 1, 300))
        self.assertEqual(FIX.cook(engine, chef, recipe='dumplings', ingredient_1={'batch_id': tasty['batch_id']}, ingredient_2={'item': 'item/먹다남은음식'})['count'], 1)
        self.assertTrue(engine.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
