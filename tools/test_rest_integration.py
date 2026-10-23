"""Source-derived rest integration boundaries; no whole-rule certification.

ch07:746: uninterrupted 30 minutes, real maximum HP / 16, first eight hours/day.
ch07:750: four-hour extended rest, persistent conditions, drained AP and eligible
prior-day daily moves. Tests distinguish an explicit bout from adjacent API calls.
"""
import copy
import hashlib
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from engine import Rules, Engine, Combatant
import downtime as DT
import frequency as FREQ


class RestIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")

    def fixture(self, n=1):
        e = Engine(self.rules)
        actors = [Combatant(self.rules, dict(name="Rest" + str(i), kind="pokemon", level=1,
                  stats={"hp":23, "atk":5, "def":5, "spa":5, "spd":5, "spe":5},
                  types=["노말"], moves=[])) for i in range(n)]
        for c in actors:
            self.assertEqual(c.base_max_hp, 80)
            c.hp = 1
        e.everyone = e.gm.everyone = actors
        return e, actors

    def state(self, e, actors):
        return copy.deepcopy(dict(time=e.elapsed_seconds, round=e.round_no,
            round_start=e.round_start_seconds, gaps=e.unresolved_time_intervals,
            log=e.log_lines, clock_actors=[id(c) for c in e._time_actors],
            actors=[dict(hp=c.hp, spec=c.spec, injuries=c.injuries,
                         conditions=c.conditions, stages=c.stages, dead=c.dead,
                         life_elapsed=c.life_elapsed_seconds) for c in actors]))

    def assert_rejected_unchanged(self, e, actors, callback, exception=ValueError):
        before = self.state(e, actors)
        with patch.object(e, "advance_time", wraps=e.advance_time) as clock:
            with self.assertRaises(exception):
                callback()
            clock.assert_not_called()
        self.assertEqual(self.state(e, actors), before)

    def test_same_explicit_id_fifteen_plus_fifteen_pays_one_block(self):
        e, (c,) = self.fixture()
        self.assertEqual(DT.rest(e, c, 15, rest_id="nap"), 0)
        self.assertEqual(DT.rest(e, c, 15, rest_id="nap"), 5)
        self.assertEqual((c.hp, e.elapsed_seconds, c.spec["rested_minutes_today"]), (6, 1800, 30))
        self.assertEqual(c.spec["rest_interval"]["carry_minutes"], 0)

    def test_single_thirty_and_explicit_split_have_equal_results(self):
        ea, (a,) = self.fixture()
        eb, (b,) = self.fixture()
        DT.rest(ea, a, 30, rest_id="nap")
        DT.rest(eb, b, 15, rest_id="nap")
        DT.rest(eb, b, 15, rest_id="nap")
        self.assertEqual((a.hp, ea.elapsed_seconds, a.spec["rest_interval"]),
                         (b.hp, eb.elapsed_seconds, b.spec["rest_interval"]))

    def test_distinct_ids_do_not_combine_adjacent_fifteen_minutes(self):
        e, (c,) = self.fixture()
        DT.rest(e, c, 15, rest_id="first")
        DT.rest(e, c, 15, rest_id="second")
        self.assertEqual((c.hp, e.elapsed_seconds), (1, 1800))

    def test_none_ids_do_not_infer_continuity(self):
        e, (c,) = self.fixture()
        DT.rest(e, c, 15)
        DT.rest(e, c, 15)
        self.assertEqual((c.hp, e.elapsed_seconds), (1, 1800))

    def test_explicit_interruption_discards_carry_but_not_daily_use(self):
        e, (c,) = self.fixture()
        DT.rest(e, c, 15, rest_id="nap")
        DT.interrupt_rest(c)
        self.assertEqual(c.spec["rested_minutes_today"], 15)
        DT.rest(e, c, 15, rest_id="nap")
        self.assertEqual((c.hp, e.elapsed_seconds, c.spec["rested_minutes_today"]), (1, 1800, 30))

    def test_intervening_elapsed_time_rejects_same_id_before_clock(self):
        e, (c,) = self.fixture()
        DT.rest(e, c, 15, rest_id="nap")
        e.advance_time(1)
        self.assert_rejected_unchanged(e, [c], lambda: DT.rest(e, c, 15, rest_id="nap"))

    def test_intervening_round_rejects_same_id_before_clock(self):
        e, (c,) = self.fixture()
        DT.rest(e, c, 15, rest_id="nap")
        e.start_round([c])
        self.assert_rejected_unchanged(e, [c], lambda: DT.rest(e, c, 15, rest_id="nap"))

    def test_new_unknown_gap_rejects_same_id_before_clock(self):
        e, (c,) = self.fixture()
        DT.rest(e, c, 15, rest_id="nap")
        e.unresolved_time_intervals.append(dict(reason="externally declared missing interval"))
        self.assert_rejected_unchanged(e, [c], lambda: DT.rest(e, c, 15, rest_id="nap"))

    def test_injury_change_rejects_same_id_before_clock(self):
        e, (c,) = self.fixture()
        DT.rest(e, c, 15, rest_id="nap")
        c.injuries = 1
        self.assert_rejected_unchanged(e, [c], lambda: DT.rest(e, c, 15, rest_id="nap"))

    def test_real_maximum_change_rejects_same_id_before_clock(self):
        e, (c,) = self.fixture()
        DT.rest(e, c, 15, rest_id="nap")
        c.stats["hp"] = 24
        self.assertEqual(c.base_max_hp, 83)
        self.assert_rejected_unchanged(e, [c], lambda: DT.rest(e, c, 15, rest_id="nap"))

    def test_explicit_day_transition_rejects_same_id_before_clock(self):
        e, (c,) = self.fixture()
        DT.rest(e, c, 15, rest_id="nap")
        DT.new_day(c)
        self.assert_rejected_unchanged(e, [c], lambda: DT.rest(e, c, 15, rest_id="nap"))

    def test_new_bout_after_explicit_day_transition_has_fresh_allowance(self):
        e, (c,) = self.fixture()
        DT.rest(e, c, 480, rest_id="yesterday")
        c.hp = 1
        DT.new_day(c)
        self.assertEqual(DT.rest(e, c, 30, rest_id="today"), 5)
        self.assertEqual((c.hp, c.spec["rested_minutes_today"], e.elapsed_seconds), (6, 30, 30600))

    def test_ordinary_rest_and_extended_rest_share_four_hour_milestone(self):
        e, (c,) = self.fixture()
        c.spec["ap_removed"] = 2
        e.apply_status(c, "독")
        DT.rest(e, c, 120, rest_id="sleep")
        self.assertEqual(c.spec["ap_removed"], 2)
        self.assertIn("독", c.conditions)
        DT.extended_rest(e, c, 2, rest_id="sleep")
        self.assertEqual((c.spec["ap_removed"], c.hp, e.elapsed_seconds), (0, 41, 14400))
        self.assertNotIn("독", c.conditions)

    def test_two_extended_segments_share_four_hour_milestone(self):
        e, (c,) = self.fixture()
        c.spec["ap_removed"] = 2
        DT.extended_rest(e, c, 2, rest_id="sleep")
        DT.extended_rest(e, c, 2, rest_id="sleep")
        self.assertEqual((c.spec["ap_removed"], e.elapsed_seconds), (0, 14400))

    def test_ordinary_four_hour_rest_also_applies_extended_benefits(self):
        e, (c,) = self.fixture()
        c.spec["ap_removed"] = 2
        DT.rest(e, c, 240, rest_id="sleep")
        self.assertEqual(c.spec["ap_removed"], 0)

    def test_four_hour_milestone_does_not_repeat_on_short_same_bout_segment(self):
        e, (c,) = self.fixture()
        c.spec["ap_removed"] = 2
        DT.rest(e, c, 240, rest_id="sleep")
        c.spec["ap_removed"] = 2
        DT.rest(e, c, 15, rest_id="sleep")
        self.assertEqual(c.spec["ap_removed"], 2)
        DT.rest(e, c, 0, rest_id="sleep")
        self.assertEqual(c.spec["ap_removed"], 2)
        DT.extended_rest(e, c, 4, rest_id="new-sleep")
        self.assertEqual(c.spec["ap_removed"], 0)

    def test_unconfirmed_two_hour_bouts_do_not_make_extended_rest(self):
        for ids in ((None, None), ("first", "second")):
            e, (c,) = self.fixture()
            c.spec["ap_removed"] = 2
            DT.extended_rest(e, c, 2, rest_id=ids[0])
            DT.extended_rest(e, c, 2, rest_id=ids[1])
            self.assertEqual((c.spec["ap_removed"], e.elapsed_seconds), (2, 14400))

    def test_parallel_group_uses_single_interval_and_actor_specific_carry(self):
        e, (a, b) = self.fixture(2)
        DT.rest(e, a, 15, rest_id="nap")
        with patch.object(e, "advance_time", wraps=e.advance_time) as clock:
            self.assertEqual(DT.rest_many(e, [a, b], 15, rest_id="nap"), [5, 0])
            self.assertEqual(clock.call_count, 1)
        self.assertEqual((a.hp, b.hp, e.elapsed_seconds), (6, 1, 1800))
        self.assertEqual((a.spec["rested_minutes_today"], b.spec["rested_minutes_today"]), (30, 15))
        self.assertEqual((a.life_elapsed_seconds, b.life_elapsed_seconds), (1800, 1800))

    def test_duplicate_group_actor_is_not_credited_twice(self):
        e, (a, b) = self.fixture(2)
        gains = DT.rest_many(e, [a, a, b, a], 30, rest_id="nap")
        self.assertEqual(gains, [5, 5])
        self.assertEqual((a.hp, b.hp, e.elapsed_seconds), (6, 6, 1800))
        self.assertEqual((a.spec["rested_minutes_today"], b.spec["rested_minutes_today"]), (30, 30))

    def test_invalid_later_actor_rolls_back_entire_group_before_clock(self):
        e, (a, b) = self.fixture(2)
        DT.rest_many(e, [a, b], 15, rest_id="nap")
        b.injuries = 1
        self.assert_rejected_unchanged(e, [a, b], lambda: DT.rest_many(e, [a, b], 15, rest_id="nap"))

    def test_bad_daily_ledger_in_later_actor_rejects_entire_group(self):
        e, (a, b) = self.fixture(2)
        b.spec["rested_minutes_today"] = True
        self.assert_rejected_unchanged(e, [a, b], lambda: DT.rest_many(e, [a, b], 30, rest_id="nap"))

    def test_public_clock_bypass_is_rejected_without_mutation(self):
        e, (c,) = self.fixture()
        self.assert_rejected_unchanged(e, [c], lambda: DT.rest(e, c, 30, advance_time=False), TypeError)
        self.assert_rejected_unchanged(e, [c], lambda: DT.rest_many(e, [c], 30, advance_time=False), TypeError)

    def test_daily_first_480_minutes_bound_credit_under_segmentation(self):
        e, (c,) = self.fixture()
        gains = []
        for _ in range(32):
            c.hp = 1  # Isolate each payout from maximum-HP clamping.
            gains.append(DT.rest(e, c, 15, rest_id="sleep"))
        self.assertEqual(gains, [0, 5] * 16)
        c.hp = 1
        self.assertEqual(DT.rest(e, c, 30, rest_id="sleep"), 0)
        self.assertEqual((c.hp, c.spec["rested_minutes_today"], e.elapsed_seconds), (1, 510, 30600))

    def test_snapshot_restores_clock_carry_daily_use_and_four_hour_milestone(self):
        e, (c,) = self.fixture()
        c.spec["ap_removed"] = 2
        DT.rest(e, c, 225, rest_id="sleep")
        self.assertEqual((c.hp, c.spec["rest_interval"]["carry_minutes"]), (36, 15))
        e.gm.snapshot("before-milestone")
        for _ in range(2):
            self.assertEqual(DT.rest(e, c, 15, rest_id="sleep"), 5)
            self.assertEqual((c.hp, c.spec["ap_removed"], e.elapsed_seconds), (41, 0, 14400))
            e.gm.restore("before-milestone")
            self.assertEqual((c.hp, c.spec["ap_removed"], e.elapsed_seconds), (36, 2, 13500))
            self.assertEqual((c.spec["rest_interval"]["carry_minutes"], c.spec["rested_minutes_today"]), (15, 225))

    def test_heavy_injuries_deny_hp_but_do_not_erase_time_or_daily_consumption(self):
        e, (c,) = self.fixture()
        c.injuries = 5
        self.assertEqual(DT.rest(e, c, 15, rest_id="nap"), 0)
        self.assertEqual(DT.rest(e, c, 15, rest_id="nap"), 0)
        self.assertEqual((c.hp, e.elapsed_seconds, c.spec["rested_minutes_today"]), (1, 1800, 30))

    def test_invalid_duration_and_id_have_no_partial_effects(self):
        for minutes, rest_id in ((True, "nap"), (-1, "nap"), (1.5, "nap"), (30, ""), (30, [])):
            e, (c,) = self.fixture()
            self.assert_rejected_unchanged(e, [c], lambda: DT.rest(e, c, minutes, rest_id=rest_id))


if __name__ == "__main__":
    class Result(unittest.TextTestResult):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.rows = []
        def addSuccess(self, t):
            super().addSuccess(t)
            self.rows.append(dict(id="REST-INTEGRATION-" + t._testMethodName, status="pass"))
        def addFailure(self, t, err):
            super().addFailure(t, err)
            self.rows.append(dict(id="REST-INTEGRATION-" + t._testMethodName, status="fail"))
        def addError(self, t, err):
            super().addError(t, err)
            self.rows.append(dict(id="REST-INTEGRATION-" + t._testMethodName, status="error"))
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RestIntegrationTests))
    paths = ["tools/test_rest_integration.py", "engine/rest_intervals.py", "engine/downtime.py",
             "engine/engine.py", "engine/life.py", "engine/gm_state.py", "engine/frequency.py",
             "engine/action_points.py", "data/core-rules.json", "data/conditions.json", "input/ch07-combat.md"]
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(),
                  scope="Rest continuity, daily allowance, shared clock, extended-rest milestone and rewind integration only.",
                  whole_rule_certified=False, tests_run=result.testsRun, results=result.rows,
                  input_hashes={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths})
    (ROOT / "output/rest-integration-tests.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
