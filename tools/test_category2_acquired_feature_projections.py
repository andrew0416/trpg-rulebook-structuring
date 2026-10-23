"""Seventeen exact acquired-Feature projections through native consumers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from builder import build_trainer
from engine import Combatant, Engine, Rules
from state_codec import dump_engine, load_engine
import ability_transitions as ABILITIES
import acquired_feature_projections as PROJECTIONS
import encounter
import items
import state_grants as GRANTS


CASES = {
    "feat/파동의-힘": {"choices": ["배짱"]},
    "feat/안수": {"choices": ["축복의손길"]},
    "feat/느림-또는-안정": {"choices": ["애널라이즈"]},
    "feat/무리어미": {"parent_choice": "거미의 포용"},
    "feat/재봉사-마스터리": {"choices": ["매직가드"]},
    "feat/불타는-열정": {"choices": ["타오르는불꽃"]},
    "feat/돌풍의-속도": {"choices": ["기념"]},
    "feat/스산함": {"choices": ["프레셔"]},
    "feat/어머니-대지의-축복": {"choices": ["개미지옥"]},
    "feat/루미너스-오라": {"choices": ["스타라이트"]},
    "feat/물의-장막": {"choices": ["씻어내기"]},
    "feat/펄기아의-메이저-기프트-노마드": {},
    "feat/아이템-마스터리": {},
    "feat/지면돌출": {"choices": ["드릴라이너", "매그니튜드"]},
    "feat/구조이동": {"choices": ["지진", "대지의힘"]},
    "feat/널-에러": {},
    "feat/버그-셔플": {},
}


class AcquiredFeatureProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="all")
        cls.policy = json.loads((ROOT / PROJECTIONS.POLICY).read_text(encoding="utf-8"))

    def fixture(self, uid, case=None):
        case = CASES[uid] if case is None else case
        engine = Engine(self.rules, seed=173)
        spec = build_trainer(
            self.rules, "projection-owner", 30,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
            moves=[],
        )
        choices = {}
        if "choices" in case:
            choices[uid] = deepcopy(case["choices"])
        if "parent_choice" in case:
            choices["supp-fantasy/벌레-원소술사-무리군주"] = case["parent_choice"]
        spec.update(classes=[], edges=[], feats=[uid], abilities=[], feature_choices=choices)
        actor = Combatant(self.rules, spec)
        engine.everyone = engine.gm.everyone = [actor]
        return engine, actor

    @staticmethod
    def source(actor, uid):
        return "feature:" + actor.entity_id + ":" + uid

    def test_exact_seventeen_denominator_and_full_source_catalog_preflight(self):
        self.assertEqual(set(PROJECTIONS.clause_ids(self.rules)), {
            "input/ch04-trainer-classes.md:2791-2796",
            "input/ch04-trainer-classes.md:3103-3107",
            "FAN-097", "FAN-119", "FAN-145", "FAN-151", "FAN-157",
            "FAN-161", "FAN-173", "FAN-188", "FAN-213",
            "C2ADD/supp-blessings:1015", "ERRATA-004", "FAN-175", "FAN-176",
            "C2ADD/supp-polygon:1896", "C2ADD/supp-polygon:1922",
        })
        self.assertEqual(set(CASES), set(PROJECTIONS.sources(self.rules)))
        self.assertEqual(len(self.policy["abilities"]), 23)
        self.assertEqual(len(self.policy["moves"]), 13)
        self.assertEqual(self.policy["moves"]["내던지기"]["move_id"], "move/내던지기")
        fling = self.rules.move("move/내던지기")
        self.assertEqual((fling["eng"], fling["damage_base"], fling["mech_auto"]["held_item_damage"]),
                         ("Fling", "variable", True))

    def test_all_seventeen_project_to_native_consumers_and_revoke_by_owner(self):
        for uid, case in CASES.items():
            with self.subTest(source=uid):
                engine, actor = self.fixture(uid, case)
                expected = PROJECTIONS.plan(engine, actor, uid)
                self.assertEqual(items.register_feats(engine, actor), 1)
                self.assertEqual(items.register_feats(engine, actor), 0)
                source = self.source(actor, uid)
                row = actor.spec[GRANTS.KEY]["sources"][source]
                self.assertEqual(
                    (row["kind"], row["owner_id"], row["lifetime"], row["rule_id"], row[PROJECTIONS.TAG]),
                    ("feature", actor.entity_id, "while_owned", uid, 1),
                )
                self.assertEqual(row["projection_clause_id"], self.policy["rules"][uid]["clause_id"])
                self.assertEqual(row["projection_ability_ids"], expected["ability_ids"])
                self.assertEqual(row["projection_move_ids"], expected["move_ids"])
                if expected["ability_ids"]:
                    self.assertEqual(ABILITIES.known(actor), expected["ability_ids"])
                    for name in row["grants"]["abilities"]:
                        self.assertIn(name, actor.spec[GRANTS.KEY]["ability_receipts"])
                        self.assertTrue(self.rules.ability_effects[name])
                if expected["move_ids"]:
                    self.assertTrue(set(expected["move_ids"]).issubset(actor.moves))
                    self.assertTrue(set(expected["move_ids"]).issubset(encounter.usable_moves(engine, actor)))
                    self.assertTrue(all(self.rules.move(move_id) for move_id in expected["move_ids"]))
                GRANTS.revoke(actor, source, engine=engine)
                self.assertFalse(set(expected["ability_ids"]) & set(ABILITIES.known(actor)))
                self.assertFalse(set(expected["move_ids"]) & set(actor.moves))
                self.assertTrue(engine.validate_state()["valid"])

    def test_every_printed_ability_choice_resolves_an_exact_executable_identity(self):
        for uid, row in self.policy["rules"].items():
            if row["mode"] != "ability_choice":
                continue
            for printed in row["abilities"]:
                with self.subTest(source=uid, ability=printed):
                    engine, actor = self.fixture(uid, {"choices": [printed]})
                    items.register_feats(engine, actor)
                    ability_id = self.policy["abilities"][printed]["ability_id"]
                    self.assertEqual(ABILITIES.known(actor), [ability_id])
                    registration = PROJECTIONS.registration(self.rules, ability_id)
                    self.assertEqual(registration["source_id"], ability_id)
                    self.assertIn(registration["name"], self.rules.ability_effects)

    def test_rank_growth_downgrade_removal_and_independent_baselines(self):
        for uid, choices in (
            ("feat/파동의-힘", ["배짱", "파동바람"]),
            ("feat/어머니-대지의-축복", ["개미지옥", "피뢰침"]),
        ):
            with self.subTest(source=uid):
                engine, actor = self.fixture(uid, {"choices": [choices[0]]})
                baseline_id, baseline_name = PROJECTIONS._ability(self.rules, choices[0])
                GRANTS.set_baseline(actor, "abilities", [baseline_name])
                items.register_feats(engine, actor)
                actor.spec["feat_ranks"] = {uid: 2}
                actor.spec["feature_choices"][uid] = choices
                items.register_feats(engine, actor)
                ids = [PROJECTIONS._ability(self.rules, value)[0] for value in choices]
                self.assertEqual(ABILITIES.known(actor), ids)
                actor.spec["feat_ranks"][uid] = 1
                actor.spec["feature_choices"][uid] = [choices[0]]
                items.register_feats(engine, actor)
                self.assertEqual(ABILITIES.known(actor), [baseline_id])
                actor.spec["feats"] = []
                items.register_feats(engine, actor)
                self.assertEqual(ABILITIES.known(actor), [baseline_id])

    def test_fixed_nomad_ability_and_move_commit_as_one_source(self):
        uid = "feat/펄기아의-메이저-기프트-노마드"
        engine, actor = self.fixture(uid)
        items.register_feats(engine, actor)
        row = actor.spec[GRANTS.KEY]["sources"][self.source(actor, uid)]
        self.assertEqual(row["projection_ability_ids"], ["ability/트랜스포터-playtest"])
        self.assertEqual(row["projection_move_ids"], ["move/순간이동"])
        self.assertIn("move/순간이동", encounter.usable_moves(engine, actor))

    def test_snapshot_json_restore_then_owner_loss_reconciles_every_case(self):
        for uid, case in CASES.items():
            with self.subTest(source=uid):
                engine, actor = self.fixture(uid, case)
                expected = PROJECTIONS.plan(engine, actor, uid)
                items.register_feats(engine, actor)
                engine.gm.snapshot("acquired-projection")
                GRANTS.revoke(actor, self.source(actor, uid), engine=engine)
                engine.gm.restore("acquired-projection", reason="restore acquired Feature projection")
                restored = load_engine(self.rules, json.loads(json.dumps(dump_engine(engine), ensure_ascii=False)))
                copy = restored.everyone[0]
                self.assertEqual(ABILITIES.known(copy), expected["ability_ids"])
                self.assertTrue(set(expected["move_ids"]).issubset(copy.moves))
                copy.spec["feats"] = []
                items.register_feats(restored, copy)
                self.assertFalse(set(expected["ability_ids"]) & set(ABILITIES.known(copy)))
                self.assertFalse(set(expected["move_ids"]) & set(copy.moves))

    def test_invalid_last_source_fails_entire_multi_source_batch_atomically(self):
        engine, actor = self.fixture("feat/파동의-힘")
        actor.spec["feats"] = list(CASES)
        actor.spec["feature_choices"] = {}
        for uid, case in CASES.items():
            if "choices" in case:
                actor.spec["feature_choices"][uid] = deepcopy(case["choices"])
            if "parent_choice" in case:
                actor.spec["feature_choices"]["supp-fantasy/벌레-원소술사-무리군주"] = case["parent_choice"]
        actor.spec["feature_choices"]["feat/구조이동"] = ["지진", "맹독"]
        before = deepcopy((actor.spec, actor.abilities, actor.moves, engine.rng.getstate(), engine.log_lines))
        with self.assertRaisesRegex(ValueError, "outside its printed domain"):
            items.register_feats(engine, actor)
        self.assertEqual((actor.spec, actor.abilities, actor.moves, engine.rng.getstate(), engine.log_lines), before)

    def test_choice_replacement_and_duplicate_aliases_fail_without_mutation(self):
        uid = "feat/루미너스-오라"
        engine, actor = self.fixture(uid)
        items.register_feats(engine, actor)
        actor.spec["feature_choices"][uid] = ["노을"]
        before = deepcopy((actor.spec, actor.abilities, actor.registry, actor.modifiers, engine.rng.getstate()))
        with self.assertRaisesRegex(ValueError, "silently replaced"):
            items.register_feats(engine, actor)
        self.assertEqual((actor.spec, actor.abilities, actor.registry, actor.modifiers, engine.rng.getstate()), before)

        engine, actor = self.fixture(uid)
        actor.spec["feats"] = [uid, self.rules.selection.units[uid]["title"]]
        before = deepcopy(actor.spec)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            items.register_feats(engine, actor)
        self.assertEqual(actor.spec, before)


if __name__ == "__main__":
    unittest.main()
