"""C2CSV-MOVE-R0076/R0407/R0750 exact catalog Move state contracts."""
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import json
import sys
import unittest


STAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(STAGE_ROOT / "engine"), str(SOURCE_ROOT / "engine")]

from engine import Combatant, Engine, Rules
import catalog_move_states as CATALOG
import combat_timing as TIMING
import effect_lifetimes as LIFETIMES
import effects as FX
import effects_ext as EXT
import movement_actions as MOVEMENT
import state_codec as CODEC


CLAUSES = {
    "C2CSV-MOVE-R0076": (76, "지옥찌르기", "9327dff1044df1bd3fb18b8fd26e0f65f212e3297b89dd52741fbfc075ce28b3"),
    "C2CSV-MOVE-R0407": (407, "사우전드애로", "31b956fb99a0d81c0ad07f362517c2909140b5786089956c664cfa3d96ae306e"),
    "C2CSV-MOVE-R0750": (750, "떨어뜨리기", "f3bf1300ece81bf9118f9313cbfa2b894613ea0d869ffe450cbb7f5956da6389"),
}


class CatalogMoveStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(SOURCE_ROOT), ruleset="core")
        cls.by_eng = {move.get("eng"): source for source, move in cls.rules.moves.items()}
        cls.throat = cls.by_eng["Throat Chop"]
        cls.arrows = cls.by_eng["Thousand Arrows"]
        cls.smack = cls.by_eng["Smack Down"]
        cls.voice = cls.by_eng["Hyper Voice"]
        cls.tackle = next(source for source, move in cls.rules.moves.items()
                          if move.get("eng") == "Tackle [SM]")
        if (cls.throat, cls.arrows, cls.smack) != (
                "move/지옥찌르기", "move/사우전드애로", "move/떨어뜨리기"):
            raise AssertionError("selected catalog Move identities changed")

    def setUp(self):
        self.engine = Engine(self.rules, seed=76407750)
        base = deepcopy(self.rules.creatures["pokemon/archie"])
        self.actor = Combatant(self.rules, dict(base, id="pokemon/catalog-user",
            name="catalog user", moves=[self.throat, self.arrows, self.smack]))
        target_spec = dict(deepcopy(base), id="pokemon/catalog-target", name="catalog target",
                           moves=[self.voice, self.tackle])
        target_spec["movement"] = {"land": 4, "sky": 6, "levitate": 4}
        target_spec["movement_basis"] = "current"
        self.target = Combatant(self.rules, target_spec)
        self.engine.everyone = self.engine.gm.everyone = [self.actor, self.target]
        self.engine._encounter_actors = [self.actor, self.target]
        self.engine.encounter_active = True

    def effect(self, source, kind):
        mechanics, _ = self.rules.move_mech(source)
        matches = [deepcopy(effect) for effect in mechanics["effects_exec"]
                   if effect.get("type") == kind]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def dispatch(self, source, effects):
        FX.preflight_effects(self.engine, self.actor, self.target, effects, source)
        result = FX.run_effects(
            self.engine, self.actor, self.target, effects,
            {"hit": True, "attacker": self.actor, "target": self.target,
             "move": self.rules.move(source), "engine": self.engine},
            source,
        )
        self.assertEqual(tuple(result)[1], 0, result.outcomes)
        return result

    def target_turn(self):
        TIMING.begin_turn(self.engine, self.target)
        TIMING.end_turn(self.engine, self.target)

    def test_exact_source_rows_hashes_and_runtime_declarations(self):
        with (SOURCE_ROOT / "input/db/moves.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        for clause, (record, name, digest) in CLAUSES.items():
            row = rows[record - 1]
            self.assertEqual(row[0], name, clause)
            actual = hashlib.sha256(json.dumps(
                row, ensure_ascii=False, separators=(",", ":")
            ).encode()).hexdigest()
            self.assertEqual(actual, digest, clause)
        self.assertEqual(self.effect(self.throat, "move_lock"), CATALOG.MOVE_LOCKS[self.throat]["effect"])
        self.assertEqual(self.effect(self.arrows, "grounding"), CATALOG.GROUNDING[self.arrows]["effect"])
        self.assertEqual(self.effect(self.smack, "grounding"), CATALOG.GROUNDING[self.smack]["effect"])

    def test_throat_chop_blocks_only_sound_for_two_actual_target_turns(self):
        outcome = self.dispatch(self.throat, [self.effect(self.throat, "move_lock")])
        self.assertEqual(tuple(outcome), (1, 0))
        self.assertEqual(CATALOG.move_locked(self.engine, self.target, self.rules.move(self.voice)), "소리")
        self.assertIsNone(CATALOG.move_locked(self.engine, self.target, self.rules.move(self.tackle)))
        voice_mm, _ = self.rules.move_mech(self.voice)
        tackle_mm, _ = self.rules.move_mech(self.tackle)
        self.assertFalse(EXT.pre_use(self.engine, self.target, self.actor,
                                     self.rules.move(self.voice), voice_mm))
        self.assertTrue(EXT.pre_use(self.engine, self.target, self.actor,
                                    self.rules.move(self.tackle), tackle_mm))
        self.target_turn()
        self.assertTrue(CATALOG.locked_keywords(self.target))
        self.target_turn()
        self.assertFalse(CATALOG.locked_keywords(self.target))
        self.assertTrue(EXT.pre_use(self.engine, self.target, self.actor,
                                    self.rules.move(self.voice), voice_mm))

    def assert_grounded_for_three_turns(self, source):
        self.target.spec["_movement_altitude"] = 3
        self.target.airborne = True
        outcome = self.dispatch(source, [self.effect(source, "grounding")])
        self.assertEqual(tuple(outcome), (1, 0))
        self.assertTrue(CATALOG.grounded(self.target))
        self.assertEqual((self.target.spec["_movement_altitude"], self.target.airborne), (0, False))
        capabilities = MOVEMENT.capabilities(self.engine, self.target, environment=False)
        self.assertEqual((capabilities["sky"], capabilities["levitate"]), (0, 0))
        self.target.types = ["비행"]
        ground = {"id": "move/fixture-ground", "name": "fixture ground", "type": "땅",
                  "class": "물리", "range": "근접, 대상 1"}
        base, _ = self.engine.type_multiplier("땅", self.target)
        self.assertEqual(base, 0.0)
        self.assertEqual(EXT.effectiveness_hook(
            self.engine, self.actor, self.target, ground, {"effects_exec": []}, base,
            {"attacker": self.actor, "target": self.target}), 1.0)
        for remaining in (2, 1):
            self.target_turn()
            self.assertTrue(CATALOG.grounded(self.target))
            self.assertEqual(len([r for r in TIMING.records(self.target)
                                  if "catalog_grounding" in r]), 1)
        self.target_turn()
        self.assertFalse(CATALOG.grounded(self.target))
        restored = MOVEMENT.capabilities(self.engine, self.target, environment=False)
        self.assertEqual((restored["sky"], restored["levitate"]), (6, 4))

    def test_smack_down_uses_shared_grounding_lifetime_and_consumers(self):
        self.assert_grounded_for_three_turns(self.smack)

    def test_thousand_arrows_replaces_flying_matchup_ignores_levitate_and_grounds(self):
        self.target.types = ["비행"]
        self.target.abilities = ["부유"]
        move = self.rules.move(self.arrows)
        mechanics, _ = self.rules.move_mech(self.arrows)
        base, _ = self.engine.type_multiplier("땅", self.target)
        self.assertEqual(base, 0.0)
        ordinary = dict(move, id="move/ordinary-ground")
        self.assertEqual(EXT.effectiveness_hook(
            self.engine, self.actor, self.target, ordinary, {"effects_exec": []}, base,
            {"attacker": self.actor, "target": self.target}), 0.0)
        expected, _ = self.engine.type_multiplier("얼음", self.target)
        self.assertEqual(EXT.effectiveness_hook(
            self.engine, self.actor, self.target, move, mechanics, base,
            {"attacker": self.actor, "target": self.target}), expected)
        self.target.spec["_movement_altitude"] = 4
        self.target.airborne = True
        result = self.dispatch(self.arrows, deepcopy(mechanics["effects_exec"]))
        self.assertEqual(tuple(result), (1, 0))
        self.assertFalse(any(effect.get("type") in {"ignore_ability", "type_effectiveness_override"}
                             for effect in self.actor.registry))
        self.assertTrue(CATALOG.grounded(self.target))
        self.assertEqual(EXT.effectiveness_hook(
            self.engine, self.actor, self.target, ordinary, {"effects_exec": []}, base,
            {"attacker": self.actor, "target": self.target}), 1.0)

    def test_codec_preserves_both_states_and_tamper_is_rejected(self):
        self.dispatch(self.throat, [self.effect(self.throat, "move_lock")])
        self.dispatch(self.smack, [self.effect(self.smack, "grounding")])
        payload = json.loads(json.dumps(CODEC.dump_engine(self.engine), ensure_ascii=False))
        loaded = CODEC.load_engine(self.rules, payload)
        actors = {actor.entity_id: actor for actor in loaded.everyone}
        restored = actors[self.target.entity_id]
        CATALOG.validate_world(loaded, actors)
        self.assertEqual(CATALOG.locked_keywords(restored), {"소리"})
        self.assertTrue(CATALOG.grounded(restored))
        self.assertEqual((MOVEMENT.capabilities(loaded, restored, environment=False)["sky"],
                          MOVEMENT.capabilities(loaded, restored, environment=False)["levitate"]), (0, 0))
        lock = next(record for record in TIMING.records(restored) if "catalog_move_lock" in record)
        lock["turn_deadline"] += 1
        with self.assertRaisesRegex(ValueError, "boundary"):
            CATALOG.validate_world(loaded, actors)


if __name__ == "__main__":
    unittest.main()
