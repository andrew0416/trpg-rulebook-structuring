"""Boundary and native consumer checks for the shared partial-round owner."""
from copy import deepcopy
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

import elapsed_time as TIME
import invisibility_state as V
import cleanse_tags as TAG
import common_checks as C
import state_codec as CODEC
import world_entities as WORLD
import test_category2_invisibility_state as VI
import test_category2_cleanse_barrier as CB


class ElapsedTimeOwnerTests(unittest.TestCase):
    def test_multiple_gaps_known_prefix_and_observed_base_use_one_range(self):
        e = SimpleNamespace(elapsed_seconds=127, unresolved_time_intervals=[
            {'known_seconds': 0}, {'known_seconds': 3}, {'known_seconds': 9}])
        self.assertEqual(TIME.bounds(e, 100, 1, 5), (32, 40))
        self.assertEqual(TIME.bounds(e, 127, 3, 40), (40, 40))
        self.assertEqual(e.elapsed_seconds, 127)
        self.assertEqual(len(e.unresolved_time_intervals), 3)

    def test_future_negative_boolean_and_invalid_partial_intervals_reject(self):
        e = SimpleNamespace(elapsed_seconds=10, unresolved_time_intervals=[])
        for values in ((11, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0),
                       (0, 0, -1), (False, 0, 0), (0, True, 0), (0, 0, 1.0)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                TIME.bounds(e, *values)
        for known in (-1, 10, True, None, 1.0):
            e.unresolved_time_intervals = [{'known_seconds': known}]
            with self.subTest(known=known), self.assertRaises(ValueError):
                TIME.bounds(e, 0, 0, 0)
        e.unresolved_time_intervals = [None]
        with self.assertRaises(ValueError):TIME.bounds(e, 0, 0, 0)

    @staticmethod
    def fixture(cls):
        if not hasattr(cls, 'rules') and not hasattr(cls, 'r'):
            cls.setUpClass()
        value = cls('runTest')
        value.setUp()
        return value

    def test_native_invisibility_multiple_real_partial_rounds_and_observation_restore(self):
        f = self.fixture(VI.Tests)
        f.grant(f.p); f.change(f.p, True)
        f.e.advance_time(232)
        f.begin(f.p); f.e.advance_time(3); f.e.end_encounter()
        f.begin(f.p); f.e.advance_time(2); f.e.end_encounter()
        self.assertEqual(f.view(f.p)['elapsed_bounds'], [237, 252])
        self.assertIsNone(f.view(f.p)['active'])
        with patch.object(TIME, 'bounds', wraps=TIME.bounds) as owner:
            self.assertEqual(f.view(f.p)['phase'], 'uncertain')
            self.assertGreater(owner.call_count, 0)
        f.e.gm.snapshot('owner-uncertain')
        restored = CODEC.load_engine(f.r, json.loads(json.dumps(CODEC.dump_engine(f.e))))
        actual = WORLD.actor_index(restored)[f.p.entity_id]
        self.assertEqual(restored.invisibility_state(actual)['elapsed_bounds'], [237, 252])
        before = CODEC.dump_engine(restored)
        with self.assertRaises(ValueError):restored.observe_invisibility_elapsed(actual, 253, reason='outside range')
        self.assertEqual(CODEC.dump_engine(restored), before)
        restored.observe_invisibility_elapsed(actual, 239, reason='actual observed duration')
        restored.advance_time(1)
        self.assertEqual(restored.invisibility_state(actual)['phase'], 'cooldown')
        self.assertEqual(restored.invisibility_state(actual)['ready_after_elapsed'], 600)
        f.e.observe_invisibility_elapsed(f.p, 240, reason='observed expiry')
        f.e.gm.restore('owner-uncertain')
        self.assertEqual(f.view(f.p)['elapsed_bounds'], [237, 252])

    def test_native_tag_multiple_real_partial_rounds_resolve_retry_without_new_focus(self):
        f = self.fixture(CB.BarrierTests)
        self.assertFalse(f.gate())
        f.e.advance_time(3591, [f.a, f.p, f.q])
        for seconds in (3, 2):
            f.e.start_round(f.e.everyone)
            f.e.start_of_turn(f.p, initiative_count=10)
            f.e.advance_time(seconds)
            f.e.end_encounter()
        row = f.e._physical_objects['tag:one'][TAG.BARRIER]['attempts']['focus']
        self.assertEqual(TAG._elapsed(f.e, row), (3596, 3611))
        f.e.gm.snapshot('owner-tag-uncertain')
        loaded, index = f.restore()
        actor = index[f.p.entity_id]
        with patch.object(TIME, 'bounds', wraps=TIME.bounds) as owner:
            self.assertIsInstance(f.gate(actor=actor, attempt='not-a-new-roll', faces=[6]*4, engine=loaded), C.PendingDecision)
            self.assertGreater(owner.call_count, 0)
        self.assertEqual(set(loaded._physical_objects['tag:one'][TAG.BARRIER]['attempts']), {'focus'})
        before = CODEC.dump_engine(loaded)
        with self.assertRaises(ValueError):loaded.gm.observe_cleanse_retry_elapsed('tag:one', actor, 3612, reason='outside range')
        self.assertEqual(CODEC.dump_engine(loaded), before)
        loaded.gm.observe_cleanse_retry_elapsed('tag:one', actor, 3600, reason='observed actual failed-check duration')
        self.assertTrue(f.gate(actor=actor, attempt='exact-hour', faces=[3]*4, engine=loaded))
        self.assertEqual(loaded._physical_objects['tag:one']['destroyed']['cleanse_attempt_id'], 'exact-hour')
        f.e.gm.observe_cleanse_retry_elapsed('tag:one', f.p, 3599, reason='GM observed still too early')
        self.assertFalse(f.gate(attempt='one-second-early', faces=[6]*4))
        f.e.gm.restore('owner-tag-uncertain')
        self.assertEqual(TAG._elapsed(f.e, f.e._physical_objects['tag:one'][TAG.BARRIER]['attempts']['focus']), (3596, 3611))

    def test_native_corrupt_common_clock_rejects_both_serializers_and_preserves_gm_restore(self):
        for kind in ('invisibility', 'tag'):
            with self.subTest(kind=kind):
                f = self.fixture(VI.Tests if kind == 'invisibility' else CB.BarrierTests)
                if kind == 'invisibility':f.grant(f.p); f.change(f.p, True)
                else:self.assertFalse(f.gate())
                f.e.gm.snapshot('valid-owner-clock')
                f.e.unresolved_time_intervals.append({'known_seconds': True})
                with self.assertRaises((ValueError, CODEC.StateCodecError)):CODEC.dump_engine(f.e)
                f.e.gm.restore('valid-owner-clock')
                self.assertTrue(f.e.validate_state()['valid'])


if __name__ == '__main__':unittest.main()
