"""Real digger-to-walker passage, size, terrain, collision and persistence."""
from pathlib import Path
import sys
import json
from copy import deepcopy
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / 'output/ruleunits.jsonl').is_file():
    sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_reuse_partial_terrain as BASE
from grid import Grid
import burrow_tunnels as TUNNELS
import map_terrain as TERRAIN
import body_state as BODY
import state_grants as G
from state_codec import dump_engine, load_engine, StateCodecError


class PassageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.Tests.setUpClass()
        cls.r = BASE.Tests.r

    def setUp(self):
        BASE.Tests.setUp(self)
        self.e.grid = Grid(7, 2)
        self.a.spec['size'] = self.b.spec['size'] = '중형'
        self.e.observe_map_terrain([(x, 0) for x in range(1, 4)], base='earth', reason='solid corridor with no old tunnel')
        self.e.gm.set_movement_capabilities(self.b, {'land': 2, 'burrow': 0, 'swim': 0}, basis='current', reason='actual walker without digging or swimming')

    def dig(self):
        result = self.e.burrow_move(self.a, [(x, 0) for x in range(5)], diggable=True, surface=True, reason_text='actual dug corridor with two surface mouths')
        self.a.pos = (6, 0)
        self.b.pos = (0, 0)
        self.e.end_of_turn(self.a)
        self.e.start_of_turn(self.b, initiative_count=10)
        return result

    def snapshot(self):
        return deepcopy((self.e.export_state(), self.e.rng.getstate()))

    def test_actual_dig_allows_native_walking_and_surface_exit_without_burrow(self):
        self.dig()
        self.assertEqual(self.e._burrow_tunnels[0]['passage']['entries'], [(0, 0), (4, 0)])
        result = self.e.approach(self.b, self.a, movement_mode='land')
        self.assertEqual((self.b.pos, result['distance'], self.b.budget['shift']), ((2, 0), 2, 0))
        self.assertTrue(self.b.spec['_burrow']['underground'])
        self.assertFalse(TERRAIN.can_travel(self.e, self.b, (2, 1), '육상'))
        self.e.gm.set_movement_capabilities(self.b, {'land': 6, 'burrow': 0, 'swim': 0}, basis='current', reason='actual next walking allowance')
        self.e.end_of_turn(self.b)
        self.e.end_round()
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.b, initiative_count=10)
        self.e.approach(self.b, self.a, movement_mode='land')
        self.assertEqual(self.b.pos, (5, 0))
        self.assertFalse(self.b.spec['_burrow']['underground'])
        self.assertEqual(len(self.e._burrow_tunnels), 1)

    def test_small_tunnel_rejects_medium_body_even_with_same_map_width(self):
        self.a.spec['size'] = '소형'
        self.dig()
        before = self.snapshot()
        self.assertFalse(TERRAIN.can_travel(self.e, self.b, (1, 0), '육상'))
        self.assertEqual(self.snapshot(), before)
        self.b.spec['size'] = '소형'
        self.assertTrue(TERRAIN.can_travel(self.e, self.b, (1, 0), '육상'))
        self.e.approach(self.b, self.a, movement_mode='land')
        self.assertEqual(self.b.pos, (2, 0))

    def test_observed_wide_body_needs_full_passage_and_entrance(self):
        self.dig()
        BODY.observe(self.e, self.b, [(0, 0), (0, 1)], reason='actual long sideways body')
        self.assertFalse(TERRAIN.can_travel(self.e, self.b, (1, 0), '육상'))
        self.b.spec.pop('footprint')
        self.b.pos = (2, 1)
        self.assertFalse(TERRAIN.can_travel(self.e, self.b, (2, 0), '육상'))

    def test_untouched_earth_and_legacy_history_do_not_grant_walking(self):
        self.assertFalse(TERRAIN.can_travel(self.e, self.b, (1, 0), '육상'))
        self.dig()
        self.e._burrow_tunnels[0].pop('passage')
        self.assertFalse(TERRAIN.can_travel(self.e, self.b, (1, 0), '육상'))
        self.assertTrue(TERRAIN.can_travel(self.e, self.a, (1, 0), 'burrow', underground=True))

    def test_actual_subterranean_collision_and_surface_actor_are_distinct(self):
        self.dig()
        self.a.pos = (1, 0)
        self.a.spec['_burrow']['underground'] = True
        self.assertFalse(BODY.can_place(self.e, self.b, (1, 0), origin=self.b.pos))
        self.a.spec['_burrow']['underground'] = False
        self.assertTrue(BODY.can_place(self.e, self.b, (1, 0), origin=self.b.pos))

    def test_json_and_gm_restore_preserve_creation_body_mouths_and_walking_plane(self):
        self.dig()
        self.e.approach(self.b, self.a, movement_mode='land')
        self.e.gm.snapshot('inside')
        gm_engine = self.e
        self.e = load_engine(self.r, json.loads(json.dumps(dump_engine(self.e))))
        self.a, self.b, self.c = self.e.everyone
        self.assertTrue(self.b.spec['_burrow']['via_tunnel'])
        self.assertEqual(self.e._burrow_tunnels[0]['body_size'], '중형')
        self.e = gm_engine
        self.e.gm.restore('inside')
        self.a, self.b, self.c = self.e.everyone
        self.assertTrue(TERRAIN.can_travel(self.e, self.b, (3, 0), '육상'))
        self.assertTrue(self.b.spec['_burrow']['underground'])

    def test_late_dig_failure_rolls_back_tunnel_body_rng_and_action(self):
        before = self.snapshot()
        original = TUNNELS.record
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            args[0].rng.random()
            raise RuntimeError('late tunnel failure')
        with patch.object(TUNNELS, 'record', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'late tunnel'):
                self.e.burrow_move(self.a, [(0, 0), (1, 0)], diggable=True, surface=False, reason_text='actual failed dig')
        self.assertEqual(self.snapshot(), before)

    def test_bad_tunnel_geometry_rejects_world_and_restore_atomically(self):
        self.dig()
        before = self.snapshot()
        def invalid(e, a):
            e._burrow_tunnels[0]['passage']['entries'] = [(2, 0)]
            a.hp -= 3
        with self.assertRaises(ValueError):
            G.transition(self.e, self.a, invalid)
        self.assertEqual(self.snapshot(), before)
        self.e._burrow_tunnels[0]['passage']['offsets'] = [(0, 0), (99, 99)]
        with self.assertRaises(StateCodecError):
            dump_engine(self.e)

    def test_other_map_with_same_coordinates_does_not_inherit_old_tunnel(self):
        self.dig()
        old_map = self.e.grid
        self.e.grid = Grid(7, 2)
        self.e.observe_map_terrain([(1, 0), (2, 0), (3, 0)], base='earth', reason='different actual map')
        self.assertFalse(TERRAIN.can_travel(self.e, self.b, (1, 0), '육상'))
        self.e.grid = old_map
        self.assertTrue(TERRAIN.can_travel(self.e, self.b, (1, 0), '육상'))


if __name__ == '__main__':
    unittest.main()
