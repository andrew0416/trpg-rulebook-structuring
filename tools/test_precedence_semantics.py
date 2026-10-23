"""Independent examples and adversarial checks for the common precedence model."""
import copy, hashlib, itertools, json, unittest
from datetime import datetime, timezone
from pathlib import Path
from audit_precedence_semantics import ROOT, audit, duplicate_evidence, finite_check, fixture_edge, model_errors, resolve, source_errors

def rule(rid, value, scope=('outside','inside'), aspect='value', selected=True):
    return dict(id=rid, value=value, scope=list(scope), aspect=aspect, selected=selected)

def model(rules, edges=(), aspects=None):
    return dict(contexts=['outside','inside'], aspects=aspects or {'value':'exclusive'},
                rules=rules, overrides=[fixture_edge(a,b) for a,b in edges])

class PrecedenceTests(unittest.TestCase):
    def test_all_1600_finite_cases_match_independent_path_oracle(self):
        report = finite_check()
        self.assertEqual(report['accepted_directed_acyclic_graphs'],25)
        self.assertEqual(report['cases'],1600)
        self.assertEqual(report['counterexamples'],[])

    def test_finite_checker_detects_input_order_winner_mutant(self):
        def mutant(m,c):
            result=resolve(m,c)
            active=[r for r in m['rules'] if r['selected']]
            if active:
                result['value']=dict(status='resolved',value=active[-1]['value'],contributors=[active[-1]['id']],unknown=[])
            return result
        self.assertEqual(finite_check(mutant)['status'],'fail')

    def test_exception_is_local_to_scope(self):
        m=model([rule('general',1),rule('exception',2,('inside',))],[('general','exception')])
        self.assertEqual(resolve(m,'outside')['value']['value'],1)
        self.assertEqual(resolve(m,'inside')['value']['value'],2)

    def test_narrow_scope_alone_cannot_manufacture_override(self):
        m=model([rule('general',1),rule('narrow',2,('inside',))])
        self.assertEqual(resolve(m,'inside')['value']['status'],'unresolved')

    def test_unselected_exception_preserves_general(self):
        m=model([rule('general',1),rule('exception',2,('inside',),selected=False)],[('general','exception')])
        self.assertEqual(resolve(m,'inside')['value']['value'],1)

    def test_unknown_selection_cannot_be_silently_false(self):
        m=model([rule('general',1),rule('exception',2,('inside',),selected=None)],[('general','exception')])
        self.assertEqual(resolve(m,'inside')['value']['status'],'unresolved')
        self.assertEqual(resolve(m,'outside')['value']['value'],1)

    def test_incomparable_conflicting_maxima_remain_unresolved(self):
        m=model([rule('general',0),rule('left',1),rule('right',2)],[('general','left'),('general','right')])
        result=resolve(m,'inside')['value']
        self.assertEqual(result['status'],'unresolved')
        self.assertEqual(result['contributors'],['left','right'])

    def test_identical_assignments_coexist_with_provenance(self):
        m=model([rule('left',7),rule('right',7)])
        result=resolve(m,'inside')['value']
        self.assertEqual((result['status'],result['value']),('resolved',7))
        self.assertEqual(result['contributors'],['left','right'])

    def test_declared_additive_effects_coexist(self):
        m=model([rule('left',20),rule('right',30)],aspects={'value':'additive'})
        self.assertEqual(resolve(m,'inside')['value']['value'],50)

    def test_composition_never_mixes_aspects(self):
        m=model([rule('x',20,aspect='first'),rule('y',30,aspect='second')],aspects={'first':'additive','second':'additive'})
        result=resolve(m,'inside')
        self.assertEqual(result['first']['value'],20)
        self.assertEqual(result['second']['value'],30)

    def test_override_only_replaces_corresponding_aspect(self):
        m=model([rule('general-cost',1,aspect='cost'),rule('general-range',6,aspect='range'),rule('exception-cost',0,('inside',),aspect='cost')],
                [('general-cost','exception-cost')],{'cost':'exclusive','range':'exclusive'})
        result=resolve(m,'inside')
        self.assertEqual(result['cost']['value'],0)
        self.assertEqual(result['range']['value'],6)

    def test_transitive_specialization_survives_inactive_intermediate(self):
        m=model([rule('a',1),rule('b',2,selected=False),rule('c',3)],[('a','b'),('b','c')])
        self.assertEqual(resolve(m,'inside')['value']['contributors'],['c'])

    def test_every_rule_and_edge_permutation_preserves_result(self):
        rules=[rule('a',1),rule('b',2),rule('c',3)]
        expected=resolve(model(rules,[('a','b'),('b','c')]),'inside')
        for rows in itertools.permutations(rules):
            for edges in itertools.permutations([('a','b'),('b','c')]):
                self.assertEqual(resolve(model(list(rows),edges),'inside'),expected)

    def test_empty_active_set_is_not_success_or_failure(self):
        m=model([rule('a',1,selected=False)])
        self.assertEqual(resolve(m,'inside')['value']['status'],'not_applicable')

    def test_no_source_override_mapping_is_rejected(self):
        m=model([rule('a',1),rule('b',2)],[('a','b')])
        m['overrides'][0]['evidence'].pop('mapping')
        self.assertIn('unsupported_override',model_errors(m))

    def test_cycles_are_rejected(self):
        m=model([rule('a',1),rule('b',2),rule('c',3)],[('a','b'),('b','c'),('c','a')])
        with self.assertRaisesRegex(ValueError,'cyclic_specificity'):resolve(m,'inside')

    def test_reflexive_edges_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'reflexive_edge'):resolve(model([rule('a',1)],[('a','a')]),'inside')

    def test_unknown_edge_endpoint_rejected(self):
        with self.assertRaisesRegex(ValueError,'unknown_edge_endpoint'):resolve(model([rule('a',1)],[('a','missing')]),'inside')

    def test_exception_outside_parent_scope_rejected(self):
        m=model([rule('a',1,('inside',)),rule('b',2)],[('a','b')])
        with self.assertRaisesRegex(ValueError,'exception_outside_general_scope'):resolve(m,'inside')

    def test_cross_aspect_override_rejected(self):
        m=model([rule('a',1,aspect='first'),rule('b',2,aspect='second')],[('a','b')],{'first':'exclusive','second':'exclusive'})
        with self.assertRaisesRegex(ValueError,'cross_aspect_override'):resolve(m,'inside')

    def test_unknown_context_and_algebra_rejected(self):
        m=model([rule('a',1)])
        with self.assertRaisesRegex(ValueError,'unknown_context'):resolve(m,'missing')
        m['aspects']['value']='multiply'
        with self.assertRaisesRegex(ValueError,'unknown_composition'):resolve(m,'inside')

    def test_boolean_not_interchangeable_with_integer_selection(self):
        m=model([rule('a',1,selected=1)])
        with self.assertRaisesRegex(ValueError,'invalid_selection'):resolve(m,'inside')

    def test_duplicate_ids_do_not_silently_overwrite(self):
        with self.assertRaisesRegex(ValueError,'duplicate_rule_id'):resolve(model([rule('a',1),rule('a',2)]),'inside')

    def test_source_anchors_current_and_mutations_detected(self):
        spec=json.loads((ROOT/'data/verification/precedence-semantics.json').read_text(encoding='utf-8'))
        self.assertEqual(source_errors(spec,ROOT),[])
        spec['source_grounding'][0]['source']['excerpt']='invented'
        self.assertTrue(source_errors(spec,ROOT))

    def test_equal_body_different_trigger_is_not_duplicate_rule(self):
        found=duplicate_evidence(ROOT)
        self.assertEqual(found['status'],'not_equivalent_in_saved_source')
        self.assertTrue(found['same_primary_effect'])
        self.assertEqual(found['differing_fields']['발동조건'],['','현재 HP와 최대 HP가 같을떄'])
        self.assertEqual([c['record_number'] for c in found['candidates']],[303,492])

    def test_complete_audit_never_certifies_rulebook(self):
        result=audit()
        self.assertEqual(result['errors'],[])
        self.assertFalse(result['whole_rule_certified'])
        self.assertEqual(result['runtime_conformance'],'not_implemented_by_this_model')
        self.assertTrue(result['remaining'])

if __name__ == '__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='PRECEDENCE-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='PRECEDENCE-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='PRECEDENCE-'+t._testMethodName,status='error'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(PrecedenceTests))
    paths=['tools/test_precedence_semantics.py','tools/audit_precedence_semantics.py',
           'data/verification/precedence-semantics.json','input/ch01-intro.md','input/ch06-gameplay.md','input/db/abilities.csv']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Finite reference model, source-anchor integrity and duplicate identity obligations; not game behavior certification.',
        results=result.rows,input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/precedence-semantics-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
