"""Nested authored branch conditions must keep their actual turn-end leaf."""
from pathlib import Path
import os
import sys

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE
if not (ROOT / 'data').is_dir() or not (ROOT / 'output').is_dir():
    ROOT = Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
if not os.environ.get('NESTED_NO_OVERLAY') and (STAGE / 'engine').is_dir():
    sys.path.insert(0, str(STAGE / 'engine'))
for folder in ('engine', 'tools'):
    value = str(ROOT / folder)
    if value not in sys.path:
        sys.path.append(value)

import json
import unittest
from unittest.mock import patch

import action_lifecycle as ACTION
import combat_timing as TIME
import effect_contracts as EC
import effects as FX
import effects_ext as EXT
import frequency as FREQ
from state_codec import dump_engine, load_engine, StateCodecError
import test_end_turn_resume as BASE
import test_historical_effect_source_closure as FIXTURE


class NestedTurnConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.EndTurnResumeTests.setUpClass()
        print('ACTUAL_ORIGINS', json.dumps({m.__name__: str(Path(m.__file__).resolve())
              for m in (ACTION, EC, FX, EXT, BASE, FIXTURE)}, ensure_ascii=False))

    def setUp(self):
        self.c = BASE.EndTurnResumeTests(methodName='runTest')
        self.c.setUp()

    def register(self):
        c = self.c
        self.effects = [dict(type='alternate_effect', then=[c.stage('def', conditional=True), c.stage('spd')]),
                        c.stage('spe')]
        c.f.register(effects=self.effects)

    def locate(self):
        c = self.c
        self.rows = c.e._effect_dispatch_receipts
        self.parent, self.parent_row = next((t, r) for t, r in self.rows.items()
                                           if r['effect']['type'] == 'alternate_effect')
        self.leaf = next(t for t, r in self.rows.items() if 'condition_request' in r)

    def suspend(self):
        c = self.c
        self.register()
        before = dump_engine(c.e)
        try:
            self.returned = c.e.end_of_turn(c.a)
        except Exception as ex:
            print('EXACT_NATIVE_REPRO', json.dumps(dict(error=str(ex), rollback=dump_engine(c.e) == before,
                  active_is_original=c.e._active_turn_actor is c.a, closures=len(c.e._turn_closures),
                  effects=self.effects), ensure_ascii=False))
            raise
        self.locate()
        self.assertEqual(self.returned['status'], 'awaiting_input')
        self.assertIs(self.returned['receipt'], self.leaf)
        self.assertIsNot(self.returned['receipt'], self.parent)
        self.assertIs(c.e._active_turn_actor, c.a)
        self.assertEqual(len(c.e._turn_closures), 0)
        self.assertEqual((c.a.stages['def'], c.a.stages['spd'], c.a.stages['spe']), (0, 0, 0))

    def close(self, truth=True):
        c = self.c
        result = c.resolve(self.leaf, truth)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual((c.a.stages['def'], c.a.stages['spd'], c.a.stages['spe']), (int(truth), 1, 1))
        self.assertEqual(c.e._effect_dispatch_receipts[self.parent]['status'], 'completed')
        self.assertIsNone(c.e._active_turn_actor)
        self.assertEqual(len(c.e._turn_closures), 1)
        self.assertEqual(FREQ.state(c.a)['activations'][FIXTURE.SOURCE_A]['used'], 1)
        self.assertEqual(c.a._action_history, ['free'])
        ACTION.validate_turn_end_closures(c.e)
        before = dump_engine(c.e)
        c.resolve(self.leaf, truth)
        self.assertEqual(dump_engine(c.e), before)

    def test_n01_native_branch_returns_actual_answerable_leaf_then_closes_once(self):
        self.suspend()
        self.close()

    def test_n00_same_supported_effect_outside_native_close_succeeds(self):
        c = self.c
        self.register()
        self.assertIsNone(EC.inspect(c.e, c.a, c.a, self.effects[0], FIXTURE.SOURCE_A))
        FX.fire_event(c.e, c.a, {'event': 'turn_end'})
        self.locate()
        self.assertIsInstance(self.parent_row['result'], EC.BatchResult)
        self.assertNotIn('condition_request', self.parent_row)
        c.resolve(self.leaf)
        self.assertEqual((c.a.stages['def'], c.a.stages['spd'], c.a.stages['spe']), (1, 1, 1))
        self.assertEqual(c.e._effect_dispatch_receipts[self.parent]['status'], 'completed')
        self.assertIs(c.e._active_turn_actor, c.a)
        self.assertEqual(len(c.e._turn_closures), 0)
        print('SAME_SUPPORTED_DISPATCH_CONTROL', json.dumps(dict(effect=self.effects, stages=c.a.stages,
              native_turn_still_open=True), ensure_ascii=False))

    def test_n02_json_and_gm_restore_true_and_false_branches(self):
        for mode, truth in (('json', True), ('gm', False)):
            with self.subTest(mode=mode, truth=truth):
                self.setUp()
                self.suspend()
                c = self.c
                if mode == 'json':
                    c.e = load_engine(c.f.r, json.loads(json.dumps(dump_engine(c.e), ensure_ascii=False)))
                    c.a = next(a for a in c.e.everyone if a.name == 'Authored declaration owner')
                    self.locate()
                    self.close(truth)
                else:
                    c.e.gm.snapshot('nested-condition-pending')
                    self.close(truth)
                    c.e.gm.restore('nested-condition-pending', reason='restore actual pending nested branch')
                    self.locate()
                    self.close(truth)

    def test_n03_original_owner_source_boundary_and_leaf_request_guards(self):
        self.suspend()
        c = self.c
        before = dump_engine(c.e)
        with self.assertRaisesRegex(ValueError, 'owner'):
            c.e.resolve_effect_condition(object(), self.leaf, target_was_asleep=True, reason='wrong owner')
        with self.assertRaisesRegex(ValueError, 'missing historical'):
            c.resolve(self.parent)
        with c.f.changed_source():
            with self.assertRaisesRegex(ValueError, 'source changed'):
                c.resolve(self.leaf)
        c.e.elapsed_seconds += 1
        try:
            with self.assertRaisesRegex(ValueError, 'boundary'):
                c.resolve(self.leaf)
        finally:
            c.e.elapsed_seconds -= 1
        request = self.rows[self.leaf]['condition_request']
        original = request['profile']
        request['profile'] = 'forged-profile'
        try:
            with self.assertRaisesRegex(ValueError, 'source profile'):
                c.resolve(self.leaf)
        finally:
            request['profile'] = original
        self.assertEqual(dump_engine(c.e), before)
        self.close()

    def test_n04_forged_request_and_child_graphs_are_rejected(self):
        self.suspend()
        c = self.c
        before = dump_engine(c.e)
        batch = self.parent_row['result']
        original = batch.outcomes
        first = original[0]
        forged = [
            ('duplicate', original + (first,)),
            ('cycle', (EC.Outcome(FIXTURE.SOURCE_A, self.parent_row['occurrence'], 'condition_unknown', receipt=self.parent),)),
            ('missing', (EC.Outcome(FIXTURE.SOURCE_A, 'missing', 'condition_unknown', receipt=object()),)),
            ('wrong-occurrence', (EC.Outcome(first.source_id, 'forged-occurrence', first.status, receipt=first.receipt), *original[1:])),
            ('unreceipted', (EC.Outcome(FIXTURE.SOURCE_A, '', 'condition_unknown'),)),
            ('empty', ()),
        ]
        for label, outcomes in forged:
            with self.subTest(graph=label):
                batch.outcomes = outcomes
                try:
                    with self.assertRaises((ValueError, StateCodecError)):
                        dump_engine(c.e)
                    with self.assertRaises(ValueError):
                        c.e.gm.snapshot('forged-nested-' + label)
                    with self.assertRaises(ValueError):
                        c.resolve(self.leaf)
                finally:
                    batch.outcomes = original
        leaf = self.rows[self.leaf]
        original_leaf = dict(leaf)
        leaf.pop('condition_request')
        leaf['result'] = EC.BatchResult(0, 0)
        leaf['result'].engine = c.e
        try:
            # A direct unknown leaf cannot become an aggregate by attaching a
            # BatchResult and removing its actual suspended request.
            with self.assertRaises((ValueError, StateCodecError)):
                dump_engine(c.e)
            with self.assertRaises(ValueError):
                c.resolve(self.leaf)
        finally:
            # Preserve insertion order too: the exact graph encoding numbers
            # its references in field order when comparing unchanged state.
            leaf.clear()
            leaf.update(original_leaf)
        payload = json.loads(json.dumps(before))
        pair = next(pair for node in payload['nodes'].values() if node.get('kind') == 'dict'
                    for pair in node['items'] if pair[0] == 'condition_request')
        pair[1] = None
        with self.assertRaises(StateCodecError):
            load_engine(c.f.r, payload)
        self.assertEqual(dump_engine(c.e), before)
        self.close()

    def test_n05_late_native_close_failure_rolls_back_leaf_suffix_and_retry(self):
        self.suspend()
        c = self.c
        before = dump_engine(c.e)
        original = TIME.end_turn
        def fail_after_native_close(engine, actor):
            original(engine, actor)
            raise ValueError('late nested-condition native close fault')
        with patch.object(TIME, 'end_turn', side_effect=fail_after_native_close):
            with self.assertRaisesRegex(ValueError, 'late nested-condition native close fault'):
                c.resolve(self.leaf)
        self.assertEqual(dump_engine(c.e), before)
        self.assertNotIn('condition_reply', self.rows[self.leaf])
        self.close()


if __name__ == '__main__':
    unittest.main()
