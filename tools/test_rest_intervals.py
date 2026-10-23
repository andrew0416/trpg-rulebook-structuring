"""Independent checks for rest-interval accounting, not extended-rest certification."""
import copy
import hashlib
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from rest_intervals import plan_rest


def minute_oracle(carry, already_rested, minutes, cap=480, block=30):
    """A minute-by-minute state machine independent of the planner's divmod."""
    earned = 0
    for _ in range(minutes):
        if already_rested < cap:
            carry += 1
            if carry == block:
                earned += 1
                carry = 0
        already_rested += 1
    return carry, earned


class RestIntervalTests(unittest.TestCase):
    def plan(self, record=None, **changes):
        args = dict(rest_id="rest-A", now_seconds=0, gap_count=0, round_no=0,
                    day=0, injuries=0, base_max_hp=81, minutes=15,
                    rested_minutes_today=0)
        args.update(changes)
        return plan_rest(record, **args)

    def test_explicit_continuous_fifteen_plus_fifteen_equals_thirty(self):
        first, first_blocks = self.plan()
        split, second_blocks = self.plan(first, now_seconds=900, rested_minutes_today=15)
        whole, whole_blocks = self.plan(minutes=30)
        self.assertEqual(split, whole)
        self.assertEqual((first_blocks, second_blocks, whole_blocks), (0, 1, 1))

    def test_implicit_calls_are_independent(self):
        first, _ = self.plan(rest_id=None)
        second, blocks = self.plan(first, rest_id=None, now_seconds=900, rested_minutes_today=15)
        self.assertEqual((blocks, second["carry_minutes"], second["total_minutes"]), (0, 15, 15))

    def test_new_id_explicitly_starts_new_bout(self):
        first, _ = self.plan()
        second, blocks = self.plan(first, rest_id="rest-B", now_seconds=900, rested_minutes_today=15)
        self.assertEqual((blocks, second["carry_minutes"], second["total_minutes"]), (0, 15, 15))

    def test_returning_old_id_does_not_resurrect_discarded_carry(self):
        first, _ = self.plan()
        second, _ = self.plan(first, rest_id="rest-B", now_seconds=900, rested_minutes_today=15)
        third, blocks = self.plan(second, rest_id="rest-A", now_seconds=1800, rested_minutes_today=30)
        self.assertEqual((blocks, third["carry_minutes"], third["total_minutes"]), (0, 15, 15))

    def test_same_id_rejects_gap_or_overlap(self):
        first, _ = self.plan()
        before = copy.deepcopy(first)
        for now in (0, 899, 901, 1800):
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.plan(first, now_seconds=now, rested_minutes_today=15)
        self.assertEqual(first, before)

    def test_same_id_rejects_changed_semantic_context(self):
        first, _ = self.plan()
        for field, value in dict(gap_count=1, round_no=1, day=1, injuries=1,
                                 base_max_hp=82, cap_minutes=481, block_minutes=31).items():
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.plan(first, now_seconds=900, rested_minutes_today=15, **{field:value})

    def test_new_id_accepts_changed_context_without_carry(self):
        first, _ = self.plan()
        second, blocks = self.plan(first, rest_id="next-day-rest", now_seconds=1200,
                                  day=1, gap_count=1, round_no=3, injuries=1, base_max_hp=82)
        self.assertEqual((blocks, second["carry_minutes"], second["total_minutes"]), (0, 15, 15))
        self.assertEqual(second["context"]["day"], 1)

    def test_first_eight_hours_yield_at_most_sixteen_blocks(self):
        record, blocks = self.plan(minutes=600)
        self.assertEqual((blocks, record["carry_minutes"], record["total_minutes"], record["end_seconds"]),
                         (16, 0, 600, 36000))
        record, blocks = self.plan(record, now_seconds=36000, minutes=60, rested_minutes_today=600)
        self.assertEqual((blocks, record["total_minutes"]), (0, 660))

    def test_cap_crossing_counts_only_eligible_minutes_plus_prior_carry(self):
        first, blocks = self.plan(minutes=20, rested_minutes_today=450)
        self.assertEqual(blocks, 0)
        second, blocks = self.plan(first, now_seconds=1200, minutes=20, rested_minutes_today=470)
        self.assertEqual((blocks, second["carry_minutes"], second["total_minutes"]), (1, 0, 40))

    def test_exhausted_cap_does_not_turn_ineligible_minutes_into_credit(self):
        first, _ = self.plan(minutes=15, rested_minutes_today=465)
        second, blocks = self.plan(first, now_seconds=900, minutes=15, rested_minutes_today=480)
        self.assertEqual((blocks, second["carry_minutes"], second["total_minutes"]), (0, 15, 30))

    def test_zero_minutes_never_pays_or_advances(self):
        first, _ = self.plan(minutes=29)
        second, blocks = self.plan(first, now_seconds=1740, minutes=0, rested_minutes_today=29)
        self.assertEqual((blocks, second), (0, first))
        self.assertIsNot(second, first)
        self.assertIsNot(second["context"], first["context"])

    def test_custom_parameters_are_explicit_and_bounded(self):
        record, blocks = self.plan(minutes=31, cap_minutes=25, block_minutes=10)
        self.assertEqual((blocks, record["carry_minutes"]), (2, 5))
        record, blocks = self.plan(minutes=30, cap_minutes=0)
        self.assertEqual((blocks, record["carry_minutes"]), (0, 0))

    def test_no_healing_or_extended_rest_effect_is_invented(self):
        record, blocks = self.plan(minutes=240, injuries=5)
        self.assertEqual(blocks, 8)  # Time blocks only; caller must deny HP at five injuries.
        self.assertEqual(set(record), {"id", "end_seconds", "carry_minutes", "total_minutes", "context"})
        self.assertNotIn("extended_rest", record)
        self.assertNotIn("hp", record)

    def test_plan_is_pure_and_input_isolation_survives_success(self):
        first, _ = self.plan()
        before = copy.deepcopy(first)
        second, _ = self.plan(first, now_seconds=900, rested_minutes_today=15)
        self.assertEqual(first, before)
        second["context"]["day"] = 88
        self.assertEqual(first, before)

    def test_invalid_durations_and_context_rejected(self):
        for field in ("now_seconds", "gap_count", "round_no", "day", "injuries", "base_max_hp",
                      "minutes", "rested_minutes_today", "cap_minutes", "block_minutes"):
            for value in (-1, True, 1.5, "15", None):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.plan(**{field:value})
        for field in ("base_max_hp", "block_minutes"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.plan(**{field:0})

    def test_invalid_ids_rejected(self):
        for value in ("", "   ", 1, True, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.plan(rest_id=value)

    def test_invalid_prior_record_rejected_even_for_new_id(self):
        valid, _ = self.plan()
        bad_records = [[], {}, {**valid, "id": ""}, {**valid, "end_seconds": -1},
                       {**valid, "carry_minutes": 30}, {**valid, "carry_minutes": 16},
                       {**valid, "total_minutes": -1}, {**valid, "context": {}},
                       {**valid, "context": {**valid["context"], "day": True}}]
        for record in bad_records:
            with self.subTest(record=record), self.assertRaises(ValueError):
                self.plan(record, rest_id="new")

    def test_162_boundary_cases_match_independent_minute_machine(self):
        cases = 0
        for carry in (0, 1, 29):
            for used in (29, 30, 450, 479, 480, 500):
                for minutes in (0, 1, 29, 30, 31, 479, 480, 481, 600):
                    record, _ = self.plan(minutes=carry)
                    record["end_seconds"] = 36000
                    planned, blocks = self.plan(record, now_seconds=36000, minutes=minutes,
                                                rested_minutes_today=used)
                    remainder, expected = minute_oracle(carry, used, minutes)
                    self.assertEqual((planned["carry_minutes"], blocks), (remainder, expected))
                    cases += 1
        self.assertEqual(cases, 162)

    def test_partition_invariance_for_explicitly_continuous_bout(self):
        for parts in ((15, 15), (29, 1), (1, 29, 30), (200, 279, 1, 120)):
            for initial_used in (0, 450, 479, 480):
                record = None
                now = 0
                used = initial_used
                total_blocks = 0
                for minutes in parts:
                    record, blocks = self.plan(record, now_seconds=now, minutes=minutes,
                                               rested_minutes_today=used)
                    now += minutes * 60
                    used += minutes
                    total_blocks += blocks
                whole, expected = self.plan(minutes=sum(parts), rested_minutes_today=initial_used)
                self.assertEqual((record, total_blocks), (whole, expected))


if __name__ == "__main__":
    class Result(unittest.TextTestResult):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.rows = []
        def addSuccess(self, t):
            super().addSuccess(t)
            self.rows.append(dict(id="REST-INTERVAL-" + t._testMethodName, status="pass"))
        def addFailure(self, t, err):
            super().addFailure(t, err)
            self.rows.append(dict(id="REST-INTERVAL-" + t._testMethodName, status="fail"))
        def addError(self, t, err):
            super().addError(t, err)
            self.rows.append(dict(id="REST-INTERVAL-" + t._testMethodName, status="error"))
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RestIntervalTests))
    paths = ["tools/test_rest_intervals.py", "engine/rest_intervals.py", "input/ch07-combat.md"]
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(),
                  scope="Pure thirty-minute continuous-rest planning only.",
                  remaining=["Four-hour continuous extended-rest effects", "Runtime interval commitment and shared-clock authority", "Cross-day continuity adjudication"],
                  results=result.rows,
                  input_hashes={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths})
    (ROOT / "output/rest-interval-tests.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
