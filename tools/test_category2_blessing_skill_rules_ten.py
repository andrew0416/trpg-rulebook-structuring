"""Direct exact-source tests for ten CSV Blessing skill-rule consumers."""

from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "input").is_dir():
    ROOT = Path(r"D:/trpg-rulebook-structuring/ptk-structure-experiment")
sys.path.insert(0, str(ROOT / "engine"))

from engine import Combatant, Engine, Rules
from ruleset import ExcludedRuleSelection, RuleFilter
from state_codec import dump_engine, load_engine
import blessing_skill_rules as B
import items
import turn


CLAUSE_IDS = {
    "C2CSV/input/db/class-data.csv:R3:blessing",
    "C2CSV/input/db/class-data.csv:R5:blessing",
    "C2CSV/input/db/class-data.csv:R27:blessing",
    "C2CSV/input/db/class-data.csv:R36:blessing",
    "C2CSV/input/db/class-data.csv:R43:blessing",
    "C2CSV/input/db/class-data.csv:R46:blessing",
    "C2CSV/input/db/class-data.csv:R52:blessing",
    "C2CSV/input/db/class-data.csv:R55:blessing",
    "C2CSV/input/db/class-data.csv:R128:blessing",
    "C2CSV/input/db/class-data.csv:R151:blessing",
}


def trainer(rules, identity, name):
    return Combatant(
        rules,
        {
            "id": identity,
            "name": name,
            "kind": "trainer",
            "level": 20,
            "feats": ["feat/나의-이름으로", "supp-blessings/계약자"],
            "stats": {"hp": 10, "atk": 5, "def": 5, "spa": 5, "spd": 5, "spe": 5},
            "skills": {
                "전투": "숙련",
                "협박": "숙련",
                "교활": "전문",
                "매력": "초보",
                "직감": "초보",
                "통찰": "초보",
                "생존": "초보",
                "오컬트학": "초보",
                "기술학": "초보",
                "일반지식": "초보",
                "의학": "초보",
                "집중": "초보",
                "명령": "초보",
            },
        },
    )


class BlessingSkillRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="fantasy")

    def setUp(self):
        self.e = Engine(self.rules, seed=916)
        self.a = trainer(self.rules, "trainer/blessing-skill-a", "Blessing A")
        self.b = trainer(self.rules, "trainer/blessing-skill-b", "Blessing B")
        self.p = Combatant(
            self.rules,
            {
                "id": "pokemon/blessing-target",
                "name": "Target Pokemon",
                "kind": "pokemon",
                "level": 15,
                "stats": {"hp": 10, "atk": 5, "def": 5, "spa": 5, "spd": 5, "spe": 5},
                "skills": {"통찰": "초보"},
                "types": ["노말"],
            },
        )
        self.e.everyone = [self.a, self.b, self.p]
        self.e.gm.everyone = self.e.everyone

    def own(self, gift, *, actor=None, configuration=None):
        actor = self.a if actor is None else actor
        actor.spec.setdefault("gifts", []).append(gift)
        patrons = {B.ANCIENT_WISDOM: "뮤", B.PARAGON: "뮤", B.WATCHFUL_SLEEP: "지라치",
                   B.FOUNT_OF_KNOWLEDGE: "유크시", B.PLANT_INTUITION: "쉐이미",
                   B.SPIRIT_OF_JUSTICE: "코바르온", B.DAZZLING_STAGE: "메로엣타",
                   B.ROYAL_PRIVILEGE: "디안시", B.HERO_OF_BALANCE: "큐레무",
                   B.ALIEN_FACE: "미싱노 (코즈믹 호러)"}
        actor.spec.setdefault("gift_patrons", {})[gift] = patrons[gift]
        return self.e.confirm_blessing_gift(
            actor,
            gift,
            reason="GM approves this exact acquired CSV Blessing",
            configuration=configuration,
        )

    def snapshot(self, actor=None):
        actor = self.a if actor is None else actor
        return (
            deepcopy(actor.spec),
            deepcopy(getattr(actor, "budget", None)),
            deepcopy(getattr(actor, "_action_history", [])),
            self.e.rng.getstate(),
            list(self.e.log_lines),
        )

    def rejected(self, call, *, actor=None):
        before = self.snapshot(actor)
        with self.assertRaises((ValueError, ExcludedRuleSelection)):
            call()
        self.assertEqual(self.snapshot(actor), before)

    def test_exact_ten_policy_rows_registry_and_source_cells_are_bound(self):
        policy = json.loads((ROOT / "data/blessing-skill-rules-policy.json").read_text(encoding="utf-8"))
        source_path = ROOT / policy["source_file"]
        self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), policy["source_file_sha256"])
        registry = json.loads(
            (ROOT / "data/verification/category2-class-csv-clause-status.json").read_text(encoding="utf-8")
        )
        indexed = {row["id"]: row for row in registry["rows"]}
        with source_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual({row["clause_id"] for row in policy["rules"]}, CLAUSE_IDS)
        self.assertEqual(len(B.RULES), 10)
        for rule in policy["rules"]:
            source = indexed[rule["clause_id"]]
            actual = [rows[rule["record"] - 1][column - 1] for column in source["columns"]]
            digest = hashlib.sha256(
                json.dumps(actual, ensure_ascii=False, separators=(",", ":")).encode()
            ).hexdigest()
            self.assertEqual(digest, rule["cell_sha256"])
            self.assertEqual(digest, source["cell_sha256"])
            self.assertTrue(source["include_category2"])
            self.assertEqual(source["status"], "implemented")
            self.assertEqual(source["full_md_equivalence"], "not_proven_distinct_source_variant_preserved")
            self.assertIsNone(source["dedupe_target"])
            self.assertEqual(self.rules._selected_rule(rule["gift"]), rule["gift"])

    def test_acquisition_approval_configuration_and_selection_gate_every_consumer(self):
        self.rejected(
            lambda: self.e.confirm_blessing_gift(
                self.a,
                B.PARAGON,
                reason="not acquired",
                configuration={"role": "messiah", "category": "mental"},
            )
        )
        self.a.spec["gifts"] = [B.PARAGON]
        self.rejected(
            lambda: self.e.confirm_blessing_gift(
                self.a,
                B.PARAGON,
                reason="bad category",
                configuration={"role": "messiah", "category": "unknown"},
            )
        )
        self.e.confirm_blessing_gift(
            self.a,
            B.PARAGON,
            reason="actual approval",
            configuration={"role": "messiah", "category": "mental"},
        )
        self.assertEqual(self.e.skill_roll(self.a, "기술학", fixed=[2, 2, 2]).modifier, 2)
        old_filter = self.rules.ruleset
        try:
            self.rules.ruleset = RuleFilter(
                {"sources": ["core", "errata", "fantasy", "blessings"], "exclude_units": [B.PARAGON]}
            )
            self.rules._apply_ruleset()
            self.rejected(lambda: self.e.skill_roll(self.a, "기술학", fixed=[2, 2, 2]))
        finally:
            self.rules.ruleset = old_filter
            self.rules._apply_ruleset()

    def test_ancient_wisdom_roles_bonus_dice_and_one_check_free_activation(self):
        self.own(B.ANCIENT_WISDOM, configuration={"role": "messiah"})
        occult = self.e.skill_roll(self.a, "오컬트학", fixed=[2, 2, 2, 2])
        technology = self.e.skill_roll(
            self.a,
            "기술학",
            fixed=[2, 2, 2, 2],
            skill_context={"purpose": "occult_topic", "reason": "actual occult device"},
        )
        ordinary = self.e.skill_roll(self.a, "기술학", fixed=[2, 2, 2])
        self.assertEqual((len(occult.faces), len(technology.faces), len(ordinary.faces)), (4, 4, 3))

        self.setUp()
        self.own(B.ANCIENT_WISDOM, configuration={"role": "contractor"})
        self.assertEqual(len(self.e.skill_roll(self.a, "오컬트학", fixed=[2, 2, 2]).faces), 3)
        activation = self.e.activate_blessing_skill_rule(
            self.a, B.ANCIENT_WISDOM, reason="Contractor invokes ancient knowledge"
        )
        self.assertEqual(activation["action"], "free")
        empowered = self.e.skill_roll(self.a, "오컬트학", fixed=[2, 2, 2, 2, 2])
        self.assertEqual(len(empowered.faces), 5)
        self.assertEqual(
            self.a.spec[B.STATE]["activations"][B.ANCIENT_WISDOM]["status"],
            "consumed",
        )
        self.assertEqual(len(self.e.skill_roll(self.a, "오컬트학", fixed=[2, 2, 2]).faces), 3)

    def test_paragon_original_swift_cost_native_budget_atomicity_and_both_restores(self):
        self.rules=Rules(ROOT,ruleset="fantasy");self.setUp()
        self.own(B.PARAGON, configuration={"role": "messiah", "category": "mental"})
        self.assertEqual(self.e.skill_roll(self.a, "기술학", fixed=[1, 1, 1]).modifier, 2)
        self.assertEqual(self.e.skill_roll(self.a, "매력", fixed=[1, 1, 1]).modifier, 0)
        self.assertEqual(B.RULES[B.PARAGON]["action"], {"messiah": None, "contractor": "swift"})
        actor = self.b
        self.own(B.PARAGON, actor=actor, configuration={"role": "contractor", "category": "mental"})
        def next_actual_turn():
            if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
            if self.e.round_start_seconds is not None:self.e.end_round()
            self.e.start_round(self.e.everyone);self.e.start_of_turn(actor,initiative_count=20)
        for shift in (0, 1):
            with self.subTest(unavailable_swift_with_shift=shift):
                next_actual_turn()
                self.assertTrue(turn.spend(self.e,actor,'standard','actual earlier Standard'))
                self.assertTrue(turn.spend(self.e,actor,'swift','actual earlier Swift'))
                if shift==0:self.assertTrue(turn.spend(self.e,actor,'shift','actual earlier Shift'))
                self.assertEqual(actor.budget,{"standard":0,"shift":shift,"swift":0})
                self.rejected(
                    lambda: self.e.activate_blessing_skill_rule(actor, B.PARAGON, reason="no Swift remains"),
                    actor=actor,
                )
                self.assertNotIn(B.STATE, actor.spec)
        next_actual_turn()
        self.assertTrue(turn.spend(self.e,actor,'standard','actual earlier Standard'))
        self.assertTrue(turn.spend(self.e,actor,'shift','actual earlier Shift'))
        self.assertEqual(actor.budget,{'standard':0,'shift':0,'swift':1})
        before_history = list(getattr(actor, "_action_history", []))
        activation = self.e.activate_blessing_skill_rule(
            actor, B.PARAGON, reason="activate category with only the printed Swift action"
        )
        self.assertEqual(activation["action"], "swift")
        self.assertEqual(activation["source"], B.RULES[B.PARAGON]["clause_id"])
        self.assertEqual(activation["lifetime"], "scene")
        self.assertEqual(actor.budget, {"standard": 0, "shift": 0, "swift": 0})
        self.assertEqual(actor._action_history, before_history + ["swift"])
        self.assertEqual(self.e.skill_roll(actor, "기술학", fixed=[1, 1, 1]).modifier, 1)
        self.assertEqual(self.e.skill_roll(actor, "매력", fixed=[1, 1, 1]).modifier, 0)
        next_actual_turn()
        self.assertTrue(turn.spend(self.e,actor,'standard','actual next-turn Standard'))
        self.assertTrue(turn.spend(self.e,actor,'shift','actual next-turn Shift'))
        self.rejected(
            lambda: self.e.activate_blessing_skill_rule(actor, B.PARAGON, reason="already active scene"),
            actor=actor,
        )
        saved = deepcopy(actor.spec[B.STATE])
        self.e.gm.snapshot("paragon-swift")
        self.e.gm.restore("paragon-swift", reason="restore the actual Swift-paid scene activation")
        self.assertEqual(actor.spec[B.STATE], saved)
        self.assertEqual(actor.budget["swift"], 1)
        self.assertEqual(self.e.skill_roll(actor, "기술학", fixed=[1, 1, 1]).modifier, 1)
        payload = json.loads(json.dumps(dump_engine(self.e), ensure_ascii=False))
        import state_codec as CODEC
        fresh=Rules(ROOT,ruleset='fantasy')
        self.assertEqual(CODEC.rules_fingerprint(fresh),CODEC.rules_fingerprint(self.e.r))
        loaded = load_engine(fresh, payload)
        restored = next(value for value in loaded.everyone if value.entity_id == actor.entity_id)
        self.assertEqual(restored.spec[B.STATE], saved)
        self.assertEqual(restored.budget, actor.budget)
        self.assertEqual(restored._action_history, actor._action_history)
        self.assertEqual(loaded.skill_roll(restored, "기술학", fixed=[1, 1, 1]).modifier, 1)
        loaded.end_scene()
        self.assertEqual(loaded.skill_roll(restored, "기술학", fixed=[1, 1, 1]).modifier, 0)

    def test_watchful_sleep_is_only_imminent_danger_perception_and_never_wakes(self):
        self.own(B.WATCHFUL_SLEEP)
        self.a.conditions.add("잠듦")
        before_actions = deepcopy(getattr(self.a, "_action_history", []))
        result = self.e.skill_roll(
            self.a,
            "통찰",
            fixed=[3, 3, 3],
            skill_context={"purpose": "imminent_danger", "reason": "collapsing ceiling"},
        )
        self.assertEqual(result.total, 9)
        self.assertIn("잠듦", self.a.conditions)
        self.assertEqual(getattr(self.a, "_action_history", []), before_actions)
        self.rejected(
            lambda: self.e.skill_roll(
                self.a,
                "매력",
                fixed=[3, 3, 3],
                skill_context={"purpose": "imminent_danger", "reason": "wrong skill"},
            )
        )

    def test_fount_of_knowledge_rerolls_ones_once_only_on_two_chosen_educations(self):
        self.own(
            B.FOUNT_OF_KNOWLEDGE,
            configuration={"education_skills": ["기술학", "일반지식"]},
        )
        self.e.rng.seed(1)
        chosen = self.e.skill_roll(self.a, "기술학", fixed=[1, 2, 1])
        self.assertEqual(chosen.faces, (2, 2, 5))
        unchosen = self.e.skill_roll(self.a, "의학", fixed=[1, 2, 1])
        self.assertEqual(unchosen.faces, (1, 2, 1))

    def test_plant_intuition_rerolls_plant_survival_and_identifies_visible_crops(self):
        self.own(B.PLANT_INTUITION)
        self.e.rng.seed(1)
        result = self.e.skill_roll(
            self.a,
            "생존",
            fixed=[1, 2, 1],
            skill_context={"purpose": "plant_related", "reason": "inspect this actual plant"},
        )
        self.assertEqual(result.faces, (2, 2, 5))
        identity = self.e.identify_visible_blessing_crop(
            self.a,
            "오랭열매",
            visible=True,
            reason="the berry is in clear view",
        )
        self.assertEqual(identity["kind"], "berry")
        self.assertTrue(identity["identified"])
        self.rejected(
            lambda: self.e.identify_visible_blessing_crop(
                self.a,
                "빨간규토리",
                visible=False,
                reason="hidden behind an opaque wall",
            )
        )

    def test_spirit_of_justice_replaces_body_and_adds_disarm_bonus(self):
        self.own(B.SPIRIT_OF_JUSTICE)
        result = self.e.skill_roll(
            self.a,
            "전투",
            mods=2,
            fixed=[2, 2, 2, 2],
            skill_context={
                "purpose": "disarm",
                "reason": "actual disarm attempt",
                "modifier_basis": {"body": 2, "mind": 5, "selected": "mind"},
            },
        )
        self.assertEqual(result.modifier, 7)
        self.rejected(
            lambda: self.e.skill_roll(
                self.a,
                "전투",
                mods=1,
                fixed=[2, 2, 2, 2],
                skill_context={
                    "modifier_basis": {"body": 2, "mind": 5, "selected": "mind"}
                },
            )
        )

    def test_dazzling_stage_and_royal_privilege_keep_exact_csv_sources(self):
        self.own(B.DAZZLING_STAGE)
        stage = self.e.skill_roll(
            self.a,
            "매력",
            fixed=[1, 1, 1],
            skill_context={"purpose": "singing", "reason": "actual song performance"},
        )
        self.assertEqual(stage.modifier, 2)

        self.setUp()
        self.own(B.ROYAL_PRIVILEGE)
        self.a.spec.setdefault("items", {})["빨강조각"] = 1
        items.register_item(self.e, self.a, "빨강조각")
        self.assertIn("빨강조각", self.a._item_reg)
        self.assertEqual(self.a._item_reg["빨강조각"]["slots"], ["장신구"])
        self.assertEqual(self.e.skill_roll(self.a, "협박", fixed=[1, 1, 1, 1]).modifier, 2)
        self.assertEqual(self.e.skill_roll(self.a, "교활", fixed=[1, 1, 1, 1, 1]).modifier, 0)

    def test_hero_of_balance_penalizes_only_other_bound_intuition_checks(self):
        self.own(B.HERO_OF_BALANCE, actor=self.a)
        against_owner = self.e.skill_roll(
            self.b,
            "직감",
            fixed=[2, 2, 2],
            skill_target=self.a,
            skill_context={"purpose": "detect_lies", "reason": "read the owner's actual statement"},
        )
        against_other = self.e.skill_roll(
            self.b,
            "직감",
            fixed=[2, 2, 2],
            skill_target=self.p,
            skill_context={"purpose": "detect_lies", "reason": "different target"},
        )
        self.assertEqual(against_owner.modifier, -3)
        self.assertEqual(against_other.modifier, 0)

    def test_alien_face_replaces_body_and_adds_bonus_only_against_pokemon(self):
        self.own(B.ALIEN_FACE)
        result = self.e.skill_roll(
            self.a,
            "협박",
            mods=2,
            fixed=[2, 2, 2, 2],
            skill_target=self.p,
            skill_context={"modifier_basis": {"body": 2, "mind": 5, "selected": "mind"}},
        )
        trainer_target = self.e.skill_roll(
            self.a,
            "협박",
            mods=2,
            fixed=[2, 2, 2, 2],
            skill_target=self.b,
            skill_context={"modifier_basis": {"body": 2, "mind": 5, "selected": "mind"}},
        )
        self.assertEqual(result.modifier, 7)
        self.assertEqual(trainer_target.modifier, 5)

    def test_save_restore_preserves_choices_approval_scene_activation_and_reroll_rules(self):
        self.own(B.PARAGON, configuration={"role": "contractor", "category": "mental"})
        self.own(
            B.FOUNT_OF_KNOWLEDGE,
            configuration={"education_skills": ["기술학", "일반지식"]},
        )
        turn.reset_budget(self.e, self.a)
        self.e.activate_blessing_skill_rule(self.a, B.PARAGON, reason="persist scene activation")
        payload = json.loads(json.dumps(dump_engine(self.e), ensure_ascii=False))
        loaded = load_engine(self.rules, payload)
        actor = next(value for value in loaded.everyone if value.entity_id == self.a.entity_id)
        loaded.rng.seed(1)
        result = loaded.skill_roll(actor, "기술학", fixed=[1, 2, 1])
        self.assertEqual(result.faces, (2, 2, 5))
        self.assertEqual(result.modifier, 1)


if __name__ == "__main__":
    unittest.main()

