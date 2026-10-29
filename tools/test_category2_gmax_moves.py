"""Direct producer, derivation, payload, lifetime, exception and save tests for G-Max."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
CANON = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path.insert(0, str(ROOT / "engine"))

import gmax_moves as GMAX
import vortex_state as VORTEX
from builder import build_pokemon
from engine import Combatant, Engine, Rules
from native_scenario_fixture import prepare_gmax_scene


COMPLETED = {
    "C2CSV-MOVE-R1016", "C2CSV-MOVE-R1017", "C2CSV-MOVE-R1018",
    "C2CSV-MOVE-R1021", "C2CSV-MOVE-R1036", "C2CSV-MOVE-R1039",
    "C2CSV-MOVE-R1041", "C2CSV-MOVE-R1043", "C2CSV-MOVE-R1046",
}
ADDITIONAL = {"C2CSV-MOVE-R1034", "C2CSV-MOVE-R1035", "C2CSV-MOVE-R1045"}
DEFERRED = {
    "C2CSV-MOVE-R1027",
}


class GMaxMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")
        cls.declarations = {row["clause_id"]: row for row in GMAX.declarations(cls.r)}

    def world(self, clause, *, seed=1):
        return prepare_gmax_scene(self.r, self.declarations[clause], seed=seed)

    def activate(self, clause, *, seed=1):
        engine, actor, target, base, move_id = self.world(clause, seed=seed)
        result = engine.use_gmax_move_on(actor, target, base, move_id, [actor, target])
        return engine, actor, target, base, move_id, result

    def test_exact_source_rows_completed_subset_and_explicit_resumes(self):
        policy = json.loads((ROOT / "data/gmax-move-policy.json").read_text(encoding="utf-8"))
        self.assertEqual({row["clause_id"] for row in policy["moves"]}, COMPLETED | ADDITIONAL)
        self.assertEqual({row["clause_id"] for row in policy["deferred"]}, DEFERRED)
        self.assertTrue(all(row.get("reason") and row.get("resume_when") for row in policy["deferred"]))
        status_root = CANON if CANON.exists() else ROOT
        status = json.loads((status_root / "data/verification/category2-csv-abilities-moves-status.json").read_text(encoding="utf-8"))
        rows = {row["row_id"]: row for row in status["rows"] if row["row_id"] in COMPLETED | ADDITIONAL | DEFERRED}
        self.assertEqual(set(rows), COMPLETED | ADDITIONAL | DEFERRED)
        for declaration in policy["moves"] + policy["deferred"]:
            self.assertEqual(declaration["source_row_sha256"], rows[declaration["clause_id"]]["source_row_sha256"])

    def test_exact_species_learned_base_class_and_direct_call_gate(self):
        engine, actor, target, base, move_id = self.world("C2CSV-MOVE-R1016")
        planned = GMAX.plan(engine, actor, base, move_id)
        self.assertEqual(planned["class"], self.r.move(base)["class"])
        self.assertEqual(actor.spec[GMAX.STATE]["species_id"], self.declarations["C2CSV-MOVE-R1016"]["species_id"])
        before = (deepcopy(actor.budget), deepcopy(actor.move_uses),
                  deepcopy(getattr(engine, "_move_completions", {})))
        with self.assertRaisesRegex(ValueError, "direct G-Max use"):
            engine.use_move_on(actor, target, move_id, [actor, target])
        self.assertEqual((actor.budget, actor.move_uses,
                          getattr(engine, "_move_completions", {})), before)
        other = self.declarations["C2CSV-MOVE-R1017"]["move_id"]
        with self.assertRaisesRegex(ValueError, "exact species"):
            GMAX.plan(engine, actor, base, other)
        actor.moves.remove(base)
        actor.spec["moves"].remove(base)
        with self.assertRaisesRegex(ValueError, "actually learned"):
            GMAX.plan(engine, actor, base, move_id)

    def test_native_completion_hit_owns_payload_and_miss_has_none(self):
        hit, actor, target, base, move_id = self.world("C2CSV-MOVE-R1016", seed=1)
        hit.use_gmax_move_on(actor, target, base, move_id, [actor, target])
        self.assertEqual(len(hit._gmax_payload_receipts), 1)
        receipt = hit._move_completions[hit._gmax_payload_receipts[0]["completion_id"]]
        self.assertEqual(receipt["phase"], "complete")
        self.assertTrue(any(row["hit"] for row in receipt["results"].values()))

        miss, actor, target, base, move_id = self.world("C2CSV-MOVE-R1016", seed=31)
        before_hp = target.hp
        miss.use_gmax_move_on(actor, target, base, move_id, [actor, target])
        self.assertEqual(target.hp, before_hp)
        self.assertEqual(miss._gmax_payload_receipts, [])
        self.assertNotIn(GMAX.EFFECTS, target.spec)

    def test_all_field_targets_share_one_preflight_and_transaction(self):
        engine, actor, first, base, move_id = self.world("C2CSV-MOVE-R1021")
        second = Combatant(self.r, build_pokemon(self.r, "Pikachu", 20, side="wild"))
        engine.gm.add_combatant(second)
        engine.time_actors([second])
        # The caller may provide an incomplete local view; the source says the
        # whole field, so the registered second foe must still participate.
        engine.use_gmax_move_on(actor, first, base, move_id, [actor, first])
        self.assertIn("혼란", first.conditions)
        self.assertIn("혼란", second.conditions)
        self.assertEqual(set(engine._gmax_payload_receipts[-1]["target_ids"]),
                         {first.entity_id, second.entity_id})

        engine, actor, first, base, move_id = self.world("C2CSV-MOVE-R1021")
        invalid = Combatant(self.r, build_pokemon(self.r, "Pikachu", 20, side="wild"))
        engine.gm.add_combatant(invalid)
        invalid.dead = True
        engine.time_actors([invalid])
        before = (deepcopy(actor.budget), deepcopy(actor.move_uses),
                  deepcopy(getattr(engine, "_move_completions", {})))
        with self.assertRaisesRegex(ValueError, "live field participants"):
            engine.use_gmax_move_on(actor, first, base, move_id, [actor, first])
        self.assertNotIn("혼란", first.conditions)
        self.assertEqual(engine._gmax_coin_rewards, [])
        self.assertEqual((actor.budget, actor.move_uses,
                          getattr(engine, "_move_completions", {})), before)

    def test_all_nine_actual_payload_producers(self):
        observed = set()
        for clause in sorted(COMPLETED):
            with self.subTest(clause=clause):
                engine, actor, target, base, move_id, result = self.activate(clause)
                self.assertEqual(engine._gmax_payload_receipts[-1]["clause_id"], clause)
                observed.add(clause)
                effect = self.declarations[clause]["effect"]
                rows = target.spec.get(GMAX.EFFECTS, [])
                if effect == "confuse_and_coins":
                    self.assertIn("혼란", target.conditions)
                    reward = engine._gmax_coin_rewards[-1]
                    self.assertEqual(reward["amount"], actor.level * sum(reward["rolls"]))
                elif effect == "sandblast":
                    self.assertIn("수렁", target.conditions)
                    self.assertEqual(rows[-1]["turns"], 4)
                elif effect == "bind":
                    self.assertIn("조이기", target.conditions)
                    self.assertTrue(rows[-1]["persists_if_owner_leaves"])
                elif effect == "delayed_sleep":
                    self.assertEqual(rows[-1]["face"], 2)
                    self.assertTrue(rows[-1]["pending"])
                    self.assertNotIn("잠듦", target.conditions)
                elif effect == "disable_and_suppress_last_move":
                    disabled = rows[-1]["disabled_move_id"]
                    self.assertEqual(disabled, target.last_move)
                    self.assertIn("사슬묶기", target.conditions)
                    self.assertIn("억압", target.conditions)
                else:
                    self.assertEqual(rows[-1]["kind"], "typed_residual")
                    self.assertEqual(rows[-1]["turns"], 4)
        self.assertEqual(observed, COMPLETED)

    def test_turn_lifetimes_vortex_exception_depletion_and_encounter_restore(self):
        engine, actor, target, _, _, _ = self.activate("C2CSV-MOVE-R1016")
        target.hp = target.max_hp
        initial = target.hp
        loss = target.base_max_hp // 6
        for remaining in (3, 2, 1, 0):
            GMAX.start_turn(engine, target)
            self.assertEqual(target.hp, initial - loss * (4 - remaining))
            rows = target.spec.get(GMAX.EFFECTS, [])
            self.assertEqual(rows[0]["turns"] if rows else 0, remaining)

        engine, actor, target, _, _, _ = self.activate("C2CSV-MOVE-R1043")
        GMAX.start_turn(engine, target)
        self.assertIn("잠듦", target.conditions)
        self.assertNotIn(GMAX.EFFECTS, target.spec)

        engine, actor, target, _, _, _ = self.activate("C2CSV-MOVE-R1041")
        actor.on_field = False
        VORTEX.turn_start(engine, target)
        self.assertIn("조이기", target.conditions)

        engine, actor, target, _, _, _ = self.activate("C2CSV-MOVE-R1046")
        row = target.spec[GMAX.EFFECTS][0]
        self.assertIn("억압", target.conditions)
        self.assertFalse(engine.cure_status(target, "억압"))
        self.assertIn("억압", target.conditions)
        import condition_instances as CONDITIONS
        CONDITIONS.boundary(engine, round_end=True)
        self.assertIn("억압", target.conditions)
        allowed, reason = GMAX.move_allowed(engine, target, self.r.move(row["disabled_move_id"]))
        self.assertFalse(allowed)
        non_at_will = next(self.r.move(mid) for mid in target.moves
                           if self.r.move(mid)["id"] != row["disabled_move_id"] and
                           __import__("frequency").move_frequency(engine, mid, target)[0] != "at_will")
        self.assertFalse(GMAX.move_allowed(engine, target, non_at_will)[0])
        GMAX.end_encounter(engine, [actor, target])
        self.assertNotIn(GMAX.STATE, actor.spec)
        self.assertNotIn(GMAX.EFFECTS, target.spec)
        self.assertNotIn("억압", target.conditions)
        self.assertIsNone(actor.form)

    def test_save_restore_preserves_effect_sequence_coin_and_receipt_authority(self):
        engine, actor, target, _, _, _ = self.activate("C2CSV-MOVE-R1021")
        payload_before = deepcopy(engine._gmax_payload_receipts)
        reward_before = deepcopy(engine._gmax_coin_rewards)
        state = engine.export_state()
        restored = Engine.import_state(self.r, state)
        self.assertEqual(restored._gmax_payload_receipts, payload_before)
        self.assertEqual(restored._gmax_coin_rewards, reward_before)
        self.assertEqual(restored._gmax_effect_sequence, engine._gmax_effect_sequence)
        self.assertTrue(restored.validate_state()["valid"])
        owner = next(row for row in restored.time_actors() if row.side == "party")
        self.assertEqual(owner.form, owner.spec[GMAX.STATE]["form_id"])
        restored._gmax_payload_receipts[0]["completion_id"] = "forged"
        with self.assertRaisesRegex(ValueError, "gmax_state"):
            restored.export_state()


if __name__ == "__main__":
    unittest.main()
