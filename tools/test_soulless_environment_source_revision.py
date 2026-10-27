"""Environmental injury immunity on native bodies, clocks and saved worlds."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from builder import build_pokemon
from engine import Rules, Engine, Combatant
import actor_templates as TEMPLATES
import environmental_effects as ENV
import environmental_capabilities as CAP
from native_scenario_fixture import assert_rejected_unchanged


class SoullessEnvironmentSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def world(self, kind="soulless"):
        e = Engine(self.r, seed=701)
        c = Combatant(self.r, build_pokemon(
            self.r, "껍질몬" if kind == "soulless" else "꼬렛", 50, moves=[]))
        e.gm.add_combatant(c, side="party", reason="actual native environmental subject")
        if kind == "swarm":
            e.gm.set_encounter_template(
                c, kind="swarm", total_bars=3,
                action_slots=[{"id": "a", "initiative": 20}, {"id": "b", "initiative": 15}],
                member_count_or_band="25_to_40", reason="actual observed native swarm")
        self.assertEqual(TEMPLATES.injuries_immune(c), kind != "ordinary")
        return e, c

    def breath(self, e, c, *, available=False, timing=None):
        return e.observe_breathing(
            c, air_available=available, medium="air" if available else "airless",
            reason="actual breathing observation", timing_policy=timing)

    def loaded(self, e, c):
        loaded = Engine.import_state(self.r, json.loads(json.dumps(e.export_state())))
        actor = next(x for x in loaded.everyone if x.entity_id == c.entity_id)
        return loaded, actor

    def counters(self, c):
        row = c.spec["_respiration"]
        return (row["applied_injuries"], row["protected_injuries"], row.get("prevented_injuries", 0))

    def test_real_falls_keep_damage_and_record_applied_or_prevented_height_injuries(self):
        for kind, natural, expected in (("soulless", True, 2), ("swarm", False, 4),
                                         ("ordinary", False, 4)):
            with self.subTest(kind=kind):
                e, c = self.world(kind)
                hp = c.hp
                result = e.falling_damage(
                    c, action_id="actual-eight-meter-fall", meters=8, intentional=False,
                    reason="actual observed eight-meter fall")
                self.assertEqual(result["status"], "resolved")
                self.assertEqual(result["natural_sky"], natural)
                self.assertGreater(result["damage"], 0)
                self.assertEqual(c.hp, hp - result["damage"])
                self.assertEqual(result["damage_injuries"], 0)
                applied = expected if kind == "ordinary" else 0
                self.assertEqual((c.injuries, result["height_injuries"],
                                  result["height_injuries_prevented"]),
                                 (applied, applied, expected - applied))
                self.assertEqual(c.dead, False)
                self.assertEqual(c.spec["_fall_events"][result["action_id"]], result)
                assert_rejected_unchanged(
                    e, lambda: e.falling_damage(
                        c, action_id=result["action_id"], meters=8, intentional=False,
                        reason="attempt to replay this same real fall"),
                    reason_pattern="already resolved")
                e.gm.snapshot("actual-fall")
                restored, actor = self.loaded(e, c)
                self.assertEqual(actor.spec["_fall_events"], c.spec["_fall_events"])
                self.assertEqual((actor.hp, actor.injuries, actor.dead), (c.hp, c.injuries, False))
                e.gm.restore("actual-fall")
                self.assertEqual((c.hp, c.injuries), (actor.hp, actor.injuries))

    def test_soulless_suffocation_consumes_both_selected_phases_without_fake_recovery(self):
        for timing, first in ENV.TIMINGS.items():
            with self.subTest(timing=timing):
                e, c = self.world()
                self.breath(e, c, timing=timing)
                e.advance_time(first - 1)
                self.assertEqual(self.counters(c), (0, 0, 0))
                started = c.spec["_respiration"]["deprivation_started_at"]
                self.breath(e, c)
                e.advance_time(1)
                self.assertEqual((c.injuries, self.counters(c)), (0, (0, 0, 1)))
                self.assertEqual(c.spec["_respiration"]["deprivation_started_at"], started)
                other = next(name for name in ENV.TIMINGS if name != timing)
                assert_rejected_unchanged(
                    e, lambda: self.breath(e, c, timing=other), reason_pattern="cannot change suffocation timing")
                e.advance_time(20)
                self.assertEqual((c.injuries, self.counters(c), c.dead), (0, (0, 0, 3), False))
                self.breath(e, c)
                e.advance_time(0)
                self.assertEqual(self.counters(c), (0, 0, 3))
                before = deepcopy(c.spec.get("injury_healing_history", []))
                self.breath(e, c, available=True)
                self.assertEqual(self.counters(c), (0, 0, 0))
                self.assertEqual(c.spec.get("injury_healing_history", []), before)
                self.breath(e, c, timing=timing)
                e.advance_time(first)
                self.assertEqual(self.counters(c), (0, 0, 1))

    def test_prevented_ticks_survive_both_restores_and_legacy_absent_counter_is_zero(self):
        e, c = self.world()
        self.breath(e, c, timing="grace_boundary")
        e.advance_time(70)
        self.assertEqual(self.counters(c), (0, 0, 2))
        e.gm.snapshot("deprivation-at-seventy")
        restored, actor = self.loaded(e, c)
        restored.advance_time(10)
        self.assertEqual((actor.injuries, self.counters(actor)), (0, (0, 0, 3)))
        e.advance_time(10)
        e.gm.restore("deprivation-at-seventy")
        self.assertEqual((e.elapsed_seconds, self.counters(c)), (70, (0, 0, 2)))
        e.advance_time(20)
        self.assertEqual((c.injuries, self.counters(c)), (0, (0, 0, 4)))

        ordinary, p = self.world("ordinary")
        self.breath(ordinary, p, timing="grace_boundary")
        # An older valid respiration record has no prevented counter. It is
        # deliberately loaded through the native codec rather than upgraded by hand.
        p.spec["_respiration"].pop("prevented_injuries")
        legacy, q = self.loaded(ordinary, p)
        self.assertNotIn("prevented_injuries", q.spec["_respiration"])
        legacy.advance_time(60)
        self.assertEqual((q.injuries, self.counters(q)), (1, (1, 1, 0)))
        self.breath(legacy, q, available=True)
        self.assertEqual((q.injuries, self.counters(q)), (0, (0, 0, 0)))
        self.assertEqual(q.spec["injury_healing_history"][-1]["count"], 1)

    def test_actual_swarm_deactivation_does_not_replay_prevented_suffocation(self):
        e, c = self.world("swarm")
        self.breath(e, c, timing="grace_boundary")
        e.advance_time(70)
        self.assertEqual((c.injuries, self.counters(c)), (0, (0, 0, 2)))
        state = deepcopy(c.spec["encounter_template"])
        state["active"] = False
        e.gm.record_encounter_template(
            c, state=state, request_id="actual-swarm-end", reason="actual GM observation ending swarm template")
        self.assertFalse(TEMPLATES.injuries_immune(c))
        self.breath(e, c)
        e.advance_time(10)
        self.assertEqual((c.injuries, self.counters(c)), (1, (1, 1, 2)))
        restored, actor = self.loaded(e, c)
        restored.advance_time(10)
        self.assertEqual((actor.injuries, self.counters(actor)), (2, (2, 2, 2)))
        self.breath(restored, actor, available=True)
        self.assertEqual((actor.injuries, self.counters(actor)), (0, (0, 0, 0)))
        self.assertEqual(actor.spec["injury_healing_history"][-1]["count"], 2)

    def test_due_vacuum_checks_record_actual_protection_and_consume_real_check_once(self):
        policy = json.loads((ROOT / "data/examples/environment-derive.json").read_text(encoding="utf-8"))
        for kind in ("soulless", "swarm", "ordinary"):
            with self.subTest(kind=kind):
                e, c = self.world(kind)
                e.observe_environment(
                    "actual-vacuum", dict(gravity=1, pressure=0, air_available=False, medium="airless"),
                    source=policy["source"], reason="actual measured zero-pressure region")
                e.bind_environment(c, policy, region_id="actual-vacuum", reason="actual subject location")
                self.breath(e, c, timing="grace_boundary")
                exposure = e.observe_vacuum_exposure(
                    c, exposure_id="actual-vacuum-exposure", exposed=True, reason="actual vacuum exposure")
                self.assertEqual(exposure["interval_seconds"], 10)
                e.advance_time(10)
                row = c.spec[CAP.KEY]["vacuum_exposures"][exposure["id"]]
                self.assertEqual(len(row["pending"]), 1)
                check_id = next(iter(row["pending"]))
                receipt = e.resolve_vacuum_injury_check(
                    c, check_id=check_id, injury_delta=1, reason="actual adjudicated injury result")
                applied = 1 if kind == "ordinary" else 0
                self.assertEqual((receipt["injury_delta_requested"], receipt["injury_delta"],
                                  receipt["injury_delta_prevented"], receipt["injuries_before"],
                                  receipt["injuries_after"], c.injuries),
                                 (1, applied, 1 - applied, 0, applied, applied))
                current = c.spec[CAP.KEY]["vacuum_exposures"][exposure["id"]]
                self.assertEqual((current["pending"], current["resolved"]), ({}, [receipt]))
                assert_rejected_unchanged(
                    e, lambda: e.resolve_vacuum_injury_check(
                        c, check_id=check_id, injury_delta=1, reason="same consumed vacuum check"),
                    reason_pattern="actual due vacuum injury check")
                e.gm.snapshot("resolved-vacuum")
                restored, actor = self.loaded(e, c)
                self.assertEqual(actor.spec[CAP.KEY]["vacuum_exposures"][exposure["id"]]["resolved"], [receipt])
                restored.advance_time(10)
                next_row = actor.spec[CAP.KEY]["vacuum_exposures"][exposure["id"]]
                self.assertEqual((actor.injuries, len(next_row["pending"]), len(next_row["resolved"])),
                                 (applied, 1, 1))
                self.assertNotIn(check_id, next_row["pending"])
                self.assertEqual(self.counters(actor), (0, 0, 0))
                e.advance_time(10)
                e.gm.restore("resolved-vacuum")
                self.assertEqual(c.spec[CAP.KEY]["vacuum_exposures"][exposure["id"]]["resolved"], [receipt])
                self.assertEqual((c.injuries, c.spec[CAP.KEY]["vacuum_exposures"][exposure["id"]]["pending"]),
                                 (applied, {}))


if __name__ == "__main__":
    unittest.main()
