"""Style's exact Sturdy selection reaches native injury application."""
from copy import copy, deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
import ability_transitions as ABILITIES
import contest_features as CONTEST
import effects_ext as EXT
import native_scenario_fixture as NATIVE
import scene_feature_ability_grants as SCENE
import stamina as STAMINA
import state_grants as GRANTS
import test_category2_scene_feature_ability_grants as fixtures
import test_category2_ability_transitions as transition_fixtures
from state_codec import dump_engine, load_engine


class StyleSturdyNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.SceneFeatureAbilityGrantTests.setUpClass()
        cls.fixture = fixtures.SceneFeatureAbilityGrantTests()

    def style(self, ability="옹골참", *, activate=True, branch="강인함"):
        engine, trainer, pokemon = self.fixture.style_fixture()
        ranked, _, children = CONTEST.RANKED[branch]
        trainer.spec.update(
            feats=[ranked, children[0], SCENE.STYLE_FEATURE],
            feat_ranks={ranked: 2},
            feature_choices={CONTEST.STYLE: [branch], SCENE.STYLE_FEATURE: [branch]},
        )
        for target in pokemon:
            target.spec["poffins"] = [branch] * 3
        target = pokemon[0]
        self.fixture.open_style_priority(engine, trainer, target)
        if activate:
            engine.activate_scene_feature_ability(trainer, target, SCENE.STYLE_FEATURE, branch, ability)
        return engine, trainer, target

    def damage(self, engine, target, *, massive=True, protected=True):
        maximum = target.base_max_hp
        amount = (maximum + 1) // 2 if massive else (maximum - 1) // 2
        before = target.hp
        injuries = target.injuries
        with patch.object(STAMINA, "observe", wraps=STAMINA.observe) as observed:
            added = engine.take_damage(target, amount)
        markers = int(before > maximum / 2 >= before - amount)
        expected = markers + int(massive and not protected)
        self.assertEqual((target.hp, target.injuries - injuries, added),
                         (before - amount, expected, expected))
        if massive:
            observed.assert_called_once_with(engine, target, "massive_damage", amount=amount, maximum_hp=maximum)
        else:
            observed.assert_not_called()
        self.assertTrue(engine.validate_state()["valid"])

    def test_style_sturdy_native_damage_preserves_markers_threshold_and_stamina_observation(self):
        for ability, massive in (("옹골참", True), ("옹골참", False), ("위협", True)):
            with self.subTest(ability=ability, massive=massive):
                engine, trainer, target = self.style(ability)
                self.assertEqual(ABILITIES.known(target), ["ability/" + ability])
                self.assertFalse(engine.gm_prompts)
                self.damage(engine, target, massive=massive, protected=ability == "옹골참")

    def test_sturdy_switch_restore_scene_expiry_and_same_target_replacement_reach_damage(self):
        for boundary in ("recall_restore", "scene_expiry", "replacement"):
            with self.subTest(boundary=boundary):
                engine, trainer, target = self.style()
                if boundary == "recall_restore":
                    engine.gm.recall(target, reason="actual Style recipient switch out")
                    engine.gm.snapshot("sturdy-scene")
                    engine.end_scene([trainer])
                    engine.gm.restore("sturdy-scene", reason="restore actual granted Sturdy")
                    engine = load_engine(engine.r, json.loads(json.dumps(dump_engine(engine))))
                    actors = {actor.entity_id: actor for actor in engine.time_actors()}
                    trainer, target = actors[trainer.entity_id], actors[target.entity_id]
                    engine.gm.send_out(target, (1, 0), reason="actual Style recipient switch in")
                elif boundary == "scene_expiry":
                    engine.end_scene([trainer])
                    self.assertFalse(SCENE.records(target))
                else:
                    engine.start_of_turn(trainer)
                    engine.end_of_turn(trainer)
                    self.fixture.open_style_priority(engine, trainer, target)
                    engine.activate_scene_feature_ability(trainer, target, SCENE.STYLE_FEATURE, "강인함", "위협")
                    self.assertEqual(ABILITIES.known(target), ["ability/위협"])
                    self.assertEqual(len(SCENE.records(target)), 1)
                self.damage(engine, target, protected=boundary == "recall_restore")

    def test_native_selected_and_global_suppression_disable_sturdy_protection(self):
        transition_fixtures.AbilityTransitionTests.setUpClass()
        helper = transition_fixtures.AbilityTransitionTests()
        helper.setUp()
        engine, source, target = helper.e, helper.a, helper.t
        GRANTS.replace_baseline(engine, target, "abilities", ["옹골참"])
        engine.gm.choose_ability_transition(source, target, "move/위액", ability="옹골참",
                                            reason="actual Sturdy suppression choice")
        engine.use_move(source, target, "move/위액")
        self.assertIn("ability/옹골참", ABILITIES.known(target))
        self.assertFalse(ABILITIES.active(target, "ability/옹골참"))
        self.damage(engine, target, protected=False)
        engine, trainer, target = self.style()
        target.abilities_suppressed = True
        self.assertFalse(ABILITIES.active(target, "ability/옹골참"))
        self.damage(engine, target, protected=False)

    def test_unresolved_rule_ineligible_choice_and_late_native_failure_remain_atomic(self):
        for variant in ("unknown_rule", "extra_rule_field", "other_source", "ineligible", "late_failure"):
            with self.subTest(variant=variant):
                branch = "근사함" if variant == "other_source" else "강인함"
                engine, trainer, target = self.style(activate=False, branch=branch)
                ability = "옹골참"
                if variant in ("unknown_rule", "extra_rule_field", "other_source"):
                    if variant == "other_source":
                        ability = "스나이퍼"
                    rules = copy(engine.r)
                    rules.ability_effects = deepcopy(engine.r.ability_effects)
                    name = rules.selection.units["ability/스나이퍼-playtest"]["title"] if variant == "other_source" else ability
                    if variant == "unknown_rule":
                        rules.ability_effects[name].append({"type": "rule", "choice": "unresolved source choice"})
                    elif variant == "other_source":
                        rules.ability_effects[name].append({"type": "rule", "no_injury_from_massive_damage": True})
                    else:
                        rules.ability_effects[name][-1]["choice"] = "unresolved extra input"
                    engine.r = rules
                    for actor in engine.time_actors():
                        actor.r = rules
                    reason = "unresolved source input"
                elif variant == "ineligible":
                    ability = "승기"
                    reason = "outside its printed"
                else:
                    reason = "late native registration failure"
                original = EXT.register_ability_extras
                def register(staged, recipient, effects):
                    if variant == "other_source":
                        rule = next(effect for effect in effects if effect.get("no_injury_from_massive_damage") is True)
                        self.assertEqual(rule["_rule_id"], "ability/스나이퍼-playtest")
                    original(staged, recipient, effects)
                    if variant == "late_failure":
                        staged.rng.random()
                        raise ValueError(reason)
                with patch.object(EXT, "register_ability_extras", side_effect=register):
                    NATIVE.assert_rejected_unchanged(
                        engine,
                        lambda: engine.activate_scene_feature_ability(
                            trainer, target, SCENE.STYLE_FEATURE, branch, ability),
                        reason_pattern=reason,
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
