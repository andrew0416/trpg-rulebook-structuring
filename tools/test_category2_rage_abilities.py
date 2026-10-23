"""Native Rage ability queries shared by save and damage consumers."""
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from builder import build_trainer
from engine import Combatant, Engine, Rules
import feature_ability_grants as FEATURE_ABILITIES
import items
import rage_abilities as RAGE
import state_codec as CODEC
import state_grants as GRANTS


class RageAbilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="fantasy")

    def fixture(self, first_abilities=(), second_abilities=(), *, feats=(), choices=None):
        engine = Engine(self.rules, seed=67)

        def actor(name, abilities):
            spec = build_trainer(
                self.rules, name, 30,
                dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
                moves=[],
            )
            spec.update(
                classes=[], edges=[], feats=list(feats) if name == "rage-owner" else [],
                abilities=list(abilities), feature_choices=dict(choices or {}) if name == "rage-owner" else {},
            )
            return Combatant(self.rules, spec)

        first = actor("rage-owner", first_abilities)
        second = actor("rage-target", second_abilities)
        first.side, second.side = "party", "wild"
        engine.everyone = engine.gm.everyone = [first, second]
        for owner, abilities in ((first, first_abilities), (second, second_abilities)):
            for ability in abilities:
                engine.register_abilities_one(owner, ability)
        return engine, first, second

    def begin(self, engine, actor):
        engine.start_round(engine.gm.everyone)
        engine.start_of_turn(actor, initiative_count=20)

    def test_exact_native_registration_replaces_generic_prompt_and_modifier_projection(self):
        for ability_id, name in ((RAGE.ENDURING_RAGE, "불굴의격노"), (RAGE.WHITE_FLAME, "화이트플레임")):
            with self.subTest(ability=ability_id):
                engine, actor, _ = self.fixture([name])
                self.assertTrue(RAGE.registration(self.rules, ability_id))
                self.assertFalse(RAGE.registration(self.rules, "ability/대운"))
                self.assertIn(name, actor.spec[GRANTS.KEY]["ability_receipts"])
                self.assertFalse(engine.gm_prompts)
                self.assertEqual(actor.damage_reduction, 0)
                self.assertFalse(any(row.get("_ability") == name for row in actor.modifiers + actor.registry))

    def test_both_abilities_forbid_only_rage_end_save_without_rng(self):
        for name in ("불굴의격노", "화이트플레임"):
            with self.subTest(ability=name):
                engine, actor, _ = self.fixture([name])
                self.assertTrue(engine.apply_status(actor, "난동"))
                self.begin(engine, actor)
                rng = engine.rng.getstate()
                # The transaction runs on a staged Engine, so the class patch
                # proves that neither instance can consume the save roll.
                with patch.object(Engine, "d20", side_effect=AssertionError("Rage save must be skipped")) as roller:
                    engine.end_of_turn(actor)
                self.assertEqual(roller.call_count, 0)
                self.assertEqual(engine.rng.getstate(), rng)
                self.assertIn("난동", actor.conditions)
                self.assertTrue(RAGE.end_save_forbidden(actor, "난동"))
                self.assertFalse(RAGE.end_save_forbidden(actor, "혼란"))

    def test_suppression_restores_the_ordinary_rage_save(self):
        for name in ("불굴의격노", "화이트플레임"):
            with self.subTest(ability=name):
                engine, actor, _ = self.fixture([name])
                self.assertTrue(engine.apply_status(actor, "난동"))
                actor.abilities_suppressed = True
                self.begin(engine, actor)
                # end_of_turn validates on a staged Engine copy, so patch the
                # class boundary shared by the live and staged instances.
                with patch.object(Engine, "d20", return_value=20) as roller:
                    engine.end_of_turn(actor)
                self.assertEqual(roller.call_count, 1)
                self.assertNotIn("난동", actor.conditions)
                self.assertFalse(RAGE.end_save_forbidden(actor, "난동"))

    def test_white_flame_outgoing_bonus_is_dynamic_and_suppression_aware(self):
        engine, actor, target = self.fixture(["화이트플레임"])
        move = self.rules.move(self.rules.move_id("메가톤펀치"))
        plain = engine.roll_damage(actor, target, move, set_damage=True)
        self.assertEqual(RAGE.outgoing_damage_bonus(actor), 0)
        self.assertTrue(engine.apply_status(actor, "난동"))
        boosted = engine.roll_damage(actor, target, move, set_damage=True)
        self.assertEqual(boosted, plain + 5)
        self.assertEqual(RAGE.outgoing_damage_bonus(actor), 5)
        actor.abilities_suppressed = True
        self.assertEqual(engine.roll_damage(actor, target, move, set_damage=True), plain)
        actor.abilities_suppressed = False
        engine.cure_status(actor, "난동")
        self.assertEqual(engine.roll_damage(actor, target, move, set_damage=True), plain)

    def test_enduring_rage_incoming_reduction_uses_existing_defense_composition(self):
        engine, attacker, target = self.fixture((), ["불굴의격노"])
        move = self.rules.move(self.rules.move_id("메가톤펀치"))
        original = target.damage_reduction
        plain = engine.roll_damage(attacker, target, move, set_damage=True)
        self.assertTrue(engine.apply_status(target, "난동"))
        reduced = engine.roll_damage(attacker, target, move, set_damage=True)
        self.assertEqual(reduced, max(1, plain - 5))
        self.assertEqual(target.damage_reduction, original)
        self.assertEqual(RAGE.incoming_damage_reduction(target), 5)
        target.abilities_suppressed = True
        self.assertEqual(engine.roll_damage(attacker, target, move, set_damage=True), plain)
        self.assertEqual(target.damage_reduction, original)

    def test_enduring_rage_reduction_obeys_existing_ignore_damage_reduction_rule(self):
        engine, attacker, target = self.fixture((), ["불굴의격노"])
        ordinary = self.rules.move(self.rules.move_id("메가톤펀치"))
        ignoring = self.rules.move(self.rules.move_id("DD래리어트"))
        plain_ordinary = engine.roll_damage(attacker, target, ordinary, set_damage=True)
        plain_ignoring = engine.roll_damage(attacker, target, ignoring, set_damage=True)
        self.assertTrue(engine.apply_status(target, "난동"))
        self.assertEqual(
            engine.roll_damage(attacker, target, ordinary, set_damage=True),
            max(1, plain_ordinary - 5),
        )
        self.assertEqual(
            engine.roll_damage(attacker, target, ignoring, set_damage=True),
            plain_ignoring,
        )
        self.assertEqual(target.damage_reduction, 0)

    def test_feature_loss_removes_receipt_and_all_native_rage_queries(self):
        uid = "feat/분노의-힘"
        for choice in ("불굴의격노", "화이트플레임"):
            with self.subTest(choice=choice):
                engine, actor, _ = self.fixture(feats=[uid], choices={uid: [choice]})
                items.register_feats(engine, actor)
                self.assertIn(choice, actor.spec[GRANTS.KEY]["ability_receipts"])
                engine.apply_status(actor, "난동")
                actor.spec["feats"] = []
                items.register_feats(engine, actor)
                self.assertNotIn(choice, actor.abilities)
                self.assertNotIn(choice, actor.spec[GRANTS.KEY]["ability_receipts"])
                self.assertFalse(RAGE.end_save_forbidden(actor, "난동"))
                self.assertEqual(RAGE.outgoing_damage_bonus(actor), 0)
                self.assertEqual(RAGE.incoming_damage_reduction(actor), 0)

    def test_snapshot_and_json_restore_keep_exact_feature_choice_and_rage_queries(self):
        uid = "feat/분노의-힘"
        for choice, query in (("불굴의격노", RAGE.incoming_damage_reduction), ("화이트플레임", RAGE.outgoing_damage_bonus)):
            with self.subTest(choice=choice):
                engine, actor, _ = self.fixture(feats=[uid], choices={uid: [choice]})
                items.register_feats(engine, actor)
                engine.apply_status(actor, "난동")
                engine.gm.snapshot("native-rage-ability")
                actor.abilities_suppressed = True
                engine.cure_status(actor, "난동")
                engine.gm.restore("native-rage-ability", reason="restore native Rage ability")
                self.assertEqual(query(actor), 5)

                restored = CODEC.load_engine(
                    self.rules,
                    json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False)),
                )
                copy = next(value for value in restored.everyone if value.entity_id == actor.entity_id)
                self.assertEqual(query(copy), 5)
                row = copy.spec[GRANTS.KEY]["sources"]["feature:" + copy.entity_id + ":" + uid]
                self.assertEqual(row["feature_ability_selection"], "ability/" + choice)


if __name__ == "__main__":
    unittest.main()
