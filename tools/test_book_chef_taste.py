"""Hits the Spot, Accentuated Taste bonuses and Complex Aftertaste on actual Digestion Buff trade-ins."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from native_scenario_fixture import assert_rejected_unchanged
import book_chef_fixture as FIX
import action_points as AP
import chef_cooking as CHEF
import class_actor_state_actions as CLASS_ACTIONS
import combat_timing as TIMING
import common_checks as C
import effect_lifetimes as LIFETIMES
import food_effects as FOOD
import state_codec as CODEC
import temporary_hp as TEMP_HP
import trainer_feature_acquisition as ACQUIRE


class ChefTasteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        FOOD.buff_policy(self.rules)
        CLASS_ACTIONS.policy(self.rules)
        CHEF.definitions(self.rules)

    def rejected(self, engine, operation, pattern):
        return assert_rejected_unchanged(engine, operation, reason_pattern=pattern)

    def trade_in(self, engine, consumer, buff_id, attacker=None, target=None, move='move/몸통박치기'):
        """Arm the Chef Snack and trade it in through its printed attack/received-attack/self consumer."""
        buff = FOOD.get_buff(consumer, buff_id)
        payload = FOOD._chef_payload(buff)
        prep = engine.consume_food_buff(consumer, buff_id=buff_id)
        if isinstance(prep, C.PendingDecision):
            return prep
        if payload['trigger'] == 'self_activation':
            return prep
        if payload.get('attack_class') == '특수':
            move = 'move/파괴광선'
        engine.roll_damage(attacker, target, self.rules.move(move), set_damage=True)
        return FIX.receipt(consumer)

    def test_salty_bonus_stacks_with_the_digestion_buff_hits_the_spot_and_lunchbox(self):
        world = FIX.scene(self.rules, pokemon_nature=FIX.nature_for(self.rules, '짠맛', 'liked'), abilities=['도시락통 [Playtest]'])
        engine, chef, partner, foe = world['engine'], world['chef'], world['partner'], world['foe']
        salty = FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')
        served = FIX.serve(engine, chef, salty['batch_id'], partner)
        FIX.battle(engine, foe)
        receipt = self.trade_in(engine, partner, served['buff_id'], attacker=foe, target=partner)
        self.assertEqual((receipt['benefit']['amount'], receipt['benefit']['gained']), (10, 10))
        self.assertEqual(receipt['taste_bonus'], {'kind': 'temporary_hp', 'taste': '짠맛', 'disposition': 'liked', 'value': 5, 'gained': 5, 'stack': True})
        self.assertEqual(partner.temp_hp, 15)
        events = partner.custom_conditions[TEMP_HP.STATE]['grant_events']
        self.assertEqual([(row['amount'], row['stack'], row['provenance']['source']) for row in events], [(10, False, 'item/짠맛-서프라이즈'), (5, True, CHEF.ACCENTUATED)])
        hits = FIX.pending(engine, chef, CHEF.HITS)[0]
        self.assertEqual(hits['payload']['receipt_sequence'], receipt['sequence'])
        result = engine.resolve_class_actor_state_action(chef, hits['id'], use=True)
        self.assertEqual((result['intuition_rank'], result['temporary_hp_granted'], partner.temp_hp, chef.spec['ap_spent']), (6, 12, 27, 1))
        FIX.decline_all(engine, chef)
        self.assertTrue(engine.validate_state()['valid'])
        loaded, actors = FIX.restore(self.rules, engine)
        self.assertEqual(actors[partner.entity_id].temp_hp, 27)
        self.assertTrue(loaded.validate_state()['valid'])

    def test_leftovers_with_assigned_taste_stack_salty_hits_the_spot_and_lunchbox_on_the_pokemon_turn(self):
        world = FIX.scene(self.rules, pokemon_nature=FIX.nature_for(self.rules, '짠맛', 'liked'), abilities=['도시락통 [Playtest]'])
        engine, chef, partner = world['engine'], world['chef'], world['partner']
        left = FIX.cook(engine, chef, recipe='leftovers', taste='짠맛')
        served = FIX.serve(engine, chef, left['batch_id'], partner)
        FIX.battle(engine, partner)
        result = engine.consume_food_buff(partner, buff_id=served['buff_id'], action_kind='free', action_reason='actual Leftovers trade-in')
        self.assertEqual(result['until'], 'encounter_end')
        receipt = FIX.receipt(partner)
        self.assertEqual((receipt['taste_bonus']['gained'], partner.temp_hp), (5, 5))
        engine.resolve_class_actor_state_action(chef, FIX.pending(engine, chef, CHEF.HITS)[0]['id'], use=True)
        self.assertEqual(partner.temp_hp, 17)
        FIX.decline_all(engine, chef)
        lunch = engine.activate_ability(partner, '도시락통 [Playtest]', (partner, {'receipt_sequence': receipt['sequence']}))
        self.assertEqual((lunch['details']['temporary_hp'], partner.temp_hp), (engine.tick(partner), 17 + engine.tick(partner)))
        self.assertEqual([row['provenance'].get('source') for row in partner.custom_conditions[TEMP_HP.STATE]['grant_events']],
                         [CHEF.ACCENTUATED, CLASS_ACTIONS.THATS_THE_TASTE, 'ability/도시락통-playtest'])
        self.assertTrue(engine.validate_state()['valid'])

    def test_spicy_sour_dry_bitter_sweet_bonuses_reach_native_consumers_under_the_gm_lifetime_ruling(self):
        move = self.rules.move('move/몸통박치기')
        for snack, taste, boundary in (('매운맛 랩', '매운맛', 'encounter_end'), ('신맛 캔디', '신맛', 'scene_end'), ('떫은맛 웨이퍼', '떫은맛', 'encounter_end'),
                                       ('쓴맛 트리트', '쓴맛', 'scene_end'), ('단맛 과자', '단맛', 'encounter_end')):
            with self.subTest(snack=snack):
                self.rules.rulings.answers = [row for row in self.rules.rulings.answers if row['key'] != CHEF.RULING]
                world = FIX.scene(self.rules, seed=11, pokemon_nature=FIX.nature_for(self.rules, taste, 'liked'))
                engine, chef, partner, foe = world['engine'], world['chef'], world['partner'], world['foe']
                served = FIX.serve(engine, chef, FIX.cook(engine, chef, recipe='tasty_snack', snack=snack)['batch_id'], partner)
                payload = FOOD.get_buff(partner, served['buff_id'])['effect']
                FIX.battle(engine, partner if payload['trigger'] != 'received_attack' else foe)
                before = engine.export_state()
                self.assertIsInstance(engine.consume_food_buff(partner, buff_id=served['buff_id']), C.PendingDecision)
                self.assertEqual(engine.export_state(), before)
                FIX.ruling(engine, boundary)
                initiative, evasion, status_evasion, saves, effect = (engine.initiative_value(partner).value, partner.evasion('물리', engine=engine),
                                                                      partner.evasion('변화', engine=engine), LIFETIMES.numeric(partner, 'save_modifier'), CHEF.effect_range_bonus(engine, partner, move))
                attacker, target = (partner, foe) if payload['trigger'] == 'attack' else (foe, partner)
                self.trade_in(engine, partner, served['buff_id'], attacker=attacker, target=target)
                bonus = FIX.receipt(partner)['taste_bonus']
                expected = CHEF.definitions(self.rules)['taste_bonuses'][taste]
                self.assertEqual((bonus['kind'], bonus['value'], bonus['lifetime_boundary'], bonus['disposition']), (expected['kind'], expected['value'], boundary, 'liked'))
                records = [row for row in TIMING.records(partner) if row.get(CHEF.BONUS)]
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0][CHEF.BONUS]['receipt_sequence'], FIX.receipt(partner)['sequence'])
                after = {'initiative': engine.initiative_value(partner).value - initiative, 'evasion': partner.evasion('물리', engine=engine) - evasion,
                         'status_evasion': partner.evasion('변화', engine=engine) - status_evasion, 'saves': LIFETIMES.numeric(partner, 'save_modifier') - saves,
                         'effect': CHEF.effect_range_bonus(engine, partner, move) - effect, 'critical': CHEF.critical_bonus(engine, partner, move)}
                sweet_timed = 4 if taste == '단맛' else 0
                self.assertEqual(after, {'initiative': 5 if taste == '단맛' else 0, 'evasion': (1 if taste == '신맛' else 0) + sweet_timed,
                                         'status_evasion': sweet_timed, 'saves': 1 if taste == '쓴맛' else 0, 'effect': 1 if taste == '떫은맛' else 0,
                                         'critical': 1 if taste == '매운맛' else 0})
                self.assertEqual(CHEF.critical_bonus(engine, partner, self.rules.move('move/파괴광선')), 1 if taste == '매운맛' else 0)
                self.assertTrue(engine.validate_state()['valid'], engine.validate_state()['issues'])
                loaded, actors = FIX.restore(self.rules, engine)
                restored = actors[partner.entity_id]
                self.assertEqual(len([row for row in TIMING.records(restored) if row.get(CHEF.BONUS)]), 1)
                self.assertTrue(loaded.validate_state()['valid'])
                FIX.decline_all(engine, chef)
                engine.end_encounter()
                remaining = [row for row in TIMING.records(partner) if row.get(CHEF.BONUS)]
                self.assertEqual(len(remaining), 0 if boundary == 'encounter_end' else 1)
                engine.end_scene()
                self.assertEqual([row for row in TIMING.records(partner) if row.get(CHEF.BONUS)], [])
                self.assertEqual(CHEF.initiative_bonus(partner) + CHEF.critical_bonus(engine, partner, move) + CHEF.evasion_bonus(partner, '물리'), 0)

    def test_bonus_needs_a_pokemon_consumer_an_assigned_taste_and_a_taste_it_does_not_dislike(self):
        world = FIX.scene(self.rules, pokemon_nature=FIX.nature_for(self.rules, '짠맛', 'disliked'), ally=True)
        engine, chef, partner, companion, foe = world['engine'], world['chef'], world['partner'], world['companion'], world['foe']
        salty = FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')
        served = FIX.serve(engine, chef, salty['batch_id'], partner)
        FIX.battle(engine, foe)
        receipt = self.trade_in(engine, partner, served['buff_id'], attacker=foe, target=partner)
        self.assertEqual((receipt.get('taste_bonus'), receipt['benefit']['rampage_applied'], partner.temp_hp), (None, True, 5))
        self.assertIn('난동', partner.conditions)
        self.assertEqual([row['source'] for row in FIX.pending(engine, chef)], [CHEF.HITS, CHEF.AFTERTASTE])
        FIX.decline_all(engine, chef)
        engine.end_encounter()
        # A trainer trading in the same tasted Snack gets no Pokemon bonus; the tasted trade-in still offers Complex Aftertaste.
        served = FIX.serve(engine, chef, FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')['batch_id'], chef)
        FIX.battle(engine, foe)
        receipt = self.trade_in(engine, chef, served['buff_id'], attacker=foe, target=chef)
        self.assertEqual((receipt.get('taste_bonus'), chef.temp_hp), (None, 5))
        self.assertEqual([row['source'] for row in FIX.pending(engine, chef)], [CHEF.HITS, CHEF.AFTERTASTE])
        FIX.decline_all(engine, chef)
        engine.end_encounter()
        # An ordinary inventory Tasty Snack carries no assigned Taste: no bonus, no Complex Aftertaste offer.
        chef.spec['items']['item/매운맛-랩'] = 1
        plain = engine.use_item(chef, 'item/매운맛-랩', companion, duration_minutes=1, duration_reason='purchased snack intake')
        self.assertNotIn('taste_assignment', FOOD.get_buff(companion, plain['buff_id']))
        FIX.battle(engine, companion)
        receipt = self.trade_in(engine, companion, plain['buff_id'], attacker=companion, target=foe)
        self.assertIsNone(receipt.get('taste_bonus'))
        self.assertEqual(FIX.pending(engine, chef), [])
        self.assertTrue(engine.validate_state()['valid'])

    def test_hits_the_spot_book_clause_reacts_to_self_and_own_pokemon_trade_ins_for_one_ap(self):
        world = FIX.scene(self.rules, feats=(CHEF.CLASS, CHEF.HITS), ally=True)
        engine, chef, partner, companion, foe = world['engine'], world['chef'], world['partner'], world['companion'], world['foe']
        chef.spec['items']['초코바'] = 3
        own = engine.use_item(chef, '초코바', partner, duration_minutes=1, duration_reason='actual meal')
        mine = engine.use_item(chef, '초코바', chef, duration_minutes=1, duration_reason='actual meal')
        other = engine.use_item(chef, '초코바', companion, duration_minutes=1, duration_reason='actual meal')
        FIX.battle(engine, partner)
        engine.consume_food_buff(partner, buff_id=own['buff_id'], action_kind='free', action_reason='own Pokemon trade-in')
        offer = FIX.pending(engine, chef, CHEF.HITS)[0]
        self.assertEqual((offer['target_id'], offer['clause_id']), (partner.entity_id, 'C2CSV/input/db/feats.csv:R302:main'))
        # A pending offer blocks further actions until accepted or declined.
        self.rejected(engine, lambda: engine.consume_food_buff(chef, buff_id=mine['buff_id'], action_kind='free', action_reason='blocked'), 'accepted or declined')
        chef.spec['ap_spent'] = AP.maximum(chef)
        self.rejected(engine, lambda: engine.resolve_class_actor_state_action(chef, offer['id'], use=True), 'insufficient')
        chef.spec['ap_spent'] = 0
        first = engine.resolve_class_actor_state_action(chef, offer['id'], use=True)
        # Another actor's free action outside its own turn is not spent: no trade-in, no offer.
        self.assertFalse(engine.consume_food_buff(chef, buff_id=mine['buff_id'], action_kind='free', action_reason='not my turn'))
        self.assertEqual(FIX.pending(engine, chef), [])
        engine.end_of_turn(partner)
        engine.start_of_turn(chef, initiative_count=15)
        engine.consume_food_buff(chef, buff_id=mine['buff_id'], action_kind='free', action_reason='own trade-in')
        offer = FIX.pending(engine, chef, CHEF.HITS)[0]
        self.assertEqual(offer['target_id'], chef.entity_id)
        second = engine.resolve_class_actor_state_action(chef, offer['id'], use=True)
        self.assertEqual((first['temporary_hp_granted'], partner.temp_hp, second['temporary_hp_granted'], chef.temp_hp, chef.spec['ap_spent']), (12, 12, 12, 12, 2))
        engine.end_of_turn(chef)
        engine.start_of_turn(companion, initiative_count=10)
        engine.consume_food_buff(companion, buff_id=other['buff_id'], action_kind='free', action_reason='allied Pokemon trade-in')
        self.assertEqual((FIX.pending(engine, chef), FIX.pending(engine, world['ally'])), ([], []))
        self.assertTrue(engine.validate_state()['valid'])

    def test_complex_aftertaste_offers_to_self_and_allies_and_grants_the_matching_basic_snack_buff_for_one_ap(self):
        world = FIX.scene(self.rules, ally=True)
        engine, chef, partner, ally, companion, foe = (world['engine'], world['chef'], world['partner'], world['ally'], world['companion'], world['foe'])
        for uid in (CHEF.CLASS, CHEF.ACCENTUATED, CHEF.AFTERTASTE):
            FIX.acquire(engine, ally, uid)
        FIX.ruling(engine, 'encounter_end')
        sweet = FIX.cook(engine, chef, recipe='tasty_snack', snack='단맛 과자')
        served = FIX.serve(engine, chef, sweet['batch_id'], companion)
        FIX.battle(engine, companion)
        result = engine.consume_food_buff(companion, buff_id=served['buff_id'])
        self.assertEqual((result['evasion'], result['accuracy']), (4, 0))
        receipt = FIX.receipt(companion)
        self.assertEqual(receipt['taste_bonus']['kind'], 'initiative')
        self.assertEqual([row['source'] for row in FIX.pending(engine, chef)], [CHEF.AFTERTASTE])
        self.assertEqual([row['source'] for row in FIX.pending(engine, ally)], [CHEF.AFTERTASTE])
        offer = FIX.pending(engine, ally, CHEF.AFTERTASTE)[0]
        self.assertEqual((offer['clause_id'], offer['target_id'], offer['payload']['taste'], offer['trigger']), ('input/ch04-trainer-classes.md:1910-1914', companion.entity_id, '단맛', 'tasted_digestion_buff_consumed'))
        ally.spec['ap_spent'] = AP.maximum(ally)
        self.rejected(engine, lambda: engine.resolve_class_actor_state_action(ally, offer['id'], use=True), 'insufficient')
        ally.spec['ap_spent'] = 0
        granted = engine.resolve_class_actor_state_action(ally, offer['id'], use=True)
        self.assertEqual((granted['item'], granted['taste'], granted['ap_spent'], ally.spec['ap_spent']), ('item/단맛-과자', '단맛', 1, 1))
        buff = FOOD.get_buff(companion, granted['buff_id'])
        self.assertEqual(buff['effect'], FOOD.chef_effect(self.rules, 'item/단맛-과자'))
        self.assertEqual(buff['taste_assignment']['basis'], 'complex_aftertaste')
        self.assertEqual(buff['chef_provenance'], {'source': CHEF.AFTERTASTE, 'event_id': offer['id'], 'owner_id': ally.entity_id, 'origin_receipt_sequence': receipt['sequence'], 'origin_item': 'item/단맛-과자'})
        self.assertNotIn('item_stock', buff)
        # The chef's own identical offer now finds the ordinary slot occupied: atomic refusal.
        mine = FIX.pending(engine, chef, CHEF.AFTERTASTE)[0]
        self.rejected(engine, lambda: engine.resolve_class_actor_state_action(chef, mine['id'], use=True), 'cannot gain another Digestion Buff')
        self.assertEqual(engine.resolve_class_actor_state_action(chef, mine['id'], use=False), {'used': False})
        # Original text, no errata: the granted tasted buff repeats the Accentuated bonus and reopens Complex Aftertaste.
        again = engine.consume_food_buff(companion, buff_id=granted['buff_id'])
        self.assertEqual(again['evasion'], 4)
        self.assertEqual(FIX.receipt(companion)['taste_bonus']['kind'], 'initiative')
        self.assertEqual(len([row for row in TIMING.records(companion) if row.get(CHEF.BONUS)]), 2)
        self.assertEqual([row['source'] for row in FIX.pending(engine, ally)], [CHEF.AFTERTASTE])
        loaded, actors = FIX.restore(self.rules, engine)
        self.assertEqual([row['source'] for row in loaded.pending_class_actor_state_actions(actors[ally.entity_id])], [CHEF.AFTERTASTE])
        self.assertTrue(loaded.validate_state()['valid'])
        FIX.decline_all(engine, chef, ally)
        engine.end_encounter()
        # An opposing Pokemon is not an ally: its tasted trade-in offers nothing.
        served = FIX.serve(engine, chef, FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')['batch_id'], foe)
        FIX.battle(engine, partner)
        engine.consume_food_buff(foe, buff_id=served['buff_id'])
        engine.roll_damage(partner, foe, self.rules.move('move/몸통박치기'), set_damage=True)
        self.assertEqual(FIX.receipt(foe)['taste_bonus']['kind'], 'temporary_hp')
        self.assertEqual((FIX.pending(engine, chef), FIX.pending(engine, ally)), ([], []))
        self.assertTrue(engine.validate_state()['valid'])

    def test_restores_keep_batches_tastes_bonus_records_and_pending_offers_and_reject_tampering(self):
        world = FIX.scene(self.rules, pokemon_nature=FIX.nature_for(self.rules, '쓴맛', 'liked'))
        engine, chef, partner, foe = world['engine'], world['chef'], world['partner'], world['foe']
        FIX.ruling(engine, 'scene_end')
        bitter = FIX.cook(engine, chef, recipe='tasty_snack', snack='쓴맛 트리트')
        engine.gm.snapshot('cooked')
        served = FIX.serve(engine, chef, bitter['batch_id'], partner)
        FIX.battle(engine, foe)
        self.trade_in(engine, partner, served['buff_id'], attacker=foe, target=partner)
        self.assertEqual(LIFETIMES.numeric(partner, 'save_modifier'), 1)
        loaded, actors = FIX.restore(self.rules, engine)
        restored, restored_chef = actors[partner.entity_id], actors[chef.entity_id]
        self.assertEqual(LIFETIMES.numeric(restored, 'save_modifier'), 1)
        self.assertEqual(restored_chef.spec['chef_batches'][bitter['batch_id']]['count'], 0)
        self.assertEqual([row['source'] for row in loaded.pending_class_actor_state_actions(restored_chef)], [CHEF.HITS, CHEF.AFTERTASTE])
        self.assertEqual(loaded.resolve_class_actor_state_action(restored_chef, loaded.pending_class_actor_state_actions(restored_chef)[0]['id'], use=True)['temporary_hp_granted'], 12)
        self.assertTrue(loaded.validate_state()['valid'])
        record = next(row for row in TIMING.records(partner) if row.get(CHEF.BONUS))
        original = record['save_modifier']
        record['save_modifier'] = 3
        self.assertFalse(engine.validate_state()['valid'])
        record['save_modifier'] = original
        self.assertTrue(engine.validate_state()['valid'])
        FIX.receipt(partner)['taste_assignment']['taste'] = '단맛'
        self.assertFalse(engine.validate_state()['valid'])
        engine.gm.restore('cooked', reason='rewind to the cooked batch')
        self.assertEqual((chef.spec['chef_batches'][bitter['batch_id']]['count'], partner.buffs, TIMING.records(partner)), (1, [], []))
        self.assertTrue(engine.validate_state()['valid'])
        FIX.serve(engine, chef, bitter['batch_id'], partner)
        buff = partner.buffs[0]
        buff['taste_assignment']['taste'] = '단맛'
        self.assertFalse(engine.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
