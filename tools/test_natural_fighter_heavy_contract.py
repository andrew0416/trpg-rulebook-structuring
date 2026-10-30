"""NF-HEAVY follow-up: existing external-disposition contract, source-only tests.

Run only on Root's final composition including class-routes03/awareness04.
This file adds boundary coverage without changing the reviewed pending02 payload.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine, Rules
import test_natural_fighter_class_routes as ROUTES
import book_survivalist_fixture as FIX
import natural_fighter as NF
import natural_fighter_moves as MOVES
import action_points as AP
import attack_damage_history as HISTORY
import combat_timing as TIME
import heavy_injury_adapter as HEAVY
import state_grants as G


class NaturalFighterHeavyContractTests(unittest.TestCase):
    scene = ROUTES.NaturalFighterClassRouteTests.scene
    cast = ROUTES.NaturalFighterClassRouteTests.cast
    next_round = ROUTES.NaturalFighterClassRouteTests.next_round
    snap = ROUTES.NaturalFighterClassRouteTests.snap
    reject_unchanged = ROUTES.NaturalFighterClassRouteTests.reject_unchanged
    observe = ROUTES.NaturalFighterClassRouteTests.observe
    cave_target = ROUTES.NaturalFighterClassRouteTests.cave_target
    setUp = ROUTES.NaturalFighterClassRouteTests.setUp

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='all')

    def restore(self):
        self.e, index = FIX.restore(self.rules, self.e)
        self.t, self.p, self.foe, self.actor = [index[a.entity_id] for a in
                                               (self.t, self.p, self.foe, self.actor)]

    def costs(self):
        return deepcopy((AP.available(self.t), self.actor.budget,
                         self.actor.move_uses, self.actor._action_history))

    def target_wait(self):
        self.scene(terrain='wetland')
        self.foe.injuries = 5
        before_hp = self.foe.hp
        before_accuracy = self.foe.accuracy_stage
        with patch.object(Engine, 'd20', return_value=18):
            with self.assertRaises(HEAVY.HeavyPending):
                self.cast('wetland', target=self.foe)
        record = NF.current(self.actor)
        self.identity = record['id']
        self.completion_id = record['completion_id']
        self.heavy_id = record['heavy_event']
        self.assertLess(self.foe.hp, before_hp)
        self.assertEqual(self.foe.accuracy_stage, before_accuracy)
        return self.costs()

    def acknowledge(self, disposition):
        packet = self.e._heavy_events[self.heavy_id]
        return HEAVY.acknowledge_ruling(self.e, self.heavy_id, packet['target'],
            expected_current_state=HEAVY.observe(packet['target']),
            ruling='TEST ONLY: GM accounted for Heavy and the entire abandoned caller remainder',
            disposition=disposition,
            continuation_reason='TEST ONLY: all remaining effects explicitly resolved or cancelled externally')

    def test_heavy_subject_waits_after_one_paid_activation_before_accuracy_in_eight_routes(self):
        for role in ('trainer', 'partner'):
            for terrain in ('grassland', 'forest', 'wetland', 'ocean', 'tundra',
                            'mountain', 'cave', 'desert'):
                with self.subTest(role=role, terrain=terrain):
                    self.scene(role, terrain)
                    if terrain == 'cave':
                        self.cave_target()
                        self.observe(False)
                    self.actor.injuries = 5
                    before_ap = AP.available(self.t)
                    before_hp = self.actor.hp
                    before_targets = deepcopy([(a.entity_id, a.hp, a.stages, a.conditions)
                                               for a in self.e.everyone])
                    target = None if terrain in NF.SELF_ANCHORS else self.foe
                    with patch.object(Engine, 'd20', side_effect=AssertionError('accuracy must remain unexecuted')):
                        with self.assertRaises(HEAVY.HeavyPending):self.cast(terrain, target=target)
                    record = NF.current(self.actor)
                    packet = self.e._heavy_events[record['heavy_event']]
                    self.assertEqual(packet['producer'], 'Engine.use_move.native_standard')
                    self.assertEqual(packet['kind'], 'activation_observed')
                    self.assertEqual(packet['status'], 'pending')
                    self.assertFalse(packet['semantic_commit_proven'])
                    self.assertIsNone(packet['actual_action_count'])
                    self.assertFalse(packet['continuation_reified'])
                    self.assertEqual(AP.available(self.t), before_ap - 1)
                    self.assertEqual(self.actor.budget['standard'], 0)
                    self.assertEqual(self.actor.move_uses[NF.MOVES[terrain]], 1)
                    self.assertEqual(self.actor.hp, before_hp)
                    self.assertEqual([(a.entity_id, a.hp, a.stages, a.conditions)
                                      for a in self.e.everyone], before_targets)
                    self.assertFalse([r for r in self.e._heavy_standard_receipts.values()
                                      if r['actor'] is self.actor])
                    self.assertEqual(record['phase'], 'waiting')
                    self.assertIn(record['id'], self.actor.spec[G.KEY]['sources'])
                    paid = self.costs()
                    self.restore()
                    self.assertEqual(self.costs(), paid)
                    self.assertEqual(self.e._heavy_pending, record['heavy_event'])

    def test_heavy_target_preserves_damage_but_not_a_fabricated_native_return_or_effect(self):
        for terrain in ('wetland', 'mountain', 'cave'):
            with self.subTest(terrain=terrain):
                self.scene(terrain=terrain)
                if terrain == 'cave':
                    self.cave_target()
                    self.observe(True)
                self.foe.injuries = 5
                hp = self.foe.hp
                before = deepcopy((self.foe.accuracy_stage, self.foe.conditions, TIME.records(self.foe)))
                history = len(HISTORY.records(self.foe))
                with patch.object(Engine, 'd20', return_value=14):
                    with self.assertRaises(HEAVY.HeavyPending):self.cast(terrain, target=self.foe)
                record = NF.current(self.actor)
                packet = self.e._heavy_events[record['heavy_event']]
                completion = self.e._move_completions[record['completion_id']]
                self.assertEqual(packet['producer'], HEAVY.Producer.RESOLVED_HIT.value)
                self.assertEqual(packet['status'], 'pending')
                self.assertFalse(packet['continuation_reified'])
                self.assertLess(self.foe.hp, hp)
                self.assertEqual((self.foe.accuracy_stage, self.foe.conditions, TIME.records(self.foe)), before)
                self.assertEqual(len(HISTORY.records(self.foe)), history)
                self.assertNotIn(self.foe.entity_id, completion['results'])
                self.assertFalse(completion.get('native_returns'))
                self.assertFalse(getattr(self.e, '_attack_history_scopes', {}))
                self.assertFalse(self.e._heavy_native_receipts)
                paid, damaged_hp = self.costs(), self.foe.hp
                self.restore()
                with self.assertRaises(HEAVY.HeavyPending):HEAVY.ensure_clear(self.e)
                self.assertEqual(self.costs(), paid)
                self.assertEqual(self.foe.hp, damaged_hp)

    def test_attacker_faint_during_heavy_wait_does_not_invent_native_cancellation(self):
        paid = self.target_wait()
        self.restore()
        self.e.gm.set_hp(self.actor, 0, reason='actual knockout during unresolved Heavy order')
        self.reject_unchanged('acknowledge',
            lambda: self.e.survivalist_activity(self.t, 'natural_fighter_finish_heavy', subject=self.actor))
        with self.assertRaises(HEAVY.HeavyPending):HEAVY.ensure_clear(self.e)
        self.assertEqual(self.costs(), paid)
        self.assertEqual(self.e._heavy_pending, self.heavy_id)
        self.assertEqual(NF.current(self.actor)['phase'], 'waiting')
        self.acknowledge(HEAVY.ContinuationDisposition.CANCELLED_BY_RULING)
        result = self.e.survivalist_activity(self.t, 'natural_fighter_finish_heavy', subject=self.actor)
        self.assertFalse(result['native_resume'])
        self.assertEqual(self.actor.spec[NF.KEY][self.identity]['phase'], 'heavy_adjudicated')
        self.assertNotIn(self.identity, self.actor.spec[G.KEY]['sources'])
        self.assertEqual(self.costs(), paid)
        self.restore()

    def test_both_external_dispositions_cleanup_without_native_credit_or_duplicate_effect(self):
        for disposition in HEAVY.ContinuationDisposition:
            with self.subTest(disposition=disposition):
                paid = self.target_wait()
                self.restore()
                # Resolve the missing native secondary effect explicitly only for
                # the resolved-externally disposition, as actual external state.
                if disposition is HEAVY.ContinuationDisposition.RESOLVED_EXTERNALLY:
                    self.e.gm.set_stage(self.foe, 'acc', delta=-1,
                                        reason='TEST ONLY: externally adjudicated Mud-Slap suffix')
                state = deepcopy((self.foe.hp, self.foe.accuracy_stage))
                receipt = self.acknowledge(disposition)
                self.assertFalse(receipt['source_conformance_proven'])
                self.restore()
                result = self.e.survivalist_activity(self.t, 'natural_fighter_finish_heavy', subject=self.actor)
                self.assertFalse(result['native_resume'])
                self.assertEqual(result['disposition'], disposition.value)
                self.assertEqual((self.foe.hp, self.foe.accuracy_stage), state)
                self.assertEqual(self.costs(), paid)
                self.assertEqual(self.actor.spec[NF.KEY][self.identity]['phase'], 'heavy_adjudicated')
                self.assertNotIn(self.identity, self.actor.spec[G.KEY]['sources'])
                self.assertNotEqual(self.e._move_completions[self.completion_id]['phase'], 'complete')
                self.assertNotIn(self.foe.entity_id, self.e._move_completions[self.completion_id]['results'])
                self.restore()
                self.reject_unchanged('actual Natural Fighter Heavy wait',
                    lambda: self.e.survivalist_activity(self.t, 'natural_fighter_finish_heavy', subject=self.actor))
                self.assertEqual(self.costs(), paid)
                self.assertEqual((self.foe.hp, self.foe.accuracy_stage), state)


    def test_urban_heavy_wait_keeps_detached_projectile_through_external_cleanup(self):
        import test_natural_fighter_urban as URBAN
        import fling_move as FLING
        import world_entities as W
        for heavy_side in ('actor', 'recipient'):
            with self.subTest(heavy_side=heavy_side):
                self.scene(terrain='urban')
                self.e.gm.set_types(self.foe, ['물'], reason='actual nonimmune Fling recipient')
                choice = URBAN.NaturalFighterUrbanTests.object(self)
                (self.actor if heavy_side == 'actor' else self.foe).injuries = 5
                ap, hp = AP.available(self.t), self.foe.hp
                with patch.object(Engine, 'd20', return_value=18):
                    with self.assertRaises(HEAVY.HeavyPending):
                        URBAN.NaturalFighterUrbanTests.cast(self, choice=choice)
                record = NF.current(self.actor)
                self.identity, self.completion_id, self.heavy_id = [record[k] for k in
                    ('id', 'completion_id', 'heavy_event')]
                row = self.e._move_completions[self.completion_id]
                obj = self.e._physical_objects[choice['instance_id']]
                self.assertEqual(row['fling_launch']['status'], 'launched')
                self.assertNotIn('effect_receipt', row['fling_launch'])
                self.assertFalse(obj.get('consumed'))
                self.assertFalse(obj.get('equipped_by') or obj.get('carrier_id'))
                self.assertEqual(W.location_of(obj), {'kind': 'unknown'})
                self.assertEqual(AP.available(self.t), ap - 1)
                self.assertEqual(self.actor.move_uses[FLING.SOURCE], 1)
                self.assertEqual(self.foe.hp < hp, heavy_side == 'recipient')
                paid, damaged_hp = self.costs(), self.foe.hp
                self.restore()
                self.acknowledge(HEAVY.ContinuationDisposition.CANCELLED_BY_RULING)
                result = self.e.survivalist_activity(self.t, 'natural_fighter_finish_heavy', subject=self.actor)
                self.assertFalse(result['native_resume'])
                self.assertEqual(self.costs(), paid)
                self.assertEqual(self.foe.hp, damaged_hp)
                self.assertNotIn(self.identity, self.actor.spec[G.KEY]['sources'])
                self.assertNotIn(FLING.CHOICE, self.actor.spec)
                obj = self.e._physical_objects[choice['instance_id']]
                self.assertFalse(obj.get('consumed'))
                self.assertFalse(obj.get('equipped_by') or obj.get('carrier_id'))
                self.assertEqual(W.location_of(obj), {'kind': 'unknown'})
                self.assertEqual(self.e._move_completions[self.completion_id]['fling_launch']['status'], 'launched')
                self.restore()

if __name__ == '__main__':
    unittest.main()