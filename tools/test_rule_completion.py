"""Gate regression: prevents test count or a happy path from certifying a rule."""
import copy
import unittest
from check_rule_completion import assess_contract, expression_errors, component_errors


def complete():
    return dict(id="fixture",status="reviewed",source_coverage_review="complete",implementation_review="complete",
        sources=[{"file":"source-fixture"}],implementation_paths=["fixture:handler"],remaining_source_obligations=[],
        clauses=[dict(id="c",event="test",when=True,effects=[dict(op="assign",value=1)],unresolved=[],
            tests=[dict(id="T",role="positive")],required_test_roles=["positive"])])


class CompletionGateTests(unittest.TestCase):
    def assess(self,c,status="pass"):
        return assess_contract(c,{"T":{"status":status}})
    def test_reviewed_contract_with_all_declared_obligations_passes(self):
        self.assertEqual(self.assess(complete())["status"],"verified")
    def test_happy_path_does_not_cover_condition_complement(self):
        c=complete();c["clauses"][0]["when"]={"op":"eq","args":[{"var":"kind"},"pokemon"]}
        self.assertEqual(self.assess(c)["status"],"blocked")
    def test_missing_declared_boundary_is_blocked(self):
        c=complete();c["clauses"][0]["required_test_roles"].append("boundary")
        self.assertEqual(self.assess(c)["status"],"blocked")
    def test_failed_skipped_and_error_are_never_passing(self):
        for status in ["fail","error","skip","expected_failure"]:
            self.assertEqual(self.assess(complete(),status)["status"],"blocked")
    def test_missing_or_unknown_test_is_blocked(self):
        c=complete();c["clauses"][0]["tests"]=[]
        self.assertEqual(self.assess(c)["status"],"blocked")
        c=complete();c["clauses"][0]["tests"][0]["id"]="missing"
        self.assertEqual(self.assess(c)["status"],"blocked")
    def test_pending_source_review_blocks_even_green_tests(self):
        c=complete();c["source_coverage_review"]="pending"
        self.assertEqual(self.assess(c)["status"],"blocked")
    def test_text_condition_or_unresolved_formula_is_blocked(self):
        c=complete();c["clauses"][0]["when"]="whenever appropriate"
        self.assertEqual(self.assess(c)["status"],"blocked")
        c=complete();c["clauses"][0]["effects"][0]["formula"]="TODO"
        self.assertEqual(self.assess(c)["status"],"blocked")
    def test_invalid_symbolic_operator_arity_is_blocked(self):
        self.assertTrue(expression_errors({"op":"eq","args":[1]}))
        self.assertTrue(expression_errors({"op":"unknown","args":[1,2]}))

    def test_component_requires_matching_rule_test_and_scope(self):
        rec={'rule_id':'move/a','tested_components':{'frequency':{'test_id':'F','scope':'frequency only'}}}
        results={'F':{'status':'pass'}}
        self.assertEqual(component_errors(rec,results,{'F':'move/a'}),[])
        self.assertTrue(component_errors(rec,results,{'F':'move/b'}))
        self.assertTrue(component_errors(rec,{}, {'F':'move/a'}))
        self.assertTrue(component_errors(rec,{'F':{'status':'fail'}},{'F':'move/a'}))
        rec['tested_components']['frequency'].pop('scope')
        self.assertTrue(component_errors(rec,results,{'F':'move/a'}))


if __name__=="__main__":
    unittest.main()
