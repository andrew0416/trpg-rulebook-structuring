"""Actual Extended lessons, pupil-owned payments and permanent Ability results."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
import ability_transitions as ABILITIES
import feature_ability_lessons as LESSONS
import grant_payments as PAYMENTS
import items
import state_codec as CODEC
import state_grants as GRANTS

CASES = {
    "feat/효과적인-방법": ("class/듀얼리스트", ("ability/착취", "ability/강내성")),
    "feat/댄스-연습": ("class/댄서", ("ability/회전춤", "ability/마이페이스")),
    "feat/집단-전술": ("class/헌터", ("ability/무리사냥", "ability/팀워크")),
}


class FeatureAbilityLessonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="all")

    def add(self, spec):
        actor = Combatant(self.rules, spec)
        self.engine.gm.add_combatant(actor, pos=(1, 1), side="party", reason="actual lesson participants")
        return actor

    def fixture(self, uid):
        self.uid = uid
        self.engine = Engine(self.rules, seed=1199)
        self.teacher = self.add(build_trainer(
            self.rules, "teacher", 30, dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
            abilities=[], extra={"classes": [CASES[uid][0]], "feats": [], "edges": []},
        ))
        self.teacher.spec["feats"] = [uid]
        items.register_feats(self.engine, self.teacher)
        self.pupil = self.add(build_pokemon(
            self.rules, "이상해씨", 20, moves=[], abilities=[],
            extra={"trainer_id": self.teacher.entity_id, "tutor_points": 5},
        ))

    def snapshot(self):
        return deepcopy((CODEC.dump_engine(self.engine), self.engine.rng.getstate()))

    def teach(self, ability, **changes):
        options = {"target": self.pupil, "feature": self.uid, "ability": ability,
                   "seconds": 45, "reason": "GM observed the completed Extended Ability lesson"}
        options.update(changes)
        return self.engine.pokemon_activity(self.teacher, "teach_feature_ability", **options)

    def reject(self, ability, **changes):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.teach(ability, **changes)
        self.assertEqual(self.snapshot(), before)

    def test_all_six_choices_use_native_activities_real_time_payment_and_ability_consumers(self):
        for uid, (_, choices) in CASES.items():
            for ability in choices:
                with self.subTest(feature=uid, ability=ability):
                    self.fixture(uid)
                    items.register_feats(self.engine, self.teacher)
                    items.register_feats(self.engine, self.teacher)
                    self.assertEqual(self.teacher.stats["spe"], 10 if uid == "feat/효과적인-방법" else 11)
                    self.assertEqual(ABILITIES.known(self.pupil), [])
                    self.assertEqual(self.pupil.spec["tutor_points"], 5)
                    result = self.teach(ability)
                    self.assertEqual((result["source"], result["ability"], result["point_cost"], result["seconds"]),
                                     (uid, ability, 2, 45))
                    self.assertEqual(self.engine.elapsed_seconds, 45)
                    self.assertEqual(self.pupil.spec["tutor_points"], 3)
                    self.assertEqual(ABILITIES.known(self.pupil), [ability])
                    self.assertTrue(ABILITIES.active(self.pupil, ability))
                    payment = self.pupil.spec[GRANTS.KEY]["payments"][result["payment"]["group_id"]]
                    self.assertEqual(payment["paid"], 2)
                    self.assertEqual(payment["request"]["rule_id"], uid)
                    source = self.pupil.spec[GRANTS.KEY]["sources"][payment["children"][0]]
                    self.assertEqual((source["tutor_points"], source["owner_id"], source["lifetime"]), (0, None, None))
                    self.assertEqual(source["ability_lesson"]["job_id"], result["job_id"])
                    self.assertEqual(source["ability_lesson"]["teacher_id"], self.teacher.entity_id)
                    PAYMENTS.validate(self.pupil)

    def test_own_pokemon_restrictions_and_effective_methods_foreign_target(self):
        for uid, (_, choices) in CASES.items():
            with self.subTest(feature=uid):
                self.fixture(uid)
                other = self.add(build_trainer(
                    self.rules, "other owner", 30,
                    dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10), abilities=[]))
                self.pupil.spec["trainer_id"] = other.entity_id
                if uid == "feat/효과적인-방법":
                    self.teach(choices[0])
                    self.assertIn(choices[0], ABILITIES.known(self.pupil))
                else:
                    self.reject(choices[0])

    def test_qualification_choice_balance_and_manual_bypass_fail_atomically(self):
        uid = "feat/효과적인-방법"
        parent, choices = CASES[uid]
        self.fixture(uid)
        self.reject("ability/철주먹")
        self.reject(None)
        self.reject(choices[0], seconds=0)
        self.reject(choices[0], reason="")
        self.teacher.spec["feats"] = []
        self.reject(choices[0])
        self.teacher.spec["feats"] = [uid]
        self.teacher.spec["classes"] = []
        self.reject(choices[0])
        self.teacher.spec["classes"] = [parent]
        self.pupil.spec["tutor_points"] = 1
        self.reject(choices[0])
        self.pupil.spec["tutor_points"] = 5
        self.engine.encounter_active = True
        self.reject(choices[0])
        for uid in CASES:
            with self.subTest(feature=uid):
                self.fixture(uid)
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, "explicit choice"):
                    self.engine.manual_feat(self.teacher, uid, self.pupil)
                self.assertEqual(self.snapshot(), before)

    def test_permanent_result_and_once_history_survive_both_restores_and_source_refund(self):
        for uid, (_, choices) in CASES.items():
            with self.subTest(feature=uid):
                self.fixture(uid)
                items.register_feats(self.engine, self.teacher)
                result = self.teach(choices[0])
                self.engine.gm.snapshot("trained")
                self.teacher.spec.update(feats=[], classes=[])
                items.register_feats(self.engine, self.teacher)
                self.assertEqual(self.teacher.stats["spe"], 10)
                GRANTS.reconcile(self.engine, self.pupil)
                self.assertIn(choices[0], ABILITIES.known(self.pupil))
                self.engine.gm.restore("trained")
                self.reject(choices[1])
                loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(self.engine), ensure_ascii=False)))
                actors = {actor.entity_id: actor for actor in loaded.everyone}
                self.teacher, self.pupil, self.engine = actors[self.teacher.entity_id], actors[self.pupil.entity_id], loaded
                self.assertIn(choices[0], ABILITIES.known(self.pupil))
                self.reject(choices[1])
                source_id = result["payment"]["sources"][0]
                PAYMENTS.refund(loaded, self.pupil, [source_id], request_id="explicit-ended-lesson",
                                reason="GM explicitly ended this source without a TP refund", refund_mode="none")
                self.assertNotIn(choices[0], ABILITIES.known(self.pupil))
                self.assertEqual(self.pupil.spec["tutor_points"], 3)
                self.reject(choices[1])

    def test_independent_ability_is_not_duplicated_or_erased_and_late_failure_restores_clock(self):
        uid = "feat/집단-전술"
        ability = CASES[uid][1][0]
        self.fixture(uid)
        GRANTS.grant(self.pupil, "abilities", ABILITIES.label(self.rules, ability),
                     "equipment:independent-ability", "equipment")
        result = self.teach(ability)
        self.assertEqual(ABILITIES.known(self.pupil).count(ability), 1)
        GRANTS.revoke(self.pupil, "equipment:independent-ability", engine=self.engine)
        self.assertIn(ability, ABILITIES.known(self.pupil))
        PAYMENTS.validate(self.pupil)
        self.fixture(uid)
        before = self.snapshot()
        with patch.object(LESSONS.PAYMENTS, "acquire", side_effect=ValueError("late payment failure")):
            with self.assertRaisesRegex(ValueError, "late payment"):
                self.teach(ability)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.engine.elapsed_seconds, 0)
        self.assertEqual(ABILITIES.known(self.pupil), [])

    def test_exact_body_and_ability_source_bindings_reject_catalogue_drift(self):
        uid = "feat/댄스-연습"
        self.fixture(uid)
        policy = LESSONS._policy(self.rules)
        # The lesson family now also carries Culinary Appreciation (feat/요리-음미); these three bindings stay exact.
        self.assertEqual(set(policy), set(LESSONS.SOURCES))
        self.assertTrue(set(CASES) <= set(policy))
        for source_uid in (uid, *CASES[uid][1]):
            unit = deepcopy(self.rules.selection.units[source_uid])
            unit["source"]["sha256"] = "0"*64
            before = self.snapshot()
            del self.rules._feature_ability_lessons
            try:
                with patch.dict(self.rules.selection.units, {source_uid: unit}):
                    with self.assertRaises(ValueError):
                        self.teach(CASES[uid][1][0])
            finally:
                self.rules._feature_ability_lessons = policy
            self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
