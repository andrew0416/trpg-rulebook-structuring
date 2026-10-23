"""A resumed historical condition can first emit an actual native child."""
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


class ConditionNativeChildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.EndTurnResumeTests.setUpClass()

    def setUp(self):
        self.c = BASE.EndTurnResumeTests(methodName='runTest')
        self.c.setUp()

    def suspend(self, *, suffix=True):
        c = self.c
        self.has_suffix = suffix
        effects = [dict(type='apply_status', status='독', target='self',
                        **{'if':'target was asleep'})]
        if suffix:
            effects.append(c.stage('spe'))
        self.b, self.returned = c.native_status_child(
            [c.stage('spa', conditional=True), c.stage('spd')], effects)
        self.a_token = self.returned['receipt']
        self.prefix_hp = c.a.hp
        self.assertEqual(self.returned['status'], 'awaiting_input')
        self.assertIs(c.e._active_turn_actor, c.a)
        self.assertEqual(len(c.e._turn_closures), 2)
        self.assertEqual({r['source_id'] for r in c.e._effect_dispatch_receipts.values()},
                         {FIXTURE.SOURCE_A})

    def resume_a(self, truth=True):
        c = self.c
        before = dump_engine(c.e)
        try:
            c.resolve(self.a_token, truth)
        except ValueError as ex:
            print('EXACT_CONDITION_CHILD_BEFORE', json.dumps(dict(
                error=str(ex), unchanged=dump_engine(c.e)==before,
                closures=len(c.e._turn_closures), active_is_original=c.e._active_turn_actor is c.a)))
            raise
        self.b_token = next((t for t, r in c.e._effect_dispatch_receipts.items()
                             if r['source_id'] == FIXTURE.SOURCE_B and r['status'] == 'condition_unknown'), None)
        self.assertEqual(c.a.stages['spe'], int(self.has_suffix))
        self.assertEqual(c.a.hp, self.prefix_hp)
        if not truth:
            self.assertIsNone(self.b_token)
            self.assertNotIn('독', c.a.conditions)
            return
        self.assertIn('독', c.a.conditions)
        self.assertIs(c.e._active_turn_actor, c.a)
        self.assertEqual(len(c.e._turn_closures), 2)
        row = c.e._effect_dispatch_receipts[self.b_token]
        self.assertIs(row['actor'], self.b)
        self.assertIs(row['target'], c.a)
        self.assertEqual(row['condition_request']['boundary'], CONTRACTS.boundary(c.e, self.b, c.a))
        meta = next(r['turn_end_close'] for r in c.e._effect_dispatch_receipts.values() if 'turn_end_close' in r)
        self.assertIn(self.b_token, ACTION._turn_end_members(c.e, meta))
        self.assertEqual(set(meta['profiles']), {FIXTURE.SOURCE_A, FIXTURE.SOURCE_B})
        self.assertEqual((self.b.stages['spa'], self.b.stages['spd']), (0, 0))

    def resume_b(self, truth=True):
        return self.c.e.resolve_effect_condition(self.b, self.b_token, target_was_asleep=truth,
                                                reason='actual condition-born native child observation')

    def assert_closed(self, *, child=True, truth=True):
        c = self.c
        self.assertIsNone(c.e._active_turn_actor)
        self.assertEqual(len(c.e._turn_closures), 3)
        self.assertIs(c.e._turn_closures[-1]['actor'], c.a)
        self.assertEqual((self.b.stages['spa'], self.b.stages['spd']),
                         (int(child and truth), int(child)))
        self.assertEqual(c.a.stages['spe'], int(self.has_suffix))
        self.assertEqual(c.a.hp, self.prefix_hp)
        self.assertEqual(FREQ.state(c.a)['activations'][FIXTURE.SOURCE_A]['used'], 1)
        self.assertEqual(c.a._action_history, ['free'])
        if child:
            self.assertEqual(FREQ.state(self.b)['activations'][FIXTURE.SOURCE_B]['used'], 1)

    def restore_json(self):
        c = self.c
        c.e = load_engine(c.f.r, json.loads(json.dumps(dump_engine(c.e), ensure_ascii=False)))
        c.a = next(a for a in c.e.everyone if a.name == 'Authored declaration owner')
        self.b = next(a for a in c.e.everyone if a.name == 'Actual prior native attacker')
        self.rebind_receipts()

    def rebind_receipts(self):
        c = self.c
        self.a_token = next(t for t, r in c.e._effect_dispatch_receipts.items()
                            if r['source_id'] == FIXTURE.SOURCE_A and 'condition_request' in r)
        self.b_token = next((t for t, r in c.e._effect_dispatch_receipts.items()
                             if r['source_id'] == FIXTURE.SOURCE_B and 'condition_request' in r), None)

    def test_condition_head_native_child_waits_then_closes_original_turn_once(self):
        self.suspend(); self.resume_a(); self.resume_b(); self.assert_closed()
        before = dump_engine(self.c.e)
        self.c.resolve(self.a_token); self.resume_b()
        self.assertEqual(dump_engine(self.c.e), before)

    def test_final_condition_without_suffix_keeps_its_native_child(self):
        self.suspend(suffix=False); self.resume_a(); self.resume_b(); self.assert_closed()

    def test_false_head_emits_no_child_and_finishes_original_suffix(self):
        self.suspend(); self.resume_a(False); self.assert_closed(child=False)

    def test_false_native_child_finishes_only_its_suffix(self):
        self.suspend(); self.resume_a(); self.resume_b(False); self.assert_closed(truth=False)

    def test_json_and_gm_restore_before_and_after_condition_child_issuance(self):
        self.suspend(); self.restore_json(); self.resume_a(); self.restore_json()
        self.resume_b(); self.assert_closed()
        self.setUp(); self.suspend()
        c = self.c
        c.e.gm.snapshot('before-condition-native-child')
        self.resume_a()
        c.e.gm.snapshot('after-condition-native-child')
        self.resume_b(); self.assert_closed()
        c.e.gm.restore('after-condition-native-child', reason='restore actual launched child')
        self.rebind_receipts()
        self.resume_b(); self.assert_closed()
        c.e.gm.restore('before-condition-native-child', reason='restore original condition')
        self.rebind_receipts()
        self.resume_a(); self.resume_b(); self.assert_closed()

    def test_late_native_close_fault_rolls_back_child_observation_and_retry(self):
        self.suspend(); self.resume_a()
        before = dump_engine(self.c.e)
        actual = TIME.end_turn
        def fail_after_close(engine, actor):
            actual(engine, actor)
            raise ValueError('late condition-child native close fault')
        with patch.object(TIME, 'end_turn', side_effect=fail_after_close):
            with self.assertRaisesRegex(ValueError, 'late condition-child native close fault'):
                self.resume_b()
        self.assertEqual(dump_engine(self.c.e), before)
        self.resume_b(); self.assert_closed()

    def test_actual_child_owner_source_boundary_and_revocation_remain_independent(self):
        self.suspend(); self.resume_a()
        c = self.c
        before = dump_engine(c.e)
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
        self.assertTrue(c.a.active_effects.remove(c.e, 'external-row:' + FIXTURE.SOURCE_A))
        self.assertTrue(self.b.active_effects.remove(c.e, 'external-row:native-child'))
        self.assertEqual((c.a.ability_triggers, self.b.ability_triggers), ([], []))
        self.restore_json(); self.resume_b(); self.assert_closed()


if __name__ == '__main__':
    unittest.main()
