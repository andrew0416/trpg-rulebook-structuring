"""Selected Core/Homebrew Fashion outputs, actual Chic admission and source-bound Dumplings."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
P = Path(r'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository')
ROOT = STAGE if (STAGE / 'data/core-rules.json').is_file() else P
sys.path[:0] = [str(STAGE / 'engine'), str(STAGE / 'tools'), str(P / 'engine'), str(P / 'tools')]
from engine import Rules
from native_scenario_fixture import assert_rejected_unchanged
from ruleset import RuleFilter
import action_points as AP
import book_chef_fixture as CHEF_FIX
import chef_cooking as CHEF
import condition_recovery as RECOVERY
import effect_lifetimes as LIFETIMES
import fashion_items as FASHION
import fashionista as FA
import food_effects as FOOD
import held_equipment as HELD
import items as ITEMS
import test_book_fashionista_acquisition as FASHION_FIX
import turn as TURN

PRINTED = {
    'charm': ('매력', 'item/귀여운-패션'),
    'intuition': ('직감', 'item/우아한-패션'),
    'command': ('명령', 'item/기막힌-패션'),
    'intimidate': ('협박', 'item/거친-패션'),
    'guile': ('교활', 'item/번지르르한-패션'),
}
HOMEBREW = dict(zip(PRINTED, ('item/귀여운-패션-1', 'item/아름다운-패션-1',
                            'item/근사한-패션-1', 'item/강인한-패션-1', 'item/슬기로운-패션-1')))
CHEF_FEATURES = (CHEF.CLASS, CHEF.HITS, CHEF.ACCENTUATED, CHEF.AFTERTASTE, CHEF.DUMPLINGS)


class FashionSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    setUp = FASHION_FIX.FashionistaAcquisitionTests.setUp
    setup = FASHION_FIX.FashionistaAcquisitionTests.setup
    add = FASHION_FIX.FashionistaAcquisitionTests.add
    acquire = FASHION_FIX.FashionistaAcquisitionTests.acquire
    craft = FASHION_FIX.FashionistaAcquisitionTests.craft
    item = FASHION_FIX.FashionistaAcquisitionTests.item
    hold = FASHION_FIX.FashionistaAcquisitionTests.hold
    combat = FASHION_FIX.FashionistaAcquisitionTests.combat
    restore = FASHION_FIX.FashionistaAcquisitionTests.restore
    valid = FASHION_FIX.FashionistaAcquisitionTests.valid

    def test_core_printed_recipes_craft_only_chosen_skills_with_actual_payment(self):
        for key, (skill, item_id) in PRINTED.items():
            with self.subTest(skill=skill):
                other = '매력' if skill != '매력' else '직감'
                self.setup(choices=(skill, other))
                self.acquire()
                recipe = 'fashionista/basic-fashion-' + key
                self.assertEqual(FA.recipe_row(recipe)['output'], {'item_id': item_id, 'key': item_id})
                self.assertEqual(self.rules._selected_rule(item_id), item_id)
                self.assertIn(recipe, FA.craftable(self.e, self.t))
                self.assertFalse(any(r.endswith('-homebrew') for r in FA.craftable(self.e, self.t)))
                for unchosen, (other_skill, _) in PRINTED.items():
                    if other_skill not in (skill, other):
                        self.assertNotIn('fashionista/basic-fashion-' + unchosen, FA.craftable(self.e, self.t))
                money, seconds = self.t.spec['money'], self.e.elapsed_seconds
                result = self.craft(recipe, uid='printed:' + key)
                obj = self.e._physical_objects['printed:' + key]
                self.assertEqual((result['item_id'], money - self.t.spec['money'], self.e.elapsed_seconds - seconds),
                                 (item_id, 500, 600))
                self.assertEqual(obj['crafting_origin']['maker_id'], self.t.entity_id)
                self.assertEqual(obj['item_rule_id'], item_id)
                self.valid()

    def test_core_makeover_accepts_creatable_printed_fashion_without_a_slot(self):
        self.acquire()
        self.acquire(FA.MAKEOVER)
        before, available = deepcopy(HELD.entries(self.p)), AP.available(self.t)
        FA.makeover(self.e, self.t, self.p, PRINTED['intuition'][1],
                    recipe_id='fashionista/basic-fashion-intuition', seconds=600, reason='completed printed Fashion makeover')
        self.assertEqual(FA.makeover_record(self.p)['item_id'], PRINTED['intuition'][1])
        self.assertEqual(HELD.entries(self.p), before)
        self.assertEqual(AP.available(self.t), available - 2)
        self.restore()
        self.assertNotIn('all', self.p.stage_loss_immune)
        self.combat(self.p)
        effect = {'type': 'stage_change', 'stat': 'atk', 'delta': -1, 'on': 'target'}
        self.e.arm_fashion_reaction(self.p, PRINTED['intuition'][1])
        self.e.apply_effect(self.q, self.p, effect, 2, True, 0, 'move/울음소리')
        self.assertEqual(self.p.stages['atk'], 0)
        self.e.apply_effect(self.q, self.p, effect, 2, True, 0, 'move/울음소리')
        self.assertEqual(self.p.stages['atk'], -1)
        self.valid()

    def core_held(self, key):
        skill = PRINTED[key][0]
        other = '매력' if skill != '매력' else '직감'
        self.setup(choices=(skill, other))
        self.acquire()
        wearer = self.q  # Core holders need not belong to the maker.
        item_id, identity = PRINTED[key][1], 'core:' + key
        self.craft('fashionista/basic-fashion-' + key, uid=identity, owner=wearer)
        ITEMS.equip_held(self.e, wearer, item_id, source_instance_id=identity)
        self.assertEqual(self.e._physical_objects[identity]['crafting_origin']['maker_id'], self.t.entity_id)
        return item_id, identity

    def test_core_cute_nonmaker_holder_uses_one_free_action_once_and_round_effect_survives_restore(self):
        item_id, identity = self.core_held('charm')
        self.assertNotEqual(self.q.spec.get('trainer_id'), self.t.entity_id)
        self.assertEqual(self.q.evasion_mod, 0)
        self.combat(self.q)
        before = len(self.q._action_history)
        self.e.activate_fashion_item(self.q, item_id, instance_id=identity)
        self.assertEqual((LIFETIMES.numeric(self.q, 'evasion_modifier'), len(self.q._action_history) - before), (2, 1))
        self.assertFalse(any(e.get('type') == 'reroll' for e in self.rules.item_effects(item_id)[0]))
        with self.assertRaisesRegex(ValueError, 'matching equipped Fashion contest stat'):
            FASHION.contest_plan(self.e, self.q, '귀여움', set())
        ITEMS.unregister_item(self.e, self.q, item_id)
        self.restore()
        self.assertEqual(LIFETIMES.numeric(self.q, 'evasion_modifier'), 2)
        ITEMS.equip_held(self.e, self.q, item_id, source_instance_id=identity)
        assert_rejected_unchanged(self.e, lambda: self.e.activate_fashion_item(self.q, item_id), reason_pattern='already activated')
        self.e.end_of_turn(self.q)
        self.e.end_round()
        self.combat(self.q)
        self.assertEqual(LIFETIMES.numeric(self.q, 'evasion_modifier'), 0)
        self.valid()

    def test_core_elegant_and_slick_use_only_accepted_actual_enemy_reactions(self):
        for key in ('intuition', 'guile'):
            with self.subTest(key=key):
                self.setup()
                item_id, identity = self.core_held(key)
                self.assertNotIn('all', self.q.stage_loss_immune)
                self.combat(self.q)
                actions = len(self.q._action_history)
                if key == 'intuition':
                    effect = {'type': 'stage_change', 'stat': 'atk', 'delta': -1, 'on': 'target'}
                    trigger = lambda: self.e.apply_effect(self.p, self.q, effect, 2, True, 0, 'move/울음소리')
                    trigger()
                    self.assertEqual(self.q.stages['atk'], -1)
                    self.e.arm_fashion_reaction(self.q, item_id, instance_id=identity)
                    self.e.apply_effect(self.q, self.q, effect, 2, True, 0, 'move/울음소리')
                    self.assertEqual(self.q.stages['atk'], -2)
                    trigger()
                    self.assertEqual(self.q.stages['atk'], -2)
                    trigger()
                    self.assertEqual(self.q.stages['atk'], -3)
                else:
                    self.e.arm_fashion_reaction(self.q, item_id, instance_id=identity)
                    TURN.trigger_aoo(self.e, self.q, 'actual movement provoking opportunity', [self.p])
                    self.assertFalse(self.p.aoo_used)
                    TURN.trigger_aoo(self.e, self.q, 'second actual opportunity', [self.p])
                    self.assertTrue(self.p.aoo_used)
                self.assertEqual(len(self.q._action_history), actions + 1)
                self.restore()
                self.valid()

    def test_core_rad_trainer_accessory_consumes_one_actual_save_after_restore(self):
        self.setup(choices=('명령', '직감'))
        self.acquire()
        self.u = self.add('actual nonmaker wearer', 'trainer', (4, 2), classes=[], feats=[])
        item_id, identity = PRINTED['command'][1], 'core:trainer-rad'
        self.craft('fashionista/basic-fashion-command', uid=identity, owner=self.u)
        ITEMS.register_item(self.e, self.u, item_id, source_instance_id=identity)
        self.assertEqual(next(iter(self.u._item_reg.values()))['slots'], ['장신구'])
        self.combat(self.u)
        self.e.activate_fashion_item(self.u, item_id)
        self.restore()
        first = RECOVERY.saving_check(self.e, self.u, None, 8, fixed=5)
        second = RECOVERY.saving_check(self.e, self.u, None, 8, fixed=5)
        self.assertEqual((first['fashion_bonus'], first['passed'], second['fashion_bonus'], second['passed']), (4, True, 0, False))
        assert_rejected_unchanged(self.e, lambda: self.e.activate_fashion_item(self.u, item_id), reason_pattern='already activated')
        self.valid()

    def test_core_rough_requires_observed_enemy_and_penalizes_actual_roll_for_one_round(self):
        item_id, _ = self.core_held('intimidate')
        self.combat(self.q)
        assert_rejected_unchanged(self.e, lambda: self.e.activate_fashion_item(self.q, item_id, target=self.q), reason_pattern='enemy')
        count = self.e._prepare_skill_roll(self.p, '전투')[5]['dice_count']
        before = self.e.skill_roll(self.p, '전투', fixed=[3] * count).total
        self.e.activate_fashion_item(self.q, item_id, target=self.p)
        self.assertEqual(self.e.skill_roll(self.p, '전투', fixed=[3] * count).total, before - 2)
        self.e.end_of_turn(self.q)
        self.e.end_round()
        self.combat(self.q)
        self.assertEqual(FASHION.all_roll_modifier(self.p), 0)
        self.valid()

    def test_core_dress_projection_and_later_active_item_share_the_actual_physical_quota(self):
        self.acquire()
        self.acquire(FA.WARDROBE)
        self.acquire(FA.DRESS)
        FA.make_chic(self.e, self.t, self.p, seconds=600, reason='completed actual fitting')
        item_id, identity = PRINTED['charm'][1], 'core:stored-cute'
        self.craft('fashionista/basic-fashion-charm', uid=identity, owner=self.p)
        FA.store(self.e, self.p, identity, 'wardrobe:1', reason='actual printed Fashion storage')
        self.combat(self.t)
        FA.dress_to_impress(self.e, self.t, self.p)
        receipt = self.e.activate_fashion_item(self.p, item_id)
        self.assertEqual(receipt['instance_id'], identity)
        self.restore()
        self.e.end_of_turn(self.t)
        self.e.end_round()
        self.combat(self.p)
        self.assertFalse(FA.dress_record(self.p))
        FA.swap(self.e, self.p, 'wardrobe:1')
        assert_rejected_unchanged(self.e, lambda: self.e.activate_fashion_item(self.p, item_id), reason_pattern='already activated')
        self.valid()

    def test_homebrew_outputs_remain_explicit_paid_products_with_native_activation(self):
        self.rules = Rules(ROOT, ruleset='homebrew')
        for key, (skill, _) in PRINTED.items():
            with self.subTest(skill=skill):
                other = '매력' if skill != '매력' else '직감'
                self.setup(choices=(skill, other))
                self.acquire()
                recipe, item_id = 'fashionista/basic-fashion-' + key + '-homebrew', HOMEBREW[key]
                self.assertEqual(self.rules._selected_rule(item_id), item_id)
                money = self.t.spec['money']
                result = self.craft(recipe, uid='homebrew:' + key, owner=self.p)
                self.assertEqual((result['item_id'], money - self.t.spec['money']), (item_id, 500))
                if key == 'charm':
                    ITEMS.equip_held(self.e, self.p, item_id, source_instance_id='homebrew:' + key)
                    self.combat(self.p)
                    assert_rejected_unchanged(self.e,
                        lambda: self.e.activate_fashion_item(self.p, PRINTED[key][1]), reason_pattern='unavailable')
                    self.e.activate_fashion_item(self.p, item_id)
                    self.assertEqual(LIFETIMES.numeric(self.p, 'evasion_modifier'), 2)
                self.valid()

    def stocked(self, item_id='item/선제공격손톱'):
        self.acquire()
        self.acquire(FA.WARDROBE)
        FA.make_chic(self.e, self.t, self.p, seconds=600, reason='completed Chic fitting')
        self.item('stored:1', item_id, self.p)
        FA.store(self.e, self.p, 'stored:1', 'wardrobe:1', reason='actual stored held item')

    def test_chic_direct_registration_and_equip_reject_type_and_effect_duplicates_atomically(self):
        self.stocked()
        self.item('duplicate:1', 'item/선제공격손톱', self.p)
        for operation in (
                lambda: ITEMS.register_item(self.e, self.p, 'item/선제공격손톱', source_instance_id='duplicate:1'),
                lambda: ITEMS.equip_held(self.e, self.p, 'item/선제공격손톱', source_instance_id='duplicate:1')):
            assert_rejected_unchanged(self.e, operation, reason_pattern='same type')
        self.setup()
        self.stocked('item/무사태평향로')
        self.item('duplicate:effect', 'item/회피부스터', self.p)
        self.assertTrue(FA.shares_effects(self.e, 'item/무사태평향로', 'item/회피부스터'))
        assert_rejected_unchanged(self.e,
            lambda: ITEMS.equip_held(self.e, self.p, 'item/회피부스터', source_instance_id='duplicate:effect'),
            reason_pattern='repeated effects')
        self.valid()

    def test_chic_transfer_and_exchange_preserve_both_actors_on_illegal_recipient(self):
        self.stocked()
        self.hold(self.q, 'donor:claw', 'item/선제공격손톱')
        assert_rejected_unchanged(self.e,
            lambda: ITEMS.transfer_equipment(self.e, self.q, self.p, 'donor:claw'), reason_pattern='same type')
        self.hold(self.p, 'recipient:band', 'item/기합의머리띠')
        assert_rejected_unchanged(self.e,
            lambda: ITEMS.exchange_items(self.e, self.q, self.p,
                first_selection='donor:claw', second_selection='recipient:band'), reason_pattern='same type')
        self.assertEqual(HELD.entries(self.q)[0]['instance_id'], 'donor:claw')
        self.assertEqual(HELD.entries(self.p)[0]['instance_id'], 'recipient:band')
        self.valid()

    def test_chic_distinct_equipment_swap_restore_and_idempotent_register_stay_legal(self):
        self.stocked()
        self.hold(self.p, 'active:band', 'item/기합의머리띠')
        self.combat(self.p)
        FA.swap(self.e, self.p, 'wardrobe:1')
        self.assertEqual(HELD.entries(self.p)[0]['instance_id'], 'stored:1')
        self.assertEqual(FA.chic(self.p)['slots']['wardrobe:1']['instance_id'], 'active:band')
        self.assertEqual(ITEMS.register_item(self.e, self.p, 'item/선제공격손톱', source_instance_id='stored:1'), 0)
        self.restore()
        self.valid()


class DumplingsSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)

    def inner(self, rules):
        world = CHEF_FIX.scene(rules, feats=CHEF_FEATURES)
        e, cook = world['engine'], world['chef']
        snack = CHEF_FIX.cook(e, cook, recipe='tasty_snack', snack='매운맛 랩')
        pres = CHEF_FIX.cook(e, cook, recipe='preserves', origin='item/오랭열매')
        inner = CHEF_FIX.cook(e, cook, recipe='dumplings',
            ingredient_1={'batch_id': snack['batch_id']}, ingredient_2={'batch_id': pres['batch_id']})
        return world, snack, pres, inner

    def test_core_nested_dumplings_preserve_real_debits_one_buff_and_each_consumer_once(self):
        world, snack, pres, inner = self.inner(self.rules)
        e, cook, partner, foe = (world[name] for name in ('engine', 'chef', 'partner', 'foe'))
        money, stock = cook.spec['money'], cook.spec['items']['먹다남은음식']
        outer = CHEF_FIX.cook(e, cook, recipe='dumplings',
            ingredient_1={'batch_id': inner['batch_id']}, ingredient_2={'item': CHEF.LEFTOVERS_ITEM})
        self.assertEqual((cook.spec['money'], cook.spec['items']['먹다남은음식']), (money, stock - 1))
        self.assertEqual((CHEF.batches(cook)[snack['batch_id']]['count'], CHEF.batches(cook)[pres['batch_id']]['count'],
                          CHEF.batches(cook)[inner['batch_id']]['count'], outer['batch']['count']), (0, 1, 0, 1))
        self.assertEqual(outer['batch']['ingredients'][0], {'kind': 'batch', 'batch_id': inner['batch_id']})
        self.assertEqual(outer['batch']['components'][0]['ingredient']['batch_id'], inner['batch_id'])
        self.assertEqual(outer['batch']['components'][0]['effect'], inner['batch']['payload'])
        self.assertEqual([p['effect']['kind'] for p in outer['batch']['payload']['components']], ['chef_snack', 'heal', 'turn_heal'])
        CHEF_FIX.ruling(e, 'encounter_end')
        served = CHEF_FIX.serve(e, cook, outer['batch_id'], partner)
        self.assertEqual(len(partner.buffs), 1)
        self.assertEqual(CHEF.batches(cook)[outer['batch_id']]['count'], 0)
        e, actors = CHEF_FIX.restore(self.rules, e)
        cook, partner, foe = (actors[a.entity_id] for a in (cook, partner, foe))
        before = max(1, partner.hp - 20)
        partner.hp = before
        self.assertEqual(e.consume_food_buff(partner, buff_id=served['buff_id'])['status'], 'prepared_for_actual_attack')
        CHEF_FIX.battle(e, partner)
        e.roll_damage(partner, foe, self.rules.move('move/몸통박치기'), set_damage=True)
        benefit = CHEF_FIX.receipt(partner)['benefit']
        self.assertEqual([part['kind'] for part in benefit['composite']], ['heal', 'turn_heal'])
        self.assertEqual(partner.hp, before + 5)
        self.assertEqual(len(partner.spec['food_turn_healing']), 1)
        self.assertEqual(partner.spec['food_turn_healing'][0]['buff_id'], served['buff_id'])
        self.assertFalse(partner.buffs)
        assert_rejected_unchanged(e, lambda: e.consume_food_buff(partner, buff_id=served['buff_id']), reason_pattern='Buff|buff')
        CHEF_FIX.decline_all(e, cook)
        e.end_encounter()
        self.assertFalse(partner.spec.get('food_turn_healing'))
        self.assertTrue(e.validate_state()['valid'], e.validate_state()['issues'])

    def test_selected_errata_profiles_reject_nesting_before_time_payment_or_portion_loss(self):
        for profile in ('core+errata', 'homebrew', 'all'):
            with self.subTest(profile=profile):
                rules = Rules(ROOT, ruleset=profile)
                world, _, _, inner = self.inner(rules)
                e, cook = world['engine'], world['chef']
                self.assertFalse(CHEF._nested_dumplings_allowed(rules))
                assert_rejected_unchanged(e, lambda: CHEF_FIX.cook(e, cook, recipe='dumplings',
                    ingredient_1={'batch_id': inner['batch_id']}, ingredient_2={'item': CHEF.LEFTOVERS_ITEM}),
                    reason_pattern='another Dumplings.*selected errata')

    def test_explicit_errata_source_exclusion_preserves_core_nested_behavior(self):
        profile = deepcopy(self.rules.ruleset.profile)
        profile['sources'] = ['core', 'errata']
        profile['exclude_units'] = ['chef/dumplings-no-nesting-errata']
        selected = RuleFilter(profile, 'explicit-core-without-dumplings-errata')
        with patch.object(RuleFilter, 'load', return_value=selected):
            rules = Rules(ROOT)
        world, _, _, inner = self.inner(rules)
        e, cook = world['engine'], world['chef']
        self.assertTrue(CHEF._nested_dumplings_allowed(rules))
        result = CHEF_FIX.cook(e, cook, recipe='dumplings',
            ingredient_1={'batch_id': inner['batch_id']}, ingredient_2={'item': CHEF.LEFTOVERS_ITEM})
        self.assertEqual(len(result['batch']['payload']['components']), 3)
        self.assertTrue(e.validate_state()['valid'], e.validate_state()['issues'])

    def test_core_nested_ingredient_limits_exhaustion_and_provenance_remain_enforced(self):
        world, _, _, inner = self.inner(self.rules)
        e, cook = world['engine'], world['chef']
        oka = CHEF_FIX.cook(e, cook, recipe='preserves', origin='item/오카열매')
        assert_rejected_unchanged(e, lambda: CHEF_FIX.cook(e, cook, recipe='dumplings',
            ingredient_1={'batch_id': inner['batch_id']}, ingredient_2={'batch_id': oka['batch_id']}),
            reason_pattern='two different trigger-bound')
        assert_rejected_unchanged(e, lambda: CHEF_FIX.cook(e, cook, recipe='dumplings',
            ingredient_1={'item': CHEF.LEFTOVERS_ITEM}, ingredient_2={'batch_id': inner['batch_id']}),
            reason_pattern='leftovers, preserves required')
        outer = CHEF_FIX.cook(e, cook, recipe='dumplings',
            ingredient_1={'batch_id': inner['batch_id']}, ingredient_2={'item': CHEF.LEFTOVERS_ITEM})
        assert_rejected_unchanged(e, lambda: CHEF_FIX.cook(e, cook, recipe='dumplings',
            ingredient_1={'batch_id': inner['batch_id']}, ingredient_2={'item': CHEF.LEFTOVERS_ITEM}), reason_pattern='exhausted')
        self.assertTrue(e.validate_state()['valid'], e.validate_state()['issues'])
        CHEF.batches(cook)[outer['batch_id']]['components'][0]['ingredient']['batch_id'] = 'missing:producer'
        self.assertFalse(e.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
