"""Q32 distinct core lesson and actual Food exchange/refreshment consumers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
import ability_transitions as ABILITIES
import book_chef_fixture as FIX
import chef_cooking as CHEF
import consumption_execution as STOCK_RECEIPTS
import csv_item_food_contracts as CSV
import effect_instances as INSTANCES
import food_effects as FOOD
import frequency as FREQ
import state_codec as CODEC
import state_grants as GRANTS
import world_entities as WORLD
import test_csv_food_legacy_reconciliation as LEGACY_FIXTURE


class GluttonyCoreSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = Rules(ROOT, ruleset='core')

    def world(self, *, taught=True, ally=False, honey=False):
        abilities = () if taught else ('ability/먹보',)
        if honey:
            abilities += ('ability/꿀파기',)
        world = FIX.scene(self.core, feats=(CHEF.CLASS, CHEF.APPRECIATION), abilities=abilities, ally=ally)
        pupil = world['partner']
        pupil.spec.setdefault('items', {}).update({'초코바': 9, '꿀': 2, '맛있는물': 6})
        FOOD.buff_policy(self.core)
        __import__('feature_ability_lessons')._policy(self.core)
        return world

    def lesson(self, world, **changes):
        options = {'target': world['partner'], 'feature': CHEF.APPRECIATION,
                   'ability': FOOD.CORE_GLUTTONY, 'seconds': 45,
                   'reason': 'actual GM-observed Extended core Gluttony lesson'}
        options.update(changes)
        return world['engine'].pokemon_activity(world['chef'], 'teach_feature_ability', **options)

    def state(self, e, actor):
        return deepcopy((CODEC.dump_engine(e), e.rng.getstate()))

    def feed(self, e, actor, item='초코바'):
        return e.use_item(actor, item, duration_minutes=1,
                          duration_reason='actual one-minute completed intake')

    def eat(self, e, actor, buff_id):
        return e.consume_food_buff(actor, buff_id=buff_id, action_kind='free',
                                   action_reason='GM observed this actual Food exchange as a Free Action')

    def restore(self, e, actor):
        loaded = Engine.import_state(Rules(ROOT, ruleset='core'), json.loads(json.dumps(e.export_state())))
        return loaded, WORLD.actor_index(loaded)[actor.entity_id]

    def test_actual_core_lesson_pays_once_preserves_failed_work_and_stores_more_than_three(self):
        world = self.world(ally=True)
        e, pupil = world['engine'], world['partner']
        old_buff = self.feed(e, pupil)['buff_id']
        self.eat(e, pupil, old_buff)
        del pupil.spec['food_consumption_receipts'][0][FOOD.ENCOUNTER_RECEIPT]
        old = deepcopy(pupil.spec['food_consumption_receipts'][0])
        started = e.elapsed_seconds
        for changes, pattern in (({'target': world['companion']}, 'different trainer'),
                                 ({'ability': 'ability/먹보-playtest'}, 'Excluded rule selection')):
            before = self.state(e, pupil)
            with self.assertRaisesRegex(ValueError, pattern):
                self.lesson(world, **changes)
            self.assertEqual(self.state(e, pupil), before)
        pupil.spec['tutor_points'] = 1
        before = self.state(e, pupil)
        with self.assertRaisesRegex(ValueError, 'two actual Tutor Points'):
            self.lesson(world)
        self.assertEqual(self.state(e, pupil), before)
        pupil.spec['tutor_points'] = 5
        real = FOOD.core_lesson_boundary
        def fail_after_actual_boundary(*args, **kwargs):
            real(*args, **kwargs)
            raise ValueError('actual completed lesson boundary late failure')
        before = self.state(e, pupil)
        with patch.object(FOOD, 'core_lesson_boundary', side_effect=fail_after_actual_boundary):
            with self.assertRaisesRegex(ValueError, 'late failure'):
                self.lesson(world)
        self.assertEqual(self.state(e, pupil), before)
        result = self.lesson(world)
        self.assertEqual((result['ability'], result['point_cost'], e.elapsed_seconds, pupil.spec['tutor_points']),
                         (FOOD.CORE_GLUTTONY, 2, started + 45, 3))
        self.assertEqual(ABILITIES.known(pupil), [FOOD.CORE_GLUTTONY])
        source = pupil.spec[GRANTS.KEY]['sources'][result['payment']['sources'][0]]
        self.assertEqual(source['ability_lesson']['ability_id'], FOOD.CORE_GLUTTONY)
        self.assertEqual(e.activity_job_status(result['job_id'])['status'], 'complete')
        self.assertIsNone(FOOD.buff_capacity(e, pupil))
        receipts = [self.feed(e, pupil) for _ in range(5)]
        self.assertEqual((FOOD.slots(pupil), pupil.spec['items']['초코바']), (5, 3))
        self.assertEqual(pupil.spec['food_consumption_receipts'], [old])
        self.assertEqual(len({row['buff_id'] for row in receipts}), 5)
        before = self.state(e, pupil)
        with self.assertRaisesRegex(ValueError, 'already has the printed Ability'):
            self.lesson(world)
        self.assertEqual(self.state(e, pupil), before)
        e.start_round(e.everyone)
        e.start_of_turn(pupil, initiative_count=20)
        self.eat(e, pupil, receipts[0]['buff_id'])
        self.assertEqual(pupil.spec['food_consumption_receipts'][0], old)
        self.assertNotIn(FOOD.CORE_OBSERVATION, pupil.spec)
        self.assertTrue(e.validate_state()['valid'])

    def test_three_actual_exchanges_follow_real_encounter_not_frequency_scene_or_intake(self):
        world = self.world()
        e, pupil = world['engine'], world['partner']
        self.lesson(world)
        buffs = [self.feed(e, pupil)['buff_id'] for _ in range(5)]
        e.start_round(e.everyone)
        e.start_of_turn(pupil, initiative_count=20)
        epoch = e._party_encounter_epoch
        e.lose_hp(pupil, 25, source='actual pre-exchange HP loss')
        hp = pupil.hp
        for buff_id in buffs[:2]:
            self.eat(e, pupil, buff_id)
        scene = FREQ.state(pupil)['scene']
        FREQ.end_scene(e, pupil)
        self.assertEqual((FREQ.state(pupil)['scene'], e._party_encounter_epoch, e.encounter_active),
                         (scene + 1, epoch, True))
        self.eat(e, pupil, buffs[2])
        self.assertEqual(pupil.hp, hp + 15)
        before = self.state(e, pupil)
        with self.assertRaisesRegex(ValueError, 'encounter Digestion Buff quota'):
            self.eat(e, pupil, buffs[3])
        self.assertEqual(self.state(e, pupil), before)
        history = deepcopy(pupil.spec['food_consumption_receipts'])
        self.assertEqual([row[FOOD.ENCOUNTER_RECEIPT]['encounter_epoch'] for row in history], [epoch] * 3)
        e.gm.snapshot('core-three-exchanges')
        e.end_encounter(e.everyone, round_elapsed_seconds=0)
        e.gm.restore('core-three-exchanges', reason='actual core quota rewind')
        e, pupil = self.restore(e, pupil)
        before = self.state(e, pupil)
        with self.assertRaisesRegex(ValueError, 'encounter Digestion Buff quota'):
            self.eat(e, pupil, buffs[3])
        self.assertEqual(self.state(e, pupil), before)
        e.end_scene(e.everyone, round_elapsed_seconds=0)
        self.assertFalse(e.encounter_active)
        e.start_round(e.everyone)
        e.start_of_turn(pupil, initiative_count=20)
        self.assertGreater(e._party_encounter_epoch, epoch)
        self.eat(e, pupil, buffs[3])
        self.assertEqual(pupil.spec['food_consumption_receipts'][:3], history)
        self.assertEqual(pupil.spec['food_consumption_receipts'][-1][FOOD.ENCOUNTER_RECEIPT]['encounter_epoch'], e._party_encounter_epoch)
        self.assertTrue(e.validate_state()['valid'])

    def test_suppression_and_source_return_cannot_refill_known_quota_or_erase_exempt_food(self):
        world = self.world(taught=False, honey=True)
        e, pupil = world['engine'], world['partner']
        buffs = [self.feed(e, pupil)['buff_id'] for _ in range(5)]
        honey = self.feed(e, pupil, '꿀')['buff_id']
        self.assertEqual(FOOD.get_buff(pupil, honey)[INSTANCES.KEY]['capacity']['bucket'], 'source_exempt')
        e.start_round(e.everyone)
        e.start_of_turn(pupil, initiative_count=20)
        for buff_id in buffs[:3]:
            self.eat(e, pupil, buff_id)
        self.eat(e, pupil, honey)
        self.assertFalse(pupil.spec['food_consumption_receipts'][-1][FOOD.ENCOUNTER_RECEIPT]['eligible'])
        pupil.abilities_suppressed = True
        self.eat(e, pupil, buffs[3])
        pupil.abilities_suppressed = False
        e.gm.set_ability(pupil, FOOD.CORE_GLUTTONY, add=False, reason='actual current core source loss')
        history = deepcopy(pupil.spec['food_consumption_receipts'])
        e.gm.set_ability(pupil, FOOD.CORE_GLUTTONY, reason='actual same core source return')
        e, pupil = self.restore(e, pupil)
        self.assertEqual(pupil.spec['food_consumption_receipts'], history)
        before = self.state(e, pupil)
        with self.assertRaisesRegex(ValueError, 'encounter Digestion Buff quota'):
            self.eat(e, pupil, buffs[4])
        self.assertEqual(self.state(e, pupil), before)
        with self.assertRaisesRegex(ValueError, 'cannot refill'):
            e.observe_core_gluttony_quota(pupil, used=3, reason='must not conceal four known actual exchanges')
        self.assertEqual(self.state(e, pupil), before)
        self.assertEqual(len(history), 5)
        self.assertTrue(e.validate_state()['valid'])

    def test_core_refreshments_use_two_real_stock_consumptions_per_1800_seconds(self):
        world = self.world()
        e, pupil = world['engine'], world['partner']
        self.lesson(world)
        self.feed(e, pupil, '맛있는물')
        self.feed(e, pupil, '맛있는물')
        e, pupil = self.restore(e, pupil)
        before = self.state(e, pupil)
        with self.assertRaisesRegex(ValueError, 'drink intake limit'):
            self.feed(e, pupil, '맛있는물')
        self.assertEqual(self.state(e, pupil), before)
        e.advance_time(1679, [pupil])
        before = self.state(e, pupil)
        with self.assertRaisesRegex(ValueError, 'drink intake limit'):
            self.feed(e, pupil, '맛있는물')
        self.assertEqual(self.state(e, pupil), before)
        e.advance_time(1, [pupil])
        self.feed(e, pupil, '맛있는물')
        self.assertEqual((pupil.spec['items']['맛있는물'], len(pupil.spec['drink_history'])), (3, 3))
        pupil.abilities_suppressed = True
        before = self.state(e, pupil)
        with self.assertRaisesRegex(ValueError, 'drink intake limit'):
            self.feed(e, pupil, '맛있는물')
        self.assertEqual(self.state(e, pupil), before)
        pupil.abilities_suppressed = False
        self.assertTrue(e.validate_state()['valid'])

    def test_core_unlimited_storage_reconciles_real_paid_legacy_csv_food_then_uses_native_effect(self):
        world = self.world()
        e, pupil = world['engine'], world['partner']
        self.lesson(world)
        for _ in range(5):
            self.feed(e, pupil)
        pupil.spec['items']['item/흉내허브'] = 1
        # Reuse the SHA-bound frozen D14 producer, including its real stock/payment alias graph.
        old = LEGACY_FIXTURE.OLD.consume(e, pupil, pupil, 'item/흉내허브')
        self.assertEqual((FOOD.slots(pupil), pupil.spec['items']['item/흉내허브']), (6, 0))
        observed = deepcopy(pupil.spec[CSV.STATE])
        paid_count = len(STOCK_RECEIPTS.validate(pupil))
        created = e.elapsed_seconds
        e.advance_time(90, [pupil])
        e, pupil = self.restore(e, pupil)
        current = e.elapsed_seconds
        result = e.consume_food_buff(pupil, buff_id=old['id'],
            legacy_reason='GM verified the actual original paid CSV Mirror Herb source and ownership')
        self.assertEqual((result['observed_creation_at'], result['adopted_at']), (created, current))
        self.assertEqual((e.elapsed_seconds, pupil.spec['items']['item/흉내허브'], FOOD.slots(pupil)),
                         (current, 0, 6))
        self.assertFalse(pupil.spec[CSV.STATE]['buffs'])
        self.assertEqual(pupil.spec[CSV.STATE]['receipts'][:1], observed['receipts'])
        self.assertEqual(pupil.spec[CSV.STATE]['receipts'][-1]['observation'], observed['buffs'][0])
        adopted = FOOD.get_buff(pupil, result['buff_id'])
        self.assertEqual(adopted[CSV.SELECTION]['clause_id'], 'C2CSV/inventory:232:10')
        self.assertEqual(adopted['csv_legacy_origin']['legacy_buff_id'], old['id'])
        payments = STOCK_RECEIPTS.validate(pupil)
        self.assertEqual(len(payments), paid_count)
        original = next(row for row in payments.values() if row['item_stock'] is adopted['item_stock'])
        self.assertEqual((original['outcome'], original['target_id'], original['results']),
                         ('applied', pupil.entity_id, [{'kind': 'digestion_buff', 'id': adopted['id']}]))
        source = WORLD.actor_index(e)[world['foe'].entity_id]
        e.rulings.add_answer('mirror_herb', True, reason='actual holder selects this native positive stage event')
        e.change_stage(source, 'atk', 2)
        self.assertEqual((pupil.stages['atk'], FOOD.slots(pupil)), (2, 5))
        receipt = pupil.spec['food_consumption_receipts'][-1]
        self.assertEqual((receipt['buff_id'], receipt['benefit']['source_actor_id'], receipt['benefit']['delta']),
                         (adopted['id'], source.entity_id, 2))
        self.assertTrue(e.validate_state()['valid'])

    def test_unstamped_legacy_exchanges_need_current_observation_without_rewriting_history(self):
        world = self.world()
        e, pupil = world['engine'], world['partner']
        self.lesson(world)
        buffs = [self.feed(e, pupil)['buff_id'] for _ in range(5)]
        e.start_round(e.everyone)
        e.start_of_turn(pupil, initiative_count=20)
        self.eat(e, pupil, buffs[0])
        # The exact old receipt had no encounter field; do not fabricate one on restore.
        del pupil.spec['food_consumption_receipts'][0][FOOD.ENCOUNTER_RECEIPT]
        old = deepcopy(pupil.spec['food_consumption_receipts'][0])
        e, pupil = self.restore(e, pupil)
        before = self.state(e, pupil)
        with self.assertRaisesRegex(ValueError, 'current core Gluttony quota observation required'):
            self.eat(e, pupil, buffs[1])
        self.assertEqual(self.state(e, pupil), before)
        observation = e.observe_core_gluttony_quota(pupil, used=1,
            reason='GM actually observed one eligible exchange in this current encounter')
        self.assertEqual((observation['actor_id'], observation['encounter_epoch'], observation['through_sequence']),
                         (pupil.entity_id, e._party_encounter_epoch, 1))
        self.eat(e, pupil, buffs[1])
        before = self.state(e, pupil)
        with self.assertRaisesRegex(ValueError, 'cannot refill'):
            e.observe_core_gluttony_quota(pupil, used=1, reason='cannot discard the second actual exchange')
        self.assertEqual(self.state(e, pupil), before)
        e.gm.snapshot('legacy-current-quota')
        self.eat(e, pupil, buffs[2])
        e.gm.restore('legacy-current-quota', reason='actual observed current quota rewind')
        e, pupil = self.restore(e, pupil)
        self.eat(e, pupil, buffs[2])
        before = self.state(e, pupil)
        with self.assertRaisesRegex(ValueError, 'encounter Digestion Buff quota'):
            self.eat(e, pupil, buffs[3])
        self.assertEqual(self.state(e, pupil), before)
        self.assertEqual(pupil.spec['food_consumption_receipts'][0], old)
        self.assertNotIn(FOOD.ENCOUNTER_RECEIPT, pupil.spec['food_consumption_receipts'][0])
        self.assertEqual(pupil.spec[FOOD.CORE_OBSERVATION], observation)
        e.end_encounter(e.everyone, round_elapsed_seconds=0)
        e.start_round(e.everyone)
        e.start_of_turn(pupil, initiative_count=20)
        self.eat(e, pupil, buffs[3])
        self.assertEqual(pupil.spec['food_consumption_receipts'][0], old)
        self.assertEqual(pupil.spec[FOOD.CORE_OBSERVATION], observation)
        self.assertTrue(e.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
