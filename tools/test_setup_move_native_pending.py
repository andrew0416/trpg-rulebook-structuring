"""Source-owned preparation joins the existing native defense continuation."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_setup_move_state as FIXTURE
from engine import Rules, Engine, Combatant
from builder import build_trainer
import action_resources as RESOURCES
import heavy_injury_adapter as HEAVY
import move_defense_reactions as DEFENSE
import passive_events as PASSIVE
import setup_move_state as SETUP
import world_entities as WORLD

FLY, DIG, DIVE = FIXTURE.FLY, FIXTURE.DIG, FIXTURE.DIVE


class SetupMoveNativePendingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='all')

    def world(self, move):
        case = FIXTURE.SetupMoveStateTests()
        case.r = self.r
        case.setUp()
        self.e, self.a, self.b = case.e, case.a, case.b
        self.move = move
        self.reactor = Combatant(self.r, build_trainer(
            self.r, 'setup interceptor', 30,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 30),
            skills={'육상': '달인'},
            extra={'pos': (6, 5), 'side': 'opponent', 'size': '중형',
                   'movement': {'land': 8, 'swim': 8}, 'movement_basis': 'current',
                   'abilities': []}))
        self.e.gm.add_combatant(self.reactor)
        self.other = None
        if move != FLY:
            self.other = Combatant(self.r, build_trainer(
                self.r, 'second actual Burst target', 30,
                dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 30),
                extra={'pos': (3, 3), 'side': 'opponent', 'size': '중형', 'abilities': []}))
            self.e.gm.add_combatant(self.other)
        if move == DIVE:
            self.e.observe_map_terrain(
                [(2, 2), (3, 2), (4, 2), (5, 2), (6, 2),
                 (6, 3), (6, 4), (6, 5), (3, 3)], base='underwater',
                reason='measured continuous deep-water approach and Intercept lane')
        self.prepare_options = ({'diggable': True, 'reason': 'observed loose-earth origin'}
                                if move == DIG else
                                {'water_depth_m': 12, 'reason': 'measured twelve-metre water'}
                                if move == DIVE else {})
        self.resolve_options = ({'path': [{'position': (3, 2), 'altitude': 25},
                                         {'position': (4, 2), 'altitude': 25}]}
                                if move == FLY else {'path': [(3, 2), (4, 2)]})
        if move == DIG:
            self.resolve_options.update(diggable=True, reason='observed loose-earth route')

    def use(self, options):
        return self.e.use_setup_move_on(self.a, self.b, self.move, self.e.everyone,
                                       setup_options=options, set_damage=True)

    def prepare(self, *, watch=True):
        self.assertEqual(self.use(self.prepare_options), 0)
        self.assertIsNotNone(SETUP.pending(self.a))
        self.assertEqual(self.a.setup_move, self.move)
        self.assertEqual(self.a.move_uses.get(self.move, 0), 0)
        self.assertEqual(self.a.budget['standard'], 0)
        if self.move == FLY:
            self.assertEqual((self.a.pos, self.a.spec['_movement_altitude'], self.a.airborne),
                             ((2, 2), 25, True))
        elif self.move == DIG:
            self.assertTrue(self.a.spec['_burrow']['underground'])
            self.assertEqual(self.a.spec['_burrow']['depth_m'], 25)
            self.assertEqual(self.a.budget, {'standard': 0, 'shift': 0, 'swift': 0})
        else:
            self.assertFalse(SETUP.targetable(self.a))
            self.assertEqual(self.a.budget, {'standard': 0, 'shift': 0, 'swift': 0})
        before = deepcopy(self.e.export_state())
        with self.assertRaisesRegex(ValueError, 'later turn'):
            self.use(self.resolve_options)
        self.assertEqual(self.e.export_state(), before)
        if self.e._active_turn_actor is self.a:
            self.e.end_of_turn(self.a)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)
        if watch:
            self.e.watch_move_defense(self.b,
                [{'actor_id': self.reactor.entity_id, 'source': DEFENSE.MELEE}],
                reason='actual prepared Move target offers Intercept')

    def restore(self):
        actors = [self.a, self.b, self.reactor] + ([self.other] if self.other else [])
        ids = [actor.entity_id for actor in actors]
        event = self.e._passive_pending
        self.e.gm.restore(self.e.gm.snapshot())
        self.assertEqual(self.e._passive_pending, event)
        self.e = Engine.import_state(self.r,
            json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
        restored = [WORLD.actor_index(self.e)[uid] for uid in ids]
        self.a, self.b, self.reactor = restored[:3]
        self.other = restored[3] if len(restored) > 3 else None
        self.assertEqual(self.e._passive_pending, event)

    def lifecycle(self, move):
        for use in (True, False):
            with self.subTest(move=move, intercept=use):
                self.world(move)
                self.prepare()
                hp = (self.b.hp, self.reactor.hp, self.other.hp if self.other else None)
                prior = set(getattr(self.e, '_move_completions', {}))
                with patch.object(type(self.e), 'd20', new=lambda engine: 20):
                    with self.assertRaises(PASSIVE.PassiveEventPending) as caught:
                        self.use(self.resolve_options)
                event = caught.exception.event_id
                self.assertEqual(self.e._passive_pending, event)
                self.assertIn(event, self.e._passive_events)
                self.assertEqual((self.b.hp, self.reactor.hp,
                                  self.other.hp if self.other else None), hp)
                self.assertEqual(self.a.pos, (4, 2))
                self.assertIsNone(SETUP.pending(self.a))
                self.assertIsNone(self.a.setup_move)
                self.assertTrue(SETUP.targetable(self.a))
                self.assertEqual(self.a.move_uses[move], 1)
                self.assertEqual(self.a._action_history, ['standard' if move == FLY else 'full'])
                self.assertEqual(self.a.budget['standard'], 0)
                self.assertFalse(hasattr(self.e, '_setup_move_scopes'))
                self.assertFalse(hasattr(self.e, '_reactive_move_transaction'))
                if move == FLY:
                    self.assertEqual((self.a.spec['_movement_altitude'], self.a.airborne), (0, False))
                elif move == DIG:
                    self.assertFalse(self.a.spec['_burrow']['underground'])
                    self.assertEqual(self.e._burrow_tunnels[-1]['path'], [[3, 2], [4, 2]])
                self.restore()
                paid = deepcopy((self.a.move_uses, self.a.budget, self.a._action_history))
                options = {'path': [(6, 5), (6, 4), (6, 3), (5, 2)],
                           'skill': '육상', 'mode': 'swim' if move == DIVE else 'land',
                           'shove_destination': [6, 2], 'roll_options': {'fixed': [6] * 6}} if use else None
                with patch.object(type(self.e), 'd20', new=lambda engine: 20):
                    self.e.choose_move_defense(event, self.reactor, use=use, options=options,
                        reason='accept or decline the actual prepared Move Intercept')
                self.assertIsNone(self.e._passive_pending)
                received, untouched = (self.reactor, self.b) if use else (self.b, self.reactor)
                self.assertLess(received.hp, hp[1 if use else 0])
                self.assertEqual(untouched.hp, hp[0 if use else 1])
                self.assertEqual((self.b.pos, self.reactor.pos),
                                 ((6, 2), (5, 2)) if use else ((5, 2), (6, 5)))
                self.assertEqual(RESOURCES.pending(self.reactor),
                                 {'standard': 1, 'shift': 1} if use else {})
                self.assertEqual((self.a.move_uses, self.a.budget, self.a._action_history), paid)
                rows = [row for key, row in self.e._move_completions.items() if key not in prior]
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertEqual(row['phase'], 'complete')
                self.assertEqual(row['targets'], [self.b] + ([self.other] if self.other else []))
                self.assertEqual(set(row['results']), {target.entity_id for target in row['targets']})
                self.assertIn(received.entity_id, row['received'])
                if self.other:
                    self.assertLess(self.other.hp, hp[2])
                final = deepcopy(self.e.export_state())
                with self.assertRaises(ValueError):
                    self.e.choose_move_defense(event, self.reactor, use=use, options=options,
                                              reason='same completed defense cannot replay')
                PASSIVE.deliver(self.e, event)
                self.assertEqual(self.e.export_state(), final)
                self.assertIsNone(SETUP.pending(self.a))
                self.assertEqual(self.a.pos, (4, 2))

    def test_fly_prepare_next_turn_intercept_both_choices_restores_and_native_completion(self):
        self.lifecycle(FLY)

    def test_dig_prepare_next_turn_intercept_both_choices_restores_and_all_burst_targets(self):
        self.lifecycle(DIG)

    def test_dive_prepare_next_turn_intercept_both_choices_restores_and_all_burst_targets(self):
        self.lifecycle(DIVE)

    def test_missing_or_false_native_wait_and_late_error_restore_original_preparation(self):
        class FalsePassive(PASSIVE.PassiveEventPending):
            pass
        for move in (FLY, DIG, DIVE):
            self.world(move)
            self.prepare()
            before = deepcopy(self.e.export_state())
            errors = (ValueError('native late failure'), PASSIVE.PassiveEventPending('absent-event'),
                      HEAVY.HeavyPending('absent-event'), FalsePassive('absent-event'))
            for error in errors:
                with self.subTest(move=move, error=type(error).__name__):
                    with patch.object(type(self.e), 'use_move_on', side_effect=error):
                        with self.assertRaises(type(error)):
                            self.use(self.resolve_options)
                    self.assertEqual(self.e.export_state(), before)
                    self.assertFalse(hasattr(self.e, '_setup_move_scopes'))
                    self.assertFalse(hasattr(self.e, '_reactive_move_transaction'))

    def test_authenticated_resume_scope_cannot_be_replaced_by_flags_or_foreign_completion(self):
        self.world(DIG)
        before = deepcopy(self.e.export_state())
        with self.assertRaisesRegex(ValueError, 'use_setup_move_on'):
            self.e.use_move(self.a, self.b, DIG)
        self.e._resuming_move_activation = True
        self.e._move_activation_scopes = [{'actor': self.a, 'move_id': DIG,
            'activation': {'started': True}, 'completion_id': 'absent-completion'}]
        previous = getattr(self.e, '_move_completions', None)
        try:
            with self.assertRaisesRegex(ValueError, 'use_setup_move_on'):
                self.e.use_move(self.a, self.b, DIG)
            self.e._move_completions = {'absent-completion': {
                'actor': self.b, 'move_id': DIG, 'phase': 'complete'}}
            with self.assertRaisesRegex(ValueError, 'use_setup_move_on'):
                self.e.use_move(self.a, self.b, DIG)
        finally:
            del self.e._resuming_move_activation
            del self.e._move_activation_scopes
            if previous is None:
                vars(self.e).pop('_move_completions', None)
            else:
                self.e._move_completions = previous
        self.assertEqual(self.e.export_state(), before)

    def test_actual_event_with_wrong_exception_or_missing_registry_rolls_back_paid_prefix(self):
        class FalsePassive(PASSIVE.PassiveEventPending):
            pass
        original = Engine.use_move_on
        for move in (FLY, DIG, DIVE):
            self.world(move)
            self.prepare()
            before = deepcopy(self.e.export_state())
            for fault in ('subclass', 'wrong_id', 'missing_registry', 'late_error'):
                with self.subTest(move=move, fault=fault):
                    def invalid(engine, *args, **kwargs):
                        try:
                            return original(engine, *args, **kwargs)
                        except PASSIVE.PassiveEventPending as error:
                            if fault == 'subclass':
                                raise FalsePassive(error.event_id)
                            if fault == 'wrong_id':
                                raise PASSIVE.PassiveEventPending('different-event')
                            if fault == 'late_error':
                                raise ValueError('late native defense failure')
                            engine._passive_events.pop(error.event_id)
                            raise
                    expected = (FalsePassive if fault == 'subclass' else
                                ValueError if fault == 'late_error' else PASSIVE.PassiveEventPending)
                    with patch.object(Engine, 'use_move_on', new=invalid), \
                            patch.object(Engine, 'd20', new=lambda engine: 20):
                        with self.assertRaises(expected):
                            self.use(self.resolve_options)
                    self.assertEqual(self.e.export_state(), before)

    def test_actual_heavy_wait_preserves_source_movement_consumption_and_native_damage(self):
        self.world(FLY)
        self.prepare(watch=False)
        self.e.gm.set_injuries(self.b, value=5, reason='actual pre-existing heavy injury')
        hp = self.b.hp
        with patch.object(Engine, 'd20', new=lambda engine: 20):
            with self.assertRaises(HEAVY.HeavyPending) as caught:
                self.use(self.resolve_options)
        event = caught.exception.event_id
        self.assertEqual(self.e._heavy_pending, event)
        self.assertEqual(self.e._heavy_events[event]['status'], 'pending')
        self.assertLess(self.b.hp, hp)
        self.assertEqual(self.a.pos, (4, 2))
        self.assertEqual((self.a.spec['_movement_altitude'], self.a.airborne), (0, False))
        self.assertIsNone(SETUP.pending(self.a))
        self.assertIsNone(self.a.setup_move)
        self.assertEqual((self.a.move_uses[FLY], self.a.budget['standard']), (1, 0))
        self.restore()
        self.assertEqual(self.e._heavy_pending, event)
        self.assertEqual(self.e._heavy_events[event]['target'], self.b)
        self.assertFalse(self.e._heavy_events[event]['continuation_reified'])

    def test_normal_miss_with_watched_target_finishes_all_targets_and_preserves_watch(self):
        for move in (FLY, DIG, DIVE):
            with self.subTest(move=move):
                self.world(move)
                self.prepare()
                watch = deepcopy(self.b.spec['move_defense_watch'])
                hp = (self.b.hp, self.reactor.hp, self.other.hp if self.other else None)
                with patch.object(type(self.e), 'd20', new=lambda engine: 1):
                    self.use(self.resolve_options)
                self.assertIsNone(self.e._passive_pending)
                self.assertEqual((self.b.hp, self.reactor.hp,
                                  self.other.hp if self.other else None), hp)
                self.assertEqual(self.b.spec['move_defense_watch'], watch)
                self.assertIsNone(SETUP.pending(self.a))
                self.assertEqual(self.a.move_uses[move], 1)
                rows = [row for row in self.e._move_completions.values() if row['move_id'] == move]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['phase'], 'complete')
                self.assertTrue(all(not result['hit'] for result in rows[0]['results'].values()))


if __name__ == '__main__':
    unittest.main()
