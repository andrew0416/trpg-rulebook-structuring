"""Native event boundaries absent from the old helper-only CSV tests."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from engine import Engine
import csv_item_physical_contracts as PHYSICAL
import csv_item_food_contracts as CSVFOOD
import food_effects as FOOD
import items as ITEMS
import state_grants as GRANTS
import world_entities as WORLD
import csv_item_capability_contracts as CAP
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts


class CompletedCsvNativeRemaining(unittest.TestCase):
    setUpClass = classmethod(_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass.__func__)
    pokemon = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.pokemon
    trainer = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.trainer
    fixture = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.fixture
    equip = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.equip
    physical = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.physical

    def setUp(self):
        self.r.rulings.answers.clear()

    def attack(self, e, a, t, move):
        e.start_round([a, t]); e.start_of_turn(a, initiative_count=20)
        with patch.object(e, 'd20', return_value=20):
            e.use_move(a, t, move, set_damage=True)
        e.end_of_turn(a)

    def test_balloon_native_ground_immunity_hit_destruction_and_revoked_source(self):
        attacker = self.pokemon('balloon-attacker', moves=('move/진흙뿌리기','move/몸통박치기'))
        holder = self.pokemon('balloon-holder', types=('노말',))
        e = self.fixture(attacker, holder)
        obj = self.equip(e, holder, 'csv/native-balloon', 'item/풍선')
        hp = holder.hp
        self.attack(e, attacker, holder, 'move/진흙뿌리기')
        self.assertEqual(holder.hp, hp)
        # Source says "attack hits", so an accurate immune attack also pops it.
        self.assertIn('destroyed', obj)
        self.assertNotIn('부유', GRANTS.effective(holder, 'abilities'))
        hp = holder.hp
        self.attack(e, attacker, holder, 'move/진흙뿌리기')
        self.assertLess(holder.hp, hp)
        restored = Engine.import_state(self.r, json.loads(json.dumps(e.export_state())))
        self.assertIn('destroyed', restored._physical_objects['csv/native-balloon'])

    def test_vest_native_cure_rejection_after_unequip_and_actual_encounter_end(self):
        actor = self.pokemon('vest-native')
        target = self.pokemon('vest-opponent')
        e = self.fixture(actor, target)
        e.start_round([actor, target])
        before_spd = actor.stats['spd']
        self.equip(e, actor, 'csv/native-vest', 'item/돌격조끼')
        self.assertEqual(actor.stats['spd'], before_spd + 5)
        ITEMS.unregister_item(e, actor, 'item/돌격조끼')
        self.assertEqual(actor.stats['spd'], before_spd)
        with self.assertRaisesRegex(ValueError, 'cannot be cured'):
            e.cure_status(actor, '난동')
        self.assertIn('난동', actor.conditions)
        e.end_encounter([actor, target])
        self.assertNotIn('난동', actor.conditions)
        e.export_state()

    def test_eject_button_actual_hit_pending_consumed_switch_without_turn_cost(self):
        attacker = self.pokemon('button-attacker')
        holder = self.pokemon('button-holder')
        replacement = self.pokemon('button-replacement')
        replacement.on_field = False
        e = self.fixture(attacker, holder, replacement)
        replacement.on_field = False
        obj = self.equip(e, holder, 'csv/native-button', 'item/탈출버튼')
        self.attack(e, attacker, holder, 'move/몸통박치기')
        self.assertEqual(holder.spec[PHYSICAL.PENDING]['eject_button']['event']['attacker_id'], attacker.entity_id)
        budget = deepcopy(getattr(holder, 'budget', None))
        restored = Engine.import_state(self.r, json.loads(json.dumps(e.export_state())))
        index = WORLD.actor_index(restored)
        actual, incoming = index[holder.entity_id], index[replacement.entity_id]
        result = PHYSICAL.resolve_pending(restored, actual, 'eject_button', send=incoming)
        self.assertTrue(result['switched'])
        self.assertFalse(actual.on_field)
        self.assertTrue(incoming.on_field)
        self.assertEqual(getattr(actual, 'budget', None), budget)
        self.assertIn('consumed', restored._physical_objects[obj['id']])
        with self.assertRaisesRegex(ValueError, 'actual live'):
            PHYSICAL.resolve_pending(restored, actual, 'eject_button', send=incoming)

    def test_sweet_neutral_and_disliked_native_food_choices(self):
        for disposition, amount, rampage in (('neutral',1,False),('disliked',1,True)):
            with self.subTest(disposition=disposition):
                actor = self.pokemon('sweet-' + disposition, items={'item/단맛-과자':1})
                natures = self.r.mech('pokemon/natures')['by_name']
                actor.spec['nature'] = next(name for name,row in natures.items() if
                    (row['up']==row['down'] if disposition=='neutral' else
                     row.get('dislikes','').replace(' ','')=='단맛' and row['up']!=row['down']))
                e = self.fixture(actor)
                intake = e.use_item(actor,'item/단맛-과자',food_policy='C2CSV/inventory:91:7',
                    duration_minutes=1,duration_reason='actual selected homebrew intake')
                e.start_round([actor]); e.start_of_turn(actor,initiative_count=20)
                result=e.consume_food_buff(actor,buff_id=intake['buff_id'])
                self.assertEqual(result['evasion'],amount)
                self.assertEqual('난동' in actor.conditions,rampage)
                self.assertEqual(FOOD.slots(actor),0)
                self.assertEqual(len(actor.spec['food_consumption_receipts']),1)

    def test_weakness_policy_native_trigger_and_damage_consumer_share_lifetime(self):
        fire = self.pokemon('policy-fire', moves=('move/불꽃세례',))
        holder = self.pokemon('policy-holder',types=('풀',))
        target = self.trainer('policy-native-target')
        e=self.fixture(fire,holder,target)
        self.equip(e,holder,'csv/native-policy','item/약점보험')
        e.start_round([fire,holder,target]);e.start_of_turn(fire,initiative_count=20)
        with patch.object(e,'d20',return_value=15):
            e.use_move(fire,holder,'move/불꽃세례',set_damage=True)
        e.end_of_turn(fire)
        pending=holder.spec[PHYSICAL.PENDING]['weakness_policy']
        self.assertEqual(pending['event']['attacker_id'],fire.entity_id)
        PHYSICAL.resolve_pending(e,holder,'weakness_policy')
        for active in (True,False):
            if not active:
                e.end_encounter([fire,holder,target])
            e.start_round([holder,target]);e.start_of_turn(holder,initiative_count=20)
            before=target.hp
            with patch.object(e,'d20',return_value=15):
                e.use_move(holder,target,'move/몸통박치기',set_damage=True)
            if active: boosted=before-target.hp
            else: ordinary=before-target.hp
            e.end_of_turn(holder)
        self.assertEqual(boosted-ordinary,10)

    def test_scavenger_real_daily_stock_and_restored_receipt_require_live_source(self):
        actor=self.pokemon('scavenger-native',capabilities=('청소부',))
        e=self.fixture(actor)
        result=e.scavenge(actor,fixed_d20=20,during='extended_rest', duration_minutes=240,
            duration_reason='actual uninterrupted four-hour rest',rest_id='scavenger-rest')
        self.assertEqual((result['category'],result['item_id']),('tm',None))
        CAP.resolve_scavenge_reward(e,actor,day=result['day'],item_id='TM1',reason='GM selected the actual TM')
        self.assertEqual(actor.spec['items']['TM1'],1)
        restored=Engine.import_state(self.r,json.loads(json.dumps(e.export_state())))
        actual=WORLD.actor_index(restored)[actor.entity_id]
        before=deepcopy(actual.spec)
        with self.assertRaisesRegex(ValueError,'daily use'):
            CAP.scavenge(restored,actual,fixed_d20=20)
        self.assertEqual(actual.spec,before)
        actual.spec['capabilities']=[]
        with self.assertRaisesRegex(ValueError,'actual capability'):
            CAP.scavenge(restored,actual,fixed_d20=20)

    def test_pokemon_only_held_sources_reject_trainer_registration(self):
        for item in ('item/풍선','item/돌격조끼','item/약점보험','item/탈출버튼'):
            with self.subTest(item=item):
                actor=self.trainer('wrong-kind-'+item)
                e=self.fixture(actor)
                uid='csv/wrong-kind-'+item
                obj=self.physical(e,actor,uid,item)
                try:
                    result=ITEMS.register_item(e,actor,item,source_instance_id=uid,as_held=True)
                except ValueError as error:
                    self.assertIn('Pokemon-only',str(error))
                else:
                    self.assertEqual(result,0)  # core no-effect return is also a denied use
                self.assertIsNone(obj.get('equipped_by'))
                self.assertNotIn(PHYSICAL.OBJECT_STATE,obj)

