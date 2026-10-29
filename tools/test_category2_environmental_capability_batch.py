"""Three CSV respiration/vacuum capabilities on native region and injury clocks."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(CANONICAL / "engine"), str(CANONICAL / "tools")]

# Load the staged entry points before the canonical fixture prepends its own
# root to sys.path.  Subsequent imports therefore reuse these staged modules.
import engine as ENGINE_MODULE
import environmental_effects as ENVIRONMENTAL_EFFECTS
import environment_change as ENVIRONMENT_CHANGE
import test_foundation_environment_derive as FIXTURE
import environmental_capabilities as CAP
import state_codec as CODEC
import state_grants as GRANTS


class EnvironmentalCapabilityBatchTests(unittest.TestCase):
    setUpClass = classmethod(FIXTURE.EnvironmentTests.setUpClass.__func__)
    setUp = FIXTURE.EnvironmentTests.setUp
    add = FIXTURE.EnvironmentTests.add
    pokemon = FIXTURE.EnvironmentTests.pokemon
    restored = FIXTURE.EnvironmentTests.restored
    policy = FIXTURE.EnvironmentTests.policy

    def region(self, actor, *, vacuum=False):
        facts = dict(gravity=1, pressure=0 if vacuum else 1,
                     air_available=not vacuum, medium="airless" if vacuum else "air")
        self.e.observe_environment("region", facts, source=self.policy()["source"],
                                   reason="actual measured environmental region")
        self.e.bind_environment(actor, self.policy(), reason="actual actor environment binding")

    def grant(self, actor, name, source=None):
        GRANTS.grant(actor, "capabilities", name, source or "fixture:" + name,
                     "actual sourced capability")

    def test_policy_is_exact_three_source_rows_and_hashes(self):
        value = CAP.policy()
        self.assertEqual({row["clause_id"] for row in value["capabilities"]}, {
            "C2CSV/item-data:65:5", "C2CSV/item-data:66:5", "C2CSV/item-data:86:5",
        })
        source = CANONICAL / value["source_file"]
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), value["source_file_sha256"])
        self.assertEqual(value["vacuum_check_seconds"], {"ordinary": 10, "vacuum_resistance": 300})

    def test_breathless_stops_suffocation_but_not_vacuum_injury_clock(self):
        self.region(self.p, vacuum=True); self.grant(self.p, "무호흡")
        breathing = self.e.observe_breathing(
            self.p, air_available=False, medium="airless", reason="actual vacuum atmosphere",
            timing_policy="grace_boundary")
        self.assertTrue(breathing["breathing"])
        exposure = self.e.observe_vacuum_exposure(
            self.p, exposure_id="vacuum/breathless", exposed=True,
            reason="actual zero-pressure exposure")
        self.assertEqual(exposure["interval_seconds"], 10)
        self.e.advance_time(10)
        pending = self.p.spec[CAP.KEY]["vacuum_exposures"]["vacuum/breathless"]["pending"]
        check_id = next(iter(pending))
        self.e.resolve_vacuum_injury_check(
            self.p, check_id=check_id, injury_delta=1, reason="actual failed vacuum injury check")
        self.assertEqual(self.p.injuries, 1)
        self.e.advance_time(10)
        self.assertEqual(self.p.injuries, 1)  # due again, unresolved; no invented outcome

    def test_environment_transfer_uses_live_breathless_source_without_resetting_other_rules(self):
        self.e.grid = None; self.grant(self.p, "무호흡")
        source = self.policy()["source"]
        self.e.observe_environment(
            "air", dict(gravity=1, pressure=1, air_available=True, medium="air"),
            source=source, reason="actual breathable region")
        self.e.observe_environment(
            "vacuum", dict(gravity=0, pressure=0, air_available=False, medium="airless"),
            source=source, reason="actual vacuum region")
        self.e.bind_environment(
            self.p, self.policy(), region_id="air", reason="actual initial environment")
        self.e.transfer_environment(
            self.p, "vacuum", reason="actual regional relocation", timing_policy="grace_boundary")
        self.assertTrue(self.p.spec["_respiration"]["breathing"])
        self.e.advance_time(600)
        self.assertEqual(self.p.injuries, 0)

    def test_vacuum_immunity_prevents_exposure_checks_but_does_not_grant_breathing(self):
        self.region(self.p, vacuum=True); self.grant(self.p, "진공면역")
        exposure = self.e.observe_vacuum_exposure(
            self.p, exposure_id="vacuum/immune", exposed=True,
            reason="actual zero-pressure exposure")
        self.assertIsNone(exposure["interval_seconds"])
        breathing = self.e.observe_breathing(
            self.p, air_available=False, medium="airless", reason="vacuum lacks breathable air",
            timing_policy="grace_boundary")
        self.assertFalse(breathing["breathing"])
        self.e.advance_time(60)
        current = self.p.spec[CAP.KEY]["vacuum_exposures"]["vacuum/immune"]
        self.assertEqual((self.p.injuries, current["pending"]), (1, {}))

    def test_vacuum_resistance_uses_five_minute_due_check_and_requires_live_source(self):
        self.region(self.p, vacuum=True); self.grant(self.p, "진공내성"); self.grant(self.p, "무호흡")
        exposure = self.e.observe_vacuum_exposure(
            self.p, exposure_id="vacuum/resistant", exposed=True,
            reason="actual zero-pressure exposure")
        self.assertEqual(exposure["next_due_at"], 300)
        self.e.advance_time(299); self.assertFalse(self.p.spec[CAP.KEY]["vacuum_exposures"]["vacuum/resistant"]["pending"])
        self.e.advance_time(1)
        check_id = next(iter(self.p.spec[CAP.KEY]["vacuum_exposures"]["vacuum/resistant"]["pending"]))
        with self.assertRaisesRegex(ValueError, "resolve the due"):
            self.e.advance_time(1)
        self.e.resolve_vacuum_injury_check(
            self.p, check_id=check_id, injury_delta=0, reason="actual successful vacuum injury check")
        GRANTS.revoke(self.p, "fixture:진공내성")
        with self.assertRaisesRegex(ValueError, "capability source"):
            self.e.advance_time(1)

    def test_pending_and_consumed_checks_survive_json_restore_and_tampering_rejects(self):
        self.region(self.p, vacuum=True); self.grant(self.p, "진공내성"); self.grant(self.p, "무호흡")
        self.e.observe_vacuum_exposure(
            self.p, exposure_id="vacuum/restore", exposed=True,
            reason="actual zero-pressure exposure")
        self.e.advance_time(300)
        loaded = self.restored(); actor = next(c for c in loaded.everyone if c.entity_id == self.p.entity_id)
        row = actor.spec[CAP.KEY]["vacuum_exposures"]["vacuum/restore"]
        check_id = next(iter(row["pending"]))
        loaded.resolve_vacuum_injury_check(
            actor, check_id=check_id, injury_delta=1, reason="restored actual failed check")
        self.assertEqual((actor.injuries, row["pending"], row["resolved"][0]["id"]), (1, {}, check_id))
        state = CODEC.dump_engine(loaded)
        rebuilt = CODEC.load_engine(self.r, json.loads(json.dumps(state, ensure_ascii=False)))
        rebuilt_actor = next(c for c in rebuilt.everyone if c.entity_id == actor.entity_id)
        self.assertEqual(rebuilt_actor.spec[CAP.KEY], actor.spec[CAP.KEY])
        rebuilt_actor.spec[CAP.KEY]["vacuum_exposures"]["vacuum/restore"]["intent"]["interval_seconds"] = 10
        with self.assertRaises(CODEC.StateCodecError):
            CODEC.dump_engine(rebuilt)

    def test_derived_vacuum_clock_tampering_rejects_both_restores_unchanged(self):
        self.region(self.p, vacuum=True); self.grant(self.p, "무호흡")
        exposure_id = "vacuum/derived-clock"
        self.e.observe_vacuum_exposure(self.p, exposure_id=exposure_id, exposed=True,
                                       reason="actual ordinary vacuum exposure")
        self.e.gm.snapshot("vacuum-tamper")
        original = self.e.gm.snapshots["vacuum-tamper"]
        memo = {**original["actor_refs"], id(self.e): self.e, id(self.r): self.r}
        baseline = CODEC.dump_engine(self.e)
        cases = ({"interval_seconds": None}, {"next_due_at": None},
                 {"interval_seconds": None, "next_due_at": None},
                 {"interval_seconds": 300}, {"next_due_at": 300}, {"sequence": 1})
        for changes in cases:
            with self.subTest(changes=changes):
                saved = deepcopy(baseline)
                node = next(n for n in saved["nodes"].values() if n["kind"] == "dict"
                            and ["id", exposure_id] in n["items"])
                node["items"] = [[key, changes.get(key, value)] for key, value in node["items"]]
                with self.assertRaises(CODEC.StateCodecError):
                    CODEC.load_engine(self.r, saved)
                self.assertEqual(CODEC.dump_engine(self.e), baseline)
                tampered = deepcopy(original, memo)
                tampered["combatants"][id(self.p)]["spec"][CAP.KEY]["vacuum_exposures"][exposure_id].update(changes)
                self.e.gm.snapshots["vacuum-tamper"] = tampered
                with self.assertRaisesRegex(ValueError, "vacuum"):
                    self.e.gm.restore("vacuum-tamper")
                self.assertEqual(CODEC.dump_engine(self.e), baseline)
        self.e.gm.snapshots["vacuum-tamper"] = original
        self.e.advance_time(10)
        self.assertEqual(len(self.p.spec[CAP.KEY]["vacuum_exposures"][exposure_id]["pending"]), 1)

    def test_vacuum_pending_and_resolved_check_history_cannot_change_boundaries(self):
        self.region(self.p, vacuum=True); self.grant(self.p, "무호흡")
        exposure_id = "vacuum/check-history"
        self.e.observe_vacuum_exposure(self.p, exposure_id=exposure_id, exposed=True,
                                       reason="actual ordinary vacuum exposure")
        self.e.advance_time(10)
        check_id = exposure_id + ":check:1"
        for resolved in (False, True):
            if resolved:
                self.e.resolve_vacuum_injury_check(self.p, check_id=check_id, injury_delta=0,
                                                  reason="actual successful check")
            baseline = CODEC.dump_engine(self.e)
            cases = [{"due_at": 20}, {"id": exposure_id + ":check:2"}, {"interval_seconds": 300}]
            if resolved:
                cases += [{"resolved_at": 9}, {"injuries_after": 1}, {"injury_delta_requested": 1}]
            for changes in cases:
                with self.subTest(resolved=resolved, changes=changes):
                    saved = deepcopy(baseline)
                    node = next(n for n in saved["nodes"].values() if n["kind"] == "dict"
                                and ["id", check_id] in n["items"])
                    node["items"] = [[key, changes.get(key, value)] for key, value in node["items"]]
                    with self.assertRaises(CODEC.StateCodecError):
                        CODEC.load_engine(self.r, saved)
                    self.assertEqual(CODEC.dump_engine(self.e), baseline)
        self.e.advance_time(10)
        self.assertIn(exposure_id + ":check:2", self.p.spec[CAP.KEY]["vacuum_exposures"][exposure_id]["pending"])

    def test_vacuum_clock_roundtrips_preserve_ordinary_resistant_immune_and_ended_history(self):
        for capability, interval in ((None, 10), ("진공내성", 300), ("진공면역", None)):
            with self.subTest(capability=capability):
                self.setUp(); self.region(self.p, vacuum=True); self.grant(self.p, "무호흡")
                if capability:self.grant(self.p, capability)
                self.e.observe_breathing(self.p, air_available=False, medium="airless",
                                         reason="actual Breathless actor", timing_policy="grace_boundary")
                exposure_id = "vacuum/roundtrip"
                self.e.observe_vacuum_exposure(self.p, exposure_id=exposure_id, exposed=True,
                                               reason="actual source-bound exposure")
                self.e.advance_time(interval or 600)
                self.e.gm.restore(self.e.gm.snapshot("vacuum-roundtrip"))
                loaded = self.restored()
                actor = next(c for c in loaded.everyone if c.entity_id == self.p.entity_id)
                row = actor.spec[CAP.KEY]["vacuum_exposures"][exposure_id]
                self.assertEqual(row["interval_seconds"], interval)
                if interval:
                    self.assertEqual(row["next_due_at"], interval * 2)
                    loaded.resolve_vacuum_injury_check(actor, check_id=exposure_id + ":check:1",
                                                       injury_delta=0, reason="actual successful check")
                else:
                    self.assertEqual((row["sequence"], row["pending"], row["next_due_at"]), (0, {}, None))
                loaded.observe_vacuum_exposure(actor, exposure_id=exposure_id, exposed=False,
                                               reason="actual exposure ended")
                if capability:GRANTS.revoke(actor, "fixture:" + capability, engine=loaded)
                history = deepcopy(actor.spec[CAP.KEY])
                rebuilt = CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(loaded))))
                restored = next(c for c in rebuilt.everyone if c.entity_id == actor.entity_id)
                self.assertEqual(restored.spec[CAP.KEY], history)

    def test_invalid_exposure_is_atomic_before_clock_or_receipt(self):
        self.region(self.p)
        before = deepcopy((self.e.elapsed_seconds, self.p.spec, self.p.injuries, self.e.rng.getstate()))
        with self.assertRaisesRegex(ValueError, "zero-pressure"):
            self.e.observe_vacuum_exposure(
                self.p, exposure_id="vacuum/not-real", exposed=True, reason="not a vacuum")
        self.assertEqual((self.e.elapsed_seconds, self.p.spec, self.p.injuries, self.e.rng.getstate()), before)
        self.assertNotIn(CAP.KEY, self.p.spec)


if __name__ == "__main__":
    unittest.main()
