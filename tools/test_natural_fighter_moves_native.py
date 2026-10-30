"""Source-only native Astonish/Sand Attack acceptance candidates. Not executed."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
import book_survivalist_fixture as FIX
import natural_fighter_moves as MOVES
import frequency as F
import combat_timing as TIME
import state_codec as CODEC


class NaturalFighterMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)

    def world(self, move):
        world = FIX.scene(self.rules, feats=())
        self.e, self.a, self.t = [world[k] for k in ('engine', 'trainer', 'foe')]
        self.e.gm.set_move(self.a, move, reason='actual native Move acquisition fixture')
        self.e.gm.set_position(self.t, (3, 3), reason='actual native target in range')
        self.e.gm.set_types(self.t, ['물'], reason='actual target has no Ghost immunity')
        FIX.battle(self.e, self.a)

    def observe(self, unaware, *, target=None):
        key = MOVES.awareness_key(self.e, self.a, target or self.t)
        FIX.ruling(self.e, key, {'observation_key': key, 'unaware': unaware},
                   reason='GM observed actual target awareness before this attack')

    def cast(self, move, face=14):
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.use_move_on(self.a, self.t, move, self.e.everyone, set_damage=True)

    def next_actor_turn(self):
        self.e.end_of_turn(self.a)
        self.e.end_round()
        FIX.battle(self.e, self.a)

    def restore(self):
        self.e, index = FIX.restore(self.rules, self.e)
        self.a, self.t = index[self.a.entity_id], index[self.t.entity_id]

    def test_aware_threshold_and_unaware_miss_are_native(self):
        for unaware, face, expected, quota in ((False, 14, False, True),
                (False, 15, True, True), (True, 1, False, True),
                (True, 14, True, False), (True, 15, True, True)):
            with self.subTest(unaware=unaware, face=face):
                self.world(MOVES.ASTONISH)
                self.observe(unaware)
                before = self.t.hp
                self.cast(MOVES.ASTONISH, face)
                self.assertEqual('풀죽음' in self.t.conditions, expected)
                self.assertEqual(F.activation_allowed(self.a, MOVES.QUOTA, MOVES.ONCE, engine=self.e), quota)
                self.assertEqual(self.a.move_uses[MOVES.ASTONISH], 1)
                self.assertEqual(self.a.budget['standard'], 0)
                self.assertEqual(self.t.hp < before, face != 1)

    def test_scene_auto_quota_survives_restore_without_limiting_at_will_move(self):
        self.world(MOVES.ASTONISH)
        self.observe(True)
        self.cast(MOVES.ASTONISH)
        self.e.cure_status(self.t, '풀죽음')
        self.restore()
        self.next_actor_turn()
        self.cast(MOVES.ASTONISH)
        self.assertNotIn('풀죽음', self.t.conditions)
        self.assertEqual(self.a.move_uses[MOVES.ASTONISH], 2)
        self.assertFalse(F.activation_allowed(self.a, MOVES.QUOTA, MOVES.ONCE, engine=self.e))
        self.next_actor_turn()
        self.cast(MOVES.ASTONISH, 15)
        self.assertIn('풀죽음', self.t.conditions)
        self.assertEqual(self.a.move_uses[MOVES.ASTONISH], 3)
        self.e.end_scene(round_elapsed_seconds=10)
        self.assertTrue(F.activation_allowed(self.a, MOVES.QUOTA, MOVES.ONCE, engine=self.e))

    def test_missing_or_wrong_target_awareness_is_atomic_before_cost_and_rng(self):
        for observation in ('absent', 'wrong_target', 'stale'):
            with self.subTest(observation=observation):
                self.world(MOVES.ASTONISH)
                if observation == 'wrong_target':self.observe(True, target=self.a)
                if observation == 'stale':
                    key = MOVES.awareness_key(self.e, self.a, self.t)
                    FIX.ruling(self.e, key, {'observation_key': 'old-turn', 'unaware': True})
                before = deepcopy((CODEC.dump_engine(self.e), self.e.rng.getstate()))
                with self.assertRaisesRegex(ValueError, 'presence-awareness'):
                    self.e.use_move_on(self.a, self.t, MOVES.ASTONISH, self.e.everyone)
                self.assertEqual(before, (CODEC.dump_engine(self.e), self.e.rng.getstate()))

    def test_sand_expires_at_target_next_turn_end_after_restore(self):
        self.world(MOVES.SAND)
        self.cast(MOVES.SAND)
        self.assertIn('실명', self.t.conditions)
        rows = [r for r in TIME.records(self.t) if r['source'] == MOVES.SAND]
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]['turn_owner'], self.t)
        self.restore()
        self.e.end_of_turn(self.a)
        self.assertIn('실명', self.t.conditions)
        self.e.start_of_turn(self.t, initiative_count=19)
        self.assertIn('실명', self.t.conditions)
        self.e.end_of_turn(self.t)
        self.assertNotIn('실명', self.t.conditions)
        self.assertFalse([r for r in TIME.records(self.t) if r['source'] == MOVES.SAND])

    def test_sand_retains_independent_blindness_before_or_after_it(self):
        for before in (True, False):
            with self.subTest(before=before):
                self.world(MOVES.SAND)
                if before:self.e.apply_status(self.t, '실명', source='gm/independent-blindness')
                self.cast(MOVES.SAND)
                if not before:self.e.apply_status(self.t, '실명', source='gm/independent-blindness')
                self.restore()
                self.e.end_of_turn(self.a)
                self.e.start_of_turn(self.t, initiative_count=19)
                self.e.end_of_turn(self.t)
                self.assertIn('실명', self.t.conditions)
                self.assertFalse([r for r in TIME.records(self.t) if r['source'] == MOVES.SAND])

    def test_sand_miss_has_no_timer_and_does_not_erase_existing_blindness(self):
        self.world(MOVES.SAND)
        self.e.apply_status(self.t, '실명', source='gm/existing-blindness')
        self.cast(MOVES.SAND, 1)
        self.assertIn('실명', self.t.conditions)
        self.assertFalse([r for r in TIME.records(self.t) if r['source'] == MOVES.SAND])
        self.assertEqual(self.a.move_uses[MOVES.SAND], 1)

    def test_sand_still_has_native_eot_frequency(self):
        self.world(MOVES.SAND)
        self.cast(MOVES.SAND)
        self.next_actor_turn()
        def gameplay():
            # The native codec dump compares timed records by content, not by object identity;
            # the engine log is narration (the refusal itself logs one line), not gameplay state.
            dump = CODEC.dump_engine(self.e)
            log = list(self.e.log_lines)
            nodes = {k: v for k, v in dump['nodes'].items() if not (isinstance(v, dict) and v.get('items') == log)}
            return deepcopy((dict(dump, nodes=nodes), self.e.rng.getstate()))
        before = gameplay()
        self.assertEqual(self.e.use_move_on(self.a, self.t, MOVES.SAND, self.e.everyone), 0)
        self.assertEqual(before, gameplay())

    def test_sand_timer_overlap_retains_longer_independent_source(self):
        self.world(MOVES.SAND)
        self.cast(MOVES.SAND)
        self.e.apply_effect(self.a, self.t,
            {'type': 'apply_status', 'status': '실명', 'target': 'target', 'until': 'encounter_end'},
            15, True, 0, 'gm/independent-longer-blindness')
        self.restore()
        self.e.end_of_turn(self.a)
        self.e.start_of_turn(self.t, initiative_count=19)
        self.e.end_of_turn(self.t)
        self.assertIn('실명', self.t.conditions)
        self.assertEqual([r['source'] for r in TIME.records(self.t) if '실명' in r.get('statuses', [])],
                         ['gm/independent-longer-blindness'])
        self.e.end_encounter(round_elapsed_seconds=10)
        self.assertNotIn('실명', self.t.conditions)

    def test_sand_respects_native_keen_eye_immunity(self):
        self.world(MOVES.SAND)
        self.e.gm.set_ability(self.t, '날카로운눈', reason='actual Keen Eye target')
        self.cast(MOVES.SAND)
        self.assertNotIn('실명', self.t.conditions)
        self.restore()
        self.e.end_of_turn(self.a)
        self.e.start_of_turn(self.t, initiative_count=19)
        self.e.end_of_turn(self.t)
        self.assertNotIn('실명', self.t.conditions)

    def test_old_awareness_cannot_replay_outside_native_scope_after_turn_or_scene(self):
        import effects as FX
        for boundary in ('turn', 'scene'):
            with self.subTest(boundary=boundary):
                self.world(MOVES.ASTONISH)
                self.observe(True)
                old_move = MOVES.prepare_move(self.e, self.a, self.t, self.rules.move(MOVES.ASTONISH))
                self.cast(MOVES.ASTONISH)
                self.e.cure_status(self.t, '풀죽음')
                if boundary == 'turn':self.next_actor_turn()
                else:
                    self.e.end_scene(round_elapsed_seconds=10)
                    FIX.battle(self.e, self.a)
                before = deepcopy((self.a.spec, self.t.spec, self.t.conditions,
                    self.t.custom_conditions, self.e.rng.getstate()))
                result = FX.run_effects(self.e, self.a, self.t,
                    [dict(MOVES.FLINCH, **{'if': MOVES.PREDICATE})],
                    {'move': old_move, 'nat': 14, 'hit': True, 'dealt': 0}, MOVES.ASTONISH)
                self.assertFalse(result.pending)
                self.assertEqual(before, (self.a.spec, self.t.spec, self.t.conditions,
                    self.t.custom_conditions, self.e.rng.getstate()))

    def test_live_native_scope_rejects_copied_move_and_unissued_effect_receipt(self):
        self.world(MOVES.ASTONISH)
        self.observe(True)
        copied_move = MOVES.prepare_move(self.e, self.a, self.t, self.rules.move(MOVES.ASTONISH))
        rejected = []
        def inspect(effect, ctx):
            if effect.get('if') != MOVES.PREDICATE:return effect
            current = dict(ctx, source_id=MOVES.ASTONISH)
            runtime, actor, target = current['engine'], current['attacker'], current['target']
            with self.assertRaisesRegex(ValueError, 'actual native Move object'):
                MOVES.qualifies(runtime, actor, target, dict(current, move=copied_move))
            with self.assertRaisesRegex(ValueError, 'receipt'):
                MOVES.apply(runtime, actor, target, effect, current)
            rejected.append(True)
            return effect
        self.e.rulings.add_hook('before_effect', inspect, reason='inspect actual native scope')
        self.cast(MOVES.ASTONISH)
        self.assertEqual(rejected, [True])
        self.assertIn('풀죽음', self.t.conditions)
        self.assertFalse(F.activation_allowed(self.a, MOVES.QUOTA, MOVES.ONCE, engine=self.e))

    def test_gm_modified_final_effect_is_rejected_without_forced_flinch(self):
        for change in ({'status': '실명'}, {'target': 'self'}):
            with self.subTest(change=change):
                self.world(MOVES.ASTONISH)
                self.observe(True)
                def replace(effect, ctx):
                    return dict(effect, **change) if effect.get('if') == MOVES.PREDICATE else effect
                self.e.rulings.add_hook('before_effect', replace, reason='explicit alternate effect payload')
                self.cast(MOVES.ASTONISH)
                self.assertNotIn('풀죽음', self.t.conditions)
                self.assertNotIn('풀죽음', self.a.conditions)
                self.assertNotIn('실명', self.t.conditions)
                self.assertTrue(F.activation_allowed(self.a, MOVES.QUOTA, MOVES.ONCE, engine=self.e))
                rejected = [row for row in self.e._effect_dispatch_receipts.values()
                    if row['source_id'] == MOVES.ASTONISH and row['status'] == 'execution_failed']
                self.assertEqual(len(rejected), 1)
                self.assertIn('exact final effect', str(rejected[0]['result']))

