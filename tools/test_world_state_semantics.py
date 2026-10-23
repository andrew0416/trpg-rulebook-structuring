"""Mutation checks and abstract-state counterexamples; not engine tests."""
import copy
import json
import unittest
from datetime import datetime, timezone
from audit_world_state_semantics import ROOT, SPEC, STAGE_KEYS, validate, closure_blockers, actor_fragment_errors, ap_fragment_errors, hashes, baseline_death

class WorldStateTests(unittest.TestCase):
    def spec(self):
        return json.loads((ROOT / SPEC).read_text(encoding="utf-8"))
    def actor(self, hp=1, temp=0, conscious="Conscious"):
        return dict(hp=hp,temp_hp=temp,consciousness=conscious,stages={k:0 for k in STAGE_KEYS})
    def test_actual_anchors_and_contracts_integrity(self):
        self.assertEqual(validate(self.spec()), [])
    def test_draft_never_closes_ruleset(self):
        self.assertIn("uncertified:engine_conformance",closure_blockers(self.spec()))
        self.assertGreater(len(closure_blockers(self.spec())),50)
    def test_changed_excerpt_rejected(self):
        s=self.spec();s["source_facts"][0]["source"]["excerpt"]+="invented"
        self.assertIn("stale_source:STATE-01",validate(s))
    def test_changed_hash_rejected(self):
        s=self.spec();s["source_facts"][0]["source"]["excerpt_sha256"]="0"*64
        self.assertIn("stale_source:STATE-01",validate(s))
    def test_missing_state_component_rejected(self):
        s=self.spec();s["types"].pop()
        self.assertIn("state_type_set_mismatch",validate(s))
    def test_unknown_field_source_rejected(self):
        s=self.spec();s["types"][0]["fields"]["hp"]["source_refs"]=["invented"]
        self.assertIn("unknown_source_ref:invented",validate(s))
    def test_field_type_domain_required(self):
        s=self.spec();s["types"][0]["fields"]["hp"]["domain"]=""
        self.assertIn("field_incomplete:Actor.hp",validate(s))
    def test_modeling_convention_not_mislabeled_source(self):
        s=self.spec();s["types"][0]["origin"]="direct_source_quote"
        self.assertIn("type_origin_misrepresented:Actor",validate(s))
    def test_transition_frame_required(self):
        s=self.spec();s["transitions"][0]["frame_conditions"]=[]
        self.assertIn("transition_contract_missing:declare_action:frame_conditions",validate(s))
    def test_transition_boundary_cases_required(self):
        s=self.spec();s["transitions"][0]["boundary_cases"]=[]
        self.assertIn("transition_contract_missing:declare_action:boundary_cases",validate(s))
    def test_fake_certificate_rejected(self):
        s=self.spec();s["certification"]["engine_conformance"]=True
        self.assertIn("unsupported_completion_claim",validate(s))
    def test_counterexample_required_for_obligation(self):
        s=self.spec();s["proof_obligations"][0]["counterexamples"]=[]
        self.assertIn("proof_obligation_incomplete:WORLD-P01",validate(s))
    def test_negative_hp_valid_while_fainted(self):
        self.assertEqual(actor_fragment_errors(self.actor(-50,0,"Fainted")),[])
    def test_positive_hp_can_remain_fainted(self):
        # Source ch07:635 supplies this counterexample to hp>0 => conscious.
        self.assertEqual(actor_fragment_errors(self.actor(9,0,"Fainted")),[])
    def test_nonpositive_hp_cannot_be_conscious_in_default_model(self):
        self.assertIn("nonpositive_hp_conscious",actor_fragment_errors(self.actor(0)))
        self.assertIn("nonpositive_hp_conscious",actor_fragment_errors(self.actor(-1)))
    def test_temp_hp_not_part_of_consciousness_threshold(self):
        self.assertIn("nonpositive_hp_conscious",actor_fragment_errors(self.actor(0,50)))
    def test_temp_hp_cannot_be_negative(self):
        self.assertIn("invalid_temp_hp",actor_fragment_errors(self.actor(1,-1)))
    def test_hp_has_no_combat_stage(self):
        a=self.actor();a["stages"]["hp"]=0
        self.assertIn("invalid_stage_keys",actor_fragment_errors(a))
    def test_stage_boundary_exact_not_infinite(self):
        for stage,valid in [(-7,False),(-6,True),(6,True),(7,False)]:
            a=self.actor();a["stages"]["attack"]=stage
            self.assertEqual("invalid_stage_value" not in actor_fragment_errors(a),valid)
    def test_boolean_not_numeric_state(self):
        self.assertIn("hp_not_integer",actor_fragment_errors(self.actor(True)))
        self.assertIn("invalid_temp_hp",actor_fragment_errors(self.actor(1,True)))
    def test_ap_scene_end_preserves_other_allocations(self):
        # capacity7, bound2, drained1. Scene end restores spent3 => available4.
        before=dict(capacity=7,spent=3,bound={"e":2},drained=1,available=1)
        after=dict(capacity=7,spent=0,bound={"e":2},drained=1,available=4)
        self.assertEqual(ap_fragment_errors(before),[]);self.assertEqual(ap_fragment_errors(after),[])
        bad=dict(after,available=7)
        self.assertIn("ap_conservation_violation",ap_fragment_errors(bad))
    def test_ap_overallocation_rejected(self):
        self.assertIn("ap_conservation_violation",ap_fragment_errors(dict(capacity=5,spent=4,bound={"e":2},drained=0,available=0)))
    def test_ap_boolean_not_integer(self):
        self.assertIn("ap_not_nonnegative_integer",ap_fragment_errors(dict(capacity=5,spent=True,bound={},drained=0,available=4)))

    def test_context_reviews_preserve_two_conflicts(self):
        spec=self.spec();reviews={r["id"]:r for r in spec["interpretation_reviews"]}
        self.assertIsNone(reviews["WORLD-REVIEW-AP-BOUNDARY"]["resolution"])
        self.assertIsNone(reviews["WORLD-REVIEW-TEMP-EXPIRY"]["resolution"])
        self.assertIn("interpretation_unresolved:WORLD-REVIEW-TEMP-EXPIRY",closure_blockers(spec))
    def test_pdf_excerpt_mutation_rejected(self):
        spec=self.spec();spec["interpretation_reviews"][0]["evidence"][2]["excerpt"]="wrong"
        self.assertIn("stale_review_excerpt:WORLD-REVIEW-AP-BOUNDARY",validate(spec))
    def test_pdf_hash_mutation_rejected(self):
        spec=self.spec();spec["interpretation_reviews"][1]["evidence"][1]["file_sha256"]="0"*64
        self.assertIn("stale_review_pdf:WORLD-REVIEW-TEMP-EXPIRY",validate(spec))
    def test_source_conflict_cannot_silently_select_policy(self):
        spec=self.spec();spec["interpretation_reviews"][1]["resolution"]="PTU automatically wins"
        self.assertIn("unresolved_review_has_resolution:WORLD-REVIEW-TEMP-EXPIRY",validate(spec))
    def test_death_threshold_equality_is_inclusive(self):
        # Literal source boundary examples; no expected value generated by formula.
        self.assertFalse(baseline_death(-79,40,9,False))
        self.assertTrue(baseline_death(-80,40,9,False))
        self.assertTrue(baseline_death(-81,40,9,False))
    def test_death_uses_lower_of_negative_thresholds(self):
        self.assertFalse(baseline_death(-40,20,9,False))
        self.assertFalse(baseline_death(-49,20,9,False))
        self.assertTrue(baseline_death(-50,20,9,False))
    def test_friendly_protects_hp_not_ten_injuries(self):
        self.assertFalse(baseline_death(-100,40,9,True))
        self.assertTrue(baseline_death(-100,40,10,True))
        self.assertTrue(baseline_death(1,40,10,True))
    def test_death_unknown_context_is_not_false(self):
        with self.assertRaises(ValueError):baseline_death(-100,40,0,None)
        with self.assertRaises(ValueError):baseline_death(-100,0,0,False)

class RecordedResult(unittest.TextTestResult):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.results=[]
    def addSuccess(self,test):
        super().addSuccess(test);self.results.append(dict(id=test.id(),status="pass"))
    def addFailure(self,test,err):
        super().addFailure(test,err);self.results.append(dict(id=test.id(),status="fail"))
    def addError(self,test,err):
        super().addError(test,err);self.results.append(dict(id=test.id(),status="error"))
    def addSkip(self,test,reason):
        super().addSkip(test,reason);self.results.append(dict(id=test.id(),status="skip",reason=reason))

def main():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(WorldStateTests)
    result=unittest.TextTestRunner(verbosity=1,resultclass=RecordedResult).run(suite)
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),status="passed" if result.wasSuccessful() else "failed",verification_kind="specification_integrity_and_abstract_state_fragments",engine_conformance=False,whole_rule_certified=False,tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),results=result.results,input_hashes=hashes(),limitations=["No engine behavior executed.","State fragments do not validate every common or specialized state.","Passing mutation tests do not discharge semantic completeness obligations."])
    target=ROOT/"output/world-state-semantics-tests.json";target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0 if result.wasSuccessful() else 1
if __name__=="__main__":
    raise SystemExit(main())
