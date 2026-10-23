"""Dispatcher regression tests with real shared-clock/lifetime transitions.

AI and per-turn effects are isolated so timestamps follow the independently
specified contract: completed round = 10 seconds, decisive action = unknown
partial round unless externally timestamped, round limit = pause not encounter end.
"""
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
import encounter
import downtime as DT
import frequency as FREQ


class EncounterTimeExitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")

    def fixture(self, rounds=3):
        e = Engine(self.rules)
        actors = [Combatant(self.rules, dict(name=name, level=3, kind="trainer",
                  stats={"hp":9, "atk":5, "def":5, "spa":5, "spd":5, "spe":5},
                  types=["노말"], moves=[])) for name in ("Party", "Wild")]
        e.everyone = e.gm.everyone = actors
        e.initiative = lambda cs: [c for c in actors if c in cs]
        e.start_of_turn = lambda c: None
        e.end_of_turn = lambda c: None
        return e, dict(name="clock-test", rounds=rounds), [actors[0]], [actors[1]]

    def run_fixture(self, fixture, *, action=None, hook=None):
        with patch.object(encounter, "load_encounter", return_value=fixture), \
             patch.object(encounter, "describe", side_effect=lambda s: s["name"]), \
             patch.object(encounter, "choose_action", side_effect=action or (lambda *a: (None, None, None))):
            return encounter.run_encounter(str(ROOT), "unused.json", hook=hook, write=False)

    def test_completed_round_limit_credits_every_round_once(self):
        e, _, party, wild = fixture = self.fixture(3)
        self.run_fixture(fixture)
        self.assertEqual((e.round_no, e.elapsed_seconds), (3, 30))
        self.assertIsNone(e.round_start_seconds)
        self.assertEqual(e.unresolved_time_intervals, [])
        self.assertEqual([c.life_elapsed_seconds for c in party + wild], [30, 30])
        DT.rest(e, party[0], 30)
        self.assertEqual(e.elapsed_seconds, 1830)

    def test_round_limit_preserves_ongoing_encounter_state(self):
        e, _, party, _ = fixture = self.fixture(1)
        c = party[0]
        c.stages["atk"] = 2
        e.apply_status(c, "혼란")
        c.spec["ap_spent"] = 2
        FREQ.consume_activation(c, "fixture", {"kind": "scene", "uses": 1})
        self.run_fixture(fixture)
        self.assertEqual(c.stages["atk"], 2)
        self.assertIn("혼란", c.conditions)
        self.assertEqual((c.spec["ap_spent"], FREQ.state(c)["scene"]), (2, 0))

    def test_decisive_first_action_stops_later_turns_and_records_gap(self):
        e, _, party, wild = fixture = self.fixture()
        seen = []
        def start(c):
            seen.append(c.name)
            if c is party[0]:
                wild[0].hp = 0
                e.check_fainted(wild[0])
        e.start_of_turn = start
        self.run_fixture(fixture)
        self.assertEqual(seen, ["Party"])
        self.assertEqual((e.round_no, e.elapsed_seconds), (1, 0))
        self.assertIsNone(e.round_start_seconds)
        self.assertEqual(len(e.unresolved_time_intervals), 1)
        self.assertEqual(e.unresolved_time_intervals[0]["known_seconds"], 0)
        DT.rest(e, party[0], 30)
        self.assertEqual(e.elapsed_seconds, 1800)

    def test_decisive_last_action_does_not_imply_ten_seconds(self):
        e, _, party, wild = fixture = self.fixture()
        def finish(c):
            if c is wild[0]:
                party[0].hp = 0
                e.check_fainted(party[0])
        e.end_of_turn = finish
        self.run_fixture(fixture)
        self.assertEqual((e.elapsed_seconds, len(e.unresolved_time_intervals)), (0, 1))
        self.assertIsNone(e.round_start_seconds)

    def test_complete_round_then_partial_exit_retains_only_known_seconds(self):
        e, _, party, wild = fixture = self.fixture()
        def hook(engine, c, rnd):
            if rnd == 2 and c is party[0]:
                engine.at_round_offset(3)
                wild[0].captured = True
        self.run_fixture(fixture, hook=hook)
        self.assertEqual(e.elapsed_seconds, 13)
        self.assertEqual(e.unresolved_time_intervals[0]["known_seconds"], 3)
        self.assertEqual(e.unresolved_time_intervals[0]["round"], 2)

    def test_explicit_full_round_exit_does_not_invent_gap(self):
        e, _, _, wild = fixture = self.fixture()
        def hook(engine, c, rnd):
            engine.at_round_offset(10)
            wild[0].on_field = False
        self.run_fixture(fixture, hook=hook)
        self.assertEqual(e.elapsed_seconds, 10)
        self.assertEqual(e.unresolved_time_intervals, [])
        self.assertIsNone(e.round_start_seconds)

    def test_actual_encounter_end_cleans_combat_but_preserves_scene_resources(self):
        e, _, party, wild = fixture = self.fixture()
        e.rulings.decide = lambda prompt: {
            'request_id': prompt['request_id'],
            'order': [row['key'] for row in prompt['actors']],
            'reason': 'GM explicitly resolves this actual equal-speed fixture order',
        } if prompt['type'] == 'initiative_tie_order' else None
        c = party[0]
        c.stages["atk"] = 2
        e.apply_status(c, "혼란")
        e.apply_status(c, "독")
        c.spec.update(ap_spent=2, ap_removed=1)
        FREQ.consume_activation(c, "fixture", {"kind": "scene", "uses": 1})
        def hook(engine, actor, rnd):
            wild[0].on_field = False
        self.run_fixture(fixture, hook=hook)
        self.assertEqual(c.stages["atk"], 0)
        self.assertNotIn("혼란", c.conditions)
        self.assertIn("독", c.conditions)
        self.assertEqual((c.spec["ap_spent"], c.spec["ap_removed"], FREQ.state(c)["scene"]), (2, 1, 0))
        self.assertFalse(FREQ.activation_allowed(c, "fixture", {"kind": "scene", "uses": 1}))

    def test_initially_finished_encounter_has_no_phantom_round(self):
        e, _, _, wild = fixture = self.fixture()
        wild[0].on_field = False
        self.run_fixture(fixture)
        self.assertEqual((e.round_no, e.elapsed_seconds), (0, 0))
        self.assertEqual(e.unresolved_time_intervals, [])
        self.assertIsNone(e.round_start_seconds)

    def test_zero_round_budget_does_not_end_active_encounter(self):
        e, _, party, _ = fixture = self.fixture(0)
        party[0].stages["atk"] = 2
        self.run_fixture(fixture)
        self.assertEqual((e.round_no, e.elapsed_seconds, party[0].stages["atk"]), (0, 0, 2))
        self.assertEqual(e.unresolved_time_intervals, [])


if __name__ == "__main__":
    class Result(unittest.TextTestResult):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.rows = []
        def addSuccess(self, t):
            super().addSuccess(t)
            self.rows.append(dict(id="ENCOUNTER-TIME-" + t._testMethodName, status="pass"))
        def addFailure(self, t, err):
            super().addFailure(t, err)
            self.rows.append(dict(id="ENCOUNTER-TIME-" + t._testMethodName, status="fail"))
        def addError(self, t, err):
            super().addError(t, err)
            self.rows.append(dict(id="ENCOUNTER-TIME-" + t._testMethodName, status="error"))
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(EncounterTimeExitTests))
    paths = ["tools/test_encounter_time_exit.py", "engine/encounter.py", "engine/engine.py",
             "engine/life.py", "engine/downtime.py", "engine/frequency.py", "input/ch07-combat.md"]
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(),
                  scope="Encounter dispatcher time exits only; AI and per-turn effects isolated.",
                  results=result.rows,
                  input_hashes={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths})
    (ROOT / "output/encounter-time-exit-tests.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
