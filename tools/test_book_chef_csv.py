"""Only Chef CSV differences and formerly missing recipe-to-native connections."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Combatant
from builder import build_pokemon
from native_scenario_fixture import assert_rejected_unchanged
import book_chef_fixture as FIX
import chef_cooking as CHEF
import food_effects as FOOD
import combat_timing as TIMING
import state_codec as CODEC
import trainer_feature_acquisition as ACQUIRE
import wild_equipment as WILD


class ChefCsvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)

    def scene(self, *, csv=True, nature=None, feats=FIX.ALL_FEATURES):
        world = FIX.scene(self.rules, feats=(), pokemon_nature=nature)
        for uid in feats:
            ACQUIRE.acquire_static(world['engine'], world['chef'], uid,
                acquisition_request_id='csv-chef/' + uid,
                selection={'edition': 'local_csv'} if csv and uid in (CHEF.ACCENTUATED, CHEF.DUMPLINGS) else None)
        __import__('items').register_feats(world['engine'], world['chef'])
        return world

    def reject(self, engine, operation, pattern):
        return assert_rejected_unchanged(engine, operation, reason_pattern=pattern)

    def aftertaste(self, engine, chef):
        offer = FIX.pending(engine, chef, CHEF.AFTERTASTE)[0]
        result = engine.resolve_class_actor_state_action(chef, offer['id'], use=True)
        FIX.decline_all(engine, chef)
        return result['buff_id']

    def salty(self, engine, partner, foe, buff_id):
        engine.consume_food_buff(partner, buff_id=buff_id)
        engine.roll_damage(foe, partner, engine.r.move('move/몸통박치기'), set_damage=True)
        return FIX.receipt(partner)

    def test_csv_selection_is_explicit_historical_replay_safe_and_source_bound(self):
        w = self.scene(feats=(CHEF.CLASS,))
        e, chef = w['engine'], w['chef']
        self.reject(e, lambda: ACQUIRE.acquire_static(e, chef, CHEF.ACCENTUATED,
            acquisition_request_id='bad', selection={'edition': 'invented'}), 'exact local_csv')
        row = ACQUIRE.acquire_static(e, chef, CHEF.ACCENTUATED, acquisition_request_id='taste', selection={'edition': 'local_csv'})
        self.assertEqual(row['snapshot']['source'], CHEF.csv_taste_source(self.rules))
        self.assertEqual(ACQUIRE.acquire_static(e, chef, CHEF.ACCENTUATED, acquisition_request_id='taste', selection={'edition': 'local_csv'})['request_id'], 'taste')
        self.reject(e, lambda: ACQUIRE.acquire_static(e, chef, CHEF.ACCENTUATED, acquisition_request_id='taste'), 'replay')
        self.reject(e, lambda: ACQUIRE.acquire_static(e, chef, CHEF.HITS, acquisition_request_id='bad-other', selection={'edition': 'local_csv'}), 'optional acquisition')
        with patch.dict(CHEF.CSV_SOURCE, sha256='0' * 64):
            with self.assertRaisesRegex(ValueError, 'source|changed|hash'):
                CHEF.csv_taste_source(self.rules)
        loaded, actors = FIX.restore(self.rules, e)
        self.assertEqual(CHEF._acquisitions(actors[chef.entity_id], CHEF.ACCENTUATED)[0]['snapshot']['source'], row['snapshot']['source'])
        self.assertTrue(loaded.validate_state()['valid'])

    def test_csv_sweet_bonus_once_per_physical_item_across_recursive_aftertaste_and_both_restores(self):
        w = self.scene()
        e, chef, p = w['engine'], w['chef'], w['partner']
        FIX.ruling(e, 'scene_end')
        first = FIX.cook(e, chef, recipe='tasty_snack', snack='단맛 과자')
        second = FIX.cook(e, chef, recipe='tasty_snack', snack='단맛 과자')
        served = FIX.serve(e, chef, first['batch_id'], p)
        FIX.battle(e, p)
        e.consume_food_buff(p, buff_id=served['buff_id'])
        self.assertEqual(FIX.receipt(p)['taste_bonus']['kind'], 'initiative')
        follow = self.aftertaste(e, chef)
        e.gm.snapshot('aftertaste')
        loaded, actors = FIX.restore(self.rules, e)
        restored, owner = actors[p.entity_id], actors[chef.entity_id]
        loaded.rulings.answers = [a for a in loaded.rulings.answers if a['key'] != CHEF.RULING]
        self.assertEqual(loaded.consume_food_buff(restored, buff_id=follow)['evasion'], 4)
        self.assertNotIn('taste_bonus', FIX.receipt(restored))
        follow2 = self.aftertaste(loaded, owner)
        loaded.consume_food_buff(restored, buff_id=follow2)
        self.assertNotIn('taste_bonus', FIX.receipt(restored))
        self.assertEqual(len([r for r in TIMING.records(restored) if r.get(CHEF.BONUS)]), 1)
        self.assertTrue(loaded.validate_state()['valid'])
        e.gm.restore('aftertaste', reason='actual snapshot replay boundary')
        e.consume_food_buff(p, buff_id=follow)
        self.assertNotIn('taste_bonus', FIX.receipt(p))
        FIX.decline_all(e, chef)
        e.end_encounter()
        fresh = FIX.serve(e, chef, second['batch_id'], p)
        FIX.ruling(e, 'scene_end')
        FIX.battle(e, p)
        e.consume_food_buff(p, buff_id=fresh['buff_id'])
        self.assertEqual(FIX.receipt(p)['taste_bonus']['kind'], 'initiative')
        self.assertTrue(e.validate_state()['valid'])

    def test_csv_salty_actual_attack_suppresses_only_repeat_bonus_not_snack_or_aftertaste(self):
        w = self.scene(nature=FIX.nature_for(self.rules, '짠맛', 'liked'))
        e, chef, p, foe = w['engine'], w['chef'], w['partner'], w['foe']
        served = FIX.serve(e, chef, FIX.cook(e, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')['batch_id'], p)
        FIX.battle(e, foe)
        first = self.salty(e, p, foe, served['buff_id'])
        self.assertEqual((first['benefit']['amount'], first['taste_bonus']['value']), (10, 5))
        follow = self.aftertaste(e, chef)
        e.take_damage(p, p.temp_hp)
        self.assertEqual(p.temp_hp, 0)
        again = self.salty(e, p, foe, follow)
        self.assertEqual(again['benefit']['amount'], 10)
        self.assertNotIn('taste_bonus', again)
        self.assertEqual(len(FIX.pending(e, chef, CHEF.AFTERTASTE)), 1)
        self.assertTrue(e.validate_state()['valid'])
        payload = json.loads(json.dumps(CODEC.dump_engine(e), ensure_ascii=False))
        # The live actor's own serialized receipt chain is validated on every restore.
        again['chef_provenance']['origin_receipt_sequence'] = again['sequence']
        self.assertFalse(e.validate_state()['valid'])
        again['chef_provenance']['origin_receipt_sequence'] = first['sequence']
        self.assertTrue(e.validate_state()['valid'])
        self.assertTrue(CODEC.load_engine(self.rules, payload).validate_state()['valid'])

    def test_vitamins_and_suppressants_craft_real_inventory_at_printed_prices_and_use_native_doses(self):
        w = self.scene()
        e, chef, p = w['engine'], w['chef'], w['partner']
        chef.spec['money'] = 20000
        stats = deepcopy(p.spec['stats'])
        row = CHEF.definitions(self.rules)['recipes'][CHEF.VITAMINS]
        for item in row['vitamins']:
            result = FIX.cook(e, chef, recipe='vitamin', item=item)
            self.assertEqual((result['item_id'], result['money_spent'], chef.spec['items'][item]), (item, 2450, 1))
            e.use_item(chef, item, p)
            self.assertEqual(chef.spec['items'][item], 0)
        self.assertEqual(len(p.spec['vitamins']), 6)
        for stat in stats:
            self.assertEqual(p.spec['stats'][stat], stats[stat] + 1)
        self.assertEqual(row['suppressants'], ['item/억제제'])
        result = FIX.cook(e, chef, recipe='vitamin', item='item/억제제')
        self.assertEqual((result['chef_recipe'], result['money_spent']), (CHEF.VITAMINS, 200))
        self.assertEqual(e.use_item(chef, 'item/억제제', p, selected_stat='atk', owner_consent_by=chef), (1, 0))
        self.assertEqual(len(p.spec['vitamins']), 7)
        self.assertEqual(p.spec['stats']['atk'], stats['atk'])
        FIX.cook(e, chef, recipe='vitamin', item='item/억제제')
        before = deepcopy(p.spec)
        self.assertEqual(e.use_item(chef, 'item/억제제', p, selected_stat='def', owner_consent_by=chef), (0, 0))
        self.assertEqual(p.spec, before)
        self.assertEqual(chef.spec['items']['item/억제제'], 0)
        self.assertEqual(chef.spec['money'], 20000 - 6 * 2450 - 2 * 200)
        self.reject(e, lambda: FIX.cook(e, chef, recipe='vitamin', item='item/하트-부스터'), 'ordinary Vitamin')
        self.assertTrue(e.validate_state()['valid'])
        self.assertTrue(FIX.restore(self.rules, e)[0].validate_state()['valid'])

    def wild(self, e):
        actor = Combatant(self.rules, build_pokemon(self.rules, '이브이', 20, name='actual wild', moves=['move/몸통박치기'], abilities=[], extra={'wild': True, 'skills': {'집중': 1}}))
        e.gm.add_combatant(actor, pos=(2, 1), side='wild', reason='actual encountered wild Pokemon')
        return actor

    def test_bait_money_honey_and_super_bonus_use_actual_batch_stock_and_restore(self):
        w = self.scene()
        e, chef = w['engine'], w['chef']
        chef.spec['items']['꿀'] = 2
        regular = FIX.cook(e, chef, recipe='bait')
        super_bait = FIX.cook(e, chef, recipe='bait', variant='super', honey=True)
        vile = FIX.cook(e, chef, recipe='bait', variant='vile', honey=True)
        self.assertEqual((regular['money_spent'], super_bait['money_spent'], vile['money_spent'], chef.spec['items']['꿀']), (150, 50, 50, 0))
        habitat = {'region': 'actual meadow', 'species': ['이브이'], 'reason': 'GM-observed local species'}
        e.pokemon_activity(chef, 'attract_bait', phase='place', bait_id='regular', chef_batch_id=regular['batch_id'], habitat=habitat)
        self.reject(e, lambda: e.pokemon_activity(chef, 'attract_bait', phase='wait', bait_id='regular', fixed=9, use_intuition=True), 'Super Bait')
        e.pokemon_activity(chef, 'attract_bait', phase='place', bait_id='super', chef_batch_id=super_bait['batch_id'], habitat=habitat)
        result = e.pokemon_activity(chef, 'attract_bait', phase='wait', bait_id='super', fixed=9, use_intuition=True)
        self.assertEqual((result['checks'][-1]['bonus'], result['checks'][-1]['total'], result['status']), (6, 15, 'awaiting_encounter'))
        self.reject(e, lambda: e.pokemon_activity(chef, 'attract_bait', phase='place', bait_id='free-copy', chef_batch_id=super_bait['batch_id'], habitat=habitat), 'exhausted')
        self.assertTrue(FIX.restore(self.rules, e)[0].validate_state()['valid'])
        chef.spec['placed_bait']['super']['chef_bait']['variant'] = 'vile'
        self.assertFalse(e.validate_state()['valid'])
        chef.spec['placed_bait']['super']['chef_bait']['variant'] = 'super'
        self.assertTrue(e.validate_state()['valid'])

    def test_vile_bait_native_next_standard_eating_poison_not_at_distraction(self):
        w = self.scene()
        e, chef, p = w['engine'], w['chef'], w['partner']
        bait = FIX.cook(e, chef, recipe='bait', variant='vile')
        wild = self.wild(e)
        FIX.battle(e, chef)
        e.pokemon_activity(chef, 'distract_bait', target=wild, chef_batch_id=bait['batch_id'], fixed=[1])
        self.assertTrue(WILD.pending(wild))
        self.assertNotIn('독', wild.conditions)
        e.end_of_turn(chef)
        e.start_of_turn(wild)
        before = (e.rng.getstate(), p.hp, dict(wild.move_uses))
        self.assertEqual(e.use_move(wild, p, 'move/몸통박치기', set_damage=True), 0)
        self.assertEqual(before, (e.rng.getstate(), p.hp, dict(wild.move_uses)))
        self.assertIn('독', wild.conditions)
        self.assertEqual((wild.budget['standard'], wild.spec['bait_distraction']['status']), (0, 'eaten'))
        self.assertTrue(e.validate_state()['valid'])

    def test_placed_vile_bait_requires_actual_selected_encounter_then_eating_once(self):
        w = self.scene()
        e, chef, p = w['engine'], w['chef'], w['partner']
        bait = FIX.cook(e, chef, recipe='bait', variant='vile')
        wild = self.wild(e)
        e.pokemon_activity(chef, 'attract_bait', phase='place', bait_id='actual-vile', chef_batch_id=bait['batch_id'],
            habitat={'region': 'actual meadow', 'species': ['이브이'], 'reason': 'GM observed species'})
        self.reject(e, lambda: e.pokemon_activity(chef, 'attract_bait', phase='eat', bait_id='actual-vile', target=wild), 'actual encountered')
        e.pokemon_activity(chef, 'attract_bait', phase='wait', bait_id='actual-vile', fixed=15)
        e.pokemon_activity(chef, 'attract_bait', phase='select', bait_id='actual-vile')
        e.pokemon_activity(chef, 'attract_bait', phase='encounter', bait_id='actual-vile', target=wild, party=[p], level_match_reason='actual level20 party and wild')
        self.assertNotIn('독', wild.conditions)
        self.reject(e, lambda: e.pokemon_activity(chef, 'attract_bait', phase='eat', bait_id='actual-vile', target=w['foe']), 'actual encountered')
        e.pokemon_activity(chef, 'attract_bait', phase='eat', bait_id='actual-vile', target=wild)
        self.assertIn('독', wild.conditions)
        self.reject(e, lambda: e.pokemon_activity(chef, 'attract_bait', phase='eat', bait_id='actual-vile', target=wild), 'actual encountered')
        duplicate = deepcopy(chef.spec['placed_bait']['actual-vile'])
        chef.spec['placed_bait']['forged-copy'] = duplicate
        self.assertFalse(e.validate_state()['valid'])
        del chef.spec['placed_bait']['forged-copy']
        self.assertTrue(FIX.restore(self.rules, e)[0].validate_state()['valid'])

    def test_missing_recipe_provider_tool_money_honey_and_late_failure_preserve_state(self):
        w = self.scene(feats=(CHEF.CLASS,))
        e, chef = w['engine'], w['chef']
        self.reject(e, lambda: FIX.cook(e, chef, recipe='bait'), 'acquired Chef recipe')
        self.reject(e, lambda: FIX.cook(e, chef, recipe='vitamin', item='item/타우린'), 'acquired Chef recipe')
        FIX.acquire(e, chef, CHEF.APPRECIATION)
        self.reject(e, lambda: FIX.cook(e, chef, recipe='bait', honey=True), 'ingredient')
        chef.spec['money'] = 0
        self.reject(e, lambda: FIX.cook(e, chef, recipe='bait'), 'money|material|cost')
        chef.spec['money'] = 500
        with patch.object(CHEF, '_store_batch', side_effect=ValueError('late Chef batch failure')):
            self.reject(e, lambda: FIX.cook(e, chef, recipe='bait'), 'late Chef batch failure')
        kit = chef.spec['items'].pop('요리 세트')
        self.reject(e, lambda: FIX.cook(e, chef, recipe='bait'), 'equipment|tool')
        chef.spec['items']['요리 세트'] = kit
        self.assertTrue(e.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
