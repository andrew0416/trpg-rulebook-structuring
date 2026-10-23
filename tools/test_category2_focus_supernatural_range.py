"""C03-058: live Focus range consumers and supernatural resistance.

The general Focus paragraph names Telepathy and Telekinetic abilities as
rank-sensitive examples.  Each native ability keeps its own published range
contract: Telepathy uses Focus x2, a Telekinetic Struggle uses Focus, while
remote objects and maneuvers remain fixed at eight metres.  Mental influence
uses the existing Focus-vs-Focus status-quo procedure.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import csv
import json
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]

from builder import build_pokemon, build_trainer
from common_checks import PendingDecision
from engine import Combatant, Engine, Rules
from grid import Grid
import perception_observe as OBSERVE
import skill_modifiers as SKILLS
import state_codec as CODEC
import telekinetic_combat as TK_COMBAT
import telekinetic_load as TK_LOAD
import telepathy as TELEPATHY
import turn as TURN
import world_entities as WORLD


CLAUSE_ID = "C03-058"
CLAUSE_SHA256 = "877ec1a2652ef28e3d123bbddfe96f9be050b50324ced00a615df14646c7bf03"
SOURCE_FILE_SHA256 = "b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23"


class FocusSupernaturalRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")

    def setUp(self):
        self.e = Engine(self.rules, seed=3058)
        self.e.grid = Grid(24, 8)
        self.abra = self.add(
            build_pokemon(
                self.rules,
                "캐이시",
                10,
                moves=[],
                abilities=[],
                pos=(0, 2),
                side="party",
            ),
            (0, 2),
            "party",
        )
        stats = dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 20)
        self.target = self.add(
            build_trainer(
                self.rules,
                "target",
                20,
                stats,
                skills={"집중": 3, "전투": 3, "육상": 3, "곡예": 3, "은신": 3},
                pos=(6, 2),
                side="wild",
            ),
            (6, 2),
            "wild",
        )
        self.influencer = self.add(
            build_trainer(
                self.rules,
                "influencer",
                20,
                stats,
                skills={"집중": 4},
                pos=(1, 5),
                side="wild",
            ),
            (1, 5),
            "wild",
        )
        self.resister = self.add(
            build_trainer(
                self.rules,
                "resister",
                20,
                stats,
                skills={"집중": 4},
                pos=(2, 5),
                side="party",
            ),
            (2, 5),
            "party",
        )

    def add(self, spec, pos, side):
        actor = Combatant(self.rules, spec)
        return self.e.gm.add_combatant(actor, pos=pos, side=side, reason="actual focus-range participant")

    def payload(self):
        return CODEC.dump_engine(self.e)

    def allow_and_observe(self):
        self.e.set_communication_consent(
            self.target,
            self.abra,
            TELEPATHY.SOURCE,
            True,
            reason="actual target willingly permits surface-thought reading",
        )
        self.e.gm.observe_surface_thought(
            self.target,
            "actual current thought",
            reason="GM observes only the current surface thought",
        )

    def mental(self, *, context=None, challenger=3, defender=3):
        if context is None:
            context = {
                "purpose": "resist an actual supernatural mental influence",
                "supernatural_mental_influence": True,
            }
        return self.e.common_action(
            self.influencer,
            mode="context",
            case="mental_influence",
            context=context,
            target=self.resister,
            defender_role="status_quo",
            challenger_options={"fixed": [challenger] * 4},
            defender_options={"fixed": [defender] * 4},
        )

    def start_abra_turn(self):
        self.e.start_round([self.abra, self.target])
        self.e.start_of_turn(self.abra)

    def maneuver_options(self):
        return {
            "defender_skill": "전투",
            "fixed_accuracy": 10,
            "challenger_options": {"fixed": [6] * SKILLS.effective_rank(self.rules, self.abra, "집중")},
            "defender_options": {"fixed": [1] * SKILLS.rank(self.rules, self.target, "전투")[2]},
        }

    def test_exact_clause_and_actual_abra_csv_builder_producer(self):
        registry = json.loads((ROOT / "data/verification/category2-class-clause-status.json").read_text(encoding="utf-8"))
        row = next(entry for entry in registry["entries"] if entry["source_clause_id"] == CLAUSE_ID)
        anchor = row["anchors"][0]
        lines = (ROOT / anchor["file"]).read_text(encoding="utf-8-sig").splitlines()
        excerpt = "\n".join(lines[anchor["start"] - 1 : anchor["end"]])
        self.assertEqual((anchor["start"], anchor["end"], anchor["sha256"]), (278, 278, CLAUSE_SHA256))
        self.assertEqual(sha256(excerpt.encode()).hexdigest(), CLAUSE_SHA256)
        self.assertEqual(sha256((ROOT / anchor["file"]).read_bytes()).hexdigest(), SOURCE_FILE_SHA256)

        with (ROOT / "input/db/pokemon.csv").open(encoding="utf-8-sig", newline="") as stream:
            source_rows = list(csv.reader(stream))
        csv_abra = source_rows[64]
        self.assertEqual(csv_abra[0], "캐이시")
        self.assertEqual(csv_abra[18:22], ["순간이동 2", "텔레파시", "염력", "약골"])
        species = self.rules.species["pokemon/캐이시"]
        self.assertEqual(species["_source"]["record_span"], [65, 65])
        self.assertEqual(species["capabilities"], csv_abra[18:22])
        self.assertEqual(self.abra.spec["capabilities"], csv_abra[18:22])
        self.assertEqual((self.abra.spec["skills"]["집중"], SKILLS.effective_rank(self.rules, self.abra, "집중")), ("3d6+2", 3))

    def test_telepathy_policy_is_focus_times_two_and_live_rank_changes_range_only(self):
        declaration = TELEPATHY.policy(self.rules)["declaration"]
        maximum = declaration["range"]["maximum"]
        self.assertEqual(
            maximum,
            {
                "kind": "skill_rank",
                "skill": "집중",
                "base": 0,
                "multiplier": 2,
                "rank_adjustment": {
                    "source": "poke_edge/장거리-판독",
                    "parameter": "range_rank_bonus",
                },
            },
        )
        self.allow_and_observe()
        self.assertEqual(OBSERVE.range_maximum(self.abra, declaration["range"]), 6)
        self.assertEqual(
            self.e.read_telepathic_thought(self.abra, self.target, request_id="focus-3-boundary")["status"],
            "delivered",
        )
        self.target.pos = (7, 2)
        outside = self.e.read_telepathic_thought(self.abra, self.target, request_id="focus-3-outside")
        self.assertEqual((outside["status"], outside["reason"]), ("failed", "out_of_range"))

        policy_before = deepcopy(TELEPATHY.policy(self.rules)["declaration"])
        self.e.gm.set_skill(self.abra, "집중", "4d6-2", reason="actual live Focus rank changes")
        self.target.pos = (8, 2)
        self.assertEqual(OBSERVE.range_maximum(self.abra, declaration["range"]), 8)
        result = self.e.read_telepathic_thought(self.abra, self.target, request_id="focus-4-boundary")
        self.assertEqual(result["status"], "delivered")
        self.assertEqual(TELEPATHY.policy(self.rules)["declaration"], policy_before)
        self.assertEqual(SKILLS.rank(self.rules, self.abra, "집중"), ("포켓몬 스킬", "4d6", 4))

    def test_telekinetic_struggle_range_tracks_live_focus(self):
        move = self.rules.move("struggle")
        choice = {"capability": "염력", "special": False}
        first = TK_COMBAT.prepare_struggle(self.e, self.abra, move, choice)
        self.assertEqual((first["_struggle_range"]["origin"], first["range"]), (3, "3, 대상 1"))
        self.e.gm.set_skill(self.abra, "집중", "5d6+2", reason="actual live Focus rank changes")
        second = TK_COMBAT.prepare_struggle(self.e, self.abra, move, choice)
        self.assertEqual((second["_struggle_range"]["origin"], second["range"]), (5, "5, 대상 1"))

    def test_telekinetic_object_and_maneuver_stay_fixed_eight_metres(self):
        self.e.gm.set_skill(self.abra, "집중", "5d6+2", reason="high Focus must not expand fixed Telekinetic consumers")
        self.start_abra_turn()
        WORLD.register_object(
            self.e,
            "eight-metre-object",
            location={"kind": "grid", "cell": (8, 2)},
            weight_kg=1,
            reason="actual remote object at the printed boundary",
        )
        out = self.e.telekinetic_lift(
            self.abra,
            ["eight-metre-object"],
            action_cost="shift",
            reason="GM declares actual Shift lifting activity",
        )
        self.assertEqual(out["weight_kg"], 1)
        self.e.release_telekinetic_load(self.abra, reason="release before maneuver")

        self.target.pos = (8, 2)
        with patch.object(TK_LOAD, "range_check", wraps=TK_LOAD.range_check) as range_check:
            result = self.e.telekinetic_maneuver(self.abra, self.target, "trip", **self.maneuver_options())
        self.assertTrue(result)
        self.assertGreaterEqual(range_check.call_count, 1)
        self.assertIn("넘어짐", self.target.conditions)

    def test_range_context_and_source_preflight_failures_are_atomic(self):
        self.e.gm.set_skill(self.abra, "집중", "5d6+2", reason="high Focus must not expand fixed eight metres")
        self.start_abra_turn()
        WORLD.register_object(
            self.e,
            "nine-metre-object",
            location={"kind": "grid", "cell": (9, 2)},
            weight_kg=1,
            reason="actual remote object beyond the printed boundary",
        )
        before = self.payload()
        with self.assertRaisesRegex(ValueError, "eight"):
            self.e.telekinetic_lift(
                self.abra,
                ["nine-metre-object"],
                action_cost="shift",
                reason="GM declares actual Shift lifting activity",
            )
        self.assertEqual(self.payload(), before)

        self.target.pos = (9, 2)
        before = self.payload()
        with self.assertRaises(ValueError):
            self.e.telekinetic_maneuver(self.abra, self.target, "trip", **self.maneuver_options())
        self.assertEqual(self.payload(), before)

        before = self.payload()
        rng = self.e.rng.getstate()
        pending = self.mental(context={"purpose": "influence is not established"})
        self.assertIsInstance(pending, PendingDecision)
        self.assertEqual((self.payload(), self.e.rng.getstate()), (before, rng))

        self.allow_and_observe()
        before = self.payload()
        rng = self.e.rng.getstate()
        old = self.rules.selection.excluded.get(TELEPATHY.SOURCE)
        self.rules.selection.excluded[TELEPATHY.SOURCE] = "test source preflight exclusion"
        try:
            with self.assertRaises(ValueError):
                self.e.read_telepathic_thought(self.abra, self.target, request_id="excluded-source")
        finally:
            if old is None:
                self.rules.selection.excluded.pop(TELEPATHY.SOURCE, None)
            else:
                self.rules.selection.excluded[TELEPATHY.SOURCE] = old
        self.assertEqual((self.payload(), self.e.rng.getstate()), (before, rng))

    def test_mental_influence_is_focus_vs_focus_and_tie_preserves_status_quo(self):
        target_before = deepcopy(self.resister.spec)
        tied = self.mental()
        self.assertFalse(tied.check.passed)
        self.assertEqual((tied.check.total, tied.check.dc), (12, 12))
        self.assertEqual((tied.basis["skill"], tied.basis["defender_skill"], tied.basis["defender_role"]), ("집중", "집중", "status_quo"))
        self.assertEqual(self.resister.spec, target_before)

        target_before = deepcopy(self.resister.spec)
        won = self.mental(challenger=4, defender=3)
        self.assertTrue(won.check.passed)
        self.assertIsInstance(won, PendingDecision)
        self.assertEqual(self.resister.spec, target_before)

    def test_gm_and_json_restore_keep_live_focus_capabilities_and_ranges(self):
        self.allow_and_observe()
        self.e.gm.set_skill(self.abra, "집중", "5d6+2", reason="actual restored live Focus rank")
        self.target.pos = (10, 2)
        first = self.e.read_telepathic_thought(self.abra, self.target, request_id="before-restores")
        self.assertEqual(first["status"], "delivered")
        self.e.gm.snapshot("focus-ranges")
        payload = json.loads(json.dumps(self.payload(), ensure_ascii=False))

        self.e.gm.set_skill(self.abra, "집중", "3d6+2", reason="temporary mutation after snapshot")
        self.target.pos = (20, 2)
        self.e.gm.restore("focus-ranges", reason="restore exact focus range state")
        self.assertEqual(SKILLS.effective_rank(self.rules, self.abra, "집중"), 5)
        self.assertEqual(self.target.pos, (10, 2))
        self.assertEqual(
            TK_COMBAT.prepare_struggle(
                self.e,
                self.abra,
                self.rules.move("struggle"),
                {"capability": "염력", "special": False},
            )["_struggle_range"]["origin"],
            5,
        )
        self.assertEqual(
            self.e.read_telepathic_thought(self.abra, self.target, request_id="after-gm-restore")["status"],
            "delivered",
        )

        loaded = CODEC.load_engine(self.rules, payload)
        actors = {actor.entity_id: actor for actor in loaded.everyone}
        abra = actors[self.abra.entity_id]
        target = actors[self.target.entity_id]
        self.assertEqual((SKILLS.effective_rank(self.rules, abra, "집중"), target.pos), (5, (10, 2)))
        self.assertEqual(
            TK_COMBAT.prepare_struggle(
                loaded,
                abra,
                self.rules.move("struggle"),
                {"capability": "염력", "special": False},
            )["_struggle_range"]["origin"],
            5,
        )
        self.assertEqual(
            loaded.read_telepathic_thought(abra, target, request_id="after-json-restore")["status"],
            "delivered",
        )


if __name__ == "__main__":
    unittest.main()
