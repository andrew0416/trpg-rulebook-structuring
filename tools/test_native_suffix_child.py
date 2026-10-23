"""D16-R1: actual native children first issued by an accepted retained suffix."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import action_lifecycle as ACTION
import combat_timing as TIME
import effect_contracts as CONTRACTS
import frequency as FREQ
from state_codec import dump_engine, load_engine
import test_end_turn_resume as BASE
import test_historical_effect_source_closure as FIXTURE


class NativeSuffixChildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.EndTurnResumeTests.setUpClass()

    def setUp(self):
        self.c = BASE.EndTurnResumeTests(methodName='runTest')
        self.c.setUp()

    def suspend(self, status_effect=None):
        c = self.c
        self.b, self.returned = c.native_status_child(
            [c.stage('spa', conditional=True), c.stage('spd')],
            [c.stage('def', conditional=True),
             status_effect or dict(type='apply_status', status='독', target='self'), c.stage('spe')])
        self.a_token = self.returned['receipt']
        self.assertEqual({r['source_id'] for r in c.e._effect_dispatch_receipts.values()}, {FIXTURE.SOURCE_A})
        self.prefix_hp = c.a.hp
        self.prefix_closures = len(c.e._turn_closures)
        self.assertEqual(self.prefix_closures, 2)

    def resume_a(self):
        c = self.c
        c.resolve(self.a_token)
        self.b_token, row = next((t, r) for t, r in c.e._effect_dispatch_receipts.items()
                                 if r['source_id'] == FIXTURE.SOURCE_B and r['status'] == 'condition_unknown')
        if c.e._active_turn_actor is None:
            errors = []
            for e in (c.e, load_engine(c.f.r, json.loads(json.dumps(dump_engine(c.e))))):
                b = next(actor for actor in e.everyone if actor.name == self.b.name)
                token = next(t for t, r in e._effect_dispatch_receipts.items()
                             if r['source_id'] == FIXTURE.SOURCE_B and r['status'] == 'condition_unknown')
                try:
                    e.resolve_effect_condition(b, token, target_was_asleep=True, reason='actual later native child observation')
                except ValueError as ex:
                    errors.append(str(ex))
            print('EXACT_REVIEW_P1_BEFORE', json.dumps(dict(
                closures_before=self.prefix_closures, closures_after=len(c.e._turn_closures),
                b_live_and_json_errors=errors, b_in_producer_graph=self.b_token in ACTION._turn_end_members(
                    c.e, next(r['turn_end_close'] for r in c.e._effect_dispatch_receipts.values() if 'turn_end_close' in r)))))
        self.assertIs(c.e._active_turn_actor, c.a, 'A must remain open for its newly issued native B child')
        self.assertEqual(len(c.e._turn_closures), 2)
        self.assertIs(row['actor'], self.b)
        self.assertIs(row['target'], c.a)
        self.assertEqual(row['condition_request']['boundary'], CONTRACTS.boundary(c.e, self.b, c.a))
        meta = next(r['turn_end_close'] for r in c.e._effect_dispatch_receipts.values() if 'turn_end_close' in r)
        self.assertIn(self.b_token, ACTION._turn_end_members(c.e, meta))
        self.assertEqual(set(meta['profiles']), {FIXTURE.SOURCE_A, FIXTURE.SOURCE_B})
        self.assertEqual((c.a.stages['def'], c.a.stages['spe'], self.b.stages['spa'], self.b.stages['spd']), (1, 1, 0, 0))
        self.assertIn('독', c.a.conditions)
        self.assertEqual(c.a.hp, self.prefix_hp)

    def resume_b(self, truth=True):
        return self.c.e.resolve_effect_condition(self.b, self.b_token, target_was_asleep=truth,
                                                reason='actual later native child observation')

    def assert_closed(self, truth=True):
        c = self.c
        self.assertIsNone(c.e._active_turn_actor)
        self.assertEqual(len(c.e._turn_closures), 3)
        self.assertIs(c.e._turn_closures[-1]['actor'], c.a)
        self.assertEqual((c.a.stages['def'], c.a.stages['spe'], self.b.stages['spa'], self.b.stages['spd']),
                         (1, 1, int(truth), 1))
        self.assertEqual(c.a.hp, self.prefix_hp)
        self.assertEqual(FREQ.state(c.a)['activations'][FIXTURE.SOURCE_A]['used'], 1)
        self.assertEqual(FREQ.state(self.b)['activations'][FIXTURE.SOURCE_B]['used'], 1)
        self.assertEqual(c.a._action_history, ['free'])

    def restore_json(self):
        c = self.c
        c.e = load_engine(c.f.r, json.loads(json.dumps(dump_engine(c.e), ensure_ascii=False)))
        c.a = next(a for a in c.e.everyone if a.name == 'Authored declaration owner')
        self.b = next(a for a in c.e.everyone if a.name == 'Actual prior native attacker')
        self.a_token = next(t for t, r in c.e._effect_dispatch_receipts.items()
                            if r['source_id'] == FIXTURE.SOURCE_A and 'condition_request' in r)
        self.b_token = next((t for t, r in c.e._effect_dispatch_receipts.items()
                             if r['source_id'] == FIXTURE.SOURCE_B and 'condition_request' in r), None)

    def test_suffix_born_child_waits_and_then_closes_original_turn_once(self):
        self.suspend(); self.resume_a(); self.resume_b(); self.assert_closed()

    def test_false_child_observation_finishes_only_its_suffix(self):
        self.suspend(); self.resume_a(); self.resume_b(False); self.assert_closed(False)

    def test_random_status_native_sibling_keeps_its_rng_and_child_graph(self):
        self.suspend(dict(type='apply_status_random', options=['독'], target='self'))
        before_rng = self.c.e.rng.getstate()
        self.resume_a()
        after_rng = self.c.e.rng.getstate()
        self.assertNotEqual(after_rng, before_rng)
        self.resume_b(); self.assert_closed()
        self.assertEqual(self.c.e.rng.getstate(), after_rng)
        before = dump_engine(self.c.e)
        self.c.resolve(self.a_token); self.resume_b()
        self.assertEqual(dump_engine(self.c.e), before)

    def test_json_preserves_graph_before_and_after_native_child_is_issued(self):
        self.suspend(); self.restore_json(); self.resume_a(); self.restore_json()
        self.resume_b(); self.assert_closed(); self.restore_json()
        before = dump_engine(self.c.e)
        self.resume_b()
        self.assertEqual(dump_engine(self.c.e), before)

    def test_gm_restore_keeps_the_actual_child_and_original_close(self):
        self.suspend(); self.resume_a()
        c = self.c
        c.e.gm.snapshot('actual-suffix-native-child')
        self.resume_b(); self.assert_closed()
        c.e.gm.restore('actual-suffix-native-child', reason='restore actual accepted native child')
        self.b_token = next(t for t, r in c.e._effect_dispatch_receipts.items()
                            if r['source_id'] == FIXTURE.SOURCE_B and r['status'] == 'condition_unknown')
        self.assertIs(c.e._active_turn_actor, c.a)
        self.assertEqual((self.b.stages['spa'], self.b.stages['spd']), (0, 0))
        self.resume_b(); self.assert_closed()

    def test_late_child_close_fault_rolls_back_observation_suffix_and_native_close(self):
        self.suspend(); self.resume_a()
        before = dump_engine(self.c.e)
        actual = TIME.end_turn
        def fail_after_close(engine, actor):
            actual(engine, actor)
            raise ValueError('late suffix-child native close fault')
        with patch.object(TIME, 'end_turn', side_effect=fail_after_close):
            with self.assertRaisesRegex(ValueError, 'late suffix-child native close fault'):
                self.resume_b()
        self.assertEqual(dump_engine(self.c.e), before)
        self.resume_b(); self.assert_closed()

    def test_replay_and_source_owner_boundary_guards_preserve_the_child(self):
        self.suspend(); self.resume_a()
        c = self.c
        before = dump_engine(c.e)
        c.resolve(self.a_token)
        self.assertEqual(dump_engine(c.e), before)
        with self.assertRaisesRegex(ValueError, 'owner'):
            c.e.resolve_effect_condition(c.a, self.b_token, target_was_asleep=True, reason='wrong owner')
        selected = c.f.r._selected_rule
        with patch.object(c.f.r, '_selected_rule', side_effect=lambda uid, *a, **k:
                          uid + '/changed' if uid == FIXTURE.SOURCE_B else selected(uid, *a, **k)):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                self.resume_b()
        c.e.elapsed_seconds += 1
        try:
            with self.assertRaisesRegex(ValueError, 'boundary'):
                self.resume_b()
        finally:
            c.e.elapsed_seconds -= 1
        self.assertEqual(dump_engine(c.e), before)
        for attempt in (lambda: c.e.end_of_turn(c.a), lambda: c.e.advance_time(1, [c.a, self.b])):
            with self.assertRaisesRegex(ValueError, 'turn.end|turn end|turn-end|unfinished'):
                attempt()
            self.assertEqual(dump_engine(c.e), before)
        self.resume_b(); self.assert_closed()
        before = dump_engine(c.e)
        c.resolve(self.a_token); self.resume_b()
        self.assertEqual(dump_engine(c.e), before)

    def test_trigger_revocation_does_not_cancel_the_already_launched_child(self):
        self.suspend(); self.resume_a()
        c = self.c
        self.assertTrue(c.a.active_effects.remove(c.e, 'external-row:' + FIXTURE.SOURCE_A))
        self.assertTrue(self.b.active_effects.remove(c.e, 'external-row:native-child'))
        self.assertEqual((c.a.ability_triggers, self.b.ability_triggers), ([], []))
        self.restore_json(); self.resume_b(); self.assert_closed()


if __name__ == '__main__':
    unittest.main()
