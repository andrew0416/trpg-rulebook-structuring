"""C2CSV-MOVE-R0542/R0703: reversible, source-owned stat exchanges."""
from copy import deepcopy
from pathlib import Path
import csv
import json
import sys
import unittest


STAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
SOURCE_ROOT = STAGE_ROOT if (STAGE_ROOT / "input/db/moves.csv").exists() else DEFAULT_SOURCE_ROOT
sys.path[:0] = [str(STAGE_ROOT / "engine"), str(SOURCE_ROOT / "engine")]

from engine import Combatant, Engine, Rules
import combat_state_lifecycle as COMBAT_STATE
import combat_timing as TIMING
import effect_lifetimes as LIFETIMES
import effects as FX
import life as LIFE
import state_codec as CODEC
import stat_exchange_state as EXCHANGE


CLAUSES = ("C2CSV-MOVE-R0542", "C2CSV-MOVE-R0703")
BASELINE = {"atk": 11, "def": 22, "spa": 33, "spd": 44, "spe": 55}


class StatExchangeLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(SOURCE_ROOT), ruleset="core")
        cls.sources = {}
        for source in cls.rules.moves:
            try:
                mechanics, _ = cls.rules.move_mech(source)
            except Exception:
                continue
            for effect in mechanics.get("effects_exec", []):
                if effect.get("type") == "swap_stats" and effect.get("until") in EXCHANGE.BOUNDARIES:
                    cls.sources[effect["until"]] = (source, deepcopy(effect))
        if set(cls.sources) != set(EXCHANGE.BOUNDARIES):
            raise AssertionError("the two selected source Move declarations must remain exact")

    def setUp(self):
        self.engine = Engine(self.rules, seed=542703)
        spec = deepcopy(self.rules.creatures["pokemon/archie"])
        self.actor = Combatant(self.rules, spec)
        self.actor.stats.update(BASELINE)
        self.engine.everyone = [self.actor]
        self.engine.gm.everyone = [self.actor]
        self.engine._encounter_actors = [self.actor]
        self.engine.encounter_active = True

    def dispatch(self, until):
        source, effect = self.sources[until]
        FX.preflight_effects(self.engine, self.actor, self.actor, [effect], source)
        result = FX.run_effects(
            self.engine,
            self.actor,
            self.actor,
            [effect],
            {"hit": True, "attacker": self.actor, "target": self.actor},
            source,
        )
        self.assertEqual(tuple(result), (1, 0), result.outcomes)
        self.assertEqual(result.outcomes[0].status, "completed")
        return result.outcomes[0]

    def assert_baseline(self, actor=None):
        actor = self.actor if actor is None else actor
        self.assertEqual({stat: actor.stats[stat] for stat in EXCHANGE.STATS}, BASELINE)

    def test_saved_clause_rows_and_selected_runtime_declarations_are_exact(self):
        plan = json.loads((SOURCE_ROOT / "data/verification/category2-edge-work-plan.json").read_text(encoding="utf-8"))
        text = json.dumps(plan["latest_reassessment"], ensure_ascii=False)
        for clause in CLAUSES:
            self.assertIn(clause, text)
        self.assertIn("출처가 있는 비가산 스탯 교환과 복원 경계", text)

        with (SOURCE_ROOT / "input/db/moves.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[541][0], "파워시프트")
        self.assertIn("장면의 나머지", rows[541][7])
        self.assertEqual(rows[702][0], "파워트릭")
        self.assertIn("인카운터의 나머지", rows[702][7])
        scene = self.sources["scene_end or switch or faint"][1]
        encounter = self.sources["encounter_end or faint or switch"][1]
        self.assertEqual(scene["swap_stats"], [["atk", "def"], ["spa", "spd"]])
        self.assertEqual(encounter["swap_stats"], [["atk", "def"]])

    def test_overlapping_sources_replay_remaining_exchange_at_each_boundary(self):
        self.dispatch("scene_end or switch or faint")
        self.assertEqual(
            {stat: self.actor.stats[stat] for stat in EXCHANGE.STATS},
            {"atk": 22, "def": 11, "spa": 44, "spd": 33, "spe": 55},
        )
        self.dispatch("encounter_end or faint or switch")
        self.assertEqual(
            {stat: self.actor.stats[stat] for stat in EXCHANGE.STATS},
            {"atk": 11, "def": 22, "spa": 44, "spd": 33, "spe": 55},
        )
        self.assertEqual(len(TIMING.records(self.actor)), 2)

        LIFETIMES.end_encounter(self.engine, [self.actor])
        self.assertEqual(
            {stat: self.actor.stats[stat] for stat in EXCHANGE.STATS},
            {"atk": 22, "def": 11, "spa": 44, "spd": 33, "spe": 55},
        )
        self.assertEqual(len(TIMING.records(self.actor)), 1)
        TIMING.end_scene(self.engine)
        self.assert_baseline()
        self.assertFalse(TIMING.records(self.actor))
        self.assertEqual(
            [entry["event"]["kind"] for entry in self.actor.custom_conditions[EXCHANGE.HISTORY]],
            ["encounter_end", "scene_end"],
        )
        EXCHANGE.validate_world(self.engine, {self.actor.entity_id: self.actor})

    def test_switch_and_faint_each_restore_all_live_sources(self):
        self.dispatch("scene_end or switch or faint")
        self.dispatch("encounter_end or faint or switch")
        COMBAT_STATE.recall(self.engine, self.actor)
        self.assert_baseline()
        self.assertFalse(TIMING.records(self.actor))
        self.assertFalse(self.actor.on_field)
        self.assertEqual(
            [entry["ending"] for entry in self.actor.custom_conditions[EXCHANGE.HISTORY]],
            ["switch", "switch"],
        )

        other_engine = Engine(self.rules, seed=703542)
        other_spec = deepcopy(self.rules.creatures["pokemon/archie"])
        other = Combatant(self.rules, other_spec)
        other.stats.update(BASELINE)
        other_engine.everyone = other_engine.gm.everyone = [other]
        other_engine._encounter_actors = [other]
        other_engine.encounter_active = True
        self.engine, self.actor = other_engine, other
        self.dispatch("scene_end or switch or faint")
        self.dispatch("encounter_end or faint or switch")
        self.assertTrue(LIFE.faint(self.engine, self.actor))
        self.assert_baseline()
        self.assertFalse(TIMING.records(self.actor))
        self.assertIn("기절", self.actor.conditions)
        self.assertEqual(
            [entry["ending"] for entry in self.actor.custom_conditions[EXCHANGE.HISTORY]],
            ["faint", "faint"],
        )

    def test_source_mismatch_and_tampered_projection_fail_without_state_mutation(self):
        source, effect = self.sources["scene_end or switch or faint"]
        false_effect = deepcopy(effect)
        false_effect["swap_stats"] = [["atk", "spa"]]
        before = deepcopy(self.actor.stats), deepcopy(self.actor.custom_conditions)
        result = FX.run_effects(
            self.engine,
            self.actor,
            self.actor,
            [false_effect],
            {"hit": True, "attacker": self.actor, "target": self.actor},
            source,
        )
        self.assertEqual(tuple(result), (0, 1))
        self.assertEqual(result.outcomes[0].status, "unsupported_execution")
        self.assertEqual(result.outcomes[0].reason.field, "lifetime")
        self.assertEqual((self.actor.stats, self.actor.custom_conditions), before)

        self.dispatch("scene_end or switch or faint")
        self.dispatch("encounter_end or faint or switch")
        live = TIMING.records(self.actor)
        live[1]["stat_exchange"]["boundaries"][0] = "tampered"
        before_stats = deepcopy(self.actor.stats)
        before_ids = tuple(id(record) for record in live)
        with self.assertRaisesRegex(ValueError, "boundary"):
            COMBAT_STATE.recall(self.engine, self.actor)
        self.assertEqual(self.actor.stats, before_stats)
        self.assertEqual(tuple(id(record) for record in TIMING.records(self.actor)), before_ids)
        self.assertFalse(self.actor.custom_conditions.get(EXCHANGE.HISTORY))
        live[1]["stat_exchange"]["boundaries"] = list(EXCHANGE.BOUNDARIES[live[1]["timing_text"]])

        self.actor.stats["atk"] += 1
        before = (
            deepcopy(self.actor.custom_conditions[EXCHANGE.KEY]),
            tuple(id(record) for record in TIMING.records(self.actor)),
            len(self.actor.custom_conditions.get(EXCHANGE.HISTORY, [])),
            self.actor.on_field,
            set(self.actor.conditions),
        )
        with self.assertRaisesRegex(ValueError, "diverged"):
            COMBAT_STATE.recall(self.engine, self.actor)
        after = (
            self.actor.custom_conditions[EXCHANGE.KEY],
            tuple(id(record) for record in TIMING.records(self.actor)),
            len(self.actor.custom_conditions.get(EXCHANGE.HISTORY, [])),
            self.actor.on_field,
            self.actor.conditions,
        )
        self.assertEqual(after, before)

    def test_permanent_edit_is_blocked_and_codec_preserves_live_receipt_aliases(self):
        self.dispatch("scene_end or switch or faint")
        with self.assertRaisesRegex(ValueError, "source-specific"):
            self.engine.gm.set_stat(self.actor, "atk", value=99, reason="attempt during exchange")

        payload = json.loads(json.dumps(CODEC.dump_engine(self.engine), ensure_ascii=False))
        loaded = CODEC.load_engine(self.rules, payload)
        restored = {actor.entity_id: actor for actor in loaded.everyone}[self.actor.entity_id]
        self.assertEqual(
            {stat: restored.stats[stat] for stat in EXCHANGE.STATS},
            {"atk": 22, "def": 11, "spa": 44, "spd": 33, "spe": 55},
        )
        EXCHANGE.validate_world(loaded, {restored.entity_id: restored})
        TIMING.end_scene(loaded)
        self.assert_baseline(restored)
        EXCHANGE.validate_world(loaded, {restored.entity_id: restored})


if __name__ == "__main__":
    unittest.main()
