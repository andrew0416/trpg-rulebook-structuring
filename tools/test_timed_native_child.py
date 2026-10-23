"""Timed dispatch retains actual native children at the common result handoff."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / 'data').is_dir() or not (ROOT / 'output').is_dir():
    ROOT = Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
for folder in ('engine', 'tools'):
    value = str(ROOT / folder)
    if value not in sys.path:
        sys.path.append(value)

import unittest

import action_lifecycle as ACTION
import combat_timing as TIME
import effect_contracts as CONTRACTS
from state_codec import dump_engine
import test_condition_native_child as CONDITION
import test_historical_effect_source_closure as FIXTURE


class TimedNativeChildTests(CONDITION.ConditionNativeChildTests):
    """Reuse the public registration/observation fixture with a real lifetime."""

    def suspend(self, *, suffix=True):
        c = self.c
        self.has_suffix = suffix
        self.suffix_born = getattr(self, '_suffix_born', False)
        status = dict(type='apply_status', status='독', target='self', duration='1 round')
        if self.suffix_born:
            effects = [c.stage('def', conditional=True), status]
        else:
            status['if'] = 'target was asleep'
            effects = [status]
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
        self.assertEqual(TIME.records(c.a), [])

    def resume_a(self, truth=True):
        super().resume_a(truth)
        c = self.c
        if truth:
            records = TIME.records(c.a)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['source'], FIXTURE.SOURCE_A)
            self.assertEqual(records[0]['statuses'], ['독'])
            self.assertEqual(records[0]['owned_statuses'], {'독'})
            self.assertEqual(records[0]['count_deadline'], (c.e.round_no + 1, 10))
            rows = c.e._effect_dispatch_receipts
            timed_token, timed = next((t, r) for t, r in rows.items()
                                      if r['effect'].get('duration') == '1 round')
            self.assertEqual(timed['status'], 'completed')
            self.assertIsInstance(timed['result'], CONTRACTS.BatchResult)
            child_tokens = [o.receipt for o in timed['result'].outcomes]
            self.assertEqual(len(child_tokens), len(set(child_tokens)))
            self.assertNotIn(timed_token, child_tokens)
            self.assertIn(self.b_token, child_tokens)
            self.assertTrue(all(rows[t]['source_id'] == FIXTURE.SOURCE_B for t in child_tokens))
        else:
            self.assertEqual(TIME.records(c.a), [])

    def assert_closed(self, *, child=True, truth=True):
        super().assert_closed(child=child, truth=truth)
        c = self.c
        self.assertEqual(len(TIME.records(c.a)), int(child))
        if child:
            self.assertIn('독', c.a.conditions)
        meta = next(r['turn_end_close'] for r in c.e._effect_dispatch_receipts.values()
                    if 'turn_end_close' in r)
        self.assertEqual(meta['status'], 'closed')
        self.assertIs(meta['closed_by'], c.e._turn_closures[-1])
        ACTION.validate_turn_end_closures(c.e)

    def test_suffix_born_timed_child_waits_then_closes_once(self):
        self._suffix_born = True
        self.suspend(); self.resume_a(); self.resume_b(); self.assert_closed()
        self.assertEqual(self.c.a.stages['def'], 1)
        before = dump_engine(self.c.e)
        self.c.resolve(self.a_token); self.resume_b()
        self.assertEqual(dump_engine(self.c.e), before)

    def test_suffix_timed_child_json_and_gm_restore(self):
        self._suffix_born = True
        super().test_json_and_gm_restore_before_and_after_condition_child_issuance()

    def test_suffix_timed_child_late_close_fault_and_retry(self):
        self._suffix_born = True
        super().test_late_native_close_fault_rolls_back_child_observation_and_retry()

    def test_timed_status_expires_at_its_original_count_after_child_completion(self):
        self.suspend(); self.resume_a(); self.resume_b(); self.assert_closed()
        c = self.c
        count = len(c.e._effect_dispatch_receipts)
        c.e.end_round(); c.e.start_round([self.b, c.a])
        c.e.at_initiative_count(11)
        self.assertIn('독', c.a.conditions)
        self.assertEqual(len(TIME.records(c.a)), 1)
        c.e.at_initiative_count(10)
        self.assertNotIn('독', c.a.conditions)
        self.assertEqual(TIME.records(c.a), [])
        self.assertEqual(len(c.e._effect_dispatch_receipts), count)
        self.assertEqual(len(c.e._turn_closures), 3)

    def test_existing_batch_result_preserves_directed_children_and_continuations(self):
        c = self.c
        c.f.register(effects=[dict(type='alternate_effect',
                                  then=[c.stage('atk'), c.stage('spd')]),
                              c.stage('def', conditional=True), c.stage('spe')])
        c.e.end_of_turn(c.a)
        rows = c.e._effect_dispatch_receipts
        parent_token, parent = next((t, r) for t, r in rows.items()
                                    if r['effect']['type'] == 'alternate_effect')
        child_token = next(t for t, r in rows.items() if 'condition_request' in r)
        batch = parent['result']
        self.assertIsInstance(batch, CONTRACTS.BatchResult)
        direct = [outcome.receipt for outcome in batch.outcomes]
        self.assertEqual(len(direct), len(set(direct)))
        self.assertNotIn(parent_token, direct)
        self.assertNotIn(child_token, direct)
        self.assertEqual([rows[t]['effect']['type'] for t in direct], ['stage_change', 'stage_change'])
        self.assertEqual((c.a.stages['atk'], c.a.stages['def'], c.a.stages['spd'], c.a.stages['spe']), (1, 0, 1, 0))
        c.resolve(child_token)
        self.assertEqual((c.a.stages['def'], c.a.stages['spd'], c.a.stages['spe']), (1, 1, 1))
        self.assertEqual(rows[parent_token]['status'], 'completed')
        self.assertIsNone(c.e._active_turn_actor)
        self.assertEqual(len(c.e._turn_closures), 1)
        before = dump_engine(c.e)
        c.resolve(child_token)
        self.assertEqual(dump_engine(c.e), before)


if __name__ == '__main__':
    unittest.main()
