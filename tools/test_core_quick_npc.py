"""Quick NPC adoption through actual native skill, feature and combat owners."""
from copy import copy, deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from engine import Rules, Engine, Combatant
import acquired_features as ACQUIRED
import builder
import partial_entities as PARTIAL
import quick_npc as NPC
import state_codec as CODEC
import state_fields as F
import trainer_feature_acquisition as FEATURES
import items as ITEMS
import state_grants as GRANTS
import static_feature_state_grants as STATIC


class QuickNPCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")

    def setUp(self):
        self.engine = Engine(self.rules, seed=1634)
        self.engine.everyone = []
        self.engine.gm.everyone = []

    def allocation(self, level=15, points=20, focus="mixed"):
        initial = dict.fromkeys(F.STATS, 0); initial["hp"] = 5; initial["def"] = 5
        growth = dict.fromkeys(F.STATS, 0); growth["spe"] = points
        return {"focus": focus, "growth_points": points, "initial": initial, "growth": growth,
                "reason": "GM chooses a mobile guide between the two printed extremes"}

    def binding(self, field, **options):
        return {"type": "integer", "authority": "state", "question": "Actual proposed NPC prerequisite",
                "binding": {"subject": "actor", "field": field, **options}}

    def minimum(self, name, value):
        return {"op": "ge", "left": {"$input": name}, "right": value}

    def policy(self, uid, bindings, conditions):
        printed = NPC.requirement_source(self.rules, uid)
        inputs = {"requirements_reviewed": {"type": "boolean", "authority": "gm",
                  "question": "Does this interpretation cover this complete printed prerequisite?"}, **bindings}
        return {"policy": {"schema": 1, "id": "example/quick-npc-prerequisite/" + uid,
                "variants": [{"rule_id": uid, "source": printed["source"],
                    "values": {"source_text": printed["source_text"], "requirements_reviewed": True},
                    "inputs": inputs, "when": {"all": [{"$input": "requirements_reviewed"}, *conditions]}}]},
                "decisions": {"requirements_reviewed": {"value": True,
                    "reason": "GM adopts these actual skills and required owned sources for the printed prerequisite"}}}

    def options(self):
        # Two Rogue Skills at Adept satisfy both the class and Unexpected Attacks.
        combat = self.allocation()
        combat["growth"].update(atk=1, spe=19)
        return {"role": "a discreet wilderness guide who also repairs Poké Balls",
                "level_treatment": {"very_low_level": False, "reason": "experienced recurring guide, level 15"},
                "classes": ["class/로그"], "feats": ["feat/불시의-공격"],
                "edges": ["edge/몬스터볼", "edge/몬스터볼-수리"],
                "skills": {"곡예": 4, "은신": 4, "기술학": 5},
                "combat": combat,
                "requirements": {
                    "class/로그": self.policy("class/로그",
                        {"acrobatics": self.binding("skill_rank", skill="곡예"), "stealth": self.binding("skill_rank", skill="은신")},
                        [self.minimum("acrobatics", 3), self.minimum("stealth", 3)]),
                    "feat/불시의-공격": self.policy("feat/불시의-공격",
                        {"rogue": self.binding("owned_rule_count", rule_id="class/로그"),
                         "acrobatics": self.binding("skill_rank", skill="곡예"), "stealth": self.binding("skill_rank", skill="은신")},
                        [self.minimum("rogue", 1), self.minimum("acrobatics", 4), self.minimum("stealth", 4)]),
                    "edge/몬스터볼": self.policy("edge/몬스터볼", {"tech": self.binding("skill_rank", skill="기술학")},
                        [self.minimum("tech", 3)]),
                    "edge/몬스터볼-수리": self.policy("edge/몬스터볼-수리",
                        {"basic_balls": self.binding("owned_rule_count", rule_id="edge/몬스터볼")}, [self.minimum("basic_balls", 1)])}}

    def martial_options(self):
        options = self.options()
        options.update(classes=[FEATURES.MARTIAL_ARTIST], feats=["feat/무술-훈련"], edges=["edge/기본-무술"],
                       skills={"전투": 4}, feature_choices={"feat/무술-훈련": [["마하펀치", "두번차기"]]},
                       native_acquisitions={FEATURES.MARTIAL_ARTIST: {"acquisition_request_id": "quick-martial-style",
                                                                  "selected_ability": "ability/철주먹"}})
        options["requirements"] = {
            FEATURES.MARTIAL_ARTIST: self.policy(FEATURES.MARTIAL_ARTIST,
                {"combat": self.binding("skill_rank", skill="전투"), "basic": self.binding("owned_rule_count", rule_id="edge/기본-무술")},
                [self.minimum("combat", 3), self.minimum("basic", 1)]),
            "edge/기본-무술": self.policy("edge/기본-무술", {"combat": self.binding("skill_rank", skill="전투")},
                [self.minimum("combat", 3)]),
            "feat/무술-훈련": self.policy("feat/무술-훈련", {"martial": self.binding("owned_rule_count", rule_id=FEATURES.MARTIAL_ARTIST)},
                [self.minimum("martial", 1)])}
        return options

    def test_source_reader_keeps_actual_class_skill_and_required_edge_text(self):
        self.assertIn("초보 랭크의 곡예, 육상, 은신 중 둘", NPC.requirement_source(self.rules, "class/로그")["source_text"])
        self.assertIn("몬스터볼 혹은 규토리 볼", NPC.requirement_source(self.rules, "edge/몬스터볼-수리")["source_text"])
        # The existing class extraction omits Survivalist's prerequisite; actual
        # current source still exposes it for the GM, rather than treating None as no condition.
        self.assertIn("초보 생존", NPC.requirement_source(self.rules, "class/생존가")["source_text"])

    def test_role_selected_build_reaches_native_feature_moves_skills_and_combat_stats(self):
        spec = builder.build_quick_npc(self.rules, "guide", 15, **self.options())
        self.assertEqual(spec["stats"], NPC.combat_stats(15, self.options()["combat"]))
        actor = NPC.create(self.engine, "guide", 15, **self.options())
        self.assertEqual(actor.spec["classes"], ["class/로그"])
        self.assertEqual(actor.spec["feats"], ["feat/불시의-공격"])
        self.assertTrue({self.rules.move_id(name) for name in ("속여때리기", "도둑질", "따라가때리기", "기습")} <= set(actor.moves))
        self.assertEqual(self.engine.skill_roll(actor, "기술학", fixed=[3] * 5).total, 15)
        self.assertEqual(actor.stats, {"hp": 15, "atk": 6, "def": 10, "spa": 5, "spd": 5, "spe": 24})
        self.assertEqual(actor.max_hp, 85)
        self.engine.take_damage(actor, 7)
        self.assertEqual(actor.hp, 78)
        self.assertEqual(actor.spec[NPC.KEY]["role"], self.options()["role"])
        self.assertTrue(actor.spec[NPC.KEY]["pc_acquisition_exception"])
        self.assertFalse(actor._state_origin["creation_legality_certified"])
        self.assertNotIn("trainer_entitlements", actor.spec)
        self.assertEqual(ACQUIRED.owned_rule_count(actor, "edge/몬스터볼-수리"), 1)

    def test_missing_skill_or_required_edge_does_not_receive_the_pc_progression_exception(self):
        for change in ("skill", "edge"):
            with self.subTest(change=change):
                options = self.options()
                if change == "skill": options["skills"]["기술학"] = 2
                else:
                    options["edges"].remove("edge/몬스터볼")
                    del options["requirements"]["edge/몬스터볼"]
                prepared = NPC.prepare(self.rules, "unqualified", 15, **options)
                self.assertEqual(prepared["status"], "pending")
                before = deepcopy(self.engine.export_state())
                with self.assertRaisesRegex(ValueError, "pending"):
                    NPC.create(self.engine, "unqualified", 15, **options)
                self.assertEqual(self.engine.export_state(), before)

    def test_missing_source_review_and_unresolved_necessary_condition_leave_no_entity(self):
        options = self.options()
        del options["requirements"]["class/로그"]
        self.assertEqual(NPC.prepare(self.rules, "pending", 15, **options)["status"], "pending")
        options = self.options()
        declaration = options["requirements"]["class/로그"]
        row = declaration["policy"]["variants"][0]
        row["inputs"]["unobserved_condition"] = {"type": "boolean", "authority": "gm", "question": "Necessary prerequisite observation?"}
        row["when"]["all"].append({"$input": "unobserved_condition"})
        result = NPC.prepare(self.rules, "pending", 15, **options)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["spec"][NPC.KEY]["requirements"]["class/로그"]["status"], "PolicyInputsRequired")
        with self.assertRaisesRegex(ValueError, "pending"):
            NPC.observe(self.engine, "pending", 15, **{**options, "combat": None})
        self.assertFalse(getattr(self.engine, "_partial_entities", {}))
        self.assertEqual(self.engine.everyone, [])

    def test_prerequisite_policy_cannot_substitute_empty_conditions_caller_facts_or_changed_text(self):
        for change in ("empty", "text", "context", "unused"):
            with self.subTest(change=change):
                options = self.options()
                row = options["requirements"]["edge/몬스터볼"]["policy"]["variants"][0]
                if change == "empty":
                    del row["inputs"]["tech"]; row["when"] = {"$input": "requirements_reviewed"}
                elif change == "text": row["values"]["source_text"] = "no prerequisites"
                elif change == "context":
                    row["inputs"]["tech"] = {"type": "integer", "authority": "context", "question": "forged rank"}
                else: row["when"] = {"$input": "requirements_reviewed"}
                with self.assertRaises(ValueError): NPC.prepare(self.rules, "invalid", 15, **options)
        options = self.options()
        declaration = options["requirements"]["edge/몬스터볼"]
        row = declaration["policy"]["variants"][0]
        row["when"] = {"any": [{"$input": "requirements_reviewed"}, self.minimum("tech", 3)]}
        declaration["decisions"]["requirements_reviewed"]["value"] = False
        self.assertEqual(NPC.prepare(self.rules, "declined coverage", 15, **options)["status"], "pending")
        with self.assertRaisesRegex(ValueError, "pending"):
            NPC.create(self.engine, "declined coverage", 15, **options)
        self.assertEqual(self.engine.everyone, [])

    def test_very_low_level_assessment_does_not_invent_a_cutoff_or_waive_normal_acquisition(self):
        options = self.options(); options["level_treatment"]["very_low_level"] = True
        result = NPC.prepare(self.rules, "low", 15, **options)
        self.assertEqual(result["status"], "pending")
        self.assertFalse(result["spec"][NPC.KEY]["pc_acquisition_exception"])
        with self.assertRaises(ValueError): NPC.create(self.engine, "low", 15, **options)
        options["level_treatment"]["very_low_level"] = 0
        with self.assertRaises(ValueError): NPC.prepare(self.rules, "low", 15, **options)
        self.assertEqual(self.engine.everyone, [])

    def test_optional_combat_omission_uses_existing_partial_owner_and_never_defaults_stats(self):
        options = self.options(); options["combat"] = None
        result = NPC.observe(self.engine, "witness", 15, **options)
        self.assertFalse(result["combatant"])
        self.assertIn("stats", result["unknown_fields"])
        self.assertEqual(PARTIAL.skill(self.engine, result["entity_id"], "기술학")[2], 5)
        self.assertEqual(result["provenance"][NPC.KEY]["source_id"], NPC.SOURCE)
        row = self.engine._partial_entities[result["entity_id"]]
        with self.assertRaisesRegex(ValueError, "missing stats are unknown"):
            self.engine.take_damage(row, 1)
        with self.assertRaisesRegex(ValueError, "complete stat allocation"):
            builder.build_quick_npc(self.rules, "witness", 15, **options)
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(self.engine))))
        self.assertEqual(PARTIAL.project(loaded, result["entity_id"]), result)
        before = deepcopy(self.engine.export_state())
        project = PARTIAL.project

        def fail_after_source_adoption(staged, uid):
            if NPC.KEY in staged._partial_entities[uid]["provenance"]:
                raise ValueError("late source-adopted partial projection")
            return project(staged, uid)

        with patch.object(PARTIAL, "project", side_effect=fail_after_source_adoption):
            with self.assertRaisesRegex(ValueError, "late source-adopted partial projection"):
                NPC.observe(self.engine, "failed observation", 15, **options)
        self.assertEqual(self.engine.export_state(), before)

    def test_stat_budget_endpoints_level_one_and_example_follow_main_rule_without_tag_bonus(self):
        for level, points, focus in ((1, 0, "noncombat"), (1, 0, "combat"), (5, 4, "noncombat"),
                                     (5, 8, "combat"), (15, 14, "noncombat"), (15, 20, "mixed"), (15, 28, "combat")):
            with self.subTest(level=level, points=points, focus=focus):
                stats = NPC.combat_stats(level, self.allocation(level, points, focus))
                self.assertEqual(sum(stats.values()), 35 + 10 + points)
                self.assertEqual(stats["hp"], 15)
        for points, focus in ((13, "mixed"), (29, "mixed"), (20, "noncombat"), (20, "combat"), (True, "mixed")):
            with self.subTest(points=points, focus=focus):
                with self.assertRaises(ValueError): NPC.combat_stats(15, self.allocation(points=points, focus=focus))
        invalid = self.allocation(); invalid["initial"]["hp"] = 6
        with self.assertRaises(ValueError): NPC.combat_stats(15, invalid)

    def test_four_class_limit_rank_and_branch_constraints_remain_owned_by_existing_validator(self):
        options = self.options()
        options["classes"] = ["class/스타일-전문가", "class/타입-에이스"]
        options["feats"] = []
        options["feature_choices"] = {"class/스타일-전문가": ["근사함", "귀여움"], "class/타입-에이스": ["물", "불꽃", "풀"]}
        with self.assertRaisesRegex(ValueError, "four slots"): NPC.prepare(self.rules, "overfull", 15, **options)
        options = self.options(); options["feat_ranks"] = {"feat/불시의-공격": 2}
        with self.assertRaisesRegex(ValueError, "source maximum"): NPC.prepare(self.rules, "overrank", 15, **options)

    def test_native_martial_choice_uses_existing_receipt_ability_and_move_consumers(self):
        options = self.martial_options()
        actor = NPC.create(self.engine, "quick martial guide", 15, **options)
        receipt = FEATURES.receipts(actor)[0]
        self.assertEqual(receipt["feature_id"], FEATURES.MARTIAL_ARTIST)
        self.assertEqual(FEATURES.martial_ability(actor), "ability/철주먹")
        self.assertIn("철주먹", actor.abilities)
        self.assertTrue({self.rules.move_id(x) for x in ("마하펀치", "두번차기", "바위깨기")} <= set(actor.moves))
        self.assertIs(self.engine.everyone[0], actor)
        self.assertIs(self.engine.gm.everyone[0], actor)
        self.assertEqual(actor.stats, NPC.combat_stats(15, options["combat"]))
        self.assertFalse(actor._state_origin["creation_legality_certified"])
        self.assertEqual(len(FEATURES.receipts(actor)), 1)
        with self.assertRaisesRegex(ValueError, "require quick_npc.create"):
            builder.build_quick_npc(self.rules, "unreceipted", 15, **options)

    def test_native_stat_tags_fit_explicit_allocation_without_offsetting_other_sources(self):
        options = self.options()
        register = ITEMS.register_feats

        def with_independent_source(engine, actor, *args, **kwargs):
            result = register(engine, actor, *args, **kwargs)
            GRANTS._source(actor, "gm/independent-attack", "gm", owner_id=actor.entity_id,
                           lifetime="permanent", rule_id="gm/explicit-attack", tutor_points=0)
            GRANTS.stat(actor, "atk", 3, "gm/independent-attack", operation_id="observed")
            return result

        with patch.object(ITEMS, "register_feats", side_effect=with_independent_source):
            actor = NPC.create(self.engine, "separate source", 15, **options)
        expected = NPC.combat_stats(15, options["combat"])
        self.assertEqual(actor.stats, {**expected, "atk": expected["atk"] + 3})
        self.assertTrue(STATIC.validate(actor))
        tags = sum(row.get("count", 1) for row in STATIC.plan(actor).values() if row.get("stat") == "atk")
        self.assertEqual(actor.spec["stats"]["atk"], expected["atk"] - tags)
        before = deepcopy(self.engine.export_state())
        options["combat"]["growth"].update(atk=0, spe=20)
        with self.assertRaisesRegex(ValueError, "stat tags exceed the explicit allocation"):
            NPC.create(self.engine, "needs chosen allocation", 15, **options)
        self.assertEqual(self.engine.export_state(), before)

    def test_missing_native_choice_is_pending_and_late_native_failure_rolls_back_entire_creation(self):
        options = self.martial_options(); del options["native_acquisitions"]
        self.assertEqual(NPC.prepare(self.rules, "pending style", 15, **options)["status"], "pending")
        before = deepcopy(self.engine.export_state())
        with self.assertRaises(ValueError): NPC.create(self.engine, "pending style", 15, **options)
        self.assertEqual(self.engine.export_state(), before)
        options = self.martial_options()
        # Native style commits before the existing final registration fails.
        with patch.object(Engine, "register_abilities", side_effect=ValueError("late native registration")):
            with self.assertRaisesRegex(ValueError, "late native registration"):
                NPC.create(self.engine, "rolled back style", 15, **options)
        self.assertEqual(self.engine.export_state(), before)

    def test_personal_tutor_reuses_existing_immutable_selection_producer(self):
        uid = FEATURES.PERSONAL_TUTOR
        moves = [self.rules.move_id(x) for x in ("속여때리기", "도둑질", "기습")]
        options = self.options(); options["skills"]["일반 지식"] = 3
        options["feats"].append(uid)
        options["requirements"][uid] = self.policy(uid,
            {"education": self.binding("skill_rank", skill="일반 지식"), "known_three": {"type": "boolean", "authority": "gm",
                "question": "Three permanent known moves will be proved by the existing native acquisition producer"}},
            [self.minimum("education", 3), {"$input": "known_three"}])
        options["requirements"][uid]["decisions"]["known_three"] = {"value": True, "reason": "native producer must still prove all three actual permanent moves"}
        options["native_acquisitions"] = {uid: {"acquisition_request_id": "quick-tutor", "selected_values": moves}}
        actor = NPC.create(self.engine, "quick tutor guide", 15, moves=moves, **options)
        self.assertEqual(ACQUIRED.selected_at_acquisition(actor, uid, uid + ":1"), tuple(moves))
        self.assertEqual(FEATURES.receipts(actor)[0]["selection"]["values"], moves)
        self.assertFalse(actor._state_origin["creation_legality_certified"])

    def test_native_consumers_recheck_actual_prerequisites_and_style_choices_before_commit(self):
        before = deepcopy(self.engine.export_state())
        for change in ("prerequisite", "style"):
            with self.subTest(change=change):
                options = self.martial_options()
                if change == "prerequisite":
                    options["skills"]["전투"] = 2
                    # An erroneous authored review never overrides the native
                    # source owner's actual Novice Combat prerequisite.
                    for uid in (FEATURES.MARTIAL_ARTIST, "edge/기본-무술"):
                        row = options["requirements"][uid]["policy"]["variants"][0]
                        row["when"]["all"][1]["right"] = 2
                else:
                    options["feature_choices"]["feat/무술-훈련"] = [["경혈찌르기", "두번차기"]]
                with self.assertRaises(ValueError):
                    NPC.create(self.engine, "invalid native choice", 15, **options)
                self.assertEqual(self.engine.export_state(), before)

    def test_snapshot_and_json_restore_preserve_actual_native_source_choices_and_role(self):
        actor = NPC.create(self.engine, "restored guide", 15, **self.martial_options())
        self.engine.gm.snapshot("quick NPC")
        self.engine.take_damage(actor, 7)
        self.engine.gm.restore("quick NPC")
        self.assertEqual(actor.hp, actor.max_hp)
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(self.engine))))
        restored = loaded.everyone[0]
        self.assertEqual(restored.spec[NPC.KEY], actor.spec[NPC.KEY])
        self.assertEqual(FEATURES.martial_ability(restored), "ability/철주먹")
        self.assertEqual(restored.moves, actor.moves)
        self.assertFalse(restored._state_origin["creation_legality_certified"])

    def test_changed_source_and_override_fail_before_any_creation(self):
        options = self.options()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / "input").mkdir()
            source = Path(self.rules.root) / NPC.REFERENCE["file"]
            (root / NPC.REFERENCE["file"]).write_bytes(source.read_bytes() + b"\nchanged")
            rules = copy(self.rules); rules.root = str(root)
            with self.assertRaisesRegex(ValueError, "source changed"):
                NPC.prepare(rules, "stale", 15, **options)
        with patch.dict(self.rules.rulings.mech, {NPC.SOURCE: {"invented_points": 99}}):
            with self.assertRaisesRegex(ValueError, "override"):
                NPC.create(self.engine, "override", 15, **options)
        self.assertEqual(self.engine.everyone, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
