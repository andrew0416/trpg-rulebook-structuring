"""Actual item deployment uses the existing smoke field, stock and restore owners."""
from pathlib import Path
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_category2_body_modes as body_fixture
import test_category2_medicine_stock as stock_fixture
from engine import Engine, Rules
import common_checks as C
import consumption_execution as PAID
import smoke_balls as SMOKE
import smoke_regions as REGIONS
import state_codec as CODEC
import world_entities as WORLD

ROOT = Path(__file__).resolve().parents[1]


class Tests(unittest.TestCase):
    setUpClass = classmethod(body_fixture.Tests.setUpClass.__func__)
    setUp = body_fixture.Tests.setUp
    add = body_fixture.Tests.add
    pokemon = body_fixture.Tests.pokemon
    begin = body_fixture.Tests.begin
    held = stock_fixture.MedicineStockTests.held

    def ready(self, actor=None, source='item/연막탄'):
        actor = actor or self.a
        actor.spec['items'] = {uid: 4 for uid in SMOKE.SOURCES}
        self.begin(actor)
        return actor, source

    def use(self, actor=None, source='item/연막탄', center=(10, 5), event='actual-use', **options):
        return self.e.use_item(actor or self.a, source,
            aim={'center': center, 'event_id': event,
                 'reason': 'GM observed the actual Smoke Ball used at this center'}, **options)

    def snap(self):
        return deepcopy(([(x.entity_id, vars(x)) for x in self.e.everyone],
            self.e.zone_cells, self.e.zones, self.e.rng.getstate(), self.e.elapsed_seconds,
            self.e.log_lines, self.e.gm_prompts, getattr(self.e, '_physical_objects', {})),
            {id(self.r): self.r})

    def test_originals_quantity_and_actual_instance_for_both_actor_kinds_without_move_cost(self):
        from consumable_use import adapter_for, UseFamily
        self.assertEqual(adapter_for(SMOKE.SOURCES[0]).family, UseFamily.DEPLOYED)
        for source in SMOKE.SOURCES:
            for pokemon in (False, True):
                for physical in (False, True):
                    with self.subTest(source=source, pokemon=pokemon, physical=physical):
                        self.setUp()
                        actor, _ = self.ready(self.p if pokemon else self.a, source)
                        self.assertNotIn(SMOKE.MOVE, actor.spec.get('moves', []))
                        if physical:
                            self.held(actor, source, 'actual-smoke-ball')
                        before = deepcopy((actor.budget, actor.move_uses, actor._action_history,
                            actor.last_move, actor.last_target, self.e.rng.getstate(), self.e.elapsed_seconds))
                        out = self.use(actor, source, held_selection='actual-smoke-ball' if physical else None)
                        self.assertEqual(set(self.e.zone_cells), self.e.grid.ranged_blast((10, 5), 3))
                        self.assertEqual(set(self.e.zone_cells.values()), {-3})
                        self.assertEqual((actor.budget, actor.move_uses, actor._action_history,
                            actor.last_move, actor.last_target, self.e.rng.getstate(), self.e.elapsed_seconds), before)
                        self.assertEqual(actor.spec['items'][source], 4 if physical else 3)
                        self.assertEqual((out['authority']['action_cost'], out['authority']['range_limit']), (None, None))
                        receipt = PAID.validate(actor)[out['payment_id']]
                        self.assertEqual((receipt['outcome'], receipt['target_id']), ('applied', actor.entity_id))
                        self.assertEqual(receipt['results'], [{'kind': 'smoke_ball_use', 'id': out['id']}])
                        if physical:
                            self.assertEqual(self.e._physical_objects['actual-smoke-ball']['consumed'],
                                {'source': source, 'by_actor_id': actor.entity_id, 'at': self.e.elapsed_seconds})
                        SMOKE.validate_world(self.e)

    def test_actual_blast_three_map_edges_and_walls_use_native_geometry(self):
        for center, walls in (((0, 0), ()), ((5, 5), (((5, 5), (6, 5)),))):
            with self.subTest(center=center):
                self.setUp()
                self.ready()
                self.e.grid.walls = {tuple(sorted(wall)) for wall in walls}
                out = self.use(center=center)
                actual = self.e.grid.ranged_blast(center, 3)
                self.assertEqual(set(self.e.zone_cells), actual)
                self.assertEqual(out['cells'], [list(c) for c in sorted(actual)])
                self.assertIn(center, actual)
                self.assertLess(len(actual), 9)
        # The reviewed extracted cells say burst 3; original Blast 3 is explicit.
        self.assertEqual(self.r.item_effects(SMOKE.SOURCES[0])[0][0]['cells'], 'burst 3')
        self.assertEqual(out['authority']['geometry'], 'blast 3')

    def test_item_and_native_move_overlap_share_accuracy_removal_and_encounter_lifetime(self):
        import body_state as BODY
        self.ready()
        self.use(center=(5, 5))
        self.e.gm.set_move(self.a, SMOKE.MOVE, reason='learn actual Smokescreen for shared-owner test')
        self.begin(self.a)
        self.e.use_move_on(self.a, self.t, SMOKE.MOVE, self.e.everyone, aim=(5, 5))
        self.a.pos, self.t.pos = (4, 5), (7, 5)
        BODY.observe(self.e, self.t, [[0, 0], [-1, 0]], reason='actual body partly overlaps item smoke')
        self.assertEqual(self.e._prepare_accuracy_context(self.a, self.t, self.r.move('struggle'))['zone_pen'], -3)
        self.e.gm.set_move(self.a, 'move/날려버리기', reason='actual smoke-clearing move')
        self.a.pos, self.t.pos = (1, 5), (5, 5)
        BODY.observe(self.e, self.t, [[0, 0]], reason='actual ordinary footprint')
        cells = set(self.e.zone_cells)
        self.begin(self.a)
        self.e.use_move_on(self.a, self.t, 'move/날려버리기', self.e.everyone, aim=(5, 5))
        self.assertFalse(self.e.zone_cells)
        self.e.gm.set_move(self.a, 'move/안개제거', reason='actual smoke-clearing move')
        self.begin(self.a)
        self.e.use_move_on(self.a, self.t, 'move/안개제거', self.e.everyone)
        self.assertFalse(self.e.zone_cells)
        self.use(center=(10, 5), event='second-actual-use')
        self.e.end_of_turn(self.a)
        self.e.end_encounter(self.e.everyone, round_elapsed_seconds=0)
        self.assertFalse(self.e.zone_cells)
        self.assertFalse(self.e.zones)
        self.assertEqual(len(self.a.spec[SMOKE.KEY]), 2)
        SMOKE.validate_world(self.e)

    def test_missing_observation_or_map_is_pending_without_stock_action_or_rng(self):
        self.ready()
        for aim in (None, (18, 8)):
            before = self.snap()
            pending = self.e.use_item(self.a, SMOKE.SOURCES[0], aim=aim)
            self.assertIsInstance(pending, C.PendingDecision)
            self.assertEqual(self.snap(), before)
        self.e.grid = None
        before = self.snap()
        self.assertIsInstance(self.use(), C.PendingDecision)
        self.assertEqual(self.snap(), before)

    def test_wrong_actor_aim_stock_or_current_definition_rejects_before_mutation(self):
        self.ready()
        for options in ({'count': 2}, {'free': True}, {'fixed_accuracy': 20},
                        {'selected_move': SMOKE.MOVE}, {'held_selection': 'absent'}):
            before = self.snap()
            with self.assertRaises(ValueError):
                self.use(**options)
            self.assertEqual(self.snap(), before)
        for aim in ((20, 5), {'center': (5, 5), 'event_id': 'bad', 'reason': ''},
                    {'center': (True, 5), 'event_id': 'bad', 'reason': 'actual use'}):
            before = self.snap()
            with self.assertRaises(ValueError):
                self.e.use_item(self.a, SMOKE.SOURCES[0], aim=aim)
            self.assertEqual(self.snap(), before)
        foreign = deepcopy(self.a, {id(self.r): self.r})
        before = self.snap()
        with self.assertRaises(ValueError):
            self.use(foreign)
        self.assertEqual(self.snap(), before)
        before = self.snap()
        with self.assertRaises(ValueError):
            self.e.use_item(self.a, SMOKE.SOURCES[0], self.t,
                aim={'center': (5, 5), 'event_id': 'bad-target', 'reason': 'actual use'})
        self.assertEqual(self.snap(), before)
        for field in ('item_effects', 'move_mech'):
            native = getattr(self.r, field)
            def changed(source, native=native, field=field):
                value = deepcopy(native(source))
                if field == 'item_effects' and source in SMOKE.SOURCES:
                    value[0][0]['cells'] = 'burst 4'
                if field == 'move_mech' and source == SMOKE.MOVE:
                    value[0]['zone']['accuracy_penalty'] = -4
                return value
            before = self.snap()
            with patch.object(self.r, field, side_effect=changed):
                with self.assertRaises(ValueError):
                    self.use()
            self.assertEqual(self.snap(), before)
        self.a.spec['items'][SMOKE.SOURCES[0]] = 0
        before = self.snap()
        with self.assertRaises(ValueError):
            self.use()
        self.assertEqual(self.snap(), before)

    def test_failures_after_actual_production_or_payment_completion_roll_back_graph(self):
        self.ready()
        self.held(self.a, SMOKE.SOURCES[0], 'actual-smoke-ball')
        original = REGIONS.apply
        def fail_after_smoke(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('forced failure after native smoke production')
        for module, name, failure in ((REGIONS, 'apply', fail_after_smoke),
                                     (PAID, 'finish', RuntimeError('forced receipt failure'))):
            before = self.snap()
            with patch.object(module, name, side_effect=failure):
                with self.assertRaises(RuntimeError):
                    self.use(held_selection='actual-smoke-ball')
            self.assertEqual(self.snap(), before)
        self.use(held_selection='actual-smoke-ball')
        self.assertIn('consumed', self.e._physical_objects['actual-smoke-ball'])

    def test_gm_and_fresh_rules_json_restore_keep_actual_payment_and_never_recreate_cleared_smoke(self):
        self.ready()
        out = self.use()
        cells = set(self.e.zone_cells)
        self.e.gm.snapshot('actual-smoke-ball')
        self.e.end_of_turn(self.a)
        self.e.end_encounter(self.e.everyone, round_elapsed_seconds=0)
        self.assertFalse(self.e.zone_cells)
        self.e.gm.restore('actual-smoke-ball')
        self.assertIs(WORLD.actor_index(self.e)[self.a.entity_id], self.a)
        self.assertEqual(set(self.e.zone_cells), cells)
        payload = json.loads(json.dumps(self.e.export_state()))
        loaded = Engine.import_state(Rules(ROOT, ruleset='core'), payload)
        actor = WORLD.actor_index(loaded)[self.a.entity_id]
        self.assertEqual(actor.spec[SMOKE.KEY]['actual-use'], out)
        self.assertEqual(set(loaded.zone_cells), cells)
        SMOKE.validate_world(loaded)
        loaded.end_of_turn(actor)
        loaded.end_encounter(loaded.everyone, round_elapsed_seconds=0)
        before = deepcopy((actor.spec, loaded.zone_cells, loaded.rng.getstate(), loaded.log_lines))
        with self.assertRaisesRegex(ValueError, 'already observed'):
            SMOKE.observe_use(loaded, actor, (10, 5), event_id='actual-use', reason='duplicate event')
        self.assertEqual((actor.spec, loaded.zone_cells, loaded.rng.getstate(), loaded.log_lines), before)
        row = actor.spec[SMOKE.KEY]['actual-use']
        row['cells'].append([19, 9])
        with self.assertRaises(ValueError):
            SMOKE.validate_world(loaded)


class IntegratedHooks(unittest.TestCase):
    """Run only after root composes the three small hooks on stable shared code."""
    setUpClass = classmethod(Tests.setUpClass.__func__)
    setUp = Tests.setUp
    add = Tests.add
    pokemon = Tests.pokemon
    begin = Tests.begin
    ready = Tests.ready
    use = Tests.use

    def test_public_gm_native_move_and_restore_validation_use_actual_shared_hooks(self):
        self.ready()
        with patch.object(REGIONS, 'apply', wraps=REGIONS.apply) as shared:
            out = self.e.gm.observe_smoke_ball_use(self.a, (5, 5),
                event_id='gm-observed-use', reason='actual observed deployment')
            self.assertEqual(shared.call_count, 1)
            expected = self.e.grid.ranged_blast((5, 5), 3)
            self.assertEqual(set(self.e.zone_cells), expected)
            self.assertEqual(set(self.e.zone_cells.values()), {-3})
            REGIONS.clear(self.e)
            self.e.gm.set_move(self.a, SMOKE.MOVE, reason='native move shares field producer')
            self.e.use_move_on(self.a, self.t, SMOKE.MOVE, self.e.everyone, aim=(5, 5))
            self.assertEqual(shared.call_count, 2)
            self.assertEqual(set(self.e.zone_cells), expected)
            self.assertEqual(set(self.e.zone_cells.values()), {-3})
        original = deepcopy(self.a.spec[SMOKE.KEY]['gm-observed-use'])
        self.a.spec[SMOKE.KEY]['gm-observed-use']['authority']['geometry'] = 'burst 3'
        with self.assertRaises(CODEC.StateCodecError):
            self.e.export_state()
        self.a.spec[SMOKE.KEY]['gm-observed-use'] = original
        payment = PAID.validate(self.a)[out['payment_id']]
        payment['item_stock']['count'] = 2
        with self.assertRaises(CODEC.StateCodecError):
            self.e.export_state()
        payment['item_stock']['count'] = 1
        del self.a.spec[SMOKE.KEY]
        with self.assertRaises(CODEC.StateCodecError):
            self.e.export_state()
