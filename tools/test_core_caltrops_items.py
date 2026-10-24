"""C09-080 actual item stock -> native Hazard geometry/state/entry consumers."""
from copy import deepcopy
from pathlib import Path
import json
import unittest
from unittest.mock import patch

from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from grid import Grid
import caltrops_items as CALTROPS
import hazard_state as HAZARDS
import effects_ext as EXT
import condition_instances as CONDITIONS
import item_stock as STOCK
import heavy_injury_adapter as HEAVY
import consumption_execution as EXECUTION
import test_category2_medicine_stock as STOCK_FIX

ROOT = Path(__file__).resolve().parents[1]
CELLS = ((3, 1), (3, 2), (3, 3), (4, 1), (4, 2), (4, 3), (5, 1), (5, 2))
TOOLS = ('item/마름쇠', 'item/독-마름쇠')


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='core')

    held = STOCK_FIX.MedicineStockTests.held

    def world(self, kind='trainer'):
        self.e = Engine(self.r, seed=9080)
        self.e.grid = Grid(16, 16)
        spec = (build_trainer(self.r, 'caltrops-user', 20,
                dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
                extra={'items': dict.fromkeys(TOOLS, 4)}) if kind == 'trainer'
                else build_pokemon(self.r, '피카츄', 30, moves=[], abilities=[],
                    side='party', extra={'items': dict.fromkeys(TOOLS, 4)}))
        self.a = Combatant(self.r, spec)
        self.t = Combatant(self.r, build_pokemon(self.r, '파이리', 25,
            moves=[], abilities=[], side='wild'))
        self.a.pos, self.t.pos = (2, 2), (12, 12)
        for actor in (self.a, self.t):
            self.e.gm.add_combatant(actor)
        self.begin(self.a)

    def begin(self, actor):
        if self.e._active_turn_actor is not None:
            self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor, initiative_count=20)

    def use(self, item=TOOLS[0], **options):
        return self.e.use_item(self.a, item, aim=options.pop('aim', CELLS), **options)

    def snap(self):
        return deepcopy((self.e.export_state(), self.e.rng.getstate(), self.e.log_lines))

    def test_both_actor_kinds_and_tools_use_native_move_frequency_without_learning(self):
        for kind in ('trainer', 'pokemon'):
            for item in TOOLS:
                with self.subTest(kind=kind, item=item):
                    self.world(kind)
                    self.assertEqual(self.r.item_effects(item)[1]['price'], 500)
                    before = deepcopy((self.a.moves, self.a.spec['moves'], self.a.move_uses))
                    result = self.use(item, accepted=False)
                    self.assertEqual(result['move_id'], CALTROPS.SOURCES[item][0])
                    self.assertEqual(result['payment']['kind'], 'quantity')
                    self.assertEqual(self.a.spec['items'][item], 3)
                    self.assertEqual(self.a.budget['standard'], 0)
                    self.assertEqual((self.a.moves, self.a.spec['moves']), before[:2])
                    self.assertEqual(self.a.move_uses[result['move_id']], 1)
                    completion = self.e._move_completions[result['move_completion']]
                    self.assertEqual((completion['activation'], completion['phase']), ('empty_area_field', 'complete'))
                    receipt = list(self.a.spec[EXECUTION.KEY].values())[-1]
                    self.assertEqual(receipt['outcome'], 'applied')
                    self.assertIn({'kind': 'move_completion', 'id': result['move_completion']}, receipt['results'])
                    instances = [row for env in self.e.hazards.values() for row in env['instances']]
                    self.assertEqual(len(instances), 8)
                    self.assertEqual({row['source_id'] for row in instances}, {result['move_id']})
                    self.assertEqual({row['owner_actor_id'] for row in instances}, {self.a.entity_id})
                    self.assertEqual(self.use(item), (0, 0))
                    self.assertEqual(self.a.spec['items'][item], 3)
                    self.begin(self.a)
                    if item == TOOLS[1]:
                        self.assertEqual(self.use(item), (0, 0))
                        self.assertEqual(self.a.budget['standard'], 1)
                        self.assertEqual(self.a.spec['items'][item], 3)
                        self.begin(self.a)
                    self.use(item)
                    self.assertEqual(self.a.spec['items'][item], 2)
                    self.assertEqual(self.a.move_uses[result['move_id']], 2)
                    self.assertEqual((self.a.moves, self.a.spec['moves']), before[:2])
                    self.assertEqual(len(self.e.hazards[CELLS[0]]['instances']), 2)

    def test_exact_physical_stock_and_hazard_state_survive_both_restore_paths(self):
        for item in TOOLS:
            with self.subTest(item=item):
                self.world('pokemon')
                self.held(self.a, item, 'caltrops-body')
                result = self.use(item, held_selection='caltrops-body')
                self.assertEqual(result['payment']['instance_id'], 'caltrops-body')
                self.assertIn('consumed', self.e._physical_objects['caltrops-body'])
                self.assertEqual(self.a.spec['items'][item], 4)
                self.e.gm.snapshot('caltrops-used')
                self.e.gm.restore('caltrops-used')
                restored = Engine.import_state(self.r, json.loads(json.dumps(self.e.export_state())))
                HAZARDS.validate_world(restored)
                self.assertEqual(restored.hazards, self.e.hazards)
                self.assertIn('consumed', restored._physical_objects['caltrops-body'])
                self.begin(self.a)
                before = self.snap()
                with self.assertRaises(ValueError):
                    self.use(item, held_selection='caltrops-body')
                self.assertEqual(self.snap(), before)

    def test_item_installation_is_consumed_by_actual_movement_and_native_toxic_layers(self):
        self.world()
        self.use()
        self.a.pos, self.t.pos = (4, 1), (2, 1)
        self.e.grid.blocking.update(((3, 0), (3, 2)))
        self.begin(self.t)
        before = self.t.hp
        self.e.approach(self.t, self.a)
        self.assertEqual(self.t.pos, (3, 1))
        self.assertEqual(before - self.t.hp, self.t.max_hp // 10)
        self.assertIn('둔화', self.t.conditions)

        self.world()
        self.use(TOOLS[1])
        self.begin(self.a)
        self.begin(self.a)
        self.use(TOOLS[1])
        EXT.on_enter_cell(self.e, self.t, CELLS[0])
        self.assertEqual(CONDITIONS.records(self.t, '독')[0]['effect']['variant'], '맹독')
        poison = Combatant(self.r, build_pokemon(self.r, '이상해씨', 20,
            moves=[], abilities=[], side='wild'))
        poison.pos = (11, 11)
        self.e.gm.add_combatant(poison)
        EXT.on_enter_cell(self.e, poison, CELLS[0])
        self.assertNotIn(CELLS[0], self.e.hazards)

    def test_invalid_options_geometry_stock_and_source_reject_before_any_cost_or_rng(self):
        self.world()
        invalid = [dict(free=True), dict(count=2), dict(selected_move='move/독압정'),
            dict(aim=None), dict(aim=CELLS[:-1]), dict(aim=(CELLS[0],) * 8),
            dict(aim=CELLS[:-1] + ((15, 15),)), dict(fixed_accuracy=20),
            dict(duration_minutes=1)]
        for options in invalid:
            with self.subTest(options=options):
                before = self.snap()
                with self.assertRaises(ValueError):
                    self.use(**options)
                self.assertEqual(self.snap(), before)
        self.a.spec['items'][TOOLS[0]] = 0
        before = self.snap()
        with self.assertRaises(ValueError):
            self.use()
        self.assertEqual(self.snap(), before)
        self.a.spec['items'][TOOLS[0]] = 4
        original = self.r.move_mech
        def wrong_source(move_id):
            declaration, confidence = original(move_id)
            return dict(declaration, effects_exec=[]), confidence
        before = self.snap()
        with patch.object(self.r, 'move_mech', side_effect=wrong_source):
            with self.assertRaisesRegex(ValueError, 'native field producer'):
                self.use()
        self.assertEqual(self.snap(), before)

    def test_native_disabled_and_suppression_keep_tool_action_and_field_unspent(self):
        for condition, item, parameters in (
                ('사슬묶기', TOOLS[0], {'move_id': 'move/압정뿌리기'}),
                ('억압', TOOLS[1], None)):
            with self.subTest(condition=condition):
                self.world()
                self.e.gm.add_condition(self.a, condition, reason='observed actual Move restriction',
                    **({'parameters': parameters} if parameters else {}))
                before = deepcopy((self.a.budget, self.a.spec['items'], self.a.move_uses,
                    self.e.hazards, self.e.rng.getstate()))
                self.assertEqual(self.use(item), (0, 0))
                self.assertEqual((self.a.budget, self.a.spec['items'], self.a.move_uses,
                    self.e.hazards, self.e.rng.getstate()), before)
                self.e.cure_status(self.a, condition)
                self.assertEqual(self.use(item)['move_id'], CALTROPS.SOURCES[item][0])

    def test_native_heavy_pending_keeps_actual_activation_and_consumed_tool(self):
        for physical in (False, True):
            with self.subTest(physical=physical):
                self.world()
                options = {}
                if physical:
                    self.held(self.a, TOOLS[0], 'heavy-caltrops')
                    options['held_selection'] = 'heavy-caltrops'
                self.a.injuries = 5
                with self.assertRaises(HEAVY.HeavyPending) as raised:
                    self.use(**options)
                event_id = raised.exception.event_id
                self.assertEqual(self.e._heavy_pending, event_id)
                self.assertEqual(self.a.budget['standard'], 0)
                self.assertEqual(self.a.spec['items'][TOOLS[0]], 4 if physical else 3)
                if physical:
                    self.assertIn('consumed', self.e._physical_objects['heavy-caltrops'])
                self.assertEqual(self.a.move_uses['move/압정뿌리기'], 1)
                self.assertFalse(self.e.hazards)
                self.assertEqual(self.e._heavy_events[event_id]['status'], 'pending')
                receipt = list(self.a.spec[EXECUTION.KEY].values())[-1]
                self.assertEqual(receipt['outcome'], 'paid')
                self.assertIn({'kind': 'heavy_event', 'id': event_id}, receipt['results'])
                restored = Engine.import_state(self.r, json.loads(json.dumps(self.e.export_state())))
                self.assertEqual(restored._heavy_pending, event_id)
                user = next(c for c in restored.everyone if c.entity_id == self.a.entity_id)
                self.assertEqual(user.spec['items'][TOOLS[0]], 4 if physical else 3)

    def test_payment_and_post_install_failure_roll_back_standard_stock_body_and_field(self):
        for physical in (False, True):
            for failure in ('payment', 'installation'):
                with self.subTest(physical=physical, failure=failure):
                    self.world()
                    options = {}
                    if physical:
                        self.held(self.a, TOOLS[0], 'atomic-caltrops')
                        options['held_selection'] = 'atomic-caltrops'
                    module, method = (STOCK, '_debit') if failure == 'payment' else (HAZARDS, 'install')
                    original = getattr(module, method)
                    def fail(*args, **kw):
                        original(*args, **kw)
                        args[0].rng.random()
                        raise ValueError('injected Caltrops failure')
                    before = self.snap()
                    with patch.object(module, method, side_effect=fail):
                        with self.assertRaises(ValueError):
                            self.use(**options)
                    self.assertEqual(self.snap(), before)


if __name__ == '__main__':
    unittest.main()
