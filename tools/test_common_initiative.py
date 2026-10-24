"""Local initiative oracles; GM tie policies are not source-rule claims."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from engine import Rules, Engine, Combatant
import initiative as INITIATIVE


class CommonInitiativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = copy.deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.e = Engine(self.rules, seed=51)

    def actor(self, name, speed, paralysis=False):
        c = Combatant(self.rules, {"name": name, "kind": "pokemon", "level": 10,
            "stats": {"hp": 20, "atk": 10, "def": 10, "spa": 10, "spd": 10, "spe": speed},
            "types": ["노말"], "moves": [], "abilities": []})
        self.e.gm.add_combatant(c, reason='actual initiative participant')
        if paralysis:
            self.e.apply_status(c, '마비', source='gm/observed-initiative-paralysis')
        return c

    def policy(self, *, direction="highest_d20", same="reroll", rounds=10):
        self.e.rulings.add_answer("initiative_tie_order", {"policy": direction,
            "same_face": same, "max_rounds": rounds, "reason": "테스트가 명시한 GM 동률 정책"},
            reason="테스트 전용 결정", scope="scene")

    def faces(self, values):
        values = iter(values)
        self.rolls = []
        def d20():
            n = next(values); self.rolls.append(n); return n
        self.e.d20 = d20

    def test_isolated_paralysis_changes_actual_order(self):
        a, b = self.actor("마비20", 20, True), self.actor("정상15", 15)
        self.assertEqual(INITIATIVE.order(self.e, [a, b]), [b, a])
        self.assertIn("floor((20)/2)=10", self.e.log_lines[-1])

    def test_default_floor_odd_boundary(self):
        for n in range(1, 42):
            with self.subTest(n=n):
                self.assertEqual(INITIATIVE.value(self.rules, self.actor("p", n, True)).value, n // 2)

    def test_unmodified_order_consumes_no_tie_dice(self):
        a, b = self.actor("a", 10), self.actor("b", 20)
        state = self.e.rng.getstate()
        self.assertEqual(INITIATIVE.order(self.e, [a, b]), [b, a])
        self.assertEqual(self.e.rng.getstate(), state)

    def test_staged_speed_is_used(self):
        c = self.actor("p", 20, True); c.stages["spe"] = 2
        self.assertEqual(INITIATIVE.value(self.rules, c).value, 14)  # 20 * 1.4 / 2
        self.assertEqual(c.stats["spe"], 20); self.assertEqual(c.stages["spe"], 2)

    def test_successful_paralysis_save_does_not_remove_initiative_half(self):
        c = self.actor("p", 11, True)
        self.e.start_round([c]); self.faces([11]); self.e.start_of_turn(c, initiative_count=5)
        self.assertIn("마비", c.conditions)
        self.assertEqual(INITIATIVE.value(self.rules, c).value, 5)
        self.assertEqual(c.stats["spe"], 11)

    def test_flat_bonus_without_half_preserves_old_supported_behavior(self):
        a, b = self.actor("a", 10), self.actor("b", 15); a.initiative_bonus = 10
        self.assertEqual(INITIATIVE.order(self.e, [a, b]), [a, b])
        self.assertIn("+10", self.e.log_lines[-1])

    def test_fixed_value_without_competing_modifiers(self):
        a, b = self.actor("a", 10), self.actor("b", 15)
        self.e.gm.set_initiative(a, 22, reason="시나리오 명시 순서")
        self.assertEqual(INITIATIVE.order(self.e, [a, b]), [a, b])
        self.assertIn("fixed=22", self.e.log_lines[-1])

    def test_fixed_zero_is_not_treated_as_absent(self):
        a, b = self.actor("a", 30), self.actor("b", 15); a.initiative_override = 0
        self.assertEqual(INITIATIVE.order(self.e, [a, b]), [b, a])

    def test_half_bonus_composition_holds_without_actor_clock_or_rng_mutation(self):
        a, b = self.actor("a", 20, True), self.actor("b", 15); a.initiative_bonus = 4
        before = (a.hp, a.conditions.copy(), a.initiative_bonus, self.e.elapsed_seconds, self.e.round_no, self.e.rng.getstate())
        self.assertIsNone(INITIATIVE.order(self.e, [a, b]))
        self.assertEqual(before, (a.hp, a.conditions.copy(), a.initiative_bonus, self.e.elapsed_seconds, self.e.round_no, self.e.rng.getstate()))

    def test_fixed_and_half_require_explicit_composition_decision(self):
        a = self.actor("a", 20, True); a.initiative_override = 30
        self.assertIsNone(INITIATIVE.order(self.e, [a]))
        self.e.rulings.add_answer("initiative_value", {"value": 30, "reason": "이 장면에 최종값30을 명시"})
        self.assertEqual(INITIATIVE.order(self.e, [a]), [a])
        records = [x for x in self.e.rulings.log if x["kind"] == "initiative_adjudication"]
        self.assertEqual(records[-1]["after"]["value"], 30)
        self.assertEqual(a.initiative_override, 30)

    def test_ambiguous_flinch_is_not_promoted_to_set_five(self):
        a = self.actor("a", 20); a.conditions.add("풀죽음")
        self.assertIsNone(INITIATIVE.order(self.e, [a]))

    def test_registered_initiative_extension_is_not_ignored(self):
        a = self.actor("a", 20); a.registry.append({"type": "initiative_multiplier", "value": 2})
        self.assertIsNone(INITIATIVE.order(self.e, [a]))

    def test_unanswered_tie_is_pending_without_rng(self):
        a, b = self.actor("a", 10), self.actor("b", 10)
        before = self.e.rng.getstate()
        self.assertIsNone(INITIATIVE.order(self.e, [a, b]))
        self.assertEqual(self.e.rng.getstate(), before)

    def test_explicit_tie_order_supports_duplicate_names(self):
        a, b = self.actor("동명", 10), self.actor("동명", 10)
        self.e.rulings.provider = lambda prompt: {"order": ["actor:1", "actor:0"], "request_id": prompt["request_id"], "reason": "GM 지정"}
        self.assertEqual(INITIATIVE.order(self.e, [a, b]), [b, a])

    def test_fixed_order_response_cannot_replay_for_new_roster(self):
        a, b, c, d = [self.actor(name, 10) for name in ["a", "b", "c", "d"]]
        saved = {}
        def provider(prompt):
            saved.update(order=["actor:1", "actor:0"], request_id=prompt["request_id"], reason="첫 명단 결정")
            return dict(saved)
        self.e.rulings.provider = provider
        self.assertEqual(INITIATIVE.order(self.e, [a, b]), [b, a])
        self.e.rulings.provider = None
        self.e.rulings.add_answer("initiative_tie_order", dict(saved), scope="once")
        state = self.e.rng.getstate()
        self.assertIsNone(INITIATIVE.order(self.e, [c, d]))
        self.assertIsNone(INITIATIVE.order(self.e, [a, b]))
        self.assertEqual(self.e.rng.getstate(), state)
        self.assertEqual(len(self.e.rulings.answers), 1)  # record != consumption

    def test_unscoped_stored_fixed_order_is_held(self):
        a, b = self.actor("a", 10), self.actor("b", 10)
        self.e.rulings.add_answer("initiative_tie_order", {"order": ["actor:1", "actor:0"], "reason": "누락된 요청 scope"})
        self.assertIsNone(INITIATIVE.order(self.e, [a, b]))

    def test_highest_roll_is_only_an_explicit_gm_policy(self):
        a, b = self.actor("a", 10), self.actor("b", 10); self.policy(); self.faces([3, 18])
        self.assertEqual(INITIATIVE.order(self.e, [a, b]), [b, a])
        self.assertEqual(self.rolls, [3, 18])
        self.assertTrue(any(r["kind"] == "initiative_adjudication" for r in self.e.rulings.log))

    def test_explicit_lowest_roll_policy_is_not_mislabeled_source(self):
        a, b = self.actor("a", 10), self.actor("b", 10); self.policy(direction="lowest_d20"); self.faces([3, 18])
        self.assertEqual(INITIATIVE.order(self.e, [a, b]), [a, b])

    def test_reroll_only_tied_faces_not_already_resolved_group(self):
        a, b, c = [self.actor(n, 10) for n in "abc"]; self.policy(); self.faces([9, 9, 4, 2, 18])
        self.assertEqual(INITIATIVE.order(self.e, [a, b, c]), [b, a, c])
        self.assertEqual(len(self.rolls), 5)

    def test_repeated_tie_at_explicit_computation_bound_stays_pending(self):
        a, b = self.actor("a", 10), self.actor("b", 10); self.policy(rounds=2); self.faces([7, 7, 7, 7])
        self.assertIsNone(INITIATIVE.order(self.e, [a, b]))
        self.assertEqual(len(self.rolls), 4)

    def test_repeated_tie_can_receive_explicit_order(self):
        a, b = self.actor("a", 10), self.actor("b", 10)
        def provider(prompt):
            if prompt.get("rolls") is None:
                return {"policy": "highest_d20", "same_face": "decide", "reason": "고저 재정"}
            return {"order": ["actor:1", "actor:0"], "request_id": prompt["request_id"], "reason": "동면 재정"}
        self.e.rulings.provider = provider; self.faces([4, 4])
        self.assertEqual(INITIATIVE.order(self.e, [a, b]), [b, a])

    def test_all_initial_tie_decisions_precede_random_consumption(self):
        actors = [self.actor("a", 20), self.actor("b", 20), self.actor("c", 10), self.actor("d", 10)]
        self.e.rulings.provider = lambda prompt: ({"policy": "highest_d20", "same_face": "reroll", "max_rounds": 2, "reason": "상위동률만 결정"} if prompt.get("initiative") == 20 else None)
        before = self.e.rng.getstate()
        self.assertIsNone(INITIATIVE.order(self.e, actors)); self.assertEqual(self.e.rng.getstate(), before)

    def test_bad_decision_not_treated_as_authority(self):
        a, b = self.actor("a", 10), self.actor("b", 10)
        for answer in [{"order": ["actor:0", "actor:0"], "reason": "bad"}, {"order": ["actor:0", "actor:1"]}, {"policy": "highest_d20", "same_face": "reroll", "max_rounds": True, "reason": "bad"}]:
            with self.subTest(answer=answer):
                self.e.rulings.answers = []
                self.e.rulings.add_answer("initiative_tie_order", answer)
                before = self.e.rng.getstate()
                self.assertIsNone(INITIATIVE.order(self.e, [a, b])); self.assertEqual(self.e.rng.getstate(), before)

    def test_duplicate_actor_identity_is_rejected(self):
        a = self.actor("a", 10); self.assertIsNone(INITIATIVE.order(self.e, [a, a]))

    def test_selected_condition_reader_controls_available_effect(self):
        class EmptyConditions:
            def condition_effects(self, condition): return []
        a = self.actor("a", 20, True)
        self.assertEqual(INITIATIVE.value(EmptyConditions(), a).value, 20)

    def test_empty_roster_resolves_without_decision(self):
        self.assertEqual(INITIATIVE.order(self.e, []), [])

    def test_engine_delegation_uses_actual_corrected_order(self):
        a, b = self.actor("a", 20, True), self.actor("b", 15)
        self.assertEqual(self.e.initiative([a, b]), [b, a])

    def test_source_and_spec_integrity(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from audit_common_initiative_semantics import validate
        spec = json.loads((ROOT / "data/verification/common-initiative-semantics.json").read_text(encoding="utf-8"))
        self.assertEqual(validate(spec, ROOT), [])
        for mutate in (lambda s: s.update(whole_semantic_complete=True), lambda s: s["source_anchors"][0].update(excerpt="fake"), lambda s: s["clauses"][0].update(source_anchor_ids=["unknown"]), lambda s: s["clauses"][3].update(status="source_resolved_local")):
            changed = copy.deepcopy(spec); mutate(changed); self.assertTrue(validate(changed, ROOT))


if __name__ == "__main__":
    class Result(unittest.TextTestResult):
        def __init__(self, *a, **kw): super().__init__(*a, **kw); self.rows = []
        def addSuccess(self, test): super().addSuccess(test); self.rows.append({"id": "INIT-" + test._testMethodName, "status": "pass"})
        def addFailure(self, test, err): super().addFailure(test, err); self.rows.append({"id": "INIT-" + test._testMethodName, "status": "fail"})
        def addError(self, test, err): super().addError(test, err); self.rows.append({"id": "INIT-" + test._testMethodName, "status": "error"})
        def addSubTest(self, test, subtest, err):
            super().addSubTest(test, subtest, err)
            if err: self.rows.append({"id": "INIT-" + test._testMethodName + str(subtest), "status": "fail"})
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(CommonInitiativeTests))
    files = ["engine/initiative.py", "engine/engine.py", "engine/rulings.py", "engine/gm_state.py", "engine/encounter.py", "tools/test_common_initiative.py", "tools/audit_common_initiative_semantics.py", "data/verification/common-initiative-semantics.json", "data/core-rules.json", "data/conditions.json", "input/ch06-gameplay.md", "input/ch07-combat.md"]
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "scope": "Local isolated paralysis order, ordinary bonus/fixed values, explicit GM decisions, unresolved composition and tie boundaries; not all initiative semantics.", "whole_semantic_complete": False, "results": result.rows, "input_hashes": {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}}
    (ROOT / "output/common-initiative-tests.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
