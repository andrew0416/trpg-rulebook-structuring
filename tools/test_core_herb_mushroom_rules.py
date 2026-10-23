"""New Chapter 9 source connections; reuse existing owners rather than inherit suites."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
import test_category2_progression_state as FIX
import test_category3_crafting as CRAFT_FIX
import test_category2_herbal_state as HERBAL_FIX
import test_clock_native_consumers as CLOCK_FIX
import herb_mushroom_rules as HERB
import food_effects as FOOD
import items as ITEMS
import item_stock as STOCK
import world_entities as WORLD
import state_codec as CODEC
import combat_stage_sources as STAGES
import downtime as DOWNTIME
import common_checks as C


class HerbMushroomTests(unittest.TestCase):
    setUpClass = classmethod(FIX.ProgressionStateTests.setUpClass.__func__)
    add = FIX.ProgressionStateTests.add
    pokemon = FIX.ProgressionStateTests.pokemon
    own = CRAFT_FIX.CraftTests.own
    plant_setup = CRAFT_FIX.CraftTests.plant_setup

    def setUp(self):
        FIX.ProgressionStateTests.setUp(self)
        self.p = self.pokemon(20)
        self.p.spec['loyalty'] = 6
        self.q = self.pokemon(20)

    def state(self):
        return deepcopy((self.e.rng.getstate(), self.e.elapsed_seconds,
                         [vars(actor) for actor in self.e.gm.everyone],
                         getattr(self.e, '_physical_objects', {}), self.e.log_lines),
                        {id(self.r): self.r})

    def held(self, actor, name, uid):
        WORLD.register_object(self.e, uid, location={'kind': 'unknown'},
            reason='actual observed herb or mushroom', kind='item_instance',
            item_rule_id='item/' + name, owner_id=actor.entity_id)
        ITEMS.equip_held(self.e, actor, name, source_instance_id=uid)
        return uid

    def snack(self, name, target=None):
        target = target or self.p
        self.a.spec['items'][name] = self.a.spec['items'].get(name, 0) + 1
        return self.e.use_item(self.a, name, target, duration_minutes=1,
                               duration_reason='actual Extended herb intake')

    def turn(self, actor):
        self.e.start_round(self.e.gm.everyone)
        self.e.start_of_turn(actor)

    def test_poultice_uses_revised_shared_herbal_history_and_native_dressing(self):
        self.a.spec['items'] = {'파스': 2, '힘의뿌리': 1, '붕대': 1}
        self.p.spec['loyalty'] = 4
        self.p.hp = 1
        result = self.e.use_item(self.a, '파스', self.p, duration_minutes=1,
                                duration_reason='actual dressing application')
        self.assertEqual(result['record']['expires_at'] - result['record']['started_at'], 21600)
        self.assertEqual(FOOD.herbal_state(self.p)['count'], 1)
        self.assertEqual(self.p.buffs[0]['effect'], {'kind': 'save_bonus', 'amount': 2})
        self.e.use_item(self.a, '힘의뿌리', self.p)
        self.assertEqual(FOOD.herbal_state(self.p)['count'], 2)
        self.assertFalse(FOOD.temp_hp_allowed(self.p))
        self.p.hp = 1
        DOWNTIME.rest(self.e, self.p, 30)
        self.assertEqual(self.p.hp, 1 + self.p.base_max_hp // 8)
        self.held(self.a, '파스', 'actual-poultice')
        self.e.use_item(self.a, '파스', self.p, held_selection='actual-poultice',
                        duration_minutes=1, duration_reason='same physical dressing')
        self.assertEqual(FOOD.herbal_state(self.p)['count'], 3)
        self.assertEqual(FOOD.herbal_state(self.p)['uses'][-1]['item'], 'item/파스')
        self.assertEqual(self.p.spec['loyalty'], 4)
        self.assertNotIn('bitter_medicine_history', self.p.spec)
        self.assertIn('consumed', self.e._physical_objects['actual-poultice'])
        self.e.use_item(self.a, '붕대', self.q, duration_minutes=1,
                        duration_reason='ordinary bandage stays nonherbal')
        self.assertEqual(FOOD.herbal_state(self.q)['count'], 0)
        self.assertEqual(self.r.item_effects('붕대')[1]['price'], 300)
        self.a.spec['items']['파스'] = 3
        self.e.use_item(self.a, '파스', self.q, count=3, duration_minutes=1,
                        duration_reason='three actual dressings share the recipient history')
        self.assertEqual(FOOD.validate_herbal(self.q)['count'], 3)
        self.assertEqual([row['count'] for row in FOOD.herbal_state(self.q)['uses']], [1, 2, 3])
        self.assertEqual(self.a.spec['items']['파스'], 0)

    def test_poultice_invalid_history_and_late_failure_keep_payment_time_and_effects(self):
        self.a.spec['items']['파스'] = 3
        before = self.state()
        self.e.use_item(self.a, '파스', self.p, accepted=False, duration_minutes=1,
                        duration_reason='refused application')
        self.assertEqual(before[:4], self.state()[:4])
        self.assertEqual(self.e.log_lines[:-1], before[4])
        self.assertIn('파스 사용 거부 → 미사용', self.e.log_lines[-1])
        before = self.state()
        with patch.object(FOOD, 'herbal_consumed', side_effect=ValueError('late herbal fault')):
            with self.assertRaisesRegex(ValueError, 'late herbal fault'):
                self.e.use_item(self.a, '파스', self.p, duration_minutes=1,
                                duration_reason='failed herbal attachment')
        self.assertEqual(before, self.state())
        self.p.spec['herbal_restoratives'] = {'source': FOOD.MEDICINE, 'count': 1, 'uses': []}
        before = self.state()
        with self.assertRaises(ValueError):
            self.e.use_item(self.a, '파스', self.p, duration_minutes=1,
                            duration_reason='invalid history')
        self.assertEqual(before, self.state())

    def test_poultice_resumable_application_restores_and_attaches_herbal_use_once(self):
        self.rules = self.r
        self.a.spec['items']['파스'] = 1
        CLOCK_FIX.TimedConsumerTests.install(self)
        use = lambda: CLOCK_FIX.TimedConsumerTests.use(self, '파스', identity='herbal-dressing')
        self.assertEqual(use()['status'], 'waiting')
        self.assertEqual(FOOD.herbal_state(self.p)['count'], 0)
        ids = self.a.entity_id, self.p.entity_id
        snapshot = self.e.gm.snapshot()
        loaded = CODEC.load_engine(Rules(str(ROOT), ruleset='core'),
            json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        self.e.gm.restore(snapshot)
        for engine in (self.e, loaded):
            self.e = engine
            self.a, self.p = (WORLD.actor_index(engine)[uid] for uid in ids)
            CLOCK_FIX.TimedConsumerTests.answer(self, 'herbal-dressing')
            original = FOOD.herbal_consumed
            def fail(*args):
                original(*args)
                raise ValueError('late resumed herbal fault')
            with patch.object(FOOD, 'herbal_consumed', fail):
                with self.assertRaisesRegex(ValueError, 'late resumed herbal fault'):
                    use()
            self.assertEqual((engine.elapsed_seconds, self.a.spec['items']['파스']), (60, 1))
            self.assertEqual(FOOD.herbal_state(self.p)['count'], 0)
            self.assertFalse(self.p.spec.get('bandages'))
            out = use()
            self.assertEqual(FOOD.herbal_state(self.p)['count'], 1)
            self.assertEqual(self.a.spec['items']['파스'], 0)
            self.assertEqual(len(self.p.spec['bandages']), 1)
            before = CODEC.dump_engine(engine)
            self.assertEqual(use(), out)
            self.assertEqual(CODEC.dump_engine(engine), before)

    def test_restoratives_snacks_and_mushrooms_keep_their_actual_action_routes(self):
        self.a.spec['items']['힘의뿌리'] = 1
        self.p.hp = 1
        self.turn(self.a)
        self.e.use_item(self.a, '힘의뿌리', self.p)
        self.assertEqual(self.p.hp, min(self.p.max_hp, 71))
        self.assertEqual(self.a.budget, {'standard': 0, 'shift': 1, 'swift': 1})
        self.assertEqual(self.p.pending_action_loss, {'standard': 1, 'swift': 1})
        self.assertEqual(FOOD.herbal_state(self.p)['count'], 1)
        self.assertFalse(FOOD.handles('item/힘의뿌리'))
        self.e.end_encounter(self.e.gm.everyone)
        self.a.spec['items']['부활초'] = 1
        self.p.hp = 0
        self.e.check_fainted(self.p)
        self.turn(self.a)
        self.e.use_item(self.a, '부활초', self.p)
        self.assertFalse(self.p.fainted)
        self.assertEqual(self.p.hp, self.p.base_max_hp // 2)
        self.assertEqual(self.a.budget['standard'], 0)
        self.assertEqual(self.p.pending_action_loss, {'standard': 1, 'swift': 1})
        self.e.end_encounter(self.e.gm.everyone)
        for name in ('멘탈허브', '하양허브', '파워풀허브'):
            self.assertTrue(FOOD.handles('item/' + name))
        # Power Herb's actual Set-Up exchange is covered by test_core_power_herb_skip.
        result = self.snack('멘탈허브', self.q)
        self.assertEqual(result['status'], 'digestion_buff_gained')
        self.assertEqual(self.q.buffs[-1]['effect'], HERB.SNACK_EFFECTS['item/멘탈허브'])
        self.held(self.q, '작은버섯', 'mushroom-action')
        self.turn(self.q)
        before = self.q.hp
        used = self.e.use_item(self.q, '작은버섯', held_selection='mushroom-action')
        self.assertEqual(used['status'], 'consumed')
        self.assertEqual(self.q.hp, before - 5)
        self.assertEqual(self.q.budget, {'standard': 1, 'shift': 1, 'swift': 0})
        self.assertIsNone(getattr(self.q, 'pending_action_loss', None))

    def test_mental_and_white_herbs_consume_native_buffs_without_erasing_base_sources(self):
        mental = self.snack('멘탈허브')
        self.e.apply_status(self.p, '혼란')
        self.e.apply_status(self.p, '헤롱헤롱', applied_by=self.q)
        self.e.apply_status(self.p, '독')
        before = CODEC.dump_engine(self.e)
        original = HERB.immediate_commit
        def fail(*args):
            original(*args)
            raise ValueError('late Mental Herb fault')
        with patch.object(HERB, 'immediate_commit', fail):
            with self.assertRaisesRegex(ValueError, 'late Mental Herb fault'):
                self.e.consume_food_buff(self.p, buff_id=mental['buff_id'],
                    action_kind='swift', action_reason='actual failed herb activation')
        self.assertEqual(before, CODEC.dump_engine(self.e))
        result = self.e.consume_food_buff(self.p, buff_id=mental['buff_id'],
            action_kind='swift', action_reason='GM declared actual herb buff timing')
        self.assertEqual(set(result['cured']), {'혼란', '헤롱헤롱'})
        self.assertIn('독', self.p.conditions)
        self.assertFalse(self.p.buffs)
        self.e.end_encounter(self.e.gm.everyone)
        white = self.snack('하양허브', self.q)
        self.a.spec['items']['힘의가루'] = 3
        for index in range(3):
            if index == 2:
                HERBAL_FIX.HerbalStateTests.faces(self, 1)
            self.e.use_item(self.a, '힘의가루', self.q)
        self.assertEqual(FOOD.herbal_state(self.q)['count'], 3)
        self.e.change_stage(self.q, 'def', -2)
        self.e.change_stage(self.q, 'spa', 2)
        self.q.accuracy_stage = -1
        base = deepcopy(self.q.spec[STAGES.STATE]['base'])
        before = CODEC.dump_engine(self.e)
        with patch.object(STAGES, 'assign_combat', side_effect=ValueError('late White Herb fault')):
            with self.assertRaisesRegex(ValueError, 'late White Herb fault'):
                self.e.consume_food_buff(self.q, buff_id=white['buff_id'], action_kind='swift',
                    action_reason='actual failed White Herb activation')
        self.assertEqual(before, CODEC.dump_engine(self.e))
        self.e.consume_food_buff(self.q, buff_id=white['buff_id'], action_kind='swift',
                                  action_reason='GM actual White Herb buff activation')
        self.assertEqual((self.q.stages['atk'], self.q.stages['def'], self.q.stages['spa']), (0, 0, 2))
        self.assertEqual(self.q.spec[STAGES.STATE]['base'], base)
        self.assertEqual(self.q.accuracy_stage, -1)
        FOOD.validate_herbal(self.q)
        with self.assertRaises(ValueError):
            self.e.consume_food_buff(self.q, buff_id=white['buff_id'], action_kind='swift',
                                      action_reason='already consumed')
        for name in ('멘탈허브', '하양허브'):
            self.setUp()
            self.snack(name)
            if name == '멘탈허브':
                self.e.apply_status(self.p, '헤롱헤롱', applied_by=self.q)
            else:
                self.e.change_stage(self.p, 'atk', -2)
            self.p.moves = ['move/볼가득넣기']
            self.turn(self.p)
            self.e.use_move(self.p, self.p, 'move/볼가득넣기')
            self.assertNotIn('헤롱헤롱', self.p.conditions)
            self.assertEqual(self.p.stages['atk'], 0)
            self.assertEqual(self.p.stages['def'], 2)
            self.assertFalse(self.p.buffs)
            self.assertEqual(self.p.spec['food_consumption_receipts'][0]['producer'],
                             'move/볼가득넣기')

    def test_successful_appraisal_binds_exact_stats_through_transfer_and_restores(self):
        self.held(self.a, '큰버섯', 'identified-big')
        failed = self.e.appraise_mushroom(self.a, instance_id='identified-big', fixed=[4, 5, 5, 5])
        self.assertFalse(failed['check'].passed)
        self.assertEqual(failed['check'].total, 19)
        self.assertNotIn('stats', failed)
        result = self.e.appraise_mushroom(self.a, instance_id='identified-big', fixed=[5] * 4)
        self.assertEqual(result['check'].total, 20)
        self.assertEqual(len(set(result['stats'])), 2)
        plan = deepcopy(self.e._physical_objects['identified-big'][HERB.PLAN])
        rng = self.e.rng.getstate()
        again = self.e.appraise_mushroom(self.a, instance_id='identified-big', fixed=[5] * 4)
        self.assertEqual(again['stats'], result['stats'])
        self.assertEqual(self.e.rng.getstate(), rng)
        observer = self.add(FIX.build_trainer(self.r, 'second appraiser', 20,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            skills={'생존': 4}, extra={'items': {}, 'edges': []}))
        ITEMS.transfer_equipment(self.e, self.a, observer, 'identified-big', consent_by=(self.a,))
        self.assertEqual(self.e.appraise_mushroom(observer, instance_id='identified-big',
                         fixed=[5] * 4)['stats'], result['stats'])
        self.assertEqual(self.e.rng.getstate(), rng)
        ITEMS.transfer_equipment(self.e, observer, self.p, 'identified-big', consent_by=(observer,))
        snapshot = self.e.gm.snapshot()
        saved = json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False))
        loaded = CODEC.load_engine(Rules(str(ROOT), ruleset='core'), saved)
        self.e.gm.restore(snapshot)
        for engine in (self.e, loaded):
            with self.subTest(restore='gm' if engine is self.e else 'cold_json'):
                p = WORLD.actor_index(engine)[self.p.entity_id]
                self.assertEqual(engine._physical_objects['identified-big'][HERB.PLAN], plan)
                rng = engine.rng.getstate()
                before_stages = dict(p.stages)
                used = engine.use_item(p, '큰버섯', held_selection='identified-big')
                self.assertEqual(used['stats'], result['stats'])
                self.assertEqual(engine.rng.getstate(), rng)
                self.assertIn('독', p.conditions)
                expected_stages = dict(before_stages)
                expected_stages['spd'] -= 2  # actual native Poison contribution
                for stat in used['stats']:
                    expected_stages[stat] += 1
                self.assertEqual(p.stages, expected_stages)
                self.assertIn('consumed', engine._physical_objects['identified-big'])
                self.assertTrue(engine.validate_state()['valid'])
                before = deepcopy(engine._physical_objects['identified-big'])
                with self.assertRaises(ValueError):
                    engine.use_item(p, '큰버섯', held_selection='identified-big')
                self.assertEqual(engine._physical_objects['identified-big'], before)

    def test_all_three_mushroom_effects_and_conditional_aromatic_penalty(self):
        for name in ('작은버섯', '큰버섯', '향기버섯'):
            for cured in (False, True) if name == '향기버섯' else (False,):
                self.setUp()
                self.held(self.p, name, 'effect-case')
                if cured:
                    for condition in ('독', '화상', '마비'):
                        self.e.apply_status(self.p, condition)
                hp = self.p.hp
                before = dict(self.p.stages)
                result = self.e.use_item(self.p, name, held_selection='effect-case')
                expected = 2 if name == '큰버섯' else 1 if name != '향기버섯' or cured else 0
                self.assertEqual(len(result['stats']), expected)
                self.assertEqual(len(set(result['stats'])), expected)
                if name == '작은버섯':
                    self.assertEqual(self.p.hp, hp - 5)
                elif name == '큰버섯':
                    self.assertIn('독', self.p.conditions)
                else:
                    self.assertTrue(set(result['cured']) <= {'화상', '마비', '독'})
                    self.assertFalse({'화상', '마비', '독'} & self.p.conditions)
                expected_stages = dict(before)
                if name == '큰버섯':
                    expected_stages['spd'] -= 2
                elif name == '향기버섯' and cured:
                    expected_stages['def'] += 2  # actual Burn contribution ends
                    expected_stages['spd'] += 2  # actual Poison contribution ends
                for stat in result['stats']:
                    expected_stages[stat] += -1 if name == '향기버섯' else 1
                self.assertEqual(self.p.stages, expected_stages)
                if expected == 0:
                    self.assertEqual(self.p.stages, before)

    def test_mushroom_boundaries_source_validation_and_late_failure(self):
        self.held(self.p, '작은버섯', 'boundary')
        before = self.state()
        self.e.use_item(self.p, '작은버섯', held_selection='boundary', accepted=False)
        self.assertEqual(before, self.state())
        original_stage = Engine.change_stage
        def late_stage(engine, *args, **kwargs):
            original_stage(engine, *args, **kwargs)
            raise ValueError('late mushroom stage fault')
        with patch.object(Engine, 'change_stage', late_stage):
            with self.assertRaisesRegex(ValueError, 'late mushroom stage fault'):
                self.e.use_item(self.p, '작은버섯', held_selection='boundary')
        self.assertEqual(before, self.state())
        for invoke in (
            lambda: self.e.use_item(self.p, '작은버섯'),
            lambda: self.e.use_item(self.p, '큰버섯', held_selection='boundary'),
            lambda: self.e.appraise_mushroom(self.a, instance_id='boundary', fixed=[5] * 4),
            lambda: self.e.use_item(self.p, '작은버섯', self.a, held_selection='boundary'),
        ):
            with self.assertRaises(ValueError):
                invoke()
            self.assertEqual(before, self.state())
        with patch.object(ITEMS, 'unregister_item', side_effect=ValueError('late physical fault')):
            with self.assertRaisesRegex(ValueError, 'late physical fault'):
                self.e.use_item(self.p, '작은버섯', held_selection='boundary')
        self.assertEqual(before, self.state())
        original = self.r._selected_rule
        with patch.object(self.r, '_selected_rule',
                          lambda uid: uid + '-unsupported' if uid == HERB.SOURCE else original(uid)):
            with self.assertRaises(ValueError):
                self.e.use_item(self.p, '작은버섯', held_selection='boundary')
            self.assertEqual(before, self.state())
        self.e.apply_status(self.p, '잠듦')
        before_hp = self.p.hp
        self.assertFalse(self.e.use_item(self.p, '작은버섯', held_selection='boundary'))
        self.assertEqual(self.p.hp, before_hp)
        self.assertNotIn('consumed', self.e._physical_objects['boundary'])
        self.e.cure_status(self.p, '잠듦')
        self.turn(self.p)
        self.p.budget.update(swift=0, standard=0)
        self.assertFalse(self.e.use_item(self.p, '작은버섯', held_selection='boundary'))
        self.assertNotIn('consumed', self.e._physical_objects['boundary'])
        self.e.end_encounter(self.e.gm.everyone)
        ITEMS.transfer_equipment(self.e, self.p, self.a, 'boundary', consent_by=(self.p,))
        self.e.appraise_mushroom(self.a, instance_id='boundary', fixed=[5] * 4)
        ITEMS.transfer_equipment(self.e, self.a, self.p, 'boundary', consent_by=(self.a,))
        saved = json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False))
        root_node = saved['nodes'][saved['root']['$ref']]
        self.assertEqual(root_node['kind'], 'engine')
        attributes = dict(saved['nodes'][root_node['attrs']['$ref']]['items'])
        registry = dict(saved['nodes'][attributes['_physical_objects']['$ref']]['items'])
        actual_body = dict(saved['nodes'][registry['boundary']['$ref']]['items'])
        actual_plan = dict(saved['nodes'][actual_body[HERB.PLAN]['$ref']]['items'])
        self.assertEqual(actual_plan['instance_id'], 'boundary')
        stats_node = saved['nodes'][actual_plan['stats']['$ref']]
        self.assertEqual(stats_node['items'], self.e._physical_objects['boundary'][HERB.PLAN]['stats'])
        stats_node['items'] = ['accuracy']
        with self.assertRaises(CODEC.StateCodecError):
            CODEC.load_engine(Rules(str(ROOT), ruleset='core'), saved)
        self.e._physical_objects['boundary'][HERB.PLAN]['stats'] = ['accuracy']
        invalid = deepcopy(self.e._physical_objects['boundary'])
        with self.assertRaises(ValueError):
            self.e.use_item(self.p, '작은버섯', held_selection='boundary')
        self.assertEqual(self.e._physical_objects['boundary'], invalid)
        self.assertFalse(self.e.validate_state()['valid'])

    def test_energy_root_grows_as_herb_but_never_enters_snack_route(self):
        # Reuse the existing native Botany fixture, not its test methods.
        self.a.spec.setdefault('feats', [])
        CRAFT_FIX.CraftTests.botany(self, '전문')
        self.a.spec['items']['힘의뿌리'] = 1
        self.e.pokemon_activity(self.a, 'plant_berry', berry='힘의뿌리',
                               plant_id='root', soft_soil=True)
        self.assertEqual(self.a.spec['items']['힘의뿌리'], 0)
        self.e.advance_time(172800, [self.a])
        result = self.e.pokemon_activity(self.a, 'harvest_berry', plant_id='root', fixed=4)
        self.assertEqual(result['amount'], 2)
        self.assertEqual(self.a.spec['plants']['root']['crop']['kind'], 'herb')
        self.assertFalse(FOOD.handles('item/힘의뿌리'))
        self.p.hp = 1
        self.e.use_item(self.a, '힘의뿌리', self.p)
        self.assertEqual(self.a.spec['items']['힘의뿌리'], 1)
        self.assertEqual(self.p.hp, min(self.p.max_hp, 71))
        self.assertEqual(FOOD.herbal_state(self.p)['count'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
