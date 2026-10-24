"""Selected cumulative Telepathy and preserved historical native receipts."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import test_category2_far_reading as _fixture
import roll_context as R
import state_codec as CODEC
import telepathy as T
import perception_communicate as M
import resolution_transaction as TX


class SelectedCumulativeTelepathyWitness(unittest.TestCase):
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
    telepath = _fixture.FarReadingTests.telepath

    def require_selection(self):
        self.assertEqual(T.policy(self.r)['declaration']['retry']['penalty'].get('stacking'), 'cumulative',
                         'Selected omission clarification requires cumulative native Telepathy')

    def test_two_failures_each_expire_at_their_own_exact_deadline_after_both_restores(self):
        self.require_selection()
        self.thought()
        self.assertEqual(self.read('failure-1', roll_options=self.fixed(False))['reason'], 'opposed_failed')
        self.e.advance_time(60)
        self.assertEqual(self.read('failure-2', roll_options=self.fixed(False))['retry_modifier'], -3)
        result = self.read('after-two', roll_options=self.fixed(True))
        self.assertEqual(result['retry_modifier'], -6)
        base = R.plan(self.e, self.p, '집중', purpose='telepathy', target=self.t)
        self.assertEqual(result['check']['rolls'][0]['total'], 6 * base['dice_count'] + base['modifier'] - 6)
        saved = self.e.gm.snapshot()
        self.read('another-success', roll_options=self.fixed(True))
        self.e.gm.restore(saved)
        loaded = self.restored()
        actors = {actor.entity_id: actor for actor in loaded.everyone}
        for advance, key, expected in ((86339, 'first-last-second', -6), (1, 'first-expired', -3),
                                       (59, 'second-last-second', -3), (1, 'both-expired', 0)):
            loaded.advance_time(advance)
            out = loaded.read_telepathic_thought(actors[self.p.entity_id], actors[self.t.entity_id],
                                               request_id=key, roll_options=self.fixed(True))
            self.assertEqual(out['retry_modifier'], expected)
            self.assertTrue(out['event']['supernatural_trace'])

    def test_pair_history_survives_replay_success_consent_and_scene_without_duplicate_failure(self):
        self.require_selection()
        self.thought()
        self.read('failure-1', roll_options=self.fixed(False))
        before = self.snap()
        self.assertTrue(self.read('failure-1', roll_options=self.fixed(False))['replayed'])
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.read('success', roll_options=self.fixed(True))['retry_modifier'], -3)
        self.allow()
        with patch.object(R, 'resolve', wraps=R.resolve) as opposed:
            willing = self.read('willing')
        self.assertEqual(opposed.call_count, 0)
        self.assertFalse(willing['event']['supernatural_trace'])
        self.allow(allowed=False)
        self.e.end_scene(self.e.everyone)
        other = self.pokemon(20)
        other.pos = (7, 2)
        self.thought(other)
        self.assertEqual(self.read('other-pair', other, roll_options=self.fixed(True, other))['retry_modifier'], 0)
        self.assertEqual(self.read('failure-2', roll_options=self.fixed(False))['retry_modifier'], -3)
        self.assertEqual(self.read('two-failures', roll_options=self.fixed(True))['retry_modifier'], -6)
        loaded = self.restored()
        actors = {actor.entity_id: actor for actor in loaded.everyone}
        before = CODEC.dump_engine(loaded)
        replay = loaded.read_telepathic_thought(actors[self.p.entity_id], actors[self.t.entity_id],
                         request_id='two-failures', roll_options=self.fixed(True))
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['retry_modifier'], -6)
        self.assertEqual(CODEC.dump_engine(loaded), before)

    def test_actual_read_and_projection_failures_share_only_the_same_directed_pair(self):
        self.require_selection()
        self.thought()
        self.telepath()
        self.read('read-failure', roll_options=self.fixed(False))
        projected = self.e.project_telepathic_thought(self.p, [self.t], 'projection',
                    request_id='projection-failure', roll_options=self.fixed(False))['results'][0]
        self.assertEqual((projected['reason'], projected['retry_modifier']), ('opposed_failed', -3))
        self.assertEqual(self.read('after-both', roll_options=self.fixed(True))['retry_modifier'], -6)
        reverse_options = {label: {'fixed': [6 if label == 'sender' else 1] *
                           R.plan(self.e, actor, '집중', purpose='telepathy', target=target)['dice_count']}
                           for label, actor, target in (('sender', self.t, self.p), ('recipient', self.p, self.t))}
        reverse = self.e.read_telepathic_thought(self.t, self.p, request_id='reverse', roll_options=reverse_options)
        self.assertEqual(reverse['retry_modifier'], 0)

    @contextmanager
    def previous_policy_file(self):
        # Historical input fixture only: native policy loading, source verification,
        # actual entrypoints and roll consumers all run without a validation bypass.
        current = T.policy(self.r)
        old = deepcopy(current)
        correction = old.pop('source_correction')
        old['declaration']['retry']['penalty'].pop('stacking')
        self.assertEqual(TX.request_fingerprint(M._body(old['declaration'])),
                         correction['previous_declaration_sha256'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            (root / 'data' / 'telepathy-policy.json').write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
            with patch.object(T, 'Path', return_value=root):
                yield old

    def test_previous_native_policy_restores_and_replays_without_rewriting_any_prior_receipt(self):
        self.thought()
        self.telepath()
        with self.previous_policy_file():
            self.read('old-failure-1', roll_options=self.fixed(False))
            self.e.advance_time(60)
            self.read('old-failure-2', roll_options=self.fixed(False))
            previous_success = self.read('old-success', roll_options=self.fixed(True))
            self.assertEqual(previous_success['retry_modifier'], -3)
            previous_group = self.e.project_telepathic_thought(self.p, [self.t], 'old group',
                request_id='old-group', roll_options=self.fixed(False))
            self.assertEqual(previous_group['results'][0]['retry_modifier'], -3)
            previous_offer = self.e.offer_telepathic_thought(self.a, self.p, 'old offer', request_id='old-offer')
            original = deepcopy(M._state(self.e))
            saved = self.e.gm.snapshot()
        # Changing installed policy does not rewrite the snapshot or any historical row.
        self.assertEqual(M._state(self.e), original)
        self.e.gm.restore(saved)
        loaded = self.restored()
        actors = {actor.entity_id: actor for actor in loaded.everyone}
        p, t, a = (actors[x.entity_id] for x in (self.p, self.t, self.a))
        before = CODEC.dump_engine(loaded)
        result = loaded.read_telepathic_thought(p, t, request_id='old-success', roll_options=self.fixed(True))
        self.assertEqual(result, dict(previous_success, replayed=True))
        group = loaded.project_telepathic_thought(p, [t], 'old group', request_id='old-group', roll_options=self.fixed(False))
        self.assertEqual(group, dict(previous_group, replayed=True))
        offer = loaded.offer_telepathic_thought(a, p, 'old offer', request_id='old-offer')
        self.assertEqual(offer, dict(previous_offer, replayed=True))
        self.assertEqual(CODEC.dump_engine(loaded), before)
        fresh = loaded.read_telepathic_thought(p, t, request_id='new-read', roll_options=self.fixed(True))
        self.assertEqual(fresh['retry_modifier'], -9)
        fresh_group = loaded.project_telepathic_thought(p, [t], 'new group', request_id='new-group', roll_options=self.fixed(True))
        self.assertEqual(fresh_group['results'][0]['retry_modifier'], -9)
        state = M._state(loaded)
        self.assertEqual(state['policies'], original['policies'])
        self.assertEqual(state['attempts'][:len(original['attempts'])], original['attempts'])
        self.assertEqual({key: state['requests'][key] for key in original['requests']}, original['requests'])
        self.assertEqual(state['batches']['old-group'], original['batches']['old-group'])
        # Mixed old/new identities remain replayable after a second cold load.
        again = CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(loaded), ensure_ascii=False)))
        idx = {actor.entity_id: actor for actor in again.everyone}
        before = CODEC.dump_engine(again)
        self.assertEqual(again.read_telepathic_thought(idx[p.entity_id], idx[t.entity_id],
            request_id='new-read', roll_options=self.fixed(True)), dict(fresh, replayed=True))
        self.assertEqual(CODEC.dump_engine(again), before)
        again.advance_time(86340)
        self.assertEqual(again.read_telepathic_thought(idx[p.entity_id], idx[t.entity_id],
            request_id='old-first-expired', roll_options=self.fixed(True))['retry_modifier'], -6)
        again.advance_time(60)
        self.assertEqual(again.read_telepathic_thought(idx[p.entity_id], idx[t.entity_id],
            request_id='old-all-expired', roll_options=self.fixed(True))['retry_modifier'], 0)
        self.assertEqual(again.read_telepathic_thought(idx[p.entity_id], idx[t.entity_id],
            request_id='old-success', roll_options=self.fixed(True)), dict(previous_success, replayed=True))

    def test_legacy_compatibility_cannot_authorize_fresh_old_policy_or_changed_request_inputs(self):
        self.thought()
        self.telepath()
        with self.previous_policy_file() as old:
            self.read('old-request', roll_options=self.fixed(False))
            self.e.project_telepathic_thought(self.p, [self.t], 'old text',
                request_id='old-batch', roll_options=self.fixed(True))
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'selected source contract'):
            self.e.communicate(self.p, self.t, old['declaration'], 'new text', request_id='fresh-old')
        self.assertEqual(self.snap(), before)
        with self.assertRaisesRegex(ValueError, 'changed input'):
            self.read('old-request', roll_options=self.fixed(True))
        self.assertEqual(self.snap(), before)
        with self.assertRaisesRegex(ValueError, 'changed input'):
            self.e.project_telepathic_thought(self.p, [self.t], 'different text',
                request_id='old-batch', roll_options=self.fixed(True))
        self.assertEqual(self.snap(), before)
        historical = M._body(old['declaration'])
        for field in ('range', 'delay', 'scope', 'stacking'):
            changed = deepcopy(historical)
            if field == 'range':
                changed['range']['maximum'] = 999
            elif field == 'delay':
                changed['retry']['delay_seconds'] = 1
            elif field == 'scope':
                changed['retry']['scope'] = 'sender'
            else:
                changed['retry']['penalty']['stacking'] = 'single'
            self.assertFalse(T.accepts_stored_policy(self.r, changed))
        self.assertEqual(self.snap(), before)
