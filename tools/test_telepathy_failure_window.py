"""Selected PTK behavior and explicitly authored communication stacking.

The selected native policy fills the Korean omission from explicit English wording.
Authored communication declarations retain their independent single/cumulative choice.
"""
from copy import deepcopy
from unittest.mock import patch
import unittest

import test_category2_far_reading as _fixture
import aura_pulse as A
import perception_communicate as M
import roll_context as R
import state_codec as CODEC
import state_grants as G
import telepathy as T


class TelepathyFailureWindowTests(unittest.TestCase):
    setUpClass = classmethod(_fixture.FarReadingTests.setUpClass.__func__)
    setUp = _fixture.FarReadingTests.setUp
    add = _fixture.FarReadingTests.add
    pokemon = _fixture.FarReadingTests.pokemon
    restored = _fixture.FarReadingTests.restored
    snap = _fixture.FarReadingTests.snap
    allow = _fixture.FarReadingTests.allow
    thought = _fixture.FarReadingTests.thought
    read = _fixture.FarReadingTests.read
    fixed = _fixture.FarReadingTests.fixed

    def declared(self, stacking=None):
        value = deepcopy(T.policy(self.r)['declaration'])
        value.update(id='authored:communication-retry', source=A.SOURCE, capabilities=['Aura Pulse'])
        value['retry']['penalty'].pop('stacking', None)
        if stacking is not None:
            value['retry']['penalty']['stacking'] = stacking
        G.grant(self.p, 'capabilities', 'Aura Pulse', 'fixture:authored-communication', 'fixture')
        return value

    def send_declared(self, value, request, *, win=False, target=None):
        target = self.t if target is None else target
        return self.e.communicate(self.p, target, value, 'authored message', request_id=request,
                                  roll_options=self.fixed(win, target))

    def assert_sender_modifier(self, result, modifier, *, win=True, target=None):
        target = self.t if target is None else target
        base = R.plan(self.e, self.p, '집중', purpose='telepathy', target=target)
        self.assertEqual(result['check']['rolls'][0]['total'],
                         (6 if win else 1) * base['dice_count'] + base['modifier'] + modifier)

    def test_selected_ptk_policy_is_unchanged_and_legacy_multiple_failures_stay_single(self):
        policy = T.policy(self.r)
        self.assertEqual(policy['source']['file'], 'input/ch10-index-reference.md')
        # Original ID retained; source correction replaces its former legacy expectation.
        self.assertEqual(policy['declaration']['retry']['penalty']['stacking'], 'cumulative')
        self.thought()
        self.assertEqual(self.read('failure-1', roll_options=self.fixed(False))['reason'], 'opposed_failed')
        self.e.advance_time(60)
        self.assertEqual(self.read('failure-2', roll_options=self.fixed(False))['retry_modifier'], -3)
        result = self.read('after-two', roll_options=self.fixed(True))
        self.assertEqual(result['retry_modifier'], -6)
        self.assert_sender_modifier(result, -6)

    def test_explicit_cumulative_script_rule_sums_each_failure_and_expires_independently(self):
        value = self.declared('cumulative')
        self.assertEqual(self.send_declared(value, 'failure-1')['reason'], 'opposed_failed')
        self.e.advance_time(60)
        second = self.send_declared(value, 'failure-2')
        self.assert_sender_modifier(second, -3, win=False)
        self.assert_sender_modifier(self.send_declared(value, 'two-active', win=True), -6)
        saved = self.e.gm.snapshot()
        self.send_declared(value, 'success-before-restore', win=True)
        self.e.gm.restore(saved)
        actor_ids = (self.a.entity_id, self.p.entity_id, self.t.entity_id)
        self.e = self.restored()
        actors = {actor.entity_id: actor for actor in self.e.everyone}
        self.a, self.p, self.t = (actors[identity] for identity in actor_ids)
        self.e.advance_time(86339)
        self.assert_sender_modifier(self.send_declared(value, 'first-last-second', win=True), -6)
        self.e.advance_time(1)
        self.assert_sender_modifier(self.send_declared(value, 'first-expired', win=True), -3)
        self.e.advance_time(59)
        self.assert_sender_modifier(self.send_declared(value, 'second-last-second', win=True), -3)
        self.e.advance_time(1)
        self.assert_sender_modifier(self.send_declared(value, 'both-expired', win=True), 0)

    def test_authored_omitted_and_explicit_single_keep_legacy_composition(self):
        for stacking in (None, 'single'):
            with self.subTest(stacking=stacking):
                self.setUp()
                value = self.declared(stacking)
                self.send_declared(value, 'failure-1')
                self.send_declared(value, 'failure-2')
                self.assert_sender_modifier(self.send_declared(value, 'after-two', win=True), -3)

    def test_cumulative_pairs_are_directional_and_replay_success_willingness_do_not_reset(self):
        value = self.declared('cumulative')
        first = self.send_declared(value, 'failure-1')
        before = self.snap()
        replay = self.send_declared(value, 'failure-1')
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['check'], first['check'])
        self.assertEqual(self.snap(), before)
        self.assert_sender_modifier(self.send_declared(value, 'success-1', win=True), -3)
        self.e.set_communication_consent(self.t, self.p, A.SOURCE, True, reason='explicit script-rule consent')
        willing = self.send_declared(value, 'willing')
        self.assertIsNone(willing['check'])
        self.e.set_communication_consent(self.t, self.p, A.SOURCE, False, reason='consent revoked')
        self.e.end_scene(self.e.everyone)
        self.assert_sender_modifier(self.send_declared(value, 'still-one', win=True), -3)
        other = self.pokemon(20)
        other.pos = (7, 2)
        self.assert_sender_modifier(self.send_declared(value, 'other-target', win=True, target=other), 0, target=other)
        G.grant(self.t, 'capabilities', 'Aura Pulse', 'fixture:reverse-communication', 'fixture')
        reverse_options = {label: {'fixed': [6 if label == 'sender' else 1] *
                           R.plan(self.e, actor, '집중', purpose='telepathy', target=target)['dice_count']}
                           for label, actor, target in (('sender', self.t, self.p), ('recipient', self.p, self.t))}
        reverse = self.e.communicate(self.t, self.p, value, 'reverse', request_id='reverse',
                                     roll_options=reverse_options)
        base = R.plan(self.e, self.t, '집중', purpose='telepathy', target=self.p)
        self.assertEqual(reverse['check']['rolls'][0]['total'], 6 * base['dice_count'] + base['modifier'])
        self.send_declared(value, 'failure-2')
        self.assert_sender_modifier(self.send_declared(value, 'two-after-success', win=True), -6)

    def test_native_replay_success_willingness_and_restores_preserve_original_failure_deadline(self):
        self.thought()
        failed = self.read('failed', roll_options=self.fixed(False))
        before = self.snap()
        self.assertTrue(self.read('failed', roll_options=self.fixed(False))['replayed'])
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.read('success', roll_options=self.fixed(True))['retry_modifier'], -3)
        self.allow()
        with patch.object(R, 'resolve', wraps=R.resolve) as opposed:
            willing = self.read('willing')
        self.assertEqual(opposed.call_count, 0)
        self.assertFalse(willing['event']['supernatural_trace'])
        self.allow(allowed=False)
        saved = self.e.gm.snapshot()
        self.e.advance_time(60)
        self.e.gm.restore(saved)
        self.assertEqual(self.e.elapsed_seconds, 0)
        loaded = self.restored()
        actors = {actor.entity_id: actor for actor in loaded.everyone}
        loaded.advance_time(86399)
        result = loaded.read_telepathic_thought(actors[self.p.entity_id], actors[self.t.entity_id],
                    request_id='last-second', roll_options=self.fixed(True))
        self.assertEqual(result['retry_modifier'], -3)
        self.assertTrue(result['event']['supernatural_trace'])
        loaded.advance_time(1)
        result = loaded.read_telepathic_thought(actors[self.p.entity_id], actors[self.t.entity_id],
                    request_id='expired', roll_options=self.fixed(True))
        self.assertEqual(result['retry_modifier'], 0)
        before = CODEC.dump_engine(loaded)
        replay = loaded.read_telepathic_thought(actors[self.p.entity_id], actors[self.t.entity_id],
                    request_id='failed', roll_options=self.fixed(False))
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['event'], failed['event'])
        self.assertEqual(CODEC.dump_engine(loaded), before)

    def test_native_blocked_and_unrouted_attempts_do_not_add_opposed_failure_penalties(self):
        self.thought()
        G.grant(self.t, 'capabilities', 'Mindlock', 'fixture:mindlock', 'fixture')
        self.assertEqual(self.read('blocked')['reason'], 'receiver_blocked')
        G.transition(self.e, self.t, lambda engine, actor: G.revoke(actor, 'fixture:mindlock'))
        self.t.pos = (9, 1)
        self.assertEqual(self.read('outside')['reason'], 'out_of_range')
        self.t.pos = (8, 1)
        result = self.read('actual-check', roll_options=self.fixed(True))
        self.assertEqual(result['retry_modifier'], 0)

    def test_invalid_stacking_rejects_atomically_and_registered_policy_cannot_be_relabelled(self):
        value = self.declared('cumulative')
        for bad in (True, None, 2, 'replace'):
            changed = deepcopy(value)
            changed['retry']['penalty']['stacking'] = bad
            before = self.snap()
            with self.assertRaises(ValueError):
                self.send_declared(changed, 'invalid')
            self.assertEqual(self.snap(), before)
        for field, invalid_values in (('retry', (True, 1, 1.0, [], 'retry')),
                                      ('penalty', (None, True, 1, 1.0, [], 'penalty'))):
            for bad in invalid_values:
                with self.subTest(field=field, value=bad):
                    changed = deepcopy(value)
                    if field == 'retry':
                        changed['retry'] = bad
                    else:
                        changed['retry']['penalty'] = bad
                    before = self.snap()
                    with self.assertRaises(ValueError):
                        self.send_declared(changed, 'invalid-shape')
                    self.assertEqual(self.snap(), before)
        for field in ('retry', 'penalty'):
            with self.subTest(unknown_field=field):
                changed = deepcopy(value)
                node = changed['retry'] if field == 'retry' else changed['retry']['penalty']
                node['unknown'] = True
                before = self.snap()
                with self.assertRaises(ValueError):
                    self.send_declared(changed, 'unknown-key')
                self.assertEqual(self.snap(), before)
        self.send_declared(value, 'registered')
        changed = deepcopy(value)
        changed['retry']['penalty']['stacking'] = 'single'
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'source policy'):
            self.send_declared(changed, 'changed-policy')
        self.assertEqual(self.snap(), before)

    def test_native_receipt_validation_does_not_accept_cumulative_without_selected_authority(self):
        self.thought()
        self.read('first-failure', roll_options=self.fixed(False))
        self.read('second-failure', roll_options=self.fixed(False))
        result = self.read('actual', roll_options=self.fixed(True))
        # Cumulative authority now permits -6; nonmultiples and invalid types still fail.
        self.assertEqual(result['retry_modifier'], -6)
        T.validate_result(self.e, result)
        for bad in (-1, True, 3):
            with self.subTest(modifier=bad):
                changed = deepcopy(result)
                changed['retry_modifier'] = bad
                with self.assertRaises(ValueError):
                    T.validate_result(self.e, changed)


if __name__ == '__main__':
    unittest.main()
