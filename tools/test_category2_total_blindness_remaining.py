"""Actual native movement consumers still required by C07-166.

The shared payment, geometry, dispatch and restore owners keep their own tests.
These cases exercise the relative producer and its source-specific boundaries.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'), str(ROOT / 'tools')]

from engine import Combatant, Engine, Rules
from grid import Grid
import body_state as BODY
import burrow_tunnels as TUNNELS
import hazard_state as HAZARDS
import map_terrain as TERRAIN
import movement_actions as MOVEMENT
import relative_movement as RELATIVE
import stamina as STAMINA
import state_grants as GRANTS
import test_category2_vision_impairment as ACTORS


class RemainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def world(self, *, mode='land', pace='slowly', cause='total', placement='before_entry',
              vector=(1, 0), movement=6, kind='pokemon'):
        e = Engine(self.rules, seed=166)
        e.grid = Grid(24, 16)
        a = Combatant(self.rules, {
            'id': kind + '/relative-native', 'name': 'relative-native', 'kind': kind,
            'level': 20, 'size': '중형', 'types': ['노말'], 'stats': dict(ACTORS.STATS),
            'skills': {'곡예': 4, '육상': 5, '집중': 3},
            'movement': {'land': 6, mode: movement}, 'movement_basis': 'current',
            'moves': ['move/몸통박치기'], 'pos': (1, 3),
        })
        t = ACTORS.combatant(self.rules, 'relative-native-target', pos=(20, 12))
        a.side = 'players'; t.side = 'enemies'
        e.gm.add_combatant(a); e.gm.add_combatant(t)
        e.start_round(e.everyone); e.start_of_turn(a)
        e.observe_relative_directions(a, directions={'understood': vector},
            quickly_trip_placement=placement, reason='GM binds the actual understood direction')
        if cause == 'total':
            e.apply_status(a, '완전 실명', parameters={'cause': 'external'})
        elif cause == 'ordinary':
            e.apply_status(a, '실명', parameters={'cause': 'external'})
        d = {'direction': 'understood', 'distance': movement, 'pace': pace,
             'movement_id': 'native-relative', 'movement_mode': mode,
             'blindness_options': self.options() if cause != 'none' and
                 not (cause == 'total' and pace == 'quickly' and placement == 'before_entry') else None}
        if mode != 'land':
            d['native_options'] = {'reason_text': 'GM observes the native movement requirements'}
        if mode == 'burrow': d['native_options'].update(diggable=True, surface=False)
        if mode == 'teleport': d['native_options'].update(surface_contact=True)
        return e, a, t, d

    def options(self):
        return {'frequency': 'once_per_shift', 'reason': 'GM selects the inherited check repetition',
                'check_options': [{'fixed': [6, 6, 6, 6]}]}

    def fresh(self, e, a, t):
        restored = Engine.import_state(self.rules, json.loads(json.dumps(e.export_state())))
        index = {c.entity_id: c for c in restored.everyone}
        return restored, index[a.entity_id], index[t.entity_id]

    def public(self, result):
        self.assertEqual(set(result), {'movement_id', 'state', 'distance', 'tripped'})
        self.assertNotIn('position', json.dumps(result)); self.assertNotIn('altitude', json.dumps(result))
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_swim_paces_use_native_underwater_path_and_real_shift(self):
        for pace, expected in (('slowly', 3), ('quickly', 6)):
            with self.subTest(pace=pace):
                e, a, t, d = self.world(mode='swim', pace=pace)
                TERRAIN.observe(e, [(x, 3) for x in range(1, 9)], base='underwater', reason='actual submerged route')
                before = e.rng.getstate(); out = e.move_relative(a, **d)
                self.assertEqual((a.pos, out['distance']), ((1 + expected, 3), expected))
                self.assertEqual(a._action_history, ['shift']); self.assertEqual(a.budget['shift'], 0)
                self.assertEqual(e.rng.getstate(), before); self.public(out)
                self.fresh(e, a, t)

    def test_aerial_paces_use_actual_altitude_and_native_height_limits(self):
        for mode in ('sky', 'levitate'):
            for pace, expected in (('slowly', 3), ('quickly', 6)):
                with self.subTest(mode=mode, pace=pace):
                    e, a, t, d = self.world(mode=mode, pace=pace)
                    a.spec['_movement_altitude'] = 2; a.airborne = True
                    e.grid.rough.add((2, 3)); e.grid.slow.add((3, 3))
                    out = e.move_relative(a, **d)
                    self.assertEqual((a.pos, a.spec['_movement_altitude'], out['distance']), ((1 + expected, 3), 2, expected))
                    self.assertNotIn('넘어짐', a.conditions); self.assertEqual(a._action_history, ['shift'])
                    self.public(out); self.fresh(e, a, t)
        e, a, t, d = self.world(mode='levitate', pace='quickly', vector=(0, 0, 1), movement=6)
        d['distance'] = 4
        before = e.export_state()
        with self.assertRaisesRegex(ValueError, 'Levitate altitude'):
            e.move_relative(a, **d)
        self.assertEqual(e.export_state(), before)

    def test_relative_3d_requires_measured_mixed_geometry_without_coordinate_output(self):
        e, a, t, d = self.world(mode='sky', vector=(1, 0, 1))
        before = e.export_state()
        with self.assertRaisesRegex(ValueError, 'measured'):
            e.move_relative(a, **d)
        self.assertEqual(e.export_state(), before)
        d['native_options']['gm_step_distance'] = 2
        out = e.move_relative(a, **d)
        self.assertEqual((a.pos, a.spec['_movement_altitude'], out['distance']), ((2, 3), 1, 2))
        self.public(out)
        e, a, t = self.fresh(e, a, t); before = e.export_state()
        self.assertEqual(e.move_relative(a, **d), out); self.assertEqual(e.export_state(), before)

    def test_burrow_reuses_real_tunnel_and_surface_transfer(self):
        for pace, expected in (('slowly', 3), ('quickly', 6)):
            with self.subTest(pace=pace):
                e, a, t, d = self.world(mode='burrow', pace=pace)
                TERRAIN.observe(e, [(x, 3) for x in range(2, 9)], base='earth', reason='actual diggable ground')
                out = e.move_relative(a, **d)
                self.assertEqual((a.pos, out['distance']), ((1 + expected, 3), expected))
                self.assertTrue(a.spec['_burrow']['underground']); self.assertEqual(a._action_history, ['shift'])
                self.assertTrue(e._burrow_tunnels)
                self.assertTrue(all(r['passage']['offsets'] for r in e._burrow_tunnels))
                self.assertTrue(TUNNELS.can_pass(e, a, a.pos)); self.public(out); self.fresh(e, a, t)
        e, a, t, d = self.world(mode='burrow', movement=4)
        d['native_options']['surface'] = True
        TERRAIN.observe(e, [(2, 3)], base='earth', reason='actual earth before the surface exit')
        out = e.move_relative(a, **d)
        self.assertEqual(a.pos, (3, 3)); self.assertFalse(a.spec['_burrow']['underground'])
        self.assertEqual(out['distance'], 2); self.fresh(e, a, t)

    def test_teleport_reuses_los_surface_once_round_and_no_sprint_extension(self):
        for pace, expected in (('slowly', 3), ('quickly', 6)):
            with self.subTest(pace=pace):
                e, a, t, d = self.world(mode='teleport', pace=pace)
                # This pending real Sprint was paid by its existing producer.
                e.sprint(a, source_policy='ch06_once'); d['distance'] = 12
                out = e.move_relative(a, **d)
                self.assertEqual((a.pos, out['distance']), ((1 + expected, 3), expected))
                self.assertEqual(a.spec['_teleport']['used_round'], e.round_no)
                self.assertEqual(a._action_history, ['standard', 'shift']); self.public(out)
                e, a, t = self.fresh(e, a, t)
                d2 = dict(d, movement_id='second-relative-teleport'); before = e.export_state()
                with self.assertRaisesRegex(ValueError, 'once per combat round'):
                    e.move_relative(a, **d2)
                self.assertEqual(e.export_state(), before)
        e, a, t, d = self.world(mode='teleport', movement=4, vector=(1, 1))
        a._diagonal_steps = 1
        out = e.move_relative(a, **d)
        self.assertEqual((a.pos, out['distance']), ((2, 4), 1))
        self.assertEqual(a._diagonal_steps, 1); self.fresh(e, a, t)
        e, a, t, d = self.world(mode='teleport', pace='quickly')
        e.grid.blocking.add((3, 3)); before = e.export_state()
        with self.assertRaisesRegex(ValueError, 'line of sight'):
            e.move_relative(a, **d)
        self.assertEqual(e.export_state(), before)
        e, a, t, d = self.world(mode='teleport')
        d['native_options']['surface_contact'] = False; before = e.export_state()
        with self.assertRaisesRegex(ValueError, 'Sky or Levitate'):
            e.move_relative(a, **d)
        self.assertEqual(e.export_state(), before)

    def test_quickly_full_body_blocking_rough_slow_attempts(self):
        for mode in ('land', 'swim', 'burrow'):
            for terrain in ('blocking', 'rough', 'slow'):
                with self.subTest(mode=mode, terrain=terrain):
                    e, a, t, d = self.world(mode=mode, pace='quickly')
                    BODY.observe(e, a, [(0, 0), (0, 1)], reason='actual two-cell body')
                    if mode == 'swim':
                        TERRAIN.observe(e, [(x, y) for x in range(1, 9) for y in (3, 4)],
                            base='underwater', reason='actual submerged whole-body route')
                    if mode == 'burrow':
                        TERRAIN.observe(e, [(x, y) for x in range(2, 9) for y in (3, 4)],
                            base='earth', reason='actual whole-body diggable ground')
                    getattr(e.grid, terrain).add((3, 4)); rng = e.rng.getstate()
                    out = e.move_relative(a, **d)
                    self.assertEqual(a.pos, (2, 3)); self.assertTrue(out['tripped'])
                    self.assertEqual(out['distance'], 1); self.assertEqual(a._action_history, ['shift'])
                    self.assertEqual(e.rng.getstate(), rng); self.fresh(e, a, t)
        for terrain in ('blocking', 'rough', 'slow'):
            with self.subTest(mode='burrow-surface', terrain=terrain):
                e, a, t, d = self.world(mode='burrow', pace='quickly')
                BODY.observe(e, a, [(0, 0), (0, 1)], reason='actual two-cell body at a surface exit')
                d['distance'] = 2; d['native_options']['surface'] = True
                TERRAIN.observe(e, [(2, 3), (2, 4)], base='earth', reason='actual earth before surface exit')
                getattr(e.grid, terrain).add((3, 4))
                out = e.move_relative(a, **d)
                self.assertEqual((a.pos, out['distance'], out['tripped']), ((2, 3), 1, True))
                self.fresh(e, a, t)

    def test_transfer_entry_dispatch_and_completed_replay_restore(self):
        for mode in ('burrow', 'teleport'):
            with self.subTest(mode=mode):
                e, a, t, d = self.world(mode=mode, movement=4)
                if mode == 'burrow': d['native_options']['surface'] = True
                HAZARDS.place_legacy(e, (3, 3), 'actual external entry affliction',
                    effects=[{'type': 'apply_status', 'status': '마비'}])
                log_start = len(e.log_lines)
                external_declaration = json.loads(json.dumps(d))
                out = e.move_relative(a, **external_declaration)
                self.assertIn('마비', a.conditions); self.assertNotIn((3, 3), e.hazards)
                self.assertEqual(a._action_history, ['shift']); self.public(out)
                native_logs = [line for line in e.log_lines[log_start:]
                    if '지중 이동 ' in line or '순간이동 ' in line]
                self.assertTrue(native_logs)
                self.assertNotIn(str(a.pos), json.dumps(native_logs, ensure_ascii=False))
                e, a, t = self.fresh(e, a, t); before = e.export_state()
                self.assertEqual(e.move_relative(a, **external_declaration), out); self.assertEqual(e.export_state(), before)
                a.spec[RELATIVE.KEY][d['movement_id']]['cells'][-1]['plan']['parameters']['reason_text'] = 'replaced transfer'
                with self.assertRaisesRegex(ValueError, 'native transfer plan'):
                    e.move_relative(a, **d)

    def test_absolute_nonland_producers_cannot_bypass_relative_payment(self):
        for mode in ('swim', 'sky', 'burrow', 'teleport'):
            with self.subTest(mode=mode):
                e, a, t, d = self.world(mode=mode)
                if mode == 'swim':
                    TERRAIN.observe(e, [(x, y) for x in range(24) for y in range(16)],
                        base='underwater', reason='actual submerged route for the native producer')
                before = e.export_state()
                with self.assertRaisesRegex(ValueError, 'relative'):
                    if mode == 'swim':
                        e.approach(a, t, movement_mode='swim')
                    elif mode == 'sky':
                        e.aerial_move(a, (3, 3), mode='sky', altitude=0, reason_text='valid native absolute path')
                    elif mode == 'burrow':
                        e.burrow_move(a, [(1, 3), (2, 3), (3, 3)], diggable=True, surface=True,
                            reason_text='valid native absolute tunnel')
                    else:
                        e.teleport(a, (3, 3), surface_contact=True, reason_text='valid native absolute transfer')
                self.assertEqual(e.export_state(), before); self.assertNotIn(RELATIVE.KEY, a.spec)

    def test_actual_entry_new_impairment_requires_then_accepts_resumed_policy(self):
        for status in ('실명', '완전 실명'):
            with self.subTest(status=status):
                e, a, t, d = self.world(cause='none', placement='enter_passable')
                e.grid.rough.add((2, 3))
                HAZARDS.place_legacy(e, (2, 3), 'actual entry obscures sight',
                    effects=[{'type': 'apply_status', 'status': status}])
                with self.assertRaisesRegex(ValueError, 'traversal check policy'):
                    e.move_relative(a, **d)
                self.assertEqual(a.pos, (2, 3)); self.assertEqual(a._action_history, ['shift'])
                self.assertIn('완전-실명' if status == '완전 실명' else status, a.conditions)
                self.assertNotIn((2, 3), e.hazards)
                e, a, t = self.fresh(e, a, t)
                external_resume = json.loads(json.dumps(dict(d, resumed_blindness_options=self.options())))
                out = e.move_relative(a, **external_resume)
                self.assertEqual(out['state'], 'complete'); self.assertEqual(out['distance'], 6)
                self.assertEqual(len(a.spec[RELATIVE.KEY][d['movement_id']]['checks']), 1)
                self.assertEqual(a._action_history, ['shift']); self.public(out); self.fresh(e, a, t)
                before = e.export_state(); changed = dict(self.options(), frequency='each_hazard_cell')
                with self.assertRaisesRegex(ValueError, 'replace the resumed'):
                    e.move_relative(a, **d, resumed_blindness_options=changed)
                self.assertEqual(e.export_state(), before)

    def test_pending_total_to_ordinary_updates_policy_without_repayment_or_reroll(self):
        e, a, t, d = self.world(pace='quickly', kind='trainer')
        enemy = ACTORS.combatant(self.rules, 'new-vision-aoo', pos=(1, 4))
        enemy.side = 'enemies'; e.gm.add_combatant(enemy)
        def acquire(engine, actor):
            actor.spec.setdefault('edges', []).append(STAMINA.SOURCE)
            actor.spec['skills'] = {'Athletics': 5, 'Acrobatics': 4, 'Combat': 6}
        GRANTS.transition(e, a, acquire); e.grid.rough.add((4, 3)); e.rng.seed(5)
        out = e.move_relative(a, **d)
        self.assertEqual(out['state'], 'pending'); self.assertEqual(a.pos, (2, 3))
        action = next(row for row in e._native_action_resolutions.values()
            if any(trigger['actor'] is a and trigger['source'] == STAMINA.SOURCE for trigger in row['triggers']))
        e.cure_status(a, '완전 실명'); e.apply_status(a, '실명', parameters={'cause': 'external'})
        e, a, t = self.fresh(e, a, t); e.resolve_stamina(a, action['id'], skill='육상')
        with self.assertRaisesRegex(ValueError, 'traversal check policy'):
            e.move_relative(a, **d)
        completed = len(e._move_completions)
        out = e.move_relative(a, **d, resumed_blindness_options=self.options())
        self.assertEqual(out['state'], 'complete'); self.assertEqual(a.pos, (7, 3))
        self.assertEqual(a._action_history, ['shift']); self.assertEqual(len(e._move_completions), completed)
        self.assertEqual(len(a.spec[RELATIVE.KEY][d['movement_id']]['checks']), 1)
        self.assertFalse(out['tripped']); self.public(out); self.fresh(e, a, t)


if __name__ == '__main__': unittest.main()
