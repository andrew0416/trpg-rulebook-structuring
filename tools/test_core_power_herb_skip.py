"""Power Herb's actual Snack exchange skips preparation, then uses native resolution."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine
from builder import build_trainer
import test_category2_setup_move_state as SETUP_FIX
import test_category2_native_setup_state as NATIVE_FIX
import food_effects as FOOD
import herb_mushroom_rules as HERB
import setup_move_state as SETUP
import state_codec as CODEC
import turn as TURN

POWER = 'item/파워풀허브'
BEAM = NATIVE_FIX.BEAM
BLADE = NATIVE_FIX.BLADE
GEOMANCY, FLY, DIG, DIVE = (SETUP_FIX.GEOMANCY, SETUP_FIX.FLY,
                           SETUP_FIX.DIG, SETUP_FIX.DIVE)


class PowerHerbTests(unittest.TestCase):
    setUpClass = classmethod(SETUP_FIX.SetupMoveStateTests.setUpClass.__func__)
    add = SETUP_FIX.SetupMoveStateTests.add

    def fixture(self, *, native=False, role='trainer'):
        if native:
            SETUP_FIX.SetupMoveStateTests.setUp(self)
        else:
            NATIVE_FIX.NativeSetupStateTests.fixture(self, role)
        self.e.end_encounter(self.e.everyone, round_elapsed_seconds=0)
        feeder = next(actor for actor in self.e.everyone if actor.kind == 'trainer'
                      and actor.side == 'party')
        feeder.spec.setdefault('items', {})['파워풀허브'] = 1
        before = self.e.elapsed_seconds
        result = self.e.use_item(feeder, '파워풀허브', self.a,
                                duration_minutes=1, duration_reason='actual Extended Snack intake')
        self.assertEqual(result['status'], 'digestion_buff_gained')
        self.assertEqual(self.e.elapsed_seconds, before + 60)
        self.assertEqual(feeder.spec['items'].get('파워풀허브', 0), 0)
        self.buff_id = self.a.buffs[-1]['id']
        self.assertEqual(self.a.buffs[-1]['effect'], {'kind': 'herb_skip_setup'})
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def choose(self, move):
        before = deepcopy((self.a.budget, self.a.move_uses, self.a.buffs,
                           self.e.elapsed_seconds, self.e.rng.getstate()))
        result = self.e.consume_food_buff(self.a, buff_id=self.buff_id, move_id=move)
        self.assertEqual(result['status'], 'prepared_for_actual_move')
        self.assertEqual(before, (self.a.budget, self.a.move_uses, self.a.buffs,
                                 self.e.elapsed_seconds, self.e.rng.getstate()))

    def state(self):
        return deepcopy((self.a.spec, self.a.buffs, self.a.budget, self.a.stages,
                         self.a.custom_conditions, self.a.setup_move, self.a.move_uses,
                         self.a.pos, ('airborne' in vars(self.a), getattr(self.a, 'airborne', None)),
                         self.b.hp, self.e.rng.getstate(),
                         self.e.elapsed_seconds, self.e.grid.__dict__,
                         getattr(self.e, '_burrow_tunnels', [])))

    def consumed(self, move):
        self.assertFalse(any(row['id'] == self.buff_id for row in self.a.buffs))
        rows = [row for row in self.a.spec['food_consumption_receipts']
                if row['buff_id'] == self.buff_id]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['producer'], move)
        self.assertEqual(rows[0]['benefit'], {'kind': 'skip_setup', 'move_id': move})
        self.assertEqual(self.a.counters['food_buff_consumed'], 1)
        self.assertNotIn('food_move_choice', self.a.spec)
        self.assertIsNone(self.a.setup_move)
        self.assertIsNone(SETUP.pending(self.a))
        self.assertEqual(self.a.move_uses[move], 1)

    def test_actual_snack_choice_survives_both_restores_and_resolves_once(self):
        for role in ('trainer', 'pokemon'):
            for restore in ('gm', 'json'):
                with self.subTest(role=role, restore=restore):
                    self.fixture(role=role)
                    self.choose(BEAM)
                    if restore == 'gm':
                        self.e.gm.snapshot('actual Power Herb choice')
                        self.a.spec.pop('food_move_choice')
                        self.e.gm.restore('actual Power Herb choice')
                    else:
                        aid, bid = self.a.entity_id, self.b.entity_id
                        self.e = CODEC.load_engine(self.r, json.loads(json.dumps(
                            CODEC.dump_engine(self.e), ensure_ascii=False)))
                        actors = {actor.entity_id: actor for actor in self.e.everyone}
                        self.a, self.b = actors[aid], actors[bid]
                    before = self.e.round_no, self.e.elapsed_seconds
                    hp = self.b.hp
                    with patch.object(Engine, 'd20', return_value=10) as roll:
                        self.e.use_move_on(self.a, self.b, BEAM, self.e.everyone)
                    roll.assert_called_once()
                    self.assertLess(self.b.hp, hp)
                    self.assertEqual(before, (self.e.round_no, self.e.elapsed_seconds))
                    self.assertEqual(self.a.budget, {'standard': 0, 'shift': 1, 'swift': 1})
                    self.consumed(BEAM)
                    with self.assertRaises(ValueError):
                        self.e.consume_food_buff(self.a, buff_id=self.buff_id, move_id=BEAM)

    def test_actual_generic_blade_omits_preparation_and_beam_miss_still_consumes(self):
        for move, face in ((BLADE, 10), (BEAM, 1)):
            with self.subTest(move=move):
                self.fixture()
                self.choose(move)
                stages, hp = deepcopy(self.a.stages), self.b.hp
                with patch.object(Engine, 'd20', return_value=face) as roll:
                    self.e.use_move_on(self.a, self.b, move, self.e.everyone)
                roll.assert_called_once()
                self.assertEqual(self.a.stages, stages)
                if face == 1:
                    self.assertEqual(self.b.hp, hp)
                else:
                    self.assertLess(self.b.hp, hp)
                self.consumed(move)

    def test_actual_sunny_exception_keeps_the_unneeded_herb(self):
        for move in (BEAM, BLADE):
            with self.subTest(move=move):
                self.fixture()
                self.choose(move)
                self.e.gm.set_weather('sunny', rounds=3)
                stages, hp = deepcopy(self.a.stages), self.b.hp
                with patch.object(Engine, 'd20', return_value=10):
                    self.e.use_move_on(self.a, self.b, move, self.e.everyone)
                self.assertLess(self.b.hp, hp)
                self.assertEqual(self.a.stages, stages)
                self.assertEqual(FOOD.get_buff(self.a, self.buff_id)['item'], POWER)
                self.assertEqual(self.a.spec['food_move_choice']['buff_id'], self.buff_id)
                self.assertFalse(self.a.spec.get('food_consumption_receipts'))
                self.assertEqual(self.a.move_uses[move], 1)

    def test_choice_and_denied_actual_action_do_not_consume_or_move(self):
        for native in (False, True):
            with self.subTest(native=native):
                self.fixture(native=native)
                before = self.state()
                for invalid in (SETUP_FIX.TACKLE, 'move/리벤지', 'move/눈사태'):
                    with self.assertRaises(ValueError):
                        self.e.consume_food_buff(self.a, buff_id=self.buff_id, move_id=invalid)
                self.assertEqual(before, self.state())

                move = DIG if native else BEAM
                self.choose(move)
                self.a.budget['standard'] = 0
                before = self.state()
                if native:
                    with self.assertRaises(ValueError):
                        self.e.use_setup_move_on(self.a, self.b, move, self.e.everyone,
                            setup_options={'path': [(3, 2), (4, 2)], 'diggable': True,
                                           'reason': 'actual surface route'})
                else:
                    self.assertEqual(self.e.use_move(self.a, self.b, move), 0)
                self.assertEqual(before, self.state())

        self.fixture()
        self.e.use_move(self.a, self.b, BEAM)
        self.assertEqual(self.a.setup_move, BEAM)
        before = self.state()
        with self.assertRaises(ValueError):
            self.e.consume_food_buff(self.a, buff_id=self.buff_id, move_id=BEAM)
        self.assertEqual(before, self.state())

    def test_actual_geomancy_has_only_resolution_stages_and_no_terrain_or_lock(self):
        self.fixture(native=True)
        self.choose(GEOMANCY)
        rough, now = deepcopy(self.e.grid.rough), self.e.round_no
        self.e.use_setup_move_on(self.a, self.a, GEOMANCY, self.e.everyone,
                                 setup_options={})
        self.assertEqual(self.e.grid.rough, rough)
        self.assertEqual(self.e.round_no, now)
        self.assertEqual({key: self.a.stages[key] for key in ('spa', 'spd', 'spe')},
                         {'spa': 2, 'spd': 2, 'spe': 2})
        self.assertTrue(TURN.movement_permission(self.e, self.a))
        self.assertEqual(self.a.budget, {'standard': 0, 'shift': 1, 'swift': 1})
        self.consumed(GEOMANCY)

    def test_actual_fly_uses_current_ground_or_air_position_without_preparation_ascent(self):
        for airborne in (False, True):
            with self.subTest(airborne=airborne):
                self.fixture(native=True)
                self.choose(FLY)
                if airborne:
                    self.e.aerial_move(self.a, self.a.pos, mode='sky', altitude=2,
                                       reason_text='actual ordinary flight before Fly')
                    self.assertEqual(self.a.spec['_movement_altitude'], 2)
                    path = [{'position': (3, 2), 'altitude': 2},
                            {'position': (4, 2), 'altitude': 2}]
                    expected = (4, 2)
                else:
                    self.e.gm.set_position(self.b, (3, 2), reason='actual adjacent target')
                    before = self.state()
                    with self.assertRaises(ValueError):
                        self.e.use_setup_move_on(self.a, self.b, FLY, self.e.everyone,
                            setup_options={'path': [{'position': (3, 2), 'altitude': 0}]})
                    self.assertEqual(before, self.state())
                    path, expected = [], (2, 2)
                hp = self.b.hp
                with patch.object(Engine, 'd20', return_value=10):
                    self.e.use_setup_move_on(self.a, self.b, FLY, self.e.everyone,
                                             setup_options={'path': path})
                self.assertEqual((self.a.pos, self.a.spec['_movement_altitude'], self.a.airborne),
                                 (expected, 0, False))
                self.assertLess(self.b.hp, hp)
                self.consumed(FLY)

    def test_actual_dig_uses_surface_overland_resolution_and_full_action_once(self):
        self.fixture(native=True)
        self.choose(DIG)
        other = self.add(build_trainer(self.r, 'second actual Burst target', 30,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 30),
            extra={'moves': [], 'side': 'opponent', 'pos': (4, 3), 'size': '중형'}))
        other_hp = other.hp
        hp, tunnels = self.b.hp, deepcopy(getattr(self.e, '_burrow_tunnels', []))
        with patch.object(Engine, 'd20', return_value=10) as roll:
            self.e.use_setup_move_on(self.a, self.b, DIG, self.e.everyone,
                setup_options={'path': [(3, 2), (4, 2)], 'diggable': True,
                               'reason': 'actual surface overland route'})
        roll.assert_called_once()
        self.assertEqual(self.a.pos, (4, 2))
        self.assertFalse(self.a.spec.get('_burrow', {}).get('underground'))
        self.assertEqual(getattr(self.e, '_burrow_tunnels', []), tunnels)
        self.assertLess(self.b.hp, hp)
        self.assertLess(other.hp, other_hp)
        self.assertEqual(self.a.budget, {'standard': 0, 'shift': 0, 'swift': 1})
        self.consumed(DIG)

    def test_actual_dive_retains_water_requirement_but_has_no_preparation_wait(self):
        self.fixture(native=True)
        self.choose(DIVE)
        self.e.observe_map_terrain([(2, 2), (3, 2), (4, 2), (5, 2)], base='underwater',
                                   reason='actual continuous deep-water route')
        before = self.state()
        with self.assertRaises(ValueError):
            self.e.use_setup_move_on(self.a, self.b, DIVE, self.e.everyone,
                setup_options={'path': [(3, 2), (4, 2)], 'water_depth_m': 9,
                               'reason': 'actual shallow-water observation'})
        self.assertEqual(before, self.state())
        hp, now = self.b.hp, self.e.round_no
        with patch.object(Engine, 'd20', return_value=10):
            self.e.use_setup_move_on(self.a, self.b, DIVE, self.e.everyone,
                setup_options={'path': [(3, 2), (4, 2)], 'water_depth_m': 12,
                               'reason': 'actual twelve-metre observation'})
        self.assertEqual((self.a.pos, self.e.round_no), ((4, 2), now))
        self.assertTrue(SETUP.targetable(self.a))
        self.assertLess(self.b.hp, hp)
        self.assertEqual(self.a.budget, {'standard': 0, 'shift': 0, 'swift': 1})
        self.consumed(DIVE)

    def test_actual_generic_and_native_late_failures_restore_the_same_exchange(self):
        for native in (False, True):
            with self.subTest(native=native):
                self.fixture(native=native)
                move = GEOMANCY if native else BEAM
                self.choose(move)
                before = self.state()
                original = HERB.consume_power_herb
                def fail(engine, actor, move_id):
                    original(engine, actor, move_id)
                    raise RuntimeError('late failure after actual Power Herb exchange')
                with patch.object(HERB, 'consume_power_herb', fail):
                    with self.assertRaisesRegex(RuntimeError, 'late failure'):
                        if native:
                            self.e.use_setup_move_on(self.a, self.a, move, self.e.everyone,
                                                     setup_options={})
                        else:
                            self.e.use_move_on(self.a, self.b, move, self.e.everyone)
                self.assertEqual(before, self.state())

    def test_cold_restore_rejects_a_choice_changed_to_non_setup_move(self):
        self.fixture()
        self.choose(BEAM)
        payload = json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False))
        choices = [node for node in payload['nodes'].values() if node.get('kind') == 'dict'
                   and all(isinstance(key, str) for key, value in node['items'])
                   and dict(node['items']).get('buff_id') == self.buff_id
                   and dict(node['items']).get('move_id') == BEAM]
        self.assertEqual(len(choices), 1)
        choices[0]['items'] = [[key, SETUP_FIX.TACKLE if key == 'move_id' else value]
                               for key, value in choices[0]['items']]
        with self.assertRaises(ValueError):
            CODEC.load_engine(self.r, payload)


if __name__ == '__main__':
    unittest.main()
