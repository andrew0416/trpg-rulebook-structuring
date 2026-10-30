"""Harvest uses the acquired Food Buff; retention never ends or regrants it."""
from copy import deepcopy
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from engine import Rules, Engine, Combatant
from builder import build_pokemon
import food_effects as FOOD
import effect_instances as INSTANCES
import combat_timing as TIMING
import state_codec as CODEC
import world_entities as WORLD
import survivalist_class as SC
import book_chef_fixture as CHEF_FIX
import chef_cooking as CHEF

ROOT=Path(__file__).resolve().parents[1]


def harvest_world(rules, *, item='초코바', abilities=('수확',), sunny=True):
    engine=Engine(rules,seed=42)
    actor=Combatant(rules,build_pokemon(rules,'이브이',20,name='harvester',
        moves=['move/몸통박치기'],abilities=list(abilities),extra={'items':{item:1}}))
    foe=Combatant(rules,build_pokemon(rules,'이브이',20,name='thief',
        moves=['move/벌레먹기'],abilities=[],extra={}))
    engine.gm.add_combatant(actor,pos=(0,0),side='party',reason='actual Harvest holder')
    engine.gm.add_combatant(foe,pos=(1,0),side='enemy',reason='actual opposing holder')
    intake=engine.use_item(actor,item,accepted=True,duration_minutes=1,
        duration_reason='actual physical food intake')
    if sunny:engine.gm.set_weather('sunny',reason='actual observed sunlight')
    engine.start_round(engine.everyone)
    engine.start_of_turn(actor,initiative_count=20)
    engine.gm.set_hp(actor,value=actor.base_max_hp-20,reason='actual prior damage')
    return engine,actor,foe,intake['buff_id']


def activate_food(engine,actor,buff_id):
    return engine.consume_food_buff(actor,buff_id=buff_id,action_kind='free',
        action_reason='GM-authorized Food Buff activation timing')


def next_turn(engine,actor):
    engine.end_of_turn(engine._active_turn_actor)
    engine.start_round(engine.everyone)
    engine.start_of_turn(actor,initiative_count=20)


