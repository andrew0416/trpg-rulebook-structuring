"""Nine scene ability-grant obligations through one policy executor."""
from copy import copy, deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
from state_codec import dump_engine, load_engine
from ruleset import RuleSelection
import ability_transitions as ABILITIES
import action_points as AP
import items
import priority_limited as PRIORITY
import scene_feature_ability_grants as SCENE
import state_grants as GRANTS


STAT_PRIOR = ("feat/스탯-링크", "feat/스탯-훈련", "feat/스탯-메뉴버")
ROW_CASES = (
    ("atk", "오기", "C2CSV/input/db/feats.csv:R198:main"),
    ("def", "전투무장", "C2CSV/input/db/feats.csv:R199:main"),
    ("spa", "승기", "C2CSV/input/db/feats.csv:R200:main"),
    ("spd", "강내성", "C2CSV/input/db/feats.csv:R201:main"),
    ("spe", "선봉", "C2CSV/input/db/feats.csv:R202:main"),
)


class SceneFeatureAbilityGrantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="all")
        cls.policy = json.loads((ROOT / SCENE.POLICY).read_text(encoding="utf-8"))

    def pokemon(self, trainer, name, *, poffins=()):
        spec = build_pokemon(trainer.r, "이상해씨", 30, name, abilities=[], moves=[])
        spec.update(trainer_id=trainer.entity_id, poffins=list(poffins))
        return Combatant(trainer.r, spec)

    def source_rules(self, rules, authority):
        if authority not in ("book", "csv"):
            raise ValueError("explicit Book or CSV source required")
        selected = copy(rules)
        units = deepcopy(list(rules.selection.units.values()))
        if authority == "csv":
            definition = next(row for row in self.policy["features"][SCENE.STAT_FEATURE]
                              if row["source"]["file"] == "input/db/feats.csv")
            parent = rules.selection.units[definition["values"]["parent_class"]]
            for unit in units:
                if unit["id"] == SCENE.STAT_FEATURE:
                    # RuleSelection preserves explicit catalog ancestry. The
                    # CSV definition supplies its own parent; do not borrow
                    # the Book source's path or discard the acquired guard.
                    unit["source"] = {"file": definition["source"]["file"].removeprefix("input/"),
                                      "sha256": definition["source"]["sha256"],
                                      **deepcopy(definition["locator"]), "path": [parent["title"]]}
        selected.selection = RuleSelection(selected.ruleset, units)
        selected.selection.dependencies = deepcopy(rules.selection.dependencies)
        return selected

    def stat_fixture(self, branch="atk", *, baseline=(), authority="csv", rules=None):
        rules = self.source_rules(self.rules if rules is None else rules, authority)
        engine = Engine(rules, seed=198)
        feats = [*STAT_PRIOR, SCENE.STAT_FEATURE]
        spec = build_trainer(
            rules, "stat-owner", 30,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
            skills={"명령": 5, "집중": 5},
        )
        spec.update(
            classes=["class/스탯-에이스"], feats=feats, abilities=list(baseline),
            feature_choices={"class/스탯-에이스": [branch], **{uid: [branch] for uid in feats}},
        )
        trainer = Combatant(rules, spec)
        target = self.pokemon(trainer, "stat-target")
        if baseline:
            GRANTS.set_baseline(target, "abilities", list(baseline))
        engine.everyone = engine.gm.everyone = [trainer, target]
        engine.time_actors(engine.everyone)
        return engine, trainer, target

    def style_fixture(self):
        engine = Engine(self.rules, seed=205)
        spec = build_trainer(
            self.rules, "style-owner", 30,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
            skills={name: 6 for name in ("명령", "매력", "직감", "교활", "협박")},
        )
        spec.update(
            classes=["class/스타일-전문가"],
            feats=["feat/근사한-행위", "feat/근사함의-규칙", SCENE.STYLE_FEATURE],
            feat_ranks={"feat/근사한-행위": 2}, abilities=[],
            feature_choices={"class/스타일-전문가": ["근사함"], SCENE.STYLE_FEATURE: ["근사함"]},
        )
        trainer = Combatant(self.rules, spec)
        pokemon = [self.pokemon(trainer, "style-target-" + str(index), poffins=["근사함"] * 3)
                   for index in range(3)]
        engine.everyone = engine.gm.everyone = [trainer, *pokemon]
        engine.time_actors(engine.everyone)
        return engine, trainer, pokemon

    def open_stat_turn(self, engine, trainer):
        engine.start_round(engine.everyone)
        engine.start_of_turn(trainer)

    def open_style_priority(self, engine, trainer, target):
        engine.start_round(engine.everyone)
        engine.at_initiative_count(30)
        engine.gm.observe_sensory_environment(
            trainer, target, paths={"auditory": True}, present=True,
            reason="observed audible Style Entrainment path",
        )

    def snapshot(self, engine, trainer, target):
        return deepcopy((trainer.spec, trainer.custom_conditions, getattr(trainer, "budget", None),
                         target.spec, target.abilities, target.registry, target.modifiers,
                         engine.log_lines, engine.rng.getstate()))

    def test_exact_nine_obligations_and_every_printed_choice_have_native_executable_identities(self):
        self.assertEqual(set(SCENE.completion_clause_ids(self.rules)), {
            "C2CSV/input/db/feats.csv:R197:main",
            "C2CSV/input/db/feats.csv:R198:main", "C2CSV/input/db/feats.csv:R199:main",
            "C2CSV/input/db/feats.csv:R200:main", "C2CSV/input/db/feats.csv:R201:main",
            "C2CSV/input/db/feats.csv:R202:main", "C2CSV/input/db/feats.csv:R205:main",
            "C04-048", "C04-051",
        })
        checked = 0
        for definitions in self.policy["features"].values():
            feature = next(row["values"] for row in definitions if row["source"]["file"] == "input/db/feats.csv")
            for declaration in feature["branches"].values():
                for printed, expected in declaration["abilities"].items():
                    with self.subTest(ability=printed):
                        _, ability_id, name = SCENE._ability(self.rules, declaration, printed)
                        self.assertEqual(ability_id, expected)
                        self.assertTrue(self.rules.ability_effects[name])
                        checked += 1
        self.assertEqual(checked, 20)

    def test_table_driven_six_activation_rows_use_one_native_consumer_path(self):
        for branch, ability, clause in ROW_CASES:
            with self.subTest(clause=clause):
                engine, trainer, target = self.stat_fixture(branch)
                self.open_stat_turn(engine, trainer)
                before_ap = AP.available(trainer)
                result = engine.activate_scene_feature_ability(
                    trainer, target, SCENE.STAT_FEATURE, branch, ability,
                )
                self.assertEqual((result["clause_id"], result["action"], result["priority_limited"]),
                                 (clause, "swift", False))
                self.assertEqual(ABILITIES.known(target), [result["ability_id"]])
                self.assertEqual((AP.available(trainer), trainer.budget["swift"]), (before_ap - 1, 0))
                self.assertEqual(SCENE.records(target)[0]["replacement_scope"], "same_family_same_target")
        engine, trainer, pokemon = self.style_fixture()
        target = pokemon[0]
        self.open_style_priority(engine, trainer, target)
        result = engine.activate_scene_feature_ability(
            trainer, target, SCENE.STYLE_FEATURE, "근사함", "오기",
        )
        self.assertEqual((result["clause_id"], result["action"], result["priority_limited"]),
                         ("C04-051", "swift", True))
        self.assertEqual(ABILITIES.known(target), ["ability/오기"])

    def test_book_and_csv_bind_distinct_values_to_actual_native_action_timing(self):
        # Cold parsing retains both known definitions, but only the selected
        # edition may become a current source/evidence dependency. Unrelated
        # acquired prerequisites are outside this policy-layer assertion.
        for authority, unused in (("book", "input/db/feats.csv"),
                                  ("csv", "input/ch04-trainer-classes.md")):
            with self.subTest(cold_policy=authority):
                rules = self.source_rules(Rules(str(ROOT), ruleset="all"), authority)
                vars(rules).pop("_scene_feature_ability_grant_policy", None)
                if authority == "csv":
                    self.assertEqual(rules.selection.units[SCENE.STAT_FEATURE]["source"], {
                        "file": "db/feats.csv", "record_span": [197, 202],
                        "sha256": self.policy["source_files"]["input/db/feats.csv"],
                        "path": ["스탯 에이스"],
                    })
                native_bytes, native_open = Path.read_bytes, Path.open
                reads = []
                def changed_unselected(path):
                    reads.append(path)
                    return native_bytes(path) + (b"\nchanged edition" if path == ROOT / unused else b"")
                def selected_open(path, *args, **kwargs):
                    if unused.endswith(".csv") and path == ROOT / unused:
                        raise AssertionError("Book policy must not parse unselected CSV rows")
                    return native_open(path, *args, **kwargs)
                with patch.object(Path, "read_bytes", changed_unselected), patch.object(Path, "open", selected_open):
                    definitions = SCENE._policy(rules)["features"][SCENE.STAT_FEATURE]
                    binding = rules.bind_source_policy(SCENE.STAT_FEATURE, definitions)
                    SCENE._selected_evidence(rules, binding["definition"])
                    self.assertIs(binding["definition"]["values"]["priority_limited"], authority == "book")
                self.assertNotIn(ROOT / unused, reads)
                selected = ROOT / binding["definition"]["source"]["file"]
                self.assertIn(selected, reads)
                def changed_selected(path):
                    return native_bytes(path) + (b"\nchanged selected edition" if path == selected else b"")
                # A warm declaration cache cannot bypass selected freshness.
                with patch.object(Path, "read_bytes", changed_selected):
                    with self.assertRaisesRegex(ValueError, "source changed"):
                        rules.bind_source_policy(SCENE.STAT_FEATURE, definitions)
                if authority == "csv":
                    for field in ("name", "catalog"):
                        declaration = deepcopy(binding["definition"])
                        branch = declaration["values"]["branches"]["atk"]
                        if field == "name":
                            branch["name"] = "wrong physical row name"
                        else:
                            branch["abilities"]["오기"] = "ability/unregistered-policy-choice"
                        with self.subTest(selected_csv_evidence=field), self.assertRaisesRegex(ValueError, "CSV row|catalog identity"):
                            SCENE._selected_evidence(rules, declaration)
        for authority in ("book", "csv"):
            with self.subTest(authority=authority):
                engine, trainer, target = self.stat_fixture(authority=authority)
                self.open_style_priority(engine, trainer, target)
                before_ap = AP.available(trainer)
                if authority == "csv":
                    before = self.snapshot(engine, trainer, target)
                    with self.assertRaisesRegex(ValueError, "Swift action"):
                        engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "atk", "오기")
                    self.assertEqual(self.snapshot(engine, trainer, target), before)
                    engine.start_of_turn(trainer)
                result = engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "atk", "오기")
                if authority == "book":
                    self.assertIs(result["priority_limited"], True)
                    self.assertEqual(result["clause_id"], "C04-048")
                    self.assertEqual(trainer.pending_action_loss, {"swift": 1})
                    engine.start_of_turn(trainer)
                    self.assertEqual(PRIORITY.records(trainer)[0]["payment"]["phase"], "paid")
                else:
                    self.assertIs(result["priority_limited"], False)
                    self.assertEqual(result["clause_id"], "C2CSV/input/db/feats.csv:R198:main")
                    self.assertFalse(PRIORITY.records(trainer))
                self.assertEqual(trainer.budget, {"standard": 1, "shift": 1, "swift": 0})
                self.assertEqual(AP.available(trainer), before_ap - 1)
                self.assertEqual(ABILITIES.known(target), ["ability/오기"])

    def test_historical_book_producer_survives_new_csv_selection_and_both_restores(self):
        engine, trainer, target = self.stat_fixture(authority="book", rules=Rules(str(ROOT), ruleset="all"))
        self.open_style_priority(engine, trainer, target)
        engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "atk", "오기")
        engine.start_of_turn(trainer)
        trainer.r.selection = self.source_rules(engine.r, "csv").selection
        current = engine.r.bind_source_policy(SCENE.STAT_FEATURE, self.policy["features"][SCENE.STAT_FEATURE])
        self.assertIs(current["definition"]["values"]["priority_limited"], False)
        self.assertIs(SCENE.records(target)[0]["source_policy_binding"]["definition"]["values"]["priority_limited"], True)
        producing = deepcopy(SCENE.records(target)[0]["source_policy_binding"])
        engine.gm.snapshot("producing-policy")
        trainer.spec["feats"].remove(SCENE.STAT_FEATURE)
        self.assertEqual(SCENE.reconcile_owner(engine, trainer), 1)
        self.assertFalse(SCENE.records(target))
        engine.gm.restore("producing-policy", reason="restore Book producer under current CSV authority")
        actors = {actor.entity_id: actor for actor in engine.time_actors()}
        self.assertIs(actors[trainer.entity_id], trainer)
        self.assertIs(actors[target.entity_id], target)
        row = SCENE.records(actors[target.entity_id])[0]
        self.assertEqual(row["clause_id"], "C04-048")
        self.assertEqual(row["source_policy_binding"], producing)
        self.assertIs(row["source_policy_binding"]["definition"]["values"]["priority_limited"], True)
        self.assertEqual(ABILITIES.known(actors[target.entity_id]), ["ability/오기"])
        current = engine.r.bind_source_policy(SCENE.STAT_FEATURE, self.policy["features"][SCENE.STAT_FEATURE])
        self.assertEqual(current["definition"]["source"]["file"], "input/db/feats.csv")
        self.assertIs(current["definition"]["values"]["priority_limited"], False)
        fresh = self.source_rules(Rules(str(ROOT), ruleset="all"), "csv")
        restored = load_engine(fresh, json.loads(json.dumps(dump_engine(engine), ensure_ascii=False)))
        pokemon = next(actor for actor in restored.time_actors() if actor.entity_id == target.entity_id)
        row = SCENE.records(pokemon)[0]
        self.assertEqual(row["clause_id"], "C04-048")
        self.assertIs(row["source_policy_binding"]["definition"]["values"]["priority_limited"], True)
        self.assertEqual(ABILITIES.known(pokemon), ["ability/오기"])

    def test_fresh_restore_rejects_semantic_value_and_fingerprint_tampering(self):
        engine, trainer, target = self.stat_fixture(authority="book", rules=Rules(str(ROOT), ruleset="all"))
        self.open_style_priority(engine, trainer, target)
        engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "atk", "오기")
        payload = json.loads(json.dumps(dump_engine(engine), ensure_ascii=False))
        # Change the encoded policy values and their matching public hash only
        # after the native producer has passed dump_engine's validation.
        def mapping(reference):
            return dict(payload["nodes"][reference["$ref"]]["items"])
        actor = next(node for node in payload["nodes"].values()
                     if node["kind"] == "actor" and node["entity_id"] == target.entity_id)
        spec = mapping(mapping(actor["attrs"])["spec"])
        sources = mapping(mapping(spec[GRANTS.KEY])["sources"])
        row = mapping(sources[SCENE.records(target)[0]["source"]])
        binding = payload["nodes"][row["source_policy_binding"]["$ref"]]
        definition_ref = dict(binding["items"])["definition"]["$ref"]
        definition = payload["nodes"][definition_ref]
        values_ref = dict(definition["items"])["values"]["$ref"]
        values = payload["nodes"][values_ref]
        next(pair for pair in values["items"] if pair[0] == "priority_limited")[1] = False
        import root_resolution as R
        forged = deepcopy(SCENE.records(target)[0]["source_policy_binding"]["definition"])
        forged["values"]["priority_limited"] = False
        next(pair for pair in binding["items"] if pair[0] == "definition_hash")[1] = R.fingerprint(forged)
        fresh = self.source_rules(Rules(str(ROOT), ruleset="all"), "book")
        with self.assertRaisesRegex(ValueError, "known producing source policy"):
            load_engine(fresh, payload)

    def test_same_family_replacement_switch_persistence_and_scene_expiry(self):
        engine, trainer, target = self.stat_fixture("atk", baseline=("오기",))
        first = engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "atk", "오기")
        second = engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "atk", "우격다짐")
        self.assertEqual(len(SCENE.records(target)), 1)
        self.assertEqual(SCENE.records(target)[0]["ability_id"], "ability/우격다짐-playtest")
        self.assertIn("ability/오기", ABILITIES.known(target))
        self.assertNotEqual(first["ability_id"], second["ability_id"])
        engine.gm.recall(target, reason="observed switch out")
        self.assertFalse(target.on_field)
        self.assertIn("ability/우격다짐-playtest", ABILITIES.known(target))
        engine.gm.send_out(target, (1, 0), reason="observed switch in")
        self.assertIn("ability/우격다짐-playtest", ABILITIES.known(target))
        engine.gm.recall(target, reason="observed final switch out before scene boundary")
        engine.end_scene([trainer])
        self.assertEqual(ABILITIES.known(target), ["ability/오기"])
        self.assertFalse(SCENE.records(target))

    def test_source_only_removal_and_gm_snapshot_restore(self):
        engine, trainer, target = self.stat_fixture("spa", baseline=("오기",))
        engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "spa", "승기")
        engine.gm.snapshot("scene-grant")
        trainer.spec["feats"].remove(SCENE.STAT_FEATURE)
        removed = SCENE.reconcile_owner(engine, trainer)
        self.assertEqual(removed, 1)
        self.assertEqual(ABILITIES.known(target), ["ability/오기"])
        engine.gm.restore("scene-grant", reason="restore exact scene ability grant")
        self.assertEqual(set(ABILITIES.known(target)), {"ability/오기", "ability/승기"})
        self.assertEqual(len(SCENE.records(target)), 1)

    def test_json_restore_retains_receipt_then_source_reconcile_removes_only_it(self):
        engine, trainer, target = self.stat_fixture("spe", baseline=("오기",))
        engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "spe", "가속")
        restored = load_engine(engine.r, json.loads(json.dumps(dump_engine(engine), ensure_ascii=False)))
        index = {actor.entity_id: actor for actor in restored.everyone}
        owner, pokemon = index[trainer.entity_id], index[target.entity_id]
        self.assertEqual(set(ABILITIES.known(pokemon)), {"ability/오기", "ability/가속"})
        owner.spec["feats"].remove(SCENE.STAT_FEATURE)
        self.assertEqual(SCENE.reconcile_owner(restored, owner), 1)
        self.assertEqual(ABILITIES.known(pokemon), ["ability/오기"])
        self.assertTrue(restored.validate_state()["valid"])

    def test_invalid_choice_ap_and_swift_payment_are_atomic(self):
        engine, trainer, target = self.stat_fixture("def")
        before = self.snapshot(engine, trainer, target)
        with self.assertRaisesRegex(ValueError, "outside its printed"):
            engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "def", "승기")
        self.assertEqual(self.snapshot(engine, trainer, target), before)

        trainer.spec["ap_spent"] = AP.maximum(trainer)
        before = self.snapshot(engine, trainer, target)
        with self.assertRaisesRegex(ValueError, "available AP"):
            engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "def", "전투무장")
        self.assertEqual(self.snapshot(engine, trainer, target), before)

        engine, trainer, target = self.stat_fixture("def")
        self.open_stat_turn(engine, trainer)
        trainer.budget.update(standard=0, swift=0)
        before = self.snapshot(engine, trainer, target)
        with self.assertRaisesRegex(ValueError, "Swift action"):
            engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "def", "전투무장")
        self.assertEqual(self.snapshot(engine, trainer, target), before)

    def test_style_priority_limited_reserves_and_pays_swift_without_expiring_grant(self):
        engine, trainer, pokemon = self.style_fixture()
        target = pokemon[0]
        self.open_style_priority(engine, trainer, target)
        before_ap = AP.available(trainer)
        engine.activate_scene_feature_ability(
            trainer, target, SCENE.STYLE_FEATURE, "근사함", "스나이퍼",
        )
        receipt = PRIORITY.records(trainer)[0]
        self.assertEqual((trainer.pending_action_loss, receipt["payment"]),
                         ({"swift": 1}, {"declared": "swift", "funded": {"swift": 1}, "phase": "reserved"}))
        self.assertEqual(AP.available(trainer), before_ap - 1)
        self.assertTrue(PRIORITY.validate(trainer))
        engine.start_of_turn(trainer)
        self.assertEqual(trainer.budget, {"standard": 1, "shift": 1, "swift": 0})
        self.assertEqual(PRIORITY.records(trainer)[0]["payment"]["phase"], "paid")
        self.assertEqual(ABILITIES.known(target), ["ability/스나이퍼-playtest"])
        self.assertTrue(engine.validate_state()["valid"])

    def test_items_registration_reconciles_lost_producer(self):
        engine, trainer, target = self.stat_fixture("atk")
        engine.activate_scene_feature_ability(trainer, target, SCENE.STAT_FEATURE, "atk", "오기")
        trainer.spec["feats"].remove(SCENE.STAT_FEATURE)
        self.assertGreaterEqual(items.register_feats(engine, trainer, [target]), 1)
        self.assertFalse(SCENE.records(target))

    def test_public_activation_keeps_actual_actor_owner_source_and_branch_guards(self):
        for variant in ("unregistered", "wrong_owner", "unknown_source", "unacquired_branch", "lost_source"):
            with self.subTest(variant=variant):
                engine, trainer, target = self.stat_fixture("atk")
                source, branch = SCENE.STAT_FEATURE, "atk"
                if variant == "unregistered":
                    target = self.pokemon(trainer, "not a registered world actor")
                elif variant == "wrong_owner":
                    target.spec["trainer_id"] = "another-trainer"
                elif variant == "unknown_source":
                    source = "feat/스탯-훈련"
                elif variant == "unacquired_branch":
                    branch = "spa"
                else:
                    trainer.spec["feats"].remove(SCENE.STAT_FEATURE)
                before = self.snapshot(engine, trainer, target)
                with self.assertRaises(ValueError):
                    engine.activate_scene_feature_ability(trainer, target, source, branch, "오기")
                self.assertEqual(self.snapshot(engine, trainer, target), before)

    def test_style_replacement_is_target_local_and_public_scene_expires_recalled_targets(self):
        engine, trainer, pokemon = self.style_fixture()
        target, other = pokemon[:2]
        GRANTS.set_baseline(target, "abilities", ["승기"])
        for recipient, ability in ((target, "오기"), (target, "스나이퍼"), (other, "오기")):
            self.open_style_priority(engine, trainer, recipient)
            result = engine.activate_scene_feature_ability(
                trainer, recipient, SCENE.STYLE_FEATURE, "근사함", ability,
            )
            self.assertEqual((result["owner_id"], result["target_id"]),
                             (trainer.entity_id, recipient.entity_id))
            engine.start_of_turn(trainer)
            engine.end_of_turn(trainer)
        self.assertEqual(set(ABILITIES.known(target)), {"ability/승기", "ability/스나이퍼-playtest"})
        self.assertEqual(ABILITIES.known(other), ["ability/오기"])
        self.assertEqual((len(SCENE.records(target)), len(SCENE.records(other))), (1, 1))
        engine.gm.recall(target, reason="observed Style target switch out")
        self.assertIn("ability/스나이퍼-playtest", ABILITIES.known(target))
        restored = load_engine(self.rules, json.loads(json.dumps(dump_engine(engine), ensure_ascii=False)))
        index = {actor.entity_id: actor for actor in restored.time_actors()}
        owner, target, other = (index[actor.entity_id] for actor in (trainer, target, other))
        restored.end_scene([owner])
        self.assertEqual(ABILITIES.known(target), ["ability/승기"])
        self.assertFalse(ABILITIES.known(other))
        self.assertFalse(SCENE.records(target) or SCENE.records(other))
        self.assertTrue(restored.validate_state()["valid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
