"""실제 연막 기술의 영역·명중 소비·제거·종료·저장 복원 검사."""
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from engine import Engine, Combatant
from grid import Grid
import test_category2_csv_item_transfers as _fixture_test_category2_csv_item_transfers
import world_entities as WORLD


class SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture_test_category2_csv_item_transfers.Tests.setUpClass()
        cls.fixtures = _fixture_test_category2_csv_item_transfers.Tests()

    def fixture(self):
        e, a, b, _ = self.fixtures.fixture('연막', held=(None, None))
        e.grid = Grid(20, 20)
        a.pos, b.pos = (1, 5), (5, 5)
        a.side, b.side = 'party', 'wild'
        b.spec['weight_class'] = 4
        return e, a, b

    def smoke(self, e, a, b, aim=(5, 5)):
        e.use_move_on(a, b, 'move/연막', e.everyone, aim=aim)
        self.assertEqual(a.move_uses['move/연막'], 1)
        return e.grid.ranged_blast(aim, 3)

    def test_empty_aim_creates_one_exact_region_without_approaching_primary(self):
        e, a, b = self.fixture()
        b.pos = (15, 15)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        cells = self.smoke(e, a, b)
        self.assertEqual(set(e.zone_cells), cells)
        self.assertEqual(set(e.zone_cells.values()), {-3})
        self.assertEqual((a.pos, b.pos), ((1, 5), (15, 15)))
        self.assertEqual(a.budget['standard'], 0)
        self.assertFalse(e.gm_prompts)

    def test_invalid_aim_fails_before_cost_rng_and_region_mutation(self):
        e, a, b = self.fixture()
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        before = deepcopy((a.budget, a.move_uses, e.zone_cells, a.pos, e.rng.getstate()))
        with self.assertRaisesRegex(ValueError, 'outside selected ranged area origin'):
            e.use_move_on(a, b, 'move/연막', e.everyone, aim=(15, 15))
        self.assertEqual((a.budget, a.move_uses, e.zone_cells, a.pos, e.rng.getstate()), before)

    def test_accuracy_incoming_outgoing_overlap_and_leaving_use_native_consumer(self):
        e, a, b = self.fixture()
        self.smoke(e, a, b)
        move = e.r.move('struggle')
        for origin, target, penalty in [((1, 5), (5, 5), -3),
                                        ((5, 5), (8, 5), -3),
                                        ((4, 5), (6, 5), -3),
                                        ((8, 5), (9, 5), 0)]:
            a.pos, b.pos = origin, target
            plan = e._prepare_accuracy_context(a, b, move, 0)
            self.assertEqual(plan['zone_pen'], penalty)
            e.use_move(a, b, 'struggle', set_damage=True)
        self.assertFalse(e.gm_prompts)

    def test_defog_clears_actual_smoke_and_whirlwind_preserves_outside_line(self):
        for removal in ('move/안개제거', 'move/날려버리기'):
            with self.subTest(removal=removal):
                e, a, b = self.fixture()
                cells = self.smoke(e, a, b)
                e.use_move_on(a, b, removal, e.everyone, **({'aim': (5, 5)} if removal.endswith('날려버리기') else {}))
                if removal.endswith('안개제거'):
                    self.assertFalse(e.zone_cells)
                else:
                    line = e.grid.line((1, 5), (1, 0), 6)
                    self.assertEqual(set(e.zone_cells), cells - line)
                    row = next(row for row in reversed(list(e._move_completions.values()))
                               if row['move_id'] == removal)
                    self.assertEqual([target.entity_id for target in row['targets']], [b.entity_id])
                    self.assertEqual(set(row['results']), {b.entity_id})
                    receipt_types = [e._effect_dispatch_receipts[token]['effect']['type']
                                     for token in row['effects']]
                    self.assertEqual(receipt_types.count('destroy_hazards'), 1)
                    self.assertEqual(receipt_types.count('clear_field'), 1)
                self.assertFalse(e.gm_prompts)
                self.assertFalse(e._effect_pending if hasattr(e, '_effect_pending') else [])

    def test_gm_codec_then_encounter_boundary_clears_and_keeps_live_actors(self):
        e, a, b = self.fixture()
        cells = self.smoke(e, a, b)
        e.gm.snapshot('smoke')
        e.end_encounter()
        self.assertFalse(e.zone_cells)
        e.gm.restore('smoke')
        self.assertEqual(set(e.zone_cells), cells)
        self.assertIs(WORLD.actor_index(e)[a.entity_id], a)
        loaded = Engine.import_state(e.r, json.loads(json.dumps(e.export_state())))
        self.assertEqual(set(loaded.zone_cells), cells)
        loaded.end_encounter()
        self.assertFalse(loaded.zone_cells)
        self.assertFalse(loaded.zones)
        self.assertTrue(loaded.validate_state()['valid'], loaded.validate_state()['issues'])

    def test_nogrid_target_zone_affects_incoming_and_expires(self):
        e, a, b = self.fixture()
        e.grid = None
        e.use_move(a, b, 'move/연막')
        self.assertEqual(e.zones, {b.entity_id: -3})
        self.assertEqual(e._prepare_accuracy_context(a, b, e.r.move('struggle'), 0)['zone_pen'], -3)
        e.end_encounter()
        self.assertFalse(e.zones)

    def test_nogrid_smoke_does_not_leak_to_a_duplicate_display_name(self):
        e, a, b = self.fixture()
        e.grid = None
        b.name = '같은 표시 이름'
        spec = dict(deepcopy(b.spec), id='unexposed-actor', name=b.name)
        other = Combatant(e.r, spec)
        e.everyone.append(other)
        e.use_move(a, b, 'move/연막')
        move = e.r.move('struggle')
        self.assertEqual(e._prepare_accuracy_context(a, other, move)['zone_pen'], 0)
        self.assertEqual(e._prepare_accuracy_context(a, b, move)['zone_pen'], -3)
        self.assertEqual(e._prepare_accuracy_context(b, other, move)['zone_pen'], -3)
        self.assertEqual(e.zones, {b.entity_id: -3})
        loaded = Engine.import_state(e.r, json.loads(json.dumps(e.export_state())))
        index = WORLD.actor_index(loaded)
        self.assertEqual(loaded._prepare_accuracy_context(index[a.entity_id], index[other.entity_id], move)['zone_pen'], 0)
        self.assertEqual(loaded._prepare_accuracy_context(index[a.entity_id], index[b.entity_id], move)['zone_pen'], -3)

    def test_nogrid_smoke_follows_identity_after_rename_and_gm_restore(self):
        e, a, b = self.fixture()
        e.grid = None
        e.use_move(a, b, 'move/연막')
        b.name = '이름을 바꾼 실제 대상'
        move = e.r.move('struggle')
        self.assertEqual(e._prepare_accuracy_context(a, b, move)['zone_pen'], -3)
        e.gm.snapshot('renamed-smoke')
        e.end_encounter()
        e.gm.restore('renamed-smoke')
        self.assertIs(WORLD.actor_index(e)[b.entity_id], b)
        self.assertEqual(e._prepare_accuracy_context(a, b, move)['zone_pen'], -3)
        loaded = Engine.import_state(e.r, json.loads(json.dumps(e.export_state())))
        source, target = (WORLD.actor_index(loaded)[x.entity_id] for x in (a, b))
        self.assertEqual(loaded._prepare_accuracy_context(source, target, move)['zone_pen'], -3)
        loaded.end_encounter()
        self.assertFalse(loaded.zones)
        self.assertTrue(loaded.validate_state()['valid'])

    def test_observed_body_overlap_uses_all_cells_and_does_not_stack_penalty(self):
        import body_state as BODY
        e, a, b = self.fixture()
        self.smoke(e, a, b)
        b.pos = (7, 5)
        BODY.observe(e, b, [[0, 0], [-1, 0]], reason='관측된 몸체 일부가 연막에 걸친다')
        self.assertNotIn(b.pos, e.zone_cells)
        self.assertEqual(e._prepare_accuracy_context(a, b, e.r.move('struggle'))['zone_pen'], -3)
        a.pos = (4, 5)
        self.assertEqual(e._prepare_accuracy_context(a, b, e.r.move('struggle'))['zone_pen'], -3)

    def test_empty_whirlwind_consumes_once_and_completes_field_without_target_result(self):
        import effects as FX
        import event_effects as EVENTS
        import passive_events as PASSIVE_EVENTS
        import precise_actions as PRECISE
        import sound_state as SOUND
        import weather_blessings as WEATHER
        e, a, b = self.fixture()
        b.pos = (15, 15)
        a.spec['skills'] = {'육상': 5, '전투': 5}
        a.spec.setdefault('edges', []).append('edge/스테미너')
        a.spec['sound_preference'] = {'quiet': False, 'reason': 'move-use observation test'}
        smoke_cells = self.smoke(e, a, b)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        rng = e.rng.getstate()
        uses = a.move_uses.get('move/날려버리기', 0)
        with patch.object(EVENTS, 'begin_move_use', wraps=EVENTS.begin_move_use) as begin_use, \
                patch.object(FX, 'fire_event', wraps=FX.fire_event) as fire_event, \
                patch.object(SOUND, 'observe', wraps=SOUND.observe) as sound_observe, \
                patch.object(PASSIVE_EVENTS, 'begin', wraps=PASSIVE_EVENTS.begin) as attack_begin, \
                patch.object(PRECISE, 'attacked', wraps=PRECISE.attacked) as precise_attack, \
                patch.object(WEATHER, 'begin_attack', wraps=WEATHER.begin_attack) as weather_attack, \
                patch.object(Engine, 'accuracy_check', side_effect=AssertionError('target-free accuracy')) as accuracy:
            e.use_move_on(a, a, 'move/날려버리기', e.everyone, aim=(5, 5))
        line = e.grid.line((1, 5), (1, 0), 6)
        self.assertEqual(set(e.zone_cells), smoke_cells - line)
        self.assertTrue(smoke_cells - line)
        self.assertEqual(a.move_uses['move/날려버리기'], uses + 1)
        self.assertEqual((a.budget['standard'], a._action_history.count('standard')), (0, 1))
        self.assertEqual(e.rng.getstate(), rng)
        self.assertEqual((a.last_move, a.last_target), ('move/날려버리기', None))
        row = list(e._move_completions.values())[-1]
        self.assertEqual((row['move_id'], row['activation'], row['phase']),
                         ('move/날려버리기', 'empty_area_field', 'complete'))
        self.assertEqual((row['targets'], row['started'], row['results']), ([], [], {}))
        self.assertEqual(set(row['field_cells']), line)
        receipt_types = [e._effect_dispatch_receipts[token]['effect']['type']
                         for token in row['effects']]
        self.assertEqual(receipt_types, ['destroy_hazards', 'clear_field'])
        self.assertEqual(begin_use.call_count, 1)
        self.assertTrue(begin_use.call_args.kwargs['targetless'])
        on_move_use = [call for call in fire_event.call_args_list
                       if call.args[2].get('event') == 'on_move_use']
        self.assertEqual(len(on_move_use), 1)
        self.assertIsNone(on_move_use[0].args[3])
        self.assertEqual(sound_observe.call_count, 1)
        attack_begin.assert_not_called()
        precise_attack.assert_not_called()
        weather_attack.assert_not_called()
        accuracy.assert_not_called()
        self.assertEqual(a.spec['last_sound_event']['move_id'], 'move/날려버리기')
        self.assertFalse(getattr(e, '_native_action_stack', []))
        self.assertTrue(e.validate_state()['valid'], e.validate_state()['issues'])

    def test_injured_empty_whirlwind_applies_heavy_loss_without_skipping_rule(self):
        e, a, b = self.fixture()
        b.pos = (15, 15)
        smoke_cells = self.smoke(e, a, b)
        a.injuries = 5
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        hp = a.hp
        uses = a.move_uses.get('move/날려버리기', 0)
        e.use_move_on(a, a, 'move/날려버리기', e.everyone, aim=(5, 5))
        self.assertEqual((a.hp, a.budget['standard'],
                          a.move_uses['move/날려버리기']), (hp - 5, 0, uses + 1))
        self.assertIsNone(e._heavy_pending)
        packet = e._heavy_events['heavy-standard-1']
        self.assertEqual((packet['status'], packet['action_target'],
                          packet['heavy_consequence']['amount']), ('applied', None, 5))
        self.assertEqual(set(e.zone_cells), smoke_cells - set(packet['move']['_effect_area_cells']))

    def test_injured_empty_whirlwind_pending_survives_atomic_transition(self):
        import heavy_injury_adapter as HEAVY
        e, a, b = self.fixture()
        b.pos = (15, 15)
        smoke_cells = self.smoke(e, a, b)
        a.injuries = 5
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        # A live condition makes the narrow zero-damage confluence certificate
        # unavailable. The real activation prefix must still survive as pending.
        a.conditions.add('중독')
        uses = a.move_uses.get('move/날려버리기', 0)
        completion_count = len(getattr(e, '_move_completions', {}))
        with self.assertRaises(HEAVY.HeavyPending) as raised:
            e.use_move_on(a, a, 'move/날려버리기', e.everyone, aim=(5, 5))
        event_id = raised.exception.event_id
        self.assertEqual(e._heavy_pending, event_id)
        self.assertIn(event_id, e._heavy_events)
        packet = e._heavy_events[event_id]
        self.assertEqual((packet['status'], packet['action_target']), ('pending', None))
        self.assertEqual((a.budget['standard'], a.move_uses['move/날려버리기']),
                         (0, uses + 1))
        self.assertEqual(set(e.zone_cells), smoke_cells)
        self.assertEqual(len(getattr(e, '_move_completions', {})), completion_count)
        def pending_state():
            return deepcopy((a.budget, a.move_uses, e.zone_cells, e._heavy_pending,
                {key: (row['status'], tuple(row['issues']))
                 for key, row in e._heavy_events.items()}))
        before = pending_state()
        with self.assertRaises(HEAVY.HeavyPending) as repeated:
            e.use_move_on(a, a, 'move/날려버리기', e.everyone, aim=(5, 5))
        self.assertEqual(repeated.exception.event_id, event_id)
        self.assertEqual(pending_state(), before)

    def test_injured_targeted_whirlwind_keeps_existing_pending_prefix(self):
        import heavy_injury_adapter as HEAVY
        e, a, b = self.fixture()
        a.injuries = 5
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        uses = a.move_uses.get('move/날려버리기', 0)
        with self.assertRaises(HEAVY.HeavyPending) as raised:
            e.use_move_on(a, b, 'move/날려버리기', e.everyone, aim=(5, 5))
        event_id = raised.exception.event_id
        packet = e._heavy_events[event_id]
        self.assertEqual(e._heavy_pending, event_id)
        self.assertIs(packet['action_target'], b)
        self.assertEqual((packet['status'], a.budget['standard'],
                          a.move_uses['move/날려버리기']), ('pending', 0, uses + 1))

    def test_forged_empty_field_token_refuses_before_action_or_frequency(self):
        e, a, _ = self.fixture()
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        before = deepcopy((a.budget, a._action_history, a.move_uses, a.last_move,
                           a.last_target, e.zone_cells, e.rng.getstate()))
        with self.assertRaisesRegex(ValueError, 'actual native producer authority'):
            e.use_move(a, a, 'move/날려버리기', _field_activation=object(), aim=(5, 5))
        self.assertEqual((a.budget, a._action_history, a.move_uses, a.last_move,
                          a.last_target, e.zone_cells, e.rng.getstate()), before)

    def test_authoring_field_marker_cannot_issue_target_free_authority(self):
        e, a, b = self.fixture()
        b.pos = (15, 15)
        smoke_cells = self.smoke(e, a, b)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        before = deepcopy((a.budget, a.move_uses, e.zone_cells,
                           len(getattr(e, '_move_completions', {})), e.rng.getstate()))
        native = e.r.move_mech

        def authored(move_id):
            mechanics, confidence = native(move_id)
            mechanics = deepcopy(mechanics)
            if move_id == 'move/스모그':
                mechanics.setdefault('effects_exec', []).append({
                    'type': 'clear_field', 'remove': ['연막 in line'],
                    '_activation_scope': 'field'})
            return mechanics, confidence

        with patch.object(e.r, 'move_mech', side_effect=authored):
            self.assertEqual(e.use_move_on(a, a, 'move/스모그', e.everyone, aim=(5, 5)), 0)
        self.assertEqual((a.budget, a.move_uses, e.zone_cells,
                          len(getattr(e, '_move_completions', {})), e.rng.getstate()), before)
        self.assertEqual(set(e.zone_cells), smoke_cells)

    def test_post_adapter_effect_patch_cannot_expand_target_free_authority(self):
        e, a, b = self.fixture()
        b.pos = (15, 15)
        smoke_cells = self.smoke(e, a, b)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        before = deepcopy((a.budget, a.move_uses, e.zone_cells,
                           len(getattr(e, '_move_completions', {})), e.rng.getstate()))
        native = e.r.move_mech

        def post_adapter_patch(move_id):
            mechanics, confidence = native(move_id)
            mechanics = deepcopy(mechanics)
            if move_id == 'move/날려버리기':
                mechanics['effects_exec'].append({
                    'type': 'clear_field', 'remove': ['연막 in line'],
                    '_activation_scope': 'field'})
            return mechanics, confidence

        with patch.object(e.r, 'move_mech', side_effect=post_adapter_patch):
            self.assertEqual(e.use_move_on(a, a, 'move/날려버리기',
                                           e.everyone, aim=(5, 5)), 0)
        self.assertEqual((a.budget, a.move_uses, e.zone_cells,
                          len(getattr(e, '_move_completions', {})), e.rng.getstate()), before)
        self.assertEqual(set(e.zone_cells), smoke_cells)

    def test_another_empty_area_move_cannot_bypass_target_activation(self):
        e, a, b = self.fixture()
        b.pos = (15, 15)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        before = deepcopy((a.budget, a.move_uses, a.pos, e.rng.getstate()))
        self.assertEqual(e.use_move_on(a, a, 'move/스모그', e.everyone, aim=(5, 5)), 0)
        self.assertEqual((a.budget, a.move_uses, a.pos, e.rng.getstate()), before)

    def test_empty_whirlwind_primary_placeholder_does_not_change_activation(self):
        outcomes = []
        for external_primary in (False, True):
            e, a, b = self.fixture()
            b.pos = (15, 15)
            smoke_cells = self.smoke(e, a, b)
            b.on_field = False
            e.start_round(e.everyone)
            e.start_of_turn(a, initiative_count=20)
            rng = e.rng.getstate()
            e.use_move_on(a, b if external_primary else a, 'move/날려버리기',
                          e.everyone, aim=(5, 5))
            row = list(e._move_completions.values())[-1]
            outcomes.append((set(e.zone_cells), deepcopy(a.budget),
                a.move_uses.get('move/날려버리기'), a.last_move, a.last_target,
                row['activation'], tuple(row['field_cells']), tuple(row['targets']),
                tuple(row['results']), e.rng.getstate() == rng, a.pos, b.pos,
                bool(b.on_field), bool(smoke_cells - set(row['field_cells']))))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_explicit_north_and_west_aim_choose_target_or_empty_path_from_actual_cells(self):
        for direction in ((0, -1), (-1, 0)):
            for occupied in (False, True):
                with self.subTest(direction=direction, occupied=occupied):
                    e, a, b = self.fixture()
                    a.pos = (10, 10)
                    aim = (10 + direction[0] * 5, 10 + direction[1] * 5)
                    b.pos = ((10 + direction[0] * 2, 10 + direction[1] * 2)
                             if occupied else (18, 18))
                    e.start_round(e.everyone)
                    e.start_of_turn(a, initiative_count=20)
                    e.use_move_on(a, a, 'move/날려버리기', e.everyone, aim=aim)
                    row = list(e._move_completions.values())[-1]
                    self.assertEqual(set(row.get('field_cells', e.grid.line(a.pos, direction, 6))),
                                     e.grid.line((10, 10), direction, 6))
                    if occupied:
                        self.assertNotEqual(row.get('activation'), 'empty_area_field')
                        self.assertEqual([target.entity_id for target in row['targets']],
                                         [b.entity_id])
                    else:
                        self.assertEqual(row['activation'], 'empty_area_field')
                        self.assertEqual(row['targets'], [])

    def test_empty_whirlwind_effect_failure_is_atomic(self):
        import effects as FX
        e, a, b = self.fixture()
        b.pos = (15, 15)
        self.smoke(e, a, b)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        receipts = getattr(e, '_effect_dispatch_receipts', None)
        completions = getattr(e, '_move_completions', None)

        def observed_state():
            return deepcopy((a.budget, a._action_history, a.move_uses, a.last_move,
                getattr(a.last_target, 'entity_id', None), e.zone_cells, e.hazards,
                e.grid.slow, len(getattr(e, '_effect_dispatch_receipts', {})),
                [(key, row['move_id'], row['phase'])
                 for key, row in getattr(e, '_move_completions', {}).items()], e.rng.getstate(),
                e.log_lines, e.gm_prompts, a.spec, a.counters,
                getattr(a, 'event_effect_history', None)))

        before = observed_state()

        def fail_clear(*_args):
            raise RuntimeError('forced clear failure')

        with patch.dict(FX.HANDLERS, {'clear_field': fail_clear}):
            with self.assertRaisesRegex(ValueError, 'target-free field effects did not complete'):
                e.use_move_on(a, a, 'move/날려버리기', e.everyone, aim=(5, 5))
        self.assertEqual(observed_state(), before)
        self.assertIs(getattr(e, '_effect_dispatch_receipts', None), receipts)
        self.assertIs(getattr(e, '_move_completions', None), completions)
        self.assertTrue(e.validate_state()['valid'], e.validate_state()['issues'])

    def test_empty_whirlwind_gm_and_json_restore_preserve_completion_and_live_actors(self):
        e, a, b = self.fixture()
        b.pos = (15, 15)
        smoke_cells = self.smoke(e, a, b)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        e.use_move_on(a, a, 'move/날려버리기', e.everyone, aim=(5, 5))
        remaining = smoke_cells - e.grid.line((1, 5), (1, 0), 6)
        completion_id = list(e._move_completions)[-1]
        e.gm.snapshot('empty-whirlwind')
        e.end_encounter()
        self.assertFalse(e.zone_cells)
        e.gm.restore('empty-whirlwind')
        self.assertEqual(set(e.zone_cells), remaining)
        self.assertIs(WORLD.actor_index(e)[a.entity_id], a)
        self.assertEqual(e._move_completions[completion_id]['activation'], 'empty_area_field')
        self.assertIs(e._move_completions[completion_id]['actor'], a)

        loaded = Engine.import_state(e.r, json.loads(json.dumps(e.export_state())))
        index = WORLD.actor_index(loaded)
        row = loaded._move_completions[completion_id]
        self.assertEqual(set(loaded.zone_cells), remaining)
        self.assertIs(row['actor'], index[a.entity_id])
        self.assertEqual((row['targets'], row['results'], row['phase']), ([], {}, 'complete'))
        self.assertEqual(set(row['field_cells']), e.grid.line((1, 5), (1, 0), 6))
        self.assertTrue(loaded.validate_state()['valid'], loaded.validate_state()['issues'])

    def test_unmapped_whirlwind_refuses_before_action_cost(self):
        e, a, b = self.fixture()
        e.grid = None
        before = deepcopy((a.move_uses, e.rng.getstate(), b.pos))
        with self.assertRaisesRegex(ValueError, 'actual mapped line before action cost'):
            e.use_move(a, b, 'move/날려버리기')
        self.assertEqual((a.move_uses, e.rng.getstate(), b.pos), before)


if __name__ == '__main__':
    unittest.main()
