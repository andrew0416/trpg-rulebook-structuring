"""Category2 projection for Learn From Your Mistakes (ch04:1308-1312).

The runtime already exists in the reviewed Category3 contest feature path.  These
tests certify that the complete printed feature is consumed through that native
path, including the durable observed-decision boundary and both save formats.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from engine import Combatant, Engine, Rules
import action_points as AP
import common_checks as C
import contest_features as FEATURES
import downtime as DOWNTIME
import observed_resolution as OBSERVED
from state_codec import dump_engine, load_engine


CLAUSE_ID = "input/ch04-trainer-classes.md:1308-1312"
SOURCE_SHA256 = "061be31777d79e16430b69c0b4858bce8af0d1e198ea62d87ba51d9b621cfba2"


class Sequence:
    def __init__(self, faces):
        self.faces = list(faces)

    def randint(self, low, high):
        return self.faces.pop(0)


class LearnFromMistakesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT)

    def setUp(self):
        self.engine = Engine(self.rules, seed=1308)
        ranked, skill, _ = FEATURES.RANKED["슬기로움"]
        common = {
            "level": 25,
            "stats": {"hp": 10, "atk": 10, "def": 10, "spa": 10, "spd": 10, "spe": 10},
        }
        self.trainer = Combatant(
            self.rules,
            dict(
                common,
                id="trainer/learn-from-mistakes",
                name="T",
                kind="trainer",
                skills={skill: "초보"},
                classes=["class/코디네이터", FEATURES.STYLE],
                edges=["edge/우아함"],
                feats=[ranked, FEATURES.MISTAKES],
                feat_ranks={ranked: 1},
                feature_choices={FEATURES.STYLE: ["슬기로움"]},
            ),
        )
        self.pokemon = Combatant(
            self.rules,
            dict(
                common,
                id="pokemon/learn-from-mistakes",
                name="P",
                kind="pokemon",
                trainer_id=self.trainer.spec["id"],
                skills={"육상": "초보"},
                poffins=["슬기로움"] * 3,
            ),
        )
        self.engine.everyone = self.engine.gm.everyone = [self.trainer, self.pokemon]

    def use(self, **overrides):
        options = {
            "fixed": [1, 1, 1],
            "reroll_faces": [2, 2, 2],
            "decision": lambda check: True,
        }
        options.update(overrides)
        dc = options.pop("dc", 12)
        return self.engine.contest_skill_feature(
            self.trainer,
            self.pokemon,
            FEATURES.MISTAKES,
            "육상",
            dc,
            **options,
        )

    def used(self, trainer=None):
        trainer = self.trainer if trainer is None else trainer
        return (
            trainer.spec.get("frequency_state", {})
            .get("activations", {})
            .get(FEATURES.MISTAKES, {})
            .get("used", 0)
        )

    def stable_state(self):
        return {
            "trainer": deepcopy(self.trainer.spec),
            "pokemon": deepcopy(self.pokemon.spec),
            "trainer_actions": list(getattr(self.trainer, "_action_history", [])),
            "pokemon_actions": list(getattr(self.pokemon, "_action_history", [])),
            "ap_roll_keys": tuple(self.engine._ap_rolls),
            "logs": list(self.engine.log_lines),
            "rng": self.engine.rng.getstate(),
        }

    def pending(self, *, roll_id="mistake-pending"):
        seen = []
        with self.assertRaises(ValueError):
            self.use(
                dc=99,
                roll_id=roll_id,
                decision=lambda check: seen.append(check) or "invalid",
            )
        record = self.engine._ap_rolls[roll_id][OBSERVED.KEY]
        self.assertEqual(record["state"], "pending")
        self.assertEqual(len(seen), 1)
        return record, seen[0]

    def test_exact_source_and_reviewed_category3_contract_are_bound(self):
        lines = (ROOT / "input/ch04-trainer-classes.md").read_text(
            encoding="utf-8-sig"
        ).splitlines()
        excerpt = "\n".join(lines[1307:1312])
        self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(), SOURCE_SHA256)
        self.assertIn("하루x3 - 자유 행동", excerpt)
        self.assertIn("포켓몬이 스킬 체크에 실패", excerpt)

        rows = json.loads(
            (ROOT / "data/verification/category3-register.json").read_text(encoding="utf-8")
        )["entries"]
        evidence = next(row for row in rows if row["id"] == "C3-EX-064")
        self.assertTrue(evidence["review"]["full_scope_verified"])
        self.assertEqual(evidence["review"]["remaining_obligations"], [])
        self.assertIn("engine/observed_resolution.py:begin", evidence["implementation"]["symbols"])

    def test_actual_failed_check_opens_choice_and_reroll_consumes_once(self):
        seen = []
        result = self.use(decision=lambda check: seen.append(check) or True)
        self.assertEqual(seen, [C.CheckResult(3, 12, -9, False)])
        self.assertEqual(result["first_roll"].faces, (1, 1, 1))
        self.assertEqual(result["roll"].faces, (2, 2, 2))
        self.assertEqual(result["poffin_bonus"], 5)
        self.assertEqual(result["roll"].total, 11)
        self.assertTrue(result["rerolled"])
        self.assertEqual(self.used(), 1)
        self.assertEqual(self.trainer._action_history, ["free"])

    def test_success_and_decline_never_consume_frequency_or_triggered_action(self):
        seen = []
        success = self.use(fixed=[4, 4, 4], decision=lambda check: seen.append(check) or True)
        self.assertTrue(success["check"].passed)
        self.assertEqual(seen, [])
        self.assertEqual(self.used(), 0)
        self.assertEqual(getattr(self.trainer, "_action_history", []), [])

        decline = self.use(decision=lambda check: seen.append(check) or False)
        self.assertFalse(decline["rerolled"])
        self.assertEqual(decline["roll"], decline["first_roll"])
        self.assertEqual(len(seen), 1)
        self.assertEqual(self.used(), 0)
        self.assertEqual(getattr(self.trainer, "_action_history", []), [])

    def test_original_pool_ap_helper_modifier_and_penalty_are_applied_once(self):
        self.engine.boost_roll(
            self.trainer, self.pokemon, roll_id="mistake-ap", kind="skill"
        )
        available_after_boost = AP.available(self.trainer)
        result = self.use(
            dc=15,
            roll_id="mistake-ap",
            mods=2,
            helper_rank=4,
            helper_bonus=4,
            penalty_count=1,
            fixed_penalties=[3],
            reroll_penalties=[1],
        )
        first, final = result["first_roll"], result["roll"]
        self.assertEqual((first.rank, first.faces, first.helper_bonus, first.penalties), (3, (1, 1, 1), 4, (3,)))
        self.assertEqual((first.total, final.total), (7, 17))
        self.assertEqual(final.modifier, first.modifier + 5)
        self.assertEqual(final.helper_bonus, first.helper_bonus)
        self.assertEqual(AP.available(self.trainer), available_after_boost)
        self.assertEqual(self.engine._ap_rolls["mistake-ap"]["state"], "resolved")
        with self.assertRaises(ValueError):
            self.engine.skill_roll(
                self.pokemon, "육상", fixed=[1, 1, 1], roll_id="mistake-ap"
            )

    def test_daily_three_counts_rerolls_and_explicit_day_refreshes(self):
        for _ in range(3):
            self.assertTrue(self.use()["rerolled"])
        self.assertEqual(self.used(), 3)
        before = self.stable_state()
        with self.assertRaises(ValueError):
            self.use()
        self.assertEqual(self.stable_state(), before)

        DOWNTIME.new_day(self.trainer)
        DOWNTIME.new_day(self.pokemon)
        self.use()
        self.assertEqual(self.used(), 1)

    def test_observed_choice_error_resumes_same_first_and_completed_id_cannot_repeat(self):
        record, first_check = self.pending()
        first = record["observation"]["first"]
        rng_after_first = self.engine.rng.getstate()
        result = self.use(
            dc=99,
            roll_id="mistake-pending",
            decision=lambda check: False,
        )
        self.assertIs(result["first_roll"], first)
        self.assertEqual(result["check"], first_check)
        self.assertEqual(self.engine.rng.getstate(), rng_after_first)
        self.assertEqual(record["state"], "complete")
        self.assertEqual(self.used(), 0)

        before = self.stable_state()
        with self.assertRaises(ValueError):
            self.use(dc=99, roll_id="mistake-pending")
        self.assertEqual(self.stable_state(), before)

    def test_preflight_and_late_failures_preserve_the_correct_atomic_boundary(self):
        for mode in ("bad-reroll-shape", "sleep"):
            self.setUp()
            if mode == "sleep":
                self.trainer.conditions.add("잠듦")
            before = self.stable_state()
            options = {"reroll_faces": [2]} if mode == "bad-reroll-shape" else {}
            with self.assertRaises(ValueError):
                self.use(**options)
            self.assertEqual(self.stable_state(), before)
            self.assertFalse(self.engine._ap_rolls)

        self.setUp()
        seen = []

        def lose_permission(check):
            seen.append(check)
            self.trainer.conditions.add("잠듦")
            return True

        with self.assertRaises(ValueError):
            self.use(roll_id="late-permission", decision=lose_permission)
        record = self.engine._ap_rolls["late-permission"][OBSERVED.KEY]
        self.assertEqual(record["state"], "pending")
        self.assertEqual(self.used(), 0)
        resumed = self.use(
            roll_id="late-permission", decision=lambda check: False
        )
        self.assertEqual(resumed["check"], seen[0])
        self.assertFalse(resumed["rerolled"])

        self.setUp()
        self.engine.rng = Sequence([1, 1, 1, 0, 2, 2])
        with self.assertRaises(ValueError):
            self.use(
                fixed=None,
                reroll_faces=None,
                roll_id="bad-private-reroll",
            )
        record = self.engine._ap_rolls["bad-private-reroll"][OBSERVED.KEY]
        self.assertEqual(record["observation"]["first"].faces, (1, 1, 1))
        self.assertEqual(record["state"], "pending")
        self.assertEqual(self.engine.rng.faces, [0, 2, 2])
        self.assertEqual(self.used(), 0)

    def test_gm_snapshot_restores_pending_observation_with_live_participants(self):
        record, first_check = self.pending(roll_id="gm-pending")
        self.engine.gm.snapshot("learn-from-mistakes-pending")
        self.use(dc=99, roll_id="gm-pending", decision=lambda check: False)
        self.engine.gm.restore("learn-from-mistakes-pending")

        restored = self.engine._ap_rolls["gm-pending"][OBSERVED.KEY]
        self.assertIs(restored["participants"][0], self.trainer)
        self.assertIs(restored["participants"][1], self.pokemon)
        self.assertEqual(restored["state"], "pending")
        result = self.use(dc=99, roll_id="gm-pending", decision=lambda check: False)
        self.assertEqual(result["check"], first_check)
        self.assertEqual(result["first_roll"], record["observation"]["first"])

    def test_json_roundtrip_restores_pending_identity_then_consumes_once(self):
        record, _ = self.pending(roll_id="json-pending")
        payload = json.loads(json.dumps(dump_engine(self.engine), ensure_ascii=False))
        restored_engine = load_engine(self.rules, payload)
        actors = {actor.spec["id"]: actor for actor in restored_engine.everyone}
        trainer = actors[self.trainer.spec["id"]]
        pokemon = actors[self.pokemon.spec["id"]]
        restored = restored_engine._ap_rolls["json-pending"][OBSERVED.KEY]
        self.assertIs(restored["participants"][0], trainer)
        self.assertIs(restored["participants"][1], pokemon)
        self.assertEqual(restored["observation"]["first"], record["observation"]["first"])

        result = restored_engine.contest_skill_feature(
            trainer,
            pokemon,
            FEATURES.MISTAKES,
            "육상",
            99,
            fixed=[1, 1, 1],
            reroll_faces=[2, 2, 2],
            decision=lambda check: True,
            roll_id="json-pending",
        )
        self.assertTrue(result["rerolled"])
        self.assertEqual(self.used(trainer), 1)
        with self.assertRaises(ValueError):
            restored_engine.contest_skill_feature(
                trainer,
                pokemon,
                FEATURES.MISTAKES,
                "육상",
                99,
                fixed=[1, 1, 1],
                reroll_faces=[2, 2, 2],
                decision=lambda check: True,
                roll_id="json-pending",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
