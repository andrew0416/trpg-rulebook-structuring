"""Five exact feature ability choices share one owned, atomic projection."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from builder import build_trainer
from engine import Combatant, Engine, Rules
import ability_transitions as ABILITIES
import feature_ability_grants as FEATURE_ABILITIES
import items
import state_codec as CODEC
import state_grants as GRANTS


CASES = {
    "feat/분노의-힘": ("불굴의격노", "화이트플레임"),
    "feat/다크-소울": ("그림자밟기", "대운"),
    "feat/번개의-몸": ("축전", "전기엔진"),
    "feat/빙하-방어": ("아이스실드", "겨울의입맞춤"),
    "feat/불쾌한-몸": ("힘흡수", "독가시", "독수"),
}


class FeatureAbilityChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="fantasy")

    def fixture(self, feats=(), choices=None, abilities=()):
        engine = Engine(self.rules, seed=193)
        spec = build_trainer(
            self.rules, "feature-ability-owner", 30,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
            moves=[],
        )
        spec.update(
            classes=[], edges=[], feats=list(feats), abilities=list(abilities),
            feature_choices=deepcopy(choices or {}),
            skills={"곡예": 6, "집중": 6, "교활": 6, "은신": 6},
        )
        actor = Combatant(self.rules, spec)
        engine.everyone = engine.gm.everyone = [actor]
        for ability in abilities:
            engine.register_abilities_one(actor, ability)
        return engine, actor

    @staticmethod
    def source(actor, uid):
        return "feature:" + actor.entity_id + ":" + uid

    @staticmethod
    def observed(engine, actor):
        prompts = []
        for prompt in engine.gm_prompts:
            row = {key: value for key, value in prompt.items() if key not in ("attacker", "target")}
            row["attacker_id"] = getattr(prompt.get("attacker"), "entity_id", None)
            row["target_id"] = getattr(prompt.get("target"), "entity_id", None)
            prompts.append(row)
        return deepcopy({
            "spec": actor.spec,
            "abilities": actor.abilities,
            "modifiers": actor.modifiers,
            "registry": actor.registry,
            "ability_triggers": actor.ability_triggers,
            "log_lines": engine.log_lines,
            "gm_prompts": prompts,
            "rng": engine.rng.getstate(),
        })

    def test_all_eleven_choices_use_exact_native_ability_receipts_once(self):
        self.assertEqual(FEATURE_ABILITIES.DECLARATIONS, CASES)
        for uid, choices in CASES.items():
            for choice in choices:
                with self.subTest(source=uid, choice=choice):
                    engine, actor = self.fixture([uid], {uid: [choice]})
                    self.assertEqual(items.register_feats(engine, actor), 1)
                    ability_id = self.rules.selection.resolve_name(choice, ("ability/",))
                    name = self.rules.selection.units[ability_id]["title"]
                    source = self.source(actor, uid)
                    row = actor.spec[GRANTS.KEY]["sources"][source]
                    self.assertEqual(actor.abilities, [name])
                    self.assertEqual(ABILITIES.known(actor), [ability_id])
                    self.assertEqual(row["grants"], {"abilities": [name]})
                    self.assertEqual(
                        (row["kind"], row["owner_id"], row["lifetime"], row["rule_id"], row["tutor_points"]),
                        ("feature", actor.entity_id, "while_owned", uid, 0),
                    )
                    self.assertEqual(
                        (row["feature_ability_projection"], row["feature_ability_selection"], row["feature_ability_name"]),
                        (1, ability_id, name),
                    )
                    self.assertIn(name, actor.spec[GRANTS.KEY]["ability_receipts"])
                    before = self.observed(engine, actor)
                    self.assertEqual(items.register_feats(engine, actor), 0)
                    self.assertEqual(self.observed(engine, actor), before)

    def test_printed_spacing_aliases_resolve_to_exact_catalog_identities(self):
        for printed, canonical in (("아이스 실드", "아이스실드"), ("겨울의 입맞춤", "겨울의입맞춤")):
            with self.subTest(choice=printed):
                uid = "feat/빙하-방어"
                engine, actor = self.fixture([uid], {uid: [printed]})
                items.register_feats(engine, actor)
                self.assertEqual(actor.abilities, [canonical])
                self.assertEqual(
                    actor.spec[GRANTS.KEY]["sources"][self.source(actor, uid)]["feature_ability_selection"],
                    "ability/" + canonical,
                )

    def test_invalid_missing_duplicate_and_out_of_domain_choices_are_read_only(self):
        uid = "feat/번개의-몸"
        invalid = (
            {},
            {uid: None},
            {uid: []},
            {uid: ["축전", "전기엔진"]},
            {uid: ["대운"]},
            {uid: [None]},
            {uid: ["축전"], "번개의 몸": ["축전"]},
        )
        for choices in invalid:
            with self.subTest(choices=choices):
                engine, actor = self.fixture([uid], choices)
                before = self.observed(engine, actor)
                with self.assertRaises(ValueError):
                    items.register_feats(engine, actor)
                self.assertEqual(self.observed(engine, actor), before)
                self.assertNotIn(self.source(actor, uid), actor.spec.get(GRANTS.KEY, {}).get("sources", {}))

        engine, actor = self.fixture([], {uid: ["축전"]})
        before = self.observed(engine, actor)
        self.assertEqual(items.register_feats(engine, actor), 0)
        self.assertEqual(self.observed(engine, actor), before)

    def test_existing_owned_choice_cannot_be_silently_replaced(self):
        uid = "feat/번개의-몸"
        engine, actor = self.fixture([uid], {uid: ["축전"]})
        items.register_feats(engine, actor)
        actor.spec["feature_choices"][uid] = ["전기엔진"]
        before = self.observed(engine, actor)
        with self.assertRaisesRegex(ValueError, "silently replaced"):
            items.register_feats(engine, actor)
        self.assertEqual(self.observed(engine, actor), before)
        self.assertEqual(actor.abilities, ["축전"])

    def test_all_plans_precede_mutation_and_late_second_registration_rolls_back(self):
        first, second = "feat/분노의-힘", "feat/다크-소울"
        engine, actor = self.fixture([first, second], {first: ["화이트플레임"], second: ["축전"]})
        before = self.observed(engine, actor)
        with self.assertRaises(ValueError):
            FEATURE_ABILITIES.register_all(engine, actor)
        self.assertEqual(self.observed(engine, actor), before)

        engine, actor = self.fixture([first, second], {first: ["화이트플레임"], second: ["대운"]})
        before = self.observed(engine, actor)
        original = Engine.register_abilities_one

        def fail_second(staged_engine, staged_actor, name):
            if name == "대운":
                raise RuntimeError("injected second native ability failure")
            return original(staged_engine, staged_actor, name)

        with patch.object(Engine, "register_abilities_one", new=fail_second):
            with self.assertRaisesRegex(RuntimeError, "second native ability"):
                FEATURE_ABILITIES.register_all(engine, actor)
        self.assertEqual(self.observed(engine, actor), before)
        self.assertNotIn(GRANTS.KEY, actor.spec)

    def test_while_owned_loss_removes_last_receipt_and_native_consumer(self):
        uid = "feat/번개의-몸"
        engine, actor = self.fixture([uid], {uid: ["축전"]})
        items.register_feats(engine, actor)
        move = self.rules.move(self.rules.move_id("전기쇼크"))
        self.assertEqual(engine.roll_damage(actor, actor, move, set_damage=True), 0)
        self.assertIn("축전", actor.spec[GRANTS.KEY]["ability_receipts"])

        actor.spec["feats"] = []
        items.register_feats(engine, actor)
        self.assertNotIn(self.source(actor, uid), actor.spec[GRANTS.KEY]["sources"])
        self.assertNotIn("축전", actor.abilities)
        self.assertNotIn("축전", actor.spec[GRANTS.KEY]["ability_receipts"])
        self.assertGreater(engine.roll_damage(actor, actor, move, set_damage=True), 0)
        self.assertFalse(any(row.get("_ability") == "축전" for row in actor.modifiers + actor.registry))

    def test_baseline_and_independent_same_ability_survive_feature_revoke(self):
        uid = "feat/번개의-몸"
        for kind in ("baseline", "independent"):
            with self.subTest(owner=kind):
                baseline = ["축전"] if kind == "baseline" else []
                engine, actor = self.fixture([uid], {uid: ["축전"]}, baseline)
                other = "equipment:independent-static"
                if kind == "independent":
                    GRANTS.grant(actor, "abilities", "축전", other, "equipment", lifetime="while_owned")
                    engine.register_abilities_one(actor, "축전")
                items.register_feats(engine, actor)
                GRANTS.revoke(actor, self.source(actor, uid), engine=engine)
                self.assertEqual(actor.abilities, ["축전"])
                self.assertIn("축전", actor.spec[GRANTS.KEY]["ability_receipts"])
                if kind == "independent":
                    GRANTS.revoke(actor, other, engine=engine)
                    self.assertNotIn("축전", actor.abilities)
                else:
                    self.assertEqual(actor.spec["abilities"], ["축전"])

    def test_snapshot_and_json_restore_keep_choice_then_reconcile_owner_loss(self):
        uid = "feat/빙하-방어"
        engine, actor = self.fixture([uid], {uid: ["겨울의입맞춤"]})
        items.register_feats(engine, actor)
        source = self.source(actor, uid)
        engine.gm.snapshot("feature-ability-choice")
        GRANTS.revoke(actor, source, engine=engine)
        self.assertNotIn("겨울의입맞춤", actor.abilities)
        engine.gm.restore("feature-ability-choice", reason="restore exact feature ability choice")
        self.assertEqual(actor.abilities, ["겨울의입맞춤"])
        self.assertEqual(actor.spec[GRANTS.KEY]["sources"][source]["feature_ability_selection"], "ability/겨울의입맞춤")

        restored = CODEC.load_engine(
            self.rules,
            json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False)),
        )
        copy = restored.everyone[0]
        self.assertEqual(copy.abilities, ["겨울의입맞춤"])
        copy.spec["feats"] = []
        items.register_feats(restored, copy)
        self.assertNotIn("겨울의입맞춤", copy.abilities)
        self.assertNotIn(source, copy.spec[GRANTS.KEY]["sources"])


if __name__ == "__main__":
    unittest.main()
