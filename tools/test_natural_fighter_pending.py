"""Authored acceptance cases; source-only, no local execution or PASS claim."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_natural_fighter_native as BASE
from engine import Engine, Rules
import action_points as AP
import book_survivalist_fixture as FIX
import natural_fighter as NF
import passive_events as PASSIVE
import state_grants as G
import heavy_injury_adapter as HEAVY
import combat_move_reactions as REACTION


class NaturalFighterPendingTests(unittest.TestCase):
    scene = BASE.NaturalFighterTests.scene
    cast = BASE.NaturalFighterTests.cast
    snap = BASE.NaturalFighterTests.snap
    reject_unchanged = BASE.NaturalFighterTests.reject_unchanged

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='all')

    def restore(self):
        self.e, index = FIX.restore(self.rules, self.e)
        self.t, self.p, self.foe, self.actor = [index[a.entity_id] for a in
                                              (self.t, self.p, self.foe, self.actor)]

    def dodge(self, actor):
        G.replace_baseline(self.e, actor, 'abilities', ['회피'])
        self.e.watch_move_defense(actor, [{'actor_id': actor.entity_id, 'source': 'ability/회피'}],
                                 reason='actual optional defense before this native hit')

    def wait(self, terrain='wetland'):
        with patch.object(Engine, 'd20', return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                self.cast(terrain, target=self.foe)
        return self.e._passive_pending

    def costs(self, actor=None):
        actor = actor or self.actor
        return (AP.available(self.t), deepcopy(actor.budget),
                deepcopy(actor.move_uses), list(actor._action_history))

    def test_native_defense_wait_survives_restore_resumes_once_and_revokes_permission(self):
        self.scene(terrain='wetland')
        self.dodge(self.foe)
        ap, hp = AP.available(self.t), self.foe.hp
        event = self.wait()
        record = NF.current(self.actor)
        identity, completion = record['id'], record['completion_id']
        self.assertEqual(record['payment']['amount'], 1)
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.t.budget['standard'], 0)
        self.assertEqual(self.t.move_uses[NF.MOVES['wetland']], 1)
        self.assertEqual(self.foe.hp, hp)
        self.restore()
        self.assertEqual(NF.current(self.actor)['id'], identity)
        before = self.costs()
        self.e.choose_move_defense(event, self.foe, use=False, reason='decline actual Dodge')
        self.assertEqual(self.costs(), before)
        self.assertLess(self.foe.hp, hp)
        self.assertEqual(self.foe.accuracy_stage, -1)
        self.assertEqual(self.e._move_completions[completion]['phase'], 'complete')
        self.assertIsNone(NF.current(self.actor))
        self.assertNotIn(identity, self.actor.spec[G.KEY]['sources'])
        self.assertNotIn(NF.MOVES['wetland'], self.actor.moves)
        finished = self.snap()
        self.e.deliver_passive_event(event)
        self.assertEqual(self.snap(), finished)
        self.restore()
        self.assertEqual(self.actor.spec[NF.KEY][identity]['phase'], 'complete')

    def test_pending_permission_cannot_start_another_group_or_direct_target(self):
        self.scene(terrain='wetland')
        self.dodge(self.foe)
        self.wait()
        before = self.snap()
        for call in (lambda: self.cast('wetland', target=self.foe),
                     lambda: self.e.use_move_on(self.t, self.foe, NF.MOVES['wetland'], self.e.everyone),
                     lambda: self.e.use_move(self.t, self.foe, NF.MOVES['wetland'])):
            with self.assertRaises((ValueError, PASSIVE.PassiveEventPending)):
                call()
            self.assertEqual(self.snap(), before)

    def test_restored_cancelled_recipient_keeps_cost_and_cleans_permission(self):
        self.scene(terrain='wetland')
        self.dodge(self.foe)
        event = self.wait()
        identity = NF.current(self.actor)['id']
        hp, cost = self.foe.hp, self.costs()
        self.restore()
        self.e.gm.set_hp(self.actor, 0, reason='actual GM-observed knockout during defense wait')
        self.e.choose_move_defense(event, self.foe, use=False, reason='decline now cancelled attack')
        self.assertEqual(self.foe.hp, hp)
        self.assertEqual(self.costs(), cost)
        self.assertIsNone(NF.current(self.actor))
        self.assertNotIn(identity, self.actor.spec[G.KEY]['sources'])
        self.assertEqual(self.actor.spec[NF.KEY][identity]['phase'], 'cancelled')
        self.restore()

    def test_area_wait_keeps_remaining_native_targets_and_single_payment(self):
        self.scene(terrain='grassland')
        self.dodge(self.foe)
        ap = AP.available(self.t)
        with patch.object(Engine, 'd20', return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                self.cast('grassland')
        event = self.e._passive_pending
        identity = NF.current(self.actor)['id']
        self.restore()
        self.e.choose_move_defense(event, self.foe, use=False, reason='decline actual area Dodge')
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.t.move_uses[NF.MOVES['grassland']], 1)
        self.assertEqual(self.p.stages['spe'], -2)
        self.assertEqual(self.foe.stages['spe'], -2)
        self.assertNotIn(identity, self.t.spec[G.KEY]['sources'])
        self.assertIsNone(NF.current(self.t))

    def test_precompletion_sucker_punch_wait_resumes_or_cancels_original_paid_group(self):
        for knocked_out in (False, True):
            with self.subTest(knocked_out=knocked_out):
                self.scene(terrain='wetland', foe_moves=['move/기습'])
                self.dodge(self.t)
                REACTION.arm(self.e, self.foe, 'move/기습')
                if knocked_out:
                    self.e.gm.set_hp(self.t, 1, reason='actual fragile attacker before initiation')
                ap, target_hp = AP.available(self.t), self.foe.hp
                event = self.wait()
                record = NF.current(self.t)
                identity = record['id']
                self.assertIsNone(record['completion_id'])
                self.assertEqual(AP.available(self.t), ap - 1)
                self.assertEqual(self.t.budget['standard'], 0)
                self.assertEqual(self.t.move_uses.get(NF.MOVES['wetland'], 0), 0)
                self.restore()
                with patch.object(Engine, 'd20', return_value=18):
                    self.e.choose_move_defense(event, self.t, use=False, reason='decline actual Sucker Punch defense')
                self.assertEqual(AP.available(self.t), ap - 1)
                self.assertEqual(self.t.budget['standard'], 0)
                self.assertEqual(self.t.move_uses[NF.MOVES['wetland']], 1)
                self.assertEqual(self.foe.move_uses['move/기습'], 1)
                self.assertIsNone(NF.current(self.t))
                self.assertNotIn(identity, self.t.spec[G.KEY]['sources'])
                if knocked_out:
                    self.assertEqual(self.foe.hp, target_hp)
                    self.assertEqual(self.t.spec[NF.KEY][identity]['phase'], 'cancelled')
                else:
                    self.assertLess(self.foe.hp, target_hp)
                    self.assertEqual(self.foe.accuracy_stage, -1)
                    self.assertEqual(self.t.spec[NF.KEY][identity]['phase'], 'complete')
                self.restore()

    def test_heavy_preserves_paid_prefix_until_actual_external_disposition(self):
        self.scene(terrain='wetland')
        self.foe.injuries = 5
        ap, hp = AP.available(self.t), self.foe.hp
        with patch.object(Engine, 'd20', return_value=18):
            with self.assertRaises(HEAVY.HeavyPending):
                self.cast('wetland', target=self.foe)
        record = NF.current(self.t)
        identity, event = record['id'], record['heavy_event']
        self.assertLess(self.foe.hp, hp)
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.t.budget['standard'], 0)
        self.assertEqual(self.t.move_uses[NF.MOVES['wetland']], 1)
        self.assertFalse(self.e._heavy_events[event]['continuation_reified'])
        cost = self.costs()
        self.restore()
        self.reject_unchanged('acknowledge', lambda: NF.finish_heavy(self.e, self.t, subject=self.t))
        packet = self.e._heavy_events[event]
        HEAVY.acknowledge_ruling(self.e, event, packet['target'],
            expected_current_state=HEAVY.observe(packet['target']),
            ruling='GM resolves actual Heavy consequences without replaying attack',
            disposition=HEAVY.ContinuationDisposition.CANCELLED_BY_RULING,
            continuation_reason='remaining Move suffix explicitly abandoned')
        result = self.e.survivalist_activity(self.t, 'natural_fighter_finish_heavy', subject=self.t)
        self.assertFalse(result['native_resume'])
        self.assertEqual(self.costs(), cost)
        self.assertNotIn(identity, self.t.spec[G.KEY]['sources'])
        self.assertEqual(self.t.spec[NF.KEY][identity]['phase'], 'heavy_adjudicated')
        self.restore()

    def test_saved_payment_or_permission_binding_changes_are_rejected(self):
        for field in ('payment', 'completion', 'permission'):
            with self.subTest(field=field):
                self.scene(terrain='wetland')
                self.dodge(self.foe)
                self.wait()
                record = NF.current(self.t)
                if field == 'payment':
                    record['payment']['amount'] = 0
                elif field == 'completion':
                    record['completion_id'] = 'move-complete:missing'
                else:
                    self.t.spec[G.KEY]['sources'][record['id']]['owner_id'] = self.foe.entity_id
                with self.assertRaises(ValueError):
                    FIX.restore(self.rules, self.e)


    def test_restored_initiation_can_suspend_again_at_original_recipient(self):
        self.scene(terrain='wetland', foe_moves=['move/기습'])
        self.dodge(self.t)
        self.dodge(self.foe)
        REACTION.arm(self.e, self.foe, 'move/기습')
        ap = AP.available(self.t)
        first = self.wait()
        self.restore()
        with patch.object(Engine, 'd20', return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                self.e.choose_move_defense(first, self.t, use=False, reason='decline actual response defense')
        second = self.e._passive_pending
        self.assertNotEqual(first, second)
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.t.move_uses[NF.MOVES['wetland']], 1)
        self.restore()
        before = self.costs()
        self.e.choose_move_defense(second, self.foe, use=False, reason='decline original Move defense')
        self.assertEqual(self.costs(), before)
        self.assertEqual(self.foe.accuracy_stage, -1)
        self.assertIsNone(NF.current(self.t))
        self.restore()

    def test_successful_completion_cannot_be_relabelled_as_heavy_adjudicated(self):
        self.scene(terrain='wetland')
        with patch.object(Engine, 'd20', return_value=18):
            result = self.cast('wetland', target=self.foe)
        self.restore()
        record = self.t.spec[NF.KEY][result['activation_id']]
        self.assertEqual(record['phase'], 'complete')
        self.assertIsNone(record['heavy_event'])
        proof = record['cost_proof']
        record['phase'] = 'heavy_adjudicated'
        self.assertEqual(record['cost_proof'], proof)
        with self.assertRaisesRegex(ValueError, 'terminal classification'):
            FIX.restore(self.rules, self.e)

    def test_successful_completion_cannot_be_relabelled_as_cancelled(self):
        self.scene(terrain='wetland')
        with patch.object(Engine, 'd20', return_value=18):
            result = self.cast('wetland', target=self.foe)
        self.restore()
        record = self.t.spec[NF.KEY][result['activation_id']]
        completion = self.e._move_completions[record['completion_id']]
        self.assertTrue(completion['results'][self.foe.entity_id]['hit'])
        self.assertFalse(completion['results'][self.foe.entity_id]['cancelled'])
        proof = record['cost_proof']
        record['phase'] = 'cancelled'
        self.assertEqual(record['cost_proof'], proof)
        with self.assertRaisesRegex(ValueError, 'terminal classification'):
            FIX.restore(self.rules, self.e)

    def test_actual_cancelled_completion_cannot_be_relabelled_as_complete(self):
        self.scene(terrain='wetland')
        self.dodge(self.foe)
        event = self.wait()
        identity = NF.current(self.t)['id']
        self.e.gm.set_hp(self.t, 0, reason='actual GM-observed knockout before recipient return')
        self.e.choose_move_defense(event, self.foe, use=False, reason='decline cancelled native attack')
        self.restore()
        record = self.t.spec[NF.KEY][identity]
        self.assertEqual(record['phase'], 'cancelled')
        self.assertTrue(all(r['cancelled'] for r in self.e._move_completions[record['completion_id']]['results'].values()))
        record['phase'] = 'complete'
        with self.assertRaisesRegex(ValueError, 'terminal classification'):
            FIX.restore(self.rules, self.e)

    def test_resealed_terminal_claim_still_requires_actual_native_disposition(self):
        for phase, reason in (('cancelled', 'all-cancelled native results'),
                              ('heavy_adjudicated', 'actual external disposition')):
            with self.subTest(phase=phase):
                self.scene(terrain='wetland')
                with patch.object(Engine, 'd20', return_value=18):
                    result = self.cast('wetland', target=self.foe)
                self.restore()
                record = self.t.spec[NF.KEY][result['activation_id']]
                record['phase'] = phase
                record['termination']['phase'] = phase
                # Keep the source receipt internally consistent; native evidence
                # still describes a successful Move with no Heavy adjudication.
                record['cost_proof'] = NF._proof(record)
                with self.assertRaisesRegex(ValueError, reason):
                    FIX.restore(self.rules, self.e)

if __name__ == '__main__':
    unittest.main()



