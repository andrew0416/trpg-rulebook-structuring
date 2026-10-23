"""C11-074 adopted state, actual native consumers and changed roll boundaries."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_mapless_space as fixture
import fast_combat as FAST
import source_context as SOURCE_CONTEXT
import world_entities as W
from state_codec import load_engine


class FastCombatTests(unittest.TestCase):
    setUpClass = classmethod(fixture.MaplessFixture.setUpClass.__func__)
    actor = fixture.MaplessFixture.actor
    configure = fixture.MaplessFixture.configure
    movement = fixture.MaplessFixture.movement
    snap = fixture.MaplessFixture.snap

    def setUp(self):
        self._ruling_state = deepcopy(vars(self.r.rulings))
        fixture.MaplessFixture.setUp(self)

    def tearDown(self):
        self.r.rulings.__dict__.clear()
        self.r.rulings.__dict__.update(self._ruling_state)

    def adopt(self, faces, *, sheet_id='session-sheet', enemy_ids=None, reason='GM adopts the externally pregenerated enemy accuracy sheet'):
        return self.e.gm.adopt_enemy_accuracy_sheet(sheet_id=sheet_id,
            enemy_ids=[self.b.entity_id, self.c.entity_id] if enemy_ids is None else enemy_ids,
            faces=faces, reason=reason)

    def state(self):
        return getattr(self.e, FAST.FIELD)

    def begin(self, actor):
        if self.e._active_turn_actor is not None:
            self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor, initiative_count=20)

    def targets(self, actor, targets, mid='move/물대포', event_id='actual-targets'):
        return self.e.gm.observe_mapless_targets(actor, event_id=event_id,
            move_id=mid, landmark_id='stairs', target_ids=[t.entity_id for t in targets],
            reason='GM observes these actual recipients and their abstract range')

    def test_adopted_mapless_travel_and_set_chart_reach_actual_native_attack(self):
        self.adopt([20])
        self.begin(self.a)
        self.movement(cost=4)
        self.e.move_abstract(self.a, event_id='walk')
        self.assertEqual(W.location_of(self.a), {'kind': 'abstract', 'place_id': 'fountain'})
        self.assertEqual(self.a.budget['shift'], 0)
        self.targets(self.b, [self.a])
        self.begin(self.b)
        move = self.r.move('move/물대포')
        with patch.object(self.e, 'roll_expr', side_effect=AssertionError('set chart has no damage dice')):
            expected = self.e.roll_damage(self.b, self.a, move, crit=True, set_damage=True)
            before = self.a.hp
            dealt = self.e.use_move(self.b, self.a, move['id'], set_damage=True)
        self.assertEqual(dealt, expected)
        self.assertEqual(before - self.a.hp, expected)
        self.assertEqual((self.b.budget['standard'], self.b.move_uses[move['id']]), (0, 1))
        self.assertEqual(self.state()['cursor'], 1)

    def test_only_actual_enrolled_enemies_consume_one_ordered_shared_sheet(self):
        self.adopt([1, 20, 7])
        move = self.r.move('move/물대포')
        rng = self.e.rng.getstate()
        with patch.object(self.e, 'd20', return_value=12) as die:
            miss = self.e.accuracy_check(self.b, self.a, move)
            hit = self.e.accuracy_check(self.c, self.a, move)
            player = self.e.accuracy_check(self.a, self.b, move)
            unlisted = self.e.accuracy_check(self.d, self.a, move)
            ordinary = self.e.d20()
        self.assertEqual(miss, (False, 1, False))
        self.assertEqual(hit, (True, 20, True))
        self.assertEqual((player[1], unlisted[1], ordinary), (12, 12, 12))
        self.assertEqual(die.call_count, 3)
        self.assertEqual(self.state()['cursor'], 2)
        self.assertEqual(self.e.rng.getstate(), rng)
        self.b.side = 'party'
        with patch.object(self.e, 'd20', return_value=9):
            self.assertEqual(self.e.accuracy_check(self.b, self.a, move)[1], 9)
        self.assertEqual(self.state()['cursor'], 2)
        self.snap()  # An actual side change does not corrupt the adopted sheet.

    def test_preview_fixed_observation_and_no_check_leave_cursor_untouched(self):
        self.adopt([20])
        before = deepcopy(self.state())
        move = self.r.move('move/물대포')
        with patch.object(self.e, 'd20', side_effect=AssertionError('no unobserved accuracy')):
            preview = self.e.plan_accuracy_context(self.b, self.a, move)
            self.assertTrue(preview['requires_roll'])
            self.assertIsNone(preview['final_outcome'])
            self.assertEqual(self.e.accuracy_check(self.b, self.a, move, fixed_roll=1), (False, 1, False))
            self.assertEqual(self.e.accuracy_check(self.b, self.b, self.r.move('move/빛의장막')), (True, None, False))
        self.assertEqual(self.state(), before)
        # The no-check consumer uses its ordinary self-target context; the
        # separate first case owns this source's actual mapless target relation.
        self.e.end_scene()
        self.b.moves.append('move/빛의장막')
        self.begin(self.b)
        self.e.use_move(self.b, self.b, 'move/빛의장막')
        self.assertEqual(self.state(), before)
        self.assertEqual(self.b.budget['standard'], 0)
        self.assertEqual(self.b.move_uses['move/빛의장막'], 1)
        # A damaging never-miss Move still has its real critical/effect natural.
        with patch.object(self.e, 'd20', side_effect=AssertionError('enemy uses its sheet')):
            self.assertEqual(self.e.accuracy_check(self.b, self.a, self.r.move('move/스피드스타')), (True, 20, True))
        self.assertEqual(self.state()['cursor'], 1)

    def test_native_shared_area_consumes_one_natural_for_all_actual_recipients(self):
        self.adopt([16, 1])
        self.targets(self.b, [self.a, self.c], mid='move/방전')
        self.begin(self.b)
        before = [actor.hp for actor in (self.a, self.b, self.c, self.d)]
        with patch.object(self.e, 'd20', side_effect=AssertionError('shared enemy natural uses its sheet')):
            self.e.use_move_on(self.b, self.a, 'move/방전', self.e.everyone)
        self.assertLess(self.a.hp, before[0])
        self.assertLess(self.c.hp, before[2])
        self.assertEqual([self.b.hp, self.d.hp], [before[1], before[3]])
        self.assertIn('마비', self.a.conditions)
        self.assertIn('마비', self.c.conditions)
        self.assertEqual(self.state()['cursor'], 1)
        self.assertEqual((self.b.budget['standard'], self.b.move_uses['move/방전']), (0, 1))
        self.assertFalse(getattr(self.e, '_move_activation_scopes', []))

    def test_native_multiple_accuracy_rolls_consume_distinct_faces(self):
        self.adopt([1, 20, 7])
        self.e.rule_effect('move/물대포', 'add', {'type': 'multi_roll', 'rolls': 2},
            reason='existing explicit two-roll native procedure')
        self.targets(self.b, [self.a])
        self.begin(self.b)
        before = self.a.hp
        with patch.object(self.e, 'd20', side_effect=AssertionError('two actual sheet observations')):
            self.e.use_move(self.b, self.a, 'move/물대포', set_damage=True)
        self.assertLess(self.a.hp, before)
        self.assertEqual(self.b.counters['multi_hits'], 1)
        self.assertEqual(self.state()['cursor'], 2)
        self.assertEqual(self.b.move_uses['move/물대포'], 1)

    def test_exhaustion_and_insufficient_multi_sheet_refuse_before_native_payment(self):
        self.adopt([20])
        move = self.r.move('move/물대포')
        self.e.accuracy_check(self.b, self.a, move)
        self.targets(self.b, [self.a])
        self.begin(self.b)
        before = self.snap()
        with patch.object(self.e, 'd20', side_effect=AssertionError('no RNG fallback on exhaustion')):
            with self.assertRaisesRegex(ValueError, 'exhausted'):
                self.e.use_move(self.b, self.a, move['id'], set_damage=True)
        self.assertEqual(self.snap(), before)
        self.adopt([1], sheet_id='next-sheet')
        self.e.rule_effect(move['id'], 'add', {'type': 'multi_roll', 'rolls': 2},
            reason='existing explicit two-roll native procedure')
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'exhausted'):
            self.e.use_move(self.b, self.a, move['id'], set_damage=True)
        self.assertEqual(self.snap(), before)

    def test_refused_action_and_unobserved_target_do_not_consume_sheet(self):
        self.adopt([20])
        self.targets(self.b, [self.a])
        self.begin(self.b)
        self.b.budget['standard'] = 0
        before = deepcopy(self.state())
        self.assertEqual(self.e.use_move(self.b, self.a, 'move/물대포', set_damage=True), 0)
        self.assertEqual(self.state(), before)
        self.assertNotIn('move/물대포', self.b.move_uses)
        self.b.budget['standard'] = 1
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.e.use_move(self.b, self.d, 'move/물대포', set_damage=True)
        self.assertEqual(self.state(), before)

    def test_invalid_external_sheet_inputs_never_adopt_or_mutate(self):
        for change in ({'faces': []}, {'faces': [True]}, {'faces': [0]}, {'faces': [21]},
                       {'enemy_ids': []}, {'enemy_ids': [self.b.entity_id, self.b.entity_id]},
                       {'enemy_ids': [self.a.entity_id]}, {'enemy_ids': ['unregistered-enemy']},
                       {'reason': ''}, {'sheet_id': ''}):
            with self.subTest(change=change):
                values = dict(sheet_id='session-sheet', enemy_ids=[self.b.entity_id],
                              faces=[20], reason='explicit adopted external sheet')
                values.update(change)
                before = self.snap()
                with self.assertRaises(ValueError):
                    self.e.gm.adopt_enemy_accuracy_sheet(**values)
                self.assertEqual(self.snap(), before)
                self.assertFalse(hasattr(self.e, FAST.FIELD))

    def test_replay_never_rewinds_and_next_explicit_sheet_requires_exhaustion(self):
        first = self.adopt([1, 20])
        self.e.accuracy_check(self.b, self.a, self.r.move('move/물대포'))
        before = self.snap()
        self.assertEqual(self.adopt([1, 20]), first)
        self.assertEqual(self.snap(), before)
        for values in ({'faces': [20, 1]}, {'faces': [2], 'sheet_id': 'next-sheet'}):
            with self.assertRaises(ValueError):
                self.adopt(**values)
            self.assertEqual(self.snap(), before)
        self.e.accuracy_check(self.c, self.a, self.r.move('move/물대포'))
        second = self.adopt([7], sheet_id='next-sheet')
        self.assertNotEqual(first, second)
        before = self.snap()
        self.assertEqual(self.adopt([1, 20]), first)
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.e.accuracy_check(self.b, self.a, self.r.move('move/물대포'))[1], 7)
        self.assertEqual(self.state()['cursor'], 1)

    def test_gm_and_json_restore_preserve_sheet_cursor_and_native_consumption(self):
        self.adopt([1, 20, 7])
        move = self.r.move('move/물대포')
        self.assertEqual(self.e.accuracy_check(self.b, self.a, move)[1], 1)
        saved = self.e.gm.snapshot()
        payload = json.loads(json.dumps(self.snap(), ensure_ascii=False))
        loaded = load_engine(self.r, payload)
        actors = W.actor_index(loaded)
        b, a = actors[self.b.entity_id], actors[self.a.entity_id]
        self.assertEqual(loaded.accuracy_check(b, a, move), (True, 20, True))
        self.assertEqual(getattr(loaded, FAST.FIELD)['cursor'], 2)
        self.assertEqual(self.e.accuracy_check(self.b, self.a, move)[1], 20)
        self.e.gm.restore(saved)
        self.assertEqual(self.state()['cursor'], 1)
        self.assertEqual(self.e.accuracy_check(self.b, self.a, move)[1], 20)
        self.assertEqual(self.state()['cursor'], 2)
        self.e.end_encounter()
        self.assertEqual(self.state()['cursor'], 2)
        self.e.end_scene()
        self.assertEqual(self.state()['cursor'], 2)

    def test_restore_rejects_changed_sheet_and_cursor_before_world_commit(self):
        self.adopt([1, 20])
        saved = self.e.gm.snapshot()
        before = self.snap()
        stored = self.e.gm.snapshots[saved]['engine'][FAST.FIELD]
        stored['cursor'] = 3
        with self.assertRaisesRegex(ValueError, 'cursor'):
            self.e.gm.restore(saved)
        self.assertEqual(self.snap(), before)
        stored['cursor'] = 0
        stored['declaration']['faces'][0] = 20
        with self.assertRaisesRegex(ValueError, 'declaration changed'):
            self.e.gm.restore(saved)
        self.assertEqual(self.snap(), before)

    def test_actual_source_authority_is_rechecked_without_consuming_the_sheet(self):
        self.adopt([20])
        self.targets(self.b, [self.a])
        self.begin(self.b)
        before = self.snap()
        original = SOURCE_CONTEXT.verified_source
        def changed_source(rules, reference, **options):
            if reference == FAST.REFERENCE:
                raise ValueError('enemy accuracy sheet source changed; review required')
            return original(rules, reference, **options)
        with patch.object(SOURCE_CONTEXT, 'verified_source', side_effect=changed_source):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                self.e.use_move(self.b, self.a, 'move/물대포', set_damage=True)
        self.assertEqual(self.snap(), before)


if __name__ == '__main__':
    unittest.main()
