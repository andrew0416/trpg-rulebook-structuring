"""Direct producer/consumer checks for Stellar Blast and three Tera Blast rows."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from builder import build_pokemon
from engine import Combatant, Engine, Rules
from grid import Grid
import effects as FX
import effects_ext as EXT
import homebrew_state as HOME
import stellar_tera_blast as STELLAR


class FixedRng:
    def __init__(self, faces):
        self.faces = list(faces)

    def randint(self, low, high):
        value = self.faces.pop(0)
        if not low <= value <= high:
            raise AssertionError((low, high, value))
        return value

    def getstate(self):
        return tuple(self.faces)

    def setstate(self, state):
        self.faces = list(state)


class StellarTeraBlastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="homebrew")

    def setUp(self):
        self.engine = Engine(self.rules, seed=610)
        self.owner = Combatant(self.rules, build_pokemon(
            self.rules, "이상해씨", 20, name="owner", side="party", pos=(2, 2),
            abilities=["스텔라버스트"],
            moves=["move/몸통박치기", "move/테라버스트", "move/테라버스트-물리", "move/테라버스트-특수"],
        ))
        self.ally = Combatant(self.rules, build_pokemon(
            self.rules, "꼬렛", 20, name="ally", side="party", pos=(4, 2),
            moves=["move/불꽃세례"], abilities=[],
        ))
        self.far = Combatant(self.rules, build_pokemon(
            self.rules, "꼬렛", 20, name="far", side="party", pos=(8, 8),
            moves=["move/불꽃세례"], abilities=[],
        ))
        self.foe = Combatant(self.rules, build_pokemon(
            self.rules, "파이리", 20, name="foe", side="wild", pos=(3, 2),
            moves=["move/몸통박치기"], abilities=[],
        ))
        self.engine.grid = Grid(12, 12)
        self.engine.everyone = self.engine.gm.everyone = [self.owner, self.ally, self.far, self.foe]
        self.engine.register_abilities(self.owner)
        self.engine.start_round(self.engine.everyone)
        self.engine.start_of_turn(self.owner, initiative_count=20)

    def opportunity(self):
        self.engine.rng = FixedRng([20])
        self.engine.use_move(self.owner, self.foe, "move/몸통박치기", set_damage=True)
        rows = self.owner.spec[STELLAR.STATE]["opportunities"]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def radiate(self, value="불꽃"):
        row = self.opportunity()
        return self.engine.gm.activate_stellar_blast(
            self.owner, row["id"], value, reason="chosen actual type from completed enemy hit"
        )

    def test_policy_exact_four_rows_and_source_hashes(self):
        policy = json.loads((ROOT / STELLAR.POLICY).read_text(encoding="utf-8"))
        self.assertEqual(policy["ability"]["clause_id"], "C2CSV-ABILITY-R0663")
        self.assertEqual(
            [row["clause_id"] for row in policy["moves"]],
            ["C2CSV-MOVE-R0610", "C2CSV-MOVE-R0911", "C2CSV-MOVE-R0912"],
        )
        self.assertEqual(len({row["source_row_sha256"] for row in policy["moves"]}), 3)
        self.assertEqual(set(STELLAR.rows(self.rules)), {
            "move/테라버스트", "move/테라버스트-물리", "move/테라버스트-특수",
        })

    def test_completed_enemy_hit_produces_snapshot_and_miss_or_ally_does_not(self):
        self.engine.rng = FixedRng([1])
        self.engine.use_move(self.owner, self.foe, "move/몸통박치기", set_damage=True)
        self.assertNotIn(STELLAR.STATE, self.owner.spec)
        self.setUp()
        self.engine.rng = FixedRng([20])
        self.engine.use_move(self.owner, self.ally, "move/몸통박치기", set_damage=True)
        self.assertNotIn(STELLAR.STATE, self.owner.spec)
        self.setUp()
        self.engine.rng = FixedRng([20])
        self.engine.use_move(self.owner, self.foe, "move/몸통박치기", set_damage=True)
        row = self.owner.spec[STELLAR.STATE]["opportunities"][0]
        self.assertEqual((row["target_id"], row["types"], row["consumed"]), (self.foe.entity_id, ["불꽃"], False))
        self.assertTrue(row["completion_id"].startswith("move-complete:"))

    def test_swift_activation_consumes_one_actual_opportunity_and_is_atomic(self):
        row = self.opportunity()
        before = deepcopy((self.owner.spec, self.owner.budget))
        with self.assertRaises(ValueError):
            self.engine.gm.activate_stellar_blast(self.owner, row["id"], "물", reason="not target type")
        self.assertEqual((self.owner.spec, self.owner.budget), before)
        receipt = self.engine.gm.activate_stellar_blast(self.owner, row["id"], "불꽃", reason="actual target type")
        self.assertEqual(receipt["action"], "swift")
        self.assertEqual(self.owner.budget["swift"], 0)
        self.assertEqual(STELLAR.active_radiation(self.engine, self.owner)["radiated_type"], "불꽃")
        after = deepcopy((self.owner.spec, self.owner.budget))
        with self.assertRaises(ValueError):
            self.engine.gm.activate_stellar_blast(self.owner, row["id"], "불꽃", reason="duplicate")
        self.assertEqual((self.owner.spec, self.owner.budget), after)

    def test_radiation_projects_exact_type_without_mutating_stab_or_types(self):
        original_types = list(self.owner.types)
        original_stab = HOME.stab_types(self.owner)
        self.radiate()
        for move_id in STELLAR.rows(self.rules):
            move = self.rules.move(move_id)
            mm, _ = self.rules.move_mech(move_id)
            self.assertEqual(EXT.effective_type(self.engine, self.owner, self.foe, move, mm, consume=False), "불꽃")
        self.assertEqual(self.owner.types, original_types)
        self.assertEqual(HOME.stab_types(self.owner), original_stab)

    def test_main_and_variant_stab_contracts_remain_distinct(self):
        self.radiate()
        main = self.rules.move("move/테라버스트")
        physical = self.rules.move("move/테라버스트-물리")
        special = self.rules.move("move/테라버스트-특수")
        self.assertTrue(EXT.grants_stab(self.engine, self.owner, main))
        self.assertFalse(EXT.grants_stab(self.engine, self.owner, physical))
        self.assertFalse(EXT.grants_stab(self.engine, self.owner, special))

    def test_burst_two_allies_gain_one_matching_type_bonus_and_far_or_other_type_do_not(self):
        self.radiate()
        fire = self.rules.move("move/불꽃세례")
        grass = self.rules.move("move/덩굴채찍")
        for actor, expected in ((self.owner, 10), (self.ally, 10), (self.far, 0)):
            ctx = {"actual_damage_type": "불꽃"}
            self.assertEqual(FX.passive_damage_mods(self.engine, actor, self.foe, fire, ctx)[1], expected)
        self.assertEqual(FX.passive_damage_mods(
            self.engine, self.ally, self.foe, grass, {"actual_damage_type": "풀"}
        )[1], 0)

    def test_ordinary_tera_type_projects_all_three_and_main_forces_stab(self):
        HOME.observe_type(self.engine, self.owner, "물", reason="established ordinary Tera type")
        HOME.observe_active(self.engine, self.owner, True, reason="actual active Terastal state")
        for move_id, force_stab in (
            ("move/테라버스트", True),
            ("move/테라버스트-물리", False),
            ("move/테라버스트-특수", False),
        ):
            move = self.rules.move(move_id)
            mm, _ = self.rules.move_mech(move_id)
            self.assertEqual(EXT.effective_type(self.engine, self.owner, self.foe, move, mm, consume=False), "물")
            self.assertEqual(EXT.grants_stab(self.engine, self.owner, move), force_stab)

    def test_stellar_effectiveness_uses_actual_form_evidence_and_caps_at_double(self):
        self.radiate()
        move = self.rules.move("move/테라버스트-특수")
        mm, _ = self.rules.move_mech(move["id"])
        self.foe.form = "actual-battle-form"
        ctx = {}
        self.assertEqual(EXT.effectiveness_hook(self.engine, self.owner, self.foe, move, mm, 1.5, ctx), 2.0)
        self.assertEqual(ctx["stellar_tera_blast"]["cap"], 2.0)
        ctx = {}
        self.assertEqual(EXT.effectiveness_hook(self.engine, self.owner, self.foe, move, mm, 2.0, ctx), 2.0)
        self.foe.form = None
        self.assertEqual(EXT.effectiveness_hook(self.engine, self.owner, self.foe, move, mm, 1.0, {}), 1.0)

    def test_encounter_lifetime_disables_aura_and_projection_without_deleting_audit(self):
        self.radiate()
        saved = deepcopy(self.owner.spec[STELLAR.STATE])
        self.engine.end_encounter(self.engine.everyone)
        self.assertIsNone(STELLAR.active_radiation(self.engine, self.owner))
        self.assertEqual(self.owner.spec[STELLAR.STATE], saved)
        self.engine.begin_encounter(self.engine.everyone)
        self.assertIsNone(STELLAR.active_radiation(self.engine, self.owner))

    def test_state_roundtrip_validation_and_tamper_rejection(self):
        self.radiate()
        self.engine.gm.snapshot("stellar")
        self.owner.spec[STELLAR.STATE]["active"]["radiated_type"] = "물"
        with self.assertRaises(ValueError):
            STELLAR.validate_actor(self.engine, self.owner)
        self.engine.gm.restore("stellar")
        self.assertTrue(STELLAR.validate_world(self.engine))
        self.assertEqual(STELLAR.active_radiation(self.engine, self.owner)["radiated_type"], "불꽃")


if __name__ == "__main__":
    unittest.main()
