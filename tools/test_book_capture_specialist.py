"""Capture class/rank acquisition state and its existing native consumers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from builder import build_trainer
from engine import Combatant, Engine, Rules
import acquired_features as ACQUIRED
import capture_techniques as CAPTURE
import items
import skill_modifiers as SKILLS
import state_codec as CODEC
import state_fields as FIELDS
import state_grants as GRANTS
import trainer_feature_acquisition as TFA
import trainer_retraining as RETRAIN
import wild_equipment as WILD
import test_category3_wild_equipment as WILD_FIXTURE


def choice(name):
    return {"technique": name}


def skill(edge="edge/기본-스킬", name="은신"):
    return {"technique": "포획 스킬", "edge": edge, "skill": name}


class BookCaptureSpecialistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")
        cls.errata_rules = Rules(str(ROOT), ruleset="core+errata")

    def fixture(self, *, skills=None, level=20, rules=None):
        rules = self.rules if rules is None else rules
        engine = Engine(rules, seed=375)
        spec = build_trainer(rules, "capture owner", level,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10), moves=[], abilities=[])
        spec.update(classes=[], feats=[], edges=[], skills=skills or dict.fromkeys(CAPTURE.SKILLS, 5), exp_bank=30)
        actor = Combatant(rules, spec)
        engine.everyone = engine.gm.everyone = [actor]
        return engine, actor

    def acquire(self, e, a, choices, rank=0, request=None, **options):
        return CAPTURE.acquire(e, a, CAPTURE.CLASS if rank == 0 else CAPTURE.ADVANCED,
            acquisition_request_id=request or "capture/" + str(rank), selected_techniques=choices, rank=rank,
            lifecycle_policy=TFA.LIFECYCLE_WHILE_OWNED, **options)

    def snapshot(self, e, a):
        return deepcopy((a.spec, a.stats, e.rng.getstate(), e.elapsed_seconds, e.log_lines))

    def decisions(self, e, a, uid, request="capture/retrain", **extra):
        owned = RETRAIN._owned(a)
        sources = {key: RETRAIN.owned_source(e, a, key) for key in owned}
        retained = {source: list(a.spec[GRANTS.KEY]["sources"][source].get("withdrawal_dependencies", []))
                    for key, source in sources.items() if key != uid}
        if CAPTURE.ADVANCED in owned and uid != CAPTURE.ADVANCED:
            retained[sources[CAPTURE.ADVANCED]] = [sources[CAPTURE.CLASS]]
        return dict(request_id=request, reason="reviewed actual retraining",
            gm_decision={"allowed": True, "reason": "GM reviewed retained dependencies"},
            retained_dependencies=retained, **extra)

    def test_class_and_all_four_ranks_select_two_each_make_ten_owned_instances_and_five_speed(self):
        ranks = dict.fromkeys(CAPTURE.SKILLS, 5); ranks["은신"] = 1
        e, a = self.fixture(skills=ranks)
        pairs = [[choice("작업 도구"), choice("커브볼")], [skill(), choice("빠른 투구")],
                 [choice("덫"), choice("약화 투척")], [skill(), choice("캐치 콤보")],
                 [choice("거짓 타격"), choice("끝없는 추격")]]
        originals = []
        for rank, pair in enumerate(pairs):
            originals.append(self.acquire(e, a, pair, rank))
            self.assertEqual(a.stats["spe"], 11 + rank)
            self.assertEqual(len(CAPTURE.selected(a)), 2 * (rank + 1))
        self.assertEqual(len(set(CAPTURE.selected(a))), 9)
        self.assertEqual(ACQUIRED.owned_rule_count(a, CAPTURE.ADVANCED), 4)
        self.assertEqual(ACQUIRED.owned_rule_count(a, "edge/기본-스킬"), 2)
        self.assertEqual(SKILLS.rank(e.r, a, "은신")[2], 3)
        self.assertEqual(a.spec["edges"], [])
        self.assertEqual([len(r["selection"]["values"]) for r in originals], [2] * 5)
        before = self.snapshot(e, a)
        for _ in range(2): items.register_feats(e, a)
        self.assertEqual(a.stats["spe"], 15)
        self.assertEqual(a.spec[TFA.LEDGER_KEY], before[0][TFA.LEDGER_KEY])
        self.assertTrue(e.validate_state()["valid"])

    def test_physical_and_social_or_domains_are_independent_and_class_slots_are_enforced(self):
        for physical in CAPTURE.SKILLS[:4]:
            for social in CAPTURE.SKILLS[4:]:
                ranks = dict.fromkeys(CAPTURE.SKILLS, 2); ranks.update({physical: 3, social: 3})
                e, a = self.fixture(skills=ranks)
                self.acquire(e, a, [choice("Curve Ball"), choice("Tools of the Trade")])
                self.assertEqual(len(ACQUIRED.class_instances(a)), 1)
        for ranks in ({"곡예": 3, "교활": 2}, {"곡예": 2, "교활": 3}):
            e, a = self.fixture(skills=ranks); before = self.snapshot(e, a)
            with self.assertRaises(ValueError): self.acquire(e, a, [choice("커브볼"), choice("작업 도구")])
            self.assertEqual(self.snapshot(e, a), before)
        e, a = self.fixture()
        a.spec["classes"] = ["class/운동선수", "class/멘토", "class/치어리더", "class/지휘관"]
        before = self.snapshot(e, a)
        with self.assertRaises(ValueError): self.acquire(e, a, [choice("커브볼"), choice("작업 도구")])
        self.assertEqual(self.snapshot(e, a), before)

    def test_rank_two_three_four_require_distinct_qualifying_skills_only_in_fixed_domain(self):
        pairs = [[choice("커브볼"), choice("작업 도구")], [choice("빠른 투구"), choice("약화 투척")],
                 [choice("덫"), choice("캐치 콤보")], [choice("거짓 타격"), choice("끝없는 추격")]]
        for rank, values in ((2, [4, 3, 3, 3, 3, 3]), (3, [5, 4, 4, 4, 4, 4]), (4, [5, 5, 4, 4, 4, 4])):
            e, a = self.fixture()
            for earlier in range(rank): self.acquire(e, a, pairs[earlier], earlier)
            a.spec["skills"] = dict(zip(CAPTURE.SKILLS, values)); a.spec["skills"].update({"전투": 6, "명령": 6})
            before = self.snapshot(e, a)
            with self.assertRaisesRegex(ValueError, "distinct qualifying"):
                self.acquire(e, a, [skill("edge/달인-스킬", "곡예"), skill("edge/전문-스킬", "은신")], rank)
            self.assertEqual(self.snapshot(e, a), before)

    def test_technique_count_domain_repetition_and_expert_conditions_fail_before_mutation(self):
        invalid = [[choice("커브볼")], [choice("커브볼")] * 3,
                   [choice("커브볼"), choice("Curve Ball")], [choice("unknown"), choice("덫")],
                   [skill(name="전투"), choice("덫")]]
        for choices in invalid:
            e, a = self.fixture(); before = self.snapshot(e, a)
            with self.assertRaises(ValueError): self.acquire(e, a, choices)
            self.assertEqual(self.snapshot(e, a), before)
        for technique in CAPTURE.EXPERT:
            e, a = self.fixture(skills={"곡예": 5, "육상": 5, "교활": 3})
            before = self.snapshot(e, a)
            with self.assertRaisesRegex(ValueError, "three Expert"):
                self.acquire(e, a, [choice(technique), choice("덫")])
            self.assertEqual(self.snapshot(e, a), before)
        e, a = self.fixture(skills={"곡예": 3, "교활": 3, "은신": 1})
        self.acquire(e, a, [skill(), skill()])
        before = self.snapshot(e, a)
        with self.assertRaisesRegex(ValueError, "at most twice"):
            self.acquire(e, a, [skill("edge/숙련-스킬"), choice("덫")], 1)
        self.assertEqual(self.snapshot(e, a), before)

    def test_every_skill_edge_uses_exact_transition_level_and_actual_native_skill_result(self):
        for edge, before_rank, level in (("edge/기본-스킬", 1, 1), ("edge/기본-스킬", 2, 1),
                ("edge/숙련-스킬", 3, 2), ("edge/전문-스킬", 4, 6), ("edge/달인-스킬", 5, 12)):
            e, a = self.fixture(skills={"곡예": 3, "교활": 3, "은신": before_rank}, level=level)
            r = self.acquire(e, a, [skill(edge), choice("커브볼")])
            self.assertEqual(SKILLS.rank(e.r, a, "은신")[2], before_rank + 1)
            self.assertEqual(ACQUIRED.owned_rule_count(a, edge), 1)
            self.assertEqual(r["selection"]["proofs"][0]["skill_edge"]["before"], before_rank)
            self.assertTrue(any(row.get("source_id") == edge for row in e.acquisition_receipts(a)))
            for wrong_rank, wrong_level in ((min(6, before_rank + 1), level), (before_rank, level - 1)):
                if edge == "edge/기본-스킬" and wrong_rank == 2 or wrong_level < 1: continue
                e2, a2 = self.fixture(skills={"곡예": 3, "교활": 3, "은신": wrong_rank}, level=wrong_level)
                original = self.snapshot(e2, a2)
                with self.assertRaises(ValueError): self.acquire(e2, a2, [skill(edge), choice("커브볼")])
                self.assertEqual(self.snapshot(e2, a2), original)

    def test_acquisition_replay_provider_imported_ownership_and_source_variant_are_exact(self):
        e, a = self.fixture(); pair = [choice("커브볼"), choice("작업 도구")]
        receipt = self.acquire(e, a, pair); before = self.snapshot(e, a)
        self.assertEqual(self.acquire(e, a, pair), receipt)
        with self.assertRaises(ValueError): self.acquire(e, a, [choice("빠른 투구"), choice("작업 도구")])
        self.assertEqual(self.snapshot(e, a), before)
        e, a = self.fixture(); other = Combatant(e.r, dict(deepcopy(a.spec), id="trainer/other"))
        e.everyone.append(other)
        with self.assertRaisesRegex(ValueError, "provider"): self.acquire(e, a, pair, provider=other)
        a.spec["classes"] = [CAPTURE.CLASS]
        with self.assertRaisesRegex(ValueError, "unreceipted"): self.acquire(e, a, pair)
        e, a = self.fixture(); selected = e.r._selected_rule
        with patch.object(e.r, "_selected_rule", side_effect=lambda uid, **kw: uid + "-other" if uid == CAPTURE.CLASS else selected(uid, **kw)):
            with self.assertRaisesRegex(ValueError, "selected Capture"): self.acquire(e, a, pair)

    def test_historical_qualification_stays_immutable_after_live_skill_changes(self):
        e, a = self.fixture(); receipt = self.acquire(e, a, [choice("작업 도구"), choice("캐치 콤보")])
        FIELDS.base_patch(a, {"skills": dict.fromkeys(CAPTURE.SKILLS, 1)}, reason="later GM skill change")
        self.assertEqual(CAPTURE.selected(a), ("작업 도구", "캐치 콤보"))
        self.assertEqual(WILD.tools_bonus(e, a, "accuracy"), 2)
        self.assertEqual(a.spec[TFA.LEDGER_KEY]["capture/0"], receipt)

    def test_receipt_actual_source_and_rank_tampering_refuse_native_use_and_validation(self):
        for target in ("receipt", "source", "rank", "child"):
            e, a = self.fixture(skills={"곡예": 5, "교활": 5, "은신": 2})
            r = self.acquire(e, a, [skill(), choice("작업 도구")])
            if target == "receipt": a.spec[TFA.LEDGER_KEY]["capture/0"]["selection"]["values"][0] = "덫"
            if target == "source": a.spec[GRANTS.KEY]["sources"].pop(CAPTURE._source_id(a, r))
            if target == "rank": a.spec["feats"].append(CAPTURE.ADVANCED); a.spec["feat_ranks"] = {CAPTURE.ADVANCED: 2}
            if target == "child": CAPTURE.skill_edges(a)[0][1]["skill_edge"]["after"] = 6
            with self.assertRaises(ValueError): WILD.tools_bonus(e, a, "accuracy")
            with self.assertRaises(CODEC.StateCodecError): CODEC.dump_engine(e)

    def test_late_child_grant_failure_rolls_back_the_whole_class_and_first_edge(self):
        e, a = self.fixture(skills={"곡예": 3, "교활": 3, "은신": 1}); before = self.snapshot(e, a)
        actual = FIELDS.base_patch
        def fail_second(actor, changes, **kw):
            if changes["skills"].get("은신") == 3: raise ValueError("second actual Edge transition failed")
            return actual(actor, changes, **kw)
        with patch.object(FIELDS, "base_patch", side_effect=fail_second):
            with self.assertRaisesRegex(ValueError, "second actual"):
                self.acquire(e, a, [skill(), skill()])
        self.assertEqual(self.snapshot(e, a), before)

    def test_actual_tools_selected_source_drives_ball_accuracy_lure_reel_and_bait(self):
        f = WILD_FIXTURE.WildEquipmentTests(); f.rules = self.rules; f.setUp()
        self.acquire(f.e, f.a, [choice("작업 도구"), choice("커브볼")])
        f.place(); result = f.act("attract_bait", phase="wait", bait_id="bait", fixed=11)
        self.assertEqual(result["checks"][-1]["total"], 15)
        f.a.spec["items"].update({"대단한낚싯대": 1, "루어": 1, "몬스터볼": 1})
        f.act("fishing", phase="start", rod="대단한낚싯대", attachment="루어")
        self.assertEqual(f.act("fishing", phase="wait", roll_d20=11)["bite_bonus"], 4)
        self.assertEqual(f.act("fishing", phase="reel", target=f.p, fixed=[1, 1, 2, 2])["check"].total, 8)
        f.p.spec["evolutions_remaining"] = 0
        f.e.throw_ball(f.a, f.p, fixed_accuracy=5, fixed_capture=7)
        result = f.a.spec["capture_attempts"]["capture-1"]
        self.assertEqual((result["tools_accuracy"], result["capture_total"]), (2, 10))

    def test_snare_book_selection_needs_selected_modern_conversion_and_never_claims_book_minus_ten(self):
        f = WILD_FIXTURE.WildEquipmentTests(); f.rules = self.rules; f.setUp()
        self.acquire(f.e, f.a, [choice("덫"), choice("커브볼")]); f.distract()
        f.a.spec["items"]["몬스터볼"] = 1; before = f.state()
        with self.assertRaisesRegex(ValueError, "errata-ball-mod-conversion"):
            f.e.throw_ball(f.a, f.p, fixed_accuracy=20, fixed_capture=7)
        self.assertEqual(f.state(), before)
        f.rules = self.errata_rules; f.setUp()
        self.acquire(f.e, f.a, [choice("덫"), choice("커브볼")]); f.distract()
        f.a.spec["items"]["몬스터볼"] = 1; f.p.spec["evolutions_remaining"] = 0
        self.assertTrue(f.e.throw_ball(f.a, f.p, fixed_accuracy=20, fixed_capture=7))
        result = f.a.spec["capture_attempts"]["capture-1"]
        self.assertEqual((result["snare_bonus"], result["resolution"]["sides"], result["capture_total"]), (2, 20, 12))

    def test_parent_dependency_and_ranked_retraining_limit_are_explicit_and_atomic(self):
        e, a = self.fixture(); self.acquire(e, a, [choice("작업 도구"), choice("커브볼")])
        self.acquire(e, a, [choice("빠른 투구"), choice("약화 투척")], 1)
        options = self.decisions(e, a, CAPTURE.CLASS); before = self.snapshot(e, a)
        with self.assertRaisesRegex(ValueError, "retained grant depends"):
            e.retrain_trainer_source(a, CAPTURE.CLASS, **options)
        self.assertEqual(self.snapshot(e, a), before)
        self.acquire(e, a, [choice("덫"), choice("캐치 콤보")], 2)
        options = self.decisions(e, a, CAPTURE.ADVANCED); before = self.snapshot(e, a)
        with self.assertRaisesRegex(ValueError, "select one actual"):
            e.retrain_trainer_source(a, CAPTURE.ADVANCED, **options)
        self.assertEqual(self.snapshot(e, a), before)
        a.spec["feat_ranks"][CAPTURE.ADVANCED] = 1
        with self.assertRaisesRegex(ValueError, "current Capture ranks"): TFA.validate_actor(a)

    def test_rank_one_and_class_retraining_revoke_choices_and_speed_preserving_independent_stat(self):
        e, a = self.fixture(); first = self.acquire(e, a, [choice("작업 도구"), choice("커브볼")])
        second = self.acquire(e, a, [choice("빠른 투구"), choice("약화 투척")], 1)
        GRANTS._source(a, "independent/speed", "gm", owner_id=a.entity_id)
        GRANTS.reconcile_stat(a, "spe", 2, "independent/speed", operation_id="independent")
        e.retrain_trainer_source(a, CAPTURE.ADVANCED, **self.decisions(e, a, CAPTURE.ADVANCED))
        self.assertEqual((a.stats["spe"], CAPTURE.selected(a)), (13, ("작업 도구", "커브볼")))
        e.retrain_trainer_source(a, CAPTURE.CLASS, **self.decisions(e, a, CAPTURE.CLASS, "capture/retrain-class"))
        self.assertEqual((a.stats["spe"], CAPTURE.selected(a)), (12, ()))
        self.assertEqual(a.spec[TFA.LEDGER_KEY], {"capture/0": first, "capture/1": second})
        self.assertEqual(WILD.tools_bonus(e, a, "accuracy"), 0)

    def test_child_retention_policy_preserves_actual_edge_and_independent_later_skill_growth(self):
        e, a = self.fixture(skills={"곡예": 3, "교활": 3, "은신": 2})
        self.acquire(e, a, [skill(), choice("작업 도구")])
        FIELDS.base_patch(a, {"skills": dict(a.spec["skills"], 은신=5)}, reason="independent later skill growth")
        options = self.decisions(e, a, CAPTURE.CLASS); before = self.snapshot(e, a)
        with self.assertRaisesRegex(ValueError, "explicit GM"): e.retrain_trainer_source(a, CAPTURE.CLASS, **options)
        self.assertEqual(self.snapshot(e, a), before)
        options["granted_skill_edge_policy"] = {"mode": "retain", "reason": "GM retains the already granted permanent Edge"}
        e.retrain_trainer_source(a, CAPTURE.CLASS, **options)
        self.assertEqual((SKILLS.rank(e.r, a, "은신")[2], ACQUIRED.owned_rule_count(a, "edge/기본-스킬")), (5, 1))
        self.assertEqual(CAPTURE.selected(a), ())
        self.assertTrue(e.validate_state()["valid"])
        CAPTURE.skill_edges(a)[0][1].pop("parent_end_policy")
        with self.assertRaisesRegex(CODEC.StateCodecError, "explicit child policy"):
            CODEC.dump_engine(e)

    def test_explicit_child_withdrawal_uses_gm_result_and_rejects_stale_or_retained_dependency(self):
        for blocked in ("stale", "dependent", None):
            e, a = self.fixture(skills={"곡예": 3, "교활": 3, "은신": 1})
            self.acquire(e, a, [skill(), skill()])
            children = CAPTURE.skill_edges(a)
            if blocked == "dependent":
                GRANTS._source(a, "independent/skill-dependent", "gm", owner_id=a.entity_id)
                e.bind_grant_dependencies(a, "independent/skill-dependent", [children[-1][0]])
            options = self.decisions(e, a, CAPTURE.CLASS, granted_skill_edge_policy={"mode": "withdraw",
                "reason": "GM reviewed removed Edge results and all independent skills",
                "skills_before": {"은신": 2 if blocked == "stale" else 3}, "skills_after": {"은신": 1}})
            before = self.snapshot(e, a)
            if blocked:
                with self.assertRaises(ValueError): e.retrain_trainer_source(a, CAPTURE.CLASS, **options)
                self.assertEqual(self.snapshot(e, a), before)
            else:
                e.retrain_trainer_source(a, CAPTURE.CLASS, **options)
                self.assertEqual((SKILLS.rank(e.r, a, "은신")[2], ACQUIRED.owned_rule_count(a, "edge/기본-스킬")), (1, 0))
                self.assertEqual(len([r for r in a.spec[GRANTS.KEY]["ended_sources"] if "capture_skill_receipt" in r["record"]]), 2)
                self.assertTrue(e.validate_state()["valid"])
                ended = next(row["record"] for row in a.spec[GRANTS.KEY]["ended_sources"] if "capture_skill_receipt" in row["record"])
                ended["capture_skill_withdrawal"]["state_change"]["after"]["skills"]["은신"] = 6
                with self.assertRaisesRegex(CODEC.StateCodecError, "withdrawal result"):
                    CODEC.dump_engine(e)

    def test_gm_and_fresh_rules_restore_keep_exact_choices_skills_and_single_stat_application(self):
        e, a = self.fixture(skills={"곡예": 5, "교활": 5, "은신": 1})
        self.acquire(e, a, [skill(), choice("작업 도구")])
        self.acquire(e, a, [skill(), choice("커브볼")], 1)
        identity = a.entity_id; before = deepcopy(a.spec)
        e.gm.snapshot("capture-before")
        FIELDS.base_patch(a, {"skills": dict(a.spec["skills"], 은신=6)}, reason="later temporary comparison")
        e.gm.restore("capture-before", reason="restore Capture acquisition")
        a = next(actor for actor in e.gm.everyone if actor.entity_id == identity)
        self.assertEqual(a.spec, before)
        fresh = CODEC.load_engine(Rules(str(ROOT), ruleset="core"), json.loads(json.dumps(CODEC.dump_engine(e), ensure_ascii=False)))
        restored = next(actor for actor in fresh.gm.everyone if actor.entity_id == identity)
        self.assertEqual((restored.stats["spe"], SKILLS.rank(fresh.r, restored, "은신")[2]), (12, 3))
        self.assertEqual(restored.spec[TFA.LEDGER_KEY], before[TFA.LEDGER_KEY])
        self.assertEqual(WILD.tools_bonus(fresh, restored, "accuracy"), 2)
        self.assertTrue(fresh.validate_state()["valid"])


if __name__ == "__main__":
    unittest.main()
