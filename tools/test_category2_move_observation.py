"""Actual GM level observations retain individual natural-move history atomically."""
from pathlib import Path
from copy import deepcopy
import sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from engine import Rules, Engine, Combatant
from builder import build_pokemon
import move_state as M
import pokemon_teaching as T
import state_fields as F

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def setUp(self):
        self.e = Engine(self.r, seed=5351)
        spec = build_pokemon(self.r, "브케인", 39, moves=["move/화염방사"], abilities=[],
            extra={"move_learning": {"move/화염방사": {"method": "tm", "source": T.MACHINES,
                "learned_at_level": 30, "natural": False}}})
        self.c = Combatant(self.r, spec)
        self.e.gm.add_combatant(self.c, pos=(1, 1), reason="observed actual Pokemon")

    def test_gm_level_observation_records_opportunity_and_preserves_it_after_reduction(self):
        self.assertEqual(T.classifications(self.r, self.c.spec)["move/화염방사"], "taught")
        rng = self.e.rng.getstate()
        self.e.gm.set_level(self.c, 40, reason="GM confirms an actual level reached")
        events = deepcopy(self.c.spec[M.HISTORY]["move/화염방사"])
        self.assertEqual([(e["species_id"], e["required_level"], e["at_level"]) for e in events],
                         [("pokemon/브케인", 40, 40)])
        self.assertTrue(self.c.spec["move_learning"]["move/화염방사"]["natural"])
        self.e.gm.snapshot("observed-natural")
        self.e.gm.set_level(self.c, 39, reason="GM records a subsequent lower level")
        self.assertEqual(T.classifications(self.r, self.c.spec)["move/화염방사"], "natural")
        self.assertEqual(self.c.spec[M.HISTORY]["move/화염방사"], events)
        restored = Engine.import_state(self.r, self.e.export_state())
        c = restored.everyone[0]
        self.assertEqual((c.level, T.classifications(self.r, c.spec)["move/화염방사"]), (39, "natural"))
        self.assertEqual(c.spec["move_learning"]["move/화염방사"]["method"], "tm")
        self.e.gm.restore("observed-natural")
        self.assertEqual(self.c.level, 40)
        self.assertEqual(self.c.spec[M.HISTORY]["move/화염방사"], events)
        self.assertEqual(self.e.rng.getstate(), rng)

    def test_later_rejection_keeps_level_history_and_receipt_unmodified(self):
        self.c._nonadditive_stats = [{"effect": "unresolved transformed baseline"}]
        before = deepcopy(self.c.spec)
        stats = dict(self.c.stats)
        stats["atk"] += 1
        with self.assertRaisesRegex(ValueError, "transformation-specific"):
            F.base_patch(self.c, {"level": 40, "stats": stats}, reason="mixed observed change", request_id="reject")
        self.assertEqual(self.c.spec, before)
        self.assertEqual(self.c.level, 39)
        self.assertNotIn("reject", getattr(self.c, "_state_receipts", {}))
        self.assertEqual(getattr(self.c, "_state_revision", 0), 0)
        del self.c._nonadditive_stats
        self.c.spec["move_learning"]["move/연막"] = "malformed"
        before = deepcopy(self.c.spec)
        with self.assertRaisesRegex(ValueError, "must be a record"):
            self.e.gm.set_level(self.c, 40, reason="invalid provenance must reject before mutation")
        self.assertEqual(self.c.spec, before)

    def test_retry_preserves_single_history_and_explicit_derived_receipt(self):
        kwargs = dict(reason="confirmed observed level", request_id="level-40", expected_revision=0)
        first = F.base_patch(self.c, {"level": 40}, **kwargs)
        second = F.base_patch(self.c, {"level": 40}, **kwargs)
        self.assertEqual(first, second)
        self.assertEqual(first["derived_after"][M.HISTORY], self.c.spec[M.HISTORY])
        self.assertEqual(len(self.c.spec[M.HISTORY]["move/화염방사"]), 1)
        self.assertEqual(self.c._state_revision, 1)

    def test_forged_history_is_rejected_by_real_actor_and_save_validation(self):
        self.c.spec[M.HISTORY] = {"move/화염방사": [{"source": M.SOURCE,
            "species_id": "pokemon/브케인", "kind": "level_up", "required_level": 40,
            "at_level": 39, "reason": "invalid claimed observation"}]}
        before = deepcopy(self.c.spec)
        issues = self.e.validate_state()["issues"]
        self.assertTrue(any(row["code"] == "actor_state" and "historical species and level" in row["message"] for row in issues))
        for operation in (lambda: self.e.export_state(),
                          lambda: self.e.gm.set_level(self.c, 40, reason="reject forged prior record")):
            with self.assertRaisesRegex(ValueError, "historical species and level"):
                operation()
            self.assertEqual(self.c.spec, before)

if __name__ == "__main__":
    unittest.main()
