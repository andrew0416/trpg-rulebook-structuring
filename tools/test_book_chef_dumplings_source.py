"""R307's actual Book versus CSV contract, using the existing composite consumer."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_book_chef_csv as _fixture_chef_csv
import book_chef_fixture as FIX
import chef_cooking as CHEF
import common_checks as C
import food_effects as FOOD
import vitamin_moves as V
import herb_mushroom_rules as HERB
import items as ITEMS
import world_entities as WORLD
from engine import Engine, Combatant


class DumplingsSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ruleset import RuleFilter
        from engine import Rules
        profile = deepcopy(RuleFilter.load(ROOT, 'all').profile)
        profile['exclude_units'] = list(profile.get('exclude_units', [])) + ['chef/dumplings-no-nesting-errata']
        selected = RuleFilter(profile, 'all-with-original-book-dumplings')
        with patch.object(RuleFilter, 'load', return_value=selected):
            cls.rules = Rules(ROOT, ruleset='all')
    setUp = _fixture_chef_csv.ChefCsvTests.setUp
    scene = _fixture_chef_csv.ChefCsvTests.scene
    reject = _fixture_chef_csv.ChefCsvTests.reject

    def prepared(self, *, csv):
        w = self.scene(csv=csv)
        e, chef = w['engine'], w['chef']
        first = FIX.cook(e, chef, recipe='preserves', origin='item/오랭열매')
        left = FIX.cook(e, chef, recipe='leftovers')
        second = FIX.cook(e, chef, recipe='preserves', origin='item/버치열매')
        parent = FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': first['batch_id']}, ingredient_2={'batch_id': left['batch_id']})
        return w, parent, second

    def nested(self, e, chef, parent, second):
        return FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': parent['batch_id']}, ingredient_2={'batch_id': second['batch_id']})

    def add_chef(self, engine, *, items):
        """Use the same real acquisition/cooking fixture in another native scene."""
        chef=Combatant(self.rules,FIX.trainer_spec(self.rules,'visiting actual Chef',items={'요리 세트':1,**items}))
        engine.gm.add_combatant(chef,pos=(8,5),side='party',reason='actual registered Chef serving the existing native scenario')
        for uid in FIX.ALL_FEATURES:FIX.acquire(engine,chef,uid)
        ITEMS.register_feats(engine,chef)
        return chef

    def test_book_nested_first_preserves_actual_parent_unit_all_effects_and_both_restores(self):
        w, parent, second = self.prepared(csv=False)
        e, chef, p = w['engine'], w['chef'], w['partner']
        child = self.nested(e, chef, parent, second)
        batch = CHEF.batches(chef)[child['batch_id']]
        self.assertEqual(batch['dumplings_basis']['edition'], 'book')
        self.assertEqual(len(batch['components']), 2)
        self.assertEqual([part['effect']['kind'] for part in batch['payload']['components']], ['heal', 'turn_heal', 'cure'])
        stock = batch['components'][0]['ingredient']['stock']
        self.assertEqual((stock['batch_id'], stock['unit'], CHEF.batches(chef)[parent['batch_id']]['count']), (parent['batch_id'], 1, 0))
        self.assertEqual((chef.spec['money'], e.elapsed_seconds), (1800, 25 * 60))
        p.hp = p.base_max_hp // 2
        e.apply_status(p, '마비', source='move/전기자석파', applied_by=w['foe'])
        snapshot = e.gm.snapshot('actual nested Book before intake')
        loaded, actors = FIX.restore(self.rules, e)
        for current, cook, target in ((loaded, actors[chef.entity_id], actors[p.entity_id]), (e, chef, p)):
            served = FIX.serve(current, cook, child['batch_id'], target)
            with patch.object(Engine, 'd20', return_value=20):
                FIX.battle(current, target)  # Actual successful native Paralysis save.
            before_hp = target.hp
            result = current.consume_food_buff(target, buff_id=served['buff_id'], action_kind='free', action_reason='GM-observed actual composite trade-in')
            self.assertEqual([part['kind'] for part in result['components']], ['heal', 'turn_heal', 'cure'])
            self.assertGreater(target.hp, before_hp)
            self.assertNotIn('마비', target.conditions)
            self.assertEqual(len(target.spec['food_turn_healing']), 1)
            FIX.decline_all(current, cook)
            self.assertTrue(current.validate_state()['valid'])
        e.gm.restore(snapshot)
        self.assertEqual((CHEF.batches(chef)[parent['batch_id']]['count'], CHEF.batches(chef)[child['batch_id']]['count']), (0, 1))
        batch = CHEF.batches(chef)[child['batch_id']]
        batch['components'][0]['ingredient']['stock']['unit'] = 2
        self.assertFalse(e.validate_state()['valid'])
        batch['components'][0]['ingredient']['stock']['unit'] = 1
        self.assertTrue(e.validate_state()['valid'])
        duplicate = deepcopy(batch)
        duplicate['id'] = 'chef-batch:' + chef.entity_id + ':6'
        CHEF.batches(chef)[duplicate['id']] = duplicate
        chef.spec[CHEF.SERIAL] = 6
        self.assertFalse(e.validate_state()['valid'])
        del CHEF.batches(chef)[duplicate['id']]
        chef.spec[CHEF.SERIAL] = 5
        self.assertTrue(e.validate_state()['valid'])

    def test_csv_actual_acquisition_and_parent_source_reject_recursion_before_any_cost_and_survive_restore(self):
        w, parent, second = self.prepared(csv=True)
        e, chef = w['engine'], w['chef']
        basis = CHEF.batches(chef)[parent['batch_id']]['dumplings_basis']
        self.assertEqual(basis['source'], CHEF.csv_dumplings_source(self.rules))
        self.assertEqual(basis['source']['record'], 307)
        self.reject(e, lambda: self.nested(e, chef, parent, second), 'source forbids.*another Dumplings')
        loaded, actors = FIX.restore(self.rules, e)
        owner = actors[chef.entity_id]
        self.reject(loaded, lambda: self.nested(loaded, owner, parent, second), 'source forbids.*another Dumplings')
        original = deepcopy(basis)
        basis['edition'] = 'book'
        basis['source'] = CHEF._dumplings_source(self.rules, 'book')
        self.assertFalse(e.validate_state()['valid'])
        CHEF.batches(chef)[parent['batch_id']]['dumplings_basis'] = original
        self.assertTrue(e.validate_state()['valid'])

    def test_book_second_slot_and_late_nested_failure_preserve_real_ingredients_time_and_rng(self):
        w, parent, second = self.prepared(csv=False)
        e, chef = w['engine'], w['chef']
        self.reject(e, lambda: FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': second['batch_id']}, ingredient_2={'batch_id': parent['batch_id']}), 'ingredient 2.*source forbids')
        with patch.object(CHEF, '_store_batch', side_effect=ValueError('late nested physical output failure')):
            self.reject(e, lambda: self.nested(e, chef, parent, second), 'late nested physical output failure')
        self.assertEqual(CHEF.batches(chef)[parent['batch_id']]['count'], 1)
        self.assertEqual(CHEF.batches(chef)[second['batch_id']]['count'], 2)
        self.assertTrue(e.validate_state()['valid'])

    def test_native_dismantle_keeps_book_unprinted_price_pending_but_enforces_csv_prohibition(self):
        for csv in (False, True):
            with self.subTest(csv=csv):
                w = self.scene(csv=csv)
                e, chef = w['engine'], w['chef']
                snack = FIX.cook(e, chef, recipe='tasty_snack', snack='매운맛 랩')
                dumpling = FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': snack['batch_id']}, ingredient_2={'item': CHEF.LEFTOVERS_ITEM})
                operation = lambda: e.pokemon_activity(chef, 'dismantle', item=dumpling['item_id'], chef_batch_id=dumpling['batch_id'])
                if csv:
                    self.reject(e, operation, 'CSV Dumplings cannot be sold or disassembled')
                else:
                    before = e.export_state()
                    self.assertIsInstance(operation(), C.PendingDecision)
                    self.assertEqual(e.export_state(), before)
                self.assertEqual(CHEF.batches(chef)[dumpling['batch_id']]['count'], 1)
                self.assertTrue(FIX.restore(self.rules, e)[0].validate_state()['valid'])

    def test_immediate_herb_preserves_mix_and_reuse_actual_cure_stage_consumers_after_both_restores(self):
        w = self.scene()
        e, chef, p = w['engine'], w['chef'], w['partner']
        first = FIX.cook(e, chef, recipe='preserves', origin='item/멘탈허브')
        second = FIX.cook(e, chef, recipe='preserves', origin='item/하양허브')
        mixed = FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': first['batch_id']}, ingredient_2={'batch_id': second['batch_id']})
        served = FIX.serve(e, chef, mixed['batch_id'], p)
        e.apply_status(p, '혼란', source='move/이상한빛', applied_by=w['foe'])
        e.change_stage(p, 'def', -2)
        e.gm.snapshot('actual two Herb composite')
        loaded, actors = FIX.restore(self.rules, e)
        for current, target, cook in ((loaded, actors[p.entity_id], actors[chef.entity_id]), (e, p, chef)):
            result = current.consume_food_buff(target, buff_id=served['buff_id'], action_kind='free', action_reason='GM observed immediate Herb trade-in')
            self.assertEqual([part['kind'] for part in result['components']], ['herb_cure_volatile', 'herb_reset_lowered'])
            self.assertNotIn('혼란', target.conditions)
            self.assertEqual(target.stages['def'], 0)
            FIX.decline_all(current, cook)
            self.assertTrue(current.validate_state()['valid'])
        e.gm.restore('actual two Herb composite')
        self.assertEqual(p.stages['def'], -2)
        self.assertEqual(FOOD.get_buff(p, served['buff_id'])['effect']['kind'], 'chef_composite')

    def test_six_suppressant_berry_preserves_use_current_owner_and_exact_component_growth_sources(self):
        for item, stat in V.SUPPRESSANT_BERRIES.items():
            with self.subTest(item=item), patch.dict(FIX.INVENTORY, {item: 1}):
                w = self.scene()
                e, chef, p = w['engine'], w['chef'], w['partner']
                preserved = FIX.cook(e, chef, recipe='preserves', origin=item)
                mixed = FIX.cook(e, chef, recipe='dumplings', ingredient_1={'item': CHEF.LEFTOVERS_ITEM}, ingredient_2={'batch_id': preserved['batch_id']})
                served = FIX.serve(e, chef, mixed['batch_id'], p)
                FIX.battle(e, p)
                before = e.export_state()
                self.assertIsInstance(e.consume_food_buff(p, buff_id=served['buff_id'], action_kind='free', action_reason='GM observed Berry trade-in'), C.PendingDecision)
                self.assertEqual(e.export_state(), before)
                old = deepcopy(p.spec['stats'])
                result = e.consume_food_buff(p, buff_id=served['buff_id'], action_kind='free', action_reason='GM observed Berry trade-in', owner_consent_by=chef)
                self.assertEqual(result['components'][1]['item'], item)
                self.assertEqual(result['components'][1]['owner_id'], chef.entity_id)
                self.assertEqual(p.spec['stats'][stat], old[stat] - 1)
                FIX.decline_all(e, chef)
                self.assertTrue(FIX.restore(self.rules, e)[0].validate_state()['valid'])

    def test_power_herb_composite_consumes_only_with_actual_setup_move_and_applies_leftovers(self):
        with patch.object(FIX, 'MOVES', FIX.MOVES + ['move/솔라빔']):
            w = self.scene()
        e, chef, p, foe = w['engine'], w['chef'], w['partner'], w['foe']
        e.gm.observe_loyalty(p, 6, reason='actual current owner before the Set-Up Move')
        preserved = FIX.cook(e, chef, recipe='preserves', origin='item/파워풀허브')
        mixed = FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': preserved['batch_id']}, ingredient_2={'item': CHEF.LEFTOVERS_ITEM})
        served = FIX.serve(e, chef, mixed['batch_id'], p)
        FIX.battle(e, p)
        e.consume_food_buff(p, buff_id=served['buff_id'], move_id='move/솔라빔')
        self.assertEqual(p.buffs[0]['id'], served['buff_id'])
        loaded, actors = FIX.restore(self.rules, e)
        target, enemy = actors[p.entity_id], actors[foe.entity_id]
        with patch.object(Engine, 'd20', return_value=10):
            loaded.use_move_on(target, enemy, 'move/솔라빔', loaded.everyone)
        self.assertIsNone(target.setup_move)
        receipt = FIX.receipt(target)
        self.assertEqual(receipt['benefit']['kind'], 'skip_setup')
        self.assertEqual(receipt['benefit']['composite'][0]['kind'], 'turn_heal')
        self.assertEqual(len(target.spec['food_turn_healing']), 1)
        FIX.decline_all(loaded, actors[chef.entity_id])
        self.assertTrue(loaded.validate_state()['valid'])

    def test_meal_planner_four_printed_products_reach_native_drink_consumers_and_keep_rank_prices(self):
        products = CHEF.definitions(self.rules)['recipes'][CHEF.MEAL_PLANNER]['products']
        for uid, row in products.items():
            with self.subTest(item=uid):
                w = FIX.scene(self.rules, feats=(CHEF.CLASS,), intuition=row['book_rank'])
                e, chef, p = w['engine'], w['chef'], w['partner']
                made = FIX.cook(e, chef, recipe='meal_planner', item=uid, event_id='actual-meal-planner')
                self.assertEqual((made['item_id'], made['money_spent'], chef.spec['items'][uid]), (uid, row['money'], 1))
                self.assertEqual(made['meal_planner_basis']['intuition_rank'], row['book_rank'])
                self.assertEqual((chef.spec['money'], e.elapsed_seconds), (2000-row['money'], 300))
                p.hp = 1
                e.use_item(chef, uid, p, duration_minutes=1, duration_reason='actual printed drink intake')
                self.assertEqual(p.hp, min(p.max_hp, 1+FOOD.DRINKS[uid]))
                self.assertEqual(chef.spec['items'][uid], 0)
                self.assertFalse(p.buffs)
                before = e.export_state()
                replay = FIX.cook(e, chef, recipe='meal_planner', item=uid, event_id='actual-meal-planner')
                self.assertEqual(replay['production_id'], made['production_id'])
                self.assertEqual(e.export_state(), before)
                self.assertTrue(FIX.restore(self.rules, e)[0].validate_state()['valid'])

    def test_meal_planner_real_csv_fruit_rank_is_selected_historically_without_mixing_homebrew_prices(self):
        w = FIX.scene(self.rules, feats=(CHEF.CLASS,), intuition=4)
        e, chef = w['engine'], w['chef']
        self.reject(e, lambda: FIX.cook(e, chef, recipe='meal_planner', item='item/후르츠밀크'), 'selected printed Intuition rank')
        self.reject(e, lambda: FIX.cook(e, chef, recipe='meal_planner', item='item/튼튼밀크', edition='local_csv'), 'selected printed Intuition rank')
        self.reject(e, lambda: FIX.cook(e, chef, recipe='meal_planner', item='item/맛있는물', edition='homebrew'), 'exact book or local_csv')
        made = FIX.cook(e, chef, recipe='meal_planner', item='item/후르츠밀크', edition='local_csv', event_id='csv-fruit')
        self.assertEqual((made['money_spent'], made['recipe_source'], chef.spec['money']), (125, CHEF.MEAL_PLANNER, 1875))
        self.assertEqual(made['meal_planner_basis']['source']['record'], 10)
        self.assertEqual(made['meal_planner_basis']['source']['columns'], [4, 5, 6, 7])
        self.reject(e, lambda: FIX.cook(e, chef, recipe='meal_planner', item='item/후르츠밀크', event_id='csv-fruit'), 'original request')
        snapshot = e.gm.snapshot('selected actual Meal Planner source')
        loaded, actors = FIX.restore(self.rules, e)
        target = actors[chef.entity_id]
        record = target.spec['crafting_products'][made['production_id']]['transformation']['result']
        record['meal_planner_basis']['edition'] = 'book'
        self.assertFalse(loaded.validate_state()['valid'])
        e.gm.restore(snapshot)
        self.assertEqual(chef.spec['crafting_products'][made['production_id']]['transformation']['result']['meal_planner_basis']['edition'], 'local_csv')
        self.assertTrue(e.validate_state()['valid'])

    def test_five_fixed_stage_berry_preserves_reuse_native_stages_and_two_actual_units(self):
        for uid, stat in FOOD.BERRY_STAGES.items():
            with self.subTest(item=uid), patch.dict(FIX.INVENTORY, {uid: 1}):
                w = self.scene(csv=False)
                e, chef, p = w['engine'], w['chef'], w['partner']
                made = FIX.cook(e, chef, recipe='preserves', origin=uid)
                self.assertEqual((made['batch']['count'], chef.spec['items'][uid]), (2, 0))
                first = FIX.serve(e, chef, made['batch_id'], p)
                FIX.battle(e, p)
                self.reject(e, lambda: e.consume_food_buff(p, buff_id=first['buff_id'], action_kind='free', action_reason='actual Berry trade-in'), 'HP at most half')
                p.hp = p.base_max_hp//2
                used = e.consume_food_buff(p, buff_id=first['buff_id'], action_kind='free', action_reason='actual Berry trade-in')
                self.assertEqual((used['stat'], used['actual_delta'], p.stages[stat]), (stat, 1, 1))
                FIX.decline_all(e, chef)
                e.end_encounter(e.everyone)
                second = FIX.cook(e, chef, recipe='dumplings', ingredient_1={'item': CHEF.LEFTOVERS_ITEM}, ingredient_2={'batch_id': made['batch_id']})
                served = FIX.serve(e, chef, second['batch_id'], p)
                FIX.battle(e, p)
                snapshot = e.gm.snapshot('actual stage Berry composite')
                loaded, actors = FIX.restore(self.rules, e)
                for current, target, cook in ((loaded, actors[p.entity_id], actors[chef.entity_id]), (e, p, chef)):
                    target.hp = target.base_max_hp//2
                    result = current.consume_food_buff(target, buff_id=served['buff_id'], action_kind='free', action_reason='actual composite Berry trade-in')
                    self.assertEqual([part['kind'] for part in result['components']], ['turn_heal', 'stage_change'])
                    self.assertEqual(target.stages[stat], 1)
                    self.assertEqual(CHEF.batches(cook)[made['batch_id']]['count'], 0)
                    FIX.decline_all(current, cook)
                    self.assertTrue(current.validate_state()['valid'])
                e.gm.restore(snapshot)
                self.assertEqual(FOOD.get_buff(p, served['buff_id'])['effect']['components'][1]['effect']['stat'], stat)

    def test_unresolved_distinct_trigger_pair_is_still_atomic_not_a_completed_contract(self):
        for csv in (False, True):
            with self.subTest(csv=csv):
                w = self.scene(csv=csv)
                e, chef = w['engine'], w['chef']
                spicy = FIX.cook(e, chef, recipe='tasty_snack', snack='매운맛 랩')
                berry = FIX.cook(e, chef, recipe='preserves', origin='item/오카열매')
                self.reject(e, lambda: FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': spicy['batch_id']}, ingredient_2={'batch_id': berry['batch_id']}), 'GM trade-in policy before use')
                self.assertEqual((CHEF.batches(chef)[spicy['batch_id']]['count'], CHEF.batches(chef)[berry['batch_id']]['count']), (1, 2))

    def test_suppressant_component_consent_survives_actual_attack_hit_and_setup_trigger_choices(self):
        for trigger in ('attack', 'hit', 'setup'):
            with self.subTest(trigger=trigger), patch.dict(FIX.INVENTORY, {'토망열매': 1}), patch.object(FIX, 'MOVES', FIX.MOVES + ['move/솔라빔']):
                w = self.scene()
                e, chef, p, foe = w['engine'], w['chef'], w['partner'], w['foe']
                e.gm.observe_loyalty(p, 6, reason='actual current owner before the Set-Up Move')
                stat = FIX.cook(e, chef, recipe='preserves', origin='item/토망열매')
                if trigger=='attack':
                    first = FIX.cook(e, chef, recipe='tasty_snack', snack='매운맛 랩')
                else:
                    first = FIX.cook(e, chef, recipe='preserves', origin='item/카리열매' if trigger=='hit' else 'item/파워풀허브')
                mixed = FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': first['batch_id']}, ingredient_2={'batch_id': stat['batch_id']})
                served = FIX.serve(e, chef, mixed['batch_id'], p)
                FIX.battle(e, p)
                options = {'move_id':'move/솔라빔'} if trigger=='setup' else {}
                e.consume_food_buff(p, buff_id=served['buff_id'], owner_consent_by=chef, **options)
                loaded, actors = FIX.restore(self.rules, e)
                target, enemy = actors[p.entity_id], actors[foe.entity_id]
                speed = target.spec['stats']['spe']
                if trigger=='setup':
                    with patch.object(Engine, 'd20', return_value=10):
                        loaded.use_move_on(target, enemy, 'move/솔라빔', loaded.everyone)
                else:
                    attacker, defender = (target, enemy) if trigger=='attack' else (enemy, target)
                    loaded.roll_damage(attacker, defender, loaded.r.move('move/몸통박치기'), set_damage=True)
                self.assertEqual(target.spec['stats']['spe'], speed-1)
                self.assertEqual(FIX.receipt(target)['benefit']['composite'][0]['item'], 'item/토망열매')
                FIX.decline_all(loaded, actors[chef.entity_id])
                self.assertTrue(loaded.validate_state()['valid'])

    def test_restorative_preserves_keep_native_medicine_actions_herbal_history_and_no_snack_slots(self):
        with patch.dict(FIX.INVENTORY, {'힘의뿌리': 2, '부활초': 1, '파스': 1, '힘의가루': 1, '만능가루': 1}):
            w = self.scene()
        e, chef, p = w['engine'], w['chef'], w['partner']
        for invalid in ('item/파스', 'item/힘의가루', 'item/만능가루'):
            self.reject(e, lambda uid=invalid: FIX.cook(e, chef, recipe='preserves', origin=uid), 'Berry, Herb or Mushroom')
        self.reject(e, lambda: FIX.cook(e, chef, recipe='preserves', origin='item/힘의뿌리', taste='단맛'), 'non-Snack')
        root = FIX.cook(e, chef, recipe='preserves', origin='item/힘의뿌리')
        revival = FIX.cook(e, chef, recipe='preserves', origin='item/부활초')
        self.assertEqual((chef.spec['money'], chef.spec['items']['힘의뿌리'], chef.spec['items']['부활초']), (1900, 1, 0))
        self.assertIsNone(root['batch']['taste'])
        snapshot = e.gm.snapshot('native restorative Preserves')
        loaded, actors = FIX.restore(self.rules, e)
        for current, cook, target in ((e, chef, p), (loaded, actors[chef.entity_id], actors[p.entity_id])):
            target.hp = 1
            FIX.battle(current, cook)
            result = FIX.serve(current, cook, root['batch_id'], target)
            self.assertEqual(result, (1, 0))
            self.assertEqual(target.hp, min(target.max_hp, 71))
            self.assertEqual(cook.budget['standard'], 0)
            self.assertEqual(target.pending_action_loss, {'standard': 1, 'swift': 1})
            self.assertEqual(FOOD.herbal_state(target)['count'], 1)
            self.assertTrue(all(buff['source'] == FOOD.MEDICINE for buff in target.buffs))
            self.assertEqual(target.buffs[0]['effect'], {'kind': 'save_bonus', 'amount': 2})
            current.end_encounter(current.everyone)
            target.hp = 0
            current.check_fainted(target)
            FIX.battle(current, cook)
            FIX.serve(current, cook, revival['batch_id'], target)
            self.assertFalse(target.fainted)
            self.assertEqual(target.hp, target.base_max_hp // 2)
            self.assertEqual(FOOD.herbal_state(target)['count'], 2)
            self.assertEqual(CHEF.batches(cook)[revival['batch_id']]['count'], 1)
            self.assertTrue(all(buff['source'] == FOOD.MEDICINE for buff in target.buffs))
            self.assertTrue(current.validate_state()['valid'])
        e.gm.restore(snapshot)
        self.assertEqual(CHEF.batches(chef)[root['batch_id']]['count'], 2)
        other = FIX.cook(e, chef, recipe='preserves', origin='item/버치열매')
        mixed = FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': root['batch_id']}, ingredient_2={'batch_id': other['batch_id']})
        served = FIX.serve(e, chef, mixed['batch_id'], p)
        p.hp = 1
        e.apply_status(p, '마비', applied_by=w['foe'])
        with patch.object(Engine, 'd20', return_value=20):
            FIX.battle(e, p)  # Native successful Paralysis save admits this Free action.
        used = e.consume_food_buff(p, buff_id=served['buff_id'], action_kind='free', action_reason='actual mixed preserved medicine')
        self.assertEqual([part['kind'] for part in used['components']], ['native_consumable', 'cure'])
        self.assertNotIn('마비', p.conditions)
        self.assertEqual(FOOD.herbal_state(p)['count'], 1)
        self.assertTrue(e.validate_state()['valid'])

    def test_actual_mushroom_origin_fixed_plan_is_shared_by_two_native_units_without_free_appraisal(self):
        for uid in HERB.MUSHROOMS:
            with self.subTest(item=uid):
                w = self.scene()
                e, chef, p = w['engine'], w['chef'], w['partner']
                source = 'actual-preserves-' + uid.split('/')[1]
                WORLD.register_object(e, source, location={'kind': 'unknown'}, reason='actual Mushroom for Preserves', kind='item_instance', item_rule_id=uid, owner_id=chef.entity_id)
                ITEMS.equip_held(e, chef, uid, source_instance_id=source)
                # The actual Survival owner fixes and identifies this physical body's effect.
                chef.spec['skills']['생존'] = 4
                identified = e.appraise_mushroom(chef, instance_id=source, fixed=[6] * 4)
                self.assertEqual(identified['status'], 'identified')
                before_rng = e.rng.getstate()
                before_appraisals = deepcopy(e._physical_objects[source][HERB.APPRAISALS])
                result = FIX.cook(e, chef, recipe='preserves', origin={'item': uid, 'instance_id': source})
                batch_id = result['batch_id']
                batch = CHEF.batches(chef)[batch_id]
                self.assertEqual(batch['origin_body']['plan']['stats'], identified['stats'])
                self.assertEqual(e.rng.getstate(), before_rng)
                self.assertEqual(e._physical_objects[source][HERB.APPRAISALS], before_appraisals)
                self.assertIn('consumed', e._physical_objects[source])
                snapshot = e.gm.snapshot('two actual Mushroom Preserves')
                loaded, actors = FIX.restore(self.rules, e)
                for current, cook, target in ((e, chef, p), (loaded, actors[chef.entity_id], actors[p.entity_id])):
                    rng = current.rng.getstate()
                    for unit in (1, 2):
                        if uid == 'item/향기버섯':current.apply_status(target, '화상', applied_by=WORLD.actor_index(current)[w['foe'].entity_id])
                        FIX.battle(current, target)
                        consumed = FIX.serve(current, cook, batch_id, target)
                        self.assertEqual(consumed['stats'], identified['stats'])
                        self.assertEqual(consumed['item_stock']['unit'], unit)
                        self.assertEqual(target.budget['swift'], 0)
                        self.assertFalse(target.buffs)
                        current.end_of_turn(target)
                    self.assertEqual(CHEF.batches(cook)[batch_id]['count'], 0)
                    self.assertEqual(current.rng.getstate(), rng)
                    self.assertTrue(current.validate_state()['valid'])
                e.gm.restore(snapshot)
                self.assertEqual(CHEF.batches(chef)[batch_id]['count'], 2)
                body = CHEF.batches(chef)[batch_id]['origin_body']
                body['instance_id'] = 'another-origin-body'
                self.assertFalse(e.validate_state()['valid'])
                body['instance_id'] = source
                self.assertTrue(e.validate_state()['valid'])
                other_source = source + '-different-actual-origin'
                WORLD.register_object(e, other_source, location={'kind': 'unknown'}, reason='a different actual Mushroom body', kind='item_instance', item_rule_id=uid, owner_id=chef.entity_id)
                ITEMS.equip_held(e, chef, uid, source_instance_id=other_source)
                other = FIX.cook(e, chef, recipe='preserves', origin={'item': uid, 'instance_id': other_source})
                self.assertTrue(e.validate_state()['valid'])
                original = deepcopy(CHEF.batches(chef)[batch_id])
                # Even another genuinely paid/consumed body cannot replace this
                # production's original identity, including a self-consistent effect.
                forged = CHEF.batches(chef)[batch_id]
                forged['origin_body'] = deepcopy(other['batch']['origin_body'])
                forged['payload']['origin_body'] = deepcopy(other['batch']['origin_body'])
                self.assertFalse(e.validate_state()['valid'])
                with self.assertRaises(ValueError):
                    FIX.restore(self.rules, e)
                CHEF.batches(chef)[batch_id] = original
                self.assertTrue(e.validate_state()['valid'])
        w = self.scene()
        e, chef = w['engine'], w['chef']
        WORLD.register_object(e, 'unidentified-origin', location={'kind': 'unknown'}, reason='actual unidentified Mushroom', kind='item_instance', item_rule_id='item/작은버섯', owner_id=chef.entity_id)
        ITEMS.equip_held(e, chef, '작은버섯', source_instance_id='unidentified-origin')
        before = deepcopy(e._physical_objects['unidentified-origin'])
        with patch.object(CHEF, '_store_batch', side_effect=ValueError('late Mushroom transformation failure')):
            self.reject(e, lambda: FIX.cook(e, chef, recipe='preserves', origin={'item': '작은버섯', 'instance_id': 'unidentified-origin'}), 'late Mushroom transformation failure')
        self.assertEqual(e._physical_objects['unidentified-origin'], before)
        result = FIX.cook(e, chef, recipe='preserves', origin={'item': '작은버섯', 'instance_id': 'unidentified-origin'})
        obj = e._physical_objects['unidentified-origin']
        self.assertNotIn(HERB.APPRAISALS, obj)
        self.assertEqual(obj[HERB.PLAN], result['batch']['origin_body']['plan'])
        self.assertTrue(e.validate_state()['valid'])


    def test_clear_native_berries_keep_both_preserves_units_randomness_status_accuracy_and_critical_lifetimes(self):
        import random
        import combat_stage_sources as STAGES
        import combat_timing as TIMING
        for uid in ('item/리샘열매', 'item/랑사열매', 'item/스타열매', 'item/미클열매'):
            with self.subTest(item=uid):
                w = self.scene()
                e, chef, p = w['engine'], w['chef'], w['partner']
                chef.spec['items'][uid] = 1
                result = FIX.cook(e, chef, recipe='preserves', origin=uid)
                batch_id = result['batch_id']
                self.assertEqual((result['money_spent'], result['count'], chef.spec['items'].get(uid, 0)), (50, 2, 0))
                snapshot = e.gm.snapshot('actual clear Berry units')
                loaded, actors = FIX.restore(self.rules, e)
                for current, cook, target in ((e, chef, p), (loaded, actors[chef.entity_id], actors[p.entity_id])):
                    for unit in (1, 2):
                        served = FIX.serve(current, cook, batch_id, target)
                        choices = None
                        if uid == 'item/리샘열매':
                            current.apply_status(target, '독', applied_by=WORLD.actor_index(current)[w['foe'].entity_id])
                            current.apply_status(target, '화상', applied_by=WORLD.actor_index(current)[w['foe'].entity_id])
                            choices = {'condition': '독'}
                        target.hp = target.base_max_hp // 4
                        FIX.battle(current, target)
                        if uid == 'item/리샘열매':
                            self.assertIsInstance(current.consume_food_buff(target, buff_id=served['buff_id'], action_kind='free', action_reason='actual Berry use'), C.PendingDecision)
                            self.assertIn('독', target.conditions)
                        if uid == 'item/스타열매':
                            target.hp = target.base_max_hp // 4 + 1
                            self.reject(current, lambda: current.consume_food_buff(target, buff_id=served['buff_id'], action_kind='free', action_reason='actual Berry use'), 'one quarter')
                            target.hp = target.base_max_hp // 4
                        expected_rng = random.Random(); expected_rng.setstate(current.rng.getstate())
                        expected_stat = expected_rng.choice(STAGES.STATS) if uid == 'item/스타열매' else None
                        with patch.object(Engine, 'change_stage', side_effect=ValueError('late Berry native effect')) if uid == 'item/스타열매' else __import__('contextlib').nullcontext():
                            if uid == 'item/스타열매':self.reject(current, lambda: current.consume_food_buff(target, buff_id=served['buff_id'], action_kind='free', action_reason='actual Berry use'), 'late Berry native effect')
                        used = current.consume_food_buff(target, buff_id=served['buff_id'], action_kind='free', action_reason='actual Berry use', berry_choices=choices)
                        if uid == 'item/리샘열매':
                            self.assertTrue(used['cured']);self.assertNotIn('독', target.conditions);self.assertIn('화상', target.conditions)
                        elif uid == 'item/스타열매':
                            self.assertEqual((used['stat'], used['actual_delta']), (expected_stat, 2))
                            self.assertEqual(current.rng.getstate(), expected_rng.getstate())
                        elif uid == 'item/미클열매':self.assertEqual((used['actual_delta'], target.accuracy_stage), (1, 1))
                        else:
                            self.assertEqual(ITEMS.crit_delta(target, self.rules.move('move/몸통박치기'), engine=current), 1)
                            row = next(r for r in TIMING.records(target) if r.get('berry_critical'))
                            row['receipt_sequence'] += 100
                            self.assertFalse(current.validate_state()['valid'])
                            row['receipt_sequence'] -= 100
                        self.assertEqual(CHEF.batches(cook)[batch_id]['count'], 2-unit)
                        self.reject(current, lambda: current.consume_food_buff(target, buff_id=served['buff_id'], action_kind='free', action_reason='replay'), 'actual acquired')
                        FIX.decline_all(current, cook)
                        self.assertTrue(current.validate_state()['valid'])
                        current.end_encounter(current.everyone)
                        self.assertEqual(target.accuracy_stage, 0)
                        self.assertEqual(ITEMS.crit_delta(target, self.rules.move('move/몸통박치기'), engine=current), 0)
                        for status in ('독', '화상'):current.cure_status(target, status)
                e.gm.restore(snapshot)
                self.assertEqual(CHEF.batches(chef)[batch_id]['count'], 2)
                self.assertTrue(e.validate_state()['valid'])

    def test_leppa_and_lum_composite_choose_actual_status_and_spent_scene_move_through_native_owners(self):
        from builder import build_pokemon
        from engine import Combatant
        import frequency as FREQ
        w = self.scene()
        e, chef = w['engine'], w['chef']
        p = Combatant(self.rules, build_pokemon(self.rules, '이브이', 20, name='actual Scene Move eater', moves=['move/전기자석파', 'move/파괴광선'], abilities=[], extra={'trainer_id': chef.entity_id, 'trainer': chef.name}))
        e.gm.add_combatant(p, side='party', pos=(0, 1), reason='actual Berry recipient with Scene and Daily Moves')
        e.gm.observe_loyalty(p, 6, reason='actual owner observation')
        for uid in ('item/리샘열매', 'item/과사열매'):chef.spec['items'][uid] = 1
        lum = FIX.cook(e, chef, recipe='preserves', origin='item/리샘열매')
        leppa = FIX.cook(e, chef, recipe='preserves', origin='item/과사열매')
        mixed = FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': lum['batch_id']}, ingredient_2={'batch_id': leppa['batch_id']})
        served = FIX.serve(e, chef, mixed['batch_id'], p)
        FIX.battle(e, p)
        with patch.object(Engine, 'd20', return_value=20):e.use_move_on(p, w['foe'], 'move/전기자석파', e.everyone)
        self.assertEqual(p.move_uses['move/전기자석파'], 1)
        e.apply_status(p, '독', applied_by=w['foe'])
        e.apply_status(p, '화상', applied_by=w['foe'])
        p.hp = p.base_max_hp // 2
        snapshot = e.gm.snapshot('real Scene use and composite Berry')
        loaded, actors = FIX.restore(self.rules, e)
        for current, target in ((e, p), (loaded, actors[p.entity_id])):
            self.reject(current, lambda: current.consume_food_buff(target, buff_id=served['buff_id'], action_kind='free', action_reason='actual composite Berry', berry_choices={'condition': '독', 'move_id': 'move/파괴광선'}), 'already used|actual known|Scene')
            with patch.object(FREQ, 'restore_scene_use', side_effect=ValueError('late actual Scene restoration')):
                self.reject(current, lambda: current.consume_food_buff(target, buff_id=served['buff_id'], action_kind='free', action_reason='actual composite Berry', berry_choices={'condition': '독', 'move_id': 'move/전기자석파'}), 'late actual Scene restoration')
            used = current.consume_food_buff(target, buff_id=served['buff_id'], action_kind='free', action_reason='actual composite Berry', berry_choices={'condition': '독', 'move_id': 'move/전기자석파'})
            self.assertEqual([r['kind'] for r in used['components']], ['berry_cure_any', 'berry_scene_move'])
            self.assertNotIn('독', target.conditions);self.assertIn('화상', target.conditions)
            self.assertEqual(target.move_uses['move/전기자석파'], 0)
            self.assertEqual(used['components'][1]['restored'], 1)
            self.assertNotIn(FOOD.BERRY_CHOICE, target.spec)
            FIX.decline_all(current, WORLD.actor_index(current)[chef.entity_id])
            self.assertTrue(current.validate_state()['valid'])
        e.gm.restore(snapshot)
        self.assertEqual(p.move_uses['move/전기자석파'], 1)
        self.assertIn('독', p.conditions)


    def test_flavor_preserves_bind_actual_nature_and_explicit_kr_en_disliked_source_without_price_or_taste_mix(self):
        import arithmetic_policy as M
        for uid, flavor in [('item/무화열매','매운맛'),('item/위키열매','떫은맛'),('item/마고열매','단맛'),('item/아바열매','쓴맛'),('item/파야열매','신맛')]:
            with self.subTest(item=uid):
                w = self.scene(nature=FIX.nature_for(self.rules, flavor, 'disliked'))
                e, chef, p = w['engine'], w['chef'], w['partner']
                chef.spec['items'][uid] = 1
                made = FIX.cook(e, chef, recipe='preserves', origin=uid)
                self.assertEqual(made['batch']['payload']['flavor'], flavor)
                snapshot = e.gm.snapshot('flavor sources before both units')
                loaded, actors = FIX.restore(self.rules, e)
                for current, cook, target in ((e,chef,p),(loaded,actors[chef.entity_id],actors[p.entity_id])):
                    for edition in ('kr_book','core_en_1_05'):
                        served = FIX.serve(current,cook,made['batch_id'],target)
                        target.hp = 1
                        FIX.battle(current,target)
                        before = target.hp
                        answer = current.consume_food_buff(target,buff_id=served['buff_id'],action_kind='free',action_reason='actual source-selected Treat Berry')
                        self.assertIsInstance(answer,C.PendingDecision)
                        self.assertEqual(target.hp,before)
                        self.reject(current,lambda:current.consume_food_buff(target,buff_id=served['buff_id'],action_kind='free',action_reason='actual Treat Berry',berry_choices={'flavor_edition':'invented'}),'exact printed')
                        used = current.consume_food_buff(target,buff_id=served['buff_id'],action_kind='free',action_reason='actual source-selected Treat Berry',berry_choices={'flavor_edition':edition})
                        self.assertEqual(used['healed'],0 if edition=='kr_book' else M.ratio(target.base_max_hp,8))
                        self.assertEqual((used['disposition'],used['edition']),('disliked',edition))
                        self.assertIn('혼란',target.conditions)
                        FIX.decline_all(current,cook)
                        self.assertTrue(current.validate_state()['valid'])
                        current.end_encounter(current.everyone)
                        current.cure_status(target,'혼란')
                e.gm.restore(snapshot)
                self.assertEqual(CHEF.batches(chef)[made['batch_id']]['count'],2)
        for disposition in ('liked','neutral'):
            nature=FIX.nature_for(self.rules,'매운맛','liked') if disposition=='liked' else None
            w=self.scene(nature=nature);e,chef,p=w['engine'],w['chef'],w['partner']
            chef.spec['items']['무화열매']=1
            made=FIX.cook(e,chef,recipe='preserves',origin='item/무화열매')
            served=FIX.serve(e,chef,made['batch_id'],p);p.hp=1;FIX.battle(e,p)
            used=e.consume_food_buff(p,buff_id=served['buff_id'],action_kind='free',action_reason='agreeing printed Treat Berry')
            self.assertEqual(used['healed'],M.ratio(p.base_max_hp,6 if disposition=='liked' else 8))
            self.assertNotIn('혼란',p.conditions)

    def test_reactive_preserves_observe_final_native_damage_not_preview_and_exchange_one_unit_across_restores(self):
        import arithmetic_policy as M
        for uid, mid in [('item/의문열매','move/몸통박치기'),('item/자보열매','move/몸통박치기'),('item/애터열매','move/염동력'),('item/악키열매','move/몸통박치기'),('item/타라프열매','move/염동력')]:
            with self.subTest(item=uid):
                w=self.scene();e,chef,p,foe=w['engine'],w['chef'],w['partner'],w['foe']
                chef.spec['items'][uid]=1
                made=FIX.cook(e,chef,recipe='preserves',origin=uid)
                served=FIX.serve(e,chef,made['batch_id'],p)
                FIX.battle(e,foe)
                e.consume_food_buff(p,buff_id=served['buff_id'])
                # A genuine native calculation is still not a finalized hit.
                e.roll_damage(foe,p,self.rules.move(mid),set_damage=True)
                self.assertEqual(len(p.buffs),1)
                snapshot=e.gm.snapshot('armed actual reactive Berry')
                loaded,actors=FIX.restore(self.rules,e)
                for current,cook,target,attacker in ((e,chef,p,foe),(loaded,actors[chef.entity_id],actors[p.entity_id],actors[foe.entity_id])):
                    if uid=='item/의문열매':
                        # The actual damage formula receives Fighting, while the
                        # printed Move remains Normal. No food-side type guess.
                        context=patch('effects_ext.effective_type',return_value='격투')
                    else:context=__import__('contextlib').nullcontext()
                    before_attacker=attacker.hp
                    with context:current.resolve_attack_damage(attacker,target,self.rules.move(mid),set_damage=True)
                    receipt=FIX.receipt(target);benefit=receipt['benefit']
                    self.assertEqual(receipt['producer'],'actual_berry_hit')
                    self.assertEqual(benefit['actual_damage_type'],'격투' if uid=='item/의문열매' else self.rules.move(mid)['type'])
                    self.assertEqual(benefit['damage_receipt']['source'],mid)
                    if uid=='item/의문열매':self.assertEqual(target.temp_hp,M.ratio(target.base_max_hp,6))
                    elif uid in ('item/자보열매','item/애터열매'):self.assertEqual(before_attacker-attacker.hp,M.ratio(attacker.base_max_hp,8))
                    else:self.assertEqual((benefit['actual_delta'],target.stages['def' if uid=='item/악키열매' else 'spd']),(1,1))
                    self.assertNotIn(FOOD.BERRY_HIT_CHOICE,target.spec)
                    self.assertFalse(target.buffs)
                    self.assertEqual(CHEF.batches(cook)[made['batch_id']]['count'],1)
                    before=len(target.spec['food_consumption_receipts'])
                    current.resolve_attack_damage(attacker,target,self.rules.move('move/몸통박치기'),set_damage=True)
                    self.assertEqual(len(target.spec['food_consumption_receipts']),before)
                    FIX.decline_all(current,cook)
                    self.assertTrue(current.validate_state()['valid'])
                    current.end_encounter(current.everyone)
                    if target.fainted:current.gm.revive(target,hp=target.base_max_hp,reason='second actual Preserve unit recipient')
                    else:current.gm.set_hp(target,value=target.base_max_hp,reason='second actual Preserve unit recipient')
                    second=FIX.serve(current,cook,made['batch_id'],target)
                    FIX.battle(current,attacker)
                    current.consume_food_buff(target,buff_id=second['buff_id'])
                    with patch('effects_ext.effective_type',return_value='격투') if uid=='item/의문열매' else __import__('contextlib').nullcontext():
                        current.resolve_attack_damage(attacker,target,self.rules.move(mid),set_damage=True)
                    self.assertEqual(CHEF.batches(cook)[made['batch_id']]['count'],0)
                    self.assertEqual(len(target.spec['food_consumption_receipts']),2)
                    FIX.decline_all(current,cook)
                    self.assertTrue(current.validate_state()['valid'])
                e.gm.restore(snapshot)
                self.assertEqual(len(p.buffs),1)
                self.assertIn(FOOD.BERRY_HIT_CHOICE,p.spec)

    def test_custap_preserves_use_actual_ordinary_priority_loan_and_keep_stock_and_rng_on_late_failure(self):
        w=self.scene();e,chef,p,foe=w['engine'],w['chef'],w['partner'],w['foe']
        chef.spec['items']['애슈열매']=1
        made=FIX.cook(e,chef,recipe='preserves',origin='item/애슈열매')
        served=FIX.serve(e,chef,made['batch_id'],p)
        e.gm.observe_loyalty(p,6,reason='actual owner observation')
        # The two actual Eevee have equal initiative: choose explicit stable
        # singleton order groups rather than leaving schedule preparation Pending.
        bindings=[{'slot':actor.entity_id,'actor_id':actor.entity_id,'role':actor.entity_id} for actor in e.everyone]
        schedule=e.prepare_initiative_schedule(e.everyone,source='gm/actual Custap schedule',bindings=bindings,order_groups=[[actor.entity_id] for actor in e.everyone])
        self.assertNotEqual(schedule.get('status'),'pending')
        e.start_round(e.everyone)
        self.reject(e,lambda:e.consume_food_buff(p,buff_id=served['buff_id'],move_id='move/몸통박치기'),'one quarter')
        p.hp=p.base_max_hp//4
        e.consume_food_buff(p,buff_id=served['buff_id'],move_id='move/몸통박치기')
        before=e.export_state()
        self.assertEqual(FOOD.priority_berry(e,p,'move/몸통박치기'),'item/애슈열매')
        # A plain native food gate without the paid Custap loan cannot spend it.
        self.assertTrue(FOOD.move_allowed(e,p,self.rules.move('move/몸통박치기'),self.rules.move_mech('move/몸통박치기')[0]))
        self.assertEqual(e.export_state(),before)
        snapshot=e.gm.snapshot('Custap actual unacted turn')
        loaded,actors=FIX.restore(self.rules,e)
        for current,cook,user,target in ((e,chef,p,foe),(loaded,actors[chef.entity_id],actors[p.entity_id],actors[foe.entity_id])):
            with patch.object(Engine,'use_move_on',side_effect=ValueError('late native Custap Move')):
                self.reject(current,lambda:current.use_priority_move(user,target,'move/몸통박치기'),'late native Custap Move')
            native_rest=FOOD._apply_composite_rest
            def fail_exchange(*args,**options):
                native_rest(*args,**options)
                raise ValueError('late actual Custap food exchange')
            with patch.object(FOOD,'_apply_composite_rest',side_effect=fail_exchange):
                self.reject(current,lambda:current.use_priority_move(user,target,'move/몸통박치기'),'late actual Custap food exchange')
            with patch.object(Engine,'d20',return_value=20):result=current.use_priority_move(user,target,'move/몸통박치기')
            self.assertEqual(result['source'],'item/애슈열매')
            self.assertEqual(user.budget,{'standard':0,'shift':1,'swift':1})
            self.assertEqual(user.move_uses['move/몸통박치기'],1)
            self.assertNotIn(FOOD.BERRY_PRIORITY_CHOICE,user.spec)
            self.assertEqual(FIX.receipt(user)['producer'],'actual_priority_move')
            status=current.initiative_reaction_status()
            self.assertEqual((status['status'],status['active_actor_id']),('open',user.entity_id))
            offers=FIX.pending(current,cook,CHEF.HITS)
            self.assertEqual(len(offers),1)
            self.assertEqual(offers[0]['payload']['producer'],'actual_priority_move')
            self.assertFalse(FIX.pending(current,cook,CHEF.AFTERTASTE))
            self.reject(current,lambda:current.finish_initiative_reaction(),'triggered class state action')
            accepted=current is e
            before_temp=user.temp_hp
            current.resolve_class_actor_state_action(cook,offers[0]['id'],use=accepted)
            self.assertEqual(user.temp_hp-before_temp,12 if accepted else 0)
            self.assertEqual(len(user.buffs),0)
            current.finish_initiative_reaction()
            self.assertTrue(current.initiative_reaction_status()['owed_turns'])
            FIX.decline_all(current,cook)
            self.assertTrue(current.validate_state()['valid'])
        e.gm.restore(snapshot)
        self.assertEqual(len(p.buffs),1)
        self.assertNotIn('move/몸통박치기',p.move_uses)

    def _poffin_ingredient_input(self):
        """Independent O_A builder: actual stock/history only, never another test body."""
        world=self.scene();engine,chef=world['engine'],world['chef']
        names='라즈 블리 나나 서배 파인 메호키 자야 슈박 두리 루베 버치 유루 복슝 복분 배리 무화 위키 마고 아바 파야'.split()
        # ch09:305-343: first choice is explicit for each two-stat ingredient.
        stats=('근사함','아름다움','귀여움','슬기로움','강인함',
               '근사함','귀여움','귀여움','슬기로움','근사함',
               '근사함','아름다움','귀여움','슬기로움','강인함',
               '근사함','아름다움','귀여움','슬기로움','강인함')
        cases=tuple(('item/'+name+'열매',stat) for name,stat in zip(names,stats))
        chef.spec['items']['포핀 혼합기']=1
        # 20 original + 20 cold-fresh EN products, alternate, mixed and KR; no refills.
        chef.spec['cooking_materials_value']=21500
        for uid,_ in cases:
            chef.spec['items'].pop(uid.removeprefix('item/'),None)
            chef.spec['items'][uid]=5 if uid=='item/라즈열매' else 2 if uid=='item/블리열매' else 1
        made={uid:FIX.cook(engine,chef,recipe='preserves',origin=uid) for uid,_ in cases}
        other=FIX.cook(engine,chef,recipe='preserves',origin='item/라즈열매')
        mixed=FIX.cook(engine,chef,recipe='preserves',origin='item/블리열매')
        return world,cases,made,other,mixed

    def test_ten_poffin_ingredient_preserves_use_explicit_en_full500_path_actual_production_and_native_contest_effect(self):
        import poffin_state as POFFINS
        w,cases,made,other_origin,mixed_origin=self._poffin_ingredient_input()
        e,chef,p=w['engine'],w['chef'],w['partner']
        prepared_engine,prepared_chef=e,chef
        snapshot=e.gm.snapshot('actual ingredient Preserves')
        def options(uid,stat):
            return dict(ingredients={},preserves={made[uid]['batch_id']:1},edition='core_en_1_05',
                        minutes=1,reason='actual EN500 and Berry conjunction',tie_choice=stat,event_id='actual-en-poffin/'+uid)
        first_uid,first_stat=cases[0];first_options=options(first_uid,first_stat)
        # The edition guard precedes all ingredient dispatch. Share that exact
        # atomic predicate, but retain every ingredient's actual production.
        self.reject(e,lambda:e.pokemon_activity(chef,'cook_poffins',**dict(first_options,edition=None)),'explicit core_en_1_05')
        materials=chef.spec['cooking_materials_value'];chef.spec['cooking_materials_value']=499
        self.reject(e,lambda:e.pokemon_activity(chef,'cook_poffins',**first_options),'worth500')
        chef.spec['cooking_materials_value']=materials
        produced={}
        for uid,stat in cases:
            before=chef.spec['cooking_materials_value']
            result=e.pokemon_activity(chef,'cook_poffins',**options(uid,stat));produced[uid]=result
            self.assertEqual((before-chef.spec['cooking_materials_value'],result['batch']['contest_stat'],result['batch']['count']),(500,stat,2))
            self.assertEqual(CHEF.batches(chef)[made[uid]['batch_id']]['count'],1)
            stock=result['batch']['preserves_inputs'][0]
            self.assertEqual((stock['stock']['unit'],stock['production_id'],stock['origin_item']),(1,made[uid]['production_id'],uid))
        first=produced[first_uid]
        alternate=e.pokemon_activity(chef,'cook_poffins',ingredients={},preserves={other_origin['batch_id']:1},
                    edition='core_en_1_05',minutes=1,reason='another actual identical-origin Poffin production',tie_choice=first_stat)
        self.assertEqual(chef.spec['cooking_materials_value'],11000)
        batch=chef.spec['poffin_batches'][first['batch']['id']];original=deepcopy(batch['preserves_inputs'])
        # A genuine same-origin alternate cannot replace this production's input.
        batch['preserves_inputs']=deepcopy(alternate['batch']['preserves_inputs'])
        self.assertFalse(e.validate_state()['valid'])
        with self.assertRaises(ValueError):FIX.restore(self.rules,e)
        batch['preserves_inputs']=original
        # The original world consumes its actually produced first Poffin.
        self.assertEqual(POFFINS.consumption_limit(p,engine=e),5)
        fed=e.pokemon_activity(chef,'feed_poffin',batch_id=first['batch']['id'],target=p,
                              minutes=1,reason='actual original native Poffin intake')
        self.assertEqual((fed['effective'],fed['contest_stat'],p.spec['poffins']),(True,first_stat,[first_stat]))
        self.assertEqual(chef.spec['poffin_batches'][first['batch']['id']]['count'],1)
        before_cold={'poffins':deepcopy(chef.spec['poffin_batches']),
                     'preserves':deepcopy(CHEF.batches(chef)),
                     'productions':deepcopy(chef.spec['crafting_products']),
                     'transformations':deepcopy(chef.spec['resource_transformations']),
                     'materials':chef.spec['cooking_materials_value'],'rng':e.rng.getstate(),'time':e.elapsed_seconds,
                     'consumed':deepcopy(p.spec['poffins']),'consumption':deepcopy(p.spec['poffin_consumption'])}
        # O_B's actual outputs become O_C's input through one cold reconstruction.
        e,actors=FIX.restore(self.rules,e);chef,p=actors[chef.entity_id],actors[p.entity_id]
        self.assertEqual(chef.spec['poffin_batches'],before_cold['poffins'])
        self.assertEqual(CHEF.batches(chef),before_cold['preserves'])
        self.assertEqual(chef.spec['crafting_products'],before_cold['productions'])
        self.assertEqual(chef.spec['resource_transformations'],before_cold['transformations'])
        self.assertEqual((chef.spec['cooking_materials_value'],e.rng.getstate(),e.elapsed_seconds),
                         (before_cold['materials'],before_cold['rng'],before_cold['time']))
        self.assertEqual((p.spec['poffins'],p.spec['poffin_consumption']),(before_cold['consumed'],before_cold['consumption']))
        for uid,stat in cases:
            result=produced[uid]
            self.assertEqual(e.pokemon_activity(chef,'cook_poffins',**options(uid,stat)),result)
            self.assertEqual(CHEF.batches(chef)[made[uid]['batch_id']]['count'],1)
        self.assertEqual(chef.spec['cooking_materials_value'],11000)
        # Replay checks history; new events must also consume every actual cold
        # ingredient through the native producer and its second physical unit.
        cold_produced={}
        for uid,stat in cases:
            before=chef.spec['cooking_materials_value']
            result=e.pokemon_activity(chef,'cook_poffins',**dict(options(uid,stat),event_id='cold-fresh-poffin/'+uid))
            cold_produced[uid]=result
            self.assertEqual((before-chef.spec['cooking_materials_value'],result['batch']['contest_stat'],result['batch']['count']),(500,stat,2))
            self.assertNotEqual(result['production_id'],produced[uid]['production_id'])
            self.assertEqual(CHEF.batches(chef)[made[uid]['batch_id']]['count'],0)
            stock=result['batch']['preserves_inputs'][0]
            self.assertEqual((stock['stock']['unit'],stock['production_id'],stock['origin_item']),(2,made[uid]['production_id'],uid))
        self.assertEqual(chef.spec['cooking_materials_value'],1000)
        # The same real partner retains its original consumption across cold
        # restore, then consumes the newly produced cold-world Poffin (cap5).
        cold_first=cold_produced[first_uid]
        fed=e.pokemon_activity(chef,'feed_poffin',batch_id=cold_first['batch']['id'],target=p,
                              minutes=1,reason='actual cold fresh native Poffin intake')
        self.assertEqual((fed['effective'],fed['contest_stat'],p.spec['poffins']),(True,first_stat,[first_stat,first_stat]))
        self.assertEqual(chef.spec['poffin_batches'][cold_first['batch']['id']]['count'],1)
        self.assertEqual(POFFINS.available(p,engine=e),(first_stat,first_stat))
        mixed_options=dict(ingredients={'라즈열매':2},preserves={mixed_origin['batch_id']:1},
                           edition='core_en_1_05',minutes=1,reason='actual original and preserved Berry proportions')
        self.reject(e,lambda:e.pokemon_activity(chef,'cook_poffins',**mixed_options,tie_choice='아름다움'),'unique dominant')
        mixed=e.pokemon_activity(chef,'cook_poffins',**mixed_options)
        self.assertEqual(mixed['batch']['berry_counts'],{'라즈열매':2,'블리열매':1})
        self.assertEqual((mixed['batch']['contest_stat'],chef.spec['cooking_materials_value'],chef.spec['items']['item/라즈열매']),('근사함',500,1))
        price=self.rules.item_effects('item/라즈열매')[1]['price']
        legacy=e.pokemon_activity(chef,'cook_poffins',ingredients={'라즈열매':1},minutes=1,reason='unchanged KR Berry price deduction')
        self.assertNotIn('poffin_basis',legacy['batch'])
        self.assertEqual(chef.spec['cooking_materials_value'],price)
        self.assertEqual(chef.spec['items']['item/라즈열매'],0)
        self.assertTrue(e.validate_state()['valid'])
        prepared_engine.gm.restore(snapshot)
        self.assertEqual(prepared_chef.spec['cooking_materials_value'],21500)
        self.assertTrue(all(CHEF.batches(prepared_chef)[row['batch_id']]['count']==2 for row in [*made.values(),other_origin,mixed_origin]))



    def test_pure_poffin_ingredient_leftovers_dumplings_keep_both_physical_consumers_and_actual_full_production(self):
        for ingredient_first in (True,False):
            with self.subTest(ingredient_first=ingredient_first):
                w=self.scene();e,chef,p=w['engine'],w['chef'],w['partner']
                chef.spec['items'].update({'라즈열매':2,'포핀 혼합기':1})
                chef.spec['cooking_materials_value']=1000
                berries=[FIX.cook(e,chef,recipe='preserves',origin='item/라즈열매') for _ in range(2)]
                left=[FIX.cook(e,chef,recipe='leftovers') for _ in range(3)]
                def mix(berry,leftover):
                    parts=[{'batch_id':berry['batch_id']},{'batch_id':leftover['batch_id']}]
                    if not ingredient_first:parts.reverse()
                    return FIX.cook(e,chef,recipe='dumplings',ingredient_1=parts[0],ingredient_2=parts[1])
                eaten=mix(berries[0],left[0]);cooked=mix(berries[0],left[1]);other=mix(berries[1],left[2])
                snapshot=e.gm.snapshot('two-leaf actual whole Dumplings units before either native consumer')
                loaded,actors=FIX.restore(self.rules,e)
                for current,cook,target in ((e,chef,p),(loaded,actors[chef.entity_id],actors[p.entity_id])):
                    options=dict(ingredients={},preserves={cooked['batch_id']:1},edition='core_en_1_05',minutes=1,reason='actual EN physical Poffin Ingredient Dumpling')
                    made=current.pokemon_activity(cook,'cook_poffins',**options,event_id='actual-two-leaf/'+str(ingredient_first))
                    recorded=made['batch']['preserves_inputs'][0]
                    self.assertEqual((recorded['stock']['batch_id'],recorded['stock']['unit'],recorded['production_id'],recorded['origin_item']),
                        (cooked['batch_id'],1,cooked['production_id'],'item/라즈열매'))
                    self.assertEqual(recorded['effect'],cooked['batch']['payload'])
                    self.assertEqual((made['batch']['berry_counts'],made['batch']['contest_stat']),({'라즈열매':1},'근사함'))
                    self.assertEqual(CHEF.batches(cook)[cooked['batch_id']]['count'],0)
                    self.reject(current,lambda:current.pokemon_activity(cook,'cook_poffins',**options),'insufficient actual Preserves units')
                    alternate=current.pokemon_activity(cook,'cook_poffins',**dict(options,preserves={other['batch_id']:1}))
                    self.assertEqual(cook.spec['cooking_materials_value'],0)
                    row=cook.spec['poffin_batches'][made['batch']['id']];original=deepcopy(row['preserves_inputs'])
                    row['preserves_inputs']=deepcopy(alternate['batch']['preserves_inputs'])
                    self.assertFalse(current.validate_state()['valid'])
                    with self.assertRaises(ValueError):FIX.restore(self.rules,current)
                    row['preserves_inputs']=original
                    current.pokemon_activity(cook,'feed_poffin',batch_id=row['id'],target=target,minutes=1,reason='native contest Poffin consumer')
                    self.assertEqual(target.spec['poffins'],['근사함'])
                    served=FIX.serve(current,cook,eaten['batch_id'],target)
                    self.assertEqual(CHEF.batches(cook)[eaten['batch_id']]['count'],0)
                    self.reject(current,lambda:current.pokemon_activity(cook,'cook_poffins',**dict(options,preserves={eaten['batch_id']:1})),'insufficient actual Preserves units')
                    target.hp=1;FIX.battle(current,target)
                    used=current.consume_food_buff(target,buff_id=served['buff_id'],action_kind='free',action_reason='GM actual ordinary composite trade-in')
                    self.assertEqual([part['kind'] for part in used['components']],['turn_heal'])
                    self.assertEqual((target.hp,target.spec['poffins']),(1,['근사함']))
                    self.assertEqual(FIX.receipt(target)['effect'],eaten['batch']['payload'])
                    self.assertEqual(len(target.spec['food_turn_healing']),1)
                    FIX.decline_all(current,cook)
                    current.end_of_turn(target);current.end_round();current.start_round(current.everyone)
                    current.start_of_turn(target,initiative_count=20)
                    self.assertEqual(target.hp,1+target.base_max_hp//16)
                    self.assertTrue(current.validate_state()['valid'])
                    restored,index=FIX.restore(self.rules,current)
                    self.assertEqual((CHEF.batches(index[cook.entity_id])[eaten['batch_id']]['count'],index[target.entity_id].spec['poffins']),(0,['근사함']))
                    self.assertTrue(restored.validate_state()['valid'])
                e.gm.restore(snapshot)
                self.assertTrue(all(CHEF.batches(chef)[made['batch_id']]['count']==1 for made in (eaten,cooked,other)))

    def test_tasty_snack_first_and_single_poffin_preserves_keep_native_food_and_physical_ingredient_effects(self):
        w=self.scene(csv=False,nature=FIX.nature_for(self.rules,'단맛','liked'))
        e,chef,p=w['engine'],w['chef'],w['partner']
        chef.spec['items'].update({'라즈열매':2,'포핀 혼합기':1})
        chef.spec['cooking_materials_value']=1000
        berries=[FIX.cook(e,chef,recipe='preserves',origin='item/라즈열매') for _ in range(2)]
        sweets=[FIX.cook(e,chef,recipe='tasty_snack',snack='item/단맛-과자') for _ in range(3)]
        self.reject(e,lambda:FIX.cook(e,chef,recipe='dumplings',ingredient_1={'batch_id':berries[0]['batch_id']},ingredient_2={'batch_id':sweets[0]['batch_id']}),'ingredient 2')
        def mix(sweet,berry):
            return FIX.cook(e,chef,recipe='dumplings',ingredient_1={'batch_id':sweet['batch_id']},ingredient_2={'batch_id':berry['batch_id']})
        eaten=mix(sweets[0],berries[0]);cooked=mix(sweets[1],berries[0]);other=mix(sweets[2],berries[1])
        self.assertEqual([part['effect']['kind'] for part in eaten['batch']['payload']['components']],['chef_snack','berry_ingredient'])
        self.assertEqual(eaten['batch']['dumplings_basis']['edition'],'book')
        snapshot=e.gm.snapshot('actual Tasty Snack first and single passive Berry ingredient')
        loaded,actors=FIX.restore(self.rules,e)
        for current,cook,target in ((e,chef,p),(loaded,actors[chef.entity_id],actors[p.entity_id])):
            options=dict(ingredients={},edition='core_en_1_05',minutes=1,reason='actual single Berry ingredient with native Chef Snack')
            made=current.pokemon_activity(cook,'cook_poffins',preserves={cooked['batch_id']:1},**options)
            alternate=current.pokemon_activity(cook,'cook_poffins',preserves={other['batch_id']:1},**options)
            recorded=made['batch']['preserves_inputs'][0]
            self.assertEqual((recorded['origin_item'],recorded['production_id'],recorded['stock']['unit']),('item/라즈열매',cooked['production_id'],1))
            self.assertEqual(recorded['effect'],cooked['batch']['payload'])
            self.assertEqual((made['batch']['berry_counts'],made['batch']['contest_stat']),({'라즈열매':1},'근사함'))
            self.assertEqual(cook.spec['cooking_materials_value'],0)
            row=cook.spec['poffin_batches'][made['batch']['id']];original=deepcopy(row['preserves_inputs'])
            row['preserves_inputs']=deepcopy(alternate['batch']['preserves_inputs'])
            self.assertFalse(current.validate_state()['valid'])
            with self.assertRaises(ValueError):FIX.restore(self.rules,current)
            row['preserves_inputs']=original
            current.pokemon_activity(cook,'feed_poffin',batch_id=row['id'],target=target,minutes=1,reason='actual native Poffin consumer')
            self.assertEqual(target.spec['poffins'],['근사함']);self.assertFalse(target.buffs)
            self.reject(current,lambda:current.pokemon_activity(cook,'cook_poffins',preserves={cooked['batch_id']:1},**options),'insufficient actual Preserves units')
            served=FIX.serve(current,cook,eaten['batch_id'],target)
            self.reject(current,lambda:current.pokemon_activity(cook,'cook_poffins',preserves={eaten['batch_id']:1},**options),'insufficient actual Preserves units')
            FIX.battle(current,target)
            baseline=target.evasion('물리',engine=current)
            with patch.object(__import__('combat_timing'),'install',side_effect=ValueError('late actual Sweet composite lifetime')):
                self.reject(current,lambda:current.consume_food_buff(target,buff_id=served['buff_id']),'late actual Sweet composite lifetime')
            used=current.consume_food_buff(target,buff_id=served['buff_id'])
            self.assertEqual((used['evasion'],used['accuracy'],used['composite']),(4,4,[]))
            self.assertEqual(FIX.receipt(target)['effect'],eaten['batch']['payload'])
            self.assertEqual((target.evasion('물리',engine=current),target.spec['poffins']),(baseline+4,['근사함']))
            FIX.decline_all(current,cook)
            current.end_of_turn(target);current.end_round();current.start_round(current.everyone)
            current.start_of_turn(target,initiative_count=20)
            self.assertEqual(target.evasion('물리',engine=current),baseline+4)
            current.end_of_turn(target)
            self.assertEqual(target.evasion('물리',engine=current),baseline)
            restored,index=FIX.restore(self.rules,current)
            self.assertEqual((CHEF.batches(index[cook.entity_id])[eaten['batch_id']]['count'],index[target.entity_id].spec['poffins']),(0,['근사함']))
            self.assertTrue(restored.validate_state()['valid'])
        e.gm.restore(snapshot)
        self.assertTrue(all(CHEF.batches(chef)[made['batch_id']]['count']==1 for made in (eaten,cooked,other)))

    def test_single_poffin_leaf_and_supported_preserves_keep_native_heal_setup_and_non_snack_medicine_consumers(self):
        for origin,kind in (('item/오랭열매','heal'),('item/파워풀허브','herb_skip_setup'),('item/힘의뿌리','native_consumable')):
            with self.subTest(origin=origin):
                w=self.scene(csv=False);e,chef,p,foe=w['engine'],w['chef'],w['partner'],w['foe']
                chef.spec['items'].update({'라즈열매':1,origin.split('/',1)[1]:1,'포핀 혼합기':1})
                chef.spec['cooking_materials_value']=500
                if kind=='herb_skip_setup':
                    e.gm.set_move(p,'move/솔라빔',reason='actual known Set-Up Move')
                    e.gm.observe_loyalty(p,6,reason='actual current owner before native Move')
                berry=FIX.cook(e,chef,recipe='preserves',origin='item/라즈열매')
                companion=FIX.cook(e,chef,recipe='preserves',origin=origin)
                eaten=FIX.cook(e,chef,recipe='dumplings',ingredient_1={'batch_id':berry['batch_id']},ingredient_2={'batch_id':companion['batch_id']})
                cooked=FIX.cook(e,chef,recipe='dumplings',ingredient_1={'batch_id':companion['batch_id']},ingredient_2={'batch_id':berry['batch_id']})
                self.assertEqual([part['effect']['kind'] for part in eaten['batch']['payload']['components']],['berry_ingredient',kind])
                # A second Poffin leaf or a nested parent is deliberately still
                # not assigned an invented ingredient ratio or exchange policy.
                chef.spec['items']['블리열매']=1
                extra=FIX.cook(e,chef,recipe='preserves',origin='item/블리열매')
                self.reject(e,lambda:FIX.cook(e,chef,recipe='dumplings',ingredient_1={'batch_id':eaten['batch_id']},ingredient_2={'batch_id':extra['batch_id']}),'Poffin Ingredient composite proportions')
                if kind=='heal':
                    for dual_role in ('item/위키열매','item/버치열매'):
                        chef.spec['items'][dual_role.split('/',1)[1]]=1
                        dual=FIX.cook(e,chef,recipe='preserves',origin=dual_role)
                        self.reject(e,lambda:FIX.cook(e,chef,recipe='dumplings',ingredient_1={'batch_id':extra['batch_id']},ingredient_2={'batch_id':dual['batch_id']}),'Poffin Ingredient composite proportions')
                snapshot=e.gm.snapshot('single passive Poffin leaf and actual native companion')
                loaded,actors=FIX.restore(self.rules,e)
                for current,cook,target,enemy in ((e,chef,p,foe),(loaded,actors[chef.entity_id],actors[p.entity_id],actors[foe.entity_id])):
                    options=dict(ingredients={},preserves={cooked['batch_id']:1},edition='core_en_1_05',minutes=1,reason='actual one Berry identity and native companion')
                    made=current.pokemon_activity(cook,'cook_poffins',**options)
                    recorded=made['batch']['preserves_inputs'][0]
                    self.assertEqual((recorded['origin_item'],recorded['production_id'],recorded['effect']),('item/라즈열매',cooked['production_id'],cooked['batch']['payload']))
                    self.assertEqual((made['batch']['berry_counts'],cook.spec['cooking_materials_value']),({'라즈열매':1},0))
                    self.reject(current,lambda:current.pokemon_activity(cook,'cook_poffins',**options),'insufficient actual Preserves units')
                    current.pokemon_activity(cook,'feed_poffin',batch_id=made['batch']['id'],target=target,minutes=1,reason='native Poffin has only its printed contest effect')
                    self.assertEqual(target.spec['poffins'],['근사함']);self.assertFalse(target.buffs)
                    served=FIX.serve(current,cook,eaten['batch_id'],target)
                    self.reject(current,lambda:current.pokemon_activity(cook,'cook_poffins',**dict(options,preserves={eaten['batch_id']:1})),'insufficient actual Preserves units')
                    target.hp=1;FIX.battle(current,target)
                    if kind=='herb_skip_setup':
                        selected=current.consume_food_buff(target,buff_id=served['buff_id'],move_id='move/솔라빔')
                        self.assertEqual(selected['status'],'prepared_for_actual_move')
                        with patch.object(Engine,'d20',return_value=15):
                            current.use_move_on(target,enemy,'move/솔라빔',current.everyone,set_damage=True)
                        self.assertIsNone(target.setup_move)
                        self.assertEqual(FIX.receipt(target)['benefit'],{'kind':'skip_setup','move_id':'move/솔라빔','composite':[]})
                        self.assertNotIn('food_move_choice',target.spec)
                        self.assertFalse(target.buffs)
                    else:
                        if kind=='heal':
                            with patch.object(Engine,'heal',side_effect=ValueError('late actual single native companion')):
                                self.reject(current,lambda:current.consume_food_buff(target,buff_id=served['buff_id'],action_kind='free',action_reason='actual native companion trade-in'),'late actual single native companion')
                        else:
                            native_herbal=FOOD.herbal_consumed;observed=[]
                            def fail_after_herbal(world,user,item):
                                native_herbal(world,user,item)
                                observed.append((user.hp,FOOD.herbal_state(user)['count']))
                                raise ValueError('late actual native herbal history')
                            # Item effect dispatch catches effect exceptions;
                            # use the actual later herbal-history owner, not an
                            # impossible exception escaping native heal dispatch.
                            with patch.object(FOOD,'herbal_consumed',side_effect=fail_after_herbal):
                                self.reject(current,lambda:current.consume_food_buff(target,buff_id=served['buff_id'],action_kind='free',action_reason='actual native companion trade-in'),'late actual native herbal history')
                            self.assertEqual(observed,[(min(target.max_hp,71),1)])
                        used=current.consume_food_buff(target,buff_id=served['buff_id'],action_kind='free',action_reason='actual native companion trade-in')
                        self.assertEqual([part['kind'] for part in used['components']],[kind])
                        if kind=='heal':
                            self.assertEqual(target.hp,min(target.max_hp,6));self.assertFalse(target.buffs)
                        else:
                            self.assertEqual(target.hp,min(target.max_hp,71))
                            self.assertEqual(FOOD.herbal_state(target)['count'],1)
                            self.assertTrue(target.buffs)
                            self.assertTrue(all(buff['source']==FOOD.MEDICINE for buff in target.buffs))
                    self.assertEqual(FIX.receipt(target)['effect'],eaten['batch']['payload'])
                    self.assertEqual(target.spec['poffins'],['근사함'])
                    FIX.decline_all(current,cook)
                    self.assertTrue(current.validate_state()['valid'])
                    restored,index=FIX.restore(self.rules,current)
                    self.assertEqual((CHEF.batches(index[cook.entity_id])[eaten['batch_id']]['count'],CHEF.batches(index[cook.entity_id])[cooked['batch_id']]['count']),(0,0))
                    self.assertTrue(restored.validate_state()['valid'])
                e.gm.restore(snapshot)
                self.assertEqual((CHEF.batches(chef)[eaten['batch_id']]['count'],CHEF.batches(chef)[cooked['batch_id']]['count']),(1,1))

    def test_reactive_berry_ignores_actual_miss_and_substitute_and_rolls_back_only_exchange_after_finalized_hit(self):
        import substitute as SUBSTITUTE
        w=self.scene();e,chef,p,foe=w['engine'],w['chef'],w['partner'],w['foe']
        chef.spec['items']['악키열매']=1
        made=FIX.cook(e,chef,recipe='preserves',origin='item/악키열매')
        served=FIX.serve(e,chef,made['batch_id'],p)
        e.gm.set_move(p,'move/대타출동',reason='actual learned native Substitute')
        e.gm.observe_loyalty(p,6,reason='actual own Pokemon observation')
        FIX.battle(e,p)
        e.use_move_on(p,p,'move/대타출동',e.everyone,set_damage=True)
        self.assertTrue(SUBSTITUTE.live(p))
        e.end_of_turn(p);e.start_of_turn(foe,initiative_count=10)
        e.consume_food_buff(p,buff_id=served['buff_id'])
        while SUBSTITUTE.live(p):
            e.resolve_attack_damage(foe,p,self.rules.move('move/몸통박치기'),set_damage=True)
            self.assertEqual(len(p.buffs),1)
        with patch.object(Engine,'d20',return_value=1):e.use_move_on(foe,p,'move/몸통박치기',e.everyone,set_damage=True)
        self.assertEqual(len(p.buffs),1)
        snapshot=e.gm.snapshot('actual hit will follow miss and Substitute')
        before_hp=p.hp;before_buff=deepcopy(p.buffs);before_choice=deepcopy(p.spec[FOOD.BERRY_HIT_CHOICE])
        with patch.object(Engine,'change_stage',side_effect=ValueError('late actual reactive native effect')):
            with self.assertRaisesRegex(ValueError,'late actual reactive native effect'):
                e.resolve_attack_damage(foe,p,self.rules.move('move/몸통박치기'),set_damage=True)
        # This owner is deliberately AFTER the actual hit: it retains that
        # native damage prefix, but never half-consumes the selected food.
        self.assertLess(p.hp,before_hp)
        self.assertEqual(p.buffs,before_buff)
        self.assertEqual(p.spec[FOOD.BERRY_HIT_CHOICE],before_choice)
        self.assertNotIn('food_consumption_receipts',p.spec)
        self.assertTrue(e.validate_state()['valid'])
        e.gm.restore(snapshot)
        e.resolve_attack_damage(foe,p,self.rules.move('move/몸통박치기'),set_damage=True)
        self.assertEqual(p.stages['def'],1)
        self.assertEqual(len(p.spec['food_consumption_receipts']),1)
        FIX.decline_all(e,chef)
        self.assertTrue(e.validate_state()['valid'])

    def test_enigma_uses_actual_post_resistance_and_selected_mettle_multiplier_not_raw_context(self):
        import test_mettle as METTLE
        w=self.scene();e,chef,p,foe=w['engine'],w['chef'],w['partner'],w['foe']
        chef.spec['items']['의문열매']=1
        made=FIX.cook(e,chef,recipe='preserves',origin='item/의문열매')
        served=FIX.serve(e,chef,made['batch_id'],p)
        e.gm.set_types(p,['풀'],reason='actual Fire weakness')
        e.gm.set_ability(p,'두꺼운지방',reason='actual native one-step Fire resistance')
        e.gm.set_move(foe,'move/불꽃세례',reason='actual known Fire attack')
        FIX.battle(e,foe);e.consume_food_buff(p,buff_id=served['buff_id'])
        observed=[];native=FOOD.berry_after_hit
        def observe(current,a,t,m,event,receipt):
            observed.append((event['context']['multiplier'],event.get('effective_type_multiplier',event['damage_formula']['multiplier'])))
            return native(current,a,t,m,event,receipt)
        with patch.object(FOOD,'berry_after_hit',observe),patch.object(Engine,'d20',return_value=15):
            e.use_move_on(foe,p,'move/불꽃세례',e.everyone,set_damage=True)
        self.assertEqual(observed,[(1.5,1.0)])
        self.assertIn(FOOD.BERRY_HIT_CHOICE,p.spec);self.assertEqual(len(p.buffs),1)
        self.assertNotIn('food_consumption_receipts',p.spec)
        FIX.decline_all(e,chef);self.assertTrue(e.validate_state()['valid'])
        helper=METTLE.MettleTests();helper.rules=self.rules
        __import__('synthetic_rule_fixture').register_synthetic(self.rules,'audit/mettle-source',name='깡다구 원문 검사 공격')
        e,foe,target,mid=helper.fixture(answer=True)
        # Direct finalized damage needs no legacy accuracy lambda; leave the
        # native Engine.d20 owner intact for actual JSON serialization.
        del e.d20
        # The legacy fixture isolates GM answers by copying only Engine.rulings.
        # Native JSON restoration requires both owners to share that object.
        previous_rulings=self.rules.rulings
        self.rules.rulings=e.rulings
        self.addCleanup(setattr,self.rules,'rulings',previous_rulings)
        # This existing synthetic attack fixture isolates the actual native
        # Mettle response; the added Berry is still actually crafted/served.
        self.rules.moves[mid]['type']='격투';self.rules.touch('moves')  # in-place rule edit declared
        e.gm.set_types(target,['노말'],reason='actual selected Fighting weakness')
        chef=self.add_chef(e,items={'의문열매':1})
        made=FIX.cook(e,chef,recipe='preserves',origin='item/의문열매')
        served=FIX.serve(e,chef,made['batch_id'],target)
        FIX.battle(e,foe);e.consume_food_buff(target,buff_id=served['buff_id'])
        observed=[]
        # Exercise the actual finalized-damage owner directly; this synthetic
        # fixture's old use_move convenience call did not reach it in raw20.
        with patch.object(FOOD,'berry_after_hit',observe):
            e.resolve_attack_damage(foe,target,self.rules.move(mid),set_damage=True)
        self.assertEqual(observed,[(1.5,1.0)])
        self.assertEqual(foe.stages['atk'],-2)
        self.assertIn(FOOD.BERRY_HIT_CHOICE,target.spec);self.assertEqual(len(target.buffs),1)
        loaded,actors=FIX.restore(self.rules,e)
        self.assertIn(FOOD.BERRY_HIT_CHOICE,actors[target.entity_id].spec)
        FIX.decline_all(loaded,actors[chef.entity_id]);self.assertTrue(loaded.validate_state()['valid'])

    def test_enigma_lean_pair_uses_each_final_native_multiplier_and_each_physical_unit_once(self):
        import test_book_rider_csv_full as RIDER
        import conquerors_march as CM
        for types,expected in ((['에스퍼'],1.0),(['에스퍼','고스트'],1.5)):
            with self.subTest(types=types):
                helper=RIDER.RiderFullTests();helper.rules=self.rules;helper.setUp()
                self.addCleanup(helper.tearDown)
                helper.setup(feature=CM.LEAN)
                e,a,p,foe=helper.e,helper.a,helper.p,helper.enemy
                chef=self.add_chef(e,items={'의문열매':1})
                made=FIX.cook(e,chef,recipe='preserves',origin='item/의문열매')
                for target in (a,p):
                    e.gm.set_types(target,types,reason='actual selected mounted pair weakness')
                    served=FIX.serve(e,chef,made['batch_id'],target)
                helper.answer('rider_lean_in',True);helper.combat(foe)
                for target in (a,p):e.consume_food_buff(target,buff_id=target.buffs[-1]['id'])
                snapshot=e.gm.snapshot('both actual Enigma units armed before paired Lean')
                seen=[];native=FOOD.berry_after_hit
                def observe(current,attacker,target,move,event,receipt):
                    seen.append((target.entity_id,event.get('effective_type_multiplier'),event['damage_formula']['multiplier']))
                    return native(current,attacker,target,move,event,receipt)
                with patch.object(FOOD,'berry_after_hit',observe):helper.area()
                self.assertEqual({row[0] for row in seen},{a.entity_id,p.entity_id})
                self.assertEqual([row[1:] for row in seen],[(expected,expected)]*2)
                for target in (a,p):
                    if expected>1:
                        self.assertEqual(len(target.spec['food_consumption_receipts']),1)
                        self.assertEqual(FIX.receipt(target)['benefit']['multiplier'],expected)
                    else:
                        self.assertEqual(len(target.buffs),1)
                        self.assertNotIn('food_consumption_receipts',target.spec)
                FIX.decline_all(e,chef);helper.valid()
                loaded,actors=FIX.restore(self.rules,e)
                self.assertEqual([len(actors[x.entity_id].buffs) for x in (a,p)],[0 if expected>1 else 1]*2)
                self.assertTrue(loaded.validate_state()['valid'])
                e.gm.restore(snapshot)
                self.assertTrue(all(FOOD.BERRY_HIT_CHOICE in x.spec for x in (a,p)))

    def test_counter_berry_native_incoming_receipt_and_attacker_ko_survive_composite_late_failure_without_half_exchange(self):
        import attack_damage_history as HISTORY
        w=self.scene();e,chef,p,foe=w['engine'],w['chef'],w['partner'],w['foe']
        chef.spec['items']['자보열매']=1
        berry=FIX.cook(e,chef,recipe='preserves',origin='item/자보열매')
        left=FIX.cook(e,chef,recipe='leftovers')
        mixed=FIX.cook(e,chef,recipe='dumplings',ingredient_1={'batch_id':berry['batch_id']},ingredient_2={'batch_id':left['batch_id']})
        served=FIX.serve(e,chef,mixed['batch_id'],p)
        e.gm.set_hp(foe,value=1,reason='actual foe can faint to printed counter HP loss')
        FIX.battle(e,foe);e.consume_food_buff(p,buff_id=served['buff_id'])
        snapshot=e.gm.snapshot('native incoming hit and counter composite')
        hp=p.hp;buff=deepcopy(p.buffs);choice=deepcopy(p.spec[FOOD.BERRY_HIT_CHOICE])
        import effect_instances as INSTANCES
        native_create=INSTANCES.create
        def fail_install(*args,**options):
            if options.get('kind')=='food_turn_healing':raise ValueError('late composite Leftovers native installation')
            return native_create(*args,**options)
        with patch.object(INSTANCES,'create',side_effect=fail_install):
            with self.assertRaisesRegex(ValueError,'late composite Leftovers native installation'):
                e.resolve_attack_damage(foe,p,self.rules.move('move/몸통박치기'),set_damage=True)
        self.assertLess(p.hp,hp)
        self.assertEqual((foe.hp,foe.fainted),(1,False))
        self.assertEqual((p.buffs,p.spec[FOOD.BERRY_HIT_CHOICE]),(buff,choice))
        self.assertNotIn('food_consumption_receipts',p.spec)
        self.assertTrue(e.validate_state()['valid'])
        e.gm.restore(snapshot)
        observed={};native_resolve=Engine.resolve_attack_damage
        def observe_hit(current,a,t,move,*args,**options):
            result=native_resolve(current,a,t,move,*args,**options)
            if t.entity_id==p.entity_id:observed.update(options['_damage_observation'])
            return result
        with patch.object(Engine,'resolve_attack_damage',observe_hit),patch.object(Engine,'d20',return_value=15):
            e.use_move_on(foe,p,'move/몸통박치기',e.everyone,set_damage=True)
        self.assertTrue(foe.fainted);self.assertLessEqual(foe.hp,0)
        used=FIX.receipt(p)['benefit']
        actual_receipt={key:value for key,value in observed.items() if key not in ('actual_damage_type','type_multiplier')}
        self.assertEqual(used['damage_receipt'],actual_receipt)
        self.assertEqual((used['actual_damage_type'],used['multiplier']),(observed['actual_damage_type'],observed['type_multiplier']))
        self.assertEqual(HISTORY.last_damage(p)['receipt'],{key:value for key,value in actual_receipt.items() if key!='native_damage'})
        self.assertEqual(used['damage_receipt']['requested'],HISTORY.last_damage(p)['receipt']['requested'])
        self.assertEqual(len(p.spec['food_consumption_receipts']),1)
        self.assertEqual(len(used['composite']),1)
        self.assertEqual(len(p.spec['food_turn_healing']),1)
        self.assertEqual(len(FIX.pending(e,chef,CHEF.HITS)),1)
        self.assertFalse(FIX.pending(e,chef,CHEF.AFTERTASTE))
        FIX.decline_all(e,chef)
        e.end_of_turn(foe);before=p.hp;e.start_of_turn(p,initiative_count=10)
        self.assertEqual(p.hp-before,min(p.base_max_hp//16,p.base_max_hp-before))
        FIX.decline_all(e,chef);self.assertTrue(e.validate_state()['valid'])

    def test_fixed_dragon_rage_uses_native_special_loss_class_without_inventing_effectiveness_and_keeps_exchange_atomic(self):
        import attack_damage_history as HISTORY
        for uid in ('item/타라프열매','item/애터열매','item/의문열매'):
            with self.subTest(item=uid):
                w=self.scene();e,chef,p,foe=w['engine'],w['chef'],w['partner'],w['foe']
                chef.spec['items'][uid]=1
                made=FIX.cook(e,chef,recipe='preserves',origin=uid)
                served=FIX.serve(e,chef,made['batch_id'],p)
                e.gm.set_types(p,['드래곤'],reason='actual type would be weak if an ordinary type multiplier applied')
                e.gm.set_move(foe,'move/용의분노',reason='actual known printed fixed15 special HP-loss Move')
                if uid=='item/애터열매':e.gm.set_hp(foe,value=1,reason='actual attacker may faint from Rowap HP loss')
                FIX.battle(e,foe);e.consume_food_buff(p,buff_id=served['buff_id'])
                snapshot=e.gm.snapshot('armed Berry before actual fixed HP-loss producer')
                if uid=='item/타라프열매':
                    hp=p.hp;buff=deepcopy(p.buffs);choice=deepcopy(p.spec[FOOD.BERRY_HIT_CHOICE])
                    with patch.object(Engine,'d20',return_value=15),patch.object(Engine,'change_stage',side_effect=ValueError('late fixed-loss Berry effect')) as failed:
                        e.use_move_on(foe,p,'move/용의분노',e.everyone,set_damage=True)
                    self.assertEqual(failed.call_count,1,'the actual fixed-loss hit must reach its class-only Berry')
                    held=[row for row in e._effect_dispatch_receipts.values() if row['status']=='execution_failed' and str(row.get('result'))=='late fixed-loss Berry effect']
                    self.assertEqual(len(held),1)
                    # The existing effect_loss transaction owns BOTH its HP
                    # loss and reaction; paid activation prefix is not undone.
                    self.assertEqual((p.hp,p.buffs,p.spec[FOOD.BERRY_HIT_CHOICE]),(hp,buff,choice))
                    self.assertFalse(HISTORY.records(p))
                    self.assertNotIn('food_consumption_receipts',p.spec)
                    e.gm.restore(snapshot)
                hp=p.hp
                with patch.object(Engine,'d20',return_value=15):e.use_move_on(foe,p,'move/용의분노',e.everyone,set_damage=True)
                self.assertEqual(hp-p.hp,15)
                self.assertEqual(HISTORY.last_damage(p)['application_kind'],'hp_loss')
                if uid=='item/의문열매':
                    # This native fixed15 producer has no effectiveness
                    # calculation. Absence is not defined to mean Neutral or
                    # resolved as a hypothetical printed-type SE calculation.
                    self.assertEqual(len(p.buffs),1)
                    self.assertIn(FOOD.BERRY_HIT_CHOICE,p.spec)
                    self.assertNotIn('food_consumption_receipts',p.spec)
                else:
                    used=FIX.receipt(p)['benefit']
                    self.assertIsNone(used['actual_damage_type']);self.assertIsNone(used['multiplier'])
                    self.assertEqual(used['damage_receipt']['requested'],15)
                    if uid=='item/타라프열매':self.assertEqual(p.stages['spd'],1)
                    else:self.assertTrue(foe.fainted)
                    self.assertEqual(len(p.spec['food_consumption_receipts']),1)
                FIX.decline_all(e,chef);self.assertTrue(e.validate_state()['valid'])
                loaded,actors=FIX.restore(self.rules,e)
                self.assertEqual(len(actors[p.entity_id].buffs),1 if uid=='item/의문열매' else 0)
                self.assertTrue(loaded.validate_state()['valid'])

    def test_pain_replacement_hp_loss_is_not_a_second_actual_move_hit_on_shared_recipient(self):
        from channeler_fixture import ChannelerScene
        import channeler as CHANNEL
        class ActualChannelerScene(ChannelerScene,unittest.TestCase):pass
        helper=ActualChannelerScene();helper.rules=self.rules;helper.setup()
        e=helper.e
        chef=self.add_chef(e,items={'악키열매':1})
        made=FIX.cook(e,chef,recipe='preserves',origin='item/악키열매')
        served=FIX.serve(e,chef,made['batch_id'],helper.q)
        helper.ready_pain()
        e.consume_food_buff(helper.q,buff_id=served['buff_id'])
        hp=helper.q.hp
        helper.damage()
        self.assertLess(helper.q.hp,hp)
        self.assertEqual(helper.q.stages['def'],0)
        self.assertIn(FOOD.BERRY_HIT_CHOICE,helper.q.spec)
        self.assertNotIn('food_consumption_receipts',helper.q.spec)
        self.assertEqual(len(helper.q.buffs),1)
        self.assertEqual(__import__('frequency').state(helper.a)['activations'][CHANNEL.PAIN]['used'],1)
        FIX.decline_all(e,chef);helper.valid()
        loaded,actors=FIX.restore(self.rules,e)
        self.assertIn(FOOD.BERRY_HIT_CHOICE,actors[helper.q.entity_id].spec)
        self.assertTrue(loaded.validate_state()['valid'])

    def test_distinct_reactive_preserves_reject_full_payloads_before_cooking_or_legacy_use_cost(self):
        for csv in (False, True):
            for first_id, second_id in (('item/자보열매', 'item/애터열매'), ('item/악키열매', 'item/타라프열매')):
                with self.subTest(csv=csv, first=first_id, second=second_id):
                    w = self.scene(csv=csv)
                    e, chef, p = w['engine'], w['chef'], w['partner']
                    for uid in (first_id, second_id):
                        chef.spec['items'][uid] = 1
                    first = FIX.cook(e, chef, recipe='preserves', origin=first_id)
                    second = FIX.cook(e, chef, recipe='preserves', origin=second_id)
                    options = dict(recipe='dumplings', ingredient_1={'batch_id': first['batch_id']}, ingredient_2={'batch_id': second['batch_id']})
                    self.reject(e, lambda: FIX.cook(e, chef, **options), 'two different trigger-bound.*GM trade-in policy')
                    self.assertEqual([CHEF.batches(chef)[row['batch_id']]['count'] for row in (first, second)], [2, 2])
                    # Recreate only sealed02's old admission decision; every
                    # acquisition, ingredient debit and served unit is native.
                    with patch.object(CHEF, 'trigger_component', side_effect=lambda buff: buff['effect']['components'][0]['effect']):
                        legacy = FIX.cook(e, chef, **options)
                    served = FIX.serve(e, chef, legacy['batch_id'], p)
                    FIX.battle(e, p)
                    self.reject(e, lambda: e.consume_food_buff(p, buff_id=served['buff_id']), 'two different trigger-bound.*GM trade-in policy')
                    self.assertEqual(len(p.spec.get('food_consumption_receipts', [])), 0)
                    self.assertEqual(len(p.buffs), 1)
                    self.assertNotIn(FOOD.BERRY_HIT_CHOICE, p.spec)

    def test_identical_reactive_nested_book_payloads_keep_supported_native_exchange(self):
        import arithmetic_policy as M
        w = self.scene(csv=False)
        e, chef, p, foe = w['engine'], w['chef'], w['partner'], w['foe']
        chef.spec['items']['자보열매'] = 1
        berry = FIX.cook(e, chef, recipe='preserves', origin='item/자보열매')
        left = FIX.cook(e, chef, recipe='leftovers')
        inner = FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': berry['batch_id']}, ingredient_2={'batch_id': left['batch_id']})
        outer = FIX.cook(e, chef, recipe='dumplings', ingredient_1={'batch_id': inner['batch_id']}, ingredient_2={'batch_id': berry['batch_id']})
        components = outer['batch']['payload']['components']
        self.assertEqual(components[0]['effect'], components[2]['effect'])
        self.assertEqual(CHEF.trigger_component({'effect': outer['batch']['payload']}), components[0]['effect'])
        served = FIX.serve(e, chef, outer['batch_id'], p)
        FIX.battle(e, foe)
        e.consume_food_buff(p, buff_id=served['buff_id'])
        hp = foe.hp
        e.resolve_attack_damage(foe, p, self.rules.move('move/몸통박치기'), set_damage=True)
        self.assertEqual(hp - foe.hp, M.ratio(foe.base_max_hp, 8))
        self.assertEqual(len(p.spec['food_turn_healing']), 1)
        self.assertEqual(len(p.spec['food_consumption_receipts']), 1)
        self.assertFalse(p.buffs)
        FIX.decline_all(e, chef)
        self.assertTrue(e.validate_state()['valid'])

    def test_salty_enigma_keeps_real_food_and_taste_contributions_fifo_expiry_and_both_restores(self):
        import temporary_hp as TEMP
        w = self.scene(csv=False, nature=FIX.nature_for(self.rules, '짠맛', 'liked'))
        e, chef, p, foe = w['engine'], w['chef'], w['partner'], w['foe']
        e.gm.set_stat(p, 'hp', value=10, reason='actual HP stat for the true maximum 60 Enigma boundary')
        self.assertEqual(p.base_max_hp, 60)
        e.gm.set_hp(p, value=p.base_max_hp, reason='conscious full-HP reactive Berry recipient')
        chef.spec['items']['의문열매'] = 1
        made = FIX.cook(e, chef, recipe='preserves', origin='item/의문열매', taste='짠맛')
        served = FIX.serve(e, chef, made['batch_id'], p)
        FIX.battle(e, foe)
        e.consume_food_buff(p, buff_id=served['buff_id'])
        with patch('effects_ext.effective_type', return_value='격투'):
            e.resolve_attack_damage(foe, p, self.rules.move('move/몸통박치기'), set_damage=True)
        receipt = FIX.receipt(p)
        self.assertEqual((receipt['benefit']['kind'], receipt['benefit']['amount'], receipt['benefit']['gained']), ('temporary_hp', 10, 10))
        self.assertEqual((receipt['taste_bonus']['gained'], p.temp_hp), (5, 15))
        rows = p.custom_conditions[TEMP.STATE]['contributions']
        self.assertEqual([(row['source']['kind'], row['amount']) for row in rows], [('chef_taste', 5), ('food', 10)])
        for row in rows:
            self.assertEqual((row['source']['receipt_sequence'], row['source']['buff_id']), (receipt['sequence'], served['buff_id']))
        self.assertEqual(rows[1]['source']['rule_id'], 'item/의문열매')
        self.assertEqual(rows[0]['source']['rule_id'], CHEF.ACCENTUATED)
        FIX.decline_all(e, chef)
        self.assertTrue(e.validate_state()['valid'])
        snapshot = e.gm.snapshot('salty Enigma retains both actual contribution rights')
        loaded, actors = FIX.restore(self.rules, e)
        for current, target in ((e, p), (loaded, actors[p.entity_id])):
            hp = target.hp
            current.take_damage(target, 3)
            self.assertEqual((target.temp_hp, target.hp), (12, hp))
            self.assertEqual([(row['source']['kind'], row['amount']) for row in target.custom_conditions[TEMP.STATE]['contributions']], [('chef_taste', 2), ('food', 10)])
            current.take_damage(target, 2)
            self.assertEqual(target.temp_hp, 10)
            self.assertEqual([row['source']['kind'] for row in target.custom_conditions[TEMP.STATE]['contributions']], ['food'])
            current.end_of_turn(current._active_turn_actor);current.end_round()
            self.assertTrue(current.encounter_active);self.assertIsNone(current.round_start_seconds)
            current.advance_time(900)  # Actual combat continues, with no open ten-second round.
            self.assertEqual(target.temp_hp, 10)
            current.end_encounter(current.everyone)
            current.advance_time(299)
            self.assertEqual(target.temp_hp, 10)
            current.advance_time(1)
            self.assertEqual(target.temp_hp, 0)
            self.assertNotIn(TEMP.STATE, target.custom_conditions)
            self.assertTrue(current.validate_state()['valid'])
        e.gm.restore(snapshot)
        self.assertEqual(p.temp_hp, 15)
        self.assertEqual([(row['source']['kind'], row['amount']) for row in p.custom_conditions[TEMP.STATE]['contributions']], [('chef_taste', 5), ('food', 10)])
        self.assertTrue(e.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
