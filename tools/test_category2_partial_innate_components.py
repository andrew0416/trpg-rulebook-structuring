"""Direct contract tests for the four partial-Innate component clauses."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys
import unittest


STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

import ability_transitions as A
from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
from grid import Grid
import combat_timing as TIME
import state_grants as G
from state_codec import StateCodecError


SHIELD = "불굴의방패"
SWORD = "불요의검"
SHIELD_ID = "ability/불굴의방패"
SWORD_ID = "ability/불요의검"
MOVES = ["move/위액", "move/코어퍼니셔", "move/고민씨", "move/심플빔",
         "move/역할", "move/스킬스왑", "move/베껴그리기"]
CLAUSES = {
    "C10-185": "c5e727e89d391f06ee5f29714767a0db85b38d2d90ebc7fe2022d895218a2628",
    "C10-187": "30de70cf379fa26ce27ff513bfc3ccdd6d1a71ce28ff05b905ad47ad49b02fbc",
    "C10-188": "12f31b9d1da6f14eaf4648ff2040f51e4b362f655ea7f4988b717fe12fb51484",
    "C10-189": "c257a25a53bd9f24b57f0780b0bdfeaf3798baa9bae6a8a5337a085c5e1e26ab",
}


def reviewed_rules():
    rules = Rules(str(ROOT), ruleset="core")
    rules.ability_transition_policy = json.loads(
        (STAGE / "data/ability-transition-policy.json").read_text(encoding="utf-8"))
    fixtures = {
        SHIELD_ID: (SHIELD, "shield-innate", "shield-transferable"),
        SWORD_ID: (SWORD, "sword-innate", "sword-transferable"),
    }
    # These reviewed fixture rows exercise the generic component contract through
    # real Move producers. They do not assert that the two named source Abilities
    # are partially Innate in the published data.
    for uid, (name, innate, transferable) in fixtures.items():
        rules.ability_transition_policy["innate_components"][uid] = {
            "name": name,
            "source_record": "direct-contract-fixture",
            "source_cells": [],
            "components": [
                {"id": innate, "innate": True, "source_text": "fixture Innate component"},
                {"id": transferable, "innate": False, "source_text": "fixture transferable component"},
            ],
            "registration_only": False,
            "registration_judgment": "Direct generic contract fixture only.",
        }
    return rules


class PartialInnateComponentTests(unittest.TestCase):
    def setUp(self):
        self.r = reviewed_rules()
        self.e = Engine(self.r, 530)
        self.e.grid = Grid(30, 30)
        self.a = self.actor("user", [SWORD], (2, 2), "party")
        self.t = self.actor("target", [SHIELD], (3, 2), "opponent", pokemon=True)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def actor(self, name, abilities, pos, side, *, pokemon=False):
        extra = {"abilities": abilities, "size": "중형", "pos": pos, "side": side}
        if pokemon:
            spec = build_pokemon(self.r, "이상해씨", 10, name=name,
                                 moves=["move/몸통박치기"], extra=extra)
        else:
            spec = build_trainer(self.r, name, 10,
                                 dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
                                 extra=dict(extra, moves=MOVES))
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def select(self, source, ability=None):
        return self.e.gm.choose_ability_transition(
            self.a, self.t, source, ability=ability, reason="reviewed component choice")

    def use(self, source):
        self.e.use_move(self.a, self.t, source)

    def parts(self, actor, uid):
        return set(A.project_components(actor).get(uid, ()))

    def live(self, actor):
        return [row for row in TIME.records(actor) if A.TAG in row]

    def test_source_clause_digests_and_reviewed_component_contract(self):
        source = ROOT / "input/ch10-index-reference.md"
        policy = self.r.ability_transition_policy["partial_innate_component_contract"]
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), policy["source_sha256"])
        registry = json.loads((ROOT / "data/verification/category2-core-clause-status.json").read_text(encoding="utf-8"))
        rows = {row["clause_id"]: row for row in registry["clause_mappings"] if row["clause_id"] in CLAUSES}
        self.assertEqual(set(rows), set(CLAUSES))
        for clause_id, digest in CLAUSES.items():
            with self.subTest(clause_id=clause_id):
                self.assertIn(rows[clause_id]["category2_status"], {"incomplete", "implemented"})
                self.assertEqual(rows[clause_id]["statement_sha256"], digest)
                self.assertEqual(policy["clauses"][clause_id]["statement_sha256"], digest)
        self.assertTrue(A.partially_innate(self.r, SHIELD_ID))
        self.assertFalse(A.wholly_innate(self.r, SHIELD_ID))

    def test_actual_suppression_removes_only_transferable_component_then_restores(self):
        self.select("move/위액", SHIELD)
        self.use("move/위액")
        self.assertEqual(self.t.abilities, [SHIELD])
        self.assertEqual(self.parts(self.t, SHIELD_ID), {"shield-innate"})
        self.assertTrue(A.active(self.t, SHIELD_ID, "shield-innate"))
        self.assertFalse(A.active(self.t, SHIELD_ID, "shield-transferable"))
        self.e.end_encounter(self.e.everyone)
        self.assertEqual(self.parts(self.t, SHIELD_ID), {"shield-innate", "shield-transferable"})

    def test_actual_copy_transfers_only_non_innate_component_and_survives_restore(self):
        self.use("move/역할")
        self.assertEqual(self.parts(self.a, SHIELD_ID), {"shield-transferable"})
        self.assertNotIn("shield-innate", self.parts(self.a, SHIELD_ID))
        saved = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        restored = Engine.import_state(reviewed_rules(), saved)
        actor = next(row for row in restored.everyone if row.entity_id == self.a.entity_id)
        self.assertEqual(self.parts(actor, SHIELD_ID), {"shield-transferable"})
        restored.gm.recall(actor, reason="actual copied-component recall")
        self.assertNotIn(SHIELD_ID, A.project_components(actor))
        self.assertEqual(self.parts(actor, SWORD_ID), {"sword-innate", "sword-transferable"})

    def test_actual_skill_swap_retains_each_innate_side_and_restores_independently(self):
        self.select("move/스킬스왑", SWORD)
        self.use("move/스킬스왑")
        self.assertEqual(self.parts(self.a, SWORD_ID), {"sword-innate"})
        self.assertEqual(self.parts(self.a, SHIELD_ID), {"shield-transferable"})
        self.assertEqual(self.parts(self.t, SHIELD_ID), {"shield-innate"})
        self.assertEqual(self.parts(self.t, SWORD_ID), {"sword-transferable"})
        saved = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        restored = Engine.import_state(reviewed_rules(), saved)
        actor = next(row for row in restored.everyone if row.entity_id == self.a.entity_id)
        target = next(row for row in restored.everyone if row.entity_id == self.t.entity_id)
        restored.gm.recall(actor, reason="one Skill Swap participant recalls")
        self.assertEqual(self.parts(actor, SWORD_ID), {"sword-innate", "sword-transferable"})
        self.assertNotIn(SHIELD_ID, A.project_components(actor))
        self.assertEqual(self.parts(target, SHIELD_ID), {"shield-innate"})
        self.assertEqual(self.parts(target, SWORD_ID), {"sword-transferable"})
        restored.end_encounter(restored.everyone)
        self.assertEqual(self.parts(target, SHIELD_ID), {"shield-innate", "shield-transferable"})
        self.assertNotIn(SWORD_ID, A.project_components(target))

    def test_replacement_preserves_innate_component_but_adds_reviewed_replacement(self):
        self.select("move/심플빔", SHIELD)
        self.use("move/심플빔")
        self.assertEqual(self.parts(self.t, SHIELD_ID), {"shield-innate"})
        self.assertEqual(self.parts(self.t, "ability/단순"), {"main"})
        self.e.end_encounter(self.e.everyone)
        self.assertEqual(self.parts(self.t, SHIELD_ID), {"shield-innate", "shield-transferable"})
        self.assertNotIn("ability/단순", A.project_components(self.t))

    def test_invalid_component_definition_rejects_before_cost_frequency_or_rng(self):
        self.select("move/위액", SHIELD)
        row = self.r.ability_transition_policy["innate_components"][SHIELD_ID]
        row["components"][1]["id"] = row["components"][0]["id"]
        before = deepcopy((self.a.spec, self.a.budget, self.a.move_uses,
                           self.t.spec, self.e.rng.getstate()))
        with self.assertRaisesRegex(ValueError, "distinct ability component"):
            self.use("move/위액")
        self.assertEqual((self.a.spec, self.a.budget, self.a.move_uses,
                          self.t.spec, self.e.rng.getstate()), before)
        self.assertFalse(self.live(self.a) + self.live(self.t))

    def test_component_provenance_tamper_rejects_snapshot_and_durable_save(self):
        self.select("move/위액", SHIELD)
        self.use("move/위액")
        self.live(self.t)[0]["selection"]["component_contract"]["copied"]["innate"] = []
        with self.assertRaises(StateCodecError):
            self.e.export_state()
        with self.assertRaises(ValueError):
            self.e.gm.snapshot("tampered component provenance")


if __name__ == "__main__":
    unittest.main()
