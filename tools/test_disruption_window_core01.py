"""Native Disruption window compatibility, atomicity and graph-reference probes.

Source proposal only. Legacy projection deletes only newly added bookkeeping
from a real native saved graph; it does not create hit/payment authority.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import action_points as AP
import move_completion as MC
import state_codec as CODEC
import state_grants as G
import skill_feature_actions as SF
import trainer_feature_acquisition as ACQUIRE
import trickster as TRICK
import turn as TURN
import world_entities as WORLD
import test_disruption_window_review01 as BASE


class DisruptionWindowCoreTests(unittest.TestCase):
    setUp = BASE.DisruptionWindowTests.setUp
    setup = BASE.DisruptionWindowTests.setup
    add = BASE.DisruptionWindowTests.add
    acquire = BASE.DisruptionWindowTests.acquire
    combat = BASE.DisruptionWindowTests.combat
    family = BASE.DisruptionWindowTests.family
    known = BASE.DisruptionWindowTests.known
    native = BASE.DisruptionWindowTests.native
    completed = BASE.DisruptionWindowTests.completed
    valid = BASE.DisruptionWindowTests.valid
    actual_hit = BASE.DisruptionWindowTests.actual_hit
    restored = BASE.DisruptionWindowTests.restored
    reject_unchanged = BASE.DisruptionWindowTests.reject_unchanged
    apply_once = BASE.DisruptionWindowTests.apply_once

    def load(self, saved):
        ids = {key: getattr(self, key).entity_id for key in ('t', 'p', 'q', 'b')}
        self.e = CODEC.load_engine(self.rules, saved)
        actors = WORLD.actor_index(self.e)
        for key, uid in ids.items():
            setattr(self, key, actors[uid])
        self.assertIs(self.e.rulings, self.e.r.rulings)

    def legacy_projection(self, saved):
        saved = deepcopy(saved)
        for node in saved['nodes'].values():
            if node['kind'] != 'dict':
                continue
            keys = {pair[0] for pair in node['items'] if isinstance(pair[0], str)}
            remove = {'disruption_window', 'trigger_children', 'trigger_origins', 'trigger_recorded', 'trigger_move_paid', 'trigger_granted_payment', 'trigger_feature_payments', MC.DISRUPTION_WINDOWS}
            if {'actor', 'source', 'kind', 'id', 'before_effects'} <= keys:
                remove.add('completion_id')
            node['items'] = [pair for pair in node['items']
                             if not isinstance(pair[0], str) or pair[0] not in remove]
        # Removing new bookkeeping references also removes their now-unreachable
        # serialized containers. Keep every node still reachable from the actual
        # Engine root; the normal codec reachability guard stays unchanged.
        reachable, todo = set(), [saved['root']['$ref']]
        while todo:
            uid = todo.pop()
            if uid in reachable:
                continue
            node = saved['nodes'][uid]
            reachable.add(uid)
            values = list(node.get('items', []))
            if node['kind'] == 'dict':
                values = [value for pair in values for value in pair]
            values += [node[key] for key in ('attrs', 'state') if key in node]
            todo.extend(value['$ref'] for value in values
                        if type(value) is dict and '$ref' in value)
        saved['nodes'] = {uid: node for uid, node in saved['nodes'].items()
                          if uid in reachable}
        return saved

    def actual_trickster_child(self, *, foreign=False):
        self.family('벌레', 'Insectoid Utility', 'Disruption Order')
        self.e.gm.set_skill(self.t, '교활', 6, reason='actual Trickster prerequisite')
        ACQUIRE.acquire_static(self.e, self.t, TRICK.CLASS, selection={'source': 'core'},
                               acquisition_request_id='window-core/trickster')
        self.e.gm.set_position(self.b, (3, 2), reason='actual Bug cone and maneuver recipient')
        foreign_id = None
        if foreign:
            self.native(self.q, self.b, 'move/몸통박치기')
            foreign_id = self.completed(self.q)['id']
        self.combat(self.p)
        self.native(self.p, self.b, 'move/실뿜기', aim=(3, 2))
        original = self.completed()['id']
        before = AP.available(self.t)
        self.assertTrue(self.e.trickster_maneuver(
            self.t, self.p, self.b, original, 'manipulate', 'terrorize',
            defender_skill='집중', challenger_options={'fixed': [6] * 6},
            defender_options={'fixed': [1] * 6}))
        self.assertEqual(AP.available(self.t), before - 1)
        return original, foreign_id

    def callback_child(self, *, unrelated=None, accept=False):
        self.family('벌레', 'Insectoid Utility', 'Disruption Order')
        for skill, rank in (('교활', 6), ('곡예', 4), ('통찰', 4)):
            self.e.gm.set_skill(self.t, skill, rank, reason='actual Trickster and Skill Monkey prerequisites')
        ACQUIRE.acquire_static(self.e, self.t, TRICK.CLASS, selection={'source': 'core'},
                               acquisition_request_id='window-callback/trickster')
        ACQUIRE.acquire_static(self.e, self.t, SF.MONKEY,
                               acquisition_request_id='window-callback/monkey')
        self.e.gm.set_position(self.b, (3, 2), reason='actual Bug cone and maneuver recipient')
        if unrelated == 'move':
            self.e.gm.set_movement_capabilities(self.p,
                dict(self.p.spec['movement'], high_jump=1, long_jump=2), basis='current',
                reason='observed actual current jump totals before learning independent Splash')
            self.known(self.p, 'move/튀어오르기')
        self.combat(self.p)
        self.native(self.p, self.b, 'move/실뿜기', aim=(3, 2))
        original = self.completed()['id']
        ap = AP.available(self.t)
        history = list(self.p._action_history)
        observed = []
        def choose(first):
            observed.append(first)
            self.assertIs(self.e._active_turn_actor, self.p)
            if unrelated is not None:
                before = list(self.p._action_history)
                budget = deepcopy(self.p.budget)
                if unrelated == 'move':
                    position = tuple(self.p.pos)
                    self.e.declare_jump_move(self.p, self.p, 'move/튀어오르기',
                        event_id='window-callback/independent-splash',
                        jump=None,
                        reason='independent ordinary Shift Move in observed callback')
                    self.native(self.p, self.p, 'move/튀어오르기')
                    self.assertEqual(tuple(self.p.pos), position)
                    self.assertEqual(self.p.budget['shift'], budget['shift'] - 1)
                    self.assertEqual(self.p.move_uses['move/튀어오르기'], 1)
                    independent = self.completed(self.p, 'move/튀어오르기')
                    self.assertEqual(independent['phase'], 'complete')
                    self.assertEqual(self.p._action_history, before + ['shift'])
                else:
                    self.assertTrue(TURN.spend(self.e, self.p, unrelated, 'ordinary callback action'))
                    self.assertEqual(self.p._action_history, before + [unrelated])
                    if unrelated == 'swift':
                        self.assertEqual(self.p.budget['swift'], budget['swift'] - 1)
            return accept
        self.assertTrue(self.e.trickster_maneuver(
            self.t, self.p, self.b, original, 'manipulate', 'terrorize',
            defender_skill='집중',
            challenger_options={'fixed': [6] * 6, 'roll_id': 'window-callback/challenger',
                'feature': SF.MONKEY, 'feature_options': {'decision': choose, 'reroll_faces': [6] * 6}},
            defender_options={'fixed': [1] * 6, 'roll_id': 'window-callback/defender'}))
        self.assertEqual(len(observed), 1)
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.p._action_history, history + ['free'] + ([] if unrelated is None else ['shift' if unrelated == 'move' else unrelated]))
        event = SF.event(self.e, self.t, 'window-callback/challenger')
        self.assertEqual(event.state, 'final')
        self.assertEqual(event.first, observed[0])
        self.assertEqual(event.final.faces, (6,) * 6)
        self.assertEqual(self.t.spec.get('frequency_state', {}).get('activations', {}).get(SF.MONKEY, {}).get('used', 0), int(accept))
        return original

    def test_native_observed_callback_ordinary_swift_closes_original_hit_window(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                original = self.callback_child(unrelated='swift')
                if cold:
                    self.restored()
                self.reject_unchanged(original)

    def test_native_observed_callback_ordinary_free_closes_original_hit_window(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                original = self.callback_child(unrelated='free')
                if cold:
                    self.restored()
                self.reject_unchanged(original)

    def test_native_observed_callback_independent_splash_move_closes_original_hit_window(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                original = self.callback_child(unrelated='move')
                if cold:
                    self.restored()
                self.reject_unchanged(original)
    def test_native_same_hit_maneuver_declined_or_paid_monkey_preserves_original_window(self):
        for accept in (False, True):
            with self.subTest(accept=accept):
                original = self.callback_child(accept=accept)
                self.restored()
                self.apply_once(original)
    def test_legacy_immediate_native_hit_load_is_read_only_and_can_activate_once(self):
        for encounter in (False, True):
            with self.subTest(encounter=encounter):
                original = self.actual_hit(encounter=encounter)
                saved = self.legacy_projection(self.e.export_state())
                untouched = deepcopy(saved)
                self.load(saved)
                self.assertEqual(saved, untouched)
                self.assertNotIn('disruption_window', self.e._move_completions[original])
                self.assertNotIn(MC.DISRUPTION_WINDOWS, self.p.custom_conditions)
                self.valid()
                self.assertNotIn('disruption_window', self.e._move_completions[original])
                self.apply_once(original)

    def test_legacy_actual_paid_trickster_child_preserves_current_parent_without_repayment(self):
        original, _ = self.actual_trickster_child()
        ap, history = AP.available(self.t), list(self.p._action_history)
        self.load(self.legacy_projection(self.e.export_state()))
        self.assertEqual(AP.available(self.t), ap)
        self.assertEqual(self.p._action_history, history)
        self.apply_once(original)
        self.assertEqual(AP.available(self.t), ap)

    def test_legacy_missing_causal_current_trigger_does_not_create_old_credit(self):
        original = self.actual_hit()
        self.assertTrue(TURN.spend(self.e, self.p, 'free', 'actual unrelated ordinary action'))
        self.load(self.legacy_projection(self.e.export_state()))
        self.assertNotIn('disruption_window', self.e._move_completions[original])
        self.reject_unchanged(original)

    def test_failed_actual_action_permission_does_not_close_or_pay_hit_window(self):
        original = self.actual_hit()
        before = (deepcopy(self.p.budget), list(self.p._action_history), AP.available(self.t),
                  self.e.rng.getstate(), deepcopy(self.e._move_completions[original]['disruption_window'], {id(self.p): self.p}))
        self.assertFalse(TURN.spend(self.e, self.p, 'standard', 'actual unavailable second Standard'))
        after = (deepcopy(self.p.budget), list(self.p._action_history), AP.available(self.t),
                 self.e.rng.getstate(), deepcopy(self.e._move_completions[original]['disruption_window'], {id(self.p): self.p}))
        self.assertEqual(after, before)
        self.apply_once(original)

    def test_actual_staged_action_closure_rolls_back_with_existing_native_transaction(self):
        original = self.actual_hit()
        before = self.e.export_state()
        def rejected(staged, actor, *_participants):
            self.assertTrue(TURN.spend(staged, actor, 'swift', 'actual staged ordinary action'))
            self.assertIsNotNone(staged._move_completions[original]['disruption_window']['closed_by'])
            raise ValueError('bounded late-refusal diagnostic')
        with self.assertRaisesRegex(ValueError, 'bounded late-refusal diagnostic'):
            G.transition(self.e, self.p, rejected, participants=(self.t, self.b), include_rulings=True)
        self.assertEqual(self.e.export_state(), before)
        self.apply_once(original)

    def test_saved_actual_index_and_child_parent_cannot_claim_another_native_completion(self):
        original, foreign = self.actual_trickster_child(foreign=True)
        baseline = self.e.export_state()
        self.load(deepcopy(baseline))
        for field in ('index', 'child_parent'):
            with self.subTest(field=field):
                saved = deepcopy(baseline)
                if field == 'index':
                    holders = [node for node in saved['nodes'].values() if node['kind'] == 'dict'
                               and any(pair[0] == MC.DISRUPTION_WINDOWS for pair in node['items'])]
                    lists = [saved['nodes'][next(pair[1] for pair in node['items']
                             if pair[0] == MC.DISRUPTION_WINDOWS)['$ref']] for node in holders]
                    actual = [node for node in lists if original in node['items']]
                    self.assertEqual(len(actual), 1)
                    actual[0]['items'] = [foreign]
                else:
                    frames = [node for node in saved['nodes'].values() if node['kind'] == 'dict'
                              and ['kind', 'maneuver'] in node['items']
                              and any(pair[0] == 'trigger_origins' for pair in node['items'])]
                    self.assertEqual(len(frames), 1)
                    ref = next(pair[1] for pair in frames[0]['items'] if pair[0] == 'trigger_origins')
                    saved['nodes'][ref['$ref']]['items'] = [foreign]
                with self.assertRaises(ValueError):
                    CODEC.load_engine(self.rules, saved)
        self.apply_once(original)

    def test_saved_closed_window_cannot_reopen_by_deleting_only_its_closing_evidence(self):
        original = self.actual_hit()
        self.assertTrue(TURN.spend(self.e, self.p, 'shift', 'actual unrelated ordinary Shift'))
        saved = self.e.export_state()
        windows = [node for node in saved['nodes'].values() if node['kind'] == 'dict'
                   and ['completion_id', original] in node['items']
                   and any(pair[0] == 'closed_by' for pair in node['items'])]
        self.assertEqual(len(windows), 1)
        next(pair for pair in windows[0]['items'] if pair[0] == 'closed_by')[1] = None
        with self.assertRaises(ValueError):
            CODEC.load_engine(self.rules, saved)
        self.reject_unchanged(original)


if __name__ == '__main__':
    unittest.main()
