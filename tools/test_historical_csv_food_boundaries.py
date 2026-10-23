"""Native stage and timing boundaries following real public Extended intake."""
from unittest.mock import patch
import json
import unittest

from engine import Engine
import csv_item_food_contracts as FOOD
import combat_timing as TIMING
import state_codec as CODEC
import stage_change_history as HISTORY
import world_entities as WORLD
import food_effects as COMMON
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts


class HistoricalCsvFoodBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass()

    def setUp(self):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.answers.clear()
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.provider = None

    def tearDown(self):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.answers.clear()
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.rulings.provider = None

    def fixture(self, item, *, disposition='liked'):
        fixture = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests()
        actor = fixture.pokemon('csv-food-holder', items={item: 1})
        if item=='item/단맛-과자':
            nature=self.nature_for(disposition)
            actor.spec['nature']=nature
        source = fixture.pokemon('csv-food-source', moves=('move/칼춤',))
        engine = fixture.fixture(actor, source)
        result=engine.use_item(actor,item,food_policy=FOOD.definition(engine.r,item)['clause_id'],
            duration_minutes=1,duration_reason='GM actual intake before native event')
        buff=COMMON.get_buff(actor,result['buff_id'])
        return engine, actor, source, buff

    def nature_for(self,disposition):
        key='likes' if disposition=='liked' else 'dislikes'
        return next(name for name,row in _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.r.mech('pokemon/natures')['by_name'].items()
                    if row.get(key,'').replace(' ','')=='단맛' and row['up']!=row['down'])

    def choose(self, engine, answer=True):
        engine.rulings.add_answer('mirror_herb', answer,
                                  reason='explicit holder exchange for actual stage event')

    def spent(self, actor):
        return actor.spec.get('food_consumption_receipts',[])

    def test_mirror_actual_stage_late_failure_rolls_back_buff_and_stage(self):
        e, actor, source, buff = self.fixture('item/흉내허브')
        self.choose(e)
        e.start_round([source, actor])
        e.start_of_turn(source, initiative_count=20)
        before = CODEC.dump_engine(e)
        original = Engine.change_stage
        attempted = []
        def fail_after_actual_stage(engine, target, stat, delta):
            result = original(engine, target, stat, delta)
            if target.entity_id == actor.entity_id:
                attempted.append({'copied_stage': target.stages[stat],
                                  'native_event': HISTORY.rises_since_turn_start(
                                      WORLD.actor_index(engine)[source.entity_id])[-1]})
                raise ValueError('bounded late fault after actual native copied stage')
            return result
        with patch.object(Engine, 'change_stage', fail_after_actual_stage):
            with self.assertRaisesRegex(ValueError, 'bounded late fault'):
                e.change_stage(source, 'atk', 2)
        self.assertEqual(attempted[0]['copied_stage'], 2)
        self.assertEqual((attempted[0]['native_event']['before'],
                          attempted[0]['native_event']['after']), (0, 2))
        self.assertEqual(before, CODEC.dump_engine(e))
        self.assertEqual((source.stages['atk'], actor.stages['atk']), (0, 0))
        self.assertFalse(hasattr(e, '_csv_food_stage_event'))
        self.assertFalse(hasattr(e, '_csv_food_stage_transaction'))
        print('MIRROR_NATIVE_LATE_FAULT', json.dumps(
            {'attempted': attempted, 'same_dump': before == CODEC.dump_engine(e)}, ensure_ascii=True))

    def test_mirror_native_swords_dance_is_printed_actual_event_and_spent_once_after_restore(self):
        e, actor, source, buff = self.fixture('item/흉내허브')
        self.choose(e)
        mech, provenance = e.r.move_mech('move/칼춤')
        effect = next(row for row in mech['effects_exec'] if row['type'] == 'stage_change')
        self.assertEqual((effect['stat'], effect['delta']), ('atk', 2))
        self.assertTrue(effect['_src'])
        e.start_round([source, actor])
        e.start_of_turn(source, initiative_count=20)
        e.use_move(source, source, 'move/칼춤')
        self.assertEqual((source.stages['atk'], actor.stages['atk']), (2, 2))
        event = HISTORY.rises_since_turn_start(source)[-1]
        self.assertEqual((event['before'], event['after'], event['source_id']), (0, 2, 'move/칼춤'))
        receipt = self.spent(actor)[0]
        self.assertEqual(receipt['buff_id'], buff['id'])
        self.assertEqual(receipt['benefit'], {'source_actor_id': source.entity_id,
            'stat': 'atk', 'before': 0, 'after': 2, 'delta': 2})
        self.assertFalse(actor.buffs)
        payload = CODEC.dump_engine(e)
        restored = CODEC.load_engine(e.r, json.loads(json.dumps(payload)))
        index = WORLD.actor_index(restored)
        other, holder = index[source.entity_id], index[actor.entity_id]
        restored.change_stage(other, 'atk', 1)
        self.assertEqual(holder.stages['atk'], 2)
        self.assertEqual(len(self.spent(holder)), 1)
        print('MIRROR_PRINTED_NATIVE', json.dumps({'source_id': 'move/칼춤',
            'payload': effect, 'provenance': provenance, 'native_event': event,
            'receipt': receipt, 'restored_no_reuse': True}, ensure_ascii=True))

    def test_mirror_actual_clamped_gain_reacts_without_turn_history_window(self):
        fixture = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests()
        actor = fixture.pokemon('no-window-holder', items={'item/흉내허브': 1})
        source = fixture.pokemon('no-window-source')
        e = fixture.fixture(actor, source)
        e.change_stage(source, 'atk', 5)
        e.use_item(actor,'item/흉내허브',duration_minutes=1,duration_reason='native clamped fixture intake')
        self.choose(e)
        self.assertFalse(HISTORY.rises_since_turn_start(source))
        e.change_stage(source, 'atk', 2)
        self.assertEqual((source.stages['atk'], actor.stages['atk']), (6, 1))
        self.assertFalse(HISTORY.rises_since_turn_start(source))
        self.assertEqual(self.spent(actor)[0]['benefit']['delta'], 1)

    def test_mirror_absent_or_declined_choice_preserves_actual_buff(self):
        for answer in (None, False):
            with self.subTest(answer=answer):
                e, actor, source, buff = self.fixture('item/흉내허브')
                if answer is not None:
                    self.choose(e, answer)
                e.change_stage(source, 'atk', 2)
                self.assertEqual((source.stages['atk'], actor.stages['atk']), (2, 0))
                self.assertEqual(actor.buffs[0]['id'], buff['id'])
                self.assertFalse(self.spent(actor))
                e.rulings.answers.clear()

    def test_mirror_multiple_holders_copy_recursively_each_buff_only_once(self):
        e, first, source, first_buff = self.fixture('item/흉내허브')
        fixture = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests()
        second = fixture.pokemon('second-holder', items={'item/흉내허브': 1})
        e.gm.add_combatant(second)
        second_result=e.use_item(second,'item/흉내허브',duration_minutes=1,duration_reason='second actual holder intake')
        second_buff=COMMON.get_buff(second,second_result['buff_id'])
        source.spec['items']['item/흉내허브'] = 1
        source_result=e.use_item(source,'item/흉내허브',duration_minutes=1,duration_reason='source actual holder intake')
        source_buff=COMMON.get_buff(source,source_result['buff_id'])
        self.choose(e)
        e.change_stage(source, 'atk', 2)
        self.assertEqual((source.stages['atk'], first.stages['atk'], second.stages['atk']), (4, 2, 2))
        for holder, buff in ((first, first_buff), (second, second_buff), (source, source_buff)):
            self.assertFalse(holder.buffs)
            self.assertEqual([row['buff_id'] for row in self.spent(holder)], [buff['id']])
        e.change_stage(source, 'atk', 1)
        self.assertEqual((first.stages['atk'], second.stages['atk']), (2, 2))

    def test_mirror_nonpositive_and_source_own_gain_do_not_spend(self):
        e, actor, source, buff = self.fixture('item/흉내허브')
        self.choose(e)
        e.change_stage(source, 'atk', -1)
        e.change_stage(source, 'atk', 0)
        e.change_stage(actor, 'atk', 2)
        self.assertEqual(actor.stages['atk'], 2)
        self.assertEqual(actor.buffs[0]['id'], buff['id'])
        self.assertFalse(self.spent(actor))

    def test_mirror_fabricated_or_replayed_direct_observation_is_rejected_without_mutation(self):
        e, actor, source, buff = self.fixture('item/흉내허브')
        for when in ('before_actual_gain', 'after_actual_gain'):
            before = CODEC.dump_engine(e)
            with self.assertRaisesRegex(ValueError, 'actual native stage event'):
                FOOD.observe_positive_stage(e, source, 'atk', 0, 2, recipient=actor)
            self.assertEqual(before, CODEC.dump_engine(e))
            if when == 'before_actual_gain':
                e.change_stage(source, 'atk', 2)
        self.assertEqual(actor.buffs[0]['id'], buff['id'])

    def test_sweet_actual_status_late_failure_rolls_back_timing_status_and_buff(self):
        e, actor, source, buff = self.fixture('item/단맛-과자',disposition='disliked')
        e.start_round([actor, source])
        e.start_of_turn(actor, initiative_count=20)
        before = CODEC.dump_engine(e)
        original = Engine.apply_status
        def fail_after_actual_status(engine, target, condition, **kwargs):
            result = original(engine, target, condition, **kwargs)
            if target.entity_id == actor.entity_id and condition == '난동':
                raise ValueError('bounded late fault after actual native disliked status')
            return result
        with patch.object(Engine, 'apply_status', fail_after_actual_status):
            with self.assertRaisesRegex(ValueError, 'bounded late fault'):
                e.consume_food_buff(actor,buff_id=buff['id'])
        after = CODEC.dump_engine(e)
        print('SWEET_LATE_FAULT', json.dumps({'remaining_buffs':
            [row['id'] for row in actor.buffs],
            'conditions': sorted(actor.conditions), 'timed_effects': len(TIMING.records(actor)),
            'same_dump': before == after}, ensure_ascii=True))
        self.assertEqual(before, after)

    def test_sweet_current_timing_and_single_spend_survive_json_until_next_turn_end(self):
        e, actor, source, buff = self.fixture('item/단맛-과자')
        e.start_round([actor, source])
        e.start_of_turn(actor, initiative_count=20)
        result = e.consume_food_buff(actor,buff_id=buff['id'])
        self.assertEqual(result['evasion'], 2)
        self.assertEqual(len(self.spent(actor)), 1)
        self.assertFalse(actor.buffs)
        restored = CODEC.load_engine(e.r, json.loads(json.dumps(CODEC.dump_engine(e))))
        holder = WORLD.actor_index(restored)[actor.entity_id]
        self.assertEqual(TIMING.records(holder)[0]['evasion_modifier'], 2)
        timing=TIMING.records(holder)[0]
        timing['skill_modifier']=100
        with self.assertRaises(CODEC.StateCodecError):
            CODEC.load_engine(restored.r,json.loads(json.dumps(CODEC.dump_engine(restored))))
        timing.pop('skill_modifier')
        before = CODEC.dump_engine(restored)
        with self.assertRaisesRegex(ValueError, 'one actual'):
            restored.consume_food_buff(holder,buff_id=buff['id'])
        self.assertEqual(before, CODEC.dump_engine(restored))
        restored.end_of_turn(holder)
        self.assertEqual(len(TIMING.records(holder)), 1)
        restored.end_round()
        restored.start_round(list(WORLD.actor_index(restored).values()))
        restored.start_of_turn(holder, initiative_count=20)
        restored.end_of_turn(holder)
        self.assertFalse(TIMING.records(holder))
