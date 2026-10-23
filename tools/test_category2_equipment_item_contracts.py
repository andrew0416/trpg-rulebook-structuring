"""Direct Chapter 9 item-contract producers and consumers for C2-CORE-G029."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
CANON = STAGE if (STAGE / 'input').exists() else Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path[:0] = [str(STAGE / 'engine'), str(CANON / 'engine'), str(CANON / 'tools')]

import equipment_item_contracts as CONTRACTS
import food_effects as FOOD
import crafting_resources as RESOURCES
import test_category3_food_effects as food_fixture
import test_category2_crafting_resource_state as scrap_fixture
import test_foundation_crafting_product as product_fixture


class FoodItemContractTests(unittest.TestCase):
    setUpClass = classmethod(food_fixture.FoodTests.setUpClass.__func__)
    setUp = food_fixture.FoodTests.setUp
    actor = food_fixture.FoodTests.actor
    state = food_fixture.FoodTests.state
    snack = food_fixture.FoodTests.snack
    built_pokemon = food_fixture.FoodTests.built_pokemon
    baby = food_fixture.FoodTests.baby

    def contract(self, item_id, *, forced_snack=False):
        return CONTRACTS.food_intake(
            self.e.r, item_id, snack_items=FOOD.SNACKS,
            drink_items=FOOD.DRINKS, other_food_items={'item/이유식'},
            forced_snack=forced_snack)

    def test_snack_and_berry_use_one_extended_digestion_slot_then_actual_effect(self):
        self.assertEqual(self.contract('item/초코바'), {
            'kind': 'snack', 'clause_id': 'C09-028', 'action': 'extended',
            'limit_bucket': 'digestion_buff', 'berries_are_snacks': False})
        chocolate = self.snack('초코바')
        self.assertEqual((self.e.elapsed_seconds, self.p._action_history), (60, ['extended']))
        self.assertEqual(len(self.p.buffs), 1)
        self.a.spec['items']['오랭열매'] = 1
        before = self.state()
        with self.assertRaises(ValueError):
            self.e.use_item(self.a, '오랭열매', self.p, duration_minutes=1,
                            duration_reason='occupied digestion slot')
        self.assertEqual(before, self.state())
        self.e.consume_food_buff(self.p, buff_id=chocolate['buff_id'],
                                 action_kind='free', action_reason='free the actual slot')
        berry = self.e.use_item(self.a, '오랭열매', self.p, duration_minutes=1,
                                duration_reason='actual berry snack')
        self.assertTrue(self.contract('item/오랭열매')['berries_are_snacks'])
        stored = FOOD.get_buff(self.p, berry['buff_id'])
        self.assertEqual(stored['effect'], {'kind': 'heal', 'amount': 5, 'berry': True})

    def test_gluttony_is_the_selected_capacity_exception_to_the_one_slot_rule(self):
        self.rules = self.playtest
        self.setUp()
        self.p.abilities = ['먹보 [Playtest]']
        for item in ('초코바', '꿀', '초코바'):
            self.snack(item)
        self.assertEqual(len(self.p.buffs), 3)
        self.a.spec['items']['꿀'] = self.a.spec['items'].get('꿀', 0) + 1
        before = self.state()
        with self.assertRaises(ValueError):
            self.e.use_item(self.a, '꿀', self.p, duration_minutes=1,
                            duration_reason='fourth digestion slot')
        self.assertEqual(before, self.state())
        self.assertTrue(all(row[FOOD.INSTANCES.KEY]['capacity']['bucket'] == 'ordinary'
                            for row in self.p.buffs))

    def test_other_food_keeps_extended_action_but_neither_food_limit_bucket(self):
        result = self.baby('book_xp20_level15', 15)
        record = self.p.spec['baby_food']
        self.assertEqual(result['status'], 'consumed')
        self.assertEqual(record['intake_contract'], {
            'kind': 'other_food', 'clause_id': 'C09-031', 'action': 'extended',
            'limit_bucket': 'independent', 'berries_are_snacks': False})
        self.assertEqual((self.e.elapsed_seconds, self.p._action_history), (60, ['extended']))
        self.assertFalse(self.p.buffs)
        self.assertNotIn('drink_history', self.p.spec)


class ScrapKindContractTests(unittest.TestCase):
    setUpClass = classmethod(scrap_fixture.CraftingResourceStateTests.setUpClass.__func__)
    setUp = scrap_fixture.CraftingResourceStateTests.setUp
    actor = scrap_fixture.CraftingResourceStateTests.actor
    act = scrap_fixture.CraftingResourceStateTests.act
    own = scrap_fixture.CraftingResourceStateTests.own
    snap = scrap_fixture.CraftingResourceStateTests.snap

    def test_five_examples_are_exact_kinds_and_the_source_list_remains_open(self):
        rows = [
            ('초코바', '음식'), ('상처약', '약'), ('실버스프레이', '스프레이'),
            ('item/몬스터볼-2', '몬스터볼'), ('콘테스트 옷', '패션 도구')]
        for item, expected in rows:
            self.a.spec['items'][item] = 1
            result = self.act('dismantle', item=item)
            self.assertEqual(result['category'], expected)
        self.assertEqual(RESOURCES.EXAMPLE_KINDS, CONTRACTS.SCRAP_EXAMPLE_KINDS)
        self.a.spec['items']['화학 세트'] = 1
        before = self.snap()
        with self.assertRaises(ValueError):
            self.act('dismantle', item='item/화학-세트-1')
        self.assertEqual(before, self.snap())
        result = self.act('dismantle', item='item/화학-세트-1',
                          scrap_kind='실험용 재료',
                          scrap_reason='GM observed a related intact laboratory material')
        self.assertEqual(result['category'], '실험용 재료')
        self.assertIn('실험용 재료', self.a.spec['crafting_scrap'])


class FashionProductScrapContractTests(unittest.TestCase):
    setUpClass = classmethod(product_fixture.ProductTests.setUpClass.__func__)
    setUp = product_fixture.ProductTests.setUp
    actor = product_fixture.ProductTests.actor
    own = product_fixture.ProductTests.own
    recipe = product_fixture.ProductTests.recipe
    ready = product_fixture.ProductTests.ready
    policy = product_fixture.ProductTests.policy
    craft = product_fixture.ProductTests.craft
    made = product_fixture.ProductTests.made
    equip = product_fixture.ProductTests.equip
    snapshot = product_fixture.ProductTests.snapshot

    def test_actual_fashion_product_body_is_the_scrap_producer_and_is_consumed_once(self):
        recipe, policy, made = self.made()
        self.equip()
        origin = deepcopy(self.e._physical_objects['crafted:goggles']['crafting_origin'])
        result = self.e.pokemon_activity(
            self.a, 'dismantle', item='item/방진고글', held_selection='crafted:goggles')
        body = self.e._physical_objects['crafted:goggles']
        self.assertEqual(result['category'], '패션 도구')
        self.assertEqual(body['crafting_origin'], origin)
        self.assertEqual(body['consumed']['by_actor_id'], self.a.entity_id)
        self.assertEqual(made['product_instance_ids'], ['crafted:goggles'])
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.e.pokemon_activity(
                self.a, 'dismantle', item='item/방진고글', held_selection='crafted:goggles')
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