class HarvestFoodTests(unittest.TestCase):
    def setUp(self):
        self.rules=Rules(ROOT,ruleset='all')

    def restored(self,engine):
        restored=CODEC.load_engine(self.rules,deepcopy(CODEC.dump_engine(engine)))
        self.assertTrue(restored.validate_state()['valid'])
        return restored,WORLD.actor_index(restored)

    def test_sun_retains_same_paid_instance_without_consumption_or_rng_and_blocks_same_turn(self):
        e,a,foe,bid=harvest_world(self.rules)
        before=deepcopy(FOOD.get_buff(a,bid));rng=e.rng.getstate();hp=a.hp
        result=activate_food(e,a,bid)
        self.assertEqual(result['status'],'retained')
        self.assertEqual(a.hp,hp+5)
        self.assertEqual(FOOD.get_buff(a,bid),before)
        self.assertEqual(e.rng.getstate(),rng)
        receipt=a.spec['food_consumption_receipts'][-1]
        self.assertNotIn(INSTANCES.KEY,receipt)
        self.assertEqual(receipt['harvest']['coin'],None)
        self.assertEqual(a.counters.get('food_buff_consumed',0),0)
        self.assertFalse(FOOD.consumed_this_scene(e,a))
        frozen=deepcopy(CODEC.dump_engine(e));rng=e.rng.getstate()
        with self.assertRaisesRegex(ValueError,'one Food Buff activation'):
            activate_food(e,a,bid)
        self.assertEqual(CODEC.dump_engine(e),frozen)
        self.assertEqual(e.rng.getstate(),rng)
        restored,index=self.restored(e)
        with self.assertRaisesRegex(ValueError,'one Food Buff activation'):
            activate_food(restored,index[a.entity_id],bid)

    def test_coin_heads_and_tails_preserve_actual_consumption_boundary_under_guide(self):
        for seed in (0,1):
            with self.subTest(seed=seed):
                e,a,foe,bid=harvest_world(self.rules)
                e.rng.seed(seed);expected=random.Random(seed).randint(1,2)
                hp=a.hp
                with patch.object(SC,'weather_ability_suppressed',return_value=True) as gate:
                    activate_food(e,a,bid)
                gate.assert_called_with(e,a,FOOD.HARVEST)
                receipt=a.spec['food_consumption_receipts'][-1]
                self.assertEqual(receipt['harvest']['coin'],expected)
                self.assertFalse(receipt['harvest']['sunny'])
                self.assertEqual(a.hp,hp+5)
                self.assertEqual(bool(a.buffs),expected==1)
                self.assertEqual(INSTANCES.KEY in receipt,expected==2)
                self.assertEqual(a.counters.get('food_buff_consumed',0),int(expected==2))
                self.assertEqual(FOOD.consumed_this_scene(e,a),expected==2)
                self.restored(e)

    def test_retained_then_terminal_consumption_keeps_unique_instance_and_receipt_parent(self):
        e,a,foe,bid=harvest_world(self.rules)
        activate_food(e,a,bid)
        next_turn(e,a)
        e.gm.set_weather(None,reason='sunlight ended');e.rng.seed(0)
        self.assertEqual(activate_food(e,a,bid)['status'],'consumed')
        rows=a.spec['food_consumption_receipts']
        self.assertEqual([row['sequence'] for row in rows],[1,2])
        self.assertEqual([row['buff_id'] for row in rows],[bid,bid])
        self.assertEqual(sum(INSTANCES.KEY in row for row in rows),1)
        self.assertFalse(a.buffs)
        self.assertEqual(a.counters['food_buff_consumed'],1)
        self.restored(e)

    def test_repeated_leftovers_activation_binds_each_ongoing_effect_and_expires(self):
        e,a,foe,bid=harvest_world(self.rules,item='먹다남은음식')
        activate_food(e,a,bid);next_turn(e,a);activate_food(e,a,bid)
        healing=a.spec['food_turn_healing']
        self.assertEqual([row['receipt_sequence'] for row in healing],[1,2])
        self.assertEqual(len({row['id'] for row in healing}),2)
        self.restored(e)
        e.end_of_turn(a);e.end_encounter(round_elapsed_seconds=10)
        self.assertFalse(a.spec.get('food_turn_healing'))
        self.restored(e)

    def test_retained_buff_can_be_stolen_live_without_creating_consumed_candidate(self):
        e,a,foe,bid=harvest_world(self.rules)
        activate_food(e,a,bid)
        self.assertEqual(FOOD.transfer_live_preflight(e,foe,a,'move/벌레먹기'),
                         {'kind':'live','buff_id':bid})
        self.assertEqual(FOOD.transfer_live(e,foe,a,'move/벌레먹기'),bid)
        self.assertFalse(a.buffs)
        self.assertEqual(FOOD.get_buff(foe,bid)[INSTANCES.KEY]['holder_id'],foe.entity_id)
        self.assertFalse(FOOD.theft_condition(a))
        self.restored(e)

    def test_repeated_sweet_timers_and_chef_consumption_observers_keep_correct_provenance(self):
        world=CHEF_FIX.scene(self.rules,abilities=['수확'])
        e,chef,a=[world[key] for key in ('engine','chef','partner')]
        cooked=CHEF_FIX.cook(e,chef,recipe='tasty_snack',snack='단맛 과자')
        bid=CHEF_FIX.serve(e,chef,cooked['batch_id'],a)['buff_id']
        CHEF_FIX.ruling(e,'encounter_end')
        e.gm.set_weather('sunny',reason='actual sunlight');CHEF_FIX.battle(e,a)
        e.consume_food_buff(a,buff_id=bid)
        first=a.spec['food_consumption_receipts'][-1]
        self.assertTrue(FOOD.retained_activation(first))
        self.assertFalse(CHEF_FIX.pending(e,chef,CHEF.AFTERTASTE))
        next_turn(e,a);e.consume_food_buff(a,buff_id=bid)
        timers=[row for row in TIMING.records(a) if row.get('chef_snack') or row.get('csv_sweet')]
        self.assertEqual([row['receipt_sequence'] for row in timers],[1,2])
        self.assertEqual(len({row['effect_id'] for row in timers}),2)
        self.restored(e)
        next_turn(e,a)
        self.assertEqual(len([row for row in TIMING.records(a) if row.get('chef_snack') or row.get('csv_sweet')]),1)
        self.restored(e)

    def test_lunchbox_rejects_retention_before_payment_and_accepts_later_consumption(self):
        e,a,foe,bid=harvest_world(self.rules,abilities=('수확','도시락통 [Playtest]'))
        activate_food(e,a,bid)
        retained=a.spec['food_consumption_receipts'][-1]
        self.assertTrue(FOOD.retained_activation(retained))
        frozen=deepcopy(CODEC.dump_engine(e));rng=e.rng.getstate()
        with self.assertRaisesRegex(ValueError,'^Lunchbox requires consumed food, not a retained Harvest activation$'):
            e.activate_ability(a,'도시락통 [Playtest]',(a,{'receipt_sequence':retained['sequence']}))
        self.assertEqual(CODEC.dump_engine(e),frozen)
        self.assertEqual(e.rng.getstate(),rng)
        next_turn(e,a)
        e.gm.set_weather(None,reason='sunlight ended');e.rng.seed(0)
        self.assertEqual(activate_food(e,a,bid)['status'],'consumed')
        consumed=a.spec['food_consumption_receipts'][-1]
        self.assertFalse(FOOD.retained_activation(consumed))
        before=a.temp_hp
        result=e.activate_ability(a,'도시락통 [Playtest]',(a,{'receipt_sequence':consumed['sequence']}))
        self.assertEqual(result['details']['temporary_hp'],e.tick(a))
        self.assertEqual(a.temp_hp,before+e.tick(a))
        retained,consumed=a.spec['food_consumption_receipts']
        self.assertNotIn('ability_native_claims',retained)
        self.assertEqual(consumed['ability_native_claims'],['ability/도시락통-playtest'])
        self.restored(e)

    def test_retained_receipt_cannot_claim_terminal_metadata_or_rewrite_source_payload(self):
        e,a,foe,bid=harvest_world(self.rules)
        activate_food(e,a,bid)
        receipt=a.spec['food_consumption_receipts'][0]
        original=deepcopy(receipt)
        receipt[INSTANCES.KEY]=deepcopy(a.buffs[0][INSTANCES.KEY])
        with self.assertRaises(ValueError):e.validate_state()
        receipt.clear();receipt.update(deepcopy(original))
        receipt['retained_buff']['effect']['amount']=999
        with self.assertRaises(ValueError):e.validate_state()
        receipt.clear();receipt.update(original)
        self.restored(e)


if __name__=='__main__':unittest.main()